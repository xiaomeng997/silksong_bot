"""Track A's measurements over the Forum caches (forum.md §26; ssbot.knowledge.forum_cache, R0 + R1):
  whip      the Choristor's Whip Hit 1-6 colliders in its facing frame (x + in front of the transform, y from it), the
            whip states' dwell and speed: does the whip reach behind it (it does: Whip Hit 5-6 to 4.75 u behind)
  minister  the Minister's Parry Stance: its transform's height over the floor, the stance collider's bottom / top, and
            its counter's colliders (ParrySlash Hit 1-4) and the Reed's (ParrySlash Hit) relative to the transform
  knockback each nail hit's push on the enemy: the transform's displacement 2-30 frames after the hit less its own
            motion over the 3 frames before (side: away from the hero), by type x slash (side / up / down) x state at
            the hit; the guards as "guard" rows (a Minister's Parry Stance -> Parry Block, a Reed's Defend -> Block,
            the slash taken from where the hero is: below / above / beside)

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_knockback --out C:/ssbot/data/m2_forum_ta/measure.json
        [--cache "C:/ssbot/data/m2_forum_r0/cache/*.npz" --cache "C:/ssbot/data/m2_forum_r1c/cache/*.npz"]

The planner's constants (combat.forum_planner KB_*, the L2 rules' whip_* / guard_* in Forum.yaml / L2Rules) come from
this output (forum.md §26).
"""
import argparse
import glob
import json
import sys
from collections import defaultdict

import numpy as np

from ssbot.core.forum import FLOOR_Y

KB_F = (2, 4, 6, 9, 12, 18, 24, 30)
SLASH = {"Slash": "side", "AltSlash": "side", "WallSlash": "side", "UpSlash": "up", "DownSlash New": "down",
         "DownSlash": "down", "DashSlash": "side"}
TYPES = ("Song Reed", "Song Administrator", "Pilgrim 03 Song", "Song Pilgrim Maestro", "Song Automaton Tiny",
         "Song Handmaiden", "Song Pilgrim 03", "Song Pilgrim 01", "Song Heavy Sentry")
CACHES = ("C:/ssbot/data/m2_forum_r0/cache/*.npz", "C:/ssbot/data/m2_forum_r1c/cache/*.npz")


class Acc:
    def __init__(self):
        self.whip = defaultdict(list)
        self.whip_speed = []
        self.whip_dwell = defaultdict(list)
        self.mstance = []
        self.mcounter = defaultdict(list)
        self.rcounter = []
        self.kb = defaultdict(list)
        self.fights = 0


