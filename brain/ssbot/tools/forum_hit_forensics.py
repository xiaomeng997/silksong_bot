"""Wave-0 hit forensics of live Forum planner runs (task "wave-0 forensics", forum.md §19): for every hero hit of an
eval run, what hit, whether the support covered it, what the planner knew and chose before it, whether a plan that the
recorded future would have left untouched existed, and whether the hero moved as the model said.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_hit_forensics C:/ssbot/data/runs/m2/<run> [<run> ...]
        --out <dir> [--episodes 0,3] [--instances 1] [--every 3] [--workers 3] [--threads 4] [--deadline-ms inf]
        [--forced-rank share|seen|seen_cf]

Per episode the recording is replayed open loop through ForumPlannerPolicy (as tools.forum_policy_replay: the recorded
STATEs drive it, the supervisor never takes the keys; the prefix of each tick is the recorded ACTION masks, so every
tick plans from what really happened). The planner keeps its rows (ForumPlanner.debug). Written per episode
(<out>/<run>_i<inst>_ep<k>.json; existing ones are skipped):
  hits      each damage event and Multihit tick: source path, type, iid, the source's FSM state, the hero's
            position / clip; support coverage at L = 2 / 3 / 4 (the union and the source type's own support with the
            hazards it throws; a chain's Final Hit at its hook, as the live accounting) and what covered it (forecast /
            idle body tube / collider tube / hazard tube); the recorded colliders touching the hero the frame before.
  ticks     every `every`-th tick of the battle and every tick of K_SET before a hit: FORCED_RISK, rows (ok, known),
            safe rows; hindsight: each known row's first contact with the recorded damage colliders over its horizon
            (the nominal box, its invulnerable frames skipped, also grown by 0.25 u; the recorded future is open loop:
            the enemies' later reactions to a different hero are not modelled), the rows clear in hindsight, and which
            row each ranking picks (each ends with the share, the first support contact, -J):
              replay     the planner's own choice (ForumConfig.forced_rank = --forced-rank)
              live       the run's logged choice (decisions_i<N>.jsonl), matched by name
              share      least share of frames in the support over every known row
              committed  least share in MultiForecast.committed() (current attacks, tails, hazards)
              near       least share in the committed support or the tubes / death tails
              seen       forced_rank "seen"'s key over every known row (production seen_polys / seen_contacts)
              seen_cm    seen, then the committed share; seen_cf: seen, then the committed fine placements' share;
                         cf_seen: seen + committed fine frames as one count
              dr         seen's key on the recorded colliders (multi-hit ones too); dr_first: its first contact
                         first; dr_g: grown 0.3 u; dr18: the first 18 frames only
            and, before hits (DECOMP_K), the support decomposed by group (decompose).
  exec      per damage hit, the recorded keys of the last 12 / 24 frames rolled out from the state estimated there
            (the kin_check estimator, the planner's timing): the model's box against the logged one at the hit frame,
            and whether the model's and the logged path meet the recorded colliders (a kinematic miss: the logged path
            does, the model's does not).
"""
import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numba
import numpy as np

from ssbot.combat.planner import _rect_meets_polys

LAGS = (2, 3, 4)
K_SET = (1, 2, 3, 4, 6, 9, 12, 15, 18, 24, 30, 36, 45, 60, 75, 90)   # frames before a hit analysed in full
EXEC_K = (12, 24)
DECOMP_K = (1, 6, 12, 24, 36)                # ticks before a hit whose support is decomposed by group
NEAR_KINDS = ("idle", "collider", "hazard", "death")


# ---- recorded damage colliders ----

def damage_polys(s: dict) -> list[tuple[int, str, str, np.ndarray, tuple]]:
    """(iid, type key, collider name, world vertices [m, 2], entity velocity) of every enabled damage collider of a
    STATE (the cache's rule: support_threat, or a multi-hit collider of a multi_wounder entity)."""
    from ssbot.ipc.ents import SRC_BITS
    from ssbot.knowledge.behaviour_tables import multi_wounder_threat, support_threat
    out = []
    for e in s.get("ents") or ():
        src = int(e.get("src") or 0)
        vel = tuple(e.get("vel") or (0.0, 0.0))[:2]
        for c in e.get("colliders") or ():
            if not (support_threat(c) or (multi_wounder_threat(c) and src & SRC_BITS["multi_wounder"])):
                continue
            v = c.get("verts_world") or ()
            if len(v) < 6:
                continue
            out.append((int(e.get("iid") or 0), str(e.get("type_key")), str(c.get("name")),
                        np.asarray(v, np.float64).reshape(-1, 2), vel))
    return out


