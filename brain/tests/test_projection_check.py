"""Offline checks of the projection calibration (ssbot.tools.projection_check, ssbot.probes.m1_projection) on synthetic
DebugMod drawings. DebugMod's antialiased line routine (Hitbox/Drawing.cs DrawLine) is re-implemented here, so the IoU
pipeline sees the same kind of pixels the game shows: a quad 3 * width wide along each segment, alpha 1 - |d| / width
across it, blended twice, vertices rounded to whole GUI pixels."""
import math
import socket
import threading
import time

import msgpack
import numpy as np
import pytest

from ssbot.ipc.framing import BUTTONS, SCHEMA_VERSION, MsgType, encode, port
from ssbot.oracle.messages import Hazard, Shape, Solid, Terrain
from ssbot.tools import projection_check as pc
from ssbot.tools import projector

W, H = 960, 540
PPU = 40.0                                           # pixels per world unit on the z = 0 plane
DIST = 20.0                                          # camera distance to the z = 0 plane
FOV = math.degrees(2 * math.atan(H / PPU / 2 / DIST))
LINE = max(0.7, W / 960)                             # HitboxRender.LineWidth at this width (ZoomFactor 1)


# ---- camera ---------------------------------------------------------------------------------------------------------

def camera(cx: float, cy: float, shake: tuple[float, float] = (0.0, 0.0)) -> dict:
    """A STATE "cam" (src 1: render-time V, i.e. at the shaken position) for a camera over (cx, cy) at z = -DIST."""
    x, y = cx + shake[0], cy + shake[1]
    v = np.array([[1, 0, 0, -x], [0, 1, 0, -y], [0, 0, -1, -DIST], [0, 0, 0, 1]], dtype=np.float64)
    f = 1 / math.tan(math.radians(FOV) / 2)
    near, far = 0.3, 1000.0
    p = np.array([[f / (W / H), 0, 0, 0], [0, f, 0, 0], [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
                  [0, 0, -1, 0]])
    return {"V": list(v.flatten(order="F")), "P": list(p.flatten(order="F")), "rect": [0.0, 0.0, 1.0, 1.0],
            "screen": [W, H], "src": 1, "shake": list(shake), "pos": [x, y, -DIST]}


def cam_info(cam: dict, render: bool = True) -> dict:
    return {"id": 1, "name": "tk2dCamera", "is_main": True, "render": render, "pixel_rect": [0.0, 0.0, W, H],
            "rect": [0.0, 0.0, 1.0, 1.0], "target": [W, H], "rt": False, "screen": [W, H], "V": cam["V"], "P": cam["P"]}


def unity_screen(cam: dict, pts) -> list[float]:
    """Camera.WorldToScreenPoint (bottom-left origin) of world points, flat, float32 like the RPC."""
    img, _ = projector.project_cam(np.asarray(pts, dtype=np.float64).reshape(-1, 2), cam)
    return [float(v) for v in np.stack([img[:, 0], H - img[:, 1]], axis=1).astype(np.float32).ravel()]


# ---- DebugMod's drawing ---------------------------------------------------------------------------------------------

def dm_line(img: np.ndarray, a, b, rgb, w: float = LINE) -> None:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    d = b - a
    length = math.hypot(*d)
    if length < 1e-3:
        return
    quad = 3 * w
    n = np.array([-d[1], d[0]]) / length
    lo = np.maximum(np.floor(np.minimum(a, b) - quad).astype(int), 0)
    hi = np.minimum(np.ceil(np.maximum(a, b) + quad).astype(int), [img.shape[1], img.shape[0]])
    if (hi <= lo).any():
        return
    ys, xs = np.mgrid[lo[1]:hi[1], lo[0]:hi[0]]
    px, py = xs + 0.5 - a[0], ys + 0.5 - a[1]
    u = (px * d[0] + py * d[1]) / (length * length)
    dist = px * n[0] + py * n[1]
    inside = (u >= 0) & (u <= 1) & (np.abs(dist) <= quad / 2)
    alpha = np.where(inside, np.clip(1 - np.abs(dist) / w, 0, 1), 0)[..., None]
    region = img[lo[1]:hi[1], lo[0]:hi[0]]
    for _ in range(2):
        region[:] = region * (1 - alpha) + np.asarray(rgb, dtype=np.float64) * alpha


def dm_draw(img: np.ndarray, gui: np.ndarray, rgb, closed: bool = True) -> None:
    pts = list(gui) + ([gui[0]] if closed else [])
    for a, b in zip(pts, pts[1:]):
        dm_line(img, a, b, rgb)


def background(seed: int = 1) -> np.ndarray:
    """A dark, smoothly varying RGB float image."""
    import cv2

    rng = np.random.default_rng(seed)
    noise = cv2.resize(rng.normal(0, 1, (H // 16 + 2, W // 16 + 2, 3)), (W, H), interpolation=cv2.INTER_CUBIC)
    return np.clip(60 + 25 * noise, 0, 255)


def octagon(c, r) -> list[float]:
    """Entities.ColliderGeometry.AppendCircle: the circumscribed octagon, vertices at 22.5 + 45 k degrees."""
    k = np.radians(22.5 + 45 * np.arange(8))
    s = 1.0823922
    return [float(v) for v in np.stack([c[0] + r * s * np.cos(k), c[1] + r * s * np.sin(k)], axis=1).astype(np.float32).ravel()]


def box_tl(x0, y0, x1, y1) -> np.ndarray:
    """DebugMod's box order: TL, TR, BR, BL (world, y up)."""
    return np.array([[x0, y1], [x1, y1], [x1, y0], [x0, y0]], dtype=np.float64)


def box_bl(x0, y0, x1, y1) -> np.ndarray:
    """The ents / TERRAIN box order: BL, BR, TR, TL."""
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)


def f32(a) -> list[float]:
    return [float(v) for v in np.asarray(a, dtype=np.float32).ravel()]


class Scene:
    """Hornet (Knight box), two enemies (a box and a circle, both STATE ents), a spike hazard on the floor (TERRAIN
    hazard), five terrain pieces (TERRAIN solids: two boxes sharing an edge and running off both sides of the view, an
    overlapping pair, one of them partly off screen, a quad), an attack box touching Hornet's (a type the oracle does
    not label), an enemy box nobody exports and an edge chain. Drawn in DebugMod's order (highest HitboxType depth
    first, so the Knight ends up on top)."""

    CX, CY = 10.0, 5.0

    def __init__(self, shake=(0.0, 0.0), seed: int = 1):
        self.cam = camera(self.CX, self.CY, shake)        # STATE cam: render time, shaken
        self.gui_cam = camera(self.CX, self.CY)            # DebugMod's end-of-frame pose
        hero_box = (9.6, 3.0, 10.4, 4.6)
        enemy_box = (13.0, 3.0, 15.2, 4.1)
        circle_c, circle_r = (12.0, 7.5), 1.2
        hazard_box = (4.0, 2.9, 6.0, 3.4)
        terrain = [(100, "box", box_bl(-2.0, 0.0, 8.0, 2.9)), (101, "box", box_bl(8.0, 0.0, 22.0, 2.9)),
                   (102, "box", box_bl(16.0, 5.0, 19.0, 6.0)), (103, "box", box_bl(17.5, 5.5, 23.0, 7.0)),
                   (104, "poly", np.array([[3.0, 6.0], [6.5, 5.5], [7.2, 8.0], [4.0, 9.1]]))]
        cols = []

        def col(cid, typ, kind, w, o=None, closed=True, r=0.0):
            cols.append({"id": cid, "path": 0, "go": f"go{cid}", "type": typ,
                         "color": [c / 255 for c in pc.PALETTE[typ]], "kind": kind, "closed": closed, "layer": 8,
                         "trigger": False, "er": 0.0, "r": r, "w": f32(w), "o": o if o is not None else f32(w),
                         "s": unity_screen(self.cam, w), "e": unity_screen(self.gui_cam, w), "moved": 0.0})

        col(1, "Knight", "box", box_tl(*hero_box))
        enemy_o = f32(box_bl(*enemy_box))
        col(2, "Enemy", "box", box_tl(*enemy_box), enemy_o)
        circle_o = octagon(circle_c, circle_r)
        col(3, "Enemy", "circle", [circle_c, (circle_c[0] + circle_r, circle_c[1])], circle_o, r=circle_r)
        col(4, "Enemy", "box", box_tl(*hazard_box))
        for cid, kind, v in terrain:
            w = box_tl(v[0, 0], v[0, 1], v[2, 0], v[2, 1]) if kind == "box" else v
            col(cid, "Terrain", kind, w)
        col(200, "Attack", "box", box_tl(10.4, 3.6, 11.6, 4.2))
        col(201, "Enemy", "box", box_tl(1.0, 4.0, 2.0, 5.0))       # drawn, but no label anywhere
        col(202, "Terrain", "edge", np.array([[20.0, 3.5], [21.0, 4.5], [22.0, 3.5]]), closed=False)
        self.sample = {"frame": 500, "q": 0, "source": "debugmod", "cam": cam_info(self.cam), "dm_cam": cam_info(self.gui_cam),
                       "cols": cols, "n": {"candidates": len(cols), "cols": len(cols), "truncated": False},
                       "dm": {"show": 1, "state": 1, "line_width": LINE, "version": "1.1.2"}}

        self.state = {"f": 500, "q": 0, "cam": self.cam,
                      "hero": {"pos": [10.0, 3.0, 0.0], "box": list(hero_box)},
                      "ents": [
                          {"iid": -10, "colliders": [{"kind": "box", "verts_world": enemy_o, "enabled": True, "layer": 11,
                                                      "damage": {"eff": 1}}]},
                          {"iid": -11, "colliders": [{"kind": "circle", "verts_world": circle_o, "r": circle_r,
                                                      "enabled": True, "layer": 11, "damage": {"eff": 1}}]},
                      ]}
        solids = [Solid(cid, f"go{cid}", 8, True, 0, 0, [Shape(kind, np.asarray(v, dtype=np.float32))])
                  for cid, kind, v in terrain]
        hazards = [Hazard(4, "spikes", True, "SPIKES", 1, 0, False, False, 0,
                          [Shape("box", box_bl(*hazard_box).astype(np.float32))])]
        self.terrain = Terrain(1, "Test_01", "Test_01", "rpc", 400, solids, hazards, {}, {}, {}, {})

        img = background(seed)
        img[300:330, 470:490] = (185, 25, 30)     # Hornet's red cloak inside her box: nearly "Enemy" red
        img[345:375, 700:760] = (10, 190, 10)     # green scenery straddling the floor's top edge (y 354)
        img[40:80, 40:120] = (200, 20, 20)        # a red lamp far from any collider
        depth = list(pc.PALETTE)  # HitboxType declaration order = Depth
        for c in sorted(cols, key=lambda c: -depth.index(c["type"])):
            pts, closed = pc.dm_outline(c, H)
            dm_draw(img, pts, pc.PALETTE[c["type"]], closed)
        self.capture = to_bgr(img)

    def polys(self, ref_state: dict | None = None):
        polys, unmatched, skipped = pc.match_sample(self.sample, self.state, self.terrain)
        for p in polys:
            p.world, p.radius = pc.world_at(p, ref_state or self.state)
        return polys, unmatched, skipped


def to_bgr(rgb: np.ndarray) -> np.ndarray:
    return np.clip(np.round(rgb), 0, 255).astype(np.uint8)[..., ::-1].copy()


# ---- conversions and camera poses -----------------------------------------------------------------------------------

def test_unity_to_image_plain_render_texture_and_letterbox():
    plain = {"pixel_rect": [0, 0, 1920, 1080], "rect": [0, 0, 1, 1], "screen": [1920, 1080]}
    assert pc.unity_to_image([100.0, 80.0], plain)[0] == pytest.approx([100.0, 1000.0])
    # CameraRenderScaled: a 960x540 texture shown on the whole 1920x1080 screen.
    rt = {"pixel_rect": [0, 0, 960, 540], "rect": [0, 0, 1, 1], "screen": [1920, 1080]}
    assert pc.unity_to_image([480.0, 270.0, 0.0, 540.0], rt) == pytest.approx(np.array([[960.0, 540.0], [0.0, 0.0]]))
    # ForceCameraAspect letterbox: rect y 0.05, height 0.9 of the screen.
    box = {"pixel_rect": [0, 54, 1920, 972], "rect": [0, 0.05, 1, 0.9], "screen": [1920, 1080]}
    assert pc.unity_to_image([0.0, 54.0, 1920.0, 1026.0], box) == pytest.approx(np.array([[0.0, 1026.0], [1920.0, 54.0]]))


def test_debugmod_gui_rounds_half_to_even_like_math_round():
    gui = pc.debugmod_gui([10.5, 359.5, 11.5, 0.4], 360)
    assert gui.tolist() == [[10.0, 0.0], [12.0, 360.0]]   # 0.5 -> 0, 11.5 -> 12, 360 - 0.4 = 359.6 -> 360


def test_dm_circle_matches_debugmods_bezier_quarters():
    pts = pc.dm_circle((100.0, 50.0), 24.0)
    assert len(pts) == 16                                  # clamp(24 // 16, 4, 32) = 4 segments per quarter
    assert np.hypot(*(pts - (100.0, 50.0)).T) == pytest.approx(24.0, rel=3e-4)
    assert pts[0] == pytest.approx([100.0, 26.0])          # starts at the top (GUI y down), goes clockwise on screen
    assert pts[4] == pytest.approx([124.0, 50.0])
    assert len(pc.dm_circle((0, 0), 100.0)) == 24 and len(pc.dm_circle((0, 0), 900.0)) == 128


def test_eof_pose_removes_the_shake():
    shaken = camera(10.0, 5.0, shake=(0.3, -0.2))
    still = camera(10.0, 5.0)
    pts = np.array([[8.0, 3.0], [14.0, 9.0]])
    a, _ = projector.project_cam(pts, pc.eof_pose(shaken))
    b, _ = projector.project_cam(pts, still)
    assert a == pytest.approx(b, abs=1e-6)
    c, _ = projector.project_cam(pts, shaken)
    assert np.abs(c - b).max() > 10                        # 0.3 u at 40 px/u
    assert pc.eof_pose(dict(shaken, src=0)) is not None and pc.eof_pose(dict(shaken, src=0))["V"] == shaken["V"]


def test_vertex_errors_are_zero_for_the_same_camera_and_catch_a_mismatch():
    scene = Scene(shake=(0.25, 0.1))
    render = pc.vertex_errors(scene.sample, scene.cam, "render")
    eof = pc.vertex_errors(scene.sample, scene.cam, "eof")
    assert len(render) == sum(len(c["w"]) // 2 for c in scene.sample["cols"])
    assert render.max() < 1e-3 and eof.max() < 1e-3
    assert pc.summarize(render)["p99"] < pc.VERTEX_P99_MAX
    # A STATE camera 2 px off (e.g. the wrong frame's V, or a transposed matrix would be far worse).
    wrong = camera(10.0 + 2 / PPU, 5.0, shake=(0.25, 0.1))
    assert pc.vertex_errors(scene.sample, wrong, "render") == pytest.approx(2.0, abs=1e-3)
    # Unity's end-of-frame points compared against the uncorrected (shaken) camera: off by the shake.
    assert pc.vertex_errors(scene.sample, dict(scene.cam, shake=[0.0, 0.0]), "eof").max() > 5
    assert pc.matrices_match(scene.sample["cam"], scene.cam) == 0.0


# ---- rasterisation and segmentation ---------------------------------------------------------------------------------

def test_fill_counts_pixel_centres_exactly():
    box = np.array([[10.0, 20.0], [42.0, 20.0], [42.0, 84.0], [10.0, 84.0]])
    assert pc.fill((100, 60), box).sum() == 32 * 64
    assert pc.fill((100, 60), box + 0.49).sum() == 32 * 64   # centres x.5 still inside [10.49, 42.49)
    crop = pc.fill((30, 40), box, ox=5, oy=15)                 # the same pixels, seen from a crop at (5, 15)
    assert np.array_equal(crop, pc.fill((100, 60), box)[15:45, 5:45])
    tri = np.array([[0.0, 0.0], [200.0, 0.0], [0.0, 100.0]])
    assert pc.fill((120, 220), tri).sum() == pytest.approx(10000, rel=0.01)
    disc = pc.fill((200, 200), np.array([[100.0, 100.0]]), radius=50.0)
    assert disc.sum() == pytest.approx(math.pi * 2500, rel=0.005)
    assert pc.fill((10, 10), np.array([[1.0, 1.0], [5.0, 1.0]])).sum() == 0


def test_bridge_closes_one_pixel_gaps_but_keeps_close_lines_apart():
    line = np.zeros((12, 12), bool)
    line[2, :] = True
    line[2, 5] = False                    # a one-pixel gap in a line
    line[5, :] = True                     # two lines two pixels apart (rows 5 and 8)
    line[8, :] = True
    out = pc.bridge(line)
    assert out[2, 5]
    assert not out[6:8].any()


def test_segment_looks_for_lines_only_near_debugmods_outlines():
    img = np.full((20, 20, 3), 40, np.uint8)
    img[:, 15:] = (0, 190, 0)[::-1]       # a green patch in the scene (BGR)
    img[10, :] = (0, 204, 0)[::-1]        # a Terrain line across everything, also over the patch
    palette = {"Terrain": pc.PALETTE["Terrain"], "Enemy": pc.PALETTE["Enemy"]}
    line, cls, names = pc.segment(img, palette, close=False)
    assert line[10].all() and line[:, 15:].all()     # colour alone: the patch looks like line
    near = np.zeros((20, 20), bool)
    near[8:13] = True                                 # DebugMod drew along row 10
    line, cls, names = pc.segment(img, palette, near=near, close=False)
    assert line[10].all() and not line[:8].any() and not line[13:].any()
    assert names == ["Terrain", "Enemy"] and (cls[line] == 0).all() and (cls[~line] == -1).all()


def test_free_space_owner_splits_a_line_at_its_centre():
    line = np.zeros((10, 20), bool)
    line[4:6, :] = True                   # a two-pixel line between rows 0-3 and 6-9
    fs = pc.free_space(line, (0, 0, 20, 10))
    above, below = fs.labels[0, 0], fs.labels[9, 0]
    assert above != below and above > 0 and below > 0
    assert (fs.owner[4] == above).all() and (fs.owner[5] == below).all()


# ---- matching, timing, stability ------------------------------------------------------------------------------------

def test_match_sample_pairs_each_source_and_counts_the_rest():
    scene = Scene()
    polys, unmatched, skipped = pc.match_sample(scene.sample, scene.state, scene.terrain)
    by_key = {p.key: p for p in polys}
    assert by_key["1/0"].src == "hero" and by_key["1/0"].type == "Knight"
    assert by_key["2/0"].src == "ents" and by_key["2/0"].ref == ("ents", -10, 0)
    circle = by_key["3/0"]
    assert circle.src == "ents" and circle.kind == "circle" and circle.radius == pytest.approx(1.2)
    assert circle.world[0] == pytest.approx([12.0, 7.5], abs=1e-5)
    assert by_key["4/0"].src == "hazard"
    for cid in (100, 101, 102, 103, 104):
        p = by_key[f"{cid}/0"]
        assert p.src == "terrain" and p.stale < 1e-5      # TERRAIN corners in another order still match
    assert unmatched == {"Enemy": 1}
    assert skipped == {"type Attack": 1, "kind edge": 1}
    assert len(circle.dm) == 16 and len(by_key["2/0"].dm) == 4


def test_match_sample_leaves_moved_terrain_as_stale():
    scene = Scene()
    scene.terrain.solids[0].shapes[0].verts = scene.terrain.solids[0].shapes[0].verts + np.float32(0.5)
    polys, _, _ = pc.match_sample(scene.sample, scene.state, scene.terrain)
    stale = {p.key: p.stale for p in polys}
    assert stale["100/0"] == pytest.approx(math.hypot(0.5, 0.5), abs=1e-4) and stale["101/0"] < 1e-5


def test_label_offset_tells_the_drawn_shape_from_another_label_shape():
    scene = Scene()
    polys, _, _ = pc.match_sample(scene.sample, scene.state, scene.terrain)
    assert max(p.offset for p in polys) < pc.LABEL_EXACT               # every label here is the drawn shape
    # An ents box with edgeRadius (in "o" and verts_world, not in what DebugMod draws) and a hero box that is
    # Collider2D.bounds with Box2D's contact skin: still matched, but as another shape.
    er, skin = 0.05, 0.01
    o = f32(box_bl(13.0 - er, 3.0 - er, 15.2 + er, 4.1 + er))
    enemy = next(c for c in scene.sample["cols"] if c["id"] == 2)
    enemy["o"], enemy["er"] = o, er
    scene.state["ents"][0]["colliders"][0]["verts_world"] = o
    x0, y0, x1, y1 = scene.state["hero"]["box"]
    scene.state["hero"]["box"] = [x0 - skin, y0 - skin, x1 + skin, y1 + skin]
    polys, _, _ = pc.match_sample(scene.sample, scene.state, scene.terrain)
    by_key = {p.key: p for p in polys}
    assert by_key["2/0"].src == "ents" and by_key["2/0"].offset == pytest.approx(er * math.sqrt(2), rel=1e-3)
    assert by_key["1/0"].src == "hero" and by_key["1/0"].offset == pytest.approx(skin * math.sqrt(2), rel=1e-3)
    assert all(p.offset < pc.LABEL_EXACT for k, p in by_key.items() if k not in ("1/0", "2/0"))


def test_frame_for_capture_takes_the_newest_frame_ended_before_the_callback():
    freq = 10_000_000
    q = {f: 1_000_000 + f * freq // 60 for f in range(100, 110)}
    t_ns = int(q[104] * 1e9 / freq) + 2_000_000        # 2 ms after frame 104 ended
    assert pc.frame_for_capture(q, t_ns, freq) == 104
    assert pc.frame_for_capture(q, t_ns, freq, lag_ns=5_000_000) == 103
    assert pc.frame_for_capture(q, 0, freq) is None


def test_stable_needs_a_still_camera_and_a_still_label():
    scene = Scene()
    polys, _, _ = scene.polys(scene.state)
    enemy = next(p for p in polys if p.key == "2/0")
    terrain = next(p for p in polys if p.key == "101/0")
    still = [dict(scene.state, f=f) for f in range(495, 501)]
    assert pc.stable(enemy, still, scene.state)[0] and pc.stable(terrain, still, scene.state)[0]
    walked = [dict(s, ents=[{"iid": -10, "colliders": [{"verts_world": list(np.asarray(scene.state["ents"][0]["colliders"][0]
              ["verts_world"]) + 0.1 * (500 - s["f"])), "kind": "box"}]}]) for s in still]
    ok, drift = pc.stable(enemy, walked, scene.state)
    assert not ok and drift == pytest.approx(math.hypot(0.5, 0.5) * PPU, rel=0.01)
    assert pc.stable(terrain, walked, scene.state)[0]           # terrain does not care about the enemy
    panned = [dict(s, cam=camera(Scene.CX + 0.01 * (500 - s["f"]), Scene.CY)) for s in still]
    assert not pc.stable(terrain, panned, scene.state)[0]
    gone = [dict(s, ents=[]) for s in still]
    assert pc.stable(enemy, gone, scene.state) == (False, math.inf)


# ---- IoU on synthetic DebugMod drawings -----------------------------------------------------------------------------

def iou_by_key(rep: pc.FrameReport) -> dict[str, float]:
    return {r.key: r.iou for r in rep.results}


@pytest.mark.parametrize("seed", [1, 2])
def test_aligned_labels_pass(seed):
    scene = Scene(seed=seed)
    polys, _, _ = scene.polys()
    rep = pc.evaluate_frame(scene.capture, polys, scene.cam, scene.sample)
    ious = iou_by_key(rep)
    assert set(ious) == {"1/0", "2/0", "3/0", "4/0", "100/0", "101/0", "102/0", "103/0", "104/0"}
    assert min(ious.values()) >= pc.IOU_MIN, ious
    boxes = [v for k, v in ious.items() if k != "3/0"]
    assert min(boxes) > 0.99                               # only the circle (DebugMod's 16-gon) loses more
    assert 0.96 < ious["3/0"] < 0.99
    assert rep.coverage > 0.95 and 1.5 < rep.thickness < 2.6 and rep.shift[:2] == (0, 0)
    assert all(r.iou_dm > 0.98 and not r.leak and r.colour > 0.9 for r in rep.results)
    assert rep.palette["Terrain"] != pc.PALETTE["Terrain"]  # measured on the capture (antialiased core)


def test_camera_shake_is_compared_in_debugmods_pose():
    scene = Scene(shake=(0.3, -0.2))                       # 12 px / 8 px at 40 px/u
    polys, _, _ = scene.polys()
    rep = pc.evaluate_frame(scene.capture, polys, scene.cam, scene.sample)
    assert pc.summarize(r.iou for r in rep.results)["min"] >= pc.IOU_MIN
    # Without the correction (as if STATE V were already the end-of-frame one) the small boxes fall apart.
    rep = pc.evaluate_frame(scene.capture, polys, dict(scene.cam, src=0), scene.sample)
    assert iou_by_key(rep)["1/0"] < 0.8


@pytest.mark.parametrize("px, worst", [(1.0, 0.95), (3.0, 0.85)])
def test_misprojected_labels_fail(px, worst):
    scene = Scene()
    polys, _, _ = scene.polys()
    off = camera(Scene.CX - px / PPU, Scene.CY)            # the oracle's projection lands px pixels to the right
    rep = pc.evaluate_frame(scene.capture, polys, off, scene.sample)
    ious = iou_by_key(rep)
    assert min(ious.values()) < worst, ious                # 1 px: only Hornet's 32 px wide box drops below 0.95
    if px >= 3:
        assert pc.summarize(ious.values())["p5"] < pc.IOU_MIN
    # DebugMod's own vertices still agree with the capture: the error is in the projection, not the capture chain.
    assert min(r.iou_dm for r in rep.results) > 0.95
    assert min(r.iou_geom for r in rep.results) < worst


def test_a_misaligned_crop_shows_up_as_a_shift():
    scene = Scene()
    polys, _, _ = scene.polys()
    shifted = np.roll(scene.capture, 2, axis=1)            # the client area cut 2 px too far left
    rep = pc.evaluate_frame(shifted, polys, scene.cam, scene.sample)
    assert rep.shift[:2] == (2, 0) and rep.shift[2] > rep.shift[3] + 0.1  # horizontal lines still hit at (0, 0)
    assert min(r.iou_dm for r in rep.results) < 0.95


def test_a_gap_in_an_outline_leaks_and_is_flagged():
    scene = Scene()
    img = scene.capture.copy()
    img[:, 458:470] = 90                                   # a strip hides the hero box's left edge (x = 464)
    polys, _, _ = scene.polys()
    rep = pc.evaluate_frame(img, polys, scene.cam, scene.sample, keep_masks=True)
    knight = next(r for r in rep.results if r.key == "1/0")
    assert knight.leak and knight.iou < 0.5
    assert knight.d is not None and knight.d.shape == knight.o.shape


def test_report_gates_only_labels_of_the_drawn_shape(monkeypatch, capsys):
    """A hero box larger than the drawn one (bounds with a contact skin, 0.8 px a side here) scores below 0.95 and
    would sink p5, but it is a label-definition difference: reported with its offset, outside the gate."""
    from ssbot.probes import m1_projection

    monkeypatch.setattr(m1_projection, "results", [])
    scene = Scene()
    skin = 0.02
    x0, y0, x1, y1 = scene.state["hero"]["box"]
    scene.state["hero"]["box"] = [x0 - skin, y0 - skin, x1 + skin, y1 + skin]
    polys, _, _ = scene.polys()
    rep = pc.evaluate_frame(scene.capture, polys, scene.cam, scene.sample)
    assert iou_by_key(rep)["1/0"] < pc.IOU_MIN
    totals = m1_projection.Totals()
    totals.polys = rep.results * 2
    out = m1_projection.report(totals, vertex_only=False)
    assert out["iou"]["n"] == 16 and out["iou"]["p5"] >= pc.IOU_MIN
    assert out["iou_not_gated"]["n"] == 2 and out["iou_all"]["p5"] < pc.IOU_MIN
    assert [p["offset"] > pc.LABEL_EXACT for p in out["polys"]].count(True) == 2
    levels = {name: level for level, name, _ in m1_projection.results}
    assert levels[f"at least {m1_projection.MIN_POLYS} polygon-frames compared (label = the drawn shape)"] == "PASS"
    assert levels[f"IoU p5 >= {pc.IOU_MIN} (label = the drawn shape)"] == "PASS"
    assert levels[f"IoU p5 >= {pc.IOU_MIN} where the label is another shape (not gated)"] == "WARN"
    text = capsys.readouterr().out
    assert "Knight" in text and "2 not gated" in text


# ---- the probe against a fake oracle --------------------------------------------------------------------------------

INSTANCES = iter(range(960, 990))  # ports 47977+; far from the real instances, one per test


class ProjectionOracle:
    """Streams STATEs of the Scene (still camera, "q" on the real QPC clock in ns) and answers projection.sample from
    it. error_px displaces Unity's render-time points (a projector/export bug the vertex check must catch). debugmod:
    hitbox.show and scene.dump work (else hitbox.show fails like an oracle without DebugMod)."""

    PANELS = {"MainPanelVisible": True, "ConsoleVisible": False}

    def __init__(self, error_px: float = 0.0, debugmod: bool = False):
        self.instance = next(INSTANCES)
        self.srv = socket.create_server(("127.0.0.1", port(self.instance)))
        self.scene = Scene(shake=(0.05, 0.0))
        self.error_px = error_px
        self.debugmod = debugmod
        self.show, self.panels = 0, dict(self.PANELS)
        self.calls: list[tuple[str, dict]] = []
        self.frame = 1000
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.seq = 0
        threading.Thread(target=self._serve, daemon=True).start()

    def _send(self, conn, t: MsgType, obj) -> None:
        with self.lock:
            self.seq += 1
            conn.sendall(encode(t, self.seq, msgpack.packb(obj, use_single_float=True)))

    def _serve(self) -> None:
        conn, _ = self.srv.accept()
        self._send(conn, MsgType.HELLO, {"role": "oracle", "schema": SCHEMA_VERSION, "plugin": "fake", "game": "1.0.30000",
                                         "instance": str(self.instance), "qpc_freq": 1_000_000_000, "buttons": list(BUTTONS),
                                         "rpcs": ["ping", "projection.sample", "hitbox.show", "scene.dump"]})
        threading.Thread(target=self._stream, args=(conn,), daemon=True).start()
        try:
            while not self.stop.is_set():
                n = int.from_bytes(self._recv(conn, 4), "little")
                body = self._recv(conn, n)
                if body[0] == MsgType.RPC_REQ:
                    req = msgpack.unpackb(body[8:], raw=False)
                    self.calls.append((req["name"], req["args"]))
                    self._send(conn, MsgType.RPC_RES, self._rpc(conn, req))
        except (ConnectionError, OSError):
            pass

    def _state(self, f: int) -> dict:
        return {"f": f, "q": time.perf_counter_ns(), "game": {"gs": 4}, "pause": {"bench": False},
                "hero": {"pos": [10.0, 3.0, 0.0], "hero_accepting_input": True, "box": [9.6, 3.0, 10.4, 4.6]},
                "cam": self.scene.cam, "ents": self.scene.state["ents"]}

    def _stream(self, conn) -> None:
        while not self.stop.is_set():
            with self.lock:
                self.frame += 1
                f = self.frame
            try:
                self._send(conn, MsgType.STATE, self._state(f))
            except OSError:
                return
            time.sleep(1 / 120)

    def _terrain(self) -> dict:
        def shapes(items):
            return [{"k": s.kind, "v": np.asarray(s.verts, "<f4").tobytes(), "r": s.radius} for s in items]

        t = self.scene.terrain
        return {"seq": 7, "reason": "rpc", "frame": self.frame, "transition": 1, "scene_raw": t.scene_raw, "scene": t.scene,
                "solids": [{"id": s.id, "go": s.go, "layer": s.layer, "on": s.on, "body": s.body, "flags": s.flags,
                            "shapes": shapes(s.shapes)} for s in t.solids],
                "hazards": [{"id": h.id, "go": h.go, "src": h.src, "on": h.on, "hazard": h.hazard, "damage": h.damage,
                             "flags": h.flags, "tink": h.tink, "trigger": h.trigger, "body": h.body,
                             "shapes": shapes(h.shapes)} for h in t.hazards]}

    def _rpc(self, conn, req: dict) -> dict:
        args = req["args"]
        if req["name"] == "projection.sample":
            with self.lock:
                f = self.frame + 1  # answered at the end of the next frame, like the oracle
            sample = dict(self.scene.sample, frame=f, source=args.get("source"))
            if self.error_px:
                sample["cols"] = [dict(c, s=[v + self.error_px if i % 2 == 0 else v for i, v in enumerate(c["s"])])
                                  for c in sample["cols"]]
            return {"id": req["id"], "ok": True, "result": sample}
        if req["name"] == "hitbox.show":
            if not self.debugmod:
                return {"id": req["id"], "ok": False, "error": "DebugMod is not loaded"}
            prev = {"show": self.show, "panels": dict(self.panels)}
            self.show = args.get("mode", {True: 1, False: 0}.get(args.get("on"), self.show))
            if "ui" in args:
                self.panels = {k: args["ui"] for k in self.panels}
            self.panels.update(args.get("panels") or {})
            return {"id": req["id"], "ok": True, "result": {
                "show": self.show, "state": self.show, "render": self.show > 0, "colliders": 12 if self.show else -1,
                "line_width": LINE, "gameplay": True, "panels": dict(self.panels), "settled": True, "frames": 2,
                "version": "1.1.2", "prev": prev}}
        if req["name"] == "scene.dump" and self.debugmod:
            self._send(conn, MsgType.TERRAIN, self._terrain())
            return {"id": req["id"], "ok": True, "result": {"seq": 7}}
        return {"id": req["id"], "ok": False, "error": f"unknown rpc {req['name']}"}

    @staticmethod
    def _recv(conn, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError
            buf += chunk
        return buf

    def close(self) -> None:
        self.stop.set()
        self.srv.close()


@pytest.mark.parametrize("error_px, code", [(0.0, 0), (2.0, 1)])
def test_probe_vertex_check_end_to_end(monkeypatch, capsys, tmp_path, error_px, code):
    from ssbot.probes import m1_projection

    oracle = ProjectionOracle(error_px)
    out = tmp_path / "m1_projection.json"
    monkeypatch.setattr("sys.argv", ["m1_projection", "--instance", str(oracle.instance), "--vertex-samples", "4",
                                     "--vertex-only", "--json", str(out)])
    monkeypatch.setattr(m1_projection, "results", [])
    try:
        assert m1_projection.main() == code
    finally:
        oracle.close()
    assert not [a for name, a in oracle.calls if name == "hitbox.show"]   # --vertex-only leaves DebugMod alone
    import json

    numbers = json.loads(out.read_text())
    assert numbers["samples"] == 4
    assert numbers["vertex_render"]["p99"] == pytest.approx(error_px, abs=1e-3)
    assert numbers["vertex_eof"]["max"] < 1e-3            # the end-of-frame points were not displaced


def test_probe_without_debugmods_display_measures_vertices_but_fails(monkeypatch, capsys, tmp_path):
    """No --vertex-only: the IoU half of the M1 check cannot run, so good vertices alone are no PASS."""
    from ssbot.probes import m1_projection

    oracle = ProjectionOracle()                             # hitbox.show fails like an oracle without DebugMod
    out = tmp_path / "m1_projection.json"
    monkeypatch.setattr("sys.argv", ["m1_projection", "--instance", str(oracle.instance), "--vertex-samples", "2",
                                     "--json", str(out)])
    monkeypatch.setattr(m1_projection, "results", [])
    try:
        assert m1_projection.main() == 1
    finally:
        oracle.close()
    text = capsys.readouterr().out
    assert "vertex check only" in text and any(line.startswith("FAIL: ") for line in text.splitlines())
    fails = [name for level, name, _ in m1_projection.results if level == "FAIL"]
    assert fails == ["DebugMod's hitbox display available (the IoU check needs it; --vertex-only skips it)"]
    import json

    numbers = json.loads(out.read_text())
    assert numbers["samples"] == 2 and numbers["vertex_render"]["p99"] < 1e-3


def test_probe_iou_end_to_end(monkeypatch, capsys, tmp_path):
    """The whole IoU path of the probe on the Scene: the window capture returns the synthetic DebugMod drawing."""
    from ssbot.io import game_window
    from ssbot.probes import m1_projection, shot

    oracle = ProjectionOracle(debugmod=True)
    capture = oracle.scene.capture

    def grab_frames(n, timeout_s=3.0, hwnd=None):
        time.sleep(0.05)  # the capture callback comes a few frames after the frame it shows
        return [(time.perf_counter_ns(), capture.copy()) for _ in range(n)]

    monkeypatch.setattr(shot, "grab_frames", grab_frames)
    monkeypatch.setattr(game_window, "find", lambda: 1)
    monkeypatch.setattr(game_window, "client_in_capture", lambda hwnd: (0, 0, W, H))
    monkeypatch.setattr("ssbot.tools.launcher.set_dpi_aware", lambda: None)
    monkeypatch.setattr(m1_projection, "results", [])
    out, png = tmp_path / "m1.json", tmp_path / "m1.png"
    monkeypatch.setattr("sys.argv", ["m1_projection", "--instance", str(oracle.instance), "--rounds", "2", "--frames", "2",
                                     "--vertex-samples", "2", "--still-s", "2", "--json", str(out), "--shot", str(png)])
    try:
        code = m1_projection.main()
    finally:
        oracle.close()
    text = capsys.readouterr().out
    assert code == 0, text
    import json

    numbers = json.loads(out.read_text())
    assert numbers["iou"]["n"] == 2 * 2 * 9 and numbers["iou"]["p5"] >= pc.IOU_MIN
    assert numbers["unmatched"] == {"Enemy": 2} and numbers["skipped"] == {"type Attack": 2, "kind edge": 2}
    assert numbers["samples"] == 4 and numbers["vertex_render"]["p99"] < 1e-3
    assert all((tmp_path / f"m1{suffix}.png").exists() for suffix in ("", "_overlay", "_masks"))
    # DebugMod's display was switched on with the panels hidden, then put back exactly as it was.
    shows = [a for name, a in oracle.calls if name == "hitbox.show"]
    assert shows[0] == {} and shows[1] == {"on": True, "ui": False}
    assert shows[-1] == {"mode": 0, "panels": ProjectionOracle.PANELS}
    assert (oracle.show, oracle.panels) == (0, ProjectionOracle.PANELS)


def test_probe_iou_fails_when_no_polygon_is_compared(monkeypatch, capsys, tmp_path):
    """Every capture skipped (here: a client area that does not match cam.screen, as a window larger than the desktop
    gives): good vertices alone must not make the M1 check PASS."""
    from ssbot.io import game_window
    from ssbot.probes import m1_projection, shot

    oracle = ProjectionOracle(debugmod=True)
    capture = oracle.scene.capture
    monkeypatch.setattr(shot, "grab_frames", lambda n, timeout_s=3.0, hwnd=None: [(time.perf_counter_ns(), capture.copy())])
    monkeypatch.setattr(game_window, "find", lambda: 1)
    monkeypatch.setattr(game_window, "client_in_capture", lambda hwnd: (0, 0, W, H - 20))
    monkeypatch.setattr("ssbot.tools.launcher.set_dpi_aware", lambda: None)
    monkeypatch.setattr(m1_projection, "results", [])
    out = tmp_path / "m1.json"
    monkeypatch.setattr("sys.argv", ["m1_projection", "--instance", str(oracle.instance), "--rounds", "1", "--frames", "1",
                                     "--vertex-samples", "1", "--still-s", "2", "--json", str(out)])
    try:
        code = m1_projection.main()
    finally:
        oracle.close()
    text = capsys.readouterr().out
    assert code == 1, text
    assert "client area 960x520 != cam.screen 960x540" in text
    fails = [name for level, name, _ in m1_projection.results if level == "FAIL"]
    assert fails == [f"at least {m1_projection.MIN_POLYS} polygon-frames compared (label = the drawn shape)"]
    import json

    numbers = json.loads(out.read_text())
    assert "iou" not in numbers and numbers["left_out"]["client area != cam.screen"] == 1
    assert numbers["vertex_render"]["p99"] < 1e-3
    assert (oracle.show, oracle.panels) == (0, ProjectionOracle.PANELS)
