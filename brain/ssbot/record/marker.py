"""Frame marker: ground truth for frame/label alignment (DESIGN §3.1.4 C4; the M1 alignment gate, >= 99.5 %).

In a validation-only session the oracle draws, into every image it renders while the marker is on (RPC
"frame.marker", training profiles only), a small black and white pattern that encodes Time.frameCount: the number
STATE "f" carries for that frame (oracle/src/Export/FrameMarker.cs draws it in OnGUI, after every camera and every
other GUI, before the end-of-frame STATE is built). STATE "mk" is non-nil while it is on, so a recording made with it
is identifiable (RecordingReader.check reports it): it is validation data and never training data. The rule "no
barcode in the pixels" (C4) holds for everything the bot learns from.

Layout (oracle/src/Export/MarkerCode.cs is the same code; tests pin both to the same vectors): a grid of
(ROWS + 2) x (COLS + 2) square cells of `cell` client px, `cell` px in from one corner of the client area, drawn with
a one-cell black border. Grid row gr = 0 .. ROWS + 1 (top to bottom), column gc = 0 .. COLS + 1 (left to right),
1 = white:
    border (gr in {0, ROWS + 1} or gc in {0, COLS + 1})   black
    gc = 1        gr = 1 white, gr = 2 black                (sync)
    gc = COLS     gr = 1 black, gr = 2 white                (sync)
    gc = 2 .. COLS - 1: bit j = (gc - 2) + (gr - 1) * (COLS - 2), j = 0 .. 19:
        j = 0 .. 15   bit j of the frame number (LSB first; the frame modulo 65536)
        j = 16 .. 19  bit j - 16 of crc4 of those 16 bits (x^4 + x + 1, MSB first)
With the default cell (screen height / 60: 12 px at 720p, 18 at 1080p) a cell spans 3 px of a 320 px wide thumbnail.

Decoding (decode): the cell centres follow from STATE "mk" rect and cell and the thumbnail's scale (FrameInfo w / src_w);
a search over +-1.5 thumbnail px absorbs a client crop a few px off. Each cell is the mean of 3 x 3 bilinear samples
over its inner 40 %. The border and the black sync cells give the black level, the white sync cells the white level;
the pattern is "absent" unless every border and sync cell lies on its side of the middle by a quarter of the contrast
(and the contrast is >= MIN_CONTRAST), "unclear" if a data cell does not, "check" if the crc fails. The 16 bits are
unwrapped to the frame nearest a reference (the capture's label).

The exact report (exact): D is calibrated from the truth (align.agree_interval: the D most captures agree on, over
the decoded frames), then every capture gets its label (align.match) and its offset k = decoded frame - label.
Counted: labelled captures whose label's next frame has a STATE (as in the monitor). A counted capture without a
decodable marker although the marker was drawn in every frame within max_offset of its label is "missing" and counts
against the share: the gate may fail an aligned recording, never pass a misaligned one. Share = captures at offset 0 /
(decoded + missing); PASS >= threshold with >= min_captures counted, INCONCLUSIVE below. Also: the offset histogram,
duplicates (consecutive captures that show the same frame) and skips (frames between two consecutive captures that
no capture shows), frames never captured, the lag from end of frame to capture, and the arrival clock as a
cross-check. score_monitor compares the correlation monitor (ssbot.record.align) with the truth capture by capture.

    python -m ssbot.record.marker <episode> [--json] [--monitor]   (exit 1 unless PASS)
"""
import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2  # comes with windows-capture
import numpy as np

from ssbot.record import align
from ssbot.record.recorder import RecordingReader
from ssbot.record.video import VideoReader

ROWS, COLS = 2, 12
DATA_BITS, CHECK_BITS = 16, 4
MODULUS = 1 << DATA_BITS
CORNERS = ("tl", "tr", "bl", "br")
MIN_CONTRAST = 64.0     # gray levels between the white and the black cells
CLARITY = 0.25          # every cell at least this share of the contrast away from the middle
SEARCH = 1.5            # thumbnail px searched around the expected position, both axes
THRESHOLD = align.THRESHOLD


def crc4(value: int) -> int:
    """CRC-4 (x^4 + x + 1, init 0, no reflection) of the DATA_BITS low bits of value, MSB first."""
    crc = 0
    for i in range(DATA_BITS - 1, -1, -1):
        fb = ((crc >> 3) & 1) ^ ((value >> i) & 1)
        crc = (crc << 1) & 0xF
        if fb:
            crc ^= 0x3
    return crc


