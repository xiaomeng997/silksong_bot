"""The camera-trajectory alignment monitor (ssbot.record.align) on synthetic episodes with known timing
(tests/align_synth.py): a textured world under a moving camera, STATE with render-time V/P, thumbnails with capture
jitter, and injected faults (stale captures, periodic judder, a latency step, a wrong fixed D, parallax, drops, a scene
jump, a still camera, registration glitches, runs out of step that begin while the camera stands still), with and
without a figure at the image centre and a HUD (masked out of the registration by their STATE labels, or found in the
video). The monitor must never judge a capture out of step at 0 and must not PASS a misaligned recording where the
camera motion can tell; where it cannot (constant speed), the captures are uninformative, never aligned. The M1 gate
itself is measured against the frame marker (tests/test_marker.py)."""
import dataclasses
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


def _truly_off(ep, off, trk) -> tuple[float, np.ndarray]:
    """Share of the judgeable captures (judged or counted as unjudged) that truly show another frame, and true k."""
    tk = ep.true_k(off, trk)
    judgeable = (off.status == align.OK) | np.isin(off.status, align.UNJUDGED)
    return float(((tk != 0) & judgeable).sum() / judgeable.sum()), tk


@pytest.mark.parametrize("seed, stale", [(8, range(300, 900, 2)), (8, range(300, 900, 3)), (1, range(300, 900, 2)),
                                         (8, range(300, 360, 2)), (5, range(300, 900, 2))])
def test_periodic_judder_fails(tmp_path, seed, stale):
    """Every 2nd or 3rd capture repeating the previous frame (the next one skipping a frame): each stale capture's
    two anomalies pair up (out of step and back), its neighbours and the fits go on without it, and it is judged by
    itself at -1, instead of the judder spoiling every fit around it. Here, in a moving camera, 1 - share comes close
    to the share truly off (not a property of the monitor in general). Every 2nd over half of the recording makes
    half of the increments anomalous (seed 5: the median noise estimate lay among them, nothing stood out, and
    1 - share was 0.52 for 0.26 true)."""
    ep = S.make(tmp_path, seconds=20, seed=seed, stale=set(stale))
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    assert not rep.ok and pr.verdict == "FAIL" and pr.share < 0.98
    truth, tk = _truly_off(ep, off, trk)
    ok = off.status == align.OK
    assert (off.k == tk)[ok].mean() >= 0.95 and pr.hist.get(-1, 0) >= 0.5 * len(stale)
    assert truth - 0.01 <= 1 - pr.share <= truth + 0.05
    assert pr.excursions["runs"] >= 0.5 * len(stale) and "out of step" in pr.reason
    # What is left out does not depend on the judder: the same as without it, give or take the edges.
    assert pr.excluded["uninformative"] == 0 and pr.excluded["low_motion"] <= 220


def test_anomaly_noise_holds_when_half_the_increments_are_anomalies():
    rng = np.random.default_rng(0)
    clean = np.linalg.norm(rng.normal(0.0, 0.1, (1000, 2)), axis=1)      # misses of clean increments, sigma 0.1
    assert align._noise(clean, 3.0) == pytest.approx(np.median(clean) / 1.1774) == pytest.approx(0.1, rel=0.1)
    judder = np.r_[clean[:450], rng.uniform(3.0, 15.0, 550)]            # 55 % anomalous: the median lies among them
    assert np.median(judder) / 1.1774 > 2.0 and align._noise(judder, 3.0) < 0.55
    assert align._noise(np.zeros(0), 3.0) == 0.0


def test_judder_everywhere_fails_unjudged(tmp_path):
    """Every 2nd capture stale from start to end: no fit anywhere (the anomaly noise itself is the judder), nothing
    is judged, and every judgeable capture counts against the share."""
    ep = S.make(tmp_path, seconds=12, seed=8, stale=set(range(1, 720, 2)))
    rep, *_ = align.align_episode(ep.path)
    pr = rep.primary
    assert not rep.ok and pr.verdict == "FAIL" and pr.share < 0.05 and pr.unjudged_by["no_window"] > 300
    assert "periodic repeated or skipped frames" in pr.reason


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
    assert all(v[2] == pytest.approx(0.6, abs=0.02) for v in rep.scale_by_speed.values())   # one layer: one scale


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


# ---- screen-fixed content: the hero, the HUD, and what the video shows ---------------------------------------------

