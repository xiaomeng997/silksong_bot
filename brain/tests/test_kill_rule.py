"""The killing-blow rule (DESIGN §3.7.3 YELLOW, I3) after the "STUCK at 15 HP" task (2026-10-04): per-attack damage
bounds from the loadout (combat.hero_damage), the L0 filter's geometry-free "may kill" and its certification through
the boss-death slow motion (combat.safety_filter), the supervisor's allowlist and its stalemate quit (QS), and the
supervision glue. Property tests sweep random inputs with fixed seeds: the rule may only ever get stricter where the
model knows less."""
import math

import numpy as np
import pytest

from ssbot.combat.hero_damage import NEEDLE_DAMAGE, HeroDamage
from ssbot.combat.safety_filter import (HIT_END_F, LANE_SLACK_F, QUEUE_F, FilterContext, i3_kill_allowed,
                                        kill_certified, kill_frames, kill_window_frames, unpausable)
from ssbot.combat.tactics import load_playbook
from ssbot.core.primitives import ALL, ATTACKS, DAMAGING, EVASIVE, N_PRIM, Prim
from ssbot.knowledge import kinematics as kin
from ssbot.safety.hits_to_death import MASK_NONE, SupportEvent
from ssbot.safety.supervisor import Supervisor, SupervisorConfig, SupervisorInput
from ssbot.train.supervision import SupervisedControl, entity_support, threat_min_hp

BB = SupervisorConfig(worst_known_damage=2)
BODY = SupportEvent("Bone Beast", 2, instance=529544)
FT = 1 / 60
HUNTER = HeroDamage.from_loadout("Hunter", 0, ("Silk Spear",))


# ---- damage bounds ------------------------------------------------------------------------------------------------

def test_hunter_bounds_match_the_logged_hits_and_the_playbook():
    """Hunter crest, needle level 0: every logged nail hit 5, every Silkspear 15 (4,081 / 460 hits, 21 of 21 in each
    STUCK episode, none critical); the playbook's hit_damage says the same."""
    assert (HUNTER.nail, HUNTER.spear, HUNTER.crit) == (5.0, 15.0, False)
    pb = load_playbook()
    assert pb.hit_damage == {"nail": HUNTER.nail, "silkspear": HUNTER.spear} and pb.needle_level == 0
    assert HUNTER.of_prim(Prim.ATTACK_SIDE) == HUNTER.of_prim(Prim.ATTACK_DOWN) == 5.0
    assert HUNTER.of_prim(Prim.SILKSKILL) == 15.0 and HUNTER.of_prim(Prim.DASH) == 0.0
    assert math.isinf(HUNTER.of_prim(Prim.TOOL)) and math.isinf(HUNTER.of_prim(Prim.CLAWLINE))
    # the STUCK state: boss 15 HP. The nail cannot kill it, only the Silkspear (not allowed below full HP)
    assert Prim.ATTACK_SIDE not in HUNTER.kill_prims(15.0) and Prim.SILKSKILL in HUNTER.kill_prims(15.0)
    assert ATTACKS <= HUNTER.kill_prims(5.0) and HUNTER.kill_prims(None) == frozenset()
    assert HUNTER.kill_prims(5.0) <= DAMAGING


def test_crits_only_with_a_crest_that_has_them():
    """A Wanderer critical hit is x 3 (HealthManager.cs 1011-1013); HeroController.IsWandererLucky needs the Wanderer
    crest, so no other known crest gets the factor. An unknown crest gets every factor."""
    w = HeroDamage.from_loadout("Wanderer")
    assert w.crit and w.nail >= 15.0                   # x 3, and no attack table yet: the largest swing multiplier
    for c in ("Hunter", "Hunter_v2", "Hunter_v3", "Reaper", "Warrior"):
        d = HeroDamage.from_loadout(c)
        assert not d.crit and d.nail < w.nail
    unk = HeroDamage.from_loadout(None)
    assert unk.crit and all(unk.nail >= HeroDamage.from_loadout(c).nail
                            for c in ("Hunter", "Hunter_v2", "Hunter_v3", "Reaper", "Warrior", "Wanderer"))
    assert HeroDamage.from_loadout("Hunter_v2").nail == 6.5 and HeroDamage.from_loadout("Hunter_v3").nail == 7.5
    assert HeroDamage.from_loadout("Reaper").nail == 5.0 and HeroDamage.from_loadout("Warrior").nail >= 6.25


