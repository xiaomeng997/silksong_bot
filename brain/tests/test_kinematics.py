"""Hero kinematics model (ssbot.knowledge.kinematics): synthetic checks of the integrator, the collision and the
mode machine against the decompiled HeroController rules, the compiled build against the NumPy reference, the input
filter's state, the variant lanes, the estimator's use of exported timers, and acceptance under the planner's
information set on held-out play: tests/fixtures/kin_bellbeast_trial.npz (frames 45240-51240 of the trial run
20261001_121446 i0_000) and kin_live_heldout.npz (live run 20261001_122249 i1_000 around a hit during Bind and a
BossDeathSlow kill, i2_002 around a hit under the sloped roof); the parameters are fitted on live i0_000 only."""
import random
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.knowledge.kinematics import HeroParams, Terrain2D
from ssbot.tools import cstate as cst

FIXTURE = Path(__file__).parent / "fixtures" / "kin_bellbeast_trial.npz"
LIVE = Path(__file__).parent / "fixtures" / "kin_live_heldout.npz"
# measured on the fixtures with the shipped parameters (fitted on live i0_000), minus a margin: share of covered
# windows within 0.1 u after 0.5 s, nominal lane (plain primitives, all) and inside the variant lanes' hull
# (trial 0.9915 / 0.9042 / 0.9896; live fixture 0.9865 / 0.8698 / 0.9567, its windows crowd around rare events)
ACCEPT = {"trial": {"plain": 0.985, "planner": 0.89, "bounds": 0.98},
          "live": {"plain": 0.98, "planner": 0.85, "bounds": 0.94}}
FT = 1 / 60
REST = 2.0 + 0.015 + 1.5527          # body y standing on a floor at y = 2 (Bone_05: 3.5677)


@pytest.fixture(scope="module")
def p() -> HeroParams:
    params = HeroParams.load()
    params.frame_time = FT
    return params


def floor(x0=0.0, x1=200.0, top=2.0) -> tuple:
    return (x0, top - 2.0, x1, top)


def roll(p, start, masks, terrain=None, events=None, n=None):
    masks = np.asarray(masks, dtype=np.int64)
    return km.rollout(start, masks[None] if masks.ndim == 1 else masks, p, terrain, events=events)


def steps_taken(r, lane=0) -> np.ndarray:
    """Frames whose physics body moved (QX/QY updated) are those with a step; recover them from phys changes."""
    return np.flatnonzero(np.any(np.diff(r.phys[lane], axis=0) != 0, axis=1)) + 1


# ---- parameters -----------------------------------------------------------------------------------------------

def test_shipped_params_hold_the_measured_constants(p, tmp_path):
    assert (p.gravity, p.run_speed, p.jump_speed, p.jump_steps) == (60.0, 8.25, 18.6, 8)
    assert (p.foot, p.head, p.half_width, p.skin) == (1.5527, 0.5262, 0.25, 0.015)
    assert p.scene("Bone_05") == {"enable": ["Threaded Bell Gate", "Threaded Bell Gate (1)"], "disable": ["Wall"]}
    assert len(p.vector()) == km.NP
    out = p.save(tmp_path / "k.json")
    assert HeroParams.load(out) == p
    with pytest.raises(ValueError, match="unknown"):
        HeroParams.from_json({**p.to_json(), "bogus": 1})


# ---- integrator and modes -------------------------------------------------------------------------------------

def test_run_is_instant_and_render_interpolates(p):
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST)
    r = roll(p, s, [km.B_RIGHT] * 30, terrain)
    vx = r.vel[0, 2:, 0]
    assert np.all(vx == 8.25)                                # no acceleration: Move() sets vx from the input
    dx = np.diff(r.phys[0, :, 0])
    assert set(np.round(dx[dx != 0], 6)) == {round(8.25 * p.fdt, 6)}     # 0.165 per physics step
    assert np.allclose(np.diff(r.pos[0, 10:, 0]), 8.25 * FT, atol=2e-3)  # render: 0.1375 per frame
    assert r.phys[0, -1, 1] == pytest.approx(REST)


