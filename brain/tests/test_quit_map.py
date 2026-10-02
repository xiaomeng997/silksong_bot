"""Quit map v0: the builder over a synthetic STATE stream (hit, hazard death, freeze, dialogue, scene change, pause),
censoring of deaths and harness operations, cause priority, transition splits, the query API (unknown is not "not
quittable"), and the committed knowledge/1.0.30000/quit_map.json."""
import json
import math

import pytest

from ssbot.safety import game_codes as gc
from ssbot.safety.invariants import ZONE_KINDS
from ssbot.safety.quit_map import DEFAULT_PATH, KEYS, QuitMap, QuitMapBuilder, QuitMapParams, cause_kind

DT = 1 / 60


class Stream:
    def __init__(self):
        self.f = 0
        self.out: list[dict] = []

    def add(self, n: int, scene: str = "Bone_05", gs: int = gc.GS_PLAYING, blk: int = 0, dsq: bool = False,
            preload: bool = False, interact: bool = False, slowed: int = 0, ev: list | None = None) -> None:
        for i in range(n):
            self.out.append({"f": self.f, "udt": DT, "ev": (ev or []) if i == 0 else [],
                             "game": {"gs": gs, "scene": scene, "slowed": slowed},
                             "pause": {"blk": blk, "dsq": dsq, "preload": preload, "interact": interact,
                                       "inv": False}})
            self.f += 1


def _ev(k: str, **d) -> dict:
    return {"k": k, "f": 0, "d": d}


def _build() -> dict:
    s = Stream()
    s.add(120, ev=[_ev("scene_enter")])                                         # 60 entry + 60 free frames
    s.add(15, blk=gc.BLK_DISABLE_PAUSE | gc.BLK_TIME_SLOWED, ev=[_ev("damage", hazard="ENEMY")])   # 0.25 s
    s.add(60)                                                                   # 3 more hurt0 frames, then hurt1
    s.add(138, blk=gc.BLK_DISABLE_PAUSE, ev=[_ev("hazard_death", hazard="SPIKES")])                # 2.3 s
    s.add(1, ev=[_ev("hazard_respawn", phase="end")])
    s.add(60)                                                                   # 0.5 s hazard tail, then free
    s.add(83, slowed=1, blk=gc.BLK_TIME_SLOWED, ev=[_ev("freeze", phase="start", type="BossDeathSlow")])
    s.add(10)
    s.add(60, dsq=True)                                                         # quit greyed, pause fine
    s.add(100)
    s.add(30, gs=gc.GS_PAUSED, blk=gc.BLK_GAME_STATE)                           # not samples
    s.add(40, blk=gc.BLK_BLOCKING_INTERACT, interact=True)
    s.add(10)
    s.add(20, gs=gc.GS_EXITING_LEVEL, blk=gc.BLK_GAME_STATE, ev=[_ev("gs", to="EXITING_LEVEL", to_i=6, from_i=4)])
    s.add(40, scene="Bone_06", ev=[_ev("scene_enter")])
    b = QuitMapBuilder(QuitMapParams(entry_s=0.99, hurt0_s=0.29))   # off the frame grid: no float ties at 60 fps
    b.begin("synthetic", "test")
    for st in s.out:
        b.add(st)
    return b.build({"generated": "test"})


def test_builder_keys_and_probabilities():
    d = _build()
    sc = d["scenes"]["Bone_05"]
    bk = sc["by_key"]
    assert bk["entry"]["frames"] == 60 and bk["entry"]["p_pause"] == 1.0
    assert bk["hurt0"]["frames"] == 18 and bk["hurt0"]["p_pause"] == pytest.approx(3 / 18, abs=1e-4)
    assert bk["hazard"]["p_pause"] == pytest.approx(31 / 169, abs=0.01)   # 138 blocked, respawn + 0.5 s tail free
    assert bk["freeze"]["p_pause"] == 0.0 and bk["freeze"]["frames"] == 83
    assert bk["interact"]["p_pause"] == 0.0
    assert bk["free"]["p_quit"] < bk["free"]["p_pause"] == 1.0  # the disableSaveQuit second
    assert bk["transition"]["p_pause"] == 0.0
    assert sc["dsq_s"] == pytest.approx(1.0, abs=1e-3)
    assert set(bk) <= set(KEYS)
    assert d["sources"][0]["frames"] == 787 and d["sources"][0]["samples"] == 757     # paused frames are no samples
    assert d["scenes"]["Bone_06"]["by_key"]["entry"]["frames"] == 40


