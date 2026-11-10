"""Task 179 #313/#314 (the person via Sol seq 233-237): after a near attack, back between the two, via the real L2 entry.

A Clapper move that came within the slam range of her makes the return due when it ends, whatever her path before (out
of the middle, or the two overlapped from the start; on the ground or in the air), unless she is between the roots
with a standing gap then. Quiet scene: a ground pose in a standing gap (the existing ground stance on the target's gap
side, the passed one not hit), else an air pose at the seam above the target's body (the existing stomp style) until
they part; done only once she has landed in the gap. Not while the attack, a new attack, a circle over the
destination, a middle-jump event or a cluster route holds the scene."""
import pytest

from ssbot.combat.tactics import clapper_priority as P, gauntlet as G
from ssbot.core.worldstate import E
from tests.test_clapper_priority import change, manual, scene, seq312_off, step   # noqa: F401  (autouse manual-B fixture)


def hero_at(ws, x, y=5.6):
    ws.hero.pos = E((x, y))
    ws.hero.contact = E("GROUND" if y <= 5.6 else "AIR")
    ws.hero.hurtbox = [(x-.25, y-1.6), (x+.25, y-1.6), (x+.25, y+.4), (x-.25, y+.4)]


def move(ws, fc, iid, x):
    change(fc, iid, pos=(x, 5.))
    e = next(e for e in ws.entities if e.id == iid)
    e.dmg_boxes[0].poly = [(x-1., 3.), (x+1., 3.), (x+1., 7.), (x-1., 7.)]


def near_attack(tac, ws, fc, iid=7, family=G.CC_SLAM, states=("Slam Antic", "Slam Recover")):
    for st in states:
        change(fc, iid, family=family, state=st, committed=True)
        step(tac, ws, fc)
        assert tac.last["clapper_back"] is None and tac.last["clapper_winner"]["rule"] != "back"
    change(fc, iid, family=G.CC_IDLE, state="Idle", committed=False)
    return step(tac, ws, fc)