def test_full_jump_matches_the_step_rules(p):
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST)
    r = roll(p, s, [km.B_JUMP] * 60, terrain)
    vy = r.vel[0, :, 1]
    rise = p.jump_speed - p.gravity * p.fdt                  # 17.4 reported after each Jump() step
    assert np.count_nonzero(np.isclose(vy[np.r_[True, np.diff(vy) != 0]], rise)) == 1
    # semi-implicit Euler, 9 steps at 18.6 then gravity: the closed form of the peak (BecomeAirborne lifts 0.02)
    y, v = REST + p.airborne_lift, 0.0
    peak = y
    for k in range(40):
        v = (p.jump_speed if k <= p.jump_steps else v) - p.gravity * p.fdt
        y += v * p.fdt
        peak = max(peak, y)
        if v < 0:
            break
    assert r.phys[0, :, 1].max() == pytest.approx(peak, abs=1e-6)
    assert peak - REST == pytest.approx(5.5040, abs=1e-3)


def test_release_halves_the_rise_every_update(p):
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST)
    masks = [km.B_JUMP] * 5 + [0] * 20
    r = roll(p, s, masks, terrain)
    vy = r.vel[0, :, 1]
    i = 6                                                    # first frame with the jump released
    assert 0 < vy[i] < vy[i - 1] * p.jump_release_mult + 1e-9
    assert r.phys[0, :, 1].max() - REST < 2.6                # a short hop


def test_falling_lands_on_the_floor_and_stops(p):
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST + 4.0, ground=False)
    r = roll(p, s, [0] * 60, terrain)
    assert r.phys[0, -1, 1] == pytest.approx(REST, abs=p.land_slop_hi + 1e-6)
    assert r.vel[0, -1, 1] == 0.0
    assert r.flags[0, -1] & km.F_GROUND
    assert r.vel[0, :, 1].min() >= -p.max_fall


def test_wall_stops_the_box_one_skin_away(p):
    terrain = Terrain2D.from_boxes([floor(), (50.0, 0.0, 52.0, 20.0)])
    s = km.initial_state(p, 45.0, REST)
    r = roll(p, s, [km.B_RIGHT] * 60, terrain)
    assert r.phys[0, -1, 0] == pytest.approx(50.0 - p.skin - p.half_width)


def test_ceiling_cuts_the_jump(p):
    terrain = Terrain2D.from_boxes([floor(), (0.0, 7.0, 200.0, 8.0)])
    s = km.initial_state(p, 10.0, REST)
    r = roll(p, s, [km.B_JUMP] * 40, terrain)
    top = 7.0 - p.skin - p.head
    assert r.phys[0, :, 1].max() == pytest.approx(top)
    assert r.phys[0, -1, 1] < top - 0.5                      # bumped, falling again


def test_walking_off_a_ledge_falls_from_the_next_step(p):
    terrain = Terrain2D.from_boxes([(0.0, 3.0, 30.0, 5.0), (30.0, 0.0, 200.0, 2.0)])
    hi = 5.0 + p.skin + p.foot
    s = km.initial_state(p, 29.5, hi)
    r = roll(p, s, [km.B_RIGHT] * 60, terrain)
    y = r.phys[0, :, 1]
    off = int(np.argmax(r.phys[0, :, 0] - p.half_width > 30.0))
    assert y[off] == pytest.approx(hi)                       # the step that leaves the edge does not sink
    assert y[off + 3] < hi
    assert y[-1] == pytest.approx(REST, abs=p.land_slop_hi + 1e-6)


def test_downspike_antic_spike_and_landing_recovery(p):
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST)
    masks = [km.B_JUMP | km.B_RIGHT] * 12 + [km.B_DOWN | km.B_ATTACK | km.B_RIGHT] * 3 + [km.B_RIGHT] * 45
    r = roll(p, s, masks, terrain)
    m = r.mode[0]
    antic = np.flatnonzero(m == km.M_DS_ANTIC)
    spike = np.flatnonzero(m == km.M_DS_SPIKE)
    assert 6 <= len(antic) <= 7 and antic[0] == 13           # 0.1 s of Update time from the press frame
    assert len(spike) > 0 and spike[0] == antic[-1] + 1
    v = r.vel[0, spike[1:]]
    v = v[np.abs(v[:, 1]) > 20]
    assert np.allclose(v, [26.0, -26.0])                    # facing right: (+26, -26), gravity off
    land = np.flatnonzero(r.flags[0, spike[0]:] & km.F_GROUND)[0] + spike[0]
    still = r.phys[0, land + 2:land + 8, 0]
    assert np.allclose(still, still[0])                      # DOWNSPIKE_LAND_RECOVERY: no running for 0.167 s


