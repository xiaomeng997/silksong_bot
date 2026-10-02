"""Knockback envelope (ssbot.knowledge.knockback): a conservative bound, so the tests try to break containment with
the hero model itself (dense physics phase, frame-time jitter, hitches, both sides, the Weighted Anklet), check the
properties that make delays safe (union[k] only grows), terrain clipping and the sloped-ceiling rule, the batched
form against single queries, and the report of escaping hits."""
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.knowledge import knockback as kb
from ssbot.knowledge.kinematics import HeroParams, Terrain2D

REST = 2.0 + 0.015 + 1.5527
FIXTURE = Path(__file__).parent / "fixtures" / "kin_bellbeast_trial.npz"


@pytest.fixture(scope="module")
def p() -> HeroParams:
    return HeroParams.load()


def floor(x0=0.0, x1=300.0, top=2.0) -> tuple:
    return (x0, top - 2.0, x1, top)


def _timings(p: HeroParams, n: int, T: int, rng) -> np.ndarray:
    """[n, T] unscaled frame times inside the jitter model: constant at its ends and mean, random per frame, and with
    one or two hitches anywhere (the knockback bound's assumptions)."""
    u = np.empty((n, T))
    kind = np.arange(n) % 6
    u[kind == 0] = p.frame_time_lo
    u[kind == 1] = p.frame_time
    u[kind == 2] = p.frame_time_max
    for k in (3, 4, 5):
        sel = np.flatnonzero(kind == k)
        u[sel] = rng.uniform(p.frame_time_lo, p.frame_time_max, (len(sel), T))
        for h in range(k - 3):
            u[sel, rng.integers(1, T, len(sel))] = rng.uniform(p.frame_time_max, p.hitch_max, len(sel))
    return u