def test_builder_windows():
    d = _build()
    pw = d["scenes"]["Bone_05"]["pause_windows"]
    by = pw["by_key"]
    assert by["hurt0"]["max_s"] == pytest.approx(0.25, abs=1e-3)
    assert by["hazard"]["max_s"] == pytest.approx(2.3, abs=1e-3)
    assert by["freeze"]["max_s"] == pytest.approx(83 / 60, abs=1e-3)
    assert by["transition"]["n"] == 1                         # exit + the new scene's entry is one window
    longs = d["scenes"]["Bone_05"]["long_windows"]
    assert [w["key"] for w in longs][:2] == ["hazard", "freeze"]
    assert longs[0]["cause"] == "hazard_death:SPIKES" and "DISABLE_PAUSE" in longs[0]["bits"]
    qw = d["scenes"]["Bone_05"]["quit_windows"]
    assert qw["n"] == pw["n"] + 1                             # the disableSaveQuit stretch blocks only quitting


def test_query_api():
    qm = QuitMap(_build())
    assert qm.p_pause("Bone_05", "entry") == 1.0
    assert qm.p_quit("Bone_05", "hurt0") == pytest.approx(3 / 18, abs=1e-4)
    assert qm.p_pause("Nowhere", "free") is None
    assert qm.p_pause("Nowhere", "free", fallback=True) is not None
    assert qm.quittable("Bone_05", "entry") and qm.quittable("Bone_05", "hurt0", min_s=0.2) is False
    assert qm.quittable("Bone_05", "hurt0") is None           # 0.3 s of samples: too little to tell
    assert qm.quittable("Bone_05", "free") is False           # the disableSaveQuit second
    # review: no data used to read as "not quittable", which left I1 vacuous; it is unknown now
    assert qm.quittable("Nowhere", "free") is None and qm.quittable("Bone_05", "inventory") is None
    zones = qm.commit_zones("Bone_05")
    assert zones[0].kind == "window" and zones[0].seconds == pytest.approx(2.3, abs=1e-3)
    assert "hazard" in zones[0].key
    # a scene the map has no data on: one unknown zone of unbounded length (I3 never has nothing to check)
    (z,) = qm.commit_zones("Nowhere")
    assert z.kind == "unknown" and z.seconds == math.inf
    # the window the hero is in now
    assert qm.current_zone("Bone_05", "entry") is None
    assert qm.current_zone("Bone_05", "hurt0").kind == "unknown"
    hurt0 = qm.current_zone("Bone_05", "hurt0", min_s=0.2)
    assert hurt0.kind == "window" and hurt0.seconds == pytest.approx(0.25, abs=1e-3)
    assert qm.current_zone("Nowhere", "free").kind == "unknown"
    assert qm.current_zone("Bone_05", "inventory").kind == "unknown"


def _stream_states(*chunks) -> list[dict]:
    s = Stream()
    for kw in chunks:
        s.add(**kw)
    return s.out


def _build_from(states: list[dict], **params) -> dict:
    b = QuitMapBuilder(QuitMapParams(**params) if params else None)
    b.begin("synthetic", "test")
    for st in states:
        b.add(st)
    return b.build()