def test_damage_knockback_freezes_then_recoils_away(p):
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST)
    ev = np.zeros((1, 50), dtype=np.int64)
    ev[0, 0] = km.EV_HURT_L                                  # impact on the left: pushed right
    r = roll(p, s, [km.B_LEFT] * 50, terrain, events=ev)
    m = r.mode[0]
    frozen = np.flatnonzero(m == km.M_HURT_FREEZE)
    rec = np.flatnonzero(m == km.M_HURT_RECOIL)
    assert 13 <= len(frozen) <= 15                           # FreezeMoment: wait 0.1 s + ramp 0.1 s, unscaled
    assert np.allclose(r.phys[0, frozen, 0], 10.0)
    d = r.phys[0, rec[-1] + 1] - r.phys[0, rec[0]]
    n = round(d[0] / (p.hurt_velocity * p.fdt))
    assert n in (10, 11)
    assert d[1] == pytest.approx(n * p.hurt_velocity * p.hurt_vy_ratio * p.fdt)
    assert np.all(r.flags[0, frozen[0]:rec[-1] + 1] & km.F_NO_INPUT)
    assert r.vel[0, -1, 0] == -8.25                          # control back: the held left moves her again


def test_nail_recoil_pushes_back_for_eight_steps(p):
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST)
    ev = np.zeros((1, 30), dtype=np.int64)
    ev[0, 5] = km.EV_RECOIL_L
    r = roll(p, s, [km.B_RIGHT] * 30, terrain, events=ev)
    vx = r.vel[0, :, 0]
    after = vx[6:]
    pushed = np.flatnonzero(after == -p.recoil_velocity)
    st = steps_taken(r)
    assert len([f for f in st if 6 < f <= 6 + pushed[-1] + 1]) >= p.recoil_steps
    assert after[-1] == 8.25


def test_silkspear_needs_silk_and_runs_its_phases(p):
    terrain = Terrain2D.from_boxes([floor()])
    masks = [km.B_QUICKCAST] * 3 + [0] * 70
    poor = roll(p, km.initial_state(p, 10.0, REST, silk=3), masks, terrain)
    assert (poor.mode[0] == km.M_NORMAL).all()
    r = roll(p, km.initial_state(p, 10.0, REST, silk=9, facing=1), masks, terrain)
    cast = np.flatnonzero(r.mode[0] == km.M_CAST)
    assert cast[0] == 1 and r.final[km.SILK, 0] == 9 - p.cast_silk
    x = r.phys[0, :, 0]
    assert x[cast[-1] + 1] == pytest.approx(10.0 - 0.9, abs=0.05)   # the catch pulls her back ~0.9 u (log: 0.899)


def test_bind_holds_her_in_the_air(p):
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST + 3.0, ground=False, silk=9)
    r = roll(p, s, [km.B_BIND] * 2 + [0] * 70, terrain)
    b = np.flatnonzero(r.mode[0] == km.M_BIND)
    assert len(b) >= 60
    assert np.ptp(r.phys[0, b[5:], 1]) < 0.05


def test_lanes_are_independent(p):
    terrain = Terrain2D.from_boxes([floor(), (50.0, 0.0, 52.0, 20.0)])
    s = km.initial_state(p, 45.0, REST)
    masks = np.array([[km.B_RIGHT] * 40, [km.B_JUMP | km.B_LEFT] * 40, [0] * 40])
    both = km.rollout(s, masks, p, terrain)
    for i in range(3):
        one = km.rollout(s, masks[i:i + 1], p, terrain)
        assert np.array_equal(both.phys[i], one.phys[0])
        assert np.array_equal(both.mode[i], one.mode[0])


