"""The slam score map at run time (task 1v1 SG4; forum.md 59): the stored dense levels, the map state from the
planner's hero state, the map row (the one-step lookahead rolled over the planner's horizon on the hero macros),
readiness, the deviation and wall exits. Behind SSBOT_FORUM_SPECIAL_MAP (default off: nothing here is loaded).

Storage (the person's choice for run time, SG4 1c): one npz per map (zlib), per physics phase p the uint8 levels of
every macro state S{p} [K, 3, NS, NX] (keyed map: per state key c) or [K, NS, NX], and for a keyed map the press flags
P{p} (bit-packed [K, 3, NS, NX]: the node takes the slash with its key held), for an unkeyed one the strike levels
SV{p} [K, NS, NX, 3]. Decompressed at load (special_map_store builds it; RAM in forum.md 59).

Map coordinates (special_map / map_lookahead): k = frames since the Slam Antic entry (game-time clock), x = hero box
centre minus the Clapper's x at k = 0 along its facing (u, centre to centre), the vertical event (ground / jump h /
bounce at contact height yc, j frames since its start), the state key c (keyed maps: the key already read, moving the
body next frame), the physics phase p (frame k has a run step iff (k - p) % 6 != 0; unknown: the minimum per action
over the possible phases).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.combat import map_lookahead as ml
from ssbot.combat import special_map as sm
from ssbot.combat import special_map_jit as smj

MAP_ON = os.environ.get("SSBOT_FORUM_SPECIAL_MAP", "0").strip() == "1"
MAP_TAG = os.environ.get("SSBOT_FORUM_SPECIAL_MAP_TAG", "sg4").strip() or "sg4"
LAMBDA = float(os.environ.get("SSBOT_FORUM_SPECIAL_MAP_LAMBDA", "0.02") or 0.02)
# readiness penalty (hits per readiness unit below R_ref; R_ref from the file unless set)
READY_W = float(os.environ.get("SSBOT_FORUM_SPECIAL_MAP_READY_W", "0.4") or 0.4)
_RR = os.environ.get("SSBOT_FORUM_SPECIAL_MAP_READY_REF", "").strip()
READY_REF = float(_RR) if _RR else None
READY_RANGE_U = 8.05 + 0.5         # the Clapper's Slam Range (pos +- 8.05 u, forum.md 10) + the hero's half width
DEV_TOL_U = 0.2                    # the deviation exit: the Clapper off its anchor + the variants' displacement range
WALL_FRONT_U = 14.0                # leave the map when a wall is this close in front of the anchor (the hammer: 12 u)
WALL_BACK_U = 6.0                  # ... or behind it (no wall buckets for the SG4 maps)
ROW_EXTRA_F = 24                   # the map row's template past the planner's horizon (its tail check)
INF_LEVEL, NONE_LEVEL = sm.INF_LEVEL, sm.NONE_LEVEL
# SG6 (forum.md 62): the map row's rollout, the readiness and the batched lookups compiled (special_map_jit,
# bit-identical to the Python code here); SSBOT_FORUM_SPECIAL_MAP_JIT=0: the Python reference
JIT = smj.JIT


def map_path(tag: str = MAP_TAG) -> Path:
    return sm.MAP_DIR / f"special_map_CL_SLAM_{tag}_levels.npz"


# ---- storage ----
def level_scale(wc: float) -> float:
    """The level step for a config: two deep strikes (about 4.6) plus the clearance weight fit in 250 levels."""
    return max(0.02, float(np.ceil((4.6 + wc) / 250.0 / 0.005) * 0.005))


def to_levels(a: np.ndarray, scale: float) -> np.ndarray:
    a = np.asarray(a, np.float32)
    out = np.full(a.shape, INF_LEVEL, np.uint8)
    fin = np.isfinite(a)
    out[fin] = np.clip(np.rint(np.maximum(a[fin], 0.0) / scale), 0, 250).astype(np.uint8)
    return out


def press_flags(pm) -> np.ndarray:
    """[K, 3, NS, NX] bool: the keyed node takes the slash with its key held (its strike value is the node's)."""
    S = pm.S.astype(np.float32)                                  # [K, 3, NS, NX]
    SV = np.moveaxis(pm.SV.astype(np.float32), 3, 1)             # [K, 3, NS, NX]
    with np.errstate(invalid="ignore"):
        return np.isfinite(SV) & (SV >= S - 1e-3)


def phase_levels(pm, keyed: bool, scale: float) -> dict:
    """One phase map (keep_full) as the stored arrays."""
    out = {f"S{pm.p}": to_levels(pm.S, scale)}
    if keyed:
        out[f"P{pm.p}"] = np.packbits(press_flags(pm), axis=None)
    else:
        out[f"SV{pm.p}"] = to_levels(pm.SV, scale)
    return out


def save_levels(path: Path, geo, arrs: dict, phases: list, scale: float, meta: dict) -> dict:
    """The run-time file of one config's phases (arrs: phase_levels of each, merged)."""
    cfg = geo.cfg
    m = {"format": "ssbot.special_map_levels/1", "move": "CL_SLAM", "keyed": bool(cfg.keyed),
         "key_noise": cfg.key_noise, "p_late": list(cfg.p_late), "gamma": cfg.gamma, "wc": cfg.wc, "c_cap": cfg.c_cap,
         "scale": scale, "phases": [int(p) for p in phases], "tubes": ml.TubeIndex.from_geometry(geo).to_dict(),
         "config": cfg.key(), "end_min": geo.end_min, "end_max": geo.end_max, "K": geo.K, "NX": geo.NX,
         "NS": geo.NS} | meta
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, meta=json.dumps(m), **arrs)
    return m


