"""Zone overlay (task "zone overlay", the person 2026-10-08): the Forum planner's danger regions drawn over the game,
live (human_session --overlay) or over a recording (render / viewer --zones), so the person can check by eye whether
they are computed right. It shows what the bot ACTUALLY computes, not an idealised version.

    cd brain
    ../scripts/uv.cmd run python -u -m ssbot.tools.human_session --instance 8 --savestate fo_W --speed 0.5 --overlay
        --display borderless                                   # live (keys below)
    ../scripts/uv.cmd run python -m ssbot.tools.viewer C:/ssbot/data/human/<session> --zones [--from F --to F]
        [--k 0,12] [--video] [--save out.rrd]                  # replay with rewind (Rerun, "frame" timeline)
    ../scripts/uv.cmd run python -m ssbot.tools.zone_overlay render <session> --attempt N --from F --to F
        [--png-every 30] [--clip out.mp4] [--k 12] [--mode all]   # zones drawn on the recorded video
    ../scripts/uv.cmd run python -m ssbot.tools.zone_overlay bench <session> --attempt N [--limit-s 60]

Computation (ZoneEngine), on the person's STATE stream in game frames (a 0.5x session's STATE pairs merged as
tools.forum_human_score does): ForumPlannerPolicy's own forecast path (OracleBackend -> StateTracker -> MultiForecaster
.update -> forecast(HORIZON_S)), with the planner's switches from the environment, defaulting to the round-5
recommended configuration (SSBOT_FORUM_FR=seen_cf, REACT=escape+n+g, MARGIN=state, KF=kill, clash main; printed in
the legend). The planner's tick is not run: the support does not depend on its picks.

  support layers  the forecast at look-ahead k (now, +6, +12, +18, +36 frames) queried with the planner's own occupancy
                  (forum_layer_audit.group_occ) on a hero-centre grid over the arena (CELL u cells, walls excluded, from
                  standing height up TOP_U u), one layer per group kind (LAYER_OF): bodies + idle growth, committed fine
                  (fine placements, chains, tails), window placements (windows, family unions, re-anchor bboxes), not
                  started (later attacks / idle instances / entries), projectiles (hazards), death tails (+ arena),
                  margins (the area only the margins add: the same tick on tables with every margin x 0; --margins).
  yellow          INESCAPABLE, the person's definition (forum.md §26): (a) every enemy with a committed attack: its own
                  committed fine placements (owner filter) on the grid for frames 0 .. YELLOW_F, then from the last
                  frame back to now Z_k = D_k | erode(Z_k+1, one-frame reach box) (forum_ics.zone_lb's box: dash speed
                  sideways, jump speed up, max fall down, ceil to cells), the floor and the walls solid (a cell from
                  which every one-frame move lands in Z is in Z), the first LAT_F frame standing; per enemy, then the
                  union; shown at frame k. (b) every alive, in-play enemy that has not started an attack, from its
                  earliest start t_strike on (one frame early): the commit-now zone of zones_lat1.npz (forum_ics Zones, the upper bound
                  of its library, the whole zone "z") for the hero's lock state NOW toward that enemy (free / attack / dash; above
                  standing height: air), placed on the enemy's anchor dead-reckoned to frame k, mirrored to the hero's
                  side (the attack faces the hero at its commit).
  red             NON-CLASHABLE damage colliders of the STATE shown (`hurts`: enabled, dealt > 0 or a multi-hit one
                  exported with dealt 0: the whip, the ParrySlash Hit, the Minister's Slash Collider; parry bits without clash /
                  force: oracle 4 = counter only; 5 = clash + counter is clashable; every Clapper collider), each with
                  its sweep over the next SWEEP_F frames (moved along its entity's velocity, convex hull). Bodies,
                  Clapper moves and runes, Clawmaiden spear / explosion, bells (a hit-back bell deals 0: not drawn),
                  Tiny rams, unclashable projectiles all carry parry 4 in the recordings.

  range           (--range / human_session --overlay-range / viewer --zones --range or --range-only; modes range+red,
                  range) each enemy's ATTACK-RANGE estimate at k (combat.attack_range, Task "attack range" 2026-10-10:
                  no margin of any kind), in its own colour: filled = the raw region its damage colliders can occupy
                  at +k, thin outline = the same in hero-centre space (dilated by the hurtbox 0.4554 x 2.2498 at
                  (0, -0.38) from the hero TRANSFORM). Idle enemies = their body now. Needs no planner forecast (the
                  range modes skip it); attacks that have not started are not drawn (group 2, not this round).
                  ALL K (key 0 / human_session --overlay-all-k, the person 2026-10-10): every look-ahead 0 / 6 / 12 /
                  18 / 36 at once, +0 filled, the later ones as outlines (solid, dashed, dotted, fainter as k grows)
                  labelled +k; a k whose estimate is the same region as an earlier one is drawn once (+0=6=...).
                  SWEPT (key 9 / --overlay-swept): the union of the estimate over every frame 0..k (0..36 with all
                  k): the whole path of a lunge or a dive, out and back, a light dashed outline over a faint fill.
                  Both come from one pass (RangeTracker.ladder). The real damage colliders stay drawn (red / orange).
                  AIM ZONES (key 8 / --overlay-aim, the person 2026-10-10): every enemy in a pending aimed antic
                  (Reed Stab Antic, Maestro Fire Antic, Clapper Jump Antic / Cast Slam Antic, Tiny Fire Ready) shows
                  its composite inescapable zone (tools.aim_zones, lat 2) at its position now: each cell by its own
                  height class (ground band filled, low air solid, high air dashed), walls / dome by its x bin;
                  an empty zone is labelled "zone 0".

Space: the support layers and yellow are HERO-CENTRE configuration space: where the hero's CENTRE (the white dot) must
not be; the colliders are already grown by the hero hurtbox half extents (0.25 x 1.04 u). Red is the colliders
themselves (compare with DebugMod's hitbox.show).

Live keys (polled, only while the game window has the focus; the game still gets them): F8 overlay on / off, F9 cycles
yellow+red / yellow / red / support / all, F10 freeze / unfreeze (time.scale 0.0001: the oracle refuses 0), F11 one
game frame forward while frozen (about one: the RPC lands a render frame or two later), 1-5 look-ahead now / +6 / +12 /
+18 / +36, 0 every look-ahead at once (range), 9 the swept path (range), 8 the aim zones (range), Ctrl+1-7 toggles a
support layer. The same through the session's command file: "overlay k 12", "overlay mode all", "overlay layer window",
"overlay all", "overlay swept on", "overlay aim on", "overlay freeze", "overlay step", "overlay off" / "overlay on".
"""
import argparse
import ctypes
import json
import math
import os
import queue
import random
import re
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np

ZONES_NPZ = Path(r"C:\ssbot\data\m2_forum_ics\zones_lat1.npz")
OUT_DIR = Path(r"C:\ssbot\data\m2_forum_overlay")
FT = 1.0 / 60.0
KS = (0, 6, 12, 18, 36)
CELL = 0.25
TOP_U = 16.0
YELLOW_F = 72
LAT_F = 1
SWEEP_F = 6
RENDER = (1920, 1080)
FORUM_SCENES = ("Hang_04", "Hang_04_boss")
FORCE_RED_TYPES = frozenset({"Song Heavy Sentry"})       # the Clapper: no move of it can be clashed
CLASH_BITS = 1 | 2                                        # ipc.ents PARRY_BITS clash | force
MW_SRC_BIT = 8                                            # ipc.ents SRC_BITS["multi_wounder"]
PARKED_STATES = r"Ready|Dormant|Sleep|Wait"                # with no render: a member parked before its entry
FREEZE_SCALE = 1e-4
SHORT_NAMES = {"Song Reed": "Reed", "Song Pilgrim 01": "Envoy", "Song Administrator": "Minister",
               "Song Pilgrim 03": "Choristor", "Song Handmaiden": "Clawmaiden", "Pilgrim 03 Song": "Bellbearer",
               "Song Heavy Sentry": "Clapper", "Song Automaton Tiny": "Tiny", "Song Pilgrim Maestro": "Maestro"}
KIN_F = 12                        # yellow: frames a committed attack's colliders are carried along its velocity
LOCK_LAT = {0: LAT_F, 1: LAT_F + 6, 2: LAT_F + 6, 3: LAT_F}   # not-started yellow: free / attack / dash / air
NS_U = 24.0                       # the not-started lower bound's half width (u) around the anchor
THROWS = frozenset({"CB_THROW", "RE_THROW", "CC_CAST"})   # yellow: their thrown objects are the hazard layer's
# a distinct colour per enemy (BGR) for its outlines, by name order
ENEMY_COLORS = ((255, 120, 60), (60, 200, 255), (120, 255, 120), (255, 90, 220), (90, 140, 255), (255, 255, 90),
                (180, 120, 255), (60, 255, 200), (200, 200, 255), (255, 170, 170))
# the round-5 recommended configuration (forum.md, the lead 2026-10-08); the environment wins
DEFAULT_ENV = {"SSBOT_FORUM_FR": "seen_cf", "SSBOT_FORUM_REACT": "escape+n+g", "SSBOT_FORUM_MARGIN": "state",
               "SSBOT_FORUM_KF": "kill", "SSBOT_FORUM_AIM": "1"}
DEFAULT_CLASH = "main"
SWITCHES = ("FR", "REACT", "MARGIN", "KF", "AIM", "PARK", "TIGHT", "RCLIP", "PRESTRIKE", "REANCHOR", "RTHROW",
            "WALKFLOOR", "NSBOX", "GATES", "TINYCLIP", "BODYCLIP", "PC", "TV", "T", "BELLS", "L2", "AB")

LAYERS = ("body", "committed", "window", "not_started", "hazard", "death", "margins")
LAYER_OF = {"body": "body", "collider": "body", "idle_now": "body", "idle": "body",
            "com_fine": "committed", "chain_fine": "committed", "tail": "committed",
            "com_win": "window", "com_fam": "window", "chain_win": "window", "com_bbox": "window",
            "chain_bbox": "window",
            "start_attack": "not_started", "start_idle": "not_started", "entry_later": "not_started",
            "entry_now": "not_started", "prestrike": "not_started",
            "haz_self": "hazard", "haz_path": "hazard", "haz_tube": "hazard",
            "death": "death", "arena": "death"}
NAMES = {"body": "bodies + idle growth", "committed": "committed fine (+chains, tails)",
         "window": "window / family / bbox placements", "not_started": "not started (later attacks, idle, entries)",
         "hazard": "projectiles / hazards", "death": "death tails (+arena)", "margins": "margins only",
         "yellow": "INESCAPABLE: hero centre must not be here", "red": "NON-CLASHABLE colliders (+6 f sweep)"}
# BGR, light colours
COLORS = {"body": (200, 200, 200), "committed": (245, 150, 245), "window": (250, 195, 140),
          "not_started": (160, 235, 160), "hazard": (110, 190, 255), "death": (220, 160, 185),
          "margins": (255, 245, 185), "yellow": (140, 245, 255), "red": (130, 130, 255),
          "clash": (60, 180, 255)}
A_SUPPORT, A_YELLOW, A_RED, A_SWEEP = 0.33, 0.40, 0.42, 0.22
A_RANGE = 0.30
KEY_K = {0x31: 0, 0x32: 6, 0x33: 12, 0x34: 18, 0x35: 36}
KEY_ALL_K, KEY_SWEPT = 0x30, 0x39   # 0: every look-ahead at once, 9: the swept path (range modes)
KEY_AIM = 0x38                      # 8: the aim zones of the pending aimed moves (range modes)
AIM_LAT = 2                         # the aim zones' latency: the bot reacting to the decision (tools.aim_zones)
# the range layer's all-k mode, by the look-ahead's rank in KS: (line, px at 1080p, opacity); rank 0 is also filled
RANGE_STYLE = (("solid", 2.0, 1.0), ("solid", 2.0, 0.95), ("dash", 2.0, 0.85), ("dash", 1.5, 0.7), ("dot", 1.5, 0.6))
A_SWEPT = 0.10


def apply_default_env() -> dict:
    """The round-5 configuration where the environment does not set a switch (before the planner modules load:
    SSBOT_FORUM_KF is read at import). Returns the switches in effect."""
    for k, v in DEFAULT_ENV.items():
        os.environ.setdefault(k, v)
    return {k: os.environ[f"SSBOT_FORUM_{k}"] for k in SWITCHES if f"SSBOT_FORUM_{k}" in os.environ}


def merge_states(group: list[dict], f: int, base: float) -> dict:
    """One game frame from the STATEs of `group` at commanded time scale `base` (tools.forum_human_score._merge_pair
    for any count: as a 1x STATE reads, udt x base summed, ts / base, the events and input masks of all)."""
    b = group[-1]
    m = dict(b)
    m["f"] = f
    m["_f_raw"] = b["f"]
    if len(group) == 1 and base >= 0.999:
        return m
    m["dt"] = sum(float(x.get("dt") or 0.0) for x in group)
    m["udt"] = sum(float(x.get("udt") or 0.0) for x in group) * base
    m["ts"] = min(1.0, float(b.get("ts") or 0.0) / base)
    m["fs"] = sum(int(x.get("fs") or 0) for x in group)
    evs = []
    for x in group:
        for e in x.get("ev") or ():
            evs.append(dict(e, f=f) if "f" in e else e)
    m["ev"] = evs
    mask = 0
    for x in group:
        mask |= int((x.get("input") or {}).get("mask") or 0)
    m["input"] = dict(b.get("input") or {}, mask=mask)
    return m


def battle(s: dict) -> dict | None:
    return next((x for x in (s.get("room") or {}).get("battles") or () if x.get("name") == "Battle Scene"), None)


