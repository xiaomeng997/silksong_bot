"""ObservabilityFilter(VISION_EQUIVALENT): turns an oracle WorldState into what the final vision path could know
(DESIGN §3.9.2 "模拟最终路径": OracleBackend -> ObservabilityFilter -> SimpleNoise -> DelayLine -> brain).

    filt = ObservabilityFilter(bosses=[BELL_BEAST])
    ws_v = filt.apply(oracle_backend.feed(state))       # every frame, in order (it keeps memory)

What it does per frame:
  - O fields -> None and O-only events dropped (WorldState.view("VISION_EQUIVALENT"): FSM states, `can`, game state,
    saved play time, LethalBlock events, pause-gate flags ...).
  - Entities outside the image are hidden: every collider point and the position are projected with the frame's
    camera (ssbot.tools.projector) and visible_frac is the share inside the screen. A hidden entity is replaced by
    a memory track (last seen position and velocity, age in last_seen_ms, no polygons) until a per-kind TTL or its
    ENEMY_KILLED. Measured on the trial run (2 episodes; the oracle exports the view plus a margin): hidden were
    1.7 % / 1.2 % of the Bell Beast's exported frames (112 of 6403, 69 of 5866; by its centre alone it would be 9.8 %),
    37 % / 11 % of the projectile frames (AtkBells flying out of the image), 0.2 % / 0.05 % of the bells.
  - Boss HP -> hit-count estimate. The oracle has no hit-dealt event (see OracleBackend), so a hit is an HP drop of a
    visible entity (Ev.HIT_DEALT, whose amount is O); hp_est = hp_max - hits * hit_damage, sigma = hit_sigma *
    sqrt(hits). Default hit_damage 5: every Hunter nail hit on the Bell Beast took 5 HP (56 of 56 drops, trial run +
    the person's fight), and over both trial episodes (29 + 27 hits, all on a visible boss) the estimate equalled the
    oracle HP in every frame. Wrong for other crests, needle upgrades, tools and spells: callers pass the loadout's
    value.
  - FSM state -> observable phase through the caller's table (BossSpec.phases or phase_map; default "unknown"),
    with t_in_phase counted from the observable phase change.
  - Exact timers (HeroState fields tagged timer=True) -> None until the vision-side timer models exist.
  - playTime -> wall clock: calibrated once from the first frame (standing in for the save-slot read, sigma
    calib_sigma_s; the slot shows h:mm), then advanced by the QPC wall clock while the screen counts (GameManager
    counts unscaled time in PLAYING / ENTERING_LEVEL / EXITING_LEVEL with the inventory closed, GameManager.cs:4223),
    sigma growing by drift per second.
  - bind_ready -> from the silk count (the spool is visible), not CanBind().

Cost on the trial run (13900K, one core): p50 213-269 us, p99 1.1-1.2 ms per frame, most of it the deep copy of
view(). The per-frame visibility kernel is vectorised NumPy; visible_fractions_loop is the same computation as a plain
loop, ready for @numba.njit when numba is installed (it is not, 2026-10) and kept equal to the NumPy path by the tests.
"""
import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from ssbot.core.bosses import BossSpec
from ssbot.core.worldstate import (BIND_SILK, ORACLE, VISION_EQUIVALENT, E, Entity, Ev, HeroState, Kind, PhasePost,
                                   Screen, Src, Unobs, WorldState, timer_fields)
from ssbot.tools.projector import mat4, project

try:
    import numba
except ImportError:
    numba = None

UNKNOWN_PHASE = "unknown"
# Memory-track lifetime per kind (game seconds); placeholders until M3 measures re-detection gaps.
DEFAULT_TTL_S = {Kind.BOSS: 10.0, Kind.ENEMY: 5.0}
OTHER_TTL_S = 0.5
NOT_COUNTING = frozenset((Screen.PAUSE_MENU, Screen.INVENTORY, Screen.MAIN_MENU, Screen.SAVE_SELECT,
                          Screen.MODE_SELECT, Screen.CUTSCENE_VIDEO, Screen.CREDITS, Screen.MSG_CANVAS))
NO_BIND_MODES = frozenset(("hurt", "dash", "cutscene", "bench"))
_TIMERS = timer_fields(HeroState)


def visible_fractions(xy: np.ndarray, ok: np.ndarray, owner: np.ndarray, n: int, w: float, h: float,
                      margin: float = 0.0) -> np.ndarray:
    """Share of each owner's projected points inside [-margin, w + margin] x [-margin, h + margin]."""
    inside = ok & (xy[:, 0] >= -margin) & (xy[:, 0] <= w + margin) & (xy[:, 1] >= -margin) & (xy[:, 1] <= h + margin)
    cnt = np.bincount(owner, minlength=n).astype(np.float64)
    hit = np.bincount(owner, weights=inside.astype(np.float64), minlength=n)
    return np.where(cnt > 0, hit / np.maximum(cnt, 1.0), 0.0)


