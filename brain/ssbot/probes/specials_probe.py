"""Scripted verification of the special-move table (task 1v1 T3, forum.md 48): the arrive-and-strike rows the run time
would add (ssbot.combat.specials.strike_rows) executed open loop against a live Clapper slam. Not a planner: the row
is chosen by the trial's filter, so the table's entries are verified directly, including the ones no recording has
(the person: human play cannot think of every tactic).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.specials_probe --instance 0 --trials 120 --seed 1 \
        [--savestate fo_cl_w7w] [--out C:/ssbot/data/m2_specials/live]

A trial: stand wait_x in front of the Clapper (following it) until a Slam Antic; stand until the antic frame k_start;
plan from the standing state (the start D frames ahead: the hero stands, so the state is the same), pick a strike row
whose entry matches the trial's filter (cert both / bounce, the hero's side at the press front / behind), send it
frame by frame (each ACTION is sent for STATE frame + 2), then SETTLE_F frames with no input. Logged per trial: the
entry, the planned press frame, the frames sent (gaps), the hero's health and the Clapper's HP per frame from the
plan to the end: landed (the Clapper lost HP within 6 frames of the press), bounce (the hero's vy > 6 within 10
frames after the press), hurt (the hero lost health; before / after the press).

Safety: a free training instance; save suppression and LethalBlock on; no invincibility.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

from ssbot.combat import specials as sp
from ssbot.combat.pogo_slam import SlamTimeline
from ssbot.ipc.oracle_link import OracleLink
from ssbot.knowledge import kinematics as kin
from ssbot.probes.pogo_probe import clapper, control, hx
from ssbot.probes.pogo_target import MIN_HP, SETTLE_F, WAIT_S, Target, stop_requested
from ssbot.tools.pogo_theory import load_kin

D = 4                      # frames between the plan's state and the row's first frame (the planning time)
FILTERS = ("both_front", "both_behind", "bounce_front", "bounce_behind")


def trial_specs(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        out.append({"i": i, "wait_x": rng.choice((3.0, 4.5, 6.0, 7.5, 9.0)),
                    "k_start": rng.choice((2, 8, 14, 20, 26, 32, 38, 44)),
                    "filter": FILTERS[i % len(FILTERS)], "pick": rng.random()})
    return out


class Probe(Target):
    def __init__(self, link, savestate, tab: sp.SpecialTable):
        super().__init__(link, savestate)
        self.params, self.terrain = load_kin()
        self.tl = SlamTimeline.load()
        self.lut = tab.lut("CL_SLAM", certs=("both", "bounce"))

    def run(self, t: dict) -> dict:
        s = self.step(0)
        e = clapper(s)
        hp = int(s["hero"].get("health") or 0)
        if e is None or hp < MIN_HP or (e.get("hp") or 0) < 70:
            s = self.load()
        wx = float(t["wait_x"])
        s, _ = self.walk_to(s, self.side_x(s, wx), 240)
        t0, fa = time.time(), None
        while time.time() - t0 < WAIT_S:
            e = clapper(s)
            st = control(e)
            if st == "Slam Antic":
                tin = next((float(m.get("t") or 0.0) for m in e.get("fsms") or () if m.get("name") == "Control"), 0.0)
                fa = s["f"] - int(round(tin * 60))
                break
            m = 0
            if e is not None and (st == "Evade Scuttle" or abs(abs(hx(s) - float(e["pos"][0])) - wx) > 0.4):
                m = self.walk_mask(s, self.side_x(s, wx))
            s = self.step(m)
        if fa is None:
            return {"skip": "no slam"}
        # stand until k_start (at least 3 frames still)
        still = 0
        while s["f"] - fa < int(t["k_start"]) or still < 3:
            s = self.step(0)
            still = still + 1 if abs(float((s["hero"].get("vel") or [0, 0])[0])) < 0.05 else 0
            if s["f"] - fa > 60:
                return {"skip": "never still", "f_antic": fa}
        e = clapper(s)
        h = s["hero"]
        face = 1 if e.get("flipX") else -1
        cx, cy = float(e["pos"][0]), float(e["pos"][1])
        f_plan = s["f"]
        k_now = f_plan + 1 + D - fa                 # rollout index 0; mask 0 lands on frame fa + k_now + 1
        start = kin.initial_state(self.params, float(h["pos"][0]), float(h["pos"][1]), facing=-face, ground=True)
        xa = cx - face * self.tl.disp[min(max(k_now, 0), len(self.tl.disp) - 1)]
        t1 = time.perf_counter()
        r = sp.strike_rows(self.params, self.terrain, start, self.lut, k_now, xa, cy, face, self.tl.disp, 36,
                           max_rows=400, per_entry=1, js_step=1)
        plan_ms = (time.perf_counter() - t1) * 1e3
        cert, side = t["filter"].split("_")
        ok = [i for i, en in enumerate(r.entry) if en.cert == cert and ((en.dx0 >= 0) == (side == "front"))]
        info = {"f_antic": fa, "k_now": k_now, "cx": round(cx, 3), "cy": round(cy, 3), "face": face,
                "hx": round(float(h["pos"][0]), 3), "rows": len(r.cmd), "tried": r.tried, "match": len(ok),
                "plan_ms": round(plan_ms, 1)}
        if not ok:
            for _ in range(SETTLE_F):
                s = self.step(0)
            return info | {"skip": "no row"}
        i = ok[min(int(t["pick"] * len(ok)), len(ok) - 1)]
        en, masks, jp = r.entry[i], [int(m) for m in r.cmd[i]], int(r.j_press[i])
        f_first = fa + k_now + 1                     # the frame mask 0 lands on
        f_press = f_first + jp
        if s["f"] + 2 > f_first:
            return info | {"skip": "planned too slowly", "late_f": s["f"] + 2 - f_first}
        while s["f"] + 2 < f_first:
            s = self.step(0)
        sent, trace = [], []
        for _ in range(len(masks) + SETTLE_F):
            idx = s["f"] + 2 - f_first
            m = masks[idx] if 0 <= idx < len(masks) else 0
            sent.append((s["f"] + 2, m))
            s = self.step(m)
            c = clapper(s)
            trace.append((s["f"], int(s["hero"].get("health") or 0), round(float((s["hero"].get("vel") or [0, 0])[1]), 2),
                          None if c is None else c.get("hp"), round(hx(s), 3), round(float(s["hero"]["pos"][1]), 3)))
        hp0 = next((x[1] for x in trace if x[0] >= f_first - 1), trace[0][1])
        hurt = [x[0] - f_press for x in trace if x[1] < hp0]
        chp0 = next((x[3] for x in trace if x[0] >= f_press - 1 and x[3] is not None), None)
        landed = chp0 is not None and any(x[3] is not None and x[3] < chp0 for x in trace if f_press <= x[0] <= f_press + 6)
        bounce = any(x[2] > 6 for x in trace if f_press < x[0] <= f_press + 10)
        pp = next((x for x in trace if x[0] == f_press), None)
        return info | {"entry": en.id, "cert": en.cert, "k0": en.k0, "k1": en.k1, "dx": [en.dx0, en.dx1],
                       "dy": [en.dy0, en.dy1], "vy": en.vy, "key": en.key, "share": en.share, "j_press": jp,
                       "f_first": f_first, "f_press": f_press, "masks": masks,
                       "gaps": sum(1 for a, b in zip(sent, sent[1:]) if b[0] - a[0] != 1),
                       "press_pos": None if pp is None else [round((pp[4] - cx) * face, 3), round(pp[5] - cy, 3)],
                       "landed": bool(landed), "bounce": bool(bounce), "hurt_rel": hurt[:1],
                       "hurt_before": bool(hurt and hurt[0] < 0), "hurt": bool(hurt),
                       "success": bool(landed and not hurt)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--savestate", default="fo_cl_w7w")
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=r"C:\ssbot\data\m2_specials\live")
    a = ap.parse_args(argv)
    from ssbot.record.recorder import Recorder
    specs = trial_specs(a.trials, a.seed)
    tab = sp.SpecialTable.load()
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    rec = None
    try:
        link.rpc("guards.set", save_suppression=True, lethal_block="block")
        link.rpc("fsmtap.set", all=True)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"specials_i{a.instance}_s{a.seed}",
                       config={"probe": "specials_probe", "seed": a.seed, "savestate": a.savestate}).start()
        log = (rec.path / "specials_trials.jsonl").open("w", encoding="utf-8")
        pr = Probe(link, a.savestate, tab)
        pr.load()
        for t in specs:
            if stop_requested():
                print("stop requested", flush=True)
                break
            try:
                info = pr.run(t)
            except Exception as ex:  # noqa: BLE001
                info = {"error": repr(ex)}
                try:
                    pr.load()
                except Exception as ex2:  # noqa: BLE001
                    print("reload failed", ex2, flush=True)
                    break
            link.rpc("input.release", timeout_s=10)
            pr.d.collect()
            row = {"spec": t} | info
            log.write(json.dumps(row) + "\n")
            log.flush()
            print(json.dumps({k: v for k, v in row.items() if k != "masks"})[:300], flush=True)
        log.close()
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
            link.rpc("fsmtap.set", all=False)
        except Exception:  # noqa: BLE001
            pass
        if rec is not None:
            rec.close()
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
