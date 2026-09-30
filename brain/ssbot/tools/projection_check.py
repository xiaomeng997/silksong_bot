"""Oracle collider projection vs DebugMod's hitbox display (DESIGN §3.1.3 calibration; M1 exit "projection IoU >= 0.95,
vertex error <= 1.5 px"): the image and geometry half of ssbot.probes.m1_projection, free of IPC and capture so it can
be tested on synthetic images.

What DebugMod draws (oracle/src/Train/DebugModBridge.cs, hitbox section; REF\\Silksong.DebugMod\\Hitbox): in OnGUI, after
rendering, every collider of its dictionary that is enabled and in view, as Camera.main.WorldToScreenPoint of the
authored outline with each vertex rounded to an integer GUI pixel, joined by antialiased lines (a quad 3 * LineWidth wide
whose alpha falls linearly from 1 on the centreline to 0 at LineWidth, drawn twice), in the HitboxType's colour
(PALETTE). The camera pose is the end-of-frame one, without the shake the image was rendered with.

Coordinates: "image" pixels have their origin at the top-left corner of the client area, x right, y down, and pixel
(row i, col j) covers [j, j+1] x [i, i+1]; projector.project, DebugMod's GUI space and the capture agree on this.
OpenCV draws with pixel centres on integers, so cv = image - 0.5.

For one captured frame (hitboxes on) and the STATE of that frame:
  1. match_sample pairs each collider DebugMod drew (RPC projection.sample, source debugmod) with the oracle's own label
     polygon: TERRAIN solids (by collider id), STATE ents colliders (float-identical outline "o"), TERRAIN hazards (id),
     the STATE hero box (Knight). Types the oracle does not label (Attack, Gate, Trigger, ...) are left out. Each
     pair records how far the label's world outline is from the one DebugMod draws (Poly.offset): up to float noise
     the same shape, or a label that is another shape (the hero box is Collider2D.bounds, possibly with Box2D's
     contact skin; an ents box includes the edgeRadius DebugMod leaves out; TERRAIN moved since the room dump), whose
     IoU then measures that difference as well as the projection.
  2. segment finds DebugMod's line pixels by colour, with the palette measured on the capture along the outlines
     DebugMod says it drew, and only near those outlines (NEAR_PX), so scene pixels of a palette colour elsewhere
     (Hornet's red cloak is close to "Enemy") are not taken for lines.
  3. evaluate, per polygon (all regions are pixel sets, a pixel counting when its centre is inside):
     D = DebugMod's outline filled, from the capture: the cells (connected non-line pixels) holding seeds deep inside
         the oracle polygon, plus the line pixels on their side of the line, so D ends on DebugMod's centreline;
     O = the oracle polygon projected with the STATE camera moved to the end-of-frame pose DebugMod draws with;
     M = DebugMod's own polygon from the vertices it reports (rounded like it rounds them).
     IoU(D, O) is the M1 number; IoU(D, M) checks the capture / crop / segmentation chain, IoU(M, O) the geometry.

Residual differences with everything right: DebugMod rounds each vertex to a whole pixel (up to 0.5 px per vertex,
worst on small polygons), strokes circles as 16+ chords (a circle under 64 px radius is a 16-gon: IoU 0.974 against the
true circle) and never draws a box's edgeRadius that the ents outline includes; which side of the centreline an
antialiased pixel falls on depends on the background colour (about +-0.5 px along an edge).
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import cv2
import numpy as np

from ssbot.tools import projector

# DebugMod HitboxRender.HitboxType colours (Unity Color * 255, rounded), RGB.
PALETTE: dict[str, tuple[int, int, int]] = {
    "Knight": (255, 235, 4),          # Color.yellow
    "Enemy": (204, 0, 0),
    "Attack": (0, 255, 255),          # Color.cyan
    "Terrain": (0, 204, 0),
    "NonSliderTerrain": (0, 204, 153),
    "Trigger": (128, 128, 255),
    "Breakable": (255, 191, 204),
    "Gate": (0, 0, 128),
    "HazardRespawn": (128, 0, 128),
    "NonMantleRegion": (0, 77, 0),
    "AlertRegion": (230, 153, 102),
    "Other": (179, 179, 179),
}
# Types with an oracle label polygon: the hero box, threats (ents / TERRAIN hazards) and terrain (TERRAIN solids).
LABELLED = ("Knight", "Enemy", "Terrain", "NonSliderTerrain")
FILL_KINDS = ("box", "poly", "circle")

IOU_MIN = 0.95          # M1: per-polygon IoU p5
VERTEX_P99_MAX = 1.5    # M1: vertex error p99, pixels
NEAR_PX = 4             # line pixels are looked for this far (Chebyshev) from the outlines DebugMod reports drawing
SHIFT = 4               # fixed-point bits for OpenCV drawing


# ---- Unity screen points and DebugMod's GUI points ---------------------------------------------------------------

def unity_to_image(s: Sequence[float], cam_info: dict) -> np.ndarray:
    """Camera.WorldToScreenPoint results (flat x, y pairs; pixels of the camera's target, bottom-left origin) -> image
    pixels the way projector.project places them: position in the pixel rect -> normalized rect -> screen. Without a
    render texture this is (x, screen_h - y)."""
    p = np.asarray(s, dtype=np.float64).reshape(-1, 2)
    px, py, pw, ph = cam_info["pixel_rect"]
    rx, ry, rw, rh = cam_info["rect"]
    sw, sh = cam_info["screen"]
    u = (p[:, 0] - px) / pw
    t = (p[:, 1] - py) / ph
    return np.stack([(rx + u * rw) * sw, sh - (ry + t * rh) * sh], axis=1)


def debugmod_gui(e: Sequence[float], screen_h: float) -> np.ndarray:
    """Where DebugMod draws the vertices: HitboxRender.LocalToScreenPoint = (round(x), round(Screen.height - y)) with
    Math.Round's half-to-even, like numpy. Only image pixels while the camera renders to the screen (no "rt")."""
    p = np.asarray(e, dtype=np.float64).reshape(-1, 2)
    return np.stack([np.round(p[:, 0]), np.round(np.float32(screen_h) - p[:, 1].astype(np.float32))], axis=1)


def dm_outline(col: dict, screen_h: float) -> tuple[np.ndarray, bool]:
    """(GUI vertices, closed) of one sampled collider as DebugMod draws it. Circles become the polygon DebugMod's
    Drawing.DrawCircle strokes around the rounded centre with radius round(|right - centre|)."""
    gui = debugmod_gui(col["e"], screen_h)
    if col["kind"] == "circle":
        return dm_circle(gui[0], float(np.round(np.hypot(*(gui[1] - gui[0]))))), True
    return gui, bool(col["closed"])


def dm_circle(centre: Sequence[float], radius: float) -> np.ndarray:
    """Drawing.DrawCircle: four cubic Bezier quarters (tangent length 0.5519 r), clamp(r // 16, 4, 32) segments each."""
    c = np.asarray(centre, dtype=np.float64)
    r = float(radius)
    seg = int(min(32, max(4, int(r) // 16)))
    rh = r * 0.551915024494
    quarters = (  # start, start tangent, end, end tangent (GUI space, y down)
        (c + (0, -r), c + (rh, -r), c + (r, 0), c + (r, -rh)),
        (c + (r, 0), c + (r, rh), c + (0, r), c + (rh, r)),
        (c + (0, r), c + (-rh, r), c + (-r, 0), c + (-r, rh)),
        (c + (-r, 0), c + (-r, -rh), c + (0, -r), c + (-rh, -r)),
    )
    t = np.arange(seg)[:, None] / seg
    pts = [(1 - t) ** 3 * s + 3 * (1 - t) ** 2 * t * st + 3 * (1 - t) * t * t * et + t ** 3 * e for s, st, e, et in quarters]
    return np.concatenate(pts)


# ---- camera poses and the vertex check -----------------------------------------------------------------------------

def translate(dx: float, dy: float, dz: float = 0.0) -> np.ndarray:
    t = np.eye(4)
    t[:3, 3] = (dx, dy, dz)
    return t


def eof_pose(cam: dict) -> dict:
    """STATE "cam" moved from the render-time pose (src 1: shake included) to the end-of-frame pose DebugMod's OnGUI
    projects with. The shake moves the camera by shake = pos - pos_eof, so V_eof(x) = V(x + shake)."""
    shake = cam.get("shake") or (0.0, 0.0)
    if cam.get("src") != 1 or not any(shake):
        return cam
    v = projector.mat4(cam["V"]) @ translate(shake[0], shake[1])
    return dict(cam, V=list(v.flatten(order="F")))


def vertex_errors(sample: dict, cam: dict, pose: str = "render") -> np.ndarray:
    """Per-vertex distance in image pixels between projector.py on the STATE camera of sample["frame"] and Unity's own
    WorldToScreenPoint of the same world points. "render": "s" (main camera in onPreRender, the V/P STATE carries when
    cam src is 1) vs the STATE camera as is. "eof": "e" (Camera.main at end of frame, DebugMod's pose) vs eof_pose."""
    if pose not in ("render", "eof"):
        raise ValueError(pose)
    key, info, use = ("s", sample["cam"], cam) if pose == "render" else ("e", sample["dm_cam"], eof_pose(cam))
    errs = []
    for c in sample["cols"]:
        s = c.get(key)
        if s is None:
            continue
        w = c["w"] if pose == "render" else c.get("we", c["w"])
        ours, ok = projector.project_cam(np.asarray(w, dtype=np.float64).reshape(-1, 2), use)
        theirs = unity_to_image(s, info)
        errs.append(np.hypot(*(ours - theirs).T)[ok])
    return np.concatenate(errs) if errs else np.zeros(0)


def matrices_match(sample_cam: dict, state_cam: dict) -> float:
    """Largest difference between the sample's render-time V/P and the STATE's (0 when the frames line up)."""
    return float(max(np.max(np.abs(np.asarray(sample_cam[k]) - np.asarray(state_cam[k]))) for k in ("V", "P")))


def summarize(xs: Iterable[float]) -> dict:
    a = np.asarray(list(xs), dtype=np.float64)
    if a.size == 0:
        return {"n": 0}
    return {"n": int(a.size), "p5": float(np.percentile(a, 5)), "p50": float(np.percentile(a, 50)),
            "p99": float(np.percentile(a, 99)), "min": float(a.min()), "max": float(a.max()), "mean": float(a.mean())}


# ---- oracle label polygons for what DebugMod drew ----------------------------------------------------------------

@dataclass
class Poly:
    """One collider DebugMod drew, paired with the oracle's label for it."""
    key: str                    # "<collider id>/<path>"
    type: str                   # DebugMod HitboxType
    kind: str                   # box | poly | circle
    src: str                    # ents | hazard | terrain | hero
    world: np.ndarray           # (n, 2) oracle outline in world units; circles: (1, 2) centre
    radius: float = 0.0         # circle radius, world units
    ref: tuple = ()             # ("ents", iid, k) | ("terrain" | "hazard", id, shape) | ("hero",)
    stale: float = 0.0          # world distance between DebugMod's outline and the label's (TERRAIN is a room dump)
    dm: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))   # DebugMod's GUI outline (dm_outline)
    offset: float = 0.0         # label_offset: how far the label's shape is from the drawn one, any source (world units)


STALE_MAX = 0.05  # world units: a label further from DebugMod's outline than this is out of date, not a projection error
# World units: a label within this of DebugMod's drawn outline is the drawn shape (float noise is ~1e-5; 1e-3 u is
# about 0.06 px at 1080p, ~60 px/u). Only those labels make the IoU gate a test of the projection alone.
LABEL_EXACT = 1e-3


def match_sample(sample: dict, state: dict, terrain=None) -> tuple[list[Poly], Counter, Counter]:
    """Pair the drawn colliders of a debugmod-source sample with oracle labels (see the module docstring). Returns
    (polys, unmatched by type, skipped by reason). terrain: a decoded ssbot.oracle.messages.Terrain of the room."""
    polys: list[Poly] = []
    unmatched: Counter = Counter()
    skipped: Counter = Counter()
    screen_h = sample["dm_cam"]["screen"][1]
    ents = [(e["iid"], k, c) for e in state.get("ents") or () for k, c in enumerate(e.get("colliders") or ())]
    solids = {s.id: s for s in terrain.solids} if terrain is not None else {}
    hazards = {h.id: h for h in terrain.hazards} if terrain is not None else {}
    for c in sample["cols"]:
        t = c.get("type")
        if t not in LABELLED:
            skipped[f"type {t}"] += 1
            continue
        if not c.get("closed") or c["kind"] not in FILL_KINDS:
            skipped[f"kind {c['kind']}"] += 1
            continue
        if t == "Knight":
            p = _hero_poly(c, state.get("hero"))
        elif t == "Enemy":
            p = _ents_poly(c, ents) or _terrain_poly(c, hazards, "hazard")
        else:
            p = _terrain_poly(c, solids, "terrain") or _ents_poly(c, ents)
        if p is None:
            unmatched[t] += 1
            continue
        p.key, p.type = f"{c['id']}/{c['path']}", t
        p.dm, _ = dm_outline(c, screen_h)
        p.offset = label_offset(p, c)
        polys.append(p)
    return polys, unmatched, skipped


def label_offset(p: Poly, c: dict) -> float:
    """World distance between the outline DebugMod draws for sampled collider c ("w") and the label p in the same
    frame: the largest distance from a drawn vertex to the nearest label vertex; circles: centre distance plus the
    radius difference. Above LABEL_EXACT the label is another shape than the drawn one."""
    w = np.asarray(c["w"], dtype=np.float64).reshape(-1, 2)
    if p.kind == "circle":
        return float(np.hypot(*(p.world[0] - w[0])) + abs(p.radius - np.hypot(*(w[1] - w[0]))))
    if len(p.world) != len(w):
        return math.inf
    return float(np.max(np.min(np.linalg.norm(w[:, None] - p.world[None], axis=2), axis=1)))


def _ents_poly(c: dict, ents: list) -> Poly | None:
    o = np.asarray(c["o"], dtype=np.float64)
    for iid, k, ec in ents:
        v = ec.get("verts_world") or ()
        if ec.get("kind") != c["kind"] or len(v) != len(o) or not np.allclose(v, o, atol=1e-4):
            continue
        pts = np.asarray(v, dtype=np.float64).reshape(-1, 2)
        if c["kind"] == "circle":
            return Poly("", "", "circle", "ents", pts.mean(axis=0)[None], float(ec.get("r", c.get("r", 0.0))), ("ents", iid, k))
        return Poly("", "", c["kind"], "ents", pts, 0.0, ("ents", iid, k))
    return None


def _terrain_poly(c: dict, table: dict, src: str) -> Poly | None:
    item = table.get(c["id"])
    if item is None:
        return None
    w = np.asarray(c["w"], dtype=np.float64).reshape(-1, 2)
    best = None
    for i, sh in enumerate(item.shapes):
        if sh.kind != c["kind"]:
            continue
        v = np.asarray(sh.verts, dtype=np.float64)
        if c["kind"] == "circle":
            d = float(np.hypot(*(v[0] - w[0])))
        elif len(v) != len(w):
            continue
        else:
            # Same corners, maybe another order (TERRAIN boxes start bottom-left, DebugMod's top-left).
            d = float(np.max(np.min(np.linalg.norm(w[:, None] - v[None], axis=2), axis=1)))
        if best is None or d < best[0]:
            best = (d, i, v, sh.radius)
    if best is None:
        return None
    d, i, v, r = best
    if c["kind"] == "circle":
        return Poly("", "", "circle", src, v[:1], float(r), (src, item.id, i), d)
    return Poly("", "", c["kind"], src, v, 0.0, (src, item.id, i), d)


def _hero_poly(c: dict, hero: dict | None) -> Poly | None:
    if not hero or not hero.get("box"):
        return None
    x0, y0, x1, y1 = hero["box"]
    w = np.asarray(c["w"], dtype=np.float64).reshape(-1, 2)
    d = float(np.max(np.abs(np.concatenate([w.min(axis=0), w.max(axis=0)]) - (x0, y0, x1, y1))))
    if d > STALE_MAX:
        return None  # another non-trigger collider on the hero, not the body box STATE exports
    return Poly("", "", "box", "hero", np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64), 0.0,
                ("hero",), d)


def world_at(p: Poly, state: dict) -> tuple[np.ndarray, float] | None:
    """The label's world outline in another STATE (ents move; TERRAIN is static), or None when it is gone."""
    if p.src == "ents":
        _, iid, k = p.ref
        for e in state.get("ents") or ():
            if e["iid"] == iid:
                cols = e.get("colliders") or ()
                if k >= len(cols):
                    return None
                pts = np.asarray(cols[k]["verts_world"], dtype=np.float64).reshape(-1, 2)
                return (pts.mean(axis=0)[None], float(cols[k].get("r", p.radius))) if p.kind == "circle" else (pts, 0.0)
        return None
    if p.src == "hero":
        hero = state.get("hero")
        if not hero or not hero.get("box"):
            return None
        x0, y0, x1, y1 = hero["box"]
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64), 0.0
    return p.world, p.radius