def test_deaths_and_harness_operations_are_censored():
    """Review: a BossDeathSlow window ran through a savestate.load (trial f56112, 1.622 s) and the person's death
    (human f6841, 4.58 s) was stored as a hurt0 window."""
    slow = gc.BLK_TIME_SLOWED
    d = _build_from(_stream_states(
        dict(n=120, ev=[_ev("scene_enter")]),
        dict(n=90, slowed=1, blk=slow, ev=[_ev("freeze", phase="start", type="BossDeathSlow")]),
        dict(n=10, blk=slow, ev=[_ev("harness", op="savestate.load", ms=120.0)]),
        dict(n=60),
        dict(n=20, blk=gc.BLK_DISABLE_PAUSE, ev=[_ev("damage", hazard="ENEMY")]),
        dict(n=5, blk=gc.BLK_DISABLE_PAUSE, ev=[_ev("hero_dead")]),
        dict(n=200, blk=gc.BLK_DISABLE_PAUSE),                           # dead: no samples until the next entry
        dict(n=70, ev=[_ev("scene_enter")])))
    sc = d["scenes"]["Bone_05"]
    assert sc["long_windows"] == [] and "boss_death_slowmo" not in d["kinds"]
    qw = sc["quit_windows"]
    assert qw["n"] == 0 and qw["censored"] == 2
    # the 9 frames of the load's 120 ms (+ 2 frames) are taken back, the 10 slowed frames after it are held out, and
    # nothing counts from the death to the next entry
    assert d["sources"][0]["samples"] == 120 + (90 - 9) + 60 + 20 + 70
    assert d["scenes"]["Bone_05"]["by_key"]["freeze"]["frames"] == 81
    # the same window without the harness op is kept
    d = _build_from(_stream_states(
        dict(n=120, ev=[_ev("scene_enter")]),
        dict(n=90, slowed=1, blk=slow, ev=[_ev("freeze", phase="start", type="BossDeathSlow")]),
        dict(n=60)))
    assert d["kinds"]["boss_death_slowmo"]["max_s"] == pytest.approx(1.5, abs=1e-3)
    # a harness op long after a window closed does not touch it
    d = _build_from(_stream_states(
        dict(n=120, ev=[_ev("scene_enter")]),
        dict(n=90, slowed=1, blk=slow, ev=[_ev("freeze", phase="start", type="BossDeathSlow")]),
        dict(n=60), dict(n=10, ev=[_ev("harness", op="randomize_start")]), dict(n=10)))
    assert d["kinds"]["boss_death_slowmo"]["n"] == 1


def test_window_cause_by_priority_not_last_logged():
    """Review: a LAVA hazard death (human f105032, 2.433 s) was labelled freeze:EnemyDeath (the last event logged)."""
    dp = gc.BLK_DISABLE_PAUSE
    d = _build_from(_stream_states(
        dict(n=120, ev=[_ev("scene_enter")]),
        dict(n=1, blk=dp, ev=[_ev("hazard_death", hazard="LAVA"), _ev("freeze", phase="start", type="EnemyDeath")]),
        dict(n=145, blk=dp), dict(n=1, ev=[_ev("hazard_respawn", phase="end")]), dict(n=60),
        # a freeze starts the window and the hazard death is logged a frame later
        dict(n=1, blk=dp, ev=[_ev("freeze", phase="start", type="EnemyDeath")]),
        dict(n=1, blk=dp, ev=[_ev("hazard_death", hazard="SPIKES")]),
        dict(n=136, blk=dp), dict(n=1, ev=[_ev("hazard_respawn", phase="end")]), dict(n=60)))
    causes = [w["cause"] for w in d["scenes"]["Bone_05"]["long_windows"]]
    assert causes == ["hazard_death:LAVA", "hazard_death:SPIKES"]
    hz = d["kinds"]["hazard_death"]
    assert hz["by_hazard"]["LAVA"] == pytest.approx(146 / 60, abs=1e-3) and hz["n"] == 2
    assert hz["by_hazard"]["SPIKES"] == pytest.approx(138 / 60, abs=1e-3)
    assert hz["max_s"] == pytest.approx(146 / 60, abs=1e-3)
    assert cause_kind("hazard_damage:SPIKES") == ("hazard_death", "SPIKES")
    assert cause_kind("freeze:EnemyBattleEndSlow") == ("arena_end_slowmo", None)
    assert cause_kind("damage:ENEMY", "entry") == ("room_entry", None) and cause_kind("damage:ENEMY") == (None, None)


