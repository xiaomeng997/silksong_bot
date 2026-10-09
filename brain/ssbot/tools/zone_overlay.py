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
                  earliest start t_strike on: the commit-now zone of zones_lat1.npz (forum_ics Zones, the upper bound
                  of its library) for the hero's lock state NOW toward that enemy (free / attack / dash; above
                  standing height: air), placed on the enemy's anchor dead-reckoned to frame k, mirrored to the hero's
                  side (the attack faces the hero at its commit).
  red             NON-CLASHABLE damage colliders of the STATE shown (enabled, dealt > 0, parry bits without clash /
                  force: oracle 4 = counter only; 5 = clash + counter is clashable; every Clapper collider), each with
                  its sweep over the next SWEEP_F frames (moved along its entity's velocity, convex hull). Bodies,
                  Clapper moves and runes, Clawmaiden spear / explosion, bells (a hit-back bell deals 0: not drawn),
                  Tiny rams, unclashable projectiles all carry parry 4 in the recordings.

Space: the support layers and yellow are HERO-CENTRE configuration space: where the hero's CENTRE (the white dot) must
not be; the colliders are already grown by the hero hurtbox half extents (0.25 x 1.04 u). Red is the colliders
themselves (compare with DebugMod's hitbox.show).

Live keys (polled, only while the game window has the focus; the game still gets them): F8 overlay on / off, F9 cycles
yellow+red / yellow / red / support / all, F10 freeze / unfreeze (time.scale 0.0001: the oracle refuses 0), F11 one
game frame forward while frozen (about one: the RPC lands a render frame or two later), 1-5 look-ahead now / +6 / +12 /
+18 / +36, Ctrl+1-7 toggles a support layer. The same through the session's command file: "overlay k 12",
"overlay mode all", "overlay layer window", "overlay freeze", "overlay step", "overlay off" / "overlay on".
"""
import argparse
import ctypes
import json
import math
import os
import queue
import random
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
FREEZE_SCALE = 1e-4
# the round-5 recommended configuration (forum.md, the lead 2026-10-08); the environment wins
DEFAULT_ENV = {"SSBOT_FORUM_FR": "seen_cf", "SSBOT_FORUM_REACT": "escape+n+g", "SSBOT_FORUM_MARGIN": "state",
               "SSBOT_FORUM_KF": "kill"}
DEFAULT_CLASH = "main"
SWITCHES = ("FR", "REACT", "MARGIN", "KF", "PC", "TV", "T", "BELLS", "L2", "AB")

LAYERS = ("body", "committed", "window", "not_started", "hazard", "death", "margins")
LAYER_OF = {"body": "body", "collider": "body", "idle_now": "body", "idle": "body",
            "com_fine": "committed", "chain_fine": "committed", "tail": "committed",
            "com_win": "window", "com_fam": "window", "chain_win": "window", "com_bbox": "window",
            "chain_bbox": "window",
            "start_attack": "not_started", "start_idle": "not_started", "entry_later": "not_started",
            "entry_now": "not_started",
            "haz_self": "hazard", "haz_path": "hazard", "haz_tube": "hazard",
            "death": "death", "arena": "death"}
NAMES = {"body": "bodies + idle growth", "committed": "committed fine (+chains, tails)",
         "window": "window / family / bbox placements", "not_started": "not started (later attacks, idle, entries)",
         "hazard": "projectiles / hazards", "death": "death tails (+arena)", "margins": "margins only",
         "yellow": "INESCAPABLE: hero centre must not be here", "red": "NON-CLASHABLE colliders (+6 f sweep)"}
# BGR, light colours
COLORS = {"body": (200, 200, 200), "committed": (245, 150, 245), "window": (250, 195, 140),
          "not_started": (160, 235, 160), "hazard": (110, 190, 255), "death": (220, 160, 185),
          "margins": (255, 245, 185), "yellow": (140, 245, 255), "red": (130, 130, 255)}
A_SUPPORT, A_YELLOW, A_RED, A_SWEEP = 0.33, 0.40, 0.42, 0.22
KEY_K = {0x31: 0, 0x32: 6, 0x33: 12, 0x34: 18, 0x35: 36}


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

def damage_colliders(s: dict):
    """[(poly [n, 2], clashable, label, entity velocity)] of every enabled collider with damage dealt > 0."""
    out = []
    for e in s.get("ents") or ():
        tk = str(e.get("type_key") or e.get("name") or "")
        vel = e.get("vel") or (0.0, 0.0)
        for c in e.get("cols") or e.get("colliders") or ():
            d = c.get("damage")
            v = c.get("verts_world")
            if not d or not c.get("enabled") or not v or len(v) < 6 or not (d.get("dealt") or 0) > 0:
                continue
            clash = bool(int(d.get("parry") or 0) & CLASH_BITS) and tk not in FORCE_RED_TYPES
            out.append((np.asarray(v, np.float64).reshape(-1, 2), clash, f"{tk}/{c.get('name')}",
                        (float(vel[0]), float(vel[1]))))
    return out


def sweep_hull(poly: np.ndarray, vel, frames: int = SWEEP_F) -> np.ndarray:
    """The convex hull of the collider and its copy moved `frames` along its entity's velocity."""
    import cv2
    d = np.asarray(vel, np.float64) * frames * FT
    pts = np.vstack([poly, poly + d]).astype(np.float32)
    return cv2.convexHull(pts).reshape(-1, 2).astype(np.float64)


# ------------------------------------------------------------------------------------------------ erosion (yellow)

def erode_back(D: np.ndarray, ax: int, up: int, dn: int, lat: int = LAT_F) -> np.ndarray:
    """D [K+1, ny, nx] bool (row 0 = the lowest hero centre, standing) -> Z [K+1, ny, nx]: Z_K = D_K;
    Z_k = D_k | erode(Z_k+1) for k >= lat (a cell is doomed when every one-frame move, dx in [-ax, ax] cells,
    dy in [-dn, up] cells, lands in a doomed cell); Z_k = D_k | Z_k+1 below lat (the hero has not reacted). The floor
    (below row 0) and the walls (left of column 0, right of the last) are solid, i.e. doomed; above is free."""
    import cv2
    K1, ny, nx = D.shape
    p = max(ax, up, dn) + 1
    S = np.zeros((ny + 2 * p, nx + 2 * p), np.uint8)
    S[:p, :] = 1
    S[:, :p] = 1
    S[:, -p:] = 1
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

    @property
    def shape(self) -> tuple[int, int]:
        return self.ny, self.nx

    def to_world(self, cols: np.ndarray, rows: np.ndarray) -> np.ndarray:
        return np.stack([self.x0 + cols * self.cell, self.y0 + rows * self.cell], axis=-1)


class ZoneEngine:
    """ForumPlannerPolicy's forecast path on game-frame STATEs, and the zones of one frame (module docstring)."""

    def __init__(self, crest: str = "Wanderer", threads: int = 4, clash: str = DEFAULT_CLASH, cell: float = CELL,
                 margins: bool = False, zones_path: Path = ZONES_NPZ):
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
        self.zones = Zones(zones_path) if zones_path.exists() else None
        self.grid = Grid(cell)
        p = self.pol.params
        self.reach = (int(math.ceil(p.dash_speed * FT / cell)), int(math.ceil(p.jump_speed * FT / cell)),
                      int(math.ceil(p.max_fall * FT / cell)))
        self.running = False
        self.ws = None
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

    def feed(self, s: dict) -> bool:
        """One game-frame STATE (frames numbered consecutively): the forecast-only part of ForumPlannerPolicy.act."""
        pol = self.pol
        f = s["f"]
        pol.raw[f] = s
        for old in [k for k in pol.raw if k < f - 12]:
            del pol.raw[old]
        self.raw = s
        self.f_fed = f
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
                m = o[:, j].reshape(g.shape)
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

    def yellow(self, ks, fcast=None) -> tuple[dict, dict, dict]:
        """({k: committed-attack zone}, {k: not-started zone}, info) on the hero-centre grid."""
        from ssbot.core.forum import FLOOR_Y, FORUM_TYPES
        fcast = fcast or self.fcast
        g = self.grid
        com = {k: np.zeros(g.shape, bool) for k in ks}
        ns = {k: np.zeros(g.shape, bool) for k in ks}
        info = {"committed": [], "not_started": []}
        if fcast is None:
            return com, ns, info
        pm = fcast.pm
        owner = np.asarray(pm["owner"]) if len(pm["owner"]) else np.zeros(0, np.int64)
        commit = np.asarray(pm["committed"], bool) if len(pm["owner"]) else np.zeros(0, bool)
        K = YELLOW_F
        tkK = np.arange(K + 1, dtype=np.float64) * FT
        GX = GY = None
        ax_, up, dn = self.reach
        for s in fcast.subjects:
            if not s.alive or not s.committed:
                continue
            sel = (owner == s.iid) & commit
            if not sel.any():
                continue
            if GX is None:
                GX = np.ascontiguousarray(np.repeat(g.gx, K + 1, axis=1))
                GY = np.ascontiguousarray(np.repeat(g.gy, K + 1, axis=1))
            occ = fcast._fine_occ(GX, GY, tkK, sel)
            if not occ.any():
                continue
            D = occ.T.reshape(K + 1, *g.shape)
            last = int(np.flatnonzero(D.reshape(K + 1, -1).any(axis=1)).max())
            Z = erode_back(D[:last + 1], ax_, up, dn)
            for k in ks:
                if k <= last:
                    com[k] |= Z[k]
            info["committed"].append([s.iid, s.type_key, s.family, last])
        if self.zones is None:
            return com, ns, info
        hc = self.hero()
        ground, dashing, attacking, facing = self.lock()
        mf = self.pol.fc
        hrel = (g.gy[:, 0] - g.y0)
        for s in fcast.subjects:
            if not (s.alive and s.in_play) or s.committed or not math.isfinite(s.t_strike):
                continue
            tr = mf.trackers.get(s.iid)
            sp = FORUM_TYPES.get(s.type_key)
            if tr is None or tr.pos is None or sp is None:
                continue
            age = fcast.origin_t - tr.seen_T
            shown = False
            for k in ks:
                t = k * FT
                if t < s.t_strike - 1e-9:
                    continue
                ax = tr.pos[0] + tr.vel[0] * (age + t)
                ay = tr.pos[1] + tr.vel[1] * (age + t)
                toward = hc is not None and facing != 0 and np.sign(ax - hc[0]) == facing
                code = 3 if not ground else 2 if (dashing and toward) else 1 if attacking else 0
                dx = g.gx[:, 0] - ax
                lock = np.where(hrel > 0.25, 3, code).astype(np.int64)
                m = np.abs(dx) < 45.0
                z = np.zeros(len(dx), bool)
                z[m] = self.zones.occ(s.type_key, sp.idle_family, sp.entry_family, float(ay - FLOOR_Y), dx[m],
                                      hrel[m], lock[m])
                ns[k] |= z.reshape(g.shape)
                shown = True
            if shown:
                info["not_started"].append([s.iid, s.type_key, round(float(s.t_strike), 3)])
        return com, ns, info

    def compute(self, ks=KS, support: bool = True, yellow: bool = True) -> dict:
        """Everything drawn for the current frame: forecast, support per k, yellow per k, the colliders."""
        t0 = time.perf_counter()
        fc = self.forecast()
        t1 = time.perf_counter()
        sup = self.support(ks, fc) if support else {k: {} for k in ks}
        t2 = time.perf_counter()
        com, ns, info = self.yellow(ks, fc) if yellow else ({}, {}, {})
        t3 = time.perf_counter()
        s = self.raw or {}
        return {"f": s.get("f"), "f_raw": s.get("_f_raw", s.get("f")), "hero": self.hero(), "ks": tuple(ks),
                "support": sup, "ycom": com, "yns": ns, "info": info, "cols": damage_colliders(s),
                "cam": s.get("cam"), "running": fc is not None,
                "ms": {"forecast": round((t1 - t0) * 1e3, 1), "support": round((t2 - t1) * 1e3, 1),
                       "yellow": round((t3 - t2) * 1e3, 1)}}


# ------------------------------------------------------------------------------------------------ drawing

class View:
    """What is drawn (the live keys and the render options)."""
    MODES = ("yellow+red", "yellow", "red", "support", "all")

    def __init__(self, mode: str = "yellow+red", k: int = 0):
        self.on = True
        self.mode = mode
        self.k = k
        self.layers = {lay: True for lay in LAYERS}
        self.frozen = False
        self.note = ""

    def show(self, what: str) -> bool:
        if what == "support":
            return self.mode in ("support", "all")
        return self.mode == "all" or what in self.mode.split("+")

    def cycle(self) -> None:
        self.mode = self.MODES[(self.MODES.index(self.mode) + 1) % len(self.MODES)]


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
    sel = m.astype(bool)
    if sel.any():
        src = np.array([*color, 255.0]) * alpha
        roi[sel] = (roi[sel] * (1.0 - alpha) + src).astype(np.uint8)
    if outline:
        cv2.polylines(img, [p], True, (*[int(c * 0.75) for c in color], 255), outline, cv2.LINE_AA)


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
        if view.show("red"):
            th = max(1, int(round(1.5 * H / 1080)))
            for poly, clash, _, vel in fr.get("cols") or ():
                if clash:
                    continue
                hull = sweep_hull(poly, vel)
                _blend_poly(img, _to_px(Hw, hull), COLORS["red"], A_SWEEP)
                _blend_poly(img, _to_px(Hw, poly), COLORS["red"], A_RED, outline=th)
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
    lines = [(f"ZONES  k=+{k} f ({k / 60:.2f} s)  mode {view.mode}" + ("  FROZEN" if view.frozen else "")
              + (f"  {extra}" if extra else ""), None)]
    if view.show("yellow"):
        lines.append((NAMES["yellow"] + " (hero-centre space; committed: erosion lower bound, "
                      "not started: zones_lat1 for the lock now)", COLORS["yellow"]))
    if view.show("red"):
        lines.append((NAMES["red"] + " (the colliders themselves)", COLORS["red"]))
    if view.show("support"):
        for i, lay in enumerate(LAYERS):
            on = view.layers.get(lay)
            lines.append((f"Ctrl+{i + 1} {NAMES[lay]}{'' if on else '  (off)'}", COLORS[lay] if on else (90, 90, 90)))
    lines.append(("white dot = hero centre   F8 on/off  F9 mode  F10 freeze  F11 step  1-5 k  Ctrl+1-7 layers",
                  None))
    lines.append((config, None))
    if fr is not None and fr.get("info"):
        inf = fr["info"]
        c = ", ".join(f"{x[1].replace('Song ', '')}:{x[2]}" for x in inf.get("committed", [])[:4])
        lines.append((f"committed: {c or '-'}   not started: {len(inf.get('not_started', []))}", None))
    return lines


def draw_legend(img: np.ndarray, lines, view: View) -> None:
    import cv2
    H = img.shape[0]
    s = H / 1080.0
    fs, lh = 0.45 * s, int(round(18 * s))
    x0, y0 = int(round(12 * s)), H - int(round(12 * s)) - lh * len(lines)
    w = int(round(820 * s))
    roi = img[max(y0 - lh, 0):H - int(round(6 * s)), x0 - 6:x0 + w]
    roi[:] = (roi * 0.35 + np.array([0, 0, 0, 255.0]) * 0.65).astype(np.uint8)
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
                 every: int = 3, margins: bool = False, log_path: Path | None = None):
        self.link, self.pid = link, game_pid
        self.speed = speed if speed and speed > 0 else 1.0
        self.crest, self.threads, self.every, self.margins = crest, threads, max(1, every), margins
        self.view = View()
        self.q: queue.SimpleQueue = queue.SimpleQueue()
        self.cmds: queue.SimpleQueue = queue.SimpleQueue()
        self.terrain: dict | None = None
        self.stop_ev = threading.Event()
        self.stats = {"computed": 0, "fed": 0, "ms": [], "upd_ms": [], "max_backlog": 0, "errors": [],
                      "excluded_from_capture": None, "starts": 0}
        self.log_path = log_path
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
            self.eng = ZoneEngine(crest=self.crest, threads=self.threads, margins=self.margins)
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
                if win is not None and (since >= self.every or self.dirty):
                    t0 = time.perf_counter()
                    if self.eng.running and self.eng.ws is not None and (since >= self.every or fr is None
                                                                         or self.view.k not in fr["ks"]):
                        fr = self.eng.compute(ks=(self.view.k,), support=self.view.show("support"))
                        self.stats["computed"] += 1
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
                threads: int = 4) -> dict:
    """Log a human session's Forum attempts with the zone layers per game frame into a Rerun recording ("frame" =
    the raw oracle frame, as the video labels): world/ (y up, as tools.viewer) hero, the real damage colliders
    (colliders/non_clashable, colliders/clashable: the ground truth), zones/red (the non-clashable sweeps),
    zones/yellow/{committed, not_started}, support/k<k>/<layer>; with video, screen/video (the recorded frame) and the
    same outlines projected with the STATE camera (screen/zones/...)."""
    import cv2
    import rerun as rr
    from ssbot.tools.forum_human_score import load_segment, segments
    from ssbot.tools.viewer import closed, polygons_by_key
    eng = ZoneEngine(crest="Wanderer", threads=threads, margins=margins)
    g = eng.grid
    stats: dict = {"frames": 0, "attempts": [], "config": eng.config_text(), "compute_ms": []}
    segs = [s for s in segments(f"{session}:win", demo_cache)
            if (f1 is None or s["f0"] <= f1) and (f0 is None or s["f1"] >= f0)]
    vidx = _video_index(session) if video else {}
    size = (int(RENDER[0] * video_scale), int(RENDER[1] * video_scale))
    vf = VideoFrames(session, size) if video else None
    rr_ = 0.04

    def wl(pts):
        return [(float(x), -float(y)) for x, y in pts]

    def grid_world(c):
        return g.to_world(c[:, 0], c[:, 1])

    rec.log("legend", rr.TextDocument(
        "zones (hero-centre space: where the hero CENTRE must not be): yellow = inescapable (committed: erosion "
        "lower bound; not started: zones_lat1 for the lock now); red = non-clashable colliders + 6-frame sweep; "
        "colliders/* = the real damage colliders (ground truth); support/k<k>/<layer> = the planner's support at "
        f"look-ahead k. Config: {eng.config_text()}"), static=True)
    for seg in segs:
        terrain, states = load_segment(seg)
        eng.crest = seg.get("crest") or eng.crest
        eng.start(terrain)
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
            fr = eng.compute(ks=ks, support=True)
            stats["compute_ms"].append((time.perf_counter() - t0) * 1e3)
            rec.set_time("frame", sequence=int(fr_raw))
            rec.set_time("game_frame", sequence=int(s["f"]))
            hc = fr["hero"]
            rec.log("world/hero", rr.Points2D([(hc[0], -hc[1])] if hc else [], colors=[[255, 255, 255]],
                                              radii=[0.15]))
            cols = fr["cols"]
            nc = [p for p, c, _, _ in cols if not c]
            cl = [p for p, c, _, _ in cols if c]
            rec.log("world/colliders/non_clashable", rr.LineStrips2D(
                [closed(wl(p)) for p in nc], colors=[[255, 60, 60]], radii=[0.03],
                labels=[lb for p, c, lb, _ in cols if not c]))
            rec.log("world/colliders/clashable", rr.LineStrips2D(
                [closed(wl(p)) for p in cl], colors=[[240, 240, 240]], radii=[0.03],
                labels=[lb for p, c, lb, _ in cols if c]))
            sweeps = [sweep_hull(p, v) for p, c, _, v in cols if not c]
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


