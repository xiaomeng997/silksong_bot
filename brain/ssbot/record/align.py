"""Frame/label alignment of a recorded episode (DESIGN §3.1.4 C4; M1 exit: >= 99.5 % of frames at offset 0).

Input: an episode folder with the oracle STATE stream (ssbot.record.recorder) and the gray thumbnail video
(ssbot.record.video). STATE "q" is the raw QPC at end of frame (ticks of HELLO qpc_freq); every captured frame has its
arrival time and WGC's SystemRelativeTime (the "frame" clock), both QPC in ns. The frame clock is the gate clock, as
DESIGN §3.1.4 has it: WGC stamps it on the composed frame (P8: 7-10 ms after the arrival, apparently the target present
time), while the arrival also carries the jitter of the callback itself (staging copy, GIL). D is calibrated for each
clock, and the arrival clock's result is reported as a cross-check.

1. Registration: the camera motion between consecutive captures, phase correlation of the thumbnails (Hann window;
   the peak refined by an upsampled DFT, see PhaseCorrelator), scaled to client pixels. An increment with a weak peak
   or from a flat image (fades, black screens) is not trusted.
2. Oracle camera track: per STATE frame, the image motion of the gameplay plane (z = 0) at the image centre from that
   frame's render-time V/P (the projection of tools/projector), summed into a track in client pixels. It breaks at
   scene changes, frames without a camera and camera jumps (respawns).
3. Matching (C4): capture i gets the newest STATE frame whose predicted present time t_eof + D is <= its capture time.
4. Offsets. Windows: over +-W captures, fit the video increments = a * the oracle increments shifted by k frames, for
   every integer k in [-K, K] (a absorbs parallax: the registration locks onto whichever layer dominates the image). A
   window is decisive when one k fits clearly better; that needs the camera to change speed inside it, because a
   constant offset is invisible in constant motion. Anomalies: an increment that a * the oracle increment explains at
   no k. Two in a row whose sum is explained are one capture off (stale or glitched): they are left out of the fits.
   Any other one (a latency step, i.e. a repeated or skipped frame after which the offset stays changed) breaks the
   track, so no window straddles it. Captures: each capture's video position is compared with the oracle positions at
   every k, with the track constant taken from its +-h neighbours at the offset of the nearest decisive window, if
   every decisive window within W agrees on it, separately from the left and from the right neighbours (a
   registration glitch next to a capture makes the two disagree: "split").
5. Calibrating D: a coarse scan picks the D whose matching best correlates the video and oracle increments. Then every
   clearly judged capture, with true frame g in STATE row r, needs t - t_eof[r + 1] < D <= t - t_eof[r]; D becomes the
   middle of the interval most captures agree on, and step 4 runs again.
6. The metric: captures at offset 0 / judgeable captures (PASS >= 99.5 %). Left out, for reasons that do not depend on
   whether video and oracle agree: captures without a label, whose next STATE frame is missing (they may show a frame
   without a label), whose candidate positions around the label lie closer together than min_sep thumbnail px (a slow
   or still camera), or that no window within W could judge even with a perfect video (too few trusted increments, or
   camera motion that tells no k apart: "no_evidence"). Every other capture is judgeable, and one that was not judged
   (no agreeing decisive window, split) counts as not at offset 0: periodic repeated or skipped frames spoil every fit
   around them, and would otherwise vanish from the share. At least min_informative judged captures, and
   min_coverage of all captures, are needed for a verdict.

    python -m ssbot.record.align <episode> [--clock frame|arrival] [--json] [--dump]     (exit 1 unless PASS)
"""
import argparse
import json
import math
import sys
import warnings
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2  # comes with windows-capture
import numpy as np

from ssbot.record.recorder import RecordingReader
from ssbot.record.video import FrameInfo, VideoReader

THRESHOLD = 0.995

# Per-capture status of an offsets() run. OK captures are judged; NO_WINDOW and SPLIT ones could have been judged
# (they are labelled, moving and have evidence) but were not, which misalignment itself causes (periodic repeated or
# skipped frames spoil every fit), so they count against the share. The other statuses do not depend on whether
# video and oracle agree and are left out.
OK, NO_LABEL, STATE_GAP, NO_WINDOW, LOW_MOTION, SPLIT, NO_EVIDENCE = range(7)
STATUS = ("ok", "no_label", "state_gap", "no_window", "low_motion", "split", "no_evidence")
UNJUDGED = (NO_WINDOW, SPLIT)
GATE_CLOCK = "frame"  # DESIGN §3.1.4: WGC SystemRelativeTime with a calibrated offset; "arrival" is the cross-check


@dataclass
class Params:
    max_offset: int = 3              # K: frame offsets searched on each side
    window: int = 30                 # W: captures on each side of a window centre
    neighbours: int = 4              # h: captures on each side that give a capture its track constant
    min_sep: float = 0.5             # thumbnail px between a capture's candidate positions, else low motion
    registration: str = "updft"      # PhaseCorrelator; "cv2" = cv2.phaseCorrelate (centroid peak, ~10x noisier)
    min_response: float = 0.2        # correlation peak below which an increment is not trusted (unrelated ~0.1)
    min_contrast: float = 3.0        # gray std (0-255) below which a thumbnail counts as flat
    jump_frac: float = 0.2           # an oracle camera step above this share of the screen width breaks the track
    decisive: float = 36.0           # window: SSE(second best k) - SSE(best k) >= decisive * noise variance
    outlier: float = 6.0             # anomaly: an increment max(min_sep / 2, outlier * window noise) from every k
    noise_floor: float = 0.02        # thumbnail px: lower bound of a window's noise estimate
    min_increments: int = 20         # trusted increments a window fit needs
    a_range: tuple[float, float] = (0.2, 5.0)
    scan_ms: tuple[float, float] = (-50.0, 250.0)   # coarse search range of D
    scan_step_ms: float = 0.5
    threshold: float = THRESHOLD
    min_informative: int = 300
    min_coverage: float = 0.5        # judged captures must also be at least this share of all captures


# ---- inputs --------------------------------------------------------------------------------------------