@pytest.mark.parametrize("side,weighted", [("left", False), ("right", False), ("left", True)])
def test_every_modelled_timing_stays_inside_the_envelope(p, side, weighted):
    """1200 rollouts of the real hit (EV_HURT in frame 1) per case: dense phase, jitter and hitches; with and without
    inputs after control returns. Every frame's box lies in union[k] and every no-input box in the swept hull."""
    q = p.with_weighted(True) if weighted else p
    rng = np.random.default_rng(11)
    n, T = 1200, kb.FRAMES
    terrain = Terrain2D.from_boxes([floor()])
    S = np.repeat(km.initial_state(q, 150.0, REST)[:, None], n, axis=1)
    S[km.ALPHA] = rng.random(n)
    S[km.GROUND] = (np.arange(n) % 2).astype(float)          # half start in the air (no floor below them)
    S[km.PY] = S[km.QY] = S[km.SY] = np.where(S[km.GROUND] > 0, REST, REST + 2.0)
    masks = np.where(rng.random((n, T)) < 0.5, rng.choice([0, km.B_LEFT, km.B_RIGHT | km.B_JUMP, km.B_ATTACK],
                                                          (n, T)), 0)
    masks[: n // 2] = 0
    ev = np.zeros((n, T), dtype=np.int64)
    ev[:, 0] = km.EV_HURT_L if side == "left" else km.EV_HURT_R
    r = km.rollout(S, masks, q, terrain, events=ev, udt=_timings(q, n, T, rng))
    swept, frames, _ = kb.knockback_boxes(r.box[:, 1], side, q, terrain, per_frame=True)
    boxes = r.box[:, 1:T + 1]                                   # frame k after the hit frame
    F = min(T, frames.shape[1])
    u = frames[:, :F]
    exc = np.maximum.reduce([u[..., 0] - boxes[:, :F, 0], u[..., 1] - boxes[:, :F, 1], boxes[:, :F, 2] - u[..., 2],
                             boxes[:, :F, 3] - u[..., 3]])
    assert exc.max() <= 1e-9
    noinp = (r.flags[:, 1:T + 1] & km.F_NO_INPUT) != 0
    sw = np.broadcast_to(swept[:, None], boxes.shape)
    out = np.maximum.reduce([sw[..., 0] - boxes[..., 0], sw[..., 1] - boxes[..., 1], boxes[..., 2] - sw[..., 2],
                             boxes[..., 3] - sw[..., 3]])
    assert out[noinp].max() <= 1e-9
    reach = (swept[:, 2] - r.box[:, 1, 2]) if side == "left" else (r.box[:, 1, 0] - swept[:, 0])
    step = q.hurt_velocity * q.fdt
    assert np.allclose(reach, kb.recoil_timing(q).n_max * step + kb.CONTACT_SLOP)
    ctl = np.argmax(~noinp, axis=1)
    assert ctl.min() >= kb.recoil_timing(q).ctl_min


def test_union_only_grows_so_a_delayed_recoil_stays_inside(p):
    """A concurrent freeze (BindBreak, BossDeathSlow) holds the hero somewhere on the path for any number of frames:
    the box of frame k is then one of frame j <= k, inside union[j], which union[k] contains."""
    for side in ("left", "right", "top"):
        env = kb.knockback_envelope(np.array([10.0, 2.015, 10.5, 4.094]), side, p, Terrain2D.from_boxes([floor()]))
        u = env.union
        assert (np.diff(u[:, :2], axis=0) <= 1e-12).all() and (np.diff(u[:, 2:], axis=0) >= -1e-12).all()
        assert env.contains(np.array([10.0, 2.015, 10.5, 4.094]), 0)
    top = kb.knockback_envelope(np.array([10.0, 2.015, 10.5, 4.094]), "top", p)
    assert top.swept == pytest.approx([10.0 - kb.CONTACT_SLOP, 2.015 - kb.CONTACT_SLOP, 10.5 + kb.CONTACT_SLOP,
                                       4.094 + kb.CONTACT_SLOP])           # StartRecoil: no vector for top / bottom


def test_walls_clip_and_slopes_widen(p):
    hit = np.array([10.0, 2.015, 10.5, 4.094])
    free = kb.knockback_envelope(hit, "left", p, Terrain2D.from_boxes([floor()]))
    walled = kb.knockback_envelope(hit, "left", p, Terrain2D.from_boxes([floor(), (11.5, 0.0, 13.0, 20.0)]))
    assert walled.swept[2] <= 11.5 - p.skin + kb.CONTACT_SLOP + 1e-9 < free.swept[2]
    assert walled.flags & kb.KF_TERRAIN and not walled.flags & kb.KF_SLOPE
    # a ceiling sloping down to the right, as Bone_05's Roof Collider: Box2D slides the box along it, downwards
    # (live i2_002 f 693717: v = (12.98, -2.60) under a 0.2 slope), out of the axis-aligned path's hull
    air = np.array([10.0, 5.0, 10.5, 7.079])
    base = Terrain2D.from_boxes([floor()])
    axis = kb.knockback_envelope(air, "left", p, base)
    d = np.array([p.hurt_velocity, p.hurt_velocity * p.hurt_vy_ratio]) * p.fdt
    n = kb.recoil_timing(p).n_max
    lowest = np.inf
    for drop in (0.5, 1.5, 3.2, 6.0, -1.0):                   # ceilings falling (or rising) to the right
        a, b = (8.0, 8.2), (16.0, 8.2 - drop)
        roof = Terrain2D.from_outlines([np.array([a, b, (16.0, 12.0), (8.0, 12.0)])], [True])
        terrain = Terrain2D(np.concatenate([base.hseg, roof.hseg]), np.concatenate([base.vseg, roof.vseg]),
                            roof.slopes)
        env = kb.knockback_envelope(air, "left", p, terrain)
        assert env.flags & kb.KF_SLOPE
        slope = (b[1] - a[1]) / (b[0] - a[0])
        t = np.array([1.0, slope]) / np.hypot(1.0, slope)
        box = air.copy()
        for _ in range(n):
            nxt = box + np.r_[d, d]
            if nxt[3] > a[1] + (nxt[2] - a[0]) * slope - p.skin:      # slide: keep the tangential part of the step
                nxt = box + np.r_[t * max(d @ t, 0.0), t * max(d @ t, 0.0)]
            box = nxt
            s_ = env.swept
            assert s_[0] <= box[0] and s_[1] <= box[1] and box[2] <= s_[2] and box[3] <= s_[3]
        lowest = min(lowest, box[1])
        disk = air + np.r_[n * d / 2 - n * np.hypot(*d) / 2, n * d / 2 + n * np.hypot(*d) / 2] + \
            np.r_[-1, -1, 1, 1] * kb.CONTACT_SLOP
        assert (env.swept[:2] >= disk[:2] - 1e-9).all() and (env.swept[2:] <= disk[2:] + 1e-9).all()
    assert lowest < axis.swept[1] - 0.5                            # outside what the axis-aligned rule allows


def test_round_terrain_counts_as_a_slope_for_the_bound(p):
    """A circle or capsule (or an unknown shape kind) deflects a push like a slope: Terrain2D keeps its AABB sides as
    slopes, so the bound switches to the contact-projection disk near it (and ignores it far away)."""
    def shape(kind, pts, r=0.0):
        return {"k": kind, "v": np.asarray(pts, dtype=np.float32).tobytes(), "r": r}

    def msg(*shapes):
        return {"seq": 1, "scene_raw": "R", "scene": "R", "reason": "enter", "frame": 1, "hazards": [],
                "solids": [{"id": 1, "go": "Floor", "layer": 8, "on": True, "body": 0, "flags": 0,
                            "shapes": [shape("box", [[0, 0], [300, 0], [300, 2], [0, 2]])]},
                           {"id": 2, "go": "Round", "layer": 8, "on": True, "body": 0, "flags": 0,
                            "shapes": list(shapes)}]}

    air = np.array([10.0, 5.0, 10.5, 7.079])
    base = kb.knockback_envelope(air, "left", p, Terrain2D.from_boxes([floor()]))
    for sh in (shape("circle", [[12.5, 8.6]], 0.8), shape("capsule", [[12.0, 8.0], [13.0, 8.0]], 0.5),
               shape("blob", [[12.0, 8.0], [13.0, 9.0]])):
        t = Terrain2D.from_message(msg(sh))
        assert len(t.slopes) >= 4
        env = kb.knockback_envelope(air, "left", p, t)
        assert env.flags & kb.KF_SLOPE, sh["k"]
        assert env.swept[1] < base.swept[1] - 0.05                # the disk reaches below the open-air path
        hull, fl = kb.knockback_hull(np.repeat(air[None, None], 3, axis=1), p, t)
        assert fl[0] & kb.KF_SLOPE
    far = Terrain2D.from_message(msg(shape("circle", [[60.0, 8.6]], 0.8)))
    assert not kb.knockback_envelope(air, "left", p, far).flags & kb.KF_SLOPE
    # the circle's flat faces (circumscribed octagon) still stop a rollout; a radius-free box stays sharp
    oct_, closed, rnd = Terrain2D.shape_outline("circle", np.array([[0.0, 0.0]]), 1.0)
    assert closed and rnd == (-1.0, -1.0, 1.0, 1.0) and np.abs(oct_).max() == pytest.approx(1.0)
    assert np.hypot(*oct_.T).max() == pytest.approx(1.0 / np.cos(np.pi / 8))
    assert Terrain2D.shape_outline("box", np.array([[0, 0], [1, 0], [1, 1], [0, 1.0]]))[2] is None


def test_batched_queries_match_single_ones_and_the_open_air_table(p):
    from ssbot.tools.kin_check import load_fixture
    _, terrains = load_fixture(FIXTURE)
    terrain = terrains["Bone_05"]
    rng = np.random.default_rng(3)
    x = rng.uniform(68.0, 103.0, (4, 6))
    y = rng.uniform(2.015, 9.0, (4, 6))
    boxes = np.stack([x - 0.25, y, x + 0.25, y + 2.0789], axis=-1)
    table = kb.knockback_table(p, "right")
    swept, frames, flags = kb.knockback_boxes(boxes, "right", p, terrain, per_frame=True, table=table)
    assert swept.shape == (4, 6, 4) and frames.shape == (4, 6, kb.FRAMES + 1, 4)
    for i in range(4):
        for j in range(6):
            env = kb.knockback_envelope(boxes[i, j], "right", p, terrain)
            assert np.array_equal(env.union, frames[i, j]) and np.array_equal(env.swept, swept[i, j])
    opened = flags == 0
    assert opened.any() and (flags != 0).any()
    assert np.allclose(swept[opened], boxes[opened] + table.swept_offset)
    loose, _, _ = kb.knockback_boxes(boxes, "right", p, terrain, clip=False)
    assert (loose[..., :2] <= swept[..., :2] + 1e-12).all() and (loose[..., 2:] >= swept[..., 2:] - 1e-12).all()
    par, _, _ = kb.knockback_boxes(boxes, "right", p, terrain, threads=2)
    assert np.array_equal(par, swept)


def test_candidate_hull_bounds_every_frame_and_side(p):
    """knockback_hull (the planner's per-tick query) contains, per candidate, the swept hull of a hit in each valid
    frame from either side, terrain-clipped or not; open air: exactly their unclipped union."""
    from ssbot.tools.kin_check import load_fixture
    _, terrains = load_fixture(FIXTURE)
    terrain = terrains["Bone_05"]
    assert len(terrain.slopes)                                       # the Roof Collider
    rng = np.random.default_rng(5)
    N, T1 = 64, 49
    x = np.cumsum(rng.uniform(-0.2, 0.2, (N, T1)), axis=1) + rng.uniform(70.0, 100.0, (N, 1))
    y = np.clip(np.cumsum(rng.uniform(-0.15, 0.15, (N, T1)), axis=1) + rng.uniform(2.015, 12.0, (N, 1)), 2.015, None)
    boxes = np.stack([x - 0.25, y, x + 0.25, y + 2.0789], axis=-1)
    valid = rng.random((N, T1)) < 0.8
    valid[0] = False
    hull, flags = kb.knockback_hull(boxes, p, terrain, valid=valid)
    assert hull[0, 0] > hull[0, 2]                                   # no frame can be hit: empty
    assert (flags & kb.KF_SLOPE).any() and not (flags & kb.KF_SLOPE).all()
    for side in ("left", "right"):
        for clip in (True, False):
            sw, _, _ = kb.knockback_boxes(boxes, side, p, terrain, clip=clip)
            for i in range(1, N):
                s = sw[i, valid[i]]
                assert (hull[i, :2] <= s[:, :2].min(axis=0) + 1e-12).all()
                assert (hull[i, 2:] >= s[:, 2:].max(axis=0) - 1e-12).all()
    op = np.flatnonzero(flags == 0)[1:]
    sw = [kb.knockback_boxes(boxes[op], s, p, terrain, clip=False)[0] for s in ("left", "right")]
    for j, i in enumerate(op):
        u = np.concatenate([w[j, valid[i]] for w in sw])
        assert np.allclose(hull[i], np.r_[u[:, :2].min(axis=0), u[:, 2:].max(axis=0)])
    par, _ = kb.knockback_hull(boxes, p, terrain, valid=valid, threads=2)
    assert np.array_equal(par, hull)


def test_weighted_anklet_halves_the_push(p):
    plain = kb.knockback_table(p, "left")
    heavy = kb.knockback_table(p, "left", weighted=True)
    assert heavy.step[0] == pytest.approx(plain.step[0] * p.weighted_knockback_mult)
    assert heavy.swept_offset[2] - kb.CONTACT_SLOP == pytest.approx((plain.swept_offset[2] - kb.CONTACT_SLOP) / 2)
    again = kb.knockback_table(p.with_weighted(), "left")                    # already weighted params: same bound
    assert np.array_equal(again.offsets, heavy.offsets) and again.step == heavy.step


def test_escaping_hits_are_listed_and_fail_the_run(p, tmp_path):
    from ssbot.tools import kin_check
    tr, terrains = kin_check.load_fixture(FIXTURE)
    hits = np.flatnonzero(km._onset(tr.flag("recoilFrozen")))
    tr.box = tr.box.copy()
    i = int(hits[0])
    tr.box[i + 5] += np.array([-1.0, 0.0, -1.0, 0.0])          # a frame in the hit-stop 1 u towards the impact side
    rep = kin_check.check_knockback(tr, terrains, p)
    assert not rep["ok"] and len(rep["misses"]) == 1 and rep["misses"][0]["f"] == int(tr.f[i])
    path = tmp_path / "doctored.npz"
    kin_check.save_fixture(path, tr, terrains)
    assert kin_check.main([str(path), "--no-windows"]) == 1
    assert kin_check.main([str(FIXTURE), "--no-windows"]) == 0
