"""Wall pressure is an L2 geometry candidate, never a route or floor certificate."""
from types import SimpleNamespace as NS

import pytest

from ssbot.combat.tactics import gauntlet as G, modes as M
from ssbot.core.worldstate import DamageBox, E, Event, Ev, HitDealt
from tests.test_forum_l2 import CC, WinFc, l2, subj, world


FLAGS = ("SSBOT_FORUM_CHAIN_NATIVE", "SSBOT_FORUM_CHAIN_B2", "SSBOT_FORUM_CHAIN_AIR_MANUAL")


@pytest.fixture(autouse=True)
def explicit_manual_b(monkeypatch):
    for flag in FLAGS:
        monkeypatch.setenv(flag, "1")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_ARM", "B")
    monkeypatch.setattr(G, "TWO_FOCUS", False)


def scene(side=-1, body=(3., 5.), hero=1.5):
    if side > 0:
        body, hero = (60. - body[1], 60. - body[0]), 60. - hero
    x = sum(body) / 2
    entity = NS(id=7, dmg_boxes=[DamageBox(
        poly=[(body[0], 3.), (body[1], 3.), (body[1], 7.), (body[0], 7.)],
        active=True, name=CC)])
    ws = world(hero, ents=[entity])
    ws.hero.hurtbox = [(hero-.25, 4.5), (hero+.25, 4.5), (hero+.25, 6.5), (hero-.25, 6.5)]
    ws.hero.mode, ws.hero.contact = E("air"), E("AIR")
    ws.stamp.frame = 100
    target = subj(7, CC, x, family=G.CC_IDLE)
    fc = WinFc([target], t_min=9.)
    tac = l2()
    tac.pb.arena_x = (0., 60.)
    tac.goal = G.Goal(G.RUSH, 7, 4. if side < 0 else 56., 1., family=G.CC_IDLE)
    return tac, ws, fc


def candidate(tac, ws, fc, **kwargs):
    return tac.wall_pressure_candidate(ws, fc, 7, **kwargs)


@pytest.mark.parametrize("side,span", [(-1, (.25, 2.75)), (1, (57.25, 59.75))])
def test_mirrored_wall_gap_is_only_a_geometry_candidate(side, span):
    tac, ws, fc = scene(side)
    intent = candidate(tac, ws, fc)
    assert isinstance(intent, M.WallPressure)
    assert (intent.target, intent.kind, intent.wall_side) == (7, "side", side)
    assert intent.floor_span == pytest.approx(span)
    assert intent.geometry_candidate is True


@pytest.mark.parametrize("edge,kind", [(.5, "side"), (.4999, "stomp")])
def test_projected_width_boundary_never_claims_floor_support(edge, kind):
    tac, ws, fc = scene(body=(edge, 2.5), hero=.25)
    intent = candidate(tac, ws, fc)
    assert intent.kind == kind and intent.geometry_candidate
    assert (intent.floor_span is None) == (kind == "stomp")


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", ["0", ""])
def test_each_explicit_manual_flag_is_required(monkeypatch, flag, value):
    tac, ws, fc = scene()
    monkeypatch.setenv(flag, value)
    assert candidate(tac, ws, fc) is None


@pytest.mark.parametrize("arm", ["A", "", "b"])
def test_baseline_and_unknown_arm_do_not_receive_wall_pressure(monkeypatch, arm):
    tac, ws, fc = scene()
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_ARM", arm)
    assert candidate(tac, ws, fc) is None


@pytest.mark.parametrize("missing", ["body", "hero_box", "hero_conf", "arena", "body_nan", "root_name"])
def test_unknown_geometry_has_no_guessed_standing_or_stomp_intent(missing):
    tac, ws, fc = scene()
    if missing == "body": ws.entities[0].dmg_boxes = []
    elif missing == "hero_box": ws.hero.hurtbox = []
    elif missing == "hero_conf": ws.hero.pos = E(ws.hero.pos.v, conf=0.)
    elif missing == "arena": tac.pb.arena_x = (float("nan"), 60.)
    elif missing == "body_nan": ws.entities[0].dmg_boxes[0].poly[0] = (float("nan"), 3.)
    elif missing == "root_name": ws.entities[0].dmg_boxes[0].name = "Slam Collider 1"
    assert candidate(tac, ws, fc) is None


def test_no_crossing_into_wall_side_and_no_central_wall_pressure():
    tac, ws, fc = scene(hero=8.)
    assert candidate(tac, ws, fc) is None
    tac, ws, fc = scene(body=(20., 22.), hero=18.)
    assert candidate(tac, ws, fc) is None


