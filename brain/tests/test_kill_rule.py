"""The killing-blow rule (DESIGN §3.7.3 YELLOW, I3 and its certified exception, lead decision 2026-10-04) after the
"STUCK at 15 HP" task and its fixer round: per-attack damage bounds from the loadout and the targets' damage scaling
(combat.hero_damage, the game's formula with every rounding taken up), the kill kinds' measured slow motion
(safety_filter.KillKnowledge), the L0 filter's geometry-free "may kill" / "in flight" and its certification, the
supervisor's allowlist and its stalemate quit (QS), the supervision glue's one source of the kill inputs, and the
policy's kill commitment by game time. Property tests sweep random inputs with fixed seeds: the rule may only ever get
stricter where the model knows less."""
import itertools
import math

import numpy as np
import pytest

from ssbot.combat.hero_damage import (CREST_ADDS, FIXED_DEALT, NEEDLE_DAMAGE, SLOT_MULT, HeroDamage, round_up,
                                      scaling_at)
from ssbot.combat.safety_filter import (HIT_END_F, KILL_MARGIN_S, KILL_WINDOW_S, LANE_SLACK_F, QUEUE_F, FilterContext,
                                        KillKnowledge, i3_kill_allowed, kill_certified, kill_frames,
                                        kill_window_frames, unpausable)
from ssbot.combat.tactics import load_playbook
from ssbot.core.primitives import ALL, ATTACKS, DAMAGING, EVASIVE, N_PRIM, Prim
from ssbot.knowledge import kinematics as kin
from ssbot.safety.hits_to_death import MASK_NONE, SupportEvent
from ssbot.safety.supervisor import Supervisor, SupervisorConfig, SupervisorInput
from ssbot.train.planner_policy import commit_frame
from ssbot.train.supervision import SupervisedControl, entity_support, threat_min_hp

BB = SupervisorConfig(worst_known_damage=2)
BODY = SupportEvent("Bone Beast", 2, instance=529544)
FT = 1 / 60
HUNTER = HeroDamage.from_loadout("Hunter", 0, ("Silk Spear",))
KNOW = KillKnowledge.load()


# ---- the game's damage, emulated (float32, Mathf.RoundToInt half to even) -------------------------------------------

def rti(x) -> int:
    """Mathf.RoundToInt: Math.Round of the float32, half to even."""
    return int(np.rint(np.float32(x)))


def game_hit(level: int, slot: float, mults: list[float], scaling: float, crit: bool, per_hit: float = 1.0) -> int:
    """DamageEnemies.DoDamage (base, DamageStack.PopDamage, damageMultPerHit) then HealthManager.TakeDamage
    (ApplyDamageScaling, the Wanderer critical hit, HitInstance.Multiplier 1), all in float32."""
    f32 = np.float32
    base = rti(f32(NEEDLE_DAMAGE[level]) * f32(slot))
    num = f32(base)
    vals = [f32(num * f32(m) - num) for m in [*mults, 1.0]]     # + the damager's DamageMultiplier (1.0)
    for v in vals:
        num = f32(num + v)
    num = f32(num + f32(0.0))                                   # - damageDealtOffset (0)
    dealt = rti(num)
    if per_hit != 1.0:
        dealt = rti(max(f32(dealt) * f32(per_hit), f32(0.51)))
    v = rti(f32(dealt) * f32(scaling))
    if crit:
        v = rti(f32(v) * f32(3.0))
    return rti(f32(v) * f32(1.0))


# the swings each crest's attack table has (crests.json / attacks; the charge slash is never pressed) and the stack's
# multipliers the game can apply with it (the combos are if / else: one of them)
SWINGS = {"Hunter": (1.0, 0.5), "Hunter_v2": (1.0, 0.5), "Hunter_v3": (1.0, 0.5), "Reaper": (1.0, 0.5),
          "Wanderer": (1.0, 0.55, 0.5), "Warrior": (1.0, 1.4, 2.3, 2.5, 0.5)}
COMBOS = {"Hunter": [[]], "Hunter_v2": [[], [1.3]], "Hunter_v3": [[], [1.3], [1.5]], "Reaper": [[]], "Wanderer": [[]],
          "Warrior": [[], [1.25]]}


