"""Frame/label alignment (ssbot.record.align) on synthetic episodes with known timing (tests/align_synth.py): a
textured world under a moving camera, STATE with render-time V/P, thumbnails with capture jitter, and injected
faults (stale captures, periodic judder, a latency step, a wrong fixed D, parallax, drops, a scene jump, a still
camera, registration glitches), with and without a figure at the image centre and a HUD (masked out of the
registration by their STATE labels, or found in the video)."""
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
                                         (8, range(300, 360, 2))])
def test_periodic_judder_fails(tmp_path, seed, stale):
    """Every 2nd or 3rd capture repeating the previous frame (the next one skipping a frame): each stale capture's
    two anomalies pair up (out of step and back), its neighbours and the fits go on without it, and it is judged by
    itself at -1. The share then tracks the truth instead of the judder spoiling every fit around it."""
    ep = S.make(tmp_path, seconds=20, seed=seed, stale=set(stale))
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    assert not rep.ok and pr.verdict == "FAIL" and pr.share < 0.98
    truth, tk = _truly_off(ep, off, trk)
    ok = off.status == align.OK
    assert (off.k == tk)[ok].mean() >= 0.95 and pr.hist.get(-1, 0) >= 0.6 * len(stale)
    assert 1 - pr.share == pytest.approx(truth, abs=0.04)      # the misalignment estimate, not a multiple of it
    assert pr.excursions["runs"] >= 0.5 * len(stale) and "out of step" in pr.reason
    # What is left out does not depend on the judder: the same as without it, give or take the edges.
    assert pr.excluded["no_evidence"] == 0 and pr.excluded["low_motion"] <= 220


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


# ---- anomalies: excursions, breaks, bridges -------------------------------------------------------------------

@pytest.mark.parametrize("seed, figure", [(8, False), (4, False), (1, True)])
def test_stale_pairs_are_one_excursion_each(tmp_path, seed, figure):
    """Two stale captures in a row every 20 captures (~5 % off): the repeated frame at s and the skipped one at s + 2
    pair up as one excursion, the track goes on through it, and the two captures are judged by themselves. Before,
    each anomaly broke the track and the short segments left their aligned captures unjudged (~7x the truth)."""
    stale = {s + d for s in range(300, 900, 20) for d in (0, 1)}
    ep = S.make(tmp_path, seconds=20, seed=seed, stale=stale,
                **(dict(hero="sprite", lead=1.0, hud_state=True) if figure else {}))
    rep, off, mot, trk = align.align_episode(ep.path)
    pr = rep.primary
    truth, tk = _truly_off(ep, off, trk)
    assert not rep.ok and pr.verdict == "FAIL" and 0.04 < truth < 0.07
    assert 1 - pr.share == pytest.approx(truth, rel=0.4) and pr.unjudged <= 25
    assert pr.excursions["runs"] >= 20 and pr.excursions["longest"] <= 2
    assert (off.k == tk)[off.status == align.OK].all()


def test_registration_glitches_do_not_cascade(clean):
    """Unpaired anomalies that are registration glitches, not latency steps: two 8 captures apart, then one every 13
    captures for 300 captures. Each breaks the track, but the captures between them take their reference from the
    windows across the breaks, which all agree, and the increments across the breaks are not explained (a real
    excursion's are): they are judged, not counted against the share."""
    ep, rep, off, mot, trk = clean
    inc = mot.inc.copy()
    inc[500] += (6.0, 0.0)
    inc[508] += (-2.0, 5.0)
    inc[700:1000:13] += (4.0, 3.0)
    bad, off2 = align.align(dataclasses.replace(mot, inc=inc), trk)
    pr = bad.primary
    assert bad.ok and pr.share == 1.0 and pr.unjudged == 0
    assert pr.anomalies["breaks"] >= 20 and pr.bridged > 100 and off2.bridged[501:508].all()
