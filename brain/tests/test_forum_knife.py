"""Fixed proposals and conservative, shared escape checks."""
from types import SimpleNamespace

import numpy as np
import pytest

from ssbot.combat import forum_knife as fk
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.knowledge import kinematics as km
from ssbot.map2 import reflex as rx


def test_contingent_macro_is_only_a_new_fixed_proposal():
    macro = rx.Macro("cl", hop=3, cont=(("early", 42, -1), ("late", 46, 1)))
    row, p, k, fixed = fk.fixed_keys(macro, 1)
    assert macro.cont and not fixed.cont  # original evidence remains unchanged
    assert p == 3 and k == 46 and fixed.dd == 0
    assert np.flatnonzero(row & km.B_ATTACK).tolist() == [45, 46]
    assert np.flatnonzero(row & (1 << 4)).tolist() == [2, 3]
    assert np.array_equal(hold_filter_jit(row[None], km.HoldState.idle())[0][0], row)


def test_common_drift_is_kept_and_throw_direction_is_explicit():
    row, _, k, fixed = fk.fixed_keys(rx.Macro("cl", cont=(("early", 42, -1), ("late", 46, -1))), -1)
    assert k == 46 and fixed.dd == -1
    assert row[0] & km.B_LEFT and not row[0] & km.B_RIGHT


def test_unhooked_macro_cannot_claim_a_down_contact():
    with pytest.raises(ValueError, match="no down strike"):
        fk.fixed_keys(rx.Macro("cl"), 1)


def test_feature_requires_the_agreed_configuration():
    env = dict(SSBOT_FORUM_WINDOWS="1", SSBOT_FORUM_WINDOWS_CORE="2", SSBOT_FORUM_WINDOWS_PRESS="0",
               SSBOT_FORUM_SLAM_PLAY="0", SSBOT_FORUM_CLAWSTRIKE="0", SSBOT_FORUM_SLAM_PLAY_PREFS="1",
               SSBOT_FORUM_TV="0", SSBOT_FORUM_HERO2="1", SSBOT_FORUM_V2="1")
    fk.validate_environment(env)
    for key, value in (("SSBOT_FORUM_WINDOWS_CORE", "0"), ("SSBOT_FORUM_WINDOWS_PRESS", "1"),
                       ("SSBOT_FORUM_SLAM_PLAY", "1"), ("SSBOT_FORUM_TV", "1")):
        with pytest.raises(ValueError, match="incompatible"):
            fk.validate_environment({**env, key: value})


def test_envelope_keeps_an_unfavorable_hook_outcome():
    def lane(box, flags):
        return SimpleNamespace(bound=np.array([[box]], float), flags_all=np.array([[flags]], np.int64))
    bound, flags = fk.envelope([lane([0, 1, 2, 3], km.F_INVULN), lane([-4, 2, 1, 6], 0)])
    assert bound.tolist() == [[-4., 1., 2., 6.]]
    assert flags.tolist() == [0]


def test_body_shape_changes_without_changing_old_template_translation():
    class Knowledge:
        def box(self, state, frame):
            return np.array([-1., 1., -4., -1. if state == "Slam Antic" else 1.])
        def durations(self, state):
            return (2, 2, 2)
    obs = SimpleNamespace(st="Slam Antic", j=0, x=20., y=7., face=-1)
    old = np.tile([19., 3., 21., 6.], (20, 1))
    old[1:, [0, 2]] += 2.
    body = fk.slam_body_paths(obs, [old], Knowledge())[0]
    assert body[0].tolist() == [19., 3., 21., 6.]
    assert body[2].tolist() == [21., 3., 23., 8.]
    assert np.isnan(body[-1]).all()  # no fictitious stationary body after the Slam


def test_different_escapes_for_different_outcomes_are_not_a_common_escape(monkeypatch):
    # Model two valid control outcomes. Left is safe only in the first;
    # right is safe only in the second. A favorable outcome must not win.
    def rollout(state, masks, *args, **kwargs):
        direction = 1 if masks[0, -1] & km.B_RIGHT else -1
        box = np.tile([state[km.PX], direction, state[km.PX] + .5, direction + .5], (1, masks.shape[1] + 1, 1))
        return SimpleNamespace(bound=box, flags_all=np.zeros(box.shape[:2], np.int64))
    monkeypatch.setattr(km, "rollout", rollout)
    params = km.HeroParams()
    starts = {q: km.initial_state(params, q, 8, ground=False) for q in range(2)}
    path = SimpleNamespace(control_frames=np.array([2, 2]), control_states=starts)
    planner = SimpleNamespace(params=params, terrain=None, cfg=SimpleNamespace(threads=1),
                              _esc_cmds=lambda length: np.array([[km.B_LEFT] * length, [km.B_RIGHT] * length]))
    def contacts(f, bound, tk, skip, query):
        x, direction = bound[0, 0, :2]
        fail = (x < .5 and direction > 0) or (x > .5 and direction < 0)
        return np.full(bound.shape[:2], fail, bool)
    planner._contacts_fn = contacts
    forecast = SimpleNamespace(rs=SimpleNamespace(occupied_esc=lambda *a: None))
    assert fk.common_escape(planner, forecast, [path], np.zeros(40, np.int64),
                            np.zeros(2, np.int64), km.HoldState.idle(), 38) is None


