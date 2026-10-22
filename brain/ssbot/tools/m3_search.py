"""Map v2 stage M3: the search's measurements and the acceptance suite (docs/plans/forum_map_v2.md section 0, 1 L3,
1b, section 2 M3; forum.md section 94). Offline only: the bot does not import this or ssbot.map2.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m3_search margins --set fit|held [--jobs 6]
        # IN-MOVE margins (1b.2: per move and frame offset): from starts INSIDE a move (its antic already seen), the
        # actual damage area of that move covered by the realized branch's shapes grown by m, per look-ahead k
        # -> map2/m3/margins_inmove_<set>.json (the fit set's table goes into clapper_m2.json 'margins_inmove')
    ../scripts/uv.cmd run python -m ssbot.tools.m3_search situations      # the acceptance situations -> m3/sits.pkl
    ../scripts/uv.cmd run python -m ssbot.tools.m3_search run --lib none|full [--jobs 6]
    ../scripts/uv.cmd run python -m ssbot.tools.m3_search report
    ../scripts/uv.cmd run python -m ssbot.tools.m3_search horizon --set held [--jobs 6]
        # the needed horizon: for HP losses in the recordings, the frames before the hit at which the last safe exit
        # (an envelope pass in the realized branch's danger) vanished

Frames are game frames (a hit-stop freeze is not a frame); u world units, centre to centre unless a box edge is named.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.map2 import clapper as cm
from ssbot.tools.m2_clapper import DATA as M2DATA, idle_priority
from ssbot.tools import m2_validate as mv

OUT = Path(r"C:\ssbot\data\m2_play\map2\m3")
MOVE_START = {"Slam Antic": "slam", "Spell Antic": "cast", "Jump Antic": "jump", "Cast Slam Antic": "jcast",
              "Evade Scuttle": "evade"}
IM_STARTS = (1, 3, 6, 10, 15, 20, 30, 40)
IM_KS = (0, 3, 6, 9, 12, 18, 24, 30, 36, 45, 60, 75, 90)


# ---- in-move margins ---------------------------------------------------------------------------------------------

def _inmove_episode(path: str) -> dict:
    with open(path, "rb") as fh:
        tr = pickle.load(fh)
    K = cm.Know.load()
    E = mv.Episode(tr)
    acts = mv.actual_decisions(E)
    mem_at = mv._memories(E)
    R = defaultdict(list)
    starts = []
    for iid in E.iids:
        for (g, a, b, f) in E.trans[iid]:
            if b in MOVE_START:
                # the move ends at its next Idle entry
                end = next((g2 for (g2, a2, b2, f2) in E.trans[iid] if g2 > g and b2 == "Idle"), None)
                if end is None:
                    continue
                for d in IM_STARTS:
                    if g + d < end - 2:
                        starts.append((g + d, iid, MOVE_START[b], g, end))
    for g0, iid, move, gs, gend in sorted(starts):
        obs, mems = [], {}
        for jj in E.iids:
            m = mem_at(jj, g0)
            o = E.obs(jj, g0, m)
            if o is not None and o.st is not None:
                obs.append(o)
                mems[jj] = m
        if not any(o.iid == iid for o in obs):
            continue
        T = min(max(IM_KS) + 3, E.n_g - 1 - g0, gend - g0 + 2)
        if T < 3:
            continue
        hero = E.hero_path(g0, T, [o.iid for o in obs])
        try:
            P = cm.predict(obs, mems, hero, K, T=T, group=False, max_particles=400,
                           hazards=E.ghost_hazards(g0, {o.iid for o in obs}, K))
        except Exception as ex:
            R["errors"].append(f"{g0}: {ex!r}")
            continue
        act_rel = {o.iid: [dict(d, k=d["g"] - g0) for d in acts.get(o.iid, ()) if g0 < d["g"] <= g0 + T]
                   for o in obs}
        real = None
        for b in P.branches:
            if all(mv.consistent(b.logs.get(o.iid, []), act_rel[o.iid], T) for o in obs):
                real = b
                break
        R["realized"].append(real is not None)
        if real is None:
            continue
        for k in IM_KS:
            if k > T or g0 + k >= gend:
                continue
            act = mv.actual_damage(E, g0 + k, iid)
            if not act:
                continue
            pred = [s for s in real.damage(k) if s.iid == iid and s.name in ("body", "Slam Collider 1",
                                                                            "Slam Collider 2")]
            a, cov, pa = mv.area_cover(act, pred)
            names = "+".join(sorted({s.name for s in act}))
            R["area"].append((move, g0 - gs, k, round(a, 3), cov, round(pa, 3), E.st(iid, g0 + k), names))
        # true damage contacts of this Clapper inside the move
        for g, cid, skind, kind in E.contacts:
            k = g - 2 - g0
            if cid != iid or k < 0 or k + 2 > T or g >= gend:
                continue
            m_r = None
            for m in mv.MARGINS:
                for kk in range(k, k + 3):
                    hb = mv.her_box(E, g0 + kk)
                    if any(s.hits_box(hb, m) for s in real.damage(kk) if s.iid == iid):
                        m_r = m
                        break
                if m_r is not None:
                    break
            R["contact"].append((move, g0 - gs, k, skind, m_r))
    return dict(R)


def _kbin(k: int) -> int:
    for kk in (0, 6, 12, 24, 36, 60, 90):
        if k <= kk:
            return kk
    return 120


def cmd_margins(a) -> int:
    idle_priority()
    d = M2DATA / "cache" / a.set
    paths = sorted(d.glob("*.pkl"))
    if a.limit:
        paths = paths[:a.limit]
    t0 = time.time()
    res = []
    if a.jobs > 1:
        from multiprocessing import Pool
        with Pool(a.jobs) as pool:
            for n, r in enumerate(pool.imap_unordered(_inmove_episode, [str(p) for p in paths])):
                res.append(r)
                if n % 25 == 0:
                    print(f"{n + 1}/{len(paths)} {time.time() - t0:.0f}s", flush=True)
    else:
        res = [_inmove_episode(str(p)) for p in paths]
    area = defaultdict(lambda: np.zeros(len(mv.MARGINS) + 1))
    area_st = defaultdict(lambda: np.zeros(len(mv.MARGINS) + 1))
    area_sk = defaultdict(lambda: np.zeros(len(mv.MARGINS) + 1))
    cont = defaultdict(lambda: defaultdict(int))
    nreal = [0, 0]
    for r in res:
        for x in r.get("realized", ()):
            nreal[0] += 1
            nreal[1] += int(x)
        for row in r.get("area", ()):
            move, since, k, A, cov, pa = row[:6]
            key = (move, _kbin(k))
            area[key][0] += A
            area[key][1:] += np.asarray(cov, float)
            st = row[6] if len(row) > 6 else "?"
            key2 = (move, st, row[7] if len(row) > 7 else "")
            area_st[key2][0] += A
            area_st[key2][1:] += np.asarray(cov, float)
            key3 = (move, st, _kbin(k))
            area_sk[key3][0] += A
            area_sk[key3][1:] += np.asarray(cov, float)
        for (move, since, k, skind, m_r) in r.get("contact", ()):
            key = (move, _kbin(k))
            cont[key]["n"] += 1
            cont[key][str(m_r)] += 1
    table = {}
    lines = [f"in-move margins, set {a.set}: {len(res)} episodes, realized {nreal[1]} / {nreal[0]}"]

    def m99_of(share):
        m = next((m for m, s in zip(mv.MARGINS, share) if s >= 0.99), None)
        if m is None:     # the knee: within 0.2 % of the share at 1.0 u
            m = next(m for m, s in zip(mv.MARGINS, share) if s >= share[-1] - 0.002)
        return m
    for (move, kb), v in sorted(area.items()):
        share = v[1:] / max(v[0], 1e-9)
        m99 = m99_of(share)
        table.setdefault(move, []).append([kb, m99])
        c = cont.get((move, kb), {})
        lines.append(f"{move:6s} k<={kb:3d} area {v[0]:9.1f} share " + " ".join(f"{s:.4f}" for s in share) +
                     f" -> m {m99}; contacts {c.get('n', 0)}: " +
                     " ".join(f"{m}:{c.get(str(m), 0)}" for m in mv.MARGINS) + f" None:{c.get('None', 0)}")
    lines.append("by the actual state (all k): area, share at each margin")
    for (move, st, nm), v in sorted(area_st.items()):
        share = v[1:] / max(v[0], 1e-9)
        lines.append(f"  {move:6s} {str(st):18s} {nm:32s} {v[0]:9.1f} " + " ".join(f"{x:.4f}" for x in share))
    # per (move, the actual state, k bin): the table the search reads (a shape's margin by its own state)
    by_state = {}
    lines.append("by (move, state, k bin): margin (share at 0 / 0.2 / 0.5)")
    for (move, st, kb), v in sorted(area_sk.items(), key=lambda t: (t[0][0], str(t[0][1]), t[0][2])):
        if v[0] < 200.0:
            continue
        share = v[1:] / max(v[0], 1e-9)
        m = m99_of(share)
        by_state.setdefault(move, {}).setdefault(str(st), []).append([kb, m])
        lines.append(f"  {move:6s} {str(st):18s} k<={kb:3d} area {v[0]:9.1f} -> {m} ({share[0]:.4f} / {share[3]:.4f} / "
                     f"{share[5]:.4f})")
    for move, d in by_state.items():
        for st, t in d.items():
            t.sort()
            mx = 0.0
            for row in t:
                mx = max(mx, row[1])
                row[1] = mx
    with open(OUT / f"margins_inmove_{a.set}.raw.pkl", "wb") as fh:
        pickle.dump(res, fh)
    out = {"set": a.set, "episodes": len(res), "realized": nreal, "by_move": table, "by_state": by_state,
           "rule": "starts inside a move (its first state + 1 .. 40 frames), the move's own body / hammer area to its "
                   "Idle; >= 99 % covered by the realized branch's union grown by m, else the knee; monotone in k"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"margins_inmove_{a.set}.json").write_text(json.dumps(out, indent=1), "utf-8")
    (OUT / f"margins_inmove_{a.set}.txt").write_text("\n".join(lines) + "\n" + json.dumps(table) + "\n", "utf-8")
    print("\n".join(lines))
    print(json.dumps(table))
    print(f"{time.time() - t0:.0f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="m3_search")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("margins")
    p.add_argument("--set", default="fit")
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_margins)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
