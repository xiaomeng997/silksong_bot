"""The simulated final path (DESIGN §3.9.2): ObservabilityFilter, SimpleNoise, DelayLine, the action-side latency
client and DegradedOracleBackend, on real STATEs of the trial Bell Beast run (tests/worldstate_fixture.py)."""
import copy

import numpy as np
import pytest

from ssbot.backends import observability as obs
from ssbot.backends.degraded import DegradedOracleBackend
from ssbot.backends.delay_line import PRIOR, DelayLine, latency_model_args, set_action_latency
from ssbot.backends.noise_simple import NoiseConfig, SimpleNoise
from ssbot.backends.observability import ObservabilityFilter
from ssbot.backends.oracle_backend import OracleBackend
from ssbot.core.bosses import BELL_BEAST, BossSpec
from ssbot.core.worldstate import (O, ORACLE, E, Entity, Ev, Event, HitDealt, Kind, Screen, Src, Unobs, WorldState,
                                   iter_fields)
from tests import worldstate_fixture as fx


def oracle_frames(i: int) -> list[WorldState]:
    b = OracleBackend(bosses=[BELL_BEAST], clock=None)
    return [b.feed(s) for s in fx.window(i)]


@pytest.fixture(scope="module")
def wake() -> list[WorldState]:
    return oracle_frames(0)


def filtered(wss: list[WorldState], **kw) -> list[WorldState]:
    f = ObservabilityFilter(bosses=kw.pop("bosses", [BELL_BEAST]), **kw)
    return [f.apply(w) for w in wss]


def boss(ws: WorldState) -> Entity | None:
    return next((e for e in ws.entities if e.id == fx.BOSS_IID), None)


def test_no_oracle_only_value_survives(wake):
    for w in filtered(wake):
        leaks = [p for p, o, timer, v in iter_fields(w) if (o == O or timer) and v is not None]
        assert leaks == []
        assert not [e for e in w.events if e.kind in (Ev.FSM_TRANSITION, Ev.CATASTROPHE, Ev.DISABLE_PAUSE_ON)]
        assert w.game.unobservable & Unobs.TIMERS_DROPPED and w.game.unobservable & Unobs.PLAYTIME_WALL
    assert wake[100].hero.iframes_left is not None and wake[100].entities[0].fsm is not None   # input untouched


def test_oracle_profile_is_identity(wake):
    f = ObservabilityFilter(profile=ORACLE)
    assert f.apply(wake[0]) is wake[0]
    with pytest.raises(ValueError):
        ObservabilityFilter(profile="X")


def test_boss_hp_from_counted_hits(wake):
    out = filtered(wake)
    first = next(w for w in out if boss(w) is not None)
    assert boss(first).hp_est.v == 150.0 and boss(first).hp_est.src == Src.EVENT
    hit = next(w for w in out if any(e.kind == Ev.HIT_DEALT for e in w.events))
    assert hit.stamp.frame == 56818
    ev = next(e for e in hit.events if e.kind == Ev.HIT_DEALT)
    assert ev.data.amount is None and ev.data.target_id == fx.BOSS_IID
    est = boss(hit).hp_est
    assert est.v == 145.0 and est.sigma == pytest.approx(0.5)
    # matches the oracle while every hit is seen
    for w_o, w_v in zip(wake, out):
        if boss(w_o) is not None and boss(w_v) is not None and boss(w_v).visible_frac > 0:
            assert boss(w_v).hp_est.v == boss(w_o).hp_est.v


def test_kill_zeroes_and_drops_the_track():
    out = filtered(oracle_frames(2), hit_damage=5.0)
    i = next(i for i, w in enumerate(out) if any(e.kind == Ev.ENEMY_KILLED for e in w.events))
    assert out[i].stamp.frame == 69029
    assert boss(out[i - 1]) is not None and boss(out[i - 1]).hp_est.v == 145.0   # one hit seen in this window
    assert all(boss(w) is None for w in out[i:])


def test_unknown_types_get_no_hp(wake):
    out = filtered(wake, bosses=[])
    assert all(e.hp_est is None for w in out for e in w.entities)


def test_phase_from_the_callers_table(wake):
    out = filtered(wake)
    assert {boss(w).phase.top for w in out if boss(w) is not None and boss(w).visible_frac > 0} == {"unknown"}
    spec = BossSpec("Bone Beast", "Control", ("Death Broadcast",), 150.0,
                    phases={"Charge Antic": "charge_antic", "Charge": "charge"})
    out = filtered(wake, bosses=[spec])
    names = [(w.stamp.t_game_s, boss(w).phase) for w in out if boss(w) is not None and boss(w).visible_frac > 0]
    tops = [p.top for _, p in names]
    assert "charge_antic" in tops and "charge" in tops and "unknown" in tops
    for (t0, p0), (t1, p1) in zip(names, names[1:]):
        if p1.top == p0.top:
            assert p1.t_in_phase == pytest.approx(p0.t_in_phase + (t1 - t0))
        else:
            assert p1.t_in_phase == 0.0


