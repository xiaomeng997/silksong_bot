"""Thumbnail video recorder/reader (ssbot.record.video) with synthetic frames: crop + gray + vision mask + INTER_AREA
downscale, per-frame timestamps, chunks and index, queue drops, index rebuild; the frame marker read from the
full-resolution capture and masked before the thumbnail (no marker pixel in any stored thumbnail), its index fields,
summary and cost; the mask guard against the oracle's report of where it drew the marker (a crop that fell back, a
render scaled to its window, an older plugin's cell, a stale STATE: blanked and flagged mask_mismatch); format-1 and
format-2 videos."""
import json
import threading
import time

import cv2
import numpy as np
import pytest

from ssbot.record import formats
from ssbot.record import marker as mk
from ssbot.record.video import (DATA, FRAME_HEAD, FRAME_HEAD_V1, FRAME_HEAD_V2, GUARD_NS, INDEX, MARK_OFF,
                                MARK_STATUS, META, VideoReader, VideoRecorder, marker_box)
from ssbot.vision import mask as vmask
from tests import align_synth as S


def frame(i: int, w: int = 402, h: int = 257) -> np.ndarray:
    """A BGRA 'window capture': 1 px border, 31 px title bar, 400x225 client with a pattern that changes per frame."""
    rng = np.random.default_rng(i)
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 3] = 255
    img[:31] = (200, 200, 200, 255)
    img[31:256, 1:401, :3] = rng.integers(0, 256, (225, 400, 3), dtype=np.uint8)
    return img


def expected(img: np.ndarray, crop=(1, 31, 400, 225), width: int = 160, mask: bool = True) -> np.ndarray:
    x, y, w, h = crop
    g = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGRA2GRAY)
    if mask:
        vmask.apply(g)
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
    assert meta["qpc"]["freq"] > 0 and meta["callback_us"]["p50"] > 0 and meta["format"] == 3
    # Masked by default, even without the marker: the rect the final run fills (225 px tall: the marker plus 2 cells).
    assert meta["mask"]["rects"] == [[[400, 225], [349, 0, 400, 21]]] and meta["marker"]["decode"] is False
    # No STATE to guard against: not known to be training data.
    assert meta["mask"]["guard"] is False and meta["mask_mismatch"] == 0 and meta["training_safe"] is None
    assert meta["marker"]["counts"] == {"off": 20} and meta["marker"]["share"] == 0.0

    rd = VideoReader(tmp_path)
    assert len(rd) == 20 and not rd.rebuilt and [e["n"] for e in rd.index()] == [7, 7, 6]
    got = list(rd.frames())
    for i, (info, thumb) in enumerate(got):
        assert (info.seq, info.w, info.h, info.src_w, info.src_h) == (i, 160, 90, 400, 225)
        assert info.arrival_ns == 1_000_000_000 + i * 16_666_667 and info.frame_ns == info.arrival_ns + 8_000_000
        assert np.array_equal(thumb, expected(imgs[i]))
    times = rd.times()
    assert times["seq"].tolist() == list(range(20)) and times["t"][3] == 1_000_000_000 + 3 * 16_666_667
    assert (times["mk"] == -1).all() and (times["mks"] == MARK_OFF).all() and not rd.marked
    assert (times["mm"] == 0).all() and rd.masked
    # Each chunk is an independent zstd frame at its indexed offset holding n records.
    blob = (tmp_path / DATA).read_bytes()
    e = rd.index()[1]
    raw = formats.decompress_chunk(blob[e["off"]:e["off"] + e["clen"]])
    assert len(raw) == e["ulen"] == 7 * (FRAME_HEAD.size + 160 * 90)
    unmasked = tmp_path / "unmasked"
    vid = VideoRecorder(unmasked, crop=(1, 31, 400, 225), width=160, queue_size=1000, mask=False).start()
    vid.push(imgs[0], 1, 2)
    assert vid.close()["error"] is None and json.loads((unmasked / META).read_text("utf-8"))["mask"] is None
    assert VideoReader(unmasked).labels()["training_safe"] is False and not VideoReader(unmasked).masked
    assert np.array_equal(next(VideoReader(unmasked).frames())[1], expected(imgs[0], mask=False))


