"""Episode recorder and reader for the oracle stream (DESIGN §3.10; layout in ssbot.record.formats).

The recorder subscribes to OracleLink.subscribe_raw. The callback runs on the link's reader thread, so it only
timestamps the frame and hands it to a bounded queue (put_nowait): a slow disk costs counted drops, never a stalled
reader, which would make the oracle drop STATE frames instead (DESIGN §2.5 recorder: drop rather than slow `rt`).
A background thread peeks the few STATE fields it needs (f, drop, q, ev), appends the untouched wire frame to the
current chunk and compresses every CHUNK_FRAMES frames into one independent zstd frame plus an index line.

    rec = Recorder(link, out_dir="runs", profile="TRAIN", episode="bellbeast_0001").start()
    ...
    summary = rec.close()
    report = RecordingReader(rec.path).check(deep=True)   # M1 metric: >= 99.9 % frame delivery over 60 min

CLI:  python -m ssbot.record.recorder record --seconds 60 [--video] [--no-marker] | check <dir> [--deep] | info <dir>
      (--video adds the instance window's thumbnail stream of ssbot.record.video; a training recording turns the
      oracle's frame marker on first, which the video's capture path reads as each capture's exact label and masks:
      ssbot.record.marker; --no-marker, or an oracle that refuses it, leaves timestamp labels only)
"""
import argparse
import ctypes
import hashlib
import json
import os
import platform
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import tomllib
import traceback
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ssbot.record import formats
from ssbot.record.formats import STREAMS, data_name, index_name

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "runs"
DELIVERY_THRESHOLD = 0.999


# ---- environment for meta.json --------------------------------------------------------------------------

def find_repo_root(start: Path | None = None) -> Path | None:
    """The directory holding versions.lock, searched upwards from this package (editable install) or cwd."""
    for base in (start, Path(__file__).resolve().parent, Path.cwd()):
        if base is None:
            continue
        for p in (base, *base.parents):
            if (p / "versions.lock").is_file():
                return p
    return None


def versions_lock_info(root: Path | None) -> dict | None:
    if root is None or not (root / "versions.lock").is_file():
        return None
    data = (root / "versions.lock").read_bytes()
    info: dict[str, Any] = {"path": str(root / "versions.lock"), "sha256": hashlib.sha256(data).hexdigest(),
                            "text": data.decode("utf-8")}
    try:
        game = tomllib.loads(info["text"]).get("game", {})
        info["game"] = {k: game.get(k) for k in ("version", "buildid", "manifest", "tree_sha256", "file_count")}
        info["files"] = game.get("files", {})
    except tomllib.TOMLDecodeError as e:
        info["parse_error"] = str(e)
    return info


def git_info(root: Path | None) -> dict | None:
    if root is None:
        return None

    def run(*args: str) -> str | None:
        try:
            r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    sha = run("rev-parse", "HEAD")
    status = run("status", "--porcelain", "--untracked-files=no")
    return {"sha": sha, "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": None if status is None else bool(status)}


def qpc() -> tuple[int, int]:
    """(QueryPerformanceCounter ticks, frequency): the clock of the oracle's "q" field."""
    if sys.platform == "win32":
        c, f = ctypes.c_int64(), ctypes.c_int64()
        ctypes.windll.kernel32.QueryPerformanceCounter(ctypes.byref(c))
        ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(f))
        return c.value, f.value
    return time.perf_counter_ns(), 1_000_000_000


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dll_hashes(game_dir: Path | None, lock: dict | None) -> dict | None:
    """Hashes of the pinned game files (versions.lock [game.files]) and every plugin DLL of the copy the oracle runs
    in, so a recording names exactly which binaries produced it (DESIGN §3.10 meta: build and DLL hashes)."""
    if game_dir is None or not Path(game_dir).is_dir():
        return None
    game_dir = Path(game_dir)
    names = list((lock or {}).get("files", {}))
    plugins = game_dir / "BepInEx" / "plugins"
    if plugins.is_dir():
        names += [p.relative_to(game_dir).as_posix() for p in sorted(plugins.rglob("*.dll"))]
    out = {}
    for n in names:
        p = game_dir / n
        if not p.is_file() and n.endswith("steam_api64.dll"):
            p = p.with_name(p.name + ".disabled")  # training copy (D15)
        out[n] = file_sha256(p) if p.is_file() else None
    return out


