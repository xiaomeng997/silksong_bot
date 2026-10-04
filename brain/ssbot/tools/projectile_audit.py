"""Centre error of the deterministic hazard paths (Forum plan R2 acceptance (c): p99 <= 0.3 u) on recorded fights.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.projectile_audit --cache C:/ssbot/data/m2_forum_r0/cache
        [--fights 20] [--every 2] [--horizon 0.8] [--json out.json]

Each fight's cache (ssbot.tools.forum_extract) is replayed as oracle WorldStates of its hazard entities (transform,
exported velocity, FSM state, damage boxes) through ssbot.combat.projectiles.HazardTracker; from every --every-th frame
each hazard's path (no time slack) is compared with where the export then shows it, frame by frame up to --horizon:
the transform for a bell, the damage box centre for a javelin, the circle's centre for a bomb (a row's later bombs
predicted before they appear: x and the appearance time). Left out (counted): frames after an event the path does not
model and nobody can (a nail hit, a break, a stick after the origin; the dome tube); a frame whose hazard is not
exported. Also: the share of logged damage boxes inside the support form (time slack, skin).
"""
import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def cache_worldstates(cache: dict, types: frozenset | None = None, start: int = 0):
    """Oracle WorldStates of a cache's entities (only types, or every type): stamp, transform, exported velocity, the
    first FSM's state, damage boxes (active), hidden. Yields (frame index, WorldState)."""
    from ssbot.core.worldstate import DamageBox, E, Entity, Stamp, WorldState
    tnames, snames = cache["types"], cache["states"]
    starts = np.searchsorted(cache["e_fi"], np.arange(len(cache["f"]) + 1))
    cstarts = np.searchsorted(cache["c_ei"], np.arange(len(cache["e_fi"]) + 1))
    ok_t = np.array([types is None or t in types for t in tnames], bool)
    for i in range(start, len(cache["f"])):
        ents = []
        for r in range(starts[i], starts[i + 1]):
            k = int(cache["e_tk"][r])
            if not ok_t[k]:
                continue
            boxes = []
            for j in range(cstarts[r], cstarts[r + 1]):
                b = cache["c_box"][j]
                boxes.append(DamageBox(poly=[(float(b[0]), float(b[1])), (float(b[2]), float(b[1])),
                                             (float(b[2]), float(b[3])), (float(b[0]), float(b[3]))], active=True,
                                       name=cache["names"][int(cache["c_name"][j])]))
            x, y = float(cache["e_x"][r]), float(cache["e_y"][r])
            vx, vy = float(cache["e_vx"][r]), float(cache["e_vy"][r])
            st = int(cache["e_st"][r])
            ents.append(Entity(id=int(cache["e_iid"][r]), type_key=E(tnames[k]), pos=E((x, y)),
                               vel=E((0.0 if math.isnan(vx) else vx, 0.0 if math.isnan(vy) else vy),
                                     conf=0.0 if math.isnan(vx) else 1.0),
                               dmg_boxes=boxes, fsm=[("Control", snames[st], float(cache["e_tin"][r]))] if st >= 0
                               else None, hidden=bool(cache["e_hidden"][r]), pos_transform=(x, y),
                               flip_x=bool(cache["e_flip"][r])))
        yield i, WorldState(stamp=Stamp(frame=int(cache["f"][i]), t_game_s=float(cache["T"][i])), entities=ents)


