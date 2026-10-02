"""The simulated final path (DESIGN §3.9.2): ObservabilityFilter, SimpleNoise, DelayLine, the action-side latency
client and DegradedOracleBackend, on real STATEs of the trial Bell Beast run (tests/worldstate_fixture.py)."""
import copy
import json

import numpy as np
import pytest
from shapely.geometry import Polygon, box as sbox

from ssbot.backends import observability as obs
from ssbot.backends.degraded import DegradedOracleBackend
from ssbot.backends.delay_line import PRIOR, DelayLine, latency_model_args, set_action_latency
from ssbot.backends.noise_simple import NoiseConfig, SimpleNoise
from ssbot.backends.observability import BoxTable, ObservabilityFilter
from ssbot.backends.oracle_backend import OracleBackend
from ssbot.core.bosses import BELL_BEAST, BossSpec
from ssbot.core.worldstate import (O, ORACLE, VISION_BLOCKS, DamageBox, E, Entity, Ev, Event, Hazard, HitDealt, Kind,
                                   Screen, Src, Unobs, WorldState, iter_estimates, iter_fields)
from tests import worldstate_fixture as fx


def oracle_frames(i: int, states: list[dict] | None = None) -> list[WorldState]:
    b = OracleBackend(bosses=[BELL_BEAST], clock=None)
    return [b.feed(s) for s in (states if states is not None else fx.window(i))]


@pytest.fixture(scope="module")
def wake() -> list[WorldState]:
    return oracle_frames(0)


@pytest.fixture(scope="module")
def wake_v(wake) -> list[WorldState]:
    return filtered(wake)


def filtered(wss: list[WorldState], **kw) -> list[WorldState]:
    f = ObservabilityFilter(bosses=kw.pop("bosses", [BELL_BEAST]), **kw)
    return [f.apply(w) for w in wss]


def boss(ws: WorldState) -> Entity | None:
    return next((e for e in ws.entities if e.id == fx.BOSS_IID), None)


# ---- what may survive -------------------------------------------------------------------------------------------

def test_no_oracle_only_value_survives(wake, wake_v):
    for w in wake_v:
        leaks = [p for p, o, timer, v in iter_fields(w) if (o == O or timer) and v is not None]
        assert leaks == []
        assert not [e for e in w.events if e.kind in (Ev.FSM_TRANSITION, Ev.CATASTROPHE, Ev.DISABLE_PAUSE_ON)]
        assert w.game.unobservable & Unobs.TIMERS_DROPPED and w.game.unobservable & Unobs.PLAYTIME_WALL
    assert wake[100].hero.iframes_left is not None and wake[100].entities[0].fsm is not None   # input untouched


def test_no_estimate_field_keeps_src_oracle(wake_v):
    """Every field documented "V = estimate, O = exact" (est=True) is rebuilt: never src ORACLE, never conf 1."""
    seen = set()
    for w in wake_v + filtered(oracle_frames(2)):
        for path, v in iter_estimates(w):
            if isinstance(v, E):
                seen.add(path.split("[")[0])
                assert v.src != Src.ORACLE and v.conf < 1.0, (path, v)
    assert {"game.pause_available", "game.quit_available", "res.bind_ready", "res.pending_dmg",
            "entities"} <= seen


def test_oracle_profile_is_identity(wake):
    f = ObservabilityFilter(profile=ORACLE)
    assert f.apply(wake[0]) is wake[0]
    with pytest.raises(ValueError):
        ObservabilityFilter(profile="X")


# ---- pause / quit availability from vision cues ----------------------------------------------------------------

def test_pause_availability_is_conservative_and_inferred(wake, wake_v):
    blocked = 0
    for w_o, w_v in zip(wake, wake_v):
        pa = w_v.game.pause_available
        assert pa.src == Src.PREDICTED and pa.conf < 1.0
        assert not (pa.v and not w_o.game.pause_available.v)          # never available when the oracle says not
        assert w_v.game.pause_blockers & ~int(VISION_BLOCKS) == 0
        assert not w_v.game.quit_available.v and w_v.game.quit_available.conf == 0.0   # no quit map
        blocked += not w_o.game.pause_available.v
    assert blocked >= 10                                               # the window holds a hit with its blocker