def test_gray_and_bgr_input_and_small_frames(tmp_path):
    vid = VideoRecorder(tmp_path, width=320, queue_size=100).start()
    gray = np.arange(100 * 60, dtype=np.uint32).reshape(60, 100).astype(np.uint8)
    keep = gray.copy()
    vid.push(gray, 1, 2)                                   # narrower than width: stored as is (masked)
    vid.push(np.dstack([gray] * 3), 3, 4)                  # BGR
    vid.close()
    assert np.array_equal(gray, keep)                      # the caller's image is never written to
    (a, ta), (b, tb) = list(VideoReader(tmp_path).frames())
    assert (a.w, a.h) == (100, 60) and np.array_equal(ta, vmask.apply(gray.copy())) and np.array_equal(tb, ta)


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


# ---- the frame marker in the capture path -------------------------------------------------------------------------

def _client(w: int, h: int, seed: int = 5) -> np.ndarray:
    return S.texture(h + 20, w + 20, seed)[:h, :w].copy()


@pytest.mark.parametrize("client", [(1280, 720), (1920, 1080), (1366, 768)])
def test_marker_read_at_full_resolution_and_masked_before_the_thumbnail(tmp_path, client):
    """Captures with the marker (decoded, exact) and the same captures without it give identical thumbnails: no
    marker pixel reaches a stored image, and a marked training image is the final run's image. Captures whose marker
    is off or covered fall back (absent); the index, a rebuilt index and video.json say so."""
    w, h = client
    base = _client(w, h)
    g = mk.Geometry.place(client)
    marked = VideoRecorder(tmp_path / "marked", width=320, queue_size=1000, chunk_frames=16, marker=True).start()
    plain = VideoRecorder(tmp_path / "plain", width=320, queue_size=1000, chunk_frames=16).start()
    frames = [70000 + 7 * i for i in range(40)]
    off, covered = {5, 6, 30}, {12, 33}
    for i, f in enumerate(frames):
        img = base.copy()
        if i not in off:
            mk.draw(img, f, g)
        if i in covered:
            x0, y0, x1, y1 = (int(v) for v in g.rect)
            img[y0:y1, x0:x1] = 128
        bgra = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        marked.push(bgra, 1000 + i, 2000 + i)
        plain.push(cv2.cvtColor(base, cv2.COLOR_GRAY2BGRA), 1000 + i, 2000 + i)
    ms, ps = marked.close(), plain.close()
    assert ms["written"] == ps["written"] == 40 and ms["error"] is None
    rd = VideoReader(tmp_path / "marked")
    for (a, ta), (_, tb) in zip(rd.frames(), VideoReader(tmp_path / "plain").frames()):
        assert np.array_equal(ta, tb), a.seq
    times = rd.times()
    bad = off | covered
    assert rd.marked and times["mk"].tolist() == [-1 if i in bad else f % mk.MODULUS for i, f in enumerate(frames)]
    assert [MARK_STATUS[s] for s in times["mks"]] == ["absent" if i in bad else "ok" for i in range(40)]
    assert ms["marker"]["counts"] == {"ok": 35, "absent": 5} and ms["marker"]["labelled"] == 35
    assert ms["marker"]["share"] == 35 / 40 and ms["marker"]["decode_mask_us"]["p50"] > 0
    assert rd.labels() == {"captures": 40, "marker": 35, "timestamp": 5, "share": 35 / 40, "decoded_in_capture": True,
                           "decode": {"ok": 35, "absent": 5}, "masked": True, "mask_mismatch": 0,
                           "training_safe": None}
    meta = json.loads((tmp_path / "marked" / META).read_text("utf-8"))
    assert meta["mask"]["rects"] == [[[w, h], list(vmask.mask_rect(w, h))]] and meta["marker"]["corner"] == "tr"
    (tmp_path / "marked" / INDEX).unlink()                 # rebuilt from the frame headers: the same marks
    again = VideoReader(tmp_path / "marked")
    assert again.rebuilt and all(np.array_equal(again.times()[k], times[k]) for k in times)
    assert [i.mk for i, _ in again.frames()] == times["mk"].tolist()


def test_marker_found_with_the_client_crop_off_and_never_outside_the_mask(tmp_path):
    """A client crop up to 3 px off (both axes) still decodes, and the thumbnail is still the unmarked image's: the
    mask's margin covers every marker the decoder can find."""
    w, h = 1280, 720
    base = _client(w + 8, h + 8)
    g = mk.Geometry.place((w, h))
    for dx, dy in ((0, 0), (-1, 2), (3, -3), (-3, 3)):
        out = tmp_path / f"crop_{dx}_{dy}"
        marked = VideoRecorder(out / "m", crop=(4, 4, w, h), width=320, queue_size=100, marker=True).start()
        plain = VideoRecorder(out / "p", crop=(4, 4, w, h), width=320, queue_size=100).start()
        img = base.copy()
        sub = img[4 + dy:4 + dy + h, 4 + dx:4 + dx + w]    # the marker drawn (dx, dy) off the recorder's client
        mk.draw(sub, 123456, g)
        marked.push(img, 1, 2)
        plain.push(base, 1, 2)
        marked.close(), plain.close()
        (info, ta), = VideoReader(out / "m").frames()
        (_, tb), = VideoReader(out / "p").frames()
        assert info.mk == 123456 % mk.MODULUS and MARK_STATUS[info.mks] == "ok", (dx, dy)
        assert np.array_equal(ta, tb), (dx, dy)


