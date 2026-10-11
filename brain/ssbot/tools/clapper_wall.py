"""The Clapper and the wall top (the person 2026-10-11, live session 20261011_051105: "during the Clapper's big rune
antic the damage range shown is too large: when I cling at the top of the wall I am inside it, but that spot can never
be hit by any Clapper attack"). docs/facts/1.0.30000/forum.md sec. 42.

  frames  the person's frames with a Clapper antic (Cast Slam Antic / 2 = the jump cast with the rune slam, Spell Antic
          / Cast 1 / 2 = the rune bombs, Jump Antic / Jump Aim) while the hero is at a wall top: which overlay layer
          covers the hero's box (the range estimate at every k of the overlay, the swept path 0-36, the aim zone by
          class) and the aim reader's class at the HeroBox centre; --npz-dir reads other aim tables (before / after)
  truth   every Forum recording (R0 dev / fresh, R1c, the person's sessions): how high and how close to the walls any
          Clapper damage collider ever reached (the body and slam colliders, the rune slam circle, the rune bombs), the
          gap to the wall-top cling box, and the hero hits by a Clapper while the hero was at a wall top
  png     the person's frames rendered like the live overlay (range, all k, swept, aim) over the recorded video

    cd <checkout>/brain
    ../scripts/uv.cmd run python -m ssbot.tools.clapper_wall frames --json C:/ssbot/data/m2_forum_aimics/clapper_wall/before.json
    ../scripts/uv.cmd run python -m ssbot.tools.clapper_wall truth --json C:/ssbot/data/m2_forum_aimics/clapper_wall/truth.json
    ../scripts/uv.cmd run python -m ssbot.tools.clapper_wall png --out C:/ssbot/data/m2_forum_aimics/clapper_wall/after
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

CLAPPER = "Song Heavy Sentry"
WALL_L, WALL_R = 14.01, 48.99
SESSION = Path(r"C:\ssbot\data\human\20261011_051105")
ATTEMPT = 1
OUT = Path(r"C:\ssbot\data\m2_forum_aimics\clapper_wall")
PERSON_ROOTS = (OUT / "person_cache", Path(r"C:\ssbot\data\m2_forum_are\person_cache"))
ANTICS = ("Cast Slam Antic", "Cast Slam Antic 2", "Spell Antic", "Cast 1", "Cast 2", "Jump Antic", "Jump Aim")
# HeroBoxWallSlide (forum.md sec. 8): 0.8757 x 1.2805 at (+-0.2101, -0.2755) from the transform, into the arena
WS_W, WS_H, WS_DX, WS_DY = 0.8757, 1.2805, 0.2101, -0.2755
TOP_Y = 10.5                     # the hero transform this high next to a wall = "at the wall top"
NEAR_WALL = 1.0                  # transform within this of a wall face
HAZ = {"rune slam": 14.374, "rune bomb small": 4.332}     # circle hazards by their AABB width (attack_range clapper)
HAZ_Y = (2.0, 5.5)               # ... and their centre height (floor + 0.33 / + 0.65): other damagers share widths
CLING_HIGH = 11.8                # a cling this high (transform y) is above the rune slam's reach (its top 10.53)


def at_wall_top(hx: float, hy: float) -> bool:
    return min(hx - WALL_L, WALL_R - hx) <= NEAR_WALL and hy >= TOP_Y


def cling_box(hx: float, hy: float) -> tuple:
    """The wall-slide HeroBox of a hero clinging at (hx, hy) (into the arena from the nearer wall)."""
    sx = 1.0 if hx < 0.5 * (WALL_L + WALL_R) else -1.0
    cx, cy = hx + sx * WS_DX, hy + WS_DY
    return (cx - WS_W / 2, cy - WS_H / 2, cx + WS_W / 2, cy + WS_H / 2)


def normal_box(hx: float, hy: float) -> tuple:
    from ssbot.combat.attack_range import HERO_DY, HERO_HALF
    return (hx - HERO_HALF[0], hy + HERO_DY - HERO_HALF[1], hx + HERO_HALF[0], hy + HERO_DY + HERO_HALF[1])


def polys_hit_box(polys, box) -> bool:
    """Any polygon overlapping the box (a 12 x 16 lattice of the box's points)."""
    import cv2
    x0, y0, x1, y1 = box
    xs, ys = np.meshgrid(np.linspace(x0, x1, 12), np.linspace(y0, y1, 16))
    pts = np.stack([xs.ravel(), ys.ravel()], 1)
    for p in polys:
        if len(p) < 3:
            continue
        c = np.asarray(p, np.float32).reshape(-1, 1, 2)
        lo, hi = c.reshape(-1, 2).min(0), c.reshape(-1, 2).max(0)
        if hi[0] < x0 or lo[0] > x1 or hi[1] < y0 or lo[1] > y1:
            continue
        if any(cv2.pointPolygonTest(c, (float(a), float(b)), False) >= 0 for a, b in pts):
            return True
    return False


def rect_gaps(b: np.ndarray, r) -> np.ndarray:
    """Euclidean gaps of AABBs b [n, 4] to the box r (0 = touching or overlapping)."""
    dx = np.maximum(np.maximum(b[:, 0] - r[2], r[0] - b[:, 2]), 0.0)
    dy = np.maximum(np.maximum(b[:, 1] - r[3], r[1] - b[:, 3]), 0.0)
    return np.hypot(dx, dy)


def circle_gaps(cx: np.ndarray, cy: np.ndarray, rad: np.ndarray, r) -> np.ndarray:
    """Gaps of circles to the box r (<= 0: overlapping)."""
    dx = np.maximum(np.maximum(r[0] - cx, cx - r[2]), 0.0)
    dy = np.maximum(np.maximum(r[1] - cy, cy - r[3]), 0.0)
    return np.hypot(dx, dy) - rad


# ---------------------------------------------------------------------------------------------- frames
def _clapper_now(trk) -> list:
    from ssbot.combat.attack_range import _first_state
    return [(iid, _first_state(e)[0], e, inst) for iid, (tk, e, inst) in trk.now.items() if tk == CLAPPER]


def cmd_frames(args) -> dict:
    from ssbot.combat.attack_range import RangeTracker, contours
    from ssbot.tools import aim_zones as az
    from ssbot.tools import zone_overlay as zo
    if args.npz_dir:
        _readers_at(args.npz_dir)
    _, _, states = zo.attempt_states(Path(args.session), args.attempt)
    trk = RangeTracker()
    trk.reset()
    by = defaultdict(Counter)
    rows = []
    for s in states:
        trk.feed(s)
        h = s.get("hero") or {}
        p = h.get("pos")
        if not p or s["f"] % args.every:
            continue
        hx, hy = float(p[0]), float(p[1])
        if not at_wall_top(hx, hy):
            continue
        cl = [c for c in _clapper_now(trk) if c[1] in ANTICS]
        if not cl:
            continue
        clip = (h.get("anim") or {}).get("clip")
        box = cling_box(hx, hy) if clip in ("Wall Cling", "Wall Slide") else normal_box(hx, hy)
        ests, swept = trk.ladder(zo.KS, max(zo.KS))
        aims = {iid: (polys, lab) for iid, polys, lab, _ in zo.aim_zones_of(trk)}
        for iid, st, e, inst in cl:
            cov = [f"k{k}" for k in zo.KS for est in ests[k] if est.iid == iid and polys_hit_box(contours(est.raw), box)]
            if iid in swept and polys_hit_box(contours(swept[iid]), box):
                cov.append("swept")
            polys, lab = aims.get(iid, ({}, None))
            cov += [f"aim:{cls}" for cls, ps in polys.items() if polys_hit_box(ps, box)]
            name = az.pending_move(CLAPPER, st)
            if st == "Jump Aim" and inst is not None:
                name = inst.fam
            ex, ey = float(e["pos"][0]), float(e["pos"][1])
            code = None
            if name in az.readers():
                code = az.readers()[name].inescapable((0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])), (ex, ey),
                                                      1 if hx >= ex else -1)
            for c in cov or ["none"]:
                by[st][c] += 1
            rows.append(dict(f_raw=int(s["_f_raw"]), f=int(s["f"]), iid=int(iid), st=st,
                             tin=round(float(((e.get("fsms") or [{}])[0]).get("t") or 0.0), 2), ex=round(ex, 2),
                             ey=round(ey, 2), hx=round(hx, 2), hy=round(hy, 2), clip=clip, cov=cov, aim_move=name,
                             aim_centre_class=code, aim_label=lab))
    res = {"session": str(args.session), "attempt": args.attempt, "every": args.every,
           "npz_dir": args.npz_dir, "by_state": {k: dict(v) for k, v in by.items()}, "rows": rows}
    for k, v in by.items():
        print(k, dict(v), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=0), "utf-8")
    return res


