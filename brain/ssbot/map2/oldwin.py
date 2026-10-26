"""Task oldwin (the person's decision of 2026-10-25 ~17:00 PDT): keep the OLD planner (combat.forum_planner, the default
arm rnjb) as the controller and connect its special-move rows to the reflex's strike-window table (map2.reflex,
`clapper_windows_v2.npz`: 11 window types, 4,267,885 cells, live-press precision 0.999). SSBOT_FORUM_WINDOWS=1,
default off (off: the policy builds no WindowRows and the planner runs no line of this - bit-identical).

WHAT IT GIVES THE PLANNER (ForumPlanner._win_rows; this module only finds the rows - every check is the planner's):
  NOW rows      her exact state at the decision (state index P, after the keys in flight) looked up against each
                Clapper's move + frame at that index (its j advanced by P, a flying Clapper's x by its vx): the cell's
                macro is a row starting now.
  APPROACH rows the old planner's approach shapes (walk L / R / stand; a jump now held 3 / 8 / 14 / 20 frames with the
                drift L / R / N; in the air the drift L / R / N) rolled once from her state; at every frame j of each
                her state there (on the ground, or falling in normal control) keyed against the Clapper's move at
                index P + j (vectorized: the packed keys searched in the table's sorted keys) -> approach[:j] + the
                cell's macro (the 'walk to the cell and strike' row, now for every down-slash window type). The picks
                are re-keyed EXACTLY from a rollout truncated at P + j (rx.cell_of on the final state) - a pick whose
                exact cell is not the one found is dropped.
  CONT rows     the row chosen last tick, shifted by the frames elapsed, while she follows it (the keys in flight are
                its keys, her observed position is its lane's within CONT_TOL, the Clapper's move / frame as expected,
                its contact still ahead) - the reflex's Press as a planner row.
  Each row carries its strike's contact frame from the table (k_strike, the earliest over the outcomes) and its target.
  The planner judges them as the certain-hit rows of combat.dslash (G3): the bounce lane from the contact, stage 1 /
  the envelope / the score with the contact anchored on the target / the hit branch with the reaction from the bounce
  lane / the escape / the forced-risk order / the ranking; a contact past the horizon: the row within the horizon as
  any row, its tail to the contact + 14 against the support with the bounce, the strike credited (dslash's 'extra').

THE CLAWLINE TYPES (claw_slam0, claw_head2, cast_claw, evade_claw) are NOT rows: the old planner's hero model
(kinematics.rollout) has no Clawline (no hook, no pull, no control return), so no old check can judge a Clawline row.
They are counted (the cells open now, with the reflex's cheap gates: low HP, solo-only) for the measurement; their way
in is either the rnjb scripts (CLAWSTRIKE for the slam, CLAW_CHASE for the evade) or the reflex's own exact check on a
worker (map2.reflex, integration plan) - see HANDOFF 'Task oldwin'.

Only FULL cells (every sample point of the cell a window) are used.
"""
from __future__ import annotations

import math
import os
import time
from collections import Counter
from dataclasses import dataclass, replace

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import reflex as rx
from ssbot.map2 import strike as sk

ENV = "SSBOT_FORUM_WINDOWS"
REACH_U = 12.0                     # u: a Clapper this far from her (centre to centre) is not looked up
MAX_ROWS = int(os.environ.get("SSBOT_FORUM_WINDOWS_ROWS", "8") or 8)
PER_TYPE = 2                       # rows per (Clapper, window type) at most (the earliest contacts)
LONG_MAX = 24                      # frames: a contact at most this far past the planner's horizon
CONT_TOL = 0.12                    # u: her observed position vs the chosen row's lane (x and y) for its continuation
APPR_HOLDS = (3, 8, 14, 20)        # the jump's holds of the approach shapes (specials._templates')
ALL_DS = tuple(n for n, w in rx.WINDOWS.items() if w.generated and w.family == "ds")
# the down-slash types given as rows (SSBOT_FORUM_WINDOWS_TYPES: comma list, 'all': every one). Default: all but
# hop_slam0 - the w13 audit's exact check (map2.reflex.judge from her exact state, the reflex branch's own judge too)
# refuted 4 of 10 chosen hop_slam0 approach rows (a collision after the strike: hit@25 / 28 / 35 - the slam's body;
# the table's bulk v1 cells were judged with the default physics-step anchor, hop_slam0 the type most sensitive to it:
# HANDOFF 'Task reflex - stage 4' finding 2), every other type's chosen rows safe; rnjb's SLAM_PLAY plays this strike
_TY = os.environ.get("SSBOT_FORUM_WINDOWS_TYPES", "").strip()
DS_TYPES = ALL_DS if _TY == "all" else (tuple(t for t in _TY.split(",") if t in ALL_DS) if _TY else
                                        tuple(t for t in ALL_DS if t != "hop_slam0"))