class FramePolys:
    """The recorded damage colliders of an episode, frame by frame, packed for the contact kernel. A collider gone on
    the next frame (a projectile destroyed by its hit inside that frame's physics steps) is carried into it, moved by
    its entity's velocity: the sampled frames alone miss such a contact."""

    def __init__(self, states: list[dict]):
        self.idx = {int(s["f"]): i for i, s in enumerate(states)}
        verts, starts, fst, owner, pvel = [], [0], [0], [], []
        n = 0
        prev: dict = {}
        for s in states:
            cur = {}
            dt = float(s.get("dt") or 0.0)
            items = damage_polys(s)
            for iid, tk, name, v, vel in items:
                cur[(iid, name)] = (tk, v, vel)
            for (iid, name), (tk, v, vel) in prev.items():
                if (iid, name) not in cur:
                    items.append((iid, tk, name + " (carried)", v + np.array([vel[0] * dt, vel[1] * dt]), vel))
            for iid, tk, name, v, vel in items:
                verts.append(v)
                n += len(v)
                starts.append(n)
                owner.append((iid, tk, name))
                pvel.append(vel if not name.endswith("(carried)") else (math.nan, math.nan))
            fst.append(len(starts) - 1)
            prev = cur
        self.verts = np.ascontiguousarray(np.concatenate(verts) if verts else np.zeros((0, 2)))
        self.starts = np.array(starts, np.int64)
        self.fst = np.array(fst, np.int64)        # polygons of state i: fst[i] .. fst[i + 1]
        self.owner = owner
        self.vel = np.array(pvel, np.float64).reshape(-1, 2)

    def window(self, f0: int, n: int) -> tuple[np.ndarray, int]:
        """Polygon index bounds [n + 1] of the frames f0 .. f0 + n - 1 (frames past the episode: none) and how many
        of them exist."""
        i0 = self.idx.get(int(f0))
        if i0 is None:
            return np.zeros(1, np.int64), 0
        m = min(n, len(self.fst) - 1 - i0)
        return np.ascontiguousarray(self.fst[i0:i0 + m + 1]), m

    def who(self, f: int, box) -> list[tuple]:
        """Colliders of frame f meeting a box."""
        i = self.idx.get(int(f))
        out = []
        if i is None:
            return out
        for p in range(self.fst[i], self.fst[i + 1]):
            st = self.starts[p:p + 2]
            if _rect_meets_polys(box[0], box[1], box[2], box[3], self.verts, st, 0.0, 0.0):
                out.append(self.owner[p])
        return out


def decompose(fcast, cx, cy, t, live) -> list[list]:
    """What covers the rows' centres (cx, cy [N, F] at t [F]; live [N, F]: not invulnerable): per support group (the
    placements of one owner, kind, family and committed flag; the boxes of one owner and kind; a hazard path) the
    share of the live cells it covers and of the live cells of the first frame. Sorted by share, groups >= 1 %."""
    tk_of = {s.iid: s.type_key for s in fcast.subjects}
    tot = max(int(live.sum()), 1)
    tot1 = max(int(live[:, 0].sum()), 1)
    out = []

    def add(owner, kind, fam, com, occ):
        occ = occ & live
        sh = occ.sum() / tot
        if sh >= 0.01:
            out.append([tk_of.get(int(owner), str(owner)), kind, str(fam), bool(com), round(float(sh), 3),
                        round(float(occ[:, 0].sum() / tot1), 3)])
    for kname, meta, fn in (("fine", fcast.pm, fcast._fine_occ), ("window", fcast.wm, fcast._win_occ),
                            ("bbox", fcast.bb, fcast._bbox_occ)):
        if not len(meta["owner"]):
            continue
        groups = defaultdict(list)
        for i, (o, fam, com) in enumerate(zip(meta["owner"], meta["family"], meta["committed"])):
            groups[(int(o), str(fam), bool(com))].append(i)
        for (o, fam, com), idx in groups.items():
            sel = np.zeros(len(meta["owner"]), bool)
            sel[idx] = True
            add(o, kname, fam, com, fn(cx, cy, t, sel))
    for o, kind in sorted({(int(b[0]), b[1]) for b in fcast.boxes}):
        add(o, kind, "-", kind == "death", fcast._box_occ(cx, cy, t, kinds=(kind,), only={o}))
    for p in fcast.paths:
        add(p.iid, "path", p.type_key, True, fcast._path_occ(cx, cy, t, only={int(p.iid)}))
    out.sort(key=lambda r: -r[4])
    return out