def _readers_at(npz_dir: str) -> None:
    """Points tools.aim_zones.readers() (and so the overlay's aim layer) at another table directory."""
    from ssbot.tools import aim_zones as az
    orig = az.readers
    az.readers = lambda root=None: orig(root or npz_dir)


# ---------------------------------------------------------------------------------------------- truth
def _src_group(source: str) -> str:
    return "rune slam" if "rune slam" in source else "rune bomb" if "rune bomb" in source else "body/slam"


def _y_band(hy: float) -> str:
    return "<11.5" if hy < 11.5 else "11.5-12.5" if hy < 12.5 else ">=12.5"


def _cache_sets(names) -> list:
    from ssbot.tools.attack_range_build import SETS
    files = []
    for n in names:
        if n == "person":
            for r in PERSON_ROOTS:
                files += [("person", f) for f in sorted(r.glob("*.npz"))]
        elif n == "r1c":
            files += [("r1c", f) for f in sorted(Path(r"C:\ssbot\data\m2_forum_r1c\cache").glob("*.npz"))]
        else:
            files += [(n, f) for d in SETS[n] for f in sorted(d.glob("*.npz"))]
    return files


def cmd_truth(args) -> dict:
    """Per collider kind: the highest top, the closest approach to each wall face above a height, the smallest gap to
    the wall-top cling box (the person's cling y 12.2 and the highest measured cling 13.6) and its frames; the hero
    hits from a Clapper with the hero at a wall top; the hero's wall-top frames with a Clapper alive."""
    from ssbot.combat.attack_range import MW_SRC_BIT
    from ssbot.knowledge.forum_cache import load_cache
    boxes = {f"{side}{y}": cling_box(x, y) for side, x in (("L", 14.27), ("R", 48.73)) for y in (11.28, 12.2, 13.6)}
    K = {}

    def kind(name: str) -> dict:
        return K.setdefault(name, {"frames": 0, "top_max": -1e9, "top_at": None, "wall_gap_above_10": 1e9,
                                   "wall_gap_at": None, "gap": {b: 1e9 for b in boxes}, "gap_at": {},
                                   "overlap_frames": Counter(), "overlap_states": defaultdict(Counter)})
    hits, top_frames, clap_frames, cling_frames, seen = [], 0, 0, 0, Counter()
    for src, f in _cache_sets(args.sets):
        c = load_cache(f)
        types = list(c["types"])
        if CLAPPER not in types:
            continue
        seen[src] += 1
        tk = types.index(CLAPPER)
        e_tk = c["e_tk"]
        ei = c["c_ei"]
        box = c["c_box"].astype(np.float64)
        fi_of = c["e_fi"][ei]
        w = box[:, 2] - box[:, 0]
        hurt = (c["c_dealt"] > 0) | ((c["c_dealt"] == 0) & (c["c_eff"] != 0) & ((c["e_src"][ei] & MW_SRC_BIT) != 0))
        own = (e_tk[ei] == tk) & hurt
        groups = {"body+slam": np.nonzero(own)[0]}
        dmg = types.index("damager") if "damager" in types else -2
        cyy = 0.5 * (box[:, 1] + box[:, 3])
        for hz, bw in HAZ.items():          # the pooled "damager" circles at the floor (the Clapper's rune hazards)
            groups[hz] = np.nonzero((np.abs(w - bw) < 0.03) & (c["c_dealt"] > 0) & (e_tk[ei] == dmg)
                                    & (cyy > HAZ_Y[0]) & (cyy < HAZ_Y[1]))[0]
        fid = str(c["meta"].get("id", f.stem))
        for name, rows in groups.items():
            if not len(rows):
                continue
            k = kind(name)
            k["frames"] += len(np.unique(fi_of[rows]))
            b = box[rows]
            circ = name in HAZ
            if circ:
                cx, cy, r = 0.5 * (b[:, 0] + b[:, 2]), 0.5 * (b[:, 1] + b[:, 3]), 0.5 * (b[:, 2] - b[:, 0])
                top = cy + r
            else:
                top = b[:, 3]
            i = int(np.argmax(top))
            if top[i] > k["top_max"]:
                k["top_max"] = round(float(top[i]), 3)
                k["top_at"] = [fid, int(c["f"][fi_of[rows[i]]]), [round(float(v), 2) for v in b[i]]]
            # how close to either wall face above y 10 (a circle: its chord at max(10, its centre))
            up = np.nonzero(top > 10.0)[0]
            if len(up):
                if circ:
                    yy = np.maximum(10.0, cy[up])
                    half = np.sqrt(np.maximum(r[up] ** 2 - (yy - cy[up]) ** 2, 0.0))
                    x0, x1 = cx[up] - half, cx[up] + half
                else:
                    x0, x1 = b[up, 0], b[up, 2]
                g = np.minimum(x0 - WALL_L, WALL_R - x1)
                j = int(np.argmin(g))
                if g[j] < k["wall_gap_above_10"]:
                    k["wall_gap_above_10"] = round(float(g[j]), 3)
                    k["wall_gap_at"] = [fid, int(c["f"][fi_of[rows[up[j]]]]), [round(float(v), 2) for v in b[up[j]]]]
            for bn, bb in boxes.items():
                g = circle_gaps(cx, cy, r, bb) if circ else rect_gaps(b, bb)
                j = int(np.argmin(g))
                if g[j] < k["gap"][bn]:
                    k["gap"][bn] = round(float(g[j]), 3)
                    k["gap_at"][bn] = [fid, int(c["f"][fi_of[rows[j]]]), [round(float(v), 2) for v in b[j]]]
                k["overlap_frames"][bn] += int(len(np.unique(fi_of[rows[g <= 0]])))
                if not circ and (g <= 0).any():          # the owner's Control state at the overlapping frames
                    for x in np.unique(np.stack([fi_of[rows[g <= 0]], c["e_st"][ei[rows[g <= 0]]]], 1), axis=0):
                        k["overlap_states"][bn][str(c["states"][x[1]]) if x[1] >= 0 else "?"] += 1
        # the hero at a wall top (with a Clapper alive) and the Clapper's hits on it
        hx, hy = c["hx"].astype(np.float64), c["hy"].astype(np.float64)
        top_mask = (np.minimum(hx - WALL_L, WALL_R - hx) <= NEAR_WALL) & (hy >= TOP_Y)
        alive = np.zeros(len(hx), bool)
        alive[c["e_fi"][(e_tk == tk) & (c["e_hidden"] == 0)]] = True
        top_frames += int((top_mask & alive).sum())
        clap_frames += int(alive.sum())
        fidx = {int(x): i for i, x in enumerate(c["f"])}
        clips = c["names"]
        cl_id = [i for i, n in enumerate(clips) if str(n) == "Wall Cling"]
        high_cling = top_mask & (hy >= CLING_HIGH) & np.isin(c["hclip"], cl_id)
        cling_frames += int((high_cling & alive).sum())
        cst = defaultdict(set)                  # frame -> the Clappers' Control states
        for r in np.nonzero(e_tk == tk)[0]:
            cst[int(c["e_fi"][r])].add(int(c["e_st"][r]))
        for ev in c["events"]:
            if ev[1] not in ("damage", "damage_blocked") or ev[2].get("hazard") != "ENEMY":
                continue
            so = str(ev[2].get("source", ""))
            if "Heavy Sentry" not in so and "rune" not in so:
                continue
            i = fidx.get(int(ev[2].get("first_f", ev[0])), fidx.get(int(ev[0])))
            if i is None:
                continue
            row = {"src": src, "fight": fid, "f": int(c["f"][i]), "kind": ev[1], "source": so,
                   "hx": round(float(hx[i]), 2), "hy": round(float(hy[i]), 2),
                   "clip": str(clips[c["hclip"][i]]) if c["hclip"][i] >= 0 else None, "at_wall_top": bool(top_mask[i]),
                   "high_cling": bool(high_cling[i]),
                   "clapper_states": sorted(str(c["states"][s]) for s in cst.get(i, ()) if s >= 0)}
            hits.append(row)
    res = {"sets": args.sets, "fights_with_clapper": dict(seen), "cling_boxes": boxes,
           "kinds": {n: {**k, "overlap_frames": dict(k["overlap_frames"]),
                         "overlap_states": {b: dict(v) for b, v in k["overlap_states"].items()}} for n, k in K.items()},
           "hero_wall_top_frames_with_clapper": top_frames, "clapper_frames": clap_frames,
           "clapper_hits": len(hits), "clapper_hits_by_kind": dict(Counter(h["kind"] for h in hits)),
           "hero_high_cling_frames_with_clapper": cling_frames,
           "wall_top_hits_by": dict(Counter(
               f"{_src_group(h['source'])} | {h['kind']} | y {_y_band(h['hy'])} | "
               f"{h['clip'] if h['clip'] in ('Wall Cling', 'Wall Slide') else 'other'}"
               for h in hits if h["at_wall_top"]).most_common()),
           "high_cling_hits": [h for h in hits if h["high_cling"]],
           "clapper_hits_at_wall_top": [h for h in hits if h["at_wall_top"]],
           "clapper_hits_hero_y_max": sorted(hits, key=lambda h: -h["hy"])[:10]}
    print(json.dumps({k: v for k, v in res.items() if k not in ("clapper_hits_hero_y_max", "clapper_hits_at_wall_top")},
                     indent=1)[:8000])
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=1), "utf-8")
    return res


