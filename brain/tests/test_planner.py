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
    assert not unpausable(np.array([True]), FilterContext(allowed_mask=allowed, hp=5, max_hp=5, h=3,
                                                          tier="GREEN")).any()
    # YELLOW forbids the uncertified killing blow at full HP too (§3.7.3); a certified plan passes
    y = FilterContext(allowed_mask=allowed, hp=5, max_hp=5, h=3, tier="YELLOW")
    assert unpausable(np.array([True, True]), y, np.array([False, True])).tolist() == [True, False]


def test_killing_blow_is_vetoed_unless_certified(model, tpls, params, arena):
    """The STUCK fix in the planner (safety_filter U / KILL): h 2 in YELLOW with nothing in support. Boss at 15 HP:
    a plan with one or two nail presses (5 each, Hunter) cannot kill and is not touched; at 5 HP every attacking plan
    may kill, those whose last hit plus the slow motion's window fits in the rollout are certified and pass, the rest
    are vetoed (R_KILL); with the support not certified none passes; GREEN at full HP with h 3 needs no certificate."""
    from ssbot.combat.hero_damage import HeroDamage
    planner = Planner(params, arena, PlannerConfig(threads=4))
    f = fc_with(model, tpls, []).forecast(2.0, 0.0)
    ws = world(85.0, 3, 0)
    prefs = Tactics(load_playbook()).decide(ws, f, None, 2)
    start = kin.initial_state(params, 85.0, 2.015 + params.foot)
    dmg = HeroDamage.from_loadout("Hunter", 0, ("Silk Spear",))

    def run(hp=3, h=2, tier="YELLOW", **kw):
        ctx = FilterContext.from_world(world(85.0, hp, 0), None, h, damage=dmg)
        ctx.tier = tier
        for k, v in kw.items():
            setattr(ctx, k, v)
        planner.reset()
        r = planner.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, prefs, ctx)
        return r, planner.last_kill

    r, (may, cert, vet, infl) = run(kill_hp=15.0, support_known=True)
    def edges(bit):
        on = (planner.last_cs.cmd & bit) != 0
        return (on[:, 1:] & ~on[:, :-1]).sum(axis=1) + on[:, 0]
    presses, casts = edges(kin.B_ATTACK), edges(kin.B_QUICKCAST)
    assert may <= int((5 * presses + 15 * casts >= 15).sum()) and r.S == 0     # casts: the Silkspear's 15
    r, (may, cert, vet, infl) = run(kill_hp=5.0, support_known=True)
    assert may >= int((presses >= 1).sum()) and cert > 0 and vet == may - cert
    assert 0 < r.vetoes.get("uncertified killing blow", 0) <= vet and r.S == 0   # (the Silkspear's: silk reserve)
    r, (may, cert, vet, infl) = run(kill_hp=5.0, support_known=False)
    assert cert == 0 and vet == may > 0 and not (r.cmd[:3] & kin.B_ATTACK).any()
    r, (may, cert, vet, infl) = run(kill_hp=5.0, support_known=False, h=1)
    assert cert == 0 and vet == may
    r, (may, cert, vet, infl) = run(hp=5, h=3, tier="GREEN", kill_hp=5.0, support_known=False)
    assert may > 0 and vet == 0
    # the chosen plan's kill: certified plans carry their window (the policy keeps them through the slow motion)
    r, (may, cert, vet, infl) = run(kill_hp=5.0, support_known=True)
    if r.kill is not None:
        assert r.kill.own and r.kill.certified and not r.kill.i3 and r.kill.k_hi + r.kill.window <= r.kill.P + 48
    assert r.idle_clear is not None and r.idle_clear > 0          # nothing in support: the no-input path is clear
    # a kill kind whose slow motion does not fit the rollout (the Forum's arena end, 0.79 s of game time): nothing
    # is certified, every plan whose own presses may kill is vetoed
    r, (may, cert, vet, infl) = run(kill_hp=5.0, support_known=True, kill_window_s=0.7941)
    assert cert == 0 and vet == may > 0 and not (r.cmd[:3] & kin.B_ATTACK).any()
    # a blow already sent (the prefix presses the attack): no candidate is vetoed for it, the certified ones rank first
    ctx = FilterContext.from_world(world(85.0, 3, 0), None, 2, damage=dmg)
    ctx.tier, ctx.kill_hp, ctx.support_known = "YELLOW", 5.0, True
    planner.reset()
    r = planner.tick(ws, start, kin.HoldState.idle(1), np.full(2, kin.B_ATTACK, np.int64), f, prefs, ctx)
    may, cert, vet, infl = planner.last_kill
    assert infl > 0 and r.kill is not None and (r.kill.certified or not r.kill.own)


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
    r, prefs = tick(planner, model, tpls, params, [], 85.0, hp=3, silk=9, h=2)
    assert prefs.mode == HEAL and prefs.want_bind and r.name == "BIND" and r.mask & kin.B_BIND
    an = model.anchor("BB_CHARGE", "Set L")
    charge = [Root("Charge", -0.1, -0.1, Ctx("BB_CHARGE", "Set L", an, "P1", False), current=True)]
    planner.reset()
    r, prefs = tick(planner, model, tpls, params, charge, an.x + 8.0, hp=3, silk=9, h=2)
    assert prefs.mode != HEAL and r.name != "BIND"                           # T_min < 1.37 + 0.15 s
    # Q1 (the person's rule, 2026-10-03): never a Bind at h <= 1, whatever the room
    planner.reset()
    r, prefs = tick(planner, model, tpls, params, [], 85.0, hp=2, silk=9, h=1)
    assert prefs.mode != HEAL and not prefs.want_bind and r.name != "BIND"