@pytest.mark.parametrize("crest", sorted(SWINGS) + ["Cursed"])
def test_bound_never_below_the_game_over_every_combination(crest):
    """Property (the verifier's refutation of the first version, which kept the exact product: Hunter_v3 needle 0
    bounded 7.5 against the game's 8, Hunter_v2 needle 1 11.7 against 12): for every crest, needle level, tool set,
    combo state, swing and damage scaling up to the bound's, the emulated game damage is at most the bound."""
    tools_sets = [(), ("Barbed Wire",), ("Silk Spear", "Weighted Anklet"), ("Fire Imbue",), ("Barbed Wire", "Zap X")]
    unknown = crest not in SWINGS
    swings = (1.0, 0.5, 0.55, 0.6, 0.7, 1.4, 2.3, 2.5) if unknown else SWINGS[crest]
    combos = [[], [1.3], [1.5], [1.25], [1.5, 1.25]] if unknown else COMBOS[crest]
    worst = 0
    for lv, tools in itertools.product(range(5), tools_sets):
        for scal in (1.0, 1.02, 1.0333, {lv: 1.1667}, {lv: 0.5}):
            d = HeroDamage.from_loadout(crest, lv, tools, scaling=scal)
            s = scaling_at(scal, lv)
            for slot, combo in itertools.product(swings, combos):
                for imbue in ((1.0, 1.2, 1.5) if any(t not in ("Barbed Wire", "Silk Spear", "Weighted Anklet")
                                                        for t in tools) else (1.0,)):
                    mults = list(combo) + ([1.25] if "Barbed Wire" in tools or imbue != 1.0 else []) + \
                        ([imbue] if imbue != 1.0 else [])
                    for crit in ((False, True) if d.crit else (False,)):
                        for ms in (s, s * 0.97):
                            g = game_hit(lv, slot, mults, ms, crit)
                            assert g <= d.nail, (crest, lv, tools, scal, slot, combo, imbue, crit, ms, g, d.nail)
                            worst = max(worst, g)
                # the fixed damagers (useNailDamage false: damageDealt 5, level -1 scaling x 1)
                assert rti(FIXED_DEALT * (3 if d.crit else 1)) <= d.nail
            # the Silkspear (3 x nailDamage: 15 measured at needle level 0; an unknown tool may be the zap tool or an
            # imbuement, both added to its stack)
            unk_tool = any(t not in ("Barbed Wire", "Silk Spear", "Weighted Anklet") for t in tools)
            for adds in ([0.0, 0.25, 0.5, 0.75] if unk_tool else [0.0]):
                sp = rti(np.float32(rti(15 * NEEDLE_DAMAGE[lv] / 5)) * np.float32(1.0 + adds))
                assert rti(np.float32(sp) * np.float32(s)) <= d.spear
    assert worst > 0


def test_verifier_counterexamples_and_tightness():
    assert HeroDamage.from_loadout("Hunter_v3", 0).nail >= 8 == game_hit(0, 1.0, [1.5], 1.0, False)
    assert HeroDamage.from_loadout("Hunter_v2", 1).nail >= 12 == game_hit(1, 1.0, [1.3], 1.0, False)
    for lv, nd in enumerate(NEEDLE_DAMAGE):                     # the plain Hunter: exact
        assert HeroDamage.from_loadout("Hunter", lv).nail == nd == game_hit(lv, 1.0, [], 1.0, False)
    assert round_up(7.5) == 8 and round_up(8.5) == 9 and round_up(7.4) == 7 and round_up(math.inf) == math.inf


def test_hunter_bounds_match_the_logged_hits_and_the_playbook():
    """Hunter crest, needle level 0: every logged nail hit 5, every Silkspear 15 (Bell Beast: 6,146 / 1,564 hits of
    the recordings tools/kill_window read, dealt = dmg, none critical); the playbook's hit_damage says the same, and
    Bell Beast's audited scaling (m < 15.5 / 15) keeps the nail at 5."""
    assert (HUNTER.nail, HUNTER.spear, HUNTER.crit) == (5.0, 15.0, False)
    pb = load_playbook()
    assert pb.hit_damage == {"nail": HUNTER.nail, "silkspear": HUNTER.spear} and pb.needle_level == 0
    bb = HUNTER.at(KNOW.scaling(["Bone Beast"]))
    assert bb.nail == 5.0 and bb.spear >= 15.0 and 1.0 <= bb.scaling < 1.034
    assert HUNTER.of_prim(Prim.ATTACK_SIDE) == HUNTER.of_prim(Prim.ATTACK_DOWN) == 5.0
    assert HUNTER.of_prim(Prim.SILKSKILL) == 15.0 and HUNTER.of_prim(Prim.DASH) == 0.0
    assert math.isinf(HUNTER.of_prim(Prim.TOOL)) and math.isinf(HUNTER.of_prim(Prim.CLAWLINE))
    # the STUCK state: boss 15 HP. The nail cannot kill it, only the Silkspear (not allowed below full HP)
    assert Prim.ATTACK_SIDE not in bb.kill_prims(15.0) and Prim.SILKSKILL in bb.kill_prims(15.0)
    assert ATTACKS <= bb.kill_prims(5.0) and bb.kill_prims(None) == frozenset()
    assert HUNTER.kill_prims(5.0) <= DAMAGING


