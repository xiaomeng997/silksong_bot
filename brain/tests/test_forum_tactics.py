"""ForumTactics (forum_planner_plan R4, combat.tactics.forum_local): target priority, the defensive-stance hit weight,
the pocket rules, EVADE and HEAL, on a fake forecast."""
from types import SimpleNamespace as NS

import numpy as np

from ssbot.combat.multi_forecast import Subject
from ssbot.combat.tactics.forum_local import LEAVE, ForumTactics, load_forum_playbook
from ssbot.core.worldstate import E, WorldState


class FakeFc:
    def __init__(self, subjects, t_min=9.0):
        self.subjects = subjects
        self._t = t_min

    def occupied(self, x, y, tk):
        return np.zeros(np.shape(x), bool)

    def t_min(self, x, y, t_max=3.0, subject=None):
        return min(self._t, t_max) if self._t < t_max else t_max


def subj(iid, tk, x, state="Idle", y=5.0):
    return Subject(iid, tk, True, True, False, None, state, 50.0, 1.0, (x, y), 0.0, 1.0)


def world(x=30.0, y=5.6, hp=7, silk=0, ents=()):
    ws = WorldState()
    ws.hero.pos = E((x, y))
    ws.res.hp, ws.res.hp_max, ws.res.silk = E(hp), E(7), E(silk)
    ws.entities = list(ents)
    return ws


def tac():
    pb, rules = load_forum_playbook()
    return ForumTactics(pb, rules, 5.6)


def test_clawmaiden_first_and_distant_maestro_last():
    t = tac()
    s = [subj(1, "Song Pilgrim 03", 33.0), subj(2, "Song Handmaiden", 38.0)]
    p = t.decide(world(), FakeFc(s), None, 3)
    assert p.mode == "ENGAGE" and p.target == 2
    s = [subj(3, "Song Pilgrim Maestro", 40.0), subj(4, "Song Reed", 44.0)]
    assert t.decide(world(), FakeFc(s), None, 3).target == 4
    s = [subj(3, "Song Pilgrim Maestro", 33.0), subj(4, "Song Reed", 44.0)]
    assert t.decide(world(), FakeFc(s), None, 3).target == 3


def test_defensive_stance_scores_negative():
    t = tac()
    s = [subj(5, "Song Administrator", 32.0, state="Parry Stance"), subj(6, "Song Reed", 36.0, state="Block"),
         subj(7, "Song Reed", 40.0, state="Alert")]
    p = t.decide(world(), FakeFc(s), None, 3)
    assert p.hit_w[5] < 0 and p.hit_w[6] < 0 and p.hit_w[7] > 0


def test_pocket_rule_two_leaves():
    t = tac()
    clap = NS(type_key=NS(v="Song Heavy Sentry"), pos_transform=(17.5, 7.45), facing=NS(v=-1, conf=1.0),
              hidden=False)
    s = [subj(8, "Song Heavy Sentry", 17.5)]
    p = t.decide(world(14.3, 13.6, ents=[clap]), FakeFc(s), None, 3)
    assert p.mode == LEAVE and p.stance_x > 18.0
    clap.facing = NS(v=1, conf=1.0)
    clap.pos_transform = (25.0, 7.45)
    assert t.decide(world(14.3, 13.6, ents=[clap]), FakeFc(s), None, 3).mode != LEAVE


def test_pocket_rule_one_keeps_stances_off_the_wall():
    t = tac()
    clap = NS(type_key=NS(v="Song Heavy Sentry"), pos_transform=(16.0, 7.45), facing=NS(v=-1, conf=1.0),
              hidden=False)
    enter, _ = t.pocket_vetoes(world(ents=[clap]))
    assert enter


def test_evade_and_heal():
    t = tac()
    s = [subj(1, "Song Pilgrim 03", 31.0)]
    assert t.decide(world(), FakeFc(s, t_min=0.2), None, 3).mode == "EVADE"
    d = NS(allows=lambda p: True, pause_pending=False, restrictions=NS(max_punish_hits=None))
    p = t.decide(world(hp=4, silk=9), FakeFc(s, t_min=3.0), d, 2)
    assert p.mode == "HEAL" and p.want_bind
    p = t.decide(world(hp=4, silk=3), FakeFc(s, t_min=3.0), d, 2)
    assert p.mode == "ENGAGE" and p.weights["hit"] > t.pb.weights["hit"]