def project_poly(world: np.ndarray, radius: float, kind: str, cam: dict) -> tuple[np.ndarray, float]:
    """Image vertices (circle: centre) and the circle radius in pixels."""
    if kind == "circle":
        c = world[0]
        pts, _ = projector.project_cam(np.array([c, c + (radius, 0.0)]), cam)
        return pts[:1], float(np.hypot(*(pts[1] - pts[0])))
    pts, _ = projector.project_cam(world, cam)
    return pts, 0.0


def stable(p: Poly, states: Sequence[dict], ref: dict, tol_px: float = 0.3) -> tuple[bool, float]:
    """Whether the label sits still on screen (end-of-frame pose) over `states` relative to STATE `ref`: the capture
    frame is only known to within a frame or two, so only still polygons are compared. Returns (ok, max drift px)."""
    base = world_at(p, ref)
    if base is None:
        return False, math.inf
    b_pts, b_r = project_poly(base[0], base[1], p.kind, eof_pose(ref["cam"]))
    drift = 0.0
    for s in states:
        wr = world_at(p, s)
        if wr is None or s.get("cam") is None:
            return False, math.inf
        pts, r = project_poly(wr[0], wr[1], p.kind, eof_pose(s["cam"]))
        if pts.shape != b_pts.shape:
            return False, math.inf
        drift = max(drift, float(np.max(np.hypot(*(pts - b_pts).T))), abs(r - b_r))
    return drift <= tol_px, drift