def scene_of(s: dict) -> str | None:
    g = s.get("game") or {}
    return g.get("scene_raw") or g.get("scene")


# ------------------------------------------------------------------------------------------------ colliders (red)

def parked(e: dict) -> bool:
    """A later wave's member parked off-stage before its entry (e.g. a Reed in "Fly In Ready": not rendered, its body
    collider reported enabled, but the hero overlapped it for 136 frames of 20261008_230220 with no damage)."""
    if e.get("render_aabb") is not None:
        return False
    return any(re.search(PARKED_STATES, str(f.get("state") or "")) for f in e.get("fsms") or ())


def hurts(c: dict, src: int) -> bool:
    """A collider that damages the hero: enabled, with damage dealt > 0, or a multi-hit collider exported with dealt 0
    (eff != 0 on an entity with the multi_wounder src bit: behaviour_tables.multi_wounder_threat as forum_cache keeps
    it; the Choristor's Whip Hit 1-6, the Reed's / Minister's ParrySlash Hit, the Minister's Slash Collider, whose hits
    the hornet_multi_wounder FSM deals). A hit-back bell, a parried pin and a Handmaiden's body also export dealt 0,
    with eff 0 and no multi_wounder bit: no recorded damage event ever came from them (C:/ssbot/data/m2_forum_push/p0
    mw_proof*.json), so they stay out."""
    d = c.get("damage")
    if not d or not c.get("enabled"):
        return False
    if (d.get("dealt") or 0) > 0:
        return True
    return not d.get("dealt") and (d.get("eff") or 0) != 0 and bool(int(src or 0) & MW_SRC_BIT)


def damage_colliders(s: dict):
    """[(poly [n, 2], clashable, label, entity velocity, owner iid)] of every collider that damages the hero (`hurts`:
    dealt > 0 or a multi-hit one exported with dealt 0; parked entities skipped)."""
    out = []
    for e in s.get("ents") or ():
        if parked(e):
            continue
        tk = str(e.get("type_key") or e.get("name") or "")
        vel = e.get("vel") or (0.0, 0.0)
        src = int(e.get("src") or 0)
        for c in e.get("cols") or e.get("colliders") or ():
            d = c.get("damage")
            v = c.get("verts_world")
            if not v or len(v) < 6 or not hurts(c, src):
                continue
            clash = bool(int(d.get("parry") or 0) & CLASH_BITS) and tk not in FORCE_RED_TYPES
            out.append((np.asarray(v, np.float64).reshape(-1, 2), clash, f"{tk}/{c.get('name')}",
                        (float(vel[0]), float(vel[1])), int(e.get("iid") or -1)))
    return out


def sweep_hull(poly: np.ndarray, vel, frames: int = SWEEP_F) -> np.ndarray:
    """The convex hull of the collider and its copy moved `frames` along its entity's velocity."""
    import cv2
    d = np.asarray(vel, np.float64) * frames * FT
    pts = np.vstack([poly, poly + d]).astype(np.float32)
    return cv2.convexHull(pts).reshape(-1, 2).astype(np.float64)


# ------------------------------------------------------------------------------------------------ erosion (yellow)

def erode_back(D: np.ndarray, ax: int, up: int, dn: int, lat: int = LAT_F, solid: np.ndarray | None = None,
               walls: bool = True) -> np.ndarray:
    """D [K+1, ny, nx] bool (row 0 = the lowest hero centre, standing) -> Z [K+1, ny, nx]: Z_K = D_K;
    Z_k = D_k | erode(Z_k+1) for k >= lat (a cell is doomed when every one-frame move, dx in [-ax, ax] cells,
    dy in [-dn, up] cells, lands in a doomed cell); Z_k = D_k | Z_k+1 below lat (the hero has not reacted). The floor
    (below row 0), the walls (left of column 0, right of the last; walls=False: open) and `solid` [ny, nx] (the sky
    above the dome) are solid, i.e. doomed (no escape into them; the caller masks them out); above is free."""
    import cv2
    K1, ny, nx = D.shape
    p = max(ax, up, dn) + 1
    S = np.zeros((ny + 2 * p, nx + 2 * p), np.uint8)
    S[:p, :] = 1
    if walls:
        S[:, :p] = 1
        S[:, -p:] = 1
    if solid is not None:
        S[p:p + ny, p:p + nx] |= solid.astype(np.uint8)
    kern = np.ones((up + dn + 1, 2 * ax + 1), np.uint8)
    Z = np.zeros((K1, ny, nx), bool)
    cur = S.copy()
    cur[p:p + ny, p:p + nx] |= D[-1]
    Z[-1] = cur[p:p + ny, p:p + nx] > 0
    for k in range(K1 - 2, -1, -1):
        if k >= lat:
            e = cv2.erode(cur, kern, anchor=(ax, dn), borderType=cv2.BORDER_REPLICATE)
        else:
            e = cur
        nxt = S | e
        nxt[p:p + ny, p:p + nx] |= D[k]
        cur = nxt
        Z[k] = cur[p:p + ny, p:p + nx] > 0
    return Z


# ------------------------------------------------------------------------------------------------ the engine

def aim_zones_of(trk, lat: int = AIM_LAT) -> list:
    """The composite aim zone (tools.aim_zones) of every enemy a RangeTracker tracks in a pending aimed antic, placed
    at its position now in its side (the facing for the Reed's stab, the hero's side now for the others):
    [(iid, {class: [world polygons]}, label, (x, y))]; an empty zone has no polygons and the label "zone 0"."""
    if trk is None:
        return []
    try:
        from ssbot.tools import aim_zones as az
        rd = az.readers()
    except Exception:  # noqa: BLE001  (no tables: no layer)
        return []
    from ssbot.combat.attack_range import _first_state
    out = []
    hero = trk.hero
    for iid, (tk, e, inst) in sorted(trk.now.items()):
        st, _ = _first_state(e)
        name = az.pending_move(tk, st)
        if st == "Jump Aim" and inst is not None and inst.fam in ("CC_JUMP", "CC_JUMP_CAST"):
            name = inst.fam
        if name is None or name not in rd:
            continue
        p = e.get("pos") or (0.0, 0.0)
        x, y = float(p[0]), float(p[1])
        if az.MOVES[name].aim == "facing":
            side = trk.tables[tk].facing(e.get("flipX"))
        else:
            side = 1 if hero is None or hero[0] >= x else -1
        r = rd[name]
        polys = r.world_polys(x, y, side, lat)
        ar = r.area(x, y, side, lat)
        lab = f"aim {name} lat{lat}: " + (" / ".join(f"{c[0].upper()} {a:.1f}" for c, a in ar.items() if a > 0)
                                          + " u2" if polys else "zone 0")
        out.append((iid, polys, lab, (x, y)))
    return out


class Grid:
    """The hero-centre grid: x over the arena between the walls, y from standing height up TOP_U u."""

    def __init__(self, cell: float = CELL):
        from ssbot.core.forum import FLOOR_Y, WALL_L, WALL_R
        from ssbot.knowledge import hitbox_tables as hb
        self.cell = cell
        self.half = hb.HERO_HALF_U
        self.y0 = FLOOR_Y + hb.HERO_HALF_U[1]
        self.x0 = WALL_L + hb.HERO_HALF_U[0]
        x1 = WALL_R - hb.HERO_HALF_U[0]
        self.nx = int(math.floor((x1 - self.x0) / cell + 1e-9)) + 1
        self.ny = int(round(TOP_U / cell)) + 1
        self.xs = self.x0 + np.arange(self.nx) * cell
        self.ys = self.y0 + np.arange(self.ny) * cell
        GX, GY = np.meshgrid(self.xs, self.ys)
        self.gx = np.ascontiguousarray(GX.reshape(-1, 1))
        self.gy = np.ascontiguousarray(GY.reshape(-1, 1))
        # the hero centres inside the arena: the hurtbox's top under the dome (core.forum.DOME, the roof colliders);
        # above it is the sky (solid for the escape, never drawn)
        from ssbot.core.forum import dome_y
        top = np.array([dome_y(float(x)) for x in self.xs]) - hb.HERO_HALF_U[1]
        self.inside = self.ys[:, None] <= top[None, :]

    @property
    def shape(self) -> tuple[int, int]:
        return self.ny, self.nx

    def to_world(self, cols: np.ndarray, rows: np.ndarray) -> np.ndarray:
        return np.stack([self.x0 + cols * self.cell, self.y0 + rows * self.cell], axis=-1)