def test_needle_and_tools_raise_the_bounds():
    for lvl, nd in enumerate(NEEDLE_DAMAGE):
        d = HeroDamage.from_loadout("Hunter", lvl)
        assert d.nail == nd and d.spear >= 15.0 * nd / 5
    assert HeroDamage.from_loadout("Hunter", 0, ("Barbed Wire",)).nail == 6.25
    assert HeroDamage.from_loadout("Hunter", 0, ("Some Imbuement",)).nail > 6.25        # unknown tool: bounded high
    assert HeroDamage.from_loadout("Hunter", 0, ("Weighted Anklet", "Silk Spear", None)).nail == 5.0


def test_observe_raises_only_the_hits_kind():
    d = HUNTER.observe("Slash", "Nail", 5)
    assert d is HUNTER
    d = HUNTER.observe("Needle Damage", "Heavy", 15)
    assert d is HUNTER                                  # the Silkspear's 15 leaves the nail at 5 (the STUCK cause)
    d = HUNTER.observe("Slash", "Nail", 8)
    assert d.nail == 8 and d.spear == 15 and d.raised == ("nail",)
    assert HUNTER.observe(None, "Generic", 100).nail == 5     # a hit of no known hero attack: the tool bound (inf)


@pytest.mark.parametrize("seed", range(3))
def test_kill_prims_property(seed):
    """Property: a primitive is in kill_prims(hp) iff its bound reaches hp; lower HP never removes one."""
    rng = np.random.default_rng(seed)
    for _ in range(300):
        d = HeroDamage.from_loadout(rng.choice(["Hunter", "Wanderer", "Warrior", "", "Reaper"]), int(rng.integers(5)))
        hp = float(rng.uniform(0.5, 60))
        kp = d.kill_prims(hp)
        assert kp == {p for p in Prim if 0 < d.of_prim(p) and hp <= d.of_prim(p)}
        assert kp <= d.kill_prims(hp * float(rng.uniform(0.1, 1.0)))


# ---- L0: may kill, certification, U -------------------------------------------------------------------------------

def _stream(rng, N, L, P):
    m = np.zeros((N, L), np.int64)
    for c in range(N):
        for _ in range(int(rng.integers(0, 4))):
            j = int(rng.integers(0, L - 3))
            b = kin.B_ATTACK if rng.random() < 0.8 else kin.B_QUICKCAST
            m[c, j:j + 3] |= b
            if rng.random() < 0.3:
                m[c, j:j + 3] |= kin.B_DOWN if rng.random() < 0.5 else kin.B_UP
    return m


def _edges(m: np.ndarray, bit: int) -> list[int]:
    on = (m & bit) != 0
    return [j for j in range(len(m)) if on[j] and (j == 0 or not on[j - 1])]


