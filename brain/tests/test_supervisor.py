"""Supervisor v1 (DESIGN §3.7.3-3.7.4): tiers, triggers Q1-Q9, the Q4 latch and risk integral, explicit support,
an unknown hero, the primitive allowlists (PAUSE_PENDING / YELLOW / EVADE_EXIT), P1, and the §3.5.6 gates. Bell Beast
numbers: 5 masks, every attack 2 masks; the boss root iid 529544 (trial run 20261001_121446)."""
import ast
from pathlib import Path

import pytest

from ssbot.core.primitives import DAMAGING, EVASIVE, N_PRIM, Prim
from ssbot.safety import supervisor as sv
from ssbot.safety.hits_to_death import MASK_INTACT, MASK_NONE, UNBOUNDED, SupportEvent
from ssbot.safety.supervisor import Supervisor, SupervisorConfig, SupervisorInput

BODY = SupportEvent("Bone Beast", 2, instance=529544)
BELL_L = SupportEvent("BoneBeast DropBell L", 2, instance=529628)
BB = SupervisorConfig(worst_known_damage=2)          # Bell Beast: every attack is 2 masks
W1 = SupervisorConfig(worst_known_damage=1)


def _inp(**kw) -> SupervisorInput:
    base = dict(t=10.0, hp=5, max_hp=5, mask=MASK_NONE, support=(BODY,), support_known=True, plan_s=0)
    base.update(kw)
    return SupervisorInput(**base)


def test_tiers_from_h_and_plan():
    s = Supervisor(BB)
    d = s.step(_inp())
    assert (d.tier, d.h, d.pause_pending, d.triggers) == ("GREEN", 3, False, ())
    assert d.long_planning_ok and d.allows("ATTACK(side)") and d.allows("SILKSKILL(1)")
    assert s.step(_inp(plan_s=1)).tier == "YELLOW"
    assert s.step(_inp(plan_s=None)).tier == "YELLOW"              # no plan yet: not proven safe
    d = s.step(_inp(hp=4))                                         # 4 -> 2 -> dead: h = 2
    assert d.tier == "YELLOW" and d.h == 2
    r = d.restrictions
    assert r.heal_first and r.max_punish_hits == 1 and r.no_parry and r.no_killing_blow and r.no_new_fights
    assert d.allows("ATTACK(side)") and not d.allows("SILKSKILL(0)")   # below full HP: no silk skills
    d = s.step(_inp(hp=4, next_hit_may_kill=True, over_hazard=True))
    assert not d.allowed & DAMAGING and not d.allows("ATTACK(down)") and d.allows("DASH")


def test_q1_low_h_is_a_sticky_pause_pending_quit():
    s = Supervisor(BB)
    d = s.step(_inp(hp=2))
    assert d.tier == "RED" and "Q1" in d.triggers and d.pause_pending and d.quit_requested
    assert d.allowed == EVASIVE
    for name in ("MOVE", "JUMP(12)", "JUMP(max)", "DOUBLEJUMP", "DASH", "WALLJUMP", "GLIDE", "WAIT", "WAIT(4)",
                 "ABORT"):
        assert d.allows(name), name
    # the review's names: none passes while a pause is pending, known or not
    for name in ("ATTACK", "TOOL(0)", "SILKSKILL(1)", "ATTACK(down)", "ATTACK(side)", "HARPOON", "BIND", "CLAWLINE",
                 "INTERACT(UP)", "NEEDOLIN_PLAY(30)", "HIT_TARGET(lever)", "PARRY", "", "TOOL"):
        assert not d.allows(name), name
    # healing back (a heal during the loop) does not lift PAUSE_PENDING: a pause does not end the threat
    d = s.step(_inp(hp=5))
    assert d.pause_pending and d.tier == "RED" and d.quit_requested
    s.notify_paused()
    d = s.step(_inp(hp=5))
    assert d.paused and not d.pause_pending and d.allowed == frozenset()
    assert not d.allowed_mask.any()


def test_allowed_mask_matches_the_allowlist():
    d = Supervisor(BB).step(_inp(hp=4, next_hit_may_kill=True))
    m = d.allowed_mask
    assert m.shape == (N_PRIM,) and m.dtype == bool
    assert {Prim(i) for i in range(N_PRIM) if m[i]} == set(d.allowed)