def bits(frame: int) -> list[int]:
    """The 20 data-cell bits of a frame number (j = 0 .. 19, see the module docstring)."""
    v = frame % MODULUS
    c = crc4(v)
    return [(v >> j) & 1 for j in range(DATA_BITS)] + [(c >> j) & 1 for j in range(CHECK_BITS)]


def grid(frame: int) -> np.ndarray:
    """(ROWS + 2, COLS + 2) uint8, 1 = white: the whole pattern of `frame`, border included."""
    g = np.zeros((ROWS + 2, COLS + 2), np.uint8)
    g[1, 1] = 1
    g[2, COLS] = 1
    for j, b in enumerate(bits(frame)):
        g[1 + j // (COLS - 2), 2 + j % (COLS - 2)] = b
    return g


def _structure() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Masks over the grid: the cells that are always black, always white, and the data cells."""
    black = np.zeros((ROWS + 2, COLS + 2), bool)
    black[0, :] = black[-1, :] = black[:, 0] = black[:, -1] = True
    black[2, 1] = black[1, COLS] = True
    white = np.zeros_like(black)
    white[1, 1] = white[2, COLS] = True
    return black, white, ~(black | white)


BLACK, WHITE, DATA = _structure()


@dataclass(frozen=True)
class Geometry:
    """Where the marker is, in client px (top-left origin): the grid's top-left corner (border included) and cell."""
    x0: float
    y0: float
    cell: float

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x0 + (COLS + 2) * self.cell, self.y0 + (ROWS + 2) * self.cell)

    @staticmethod
    def place(screen: tuple[int, int], corner: str = "tr", cell: int | None = None) -> "Geometry":
        """The oracle's placement (FrameMarker.cs): `cell` px from the two edges of `corner`; cell defaults to
        max(4, round(screen height / 60))."""
        w, h = screen
        c = cell or max(4, round(h / 60))
        gw, gh = (COLS + 2) * c, (ROWS + 2) * c
        x0 = c if corner[1] == "l" else w - c - gw
        y0 = c if corner[0] == "t" else h - c - gh
        return Geometry(float(x0), float(y0), float(c))

    @staticmethod
    def from_state(mk: Any) -> "Geometry | None":
        """From STATE "mk" ({drawn, corner, cell, rect, grid}); None while the marker is off or the shape is unknown."""
        if not isinstance(mk, dict):
            return None
        r, c, g = mk.get("rect"), mk.get("cell"), mk.get("grid")
        if not (isinstance(r, (list, tuple)) and len(r) == 4 and all(isinstance(v, (int, float)) for v in r)):
            return None
        if not isinstance(c, (int, float)) or c <= 0 or (g is not None and list(g) != [ROWS, COLS]):
            return None
        return Geometry(float(r[0]), float(r[1]), float(c))


def draw(img: np.ndarray, frame: int, geom: Geometry, black: int = 0, white: int = 255) -> None:
    """Paint the marker of `frame` into a client-size gray (or BGR) image, as the oracle does (tests, synthetic
    episodes)."""
    g = grid(frame)
    c = geom.cell
    for gr in range(ROWS + 2):
        for gc in range(COLS + 2):
            x0, y0 = int(round(geom.x0 + gc * c)), int(round(geom.y0 + gr * c))
            x1, y1 = int(round(geom.x0 + (gc + 1) * c)), int(round(geom.y0 + (gr + 1) * c))
            img[y0:y1, x0:x1] = white if g[gr, gc] else black


@dataclass
class Decoded:
    value: int | None        # frame number modulo 65536; None unless status == "ok"
    status: str              # ok | absent | unclear | check
    contrast: float = 0.0
    shift: tuple[float, float] = (0.0, 0.0)   # thumbnail px from the expected position


_SUB = np.array([0.3, 0.5, 0.7])


