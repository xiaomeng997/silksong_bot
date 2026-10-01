"""Quit map v0: the builder over a synthetic STATE stream (hit, hazard death, freeze, dialogue, scene change, pause),
the query API, and the committed knowledge/1.0.30000/quit_map.json."""
import json

import pytest

from ssbot.safety import game_codes as gc
from ssbot.safety.quit_map import DEFAULT_PATH, KEYS, QuitMap, QuitMapBuilder, QuitMapParams

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
    assert qm.quittable("Bone_05", "entry") and not qm.quittable("Bone_05", "hurt0")
    assert not qm.quittable("Bone_05", "free")                # the disableSaveQuit second
    zones = qm.commit_zones("Bone_05")
    assert zones[0].kind == "window" and zones[0].seconds == pytest.approx(2.3, abs=1e-3)
    assert "hazard" in zones[0].key


def test_committed_quit_map():
    if not DEFAULT_PATH.is_file():
        pytest.skip("knowledge/1.0.30000/quit_map.json not built")
    qm = QuitMap.load()
    assert qm.data["version"] == 0 and qm.data["build"] == "1.0.30000"
    assert {s["kind"] for s in qm.data["sources"]} >= {"human", "train"}
    bone = qm.windows("Bone_05")["pause"]["by_key"]["hurt0"]
    assert 0.2 <= bone["max_s"] <= 0.27                       # probe P7: 0.25 s without pause after an enemy hit
    assert qm.p_pause("Bone_05", "free") > 0.99
    json.dumps(qm.data)
