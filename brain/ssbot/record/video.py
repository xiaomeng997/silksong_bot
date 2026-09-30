"""Gray thumbnail video of one game window for frame/label alignment (DESIGN §3.1.4 C4; analysed by ssbot.record.align).

Windows Graphics Capture (windows-capture) calls back on its own thread for every frame DWM composes for the window.
The callback stamps the arrival with time.perf_counter_ns() (QPC: the clock of STATE "q" * 1e9 / qpc_freq and of the
recorder's recv_ns), crops the client area (the capture includes the title bar: game_window.client_in_capture), converts
to 8-bit gray, downscales with INTER_AREA to `width` px and hands the thumbnail to a bounded queue: a slow disk costs
counted drops, never a stalled capture thread. A writer thread packs `chunk_frames` thumbnails into one independent zstd
frame per chunk, like the STATE stream (ssbot.record.formats). This is not training video (that is NVENC HEVC, DESIGN
§3.1.6): it is a cheap, lossless stream for image registration.

Files, in the episode folder the Recorder writes (VideoRecorder is its sibling and shares the folder):
    video.gray.zst       chunks; a decompressed chunk is a sequence of records, each FRAME_HEAD + h * w gray bytes
    video.index.jsonl    one line per chunk: off, clen, ulen, n, and per frame "seq", "t" (arrival ns), "ts" (frame ns)
    video.json           capture settings (hwnd, crops, width), QPC frequency, start/end, counts, drops, callback cost

FRAME_HEAD (little-endian): u32 seq | i64 arrival_ns | i64 frame_ns | u16 w | u16 h | u16 src_w | u16 src_h
    seq          callback counter; a gap means frames dropped on the full queue
    arrival_ns   time.perf_counter_ns() when the callback started
    frame_ns     Frame.timespan * 100: Direct3D11CaptureFrame.SystemRelativeTime (QPC in 100 ns units). P8 found it
                 7-10 ms after the arrival (it looks like the target present time); the aligner's gate clock, with
                 the arrival as a cross-check
    w, h         thumbnail size; src_w, src_h: the client crop it was made from (normally STATE cam.screen)

Cost at the default width 320 (1280x720 client): the callback ~0.4 ms p50 (cvtColor + resize), 57.6 KB per frame raw,
~1.5-2 MB/s on disk at 60 fps after zstd level 1 (~3 ms per 60-frame chunk on the writer thread): 4 instances are fine
for alignment runs of minutes. Lower `width` for long sessions.

    rec = Recorder(link, profile="PROBE", episode="align_0001").start()
    vid = VideoRecorder(rec.path, hwnd=instance_window(0)).start()
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

DATA = "video.gray.zst"
INDEX = "video.index.jsonl"
META = "video.json"
FRAME_HEAD = struct.Struct("<Iqq4H")
CHUNK_FRAMES = 60
DEFAULT_WIDTH = 320


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
    """Writes video.* into `path` from a WGC capture of `hwnd`, or from push() calls (tests, replays)."""

    def __init__(self, path: str | Path, hwnd: int | None = None, *, width: int = DEFAULT_WIDTH,
                 crop: tuple[int, int, int, int] | None = None, chunk_frames: int = CHUNK_FRAMES, level: int = 1,
                 queue_size: int = 240):
        self.path = Path(path)
        self.hwnd = hwnd
        self.width = width
        self.fixed_crop = crop  # (x, y, w, h) in the captured frame; None: the client area of hwnd, else the frame
        self.chunk_frames = chunk_frames
        self.level = level
        self.queue_size = queue_size

        self._q: queue.Queue = queue.Queue(maxsize=queue_size)
        self._accepting = False
        self._thread: threading.Thread | None = None
        self._control = None
        self._crops: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        self._data = None
        self._index = None
        self._cctx = formats.compressor(level)
        self._chunk: list[bytes] = []
        self._chunk_info: dict[str, list] = {"seq": [], "t": [], "ts": []}
        self._meta: dict = {}
        self.summary: dict | None = None

        # push() runs on the capture thread (or the caller's); the writer thread only touches the written_* counters.
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
        self._cost_ns = array("q")

    # ---- lifecycle -------------------------------------------------------------------------------------

    def start(self) -> "VideoRecorder":
        self.path.mkdir(parents=True, exist_ok=True)  # usually the Recorder's episode folder, already there
        if (self.path / DATA).exists():
            raise FileExistsError(f"{self.path / DATA} exists; one video per episode")
        self._data = (self.path / DATA).open("wb")
        self._index = (self.path / INDEX).open("w", encoding="utf-8", newline="\n")
        self._meta = {
            "format": 1, "status": "recording", "hwnd": self.hwnd, "width": self.width, "fixed_crop": self.fixed_crop,
            "chunk_frames": self.chunk_frames, "zstd_level": self.level, "queue_size": self.queue_size,
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
        Crops, converts and downscales here, because a WGC frame buffer does not outlive the callback."""
        if not self._accepting:
            return
        t0 = time.perf_counter_ns()
        seq = self.pushed
        self.pushed += 1
        try:
            h, w = image.shape[:2]
            x, y, cw, ch = self._crop_for(w, h)
            view = image[y:y + ch, x:x + cw]
            if view.ndim == 3:
                view = cv2.cvtColor(view, cv2.COLOR_BGRA2GRAY if view.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
            tw = min(self.width, cw)
            th = max(1, round(tw * ch / cw))
            small = view.copy() if (tw, th) == (cw, ch) else cv2.resize(view, (tw, th), interpolation=cv2.INTER_AREA)
        except Exception as e:
            self.failed += 1
            if self.error is None:
                self.error = repr(e)
                traceback.print_exc()
            return
        try:
            self._q.put_nowait((seq, int(arrival_ns), int(frame_ns), small, cw, ch))
        except queue.Full:
            self.dropped += 1
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
        costs = sorted(self._cost_ns)

        def pct(p: float) -> float | None:
            return costs[min(len(costs) - 1, round(p * (len(costs) - 1)))] / 1000 if costs else None

        meta = self._meta
        meta.update(status="closed", crops=[[list(k), list(v)] for k, v in self._crops.items()], pushed=self.pushed,
                    written=self.written, dropped=self.dropped, late=self.late, failed=self.failed,
                    max_queue=self.max_queue, chunks=self.chunks, bytes=self.bytes, raw_bytes=self.raw_bytes,
                    capture_closed=self.capture_closed, callback_us={"p50": pct(.5), "p99": pct(.99), "max": pct(1.0)},
                    error=self.error)
        meta["qpc"]["perf_ns_end"] = time.perf_counter_ns()
        meta["wall"]["end"] = datetime.now().isoformat(timespec="milliseconds")
        self._write_meta()
        self.summary = {k: meta[k] for k in ("pushed", "written", "dropped", "late", "failed", "max_queue", "chunks",
                                            "bytes", "raw_bytes", "callback_us", "error")}
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

    def _add(self, seq: int, arrival_ns: int, frame_ns: int, small: np.ndarray, src_w: int, src_h: int) -> None:
        h, w = small.shape
        self._chunk.append(FRAME_HEAD.pack(seq, arrival_ns, frame_ns, w, h, src_w, src_h) + small.tobytes())
        self._chunk_info["seq"].append(seq)
        self._chunk_info["t"].append(arrival_ns)
        self._chunk_info["ts"].append(frame_ns)
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
        self._chunk = []
        self._chunk_info = {"seq": [], "t": [], "ts": []}


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


def iter_frames(buf: bytes | memoryview) -> Iterator[tuple[FrameInfo, np.ndarray]]:
    """(header, gray thumbnail) for every record of a decompressed chunk; the array is a view into buf."""
    mv = memoryview(buf)
    pos, end = 0, len(mv)
    while pos < end:
        if pos + FRAME_HEAD.size > end:
            raise ValueError(f"truncated frame header at {pos}")
        info = FrameInfo(*FRAME_HEAD.unpack_from(mv, pos))
        pos += FRAME_HEAD.size
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
        self.rebuilt = False
        self._index = self._load_index()

    def exists(self) -> bool:
        return (self.path / DATA).is_file()

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
                heads = [h for h, _ in iter_frames(raw)]
                entries.append({"i": i, "off": off, "clen": clen, "ulen": len(raw), "n": len(heads),
                                "seq": [h.seq for h in heads], "t": [h.arrival_ns for h in heads],
                                "ts": [h.frame_ns for h in heads]})
        return entries

    def chunk(self, entry: dict) -> bytes:
        with (self.path / DATA).open("rb") as f:
            f.seek(entry["off"])
            return formats.decompress_chunk(f.read(entry["clen"]))

    def frames(self) -> Iterator[tuple[FrameInfo, np.ndarray]]:
        for e in self._index:
            yield from iter_frames(self.chunk(e))

    def times(self) -> dict[str, np.ndarray]:
        """Per frame, from the index alone: seq, arrival_ns ("t") and frame_ns ("ts") as int64 arrays."""
        return {k: np.fromiter((v for e in self._index for v in e[k]), np.int64) for k in ("seq", "t", "ts")}