def _sample(img: np.ndarray, geom: Geometry, sx: float, sy: float, shifts: np.ndarray) -> np.ndarray:
    """(len(shifts), ROWS + 2, COLS + 2) cell means: 3 x 3 bilinear samples over each cell's inner 40 %."""
    gr, gc = np.meshgrid(np.arange(ROWS + 2), np.arange(COLS + 2), indexing="ij")
    fy, fx = np.meshgrid(_SUB, _SUB, indexing="ij")
    X = geom.x0 + (gc[..., None, None] + fx) * geom.cell                 # client px (ROWS+2, COLS+2, 3, 3)
    Y = geom.y0 + (gr[..., None, None] + fy) * geom.cell
    u = X[None] * sx - 0.5 + shifts[:, 0, None, None, None, None]       # thumbnail px, pixel centres at integers
    v = Y[None] * sy - 0.5 + shifts[:, 1, None, None, None, None]
    shape = u.shape
    flat = (-1, 9)   # remap maps stay well below its 32767 px per row
    out = cv2.remap(img.astype(np.float32), u.reshape(flat).astype(np.float32), v.reshape(flat).astype(np.float32),
                    cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return out.reshape(shape).mean(axis=(-1, -2))


def _levels(cells: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per shift: black level, white level, and the worst margin of the always-black / always-white cells
    (as a share of the contrast; > 0: every one on its side of the middle)."""
    blk = np.median(cells[:, BLACK], axis=1)
    wht = cells[:, WHITE].mean(axis=1)
    con = np.maximum(wht - blk, 1e-6)
    mid = (wht + blk) / 2
    worst = np.minimum((mid[:, None] - cells[:, BLACK]).min(axis=1), (cells[:, WHITE] - mid[:, None]).min(axis=1))
    return blk, wht, worst / con


def decode(img: np.ndarray, geom: Geometry, scale: tuple[float, float], search: float = SEARCH) -> Decoded:
    """Decode the marker from a gray thumbnail (or a full-size gray image: scale (1, 1)); scale = thumbnail px per
    client px (FrameInfo w / src_w, h / src_h)."""
    sx, sy = scale
    steps = np.arange(-search, search + 1e-9, 0.5)
    shifts = np.stack(np.meshgrid(steps, steps, indexing="ij"), -1).reshape(-1, 2)
    shifts = shifts[np.argsort(np.hypot(shifts[:, 0], shifts[:, 1]), kind="stable")]   # ties: nearest first
    cells = _sample(img, geom, sx, sy, shifts)
    blk, wht, worst = _levels(cells)
    b = int(np.argmax(worst))
    con = float(wht[b] - blk[b])
    sh = (float(shifts[b, 0]), float(shifts[b, 1]))
    if con < MIN_CONTRAST or worst[b] < CLARITY:
        return Decoded(None, "absent", con, sh)
    mid = (wht[b] + blk[b]) / 2
    data = cells[b][DATA].reshape(ROWS, COLS - 2)          # row-major: j = (gc - 2) + (gr - 1) * (COLS - 2)
    if (np.abs(data - mid) < CLARITY * con).any():
        return Decoded(None, "unclear", con, sh)
    bj = (data > mid).astype(np.int64).reshape(-1)
    value = int((bj[:DATA_BITS] << np.arange(DATA_BITS)).sum())
    check = int((bj[DATA_BITS:] << np.arange(CHECK_BITS)).sum())
    if check != crc4(value):
        return Decoded(None, "check", con, sh)
    return Decoded(value, "ok", con, sh)


def unwrap(value: int, ref: int) -> int:
    """The frame number with value == frame % MODULUS nearest `ref`."""
    return ref + ((value - ref + MODULUS // 2) % MODULUS) - MODULUS // 2


# ---- the episode's truth -------------------------------------------------------------------------------------------

DECODE_STATUS = ("ok", "absent", "unclear", "check", "no_geometry")


@dataclass
class Truth:
    """Per capture (video order): the decoded frame modulo 65536 (-1 if none) and why not; per STATE row: frame, end
    of frame, whether the marker was drawn in that frame."""
    seq: np.ndarray          # (N,) capture callback counter
    t_arrival: np.ndarray    # (N,) ns
    t_frame: np.ndarray      # (N,) ns (0 without SystemRelativeTime)
    value: np.ndarray        # (N,) decoded frame % MODULUS, -1 if not decoded
    status: np.ndarray       # (N,) index into DECODE_STATUS
    f: np.ndarray            # (R,) STATE frames, ascending
    t_eof: np.ndarray        # (R,) ns
    drawn: np.ndarray        # (R,) the marker was drawn in that frame (STATE mk.drawn)


def _state_rows(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    rr = RecordingReader(path)
    freq = rr.hello.get("qpc_freq") or (rr.meta.get("qpc") or {}).get("freq")
    if not freq:
        raise ValueError(f"no qpc_freq in {path / 'meta.json'}")
    rows: dict[int, tuple] = {}
    for s in rr.states(keys=("q", "mk")):
        f, q = s.get("f"), s.get("q")
        if isinstance(f, int) and isinstance(q, int) and f not in rows:
            mk = s.get("mk")
            rows[f] = (q * 1_000_000_000 // freq, isinstance(mk, dict) and mk.get("drawn") is True,
                       Geometry.from_state(mk))
    fs = sorted(rows)
    return (np.asarray(fs, np.int64), np.asarray([rows[f][0] for f in fs], np.int64),
            np.asarray([rows[f][1] for f in fs], bool), [rows[f][2] for f in fs])


def read_truth(path: str | Path, lag_ns: int = 30_000_000) -> Truth:
    """Decode every capture of an episode. The geometry comes from the STATE row that ended lag_ns before the
    capture (any frame near it: the marker only moves when the window is resized), or the nearest row with one."""
    path = Path(path)
    vr = VideoReader(path)
    if not vr.exists():
        raise FileNotFoundError(f"no video in {path}")
    f, t_eof, drawn, geoms = _state_rows(path)
    have = np.flatnonzero([g is not None for g in geoms])
    # Per STATE row, the nearest row with a geometry (before or after).
    nearest = have[np.clip(np.searchsorted(have, np.arange(len(f))), 0, len(have) - 1)] if len(have) else None
    if nearest is not None:
        before = have[np.clip(np.searchsorted(have, np.arange(len(f)), side="right") - 1, 0, len(have) - 1)]
        nearest = np.where(np.abs(before - np.arange(len(f))) <= np.abs(nearest - np.arange(len(f))), before, nearest)
    seq, ta, tf, val, st = [], [], [], [], []
    for info, img in vr.frames():
        t = info.frame_ns or info.arrival_ns
        geom = None
        if nearest is not None:
            r = int(np.clip(np.searchsorted(t_eof, t - lag_ns, side="right") - 1, 0, len(f) - 1))
            geom = geoms[nearest[r]]
        if geom is None:
            d = Decoded(None, "no_geometry")
        else:
            d = decode(img, geom, (info.w / info.src_w, info.h / info.src_h))
        seq.append(info.seq)
        ta.append(info.arrival_ns)
        tf.append(info.frame_ns)
        val.append(-1 if d.value is None else d.value)
        st.append(DECODE_STATUS.index(d.status))
    return Truth(np.asarray(seq, np.int64), np.asarray(ta, np.int64), np.asarray(tf, np.int64),
                 np.asarray(val, np.int64), np.asarray(st, np.int64), f, t_eof, drawn)


# ---- exact report --------------------------------------------------------------------------------------------------

@dataclass
class ExactClock:
    clock: str
    D_ms: float | None = None
    D_interval_ms: list | None = None       # every D in it labels the agreeing captures right
    D_agree: list | None = None             # [agreeing, decoded] captures
    counted: int = 0                        # labelled, next frame has a STATE
    decoded: int = 0                        # counted with a decoded marker
    missing: int = 0                        # counted, marker drawn around the label but not decoded: count against
    zero: int = 0                           # decoded at offset 0
    share: float | None = None              # zero / (decoded + missing): the M1 gate
    hist: dict = field(default_factory=dict)          # offset (decoded frame - label) -> captures
    missing_by: dict = field(default_factory=dict)    # decode status of the missing
    excluded: dict = field(default_factory=dict)      # no_label, state_gap, marker_off
    label_steps: dict = field(default_factory=dict)   # label(i) - label(i - 1) -> count (consecutive seq)
    lag_ms: dict | None = None               # capture time - end of the frame it shows
    first_nonzero: list = field(default_factory=list)  # [capture, seq, label frame, k]
    ok: bool = False
    verdict: str = "FAIL"
    reason: str = ""


@dataclass
class ExactReport:
    path: str = ""
    captures: int = 0
    seq_gaps: int = 0                       # captures the video recorder dropped
    states: int = 0
    marker_frames: int = 0                  # STATE frames with the marker drawn
    decode: dict = field(default_factory=dict)          # decode status -> captures
    shown_steps: dict = field(default_factory=dict)     # decoded frame(i) - decoded frame(i - 1) -> count
    duplicates: int = 0                     # consecutive captures showing the same frame
    skips: int = 0                          # frames between consecutive captures that neither shows
    backwards: int = 0                      # a capture showing an older frame than the one before
    never_captured: int = 0                 # frames in the decoded range that no capture shows (STATE frames only)
    threshold: float = THRESHOLD
    min_captures: int = 0
    primary: ExactClock | None = None
    alt: ExactClock | None = None
    monitor: dict | None = None             # score_monitor
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
        pct = (lambda x: f"{x * 100:.3f} %" if x is not None else "n/a")
        lines = [f"captures {self.captures} ({self.seq_gaps} dropped by the video recorder), STATE {self.states}, "
                 f"marker drawn in {self.marker_frames} frames; decode {self.decode}",
                 f"shown frame steps between consecutive captures {self.shown_steps}: duplicates {self.duplicates}, "
                 f"skipped frames {self.skips}, backwards {self.backwards}; frames never captured {self.never_captured}"]
        for c in (self.primary, self.alt):
            if c is None:
                continue
            tag = "gate" if c is self.primary else "cross-check"
            lines.append(f"[{c.clock} clock, {tag}] D {c.D_ms and round(c.D_ms, 3)} ms, interval {c.D_interval_ms} "
                         f"agreed by {c.D_agree}; lag {c.lag_ms}")
            lines.append(f"  counted {c.counted}: decoded {c.decoded} + missing {c.missing} {c.missing_by}; offset 0 "
                         f"{c.zero} = {pct(c.share)} -> {c.verdict}{' (' + c.reason + ')' if c.reason else ''}")
            lines.append(f"  offsets {c.hist}; label steps {c.label_steps}; excluded {c.excluded}")
            if c.first_nonzero:
                lines.append(f"  first non-zero (capture, seq, label frame, k): {c.first_nonzero}")
        if self.monitor:
            m = self.monitor
            lines.append(f"monitor vs truth: verdict {m['verdict']} (truth {m['truth_verdict']}), D {m['D_ms']} ms "
                         f"(truth {m['truth_D_ms']}); judged at 0: {m['judged_zero']} (false aligned "
                         f"{m['false_aligned']}, rate {m['false_aligned_rate']}); judged off: {m['judged_off']} (false "
                         f"misaligned {m['false_misaligned']}, rate {m['false_misaligned_rate']}; wrong offset "
                         f"{m['wrong_offset']})")
            lines.append(f"  truly off {m['truly_off']}: flagged {m['off_flagged']}, judged at 0 {m['false_aligned']}, "
                         f"not seen {m['off_unseen']}; unjudged by truth {m['unjudged']}; left out by truth "
                         f"{m['excluded']}")
        lines.extend(f"note: {n}" for n in self.notes)
        pr = self.primary
        lines.append(f"{'PASS' if self.ok else pr.verdict if pr else 'FAIL'}: {pct(pr.share if pr else None)} of the "
                     f"counted captures show their label's frame on the {pr.clock if pr else '?'} clock (threshold "
                     f"{self.threshold * 100:.1f} %; >= {self.min_captures} counted)")
        return "\n".join(lines)


def _hist(x: np.ndarray) -> dict:
    v, c = np.unique(x, return_counts=True)
    return {int(a): int(b) for a, b in zip(v, c)}


def _p(x: np.ndarray, q: float) -> float:
    return round(float(np.percentile(x, q)), 3)


def truth_frames(tr: Truth, t_cap: np.ndarray, lag_ns: int = 30_000_000) -> np.ndarray:
    """Full decoded frame per capture (-1 where none): unwrapped near the STATE frame that ended lag_ns before it."""
    out = np.full(len(tr.value), -1, np.int64)
    ok = tr.value >= 0
    if not ok.any() or not len(tr.f):
        return out
    r = np.clip(np.searchsorted(tr.t_eof, t_cap - lag_ns, side="right") - 1, 0, len(tr.f) - 1)
    ref = tr.f[r]
    half = MODULUS // 2
    out[ok] = ref[ok] + ((tr.value[ok] - ref[ok] + half) % MODULUS) - half
    return out


def exact_clock(tr: Truth, clock: str, *, D: int | None = None, max_offset: int = align.Params.max_offset,
                threshold: float = THRESHOLD, min_captures: int = 1000) -> tuple[ExactClock, dict]:
    """The exact report of one capture clock. Returns (result, per-capture arrays: label row, k, counted, missing,
    frame shown)."""
    res = ExactClock(clock)
    t_cap = tr.t_arrival if clock == "arrival" else tr.t_frame
    N, R = len(t_cap), len(tr.f)
    arrays = {"label": np.full(N, -1, np.int64), "k": np.zeros(N, np.int64), "counted": np.zeros(N, bool),
              "missing": np.zeros(N, bool), "shown": np.full(N, -1, np.int64)}
    if N == 0 or R == 0 or (clock == "frame" and (t_cap == 0).any()):
        res.reason = "no captures" if N == 0 else "no STATE frames" if R == 0 else "captures without a frame clock"
        return res, arrays
    g = truth_frames(tr, t_cap)
    arrays["shown"] = g
    row_of = np.full(int(tr.f[-1] - tr.f[0]) + 1, -1, np.int64)
    row_of[tr.f - tr.f[0]] = np.arange(R)
    inside = (g >= tr.f[0]) & (g <= tr.f[-1])
    grow = np.where(inside, row_of[np.clip(g - tr.f[0], 0, len(row_of) - 1)], -1)
    if D is None:
        sel = np.flatnonzero(grow >= 0)
        sw = align.agree_interval(t_cap[sel], grow[sel], tr.t_eof)
        if sw.D is None:
            res.reason = "no decoded marker to calibrate on"
            return res, arrays
        D = sw.D
        if sw.lo is not None:
            res.D_interval_ms = [sw.lo / 1e6, sw.hi / 1e6]
        res.D_agree = [sw.agree, sw.used]
    res.D_ms = D / 1e6
    L = align.match(t_cap, tr.t_eof, D)
    Lc = np.clip(L, 0, R - 1)
    labelled = L >= 0
    nxt = np.where(labelled, tr.f[Lc] + 1 - tr.f[0], 0)
    gap = labelled & ~((nxt < len(row_of)) & (row_of[np.clip(nxt, 0, len(row_of) - 1)] >= 0))
    counted = labelled & ~gap
    decoded = counted & (g >= 0)
    # A missing marker counts against the share only where it was drawn in every frame the capture could show. A frame
    # whose STATE was dropped counts as drawn when the nearest STATEs before and after it were drawn: an undecodable
    # marker next to a dropped STATE must not leave the share.
    drawn_rel = np.zeros(len(row_of), bool)
    drawn_rel[tr.f - tr.f[0]] = tr.drawn
    known = row_of >= 0
    if not known.all():
        idx = np.arange(len(row_of))
        prev = np.maximum.accumulate(np.where(known, idx, -1))
        nxt_known = np.minimum.accumulate(np.where(known, idx, len(row_of))[::-1])[::-1]
        both = ~known & (prev >= 0) & (nxt_known < len(row_of))
        drawn_rel[both] = drawn_rel[prev[both]] & drawn_rel[np.clip(nxt_known[both], 0, len(row_of) - 1)]
    drawn = np.zeros(len(row_of) + 2 * max_offset + 2, bool)
    drawn[max_offset + 1:max_offset + 1 + len(row_of)] = drawn_rel
    near = np.ones(N, bool)
    for k in range(-max_offset, max_offset + 1):
        near &= drawn[np.clip(tr.f[Lc] - tr.f[0] + k + max_offset + 1, 0, len(drawn) - 1)]
    missing = counted & (g < 0) & near
    k = np.where(decoded, g - tr.f[Lc], 0)
    arrays.update(label=L, k=k, counted=counted, missing=missing)
    res.counted, res.decoded, res.missing = int(counted.sum()), int(decoded.sum()), int(missing.sum())
    res.zero = int((decoded & (k == 0)).sum())
    res.hist = _hist(k[decoded])
    res.missing_by = {DECODE_STATUS[s]: int(n) for s, n in _hist(tr.status[missing]).items()}
    res.excluded = {"no_label": int((~labelled).sum()), "state_gap": int(gap.sum()),
                    "marker_off": int((counted & (g < 0) & ~near).sum())}
    consec = np.r_[False, np.diff(tr.seq) == 1] & labelled & np.r_[False, labelled[:-1]]
    res.label_steps = _hist((tr.f[Lc] - np.r_[0, tr.f[Lc][:-1]])[consec])
    shown = np.flatnonzero(decoded & (grow >= 0))
    if len(shown):
        lag = (t_cap[shown] - tr.t_eof[grow[shown]]) / 1e6
        res.lag_ms = {"p1": _p(lag, 1), "p50": _p(lag, 50), "p99": _p(lag, 99), "min": round(float(lag.min()), 3),
                      "max": round(float(lag.max()), 3)}
    bad = np.flatnonzero(decoded & (k != 0))
    res.first_nonzero = [[int(i), int(tr.seq[i]), int(tr.f[Lc[i]]), int(k[i])] for i in bad[:10]]
    judged = res.decoded + res.missing
    res.share = res.zero / judged if judged else None
    marker_off = res.excluded["marker_off"]
    # The sample is what the share is computed over (decoded + missing), not every labelled capture: captures whose
    # marker was never drawn around their label are left out of the share, so they cannot count towards its size.
    if judged < min_captures:
        res.verdict = "INCONCLUSIVE"
        res.reason = f"only {judged} captures judged against the marker (< {min_captures}; {marker_off} without a marker)"
    elif marker_off > 0.10 * res.counted:
        res.verdict = "INCONCLUSIVE"
        res.reason = (f"the marker was off around {marker_off} of {res.counted} captures (> 10 %): it went off during the "
                      f"run, so the gate did not see the whole recording")
    elif res.share is not None and res.share >= threshold:
        res.verdict, res.ok = "PASS", True
        if marker_off > 0.01 * res.counted:
            res.reason = f"note: the marker was off around {marker_off} of {res.counted} captures; those are not judged"
    else:
        res.reason = f"{res.decoded - res.zero} decoded captures off their label, {res.missing} missing markers"
    return res, arrays


def exact(tr: Truth, clock: str = align.GATE_CLOCK, *, D_ms: float | None = None,
          threshold: float = THRESHOLD, min_captures: int = 1000) -> tuple[ExactReport, dict]:
    """The exact report: the gate clock and, when D is calibrated, the other clock as a cross-check."""
    rep = ExactReport(captures=len(tr.seq), states=len(tr.f), marker_frames=int(tr.drawn.sum()),
                      threshold=threshold, min_captures=min_captures)
    rep.seq_gaps = int(np.clip(np.diff(tr.seq) - 1, 0, None).sum()) if len(tr.seq) > 1 else 0
    rep.decode = {DECODE_STATUS[s]: n for s, n in _hist(tr.status).items()}
    D = None if D_ms is None else int(round(D_ms * 1e6))
    rep.primary, arrays = exact_clock(tr, clock, D=D, threshold=threshold, min_captures=min_captures)
    other = "arrival" if clock == "frame" else "frame"
    if D is None and not (other == "frame" and (tr.t_frame == 0).any()):
        rep.alt, _ = exact_clock(tr, other, threshold=threshold, min_captures=min_captures)
    g = arrays["shown"]
    both = np.flatnonzero(np.r_[False, (g[1:] >= 0) & (g[:-1] >= 0) & (np.diff(tr.seq) == 1)])
    d = g[both] - g[both - 1]
    rep.shown_steps = _hist(d)
    rep.duplicates = int((d == 0).sum())
    rep.skips = int(np.clip(d - 1, 0, None).sum())
    rep.backwards = int((d < 0).sum())
    seen = np.unique(g[g >= 0])
    if len(seen):
        span = tr.f[(tr.f >= seen[0]) & (tr.f <= seen[-1])]
        rep.never_captured = int(len(np.setdiff1d(span, seen)))
    if rep.marker_frames == 0:
        rep.notes.append("no STATE frame has the marker drawn: was frame.marker turned on (training profile)?")
    return rep, arrays


def score_monitor(off: align.Offsets, trk: align.OracleTrack, shown: np.ndarray, verdict: str = "",
                  truth: ExactClock | None = None) -> dict:
    """The correlation monitor's per-capture verdicts against the truth (`shown`: the frame each capture shows, -1
    where the marker was not decoded). The monitor claims capture i shows frame f[label] + k; the truth offset is
    shown - f[label] under the monitor's own D. Judged at 0 but truly off: false aligned; judged off but truly at 0:
    false misaligned; judged off by a wrong amount: wrong offset. Unjudged and left-out captures are split by the
    truth as well: how many truly misaligned captures the monitor flagged (judged off or unjudged), and how many it
    could not see (left out)."""
    L = off.label
    have = (shown >= 0) & (L >= 0)
    kt = np.where(have, shown - trk.f[np.clip(L, 0, None)], 0)
    ok = have & (off.status == align.OK)
    j0, joff = ok & (off.k == 0), ok & (off.k != 0)
    unj = have & np.isin(off.status, align.UNJUDGED)
    excl = have & ~ok & ~unj
    fa, fm = j0 & (kt != 0), joff & (kt == 0)
    wrong = joff & (kt != 0) & (kt != off.k)
    off_true = have & (kt != 0)

    def split(mask: np.ndarray) -> dict:
        return {align.STATUS[s]: {"aligned": int((mask & (off.status == s) & (kt == 0)).sum()),
                                  "off": int((mask & (off.status == s) & (kt != 0)).sum())}
                for s in np.unique(off.status[mask])}

    rate = (lambda a, b: round(a / b, 5) if b else None)
    return {"verdict": verdict, "truth_verdict": truth.verdict if truth else None, "D_ms": round(off.D / 1e6, 3),
            "truth_D_ms": round(truth.D_ms, 3) if truth and truth.D_ms is not None else None,
            "with_truth": int(have.sum()),
            "judged_zero": int(j0.sum()), "false_aligned": int(fa.sum()), "false_aligned_rate": rate(int(fa.sum()),
                                                                                                     int(j0.sum())),
            "judged_off": int(joff.sum()), "false_misaligned": int(fm.sum()),
            "false_misaligned_rate": rate(int(fm.sum()), int(joff.sum())), "wrong_offset": int(wrong.sum()),
            "truly_off": int(off_true.sum()), "off_flagged": int((off_true & (joff | unj)).sum()),
            "off_unseen": int((off_true & excl).sum()), "unjudged": split(unj), "excluded": split(excl)}


def exact_episode(path: str | Path, clock: str = align.GATE_CLOCK, *, D_ms: float | None = None,
                  threshold: float = THRESHOLD, min_captures: int = 1000) -> tuple[ExactReport, dict, Truth]:
    tr = read_truth(path)
    rep, arrays = exact(tr, clock, D_ms=D_ms, threshold=threshold, min_captures=min_captures)
    rep.path = str(path)
    return rep, arrays, tr


def monitor_against_truth(path: str | Path, rep: ExactReport, arrays: dict, p: align.Params = align.Params(),
                          clock: str = align.GATE_CLOCK, progress=None
                          ) -> tuple[align.AlignReport, align.Offsets | None, align.VideoMotion, align.OracleTrack]:
    """Run the monitor on the same episode and put its score into rep.monitor."""
    mrep, off, mot, trk = align.align_episode(path, p, clock, progress=progress)
    if off is not None:
        rep.monitor = score_monitor(off, trk, arrays["shown"], mrep.primary.verdict, rep.primary)
    return mrep, off, mot, trk


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.record.marker", description=__doc__.split("\n")[0])
    ap.add_argument("path", help="episode folder with state.* and video.* recorded with the frame marker on")
    ap.add_argument("--clock", choices=("frame", "arrival"), default=align.GATE_CLOCK)
    ap.add_argument("--D-ms", type=float, help="use this capture offset instead of calibrating it on the truth")
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--min-captures", type=int, default=1000)
    ap.add_argument("--monitor", action="store_true", help="also run the correlation monitor and score it")
    ap.add_argument("--json", action="store_true", help="also write marker.json into the episode folder")
    a = ap.parse_args(argv)
    rep, arrays, _ = exact_episode(a.path, a.clock, D_ms=a.D_ms, threshold=a.threshold, min_captures=a.min_captures)
    if a.monitor:
        mrep, *_ = monitor_against_truth(a.path, rep, arrays, clock=a.clock)
        print(mrep.format() + "\n")
    print(rep.format())
    if a.json:
        (Path(a.path) / "marker.json").write_text(json.dumps(rep.as_dict(), indent=1), encoding="utf-8")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
