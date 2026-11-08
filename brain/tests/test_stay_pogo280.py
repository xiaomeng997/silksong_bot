"""Task 182 seq 280 - 283 (the person via Sol: "give the ordinary planner the slow-shift preference"): over the vaulted
Clapper's head after its real bounce (L2's over_stay), the ordinary rows' own down slash on it - GoalPrefs.stay_pogo - may
change the tick's send only after the tick has made its own choice exactly as without it, and only through a candidate that
passes every gate that choice passed (contact evidence, both branches safe, the escape check, the tail check). Under the
production deadlines (a cost clock) the tick's own checks keep their whole budget - the candidate scan, the order and every
check of the promotion run after them - and each of the promotion's steps starts only if its estimate ends before the escape
deadline, its result taken only if that deadline has not passed (Sol seq 282); the estimates are the measured costs of the
same calls - the tick's own escape batch and tail checks, the promotion's own steps - not fixed seeds (Sol seq 283: the formal
run cut every scan with 1.5-2 ms left, its seeds never measured). A failure, a cut or nothing checked leaves the
tick's own choice, verdict, tail, escape record and hand-back. The stage's no_hit for every other slash, the other Clapper's
ban, every other source's ban, FORCED_RISK, the dash kept for an escape, the envelope's queue and caps, every other stage (the
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
    pl.test_args = args
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


def _scan(pl, seen):
    """The over_stay scan of the tick just run: the promotion's own (last_sel["stay"]), or, where the promotion did not run
    it, _stay_scan on that tick's scorer result and rollout (diagnostics only)."""
    if pl.last_sel.get("stay") is not None:
        return pl.last_sel["stay"]
    _, sc = _rows_of(seen, pl)
    dbg, prefs = pl.last_info["dbg"], pl.test_args[5]
    return pl._stay_scan(sc, NS(box=dbg["box"], mode=dbg["mode"], flags=dbg["flags"]), pl.test_args[1], prefs,
                         frozenset(prefs.stay_pogo) & frozenset(prefs.no_hit))


REAL = dict(deadline_ms=ForumConfig().deadline_ms, esc_deadline_ms=ForumConfig().esc_deadline_ms)   # production: 8 / 8 + 2 ms


def _cost_clock(monkeypatch, esc_ms, hb_ms, tail_ms, score_ms=0.0, robust_ms=0.0, tail_extra=None, esc_extra=None, scan_ms=0.0):
    """A deterministic clock for the production deadlines (REAL): every perf_counter reads it and it moves only in the
    planner's costed calls - an escape batch (_escape_fail_v2), a hit branch, a tail check - by their ms; score_ms at
    _score_forum's entry, robust_ms in each _down_robust (the over_stay scan's contact kernel), tail_extra / esc_extra
    {n: ms} more in the tick's n-th tail check / escape batch (counted from 1 per tick); scan_ms per over_stay scan
    (_stay_scan), clk.scan_extra {n: ms} more in the tick's n-th. Garbage collections (forum_planner._gc_runs) are the clock's
    own count, clk.gc: one is counted inside each call (kind, n) of clk.gc_calls - kinds esc, hb, hbu (the uncapped hit
    branches only), tail, scan, n counted from 1 per tick - so none happens unless a test puts it there. Returns its state:
    log, the calls [(kind, rows)] (hit branches: the uncapped ones only, the promotion's swing recheck); ranked, the escape
    check's order per tick (its first 16 rows); at, per tick the ms from the tick's start to the escape check's entry and to
    the tick's end; passing, None (the real check) or the only rows that pass it (the others fail it once). clk's fields may
    be changed between ticks."""
    import time
    from ssbot.combat import forum_planner as fp
    now, clk = [1000.0], NS(log=[], ranked=[], at=[], passing=None, n_tail=0, n_esc=0, n_hb=0, n_hbu=0, n_scan=0, t0=0.0,
                            scan_ms=scan_ms, scan_extra={}, gc_calls=set(), gc=0)
    esc0, hb0, tail0 = fp.ForumPlanner._escape_fail_v2, fp.ForumPlanner._hit_branch, fp.ForumPlanner._tail_pick
    pick0, score0, tick0, rob0 = (fp.ForumPlanner._escape_pick, fp.ForumPlanner._score_forum, fp.ForumPlanner._ordinary_tick,
                                  fp._down_robust)
    scan0 = fp.ForumPlanner._stay_scan
    ms = lambda: round((now[0] - clk.t0) * 1e3, 3)

    def gc_in(kind, n):
        if (kind, n) in clk.gc_calls:
            clk.gc += 1

    def esc(self, f, r1, hold_end, rows):
        nf, lab = esc0(self, f, r1, hold_end, rows)
        if clk.passing is not None:
            nf = np.asarray([0 if int(r) in clk.passing else max(int(n), 1) for r, n in zip(rows, nf)], np.int64)
        clk.n_esc += 1
        now[0] += (esc_ms + (esc_extra or {}).get(clk.n_esc, 0.0)) * 1e-3
        gc_in("esc", clk.n_esc)
        clk.log.append(("esc", [int(r) for r in rows]))
        return nf, lab

    def hb(self, *a, **k):
        out = hb0(self, *a, **k)
        now[0] += hb_ms * 1e-3
        clk.n_hb += 1
        gc_in("hb", clk.n_hb)
        if k.get("cap") is False:
            clk.n_hbu += 1
            gc_in("hbu", clk.n_hbu)
            clk.log.append(("hb", [int(r) for r in a[4]]))
        return out

    def tail(self, *a, **k):
        out = tail0(self, *a, **k)
        clk.n_tail += 1
        now[0] += (tail_ms + (tail_extra or {}).get(clk.n_tail, 0.0)) * 1e-3
        gc_in("tail", clk.n_tail)
        clk.log.append(("tail", [int(r) for r in a[3]]))
        return out

    def scan(self, *a, **k):
        out = scan0(self, *a, **k)
        clk.n_scan += 1
        now[0] += (clk.scan_ms + clk.scan_extra.get(clk.n_scan, 0.0)) * 1e-3
        gc_in("scan", clk.n_scan)
        return out

    def pick(self, *a, **k):
        clk.ranked.append([int(r) for r in a[6][:16]])
        clk.at[-1]["pick"] = ms()
        return pick0(self, *a, **k)

    def score(self, *a, **k):
        now[0] += score_ms * 1e-3
        return score0(self, *a, **k)

    def robust(*a):
        now[0] += robust_ms * 1e-3
        return rob0(*a)

    def tick(self, *a, **k):
        clk.t0, clk.n_tail, clk.n_esc, clk.n_hb, clk.n_hbu, clk.n_scan = now[0], 0, 0, 0, 0, 0
        clk.at.append({})
        out = tick0(self, *a, **k)
        clk.at[-1]["end"] = ms()
        return out

    monkeypatch.setattr(fp.ForumPlanner, "_escape_fail_v2", esc)
    monkeypatch.setattr(fp.ForumPlanner, "_hit_branch", hb)
    monkeypatch.setattr(fp.ForumPlanner, "_tail_pick", tail)
    monkeypatch.setattr(fp.ForumPlanner, "_escape_pick", pick)
    monkeypatch.setattr(fp.ForumPlanner, "_score_forum", score)
    monkeypatch.setattr(fp.ForumPlanner, "_ordinary_tick", tick)
    monkeypatch.setattr(fp.ForumPlanner, "_stay_scan", scan)
    monkeypatch.setattr(fp, "_down_robust", robust)
    monkeypatch.setattr(fp, "_gc_runs", lambda: clk.gc)
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    return clk


