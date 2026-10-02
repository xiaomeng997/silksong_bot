"""DataPolicy against an M2 oracle STATE: a hidden boss (underground, HealthManager off) is treated as absent, as it was
absent from "ents" when the policy was tuned, so data collection behaves the same across oracle versions."""
import random

from ssbot.ipc.framing import mask
from ssbot.train.data_policy import DataPolicy
from ssbot.train.encounters import BELL_BEAST


class _Tap:
    control = "Submerged"


def _state(hidden: bool | None) -> dict:
    boss = {"iid": -7, "type_key": BELL_BEAST.boss_type, "pos": [92.0, 3.6, 0.0], "hp": 500, "colliders": []}
    if hidden is not None:
        boss["hidden"] = hidden
    return {"hero": {"pos": [80.0, BELL_BEAST.floor_y, 0.0], "facing": 1, "health": 5, "silk": 0},
            "ents": [boss]}


def _moves(hidden: bool | None) -> list[int]:
    pol = DataPolicy()
    pol.reset(random.Random(1), BELL_BEAST)
    out = []
    for _ in range(30):
        pol.mode, pol.mode_left = "PRESS", 1000      # close in: walks right toward a boss it can see
        out.append(pol.act(_state(hidden), _Tap()) & mask("left", "right"))
    return out


def test_hidden_boss_is_not_chased():
    assert all(m == mask("right") for m in _moves(False))
    assert all(m == mask("right") for m in _moves(None))   # pre-M2 STATE without the key
    assert all(m == 0 for m in _moves(True))