@numba.njit(cache=True)
def first_contact(box, inv, verts, starts, fb, m, grow):
    """[N]: the first frame k (1 .. m - 1) at which row n's box (grown by `grow`) meets a recorded damage polygon of
    frame k (polygons fb[k] .. fb[k + 1]), skipping invulnerable frames; -1: none."""
    N, T1 = box.shape[0], box.shape[1]
    out = np.full(N, -1, np.int64)
    for n in range(N):
        for k in range(1, min(T1, m)):
            if inv[n, k]:
                continue
            a, b = fb[k], fb[k + 1]
            if b <= a:
                continue
            if _rect_meets_polys(box[n, k, 0] - grow, box[n, k, 1] - grow, box[n, k, 2] + grow, box[n, k, 3] + grow,
                                 verts, starts[a:b + 1], 0.0, 0.0):
                out[n] = k
                break
    return out


@numba.njit(cache=True)
def dr_contact(box, inv, verts, starts, p0, p1, vel, tk, grow):
    """[N] contact frames and [N] first contact (-1: none) of each row's box (grown by `grow`) with the damage
    polygons p0 .. p1 - 1 of the tick's own frame dead-reckoned along their entity's velocity (tk[k] s on at frame
    k); carried polygons (nan velocity) are left out. The planner's view of the colliders it sees now, no forecast."""
    N, T1 = box.shape[0], box.shape[1]
    cnt = np.zeros(N, np.int64)
    first = np.full(N, -1, np.int64)
    for n in range(N):
        for k in range(1, T1):
            if inv[n, k]:
                continue
            for p in range(p0, p1):
                if vel[p, 0] != vel[p, 0]:
                    continue
                dx, dy = vel[p, 0] * tk[k], vel[p, 1] * tk[k]
                if _rect_meets_polys(box[n, k, 0] - grow, box[n, k, 1] - grow, box[n, k, 2] + grow,
                                     box[n, k, 3] + grow, verts, starts[p:p + 2], dx, dy):
                    cnt[n] += 1
                    if first[n] < 0:
                        first[n] = k
                    break
    return cnt, first


# ---- per-episode replay ----

def _mask_of(s: dict) -> int:
    return int((s.get("act") or {}).get("mask", 0) or 0)


def _family_of(pol, iid) -> tuple[str | None, str | None]:
    tr = pol.fc.trackers.get(iid) if iid is not None else None
    if tr is None:
        return None, None
    inst = getattr(tr, "inst", None) or getattr(tr, "instance", None)
    fam = getattr(inst, "family", None) if inst is not None else None
    return getattr(tr, "state", None), fam


def _own_ids(fcast, tk: str | None) -> set:
    """The iids of the enemies of type tk in the forecast and of the hazards they throw (their placements' family
    "ent/<hazard type>", their deterministic paths)."""
    from ssbot.core.forum import FORUM_TYPES
    if tk is None:
        return set()
    out = {s.iid for s in fcast.subjects if s.type_key == tk}
    spawns = {hz for hz, _ in FORUM_TYPES[tk].spawns} if tk in FORUM_TYPES else set()
    for p in getattr(fcast, "paths", ()) or ():
        if p.type_key in spawns:
            out.add(int(p.iid))
    for meta in (fcast.pm, fcast.wm, fcast.bb):
        for o, fam in zip(meta["owner"], meta["family"]):
            if str(fam).startswith("ent/") and str(fam)[4:] in spawns:
                out.add(int(o))
    return out