CL_TYPES = tuple(n for n, w in rx.WINDOWS.items() if w.generated and w.family == "cl")
# SSBOT_FORUM_WINDOWS_MARGIN (default 1): a cell is used only when both its dx neighbours (the same key, dx +- one bin)
# are window cells too - her exact state off a cell's edge (the audit's refuted pogo_cast rows were approach rows);
# 0: every full cell
MARGIN = os.environ.get("SSBOT_FORUM_WINDOWS_MARGIN", "1").strip() != "0"
_DX1 = 1 << 25                     # dx's place in the packed key (the fields after it: 2 + 7 + 8 + 2 + 1 + 4 + 1 bits)
_J, _L, _R = km.B_JUMP, km.B_LEFT, km.B_RIGHT
AUDIT = os.environ.get("SSBOT_FORUM_WINDOWS_AUDIT", "0").strip() == "1"   # (offline: the chosen rows kept for the
#                                  reflex's exact check - WindowRows.log; the replay dumps it)


def enabled() -> bool:
    return os.environ.get(ENV, "0").strip() == "1"


@dataclass
class Cand:
    kind: str                      # "now" / "appr" / "cont"
    wt: str
    iid: int
    cmd: np.ndarray                # commands after the keys in flight (the approach's, then the macro's; the whole row)
    j: int                         # the macro's first key is the row's mask j (the approach's length)
    k0: int                        # the strike's contact, state index from the planner's origin (the earliest outcome)
    k1: int                        # ... the latest outcome's
    key: str                       # the cell (CellKey.short) / the continued row's
    label: str                     # the macro (Macro.label)
    n_macro: int                   # the macro's frames (latched unchanged required)
    tpl: str = ""                  # the approach shape
    dec: tuple | None = None       # (her state at the macro's decision, the Clappers there, the macro): the audit


def _pack_np(wt, st, j, band, dxq, cls, bbq, sub, vxc, adash, cvx, chg) -> np.ndarray:
    """reflex.pack_key over arrays (int64; the same fields, widths and offsets)."""
    v = np.asarray(wt, np.int64)
    for x, b in ((st, 5), (j, 9), (band, 4), (np.asarray(dxq) + 256, 9), (cls, 2), (bbq, 7),
                 (np.asarray(sub) + 128, 8), (np.asarray(vxc) + 1, 2), (adash, 1), (np.asarray(cvx) + 8, 4), (chg, 1)):
        v = (v << b) | (np.asarray(x, np.int64) & ((1 << b) - 1))
    return v


def _types_in(st: str | None, j0: int, j1: int, names: tuple) -> list:
    """The window types of `names` anchored at the state for some frame in j0 .. j1."""
    out = []
    for n in names:
        for (s, lo, hi) in rx.WINDOWS[n].anchor:
            if s == st and lo <= j1 and hi >= j0:
                out.append(n)
                break
    return out


def _advance(o, lead: int):
    """The Clapper's Obs `lead` frames on: its frame in the state, a flying body's x by its vx (the table's key)."""
    x = o.x + (o.vx * lead / 60.0 if o.st in rx.JUMPING else 0.0)
    return replace(o, j=int(o.j or 0) + int(lead), x=float(x))


def _templates(T: int, ground: bool) -> tuple:
    """The approach shapes (commands over T frames) and their names."""
    rows, names = [], []
    for k, m in (("R", _R), ("L", _L), ("N", 0)):
        x = np.full(T, m, np.int64)
        rows.append(x)
        names.append(("walk" if ground else "drift") + k)
    if ground:
        for h in APPR_HOLDS:
            for k, m in (("R", _R), ("L", _L), ("N", 0)):
                x = np.full(T, m, np.int64)
                x[:h] |= _J
                rows.append(x)
                names.append(f"jump{h}{k}")
    return np.stack(rows), names


