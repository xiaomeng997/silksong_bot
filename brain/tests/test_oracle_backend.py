"""OracleBackend on real STATEs of the trial Bell Beast run (tests/worldstate_fixture.py) and on edited copies."""
import math

import numpy as np
import pytest

from ssbot.backends.oracle_backend import (HAZARD_OF, PROJECTILE_HOLD_S, OracleBackend, box_hazard,
                                         cstate_names_from_facts, damage_flags, entity_kind, entity_pos, main_collider,
                                         type_key_of)
from ssbot.core.bosses import BELL_BEAST
from ssbot.ipc.ents import HAZARD_TYPES
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
    assert d.hero_anim == fx.window(0)[[s["f"] for s in fx.window(0)].index(56818)]["hero"]["anim"]["clip"]
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


def test_a_hit_landing_while_hurt_keeps_the_action_before():
    """The live run's case: a Silk Spear in flight hits while the hero plays "Stun" (hurt); it is still the throw."""
    states = fx.window(2)
    i = next(i for i, s in enumerate(states) if s["f"] == 68995)
    states[i - 1]["hero"]["anim"]["clip"] = "NeedleThrow Throwing"
    bits = cstate.decode(states[i]["hero"]["cstate"], NAMES)
    bits["recoiling"] = True
    states[i]["hero"]["cstate"] = cstate.encode(bits, NAMES)
    states[i]["hero"]["anim"]["clip"] = "Stun"
    w = run(states[:i + 1])[-1]
    assert w.hero.mode.v == "hurt"
    (hit,) = [e.data for e in w.events if e.kind == Ev.HIT_DEALT]
    assert hit.hero_anim == "NeedleThrow Throwing"


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


def test_kind_follows_the_projectile_bit_with_a_short_hold():
    states = fx.window(0)[-40:]
    bell = next(e for e in states[0]["ents"] if e["type_key"] == "BoneBeast DropBell L")
    bell["src"] = 34
    wss = run(states)
    t0 = wss[0].stamp.t_game_s
    for w in wss:
        kind = next(e.kind for e in w.entities if e.id == bell["iid"])
        assert kind == (Kind.PROJECTILE if w.stamp.t_game_s - t0 <= PROJECTILE_HOLD_S else Kind.ENEMY_ATTACK)
    assert wss[-1].stamp.t_game_s - t0 > PROJECTILE_HOLD_S       # the hold ended inside the window


# ---- the TakeDamage gate: one case per hazard type -------------------------------------------------------------

@pytest.mark.parametrize("name", HAZARD_TYPES + ("cog", "unknown"))
def test_damage_flags_follow_the_take_damage_gate(name):
    """HeroController.cs:5369 (m0:N1): with hit or parry i-frames only ENEMY, NON_HAZARD and EXPLOSION return
    early; the parry stance parries ENEMY only (cs:5391); cogs deal TakeDamage(1, SPIKES)."""
    h = HAZARD_TYPES.index(name) if name in HAZARD_TYPES else 99 if name == "unknown" else 1
    d = {"parry": 0, "flags": 0, "hazard_type": h, "eff": 1}
    flags = damage_flags(d, cog=name == "cog")
    stopped_by_iframes = name in ("ENEMY", "NON_HAZARD", "EXPLOSION")
    assert ("IGNORES_IFRAMES" in flags) == (not stopped_by_iframes)
    assert ("IGNORES_PARRY" in flags) == (name != "ENEMY")
    expect = Hazard.COG if name == "cog" else Hazard.OTHER if name == "unknown" else HAZARD_OF[name]
    assert box_hazard(d, cog=name == "cog") == expect


def test_damage_flag_bits():
    d = {"parry": 1 | 4, "flags": 4 | 16 | 2, "hazard_type": 1, "eff": -1}
    assert damage_flags(d) == {"PARRYABLE", "DEFLECTABLE", "COUNTER", "FLAME", "TAG_ACID", "NON_LETHAL", "AMOUNT_FSM"}
    assert damage_flags({"parry": 2, "flags": 0, "hazard_type": 1, "eff": 2}) == {"PARRYABLE"}


def test_cog_entity_boxes_go_through_iframes():
    s = fx.window(0)[-1]
    bell = next(e for e in s["ents"] if e["type_key"] == "BoneBeast DropBell L")
    bell["src"] = 2 | 16
    w = OracleBackend(clock=None).feed(s)
    box = next(e for e in w.entities if e.id == bell["iid"]).dmg_boxes[0]
    assert box.hazard == Hazard.COG and {"IGNORES_IFRAMES", "IGNORES_PARRY"} <= box.flags


