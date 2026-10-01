"""OracleBackend on real STATEs of the trial Bell Beast run (tests/worldstate_fixture.py) and on edited copies."""
import math

import numpy as np
import pytest

from ssbot.backends.oracle_backend import OracleBackend, cstate_names_from_facts, damage_flags, entity_kind
from ssbot.core.bosses import BELL_BEAST
from ssbot.core.worldstate import (FM, Ev, Hazard, Kind, PauseBlock, Screen, Src, WorldState)
from ssbot.tools import cstate
from tests import worldstate_fixture as fx

NAMES = cstate_names_from_facts()


def run(states: list[dict]) -> list[WorldState]:
    b = OracleBackend(bosses=[BELL_BEAST], clock=None)
    return [b.feed(s) for s in states]


@pytest.fixture(scope="module")
def wake() -> list[WorldState]:
    return run(fx.window(0))


@pytest.fixture(scope="module")
def kill() -> list[WorldState]:
    return run(fx.window(2))


def at(wss: list[WorldState], f: int) -> WorldState:
    return next(w for w in wss if w.stamp.frame == f)


def events(wss: list[WorldState], kind: Ev) -> list[tuple[int, object]]:
    return [(w.stamp.frame, e.data) for w in wss for e in w.events if e.kind == kind]


def test_stamp_and_game_time(wake):
    states = fx.window(0)
    assert [w.stamp.frame for w in wake] == [s["f"] for s in states]
    assert wake[-1].stamp.t_game_s == pytest.approx(sum(s["dt"] for s in states))
    assert wake[0].stamp.t_sample_qpc_ns == states[0]["q"] * 100        # QPC at 10 MHz
    assert all(w.stamp.backend == "oracle" and w.perception.dropped_frames == 0 for w in wake)


def test_hit_taken_with_its_side_events(wake):
    w = at(wake, 56777)
    kinds = [e.kind for e in w.events]
    for k in (Ev.HIT_TAKEN, Ev.CATASTROPHE, Ev.FREEZE, Ev.DISABLE_PAUSE_ON):
        assert k in kinds
    hit = next(e.data for e in w.events if e.kind == Ev.HIT_TAKEN)
    assert (hit.amount, hit.hazard, hit.source_type, hit.source_id) == (2, Hazard.ENEMY, "Bone Beast", fx.BOSS_IID)
    assert hit.caller_path == "Bone Beast/PolyCollider"
    lethal = next(e.data for e in w.events if e.kind == Ev.CATASTROPHE)
    assert lethal.blocked is True and lethal.path == "damage" and lethal.amount == 2
    freeze = next(e.data for e in w.events if e.kind == Ev.FREEZE)
    assert freeze.phase == "start" and freeze.profile == "direct:HeroController.StartRecoil"
    assert w.hero.mode.v == "hurt"


def test_iframes_count_down_in_game_time(wake):
    i0 = next(i for i, w in enumerate(wake) if w.stamp.frame == 56777)
    vals = []
    for w in wake[i0:]:
        it = w.hero.iframes_left
        if it.v == 0.0 and it.src == Src.ORACLE:     # invulnerable has fallen
            break
        assert it.src == Src.PREDICTED and it.conf == pytest.approx(0.9)
        vals.append(it.v)
    assert vals[0] == pytest.approx(1.0)
    assert all(a >= b for a, b in zip(vals, vals[1:]))
    assert vals[-1] < 0.05                           # measured: rise to fall = INVUL_TIME - one frame
    assert 70 < len(vals) < 90                       # about 1 s of game time plus the frozen frames


def test_pause_availability_follows_the_blockers(wake):
    states = {s["f"]: s for s in fx.window(0)}
    seen_blocked = False
    for w in wake:
        raw = states[w.stamp.frame]["pause"]["blk"]
        assert w.game.pause_available.v == (raw == 0)
        assert w.game.quit_available.v == (raw == 0)
        if raw == 3:
            seen_blocked = True
            assert w.game.pause_blockers == PauseBlock.DISABLE_PAUSE | PauseBlock.TIME_SLOWED
    assert seen_blocked
    w = wake[-1]
    assert w.game.screen.v == Screen.PLAYING and w.game.scene.v == "Bone_05" and w.game.game_state == 4
    assert w.game.play_time.saved_s is not None and w.game.play_time.counting


