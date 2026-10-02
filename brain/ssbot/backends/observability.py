"""ObservabilityFilter(VISION_EQUIVALENT): turns an oracle WorldState into what the final vision path could know
(DESIGN §3.9.2 "模拟最终路径": OracleBackend -> ObservabilityFilter -> SimpleNoise -> DelayLine -> brain).

    filt = ObservabilityFilter(bosses=[BELL_BEAST])
    ws_v = filt.apply(oracle_backend.feed(state))       # every frame, in order (it keeps memory)

Rule: no value in the output may depend on something pixels cannot show. Per frame:
  - O fields -> None and O-only events dropped (WorldState.view("VISION_EQUIVALENT"): FSM states, `can`, game state,
    saved play time, LethalBlock events, pause-gate flags, transforms, collider names ...).
  - Visibility: each entity's image extent (its render_aabb plus its active damage boxes when exported, else its
    enabled colliders) is projected with the frame's camera (ssbot.tools.projector) and clipped to the camera viewport; visible_frac is the visible
    area share. An entity with neither (no drawn root renderer, no enabled collider) is not drawn.
  - Entities that stop being visible: if at least half of it was visible in its last visible frame and it is not
    now projected outside the image (oracle ents[].hidden, not drawn any more, or gone from the export), it vanished
    in view: no tracker loses a mostly visible object over the edge in one frame -> a boss or enemy stays as a hidden
    entity (hidden=True, pos conf 0, no boxes, phase "hidden": "it dug in, position unknown") while the oracle still
    exports it hidden, else until the TTL; any other kind is dropped (a bell put away, a projectile that hit
    something). Otherwise vision lost it over the image edge -> memory track ("ghost": last seen position and
    velocity, age in last_seen_ms, no polygons) until a per-kind TTL or its ENEMY_KILLED. A ghost stays a ghost and
    a hidden entity hidden until it is visible again: vision sees neither a dig-in off-screen nor a re-emergence
    off-screen.
  - Damage boxes: the box activity and which child colliders exist are FSM timing (trial run: the Bell Beast's
    charge polygon exists only in Charge Antic / Charge, its leap polygon only in Leap Out / Descending). Until the
    hitbox tables of W2 are wired in, every visible entity carries its type's box table (BoxTable: one axis-aligned
    box per collider, the union of every damage collider of that type, relative to Entity.pos and mirrored with
    flipX), all active. The default is the shipped offline table (knowledge/1.0.30000/enemies/box_tables.json, built
    by ssbot.tools.box_table_build from live run instance 0, i0_000 + i0_001: 516,967 STATEs), frozen, so nothing
    about the boxes depends on the current run; only types missing from it are learnt online, where a collider's
    first appearance still shows FSM timing.
  - Pause / quit availability and blockers are rebuilt from vision cues (DESIGN §3.7.5): screen mode (a dialogue
    box blocks); the 0.3 s real-time lockout after its own PAUSE_ON/OFF edges; < 0.3 s since a hit taken (trial
    run: the first pausable frame after a hit came 0.215-0.250 s later in 99 of 101 hits; probe P7: 0.25 s); a
    running freeze (FREEZE start/end) or a world visibly running slow, which catches the slow motion whose start the
    filter never saw, e.g. BossDeathSlow running on across a savestate load. The speed stands in for a motion-based
    estimate: game time over real time summed over the last SLOW_WINDOW frames (not the exact per-frame time scale),
    so an onset is seen late (a drop to 0.05 x shows on its second slow frame) and the first SLOW_WINDOW frames, with
    no full reading yet, count as slowed; TIME_SLOWED is held SLOW_HOLD_S after the last slow reading; a hazard death until 1.0 s after
    the hazard respawn; < 0.5 s after a scene entry or a return to gameplay; the hurt mode. Without a quit map,
    quit_available is False with conf 0 except in the pause menu with a menu read; with one (quit_map.p_pause /
    p_quit(scene, key), ssbot.safety.quit_map keys) both need P >= min_p. The blockers carry only VISION_BLOCKS
    bits. src PREDICTED.
  - Boss HP -> hit-count estimate: a HIT_DEALT on a visible entity counts (amount is O); hp_est = hp_max - sum of
    the per-attack damage (attack_damage[HitDealt.src], else [attack], else the longest key prefixing
    HitDealt.hero_anim, else hit_damage), sigma = hit_sigma * sqrt(hits); a hit the hero did not deal (by_hero False)
    is not priced by the hero's clip and adds a full hit_damage of sigma. Defaults: 5 per hit, 15 for a hit during
    "NeedleThrow Throwing" (Silk Spear): Hunter crest, needle level 0 (DEFAULT_ATTACK_DAMAGE).
  - FSM state -> observable phase through the caller's table (BossSpec.phases or phase_map; default "unknown"),
    with t_in_phase counted from the observable phase change.
  - Exact timers (HeroState fields tagged timer=True) -> None until the vision-side timer models exist.
  - playTime -> wall clock: calibrated once from the first frame (standing in for the save-slot read, sigma
    calib_sigma_s; the slot shows h:mm), then advanced by the QPC wall clock while the game would count it
    (GameManager.IncreaseGameTimer, GameManager.cs:4223: PLAYING / ENTERING_LEVEL / EXITING_LEVEL with the inventory
    closed, unscaledDeltaTime < 1 s): not in the pause menu, inventory, menus, loads (TRANSITION) or video cutscenes;
    a message canvas counts unless the filter's own pause edges say the game is paused.
  - bind_ready from the silk count (the spool is visible); pending_dmg 0 when no damage status is visible, else
    unknown: conf 0 and v = health + blue (lethal by itself, as the oracle path reports an unbounded tag).

Measured with ObservabilityFilter reset at every savestate load and a BoxTable learnt from the trial run, on the
live Bell Beast run 20261001_122249 (rec i<N>_000 / _001: 200 savestate episodes, 2,148,565 STATEs; held out from
the pause cues and SLOW_RATE / SLOW_HOLD_S, which were set on the trial run, but not from the 15-HP Silk Spear value),
the trial run 20261001_121446 (26,892 STATEs) and the person's fight (human/20260930_210337 frames 64275-68397):
  - Pause: vision says pausable while the oracle's gate is closed in 0 of 2,146,430 PLAYING frames (live; trial 0,
    person 0; without the slow-motion cue 3,458 live frames, all TIME_SLOWED). The cues close the gate in 5.8 % of
    the frames the oracle has it open (116,404 of 2,009,327; trial 5.6 %, person 0.1 %).
  - Visibility: the boss is outside the image in 6,704 of 932,222 exported frames (0.72 %; the old any-vertex rule
    said 10,552): 4,308 as a ghost, 2,396 still hidden (it came back up off-screen). Of the 1,216,343 frames the
    boss was not exported (underground, before the wake, after the kill) the vision view holds it hidden (dug in
    while in view, position unknown) in 967,738 and as a ghost in 103,135 (it dug in off-screen or at the image
    edge, so vision last saw it there; mean pos conf 0.88).
  - Damage boxes: of 8,461 hits taken, the vision boxes touch the hero hurtbox in the hit frame in 8,213 (97.1 %),
    every one of the 7,562 the oracle's own active boxes touch included, and in the frame before in 32 more; 209
    miss both frames by at most 0.56 u (p50 0.10 u: fast bells and charges, the contact fell between frames; the
    oracle's boxes miss by the same distance), 7 came from the boss bursting out of the ground while not exported.
  - Boss HP: zero error in every frame the boss was visible (live 925,463 frames, 4,541 hits of which 460 Silk
    Spear; trial 12,177; person 1,737).
  - Cost per STATE (13900K, two measuring processes in parallel): p50 145-148 us, p99 273-289 us (OracleBackend
    p50 95-96 us, p99 172-186 us).
The per-frame visibility kernel (polygon clipping against the viewport rectangle, Sutherland-Hodgman, shoelace areas)
runs under @numba.njit; clip_fractions_ref is the plain reference the tests hold it to, and shapely the external
check.
"""
import json
import math
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