def _decision(hp: int, max_hp: int = 5):
    """The supervisor's decision for a hero at hp of max_hp against the Bell Beast's 2-mask body (S = 0 plan)."""
    from ssbot.safety.hits_to_death import SupportEvent
    from ssbot.safety.supervisor import Supervisor, SupervisorConfig, SupervisorInput
    return Supervisor(SupervisorConfig(worst_known_damage=2)).step(SupervisorInput(
        t=1.0, hp=hp, max_hp=max_hp, support=(SupportEvent("Bone Beast", 2),), support_known=True, plan_s=0))


def test_q1a_heal_first_branches(model, tpls, params, arena):
    """Q1a (DESIGN §3.7.4): h >= 2 below max HP -> Bind in place when the commit test passes; else walk to a verified
    safe spot the forecast agrees with and Bind there; else fight on (the other modes)."""
    from dataclasses import replace

    from ssbot.combat.tactics import HEAL_SPOT, SafeSpot
    planner = Planner(params, arena, PlannerConfig(threads=4))
    tac = Tactics(load_playbook())
    f_none = fc_with(model, tpls, []).forecast(2.0, 0.0)
    # 4 / 5 (h 2): the playbook's hp_missing_min alone keeps the Bind off; the supervisor's heal-first flag does not
    d4 = _decision(4)
    assert d4.h == 2 and d4.restrictions.heal_first
    assert tac.decide(world(85.0, hp=4, silk=9), f_none, None, 2).mode != HEAL
    prefs = tac.decide(world(85.0, hp=4, silk=9), f_none, d4, d4.h)
    assert prefs.mode == HEAL and prefs.want_bind
    r = planner.tick(world(85.0, hp=4, silk=9), kin.initial_state(params, 85.0, 2.015 + params.foot),
                     kin.HoldState.idle(1), np.zeros(1, np.int64), f_none, prefs,
                     FilterContext.from_world(world(85.0, hp=4, silk=9), d4, d4.h, want_bind=prefs.want_bind))
    assert r.name == "BIND"
    # full HP: nothing to heal; 2 / 5 (h 1): Q1's quit, never a Bind
    assert not _decision(5).restrictions.heal_first
    d2 = _decision(2)
    assert d2.pause_pending and not d2.allows("BIND")
    assert tac.decide(world(85.0, hp=2, silk=9), f_none, d2, d2.h).mode != HEAL
    # the decision of the tick before (h 2, heal first) with this tick's h 1 (a hit to 1 HP on this tick): no Bind
    # (PlannerPolicy hands the tactics SupervisedControl.h_now; fixer review 2026-10-03)
    d3 = _decision(3)
    assert d3.h == 2 and d3.restrictions.heal_first
    prefs = tac.decide(world(85.0, hp=1, silk=9), f_none, d3, 1)
    assert prefs.mode != HEAL and not prefs.want_bind
    # gathering silk (DESIGN §3.7.4 Q6, 2026-10-03): h 2 below max HP with silk < 9 raises the hit weight by the
    # playbook's gather_hit_x; not at full HP, not with the Bind's silk, not at h 1
    pb0 = load_playbook()
    assert pb0.bind_gather_hit_x > 1.0
    base = pb0.weights["hit"]
    assert tac.decide(world(85.0, hp=3, silk=5), f_none, d3, 2).weights["hit"] == base * pb0.bind_gather_hit_x
    assert tac.decide(world(85.0, hp=5, silk=5), f_none, _decision(5), 3).weights["hit"] == base
    assert tac.decide(world(85.0, hp=1, silk=5), f_none, d3, 1).weights["hit"] == base
    assert tac.decide(world(85.0, hp=3, silk=5), f_none, None, 2).weights["hit"] == base     # no supervisor: tools
    # in place impossible (a charge 8 u away): no spot in the Bell Beast playbook -> fight on (EVADE here)
    an = model.anchor("BB_CHARGE", "Set L")
    charge = [Root("Charge", -0.1, -0.1, Ctx("BB_CHARGE", "Set L", an, "P1", False), current=True)]
    f_ch = fc_with(model, tpls, charge).forecast(2.0, 0.0)
    d3 = _decision(3)
    x = an.x + 8.0
    prefs = tac.decide(world(x, hp=3, silk=9), f_ch, d3, d3.h)
    assert prefs.mode not in (HEAL, HEAL_SPOT) and not prefs.want_bind and "T_min" in prefs.bind_why
    # a leap landed right of the arena's middle: its body (and the next attack, past the 2 s horizon) leaves the left
    # floor out of reach for a Bind; the hero beside the body cannot Bind there
    pb = load_playbook()
    lan = model.anchor("BB_LEAP", "Set L")
    land = [Root("Leap Land", -0.1, -0.1, Ctx("BB_LEAP", "Set L", lan, "P1", False), current=True)]
    f_ld = fc_with(model, tpls, land).forecast(2.0, 0.0)
    xs = np.arange(pb.arena_x[0], pb.arena_x[1], 0.5)
    tm = np.array([f_ld.t_min(float(v), pb.hero_y, t_max=2.0) for v in xs])
    near_x = float(xs[np.flatnonzero(tm < 1.52)[0]])               # the first covered spot (nearest the free side)
    free = xs[tm >= 1.52]
    assert len(free) and np.isfinite(near_x)
    spot = SafeSpot("test spot", float(free[0]), pb.hero_y, "floor", 1.0, "synthetic")
    assert Tactics(pb).decide(world(near_x, hp=3, silk=9), f_ld, d3, d3.h).mode not in (HEAL, HEAL_SPOT)
    tac2 = Tactics(replace(pb, safe_spots=(spot,)))
    prefs = tac2.decide(world(near_x, hp=3, silk=9), f_ld, d3, d3.h)
    assert prefs.mode == HEAL_SPOT and prefs.stance_x == spot.x and not prefs.want_bind
    assert "safe spot" in prefs.bind_why
    # once there, the commit test passes in place: HEAL, and the planner's own Bind rollout agrees
    prefs = tac2.decide(world(spot.x, hp=3, silk=9), f_ld, d3, d3.h)
    assert prefs.mode == HEAL and prefs.want_bind
    planner.reset()
    r = planner.tick(world(spot.x, hp=3, silk=9), kin.initial_state(params, spot.x, 2.015 + params.foot),
                     kin.HoldState.idle(1), np.zeros(1, np.int64), f_ld, prefs,
                     FilterContext.from_world(world(spot.x, hp=3, silk=9), d3, d3.h, want_bind=True))
    assert r.name == "BIND"
    # a spot the forecast covers, an unverified one, a wall one or one that needs an ability is never used
    covered = SafeSpot("covered", near_x, pb.hero_y, "floor", 1.0, "synthetic")
    for sp in (covered, replace(spot, verified=""), replace(spot, kind="wall"), replace(spot, needs=("double_jump",))):
        prefs = Tactics(replace(pb, safe_spots=(sp,))).decide(world(near_x, hp=3, silk=9), f_ld, d3, d3.h)
        assert prefs.mode not in (HEAL, HEAL_SPOT), sp
    # silk short of a Bind: no spot either (only the place may fail); h 1: never
    assert tac2.decide(world(near_x, hp=3, silk=8), f_ld, d3, d3.h).mode not in (HEAL, HEAL_SPOT)
    assert tac2.decide(world(near_x, hp=2, silk=9), f_ld, d2, d2.h).mode not in (HEAL, HEAL_SPOT)
    assert load_playbook().safe_spots == ()                      # Bell Beast: none verified (playbook comment)


