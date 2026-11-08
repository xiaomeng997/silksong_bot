"""Task 182 seq 280 / 281 (the person via Sol: "give the ordinary planner the slow-shift preference"): over the vaulted Clapper's
head after its real bounce (L2's over_stay), the ordinary rows' own down slash on it - GoalPrefs.stay_pogo - may change the
tick's send only after the tick has made its own choice exactly as without it, and only through a candidate that passes every
gate that choice passed (contact evidence, both branches safe, the escape check, the tail check). A failure, the escape
deadline or nothing checked leaves the tick's own choice: under the production deadlines the tick's own checks run first,
unchanged, and each of the promotion's own (a swing's hit branch, an escape batch, a tail check) starts only if it ends before
the escape check's deadline. The stage's no_hit for every other slash, the other Clapper's ban,
every other source's ban, FORCED_RISK, the dash kept for an escape, the envelope's queue and caps, every other stage (the
middle landing included) and every value B2 compares stay."""
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


def _tick(params, arena, monkeypatch, x0, h, vy, prefs, challenger=None, swing_age=None, facing=None, rs=None, pre=None,
          **cfg):
    """One ordinary tick in the air over the target: her box bottom h u above its top, falling at vy, facing it (or facing);
    the body is a damage box (as a Clapper's), the target never reacts (test_dslash). swing_age: a down slash pressed that
    many frames before this tick is swinging. rs: another RangeSupport. pre(planner, tick args): run before the tick.
    cfg: ForumConfig fields."""
    monkeypatch.setattr(stance_block, "blocked", lambda *a, **k: None)
    monkeypatch.setattr(v2.RangeSupport, "reaction", lambda self, *a, **k: None)
    if rs is None:
        rs = _support({7: [(RX - 0.5, FLOOR, RX + 0.5, FLOOR + 2.0)]}, NS(now={}, tables={}, hero=None, T=0.0))
    f = v2.V2Forecast(_reed_forecaster(None, x=RX).forecast(0.8), rs)
    fc = dict(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True)
    fc.update(cfg)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig(**fc), crest="Wanderer")
    pl.debug = True
    y = FLOOR + 2.0 + h + params.foot
    start = kin.initial_state(params, x0, y, vy=vy, ground=False,
                              facing=facing if facing is not None else (1 if x0 < RX else -1))
    if swing_age is not None:
        start[kin.ATTACKING], start[kin.ATK_T], start[kin.ATK_PDIR] = 1.0, swing_age * params.frame_time, 2.0
    ws = _world(x0)
    ws.hero.pos = E((x0, y))
    args = (ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, prefs, _ctx())
    if pre is not None:
        pre(pl, args)
    if challenger is not None:
        return pl, pl._ordinary_tick(*args, challenger_value=challenger)
    return pl, pl.tick(*args)



def _scores(monkeypatch):
    """Keep every _score_forum result of the ticks that follow (the last one of a tick's row count is its rows')."""
    from ssbot.combat import forum_planner as fp
    seen = []
    orig = fp.ForumPlanner._score_forum

    def keep(self, *a, **k):
        seen.append(orig(self, *a, **k))
        return seen[-1]

    monkeypatch.setattr(fp.ForumPlanner, "_score_forum", keep)
    return seen


def _rows_of(seen, pl):
    names = pl.last_info["dbg"]["names"]
    return names, next(s for s in reversed(seen) if len(s["J"]) == len(names))


REAL = dict(deadline_ms=ForumConfig().deadline_ms, esc_deadline_ms=ForumConfig().esc_deadline_ms)   # production: 8 / 8 + 2 ms