def test_pause_estimate_ignores_the_oracle_blocker_bits():
    states = fx.window(0)
    edited = fx.window(0)
    for s in edited:
        s["pause"].update(blk=16 | 32, dsq=True, preload=True)        # interact / input / save-quit internals
    a, b = filtered(oracle_frames(0, states)), filtered(oracle_frames(0, edited))
    for x, y in zip(a, b):
        assert (x.game.pause_available, x.game.quit_available, x.game.pause_blockers) == \
               (y.game.pause_available, y.game.quit_available, y.game.pause_blockers)


def test_pause_cues_lockout_hit_and_quit_map(wake):
    w = copy.deepcopy(wake[200])
    q = w.stamp.t_sample_qpc_ns / 1e9
    f = ObservabilityFilter(bosses=[BELL_BEAST])
    f.apply(copy.deepcopy(wake[199]))
    w.events = [Event(Ev.PAUSE_ON, w.stamp.frame, w.stamp.t_game_s, None)]
    w.game.screen = E(Screen.PAUSE_MENU)
    v = f.apply(w)
    assert v.game.pause_available.v and v.game.unpause_lockout_until_s == pytest.approx(q + 0.3)
    w2 = copy.deepcopy(wake[201])
    w2.events = [Event(Ev.PAUSE_OFF, w2.stamp.frame, w2.stamp.t_game_s, None)]
    v2 = f.apply(w2)
    assert not v2.game.pause_available.v and v2.game.pause_blockers & 4          # PAUSE_LOCKOUT

    class QM:
        key = None

        def p_pause(self, scene, key):
            self.key = key
            return 1.0 if key == "free" else 0.0

        def p_quit(self, scene, key):
            return 0.995

    qm = QM()
    f = ObservabilityFilter(bosses=[BELL_BEAST], quit_map=qm)
    for w in wake[:20]:
        v = f.apply(copy.deepcopy(w))
    i = 20
    v = f.apply(copy.deepcopy(wake[i]))
    assert v.game.pause_available.v and v.game.quit_available.v and v.game.quit_available.conf == obs.CONF_MAX
    talk = copy.deepcopy(wake[i + 1])
    talk.game.screen = E(Screen.DIALOG)                             # a dialogue box (oracle: pause.interact)
    v = f.apply(talk)
    assert qm.key == "interact" and not v.game.pause_available.v and v.game.pause_blockers & 512


def test_slow_motion_blocks_pause_without_a_freeze_event(wake, wake_v):
    """The trial run's case: BossDeathSlow (time scale 0.05) running on across a savestate load, so the filter (reset
    per episode) never saw its FREEZE start. The world visibly runs slow: TIME_SLOWED until SLOW_HOLD_S after."""
    i = next(i for i in range(len(wake_v) - 40) if all(w.game.pause_available.v for w in wake_v[i:i + 40]))
    ws = [copy.deepcopy(w) for w in wake[i:i + 40]]
    for w in ws:
        w.events = []
    q0, t0 = ws[0].stamp.t_sample_qpc_ns, ws[0].stamp.t_game_s
    for k, w in enumerate(ws):                                   # 5 % speed (as in BossDeathSlow), then full speed
        dq = (w.stamp.t_sample_qpc_ns - q0) / 1e9
        w.stamp.t_game_s = t0 + (0.05 * dq if k < 20 else ws[19].stamp.t_game_s - t0 + dq - (
            ws[19].stamp.t_sample_qpc_ns - q0) / 1e9)
    f = ObservabilityFilter(bosses=[BELL_BEAST])
    out = [f.apply(w) for w in ws]
    slow_end = ws[19].stamp.t_sample_qpc_ns / 1e9 + obs.SLOW_HOLD_S
    assert out[0].game.pause_blockers & 2                                   # no speed reading yet: as if slowed
    for w, v in zip(ws[1:], out[1:]):
        q = w.stamp.t_sample_qpc_ns / 1e9
        assert bool(v.game.pause_blockers & 2) == (q < slow_end)            # TIME_SLOWED
        assert v.game.pause_available.v == (q >= slow_end)
    assert not out[-1].game.pause_blockers


