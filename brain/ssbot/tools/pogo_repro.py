"""Ground truth for the pogo model: the person's pogos off the Bell Beast in a recorded session, replayed through the
kinematics and the planner's hit model with the person's own inputs and the boss's logged path.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.pogo_repro C:/ssbot/data/human/20260930_210337 [--frames 64275 68397]

A pogo: a DownSpike clip starting (the press) followed within 25 frames by a boss hp drop and the hero rising after
it (the bounce). For each: head-on (the boss moving towards the hero) or from behind;
whether the DOWN box (planner.DOWN, from the hero's recorded centre) meets the boss's enabled colliders at the hp-drop
frame (the geometry check); and the replay: the kinematics from the press (StateTracker state 1 frame before, the
person's masks as latched), scored by planner._attacks_of against the recorded boss box per frame (the polygon of
the press frame moved with it), in the nominal lane and in every timing lane.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("--frames", type=int, nargs=2, default=(64275, 68397))
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.combat import planner as pl
    from ssbot.knowledge import kinematics as kin
    from ssbot.tools.raw_session import states as raw_states
    params = kin.HeroParams.load()
    S = [s for s in raw_states(a.session) if a.frames[0] - 120 <= s.get("f", -1) <= a.frames[1] + 60]
    by_f = {s["f"]: (i, s) for i, s in enumerate(S)}
    D, A = kin.B_DOWN, kin.B_ATTACK

    def boss_of(s):
        return next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)

    def polys(e):
        return [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in (e or {}).get("colliders") or ()
                if c.get("enabled")]

    def spiking(s):
        return "DownSpike" in str((s.get("hero") or {}).get("anim"))

    found = []
    for i, s in enumerate(S):
        # the press: the first frame of a DownSpike clip (the session's cstate is packed bits, the input mask may
        # have down before attack); the hit: a boss hp drop within 25 frames; the bounce: the hero rising after it
        if not (spiking(s) and i and not spiking(S[i - 1])) or not a.frames[0] <= s["f"] <= a.frames[1]:
            continue
        hp0 = (boss_of(s) or {}).get("hp")
        drop = bounce = None
        for j in range(i + 1, min(len(S), i + 26)):
            b = boss_of(S[j])
            if b and hp0 is not None and b.get("hp") is not None and b["hp"] < hp0:
                drop = j
                break
        if drop is None:
            continue
        y = [S[min(k, len(S) - 1)]["hero"]["pos"][1] for k in range(drop, drop + 10)]
        if max(y) - y[0] > 0.3:
            bounce = drop + int(np.argmax(y))
        if bounce is None:
            continue
        b = boss_of(s)
        st = (b.get("fsms") or [{}])[0].get("state")
        hx = s["hero"]["pos"][0]
        bvx = (b.get("vel") or [0, 0])[0]
        head_on = bool(bvx and np.sign(bvx) == np.sign(hx - b["pos"][0]))
        found.append({"f": s["f"], "i": i, "drop": drop, "bounce": bounce, "state": st, "head_on": head_on})
    trk = kin.StateTracker(params, kin.Terrain2D.empty())
    k_done = 0
    res = []
    win = pl.WINDOWS["v2"]
    for p in found:
        i = p["i"]
        while k_done < i:
            trk.push(S[k_done])
            k_done += 1
        try:
            start = trk.state().copy()
        except Exception:
            continue
        T = 40
        lat = np.array([((S[min(i + k, len(S) - 1)].get("input") or {}).get("mask", 0) or 0) for k in range(T)],
                       np.int64)[None]
        bb = np.zeros((T + 1, 4))
        okb = np.zeros(T + 1, np.bool_)
        for k in range(T + 1):
            pk = polys(boss_of(S[min(i + k, len(S) - 1)]))
            if pk:
                v = np.concatenate(pk)
                bb[k] = (v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max())
                okb[k] = True
        p0 = polys(boss_of(S[i]))
        if not p0:
            continue
        flat = np.concatenate(p0)
        starts = np.cumsum([0] + [len(q) for q in p0]).astype(np.int64)
        face = 1 if (S[i]["hero"].get("facing") or 1) >= 0 else -1
        r = kin.rollout(start, lat, params, None, variants="bounds", lanes=True)
        lanes_hit = []
        for v in range(r.var_box.shape[1]):
            lst = pl._attacks_of(np.ascontiguousarray(r.var_box[0, v]), np.ascontiguousarray(r.var_flags[0, v]),
                                 np.ascontiguousarray(r.var_mode[0, v]), np.ascontiguousarray(lat[0]), face, bb, okb,
                                 flat, starts, np.array([bb[0, 0], bb[0, 1]]), win)
            lanes_hit.append(next((j for kd, _, j in lst if kd == 3 and j >= 0), -1))
        # geometry at the hp drop: the DOWN box from the recorded hero centre against the recorded colliders
        sd = S[p["drop"]]
        hb = sd["hero"]["box"]
        cx, cy = 0.5 * (hb[0] + hb[2]), 0.5 * (hb[1] + hb[3])
        g = pl.DOWN
        geo = []
        for fc in (face, -face):
            x0, x1 = (cx + g[0], cx + g[1]) if fc > 0 else (cx - g[1], cx - g[0])
            pd = polys(boss_of(sd))
            geo.append(bool(pd) and bool(pl._rect_meets_polys(x0, cy + g[2], x1, cy + g[3], np.concatenate(pd),
                                                              np.cumsum([0] + [len(q) for q in pd]).astype(np.int64),
                                                              0.0, 0.0)))
        ds_frames = int((r.var_mode[0, 0] == kin.M_DS_SPIKE).sum())
        res.append(dict(p, f_drop=S[p["drop"]]["f"], nominal_hit=lanes_hit[0], lanes_hit=sum(x >= 0 for x in lanes_hit),
                        lanes=len(lanes_hit), geometry_hit_at_drop=geo[0], geometry_either_facing=any(geo),
                        model_spike_frames=ds_frames))
    out = {"pogos": len(found), "replayed": len(res),
           "nominal_reproduced": sum(1 for x in res if x["nominal_hit"] >= 0),
           "all_lanes_reproduced": sum(1 for x in res if x["lanes_hit"] == x["lanes"]),
           "geometry_at_drop": sum(1 for x in res if x["geometry_hit_at_drop"]),
           "head_on": sum(1 for x in res if x["head_on"]), "cases": res}
    print(json.dumps({k: v for k, v in out.items() if k != "cases"}, indent=1))
    for x in res[:12]:
        print({k: x[k] for k in ("f", "f_drop", "state", "head_on", "nominal_hit", "lanes_hit", "geometry_hit_at_drop",
                                 "geometry_either_facing", "model_spike_frames")})
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