def _cost_clock(monkeypatch, esc_ms, hb_ms, tail_ms):
    """A deterministic clock for the production deadlines (REAL): every perf_counter reads it and it moves only in the
    planner's costed calls - an escape batch (_escape_fail_v2), a hit branch, a tail check - by their ms. Returns its state:
    log, the calls [(kind, rows)] (hit branches: the uncapped ones only, the promotion's swing recheck); ranked, the escape
    check's order per tick (its first 16 rows); passing, None (the real check) or the only rows that pass it (the others fail
    it once)."""
    import time
    from ssbot.combat import forum_planner as fp
    now, clk = [1000.0], NS(log=[], ranked=[], passing=None)
    esc0, hb0, tail0 = fp.ForumPlanner._escape_fail_v2, fp.ForumPlanner._hit_branch, fp.ForumPlanner._tail_pick
    pick0 = fp.ForumPlanner._escape_pick

    def esc(self, f, r1, hold_end, rows):
        nf, lab = esc0(self, f, r1, hold_end, rows)
        if clk.passing is not None:
            nf = np.asarray([0 if int(r) in clk.passing else max(int(n), 1) for r, n in zip(rows, nf)], np.int64)
        now[0] += esc_ms * 1e-3
        clk.log.append(("esc", [int(r) for r in rows]))
        return nf, lab

    def hb(self, *a, **k):
        out = hb0(self, *a, **k)
        now[0] += hb_ms * 1e-3
        if k.get("cap") is False:
            clk.log.append(("hb", [int(r) for r in a[4]]))
        return out

    def tail(self, *a, **k):
        out = tail0(self, *a, **k)
        now[0] += tail_ms * 1e-3
        clk.log.append(("tail", [int(r) for r in a[3]]))
        return out

    def pick(self, *a, **k):
        clk.ranked.append([int(r) for r in a[6][:16]])
        return pick0(self, *a, **k)

    monkeypatch.setattr(fp.ForumPlanner, "_escape_fail_v2", esc)
    monkeypatch.setattr(fp.ForumPlanner, "_hit_branch", hb)
    monkeypatch.setattr(fp.ForumPlanner, "_tail_pick", tail)
    monkeypatch.setattr(fp.ForumPlanner, "_escape_pick", pick)
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    return clk


def _credit(monkeypatch):
    """Sol's counterexample (seq 281): the scorer's over_stay candidates of the tick's full row set (n rows) replaced by rows,
    each credited 30 (state.n / state.rows set by the test; None: the scorer's own)."""
    from ssbot.combat import forum_planner as fp
    st, orig = NS(n=None, rows=None), fp.ForumPlanner._score_forum

    def score(self, *a, **k):
        out = orig(self, *a, **k)
        if st.rows is not None and "stay_pogo" in out and len(out["J"]) == st.n:
            m = np.zeros(st.n, bool)
            m[list(st.rows)] = True
            out["stay_pogo"], out["J_stay"] = m, np.where(m, 30.0, 0.0)
        return out

    monkeypatch.setattr(fp.ForumPlanner, "_score_forum", score)
    return st


@pytest.mark.parametrize("side", [-1, 1])
def test_a_safe_down_slash_on_the_stay_target_is_taken_on_either_side(wparams, warena, monkeypatch, side):
    # off: the tick's own choice; on: the same choice first, then its own slash (both branches safe, the escape and the tail
    # checks passed) taken in its place - and B2 still compares the choice's J
    x0 = RX + side * 0.9
    pl0, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False))
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True))
    k = "L" if side < 0 else "R"
    assert not r0.name.startswith("ATTACK(down)") and not r0.S        # off: the stage's no_hit and SP4's no_pogo keep it out
    assert r1.name == f"ATTACK(down){k}+idle" and not r1.S and not r1.forced_risk
    sp = pl1.last_info["stay_pogo"]
    assert sp["promoted"] and sp["chosen"] and sp["orig"] == r0.idx and sp["checked"][-1] == (r1.idx, 0, True)
    assert sp["safe"] >= 5 and sp["rows"] > sp["safe"] and sp["credit"] == pytest.approx(30.0)
    assert r1.J == pytest.approx(r0.J)                                # PlanResult.J: the choice's own (what B2 compares)
    cmd = pl1.last_sel["cmd"][r1.idx]
    assert ((cmd[1:4] & kin.B_ATTACK) != 0).all() and ((cmd[1:4] & kin.B_DOWN) != 0).all()
    # the same rows are checked either way: the evasion core keeps its S / Hz / U (prefs never reach them)
    for key in ("S", "Hz", "U"):
        assert np.array_equal(pl0.last_info[key][pl0.last_info["core_mask"]], pl1.last_info[key][pl1.last_info["core_mask"]])


