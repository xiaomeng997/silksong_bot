"""Track A of the Forum push 2 (2026-10-08, the person's decisions and tactics; forum.md §26): the SSBOT_FORUM_TA
tokens. free: the supervisor's free mode (DESIGN 3.5.6 revision), the L0 filter's I3 and the clash gate with it;
whip / guard / edge: the L2 rules; under / eml: the J terms and FORCED_RISK's tie-break; kb: the hit branch's
knockback. Every token off is the planner before (the default)."""
import numpy as np
import pytest

from ssbot.combat.forum_planner import (K_DOWN, K_SIDE, K_UP, ForumConfig, ForumPlanner, knockback, parse_ta,
                                        under_gains)
from ssbot.combat.planner import PlannerConfig
from ssbot.combat.safety_filter import FilterContext, i3_kill_allowed
from ssbot.combat.tactics.gauntlet import CH_WHIP, CHORISTOR, RUSH, Goal
from ssbot.combat.tactics.modes import GoalPrefs
from ssbot.core.forum import FLOOR_Y
from ssbot.core.primitives import ATTACKS, N_PRIM, Prim
from ssbot.core.worldstate import E, Entity
from ssbot.knowledge import kinematics as kin
from ssbot.safety.hits_to_death import MASK_NONE, SupportEvent
from ssbot.safety.supervisor import Supervisor, SupervisorInput, forum_supervisor_config
from tests.test_forum_l2 import MI, RE, WinFc, l2, subj, world
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena, params  # noqa: F401

TWO = SupportEvent("Envoy", 2, instance=11)


def _inp(**kw) -> SupervisorInput:
    base = dict(t=10.0, hp=5, max_hp=5, mask=MASK_NONE, support=(TWO,), support_known=True, plan_s=0)
    base.update(kw)
    return SupervisorInput(**base)


# ---- free: the DESIGN 3.5.6 revision ----

def test_free_mode_lifts_the_h2_tightening_until_a_hit_leaves_h1():
    kp = frozenset({Prim.ATTACK_SIDE, Prim.ATTACK_UP})
    plain = Supervisor(forum_supervisor_config())
    free = Supervisor(forum_supervisor_config(free_until_hit=True))
    # h = 2 (4 HP against 2-mask events), a freezing kill possible: before, YELLOW withheld it and limited punishes
    d0 = plain.step(_inp(hp=4, kill_prims=kp))
    assert d0.tier == "YELLOW" and d0.h == 2 and not d0.free
    assert not d0.allows("ATTACK(side)") and d0.restrictions.no_parry and d0.restrictions.max_punish_hits == 1
    d = free.step(_inp(hp=4, kill_prims=kp))
    assert d.tier == "YELLOW" and d.h == 2 and d.free                      # the tier keeps its label
    assert d.allows("ATTACK(side)") and d.allows("ATTACK(up)") and not d.kill_rule
    r = d.restrictions
    assert not (r.no_parry or r.no_killing_blow or r.no_new_fights) and r.max_punish_hits is None
    assert r.heal_first                                                    # Q1a stays: heal when the window allows
    # an S = 1 plan at full HP (h 3) the same
    d = free.step(_inp(hp=5, plan_s=1, kill_prims=kp))
    assert d.free and d.allows("ATTACK(side)")
    # a hit to 2 HP: h = 1, Q1 in the post-hit window exactly as before, evasive keys only
    d = free.step(_inp(t=10.5, hp=2, damage_taken=2, hurt=True, kill_prims=kp))
    assert "Q1" in d.triggers and d.pause_pending and not d.free and d.q1_cause == "hit"
    assert not any(d.allows(p) for p in ATTACKS)


def test_free_mode_leaves_q3_and_the_bell_beast_alone():
    free = Supervisor(forum_supervisor_config(free_until_hit=True))
    d = free.step(_inp(hp=4, support_known=False))           # h = 2 with an unknown support: Q3 quits as before
    assert "Q3" in d.triggers and d.pause_pending and not d.free
    assert forum_supervisor_config().free_until_hit is False
    from ssbot.safety.supervisor import SupervisorConfig
    assert SupervisorConfig(worst_known_damage=2).free_until_hit is False