def test_oracle_track_collects_screen_fixed_rects():
    cam = syn.camera(2.0, 1.0, screen=(640, 360), ppu=30.0)
    hero = {"pos": [2.5, 1.0, 0.0], "box": [2.25, 0.5, 2.75, 1.5]}
    s0 = {"f": 10, "q": 1_000_000, "cam": cam, "game": {"scene": "A"}, "hero": hero, "hud": S.hud_state_dict()}
    s1 = {"f": 11, "q": 1_166_667, "cam": dict(cam, rect=[0.0, 0.1, 1.0, 0.8]), "game": {"scene": "A"},
          "hero": None, "hud": {"masks": [None, [1, True, "Idle", None]], "spool": None, "bind_orb": [1, 2, 3]}}
    trk = align.oracle_track([s0, s1], 10_000_000, hero_margin=(1.0, 0.5))
    fx = trk.fixed
    px = fx[:, 2:] * [640, 360, 640, 360]
    hero_r = px[(fx[:, 0] == 0) & (fx[:, 1] == align.FIXED_HERO)]
    # 0.5 u right of the camera (335 px); 0.25 + 1.0 u (37.5 px) to each side, 0.5 + 0.5 u (30 px) up and down
    assert np.allclose(hero_r, [[297.5, 150.0, 372.5, 210.0]])
    hud = px[(fx[:, 0] == 0) & (fx[:, 1] == align.FIXED_HUD)].round(1).tolist()
    assert len(hud) == 5 + 1 + 2 + 2 and [16, 58, 62, 104] in hud and [70, 60, 82, 76] in hud
    assert [65.5, 74.0, 195.5, 100.0] in hud        # the spool: slots and chunks, padded by the pitch (13 px)
    # Row 1 is letterboxed (10 % bars at the top and bottom), has no hero and no usable HUD rect.
    assert np.allclose(fx[fx[:, 0] == 1], [[1, align.FIXED_VIEW, 0, 0, 1, 0.1], [1, align.FIXED_VIEW, 0, 0.9, 1, 1]])
    # A step masks what any frame it could show holds: D anywhere in the scan range, then +-K frames.
    sf = align.ScreenFixed(trk)
    t = int(trk.t_eof[0]) + 30_000_000
    key, w = sf.weight(t, t + 16_666_667, (90, 160))
    assert w[45, 84] < 0.01 and w[45, 60] > 0.99 and w[20, 10] < 0.01 and w[4, 80] < 0.01 and w[86, 80] < 0.01
    assert sf.weight(t, t, (90, 160))[0] == key and sf.weight(t + 10**9, t + 10**9, (90, 160)) == (None, None)


def test_static_pixels_are_screen_fixed_texture_only():
    tex = S.texture(1400, 2400, 4)
    checker = np.kron([[0, 255] * 5, [255, 0] * 5] * 3, np.ones((2, 2))).astype(np.uint8)[:12, :20]
    frames = []
    for i in range(90):
        img = cv2.resize(S.render(tex, 0.25 * i - 11, 0.0, hud=False), (160, 90), interpolation=cv2.INTER_AREA)
        img[40:52, 70:90] = checker   # an overlay: static, with texture
        img[0:10, 0:30] = 128         # a flat static patch: only its edge is texture (masking it would add one)
        frames.append((FrameInfo(i, 1000 + i, 0, 160, 90, 640, 360), img))
    m = align.static_pixels(frames)[(90, 160)]
    assert m[40:52, 70:90].all() and not m[0:8, 0:28].any() and not m[20:, 100:].any()
    assert align.static_pixels(frames[:40]) == {}   # too few moving steps to tell


@pytest.fixture(scope="module")
def figure(tmp_path_factory):
    """Hornet-like: a 3-pose sprite the camera keeps near the image centre (1 u behind it in its direction of travel)
    with STATE hero pos/box, and a labelled HUD with STATE hud rects; aligned (every capture shows its label)."""
    ep = S.make(tmp_path_factory.mktemp("figure"), seconds=20, seed=1, hero="sprite", lead=1.0, hud_state=True)
    return ep, *align.align_episode(ep.path)


def test_centre_figure_and_hud_are_masked_out_of_the_registration(figure, capsys):
    ep, rep, off, mot, trk = figure
    pr = rep.primary
    assert rep.ok and pr.share == 1.0 and pr.unjudged == 0 and pr.hist == {0: pr.informative}
    assert pr.anomalies == {"left_out": 0, "breaks": 0} and pr.informative >= 0.8 * rep.captures
    assert rep.scale_a["p1"] > 0.98 and rep.scale_a["p99"] < 1.02    # no speed-dependent pull towards 0
    assert rep.masked["steps"] == rep.captures - 1 and 0.05 < rep.masked["p50"] < 0.4
    # Unmasked, the figure pulls every step towards 0 by a share that falls with the speed (~25 % at 1 thumbnail px
    # per frame), the neighbours on the two sides disagree near speed changes, and the aligned recording fails.
    assert align.main([str(ep.path), "--no-mask"]) == 1
    assert "split" in capsys.readouterr().out