import numpy as np

from ssbot.core.bosses import BossSpec
from ssbot.core.worldstate import (BIND_SILK, ORACLE, VISION_BLOCKS, VISION_EQUIVALENT, DamageBox, E, Entity, Ev,
                                   Hazard, HeroState, HitDealt, Kind, PauseBlock, PhasePost, Screen, Src, Unobs,
                                   WorldState, timer_fields, unknown)
from ssbot.tools.projector import mat4, project

try:
    import numba
except ImportError:   # pragma: no cover
    numba = None

# Damage per attack for the hit-count HP estimate, keyed by HitDealt.attack or by a prefix of the hero's animation
# clip at the hit (the bot knows what it did). Hunter crest, needle level 0 (the M2 loadout), live Bell Beast run
# 20261001_122249: the 460 hits dealt with "NeedleThrow Throwing" (Silk Spear) took 15 HP, the other 4,081 took 5 HP.
DEFAULT_ATTACK_DAMAGE = {"NeedleThrow Throwing": 15.0}
DEFAULT_BOX_TABLE = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "box_tables.json"
UNKNOWN_PHASE = "unknown"
HIDDEN_PHASE = "hidden"
# Memory-track lifetime per kind (game seconds); placeholders until M3 measures re-detection gaps.
DEFAULT_TTL_S = {Kind.BOSS: 10.0, Kind.ENEMY: 5.0}
OTHER_TTL_S = 0.5
KEEP_HIDDEN = frozenset((Kind.BOSS, Kind.ENEMY))   # kinds kept as hidden entities when they vanish inside the image
VANISH_FRAC = 0.5      # left the export while at least this share was visible: it vanished in view (a tracker
#                        could not have lost it over the edge in one frame)
NOT_COUNTING = frozenset((Screen.PAUSE_MENU, Screen.INVENTORY, Screen.MAIN_MENU, Screen.SAVE_SELECT,
                          Screen.MODE_SELECT, Screen.TRANSITION, Screen.CUTSCENE_VIDEO, Screen.CREDITS))