def test_unknown_parts_are_unbounded_or_bounded_high():
    """An unknown target scaling (a type without an audit, or a needle level not measured) makes every press able to
    kill; an unknown needle level (vision without an inventory audit) takes every level."""
    assert math.isinf(HUNTER.at(None).nail) and math.isinf(HUNTER.at({1: 1.0}).nail)
    assert KNOW.scaling(["Bone Beast", "Never Seen"]) == {}
    assert math.isinf(HUNTER.at(KNOW.scaling(["Never Seen"])).nail)
    v = HeroDamage.from_loadout("Hunter", None, ("Silk Spear",))
    assert v.needle_level is None and v.at(1.0).nail == 21 and v.at({0: 1.0}).nail == math.inf
    assert Prim.ATTACK_SIDE in v.at(1.0).kill_prims(21.0)


def test_crits_only_with_a_crest_that_has_them():
    """A Wanderer critical hit is x 3 (HealthManager.cs 1011-1013); HeroController.IsWandererLucky needs the Wanderer
    crest, so no other known crest gets the factor. An unknown crest gets every factor."""
    w = HeroDamage.from_loadout("Wanderer")
    assert w.crit and w.nail == 15.0                   # 5 x 3 (its swings are 1.0, crests.json)
    for c in ("Hunter", "Hunter_v2", "Hunter_v3", "Reaper", "Warrior"):
        assert not HeroDamage.from_loadout(c).crit
    unk = HeroDamage.from_loadout(None)
    assert unk.crit and all(unk.nail >= HeroDamage.from_loadout(c).nail for c in (*SLOT_MULT, *CREST_ADDS))
    assert HeroDamage.from_loadout("Hunter_v2").nail == 7 and HeroDamage.from_loadout("Hunter_v3").nail == 8
    assert HeroDamage.from_loadout("Reaper").nail == 5.0 and HeroDamage.from_loadout("Warrior").nail >= 16


def test_needle_and_tools_raise_the_bounds():
    for lvl, nd in enumerate(NEEDLE_DAMAGE):
        d = HeroDamage.from_loadout("Hunter", lvl)
        assert d.nail == nd and d.spear >= 15.0 * nd / 5
    assert HeroDamage.from_loadout("Hunter", 0, ("Barbed Wire",)).nail == 6      # RoundToInt(6.25)
    assert HeroDamage.from_loadout("Hunter", 0, ("Some Imbuement",)).nail >= 9  # unknown tool: bounded high
    assert HeroDamage.from_loadout("Hunter", 0, ("Weighted Anklet", "Silk Spear", None)).nail == 5.0


def test_observe_raises_only_the_hits_kind():
    d = HUNTER.observe("Slash", "Nail", 5)
    assert d is HUNTER
    d = HUNTER.observe("Needle Damage", "Heavy", 15)
    assert d is HUNTER                                  # the Silkspear's 15 leaves the nail at 5 (the STUCK cause)
    d = HUNTER.observe("Slash", "Nail", 8)
    assert d.nail == 8 and d.spear == 15 and d.raised == ("nail",)
    assert d.at(1.0).nail == 8                          # a raised bound survives the per-frame scaling
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


# ---- the kill kinds' slow motion -----------------------------------------------------------------------------------

def test_kill_windows_are_measured_per_kind_and_encounter():
    """knowledge kill_windows.json (tools/kill_window): BossDeathSlow ends 0.15-0.17 s of game time after the killing
    hit; the Forum's arena end (EnemyBattleEndSlow) and big-enemy deaths about 0.79 s; an encounter or kind with no
    measurement takes the longest measured."""
    bb, fo = KNOW.window_s("BellBeast"), KNOW.window_s("Forum")
    assert 0.15 <= bb <= KILL_WINDOW_S and KNOW.encounters["BellBeast"] == ("BossDeathSlow",)
    assert fo >= 0.75 and KNOW.window_s("Unknown Encounter") == max(KNOW.kinds.values()) >= fo
    assert kill_window_frames(FT, bb) == math.ceil((bb + KILL_MARGIN_S) * 60 - 1e-9) <= 20
    # the Forum's window does not fit a 48-frame rollout: nothing there is ever certified (the I3 rule stands)
    assert kill_window_frames(FT, fo) > 48
    ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), h=2, support_known=True, kill_window_s=fo)
    assert not kill_certified(np.zeros(4, bool), np.array([1, 2, 3, 4]), 49, ctx, FT).any()


