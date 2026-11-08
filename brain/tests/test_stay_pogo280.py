"""Task 182 seq 280 (the person via Sol: "give the ordinary planner the slow-shift preference"): over the vaulted Clapper's head
after its real bounce (L2's over_stay), the ordinary rows' own down slash on it still counts - GoalPrefs.stay_pogo - credited
only once the row's checks pass (contact and its exit: S = 0 on both branches), while the stage's no_hit for every other slash,
the other Clapper's ban, every other source's ban, FORCED_RISK, the dash kept for an escape, the escape check's window, every
other stage (the middle landing included) and every value B2 compares stay: the credit ranks the ordinary rows only."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_v2 as v2, stance_block
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.knife_chain_score_bound import ValueDominated
from ssbot.combat.planner import PlannerConfig, PlanResult
from ssbot.combat.tactics import clapper_tactics as CT, gauntlet as G
from ssbot.combat.tactics.modes import GoalPrefs
from ssbot.core.worldstate import E
from ssbot.knowledge import kinematics as kin
from ssbot.train.forum_planner_policy import CREST_PARAMS
from tests.test_clapper_priority import change
from tests.test_forum_planner import FLOOR, _ctx, _reed_forecaster, _world
from tests.test_l2_plan182 import antic, body, go_, plan_of, planned, request
from tests.test_special_mode import _support

RX = 37.0                                 # the target (test_dslash's synthetic Reed): body RX +- 0.5, FLOOR .. FLOOR + 2
ONE = frozenset({7})


# ---- L2: only over_stay names its own target, idle or walking, and only when nothing else bans it ----

@pytest.fixture
def manual_b(monkeypatch):
    """test_clapper_priority's manual-B settings (its autouse fixture), for the L2 tests here only."""
    for k in ("SSBOT_FORUM_CHAIN_NATIVE", "SSBOT_FORUM_CHAIN_B2", "SSBOT_FORUM_CHAIN_AIR_MANUAL"):
        monkeypatch.setenv(k, "1")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_ARM", "B")
    monkeypatch.setattr(G, "TWO_FOCUS", True)
    monkeypatch.setattr(G, "TWO_SPRINTSW", True)
    monkeypatch.setattr(G.jump_behind, "ENABLED", True)
    return monkeypatch


def test_only_over_stay_keeps_its_targets_down_slash():
    J = body(1, 19., "Cast Slam Antic", "CC_JUMP_CAST", facing=1)
    plan = plan_of(request(J=J, W=body(2, 28.), hx=24.))
    assert plan.phase("over_head").after("bounced") == "over_stay"
    names = [p.name for p in plan.phases]
    assert [n for n in names if plan.phase(n).down_ok] == ["over_stay"]
    assert set(plan.phase("over_stay").no_hit) == {1, 2} and plan.phase("over_stay").attack is None   # as before
    # the legal, safe middle landing stays the existing route: once the jumper's hazard is over, over_back lands in the gap
    assert plan.phase("over_stay").after("hazard_over") == "over_back" and not plan.phase("over_back").down_ok
    assert plan.phase("over_back").stance == ("middle", 2)
    unit = CT.PlannedMiddle()
    plans = NS(stance=lambda sc, ph: 30., stage_frame=lambda sc: 77)
    sc = NS(plans=plans, geo=None, hx=24., tac=None)
    for name in names:
        plans.exec = NS(plan=plan, phase=plan.phase(name), name=name)
        for fam in (None, "CC_IDLE"):                     # idle or walking: the subject reads CC_IDLE for both
            ap = unit.apply(sc, "middle_jump", None, NS(iid=2, family=fam))
            assert ap.down_ok == (frozenset({2}) if name == "over_stay" else frozenset()), (name, fam)
    plans.exec = NS(plan=plan, phase=plan.phase("over_stay"), name="over_stay")
    for fam in ("CC_SLAM", "CC_EVADE", "CC_JUMP", "CC_JUMP_CAST"):     # a new move of it: re-judged, no credit
        assert unit.apply(sc, "middle_jump", None, NS(iid=2, family=fam)).down_ok == frozenset(), fam
    assert unit.apply(sc, "middle_jump", None, NS(iid=1, family=None)).down_ok == frozenset()      # never the other one
    assert unit.apply(sc, "middle_jump", None, NS(iid=2)).down_ok == frozenset({2})                # (no family: idle)