def test_clear_fixed_row_is_appended_with_its_real_hook_envelope():
    """Exercise the accepted plumbing in an empty synthetic danger field.

    The contact oracle is controlled; this tests row/envelope/escape ownership,
    not that a real Clapper is hittable or that the treatment is effective.
    """
    from ssbot.map2.envelope import load_params
    params = load_params(hero2=True)
    obs = fk.cm.Obs(7, "Slam Antic", 2 / 60, 5., 7., 0., 0., -1, 100, None, j=2)
    class Knowledge:
        def box(self, state, frame): return np.array([-1.5, 1.5, -4., 1.])
        def durations(self, state): return (48, 48, 48)
    win = SimpleNamespace(knife_scope=True, harpoon=False, lat_s=0, fo=100, last_freeze=None,
                           obs=lambda: [obs], knife_knowledge=Knowledge(),
                           _has_full=lambda key: np.ones(len(key), bool),
                           _margin=lambda key: np.ones(len(key), bool),
                           _entry=lambda key: SimpleNamespace(macro=rx.Macro("cl", k=45)))
    target = SimpleNamespace(iid=7, hazard=False)
    def targets(ws, f, tk, prefs):
        return np.tile([3.5, 3., 6.5, 8.], (1, len(tk), 1)), np.ones((1, len(tk)), bool), None, [target]
    def contacts(ro, masks, *args):
        n = len(ro.hooks)
        return np.full(n, 46), np.full(n, 49), np.zeros(n, np.int64), np.ones(n, bool)
    planner = SimpleNamespace(params=params, terrain=None, cfg=SimpleNamespace(threads=1),
                               _forum_targets=targets, _ds_move_paths=lambda tr, keep, boxes: {0: [boxes[0]]},
                               _ds_hits=contacts, _contacts=lambda f, b, tk, sk: np.zeros(b.shape[:2], bool),
                               _contacts_fn=lambda f, b, tk, sk, fn: np.zeros(b.shape[:2], bool),
                               _esc_cmds=lambda length: np.zeros((1, length), np.int64))
    forecast = SimpleNamespace(targets=lambda tk: [target], rs=SimpleNamespace(trk=None, occupied_esc=lambda *a: None))
    state = km.initial_state(params, 0., 6., ground=False)
    result = fk.append_rows(planner, win, None, forecast, state, km.HoldState.idle(),
                             np.zeros(1, np.int64), SimpleNamespace(), 36, "air", None)
    assert result is not None and len(result.cmd) == 1
    assert not result.cert[0] and result.extra[0] == 1
    custom = result.custom[0]
    assert custom["bound"].shape == (38, 4) and custom["escape"] == 0
    assert custom["final"].shape == (km.K,)
    assert np.array_equal(custom["latched"], hold_filter_jit(
        np.r_[0, result.cmd[0]][None], km.HoldState.idle())[0][0])



def test_safety_support_extends_without_mutating_the_planner_forecast(monkeypatch):
    from ssbot.combat import forum_v2 as v2
    cv = v2.Canvas(cell=.25, box=(0, 0, 4, 4))
    rs = v2.RangeSupport(cv, (0, 2), k_shift=-1)
    rs.trk, rs.margin_mode = object(), "zero"
    rs.stack[:, 1, 1] = True
    rs.raw[0] = [(7, np.ones((1, 1), bool), 1, 1, 0., None)]
    rs.bombs = np.array([[7., 1., 1., .5, 0., 10.]])
    original = rs.stack.copy()
    def build(cls, trk, *, samples, k_shift, **kwargs):
        assert trk is rs.trk and samples == (7,) and k_shift == -1
        extra = v2.RangeSupport(cv, samples, k_shift)
        extra.stack[:, 2, 2] = True
        extra.stack_esc = np.zeros_like(extra.stack)
        return extra
    monkeypatch.setattr(v2.RangeSupport, "build", classmethod(build))
    f = v2.V2Forecast(SimpleNamespace(fc=None), rs)
    out = fk.safety_forecast(f, 6)
    assert out.rs is not rs and out.rs.samples == (0, 2, 7)
    assert max(out.rs.samples) + out.rs.k_shift == 6
    assert np.array_equal(rs.stack, original) and rs.samples == (0, 2)
    assert np.array_equal(out.rs.stack[:2], original)
    assert out.rs.stack[2, 2, 2]
    assert np.array_equal(out.rs.stack_esc[:2], original)
    assert not out.rs.stack_esc[2].any()
    assert out.rs.bombs is rs.bombs and out.rs.raw[0] is rs.raw[0]
    assert fk.safety_forecast(out, 6) is out


def test_escape_support_horizon_uses_the_forecast_origin_shift():
    planner = SimpleNamespace()
    forecast = SimpleNamespace(rs=SimpleNamespace(samples=(0, 62), k_shift=-2))
    with pytest.raises(ValueError, match="support horizon"):
        fk.common_escape(planner, forecast, [], np.zeros(38, np.int64),
                         np.zeros(2, np.int64), km.HoldState.idle(), 38)
