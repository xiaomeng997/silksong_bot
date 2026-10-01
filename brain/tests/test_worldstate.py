"""WorldState schema v2: observability tags, the VISION_EQUIVALENT view, enum values from DESIGN §4.2."""
import types
import typing
from dataclasses import fields

import pytest

from ssbot.core import worldstate as W
from ssbot.core.worldstate import (D, E, Ev, EVENT_OBS, O, V, Entity, Event, HeroState, PauseBlock, PhasePost,
                                   WorldState)


def _optional(tp) -> bool:
    return type(None) in typing.get_args(tp) or tp is typing.Any


def test_every_field_is_tagged_and_every_o_field_can_be_none():
    for cls in W.SCHEMA_CLASSES:
        hints = typing.get_type_hints(cls)
        for f in fields(cls):
            assert f.metadata.get(W.OBS) in (V, O, D), f"{cls.__name__}.{f.name} has no V/O/D tag"
            if f.metadata[W.OBS] == O or f.metadata.get(W.TIMER):
                assert _optional(hints[f.name]), f"{cls.__name__}.{f.name} is O/timer but not Optional"


def test_o_fields_named_in_the_design_are_o():
    assert W.observability(W.Game)["game_state"] == O
    assert W.observability(W.Game)["memory_scene"] == O
    assert W.observability(W.Game)["permadeath_mode"] == O
    assert W.observability(W.PlayTimeEst)["saved_s"] == O
    assert W.observability(HeroState)["can"] == O
    assert W.observability(Entity)["fsm"] == O
    assert W.observability(Entity)["hp_est"] == D
    assert W.timer_fields(HeroState) == ("iframes_left", "recoil_left", "dash_cd_left", "action_lock_left")
    assert all(not W.timer_fields(c) for c in W.SCHEMA_CLASSES if c is not HeroState)


def test_enums_match_the_design():
    assert W.Screen.MSG_CANVAS == 21 and W.Screen.UNKNOWN == 31 and W.Screen.FOREIGN_WINDOW == 20
    assert PauseBlock.GAME_STATE_NOT_PLAYING == 512 and PauseBlock.FOCUS_LOST == 256
    assert W.Kind.HELPER == 12 and W.Kind.UNKNOWN == 15
    assert W.Hazard.SINK == 13 and W.Hazard.OTHER == 15
    assert W.FM.UNKNOWN == 3
    assert not (W.PAUSE_ONLY & (PauseBlock.DISABLE_PAUSE | PauseBlock.PAUSE_LOCKOUT))
    assert set(EVENT_OBS) == set(Ev)
    assert {k for k, v in EVENT_OBS.items() if v == O} >= {Ev.FSM_TRANSITION, Ev.WOULD_DIE, Ev.CATASTROPHE}


def test_e_defaults_and_unknown():
    e = E((1.0, 2.0))
    assert (e.sigma, e.conf, e.src, e.age_ms) == (0.0, 1.0, W.Src.ORACLE, 0.0)
    u = W.unknown(3)
    assert u.v == 3 and u.conf == 0.0 and u.src == W.Src.UNKNOWN
    with pytest.raises(AttributeError):
        e.extra = 1          # slots


def _full_state() -> WorldState:
    ws = WorldState()
    ws.game.game_state = 4
    ws.game.memory_scene = False
    ws.game.permadeath_mode = 0
    ws.game.play_time.saved_s = 12.5
    ws.hero.can = {"dash": True}
    ws.hero.iframes_left = E(0.5)
    ent = Entity(id=7, type_key=E("Bone Beast"), hp_est=E(145.0), fsm=[("Control", "Charge", 0.2)],
                 phase=PhasePost(topk=[("Charge", 1.0)]))
    ws.entities = [ent]
    ws.events = [
        Event(Ev.HIT_TAKEN, 10, 0.1, W.HitTaken(amount=2, caller_path="Bone Beast/PolyCollider")),
        Event(Ev.HIT_DEALT, 10, 0.1, W.HitDealt(7, "Bone Beast", 5.0, 145.0)),
        Event(Ev.FSM_TRANSITION, 10, 0.1, W.FsmTransition(7, "Bone Beast", "Control", "Charge Antic", "Charge")),
        Event(Ev.WOULD_DIE, 10, 0.1, W.Lethal(path="damage")),
        Event(Ev.PAUSE_ON, 10, 0.1, None),
    ]
    return ws


def test_vision_view_nulls_every_o_field_and_drops_o_events():
    ws = _full_state()
    assert ws.view(W.ORACLE) is ws
    v = ws.view(W.VISION_EQUIVALENT)
    leaks = [p for p, obs, _, val in W.iter_fields(v) if obs == O and val is not None]
    assert leaks == []
    assert [e.kind for e in v.events] == [Ev.HIT_TAKEN, Ev.HIT_DEALT, Ev.PAUSE_ON]
    assert v.events[0].data.amount == 2 and v.events[0].data.caller_path is None
    assert v.events[1].data.amount is None and v.events[1].data.target_id == 7
    # V/D values survive, and the view is a copy
    assert v.entities[0].hp_est.v == 145.0 and v.entities[0].phase.top == "Charge"
    assert v.hero.iframes_left.v == 0.5         # timers are the ObservabilityFilter's job, not view()'s
    v.entities[0].pos = E((1.0, 1.0))
    v.entities[0].phase.topk.append(("x", 0.0))
    assert ws.entities[0].pos.v == (0.0, 0.0) and len(ws.entities[0].phase.topk) == 1
    assert ws.entities[0].fsm == [("Control", "Charge", 0.2)] and ws.hero.can == {"dash": True}
    with pytest.raises(ValueError):
        ws.view("SHADOW")


def test_iter_fields_walks_nested_lists():
    paths = {p for p, *_ in W.iter_fields(_full_state())}
    assert "entities[0].fsm" in paths and "events[2].data.to_state" in paths and "game.play_time.saved_s" in paths


def test_dataclasses_are_slotted():
    for cls in W.SCHEMA_CLASSES:
        assert "__slots__" in vars(cls), cls.__name__
    assert isinstance(W.E, type) and not isinstance(W.E, types.GenericAlias)
