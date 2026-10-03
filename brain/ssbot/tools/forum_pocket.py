"""The left-wall cling pocket of the Forum finale (M2 W8, the person's plan: two Choir Clappers, cling at the top of
the left wall where they cannot reach): the closest approach of every Clapper damage collider and of its hazards to
the pocket, from recordings (docs/facts/1.0.30000/forum.md §10).

    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_pocket C:/ssbot/data/runs/m2/<run> [more runs] [--include-open]
        [--pocket 14.042,12.534,14.918,13.965] [--json out.json]

The pocket is the hero's damage receiver at the top of the left-wall cling (forum.md §8.1: wall face x 14.01, cling
x 14.27, highest still cling y 13.45-13.60 under the Roof Collider_Basic (2) dome). Clinging to the left wall calls
FaceLeft (transform scale x +1) and HeroBox.HeroBoxWallSlide (HeroBox.cs: 0.8757 x 1.2805 at (+0.2101, -0.2755) from
the hero transform), so the receiver spans x 14.04-14.92, y 12.53-13.97 (STATE hero.box is the physics collider's
bounds, 0.5 x 2.08, not the receiver). For every frame of every fight (AttemptRecord f_wake..f_end) and
every enabled damage collider of a "Song Heavy Sentry" (body box, Slam Collider 1 / 2) and of the hazards it spawns
("damager" circles told apart by radius: Bomb Cast bombs, the Jump Cast rune; ssbot.knowledge.gauntlet_tables
.HAZARD_ALIASES), the exact distance from the collider (polygon or circle) to the pocket box, kept per Clapper attack
family (its Control state mapped through FORUM_SPECS) and state. Also: every jump's takeoff x and the lowest x of the
body's left edge while its top is above the pocket's bottom, and the hero contacts while the hero was in the pocket.
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from ssbot.ipc.ents import collider_points
from ssbot.knowledge.behaviour_tables import fight_states, run_fights, support_threat
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS, hazard_type

CLAPPER = "Song Heavy Sentry"
POCKET = (14.042, 12.534, 14.918, 13.965)   # HeroBoxWallSlide at (14.27, 13.45-13.60), facing left
CLING_X, CLING_Y_MIN = 14.27, 13.2          # hero transform in the pocket (the contacts there are listed)


def _seg_box_dist(p: np.ndarray, q: np.ndarray, box: tuple) -> float:
    """Distance from segment p-q to an axis-aligned box (0 when they meet), sampled finely enough for colliders of a
    few units (the exact segment-box distance is the minimum over the segment; 64 samples, error < 0.1 % of its
    length)."""
    t = np.linspace(0.0, 1.0, 64)[:, None]
    pts = p + t * (q - p)
    dx = np.maximum(np.maximum(box[0] - pts[:, 0], pts[:, 0] - box[2]), 0.0)
    dy = np.maximum(np.maximum(box[1] - pts[:, 1], pts[:, 1] - box[3]), 0.0)
    return float(np.sqrt(dx * dx + dy * dy).min())


def collider_box_distance(c: dict, box: tuple) -> float:
    """Exact-enough distance from a collider (circle, box, polygon) to an axis-aligned box; 0 when they overlap."""
    pts = np.asarray(collider_points(c), np.float64).reshape(-1, 2)
    if c.get("kind") == "circle" and c.get("r") is not None:
        cx, cy = pts.mean(axis=0) if len(pts) > 1 else pts[0]
        dx = max(box[0] - cx, cx - box[2], 0.0)
        dy = max(box[1] - cy, cy - box[3], 0.0)
        return max(0.0, math.hypot(dx, dy) - float(c["r"]))
    if len(pts) == 0:
        return math.inf
    inside = ((pts[:, 0] >= box[0]) & (pts[:, 0] <= box[2]) & (pts[:, 1] >= box[1]) & (pts[:, 1] <= box[3])).any()
    if inside:
        return 0.0
    # a box corner inside the polygon (the collider wraps the pocket)
    corners = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    if len(pts) >= 3 and any(_inside(pts, cx, cy) for cx, cy in corners):
        return 0.0
    n = len(pts)
    if n == 1:
        return _seg_box_dist(pts[0], pts[0], box)
    return min(_seg_box_dist(pts[i], pts[(i + 1) % n], box) for i in range(n))


def _inside(poly: np.ndarray, x: float, y: float) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def scan(runs: list[Path], include_open: bool = False, pocket: tuple = POCKET) -> dict:
    spec = FORUM_SPECS[CLAPPER]
    best: dict[tuple, dict] = {}
    fam_best: dict[str, dict] = {}
    jumps: list[dict] = []
    pocket_contacts: list[dict] = []
    pocket_frames = 0
    pocket_entries: Counter = Counter()     # Clapper Control states entered while the hero is in the pocket
    pocket_x: list[float] = []              # Clapper x on those frames
    clapper_frames = 0
    fights = 0
    for run in runs:
        fs, _ = run_fights(run, closed_only=not include_open)
        for fight in fs:
            fights += 1
            fam: dict[int, str] = {}
            st_prev: dict[int, str] = {}
            air: dict[int, dict] = {}
            for s in fight_states(fight, keys=("hero", "ents", "ev")):
                f = s["f"]
                hero = s.get("hero") or {}
                hb = hero.get("box")
                hp = hero.get("pos")
                in_pocket = bool(hp) and hp[0] < CLING_X + 0.3 and hp[1] >= CLING_Y_MIN   # clinging up there
                pocket_frames += in_pocket
                if in_pocket:
                    for ev in s.get("ev") or ():
                        if ev.get("k") in ("damage", "damage_blocked"):
                            d = ev.get("d") or {}
                            pocket_contacts.append({"fight": fight.id, "f": f, "kind": ev["k"],
                                                    "source": d.get("source"), "hero_pos": [round(v, 3) for v in hp[:2]],
                                                    "hero_bounds": [round(v, 3) for v in hb or ()]})
                clappers = []
                for e in s.get("ents") or ():
                    tk = e.get("type_key")
                    if tk == CLAPPER:
                        clappers.append(e)
                        clapper_frames += 1
                        iid = e["iid"]
                        st = next((x.get("state") for x in e.get("fsms") or () if x.get("name") == "Control"), None)
                        if st in spec.attack_starts:
                            fam[iid] = spec.attack_starts[st]
                        elif st in spec.decision_states or st in spec.dormant:
                            fam[iid] = spec.idle_family
                        _jump(e, st, st_prev.get(iid), air, jumps, fight.id, f, pocket, hp[0] if hp else None)
                        if in_pocket:
                            pocket_x.append(round(e["pos"][0], 2))
                            if st != st_prev.get(iid):
                                pocket_entries[st] += 1
                        st_prev[iid] = st
                        for c in e.get("colliders") or ():
                            if support_threat(c):
                                _keep(best, fam_best, (fam.get(iid, "?"), st, c.get("name")), c, pocket, f,
                                      fight.id, e)
                    elif tk == "damager":
                        alias = hazard_type(e)
                        for c in e.get("colliders") or ():
                            if support_threat(c):
                                _keep(best, fam_best, (alias, "-", c.get("name")), c, pocket, f, fight.id, e)
    rows = sorted(({"family": k[0], "state": k[1], "collider": k[2], **v} for k, v in best.items()),
                  key=lambda r: r["dist_u"])
    return {"pocket": list(pocket), "fights": fights, "clapper_frames": clapper_frames,
            "pocket_frames": pocket_frames,
            "pocket_clapper_states": dict(pocket_entries.most_common()),
            "pocket_clapper_x": [float(v) for v in np.quantile(pocket_x, [0, 0.05, 0.5, 0.95, 1])] if pocket_x else None,
            "by_family": dict(sorted(fam_best.items(), key=lambda kv: kv[1]["dist_u"])),
            "by_state": rows, "jumps": jumps, "pocket_contacts": pocket_contacts}


def _keep(best: dict, fam_best: dict, key: tuple, c: dict, pocket: tuple, f: int, fid: str, e: dict) -> None:
    d = collider_box_distance(c, pocket)
    row = {"dist_u": round(d, 3), "f": f, "fight": fid, "pos": [round(v, 2) for v in e["pos"][:2]],
           "n": best.get(key, {}).get("n", 0) + 1}
    if key not in best or d < best[key]["dist_u"]:
        best[key] = row
    else:
        best[key]["n"] = row["n"]
    fk = key[0]
    if fk not in fam_best or d < fam_best[fk]["dist_u"]:
        fam_best[fk] = {**row, "state": key[1], "collider": key[2]}


def _jump(e: dict, st: str | None, prev: str | None, air: dict, jumps: list, fid: str, f: int, pocket: tuple,
          hero_x: float | None = None) -> None:
    """Track a jump from its Jump state until it leaves Air: takeoff x, facing, and the lowest left edge of the body
    box while the body's top is above the pocket's bottom."""
    iid = e["iid"]
    body = next((c for c in e.get("colliders") or ()
                 if str(c.get("name")).startswith(CLAPPER) and c.get("kind") == "box"), None)
    if st == "Jump" and prev != "Jump":
        air[iid] = {"fight": fid, "f": f, "x0": round(e["pos"][0], 3), "flipX": e.get("flipX"),
                    "hero_x": None if hero_x is None else round(hero_x, 2),
                    "min_left_high": None, "max_top": None}
    j = air.get(iid)
    if j is None:
        return
    if st in ("Jump", "Air") and body is not None:
        v = np.asarray(collider_points(body)).reshape(-1, 2)
        left, top = float(v[:, 0].min()), float(v[:, 1].max())
        j["max_top"] = round(max(top, j["max_top"] or -math.inf), 3)
        if top >= pocket[1]:
            j["min_left_high"] = round(min(left, j["min_left_high"] if j["min_left_high"] is not None else math.inf), 3)
    elif st not in ("Jump", "Air"):
        jumps.append(air.pop(iid))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--include-open", action="store_true")
    ap.add_argument("--pocket", default=",".join(str(v) for v in POCKET), help="x0,y0,x1,y1 of the hero's damage receiver")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    pocket = tuple(float(v) for v in a.pocket.split(","))
    out = scan(a.runs, a.include_open, pocket)
    print(f"pocket {pocket}: {out['fights']} fights, {out['clapper_frames']} Clapper frames, hero in the pocket "
          f"{out['pocket_frames']} frames, contacts there {len(out['pocket_contacts'])}")
    print("Clapper states entered while the hero is in the pocket:", out["pocket_clapper_states"])
    print("Clapper x then (min, p5, p50, p95, max):", out["pocket_clapper_x"])
    print("closest approach per family (u):")
    for k, v in out["by_family"].items():
        print(f"  {k:16s} {v['dist_u']:6.2f}  ({v['state']} / {v['collider']}, f{v['f']} pos {v['pos']})")
    print("per state and collider:")
    for r in out["by_state"]:
        print(f"  {r['family']:16s} {r['state']!s:18s} {r['collider']!s:24s} {r['dist_u']:6.2f}  n {r['n']}")
    hi = [j for j in out["jumps"] if j["min_left_high"] is not None]
    if out["jumps"]:
        print(f"jumps {len(out['jumps'])}: takeoff x {min(j['x0'] for j in out['jumps']):.2f}.."
              f"{max(j['x0'] for j in out['jumps']):.2f}; body left edge while its top >= {pocket[1]}: min "
              f"{min(j['min_left_high'] for j in hi) if hi else None}")
    for c in out["pocket_contacts"][:20]:
        print("  pocket contact", c)
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
