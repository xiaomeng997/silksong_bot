"""Supervisor v1 (DESIGN §3.7.3-3.7.4): tiers, triggers Q1-Q9, the Q4 latch and risk integral, PAUSE_PENDING and
YELLOW restrictions, P1, and the §3.5.6 gates. Bell Beast numbers: 5 masks, every attack 2 masks."""
import ast
from pathlib import Path

from ssbot.safety import supervisor as sv
from ssbot.safety.hits_to_death import MASK_INTACT, MASK_NONE, SupportEvent
from ssbot.safety.supervisor import Supervisor, SupervisorConfig, SupervisorInput

BODY = SupportEvent("Bone Beast", 2)
BELL_L = SupportEvent("BoneBeast DropBell L", 2)


def _inp(**kw) -> SupervisorInput:
    base = dict(t=10.0, hp=5, max_hp=5, mask=MASK_NONE, support=(BODY,), plan_s=0)
    base.update(kw)
    return SupervisorInput(**base)


def test_tiers_from_h_and_plan():
    s = Supervisor()
    d = s.step(_inp())
    assert (d.tier, d.h, d.pause_pending, d.triggers) == ("GREEN", 3, False, ())
    assert d.long_planning_ok and "PARRY" not in d.forbidden
    assert s.step(_inp(plan_s=1)).tier == "YELLOW"
    assert s.step(_inp(plan_s=None)).tier == "YELLOW"              # no plan yet: not proven safe
    d = s.step(_inp(hp=4))                                         # 4 -> 2 -> dead: h = 2
    assert d.tier == "YELLOW" and d.h == 2
    r = d.restrictions
    assert r.heal_first and r.max_punish_hits == 1 and r.no_parry and r.no_killing_blow and r.no_new_fights
    assert "PARRY" in d.forbidden and "ATTACK_SIDE" not in d.forbidden
    d = s.step(_inp(hp=4, next_hit_may_kill=True, over_hazard=True))
    assert {"ATTACK_SIDE", "TOOL", "SILKSKILL", "ATTACK_DOWN"} <= d.forbidden and "DASH" not in d.forbidden


def test_q1_low_h_is_a_sticky_pause_pending_quit():
    s = Supervisor()
    d = s.step(_inp(hp=2))
    assert d.tier == "RED" and "Q1" in d.triggers and d.pause_pending and d.quit_requested
    assert d.forbidden == sv.PAUSE_PENDING_FORBIDDEN
    assert not d.forbidden & {"MOVE", "JUMP", "DASH", "WAIT", "ABORT"}
    assert {"ATTACK_SIDE", "ATTACK_DOWN", "PARRY", "TOOL", "SILKSKILL", "BIND", "INTERACT", "CLAWLINE"} <= d.forbidden
    # healing back (a heal during the loop) does not lift PAUSE_PENDING: a pause does not end the threat
    d = s.step(_inp(hp=5))
    assert d.pause_pending and d.tier == "RED" and d.quit_requested
    s.notify_paused()
    d = s.step(_inp(hp=5))
    assert d.paused and not d.pause_pending and d.forbidden == sv.PRIMITIVES


def test_q1_fractured_mask_just_broken_at_one_hp():
    s = Supervisor()
    assert s.step(_inp(hp=1, mask=MASK_INTACT)).h == 2
    d = Supervisor().step(_inp(hp=1, mask=MASK_NONE))
    assert "Q1" in d.triggers


def test_q2_i2_without_escape():
    assert "Q2" not in Supervisor().step(_inp(i2_violated=True, escape_s=0.15)).triggers
    d = Supervisor().step(_inp(i2_violated=True, escape_s=0.35))
    assert "Q2" in d.triggers and d.quit_requested
    assert "Q2" in Supervisor().step(_inp(i2_violated=True, escape_s=None)).triggers


