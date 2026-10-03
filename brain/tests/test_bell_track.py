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


# ---- attack bells ------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def atk_spec():
    from ssbot.combat.bell_track import ATK_BELL
    return next(s for s in load_registry() if s.prefix == ATK_BELL)


def _atk(iid: int, x: float, y: float, sigma: float) -> Entity:
    return Entity(id=iid, kind=Kind.ENEMY_ATTACK, type_key=E("BoneBeast AtkBell R"),
                  pos=E((x, y), sigma=sigma, conf=1.0), visible_frac=1.0)


def _launch(spec, x0: float, side: int, t_launch: float, frames: int, sigma: float, seed: int,
            step_phase: float = 0.0, first: int = 0):
    """Frames (t, x, y) of an attack bell launched at t_launch: the registry physics in 50 Hz steps, shown at 60 fps,
    with Gaussian noise; from frame `first` on (a detector may miss the first frames under the floor)."""
    rng = np.random.default_rng(seed)
    out = []
    for k in range(first, frames):
        t = t_launch + k / 60
        n_steps = int(np.floor((t - t_launch + step_phase) / 0.02 + 1e-9))
        cx, cy, _ = simulate(spec, x0, 0.954, side * 1.0, 38.0, 0, None, np.array([n_steps * 0.02]))
        out.append((t, cx[0] + rng.normal(0, sigma), cy[0] + rng.normal(0, sigma)))
    return out


def test_atk_registry_start_and_first_bounce(atk_spec):
    from ssbot.combat.bell_track import AtkBellTracks
    tr = AtkBellTracks(atk_spec)
    assert tr.ok and tr.y0 == pytest.approx(0.954) and tr.vy0 == pytest.approx(38.0) and tr.vx_mag == 1.0
    assert 1.0 < tr.t_bounce < 1.3


@pytest.mark.parametrize("first", [0, 8, 45])
def test_atk_pair_launch_time_x_and_sides(atk_spec, first):
    """A burst's two bells from noisy detections (from the launch, from under the floor's edge, or first seen
    falling): launch within 2 physics steps, the launch x within 3 sigma, the sides from the pair (left goes left),
    the end at the End Timer; the path stays within the skin of the truth."""
    from ssbot.combat.bell_track import SKIN_Z, AtkBellTracks
    tr = AtkBellTracks(atk_spec)
    a = _launch(atk_spec, 84.0, -1, 30.0, 150, 0.15, seed=1, step_phase=0.007, first=first)
    b = _launch(atk_spec, 88.0, 1, 30.0, 150, 0.15, seed=2, step_phase=0.007, first=first)
    for (t, xa, ya), (_, xb, yb) in zip(a, b):
        tr.update(_ws(t, [_atk(1, xa, ya, 0.15), _atk(2, xb, yb, 0.15)]), t)
    ests = {e.iid: e for e in tr.estimates()}
    assert set(ests) == {1, 2}
    for iid, x0, side in ((1, 84.0, -1), (2, 88.0, 1)):
        e = ests[iid]
        assert e.pair and e.side == side
        assert abs(e.t_launch - 30.0) <= 0.04
        assert abs(tr.x0(e, side) - x0) <= 3 * e.sx + 0.05
        assert e.t_end == pytest.approx(30.0 + tr.t_bounce + 2.0 + 0.04, abs=0.05)
        t = a[-1][0]
        cx, cy, _ = simulate(atk_spec, *tr.path_args(e, side), 0, None, np.array([t - e.t_launch]))
        tx, ty, _ = simulate(atk_spec, x0, 0.954, side * 1.0, 38.0, 0, None, np.array([t - 30.0]))
        assert np.hypot(cx[0] - tx[0], cy[0] - ty[0]) <= 0.1 + SKIN_Z * e.sx + 38 * 0.02


def test_atk_side_from_the_burst_anchor_and_open_without(atk_spec):
    from ssbot.combat.bell_track import AtkBellTracks
    frames = _launch(atk_spec, 90.0, 1, 5.0, 6, 0.15, seed=3)
    tr = AtkBellTracks(atk_spec)
    for t, x, y in frames:
        tr.update(_ws(t, [_atk(4, x, y, 0.15)]), t, anchor_x=88.0)
    assert tr.estimates()[0].side == 1
    tr = AtkBellTracks(atk_spec)
    for t, x, y in frames:
        tr.update(_ws(t, [_atk(4, x, y, 0.15)]), t)
    assert tr.estimates()[0].side == 0          # alone, 0.1 s of a 1 u/s drift: both sides