# ---- the mask guard: where the oracle says it drew the marker, against the mask --------------------------------------

def _mk_state(rect, screen) -> dict:
    """The newest STATE as the guard reads it (link.state): mk rect in px of the render `screen`."""
    return {"f": 1, "mk": {"drawn": True, "corner": "tr", "cell": 3, "rect": [float(v) for v in rect],
                           "screen": list(screen)}}


def _pair(tmp_path, name, marked_imgs, plain_imgs, states, **kw):
    """The same captures with and without the marker, both guarded by the same STATEs: identical thumbnails mean no
    marker pixel was stored. Returns (marked reader, its video.json)."""
    out = []
    for tag, imgs in (("m", marked_imgs), ("p", plain_imgs)):
        st = [None]
        vid = VideoRecorder(tmp_path / name / tag, width=320, queue_size=1000, states=lambda: st[0], **kw).start()
        for i, img in enumerate(imgs):
            st[0] = states[i]
            vid.push(img, 1_000_000_000 + i * 16_666_667, 1_008_000_000 + i * 16_666_667)
        assert vid.close()["error"] is None
        out.append(VideoReader(tmp_path / name / tag))
    for (a, ta), (_, tb) in zip(out[0].frames(), out[1].frames()):
        assert np.array_equal(ta, tb), (name, a.seq)
    return out[0], json.loads((tmp_path / name / "m" / META).read_text("utf-8"))


def test_guard_passes_the_masks_marker(tmp_path):
    """The oracle draws the mask's marker: nothing to blank, the session is training data."""
    w, h = 1280, 720
    base = _client(w, h)
    img = base.copy()
    mk.draw(img, 4242, mk.Geometry.place((w, h)))
    rd, meta = _pair(tmp_path, "nominal", [img] * 3, [base] * 3, [_mk_state(vmask.marker_rect(w, h), (w, h))] * 3)
    assert meta["mask_mismatch"] == 0 and meta["training_safe"] is True and meta["mask"]["guard"] is True
    assert rd.labels()["training_safe"] is True and (rd.times()["mm"] == 0).all() and meta["mask"]["outside"] == []


def test_guard_blanks_a_marker_when_the_client_crop_falls_back(tmp_path):
    """The client area does not fit the capture (a resize, a minimised window, a DPI mismatch): the whole frame,
    title bar included, is kept, the client's place in it unknown. The marker the oracle drew (in px of its 400x225
    render) lies somewhere in the union of its possible places, which is blanked; the captures are flagged."""
    plain = frame(0)
    marked = plain.copy()
    client = marked[31:256, 1:401]
    g = mk.Geometry.place((400, 225))
    gray = np.zeros((225, 400), np.uint8)
    mk.draw(gray, 777, g)
    x0, y0, x1, y1 = (int(v) for v in g.rect)
    client[y0:y1, x0:x1, :3] = gray[y0:y1, x0:x1, None]
    st = [_mk_state(g.rect, (400, 225))] * 2
    rd, meta = _pair(tmp_path, "fallback", [marked] * 2, [plain] * 2, st, crop=(10, 10, 500, 500))
    box = marker_box(g.rect, (400, 225), (402, 257), (402, 257))
    assert box == (355, 3, 399, 47) and meta["fallback"] == [[402, 257]] and meta["mask"]["outside"] == [list(box)]
    assert rd.times()["mm"].tolist() == [1, 1] and meta["mask_mismatch"] == 2 and meta["training_safe"] is False
    assert rd.labels()["mask_mismatch"] == 2 and rd.labels()["training_safe"] is False


@pytest.mark.parametrize("render, client, outside", [((1280, 720), (2560, 1440), False),
                                                     ((1280, 720), (1920, 1080), False),
                                                     ((640, 360), (1920, 1080), True)])