def frame_for_capture(q_by_frame: dict[int, int], t_ns: int, qpc_freq: float, lag_ns: int = 0) -> int | None:
    """The newest STATE frame whose end-of-frame QPC ("q") is at least lag_ns before a capture callback's
    time.perf_counter_ns (the same QPC clock, in ns): the newest frame the captured image can show."""
    best = None
    for f, q in q_by_frame.items():
        if q * 1e9 / qpc_freq <= t_ns - lag_ns and (best is None or f > best):
            best = f
    return best


# ---- rasterisation ------------------------------------------------------------------------------------------------

def _cv(pts: np.ndarray) -> np.ndarray:
    """Image points -> OpenCV fixed-point pixel-centre coordinates."""
    p = np.asarray(pts, dtype=np.float64) - 0.5
    return np.round(p * (1 << SHIFT)).astype(np.int32)


def fill(shape: tuple[int, int], pts: np.ndarray, radius: float = 0.0, ox: int = 0, oy: int = 0) -> np.ndarray:
    """Pixels whose centre is inside the polygon (even-odd rule) or the circle of `radius` around pts[0], in a crop of
    `shape` at (ox, oy). Exact scanline test on pixel centres: OpenCV's fillPoly also sets the pixels its rounded
    boundary passes through, about one extra pixel per dimension, which alone costs a 30 px box 0.03 of IoU."""
    h, w = shape
    xs = ox + np.arange(w) + 0.5
    ys = oy + np.arange(h) + 0.5
    if radius > 0:
        cx, cy = pts[0]
        return (xs[None, :] - cx) ** 2 + (ys[:, None] - cy) ** 2 < radius * radius
    p = np.asarray(pts, dtype=np.float64)
    if len(p) < 3 or h == 0 or w == 0:
        return np.zeros(shape, bool)
    q = np.roll(p, -1, axis=0)
    x1, y1, x2, y2 = p[:, 0], p[:, 1], q[:, 0], q[:, 1]
    lo, hi = np.minimum(y1, y2), np.maximum(y1, y2)
    # Edge e crosses row i when lo <= y < hi (half-open: a vertex counts once, horizontal edges never), so every row
    # has an even number of crossings and consecutive x-sorted crossings pair up into spans.
    rows, edges = np.nonzero((ys[:, None] >= lo[None, :]) & (ys[:, None] < hi[None, :]))
    if len(rows) == 0:
        return np.zeros(shape, bool)
    xc = x1[edges] + (ys[rows] - y1[edges]) * (x2[edges] - x1[edges]) / (y2[edges] - y1[edges])
    order = np.lexsort((xc, rows))
    rows, xc = rows[order], xc[order]
    # Column j is inside a span [a, b) when its centre ox + j + 0.5 is.
    start = np.clip(np.ceil(xc[0::2] - ox - 0.5), 0, w).astype(np.int64)
    end = np.clip(np.ceil(xc[1::2] - ox - 0.5), 0, w).astype(np.int64)
    diff = np.zeros((h, w + 1), np.int32)
    np.add.at(diff, (rows[0::2], start), 1)
    np.add.at(diff, (rows[0::2], end), -1)
    return np.cumsum(diff, axis=1)[:, :w] > 0


