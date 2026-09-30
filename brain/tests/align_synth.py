"""Synthetic episodes for the aligner: a textured world seen by a moving camera with known timing, written through the
real Recorder (STATE with "cam") and VideoRecorder (thumbnails), so the tests exercise the on-disk formats too.

Timing model: STATE frame f ends at q_f = T0 + f * PERIOD + eof jitter; its image reaches the capture callback at
q_f + D_TRUE + capture jitter (the "frame" clock is 8 ms later). A capture listed in `stale` shows the previous frame
under its own timestamps, as a late composition would: its true offset is -1.
"""
from dataclasses import dataclass, field
from datetime import datetime

import cv2
import numpy as np

from ssbot.ipc.framing import MsgType
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


@dataclass
class Episode:
    path: object
    q_ns: dict                    # STATE frame -> end-of-frame ns (all frames, including dropped STATEs)
    capture_t: list               # arrival ns per written capture
    capture_frame: list           # game frame each capture truly shows
    capture_label: list           # game frame each capture is timed for (differs from the shown one when stale)
    valid_D: tuple = ()           # (lo, hi]: every D in it matches every non-stale capture to its frame
    extra: dict = field(default_factory=dict)


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


def make(tmp_path, *, seconds: float = 25.0, seed: int = 1, parallax: float = 1.0, stale: set[int] = frozenset(),
         drop_states: set[int] = frozenset(), drop_captures: set[int] = frozenset(), still=None, jump_at=None,
         eof_jitter_ns: int = 1_000_000, cap_jitter_ns: int = 4_000_000, noise: float = 2.0, episode: str = "ep",
         hud: bool = True) -> Episode:
    """Write an episode with STATE frames 1000.. and one capture per frame (minus drop_captures)."""
    rng = np.random.default_rng(seed + 100)
    n = int(seconds * 60)
    frames = np.arange(1000, 1000 + n)
    cam = trajectory(n, seed, still, jump_at)
    tex = texture(1400, 2400, seed)
    q = {int(f): T0_NS + int(f) * PERIOD_NS + int(rng.integers(-eof_jitter_ns, eof_jitter_ns + 1)) for f in frames}

    rec = Recorder(None, out_dir=tmp_path, profile="TEST", episode=episode, hello=syn.hello(), when=WHEN,
                   min_free_gb=0, queue_size=1_000_000).start()
    for i, f in enumerate(frames):
        if int(f) in drop_states:
            continue
        s = syn.state(int(f), hero=False, ents=False)
        s["q"] = q[int(f)] * syn.QPC_FREQ // 1_000_000_000
        s["cam"] = syn.camera(*cam[i], screen=SCREEN, ppu=PPU)
        if jump_at is not None and i >= jump_at:
            s["game"]["scene"] = s["game"]["scene_raw"] = "Tut_02"
        rec.on_raw(MsgType.STATE, syn.wire(MsgType.STATE, i + 1, s))
    rec.close()

    vid = VideoRecorder(rec.path, width=THUMB, queue_size=1_000_000).start()
    ep = Episode(rec.path, q, [], [], [])
    lo, hi = -2**62, 2**62
    grain = [rng.normal(0, noise, (SCREEN[1], SCREEN[0])).astype(np.float32) for _ in range(7)]  # sensor-like noise
    for i, f in enumerate(frames):
        if int(f) in drop_captures:
            continue
        t = q[int(f)] + D_TRUE_NS + int(rng.integers(0, cap_jitter_ns + 1))
        shown = int(f) - 1 if i in stale and i > 0 else int(f)
        j = shown - 1000
        img = render(tex, cam[j, 0], cam[j, 1], parallax, hud).astype(np.float32)
        img = np.clip(img + grain[i % len(grain)], 0, 255).astype(np.uint8)
        vid.push(img, t, t + FRAME_CLOCK_NS + int(rng.integers(0, 500_000)))
        ep.capture_t.append(t)
        ep.capture_frame.append(shown)
        ep.capture_label.append(int(f))
        if shown == int(f):
            hi = min(hi, t - q[int(f)])
            if int(f) + 1 in q:
                lo = max(lo, t - q[int(f) + 1])
    vid.close()
    ep.valid_D = (lo, hi)
    ep.extra["cam"] = cam
    return ep