def _credit(monkeypatch):
    """Sol's counterexample (seq 281): the over_stay scan's candidates replaced by rows, each credited 30 (state.rows set by
    the test; None: the scan's own)."""
    from ssbot.combat import forum_planner as fp
    st, orig = NS(rows=None), fp.ForumPlanner._stay_scan

    def scan(self, sc, roll, start, prefs, sp_):
        out = orig(self, sc, roll, start, prefs, sp_)
        if st.rows is not None:
            n = len(sc["J"])
            m = np.zeros(n, bool)
            m[list(st.rows)] = True
            out = dict(out, stay_pogo=m, J_stay=np.where(m, 30.0, 0.0), inflight_down=np.zeros(n, bool))
        return out

    monkeypatch.setattr(fp.ForumPlanner, "_stay_scan", scan)
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
    # the promotion's own names never shadow the tick's (its debug record keeps the rows' known mask)
    for key in ("known", "ok", "J", "t_hit"):
        assert np.array_equal(np.asarray(pl0.last_info["dbg"][key]), np.asarray(pl1.last_info["dbg"][key])), key


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
    # meet the body at frame 5 on every row that keeps the swing - kept apart in the scan (stay_ff ...), which runs after the
    # tick's choice and never touches the scorer's result; a dash ends it. The old live failure (#280: the swing pressed at
    # 4838 dropped at 4841 for a dash) is this case
    seen = _scores(monkeypatch)
    x0 = RX + side * 0.9
    pl1, r1 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), swing_age=3)
    names, sc = _rows_of(seen, pl1)
    scn = pl1.last_sel["stay"]                         # the promotion's own scan
    k = "L" if side < 0 else "R"
    move, wait = names.index(f"MOVE({k})+idle"), names.index("WAIT+idle")
    dash = next(i for i, n in enumerate(names) if str(n).startswith(f"DASH({k})"))
    assert scn["inflight_down"][move] and scn["stay_fk"][move] == 4 and scn["stay_ff"][move] == 5
    assert not scn["inflight_down"][dash] and scn["stay_ff"][dash] != 5
    safe = pl1.last_sel["safe"]
    assert safe[move] and not safe[wait]               # straight down onto the body: unsafe on its miss branch
    assert scn["stay_pogo"][wait] and pl1.last_info["stay_pogo"]["safe"] < pl1.last_info["stay_pogo"]["rows"]
    seen.clear()
    pl0, r0 = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(False), swing_age=3)
    _, sc0 = _rows_of(seen, pl0)
    assert not {k_ for k_ in sc if k_.startswith(("stay", "inflight", "J_stay"))}    # the scorer has no stay outputs
    for key in ("first_f", "first_t", "first_k", "first_face", "J", "nh"):
        assert np.array_equal(sc[key], sc0[key]), key  # the scorer's own outputs as without the preference
    # the choice itself keeps the swing (a credited row): nothing to promote, the same send
    assert r1.name == r0.name == f"MOVE({k})+idle" and r1.J == pytest.approx(r0.J) and not r1.S
    assert pl1.last_info["stay_pogo"]["chosen"] and not pl1.last_info["stay_pogo"]["promoted"]
    # the same swing 8 frames old: one active frame left (frame 1, still 1.5 u above), so no row is credited a contact the
    # finished swing would have made later
    seen.clear()
    pl8, _ = _tick(wparams, warena, monkeypatch, x0, 1.5, -6.0, _prefs(True), swing_age=8)
    assert not _scan(pl8, seen)["inflight_down"].any()
    # a dash inside the swing's window ends it: 1.6 u off its edge, 0.6 u above its top, the swing 4 frames old (frames 1-5
    # left), the dash toward it starts on frame 3 and passes over it at the blade's height - no contact is credited to it
    seen.clear()
    to = "R" if side < 0 else "L"
    pld, _ = _tick(wparams, warena, monkeypatch, RX + side * (0.5 + 1.6), 0.6, -2.0, _prefs(True), swing_age=4)
    nd = pld.last_info["dbg"]["names"]
    md = np.asarray(pld.last_info["dbg"]["mode"])
    dashes = [i for i, n in enumerate(nd) if str(n).startswith(f"DASH({to})")]
    from ssbot.combat import forum_planner as fp
    assert dashes and (md[dashes, 3] == fp.M_DASH).all()
    assert not _scan(pld, seen)["inflight_down"][dashes].any()


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
    scn = pl1.last_sel["stay"]
    from ssbot.combat import forum_planner as fp
    away, to = ("R", "L") if side > 0 else ("L", "R")
    edge = names.index(f"ATTACK(down){away}+run{to}8_stop")
    assert sc["first_k"][edge] == fp.K_DOWN and sc["first_f"][edge] >= 0
    assert scn["stay_edge"][edge] and not scn["stay_pogo"][edge]
    assert edge not in pl1.last_info["stay_pogo"].get("cands", [])
    turn = names.index(f"ATTACK(down){to}+idle")
    assert scn["stay_pogo"][turn] and not scn["stay_edge"][turn]
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
    # the credited rows ahead of it (0-3), which that pick failed - read from its result alone (esc_known: the check keeps no
    # record of its own, Sol seq 282) - and changes nothing
    from ssbot.combat import forum_planner as fp
    pl = ForumPlanner(wparams, warena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True), crest="Wanderer")
    calls = []
    passing = [{4}]

    def fail_v2(f, r1, hold_end, rows):
        calls.append([int(r) for r in rows])
        return np.asarray([0 if int(r) in passing[0] else 1 for r in rows]), [[] for _ in rows]

    pl._escape_fail_v2 = fail_v2
    got = pl._escape_pick(None, None, None, None, None, None, np.arange(25), (0.0, 0.0), 16, None, v2=True)
    assert got[:3] == (4, 0, 8) and calls == [[0, 1, 2, 3], [4, 5, 6, 7]]
    known = fp.esc_known(np.arange(25), got[0], got[1], got[2], 16)
    assert known == [0, 1, 2, 3]                                          # 5-7 were checked too, but not taken: unknown
    esc = lambda rows: np.asarray([-1 if int(r) in known else 0 for r in rows])
    assert fp.stay_promote(np.arange(4), esc, lambda r: True) == (None, [(0, -1, None), (1, -1, None), (2, -1, None),
                                                                        (3, -1, None)])   # row 4 stands
    # nothing passes: the fewest failures, the first (row 0); every row of the window checked failed
    passing[0] = set()
    got = pl._escape_pick(None, None, None, None, None, None, np.arange(25), (0.0, 0.0), 16, None, v2=True)
    assert got[:3] == (0, 1, 16) and fp.esc_known(np.arange(25), *got[:3], 16) == list(range(16))
    # the deadline stopped it after one batch, or it took a row of a later pass (ESC_MORE): only what it read; none taken
    assert fp.esc_known(np.arange(25), 0, 1, 4, 16) == [0, 1, 2, 3]
    assert fp.esc_known(np.arange(25), 20, 0, 20, 16) == list(range(16))
    assert fp.esc_known(np.arange(25), None, 0, 0, 16) == [] and fp.esc_known(np.arange(25), 3, 0, 0, 16) == []


