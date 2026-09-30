"""Synthetic episodes for the aligner: a textured world seen by a moving camera with known timing, written through the
real Recorder (STATE with "cam") and VideoRecorder (thumbnails), so the tests exercise the on-disk formats too.

Timing model: STATE frame f ends at q_f = T0 + f * PERIOD + eof jitter; its image reaches the capture callback at
q_f + D_TRUE + capture jitter (the "frame" clock is 8-8.5 ms later). A capture listed in `stale` shows the previous
frame under its own timestamps, as a late composition would: its true offset is -1. Every 2nd or 3rd capture stale is
periodic judder (repeated and skipped frames); a run of them is a latency step.

Screen-fixed content: an unlabelled HUD block in the top-left corner (hud=True), and optionally a figure the camera
keeps near the image centre, like Hornet (hero="block": a static collider-sized block; "sprite": a larger 3-pose
animation around the collider; `lead` world units behind the camera in its direction of travel) with STATE "hero"
pos/box, and a labelled HUD (hud_state=True: bind orb, masks, silk spool, tool icons) with STATE "hud" rects.

Two parallax layers: far=(parallax, share) replaces the top `share` of the image (unlabelled HUD block included) with a
second texture at that parallax, a far background above a near ground layer; the figure and the labelled HUD are
drawn in front of both.

Frame marker (ssbot.record.marker): marker="tr" (a corner) draws the pattern of the frame each capture shows, with
12 px cells (3 px of the 160 px thumbnail), over everything and under the grain, and writes STATE "mk" as the oracle
does. marker_off: frames whose STATE has no "mk" and whose image has no marker (the marker off); hide_marker: capture
indices whose marker is covered by a gray patch (a marker that did not make it into the capture).
"""
from dataclasses import dataclass, field
from datetime import datetime

import cv2
import numpy as np

from ssbot.ipc.framing import MsgType
from ssbot.record import marker as mk
from ssbot.record import synthetic as syn
from ssbot.record.recorder import Recorder
from ssbot.record.video import VideoRecorder

SCREEN = (640, 360)
THUMB = 160
PPU = 30.0
PERIOD_NS = 16_666_667
T0_NS = 5_000_000_000_000        # ~83 min of QPC uptime
D_TRUE_NS = 23_300_000
FRAME_CLOCK_NS = 8_000_000
WHEN = datetime(2026, 9, 30, 12, 0, 0)
MARKER_CELL = 12                 # client px: 3 px of the thumbnail


@dataclass
class Episode:
    path: object
    q_ns: dict                    # STATE frame -> end-of-frame ns (all frames, including dropped STATEs)
    capture_t: list               # arrival ns per written capture
    capture_frame: list           # game frame each capture truly shows
    capture_label: list           # game frame each capture is timed for (differs from the shown one when stale)
    valid_D: dict = field(default_factory=dict)  # clock -> (lo, hi]: every D in it matches every non-stale capture
    extra: dict = field(default_factory=dict)

    def true_k(self, off, trk) -> np.ndarray:
        """Per capture: the frame it shows - the frame it was matched to (only meaningful where labelled)."""
        lab = np.where(off.label >= 0, trk.f[np.clip(off.label, 0, None)], -1)
        return np.asarray(self.capture_frame) - lab