def test_soft_gates_at_h2(model, tpls, params, arena):
    planner = Planner(params, arena, PlannerConfig(threads=4))
    r, _ = tick(planner, model, tpls, params, [], 71.0, hp=3, h=2, gates=True)
    assert r.S == 0 and not r.Hz                                              # Hz soft ranks below; chosen plan
    r, _ = tick(planner, model, tpls, params, [], 85.0, hp=3, h=2, gates=True)
    assert r.S == 0


def test_hull_points_cover_wide_boxes():
    """Every hull box is covered by the union of its query points grown by the point coverage (hx, hy); boxes wider
    than 2 points cover are flagged too_wide; frames that need fewer points get NaN (skipped by the query)."""
    from ssbot.combat.planner import _hull_points
    rng = np.random.default_rng(5)
    hx, hy = 0.4, 1.2894
    n, t = 40, 30
    x0 = rng.uniform(70, 100, (n, t))
    y0 = rng.uniform(2, 10, (n, t))
    w = rng.choice([0.5, 0.7, 0.9, 1.5, 2.0], (n, t))
    h = rng.choice([2.08, 2.4, 3.0, 5.0, 6.0], (n, t))
    bound = np.stack([x0, y0, x0 + w, y0 + h], -1)
    X, Y, rows, too_wide = _hull_points(bound, hx, hy, 2)
    assert (too_wide == ((w > 4 * hx + 1e-9) | (h > 4 * hy + 1e-9))).all()
    pts = [(X[:n], Y[:n])] + [(np.full((n, t), np.nan), np.full((n, t), np.nan)) for _ in range(3)]
    for layer in range(3):
        blk = slice(n + layer * len(rows), n + (layer + 1) * len(rows))
        pts[layer + 1][0][rows], pts[layer + 1][1][rows] = X[blk], Y[blk]
    for i in range(n):
        for k in range(t):
            if too_wide[i, k]:
                continue
            P = [(px[i, k], py[i, k]) for px, py in pts if not np.isnan(px[i, k])]
            for fx in np.linspace(0, 1, 7):
                for fy in np.linspace(0, 1, 7):
                    qx, qy = x0[i, k] + fx * w[i, k], y0[i, k] + fy * h[i, k]
                    assert any(abs(qx - a) <= hx + 1e-9 and abs(qy - b) <= hy + 1e-9 for a, b in P)