def draw_outline(m: np.ndarray, pts: np.ndarray, closed: bool = True, value: int = 1) -> None:
    """Draw a one-pixel polyline along the outline into the uint8 image m (DebugMod's centreline: a line on the
    boundary between two pixel columns lands on one of the two core pixels of its antialiased stroke)."""
    if len(pts) >= 2:
        cv2.polylines(m, [_cv(pts)], closed, value, 1, cv2.LINE_8, SHIFT)


def grow(mask: np.ndarray, px: float) -> np.ndarray:
    """mask plus every pixel whose centre lies within px of a mask pixel centre (Euclidean)."""
    if px <= 0 or not mask.any():
        return mask.copy()
    d = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return d <= px + 1e-6


def shrink(mask: np.ndarray, px: float) -> np.ndarray:
    if px <= 0:
        return mask.copy()
    return ~grow(~mask, px)


def iou(a: np.ndarray, b: np.ndarray) -> float:
    union = int(np.count_nonzero(a | b))
    return int(np.count_nonzero(a & b)) / union if union else 1.0


# ---- segmentation ------------------------------------------------------------------------------------------------

def bridge(line: np.ndarray) -> np.ndarray:
    """line plus every pixel with line pixels on two opposite sides (left/right, up/down or a diagonal pair): closes
    one-pixel gaps in an outline without merging two lines that run two or more pixels apart, as a 3x3 closing would."""
    p = np.pad(line, 1)
    c = p[1:-1, 1:-1]
    gap = ((p[1:-1, :-2] & p[1:-1, 2:]) | (p[:-2, 1:-1] & p[2:, 1:-1])
           | (p[:-2, :-2] & p[2:, 2:]) | (p[:-2, 2:] & p[2:, :-2]))
    return c | gap


