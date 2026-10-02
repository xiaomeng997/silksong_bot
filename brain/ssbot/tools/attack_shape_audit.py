"""Attack shape audit: does the planner's down-attack shape predict the game's down-attack hits on the boss, from the
recorded hero and boss alone (no prediction involved)?

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.attack_shape_audit C:/ssbot/data/runs/m2/<run> [--instances 0,1]
        [--episodes 10] [--json out.json]

Why (2026-10-02): the person saw head-on down spikes on the charge never hit and the spike "start too high". The plan
against the recording (tools/spike_audit) showed the planned hero path and the predicted boss box right, and the
planner's DOWN rectangle meeting the recorded boss collider in spikes that did not hit. The rectangle is the bounding
box of the clash polygon (crests.json P17); the damage collider (Attacks/Default/DownSlash, damager 0) is a diagonal
sliver from the hero's back-top to a forward-low tip, and the rectangle's back-low corner covers 0.5-1 u where it has
nothing.

For every down spike (hero clip DownSpike after DownSpike Antic) of the episodes: per frame from the spike's first frame
to 12 frames on, whether each shape, placed at the recorded hero hurtbox centre with her facing, meets the boss's
recorded enabled colliders (planner._rect_meets_polys / _poly_meets_polys), and the frame of the game's DownSlash hit
event on the boss. Confusion of "some frame of the spike meets" (frames while the hero is in DownSpike) against "a hit
event", per shape, and the first contact frame minus the hit frame.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instances", default="0")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.combat import planner as pl
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import episode_rows, find_recording

    def anim(s):
        return str(((s.get("hero") or {}).get("anim") or {}).get("clip", ""))

    def boss(s):
        b = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
        vs = [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in (b or {}).get("colliders") or ()
              if c.get("enabled")]
        if not vs:
            return None
        return np.concatenate(vs), np.cumsum([0] + [len(q) for q in vs]).astype(np.int64)

    conf = {"rect": Counter(), "poly": Counter()}
    lead = {"rect": [], "poly": []}
    n = 0
    for inst in (int(x) for x in a.instances.split(",")):
        for row in episode_rows(a.run, inst)[:a.episodes]:
            if not row.get("recording") or row.get("outcome") == "HARNESS_FAIL":
                continue
            S = list(RecordingReader(find_recording(a.run, row)).states(row["f_end"] - row["acts"], row["f_end"]))
            for i in range(1, len(S)):
                if not ("DownSpike" in anim(S[i]) and "Antic" not in anim(S[i]) and "Antic" in anim(S[i - 1])):
                    continue
                n += 1
                hit_k = next((k for k in range(0, 14) if i + k < len(S) for e in S[i + k].get("ev") or ()
                              if e.get("k") == "hit" and str((e.get("d") or {}).get("src", "")).startswith("Down")),
                             None)
                first = {"rect": None, "poly": None}
                for k in range(0, 12):
                    if i + k >= len(S):
                        break
                    s = S[i + k]
                    over = anim(s) != "DownSpike"   # recovery, or the bounce of a hit in this very frame (tested)
                    bp = boss(s)
                    if bp is None:
                        if over:
                            break
                        continue
                    hb = s["hero"]["box"]
                    cx, cy = 0.5 * (hb[0] + hb[2]), 0.5 * (hb[1] + hb[3])
                    face = 1 if (s["hero"].get("facing") or 1) >= 0 else -1
                    g = pl.DOWN
                    x0, x1 = (cx + g[0], cx + g[1]) if face > 0 else (cx - g[1], cx - g[0])
                    if first["rect"] is None and pl._rect_meets_polys(x0, cy + g[2], x1, cy + g[3], bp[0], bp[1],
                                                                      0.0, 0.0):
                        first["rect"] = k
                    dp = np.ascontiguousarray(np.c_[cx + face * pl.DOWN_POLY[:, 0], cy + pl.DOWN_POLY[:, 1]])
                    if first["poly"] is None and pl._poly_meets_polys(dp, bp[0], bp[1], 0.0, 0.0):
                        first["poly"] = k
                    if over:
                        break
                for m in ("rect", "poly"):
                    pred, act = first[m] is not None, hit_k is not None
                    conf[m][("TP" if act else "FP") if pred else ("FN" if act else "TN")] += 1
                    if pred and act:
                        lead[m].append(first[m] - hit_k)
    out = {"spikes": n, "confusion": {m: dict(c) for m, c in conf.items()},
           "contact_minus_hit_frames": {m: dict(Counter(v)) for m, v in lead.items()}}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