def _go(tac, ws, fc, **kw):
    """go_ with more fields in the incoming preferences (another source's ban, a stale stay_pogo)."""
    ws.stamp.t_game_s += 1 / 60.
    for e in ws.entities:
        e.fsm = [(a, b, c + 1 / 60.) for a, b, c in (getattr(e, "fsm", None) or [])]
    return tac._decide(ws, fc, G.GoalPrefs(mode="ENGAGE", stance_x=27., weights={}, hit_w={7: 1., 8: 1.}, **kw))


def test_the_real_l2_hands_over_stays_target_to_the_planner_alone(manual_b):
    tac, ws, fc = planned(manual_b)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)
    go_(tac, ws, fc)
    ex = tac.plan_runner.exec
    assert ex.plan is not None
    # before the stage: none, and a stale one in the incoming preferences is not carried
    out = _go(tac, ws, fc, stay_pogo=frozenset({8}))
    assert ex.name != "over_stay" and out.stay_pogo == frozenset()
    ex.name = "over_stay"                                  # after the over route's real bounce (test_l2_plan182)
    out = go_(tac, ws, fc)
    assert ex.name == "over_stay" and out.target == 8
    assert out.stay_pogo == frozenset({8}) and {7, 8} <= set(out.no_hit)    # the merged no_hit as before
    # another source bans it (an earlier no_hit): no credit
    out = _go(tac, ws, fc, no_hit=frozenset({8}))
    assert ex.name == "over_stay" and out.stay_pogo == frozenset() and 8 in out.no_hit
    out = go_(tac, ws, fc)
    assert ex.name == "over_stay" and out.stay_pogo == frozenset({8})        # fresh every tick
    # its new move (the slam's antic): no credit, whatever the stage does with it
    change(fc, 8, family=G.CC_SLAM, state="Slam Antic", committed=True)
    out = go_(tac, ws, fc)
    assert out.stay_pogo == frozenset()


# ---- the planner: the credit only after the checks ----

@pytest.fixture(scope="module")
def wparams():
    return kin.HeroParams.load(CREST_PARAMS["Wanderer"])


@pytest.fixture(scope="module")
def warena():
    return kin.Terrain2D.from_boxes([(10.0, 0.0, 53.0, FLOOR), (10.0, 0.0, 14.01, 30.0), (48.99, 0.0, 53.0, 30.0)])


def _prefs(sp=True, stance=RX, **kw):
    """over_stay's preferences on the target (iid 7): the stage's no_hit, SP4's no_pogo / ground_hit / no_dash near an idle
    Clapper, the target's weight 3, its head as the stance (or stance); stay_pogo on or off."""
    d = dict(hit_w={7: 3.0}, target=7, no_hit=ONE, no_pogo=ONE, ground_hit=ONE, no_dash=ONE,
             stay_pogo=ONE if sp else frozenset())
    d.update(kw)
    return GoalPrefs("RUSH", stance, {}, **d)


def _late_support(w, k_from=42):
    """test_dslash's body (iid 7, margin 0.5, in the escape check from ESC_FROM_K on) and a threat only the escape check reads
    (iid 9): the floor w u either side of the target from look-ahead k_from on (past the horizon)."""
    from tests.test_special_mode import _raw
    rs = v2.RangeSupport(v2.Canvas(), v2.SAMPLE_KS, 0, None)
    rs.trk, rs.margin_mode, rs.focus, rs.dash_focus = NS(now={}, tables={}, hero=None, T=0.0), "flat:0.5", 7, None
    cb, bx0, by0 = v2.coarse(_raw(RX - 0.5, FLOOR, RX + 0.5, FLOOR + 2.0), 0.05, rs.cv.cell)
    cl, lx0, ly0 = v2.coarse(_raw(RX - w, FLOOR, RX + w, FLOOR + 3.0), 0.05, rs.cv.cell)
    for si, k in enumerate(v2.SAMPLE_KS):
        rs.add_raw(si, 7, cb, bx0, by0, 0.5, 0.5 if k >= v2.ESC_FROM_K else None)
        if k >= k_from:
            rs.add_raw(si, 9, cl, lx0, ly0, None, 0.5)
    rs.finish()
    return rs


