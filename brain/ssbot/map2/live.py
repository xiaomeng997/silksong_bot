"""Map v2 stage M4c: THE SEARCH PLAYED LIVE - SSBOT_FORUM_MAP2 (default off; HANDOFF 'Task map2 - stage M4' / 'M4c',
forum.md 97). The policy (ForumPlannerPolicy) imports this module only when the switch is on; with it off nothing here
runs and the bot's decisions stay bit-identical. With it on SSBOT_FORUM_HERO2 must be on too (the search's hero model).

THE PARTS
- WORKERS (worker_main): their own processes (parts=N, default 2: M4b's split search, Searcher.part = (i, N)), boosted
  like the live bot's worker (High, the P-cores, EcoQoS off; never Idle). A reader thread keeps the NEWEST snapshot the
  bot sent; the search loop takes it whenever it is free (the background refresh) and runs Searcher.decide from it with
  the snapshot's PREFIX - the keys on their way to the game and the BRIDGE the bot expects to play while the search
  runs (the plan in control's own keys, or the fallback planner's plan), passed through the oracle's hold filter
  (kinematics.hold_filter: the search's masks are LATCHED masks) - and the plan in control re-anchored as the kept
  plan (the hysteresis). A safe plan that is not the noop goes back as a LivePlan: anchored at the snapshot's frame,
  per safe outcome its command timeline (the Clawline key with the direction for CLAW_PRESS_F frames from its press, as
  the M0 / M4a probes pressed it; nothing in its block), its planned positions, the Clappers' records (TickCheck's),
  its danger geometry and the strike targets' robust boxes over its committed part. A search is cut (abort) when the
  bot reports her hit or another plan in control (its prefix is gone).
- THE CONTROLLER (Map2Controller, on the bot's thread): ForumPlannerPolicy.act calls pre() before the planner (the
  keys map2 sends this tick, or None: the fallback's) and post() after the keys are chosen (the snapshot to the
  workers, the per-tick log). Per tick:
  1. COMMIT: a received plan is RE-ANCHORED to now (its frames already played dropped) and committed only after THE
     EXACT HERO2 SIMULATION CHECK FROM THE CURRENT STATE (commit_check): her observed kin state now, the keys in
     flight and the plan's commands through the hold filter, simulated with the strike module (simulate) in every
     outcome consistent with the Clappers seen now; each such outcome must stay within tol_commit of its planned path
     and touch none of its danger (its geometry, the margins on) up to the end of its committed part. A failed check
     drops the plan (logged with the reason); a plan older than `stale` frames is dropped unchecked.
  2. EXECUTE: the committed plan's command for the frame being chosen (f + 2), taken from the most probable outcome
     consistent with the observation (TickCheck's rule: every Clapper's state, its frame in it within tol_j, its x
     within tol_x, its facing; her position within tol_hero of the path re-simulated at the commit) whose committed
     part reaches that frame - so the contingent continuation after a hook and the hook variant's control are picked
     from what she sees. No consistent outcome (the check failed) or none reaching the frame (the committed part's
     end) -> the plan is dropped and the FALLBACK (the w7 / w13 default planner and its scripts) has the keys again;
     her freeze (hit-stop), her own hit and the supervisor's keys drop it too.
  3. HANDOVER: while map2 has the keys the scripts are not stepped (their runs are aborted on the tick it takes them);
     the planner keeps planning every tick from the keys actually sent (its prefix and the hold filter's state), so
     when map2 drops the plan the fallback continues from the real key state - held keys held or released as its
     plan wants, a press in flight not lost, no press repeated (the filter's edges). map2 takes the keys back when a
     new plan passes its commit check.
  4. TRIGGERS (branch points) in the snapshot: a Clapper's new state (its move choice revealed), a hit (hers: the
     search is cut; on a Clapper), the plan in control near its committed end (end_lead) or dropped.
  5. LOG (map2_i<N>.jsonl beside the decisions, one row per tick): who controls and why, the plan id, its age and the
     search's latency, the planned vs observed hero position and Clappers (state, frame in it, x) of the best
     consistent outcome, the commit checks with their reasons, the worker messages.

Frames: STATE frames (the oracle applies a tick's keys at f + 2); a plan's frame 0 is its snapshot's observation frame
(its anchor), its command index k applies to frame anchor + k. u: world units, her transform (kin pos).
"""
from __future__ import annotations

import json
import math
import os
import queue
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np
from numba import njit

from ssbot.knowledge import kinematics as km
from ssbot.map2 import brnum
from ssbot.map2 import clapper as cm
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

MAP2_ENV = "SSBOT_FORUM_MAP2"
SET_ENV = "SSBOT_FORUM_MAP2_SET"
M_CLAW = 1 << 4                    # the Clawline button (ssbot.ipc.framing BUTTONS order; combat.claw_strike.M_CLAW)
M_DS = km.B_DOWN | km.B_ATTACK
CLAW_PRESS_F = 3                   # the Clawline key and the direction held this many frames from P (the probes')
DS_WIN = sk.DS_ACTIVE[1] + 1       # a slash's contact can still come this many frames after its press
CLAW_BLOCK_F = 36                  # a Clawline pressed this recently: she may still be in its block (control P + 34)
CTRL_SETTLE = 2                    # frames after a Clawline's control still treated as its block (the forced bounce)
VARIANTS = {v.name: v for v in sk.HOOK_VARIANTS}


def enabled() -> bool:
    return os.environ.get(MAP2_ENV, "0").strip() == "1"


@dataclass
class LiveCfg:
    parts: int = 2                 # search worker processes per game instance (M4b's split search)
    prio: str = "high"             # the workers' priority: high (the live bot's rule) / as (as started: tests)
    cap_fb: float = 0.25           # the search's cap (s) while the fallback has the keys
    cap_ch: float = 0.6            # ... while map2 has them (the chained search, anchored after its bridge)
    cap_min: float = 0.12
    fb_lead: int = 16              # the bridge's frames from the fallback planner's own plan
    ch_lead: int = 40              # the bridge's frames from the plan in control
    sc_lead: int = 8               # ... while a script of the fallback has the keys: its key now held (a guess)
    min_frames: int = 4            # a plan this short past its prefix is not sent
    tol_hero: float = 0.2          # TickCheck's tolerances (M4b's guesses; calibrate live)
    tol_x: float = 0.35
    tol_j: int = 1
    tol_commit: float = 0.2        # the commit re-simulation against the planned path (u)
    tol_reanchor: float = 0.5      # ... when the plan in control is re-anchored after her position left its path (the
    #                                Clappers still consistent): the collision check stays exact
    stale: int = 45                # a received plan older than this (frames since its anchor) is dropped
    end_lead: int = 20             # the 'end' trigger: the plan in control has this few committed frames left
    commits_per_tick: int = 2      # commit checks per tick at most (the rest wait)
    mem_gb: float = 6.0            # a worker above this RSS exits after its search (the controller restarts it)
    ready_s: float = 240.0         # the workers' start-up wait
    replay: bool = False           # an offline replay: her position is the recording's, not her keys' result - the
    #                                hero tolerances are logged, not enforced
    log: bool = True

    @classmethod
    def from_env(cls, **kw) -> "LiveCfg":
        """SSBOT_FORUM_MAP2_SET="parts=1,cap_fb=0.3,..." overrides the defaults."""
        d: dict = {}
        types = {f.name: f.type for f in fields(cls)}
        for item in filter(None, (x.strip() for x in os.environ.get(SET_ENV, "").split(","))):
            k, _, v = item.partition("=")
            k = k.strip()
            if k not in types:
                raise ValueError(f"{SET_ENV}: unknown key {k!r} ({sorted(types)})")
            t = str(types[k])
            d[k] = (v.strip() in ("1", "true", "True")) if t == "bool" else int(v) if t == "int" else \
                float(v) if t == "float" else v.strip()
        d.update(kw)
        return cls(**d)

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


# ---- the oracle's hold filter, one lane (kinematics.hold_filter, compiled) ------------------------------------------