class LevelSource:
    """One phase of a stored level map with the DenseSource / KeyedDenseSource interface (map_lookahead.decide)."""

    def __init__(self, S: np.ndarray, extra: np.ndarray, ti: ml.TubeIndex, p: int, meta: dict):
        self.p, self.ti = p, ti
        self.st = ml.steps(p, ti.K)
        self.keyed = bool(meta["keyed"])
        self.kind = "levels_keyed" if self.keyed else "levels"
        self.scale = float(meta["scale"])
        self._S = np.asarray(S)                          # a plain view of a memmap: scalar indexing 5x faster
        self._P = np.asarray(extra) if self.keyed else None   # packed bits of [K, 3, NS, NX] (np.packbits order)
        self._SV = None if self.keyed else np.asarray(extra)  # uint8 [K, NS, NX, 3]
        self._x_lo, self._step, self._NX, self._K = float(ti.x_lo), float(ti.step), int(ti.NX), int(ti.K)
        self.NS, self.NX = int(meta["NS"]), int(meta["NX"])
        self.mode = meta.get("key_noise", "none")
        pl = np.asarray(meta.get("p_late", (1, 0, 0, 0)), float)
        self.pl = pl / pl.sum()
        self.gamma = float(meta["gamma"])
        self.nq = 0
        # SG7 stage maps (meta "stage"): frame k -> the row of the arrays along one variant's path (-1: none); the
        # default is the first variant's; plain maps: the frame itself
        rows = meta.get("stage")
        self.rm = (np.asarray(rows["RM"][0], np.int64) if rows else np.arange(self._K)).copy()
        self.rm = np.concatenate([self.rm, np.full(16, -1, np.int64)])

    def with_rows(self, rm) -> "LevelSource":
        import copy
        o = copy.copy(self)
        o.rm = np.concatenate([np.asarray(rm, np.int64)[:self._K], np.full(16, -1, np.int64)])
        return o

    def _xi(self, k, s, x):
        if s is None or s < 0 or not 0 <= k < self._K or self.rm[k] < 0:
            return -1
        xi = int(round((x - self._x_lo) / self._step))
        return xi if 0 <= xi < self._NX else -1

    def _v(self, lv) -> float:
        lv = int(lv)
        return -np.inf if lv >= NONE_LEVEL else lv * self.scale

    def S(self, k: int, s: int, x: float, c: int = 0) -> float:
        xi = self._xi(k, s, x)
        self.nq += 1
        if xi < 0:
            return -np.inf
        r = self.rm[k]
        return self._v(self._S[r, c + 1, s, xi] if self.keyed else self._S[r, s, xi])

    def Smax(self, k: int, s: int, x: float) -> float:
        xi = self._xi(k, s, x)
        self.nq += 1
        if xi < 0:
            return -np.inf
        S_ = self._S
        r = self.rm[k]
        m = -1
        for c in range(3):
            lv = int(S_[r, c, s, xi])
            if lv < NONE_LEVEL and lv > m:
                m = lv
        return m * self.scale if m >= 0 else -np.inf

    def pbit(self, k: int, c: int, s: int, xi: int) -> bool:
        idx = ((k * 3 + c + 1) * self.NS + s) * self.NX + xi
        return bool((int(self._P[idx >> 3]) >> (7 - (idx & 7))) & 1)

    def SV(self, k: int, s: int, x: float, d: int) -> float:
        xi = self._xi(k, s, x)
        self.nq += 1
        if xi < 0:
            return -np.inf
        r = self.rm[k]
        if self.keyed:
            return self._v(self._S[r, d + 1, s, xi]) if self.pbit(r, d, s, xi) else -np.inf
        return self._v(self._SV[r, s, xi, d + 1])

    def press(self, k: int, s: int, x: float, d: int) -> bool:
        sv = self.SV(k, s, x, d)
        return bool(np.isfinite(sv) and sv >= self.S(k, s, x) - ml.PRESS_EPS)


CACHE = Path(os.environ.get("SSBOT_FORUM_SPECIAL_MAP_CACHE", "C:/ssbot/cache/special_map"))
MMAP = os.environ.get("SSBOT_FORUM_SPECIAL_MAP_MMAP", "1").strip() != "0"


def load_levels(path: Path | None = None, mmap: bool = MMAP) -> tuple[dict, ml.TubeIndex, dict]:
    """{p: LevelSource}, the tube index, meta. mmap (default): the arrays are decompressed once into CACHE (one .npy
    per array, keyed by the file's size and mtime) and memory-mapped (file-backed pages shared by every process, only
    the frames a slam touches are read); else decompressed into the process's RAM."""
    t0 = time.time()
    path = Path(path or map_path())
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    ti = ml.TubeIndex.from_dict(meta["tubes"])
    names = [f"S{p}" for p in meta["phases"]] + [(f"P{p}" if meta["keyed"] else f"SV{p}") for p in meta["phases"]]
    if mmap:
        st_ = path.stat()
        d = CACHE / f"{path.stem}_{st_.st_size}_{int(st_.st_mtime)}"
        if not (d / "done").exists():
            # review: written into a private directory and renamed into place, so two brain processes starting
            # together never map (or overwrite) each other's half-written arrays; the loser of the rename uses the
            # winner's copy
            tmp = CACHE / f".{d.name}.{os.getpid()}.{time.time_ns()}"
            tmp.mkdir(parents=True, exist_ok=True)
            for nm in names:
                np.save(tmp / f"{nm}.npy", z[nm])
            (tmp / "done").write_text("ok", "utf-8")
            import shutil
            for attempt in range(2):
                try:
                    os.replace(tmp, d)
                    break
                except OSError:
                    if (d / "done").exists() or attempt:
                        break
                    shutil.rmtree(d, ignore_errors=True)   # a half-written directory left by a crashed writer
            if not (d / "done").exists():
                d = tmp                                   # the rename lost to a directory without "done": use ours
            elif tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        arr = {nm: np.load(d / f"{nm}.npy", mmap_mode="r") for nm in names}
    else:
        arr = {nm: z[nm] for nm in names}
    srcs = {}
    for p in meta["phases"]:
        extra = arr[f"P{p}"] if meta["keyed"] else arr[f"SV{p}"]
        srcs[int(p)] = LevelSource(arr[f"S{p}"], extra, ti, int(p), meta)
    meta["load_s"] = round(time.time() - t0, 2)
    meta["mmap"] = bool(mmap)
    meta["array_mb"] = round(sum(a.nbytes for a in arr.values()) / 1e6, 1)
    return srcs, ti, meta