def test_boss_entity_hit_dealt_and_phase(wake):
    w = at(wake, 56714)
    boss = next(e for e in w.entities if e.id == fx.BOSS_IID)
    assert boss.kind == Kind.BOSS and boss.hp_est.v == 150.0
    assert boss.phase.top == "Charge Emerge" and boss.phase.t_in_phase == 0.0
    assert boss.fsm[0][:2] == ("Control", "Charge Emerge")
    hits = events(wake, Ev.HIT_DEALT)
    assert len(hits) == 1
    f, d = hits[0]
    assert f == 56818 and (d.target_id, d.amount, d.hp_after) == (fx.BOSS_IID, 5.0, 145.0)
    assert next(e for e in at(wake, 56830).entities if e.id == fx.BOSS_IID).hp_est.v == 145.0
    # time in phase advances by the scaled dt and restarts at each Control transition
    prev, checked = None, 0
    for w in wake:
        boss = next((e for e in w.entities if e.id == fx.BOSS_IID), None)
        moved = any(e.kind == Ev.FSM_TRANSITION and e.data.enemy_id == fx.BOSS_IID for e in w.events)
        if boss is not None and prev is not None and not moved and boss.phase.top == prev[0]:
            assert boss.phase.t_in_phase == pytest.approx(prev[1] + (w.stamp.t_game_s - prev[2]))
            checked += 1
        elif boss is not None and moved:
            assert boss.phase.t_in_phase == 0.0
        prev = (boss.phase.top, boss.phase.t_in_phase, w.stamp.t_game_s) if boss is not None else None
    assert checked > 100


def test_fsm_transitions_carry_hero_relative_position(wake):
    trans = events(wake, Ev.FSM_TRANSITION)
    first = next(d for f, d in trans if d.type_key == "Bone Beast")
    assert (first.from_state, first.to_state) == ("Dormant", "Submerged Init")
    assert first.hero_rel_pos is None           # the boss was not exported yet (submerged)
    seen = [(f, d) for f, d in trans if d.type_key == "Bone Beast" and d.hero_rel_pos is not None]
    assert seen
    f, d = seen[0]
    w = at(wake, f)
    boss = next(e for e in w.entities if e.id == fx.BOSS_IID)
    assert d.hero_rel_pos == pytest.approx((boss.pos.v[0] - w.hero.pos.v[0], boss.pos.v[1] - w.hero.pos.v[1]))


def test_bells_are_enemy_attacks_with_damage_boxes(wake):
    w = wake[-1]
    bells = [e for e in w.entities if e.type_key.v.startswith("BoneBeast DropBell")]
    assert len(bells) >= 4
    for e in bells:
        assert e.kind == Kind.ENEMY_ATTACK and e.hp_est is None and len(e.dmg_boxes) == 1
        box = e.dmg_boxes[0]
        assert box.hazard == Hazard.ENEMY and box.dmg_seq == (2,) and len(box.poly) == 8
        assert "COUNTER" in box.flags and "PARRYABLE" not in box.flags


def test_kill_comes_from_the_death_state(kill):
    hits = events(kill, Ev.HIT_DEALT)
    assert [(f, d.hp_after) for f, d in hits] == [(68995, 15.0)]
    killed = events(kill, Ev.ENEMY_KILLED)
    assert [(f, d.target_id) for f, d in killed] == [(69029, fx.BOSS_IID)]
    assert all(e.id != fx.BOSS_IID for e in at(kill, 69029).entities)


def test_rage_window_resolves_bell_hits():
    wss = run(fx.window(1))
    hit = next(d for f, d in events(wss, Ev.HIT_TAKEN) if f == 62131)
    assert hit.source_type == "BoneBeast DropBell M2" and hit.source_id is not None
    assert [f for f, _ in events(wss, Ev.HIT_DEALT)] == [61616, 61710]
    for w in wss:
        ids = [e.id for e in w.entities]
        assert len(ids) == len(set(ids))
        assert w.res.hp.v >= 1 and w.res.crest.v == "Hunter" and w.res.fractured_mask.v == FM.NOT_EQUIPPED


# ---- edited STATEs ------------------------------------------------------------------------------------------

def test_pause_edges_lockout_and_focus():
    states = fx.window(0)[:4]
    s1, s2, s3 = states[1], states[2], states[3]
    s2["game"]["paused"] = True
    s2["game"]["gs"] = 5
    s2["pause"]["blk"] = 4 | 64
    s3["focus"] = False
    b = OracleBackend(bosses=[BELL_BEAST], clock=None)
    w0, w1, w2, w3 = (b.feed(s) for s in states)
    assert not any(e.kind in (Ev.PAUSE_ON, Ev.PAUSE_OFF) for e in w0.events + w1.events)
    assert [e.kind for e in w2.events if e.kind == Ev.PAUSE_ON] == [Ev.PAUSE_ON]
    assert w2.game.screen.v == Screen.PAUSE_MENU and w2.game.pause_available.v
    assert w2.game.unpause_lockout_until_s == pytest.approx(s2["q"] / 1e7 + 0.3)
    assert w2.game.pause_blockers & PauseBlock.PAUSE_LOCKOUT
    assert Ev.PAUSE_OFF in [e.kind for e in w3.events] and Ev.FOCUS_LOST in [e.kind for e in w3.events]
    assert not w3.game.pause_available.v and w3.game.pause_blockers & PauseBlock.FOCUS_LOST
    assert w3.game.unpause_lockout_until_s == pytest.approx(s3["q"] / 1e7 + 0.3)