def test_the_promotions_cost_estimate_rises_at_once_and_falls_by_halves():
    from ssbot.combat.forum_planner import stay_cost
    assert stay_cost(0.003, 0.010) == pytest.approx(0.010)               # a slower check: its own cost at once
    assert stay_cost(0.010, 0.002) == pytest.approx(0.006)               # a faster one: half way down
    assert stay_cost(0.003, 0.003) == pytest.approx(0.003)


def _same_send(pl0, r0, pl1, r1):
    """The two arms send the same row with the same safety verdict, tail, escape record (its ms aside: the real clock unless a
    cost clock runs) and hand-back to the next tick."""
    assert (r1.name, r1.idx, r1.mask, r1.S, r1.J, r1.tail_ok) == (r0.name, r0.idx, r0.mask, r0.S, r0.J, r0.tail_ok)
    no_ms = lambda e: {k: v for k, v in (e or {}).items() if k != "ms"}
    assert np.array_equal(r1.cmd, r0.cmd) and no_ms(pl1.last_info["esc"]) == no_ms(pl0.last_info["esc"])
    assert np.array_equal(pl1.prev_cmd, pl0.prev_cmd)
    assert (pl1.prev_tail_ok, pl1.prev_esc_unsafe, pl1.macro_until) == (pl0.prev_tail_ok, pl0.prev_esc_unsafe, pl0.macro_until)