def test_after_a_near_attack_she_goes_back_between_on_the_ground():
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)        # outside: both on her right
    out = near_attack(tac, ws, fc)
    back = tac.last["clapper_back"]
    assert tac.last["clapper_winner"]["rule"] == "back" and out.target == 8   # the one with more room behind it
    assert back["posture"] == "ground" and back["move"] == [7, G.CC_SLAM] and back["crossed"] == 7
    assert out.stance_x == pytest.approx(30.)          # 8's face spot inside the standing gap 21.25 .. 32.75
    assert 7 in out.no_hit and 8 not in out.no_hit and out.entry_attack is None
    assert tac.last["clapper_scene"] == "middle return ground"
    hero_at(ws, 29., y=9.)                               # over the gap in the air: not back yet
    step(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return ground" and tac.last["clapper_back_end"] is None
    hero_at(ws, 29.)                                     # landed between: done, the ordinary scene again
    step(tac, ws, fc)
    assert tac.last["clapper_back"] is None and tac.last["clapper_back_end"]["end"] == "landed in the standing gap"
    assert tac.last["clapper_winner"]["rule"] != "back"


def test_the_crossed_body_is_recorded_apart_only_while_no_other_source_bans_it():
    # Task 183 seq 267 (Sol): the ordinary return's crossed body stays in no_hit (the planner's output as before);
    # GoalPrefs.return_cross names it only while no other source bans the same iid (here an upstream one)
    from ssbot.combat.tactics.modes import GoalPrefs
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_winner"]["rule"] == "back" and tac.last["clapper_back"]["crossed"] == 7
    assert 7 in out.no_hit and out.return_cross == frozenset({7})
    ws.stamp.t_game_s += 1/60.
    both = tac._decide(ws, fc, GoalPrefs(mode="ENGAGE", stance_x=27., weights={}, hit_w={7: 1., 8: 1.},
                                         no_hit=frozenset({7})))
    assert tac.last["clapper_winner"]["rule"] == "back" and 7 in both.no_hit and both.return_cross == frozenset()
    ws.stamp.t_game_s += 1/60.
    assert step(tac, ws, fc).return_cross == frozenset({7})                 # every tick on its own


@pytest.mark.usefixtures("seq312_off")   # the legacy air pose (seq 312 #379: tests/test_separated312.py)
def test_crossing_a_root_in_the_air_is_not_yet_back_and_a_closing_gap_turns_it_to_the_air_pose():
    # live 2812: over the passed body's inner half in the air the gap was still open, then it closed (the other one
    # walked in): the return goes on, now at the seam above the target
    tac, ws, fc = scene(xs=(20., 30.), hx=15.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    hero_at(ws, 20.6, y=9.)                              # over 7's inner half: between the roots, not in the gap
    step(tac, ws, fc)
    assert tac.last["clapper_region"] == "over" and tac.last["clapper_scene"] == "middle return ground"
    move(ws, fc, 8, 23.)                                 # 8 walks in: bodies 1 u apart
    out = step(tac, ws, fc)
    assert tac.last["clapper_back"]["posture"] == "air" and tac.last["clapper_scene"] == "middle return air"
    assert out.target == 8 and out.stance_x == pytest.approx(22.) and 7 in out.no_hit


@pytest.mark.usefixtures("seq312_off")   # the legacy air pose (seq 312 #379: tests/test_separated312.py)
def test_no_ground_gap_holds_the_seam_in_the_air_then_lands_when_they_part():
    tac, ws, fc = scene(xs=(20., 23.), hx=15.); step(tac, ws, fc)         # bodies 19..21 and 22..24: 1 u apart
    out = near_attack(tac, ws, fc, family=G.CC_CAST, states=("Spell Antic", "Cast 2"))
    back = tac.last["clapper_back"]
    assert back["posture"] == "air" and back["gap"] == pytest.approx(1.) and out.target == 8
    assert out.stance_x == pytest.approx(22.)            # the seam 21.5 kept on 8's body: its down-slash reach
    assert out.hit_kw[8][:3] == (0., 0., 0.) and out.hit_kw[8][3] > 0
    assert 8 not in out.ground_hit | out.no_pogo | out.ground_first and 7 in out.no_hit
    assert tac.last["clapper_scene"] == "middle return air"
    hero_at(ws, 21.5, y=9.)                              # over the gap: a middle region, yet no standing room
    step(tac, ws, fc)
    assert tac.last["clapper_region"] == "middle" and tac.last["clapper_scene"] == "middle return air"
    move(ws, fc, 8, 28.)                                 # they part while she is still in the air (Root's probe)
    out = step(tac, ws, fc)
    assert tac.last["clapper_back"]["posture"] == "ground" and tac.last["clapper_back_end"] is None
    assert tac.last["clapper_scene"] == "middle return ground" and out.stance_x == pytest.approx(24.)
    move(ws, fc, 8, 23.)                                 # ... and close again before she lands: the air pose again
    out = step(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return air" and out.stance_x == pytest.approx(22.)
    assert out.hit_kw[8][:3] == (0., 0., 0.)
    move(ws, fc, 8, 28.)
    hero_at(ws, 24.)                                     # parted, and she lands in the gap: done
    out = step(tac, ws, fc)
    assert tac.last["clapper_back"] is None and tac.last["clapper_back_end"]["end"] == "landed in the standing gap"
    assert tac.last["clapper_winner"]["rule"] == "keep" and tac.last["clapper_scene"] == "attack focus"
    assert out.target == 8 and out.stance_x == pytest.approx(24.)   # at its face in the gap: the side slash
    assert 8 not in out.hit_kw and 7 not in out.no_hit               # no stomp-only weights, nothing held back


def test_the_gap_opening_while_still_outside_turns_the_air_pose_into_the_ground_one():
    tac, ws, fc = scene(xs=(20., 23.), hx=15.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    assert tac.last["clapper_back"]["posture"] == "air"
    move(ws, fc, 8, 28.)
    out = step(tac, ws, fc)
    assert tac.last["clapper_back"]["posture"] == "ground" and tac.last["clapper_scene"] == "middle return ground"
    assert out.stance_x == pytest.approx(24.) and 7 in out.no_hit and 8 not in out.hit_kw


def test_overlapped_from_the_start_then_a_near_cast_cuts_into_the_middle_from_the_air():
    tac, ws, fc = scene(xs=(20., 21.5), hx=15.)                           # overlapped; she was never between
    hero_at(ws, 15., y=9.)
    step(tac, ws, fc)
    change(fc, 7, family=G.CC_CAST, state="Spell Antic", committed=True); step(tac, ws, fc)
    move(ws, fc, 8, 27.)                                 # the other one backs off during the cast
    change(fc, 7, state="Cast 2"); step(tac, ws, fc)
    assert tac.last["clapper_back"] is None             # the cast is not over
    change(fc, 7, family=G.CC_IDLE, state="Idle", committed=False)
    out = step(tac, ws, fc)
    assert tac.last["clapper_winner"]["rule"] == "back" and tac.last["clapper_back"]["posture"] == "ground"
    assert out.target == 8 and out.stance_x == pytest.approx(23.) and 7 in out.no_hit


@pytest.mark.usefixtures("seq312_off")   # the legacy air pose (seq 312 #379: tests/test_separated312.py)
def test_tight_overlap_after_the_attack_is_the_air_pose_not_the_overhead_root():
    tac, ws, fc = scene(xs=(20., 21.5), hx=15.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    hero_at(ws, 21., y=9.)                               # between the roots, the bodies overlapped
    out = step(tac, ws, fc)
    assert tac.last["clapper_region"] == "tight" and tac.last["clapper_scene"] == "middle return air"
    assert out.stance_x == pytest.approx(20.75)          # the seam inside the overlap, not a root
    rules = {c["rule"] for c in tac.last["clapper_choices"]}
    assert "back" in rules and "overhead" not in rules   # the return holds the tight scene


@pytest.mark.usefixtures("seq312_off")   # the legacy air pose (seq 312 #379: tests/test_separated312.py)
def test_between_the_roots_without_a_standing_gap_when_the_attack_ends_still_gets_the_seam():
    # Root's #313 probe: H 20.75 / y 9, roots 20 / 21.5 (overlapped bodies) when the near attack ends: the seam
    # (20.75) with the stomp style, not the old overhead at root 20
    tac, ws, fc = scene(xs=(20., 21.5), hx=20.75)
    hero_at(ws, 20.75, y=9.)
    step(tac, ws, fc)
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_region"] == "tight" and tac.last["clapper_winner"]["rule"] == "back"
    assert tac.last["clapper_scene"] == "middle return air" and out.stance_x == pytest.approx(20.75)
    assert out.target == 8 and out.hit_kw[8][:3] == (0., 0., 0.) and out.hit_kw[8][3] > 0


def test_over_the_inner_half_when_the_attack_ends_the_attack_there_is_kept():
    # live 2626: the slam ended with her pogoing its inner half (between the roots) and a wide gap: no return, the
    # same focus (the bout's successful attack prefix)
    tac, ws, fc = scene(xs=(20., 34.), hx=21.5)
    hero_at(ws, 20.6, y=9.)
    step(tac, ws, fc)
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_region"] == "over" and tac.last["clapper_back"] is None and out.target == 7
    assert tac._clapper_priority.get("back") is None and tac.last["clapper_back_end"] is None


def test_a_new_attack_suspends_the_return_until_it_is_over():
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    assert tac.last["clapper_winner"]["rule"] == "back"
    change(fc, 8, family=G.CC_CAST, state="Spell Antic", committed=True)
    step(tac, ws, fc)
    assert tac.last["clapper_back"] is None and tac.last["clapper_winner"]["rule"] != "back"
    change(fc, 8, family=G.CC_IDLE, state="Idle", committed=False)       # a far cast: still the first one's return
    step(tac, ws, fc)
    assert tac.last["clapper_back"]["move"] == [7, G.CC_SLAM] and tac.last["clapper_winner"]["rule"] == "back"


def test_a_far_attack_makes_no_return(seq312_off):
    tac, ws, fc = scene(xs=(20., 34.), hx=5.); step(tac, ws, fc)          # 15 u from it all along
    near_attack(tac, ws, fc)
    assert tac.last["clapper_back"] is None and tac.last["clapper_winner"]["rule"] != "back"


def test_with_seq312_a_far_slam_makes_the_return_due_a_far_cast_none():
    # #386 (the person 11-10, Sol seq 330: "锤后一律回中间"): a slam's end, both Clappers here, wherever she was; other far moves as before
    tac, ws, fc = scene(xs=(20., 34.), hx=5.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    assert tac.last["clapper_back"] is not None and tac.last["clapper_back"]["move"] == [7, G.CC_SLAM]
    tac, ws, fc = scene(xs=(20., 34.), hx=5.); step(tac, ws, fc)
    near_attack(tac, ws, fc, family=G.CC_CAST, states=("Spell Antic", "Cast 1"))
    assert tac.last["clapper_back"] is None


@pytest.mark.parametrize("facing,offered", [(1., False), (-1., True)])
def test_a_circle_still_to_burst_over_the_destination_holds_it(facing, offered):
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    tac.rune[7] = (20., facing, "test", ws.stamp.t_game_s + 1.)          # in front of its facing (+1: the gap side)
    near_attack(tac, ws, fc)
    assert (tac.last["clapper_back"] is not None) is offered
    assert (tac.last["clapper_winner"]["rule"] == "back") is offered


def test_a_jump_antic_with_both_beyond_her_stays_the_cluster_route():
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    change(fc, 8, family=G.CC_JUMP, state="Jump Antic", committed=True)
    out = step(tac, ws, fc)
    assert tac.last["clapper_cluster"] is not None and tac.last["clapper_winner"]["rule"] == "bait"
    assert tac.last["clapper_back"] is None and {7, 8} <= out.no_hit


def test_lowering_the_back_maximum_keeps_the_outside_focus():
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    tac.rules.clapper_scores = {"back": 40.}
    near_attack(tac, ws, fc)
    choices = {c["rule"]: c for c in tac.last["clapper_choices"]}
    assert choices["back"]["score"] < choices["keep"]["score"] and tac.last["clapper_winner"]["rule"] == "keep"


def test_reset_drops_a_due_return():
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    tac.reset()
    assert tac._clapper_priority is None
    step(tac, ws, fc)
    assert tac.last["clapper_back"] is None