# ---------------------------------------------------------------------------------------------- png
def cmd_png(args) -> None:
    """The overlay as the person saw it (range+red mode, all k, swept, aim) over the recorded frames of `frames`."""
    import cv2
    from ssbot.tools import zone_overlay as zo
    if args.npz_dir:
        _readers_at(args.npz_dir)
    want = {int(x) for x in args.frames}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    session = Path(args.session)
    _, terrain, states = zo.attempt_states(session, args.attempt)
    eng = _RangeEngine()
    view = zo.View(mode="range+red", all_k=True, swept=True, aim=True)
    vidx = zo._video_index(session)
    vf = zo.VideoFrames(session)
    n = 0
    for s in states:
        eng.feed(s)
        fr_raw = int(s["_f_raw"])
        if fr_raw not in want:
            continue
        fr = eng.compute(view)
        vi = vidx.get(fr_raw)
        img = vf.get(vi) if vi is not None else None
        if img is None:
            continue
        lines = zo.legend_lines(fr, view, args.tag, f"f {fr_raw}")
        ov = zo.render(fr, zo.Grid(zo.CELL), (img.shape[1], img.shape[0]), view, legend=lines)
        cv2.imwrite(str(out / f"{session.name}_a{args.attempt}_f{fr_raw}_{args.tag}.png"), zo.composite(img, ov))
        n += 1
    vf.close()
    print(json.dumps({"pngs": n, "out": str(out)}))