@njit(cache=True)
def _hf1(cmds, lat0, des0, pen0, age0, min_press, min_release, max_pending, age_long):
    T = cmds.shape[0]
    nb = lat0.shape[0]
    lat = lat0.copy()
    des = des0.copy()
    pen = pen0.copy()
    age = age0.copy()
    out = np.zeros(T, np.int64)
    nxt = np.zeros(nb, np.bool_)
    prs = np.zeros(nb, np.bool_)
    for t in range(T):
        m = cmds[t]
        for b in range(nb):
            w = ((m >> b) & 1) == 1
            if w != des[b]:
                pen[b] += 1
            des[b] = w
            if pen[b] > max_pending:
                pen[b] -= 2
            has = pen[b] > 0
            r = has and lat[b] and age[b] >= min_press
            p = has and (not lat[b]) and age[b] >= min_release
            nxt[b] = lat[b]
            if r:
                nxt[b] = False
            if p:
                nxt[b] = True
            prs[b] = p
            if r or p:
                pen[b] -= 1
        both = nxt[20] and nxt[21]
        for b in (20, 21):
            if both and prs[b]:
                nxt[b] = False
                pen[b] += 1
                if not des[b]:
                    pen[b] = 0
        v = 0
        for b in range(nb):
            if nxt[b] != lat[b]:
                age[b] = 1
            else:
                age[b] = min(age[b] + 1, age_long)
            lat[b] = nxt[b]
            if lat[b]:
                v |= 1 << b
        out[t] = v
    return out, lat, des, pen, age


def hold_filter1(cmds, hold: tuple) -> np.ndarray:
    """kinematics.hold_filter for one lane from a hold tuple (latched, desired, pending, age: [22] each): the latched
    masks of the commands."""
    c = np.ascontiguousarray(np.asarray(cmds, np.int64).reshape(-1))
    if not len(c):
        return np.zeros(0, np.int64)
    lat, des, pen, age = hold
    out, *_ = _hf1(c, np.asarray(lat, np.bool_), np.asarray(des, np.bool_), np.asarray(pen, np.int64),
                   np.asarray(age, np.int64), 2, 2, 3, km._AGE_LONG)
    return out


def hold_run(cmds, hold: tuple) -> tuple:
    """(latched masks, the filter's state after them) for one lane's commands from a hold tuple."""
    c = np.ascontiguousarray(np.asarray(cmds, np.int64).reshape(-1))
    lat, des, pen, age = hold
    if not len(c):
        return np.zeros(0, np.int64), hold
    out, l2, d2, p2, a2 = _hf1(c, np.asarray(lat, np.bool_), np.asarray(des, np.bool_), np.asarray(pen, np.int64),
                               np.asarray(age, np.int64), 2, 2, 3, km._AGE_LONG)
    return out, (l2, d2, p2, a2)


def _press_at(lat: np.ndarray, i: int, prev: int, look: int = 2) -> int:
    """The frame (index) of the latched down slash press for one commanded at i: the first rising attack with down
    in i .. i + look; -1 when the filter takes it away."""
    for j in range(i, min(i + look + 1, len(lat))):
        m = int(lat[j])
        pm = int(lat[j - 1]) if j > 0 else int(prev)
        if _rising(m, pm, km.B_ATTACK):
            return j if (m & M_DS) == M_DS else -1
    return -1


class HoldRealizer:
    """A plan as the oracle's hold filter latches it (Searcher.realizer in the live worker): the search's masks
    (M1's witness keys, kin_jit's latched masks) may press or release a key for one frame, which the filter cannot
    latch (a press lasts >= 2 frames, a release too): every plan is turned into what the game will receive before it
    is evaluated. The first n_pre masks (the prefix: already the latched result of the bot's commands) are kept; the
    rest of the first segment goes through the filter as commands from its state after the prefix; a segment after a
    Clawline (and its per-variant / per-reaction alternatives) from the filter's state after the press (the key for
    CLAW_PRESS_F frames) and a block of no key; a down slash press moves to its latched press frame (dropped when the
    filter takes the press away: the strike is then not in the plan)."""

    def __init__(self, n_pre: int, hold_after: tuple):
        self.n_pre, self.hold = int(n_pre), hold_after
        self.n_moved = 0
        self.n_dropped = 0

    def _seg(self, s, h: tuple, base: int) -> tuple:
        m = np.asarray(s.masks, np.int64)
        if base > 0:
            head = m[:base]
            tail, h2 = hold_run(m[base:], h)
            lat = np.concatenate([head, tail]).astype(np.int64)
            prev = int(head[-1]) if len(head) else 0
        else:
            lat, h2 = hold_run(m, h)
            prev = 0
        dsl = []
        for (i, iid) in s.dsl:
            if i < base:
                dsl.append((i, iid))
                continue
            j = _press_at(lat, int(i), prev)
            if j < 0:
                self.n_dropped += 1
                continue
            if j != i:
                self.n_moved += 1
            dsl.append((j, iid))
        if s.claw is not None:
            dk = km.B_RIGHT if s.claw[0] > 0 else km.B_LEFT
            _, h2 = hold_run(np.array([M_CLAW | dk] * CLAW_PRESS_F + [0] * 22, np.int64), h2)
        return lat, dsl, h2

    def _chain(self, segs: list, h: tuple, base0: int) -> list:
        out = []
        for si, s in enumerate(segs):
            lat, dsl, h2 = self._seg(s, h, base0 if si == 0 else 0)
            var_alt = None if s.var_alt is None else {k: self._chain([v], h, 0)[0] for k, v in s.var_alt.items()}
            out_alt = None if s.out_alt is None else {k: self._chain(v, h, 0) for k, v in s.out_alt.items()}
            out.append(ms.Seg(lat, dsl, s.claw, s.tag, var_alt, out_alt))
            h = h2
        return out

    def __call__(self, plan):
        return ms.Plan(self._chain(list(plan.segs), self.hold, self.n_pre), plan.origin, plan.note)


def hold_tuple(hold: km.HoldState) -> tuple:
    return (hold.latched[0].copy(), hold.desired[0].copy(), hold.pending[0].copy(), hold.age[0].copy())


def _rising(m: int, pm: int, bit: int) -> bool:
    return bool(m & bit) and not bool(pm & bit)


# ---- a plan as the bot executes it --------------------------------------------------------------------------------

def outcome_cmds(tr) -> np.ndarray:
    """The outcome's COMMANDS per frame 0 .. tr.end (index 0 unused): its played segments' masks at their frames, a
    Clawline's key with the direction for CLAW_PRESS_F frames from its press P (the segment's last mask frame), no key
    in the block until the next segment (its control)."""
    end = int(tr.end)
    c = np.zeros(end + 1, np.int64)
    for seg, k0 in zip(getattr(tr, "segs", ()), tr.seg_start):
        m = np.asarray(seg.masks, np.int64)
        hi = min(int(k0) + len(m), end)
        if hi > k0:
            c[int(k0) + 1:hi + 1] = m[:hi - int(k0)]
        if seg.claw is not None:
            P = int(k0) + len(m)
            dk = km.B_RIGHT if seg.claw[0] > 0 else km.B_LEFT
            for j in range(CLAW_PRESS_F):
                if P + j <= end:
                    c[P + j] = M_CLAW | dk
    return c


class OutData:
    """One safe outcome of a sent plan (frames from the anchor): p, kc (its committed part's end: the reveal + lag of a
    later collision, else its end), end, cmds (outcome_cmds), pos [kc + 1, 2] her planned transform, recs / sids
    (TickCheck's records of the Clappers to kc), segs [(start frame, masks, dsl, claw)] as played, presses [(frame,
    iid)], variant, boxes {iid: robust body rows} (the strikes' targets), geo (off, BX, IIDB, coff, CO to kc), rare
    {k: grown shapes} (the hammers), rare_k, label."""
    __slots__ = ("p", "kc", "end", "cmds", "pos", "recs", "vrecs", "sids", "segs", "presses", "variant", "boxes", "geo",
                 "rare", "rare_k", "label", "contacts", "blocks")

    def in_block(self, n: int) -> bool:
        """Frame n inside a Clawline's block (its press .. control + CTRL_SETTLE: no control, the forced bounce's
        first frames) - her position is the pull's, not her keys'."""
        return any(P < n <= c + CTRL_SETTLE for (P, c) in self.blocks)


