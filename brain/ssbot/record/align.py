"""Camera-trajectory alignment MONITOR of a recorded episode (DESIGN §3.1.4 C4).

The monitor is not the M1 alignment gate. Training sessions carry the oracle's frame marker (RPC "frame.marker", STATE
"mk"), which the capture path reads and masks (ssbot.record.video, ssbot.vision.mask): a capture whose marker decoded is
labelled exactly, and the gate is the share of such captures (ssbot.record.marker). The monitor checks timestamp labels
against the camera motion wherever the camera motion can tell: those of sessions without the marker (--no-marker, a
refusal, human sessions before 2026-09-30) and of the captures whose marker did not decode; it flags a session, never
discards it. AlignReport.labels says how many captures carry which label. What it can and cannot see:

- A constant offset is invisible while the camera stands still or moves at constant speed. A capture is judged only by
  its own window (the +-W captures around it, in its own track segment), and only when the camera changes speed in
  there. Otherwise it is "uninformative", or "low_motion" when the camera barely moves at the capture itself; both
  are reported and left out, never counted as aligned.
- A judged capture ("ok") lies in an own window that is decisive at some k, that agrees with every decisive window it
  lies inside, and that is consistent at that k (_consistent): every increment of the fit is explained at k, not
  merely at some k, and the video's path between any two of its captures matches the oracle's at k within the noise
  and scale_tol. No neighbour constant or k comes from outside that window. So between a capture judged at 0 and the
  speed changes that decided its window, no increment and no stretch is better explained by another offset.
- Detected: isolated stale or glitched captures and short runs out of step and back (excursions, judged one by one);
  periodic judder; latency steps (track breaks); runs out of step between two breaks (cut); runs that begin or end
  while the camera stands still and contain a speed change (mixed: the stand -> walk repro of verify3).
- Not detected: offsets of captures more than W captures inside a stretch of constant speed (uninformative); offsets
  smaller than the registration noise (a one-frame offset while the camera moves less than ~min_sep / 2 per frame);
  a window whose only speed change sits next to a stale capture takes the wrong k (the stale capture explains the
  change one frame early), so its aligned captures are judged off and the stale one may be judged at 0.
- It fails aligned captures next to misaligned or badly registered ones (mixed, cut, split), and in rooms where two
  parallax layers make the registered scale depend on the camera speed (below). 1 - share is therefore not an
  estimate of the misaligned share: it overstates it next to faults and leaves the uninformative captures out. Only
  for isolated stale captures and periodic judder in a moving camera does it come close.

Input: an episode folder with the oracle STATE stream (ssbot.record.recorder) and the gray thumbnail video
(ssbot.record.video). STATE "q" is the raw QPC at end of frame (ticks of HELLO qpc_freq); every captured frame has its
arrival time and WGC's SystemRelativeTime (the "frame" clock), both QPC in ns. The frame clock is the primary clock,
as DESIGN §3.1.4 has it: WGC stamps it on the composed frame (P8: 7-10 ms after the arrival, apparently the target
present time), while the arrival also carries the jitter of the callback itself (staging copy, GIL). D is calibrated
for each clock, and the arrival clock's result is reported as a cross-check.

1. Registration: the camera motion between consecutive captures, phase correlation of the thumbnails (Hann window;
   the peak refined by an upsampled DFT, see PhaseCorrelator), scaled to client pixels. An increment with a weak peak
   or from a flat image (fades, black screens) is not trusted. Content that does not move with the world is masked
   out (ScreenFixed): Hornet, whom the camera keeps near the image centre (hero box widened by hero_margin and
   projected with the frame's V/P), the HUD (STATE hud rects), the frame marker (STATE mk rect), the vision mask's
   corner where the capture path filled it (video.json "mask"), letterbox bars, and textured pixels that keep their
   value while the image moves (static_pixels). Unmasked, a figure at the centre
   pulls every step towards 0 by a share that falls with the speed (0.76 of the step at ~1 thumbnail px per frame,
   0.97 at ~3.5), which no single parallax scale absorbs. A masked step is registered twice: the mask's own edges
   still pull by ~1 %, so the later image is moved back by the first estimate and registered again, with both places
   of the masked content masked; at a residual of ~0 that pull vanishes.
2. Oracle camera track: per STATE frame, the image motion of the gameplay plane (z = 0) at the image centre from that
   frame's render-time V/P (the projection of tools/projector), summed into a track in client pixels. It breaks at
   scene changes, frames without a camera and camera jumps (respawns).
3. Matching (C4): capture i gets the newest STATE frame whose predicted present time t_eof + D is <= its capture time.
4. Offsets. Windows: over +-W captures, fit the video increments = a * the oracle increments shifted by k frames, for
   every integer k in [-K, K] (a absorbs parallax: the registration locks onto whichever layer dominates the image). A
   window is decisive when one k fits clearly better; that needs the camera to change speed inside it. Anomalies: an
   increment that a * the oracle increment explains at no k (6 sigma of the increments' own robust noise, _noise).
   Excursions (_excursions): two anomalies at most max_excursion captures apart, or one next to an increment that only
   an odd k explains, whose increments sum to what the oracle says: the captures between were out of step and came
   back (stale or glitched captures, a stale pair, periodic judder). Their increments leave the fits, their sum enters
   them as one increment, they are nobody's neighbours, and the track goes on through them. Any other anomaly (a
   latency step, i.e. a repeated or skipped frame after which the offset stays changed; a registration glitch) breaks
   the track, so no window straddles it. A repeated frame while the camera stands still is no anomaly at all: that is
   what the consistency test of the own window is for.
   Captures: each capture judged by its own window (above) has its video position compared with the oracle positions
   at every k, with the track constant taken from its h nearest neighbours outside excursions (inside the own window)
   at the window's k, separately from the left and from the right neighbours (a registration glitch next to a capture
   makes the two disagree: "split"). The captures between two breaks may be a run out of step that is too long to
   pair, whose neighbours are all equally off, so a segment too short for a decisive window of its own stays
   unjudged ("cut"), even when the breaks were registration glitches.
5. Calibrating D: a coarse scan picks the D whose matching best correlates the video and oracle increments. Then every
   clearly judged capture, with true frame g in STATE row r, needs t - t_eof[r + 1] < D <= t - t_eof[r]; D becomes the
   middle of the interval most captures agree on, and step 4 runs again.
6. The verdict: captures judged at offset 0 / (judged + unjudged) >= threshold, with at least min_informative judged
   captures and min_coverage of all captures (else INCONCLUSIVE). Left out, for reasons that do not depend on whether
   video and oracle agree: captures without a label, whose next STATE frame is missing (they may show a frame without
   a label), low_motion (candidate positions around the label closer together than min_sep thumbnail px) and
   uninformative (the own window, as registered, has too few trusted increments or camera motion that tells no k
   apart). Unjudged, counting against the share: no_window (nothing within W fits, even across breaks: judder),
   split, cut (a window was within reach, but only across anomalies: between two breaks, inside a long excursion),
   mixed (the own window is decisive but not consistent, or disagrees with another decisive window: a change of the
   offset inside it that no anomaly showed). A PASS says that nothing the monitor can see disagrees; the share of
   aligned captures is what the marker measures. Anomalies are reported apart (excursions, breaks), and so are where
   the splits fall and the registration scale per camera speed (scale_by_speed).

Parallax, a known limit: a window fits one scale a, but two parallax layers of comparable weight (a near ground layer
under a far background, common in Silksong rooms) make the registered scale depend on the camera speed: their
correlation peaks merge at some speeds and part at others. Synthetic, the bottom half at parallax 1 and the top half
at 0.5, no figure (seed 1): median 0.56 / 0.74 / 0.68 of the near layer's motion at 0.5-1 / 1-2 / 2-4 thumbnail px
per capture; the near layer on the bottom 35 %, with the figure: 0.63 / 0.54 at 1-2 / 2-4. Such windows are not
consistent (mixed) and the neighbours on the two sides of a speed change disagree (split), so aligned recordings of
such rooms FAIL (tests/test_align.py::test_two_layer_parallax_aligned_recording_passes, xfail). The reach is wider than
"comparable weight": a far layer at parallax 0.9 on the top half, or at 0.5 on only the top 30 %, leaves aligned
recordings at 0.09-0.14 with 85-92 % of the judgeable captures mixed. Until the monitor is tuned, its FAIL therefore
flags a session (DESIGN §3.1.4) instead of discarding it; the gate is the frame marker (ssbot.record.marker). It is not
tuned on synthetic data: the first in-game run with the marker scores the monitor's verdicts
against the truth (ssbot.record.marker.score_monitor) and records the registration scale against the camera speed
(AlignReport.scale_by_speed) and where the splits fall (ClockResult.split_at; the probe also keeps the per-capture
arrays), and the next step is to tune on those recordings.

    python -m ssbot.record.align <episode> [--clock frame|arrival] [--json] [--dump] [--no-mask]  (exit 1 unless PASS)
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
from ssbot.vision import mask as vmask

THRESHOLD = 0.995

# Per-capture status of an offsets() run. OK captures are judged; NO_WINDOW, SPLIT, CUT and MIXED ones could have
# been judged (they are labelled, moving and their own window has evidence) but were not, which misalignment itself
# causes (periodic repeated or skipped frames spoil every fit; anomalies cut the track; a change of the offset that no
# anomaly showed makes the own window inconsistent), so they count against the share. They are reported apart:
# NO_WINDOW (nothing within reach fits: judder), SPLIT (the neighbours on the two sides disagree), CUT (a window was
# within reach, but only across anomalies), MIXED (the own window is decisive but not consistent at its k, or another
# decisive window around disagrees). The other statuses do not depend on whether video and oracle agree and are left
# out: NO_LABEL, STATE_GAP, LOW_MOTION and UNINFORMATIVE (no speed change in the own window: nothing to see).
OK, NO_LABEL, STATE_GAP, NO_WINDOW, LOW_MOTION, SPLIT, UNINFORMATIVE, CUT, MIXED = range(9)
STATUS = ("ok", "no_label", "state_gap", "no_window", "low_motion", "split", "uninformative", "cut", "mixed")
UNJUDGED = (NO_WINDOW, SPLIT, CUT, MIXED)
GATE_CLOCK = "frame"  # DESIGN §3.1.4: WGC SystemRelativeTime with a calibrated offset, for timestamp labels (the
                      # fallback of ssbot.record.marker) and the monitor alike; "arrival" is the cross-check


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
    outlier: float = 6.0             # anomaly: an increment max(min_sep / 2, outlier * noise) from every k
    noise_bound: float = 3.0         # that noise (median) is at most this times the lower-quartile estimate (_noise)
    noise_floor: float = 0.02        # thumbnail px: lower bound of a window's noise estimate
    min_increments: int = 20         # trusted increments a window fit needs
    a_range: tuple[float, float] = (0.2, 5.0)
    scan_ms: tuple[float, float] = (-50.0, 250.0)   # coarse search range of D
    scan_step_ms: float = 0.5
    threshold: float = THRESHOLD
    min_informative: int = 300
    min_coverage: float = 0.5        # judged captures must also be at least this share of all captures
    mask: bool = True                # leave screen-fixed content out of step 1 (labels: hero, HUD; static pixels)
    hero_margin: tuple[float, float] = (1.0, 0.75)  # world units around the hero collider (sprite, cloak, needle)
    mask_margin: float = 0.02        # share of the image height added around every masked rect, then feathered
    max_excursion: int = 8           # longest run of captures off and back whose anomalies pair up (else: breaks)
    drift: float = 5.0               # own window, captures j - i apart: max(min_sep / 2, drift * noise * sqrt(j - i))
    scale_tol: float = 0.02          # ... plus this share of the camera's displacement (_consistent)


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
    masked: np.ndarray       # (N,) share of the thumbnail left out of the step's registration (screen-fixed content)


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

    def spectrum(self, img: np.ndarray, weight: np.ndarray | None = None) -> np.ndarray:
        """Spectrum of the zero-mean image under the Hann window, times `weight` (ScreenFixed) if given: the mean is
        then taken where the weight is, so that masked content does not leave a static step behind."""
        x = img.astype(np.float64)
        if weight is None:
            return np.fft.rfft2((x - x.mean()) * self.win)
        w = self.win * weight
        return np.fft.rfft2((x - (x * w).sum() / max(w.sum(), 1e-12)) * w)

    def moved_back(self, img: np.ndarray, dx: float, dy: float) -> np.ndarray:
        """The image with its content moved by (-dx, -dy) px (a Fourier shift: exact inside, wrapped at the edges,
        where the Hann window is ~0)."""
        X = np.fft.rfft2(img.astype(np.float64))
        return np.fft.irfft2(X * np.exp(2j * np.pi * (self.ky[:, None] * dy + self.kx[None, :] * dx)),
                             s=(self.h, self.w))

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


def _contrast(img: np.ndarray, weight: np.ndarray | None) -> float:
    """Gray std of the thumbnail, where `weight` is (> 0.5) if given."""
    if weight is None:
        return float(img.std())
    x = img[weight > 0.5]
    return float(x.std()) if x.size else 0.0


def register(frames: Iterable[tuple[FrameInfo, np.ndarray]], params: Params = Params(),
             progress: Callable[[int], None] | None = None, fixed: "ScreenFixed | None" = None) -> VideoMotion:
    """Phase-correlate every capture with the previous one. The correlation gives how far the content moved; the
    camera moved the other way. With `fixed`, both thumbnails of a step are weighted by its mask (the same weight
    for both), so that screen-fixed content does not pull the step towards 0. params.registration "cv2" uses
    cv2.phaseCorrelate instead (for comparison; the mask goes into its window)."""
    t, ts, seq, inc, resp, con, scale, src, ok, masked = [], [], [], [], [], [], [], [], [], []
    prev = prev_t = None
    held: tuple = (None, None, None)       # (mask key, spectrum, contrast) of the previous thumbnail
    tools: dict[tuple[int, int], Any] = {}
    use_cv2 = params.registration == "cv2"
    for i, (info, img) in enumerate(frames):
        t_img = info.frame_ns or info.arrival_ns
        sx, sy = info.src_w / info.w, info.src_h / info.h
        tool = tools.get(img.shape)
        if tool is None:
            tool = tools[img.shape] = (cv2.createHanningWindow((img.shape[1], img.shape[0]), cv2.CV_32F) if use_cv2
                                       else PhaseCorrelator(img.shape))
        step, r, good, share = (0.0, 0.0), 0.0, False, 0.0
        key, weight = fixed.weight(prev_t, t_img, img.shape) if fixed is not None and prev is not None \
            else (None, None)
        if use_cv2:
            cur = img.astype(np.float32)
            c = _contrast(img, weight)
            if prev is not None and prev.shape == img.shape:
                win = tool if weight is None else (tool * weight).astype(np.float32)
                (dx, dy), r = cv2.phaseCorrelate(prev.astype(np.float32), cur, win)
                step = (-dx * sx, -dy * sy)
                good = bool(np.isfinite(r) and r >= params.min_response and c >= params.min_contrast
                            and _contrast(prev, weight) >= params.min_contrast)
        else:
            cur, c = tool.spectrum(img, weight), _contrast(img, weight)
            if prev is not None and prev.shape == img.shape:
                A, c0 = held[1:] if held[0] == key and held[1] is not None and held[1].shape == cur.shape \
                    else (tool.spectrum(prev, weight), _contrast(prev, weight))
                dx, dy, r = tool.shift(A, cur)
                if weight is not None:
                    # The mask is screen-fixed while the content moves: its edges still pull the peak towards 0
                    # (~1 % of the step). Again with the later image moved back by the first estimate, the residual
                    # is ~0, where that pull vanishes (the weight's overlap with itself is symmetric about 0).
                    w2 = fixed.moved_weight(prev_t, t_img, img.shape, dx, dy)
                    ex, ey, r = tool.shift(tool.spectrum(prev, w2), tool.spectrum(tool.moved_back(img, dx, dy), w2))
                    dx, dy = dx + ex, dy + ey
                step = (-dx * sx, -dy * sy)
                good = bool(np.isfinite(r) and r >= params.min_response and c >= params.min_contrast
                            and c0 >= params.min_contrast)
            held = (key, cur, c)
        if weight is not None:
            share = float((weight < 0.5).mean())
        prev, prev_t = img, t_img
        t.append(info.arrival_ns)
        ts.append(info.frame_ns)
        seq.append(info.seq)
        inc.append(step)
        resp.append(r)
        con.append(float(img.std()))
        scale.append(sx)
        src.append((info.src_w, info.src_h))
        ok.append(good)
        masked.append(share)
        if progress is not None and i % 5000 == 4999:
            progress(i + 1)
    return VideoMotion(np.asarray(t, np.int64), np.asarray(ts, np.int64), np.asarray(seq, np.int64),
                       np.asarray(inc, np.float64).reshape(-1, 2), np.asarray(ok, bool), np.asarray(resp),
                       np.asarray(con), np.asarray(scale, np.float64), np.asarray(src, np.int64).reshape(-1, 2),
                       np.asarray(masked, np.float64))


@dataclass
class OracleTrack:
    """The oracle camera as the image sees it. Row r is STATE frame f[r]."""
    f: np.ndarray            # (R,) frame numbers, ascending, unique
    t_eof: np.ndarray        # (R,) end of frame, ns
    pos: np.ndarray          # (R, 2) camera track in client px (x right, y down); NaN without a camera
    seg: np.ndarray          # (R,) track segment (positions are only comparable inside one); -1 without a camera
    screen: np.ndarray       # (R, 2) cam.screen; 0 without a camera
    breaks: dict = field(default_factory=dict)   # why segments started: scene / jump / no_cam / screen
    # (F, 6) screen-fixed content per row: row, kind (FIXED_*), x0, y0, x1, y1 as shares of cam.screen; row-sorted
    fixed: np.ndarray = field(default_factory=lambda: np.zeros((0, 6)))

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


FIXED_HERO, FIXED_HUD, FIXED_VIEW, FIXED_MARKER = range(4)   # OracleTrack.fixed kinds


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _hud_rects(hud: Any) -> list[list[float]]:
    """Client-px rects [x0, y0, x1, y1] of what a STATE "hud" (HudProbe) says is on screen: masks, lifeblood masks,
    bind orb, tool icons and the silk spool (its slot, chunk and notch centres, padded by the pitch and the chunk
    size). Hidden or not: masking a HUD that is not drawn only costs texture."""
    out: list[list[float]] = []
    if not isinstance(hud, dict):
        return out

    def rect(r: Any) -> None:
        if isinstance(r, (list, tuple)) and len(r) == 4 and all(_num(v) for v in r):
            out.append([min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])])

    for key, at in (("masks", 3), ("blue", 2), ("tools", 3)):
        for e in hud.get(key) or []:
            if isinstance(e, (list, tuple)) and len(e) > at:
                rect(e[at])
    rect(hud.get("bind_orb"))
    sp = hud.get("spool")
    if isinstance(sp, dict):
        n = len(out)
        rect(sp.get("chunk_rect"))
        pad = float(sp["pitch"]) if _num(sp.get("pitch")) else 0.0
        if len(out) > n:  # the spool is at least as tall as a chunk
            c = out[-1]
            pad = max(pad, c[2] - c[0], c[3] - c[1])
        pts = [p for p in [*(sp.get("slots") or []), *(sp.get("chunks") or []), sp.get("notch")]
               if isinstance(p, (list, tuple)) and len(p) >= 2 and _num(p[0]) and _num(p[1])]
        if pts:
            xy = np.asarray([p[:2] for p in pts], np.float64)
            lo, hi = xy.min(axis=0) - pad, xy.max(axis=0) + pad
            out.append([float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])])
    return out


def _marker_rect(mk: Any) -> list[list[float]]:
    """Client-px rect of the frame marker (STATE "mk", ssbot.record.marker) while it is on."""
    r = mk.get("rect") if isinstance(mk, dict) else None
    if isinstance(r, (list, tuple)) and len(r) == 4 and all(_num(v) for v in r):
        return [[float(r[0]), float(r[1]), float(r[2]), float(r[3])]]
    return []


def _view_bars(rect: np.ndarray) -> list[list[float]]:
    """Shares of the screen outside the camera viewport (normalized rect x, y, w, h; y up): letterbox bars."""
    x0, y0, x1, y1 = rect[0], 1.0 - (rect[1] + rect[3]), rect[0] + rect[2], 1.0 - rect[1]
    bars = [[0.0, 0.0, 1.0, y0], [0.0, y1, 1.0, 1.0], [0.0, 0.0, x0, 1.0], [x1, 0.0, 1.0, 1.0]]
    return [b for b in bars if b[2] - b[0] > 2e-3 and b[3] - b[1] > 2e-3]


def oracle_track(states: Iterable[dict], qpc_freq: int, jump_frac: float = Params.jump_frac,
                 hero_margin: tuple[float, float] = Params.hero_margin) -> OracleTrack:
    """Build the track from STATE dicts (only f, q, cam, game["scene"], hero pos/box, hud and mk are read). The step
    of row r is the image motion, between frames r - 1 and r, of the z = 0 point in front of the camera at r - 1, both
    under their own render-time matrices: exact for zoom (fov animations) and shake, which V/P carry. Screen-fixed
    content per row (OracleTrack.fixed): the hero collider box widened by hero_margin world units and projected with
    the row's V/P (the camera keeps her near the image centre), the HUD rects, the frame marker (it changes every
    frame, where a screen-fixed pattern would pull every step towards 0) and the bars outside the viewport."""
    rows: dict[int, tuple] = {}
    for s in states:
        f, q = s.get("f"), s.get("q")
        if not isinstance(f, int) or not isinstance(q, int) or f in rows:
            continue
        cam = s.get("cam")
        game = s.get("game") or {}
        good = isinstance(cam, dict) and all(isinstance(cam.get(k), list) for k in ("V", "P", "rect", "screen"))
        hero = s.get("hero")
        box = hero.get("box") if isinstance(hero, dict) else None
        pos = hero.get("pos") if isinstance(hero, dict) else None
        z = pos[2] if isinstance(pos, (list, tuple)) and len(pos) >= 3 and _num(pos[2]) else 0.0
        box = (*box, z) if isinstance(box, (list, tuple)) and len(box) == 4 and all(_num(v) for v in box) else None
        # Python ints: q * 1e9 overflows int64 (and float64 loses ms) once the machine has been up for days.
        rows[f] = (q * 1_000_000_000 // qpc_freq, cam if good else None, game.get("scene"), box,
                   _hud_rects(s.get("hud")), _marker_rect(s.get("mk")))
    fs = np.asarray(sorted(rows), np.int64)
    R = len(fs)
    t_eof = np.asarray([rows[f][0] for f in fs], np.int64)
    has = np.asarray([rows[f][1] is not None for f in fs], bool)
    scene = [rows[f][2] for f in fs]
    V16 = np.zeros((R, 16))
    P16 = np.zeros((R, 16))
    rect = np.zeros((R, 4))
    screen = np.zeros((R, 2))
    hbox = np.full((R, 5), np.nan)
    for r, f in enumerate(fs):
        cam = rows[f][1]
        if cam is not None:
            V16[r], P16[r], rect[r], screen[r] = cam["V"], cam["P"], cam["rect"], cam["screen"][:2]
            if rows[f][3] is not None:
                hbox[r] = rows[f][3]
    V, P = _cols(V16), _cols(P16)
    M = P @ V
    fixed = _fixed([rows[f][4] for f in fs], M, rect, screen, has, hbox, hero_margin, [rows[f][5] for f in fs])
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
    return OracleTrack(fs, t_eof, pos, seg, np.where(has[:, None], screen, 0.0), why, fixed)


def _fixed(huds: list[list], M: np.ndarray, rect: np.ndarray, screen: np.ndarray, has: np.ndarray,
           hbox: np.ndarray, margin: tuple[float, float], marks: list[list] | None = None) -> np.ndarray:
    """OracleTrack.fixed: per row with a camera, the hero box (x0, y0, x1, y1, z; NaN without one) widened by
    `margin` and projected with the row's P*V (all 4 corners), its HUD rects and frame marker rect (client px) and its
    letterbox bars, as shares of cam.screen."""
    R = len(has)
    out: list[tuple] = []
    wh = np.maximum(screen, 1.0)
    hv = has & np.isfinite(hbox).all(axis=1)
    if hv.any():
        b = np.nan_to_num(hbox)
        mx, my = margin
        corners = []
        for x, y in ((b[:, 0] - mx, b[:, 1] - my), (b[:, 2] + mx, b[:, 1] - my), (b[:, 0] - mx, b[:, 3] + my),
                     (b[:, 2] + mx, b[:, 3] + my)):
            px, front = _to_image(M, np.c_[x, y, b[:, 4], np.ones(R)], rect, screen)
            corners.append(px / wh)
            hv &= front
        c = np.stack(corners)                                # (4, R, 2)
        lo, hi = c.min(axis=0), c.max(axis=0)
        out.extend((r, FIXED_HERO, lo[r, 0], lo[r, 1], hi[r, 0], hi[r, 1]) for r in np.flatnonzero(hv))
    for r in np.flatnonzero(has):
        sw, sh = wh[r]
        out.extend((r, FIXED_HUD, x0 / sw, y0 / sh, x1 / sw, y1 / sh) for x0, y0, x1, y1 in huds[r])
        if marks is not None:
            out.extend((r, FIXED_MARKER, x0 / sw, y0 / sh, x1 / sw, y1 / sh) for x0, y0, x1, y1 in marks[r])
        out.extend((r, FIXED_VIEW, *bar) for bar in _view_bars(rect[r]))
    fixed = np.asarray(out, np.float64).reshape(-1, 6)
    return fixed[np.argsort(fixed[:, 0], kind="stable")]


def static_pixels(frames: Iterable[tuple[FrameInfo, np.ndarray]], min_steps: int = 60
                  ) -> dict[tuple[int, int], np.ndarray]:
    """Screen-fixed content that no label names (an overlay, a HUD element without a rect, a figure at the image
    centre without a hero export): per thumbnail shape, the pixels that keep their value (within 3 gray levels) in
    >= 80 % of the steps where the image as a whole changed (median |difference| > 3), and that have texture of their
    own (3x3 std of their mean >= 4 gray levels: masking a flat patch would only add the mask's edge as a static
    feature). None of it depends on D. {} before min_steps such steps."""
    acc: dict[tuple[int, int], list] = {}
    prev = None
    for _, img in frames:
        if prev is not None and prev.shape == img.shape:
            d = cv2.absdiff(img, prev)
            if np.median(d[::4, ::4]) > 3:
                a = acc.setdefault(img.shape, [0, np.zeros(img.shape, np.int32), np.zeros(img.shape, np.float64)])
                a[0] += 1
                a[1] += d <= 3
                a[2] += img
        prev = img
    out = {}
    for shape, (n, still, total) in acc.items():
        if n < min_steps:
            continue
        mean = (total / n).astype(np.float32)
        tex = np.sqrt(np.maximum(cv2.blur(mean * mean, (3, 3)) - cv2.blur(mean, (3, 3)) ** 2, 0.0))
        m = (still >= 0.8 * n) & (tex >= 4.0)
        if m.any():
            out[shape] = m
    return out


class ScreenFixed:
    """The weight that leaves screen-fixed content out of a registration step (register(fixed=...)): the rects of the
    labels (OracleTrack.fixed) and the pixels that static_pixels() found. The label of a capture depends on D, which
    is calibrated only after the registration, so a step between captures at t0 <= t1 masks what any STATE frame it
    could show holds: every frame with t0 - before <= t_eof <= t1 + after, i.e. D anywhere in the scan range and then
    +-K frames. Everything masked is widened by mask_margin * image height plus the feathering and set to 0 in a
    weight of 1, which is then blurred (sigma FEATHER thumbnail px), so that the edges of the mask stay nearly as
    smooth as the Hann window's. `always`: rects masked in every step (shares of the client), the vision mask's
    corner where the capture path filled it (the fill's edge is screen-fixed, and flat, so static_pixels skips it)."""

    FEATHER = 1.0

    def __init__(self, trk: OracleTrack, p: Params = Params(), static: dict | None = None,
                 always: list | None = None):
        self.t = trk.t_eof
        self.rows = trk.fixed[:, 0].astype(np.int64)
        self.norm = trk.fixed[:, 2:6]
        self.always = np.asarray(always or [], np.float64).reshape(-1, 4)
        period = int(np.median(np.diff(trk.t_eof))) if len(trk.t_eof) > 1 else 16_666_667
        self.before = int(round(p.scan_ms[1] * 1e6)) + (p.max_offset + 1) * period
        self.after = int(round(-p.scan_ms[0] * 1e6)) + p.max_offset * period
        self.margin = p.mask_margin
        self.static = {}
        for shape, m in (static or {}).items():
            r = int(round(self.margin * shape[0] + 2 * self.FEATHER))
            self.static[shape] = cv2.dilate(m.astype(np.uint8), np.ones((2 * r + 1, 2 * r + 1), np.uint8)) > 0
        self._key: tuple | None = None
        self._weight: np.ndarray | None = None

    def rects(self, t0: int, t1: int) -> np.ndarray:
        """(n, 4) shares of the screen masked for a step between captures at t0 <= t1 (ns)."""
        r0, r1 = np.searchsorted(self.t, [t0 - self.before, t1 + self.after + 1])
        a, b = np.searchsorted(self.rows, [r0, r1])
        return np.r_[self.norm[a:b], self.always] if len(self.always) else self.norm[a:b]

    def boxes(self, t0: int, t1: int, shape: tuple[int, ...]) -> np.ndarray:
        """(n, 4) thumbnail px [x0, y0, x1, y1) of that step, widened, clipped to the image and deduplicated."""
        h, w = shape[:2]
        m = self.margin * h + 2 * self.FEATHER
        box = np.round(self.rects(t0, t1) * [w, h, w, h] + [-m, -m, m, m])
        return self._clip(box, h, w)

    @staticmethod
    def _clip(box: np.ndarray, h: int, w: int) -> np.ndarray:
        box = np.clip(box, 0, [w, h, w, h]).astype(np.int64)
        return np.unique(box[(box[:, 2] > box[:, 0]) & (box[:, 3] > box[:, 1])], axis=0)

    def _blurred(self, box: np.ndarray, static: np.ndarray | None, h: int, w: int) -> np.ndarray:
        keep = np.ones((h, w), np.float32)
        if static is not None:
            keep[static] = 0.0
        for x0, y0, x1, y1 in box:
            keep[y0:y1, x0:x1] = 0.0
        return cv2.GaussianBlur(keep, (0, 0), self.FEATHER).astype(np.float64)

    def weight(self, t0: int, t1: int, shape: tuple[int, ...]) -> tuple[tuple | None, np.ndarray | None]:
        """(key, weight (h, w) in [0, 1]) of that step; (None, None) when nothing is masked. Equal keys, equal
        weights."""
        h, w = shape[:2]
        box = self.boxes(t0, t1, shape)
        static = self.static.get((h, w))
        if not len(box) and static is None:
            return None, None
        key = (h, w, box.tobytes())
        if key != self._key:
            self._key, self._weight = key, self._blurred(box, static, h, w)
        return key, self._weight

    def moved_weight(self, t0: int, t1: int, shape: tuple[int, ...], dx: float, dy: float) -> np.ndarray:
        """The weight for the second pass (register), where the later capture's content was moved back by (dx, dy):
        its screen-fixed content now lies (dx, dy) off where it was, so both places are masked in both images."""
        h, w = shape[:2]
        box = self.boxes(t0, t1, shape)
        static = self.static.get((h, w))
        if static is not None:
            ix, iy = int(round(dx)), int(round(dy))
            moved = np.zeros_like(static)
            moved[max(-iy, 0):h - max(iy, 0), max(-ix, 0):w - max(ix, 0)] = \
                static[max(iy, 0):h - max(-iy, 0), max(ix, 0):w - max(-ix, 0)]
            static = static | moved
        return self._blurred(self._clip(np.r_[box, box - np.round([dx, dy, dx, dy])], h, w), static, h, w)


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
    anomaly: np.ndarray      # (N,) increment into capture i: 1 part of an excursion (left out of the fits), 2 break
    excursion: np.ndarray    # (N,) capture inside an excursion: off and back (anomalies paired up), judged alone
    consistent: np.ndarray   # (N,) the window centred here is decisive and consistent at its k (_consistent)


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
                       np.zeros(N, np.int64), nothing, nan, nan, np.zeros(N), nan, np.zeros(N, np.int8), nothing,
                       nothing)
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
    # has it when its own window holds enough trusted increments and oracle motion that tells k = 0 from every other
    # k (the camera changes speed inside it). The decisive windows of this pass only give the scale for the anomaly
    # test.
    s1, e1 = _segments(link)
    w1 = _windows(mot.inc, O, iv, np.maximum(idx - W, s1), np.minimum(idx + W, e1), scale, p)
    evidence = w1.distinct
    ref1, has1 = _nearest(w1.decisive, s1, e1, W)
    a1 = w1.a[idx, w1.best]
    a_loc = np.where(has1, a1[ref1], float(np.median(a1[w1.decisive])) if w1.decisive.any() else 1.0)

    # Anomalies: trusted increments that a * the oracle increment explains at no k. Excursions (_excursions): two of
    # them, or one and the increment next to it, whose sum is explained: captures that were out of step and came back
    # (stale, glitched, a short run of repeated or skipped frames). Their increments leave the fits, their sum enters
    # them as one increment, the captures inside are nobody's neighbours, and the track goes on through them. Any
    # other anomaly (a latency step, after which the offset stays changed, or a registration glitch) breaks the
    # segment, so that no window or neighbour set mixes the two sides.
    # The noise is that of the increments at their best k (_noise), not of the pass-1 windows, which hold the anomalies
    # (a stale pair every 20 captures in a dash raised their sigma to ~3 px, and a 14 px jump no longer stood out).
    j = np.flatnonzero(iv)
    miss = np.linalg.norm(mot.inc[j, None, :] - a_loc[j, None, None] * O[j], axis=2).min(axis=1)
    noise = _noise(miss, p.noise_bound)
    thr = np.maximum(0.5 * min_sep, p.outlier * noise)
    anom = np.zeros(N, bool)
    anom[j] = miss > thr[j]
    exc, covered, (xs, xe) = _excursions(anom, iv, mot.inc, Pk, a_loc, thr, p.max_excursion)
    brk = anom & ~covered

    # Pass 2: windows without the anomalies, on segments broken at the unpaired ones.
    link = link & ~brk
    seg_start, seg_end = _segments(link)
    lo, hi = np.maximum(idx - W, seg_start), np.minimum(idx + W, seg_end)
    U, O2 = mot.inc.copy(), O.copy()
    Cr = _prefix(mot.inc)
    U[xe], O2[xe] = Cr[xe + 1] - Cr[xs], Pk[xe] - Pk[xs - 1]
    fit = iv & ~anom & ~covered
    fit[xe] = True
    w2 = _windows(U, O2, fit, lo, hi, scale, p)
    best, decisive = w2.best, w2.decisive

    # A capture is judged only by its own window (centred on it, in its own segment), and only when that window is
    # decisive, every decisive window it lies inside agrees on k, and the own window is consistent at that k
    # (_consistent: every increment of the fit explained at that k, not merely at some k, and the positions on one
    # line). A window is decisive from wherever the camera changed speed inside it, which may lie across a change of
    # the offset that did not show: a run of captures one frame late whose repeated frame fell while the camera
    # stood still. Its captures then fit k = 0 against their equally late neighbours wherever the camera moves at
    # constant speed, and borrowing k from a window centred on the aligned side judged them at 0 (verify3: a
    # stand -> walk change inside the run, 16-18 late captures judged at 0, PASS). Inside the run's own windows the
    # speed change is explained only at k = -1, and every position after it lies a step off: MIXED, counting against
    # the share. Only the own segment: the captures between two breaks may be a run out of step too long to pair,
    # so a segment too short for a decisive window of its own leaves its captures unjudged (CUT), whether the breaks
    # were such a run or registration glitches. The monitor may fail an aligned recording (MIXED, CUT and SPLIT
    # captures next to misaligned or badly registered ones); it must not judge a misaligned capture at 0.
    votes = _prefix((decisive[:, None] & (best[:, None] == np.arange(len(ks))[None, :])).astype(np.float64))
    agree = ((votes[hi + 1] - votes[lo]) > 0).sum(axis=1) <= 1
    thr_fit = thr.copy()
    thr_fit[xe] = thr[xs] * np.sqrt((xe - xs + 1) / 2)       # an excursion's sum, as _excursions tests it
    consistent = np.zeros(N, bool)
    consistent[decisive] = _consistent(U, O2, fit, lo, hi, best, w2.a[idx, best], thr_fit, 0.5 * min_sep, noise, p,
                                       np.flatnonzero(decisive))
    has_ref = decisive & agree & consistent
    kref = np.where(has_ref, best, K)
    a_ref = np.where(has_ref, w2.a[idx, kref], np.nan)

    # Video positions inside each segment; the neighbour constant c = median(video - a * oracle at kref) over the
    # nearest h captures on each side that are not inside an excursion (those are off). They lie inside the capture's
    # own window, which the checks above tie to the window's evidence at kref.
    csum = np.cumsum(np.where(link[:, None], mot.inc, 0.0), axis=0)
    Cv = csum - csum[seg_start]
    nb = usable & ~exc

    def side(sign: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        res = np.full((N, h, 2), np.nan)
        cnt = np.zeros(N, np.int64)
        for d in range(1, h + p.max_excursion + 1):
            at = idx + sign * d
            j = np.clip(at, 0, N - 1)
            pj = Pk[j, kref]
            okj = has_ref & (at >= seg_start) & (at <= seg_end) & nb[j] & np.isfinite(pj[:, 0]) & (cnt < h)
            res[okj, cnt[okj]] = Cv[j][okj] - a_ref[okj, None] * pj[okj]
            cnt += okj
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN rows: no neighbours on this side
            c = np.nanmedian(res, axis=1)
        e = np.linalg.norm(Cv[:, None, :] - a_ref[:, None, None] * Pk - c[:, None, :], axis=2)
        e = np.where(np.isfinite(e), e, np.inf)
        o = np.argsort(e + 1e-9 * np.abs(ks[None, :] - ks[kref][:, None]), axis=1, kind="stable")  # ties: near kref
        return cnt >= 2, o[:, 0], e[idx, o[:, 0]], e[idx, o[:, 1]]

    okL, kL, eL1, eL2 = side(-1)
    okR, kR, eR1, eR2 = side(1)
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
    # Not judged, counting against the share: MIXED when the own window is decisive but not consistent at its k, or
    # a decisive window the capture lies inside disagrees; CUT when the anomalies are why (a decisive window lies
    # within W across the breaks, the same fits on the segments before the breaks included, or the capture is inside
    # an excursion whose neighbours are off too); NO_WINDOW when nothing within W fits at all.
    none = ~(okL | okR)
    lo1, hi1 = np.maximum(idx - W, s1), np.minimum(idx + W, e1)
    across = _prefix((decisive | _windows(U, O2, fit, lo1, hi1, scale, p).decisive).astype(np.float64))
    status[none] = np.where(((across[hi1 + 1] - across[lo1] > 0) | exc)[none], CUT, NO_WINDOW)
    status[none & decisive & ~has_ref] = MIXED
    # Uninformative: the own window, as registered (before the anomalies broke it), holds too few trusted increments
    # or camera motion that tells no k apart (the camera still or at constant speed throughout): no video could show
    # this capture's offset. Left out and reported as such, never as aligned.
    status[(status != OK) & ~evidence] = UNINFORMATIVE
    status[sep < min_sep] = LOW_MOTION
    status[gap] = STATE_GAP
    status[~labeled] = NO_LABEL
    return Offsets(D=int(D), label=L, status=status, k=ks[k_idx], clear=clear & (status == OK),
                   k_window=np.where(decisive, ks[best], 0), decisive=decisive & usable, a=a_ref,
                   resid=np.where(status == OK, resid, np.nan), sep=sep, sigma=w2.sigma,
                   anomaly=np.where(covered, 1, np.where(brk, 2, 0)).astype(np.int8), excursion=exc,
                   consistent=consistent & usable)


def _consistent(U: np.ndarray, O: np.ndarray, fit: np.ndarray, lo: np.ndarray, hi: np.ndarray, k_idx: np.ndarray,
                a: np.ndarray, thr: np.ndarray, floor: np.ndarray, noise: float, p: Params, which: np.ndarray,
                chunk: int = 256) -> np.ndarray:
    """For the windows centred at `which` ([lo, hi], fitted at k index k_idx and scale a): whether (1) every increment
    of the fit is explained at that k (|U - a O| <= thr, the anomaly threshold), and (2) between any two captures i < j
    of the window, the video's displacement matches a times the oracle's at that k, on each axis, to within
    max(floor, drift * noise * sqrt(j - i)) + scale_tol * the oracle's displacement. (1) catches a change of the
    offset that shows where the camera changes speed abruptly; (2) one that shows where it changes speed gradually
    (every increment within the noise, their sum a whole step while the camera moved little), and it tolerates a
    registration scale that drifts with the camera speed by up to scale_tol (0.997-1.003 on the synthetic scenes)."""
    out = np.zeros(len(which), bool)
    if not len(which):
        return out
    N = len(fit)
    L = int((hi[which] - lo[which]).max()) + 1
    span = np.arange(L)
    gap = np.sqrt(np.abs(np.arange(L + 1)[:, None] - np.arange(L + 1)[None, :])).astype(np.float32)
    for s in range(0, len(which), chunk):
        c = which[s:s + chunk]
        t = lo[c, None] + span[None, :]
        m = t <= hi[c, None]
        t = np.minimum(t, N - 1)
        m &= fit[t]
        aO = np.where(m[..., None], a[c, None, None] * O[t, k_idx[c][:, None]], 0.0)
        r = np.where(m[..., None], U[t], 0.0) - aO
        worst = np.where(m, np.linalg.norm(r, axis=2) / thr[t], 0.0).max(axis=1)
        zero = np.zeros((len(c), 1, 2))
        S = np.concatenate([zero, np.cumsum(r, axis=1)], axis=1).astype(np.float32)   # video - a * oracle
        Q = np.concatenate([zero, np.cumsum(aO, axis=1)], axis=1).astype(np.float32)  # a * oracle
        tol = np.maximum(floor[c, None, None].astype(np.float32), np.float32(p.drift * noise) * gap[None])
        path = np.ones(len(c), bool)
        for ax in range(2):
            dS = np.abs(S[:, :, None, ax] - S[:, None, :, ax])
            dQ = np.abs(Q[:, :, None, ax] - Q[:, None, :, ax])
            path &= (dS <= tol + np.float32(p.scale_tol) * dQ).all(axis=(1, 2))
        out[s:s + chunk] = (worst <= 1.0) & path
    return out


def _noise(miss: np.ndarray, bound: float) -> float:
    """Per-axis noise of the increments from their misses at the best k (the norm of a 2-D normal is Rayleigh: median
    1.1774 sigma, lower quartile 0.7585 sigma): the median estimate, which a minority of anomalies does not raise,
    bounded by `bound` times the lower-quartile estimate. Every stale capture spoils two increments, so judder can
    make half of them anomalous (every 2nd capture stale over half of a recording), and the median then lies among
    the anomalies: 2.5 px for ~0.01 px, nothing stood out, and the judder went unjudged instead of being judged capture
    by capture (1 - share 0.52 against 0.26 true). The lower quartile holds until three quarters are anomalous, and on
    clean increments the bound lies ~bound times above the median estimate, so it does not bind there. (Not the
    low-motion increments' noise: a still image registers ~3x quieter than a moving one, and still stretches may be
    missing.)"""
    if not len(miss):
        return 0.0
    q25, q50 = np.percentile(miss, [25, 50])
    return float(min(q50 / 1.1774, bound * q25 / 0.7585))


def _excursions(anom: np.ndarray, iv: np.ndarray, inc: np.ndarray, Pk: np.ndarray, a: np.ndarray, thr: np.ndarray,
                longest: int) -> tuple[np.ndarray, np.ndarray, tuple[np.ndarray, np.ndarray]]:
    """Excursions: runs of trusted increments j .. e whose sum is explained at some k (the captures before j and at e
    fit one offset): captures j .. e - 1 were out of step and e is back. Either both ends are anomalies, at most
    `longest` apart with none between, or one is and the run is one capture long: a stale capture's repeated frame,
    0 px, is "explained" by a k at which the camera had stopped, and only the step out of it stands out. (Longer runs
    with one anomalous end would take the start of a latency step for an excursion whenever the camera stops soon
    after it.) Of the sets of non-overlapping excursions, the one with the most anomalies inside (fewest breaks) and
    then the fewest captures out of step: with every 3rd capture stale, (s, s + 1) and (s + 1, s + 3) both explain
    their sums, and 1 capture in 3 out of step is the reading the fits agree with (with every 2nd capture stale the
    two readings tie; the fits and the neighbours then judge every capture alike either way). Returns (captures
    j .. e - 1, increments j .. e, (every j, every e))."""
    N = len(anom)
    exc, covered = np.zeros(N, bool), np.zeros(N, bool)
    A = np.flatnonzero(anom)
    runs: list[tuple[int, int]] = []
    for q, x in enumerate(A):
        x = int(x)
        if q and x - A[q - 1] <= longest:
            runs.append((int(A[q - 1]), x))
        if x - 1 >= 1 and not anom[x - 1]:
            runs.append((x - 1, x))
        if x + 1 < N and not anom[x + 1]:
            runs.append((x, x + 1))
    if not runs:
        return exc, covered, (np.zeros(0, np.int64), np.zeros(0, np.int64))
    J, E = np.asarray(runs, np.int64).T
    bad = _prefix((~iv).astype(np.float64))
    C = _prefix(inc)
    ok = bad[E + 1] - bad[J] == 0
    with np.errstate(invalid="ignore"):  # Pk may be NaN where not all trusted (not ok anyway)
        miss = np.linalg.norm((C[E + 1] - C[J])[:, None, :] - a[J, None, None] * (Pk[E] - Pk[J - 1]),
                              axis=2).min(axis=1)
        ok &= miss <= thr[J] * np.sqrt((E - J + 1) / 2)
    J, E = J[ok], E[ok]
    o = np.lexsort((J, E))
    J, E = J[o], E[o]
    gain = anom[J].astype(int) + anom[E].astype(int)
    prior = np.searchsorted(E, J, side="left")   # runs before this one end before its first increment
    # Weighted interval scheduling: best[i] = the best set among the first i runs, as (anomalies, -captures).
    best: list[tuple[int, int]] = [(0, 0)] * (len(J) + 1)
    take = np.zeros(len(J), bool)
    for i in range(len(J)):
        t = (best[prior[i]][0] + int(gain[i]), best[prior[i]][1] - int(E[i] - J[i]))
        best[i + 1], take[i] = (t, True) if t > best[i] else (best[i], False)
    chosen: list[int] = []
    i = len(J)
    while i > 0:
        if take[i - 1]:
            chosen.append(i - 1)
            i = int(prior[i - 1])
        else:
            i -= 1
    for i in chosen:
        exc[J[i]:E[i]] = True
        covered[J[i]:E[i] + 1] = True
    c = np.asarray(sorted(chosen), np.int64)
    return exc, covered, (J[c], E[c])


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
    """D from the clearly judged captures (agree_interval)."""
    sel = np.flatnonzero((off.status == OK) & off.clear)
    if len(sel) == 0:
        return Sweep(None, None, None)
    rows = trk.row_of()[trk.f[off.label[sel]] + off.k[sel] - trk.f[0]]
    return agree_interval(t_cap[sel], rows, trk.t_eof)


def agree_interval(t: np.ndarray, rows: np.ndarray, t_eof: np.ndarray) -> Sweep:
    """Capture i at time t[i] that shows STATE row rows[i] is matched correctly iff
    t - t_eof[r + 1] < D <= t - t_eof[r]: the middle of the widest interval of D that the most captures agree on."""
    if len(rows) == 0:
        return Sweep(None, None, None)
    R = len(t_eof)
    hi = t - t_eof[rows]
    lo = np.where(rows + 1 < R, t - t_eof[np.minimum(rows + 1, R - 1)], np.iinfo(np.int64).min)
    B = np.unique(np.r_[lo[lo > np.iinfo(np.int64).min], hi])
    if len(B) < 2:
        return Sweep(int(B[0]), None, None, len(rows), len(rows))
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
    return Sweep((a_ + b_) // 2, a_, b_, top, len(rows))


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
    share: float | None = None               # zero / (informative + unjudged): the monitor's verdict
    share_judged: float | None = None        # zero / informative
    hist: dict = field(default_factory=dict)          # per-capture offset -> count
    window_hist: dict = field(default_factory=dict)   # decisive window offset -> count
    unjudged_by: dict = field(default_factory=dict)   # no_window / split / cut -> count
    excluded: dict = field(default_factory=dict)      # statuses left out -> count
    anomalies: dict = field(default_factory=dict)     # increments left out of the fits (excursions) / track breaks
    excursions: dict = field(default_factory=dict)    # anomaly pairs: runs out of step and back, captures, longest
    split_at: list = field(default_factory=list)      # [first, last] capture of the first 20 runs of SPLIT captures
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
    masked: dict | None = None                # steps registered with screen-fixed content masked; share masked
    track_breaks: dict | None = None
    screen: list | None = None
    src: list | None = None
    scale_a: dict | None = None
    scale_by_speed: dict | None = None        # registration scale per camera speed (thumbnail px/capture): parallax
    noise_px: dict | None = None
    resid_px: dict | None = None
    labels: dict | None = None                # the video's label sources (VideoReader.labels): marker / timestamp
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
            f" masked {self.masked}; track breaks {self.track_breaks}",
            f"registration scale by camera speed (thumbnail px per capture): {self.scale_by_speed}",
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
            lines.append(f"  offsets {c.hist}; decisive windows {c.window_hist}; excluded {c.excluded}")
            lines.append(f"  anomalies {c.anomalies}; excursions {c.excursions}")
            if c.split_at:
                lines.append(f"  split captures (first, last): {c.split_at}")
            if c.first_nonzero:
                lines.append(f"  first non-zero (capture, seq, frame, k): {c.first_nonzero}")
        lines.append(f"noise: window sigma {self.noise_px}; per-capture residual {self.resid_px} (client px)")
        if self.labels:
            lb = self.labels
            lines.append(f"labels: {lb['marker']} of {lb['captures']} captures carry a marker label "
                         f"({pct(lb['share'])}, exact); the monitor's verdict concerns the {lb['timestamp']} timestamp "
                         f"labels")
        lines.extend(f"note: {n}" for n in self.notes)
        lines.append(f"{'PASS' if self.ok else pr.verdict if pr else 'FAIL'} (monitor): "
                     f"{pct(pr.share if pr else None)} of the judgeable captures judged at offset 0 on the "
                     f"{pr.clock if pr else '?'} clock (threshold {self.threshold * 100:.1f} %; judged >= "
                     f"{self.min_informative} and >= {self.min_coverage * 100:.0f} % of the captures); what it cannot "
                     f"see is left out, and the share of aligned captures is what the frame marker measures")
        return "\n".join(lines)


def _hist(x: np.ndarray) -> dict:
    v, c = np.unique(x, return_counts=True)
    return {int(a): int(b) for a, b in zip(v, c)}


SPEED_BINS = (0.5, 1.0, 2.0, 4.0, 8.0, math.inf)   # thumbnail px per capture (scale_by_speed)


def scale_by_speed(mot: VideoMotion, trk: OracleTrack, off: Offsets) -> dict:
    """The registration scale against the camera speed, over consecutive judged captures with a trusted increment:
    the video increment projected on the oracle camera step between the frames the two show (at their judged k), per
    bin of that step's length in thumbnail px: {"lo-hi": [steps, p10, p50, p90]} (bins with >= 5 steps). One parallax
    layer, or several whose weights do not change with the speed, gives one scale at every speed; two layers of
    comparable weight give a scale that changes with it, which one a per window cannot absorb (aligned captures then
    SPLIT near speed changes: see the module docstring, "parallax")."""
    ok = off.status == OK
    i = np.flatnonzero(ok[1:] & ok[:-1] & mot.ok[1:]) + 1
    if not len(i) or not len(trk.f):
        return {}
    row_of = trk.row_of()
    r1, r0 = (row_of[np.clip(trk.f[off.label[c]] + off.k[c] - trk.f[0], 0, len(row_of) - 1)] for c in (i, i - 1))
    same = (r1 >= 0) & (r0 >= 0) & (trk.seg[r1] == trk.seg[r0]) & (trk.seg[r1] >= 0)
    i, r1, r0 = i[same], r1[same], r0[same]
    step = trk.pos[r1] - trk.pos[r0]
    n2 = (step ** 2).sum(axis=1)
    speed = np.sqrt(n2) / mot.scale[i]
    out = {}
    for lo, hi in zip(SPEED_BINS[:-1], SPEED_BINS[1:]):
        s = (speed >= lo) & (speed < hi)
        if s.sum() >= 5:
            ratio = (mot.inc[i[s]] * step[s]).sum(axis=1) / n2[s]
            out[f"{lo:g}-{hi:g}"] = [int(s.sum()), *(round(float(v), 3) for v in np.percentile(ratio, [10, 50, 90]))]
    return out


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
    starts = np.flatnonzero(off.excursion & ~np.r_[False, off.excursion[:-1]])
    ends = np.flatnonzero(off.excursion & ~np.r_[off.excursion[1:], False])
    res.excursions = {"runs": len(starts), "captures": int(off.excursion.sum()),
                      "longest": int((ends - starts + 1).max()) if len(starts) else 0}
    sel = ok & off.clear
    if sel.any():
        rows = trk.row_of()[trk.f[off.label[sel]] + off.k[sel] - trk.f[0]]
        lag = (t_cap[sel] - trk.t_eof[rows]) / 1e6
        res.lag_ms = {"p1": round(_p(lag, 1), 3), "p50": round(_p(lag, 50), 3), "p99": round(_p(lag, 99), 3),
                      "min": round(float(lag.min()), 3), "max": round(float(lag.max()), 3)}
    bad = np.flatnonzero(ok & (off.k != 0))
    res.first_nonzero = [[int(i), int(mot.seq[i]), int(trk.f[off.label[i]]), int(off.k[i])] for i in bad[:10]]
    sp = off.status == SPLIT
    starts = np.flatnonzero(sp & ~np.r_[False, sp[:-1]])
    ends = np.flatnonzero(sp & ~np.r_[sp[1:], False])
    res.split_at = [[int(a_), int(b_)] for a_, b_ in zip(starts[:20], ends[:20])]
    need = max(1, p.min_informative, math.ceil(p.min_coverage * len(t_cap)))
    if judgeable and judgeable >= p.min_informative and res.share < p.threshold:
        off0 = res.informative - res.zero
        by = ", ".join(f"{k} {v}" for k, v in res.unjudged_by.items() if v)
        res.reason = f"{off0} judged captures off offset 0, {res.unjudged} unjudged" + (f" ({by})" if by else "")
        if res.unjudged_by["no_window"] > off0:
            res.reason += "; no window fits around the unjudged: periodic repeated or skipped frames?"
        ex = res.excursions
        if ex["runs"]:
            res.reason += f"; {ex['runs']} runs of captures out of step and back ({ex['captures']} captures)"
        if res.anomalies["breaks"]:
            res.reason += f"; {res.anomalies['breaks']} track breaks (latency steps or registration glitches)"
    elif res.informative < need:
        res.verdict, res.reason = "INCONCLUSIVE", (f"only {res.informative} judged captures (< {need}: at least "
                                                   f"{p.min_informative} and {p.min_coverage * 100:.0f} % of "
                                                   f"{len(t_cap)} captures)")
    else:
        res.verdict, res.ok = "PASS", True
        if res.anomalies["breaks"]:
            res.reason = (f"{res.anomalies['breaks']} track breaks (latency steps or registration glitches) among "
                          f"{res.excluded.get('uninformative', 0)} uninformative captures: the monitor cannot judge "
                          f"those")
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
    m = mot.masked[mot.masked > 0]
    rep.masked = {"steps": len(m), "p50": _r(_p(m, 50)), "max": _r(_p(m, 100))} if len(m) else None
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
        rep.scale_by_speed = scale_by_speed(mot, trk, off)
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
    trk = oracle_track(rr.states(keys=("q", "cam", "game", "hero", "hud", "mk")), freq, p.jump_frac, p.hero_margin)
    fixed = None
    if p.mask:
        static = static_pixels(vr.frames())
        always = _vision_mask(vr)
        if len(trk.fixed) or static or always:
            fixed = ScreenFixed(trk, p, static, always)
    mot = register(vr.frames(), p, progress, fixed)
    return mot, trk


def _vision_mask(vr: VideoReader) -> list[list[float]]:
    """The vision mask's rect as shares of the client, per client size, where the capture path filled it."""
    if not vr.meta.get("mask"):
        return []
    sizes = {tuple(r[0]) for r in vr.meta["mask"].get("rects") or ()}
    if not sizes:  # a recording that was not closed: the first capture's client size
        sizes = {(info.src_w, info.src_h) for info, _ in zip(vr.frames(), range(1))}
    return [[x0 / w, y0 / h, x1 / w, y1 / h] for w, h in sizes for x0, y0, x1, y1 in [vmask.mask_rect(w, h)]]


def align_episode(path: str | Path, p: Params = Params(), clock: str = GATE_CLOCK, D_ms: float | None = None,
                  progress: Callable[[int], None] | None = None) -> tuple[AlignReport, Offsets | None, VideoMotion,
                                                                         OracleTrack]:
    mot, trk = load(path, p, progress)
    rep, off = align(mot, trk, p, clock, D_ms)
    rep.path = str(path)
    rep.labels = VideoReader(path).labels()
    return rep, off, mot, trk


def dump(path: Path, off: Offsets, mot: VideoMotion, trk: OracleTrack, **extra: np.ndarray) -> None:
    """Per-capture arrays for a closer look (numpy .npz); `extra` adds more (the probe: the marker's truth)."""
    L = off.label
    np.savez_compressed(path, seq=mot.seq, t_arrival=mot.t_arrival, t_frame=mot.t_frame, inc=mot.inc, ok=mot.ok,
                        response=mot.response, label_row=L, label_f=np.where(L >= 0, trk.f[np.clip(L, 0, None)], -1),
                        status=off.status, k=off.k, clear=off.clear, k_window=off.k_window, decisive=off.decisive,
                        consistent=off.consistent, a=off.a, resid=off.resid, sep=off.sep, anomaly=off.anomaly,
                        excursion=off.excursion, masked=mot.masked, D=off.D, state_f=trk.f, state_t_eof=trk.t_eof,
                        state_pos=trk.pos, state_seg=trk.seg, **extra)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.record.align", description=__doc__.split("\n")[0])
    ap.add_argument("path", help="episode folder with state.* and video.*")
    ap.add_argument("--clock", choices=("frame", "arrival"), default=GATE_CLOCK,
                    help="primary clock: WGC SystemRelativeTime (frame, default, DESIGN 3.1.4) or callback arrival; "
                         "the other one is reported as a cross-check")
    ap.add_argument("--D-ms", type=float, help="use this capture offset instead of calibrating it")
    ap.add_argument("--max-offset", type=int, default=Params.max_offset)
    ap.add_argument("--window", type=int, default=Params.window)
    ap.add_argument("--min-sep", type=float, default=Params.min_sep, help="thumbnail px (low-motion exclusion)")
    ap.add_argument("--min-informative", type=int, default=Params.min_informative)
    ap.add_argument("--min-coverage", type=float, default=Params.min_coverage,
                    help="judged captures needed, as a share of all captures")
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--no-mask", action="store_true",
                    help="register the whole thumbnails, screen-fixed content included (to compare)")
    ap.add_argument("--json", action="store_true", help="also write align.json into the episode folder")
    ap.add_argument("--dump", action="store_true", help="also write per-capture arrays to align_frames.npz")
    a = ap.parse_args(argv)
    p = Params(max_offset=a.max_offset, window=a.window, min_sep=a.min_sep, min_informative=a.min_informative,
               min_coverage=a.min_coverage, threshold=a.threshold, mask=not a.no_mask)
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
