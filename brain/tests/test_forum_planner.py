"""The Forum fast layer (forum_planner_plan §4.4 items 2 and 3, round R3): combat.forum_planner.ForumPlanner on the
synthetic Reed tables of test_multi_forecast, the Forum vocabulary, hit reactions, the Forum kill rule and the
supervisor's Forum settings."""
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ssbot.combat import candidates as cmod
from ssbot.combat.forum_planner import (EnvelopeAudit, ForumConfig, ForumPlanner, forum_kill_hp,
                                        forum_yellow_kill_hp, kill_freeze_s, posture_of)
from ssbot.combat.multi_forecast import MultiForecaster, hit_reactions
from ssbot.combat.planner import PlannerConfig
from ssbot.combat.safety_filter import FilterContext
from ssbot.combat.tactics.modes import HOLD, GoalPrefs
from ssbot.core.forum import FORUM_WAVES
from ssbot.core.primitives import N_PRIM
from ssbot.core.worldstate import E, ORACLE, WorldState
from ssbot.knowledge import kinematics as kin
from ssbot.safety.hits_to_death import SupportEvent
from ssbot.safety.supervisor import (POST_HIT_WINDOW_S, Q1_HIT, Supervisor, SupervisorConfig, SupervisorInput,
                                     WEIGHTED_POST_HIT_WINDOW_S, forum_supervisor_config)
from tests.test_multi_forecast import BIN, REED, _ent, _go, _run, _tables

FORUM_PARAMS = Path(__file__).resolve().parents[2] / "knowledge" / "1.0.30000" / "kinematics" / "hero_reaper_forum.json"
FLOOR = 3.0


@pytest.fixture(scope="module")
def params():
    return kin.HeroParams.load(FORUM_PARAMS)


@pytest.fixture(scope="module")
def arena():
    return kin.Terrain2D.from_boxes([(10.0, 0.0, 53.0, FLOOR), (10.0, 0.0, 14.01, 30.0), (48.99, 0.0, 53.0, 30.0)])


def _world(x: float, hp: int = 5) -> WorldState:
    ws = WorldState()
    ws.hero.pos = E((x, FLOOR + 1.04))
    ws.res.hp, ws.res.hp_max, ws.res.silk = E(hp), E(5), E(0)
    return ws


def _reed_forecaster(stab_at: int | None = 10, frames: int = 12, x: float = 30.0):
    """A Reed idling in Alert at x (flipX: facing +x), starting a stab at frame stab_at."""
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    script = []
    for f in range(frames):
        t = f * BIN
        evs = []
        st = "Alert" if stab_at is None or f < stab_at else "Stab Pos"
        if f == 0:
            evs.append(_go(7, "Alert", f, t))
        if stab_at is not None and f == stab_at:
            evs.append(_go(7, "Stab Pos", f, t))
        script.append((f, t, [_ent(7, x, FLOOR + 1.0, st, flip=True, box=(x - 0.5, FLOOR, x + 0.5, FLOOR + 2.0))],
                       evs))
    _run(mf, script)
    return mf


def _ctx(**kw):
    d = dict(allowed_mask=np.ones(N_PRIM, bool), hp=5, max_hp=5, silk=0, h=3, tier="GREEN", support_known=True)
    d.update(kw)
    return FilterContext(**d)


def _prefs(rng=None, x=27.0):
    if rng is None:
        return GoalPrefs(HOLD, x, {})
    w = {k: float(rng.uniform(0, 20)) for k in ("hit", "waste", "jump", "stance", "risk", "face", "ground", "cont")}
    rx = np.arange(14.0, 49.0, 0.5)
    return GoalPrefs("ENGAGE", float(rng.uniform(15, 48)), w, max_hits=int(rng.integers(0, 4)), risk_x=rx,
                     risk=rng.uniform(0, 1, len(rx)), boss_x=float(rng.uniform(15, 48)), hit_w={7: float(rng.uniform(0, 5))},
                     goal=str(rng.choice(["ENGAGE", "BAIT", "FOCUS"])), target=7)


# ---- the vocabulary ----

def test_forum_families_share_the_core_rows_and_drop_the_silk_skill():
    sets = {p: cmod.build_forum(36, p) for p in cmod.POSTURES}
    cores = [cs.cmd[core] for cs, core in sets.values()]
    assert all(c.shape == (56, 36) for c in cores)
    assert all(np.array_equal(cores[0], c) for c in cores[1:])
    for p, (cs, core) in sets.items():
        assert len(cs.cmd) <= 441
        assert not ((cs.cmd & kin.B_QUICKCAST) != 0).any()
        assert ((cs.cmd[core] & kin.B_ATTACK) == 0).all()          # the evasion set has no attack (no hit branch)
    assert any(n.startswith("ATTACK(down)") for n in sets["air"][0].first_names)
    assert not any(n.startswith("ATTACK(down)") for n in sets["ground"][0].first_names)