GAMEPLAY = frozenset((Screen.PLAYING, Screen.PLAYING_HUD_HIDDEN))
NO_BIND_MODES = frozenset(("hurt", "dash", "cutscene", "bench"))
NO_DAMAGE_STATUS = frozenset(("MAGGOTED",))   # statuses that deal no damage (maggots block binding)
_TIMERS = timer_fields(HeroState)

# Vision-side pause cues (DESIGN §3.7.5; real seconds unless noted)
PAUSE_LOCKOUT_S = 0.3        # WaitForSecondsRealtime(0.3f) after every pause / unpause (m0:C12)
HIT_BLOCK_S = 0.3            # after a hit taken (disablePause until the damage freeze ends; measured <= 0.250 s)
HAZARD_BLOCK_S = 1.0         # after a hazard respawn (FinishedEnteringScene clears disablePause ~0.3 s later, m0:N9)
ENTRY_BLOCK_S = 0.5          # after a scene entry (HUDCamera PreventPause 0.5 s, m0:N14)
HURT1_S = 1.2                # quit-map key "hurt1" ends here (i-frames)
FREEZE_MAX_S = 5.0           # a freeze start without its end stops counting after this long (RaceWinSlow 3.8 s)
SLOW_RATE = 0.75             # game time over real time below this over the window: the world visibly slows down
SLOW_WINDOW = 4              # frames the speed estimate averages over (its detection latency)
SLOW_HOLD_S = 0.1            # TIME_SLOWED is kept this long after the last slow reading (the ramp back to full speed)
PAUSE_CONF = 0.9             # pause_available conf without a quit map
CONF_MAX = 0.99              # an inferred availability is never certain (est fields keep conf < 1)


class QuitMapLike(Protocol):
    def p_pause(self, scene: str, key: str) -> float | None: ...
    def p_quit(self, scene: str, key: str) -> float | None: ...


# ---- visibility kernel ----------------------------------------------------------------------------------------