def _tick(params, arena, monkeypatch, x0, h, vy, prefs, challenger=None, swing_age=None, facing=None, rs=None, **cfg):
    """One ordinary tick in the air over the target: her box bottom h u above its top, falling at vy, facing it (or facing);
    the body is a damage box (as a Clapper's), the target never reacts (test_dslash). swing_age: a down slash pressed that
    many frames before this tick is swinging. rs: another RangeSupport. cfg: ForumConfig fields."""
    monkeypatch.setattr(stance_block, "blocked", lambda *a, **k: None)
    monkeypatch.setattr(v2.RangeSupport, "reaction", lambda self, *a, **k: None)
    if rs is None:
        rs = _support({7: [(RX - 0.5, FLOOR, RX + 0.5, FLOOR + 2.0)]}, NS(now={}, tables={}, hero=None, T=0.0))
    f = v2.V2Forecast(_reed_forecaster(None, x=RX).forecast(0.8), rs)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True, **cfg), crest="Wanderer")
    pl.debug = True
    y = FLOOR + 2.0 + h + params.foot
    start = kin.initial_state(params, x0, y, vy=vy, ground=False,
                              facing=facing if facing is not None else (1 if x0 < RX else -1))
    if swing_age is not None:
        start[kin.ATTACKING], start[kin.ATK_T], start[kin.ATK_PDIR] = 1.0, swing_age * params.frame_time, 2.0
    ws = _world(x0)
    ws.hero.pos = E((x0, y))
    args = (ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, prefs, _ctx())
    if challenger is not None:
        return pl, pl._ordinary_tick(*args, challenger_value=challenger)
    return pl, pl.tick(*args)


@pytest.mark.parametrize("side", [-1, 1])
def test_a_safe_down_slash_on_the_stay_target_is_taken_on_either_side(wparams, warena, monkeypatch, side):
    x0 = RX + side * 0.9
    pl0, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False))
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True))
    k = "L" if side < 0 else "R"
    assert not r0.name.startswith("ATTACK(down)") and not r0.S        # off: the stage's no_hit and SP4's no_pogo keep it out
    assert r1.name == f"ATTACK(down){k}+idle" and not r1.S and not r1.forced_risk     # on: its own slash, checked safe
    sp = pl1.last_info["stay_pogo"]
    assert sp["chosen"] and sp["safe"] >= 5 and sp["rows"] > sp["safe"]
    i = r1.idx
    assert r1.J == pytest.approx(float(pl1.last_sel["J"][i]))                        # the plain J (what B2 compares)
    assert float(pl1.last_sel["J_sel"][i]) == pytest.approx(r1.J + 10.0 * 3.0)       # ranked with one hit at its weight
    assert sp["credit"] == pytest.approx(30.0)
    cmd = pl1.last_sel["cmd"][i]
    assert ((cmd[1:4] & kin.B_ATTACK) != 0).all() and ((cmd[1:4] & kin.B_DOWN) != 0).all()
    # the same rows are checked either way: the evasion core keeps its S / Hz / U (prefs never reach them)
    for key in ("S", "Hz", "U"):
        assert np.array_equal(pl0.last_info[key][pl0.last_info["core_mask"]], pl1.last_info[key][pl1.last_info["core_mask"]])


def test_the_landed_hit_ranks_it_whatever_its_weight(wparams, warena, monkeypatch):
    # the target's weight near 0: the hit value in J is negligible, the landed-hit rank (one hit) still takes it first
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True, hit_w={7: 0.001}))
    assert r1.name == "ATTACK(down)L+idle" and not r1.S and pl1.last_info["stay_pogo"]["chosen"]


@pytest.mark.parametrize("side", [-1, 1])
def test_its_rows_are_checked_first(wparams, warena, monkeypatch, side):
    # one hit branch a tick (hitfx_k) and a stance 4 u past her on her side: by J alone a run toward the stance (it meets the
    # target too) takes the branch first; the queue takes the stay target's down-slash rows first, so the best one is checked
    # (safe) and taken; rows past the cap stay S = 1 while a safe row exists, as before
    x0, st = RX + side * 0.9, RX + side * 4.0
    k = "L" if side < 0 else "R"
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -1.0, _prefs(True, stance=st), hitfx_k=1)
    assert r1.name == f"ATTACK(down){k}+idle" and not r1.S and pl1.last_info["stay_pogo"]["chosen"]
    pl0, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -1.0, _prefs(False, stance=st), hitfx_k=1)
    assert not r0.name.startswith("ATTACK(down)") and not r0.S