def test_a_transition_window_is_split_where_playing_resumes():
    """Review: an unpausable span that starts in a transition and runs on into the new room (a boss intro on entry, the
    HUDCamera lock after a cutscene) was the old room's transition window and never a commit zone of the new room."""
    gsb = gc.BLK_GAME_STATE
    d = _build_from(_stream_states(
        dict(n=120, ev=[_ev("scene_enter")]),
        dict(n=20, gs=gc.GS_EXITING_LEVEL, blk=gsb, ev=[_ev("gs", to="EXITING_LEVEL", to_i=6, from_i=4)]),
        dict(n=10, gs=gc.GS_LOADING, scene="Bone_06", blk=gsb),
        dict(n=48, scene="Bone_06", blk=gc.BLK_DISABLE_PAUSE, ev=[_ev("scene_enter")]),   # 0.8 s locked in PLAYING
        dict(n=60, scene="Bone_06")))
    assert d["scenes"]["Bone_05"]["quit_windows"]["by_key"]["transition"]["n"] == 1
    new = d["scenes"]["Bone_06"]
    assert [(w["key"], w["s"]) for w in new["long_windows"]] == [("entry", pytest.approx(0.8, abs=1e-3))]
    qm = QuitMap(d)
    assert qm.kind_max_s("room_entry", "Bone_06") == pytest.approx(0.8, abs=1e-3)
    z = qm.zone("room_entry", "Bone_06")
    assert z.kind == "room_entry" and z.seconds == pytest.approx(0.8, abs=1e-3)
    assert qm.zone("room_entry", "Bone_05").seconds == ZONE_KINDS["room_entry"]     # nothing longer seen there


def test_zone_lengths_are_the_larger_of_the_floor_and_the_map():
    qm = QuitMap({"kinds": {"hazard_death": {"n": 3, "max_s": 2.6, "by_hazard": {"SPIKES": 2.317, "LAVA": 2.6}},
                            "boss_death_slowmo": {"n": 1, "max_s": 1.383, "by_hazard": {}}}, "scenes": {}})
    assert qm.zone("hazard_death", "Bone_05", hazard="LAVA", hazard_damage=2).seconds == 2.6
    assert qm.zone("hazard_death", "Bone_05", hazard="SPIKES").seconds == ZONE_KINDS["hazard_death"]
    assert qm.zone("hazard_death", "Bone_05", hazard="ACID").seconds == 2.6      # unseen type: every type's max
    assert qm.zone("boss_death_slowmo", "Bone_05").seconds == ZONE_KINDS["boss_death_slowmo"]
    assert qm.zone("boss_intro", "Bone_05").seconds == math.inf                   # never measured: unbounded
    z = qm.zone("hazard_death", "Bone_05", hazard="LAVA", hazard_damage=2)
    assert z.hazard_damage == 2 and z.key == "Bone_05:hazard_death:LAVA"


def test_committed_quit_map():
    if not DEFAULT_PATH.is_file():
        pytest.skip("knowledge/1.0.30000/quit_map.json not built")
    qm = QuitMap.load()
    assert qm.data["version"] == 0 and qm.data["build"] == "1.0.30000"
    assert {s["kind"] for s in qm.data["sources"]} >= {"human", "train"}
    bone = qm.windows("Bone_05")["pause"]
    assert bone["n"] > 10_000 and bone["p95_s"] <= 0.25       # probe P7: 0.25 s without pause after an enemy hit
    assert 0.5 <= bone["by_key"]["hurt0"]["max_s"] <= 0.56     # ... 0.55 s for a hit during a Bind (BindBreak)
    assert qm.p_pause("Bone_05", "entry") > 0.99              # savestate loads no longer pollute "entry"
    kinds = qm.data["kinds"]
    assert kinds["hazard_death"]["by_hazard"]["LAVA"] == pytest.approx(2.433, abs=0.01)
    assert qm.p_pause("Bone_05", "free") > 0.99
    # every window kind the map has measured stays within its code floor (ZONE_KINDS), entries excepted (per room)
    for kind, e in qm.data["kinds"].items():
        floor = ZONE_KINDS.get(kind)
        assert floor is None or kind == "room_entry" or e["max_s"] <= floor, (kind, e)
    for sc in qm.scenes.values():
        assert not any(w["censored"] for w in sc.get("long_windows", []))
    json.dumps(qm.data)