class WindowRows:
    """The policy's window-row finder (one per bot instance): a map2 Clapper tracker fed every STATE (the table's
    key: the Clapper's Control state and its frame in it, its facing, its x / vx, the jump's charge) and the table."""

    def __init__(self, table: "rx.Table | None" = None):
        self.table = table if table is not None else rx.Table.load()
        if self.table._arr is None:
            raise ValueError("WindowRows needs a loaded table (Table.load)")
        self.keys = self.table._arr[0]
        self.trk = cm.Tracker()
        self._obs_k = None
        self._obs: list = []
        self._tpl: dict = {}
        self.prev = None           # the chosen row's continuation state (note_chosen)
        self.audit = Counter()
        self.log: list = []        # AUDIT: the chosen rows (note_chosen) for the offline exact check

    # ---- the tracker ----
    def reset(self) -> None:
        self.trk = cm.Tracker()
        self._obs_k, self._obs, self.prev = None, [], None

    def feed(self, raw: dict, fo: int) -> None:
        self.trk.feed(raw, fo)

    def obs(self) -> list:
        if self._obs_k != self.trk.k:
            self._obs = [o for o in self.trk.obs() if o.st is not None and o.j is not None]
            self._obs_k = self.trk.k
        return self._obs

    # ---- the lookups ----
    def _has(self, pk: np.ndarray) -> np.ndarray:
        """Packed keys present in the table (any cell: full or partial)."""
        pk = np.asarray(pk, np.int64)
        ii = np.minimum(np.searchsorted(self.keys, pk), len(self.keys) - 1)
        return self.keys[ii] == pk

    def _entry(self, pk: int):
        e = self.table._entry(int(pk))
        return e if e.conf[0] == e.conf[1] else None

    def _now(self, S: np.ndarray, live: list, P: int, cands: list, info: dict) -> None:
        """NOW rows: her exact state S at the decision (index P) in each Clapper's cells; the Clawline cells counted."""
        n_alive = len(self.obs())
        for o in live:
            on = _advance(o, P)
            for wt in rx.windows_for(on.st, on.j):
                wn = wt.name
                key = rx.cell_of(S, on, wt)
                if key is None:
                    continue
                pk = rx.pack_key(key)
                i = int(np.searchsorted(self.keys, pk))
                if i >= len(self.keys) or int(self.keys[i]) != pk:
                    continue
                e = self.table._entry(pk)
                full = e.conf[0] == e.conf[1]
                if wt.family == "cl":
                    gate = ("solo" if (wn in rx.SOLO_ONLY and n_alive > 1) else
                            "lowhp" if o.hp <= rx.LOW_HP_CL else "ok")
                    info["cl"][f"{wn}:{gate}{'' if full else ':part'}"] += 1
                    continue
                if wn not in DS_TYPES:
                    info["off"][wn] += 1                      # a type not given as rows (SSBOT_FORUM_WINDOWS_TYPES)
                    continue
                if MARGIN and not self._has(np.array([pk + _DX1, pk - _DX1], np.int64)).all():
                    info["edge"][wn] += 1                     # an edge cell: a dx neighbour is no window
                    continue
                if not full:
                    info["part"][wn] += 1
                    continue
                if float(S[km.ATK_CD]) > (e.macro.t - 1) / 60.0 + 1e-6:
                    info["cd"][wn] += 1
                    continue
                d = 1 if on.x >= float(S[km.PX]) else -1
                raw = rx.render(e.macro, d)
                ks = e.k_strike or (e.macro.t + 3,)
                cands.append(Cand("now", wn, int(o.iid), raw.pre.copy(), 0, P + int(ks[0]), P + int(ks[-1]),
                                  key.short(), e.macro.label(), len(raw.pre),
                                  dec=(S.copy(), [_advance(x, P) for x in self.obs()], e.macro) if AUDIT else None))

    def _approach(self, start, lat_p, ro, lat_full, M, names, live, P: int, T: int, cands: list, info: dict) -> None:
        """APPROACH rows: the shapes' states at every frame j keyed (vectorized) against each Clapper's cells there."""
        phys, vel, mode, flags = ro.phys, ro.vel, ro.mode, ro.flags
        n, T1 = mode.shape
        js = np.arange(1, T - 2)
        idx = P + js                                                  # state indices of the cut frames
        x = phys[:, idx, 0]
        bb = phys[:, idx, 1] - sk.FOOT - sk.FLOOR
        vy = vel[:, idx, 1]
        md = mode[:, idx]
        fl = flags[:, idx]
        normal = (md == km.M_NORMAL) & ((fl & km.F_ATTACKING) == 0)
        gnd = normal & ((fl & km.F_GROUND) != 0)

        prevj = (lat_full[:, idx - 1] & _J) != 0
        air = normal & ~gnd & (vy <= 0.0) & ~(prevj & (vy > 0))
        cd0 = float(np.asarray(start).reshape(km.K, -1)[km.ATK_CD, 0])
        ft = 1.0 / 60.0
        cd = np.maximum(cd0 - idx * ft, 0.0)                          # (the shapes press no attack)
        st_ids, cls_ids = rx._ST_IDS, rx._CLS_IDS
        hits = []
        for o in live:
            j_lo, j_hi = int(o.j) + P + 1, int(o.j) + P + T - 3
            for wn in _types_in(o.st, j_lo, j_hi, DS_TYPES):
                wt = rx.WINDOWS[wn]
                jj = int(o.j) + P + js                                # the Clapper's frame at each cut
                ok_j = np.array([rx.in_states(o.st, int(v), wt.anchor) for v in jj])
                if not ok_j.any():
                    continue
                xo = o.x + (o.vx * (P + js) / 60.0 if o.st in rx.JUMPING else 0.0 * js)
                face = 1 if o.face >= 0 else -1
                fd = np.where(face > 0, cm.WALL_R - xo, xo - cm.WALL_L)
                band = np.clip(np.searchsorted(rx.WALL_BANDS, fd, side="right") - 1, 0, len(rx.WALL_BANDS) - 2)
                cvx, chg = rx.clapper_extra(o)
                dx = (x - xo[None, :]) * face
                for cls, sel in (("G", gnd), ("A", air)):
                    if cls not in wt.classes:
                        continue
                    m_ = sel & ok_j[None, :]
                    if not m_.any():
                        continue
                    q = rx.dx_q(cls)
                    dxq = np.floor(dx / q).astype(np.int64)
                    if cls == "G":
                        bbq = np.zeros_like(dxq)
                        sub = np.zeros_like(dxq)
                        ad = 0
                    else:
                        bbq = np.floor(bb / rx.BB_Q).astype(np.int64)
                        sub = np.floor(vy / rx.VY_Q).astype(np.int64)
                        ad = 1
                    pk = _pack_np(rx._WT_IDS[wn], st_ids[o.st], jj[None, :], band[None, :], dxq, cls_ids[cls], bbq,
                                  sub, 0, ad, cvx, chg)
                    ii = np.searchsorted(self.keys, pk)
                    ii = np.minimum(ii, len(self.keys) - 1)
                    found = m_ & self._has(pk)
                    if MARGIN:
                        found &= self._has(pk + _DX1) & self._has(pk - _DX1)
                    for r_, c_ in zip(*np.nonzero(found)):
                        hits.append((o, wn, int(r_), int(js[c_]), int(pk[r_, c_]), float(cd[c_])))
        info["appr_found"] += len(hits)
        if not hits:
            return
        # the earliest strike per (Clapper, type, shape): decode, the attack-ready gate, then the exact re-key
        got = {}
        for (o, wn, r_, j, pk, cdj) in hits:
            e = self._entry(pk)
            if e is None:
                info["part"][wn] += 1
                continue
            if cdj > (e.macro.t - 1) / 60.0 + 1e-6:
                continue
            ks = e.k_strike or (e.macro.t + 3,)
            k0 = P + j + int(ks[0])
            kk = (int(o.iid), wn, r_)
            if kk not in got or k0 < got[kk][0]:
                got[kk] = (k0, o, wn, r_, j, pk, e)
        picks = sorted(got.values(), key=lambda g: g[0])
        per = Counter()
        sel = []
        for g in picks:
            if per[(g[1].iid, g[2])] >= PER_TYPE:
                continue
            per[(g[1].iid, g[2])] += 1
            sel.append(g)
            if len(sel) >= MAX_ROWS:
                break
        # the exact re-key: her state from a rollout truncated at P + j (one rollout per cut length)
        byj: dict = {}
        for g in sel:
            byj.setdefault(g[4], []).append(g)
        for j, gs in byj.items():
            rows_ = np.stack([np.concatenate([lat_p, lat_full[g[3], P:P + j]]) for g in gs])
            rt = km.rollout(start, rows_, self._params, self._terrain, threads=1)
            for m_, g in enumerate(gs):
                k0, o, wn, r_, _, pk, e = g
                S = rt.final[:, m_]
                on = _advance(o, P + j)
                key = rx.cell_of(S, on, rx.WINDOWS[wn])
                if key is None or rx.pack_key(key) != pk:
                    info["appr_rekey_miss"] += 1
                    continue
                if float(S[km.ATK_CD]) > (e.macro.t - 1) / 60.0 + 1e-6:
                    continue
                d = 1 if on.x >= float(S[km.PX]) else -1
                raw = rx.render(e.macro, d)
                ks = e.k_strike or (e.macro.t + 3,)
                cmd = np.concatenate([M[r_, :j], raw.pre])
                cands.append(Cand("appr", wn, int(o.iid), cmd, j, P + j + int(ks[0]), P + j + int(ks[-1]), key.short(),
                                  e.macro.label(), len(raw.pre), names[r_],
                                  dec=(np.asarray(S).copy(), [_advance(x, P + j) for x in self.obs()], e.macro)
                                  if AUDIT else None))

    def _cont(self, start, prefix: np.ndarray, f: int, fo: int, P: int, live: list, cands: list, info: dict) -> None:
        """CONT: last tick's chosen window row, shifted by the frames elapsed, while she follows it."""
        pv, self.prev = self.prev, None
        if pv is None:
            return
        d = f - pv["f"]
        k0 = pv["fo"] + pv["k0"] - fo
        if d <= 0 or d >= len(pv["cmd"]) or k0 <= P:
            info["cont_end"] += 1
            return
        sent = pv["cmd"][max(d - P, 0):d]
        if len(sent) and not np.array_equal(np.asarray(prefix[-len(sent):], np.int64), sent):
            info["cont_keys"] += 1
            return
        li = fo - pv["fo"]
        st0 = np.asarray(start).reshape(km.K, -1)[:, 0]
        if not (0 <= li < len(pv["lane"])) or abs(float(st0[km.PX]) - pv["lane"][li, 0]) > CONT_TOL or \
                abs(float(st0[km.PY]) - pv["lane"][li, 1]) > CONT_TOL:
            info["cont_dev"] += 1
            return
        o = next((o for o in live if int(o.iid) == pv["iid"]), None)
        if o is None or o.st != pv["st"] or int(o.j) != pv["oj"] + (fo - pv["fo"]):
            info["cont_clapper"] += 1
            return
        cands.append(Cand("cont", pv["wt"], pv["iid"], pv["cmd"][d:].copy(), max(pv["j"] - d, 0), k0,
                          pv["fo"] + pv["k1"] - fo, pv["key"], pv["label"],
                          max(pv["n_macro"] - max(d - pv["j"], 0), 0), pv["tpl"]))
        info["cont"] += 1

    def note_chosen(self, c: "Cand | None", f: int, fo: int, lane_phys: np.ndarray | None) -> None:
        """The planner's chosen row this tick (None: not a window row): its continuation next tick."""
        if AUDIT and c is not None and c.dec is not None:
            self.log.append({"f": f, "fo": fo, "kind": c.kind, "wt": c.wt, "iid": c.iid, "key": c.key, "label": c.label,
                             "k0": c.k0, "j": c.j, "P": f + 1 - fo, "S": c.dec[0], "obs": c.dec[1], "macro": c.dec[2],
                             "mems": self.trk.mems()})
        if c is None or lane_phys is None:
            self.prev = None
            return
        o = next((o for o in self.obs() if int(o.iid) == c.iid), None)
        if o is None:
            self.prev = None
            return
        self.prev = {"f": f, "fo": fo, "k0": c.k0, "k1": c.k1, "cmd": np.asarray(c.cmd, np.int64), "iid": c.iid,
                     "wt": c.wt, "st": o.st, "oj": int(o.j), "key": c.key, "label": c.label, "j": c.j,
                     "n_macro": c.n_macro, "tpl": c.tpl, "lane": np.asarray(lane_phys)}

    def warm(self, S, params, terrain, threads: int, hold_filter, hold) -> float:
        """The numba paths a window tick uses (the shapes' rollout at the planner's threads, the one-row rollouts,
        the hold filter on the shapes, a row with a bounce event) and one entry decoded - else compiled inside the first
        window tick (1.6 s in the smoke)."""
        t0 = time.perf_counter()
        for T in (36,):
            for g in (True, False):
                M, _ = _templates(T, g)
                pre = np.zeros((len(M), 2), np.int64)
                lat, _ = hold_filter(np.concatenate([pre, M], axis=1), hold)
                km.rollout(S, lat, params, terrain, threads=int(threads))
                km.rollout(S, lat[:2, :7], params, terrain, threads=1)
                km.rollout(S, lat[:1, :2], params, terrain, threads=1)
                ev = np.zeros((2, lat.shape[1]), np.int64)
                ev[:, 12] = km.EV_POGO
                km.rollout(S, lat[:2], params, terrain, events=ev, threads=int(threads))
        if len(self.keys):
            self.table._entry(int(self.keys[len(self.keys) // 2]))
        return time.perf_counter() - t0

    # ---- the tick ----
    def rows(self, start, prefix, hold, T: int, params, terrain, hold_filter, f: int, fo: int, threads: int,
             posture: str) -> tuple:
        """(candidates, info) for this tick; ([], info) when no Clapper within reach has a window anchored ahead."""
        t0 = time.perf_counter()
        info = {"cl": Counter(), "part": Counter(), "cd": Counter(), "off": Counter(), "edge": Counter(),
                "appr_found": 0,
                "appr_rekey_miss": 0,
                "cont": 0, "cont_end": 0, "cont_keys": 0, "cont_dev": 0, "cont_clapper": 0}
        P = len(prefix)
        st0 = np.asarray(start).reshape(km.K, -1)[:, 0]
        hx = float(st0[km.PX])
        live = [o for o in self.obs() if abs(o.x - hx) <= REACH_U and
                _types_in(o.st, int(o.j) + P, int(o.j) + P + T, DS_TYPES + CL_TYPES)]
        cands: list = []
        self._params, self._terrain, self._threads = params, terrain, int(threads)
        if self.prev is not None:
            self._cont(start, np.asarray(prefix, np.int64), f, fo, P, live, cands, info)
        if not live:
            info["ms"] = (time.perf_counter() - t0) * 1e3
            return cands, info
        self.audit["live_ticks"] += 1
        pre = np.asarray(prefix, np.int64)
        if P:
            lat_p = hold_filter(pre[None], hold)[0][0]
            S = km.rollout(start, lat_p[None], params, terrain, threads=1).final[:, 0]
        else:
            lat_p = np.zeros(0, np.int64)
            S = st0
        self._now(S, live, P, cands, info)
        if posture in ("ground", "air") and any(_types_in(o.st, int(o.j) + P, int(o.j) + P + T, DS_TYPES)
                                                for o in live):
            key = (T, posture == "ground")
            if key not in self._tpl:
                self._tpl[key] = _templates(T, posture == "ground")
            M, names = self._tpl[key]
            lat, _ = hold_filter(np.concatenate([np.broadcast_to(pre, (len(M), P)), M], axis=1), hold)
            ro = km.rollout(start, lat, params, terrain, threads=self._threads)

            self._approach(start, lat_p, ro, lat, M, names, live, P, T, cands, info)
        info["ms"] = (time.perf_counter() - t0) * 1e3
        return cands, info


__all__ = ["ENV", "enabled", "WindowRows", "Cand", "DS_TYPES", "CL_TYPES", "MAX_ROWS", "LONG_MAX"]