def test_quit_blockers_and_would_die():
    s = next(s for s in reversed(fx.window(0)) if s["pause"]["blk"] == 0)
    s["pause"]["dsq"] = True
    s["ev"] = [{"k": "would_die", "f": s["f"], "q": s["q"], "d": {"path": "die", "blocked": True, "src": "x"}}]
    w = OracleBackend(clock=None).feed(s)
    assert w.game.pause_available.v and not w.game.quit_available.v
    assert w.game.pause_blockers & PauseBlock.DISABLE_SAVEQUIT
    (ev,) = w.events
    assert ev.kind == Ev.WOULD_DIE and ev.data.path == "die"


def test_bind_events_from_the_binding_bit():
    states = fx.window(0)[-4:]
    for s in states[1:3]:
        bits = cstate.decode(s["hero"]["cstate"], NAMES)
        bits["isBinding"] = True
        s["hero"]["cstate"] = cstate.encode(bits, NAMES)
    hp0 = states[0]["hero"]["health"]
    states[3]["hero"]["health"] = hp0 + 1
    wss = run(states)
    assert [w.hero.binding.v for w in wss] == ["NONE", "IN_PROGRESS", "IN_PROGRESS", "DONE"]
    assert [e.kind for e in wss[1].events if e.kind.name.startswith("BIND")] == [Ev.BIND_START]
    done = next(e.data for e in wss[3].events if e.kind == Ev.BIND_DONE)
    assert (done.hp_before, done.hp_after) == (hp0, hp0 + 1)
    assert wss[1].hero.mode.v == "bind"


def test_gap_and_long_gap():
    states = fx.window(0)
    b = OracleBackend(bosses=[BELL_BEAST], clock=None)
    b.feed(states[0])
    w = b.feed(states[2])
    assert w.perception.dropped_frames == 1
    # a recording cut (window 0 -> window 2) must not turn the HP difference into one hit
    b2 = OracleBackend(bosses=[BELL_BEAST], clock=None)
    for s in states:
        b2.feed(s)
    w = b2.feed(fx.window(2)[0])
    assert not [e for e in w.events if e.kind == Ev.HIT_DEALT]


def test_wrong_cstate_schema_fails_loudly():
    with pytest.raises(ValueError):
        OracleBackend(cstate_names=NAMES + [f"x{i}" for i in range(64)], clock=None).feed(fx.window(0)[0])


def test_step_pulls_from_the_source():
    it = iter(fx.window(2)[:3])
    b = OracleBackend(source=lambda: next(it), clock=lambda: 42)
    w = b.step()
    assert w.stamp.frame == 68960 and w.stamp.t_pub_qpc_ns == 42
    with pytest.raises(RuntimeError):
        OracleBackend(clock=None).step()


# ---- pure mappings ------------------------------------------------------------------------------------------

def _ent(**over) -> dict:
    e = {"type_key": "X", "category": "hazard", "src": 2, "colliders": [
        {"damage": {"dealt": 1, "eff": 1, "hazard_type": 1, "flags": 0, "parry": 0, "parryable": False,
                    "can_cause_damage": True}}]}
    e.update(over)
    return e


def test_entity_kind_table():
    assert entity_kind(_ent(type_key="Bone Beast", category="enemy"), {"Bone Beast": None}) == Kind.BOSS
    assert entity_kind(_ent(category="enemy", src=3)) == Kind.ENEMY
    assert entity_kind(_ent(src=34)) == Kind.PROJECTILE
    assert entity_kind(_ent(src=16)) == Kind.HAZARD_DYN
    assert entity_kind(_ent()) == Kind.ENEMY_ATTACK
    spikes = _ent(colliders=[{"damage": {"hazard_type": 2}}])
    assert entity_kind(spikes) == Kind.HAZARD_DYN
    assert entity_kind(_ent(category="player_attack", colliders=[])) == Kind.HERO_ATTACK
    assert entity_kind(_ent(category="interactable", type_key="Lever Big", colliders=[])) == Kind.LEVER
    assert entity_kind(_ent(category="other", colliders=[])) == Kind.UNKNOWN


def test_kind_is_sticky_per_entity():
    states = fx.window(0)[-3:]
    bell = next(e for e in states[0]["ents"] if e["type_key"] == "BoneBeast DropBell L")
    bell["src"] = 34
    wss = run(states)
    kinds = [next(e.kind for e in w.entities if e.id == bell["iid"]) for w in wss]
    assert kinds == [Kind.PROJECTILE] * 3


def test_damage_flags():
    d = {"parry": 1 | 4, "flags": 4 | 16 | 2, "hazard_type": 5, "eff": -1}
    assert damage_flags(d) == {"PARRYABLE", "DEFLECTABLE", "COUNTER", "FLAME", "TAG_ACID", "NON_LETHAL",
                               "IGNORES_IFRAMES", "AMOUNT_FSM"}
    assert damage_flags({"parry": 2, "flags": 0, "hazard_type": 1, "eff": 2}) == {"PARRYABLE"}


def test_hero_without_state_is_unknown():
    s = fx.window(0)[0]
    s["hero"] = None
    w = OracleBackend(clock=None).feed(s)
    assert w.hero.pos.conf == 0.0 and w.res.hp.src == Src.UNKNOWN
    assert w.hero.iframes_left is None and math.isfinite(w.stamp.t_game_s)
    assert np.isfinite(w.cam.x)