# ---- positions (§4.1) ------------------------------------------------------------------------------------------

def test_positions_are_collider_centres_with_the_transform_kept(wake):
    states = {s["f"]: s for s in fx.window(0)}
    w = at(wake, 56830)
    s = states[56830]
    b = s["hero"]["box"]
    assert w.hero.pos.v == pytest.approx(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
    assert w.hero.pos_transform == pytest.approx(tuple(s["hero"]["pos"][:2]))
    assert w.hero.pos.v[1] < w.hero.pos_transform[1]                # the hurtbox centre is below the transform
    e = next(x for x in s["ents"] if x["iid"] == fx.BOSS_IID)
    boss = next(x for x in w.entities if x.id == fx.BOSS_IID)
    v = e["colliders"][0]["verts_world"]
    assert boss.pos.v == pytest.approx(((min(v[0::2]) + max(v[0::2])) / 2, (min(v[1::2]) + max(v[1::2])) / 2))
    assert boss.pos_transform == pytest.approx(tuple(e["pos"][:2]))
    assert boss.anim == ("Charge Loop", 1) and boss.render_box == pytest.approx(tuple(e["render_aabb"]))
    assert boss.flip_x is True and boss.hidden is False


def test_main_collider_rules():
    e = {"type_key": "Bone Beast", "pos": [1.0, 2.0, 0.0], "render_aabb": [0.0, 0.0, 4.0, 2.0], "colliders": [
        {"verts_world": [10, 10, 12, 10, 12, 14, 10, 14]}, {"verts_world": [20, 20, 22, 20, 22, 22]}]}
    assert entity_pos(e) == (11.0, 12.0)                              # no names: the first collider
    e["colliders"][0]["name"] = "PolyCollider"
    e["colliders"][1]["name"] = "Bone Beast (1)"
    assert type_key_of("Bone Beast (1)") == "Bone Beast" and type_key_of("Bell(Clone) (2)") == "Bell"
    assert entity_pos(e) == (21.0, 21.0)                              # names: the root's own collider
    e["colliders"][1]["name"] = "LeapCollider"
    assert entity_pos(e) == (2.0, 1.0) and main_collider(e) is None   # no root collider: the sprite bounds
    e["colliders"], e["render_aabb"] = [], None
    assert entity_pos(e) == (1.0, 2.0)                                # nothing: the transform


# ---- hits taken ---------------------------------------------------------------------------------------------

def _hit_state(extra_events: list[dict], amount: int = 1, hazard: str = "LAVA", source: str = "Lava Pool/Collider"
               ) -> list[dict]:
    states = fx.window(0)[100:102]
    s = states[1]
    s["ev"] = [{"k": "damage", "f": s["f"], "q": s["q"],
                "d": {"source": source, "amount": amount, "hazard": hazard}}] + extra_events
    return states


def test_hit_amount_is_the_masks_taken_not_the_raw_argument():
    s0 = fx.window(0)[100]
    hp = s0["hero"]["health"]
    states = _hit_state([{"k": "hp", "d": {"amount": 2, "delta": -2, "blue_delta": 0, "src": "TakeHealth"}}])
    states[1]["hero"]["health"] = hp - 2
    hit = next(e.data for e in run(states)[1].events if e.kind == Ev.HIT_TAKEN)
    assert (hit.amount, hit.amount_raw, hit.hazard) == (2, 1, Hazard.LAVA)
    assert hit.source_type is None and hit.source_id is None          # unresolved: no object path in a D field
    assert hit.caller_path == "Lava Pool/Collider"
    # no TakeHealth tap: the STATE's HP drop
    states = _hit_state([])
    states[1]["hero"]["health"] = hp - 1
    hit = next(e.data for e in run(states)[1].events if e.kind == Ev.HIT_TAKEN)
    assert hit.amount == 1



def test_a_rejected_take_damage_is_not_a_hit():
    """A TakeDamage call a later gate rejected (downspike invulnerability on a pogo, HeroController.cs:5385): no
    health, no recoil -> DAMAGE_BLOCKED (O), and the i-frame clock is not restarted. A 0-mask hit that puts the hero
    into recoil (Warding Bell bind shield) is still a hit."""
    states = _hit_state([], hazard="ENEMY", source="Bone Beast/PolyCollider")
    bits = cstate.decode(states[1]["hero"]["cstate"], NAMES)
    bits.update(recoiling=False, recoilFrozen=False, downSpikeBouncing=True)
    states[1]["hero"]["cstate"] = cstate.encode(bits, NAMES)
    b = OracleBackend(bosses=[BELL_BEAST], clock=None)
    w = [b.feed(s) for s in states][1]
    assert not [e for e in w.events if e.kind == Ev.HIT_TAKEN]
    (blk,) = [e.data.d for e in w.events if e.kind == Ev.DAMAGE_BLOCKED]
    assert blk["why"] == "pogo" and blk["end"] == "rejected"
    assert b.m.hero.hit_t == -math.inf
    bits.update(downSpikeBouncing=False, recoilFrozen=True)
    states[1]["hero"]["cstate"] = cstate.encode(bits, NAMES)
    hit = next(e.data for e in run(states)[1].events if e.kind == Ev.HIT_TAKEN)
    assert hit.amount == 0 and hit.amount_raw == 1


def test_lethal_blocked_hit_reports_its_damage(wake):
    hit = next(e.data for e in at(wake, 56777).events if e.kind == Ev.HIT_TAKEN)
    assert (hit.amount, hit.amount_raw) == (2, 2)


def test_special_damage_has_no_source_type():
    states = fx.window(0)[100:102]
    s = states[1]
    s["ev"] = [{"k": "special_damage", "f": s["f"], "d": {"amount": 1, "method": "TakeQuickDamage"}}]
    hit = next(e.data for e in run(states)[1].events if e.kind == Ev.HIT_TAKEN)
    assert hit.source_type is None and hit.caller_path == "TakeQuickDamage"


# ---- hero ---------------------------------------------------------------------------------------------------

def _hero_state(**bits) -> dict:
    s = fx.window(0)[-1]
    if bits:
        b = cstate.decode(s["hero"]["cstate"], NAMES)
        b.update(bits)
        s["hero"]["cstate"] = cstate.encode(b, NAMES)
    return s


def test_dash_cooldown_uses_can_dash():
    s = _hero_state(dashing=False, airDashing=False, backDashing=False)
    s["hero"]["can"]["dash"] = True
    w = OracleBackend(clock=None).feed(s)
    assert w.hero.dash_cd_left.v == 0.0 and w.hero.dash_cd_left.src == Src.ORACLE
    s["hero"]["can"]["dash"] = False          # no dash seen, yet CanDash is false: another writer of the timer
    w = OracleBackend(clock=None).feed(s)
    assert w.hero.dash_cd_left.conf == 0.5 and w.hero.dash_cd_left.sigma >= 0.1


def test_wall_side():
    s = _hero_state(onGround=False, touchingWall=True, wallSliding=False, wallClinging=False)
    s["hero"]["facing"] = 1
    w = OracleBackend(clock=None).feed(s)
    assert w.hero.contact.v == "WALL_R" and w.hero.contact.conf == 0.5        # touching only: side unknown
    s["hero"]["wall"] = [True, False]
    w = OracleBackend(clock=None).feed(s)
    assert w.hero.contact.v == "WALL_L" and w.hero.contact.conf == 1.0        # oracle hero.wall
    s = _hero_state(onGround=False, wallSliding=True)
    s["hero"]["facing"] = -1
    w = OracleBackend(clock=None).feed(s)
    assert w.hero.contact.v == "WALL_L" and w.hero.contact.conf == 1.0        # sliding faces the wall


def test_resources_unknown_without_player_data():
    s = fx.window(0)[0]
    for k in ("health", "max_health", "health_blue", "silk", "silk_max", "geo", "shell_shards", "crest", "tools",
              "tool_amounts", "fractured_mask"):
        s["hero"].pop(k, None)
    w = OracleBackend(clock=None).feed(s)
    r = w.res
    assert r.hp.src == Src.UNKNOWN and r.hp.conf == 0.0 and r.hp_max.conf == 0.0 and r.silk.conf == 0.0
    assert r.crest.conf == 0.0 and r.tools == []
    assert w.hero.pos.conf == 1.0                                              # the hero itself is known


def test_bind_at_full_hp_is_done_from_the_spell_fsm():
    states = fx.window(0)[-4:]
    for i, s in enumerate(states[1:3]):
        bits = cstate.decode(s["hero"]["cstate"], NAMES)
        bits["isBinding"] = True
        s["hero"]["cstate"] = cstate.encode(bits, NAMES)
        s["hero"]["spell"] = ["Binding", 0.1] if i == 0 else ["Bind Burst", 0.0]
    states[3]["hero"]["spell"] = ["Cooldown", 0.0]
    for s in states:
        s["hero"]["health"] = s["hero"]["max_health"]
    wss = run(states)
    assert [e.kind for e in wss[3].events if e.kind.name.startswith("BIND")] == [Ev.BIND_DONE]
    states[2]["hero"]["spell"] = ["Binding", 0.2]                    # interrupted before the burst
    wss = run(states)
    assert [e.kind for e in wss[3].events if e.kind.name.startswith("BIND")] == [Ev.BIND_BROKEN]


def test_new_hero_fields_when_exported():
    s = _hero_state(invulnerable=True)
    h = s["hero"]
    h["tm"] = {"inv": 0.5, "recoil": 0.1, "recoil_steps": 0, "dash_cd": 0.2, "atk_cd": 0.15, "atk_t": 0.1,
               "tool_cd": 0.0, "jump_steps": 3, "jumped_steps": 2, "ds": 0.0, "ds_rec": 0.0, "grav": 1.0,
               "qj": 0, "qa": 0, "qt": 0}
    h["alpha"] = 0.25
    h["tags"] = [{"kind": "acid", "dmg_left": 2, "t_left": 1.5}, {"kind": "flame", "dmg_left": 1, "t_left": 0.5}]
    h["tool_max"] = [None] * len(h["tools"])
    slot = next(i for i, x in enumerate(h["tools"]) if x)
    h["tool_max"][slot] = 12
    w = OracleBackend(clock=None).feed(s)
    hero = w.hero
    assert (hero.iframes_left.v, hero.recoil_left.v, hero.dash_cd_left.v) == (0.5, 0.1, 0.2)
    assert all(x.src == Src.ORACLE for x in (hero.iframes_left, hero.recoil_left, hero.dash_cd_left))
    assert hero.action_lock_left.v >= 0.15 and hero.phys_alpha == 0.25 and hero.tm["jump_steps"] == 3.0
    assert w.res.pending_dmg.v == 3 and w.res.pending_dmg.src == Src.ORACLE and {"ACID", "FLAME"} <= w.res.status
    assert w.res.tools[0].ammo_max == 12


def test_pending_damage_is_lethal_when_unbounded_or_unknown():
    """hero.tags dmg_left -1 (no hit limit: frost water), the frost clock and a stream without hero.tags never read as
    0 pending damage: conf 0 and v = health + blue (state_fields_m2.md §4; hits_to_death subtracts it)."""
    s = _hero_state(isFrosted=False)
    h = s["hero"]
    total = h["health"] + int(h.get("health_blue") or 0)
    h["tags"] = [{"kind": "Frost Water Tag", "dmg_left": -1, "t_left": 0.4}, {"kind": "acid", "dmg_left": 2}]
    p = OracleBackend(clock=None).feed(s).res.pending_dmg
    assert (p.v, p.conf) == (total, 0.0) and p.src != Src.ORACLE
    h["tags"] = [{"kind": "acid", "dmg_left": None}]                    # unreadable
    assert OracleBackend(clock=None).feed(s).res.pending_dmg.v == total
    h["tags"] = None                                                     # no TagDamageTaker: nothing can attach
    p = OracleBackend(clock=None).feed(s).res.pending_dmg
    assert (p.v, p.conf, p.src) == (0, 1.0, Src.ORACLE)
    h["tags"] = []
    assert OracleBackend(clock=None).feed(s).res.pending_dmg.v == 0
    del h["tags"]                                                        # an oracle without the export
    p = OracleBackend(clock=None).feed(s).res.pending_dmg
    assert (p.v, p.conf, p.src) == (total, 0.0, Src.UNKNOWN)
    s = _hero_state(isFrosted=True)                                      # the frost clock: 1 HP every 1.75 s
    s["hero"]["tags"] = []
    w = OracleBackend(clock=None).feed(s)
    assert (w.res.pending_dmg.v, w.res.pending_dmg.conf) == (total, 0.0) and "FROST" in w.res.status


def test_screen_splits_loading_from_entering():
    s = fx.window(0)[0]
    s["game"]["gs"] = 3
    assert OracleBackend(clock=None).feed(s).game.screen.v == Screen.FADE
    s["game"]["gs"] = 2
    assert OracleBackend(clock=None).feed(s).game.screen.v == Screen.TRANSITION
    s["game"]["gs"] = 4
    s["pause"]["interact"] = True                                  # a BlockingInteractable: dialogue, door, shop
    assert OracleBackend(clock=None).feed(s).game.screen.v == Screen.DIALOG


def test_menu_and_gates_when_exported():
    s = fx.window(0)[0]
    s["menu"] = {"sel": "quit", "quit_ok": False, "dim": 0.6, "alpha": 1.0, "ignore_unpause": False,
                 "quitting": False}
    s["room"] = {"gates": [{"name": "Battle Gate L", "enabled": True, "box": [70.0, 2.0, 71.0, 10.0]}]}
    w = OracleBackend(clock=None).feed(s)
    assert w.game.menu.cursor_item == "quit" and w.game.menu.quit_greyed is True
    assert w.terrain.dynamic_deltas == [("Battle Gate L", True)]
    assert w.terrain.gates == [("Battle Gate L", True, (70.0, 2.0, 71.0, 10.0))]


# ---- entities: hidden, hit events -----------------------------------------------------------------------------

def test_hidden_entity_is_exported_without_boxes():
    states = fx.window(0)
    i = next(i for i, s in enumerate(states) if any(e["iid"] == fx.BOSS_IID for e in s["ents"]))
    s = states[i]
    e = next(e for e in s["ents"] if e["iid"] == fx.BOSS_IID)
    e.update(hidden=True, colliders=[], render_aabb=None)
    w = OracleBackend(bosses=[BELL_BEAST], clock=None).feed(s)
    boss = next(x for x in w.entities if x.id == fx.BOSS_IID)
    assert boss.hidden and boss.visible_frac == 0.0 and boss.dmg_boxes == [] and boss.body_polys == []
    assert boss.pos.v == pytest.approx(tuple(e["pos"][:2])) and boss.kind == Kind.BOSS


def _hit(f: int, ent: int, before: int, after: int, attack: str = "Nail", src: str | None = "Slash", **kw) -> dict:
    return {"k": "hit", "f": f, "d": {"ent": ent, "type_key": kw.pop("type_key", "Bone Beast"), "dmg": before - after,
                                      "dealt": before - after, "attack": attack, "src": src, "hp_before": before,
                                      "hp_after": after, "dead": after <= 0, "crit": False, **kw}}


def test_hit_events_give_hits_and_the_killing_blow():
    """state_fields_m2.md §8: "attack" is an AttackTypes name, "src" the attacking object; the killing blow is
    hp_before > 0 >= hp_after (later corpse hits carry dead too); every source is reported."""
    states = fx.window(2)
    for s in states:
        if s["f"] == 68995:
            s["ev"].append(_hit(68995, fx.BOSS_IID, 20, 15))
        if s["f"] == 69029:
            s["ev"].insert(0, _hit(69029, fx.BOSS_IID, 15, 0, attack="Generic", src="Spear"))
        if s["f"] == 69030:
            s["ev"].append(_hit(69030, fx.BOSS_IID, 0, -5))                       # a hit on the corpse
            s["ev"].append(_hit(69030, 999999, 3, 0, type_key="Bug"))            # an enemy never exported
        if s["f"] == 69031:
            s["ev"].append(_hit(69031, 999999, 0, -2, type_key="Bug"))           # its corpse
            s["ev"].append(_hit(69031, 999998, 10, 8, attack="Lava", src="Lava Pool", type_key="Bug"))
    wss = run(states)
    hits = events(wss, Ev.HIT_DEALT)
    assert [(f, d.target_id, d.amount, d.attack, d.src, d.killing, d.by_hero) for f, d in hits] == [
        (68995, fx.BOSS_IID, 5.0, "Nail", "Slash", False, None),
        (69029, fx.BOSS_IID, 15.0, "Generic", "Spear", True, None),
        (69030, fx.BOSS_IID, 5.0, "Nail", "Slash", False, None), (69030, 999999, 3.0, "Nail", "Slash", True, None),
        (69031, 999999, 2.0, "Nail", "Slash", False, None), (69031, 999998, 2.0, "Lava", "Lava Pool", False, False)]
    assert hits[-1][1].hero_anim is None and hits[0][1].hero_anim is not None
    assert [(f, d.target_id) for f, d in events(wss, Ev.ENEMY_KILLED)] == [(69029, fx.BOSS_IID), (69030, 999999)]


def test_hero_without_state_is_unknown():
    s = fx.window(0)[0]
    s["hero"] = None
    w = OracleBackend(clock=None).feed(s)
    assert w.hero.pos.conf == 0.0 and w.res.hp.src == Src.UNKNOWN
    assert w.hero.iframes_left is None and math.isfinite(w.stamp.t_game_s)
    assert np.isfinite(w.cam.x)