def test_q1_fractured_mask_just_broken_at_one_hp():
    s = Supervisor(BB)
    assert s.step(_inp(hp=1, mask=MASK_INTACT)).h == 2
    d = Supervisor(BB).step(_inp(hp=1, mask=MASK_NONE))
    assert "Q1" in d.triggers


def test_q2_i2_without_escape():
    assert "Q2" not in Supervisor(BB).step(_inp(i2_violated=True, escape_s=0.15)).triggers
    d = Supervisor(BB).step(_inp(i2_violated=True, escape_s=0.35))
    assert "Q2" in d.triggers and d.quit_requested
    assert "Q2" in Supervisor(BB).step(_inp(i2_violated=True, escape_s=None)).triggers


def test_q3_h2_with_dangerous_support():
    # 3 HP vs the body alone: h = 2, a single covered 2-mask source: YELLOW, not Q3
    d = Supervisor(BB).step(_inp(hp=3))
    assert d.h == 2 and d.tier == "YELLOW" and not d.triggers
    assert not Supervisor(BB).step(_inp(hp=3, support=(BODY, BELL_L))).triggers     # two ENEMY sources: no Q3
    for support in ((SupportEvent("Lace", 2, hits=2),),                  # 1+1
                    (SupportEvent("spikes", 1, hazard=True), BODY),
                    (SupportEvent("Maul", 2, mask_covers=False),),
                    (SupportEvent("Judge", 1, critical=True), BODY)):
        d = Supervisor(BB).step(_inp(hp=3, support=support))
        if d.h == 2:
            assert "Q3" in d.triggers and d.pause_pending, support
        else:
            assert "Q1" in d.triggers, support


def test_q3_multi_instance_means_one_event_of_several_hits():
    """§3.7.4 multi-instance: one damage event made of hits the i-frames do not separate (SupportEvent.hits > 1),
    not several ENEMY sources (their hits are 1.0 s of i-frames apart). At h = 2 against the Bell Beast's body and
    bells the fight goes on in YELLOW with punishes limited to one hit; a 1+1 grab, a hazard, a mask bypass or
    CriticalDamage still quit."""
    bb = (SupportEvent("Bone Beast/PolyCollider", 2, instance=529544), SupportEvent("Boss Scene/BoneBeast AtkBell L", 2,
                                                                                   instance=1),
          SupportEvent("BoneBeast DropBell M2", 2, instance=2))
    d = Supervisor(BB).step(_inp(hp=3, support=bb))
    assert d.h == 2 and not d.triggers and d.tier == "YELLOW" and d.restrictions.max_punish_hits == 1
    two = (SupportEvent("Choir Clapper", 2, instance=11), SupportEvent("Choir Clapper", 2, instance=12))
    assert sv.q3_threat(two) is None
    assert sv.q3_threat((SupportEvent("grab", 2, hits=2),)) == "grab is a 2-hit event"
    # hazards, mask bypasses and CriticalDamage still quit at h = 2 (test_q3_h2_with_dangerous_support); Q1 unchanged
    assert "Q1" in Supervisor(BB).step(_inp(hp=1, support=bb)).triggers