def _geo_cut(br, kc: int, margins: bool) -> tuple:
    g = ms.geo(br, margins)
    n = min(kc + 2, len(g.off))
    off = g.off[:n].copy()
    BX, IIDB = g.BX[:int(off[-1])].copy(), g.IIDB[:int(off[-1])].copy()
    nc = min(kc + 2, len(g.coff))
    coff = g.coff[:nc].copy()
    CO = g.CO[:int(coff[-1])].copy() if len(coff) else np.zeros((0, 3))
    rare = {}
    for k in g.rare_k:
        if int(k) <= kc:
            rare[int(k)] = list(g.rare_grown(br, int(k), margins))
    return (off, BX, IIDB, coff, CO), rare


def build_outs(ev, margins: bool = True) -> list:
    outs = []
    gcache: dict = {}
    sid_of: dict = {}
    for o in ev.outcomes:
        if not o.safe:
            continue
        tr = o.tr
        kc = int(getattr(o, "k_end", tr.end))
        d = OutData()
        d.p, d.kc, d.end = float(o.p), kc, int(tr.end)
        d.cmds = outcome_cmds(tr)
        d.pos = np.asarray(tr.pos[:kc + 1], float).copy()
        arr, tb = brnum.barr(o.branch)
        vrecs = {}
        for iid, a in arr.items():
            a = a[(a[:, 0] >= 0) & (a[:, 0] <= kc)]
            a = a[np.argsort(a[:, 0], kind="stable")]
            vrecs[iid] = (a[:, 0].astype(np.int64), a[:, 3].astype(np.int64), a[:, 4], a[:, 5], a[:, 7])
        d.vrecs = vrecs
        # the matching uses the branch the timing view was drawn from: a record (state, frame in it, x, facing) is
        # seen at any frame k + a .. k + b of its spread (an observed timing between the two views' extremes)
        arr0, tb0 = brnum.barr(getattr(o.branch, "_base", o.branch))
        recs = {}
        for iid, a in arr0.items():
            lo, hi = a[:, 0] + a[:, 1], a[:, 0] + a[:, 2]
            a, lo, hi = a[(hi >= 0) & (lo <= kc)], lo[(hi >= 0) & (lo <= kc)], hi[(hi >= 0) & (lo <= kc)]
            o_ = np.argsort(lo, kind="stable")
            recs[iid] = (lo[o_].astype(np.int64), hi[o_].astype(np.int64), a[o_, 3].astype(np.int64), a[o_, 4],
                         a[o_, 5], a[o_, 7])
        d.recs = recs
        if tb0 is not tb:
            assert dict(tb0.sid) == dict(tb.sid)
        d.sids = sid_of.setdefault(id(tb), dict(tb.sid))
        d.segs = [(int(k0), np.asarray(s.masks, np.int64).copy(), list(s.dsl), s.claw)
                  for s, k0 in zip(getattr(tr, "segs", ()), tr.seg_start)]
        d.presses = [(int(k0) + 1 + int(i), int(iid)) for (k0, _, dsl, _) in d.segs for (i, iid) in dsl]
        d.variant = tr.variant or sk.HOOK_VARIANTS[0].name
        tgt = {iid for (_, iid) in d.presses} | {int(c[1]) for (_, _, _, c) in d.segs if c is not None}
        d.boxes = {iid: np.asarray(sk.robust_boxes(o.branch, iid, None), float) for iid in sorted(tgt)}
        key = (id(o.branch), kc)
        if key not in gcache:
            gcache[key] = _geo_cut(o.branch, kc, margins)
        d.geo, d.rare = gcache[key]
        d.rare_k = np.array(sorted(d.rare), np.int64)
        d.label = o.branch.label() if hasattr(o.branch, "label") else ""
        d.contacts = [(int(k), int(i), str(kd)) for (k, i, kd) in tr.contacts]
        d.blocks = []
        for si, (k0, m, _, c) in enumerate(d.segs):
            if c is not None:
                P = k0 + len(m)
                d.blocks.append((P, d.segs[si + 1][0] if si + 1 < len(d.segs) else P + 34))
        outs.append(d)
    return outs


class LivePlan:
    """A plan the worker sends (frames from the anchor t_a = its snapshot's observation frame)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def consistent(self, n: int, her_xy, obs: list, cfg: LiveCfg, idx=None, hero: bool = True,
                   pos_over: dict | None = None) -> tuple:
        """(indices of the outcomes consistent with the observation at frame n, outcomes failing on her position,
        outcomes failing on the Clappers) - TickCheck.check's rule per outcome."""
        out, bad_h, bad_c = [], 0, 0
        hx, hy = float(her_xy[0]), float(her_xy[1])
        for i in (range(len(self.outs)) if idx is None else idx):
            o = self.outs[i]
            if n < 0 or n > o.kc:
                continue
            pos = pos_over.get(i, o.pos) if pos_over else o.pos
            if n >= len(pos):
                continue
            if hero and not o.in_block(n) and (abs(pos[n, 0] - hx) > cfg.tol_hero or abs(pos[n, 1] - hy) > cfg.tol_hero):
                bad_h += 1
                continue
            if not _clappers_ok(o, n, obs, cfg):
                bad_c += 1
                continue
            out.append(i)
        return out, bad_h, bad_c


def _clappers_ok(o: OutData, n: int, obs: list, cfg: LiveCfg) -> bool:
    """TickCheck's rule with the timing spread: every observed Clapper matches a record of the outcome's branch seen
    at frame n (n inside its k + a .. k + b), its state, its frame in it within tol_j, its x within tol_x, its
    facing."""
    for ob in obs:
        r = o.recs.get(ob.iid)
        if r is None:
            continue
        lo, hi, st, j, x, f = r
        b = np.searchsorted(lo, n, side="right")
        w = hi[:b] >= n
        sid = o.sids.get(ob.st, -9)
        oj = ob.j if ob.j is not None else int(round(ob.t * 60.0))
        if not np.any(w & (st[:b] == sid) & (np.abs(j[:b] - oj) <= cfg.tol_j) & (np.abs(x[:b] - ob.x) <= cfg.tol_x) &
                      (f[:b] == ob.face)):
            return False
    return True


def _clapper_pred(o: OutData, n: int) -> dict:
    """The outcome's Clappers at frame n: {iid: (state, frame in it, x)} (its first record of frame n)."""
    inv = {v: k for k, v in o.sids.items()}
    out = {}
    for iid, (ks, st, j, x, f) in o.vrecs.items():
        a = np.searchsorted(ks, n)
        if a < len(ks) and ks[a] == n:
            out[iid] = (inv.get(int(st[a]), "?"), int(j[a]), round(float(x[a]), 2))
    return out


# ---- re-anchoring and the exact commit check ---------------------------------------------------------------------

def reanchor_outcome(o: OutData, s: int, lat: np.ndarray, lat_s: int) -> tuple:
    """The outcome's played segments from frame s on, with the LATCHED masks lat (frames s + 1 .. s + len(lat)); its
    down slash presses kept where the latched masks press them (a rising attack with down); lat_s: the latched mask at
    frame s. (Plan, '') or (None, why)."""
    segs = []
    first = True
    for si, (k0, masks, dsl, claw) in enumerate(o.segs):
        k1 = k0 + len(masks)                    # the segment's last frame (a Clawline's press P)
        if k1 <= s:
            if claw is not None and si + 1 < len(o.segs) and o.segs[si + 1][0] + CTRL_SETTLE > s:
                return None, "in a Clawline"
            if claw is not None and si + 1 >= len(o.segs) and k1 + 34 > s:
                return None, "in a Clawline"
            continue
        if first and k0 > s:
            return None, "in a Clawline"
        a = max(k0, s)
        lo, hi = a - s, k1 - s
        if hi > len(lat):
            return None, "short"
        m = (lat[lo:hi] & ~M_CLAW).astype(np.int64)
        nd = []
        for (i, iid) in dsl:
            kp = k0 + 1 + int(i)
            if kp <= s:
                if kp + DS_WIN > s:
                    return None, "slash under way"
                continue
            j = kp - (a + 1)
            q = lo + j
            pm = int(lat[q - 1]) if q > 0 else int(lat_s)
            if (int(lat[q]) & M_DS) != M_DS or (pm & km.B_ATTACK):
                return None, "press moved"
            nd.append((j, int(iid)))
        segs.append(ms.Seg(m, nd, claw, "re"))
        first = False
    if not segs:
        return None, "played"
    return ms.Plan(segs, "re"), ""