@pytest.mark.parametrize("seed", range(4))
def test_kill_frames_property(seed):
    """Property (random hold-filtered streams, no rollout onsets: every press waits the whole queue): may_kill iff
    the candidate has an own press and the sum of every press's bound reaches the HP; the window starts at the press
    that reaches it and ends no earlier than the last press's latest hit."""
    rng = np.random.default_rng(seed)
    N, P, T = 64, 2, 48
    L, T1 = P + T, P + T + 1
    lat = _stream(rng, N, L, P)
    flags = np.zeros((N, T1), np.int64)
    mode = np.zeros((N, T1), np.int64)
    for hp in (4.0, 5.0, 10.0, 15.0, 30.0):
        ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), kill_hp=hp, damage=HUNTER)
        may, lo, hi = kill_frames(lat, flags, mode, P, ctx)
        for c in range(N):
            ev = sorted([(j, 5.0, "a") for j in _edges(lat[c], kin.B_ATTACK)]
                        + [(j, 15.0, "c") for j in _edges(lat[c], kin.B_QUICKCAST)])
            own = any(j >= P for j, _, _ in ev)
            cum, k_lo = 0.0, None
            for j, dmg, _ in ev:
                cum += dmg
                if k_lo is None and cum >= hp:
                    k_lo = j + 1
            assert may[c] == (own and k_lo is not None)
            if may[c]:
                assert lo[c] == k_lo and 1 <= lo[c] <= hi[c]
                last = max(j for j, _, _ in ev)
                assert hi[c] >= last + 1 + QUEUE_F + HIT_END_F[0] + LANE_SLACK_F
            else:
                assert lo[c] == hi[c] == -1


def test_kill_frames_counts_the_running_attack_and_unknown_damage():
    N, P, T1 = 2, 1, 50
    lat = np.zeros((N, P + T1 - 1), np.int64)
    lat[:, 5:8] = kin.B_ATTACK
    flags = np.zeros((N, T1), np.int64)
    mode = np.zeros((N, T1), np.int64)
    flags[0, 0] = kin.F_ATTACKING                      # a slash already out at the start: 5 + 5 reaches 10
    ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), kill_hp=10.0, damage=HUNTER)
    may, lo, _ = kill_frames(lat, flags, mode, P, ctx)
    assert may.tolist() == [True, False] and lo[0] == 6
    ctx.damage = None                                  # unknown bounds: every press may kill
    assert kill_frames(lat, flags, mode, P, ctx)[0].all()
    ctx.kill_hp = None                                 # nothing alive that can die
    assert not kill_frames(lat, flags, mode, P, ctx)[0].any()
    # the nominal onset tightens the window: onset at frame 7, side slash
    flags[1, 7:20] = kin.F_ATTACKING
    ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), kill_hp=5.0, damage=HUNTER)
    _, _, hi = kill_frames(lat, flags, mode, P, ctx)
    assert hi[1] == 7 + HIT_END_F[0] + LANE_SLACK_F


@pytest.mark.parametrize("seed", range(4))
def test_certification_and_u_property(seed):
    """Properties of U (the hard veto): U implies may_kill; I3 (GREEN, full HP, h >= 3) never vetoes; a certified plan
    is never vetoed; certification needs S = 0, h >= 2, a certified support and the window inside the rollout."""
    rng = np.random.default_rng(seed)
    W = kill_window_frames(FT)
    assert W == math.ceil((0.17 + 0.15) * 60 - 1e-9)
    for _ in range(400):
        N, T1 = 32, int(rng.integers(30, 80))
        S = rng.random(N) < 0.4
        k_hi = np.where(rng.random(N) < 0.2, -1, rng.integers(1, T1, N))
        may = (k_hi >= 0) & (rng.random(N) < 0.8)
        ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), hp=int(rng.integers(1, 6)), max_hp=5,
                            h=[None, 1, 2, 3][int(rng.integers(4))], tier=["GREEN", "YELLOW", "RED"][int(rng.integers(3))],
                            support_known=bool(rng.random() < 0.7))
        cert = kill_certified(S, k_hi, T1, ctx, FT)
        U = unpausable(may, ctx, cert)
        assert not (U & ~may).any() and not (U & cert).any()
        assert not cert[S].any() and not cert[k_hi < 0].any() and not cert[k_hi + W > T1 - 1].any()
        if ctx.h is None or ctx.h < 2 or not ctx.support_known:
            assert not cert.any()
        else:
            assert (cert == (~S & (k_hi >= 0) & (k_hi + W <= T1 - 1))).all()
        if i3_kill_allowed(ctx):
            assert ctx.tier == "GREEN" and ctx.hp == 5 and ctx.h >= 3 and not U.any()
        else:
            assert (U == (may & ~cert)).all()


