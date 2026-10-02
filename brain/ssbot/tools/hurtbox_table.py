"""The boss's hittable box per observable phase, for the vision-equivalent view's attack scoring (M2 attack audit).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.hurtbox_table C:/ssbot/data/runs/m2/<oracle run> [--max-frames 200000]

Vision sees the boss's sprite, not its colliders; the planner scored nail hits against the render box, which is not
the hurtbox (stage C run 20261002_083740: 23 % of side slashes hit, 0 % of up-slashes, against 81 % / 59 % in the
oracle view). This builds, from oracle recordings, the bounding box of the boss's enabled colliders relative to its
position (x mirrored when the sprite is flipped) per observable phase (core.bosses BELL_BEAST.phases) and per 0.1 s
of time in the phase, as median and 10th / 90th percentiles, to knowledge/1.0.30000/enemies/BellBeast_hurtbox.json.
With a single enabled collider (attacks: PolyCollider, LeapCollider) the median polygon too ("poly", vertex-wise):
in a leap the collider's box covers corners the 9-vertex shape does not, and side slashes under a leap scored as
hits that never landed (stage C run 20261002_093052: 332 predicted, 0 hit). The vision view places the polygon, else
the median box, at the observed position (Forecast.body_polys).
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "BellBeast_hurtbox.json"
BIN_S = 0.1


def build(runs: list[Path], max_frames: int) -> dict:
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.record.recorder import RecordingReader
    phases = dict(BELL_BEAST.phases)
    acc = defaultdict(list)
    polys = defaultdict(list)
    n = 0
    prev_state, t_in = None, 0
    for run in runs:
        for rec in sorted(run.glob("rec/*/*/i*_*")):
            r = RecordingReader(rec)
            for s in r.states():
                b = next((e for e in s.get("ents") or () if e.get("type_key") == BELL_BEAST.type_key), None)
                if b is None:
                    prev_state = None
                    continue
                st = (b.get("fsms") or [{}])[0].get("state")
                ph = phases.get(st)
                # time in the OBSERVABLE phase (what the vision view counts), not in the FSM state: a leap phase spans
                # Emerge Antic L, Leap Out and Descending, and binning by state time put Descending's high polygon at
                # Leap Out's early times and back (stage C run 20261002_102538: side slashes under a leap, 153
                # predicted hits, 0 landed)
                if ph != prev_state:
                    prev_state, t_in = ph, 0
                else:
                    t_in += 1
                vs = [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in b.get("colliders") or ()
                      if c.get("enabled")]
                if ph is None or not vs or b.get("render_aabb") is None:
                    continue
                v = np.concatenate(vs)
                px, py = b["pos"][0], b["pos"][1]
                x0, x1 = v[:, 0].min() - px, v[:, 0].max() - px
                if b.get("flipX"):
                    x0, x1 = -x1, -x0
                key = (ph, min(int(t_in / 60 / BIN_S), 30))
                acc[key].append((x0, v[:, 1].min() - py, x1, v[:, 1].max() - py))
                if len(vs) == 1:      # the polygon itself, relative and unflipped: its box alone over-credits
                    q = vs[0] - (px, py)
                    if b.get("flipX"):
                        q = q * (-1.0, 1.0)
                    polys[key].append(q)
                n += 1
                if n >= max_frames:
                    break
            if n >= max_frames:
                break
    out = {"bin_s": BIN_S, "frames": n, "source": [str(r) for r in runs], "phases": {}}
    for (ph, b), boxes in sorted(acc.items()):
        a = np.array(boxes)
        out["phases"].setdefault(ph, {})[str(b)] = {
            "n": len(a), "median": np.round(np.median(a, axis=0), 3).tolist(),
            "p10": np.round(np.percentile(a, 10, axis=0), 3).tolist(),
            "p90": np.round(np.percentile(a, 90, axis=0), 3).tolist()}
        qs = polys.get((ph, b)) or []
        if qs:
            nv = Counter(len(q) for q in qs).most_common(1)[0][0]
            same = np.array([q for q in qs if len(q) == nv])
            out["phases"][ph][str(b)]["poly"] = np.round(np.median(same, axis=0), 3).tolist()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--max-frames", type=int, default=200000)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    out = build(a.runs, a.max_frames)
    a.out.write_text(json.dumps(out, indent=1), "utf-8")
    print(f"{out['frames']} frames, phases {sorted(out['phases'])} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