def test_centre_figure_with_periodic_judder_fails(tmp_path):
    ep = S.make(tmp_path, seconds=20, seed=1, stale=set(range(300, 900, 3)), hero="sprite", lead=1.0,
                hud_state=True)
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    truth, tk = _truly_off(ep, off, trk)
    assert not rep.ok and pr.verdict == "FAIL" and pr.hist.get(-1, 0) > 100
    assert 1 - pr.share == pytest.approx(truth, abs=0.06)
    assert (off.k == tk)[off.status == align.OK].mean() >= 0.97


def test_static_figure_without_labels_is_found_in_the_video(tmp_path):
    """The block the camera keeps at the centre, with no hero export this time: static_pixels() finds it."""
    ep = S.make(tmp_path, seconds=20, seed=1, hero="block", labels=False)
    rep, *_ = align.align_episode(ep.path)
    assert rep.ok and rep.primary.share == 1.0 and rep.masked["steps"] == rep.captures - 1


# ---- anomalies: excursions and breaks ------------------------------------------------------------------------------

@pytest.mark.parametrize("seed, figure", [(8, False), (4, False), (1, True)])
def test_stale_pairs_are_one_excursion_each(tmp_path, seed, figure):
    """Two stale captures in a row every 20 captures (~5 % off): the repeated frame at s and the skipped one at s + 2
    pair up as one excursion, the track goes on through it, and the two captures are judged by themselves. Before,
    each anomaly broke the track and the short segments left their aligned captures unjudged (~7x the truth); a pair
    that does not pair up still leaves its segment unjudged (seed 4: ~1.6x)."""
    stale = {s + d for s in range(300, 900, 20) for d in (0, 1)}
    ep = S.make(tmp_path, seconds=20, seed=seed, stale=stale,
                **(dict(hero="sprite", lead=1.0, hud_state=True) if figure else {}))
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    truth, tk = _truly_off(ep, off, trk)
    assert not rep.ok and pr.verdict == "FAIL" and 0.04 < truth < 0.07
    assert truth - 1e-9 <= 1 - pr.share <= 2 * truth and pr.unjudged <= 40
    assert pr.excursions["runs"] >= 20 and pr.excursions["longest"] <= 2
    assert (off.k == tk)[off.status == align.OK].all()


def test_registration_glitches_leave_their_segments_unjudged(clean):
    """Unpaired anomalies that are registration glitches, not latency steps: two 8 captures apart, then one every 13
    captures for 300 captures. Each breaks the track, and the captures between two of them, with no window of their
    own, stay unjudged and count against the share, as a run out of step between two breaks would: from inside the
    segment the two look alike. (Judging them from the windows across the breaks passed runs of 10-14 captures one
    frame late: test_runs_out_of_step_between_breaks_fail.) An aligned recording may fail this way; a misaligned one
    must never pass."""
    ep, rep, off, mot, trk = clean
    inc = mot.inc.copy()
    inc[500] += (6.0, 0.0)
    inc[508] += (-2.0, 5.0)
    inc[700:1000:13] += (4.0, 3.0)
    bad, off2 = align.align(dataclasses.replace(mot, inc=inc), trk)
    pr = bad.primary
    assert not bad.ok and pr.verdict == "FAIL" and pr.hist == {0: pr.informative}   # none judged off 0
    assert pr.anomalies["breaks"] >= 20 and pr.unjudged_by["cut"] > 200 and "track breaks" in pr.reason
    assert off2.anomaly[500] == off2.anomaly[508] == 2 and (off2.status[500:508] == align.CUT).all()


SPRITE = dict(hero="sprite", lead=1.0, hud_state=True)


@pytest.mark.parametrize("seed, runs, kw", [
    (4, [(250, 264)], {}), (4, [(450, 460)], {}), (4, [(250, 264), (700, 714)], {}),
    (4, [(250, 264)], SPRITE), (4, [(450, 460)], SPRITE), (4, [(250, 264), (700, 714)], SPRITE),
    (1, [(250, 264)], dict(SPRITE, far=(0.5, 0.65)))],
    ids=["14", "10", "two", "14-figure", "10-figure", "two-figure", "two-layer"])