@dataclass
class VideoMotion:
    """Registration of consecutive captures. Row i describes capture i and the step from capture i - 1 to it."""
    t_arrival: np.ndarray    # (N,) ns
    t_frame: np.ndarray      # (N,) ns (0 when the capture had no SystemRelativeTime)
    seq: np.ndarray          # (N,) callback counter
    inc: np.ndarray          # (N, 2) camera motion since the previous capture, client px (x right, y down); row 0 = 0
    ok: np.ndarray           # (N,) inc is trusted
    response: np.ndarray     # (N,) phase-correlation peak (0 for row 0 / size changes)
    contrast: np.ndarray     # (N,) gray std of the thumbnail
    scale: np.ndarray        # (N,) client px per thumbnail px
    src: np.ndarray          # (N, 2) client size the thumbnail was made from


class PhaseCorrelator:
    """Generalized phase correlation with the peak refined by a local upsampled DFT (Guizar-Sicairos et al. 2008).

    The cross-power spectrum X = B * conj(A) is divided by sqrt(|X|) ("half" whitening): full whitening (classic phase
    correlation, cv2.phaseCorrelate) gives every frequency the same weight, and the noisiest ones, where the window edges
    and resampling leave their phase errors, then cost ~0.09 px sd even on exact Fourier shifts; half whitening keeps the
    sharp peak and robustness to brightness changes at ~0.01 px. The correlation is then evaluated on a 1/up px grid
    within +-1 px of the integer peak, and a parabola through the best grid point and its neighbours finishes it.
    cv2.phaseCorrelate's 5x5 centroid also pulls sub-pixel shifts towards integers: on the synthetic scenes of
    tests/align_synth.py its error sd is ~0.17 thumbnail px, here ~0.01. Cost ~0.5 ms per 160x90 frame, ~1.5 ms at
    320x180 (one spectrum per frame). The peak is normalized by its bound sum|X|^0.5: 1 for a pure shift, ~0.1 for
    unrelated images."""

    def __init__(self, shape: tuple[int, int], up: int = 10):
        h, w = shape
        self.h, self.w = h, w
        self.win = cv2.createHanningWindow((w, h), cv2.CV_64F)
        n = 2 * up + 1
        self.offs = (np.arange(n) - up) / up
        self.ky = np.fft.fftfreq(h)
        self.kx = np.fft.rfftfreq(w)
        self.c = np.full(len(self.kx), 2.0)  # a half spectrum: every column but DC (and Nyquist) stands for two
        self.c[0] = 1.0
        if w % 2 == 0:
            self.c[-1] = 1.0

    def spectrum(self, img: np.ndarray) -> np.ndarray:
        x = img.astype(np.float64)
        return np.fft.rfft2((x - x.mean()) * self.win)

    def shift(self, A: np.ndarray, B: np.ndarray) -> tuple[float, float, float]:
        """(dx, dy, peak) of how far the content moved from the image of A to that of B."""
        R = B * np.conj(A)
        mag = np.sqrt(np.abs(R))
        R /= np.maximum(mag, 1e-12)
        bound = float((mag * self.c).sum())
        r = np.fft.irfft2(R, s=(self.h, self.w))
        py, px = np.unravel_index(int(np.argmax(r)), r.shape)
        sy = py if py <= self.h // 2 else py - self.h
        sx = px if px <= self.w // 2 else px - self.w
        ey = np.exp(2j * np.pi * np.outer(sy + self.offs, self.ky))
        ex = np.exp(2j * np.pi * np.outer(self.kx, sx + self.offs))
        loc = (ey @ (R * self.c) @ ex).real
        iy, ix = np.unravel_index(int(np.argmax(loc)), loc.shape)
        step = self.offs[1] - self.offs[0]
        fx = _vertex(loc[iy, ix - 1], loc[iy, ix], loc[iy, ix + 1]) if 0 < ix < loc.shape[1] - 1 else 0.0
        fy = _vertex(loc[iy - 1, ix], loc[iy, ix], loc[iy + 1, ix]) if 0 < iy < loc.shape[0] - 1 else 0.0
        return sx + self.offs[ix] + fx * step, sy + self.offs[iy] + fy * step, float(loc[iy, ix] / max(bound, 1e-12))


def _vertex(m: float, z: float, p: float) -> float:
    """Offset of a parabola's vertex through (-1, m), (0, z), (1, p) from 0 (0 if it is not a maximum)."""
    d = m - 2 * z + p
    return 0.0 if d >= 0 else float(np.clip(0.5 * (m - p) / d, -0.5, 0.5))


def register(frames: Iterable[tuple[FrameInfo, np.ndarray]], params: Params = Params(),
             progress: Callable[[int], None] | None = None) -> VideoMotion:
    """Phase-correlate every capture with the previous one. The correlation gives how far the content moved; the
    camera moved the other way. params.registration "cv2" uses cv2.phaseCorrelate instead (for comparison)."""
    t, ts, seq, inc, resp, con, scale, src, ok = [], [], [], [], [], [], [], [], []
    prev = prev_con = prev_spec = None
    tools: dict[tuple[int, int], Any] = {}
    use_cv2 = params.registration == "cv2"
    for i, (info, img) in enumerate(frames):
        c = float(img.std())
        sx, sy = info.src_w / info.w, info.src_h / info.h
        tool = tools.get(img.shape)
        if tool is None:
            tool = tools[img.shape] = (cv2.createHanningWindow((img.shape[1], img.shape[0]), cv2.CV_32F) if use_cv2
                                       else PhaseCorrelator(img.shape))
        cur = img.astype(np.float32) if use_cv2 else tool.spectrum(img)
        step, r, good = (0.0, 0.0), 0.0, False
        if prev is not None and prev.shape == img.shape:
            if use_cv2:
                (dx, dy), r = cv2.phaseCorrelate(prev_spec, cur, tool)
            else:
                dx, dy, r = tool.shift(prev_spec, cur)
            step = (-dx * sx, -dy * sy)
            good = bool(np.isfinite(r) and r >= params.min_response and c >= params.min_contrast
                        and prev_con >= params.min_contrast)
        prev, prev_con, prev_spec = img, c, cur
        t.append(info.arrival_ns)
        ts.append(info.frame_ns)
        seq.append(info.seq)
        inc.append(step)
        resp.append(r)
        con.append(c)
        scale.append(sx)
        src.append((info.src_w, info.src_h))
        ok.append(good)
        if progress is not None and i % 5000 == 4999:
            progress(i + 1)
    return VideoMotion(np.asarray(t, np.int64), np.asarray(ts, np.int64), np.asarray(seq, np.int64),
                       np.asarray(inc, np.float64).reshape(-1, 2), np.asarray(ok, bool), np.asarray(resp),
                       np.asarray(con), np.asarray(scale, np.float64), np.asarray(src, np.int64).reshape(-1, 2))