def test_adaptive_horizon_and_jump_commitment_through_a_charge(model, tpls, params, arena):
    """A charge from the right in its wind-up, the hero 14 u in front of the anchor: the tactics ask for a horizon
    to the charge's end, the planner rolls the dodge set that far and finds a safe jump timing; once a jump is
    pressed its hold is kept on the next ticks."""
    an = model.anchor("BB_CHARGE", "Set R")
    fc = Forecaster(model, ORACLE, margin=MARGIN, templates=tpls)
    planner = Planner(params, arena, PlannerConfig(threads=4))
    tac = Tactics(load_playbook())
    x = an.x - 14.0
    S0 = kin.initial_state(params, x, 2.015 + params.foot, facing=1)
    for tau in (0.2, 0.4):
        fc.tracker.state, fc.tracker.t_entry = "Charge Antic", -tau
        fc.tracker.roots = lambda origin, tau=tau: ([Root("Charge Antic", -tau, -tau, Ctx(
            "BB_CHARGE", "Set R", an, "P1", False), current=True)], True)
        f = fc.forecast(2.0, 0.0)
        prefs = tac.decide(world(x), f, None, 3)
        assert prefs.horizon_frames > planner.cfg.T
        planner.reset()
        r = planner.tick(world(x), S0, kin.HoldState.idle(1), np.zeros(1, np.int64), f, prefs,
                         FilterContext.from_world(world(x), None, 3))
        assert r.S == 0 and not r.forced_risk and r.n == len(planner.cands_long.cmd)
    # commitment: a plan that pressed jump keeps it held while a kept plan is safe
    fc.tracker.roots = lambda origin: ([], True)
    f = fc.forecast(2.0, 0.0)
    prefs = tac.decide(world(85.0), f, None, 3)
    planner.reset()
    planner.jump_until = planner.ticks + 20
    r = planner.tick(world(85.0), kin.initial_state(params, 85.0, 2.015 + params.foot), kin.HoldState.idle(1),
                     np.full(1, kin.B_JUMP, np.int64), f, prefs, FilterContext.from_world(world(85.0), None, 3))
    assert (r.cmd[:19] & kin.B_JUMP).all()