@pytest.mark.parametrize("side", [-1, 1])
def test_the_swinging_down_slash_stays_on_the_rows_that_keep_it(wparams, warena, monkeypatch, side):
    # a down slash pressed 3 frames before this tick (the scorer sees no swing start in the rows): its remaining active
    # frames meet the body at frame 5 on every row that keeps the swing; the hit branch judges its bounce, the miss branch
    # stays; a dash ends it. The old live failure (#280: the swing pressed at 4838 dropped at 4841 for a dash) is this case
    from ssbot.combat import forum_planner as fp
    seen = []
    orig = fp.ForumPlanner._score_forum

    def keep(self, *a, **k):
        seen.append(orig(self, *a, **k))
        return seen[-1]

    monkeypatch.setattr(fp.ForumPlanner, "_score_forum", keep)
    x0 = RX + side * 0.9
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), swing_age=3)
    names = pl1.last_info["dbg"]["names"]
    sc = next(s for s in reversed(seen) if len(s["J"]) == len(names))
    k = "L" if side < 0 else "R"
    move, wait = names.index(f"MOVE({k})+idle"), names.index("WAIT+idle")
    dash = next(i for i, n in enumerate(names) if str(n).startswith(f"DASH({k})"))
    assert sc["inflight_down"][move] and sc["first_k"][move] == 4 and sc["first_f"][move] == 5
    assert not sc["inflight_down"][dash] and sc["first_f"][dash] != 5
    safe = pl1.last_sel["safe"]
    assert safe[move] and not safe[wait]               # straight down onto the body: unsafe on its miss branch
    assert sc["stay_pogo"][wait] and not pl1.last_sel["J_sel"][wait] > pl1.last_sel["J"][wait]   # so not credited
    assert r1.name == f"MOVE({k})+idle" and pl1.last_info["stay_pogo"]["chosen"] and not r1.S
    assert float(pl1.last_sel["J_sel"][r1.idx]) == pytest.approx(r1.J + 10.0 * 3.0)
    seen.clear()
    pl0, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False), swing_age=3)
    assert r0.name == r1.name and r0.J == pytest.approx(r1.J)      # the same keys and plain J; on, its hit ranks it
    assert "inflight_down" not in next(s for s in reversed(seen) if len(s["J"]) == len(names))   # stay_pogo only
    # the same swing 8 frames old: one active frame left (frame 1, still 1.5 u above), so no row is credited a contact the
    # finished swing would have made later
    seen.clear()
    pl8, _ = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), swing_age=8)
    sc8 = next(s for s in reversed(seen) if len(s["J"]) == len(pl8.last_info["dbg"]["names"]))
    assert not sc8["inflight_down"].any()
    # a dash inside the swing's window ends it: 1.6 u off its edge, 0.6 u above its top, the swing 4 frames old (frames 1-5
    # left), the dash toward it starts on frame 3 and passes over it at the blade's height - no contact is credited to it
    seen.clear()
    to = "R" if side < 0 else "L"
    pld, _ = _tick(wparams, warena, monkeypatch, RX + side * (0.5 + 1.6), 0.6, -2.0, _prefs(True), swing_age=4)
    nd = pld.last_info["dbg"]["names"]
    scd = next(s for s in reversed(seen) if len(s["J"]) == len(nd))
    md = np.asarray(pld.last_info["dbg"]["mode"])
    dashes = [i for i, n in enumerate(nd) if str(n).startswith(f"DASH({to})")]
    assert dashes and (md[dashes, 3] == fp.M_DASH).all()
    assert not scd["inflight_down"][dashes].any()