def test_unknown_support_is_never_safe():
    """Review: a missing support used to read as UNBOUNDED / GREEN at 1 HP."""
    d = Supervisor(BB).step(_inp(hp=1, support=(), support_known=False))
    assert d.h == 1 and "Q1" in d.triggers and d.pause_pending and not d.support_known and d.tier == "RED"
    # the default input is unknown support
    d = Supervisor(BB).step(SupervisorInput(t=1.0, hp=1, max_hp=5))
    assert "Q1" in d.triggers and not d.allows("ATTACK(side)")
    # unknown at full HP: D1 >= max(1, the encounter's worst known damage); the mask is not trusted; never GREEN
    d = Supervisor(BB).step(_inp(support=(), support_known=False, mask=MASK_INTACT))
    assert d.h == 3 and d.tier == "YELLOW" and not d.long_planning_ok
    assert Supervisor(W1).step(_inp(support=(), support_known=False)).h == 5
    # h = 2 with an unknown support is a Q3 quit (review: Bell Beast at 3 HP)
    d = Supervisor(BB).step(_inp(hp=3, support=(), support_known=False))
    assert d.h == 2 and "Q3" in d.triggers and d.pause_pending
    # damage taken this attempt raises the floor
    s = Supervisor(W1)
    assert s.step(_inp(hp=3, support=(), support_known=False)).h == 3
    assert s.step(_inp(hp=3, support=(), support_known=False, damage_taken=2)).h == 2
    # a known support event larger than the floor sets D1
    d = Supervisor(BB).step(_inp(support=(SupportEvent("x", 3),), support_known=False))
    assert d.h == 2
    # review: an empty support with support_known=True (a forecaster dropout) is still unknown
    for empty in ((), []):
        d = Supervisor(BB).step(_inp(hp=1, support=empty, support_known=True))
        assert d.h == 1 and "Q1" in d.triggers and not d.support_known and d.tier == "RED", empty
        assert not d.allows("ATTACK(side)") and not d.long_planning_ok
    # only an explicitly certified empty support is "nothing can hurt"
    d = Supervisor(BB).step(_inp(hp=1, support=(), support_known=True, support_empty_ok=True))
    assert d.h == UNBOUNDED and d.tier == "GREEN" and d.support_known
    assert not Supervisor(BB).step(_inp(hp=1, support=(), support_known=False, support_empty_ok=True)).support_known


def test_missing_hero_is_unknown_not_zero_hp():
    """Review: 3 913 loading / main-menu frames without a hero section mapped to hp 0 and latched Q1."""
    s = Supervisor(BB)
    d = s.step(SupervisorInput(t=0.0, support=(BODY,), support_known=True, plan_s=0))
    assert d.h is None and not d.hero_known and not d.triggers and not d.pause_pending and d.tier == "YELLOW"
    for i in range(1, 25):
        d = s.step(SupervisorInput(t=i / 60, support=(BODY,), support_known=True, plan_s=0))
    assert "Q5" in d.triggers and d.on_paused == sv.SELF_CHECK and not d.quit_requested    # never seen > 300 ms
    # known at 5 HP, then lost: h 3 from the last known hero, no Q5 (h >= 3)
    s = Supervisor(BB)
    s.step(_inp())
    for i in range(30):
        d = s.step(_inp(hp=None, max_hp=None))
    assert d.h == 3 and not d.hero_known and not d.triggers
    # lost at 4 HP (h 2): Q5 after 300 ms
    s = Supervisor(BB)
    s.step(_inp(hp=4))
    ds = [s.step(_inp(hp=None, max_hp=None)) for _ in range(25)]
    assert "Q5" not in ds[10].triggers and "Q5" in ds[-1].triggers
    assert sv.input_from_state({"f": 1, "game": {"scene": "Bone_05"}}, 0.0, support_known=False).hp is None


def test_q4_unpredicted_hits_quit_at_the_next_pausable_green_frame():
    s = Supervisor(BB)
    assert not s.step(_inp(unpredicted_hits=1)).triggers
    d = s.step(_inp(hp=5, unpredicted_hits=1, plan_s=1))             # second unpredicted hit, not GREEN
    assert "Q4" in d.triggers and d.tier == "RED" and not d.pause_pending
    assert d.mark_retrain and d.conservative_variant and d.restrictions.no_parry
    d = s.step(_inp(pausable=False))                                 # GREEN but not pausable
    assert not d.pause_pending and "Q4" in d.triggers
    d = s.step(_inp())                                               # pausability unknown: not yet
    assert not d.pause_pending
    d = s.step(_inp(pausable=True))                                  # GREEN and pausable
    assert d.pause_pending and d.quit_requested and d.on_paused == sv.QUIT


def test_q4_risk_integral_against_twice_the_expectation():
    s = Supervisor(SupervisorConfig(2, expected_risk_per_s=1e-3, risk_warmup_s=5.0))
    # expected over the first 5 s: 5e-3, so up to 1e-2 is fine
    for i in range(9):
        assert "Q4" not in s.step(_inp(t=0.1 * i, p_death=1e-3)).triggers
    d = s.step(_inp(t=1.0, p_death=2e-3))                            # integral 1.1e-2 > 2 x 5e-3
    assert "Q4" in d.triggers and abs(d.risk_integral - 0.011) < 1e-12
    assert "Q4" not in Supervisor(BB).step(_inp(p_death=0.9)).triggers  # no training expectation yet


