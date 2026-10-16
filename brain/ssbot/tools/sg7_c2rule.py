"""Task 1v1 SG7 (1): the Slam Collider 2 rule after a bounce, from the game and the recordings (forum.md 63).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sg7_c2rule C:/ssbot/data/m2_map/sg7/c2/slams_*.jsonl \
        --out C:/ssbot/data/m2_map/sg7/c2/rule.json

Reads sg7_c2scan's slams. Per frame and per hurt shape of the Clapper's slam (Slam Collider 1 / 2, the root):
  - the overlap with the hero under four models: the bounding box (what the map's move data holds) against the hero's
    physics box (STATE hero.box, what the map's hero macros sweep); the polygon (the collider's real shape: the oracle
    exports PolygonCollider2D world vertices) against the physics box; the polygon against the real HeroBox for the
    hero's state (HeroBox.cs: ground 0.4554 x 2.2498 at -0.3799, air 0.4554 x 1.77 at -0.14, downspike 0.4554 x
    1.218 at -0.1, relative to the transform; the transform = physics box bottom + 1.5527); the polygon against the
    conservative box (the physics box with its top raised to the HeroBox's top, + 0.2187);
  - the TakeDamage attempts that name the shape (oracle "damage" = past the top gate, "damage_blocked" frames
    first_f..last_f), the hp losses naming it;
  - the hero's protection: the downspike i-frame counter (cstate_int), invulnerable, recoiling.
Counts both ways: attempts / hits without an overlap in each model (the model would miss a real hit: unsafe), and
overlaps while the hero can be hurt (counter 0, not invulnerable, not recoiling) without an attempt (the model is
stricter than the game).
Also: the polygons' rigidity in the Clapper's frame (vertices relative to its position, x mirrored by its facing).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from shapely import Polygon, box as sbox

CSN = ("onGround", "shadowDashing", "dashing", "isSprinting", "airDashing", "wallSliding", "wallClinging", "attacking",
       "downAttacking", "downSpiking", "downSpikeBouncing", "downSpikeRecovery", "bouncing", "recoiling",
       "invulnerable", "parrying", "evading")
FOOT = 1.5527                      # transform above the physics box bottom (kinematics: box 0.5 x 2.0789)
HB_HW = 0.2277                     # HeroBox half width
HB = {"ground": (-0.3799, 2.2498), "air": (-0.14, 1.77), "downspike": (-0.1, 1.218)}
TOP_UP = 0.745 - 0.5262            # the normal HeroBox's top above the physics box's top
NAMES = {"1": "Slam Collider 1", "2": "Slam Collider 2", "r": "Song Heavy Sentry"}
MODELS = ("aabb_phys", "poly_phys", "poly_herobox", "poly_cons")
LAT = 2                            # frames from an overlap to its TakeDamage attempt (the trigger fires in the next
                                   # physics step; a frame without a step adds one: 55284 -> 55286)


def cs(b: int, n: str) -> bool:
    return bool((b >> CSN.index(n)) & 1)


def herobox(r: dict) -> list[float]:
    hb = r["hb"]
    cx = 0.5 * (hb[0] + hb[2])
    tr = hb[1] + FOOT
    kind = "downspike" if cs(r["cs"], "downSpiking") else "ground" if cs(r["cs"], "onGround") else "air"
    off, h = HB[kind]
    return [cx - HB_HW, cx + HB_HW, tr + off - h / 2, tr + off + h / 2]


def phys(r: dict) -> list[float]:
    hb = r["hb"]
    return [hb[0], hb[2], hb[1], hb[3]]


def cons(r: dict) -> list[float]:
    hb = r["hb"]
    return [hb[0], hb[2], hb[1], hb[3] + TOP_UP]


def _poly(v) -> Polygon:
    return Polygon([(v[i], v[i + 1]) for i in range(0, len(v), 2)]).buffer(0)


def _gap(a, b) -> float:
    """Signed separation: > 0 apart (distance), < 0 overlapping (minus the smaller intersection side)."""
    if not a.intersects(b):
        return float(a.distance(b))
    x0, y0, x1, y1 = a.intersection(b).bounds if not a.intersection(b).is_empty else (0, 0, 0, 0)
    return -float(min(x1 - x0, y1 - y0))


def frame_gaps(r: dict) -> dict:
    """{shape: {model: gap}} for the shapes enabled on this frame."""
    out = {}
    if not r.get("hb"):
        return out
    P, H, C = phys(r), herobox(r), cons(r)
    bP, bH, bC = sbox(P[0], P[2], P[1], P[3]), sbox(H[0], H[2], H[1], H[3]), sbox(C[0], C[2], C[1], C[3])
    for key in ("1", "2", "r"):
        bb = r["ham"].get(key) if key != "r" else r.get("root")
        if bb is None:
            continue
        verts = (r.get("poly") or {}).get(key)
        A = sbox(bb[0], bb[2], bb[1], bb[3])
        Pg = _poly(verts) if verts else A
        out[key] = {"aabb_phys": _gap(A, bP), "poly_phys": _gap(Pg, bP), "poly_herobox": _gap(Pg, bH),
                    "poly_cons": _gap(Pg, bC)}
    return out


def shape_of(src: str | None) -> str | None:
    if not src:
        return None
    s = str(src)
    if s.endswith("Slam Collider 1"):
        return "1"
    if s.endswith("Slam Collider 2"):
        return "2"
    if s.endswith("Song Heavy Sentry"):
        return "r"
    return None


def rel_verts(r: dict, key: str) -> np.ndarray | None:
    v = (r.get("poly") or {}).get(key)
    if not v:
        return None
    a = np.array(v, float).reshape(-1, 2) - np.array(r["pos"], float)
    if not r["flip"]:          # flipX False: the Clapper faces left (-x); mirror into its facing frame
        a[:, 0] = -a[:, 0]
    return a


def analyse(paths: list[Path]) -> dict:
    att_rows = []          # every TakeDamage attempt naming a slam shape
    overlap_free = Counter()   # (shape, model) -> frames overlapping while the hero can be hurt, no attempt that frame
    overlap_free_ex = defaultdict(list)
    overlap_n = Counter()
    hurtable = Counter()
    verts = defaultdict(list)
    n_slams = 0
    iframes = Counter()
    hits_c2 = []
    dropped = Counter()
    for p in paths:
        slams = [json.loads(line) for line in p.open(encoding="utf-8")]
        # another Clapper slamming at the same time: the events name the collider, not the instance -> drop both
        span = defaultdict(list)
        for c in slams:
            if c["frames"]:
                span[c["rec"]].append((c["frames"][0]["f"], c["frames"][-1]["f"], c["iid"]))
        for c in slams:
            if not c["frames"]:
                continue
            a, b = c["frames"][0]["f"], c["frames"][-1]["f"]
            if any(i != c["iid"] and a <= y and x <= b for x, y, i in span[c["rec"]]):
                dropped["two_clappers"] += 1
                continue
            n_slams += 1
            F = c["frames"]
            # attempts per frame (damage: its frame; blocked: first_f..last_f)
            att = defaultdict(set)
            for r in F:
                for e in r["ev"]:
                    if e[0] == "damage":
                        k = shape_of(e[1])
                        if k:
                            att[r["f"]].add((k, "damage"))
                    elif e[0] == "blocked":
                        k = shape_of(e[1])
                        if k and isinstance(e[4], int) and isinstance(e[5], int):
                            for f in range(e[4], e[5] + 1):
                                att[f].add((k, "blocked:" + str(e[2])))
                    elif e[0] == "hp":
                        k = shape_of(e[2])
                        if k:
                            att[r["f"]].add((k, "hp"))
            byf = {r["f"]: r for r in F}
            last_hit = None
            for i, r in enumerate(F):
                for key in ("1", "2"):
                    a = rel_verts(r, key)
                    if a is not None and len(verts[key]) < 40000:
                        verts[key].append(a)
                if any(e[0] == "hit" and e[1] == c["iid"] and "Down" in str(e[3]) for e in r["ev"]):
                    last_hit = r["f"]
                if r.get("ds") is not None and last_hit is not None and 0 <= r["f"] - last_hit <= 30:
                    iframes[(r["f"] - last_hit, r["ds"])] += 1
                g = frame_gaps(r)
                prev = byf.get(r["f"] - 1)
                gprev = frame_gaps(prev) if prev else {}
                can_hurt = (r.get("ds") == 0 and not r.get("inv") and not cs(r["cs"], "recoiling")
                            and not cs(r["cs"], "parrying") and not r.get("dead"))
                kinds = att.get(r["f"], set())
                later = set().union(*(att.get(r["f"] + i, set()) for i in range(LAT + 1)))
                for key, gg in g.items():
                    for m in MODELS:
                        if gg[m] < 0:
                            overlap_n[(key, m)] += 1
                            if can_hurt:
                                hurtable[(key, m)] += 1
                                if not any(k == key for k, _ in later):
                                    overlap_free[(key, m)] += 1
                                    if len(overlap_free_ex[(key, m)]) < 12:
                                        overlap_free_ex[(key, m)].append([c["rec"], r["f"], r["st"], round(gg[m], 3)])
                for key, kind in kinds:
                    gl = [x.get(key) for x in [g, gprev] + [frame_gaps(byf[r["f"] - i]) for i in range(2, LAT + 1)
                                                            if r["f"] - i in byf]]
                    row = {"rec": c["rec"], "f": r["f"], "shape": key, "kind": kind, "st": r["st"], "ds": r.get("ds"),
                           "inv": r.get("inv"), "since_hit": None if last_hit is None else r["f"] - last_hit,
                           "clip": r.get("clip")}
                    for m in MODELS:
                        vals = [x[m] for x in gl if x]
                        row[m] = round(min(vals), 3) if vals else None
                    att_rows.append(row)
                    if key == "2" and kind == "hp":
                        hits_c2.append(row)
    # polygon rigidity
    rig = {}
    for key, L in verts.items():
        shapes = Counter(len(a) for a in L)
        n = shapes.most_common(1)[0][0]
        A = np.array([a for a in L if len(a) == n])
        med = np.median(A, axis=0)
        dev = np.abs(A - med).max(axis=(1, 2))
        rig[key] = {"n_frames": len(L), "n_verts": shapes, "median": med.round(3).tolist(),
                    "dev_p50_p99_max": [round(float(np.percentile(dev, q)), 4) for q in (50, 99, 100)]}
    # attempts without an overlap per model
    miss = {}
    for m in MODELS:
        for kind in ("hp", "damage", "blocked"):
            rows = [a for a in att_rows if a["kind"].startswith(kind)]
            bad = [a for a in rows if a[m] is None or a[m] >= 0]
            miss[f"{m}/{kind}"] = {"n": len(rows), "no_overlap": len(bad),
                                   "by_shape": Counter(a["shape"] for a in bad), "ex": bad[:8]}
    gaps = {}
    for m in MODELS:
        for kind in ("hp", "damage"):
            v = [a[m] for a in att_rows if a["kind"].startswith(kind) and a[m] is not None and a[m] >= 0]
            gaps[f"{m}/{kind}"] = [round(float(x), 3) for x in sorted(v)]
    return {"slams": n_slams, "dropped": dropped, "miss_gaps": gaps, "attempts": len(att_rows), "attempt_kinds": Counter(a["kind"] for a in att_rows),
            "attempts_by_shape": Counter(a["shape"] for a in att_rows),
            "attempts_without_overlap": miss,
            "overlap_frames": {f"{k}/{m}": v for (k, m), v in sorted(overlap_n.items())},
            "overlap_hurtable": {f"{k}/{m}": v for (k, m), v in sorted(hurtable.items())},
            "overlap_hurtable_no_attempt": {f"{k}/{m}": v for (k, m), v in sorted(overlap_free.items())},
            "overlap_hurtable_no_attempt_ex": {f"{k}/{m}": v for (k, m), v in sorted(overlap_free_ex.items())},
            "c2_hp_hits": hits_c2, "rigidity": rig,
            "iframe_counter_after_hit": sorted([[d, ds, n] for (d, ds), n in iframes.items()])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slams", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    res = analyse(a.slams)
    a.out.write_text(json.dumps(res, indent=1, default=lambda o: dict(o) if isinstance(o, Counter) else str(o)),
                     encoding="utf-8")
    for k in ("slams", "dropped", "attempts", "attempt_kinds", "attempts_by_shape", "overlap_hurtable",
              "overlap_hurtable_no_attempt"):
        print(k, res[k])
    for k, v in res["attempts_without_overlap"].items():
        print("no overlap", k, v["n"], v["no_overlap"], dict(v["by_shape"]))
    for k, v in res["rigidity"].items():
        print("rigid", k, v["n_frames"], dict(v["n_verts"]), v["dev_p50_p99_max"])
    print("c2 hp hits", len(res["c2_hp_hits"]))
    for k, v in res["miss_gaps"].items():
        print("miss gaps", k, v[:40])
    return 0


if __name__ == "__main__":
    sys.exit(main())
