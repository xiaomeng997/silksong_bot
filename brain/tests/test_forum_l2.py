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


def subj(iid, tk, x, y=5.0, state="Idle", family=None, committed=False):
    return Subject(iid, tk, True, True, committed, family, state, 50.0, 1.0, (x, y), 0.0, 1.0)


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
    # idle: face it on the hero's side
    t = l2()
    s = [subj(9, CC, 30.0, y=7.45)]
    p = t.decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p.target == 9 and p.stance_x == pytest.approx(27.0)
    # the slam: step out in front (facing left, the hero in front), or stay behind with the hero behind it
    t = l2()
    s = [subj(9, CC, 35.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]
    p = t.decide(world(30.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(22.0)
    t = l2()
    p = t.decide(world(38.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(38.5)
    # the jump: under it and behind the landing (aim stored at Jump Aim)
    t = l2()
    s = [subj(9, CC, 35.0, y=7.45, state="Jump Aim", family="CC_JUMP", committed=True)]
    p = t.decide(world(26.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    land = jump_landing(35.0, 26.0, -1.0)
    assert land == pytest.approx(35.0 + 0.92 * (31.0 - 35.0))
    assert p.stance_x == pytest.approx(land + 2.5)
    s = [subj(9, CC, 33.0, y=12.0, state="Air", family="CC_JUMP", committed=True)]
    p = t.decide(world(30.0, ents=[clapper(9, 33.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(land + 2.5)                # the take-off's aim, not the hero's x now
    # the cast: face it, the glide-spike hook on
    t = l2()
    s = [subj(9, CC, 30.0, y=7.45, state="Spell Antic", family="CC_CAST", committed=True)]
    p = t.decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert GLIDE_SPIKE in p.vocab and p.stance_x == pytest.approx(27.0)


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


def _run(t, ss, hx, at, n=6, t_min=0.2, covers=()):
    """n decisions at game time `at` (n = period: one periodic pick among them)."""
    p = None
    for _ in range(n):
        p = t.decide(world(hx, t=at), WinFc(ss, covers=covers, t_min=t_min), None, 3)
    return p


def test_a_kept_target_is_held_for_the_dwell():
    # round 2: the round-1 A/B changed goals 33 times a minute in wave 0; another target needs switch_x and dwell_s
    t = l2()
    a, b = subj(1, CH, 30.0), subj(2, EN, 45.0)
    p = t.decide(world(20.0, t=10.0), WinFc([a, b]), None, 3)
    assert p.goal == RUSH and p.target == 1                       # spread: the fastest pursuer
    b = subj(2, EN, 15.0)                                         # now the nearer (ETA 0.39 s against 0.85 s)
    assert _run(t, [a, b], 20.0, 10.5).target == 1                # held: 0.5 s < dwell 2 s
    assert _run(t, [a, b], 20.0, 12.2).target == 2                # then the switch
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
    t = l2()
    a, b = subj(1, CH, 30.0), subj(2, EN, 45.0)
    t.decide(world(20.0, t=10.0), WinFc([a, b]), None, 3)
    b = subj(2, EN, 15.0, state="Slash Recover", family="EN_SLASH", committed=True)
    p = _run(t, [a, b], 20.0, 10.2, covers=[(16.0, 18.0, 1.5)])  # its spot (16.8) clear for 1.5 s
    assert p.goal == PUNISH and p.target == 2
    # the same target under another rule (isolated -> clustered: RUSH -> KITE) after goal_dwell_s
    t = l2()
    a, b = subj(1, CH, 30.0), subj(2, EN, 45.0)
    t.decide(world(20.0, t=10.0), WinFc([a, b], t_min=9.0), None, 3)
    b = subj(2, EN, 36.0)
    assert _run(t, [a, b], 20.0, 10.3, t_min=9.0).goal == RUSH    # 0.3 s < goal_dwell 0.5 s
    p = _run(t, [a, b], 20.0, 10.6, t_min=9.0)
    assert p.goal == KITE and p.target == 1 and t.stats["tgt_switches"] == 0


def test_the_rule_moves_the_target_when_the_kept_one_is_not_eligible():
    # KITE on the Choristor; then the Envoy alone far off is isolated and the Choristor is not: RUSH takes the Envoy
    # after goal_dwell_s (the kept target is not eligible under RUSH: no dwell_s, no hysteresis)
    t = l2()
    s = [subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 36.0)]
    p = t.decide(world(20.0, t=10.0), WinFc(s, t_min=9.0), None, 3)
    assert p.goal == KITE and p.target == 1
    s = [subj(1, CH, 30.0), subj(2, RE, 33.0), subj(3, EN, 45.0)]
    p = _run(t, s, 20.0, 10.6, t_min=9.0)
    assert p.goal == RUSH and p.target == 3 and t.stats["tgt_switches"] == 1


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