def test_q5_perception_self_check():
    for kw in (dict(frame_age_ms=60), dict(hud_unreadable_ms=150), dict(scene_known=False),
               dict(overlay_intrusion=True), dict(tear_streak=3)):
        d = Supervisor(BB).step(_inp(**kw))
        assert d.triggers == ("Q5",) and d.pause_pending and d.on_paused == sv.SELF_CHECK and not d.quit_requested
    assert not Supervisor(BB).step(_inp(hud_unreadable_ms=150, ending=True)).triggers
    assert not Supervisor(BB).step(_inp(hero_lost_ms=400)).triggers          # h = 3
    assert "Q5" in Supervisor(BB).step(_inp(hp=4, hero_lost_ms=400)).triggers
    # a quit trigger outranks the self-check
    s = Supervisor(BB)
    s.step(_inp(frame_age_ms=60))
    assert s.step(_inp(hp=2)).on_paused == sv.QUIT


def test_q6_forced_risk_only_at_low_h():
    assert not Supervisor(BB).step(_inp(forced_risk=True)).triggers
    assert "Q6" in Supervisor(BB).step(_inp(hp=4, forced_risk=True)).triggers


def test_q6_counts_forced_risk_within_the_design_horizon_only():
    # the best plan meets the support within H = 0.8 s (48 frames at 60 fps, inclusive), or how long it stays clear is
    # unknown: Q6 as before; clear beyond H (the adaptive horizon's open-loop contact near a charge's end, 2 s out):
    # no Q6, the attempt goes on in YELLOW and the planner re-plans every frame
    for clear in (None, 0.0, 0.4, 48 / 60, 48 * 0.016666):
        d = Supervisor(BB).step(_inp(hp=4, forced_risk=True, forced_clear_s=clear))
        assert "Q6" in d.triggers and d.pause_pending and d.quit_requested, clear
    for clear in (49 / 60, 1.2, 2.0):
        d = Supervisor(BB).step(_inp(hp=4, forced_risk=True, forced_clear_s=clear))
        assert not d.triggers and not d.pause_pending and d.tier == "YELLOW" and d.h == 2, clear
    # h >= 3: never Q6, whatever the clearance; h = 1 is Q1 anyway
    assert not Supervisor(BB).step(_inp(forced_risk=True, forced_clear_s=0.1)).triggers
    assert "Q1" in Supervisor(BB).step(_inp(hp=2, forced_risk=True, forced_clear_s=1.5)).triggers
    # the horizon is configuration (DESIGN §3.5.4 H), and a clearance without FORCED_RISK means nothing
    s = Supervisor(SupervisorConfig(worst_known_damage=2, q6_horizon_s=1.5))
    assert "Q6" in s.step(_inp(hp=4, forced_risk=True, forced_clear_s=1.2)).triggers
    assert not Supervisor(BB).step(_inp(hp=4, forced_risk=False, forced_clear_s=0.1)).triggers


def test_q7_focus_q8_watchdog_q9_stop():
    d = Supervisor(BB).step(_inp(focus_lost=True))
    assert d.release_all and d.regain_focus and d.pause_pending and d.on_paused == sv.SELF_CHECK
    d = Supervisor(BB).step(_inp(watchdog=True))
    assert d.pause_pending and d.on_paused == sv.DIAGNOSE and d.alert
    d = Supervisor(BB).step(_inp(permadeath=True, hp=1))
    assert d.stop_input and d.alert and not d.pause_pending and d.allowed == frozenset()
    d = Supervisor(BB).step(_inp(capture_lost=True))
    assert d.stop_input and "Q9" in d.triggers

    def hook(inp):
        return ["Q8"] if inp.t > 20 else []
    s = Supervisor(SupervisorConfig(2, hooks=(hook,)))
    assert not s.step(_inp(t=10)).triggers
    assert s.step(_inp(t=21)).on_paused == sv.DIAGNOSE


