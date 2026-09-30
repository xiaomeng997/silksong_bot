"""Frame/label alignment (ssbot.record.align) on synthetic episodes with known timing (tests/align_synth.py): a
textured world under a moving camera, STATE with render-time V/P, thumbnails with capture jitter, and injected
faults (stale captures, periodic judder, a latency step, a wrong fixed D, parallax, drops, a scene jump, a still
camera)."""
import json

import cv2
import numpy as np
import pytest

from ssbot.record import align
from ssbot.record import synthetic as syn
from ssbot.record.video import FrameInfo
from tests import align_synth as S

MS = 1_000_000


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    ep = S.make(tmp_path_factory.mktemp("clean"), seconds=20, seed=1)
    rep, off, mot, trk = align.align_episode(ep.path)
    return ep, rep, off, mot, trk


def test_phase_correlator_subpixel_and_sign():
    tex = S.texture(600, 900, 3).astype(np.float32)
    pc = align.PhaseCorrelator((90, 160))
    a = cv2.resize(tex[200:380, 300:620], (160, 90), interpolation=cv2.INTER_AREA)
    errs = []
    for dx, dy in ((0.3, 0.0), (-1.7, 0.45), (5.25, -2.6), (0.0, 0.0)):
        M = np.float32([[1, 0, dx * 2], [0, 1, dy * 2]])  # content moves by (dx, dy) thumbnail px
        moved = cv2.warpAffine(tex, M, (900, 600), flags=cv2.INTER_LINEAR)
        b = cv2.resize(moved[200:380, 300:620], (160, 90), interpolation=cv2.INTER_AREA)
        ex, ey, peak = pc.shift(pc.spectrum(a), pc.spectrum(b))
        errs.append((ex - dx, ey - dy))
        assert peak > 0.3
    assert np.abs(errs).max() < 0.06


def test_register_reports_camera_motion_in_client_px():
    tex = S.texture(1400, 2400, 2)
    cams = [(0.0, 0.0), (0.2, 0.0), (0.2, 0.1), (-0.3, -0.05)]
    frames = []
    for i, (x, y) in enumerate(cams):
        img = cv2.resize(S.render(tex, x, y), (S.THUMB, 90), interpolation=cv2.INTER_AREA)
        frames.append((FrameInfo(i, 1000 + i, 0, S.THUMB, 90, *S.SCREEN), img))
    mot = align.register(frames)
    want = np.diff(np.array(cams), axis=0) * [S.PPU, -S.PPU]  # world y up = image y down
    assert np.abs(mot.inc[1:] - want).max() < 0.3
    assert mot.ok[1:].all() and not mot.ok[0] and (mot.scale == 4.0).all()


def test_oracle_track_follows_the_camera_and_breaks():
    xs = [(0.0, 0.0), (0.1, 0.0), (0.3, 0.05), (0.3, 0.05), (9.0, 0.05), (9.2, 0.05), (9.4, 0.0), (9.5, 0.0)]
    states = []
    for i, (x, y) in enumerate(xs):
        s = {"f": 10 + i, "q": 1_000_000 + i * 166_667, "cam": syn.camera(x, y, screen=(640, 360), ppu=30.0),
             "game": {"scene": "A" if i < 6 else "B"}}
        states.append(s)
    states[3]["cam"] = None  # a frame without a camera
    trk = align.oracle_track(reversed(states), qpc_freq=10_000_000)  # order does not matter
    assert trk.f.tolist() == list(range(10, 18)) and trk.t_eof[1] - trk.t_eof[0] == 16_666_700
    assert np.allclose(trk.pos[1] - trk.pos[0], [3.0, 0.0]) and np.allclose(trk.pos[2] - trk.pos[1], [6.0, -1.5])
    # no camera at row 3; row 4 starts over (after the gap), row 5 is a normal step, the 8.7 u jump at row 4 is
    # hidden by the missing camera, the scene change at row 6 breaks again.
    assert trk.seg.tolist() == [0, 0, 0, -1, 1, 1, 2, 2] and np.isnan(trk.pos[3]).all()
    assert np.allclose(trk.pos[5] - trk.pos[4], [6.0, 0.0]) and np.allclose(trk.pos[7] - trk.pos[6], [3.0, 0.0])
    assert trk.breaks["scene"] == 1 and trk.breaks["no_cam"] == 2
    jumpy = [dict(s, cam=syn.camera(x, 0.0, screen=(640, 360), ppu=30.0), game={"scene": "A"})
             for s, x in zip(states[:3], (0.0, 0.1, 5.0))]
    t2 = align.oracle_track(jumpy, 10_000_000)
    assert t2.seg.tolist() == [0, 0, 1] and t2.breaks["jump"] == 1   # 147 px > 0.2 * 640