def test_the_landed_hit_ranks_it_whatever_its_weight(wparams, warena, monkeypatch):
    # the target's weight near 0: the hit value is negligible, the landed-hit key still puts its slash ahead of the choice
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True, hit_w={7: 0.001}))
    assert r1.name == "ATTACK(down)L+idle" and not r1.S and pl1.last_info["stay_pogo"]["promoted"]


@pytest.mark.parametrize("side", [-1, 1])
def test_the_preference_buys_no_checks(wparams, warena, monkeypatch, side):
    # one hit branch a tick (hitfx_k) and a stance 4 u past her: the envelope's queue and caps are the tick's own (by J), so
    # the run toward the stance takes the one branch and the down slashes past the cap stay unchecked (S = 1): no candidate,
    # the tick sends what it sends without the preference
    x0, st = RX + side * 0.9, RX + side * 4.0
    pl0, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -1.0, _prefs(False, stance=st), hitfx_k=1)
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -1.0, _prefs(True, stance=st), hitfx_k=1)
    assert (r1.name, r1.S, r1.J, r1.mask) == (r0.name, r0.S, r0.J, r0.mask)
    sp = pl1.last_info["stay_pogo"]
    assert sp["rows"] > 0 and sp["safe"] == 0 and not sp["promoted"]
    assert np.array_equal(pl0.last_info["env"], pl1.last_info["env"]) and np.array_equal(pl0.last_info["S"], pl1.last_info["S"])


@pytest.mark.parametrize("side", [-1, 1])
def test_the_swinging_down_slash_stays_on_the_rows_that_keep_it(wparams, warena, monkeypatch, side):
    # a down slash pressed 3 frames before this tick (the scorer sees no swing start in the rows): its remaining active frames
    # meet the body at frame 5 on every row that keeps the swing - kept apart (stay_ff ...), the scorer's own first hits and
    # the tick's checks as without the preference; a dash ends it. The old live failure (#280: the swing pressed at 4838
    # dropped at 4841 for a dash) is this case
    seen = _scores(monkeypatch)
    x0 = RX + side * 0.9
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), swing_age=3)
    names, sc = _rows_of(seen, pl1)
    k = "L" if side < 0 else "R"
    move, wait = names.index(f"MOVE({k})+idle"), names.index("WAIT+idle")
    dash = next(i for i, n in enumerate(names) if str(n).startswith(f"DASH({k})"))
    assert sc["inflight_down"][move] and sc["stay_fk"][move] == 4 and sc["stay_ff"][move] == 5
    assert not sc["inflight_down"][dash] and sc["stay_ff"][dash] != 5
    safe = pl1.last_sel["safe"]
    assert safe[move] and not safe[wait]               # straight down onto the body: unsafe on its miss branch
    assert sc["stay_pogo"][wait] and pl1.last_info["stay_pogo"]["safe"] < pl1.last_info["stay_pogo"]["rows"]
    seen.clear()
    pl0, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False), swing_age=3)
    _, sc0 = _rows_of(seen, pl0)
    assert "inflight_down" not in sc0                  # stay_pogo only
    for key in ("first_f", "first_t", "first_k", "J", "nh"):
        assert np.array_equal(sc[key], sc0[key]), key  # the scorer's own outputs as without the preference
    # the choice itself keeps the swing (a credited row): nothing to promote, the same send
    assert r1.name == r0.name == f"MOVE({k})+idle" and r1.J == pytest.approx(r0.J) and not r1.S
    assert pl1.last_info["stay_pogo"]["chosen"] and not pl1.last_info["stay_pogo"]["promoted"]
    # the same swing 8 frames old: one active frame left (frame 1, still 1.5 u above), so no row is credited a contact the
    # finished swing would have made later
    seen.clear()
    pl8, _ = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), swing_age=8)
    _, sc8 = _rows_of(seen, pl8)
    assert not sc8["inflight_down"].any()
    # a dash inside the swing's window ends it: 1.6 u off its edge, 0.6 u above its top, the swing 4 frames old (frames 1-5
    # left), the dash toward it starts on frame 3 and passes over it at the blade's height - no contact is credited to it
    seen.clear()
    to = "R" if side < 0 else "L"
    pld, _ = _tick(wparams, warena, monkeypatch, RX + side * (0.5 + 1.6), 0.6, -2.0, _prefs(True), swing_age=4)
    nd, scd = _rows_of(seen, pld)
    md = np.asarray(pld.last_info["dbg"]["mode"])
    dashes = [i for i, n in enumerate(nd) if str(n).startswith(f"DASH({to})")]
    from ssbot.combat import forum_planner as fp
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
    # their first down hit from the scorer but no contact evidence (the replay's model hit takes every variant): never
    # candidates. Rows turning to it (its blade then reaches it in every variant) are, and one is taken
    seen = _scores(monkeypatch)
    x0 = RX + side * (0.5 + 1.55)
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 0.8, -6.0, _prefs(True), facing=side)
    names, sc = _rows_of(seen, pl1)
    from ssbot.combat import forum_planner as fp
    away, to = ("R", "L") if side > 0 else ("L", "R")
    edge = names.index(f"ATTACK(down){away}+run{to}8_stop")
    assert sc["first_k"][edge] == fp.K_DOWN and sc["first_f"][edge] >= 0
    assert sc["stay_edge"][edge] and not sc["stay_pogo"][edge]
    assert edge not in pl1.last_info["stay_pogo"].get("cands", [])
    turn = names.index(f"ATTACK(down){to}+idle")
    assert sc["stay_pogo"][turn] and not sc["stay_edge"][turn]
    assert r1.name == f"ATTACK(down){to}+idle" and pl1.last_info["stay_pogo"]["promoted"] and not r1.S