def test_q7_focus_only_with_a_foreground_sink():
    """Review: TRAIN runs 4-6 instances under OracleInjectSink, at most one focused; STATE focus is no Q7 there."""
    s = {"f": 1, "focus": False, "hero": {"health": 5, "max_health": 5}, "pause": {"blk": 0}}
    inp = sv.input_from_state(s, 1.0, support=(BODY,), support_known=True, plan_s=0)
    assert not inp.focus_lost
    d = Supervisor(BB).step(inp)
    assert d.tier == "GREEN" and not d.pause_pending
    assert sv.input_from_state(s, 1.0, support_known=False, foreground_sink=True).focus_lost
    s["focus"] = True
    assert not sv.input_from_state(s, 1.0, support_known=False, foreground_sink=True).focus_lost


def test_evade_exit_latch_after_a_greyed_quit():
    """§3.7.5 step 4: Quit greyed, frozen check passed -> unpause, EVADE out of the room, pause and quit. The quit
    triggers must not re-arm in that room (review: they did on the next frame)."""
    s = Supervisor(BB)
    d = s.step(_inp(hp=2, scene="Bone_05"))
    assert d.pause_pending and "Q1" in d.triggers
    s.notify_paused()
    s.notify_resumed(sv.RESUME_EVADE_EXIT, scene="Bone_05", t=10.0)
    for i in range(30):
        d = s.step(_inp(t=10.0 + i / 60, hp=2, scene="Bone_05", quittable=False))
        assert d.evade_exit and not d.pause_pending and d.allowed == EVASIVE and "Q1" in d.triggers, i
    # the next room: the latch ends and Q1 arms there
    d = s.step(_inp(t=11.0, hp=2, scene="Bone_06", quittable=False))
    assert not d.evade_exit and d.pause_pending and d.quit_requested
    assert any("EVADE_EXIT" in r for r in d.reasons)
    # quit available again in the same room ends it too
    s = Supervisor(BB)
    s.notify_resumed(sv.RESUME_EVADE_EXIT, scene="Bone_05", t=0.0)
    assert s.step(_inp(t=0.1, hp=2, scene="Bone_05", quittable=False)).evade_exit
    assert s.step(_inp(t=0.2, hp=2, scene="Bone_05", quittable=True)).pause_pending
    # a timeout alerts and re-arms
    s = Supervisor(SupervisorConfig(2, evade_exit_timeout_s=5.0))
    s.notify_resumed(sv.RESUME_EVADE_EXIT, scene="Bone_05", t=0.0)
    d = s.step(_inp(t=6.0, hp=2, scene="Bone_05", quittable=False))
    assert d.alert and d.pause_pending and not d.evade_exit
    # a self-check resume latches nothing
    s = Supervisor(BB)
    s.notify_resumed(sv.RESUME_SELF_CHECK)
    assert not s.step(_inp()).evade_exit


def test_p1_long_planning():
    assert Supervisor(BB).step(_inp()).long_planning_ok
    assert not Supervisor(BB).step(_inp(in_encounter=True)).long_planning_ok
    assert Supervisor(BB).step(_inp(in_encounter=True, in_safe_window=True)).long_planning_ok
    assert not Supervisor(BB).step(_inp(plan_s=1)).long_planning_ok


def test_silk_skills_only_at_full_hp():
    assert not Supervisor(BB).step(_inp(hp=4, max_hp=5, support=())).allows(Prim.SILKSKILL)
    assert Supervisor(BB).step(_inp()).allows(Prim.SILKSKILL)