def test_rollout_returns_collider_boxes_and_bounding_variant_lanes(p):
    """Decision 1 (collider boxes and centres) and decision 4 (variant lanes for the +-1 frame branches)."""
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 10.0, REST)
    masks = np.array([[km.B_JUMP | km.B_RIGHT] * 12 + [km.B_DOWN | km.B_ATTACK] * 3 + [0] * 33,
                      [km.B_RIGHT] * 48])
    plain = km.rollout(s, masks, p, terrain)
    assert plain.box.shape == (2, 49, 4)
    assert np.allclose(plain.centre[..., 0], plain.phys[..., 0])
    assert np.allclose(plain.box[..., 3] - plain.box[..., 1], p.foot + p.head)
    for name, n_lanes in (("fast", 3), ("bounds", 9), ("full", 17)):
        r = km.rollout(s, masks, p, terrain, variants=name)
        assert r.var_box.shape == (2, n_lanes, 49, 4)
        assert np.array_equal(r.box, plain.box)                      # lane 0 is the nominal lane
        assert (r.bound[..., :2] <= r.var_box[..., :2].min(axis=1) + 1e-12).all()
        assert (r.bound[..., 2:] >= r.var_box[..., 2:].max(axis=1) - 1e-12).all()
    r = km.rollout(s, masks, p, terrain, variants="bounds")
    antic = (r.var_mode[0] == km.M_DS_ANTIC).sum(axis=1)
    assert set(antic.tolist()) >= {6, 7}                             # both antic lengths among the lanes
    with pytest.raises(ValueError, match="nominal timing"):
        km.rollout(s, masks, p, terrain, variants="bounds", dt=np.full(48, FT), fs=np.ones(48))


def test_compiled_rollout_matches_the_numpy_reference(p):
    """kin_jit is the per-lane scalar build of _fixed_step / _apply_events / _update: bit-identical outputs on random
    buttons and events, every variant lane and logged timing (the reference stays the readable version)."""
    from ssbot.tools.kin_check import load_fixture
    tr, terrains = load_fixture(FIXTURE)
    terrain = terrains["Bone_05"]
    rng = np.random.default_rng(7)
    n, T = 96, 40
    idx = rng.integers(10, len(tr) - T - 1, n)
    S = km.estimate_state(tr, idx, p, terrain=terrain)
    masks = np.zeros((n, T), dtype=np.int64)
    for b in (km.B_JUMP, km.B_ATTACK, km.B_LEFT, km.B_RIGHT, km.B_DOWN, km.B_UP, km.B_QUICKCAST, km.B_BIND):
        masks |= np.where(rng.random((n, T)) < 0.25, b, 0)
    pool = [km.EV_RECOIL_L, km.EV_RECOIL_R, km.EV_POGO, km.EV_HURT_L, km.EV_HURT_R, km.EV_SILK, km.EV_RECOIL_DOWN,
            km.EV_CATCH, km.EV_LOCK, km.EV_UNLOCK]
    ev = np.where(rng.random((n, T)) < 0.03, rng.choice(pool, (n, T)), 0)
    I = idx[:, None] + np.arange(1, T + 1)[None]
    cases = [{}, {"events": ev}, {"events": ev, "variants": "bounds"}, {"udt": rng.uniform(0.0166, 0.02, (n, T))},
             {"events": km.derive_events(tr)[I], "dt": tr.dt[I], "fs": tr.fs[I], "udt": tr.udt[I]}]
    for kw in cases:
        a = km.rollout(S, masks, p, terrain, backend="numpy", **kw)
        b = km.rollout(S, masks, p, terrain, backend="numba", **kw)
        for name in ("phys", "pos", "vel", "mode", "flags", "box", "final"):
            assert np.array_equal(getattr(a, name), getattr(b, name)), (name, list(kw))


def test_compiled_rollout_fits_the_planner_batch(p):
    """DESIGN §3.5.4: 512 candidates x 48 frames. Generous bound (catches a fallback to the NumPy path, which takes
    ~70 ms); the measured figures are in the kinematics module docstring."""
    import time
    terrain = Terrain2D.from_boxes([floor()])
    s = km.initial_state(p, 50.0, REST)
    masks = np.random.default_rng(0).choice([0, km.B_RIGHT, km.B_JUMP | km.B_LEFT, km.B_ATTACK], (512, 48))
    km.rollout(s, masks, p, terrain)
    t0 = time.perf_counter()
    for _ in range(5):
        km.rollout(s, masks, p, terrain)
    assert (time.perf_counter() - t0) / 5 < 0.03