def test_the_promotion_takes_a_candidate_only_through_every_gate():
    # stay_promote: the first candidate (at most k) with no escape failure and a tail that holds; everything else, or no time
    # for the escape check, leaves the choice as made
    from ssbot.combat.forum_planner import stay_promote
    fails = {3: 2, 1: 0, 4: 0, 6: 0}
    tails = {1: False, 4: True, 6: True}
    esc = lambda rows: np.asarray([fails[int(r)] for r in rows])
    assert stay_promote(np.array([3, 1, 4, 6]), esc, lambda r: tails[r]) == (4, [(3, 2, None), (1, 0, False), (4, 0, True)])
    assert stay_promote(np.array([3, 1]), esc, lambda r: tails[r]) == (None, [(3, 2, None), (1, 0, False)])   # all fail
    assert stay_promote(np.array([1, 4]), esc, lambda r: None) == (1, [(1, 0, None)])     # no tail check this tick
    assert stay_promote(np.array([3, 4]), lambda rows: None, lambda r: True) == (None, [(3, None, None), (4, None, None)])
    assert stay_promote(np.array([3, 1, 3, 4]), esc, lambda r: tails[r], k=3) == (None, [(3, 2, None), (1, 0, False),
                                                                                      (3, 2, None)])     # at most k
    assert stay_promote(np.array([], np.int64), esc, lambda r: True) == (None, [])


def test_the_original_escape_result_stands_sols_counterexample(wparams, warena):
    # Sol (seq 281): order 0..24, every row past stage 1, rows 0-4 credited, limit 16, no ESC_MORE, no deadline, the escape
    # check passing only row 4. The tick's own escape pick returns row 4 (0 failures, 8 checked); the promotion only reads
    # the credited rows ahead of it (0-3), which that pick already failed, and changes nothing
    from ssbot.combat import forum_planner as fp
    pl = ForumPlanner(wparams, warena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True), crest="Wanderer")
    calls = []

    def fail_v2(f, r1, hold_end, rows):
        calls.append([int(r) for r in rows])
        return np.asarray([0 if int(r) == 4 else 1 for r in rows]), [[] for _ in rows]

    pl._escape_fail_v2 = fail_v2
    pl._esc_nf = {}
    got = pl._escape_pick(None, None, None, None, None, None, np.arange(25), (0.0, 0.0), 16, None, v2=True)
    assert got[:3] == (4, 0, 8) and calls == [[0, 1, 2, 3], [4, 5, 6, 7]]
    seen_ = dict(pl._esc_nf)
    esc = lambda rows: np.asarray([seen_[int(r)] for r in rows])          # the tick's results reused, as _ordinary_tick
    assert fp.stay_promote(np.arange(4), esc, lambda r: True)[0] is None  # rows ahead of 4: all failed, row 4 stands