@dataclass
class OracleTrack:
    """The oracle camera as the image sees it. Row r is STATE frame f[r]."""
    f: np.ndarray            # (R,) frame numbers, ascending, unique
    t_eof: np.ndarray        # (R,) end of frame, ns
    pos: np.ndarray          # (R, 2) camera track in client px (x right, y down); NaN without a camera
    seg: np.ndarray          # (R,) track segment (positions are only comparable inside one); -1 without a camera
    screen: np.ndarray       # (R, 2) cam.screen; 0 without a camera
    breaks: dict = field(default_factory=dict)   # why segments started: scene / jump / no_cam / screen

    def row_of(self) -> np.ndarray:
        """Dense frame -> row lookup over f[0] .. f[-1]; -1 for frames without a STATE."""
        out = np.full(int(self.f[-1] - self.f[0]) + 1, -1, np.int64)
        out[self.f - self.f[0]] = np.arange(len(self.f))
        return out


def _cols(m16: np.ndarray) -> np.ndarray:
    """(R, 16) column-major floats -> (R, 4, 4) matrices (projector.mat4, batched)."""
    return m16.reshape(-1, 4, 4).transpose(0, 2, 1)


def _to_image(M: np.ndarray, pts: np.ndarray, rect: np.ndarray, screen: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Batched projector.project: row r's world point pts[r] (x, y, z, 1) under row r's P*V -> image px, in front."""
    clip = np.einsum("rij,rj->ri", M, pts)
    w = clip[:, 3]
    front = w > 1e-6
    ndc = clip[:, :2] / np.where(front, w, 1.0)[:, None]
    x = (rect[:, 0] + (ndc[:, 0] + 1.0) * 0.5 * rect[:, 2]) * screen[:, 0]
    y = screen[:, 1] - (rect[:, 1] + (ndc[:, 1] + 1.0) * 0.5 * rect[:, 3]) * screen[:, 1]
    return np.stack([x, y], axis=1), front


def oracle_track(states: Iterable[dict], qpc_freq: int, jump_frac: float = Params.jump_frac) -> OracleTrack:
    """Build the track from STATE dicts (only f, q, cam and game["scene"] are read). The step of row r is the image
    motion, between frames r - 1 and r, of the z = 0 point in front of the camera at r - 1, both under their own
    render-time matrices: exact for zoom (fov animations) and shake, which V/P carry."""
    rows: dict[int, tuple] = {}
    for s in states:
        f, q = s.get("f"), s.get("q")
        if not isinstance(f, int) or not isinstance(q, int) or f in rows:
            continue
        cam = s.get("cam")
        game = s.get("game") or {}
        good = isinstance(cam, dict) and all(isinstance(cam.get(k), list) for k in ("V", "P", "rect", "screen"))
        # Python ints: q * 1e9 overflows int64 (and float64 loses ms) once the machine has been up for days.
        rows[f] = (q * 1_000_000_000 // qpc_freq, cam if good else None, game.get("scene"))
    fs = np.asarray(sorted(rows), np.int64)
    R = len(fs)
    t_eof = np.asarray([rows[f][0] for f in fs], np.int64)
    has = np.asarray([rows[f][1] is not None for f in fs], bool)
    scene = [rows[f][2] for f in fs]
    V16 = np.zeros((R, 16))
    P16 = np.zeros((R, 16))
    rect = np.zeros((R, 4))
    screen = np.zeros((R, 2))
    for r, f in enumerate(fs):
        cam = rows[f][1]
        if cam is not None:
            V16[r], P16[r], rect[r], screen[r] = cam["V"], cam["P"], cam["rect"], cam["screen"][:2]
    V, P = _cols(V16), _cols(P16)
    M = P @ V
    step = np.zeros((R, 2))
    start = np.ones(R, bool)
    why = {"no_cam": 0, "scene": 0, "screen": 0, "jump": 0}
    if R > 1:
        Vi = np.linalg.inv(np.where(has[:, None, None], V, np.eye(4)))
        eye = Vi[:, :3, 3]                                   # camera position (world)
        anchor = np.c_[eye[:-1, 0], eye[:-1, 1], np.zeros(R - 1), np.ones(R - 1)]
        now, f1 = _to_image(M[1:], anchor, rect[1:], screen[1:])
        before, f0 = _to_image(M[:-1], anchor, rect[:-1], screen[:-1])
        step[1:] = -(now - before)                           # the content moves the other way
        both = has[1:] & has[:-1]
        same_scene = np.asarray([a == b for a, b in zip(scene[1:], scene[:-1])], bool)
        same_screen = (screen[1:] == screen[:-1]).all(axis=1)
        jump = np.hypot(step[1:, 0], step[1:, 1]) > jump_frac * np.maximum(screen[1:, 0], 1)
        start[1:] = ~(both & same_scene & same_screen & ~jump & f1 & f0)
        why = {"no_cam": int((~both).sum()), "scene": int((both & ~same_scene).sum()),
               "screen": int((both & same_scene & ~same_screen).sum()),
               "jump": int((both & same_scene & same_screen & jump).sum())}
    start |= ~has
    seg = np.where(has, np.cumsum(start & has) - 1, -1)
    step[start] = 0.0
    csum = np.cumsum(step, axis=0)
    first = np.maximum.accumulate(np.where(start, np.arange(R), 0)) if R else np.zeros(0, np.int64)
    pos = csum - csum[first]
    pos[~has] = np.nan
    return OracleTrack(fs, t_eof, pos, seg, np.where(has[:, None], screen, 0.0), why)


def match(t_cap: np.ndarray, t_eof: np.ndarray, D: int) -> np.ndarray:
    """Row of the newest STATE frame whose predicted present time t_eof + D is <= the capture time; -1 if none."""
    return np.searchsorted(t_eof + D, t_cap, side="right") - 1


# ---- offsets at one D ----------------------------------------------------------------------------------

@dataclass
class Offsets:
    D: int                   # ns
    label: np.ndarray        # (N,) matched STATE row, -1 if none
    status: np.ndarray       # (N,) index into STATUS
    k: np.ndarray            # (N,) true frame - matched frame, where status == OK
    clear: np.ndarray        # (N,) the fit at k clearly beats every other k, from both sides
    k_window: np.ndarray     # (N,) best offset of the window centred here, where decisive
    decisive: np.ndarray     # (N,)
    a: np.ndarray            # (N,) scale of the capture's reference window (NaN without one)
    resid: np.ndarray        # (N,) distance of the video position from the prediction at k, client px
    sep: np.ndarray          # (N,) distance between the predictions at the label (k = 0) and the nearest other k
    sigma: np.ndarray        # (N,) noise estimate of decisive windows, client px (NaN elsewhere)
    anomaly: np.ndarray      # (N,) increment into capture i: 1 one capture off (left out of the fits), 2 track break


def _prefix(x: np.ndarray) -> np.ndarray:
    return np.concatenate([np.zeros((1,) + x.shape[1:]), np.cumsum(x, axis=0)])


def _segments(link: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """First and last capture of every capture's run of captures joined by link (link[i]: i - 1 -> i)."""
    N = len(link)
    idx = np.arange(N)
    start = ~link
    first = np.maximum.accumulate(np.where(start, idx, 0))
    last = np.minimum.accumulate(np.where(np.r_[start[1:], True], idx, N - 1)[::-1])[::-1]
    return first, last


def _nearest(mask: np.ndarray, first: np.ndarray, last: np.ndarray, W: int) -> tuple[np.ndarray, np.ndarray]:
    """(index, found): the nearest capture with mask in the same run, at most W captures away (0 if none)."""
    N = len(mask)
    idx = np.arange(N)
    big = N + W + 1
    prv = np.maximum.accumulate(np.where(mask, idx, -1))
    nxt = np.minimum.accumulate(np.where(mask, idx, N)[::-1])[::-1]
    dp = np.where((prv >= 0) & (prv >= first), idx - prv, big)
    dn = np.where((nxt < N) & (nxt <= last), nxt - idx, big)
    found = np.minimum(dp, dn) <= W
    return np.where(found, np.where(dp <= dn, prv, nxt), 0), found


@dataclass
class _Windows:
    a: np.ndarray            # (N, 2K + 1) scale per k of the window centred at each capture
    best: np.ndarray         # (N,) index of the best k
    decisive: np.ndarray     # (N,)
    sigma: np.ndarray        # (N,) noise of decisive windows, client px (NaN elsewhere)
    distinct: np.ndarray     # (N,) enough increments, and oracle motion that alone tells k = 0 from every other k


def _windows(inc: np.ndarray, O: np.ndarray, iv: np.ndarray, lo: np.ndarray, hi: np.ndarray, scale: np.ndarray,
             p: Params) -> _Windows:
    """Least squares of the video increments on the oracle increments per k, over the increments iv of each window
    [lo, hi] (valid for every k: a common support keeps the SSEs comparable)."""
    N, K = len(iv), p.max_offset
    idx = np.arange(N)
    min_sep = p.min_sep * scale
    O0 = np.where(iv[:, None, None], O, 0.0)
    U0 = np.where(iv[:, None], inc, 0.0)

    def win(x: np.ndarray) -> np.ndarray:
        c = _prefix(x)
        return c[hi + 1] - c[lo]

    n = win(iv.astype(np.float64))
    soo = win((O0 ** 2).sum(-1))
    suo = win((U0[:, None, :] * O0).sum(-1))
    suu = win((U0 ** 2).sum(-1))[:, None]
    # How far the oracle increments shifted by k lie from those at k = 0: what a wrong k costs a noise-free fit.
    dk = win(((O0 - O0[:, K:K + 1]) ** 2).sum(-1))
    dk[:, K] = np.inf
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.where(soo > 0, np.clip(suo / soo, *p.a_range), 1.0)  # no oracle motion at this k: SSE = suu anyway
    sse = np.maximum(suu - 2 * a * suo + a * a * soo, 0.0)
    # Every k or none: a k whose shifted oracle motion happened to fall out of the window must still lose on its SSE,
    # not drop out and leave the choice to the others.
    fit = (n >= p.min_increments) & (soo.max(axis=1) >= n * (0.5 * min_sep) ** 2)
    sse = np.where(fit[:, None], sse, np.inf)
    order = np.argsort(sse, axis=1, kind="stable")
    best, second = order[:, 0], order[:, 1]
    sse1, sse2 = sse[idx, best], sse[idx, second]
    var = np.maximum(sse1 / np.maximum(2 * n - 1, 1), (p.noise_floor * scale) ** 2)
    with np.errstate(invalid="ignore"):  # inf - inf where no k fits
        decisive = np.isfinite(sse2) & (sse2 - sse1 >= p.decisive * var)
    sigma = np.where(decisive, np.sqrt(sse1 / np.maximum(2 * n - 1, 1)), np.nan)
    distinct = fit & (a[:, K] ** 2 * dk.min(axis=1) >= min_sep ** 2)
    return _Windows(a, best, decisive, sigma, distinct)


def offsets(mot: VideoMotion, trk: OracleTrack, t_cap: np.ndarray, D: int, p: Params = Params()) -> Offsets:
    N, K, W, h = len(t_cap), p.max_offset, p.window, p.neighbours
    ks = np.arange(-K, K + 1)
    R = len(trk.f)
    idx = np.arange(N)
    if R == 0 or N == 0:
        nothing, nan = np.zeros(N, bool), np.full(N, np.nan)
        return Offsets(int(D), np.full(N, -1), np.full(N, NO_LABEL), np.zeros(N, np.int64), nothing,
                       np.zeros(N, np.int64), nothing, nan, nan, np.zeros(N), nan, np.zeros(N, np.int8))
    L = match(t_cap, trk.t_eof, D)
    Lc = np.clip(L, 0, R - 1)
    seg0 = np.where(L >= 0, trk.seg[Lc], -1)
    labeled = seg0 >= 0

    # Candidate positions: STATE row of frame f[L] + k, if it exists in the label's track segment.
    row_of = trk.row_of()
    gk = np.where(labeled, trk.f[Lc] - trk.f[0], 0)[:, None] + ks[None, :]
    rows = np.where(labeled[:, None] & (gk >= 0) & (gk < len(row_of)), row_of[np.clip(gk, 0, len(row_of) - 1)], -1)
    rc = np.clip(rows, 0, R - 1)
    cand = (rows >= 0) & labeled[:, None] & (trk.seg[rc] == seg0[:, None])
    Pk = np.where(cand[..., None], trk.pos[rc], np.nan)
    # A capture may show the frame after its label; if that frame has no STATE it cannot be judged.
    gap = labeled & ~cand[:, K + 1]
    usable = labeled & ~gap

    # Track segments on the capture side: consecutive captures joined by a trusted increment, labels in one segment.
    link = mot.ok & labeled & np.r_[False, labeled[:-1]] & (seg0 == np.r_[-2, seg0[:-1]])
    scale = mot.scale
    min_sep = p.min_sep * scale
    O = Pk - np.roll(Pk, 1, axis=0)
    iv = link & usable & np.r_[False, usable[:-1]] & np.isfinite(O[..., 0]).all(axis=1)

    # Pass 1, on the segments as registered. Evidence does not depend on whether video and oracle agree: a capture
    # has it when a window within reach holds enough trusted increments and oracle motion that tells k = 0 from every
    # other k. The decisive windows of this pass only give the scale and noise for the anomaly test.
    s1, e1 = _segments(link)
    w1 = _windows(mot.inc, O, iv, np.maximum(idx - W, s1), np.minimum(idx + W, e1), scale, p)
    _, evidence = _nearest(w1.distinct, s1, e1, W)
    ref1, has1 = _nearest(w1.decisive, s1, e1, W)
    a1 = w1.a[idx, w1.best]
    a_loc = np.where(has1, a1[ref1], float(np.median(a1[w1.decisive])) if w1.decisive.any() else 1.0)
    noise = float(np.median(w1.sigma[w1.decisive])) if w1.decisive.any() else 0.0

    # Anomalies: trusted increments that a * the oracle increment explains at no k. Two in a row whose sum is explained
    # mean that one capture is off (stale or glitched): both leave the window fits, and the capture is judged like any
    # other. Any other anomaly (a latency step, i.e. a repeated or skipped frame after which the offset stays changed;
    # a registration jump) breaks the segment, so that no window or neighbour set mixes the two sides.
    thr = np.maximum(0.5 * min_sep, p.outlier * noise)
    anom = np.zeros(N, bool)
    j = np.flatnonzero(iv)
    anom[j] = np.linalg.norm(mot.inc[j, None, :] - a_loc[j, None, None] * O[j], axis=2).min(axis=1) > thr[j]
    j = np.flatnonzero(anom[:-1] & anom[1:])
    single = np.zeros(N, bool)
    if len(j):
        two = np.linalg.norm((mot.inc[j] + mot.inc[j + 1])[:, None, :] - a_loc[j, None, None] * (O[j] + O[j + 1]),
                             axis=2).min(axis=1)
        single[j[two <= thr[j]]] = True
    covered = single | np.r_[False, single[:-1]]
    brk = anom & ~covered

    # Pass 2: windows without the anomalies, on segments broken at them.
    link = link & ~brk
    seg_start, seg_end = _segments(link)
    lo, hi = np.maximum(idx - W, seg_start), np.minimum(idx + W, seg_end)
    w2 = _windows(mot.inc, O, iv & ~anom, lo, hi, scale, p)
    best, decisive = w2.best, w2.decisive

    # Each capture's reference: the nearest decisive window centre in its segment, at most W captures away, if every
    # decisive window within W agrees on k (a window takes its k from wherever the camera changed speed inside it,
    # which may lie across a change of the offset).
    ref, has_ref = _nearest(decisive, seg_start, seg_end, W)
    votes = _prefix((decisive[:, None] & (best[:, None] == np.arange(len(ks))[None, :])).astype(np.float64))
    has_ref &= ((votes[hi + 1] - votes[lo]) > 0).sum(axis=1) <= 1
    ref = np.where(has_ref, ref, 0)
    kref = best[ref]
    a_ref = np.where(has_ref, w2.a[ref, kref], np.nan)

    # Video positions inside each segment; the neighbour constant c = median(video - a * oracle at kref).
    csum = np.cumsum(np.where(link[:, None], mot.inc, 0.0), axis=0)
    Cv = csum - csum[seg_start]

    def side(ds: range) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        res = np.full((N, len(ds), 2), np.nan)
        for m, d in enumerate(ds):
            j = np.clip(idx + d, 0, N - 1)
            pj = Pk[j, kref]
            okj = has_ref & (idx + d >= seg_start) & (idx + d <= seg_end) & usable[j] & np.isfinite(pj[:, 0])
            res[okj, m] = Cv[j][okj] - a_ref[okj, None] * pj[okj]
        cnt = np.isfinite(res[..., 0]).sum(axis=1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN rows: no neighbours on this side
            c = np.nanmedian(res, axis=1)
        e = np.linalg.norm(Cv[:, None, :] - a_ref[:, None, None] * Pk - c[:, None, :], axis=2)
        e = np.where(np.isfinite(e), e, np.inf)
        o = np.argsort(e + 1e-9 * np.abs(ks[None, :] - ks[kref][:, None]), axis=1, kind="stable")  # ties: near kref
        return cnt >= 2, o[:, 0], e[idx, o[:, 0]], e[idx, o[:, 1]]

    okL, kL, eL1, eL2 = side(range(-h, 0))
    okR, kR, eR1, eR2 = side(range(1, h + 1))
    k_idx = np.where(okL, kL, kR)
    split = okL & okR & (kL != kR)
    resid = np.where(okL & okR, (eL1 + eR1) / 2, np.where(okL, eL1, eR1))
    clear = ~split & (okL | okR) & (~okL | (eL1 <= 0.5 * eL2)) & (~okR | (eR1 <= 0.5 * eR2))
    # Low motion is judged at the label (k = 0), so that it does not depend on the offset found either.
    others = np.linalg.norm(Pk - Pk[:, K:K + 1], axis=2)
    others[:, K] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        sep = np.where(has_ref, a_ref, a_loc) * np.nanmin(others, axis=1)
    sep = np.where(np.isfinite(sep), sep, 0.0)

    status = np.full(N, OK)
    status[split] = SPLIT
    status[~(okL | okR)] = NO_WINDOW
    status[(status != OK) & ~evidence] = NO_EVIDENCE
    status[sep < min_sep] = LOW_MOTION
    status[gap] = STATE_GAP
    status[~labeled] = NO_LABEL
    return Offsets(D=int(D), label=L, status=status, k=ks[k_idx], clear=clear & (status == OK),
                   k_window=np.where(decisive, ks[best], 0), decisive=decisive & usable, a=a_ref,
                   resid=np.where(status == OK, resid, np.nan), sep=sep, sigma=w2.sigma,
                   anomaly=np.where(covered, 1, np.where(brk, 2, 0)).astype(np.int8))


# ---- calibration of D ----------------------------------------------------------------------------------

def scan(mot: VideoMotion, trk: OracleTrack, t_cap: np.ndarray, p: Params = Params()
         ) -> tuple[int | None, np.ndarray, np.ndarray]:
    """Coarse D: the correlation of the video increments with the oracle increments between the two captures' matched
    frames, over a grid of D. Returns (best D or None, grid ns, correlation)."""
    grid = np.round(np.arange(p.scan_ms[0], p.scan_ms[1] + p.scan_step_ms / 2, p.scan_step_ms) * 1e6).astype(np.int64)
    rho = np.full(len(grid), np.nan)
    R = len(trk.f)
    if R < 2 or len(t_cap) < 2:
        return None, grid, rho
    period = int(np.median(np.diff(trk.t_eof)))
    u = mot.inc
    for m, D in enumerate(grid):
        L = match(t_cap, trk.t_eof, D)
        Lp = np.r_[-1, L[:-1]]
        Lc, Lpc = np.clip(L, 0, R - 1), np.clip(Lp, 0, R - 1)
        v = mot.ok & (L >= 0) & (Lp >= 0) & (t_cap <= trk.t_eof[-1] + D + period)
        v &= (trk.seg[Lc] == trk.seg[Lpc]) & (trk.seg[Lc] >= 0)
        if v.sum() < 10:
            continue
        o = trk.pos[Lc[v]] - trk.pos[Lpc[v]]
        uu = u[v]
        den = np.sqrt((uu ** 2).sum() * (o ** 2).sum())
        if den > 0:
            rho[m] = (uu * o).sum() / den
    if not np.isfinite(rho).any():
        return None, grid, rho
    top = np.nanmax(rho)
    near = np.isfinite(rho) & (rho >= top - 1e-9)
    m = int(np.nanargmax(rho))
    a_, b_ = m, m
    while a_ > 0 and near[a_ - 1]:
        a_ -= 1
    while b_ < len(grid) - 1 and near[b_ + 1]:
        b_ += 1
    return int((grid[a_] + grid[b_]) // 2), grid, rho


@dataclass
class Sweep:
    D: int | None            # middle of the widest interval with the most agreeing captures, ns
    lo: int | None           # that interval (lo, hi], ns
    hi: int | None
    agree: int = 0           # captures matched correctly by any D in it
    used: int = 0            # clearly judged captures that voted


def sweep(off: Offsets, trk: OracleTrack, t_cap: np.ndarray) -> Sweep:
    """Capture i with true STATE row r is matched correctly iff t - t_eof[r + 1] < D <= t - t_eof[r]."""
    sel = np.flatnonzero((off.status == OK) & off.clear)
    if len(sel) == 0:
        return Sweep(None, None, None)
    R = len(trk.f)
    rows = trk.row_of()[trk.f[off.label[sel]] + off.k[sel] - trk.f[0]]
    t = t_cap[sel]
    hi = t - trk.t_eof[rows]
    lo = np.where(rows + 1 < R, t - trk.t_eof[np.minimum(rows + 1, R - 1)], np.iinfo(np.int64).min)
    B = np.unique(np.r_[lo[lo > np.iinfo(np.int64).min], hi])
    if len(B) < 2:
        return Sweep(int(B[0]), None, None, len(sel), len(sel))
    los, his = np.sort(lo), np.sort(hi)
    # Constant on each elementary interval (B[m], B[m + 1]].
    cnt = np.searchsorted(los, B[:-1], side="right") - np.searchsorted(his, B[1:], side="left")
    top = int(cnt.max())
    at = cnt == top
    best, run = None, None
    m = 0
    while m < len(at):
        if at[m]:
            e = m
            while e + 1 < len(at) and at[e + 1]:
                e += 1
            width = B[e + 1] - B[m]
            if run is None or width > run:
                best, run = (m, e), width
            m = e + 1
        else:
            m += 1
    a_, b_ = int(B[best[0]]), int(B[best[1] + 1])
    return Sweep((a_ + b_) // 2, a_, b_, top, len(sel))


# ---- report --------------------------------------------------------------------------------------------

def _p(x: np.ndarray, q: float) -> float | None:
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else None


@dataclass
class ClockResult:
    clock: str
    D_ms: float | None = None
    D_coarse_ms: float | None = None
    D_interval_ms: list | None = None        # [lo, hi]: every D in it matches the agreeing captures
    D_agree: list | None = None              # [agreeing, voting] clearly judged captures
    informative: int = 0                     # judged captures
    zero: int = 0                            # judged at offset 0
    unjudged: int = 0                        # could have been judged but were not (unjudged_by): count against
    share: float | None = None               # zero / (informative + unjudged): the metric
    share_judged: float | None = None        # zero / informative
    hist: dict = field(default_factory=dict)          # per-capture offset -> count
    window_hist: dict = field(default_factory=dict)   # decisive window offset -> count
    unjudged_by: dict = field(default_factory=dict)   # no_window / split -> count
    excluded: dict = field(default_factory=dict)      # statuses left out -> count
    anomalies: dict = field(default_factory=dict)     # increments left out of the fits (one capture off) / breaks
    lag_ms: dict | None = None               # capture time - end of the true frame
    first_nonzero: list = field(default_factory=list)
    ok: bool = False
    verdict: str = "FAIL"
    reason: str = ""


@dataclass
class AlignReport:
    path: str = ""
    captures: int = 0
    seq_gaps: int = 0                         # frames the video recorder dropped (gaps in seq)
    states: int = 0
    frames: list | None = None                # [first, last] STATE frame
    period_ms: float | None = None
    trusted: int = 0                          # trusted increments
    response: dict | None = None
    track_breaks: dict | None = None
    screen: list | None = None
    src: list | None = None
    scale_a: dict | None = None
    noise_px: dict | None = None
    resid_px: dict | None = None
    threshold: float = THRESHOLD
    min_informative: int = 0
    min_coverage: float = 0.0
    primary: ClockResult | None = None
    alt: ClockResult | None = None
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.primary is not None and self.primary.ok

    def as_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        d["verdicts"] = {c.clock: c.verdict for c in (self.primary, self.alt) if c is not None}
        return d

    def format(self) -> str:
        pr = self.primary
        pct = (lambda x: f"{x * 100:.2f} %" if x is not None else "n/a")
        lines = [
            f"captures {self.captures} ({self.seq_gaps} dropped by the video recorder), STATE {self.states} frames "
            f"{self.frames}, period {self.period_ms and round(self.period_ms, 3)} ms; client {self.src}, "
            f"cam.screen {self.screen}",
            f"registration: {self.trusted} trusted increments, response {self.response}; parallax scale a {self.scale_a};"
            f" track breaks {self.track_breaks}",
        ]
        for c in (pr, self.alt):
            if c is None:
                continue
            tag = "primary" if c is pr else "alternative"
            lines.append(f"[{c.clock} clock, {tag}] D {c.D_ms and round(c.D_ms, 3)} ms (coarse {c.D_coarse_ms}); "
                         f"interval {c.D_interval_ms} ms agreed by {c.D_agree}; lag {c.lag_ms}")
            lines.append(f"  judged {c.informative} + unjudged {c.unjudged} {c.unjudged_by}: offset 0 {c.zero} = "
                         f"{pct(c.share)} (of the judged {pct(c.share_judged)}) -> {c.verdict}"
                         f"{' (' + c.reason + ')' if c.reason else ''}")
            lines.append(f"  offsets {c.hist}; decisive windows {c.window_hist}; excluded {c.excluded}; "
                         f"anomalies {c.anomalies}")
            if c.first_nonzero:
                lines.append(f"  first non-zero (capture, seq, frame, k): {c.first_nonzero}")
        lines.append(f"noise: window sigma {self.noise_px}; per-capture residual {self.resid_px} (client px)")
        lines.extend(f"note: {n}" for n in self.notes)
        lines.append(f"{'PASS' if self.ok else 'FAIL'}: {pct(pr.share if pr else None)} of the judgeable captures at "
                     f"offset 0 on the {pr.clock if pr else '?'} clock (threshold {self.threshold * 100:.1f} %; judged "
                     f">= {self.min_informative} and >= {self.min_coverage * 100:.0f} % of the captures)")
        return "\n".join(lines)


def _hist(x: np.ndarray) -> dict:
    v, c = np.unique(x, return_counts=True)
    return {int(a): int(b) for a, b in zip(v, c)}


def calibrate(mot: VideoMotion, trk: OracleTrack, t_cap: np.ndarray, p: Params = Params(), clock: str = GATE_CLOCK,
              D: int | None = None) -> tuple[ClockResult, Offsets | None]:
    """Steps 3-5 for one capture clock: coarse scan, two sweep refinements, final offsets. With D given, no
    calibration: the offsets of that D (to test a fixed, e.g. previously calibrated, offset)."""
    res = ClockResult(clock)
    if len(t_cap) == 0 or len(trk.f) == 0:
        res.reason = "no video captures" if len(t_cap) == 0 else "no STATE frames"
        return res, None
    if D is None:
        D0, _, _ = scan(mot, trk, t_cap, p)
        if D0 is None:
            res.reason = "no camera motion to calibrate on"
            return res, None
        res.D_coarse_ms = D0 / 1e6
        D = D0
        off = offsets(mot, trk, t_cap, D, p)
        for _ in range(2):
            sw = sweep(off, trk, t_cap)
            if sw.D is None or sw.agree < 20 or sw.D == D:
                break
            D = sw.D
            off = offsets(mot, trk, t_cap, D, p)
        sw = sweep(off, trk, t_cap)
        if sw.lo is not None:
            res.D_interval_ms = [sw.lo / 1e6, sw.hi / 1e6]
            res.D_agree = [sw.agree, sw.used]
    else:
        off = offsets(mot, trk, t_cap, D, p)
    res.D_ms = D / 1e6
    ok = off.status == OK
    res.informative = int(ok.sum())
    res.zero = int((ok & (off.k == 0)).sum())
    res.unjudged_by = {STATUS[s]: int((off.status == s).sum()) for s in UNJUDGED}
    res.unjudged = sum(res.unjudged_by.values())
    judgeable = res.informative + res.unjudged
    res.share = res.zero / judgeable if judgeable else None
    res.share_judged = res.zero / res.informative if res.informative else None
    res.hist = _hist(off.k[ok])
    res.window_hist = _hist(off.k_window[off.decisive])
    res.excluded = {STATUS[s]: int((off.status == s).sum()) for s in range(1, len(STATUS)) if s not in UNJUDGED}
    res.anomalies = {"left_out": int((off.anomaly == 1).sum()), "breaks": int((off.anomaly == 2).sum())}
    sel = ok & off.clear
    if sel.any():
        rows = trk.row_of()[trk.f[off.label[sel]] + off.k[sel] - trk.f[0]]
        lag = (t_cap[sel] - trk.t_eof[rows]) / 1e6
        res.lag_ms = {"p1": round(_p(lag, 1), 3), "p50": round(_p(lag, 50), 3), "p99": round(_p(lag, 99), 3),
                      "min": round(float(lag.min()), 3), "max": round(float(lag.max()), 3)}
    bad = np.flatnonzero(ok & (off.k != 0))
    res.first_nonzero = [[int(i), int(mot.seq[i]), int(trk.f[off.label[i]]), int(off.k[i])] for i in bad[:10]]
    need = max(1, p.min_informative, math.ceil(p.min_coverage * len(t_cap)))
    if judgeable and judgeable >= p.min_informative and res.share < p.threshold:
        res.reason = f"{res.informative - res.zero} judged captures off offset 0, {res.unjudged} unjudged"
        if res.unjudged > res.informative - res.zero:
            res.reason += " (repeated or skipped frames leave captures unjudged)"
    elif res.informative < need:
        res.verdict, res.reason = "INCONCLUSIVE", (f"only {res.informative} judged captures (< {need}: at least "
                                                   f"{p.min_informative} and {p.min_coverage * 100:.0f} % of "
                                                   f"{len(t_cap)} captures)")
    else:
        res.verdict, res.ok = "PASS", True
    return res, off


def align(mot: VideoMotion, trk: OracleTrack, p: Params = Params(), clock: str = GATE_CLOCK,
          D_ms: float | None = None) -> tuple[AlignReport, Offsets | None]:
    """The report of the gate clock `clock` and, when D is calibrated, of the other clock as a cross-check."""
    rep = AlignReport(captures=len(mot.seq), states=len(trk.f), threshold=p.threshold, min_informative=p.min_informative,
                      min_coverage=p.min_coverage)
    rep.seq_gaps = int(np.clip(np.diff(mot.seq) - 1, 0, None).sum()) if len(mot.seq) > 1 else 0
    if len(trk.f):
        rep.frames = [int(trk.f[0]), int(trk.f[-1])]
    if len(trk.f) > 1:
        rep.period_ms = float(np.median(np.diff(trk.t_eof))) / 1e6
    rep.trusted = int(mot.ok.sum())
    r = mot.response[1:]
    if len(r):
        rep.response = {"p1": round(_p(r, 1), 3), "p50": round(_p(r, 50), 3)}
    rep.track_breaks = trk.breaks
    scr = trk.screen[trk.seg >= 0]
    rep.screen = [list(map(int, s)) for s in np.unique(scr, axis=0)] if len(scr) else []
    rep.src = [list(map(int, s)) for s in np.unique(mot.src, axis=0)] if len(mot.src) else []
    if rep.screen and rep.src and any(s not in rep.screen for s in rep.src):
        rep.notes.append("capture client size differs from cam.screen: is the crop right (DPI scaling)?")
    t_main = mot.t_arrival if clock == "arrival" else mot.t_frame
    t_alt = mot.t_frame if clock == "arrival" else mot.t_arrival
    if len(trk.f) and len(t_main) and abs(int(np.median(t_main)) - int(np.median(trk.t_eof))) > 10_000_000_000:
        rep.notes.append("capture and STATE clocks are more than 10 s apart: was q recorded as raw QPC (Core.Qpc)?")
    if (mot.t_frame == 0).any():
        rep.notes.append(f"{int((mot.t_frame == 0).sum())} captures without SystemRelativeTime (no frame-clock label)")
    D = None if D_ms is None else int(round(D_ms * 1e6))
    rep.primary, off = calibrate(mot, trk, t_main, p, clock, D)
    if len(t_alt) and (t_alt != 0).all() and D is None:
        rep.alt, _ = calibrate(mot, trk, t_alt, p, "frame" if clock == "arrival" else "arrival")
    if off is not None:
        ok = off.status == OK
        a = off.a[ok]
        rep.scale_a = {"p1": _r(_p(a, 1)), "p50": _r(_p(a, 50)), "p99": _r(_p(a, 99))}
        rep.noise_px = {"p50": _r(_p(off.sigma, 50)), "p99": _r(_p(off.sigma, 99))}
        rep.resid_px = {"p50": _r(_p(off.resid, 50)), "p99": _r(_p(off.resid, 99)), "max": _r(_p(off.resid, 100))}
    return rep, off


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(x, nd)


# ---- episode -------------------------------------------------------------------------------------------

def load(path: str | Path, p: Params = Params(), progress: Callable[[int], None] | None = None
         ) -> tuple[VideoMotion, OracleTrack]:
    path = Path(path)
    vr = VideoReader(path)
    if not vr.exists():
        raise FileNotFoundError(f"no video in {path} (record with ssbot.record.video / recorder record --video)")
    rr = RecordingReader(path)
    freq = rr.hello.get("qpc_freq") or (rr.meta.get("qpc") or {}).get("freq")
    if not freq:
        raise ValueError(f"no qpc_freq in {path / 'meta.json'}")
    trk = oracle_track(rr.states(keys=("q", "cam", "game")), freq, p.jump_frac)
    mot = register(vr.frames(), p, progress)
    return mot, trk


def align_episode(path: str | Path, p: Params = Params(), clock: str = GATE_CLOCK, D_ms: float | None = None,
                  progress: Callable[[int], None] | None = None) -> tuple[AlignReport, Offsets | None, VideoMotion,
                                                                         OracleTrack]:
    mot, trk = load(path, p, progress)
    rep, off = align(mot, trk, p, clock, D_ms)
    rep.path = str(path)
    return rep, off, mot, trk


def dump(path: Path, off: Offsets, mot: VideoMotion, trk: OracleTrack) -> None:
    """Per-capture arrays for a closer look (numpy .npz)."""
    L = off.label
    np.savez_compressed(path, seq=mot.seq, t_arrival=mot.t_arrival, t_frame=mot.t_frame, inc=mot.inc, ok=mot.ok,
                        response=mot.response, label_row=L, label_f=np.where(L >= 0, trk.f[np.clip(L, 0, None)], -1),
                        status=off.status, k=off.k, clear=off.clear, k_window=off.k_window, decisive=off.decisive,
                        a=off.a, resid=off.resid, sep=off.sep, anomaly=off.anomaly, D=off.D, state_f=trk.f,
                        state_t_eof=trk.t_eof, state_pos=trk.pos, state_seg=trk.seg)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.record.align", description=__doc__.split("\n")[0])
    ap.add_argument("path", help="episode folder with state.* and video.*")
    ap.add_argument("--clock", choices=("frame", "arrival"), default=GATE_CLOCK,
                    help="gate clock: WGC SystemRelativeTime (frame, default, DESIGN 3.1.4) or callback arrival; the "
                         "other one is reported as a cross-check")
    ap.add_argument("--D-ms", type=float, help="use this capture offset instead of calibrating it")
    ap.add_argument("--max-offset", type=int, default=Params.max_offset)
    ap.add_argument("--window", type=int, default=Params.window)
    ap.add_argument("--min-sep", type=float, default=Params.min_sep, help="thumbnail px (low-motion exclusion)")
    ap.add_argument("--min-informative", type=int, default=Params.min_informative)
    ap.add_argument("--min-coverage", type=float, default=Params.min_coverage,
                    help="judged captures needed, as a share of all captures")
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--json", action="store_true", help="also write align.json into the episode folder")
    ap.add_argument("--dump", action="store_true", help="also write per-capture arrays to align_frames.npz")
    a = ap.parse_args(argv)
    p = Params(max_offset=a.max_offset, window=a.window, min_sep=a.min_sep, min_informative=a.min_informative,
               min_coverage=a.min_coverage, threshold=a.threshold)
    rep, off, mot, trk = align_episode(a.path, p, a.clock, a.D_ms,
                                       progress=lambda n: print(f"  registered {n} captures", file=sys.stderr))
    print(rep.format())
    if a.json:
        (Path(a.path) / "align.json").write_text(json.dumps(rep.as_dict(), indent=1), encoding="utf-8")
    if a.dump and off is not None:
        dump(Path(a.path) / "align_frames.npz", off, mot, trk)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
