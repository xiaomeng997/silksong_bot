"""Thumbnail video recorder/reader (ssbot.record.video) with synthetic frames: crop + gray + INTER_AREA downscale,
per-frame timestamps, chunks and index, queue drops, index rebuild."""
import json
import threading
import time

import cv2
import numpy as np
import pytest

from ssbot.record import formats
from ssbot.record.video import DATA, FRAME_HEAD, INDEX, META, VideoReader, VideoRecorder


def frame(i: int, w: int = 402, h: int = 257) -> np.ndarray:
    """A BGRA 'window capture': 1 px border, 31 px title bar, 400x225 client with a pattern that changes per frame."""
    rng = np.random.default_rng(i)
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 3] = 255
    img[:31] = (200, 200, 200, 255)
    img[31:256, 1:401, :3] = rng.integers(0, 256, (225, 400, 3), dtype=np.uint8)
    return img


def expected(img: np.ndarray, crop=(1, 31, 400, 225), width: int = 160) -> np.ndarray:
    x, y, w, h = crop
    g = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGRA2GRAY)
    return cv2.resize(g, (width, round(width * h / w)), interpolation=cv2.INTER_AREA)


def test_roundtrip_crop_gray_downscale_and_times(tmp_path):
    vid = VideoRecorder(tmp_path, crop=(1, 31, 400, 225), width=160, chunk_frames=7, queue_size=1000).start()
    imgs = [frame(i) for i in range(20)]
    for i, img in enumerate(imgs):
        vid.push(img, 1_000_000_000 + i * 16_666_667, 1_008_000_000 + i * 16_666_667)
    s = vid.close()
    assert s["written"] == 20 and s["dropped"] == 0 and s["chunks"] == 3 and s["error"] is None
    meta = json.loads((tmp_path / META).read_text("utf-8"))
    assert meta["status"] == "closed" and meta["crops"] == [[[402, 257], [1, 31, 400, 225]]]
    assert meta["qpc"]["freq"] > 0 and meta["callback_us"]["p50"] > 0

    rd = VideoReader(tmp_path)
    assert len(rd) == 20 and not rd.rebuilt and [e["n"] for e in rd.index()] == [7, 7, 6]
    got = list(rd.frames())
    for i, (info, thumb) in enumerate(got):
        assert (info.seq, info.w, info.h, info.src_w, info.src_h) == (i, 160, 90, 400, 225)
        assert info.arrival_ns == 1_000_000_000 + i * 16_666_667 and info.frame_ns == info.arrival_ns + 8_000_000
        assert np.array_equal(thumb, expected(imgs[i]))
    times = rd.times()
    assert times["seq"].tolist() == list(range(20)) and times["t"][3] == 1_000_000_000 + 3 * 16_666_667
    # Each chunk is an independent zstd frame at its indexed offset holding n records.
    blob = (tmp_path / DATA).read_bytes()
    e = rd.index()[1]
    raw = formats.decompress_chunk(blob[e["off"]:e["off"] + e["clen"]])
    assert len(raw) == e["ulen"] == 7 * (FRAME_HEAD.size + 160 * 90)


def test_gray_and_bgr_input_and_small_frames(tmp_path):
    vid = VideoRecorder(tmp_path, width=320, queue_size=100).start()
    gray = np.arange(100 * 60, dtype=np.uint32).reshape(60, 100).astype(np.uint8)
    vid.push(gray, 1, 2)                                   # narrower than width: stored as is
    vid.push(np.dstack([gray] * 3), 3, 4)                  # BGR
    vid.close()
    (a, ta), (b, tb) = list(VideoReader(tmp_path).frames())
    assert (a.w, a.h) == (100, 60) and np.array_equal(ta, gray) and np.array_equal(tb, gray)


def test_crop_that_does_not_fit_keeps_the_whole_frame(tmp_path, capsys):
    vid = VideoRecorder(tmp_path, crop=(10, 10, 500, 500), width=64, queue_size=10).start()
    vid.push(frame(0), 1, 2)
    vid.close()
    info, _ = next(VideoReader(tmp_path).frames())
    assert (info.src_w, info.src_h) == (402, 257)
    assert "does not fit" in capsys.readouterr().out


def test_full_queue_drops_and_never_blocks(tmp_path):
    vid = VideoRecorder(tmp_path, crop=(1, 31, 400, 225), width=80, queue_size=4).start()
    gate = threading.Event()
    real = vid._add

    def slow(*a):
        gate.wait(10)
        real(*a)

    vid._add = slow
    t0 = time.perf_counter()
    for i in range(30):
        vid.push(frame(i), i, 0)
    assert time.perf_counter() - t0 < 1.0
    assert 30 - 5 <= vid.dropped <= 30 - 4
    gate.set()
    s = vid.close()
    assert s["written"] + s["dropped"] == 30
    seqs = VideoReader(tmp_path).times()["seq"]
    assert seqs[0] == 0 and len(seqs) == s["written"]  # the recorded seq values show where frames were dropped


def test_index_rebuilt_when_missing_or_torn(tmp_path):
    vid = VideoRecorder(tmp_path, crop=(1, 31, 400, 225), width=80, chunk_frames=5, queue_size=100).start()
    for i in range(23):
        vid.push(frame(i), 100 + i, 200 + i)
    vid.close()
    good = VideoReader(tmp_path).times()
    (tmp_path / INDEX).unlink()
    rd = VideoReader(tmp_path)
    assert rd.rebuilt and len(rd) == 23
    assert all(np.array_equal(rd.times()[k], good[k]) for k in good)
    data = tmp_path / DATA
    data.write_bytes(data.read_bytes()[:-50])  # killed mid-write: the torn last chunk is dropped
    assert [e["n"] for e in VideoReader(tmp_path).index()] == [5, 5, 5, 5]


def test_one_video_per_episode(tmp_path):
    VideoRecorder(tmp_path, width=80).start().close()
    with pytest.raises(FileExistsError):
        VideoRecorder(tmp_path, width=80).start()


def test_failed_capture_start_leaves_nothing_open(tmp_path, monkeypatch):
    def boom(self):
        raise OSError("no such window")

    monkeypatch.setattr(VideoRecorder, "_start_capture", boom)
    vid = VideoRecorder(tmp_path, hwnd=0x1234, width=80)
    with pytest.raises(OSError, match="no such window"):
        vid.start()
    assert not vid._thread.is_alive()
    meta = json.loads((tmp_path / META).read_text("utf-8"))
    assert meta["status"] == "failed" and "no such window" in meta["error"]
    (tmp_path / DATA).unlink()  # closed: Windows refuses to delete a file that is still open
    (tmp_path / INDEX).unlink()