@pytest.mark.parametrize("case", ["fifth_reached", "fifth_cut", "higher_fail", "higher_pass"])
def test_sols_counterexample_in_a_whole_tick_under_the_real_deadlines(wparams, warena, monkeypatch, case):
    # (Sol seq 281) the scorer's candidates put where the case needs them in the tick's own escape order (ranked), the escape
    # check passing only the given rows, the production deadlines on the cost clock:
    #   fifth_reached  ranked[0:5] credited, only the fifth passes, two batches in time: the tick's own pick is it
    #   fifth_cut      the same with 6 ms batches - the deadline stops the check after the first: the tick's own fallback (the
    #                  fewest failures, first in its order, S = 1), never one the credit would pick
    #   higher_fail    ranked[8:12] credited, ahead of the choice (ranked[1]) in the credited order: all fail, the choice stands
    #   higher_pass    one of them passes: taken, by the promotion's own batch and tail check after the tick's own checks
    # every case: the same envelope, order and window, and the tick's own checks the same calls in the same order
    clk = _cost_clock(monkeypatch, 6.0 if case == "fifth_cut" else 2.0, 0.5, 1.0)
    cred = _credit(monkeypatch)
    pl, _ = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **REAL)
    rk = clk.ranked[-1]
    cred.n, cred.rows = len(pl.last_info["dbg"]["names"]), (rk[0:5] if case.startswith("fifth") else rk[8:12])
    clk.passing = {rk[4]} if case.startswith("fifth") else ({rk[1]} if case == "higher_fail" else {rk[1], rk[9]})
    clk.log.clear()
    _, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **REAL)
    log0 = list(clk.log)
    clk.log.clear()
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), **REAL)
    assert clk.ranked[-1] == clk.ranked[-2] == rk and clk.log[:len(log0)] == log0
    more, sp = clk.log[len(log0):], pl1.last_info["stay_pogo"]
    if case == "higher_pass":
        assert sp["promoted"] and r1.idx == rk[9] and not r1.S and r1.J == pytest.approx(r0.J)
        assert more == [("esc", rk[8:12]), ("tail", [rk[9]])]
        return
    assert not sp["promoted"] and (r1.name, r1.S, r1.J, r1.mask, r1.idx) == (r0.name, r0.S, r0.J, r0.mask, r0.idx)
    if case == "fifth_reached":
        assert r0.idx == rk[4] and not r0.S and log0 == [("esc", rk[0:4]), ("esc", rk[4:8]), ("tail", [rk[4]])]
    elif case == "fifth_cut":
        assert r0.idx == rk[0] and r0.S and log0 == [("esc", rk[0:4]), ("tail", [rk[0]])]
    else:
        assert r0.idx == rk[1] and more == [("esc", rk[8:12])] and all(n == 1 for _, n, _ in sp["checked"])
    if case.startswith("fifth"):
        assert sp["orig"] == r0.idx and sp["safe"] == 5 and "cands" not in sp and more == []   # the choice is credited


@pytest.mark.parametrize("case", ["time_left", "no_time_for_its_escape_batch", "no_time_for_its_tail_check", "swing_in_time",
                                  "no_time_for_the_swing_branch"])