def test_runs_out_of_step_between_breaks_fail(tmp_path, seed, runs, kw):
    """Runs of 10-14 captures one frame late (1-2.6 % of the captures), with the centre figure and the labelled HUD,
    and in a two-layer scene: too long to pair, so the repeated frame into a run and the skipped one out of it break
    the track. The captures between have no window of their own and their neighbours are all equally late, so they
    stay unjudged and count against the share. Taking their offset from the windows across the breaks passed every
    one of these at 0.995-1.0 with the late captures judged at 0: whether the increments across the breaks were
    explained was decided with a pass-1 scale 2 % off, times a dash."""
    stale = {i for a, b in runs for i in range(a, b)}
    ep = S.make(tmp_path, seconds=20, seed=seed, stale=stale, **kw)
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    truth, tk = _truly_off(ep, off, trk)
    ok = off.status == align.OK
    assert not rep.ok and pr.verdict == "FAIL" and truth > 0.009
    assert not (ok & (tk != 0) & (off.k == 0)).any()     # no capture out of step judged at 0
    assert 1 - pr.share >= truth - 1e-9                    # the share does not understate the misalignment
    for a, b in runs:
        assert off.anomaly[a] == off.anomaly[b] == 2 and (off.status[a:b] == align.CUT).all()


# ---- runs out of step that no anomaly shows, and what the monitor cannot see ---------------------------------------

def _velocity(monkeypatch, plan) -> None:
    """Patch align_synth.trajectory: the camera velocity of frames a .. b - 1 set to v u/s (horizontal)."""
    orig = S.trajectory

    def traj(frames, seed, still=None, jump_at=None):
        pos = orig(frames, seed, still, jump_at)
        vel = np.diff(np.r_[pos[:1], pos], axis=0)
        for a, b, v in plan:
            vel[a:b] = (v / 60, 0.0)
        return pos[0] + np.cumsum(vel, axis=0)

    monkeypatch.setattr(S, "trajectory", traj)


P = 400
STAND_WALK = [(P - 6, P + 4, 0.0), (P + 4, P + 60, 8.25)]   # verify3: stand, then walk on past the run's end


@pytest.mark.parametrize("seed, kw", [(1, {}), (4, {}), (8, {}), (3, SPRITE), (5, SPRITE), (6, SPRITE)])
def test_run_out_of_step_from_a_standstill_does_not_pass(tmp_path, monkeypatch, seed, kw):
    """The verifier's repro (verify3): captures 400..423 one frame late, starting while the camera stands still (the
    repeated frame at 400 is 0 px, which the still camera explains: no anomaly), then walking at constant speed (the
    skipped frame at 424 breaks the track). Borrowing k from windows centred on the aligned side, and the track
    constant from equally late neighbours, judged 16-18 late captures at 0 and PASSED at 0.996-0.998 with 1.8-2 %
    truly late. Their own windows see the stand -> walk change one frame late (explained only at k = -1) and every
    position after it a step off: mixed, counting against the share."""
    _velocity(monkeypatch, STAND_WALK)
    ep = S.make(tmp_path, seconds=20, seed=seed, stale=set(range(P, P + 24)), **kw)
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    truth, tk = _truly_off(ep, off, trk)
    ok = off.status == align.OK
    assert truth > 0.015 and not rep.ok and pr.verdict in ("FAIL", "INCONCLUSIVE")
    assert not (ok & (tk != 0) & (off.k == 0)).any()          # no late capture judged at 0
    assert (off.k == tk)[ok].all() and 1 - pr.share >= truth
    assert pr.unjudged_by["mixed"] > 0 and not off.consistent[P + 4:P + 24].any()


@pytest.mark.parametrize("plan, stale", [
    ([(P - 6, P + 4, 0.0), (P + 4, P + 20, 8.25), (P + 20, P + 30, 0.0)], range(P, P + 25)),
    ([(P - 6, P + 4, 0.0), (P + 4, P + 25, 14.0), (P + 25, P + 45, 28.0)], range(P, P + 24)),
    ([(P - 6, P + 4, 0.0), *((P + 4 + j, P + 5 + j, 8.25 * (j + 1) / 20) for j in range(20)), (P + 24, P + 80, 8.25)],
     range(P, P + 40))],
    ids=["stand-walk-stand", "stand-run-dash", "stand-ramp-walk"])
