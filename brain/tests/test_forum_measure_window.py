from types import SimpleNamespace

import pytest

from ssbot.train.forum_measure_metrics import audit_states
from ssbot.train.forum_measure_window import CLAPPER, MeasurementWindow


def entity(iid=1, dead=False):
    return {"iid": iid, "type_key": CLAPPER, "hp": 0 if dead else 230,
            "is_dead": dead, "hidden": False}


def state(f, dt=.1, ents=(), ev=(), hp=7, blue=0, next_wave=False):
    return {"f": f, "dt": dt, "ents": list(ents), "ev": list(ev),
            "hero": {"health": hp, "health_blue": blue},
            "room": {"battles": [{"started": True, "wave": 14 if next_wave else 13}]}}


def event(f, kind, **data):
    return {"f": f, "q": f * 100, "k": kind, "d": data}


def window(**kw):
    return MeasurementWindow(SimpleNamespace(wake_frame=10), wave=13, expected_targets=2,
                             game_limit=120, **kw)


def test_wake_origin_is_preserved_when_targets_spawn_later_and_deaths_are_separate():
    obj = window(tail_seconds=.2)
    for f in range(10, 16):
        es = () if f < 12 else (entity(), entity(2))
        if f >= 13:
            es = (entity(dead=True), entity(2, dead=f >= 14))
        obj.observe(state(f, ents=es), f * 100_000_000)
    result = obj.snapshot()
    assert result["wake_f"] == 10 and result["end_f"] == 14
    assert result["T"] == pytest.approx(.5)
    assert result["deaths"] == {"1": 13, "2": 14}
    assert result["complete"]


def test_wave_intro_commits_rebased_wake_after_reader_already_observed_activation():
    tap = SimpleNamespace(wake_frame=8)
    obj = MeasurementWindow(tap, wave=13, expected_targets=2, game_limit=120, defer_wake=True)
    for f in range(8, 13):
        obj.observe(state(f, ents=(entity(), entity(2)) if f >= 10 else (entity(99),)), f * 100_000_000)
    tap.wake_frame = 10
    obj.start_at(tap.wake_frame)  # activation frame was already delivered by the reader
    obj.observe(state(13, ents=(entity(dead=True), entity(2, dead=True))), 1_300_000_000)
    result = obj.snapshot()
    assert result["complete"] and result["wake_f"] == 10
    assert result["target_ids"] == [1, 2] and result["T"] == pytest.approx(.4)


def test_intro_buffer_is_bounded_and_missing_final_wake_never_passes():
    obj = window(defer_wake=True, max_frames=1)
    obj.observe(state(9), 0)
    obj.observe(state(10), 1)
    obj.start_at(None)
    assert not obj.snapshot()["complete"]
    assert set(obj.snapshot()["errors"]) == {"intro STATE buffer capacity exceeded", "intro did not provide final f_wake"}


def test_lethal_same_frame_as_both_deaths_wins_and_does_not_invent_hp_loss():
    obj = window()
    obj.observe(state(10, ents=(entity(), entity(2))), 0)
    obj.observe(state(11, ents=(entity(dead=True), entity(2, dead=True)),
                      ev=(event(11, "would_die"),)), 100_000_000)
    assert obj.snapshot()["end_reason"] == "lethal"
    assert obj.snapshot()["tail_end_f"] == 11


def test_freezes_do_not_advance_game_clock_and_next_wave_cuts_the_tail():
    obj = window()
    obj.observe(state(10, dt=0, ents=(entity(), entity(2))), 0)
    obj.observe(state(11, dt=.05, ents=(entity(dead=True), entity(2, dead=True))), 100_000_000)
    obj.observe(state(12, dt=0), 200_000_000)
    obj.observe(state(13, next_wave=True), 300_000_000)
    result = obj.snapshot()
    assert result["T"] == .05 and result["tail_end_f"] == 12
    assert result["tail_end_reason"] == "next_wave"


def test_wall_timeout_is_independent_of_game_clock():
    obj = window(wall_limit=.2)
    for f in range(10, 13):
        obj.observe(state(f, dt=0, ents=(entity(), entity(2))), (f - 10) * 100_000_000)
    assert obj.snapshot()["end_reason"] == "wall_timeout"
    assert obj.snapshot()["T"] == 0


def test_controller_quit_is_a_measured_failure_but_an_unobserved_fault_stays_invalid():
    for reason, valid in (("episode_quit", True), ("episode_harness_fail", False)):
        obj = window()
        obj.observe(state(10, ents=(entity(), entity(2))), 0)
        obj.observe(state(11, ents=(entity(), entity(2))), 100_000_000)
        obj.finish_at(11, reason)
        assert obj.snapshot()["complete"] is valid
        assert obj.snapshot()["end_reason"] == reason


@pytest.mark.parametrize("bad", ["gap", "dt", "targets"])
def test_missing_clock_or_ambiguous_targets_never_pass(bad):
    obj = window()
    obj.observe(state(10, ents=(entity(), entity(2))), 0)
    s = state(12 if bad == "gap" else 11, ents=(entity(), entity(2), entity(3)) if bad == "targets" else ())
    if bad == "dt":
        s.pop("dt")
    obj.observe(s, 100_000_000)
    assert obj.snapshot()["errors"] and not obj.snapshot()["complete"]


def test_hp_audit_counts_damage_then_heal_in_one_frame_and_blue_loss_separately():
    rows = [state(9, hp=5, blue=2),
            state(10, hp=5, blue=2, ev=(event(10, "hp", delta=0, blue_delta=-2),
                                       event(10, "hp", delta=0, blue_delta=2))),
            state(11, hp=5, blue=0, ev=(event(11, "hp", delta=0, blue_delta=-2),))]
    result = audit_states(rows, wake_f=10, end_f=11)
    assert result["complete"] and result["L"] == 4
    assert result["T"] == pytest.approx(.2)
    assert len(result["losses"]) == 2


def test_late_hp_event_uses_original_frame_and_repeated_record_is_deduplicated():
    first = state(10, hp=5)
    late = state(11, hp=5, ev=(event(10, "hp", delta=-2, blue_delta=0),))
    result = audit_states([state(9), first, first, late], wake_f=10, end_f=10)
    assert result["complete"] and result["L"] == 2
    assert result["losses"][0]["record_f"] == 11


def test_hp_conservation_mismatch_and_raw_gap_are_invalid():
    result = audit_states([state(9), state(10, hp=5), state(12, hp=5)], wake_f=10, end_f=12)
    assert not result["complete"] and not result["hp_conservation"]


def test_hammers_use_enemy_events_and_keep_antic_kills_and_unfinished_attacks_separate():
    rows = [state(9), state(10, ev=(event(10, "fsm", ent=1, fsm="Control", to="Slam Antic"),)),
            state(11, ev=(event(11, "fsm", ent=1, fsm="Control", to="Slam 0"),)),
            state(12, ev=(event(12, "hit", ent=1, src="DownSlash", dealt=21),)),
            state(13, ev=(event(13, "fsm", ent=1, fsm="Control", to="Slam Recover"),)),
            state(14, ev=(event(14, "fsm", ent=2, fsm="Control", to="Slam Antic"),)),
            state(15, ev=(event(15, "hit", ent=2, dead=True, dealt=21),))]
    result = audit_states(rows, wake_f=10, end_f=15, target_ids=(1, 2))
    assert result["hammer_counts"] == {"entered_slam0": 1, "hit": 1, "unknown": 0, "antic_kills": 1}
    assert result["hammer_hit_rate"] == 1