def test_free_mode_reaches_i3_and_the_clash_gate(params, arena):
    ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), hp=4, max_hp=5, h=2, tier="YELLOW", free=True)
    assert i3_kill_allowed(ctx)
    ctx.free = False
    assert not i3_kill_allowed(ctx)
    ctx.free, ctx.h = True, 1
    assert not i3_kill_allowed(ctx)
    # a long kill slow motion (the Forum's final blow, EnemyBattleEndSlow 1.85 s): free never lets it go uncertified;
    # only the I3 rule (GREEN, full HP, h >= 3) does
    ctx.h, ctx.kill_window_s = 2, 1.85
    assert not i3_kill_allowed(ctx)
    ctx.h = 3
    assert not i3_kill_allowed(ctx)
    ctx.tier, ctx.hp = "GREEN", 5
    assert i3_kill_allowed(ctx)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig(clash=True))
    assert not pl.clash_allowed(_ctx(h=2, tier="YELLOW"))
    assert pl.clash_allowed(_ctx(h=2, tier="YELLOW", free=True))
    assert not pl.clash_allowed(_ctx(h=2, tier="YELLOW", free=True, pause_pending=True))


def test_the_decision_carries_free_into_the_filter_context():
    free = Supervisor(forum_supervisor_config(free_until_hit=True))
    d = free.step(_inp(hp=4))
    ctx = FilterContext.from_world(_world(30.0, hp=4), d, d.h)
    assert ctx.free and ctx.tier == "YELLOW"


# ---- the tokens ----

def test_parse_ta():
    assert parse_ta("") == frozenset() and parse_ta(None) == frozenset()
    assert parse_ta("free+whip") == {"free", "whip"} and parse_ta("eml, kb") == {"eml", "kb"}
    assert len(parse_ta("all")) == 7
    with pytest.raises(ValueError):
        parse_ta("free+nope")
    assert ForumConfig().tac == frozenset()                   # SSBOT_FORUM_TA unset in the tests: none


def test_the_policy_takes_ta_from_the_env_and_the_ab_arms(monkeypatch):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    monkeypatch.setenv("SSBOT_FORUM_TA", "free+guard")
    assert ForumPlannerPolicy._fcfg().tac == {"free", "guard"}
    monkeypatch.setenv("SSBOT_FORUM_AB", "a:ta=none;b:ta=all")
    arms = ForumPlannerPolicy._ab_arms()
    assert arms == [("a", {"ta": ""}), ("b", {"ta": "all"})]
    monkeypatch.setenv("SSBOT_FORUM_AB", "a:ta=bogus")
    with pytest.raises(ValueError):
        ForumPlannerPolicy._ab_arms()


# ---- kb: the measured knockback ----

def test_knockback_profiles():
    dx, dy = knockback("Song Reed", "Alert", K_SIDE, -1, 12)
    assert dx[0] == 0.0 and dx[1] == pytest.approx(-0.45) and dx[8] == pytest.approx(-3.6) and dx[11] == dx[8]
    assert not dy.any()
    dx, dy = knockback("Song Reed", "Alert", K_UP, 1, 12)
    assert dy[8] == pytest.approx(3.0) and not dx.any()
    assert knockback("Song Reed", "Alert", K_DOWN, 1, 12) is None
    assert knockback("Song Reed", "Stab 2", K_SIDE, 1, 12) is None          # a stab's dash: no measurable push
    assert knockback("Song Heavy Sentry", "Idle", K_UP, 1, 12) is None      # the Clapper: not pushed up
    assert knockback("Song Heavy Sentry", "Idle", K_SIDE, 1, 12)[0][8] == pytest.approx(0.72)
    assert knockback("Song Administrator", "Parry Stance", K_UP, 1, 12) is None   # a guard: not pushed up
    assert knockback("Song Pilgrim Maestro", "Fly", K_UP, 1, 12)[1][8] == pytest.approx(1.95)


class _KbF:
    """A forecast whose only support is the hit enemy's (iid 7): hero centres within 1.5 u of x 30 and above y 5.0
    (a flyer's body over the hero's jump)."""

    def __init__(self):
        from types import SimpleNamespace
        self.fc = SimpleNamespace(half=(0.25, 1.04))
        self._fc = SimpleNamespace(trackers={7: SimpleNamespace(state="Alert")})
        self.calls = []

    @staticmethod
    def _occ(X, Y):
        X, Y = np.asarray(X), np.asarray(Y)
        return (np.abs(X - 30.0) < 1.5) & (Y > 5.0)

    def occupied(self, X, Y, tk, comfort=False):
        self.calls.append("all")
        return self._occ(X, Y)

    def occupied_without(self, X, Y, tk, ex, comfort=False):
        self.calls.append(("without", ex))
        return np.zeros(np.shape(X), bool)

    def occupied_only(self, X, Y, tk, iids):
        self.calls.append(("only", tuple(iids)))
        return self._occ(X, Y)


