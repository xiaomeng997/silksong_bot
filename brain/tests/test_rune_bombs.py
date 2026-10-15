"""The Clapper's small runes (task 1v1 G2, forum.md 50; combat.rune_bombs): the per-bomb forecast, its occupancy, the
pending row gated on Cast 2 (SSBOT_FORUM_RUNE_NOPRE), the support's per-frame bombs (SSBOT_FORUM_RUNE_BOMB), the L2
cast stance (SSBOT_FORUM_RUNE_FACE). Every switch off: nothing changes (the other tests run with them off)."""
import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.combat import forum_v2 as v2
from ssbot.combat import rune_bombs as rb

FT = 1.0 / 60.0
X0, Y0 = 30.0, 7.47                     # the Clapper at Cast 2; the bombs at y0 - 3.8


def _bomb(iid, x, lit, y=Y0 - 3.8):
    return (iid, x, y, lit)


def _row_stream(t0=10.0, rings=3, lead=21, dur=6, step=10, late_side=None):
    """Frames (T, bombs) of one row: ring r's pair appears at t0 + r step, lights lead frames later for dur frames;
    late_side: (ring, side, extra frames) a pooled side served late."""
    out = []
    for n in range(0, rings * step + lead + dur + 5):
        T = t0 + n * FT
        bs = []
        for r in range(rings):
            for sd in ((0,) if r == 0 else (-1, 1)):
                a = r * step + (late_side[2] if late_side and (r, sd) == late_side[:2] else 0)
                if a <= n <= a + lead + dur - 1:
                    bs.append(_bomb(100 + 10 * r + sd, X0 + 4.2 * r * sd, a + lead <= n))
        out.append((T, bs))
    return out


def _lit_at(bombs, x, t):
    return any(abs(b[1] - x) < 0.01 and b[4] <= t <= b[5] for b in bombs)


def test_row_forecast_covers_every_lit_frame_from_the_cast_2_entry():
    stream = _row_stream()
    f = rb.RuneBombs()
    f.add_trigger(7, 10.0, X0, Y0)
    real = {}
    preds = []
    for T, bs in stream:
        f.feed_bombs(T, bs, [(7, X0)])
        preds.append((T, f.predict(T)))
        for iid, x, y, lit in bs:
            if lit:
                real.setdefault(round(x, 2), []).append(T)
    # every lit (bomb, frame) is in the forecast made at every earlier frame from 20 frames before it on
    for x, ts in real.items():
        for t in ts:
            for T, p in preds:
                if t - 20 * FT <= T <= t:
                    assert _lit_at(p, x, t), (x, round((t - 10.0) / FT), round((T - 10.0) / FT))
    # once a bomb is seen its window is its own (lead 19.5-21.5, at most 7 lit frames, half a frame of slack)
    T, p = preds[12]                                    # ring 1 seen at frame 10
    w = [b for b in p if abs(b[1] - (X0 + 4.2)) < 0.01][0]
    assert (w[5] - w[4]) / FT == pytest.approx(21.5 - 19.5 + 6 + 1)
    # the row is over: nothing left
    assert len(f.predict(stream[-1][0] + 30 * FT)) == 0


def test_late_pool_side_is_not_predicted_until_seen_then_rolls():
    stream = _row_stream(late_side=(2, -1, 30))
    f = rb.RuneBombs()
    f.add_trigger(7, 10.0, X0, Y0)
    for n, (T, bs) in enumerate(stream):
        f.feed_bombs(T, bs, None)
        p = f.predict(T)
        if 23 <= n < 50:                                 # its sibling seen at 20, it is not there yet
            assert not any(abs(b[1] - (X0 - 8.4)) < 0.01 for b in p)
        if n == 51:                                      # seen at 50: lights 19.5-21.5 frames later
            w = [b for b in p if abs(b[1] - (X0 - 8.4)) < 0.01][0]
            assert w[4] <= T + 20 * FT <= w[5]


def test_bombs_without_a_cast_2_make_their_own_row():
    f = rb.RuneBombs()
    f.feed_bombs(5.0, [_bomb(1, 22.0, False)], [(3, 21.9)])
    assert f.n_synth == 1 and f.rows[0].owner == 3
    p = f.predict(5.0)
    assert len(p) == 1 and p[0][1] == pytest.approx(22.0)


def test_occupied_box_against_circle():
    bk = rb.frames(np.array([[7, 30.0, 3.67, rb.R, 1.0 + 20 * FT, 1.0 + 26 * FT]]), 1.0)
    assert bk[0, 4] == 20 and bk[0, 5] == 26
    k = np.arange(30)
    stand = rb.occupied(bk, 30.0 + 1.0, 4.27, k, 0.15)          # standing next to it (Bounds centre 1.04 up)
    assert stand[20:27].all() and not stand[:20].any() and not stand[27:].any()
    high = rb.occupied(bk, 30.0 + 1.0, 4.27 + 3.2, k, 0.15)     # above its circle
    assert not high.any()
    assert not rb.occupied(bk, 30.0, 4.27, k, 0.15, owners={8}).any()


def test_frames_rounds_outward():
    b = rb.frames(np.array([[1, 0.0, 0.0, 1.0, 2.0 + 3.4 * FT, 2.0 + 7.6 * FT]]), 2.0)
    assert (b[0, 4], b[0, 5]) == (3, 8)


def _clapper_table():
    trk = ar.RangeTracker()
    tab = trk.tables.get(rb.CLAPPER)
    if tab is None:
        pytest.skip("no Clapper table")
    return tab


