"""The down-slash predictor (combat.pogo_model) and the overlay's eye check (tools.zone_overlay pogo layer)."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import pogo_model as pm
from ssbot.knowledge import kinematics as kin
from ssbot.train.forum_planner_policy import CREST_PARAMS

FLOOR = 3.0


@pytest.fixture(scope="module")
def params():
    return kin.HeroParams.load(CREST_PARAMS["Wanderer"])


@pytest.fixture(scope="module")
def arena():
    return kin.Terrain2D.from_boxes([(10.0, 0.0, 53.0, FLOOR), (10.0, 0.0, 14.01, 30.0), (48.99, 0.0, 53.0, 30.0)])


def _box(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float)


def test_slash_polygon_mirrors_with_the_facing_and_the_hull_holds_both():
    a = pm.slash_poly(1, alt=False)
    b = pm.slash_poly(-1, alt=False)
    assert np.allclose(a[:, 0], -b[:, 0]) and np.allclose(a[:, 1], b[:, 1])
    h = pm.slash_poly(1)
    for p in np.concatenate([pm.DOWN, pm.DOWN_ALT]):
        assert h[:, 0].min() - 1e-6 <= p[0] <= h[:, 0].max() + 1e-6
    assert h[:, 1].min() == pytest.approx(-2.676)


def test_meets_separating_axis():
    assert pm.meets(_box(0, 0, 1, 1), _box(0.5, 0.5, 2, 2))
    assert not pm.meets(_box(0, 0, 1, 1), _box(1.0, 0, 2, 1))      # touching edges only
    assert not pm.meets(_box(0, 0, 1, 1), _box(3, 3, 4, 4))


def test_collider_kinds():
    assert pm.collider_kind(11, 4, True) == pm.K_HURT
    assert pm.collider_kind(11, None, False) is None
    assert pm.collider_kind(22, 5, True) == pm.K_TINK       # clashable attack: a tink
    assert pm.collider_kind(22, 4, True) is None            # the Clapper's hammer: passes
    assert pm.collider_kind(13, None, True) is None


def _falling(params, x=30.0, y=10.0):
    return kin.initial_state(params, x, y, vy=-2.0, ground=False)


def test_a_hurtbox_below_bounces_the_hero_and_nothing_below_is_a_miss(params, arena):
    model = pm.PogoModel(params, arena)
    start = _falling(params)
    masks = np.zeros(36, np.int64)
    masks[0] = kin.B_DOWN | kin.B_ATTACK
    body = _box(29.0, 4.0, 31.0, 8.5)
    br = model.branches(start, masks, 1, lambda j: [(body, pm.K_HURT)], 1)
    assert 1 + pm.ACTIVE[0] <= br.contact_j <= 1 + pm.ACTIVE[1] and br.kind == pm.K_HURT
    assert br.hit is not None
    j = br.contact_j
    assert br.hit.pos[0, j + 8, 1] > br.miss.pos[0, j + 8, 1] + 0.5         # the bounce rises, the miss falls
    assert (br.hit.flags[0, j + 1:j + 6] & kin.F_INVULN).any()            # the pogo i-frames
    far = model.branches(start, masks, 1, lambda j: [(_box(40, 4, 42, 8), pm.K_HURT)], 1)
    assert far.contact_j == -1 and far.hit is None
    passing = model.branches(start, masks, 1, lambda j: [(body, None)], 1)
    assert passing.contact_j == -1                                       # a hammer (kind None) does not bounce


def test_overlay_pogo_layer_predicts_and_draws(params, arena):
    from ssbot.tools import zone_overlay as zo
    start = _falling(params)
    eng = NS(pol=NS(trk=NS(state=lambda: start), params=params, terrain=arena))
    s = {"hero": {"facing": 1, "pos": [30.0, 10.0]}, "input": {"mask": 0},
         "ents": [{"iid": 1, "type_key": "Song Heavy Sentry", "src": 3, "colliders": [
             {"kind": "box", "enabled": True, "layer": 11, "damage": {"parry": 4},
              "verts_world": _box(29.0, 4.0, 31.0, 8.5).ravel().tolist()}]}]}
    pg = zo.pogo_predict(eng, s)
    assert pg is not None and pg["j"] > 0 and pg["hit"] is not None and pg["slash"].shape == (14, 2) or \
        pg["slash"].shape[1] == 2
    img = np.zeros((1080, 1920, 4), np.uint8)
    Hw = np.array([[40.0, 0, -400.0], [0, -40.0, 900.0], [0, 0, 1.0]])
    zo.draw_pogo(img, {"now": pg, "frozen": None, "real": []}, Hw, 1080)
    assert img[..., 3].any()
    img2 = np.zeros_like(img)
    zo.draw_pogo(img2, {"now": pg, "frozen": pg, "real": [[30.0, 10.0], [30.0, 9.0], [30.0, 9.5]]}, Hw, 1080)
    assert img2[..., 3].any()


def test_overlay_freezes_the_prediction_at_a_press_and_collects_the_real_path(params, arena):
    from ssbot.tools import zone_overlay as zo
    start = _falling(params)
    ov = zo.LiveOverlay.__new__(zo.LiveOverlay)            # no window / thread: the per-frame logic only
    ov.pogo, ov.pogo_now, ov.pogo_frozen, ov.pogo_real, ov.pogo_t, ov.pogo_clip = True, None, None, [], 0.0, None
    ov.speed = 0.5
    ov.stats = {"errors": []}
    ov.eng = NS(pol=NS(trk=NS(state=lambda: start), params=params, terrain=arena))

    def frame(clip, y):
        return {"hero": {"facing": 1, "pos": [30.0, y], "anim": {"clip": clip}}, "input": {"mask": 0}, "ents": []}
    ov._pogo_frame(frame("Airborne", 10.0))
    assert ov.pogo_now is not None and ov.pogo_frozen is None
    pred = ov.pogo_now
    ov._pogo_frame(frame("DownSlash", 9.9))
    assert ov.pogo_frozen is pred and len(ov.pogo_real) == 2 and ov.stats.get("pogo_presses") == 1
    ov._pogo_frame(frame("DownSlash", 9.8))
    assert len(ov.pogo_real) == 3 and not ov.stats["errors"]