def test_q3_h2_with_dangerous_support():
    # 3 HP vs the body alone: h = 2, a single covered 2-mask source: YELLOW, not Q3
    d = Supervisor().step(_inp(hp=3))
    assert d.h == 2 and d.tier == "YELLOW" and not d.triggers
    for support in ((BODY, BELL_L),                                      # two instances
                    (SupportEvent("Lace", 2, hits=2),),                  # 1+1
                    (SupportEvent("spikes", 1, hazard=True), BODY),
                    (SupportEvent("Maul", 2, mask_covers=False),),
                    (SupportEvent("Judge", 1, critical=True), BODY)):
        d = Supervisor().step(_inp(hp=3, support=support))
        if d.h == 2:
            assert "Q3" in d.triggers and d.pause_pending, support
        else:
            assert "Q1" in d.triggers, support


def test_q4_unpredicted_hits_quit_at_the_next_pausable_green_frame():
    s = Supervisor()
    assert not s.step(_inp(unpredicted_hits=1)).triggers
    d = s.step(_inp(hp=5, unpredicted_hits=1, plan_s=1))             # second unpredicted hit, not GREEN
    assert "Q4" in d.triggers and d.tier == "RED" and not d.pause_pending
    assert d.mark_retrain and d.conservative_variant and d.restrictions.no_parry
    d = s.step(_inp(pausable=False))                                 # GREEN but not pausable
    assert not d.pause_pending and "Q4" in d.triggers
    d = s.step(_inp())                                               # GREEN and pausable
    assert d.pause_pending and d.quit_requested and d.on_paused == sv.QUIT


def test_q4_risk_integral_against_twice_the_expectation():
    s = Supervisor(SupervisorConfig(expected_risk_per_s=1e-3, risk_warmup_s=5.0))
    # expected over the first 5 s: 5e-3, so up to 1e-2 is fine
    for i in range(9):
        assert "Q4" not in s.step(_inp(t=0.1 * i, p_death=1e-3)).triggers
    d = s.step(_inp(t=1.0, p_death=2e-3))                            # integral 1.1e-2 > 2 x 5e-3
    assert "Q4" in d.triggers and abs(d.risk_integral - 0.011) < 1e-12
    assert "Q4" not in Supervisor().step(_inp(p_death=0.9)).triggers  # no training expectation yet


def test_q5_perception_self_check():
    for kw in (dict(frame_age_ms=60), dict(hud_unreadable_ms=150), dict(scene_known=False),
               dict(overlay_intrusion=True), dict(tear_streak=3)):
        d = Supervisor().step(_inp(**kw))
        assert d.triggers == ("Q5",) and d.pause_pending and d.on_paused == sv.SELF_CHECK and not d.quit_requested
    assert not Supervisor().step(_inp(hud_unreadable_ms=150, ending=True)).triggers
    assert not Supervisor().step(_inp(hero_lost_ms=400)).triggers          # h = 3
    assert "Q5" in Supervisor().step(_inp(hp=4, hero_lost_ms=400)).triggers
    # a quit trigger outranks the self-check
    s = Supervisor()
    s.step(_inp(frame_age_ms=60))
    assert s.step(_inp(hp=2)).on_paused == sv.QUIT


def test_q6_forced_risk_only_at_low_h():
    assert not Supervisor().step(_inp(forced_risk=True)).triggers
    assert "Q6" in Supervisor().step(_inp(hp=4, forced_risk=True)).triggers


def test_q7_focus_q8_watchdog_q9_stop():
    d = Supervisor().step(_inp(focus_lost=True))
    assert d.release_all and d.regain_focus and d.pause_pending and d.on_paused == sv.SELF_CHECK
    d = Supervisor().step(_inp(watchdog=True))
    assert d.pause_pending and d.on_paused == sv.DIAGNOSE and d.alert
    d = Supervisor().step(_inp(permadeath=True, hp=1))
    assert d.stop_input and d.alert and not d.pause_pending and d.forbidden == sv.PRIMITIVES
    d = Supervisor().step(_inp(capture_lost=True))
    assert d.stop_input and "Q9" in d.triggers

    def hook(inp):
        return ["Q8"] if inp.t > 20 else []
    s = Supervisor(SupervisorConfig(hooks=(hook,)))
    assert not s.step(_inp(t=10)).triggers
    assert s.step(_inp(t=21)).on_paused == sv.DIAGNOSE