def audit_fight(cache: dict, every: int, horizon: float, err: dict, cov: Counter, skipped: Counter,
                rows: dict) -> None:
    from ssbot.combat.projectiles import BELL, BOMB, PIN, RUNE, SKIN_U, HazardTracker
    hz = HazardTracker()
    T = cache["T"]
    tnames, snames = cache["types"], cache["states"]
    starts = np.searchsorted(cache["e_fi"], np.arange(len(cache["f"]) + 1))
    # per hazard iid: frame index -> (centre x, y of what the path predicts, state, box centre, box)
    track: dict[int, dict] = defaultdict(dict)
    alias_r = {"damager"}
    for i in range(len(cache["f"])):
        for r in range(starts[i], starts[i + 1]):
            tk = tnames[int(cache["e_tk"][r])]
            if tk not in (BELL, PIN) and tk not in alias_r:
                continue
            b = cache["e_box"][r]
            st = int(cache["e_st"][r])
            track[int(cache["e_iid"][r])][i] = (float(cache["e_x"][r]), float(cache["e_y"][r]),
                                                snames[st] if st >= 0 else None,
                                                None if math.isnan(b[0]) else tuple(float(v) for v in b))
    n_h = int(math.ceil(horizon * 60)) + 1
    pending_rows: list = []
    for i, ws in cache_worldstates(cache, frozenset((BELL, PIN, "damager"))):
        hz.update(ws)
        if i % every:
            continue
        T0 = float(T[i])
        for p in hz.paths(T0, horizon):
            if p.predicted:
                pending_rows.append((i, p))
                continue
            tr = track.get(p.iid)
            if tr is None or p.type_key in (BOMB, RUNE):
                continue
            prev = tr.get(i, (None, None, None, None))[2]
            for j in range(i + 1, min(len(T), i + n_h)):
                o = tr.get(j)
                tau = float(T[j] - T0)
                if o is None:
                    skipped[f"{p.type_key}: not exported"] += 1
                    break
                st = o[2]
                if p.type_key == BELL and st in ("Nail Hit", "Deactivate", "Recycle", "Break") and st != prev:
                    skipped[f"{p.type_key}: {st} after the origin"] += 1
                    break
                prev = st
                if p.type_key == PIN and st not in ("Fly",):
                    skipped[f"{p.type_key}: {st} after the origin"] += 1
                    break
                if p.tube_from is not None and tau >= p.tube_from:
                    skipped[f"{p.type_key}: dome tube"] += 1
                    break
                cx, cy, on, grow = p.at(np.array([tau]), slack=False)
                if p.type_key == BELL:
                    ox, oy = o[0], o[1]
                else:
                    if o[3] is None:
                        continue
                    ox, oy = 0.5 * (o[3][0] + o[3][2]), 0.5 * (o[3][1] + o[3][3])
                if not on[0, 0]:
                    continue
                e = math.hypot(cx[0, 0] - ox, cy[0, 0] - oy)
                err[p.type_key].append((tau, e))
                if o[3] is not None:
                    sx, sy, son, sg = p.at(np.array([tau]), slack=True)
                    bx = o[3]
                    ok = False
                    for s in range(sx.shape[0]):
                        if not son[s, 0]:
                            continue
                        if p.kind == "circle":
                            dx = max(abs(0.5 * (bx[0] + bx[2]) - sx[s, 0]) - 0.5 * (bx[2] - bx[0]), 0.0)
                            dy = max(abs(0.5 * (bx[1] + bx[3]) - sy[s, 0]) - 0.5 * (bx[3] - bx[1]), 0.0)
                            ok |= math.hypot(dx, dy) <= p.r + SKIN_U + sg[s, 0]
                        else:
                            ok |= (abs(0.5 * (bx[0] + bx[2]) - sx[s, 0]) <= 0.5 * (bx[2] - bx[0]) + p.hx + SKIN_U
                                   and abs(0.5 * (bx[1] + bx[3]) - sy[s, 0]) <= 0.5 * (bx[3] - bx[1]) + p.hy + SKIN_U)
                    cov[f"{p.type_key} n"] += 1
                    cov[f"{p.type_key} inside"] += ok
    # a row's later bombs: the predicted x / appearance against the bombs that appeared (first frame of each)
    appear: list = []
    for iid, fr in track.items():
        last = None
        for j in sorted(fr):
            if last is None or j - last > 30:
                x, y = fr[j][0], fr[j][1]
                if abs(y - 3.67) < 0.05:
                    appear.append((float(T[j]), x))
            last = j
    appear.sort()
    xs = np.array([a[1] for a in appear]) if appear else np.zeros(0)
    ts = np.array([a[0] for a in appear]) if appear else np.zeros(0)
    done = set()
    for i, p in pending_rows:
        key = (round(float(p.xs[0]), 2), round(float(T[i]) + p.t_lo, 1))
        if key in done:
            continue
        done.add(key)
        t_app = float(T[i]) + p.t_lo + 2 * 0.02 - 0.335
        m = (np.abs(xs - p.xs[0]) < 1.5) & (np.abs(ts - t_app) < 0.3)
        if m.any():
            j = int(np.flatnonzero(m)[np.argmin(np.abs(ts[m] - t_app))])
            rows["x_err"].append(abs(xs[j] - p.xs[0]))
            rows["t_err"].append(abs(ts[j] - t_app))
        else:
            rows["not_seen"].append(1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--fights", type=int, default=20)
    ap.add_argument("--skip", type=int, default=0, help="leave out the first N caches")
    ap.add_argument("--every", type=int, default=2)
    ap.add_argument("--horizon", type=float, default=0.8)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.knowledge.forum_cache import load_cache
    paths = sorted(a.cache.glob("*.npz"))[a.skip:a.skip + a.fights]
    err: dict = defaultdict(list)
    cov: Counter = Counter()
    skipped: Counter = Counter()
    rows: dict = defaultdict(list)
    t0 = time.perf_counter()
    for k, p in enumerate(paths):
        audit_fight(load_cache(p), a.every, a.horizon, err, cov, skipped, rows)
        print(f"[{k + 1}/{len(paths)}] {p.name} ({time.perf_counter() - t0:.0f} s)", flush=True)
    out: dict = {"fights": [p.stem for p in paths], "every": a.every, "horizon_s": a.horizon, "types": {}}
    for tk, v in err.items():
        arr = np.array(v)
        q = lambda m: {"n": int(m.sum()), "p50": round(float(np.percentile(arr[m, 1], 50)), 4),  # noqa: E731
                       "p99": round(float(np.percentile(arr[m, 1], 99)), 4),
                       "max": round(float(arr[m, 1].max()), 4)} if m.any() else {"n": 0}
        out["types"][tk] = {"all": q(np.ones(len(arr), bool)),
                            "by_horizon": {f"<={h}": q(arr[:, 0] <= h + 1e-9) for h in (0.1, 0.2, 0.4, 0.8)},
                            "support_inside": f"{cov[tk + ' inside']}/{cov[tk + ' n']}"}
    if rows:
        out["bomb_rows"] = {"predicted_bombs_matched": len(rows["x_err"]), "not_seen": len(rows["not_seen"]),
                            "x_err_max": round(float(max(rows["x_err"])), 4) if rows["x_err"] else None,
                            "x_err_p99": round(float(np.percentile(rows["x_err"], 99)), 4) if rows["x_err"] else None,
                            "t_err_max": round(float(max(rows["t_err"])), 4) if rows["t_err"] else None}
    out["left_out"] = dict(skipped)
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