def test_tail_check_runs_for_a_fresh_choice(model, tpls, params, arena):
    planner = Planner(params, arena, PlannerConfig(threads=4))
    r, _ = tick(planner, model, tpls, params, [], 85.0)
    assert r.tail_ok is True


def test_the_spear_scores_only_along_the_throw(model, tpls, params, arena):
    """The Silkspear flies the way the hero faced as the cast started; keys held during the cast do not turn it
    (run 20261002_064001: 123 casts away from the boss, none hit, all scored as three hits). A cast that hits nothing
    costs cast_waste."""
    from ssbot.core.worldstate import Entity, Kind
    an = model.anchor("BB_LEAP", "Set L")
    fc = fc_with(model, tpls, [Root("Leap Land", -0.1, -0.1, Ctx("BB_LEAP", "Set L", an, "P1", False), current=True)])
    fc.tracker.state, fc.tracker.t_entry = "Leap Land", -0.1
    f = fc.forecast(2.0, 0.0)
    f.boss = Entity(id=1, kind=Kind.BOSS, type_key=E("Bone Beast"), pos=E((96.0, 4.0)),
                    render_box=(94.0, 2.0, 98.0, 6.0), visible_frac=1.0)
    ws = world(88.0, silk=9)
    prefs = Tactics(load_playbook()).decide(ws, f, None, 3)
    planner = Planner(params, arena, PlannerConfig(threads=4))
    cs = planner.cands
    names = ["SILKSKILL(0)R+idle", "SILKSKILL(0)L+runR", "SILKSKILL(0)L+idle"]
    rows = [next(i for i in range(len(cs.cmd)) if cs.name(i) == n) for n in names]
    start = kin.initial_state(params, 88.0, 2.015 + params.foot, facing=1, silk=9)
    latched, _ = hold_filter_jit(cs.cmd[rows], kin.HoldState.idle(len(rows)))
    roll = kin.rollout(start, latched, params, arena, variants="bounds", threads=4)
    tk = np.arange(latched.shape[1] + 1) * params.frame_time
    J, hits, _ = planner._score(ws, roll, latched, start, f, prefs, 0, tk)
    assert hits.tolist() == [3.0, 0.0, 0.0]
    assert J[0] > J[1] + 25.0 and J[0] > J[2] + 25.0


def test_hits_land_on_the_boss_polygon_not_its_box():
    """Nail hits are scored against the boss's enabled collider polygons (Leap Out: LeapCollider, a 9-vertex shape
    whose bounding box is 11.7 x 3.8 u): a slash in the box's empty corner scores nothing."""
    from ssbot.combat.planner import _rect_meets_polys
    leap = np.array([2.64, 1.04, 0.3, 1.24, -1.61, 0.73, -3.82, -0.77, -5.81, -2.63, -5.94, -3.08, -0.03, -2.61, 5.58,
                     -0.67, 4.31, 0.54]).reshape(-1, 2) + (80.0, 10.0)
    starts = np.array([0, len(leap)])
    # the box's upper-left corner (x 74.1-76, y 10.5-11.2) is empty; the middle of the body is not
    assert not _rect_meets_polys(74.1, 10.4, 76.0, 11.2, leap, starts, 0.0, 0.0)
    assert _rect_meets_polys(79.0, 9.5, 81.0, 10.5, leap, starts, 0.0, 0.0)          # inside the body
    assert _rect_meets_polys(84.0, 8.0, 86.5, 9.6, leap, starts, 0.0, 0.0)           # across its right edge
    assert not _rect_meets_polys(84.0, 8.0, 86.5, 9.6, leap, starts, 0.0, 5.0)       # moved up 5 u