def test_hold_filter_carries_its_state_across_calls():
    """A planner that replans every frame passes the filter state it keeps in step with the ACTIONs it sent: the
    suffix then latches exactly as the full history does (from an idle filter it would re-press two frames early)."""
    J = km.B_JUMP
    commanded = np.array([J, 0, J, J, J, 0])
    full, _ = km.hold_filter(commanded)
    assert [int(m != 0) for m in full] == [1, 1, 0, 0, 1, 1]
    _, st = km.hold_filter(commanded[:2])
    rest, _ = km.hold_filter(commanded[2:], st)
    assert np.array_equal(rest, full[2:])
    naive, _ = km.hold_filter(commanded[2:])
    assert not np.array_equal(naive, full[2:])
    hf = {"latched": int(st.mask()[0]), "desired": int(commanded[1]), "pending": st.pending[0].tolist(),
          "age": st.age[0].tolist()}
    synced, _ = km.hold_filter(commanded[2:], km.HoldState.from_hf(hf))   # STATE act.hf, when the oracle sends it
    assert np.array_equal(synced, full[2:])
    lr, _ = km.hold_filter(np.array([km.B_LEFT, km.B_LEFT | km.B_RIGHT, km.B_RIGHT, km.B_RIGHT, km.B_RIGHT]))
    assert not any((m & km.B_LEFT) and (m & km.B_RIGHT) for m in lr)    # never both directions


# ---- terrain --------------------------------------------------------------------------------------------------

def _shape(kind: str, pts) -> dict:
    return {"k": kind, "v": np.asarray(pts, dtype=np.float32).tobytes()}


def _solid(go: str, on: bool, pts) -> dict:
    return {"id": hash(go) & 0xFFFF, "go": go, "layer": 8, "on": on, "body": 0, "flags": 0,
            "shapes": [_shape("box", pts)]}


def test_terrain_from_message_with_gates_and_stale_solids(p):
    box = lambda x0, y0, x1, y1: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]  # noqa: E731
    msg = {"seq": 1, "scene_raw": "Arena", "scene": "Arena", "reason": "enter", "frame": 1,
           "solids": [_solid("Floor", True, box(0, 0, 100, 2)), _solid("Gate L", False, box(20, 0, 22, 10)),
                      _solid("Gate R", False, box(60, 0, 62, 10)), _solid("Wall", True, box(40, 0, 45, 10))],
           "hazards": []}
    t = Terrain2D.from_message(msg, {"enable": ["Gate L", "Gate R"], "disable": ["Wall"]})
    assert len(t.gates) == 2 and t.n_base == (2, 2)
    assert list(t.inside_gates(np.array([10.0, 30.0, 70.0]))) == [False, True, False]
    s = km.initial_state(p, 30.0, REST)
    closed = roll(p, s, [km.B_RIGHT] * 300, t)
    assert closed.phys[0, -1, 0] == pytest.approx(60.0 - p.skin - p.half_width)   # Wall gone, gate closed
    opened = roll(p, s, [km.B_RIGHT] * 300, t.open())
    assert opened.phys[0, -1, 0] > 62.0                                                # through the open gate


# ---- traces from STATE dicts ----------------------------------------------------------------------------------

def _state(f: int, x: float, y: float, inp: int = 0, act: int = 0, **flags) -> dict:
    names = km.cstate_names()
    words = cst.encode({"onGround": True, "facingRight": True, **flags}, names)
    return {"f": f, "fs": 1, "dt": FT, "udt": FT, "ts": 1.0, "ev": [], "act": {"mask": act}, "input": {"mask": inp},
            "game": {"gs": 4, "scene": "Bone_05", "paused": False}, "pause": {},
            "hero": {"pos": [x, y, 0.0], "vel": [0.0, 0.0], "box": [x - 0.25, y - 1.5527, x + 0.25, y + 0.5262],
                     "facing": 1, "hero_state": 1, "control_relinquished": False, "cstate": words, "silk": 9,
                     "health": 5, "anim": {"clip": "Idle"}, "spell": ["Idle", 0.0]}}