def test_input_from_state():
    # trial run 20261001_121446 frame 43136: a Bell Beast hit at 2 HP (LethalBlock kept the hero alive), recoiling
    s = {"f": 43136, "udt": 0.01665, "focus": True,
         "hero": {"health": 2, "max_health": 5, "health_blue": 0,
                  "fractured_mask": {"equipped": False, "amount_left": 0}},
         "pause": {"blk": 3, "dsq": False, "preload": False}}
    inp = sv.input_from_state(s, t=12.0, support=(BODY,), support_known=True, plan_s=0)
    assert (inp.hp, inp.max_hp, inp.blue, inp.mask, inp.pausable, inp.quittable) == (2, 5, 0, MASK_NONE, False, False)
    assert inp.support_known
    d = Supervisor(BB).step(inp)
    assert "Q1" in d.triggers and d.pause_pending
    s["pause"]["blk"] = 0
    inp = sv.input_from_state(s, t=12.0, support_known=False)
    assert inp.pausable and inp.quittable and inp.support == () and not inp.support_known
    assert not sv.input_from_state(s, 12.0, support=(BODY,), support_known=False).support_known
    assert not sv.input_from_state(s, 12.0, support=None, support_known=True).support_known   # None is unknown
    # review: support_known is a required keyword, never inferred from the support's type
    with pytest.raises(TypeError):
        sv.input_from_state(s, 12.0, support=(BODY,))
    # oracle hero.tags (cross-module decision 5): pending damage; damage events this frame
    s["hero"]["tags"] = [{"kind": "acid", "dmg_left": 1, "t_left": 0.5}, {"kind": "frost", "dmg_left": 1}]
    s["ev"] = [{"k": "damage", "d": {"amount": 2, "hazard": "ENEMY"}}]
    inp = sv.input_from_state(s, 12.0, support=(BODY,), support_known=True)
    assert inp.pending_dmg == 2 and inp.damage_taken == 2
    for none in ([], None):              # no tag, or no TagDamageTaker (nil)
        s2 = {**s, "hero": {**s["hero"], "tags": none}}
        assert sv.input_from_state(s2, 12.0, support_known=False).pending_dmg == 0


def test_unbounded_damage_tag_is_lethal_pending_damage():
    """Review: the oracle writes dmg_left = -1 for a tag with no hit limit (frost water; state_fields_m2.md §4). Summed
    as -1 it raised h (hp 2, D1 1: h 3, GREEN); it is unbounded, so the pending damage is lethal by itself."""
    s = {"f": 1, "hero": {"health": 2, "max_health": 5, "health_blue": 0,
                          "fractured_mask": {"equipped": False, "amount_left": 0}}, "pause": {"blk": 0}}
    one = (SupportEvent("x", 1),)
    d = Supervisor(W1).step(sv.input_from_state(s, 1.0, support=one, support_known=True, plan_s=0))
    assert d.h == 2 and d.tier == "YELLOW"
    for tags in ([{"kind": "Frost", "dmg_left": -1, "t_left": 0.5}],
                 [{"kind": "Acid", "dmg_left": 1, "t_left": 0.2}, {"kind": "Frost", "dmg_left": -1, "t_left": 0.5}],
                 [{"kind": "Frost", "t_left": 0.5}], [{"kind": "Frost", "dmg_left": None}], ["Frost"]):
        s["hero"]["tags"] = tags
        inp = sv.input_from_state(s, 1.0, support=one, support_known=True, plan_s=0)
        assert inp.pending_dmg == 2 and not inp.pending_mask_covers, tags
        d = Supervisor(W1).step(inp)
        assert d.h == 0 and "Q1" in d.triggers and d.pause_pending and d.tier == "RED", tags
    # with an intact Fractured Mask the unbounded tag is still lethal (the mask is not trusted against it)
    s["hero"]["fractured_mask"] = {"equipped": True, "amount_left": 1}
    s["hero"]["tags"] = [{"kind": "Frost", "dmg_left": -1, "t_left": 0.5}]
    assert Supervisor(W1).step(sv.input_from_state(s, 1.0, support=one, support_known=True)).h == 0


def test_bind_gate():
    ok = dict(silk=9, hp=2, max_hp=5, h=1, t_min_s=1.6)
    assert sv.bind_allowed(**ok).ok
    assert not sv.bind_allowed(**{**ok, "silk": 8}).ok
    assert not sv.bind_allowed(**{**ok, "hp": 4, "h": 3}).ok          # not worth it: HP > max - 3 and h > 2
    assert sv.bind_allowed(**{**ok, "hp": 4, "h": 2}).ok
    assert not sv.bind_allowed(**{**ok, "t_min_s": 1.5}).ok            # < 1.37 + 0.15
    assert sv.bind_allowed(**{**ok, "t_min_s": 1.1, "injector_band": True}).ok
    assert not sv.bind_allowed(**{**ok, "t_min_s": 1.6, "perception_margin_s": 0.1}).ok
    assert sv.bind_allowed(**{**ok, "t_min_s": 1.45, "warding_bell": True, "p_exposed": 0.04}).ok
    # Warding Bell keeps the perception margin (review: it used to be a flat 0.05 s)
    assert not sv.bind_allowed(**{**ok, "t_min_s": 1.45, "warding_bell": True, "perception_margin_s": 0.1}).ok
    assert sv.bind_allowed(**{**ok, "t_min_s": 1.53, "warding_bell": True, "perception_margin_s": 0.1}).ok
    assert not sv.bind_allowed(**{**ok, "warding_bell": True, "p_exposed": 0.06}).ok
    assert not sv.bind_allowed(**{**ok, "p_exposed": 0.01}).ok
    for flag in ("pause_pending", "collapsing_ground", "hazard_in_envelope", "cursed"):
        assert not sv.bind_allowed(**ok, **{flag: True}).ok, flag