# ---- damage boxes ---------------------------------------------------------------------------------------------

def test_box_activity_does_not_depend_on_the_fsm(wake):
    """With the box table known, the boss's vision boxes are the same whatever its Control state, collider enables
    and which child colliders the oracle exports, and all of them are active."""
    table = BoxTable()
    f0 = ObservabilityFilter(bosses=[BELL_BEAST], box_table=table)
    for w in wake:
        f0.apply(w)
    states = fx.window(0)
    edited = fx.window(0)
    for s in edited:
        for e in s["ents"]:
            if e["iid"] == fx.BOSS_IID:
                e["colliders"] = [dict(c, enabled=not c["enabled"]) for c in e["colliders"][:1]]   # root box only
                for fs in e["fsms"]:
                    fs["state"] = "Idle"
    a = filtered(oracle_frames(0, states), box_table=table)
    b = filtered(oracle_frames(0, edited), box_table=table)
    n = 0
    for x, y in zip(a, b):
        bx, by = boss(x), boss(y)
        if bx is None or bx.visible_frac == 0:
            continue
        assert by is not None
        got = [(d.poly, d.active, d.flags) for d in by.dmg_boxes]
        assert [(d.poly, d.active, d.flags) for d in bx.dmg_boxes] == got
        assert len(bx.dmg_boxes) == len(table.t["Bone Beast"]) >= 2 and all(d.active for d in bx.dmg_boxes)
        n += 1
    assert n > 100


def test_box_table_covers_the_hit_contacts(wake, wake_v):
    """The logged boss hit (56777): the hero hurtbox touches a vision-view box of the source."""
    i = next(i for i, w in enumerate(wake) if w.stamp.frame == 56777)
    hit = next(e.data for e in wake[i].events if e.kind == Ev.HIT_TAKEN)
    hb = Polygon(wake[i].hero.hurtbox)
    ent = next(e for e in wake_v[i].entities if e.id == hit.source_id)
    assert any(Polygon(d.poly).intersects(hb) for d in ent.dmg_boxes if d.active)


def test_box_table_mirrors_with_the_flip():
    t = BoxTable()
    t.learn("X", (10.0, 0.0), False, [DamageBox(poly=[(11.0, 0.0), (13.0, 0.0), (13.0, 1.0)], hazard=Hazard.ENEMY,
                                                dmg_seq=(1,))])
    right = t.place("X", (20.0, 5.0), False)[0].poly
    left = t.place("X", (20.0, 5.0), True)[0].poly
    assert min(x for x, _ in right) == 21.0 and max(x for x, _ in left) == 19.0 and min(y for _, y in left) == 5.0
    again = BoxTable.from_dict(json.loads(json.dumps(t.to_dict())))           # an offline table round-trips
    assert again.place("X", (20.0, 5.0), True) == t.place("X", (20.0, 5.0), True)


# ---- visibility -------------------------------------------------------------------------------------------------

def test_a_polygon_across_the_image_is_visible(wake):
    """The review's case: an acid band 120 u wide through the hero, every vertex (and pos) outside the image."""
    w = copy.deepcopy(wake[-1])
    hx, hy = w.hero.pos.v
    band = [(hx - 60, hy - 1), (hx + 60, hy - 1), (hx + 60, hy + 1), (hx - 60, hy + 1)]
    acid = Entity(id=-5, kind=Kind.HAZARD_DYN, type_key=E("Acid Band"), pos=E((hx, hy - 40)), body_polys=[band],
                  dmg_boxes=[DamageBox(poly=band, active=True, hazard=Hazard.ACID,
                                       flags=frozenset({"IGNORES_IFRAMES"}))],
                  pos_transform=(hx, hy - 40))
    w.entities.append(acid)
    out = ObservabilityFilter(bosses=[BELL_BEAST]).apply(w)
    e = next(x for x in out.entities if x.id == -5)
    assert 0.0 < e.visible_frac < 0.5 and e.dmg_boxes and all(d.active for d in e.dmg_boxes)
    assert Polygon(e.dmg_boxes[0].poly).intersects(Polygon(w.hero.hurtbox))