def test_guard_maps_a_render_scaled_to_its_window(tmp_path, render, client, outside):
    """A render of another size than the window (Unity scales it to fill the client): the marker is no longer where
    the mask was placed from the client size. Within the supported sizes the mask's share still holds it (masked,
    training data, though it no longer decodes); a 360p render shown at 1080p puts it outside: blanked, flagged."""
    (rw, rh), (cw, ch) = render, client
    small = _client(rw, rh)
    marked_small = small.copy()
    g = mk.Geometry.place(render)
    mk.draw(marked_small, 31337, g)
    plain = cv2.resize(small, client, interpolation=cv2.INTER_LINEAR)
    marked = cv2.resize(marked_small, client, interpolation=cv2.INTER_LINEAR)
    rd, meta = _pair(tmp_path, f"{rw}_{cw}", [marked] * 2, [plain] * 2, [_mk_state(g.rect, render)] * 2, marker=True)
    assert meta["mask_mismatch"] == (2 if outside else 0) and meta["training_safe"] is (not outside)
    assert all(MARK_STATUS[s] != "ok" for s in rd.times()["mks"])     # a scaled marker never decodes


def test_guard_blanks_an_older_plugins_marker_also_from_a_stale_state(tmp_path):
    """An older SsOracle's 12 px marker at 720p lies far outside the mask: blanked and flagged. A capture shows a
    frame a few behind the newest STATE, so a rect reported up to GUARD_NS before still counts: the captures that
    still show the large marker after the STATEs moved on to the mask's marker are blanked too."""
    w, h = 1280, 720
    base = _client(w, h)
    big, small = mk.Geometry.place((w, h), cell=12), mk.Geometry.place((w, h))
    old = base.copy()
    mk.draw(old, 99, big)
    new = base.copy()
    mk.draw(new, 100, small)
    states = [_mk_state(big.rect, (w, h))] * 2 + [_mk_state(small.rect, (w, h))] * 3
    rd, meta = _pair(tmp_path, "old", [old, old, old, new, new], [base] * 5, states, marker=True)
    assert rd.times()["mm"].tolist() == [1] * 5 and meta["mask"]["outside"] == [[1100, 12, 1268, 60]]
    # Long after the last STATE that reported it, the old rect no longer counts.
    st = [_mk_state(big.rect, (w, h))]
    vid = VideoRecorder(tmp_path / "later", width=320, queue_size=100, marker=True, states=lambda: st[0]).start()
    vid.push(old, 1_000_000_000, 0)
    st[0] = _mk_state(small.rect, (w, h))
    vid.push(new, 1_000_000_000 + GUARD_NS + 1, 0)
    vid.close()
    assert VideoReader(tmp_path / "later").times()["mm"].tolist() == [1, 0]


def test_guard_without_a_mask_blanks_every_marker(tmp_path):
    """mask=False (comparisons) with a STATE that says the marker is drawn: nothing covers it, so it is blanked and
    flagged; an empty rect (on, not drawn yet) is ignored."""
    w, h = 640, 360
    base = _client(w, h)
    img = base.copy()
    mk.draw(img, 5, mk.Geometry.place((w, h)))
    states = [_mk_state(vmask.marker_rect(w, h), (w, h)), {"mk": {"drawn": False, "rect": [0.0, 0.0, 0.0, 0.0]}}]
    rd, meta = _pair(tmp_path, "nomask", [img, base], [base, base], states, mask=False)
    assert rd.times()["mm"].tolist() == [1, 1] and meta["training_safe"] is False and meta["mask"] is None


def test_marker_box_mapping():
    # Identity, scaled with a pixel of blur per unit of scale, letterboxed (4:3 render in a 16:9 client).
    assert marker_box([1235, 3, 1277, 15], (1280, 720), (1280, 720)) == (1235, 3, 1277, 15)
    assert marker_box([1235, 3, 1277, 15], None, (1280, 720)) == (1235, 3, 1277, 15)
    assert marker_box([1235, 3, 1277, 15], (1280, 720), (1920, 1080)) == (1850, 2, 1918, 25)
    assert marker_box([595, 3, 637, 15], (640, 480), (1920, 1080)) == (1578 - 3, 6 - 3, 1674 + 3, 34 + 3)
    assert marker_box([0, 0, 0, 0], (1280, 720), (1280, 720)) is None
    assert marker_box([1235, 3, 1277, 15], (1280, 720), (1280, 720), (1000, 600)) == (0, 0, 1000, 600)


def test_marker_needs_the_mask(tmp_path):
    with pytest.raises(ValueError, match="must be masked"):
        VideoRecorder(tmp_path, marker=True, mask=False)