def segment(img: np.ndarray, palette: dict[str, Sequence[float]], tol: float = 60.0, near: np.ndarray | None = None,
            close: bool = True) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """DebugMod's line pixels by colour. img: BGR uint8 (as captured). A pixel belongs to the nearest palette colour
    within tol (Euclidean RGB). near: where lines may be (a band around the outlines DebugMod reports drawing); scene
    pixels of a palette colour elsewhere are not lines. A background frame with hitboxes off cannot do this job: where
    the scene already has a line's colour, the drawn line is indistinguishable from it, and dropping those pixels would
    open gaps in the outline. close: bridge one-pixel gaps (the antialiased core of a diagonal line over a very
    different background can fall outside tol). Returns (line mask, class index map with -1 = none, palette names)."""
    names = list(palette)
    rgb = img[..., 2::-1].astype(np.float32)
    best = np.full(img.shape[:2], np.inf, np.float32)
    cls = np.full(img.shape[:2], -1, np.int16)
    for k, n in enumerate(names):
        d = np.sqrt(((rgb - np.asarray(palette[n], np.float32)) ** 2).sum(axis=2))
        better = d < best
        best[better] = d[better]
        cls[better] = k
    line = best <= tol
    if near is not None:
        line &= near
    cls[~line] = -1
    if close:
        line = bridge(line)
        if near is not None:
            line &= near
    return line, cls, names