def _camera_away(ws: WorldState, dx: float) -> WorldState:
    w = copy.deepcopy(ws)
    V = list(w.cam.V)
    V[12] -= dx                 # column-major translation x: the camera moves +dx, the world -dx
    w.cam.V = tuple(V)
    return w


def test_offscreen_entities_become_memory_tracks(wake):
    i = next(i for i, w in enumerate(wake) if boss(w) is not None)
    f = ObservabilityFilter(bosses=[BELL_BEAST])
    seen = f.apply(wake[i])
    assert boss(seen).visible_frac == 1.0
    b0 = boss(seen)
    away = _camera_away(wake[i + 1], 200.0)
    away.events.append(Event(Ev.HIT_DEALT, away.stamp.frame, away.stamp.t_game_s,
                             HitDealt(fx.BOSS_IID, "Bone Beast", 5.0, 145.0)))
    out = f.apply(away)
    ghost = boss(out)
    assert ghost is not None and ghost.visible_frac == 0.0 and ghost.last_seen_ms > 0
    assert ghost.pos.v == b0.pos.v and ghost.pos.src == Src.PREDICTED and ghost.pos.conf < 1.0
    assert ghost.body_polys == [] and ghost.dmg_boxes == [] and ghost.phase is None
    assert ghost.hp_est.v == 150.0                      # a hit on a hidden boss is not counted
    assert not [e for e in out.events if e.kind == Ev.HIT_DEALT]
    assert out.game.unobservable & Unobs.OFFSCREEN_HIDDEN
    # the track expires after the boss TTL (10 s of game time)
    late = _camera_away(wake[i + 2], 200.0)
    late.stamp.t_game_s += 11.0
    assert boss(f.apply(late)) is None


def test_visibility_kernel_numpy_equals_loop():
    rng = np.random.default_rng(3)
    xy = rng.uniform(-200, 1500, size=(500, 2))
    ok = rng.random(500) > 0.1
    owner = np.sort(rng.integers(0, 40, size=500))
    a = obs.visible_fractions(xy, ok, owner, 45, 1280.0, 720.0, 4.0)
    b = obs.visible_fractions_loop(xy, ok, owner, 45, 1280.0, 720.0, 4.0)
    assert np.allclose(a, b) and a[44] == 0.0


def test_play_time_runs_on_the_wall_clock(wake):
    f = ObservabilityFilter(bosses=[BELL_BEAST], calib_sigma_s=30.0, drift=1e-3)
    w0, w1, w2 = (copy.deepcopy(w) for w in wake[:3])
    a = f.apply(w0).game.play_time
    assert a.live_s == wake[0].game.play_time.live_s and a.sigma_s == 30.0 and a.saved_s is None
    b = f.apply(w1).game.play_time
    dt = (wake[1].stamp.t_sample_qpc_ns - wake[0].stamp.t_sample_qpc_ns) / 1e9
    assert b.live_s == pytest.approx(a.live_s + dt) and b.sigma_s == pytest.approx(30.0 + 1e-3 * dt)
    w2.game.screen = E(Screen.PAUSE_MENU)
    c = f.apply(w2).game.play_time
    assert c.live_s == b.live_s and not c.counting


def test_bind_ready_from_silk(wake):
    w = copy.deepcopy(wake[-1])
    w.res.silk = E(9)
    w.hero.mode = E("ground")
    assert ObservabilityFilter().apply(w).res.bind_ready.v is True
    w.res.silk = E(8)
    assert ObservabilityFilter().apply(w).res.bind_ready.v is False


# ---- noise ------------------------------------------------------------------------------------------------

def test_noise_is_seeded_and_moves_polygons_with_the_position(wake):
    base = ObservabilityFilter(bosses=[BELL_BEAST]).apply(wake[-1])
    a = SimpleNoise(seed=5).apply(copy.deepcopy(base))
    b = SimpleNoise(seed=5).apply(copy.deepcopy(base))
    c = SimpleNoise(seed=6).apply(copy.deepcopy(base))
    assert [e.pos.v for e in a.entities] == [e.pos.v for e in b.entities]
    assert [e.pos.v for e in a.entities] != [e.pos.v for e in c.entities]
    for e in (x for x in a.entities if x.visible_frac > 0):
        src = next(x for x in base.entities if x.id == e.id)
        dx, dy = e.pos.v[0] - src.pos.v[0], e.pos.v[1] - src.pos.v[1]
        for p0, p1 in zip(src.dmg_boxes, e.dmg_boxes):
            assert np.allclose(np.array(p1.poly) - np.array(p0.poly), [dx, dy])
        assert e.pos.sigma > 0
    assert a.game.unobservable & Unobs.NOISE
    assert a.hero.pos.v != base.hero.pos.v