def test_posture_of_the_start_state(params):
    s = kin.initial_state(params, 30.0, FLOOR + params.foot)
    assert posture_of(s) == "ground"
    s[kin.GROUND] = 0.0
    assert posture_of(s) == "air"
    s[kin.WSIDE] = -1.0
    assert posture_of(s) == "wall"


# ---- §4.4 item 2: the core rows' S / Hz / U do not depend on the goal ----

@pytest.mark.parametrize("hero_x,stab_at", [(27.0, 10), (31.5, 10), (24.0, None), (30.2, 10)])
def test_core_rows_s_hz_u_are_the_same_under_any_goal(params, arena, hero_x, stab_at):
    mf = _reed_forecaster(stab_at)
    f = mf.forecast(0.8)
    start = kin.initial_state(params, hero_x, FLOOR + params.foot)
    ws = _world(hero_x)
    rng = np.random.default_rng(int(hero_x * 10))
    ref = None
    forced_default = None
    for k in range(8):
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=0.0 if k % 2 else 50.0))
        prefs = _prefs(None if k == 0 else rng, hero_x)
        r = pl.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, prefs, _ctx(kill_hp=5.0))
        li = pl.last_info
        core = li["core_mask"]
        got = (li["S"][core].copy(), li["Hz"][core].copy(), li["U"][core].copy())
        # every core row past stage 1 was enveloped, whatever the deadline
        assert pl.audit.core_not_enveloped == 0
        if ref is None:
            ref, forced_default = got, r.forced_risk
        else:
            for a, b in zip(ref, got):
                assert np.array_equal(a, b)
            # a goal never makes FORCED_RISK where the default goal is not (§4.4 item 2)
            assert not r.forced_risk or forced_default


@pytest.mark.parametrize("hero_x,stab_at", [(27.0, 10), (30.2, 10), (28.5, 8)])
def test_forced_risk_does_not_depend_on_the_caps_order(params, arena, hero_x, stab_at):
    """The hit-branch caps are handed out in queue order (J: the prefs); with hitfx_k = 1 and react_k = 0 they bind on
    every tick, and still a goal's FORCED_RISK implies the default goal's (the capped rows get their hit branch
    uncapped before FORCED_RISK), and the safe set without a cap is the same under every goal."""
    mf = _reed_forecaster(stab_at)
    f = mf.forecast(0.8)
    start = kin.initial_state(params, hero_x, FLOOR + params.foot)
    ws = _world(hero_x)
    rng = np.random.default_rng(int(hero_x * 10) + 1)
    forced_default = None
    for k in range(6):
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, hitfx_k=1, react_k=0, chunk=16))
        r = pl.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None if k == 0 else rng,
                                                                                         hero_x), _ctx(kill_hp=5.0))
        if k == 0:
            forced_default = r.forced_risk
        else:
            assert not r.forced_risk or forced_default


def test_note_hit_puts_the_hit_branch_into_the_forced_ranking():
    """A row safe on its miss branch whose hit branch meets the support (or whose reaction a cap left unchecked) is
    not contact-free for FORCED_RISK's ranking: t_hit drops to the branch's first contact (to the hit frame for a
    capped one) and its contact frames are kept for the share."""
    T1 = 12
    rows = np.array([3, 5, 8])
    sh = np.array([True, False, True])
    oh = np.zeros((3, T1), bool)
    oh[0, 6:9] = True
    cp = np.array([False, False, True])
    sc = {"first_f": np.array([0, 0, 0, 2, 0, 4, 0, 0, 7, 0])}
    t_hit = np.full(10, T1, np.int64)
    hit_occ, capped = {5: np.ones(T1, bool)}, []
    ForumPlanner._note_hit(rows, sh, oh, cp, sc, t_hit, hit_occ, capped, T1)
    assert t_hit[3] == 6 and hit_occ[3][6:9].all() and hit_occ[3].sum() == 3
    assert 5 not in hit_occ and t_hit[5] == T1                     # its hit branch is clear: nothing to add
    assert t_hit[8] == 7 and hit_occ[8][7:].all() and not hit_occ[8][:7].any() and capped == [8]