@pytest.mark.parametrize("case", ["fifth_reached", "fifth_cut", "higher_fail", "higher_pass", "known_reuse"])
def test_sols_counterexample_in_a_whole_tick_under_the_real_deadlines(wparams, warena, monkeypatch, case):
    # (Sol seq 281) the scan's candidates put where the case needs them in the tick's own escape order (ranked), the escape
    # check passing only the given rows, the production deadlines on the cost clock:
    #   fifth_reached  ranked[0:5] credited, only the fifth passes, two 1.4 ms batches in time: the tick's own pick is it,
    #                  credited itself, so nothing is promoted
    #   fifth_cut      the same with 6 ms batches - the deadline stops the check after the first: the tick's own fallback (the
    #                  fewest failures, first in its order, S = 1); no time is left for the promotion's scan
    #   higher_fail    ranked[8:12] credited, ahead of the choice (ranked[1]) in the credited order: all fail, the choice stands
    #   higher_pass    one of them passes: taken, by the promotion's own batch and tail check after the tick's own checks
    #   known_reuse    ranked[0] and [2] credited, ranked[1] and [2] pass: the tick's check failed ranked[0] (read from its
    #                  result, -1), so only ranked[2] is checked anew, and taken
    # every case: the same envelope, order and window, and the tick's own checks the same calls in the same order
    clk = _cost_clock(monkeypatch, {"fifth_reached": 1.4, "fifth_cut": 6.0}.get(case, 2.0), 0.5, 1.0)
    cred = _credit(monkeypatch)
    pl, _ = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **REAL)
    rk = clk.ranked[-1]
    cred.rows, clk.passing = {"higher_fail": (rk[8:12], {rk[1]}), "higher_pass": (rk[8:12], {rk[1], rk[9]}),
                              "known_reuse": ([rk[0], rk[2]], {rk[1], rk[2]})}.get(case, (rk[0:5], {rk[4]}))
    clk.log.clear()
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **REAL)
    log0 = list(clk.log)
    clk.log.clear()
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), **REAL)
    assert clk.ranked[-1] == clk.ranked[-2] == rk and clk.log[:len(log0)] == log0
    more, sp = clk.log[len(log0):], pl1.last_info["stay_pogo"]
    if case in ("higher_pass", "known_reuse"):
        new = rk[9] if case == "higher_pass" else rk[2]
        assert sp["promoted"] and r1.idx == new and not r1.S and r1.J == pytest.approx(r0.J) and r0.idx == rk[1]
        if case == "higher_pass":
            assert more == [("esc", rk[8:12]), ("tail", [rk[9]])]
        else:
            assert more == [("esc", [rk[2]]), ("tail", [rk[2]])] and sp["checked"] == [(rk[0], -1, None), (rk[2], 0, True)]
        return
    _same_send(pl0, r0, pl1, r1)
    assert not sp["promoted"]
    if case == "fifth_reached":
        assert r0.idx == rk[4] and not r0.S and log0 == [("esc", rk[0:4]), ("esc", rk[4:8]), ("tail", [rk[4]])]
        assert sp["orig"] == r0.idx and sp["safe"] == 5 and "cands" not in sp and more == []   # the choice is credited
    elif case == "fifth_cut":
        assert r0.idx == rk[0] and r0.S and log0 == [("esc", rk[0:4]), ("tail", [rk[0]])]
        assert sp["cut"] == "scan" and "rows" not in sp and more == []
    else:
        assert r0.idx == rk[1] and more == [("esc", rk[8:12])] and all(n == 1 for _, n, _ in sp["checked"])


@pytest.mark.parametrize("case", ["time_left", "no_time_for_its_scan", "no_time_for_its_escape_batch",
                                  "no_time_for_its_tail_check", "swing_in_time", "no_time_for_the_swing_branch"])
