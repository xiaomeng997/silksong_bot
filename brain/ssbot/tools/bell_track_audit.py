"""Bell track audit (task V): the vision view's bell paths (combat.bell_track: a drop bell's column, drop time and
bounce side, an attack bell's launch time, x and side, from the bell's detections) against the recorded bells, on the
simulated final path's noise.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.bell_track_audit C:/ssbot/data/runs/m2/<run> [--instances 0,1]
        [--episodes 4] [--noise-seed 1] [--kind drop|atk] [--json out.json]

Per recorded fight: OracleBackend -> ObservabilityFilter (dust cues) -> SimpleNoise (seeded) -> the vision view's
Forecaster (its DropBellTracks), every frame. At every frame with an estimate for a bell: the predicted centre at tk
ahead (0 .. 0.8 s every 0.05 s) on each branch the estimate keeps open, against the bell's recorded transform at the
first frame whose game time reaches t + tk (while the recorded bell is still in a state the registry lists, i.e.
not put away). Reported: the centre error of the nearest branch (min over the forecaster's time slack DET_SLACK_S,
as the support uses it) by tk, the share of frames beyond the contact radius margin (skin), the time from the first
floor contact to the side decision, and decisions for the wrong side (must be 0: a wrong side drops the real branch
from the support).
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

TKS = np.round(np.arange(0, 0.81, 0.05), 3)


def audit(states: list[dict], seed: int, out: dict) -> None:
    from ssbot.backends.noise_simple import SimpleNoise
    from ssbot.backends.observability import ObservabilityFilter
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.bell_track import DROP_BELL, SKIN_Z
    from ssbot.combat.forecast import DET_SLACK_S, DET_SKIN_U
    from ssbot.combat.pogo_targets import load_registry, simulate
    from ssbot.combat.bell_track import DropBellTracks
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.train.planner_policy import DUST_TELL
    spec = next(s for s in load_registry() if s.prefix == DROP_BELL)
    be = OracleBackend(bosses=[BELL_BEAST])
    filt = ObservabilityFilter(bosses=[BELL_BEAST], tells=DUST_TELL)
    noise = SimpleNoise(seed=seed)
    tracks = DropBellTracks(spec)
    tg = np.zeros(len(states))
    truth: list[dict] = []             # per frame: iid -> (x, y, state)
    for i, s in enumerate(states):
        ws = noise.apply(filt.apply(be.feed(s)))
        tg[i] = ws.stamp.t_game_s
        tr = {}
        for e in s.get("ents") or ():
            if str(e.get("type_key", "")).startswith(DROP_BELL) and e.get("fsms"):
                st = e["fsms"][0].get("state")
                if st in spec.states or st == "Air":
                    tr[int(e["iid"])] = (float(e["pos"][0]), float(e["pos"][1]), st)
        truth.append(tr)
        tracks.update(ws, tg[i])
        for iid in list(tracks.obs):
            est = tracks.estimate(iid)
            if est is None:
                if iid in tr:
                    out["no_estimate"].append(1)
                continue
            if iid in tr:
                out["no_estimate"].append(0)
            if est.side and tr.get(iid) is not None:
                key = (iid, round(est.t_drop, 1))
                if key not in out["_sided"]:
                    out["_sided"][key] = True
                    out["side_latency"].append(tg[i] - est.t_contact)
            sides = (est.side,) if est.side else (1, -1)
            out["_pending"].append((i, iid, est, sides, tg[i] - est.t_drop))
    # resolve predictions against the recorded future
    for i, iid, est, sides, t0 in out.pop("_pending"):
        for tk in TKS:
            j = int(np.searchsorted(tg, tg[i] + tk - 1e-6))
            if j >= len(states) or iid not in truth[j]:
                continue
            ax, ay, st = truth[j][iid]
            if ay < spec.ground_y - spec.r:
                continue                    # sunk below the floor (Submerge): nothing on the floor can meet it
            best = np.inf
            for sd in sides:
                for dt in DET_SLACK_S:
                    cx, cy, ok = simulate(spec, est.x, tracks.y0, tracks.vx0, tracks.vy0, 0, None,
                                          np.array([max(t0 + tk + dt, 0.0)]), side=sd)
                    best = min(best, float(np.hypot(cx[0] - ax, cy[0] - ay)))
            out[f"err_{tk:.2f}"].append(best)
            if best > 1.0:
                out["worst"].append((round(best, 2), float(tk), iid, round(est.x, 2), round(est.t_drop, 3),
                                     est.side, est.n, st, round(ax, 2), round(ay, 2), round(float(tg[i]), 3)))
            over = best > DET_SKIN_U + SKIN_Z * est.sx
            out[f"over_{tk:.2f}"].append(over)
            if over:
                out["over_by"].append(f"{st}/{'open' if len(sides) > 1 else 'sided'}/n{min(est.n, 5)}")
            if est.side and tg[j] > est.t_contact + 0.1 and st in ("Bounce Air", "Submerge"):
                true_side = 1 if ax > est.x else -1
                out["wrong_side"].append(int(true_side != est.side))
    out["_pending"] = []


def audit_atk(states: list[dict], seed: int, out: dict) -> None:
    """Attack bells (bell_track.AtkBellTracks): the same centre errors on the launch paths, plus the collider's end
    (a recorded bell still on after the estimate's end must not happen), wrong sides, and how often a burst's two
    bells are both on exact paths (the forecaster then drops the attack-bell unions) with the pair's middle against
    the recorded burst transform."""
    from ssbot.backends.noise_simple import SimpleNoise
    from ssbot.backends.observability import ObservabilityFilter
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.bell_track import ATK_BELL, SKIN_Z, AtkBellTracks
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import DET_SKIN_U, DET_SLACK_S, BossTracker
    from ssbot.combat.pogo_targets import load_registry, simulate
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.core.worldstate import VISION_EQUIVALENT
    from ssbot.train.planner_policy import DUST_TELL
    spec = next(s for s in load_registry() if s.prefix == ATK_BELL)
    be = OracleBackend(bosses=[BELL_BEAST])
    filt = ObservabilityFilter(bosses=[BELL_BEAST], tells=DUST_TELL)
    noise = SimpleNoise(seed=seed)
    tracks = AtkBellTracks(spec)
    bt = BossTracker(BossModel.load(), VISION_EQUIVALENT)
    tg = np.zeros(len(states))
    truth: list[dict] = []
    boss_x = np.full(len(states), np.nan)
    for i, s in enumerate(states):
        ws = noise.apply(filt.apply(be.feed(s)))
        tg[i] = ws.stamp.t_game_s
        bt.update(ws)
        tr = {}
        for e in s.get("ents") or ():
            tk_ = str(e.get("type_key", ""))
            if tk_.startswith(ATK_BELL) and e.get("fsms") and e["fsms"][0].get("state") in spec.states:
                tr[int(e["iid"])] = (float(e["pos"][0]), float(e["pos"][1]), e["fsms"][0]["state"],
                                     float((e.get("vel") or (0.0, 0.0))[0]))
            elif tk_ == "Bone Beast":
                boss_x[i] = float(e["pos"][0])
        truth.append(tr)
        ax = bt.last_anchor.x if bt.last_family == "BB_BURST" and bt.last_anchor is not None else None
        tracks.update(ws, tg[i], ax)
        for est in tracks.estimates():
            if est.iid in tr:
                out["paired"].append(int(est.pair))
                out["sided"].append(int(est.side != 0))
                tvx = tr[est.iid][3]
                if est.side and abs(tvx) > 0.5:
                    out["wrong_side"].append(int((tvx > 0) != (est.side > 0)))
            out["_pending"].append((i, est.iid, est.side, tracks.path_args(est, est.side or 1),
                                    tracks.path_args(est, -(est.side or 1)), tg[i] - est.t_launch,
                                    est.t_end, est.sx, est.side))
        for iid, v in tr.items():
            out["no_estimate"].append(int(not any(e.iid == iid for e in tracks.estimates())))
    for i, iid, side, args, args2, t0, t_end, sx, sd0 in out.pop("_pending"):
        branches = [args] if side else [args, args2]
        for tk in TKS:
            j = int(np.searchsorted(tg, tg[i] + tk - 1e-6))
            if j >= len(states):
                continue
            if iid not in truth[j]:
                continue
            ax_, ay, st, _ = truth[j][iid]
            if tg[j] > t_end:
                if st != "Launch":           # (a Launch is the same object's next burst)
                    out["alive_after_end"].append((round(float(tg[j] - t_end), 3), st))
                continue
            best = np.inf
            for x0, y0, vx0, vy0 in branches:
                for dt in DET_SLACK_S:
                    cx, cy, ok = simulate(spec, x0, y0, vx0, vy0, 0, None, np.array([max(t0 + tk + dt, 0.0)]))
                    best = min(best, float(np.hypot(cx[0] - ax_, cy[0] - ay)))
            out[f"err_{tk:.2f}"].append(best)
            over = best > DET_SKIN_U + SKIN_Z * sx
            out[f"over_{tk:.2f}"].append(over)
            if over:
                out["over_by"].append(f"{st}/{'open' if not side else 'sided'}")
            if best > 1.0:
                out["worst"].append((round(best, 2), float(tk), iid, side, st, round(ax_, 2), round(ay, 2),
                                     round(float(tg[i]), 3)))
    out["_pending"] = []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instances", default="0")
    ap.add_argument("--episodes", type=int, default=4)
    ap.add_argument("--noise-seed", type=int, default=1)
    ap.add_argument("--kind", choices=("drop", "atk"), default="drop")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import episode_rows, find_recording
    out: dict = defaultdict(list)
    out["_sided"] = {}
    out["_pending"] = []
    n = 0
    for inst in (int(x) for x in a.instances.split(",")):
        for ep, row in enumerate(episode_rows(a.run, inst)[:a.episodes]):
            if not row.get("recording") or row.get("outcome") == "HARNESS_FAIL":
                continue
            r = RecordingReader(find_recording(a.run, row))
            states = list(r.states(row["f_end"] - row["acts"], row["f_end"]))
            (audit if a.kind == "drop" else audit_atk)(states, a.noise_seed + 1000 * inst + ep, out)
            n += 1
            print(f"i{inst} ep{ep}: {len(out['err_0.00'])} estimates", flush=True)
    rep = {"episodes": n, "noise_seed": a.noise_seed}
    q = lambda v: [round(float(np.percentile(v, p)), 3) for p in (50, 90, 99, 99.9)] + [round(float(np.max(v)), 3),
                                                                                         len(v)]  # noqa: E731
    rep["centre_err_p50_p90_p99_p999_max_n"] = {f"{tk:.2f}": q(out[f"err_{tk:.2f}"]) for tk in TKS
                                                 if out[f"err_{tk:.2f}"]}
    rep["over_skin_share"] = {f"{tk:.2f}": round(float(np.mean(out[f"over_{tk:.2f}"])), 4) for tk in TKS
                              if out[f"over_{tk:.2f}"]}
    from collections import Counter
    rep["over_skin_by_state"] = dict(Counter(out["over_by"]).most_common(20))
    rep["worst"] = sorted(out["worst"], reverse=True)[:12] + out["worst"][:12]
    rep["side_latency_s"] = q(out["side_latency"]) if out["side_latency"] else None
    rep["wrong_side"] = [int(np.sum(out["wrong_side"])), len(out["wrong_side"])]
    rep["no_estimate_share_while_falling"] = round(float(np.mean(out["no_estimate"])), 4) if out["no_estimate"] \
        else None
    if a.kind == "atk":
        rep["paired_share"] = round(float(np.mean(out["paired"])), 4) if out["paired"] else None
        rep["sided_share"] = round(float(np.mean(out["sided"])), 4) if out["sided"] else None
        rep["alive_after_end"] = [len(out["alive_after_end"]), sorted(out["alive_after_end"])[-5:]]
    print(json.dumps(rep, indent=1))
    if a.json:
        a.json.write_text(json.dumps(rep, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
