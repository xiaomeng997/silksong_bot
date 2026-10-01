"""Gray thumbnail video of one game window, the frame marker read and masked in the capture path (DESIGN §3.1.4 C4;
analysed by ssbot.record.marker and ssbot.record.align).

Windows Graphics Capture (windows-capture) calls back on its own thread for every frame DWM composes for the window.
The callback stamps the arrival with time.perf_counter_ns() (QPC: the clock of STATE "q" * 1e9 / qpc_freq and of the
recorder's recv_ns), crops the client area (the capture includes the title bar: game_window.client_in_capture) and
converts to 8-bit gray. Then, still at full resolution: with marker=True it reads the oracle's frame marker
(ssbot.record.marker.FullResDecoder: the frame number modulo 65536, or -1 and why not), and it fills the vision mask
(ssbot.vision.mask.apply, on by default: the rect the final run fills too), so that no marker pixel reaches a stored
image. Only then does it downscale with INTER_AREA to `width` px and hand the thumbnail to a bounded queue: a slow
disk costs counted drops, never a stalled capture thread. A writer thread packs `chunk_frames` thumbnails into one
independent zstd frame per chunk, like the STATE stream (ssbot.record.formats). This is a cheap, lossless stream for
labels and image registration; the training video (NVENC HEVC, DESIGN §3.1.6) is to take the same masked image.

The mask guard (states=, e.g. lambda: link.state): the mask is placed from the client crop's size alone, so it covers
the marker only where the oracle draws the marker the mask expects. Each capture therefore checks the oracle's own
report of where it drew it (STATE "mk" rect, in px of mk "screen", the render size) mapped into this capture
(marker_box: Unity scales a render that is not its window's size to fill the client, aspect kept; when the client
crop fell back to the whole frame, the client's place in it is unknown and the box is every place the marker could
be). Every rect a STATE reported within the last GUARD_NS counts (a capture shows a frame ~3 behind the newest STATE,
and the guard samples STATEs only once per capture), and any of them that is not inside the applied mask (another
cell, an older SsOracle's 12 px marker, a render scaled past the mask's share, a crop that fell back, no mask at all)
is filled too, and the capture is flagged "mm" (mask_mismatch: not training data); so is the session (video.json
"training_safe" false). A marker pixel is never stored silently. Without states the guard cannot run ("training_safe"
null): tests and replays only.

Files, in the episode folder the Recorder writes (VideoRecorder is its sibling and shares the folder):
    video.gray.zst       chunks; a decompressed chunk is a sequence of records, each FRAME_HEAD + h * w gray bytes
    video.index.jsonl    one line per chunk: off, clen, ulen, n, and per frame "seq", "t" (arrival ns), "ts" (frame ns),
                         "mk" (decoded frame modulo 65536, -1 if none), "mks" (MARK_STATUS index: why not) and "mm"
                         (1: mask_mismatch)
    video.json           capture settings (hwnd, crops, the frame sizes whose crop fell back, width), QPC frequency,
                         start/end, counts, drops, callback cost; "marker" (decoded in the capture path or not, captures
                         per decode status, the share labelled by the marker, decode + mask cost), "mask" (corner, fill,
                         share, rect per client size, guard on or not, the marker boxes found outside it),
                         "mask_mismatch" (captures flagged) and "training_safe" (masked, guarded, nothing flagged)

FRAME_HEAD (format 3, little-endian): u32 seq | i64 arrival_ns | i64 frame_ns | u16 w | u16 h | u16 src_w | u16 src_h
| i32 mk | u8 mks | u8 mm (format 2, FRAME_HEAD_V2, ends after mks: no guard; format 1, FRAME_HEAD_V1, after src_h: no
decode in the capture path, no mask; its marked recordings, e.g. the 2026-09-30 in-game m1_align run with 12 px cells,
hold the marker in their thumbnails and are validation data only)
    seq          callback counter; a gap means frames dropped on the full queue
    arrival_ns   time.perf_counter_ns() when the callback started
    frame_ns     Frame.timespan * 100: Direct3D11CaptureFrame.SystemRelativeTime (QPC in 100 ns units). P8 found it
                 7-10 ms after the arrival (it looks like the target present time); the timestamp labels' clock, with
                 the arrival as a cross-check
    w, h         thumbnail size; src_w, src_h: the client crop it was made from (normally STATE cam.screen)
    mk, mks      the marker read from the full-resolution crop: frame modulo 65536 (-1 unless mks is "ok"), status
    mm           1 when a marker rect the oracle reported lay outside the mask: filled as well, not training data

Cost at the default width 320 (1280x720 client): the callback ~0.35 ms p50 (cvtColor + resize), of which reading the
marker and filling the mask take ~0.03 ms (1080p: ~0.06 of ~0.9 ms; a capture without a marker, which runs the search,
~0.25 ms; the mask guard adds ~0.005-0.01 ms; tests/test_video.py measures them), 57.6 KB per frame raw, ~1.5-2 MB/s on
disk at 60 fps after zstd level 1 (~3 ms per 60-frame chunk on the writer thread): 4 instances are fine for alignment
runs of minutes. Lower `width` for long sessions.

    rec = Recorder(link, profile="PROBE", episode="align_0001").start()
    marker_on(link)                                  # ssbot.record.marker: training sessions carry the marker
    vid = VideoRecorder(rec.path, hwnd=instance_window(0), marker=True, states=lambda: link.state).start()
    ...
    vid.close(); rec.close()
"""
import json
import math
import os
import queue
import struct
import threading
import time
import traceback
from array import array
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2  # comes with windows-capture
import numpy as np