def test_clip_kernel_matches_the_reference_and_shapely():
    rng = np.random.default_rng(3)
    polys, owner = [], []
    for o in range(30):
        k = int(rng.integers(1, 3))
        while k:
            n = int(rng.integers(3, 9))
            c = rng.uniform(-300, 1500, 2)
            ang = np.sort(rng.uniform(0, 2 * np.pi, n))
            r = rng.uniform(5, 400, n)                                  # star-shaped, often concave
            p = np.stack([c[0] + r * np.cos(ang), c[1] + r * np.sin(ang)], axis=1)
            if Polygon(p).is_valid:                                     # colliders are simple polygons
                polys.append(p)
                owner.append(o)
                k -= 1
    polys.append(np.array([[10.0, 10.0], [50.0, 10.0]]))                # an edge collider: point share
    owner.append(30)
    xy = np.concatenate(polys)
    start = np.cumsum([0] + [len(p) for p in polys]).astype(np.int64)
    rect = np.array([0.0, 0.0, 1280.0, 720.0])
    a = obs.clip_fractions(xy, start, np.asarray(owner, dtype=np.int64), 32, rect)
    b = obs.clip_fractions_ref(xy, start, np.asarray(owner, dtype=np.int64), 32, rect)
    assert np.allclose(a, b, atol=1e-9)
    img = sbox(0, 0, 1280, 720)
    for o in range(30):
        ps = [Polygon(p) for p, ow in zip(polys, owner) if ow == o]
        full = sum(p.area for p in ps)
        vis = sum(p.intersection(img).area for p in ps)
        assert a[o] == pytest.approx(vis / full, abs=1e-6)
    assert a[30] == 1.0 and a[31] == 0.0


# ---- hidden entities, ghosts ------------------------------------------------------------------------------------

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
    b0 = boss(seen)
    assert b0.visible_frac == 1.0
    away = _camera_away(wake[i + 1], 200.0)
    away.events.append(Event(Ev.HIT_DEALT, away.stamp.frame, away.stamp.t_game_s,
                             HitDealt(fx.BOSS_IID, "Bone Beast", 5.0, 145.0)))
    out = f.apply(away)
    ghost = boss(out)
    assert ghost is not None and ghost.visible_frac == 0.0 and not ghost.hidden and ghost.last_seen_ms > 0
    assert ghost.pos.v == b0.pos.v and ghost.pos.src == Src.PREDICTED and 0.0 < ghost.pos.conf < 1.0
    assert ghost.body_polys == [] and ghost.dmg_boxes == [] and ghost.phase is None
    assert ghost.hp_est.v == 150.0                      # a hit on a hidden boss is not counted
    assert not [e for e in out.events if e.kind == Ev.HIT_DEALT]
    assert out.game.unobservable & Unobs.OFFSCREEN_HIDDEN
    late = _camera_away(wake[i + 2], 200.0)
    late.stamp.t_game_s += 11.0                         # the boss TTL (10 s of game time)
    assert boss(f.apply(late)) is None


def test_vanishing_in_view_is_not_a_ghost(wake):
    """The boss leaves the export while fully in view (it dug in): hidden, position unknown, no boxes."""
    i = next(i for i, w in enumerate(wake) if boss(w) is not None and boss(w).dmg_boxes)
    f = ObservabilityFilter(bosses=[BELL_BEAST])
    for w in wake[i:i + 3]:
        f.apply(w)
    gone = copy.deepcopy(wake[i + 3])
    gone.entities = [e for e in gone.entities if e.id != fx.BOSS_IID]
    out = f.apply(gone)
    b = boss(out)
    assert b is not None and b.hidden and b.visible_frac == 0.0 and b.pos.conf == 0.0 and b.dmg_boxes == []
    assert b.phase.top == obs.HIDDEN_PHASE and out.game.unobservable & Unobs.VANISHED_IN_VIEW
    assert not out.game.unobservable & Unobs.OFFSCREEN_HIDDEN