def test_knockback_moves_the_hit_enemy_in_the_hit_branch(params, arena):
    """Under a flyer, a jump with an up slash hitting it on frame 8: with "kb" the enemy (its support) goes up with the
    push from the hit on (the hero's hull moved down against that enemy's own support, the rest of the support
    unmoved), so the branch meets it on fewer frames; without "kb" the enemy stays where it was."""
    from ssbot.combat.multi_forecast import Target
    T = 36
    cmd = np.zeros((1, T), np.int64)
    cmd[0, :20] |= kin.B_JUMP
    cmd[0, 5:7] |= kin.B_UP | kin.B_ATTACK
    start = kin.initial_state(params, 30.0, FLOOR + params.foot)
    tk = np.arange(T + 1) * params.frame_time
    tgt = Target(7, "Song Reed", np.tile([[29.5, 9.0, 30.5, 11.0]], (T + 1, 1)), np.ones(T + 1, bool))
    sc = {"first_k": np.array([K_UP]), "first_face": np.array([1]), "first_f": np.array([8]),
          "first_t": np.array([0]), "targets": [tgt]}
    occ = {}
    for ta in ("", "kb"):
        pl = ForumPlanner(params, arena, PlannerConfig(T=T, threads=2, variants="bounds_lo"), ForumConfig(ta=ta))
        f = _KbF()
        budget = {"hitfx": 0, "react": 0, "capped": 0, "react_cache": {}}
        s, o, cp = pl._hit_branch(f, start, cmd, sc, np.array([0]), tk, False, budget)
        occ[ta] = (o[0].copy(), f.calls, pl.audit.kb_rows)
    plain, kb = occ[""], occ["kb"]
    assert plain[2] == 0 and plain[1] == ["all"] and kb[2] == 1
    # the review of forum push 2: the push is the median knockback with no lower bound and no wall, so the hit enemy's
    # unpushed support stays (the whole support unmoved) and its pushed one is added
    assert "all" in kb[1] and ("only", (7,)) in kb[1] and ("without", 7) not in kb[1]
    assert plain[0].any() and (kb[0] | plain[0] == kb[0]).all()
    assert (kb[0][:9] == plain[0][:9]).all()                  # before the hit (frame 8 on) nothing moved


# ---- under ----

def test_under_gains_from_below_json():
    typ, fam = under_gains()
    assert typ["Song Reed"] == pytest.approx(0.0318, abs=0.002)
    assert typ["Pilgrim 03 Song"] == pytest.approx(0.085, abs=0.002)
    assert typ.get("Song Administrator", 0.0) == 0.0                         # under a Minister is not safer
    assert fam[("Song Reed", "RE_STAB")] == pytest.approx(0.066, abs=0.002)


def test_under_bonus_scores_rows_under_a_flyer(params, arena):
    from ssbot.combat.multi_forecast import Target
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig(ta="under"))
    T1 = 10
    fly = np.tile([[29.5, 8.0, 30.5, 9.0]], (T1, 1))
    t = Target(7, "Song Reed", fly, np.ones(T1, bool))
    box = np.zeros((3, T1, 4))
    for n, x in enumerate((30.0, 31.05, 35.0)):               # under it, within its half-width + 0.6, beside it
        box[n] = [x - 0.25, 3.0, x + 0.25, 5.08]
    b = pl._under_bonus(object(), box, [t])
    assert b[0] == pytest.approx(10.0 * 0.0318, abs=0.03) and b[1] == pytest.approx(b[0]) and b[2] == 0.0


# ---- eml and the per-kind weights ----

def test_per_kind_hit_weights(params, arena):
    mf = _reed_forecaster(None, frames=3, x=30.0)
    f = mf.forecast(0.8)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig())
    tk = np.arange(37) * (1 / 60)
    p0 = GoalPrefs("ENGAGE", 28.0, {}, hit_w={7: 2.5})
    p1 = GoalPrefs("ENGAGE", 28.0, {}, hit_w={7: 2.5}, hit_kw={7: (0.0, 4.0, 0.0, -1.0)})
    assert (pl._forum_targets(_world(28.0), f, tk, p0)[2][0] == 2.5).all()
    assert list(pl._forum_targets(_world(28.0), f, tk, p1)[2][0]) == [0.0, 4.0, 0.0, -1.0]


