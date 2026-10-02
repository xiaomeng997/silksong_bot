"""Boss path audit: the planner's predicted boss hurtbox (Forecast.boss_box, the box its attacks are scored against
and the pogo gate checks) against the boss's recorded colliders, k frames ahead, per Control state at the origin.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.boss_path_audit C:/ssbot/data/runs/m2/<run> [--instances 0,1]
        [--episodes 4] [--states "Charge Antic,Charge"] [--json out.json]

Why (2026-10-02, the person watching the live check of main): head-on down spikes on the charge never hit, and from
behind the spike starts too high and ends before the boss arrives. The hit model reproduces the person's pogos with the
boss's LOGGED colliders (tools/pogo_repro: 5 of 5), so what is left is the predicted box: its x along the charge
(timing, anchor, speed profile) and its height (which polygon is moved along the path).

How: each episode's recording is replayed through the oracle backend and the forecaster (oracle view, the playbook's
no-hurtbox states), as the planner policy does; at every `--every`-th frame whose Control state is in --states, the
box predicted for k frames ahead (tk = k / 60 game s, the planner's rollout clock) is compared with the recorded
enabled colliders' bounding box at
  frame base   frame fo + k (what the planner's frame k meets: game time stands still in hit-stop frames, the
               rollout's frames do not);
  game base    the first frame whose game time is >= t(fo) + tk (the model's own accuracy).
Errors along the boss's motion (dir = the recorded box centre's displacement sign over the window): front = dir *
(predicted front edge - recorded front edge), > 0: the prediction is ahead (the boss arrives later than planned);
top = predicted top - recorded top, > 0: predicted taller (a spike planned to meet it is pressed too high). Also the
hittable flag (predicted ok vs recorded colliders enabled) and the share of hit-stop frames (ts 0) in the window.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

KS = (3, 6, 9, 12, 18, 24, 30, 36, 42, 48)
CHARGE = ("Charge Emerge", "Charge Antic", "Charge", "Charge End")


def _box(e) -> tuple | None:
    vs = [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in (e or {}).get("colliders") or ()
          if c.get("enabled")]
    if not vs:
        return None
    v = np.concatenate(vs)
    return float(v[:, 0].min()), float(v[:, 1].min()), float(v[:, 0].max()), float(v[:, 1].max())


def _boss(s):
    return next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)


def _q(v):
    if not v:
        return None
    a = np.asarray(v)
    return [round(float(np.percentile(a, p)), 2) for p in (10, 50, 90)] + [len(a)]


def audit_episode(states: list[dict], fc, want: set[str], every: int, out: dict) -> None:
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.forecast import Forecast
    from ssbot.core.bosses import BOSSES
    fc.reset()
    be = OracleBackend(bosses=[BOSSES[fc.model.boss_type]])
    tg = np.zeros(len(states))
    boxes: list = [None] * len(states)
    frz = np.zeros(len(states), bool)
    for i, s in enumerate(states):
        boxes[i] = _box(_boss(s))
        frz[i] = float(s.get("ts", 1.0) or 0.0) == 0.0
    preds = []
    for i, s in enumerate(states):
        ws = be.feed(s)
        tg[i] = ws.stamp.t_game_s
        fc.update(ws)
        st = fc.tracker.state
        if st not in want or i % every or i + KS[-1] >= len(states):
            continue
        f = Forecast(fc, ws.stamp.t_game_s, 0.8, [], [], True, [], fc.boss)
        tk = np.arange(KS[-1] + 1) / 60.0
        bb, ok = f.boss_box(tk)
        hx = float(s["hero"]["pos"][0])
        ph = f"{fc.tracker.ctx.phase}{'first' if fc.tracker.n_attacks <= 1 else ''}"
        preds.append((i, st, ph, round(ws.stamp.t_game_s - fc.tracker.t_entry, 3) if fc.tracker.t_entry is not None
                      else None, bb, ok, hx))
    for i, st, ph, tau, bb, ok, hx in preds:
        b0 = boxes[i]
        for k in KS:
            for base in ("frame", "game"):
                if base == "frame":
                    j = i + k
                else:
                    j = int(np.searchsorted(tg, tg[i] + k / 60.0 - 1e-6))
                    if j >= len(states):
                        continue
                bj = boxes[j]
                key = (st + "/" + str(ph), base, k)
                o = out.setdefault(key, defaultdict(list))
                o["n"].append(1)
                if not ok[k] or bj is None:
                    o["ok_mismatch"].append(int(bool(ok[k]) != (bj is not None)))
                    continue
                o["ok_mismatch"].append(0)
                p = bb[k]
                c_now = 0.5 * ((b0 or bj)[0] + (b0 or bj)[2])
                c_then = 0.5 * (bj[0] + bj[2])
                d = 1.0 if c_then > c_now + 1e-3 else (-1.0 if c_then < c_now - 1e-3 else 0.0)
                if d != 0.0:
                    pf, af = (p[2], bj[2]) if d > 0 else (p[0], bj[0])
                    o["front"].append(d * (pf - af))
                    # head-on: the hero ahead of the boss in its motion; else behind it (the boss comes from behind)
                    rel = "head_on" if d * (hx - c_now) > 0 else "behind"
                    o[f"front_{rel}"].append(d * (pf - af))
                o["cx"].append(0.5 * (p[0] + p[2]) - c_then)
                o["top"].append(p[3] - bj[3])
                o["bottom"].append(p[1] - bj[1])
                o["width"].append((p[2] - p[0]) - (bj[2] - bj[0]))
                o["frozen"].append(float(frz[i + 1:i + k + 1].mean()) if base == "frame" else 0.0)
                o["tau"].append(tau if tau is not None else np.nan)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instances", default="0")
    ap.add_argument("--episodes", type=int, default=4)
    ap.add_argument("--states", default=",".join(CHARGE))
    ap.add_argument("--every", type=int, default=2)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster
    from ssbot.combat.tactics import load_playbook
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import episode_rows, find_recording
    model = BossModel.load("BellBeast")
    from ssbot.core.worldstate import ORACLE
    fc = Forecaster(model, ORACLE, templates={})
    pb = load_playbook("BellBeast")
    fc.no_hurtbox, fc.shape_from = pb.no_hurtbox, pb.shape_from
    want = set(a.states.split(","))
    out: dict = {}
    n_ep = 0
    for inst in (int(x) for x in a.instances.split(",")):
        for row in episode_rows(a.run, inst)[:a.episodes]:
            if not row.get("recording") or row.get("outcome") == "HARNESS_FAIL":
                continue
            r = RecordingReader(find_recording(a.run, row))
            states = [s for s in r.states(row["f_end"] - row["acts"], row["f_end"])]
            audit_episode(states, fc, want, a.every, out)
            n_ep += 1
    rep = {"episodes": n_ep, "quantiles": "p10 / p50 / p90 / n", "rows": []}
    for (st, base, k), o in sorted(out.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        rep["rows"].append({"state": st, "base": base, "k": k, "n": len(o["n"]),
                            "ok_mismatch": round(float(np.mean(o["ok_mismatch"])), 3) if o["ok_mismatch"] else None,
                            **{m: _q(o[m]) for m in ("front", "front_head_on", "front_behind", "top", "bottom",
                                                     "width", "frozen")}})
    for x in rep["rows"]:
        print(json.dumps(x))
    if a.json:
        a.json.write_text(json.dumps(rep, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