def zones_blueprint(video: bool):
    import rerun.blueprint as rrb
    views = [rrb.Spatial2DView(origin="world", name="world (y up): zones, colliders, hero")]
    if video:
        views.append(rrb.Spatial2DView(origin="screen", name="recorded video + zones"))
    return rrb.Blueprint(rrb.Horizontal(*views, rrb.TextDocumentView(origin="legend", name="legend"),
                                        column_shares=[3, 3, 1][:len(views)] + [1]), collapse_panels=True)


def cmd_render(a) -> int:
    import cv2
    session = Path(a.session)
    eng = ZoneEngine(crest="Wanderer", threads=a.threads, margins=a.margins)
    seg, terrain, states = attempt_states(session, a.attempt, Path(a.demo_cache) if a.demo_cache else None)
    eng.crest = seg.get("crest") or eng.crest
    vidx = _video_index(session)
    vf = VideoFrames(session)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    view = View(mode=a.mode, k=a.k)
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
        fr = eng.compute(ks=(a.k,), support=view.show("support"))
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
    eng = ZoneEngine(crest="Wanderer", threads=a.threads, margins=a.margins)
    seg, terrain, states = attempt_states(session, a.attempt, Path(a.demo_cache) if a.demo_cache else None)
    if a.limit_s:
        states = states[:int(a.limit_s * 60)]
    eng.start(terrain)
    view = View(mode="all", k=a.k)
    feed, comp, rend, rend4k, parts = [], [], [], [], []
    for s in states:
        t0 = time.perf_counter()
        eng.feed(s)
        feed.append((time.perf_counter() - t0) * 1e3)
        if s["f"] % a.every or s["f"] < 30:
            continue
        t0 = time.perf_counter()
        fr = eng.compute(ks=(a.k,), support=True)
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
           "yellow_ms": q([p["yellow"] for p in parts]), "config": eng.config_text()}
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