def _first_collision_out(o: OutData, tr, s: int, k1: int) -> int | None:
    """brnum.first_hit + the rare shapes for a trajectory re-simulated from frame s (its index k = frame s + k)
    against the outcome's geometry (frames from the anchor), frames s + 1 .. k1."""
    n = s + len(tr.pos)
    px = np.zeros(n)
    py = np.zeros(n)
    px[s:] = tr.pos[:, 0]
    py[s:] = tr.pos[:, 1]
    ifr = np.ones(n, np.bool_)
    ifr[s:] = tr.ifr[:len(tr.pos)]
    k1 = min(k1, n - 1)
    if k1 < s + 1:
        return None
    hk = [(h.iid, h.P + s + sk.HOOK_BODY_OFF[0], h.ctrl + s + sk.HOOK_BODY_OFF[1]) for h in tr.hooks if h.ok]
    hki = np.array([h[0] for h in hk], np.int64)
    hlo = np.array([h[1] for h in hk], np.int64)
    hhi = np.array([h[2] for h in hk], np.int64)
    off, BX, IIDB, coff, CO = o.geo
    kb, _ = brnum.first_hit(px, py, ifr, s + 1, k1, off, BX, IIDB, hki, hlo, hhi, ms._HW, ms._HH, ms._HDY,
                            ms.WALL_L, ms.WALL_R, coff, CO)
    top = kb - 1 if kb >= 0 else k1
    for k in o.rare_k:
        k = int(k)
        if s + 1 <= k <= top and not ifr[k]:
            if ms.shapes_hit(o.rare[k], cm.hurtbox(px[k], py[k])):
                return k
    return kb if kb >= 0 else None


def commit_check(W, lp: LivePlan, fo: int, S0: np.ndarray, inflight: np.ndarray, hold: tuple, lat_s: int, her_xy,
                 obs: list, cfg: LiveCfg, idx=None, tol: float | None = None) -> tuple:
    """THE EXACT HERO2 SIMULATION CHECK FROM THE CURRENT STATE of a received plan (module docstring, 1): (ok, why,
    info) - info: the outcomes kept (alive at f + 2), their re-simulated paths (pos_over), the max path deviation,
    the outcomes checked and simulated, ms."""
    t0 = time.perf_counter()
    s = int(fo - lp.t_a)
    info = {"s": s}
    if s < 0:
        return False, "future", info
    L = len(inflight)
    r0 = s + L + 1                           # the frame being chosen (f + 2)
    cons, bad_h, bad_c = lp.consistent(s, her_xy, obs, cfg, idx=idx, hero=False)
    info["cons"] = len(cons)
    tol = cfg.tol_commit if tol is None else tol
    if not cons:
        # the log: the most probable outcome's Clappers at s against the observed ones
        o_ = max(lp.outs, key=lambda o: o.p) if lp.outs else None
        if o_ is not None:
            info["pred"] = {str(k % 1000): v for k, v in _clapper_pred(o_, s).items()}
            info["obs"] = [[ob.iid % 1000, ob.st, ob.j, round(float(ob.x), 2), ob.face] for ob in obs]
        return False, "clappers", info
    alive = [i for i in cons if lp.outs[i].kc >= r0]
    if not alive:
        return False, "short", info
    face0 = int(S0[km.FACE]) if S0[km.FACE] != 0 else 1
    alpha_c = int(round(float(S0[km.ALPHA]) * 6.0)) % 6
    memo: dict = {}
    pos_over: dict = {}
    dev_max = 0.0
    n_sim = 0
    for i in alive:
        o = lp.outs[i]
        cmds = np.concatenate([np.asarray(inflight, np.int64), o.cmds[r0:o.end + 1]])
        lat = hold_filter1(cmds, hold)
        # a press of the fallback's still in flight (or one the filter moved) that the plan does not have
        planned = {k for (k, _) in o.presses}
        pm = int(lat_s)
        for q in range(min(len(lat), max(0, o.kc - s))):
            m = int(lat[q])
            if _rising(m, pm, km.B_ATTACK) and (s + 1 + q) not in planned:
                return False, "unplanned slash", info
            pm = m
        key = (o.variant, lat.tobytes(), tuple((iid, o.boxes[iid].tobytes()) for iid in sorted(o.boxes)),
               tuple((k0, c) for (k0, _, _, c) in o.segs))
        tr = memo.get(key)
        if tr is None:
            plan, why = reanchor_outcome(o, s, lat, lat_s)
            if plan is None:
                return False, why, info
            boxes = {iid: b[s:] for iid, b in o.boxes.items()}
            tr = ms.simulate(W, plan, lambda iid: boxes.get(iid), face0, S0, VARIANTS[o.variant], alpha_c)
            memo[key] = tr
            n_sim += 1
        kk = min(o.kc - s, len(tr.pos) - 1)
        if kk < L + 1:
            return False, "short", info
        dev = np.abs(tr.pos[:kk + 1] - o.pos[s:s + kk + 1]).max(axis=1) if kk >= 0 else np.zeros(0)
        dmax = float(dev.max()) if len(dev) else 0.0
        dev_max = max(dev_max, dmax)
        if dmax > tol and not cfg.replay:
            info.update(dev=round(dmax, 3), dev_k=int(np.argmax(dev)) + s, out=i)
            return False, "path", info
        kc_ = _first_collision_out(o, tr, s, o.kc)
        if kc_ is not None:
            info.update(col=int(kc_), out=i)
            return False, "danger", info
        po = o.pos.copy()
        po[s:s + kk + 1] = tr.pos[:kk + 1]
        pos_over[i] = po
    info.update(alive=alive, pos_over=pos_over, dev=round(dev_max, 3), n_sim=n_sim,
                ms=round((time.perf_counter() - t0) * 1e3, 2))
    return True, "ok", info


# ---- the worker process ---------------------------------------------------------------------------------------------

def boost_self(prio: str) -> str:
    """The live bot's worker rule (combat_run.boost_worker): High, the P-cores (SSBOT_WORKER_CPUS, default 0-15),
    EcoQoS off; 'as': as started."""
    if prio != "high":
        return "as started"
    if os.name != "nt" or os.environ.get("SSBOT_WORKER_BOOST", "1").strip() == "0":
        return "boost off"
    msgs = []
    try:
        import ctypes
        import psutil
        p = psutil.Process()
        p.nice(psutil.HIGH_PRIORITY_CLASS)
        msgs.append("High")
        spec = os.environ.get("SSBOT_WORKER_CPUS", "0-15")
        cpus = []
        for part in spec.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                cpus += range(int(a), int(b) + 1)
            elif part.strip():
                cpus.append(int(part))
        cpus = [c for c in cpus if c < (psutil.cpu_count() or 0)]
        if cpus:
            p.cpu_affinity(cpus)
            msgs.append(f"cpus {cpus[0]}-{cpus[-1]}")

        class _PT(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_uint32), ("ControlMask", ctypes.c_uint32), ("StateMask", ctypes.c_uint32)]
        st = _PT(1, 1, 0)
        k32 = ctypes.windll.kernel32
        ok = k32.SetProcessInformation(ctypes.c_void_p(k32.GetCurrentProcess()), 4, ctypes.byref(st),
                                       ctypes.sizeof(st))
        msgs.append("throttling off" if ok else "throttling unchanged")
    except Exception as e:  # noqa: BLE001 - best effort
        msgs.append(f"boost failed: {e}")
    return ", ".join(msgs)


class _Searcher(ms.Searcher):
    """The worker's searcher: its clock jumps past the cap once the search is to be cut (abort_fn)."""
    abort_fn = None

    def _now(self) -> float:
        t = time.perf_counter() if self.vclock is None else self.ev.units * self.vclock
        f = self.abort_fn
        return t + 1.0e6 if (f is not None and f()) else t


def build_prefix(snap: dict) -> tuple:
    """The snapshot's commands (in flight + bridge) through the hold filter -> (Seg of latched masks with the down
    slash presses of the plan in control, '') or (None, why) when a press the search cannot place is in flight (the
    bridge is cut before one)."""
    cmds = np.asarray(snap["cmds"], np.int64)
    L = int(snap["n_inflight"])
    lat = hold_filter1(cmds, snap["hold"])
    fo = int(snap["fo"])
    presses = {int(k): int(i) for (k, i) in snap.get("presses") or ()}
    n = len(lat)
    pm = int(snap.get("lat_s") or 0)
    dsl = []
    for q in range(len(lat)):
        m = int(lat[q])
        if m & M_CLAW:
            if q < L:
                return None, "Clawline in flight"
            n = q
            break
        if _rising(m, pm, km.B_ATTACK):
            iid = presses.get(fo + 1 + q) if (m & M_DS) == M_DS else None
            if iid is None:
                if q < L:
                    return None, "slash in flight"
                n = q
                break
            dsl.append((q, iid))
        pm = m
    if n == 0:
        return None, "no prefix"
    _, hold_after = hold_run(cmds[:n], snap["hold"])
    seg = ms.Seg((lat[:n] & ~M_CLAW).astype(np.int64), dsl, None, "pre")
    seg.hold_after = hold_after
    return seg, ""