def test_forced_ranking_never_takes_a_row_in_contact_for_contact_free(params, arena):
    """FORCED_RISK ranks its candidates on one lane over every frame: a candidate in contact at stage 1, or whose hit
    branch meets the support, has a share in contact above 0 and a first contact no later than its estimate's."""
    rng = np.random.default_rng(11)
    forced = 0
    for x in (30.6, 31.0, 31.6, 32.0):
        mf = _reed_forecaster(10, frames=17)
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, chunk=16))
        r = pl.tick(_world(x), kin.initial_state(params, x, FLOOR + params.foot), kin.HoldState.idle(1),
                    np.zeros(1, np.int64), mf.forecast(0.8), _prefs(rng, x), _ctx())
        li = pl.last_info
        if not r.forced_risk:
            continue
        forced += 1
        for i in np.flatnonzero(li["cand"]):
            if not li["env"][i] or int(i) in li["hit_occ"]:
                assert li["Pc"][i] > 0
            h = li["hit_occ"].get(int(i))
            if h is not None:
                assert li["t_c"][i] <= int(np.argmax(h))
    assert forced > 0


# ---- §4.4 item 3: the chosen plan is always enveloped ----

def test_the_chosen_safe_plan_was_always_enveloped(params, arena):
    rng = np.random.default_rng(5)
    for deadline in (0.0, 2.0, 50.0):
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=deadline, chunk=16))
        for x in np.linspace(22.0, 34.0, 13):
            mf = _reed_forecaster(int(rng.integers(5, 12)))
            r = pl.tick(_world(float(x)), kin.initial_state(params, float(x), FLOOR + params.foot),
                        kin.HoldState.idle(1), np.zeros(1, np.int64), mf.forecast(0.8), _prefs(rng, float(x)),
                        _ctx())
            if r.S == 0:
                assert pl.last_info["env"][r.idx]
        a = pl.audit
        assert a.ticks == 13 and a.chosen_safe > 0
        assert a.chosen_safe == a.chosen_safe_enveloped and a.core_not_enveloped == 0
        assert a.chosen_safe + a.forced == a.ticks


def test_inside_the_stab_every_way_out_is_checked_before_forced_risk(params, arena):
    """Hero in front of a committed stab: FORCED_RISK only once every row past stage 1 was enveloped."""
    mf = _reed_forecaster(10, frames=17)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=0.0, chunk=8))
    r = pl.tick(_world(31.6), kin.initial_state(params, 31.6, FLOOR + params.foot), kin.HoldState.idle(1),
                np.zeros(1, np.int64), mf.forecast(0.8), _prefs(), _ctx())
    li = pl.last_info
    if r.forced_risk:
        assert li["enveloped"] == li["stage1_pass"]
    else:
        assert li["env"][r.idx] and r.S == 0


# ---- hit reactions ----

def test_a_hit_reed_in_alert_stabs_at_once():
    """hero_caused.json: a Reed hit in Alert goes to Stab Pos at once; the plain forecast has the stab only after
    Alert's least dwell (0.2 s in the synthetic table)."""
    assert hit_reactions()[REED]["Alert"] == "Stab Pos"
    mf = _reed_forecaster(None, frames=3)
    assert mf.reaction_state(7) == "Stab Pos"
    f = mf.forecast(0.8)
    T = mf.t
    rf = mf.forecast_reaction(7, "Stab Pos", T + 0.05, 0.8, T)
    tk = np.arange(0, 16) * BIN                        # the first 0.25 s
    X, Y = np.full((1, 16), 32.0), np.full((1, 16), FLOOR + 1.0)
    # past the collider tube's 5 bins: only the reaction's stab reaches the blade's place
    assert not f.occupied(X, Y, tk)[0][6:13].any()
    assert rf.occupied(X, Y, tk)[0][6:13].any()
    assert mf.trackers[7].state == "Alert"             # the real state is untouched


@pytest.mark.parametrize("stab_at", [None, 10])
def test_occupied_is_the_union_of_its_parts(stab_at):
    """The support query's boxes of every kind in one call (R3 fix) answer exactly what the parts do."""
    mf = _reed_forecaster(stab_at, frames=12)
    f = mf.forecast(0.8)
    tk = np.arange(0, 40) * BIN
    xs = np.linspace(24.0, 36.0, 49)
    X = np.repeat(xs[:, None], len(tk), axis=1)
    for y in (FLOOR + 0.5, FLOOR + 1.5, FLOOR + 3.5):
        Y = np.full_like(X, y)
        parts = f.occupied_parts(X, Y, tk)
        union = np.logical_or.reduce(list(parts.values()))
        assert np.array_equal(f.occupied(X, Y, tk), union)
        assert union.any()