def test_atk_track_off_the_model_is_withdrawn(atk_spec):
    from ssbot.combat.bell_track import AtkBellTracks
    tr = AtkBellTracks(atk_spec)
    frames = _launch(atk_spec, 84.0, -1, 5.0, 20, 0.05, seed=4)
    for t, x, y in frames:
        tr.update(_ws(t, [_atk(4, x, y, 0.05)]), t, anchor_x=86.0)
    assert tr.estimates()
    for k in (1, 2):                            # two detections 2 u off the path
        t = frames[-1][0] + k / 60
        tr.update(_ws(t, [_atk(4, frames[-1][1] + 2.0, frames[-1][2], 0.05)]), t, anchor_x=86.0)
    assert not tr.estimates()


def test_forecaster_drops_a_bursts_bell_unions_once_both_bells_are_tracked(atk_spec):
    """Vision view: a burst (anchor 86) whose two attack bells are both on exact paths places no attack-bell union for
    its Burst Recovery and tail, and puts the bells on their paths instead; with one bell tracked the unions stay."""
    from ssbot.combat.boss_model import Anchor, BossModel
    from ssbot.combat.forecast import Ctx, Forecaster, Root, load_planner_templates
    from ssbot.core.worldstate import VISION_EQUIVALENT
    model = BossModel.load("BellBeast")
    tpl = {k: v for k, v in load_planner_templates(model, 0.0).items() if "/BB_BURST/" in k}
    an = Anchor(86.0, 5.49, 1)
    a = _launch(atk_spec, 84.0, -1, 30.0, 40, 0.15, seed=5)
    b = _launch(atk_spec, 88.0, 1, 30.0, 40, 0.15, seed=6)
    for both in (True, False):
        fc = Forecaster(model, VISION_EQUIVALENT, templates=tpl)
        fc.reset()
        for (t, xa, ya), (_, xb, yb) in zip(a, b):
            fc.update(_ws(t, [_atk(1, xa, ya, 0.15)] + ([_atk(2, xb, yb, 0.15)] if both else [])))
        t = a[-1][0]
        e_br = 30.0 + 0.91 - t                   # Burst Recovery's entry from the origin
        fc.tracker.roots = lambda origin: ([Root("Burst Out", 30.0 - t, 30.0 - t, Ctx("BB_BURST", None, an, "P1",
                                                                                        False), current=True)], True)
        f = fc.forecast(2.0)
        keys = {p.key for p in f.placements}
        assert ("support/BB_BURST/Burst Recovery/anchor" in keys) != both
        assert ("support/BB_BURST/_tail/anchor" in keys) != both
        assert "support/BB_BURST/Burst Out/anchor" in keys            # the eruption's body stays
        assert len(f.det) == 2 if both else len(f.det) in (1, 2)    # one bell: one side or both
        if both:
            # under the left bell at its first floor contact, nowhere near it
            tc = 30.0 + fc.atk_tracks.t_bounce - t
            cx, _, _ = simulate(atk_spec, 84.0, 0.954, -1.0, 38.0, 0, None, np.array([fc.atk_tracks.t_bounce]))
            occ = f.occupied(np.array([[cx[0]], [100.0]]), np.full((2, 1), 3.05), np.array([tc]))[:, 0]
            assert occ[0] and not occ[1]
            assert e_br > 0


def test_vision_view_bell_targets_are_the_tracked_attack_bells(atk_spec, monkeypatch):
    """SSBOT_VE_TARGETS: the tracked attack bells as pogo targets (their certain circle smaller than the oracle's, no
    redirect); drop bells only with SSBOT_VE_DROP_TARGETS (an attack near one withdraws its track)."""
    from ssbot.combat import forecast as fmod
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.pogo_targets import CERT_MARGIN_U
    from ssbot.core.worldstate import VISION_EQUIVALENT
    monkeypatch.setattr(fmod, "VE_TARGETS", True)
    fc = fmod.Forecaster(BossModel.load("BellBeast"), VISION_EQUIVALENT, templates={})
    fc.reset()
    a = _launch(atk_spec, 84.0, -1, 30.0, 40, 0.15, seed=5)
    b = _launch(atk_spec, 88.0, 1, 30.0, 40, 0.15, seed=6)
    for (t, xa, ya), (_, xb, yb) in zip(a, b):
        fc.update(_ws(t, [_atk(1, xa, ya, 0.15), _atk(2, xb, yb, 0.15)]))
    f = fc.forecast(1.0)
    tk = np.arange(30) / 60
    paths = f.target_paths(tk)
    assert len(paths) == 2 and all(p.cert_margin > CERT_MARGIN_U and not p.redirect for p in paths)
    assert all(p.ok.any() for p in paths)
    monkeypatch.setattr(fmod, "VE_TARGETS", False)
    assert f.target_paths(tk) == []
