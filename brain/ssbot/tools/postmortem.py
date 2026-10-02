"""Postmortem of planner episodes (M2 W7; DESIGN §3.10): for every hero hit, WOULD_DIE and FORCED_RISK stretch of an
eval episode, what the forecast's support said at decision time, the chosen candidate and the best alternatives,
and whether the hero's actual path stayed inside the predicted lanes' hull.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.postmortem C:/ssbot/data/runs/m2/<run> [--instance 0] [--episode 3]
        [--lag 3] [--png DIR] [--forced]

How: the episode's recording (combat_run records every episode) is replayed through a fresh PlannerPolicy of the same
view (open loop: the recorded STATEs drive it; the planner is deterministic given them, so its decisions match the
live ones unless the live tick ran late), up to each event. At the decision frame `lag` frames before the event it
prints the forecast roots and placements, whether the hero's recorded box at the event was inside the support (an
unpredicted hit if not), the chosen plan with S / V / P / J and the alternatives, and whether the recorded hero boxes
of the next frames stayed inside the chosen plan's lanes' hull (a kinematics miss if not). --png draws, per event,
five time slices 0-0.8 s after the decision: support cells (grey), the chosen plan's hull (blue), the recorded hero box
(green, red when in contact) and the boss's body (orange).
The decision log of the run (decisions_i<N>.jsonl) gives the live choices next to the replayed ones.
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np


def episode_rows(run: Path, instance: int) -> list[dict]:
    p = run / f"attempts_i{instance}.jsonl"
    return [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]


def find_recording(run: Path, row: dict) -> Path:
    rec = Path(row["recording"])
    if not rec.is_dir():
        found = list(run.glob(f"rec/*/*/{rec.name}"))
        rec = found[0] if found else rec
    return rec


def events_of(row: dict, forced: bool) -> list[tuple[int, str]]:
    pol = row.get("policy") or {}
    ev = [(f, "hit") for f in pol.get("hits_taken") or ()]
    if row.get("first_lethal_f"):
        ev.append((row["first_lethal_f"], "would_die"))
    if forced:
        ff = pol.get("forced_first") or []
        starts = [f for i, f in enumerate(ff) if i == 0 or ff[i - 1] != f - 1]
        ev += [(f, "forced_risk") for f in starts]
    return sorted(set(ev))


def render(path: Path, fcast, res, boxes_actual: list, boss_boxes: list, title: str) -> None:
    import cv2
    x0, x1, y0, y1, s = 67.0, 104.0, 0.0, 16.0, 16
    W, H = int((x1 - x0) * s), int((y1 - y0) * s)
    panels = []
    xs = np.arange(x0, x1, 0.25) + 0.125
    ys = np.arange(y0, y1, 0.25) + 0.125
    gx, gy = np.meshgrid(xs, ys)
    for k in (0, 12, 24, 36, 48):
        img = np.full((H, W, 3), 255, np.uint8)
        t = k * (1 / 60)
        occ = fcast.occupied(gx.reshape(-1, 1), gy.reshape(-1, 1), np.array([t])).reshape(gx.shape)
        for (iy, ix) in zip(*np.nonzero(occ)):
            px, py = int((xs[ix] - 0.125 - x0) * s), int(H - (ys[iy] + 0.125 - y0) * s)
            cv2.rectangle(img, (px, py), (px + 4, py + 4), (190, 190, 190), -1)

        def rect(b, col, th=2):
            p0 = (int((b[0] - x0) * s), int(H - (b[3] - y0) * s))
            p1 = (int((b[2] - x0) * s), int(H - (b[1] - y0) * s))
            cv2.rectangle(img, p0, p1, col, th)
        if res is not None and res.hull is not None and k < len(res.hull):
            rect(res.hull[k], (255, 80, 0))
        if k < len(boss_boxes) and boss_boxes[k] is not None:
            rect(boss_boxes[k], (0, 140, 255))
        if k < len(boxes_actual) and boxes_actual[k] is not None:
            b = boxes_actual[k]
            c = fcast.occupied(np.array([[0.5 * (b[0] + b[2])]]), np.array([[0.5 * (b[1] + b[3])]]),
                               np.array([t]))[0, 0]
            rect(b, (0, 0, 220) if c else (0, 170, 0))
        cv2.putText(img, f"t+{t:.2f}s", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        panels.append(img)
    out = np.vstack(panels)
    cv2.putText(out, title[:110], (6, out.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.imwrite(str(path), out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episode", type=int, default=None)
    ap.add_argument("--lag", type=int, default=3)
    ap.add_argument("--png", type=Path, default=None)
    ap.add_argument("--forced", action="store_true", help="also every FORCED_RISK stretch")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)

    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.encounters import BELL_BEAST
    from ssbot.train.planner_policy import PlannerPolicy

    rows = episode_rows(a.run, a.instance)
    view = (rows[0].get("policy") or {}).get("view", "oracle") if rows else "oracle"
    pol = PlannerPolicy(view=view, threads=8)
    report = []
    if a.png:
        a.png.mkdir(parents=True, exist_ok=True)
    for ep, row in enumerate(rows):
        if a.episode is not None and ep != a.episode:
            continue
        evs = events_of(row, a.forced)
        if not evs or not row.get("recording"):
            continue
        r = RecordingReader(find_recording(a.run, row))
        for _, m in r.terrain():
            if m.get("scene_raw") == BELL_BEAST.scene:
                pol.terrain = Terrain2D.from_message(m, pol.params.scene(BELL_BEAST.scene))

        class Tap:
            wake_frame = row.get("f_wake")
        start = row["f_end"] - row["acts"]
        pol.reset(random.Random(row["seed"]), BELL_BEAST)     # run_episode seeds the policy the same way
        targets = {f - a.lag: (f, kind) for f, kind in evs}
        states = list(r.states(start, row["f_end"]))
        by_f = {s["f"]: s for s in states}
        snaps = {}
        for s in states:
            pol.act(s, Tap)
            if s["f"] in targets and pol.forecasts:
                fo, fcast, t_o = pol.forecasts[-1]
                snaps[s["f"]] = (fo, fcast, t_o, pol.planner_last, dict(pol.ring[-1]) if pol.ring else {})
        for fd, (fe, kind) in sorted(targets.items()):
            if fd not in snaps:
                continue
            fo, fcast, t_o, res, rec = snaps[fd]
            boxes, boss, inside = [], [], []
            for k in range(0, 49):
                s = by_f.get(fo + k)
                b = ((s or {}).get("hero") or {}).get("box")
                boxes.append(tuple(b[:4]) if b else None)
                bb = next((e for e in (s or {}).get("ents") or () if e.get("type_key") == BELL_BEAST.boss_type
                           and e.get("colliders")), None)
                if bb:
                    v = np.array(bb["colliders"][0]["verts_world"]).reshape(-1, 2)
                    boss.append((v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max()))
                else:
                    boss.append(None)
                if b and res is not None and res.hull is not None and k < len(res.hull):
                    h = res.hull[k]
                    inside.append(bool(b[0] >= h[0] - 0.02 and b[2] <= h[2] + 0.02 and b[1] >= h[1] - 0.02
                                       and b[3] <= h[3] + 0.02))
            se = by_f.get(fe)
            be = ((se or {}).get("hero") or {}).get("box")
            te = None
            if se is not None and "_t" in se:
                te = se["_t"] - t_o
            covered = None
            if be and te is not None:
                covered = bool(fcast.occupied(np.array([[0.5 * (be[0] + be[2])]]),
                                              np.array([[0.5 * (be[1] + be[3])]]), np.array([te]))[0, 0])
            item = {"episode": ep, "event": kind, "frame": fe, "decision_frame": fo, "outcome": row["outcome"],
                    "boss_state": rec.get("boss_state"), "roots": rec.get("roots"), "n_place": len(fcast.placements),
                    "mode": rec.get("mode"), "stance": rec.get("stance"), "hero": rec.get("hero"),
                    "event_box_in_support": covered,
                    "plan": None if res is None else res.name, "S": None if res is None else res.S,
                    "V": None if res is None else res.V, "P": None if res is None else round(res.P, 3),
                    "J": None if res is None else round(res.J, 2), "n_safe": None if res is None else res.n_safe,
                    "alternatives": None if res is None else res.alternatives,
                    "actual_in_hull_frames": f"{sum(inside)}/{len(inside)}",
                    "first_out_of_hull": next((k for k, v in enumerate(inside) if not v), None),
                    "placements": [(p.key.split('/', 1)[1], round(p.t_ref, 3), None if p.anchor is None else
                                    [round(p.anchor[0], 2), round(p.anchor[1], 2)], round(p.t_on, 2),
                                    round(p.t_off, 2)) for p in fcast.placements][:24]}
            report.append(item)
            print(json.dumps(item))
            if a.png:
                title = f"ep{ep} {kind} f{fe} plan {item['plan']} S{item['S']} in-support {covered}"
                render(a.png / f"ep{ep}_{kind}_{fe}.png", fcast, res, boxes, boss, title)
    if a.json:
        a.json.write_text(json.dumps(report, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