def test_eml_is_a_tie_break_after_the_first_contacts(params, arena):
    """FORCED_RISK in front of a committed stab: with "eml" the chosen row is still the least by the old keys
    (the tie-break comes after the first contacts), and its eml key is the least among the rows tied on them."""
    mf = _reed_forecaster(10, frames=17)
    res = {}
    for ta in ("", "eml"):
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=float("inf"), ta=ta))
        r = pl.tick(_world(31.6), kin.initial_state(params, 31.6, FLOOR + params.foot), kin.HoldState.idle(1),
                    np.zeros(1, np.int64), mf.forecast(0.8), _prefs(), _ctx())
        res[ta] = (r, pl.last_sel)
    r0, s0 = res[""]
    r1, s1 = res["eml"]
    assert not s0["eml"].any()
    if r1.forced_risk:
        i = s1["chosen"]
        keys = ("hz", "hz_soft", "U", "S", "clash_p", "sk_n", "sk_c", "Pc", "Pcm", "Pf", "t_c", "t_hit")
        tied = np.flatnonzero(s1["sel"])
        for k in keys:
            v = np.asarray(s1[k], float)
            tied = tied[v[tied] == v[i]]
        assert s1["eml"][i] == s1["eml"][tied].min()


# ---- the L2 rules ----

def _l2(ta):
    t = l2()
    t.ta = parse_ta(ta)
    return t


def test_guard_bands_for_a_minister():
    t = _l2("guard")
    neg = t.local.rules.defensive_hit_w
    other = subj(2, CHORISTOR, 26.0)
    for ey, band in ((4.0, "low"), (4.8, "mid"), (6.0, "high"), (9.0, "out")):
        m = subj(1, MI, 24.0, y=FLOOR_Y + ey, state="Parry Stance", family="MI_PARRY")
        w_g, _, lab_g = t._guard_rule(m, [m, other], 3.0, 20.0, WinFc([m, other]))
        w_a, _, lab_a = t._guard_rule(m, [m], 3.0, 20.0, WinFc([m]))
        assert band in lab_g and "grouped" in lab_g and "alone" in lab_a
        assert w_g[0] == w_g[2] == neg and w_a[0] == w_a[2] == neg         # never from the side
        assert w_a[1] == neg                                                # alone: no up slash (wait)
        assert w_g[1] == (3.0 if band in ("mid", "high") else neg)
        assert w_g[3] == w_a[3] == (3.0 if band in ("low", "mid") else neg)  # the down slash from above: either
    # triggered (Parry Block): high band up slashes even alone; mid keeps the swing for the clash (0)
    hi = subj(1, MI, 24.0, y=FLOOR_Y + 6.0, state="Parry Block", family="MI_PARRY")
    assert t._guard_rule(hi, [hi], 3.0, 20.0, WinFc([hi]))[0][1] == 3.0
    mid = subj(1, MI, 24.0, y=FLOOR_Y + 4.8, state="Parry Block", family="MI_PARRY")
    assert t._guard_rule(mid, [mid, other], 3.0, 20.0, WinFc([mid, other]))[0][1] == 0.0


def test_guard_reed_never_triggers_and_waits_in_reach():
    t = _l2("guard")
    neg = t.local.rules.defensive_hit_w
    r = subj(3, RE, 30.0, y=FLOOR_Y + 3.0, state="Defend", family="RE_DEFEND")
    w, st, lab = t._guard_rule(r, [r], 3.0, 24.0, WinFc([r]))
    assert w == (neg, neg, neg, neg) and "reed" in lab
    assert st == pytest.approx(30.0 - 0.8 - t.rules.edge_u)                 # the body's edge + edge_u, hero's side
    assert t._guard_rule(subj(3, RE, 30.0, state="Alert"), [], 3.0, 24.0, WinFc([]))[0] is None


def test_whip_zone_and_stance():
    t = _l2("whip")
    ch = subj(5, CHORISTOR, 30.0, state="Whip Antic", family=CH_WHIP, committed=True)
    ent = Entity(id=5, type_key=E(CHORISTOR), pos=E((30.0, 4.0)), flip_x=True)    # faces +x
    ws = world(31.0, ents=[ent])
    z = t._whip_zones(ws, WinFc([ch]))
    assert z == [(5, pytest.approx(30.0 - 5.3), pytest.approx(30.0 + 9.3), 30.0, 1.0)]
    g = Goal(RUSH, 5, 31.0, 0.0)
    p, why = t._ta_rules(ws, WinFc([ch]), GoalPrefs(RUSH, 31.0, {}), g, ch, 31.0)
    assert p.stance_x == pytest.approx(30.0 - 5.3) and why == ["whip: out of its reach"]    # behind: nearer
    # a pick whose spot is in its reach goes last
    other = subj(6, "Song Pilgrim 01", 45.0)
    cands = {c.s.iid: c for c in t.candidates(ws, WinFc([ch, other]), 31.0)}
    assert cands[5].prio == pytest.approx(t.rules.whip_prio_x) and cands[6].prio == pytest.approx(1.0)