# ---- L0: may kill, in flight, certification, U --------------------------------------------------------------------

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
    """Property (random hold-filtered streams, no rollout onsets: every press waits the whole queue): the sum of every
    press's bound reaching the HP makes the candidate may_kill when it has an own press, in_flight when only the
    prefix's presses reach it; the window starts at the press that reaches it and ends no earlier than the last
    press's latest hit."""
    rng = np.random.default_rng(seed)
    N, P, T = 64, 6, 48
    L, T1 = P + T, P + T + 1
    lat = _stream(rng, N, L, P)
    flags = np.zeros((N, T1), np.int64)
    mode = np.zeros((N, T1), np.int64)
    for hp in (4.0, 5.0, 10.0, 15.0, 30.0):
        ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), kill_hp=hp, damage=HUNTER)
        may, lo, hi, infl = kill_frames(lat, flags, mode, P, ctx)
        assert not (may & infl).any()
        for c in range(N):
            ev = sorted([(j, 5.0, "a") for j in _edges(lat[c], kin.B_ATTACK)]
                        + [(j, 15.0, "c") for j in _edges(lat[c], kin.B_QUICKCAST)])
            own = any(j >= P for j, _, _ in ev)
            cum, k_lo = 0.0, None
            for j, dmg, _ in ev:
                cum += dmg
                if k_lo is None and cum >= hp:
                    k_lo = j + 1
            assert may[c] == (own and k_lo is not None) and infl[c] == (not own and k_lo is not None)
            if k_lo is not None:
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
    may, lo, _, infl = kill_frames(lat, flags, mode, P, ctx)
    assert may.tolist() == [True, False] and lo[0] == 6 and not infl.any()
    ctx.damage = None                                  # unknown bounds: every press may kill
    assert kill_frames(lat, flags, mode, P, ctx)[0].all()
    ctx.damage = HUNTER.at(math.inf)                   # unknown target scaling: the same
    assert kill_frames(lat, flags, mode, P, ctx)[0].all()
    ctx.kill_hp = None                                 # nothing alive that can die
    assert not kill_frames(lat, flags, mode, P, ctx)[0].any()
    # the nominal onset tightens the window: onset at frame 7, side slash
    flags[1, 7:20] = kin.F_ATTACKING
    ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), kill_hp=5.0, damage=HUNTER)
    _, _, hi, _ = kill_frames(lat, flags, mode, P, ctx)
    assert hi[1] == 7 + HIT_END_F[0] + LANE_SLACK_F
    # a blow in flight: the running attack alone reaches the HP, the candidate presses nothing
    lat2 = np.zeros((1, P + T1 - 1), np.int64)
    flags2 = np.zeros((1, T1), np.int64)
    flags2[0, 0] = kin.F_ATTACKING
    may, lo, hi, infl = kill_frames(lat2, flags2, np.zeros((1, T1), np.int64), P, ctx)
    assert infl.tolist() == [True] and not may.any() and lo[0] == 1 and hi[0] > 1


@pytest.mark.parametrize("seed", range(4))
def test_certification_and_u_property(seed):
    """Properties of U (the hard veto for the candidate's own presses, the ranking key for a blow in flight): U implies
    a possible kill; I3 (GREEN, full HP, h >= 3) never vetoes; a certified plan is never vetoed; certification needs
    S = 0, h >= 2, a certified support and the kill kind's window inside the rollout."""
    rng = np.random.default_rng(seed)
    for _ in range(400):
        N, T1 = 32, int(rng.integers(30, 80))
        win = float(rng.choice([0.1668, 0.17, 0.7941, math.inf]))
        W = kill_window_frames(FT, win) if math.isfinite(win) else 10 ** 6
        S = rng.random(N) < 0.4
        k_hi = np.where(rng.random(N) < 0.2, -1, rng.integers(1, T1, N))
        may = (k_hi >= 0) & (rng.random(N) < 0.8)
        ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), hp=int(rng.integers(1, 6)), max_hp=5,
                            h=[None, 1, 2, 3][int(rng.integers(4))], tier=["GREEN", "YELLOW", "RED"][int(rng.integers(3))],
                            support_known=bool(rng.random() < 0.7), kill_window_s=win)
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


