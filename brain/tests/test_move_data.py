"""Task 1v1 SG1: the move-data format (ssbot.combat.move_data) against the sources it replaces."""
import numpy as np
import pytest

from ssbot.combat import move_data as md
from ssbot.combat import pogo_slam as ps

pytestmark = pytest.mark.skipif(not md.SLAM_TEMPLATE.exists(), reason="no slam template")


def _hammer(tl: md.MoveTimeline) -> np.ndarray:
    h = tl.boxes["Slam Collider 1"].copy()
    sel = np.isfinite(tl.boxes["Slam Collider 2"][:, 0])
    h[sel] = tl.boxes["Slam Collider 2"][sel]
    return h


def test_cl_slam_equals_slamtimeline_in_every_variant():
    spec = md.load_cl_slam()
    ref = [ps.SlamTimeline.load()] + ps.SlamTimeline.variants()
    mine = spec.variants("t1")
    assert len(mine) == len(ref) == 9
    for r, m in zip(ref, mine):
        assert r.state == m.state
        np.testing.assert_array_equal(r.root, m.boxes["root"])
        np.testing.assert_array_equal(r.hammer, _hammer(m))
        np.testing.assert_array_equal(r.disp, m.disp)
        for k in (0, 30, 50, 55, 58, 70, 100):              # world boxes with the lunge
            np.testing.assert_array_equal(r.world(np.array([k]))[0], m.box("root", k))
            np.testing.assert_array_equal(r.world(np.array([k]), "hammer")[0], _hammer(m)[k] + [m.disp[k], m.disp[k], 0, 0])


def test_roles_damage_and_targets():
    tl = md.load_cl_slam().timeline()
    assert len(tl.targets(55)) == 1 and len(tl.damage(55)) == 2          # root + Slam Collider 1
    assert len(tl.damage(10)) == 1                                         # root only in the antic
    np.testing.assert_array_equal(tl.targets(60)[0], tl.box("root", 60))
    assert tl.end_k == 77 and tl.entry["Slam 2"] == 57


def test_observed_variants_cover_every_seen_duration():
    spec = md.load_cl_slam()
    obs = spec.variants("observed")
    assert len(obs) == 3 * 2 * 1 * 2 * 3 * 2
    assert sum(t.weight for t in obs) == pytest.approx(1.0)
    assert {t.entry["Slam 0"] for t in obs} == {47, 48, 49}
    assert spec.states[0].share(47) > 0.05                                 # antic 47: not in T1's nine


def test_round_trip(tmp_path):
    spec = md.load_cl_slam()
    back = md.MoveSpec.load(spec.save(tmp_path / "cl.json"))
    for a, b in zip(spec.variants("t1"), back.variants("t1")):
        for n in a.boxes:
            np.testing.assert_array_equal(a.boxes[n], b.boxes[n])
        np.testing.assert_array_equal(a.disp, b.disp)


@pytest.mark.skipif(not (md.FORUM / "ChoirClapper_hitboxes.npz").exists(), reason="no hitbox tables")
def test_raster_move_cc_evade():
    spec = md.load_raster_move("ChoirClapper", "CC_EVADE")
    tl = spec.timeline()
    assert [s.name for s in spec.states] == ["Evade Scuttle"] and tl.end_k == 21
    assert all(md.TARGET not in t.roles for t in spec.tracks)              # a raster gives no strike target
    d0, d20 = tl.damage(0), tl.damage(20)
    assert len(d0) and len(d20)
    assert d20[:, 0].min() < d0[:, 0].min() - 4.0                          # the backstep: about 5 u away from the facing
