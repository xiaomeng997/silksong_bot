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

Files, in the episode folder the Recorder writes (VideoRecorder is its sibling and shares the folder):
    video.gray.zst       chunks; a decompressed chunk is a sequence of records, each FRAME_HEAD + h * w gray bytes
    video.index.jsonl    one line per chunk: off, clen, ulen, n, and per frame "seq", "t" (arrival ns), "ts" (frame ns),
                         "mk" (decoded frame modulo 65536, -1 if none) and "mks" (MARK_STATUS index: why not)
    video.json           capture settings (hwnd, crops, width), QPC frequency, start/end, counts, drops, callback cost;
                         "marker" (decoded in the capture path or not, captures per decode status, the share labelled
                         by the marker, decode + mask cost) and "mask" (corner, fill, rect per client size)

FRAME_HEAD (format 2, little-endian): u32 seq | i64 arrival_ns | i64 frame_ns | u16 w | u16 h | u16 src_w | u16 src_h
| i32 mk | u8 mks (format 1, FRAME_HEAD_V1, ends after src_h: no decode in the capture path, no mask)
    seq          callback counter; a gap means frames dropped on the full queue
    arrival_ns   time.perf_counter_ns() when the callback started
    frame_ns     Frame.timespan * 100: Direct3D11CaptureFrame.SystemRelativeTime (QPC in 100 ns units). P8 found it
                 7-10 ms after the arrival (it looks like the target present time); the timestamp labels' clock, with
                 the arrival as a cross-check
    w, h         thumbnail size; src_w, src_h: the client crop it was made from (normally STATE cam.screen)
    mk, mks      the marker read from the full-resolution crop: frame modulo 65536 (-1 unless mks is "ok"), status

Cost at the default width 320 (1280x720 client): the callback ~0.35 ms p50 (cvtColor + resize), of which reading
the marker and filling the mask take ~0.03 ms (1080p: ~0.06 of ~0.9 ms; a capture without a marker, which runs the
search, ~0.25 ms; tests/test_video.py measures them), 57.6 KB per frame raw, ~1.5-2 MB/s on disk at 60 fps after zstd
level 1 (~3 ms per 60-frame chunk on the writer thread): 4 instances are fine for alignment runs of minutes. Lower
`width` for long sessions.

    rec = Recorder(link, profile="PROBE", episode="align_0001").start()
    marker_on(link)                                  # ssbot.record.marker: training sessions carry the marker
    vid = VideoRecorder(rec.path, hwnd=instance_window(0), marker=True).start()
    ...
    vid.close(); rec.close()