def centrelines(shape: tuple[int, int], sample: dict, names: Sequence[str]) -> np.ndarray:
    """DebugMod's centrelines of every drawn collider as a type-index map: -1 none, -2 where types overlap."""
    screen_h = sample["dm_cam"]["screen"][1]
    layers = {n: np.zeros(shape, np.uint8) for n in names}
    for c in sample["cols"]:
        t = c.get("type")
        if t in layers:
            pts, closed = dm_outline(c, screen_h)
            draw_outline(layers[t], pts, closed)
    count = np.zeros(shape, np.uint8)
    index = np.full(shape, -1, np.int16)
    for k, n in enumerate(names):
        m = layers[n].astype(bool)
        count += m
        index[m] = k
    index[count > 1] = -2
    return index


def measure_palette(img: np.ndarray, centre: np.ndarray, names: Sequence[str], nominal: dict | None = None,
                    min_px: int = 30, max_off: float = 90.0) -> tuple[dict[str, tuple[int, int, int]], dict[str, int]]:
    """Median RGB of the captured pixels on each type's centreline (fully covered core pixels, a little of the
    background mixed in by the antialiasing). The nominal colour stays for types with fewer than min_px pixels or a
    median further than max_off from it (the centrelines missed the drawn lines: wrong frame or crop). Returns
    (palette, pixel counts)."""
    nominal = nominal or PALETTE
    out, counts = {}, {}
    for k, n in enumerate(names):
        px = img[centre == k]
        counts[n] = int(len(px))
        out[n] = tuple(nominal[n])
        if len(px) >= min_px:
            med = np.median(px[:, 2::-1], axis=0)
            if np.linalg.norm(med - np.asarray(nominal[n], np.float64)) <= max_off:
                out[n] = tuple(int(v) for v in med)
    return out, counts