def test_under_the_real_deadlines_the_promotion_takes_only_the_time_left(wparams, warena, monkeypatch, case):
    # the real candidates (the plain fixture; the swing cases: pressed a frame before, the stance 7 u away) under the
    # production deadlines on the cost clock: the tick's own checks run first, exactly as without the preference; the
    # promotion's swing recheck, escape batch and tail check each start only if they end before the escape deadline, and
    # one that would not leaves the choice as made (the original tail check 6 ms: no time for the next batch or recheck;
    # 4 ms batches: the promotion's batch ends at the deadline, no time for its tail check)
    esc_ms, tail_ms = {"time_left": (2.0, 1.0), "no_time_for_its_escape_batch": (2.0, 6.0), "no_time_for_its_tail_check":
                       (4.0, 1.0), "swing_in_time": (2.0, 1.0), "no_time_for_the_swing_branch": (2.0, 6.0)}[case]
    clk = _cost_clock(monkeypatch, esc_ms, 0.5, tail_ms)
    swing = "swing" in case
    x0, st, age = (RX - 1.2, RX - 7.0, 1) if swing else (RX - 0.9, RX, None)
    pl0, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False, stance=st), swing_age=age, **REAL)
    log0 = list(clk.log)
    clk.log.clear()
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True, stance=st), swing_age=age, **REAL)
    assert clk.log[:len(log0)] == log0
    for key in ("env", "S"):
        assert np.array_equal(pl0.last_info[key], pl1.last_info[key]), key
    more, sp = clk.log[len(log0):], pl1.last_info["stay_pogo"]
    cands = sp["cands"]
    if case in ("time_left", "swing_in_time"):
        assert sp["promoted"] and not r1.S and r1.J == pytest.approx(r0.J)
        assert r1.name == ("MOVE(L)+upatk2L" if swing else "ATTACK(down)L+idle")
        head = [("hb", more[0][1])] if swing else []
        assert more == head + [("esc", cands), ("tail", [r1.idx])]
        if swing:
            assert sp["inflight_unsafe"] == [] and set(more[0][1]) <= set(cands)
        return
    assert not sp["promoted"] and (r1.name, r1.S, r1.J, r1.mask, r1.idx) == (r0.name, r0.S, r0.J, r0.mask, r0.idx)
    if case == "no_time_for_its_escape_batch":
        assert sp["cut"] == "escape" and more == [] and all(n is None for _, n, _ in sp["checked"])
    elif case == "no_time_for_its_tail_check":
        assert sp["cut"] == "tail" and more == [("esc", cands)] and all(n == 0 and t is False for _, n, t in sp["checked"])
    else:
        assert sp["inflight_cut"] and cands == [] and more == [] and "inflight_unsafe" not in sp


@pytest.mark.parametrize("side", [-1, 1])
def test_the_escape_check_comes_before_the_preference(wparams, warena, monkeypatch, side):
    # a threat only the escape check reads (past the horizon, the floor 2 u round the target) and a 4-row escape window: the
    # tick's own choice passes it; the four best candidates end in it and fail it, so the choice stands as without the
    # preference (S = 0). With the stance behind her, a candidate that runs out of it passes and is taken
    k = "L" if side < 0 else "R"
    x0 = RX + side * 0.9
    _, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False), rs=_late_support(2.0), v2_esc_k=4)
    pl, r = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), rs=_late_support(2.0), v2_esc_k=4)
    sp = pl.last_info["stay_pogo"]
    assert (r.name, r.S, r.J, r.mask) == (r0.name, r0.S, r0.J, r0.mask) and not r.S
    assert not sp["promoted"] and len(sp["checked"]) == 4 and all(n > 0 for _, n, _ in sp["checked"])
    _, r2_0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False, stance=RX + side * 4.0), rs=_late_support(2.0),
                    v2_esc_k=4)
    pl2, r2 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True, stance=RX + side * 4.0), rs=_late_support(2.0),
                    v2_esc_k=4)
    assert r2.name == f"ATTACK(down){k}+run{k}28_stop" and not r2.S and pl2.last_info["stay_pogo"]["promoted"]
    assert r2.J == pytest.approx(r2_0.J)


@pytest.mark.parametrize("case", ["escape_fails_everywhere", "no_time"])
def test_an_unsafe_or_unchecked_fallback_is_the_ticks_own(wparams, warena, monkeypatch, case):
    # (Sol seq 281, the Q6 case) every row fails the escape check - the fallback is the fewest failures, first in the tick's
    # own order - or the escape deadline leaves nothing checked: the preference changes nothing, not even the tie
    kw = dict(rs=_late_support(20.0)) if case == "escape_fails_everywhere" else dict(esc_deadline_ms=0.0)
    _, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **kw)
    pl, r = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), **kw)
    assert (r.name, r.S, r.J, r.mask, r.idx) == (r0.name, r0.S, r0.J, r0.mask, r0.idx) and r.S
    sp = pl.last_info["stay_pogo"]
    assert not sp["promoted"] and sp["safe"] > 0 and sp["checked"]
    if case == "no_time":
        assert all(n is None for _, n, _ in sp["checked"])
    else:
        assert all(n > 0 for _, n, _ in sp["checked"])