def visible_fractions_loop(xy: np.ndarray, ok: np.ndarray, owner: np.ndarray, n: int, w: float, h: float,
                           margin: float = 0.0) -> np.ndarray:
    """visible_fractions as a plain loop (the numba candidate)."""
    cnt = np.zeros(n)
    hit = np.zeros(n)
    for i in range(xy.shape[0]):
        o = owner[i]
        cnt[o] += 1.0
        x, y = xy[i, 0], xy[i, 1]
        if ok[i] and -margin <= x <= w + margin and -margin <= y <= h + margin:
            hit[o] += 1.0
    out = np.zeros(n)
    for o in range(n):
        if cnt[o] > 0:
            out[o] = hit[o] / cnt[o]
    return out


if numba is not None:   # pragma: no cover - not installed here
    visible_fractions = numba.njit(cache=True)(visible_fractions_loop)   # noqa: F811


def entity_points(ents: list[Entity]) -> tuple[np.ndarray, np.ndarray]:
    """All collider points and the position of every entity, (N, 2), with the owning entity's index."""
    pts: list[tuple[float, float]] = []
    owner: list[int] = []
    for i, e in enumerate(ents):
        n0 = len(pts)
        pts.append(e.pos.v)
        for poly in e.body_polys:
            pts.extend(poly)
        for b in e.dmg_boxes:
            pts.extend(b.poly)
        owner.extend([i] * (len(pts) - n0))
    if not pts:
        return np.zeros((0, 2)), np.zeros(0, dtype=np.int64)
    return np.asarray(pts, dtype=np.float64), np.asarray(owner, dtype=np.int64)


@dataclass(slots=True)
class _Seen:
    ent: Entity            # the last visible copy (already filtered)
    t: float               # game time it was last visible


@dataclass(slots=True)
class _Phase:
    name: str
    t0: float