def test_contact_evidence_is_every_blade_in_the_air():
    # the variant set is the replay's model hit rule (pogo_model.slash_poly: DownSlash / DownSlashAlt, both facings), and a
    # row's contact counts only with the hero off the ground and every one of them meeting its target there
    from ssbot.combat import forum_planner as fp, pogo_model as PM
    v, st = fp._down_variants("Wanderer")
    polys = [v[st[i]:st[i + 1]] for i in range(len(st) - 1)]
    want = [PM.slash_poly(f, alt) for alt in (False, True) for f in (1, -1)]
    assert len(polys) == len(want) == 4
    for p, q in zip(polys, want):
        assert (p[:, 0].min(), p[:, 0].max()) == pytest.approx((q[:, 0].min(), q[:, 0].max()), abs=1e-3)
    T1, cy = 6, 11.04                                         # her box centre y (box 10.0 .. 12.08)
    xs = [10.0, 10.0, 10.0, 11.0 + 1.6, 11.0 + 1.3, 11.0 + 1.52, 10.0]
    box = np.zeros((len(xs), T1, 4))
    for c, x in enumerate(xs):
        box[c, :] = (x - 0.25, 10.0, x + 0.25, 12.08)
    tbox = np.zeros((2, T1, 4))
    tbox[0, :] = (9.0, 8.0, 11.0, 12.5)                      # tall: the blades' whole height, x 9 .. 11
    tbox[1, :] = (9.0, 6.0, 11.0, cy - 2.13)                 # its top between DownSlash's lowest point and DownSlashAlt's
    flags = np.zeros((len(xs), T1), np.int32)
    flags[1, 3] = kin.F_GROUND
    sel = np.array([True, True, False, True, True, True, True])
    ft = np.array([0, 0, 0, 0, 0, 0, 1], np.int64)
    out = np.zeros(len(xs), np.bool_)
    fp._down_robust(box, flags, tbox, np.full(len(xs), 3, np.int64), ft, sel, v, st, out)
    # over it in the air / landed / not asked / 1.6 u off (DownSlash facing away reaches 1.742) / 1.3 u (all reach) /
    # 1.52 u (both blades facing away reach, the other facing's DownSlash 1.481 does not) / DownSlashAlt short below
    assert out.tolist() == [True, False, False, False, True, False, False]


@pytest.mark.parametrize("side", [-1, 1])
def test_a_contact_only_some_blades_make_earns_nothing(wparams, warena, monkeypatch, side):
    # the target behind her (she faces away), 1.55 u past its edge: the scorer's DownSlash in her facing reaches 1.742 u back,
    # DownSlashAlt 1.576 u and the other facing 1.481 u. The rows that keep her facing and close in only at the edge get
    # their first down hit from the scorer but no contact evidence (the replay's model hit takes every variant): not
    # credited. Rows turning to it (its blade then reaches it in every variant) still are
    from ssbot.combat import forum_planner as fp
    seen = []
    orig = fp.ForumPlanner._score_forum

    def keep(self, *a, **k):
        seen.append(orig(self, *a, **k))
        return seen[-1]

    monkeypatch.setattr(fp.ForumPlanner, "_score_forum", keep)
    x0 = RX + side * (0.5 + 1.55)
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 0.8, -6.0, _prefs(True), facing=side)
    names = pl1.last_info["dbg"]["names"]
    sc = next(s for s in reversed(seen) if len(s["J"]) == len(names))
    away, to = ("R", "L") if side > 0 else ("L", "R")
    edge = names.index(f"ATTACK(down){away}+run{to}8_stop")
    assert sc["first_k"][edge] == fp.K_DOWN and sc["first_f"][edge] >= 0
    assert sc["stay_edge"][edge] and not sc["stay_pogo"][edge]
    turn = names.index(f"ATTACK(down){to}+idle")
    assert sc["stay_pogo"][turn] and not sc["stay_edge"][turn]
    assert r1.name == f"ATTACK(down){to}+idle" and pl1.last_info["stay_pogo"]["chosen"] and not r1.S


def test_the_escape_check_window_keeps_the_rows_it_read_before():
    # the credited rows (5 .. 10): every other safe row and the first four credited ones stay where the order put them, the
    # other credited ones go last - the check's old window (its first K other rows) stays whole once the caller adds the 4
    # kept to its K; nothing credited: the order's safe rows as before
    from ssbot.combat import forum_planner as fp
    order = np.array([5, 0, 6, 1, 7, 2, 8, 3, 9, 4, 10])
    safe = np.ones(11, bool)
    safe[3] = False
    sp = np.zeros(11, bool)
    sp[5:] = True
    ranked, n = fp._esc_ranked(order, safe, sp, front=4)
    assert n == 4 and ranked.tolist() == [5, 0, 6, 1, 7, 2, 8, 4, 9, 10]
    for none in (None, np.zeros(11, bool)):
        r0, n0 = fp._esc_ranked(order, safe, none)
        assert n0 == 0 and r0.tolist() == [5, 0, 6, 1, 7, 2, 8, 9, 4, 10]