def _coverage(pol, fj: int | None, tk: str | None) -> dict:
    """The hit at frame fj (or the frame before) against the forecasts L frames earlier: union, own, what covered."""
    out = {}
    by_f = {x[0]: x for x in pol.forecasts}
    for L in LAGS:
        r = {"union": None, "own": None, "by": None}
        old = None if fj is None else by_f.get(fj - L)
        if old is not None:
            _, fc, t_o = old
            xs, ys, ts = [], [], []
            for fr in (fj - 1, fj):
                bt = pol._boxes.get(fr)
                if bt is None:
                    continue
                bx, t = bt
                xs.append(0.5 * (bx[0] + bx[2]))
                ys.append(0.5 * (bx[1] + bx[3]))
                ts.append(t - t_o)
            if xs:
                X, Y, T = np.array([xs]), np.array([ys]), np.array(ts)
                parts = fc.occupied_parts(X, Y, T)
                hit = {k: bool(v.any()) for k, v in parts.items()}
                r["union"] = any(hit.values())
                r["by"] = [k for k, v in hit.items() if v]
                ids = _own_ids(fc, tk)
                r["own"] = bool(fc.occupied_only(X, Y, T, ids).any()) if ids else False
        out[str(L)] = r
    return out


def _shares(fcast, box, inv, tk, frames) -> dict[str, np.ndarray]:
    """[N] share of `frames` with the row's box centre in the full support, the committed support and the near
    support (committed or the tubes / death tails), invulnerable frames clear."""
    cx = 0.5 * (box[:, frames, 0] + box[:, frames, 2])
    cy = 0.5 * (box[:, frames, 1] + box[:, frames, 3])
    t = tk[frames]
    live = ~inv[:, frames]
    full = fcast.occupied(cx, cy, t) & live
    com = fcast.committed().occupied(cx, cy, t) & live
    near = (com | fcast._box_occ(np.asarray(cx, np.float64), np.asarray(cy, np.float64), np.asarray(t, np.float64),
                                 kinds=NEAR_KINDS)) & live
    first = np.where(full.any(axis=1), full.argmax(axis=1), len(frames))
    pm = fcast.pm
    cfine = (fcast._fine_occ(np.asarray(cx, np.float64), np.asarray(cy, np.float64), np.asarray(t, np.float64),
                             np.asarray(pm["committed"], bool)) if len(pm["owner"]) else np.zeros(cx.shape, bool)) & live
    return {"full": full.mean(axis=1), "committed": com.mean(axis=1), "near": near.mean(axis=1), "first": first,
            "cfine": cfine.mean(axis=1)}


def _pick(keys: list[np.ndarray], rows: np.ndarray) -> int:
    """The row of `rows` first in the lexicographic order of keys (ascending; the first key is the primary)."""
    order = np.lexsort(tuple(k[rows] for k in reversed(keys)))
    return int(rows[order[0]])


