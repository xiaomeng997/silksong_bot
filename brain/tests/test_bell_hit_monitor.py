"""The known-effect invariant (train/bell_hit_monitor.py, M2 plan): a drop bell the hero tinks leaves a danger zone
around her no larger than the untouched bell's, once the view has seen the tink."""
import numpy as np
import pytest

from ssbot.combat import pogo_targets as pt
from ssbot.combat.boss_model import BossModel
from ssbot.combat.forecast import Forecaster
from ssbot.core.worldstate import VISION_EQUIVALENT, E, Entity, Kind, WorldState
from ssbot.train.bell_hit_monitor import BellHitMonitor, tinks_of, zone


@pytest.fixture(scope="module")
def spec():
    return next(s for s in pt.load_registry() if s.prefix == "BoneBeast DropBell")


def _run(spec, d: int, k_tink: int, x0: float = 86.6, hero_x: float = 84.6, seed: int = 2) -> BellHitMonitor:
    """A drop bell falling at x0, the hero (facing d) attacking it from 0.05 s before the tink to 0.03 s after,
    detections (sigma 0.1) on the tinked path; the vision view's Forecaster and the monitor every frame."""
    rng = np.random.default_rng(seed)
    fc = Forecaster(BossModel.load("BellBeast"), VISION_EQUIVALENT, margin=(0.5, 0.6), templates={})
    fc.tracker.roots = lambda origin: ([], True)
    mon = BellHitMonitor()
    t_tink = k_tink * 0.02
    f0 = 1000
    for i in range(90):
        t = 20.0 + i / 60
        n = int(np.floor((t - 20.0) / 0.02 + 1e-9))
        cx, cy, _ = pt.simulate(spec, x0, 13.74, 0.0, -17.0, 0, None, np.array([n * 0.02]), side=1,
                                redirect=(t_tink - 1e-9, d))
        ws = WorldState()
        ws.stamp.t_game_s = t
        ws.stamp.frame = f0 + i
        ws.hero.pos = E((hero_x, 3.05))
        ws.hero.facing = E(d)
        ws.hero.mode = E("attack" if t_tink - 0.05 <= t - 20.0 <= t_tink + 0.03 else "ground")
        ws.entities = [Entity(id=7, kind=Kind.ENEMY_ATTACK, type_key=E("BoneBeast DropBell M2"),
                              pos=E((cx[0] + rng.normal(0, 0.1), cy[0] + rng.normal(0, 0.1)), sigma=0.1, conf=1.0),
                              visible_frac=1.0)]
        fc.update(ws)
        s = {"f": f0 + i, "hero": {"box": [hero_x - 0.4, 2.4, hero_x + 0.4, 3.7]}, "ev": []}
        if n * 0.02 >= t_tink and (i == 0 or int(np.floor((t - 1 / 60 - 20.0) / 0.02 + 1e-9)) * 0.02 < t_tink):
            s["ev"] = [{"k": "fsm", "d": {"obj": "BoneBeast DropBell M2", "iid": 7,
                                          "to": "Tink Right" if d > 0 else "Tink Left"}}]
        mon.on_tick(fc.forecast(2.0), f0 + i, t, [s])
    return mon


@pytest.mark.parametrize("d,k", [(1, 12), (-1, 12), (1, 16)])
def test_a_tinked_bell_never_enlarges_the_zone_in_the_vision_view(spec, d, k):
    mon = _run(spec, d, k, hero_x=86.6 - 2.0 * d)
    st = mon.stats()
    assert st["tinks"] == 1 and st["evaluated"] == 1, st
    assert st["violations"] == 0, st["cases"]
    case = st["cases"][0]
    assert case["eval"]["hit"] <= case["eval"]["nohit"] and case["first"] is not None


def test_zone_counts_only_that_bell(spec):
    fc = Forecaster(BossModel.load("BellBeast"), VISION_EQUIVALENT, margin=(0.5, 0.6), templates={})
    fc.tracker.roots = lambda origin: ([], True)
    f = fc.forecast(1.0)
    assert zone(f, "BoneBeast DropBell M2", 85.0, 3.0, 0.0, 1.0) == 0
    assert tinks_of({"ev": [{"k": "fsm", "d": {"obj": "BoneBeast DropBell L", "iid": 3, "to": "Tink Left 2"}},
                            {"k": "fsm", "d": {"obj": "Bone Beast", "iid": 1, "to": "Charge"}}]}) == \
        [(3, "BoneBeast DropBell L")]