@pytest.mark.parametrize("side", [-1, 1])
def test_the_escape_check_comes_before_the_preference(wparams, warena, monkeypatch, side):
    # a threat only the escape check reads (past the horizon, the floor 2 u round the target) and a 4-row escape window: the
    # four best credited rows end in it; the check then reads the rows it read before the credit, in their order, before any
    # other credited row, and the first of them passes (S = 0) - a credited row taken from the window alone fails (S = 1).
    # With the stance behind her, a credited row that runs out of it passes and is taken
    k = "L" if side < 0 else "R"
    x0 = RX + side * 0.9
    pl, r = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), rs=_late_support(2.0), v2_esc_k=4)
    assert r.name == f"MOVE({k})+wait8_jump" and not r.S
    assert pl.last_info["esc"]["fail"] == 0 and pl.last_info["esc"]["checked"] == 8
    assert not pl.last_info["stay_pogo"]["chosen"] and pl.last_info["stay_pogo"]["safe"] > 4
    pl2, r2 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True, stance=RX + side * 4.0), rs=_late_support(2.0),
                    v2_esc_k=4)
    assert r2.name == f"ATTACK(down){k}+run{k}28_stop" and not r2.S and pl2.last_info["stay_pogo"]["chosen"]


def test_forced_risk_ranks_as_before(wparams, warena, monkeypatch):
    # no safe row: the down slash on it (in contact on a branch) has no exit and earns nothing
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 0.6, 0.0, _prefs(False))
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 0.6, 0.0, _prefs(True))
    assert r0.forced_risk and r1.forced_risk
    assert r1.name == r0.name and r1.J == pytest.approx(r0.J)
    sp = pl1.last_info["stay_pogo"]
    assert sp["rows"] > 0 and sp["safe"] == 0 and not sp["chosen"]


def test_an_unsafe_down_slash_earns_nothing_beside_safe_rows(wparams, warena, monkeypatch):
    # straight over the body: every down slash's miss branch falls onto it; the safe rows rank as before
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.3, 2.0, 0.0, _prefs(False))
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.3, 2.0, 0.0, _prefs(True))
    assert not r1.S and not r1.forced_risk
    assert r1.name == r0.name and r1.J == pytest.approx(r0.J)
    sp = pl1.last_info["stay_pogo"]
    assert sp["rows"] > 0 and sp["safe"] == 0 and not sp["chosen"]


def test_the_dash_stays_for_the_escape_it_is_needed_for(wparams, warena, monkeypatch):
    # falling fast just off its edge: only dash rows clear it; no_dash ranks them after a safe dashless row, none exists
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.3, 2.0, -6.0, _prefs(False))
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.3, 2.0, -6.0, _prefs(True))
    assert not r1.S and r1.name == r0.name
    assert ((pl1.last_sel["cmd"][r1.idx] & kin.B_DASH) != 0).any()


@pytest.mark.parametrize("case", ["not_in_no_hit", "absent_target", "other_target"])
def test_outside_the_stage_nothing_changes(wparams, warena, monkeypatch, case):
    # stay_pogo only gives way to the stage's own no_hit on its own target: a target not in no_hit, one not present, or a
    # stay target other than the one hit (both in no_hit) changes nothing
    if case == "not_in_no_hit":
        base = dict(no_hit=frozenset(), no_pogo=frozenset(), ground_hit=frozenset())
        p0, p1 = _prefs(False, **base), _prefs(False, **base, stay_pogo=ONE)
    elif case == "absent_target":
        p0, p1 = _prefs(False), _prefs(False, stay_pogo=frozenset({9}))
    else:
        p0, p1 = _prefs(False, no_hit=frozenset({7, 9})), _prefs(False, no_hit=frozenset({7, 9}), stay_pogo=frozenset({9}))
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, p0)
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, p1)
    assert (r1.name, r1.J, r1.S) == (r0.name, r0.J, r0.S)
    sp = pl1.last_info.get("stay_pogo")
    if case == "other_target":
        assert sp is not None and sp["rows"] == 0 and not sp["chosen"]      # its own rows: none hit target 9 first
    else:
        assert sp is None


def test_b2_compares_the_plain_value(wparams, warena, monkeypatch):
    # the credit ranks the ordinary rows only: against a B2 commitment the value proof stands with stay_pogo as without it
    # (every weight is zero: no_hit on the only target), and an unpruned tick hands B2 its row's plain J
    _, q0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), challenger=1e6)
    _, q1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), challenger=1e6)
    assert isinstance(q0, ValueDominated) and isinstance(q1, ValueDominated)
    assert (q1.upper_bound, q1.challenger) == (q0.upper_bound, q0.challenger)
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True))
    assert isinstance(r1, PlanResult) and r1.name.startswith("ATTACK(down)") and not r1.S
    assert r1.J == pytest.approx(float(pl1.last_sel["J"][r1.idx]))
    assert r1.J < float(pl1.last_sel["J_sel"][r1.idx])