class ZoneEngine:
    """ForumPlannerPolicy's forecast path on game-frame STATEs, and the zones of one frame (module docstring)."""

    def __init__(self, crest: str = "Wanderer", threads: int = 4, clash: str = DEFAULT_CLASH, cell: float = CELL,
                 margins: bool = False, zones_path: Path = ZONES_NPZ, range_layer: bool = False):
        # the attack-range estimate (combat.attack_range, no margin): its own tracker on the same game frames
        self.rng = None
        if range_layer:
            from ssbot.combat.attack_range import RangeTracker
            self.rng = RangeTracker()
        self.switches = apply_default_env()
        import numba
        numba.set_num_threads(threads)
        from ssbot.tools.forum_ics import Zones
        from ssbot.train.forum_planner_policy import ForumPlannerPolicy
        self.crest = crest if crest in ("Wanderer", "Reaper") else "Wanderer"
        self.clash = clash
        self.pol = ForumPlannerPolicy(threads=threads, crest=self.crest, clash=clash)
        self.pol.warmup()
        self.vs = None
        if margins:
            from ssbot.tools.forum_layer_audit import Variants
            self.vs = Variants(self.pol.fc, ("m0",))
        # "z": the whole upper-bound zone (the definition); "zl" (late=True) keeps only the points left after
        # LATE_F frames, and is empty for most families at the anchor heights seen in the Forum
        self.zones = Zones(zones_path, late=False) if zones_path.exists() else None
        self.grid = Grid(cell)
        p = self.pol.params
        self.reach = (int(math.ceil(p.dash_speed * FT / cell)), int(math.ceil(p.jump_speed * FT / cell)),
                      int(math.ceil(p.max_fall * FT / cell)))
        self.running = False
        self.ws = None
        self.names: dict[int, str] = {}
        self.counts: dict[str, int] = {}
        self._lb: dict = {}
        self.raw: dict | None = None
        self.fcast = None
        self.f_fed = None

    def config_text(self) -> str:
        sw = " ".join(f"{k}={v}" for k, v in self.switches.items())
        return f"{sw} clash={self.clash} crest={self.crest}" + (" margins" if self.vs is not None else "")

    def start(self, terrain_msg: dict | None) -> None:
        """A new battle attempt (ForumPlannerPolicy.reset on the Forum encounter)."""
        from ssbot.train.encounters import ENCOUNTERS
        self.pol.terrain_msg = terrain_msg
        self.pol.reset(random.Random(0), ENCOUNTERS["Forum"])
        self.running = True
        self.ws = self.raw = self.fcast = None
        self.names, self.counts = {}, {}
        if self.rng is not None:
            self.rng.reset()

    def feed(self, s: dict) -> bool:
        """One game-frame STATE (frames numbered consecutively): the forecast-only part of ForumPlannerPolicy.act."""
        pol = self.pol
        f = s["f"]
        if self.rng is not None:
            self.rng.feed(s)
        pol.raw[f] = s
        for old in [k for k in pol.raw if k < f - 12]:
            del pol.raw[old]
        self.raw = s
        self.f_fed = f
        self._names_of(s)
        ws = pol.backend.feed(s)
        if ws is None:
            return False
        fo = ws.stamp.frame
        raw = pol.raw.get(fo, s)
        raw["_t"] = ws.stamp.t_game_s
        pol._first_tick(ws, raw)
        pol.trk.push(raw)
        pol._wake(ws, s, None)
        pol.fc.update(ws)
        self.ws = ws
        return True

    def _names_of(self, s: dict) -> None:
        """Stable short names: the type's short name + a number in order of first appearance in play ('Reed 1')."""
        from ssbot.core.forum import FORUM_TYPES
        for e in s.get("ents") or ():
            tk = str(e.get("type_key") or "")
            iid = e.get("iid")
            if iid is None or tk not in FORUM_TYPES or int(iid) in self.names or parked(e):
                continue
            short = SHORT_NAMES.get(tk, tk.split()[-1])
            self.counts[short] = self.counts.get(short, 0) + 1
            self.names[int(iid)] = f"{short} {self.counts[short]}"

    def name(self, iid: int) -> str:
        return self.names.get(int(iid), f"#{iid}")

    def color(self, iid: int) -> tuple:
        """The enemy's own colour (BGR), by its name's order."""
        order = list(self.names)
        return ENEMY_COLORS[order.index(iid) % len(ENEMY_COLORS)] if iid in self.names else (200, 200, 200)

    def enemies(self) -> list:
        """[(iid, name, Control state, transform, colour)] of the named enemies alive and not parked now."""
        out = []
        for iid, name in self.names.items():
            tr = self.pol.fc.trackers.get(iid)
            if tr is None or tr.pos is None or tr.dead or tr.parked:
                continue
            out.append((iid, name, tr.state, tr.pos, self.color(iid)))
        return out

    def support_by(self, ks, fcast=None) -> dict:
        """{k: {iid: [ny, nx]}}: each named enemy's own support (MultiForecast.occupied_only: its placements, boxes
        and paths), hero-centre grid, inside the arena."""
        fcast = fcast or self.fcast
        g = self.grid
        out = {k: {} for k in ks}
        if fcast is None:
            return out
        tk = np.asarray(ks, np.float64) * FT
        cx = np.ascontiguousarray(np.repeat(g.gx, len(ks), axis=1))
        cy = np.ascontiguousarray(np.repeat(g.gy, len(ks), axis=1))
        for iid, *_ in self.enemies():
            o = fcast.occupied_only(cx, cy, tk, [iid])
            for j, k in enumerate(ks):
                m = o[:, j].reshape(g.shape) & g.inside
                if m.any():
                    out[k][iid] = m
        return out

    def state_of(self, iid: int) -> str | None:
        tr = self.pol.fc.trackers.get(iid)
        return tr.state if tr is not None else None

    def forecast(self):
        from ssbot.train.planner_policy import HORIZON_S
        self.fcast = self.pol.fc.forecast(HORIZON_S) if self.ws is not None else None
        return self.fcast

    # ---- zones of the current forecast ----

    def support(self, ks, fcast=None) -> dict:
        """{k: {layer: [ny, nx] bool}} (hero-centre grid)."""
        from ssbot.tools.forum_layer_audit import classify, group_occ
        fcast = fcast or self.fcast
        g = self.grid
        F = len(ks)
        out = {k: {} for k in ks}
        if fcast is None:
            return out
        tk = np.asarray(ks, np.float64) * FT
        cx = np.ascontiguousarray(np.repeat(g.gx, F, axis=1))
        cy = np.ascontiguousarray(np.repeat(g.gy, F, axis=1))
        live = np.ones(cx.shape, bool)
        occ = group_occ(fcast, cx, cy, tk, live, classify(fcast))
        tot = np.zeros(cx.shape, bool)
        for key, o in occ.items():
            lay = LAYER_OF.get(key[0], "death")
            for j, k in enumerate(ks):
                m = o[:, j].reshape(g.shape) & g.inside
                out[k][lay] = out[k][lay] | m if lay in out[k] else m
            tot |= o
        if self.vs is not None:
            self.vs.swap("m0")
            try:
                from ssbot.train.planner_policy import HORIZON_S
                f0 = self.pol.fc.forecast(HORIZON_S)
                m0 = f0.occupied(cx, cy, tk)
            finally:
                self.vs.restore()
            for j, k in enumerate(ks):
                out[k]["margins"] = (tot[:, j] & ~m0[:, j]).reshape(g.shape)
        return out

    def hero(self, s: dict | None = None) -> tuple | None:
        b = ((s or self.raw or {}).get("hero") or {}).get("box")
        return (0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])) if b else None

    def lock(self, s: dict | None = None) -> tuple[bool, bool, bool, int]:
        """(on ground, dashing, attacking, facing) of the hero now."""
        from ssbot.tools.forum_demo import _cs_index, _flags
        h = (s or self.raw or {}).get("hero") or {}
        cs = h.get("cstate")
        if not cs:
            return True, False, False, int(h.get("facing") or 0)
        fl = _flags(cs, _cs_index())
        return bool(fl["onGround"]), bool(fl["dashing"] or fl["airDashing"]), bool(fl["attacking"]), \
            int(h.get("facing") or 0)

    @staticmethod
    def aim_families() -> set:
        """(type key, family) of the families whose strike follows the hero (tools.forum_aim CANDIDATES): until their
        certified aim template is placed, where they strike is not known."""
        from ssbot.tools.forum_aim import CANDIDATES
        return {(tk, f) for tk, fams in CANDIDATES.items() for f in fams}

    def _fill_hero_centre(self, img: np.ndarray, poly: np.ndarray) -> None:
        """Mark on img [ny, nx] the hero centres whose hurtbox overlaps the convex polygon (world u)."""
        import cv2
        g = self.grid
        hx, hy = g.half
        pts = np.concatenate([poly + (sx * hx, sy * hy) for sx in (-1, 1) for sy in (-1, 1)])
        cell = np.stack([(pts[:, 0] - g.x0) / g.cell, (pts[:, 1] - g.y0) / g.cell], axis=1)
        hull = cv2.convexHull(np.rint(cell).astype(np.int32))
        cv2.fillConvexPoly(img, hull, 1)

    def _ns_lb(self, fam: str, lat: int, a_h: float) -> np.ndarray | None:
        """The commit-now inescapable zone's LOWER bound of one family ([ny, 2 NS_U / cell + 1] on the grid's rows,
        columns u = (x - anchor x) x mirror from -NS_U): the family template (the planner's coarse base, hero-centre
        space) placed with its start now at an anchor a_h above the floor, eroded back with the one-frame reach box,
        the floor solid, no walls (cached per family, latency, anchor height to 0.5 u)."""
        from ssbot.core.forum import FLOOR_Y
        key = (fam, lat, round(a_h * 2.0) / 2.0)
        if key in self._lb:
            return self._lb[key]
        tables = self.pol.fc.tables
        tid = tables.key_id(fam, None, "anchor")
        out = None
        if tid is not None:
            t = tables.template(tid)
            g = self.grid
            us = np.arange(-NS_U, NS_U + 1e-9, g.cell)
            ix = np.floor(us / t.cell).astype(np.int64) - t.ix0
            iy = np.floor((g.ys - FLOOR_Y - key[2]) / t.cell).astype(np.int64) - t.iy0
            okx, oky = (ix >= 0) & (ix < t.nx), (iy >= 0) & (iy < t.ny)
            D = np.zeros((YELLOW_F + 1, g.ny, len(us)), bool)
            if okx.any() and oky.any():
                for k in range(YELLOW_F + 1):
                    b = int(round((k * FT - t.t0) / t.bin_s))
                    if 0 <= b < t.nt:
                        D[k][np.ix_(oky, okx)] = t.plane(b)[np.ix_(iy[oky], ix[okx])]
            nz = np.flatnonzero(D.reshape(len(D), -1).any(axis=1))
            if len(nz):
                out = erode_back(D[:nz[-1] + 1], *self.reach, lat=lat, walls=False)[0]
        self._lb[key] = out
        return out

    def yellow(self, ks, fcast=None) -> tuple[dict, dict, dict]:
        """({k: committed-attack zone}, {k: not-started zone}, info) on the hero-centre grid."""
        from ssbot.core.forum import FLOOR_Y, FORUM_TYPES
        fcast = fcast or self.fcast
        g = self.grid
        com = {k: np.zeros(g.shape, bool) for k in ks}
        ns = {k: np.zeros(g.shape, bool) for k in ks}
        info = {"committed": [], "not_started": [], "ycom_by": {k: {} for k in ks}, "yns_by": {k: {} for k in ks}}
        if fcast is None:
            return com, ns, info
        # the committed attacks' certain cells, per instance: its own damage colliders now (the oracle's) carried
        # along its velocity for KIN_F frames (its flight: the Reed's stab slides along one line with the needle ahead,
        # the person 2026-10-09: "a thin diagonal strip below it"), in hero-centre space (the Minkowski sum with the hero
        # box), eroded back with the one-frame reach, the sky above the dome solid; the family templates (the union of
        # every recorded instance of the family, forum.md §29.2) are the planner's upper bound, not certain cells
        cols: dict = {}
        for poly, _clash, _label, vel, iid in damage_colliders(self.raw or {}):
            cols.setdefault(iid, []).append((poly, vel))
        mf = self.pol.fc
        aimed = self.aim_families()
        ax_, up, dn = self.reach
        for s in fcast.subjects:
            if not s.alive or not s.committed or s.iid not in cols:
                continue
            D = np.zeros((KIN_F + 1, *g.shape), np.uint8)
            for k in range(KIN_F + 1):
                for poly, vel in cols[s.iid]:
                    self._fill_hero_centre(D[k], poly + np.asarray(vel, np.float64) * (k * FT))
            if not D.any():
                continue
            Z = erode_back(D.astype(bool), ax_, up, dn, solid=~g.inside)
            for k in ks:
                if k <= KIN_F:
                    z = Z[k] & g.inside
                    if z.any():
                        com[k] |= z
                        info["ycom_by"][k][s.iid] = z
            info["committed"].append([s.iid, s.type_key, s.family, KIN_F])
        hc = self.hero()
        ground, dashing, attacking, facing = self.lock()
        for s in fcast.subjects:
            if not (s.alive and s.in_play) or s.committed or not math.isfinite(s.t_strike):
                continue
            tr = mf.trackers.get(s.iid)
            sp = FORUM_TYPES.get(s.type_key)
            if tr is None or tr.pos is None or sp is None:
                continue
            # the commit-now lower bound of every attack family it can start (the aimed ones excluded: where they
            # strike follows the hero); its thrown hazards (bells, pins, runes) are the hazard layer's, not here
            fl = sorted(set(tr.table.attack_starts.values()) - {sp.idle_family, sp.entry_family} - THROWS
                        - {f for t_, f in aimed if t_ == s.type_key})
            age = fcast.origin_t - tr.seen_T
            shown = False
            for k in ks:
                t = k * FT
                # from its earliest start on; one frame early (t_strike is at least the 1-frame sensing latency, so
                # "now" would otherwise never show a commit-now zone)
                if t + 1.5 * FT < s.t_strike:
                    continue
                ax = tr.pos[0] + tr.vel[0] * (age + t)
                ay = tr.pos[1] + tr.vel[1] * (age + t)
                toward = hc is not None and facing != 0 and np.sign(ax - hc[0]) == facing
                code = 3 if not ground else 2 if (dashing and toward) else 1 if attacking else 0
                mir = 1 if hc is None or hc[0] >= ax else -1      # the attack faces the hero at its commit
                col = np.rint(((g.xs - ax) * mir + NS_U) / g.cell).astype(np.int64)
                z = np.zeros(g.shape, bool)
                for fam in fl:
                    lb = self._ns_lb(fam, LOCK_LAT[code], float(ay - FLOOR_Y))
                    if lb is None:
                        continue
                    ok = (col >= 0) & (col < lb.shape[1])
                    z[:, ok] |= lb[:, col[ok]]
                z &= g.inside
                if not z.any():
                    continue
                ns[k] |= z
                info["yns_by"][k][s.iid] = z
                shown = True
            if shown:
                info["not_started"].append([s.iid, s.type_key, round(float(s.t_strike), 3)])
        return com, ns, info

    def range_layer(self, ks, sweep: int | None = None, hero: bool = True) -> dict:
        """The attack-range estimate of every tracked enemy (world polygons; all empty without --range), every k in
        one pass (RangeTracker.ladder):
          range        {k: [(iid, name, colour, raw outlines, hero-centre outlines ([] when not hero), label)]}
          range_same   {k: {iid: the earlier k of ks whose estimate is the same set of cells}} (drawn once)
          range_swept  [(iid, name, colour, outlines of the union over 0..sweep, label)] ([] without sweep)
          range_sweep  sweep"""
        out: dict = {k: [] for k in ks}
        same: dict = {k: {} for k in ks}
        swept_out: list = []
        res = {"range": out, "range_same": same, "range_swept": swept_out, "range_sweep": sweep}
        if self.rng is None:
            return res
        from ssbot.combat.attack_range import contours, hero_space, same_mask
        per, swept = self.rng.ladder(ks, sweep)
        seen: dict = {}                       # iid -> [(k, raw mask)] of the distinct estimates so far
        for k in sorted(ks):
            for est in per[k]:
                lab = (f"{est.fam} {est.branch or ('?' if est.fam else '')} b{est.b}" if est.fam else "idle body")
                if est.haz is not None and est.haz.m.size and est.haz.m.any():
                    lab += " + hazards"
                prev = seen.setdefault(est.iid, [])
                for k0, m0 in prev:
                    if same_mask(m0, est.raw):
                        same[k][est.iid] = k0
                        break
                else:
                    prev.append((k, est.raw))
                out[k].append((est.iid, self.name(est.iid), self.color(est.iid), contours(est.raw),
                               contours(hero_space(est.raw)) if hero else [], lab))
        for iid, m in swept.items():
            swept_out.append((iid, self.name(iid), self.color(iid), contours(m), f"path 0-{sweep}"))
        return res

    def aim_layer(self, lat: int = AIM_LAT) -> list:
        """aim_zones_of with the enemy's name and colour: [(iid, name, colour, {class: polys}, label, (x, y))]."""
        return [(iid, self.name(iid), self.color(iid), polys, lab, pos)
                for iid, polys, lab, pos in aim_zones_of(self.rng, lat)]

    def compute(self, ks=KS, support: bool = True, yellow: bool = True, forecast: bool = True,
                range_ks=None, sweep: int | None = None, range_hero: bool = True, aim: bool = False) -> dict:
        """Everything drawn for the current frame: forecast, support per k, yellow per k, the colliders, the attack
        range (--range; at range_ks (default ks), with sweep its swept path over 0..sweep, range_hero=False: no
        hero-centre outlines).
        forecast=False (the range layer alone): no planner forecast, no support, no yellow."""
        t0 = time.perf_counter()
        fc = self.forecast() if forecast else None
        if not forecast:
            support = yellow = False
        t1 = time.perf_counter()
        sup = self.support(ks, fc) if support else {k: {} for k in ks}
        t2 = time.perf_counter()
        com, ns, info = self.yellow(ks, fc) if yellow else ({}, {}, {})
        t3 = time.perf_counter()
        rng = self.range_layer(ks if range_ks is None else range_ks, sweep, range_hero)
        rng["aim"] = self.aim_layer() if aim else []
        t4 = time.perf_counter()
        s = self.raw or {}
        return {"f": s.get("f"), "f_raw": s.get("_f_raw", s.get("f")), "hero": self.hero(), "ks": tuple(ks),
                "support": sup, "ycom": com, "yns": ns, "ycom_by": info.pop("ycom_by", {}),
                "yns_by": info.pop("yns_by", {}), "info": info, "cols": damage_colliders(s),
                "names": dict(self.names), "states": {i: self.state_of(i) for i in self.names},
                "enemies": self.enemies(), **rng,
                "cam": s.get("cam"), "running": fc is not None or not forecast,
                "ms": {"forecast": round((t1 - t0) * 1e3, 1), "support": round((t2 - t1) * 1e3, 1),
                       "yellow": round((t3 - t2) * 1e3, 1), "range": round((t4 - t3) * 1e3, 1)}}