# ---- supervisor ---------------------------------------------------------------------------------------------------

def _inp(**kw) -> SupervisorInput:
    base = dict(t=10.0, hp=3, max_hp=5, mask=MASK_NONE, support=(BODY,), support_known=True, plan_s=0,
                pausable=True)
    base.update(kw)
    return SupervisorInput(**base)


def test_supervisor_keeps_the_nail_when_it_cannot_kill():
    """The STUCK state: h 2, boss 15 HP. Before, a Silkspear hit earlier in the attempt made every damaging primitive
    "may kill" and YELLOW removed them all; per attack only the Silkspear could (not allowed below full HP)."""
    d = Supervisor(BB).step(_inp(next_hit_may_kill=True, kill_prims=HUNTER.kill_prims(15.0)))
    assert d.tier == "YELLOW" and d.h == 2 and d.allows("ATTACK(side)") and d.allows("ATTACK(up)")
    assert not d.allows("SILKSKILL(0)") and not d.kill_prims & ATTACKS and d.stall_s == 0.0
    # (tools and the Clawline count as unbounded, so kill_rule reports them; the planner presses neither)
    assert d.kill_rule and d.kill_prims & d.allowed <= {Prim.TOOL, Prim.CLAWLINE}


@pytest.mark.parametrize("seed", range(3))
def test_supervisor_kill_allowlist_property(seed):
    """Property: careful (YELLOW / RED) with a possibly killing primitive and no way to certify a kill (support not
    certified, or h < 2) removes it; GREEN at full HP with h >= 3 never flags the rule; pending is evasive only."""
    rng = np.random.default_rng(seed)
    prims = sorted(DAMAGING)
    for i in range(600):
        kp = frozenset(p for p in prims if rng.random() < 0.5)
        inp = _inp(t=float(i), hp=int(rng.integers(1, 6)), plan_s=int(rng.integers(2)),
                   support_known=bool(rng.random() < 0.7), kill_prims=kp, next_hit_may_kill=bool(kp))
        d = Supervisor(BB).step(inp)
        if d.pause_pending:
            assert d.allowed == EVASIVE and not d.kill_rule
            continue
        certifiable = d.support_known and d.h is not None and d.h >= 2
        base = set(ALL) - ({Prim.SILKSKILL} if inp.hp < 5 else set())
        kill = kp & base
        careful = d.tier in ("YELLOW", "RED")
        if careful and not certifiable:
            assert not d.allowed & kp
        else:
            assert kill <= d.allowed                     # left to the L0 filter's certification (or I3 allows it)
        i3 = d.tier == "GREEN" and inp.hp == 5 and d.h >= 3
        assert d.kill_rule == (bool(kill) and not i3)
        assert d.kill_prims == kp


