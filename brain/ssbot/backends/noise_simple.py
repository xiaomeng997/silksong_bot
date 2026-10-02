"""SimpleNoise: seeded perception noise for the simulated final path (DESIGN §3.9.2 "简单噪声").

    noise = SimpleNoise(seed=episode_seed)
    ws = noise.apply(filt.apply(backend.feed(state)))

Per frame: every visible entity misses its detection with probability p_drop[kind]; the tracker then coasts it
(§3.2.7: a lost track coasts on its last velocity): the entity stays, moved by its last velocity over the elapsed game
time, with visible_frac 0, pos conf halved per missed frame and pos sigma grown by the distance coasted; its polygons
and damage boxes move with it. A miss on an entity never detected before drops it. The survivors' positions get
Gaussian noise with sigma_pos[kind] u; the entity's polygons move with it (a detection offset moves the whole box)
and pos.sigma becomes the noise sigma. Memory tracks and hidden entities from the ObservabilityFilter (visible_frac
0) are left alone. The hero's position gets sigma_hero. Velocities get sigma_vel. HUD and phase confusion are not
modelled yet.

Every default is a PLACEHOLDER until M3 measures the vision stack (§3.9.5): position sigma per class from the detector
against projected oracle boxes, miss rate from the detector's recall. Seeded with numpy's PCG64: the same seed and the
same WorldState stream give the same noise.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

import numpy as np

from ssbot.core.worldstate import E, Entity, Kind, Src, Unobs, WorldState

# PLACEHOLDERS (M3 replaces them with measured values)
SIGMA_POS_U = {Kind.BOSS: 0.10, Kind.ENEMY: 0.10, Kind.PROJECTILE: 0.15, Kind.ENEMY_ATTACK: 0.15,
               Kind.HAZARD_DYN: 0.10}
P_DROP = {Kind.BOSS: 0.01, Kind.ENEMY: 0.02, Kind.PROJECTILE: 0.05, Kind.ENEMY_ATTACK: 0.05, Kind.HAZARD_DYN: 0.02}
SIGMA_POS_OTHER_U = 0.10
P_DROP_OTHER = 0.02
SIGMA_HERO_U = 0.05
SIGMA_VEL_U_S = 0.5


@dataclass(slots=True)
class NoiseConfig:
    sigma_pos: Mapping[Kind, float] = field(default_factory=lambda: dict(SIGMA_POS_U))
    p_drop: Mapping[Kind, float] = field(default_factory=lambda: dict(P_DROP))
    sigma_pos_other: float = SIGMA_POS_OTHER_U
    p_drop_other: float = P_DROP_OTHER
    sigma_hero: float = SIGMA_HERO_U
    sigma_vel: float = SIGMA_VEL_U_S


def _shift(poly: list[tuple[float, float]], dx: float, dy: float) -> list[tuple[float, float]]:
    return [(x + dx, y + dy) for x, y in poly]


def _moved(e: Entity, dx: float, dy: float) -> Entity:
    """A copy of e moved by (dx, dy), polygons and boxes included (e itself is not modified)."""
    return replace(e, body_polys=[_shift(p, dx, dy) for p in e.body_polys],
                   dmg_boxes=[replace(b, poly=_shift(b.poly, dx, dy)) for b in e.dmg_boxes])


class SimpleNoise:
    def __init__(self, cfg: NoiseConfig | None = None, seed: int = 0):
        self.cfg = cfg or NoiseConfig()
        self.reset(seed)

    def reset(self, seed: int) -> None:
        self.rng = np.random.default_rng(seed)
        self._last: dict[int, tuple[Entity, float]] = {}    # id -> (last output with a detection or coast, t_game)

    def apply(self, ws: WorldState) -> WorldState:
        """Noise in place (callers pass the filter's private copy) and return ws."""
        cfg = self.cfg
        t = ws.stamp.t_game_s
        live = [e for e in ws.entities if e.visible_frac > 0.0]
        others = [e for e in ws.entities if e.visible_frac <= 0.0]
        n = len(live)
        missed = False
        last: dict[int, tuple[Entity, float]] = {}
        if n:
            p = np.array([cfg.p_drop.get(e.kind, cfg.p_drop_other) for e in live])
            sig = np.array([cfg.sigma_pos.get(e.kind, cfg.sigma_pos_other) for e in live])
            keep = self.rng.random(n) >= p
            dpos = self.rng.standard_normal((n, 2)) * sig[:, None]
            dvel = self.rng.standard_normal((n, 2)) * cfg.sigma_vel
            out = []
            for i, e in enumerate(live):
                if not keep[i]:
                    missed = True
                    prev = self._last.get(e.id)
                    if prev is not None:
                        c = self._coast(*prev, t)
                        out.append(c)
                        last[e.id] = (c, t)
                    continue
                dx, dy = float(dpos[i, 0]), float(dpos[i, 1])
                x, y = e.pos.v
                e.pos = E((x + dx, y + dy), sigma=float(sig[i]), conf=e.pos.conf, src=e.pos.src, age_ms=e.pos.age_ms)
                vx, vy = e.vel.v
                e.vel = E((vx + float(dvel[i, 0]), vy + float(dvel[i, 1])), sigma=cfg.sigma_vel, conf=e.vel.conf,
                          src=e.vel.src, age_ms=e.vel.age_ms)
                e.body_polys = [_shift(poly, dx, dy) for poly in e.body_polys]
                for b in e.dmg_boxes:
                    b.poly = _shift(b.poly, dx, dy)
                out.append(e)
                last[e.id] = (e, t)
            ws.entities = out + others
        self._last = last
        h = ws.hero
        dh = self.rng.standard_normal(2) * cfg.sigma_hero
        hx, hy = h.pos.v
        h.pos = E((hx + float(dh[0]), hy + float(dh[1])), sigma=cfg.sigma_hero, conf=h.pos.conf, src=h.pos.src,
                  age_ms=h.pos.age_ms)
        h.hurtbox = _shift(h.hurtbox, float(dh[0]), float(dh[1]))
        flags = Unobs.NOISE | (Unobs.DETECTION_MISSED if missed else Unobs(0))
        ws.game.unobservable = int(ws.game.unobservable | flags)
        return ws

    @staticmethod
    def _coast(prev: Entity, t_prev: float, t: float) -> Entity:
        """The tracker's prediction for a missed detection: constant velocity from the last output."""
        dt = max(0.0, t - t_prev)
        vx, vy = prev.vel.v
        dx, dy = vx * dt, vy * dt
        c = _moved(prev, dx, dy)
        x, y = prev.pos.v
        c.pos = E((x + dx, y + dy), sigma=prev.pos.sigma + abs(dx) + abs(dy), conf=prev.pos.conf * 0.5,
                  src=Src.PREDICTED, age_ms=prev.pos.age_ms + dt * 1000.0)
        c.vel = E(prev.vel.v, sigma=prev.vel.sigma, conf=prev.vel.conf * 0.5, src=Src.PREDICTED,
                  age_ms=prev.vel.age_ms + dt * 1000.0)
        c.visible_frac = 0.0
        c.last_seen_ms = prev.last_seen_ms + dt * 1000.0
        return c
