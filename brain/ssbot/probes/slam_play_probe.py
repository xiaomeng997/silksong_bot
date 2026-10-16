"""Fixed-point live trials of the slam playbook (task 1v1 SP1, forum.md 65): the hero waits on the ground D u in front
of the Clapper (centre to centre, following it), and from the first STATE that reads Slam Antic the playbook's own
code (ssbot.combat.slam_play.SlamPlay.step, the policy's call) decides every frame; its mask for STATE f is sent for
f + 2 as the episode loop does (ssbot.train.episode._act), with an optional sleep before the send that stands in for
the planner's tick (--tick-ms). When the playbook declines or aborts the probe stands still (no key).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.slam_play_probe --instance 0 --dists 4.5,5.5,6.5,7.5 --per 20 \
        [--seed 1] [--tick-ms 0] [--savestate fo_cl_w7w] [--out C:/ssbot/data/m2_play/live]

Per trial (<recording>/play_trials.jsonl): the distance class, the hero's x at the antic sighting, the playbook's run
(start / jump / press frames it sent, its end and why), and from the STATEs (act.mask = the keys the game held): the
antic entry fa, Slam 0 / Slam 1 / Slam Recover entries, the real jump and press frames, landed (the Clapper lost HP
within 14 frames of the press), bounce (vy > 6 within 14 frames after the press), the hero's damage (frame relative to
Slam 0, source) until the Slam Recover ends and after it (to the end of the trial), success = landed and no damage
until the Slam Recover ends. Settings env SSBOT_FORUM_SLAM_PLAY_SET (slam_play.PlayCfg.from_env).

Safety: a free training instance; save suppression and LethalBlock on; no invincibility; the time scale is set to 1.0
at the start (the instances are left frozen at 1e-4 between runs).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import replace
from pathlib import Path

from ssbot.combat import slam_play as sp
from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.probes.pogo_target import MIN_HP, Target, stop_requested

M_L, M_R, M_J, M_A = mask("left"), mask("right"), mask("jump"), mask("attack")
WAIT_S = 12.0
SETTLE_F = 30
MAX_F = 260


def _ctl(e) -> str | None:
    return sp.control(e)[0]


class PlayProbe(Target):
    def __init__(self, link: OracleLink, savestate: str, tick_ms: float, pin: bool = False):
        super().__init__(link, savestate)
        self.tick_ms = tick_ms
        self.play = sp.SlamPlay()
        self.base = self.play.cfg
        self.pin = pin

    def scale1(self) -> None:
        r = self.link.rpc("time.scale", timeout_s=10, scale=1.0)
        t0 = time.monotonic()
        while abs(float((r or {}).get("time_scale") or 0.0) - 1.0) > 1e-3 and time.monotonic() - t0 < 5:
            time.sleep(0.2)
            r = self.link.rpc("time.scale", timeout_s=10)

    def load(self) -> dict:
        self.scale1()
        s = super().load()
        self.scale1()
        return s

    def follow_mask(self, s: dict, d: float) -> int:
        e = sp.clapper(s)
        if e is None:
            return 0
        tx = self.side_x(s, d)
        st = _ctl(e)
        if st == "Evade Scuttle" or abs(abs(sp.hero_x(s) - float(e["pos"][0])) - d) > 0.3:
            return self.walk_mask(s, tx)
        return 0

    def trial(self, d: float) -> dict:
        link = self.link
        s = link.wait_state(newer_than=link.frame, timeout_s=3.0)
        e = sp.clapper(s)
        hp = int(s["hero"].get("health") or 0)
        if e is None or hp < MIN_HP or (e.get("hp") or 0) < 70:
            s = self.load()
        last = s["f"]
        if self.pin:
            # --pin: the strike from D itself (the stand band pinned at D, the jump band around it): x at the jump
            # classes, the band's edges
            b = self.base
            self.play.cfg = replace(b, stand=(d - 0.08, d + 0.08), band=(min(b.band[0], d - 0.3), max(b.band[1], d + 0.3)),
                                    reach=(2.7, max(b.reach[1], d + 1.5)))
        self.play.reset()
        t0 = time.time()
        seen = None
        rows, n_after = [], 0
        while True:
            e = sp.clapper(s)
            st = _ctl(e)
            if seen is None:
                if st == "Slam Antic":
                    seen = {"f": s["f"], "x": round((sp.hero_x(s) - float(e["pos"][0])) * (1 if e.get("flipX") else -1), 3),
                            "ground": sp.on_ground(s), "vx": round(float((s["hero"].get("vel") or [0, 0])[0]), 2)}
                elif time.time() - t0 > WAIT_S:
                    return {"skip": "no slam"}
            if seen is None:
                m = self.follow_mask(s, d)
            else:
                pm = self.play.step(s["f"], s, sp.on_ground(s), bool(s["hero"].get("hero_accepting_input", True)))
                if self.tick_ms > 0:
                    time.sleep(self.tick_ms / 1000.0)
                m = 0 if pm is None else pm
            link.act(s["f"] + 2, m, hold_frames=0)
            if seen is not None:
                h = s.get("hero") or {}
                rows.append(self._row(s, e, m))
                if self.play.run is None and st not in sp.SLAM_STATES:
                    n_after += 1
                    if n_after > SETTLE_F:
                        break
                if len(rows) > MAX_F:
                    break
            s = link.wait_state(newer_than=last, timeout_s=3.0)
            if s["f"] > last + 1 and seen is not None:
                rows.append({"gap": s["f"] - last - 1})
            last = s["f"]
        link.act(last + 2, 0, hold_frames=0)
        run = self.play.done[-1] if self.play.done else self.play.run
        return {"d": d, "pin": self.pin, "seen": seen} | self._outcome(run, rows)

    @staticmethod
    def _row(s: dict, e: dict | None, m: int) -> dict:
        h = s.get("hero") or {}
        evs = []
        for ev in s.get("ev") or ():
            k, dd = ev.get("k"), ev.get("d") or {}
            if k == "hit" and dd.get("type_key") == sp.CLAPPER:
                evs.append(["hit", str(dd.get("src")), dd.get("dealt")])
            elif k == "hp" and (dd.get("delta") or 0) < 0:
                evs.append(["hp", dd.get("delta"), str(dd.get("source"))])
            elif k == "damage":
                evs.append(["damage", str(dd.get("source")), dd.get("amount")])
        return {"f": s["f"], "m": m, "act": int((s.get("act") or {}).get("mask") or 0),
                "x": round(sp.hero_x(s), 3), "y": round(float(h["pos"][1]), 3),
                "vy": round(float((h.get("vel") or [0, 0])[1]), 2), "g": sp.on_ground(s), "hp": int(h.get("health") or 0),
                "st": _ctl(e), "cx": None if e is None else round(float(e["pos"][0]), 3),
                "chp": None if e is None else e.get("hp"), "ev": evs}

    @staticmethod
    def _outcome(run, rows: list) -> dict:
        R = [r for r in rows if "f" in r]
        out = {"gaps": sum(r.get("gap", 0) for r in rows)}
        if run is not None:
            out["play"] = {"fa": run.fa, "face": run.face, "phase": run.phase, "why": run.why, "k_start": run.k_start,
                           "x_start": run.x_start, "k_jump": run.k_jump, "x_jump": run.x_jump, "k_press": run.k_press}
        if not R or run is None:
            return out | {"trace": R}
        fa, face = run.fa, run.face

        def first(pred, after=None):
            return next((r["f"] for r in R if (after is None or r["f"] >= after) and pred(r)), None)

        s0 = first(lambda r: r["st"] == "Slam 0")
        s1 = first(lambda r: r["st"] == "Slam 1")
        rec = first(lambda r: r["st"] == "Slam Recover")
        end = first(lambda r: r["st"] not in sp.SLAM_STATES, rec) if rec is not None else None
        prev = 0
        jump = press = None
        for r in R:
            rise = r["act"] & ~prev
            prev = r["act"]
            if jump is None and rise & M_J:
                jump = r["f"]
            if press is None and rise & M_A:
                press = r["f"]
        landed = False
        bounce = False
        if press is not None:
            c0 = next((r["chp"] for r in R if r["f"] >= press - 1 and r["chp"] is not None), None)
            landed = any(r["chp"] is not None and c0 is not None and r["chp"] < c0 for r in R if press <= r["f"] <= press + 14)
            bounce = any(r["vy"] > 6 for r in R if press < r["f"] <= press + 14)
        contact = next((r["f"] for r in R if press is not None and r["f"] >= press and any(e[0] == "hit" for e in r["ev"])), None)
        hp0 = R[0]["hp"]
        hurts = []
        for r in R:
            for ev in r["ev"]:
                if ev[0] == "hp":
                    hurts.append({"f": r["f"], "rel_s0": None if s0 is None else r["f"] - s0, "src": ev[2][-28:],
                                  "st": r["st"], "in_slam": end is None or r["f"] < end})
        if not hurts:                                  # no hp event: the health field
            for a, b in zip(R, R[1:]):
                if b["hp"] < a["hp"]:
                    hurts.append({"f": b["f"], "rel_s0": None if s0 is None else b["f"] - s0, "src": "?", "st": b["st"],
                                  "in_slam": end is None or b["f"] < end})
        hurt_slam = [h for h in hurts if h["in_slam"]]
        pp = next((r for r in R if press is not None and r["f"] == press), None)
        jp = next((r for r in R if jump is not None and r["f"] == jump), None)
        xs = lambda r: None if r is None or r["cx"] is None else round((r["x"] - r["cx"]) * face, 3)   # noqa: E731
        return out | {
            "fa": fa, "antic": None if s0 is None else s0 - fa, "s0": s0, "s1": s1, "rec": rec, "end": end,
            "k_jump_real": None if jump is None else jump - fa, "k_press_real": None if press is None else press - fa,
            "press_rel_s0": None if (press is None or s0 is None) else press - s0,
            "x_jump": xs(jp), "x_press": xs(pp), "y_press": None if pp is None else pp["y"],
            "contact_rel_s0": None if (contact is None or s0 is None) else contact - s0,
            "landed": landed, "bounce": bounce, "hurt_slam": hurt_slam, "hurt_after": [h for h in hurts if not h["in_slam"]],
            "hp0": hp0, "success": bool(landed and not hurt_slam), "trace": R}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--savestate", default="fo_cl_w7w")
    ap.add_argument("--dists", default="4.5,5.5,6.5,7.5")
    ap.add_argument("--per", type=int, default=20, help="slams per distance class (trials that saw a slam)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tick-ms", type=float, default=0.0)
    ap.add_argument("--max-trials", type=int, default=400)
    ap.add_argument("--out", default=r"C:\ssbot\data\m2_play\live")
    ap.add_argument("--tag", default="")
    ap.add_argument("--pin", action="store_true", help="the stand band pinned at each distance class (x at the jump)")
    a = ap.parse_args(argv)
    from ssbot.record.recorder import Recorder
    dists = [float(x) for x in a.dists.split(",")]
    rng = random.Random(a.seed)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    rec = None
    try:
        link.rpc("guards.set", save_suppression=True, lethal_block="block")
        link.rpc("fsmtap.set", all=True)
        pr = PlayProbe(link, a.savestate, a.tick_ms, a.pin)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"slam_play_i{a.instance}_s{a.seed}{a.tag}",
                       config={"probe": "slam_play_probe", "seed": a.seed, "dists": dists, "per": a.per,
                               "tick_ms": a.tick_ms, "savestate": a.savestate, "pin": a.pin,
                               "cfg": pr.play.cfg.__dict__}).start()
        log = (rec.path / "play_trials.jsonl").open("w", encoding="utf-8")
        pr.load()
        done = {d: 0 for d in dists}
        n = 0
        while n < a.max_trials and any(v < a.per for v in done.values()):
            if stop_requested():
                print("stop requested", flush=True)
                break
            left = [d for d in dists if done[d] < a.per]
            d = rng.choice(left)
            try:
                info = pr.trial(d)
            except Exception as ex:  # noqa: BLE001
                info = {"d": d, "error": repr(ex)}
                try:
                    pr.load()
                except Exception as ex2:  # noqa: BLE001
                    print("reload failed", ex2, flush=True)
                    break
            link.rpc("input.release", timeout_s=10)
            if "skip" not in info and "error" not in info:
                done[d] += 1
            row = {"n": n} | info
            log.write(json.dumps(row) + "\n")
            log.flush()
            n += 1
            print(json.dumps({k: v for k, v in row.items() if k != "trace"})[:400], flush=True)
        log.close()
        print("done", done, flush=True)
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
            link.rpc("fsmtap.set", all=False)
            link.rpc("time.scale", timeout_s=10, scale=1e-4)        # leave the game frozen (the person, 10-15)
        except Exception:  # noqa: BLE001
            pass
        if rec is not None:
            rec.close()
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