from ssbot.record import formats
from ssbot.vision import mask as vmask

DATA = "video.gray.zst"
INDEX = "video.index.jsonl"
META = "video.json"
FORMAT = 3
FRAME_HEAD = struct.Struct("<Iqq4HiBB")
FRAME_HEAD_V2 = struct.Struct("<Iqq4HiB")
FRAME_HEAD_V1 = struct.Struct("<Iqq4H")
HEADS = {1: FRAME_HEAD_V1, 2: FRAME_HEAD_V2, 3: FRAME_HEAD}
GUARD_NS = 500_000_000   # a marker rect a STATE reported is checked against the mask in the captures this long after
CHUNK_FRAMES = 60
DEFAULT_WIDTH = 320
# Per-capture marker status (FRAME_HEAD / index "mks"): ssbot.record.marker's decode statuses, and "off": not read in
# the capture path (marker=False, or a format-1 video). "implausible" is never stored: the analysis
# (marker.reject_implausible) gives it to a decoded marker that cannot be the capture's frame.
MARK_STATUS = ("ok", "absent", "unclear", "check", "no_geometry", "off", "implausible")
MARK_OK, MARK_OFF = MARK_STATUS.index("ok"), MARK_STATUS.index("off")


def marker_screen(s: dict) -> tuple[int, int] | None:
    """The render size STATE "mk" rect is in px of: mk "screen" (SsOracle since 2026-09-30), else cam "screen" (the
    same Screen size); None when neither is known."""
    for v in ((s.get("mk") or {}).get("screen"), (s.get("cam") or {}).get("screen")):
        if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) and x > 0 for x in v):
            return int(v[0]), int(v[1])
    return None