def test_under_the_real_deadlines_the_promotion_takes_only_the_time_left(wparams, warena, monkeypatch, case):
    # the real candidates (the plain fixture; the swing cases: pressed a frame before, the stance 7 u away) under the
    # production deadlines on the cost clock: the tick's own checks run first, exactly as without the preference; the
    # promotion's scan, swing recheck, escape batch and tail check each start only if their estimates end before the escape
    # deadline (the scan: with a tail check; a recheck or batch: with a tail check), and one that would not leaves the
    # choice, its verdict, tail and hand-back as made. The tail estimate is measured on the tick's own tail check (seq 283),
    # the batch is the tick's own 2.5 ms estimate: original tail 3.5 ms (ends at 6.5 ms) no time to scan (0.5 + 3.5);
    # 3 ms: scanned, then no time for the batch (2.5 + 3); the promotion's batch 3 ms slower than its estimate: no time for
    # its tail; original tail 2.2 ms: no time for the recheck (3 + 2.35)
    esc_ms, tail_ms, extra = {"time_left": (2.0, 1.0, None), "no_time_for_its_scan": (2.0, 3.5, None),
                              "no_time_for_its_escape_batch": (2.0, 3.0, None), "no_time_for_its_tail_check": (2.0, 1.0, {2: 3.0}),
                              "swing_in_time": (2.0, 1.0, None), "no_time_for_the_swing_branch": (2.0, 2.2, None)}[case]
    clk = _cost_clock(monkeypatch, esc_ms, 0.5, tail_ms, esc_extra=extra)
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
    if case in ("time_left", "swing_in_time"):
        cands = sp["cands"]
        assert sp["promoted"] and not r1.S and r1.J == pytest.approx(r0.J)
        assert r1.name == ("MOVE(L)+upatk2L" if swing else "ATTACK(down)L+idle")
        head = [("hb", more[0][1])] if swing else []
        assert more == head + [("esc", cands), ("tail", [r1.idx])]
        if swing:
            assert sp["inflight_unsafe"] == [] and set(more[0][1]) <= set(cands)
        return
    assert not sp["promoted"]
    _same_send(pl0, r0, pl1, r1)
    if case == "no_time_for_its_scan":
        assert sp["cut"] == "scan" and more == [] and "rows" not in sp
    elif case == "no_time_for_its_escape_batch":
        assert sp["cut"] == "escape" and more == [] and all(n is None for _, n, _ in sp["checked"]) and sp["safe"] > 0
    elif case == "no_time_for_its_tail_check":
        assert sp["cut"] == "tail" and more == [("esc", sp["cands"])]
        assert all(n == 0 and t is False for _, n, t in sp["checked"])
    else:
        assert sp["inflight_cut"] and sp["cands"] == [] and more == [] and "inflight_unsafe" not in sp


def test_sols_scan_counterexample_the_tick_keeps_its_own_escape_budget(wparams, warena, monkeypatch):
    # Sol seq 282 item 1: the scorer 5.9 ms, hit branches 0.5, escape batches 2, tail checks 1, and the over_stay contact
    # kernel (_down_robust) 0.2 ms more with the preference on. The scan runs only after the tick's own checks, so both arms
    # enter the escape check at 6.9 ms, check the same four rows and pass row 21 (S = 0); the promotion then has no time left
    clk = _cost_clock(monkeypatch, 2.0, 0.5, 1.0, score_ms=5.9, robust_ms=0.2)
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **REAL)
    log0, at0 = list(clk.log), clk.at[-1]
    clk.log.clear()
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), **REAL)
    assert at0["pick"] == clk.at[-1]["pick"] == pytest.approx(6.9) and clk.log == log0 == [("esc", [21, 34, 84, 93]),
                                                                                          ("tail", [21])]
    assert r0.name == "MOVE(L)+idle" and r0.idx == 21 and not r0.S
    esc0 = pl0.last_info["esc"]
    assert (esc0["checked"], esc0["fail"], esc0["cut"], esc0["unsafe"]) == (4, 0, False, False)
    _same_send(pl0, r0, pl1, r1)
    assert pl1.last_info["stay_pogo"]["cut"] == "scan" and not pl1.last_info["stay_pogo"]["promoted"]


def test_sols_late_check_counterexample_changes_nothing(wparams, warena, monkeypatch):
    # Sol seq 282 item 2: the same costs, the promotion's tail check (the tick's second) 12 ms slower and passing. Off: the
    # tick ends at 4 ms with row 21 (mask 1048576). On: the check started in time, ended at 19 ms, past the 10 ms deadline -
    # its pass is not taken: row 21, its verdict, tail, escape record and hand-back exactly as off
    clk = _cost_clock(monkeypatch, 2.0, 0.5, 1.0, tail_extra={2: 12.0})
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **REAL)
    log0, at0 = list(clk.log), clk.at[-1]
    clk.log.clear()
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), **REAL)
    assert at0["end"] == pytest.approx(4.0) and (r0.idx, r0.name, r0.mask) == (21, "MOVE(L)+idle", 1048576)
    sp = pl1.last_info["stay_pogo"]
    assert clk.at[-1]["end"] == pytest.approx(19.0) and clk.log[len(log0):] == [("esc", sp["cands"]), ("tail", [399])]
    assert sp["cut"] == "final" and sp["checked"] == [(399, 0, True)] and not sp["promoted"]
    _same_send(pl0, r0, pl1, r1)
    assert "promoted_from" not in pl1.last_info["esc"]


