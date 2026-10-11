"""GauntletTactics, the Forum's L2 target layer v0 (forum_planner_plan R6, combat.tactics.gauntlet): the far-target
scenario (pick the far enemy in a long recovery when its window covers the run, not when it does not), the person's
rules (isolated -> rush, spread -> fastest pursuer, clustered -> kite, Tinies -> under the Maestro, Clawmaiden first,
Minister last), the Clapper controller, and §4.4 item 4 (L2 failing -> LOCAL's prefs bit for bit)."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat.multi_forecast import Subject
from ssbot.combat.tactics.forum_local import ForumTactics, clapper_facing, load_forum_playbook
from ssbot.combat.tactics.gauntlet import (GLIDE_SPIKE, KITE, PUNISH, RUSH, GauntletTactics, L2Rules, jump_landing,
                                           load_l2_rules)
from ssbot.core.worldstate import E, Entity, Ev, Event, HitDealt, WorldState

FLOOR = 5.6
CH, EN, RE, MI, CM, MA, AT, CC = ("Song Pilgrim 03", "Song Pilgrim 01", "Song Reed", "Song Administrator",
                                  "Song Handmaiden", "Song Pilgrim Maestro", "Song Automaton Tiny", "Song Heavy Sentry")


class WinFc:
    """A fake MultiForecast: covers[(x0, x1)] = t -> a floor spot in [x0, x1] is in support from t s on (inf: never;
    default 0.3 s: an idle enemy's next attack); t_min for LOCAL's EVADE test."""

    def __init__(self, subjects, covers=(), t_min=0.2, default=0.3):
        self.subjects, self.covers, self._t, self.default = subjects, list(covers), t_min, default

    def occupied(self, x, y, tk, comfort=False):
        x = np.asarray(x, float)
        tk = np.asarray(tk, float)
        out = np.zeros(x.shape, bool)
        for i in range(x.shape[0]):
            t = self.default
            for x0, x1, tc in self.covers:
                if x0 <= x[i, 0] <= x1:
                    t = tc
            out[i] = tk >= t
        return out

    def t_min(self, x, y, t_max=3.0, subject=None):
        return min(self._t, t_max)


def subj(iid, tk, x, y=5.0, state="Idle", family=None, committed=False, t_free=None):
    t_free = (1.0 if committed else 0.0) if t_free is None else t_free
    return Subject(iid, tk, True, True, committed, family, state, 50.0, 1.0, (x, y), t_free, 1.0)


def world(x=20.0, y=FLOOR, hp=7, silk=0, ents=(), t=10.0, events=()):
    ws = WorldState()
    ws.hero.pos = E((x, y))
    ws.res.hp, ws.res.hp_max, ws.res.silk = E(hp), E(7), E(silk)
    ws.entities = list(ents)
    ws.stamp.t_game_s = t
    ws.events = list(events)
    return ws


def clapper(iid, x, flip, y=7.45):
    return Entity(id=iid, type_key=E(CC), pos=E((x, y - 2.5)), pos_transform=(x, y), flip_x=flip)


def l2(**kw):
    pb, rules = load_forum_playbook()
    r = load_l2_rules()
    for k, v in kw.items():
        setattr(r, k, v)
    return GauntletTactics(ForumTactics(pb, rules, FLOOR), r)


def test_far_target_with_a_long_window_is_picked():
    t = l2()
    near = subj(1, CH, 22.0)                                       # idle: its spot covered from 0.3 s
    far = subj(2, EN, 33.0, state="Slash Recover", family="EN_SLASH", committed=True)
    fc = WinFc([near, far], covers=[(30.0, 32.0, 1.4)])           # the far spot (31.2) clear for 1.4 s
    p = t.decide(world(20.0), fc, None, 3)
    assert p.goal == PUNISH and p.target == 2
    assert p.stance_x == pytest.approx(31.2)
    assert p.hit_w[2] > p.hit_w[1] > 0
    # the window must cover the run (0.05 + 11.2 / 17.5 = 0.69 s) + the swing (0.25) + the margin (0.1)
    t_run = 0.05 + 11.2 / 17.5
    assert 1.4 >= t_run + 0.25 + 0.10


def test_far_target_with_a_short_window_is_not_picked():
    t = l2()
    near = subj(1, CH, 22.0)
    far = subj(2, EN, 33.0, state="Slash Recover", family="EN_SLASH", committed=True)
    p = t.decide(world(20.0), WinFc([near, far], covers=[(30.0, 32.0, 0.8)]), None, 3)
    assert p.target == 1 and p.goal == RUSH                       # spread: the fastest pursuer (the near one)
    t = l2()
    p = t.decide(world(20.0), WinFc([near, far], covers=[(30.0, 32.0, 0.8), (19.0, 21.0, 0.5)]), None, 3)
    assert p.goal == PUNISH and p.target == 1                     # the near one's own window covers its swing


def test_isolated_rush_and_clustered_kite():
    t = l2()
    s = [subj(1, CH, 30.0), subj(2, RE, 32.0), subj(3, EN, 42.0)]
    p = t.decide(world(20.0), WinFc(s), None, 3)
    assert p.goal == RUSH and p.target == 3                       # the isolated one
    t = l2()
    s = [subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 36.0)]
    p = t.decide(world(20.0, ents=()), WinFc(s, t_min=9.0), None, 3)
    assert p.goal == KITE
    # fastest pursuer: ETA = max(0, d - 1.8) / speed: Choristor 8.2 / 9.69 = 0.85 < Envoy 14.2 / 8.14, Reed 11.2 / 4.63
    assert p.target == 1
    assert p.stance_x == pytest.approx(22.0)                      # 8 u from it, on its side away from the others
    # LOCAL's EVADE (the hero's spot covered within 0.6 s) stands against KITE
    t = l2()
    p = t.decide(world(20.0), WinFc(s, t_min=0.2), None, 3)
    assert p.mode == "EVADE" and t.last["goal"] == "KITE(EVADE)"


def test_tinies_kite_under_the_maestro():
    t = l2()
    s = [subj(1, MA, 25.0, y=10.8), subj(2, AT, 27.0, y=9.0), subj(3, AT, 28.0, y=9.5)]
    p = t.decide(world(35.0), WinFc(s, t_min=9.0), None, 3)
    assert p.goal == KITE and p.stance_x == pytest.approx(25.0)


def test_clawmaiden_first_minister_last():
    t = l2()
    s = [subj(1, RE, 22.0, y=9.0), subj(2, CM, 40.0, y=9.0)]
    p = t.decide(world(20.0), WinFc(s), None, 3)
    assert p.target == 2
    t = l2()
    s = [subj(1, MI, 26.0, y=9.0), subj(2, RE, 34.0, y=9.0)]
    p = t.decide(world(20.0), WinFc(s), None, 3)
    assert p.target == 2                                          # the Minister (6 u) waits for the Reed (14 u)
    assert p.stance_x == pytest.approx(34.0)                      # under the flyer


def test_clapper_controller():
    # idle: face it on the hero's side, 4 u (its body reaches 2.25 u in front)
    t = l2()
    s = [subj(9, CC, 30.0, y=7.45)]
    p = t.decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p.target == 9 and p.stance_x == pytest.approx(26.0)
    # the slam: step out in front (facing left, the hero in front), or stay behind with the hero behind it
    t = l2()
    s = [subj(9, CC, 35.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]
    p = t.decide(world(30.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(22.0)
    t = l2()
    p = t.decide(world(38.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(38.5)
    # the jump: behind its "landing" judged from where both are now (forum.md 21.7.1), in time: under it and behind
    t = l2()
    s = [subj(9, CC, 35.0, y=7.45, state="Jump Antic", family="CC_JUMP", committed=True)]
    p = t.decide(world(26.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    land = jump_landing(35.0, 26.0, -1.0)
    assert land == pytest.approx(35.0 + 0.92 * (31.0 - 35.0))
    assert p.stance_x == pytest.approx(land + 2.5) and t.last["goal_why"].endswith("jump: under and behind")
    s = [subj(9, CC, 33.0, y=12.0, state="Air", family="CC_JUMP", committed=True)]
    p = t.decide(world(30.0, ents=[clapper(9, 33.0, False)]), WinFc(s), None, 3)
    # from where both are now: behind its landing (37.34) leaves 11.7 u to the right wall, under corner_room_u
    # (13 u, forum.md 44): back off in front of the landing instead
    assert p.stance_x == pytest.approx(jump_landing(33.0, 30.0, -1.0) - 8.5)
    assert t.last["goal_why"].endswith("jump: back off")
    t.rules.corner_room_u = 0.0                                   # the rule off: under it and behind
    p = t.decide(world(30.0, ents=[clapper(9, 33.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(jump_landing(33.0, 30.0, -1.0) + 2.5)
    assert p.hit_w[9] == pytest.approx(3.0 * 1.5)                 # up slashes on the way under it
    # the cast: face it, the glide-spike hook on
    t = l2()
    s = [subj(9, CC, 30.0, y=7.45, state="Spell Antic", family="CC_CAST", committed=True)]
    p = t.decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert GLIDE_SPIKE in p.vocab and p.stance_x == pytest.approx(26.0)


def test_two_clappers_never_attack_together():
    s = [subj(1, CC, 21.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True), subj(2, CC, 38.0, y=7.45)]
    ents = [clapper(1, 21.0, True), clapper(2, 38.0, False)]
    p = l2().decide(world(28.0, ents=ents), WinFc(s), None, 3)
    assert p.target == 2                                          # the idle one while the other one attacks
    s[0] = subj(1, CC, 21.0, y=7.45)
    p = l2().decide(world(28.0, ents=ents), WinFc(s), None, 3)
    assert p.target == 1                                          # both idle: the fastest pursuer (the nearer)


def test_clapper_facing_from_flip_x():
    assert clapper_facing(clapper(1, 30.0, True)) == 1 and clapper_facing(clapper(1, 30.0, False)) == -1
    assert clapper_facing(NS(facing=NS(v=-1, conf=1.0))) == -1     # no flip_x (tests): the facing


def _same(a, b) -> bool:
    for k in a.__dataclass_fields__:
        x, y = getattr(a, k), getattr(b, k)
        if isinstance(x, np.ndarray) or isinstance(y, np.ndarray):
            if not np.array_equal(x, y):
                return False
        elif x != y and not (isinstance(x, float) and math.isnan(x) and math.isnan(y)):
            return False
    return True


@pytest.mark.parametrize("case", ["fail", "error", "off"])
def test_l2_failure_is_local_bit_for_bit(case):
    s = [subj(1, CH, 22.0), subj(2, EN, 33.0, state="Slash Recover", family="EN_SLASH", committed=True)]
    pb, rules = load_forum_playbook()
    local = ForumTactics(pb, rules, FLOOR)
    for t_min in (0.2, 9.0):
        fc = WinFc(s, covers=[(30.0, 32.0, 1.4)], t_min=t_min)
        want = local.decide(world(20.0), fc, None, 3)
        t = l2(fail_p=1.0 if case == "fail" else 0.0, enabled=case != "off")
        if case == "error":
            def boom(*a, **k):
                raise RuntimeError("injected")
            t.candidates = boom
        got = t.decide(world(20.0), fc, None, 3)
        assert _same(got, want)
    if case == "error":
        assert t.stats["errors"] == 1 and "injected" in t.last["l2_error"]
    if case == "fail":
        assert t.stats["fails"] == 1


def test_switch_and_rules_loading():
    assert not load_l2_rules(env="0").enabled and load_l2_rules(env="fail:0.1").fail_p == pytest.approx(0.1)
    assert load_l2_rules(env="on").enabled
    with pytest.raises(ValueError):
        load_l2_rules(env="maybe")
    with pytest.raises(KeyError):
        L2Rules.from_dict({"nope": 1})


def test_punish_hit_inside_the_window_is_counted():
    t = l2()
    near = subj(1, CH, 22.0)
    far = subj(2, EN, 33.0, state="Slash Recover", family="EN_SLASH", committed=True)
    fc = WinFc([near, far], covers=[(30.0, 32.0, 1.4)])
    t.decide(world(20.0, t=10.0), fc, None, 3)
    hit = Event(Ev.HIT_DEALT, 0, 10.5, HitDealt(2, EN, 9.0, 20.0, attack="Nail", src="Slash"))
    t.decide(world(31.0, t=10.5, events=[hit]), fc, None, 3)
    st = t.stats_dict()
    assert st["punish_goals"] == 1 and st["punish_landed"] == 1 and st["goal_hits"]["PUNISH"] == 1


R2_HOLD = dict(dwell_s=4.0, goal_dwell_s=1.0, switch_x=1.5, rule_hyst_u=0.0)     # round 2's holding (17.6.1)


def _run(t, ss, hx, at, n=6, t_min=0.2, covers=()):
    """n decisions at game time `at` (n = period: one periodic pick among them)."""
    p = None
    for _ in range(n):
        p = t.decide(world(hx, t=at), WinFc(ss, covers=covers, t_min=t_min), None, 3)
    return p


def test_a_kept_target_is_held_for_the_dwell():
    # round 2: the round-1 A/B changed goals 33 times a minute in wave 0; another target needs switch_x and dwell_s
    t = l2(**R2_HOLD)
    a, b = subj(1, CH, 30.0), subj(2, EN, 45.0)
    p = t.decide(world(20.0, t=10.0), WinFc([a, b]), None, 3)
    assert p.goal == RUSH and p.target == 1                       # spread: the fastest pursuer
    b = subj(2, EN, 15.0)                                         # now the nearer (ETA 0.39 s against 0.85 s)
    assert _run(t, [a, b], 20.0, 10.5).target == 1                # held: 0.5 s < dwell 4 s
    assert _run(t, [a, b], 20.0, 13.2).target == 1
    assert _run(t, [a, b], 20.0, 14.2).target == 2                # then the switch (score x 1.78 >= 1.5)
    st = t.stats_dict()
    assert st["tgt_switches"] == 1 and st["switches"] == 1


def test_a_move_change_of_the_target_does_not_drop_it():
    t = l2()
    a, b = subj(1, CH, 30.0), subj(2, EN, 45.0)
    t.decide(world(20.0, t=10.0), WinFc([a, b]), None, 3)
    a = subj(1, CH, 30.0, state="Slash Antic", family="CH_SLASH", committed=True)
    b = subj(2, EN, 15.0)
    picks = t.stats["picks"]
    p = t.decide(world(20.0, t=10.2), WinFc([a, b]), None, 3)
    assert p.target == 1 and t.stats["picks"] == picks + 1        # the event picked once and kept the target
    p = t.decide(world(20.0, t=10.22), WinFc([a, b]), None, 3)
    assert p.target == 1 and t.stats["picks"] == picks + 1        # handled: no pick on every tick after it


def test_an_opening_and_a_rule_change_do_not_wait():
    # PUNISH (rank 2) takes over inside the dwell
    t = l2(**R2_HOLD)
    a, b = subj(1, CH, 30.0), subj(2, EN, 45.0)
    t.decide(world(20.0, t=10.0), WinFc([a, b]), None, 3)
    b = subj(2, EN, 15.0, state="Slash Recover", family="EN_SLASH", committed=True)
    p = _run(t, [a, b], 20.0, 10.2, covers=[(16.0, 18.0, 1.5)])  # its spot (16.8) clear for 1.5 s
    assert p.goal == PUNISH and p.target == 2
    # the same target under another rule (isolated -> clustered: RUSH -> KITE) after goal_dwell_s
    t = l2(**R2_HOLD)
    a, b = subj(1, CH, 30.0), subj(2, EN, 45.0)
    t.decide(world(20.0, t=10.0), WinFc([a, b], t_min=9.0), None, 3)
    b = subj(2, EN, 36.0)                                         # 6 u: the kept one still isolated (8 - 2 u)
    assert _run(t, [a, b], 20.0, 10.3, t_min=9.0).goal == RUSH
    b = subj(2, EN, 35.0)
    assert _run(t, [a, b], 20.0, 10.9, t_min=9.0).goal == RUSH    # 0.9 s < goal_dwell 1 s
    p = _run(t, [a, b], 20.0, 11.1, t_min=9.0)
    assert p.goal == KITE and p.target == 1 and t.stats["tgt_switches"] == 0


def test_a_rush_target_that_gets_company_is_kited_with_then_left():
    # RUSH on the Choristor (all spread); the Reed comes within 3 u of it while the Envoy is alone: KITE on the
    # Choristor until dwell_s (no switch), then RUSH the isolated Envoy (the kept one not eligible: no hysteresis)
    t = l2(**R2_HOLD)
    s = [subj(1, CH, 30.0), subj(2, RE, 40.0), subj(3, EN, 48.0)]
    p = t.decide(world(20.0, t=10.0), WinFc(s, t_min=9.0), None, 3)
    assert p.goal == RUSH and p.target == 1
    s = [subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 48.0)]
    assert _run(t, s, 20.0, 10.6, t_min=9.0).goal == RUSH         # the rule held goal_dwell_s (on the kept one)
    p = _run(t, s, 20.0, 11.1, t_min=9.0)
    assert p.goal == KITE and p.target == 1 and t.stats["tgt_switches"] == 0
    p = _run(t, s, 20.0, 14.1, t_min=9.0)
    assert p.goal == RUSH and p.target == 3 and t.stats["tgt_switches"] == 1
    assert t.stats["switch_kinds"] == {"ineligible": 1}


def test_the_idle_clappers_turn_does_not_wait():
    # (ETA 0.66 s against 0.87 s; with the other one in its slam the idle one's priority x 2: 0.44 s)
    t = l2()
    s = [subj(1, CC, 22.0, y=7.45), subj(2, CC, 40.0, y=7.45)]
    ents = [clapper(1, 22.0, False), clapper(2, 40.0, True)]
    p = t.decide(world(30.0, t=10.0, ents=ents), WinFc(s), None, 3)
    assert p.target == 1
    s[0] = subj(1, CC, 22.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)
    p = t.decide(world(30.0, t=10.2, ents=ents), WinFc(s), None, 3)
    assert p.target == 2                                          # its turn: inside the dwell


def test_a_spot_past_the_window_query_is_no_punish():
    # the run + swing past window_max_s (2 s): the spot is not checked that far, so no PUNISH even with no cover
    # (round 2: such far spots read window inf and two of them flip-flopped as PUNISH every pick)
    t = l2()
    far = subj(2, EN, 47.0, state="Slash Recover", family="EN_SLASH", committed=True)
    p = t.decide(world(15.0), WinFc([far], default=math.inf), None, 3)
    assert p.goal != PUNISH                                       # t_run 0.05 + 30.2 / 17.5 = 1.78 s, + 0.35 > 2 s
    t = l2()
    near = subj(2, EN, 30.0, state="Slash Recover", family="EN_SLASH", committed=True)
    p = t.decide(world(15.0), WinFc([near], default=math.inf), None, 3)
    assert p.goal == PUNISH and t.last["l2_cands"][0][2] == 9.0  # inside the query: open (inf, logged as 9)


def test_clapper_jump_judged_from_now():
    # v4's rule (live w7: 1 crossing under it in 25 jumps, 0 body hits; forum.md 21.7.1), judged every tick from where
    # the hero and it are now: behind its "landing" while the run gets there 0.25 s before it lands and does not
    # cross its body on the ground, else back off in front of it
    ents = [clapper(9, 35.0, False)]
    jmp = dict(y=7.45, family="CC_JUMP", committed=True)
    t = l2()
    t.decide(world(26.0, t=10.0, ents=ents), WinFc([subj(9, CC, 35.0, state="Jump Antic", **jmp)]), None, 3)
    assert t.last["goal_why"].endswith("jump: under and behind")
    # 1.0 s in (lands at 1.415 s): 0.45 s of run > 0.415 - 0.25 -> back off past its landing slam, no hit reward
    p = t.decide(world(26.0, t=11.0, ents=[clapper(9, 33.0, False)]),
                 WinFc([subj(9, CC, 33.0, state="Air", **jmp)]), None, 3)
    assert t.last["goal_why"].endswith("jump: back off")
    assert p.stance_x == pytest.approx(jump_landing(33.0, 26.0, -1.0) - 8.5) and p.hit_w.get(9, 0.0) == 0.0
    # at its face (3 u) on the ground: behind it is through its body -> back off
    t = l2()
    p = t.decide(world(32.0, t=10.0, ents=ents), WinFc([subj(9, CC, 35.0, state="Jump Antic", **jmp)]), None, 3)
    assert t.last["goal_why"].endswith("jump: back off")
    assert p.stance_x == pytest.approx(jump_landing(35.0, 32.0, -1.0) - 8.5)
    # CC_JUMP_CAST near the right wall: past the rune circle (14.5 u in front) when there is room, else under it
    t = l2()
    cast = dict(y=7.45, family="CC_JUMP_CAST", committed=True)
    p = t.decide(world(30.0, t=10.0, ents=[clapper(9, 44.0, False)]),
                 WinFc([subj(9, CC, 44.0, state="Air", **cast)]), None, 3)
    land = jump_landing(44.0, 30.0, -1.0)
    assert "under and behind" in t.last["goal_why"] and p.stance_x == pytest.approx(land + 2.5)
    p = t.decide(world(30.0, t=11.5, ents=[clapper(9, 44.0, False)]),
                 WinFc([subj(9, CC, 44.0, state="Air", **cast)]), None, 3)
    assert "no room out" in t.last["goal_why"] or p.stance_x == pytest.approx(land - 14.5)


def test_the_idle_clappers_turn_needs_its_spot_in_time():
    # the busy one's slam can end in 0.3 s: the idle one's spot (6 u off, 0.39 s) is not reached in time -> no turn
    s = [subj(1, CC, 22.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True, t_free=0.3),
         subj(2, CC, 40.0, y=7.45)]
    ents = [clapper(1, 22.0, False), clapper(2, 40.0, True)]
    t = l2()
    t.decide(world(30.0, t=10.0, ents=ents), WinFc([subj(1, CC, 22.0, y=7.45), s[1]]), None, 3)
    p = t.decide(world(30.0, t=10.2, ents=ents), WinFc(s), None, 3)
    assert p.target == 1 and t.stats["tgt_switches"] == 0


def test_clapper_slam_with_no_room_out_stays_in_front():
    # out 13 u in front is past the left wall: as far out as the wall lets, not behind it (through its body)
    t = l2()
    s = [subj(9, CC, 26.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]
    p = t.decide(world(22.0, ents=[clapper(9, 26.0, False)]), WinFc(s), None, 3)
    x0, _ = t.pb.arena_x
    assert p.stance_x == pytest.approx(x0 + t.rules.wall_room_u) and t.last["goal_why"].endswith("out to the wall")


def test_clapper_retreat_branches_do_not_reward_hitting_it():
    # stepping out of its slam: its hit weight 0 (the stance pulls out, a hit weight would pull back in)
    t = l2()
    s = [subj(9, CC, 35.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]
    p = t.decide(world(30.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    assert t.last["goal_why"].endswith("slam: step out") and p.hit_w.get(9, 0.0) == 0.0
    # face: the target's weight
    t = l2()
    p = t.decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc([subj(9, CC, 30.0, y=7.45)]), None, 3)
    assert p.hit_w[9] == pytest.approx(3.0)


@pytest.fixture(scope="module")
def prod_tables():
    from ssbot.combat import enemy_tables as et
    if not (et.FORUM_DIR / "ChoirClapper_hitboxes.npz").exists():
        pytest.skip("the Forum tables' npz files are not built here (behaviour_build --encounter Forum)")
    return et.EnemyTables.production()


def _cc_ent(iid, x, flip, state, tin=0.0):
    y = 7.45
    return Entity(id=iid, type_key=E(CC), pos=E((x, y - 2.5)), vel=E((0.0, 0.0)), pos_transform=(x, y), flip_x=flip,
                  fsm=[("Control", state, tin)],
                  body_polys=[[(x - 1.5, y - 3.5), (x + 1.5, y - 3.5), (x + 1.5, y + 1.0), (x - 1.5, y + 1.0)]])


def test_the_idle_clappers_turn_with_a_real_forecast(prod_tables):
    # round 3 (forum.md 21.7): MultiForecast gave every Subject t_free = 0, so the Buddy rule's reach test (the idle
    # one's spot reached before the busy one's attack can end) never held live. With the family's duration p0.5
    # (CC_SLAM 1.26 s) the slamming one has t_free > 0 and the idle one's turn comes; late in the slam it does not.
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.core.worldstate import FsmTransition, ORACLE, Stamp

    def go(iid, to, t):
        return Event(Ev.FSM_TRANSITION, 0, t, FsmTransition(enemy_id=iid, type_key=CC, fsm="Control", to_state=to))

    def frame(mf, t, s1, evs=()):
        ents = [_cc_ent(1, 22.0, False, s1), _cc_ent(2, 40.0, True, "Idle")]
        ws = WorldState(stamp=Stamp(frame=int(t * 60), t_game_s=t), entities=ents, events=list(evs))
        mf.update(ws)
        w = world(30.0, t=t, ents=ents)
        return w, mf.forecast(0.8)

    for late, want in ((0.1, 2), (1.0, 1)):
        mf = MultiForecaster(prod_tables, ORACLE, waves=False)
        tac = l2()
        w, fc = frame(mf, 10.0, "Idle", [go(1, "Idle", 10.0), go(2, "Idle", 10.0)])
        assert all(s.t_free == 0.0 and not s.committed for s in fc.subjects)
        assert tac.decide(w, fc, None, 3).target == 1                 # both idle: the nearer (8 u against 10 u)
        frame(mf, 10.1, "Slam Antic", [go(1, "Slam Antic", 10.1)])
        w, fc = frame(mf, 10.1 + late, "Slam Antic")
        busy = next(s for s in fc.subjects if s.iid == 1)
        assert busy.committed and busy.family == "CC_SLAM"
        assert busy.t_free == pytest.approx(prod_tables.types[CC].families["CC_SLAM"].dur[0] - late, abs=1e-6)
        p = tac.decide(w, fc, None, 3)
        assert p.target == want, (late, busy.t_free, tac.last.get("l2_cands"))
        if want == 2:
            assert tac.stats["switch_kinds"] == {"turn": 1}
        else:                                                         # 0.26 s left < the run (0.05 + 6 / 17.5)
            assert tac.stats["tgt_switches"] == 0


def test_jump_cast_rune_circle_kept_out_of_after_the_move():
    # round 3 (forum.md 21.7.6): a CC_JUMP_CAST's rune circle (6.62 u in front of where it landed, r 7.19) bursts
    # about 0.75-0.87 s after the move ends; the face (4 u in front) is inside it (v4 w7: 20 hits). Until rune_hold_s
    # after the move: out past the circle when the way round backed off, behind the landing when it went under; then
    # the face again.
    t = l2()
    cast = dict(y=7.45, family="CC_JUMP_CAST", committed=True)
    t.decide(world(36.0, t=10.0, ents=[clapper(9, 46.0, False)]),
             WinFc([subj(9, CC, 46.0, state="Cast Slam Antic 2", **cast)]), None, 3)
    # 1.3 s in: behind it (7.7 u off, 0.49 s) is not reached 0.25 s before it lands (1.85 s) -> back off
    t.decide(world(36.0, t=11.3, ents=[clapper(9, 44.0, False)]),
             WinFc([subj(9, CC, 44.0, state="Air", **cast)]), None, 3)
    assert t.jump_how[9] == "back off"
    # the move over at 12.2 s: idle where it landed (41.2), the hero in front of it
    land = 41.2
    idle = [subj(9, CC, land, y=7.45)]
    p = t.decide(world(36.0, t=12.2, ents=[clapper(9, land, False)]), WinFc(idle), None, 3)
    assert t.rune[9][:2] == (land, -1.0)
    assert t.last["goal_why"].endswith("rune: out") and p.stance_x == pytest.approx(land - 14.5)
    assert p.hit_w.get(9, 0.0) == 0.0                             # stepping away: no hit reward on it
    p = t.decide(world(36.0, t=13.1, ents=[clapper(9, land, False)]), WinFc(idle), None, 3)
    assert t.last["goal_why"].endswith("rune: out")
    p = t.decide(world(36.0, t=13.3, ents=[clapper(9, land, False)]), WinFc(idle), None, 3)
    assert t.last["goal_why"].endswith("face") and p.stance_x == pytest.approx(land - 4.0)
    assert 9 not in t.rune
    # under it: behind the landing (2.5 u, out of the circle's back edge at 0.58 u) while the rune is pending
    t = l2()
    t.decide(world(34.0, t=10.0, ents=[clapper(9, 40.0, False)]),
             WinFc([subj(9, CC, 40.0, state="Cast Slam Antic 2", **cast)]), None, 3)
    t.decide(world(34.0, t=10.93, ents=[clapper(9, 39.5, False)]),
             WinFc([subj(9, CC, 39.5, state="Air", **cast)]), None, 3)
    assert t.jump_how[9] == "under and behind"
    land = 39.1
    p = t.decide(world(land + 3.0, t=12.2, ents=[clapper(9, land, False)]), WinFc([subj(9, CC, land, y=7.45)]),
                 None, 3)
    assert t.last["goal_why"].endswith("rune: behind") and p.stance_x == pytest.approx(land + 2.5)


def test_round3_holding_rule_hysteresis():
    # round 3 (forum.md 21.7.3): goal switches (target or rule) were 25.9 / min live in wave 0, most of them RUSH <->
    # KITE at the 8 u edge. The playbook's holding: the rule 4 s, the target 8 s and x 2, and from KITE, RUSH only on
    # one isolated by 8 + 2 u
    r = load_l2_rules()
    assert (r.goal_dwell_s, r.dwell_s, r.switch_x, r.rule_hyst_u) == (4.0, 8.0, 2.0, 2.0)
    t = l2()
    s = [subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 36.0)]
    p = t.decide(world(20.0, t=10.0), WinFc(s, t_min=9.0), None, 3)
    assert p.goal == KITE and p.target == 1                       # nobody isolated
    s = [subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 42.0)]  # the Envoy 9 u from the Reed: isolated (8 u)
    assert _run(t, s, 20.0, 14.5, t_min=9.0).goal == KITE           # but not by 10 u: KITE stays
    s = [subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 44.0)]  # 11 u
    p = _run(t, s, 20.0, 14.6, t_min=9.0)
    assert p.goal == RUSH and p.target == 3
    assert t.stats["rule_changes"] == {} and t.stats["switch_kinds"] == {"ineligible": 1}
    # with no kept KITE (the first goal) 8 u is enough
    t = l2()
    p = t.decide(world(20.0, t=10.0), WinFc([subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 42.0)], t_min=9.0),
                 None, 3)
    assert p.goal == RUSH and p.target == 3
    # the rule held goal_dwell_s: RUSH on the Envoy, it gets company at 2 s: still RUSH, KITE on it after 4 s
    s = [subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 37.0)]
    assert _run(t, s, 20.0, 12.0, t_min=9.0).goal == RUSH
    p = _run(t, s, 20.0, 14.1, t_min=9.0)
    assert p.goal == KITE and p.target == 3 and t.stats["rule_changes"] == {"RUSH>KITE": 1}