def test_oracle_hidden_boss_is_kept_past_the_ttl(wake):
    i = next(i for i, w in enumerate(wake) if boss(w) is not None)
    f = ObservabilityFilter(bosses=[BELL_BEAST])
    f.apply(wake[i])
    for k, dt in enumerate((0.5, 12.0, 25.0)):
        w = copy.deepcopy(wake[i + 1 + k])
        w.stamp.t_game_s += dt
        b = boss(w)
        b.hidden, b.dmg_boxes, b.body_polys, b.render_box, b.visible_frac = True, [], [], None, 0.0
        out = f.apply(w)
        assert boss(out).hidden and boss(out).pos.conf == 0.0
    w = copy.deepcopy(wake[i + 5])                                    # it comes back up
    out = f.apply(w)
    assert boss(out).visible_frac > 0 and not boss(out).hidden and boss(out).phase.t_in_phase == 0.0


def test_off_screen_changes_are_not_seen(wake):
    """A ghost that digs in off-screen stays a ghost (vision did not see it go); a boss that dug in in view and comes
    back up off-screen stays hidden (vision did not see it come back)."""
    i = next(i for i, w in enumerate(wake) if boss(w) is not None)
    f = ObservabilityFilter(bosses=[BELL_BEAST])
    f.apply(wake[i])
    away = _camera_away(wake[i + 1], 200.0)
    assert boss(f.apply(away)).hidden is False                      # off-screen: a ghost
    under = _camera_away(wake[i + 2], 200.0)
    b = boss(under)
    b.hidden, b.dmg_boxes, b.body_polys, b.render_box = True, [], [], None
    g = boss(f.apply(under))
    assert not g.hidden and g.pos.conf > 0 and g.visible_frac == 0.0
    f = ObservabilityFilter(bosses=[BELL_BEAST])
    f.apply(wake[i])
    dug = copy.deepcopy(wake[i + 1])
    dug.entities = [e for e in dug.entities if e.id != fx.BOSS_IID]
    assert boss(f.apply(dug)).hidden                                  # dug in in view
    up = _camera_away(wake[i + 2], 200.0)                             # back up, but off-screen
    h = boss(f.apply(up))
    assert h.hidden and h.pos.conf == 0.0


def test_a_bell_put_away_in_view_is_dropped(wake):
    i = next(i for i, w in enumerate(wake) if boss(w) is not None)
    w = copy.deepcopy(wake[i])
    hx, hy = w.hero.pos.v
    poly = [(hx - 1, hy - 1), (hx + 1, hy - 1), (hx + 1, hy + 1), (hx - 1, hy + 1)]
    w.entities.append(Entity(id=-7, kind=Kind.PROJECTILE, type_key=E("Bell"), pos=E((hx, hy)), body_polys=[poly],
                             dmg_boxes=[DamageBox(poly=poly, active=True, hazard=Hazard.ENEMY)],
                             pos_transform=(hx, hy)))
    f = ObservabilityFilter(bosses=[BELL_BEAST])
    assert any(e.id == -7 for e in f.apply(w).entities)
    w2 = copy.deepcopy(wake[i + 1])
    out = f.apply(w2)
    assert not any(e.id == -7 for e in out.entities)


# ---- estimates ----------------------------------------------------------------------------------------------

def test_boss_hp_from_counted_hits(wake, wake_v):
    first = next(w for w in wake_v if boss(w) is not None)
    assert boss(first).hp_est.v == 150.0 and boss(first).hp_est.src == Src.EVENT
    hit = next(w for w in wake_v if any(e.kind == Ev.HIT_DEALT for e in w.events))
    assert hit.stamp.frame == 56818
    ev = next(e for e in hit.events if e.kind == Ev.HIT_DEALT)
    assert ev.data.amount is None and ev.data.target_id == fx.BOSS_IID
    est = boss(hit).hp_est
    assert est.v == 145.0 and est.sigma == pytest.approx(0.5)
    for w_o, w_v in zip(wake, wake_v):
        if boss(w_o) is not None and boss(w_v) is not None and boss(w_v).visible_frac > 0:
            assert boss(w_v).hp_est.v == boss(w_o).hp_est.v