def test_parry_gate():
    assert sv.parry_allowed(True, 5, 0, 2, "GREEN", False).ok
    assert not sv.parry_allowed(False, 5, 0, 2, "GREEN", False).ok
    assert not sv.parry_allowed(True, 3, 0, 2, "GREEN", False).ok      # a failed parry leaves 1
    assert sv.parry_allowed(True, 3, 1, 2, "GREEN", False).ok
    assert not sv.parry_allowed(True, 4, 0, 2, "GREEN", False, pending_dmg=1).ok   # review: pending damage counts
    assert not sv.parry_allowed(True, 5, 0, 2, "YELLOW", False).ok
    assert not sv.parry_allowed(True, 5, 0, 2, "GREEN", True).ok
    assert not sv.parry_allowed(True, 5, 0, 2, "GREEN", False, lace_guard=True).ok
    assert not sv.parry_allowed(True, 5, 0, 2, "GREEN", False, vision_success=0.99).ok
    assert sv.parry_allowed(True, 5, 0, 2, "GREEN", False, vision_success=0.996).ok


def test_down_slash_gate_agrees_with_step():
    """Review: down_slash_allowed allowed a non-spike hazard in GREEN while step() forbade it; one rule now."""
    for spikes in (False, True):
        for hazard in (False, True):
            for hp, tier in ((5, "GREEN"), (4, "YELLOW")):
                d = Supervisor(BB).step(_inp(hp=hp, over_spikes=spikes, over_hazard=hazard))
                assert d.tier == tier
                assert d.allows("ATTACK(down)") == sv.down_slash_allowed(spikes, hazard, tier, False).ok, \
                    (spikes, hazard, tier)
    assert not sv.down_slash_allowed(True, True, "GREEN", False).ok
    assert sv.down_slash_allowed(False, True, "GREEN", False).ok
    assert not sv.down_slash_allowed(False, True, "YELLOW", False).ok
    assert not sv.down_slash_allowed(False, False, "GREEN", True).ok


def test_silk_gate():
    assert sv.silk_spend_allowed(9, 4, 5, 5).ok
    assert not sv.silk_spend_allowed(9, 4, 4, 5).ok                    # skill below full HP
    assert not sv.silk_spend_allowed(12, 4, 4, 5, skill=False).ok      # would leave 8 < 9
    assert sv.silk_spend_allowed(13, 4, 4, 5, skill=False).ok


def test_safety_package_never_imports_ipc_or_an_oracle_backend():
    """DESIGN §8.2 import firewall for safety/."""
    root = Path(__file__).resolve().parents[1] / "ssbot" / "safety"
    files = list(root.glob("*.py"))
    assert len(files) >= 8
    for p in files:
        for node in ast.walk(ast.parse(p.read_text("utf-8"))):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
            else:
                continue
            for m in mods:
                assert not m.startswith("ssbot.ipc") and "oracle_backend" not in m, (p.name, m)


def test_bind_reserve_at_full_hp_is_opt_in():
    # off (the default): at full HP any silk above the cost may go into a silk skill
    assert sv.silk_spend_allowed(9, 4, 5, 5).ok and sv.silk_spend_allowed(4, 4, 5, 5).ok
    # on (playbook bind.reserve_at_full_hp): never under the Bind's 9 at full HP either; below full HP as before
    v = sv.silk_spend_allowed(9, 4, 5, 5, reserve_at_full_hp=True)
    assert not v.ok and "Bind reserve" in v.reason
    assert sv.silk_spend_allowed(13, 4, 5, 5, reserve_at_full_hp=True).ok
    assert not sv.silk_spend_allowed(13, 4, 4, 5, reserve_at_full_hp=True).ok     # a skill below full HP: never