def test_noise_drop_rate_and_sigma():
    ents = [Entity(id=i, kind=Kind.ENEMY, pos=E((0.0, 0.0)), visible_frac=1.0) for i in range(4000)]
    ghost = Entity(id=-1, kind=Kind.ENEMY, pos=E((5.0, 5.0)), visible_frac=0.0)
    cfg = NoiseConfig(sigma_pos={Kind.ENEMY: 0.2}, p_drop={Kind.ENEMY: 0.25})
    out = SimpleNoise(cfg, seed=1).apply(WorldState(entities=ents + [ghost]))
    live = [e for e in out.entities if e.visible_frac > 0]
    assert 0.72 < len(live) / 4000 < 0.78
    xy = np.array([e.pos.v for e in live])
    assert np.allclose(xy.std(axis=0), 0.2, atol=0.015)
    assert out.entities[-1].id == -1 and out.entities[-1].pos.v == (5.0, 5.0)   # memory tracks untouched


# ---- delay line and the action-side client -------------------------------------------------------------------

def test_delay_k_follows_the_prior():
    ks = [DelayLine(seed=s).k for s in range(2000)]
    freq = {k: ks.count(k) / len(ks) for k, _ in PRIOR}
    for k, w in PRIOR:
        assert abs(freq[k] - w) < 0.04
    assert DelayLine(seed=11).k == DelayLine(seed=11).k


def test_delay_line_returns_the_state_k_frames_ago(wake):
    d = DelayLine(dist=((3, 1.0),), seed=0)
    assert d.k == 3
    outs = [d.push(copy.deepcopy(w)) for w in wake[:8]]
    assert outs[:3] == [None, None, None]
    assert [o.stamp.frame for o in outs[3:]] == [w.stamp.frame for w in wake[:5]]
    age = (wake[3].stamp.t_sample_qpc_ns - wake[0].stamp.t_sample_qpc_ns) / 1e6
    assert outs[3].perception.frame_age_ms == pytest.approx(age) and outs[3].game.unobservable & Unobs.DELAYED
    d.reset(1)
    assert d.push(copy.deepcopy(wake[0])) is None
    with pytest.raises(ValueError):
        DelayLine(dist=((2, 0.0),))


def test_latency_model_args():
    assert latency_model_args(7) == {"delay_frames": 0, "jitter_frames": 0, "seed": 7}
    a = latency_model_args(2 ** 32 - 1, dist=PRIOR, min_press_frames=2, min_release_frames=3)
    assert a["seed"] == -1 and a["dist"] == [[2, 0.3], [3, 0.5], [4, 0.2]]
    assert (a["min_press_frames"], a["min_release_frames"]) == (2, 3)
    for bad in (dict(delay_frames=61), dict(dist=[(2, 0.0)]), dict(dist=[]), dict(min_press_frames=0)):
        with pytest.raises(ValueError):
            latency_model_args(0, **bad)

    class Link:
        def rpc(self, name, timeout_s=10.0, **args):
            self.call = (name, timeout_s, args)
            return {"ok": True}

    link = Link()
    assert set_action_latency(link, 3, delay_frames=1, jitter_frames=1) == {"ok": True}
    assert link.call == ("input.latency_model", 10.0, {"delay_frames": 1, "jitter_frames": 1, "seed": 3})


def test_degraded_backend_end_to_end():
    states = fx.window(0)
    deg = DegradedOracleBackend(OracleBackend(bosses=[BELL_BEAST], clock=None),
                                ObservabilityFilter(bosses=[BELL_BEAST]))
    k = deg.reset(21)
    outs = [deg.feed(s) for s in states]
    assert outs[:k] == [None] * k and all(o is not None for o in outs[k:])
    assert [o.stamp.frame for o in outs[k:]] == [s["f"] for s in states[:len(states) - k]]
    last = outs[-1]
    assert last.game.unobservable & (Unobs.NOISE | Unobs.DELAYED) == Unobs.NOISE | Unobs.DELAYED
    assert not [p for p, o, t, v in iter_fields(last) if (o == O or t) and v is not None]
    again = DegradedOracleBackend(OracleBackend(bosses=[BELL_BEAST], clock=None),
                                  ObservabilityFilter(bosses=[BELL_BEAST]))
    assert again.reset(21) == k
    outs2 = [again.feed(s) for s in states]
    assert [o.hero.pos.v for o in outs2[k:]] == [o.hero.pos.v for o in outs[k:]]