def texture(h: int, w: int, seed: int) -> np.ndarray:
    """Multi-scale smooth noise with enough detail at thumbnail scale."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    for sigma, amp in ((24, 1.0), (8, 0.8), (3, 0.6)):
        out += amp * cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigma) * sigma
    out = (out - out.mean()) / (out.std() + 1e-6)
    return np.clip(128 + 45 * out, 0, 255).astype(np.uint8)


def trajectory(frames: int, seed: int, still: tuple[int, int] | None = None, jump_at: int | None = None
               ) -> np.ndarray:
    """(frames, 2) camera x, y in world units: piecewise-constant velocity (run / dash / stop, random durations and
    vertical hops), kept inside +-12 u so it stays on the texture. still = (a, b): frames a..b-1 do not move. jump_at:
    the camera teleports 20 u there (a respawn / scene change)."""
    rng = np.random.default_rng(seed)
    pos = np.zeros((frames, 2))
    v = np.zeros(2)
    left = 0
    x = np.zeros(2)
    for f in range(frames):
        if left <= 0:
            left = int(rng.integers(6, 40))
            speed = rng.choice([0.0, 8.25, 8.25, 14.0, 28.0]) / 60 * rng.choice([-1, 1])
            if abs(x[0] + speed * left) > 12:
                speed = -speed
            v = np.array([speed, rng.choice([0.0, 0.0, 6.0, -6.0]) / 60])
            if abs(x[1] + v[1] * left) > 5:
                v[1] = -v[1]
        if still and still[0] <= f < still[1]:
            step = np.zeros(2)
        else:
            step = v
        x = x + step
        if jump_at is not None and f == jump_at:
            x = x + np.array([20.0, 0.0])
        pos[f] = x
        left -= 1
    return pos


def render(tex: np.ndarray, cx: float, cy: float, parallax: float = 1.0, hud: bool = True) -> np.ndarray:
    """The client image (gray, SCREEN) of the camera at (cx, cy): world (X, Y) on the layer is at texture pixel
    (X * PPU * parallax, -Y * PPU * parallax) from the texture centre."""
    w, h = SCREEN
    th, tw = tex.shape
    tx = tw / 2 + cx * PPU * parallax - w / 2
    ty = th / 2 - cy * PPU * parallax - h / 2
    M = np.array([[1.0, 0.0, tx], [0.0, 1.0, ty]])
    img = cv2.warpAffine(tex, M, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT)
    if hud:
        img[12:40, 12:150] = 235  # a static HUD block that must not win the registration
        img[18:34, 18:60] = 20
    return img


HERO_BOX = (16 / PPU, 34 / PPU)  # collider w, h in world units: 16x34 px of the 640x360 client


def hero_track(cam: np.ndarray, lead: float) -> np.ndarray:
    """(frames, 2) hero centre: `lead` units behind the camera in its (smoothed) direction of travel, as a camera
    that looks ahead of a running figure shows her; 0 keeps her at the image centre."""
    if lead == 0.0:
        return cam.copy()
    v = np.r_[0.0, np.diff(cam[:, 0])]
    d = np.zeros(len(cam))
    for i in range(1, len(cam)):  # eases to the new side over ~20 frames
        d[i] = d[i - 1] + 0.1 * (np.sign(v[i]) - d[i - 1]) if v[i] != 0 else d[i - 1]
    return cam - np.c_[lead * d, np.zeros(len(cam))]


def _to_px(cx: float, cy: float, x: float, y: float) -> tuple[float, float]:
    """Client px of world (x, y) under the camera at (cx, cy) (the z = 0 plane, SCREEN, PPU)."""
    return SCREEN[0] / 2 + (x - cx) * PPU, SCREEN[1] / 2 - (y - cy) * PPU


def draw_hero(img: np.ndarray, cx: float, cy: float, hx: float, hy: float, kind: str, pose: int) -> None:
    """The figure at world (hx, hy): "block" fills the collider (dark, with a bright patch at the head); "sprite" is a
    dark body with a bright head and a cloak that sticks out of the collider by up to ~0.35 u, in one of 3 poses."""
    x, y = _to_px(cx, cy, hx, hy)
    w, h = HERO_BOX[0] * PPU, HERO_BOX[1] * PPU
    x0, y0, x1, y1 = (int(round(v)) for v in (x - w / 2, y - h / 2, x + w / 2, y + h / 2))
    if kind == "block":
        img[y0:y1, x0:x1] = 30
        img[y0 + 2:y0 + 10, x0 + 4:x1 - 4] = 230
        return
    sway = (-4, 3, 9)[pose % 3]                                         # cloak, behind and below
    pts = np.array([[x0 + 1, y0 + 12], [x0 - 7 + sway, y1 + 4], [x1 + 2, y1 + 6], [x1 - 1, y0 + 14]], np.int32)
    cv2.fillConvexPoly(img, pts, 150)
    img[y0 + 9:y1 - 6, x0 + 3:x1 - 3] = 40                              # body
    cv2.circle(img, (int(round(x)), y0 + 6), 6, 235, -1)              # head
    cv2.line(img, (x1 - 2, y0 + 16), (x1 + 8, y0 + 4 + 2 * (pose % 3)), 250, 2)  # needle


HUD = {  # client px [x0, y0, x1, y1] of a labelled HUD (hud_state=True), below the unlabelled block of hud=True
    "bind_orb": [16, 58, 62, 104],
    "masks": [[70 + 16 * i, 60, 82 + 16 * i, 76] for i in range(5)],
    "spool": [70, 82, 194, 92],
    "tools": [[16, 300, 38, 322], [46, 300, 68, 322]],
}


def draw_hud(img: np.ndarray) -> None:
    x0, y0, x1, y1 = HUD["bind_orb"]
    cv2.circle(img, ((x0 + x1) // 2, (y0 + y1) // 2), (x1 - x0) // 2, 30, -1)
    cv2.circle(img, ((x0 + x1) // 2, (y0 + y1) // 2), (x1 - x0) // 2 - 5, 215, -1)
    for x0, y0, x1, y1 in HUD["masks"]:
        img[y0:y1, x0:x1] = 25
        img[y0 + 2:y1 - 2, x0 + 2:x1 - 2] = 245
    x0, y0, x1, y1 = HUD["spool"]
    img[y0:y1, x0:x1] = 70
    for i in range(6):  # silk chunks
        img[y0 + 2:y1 - 2, x0 + 4 + 13 * i:x0 + 13 + 13 * i] = 225
    for n, (x0, y0, x1, y1) in enumerate(HUD["tools"]):
        img[y0:y1, x0:x1] = 200 if n == 0 else 55
        img[y0 + 5:y1 - 5, x0 + 5:x1 - 5] = 100


def hud_state_dict() -> dict:
    """STATE "hud" (HudProbe layout) of the labelled HUD."""
    x0, y0, x1, y1 = HUD["spool"]
    slots = [[x0 + 8.5 + 13 * i, (y0 + y1) / 2] for i in range(9)]
    return {"hidden": False, "vis": {"canvas": True, "cams": True, "global_hide": False, "reduced": False},
            "cam": None, "masks": [[i + 1, True, "Idle", list(map(float, r))] for i, r in enumerate(HUD["masks"])],
            "blue": [], "spool": {"parts": 3, "slots": slots, "pitch": 13.0, "chunks": slots[:6],
                                  "chunk_rect": [x0 + 4.0, y0 + 2.0, x0 + 13.0, y1 - 2.0], "notch": None},
            "bind_orb": list(map(float, HUD["bind_orb"])),
            "tools": [[0, "Straight Pin", True, list(map(float, HUD["tools"][0]))],
                      [2, "Sting Shard", True, list(map(float, HUD["tools"][1]))]]}


def make(tmp_path, *, seconds: float = 25.0, seed: int = 1, parallax: float = 1.0, stale: set[int] = frozenset(),
         drop_states: set[int] = frozenset(), drop_captures: set[int] = frozenset(), still=None, jump_at=None,
         eof_jitter_ns: int = 1_000_000, cap_jitter_ns: int = 4_000_000, noise: float = 2.0, episode: str = "ep",
         hud: bool = True, hero: str | None = None, lead: float = 0.0, hud_state: bool = False,
         labels: bool = True, far: tuple[float, float] | None = None, marker: str | None = None,
         marker_off: set[int] = frozenset(), hide_marker: set[int] = frozenset()) -> Episode:
    """Write an episode with STATE frames 1000.. and one capture per frame (minus drop_captures). labels=False draws
    the hero and the labelled HUD but leaves them out of STATE."""
    rng = np.random.default_rng(seed + 100)
    n = int(seconds * 60)
    frames = np.arange(1000, 1000 + n)
    cam = trajectory(n, seed, still, jump_at)
    her = hero_track(cam, lead)
    tex = texture(1400, 2400, seed)
    tex_far = texture(1400, 2400, seed + 50) if far else None
    q = {int(f): T0_NS + int(f) * PERIOD_NS + int(rng.integers(-eof_jitter_ns, eof_jitter_ns + 1)) for f in frames}
    geom = mk.Geometry.place(SCREEN, marker, MARKER_CELL) if marker else None

    rec = Recorder(None, out_dir=tmp_path, profile="TEST", episode=episode, hello=syn.hello(), when=WHEN,
                   min_free_gb=0, queue_size=1_000_000).start()
    for i, f in enumerate(frames):
        if int(f) in drop_states:
            continue
        s = syn.state(int(f), hero=False, ents=False)
        s["q"] = q[int(f)] * syn.QPC_FREQ // 1_000_000_000
        s["cam"] = syn.camera(*cam[i], screen=SCREEN, ppu=PPU)
        if hero and labels:
            hx, hy = her[i]
            bw, bh = HERO_BOX
            s["hero"] = {"pos": [float(hx), float(hy), 0.004], "facing": 1,
                         "box": [float(hx - bw / 2), float(hy - bh / 2), float(hx + bw / 2), float(hy + bh / 2)]}
        if hud_state and labels:
            s["hud"] = hud_state_dict()
        if jump_at is not None and i >= jump_at:
            s["game"]["scene"] = s["game"]["scene_raw"] = "Tut_02"
        if geom is not None and int(f) not in marker_off:
            s["mk"] = {"drawn": True, "corner": marker, "cell": MARKER_CELL, "rect": list(geom.rect),
                       "grid": [mk.ROWS, mk.COLS], "us": 20.0}
        rec.on_raw(MsgType.STATE, syn.wire(MsgType.STATE, i + 1, s))
    rec.close()

    vid = VideoRecorder(rec.path, width=THUMB, queue_size=1_000_000).start()
    ep = Episode(rec.path, q, [], [], [])
    bounds = {"arrival": [-2**62, 2**62], "frame": [-2**62, 2**62]}
    grain = [rng.normal(0, noise, (SCREEN[1], SCREEN[0])).astype(np.float32) for _ in range(7)]  # sensor-like noise
    for i, f in enumerate(frames):
        if int(f) in drop_captures:
            continue
        t = q[int(f)] + D_TRUE_NS + int(rng.integers(0, cap_jitter_ns + 1))
        ts = t + FRAME_CLOCK_NS + int(rng.integers(0, 500_000))
        shown = int(f) - 1 if i in stale and i > 0 else int(f)
        j = shown - 1000
        img = render(tex, cam[j, 0], cam[j, 1], parallax, hud)
        if far:
            cut = int(round(far[1] * SCREEN[1]))
            img[:cut] = render(tex_far, cam[j, 0], cam[j, 1], far[0], hud=False)[:cut]
        if hero:
            draw_hero(img, cam[j, 0], cam[j, 1], her[j, 0], her[j, 1], hero, j // 6)
        if hud_state:
            draw_hud(img)
        if geom is not None and shown not in marker_off:
            mk.draw(img, shown, geom)
            if i in hide_marker:
                x0, y0, x1, y1 = (int(v) for v in geom.rect)
                img[y0:y1, x0:x1] = 128
        img = np.clip(img.astype(np.float32) + grain[i % len(grain)], 0, 255).astype(np.uint8)
        vid.push(img, t, ts)
        ep.capture_t.append(t)
        ep.capture_frame.append(shown)
        ep.capture_label.append(int(f))
        if shown == int(f):
            for clock, tc in (("arrival", t), ("frame", ts)):
                b = bounds[clock]
                b[1] = min(b[1], tc - q[int(f)])
                if int(f) + 1 in q:
                    b[0] = max(b[0], tc - q[int(f) + 1])
    vid.close()
    ep.valid_D = {k: tuple(v) for k, v in bounds.items()}
    ep.extra["cam"] = cam
    ep.extra["hero"] = her
    return ep