def test_p1_long_planning():
    assert Supervisor().step(_inp()).long_planning_ok
    assert not Supervisor().step(_inp(in_encounter=True)).long_planning_ok
    assert Supervisor().step(_inp(in_encounter=True, in_safe_window=True)).long_planning_ok
    assert not Supervisor().step(_inp(plan_s=1)).long_planning_ok


def test_silk_skills_only_at_full_hp():
    assert "SILKSKILL" in Supervisor().step(_inp(hp=4, max_hp=5, support=())).forbidden
    assert "SILKSKILL" not in Supervisor().step(_inp()).forbidden


def test_input_from_state():
    # trial run 20261001_121446 frame 43136: a Bell Beast hit at 2 HP (LethalBlock kept the hero alive), recoiling
    s = {"f": 43136, "udt": 0.01665, "focus": True,
         "hero": {"health": 2, "max_health": 5, "health_blue": 0,
                  "fractured_mask": {"equipped": False, "amount_left": 0}},
         "pause": {"blk": 3, "dsq": False, "preload": False}}
    inp = sv.input_from_state(s, t=12.0, support=(BODY,), plan_s=0)
    assert (inp.hp, inp.max_hp, inp.blue, inp.mask, inp.pausable, inp.quittable) == (2, 5, 0, MASK_NONE, False, False)
    d = Supervisor().step(inp)
    assert "Q1" in d.triggers and d.pause_pending
    s["pause"]["blk"] = 0
    s["focus"] = False
    inp = sv.input_from_state(s, t=12.0)
    assert inp.pausable and inp.quittable and inp.focus_lost and inp.support == ()


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
    assert not sv.bind_allowed(**{**ok, "warding_bell": True, "p_exposed": 0.06}).ok
    assert not sv.bind_allowed(**{**ok, "p_exposed": 0.01}).ok
    for flag in ("pause_pending", "collapsing_ground", "hazard_in_envelope", "cursed"):
        assert not sv.bind_allowed(**ok, **{flag: True}).ok, flag


def test_parry_gate():
    assert sv.parry_allowed(True, 5, 0, 2, "GREEN", False).ok
    assert not sv.parry_allowed(False, 5, 0, 2, "GREEN", False).ok
    assert not sv.parry_allowed(True, 3, 0, 2, "GREEN", False).ok      # a failed parry leaves 1
    assert sv.parry_allowed(True, 3, 1, 2, "GREEN", False).ok
    assert not sv.parry_allowed(True, 5, 0, 2, "YELLOW", False).ok
    assert not sv.parry_allowed(True, 5, 0, 2, "GREEN", True).ok
    assert not sv.parry_allowed(True, 5, 0, 2, "GREEN", False, lace_guard=True).ok
    assert not sv.parry_allowed(True, 5, 0, 2, "GREEN", False, vision_success=0.99).ok
    assert sv.parry_allowed(True, 5, 0, 2, "GREEN", False, vision_success=0.996).ok


def test_down_slash_and_silk_gates():
    assert not sv.down_slash_allowed(True, True, "GREEN", False).ok
    assert sv.down_slash_allowed(False, True, "GREEN", False).ok
    assert not sv.down_slash_allowed(False, True, "YELLOW", False).ok
    assert not sv.down_slash_allowed(False, False, "GREEN", True).ok
    assert sv.silk_spend_allowed(9, 4, 5, 5).ok
    assert not sv.silk_spend_allowed(9, 4, 4, 5).ok                    # skill below full HP
    assert not sv.silk_spend_allowed(12, 4, 4, 5, skill=False).ok      # would leave 8 < 9
    assert sv.silk_spend_allowed(13, 4, 4, 5, skill=False).ok


def test_safety_package_never_imports_ipc_or_an_oracle_backend():
    """DESIGN §8.2 import firewall for safety/."""
    root = Path(__file__).resolve().parents[1] / "ssbot" / "safety"
    files = list(root.glob("*.py"))
    assert len(files) >= 7
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