def reanchor_prev(plan, t_a: int, fo: int, pre) -> object | None:
    """The plan in control (anchored at t_a) as the kept plan of a search from fo whose prefix is pre: the prefix,
    then its own masks after it (its first segment not played past the prefix), its later segments."""
    s = int(fo - t_a)
    n = len(pre.masks)
    seg0 = plan.segs[0]
    cut = s + n
    if s < 0 or cut >= len(seg0.masks):
        return None
    masks = np.concatenate([np.asarray(pre.masks, np.int64), np.asarray(seg0.masks, np.int64)[cut:]])
    dsl = list(pre.dsl) + [(int(i) - s, int(iid)) for (i, iid) in seg0.dsl if int(i) >= cut]
    return ms.Plan([ms.Seg(masks, dsl, seg0.claw, seg0.tag)] + [x.copy() for x in plan.segs[1:]], plan.origin, "kept")


def _search_one(S, cfg: LiveCfg, snap: dict, part: int, plans: dict, aborted) -> object:
    base = {"kind": "status", "part": part, "seq": snap["seq"], "ep": snap["ep"], "fo": snap["fo"],
            "ctrl_seen": (snap.get("ctrl") or (None,))[0]}
    if snap.get("busy"):
        return {**base, "status": "busy:" + str(snap["busy"])}
    if not snap.get("obs"):
        return {**base, "status": "no clapper"}
    pre, why = build_prefix(snap)
    if pre is None:
        return {**base, "status": "busy:" + why}
    sit = ms.Situation(np.asarray(snap["S"], float), list(snap["obs"]), dict(snap["mems"]), list(snap["hazards"]),
                       name=f"f{snap['fo']}")
    ctrl = snap.get("ctrl")
    prev = None
    if ctrl is not None and ctrl[0] in plans:
        prev = reanchor_prev(plans[ctrl[0]], ctrl[1], snap["fo"], pre)
    lead = len(pre.masks) - int(snap["n_inflight"])
    cap = min(max((lead - 2) / 60.0, cfg.cap_min), cfg.cap_ch if ctrl is not None else cfg.cap_fb)
    if aborted():
        return {**base, "status": "abort"}
    S.abort_fn = aborted
    S.realizer = HoldRealizer(len(pre.masks), pre.hold_after)
    t0 = time.perf_counter()
    res = S.decide(sit, prev=prev, cap_s=cap, prefix=pre)
    ms_ = (time.perf_counter() - t0) * 1e3
    base.update(ms=round(ms_, 1), cap=round(cap, 3), n_pre=len(pre.masks), n_cand=res.n_cand, had_prev=prev is not None,
                moved=S.realizer.n_moved, dropped=S.realizer.n_dropped)
    if aborted():
        return {**base, "status": "abort"}
    e = res.ev
    if e is None:
        return {**base, "status": "none"}
    if res.kept:
        return {**base, "status": "kept", "value": round(float(e.value), 3)}
    if not e.safe:
        return {**base, "status": "unsafe"}
    if e.plan.origin == "noop" or e.plan.n_frames() - len(pre.masks) < cfg.min_frames:
        return {**base, "status": "noop", "value": round(float(e.value), 3)}
    outs = build_outs(e, S.cfg.margins)
    if not outs:
        return {**base, "status": "unsafe"}
    pid = f"{part}:{snap['seq']}"
    log = ms.plan_log(e, snap["fo"])
    return LivePlan(pid=pid, part=part, ep=snap["ep"], seq=snap["seq"], t_a=int(snap["fo"]), f_snap=int(snap["f"]),
                    n_pre=len(pre.masks), n_inflight=int(snap["n_inflight"]), plan=e.plan, outs=outs,
                    value=float(e.value), hits=float(e.hits), p_safe=float(e.p_safe), origin=e.plan.origin,
                    note=e.plan.note, ms=round(ms_, 1), cap=cap, ctrl_seen=base["ctrl_seen"],
                    had_prev=prev is not None, n_cand=res.n_cand, timed_out=bool(res.timed_out),
                    steps=log.get("steps"), outcomes=log.get("outcomes"), t_sent=time.time())


def _warm_search(S, W) -> None:
    S0 = km.initial_state(W.params, 26.0, sk.FLOOR + sk.FOOT, ground=True, facing=1)
    o = cm.Obs(1, "Idle", 8 / 60.0, 33.0, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=8)
    sit = ms.Situation(S0, [o], {1: cm.Memory()})
    S.decide(sit, cap_s=0.3)
    S.decide(sit, cap_s=0.2, prefix=ms.Seg(np.full(3, km.B_RIGHT, np.int64), [], None, "pre"))


def worker_main(cfg_d: dict, part: int, nparts: int, in_q, out_q, inst: int = 0) -> None:
    """One search worker (module docstring, WORKERS): runs until a {'stop': True} snapshot or its queue closes."""
    cfg = LiveCfg(**cfg_d)
    boost = boost_self(cfg.prio)
    W = ms.World()
    S = _Searcher(W, ms.Cfg.live())
    if nparts > 1:
        S.part = (part, nparts)
    t0 = time.perf_counter()
    try:
        _warm_search(S, W)
    except Exception as e:  # noqa: BLE001 - reported, the worker goes on
        out_q.put({"kind": "error", "part": part, "where": "warm", "error": repr(e)[:400]})
    state = {"latest": None, "plans": {}, "abort": False, "cur": None, "stop": False}
    cond = threading.Condition()

    def reader():
        while True:
            try:
                snap = in_q.get()
            except (EOFError, OSError, ValueError):
                snap = {"stop": True}
            with cond:
                if snap.get("stop"):
                    state["stop"] = True
                    state["abort"] = True
                    cond.notify_all()
                    return
                po = snap.get("plan_obj")
                if po is not None and snap.get("ctrl") is not None:
                    state["plans"][snap["ctrl"][0]] = po
                    if len(state["plans"]) > 16:
                        state["plans"].pop(next(iter(state["plans"])))
                state["latest"] = snap
                cur = state["cur"]
                if cur is not None and ("hit" in (snap.get("trig") or ()) or snap.get("ep") != cur.get("ep") or
                                        (snap.get("ctrl") or (None,))[0] != (cur.get("ctrl") or (None,))[0]):
                    state["abort"] = True
                cond.notify_all()
    th = threading.Thread(target=reader, daemon=True, name="map2-reader")
    th.start()
    out_q.put({"kind": "ready", "part": part, "boost": boost, "os_pid": os.getpid(),
               "warm_s": round(time.perf_counter() - t0, 1)})
    done = -1
    while True:
        with cond:
            while not state["stop"] and (state["latest"] is None or state["latest"]["seq"] <= done):
                cond.wait(0.5)
            if state["stop"]:
                break
            snap = state["latest"]
            state["cur"] = snap
            state["abort"] = False
            plans = dict(state["plans"])
        done = snap["seq"]
        try:
            msg = _search_one(S, cfg, snap, part, plans, lambda: state["abort"])
        except Exception as e:  # noqa: BLE001 - one bad snapshot must not end the worker
            import traceback
            msg = {"kind": "error", "part": part, "seq": snap["seq"], "ep": snap["ep"], "error": repr(e)[:300],
                   "tb": traceback.format_exc()[-1500:]}
        with cond:
            state["cur"] = None
        try:
            out_q.put(msg)
        except Exception as e:  # noqa: BLE001
            out_q.put({"kind": "error", "part": part, "seq": snap["seq"], "error": "send: " + repr(e)[:300]})
        if cfg.mem_gb > 0:
            try:
                import psutil
                if psutil.Process().memory_info().rss > cfg.mem_gb * 2 ** 30:
                    out_q.put({"kind": "exit", "part": part, "why": "memory"})
                    return
            except Exception:  # noqa: BLE001
                pass