def test_observed_target_hit_and_bounce_allows_a_head_start():
    tac, ws, fc = scene(hero=4.)
    assert candidate(tac, ws, fc) is None
    ws.hero.mode = E("pogo")
    ws.events = [Event(Ev.HIT_DEALT, 100, 10., HitDealt(7, CC, 9., 20., attack="Nail", src="DownSlash"))]
    assert candidate(tac, ws, fc).wall_side == -1
    ws.events[0].frame = 99
    assert candidate(tac, ws, fc) is None
    assert candidate(tac, ws, fc, observed_bounce=True).wall_side == -1


@pytest.mark.parametrize("contact,mode", [("WALL_L", "wall"), ("WALL_R", "wall")])
def test_wall_slide_is_not_a_standing_permission(contact, mode):
    tac, ws, fc = scene()
    ws.hero.contact, ws.hero.mode = E(contact), E(mode)
    assert candidate(tac, ws, fc) is None


def test_focus_and_existing_entry_attack_keep_priority():
    tac, ws, fc = scene()
    tac.goal.target = 8
    assert candidate(tac, ws, fc) is None
    tac.goal.target = 7
    tac.goal.entry_attack = M.EntryAttack(7, "stomp", 8, G.CC_CAST, 10., 10.)
    assert candidate(tac, ws, fc) is None


def test_same_target_refreshes_every_tick_without_rewriting_goal_or_clamp(monkeypatch):
    tac, ws, fc = scene(body=(1., 3.), hero=.25)
    old_goal = tac.goal
    monkeypatch.setattr(tac, "_pick", lambda *args: tac.goal)
    prefs = M.GoalPrefs(mode="ENGAGE", stance_x=30., weights={}, hit_w={7: 3.})
    out = tac._decide(ws, fc, prefs)
    assert out.wall_pressure.kind == "side"
    assert .25 <= out.stance_x <= .75 < tac.rules.wall_room_u
    assert tac.goal is old_goal and old_goal.stance_x == tac.rules.wall_room_u
    assert tac._clamp(.5) == tac.rules.wall_room_u
    assert out.hit_kw[7] == (3., 0., 0., 0.)
    ws.entities[0].dmg_boxes[0].poly = [(0.4, 3.), (3., 3.), (3., 7.), (0.4, 7.)]
    out2 = tac._decide(ws, fc, prefs)
    assert out2.wall_pressure.kind == "stomp"
    assert out2.hit_kw[7] == (0., 0., 0., 3.)
    assert tac.goal is old_goal


def test_new_focus_tick_and_entry_clear_do_not_overwrite_switch_style(monkeypatch):
    tac, ws, fc = scene()
    tac.goal = G.Goal(G.RUSH, 8, 30., 1.)
    monkeypatch.setattr(tac, "_pick", lambda *args: G.Goal(G.RUSH, 7, 4., 10., family=G.CC_IDLE))
    prefs = M.GoalPrefs(mode="ENGAGE", stance_x=30., weights={}, hit_w={7: 3.})
    out = tac._decide(ws, fc, prefs)
    assert out.target == 7 and out.wall_pressure is None


def test_disabled_mode_preserves_legacy_preferences(monkeypatch):
    tac, ws, fc = scene()
    monkeypatch.setattr(tac, "_pick", lambda *args: tac.goal)
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_ARM", "A")
    prefs = M.GoalPrefs(mode="ENGAGE", stance_x=30., weights={}, hit_w={7: 3.}, no_hit=frozenset({8}))
    out = tac._decide(ws, fc, prefs)
    assert out.wall_pressure is None and out.stance_x >= tac.rules.wall_room_u
    assert out.no_hit == prefs.no_hit and "wall_pressure" not in tac.last


@pytest.mark.parametrize("bad", ["mode", "wrong_target", "wrong_source", "future", "no_event"])
def test_head_start_requires_current_focus_downslash_and_observed_pogo(bad):
    tac, ws, fc = scene(hero=4.)
    ws.hero.mode = E("pogo")
    ws.events = [Event(Ev.HIT_DEALT, 100, 10., HitDealt(7, CC, 9., 20., attack="Nail", src="DownSlash"))]
    if bad == "mode": ws.hero.mode = E("attack")
    elif bad == "wrong_target": ws.events[0].data.target_id = 8
    elif bad == "wrong_source": ws.events[0].data.src = "Slash"
    elif bad == "future": ws.events[0].frame = 101
    else: ws.events = []
    assert candidate(tac, ws, fc) is None


def test_attack_reaction_and_no_hit_keep_their_priority(monkeypatch):
    tac, ws, fc = scene()
    fc.subjects = [subj(7, CC, 4., family=G.CC_CAST, state="Spell Antic")]
    assert candidate(tac, ws, fc) is None
    tac, ws, fc = scene()
    monkeypatch.setattr(tac, "_pick", lambda *args: tac.goal)
    prefs = M.GoalPrefs(mode="ENGAGE", stance_x=30., weights={}, hit_w={7: 3.}, no_hit=frozenset({7}))
    assert tac._decide(ws, fc, prefs).wall_pressure is None