def line_stats(line: np.ndarray, centre_any: np.ndarray) -> tuple[float, float]:
    """(coverage, thickness): the share of DebugMod's centreline pixels found as line pixels, and the found line
    pixels within 3 px of it per centreline pixel (about the line's core width in pixels)."""
    n = np.count_nonzero(centre_any)
    if n == 0:
        return 0.0, 0.0
    near = cv2.dilate(centre_any.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    return int(np.count_nonzero(line & centre_any)) / n, int(np.count_nonzero(line & near)) / n


def best_shift(line: np.ndarray, centre_any: np.ndarray, r: int = 4) -> tuple[int, int, float, float]:
    """The integer image shift (dx, dy) that best puts DebugMod's centrelines on the captured line pixels, its coverage
    and the coverage at (0, 0). A best shift other than (0, 0) points at the client-area crop."""
    h, w = line.shape
    ys, xs = np.nonzero(centre_any)
    if len(xs) == 0:
        return 0, 0, 0.0, 0.0
    best = (0, 0, -1.0)
    at0 = 0.0
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            x, y = xs + dx, ys + dy
            ok = (x >= 0) & (x < w) & (y >= 0) & (y < h)
            cov = int(np.count_nonzero(line[y[ok], x[ok]])) / len(xs)
            if dx == 0 and dy == 0:
                at0 = cov
            if cov > best[2] + 1e-9 or (abs(cov - best[2]) <= 1e-9 and dx * dx + dy * dy < best[0] ** 2 + best[1] ** 2):
                best = (dx, dy, cov)
    return best[0], best[1], best[2], at0


# ---- regions and IoU ----------------------------------------------------------------------------------------------

@dataclass
class FreeSpace:
    """The cells DebugMod's lines cut the viewport into: 4-connected components of the non-line pixels (label 0: line
    pixel or outside the viewport), and for every other pixel the cell of its nearest non-line pixel and the distance
    to it. A line pixel belongs to the cell on its side of the centreline, so a cell plus its line pixels ends on
    DebugMod's centreline (the half-pixel on either side of it is decided by the antialiasing and colour threshold)."""
    labels: np.ndarray
    stats: np.ndarray
    owner: np.ndarray
    dist: np.ndarray
    viewport: tuple[int, int, int, int]   # x0, y0, x1, y1 (pixel index bounds, end exclusive)


def viewport_box(cam: dict, shape: tuple[int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = projector.viewport_px(cam)
    h, w = shape
    return max(0, round(x0)), max(0, round(y0)), min(w, round(x1)), min(h, round(y1))


def free_space(line: np.ndarray, viewport: tuple[int, int, int, int]) -> FreeSpace:
    x0, y0, x1, y1 = viewport
    free = np.zeros(line.shape, np.uint8)
    free[y0:y1, x0:x1] = ~line[y0:y1, x0:x1]
    _, labels, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=4)
    if not free.any():
        return FreeSpace(labels, stats, np.zeros_like(labels), np.full(line.shape, np.inf, np.float32), viewport)
    # DIST_LABEL_PIXEL numbers the zero pixels of its input 1, 2, ... in raster order.
    dist, nearest = cv2.distanceTransformWithLabels(1 - free, cv2.DIST_L2, cv2.DIST_MASK_5, labelType=cv2.DIST_LABEL_PIXEL)
    zy, zx = np.nonzero(free)
    owner = labels[zy, zx][nearest - 1]
    return FreeSpace(labels, stats, owner.astype(np.int32), dist, viewport)


@dataclass
class PolyResult:
    key: str
    type: str
    src: str
    iou: float                  # IoU(D, O): capture vs oracle label (the M1 number)
    iou_dm: float               # IoU(D, M): capture vs DebugMod's own vertices (capture / crop / segmentation chain)
    iou_geom: float             # IoU(M, O): DebugMod's vertices vs oracle label (geometry alone)
    area: int                   # |O| in pixels
    colour: float | None        # share of line pixels along the outline that have the polygon's DebugMod colour
    leak: bool                  # D more than 3x O: the flood escaped through a gap in DebugMod's outline
    img_pts: np.ndarray = field(repr=False, default_factory=lambda: np.zeros((0, 2)))
    img_radius: float = 0.0
    box: tuple[int, int, int, int] = (0, 0, 0, 0)   # crop (x0, y0, x1, y1) of d and o
    d: np.ndarray | None = field(repr=False, default=None)   # kept by evaluate_frame(keep_masks=True)
    o: np.ndarray | None = field(repr=False, default=None)
    offset: float = 0.0         # Poly.offset (world units): above LABEL_EXACT the label is another shape than the drawn one


def _bbox(pts: np.ndarray, radius: float, pad: float, shape: tuple[int, int]) -> tuple[int, int, int, int]:
    h, w = shape
    lo = pts.min(axis=0) - radius - pad
    hi = pts.max(axis=0) + radius + pad
    return (int(max(0, math.floor(lo[0]))), int(max(0, math.floor(lo[1]))),
            int(min(w, math.ceil(hi[0]) + 1)), int(min(h, math.ceil(hi[1]) + 1)))


def _union(a: tuple, b: tuple) -> tuple:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def evaluate_poly(fs: FreeSpace, line: np.ndarray, cls: np.ndarray, type_index: int, p: Poly, img_pts: np.ndarray,
                  img_radius: float, thickness: float, keep_masks: bool = False) -> PolyResult | None:
    """IoU of one polygon (see the module docstring); None when the polygon is too thin for seeds or out of view.
    thickness: the captured line's core width in pixels (line_stats). D = the cells holding seeds (oracle interior
    pixels at least thickness + 2 px from its outline) plus the line pixels they own, i.e. whose nearest non-line pixel
    is in one of them: a line (or two touching lines, or line-coloured scenery around a line) is split down its middle
    between the cells on either side. O = the oracle polygon's pixels; M = DebugMod's polygon's pixels (pixel centres
    inside, clipped to the viewport)."""
    shape = line.shape
    reach = NEAR_PX + 1.5                   # line pixels only exist this close to DebugMod's outlines anyway
    inset = math.ceil(thickness) + 2        # seeds keep this far inside the oracle outline
    pad = inset + math.ceil(reach) + 4
    circle = p.kind == "circle"
    vx0, vy0, vx1, vy1 = fs.viewport
    box = _bbox(img_pts, img_radius, pad, shape)
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return None
    crop = (y1 - y0, x1 - x0)
    inner = fill(crop, img_pts, img_radius if circle else 0.0, x0, y0)
    seeds = shrink(inner, inset) & (fs.labels[y0:y1, x0:x1] > 0)
    ids = np.unique(fs.labels[y0:y1, x0:x1][seeds])
    ids = ids[ids > 0]
    if len(ids) == 0:
        return None
    # Everything the result depends on: the oracle polygon, DebugMod's, and the flooded cells (which may leak).
    for i in ids:
        sx, sy, sw, sh = fs.stats[i, :4]
        box = _union(box, (max(0, sx - pad), max(0, sy - pad), min(shape[1], sx + sw + pad), min(shape[0], sy + sh + pad)))
    box = _union(box, _bbox(p.dm, 0.0, pad, shape))
    x0, y0, x1, y1 = box
    crop = (y1 - y0, x1 - x0)
    view = np.zeros(crop, bool)
    view[max(0, vy0 - y0):max(0, vy1 - y0), max(0, vx0 - x0):max(0, vx1 - x0)] = True
    inner = fill(crop, img_pts, img_radius if circle else 0.0, x0, y0)
    o = inner & view
    m = fill(crop, p.dm, 0.0, x0, y0) & view
    lines = line[y0:y1, x0:x1]
    cells = np.isin(fs.labels[y0:y1, x0:x1], ids)
    owned = lines & np.isin(fs.owner[y0:y1, x0:x1], ids) & (fs.dist[y0:y1, x0:x1] <= reach)
    d = (cells | owned) & view
    ring = grow(inner, thickness + 1) & ~shrink(inner, thickness + 1) & lines
    k = cls[y0:y1, x0:x1][ring]
    k = k[k >= 0]
    colour = float(np.mean(k == type_index)) if len(k) else None
    area = int(np.count_nonzero(o))
    return PolyResult(p.key, p.type, p.src, iou(d, o), iou(d, m), iou(m, o), area, colour,
                      bool(np.count_nonzero(d) > 3 * max(area, 1)), img_pts, img_radius, box,
                      d if keep_masks else None, o if keep_masks else None, p.offset)


@dataclass
class FrameReport:
    results: list[PolyResult]
    palette: dict[str, tuple[int, int, int]]
    palette_px: dict[str, int]
    coverage: float             # share of DebugMod's centreline pixels segmented as line
    thickness: float            # captured line core width, pixels
    shift: tuple[int, int, float, float]   # best_shift
    too_small: int              # polygons without seeds (thinner than about 2 * (thickness + 2) px) or out of view
    line: np.ndarray = field(repr=False, default=None)


def evaluate_frame(img: np.ndarray, polys: Sequence[Poly], cam: dict, sample: dict, tol: float = 60.0,
                   keep_masks: bool = False) -> FrameReport:
    """All polygons of one captured frame. img: BGR client-area image; cam: the STATE "cam" of the frame the image
    shows (moved to DebugMod's end-of-frame pose here); sample: the projection.sample reply the polygons came from (its
    drawn outlines calibrate the palette and bound where line pixels are looked for)."""
    shape = img.shape[:2]
    types = sorted({c["type"] for c in sample["cols"] if c.get("type") in PALETTE}, key=list(PALETTE).index)
    names = types or list(LABELLED)
    centre = centrelines(shape, sample, names)
    palette, counts = measure_palette(img, centre, names)
    centre_any = centre != -1
    near = cv2.dilate(centre_any.astype(np.uint8), np.ones((2 * NEAR_PX + 1, 2 * NEAR_PX + 1), np.uint8)).astype(bool)
    line, cls, names = segment(img, palette, tol, near)
    coverage, thickness = line_stats(line, centre_any)
    shift = best_shift(line, centre_any)
    fs = free_space(line, viewport_box(cam, shape))
    pose = eof_pose(cam)
    results, too_small = [], 0
    for p in polys:
        pts, r = project_poly(p.world, p.radius, p.kind, pose)
        res = evaluate_poly(fs, line, cls, names.index(p.type) if p.type in names else -1, p, pts, r, thickness or 2.0,
                            keep_masks)
        if res is None:
            too_small += 1
        else:
            results.append(res)
    return FrameReport(results, palette, counts, coverage, thickness, shift, too_small, line)