# ---- the kill commitment's clock -----------------------------------------------------------------------------------

def test_commit_frame_runs_on_game_time():
    """Before the kill the committed plan advances one rollout frame per real frame; in BossDeathSlow (0.05 speed) it
    advances 0.05 of one, so each of its frames' keys go out for about 20 real frames, and through the whole slow
    motion (0.167 s of game time) the plan moves 10 rollout frames, not the 100 real frames."""
    tg0, fo = 10.0, 1000
    assert commit_frame(tg0, fo, fo, FT, tg0, FT) == 2               # the mask for f + 2: rollout frame 2
    assert commit_frame(tg0 + 3 * FT, fo + 3, fo + 3, FT, tg0, FT) == 5
    # the slow motion: game time 0.05 per real frame
    k = [commit_frame(tg0 + 5 * FT + i * 0.05 * FT, fo + 5 + i, fo + 5 + i, 0.05 * FT, tg0, FT) for i in range(100)]
    assert k[0] == 5 and k[-1] == 10 and all(b - a in (0, 1) for a, b in zip(k, k[1:]))
    # a view k frames old (vision): extrapolated from its frame at its rate
    assert commit_frame(tg0, fo + 3, fo, FT, tg0, FT) == 5


# ---- supervisor ---------------------------------------------------------------------------------------------------

def _inp(**kw) -> SupervisorInput:
    base = dict(t=10.0, hp=3, max_hp=5, mask=MASK_NONE, support=(BODY,), support_known=True, plan_s=0,
                pausable=True, idle_clear_s=1.0)
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
    armed at the first pausable frame whose plan is S = 0 without FORCED_RISK and whose no-input path stays clear for
    the pause's latency. A hit or a heal resets the clock, on the very step too."""
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
    d = s.step(_inp(t=20.05, kill_prims=kp, next_hit_may_kill=True, idle_clear_s=0.1))
    assert not d.pause_pending                                       # the no-input path meets the support soon
    d = s.step(_inp(t=20.055, kill_prims=kp, next_hit_may_kill=True, idle_clear_s=None))
    assert not d.pause_pending                                       # unknown: not safe
    d = s.step(_inp(t=20.06, kill_prims=kp, next_hit_may_kill=True))
    assert d.pause_pending and d.quit_requested and "QS" in d.triggers and d.allowed == EVASIVE
    assert any(r.startswith("QS: stalemate") for r in d.reasons)
    # a hit dealt on the step a latched QS could fire: no quit (the latch is cleared before the triggers)
    s = Supervisor(BB)
    for k in range(0, 20 * 60 + 2):
        d = s.step(_inp(t=k / 60, kill_prims=kp, next_hit_may_kill=True, plan_s=1))
    assert s.qs is not None and not d.pause_pending
    d = s.step(_inp(t=20.1, kill_prims=kp, next_hit_may_kill=True, hit_dealt=True))
    assert not d.pause_pending and s.qs is None and d.stall_s == 0.0
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


@pytest.mark.parametrize("seed", range(3))
def test_stalemate_fires_only_at_safe_frames_property(seed):
    """Property: QS fires only on a step that is pausable, S = 0, not FORCED_RISK, with the no-input path clear for
    qs_idle_clear_s, and never on a step with a hit dealt or a heal."""
    rng = np.random.default_rng(seed)
    kp = HUNTER.kill_prims(5.0)
    s = Supervisor(BB)
    hp = 3
    for k in range(60 * 60):
        hit = rng.random() < 0.0004
        new_hp = hp + 2 if rng.random() < 0.0003 and hp < 5 else hp
        inp = _inp(t=k / 60, hp=new_hp, kill_prims=kp, next_hit_may_kill=True, plan_s=int(rng.random() < 0.2),
                   forced_risk=bool(rng.random() < 0.1), pausable=bool(rng.random() < 0.9), hit_dealt=hit,
                   idle_clear_s=[None, 0.1, 0.5, 1.0][int(rng.integers(4))])
        d = s.step(inp)
        if "QS" in d.triggers:
            assert inp.pausable and inp.plan_s == 0 and not inp.forced_risk and inp.idle_clear_s >= 0.4
            assert not hit and new_hp == hp
            break
        hp = new_hp


# ---- the supervision glue (oracle STATE) ------------------------------------------------------------------------