@pytest.mark.parametrize("tail_ms, collected", [(1.0, False), (4.0, False), (4.0, True), (1.0, True)])
def test_the_tail_estimate_is_measured_on_the_ticks_own_tail_check(wparams, warena, monkeypatch, tail_ms, collected):
    # Task 182 seq 283: the promotion's tail-check estimate is measured on the tick's own tail check too (two clock reads round
    # it, after its result), the stage on or not: a 1 ms check takes the 2.5 ms seed half way down, a 4 ms one up at once.
    # Seq 284: with a garbage collection inside the check the 4 ms one raises nothing (the 1 ms one still lowers it)
    from ssbot.combat.forum_planner import stay_cost
    clk = _cost_clock(monkeypatch, 2.0, 0.5, tail_ms)
    clk.gc_calls = {("tail", 1)} if collected else set()
    pl, r = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **REAL)
    assert (r.idx, r.tail_ok) == (21, True) and pl.last_info.get("stay_pogo") is None and clk.gc == int(collected)
    assert pl.stay_tail_s == pytest.approx(0.0025 if (collected and tail_ms > 2.5) else stay_cost(0.0025, tail_ms * 1e-3))


SEEDS_353 = dict(stay_scan_s=0.002, stay_esc_s=0.003, stay_tail_s=0.0025)        # 48351df9's fixed estimates


@pytest.mark.parametrize("case", ["measured", "seeds_353", "tail_unmeasured", "esc_floor_353", "own_batch_slower"])
def test_sols_formal_budget_the_promotion_runs_in_the_time_the_tick_leaves(wparams, warena, monkeypatch, case):
    # Task 182 seq 283 (Sol, the formal #353 run: Q2 f4827 / f4828 and Q5 f4860 cut at the scan, 1.5-2 ms left there): the
    # tick's own checks end late - the escape check entered at 7.7 ms, a 0.3 ms batch, a 0.4 ms tail check: 1.6 ms left - and
    # the promotion's steps are short (offline on E16-23: scan 0.06-0.14 ms, an escape batch 0.46-0.67, a tail check
    # 0.66-0.83; Sol's formal P about half). Estimates as measured on earlier ticks (the tick's own batches 0.3 ms, its tail
    # checks 0.45 ms, then this tick's 0.4: 0.425; the scan never run: its 0.5 ms seed): the scan, a batch and a tail check
    # fit - promoted by 9.1 ms, the record keeping the time left and the estimates. 48351df9's fixed estimates (scan 2,
    # escape 3, tail 2.5 ms): cut at the scan (the formal result). The tail measured only on this tick's check (1.45 ms): cut
    # at the scan; the old 3 ms escape floor, or the promotion's own earlier batch at 5 ms: scanned, cut at the batch
    clk = _cost_clock(monkeypatch, 0.3, 0.5, 0.4, score_ms=6.7)
    meas = dict(esc_batch_s=0.0003, stay_tail_s=0.00045)
    est = {"measured": meas, "seeds_353": dict(esc_batch_s=0.0003, **SEEDS_353), "tail_unmeasured": dict(esc_batch_s=0.0003),
           "esc_floor_353": dict(meas, stay_esc_s=0.003), "own_batch_slower": dict(meas, stay_esc_s=0.005)}[case]
    warm = lambda pl, args: [setattr(pl, k, v) for k, v in est.items()]
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), pre=warm, **REAL)
    log0, at0 = list(clk.log), clk.at[-1]
    clk.log.clear()
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), pre=warm, **REAL)
    assert at0["pick"] == clk.at[-1]["pick"] == pytest.approx(7.7) and at0["end"] == pytest.approx(8.4)
    assert clk.log[:len(log0)] == log0 == [("esc", [21, 34, 84, 93]), ("tail", [21])] and r0.idx == 21
    sp = pl1.last_info["stay_pogo"]
    assert sp["left"] == pytest.approx(1.6)
    assert sp["est"] == pytest.approx({"measured": [0.5, 0.3, 0.425], "seeds_353": [2.0, 3.0, 1.45],
                                       "tail_unmeasured": [0.5, 0.3, 1.45], "esc_floor_353": [0.5, 3.0, 0.425],
                                       "own_batch_slower": [0.5, 5.0, 0.425]}[case])
    if case == "measured":
        assert sp["promoted"] and r1.idx == 399 and not r1.S and r1.tail_ok is True and r1.J == pytest.approx(r0.J)
        assert clk.log[len(log0):] == [("esc", sp["cands"]), ("tail", [399])] and clk.at[-1]["end"] == pytest.approx(9.1)
        assert sp["checked"] == [(399, 0, True)] and pl1.stay_esc_s == pytest.approx(0.0003)
        return
    _same_send(pl0, r0, pl1, r1)
    assert not sp["promoted"] and clk.log[len(log0):] == []
    cut = {"seeds_353": "scan", "tail_unmeasured": "scan", "esc_floor_353": "escape", "own_batch_slower": "escape"}[case]
    assert sp["cut"] == cut and (("rows" in sp) == (cut == "escape"))