@pytest.mark.parametrize("side", [-1, 1])
def test_a_candidate_behind_the_choice_is_never_taken(wparams, warena, monkeypatch, side):
    # a macro commitment (the previous tick's row continues while no row beats it by MACRO_MARGIN): the candidates rank behind
    # the CONTINUE on that key even with the credit, so none is read and the tick sends what it sends without the preference
    from dataclasses import replace

    def macro(pl, args):
        ws, start, hold, prefix, f, prefs, ctx = args
        pl.tick(ws, start, hold, prefix, f, replace(prefs, stay_pogo=frozenset()), ctx)   # its row is the CONTINUE now
        pl.macro_until = pl.ticks + 5

    x0 = RX + side * 0.9
    _, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False), pre=macro)
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), pre=macro)
    assert r0.name == "CONTINUE" and (r1.name, r1.S, r1.J, r1.mask) == (r0.name, r0.S, r0.J, r0.mask)
    sp = pl1.last_info["stay_pogo"]
    assert sp["safe"] > 0 and sp["cands"] == [] and not sp["promoted"]


@pytest.mark.parametrize("side", [-1, 1])
def test_a_swing_in_flight_is_promoted_only_through_its_hit_branch(wparams, warena, monkeypatch, side):
    # the swing pressed a frame before this tick, 0.7 u off the target's edge, the stance 7 u away on her side: the tick's own
    # choice runs off (no contact: not a candidate) and the rows keeping the swing are candidates ahead of it. The envelope
    # never saw that swing's bounce, so the promotion first runs their hit branch: passed here (no reaction in this fixture),
    # the first is taken; made unsafe, none is and the choice stands
    from ssbot.combat import forum_planner as fp
    k = "L" if side < 0 else "R"
    x0, st = RX + side * 1.2, RX + side * 7.0
    _, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False, stance=st), swing_age=1)
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True, stance=st), swing_age=1)
    sp = pl1.last_info["stay_pogo"]
    assert sp["promoted"] and sp["orig"] == r0.idx and r1.name == f"MOVE({k})+upatk2{k}" and not r1.S
    assert sp["inflight_unsafe"] == [] and r1.J == pytest.approx(r0.J)
    orig = fp.ForumPlanner._hit_branch

    def unsafe(self, f, start, latched, sc, rows, tk, enemy_only, budget, cap=True, ev_base=None):
        if cap is False:                      # (the promotion's recheck; no other uncapped branch on a tick with a safe row)
            return np.ones(len(rows), bool), {}, {}
        return orig(self, f, start, latched, sc, rows, tk, enemy_only, budget, cap=cap, ev_base=ev_base)

    monkeypatch.setattr(fp.ForumPlanner, "_hit_branch", unsafe)
    pl2, r2 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True, stance=st), swing_age=1)
    sp2 = pl2.last_info["stay_pogo"]
    assert not sp2["promoted"] and sp2["inflight_unsafe"] and sp2["cands"] == []
    assert (r2.name, r2.S, r2.J, r2.mask) == (r0.name, r0.S, r0.J, r0.mask)


def test_forced_risk_ranks_as_before(wparams, warena, monkeypatch):
    # no safe row: the down slash on it (in contact on a branch) has no exit and earns nothing
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 0.6, 0.0, _prefs(False))
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 0.6, 0.0, _prefs(True))
    assert r0.forced_risk and r1.forced_risk
    assert r1.name == r0.name and r1.J == pytest.approx(r0.J)
    sp = pl1.last_info["stay_pogo"]
    assert sp["rows"] > 0 and sp["safe"] == 0 and not sp["chosen"] and not sp["promoted"]


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
    # the preference never reaches what B2 compares: against a B2 commitment the value proof stands with stay_pogo as without
    # it (every weight is zero: no_hit on the only target), and a promoted tick hands B2 its own choice's J
    _, q0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), challenger=1e6)
    _, q1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), challenger=1e6)
    assert isinstance(q0, ValueDominated) and isinstance(q1, ValueDominated)
    assert (q1.upper_bound, q1.challenger) == (q0.upper_bound, q0.challenger)
    _, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False))
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True))
    assert isinstance(r1, PlanResult) and r1.name.startswith("ATTACK(down)") and not r1.S
    assert r1.J == pytest.approx(r0.J) and r1.J == pytest.approx(float(pl1.last_sel["J"][pl1.last_info["stay_pogo"]["orig"]]))