# ------------------------------------------------------------------------------------------------ drawing

class View:
    """What is drawn (the live keys and the render options)."""
    MODES = ("yellow+red", "yellow", "red", "support", "all", "range+red", "range")

    def __init__(self, mode: str = "yellow+red", k: int = 0, all_k: bool = False, swept: bool = False,
                 aim: bool = False):
        self.on = True
        self.aim = aim              # range: the aim zones of the pending aimed moves (key 8)
        self.mode = mode
        self.k = k
        self.all_k = all_k          # range: every look-ahead of KS at once (key 0)
        self.swept = swept          # range: the swept path over 0..k (0..max KS with all_k; key 9)
        self.layers = {lay: True for lay in LAYERS}
        self.frozen = False
        self.note = ""

    def show(self, what: str) -> bool:
        if what == "support":
            return self.mode in ("support", "all")
        return self.mode == "all" or what in self.mode.split("+")

    def needs_forecast(self) -> bool:
        """The planner's forecast is drawn (support or yellow); the range layer and red need none."""
        return self.show("support") or self.show("yellow")

    def cycle(self) -> None:
        self.mode = self.MODES[(self.MODES.index(self.mode) + 1) % len(self.MODES)]

    def range_ks(self) -> tuple:
        """The look-aheads of the range layer: every k of KS at once (all_k) or the k shown."""
        return tuple(KS) if self.all_k and self.show("range") else (self.k,)

    def range_sweep(self) -> int | None:
        """The swept path's last look-ahead (None: no swept path)."""
        if not (self.swept and self.show("range")):
            return None
        return max(KS) if self.all_k else self.k

    def range_aim(self) -> bool:
        return self.aim and self.show("range")


def homography(grid: Grid, cam: dict, out_size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """(world z=0 -> output px, grid image px -> output px) 3x3 maps from the STATE camera; the grid image has row 0
    at the top (the highest hero centre)."""
    import cv2
    from ssbot.tools.projector import project_cam
    screen = cam.get("screen") or RENDER
    sx, sy = out_size[0] / float(screen[0]), out_size[1] / float(screen[1])
    x1, y1 = grid.xs[-1], grid.ys[-1]
    w = np.array([[grid.x0, grid.y0], [x1, grid.y0], [x1, y1], [grid.x0, y1]], np.float64)
    px, _ = project_cam(w, cam, screen)
    px = px * np.array([sx, sy])
    Hw = cv2.getPerspectiveTransform(w.astype(np.float32), px.astype(np.float32)).astype(np.float64)
    A = np.array([[grid.cell, 0.0, grid.x0], [0.0, -grid.cell, grid.y0 + (grid.ny - 1) * grid.cell],
                  [0.0, 0.0, 1.0]])
    return Hw, Hw @ A


def _to_px(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    p = np.hstack([np.asarray(pts, np.float64).reshape(-1, 2), np.ones((len(pts), 1))]) @ H.T
    return p[:, :2] / p[:, 2:3]


def _blend_poly(img: np.ndarray, pts: np.ndarray, color, alpha: float, outline: int = 0) -> None:
    """Premultiplied BGRA img: fill the polygon with color at alpha (over), in its bounding box only."""
    import cv2
    h, w = img.shape[:2]
    p = np.round(pts).astype(np.int32)
    x0, y0 = max(int(p[:, 0].min()) - 2, 0), max(int(p[:, 1].min()) - 2, 0)
    x1, y1 = min(int(p[:, 0].max()) + 3, w), min(int(p[:, 1].max()) + 3, h)
    if x1 <= x0 or y1 <= y0:
        return
    roi = img[y0:y1, x0:x1]
    m = np.zeros(roi.shape[:2], np.uint8)
    cv2.fillPoly(m, [p - [x0, y0]], 1)
    sel = m.view(bool)
    if sel.any():
        # roi * (1 - alpha) + colour * alpha where the polygon is (cv2 on the box, then copied through the mask)
        src = np.empty_like(roi)
        src[:] = np.array([*color, 255.0]) * alpha
        np.copyto(roi, cv2.addWeighted(roi, 1.0 - alpha, src, 1.0, 0.0), where=sel[..., None])
    if outline:
        cv2.polylines(img, [p], True, (*[int(c * 0.75) for c in color], 255), outline, cv2.LINE_AA)


def _dashed(img: np.ndarray, pts: np.ndarray, color, th: int, dash: float, gap: float) -> None:
    """A closed dashed outline (px points): a straight dash from every (dash + gap) px along its length to dash px
    further (a dash over a corner cuts it), all in one polylines call."""
    import cv2
    p = np.asarray(pts, np.float64).reshape(-1, 2)
    if len(p) < 2:
        return
    p = np.vstack([p, p[:1]])
    cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    if cum[-1] <= 0:
        return
    t0 = np.arange(0.0, cum[-1], dash + gap)
    t = np.stack([t0, np.minimum(t0 + max(dash, 1.0), cum[-1])], axis=1).ravel()
    q = np.stack([np.interp(t, cum, p[:, 0]), np.interp(t, cum, p[:, 1])], axis=1)
    cv2.polylines(img, list(np.round(q).astype(np.int32).reshape(-1, 2, 2)), False, color, th, cv2.LINE_AA)


def _outline(img: np.ndarray, q: np.ndarray, col, style: tuple, s: float) -> None:
    """One range outline in a RANGE_STYLE (line, px at 1080p, opacity) on the premultiplied image."""
    import cv2
    line, px, a = style
    c = (*[int(v * a) for v in col], int(255 * a))
    th = max(1, int(round(px * s)))
    if line == "solid":
        cv2.polylines(img, [np.round(q).astype(np.int32)], True, c, th, cv2.LINE_AA)
    else:
        _dashed(img, q, c, th, (12.0 if line == "dash" else 3.0) * s, (7.0 if line == "dash" else 5.0) * s)


def _tag(img: np.ndarray, text: str, at: tuple, col, s: float, placed: list) -> None:
    """A small label at px `at` (its top left), moved down past the labels already placed (no overlap)."""
    import cv2
    fs = 0.42 * s
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
    x, y = int(at[0]), int(at[1])
    for _ in range(8):
        if not any(x < bx + bw + 4 and bx < x + w + 4 and y < by + bh + 2 and by < y + h + 2
                   for bx, by, bw, bh in placed):
            break
        y += h + 3
    placed.append((x, y, w, h))
    th = max(1, int(round(s)))
    cv2.putText(img, text, (x, y + h), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0, 255), th + 2, cv2.LINE_AA)
    cv2.putText(img, text, (x, y + h), cv2.FONT_HERSHEY_SIMPLEX, fs, (*col, 255), th, cv2.LINE_AA)


def draw_range(img: np.ndarray, fr: dict, Hw: np.ndarray, view: View) -> None:
    """The attack-range layer. Single k: the estimate at view.k filled (+ its hero-centre outline thin). All k
    (view.all_k, the person 2026-10-10): every look-ahead at once per enemy in its colour, +0 filled and the later
    ones as outlines by RANGE_STYLE (solid, dashed, dotted, fainter as k grows), each labelled +k; a look-ahead
    whose estimate is the same set of cells as an earlier one is drawn once, labelled +0=6=... Swept (view.swept):
    the union of the estimate over 0..K, a light dashed outline over a faint fill, labelled "path 0-K"."""
    import cv2
    H = img.shape[0]
    s = H / 1080.0
    rng = fr.get("range") or {}
    same = fr.get("range_same") or {}
    placed: list = []
    for _iid, _name, col, polys, lab in (fr.get("range_swept") or ()) if view.swept else ():
        light = tuple(int(c + (255 - c) * 0.4) for c in col)
        qs = [_to_px(Hw, p) for p in polys]
        for q in qs:
            _blend_poly(img, q, light, A_SWEPT)
            _dashed(img, q, (*light, 255), max(1, int(round(2 * s))), 6.0 * s, 4.0 * s)
        if qs:
            q = max(qs, key=len)
            j = int(np.lexsort((q[:, 0], -q[:, 1]))[0])        # its lowest point (the leftmost of those)
            _tag(img, lab, (q[j, 0], q[j, 1] + 2), light, s, placed)
    if view.all_k:
        ks = sorted(rng)
    else:
        k = view.k if view.k in rng else (sorted(rng) or [None])[0]
        ks = [] if k is None else [k]
    th = max(1, int(round(2 * s)))
    for rank, k in enumerate(ks):
        for iid, _name, col, raw, hero, _lab in rng.get(k, ()):
            if not view.all_k:
                for p in raw:
                    _blend_poly(img, _to_px(Hw, p), col, A_RANGE, outline=th)
                for p in hero:
                    q = np.round(_to_px(Hw, p)).astype(np.int32)
                    cv2.polylines(img, [q], True, (*col, 255), 1, cv2.LINE_AA)
                continue
            if iid in same.get(k, {}):
                continue                     # drawn with the earlier k
            style = RANGE_STYLE[min(rank, len(RANGE_STYLE) - 1)]
            qs = [_to_px(Hw, p) for p in raw]
            for q in qs:
                if rank == 0:
                    _blend_poly(img, q, col, A_RANGE)
                _outline(img, q, col, style, s)
            if qs:
                grp = [k] + [k2 for k2 in ks if same.get(k2, {}).get(iid) == k]
                q = max(qs, key=len)
                j = int(np.lexsort((-q[:, 0], q[:, 1]))[0])     # its highest point (the rightmost of those)
                _tag(img, "+" + "=".join(map(str, grp)), (q[j, 0] + 3, q[j, 1] - 14 * s), col, s, placed)


AIM_STYLE = {"ground": ("solid", 3.0, 1.0), "low": ("solid", 2.0, 0.9), "high": ("dash", 2.0, 0.8)}
A_AIM = 0.35


def draw_aim(img: np.ndarray, fr: dict, Hw: np.ndarray) -> None:
    """The aim zones (tools.aim_zones; the person 2026-10-10): per enemy in a pending aimed antic, its composite zone
    at its position now: ground band filled + thick outline, low air solid, high air dashed, in a light tint of the
    enemy's colour; an empty zone is only labelled "zone 0"."""
    H = img.shape[0]
    s = H / 1080.0
    placed: list = []
    for _iid, _name, col, polys, lab, pos in fr.get("aim") or ():
        light = tuple(int(c + (255 - c) * 0.55) for c in col)
        for cls, ps in polys.items():
            for p in ps:
                q = _to_px(Hw, p)
                if cls == "ground":
                    _blend_poly(img, q, light, A_AIM)
                _outline(img, q, light, AIM_STYLE[cls], s)
        at = _to_px(Hw, np.array([[pos[0], pos[1] - 1.2]]))[0]
        _tag(img, lab, (at[0] - 60 * s, at[1]), light, s, placed)


def zone_masks(fr: dict, view: View) -> list[tuple[str, np.ndarray, tuple, float]]:
    """[(name, mask [ny, nx] row 0 = lowest, colour, alpha)] in drawing order for view.k."""
    k = view.k if view.k in fr["ks"] else fr["ks"][0]
    out = []
    if view.show("support"):
        for lay in LAYERS:
            m = fr["support"].get(k, {}).get(lay)
            if m is not None and view.layers.get(lay) and m.any():
                out.append((lay, m, COLORS[lay], A_SUPPORT))
    if view.show("yellow"):
        y = None
        for part in ("ycom", "yns"):
            m = fr.get(part, {}).get(k)
            if m is not None:
                y = m if y is None else (y | m)
        if y is not None and y.any():
            out.append(("yellow", y, COLORS["yellow"], A_YELLOW))
    return out


def render(fr: dict, grid: Grid, out_size: tuple[int, int], view: View, legend: list[str] | None = None,
           cam: dict | None = None) -> np.ndarray:
    """The overlay as premultiplied BGRA [h, w, 4] uint8 (fully transparent where nothing is drawn)."""
    import cv2
    W, H = out_size
    img = np.zeros((H, W, 4), np.uint8)
    cam = cam or fr.get("cam")
    if not view.on:
        return img
    if cam is not None and cam.get("V") and cam.get("P"):
        Hw, Hg = homography(grid, cam, out_size)
        masks = zone_masks(fr, view)
        if masks:
            gimg = np.zeros((grid.ny, grid.nx, 4), np.float32)
            for _, m, col, a in masks:
                mm = m[::-1]
                src = np.array([*col, 255.0], np.float32) * a
                gimg[mm] = gimg[mm] * (1.0 - a) + src
            img = cv2.warpPerspective(gimg.astype(np.uint8), Hg, (W, H), flags=cv2.INTER_NEAREST,
                                      borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
            th = max(1, int(round(H / 1080)))
            for _, m, col, a in masks:
                cs, _ = cv2.findContours(m[::-1].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                pl = [np.round(_to_px(Hg, c.reshape(-1, 2) + 0.0)).astype(np.int32) for c in cs if len(c) >= 2]
                if pl:
                    dark = tuple(int(c * 0.8) for c in col)
                    cv2.polylines(img, pl, True, (*dark, 255), th, cv2.LINE_AA)
        if view.show("range"):
            draw_range(img, fr, Hw, view)
            if view.aim:
                draw_aim(img, fr, Hw)
        if view.show("red") or view.show("range"):
            # the range modes compare the prediction with the truth: every real damage collider NOW, the clashable
            # ones too (orange), no sweep (the person, 2026-10-10)
            th = max(1, int(round(1.5 * H / 1080)))
            truth = view.show("range")
            for poly, clash, _, vel, *_ in fr.get("cols") or ():
                if clash and not truth:
                    continue
                col = COLORS["clash"] if clash else COLORS["red"]
                if not truth:
                    hull = sweep_hull(poly, vel)
                    _blend_poly(img, _to_px(Hw, hull), col, A_SWEEP)
                _blend_poly(img, _to_px(Hw, poly), col, A_RED, outline=th)
        fs = 0.5 * H / 1080.0
        for iid, name, st, pos, col in fr.get("enemies") or ():
            if view.show("red") or view.show("yellow") or view.show("range"):
                p = _to_px(Hw, np.array([[pos[0], pos[1] + 1.6]]))[0]
                cv2.putText(img, f"{name} {st or ''}", (int(p[0]) - int(40 * fs * 2), int(p[1])),
                            cv2.FONT_HERSHEY_SIMPLEX, fs, (*col, 255), max(1, int(round(H / 1080))), cv2.LINE_AA)
        hc = fr.get("hero")
        if hc is not None:
            p = _to_px(Hw, np.array([hc]))[0]
            r = max(4, int(round(5 * H / 1080)))
            c = (int(round(p[0])), int(round(p[1])))
            cv2.circle(img, c, r + 2, (0, 0, 0, 255), -1, cv2.LINE_AA)
            cv2.circle(img, c, r, (255, 255, 255, 255), -1, cv2.LINE_AA)
    if legend is not None:
        draw_legend(img, legend, view)
    return img


def legend_lines(fr: dict | None, view: View, config: str, extra: str = "") -> list[tuple[str, tuple | None]]:
    k = view.k
    kt = (f"range k=+{'/'.join(map(str, KS))} at once" if view.all_k and view.show("range")
          else f"k=+{k} f ({k / 60:.2f} s)")
    lines = [(f"ZONES  {kt}  mode {view.mode}" + ("  FROZEN" if view.frozen else "")
              + (f"  {extra}" if extra else ""), None)]
    if view.show("yellow"):
        lines.append((NAMES["yellow"] + " (hero-centre space, lower bound: committed = each attack's own colliders "
                      "along its flight, 12 f; not started: commit-now erosion for the lock now)", COLORS["yellow"]))
    if view.show("range"):
        if view.all_k:
            lines.append(("ATTACK RANGE at EVERY look-ahead (enemy colour, no margin): +0 filled, +6 solid, "
                          "+12/+18 dashed, +36 dotted; +0=6 = same region", None))
        else:
            lines.append(("ATTACK RANGE per enemy (its colour; filled = the raw estimate of where its damage colliders "
                          "can be at +k, no margin; thin line = where the hero transform must not be)", None))
        if view.swept:
            K = max(KS) if view.all_k else view.k
            lines.append((f"SWEPT path 0-{K} (light dashed + faint fill): the union of the estimate over every frame "
                          f"0..{K}, out and back", None))
        lines.append(("REAL damage colliders NOW: not clashable", COLORS["red"]))
        lines.append(("REAL damage colliders NOW: clashable", COLORS["clash"]))
        rng = (fr or {}).get("range") or {}
        k = min(rng) if view.all_k and rng else (view.k if view.k in rng else None)
        for _iid, name, col, _raw, _hero, lab in rng.get(k, ())[:6]:
            lines.append((f"{name}: {lab}", col))
        if view.aim:
            lines.append((f"AIM ZONES lat{AIM_LAT} (light tint, at the enemy now): no escape after its decision; each "
                          "cell by its own height: ground band (HeroBox centre -0.25..+0.25 u of standing, filled), "
                          "low air 0.25-1.5 u no dash (solid), high air >= 1.5 u no dash (dashed); zone 0 = empty",
                          None))
            for _iid, name, col, _p, lab, _pos in (fr or {}).get("aim", ())[:4]:
                lines.append((f"{name}: {lab}", col))
        lines.append((f"0 all look-aheads ({'on' if view.all_k else 'off'})   9 swept path "
                      f"({'on' if view.swept else 'off'})   8 aim zones ({'on' if view.aim else 'off'})   "
                      "1-5 single k", None))
    if view.show("red"):
        lines.append((NAMES["red"] + " (the colliders themselves)", COLORS["red"]))
    if view.show("support"):
        for i, lay in enumerate(LAYERS):
            on = view.layers.get(lay)
            lines.append((f"Ctrl+{i + 1} {NAMES[lay]}{'' if on else '  (off)'}", COLORS[lay] if on else (90, 90, 90)))
    lines.append(("white dot = hero centre   F8 on/off  F9 mode  F10 freeze  F11 step  1-5 k  0 all k  9 swept  8 aim  "
                  "Ctrl+1-7 layers", None))
    lines.append((config, None))
    if fr is not None and fr.get("info"):
        inf = fr["info"]
        c = ", ".join(f"{x[1].replace('Song ', '')}:{x[2]}" for x in inf.get("committed", [])[:4])
        lines.append((f"committed: {c or '-'}   not started: {len(inf.get('not_started', []))}", None))
    for iid, name, st, pos, col in (fr or {}).get("enemies", [])[:8]:
        lines.append((f"{name}: {st or '?'}", col))
    return lines


def draw_legend(img: np.ndarray, lines, view: View) -> None:
    import cv2
    H = img.shape[0]
    s = H / 1080.0
    fs, lh = 0.45 * s, int(round(18 * s))
    # top right, under the frame marker's corner (the HUD is top left; the hero lives near the floor)
    w = int(round(820 * s))
    x0, y0 = img.shape[1] - w - int(round(12 * s)), int(round(48 * s)) + lh
    roi = img[max(y0 - lh, 0):y0 + lh * (len(lines) - 1) + int(round(6 * s)), x0 - 6:x0 + w]
    roi[:] = (roi * 0.5 + np.array([0, 0, 0, 255.0]) * 0.5).astype(np.uint8)
    for i, (t, col) in enumerate(lines):
        y = y0 + i * lh
        tx = x0
        if col is not None:
            cv2.rectangle(img, (x0, y - int(11 * s)), (x0 + int(14 * s), y + int(2 * s)), (*col, 255), -1)
            tx = x0 + int(20 * s)
        cv2.putText(img, t, (tx, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (235, 235, 235, 255), max(1, int(round(s))),
                    cv2.LINE_AA)


def composite(frame_bgr: np.ndarray, bgra: np.ndarray) -> np.ndarray:
    a = bgra[..., 3:4].astype(np.float32) / 255.0
    return np.clip(frame_bgr.astype(np.float32) * (1.0 - a) + bgra[..., :3].astype(np.float32), 0, 255
                   ).astype(np.uint8)


# ------------------------------------------------------------------------------------------------ live window

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
gdi32 = ctypes.windll.gdi32 if sys.platform == "win32" else None
WS_EX = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000  # LAYERED TRANSPARENT TOPMOST TOOLWINDOW NOACTIVATE
WS_POPUP = 0x80000000
WDA_EXCLUDEFROMCAPTURE = 0x11
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class _BLEND(ctypes.Structure):
    _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_ubyte)]


class _BMI(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("w", wintypes.LONG), ("h", wintypes.LONG), ("planes", wintypes.WORD),
                ("bits", wintypes.WORD), ("comp", wintypes.DWORD), ("img", wintypes.DWORD), ("xppm", wintypes.LONG),
                ("yppm", wintypes.LONG), ("used", wintypes.DWORD), ("imp", wintypes.DWORD), ("pad", wintypes.DWORD * 4)]


class _WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("proc", WNDPROC), ("cls", ctypes.c_int), ("wnd", ctypes.c_int),
                ("inst", wintypes.HINSTANCE), ("icon", wintypes.HICON), ("cursor", wintypes.HANDLE),
                ("bg", wintypes.HBRUSH), ("menu", wintypes.LPCWSTR), ("name", wintypes.LPCWSTR)]


def _setup_win32() -> None:
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                           ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                           wintypes.COLORREF, ctypes.POINTER(_BLEND), wintypes.DWORD]
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                    wintypes.UINT]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetForegroundWindow.restype = wintypes.HWND
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(_BMI), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]


