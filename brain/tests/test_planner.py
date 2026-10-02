"""Planner, safety filter, tactics and their compiled parts (ssbot.combat, M2 W4): the hold filter and the parallel
support query bit for bit against their references, the candidate vocabulary, the L0 rules, and planner ticks on a
synthetic Bone_05 arena against a charge, against nothing, and inside an unavoidable attack (FORCED_RISK)."""
import numpy as np
import pytest

from ssbot.combat import candidates as cmod
from ssbot.combat.boss_model import BossModel
from ssbot.combat.fastquery import query_par
from ssbot.combat.forecast import BIN, Ctx, Forecaster, Root, load_planner_templates
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.planner import Planner, PlannerConfig
from ssbot.combat.safety_filter import R_ALLOW, R_BIND, R_SILK, FilterContext, hazard_flags, unpausable, veto
from ssbot.combat.tactics import EVADE, HEAL, HOLD, Tactics, load_playbook
from ssbot.core.primitives import N_PRIM, EVASIVE, Prim
from ssbot.core.worldstate import ORACLE, E, Gate, WorldState
from ssbot.knowledge import kinematics as kin

MARGIN = (0.15, 0.25)


@pytest.fixture(scope="module")
def model():
    return BossModel.load()


@pytest.fixture(scope="module")
def tpls(model):
    return load_planner_templates(model, MARGIN)


@pytest.fixture(scope="module")
def params():
    return kin.HeroParams.load()


@pytest.fixture(scope="module")
def arena():
    return kin.Terrain2D.from_boxes([(60.0, 0.0, 110.0, 2.0), (67.2, 0.0, 69.2, 14.0), (102.0, 0.0, 104.0, 14.0)])


def fc_with(model, tpls, roots):
    fc = Forecaster(model, ORACLE, margin=MARGIN, templates=tpls)
    fc.tracker.roots = lambda origin: (roots, True)
    return fc


def world(x: float, hp: int = 5, silk: int = 5, gates: bool = False) -> WorldState:
    ws = WorldState()
    ws.hero.pos = E((x, 3.0544))
    ws.res.hp, ws.res.hp_max, ws.res.silk = E(hp), E(5), E(silk)
    if gates:
        ws.terrain.gates = [Gate("Gate L", True, (67.2, 0.0, 69.2, 14.0)), Gate("Gate R", True, (102.0, 0.0, 104.0,
                                                                                                  14.0))]
    return ws


def test_hold_filter_matches_the_reference():
    rng = np.random.default_rng(3)
    bits = [kin.B_JUMP, kin.B_ATTACK, kin.B_BIND, kin.B_QUICKCAST, kin.B_UP, kin.B_DOWN, kin.B_LEFT, kin.B_RIGHT]
    for trial in range(12):
        m = np.zeros((70, 40), np.int64)
        for b in bits:
            m |= np.where(rng.random(m.shape) < rng.uniform(0.05, 0.6), b, 0)
        st = kin.HoldState.idle(1) if trial % 2 == 0 else kin.hold_filter(m[:1, :9])[1]
        a, sa = kin.hold_filter(m, st)
        b2, sb = hold_filter_jit(m, st)
        assert (a == b2).all()
        for x, y in zip((sa.latched, sa.desired, sa.pending, sa.age), (sb.latched, sb.desired, sb.pending, sb.age)):
            assert (np.asarray(x) == np.asarray(y)).all()


def test_parallel_query_matches_support_query(model, tpls):
    fc = fc_with(model, tpls, [Root("Submerged", -0.6, -0.6, Ctx(phase="P2", raged=True, hp=50.0))])
    f = fc.forecast(3.0, 0.0)
    rng = np.random.default_rng(1)
    tk = np.arange(49) * BIN + 0.9
    x, y = rng.uniform(70, 101, (300, 49)), rng.uniform(2, 12, (300, 49))
    q = f._query(f.placements)
    a = q.query(x, y, tk)
    assert (a == query_par(q, x, y, tk)).all() and 0.02 < a.mean() < 0.9


def test_candidate_vocabulary():
    cs = cmod.build(48)
    assert len(cs.cmd) == len(cs.first_names) * len(cs.cont_names) <= 512
    up_down = (cs.cmd & (kin.B_UP | kin.B_DOWN)) != 0
    side = (cs.cmd & (kin.B_LEFT | kin.B_RIGHT)) != 0
    assert not (up_down & ~side).any()                       # never an up / down edge without a side key
    assert not ((cs.cmd & kin.B_LEFT) & (cs.cmd & kin.B_RIGHT)).any()
    att = (cs.cmd & kin.B_ATTACK) != 0
    runs = np.diff(np.concatenate([np.zeros((len(att), 1), bool), att, np.zeros((len(att), 1), bool)], axis=1)
                   .astype(np.int8), axis=1)
    assert (np.argwhere(runs == -1)[:, 1] - np.argwhere(runs == 1)[:, 1]).max() <= cmod.PRESS   # no nail-art charge
    allowed = np.zeros(N_PRIM, bool)
    allowed[[int(p) for p in EVASIVE]] = True
    ok = cs.allowed(allowed)
    names = [cs.name(i) for i in np.flatnonzero(ok)]
    assert ok.any() and not any("ATTACK" in n or "SILK" in n or "attack" in n for n in names)
    nc = cmod.no_control(cs)
    assert len(nc.cmd) == len(cmod.NO_CONTROL_FIRST) * len(cs.cont_names)
    prev = cs.cmd[5]
    cont = cmod.continue_plan(prev, 1, 48)
    assert (cont[:47] == prev[1:]).all() and cont[47] == prev[47] & (kin.B_LEFT | kin.B_RIGHT)