class ObservabilityFilter:
    def __init__(self, profile: str = VISION_EQUIVALENT, bosses: Iterable[BossSpec] = (),
                 hp_max: dict[str, float] | None = None, phase_map: dict[str, dict[str, str]] | None = None,
                 hit_damage: float = 5.0, hit_sigma: float = 0.5, ttl_s: dict[Kind, float] | None = None,
                 margin_px: float = 0.0, calib_sigma_s: float = 30.0, drift: float = 1e-3):
        if profile not in (ORACLE, VISION_EQUIVALENT):
            raise ValueError(f"unknown profile {profile!r}")
        self.profile = profile
        specs = {b.type_key: b for b in bosses}
        self.hp_max = {k: b.hp_max for k, b in specs.items() if b.hp_max is not None} | (hp_max or {})
        self.phase_map = {k: dict(b.phases) for k, b in specs.items()} | (phase_map or {})
        self.hit_damage = hit_damage
        self.hit_sigma = hit_sigma
        self.ttl_s = DEFAULT_TTL_S | (ttl_s or {})
        self.margin_px = margin_px
        self.calib_sigma_s = calib_sigma_s
        self.drift = drift
        self.reset()

    def reset(self) -> None:
        self._seen: dict[int, _Seen] = {}
        self._hits: dict[int, int] = {}
        self._killed: set[int] = set()
        self._phase: dict[int, _Phase] = {}
        self._pt: list[float] | None = None      # [live_s, sigma_s, calib value]
        self._q_prev: int | None = None
        self._scene: str | None = None

    # ---- per frame ---------------------------------------------------------------------------------------------

    def apply(self, ws: WorldState) -> WorldState:
        if self.profile == ORACLE:
            return ws
        t = ws.stamp.t_game_s
        out = ws.view(VISION_EQUIVALENT)
        if out.game.scene.v != self._scene:
            self._scene = out.game.scene.v
            self._seen.clear()
            self._hits.clear()
            self._killed.clear()
            self._phase.clear()
        unobs = Unobs.TIMERS_DROPPED | Unobs.PLAYTIME_WALL

        frac = self._visibility(out)
        visible: list[Entity] = []
        for e, fv in zip(out.entities, frac):
            if fv <= 0.0:
                unobs |= Unobs.OFFSCREEN_HIDDEN
                continue
            e.visible_frac = float(fv)
            e.last_seen_ms = 0.0
            visible.append(e)
        vis_ids = {e.id for e in visible}

        events = []
        for ev in out.events:
            if ev.kind == Ev.HIT_DEALT:
                if ev.data.target_id not in vis_ids:
                    continue     # a hit vision cannot see
                self._hits[ev.data.target_id] = self._hits.get(ev.data.target_id, 0) + 1
            elif ev.kind == Ev.ENEMY_KILLED:
                self._killed.add(ev.data.target_id)
            events.append(ev)
        out.events = events

        for e in visible:
            unobs |= self._estimate(e, t)
            self._seen[e.id] = _Seen(e, t)
        ents = list(visible)
        for iid in list(self._seen):
            if iid in vis_ids:
                continue
            seen = self._seen[iid]
            age = t - seen.t
            if iid in self._killed or age > self.ttl_s.get(seen.ent.kind, OTHER_TTL_S):
                del self._seen[iid]
                continue
            ents.append(self._ghost(seen, age))
            unobs |= Unobs.OFFSCREEN_HIDDEN
        out.entities = ents

        for name in _TIMERS:
            setattr(out.hero, name, None)
        silk = out.res.silk.v
        out.res.bind_ready = E(silk >= BIND_SILK and out.hero.mode.v not in NO_BIND_MODES, conf=0.8,
                               src=Src.PREDICTED)
        self._play_time(out)
        out.game.unobservable = int(Unobs(out.game.unobservable) | unobs)
        return out

    # ---- parts -------------------------------------------------------------------------------------------------

    def _visibility(self, ws: WorldState) -> np.ndarray:
        ents = ws.entities
        cam = ws.cam
        if not ents:
            return np.zeros(0)
        if cam.V is None or cam.P is None or cam.screen is None:
            return np.ones(len(ents))       # no camera: nothing to cull against
        pts, owner = entity_points(ents)
        xy, ok = project(pts, mat4(cam.V), mat4(cam.P), cam.viewport, cam.screen)
        return visible_fractions(xy, ok, owner, len(ents), float(cam.screen[0]), float(cam.screen[1]),
                                 self.margin_px)

    def _estimate(self, e: Entity, t: float) -> Unobs:
        flags = Unobs(0)
        tk = e.type_key.v
        hp_max = self.hp_max.get(tk)
        if e.hp_est is not None or hp_max is not None:
            e.hp_est = self._hp(e.id, hp_max)
            flags |= Unobs.HP_FROM_HITS
        if e.phase is not None:
            fsm_state = e.phase.top
            name = self.phase_map.get(tk, {}).get(fsm_state, UNKNOWN_PHASE) if fsm_state else UNKNOWN_PHASE
            ph = self._phase.get(e.id)
            if ph is None or ph.name != name:
                ph = self._phase[e.id] = _Phase(name, t)
            e.phase = PhasePost(topk=[(name, 1.0)], t_in_phase=t - ph.t0)
            flags |= Unobs.PHASE_FROM_TABLE
        return flags

    def _hp(self, iid: int, hp_max: float | None) -> E[float] | None:
        if hp_max is None:
            return None              # no prior for this type: vision cannot tell its HP
        if iid in self._killed:
            return E(0.0, conf=0.9, src=Src.EVENT)
        n = self._hits.get(iid, 0)
        return E(max(0.0, hp_max - n * self.hit_damage), sigma=self.hit_sigma * math.sqrt(n), conf=0.8,
                 src=Src.EVENT)

    def _ghost(self, seen: _Seen, age: float) -> Entity:
        g = seen.ent
        vx, vy = g.vel.v
        spread = math.hypot(vx, vy) * age
        age_ms = age * 1000.0
        conf = max(0.05, 1.0 - age / self.ttl_s.get(g.kind, OTHER_TTL_S))
        return Entity(id=g.id, kind=g.kind, type_key=g.type_key,
                      pos=E(g.pos.v, sigma=g.pos.sigma + spread, conf=conf, src=Src.PREDICTED, age_ms=age_ms),
                      vel=E(g.vel.v, sigma=g.vel.sigma, conf=conf, src=Src.PREDICTED, age_ms=age_ms),
                      facing=g.facing, hp_est=self._hp(g.id, self.hp_max.get(g.type_key.v)) if g.hp_est else None,
                      visible_frac=0.0, last_seen_ms=age_ms)

    def _play_time(self, ws: WorldState) -> None:
        pt = ws.game.play_time
        q = ws.stamp.t_sample_qpc_ns
        counting = ws.game.screen.v not in NOT_COUNTING
        if self._pt is None:
            self._pt = [pt.live_s, self.calib_sigma_s, pt.live_s]
        elif self._q_prev is not None and counting:
            dt = (q - self._q_prev) / 1e9
            if 0.0 < dt < 1.0:      # the game's own guard: unscaledDeltaTime < 1 s
                self._pt[0] += dt
                self._pt[1] += self.drift * dt
        self._q_prev = q
        pt.live_s, pt.sigma_s, pt.last_calib_s = self._pt
        pt.counting = counting