def test_the_collection_count_is_the_process_own():
    # Task 182 seq 284: forum_planner._gc_runs counts every garbage collection this process runs (gc.get_stats; no clock read,
    # no callback), so a change across a measured call means one ran in it
    import gc
    from ssbot.combat import forum_planner as fp
    n0 = fp._gc_runs()
    gc.collect(0)
    assert fp._gc_runs() >= n0 + 1


def test_a_collection_inside_a_call_never_raises_its_estimate():
    # Task 182 seq 284 (Sol: a 2.45 ms gen-0 collection inside the f4827 scan raised the next tick's scan estimate past its
    # time): a call a garbage collection ran in can only lower an estimate; without one a slower call raises it at once
    from ssbot.combat.forum_planner import stay_cost
    assert stay_cost(0.00005, 0.0025, gc_ran=True) == pytest.approx(0.00005)
    assert stay_cost(0.003, 0.001, gc_ran=True) == pytest.approx(0.002)
    assert stay_cost(0.00005, 0.0025) == pytest.approx(0.0025)


MEAS = dict(esc_batch_s=0.0003, stay_tail_s=0.00045, stay_scan_s=0.00005)      # as measured on earlier ticks (formal P sized)


@pytest.mark.parametrize("case", ["gc_once", "pause_once", "slow_twice", "gc_twice"])
def test_sols_q2_pause_the_next_tick_recovers_repeated_slowness_is_refused(wparams, warena, monkeypatch, case):
    # Task 182 seq 284 (Sol: the formal Q2 f4827 / f4828): two consecutive ticks of one planner on the formal budget of the test
    # above (the escape check in at 7.7 ms, 1.6 ms left; the estimates as measured: batch 0.3, tail 0.45, scan 0.05 ms). The
    # first tick's scan takes 2.45 ms more: it starts in time, then no time is left for the escape batch - cut, the choice (row
    # 21) sent as made, as with the preference off. With a garbage collection counted in that scan (Sol's event) the scan's
    # estimate stays 0.05 ms and the second tick, with no pause, scans and promotes. The same pause without a collection (a
    # pause of another cause or real slowness) raises it at once to 2.5 ms: the second tick does not even scan - and repeated
    # (slow again), it is refused before it starts. A collection at both ticks: each falls back in turn, nothing taken late
    clk = _cost_clock(monkeypatch, 0.3, 0.5, 0.4, score_ms=6.7, scan_ms=0.05)
    first = {}

    def two(pl, args):
        for k, v in MEAS.items():
            setattr(pl, k, v)
        clk.scan_extra = {1: 2.45}
        clk.gc_calls = {("scan", 1)} if case.startswith("gc") else set()
        r_a = pl.tick(*args)
        first.update(r=r_a, sp=dict(pl.last_info["stay_pogo"]), scan_est=pl.stay_scan_s, end=clk.at[-1]["end"],
                     esc=dict(pl.last_info["esc"]))
        clk.scan_extra = {1: 2.45} if case in ("slow_twice", "gc_twice") else {}
        clk.gc_calls = {("scan", 1)} if case == "gc_twice" else set()

    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False),
                    pre=lambda pl, a: [setattr(pl, k, v) for k, v in MEAS.items()], **REAL)
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), pre=two, **REAL)
    sp_a, sp_b = first["sp"], pl1.last_info["stay_pogo"]
    # the paused tick: scanned in time, cut before the batch, the tick's own send and escape record
    assert sp_a["left"] == pytest.approx(1.6) and sp_a["cut"] == "escape" and not sp_a["promoted"]
    assert (first["r"].idx, first["r"].mask, first["r"].S) == (r0.idx, r0.mask, r0.S) == (21, 1048576, 0)
    assert {k: v for k, v in first["esc"].items() if k != "ms"} == {k: v for k, v in pl0.last_info["esc"].items() if k != "ms"}
    assert first["end"] == pytest.approx(8.4 + 0.05 + 2.45) and sp_a.get("gc") == (["scan"] if case.startswith("gc") else None)
    assert first["scan_est"] == pytest.approx(0.00005 if case.startswith("gc") else 0.0025)
    if case == "gc_once":
        assert sp_b["promoted"] and r1.name.startswith("ATTACK(down)") and not r1.S and sp_b["est"][0] == pytest.approx(0.05)
        assert clk.at[-1]["end"] <= 10.0
    elif case == "gc_twice":
        assert not sp_b["promoted"] and sp_b["cut"] == "escape" and sp_b["gc"] == ["scan"] and r1.idx == sp_b["orig"]
    else:
        assert not sp_b["promoted"] and sp_b["cut"] == "scan" and sp_b["est"][0] == pytest.approx(2.5) and "rows" not in sp_b