def test_callback_cost_of_the_marker(tmp_path):
    """The capture callback at 1080p with the marker read, masked and guarded: decode + mask (+ the guard) stay a
    small part of the callback (cvtColor and the INTER_AREA resize dominate). Measured 2026-09-30 (13900K, a
    2-instance soak running), p50:
    decode + mask 0.056 ms of a 0.93 ms callback at 1080p, 0.027 of 0.34 ms at 720p (on caches the gray conversion
    has just flushed: 0.015-0.022 ms warm); a capture without a marker (the +-3 px search) ~0.25 ms at 1080p. The
    bounds leave room for a loaded machine."""
    w, h = 1920, 1080
    base = _client(w, h)
    g = mk.Geometry.place((w, h))
    caps = []
    for i in range(8):
        img = base.copy()
        mk.draw(img, 5000 + i, g)
        caps.append(cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA))
    st = {"mk": {"drawn": True, "rect": list(g.rect), "screen": [w, h]}}      # guarded, as a live capture is
    vid = VideoRecorder(tmp_path / "on", width=320, queue_size=1000, marker=True, states=lambda: st).start()
    for i in range(240):
        vid.push(caps[i % len(caps)], i, i)
    s = vid.close()
    cost, mark = s["callback_us"], s["marker"]["decode_mask_us"]
    assert s["marker"]["counts"] == {"ok": 240} and s["training_safe"] is True
    assert mark["p50"] < 250 and mark["p50"] < 0.3 * cost["p50"], (mark, cost)
    vid = VideoRecorder(tmp_path / "absent", width=320, queue_size=1000, marker=True).start()
    plain = cv2.cvtColor(base, cv2.COLOR_GRAY2BGRA)
    for i in range(60):
        vid.push(plain, i, i)
    s = vid.close()
    assert s["marker"]["counts"] == {"absent": 60} and s["marker"]["decode_mask_us"]["p50"] < 1000, s["marker"]


def test_format_2_video_still_reads(tmp_path):
    """A video from before the mask guard: no "mm" (0), marks read as recorded."""
    imgs = [np.full((9, 16), v, np.uint8) for v in (10, 20)]
    raw = b"".join(FRAME_HEAD_V2.pack(i, 100 + i, 200 + i, 16, 9, 64, 36, 7 + i, 0) + im.tobytes()
                   for i, im in enumerate(imgs))
    comp = formats.compressor(1).compress(raw)
    (tmp_path / DATA).write_bytes(comp)
    (tmp_path / META).write_text(json.dumps({"format": 2, "status": "closed", "marker": {"decode": True},
                                             "mask": {"corner": "tr"}}), encoding="utf-8")
    rd = VideoReader(tmp_path)                             # no index: rebuilt from the format-2 headers
    assert rd.rebuilt and rd.marked and rd.masked and [(i.mk, i.mm) for i, _ in rd.frames()] == [(7, 0), (8, 0)]
    assert rd.times()["mm"].tolist() == [0, 0] and rd.labels()["training_safe"] is None


def test_format_1_video_still_reads(tmp_path):
    """A video recorded before the capture path read the marker: shorter frame header, no marks (mk -1, "off")."""
    imgs = [np.full((9, 16), v, np.uint8) for v in (10, 20, 30)]
    raw = b"".join(FRAME_HEAD_V1.pack(i, 100 + i, 200 + i, 16, 9, 64, 36) + im.tobytes() for i, im in enumerate(imgs))
    comp = formats.compressor(1).compress(raw)
    (tmp_path / DATA).write_bytes(comp)
    (tmp_path / META).write_text(json.dumps({"format": 1, "status": "closed"}), encoding="utf-8")
    entry = {"i": 0, "off": 0, "clen": len(comp), "ulen": len(raw), "n": 3, "seq": [0, 1, 2], "t": [100, 101, 102],
             "ts": [200, 201, 202]}
    (tmp_path / INDEX).write_text(json.dumps(entry) + "\n", encoding="utf-8")
    for rebuilt in (False, True):
        rd = VideoReader(tmp_path)
        assert rd.rebuilt == rebuilt and not rd.marked and rd.format == 1
        got = list(rd.frames())
        assert [(i.seq, i.src_w, i.mk, i.mks) for i, _ in got] == [(k, 64, -1, MARK_OFF) for k in range(3)]
        assert all(np.array_equal(t, im) for (_, t), im in zip(got, imgs))
        assert rd.times()["mk"].tolist() == [-1] * 3 and rd.labels()["decode"] == {"off": 3}
        assert not rd.masked and rd.labels()["training_safe"] is False
        (tmp_path / INDEX).unlink(missing_ok=True)