def test_edge_spot_for_rush():
    t = _l2("edge")
    s = subj(4, "Song Pilgrim 01", 30.0)
    g = Goal(RUSH, 4, 28.2, 0.0)
    p, why = t._ta_rules(world(20.0), WinFc([s]), GoalPrefs(RUSH, 28.2, {}), g, s, 20.0)
    assert why == ["edge"] and p.stance_x == pytest.approx(30.0 - 0.8 - 2.7)
    t.ta = frozenset()
    assert t._ta_rules(world(20.0), WinFc([s]), GoalPrefs(RUSH, 28.2, {}), g, s, 20.0)[1] == []


def test_human_score_j_terms_use_the_kernel_signature(params, arena):
    """tools.forum_human_score.j_terms calls the score kernel itself: its hits term equals _score_forum's hits."""
    from ssbot.tools.forum_human_score import j_terms
    mf = _reed_forecaster(None, frames=3, x=30.0)
    f = mf.forecast(0.8)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig())
    start = kin.initial_state(params, 27.6, FLOOR + params.foot)
    cmd = np.zeros((3, 36), np.int64)
    cmd[1, 1:3] = kin.B_ATTACK | kin.B_RIGHT
    cmd[2, 1:3] = kin.B_ATTACK | kin.B_UP
    roll = kin.rollout(start, cmd, params, arena, threads=2)
    prefs = GoalPrefs("ENGAGE", 27.6, {}, hit_w={7: 2.0})
    ws = _world(27.6)
    tk = np.arange(cmd.shape[1] + 1) * params.frame_time
    sc = pl._score_forum(ws, roll, cmd, start, f, prefs, tk, _ctx())
    jt = j_terms(pl, {"args": (ws, start, None, None, f, prefs, _ctx())}, roll.box, roll.flags, roll.mode, cmd)
    assert np.allclose(jt[:, 0], sc["hits"])


# ---- the measurement tool (tools.forum_knockback) ----

def test_forum_knockback_measures_the_whip_frame_and_a_push():
    from ssbot.tools.forum_knockback import Acc, add_cache, summary
    F = 20
    rows = []                                                  # (fi, iid, tk, x, y, flip, st)
    for fi in range(F):
        rows.append((fi, 1, 0, 30.0, 4.0, 1, 0))               # a Choristor facing +x, whipping
        x = 31.0 + (0.45 * min(fi - 5, 8) if fi > 5 else 0.0)  # a Reed pushed 0.45 u a frame after a hit on frame 5
        rows.append((fi, 2, 1, x, 6.0, 0, 1))
    a = np.array(rows, dtype=object)
    c = {"types": ["Song Pilgrim 03", "Song Reed"], "states": ["Whip 1", "Alert"], "names": ["Whip Hit 1"],
         "f": np.arange(100, 100 + F), "hx": np.full(F, 28.0), "hy": np.full(F, 4.0),
         "e_fi": a[:, 0].astype(np.int64), "e_iid": a[:, 1].astype(np.int64), "e_tk": a[:, 2].astype(np.int64),
         "e_x": a[:, 3].astype(float), "e_y": a[:, 4].astype(float), "e_flip": a[:, 5].astype(np.int8),
         "e_st": a[:, 6].astype(np.int64), "e_vx": np.zeros(len(a)), "e_tin": np.full(len(a), 0.05),
         "c_ei": np.array([0]), "c_name": np.array([0]), "c_box": np.array([[30.5, 3.0, 35.7, 4.1]]),
         "events": [(105, "hit", {"ent": 2, "src": "Slash"})]}
    acc = Acc()
    add_cache(acc, c)
    out = summary(acc, min_n=1)
    w = out["whip"]["Whip Hit 1"]
    assert w["x0"]["50"] == pytest.approx(0.5) and w["x1"]["50"] == pytest.approx(5.7)
    kb = out["kb"]["Song Reed|side|Alert|hit"]
    assert kb["dx_p50"][0] == pytest.approx(0.9) and kb["dx_p50"][4] == pytest.approx(3.6)
    assert kb["dy_p50"][4] == pytest.approx(0.0)