def test_hp_uses_the_damage_of_the_attack(wake):
    i = next(i for i, w in enumerate(wake) if boss(w) is not None)
    f = ObservabilityFilter(bosses=[BELL_BEAST], attack_damage={"Silk Spear": 15.0})
    f.apply(wake[i])
    w = copy.deepcopy(wake[i + 1])
    w.events.append(Event(Ev.HIT_DEALT, w.stamp.frame, w.stamp.t_game_s,
                          HitDealt(fx.BOSS_IID, "Bone Beast", 15.0, 135.0, attack="Silk Spear")))
    assert boss(f.apply(w)).hp_est.v == 135.0
    w = copy.deepcopy(wake[i + 2])                       # no attack name: the hero's clip (the default table)
    w.events.append(Event(Ev.HIT_DEALT, w.stamp.frame, w.stamp.t_game_s,
                          HitDealt(fx.BOSS_IID, "Bone Beast", 15.0, 120.0, hero_anim="NeedleThrow Throwing")))
    assert boss(f.apply(w)).hp_est.v == 120.0
    w = copy.deepcopy(wake[i + 3])                       # a slash landing as a throw starts: still 5
    w.events.append(Event(Ev.HIT_DEALT, w.stamp.frame, w.stamp.t_game_s,
                          HitDealt(fx.BOSS_IID, "Bone Beast", 5.0, 115.0, hero_anim="NeedleThrow AnticA")))
    assert boss(f.apply(w)).hp_est.v == 115.0


def test_kill_zeroes_and_drops_the_track():
    out = filtered(oracle_frames(2), hit_damage=5.0)
    i = next(i for i, w in enumerate(out) if any(e.kind == Ev.ENEMY_KILLED for e in w.events))
    assert out[i].stamp.frame == 69029
    assert boss(out[i - 1]) is not None and boss(out[i - 1]).hp_est.v == 145.0   # one hit seen in this window
    assert all(boss(w) is None for w in out[i:])


def test_unknown_types_get_no_hp(wake):
    out = filtered(wake, bosses=[])
    assert all(e.hp_est is None for w in out for e in w.entities)


def test_phase_from_the_callers_table(wake, wake_v):
    assert {boss(w).phase.top for w in wake_v if boss(w) is not None and boss(w).visible_frac > 0} == {"unknown"}
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


def test_play_time_follows_the_game_timer_rule(wake):
    f = ObservabilityFilter(bosses=[BELL_BEAST], calib_sigma_s=30.0, drift=1e-3)
    ws = [copy.deepcopy(w) for w in wake[:6]]
    a = f.apply(ws[0]).game.play_time
    assert a.live_s == wake[0].game.play_time.live_s and a.sigma_s == 30.0 and a.saved_s is None
    b = f.apply(ws[1]).game.play_time
    dt = (wake[1].stamp.t_sample_qpc_ns - wake[0].stamp.t_sample_qpc_ns) / 1e9
    assert b.live_s == pytest.approx(a.live_s + dt) and b.sigma_s == pytest.approx(30.0 + 1e-3 * dt)
    expect = {Screen.PAUSE_MENU: False, Screen.TRANSITION: False, Screen.FADE: True, Screen.MSG_CANVAS: True}
    prev = b.live_s
    for w, (screen, counts) in zip(ws[2:], expect.items()):
        w.game.screen = E(screen)
        c = f.apply(w).game.play_time
        assert c.counting == counts and (c.live_s > prev) == counts, screen
        prev = c.live_s


def test_bind_ready_and_pending_damage(wake):
    w = copy.deepcopy(wake[-1])
    w.res.silk = E(9)
    w.hero.mode = E("ground")
    out = ObservabilityFilter().apply(w)
    assert out.res.bind_ready.v is True and out.res.pending_dmg.v == 0 and out.res.pending_dmg.src == Src.PREDICTED
    w.res.silk = E(8)
    w.res.status = frozenset({"ACID"})
    w.res.pending_dmg = E(3)
    out = ObservabilityFilter().apply(w)
    assert out.res.bind_ready.v is False and out.res.pending_dmg.conf == 0.0
    assert out.res.pending_dmg.v == w.res.hp.v + w.res.blue.v                # unknown reads as lethal
    w.res.status = frozenset({"MAGGOTED"})                                    # no damage: nothing pending
    assert ObservabilityFilter().apply(w).res.pending_dmg.v == 0