def test_reactions_come_from_every_state_the_walk_allows_at_the_hit():
    """A Reed in Stab Pos now (its TOOK DAMAGE exit: Stab Antic) is back in Alert (exit: Stab Pos) by a hit 0.8 s on,
    not by one 2 frames on; the reaction forecast holds all of them, anchored at the hit time."""
    mf = _reed_forecaster(10, frames=12)
    T = mf.t
    assert mf.trackers[7].state == "Stab Pos"
    ex = hit_reactions()[REED]
    soon = mf.reaction_states(7, T + 2 * BIN, 0.8)
    late = mf.reaction_states(7, T + 0.8, 0.8)
    assert soon == [ex["Stab Pos"]]
    assert set(late) >= {ex["Stab Pos"], ex["Alert"]}
    rf = mf.forecast_reaction(7, late, T + 0.8, 1.2, T)
    assert rf is not None and mf.trackers[7].state == "Stab Pos"
    # a reaction entering the stab again at 0.8 s: its blade is placed from then (both mirrors) at the anchor box
    tk = np.arange(0, 80) * BIN
    X, Y = np.full((1, 80), 30.0 + 2.0), np.full((1, 80), FLOOR + 1.0)
    Xl = np.full((1, 80), 30.0 - 2.0)
    late_occ = rf.occupied(X, Y, tk)[0] | rf.occupied(Xl, Y, tk)[0]
    assert late_occ[49:].any()


# ---- the Forum kill rules ----

def _tr(tk, hp, sd=0.0, in_play=True, dead=False):
    return SimpleNamespace(tk=tk, hp_est=hp, hp_sd=sd, in_play=in_play, dead=dead)


def test_the_unpausable_blow_is_the_one_that_may_end_the_battle():
    last = len(FORUM_WAVES) - 1
    clap = "Song Heavy Sentry"
    mf = SimpleNamespace(waves=SimpleNamespace(done=False, wave=last - 1, queued=None),
                         trackers={1: _tr(clap, 5.0)})
    assert forum_kill_hp(mf) is None                   # another wave to come: an ordinary kill
    mf.waves.wave = last
    mf.trackers = {1: _tr(clap, 40.0, 1.0), 2: _tr(clap, 9.0, 1.0)}
    assert forum_kill_hp(mf) == pytest.approx(37.0)    # one blow ends it only if both die
    mf.trackers[1].dead = True
    assert forum_kill_hp(mf) == pytest.approx(6.0)
    freeze = kill_freeze_s()
    assert set(freeze) >= {clap, REED}
    mf2 = SimpleNamespace(trackers={1: _tr(REED, 20.0, 2.0), 2: _tr(clap, 8.0)})
    assert forum_yellow_kill_hp(mf2, {REED: 0.25, clap: 0.0}) == pytest.approx(14.0)
    assert forum_yellow_kill_hp(mf2, {REED: 0.0, clap: 0.0}) is None


# ---- the supervisor's Forum settings ----

def test_q4_counts_unpredicted_hits_per_enemy_instance():
    sup = Supervisor(forum_supervisor_config())
    ev = (SupportEvent(REED, 1, instance=7),)
    base = dict(hp=5, max_hp=5, support=ev, support_known=True, plan_s=0)
    d = sup.step(SupervisorInput(t=0.0, unpredicted_hits=1, unpredicted_sources=(7,), **base))
    d = sup.step(SupervisorInput(t=1.0, unpredicted_hits=1, unpredicted_sources=(8,), **base))
    assert "Q4" not in d.triggers                      # two instances, one each
    d = sup.step(SupervisorInput(t=2.0, unpredicted_hits=1, unpredicted_sources=(7,), **base))
    assert "Q4" in d.triggers                          # instance 7 twice
    sup2 = Supervisor(forum_supervisor_config())
    for i, src in enumerate((1, 2, 3)):
        d = sup2.step(SupervisorInput(t=float(i), unpredicted_hits=1, unpredicted_sources=(src,), **base))
    assert "Q4" in d.triggers                          # the attempt-wide total (3)
    old = Supervisor(SupervisorConfig(worst_known_damage=2))
    old.step(SupervisorInput(t=0.0, unpredicted_hits=1, **base))
    assert "Q4" in old.step(SupervisorInput(t=1.0, unpredicted_hits=1, **base)).triggers   # Bell Beast unchanged