# ---- several phases: the minimum per action ----
def decide_multi(srcs: list, k: int, ev: dict, x: float, c: int, last_press: int, lam: float, land: int | None):
    """decide() on each candidate phase's source; per action the minimum value over the phases (an action some phase
    does not offer is out); (value, action, per-phase candidates). One phase: decide() itself."""
    if len(srcs) == 1:
        return ml.decide(srcs[0], k, ev, x, c, last_press, lam, land)
    vals: dict = {}
    for i, s in enumerate(srcs):
        _, _, cands = ml.decide(s, k, ev, x, c, last_press, lam, land)
        seen = {}
        for v, a in cands:
            seen[a] = max(seen.get(a, -np.inf), v)
        for a, v in seen.items():
            if i == 0:
                vals[a] = v
            elif a in vals:
                vals[a] = min(vals[a], v)
        for a in list(vals):
            if a not in seen:
                del vals[a]
    if not vals:
        act = ("dir", 1 if x >= 0 else -1) if ev["kind"] == "ground" else ("dir", c)
        return -np.inf, act, []
    a, v = max(vals.items(), key=lambda t: t[1])
    if not np.isfinite(v) and v < 0:
        a = ("dir", 1 if x >= 0 else -1) if ev["kind"] == "ground" else ("dir", c)
    return v, a, [(vv, aa) for aa, vv in vals.items()]


def phases_of(alo: float, ahi: float, k: int) -> list[int]:
    """The map phases p possible for a hero whose ALPHA lies in [alo, ahi] at move frame k: the cycle q at that frame
    (hero_macros.ALPHAS[q] = ((q - 0.5) / 6) % 1, each q owning alpha in [(q - 1) / 6, q / 6)), p = (q + k) % 6."""
    lo, hi = float(alo), float(ahi)
    if hi < lo:
        lo, hi = hi, lo
    qs = set()
    a = lo
    while True:
        qs.add(int(np.floor(6.0 * (a % 1.0) + 1.0)) % 6)
        if a >= hi:
            break
        a = min(a + 1.0 / 12.0, hi)
    return sorted({(q + int(k)) % 6 for q in qs})


@dataclass
class MapPlan:
    """The map row from one state: masks [L] (the planner's key bits per frame after the prefix), the map's value of
    the first decision, the press frames and model contacts (row indices), the hero's model x / y per frame, the
    action per frame, the phases used, k0 = the start frame; plan() adds states (the loop state before each frame's
    decision), values (each decision's value) and final (the loop state at the end, MapRuntime.extend)."""
    masks: np.ndarray
    value: float
    first: tuple
    presses: list
    contacts: list
    xs: np.ndarray
    ys: np.ndarray
    acts: list
    phases: list
    k0: int
    ms: float = 0.0
    info: dict = field(default_factory=dict)


