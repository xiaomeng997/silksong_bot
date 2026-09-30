"""Legacy-session offset (ssbot.record.align_legacy) with a synthetic session: STATE on its own clock with freeze runs
and menus, a video whose frames show them with a known offset, 1 ms timestamps and capture jitter."""
import json

import cv2
import msgpack
import numpy as np
import pytest
import zstandard

from ssbot.ipc.framing import MsgType, encode
from ssbot.record import align_legacy as AL

PERIOD = 16_666_667
OFFSET = -1_937_000_000        # q_ns + OFFSET = pts_ns of the video frame that first shows the STATE frame


def session(seed: int = 0, n: int = 9000, freezes: int = 14):
    """STATE rows (q_ns, dt, gs) and the true video: which row each video frame shows, its pts and change."""
    rng = np.random.default_rng(seed)
    q = 1_500_000_000 + np.arange(n) * PERIOD + rng.integers(-1_500_000, 1_500_001, n)
    gs = np.full(n, AL.GS_PLAYING)
    gs[:600] = 1                                   # title menu
    gs[4000:4060] = 6                              # a scene transition
    dt = np.full(n, 1 / 60)
    candidates = np.arange(700, n - 100, 60)
    for s in rng.choice(candidates, min(freezes, len(candidates)), replace=False):
        if gs[s] == AL.GS_PLAYING:
            dt[s:s + rng.integers(3, 18)] = 0.0
    st = AL.LegacyStates(np.arange(100, 100 + n), q.astype(np.int64), dt, gs)
    # The video starts 300 frames (5 s) later; one video frame per STATE frame (a few skipped), captured 4-8 ms after
    # its present time, 1 ms timestamps.
    keep = 300 + np.flatnonzero(rng.random(n - 300) > 0.03)
    t = q[keep] + OFFSET + rng.integers(4_000_000, 8_000_001, len(keep))
    pts = (t // 1_000_000) * 1_000_000
    pts -= pts[0] - 200_000_000                    # the container starts near 0
    shown = keep
    offset = OFFSET - (int(t[0] // 1_000_000) * 1_000_000 - 200_000_000)
    frozen = dt == 0
    change = np.empty(len(shown))
    for i, r in enumerate(shown):
        rp = shown[i - 1] if i else -1
        if i and frozen[rp] and not (dt[rp + 1:r + 1] > 0).any():
            change[i] = 0.0                                          # identical render
        elif gs[r] == AL.GS_PLAYING and rng.random() < 0.18:
            change[i] = 0.0                                          # a still scene while the game advances
        else:
            change[i] = rng.uniform(0.01, 0.6)
    vid = AL.VideoSignals(pts.astype(np.int64), change, np.full(len(pts), 80.0))
    return st, vid, shown, offset


def test_finds_an_offset_that_labels_every_frame_right():
    st, vid, shown, offset = session()
    rep = AL.find_offset(st, vid)
    L = AL.labels(st, vid.pts_ns, int(rep.offset_ms * 1e6))
    assert (L == shown).mean() > 0.999
    lo, hi = rep.plateau_ms
    assert lo <= rep.offset_ms <= hi and hi - lo < PERIOD / 1e6
    assert rep.still_pairs[1] == 0 and rep.still_pairs[0] > 50
    assert rep.runner_up is not None and rep.score - rep.runner_up > 10 and not rep.notes
    assert abs(rep.guess_ms - rep.offset_ms) > 100      # the start guess alone would be far off
    assert len(rep.freeze_runs) >= 10


@pytest.mark.parametrize("seed", [3, 4, 5])
def test_the_phase_band_labels_every_frame_right(seed):
    st, vid, shown, offset = session(seed=seed)
    rep = AL.find_offset(st, vid)
    lo, hi = rep.band_ms
    assert rep.plateau_ms[0] <= lo <= rep.offset_ms <= hi <= rep.plateau_ms[1]
    # The freezes alone leave the plateau wider than the band of exact labels; the phase step finds that band.
    assert (AL.labels(st, vid.pts_ns, int(rep.offset_ms * 1e6)) == shown).all()
    for off_ms in (lo, hi):
        assert (AL.labels(st, vid.pts_ns, int(off_ms * 1e6)) == shown).mean() > 0.999
    assert rep.inconsistent == 0
    assert (AL.labels(st, vid.pts_ns, int((rep.offset_ms + PERIOD / 1e6) * 1e6)) == shown).mean() < 0.2


def write_session(tmp_path, st, n_video=40):
    (tmp_path / "meta.json").write_text(json.dumps({"hello": {"qpc_freq": 10_000_000}}), encoding="utf-8")
    cctx = zstandard.ZstdCompressor(level=3)
    with (tmp_path / "state.raw.zst").open("wb") as f, cctx.stream_writer(f) as z:
        for i, (fr, q, dt, gs) in enumerate(zip(st.f, st.q_ns, st.dt, st.gs)):
            payload = {"f": int(fr), "q": int(q) // 100, "dt": float(dt), "ts": 1.0,
                       "game": {"gs": int(gs), "scene": "Tut_01"}}
            z.write(encode(MsgType.STATE, i + 1, msgpack.packb(payload)))
    # A tiny MJPG video: a moving gradient that stops for frames 10..19.
    w = cv2.VideoWriter(str(tmp_path / "video.mkv"), cv2.VideoWriter_fourcc(*"MJPG"), 60.0, (160, 90))
    assert w.isOpened()
    x = 0
    for i in range(n_video):
        if not 10 <= i < 20:
            x += 3
        img = np.zeros((90, 160, 3), np.uint8)
        img[:, :, 1] = ((np.arange(160)[None, :] + x) * 4 % 256).astype(np.uint8)
        img[20:40, (x % 120):(x % 120) + 30] = 255
        w.write(img)
    w.release()


def test_reads_the_raw_state_stream_and_decodes_the_video(tmp_path):
    st, *_ = session(n=700)
    write_session(tmp_path, st)
    got = AL.read_states(tmp_path)
    assert got.f.tolist() == st.f.tolist() and (got.q_ns == st.q_ns // 100 * 100).all()
    assert np.allclose(got.dt, st.dt) and (got.gs == st.gs).all()
    vid = AL.decode(tmp_path / "video.mkv", width=80)
    assert len(vid.pts_ns) == 40 and np.allclose(np.diff(vid.pts_ns), PERIOD, atol=1_000_000)
    assert (vid.change[11:20] < AL.STILL).all() and (vid.change[1:10] > 0.05).all() and (vid.change[21:] > 0.05).all()


def test_cli_never_writes_into_the_session(tmp_path, capsys):
    st, *_ = session(n=700)
    (tmp_path / "s").mkdir()
    write_session(tmp_path / "s", st)
    with pytest.raises(SystemExit):
        AL.main([str(tmp_path / "s"), "--out", str(tmp_path / "s" / "x.json")])
    assert "only reads" in capsys.readouterr().err
    assert AL.main([str(tmp_path / "s"), "--out", str(tmp_path / "r.json"), "--cache", str(tmp_path / "c.npz"),
                    "--dump", str(tmp_path / "m.npz"), "--search-s", "5"]) == 0
    assert (tmp_path / "c.npz").is_file() and json.loads((tmp_path / "r.json").read_text("utf-8"))["offset_ms"]
    assert len(np.load(tmp_path / "m.npz")["state_f"]) == 40