def test_match_picks_the_newest_frame_presented_before_the_capture():
    t_eof = np.array([0, 100, 200, 300])
    t_cap = np.array([5, 25, 124, 125, 126, 1000])
    assert align.match(t_cap, t_eof, 25).tolist() == [-1, 0, 0, 1, 1, 3]


def test_clean_episode_passes_with_D_inside_the_valid_interval(clean):
    ep, rep, off, mot, trk = clean
    pr = rep.primary
    assert pr.clock == align.GATE_CLOCK == "frame" and rep.alt.clock == "arrival"
    assert rep.ok and pr.verdict == "PASS" and pr.share == 1.0 and pr.hist == {0: pr.informative}
    assert pr.unjudged == 0 and pr.informative >= 0.5 * rep.captures and set(pr.window_hist) == {0}
    assert pr.anomalies == {"left_out": 0, "breaks": 0}
    for c in (pr, rep.alt):
        lo, hi = ep.valid_D[c.clock]
        assert lo < c.D_ms * MS <= hi
    # The agreed interval is bounded by the judged captures only, so it may reach a little past the true one.
    assert pr.D_interval_ms[0] < pr.D_ms < pr.D_interval_ms[1] and pr.D_agree[0] == pr.D_agree[1] > 300
    assert pr.lag_ms["p50"] == pytest.approx((S.D_TRUE_NS + S.FRAME_CLOCK_NS + 2.25 * MS) / MS, abs=1.0)
    # The arrival runs ~8 ms ahead of the WGC frame clock: the same matching, D shifted by that much.
    assert rep.alt.verdict == "PASS" and rep.alt.D_ms == pytest.approx(pr.D_ms - 8.25, abs=4.0)
    assert rep.scale_a["p1"] > 0.97 and rep.scale_a["p99"] < 1.03 and rep.resid_px["p99"] < 1.0
    ok = off.status == align.OK
    assert (np.array(ep.capture_frame)[ok] == trk.f[off.label[ok]] + off.k[ok]).all()
    assert rep.notes == [] and rep.screen == [[640, 360]] and rep.src == [[640, 360]]


def test_still_frames_are_low_motion_not_offsets(clean):
    ep, rep, off, mot, trk = clean
    cam = ep.extra["cam"]
    still = np.r_[False, (np.abs(np.diff(cam, axis=0)) < 1e-9).all(axis=1)]
    still_both = still & np.r_[still[1:], True]  # did not move into or out of this frame
    assert still_both.sum() > 50 and (off.status[still_both] != align.OK).all()
    assert (off.status[still_both] == align.LOW_MOTION).mean() > 0.9


def test_stale_captures_show_up_as_offset_minus_one(tmp_path):
    stale = set(range(150, 1100, 61))
    ep = S.make(tmp_path, seconds=20, seed=2, stale=stale)
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    ok = off.status == align.OK
    flagged = set(np.flatnonzero(ok & (off.k == -1)).tolist())
    assert flagged and flagged <= stale and set(pr.hist) <= {-1, 0}
    judged = {i for i in stale if ok[i]}
    assert flagged == judged                       # every judged stale capture, and nothing else
    assert len(judged) >= len(stale) - 4 and pr.unjudged == 0
    assert pr.share == pytest.approx(1 - len(judged) / pr.informative)
    assert not rep.ok and pr.verdict == "FAIL"     # ~1.5 % of captures one frame late
    # A stale capture's increments in and out are left out of the window fits; the track goes on through it.
    assert pr.anomalies["left_out"] >= 1.5 * len(judged) and pr.anomalies["breaks"] <= 2
    lo, hi = ep.valid_D["frame"]
    assert lo < pr.D_ms * MS <= hi                 # the stale minority does not move the calibration


@pytest.mark.parametrize("seed, stale", [(8, range(300, 900, 2)), (8, range(300, 900, 3)), (1, range(300, 900, 2)),
                                         (8, range(300, 360, 2))])
def test_periodic_judder_fails(tmp_path, seed, stale):
    """Every 2nd or 3rd capture repeating the previous frame (the next one skipping a frame) spoils the window fits
    around them: those captures cannot be judged, and they count against the share instead of vanishing from it."""
    ep = S.make(tmp_path, seconds=20, seed=seed, stale=set(stale))
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    assert not rep.ok and pr.verdict == "FAIL" and "unjudged" in pr.reason
    assert pr.unjudged > len(stale) // 2 and pr.share < 0.97
    # What is left out does not depend on the judder: the same as without it, give or take the edges.
    assert pr.excluded["no_evidence"] == 0 and pr.excluded["low_motion"] <= 220