def test_input_traces_move_the_jump_press_back_one_frame(p):
    inp = [0, 0, km.B_JUMP, km.B_JUMP, km.B_JUMP, 0, 0]       # the exporter shows the press one frame late
    tr = km.Trace.from_states([_state(i, 10.0, REST, inp=m) for i, m in enumerate(inp)], p)
    assert tr.mask_source == "input"
    assert [int(m & km.B_JUMP != 0) for m in tr.mask] == [0, 1, 1, 1, 1, 0, 0]   # release kept in place
    act = km.Trace.from_states([_state(i, 10.0, REST, act=m) for i, m in enumerate(inp)], p)
    assert act.mask_source == "act" and list(act.mask) == inp


def test_excitation_probe_plans_stay_left_of_the_trigger(p):
    from ssbot.probes import kin_excite as kx
    rng = random.Random(3)
    kinds = {kx.draw(rng, True).kind for _ in range(400)}
    assert {"jump_hold", "down_attack", "turnaround", "silkspear", "bind", "hurt", "jump_queue"} <= kinds
    terrain = Terrain2D.from_boxes([floor(60, 110), (67.2, 0.0, 69.2, 14.0), (102.0, 0.0, 104.0, 14.0)])
    S = km.estimate_state(km.Trace.from_states([_state(0, 78.0, REST)], p), [0], p, terrain=terrain)
    hurt_trials = 0
    for seed in range(8):
        t = kx.plan(random.Random(seed), _state(0, 78.0, REST), (p, terrain), hurt=True)
        r = km.rollout(S, np.array(t.masks + [0] * kx.SETTLE_FRAMES)[None], p, terrain)
        assert kx.X_SAFE[0] <= r.phys[0, :, 0].min() and r.phys[0, :, 0].max() <= kx.X_SAFE[1]
        if t.hurt:                      # the plan was checked with the hit on every frame it can land on
            hurt_trials += 1
            assert kx.safe(S, t, p, terrain)
    # standing 3.5 u from the trigger is safe, but not with a hit from the left: the 4.2 u knockback carries her past
    S2 = km.estimate_state(km.Trace.from_states([_state(0, 82.0, REST)], p), [0], p, terrain=terrain)
    assert kx.safe(S2, kx.Trial("rest", {}, [0] * 30, None), p, terrain)
    assert kx.safe(S2, kx.Trial("hurt", {}, [0] * 30, {"frame": 10, "side": "right"}), p, terrain)
    assert not kx.safe(S2, kx.Trial("hurt", {}, [0] * 30, {"frame": 10, "side": "left"}), p, terrain)


# ---- the real slice -------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    from ssbot.tools.kin_check import load_fixture
    return load_fixture(FIXTURE)


def test_fixture_is_small_and_complete(real):
    tr, terrains = real
    assert FIXTURE.stat().st_size < 500_000
    assert "Bone_05" in terrains and len(terrains["Bone_05"].gates) == 2
    assert tr.mask_source == "act" and len(tr) == 6000


def test_estimator_reads_the_body_and_replays_every_hit_stop(real, p):
    tr, terrains = real
    S = km.estimate_state(tr, np.arange(100, 110), p)
    assert np.allclose(S[[km.PX, km.PY]].T, tr.phys[100:110])
    rep = km._freeze_replay(tr, p)
    modes = km.classify_modes(tr)
    hits = np.flatnonzero(km._onset(tr.flag("recoilFrozen")))
    ok = 0
    for i in hits:
        k = i + 1
        while k < len(tr) and modes[k] == km.M_HURT_FREEZE:
            k += 1
        pred = np.flatnonzero(rep[i:i + 40, 0] == 2)
        ok += int(len(pred) > 0 and i + pred[0] == k)
    assert len(hits) >= 15 and ok == len(hits)