# ---- noise ------------------------------------------------------------------------------------------------

def _visible_boss_frame(wake_v) -> WorldState:
    return next(w for w in wake_v if boss(w) is not None and boss(w).visible_frac > 0 and boss(w).dmg_boxes
                and abs(boss(w).vel.v[0]) > 1.0)


def test_noise_is_seeded_and_moves_polygons_with_the_position(wake_v):
    base = _visible_boss_frame(wake_v)
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
    assert len(out.entities) == len(live) + 1          # a miss on a never-detected entity drops it
    xy = np.array([e.pos.v for e in live])
    assert np.allclose(xy.std(axis=0), 0.2, atol=0.015)
    assert out.entities[-1].id == -1 and out.entities[-1].pos.v == (5.0, 5.0)   # memory tracks untouched


def test_a_missed_detection_coasts(wake_v):
    base = _visible_boss_frame(wake_v)
    cfg = NoiseConfig(sigma_pos={}, p_drop={}, sigma_pos_other=0.0, p_drop_other=0.0, sigma_vel=0.0)
    n = SimpleNoise(cfg, seed=0)
    first = n.apply(copy.deepcopy(base))
    b0 = boss(first)
    n.cfg = NoiseConfig(sigma_pos={}, p_drop={Kind.BOSS: 1.0}, sigma_pos_other=0.0, p_drop_other=0.0, sigma_vel=0.0)
    nxt = copy.deepcopy(base)
    nxt.stamp.t_game_s += 0.1
    out = n.apply(nxt)
    c = boss(out)
    assert c is not None and c.visible_frac == 0.0 and c.pos.src == Src.PREDICTED and c.pos.conf == b0.pos.conf / 2
    dx = b0.vel.v[0] * 0.1
    assert c.pos.v[0] == pytest.approx(b0.pos.v[0] + dx)
    assert c.dmg_boxes and np.allclose(np.array(c.dmg_boxes[0].poly)[:, 0] - np.array(b0.dmg_boxes[0].poly)[:, 0], dx)
    assert out.game.unobservable & Unobs.DETECTION_MISSED


# ---- delay line and the action-side client -------------------------------------------------------------------

def test_delay_k_follows_the_prior():
    ks = [DelayLine(seed=s).k for s in range(2000)]
    freq = {k: ks.count(k) / len(ks) for k, _ in PRIOR}
    for k, w in PRIOR:
        assert abs(freq[k] - w) < 0.04
    assert DelayLine(seed=11).k == DelayLine(seed=11).k


def test_delay_line_returns_the_state_k_frames_ago_and_exposes_the_live_frame(wake):
    d = DelayLine(dist=((3, 1.0),), seed=0)
    assert d.k == 3 and d.live_frame is None and not d.ready
    outs = []
    for w in wake[:8]:
        outs.append(d.push(copy.deepcopy(w)))
        assert d.live_frame == w.stamp.frame
    assert outs[:3] == [None, None, None] and d.ready
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
    assert deg.live_frame == states[-1]["f"] == outs[-1].stamp.frame + k
    last = outs[-1]
    assert last.game.unobservable & (Unobs.NOISE | Unobs.DELAYED) == Unobs.NOISE | Unobs.DELAYED
    assert not [p for p, o, t, v in iter_fields(last) if (o == O or t) and v is not None]
    again = DegradedOracleBackend(OracleBackend(bosses=[BELL_BEAST], clock=None),
                                  ObservabilityFilter(bosses=[BELL_BEAST]))
    assert again.reset(21) == k
    outs2 = [again.feed(s) for s in states]
    assert [o.hero.pos.v for o in outs2[k:]] == [o.hero.pos.v for o in outs[k:]]