def test_latency_step_is_localized(tmp_path):
    """Captures 300-399 all one frame late: the repeated frame at 300 and the skipped one at 400 break the track, so
    no window or neighbour set mixes the two offsets and no capture next to the step inherits the wrong one."""
    ep = S.make(tmp_path, seconds=20, seed=8, stale=set(range(300, 400)))
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    tk = ep.true_k(off, trk)
    ok = off.status == align.OK
    assert off.anomaly[300] == 2 and off.anomaly[400] == 2
    assert (ok[287:300]).all() and (off.k[287:300] == 0).all() and (off.k[300:304] == -1).all()
    assert ((off.k == 0) == (tk == 0))[ok].all()   # judged at 0 exactly where the capture shows its label
    assert (off.k == tk)[ok & off.clear].all()
    assert not rep.ok and pr.hist.get(-1, 0) >= 40 and pr.hist.get(-1, 0) + pr.hist[0] >= pr.informative - 2


def test_fixed_D_one_frame_early_is_offset_minus_one_everywhere(clean):
    ep, rep, off, mot, trk = clean
    bad, off2 = align.align(mot, trk, D_ms=rep.primary.D_ms - S.PERIOD_NS / MS)
    pr = bad.primary
    assert pr.hist == {-1: pr.informative} and set(pr.window_hist) == {-1} and not bad.ok
    assert bad.alt is None                         # no calibration, no second clock
    late, _ = align.align(mot, trk, D_ms=rep.primary.D_ms + S.PERIOD_NS / MS)
    assert late.primary.hist == {1: late.primary.informative}


def test_parallax_scale_and_static_hud(tmp_path):
    ep = S.make(tmp_path, seconds=15, seed=3, parallax=0.6)
    rep, *_ = align.align_episode(ep.path)
    assert rep.ok and rep.scale_a["p50"] == pytest.approx(0.6, abs=0.02)


def test_drops_on_both_sides(tmp_path):
    drop_states = set(range(1200, 1900, 37))
    drop_captures = set(range(1100, 2000, 23))
    ep = S.make(tmp_path, seconds=20, seed=4, drop_states=drop_states, drop_captures=drop_captures)
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    assert rep.ok and pr.share == 1.0 and rep.states == 1200 - len(drop_states)
    # Captures whose next frame has no STATE cannot be judged (they might show that frame).
    assert pr.excluded["state_gap"] >= len(drop_states) - 3
    ok = off.status == align.OK
    assert (np.array(ep.capture_frame)[ok] == trk.f[off.label[ok]] + off.k[ok]).all()


def test_scene_jump_breaks_the_track(tmp_path):
    ep = S.make(tmp_path, seconds=15, seed=5, jump_at=450)
    rep, off, mot, trk = align.align_episode(ep.path)
    assert rep.track_breaks["scene"] == 1 and rep.ok and rep.primary.share == 1.0
    assert not mot.ok[450]                        # the registration does not bridge the jump either
    assert off.status[449] == align.STATE_GAP      # its next frame lies in the other track segment
    ok = off.status == align.OK
    assert (np.array(ep.capture_frame)[ok] == trk.f[off.label[ok]] + off.k[ok]).all()


def test_still_camera_is_inconclusive_and_cli_exit_codes(tmp_path, capsys):
    ep = S.make(tmp_path, seconds=6, seed=6, still=(0, 10_000))
    assert align.main([str(ep.path), "--json"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "no camera motion" in out
    rep = json.loads((ep.path / "align.json").read_text("utf-8"))
    assert rep["ok"] is False and rep["primary"]["verdict"] == "FAIL"


def test_cli_pass_writes_report_and_dump(clean, capsys):
    ep = clean[0]
    assert align.main([str(ep.path), "--json", "--dump"]) == 0
    assert "PASS" in capsys.readouterr().out
    rep = json.loads((ep.path / "align.json").read_text("utf-8"))
    assert rep["ok"] is True and rep["verdicts"] == {"frame": "PASS", "arrival": "PASS"}
    z = np.load(ep.path / "align_frames.npz")
    assert len(z["label_f"]) == len(ep.capture_t) and (z["k"][z["status"] == align.OK] == 0).all()
    assert align.main([str(ep.path), "--clock", "arrival", "--min-coverage", "0.95"]) == 1  # ~85 % judged
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_no_captures_is_reported_as_such(clean):
    trk = clean[4]
    rep, off = align.align(align.register([]), trk)
    assert off is None and not rep.ok and rep.primary.reason == "no video captures" and rep.alt is None


def test_cv2_registration_is_selectable(clean):
    ep = clean[0]
    rep, *_ = align.align_episode(ep.path, align.Params(registration="cv2", min_sep=1.0))
    assert rep.primary.informative > 0 and rep.primary.D_ms is not None