"""
import json
import os
import queue
import struct
import threading
import time
import traceback
from array import array
from collections.abc import Iterator
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
FORMAT = 2
FRAME_HEAD = struct.Struct("<Iqq4HiB")
FRAME_HEAD_V1 = struct.Struct("<Iqq4H")
CHUNK_FRAMES = 60
DEFAULT_WIDTH = 320
# Per-capture marker status (FRAME_HEAD / index "mks"): ssbot.record.marker's decode statuses, and "off": not read in
# the capture path (marker=False, or a format-1 video).
MARK_STATUS = ("ok", "absent", "unclear", "check", "no_geometry", "off")
MARK_OK, MARK_OFF = MARK_STATUS.index("ok"), MARK_STATUS.index("off")


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
    stores the thumbnails unmasked, which only a capture without the marker may do (comparisons, legacy tests)."""

    def __init__(self, path: str | Path, hwnd: int | None = None, *, width: int = DEFAULT_WIDTH,
                 crop: tuple[int, int, int, int] | None = None, chunk_frames: int = CHUNK_FRAMES, level: int = 1,
                 queue_size: int = 240, marker: bool = False, mask: bool = True):
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
        self._decoder = None
        if marker:
            from ssbot.record.marker import FullResDecoder  # marker imports this module
            self._decoder = FullResDecoder()

        self._q: queue.Queue = queue.Queue(maxsize=queue_size)
        self._accepting = False
        self._thread: threading.Thread | None = None
        self._control = None
        self._crops: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        self._data = None
        self._index = None
        self._cctx = formats.compressor(level)
        self._chunk: list[bytes] = []
        self._chunk_info: dict[str, list] = {"seq": [], "t": [], "ts": [], "mk": [], "mks": []}
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
            "mask": {"corner": vmask.CORNER, "fill": vmask.FILL, "margin_cells": vmask.MARGIN_CELLS} if self.mask
            else None,
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
        Crops, converts, reads the marker, masks and downscales here, because a WGC frame buffer does not outlive
        the callback; the caller's image is never written to."""
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
            elif self.mask:
                view, own = view.copy(), True
            t1 = time.perf_counter_ns()
            mk, mks = -1, MARK_OFF
            if self._decoder is not None:
                d = self._decoder.decode(view)
                mk, mks = (d.value, MARK_OK) if d.value is not None else (-1, MARK_STATUS.index(d.status))
            if self.mask:
                vmask.apply(view)
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
            self._q.put_nowait((seq, int(arrival_ns), int(frame_ns), small, cw, ch, mk, mks))
        except queue.Full:
            self.dropped += 1
        self._mark_ns.append(t2 - t1)
        self._cost_ns.append(time.perf_counter_ns() - t0)

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
                if crop is not None:
                    print(f"[video] client area {crop} does not fit a {w}x{h} capture; keeping the whole frame")
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
        meta.update(status="closed", crops=[[list(k), list(v)] for k, v in self._crops.items()], pushed=self.pushed,
                    written=self.written, dropped=self.dropped, late=self.late, failed=self.failed,
                    max_queue=self.max_queue, chunks=self.chunks, bytes=self.bytes, raw_bytes=self.raw_bytes,
                    capture_closed=self.capture_closed, callback_us=pct(self._cost_ns), error=self.error)
        counts = {s: n for s, n in zip(MARK_STATUS, self.marks) if n}
        meta["marker"].update(counts=counts, labelled=self.marks[MARK_OK],
                              share=self.marks[MARK_OK] / self.written if self.written else None,
                              decode_mask_us=pct(self._mark_ns))
        if meta["mask"] is not None:
            meta["mask"]["rects"] = [[[w, h], list(vmask.mask_rect(w, h))] for _, _, w, h in self._crops.values()]
        meta["qpc"]["perf_ns_end"] = time.perf_counter_ns()
        meta["wall"]["end"] = datetime.now().isoformat(timespec="milliseconds")
        self._write_meta()
        self.summary = {k: meta[k] for k in ("pushed", "written", "dropped", "late", "failed", "max_queue", "chunks",
                                            "bytes", "raw_bytes", "callback_us", "error")}
        self.summary["marker"] = {k: meta["marker"][k] for k in ("decode", "counts", "labelled", "share",
                                                                 "decode_mask_us")}
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
             mk: int = -1, mks: int = MARK_OFF) -> None:
        h, w = small.shape
        self._chunk.append(FRAME_HEAD.pack(seq, arrival_ns, frame_ns, w, h, src_w, src_h, mk, mks) + small.tobytes())
        info = self._chunk_info
        info["seq"].append(seq)
        info["t"].append(arrival_ns)
        info["ts"].append(frame_ns)
        info["mk"].append(mk)
        info["mks"].append(mks)
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
        self._chunk = []
        self._chunk_info = {"seq": [], "t": [], "ts": [], "mk": [], "mks": []}


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
    mk: int = -1            # decoded frame modulo 65536 (format 2)
    mks: int = MARK_OFF     # MARK_STATUS index


def iter_frames(buf: bytes | memoryview, head: struct.Struct = FRAME_HEAD) -> Iterator[tuple[FrameInfo, np.ndarray]]:
    """(header, gray thumbnail) for every record of a decompressed chunk; the array is a view into buf. head:
    FRAME_HEAD_V1 for a format-1 video."""
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
        self.head = FRAME_HEAD_V1 if self.format == 1 else FRAME_HEAD
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
        """Per frame, from the index alone: seq, arrival_ns ("t"), frame_ns ("ts"), and the marker read in the
        capture path, "mk" and "mks" (format 1: -1 and "off"), as int64 arrays."""
        out = {k: np.fromiter((v for e in self._index for v in e[k]), np.int64) for k in ("seq", "t", "ts")}
        n = len(out["seq"])
        for k, none in (("mk", -1), ("mks", MARK_OFF)):
            have = all(k in e for e in self._index)
            out[k] = np.fromiter((v for e in self._index for v in e[k]), np.int64) if have and n \
                else np.full(n, none, np.int64)
        return out

    def labels(self) -> dict | None:
        """The session's label sources, from the index alone (RecordingReader.check, the reports): captures, how
        many carry a marker label (read in the capture path: exact) and how many fall back to their timestamp
        label, captures per decode status, the marker-labelled share. None without a video."""
        if not self.exists():
            return None
        mks = self.times()["mks"]
        n, ok = len(mks), int((mks == MARK_OK).sum())
        v, c = np.unique(mks, return_counts=True)
        return {"captures": n, "marker": ok, "timestamp": n - ok, "share": ok / n if n else None,
                "decoded_in_capture": self.marked, "decode": {MARK_STATUS[int(a)]: int(b) for a, b in zip(v, c)}}