class LayeredWindow:
    """A click-through, always-on-top, per-pixel-alpha window over a screen rect, excluded from screen capture
    (SetWindowDisplayAffinity WDA_EXCLUDEFROMCAPTURE: Desktop Duplication, i.e. ffmpeg ddagrab, does not see it).
    Create, show and pump it on one thread."""

    _proc = None

    def __init__(self, rect: list[int]):
        _setup_win32()
        if LayeredWindow._proc is None:
            LayeredWindow._proc = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))
            wc = _WNDCLASS()
            wc.proc = LayeredWindow._proc
            wc.inst = ctypes.windll.kernel32.GetModuleHandleW(None)
            wc.name = "SsbotZoneOverlay"
            user32.RegisterClassW(ctypes.byref(wc))
        self.rect = [0, 0, 0, 0]
        x, y, w, h = rect
        self.hwnd = user32.CreateWindowExW(WS_EX, "SsbotZoneOverlay", "ssbot zones", WS_POPUP, x, y, w, h, None,
                                           None, ctypes.windll.kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise OSError("CreateWindowExW failed")
        self.excluded = bool(user32.SetWindowDisplayAffinity(self.hwnd, WDA_EXCLUDEFROMCAPTURE))
        user32.ShowWindow(self.hwnd, 4)     # SW_SHOWNOACTIVATE
        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        self.bmp = None
        self.bits = ctypes.c_void_p()
        self.resize(rect)

    def resize(self, rect: list[int]) -> None:
        if list(rect) == self.rect:
            return
        x, y, w, h = rect
        if self.bmp is not None and (w, h) != tuple(self.rect[2:]):
            gdi32.DeleteObject(self.bmp)
            self.bmp = None
        if self.bmp is None:
            bmi = _BMI()
            bmi.size = 40
            bmi.w, bmi.h, bmi.planes, bmi.bits = w, -h, 1, 32
            self.bmp = gdi32.CreateDIBSection(self.mem_dc, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
            gdi32.SelectObject(self.mem_dc, self.bmp)
        user32.SetWindowPos(self.hwnd, wintypes.HWND(-1), x, y, w, h, 0x0010 | 0x0040)  # TOPMOST, NOACTIVATE|SHOW
        self.rect = list(rect)

    def show(self, bgra: np.ndarray) -> None:
        x, y, w, h = self.rect
        if bgra.shape[:2] != (h, w):
            raise ValueError(f"image {bgra.shape[:2]} for a {w}x{h} window")
        ctypes.memmove(self.bits, np.ascontiguousarray(bgra).ctypes.data, w * h * 4)
        blend = _BLEND(0, 0, 255, 1)
        ok = user32.UpdateLayeredWindow(self.hwnd, self.screen_dc, ctypes.byref(wintypes.POINT(x, y)),
                                        ctypes.byref(wintypes.SIZE(w, h)), self.mem_dc,
                                        ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), 2)
        if not ok:
            raise OSError(f"UpdateLayeredWindow failed ({ctypes.GetLastError()})")

    def pump(self) -> None:
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def close(self) -> None:
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self.bmp is not None:
            gdi32.DeleteObject(self.bmp)
            self.bmp = None
        gdi32.DeleteDC(self.mem_dc)
        user32.ReleaseDC(None, self.screen_dc)


class Keys:
    """Rising edges of polled keys (GetAsyncKeyState: the game still receives them)."""

    def __init__(self):
        self.down: dict[int, bool] = {}

    def pressed(self, vk: int) -> bool:
        d = bool(user32.GetAsyncKeyState(vk) & 0x8000)
        was = self.down.get(vk, False)
        self.down[vk] = d
        return d and not was

    @staticmethod
    def held(vk: int) -> bool:
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class LiveOverlay:
    """The overlay inside the human session process: fed by the session's own OracleLink (subscribe_state /
    subscribe_raw: no second IPC client), computing and drawing on its own thread."""

    def __init__(self, link, game_pid: int, speed: float = 1.0, crest: str = "Wanderer", threads: int = 4,
                 every: int = 3, margins: bool = False, log_path: Path | None = None, range_layer: bool = False,
                 mode: str | None = None, k: int = 0, all_k: bool = False, swept: bool = False, aim: bool = False):
        self.link, self.pid = link, game_pid
        self.speed = speed if speed and speed > 0 else 1.0
        self.crest, self.threads, self.every, self.margins = crest, threads, max(1, every), margins
        self.range_layer = range_layer
        self.view = View(mode=mode if mode in View.MODES else ("range+red" if range_layer else "yellow+red"), k=k,
                         all_k=all_k, swept=swept, aim=aim)
        self.q: queue.SimpleQueue = queue.SimpleQueue()
        self.cmds: queue.SimpleQueue = queue.SimpleQueue()
        self.terrain: dict | None = None
        self.stop_ev = threading.Event()
        self.stats = {"computed": 0, "fed": 0, "ms": [], "range_ms": [], "upd_ms": [], "max_backlog": 0, "errors": [],
                      "excluded_from_capture": None, "starts": 0}
        self.log_path = log_path
        from ssbot.tools.launcher import set_dpi_aware
        set_dpi_aware()     # window rects in physical px before the overlay window exists (idempotent)
        link.subscribe_state(self.q.put)
        link.subscribe_raw(self._raw)
        self.thread = threading.Thread(target=self._run, name="ZoneOverlay", daemon=True)
        self.thread.start()

    def _raw(self, msg_type: int, raw: bytes) -> None:
        from ssbot.ipc.framing import HEADER, MsgType
        if msg_type != MsgType.TERRAIN:
            return
        import msgpack
        try:
            m = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
        except Exception:  # noqa: BLE001 - a TERRAIN we cannot read: the overlay runs without terrain
            return
        if (m.get("scene_raw") or m.get("scene")) in FORUM_SCENES:
            self.terrain = m

    def command(self, text: str) -> str:
        self.cmds.put(text)
        return "queued"

    def close(self) -> dict:
        self.stop_ev.set()
        self.thread.join(timeout=10)
        st = dict(self.stats)
        rm = st.pop("range_ms", [])
        if rm:
            st["range_ms_p50"], st["range_ms_p95"] = float(np.percentile(rm, 50)), float(np.percentile(rm, 95))
        ms = st.pop("ms")
        um = st.pop("upd_ms")
        if ms:
            st["compute_ms_p50"], st["compute_ms_p95"] = float(np.percentile(ms, 50)), float(np.percentile(ms, 95))
        if um:
            st["draw_ms_p50"], st["draw_ms_p95"] = float(np.percentile(um, 50)), float(np.percentile(um, 95))
        return st

    # ---- the worker ----

    def _client(self) -> tuple[int, list[int] | None]:
        from ssbot.tools.launcher import find_window
        hwnd = find_window(self.pid)
        if not hwnd:
            return 0, None
        pt, rc = wintypes.POINT(0, 0), wintypes.RECT()
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)) or not user32.GetClientRect(hwnd, ctypes.byref(rc)):
            return hwnd, None
        w, h = rc.right - rc.left, rc.bottom - rc.top
        return hwnd, ([pt.x, pt.y, w, h] if w > 0 and h > 0 and pt.x > -10000 else None)

    def _rpc_scale(self, s: float) -> None:
        try:
            self.link.rpc("time.scale", scale=float(s))
        except Exception as e:  # noqa: BLE001 - shown in the legend, the session goes on
            self.view.note = f"time.scale failed: {e}"

    def _apply(self, text: str) -> None:
        p = text.split()
        if not p:
            return
        if p[0] == "k" and len(p) > 1:
            self.view.k = int(p[1])
        elif p[0] == "mode" and len(p) > 1 and p[1] in View.MODES:
            self.view.mode = p[1]
        elif p[0] == "all":
            self.view.all_k = not self.view.all_k if len(p) < 2 else p[1] == "on"
        elif p[0] == "swept":
            self.view.swept = not self.view.swept if len(p) < 2 else p[1] == "on"
        elif p[0] == "aim":
            self.view.aim = not self.view.aim if len(p) < 2 else p[1] == "on"
        elif p[0] == "layer" and len(p) > 1 and p[1] in LAYERS:
            self.view.layers[p[1]] = not self.view.layers[p[1]]
        elif p[0] in ("on", "off"):
            self.view.on = p[0] == "on"
        elif p[0] == "freeze":
            self._freeze(not self.view.frozen)
        elif p[0] == "step":
            self._step()
        elif p[0] == "speed" and len(p) > 1:
            self.speed = float(p[1])
        self.dirty = True

    def _freeze(self, on: bool) -> None:
        self._rpc_scale(FREEZE_SCALE if on else self.speed)
        self.view.frozen = on
        self.stepping = 0
        self.dirty = True

    def _step(self) -> None:
        if not self.view.frozen:
            return
        self.stepping = max(1, int(round(1.0 / self.speed)))
        self._rpc_scale(self.speed)

    def _keys(self, keys: Keys, hwnd: int) -> None:
        if not hwnd or user32.GetForegroundWindow() != hwnd:
            return
        if keys.pressed(0x77):
            self.view.on = not self.view.on
            self.dirty = True
        if keys.pressed(0x78):
            self.view.cycle()
            self.dirty = True
        if keys.pressed(0x79):
            self._freeze(not self.view.frozen)
        if keys.pressed(0x7A):
            self._step()
        ctrl = keys.held(0x11)
        if keys.pressed(KEY_ALL_K) and not ctrl:
            self.view.all_k = not self.view.all_k
            self.dirty = True
        if keys.pressed(KEY_SWEPT) and not ctrl:
            self.view.swept = not self.view.swept
            self.dirty = True
        if keys.pressed(KEY_AIM) and not ctrl:
            self.view.aim = not self.view.aim
            self.dirty = True
        for vk, k in KEY_K.items():
            if keys.pressed(vk):
                if ctrl:
                    lay = LAYERS[vk - 0x31]
                    self.view.layers[lay] = not self.view.layers[lay]
                else:
                    self.view.k = k
                self.dirty = True
        for vk, lay in ((0x36, LAYERS[5]), (0x37, LAYERS[6])):
            if keys.pressed(vk) and ctrl:
                self.view.layers[lay] = not self.view.layers[lay]
                self.dirty = True

    def _take(self, s: dict) -> bool:
        """One raw STATE: battle tracking, grouping into game frames, feeding. True when a game frame was fed."""
        self.last_raw = s
        b = battle(s)
        if scene_of(s) not in FORUM_SCENES or not b or not b.get("started"):
            if self.bid is not None:
                self.bid = None
                if self.eng is not None:
                    self.eng.running = False
            return False
        if b.get("id") != self.bid:
            self.bid = b.get("id")
            self.eng.start(self.terrain)
            self.stats["starts"] += 1
            self.group, self.f_next = [], 0
        ts = float(s.get("ts") or 0.0)
        if self.view.frozen and not self.stepping:
            return False
        if ts < 0.05 and self.view.frozen:
            return False
        self.group.append(s)
        n = max(1, int(round(1.0 / max(self.speed, 0.1))))
        if len(self.group) < n:
            return False
        m = merge_states(self.group, self.f_next, max(self.speed, 0.1))
        self.group = []
        self.f_next += 1
        self.eng.feed(m)
        self.stats["fed"] += 1
        if self.stepping:
            self.stepping = 0
            self._rpc_scale(FREEZE_SCALE)
            self.dirty = True
        return True

    def _run(self) -> None:
        self.eng = None
        self.bid = None
        self.group, self.f_next = [], 0
        self.stepping = 0
        self.dirty = True
        self.last_raw = None
        win = None
        keys = Keys()
        fr = None
        since = 0
        t_place = 0.0
        hwnd, rect = 0, None
        try:
            self.eng = ZoneEngine(crest=self.crest, threads=self.threads, margins=self.margins,
                                  range_layer=self.range_layer)
            config = self.eng.config_text()
            print(f"overlay ready ({config})")
            while not self.stop_ev.is_set():
                now = time.perf_counter()
                if now - t_place > 1.0 or win is None:
                    t_place = now
                    hwnd, rect = self._client()
                    if rect is not None:
                        if win is None:
                            win = LayeredWindow(rect)
                            self.stats["excluded_from_capture"] = win.excluded
                            if not win.excluded:
                                print("WARNING overlay: SetWindowDisplayAffinity failed, the video may show it")
                        else:
                            win.resize(rect)
                n = 0
                while True:
                    try:
                        s = self.q.get_nowait()
                    except queue.Empty:
                        break
                    n += 1
                    if self._take(s):
                        since += 1
                self.stats["max_backlog"] = max(self.stats["max_backlog"], n)
                while True:
                    try:
                        self._apply(self.cmds.get_nowait())
                    except queue.Empty:
                        break
                self._keys(keys, hwnd)
                # redraw on every new STATE (the camera moves when the hero turns or stands at a scene's edge, also out
                # of battle where no game frame is fed); recompute the zones only every `every` game frames
                if win is not None and (since >= self.every or self.dirty or n > 0):
                    t0 = time.perf_counter()
                    if since >= self.every or self.dirty:
                        if self.eng.running and self.eng.ws is not None:   # new frames, or a new k / mode / layer
                            fr = self.eng.compute(ks=(self.view.k,), support=self.view.show("support"),
                                                  forecast=self.view.needs_forecast(),
                                                  range_ks=self.view.range_ks(), sweep=self.view.range_sweep(),
                                                  range_hero=not self.view.all_k, aim=self.view.range_aim())
                            self.stats["computed"] += 1
                            self.stats["range_ms"].append(fr["ms"]["range"])
                            self.stats["ms"].append((time.perf_counter() - t0) * 1e3)
                        elif not self.eng.running:
                            fr = None
                        since = 0
                        self.dirty = False
                    t1 = time.perf_counter()
                    shown = fr
                    if shown is None and self.last_raw is not None:
                        s = self.last_raw
                        shown = {"ks": (self.view.k,), "support": {}, "ycom": {}, "yns": {}, "info": {},
                                 "cols": damage_colliders(s), "cam": s.get("cam"), "hero": self.eng.hero(s)}
                    elif shown is not None and self.last_raw is not None:
                        # the colliders and the camera of the newest STATE (what is on the screen now)
                        shown = dict(shown, cols=damage_colliders(self.last_raw), cam=self.last_raw.get("cam"),
                                     hero=self.eng.hero(self.last_raw))
                    lines = legend_lines(fr, self.view, config,
                                         "" if self.eng.running else "(no battle: red only)")
                    # drawn at most at the render size and scaled up nearest (a 4K window: 3 ms instead of 55)
                    W, H = rect[2], rect[3]
                    sc = min(1.0, RENDER[0] / W, RENDER[1] / H)
                    size = (max(1, int(round(W * sc))), max(1, int(round(H * sc))))
                    img = render(shown or {"ks": (0,), "support": {}}, self.eng.grid, size, self.view,
                                 legend=lines if self.view.on else None)
                    if size != (W, H):
                        import cv2
                        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_NEAREST)
                    win.show(img)
                    self.stats["upd_ms"].append((time.perf_counter() - t1) * 1e3)
                if win is not None:
                    win.pump()
                time.sleep(0.004)
        except Exception as e:  # noqa: BLE001 - the session and its recording go on without the overlay
            import traceback
            self.stats["errors"].append(traceback.format_exc()[-2000:])
            print(f"overlay stopped: {e!r}")
        finally:
            if win is not None:
                win.close()