class _RangeEngine:
    """The range-only part of zone_overlay.ZoneEngine (no planner forecast): what the live overlay draws in the
    range modes."""

    def __init__(self):
        from ssbot.combat.attack_range import RangeTracker
        from ssbot.tools import zone_overlay as zo
        self.rng = RangeTracker()
        self.rng.reset()
        self.names: dict = {}
        self.counts: dict = {}
        self.raw = None
        self._zo = zo

    def feed(self, s: dict) -> None:
        self.rng.feed(s)
        self.raw = s
        self._zo.ZoneEngine._names_of(self, s)

    def compute(self, view) -> dict:
        zo = self._zo
        from ssbot.combat.attack_range import _first_state
        rng = zo.ZoneEngine.range_layer(self, view.range_ks(), view.range_sweep(), not view.all_k)
        rng["aim"] = zo.ZoneEngine.aim_layer(self)
        ens = []
        for iid, name in self.names.items():
            t = self.rng.now.get(iid)
            if t is None:
                continue
            p = t[1].get("pos")
            if p:
                ens.append((iid, name, _first_state(t[1])[0], (float(p[0]), float(p[1])), self.color(iid)))
        s = self.raw or {}
        return {"f": s.get("f"), "f_raw": s.get("_f_raw"), "hero": zo.ZoneEngine.hero(self), "ks": tuple(zo.KS),
                "support": {}, "ycom": {}, "yns": {}, "info": {}, "cols": zo.damage_colliders(s), "enemies": ens,
                "cam": s.get("cam"), **rng}

    def name(self, iid: int) -> str:
        return self.names.get(int(iid), f"#{iid}")

    def color(self, iid: int) -> tuple:
        order = list(self.names)
        return self._zo.ENEMY_COLORS[order.index(iid) % len(self._zo.ENEMY_COLORS)] if iid in self.names else \
            (200, 200, 200)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("frames")
    a.add_argument("--session", default=str(SESSION))
    a.add_argument("--attempt", type=int, default=ATTEMPT)
    a.add_argument("--every", type=int, default=3)
    a.add_argument("--npz-dir")
    a.add_argument("--json")
    b = sub.add_parser("truth")
    b.add_argument("--sets", nargs="+", default=["dev", "fresh", "r1c", "person"])
    b.add_argument("--json")
    c = sub.add_parser("png")
    c.add_argument("--session", default=str(SESSION))
    c.add_argument("--attempt", type=int, default=ATTEMPT)
    c.add_argument("--frames", nargs="+", required=True)
    c.add_argument("--npz-dir")
    c.add_argument("--tag", default="overlay")
    c.add_argument("--out", required=True)
    args = ap.parse_args()
    {"frames": cmd_frames, "truth": cmd_truth, "png": cmd_png}[args.cmd](args)


if __name__ == "__main__":
    main()