class MapRuntime:
    """The loaded map, the hero macros (vertical profiles, run steps, render lag) and the move's nominal timeline."""

    def __init__(self, params, terrain, path: Path | None = None, srcs=None, ti=None, meta=None, hm=None):
        from ssbot.combat.hero_macros import HeroMacros
        from ssbot.combat.move_data import load_cl_slam
        from ssbot.combat.pogo_model import slash_poly
        t0 = time.time()
        if srcs is None:
            srcs, ti, meta = load_levels(path)
        self.srcs, self.ti, self.meta = srcs, ti, meta
        self.hm = hm if hm is not None else HeroMacros(params, terrain)
        self.spec = load_cl_slam()
        K = ti.K + 30
        self.tl = self.spec.timeline(K=K)
        vs = self.spec.variants("observed")
        D = np.stack([np.pad(v.disp, (0, max(0, K - len(v.disp))), mode="edge")[:K] for v in vs])
        self.disp_lo, self.disp_hi = D.min(0), D.max(0)
        self.end_min = int(meta.get("end_min", min(v.end_k for v in vs)))
        self.end_max = int(meta.get("end_max", max(v.end_k for v in vs)))
        self.polys = {(f, a): slash_poly(f, a) for f in (1, -1) for a in (False, True)}
        self.pa = self.spec.pos_above_floor
        self.wc = float(meta["wc"])
        self.keyed = bool(meta["keyed"])
        self._ready_ref = READY_REF if READY_REF is not None else float(meta.get("ready_ref", self.wc + 1.0))
        self._tube_y()
        # SG7 stage maps (meta "stage", forum.md 63): the rows' table and each variant's row map; rows = the row maps
        # of the variants consistent with what the hero has seen (set by forum_map per tick; None: every variant's);
        # plan_tl = the timeline whose targets the map row's contacts use (None: the nominal)
        self.stage = meta.get("stage")
        self.rows = None
        self.plan_tl = None
        self._tgt_cache: dict = {}
        if self.stage:
            self.RMv = np.asarray(self.stage["RM"], np.int64)
            self.vtl = [self.spec.timeline(v["frames"], v["phase"], K=K) for v in self.stage["variants"]]
            self.all_rows = [np.asarray(r, np.int64) for r in np.unique(self.RMv, axis=0)]
        # SG6: the compiled kernels' tables (built here: the map's load, never on a slam tick)
        self.use_jit = JIT
        self._jt = None
        if self.use_jit:
            self.jit_tables()
        self.init_s = round(time.time() - t0, 2)

    # ---- SG7: the sources = phases x the observation's row maps ----
    def _rowmaps(self) -> list:
        if self.rows:
            return list(self.rows)
        if self.stage:
            return list(self.all_rows)
        return [None]

    def _srcs(self, phases) -> list:
        return [self.srcs[p] if rm is None else self.srcs[p].with_rows(rm) for p in phases for rm in self._rowmaps()]

    def _ph_rm(self, phases) -> tuple:
        K = self.ti.K
        pairs = [(p, rm) for p in phases for rm in self._rowmaps()]
        ph = np.array([p for p, _ in pairs], np.int64)
        RM = np.stack([np.asarray(self.srcs[p].rm[:K] if rm is None else np.asarray(rm)[:K], np.int64)
                       for p, rm in pairs])
        return ph, np.ascontiguousarray(RM)

    def observe(self, seen: dict | None, k_now: int | None = None, lat: int = 0) -> list:
        """SG7: set rows / plan_tl from what the hero has seen of the slam's stage entries: seen = {stage: entry
        frame} ("Slam 0", "Slam 1", "Slam 2", "Slam Recover"; the antic's is 0) and the stage it is in at frame k_now
        (the observation's frame: the planner's frame minus the transition latency lat). The consistent variants: each
        seen entry equal to the variant's, the variant in the same stage at k_now - lat (an unseen next stage has not
        started by then). Returns the consistent variants' indices (every variant: nothing known / a plain map)."""
        self.rows, self.plan_tl = None, None
        if not self.stage or seen is None or k_now is None:
            return list(range(len(self.vtl))) if self.stage else []
        ko = max(int(k_now) - int(lat), 0)
        cur = max(seen, key=lambda st_: seen[st_]) if seen else "Slam Antic"
        ok = []
        for vi, tl in enumerate(self.vtl):
            if any(int(tl.entry.get(st_, -1)) != int(e) for st_, e in seen.items() if st_ != "Slam Antic"):
                continue
            st_k = tl.state[ko] if ko < len(tl.state) else "after"
            if cur == "Slam Recover":
                if st_k not in ("Slam Recover", "after"):
                    continue
            elif st_k != cur:
                continue
            ok.append(vi)
        if not ok:                                   # an observation no variant explains: every variant
            return list(range(len(self.vtl)))
        self.rows = [np.asarray(r, np.int64) for r in np.unique(self.RMv[ok], axis=0)]
        # the plan's contacts on the consistent variant nearest the nominal timing
        nom = self.spec.timeline(K=len(self.tl.state))
        best = min(ok, key=lambda vi: sum(abs(int(self.vtl[vi].frames[st_]) - int(nom.frames[st_]))
                                          for st_ in nom.frames) + abs(self.vtl[vi].phase - nom.phase))
        self.plan_tl = self.vtl[best]
        return ok

    def jit_tables(self) -> dict | None:
        """special_map_jit.tables (None: not a keyed level map; the Python path)."""
        if self._jt is None:
            self._jt = smj.tables(self) or False
        return self._jt or None

    @property
    def ready_ref(self) -> float:
        return self._ready_ref

    # ---- the tube heights (special_map.Geometry._tubes' construction from the macros) ----
    def _tube_y(self):
        hm, ti = self.hm, self.ti
        nt = len(ti.kinds)
        JM = max(ti.n) + 4
        self.TY = np.full((nt, 6, JM), 50.0)
        for i, (kd, prm) in enumerate(zip(ti.kinds, ti.params)):
            if kd == "jump":
                for q in range(6):
                    y = hm.jumps[(int(prm) if float(prm).is_integer() else prm, q)].y
                    n = min(len(y), JM)
                    self.TY[i, q, :n] = y[:n]
            elif kd == "bounce":
                for q in range(6):
                    y = prm + hm.bounces[q].y
                    n = min(len(y), JM)
                    self.TY[i, q, :n] = y[:n]
            else:
                self.TY[i] = 0.0

    def land_of(self, ev: dict) -> int | None:
        hm = self.hm
        if ev["kind"] == "jump":
            return int(hm.jumps[(int(ev["h"]), int(ev["q0"]))].land)
        if ev["kind"] == "bounce":
            b = hm.bounces[int(ev["q0"])]
            y = ev["yc"] + b.y
            below = np.flatnonzero(y[b.apex:] <= 0.0)
            return int(b.apex + int(below[0])) if len(below) else len(y)
        return None

    def y_of(self, ev: dict, j: int) -> tuple[float, float]:
        """(box bottom above the floor, rendered pos y offset) of the event at index j."""
        hm = self.hm
        if ev["kind"] == "jump":
            p = hm.jumps[(int(ev["h"]), int(ev["q0"]))]
            j = min(j, len(p.y) - 1)
            return float(p.y[j]), float(p.py[j])
        if ev["kind"] == "bounce":
            b = hm.bounces[int(ev["q0"])]
            j = min(j, len(b.y) - 1)
            return float(ev["yc"] + b.y[j]), float(b.py[j])
        return 0.0, float(hm.jumps[(1, 0)].py[0])

    # ---- the map state of an airborne hero: the tube slices matching its recent heights ----
    def locate(self, k: int, ys: list, p: int, tol: float = 0.06) -> list[int]:
        """Slices s at frame k (phase p) whose heights match ys (box bottom above the floor, newest first)."""
        ti = self.ti
        J = ti.SJ
        T = ti.ST
        q = (p - k + J) % 6
        kinds = np.array(ti.kinds)[T]
        ok = (J >= len(ys) - 1) & (J < ti.LA[T, q]) & (kinds != "ground")
        for i, yy in enumerate(ys):
            ok &= np.abs(self.TY[T, q, np.maximum(J - i, 0)] - yy) <= tol
        return np.flatnonzero(ok).tolist()

    def ev_of_slice(self, s: int, k: int, p: int) -> dict:
        ti = self.ti
        t = int(ti.ST[s])
        j = int(ti.SJ[s])
        kd, prm = ti.kinds[t], ti.params[t]
        k0 = k - j
        ev = {"kind": kd, "k": k0, "q0": (p - k0) % 6}
        if kd == "jump":
            ev["h"] = int(prm) if float(prm).is_integer() else prm
        elif kd == "bounce":
            ev["yc"] = float(prm)
        return ev

    # ---- readiness ----
    def readiness(self, x: float, c: int, p: int, slices: list | None = None) -> float:
        """The score at the antic entry (k = 0, phase p) for a hero at map x with state key c: the ground layer
        (slices None) or the minimum over the matched airborne slices."""
        src = self.srcs[p]
        if not slices:
            return src.S(0, 0, x, c) if self.keyed else src.S(0, 0, x)
        v = [src.S(0, s, x, c) if self.keyed else src.S(0, s, x) for s in slices]
        return float(min(v))

    def ready_slices(self, p: int, y_now: float, y_prev: float, tol: float = 0.08) -> list[int]:
        return self.locate(0, [y_now, y_prev], p, tol)

    def _k0_slices(self, p: int):
        """The airborne slices that are states at k = 0 in phase p and their heights at j and j - 1 (cached)."""
        c = getattr(self, "_k0c", None)
        if c is None:
            c = self._k0c = {}
        if p not in c:
            ti = self.ti
            J, T = ti.SJ, ti.ST
            q = (p + J) % 6
            kinds = np.array(ti.kinds)[T]
            ok = (J >= 1) & (J < ti.LA[T, q]) & (kinds != "ground")
            s = np.flatnonzero(ok)
            c[p] = (s, self.TY[T[s], q[s], J[s]], self.TY[T[s], q[s], J[s] - 1])
        return c[p]

    def readiness_rows(self, p: int, xm: np.ndarray, kd: np.ndarray, gnd: np.ndarray, yb: np.ndarray,
                       yp: np.ndarray, tol: float = 0.08) -> np.ndarray:
        """[N] readiness of end states at k = 0 (phase p): map x xm, state key kd (map frame), on the ground or the
        minimum over the airborne slices matching the last two box bottoms (none matched: 0, off the macros)."""
        src = self.srcs[p]
        xm, kd, gnd, yb, yp = (np.asarray(a) for a in (xm, kd, gnd, yb, yp))
        key = np.stack([np.rint(xm / self.ti.step), kd, gnd.astype(float), np.where(gnd, 0, np.rint(yb / 0.01)),
                        np.where(gnd, 0, np.rint(yp / 0.01))], axis=1)
        uk, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        if len(uk) < len(xm):                                     # many rows end in the same state
            Ru = self.readiness_rows(p, xm[first], kd[first], gnd[first], yb[first], yp[first], tol)
            return Ru[np.asarray(inv).reshape(-1)]
        S0 = np.asarray(src._S[0], np.int64)                      # [3, NS, NX] or [NS, NX]
        xi = np.clip(np.rint((np.asarray(xm) - self.ti.x_lo) / self.ti.step).astype(np.int64), 0, self.ti.NX - 1)
        inside = (np.asarray(xm) >= self.ti.x_lo) & (np.asarray(xm) <= self.ti.x_lo + self.ti.step * (self.ti.NX - 1))
        c = np.asarray(kd, np.int64) + 1

        def val(lv):
            return np.where(lv >= NONE_LEVEL, -np.inf, lv * src.scale)
        R = np.zeros(len(xm))
        g = np.asarray(gnd, bool)
        if g.any():
            lv = S0[c[g], 0, xi[g]] if self.keyed else S0[0, xi[g]]
            R[g] = val(lv)
        a = ~g
        if a.any():
            s, y0, y1 = self._k0_slices(p)
            ia = np.flatnonzero(a)
            m = (np.abs(np.asarray(yb)[ia, None] - y0[None, :]) <= tol) & (np.abs(np.asarray(yp)[ia, None] - y1[None, :]) <= tol)
            for r, i in enumerate(ia):
                ss = s[m[r]]
                if not len(ss):
                    R[i] = 0.0
                    continue
                lv = S0[c[i], ss, xi[i]] if self.keyed else S0[ss, xi[i]]
                R[i] = float(val(lv).min())
        R[~inside] = -np.inf
        return R

    def readiness_min(self, phases, xm: np.ndarray, kd: np.ndarray, gnd: np.ndarray, yb: np.ndarray,
                      yp: np.ndarray, tol: float = 0.08) -> np.ndarray:
        """[N] the minimum over phases of readiness_rows (SG6: one compiled call with the JIT)."""
        T = self.jit_tables() if self.use_jit else None
        if T is None:
            R = np.full(len(xm), np.inf)
            for p in phases:
                R = np.minimum(R, self.readiness_rows(p, xm, kd, gnd, yb, yp, tol))
            return R
        ti = self.ti
        return smj.ready_k(T["Ss"], np.asarray(list(phases), np.int64), smj.wr(xm, np.float64),
                           smj.wr(kd, np.int64), smj.wr(gnd, np.bool_), smj.wr(yb, np.float64),
                           smj.wr(yp, np.float64), float(tol),
                           T["K0S"], T["K0Y0"], T["K0Y1"], T["K0N"], float(ti.x_lo), float(ti.step), int(ti.NX),
                           float(T["cf"][smj.CF_SCALE]))

    def S_min(self, phases, ks, ss, xs, cs) -> np.ndarray:
        """[n] min over phases of the sources' S(k, s, x, c) (keyed; unkeyed: S(k, s, x)), elementwise (scalars
        broadcast). SG6: one compiled call with the JIT (the L2 strip, the off-board spot, the swing lock)."""
        xs = smj.wr(np.asarray(xs, np.float64).reshape(-1), np.float64)
        n = len(xs)
        ks, ss, cs = (np.array(np.broadcast_to(np.asarray(a, np.int64), (n,))) for a in (ks, ss, cs))
        T = self.jit_tables() if self.use_jit else None
        if T is None:
            srcs = self._srcs(phases)
            return np.array([min(sr.S(int(k), int(s), float(x), int(c)) if self.keyed else
                                 sr.S(int(k), int(s), float(x)) for sr in srcs)
                             for k, s, x, c in zip(ks, ss, xs, cs)], np.float64).reshape(n)
        ti = self.ti
        ph, RM = self._ph_rm(phases)
        return smj.smin_k(T["Ss"], ph, RM, ks, ss, xs, cs, int(ti.K),
                          int(ti.NX), float(T["cf"][smj.CF_XLO]), float(T["cf"][smj.CF_STEP]),
                          float(T["cf"][smj.CF_SCALE]))

    def _plan_tgt(self, T: dict):
        """(TGT, NTGT) of the plan's timeline (the nominal's from the tables; SG7: the observation's)."""
        if self.plan_tl is None:
            return T["TGT"], T["NTGT"]
        key = self.plan_tl.name
        if key not in self._tgt_cache:
            KT = T["KT"]
            tg = [np.asarray(self.plan_tl.targets(k), np.float64).reshape(-1, 4) for k in range(KT)]
            nb = max(T["TGT"].shape[1], max(len(t) for t in tg))
            TGT = np.zeros((KT, nb, 4))
            NTGT = np.zeros(KT, np.int64)
            for k_, t in enumerate(tg):
                TGT[k_, :len(t)] = t
                NTGT[k_] = len(t)
            self._tgt_cache[key] = (TGT, NTGT)
        return self._tgt_cache[key]

    # ---- the exits ----
    def deviation(self, k: int, cx: float, x0: float, face: int) -> float:
        """How far the Clapper's x lies outside anchor + the variants' displacement range at frame k (u, >= 0)."""
        kk = int(np.clip(k, 0, len(self.disp_lo) - 1))
        lo = x0 + face * self.disp_lo[kk]
        hi = x0 + face * self.disp_hi[kk]
        a, b = min(lo, hi), max(lo, hi)
        return float(max(a - cx, cx - b, 0.0))

    @staticmethod
    def wall_exit(x0: float, face: int, arena: tuple) -> bool:
        lo, hi = arena
        front = (hi - x0) if face > 0 else (x0 - lo)
        back = (x0 - lo) if face > 0 else (hi - x0)
        return front < WALL_FRONT_U or back < WALL_BACK_U

    # ---- the map row ----
    def plan(self, k: int, x: float, ev: dict, c: int, last_press: int, phases: list, L: int,
             lam: float = LAMBDA, face_hero: int = 1, face: int = 1, resume: dict | None = None,
             slash: dict | None = None) -> MapPlan:
        """plan_py (below); SG6: the compiled loop (plan_jit, the same MapPlan) when the JIT is on."""
        if self.use_jit:
            T = self.jit_tables()
            if T is not None:
                pl = self.plan_jit(T, k, x, ev, c, last_press, phases, L, lam, face_hero, face, resume, slash)
                if pl is not None:
                    return pl
        return self.plan_py(k, x, ev, c, last_press, phases, L, lam, face_hero, face, resume, slash)

    def decide_jit(self, phases, k: int, ev: dict, x: float, c: int, last_press: int, lam: float,
                   land: int | None) -> tuple | None:
        """decide_multi([srcs[p] for p in phases], ...)'s (value, action) from the compiled kernel (None: no
        tables)."""
        T = self.jit_tables()
        if T is None:
            return None
        ti = self.ti
        kind, tube = smj.EV_GROUND, 0
        if ev["kind"] == "jump":
            kind, tube = smj.EV_JUMP, ti._jt[float(ev["h"])]
        elif ev["kind"] == "bounce":
            kind, tube = smj.EV_BOUNCE, ti.bounce_t[int(np.clip(np.floor(ev["yc"] / ti.cb_w), 0, ti.ncb - 1))]
        ph, RM = self._ph_rm(phases)
        v, a0, a1, a2 = smj.decide_k(T["Ss"], T["Ps"], ph, RM, int(k), kind,
                                     int(ev["k"]), tube, 0 if land is None else int(land), land is not None, float(x),
                                     int(c), int(last_press), float(lam), T["ci"], T["cf"], T["pl"], T["gp"], T["TS0"],
                                     T["TN"], T["JS0"])
        act = ("dir", a1) if a0 == smj.A_DIR else (("jump", ti.jump_h[a1], a2) if a0 == smj.A_JUMP else
                                                     ("press", a1))
        return float(v), act

    def plan_jit(self, T: dict, k, x, ev, c, last_press, phases, L, lam=LAMBDA, face_hero=1, face=1, resume=None,
                 slash=None) -> MapPlan | None:
        """plan_py as one compiled loop (special_map_jit.plan_k); None: a state the tables do not cover (the
        Python path)."""
        t0 = time.perf_counter()
        ti = self.ti
        if resume is not None:
            ls = dict(resume)
            ls["ev"] = dict(ls["ev"])
        else:
            ev = dict(ev)
            ls = {"k": int(k), "x": float(x), "ev": ev, "land": self.land_of(ev) if ev["kind"] != "ground" else None,
                  "dir": int(c), "facing": int(face_hero), "slash": slash, "lsd": 0, "lp": int(last_press)}
        ev0 = ls["ev"]
        si = np.zeros(smj.NSI, np.int64)
        sf = np.zeros(smj.NSF)
        si[smj.SI_K] = ls["k"]
        sf[smj.SF_X] = ls["x"]
        kd = ev0["kind"]
        si[smj.SI_EVSRC] = smj.SRC_INPUT
        si[smj.SI_EVK] = ev0["k"]
        if kd == "jump":
            ji = T["jidx"].get(int(ev0["h"]))
            tb = ti._jt.get(float(ev0["h"]))
            if ji is None or tb is None:
                return None
            si[smj.SI_EVKIND] = smj.EV_JUMP
            si[smj.SI_EVJ] = ji
            si[smj.SI_EVQ0] = int(ev0["q0"])
            si[smj.SI_EVTUBE] = tb
            sf[smj.SF_H] = float(ev0["h"])
        elif kd == "bounce":
            si[smj.SI_EVKIND] = smj.EV_BOUNCE
            si[smj.SI_EVQ0] = int(ev0["q0"])
            sf[smj.SF_YC] = float(ev0["yc"])
            si[smj.SI_EVTUBE] = ti.bounce_t[int(np.clip(np.floor(ev0["yc"] / ti.cb_w), 0, ti.ncb - 1))]
        elif kd != "ground":
            return None
        if ls["land"] is not None:
            si[smj.SI_HASLAND] = 1
            si[smj.SI_LAND] = int(ls["land"])
        si[smj.SI_DIR] = ls["dir"]
        si[smj.SI_FACING] = ls["facing"]
        sl = ls["slash"]
        if sl is not None:
            si[smj.SI_HASSL] = 1
            si[smj.SI_SLP] = int(sl["P"])
            si[smj.SI_SLFACE] = int(sl["face"])
        si[smj.SI_LSD] = ls["lsd"]
        si[smj.SI_LP] = ls["lp"]
        k_start = ls["k"]
        (masks, xs, ys, act, vals, sti, stf, press, cont, n, s, f, has_first, v_first,
         first) = smj.plan_k(T["Ss"], T["Ps"], *self._ph_rm(phases), si, sf, int(L), float(lam),
                             int(face), *smj.plan_args(T, self._plan_tgt(T)))
        JH = ti.jump_h

        def act_of(a):
            if a[0] == smj.A_DIR:
                return ("dir", a[1])
            if a[0] == smj.A_JUMP:
                return ("jump", JH[a[1]], a[2])
            if a[0] == smj.A_PRESS:
                return ("press", a[1])
            return ("slash",)
        KN = ("ground", "jump", "bounce")
        n = int(n)
        acts = [act_of(a) for a in act[:n].tolist()]
        values = [np.nan if a[0] == "slash" else v for a, v in zip(acts, vals[:n].tolist())]
        states = []
        for si_, sf_ in zip(sti[:n].tolist(), stf[:n].tolist()):
            src_ = si_[smj.SI_EVSRC]
            if src_ == smj.SRC_INPUT:
                h, yc = ev0.get("h"), ev0.get("yc")
            elif src_ == smj.SRC_JUMP:
                h, yc = JH[si_[smj.SI_EVJ]], None
            elif src_ == smj.SRC_BOUNCE:
                h, yc = None, sf_[smj.SF_YC]
            else:
                h, yc = None, None
            states.append((si_[smj.SI_K], sf_[smj.SF_X], KN[si_[smj.SI_EVKIND]], si_[smj.SI_EVK], h, yc,
                           si_[smj.SI_DIR], si_[smj.SI_LP], si_[smj.SI_HASSL] != 0))
        s = s.tolist()
        f = f.tolist()
        src_ = s[smj.SI_EVSRC]
        if src_ == smj.SRC_INPUT:
            evf = dict(ev0)
        elif src_ == smj.SRC_JUMP:
            evf = {"kind": "jump", "h": JH[s[smj.SI_EVJ]], "k": s[smj.SI_EVK], "q0": s[smj.SI_EVQ0]}
        elif src_ == smj.SRC_BOUNCE:
            evf = {"kind": "bounce", "yc": f[smj.SF_YC], "k": s[smj.SI_EVK], "q0": s[smj.SI_EVQ0]}
        else:
            evf = {"kind": "ground", "k": s[smj.SI_EVK]}
        slf = None
        if s[smj.SI_HASSL]:
            slf = {"P": s[smj.SI_SLP], "face": s[smj.SI_SLFACE]}
            if sl is not None and slf == sl:
                slf = sl
        final = {"k": s[smj.SI_K], "x": f[smj.SF_X], "ev": evf, "land": s[smj.SI_LAND] if s[smj.SI_HASLAND] else None,
                 "dir": s[smj.SI_DIR], "facing": s[smj.SI_FACING], "slash": slf, "lsd": s[smj.SI_LSD],
                 "lp": s[smj.SI_LP]}
        pl = MapPlan(masks, float(v_first) if has_first else -np.inf, act_of(first.tolist()) if has_first else None,
                     np.flatnonzero(press[:n]).tolist(), np.flatnonzero(cont[:n]).tolist(), xs[:n], ys[:n], acts,
                     list(phases), k_start, (time.perf_counter() - t0) * 1e3)
        pl.rows, pl.plan_tl = self.rows, self.plan_tl
        pl.states = states
        pl.values = values
        pl.final = final
        return pl

    def plan_py(self, k: int, x: float, ev: dict, c: int, last_press: int, phases: list, L: int,
                lam: float = LAMBDA, face_hero: int = 1, face: int = 1, resume: dict | None = None,
                slash: dict | None = None) -> MapPlan:
        """Roll the lookahead over L frames from the state at the end of frame k (noise free, the macro model; the
        contact on the nominal timeline's target boxes with the real slash polygon). masks[t] = the inputs of frame
        k + 1 + t (planner key bits; the map key d is the world key d x face, face = the Clapper's facing); c,
        face_hero: the state key and the hero's facing in map coordinates; presses / contacts: row indices.
        resume: a previous plan's final loop state (MapPlan.final) to continue from (k, x, ev, c ignored)."""
        from ssbot.combat import dslash
        from ssbot.combat.hero_macros import key_mask
        from ssbot.combat.pogo_model import ACTIVE
        from ssbot.combat.pogo_slam import clip_band
        from ssbot.knowledge import kinematics as kin
        t0 = time.perf_counter()
        srcs = self._srcs(phases)
        p0 = phases[0]
        st = srcs[0].st
        tl_c = self.plan_tl if self.plan_tl is not None else self.tl
        step = self.ti.step
        hm = self.hm
        if resume is not None:
            ls = dict(resume)
            ls["ev"] = dict(ls["ev"])
        else:
            ev = dict(ev)
            ls = {"k": int(k), "x": float(x), "ev": ev, "land": self.land_of(ev) if ev["kind"] != "ground" else None,
                  "dir": int(c), "facing": int(face_hero), "slash": slash, "lsd": 0, "lp": int(last_press)}
        k_start = ls["k"]
        masks = np.zeros(L, np.int64)
        xs, ys = np.zeros(L), np.zeros(L)
        acts, presses, contacts, states, values = [], [], [], [], []
        value, first = None, None
        n = 0
        for t in range(L):
            k = ls["k"]
            if k >= self.ti.K - 5:
                break
            ev = ls["ev"]
            states.append((k, ls["x"], ev["kind"], ev["k"], ev.get("h"), ev.get("yc"), ls["dir"], ls["lp"],
                           ls["slash"] is not None))
            jump_now, press_now = None, False
            dir_cur = ls["dir"]
            if ls["slash"] is None:
                v, act, _ = decide_multi(srcs, k, ev, ls["x"], dir_cur, ls["lp"], lam, ls["land"])
                values.append(float(v))
                if value is None:
                    value, first = float(v), act
                acts.append(act)
                new_dir = dir_cur
                if act[0] == "dir":
                    new_dir = act[1]
                elif act[0] == "jump":
                    jump_now, new_dir = act[1], act[2]
                elif act[0] == "press":
                    press_now = True
            else:
                acts.append(("slash",))
                values.append(np.nan)
                new_dir = dir_cur
            # frame k + 1: the body moves by the key read in frame k
            if st[k + 1]:
                ls["x"] += dir_cur * step
                ls["lsd"] = dir_cur
            if jump_now is not None:
                ev = {"kind": "jump", "h": jump_now, "k": k, "q0": (p0 - k) % 6}
                ls["land"] = self.land_of(ev)
            ls["dir"] = dir_cur = new_dir
            if dir_cur:
                ls["facing"] = dir_cur
            k += 1
            ls["k"] = k
            j = k - ev["k"]
            if ev["kind"] != "ground" and ls["land"] is not None and j >= ls["land"]:
                ev = {"kind": "ground", "k": k}
                ls["land"] = None
            y, py = self.y_of(ev, j) if ev["kind"] != "ground" else self.y_of(ev, 0)
            xs[t], ys[t] = ls["x"], y
            masks[t] |= key_mask(dir_cur * face)
            if ev["kind"] == "jump" and 1 <= j <= ev["h"]:
                masks[t] |= kin.B_JUMP
            if press_now:
                presses.append(t)
                ls["lp"] = k
                if ev["kind"] != "ground":
                    ls["slash"] = {"P": k, "face": ls["facing"]}
                dslash.strike(masks, t)
            sl = ls["slash"]
            if sl is not None:
                i = k - sl["P"]
                if ev["kind"] == "ground" or i > ACTIVE[1]:
                    ls["slash"] = None
                elif i >= ACTIVE[0]:
                    lag = hm.lag[p0, 12 + (k - 12) % 6]
                    xr = ls["x"] - lag * ls["lsd"] * step
                    yr = y + py
                    poly = self.polys[(sl["face"], False)]
                    for b in tl_c.targets(k):
                        r = clip_band(poly, b[2] + self.pa - yr, b[3] + self.pa - yr)
                        if r is not None and b[0] - r[1] < xr < b[1] - r[0]:
                            contacts.append(t)
                            ev = {"kind": "bounce", "yc": y, "k": k, "q0": (p0 - k) % 6}
                            ls["land"] = self.land_of(ev)
                            ls["slash"] = None
                            break
            ls["ev"] = ev
            n = t + 1
        pl = MapPlan(masks, value if value is not None else -np.inf, first, presses, contacts, xs[:n], ys[:n], acts,
                     list(phases), k_start, (time.perf_counter() - t0) * 1e3)
        pl.rows, pl.plan_tl = self.rows, self.plan_tl
        pl.states = states
        pl.values = values
        pl.final = ls
        return pl

    def extend(self, prev: MapPlan, i: int, L: int, lam: float = LAMBDA, face: int = 1) -> MapPlan:
        """prev from its index i on (the hero followed it for i frames), extended by i frames to length L from its
        final loop state: what plan() from prev.states[i] returns (deterministic), at the cost of i decisions."""
        t0 = time.perf_counter()
        keep = (self.rows, self.plan_tl)
        self.rows, self.plan_tl = getattr(prev, "rows", None), getattr(prev, "plan_tl", None)
        try:
            tail = self.plan(0, 0.0, {"kind": "ground"}, 0, -100, prev.phases, i, lam=lam, face=face,
                             resume=prev.final)
        finally:
            self.rows, self.plan_tl = keep
        m = np.concatenate([prev.masks[i:], tail.masks])[:L]
        # a strike's down key starts one frame before its press: redo the presses near the seam
        pl = MapPlan(m, np.nan, None, [t - i for t in prev.presses if t >= i] + [t + len(prev.masks) - i
                                                                              for t in tail.presses],
                     [t - i for t in prev.contacts if t >= i] + [t + len(prev.masks) - i for t in tail.contacts],
                     np.concatenate([prev.xs[i:], tail.xs]), np.concatenate([prev.ys[i:], tail.ys]),
                     prev.acts[i:] + tail.acts, list(prev.phases), prev.k0 + i, 0.0)
        pl.rows, pl.plan_tl = getattr(prev, "rows", None), getattr(prev, "plan_tl", None)
        pl.states = prev.states[i:] + tail.states
        pl.values = prev.values[i:] + tail.values
        pl.final = tail.final
        pl.first = pl.acts[0] if pl.acts else None
        v0 = pl.values[0] if pl.values else np.nan
        pl.value = float(v0) if np.isfinite(v0) or (isinstance(v0, float) and np.isneginf(v0)) else prev.value
        pl.ms = (time.perf_counter() - t0) * 1e3
        return pl


_RT: dict = {}


def runtime(params, terrain) -> MapRuntime | None:
    """The process's map runtime (loaded once); None when the file is missing (the planner then runs without it)."""
    # review: keyed by the terrain and the hero too (the hero macros are rolled on them)
    import hashlib
    sig = hashlib.md5(b"".join(np.ascontiguousarray(getattr(terrain, nm, np.zeros(0)), np.float64).tobytes()
                               for nm in ("hseg", "vseg"))).hexdigest() if terrain is not None else "none"
    key = (MAP_TAG, sig, getattr(params, "crest", None), float(getattr(params, "run_speed", 0.0)))
    if key not in _RT:
        p = map_path()
        _RT[key] = MapRuntime(params, terrain, p) if p.exists() else None
    return _RT[key]


__all__ = ["MAP_ON", "MapRuntime", "MapPlan", "LevelSource", "load_levels", "save_levels", "decide_multi", "phases_of",
           "runtime", "map_path", "READY_W", "READY_RANGE_U", "DEV_TOL_U", "LAMBDA"]