def _clip_area(px: np.ndarray, py: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> float:
    """Area of the polygon (px, py) inside the rectangle [x0, x1] x [y0, y1] (Sutherland-Hodgman, shoelace)."""
    n = px.shape[0]
    cap = 16 * n + 16             # each of the 4 stages at most doubles the vertex count
    ax = np.empty(cap)
    ay = np.empty(cap)
    bx = np.empty(cap)
    by = np.empty(cap)
    for i in range(n):
        ax[i] = px[i]
        ay[i] = py[i]
    m = n
    for edge in range(4):
        k = 0
        for i in range(m):
            sx, sy = ax[i], ay[i]
            ex, ey = ax[(i + 1) % m], ay[(i + 1) % m]
            if edge == 0:
                s_in, e_in = sx >= x0, ex >= x0
            elif edge == 1:
                s_in, e_in = sx <= x1, ex <= x1
            elif edge == 2:
                s_in, e_in = sy >= y0, ey >= y0
            else:
                s_in, e_in = sy <= y1, ey <= y1
            if s_in != e_in:
                if edge == 0 or edge == 1:
                    xc = x0 if edge == 0 else x1
                    tt = (xc - sx) / (ex - sx)
                    ix, iy = xc, sy + tt * (ey - sy)
                else:
                    yc = y0 if edge == 2 else y1
                    tt = (yc - sy) / (ey - sy)
                    ix, iy = sx + tt * (ex - sx), yc
                bx[k] = ix
                by[k] = iy
                k += 1
            if e_in:
                bx[k] = ex
                by[k] = ey
                k += 1
        for i in range(k):
            ax[i] = bx[i]
            ay[i] = by[i]
        m = k
        if m == 0:
            return 0.0
    a = 0.0
    for i in range(m):
        j = (i + 1) % m
        a += ax[i] * ay[j] - ax[j] * ay[i]
    return abs(a) * 0.5


def _poly_area(px: np.ndarray, py: np.ndarray) -> float:
    n = px.shape[0]
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += px[i] * py[j] - px[j] * py[i]
    return abs(a) * 0.5


def clip_fractions_ref(xy: np.ndarray, start: np.ndarray, owner: np.ndarray, n: int, rect: np.ndarray
                       ) -> np.ndarray:
    """Per owner: visible area share of its polygons (polygon p = xy[start[p]:start[p + 1]]) inside rect
    [x0, y0, x1, y1]. Owners whose polygons have no area use the share of their vertices inside instead; owners
    without polygons get 0."""
    x0, y0, x1, y1 = rect[0], rect[1], rect[2], rect[3]
    tot = np.zeros(n)
    vis = np.zeros(n)
    pts = np.zeros(n)
    pin = np.zeros(n)
    for p in range(start.shape[0] - 1):
        a, b = start[p], start[p + 1]
        o = owner[p]
        px = xy[a:b, 0].copy()
        py = xy[a:b, 1].copy()
        for i in range(b - a):
            pts[o] += 1.0
            if x0 <= px[i] <= x1 and y0 <= py[i] <= y1:
                pin[o] += 1.0
        if b - a >= 3:
            full = _poly_area(px, py)
            if full > 1e-9:
                tot[o] += full
                vis[o] += _clip_area(px, py, x0, y0, x1, y1)
    out = np.zeros(n)
    for o in range(n):
        if tot[o] > 1e-9:
            out[o] = min(1.0, vis[o] / tot[o])
        elif pts[o] > 0:
            out[o] = pin[o] / pts[o]
    return out


if numba is not None:
    _clip_area_nb = numba.njit(cache=True)(_clip_area)
    _poly_area_nb = numba.njit(cache=True)(_poly_area)

    @numba.njit(cache=True)
    def clip_fractions(xy: np.ndarray, start: np.ndarray, owner: np.ndarray, n: int, rect: np.ndarray
                       ) -> np.ndarray:   # pragma: no cover - compiled twin of clip_fractions_ref
        x0, y0, x1, y1 = rect[0], rect[1], rect[2], rect[3]
        tot = np.zeros(n)
        vis = np.zeros(n)
        pts = np.zeros(n)
        pin = np.zeros(n)
        for p in range(start.shape[0] - 1):
            a, b = start[p], start[p + 1]
            o = owner[p]
            px = xy[a:b, 0].copy()
            py = xy[a:b, 1].copy()
            for i in range(b - a):
                pts[o] += 1.0
                if x0 <= px[i] <= x1 and y0 <= py[i] <= y1:
                    pin[o] += 1.0
            if b - a >= 3:
                full = _poly_area_nb(px, py)
                if full > 1e-9:
                    tot[o] += full
                    vis[o] += _clip_area_nb(px, py, x0, y0, x1, y1)
        out = np.zeros(n)
        for o in range(n):
            if tot[o] > 1e-9:
                out[o] = min(1.0, vis[o] / tot[o])
            elif pts[o] > 0:
                out[o] = pin[o] / pts[o]
        return out
else:   # pragma: no cover
    clip_fractions = clip_fractions_ref


def _rect_poly(r: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    return [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]


def image_extent(e: Entity) -> list[list[tuple[float, float]]]:
    """What a detector would see of e: its sprite bounds (the root renderer only, EntityRegistry.cs:691) plus its
    active damage boxes (a beam or slash effect is drawn; live i1_001 f352306: render box 72.26-73.84 x 1.76-2.24,
    damage box 72.44-75.44 x 1.96-4.07), else its enabled colliders; [] = not drawn."""
    if e.hidden:
        return []
    if e.render_box is not None:
        return [_rect_poly(e.render_box)] + [b.poly for b in e.dmg_boxes if b.active and len(b.poly) >= 2]
    return [p for p in e.body_polys if len(p) >= 2]


def viewport_rect(cam, margin_px: float = 0.0) -> np.ndarray:
    rx, ry, rw, rh = cam.viewport
    sw, sh = cam.screen
    return np.array([rx * sw - margin_px, sh - (ry + rh) * sh - margin_px, (rx + rw) * sw + margin_px,
                     sh - ry * sh + margin_px])


# ---- box tables ------------------------------------------------------------------------------------------------

@dataclass(slots=True)
class _LocalBox:
    box: list[float]              # x0, y0, x1, y1 in the mirrored transform frame
    hazard: Hazard
    flags: frozenset[str]
    dmg: int


class BoxTable:
    """Per type_key, the union of every damage collider seen, one axis-aligned box per collider (keyed by its name
    when exported, else its point count and rank), in the entity's frame: x mirrored when flip_x, relative to
    Entity.pos (decision 1: the main body collider centre, else the sprite bounds centre; both visible), so vision can
    place it. Colliders mirror with the transform's negative x scale while flipX also folds in the sprite flip, so a
    wrong guess only widens the union to both sides (still a superset of what was seen). Types in `frozen` (an offline
    table, see load) are not learnt online: their boxes do not depend on anything the current run showed."""

    def __init__(self) -> None:
        self.t: dict[str, dict[tuple, _LocalBox]] = {}
        self.frozen: set[str] = set()

    @staticmethod
    def _keys(boxes: list[DamageBox]) -> list[tuple]:
        seen: dict[tuple, int] = {}
        out = []
        for b in boxes:
            base = (b.name or "", len(b.poly))
            i = seen.get(base, 0)
            seen[base] = i + 1
            out.append(base + (i,))
        return out

    def learn(self, type_key: str, anchor: tuple[float, float], flip: bool, boxes: list[DamageBox]) -> None:
        if not boxes or type_key in self.frozen:
            return
        tab = self.t.setdefault(type_key, {})
        s = -1.0 if flip else 1.0
        ax, ay = anchor
        for key, b in zip(self._keys(boxes), boxes):
            if not b.poly:
                continue
            xs = [s * (x - ax) for x, _ in b.poly]
            ys = [y - ay for _, y in b.poly]
            bx = [min(xs), min(ys), max(xs), max(ys)]
            dmg = max(b.dmg_seq) if b.dmg_seq else 0
            lb = tab.get(key)
            if lb is None:
                tab[key] = _LocalBox(bx, b.hazard, b.flags, dmg)
            else:
                lb.box = [min(lb.box[0], bx[0]), min(lb.box[1], bx[1]), max(lb.box[2], bx[2]), max(lb.box[3], bx[3])]
                lb.flags = lb.flags | b.flags
                lb.dmg = max(lb.dmg, dmg)

    def to_dict(self) -> dict:
        """JSON-able form (an offline table built from earlier recordings: pass it back with from_dict)."""
        return {tk: [[list(k), lb.box, int(lb.hazard), sorted(lb.flags), lb.dmg] for k, lb in tab.items()]
                for tk, tab in self.t.items()}

    @classmethod
    def from_dict(cls, d: Mapping[str, list], frozen: bool = True) -> "BoxTable":
        bt = cls()
        for tk, rows in d.items():
            bt.t[tk] = {tuple(k): _LocalBox(list(map(float, box)), Hazard(hz), frozenset(fl), int(dmg))
                        for k, box, hz, fl, dmg in rows}
        if frozen:
            bt.frozen = set(bt.t)
        return bt

    @classmethod
    def load(cls, path: Path | str | None = None) -> "BoxTable":
        """The offline table (default: the shipped knowledge/<build>/enemies/box_tables.json, built by
        ssbot.tools.box_table_build), every type frozen; an empty table when the file is missing."""
        p = Path(path) if path is not None else DEFAULT_BOX_TABLE
        if not p.is_file():
            return cls()
        doc = json.loads(p.read_text("utf-8"))
        return cls.from_dict(doc["types"])

    def place(self, type_key: str, anchor: tuple[float, float], flip: bool) -> list[DamageBox]:
        tab = self.t.get(type_key)
        if not tab:
            return []
        ax, ay = anchor
        out = []
        for lb in tab.values():
            x0, y0, x1, y1 = lb.box
            wx0, wx1 = (ax - x1, ax - x0) if flip else (ax + x0, ax + x1)
            out.append(DamageBox(poly=_rect_poly((wx0, ay + y0, wx1, ay + y1)), active=True,
                                 dmg_seq=(lb.dmg,) if lb.dmg > 0 else (), hazard=lb.hazard, flags=lb.flags))
        return out


# ---- the filter -------------------------------------------------------------------------------------------------

@dataclass(slots=True)
class _Seen:
    ent: Entity            # the last visible copy (already filtered)
    t: float               # game time it was last visible
    frac: float            # its visible_frac then
    state: str             # "visible" | "ghost" (known to be outside the image) | "hidden" (gone inside the image)
    t_state: float         # game time the state was last confirmed
    oracle_hidden: bool = False


@dataclass(slots=True)
class _Phase:
    name: str
    t0: float


class ObservabilityFilter:
    def __init__(self, profile: str = VISION_EQUIVALENT, bosses: Iterable[BossSpec] = (),
                 hp_max: dict[str, float] | None = None, phase_map: dict[str, dict[str, str]] | None = None,
                 hit_damage: float = 5.0, attack_damage: Mapping[str, float] | None = None, hit_sigma: float = 0.5,
                 ttl_s: dict[Kind, float] | None = None, margin_px: float = 0.0, calib_sigma_s: float = 30.0,
                 drift: float = 1e-3, quit_map: QuitMapLike | None = None, min_p: float = 0.99,
                 box_table: BoxTable | None = None):
        if profile not in (ORACLE, VISION_EQUIVALENT):
            raise ValueError(f"unknown profile {profile!r}")
        self.profile = profile
        specs = {b.type_key: b for b in bosses}
        self.hp_max = {k: b.hp_max for k, b in specs.items() if b.hp_max is not None} | (hp_max or {})
        self.phase_map = {k: dict(b.phases) for k, b in specs.items()} | (phase_map or {})
        self.hit_damage = hit_damage
        self.attack_damage = DEFAULT_ATTACK_DAMAGE | dict(attack_damage or {})
        self._anim_keys = sorted(self.attack_damage, key=len, reverse=True)
        self.hit_sigma = hit_sigma
        self.ttl_s = DEFAULT_TTL_S | (ttl_s or {})
        self.margin_px = margin_px
        self.calib_sigma_s = calib_sigma_s
        self.drift = drift
        self.quit_map = quit_map
        self.min_p = min_p
        self.boxes = box_table if box_table is not None else BoxTable.load()   # knowledge: survives reset()
        self.reset()

    def reset(self) -> None:
        self._seen: dict[int, _Seen] = {}
        self._var: dict[int, float] = {}
        self._dmg: dict[int, float] = {}
        self._killed: set[int] = set()
        self._phase: dict[int, _Phase] = {}
        self._pt: list[float] | None = None      # [live_s, sigma_s, calib value]
        self._q_prev: int | None = None
        self._scene: str | None = None
        # pause cues (QPC seconds)
        self._paused: bool | None = None
        self._lockout_until = -math.inf
        self._hit_q = -math.inf
        self._hazard_q = -math.inf
        self._entry_q = -math.inf
        self._freeze_q: list[float] = []
        self._slow_until = -math.inf
        self._tq_prev: tuple[float, float] | None = None     # (game time, QPC s) of the previous frame
        self._rates: deque[tuple[float, float]] = deque(maxlen=SLOW_WINDOW)   # (game dt, real dt) per frame
        self._gameplay_prev: bool | None = None

    # ---- per frame ---------------------------------------------------------------------------------------------

    def apply(self, ws: WorldState) -> WorldState:
        if self.profile == ORACLE:
            return ws
        t = ws.stamp.t_game_s
        q = ws.stamp.t_sample_qpc_ns / 1e9
        out = ws.view(VISION_EQUIVALENT)
        if out.game.scene.v != self._scene:
            self._scene = out.game.scene.v
            self._seen.clear()
            self._var.clear()
            self._dmg.clear()
            self._killed.clear()
            self._phase.clear()
            self._freeze_q.clear()
        unobs = Unobs.TIMERS_DROPPED | Unobs.PLAYTIME_WALL | Unobs.PAUSE_INFERRED

        for e in ws.entities:                      # types without an offline table: learn from every exported one
            if not e.hidden and e.dmg_boxes:
                self.boxes.learn(e.type_key.v, e.pos.v, e.flip_x, e.dmg_boxes)

        frac, inside = self._visibility(out)
        visible: list[Entity] = []
        gone_inside: dict[int, bool] = {}          # id -> the oracle exports it hidden
        outside: set[int] = set()
        for e, fv, pin in zip(out.entities, frac, inside):
            if e.hidden or (fv <= 0.0 and not image_extent(e) and pin):
                gone_inside[e.id] = e.hidden
            elif fv <= 0.0:
                outside.add(e.id)
            else:
                e.visible_frac = float(fv)
                e.last_seen_ms = 0.0
                visible.append(e)
        vis_ids = {e.id for e in visible}

        events = []
        for ev in out.events:
            if ev.kind == Ev.HIT_DEALT:
                if ev.data.target_id not in vis_ids:
                    continue     # a hit vision cannot see
                iid = ev.data.target_id
                dmg, var = self._hit_value(ev.data)
                self._var[iid] = self._var.get(iid, 0.0) + var
                self._dmg[iid] = self._dmg.get(iid, 0.0) + dmg
            elif ev.kind == Ev.ENEMY_KILLED:
                self._killed.add(ev.data.target_id)
            events.append(ev)
        out.events = events

        for e in visible:
            unobs |= self._estimate(e, t)
            if self.boxes.t.get(e.type_key.v):
                e.dmg_boxes = self.boxes.place(e.type_key.v, e.pos.v, e.flip_x)
                unobs |= Unobs.BOXES_FROM_TABLE
            else:
                e.dmg_boxes = [replace(b, active=True) for b in e.dmg_boxes]
            if e.render_box is not None:
                e.body_polys = [_rect_poly(e.render_box)]
            self._seen[e.id] = _Seen(e, t, float(e.visible_frac), "visible", t)

        ents = list(visible)
        for iid in list(self._seen):
            if iid in vis_ids:
                continue
            seen = self._seen[iid]
            if iid in self._killed:
                del self._seen[iid]
                continue
            seen.oracle_hidden = gone_inside.get(iid, False)
            if seen.state == "visible":            # just lost: it vanished in view, or vision lost it over the edge
                vanished = iid not in outside and seen.frac >= VANISH_FRAC    # hidden, not drawn, left the export
                seen.state, seen.t_state = ("hidden" if vanished else "ghost"), t
            # (a ghost stays a ghost and a hidden one hidden until seen again: vision cannot see either change)
            age = t - seen.t
            if seen.state == "hidden" and seen.ent.kind not in KEEP_HIDDEN:
                del self._seen[iid]
                continue
            if age > self.ttl_s.get(seen.ent.kind, OTHER_TTL_S) and not (seen.oracle_hidden and seen.state == "hidden"):
                del self._seen[iid]               # (seen digging in and still exported hidden: no TTL)
                continue
            if seen.state == "hidden":
                ents.append(self._hidden(seen, t, age))
                unobs |= Unobs.VANISHED_IN_VIEW
            else:
                ents.append(self._ghost(seen, age))
                unobs |= Unobs.OFFSCREEN_HIDDEN
        out.entities = ents

        for name in _TIMERS:
            setattr(out.hero, name, None)
        silk = out.res.silk.v
        out.res.bind_ready = E(silk >= BIND_SILK and out.hero.mode.v not in NO_BIND_MODES, conf=0.8,
                               src=Src.PREDICTED)
        if out.res.status - NO_DAMAGE_STATUS:      # a damage status is visible, its remaining damage is not: lethal
            out.res.pending_dmg = E(out.res.hp.v + out.res.blue.v, sigma=math.inf, conf=0.0, src=Src.PREDICTED)
        else:
            out.res.pending_dmg = E(0, conf=0.9, src=Src.PREDICTED)
        self._pause(out, q)
        self._play_time(out)
        out.game.unobservable = int(Unobs(out.game.unobservable) | unobs)
        return out

    # ---- parts -------------------------------------------------------------------------------------------------

    def _visibility(self, ws: WorldState) -> tuple[np.ndarray, np.ndarray]:
        """(visible area share, position inside the image) per entity."""
        ents = ws.entities
        cam = ws.cam
        n = len(ents)
        if not n:
            return np.zeros(0), np.zeros(0, dtype=bool)
        if cam.V is None or cam.P is None or cam.screen is None:
            return np.ones(n), np.ones(n, dtype=bool)        # no camera: nothing to cull against
        rect = viewport_rect(cam, self.margin_px)
        pts: list[tuple[float, float]] = [e.pos.v for e in ents]
        start = [n]
        owner = []
        for i, e in enumerate(ents):
            for poly in image_extent(e):
                pts.extend(poly)
                start.append(len(pts))
                owner.append(i)
        xy, ok = project(np.asarray(pts, dtype=np.float64), mat4(cam.V), mat4(cam.P), cam.viewport, cam.screen)
        inside = ok[:n] & (xy[:n, 0] >= rect[0]) & (xy[:n, 0] <= rect[2]) & (xy[:n, 1] >= rect[1]) & \
            (xy[:n, 1] <= rect[3])
        if not owner:
            return np.zeros(n), inside
        # (points behind the camera cannot occur: every point is on the z = 0 gameplay plane in front of it)
        frac = clip_fractions(np.ascontiguousarray(xy), np.asarray(start, dtype=np.int64),
                              np.asarray(owner, dtype=np.int64), n, rect)
        return frac, inside

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
            e.phase = PhasePost(topk=[(name, 1.0)], t_in_phase=self._phase_time(e.id, name, t))
            flags |= Unobs.PHASE_FROM_TABLE
        return flags

    def _hit_value(self, d: HitDealt) -> tuple[float, float]:
        """(damage, variance) of one hit dealt: attack_damage[src], else [attack], else the longest key prefixing the
        hero's clip, else hit_damage, each with variance hit_sigma^2. A hit the hero did not deal (by_hero False:
        lava, spikes ...) is not priced by the hero's clip: attack_damage[src] / [attack] when listed, else
        hit_damage with a variance of hit_damage^2 (unpriced)."""
        for key in (d.src, d.attack):
            if key is not None and key in self.attack_damage:
                return self.attack_damage[key], self.hit_sigma ** 2
        if d.by_hero is False:
            return self.hit_damage, self.hit_damage ** 2
        clip = d.hero_anim or ""
        for k in self._anim_keys:
            if clip.startswith(k):
                return self.attack_damage[k], self.hit_sigma ** 2
        return self.hit_damage, self.hit_sigma ** 2

    def _phase_time(self, iid: int, name: str, t: float) -> float:
        ph = self._phase.get(iid)
        if ph is None or ph.name != name:
            ph = self._phase[iid] = _Phase(name, t)
        return t - ph.t0

    def _hp(self, iid: int, hp_max: float | None) -> E[float] | None:
        if hp_max is None:
            return None              # no prior for this type: vision cannot tell its HP
        if iid in self._killed:
            return E(0.0, conf=0.9, src=Src.EVENT)
        return E(max(0.0, hp_max - self._dmg.get(iid, 0.0)), sigma=math.sqrt(self._var.get(iid, 0.0)), conf=0.8,
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
                      visible_frac=0.0, last_seen_ms=age_ms, flip_x=g.flip_x)

    def _hidden(self, seen: _Seen, t: float, age: float) -> Entity:
        """Gone inside the image (dug in, put away): it exists, its position is unknown (conf 0)."""
        g = seen.ent
        phase = None
        if g.phase is not None:
            ph = self._phase.get(g.id)
            if ph is None or ph.name != HIDDEN_PHASE:
                ph = self._phase[g.id] = _Phase(HIDDEN_PHASE, seen.t_state)
            phase = PhasePost(topk=[(HIDDEN_PHASE, 1.0)], t_in_phase=t - ph.t0)
        return Entity(id=g.id, kind=g.kind, type_key=g.type_key,
                      pos=E(g.pos.v, sigma=math.inf, conf=0.0, src=Src.PREDICTED, age_ms=age * 1000.0),
                      vel=unknown((0.0, 0.0)), facing=g.facing, phase=phase,
                      hp_est=self._hp(g.id, self.hp_max.get(g.type_key.v)) if g.hp_est else None,
                      visible_frac=0.0, last_seen_ms=age * 1000.0, hidden=True, flip_x=g.flip_x)

    def _pause(self, ws: WorldState, q: float) -> None:
        """pause_available / quit_available / pause_blockers from vision cues (DESIGN §3.7.5)."""
        g = ws.game
        screen = g.screen.v
        for ev in ws.events:
            if ev.kind in (Ev.PAUSE_ON, Ev.PAUSE_OFF):
                self._paused = ev.kind == Ev.PAUSE_ON
                self._lockout_until = q + PAUSE_LOCKOUT_S
            elif ev.kind == Ev.HIT_TAKEN:
                self._hit_q = q
            elif ev.kind == Ev.FREEZE:
                if ev.data.phase == "start":
                    self._freeze_q.append(q)
                elif self._freeze_q:
                    self._freeze_q.pop(0)
            elif ev.kind == Ev.SCENE_ENTER:
                self._entry_q = q
            elif ev.kind == Ev.HAZARD_RESPAWN:
                self._hazard_q = q
        if self._paused is None:
            self._paused = screen == Screen.PAUSE_MENU
        self._freeze_q = [x for x in self._freeze_q if q - x < FREEZE_MAX_S]
        t = ws.stamp.t_game_s
        if self._tq_prev is not None and q > self._tq_prev[1]:
            self._rates.append((t - self._tq_prev[0], q - self._tq_prev[1]))
        self._tq_prev = (t, q)
        if len(self._rates) < SLOW_WINDOW or \
                sum(g for g, _ in self._rates) < SLOW_RATE * sum(r for _, r in self._rates):
            self._slow_until = q + SLOW_HOLD_S      # no full speed reading yet, or the world runs slow
        gameplay = screen in GAMEPLAY
        if gameplay and self._gameplay_prev is False:
            self._entry_q = q
        self._gameplay_prev = gameplay
        if ws.hero.contact.v == "HAZARD":
            self._hazard_q = q

        blk = PauseBlock(0)
        if q < self._lockout_until:
            blk |= PauseBlock.PAUSE_LOCKOUT
        if not g.focus_ok:
            blk |= PauseBlock.FOCUS_LOST
        if screen == Screen.MSG_CANVAS:
            blk |= PauseBlock.MSG_CANVAS
        elif not gameplay and not self._paused:
            blk |= PauseBlock.GAME_STATE_NOT_PLAYING
        if self._freeze_q or q < self._slow_until:
            blk |= PauseBlock.TIME_SLOWED
        if q - self._hit_q < HIT_BLOCK_S or q - self._hazard_q < HAZARD_BLOCK_S or ws.hero.mode.v == "hurt" \
                or q - self._entry_q < ENTRY_BLOCK_S:
            blk |= PauseBlock.DISABLE_PAUSE
        blk &= VISION_BLOCKS
        key = self._key(screen, gameplay, q)

        if self._paused:
            pause = E(True, conf=PAUSE_CONF, src=Src.PREDICTED)
            greyed = g.menu.quit_greyed if g.menu is not None else None
            quit_ = E(not greyed, conf=0.95, src=Src.PREDICTED) if greyed is not None else \
                E(False, conf=0.0, src=Src.PREDICTED)
        else:
            rules_ok = not blk
            if self.quit_map is None:
                pause = E(rules_ok, conf=PAUSE_CONF, src=Src.PREDICTED)
                quit_ = E(False, conf=0.0, src=Src.PREDICTED)
            else:
                pp = self.quit_map.p_pause(g.scene.v, key)
                pq = self.quit_map.p_quit(g.scene.v, key)
                p_ok = rules_ok and pp is not None and pp >= self.min_p
                pause = E(p_ok, conf=min(CONF_MAX, pp if p_ok else 1.0 - (pp or 0.0)), src=Src.PREDICTED)
                q_ok = p_ok and pq is not None and pq >= self.min_p
                quit_ = E(q_ok, conf=min(CONF_MAX, pq if q_ok else 1.0 - (pq or 0.0)), src=Src.PREDICTED)
        g.pause_available = pause
        g.quit_available = quit_
        g.pause_blockers = int(blk)
        g.unpause_lockout_until_s = self._lockout_until if math.isfinite(self._lockout_until) else 0.0

    def _key(self, screen: Screen, gameplay: bool, q: float) -> str:
        """The quit-map state key (ssbot.safety.quit_map) from vision cues."""
        if screen == Screen.INVENTORY:
            return "inventory"
        if screen == Screen.DIALOG:
            return "interact"
        if not gameplay:
            return "transition"
        if q - self._entry_q < 1.0:
            return "entry"
        if q - self._hazard_q < HAZARD_BLOCK_S:
            return "hazard"
        if q - self._hit_q < HIT_BLOCK_S:
            return "hurt0"
        if self._freeze_q or q < self._slow_until:
            return "freeze"
        if q - self._hit_q < HURT1_S:
            return "hurt1"
        return "free"

    def _play_time(self, ws: WorldState) -> None:
        pt = ws.game.play_time
        q = ws.stamp.t_sample_qpc_ns
        screen = ws.game.screen.v
        counting = screen not in NOT_COUNTING and not (screen == Screen.MSG_CANVAS and self._paused)
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