def test_yellow_withholds_a_freezing_kill_even_when_known_at_h2():
    """forum_planner_plan §4.4 item 7 (R4 fixer round): the Forum cannot certify a kill (no kill branches, and the L0
    filter's kill_hp is only the battle's last blow), so YELLOW withholds kill_prims with a certified support at h = 2
    too; Bell Beast's config keeps them for the L0 filter's certification."""
    from ssbot.combat.hero_damage import HeroDamage
    from ssbot.core.primitives import Prim
    dmg = HeroDamage.from_loadout("Reaper", 0)
    kp = dmg.kill_prims(5.0)                           # an Envoy at hp_est 5 (forum_yellow_kill_hp)
    assert Prim.ATTACK_SIDE in kp
    base = dict(t=10.0, hp=3, max_hp=5, support=(SupportEvent(REED, 2, instance=7),), support_known=True, plan_s=0,
                pausable=True, idle_clear_s=1.0, kill_prims=kp, next_hit_may_kill=True)
    d = Supervisor(forum_supervisor_config()).step(SupervisorInput(**base))
    assert d.tier == "YELLOW" and d.h == 2 and d.support_known
    assert not d.allows("ATTACK(side)") and not d.allows("ATTACK(up)") and not d.allowed & kp
    assert d.allows("DASH") and d.kill_rule
    bb = Supervisor(SupervisorConfig(worst_known_damage=2)).step(SupervisorInput(**base))
    assert bb.allows("ATTACK(side)")                   # Bell Beast unchanged: left to kill_certified
    d0 = Supervisor(forum_supervisor_config()).step(SupervisorInput(**{**base, "hp": 5}))
    assert d0.tier == "GREEN" and d0.allows("ATTACK(side)")   # GREEN: the L0 filter's (I3 / forum_kill_hp)


def test_the_weighted_anklet_widens_the_post_hit_window():
    assert forum_supervisor_config(weighted=True).post_hit_window_s == WEIGHTED_POST_HIT_WINDOW_S == 1.3
    assert forum_supervisor_config().post_hit_window_s == POST_HIT_WINDOW_S
    for cfg, q1 in ((forum_supervisor_config(weighted=True), Q1_HIT), (forum_supervisor_config(), "no_hit")):
        sup = Supervisor(cfg)
        sup.t_hit = 0.0
        assert (sup.q1_cause(1.2) == Q1_HIT) == (q1 == Q1_HIT)


def test_envelope_audit_is_a_plain_record():
    a = EnvelopeAudit()
    assert a.as_dict()["chosen_safe"] == 0


# ---- the Reaper's shapes (M2.md: the side slash reaches the front-up, the up slash only above and behind) ----

def test_reaper_side_slash_reaches_front_up_and_up_slash_overhead(params, arena):
    from ssbot.combat.holdfilter import hold_filter_jit
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=1, variants="bounds_lo"))
    cs, _ = cmod.build_forum(36, "ground")
    names = [cs.name(i) for i in range(len(cs.cmd))]
    rows = [names.index("ATTACK(side)R+idle"), names.index("ATTACK(up)R+idle")]
    x0 = 30.0
    start = kin.initial_state(params, x0, FLOOR + params.foot, facing=1)
    full = np.concatenate([np.zeros((2, 1), np.int64), cs.cmd[rows]], axis=1)
    latched, _ = hold_filter_jit(full, kin.HoldState.idle(2))
    roll = kin.rollout(start, latched, params, arena)
    tk = np.arange(roll.box.shape[1]) * params.frame_time
    b = roll.box[0, 0]
    cx, cy = 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])

    def fc(box):
        return SimpleNamespace(targets=lambda t: [SimpleNamespace(iid=1, type_key=REED, hazard=False,
                                                                 box=np.tile(np.array(box), (len(t), 1)),
                                                                 ok=np.ones(len(t), bool))])

    front_up = (cx + 1.8, cy + 1.6, cx + 2.4, cy + 2.2)
    overhead = (cx - 0.9, cy + 2.8, cx - 0.3, cy + 3.4)
    sc = pl._score_forum(_world(x0), roll, latched, start, fc(front_up), _prefs(), tk)
    assert sc["hits"][0] > 0 and sc["hits"][1] == 0 and sc["first_k"][0] == 1
    sc = pl._score_forum(_world(x0), roll, latched, start, fc(overhead), _prefs(), tk)
    assert sc["hits"][1] > 0 and sc["hits"][0] == 0 and sc["first_k"][1] == 2