def run_episode(job: dict) -> dict:
    from ssbot.knowledge import kinematics as kin
    from ssbot.knowledge.kinematics import F_INVULN
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.forum_a0_report import type_of
    from ssbot.train.encounters import ENCOUNTERS
    pol = _POL["pol"]
    row, dec = job["row"], job["dec"]
    every = job["every"]
    t_job = time.perf_counter()
    rd = RecordingReader(row["recording"])
    for _, m in rd.terrain():
        if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
            pol.terrain_msg = m
    states = list(rd.states(row["f_wake"], row["f_end"]))
    pol.reset(random.Random(0), ENCOUNTERS[row["unit"]])
    pol.planner.debug = True
    if job["deadline_ms"] is not None:
        pol.planner.fcfg.deadline_ms = job["deadline_ms"]
    pol.planner.fcfg.forced_rank = job.get("forced_rank") or "share"
    feed0 = pol.backend.feed
    last_ws: list = [None]

    def feed(st):
        w = feed0(st)
        last_ws[0] = w
        return w
    pol.backend.feed = feed
    fp = FramePolys(states)
    by_f = {int(s["f"]): s for s in states}
    dmg_f = []
    for s in states:
        for ev in s.get("ev") or ():
            if ev.get("k") in ("damage", "special_damage"):
                dmg_f.append(int(s["f"]))
                break
    want = set()
    for c in dmg_f:
        want |= {c - k for k in K_SET}
    live = {int(d["f"]): d for d in dec}
    hits, ticks = [], []
    f_first = int(states[0]["f"])
    n = 0
    for i, s in enumerate(states):
        f = int(s["f"])
        nxt = states[i + 1] if i + 1 < len(states) else None
        if nxt is not None:
            pol.sent[int(nxt["f"])] = _mask_of(nxt)   # the prefix: the recorded keys
        pol.act(s, None)
        n += 1
        fo = int(s["f"])
        li = pol.planner.last_info
        dbg = li.get("dbg") if li else None
        res = pol.planner_last
        # ---- hits of this frame ----
        evs = [ev for ev in (s.get("ev") or ()) if ev.get("k") in ("damage", "special_damage")]
        for ev in evs:
            d = ev.get("d") or {}
            kind = "damage" if ev["k"] == "damage" else "tick"
            path = d.get("source") if kind == "damage" else (d.get("fsm") or d.get("method"))
            src = next((e for e in pol._hit_src.get(fo, []) if e["path"] == path), None)
            sid = None if src is None else src["sid"]
            tk = type_of(path, None)
            if sid is not None:
                tr = pol.fc.trackers.get(sid)
                tk = getattr(tr, "tk", tk) if tr is not None else tk
            fj, final = fo, False
            if kind == "damage" and "Final Hit" in str(d.get("fsm") or ""):
                fj, final = pol._hook_of(sid, str(path or ""), fo), True
            hero = s.get("hero") or {}
            b = hero.get("box")
            src_state = None
            if sid is not None:
                for e in s.get("ents") or ():
                    if int(e.get("iid") or 0) == sid:
                        fs = e.get("fsms") or ()
                        src_state = fs[0].get("state") if fs else None
            prev = by_f.get(fo - 1)
            who = fp.who(fo - 1, (prev.get("hero") or {}).get("box")) if prev and (prev.get("hero") or {}).get("box") \
                else []
            hits.append({"f": fo, "t": round(float(pol.fc.t), 3), "kind": kind, "path": path, "type": tk,
                         "src_id": sid, "src_state": src_state, "fsm": d.get("fsm"), "final": final, "hook": fj,
                         "hero": None if not b else [round(0.5 * (b[0] + b[2]), 2), round(b[1], 2)],
                         "clip": (hero.get("anim") or {}).get("clip"), "ground": (hero.get("cs") or {}).get("onGround"),
                         "cover": _coverage(pol, fj, tk) if kind == "damage" else None,
                         "touch_prev": [list(w) for w in who][:4]})
        # ---- tick analysis ----
        if dbg is None or res is None:
            continue
        rel = fo - f_first
        if fo not in want and rel % every:
            continue
        box, flags = dbg["box"], dbg["flags"]
        inv = (flags & F_INVULN) != 0
        T1 = box.shape[1]
        fb, m = fp.window(fo, T1)
        first = first_contact(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(inv), fp.verts, fp.starts,
                              fb, m, 0.0)
        first_g = first_contact(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(inv), fp.verts, fp.starts,
                                fb, m, 0.25)
        ok, known = dbg["ok"], dbg["known"]
        rows = np.flatnonzero(ok & known)
        fcast = pol.forecasts[-1][1] if pol.forecasts else None
        rec = {"f": fo, "rel": rel, "forced": bool(res.forced_risk), "S": int(res.S), "n": int(len(dbg["J"])),
               "n_ok_known": int(len(rows)), "n_safe": int(res.n_safe), "m": int(m),
               "replay": res.name, "posture": li.get("posture"),
               "hero": [round(float(v), 2) for v in ((s.get("hero") or {}).get("pos") or ())]}
        if len(rows):
            clear = first[rows] < 0
            clear_g = first_g[rows] < 0
            rec["hs_clear"] = int(clear.sum())
            rec["hs_clear_g"] = int(clear_g.sum())
            # among the planner-safe rows (S = 0), how many the recorded future leaves clear
            S = pol.planner.last_info["S"]
            safe = rows[~S[rows]]
            rec["safe_hs_clear"] = int((first[safe] < 0).sum()) if len(safe) else None
            frames = np.arange(1, T1)
            sh = _shares(fcast, box, inv, dbg["tk"], frames) if fcast is not None else None
            J = dbg["J"]
            names = dbg["names"]
            picks = {"replay": int(dbg["chosen"])}
            lv = live.get(fo)
            if lv is not None and lv.get("plan") in names:
                picks["live"] = names.index(lv["plan"]) if lv["plan"] != "CONTINUE" else len(names) - 1
            if sh is not None:
                picks["share"] = _pick([sh["full"], -sh["first"], -J], rows)
                picks["committed"] = _pick([sh["committed"], sh["full"], -sh["first"], -J], rows)
                picks["near"] = _pick([sh["near"], sh["full"], -sh["first"], -J], rows)
                i0 = fp.idx[fo]
                dcnt, dfirst = dr_contact(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(inv), fp.verts,
                                          fp.starts, int(fp.fst[i0]), int(fp.fst[i0 + 1]), fp.vel,
                                          np.ascontiguousarray(dbg["tk"], np.float64), 0.0)
                dfk = np.where(dfirst < 0, T1, dfirst)
                tdr = time.perf_counter()
                gcnt, gfirst = dr_contact(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(inv), fp.verts,
                                          fp.starts, int(fp.fst[i0]), int(fp.fst[i0 + 1]), fp.vel,
                                          np.ascontiguousarray(dbg["tk"], np.float64), 0.3)
                rec["dr_ms"] = round((time.perf_counter() - tdr) * 1e3, 3)
                b18 = np.ascontiguousarray(box[:, :19], np.float64)
                c18, f18 = dr_contact(b18, np.ascontiguousarray(inv[:, :19]), fp.verts, fp.starts, int(fp.fst[i0]),
                                      int(fp.fst[i0 + 1]), fp.vel, np.ascontiguousarray(dbg["tk"][:19], np.float64), 0.0)
                picks["dr_g"] = _pick([gcnt, -np.where(gfirst < 0, T1, gfirst), sh["full"], -sh["first"], -J], rows)
                picks["dr18"] = _pick([c18, -np.where(f18 < 0, T1, f18), sh["full"], -sh["first"], -J], rows)
                picks["dr"] = _pick([dcnt, -dfk, sh["full"], -sh["first"], -J], rows)
                if last_ws[0] is not None:
                    from ssbot.combat.forum_planner import seen_contacts, seen_polys
                    sv, ss, sb, svel = seen_polys(last_ws[0])
                    if len(sb):
                        scnt, sfst = seen_contacts(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(inv),
                                                   sv, ss, sb, svel, np.ascontiguousarray(dbg["tk"], np.float64),
                                                   np.ascontiguousarray(rows, np.int64), 0.0)
                    else:
                        scnt, sfst = np.zeros(len(J), np.int64), np.full(len(J), T1, np.int64)
                    picks["seen"] = _pick([scnt, -sfst, sh["full"], -sh["first"], -J], rows)
                    picks["seen_cf"] = _pick([scnt, -sfst, sh["cfine"], sh["full"], -sh["first"], -J], rows)
                    picks["seen_cm"] = _pick([scnt, -sfst, sh["committed"], sh["full"], -sh["first"], -J], rows)
                    picks["cf_seen"] = _pick([scnt + np.round(sh["cfine"] * (T1 - 1)).astype(np.int64), -sfst,
                                              sh["full"], -sh["first"], -J], rows)
                    rec["seen_clear"] = int((scnt[rows] == 0).sum())
                    rec["seen_clear_hs"] = int(((scnt[rows] == 0) & clear).sum())
                picks["dr_first"] = _pick([-dfk, dcnt, sh["full"], -sh["first"], -J], rows)
                rec["dr_clear"] = int((dcnt[rows] == 0).sum())
                rec["dr_clear_hs"] = int(((dcnt[rows] == 0) & clear).sum())
                rec["dr_hit_hs"] = int(((dcnt[rows] > 0) & clear).sum())
                rec["share_min"] = round(float(sh["full"][rows].min()), 3)
                rec["committed_min"] = round(float(sh["committed"][rows].min()), 3)
                rec["near_min"] = round(float(sh["near"][rows].min()), 3)
                rec["cfine_min"] = round(float(sh["cfine"][rows].min()), 3)
                rec["clear_cfine"] = round(float(sh["cfine"][rows][clear].mean()), 3) if clear.any() else None
                rec["hit_cfine"] = round(float(sh["cfine"][rows][~clear].mean()), 3) if (~clear).any() else None
                rec["clear_share"] = round(float(sh["full"][rows][clear].mean()), 3) if clear.any() else None
                rec["hit_share"] = round(float(sh["full"][rows][~clear].mean()), 3) if (~clear).any() else None
                rec["clear_committed"] = round(float(sh["committed"][rows][clear].mean()), 3) if clear.any() else None
                rec["hit_committed"] = round(float(sh["committed"][rows][~clear].mean()), 3) if (~clear).any() \
                    else None
                if any(fo == c - k for c in dmg_f for k in DECOMP_K):
                    fr_ = np.arange(1, T1)
                    br = box[rows][:, fr_]
                    rec["decomp"] = decompose(fcast, 0.5 * (br[..., 0] + br[..., 2]), 0.5 * (br[..., 1] + br[..., 3]),
                                              dbg["tk"][fr_], ~inv[rows][:, fr_])
            rec["picks"] = {k: [names[v] if v < len(names) else str(v), int(first[v]), int(first_g[v])]
                            for k, v in picks.items()}
            if lv is not None:
                rec["live_ms"] = lv.get("ms")
                rec["live_forced"] = lv.get("forced")
                rec["live_plan"] = lv.get("plan")
        ticks.append(rec)
    # ---- execution: recorded keys rolled out from the state estimated k frames before each damage hit ----
    exe = []
    try:
        from ssbot.knowledge.kinematics import Trace
        tr = Trace.from_states(states, pol.params)
        terrain = pol.terrain
        modes = kin.classify_modes(tr, forum=bool(pol.params.abilities))
        evs = kin.derive_events(tr, modes)
        fidx = {int(f): i for i, f in enumerate(tr.f)}
        for h in hits:
            if h["kind"] != "damage":
                continue
            c = h["f"]
            for K in EXEC_K:
                i0, ic = fidx.get(c - K), fidx.get(c)
                if i0 is None or ic is None or ic <= i0:
                    continue
                S0 = kin.estimate_state(tr, [i0], pol.params, terrain=terrain)
                I = np.arange(i0 + 1, ic + 1)
                ev = evs[I].copy()
                ev[-1] = 0                              # not the hit's own event
                r = kin.rollout(S0, tr.mask[I][None], pol.params, terrain, events=ev[None])
                mb, lb = r.box[0, -1], tr.box[ic]
                err = math.hypot(0.5 * (mb[0] + mb[2]) - 0.5 * (lb[0] + lb[2]), 0.5 * (mb[1] + mb[3])
                                 - 0.5 * (lb[1] + lb[3]))
                inv = (r.flags[0] & F_INVULN) != 0
                fb, m = fp.window(int(tr.f[i0]), r.box.shape[1])
                fc_model = int(first_contact(np.ascontiguousarray(r.box, np.float64), np.ascontiguousarray(inv[None]),
                                             fp.verts, fp.starts, fb, m, 0.0)[0])
                lbx = np.ascontiguousarray(tr.box[i0:ic + 1][None], np.float64)
                linv = np.zeros(lbx.shape[:2], np.bool_)
                fc_log = int(first_contact(lbx, linv, fp.verts, fp.starts, fb, m, 0.0)[0])
                exe.append({"f": c, "K": K, "err": round(err, 3), "model_first": fc_model, "log_first": fc_log,
                            "keys": [int(x) for x in tr.mask[I][-K:]]})
    except Exception as e:      # the execution check is an extra: a failure leaves the rest
        exe.append({"error": repr(e)[:300]})
    return {"run": job["run"], "inst": row["_inst"], "ep": row["episode"], "seed": row.get("seed"),
            "outcome": row.get("outcome"), "reason": row.get("reason"), "n_states": n, "hits": hits, "ticks": ticks,
            "exec": exe, "live_hit_log": (row.get("policy") or {}).get("hit_log"),
            "secs": round(time.perf_counter() - t_job, 1)}