def marker_box(rect, screen: tuple[int, int] | None, client: tuple[int, int],
               frame: tuple[int, int] | None = None) -> tuple[int, int, int, int] | None:
    """Where the oracle's marker (STATE mk rect, px of the render `screen`; None: the client's size) lies in a client
    image of size `client`, rounded outward; None for an empty rect. A render of another size is scaled to fill the
    client, aspect kept and centred (Unity's fullscreen window), and the box then grows by the scale (rounded up, at
    least 1 px) for the interpolation's blur. frame (w, h): the client crop fell back to the whole capture frame, so
    the client's place in it is unknown: the box is the union of the marker's places over every position of an
    unscaled render inside the frame, or the whole frame if the render does not fit."""
    x0, y0, x1, y1 = (float(v) for v in rect)
    if not (x1 > x0 and y1 > y0):
        return None
    rw, rh = screen or client
    if frame is not None:
        fw, fh = frame
        if rw > fw or rh > fh:
            return 0, 0, fw, fh
        return math.floor(x0), math.floor(y0), math.ceil(x1) + fw - rw, math.ceil(y1) + fh - rh
    cw, ch = client
    if (rw, rh) == (cw, ch):
        return math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)
    k = min(cw / rw, ch / rh)
    ox, oy, b = (cw - rw * k) / 2, (ch - rh * k) / 2, max(1, math.ceil(k))
    return (math.floor(ox + x0 * k) - b, math.floor(oy + y0 * k) - b, math.ceil(ox + x1 * k) + b,
            math.ceil(oy + y1 * k) + b)


def inside(box: tuple[int, int, int, int], rect: tuple[int, int, int, int]) -> bool:
    return rect[0] <= box[0] and rect[1] <= box[1] and box[2] <= rect[2] and box[3] <= rect[3]


def _qpc_freq() -> int:
    from ssbot.record.recorder import qpc
    return qpc()[1]


def instance_window(instance: int) -> int:
    """HWND of the training instance whose oracle owns port(instance) (all copies share one window title, so
    game_window.find() cannot tell them apart). 0 if not found. Reads the TCP table; never connects."""
    import psutil

    from ssbot.ipc.framing import port
    from ssbot.tools.launcher import find_window
    me = os.getpid()
    for c in psutil.net_connections(kind="tcp4"):
        # The listening socket, or the game's end of an established brain connection.
        if c.laddr and c.laddr.port == port(instance) and c.pid and c.pid != me:
            hwnd = find_window(c.pid)
            if hwnd:
                return hwnd
    return 0