def test_safety_filter_rules():
    cs = cmod.build(48)
    allowed = np.ones(N_PRIM, bool)
    ctx = FilterContext(allowed_mask=allowed, hp=4, max_hp=5, silk=9, h=2, tier="YELLOW")
    ok, why = veto(cs, ctx)
    spear = (cs.prim_bits & (1 << int(Prim.SILKSKILL))) != 0
    assert (why[spear] == R_SILK).all() and not ok[spear].any()          # below full HP: no silk skill
    ctx = FilterContext(allowed_mask=allowed, hp=5, max_hp=5, silk=4, h=3, tier="GREEN")
    ok, _ = veto(cs, ctx)
    assert ok[spear].all()
    pend = np.zeros(N_PRIM, bool)
    pend[[int(p) for p in EVASIVE]] = True
    ok, why = veto(cs, FilterContext(allowed_mask=pend, hp=5, max_hp=5, silk=4, h=1, pause_pending=True))
    attack = (cs.prim_bits & (1 << int(Prim.ATTACK_SIDE))) != 0
    assert not ok[attack].any() and (why[attack] == R_ALLOW).all()
    b = cmod.bind_macro(100)
    assert not veto(b, FilterContext(allowed_mask=allowed, hp=3, max_hp=5, silk=9, want_bind=False))[0][0]
    assert veto(b, FilterContext(allowed_mask=allowed, hp=3, max_hp=5, silk=9, want_bind=True))[0][0]
    assert veto(b, FilterContext(allowed_mask=allowed, hp=3, max_hp=5, silk=9, want_bind=False))[1][0] == R_BIND
    hull = np.array([[68.0, 2.0, 70.0, 4.0], [80.0, 2.0, 82.0, 4.0], [5.0, 0.0, 4.0, 0.0]])
    hz, soft = hazard_flags(hull, np.zeros(3, np.int32), FilterContext(allowed_mask=allowed, h=2,
                                                                       soft=[(67.2, 0.0, 69.2, 14.0)]))
    assert list(soft) == [True, False, False] and not hz.any()
    assert unpausable(np.array([True, False]), FilterContext(allowed_mask=allowed, hp=4, max_hp=5, h=2)).tolist() == \
        [True, False]
    assert not unpausable(np.array([True]), FilterContext(allowed_mask=allowed, hp=5, max_hp=5, h=3)).any()


def tick(planner, model, tpls, params, roots, x, hp=5, silk=5, h=3, gates=False, mode=kin.M_NORMAL):
    fc = fc_with(model, tpls, roots)
    f = fc.forecast(2.0, 0.0)
    ws = world(x, hp, silk, gates)
    prefs = Tactics(load_playbook()).decide(ws, f, None, h)
    ctx = FilterContext.from_world(ws, None, h, want_bind=prefs.want_bind)
    start = kin.initial_state(params, x, 2.015 + params.foot, mode=mode)
    return planner.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, prefs, ctx), prefs


def test_planner_ticks(model, tpls, params, arena):
    planner = Planner(params, arena, PlannerConfig(threads=4))
    r, prefs = tick(planner, model, tpls, params, [], 85.0)
    assert r.S == 0 and not r.forced_risk and r.n_safe == r.n_allowed and prefs.mode == HOLD
    # a charge from the left, the hero 10 u in front of it in the wind-up: a safe plan exists and is chosen
    an = model.anchor("BB_CHARGE", "Set L")
    charge = [Root("Charge Antic", -0.3, -0.3, Ctx("BB_CHARGE", "Set L", an, "P1", False), current=True)]
    planner.reset()
    r, prefs = tick(planner, model, tpls, params, charge, an.x + 10.0)
    assert r.S == 0 and not r.forced_risk and r.V and prefs.mode == EVADE
    assert r.hull is not None and len(r.hull) == 1 + 1 + planner.cfg.T
    # inside the burst's eruption as it starts: every plan collides, the least probable one is chosen
    from ssbot.combat.boss_model import Anchor
    burst = [Root("Burst Out", 0.0, 0.0, Ctx("BB_BURST", None, Anchor(85.0, 5.49, 1), "P1", False), current=True)]
    planner.reset()
    r, _ = tick(planner, model, tpls, params, burst, 85.0)
    assert r.forced_risk and r.S == 1 and r.P > 0.0
    # hit-stop: the no-control candidate subset
    planner.reset()
    r, _ = tick(planner, model, tpls, params, [], 85.0, mode=kin.M_HURT_FREEZE)
    assert r.n == len(cmod.no_control(planner.cands).cmd)


def test_heal_mode_and_the_bind_macro(model, tpls, params, arena):
    planner = Planner(params, arena, PlannerConfig(threads=4))
    r, prefs = tick(planner, model, tpls, params, [], 85.0, hp=2, silk=9, h=1)
    assert prefs.mode == HEAL and prefs.want_bind and r.name == "BIND" and r.mask & kin.B_BIND
    an = model.anchor("BB_CHARGE", "Set L")
    charge = [Root("Charge", -0.1, -0.1, Ctx("BB_CHARGE", "Set L", an, "P1", False), current=True)]
    planner.reset()
    r, prefs = tick(planner, model, tpls, params, charge, an.x + 8.0, hp=2, silk=9, h=1)
    assert prefs.mode != HEAL and r.name != "BIND"                           # T_min < 1.37 + 0.15 s


def test_soft_gates_at_h2(model, tpls, params, arena):
    planner = Planner(params, arena, PlannerConfig(threads=4))
    r, _ = tick(planner, model, tpls, params, [], 71.0, hp=3, h=2, gates=True)
    assert r.S == 0 and not r.Hz                                              # Hz soft ranks below; chosen plan
    r, _ = tick(planner, model, tpls, params, [], 85.0, hp=3, h=2, gates=True)
    assert r.S == 0