def test_stalemate_quits_at_a_safe_frame_after_20_s():
    """QS: the rule holding the nail back (boss 5 HP, h 2) with no hit and no heal for 20 s latches; the quit is
    armed at the first pausable frame whose plan is S = 0 without FORCED_RISK. A hit or a heal resets the clock."""
    kp = HUNTER.kill_prims(5.0)
    s = Supervisor(BB)
    for k in range(0, 20 * 60):
        d = s.step(_inp(t=k / 60, kill_prims=kp, next_hit_may_kill=True))
        assert d.kill_rule and not d.pause_pending
    assert d.stall_s == pytest.approx(19.983, abs=0.01)
    d = s.step(_inp(t=20.0, kill_prims=kp, next_hit_may_kill=True, plan_s=1))
    assert s.qs is not None and not d.pause_pending                  # latched, not safe (S = 1)
    d = s.step(_inp(t=20.02, kill_prims=kp, next_hit_may_kill=True, forced_risk=True))
    assert not d.pause_pending                                       # FORCED_RISK: not safe
    d = s.step(_inp(t=20.04, kill_prims=kp, next_hit_may_kill=True, pausable=False))
    assert not d.pause_pending                                       # the gate shut
    d = s.step(_inp(t=20.06, kill_prims=kp, next_hit_may_kill=True))
    assert d.pause_pending and d.quit_requested and "QS" in d.triggers and d.allowed == EVASIVE
    assert any(r.startswith("QS: stalemate") for r in d.reasons)
    # progress resets: a hit dealt, or a heal (HP up)
    s = Supervisor(BB)
    for k in range(0, 30 * 60):
        d = s.step(_inp(t=k / 60, kill_prims=kp, next_hit_may_kill=True, hit_dealt=k % 600 == 0))
    assert not d.pause_pending and d.stall_s < 10.1
    s = Supervisor(BB)
    for k in range(0, 30 * 60):
        hp = 3 if k < 15 * 60 else 5
        d = s.step(_inp(t=k / 60, hp=hp, kill_prims=kp, next_hit_may_kill=True))
    assert not d.pause_pending          # healed at 15 s; at full HP h 3 in GREEN the rule is off (I3)
    # the nail free (boss 15 HP): no stall however long the fight goes without a hit
    s = Supervisor(BB)
    for k in range(0, 30 * 60):
        d = s.step(_inp(t=k / 60, kill_prims=HUNTER.kill_prims(15.0), next_hit_may_kill=True))
    assert not d.pause_pending and d.stall_s == 0.0


# ---- the supervision glue (oracle STATE) ------------------------------------------------------------------------

def _state(f: int, boss_hp: int, ev=()) -> dict:
    boss = {"iid": 1, "type_key": "Bone Beast", "hp": boss_hp, "is_dead": False, "colliders": [
        {"enabled": True, "damage": {"dealt": 2, "eff": 2, "hazard_type": 1, "can_cause_damage": True}}]}
    return {"f": f, "q": f * 166_667, "pause": {"blk": 0}, "ev": list(ev), "ents": [boss],
            "hero": {"health": 3, "max_health": 5, "health_blue": 0, "crest": "Hunter",
                     "tools": [None, "Silk Spear", None], "fractured_mask": {"equipped": False, "amount_left": 0}}}


def test_glue_the_stuck_state_keeps_the_nail():
    """Runs 20261003_175813 i2 ep 58 and the five others: a Silkspear hit (15) earlier, then 3 HP and the boss at 15.
    The glue used to raise its one "hero hit" to 15 and remove every damaging primitive; now the nail stays."""
    sc = SupervisedControl(BB, support=lambda s: entity_support(s, worst_damage=2, known=True))
    spear = {"k": "hit", "d": {"ent": 1, "dmg": 15, "attack": "Heavy", "src": "Needle Damage"}}
    d = sc.step(_state(1, 30, [spear]), plan_s=0).decision
    assert sc.damage.nail == 5 and sc.damage.spear == 15 and not sc.alerts
    d = sc.step(_state(2, 15), plan_s=0).decision
    assert d.h == 2 and d.allows("ATTACK(side)") and not d.kill_prims & ATTACKS
    assert threat_min_hp(_state(2, 15)) == 15.0
    d = sc.step(_state(3, 5), plan_s=0).decision
    assert d.kill_rule and d.allows("ATTACK(side)") and Prim.ATTACK_SIDE in d.kill_prims     # L0 certifies
    # a nail hit above the bound raises it and alerts (the table was wrong)
    big = {"k": "hit", "d": {"ent": 1, "dmg": 9, "attack": "Nail", "src": "Slash"}}
    sc.step(_state(4, 20, [big]), plan_s=0)
    assert sc.damage.nail == 9 and any("hero damage" in a for a in sc.alerts)