def test_pending_row_gated_on_cast_2(monkeypatch):
    tab = _clapper_table()
    monkeypatch.setattr(rb, "NOPRE", False)
    monkeypatch.setattr(rb, "BOMB", False)
    seg = ar.Segmenter(tab.spec)
    T = 1.0
    inst = seg.step("Spell Antic", T, X0, Y0, -1, 25.0)
    w = tab.hazard_params([h for h in tab.spec.hazards if h.name == rb.NAME][0])["trig"]["CC_CAST"]
    t = T + (w[0] + 25) * FT                              # ring 0 of a Cast 2 at the window's start
    m = ar.hazards_at(tab, seg.spawned, inst, T, (X0, Y0), t)
    assert m.m.size and m.m.any()                         # today: predicted from the Spell Antic
    monkeypatch.setattr(rb, "NOPRE", True)
    m = ar.hazards_at(tab, seg.spawned, inst, T, (X0, Y0), t)
    assert not (m.m.size and m.m.any())
    # Cast 2 seen: the row is there
    inst = seg.step("Cast 1", T + 44 * FT, X0, Y0, -1, 25.0)
    inst = seg.step("Cast 2", T + 50 * FT, X0, Y0, -1, 25.0)
    m = ar.hazards_at(tab, seg.spawned, inst, T + 50 * FT, (X0, Y0), T + 72 * FT)
    assert m.m.size and m.m.any()
    # BOMB: the spawned row leaves the estimate (the per-bomb forecast has it)
    monkeypatch.setattr(rb, "BOMB", True)
    m = ar.hazards_at(tab, seg.spawned, inst, T + 50 * FT, (X0, Y0), T + 72 * FT)
    assert not (m.m.size and m.m.any())


def test_cast_2_without_its_instance_spawns_only_with_nopre(monkeypatch):
    tab = _clapper_table()
    monkeypatch.setattr(rb, "NOPRE", False)
    seg = ar.Segmenter(tab.spec)
    seg.step("Idle", 1.0, X0, Y0, -1, 25.0)
    seg.step("Cast 2", 1.0 + FT, X0, Y0, -1, 25.0, tin=2 * FT)
    assert not seg.spawned                                # Cast 2 is not a start state: today nothing
    monkeypatch.setattr(rb, "NOPRE", True)
    seg = ar.Segmenter(tab.spec)
    seg.step("Idle", 1.0, X0, Y0, -1, 25.0)
    seg.step("Cast 2", 1.0 + FT, X0, Y0, -1, 25.0, tin=2 * FT)
    assert len(seg.spawned) == 1 and seg.spawned[0][0].name == rb.NAME
    assert seg.spawned[0][1] == pytest.approx(1.0 - FT)   # back-dated to the entry
    seg.step("Cast 2", 1.0 + 2 * FT, X0, Y0, -1, 25.0, tin=3 * FT)
    assert len(seg.spawned) == 1                          # once per entry


def test_support_bombs_per_frame():
    cv = v2.Canvas()
    ls = v2.LayerSupport(cv, v2.SAMPLE_KS)
    x = np.full((1, 40), 31.0)
    y = np.full((1, 40), 4.27)
    tk = np.arange(40) * FT
    assert not ls.occupied(x, y, tk).any()                # no bombs: the stacks only (empty)
    ls.bombs = np.array([[7, 30.0, 3.67, rb.R, 20, 26]], np.float64)
    o = ls.occupied(x, y, tk)
    assert o[0, 20:27].all() and not o[0, :20].any() and not o[0, 27:].any()
    assert not ls.occupied_without(x, y, tk, 7).any()     # the owner's bombs go with it
    assert ls.occupied_only(x, y, tk, [7])[0, 20:27].all()
    assert ls.occupied_esc(x, y, tk)[0, 20:27].all()
    ls.k_shift = 2                                        # planner frame j reads tracker look-ahead j - 2
    assert ls.occupied(x, y, tk)[0, 22:29].all()


def test_l2_cast_stance(monkeypatch):
    from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world
    monkeypatch.setattr(rb, "FACE_U", None)
    s = [subj(9, CC, 30.0, y=7.45, state="Cast 1", family="CC_CAST", committed=True)]
    p = l2().decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(26.0)              # off: face_u 4
    monkeypatch.setattr(rb, "FACE_U", 3.0)
    t = l2()
    p = t.decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(27.0) and t.last["goal_why"].endswith("rune: face")
    s = [subj(9, CC, 30.0, y=7.45)]                       # idle: face_u as before
    p = l2().decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(26.0)


def test_switch_defaults_follow_v2():
    """The person, 2026-10-15: the arm rn is the default under v2 (stance 3 u); without v2 nothing changes; 0 (FACE=0)
    turns each one off (the arm fcs0)."""
    off = {"NOPRE": False, "BOMB": False, "BOMB_M": 0.15, "FACE_U": None, "HOP": False, "NOGLIDE": False}
    rn = {"NOPRE": True, "BOMB": True, "BOMB_M": 0.15, "FACE_U": 3.0, "HOP": True, "NOGLIDE": True}
    assert rb.switches({}) == off
    assert rb.switches({"SSBOT_FORUM_V2": "0"}) == off
    assert rb.switches({"SSBOT_FORUM_V2": "1"}) == rn
    fcs0 = {"SSBOT_FORUM_V2": "1", "SSBOT_FORUM_RUNE_NOPRE": "0", "SSBOT_FORUM_RUNE_BOMB": "0",
            "SSBOT_FORUM_RUNE_HOP": "0", "SSBOT_FORUM_NOGLIDE": "0", "SSBOT_FORUM_RUNE_FACE": "0"}
    assert rb.switches(fcs0) == off
    assert rb.switches({"SSBOT_FORUM_V2": "1", "SSBOT_FORUM_RUNE_FACE": "3.5"})["FACE_U"] == 3.5
    assert rb.switches({"SSBOT_FORUM_RUNE_BOMB": "1"}) == {**off, "BOMB": True}