def _atomic_write_json(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(formats.to_json(obj, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ---- per-chunk index statistics ------------------------------------------------------------------------

class StateTracker:
    """Frame-continuity bookkeeping shared by the recorder, index rebuild and the deep check: per chunk the frame
    range, the gaps in "f" (pairs [a, b] meaning frames a+1 .. b-1 never arrived; also across chunk borders),
    non-increasing frames, the oracle's cumulative "drop" counter at both ends, and the STATEs with the frame marker
    on ("mk": their images are training data only through the vision mask; ssbot.record.marker)."""

    def __init__(self) -> None:
        self.last_f: int | None = None
        self.reset()

    def reset(self) -> None:
        self.n = 0
        self.f0 = self.f1 = None
        self.gaps: list[list[int]] = []
        self.nonmono = 0
        self.nof = 0
        self.drop0 = self.drop1 = None
        self.q0 = self.q1 = None
        self.seq0 = self.seq1 = None
        self.recv0 = self.recv1 = None
        self.mk = 0

    def add(self, f: Any, drop: Any, q: Any, seq: int, recv_ns: int, mk: Any = None) -> None:
        self.n += 1
        if mk is not None:
            self.mk += 1
        if self.seq0 is None:
            self.seq0, self.recv0 = seq, recv_ns
        self.seq1, self.recv1 = seq, recv_ns
        if isinstance(drop, int):
            if self.drop0 is None:
                self.drop0 = drop
            self.drop1 = drop
        if isinstance(q, int):
            if self.q0 is None:
                self.q0 = q
            self.q1 = q
        if not isinstance(f, int):
            self.nof += 1
            return
        if self.f0 is None:
            self.f0 = f
        self.f1 = f if self.f1 is None else max(self.f1, f)
        if self.last_f is not None:
            if f > self.last_f + 1:
                self.gaps.append([self.last_f, f])
            elif f <= self.last_f:
                self.nonmono += 1
        if self.last_f is None or f > self.last_f:
            self.last_f = f

    def info(self) -> dict:
        return {"n": self.n, "f0": self.f0, "f1": self.f1, "gaps": self.gaps, "nonmono": self.nonmono,
                "nof": self.nof, "drop0": self.drop0, "drop1": self.drop1, "q0": self.q0, "q1": self.q1,
                "seq0": self.seq0, "seq1": self.seq1, "recv0": self.recv0, "recv1": self.recv1, "mk": self.mk}


class _StreamWriter:
    """One <stream>.msgpack.zst + <stream>.index.jsonl pair; every write_chunk is one independent zstd frame."""

    def __init__(self, directory: Path, stream: str, level: int):
        self.data = (directory / data_name(stream)).open("wb")
        self.index = (directory / index_name(stream)).open("w", encoding="utf-8", newline="\n")
        self.cctx = formats.compressor(level)
        self.chunks = 0
        self.records = 0
        self.compressed = 0
        self.uncompressed = 0

    def write_chunk(self, records: list[bytes], info: dict) -> None:
        raw = b"".join(records)
        comp = self.cctx.compress(raw)
        off = self.data.tell()
        self.data.write(comp)
        self.data.flush()
        entry = {"i": self.chunks, "off": off, "clen": len(comp), "ulen": len(raw), **info}
        self.index.write(json.dumps(entry) + "\n")
        self.index.flush()
        self.chunks += 1
        self.records += len(records)
        self.compressed += len(comp)
        self.uncompressed += len(raw)

    def close(self) -> None:
        self.data.close()
        self.index.close()


# ---- recorder ------------------------------------------------------------------------------------------

class Recorder:
    """Writes runs/<YYYY-MM-DD>/<profile>/<episode>/ from an OracleLink (or from on_raw calls, for tests/replays)."""

    def __init__(self, link=None, out_dir: str | Path = DEFAULT_OUT, profile: str = "TRAIN",
                 episode: str | None = None, *, config: dict | None = None, hello: dict | None = None,
                 chunk_frames: int = formats.CHUNK_FRAMES, level: int = 3, queue_size: int = 1800,
                 min_free_gb: float = 200.0, when: datetime | None = None, repo_root: Path | None = None,
                 game_dir: str | Path | None = None):
        self.link = link
        self.hello = dict(hello if hello is not None else (getattr(link, "hello", None) or {}))
        when = when or datetime.now()
        instance = self.hello.get("instance", 0)
        self.profile = profile
        self.episode = episode or f"{when:%H%M%S}_i{instance}"
        self.path = Path(out_dir) / f"{when:%Y-%m-%d}" / profile / self.episode
        self.config = config or {}
        self.chunk_frames = chunk_frames
        self.level = level
        self.queue_size = queue_size
        self.min_free_gb = min_free_gb
        self.repo_root = repo_root or find_repo_root()
        self.game_dir = game_dir

        self._q: queue.Queue = queue.Queue(maxsize=queue_size)
        self._accepting = False
        self._thread: threading.Thread | None = None
        self._streams: dict[str, _StreamWriter] = {}
        self._events = None
        self._chunk: list[bytes] = []
        self._tracker = StateTracker()
        self._meta: dict = {}
        self.summary: dict | None = None

        # Counters. dropped[*] are incremented only on the link reader thread, the rest only on the writer thread.
        self.dropped = {"state": 0, "terrain": 0, "progress": 0}
        self.dropped_disk = 0
        self.late = 0
        self.failed = 0
        self.states = 0
        self.events = 0
        self.max_queue = 0
        self.disk_low = False
        self.error: str | None = None

    # ---- lifecycle -------------------------------------------------------------------------------------

    def start(self) -> "Recorder":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(self.path.parent).free / 2**30
        if free_gb < self.min_free_gb:
            raise RuntimeError(f"only {free_gb:.0f} GB free under {self.path.parent} (< {self.min_free_gb} GB)")
        self.path.mkdir(exist_ok=False)
        for s in STREAMS.values():
            self._streams[s] = _StreamWriter(self.path, s, self.level)
        self._events = (self.path / "events.jsonl").open("w", encoding="utf-8", newline="\n")
        self._meta = self._initial_meta()
        _atomic_write_json(self.path / "meta.json", self._meta)
        self._accepting = True
        self._thread = threading.Thread(target=self._write_loop, name="Recorder.write", daemon=True)
        self._thread.start()
        if self.link is not None:
            self.link.subscribe_raw(self.on_raw)
        return self

    def __enter__(self) -> "Recorder":
        return self.start() if self._thread is None else self

    def __exit__(self, *exc) -> None:
        self.close()

    def on_raw(self, msg_type: int, raw: bytes) -> None:
        """OracleLink raw subscriber (reader thread). Never blocks."""
        if not self._accepting:
            return
        try:
            self._q.put_nowait((msg_type, raw, time.perf_counter_ns()))
        except queue.Full:
            name = STREAMS.get(msg_type)
            if name is not None:
                self.dropped[name] += 1

    def close(self, timeout_s: float = 120.0) -> dict:
        """Stop accepting, flush the partial chunk, finish meta.json. Returns the summary (also in meta.json)."""
        if self.summary is not None:
            return self.summary
        if self._thread is None:
            raise RuntimeError("recorder was never started")
        self._accepting = False
        try:
            self._q.put(None, timeout=timeout_s)
        except queue.Full:
            self.error = self.error or "writer did not drain the queue"
        self._thread.join(timeout_s)
        if self._thread.is_alive():
            self.error = self.error or "writer thread did not finish"

        c, _ = qpc()
        streams = {s: {"records": w.records, "chunks": w.chunks, "bytes": w.compressed, "raw_bytes": w.uncompressed}
                   for s, w in self._streams.items()}
        meta = self._meta
        meta["status"] = "closed"
        meta["qpc"].update(end=c, perf_ns_end=time.perf_counter_ns())
        meta["wall"]["end"] = datetime.now().isoformat(timespec="milliseconds")
        meta["streams"] = streams
        meta["events"] = self.events
        meta["drops"] = {"queue": dict(self.dropped), "disk": self.dropped_disk, "late": self.late,
                         "failed": self.failed, "max_queue": self.max_queue}
        meta["error"] = self.error
        try:
            report = RecordingReader(self.path, meta=meta).check()
            meta["continuity"] = report.as_dict()
        except Exception as e:  # a broken report must not lose the meta file
            meta["continuity"] = {"error": repr(e)}
        _atomic_write_json(self.path / "meta.json", meta)
        self.summary = {"path": str(self.path), "streams": streams, "events": self.events,
                        "drops": meta["drops"], "continuity": meta["continuity"], "error": self.error}
        return self.summary

    # ---- writer thread ---------------------------------------------------------------------------------

    def _write_loop(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            self.max_queue = max(self.max_queue, self._q.qsize() + 1)
            try:
                self._handle(*item)
            except Exception as e:
                # Keep draining: a writer that stops would turn into drops on the reader side anyway.
                self.failed += 1
                if self.error is None:
                    self.error = repr(e)
                    traceback.print_exc()
        while True:  # frames that raced with close()
            try:
                if self._q.get_nowait() is not None:
                    self.late += 1
            except queue.Empty:
                break
        try:
            self._flush_state()
        except Exception as e:
            self.error = self.error or repr(e)
        for w in self._streams.values():
            w.close()
        self._events.close()

    def _handle(self, msg_type: int, raw: bytes, recv_ns: int) -> None:
        stream = STREAMS.get(msg_type)
        if stream is None:
            return
        if self.disk_low:
            self.dropped_disk += 1
            return
        _, _, flags, seq, payload = formats.parse_frame(raw)
        record = formats.pack_record(recv_ns, raw)
        if stream == "state":
            fields = formats.peek(payload, ("f", "drop", "q", "mk", "ev"), flags, last=formats.STATE_LAST)
            f = fields.get("f")
            self._chunk.append(record)
            self.states += 1
            self._tracker.add(f, fields.get("drop"), fields.get("q"), seq, recv_ns, fields.get("mk"))
            for ev in fields.get("ev") or ():
                self._write_event(ev, f)
            if len(self._chunk) >= self.chunk_frames:
                self._flush_state()
        else:
            fields = formats.peek(payload, ("f", "frame", "scene"), flags)
            f = fields.get("f", fields.get("frame"))
            info = {"n": 1, "after_f": self._tracker.last_f, "f": f if isinstance(f, int) else None,
                    "scene": fields.get("scene") if isinstance(fields.get("scene"), str) else None,
                    "seq": seq, "recv": recv_ns}
            self._streams[stream].write_chunk([record], info)

    def _write_event(self, ev: Any, state_f: Any) -> None:
        if isinstance(ev, dict):
            line = {"frame": ev.get("f", state_f), "kind": ev.get("k"), "data": ev.get("d"),
                    "state_frame": state_f, "q": ev.get("q")}
        else:  # unexpected shape: keep it verbatim rather than lose it
            line = {"frame": state_f, "kind": None, "data": ev, "state_frame": state_f, "q": None}
        self._events.write(formats.to_json(line) + "\n")
        self.events += 1

    def _flush_state(self) -> None:
        if not self._chunk:
            return
        self._streams["state"].write_chunk(self._chunk, self._tracker.info())
        self._chunk = []
        self._tracker.reset()
        self._events.flush()
        free_gb = shutil.disk_usage(self.path).free / 2**30
        if free_gb < self.min_free_gb and not self.disk_low:
            self.disk_low = True
            self.error = self.error or f"stopped: {free_gb:.0f} GB free < {self.min_free_gb} GB"
            print(f"[recorder] {self.error}", file=sys.stderr)

    # ---- meta ------------------------------------------------------------------------------------------

    def _initial_meta(self) -> dict:
        c, f = qpc()
        lock = versions_lock_info(self.repo_root)
        return {
            "format": 1,
            "status": "recording",
            "profile": self.profile,
            "episode": self.episode,
            "instance": self.hello.get("instance"),
            "hello": self.hello,
            "config": self.config,
            "recorder": {"chunk_frames": self.chunk_frames, "zstd_level": self.level,
                         "queue_size": self.queue_size, "min_free_gb": self.min_free_gb},
            "versions_lock": lock,
            "git": git_info(self.repo_root),
            "dll_hashes": dll_hashes(Path(self.game_dir), lock) if self.game_dir else None,
            "host": {"name": socket.gethostname(), "python": platform.python_version(),
                     "platform": platform.platform()},
            "qpc": {"freq": f, "start": c, "end": None, "perf_ns_start": time.perf_counter_ns(), "perf_ns_end": None},
            "wall": {"start": datetime.now().isoformat(timespec="milliseconds"), "end": None},
        }


# ---- reader --------------------------------------------------------------------------------------------

def _pct(xs: list, p: float) -> Any:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, round(p * (len(s) - 1))))]


@dataclass
class ContinuityReport:
    """STATE frame delivery over a recording (M1 exit metric: >= 99.9 % over 60 min)."""
    states: int = 0                      # STATE records in the file
    f_first: int | None = None
    f_last: int | None = None
    expected: int = 0                    # f_last - f_first + 1
    missing: int = 0                     # frames inside the range that never arrived
    gaps: list = field(default_factory=list)   # [a, b]: frames a+1 .. b-1 missing
    nonmonotonic: int = 0                # frames not above their predecessor (duplicates / reordering)
    no_frame: int = 0                    # STATE payloads without an integer "f"
    oracle_drops: int | None = None      # delta of the oracle's own "drop" counter (its send queue overflowed)
    recorder_drops: int = 0              # recorder queue overflow + disk-low + write failures
    unexplained: int = 0                 # missing - oracle_drops - recorder_drops (e.g. failed STATE builds)
    delivery: float = 0.0                # (expected - missing) / (expected + recorder drops outside the range)
    threshold: float = DELIVERY_THRESHOLD
    duration_s: float | None = None
    fps: float | None = None
    deep: bool = False
    index_consistent: bool | None = None
    cost_us: dict | None = None          # oracle STATE build cost (C14: p50 <= 300, p99 <= 1000)
    latency_ms: dict | None = None       # oracle end-of-frame -> brain reader thread
    marked: int = 0                      # STATEs with the frame marker on (training data only through the mask)
    labels: dict | None = None           # the video's label sources and mask (VideoReader.labels); None without one

    @property
    def ok(self) -> bool:
        return self.expected > 0 and self.delivery >= self.threshold and self.nonmonotonic == 0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["gaps"] = self.gaps[:1000]
        d["gap_count"] = len(self.gaps)
        d["ok"] = self.ok
        return d

    def marker_verdict(self) -> str:
        """What the frames with the marker on are worth, from the video's mask (VideoReader.labels): training data
        only where the capture path masked them and the guard found no marker outside the mask; a video recorded
        before the mask (format 1, e.g. the 2026-09-30 in-game m1_align run with 12 px cells) is validation only."""
        lb = self.labels
        if lb is None:
            return ("no video in this episode; an image of these frames is training data only through the vision mask "
                    "(ssbot.vision.mask) and only where the marker lies inside it")
        if not lb.get("masked"):
            return ("the video is unmasked (format 1 or mask off): its thumbnails hold the marker, VALIDATION data "
                    "only, never training data")
        if lb.get("mask_mismatch"):
            return (f"NOT training data: {lb['mask_mismatch']} captures had the marker outside the vision mask "
                    f"(blanked too, mask_mismatch)")
        if lb.get("training_safe") is None:
            return "masked in the capture path but not guarded against STATE mk: training data only once checked"
        return "masked in the capture path, no marker outside the mask: training data"

    def format(self) -> str:
        lines = [
            f"STATE frames {self.states}  range {self.f_first}..{self.f_last} (expected {self.expected})",
            f"delivery {self.delivery * 100:.4f} %  (threshold {self.threshold * 100:.1f} %)  -> "
            f"{'PASS' if self.ok else 'FAIL'}",
            f"missing {self.missing} in {len(self.gaps)} gaps: oracle drops {self.oracle_drops}, recorder drops "
            f"{self.recorder_drops}, unexplained {self.unexplained}; non-monotonic {self.nonmonotonic}, "
            f"without f {self.no_frame}",
        ]
        if self.duration_s:
            fps = f", {self.fps:.2f} frames/s" if self.fps else ""
            lines.append(f"duration {self.duration_s:.1f} s{fps}")
        if self.marked or (self.labels or {}).get("mask_mismatch"):
            lines.append(f"frame marker on in {self.marked} STATE frames: {self.marker_verdict()}")
        if self.labels:
            lb = self.labels
            share = f"{lb['share'] * 100:.3f} %" if lb["share"] is not None else "n/a"
            lines.append(f"video {lb['captures']} captures: marker labels {lb['marker']} ({share}), timestamp labels "
                         f"{lb['timestamp']}{'' if lb['decoded_in_capture'] else ' (marker not read in the capture path)'};"
                         f" decode {lb['decode']}; masked {lb.get('masked')}, mask_mismatch "
                         f"{lb.get('mask_mismatch', 0)}")
        if self.gaps:
            shown = ", ".join(f"{a + 1}..{b - 1}" for a, b in self.gaps[:10])
            lines.append(f"first gaps: {shown}{' ...' if len(self.gaps) > 10 else ''}")
        if self.deep:
            lines.append(f"deep scan: index consistent {self.index_consistent}")
            if self.cost_us:
                lines.append("oracle build cost us: " + "  ".join(f"{k} {v}" for k, v in self.cost_us.items()))
            if self.latency_ms:
                lines.append("EOF->brain latency ms: " + "  ".join(f"{k} {v:.2f}" for k, v in self.latency_ms.items()))
        return "\n".join(lines)


class RecordingReader:
    """Random access to a recording: frame-range seeks read only the chunks that overlap the range."""

    def __init__(self, path: str | Path, meta: dict | None = None, cache_chunks: int = 4):
        self.path = Path(path)
        meta_path = self.path / "meta.json"
        if meta is None:
            meta = json.loads(meta_path.read_text("utf-8")) if meta_path.is_file() else {}
        self.meta = meta
        self.hello = meta.get("hello") or {}
        self.rebuilt: dict[str, bool] = {}
        self._index: dict[str, list[dict]] = {}
        for s in STREAMS.values():  # state first: a rebuilt terrain/progress index is anchored on it
            self._index[s] = self._load_index(s)
        self._cache: OrderedDict = OrderedDict()
        self._cache_size = cache_chunks

    # ---- index -----------------------------------------------------------------------------------------

    def index(self, stream: str = "state") -> list[dict]:
        return self._index[stream]

    def _load_index(self, stream: str) -> list[dict]:
        data = self.path / data_name(stream)
        if not data.is_file():
            return []
        entries = []
        idx = self.path / index_name(stream)
        if idx.is_file():
            for line in idx.read_text("utf-8").splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    break  # torn last line after a crash
        end = entries[-1]["off"] + entries[-1]["clen"] if entries else 0
        if end == data.stat().st_size:
            return entries
        self.rebuilt[stream] = True
        return self._rebuild_index(stream)

    def _rebuild_index(self, stream: str) -> list[dict]:
        """Scan the zstd frames when the index is missing or does not cover the data file (recorder killed)."""
        entries = []
        tracker = StateTracker()  # reset() per chunk keeps last_f, so gaps across chunk borders are found too
        with (self.path / data_name(stream)).open("rb") as f:  # streamed: a 60-min file is never held whole
            for i, (off, clen, raw) in enumerate(formats.scan_frames(f)):
                entry = {"i": i, "off": off, "clen": clen, "ulen": len(raw)}
                if stream == "state":
                    tracker.reset()
                    for recv_ns, frame in formats.iter_records(raw):
                        _, _, flags, seq, payload = formats.parse_frame(frame)
                        p = formats.peek(payload, ("f", "drop", "q", "mk"), flags, last=formats.STATE_LAST)
                        tracker.add(p.get("f"), p.get("drop"), p.get("q"), seq, recv_ns, p.get("mk"))
                    entry.update(tracker.info())
                else:
                    recs = list(formats.iter_records(raw))
                    recv_ns, frame = recs[0]
                    _, _, flags, seq, payload = formats.parse_frame(frame)
                    p = formats.peek(payload, ("f", "frame", "scene"), flags)
                    entry.update(n=len(recs), after_f=self._state_frame_at(recv_ns), f=p.get("f", p.get("frame")),
                                 scene=p.get("scene"), seq=seq, recv=recv_ns)
                entries.append(entry)
        return entries

    def _state_frame_at(self, recv_ns: int) -> int | None:
        """Approximate last STATE frame received before recv_ns (chunk resolution); for rebuilt indexes only."""
        best = None
        for c in self._index.get("state") or ():
            if c.get("recv0") is None or c["recv0"] > recv_ns:
                break
            best = c["f1"] if c["recv1"] <= recv_ns else c["f0"]
        return best

    # ---- raw access ------------------------------------------------------------------------------------

    def _chunk(self, stream: str, entry: dict) -> bytes:
        key = (stream, entry["i"])
        buf = self._cache.get(key)
        if buf is not None:
            self._cache.move_to_end(key)
            return buf
        with (self.path / data_name(stream)).open("rb") as f:
            f.seek(entry["off"])
            buf = formats.decompress_chunk(f.read(entry["clen"]))
        self._cache[key] = buf
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return buf

    def records(self, stream: str = "state", entries: list[dict] | None = None
                ) -> Iterator[tuple[dict, int, int, int, int, memoryview]]:
        """(index entry, recv_ns, msg_type, flags, seq, payload) for every record, in file order."""
        for e in self._index[stream] if entries is None else entries:
            for recv_ns, frame in formats.iter_records(self._chunk(stream, e)):
                msg_type, _, flags, seq, payload = formats.parse_frame(frame)
                yield e, recv_ns, msg_type, flags, seq, payload

    # ---- decoded access --------------------------------------------------------------------------------

    def chunks_for(self, f0: int | None = None, f1: int | None = None) -> list[dict]:
        out = []
        for e in self._index["state"]:
            if e.get("f0") is None:
                if f0 is None and f1 is None:
                    out.append(e)
                continue
            if f1 is not None and e["f0"] > f1:
                break
            if f0 is not None and e["f1"] < f0:
                continue
            out.append(e)
        return out

    def states(self, f0: int | None = None, f1: int | None = None, keys: tuple[str, ...] | None = None
               ) -> Iterator[dict]:
        """Decoded STATE dicts with f0 <= f <= f1 (inclusive; None = open). keys: decode only these top-level
        keys (plus "f"), which is much cheaper than full decoding when large sections are not needed."""
        want = None if keys is None else tuple({"f", *keys})
        for e in self.chunks_for(f0, f1):
            boundary = (f0 is not None and (e["f0"] is None or e["f0"] < f0)) or \
                       (f1 is not None and (e["f1"] is None or e["f1"] > f1))
            for _, _, _, flags, _, payload in self.records("state", [e]):
                if boundary:
                    f = formats.peek(payload, ("f",), flags).get("f")
                    if not isinstance(f, int) or (f0 is not None and f < f0) or (f1 is not None and f > f1):
                        continue
                yield formats.decode(payload, flags) if want is None else formats.peek(payload, want, flags)

    def state(self, f: int) -> dict | None:
        return next(self.states(f, f), None)

    def _messages(self, stream: str) -> Iterator[tuple[dict, Any]]:
        for e, _, _, flags, _, payload in self.records(stream):
            yield e, formats.decode(payload, flags)

    def terrain(self) -> Iterator[tuple[dict, Any]]:
        """(index entry with after_f/recv/seq, decoded TERRAIN payload)."""
        return self._messages("terrain")

    def progress(self) -> Iterator[tuple[dict, Any]]:
        return self._messages("progress")

    def events(self, kinds: set[str] | None = None) -> Iterator[dict]:
        p = self.path / "events.jsonl"
        if not p.is_file():
            return
        with p.open(encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if kinds is None or ev.get("kind") in kinds:
                    yield ev

    def sizes(self) -> dict[str, int]:
        return {p.name: p.stat().st_size for p in sorted(self.path.iterdir()) if p.is_file()}

    # ---- continuity ------------------------------------------------------------------------------------

    def _recorder_drops(self) -> int:
        d = self.meta.get("drops") or {}
        return int((d.get("queue") or {}).get("state", 0)) + int(d.get("disk", 0)) + int(d.get("failed", 0))

    def video_labels(self) -> dict | None:
        """Label sources of the episode's video (ssbot.record.video: marker labels read in the capture path, the rest
        timestamp labels), from its index alone; None without a video."""
        from ssbot.record.video import VideoReader
        return VideoReader(self.path).labels()

    def check(self, deep: bool = False, threshold: float = DELIVERY_THRESHOLD) -> ContinuityReport:
        """Frame continuity from the index (cheap), or with deep=True from the data itself, which also verifies
        every chunk decompresses, cross-checks the index, and adds build-cost and latency percentiles."""
        entries = self._index["state"]
        r = ContinuityReport(threshold=threshold, recorder_drops=self._recorder_drops(), deep=deep)
        r.labels = self.video_labels()
        if deep:
            tracker = StateTracker()
            fresh, costs, lat = [], [], []
            freq = self.hello.get("qpc_freq") or (self.meta.get("qpc") or {}).get("freq")
            for e in entries:
                tracker.reset()
                for recv_ns, frame in formats.iter_records(self._chunk("state", e)):
                    _, _, flags, seq, payload = formats.parse_frame(frame)
                    p = formats.peek(payload, ("f", "drop", "q", "cost_us", "mk"), flags, last=formats.STATE_LAST)
                    tracker.add(p.get("f"), p.get("drop"), p.get("q"), seq, recv_ns, p.get("mk"))
                    if isinstance(p.get("cost_us"), int):
                        costs.append(p["cost_us"])
                    if freq and isinstance(p.get("q"), int):
                        lat.append((recv_ns - p["q"] * 1e9 / freq) / 1e6)
                fresh.append(tracker.info())
            keys = ("n", "f0", "f1", "gaps", "nonmono", "drop0", "drop1")
            r.index_consistent = len(fresh) == len(entries) and all(
                all(a.get(k) == b.get(k) for k in keys) for a, b in zip(fresh, entries))
            entries = fresh
            if costs:
                r.cost_us = {"p50": _pct(costs, .5), "p99": _pct(costs, .99), "max": max(costs), "n": len(costs)}
            if lat:
                r.latency_ms = {"p50": _pct(lat, .5), "p99": _pct(lat, .99), "max": max(lat)}
        r.states = sum(e["n"] for e in entries)
        r.marked = sum(e.get("mk", 0) for e in entries)
        r.no_frame = sum(e.get("nof", 0) for e in entries)
        r.nonmonotonic = sum(e.get("nonmono", 0) for e in entries)
        framed = [e for e in entries if e.get("f0") is not None]
        if not framed:
            return r
        r.f_first = framed[0]["f0"]
        r.f_last = max(e["f1"] for e in framed)
        r.expected = r.f_last - r.f_first + 1
        r.gaps = [g for e in entries for g in e.get("gaps", ())]
        r.missing = sum(b - a - 1 for a, b in r.gaps)
        # Recorder drops inside the frame range already show up as gaps; any excess must lie outside the range
        # (typically the tail), so count it as lost too rather than let a truncated recording look complete.
        outside = max(0, r.recorder_drops - r.missing)
        r.delivery = (r.expected - r.missing) / (r.expected + outside)
        drops = [e for e in entries if e.get("drop0") is not None]
        if drops:
            r.oracle_drops = drops[-1]["drop1"] - drops[0]["drop0"]
        r.unexplained = max(0, r.missing - (r.oracle_drops or 0) - r.recorder_drops)
        qs = [e for e in entries if e.get("q0") is not None]
        freq = self.hello.get("qpc_freq") or (self.meta.get("qpc") or {}).get("freq")
        if qs and freq:
            r.duration_s = (qs[-1]["q1"] - qs[0]["q0"]) / freq
            r.fps = (r.expected - 1) / r.duration_s if r.duration_s > 0 else None
        return r


# ---- CLI -----------------------------------------------------------------------------------------------

def _cmd_record(a: argparse.Namespace) -> int:
    from ssbot.ipc.oracle_link import OracleError, OracleLink
    from ssbot.record.marker import marker_off, marker_on

    link = OracleLink(instance=a.instance)
    marked, unmarked_why = False, "--no-marker"
    if a.marker:  # every training recording carries the marker (DESIGN §3.1.4); a refusal leaves timestamp labels
        try:
            res = marker_on(link)
            marked, unmarked_why = True, None
            print(f"frame marker on ({res.get('corner')}, {res.get('cell')} px cells"
                  f"{', cell sent explicitly' if res.get('resent') else ''})")
        except (OracleError, TimeoutError) as e:
            unmarked_why = f"{type(e).__name__}: {e}"
            print(f"frame marker not on ({unmarked_why}): the video gets timestamp labels only")
    rec = Recorder(link, out_dir=a.out, profile=a.profile, episode=a.episode, game_dir=a.game_dir,
                   min_free_gb=a.min_free_gb,
                   config={"cli": sys.argv[1:], "marker": marked, "unmarked_why": unmarked_why}).start()
    vid = None
    try:  # a failing video start still closes the recording and the link
        if a.video:  # the thumbnail stream (labels, ssbot.record.align), in the same episode folder
            from ssbot.record.video import VideoRecorder, instance_window
            hwnd = instance_window(a.instance)
            if hwnd:
                vid = VideoRecorder(rec.path, hwnd=hwnd, width=a.video_width, marker=marked,
                                    states=lambda: link.state).start()
            else:
                print(f"no game window found for instance {a.instance}: recording without video")
        print(f"recording to {rec.path} for {a.seconds} s (Ctrl+C stops early)")
        end = time.monotonic() + a.seconds
        while time.monotonic() < end and not link.closed:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        vsum = vid.close() if vid is not None else None
        summary = rec.close()
        if marked:
            try:
                marker_off(link)
            except (OracleError, TimeoutError, OSError) as e:  # it goes off when the link closes anyway
                print(f"frame marker off failed ({e})")
        link.close()
    rep = RecordingReader(rec.path).check(deep=True)
    print(rep.format())
    print(f"drops {summary['drops']}")
    if vsum is not None:
        print(f"video: {vsum['written']} frames, {vsum['dropped']} dropped, callback us {vsum['callback_us']}, "
              f"marker labels {vsum['marker']['labelled']} (share {vsum['marker']['share']}, decode + mask us "
              f"{vsum['marker']['decode_mask_us']}), mask_mismatch {vsum['mask_mismatch']}, training_safe "
              f"{vsum['training_safe']}{', error ' + vsum['error'] if vsum['error'] else ''}")
    if summary["error"]:
        print(f"recorder error: {summary['error']}")
    # Exit 1 below the delivery threshold, on an index that disagrees with the data, or on a recorder error, so a
    # script can gate the M1 metric on this command as on `check`.
    return 0 if rep.ok and rep.index_consistent is not False and not summary["error"] else 1


def _cmd_check(a: argparse.Namespace) -> int:
    rd = RecordingReader(a.path)
    rep = rd.check(deep=a.deep, threshold=a.threshold)
    print(rep.format())
    if rd.rebuilt:
        print(f"index rebuilt from data for: {', '.join(rd.rebuilt)}")
    return 0 if rep.ok else 1


def _cmd_info(a: argparse.Namespace) -> int:
    rd = RecordingReader(a.path)
    m = rd.meta
    print(f"{rd.path}\n  profile {m.get('profile')}  episode {m.get('episode')}  instance {m.get('instance')}  "
          f"status {m.get('status')}")
    print(f"  plugin {rd.hello.get('plugin')}  game {rd.hello.get('game')}  git {(m.get('git') or {}).get('sha')}")
    print(f"  chunks: state {len(rd.index('state'))}, terrain {len(rd.index('terrain'))}, "
          f"progress {len(rd.index('progress'))}; drops {m.get('drops')}")
    for name, size in rd.sizes().items():
        print(f"  {name:24s} {size:>14,d} B")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.record.recorder", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="record from a running oracle (exit 1 below threshold or on an error)")
    r.add_argument("--instance", type=int, default=0)
    r.add_argument("--seconds", type=float, default=60.0)
    r.add_argument("--out", default=str(DEFAULT_OUT))
    r.add_argument("--profile", default="TRAIN")
    r.add_argument("--episode")
    r.add_argument("--game-dir", default=r"C:\ssbot\game\train")
    r.add_argument("--min-free-gb", type=float, default=200.0, help="refuse to start / stop below this free space")
    r.add_argument("--video", action="store_true", help="also record the gray thumbnail video (ssbot.record.video)")
    r.add_argument("--video-width", type=int, default=320)
    r.add_argument("--no-marker", dest="marker", action="store_false",
                   help="leave the oracle's frame marker off (default: on, as in every training recording)")
    r.set_defaults(fn=_cmd_record)
    c = sub.add_parser("check", help="frame continuity of a recording (exit 1 below threshold)")
    c.add_argument("path")
    c.add_argument("--deep", action="store_true", help="scan the data, not just the index")
    c.add_argument("--threshold", type=float, default=DELIVERY_THRESHOLD)
    c.set_defaults(fn=_cmd_check)
    i = sub.add_parser("info", help="meta and file sizes")
    i.add_argument("path")
    i.set_defaults(fn=_cmd_info)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