# ---- the controller (the bot's thread) -----------------------------------------------------------------------------

def _pct(v, q):
    return round(float(np.percentile(v, q)), 2) if len(v) else None


class Map2Controller:
    """Module docstring, THE CONTROLLER."""

    def __init__(self, instance: int = 0, log_dir=None, cfg: LiveCfg | None = None):
        self.cfg = cfg or LiveCfg.from_env()
        self.instance = instance
        self.K = cm.Know.load()
        self.W = ms.World(self.K)
        self.log_dir = Path(log_dir) if log_dir else None
        self.log_path: Path | None = (self.log_dir / f"map2_i{instance}.jsonl") if self.log_dir else None
        self.procs: list = []
        self.in_qs: list = []
        self.out_q = None
        self._ctx = None
        self.ready: dict = {}
        self.ep = -1
        self.seq = 0
        self.st = Counter()                 # counters over the run
        self.ms_pre: list = []
        self.ms_post: list = []
        self.ms_check: list = []
        self.lat: list = []                 # sent plans: the search's ms
        self.age_commit: list = []          # frames from a committed plan's anchor to its commit
        self.bridge_hist = {"plan": Counter(), "m2": Counter(), "script": Counter()}   # frames a bridge was followed
        self.errors: list = []
        self._reset_ep()

    # ---- processes ----
    def start(self, wait: bool = True) -> float:
        """Spawn the workers (their own processes) and wait until each reports ready (warmed)."""
        import multiprocessing as mp
        t0 = time.perf_counter()
        self._ctx = mp.get_context("spawn")
        self.out_q = self._ctx.Queue()
        n = max(1, int(self.cfg.parts))
        for part in range(n):
            q = self._ctx.Queue()
            self.in_qs.append(q)
            self.procs.append(self._spawn(part, n, q))
        if wait:
            self._wait_ready(n, t0)
        return time.perf_counter() - t0

    def _spawn(self, part: int, n: int, q):
        p = self._ctx.Process(target=worker_main, args=(self.cfg.as_dict(), part, n, q, self.out_q, self.instance),
                              daemon=True, name=f"map2-worker-{self.instance}-{part}")
        p.start()
        return p

    def _wait_ready(self, n: int, t0: float) -> None:
        while len(self.ready) < n and time.perf_counter() - t0 < self.cfg.ready_s:
            try:
                msg = self.out_q.get(timeout=1.0)
            except queue.Empty:
                if not all(p.is_alive() for p in self.procs):
                    break
                continue
            if msg.get("kind") == "ready":
                self.ready[msg["part"]] = msg
            elif msg.get("kind") == "error":
                self.errors.append(msg)

    def attach_inproc(self, in_qs: list, out_q) -> None:
        """Tests: workers run elsewhere (threads) on these queues."""
        self.in_qs, self.out_q = list(in_qs), out_q

    def stop(self) -> None:
        for q in self.in_qs:
            try:
                q.put({"stop": True})
            except Exception:  # noqa: BLE001
                pass
        for p in self.procs:
            p.join(timeout=5)

    def _check_procs(self) -> None:
        for part, p in enumerate(self.procs):
            if not p.is_alive():
                self.st["worker_restarts"] += 1
                self.errors.append({"kind": "restart", "part": part, "exitcode": p.exitcode, "ep": self.ep})
                self.procs[part] = self._spawn(part, len(self.procs), self.in_qs[part])

    def warm(self) -> float:
        """The bot side's compiled paths (the hold filter, a re-simulation, the collision kernel)."""
        t0 = time.perf_counter()
        hold_filter1(np.array([1, 0, 0, 2], np.int64), hold_tuple(km.HoldState.idle(1)))
        S0 = km.initial_state(self.W.params, 26.0, sk.FLOOR + sk.FOOT, ground=True, facing=1)
        ms.simulate(self.W, ms.Plan([ms.Seg(np.full(6, km.B_RIGHT, np.int64))]), lambda iid: None, 1, S0,
                    sk.HOOK_VARIANTS[0], 0)
        z = np.zeros(3)
        brnum.first_hit(z, z, np.zeros(3, np.bool_), 1, 2, np.zeros(4, np.int64), np.zeros((0, 4)),
                        np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64),
                        ms._HW, ms._HH, ms._HDY, ms.WALL_L, ms.WALL_R, np.zeros(4, np.int64), np.zeros((0, 3)))
        return time.perf_counter() - t0

    # ---- per episode ----
    def _reset_ep(self) -> None:
        self.trk = cm.Tracker()
        self.g = None                       # the game-frame clock (cumsum of dt x 60: a freeze does not advance it)
        self.lat_hist: deque = deque(maxlen=64)   # (f, latched act.mask)
        self.ctrl: LivePlan | None = None
        self.ctrl_idx: list = []
        self.ctrl_pos: dict = {}
        self.ctrl_since = None
        self.pending: list = []
        self.trig: list = []
        self.took = False
        self.last_freeze = -10 ** 9
        self.last_hit = -10 ** 9
        self._st_seen: dict = {}
        self._hp_seen: dict = {}
        self.new_plan_obj = None
        self.rows: list = []
        self.row: dict = {}
        self.last_msg: dict = {}
        self.ep_c = Counter()
        self.bridges: list = []             # [kind, first frame, keys, frames followed, alive] (the bridge audit)

    def reset(self, episode: int) -> None:
        self.flush()
        self.ep = int(episode)
        self._reset_ep()

    def feed(self, raw: dict, f: int) -> None:
        """Every STATE (ticks and caught-up frames): the Clapper tracker in game frames, her latched keys."""
        dt_ = raw.get("dt")
        dt = 1.0 / 60.0 if dt_ is None else float(dt_)
        self.g = 0.0 if self.g is None else self.g + min(max(dt, 0.0), 0.05) * 60.0
        self.trk.feed(raw, int(round(self.g)))
        self.lat_hist.append((int(f), int((raw.get("act") or {}).get("mask") or 0)))
        if dt <= 0.0:
            self.last_freeze = int(f)
        for ev in raw.get("ev") or ():
            if ev.get("k") == "damage":
                self.last_hit = int(f)

    # ---- the tick ----
    def _drain(self, fo: int) -> None:
        if self.out_q is None:
            return
        while True:
            try:
                msg = self.out_q.get_nowait()
            except (queue.Empty, EOFError, OSError):
                break
            if isinstance(msg, LivePlan):
                self.st["plans_recv"] += 1
                self.lat.append(msg.ms)
                self.last_msg = {"part": msg.part, "seq": msg.seq, "status": "plan", "ms": msg.ms, "pid": msg.pid,
                                 "value": round(msg.value, 3), "n_cand": msg.n_cand, "n_pre": msg.n_pre}
                if msg.ep != self.ep:
                    self.st["stale_ep"] += 1
                    continue
                msg.t_recv_f = int(fo)
                self.pending.append(msg)
                self.ep_c["plans"] += 1
            elif isinstance(msg, dict):
                k = msg.get("kind")
                if k == "status":
                    self.st["w_" + str(msg.get("status")).split(":")[0]] += 1
                    self.last_msg = {kk: msg.get(kk) for kk in ("part", "seq", "status", "ms", "cap", "n_pre", "n_cand",
                                                                "moved", "dropped", "value") if msg.get(kk) is not None}
                elif k == "ready":
                    self.ready[msg["part"]] = msg
                elif k in ("error", "exit"):
                    self.st["w_" + k] += 1
                    if len(self.errors) < 50:
                        self.errors.append(msg)

    def _drop(self, why: str) -> None:
        if self.ctrl is not None:
            self.st["drop_" + why] += 1
            self.ep_c["drop_" + why] += 1
            self.trig.append("drop")
        self.ctrl, self.ctrl_idx, self.ctrl_pos, self.ctrl_since = None, [], {}, None

    def pre(self, f: int, fo: int, raw: dict, S0: np.ndarray, inflight: np.ndarray, hold) -> int | None:
        """The keys map2 sends for frame f + 2, or None (the fallback's): module docstring 1 - 2."""
        t0 = time.perf_counter()
        S0 = np.asarray(S0, float).reshape(km.K, -1)[:, 0]
        row = {"f": int(f), "fo": int(fo)}
        self.row = row
        self.took = False
        if self.procs and f % 120 == 0:
            self._check_procs()
        self._drain(fo)
        h = raw.get("hero") or {}
        her = h.get("pos")
        obs = self.trk.obs()
        self._triggers(fo, obs)
        why = None
        dt_ = raw.get("dt")
        if her is None or (dt_ is not None and float(dt_) <= 0.0):
            self._drop("freeze")
            why = "freeze"
        elif self.last_hit >= fo - 1:
            self._drop("hit")
            why = "hit"
        inflight = np.asarray(inflight, np.int64)
        hold_t = hold_tuple(hold)
        lat_s = int((raw.get("act") or {}).get("mask") or 0)
        # 1. commit
        if why is None and self.pending:
            self.pending = [x for x in self.pending if fo - x.t_a <= self.cfg.stale and x.t_a > self.last_freeze]
            cands = self.pending
            if self.ctrl is not None:
                # a replacement must come from a search that knew the plan in control (and so beat it by w_switch),
                # or the plan in control is ending
                left = self._left(fo)
                cands = [x for x in cands if x.ctrl_seen == self.ctrl.pid and
                         (x.had_prev or left <= self.cfg.end_lead)]
            cands = sorted(cands, key=lambda x: (-x.value, -x.t_a))[:self.cfg.commits_per_tick]
            for lp in cands:
                tc = time.perf_counter()
                try:
                    ok, why_c, info = commit_check(self.W, lp, fo, S0, inflight, hold_t, lat_s,
                                                   her, obs, self.cfg)
                except Exception as e:  # noqa: BLE001 - a bad plan is dropped, the bot goes on
                    ok, why_c, info = False, "error", {"error": repr(e)[:200]}
                    if len(self.errors) < 50:
                        import traceback
                        self.errors.append({"kind": "check", "error": repr(e)[:300],
                                            "tb": traceback.format_exc()[-1200:]})
                msc = (time.perf_counter() - tc) * 1e3
                self.ms_check.append(msc)
                self.pending.remove(lp)
                row.setdefault("chk", []).append([lp.pid, bool(ok), why_c, round(msc, 2), info.get("s"),
                                                  info.get("cons"), info.get("dev"), info.get("col")] +
                                                 ([info.get("pred"), info.get("obs")] if "pred" in info else []))
                self.st["check_" + why_c] += 1
                self.ep_c["check_" + why_c] += 1
                if ok:
                    if self.ctrl is not None:
                        self.st["replaced"] += 1
                    self.ctrl, self.ctrl_idx, self.ctrl_pos = lp, list(info["alive"]), dict(info["pos_over"])
                    self.ctrl_since = int(f)
                    self.took = True
                    self.new_plan_obj = lp.plan
                    self.age_commit.append(int(fo - lp.t_a))
                    self.st["commits"] += 1
                    self.ep_c["commits"] += 1
                    row["commit"] = {"pid": lp.pid, "t_a": lp.t_a, "value": round(lp.value, 3), "hits": round(lp.hits, 3),
                                     "origin": lp.origin, "note": lp.note, "ms": lp.ms, "n_pre": lp.n_pre,
                                     "outs": len(lp.outs), "alive": len(info["alive"]), "steps": lp.steps,
                                     "outcomes": lp.outcomes,
                                     "cp": sorted({(k, i, kd) for o in lp.outs for (k, i, kd) in o.contacts})}
                    self.trig.append("commit")
                    break
        # 2. execute
        mask = None
        if self.ctrl is not None and why is None:
            lp = self.ctrl
            n = int(fo - lp.t_a)
            r = int(f + 2 - lp.t_a)
            cons, bad_h, bad_c = lp.consistent(n, her, obs, self.cfg, idx=self.ctrl_idx, hero=not self.cfg.replay,
                                               pos_over=self.ctrl_pos)
            alive = [i for i in cons if lp.outs[i].kc >= r and r < len(lp.outs[i].cmds)]
            if not cons and bad_h:
                # her position left the path while the Clappers are consistent: the plan re-anchored to her state
                # now (the exact re-simulation, the collisions; the path within tol_reanchor) or dropped
                tc = time.perf_counter()
                try:
                    ok, why_r, info = commit_check(self.W, lp, fo, S0, inflight, hold_t, lat_s, her, obs, self.cfg,
                                                   idx=self.ctrl_idx, tol=self.cfg.tol_reanchor)
                except Exception as e:  # noqa: BLE001
                    ok, why_r, info = False, "error", {"error": repr(e)[:200]}
                self.ms_check.append((time.perf_counter() - tc) * 1e3)
                row.setdefault("chk", []).append([lp.pid, bool(ok), "re:" + why_r, round((time.perf_counter() - tc) * 1e3, 2),
                                                  info.get("s"), info.get("cons"), info.get("dev"), info.get("col")])
                self.st["reanchor_" + why_r] += 1
                if ok:
                    self.ctrl_idx, self.ctrl_pos = list(info["alive"]), dict(info["pos_over"])
                    cons, bad_h, bad_c = lp.consistent(n, her, obs, self.cfg, idx=self.ctrl_idx, hero=True,
                                                       pos_over=self.ctrl_pos)
            if not cons:
                # the log: the most probable kept outcome's Clappers and her position against the observed ones
                o = max((lp.outs[i] for i in self.ctrl_idx), key=lambda o_: o_.p, default=None)
                if o is not None:
                    pc_ = _clapper_pred(o, n)
                    row["dc"] = [[ob.iid % 1000, ob.st, *(pc_.get(ob.iid) or (None, None, None))[:1],
                                  None if ob.iid not in pc_ else int((ob.j or 0) - pc_[ob.iid][1]),
                                  None if ob.iid not in pc_ else round(float(ob.x - pc_[ob.iid][2]), 3)] for ob in obs]
                    i_ = lp.outs.index(o)
                    pos = self.ctrl_pos.get(i_, o.pos)
                    if her is not None and 0 <= n < len(pos):
                        row["dh"] = [round(float(her[0] - pos[n, 0]), 3), round(float(her[1] - pos[n, 1]), 3)]
                self._drop("hero" if bad_h and not bad_c else "clappers")
                why = "fail:" + ("hero" if bad_h and not bad_c else "clappers")
            elif not alive:
                self._drop("end")
                why = "end"
            else:
                best = max(alive, key=lambda i: lp.outs[i].p)
                mask = int(lp.outs[best].cmds[r])
                agree = all(int(lp.outs[i].cmds[r]) == mask for i in alive)
                why = "commit" if self.took else "keep"
                row.update(pid=lp.pid, n=n, left=max(lp.outs[i].kc for i in alive) - r,
                           pc=round(sum(lp.outs[i].p for i in cons), 3), age=int(fo - lp.t_a), lat=lp.ms)
                if not agree:
                    row["dis"] = len({int(lp.outs[i].cmds[r]) for i in alive})
                    self.st["disagree"] += 1
                o = lp.outs[best]
                pos = self.ctrl_pos.get(best, o.pos)
                if her is not None and n < len(pos):
                    row["dh"] = [round(float(her[0] - pos[n, 0]), 3), round(float(her[1] - pos[n, 1]), 3)]
                pc_ = _clapper_pred(o, n)
                row["dc"] = [[ob.iid % 1000, ob.st, *(pc_.get(ob.iid) or (None, None, None))[:1],
                              None if ob.iid not in pc_ else int((ob.j or 0) - pc_[ob.iid][1]),
                              None if ob.iid not in pc_ else round(float(ob.x - pc_[ob.iid][2]), 3)] for ob in obs]
                if any(k == n for o_ in (lp.outs[i] for i in cons) for (k, _, _) in o_.contacts):
                    row["cp"] = "contact"
        if mask is None and why is None:
            why = "none" if not self.pending else "wait"
        row["why"] = why
        self.ms_pre.append((time.perf_counter() - t0) * 1e3)
        return mask

    def _left(self, fo: int) -> int:
        lp = self.ctrl
        if lp is None or not self.ctrl_idx:
            return -1
        return max(lp.outs[i].kc for i in self.ctrl_idx) - int(fo - lp.t_a)

    def _triggers(self, fo: int, obs: list) -> None:
        for ob in obs:
            key = (ob.st, int(self.trk.cl.get(ob.iid, {}).get("ent") or 0))
            if self._st_seen.get(ob.iid) not in (None, key):
                self.trig.append("reveal")
            self._st_seen[ob.iid] = key
            hp0 = self._hp_seen.get(ob.iid)
            if hp0 is not None and ob.hp < hp0:
                self.trig.append("landed")
            self._hp_seen[ob.iid] = ob.hp
        if self.last_hit >= fo - 1:
            self.trig.append("hit")
        if self.ctrl is not None and self._left(fo) <= self.cfg.end_lead:
            self.trig.append("end")

    def _busy(self, fo: int, raw: dict) -> str | None:
        h = raw.get("hero") or {}
        if not bool(h.get("hero_accepting_input", True)):
            return "no input"
        if self.last_freeze >= fo - 1:
            return "freeze"
        if any(t.get("st") in cm.INTRO for t in self.trk.cl.values() if t.get("e") is not None):
            return "intro"                      # the battle has not started (the model's intro is coarse)
        hist = [m for (fr, m) in self.lat_hist if fo - DS_WIN < fr <= fo]
        prev = [m for (fr, m) in self.lat_hist if fr == fo - DS_WIN]
        pm = prev[0] if prev else (hist[0] if hist else 0)
        for m in hist:
            if _rising(m, pm, km.B_ATTACK):
                return "slash"
            pm = m
        if any(m & M_CLAW for (fr, m) in self.lat_hist if fo - CLAW_BLOCK_F < fr <= fo):
            clip = str(((h.get("anim") or {}).get("clip")) or "")
            if clip.startswith("Harpoon") or not bool(h.get("hero_accepting_input", True)):
                return "Clawline"
        return None

    def post(self, f: int, fo: int, raw: dict, S0: np.ndarray, inflight: np.ndarray, hold, mask: int, own: str,
             res_cmd, sup: bool) -> None:
        """After the keys are chosen: the controller's state when the supervisor took the keys, the snapshot to the
        workers (module docstring, WORKERS), the per-tick log row."""
        t0 = time.perf_counter()
        S0 = np.asarray(S0, float).reshape(km.K, -1)[:, 0]
        row = self.row if self.row.get("f") == f else {"f": int(f), "fo": int(fo)}
        if sup and self.ctrl is not None:
            self._drop("sup")
            row["why"] = "sup"
        row.update(own=own, mask=int(mask), m2=int(own == "m2"))
        if own == "m2":
            self.st["ticks_m2"] += 1
            self.ep_c["ticks_m2"] += 1
        self.st["ticks"] += 1
        self.ep_c["ticks"] += 1
        # the bridge: the keys expected while the search runs
        bridge, presses = [], []
        if own == "m2" and self.ctrl is not None:
            lp = self.ctrl
            r = int(f + 3 - lp.t_a)
            cons = [i for i in self.ctrl_idx if lp.outs[i].kc >= r]
            if cons:
                o = lp.outs[max(cons, key=lambda i: lp.outs[i].p)]
                hi = min(o.kc, o.end, r + self.cfg.ch_lead - 1)
                for k in range(r, hi + 1):
                    c = int(o.cmds[k])
                    if c & M_CLAW:
                        break
                    bridge.append(c)
                pk = {int(k): iid for (k, iid) in o.presses}
                presses = [(lp.t_a + k, pk[k]) for k in range(r, r + len(bridge)) if k in pk]
        elif own == "plan" and res_cmd is not None and len(res_cmd) > 1 and int(res_cmd[0]) == int(mask):
            bridge = [int(x) for x in np.asarray(res_cmd, np.int64)[1:1 + self.cfg.fb_lead]]
        elif own not in ("sup", "m2", "plan", "cog"):
            bridge = [int(mask)] * self.cfg.sc_lead     # a script: its keys ahead are unknown - the held key (a guess)
        self._bridge_audit(f, int(mask))
        if bridge:
            kind = own if own in ("plan", "m2") else "script"
            self.bridges.append([kind, int(f) + 3, list(bridge), 0, True])
            if len(self.bridges) > 80:
                self.bridges = self.bridges[-80:]
        busy = self._busy(fo, raw)
        if self.in_qs:
            snap = {"seq": self.seq, "ep": self.ep, "f": int(f), "fo": int(fo), "S": S0.copy(),
                    "cmds": np.concatenate([np.asarray(inflight, np.int64), [int(mask)],
                                            np.asarray(bridge, np.int64)]).astype(np.int64),
                    "n_inflight": len(inflight) + 1, "hold": hold_tuple(hold),
                    "lat_s": int((raw.get("act") or {}).get("mask") or 0), "presses": presses,
                    "obs": self.trk.obs(), "mems": self.trk.mems(), "hazards": self.trk.hazards(self.K),
                    "ctrl": None if self.ctrl is None else (self.ctrl.pid, int(self.ctrl.t_a)),
                    "trig": sorted(set(self.trig)), "busy": busy, "own": own}
            if self.new_plan_obj is not None and self.ctrl is not None:
                snap["plan_obj"] = self.new_plan_obj
                self.new_plan_obj = None
            for q in self.in_qs:
                q.put(snap)
            self.seq += 1
        if self.trig:
            row["trig"] = sorted(set(self.trig))
        if busy:
            row["busy"] = busy
        if self.pending:
            row["pend"] = len(self.pending)
        if self.last_msg:
            row["w"] = self.last_msg
            self.last_msg = {}
        self.trig = []
        ms_ = (time.perf_counter() - t0) * 1e3
        self.ms_post.append(ms_)
        row["ms"] = round((self.ms_pre[-1] if self.ms_pre and self.row is row else 0.0) + ms_, 2)
        if self.cfg.log:
            self.rows.append(row)
        self.row = {}

    def _bridge_audit(self, f: int, mask: int) -> None:
        """The keys the bridges expected against the key sent for frame f + 2: per bridge the frames followed before
        the first difference (or all of them)."""
        k = int(f) + 2
        keep = []
        for b in self.bridges:
            kind, k0, keys, n, alive = b
            if not alive:
                continue
            if k0 <= k < k0 + len(keys):
                if int(keys[k - k0]) == mask:
                    b[3] += 1
                    if b[3] == len(keys):
                        self.bridge_hist[kind][len(keys)] += 1
                        continue
                else:
                    self.bridge_hist[kind][n] += 1
                    continue
            keep.append(b)
        self.bridges = keep

    def yield_sup(self, f: int, fo: int) -> None:
        """A pause tick of the supervisor: map2 drops its plan."""
        self._drop("sup")
        self.st["ticks"] += 1
        if self.cfg.log:
            self.rows.append({"f": int(f), "fo": int(fo), "own": "sup", "why": "pause", "m2": 0})

    # ---- logs and stats ----
    def flush(self) -> None:
        if self.log_path is None or not self.rows:
            self.rows = []
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            for r in self.rows:
                fh.write(json.dumps({"ep": self.ep, **r}, default=_jdefault) + "\n")
        self.rows = []

    def stats(self) -> dict:
        """The run's counters (counts: since the start; episode: this episode's), the bot-side times, the search
        latency, the workers, the first errors (the per-tick rows are flushed to the log)."""
        self.flush()
        st = dict(self.st)
        return {"cfg": self.cfg.as_dict(), "counts": st, "episode": {"ep": self.ep, **dict(self.ep_c)},
                "share_m2": round(st.get("ticks_m2", 0) / max(1, st.get("ticks", 0)), 4),
                "pre_ms_p50": _pct(self.ms_pre, 50), "pre_ms_p99": _pct(self.ms_pre, 99),
                "post_ms_p50": _pct(self.ms_post, 50), "post_ms_p99": _pct(self.ms_post, 99),
                "check_ms_p50": _pct(self.ms_check, 50), "check_ms_p99": _pct(self.ms_check, 99),
                "search_ms_p50": _pct(self.lat, 50), "search_ms_p90": _pct(self.lat, 90),
                "commit_age_p50": _pct(self.age_commit, 50), "commit_age_p90": _pct(self.age_commit, 90),
                "bridge_followed": {k: dict(sorted(v.items())) for k, v in self.bridge_hist.items()},
                "workers": {str(k): v for k, v in self.ready.items()}, "errors": self.errors[:20]}


def _jdefault(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    return str(o)


__all__ = ["enabled", "LiveCfg", "Map2Controller", "LivePlan", "OutData", "commit_check", "build_prefix",
           "reanchor_prev", "reanchor_outcome", "outcome_cmds", "hold_filter1", "worker_main", "build_outs"]