def test_acceptance_on_the_held_out_trial_slice(real):
    """Decision 3: start state from the history only, the planner's timing; logged events stand in for the threat
    layer. The trial run is held out (the parameters are fitted on live i0_000). The thresholds are the measured
    figures minus a margin, not the 99 % target, which the planner setting does not reach for the event-driven
    primitives (hit-stop and recoil end on one of two frames that the frame jitter decides)."""
    from ssbot.tools.kin_check import check_knockback, check_trace, summarize
    tr, terrains = real
    p = HeroParams.load()                                         # the shipped values, frame time included
    res = check_trace(tr, terrains, p, horizon=30, tol=0.1)
    rep = summarize([res], 0.1, 30)
    assert rep["windows"] == len(tr) - 30                                    # every window counted
    pe, pb, re_ = rep["planner_events"], rep["planner_bounds"], rep["replay_events"]
    assert pe["by_category"]["plain"]["phys"]["within"] >= ACCEPT["trial"]["plain"]
    assert pe["covered"]["phys"]["within"] >= ACCEPT["trial"]["planner"]
    assert pb["covered"]["phys"]["within"] >= ACCEPT["trial"]["bounds"]
    assert re_["covered"]["phys"]["within"] >= 0.99                           # the model itself, logged timing
    kb = check_knockback(tr, terrains, p)
    assert kb["checked"] >= 15 and kb["ok"] and not kb["misses"]


def test_acceptance_on_held_out_live_play_with_a_hit_during_bind():
    """Live run i1_000 (not used by kin_fit) around a hit during Bind (BindBreak holds the time scale at 0 for 0.4 s
    after the recoil started), a BossDeathSlow kill, and i2_002's hit in Bind under the sloped Roof Collider: the
    knockback envelope contains every no-input frame of all three; nominal timing per primitive as measured."""
    from ssbot.tools.kin_check import check_knockback, check_trace, load_fixture, summarize
    tr, terrains = load_fixture(LIVE)
    p = HeroParams.load()
    kb = check_knockback(tr, terrains, p)
    assert kb["checked"] >= 3 and kb["ok"] and not kb["misses"]
    assert kb["delayed_hits"] >= 2 and kb["slope_bound"] >= 1
    assert {"BindBreak", "BossDeathSlow"} <= set(kb["concurrent_freezes"])
    rep = summarize([check_trace(tr, terrains, p)], 0.1, 30)
    assert "world_freeze" in rep["categories"] and "uncovered:invalid" in rep["categories"]   # the seams
    pe, pb = rep["planner_events"], rep["planner_bounds"]
    assert pe["by_category"]["plain"]["phys"]["within"] >= ACCEPT["live"]["plain"]
    assert pe["covered"]["phys"]["within"] >= ACCEPT["live"]["planner"]
    assert pb["covered"]["phys"]["within"] >= ACCEPT["live"]["bounds"]


def test_fit_recovers_the_constants_from_the_slice(real):
    from ssbot.tools import kin_fit
    f = kin_fit.Fit(HeroParams())
    tr, terrains = real
    modes = km.classify_modes(tr)
    kin_fit.fit_box(tr, terrains, f)
    kin_fit.fit_motion(tr, modes, f)
    kin_fit.fit_recoil(tr, f)
    kin_fit.fit_hurt(tr, modes, f)
    assert f.p.gravity == pytest.approx(60.0, abs=0.01)
    assert f.p.run_speed == pytest.approx(8.25, abs=1e-3)
    assert f.p.jump_speed == pytest.approx(18.6, abs=1e-3)
    assert f.p.skin == pytest.approx(0.015, abs=1e-3)
    assert f.p.hurt_velocity == pytest.approx(15.0, abs=0.01)
    assert kin_fit._threshold([(0.2498, 0.2664), (0.2499, 0.2667)])[0] == 0.25


def test_estimator_takes_the_exported_timers_and_phase(p):
    """Decision 5: hero.tm / hero.alpha replace the reconstruction where STATE carries them."""
    plain = [_state(i, 10.0, REST) for i in range(4)]
    S0 = km.estimate_state(km.Trace.from_states(plain, p), [3], p)
    tm = {"inv": 0.4, "recoil": 0.0, "recoil_steps": 0, "dash_cd": 0, "atk_cd": 0.2, "atk_t": 0.1, "tool_cd": 0,
          "jump_steps": 0, "jumped_steps": 7, "ds": 0.0, "ds_rec": -1, "grav": 0.3, "qj": 2, "qa": -1, "qt": -1}
    rich = [dict(s, hero=dict(s["hero"], tm=tm, alpha=0.375)) for s in plain]
    tr = km.Trace.from_states(rich, p)
    assert tr.tm is not None and tr.alpha_log is not None
    S = km.estimate_state(tr, [3], p)
    assert S[km.ALPHA, 0] == S[km.ALO, 0] == S[km.AHI, 0] == 0.375
    assert (S[km.GS, 0], S[km.INV_T, 0], S[km.ATK_CD, 0], S[km.JDSTEPS, 0], S[km.JQ, 0]) == (0.3, 0.4, 0.2, 7, 2)
    assert S0[km.AHI, 0] - S0[km.ALO, 0] > 0.1                 # without hero.alpha the phase is an interval