_POL: dict = {}


def _init(threads: int, crest: str = "Reaper", clash: str = "off") -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    pol = ForumPlannerPolicy(threads=threads, crest=crest, clash=clash)
    pol.warmup()
    import dataclasses
    step0 = pol.sc.step

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else \
            dataclasses.replace(r, mask=None, outcome=None)
    pol.sc.step = step
    _POL["pol"] = pol


def _job_safe(job: dict) -> dict:
    try:
        return run_episode(job)
    except Exception as e:
        import traceback
        return {"run": job["run"], "inst": job["row"]["_inst"], "ep": job["row"]["episode"],
                "error": traceback.format_exc()[-2000:]}


def jobs_of(run: Path, a) -> list[dict]:
    out = []
    for p in sorted(run.glob("attempts_i*.jsonl")):
        inst = int(p.stem.split("_i")[1])
        if a.instances and inst not in a.instances:
            continue
        dec = defaultdict(list)
        dp = run / f"decisions_i{inst}.jsonl"
        if dp.exists():
            for x in dp.read_text("utf-8").splitlines():
                if x.strip():
                    d = json.loads(x)
                    if d.get("mode") != "PAUSE":
                        dec[d["ep"]].append({k: d.get(k) for k in ("f", "plan", "forced", "n_safe", "ms", "P", "J",
                                                                   "mode", "tgt_type")})
        for x in p.read_text("utf-8").splitlines():
            if not x.strip():
                continue
            r = json.loads(x)
            if r.get("outcome") == "HARNESS_FAIL" or not r.get("recording"):
                continue
            if a.episodes and r["episode"] not in a.episodes:
                continue
            r["_inst"] = inst
            r.pop("acts", None)
            out.append({"run": run.name, "row": r, "dec": dec.get(r["episode"], []), "every": a.every,
                        "deadline_ms": a.deadline_ms, "forced_rank": a.forced_rank})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--episodes", type=lambda s: [int(x) for x in s.split(",") if x], default=None)
    ap.add_argument("--instances", type=lambda s: [int(x) for x in s.split(",") if x], default=None)
    ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--deadline-ms", type=float, default=math.inf)
    ap.add_argument("--forced-rank", default="share", choices=("share", "seen", "seen_cf"),
                    help="the replayed planner's ForumConfig.forced_rank (its picks are 'replay')")
    ap.add_argument("--crest", default="Reaper", help="the policy's crest (Forum_W runs: Wanderer)")
    ap.add_argument("--clash", default="off", choices=("off", "on", "yellow", "cont", "main"),
                    help="the policy's clash mode (combat_run --forum-clash; the de-saturation arms: main)")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for r in a.runs:
        jobs += [j for j in jobs_of(r, a)
                 if not (a.out / f"{j['run']}_i{j['row']['_inst']}_ep{j['row']['episode']}.json").exists()]
    print(f"{len(jobs)} episodes", flush=True)
    t0 = time.perf_counter()

    def write(res):
        p = a.out / f"{res['run']}_i{res['inst']}_ep{res['ep']}.json"
        p.write_text(json.dumps(res, default=str), "utf-8")
        print(f"{p.name} {'ERROR' if 'error' in res else ''} {res.get('secs')} s "
              f"({time.perf_counter() - t0:.0f} s)", flush=True)
    if a.workers <= 1:
        _init(a.threads, a.crest, a.clash)
        for j in jobs:
            write(_job_safe(j))
    else:
        with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.threads, a.crest, a.clash)) as ex:
            for res in ex.map(_job_safe, jobs):
                write(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