class VideoRecorder:
    """Writes video.* into `path` from a WGC capture of `hwnd`, or from push() calls (tests, replays). marker=True
    reads the frame marker from every capture (the session turned it on: ssbot.record.marker.marker_on); mask=False
    stores the thumbnails unmasked, which only a capture without the marker may do (comparisons, legacy tests).
    states: the newest STATE (lambda: link.state) for the mask guard; every live capture passes it."""

    def __init__(self, path: str | Path, hwnd: int | None = None, *, width: int = DEFAULT_WIDTH,
                 crop: tuple[int, int, int, int] | None = None, chunk_frames: int = CHUNK_FRAMES, level: int = 1,
                 queue_size: int = 240, marker: bool = False, mask: bool = True,
                 states: Callable[[], dict | None] | None = None):
        if marker and not mask:
            raise ValueError("a capture with the frame marker must be masked (ssbot.vision.mask)")
        self.path = Path(path)
        self.hwnd = hwnd
        self.width = width
        self.fixed_crop = crop  # (x, y, w, h) in the captured frame; None: the client area of hwnd, else the frame
        self.chunk_frames = chunk_frames
        self.level = level
        self.queue_size = queue_size
        self.marker = marker
        self.mask = mask
        self.states = states
        self._decoder = None
        if marker:
            from ssbot.record.marker import FullResDecoder  # marker imports this module
            self._decoder = FullResDecoder()

        self._q: queue.Queue = queue.Queue(maxsize=queue_size)
        self._accepting = False
        self._thread: threading.Thread | None = None
        self._control = None
        self._crops: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        self._fallback: set[tuple[int, int]] = set()   # frame sizes whose client crop fell back to the whole frame
        self._seen: dict[tuple, int] = {}              # (rect, screen) a STATE reported -> last arrival_ns
        self._boxes: dict[tuple, tuple] = {}           # (rect, screen, frame size, crop) -> (box, inside the mask)
        self.outside: set[tuple[int, int, int, int]] = set()   # marker boxes found outside the mask (first 50)
        self._data = None
        self._index = None
        self._cctx = formats.compressor(level)
        self._chunk: list[bytes] = []
        self._chunk_info: dict[str, list] = {"seq": [], "t": [], "ts": [], "mk": [], "mks": [], "mm": []}
        self._meta: dict = {}
        self.summary: dict | None = None

        # push() runs on the capture thread (or the caller's); the writer thread only touches the written_* counters
        # and the per-status counts of the written captures.
        self.pushed = 0
        self.dropped = 0
        self.max_queue = 0
        self.chunks = 0
        self.written = 0
        self.bytes = 0
        self.raw_bytes = 0
        self.late = 0
        self.failed = 0
        self.capture_closed = False
        self.error: str | None = None
        self.marks = [0] * len(MARK_STATUS)
        self.mismatch = 0
        self._cost_ns = array("q")
        self._mark_ns = array("q")

    # ---- lifecycle -------------------------------------------------------------------------------------

    def start(self) -> "VideoRecorder":
        self.path.mkdir(parents=True, exist_ok=True)  # usually the Recorder's episode folder, already there
        if (self.path / DATA).exists():
            raise FileExistsError(f"{self.path / DATA} exists; one video per episode")
        self._data = (self.path / DATA).open("wb")
        self._index = (self.path / INDEX).open("w", encoding="utf-8", newline="\n")
        self._meta = {
            "format": FORMAT, "status": "recording", "hwnd": self.hwnd, "width": self.width,
            "fixed_crop": self.fixed_crop, "chunk_frames": self.chunk_frames, "zstd_level": self.level,
            "queue_size": self.queue_size,
            "marker": {"decode": self.marker, "corner": vmask.CORNER if self.marker else None,
                       "status": list(MARK_STATUS)},
            "mask": {"corner": vmask.CORNER, "fill": vmask.FILL, "share": [str(vmask.SHARE_W), str(vmask.SHARE_H)],
                     "guard": self.states is not None} if self.mask else None,
            "qpc": {"freq": _qpc_freq(), "perf_ns_start": time.perf_counter_ns(), "perf_ns_end": None},
            "wall": {"start": datetime.now().isoformat(timespec="milliseconds"), "end": None},
        }
        self._write_meta()
        self._accepting = True
        self._thread = threading.Thread(target=self._write_loop, name="VideoRecorder.write", daemon=True)
        self._thread.start()
        if self.hwnd:
            try:
                self._start_capture()
            except BaseException as e:  # a bad or closed hwnd, WGC unavailable: no thread or open file left behind
                self.error = f"capture start: {e!r}"
                self.close()
                self._meta["status"] = "failed"
                self._write_meta()
                raise
        return self

    def _start_capture(self) -> None:
        from windows_capture import WindowsCapture

        from ssbot.tools.launcher import set_dpi_aware
        set_dpi_aware()  # client_in_capture must see physical pixels, as WGC does
        cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=self.hwnd)

        @cap.event
        def on_frame_arrived(frame, control):
            t = time.perf_counter_ns()
            if not self._accepting:
                control.stop()
                return
            # frame_buffer is a view of the mapped GPU copy, valid only inside this callback: push() copies out.
            self.push(frame.frame_buffer, t, frame.timespan * 100)

        @cap.event
        def on_closed():
            self.capture_closed = True

        self._control = cap.start_free_threaded()

    def __enter__(self) -> "VideoRecorder":
        return self.start() if self._thread is None else self

    def __exit__(self, *exc) -> None:
        self.close()

    def push(self, image: np.ndarray, arrival_ns: int, frame_ns: int = 0) -> None:
        """One captured frame: BGRA (h, w, 4), BGR (h, w, 3) or gray (h, w) uint8. Any thread; never blocks.
        Crops, converts, reads the marker, masks (and blanks a marker the guard finds outside the mask) and downscales
        here, because a WGC frame buffer does not outlive the callback; the caller's image is never written to."""
        if not self._accepting:
            return
        t0 = time.perf_counter_ns()
        seq = self.pushed
        self.pushed += 1
        try:
            h, w = image.shape[:2]
            x, y, cw, ch = self._crop_for(w, h)
            view = image[y:y + ch, x:x + cw]
            own = view.ndim == 3
            if own:
                view = cv2.cvtColor(view, cv2.COLOR_BGRA2GRAY if view.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
            elif self.mask or self.states is not None:
                view, own = view.copy(), True
            t1 = time.perf_counter_ns()
            mk, mks = -1, MARK_OFF
            if self._decoder is not None:
                d = self._decoder.decode(view)
                mk, mks = (d.value, MARK_OK) if d.value is not None else (-1, MARK_STATUS.index(d.status))
            if self.mask:
                vmask.apply(view)
            mm = self._guard(view, int(arrival_ns), (w, h), (x, y, cw, ch)) if self.states is not None else 0
            t2 = time.perf_counter_ns()
            tw = min(self.width, cw)
            th = max(1, round(tw * ch / cw))
            if (tw, th) == (cw, ch):
                small = view if own else view.copy()
            else:
                small = cv2.resize(view, (tw, th), interpolation=cv2.INTER_AREA)
        except Exception as e:
            self.failed += 1
            if self.error is None:
                self.error = repr(e)
                traceback.print_exc()
            return
        try:
            self._q.put_nowait((seq, int(arrival_ns), int(frame_ns), small, cw, ch, mk, mks, mm))
        except queue.Full:
            self.dropped += 1
        self._mark_ns.append(t2 - t1)
        self._cost_ns.append(time.perf_counter_ns() - t0)

    def _guard(self, view: np.ndarray, t: int, frame: tuple[int, int], crop: tuple[int, int, int, int]) -> int:
        """The mask guard (module docstring): fills every marker box a STATE reported within GUARD_NS that is not
        inside this capture's mask; returns mm (1: one was)."""
        st = self.states()
        mk = st.get("mk") if isinstance(st, dict) else None
        if isinstance(mk, dict):
            r = mk.get("rect")
            if isinstance(r, (list, tuple)) and len(r) == 4 and all(isinstance(v, (int, float)) for v in r):
                self._seen[(tuple(float(v) for v in r), marker_screen(st))] = t
        mm = 0
        for key, seen in list(self._seen.items()):
            if t - seen > GUARD_NS:
                del self._seen[key]
                continue
            got = self._boxes.get((key, frame, crop))
            if got is None:
                cw, ch = crop[2], crop[3]
                box = marker_box(key[0], key[1], (cw, ch), frame if frame in self._fallback else None)
                got = self._boxes[(key, frame, crop)] = (box, box is None or (
                    self.mask and inside(box, vmask.mask_rect(cw, ch))))
            box, ok = got
            if not ok:
                h, w = view.shape
                view[max(0, box[1]):min(h, box[3]), max(0, box[0]):min(w, box[2])] = vmask.FILL
                mm = 1
                if len(self.outside) < 50:
                    self.outside.add(box)
        return mm

    def _crop_for(self, w: int, h: int) -> tuple[int, int, int, int]:
        """The client area inside a w x h capture; looked up again whenever the capture size changes (resize)."""
        crop = self._crops.get((w, h))
        if crop is None:
            crop = self.fixed_crop
            if crop is None and self.hwnd:
                from ssbot.io.game_window import client_in_capture
                crop = client_in_capture(self.hwnd)
            if crop is None or crop[2] <= 0 or crop[3] <= 0 or crop[0] < 0 or crop[1] < 0 \
                    or crop[0] + crop[2] > w or crop[1] + crop[3] > h:
                if crop is not None:  # (no crop and no window: push() gets client images)
                    print(f"[video] client area {crop} does not fit a {w}x{h} capture; keeping the whole frame")
                    self._fallback.add((w, h))
                crop = (0, 0, w, h)
            self._crops[(w, h)] = tuple(int(v) for v in crop)
        return crop

    def close(self, timeout_s: float = 30.0) -> dict:
        """Stop the capture, flush the partial chunk, write video.json. Returns the summary (also in video.json)."""
        if self.summary is not None:
            return self.summary
        if self._thread is None:
            raise RuntimeError("video recorder was never started")
        self._accepting = False
        if self._control is not None:
            try:
                self._control.stop()
                deadline = time.monotonic() + 5.0
                while not self._control.is_finished() and time.monotonic() < deadline:
                    time.sleep(0.01)
            except Exception as e:  # the window may already be gone
                self.error = self.error or f"capture stop: {e!r}"
        try:
            self._q.put(None, timeout=timeout_s)
        except queue.Full:
            self.error = self.error or "writer did not drain the queue"
        self._thread.join(timeout_s)
        if self._thread.is_alive():
            self.error = self.error or "writer thread did not finish"

        def pct(xs: array) -> dict:
            s = sorted(xs)
            at = (lambda p: s[min(len(s) - 1, round(p * (len(s) - 1)))] / 1000 if s else None)
            return {"p50": at(.5), "p99": at(.99), "max": at(1.0)}

        meta = self._meta
        meta.update(status="closed", crops=[[list(k), list(v)] for k, v in self._crops.items()],
                    fallback=sorted(list(k) for k in self._fallback), pushed=self.pushed,
                    written=self.written, dropped=self.dropped, late=self.late, failed=self.failed,
                    max_queue=self.max_queue, chunks=self.chunks, bytes=self.bytes, raw_bytes=self.raw_bytes,
                    capture_closed=self.capture_closed, callback_us=pct(self._cost_ns), error=self.error)
        counts = {s: n for s, n in zip(MARK_STATUS, self.marks) if n}
        meta["marker"].update(counts=counts, labelled=self.marks[MARK_OK],
                              share=self.marks[MARK_OK] / self.written if self.written else None,
                              decode_mask_us=pct(self._mark_ns))
        if meta["mask"] is not None:
            meta["mask"]["rects"] = [[[w, h], list(vmask.mask_rect(w, h))] for _, _, w, h in self._crops.values()]
            meta["mask"]["outside"] = sorted(list(b) for b in self.outside)
        meta["mask_mismatch"] = self.mismatch
        meta["training_safe"] = training_safe(meta, self.mismatch)
        meta["qpc"]["perf_ns_end"] = time.perf_counter_ns()
        meta["wall"]["end"] = datetime.now().isoformat(timespec="milliseconds")
        self._write_meta()
        self.summary = {k: meta[k] for k in ("pushed", "written", "dropped", "late", "failed", "max_queue", "chunks",
                                            "bytes", "raw_bytes", "callback_us", "error")}
        self.summary["marker"] = {k: meta["marker"][k] for k in ("decode", "counts", "labelled", "share",
                                                                 "decode_mask_us")}
        self.summary.update(mask_mismatch=self.mismatch, training_safe=meta["training_safe"])
        self.summary["path"] = str(self.path)
        return self.summary

    def _write_meta(self) -> None:
        tmp = self.path / (META + ".tmp")
        tmp.write_text(formats.to_json(self._meta, indent=1), encoding="utf-8")
        os.replace(tmp, self.path / META)

    # ---- writer thread ---------------------------------------------------------------------------------

    def _write_loop(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            self.max_queue = max(self.max_queue, self._q.qsize() + 1)
            try:
                self._add(*item)
            except Exception as e:
                self.failed += 1
                if self.error is None:
                    self.error = repr(e)
                    traceback.print_exc()
        while True:  # frames pushed while close() was stopping the capture
            try:
                if self._q.get_nowait() is not None:
                    self.late += 1
            except queue.Empty:
                break
        try:
            self._flush()
        except Exception as e:
            self.error = self.error or repr(e)
        self._data.close()
        self._index.close()

    def _add(self, seq: int, arrival_ns: int, frame_ns: int, small: np.ndarray, src_w: int, src_h: int,
             mk: int = -1, mks: int = MARK_OFF, mm: int = 0) -> None:
        h, w = small.shape
        self._chunk.append(FRAME_HEAD.pack(seq, arrival_ns, frame_ns, w, h, src_w, src_h, mk, mks, mm)
                           + small.tobytes())
        info = self._chunk_info
        info["seq"].append(seq)
        info["t"].append(arrival_ns)
        info["ts"].append(frame_ns)
        info["mk"].append(mk)
        info["mks"].append(mks)
        info["mm"].append(mm)
        if len(self._chunk) >= self.chunk_frames:
            self._flush()

    def _flush(self) -> None:
        if not self._chunk:
            return
        raw = b"".join(self._chunk)
        comp = self._cctx.compress(raw)
        off = self._data.tell()
        self._data.write(comp)
        self._data.flush()
        entry = {"i": self.chunks, "off": off, "clen": len(comp), "ulen": len(raw), "n": len(self._chunk),
                 **self._chunk_info}
        self._index.write(json.dumps(entry) + "\n")
        self._index.flush()
        self.chunks += 1
        self.written += len(self._chunk)
        self.bytes += len(comp)
        self.raw_bytes += len(raw)
        for s in self._chunk_info["mks"]:
            self.marks[s] += 1
        self.mismatch += sum(self._chunk_info["mm"])
        self._chunk = []
        self._chunk_info = {"seq": [], "t": [], "ts": [], "mk": [], "mks": [], "mm": []}


def training_safe(meta: dict, mismatch: int) -> bool | None:
    """A video's images may be training data: masked in the capture path (format >= 2) and no capture flagged
    mask_mismatch; None when nothing flagged it but the guard did not run (no STATE to check against)."""
    m = meta.get("mask") if int(meta.get("format", FORMAT)) >= 2 else None
    if not m or mismatch:
        return False
    return True if m.get("guard") else None


# ---- reader --------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class FrameInfo:
    seq: int
    arrival_ns: int
    frame_ns: int
    w: int
    h: int
    src_w: int
    src_h: int
    mk: int = -1            # decoded frame modulo 65536 (format >= 2)
    mks: int = MARK_OFF     # MARK_STATUS index
    mm: int = 0             # 1: mask_mismatch (format 3)


def iter_frames(buf: bytes | memoryview, head: struct.Struct = FRAME_HEAD) -> Iterator[tuple[FrameInfo, np.ndarray]]:
    """(header, gray thumbnail) for every record of a decompressed chunk; the array is a view into buf. head:
    HEADS[format] (FRAME_HEAD_V1 / _V2 for a format-1 / format-2 video)."""
    mv = memoryview(buf)
    pos, end = 0, len(mv)
    while pos < end:
        if pos + head.size > end:
            raise ValueError(f"truncated frame header at {pos}")
        info = FrameInfo(*head.unpack_from(mv, pos))
        pos += head.size
        n = info.w * info.h
        if pos + n > end:
            raise ValueError(f"truncated frame at {pos}")
        yield info, np.frombuffer(mv, np.uint8, n, pos).reshape(info.h, info.w)
        pos += n


class VideoReader:
    """Sequential and per-chunk access to video.*; rebuilds the index from the data if it is missing or torn."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        meta = self.path / META
        self.meta: dict[str, Any] = json.loads(meta.read_text("utf-8")) if meta.is_file() else {}
        self.format = int(self.meta.get("format", FORMAT))
        self.head = HEADS[self.format]
        self.rebuilt = False
        self._index = self._load_index()

    def exists(self) -> bool:
        return (self.path / DATA).is_file()

    @property
    def marked(self) -> bool:
        """The marker was read in the capture path (VideoRecorder marker=True): index "mk" / "mks" hold it."""
        return self.format >= 2 and bool((self.meta.get("marker") or {}).get("decode"))

    def index(self) -> list[dict]:
        return self._index

    def __len__(self) -> int:
        return sum(e["n"] for e in self._index)

    def _load_index(self) -> list[dict]:
        data = self.path / DATA
        if not data.is_file():
            return []
        entries = []
        idx = self.path / INDEX
        if idx.is_file():
            for line in idx.read_text("utf-8").splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    break  # torn last line after a crash
        end = entries[-1]["off"] + entries[-1]["clen"] if entries else 0
        if end == data.stat().st_size:
            return entries
        self.rebuilt = True
        entries = []
        with data.open("rb") as f:  # streamed: a torn last chunk ends the scan
            for i, (off, clen, raw) in enumerate(formats.scan_frames(f)):
                heads = [h for h, _ in iter_frames(raw, self.head)]
                entry = {"i": i, "off": off, "clen": clen, "ulen": len(raw), "n": len(heads),
                         "seq": [h.seq for h in heads], "t": [h.arrival_ns for h in heads],
                         "ts": [h.frame_ns for h in heads]}
                if self.format >= 2:
                    entry.update(mk=[h.mk for h in heads], mks=[h.mks for h in heads])
                if self.format >= 3:
                    entry.update(mm=[h.mm for h in heads])
                entries.append(entry)
        return entries

    def chunk(self, entry: dict) -> bytes:
        with (self.path / DATA).open("rb") as f:
            f.seek(entry["off"])
            return formats.decompress_chunk(f.read(entry["clen"]))

    def frames(self) -> Iterator[tuple[FrameInfo, np.ndarray]]:
        for e in self._index:
            yield from iter_frames(self.chunk(e), self.head)

    def times(self) -> dict[str, np.ndarray]:
        """Per frame, from the index alone: seq, arrival_ns ("t"), frame_ns ("ts"), the marker read in the capture
        path, "mk" and "mks" (format 1: -1 and "off"), and "mm" (mask_mismatch; 0 before format 3), as int64 arrays."""
        out = {k: np.fromiter((v for e in self._index for v in e[k]), np.int64) for k in ("seq", "t", "ts")}
        n = len(out["seq"])
        for k, none in (("mk", -1), ("mks", MARK_OFF), ("mm", 0)):
            have = all(k in e for e in self._index)
            out[k] = np.fromiter((v for e in self._index for v in e[k]), np.int64) if have and n \
                else np.full(n, none, np.int64)
        return out

    @property
    def masked(self) -> bool:
        """The capture path filled the vision mask before storing (format >= 2, VideoRecorder mask=True)."""
        return self.format >= 2 and bool(self.meta.get("mask"))

    def labels(self) -> dict | None:
        """The session's label sources, from the index alone (RecordingReader.check, the reports): captures, how
        many carry a marker label (read in the capture path: exact) and how many fall back to their timestamp
        label, captures per decode status, the marker-labelled share; whether the thumbnails were masked, how many
        captures the guard flagged mask_mismatch, and training_safe (video.training_safe). None without a video."""
        if not self.exists():
            return None
        tm = self.times()
        mks = tm["mks"]
        n, ok = len(mks), int((mks == MARK_OK).sum())
        v, c = np.unique(mks, return_counts=True)
        mm = int(tm["mm"].sum())
        return {"captures": n, "marker": ok, "timestamp": n - ok, "share": ok / n if n else None,
                "decoded_in_capture": self.marked, "decode": {MARK_STATUS[int(a)]: int(b) for a, b in zip(v, c)},
                "masked": self.masked, "mask_mismatch": mm, "training_safe": training_safe(self.meta, mm)}