def test_savestate_load_slide_is_marked_and_not_scored(p):
    """2026-10-01: after a savestate load the game can slide the hero back to the saved position with velocity 0
    (up to 17 frames at ~0.63 u/frame); those frames are MK_SLIDE and their windows uncovered:slide."""
    from ssbot.tools.kin_check import categorize
    states = [_state(i, 72.0, REST) for i in range(10)]
    states[9]["ev"] = [{"k": "harness", "d": {"op": "savestate.load", "name": "bellbeast_arena"}}]
    states += [_state(10 + i, 72.0 + 0.6 * (i + 1), REST) for i in range(10)]
    states += [_state(20 + i, 78.0, REST) for i in range(40)]
    tr = km.Trace.from_states(states, p)
    slid = (tr.marks & km.MK_SLIDE) != 0
    assert slid[10:20].all() and not slid[25:].any()
    modes = km.classify_modes(tr)
    _, labels = categorize(tr, 30, modes, km.derive_events(tr, modes), {"Bone_05": Terrain2D.empty()})
    assert labels[0] == "uncovered:slide" and labels[-1] != "uncovered:slide"


def test_windows_are_counted_never_dropped(real, p):
    """Every row with a full horizon after it is one window; invalid frames and gaps are labelled, not skipped."""
    from ssbot.tools.kin_check import categorize
    tr, terrains = real
    tr = tr.slice(0, 600)
    tr.valid = tr.valid.copy()
    tr.valid[100] = False
    tr.f = tr.f.copy()
    tr.f[400:] += 7
    modes = km.classify_modes(tr)
    starts, labels = categorize(tr, 30, modes, km.derive_events(tr, modes), terrains)
    assert len(starts) == len(tr) - 30
    assert (labels[70:101] == "uncovered:invalid").all()
    assert (labels[370:400] == "uncovered:gap").all()


def test_residual_monitor_scores_executed_predictions(p):
    """DESIGN §3.5.2: the runtime residual monitor compares what the executed lane predicted with what happened."""
    mon = km.ResidualMonitor(horizons=(1, 6), window=50, min_n=5, hard_u=0.5)
    for f in range(40):
        mon.predict(f, np.array([[f, 0.0]] + [[f + h + 0.01 * (h == 6), 0.0] for h in range(1, 7)]))
        mon.observe(f, (float(f), 0.0))
    st = mon.status()
    assert st["ok"] and st["horizons"][1]["within"] == 1.0 and st["horizons"][6]["max"] == pytest.approx(0.01)
    mon.predict(40, np.array([[40.0, 0.0]] + [[40.0 + h, 0.0] for h in range(1, 7)]))
    mon.invalidate()                                           # an unpredicted hit: not the model's miss
    assert mon.dropped >= 2
    mon.predict(41, np.array([[41.0, 0.0]] + [[41.0 + h, 0.0] for h in range(1, 7)]))
    mon.observe(42, (43.0, 0.0))                               # 1 u off
    assert not mon.status()["ok"] and mon.confidence() == 0.0


def test_shipped_params_carry_the_jitter_model_and_the_jump_spread(p):
    """kin_fit products the planner and the hazard margin read: the frame-time jitter model (2.96 M frames), the
    variant-valued Silkspear phases and the apex spread per jump hold."""
    q = HeroParams.load()
    assert q.frame_time_lo <= 0.01665 < q.frame_time < q.frame_time_hi < q.frame_time_max <= q.hitch_max
    assert q.hitch_max >= 0.0369 and q.hitches_per_window == 2
    assert len(q.cast_throw_variants) == 2 and len(q.cast_catch_variants) == 2
    holds = {j["hold"]: j for j in q.jump_heights}
    assert len(holds) >= 15 and all(j["spread"] < 0.5 for j in holds.values())
    assert holds[max(holds)]["logged"][2] == pytest.approx(5.456, abs=0.05)       # a full jump