# ------------------------------------------------------------------------------------------------ offline

def _video_index(session: Path) -> dict[int, int]:
    """raw oracle frame -> the first video frame labelled with it (labels.npz)."""
    z = np.load(session / "labels.npz")
    out: dict[int, int] = {}
    for i, f in zip(z["index"].tolist(), z["frame"].tolist()):
        if f >= 0 and f not in out:
            out[f] = i
    return out


def attempt_states(session: Path, attempt: int, cache: Path | None = None):
    from ssbot.tools.forum_human_score import load_segment, segments
    segs = segments(f"{session}:win:{attempt}", cache)
    if not segs:
        raise SystemExit(f"{session}: no attempt {attempt}")
    seg = segs[0]
    terrain, states = load_segment(seg)
    return seg, terrain, states


class VideoFrames:
    """The session video's frames by index (labels.npz "index" / "pts_ns"), decoded by ffmpeg from an accurate seek
    and read on sequentially (the video is variable frame rate: passthrough, one output frame per stored frame;
    OpenCV's frame seek in the HEVC mkv lands elsewhere)."""

    def __init__(self, session: Path, size: tuple[int, int] = RENDER):
        z = np.load(session / "labels.npz")
        self.pts = dict(zip(z["index"].tolist(), z["pts_ns"].tolist()))
        self.path = session / "video.mkv"
        self.size = size
        self.proc = None
        self.pos = -1

    def _open(self, i: int) -> None:
        import subprocess
        from ssbot.tools.human_video import FFMPEG
        self.close()
        ss = max(0.0, self.pts[i] / 1e9 - 0.0005)
        w, h = self.size
        self.proc = subprocess.Popen([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-ss", f"{ss:.4f}", "-i",
                                      str(self.path), "-fps_mode", "passthrough", "-vf", f"scale={w}:{h}", "-f",
                                      "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
        self.pos = i - 1

    def get(self, i: int):
        if i not in self.pts:
            return None
        if self.proc is None or i <= self.pos or i - self.pos > 900:
            self._open(i)
        w, h = self.size
        img = None
        while self.pos < i:
            buf = self.proc.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                self.close()
                return None
            self.pos += 1
            img = buf
        return np.frombuffer(img, np.uint8).reshape(h, w, 3).copy()

    def close(self) -> None:
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait()
            self.proc = None


def mask_contours(mask: np.ndarray) -> list[np.ndarray]:
    """[n, 2] (column, row) outlines of a grid mask (row 0 = the lowest hero centre)."""
    import cv2
    if mask is None or not mask.any():
        return []
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [c.reshape(-1, 2).astype(np.float64) for c in cs]


def rerun_zones(session: Path, rec, f0: int | None = None, f1: int | None = None, ks=(0,), video: bool = False,
                video_scale: float = 0.5, every: int = 1, margins: bool = False, demo_cache: Path | None = None,
                threads: int = 4, precision: bool = False, range_layer: bool = False) -> dict:
    """Log a human session's Forum attempts with the zone layers per game frame into a Rerun recording ("frame" =
    the raw oracle frame, as the video labels): world/ (y up, as tools.viewer) hero, the real damage colliders
    (colliders/non_clashable, colliders/clashable: the ground truth), zones/red (the non-clashable sweeps),
    zones/yellow/{committed, not_started}, support/k<k>/<layer>; with video, screen/video (the recorded frame) and the
    same outlines projected with the STATE camera (screen/zones/...); precision: per enemy and k the support's RATIO
    to the enemy's real damage at t + k (tools.support_precision; 0 = no prediction, -1 = a prediction with no real
    damage) as metrics/precision/<name>/k<k>/<layer> (committed, com_all, not_started, total) and the error flag (the
    person's rule) as metrics/precision/<name>/k<k>/error."""
    import cv2
    import rerun as rr
    from ssbot.tools.forum_human_score import load_segment, segments
    from ssbot.tools.viewer import closed, polygons_by_key
    eng = ZoneEngine(crest="Wanderer", threads=threads, margins=margins, range_layer=range_layer)
    g = eng.grid
    stats: dict = {"frames": 0, "attempts": [], "config": eng.config_text(), "compute_ms": []}
    rng_parts = ((*(f"range/k{k:02d}" for k in ks), "range/swept", "aim/ground", "aim/low", "aim/high")
                 if range_layer else ())
    segs = [s for s in segments(f"{session}:win", demo_cache)
            if (f1 is None or s["f0"] <= f1) and (f0 is None or s["f1"] >= f0)]
    vidx = _video_index(session) if video else {}
    size = (int(RENDER[0] * video_scale), int(RENDER[1] * video_scale))
    vf = VideoFrames(session, size) if video else None
    rr_ = 0.04
    seen_enemies: set = set()

    def wl(pts):
        return [(float(x), -float(y)) for x, y in pts]

    def grid_world(c):
        return g.to_world(c[:, 0], c[:, 1])

    rec.log("legend", rr.TextDocument(
        "zones (hero-centre space: where the hero CENTRE must not be): yellow = inescapable, a lower bound (committed: "
        "each attack's own colliders carried along its velocity for 12 frames, eroded back with the one-frame "
        "reach, floor / walls / the dome solid; not started: the commit-now erosion of each family for the lock now); "
        "red = non-clashable colliders + 6-frame sweep; colliders/* = the real damage colliders (ground truth); "
        "support/k<k>/<layer> = the planner's support at look-ahead k; enemies/<name>/ = per enemy (stable name "
        "'Reed 2' = type + order of appearance, label = name + Control state, its own colour): colliders, "
        f"yellow/k<k>, support/k<k> (its own placements). Config: {eng.config_text()}"), static=True)
    for seg in segs:
        terrain, states = load_segment(seg)
        eng.crest = seg.get("crest") or eng.crest
        eng.start(terrain)
        truth = None
        if precision:
            from ssbot.tools.support_precision import Truth
            truth = Truth(states)
        stats["attempts"].append([seg["attempt"], seg["f0"], seg["f1"], seg.get("outcome")])
        if terrain is not None:
            rec.set_time("frame", sequence=max(seg["f0"], f0 or 0))
            for key, polys in polygons_by_key(terrain).items():
                rec.log(f"world/terrain/{key}", rr.LineStrips2D([closed(wl(p)) for p in polys],
                                                                colors=[[120, 120, 120]], radii=[0.04]))
        for s in states:
            eng.feed(s)
            fr_raw = s["_f_raw"]
            if f0 is not None and fr_raw < f0:
                continue
            if f1 is not None and fr_raw > f1:
                break
            if s["f"] % every:
                continue
            t0 = time.perf_counter()
            fr = eng.compute(ks=ks, support=True, sweep=max(ks) if range_layer else None, aim=range_layer)
            stats["compute_ms"].append((time.perf_counter() - t0) * 1e3)
            rec.set_time("frame", sequence=int(fr_raw))
            rec.set_time("game_frame", sequence=int(s["f"]))
            hc = fr["hero"]
            rec.log("world/hero", rr.Points2D([(hc[0], -hc[1])] if hc else [], colors=[[255, 255, 255]],
                                              radii=[0.15]))
            cols = fr["cols"]
            nc = [p for p, c, _, _, _ in cols if not c]
            cl = [p for p, c, _, _, _ in cols if c]
            rec.log("world/colliders/non_clashable", rr.LineStrips2D(
                [closed(wl(p)) for p in nc], colors=[[255, 60, 60]], radii=[0.03],
                labels=[lb for p, c, lb, _, _ in cols if not c]))
            rec.log("world/colliders/clashable", rr.LineStrips2D(
                [closed(wl(p)) for p in cl], colors=[[240, 240, 240]], radii=[0.03],
                labels=[lb for p, c, lb, _, _ in cols if c]))
            sweeps = [sweep_hull(p, v) for p, c, _, v, _ in cols if not c]
            rec.log("world/zones/red", rr.LineStrips2D([closed(wl(h)) for h in sweeps],
                                                       colors=[[255, 130, 130]], radii=[rr_]))
            layers = {}
            for k in ks:
                layers[f"zones/yellow/committed/k{k:02d}"] = (fr["ycom"].get(k), COLORS["yellow"])
                layers[f"zones/yellow/not_started/k{k:02d}"] = (fr["yns"].get(k), (90, 220, 255))
                for lay in LAYERS:
                    layers[f"support/k{k:02d}/{lay}"] = (fr["support"].get(k, {}).get(lay), COLORS[lay])
            outlines = {}
            for path, (m, col) in layers.items():
                outlines[path] = [grid_world(c) for c in mask_contours(m) if len(c) >= 2]
                rgb = [col[2], col[1], col[0]]
                rec.log(f"world/{path}", rr.LineStrips2D([closed(wl(p)) for p in outlines[path]], colors=[rgb],
                                                         radii=[rr_]))
            # per enemy (its stable name "Reed 2" and its Control state; its own colour): the real colliders, its
            # yellow and its own support (MultiForecast.occupied_only) per k
            sb = eng.support_by(ks)
            now = set()
            per = {}
            for iid, name, st, pos, col in fr["enemies"]:
                slug = name.replace(" ", "_")
                now.add(slug)
                rgb = [col[2], col[1], col[0]]
                lab = f"{name} {st or ''}"
                polys = [p for p, _, _, _, o in cols if o == iid]
                per[f"enemies/{slug}/colliders"] = (polys, rgb, lab)
                for k in ks:
                    y = fr["ycom_by"].get(k, {}).get(iid)
                    yn = fr["yns_by"].get(k, {}).get(iid)
                    m = y if yn is None else (yn if y is None else (y | yn))
                    per[f"enemies/{slug}/yellow/k{k:02d}"] = (
                        [grid_world(c) for c in mask_contours(m) if len(c) >= 2] if m is not None else [], rgb, lab)
                    m = sb.get(k, {}).get(iid)
                    per[f"enemies/{slug}/support/k{k:02d}"] = (
                        [grid_world(c) for c in mask_contours(m) if len(c) >= 2] if m is not None else [], rgb, lab)
                rec.log(f"world/enemies/{slug}/label", rr.Points2D([(pos[0], -pos[1] - 1.6)], colors=[rgb],
                                                                   radii=[0.05], labels=[lab]))
            for k in ks if range_layer else ():             # the attack-range estimate (raw, no margin)
                for iid, name, col, raw, _hero, rlab in fr["range"].get(k, ()):
                    slug = name.replace(" ", "_")
                    now.add(slug)
                    per[f"enemies/{slug}/range/k{k:02d}"] = (raw, [col[2], col[1], col[0]], f"{name} {rlab}")
            for iid, name, col, polys, rlab in fr["range_swept"] if range_layer else ():
                slug = name.replace(" ", "_")             # the swept path over 0..max k (the person 2026-10-10)
                now.add(slug)
                per[f"enemies/{slug}/range/swept"] = (polys, [col[2], col[1], col[0]], f"{name} {rlab}")
            for iid, name, col, polys, alab, _pos in fr.get("aim", ()) if range_layer else ():
                slug = name.replace(" ", "_")             # the aim zones (tools.aim_zones; the person 2026-10-10)
                now.add(slug)
                for cls in ("ground", "low", "high"):
                    per[f"enemies/{slug}/aim/{cls}"] = (polys.get(cls, []), [col[2], col[1], col[0]],
                                                        f"{name} {alab} ({cls})")
            for slug in seen_enemies - now:                 # gone (dead, parked): clear what it drew
                for k in ("colliders", *rng_parts, *(f"{w}/k{k:02d}" for w in ("yellow", "support") for k in ks)):
                    per[f"enemies/{slug}/{k}"] = ([], [0, 0, 0], "")
                rec.log(f"world/enemies/{slug}/label", rr.Points2D([], radii=[0.05]))
            seen_enemies |= now
            if truth is not None and eng.ws is not None:
                _log_precision(rec, eng, truth, ks)
            for path, (polys, rgb, lab) in per.items():
                rec.log(f"world/{path}", rr.LineStrips2D([closed(wl(p)) for p in polys], colors=[rgb],
                                                         radii=[rr_ if "/colliders" not in path else 0.03],
                                                         labels=[lab] * len(polys) if polys else None))
            if vf is not None:
                vi = vidx.get(fr_raw)
                img = vf.get(vi) if vi is not None else None
                cam = fr.get("cam")
                if img is not None:
                    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    rec.log("screen/video", rr.EncodedImage(contents=jpg.tobytes(), media_type="image/jpeg"))
                if cam is not None and cam.get("V"):
                    Hw, _ = homography(g, cam, size)

                    def sp(pts):
                        return [tuple(map(float, q)) for q in _to_px(Hw, np.asarray(pts))]
                    for path, polys in outlines.items():
                        m, col = layers[path]
                        rec.log(f"screen/{path}", rr.LineStrips2D([closed(sp(p)) for p in polys],
                                                                  colors=[[col[2], col[1], col[0]]], radii=[1.0]))
                    for path, (polys, rgb, lab) in per.items():
                        rec.log(f"screen/{path}", rr.LineStrips2D([closed(sp(p)) for p in polys], colors=[rgb],
                                                                  radii=[1.0]))
                    for iid, name, st, pos, col in fr["enemies"]:
                        rec.log(f"screen/enemies/{name.replace(' ', '_')}/label", rr.Points2D(
                            [sp([(pos[0], pos[1] + 1.6)])[0]], colors=[[col[2], col[1], col[0]]], radii=[2.0],
                            labels=[f"{name} {st or ''}"]))
                    rec.log("screen/zones/red", rr.LineStrips2D([closed(sp(h)) for h in sweeps],
                                                                colors=[[255, 130, 130]], radii=[1.0]))
                    rec.log("screen/colliders/non_clashable", rr.LineStrips2D([closed(sp(p)) for p in nc],
                                                                              colors=[[255, 60, 60]], radii=[1.0]))
                    rec.log("screen/colliders/clashable", rr.LineStrips2D([closed(sp(p)) for p in cl],
                                                                          colors=[[240, 240, 240]], radii=[1.0]))
                    rec.log("screen/hero", rr.Points2D([sp([hc])[0]] if hc else [], colors=[[255, 255, 255]],
                                                       radii=[3.0]))
            stats["frames"] += 1
    if vf is not None:
        vf.close()
    ms = stats.pop("compute_ms")
    stats["compute_ms_p50"] = round(float(np.median(ms)), 1) if ms else None
    return stats


def rerun_range(session: Path, rec, f0: int | None = None, f1: int | None = None, ks=(0, 12), video: bool = False,
                video_scale: float = 0.35, demo_cache: Path | None = None) -> dict:
    """The attack-range layer alone (no planner forecast; viewer --zones --range-only): per game frame of the human
    session's Forum attempts in [f0, f1], world/ hero (transform + hurtbox), the real damage colliders
    (colliders/real), per enemy its estimate at each k (range/<name>/k<k>/raw filled outline, .../hero = where the
    hero transform must not be) and with video the recorded frame and the same outlines projected (screen/...)."""
    import cv2
    import rerun as rr
    from ssbot.combat.attack_range import HERO_DY, HERO_HALF, RangeTracker, contours, hero_space, same_mask
    from ssbot.tools.forum_human_score import load_segment, segments
    from ssbot.tools.viewer import closed, polygons_by_key
    trk = RangeTracker()
    g = Grid(CELL)
    segs = [s for s in segments(f"{session}:win", demo_cache)
            if (f1 is None or s["f0"] <= f1) and (f0 is None or s["f1"] >= f0)]
    vidx = _video_index(session) if video else {}
    size = (int(RENDER[0] * video_scale), int(RENDER[1] * video_scale))
    vf = VideoFrames(session, size) if video else None
    stats: dict = {"frames": 0, "attempts": []}
    rec.log("legend", rr.TextDocument(
        "attack range (combat.attack_range, NO margin): per enemy, filled = the raw estimate of where its damage "
        "colliders can be at +k frames (k = " + ", ".join(map(str, ks)) + "), thin = the same in hero-centre space "
        "(where the hero TRANSFORM must not be: dilated by the hurtbox 0.4554 x 2.2498 at (0, -0.38)); "
        "colliders/real = the real damage colliders now (red); hero = transform (dot) + hurtbox. Idle = the body "
        "now. Attacks not started yet are not drawn (group 2, not this round). range/<enemy>/swept = the union of "
        "the estimate over every frame 0.." + str(max(ks)) + " (the whole path of a lunge or a dive, out and back); "
        "a k whose estimate is the same region as an earlier k says so in its label (=k...). range/<enemy>/aim/<class> "
        "= the composite aim zone (tools.aim_zones, lat 2) of an enemy in a pending aimed antic, at its position now: "
        "ground band / low air / high air cells (each cell by its own height)."), static=True)

    def wl(pts):
        return [(float(x), -float(y)) for x, y in pts]
    names: dict = {}
    seen: set = set()
    for seg in segs:
        terrain, states = load_segment(seg)
        trk.reset()
        stats["attempts"].append([seg["attempt"], seg["f0"], seg["f1"]])
        if terrain is not None:
            rec.set_time("frame", sequence=max(seg["f0"], f0 or 0))
            for key, polys in polygons_by_key(terrain).items():
                rec.log(f"world/terrain/{key}", rr.LineStrips2D([closed(wl(p)) for p in polys],
                                                                colors=[[120, 120, 120]], radii=[0.04]))
        for s in states:
            trk.feed(s)
            fr_raw = int(s["_f_raw"])
            if f0 is not None and fr_raw < f0:
                continue
            if f1 is not None and fr_raw > f1:
                break
            rec.set_time("frame", sequence=fr_raw)
            rec.set_time("game_frame", sequence=int(s["f"]))
            h = (s.get("hero") or {}).get("pos")
            hb = None
            if h:
                hx, hy = float(h[0]), float(h[1])
                hb = [(hx - HERO_HALF[0], hy + HERO_DY - HERO_HALF[1]), (hx + HERO_HALF[0], hy + HERO_DY - HERO_HALF[1]),
                      (hx + HERO_HALF[0], hy + HERO_DY + HERO_HALF[1]), (hx - HERO_HALF[0], hy + HERO_DY + HERO_HALF[1])]
                rec.log("world/hero/transform", rr.Points2D([(hx, -hy)], colors=[[255, 255, 255]], radii=[0.08]))
                rec.log("world/hero/hurtbox", rr.LineStrips2D([closed(wl(hb))], colors=[[255, 255, 255]],
                                                              radii=[0.03]))
            cols = damage_colliders(s)
            real = [p for p, *_ in cols]
            rec.log("world/colliders/real", rr.LineStrips2D([closed(wl(p)) for p in real], colors=[[255, 60, 60]],
                                                            radii=[0.04], labels=[lb for _, _, lb, _, _ in cols]))
            per = {}
            now = set()
            ests, swept = trk.ladder(ks, max(ks))       # every k and the swept path in one pass
            prev: dict = {}
            for k in sorted(ks):
                for est in ests[k]:
                    if est.iid not in names:
                        tk = trk.now[est.iid][0]
                        n = sum(1 for v in names.values() if v.startswith(SHORT_NAMES.get(tk, tk))) + 1
                        names[est.iid] = f"{SHORT_NAMES.get(tk, tk)}_{n}"
                    nm = names[est.iid]
                    col = ENEMY_COLORS[sorted(names).index(est.iid) % len(ENEMY_COLORS)]
                    rgb = [col[2], col[1], col[0]]
                    lab = f"{nm} k{k} " + (f"{est.fam} {est.branch or '?'} b{est.b}" if est.fam else "idle body")
                    if est.haz is not None and est.haz.m.size and est.haz.m.any():
                        lab += " + hazards"           # its rune bombs / rune slam (combat.attack_range hazards)
                    k0 = next((j for j, m in prev.get(est.iid, ()) if same_mask(m, est.raw)), None)
                    if k0 is None:
                        prev.setdefault(est.iid, []).append((k, est.raw))
                    else:
                        lab += f" (=k{k0})"
                    per[f"range/{nm}/k{k:02d}/raw"] = (contours(est.raw), rgb, lab, 0.05)
                    per[f"range/{nm}/k{k:02d}/hero"] = (contours(hero_space(est.raw)), rgb, lab, 0.02)
                    now.add(nm)
            for iid, m in swept.items():
                if iid in names:
                    col = ENEMY_COLORS[sorted(names).index(iid) % len(ENEMY_COLORS)]
                    per[f"range/{names[iid]}/swept"] = (contours(m), [col[2], col[1], col[0]],
                                                        f"{names[iid]} path 0-{max(ks)}", 0.03)
            for iid, polys, alab, _pos in aim_zones_of(trk):
                if iid in names:                         # the aim zones (tools.aim_zones; the person 2026-10-10)
                    col = ENEMY_COLORS[sorted(names).index(iid) % len(ENEMY_COLORS)]
                    for cls in ("ground", "low", "high"):
                        per[f"range/{names[iid]}/aim/{cls}"] = (polys.get(cls, []), [col[2], col[1], col[0]],
                                                                f"{names[iid]} {alab} ({cls})", 0.04)
                    now.add(names[iid])
            for nm in seen - now:
                for k in ks:
                    for part in ("raw", "hero"):
                        per[f"range/{nm}/k{k:02d}/{part}"] = ([], [0, 0, 0], "", 0.02)
                per[f"range/{nm}/swept"] = ([], [0, 0, 0], "", 0.02)
                for cls in ("ground", "low", "high"):
                    per[f"range/{nm}/aim/{cls}"] = ([], [0, 0, 0], "", 0.02)
            seen |= now
            for path, (polys, rgb, lab, rad) in per.items():
                rec.log(f"world/{path}", rr.LineStrips2D([closed(wl(p)) for p in polys], colors=[rgb], radii=[rad],
                                                         labels=[lab] * len(polys) if polys else None))
            if vf is not None:
                vi = vidx.get(fr_raw)
                img = vf.get(vi) if vi is not None else None
                cam = s.get("cam")
                if img is not None:
                    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    rec.log("screen/video", rr.EncodedImage(contents=jpg.tobytes(), media_type="image/jpeg"))
                if cam is not None and cam.get("V"):
                    Hw, _ = homography(g, cam, size)

                    def sp(pts):
                        return [tuple(map(float, q)) for q in _to_px(Hw, np.asarray(pts))]
                    for path, (polys, rgb, lab, rad) in per.items():
                        rec.log(f"screen/{path}", rr.LineStrips2D([closed(sp(p)) for p in polys], colors=[rgb],
                                                                  radii=[1.5 if path.endswith("raw") else 0.7]))
                    rec.log("screen/colliders/real", rr.LineStrips2D([closed(sp(p)) for p in real],
                                                                     colors=[[255, 60, 60]], radii=[1.0]))
                    rec.log("screen/hero/hurtbox", rr.LineStrips2D([closed(sp(hb))] if hb else [],
                                                                   colors=[[255, 255, 255]], radii=[1.0]))
            stats["frames"] += 1
    if vf is not None:
        vf.close()
    return stats


def _log_precision(rec, eng, truth, ks) -> None:
    """The precision scalars of the forecast just computed (rerun_zones precision)."""
    import rerun as rr
    from ssbot.tools.support_precision import frame_rows, judge
    j0 = truth.idx.get(int(eng.ws.stamp.frame))
    if j0 is None or j0 + max(ks) + 1 >= truth.n or truth.at(j0, max(ks)) + 1 >= truth.n:
        return
    for r in frame_rows(eng, truth, j0, ks, eng.grid):
        slug = r["name"].replace(" ", "_")
        for k, ent in r["k"].items():
            err = 0.0
            for lay in ("committed", "com_all", "not_started", "ns_any", "total"):
                j = judge(ent, lay)
                v = 0.0 if j is None else (-1.0 if j[2] is None else round(j[2], 2))
                if j is not None and j[3] and lay in ("com_all", "not_started"):
                    err = 1.0
                rec.log(f"metrics/precision/{slug}/k{k:02d}/{lay}", rr.Scalars(v))
            rec.log(f"metrics/precision/{slug}/k{k:02d}/error", rr.Scalars(err))


def zones_blueprint(video: bool, precision: bool = False):
    import rerun.blueprint as rrb
    views = [rrb.Spatial2DView(origin="world", name="world (y up): zones, colliders, hero")]
    if video:
        views.append(rrb.Spatial2DView(origin="screen", name="recorded video + zones"))
    side = rrb.TextDocumentView(origin="legend", name="legend")
    if precision:
        side = rrb.Vertical(side, rrb.TimeSeriesView(origin="metrics/precision",
                                                     name="precision: RATIO support / real damage (-1 false alarm)"))
    return rrb.Blueprint(rrb.Horizontal(*views, side, column_shares=[3, 3, 1][:len(views)] + [1]),
                         collapse_panels=True)


def cmd_render(a) -> int:
    import cv2
    session = Path(a.session)
    eng = ZoneEngine(crest="Wanderer", threads=a.threads, margins=a.margins, range_layer=a.range_layer)
    seg, terrain, states = attempt_states(session, a.attempt, Path(a.demo_cache) if a.demo_cache else None)
    eng.crest = seg.get("crest") or eng.crest
    vidx = _video_index(session)
    vf = VideoFrames(session)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    view = View(mode=a.mode, k=a.k, all_k=a.all_k, swept=a.swept)
    eng.start(terrain)
    writer = None
    n_png = 0
    ms = []
    for s in states:
        eng.feed(s)
        fr_raw = s["_f_raw"]
        if a.f0 is not None and fr_raw < a.f0:
            continue
        if a.f1 is not None and fr_raw > a.f1:
            break
        if (s["f"] % a.every) and not a.clip:
            continue
        t0 = time.perf_counter()
        fr = eng.compute(ks=(a.k,), support=view.show("support"), forecast=view.needs_forecast(),
                         range_ks=view.range_ks(), sweep=view.range_sweep(), range_hero=not view.all_k)
        ms.append((time.perf_counter() - t0) * 1e3)
        vi = vidx.get(fr_raw)
        img = vf.get(vi) if vi is not None else None
        if img is None:
            continue
        lines = legend_lines(fr, view, eng.config_text(), f"f {fr_raw}")
        ov = render(fr, eng.grid, (img.shape[1], img.shape[0]), view, legend=lines)
        comp = composite(img, ov)
        if a.clip:
            if writer is None:
                writer = cv2.VideoWriter(str(out / a.clip), cv2.VideoWriter_fourcc(*"mp4v"), 30.0,
                                         (comp.shape[1], comp.shape[0]))
            writer.write(comp)
        if a.png_every and s["f"] % a.png_every == 0:
            cv2.imwrite(str(out / f"{session.name}_a{a.attempt}_f{fr_raw}_k{a.k}_{a.mode.replace('+', '')}.png"),
                        comp)
            n_png += 1
    if writer is not None:
        writer.release()
    print(json.dumps({"pngs": n_png, "frames": len(ms), "compute_ms_p50": float(np.median(ms)) if ms else None,
                      "out": str(out)}))
    return 0


def cmd_bench(a) -> int:
    """Per game frame: feed (every frame) and compute (every `every`-th, one k) cost on a recorded attempt, and the
    full-size render (+ the 4K one the live window draws)."""
    session = Path(a.session)
    eng = ZoneEngine(crest="Wanderer", threads=a.threads, margins=a.margins, range_layer=a.range_layer)
    seg, terrain, states = attempt_states(session, a.attempt, Path(a.demo_cache) if a.demo_cache else None)
    if a.limit_s:
        states = states[:int(a.limit_s * 60)]
    eng.start(terrain)
    # --range: the live range+red mode (no forecast), with --all-k / --swept as keys 0 / 9 set them
    view = View(mode="range+red" if a.range_layer else "all", k=a.k, all_k=a.all_k, swept=a.swept)
    feed, comp, rend, rend4k, parts = [], [], [], [], []
    for s in states:
        t0 = time.perf_counter()
        eng.feed(s)
        feed.append((time.perf_counter() - t0) * 1e3)
        if s["f"] % a.every or s["f"] < 30:
            continue
        t0 = time.perf_counter()
        fr = eng.compute(ks=(a.k,), support=view.show("support"), forecast=view.needs_forecast(),
                         range_ks=view.range_ks(), sweep=view.range_sweep(), range_hero=not view.all_k)
        comp.append((time.perf_counter() - t0) * 1e3)
        parts.append(fr["ms"])
        t0 = time.perf_counter()
        render(fr, eng.grid, RENDER, view, legend=legend_lines(fr, view, eng.config_text()))
        rend.append((time.perf_counter() - t0) * 1e3)
        if len(rend4k) < 60:
            t0 = time.perf_counter()
            render(fr, eng.grid, (3840, 2160), view, legend=legend_lines(fr, view, eng.config_text()))
            rend4k.append((time.perf_counter() - t0) * 1e3)

    def q(v):
        return None if not v else {"p50": round(float(np.percentile(v, 50)), 1),
                                   "p95": round(float(np.percentile(v, 95)), 1), "max": round(float(max(v)), 1)}
    res = {"session": str(session), "attempt": a.attempt, "game_frames": len(states), "every": a.every,
           "feed_ms": q(feed), "compute_ms": q(comp), "render_1080_ms": q(rend), "render_2160_ms": q(rend4k),
           "forecast_ms": q([p["forecast"] for p in parts]), "support_ms": q([p["support"] for p in parts]),
           "yellow_ms": q([p["yellow"] for p in parts]), "range_ms": q([p["range"] for p in parts]),
           "view": {"mode": view.mode, "k": view.k, "all_k": view.all_k, "swept": view.swept},
           "config": eng.config_text()}
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), "utf-8")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.tools.zone_overlay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render", "bench"):
        p = sub.add_parser(name)
        p.add_argument("session")
        p.add_argument("--attempt", type=int, default=0)
        p.add_argument("--k", type=int, default=0)
        p.add_argument("--threads", type=int, default=4)
        p.add_argument("--margins", action="store_true")
        p.add_argument("--demo-cache", default=None)
        p.add_argument("--range", dest="range_layer", action="store_true", help="the attack-range layer")
        p.add_argument("--all-k", action="store_true", help="range: every look-ahead at once (live key 0)")
        p.add_argument("--swept", action="store_true", help="range: the swept path (live key 9)")
        if name == "render":
            p.add_argument("--from", dest="f0", type=int)
            p.add_argument("--to", dest="f1", type=int)
            p.add_argument("--every", type=int, default=1)
            p.add_argument("--png-every", type=int, default=0)
            p.add_argument("--clip", default=None)
            p.add_argument("--mode", default="yellow+red", choices=View.MODES)
            p.add_argument("--out", default=str(OUT_DIR))
        else:
            p.add_argument("--every", type=int, default=3)
            p.add_argument("--limit-s", type=float, default=60.0)
            p.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    return cmd_render(a) if a.cmd == "render" else cmd_bench(a)


if __name__ == "__main__":
    sys.exit(main())