def test_hidden_runs_out_of_step_are_never_judged_at_zero(tmp_path, monkeypatch, plan, stale):
    """The verifier's near misses and a gradual start. Stand -> walk -> stand: both ends of the run fall where the
    camera stands still, so no anomaly shows at all (it PASSED at 0.996 before). Stand -> run -> dash: the skipped
    frame at the run's end is explained at k = +1 by the doubling speed. Stand -> ramp -> walk: every increment of the
    20-frame ramp lies within the noise at k = 0 (0.2 px against a 1 px threshold), but their sum is a whole step
    while the camera moved little (the path test of align._consistent)."""
    _velocity(monkeypatch, plan)
    ep = S.make(tmp_path, seconds=20, seed=4, stale=set(stale))
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    truth, tk = _truly_off(ep, off, trk)
    ok = off.status == align.OK
    assert truth > 0.009 and not rep.ok and pr.verdict == "FAIL"
    assert not (ok & (tk != 0) & (off.k == 0)).any() and (off.k == tk)[ok].all()
    assert pr.unjudged_by["mixed"] > 0


def test_constant_speed_captures_are_uninformative_not_aligned(tmp_path, monkeypatch):
    """The camera at constant speed for 4 s (frames 300..539): the captures more than W inside have no speed change in
    their own window, so no video could show their offset. They are uninformative (left out and reported), never
    judged or counted as aligned: a run one frame late deep inside (430..469) breaks the track at both ends and
    none of it is judged. Only the breaks show it (the monitor cannot say more; the M1 gate uses the frame marker)."""
    orig = S.trajectory

    def traj(frames, seed, still=None, jump_at=None):
        pos = orig(frames, seed, still, jump_at)
        vel = np.diff(np.r_[pos[:1], pos], axis=0)
        vel[300:540] = (-np.sign(pos[300, 0]) * 6.0 / 60, 0.0)   # through the middle of the texture
        return pos[0] + np.cumsum(vel, axis=0)

    monkeypatch.setattr(S, "trajectory", traj)
    ep = S.make(tmp_path, seconds=20, seed=4, stale=set(range(430, 470)))
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    inner = np.r_[300 + 32:430, 470:540 - 32]
    assert (off.status[inner] == align.UNINFORMATIVE).all()
    assert (off.status[430:470] == align.UNINFORMATIVE).all() and pr.anomalies["breaks"] >= 2
    assert pr.excluded["uninformative"] >= len(inner) + 40 and "'uninformative'" in rep.format()
    assert rep.ok and "track breaks" in pr.reason and "cannot judge" in pr.reason


# ---- parallax: two layers (a known limit, to be tuned on the first in-game recordings) -----------------------------

@pytest.fixture(scope="module")
def two_layer(tmp_path_factory):
    """The bottom half of the image at parallax 1, the top half a second texture at parallax 0.5; no figure, no HUD;
    every capture at offset 0."""
    ep = S.make(tmp_path_factory.mktemp("two_layer"), seconds=20, seed=1, hud=False, far=(0.5, 0.5))
    return ep, *align.align_episode(ep.path)


def test_scale_by_speed_reports_two_layer_parallax(two_layer, clean):
    """What the first in-game run must record: the registration scale per camera speed. One layer gives one scale;
    with two, the layers' correlation peaks merge or part with the speed (here 0.56 / 0.74 / 0.68 of the near layer's
    motion at 0.5-1 / 1-2 / 2-4 thumbnail px per capture), and where the splits fall."""
    ep, rep, off, mot, trk = two_layer
    p50 = [v[2] for v in rep.scale_by_speed.values()]
    assert len(p50) >= 2 and max(p50) - min(p50) > 0.1 and 0.5 < min(p50) and max(p50) < 0.9
    pr = rep.primary
    assert pr.split_at and sum(b - a + 1 for a, b in pr.split_at) == pr.unjudged_by["split"]
    assert "split captures (first, last)" in rep.format()
    assert all(abs(v[2] - 1.0) < 0.02 for v in clean[1].scale_by_speed.values()) and clean[1].primary.split_at == []


@pytest.mark.xfail(strict=True, reason="parallax background layers: the registration scale depends on the camera "
                   "speed, so aligned captures come out MIXED or SPLIT (align.py docstring, DESIGN 3.1.4); the monitor "
                   "only flags sessions until it is tuned on the first in-game recordings scored against the marker")
def test_two_layer_parallax_aligned_recording_passes(two_layer):
    """The verifier's repro. Every capture is at offset 0, but one scale a per window cannot absorb a scale that
    changes with the speed: the neighbours on the two sides of speed changes disagree, and the recording FAILs at
    0.952 on SPLIT alone (seeds 2 / 8: 0.983 / 0.971), with no anomaly. Failing an aligned recording is the safe side
    of the gate; this test turns XPASS (strict: an error) once parallax is handled."""
    ep, rep, off, mot, trk = two_layer
    assert rep.ok and rep.primary.share == 1.0