def _state(f: int, boss_hp: int, ev=()) -> dict:
    boss = {"iid": 1, "type_key": "Bone Beast", "hp": boss_hp, "is_dead": False, "colliders": [
        {"enabled": True, "damage": {"dealt": 2, "eff": 2, "hazard_type": 1, "can_cause_damage": True}}]}
    return {"f": f, "q": f * 166_667, "pause": {"blk": 0}, "ev": list(ev), "ents": [boss],
            "hero": {"health": 3, "max_health": 5, "health_blue": 0, "crest": "Hunter",
                     "tools": [None, "Silk Spear", None], "fractured_mask": {"equipped": False, "amount_left": 0}}}


def test_glue_the_stuck_state_keeps_the_nail():
    """Runs 20261003_175813 i2 ep 58 and the seven others: a Silkspear hit (15) earlier, then 3 HP and the boss at 15.
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


def test_glue_one_source_and_unknown_targets():
    """kill_inputs is what both the allowlist and the planner read (one value per frame); a target type without an
    audited damage scaling makes the nail able to kill it at any HP; the vision glue without an inventory audit takes
    every needle level."""
    sc = SupervisedControl(BB, support=lambda s: entity_support(s, worst_damage=2, known=True))
    st = _state(1, 30)
    dmg, hp = sc.kill_inputs(st)
    assert hp == 30.0 and dmg.nail == 5.0 and sc.kill_inputs(st) == (dmg, hp)
    d = sc.step(st, plan_s=0).decision
    assert d.kill_prims == dmg.kill_prims(hp)
    st2 = _state(2, 30)
    st2["ents"][0]["type_key"] = "Never Audited"
    dmg2, _ = sc.kill_inputs(st2)
    assert math.isinf(dmg2.nail) and Prim.ATTACK_SIDE in sc.step(st2, plan_s=0).decision.kill_prims
    assert SupervisedControl(BB, vision=True).needle_level is None
    assert SupervisedControl(BB, vision=True, needle_audited=True).needle_level == 0
    assert SupervisedControl(BB).needle_level == 0


def test_released_rise_blocks_certification():
    """Live 20261004_041626 i1 ep 0: the certified plan rose with the jump released at the kill; in BossDeathSlow the
    game's per-Update release stopped the rise at once and the hero fell 0.2-0.8 u below the plan. A plan that rises
    with the jump released between its earliest killing hit and its window's end is not certified; rising with the
    jump held, falling, or a released rise before the kill can land are fine."""
    from ssbot.combat.safety_filter import released_rise
    N, T1 = 4, 40
    vel = np.zeros((N, T1))
    lat = np.zeros((N, T1 - 1), np.int64)
    vel[0, 10:20] = 5.0                                  # rising frames 10..19, jump released: bad
    vel[1, 10:20] = 5.0
    lat[1, 9:21] = kin.B_JUMP                            # ... with the jump held: fine
    vel[2, 10:20] = -5.0                                 # falling: fine
    vel[3, 2:6] = 5.0                                    # rising released, but before the kill window: fine
    k_lo, k_end = np.full(N, 8), np.full(N, 30)
    assert released_rise(vel, lat, k_lo, k_end).tolist() == [True, False, False, False]
    ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), h=2, support_known=True, kill_window_s=0.1668)
    cert = kill_certified(np.zeros(N, bool), np.full(N, 10), T1, ctx, FT, k_lo=k_lo, vel_y=vel, latched=lat)
    assert cert.tolist() == [False, True, True, True]


def test_vision_focus_lost_alone_does_not_block_pausable_in_training():
    """The vision view's pause model counts FOCUS_LOST, which says nothing under OracleInjectSink (training runs are
    unfocused): the supervisor ignores it unless the sink is the foreground one, as input_from_state ignores STATE
    "focus" (the degraded_dust STUCK replay latched QS and never had a pausable frame)."""
    from ssbot.core.worldstate import E, PauseBlock, WorldState
    from ssbot.safety.supervisor import input_from_world
    ws = WorldState()
    ws.res.hp, ws.res.hp_max = E(3), E(5)
    ws.game.pause_available = E(False)
    ws.game.pause_blockers = int(PauseBlock.FOCUS_LOST)
    assert input_from_world(ws, 0.0, support_known=False).pausable is True
    assert input_from_world(ws, 0.0, support_known=False, foreground_sink=True).pausable is False
    ws.game.pause_blockers = int(PauseBlock.FOCUS_LOST | PauseBlock.TIME_SLOWED)
    assert input_from_world(ws, 0.0, support_known=False).pausable is False
