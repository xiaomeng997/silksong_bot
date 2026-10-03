"""combat.bell_track: drop-bell paths from noisy detections (the vision view's exact bell support, task V)."""
import numpy as np
import pytest

from ssbot.combat.bell_track import DROP_BELL, DropBellTracks
from ssbot.combat.pogo_targets import load_registry, simulate
from ssbot.core.worldstate import E, Entity, Kind, WorldState


@pytest.fixture(scope="module")
def spec():
    return next(s for s in load_registry() if s.prefix == DROP_BELL)


def _ws(t: float, ents: list[Entity], hero=(70.0, 3.05), mode: str = "ground") -> WorldState:
    ws = WorldState()
    ws.stamp.t_game_s = t
    ws.entities = ents
    ws.hero.pos = E(hero)
    ws.hero.mode = E(mode)
    ws.hero.facing = E(1)
    return ws


def _bell(iid: int, x: float, y: float, sigma: float) -> Entity:
    return Entity(id=iid, kind=Kind.ENEMY_ATTACK, type_key=E("BoneBeast DropBell M2"),
                  pos=E((x, y), sigma=sigma, conf=1.0), visible_frac=1.0)


def _drop(spec, x0: float, side: int, t_drop: float, frames: int, sigma: float, seed: int, step_phase: float = 0.0):
    """Frames (t, x, y) of a drop: the registry physics in 50 Hz steps from the drop, shown at 60 fps (each frame the
    last step's position), with Gaussian noise."""
    rng = np.random.default_rng(seed)
    out = []
    for k in range(frames):
        t = t_drop + k / 60
        n_steps = int(np.floor((t - t_drop + step_phase) / 0.02 + 1e-9))
        cx, cy, _ = simulate(spec, x0, 13.74, 0.0, -17.0, 0, None, np.array([n_steps * 0.02]), side=side)
        out.append((t, cx[0] + rng.normal(0, sigma), cy[0] + rng.normal(0, sigma)))
    return out


def test_registry_start_and_fall_time(spec):
    tr = DropBellTracks(spec)
    assert tr.ok and tr.y0 == pytest.approx(13.74) and tr.vy0 == pytest.approx(-17.0)
    assert 0.3 < tr.t_fall < 0.45


@pytest.mark.parametrize("side", [1, -1])
def test_drop_time_column_and_side_from_noisy_detections(spec, side):
    """The column within 3 sigma of the mean, the drop within 2 physics steps, the side decided after the bounce and
    never the wrong one; before the bounce both sides stay open."""
    tr = DropBellTracks(spec)
    frames = _drop(spec, 84.3, side, 20.0, 50, 0.15, seed=4 + side, step_phase=0.013)
    sided = None
    for t, x, y in frames:
        tr.update(_ws(t, [_bell(5, x, y, 0.15)]), t)
        est = tr.estimate(5)
        assert est is not None
        assert abs(est.x - 84.3) <= 3 * max(est.sx, 0.15 / np.sqrt(est.n)) + 1e-9
        assert abs(est.t_drop - 20.0) <= 0.04
        if t < est.t_contact:
            assert est.side == 0
        if est.side:
            assert est.side == side
            sided = sided or t
    assert sided is not None and sided - (20.0 + tr.t_fall) < 0.3


def test_an_attack_in_reach_or_a_path_off_the_model_withdraws_the_estimate(spec):
    tr = DropBellTracks(spec)
    frames = _drop(spec, 84.3, 1, 20.0, 12, 0.05, seed=1)
    for t, x, y in frames:
        tr.update(_ws(t, [_bell(5, x, y, 0.05)]), t)
    assert tr.estimate(5) is not None
    t = frames[-1][0] + 1 / 60
    tr.update(_ws(t, [_bell(5, frames[-1][1], frames[-1][2] - 0.6, 0.05)], hero=(83.0, 9.0), mode="attack"), t)
    assert tr.estimate(5) is None                 # touched: a tink is possible
    tr2 = DropBellTracks(spec)
    for t, x, y in frames:
        tr2.update(_ws(t, [_bell(6, x, y, 0.05)]), t)
    for k in (1, 2):                              # two detections 2 u off the column (pushed aside)
        t = frames[-1][0] + k / 60
        tr2.update(_ws(t, [_bell(6, 86.3, frames[-1][2] - k * 0.6, 0.05)]), t)
    assert tr2.estimate(6) is None


def test_forecaster_uses_the_track_in_the_vision_view(spec):
    """The vision view's Forecaster puts a seen drop bell on its path (both sides before the bounce) instead of its self
    template, and the support follows the fall."""
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster
    from ssbot.core.worldstate import VISION_EQUIVALENT
    model = BossModel.load("BellBeast")
    fc = Forecaster(model, VISION_EQUIVALENT, templates={})
    fc.reset()
    frames = _drop(spec, 84.3, 1, 20.0, 6, 0.1, seed=2)
    for t, x, y in frames:
        fc.update(_ws(t, [_bell(9, x, y, 0.1)]))
    f = fc.forecast(1.0)
    assert len(f.det) == 1 and f.det[0].sides == (1, -1) and f.det[0].t0 == pytest.approx(5 / 60, abs=0.03)
    tc = 20.0 + fc.drop_tracks.t_fall - frames[-1][0]
    xs = np.array([[84.3], [84.3 + 3.0], [84.3 - 3.0], [70.0]])
    ys = np.full((4, 1), 3.05)
    occ = f.occupied(xs, ys, np.array([tc]))[:, 0]
    assert occ[0] and not occ[3]                  # under the bell at its contact; nowhere near: free