def facing_frame(c: dict, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(lo, hi) of the collider rows' x extent in their entity's facing frame (+ in front; the Forum sprites face -x
    unflipped: flipX 1 faces +x, enemy_tracker.FACES_LEFT)."""
    ei = c["c_ei"][rows]
    face = np.where(c["e_flip"][ei] > 0, 1.0, -1.0)
    ex = c["e_x"][ei]
    a = (c["c_box"][rows, 0] - ex) * face
    b = (c["c_box"][rows, 2] - ex) * face
    return np.minimum(a, b), np.maximum(a, b)


def add_cache(acc: Acc, c: dict) -> None:
    acc.fights += 1
    types, states, names = c["types"], c["states"], c["names"]
    tk_of = {t: i for i, t in enumerate(types)}
    st_name = np.array(list(states) + ["?"], dtype=object)
    nm = np.array(names, dtype=object)
    cn = nm[c["c_name"]] if len(c["c_name"]) else np.array([], dtype=object)
    et = c["e_tk"][c["c_ei"]] if len(c["c_ei"]) else np.array([], np.int64)
    lo, hi = facing_frame(c, np.arange(len(c["c_ei"])))
    ey = c["e_y"][c["c_ei"]] if len(c["c_ei"]) else np.array([])
    cho, mi, re_ = (tk_of.get(t, -99) for t in ("Song Pilgrim 03", "Song Administrator", "Song Reed"))
    for i in np.flatnonzero(et == cho):
        if str(cn[i]).startswith("Whip Hit"):
            acc.whip[str(cn[i])].append((lo[i], hi[i], c["c_box"][i, 1] - ey[i], c["c_box"][i, 3] - ey[i]))
    for i in np.flatnonzero(et == mi):
        if cn[i] == "Collider ParryStance":
            acc.mstance.append((ey[i] - FLOOR_Y, c["c_box"][i, 1] - FLOOR_Y, c["c_box"][i, 3] - FLOOR_Y))
        elif str(cn[i]).startswith("ParrySlash Hit"):
            acc.mcounter[str(cn[i])].append((lo[i], hi[i], c["c_box"][i, 1] - ey[i], c["c_box"][i, 3] - ey[i]))
    for i in np.flatnonzero(et == re_):
        if str(cn[i]).startswith("ParrySlash Hit"):
            acc.rcounter.append((lo[i], hi[i], c["c_box"][i, 1] - ey[i], c["c_box"][i, 3] - ey[i]))
    e_tk, e_x, e_y = c["e_tk"], c["e_x"], c["e_y"]
    if cho >= 0:
        m = e_tk == cho
        sn = st_name[c["e_st"][m]]
        w = np.array([str(s).startswith("Whip") for s in sn], bool)
        acc.whip_speed += list(np.abs(c["e_vx"][m][w])[::3])
        for s in set(sn[w]):
            acc.whip_dwell[str(s)].append(float(np.max(c["e_tin"][m][sn == s])))
    fidx = {int(f): i for i, f in enumerate(c["f"])}
    rows = defaultdict(dict)
    for j in np.flatnonzero(np.isin(e_tk, [tk_of[t] for t in TYPES if t in tk_of])):
        rows[int(c["e_iid"][j])][int(c["e_fi"][j])] = j
    hx, hy = c["hx"], c["hy"]
    for (f, k, d) in c["events"]:
        if k == "fsm" and d.get("obj") in ("Song Administrator", "Song Reed") and \
                d.get("to") in ("Parry Block", "Block") and d.get("from") in ("Parry Stance", "Defend"):
            ent, how = d.get("ent"), "guard"
            fi = fidx.get(int(f))
            r0 = rows.get(int(ent)) if ent is not None else None
            if fi is None or r0 is None or fi not in r0:
                continue
            dyh = e_y[r0[fi]] - hy[fi]
            src = "up" if dyh > 1.5 and abs(e_x[r0[fi]] - hx[fi]) < 2.0 else ("down" if dyh < -1.5 else "side")
        elif k == "hit" and d.get("src") in SLASH:
            ent, how, src = d.get("ent"), "hit", SLASH[d["src"]]
        else:
            continue
        fi = fidx.get(int(f))
        r = rows.get(int(ent)) if ent is not None else None
        if fi is None or r is None or fi not in r or (fi - 3) not in r:
            continue
        j0, jb = r[fi], r[fi - 3]
        side = 1.0 if e_x[j0] >= hx[fi] else -1.0
        vx0, vy0 = (e_x[j0] - e_x[jb]) / 3.0, (e_y[j0] - e_y[jb]) / 3.0
        dxs, dys = [], []
        for kk in KB_F:
            jj = r.get(fi + kk)
            dxs.append(np.nan if jj is None else float((e_x[jj] - e_x[j0] - vx0 * kk) * side))
            dys.append(np.nan if jj is None else float(e_y[jj] - e_y[j0] - vy0 * kk))
        key = (types[e_tk[j0]], src, str(st_name[c["e_st"][j0]]), how)
        acc.kb[key].append(dxs + dys)


def _q(a, ps=(0, 1, 5, 50, 95, 99, 100)) -> dict | None:
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return {str(p): round(float(np.percentile(a, p)), 3) for p in ps} if len(a) else None


def _box_stats(v: list) -> dict:
    return {"n": len(v), "x0": _q([r[0] for r in v]), "x1": _q([r[1] for r in v]), "y0": _q([r[2] for r in v]),
            "y1": _q([r[3] for r in v])}


def summary(acc: Acc, min_n: int = 5) -> dict:
    out = {"fights": acc.fights, "kb_frames": KB_F,
           "whip": {k: _box_stats(v) for k, v in sorted(acc.whip.items())},
           "whip_behind_x0": _q([r[0] for v in acc.whip.values() for r in v]),
           "whip_speed": _q(acc.whip_speed), "whip_dwell": {k: _q(v) for k, v in sorted(acc.whip_dwell.items())},
           "minister_stance": {"n": len(acc.mstance), "ey": _q([m[0] for m in acc.mstance]),
                               "y0_rel": _q([m[1] - m[0] for m in acc.mstance]),
                               "y1_rel": _q([m[2] - m[0] for m in acc.mstance])},
           "minister_counter": {k: _box_stats(v) for k, v in sorted(acc.mcounter.items())},
           "reed_counter": _box_stats(acc.rcounter), "kb": {}}
    nk = len(KB_F)
    for key, v in sorted(acc.kb.items(), key=lambda kv: -len(kv[1])):
        a = np.array(v, float)
        if len(a) < min_n:
            continue
        out["kb"]["|".join(key)] = {
            "n": len(a), "dx_p50": [round(float(np.nanmedian(a[:, i])), 3) for i in range(nk)],
            "dy_p50": [round(float(np.nanmedian(a[:, nk + i])), 3) for i in range(nk)],
            "dy_p10": [round(float(np.nanpercentile(a[:, nk + i], 10)), 3) for i in range(nk)]}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", action="append", default=None, help="glob of forum_cache .npz (repeatable)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from ssbot.knowledge.forum_cache import load_cache
    acc = Acc()
    for g in a.cache or CACHES:
        for p in sorted(glob.glob(g)):
            add_cache(acc, load_cache(p))
            if acc.fights % 50 == 0:
                print(acc.fights, p, flush=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(summary(acc), fh, indent=1)
    print("done", acc.fights)
    return 0


if __name__ == "__main__":
    sys.exit(main())