@pytest.mark.parametrize("step", ["escape", "tail", "swing"])
def test_a_collection_inside_a_promotion_step_raises_nothing(wparams, warena, monkeypatch, step):
    # Task 182 seq 284: the promotion's escape batch and tail check (the formal budget, both 0.2 ms slower than their
    # estimates) and a swing's hit branch (test_under_the_real_deadlines' swing case, its estimate 0.1 ms, the call 0.5 ms):
    # each measured with a garbage collection inside keeps its estimate (and the record names the step); without one, the
    # slower call raises it at once. The promotion itself is taken either way (its deadline checks unchanged)
    def run(collect):
        if step == "swing":
            clk = _cost_clock(monkeypatch, 2.0, 0.5, 1.0)
            clk.gc_calls = {("hbu", 1)} if collect else set()
            pre = lambda pl, a: setattr(pl, "stay_hb_s", 0.0001)
            pl, r = _tick(wparams, warena, monkeypatch, RX - 1.2, 1.5, -6.0, _prefs(True, stance=RX - 7.0), swing_age=1,
                          pre=pre, **REAL)
            return pl, r, pl.stay_hb_s
        clk = _cost_clock(monkeypatch, 0.3, 0.5, 0.4, score_ms=6.7, esc_extra={2: 0.2}, tail_extra={2: 0.2})
        clk.gc_calls = {("esc" if step == "escape" else "tail", 2)} if collect else set()
        pl, r = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True),
                      pre=lambda pl, a: [setattr(pl, k, v) for k, v in MEAS.items()], **REAL)
        return pl, r, (pl.stay_esc_s if step == "escape" else pl.stay_tail_s)

    pl_c, r_c, est_c = run(True)
    pl_n, r_n, est_n = run(False)
    assert pl_c.last_info["stay_pogo"]["promoted"] and pl_n.last_info["stay_pogo"]["promoted"] and r_c.idx == r_n.idx
    assert pl_c.last_info["stay_pogo"]["gc"] == [{"swing": "hb"}.get(step, step)] and "gc" not in pl_n.last_info["stay_pogo"]
    before = {"escape": 0.0, "tail": 0.000425, "swing": 0.0001}[step]          # (tail: after the tick's own 0.4 ms check)
    took = {"escape": 0.0005, "tail": 0.0006, "swing": 0.0005}[step]
    assert est_c == pytest.approx(before) and est_n == pytest.approx(took)


def test_a_promoted_send_carries_its_own_escape_record(wparams, warena, monkeypatch):
    # the formal measurement reads the final row's escape from last_info["esc"] (train.measurement.escape_evidence): after a
    # promotion it is the promoted row's (its row, no failure, the candidates checked), the choice's in promoted_from
    from ssbot.train.measurement import escape_evidence
    _cost_clock(monkeypatch, 2.0, 0.5, 1.0)
    on = lambda pl, args: setattr(pl, "measurement_enabled", True)
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), pre=on, **REAL)
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), pre=on, **REAL)
    assert pl1.last_info["stay_pogo"]["promoted"] and r1.idx == 399 and r0.idx == 21
    ev0, ev1 = escape_evidence(pl0.last_info, r0.idx), escape_evidence(pl1.last_info, r1.idx)
    assert (ev0["status"], ev0["checked_row"]) == ("pass", 21) and (ev1["status"], ev1["checked_row"]) == ("pass", 399)
    pf = pl1.last_info["esc"]["promoted_from"]
    assert (pf["row"], pf["fail"], pf["checked"], pf["unsafe"], pf["tail_ok"]) == (21, 0, 4, False, True)
    assert {k: v for k, v in pf.items() if k not in ("tail_ok",)} == {**pl0.last_info["esc"], "unsafe": False}
    assert r1.tail_ok is True and escape_evidence(pl1.last_info, r0.idx)["status"] == "unchecked"


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
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(False), **kw)
    pl, r = _tick(wparams, warena, monkeypatch, RX - 0.9, 1.5, -6.0, _prefs(True), **kw)
    _same_send(pl0, r0, pl, r)
    assert r.S
    sp = pl.last_info["stay_pogo"]
    assert not sp["promoted"]
    if case == "no_time":
        assert sp["cut"] == "scan" and "rows" not in sp                 # past the deadline: not even the scan
    else:
        assert sp["safe"] > 0 and sp["checked"] and all(n > 0 for _, n, _ in sp["checked"])


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
    # no safe row: FORCED_RISK as without the preference, and the promotion does not even scan
    seen = _scores(monkeypatch)
    pl0, r0 = _tick(wparams, warena, monkeypatch, RX - 0.9, 0.6, 0.0, _prefs(False))
    pl1, r1 = _tick(wparams, warena, monkeypatch, RX - 0.9, 0.6, 0.0, _prefs(True))
    assert r0.forced_risk and r1.forced_risk
    _same_send(pl0, r0, pl1, r1)
    sp = pl1.last_info["stay_pogo"]
    assert sp["skip"] == "forced" and "rows" not in sp and not sp["chosen"] and not sp["promoted"]
    assert pl1.last_sel["stay"] is None
    scn = _scan(pl1, seen)                              # (its down slashes, scanned here: in contact on a branch, none safe)
    assert scn["stay_pogo"].any() and not (scn["stay_pogo"] & pl1.last_sel["safe"]).any()


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
