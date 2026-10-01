"""Identify the hero kinematics constants from logged play and write knowledge/1.0.30000/kinematics/hero_hunter.json
(M2 W1, DESIGN §3.5.2: identified from logs, not guessed).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.kin_fit <source> [<source> ...] [--out <json>] [--dry-run]

Sources as in ssbot.tools.kin_check (recordings, human sessions, fixtures). Each constant starts from the decompiled
prefab / crest value (HeroParams defaults: hero_constants.json, crests.json) and is replaced by the measured one
when the bot logs hold enough clean samples; `source` in the JSON names which, `fit` keeps the sample counts and
spreads. Measured from the trace itself (no model in the loop):
  frame time, gravity, run speed, jump speed and rise steps, release multiplier, air-hang ramp (terminal velocity is
  only reported: 30 u/s was not reached in the trial run);
  collider box (foot, head, half width) and the floor skin against the scene's terrain;
  nail recoil speed and steps; down-attack decay, vy clamp and spike speed (the 0.1 s antic and spike timers stay
  at the crest values: their frame counts follow the float32 timer sums, see ssbot.knowledge.kinematics);
  pogo rise steps; damage recoil vector (the hit-stop is not fitted: its FreezeMoment replay is checked against
  every logged hit instead);
  Silkspear phase thresholds (FSM wait times: the roundest float32 value inside every logged phase interval),
  decays and catch speed; Bind length, decay and vy cap; the external-lock decay; the landing contact band;
  the jump-bit lag of the "input" exporter (human sessions);
  per scene played by the bot, the solids that were really on during play (the TERRAIN dump is taken at room
  entry; Bone_05: the "Threaded Bell Gate" pair is closed for the fight, "Wall" is gone).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.knowledge.kinematics import HeroParams, Trace
from ssbot.tools.kin_check import load_source

FDT = km.FDT


def _counts(c: Counter) -> dict:
    return {int(k): int(v) for k, v in sorted(c.items())}


def _rnd(x, k=4):
    return None if x is None else round(float(x), k)


def _single_step(tr: Trace) -> np.ndarray:
    """Rows whose frame had exactly one physics step and whose previous frame is the previous game frame."""
    return (tr.fs == 1) & np.r_[False, np.diff(tr.f) == 1] & tr.valid & np.r_[False, tr.valid[:-1]]


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index ranges of True runs."""
    m = np.r_[False, mask.astype(bool), False]
    d = np.diff(m.astype(np.int8))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


class Fit:
    """Collects measured values with their provenance."""

    def __init__(self, params: HeroParams):
        self.p = params
        self.fit: dict = {}
        self.source: dict = dict(params.source)

    def set(self, key: str, value, n: int, note: str, spread=None, min_n: int = 3) -> None:
        self.fit[key] = {"value": value, "n": int(n), "spread": spread, "note": note}
        if value is None or n < min_n:
            self.source.setdefault(key, "prefab / crest config (not enough samples)")
            return
        setattr(self.p, key, type(getattr(self.p, key))(value) if not isinstance(getattr(self.p, key), list)
                else value)
        self.source[key] = f"kin_fit: {note} (n={n})"


def fit_motion(tr: Trace, modes: np.ndarray, f: Fit) -> None:
    run = tr.valid & (tr.ts == 1.0) & (tr.udt > 0) & np.r_[False, np.diff(tr.f) == 1]
    if run.sum() > 100:
        u = tr.udt[run].astype(np.float64)
        p1, p99 = np.percentile(u, [1, 99])
        f.set("frame_time", _rnd(float(np.mean(u[u < 0.025])), 7), int(run.sum()),
              f"mean unscaled frame time at time scale 1 (p1 {p1:.5f}, p99 {p99:.5f})")
    one = _single_step(tr)
    prev = np.r_[0, np.arange(len(tr) - 1)]
    normal = (modes == km.M_NORMAL) & (modes[prev] == km.M_NORMAL)
    ground = tr.flag("onGround")
    air = ~ground & ~ground[prev]
    vy, vy0 = tr.vel[:, 1], tr.vel[prev, 1]
    rec = tr.flag("recoilingLeft") | tr.flag("recoilingRight")
    jheld = (tr.mask & km.B_JUMP) != 0
    # gravity: falling, full gravity scale (jump not held, so no air hang), no contact
    sel = one & normal & air & (vy < 0) & (vy0 < 0) & ~jheld & ~jheld[prev] & (vy > -f.p.max_fall + 0.5) & \
        ~tr.flag("downSpikeBouncing") & ~tr.flag("jumping")
    g = -(vy[sel] - vy0[sel]) / FDT
    g = g[np.abs(g - np.median(g)) < 2.0] if len(g) else g
    f.set("gravity", _rnd(np.median(g), 3) if len(g) else None, len(g), "falling steps, dvy / fdt",
          _rnd(np.std(g)) if len(g) else None, min_n=20)
    # run speed: grounded, one direction held, no recoil
    lr = (tr.mask & (km.B_LEFT | km.B_RIGHT))
    one_dir = (lr == km.B_LEFT) | (lr == km.B_RIGHT)
    sel = normal & ground & one_dir & ~rec & (np.abs(tr.vel[:, 0]) > 0.5)
    v = np.abs(tr.vel[sel, 0])
    f.set("run_speed", _rnd(np.median(v), 4) if len(v) else None, len(v), "grounded |vx| with one direction held",
          _rnd(np.percentile(v, 99) - np.percentile(v, 1)) if len(v) else None, min_n=20)
    # jump speed and rise steps
    jumping = tr.flag("jumping")
    sel = one & normal & jumping & jumping[prev] & (np.abs(vy - vy0) < 1e-3) & (vy > 5)
    js = vy[sel] + f.p.gravity * FDT
    f.set("jump_speed", _rnd(np.median(js), 3) if len(js) else None, len(js), "vy + g fdt on rising jump steps",
          _rnd(np.std(js)) if len(js) else None, min_n=20)
    rise = []
    pogo_rise = []
    rise_v = f.p.jump_speed - f.p.gravity * FDT
    j_on = np.flatnonzero(jumping & ~jumping[prev])
    bounce_on = tr.flag("downSpikeBouncing") & ~tr.flag("downSpikeBouncing")[prev]
    for i in j_on:
        k, steps, n = i + 1, 0, 0
        while k < len(tr) and k < i + 40 and tr.valid[k] and (jheld[k] or bounce_on[i]) and modes[k] == km.M_NORMAL:
            if tr.fs[k] == 1 and abs(tr.vel[k, 1] - rise_v) < 1e-3:
                n += 1
            elif tr.fs[k] >= 1:
                break
            k += 1
        if k < len(tr) and tr.fs[k] >= 1 and tr.vel[k, 1] < rise_v - 0.5 and n > 0:
            (pogo_rise if bounce_on[i] else rise).append(n)
    c = Counter(rise)
    if c:
        f.set("jump_steps", int(c.most_common(1)[0][0]) - 1, len(rise), "full-hold jumps: rise steps - 1 "
              f"(JUMP_STEPS: Jump() runs while jump_steps <= JUMP_STEPS); counts {_counts(c)}", min_n=5)
    c = Counter(pogo_rise)
    if c:
        f.set("pogo_jump_steps", int(f.p.jump_steps + 1 - c.most_common(1)[0][0]), len(pogo_rise),
              f"pogo rise steps {_counts(c)} -> start jump_steps", min_n=3)
    # release: vy halves every Update while vy > 0 and jump is up (frames without a step show it alone)
    sel = (tr.fs == 0) & normal & air & ~jheld & (vy0 > 0.05) & np.r_[False, np.diff(tr.f) == 1] & \
        ~tr.flag("downSpikeBouncing")
    r = vy[sel] / vy0[sel]
    r = r[(r > 0.2) & (r < 0.9)]
    f.set("jump_release_mult", _rnd(np.median(r), 4) if len(r) else None, len(r),
          "vy ratio on step-less frames with jump released", _rnd(np.std(r)) if len(r) else None)
    # terminal velocity
    fall = vy[normal & air]
    if len(fall):
        f.fit["max_fall_observed"] = {"value": _rnd(-fall.min(), 3), "n": int(len(fall)),
                                      "note": "fastest NORMAL fall; MAX_FALL_VELOCITY 30 binds only if reached"}
    # air hang: dvy per step while the jump stays held after the apex
    sel = one & normal & air & jheld & jheld[prev] & (vy < 0) & (vy0 < 0) & ~jumping & (vy0 > -6)
    gsc = -(vy[sel] - vy0[sel]) / (FDT * f.p.gravity)
    if len(gsc):
        f.fit["air_hang_scales"] = {"value": sorted(Counter(np.round(gsc, 2).tolist()).most_common(8)),
                                    "n": int(len(gsc)), "note": "gravity scales seen right after the apex, jump held"}
    gmin = gsc[gsc > 0.05].min() if (gsc > 0.05).any() else None
    if gmin is not None:
        f.set("air_hang_gravity", _rnd(gmin - f.p.air_hang_accel * FDT, 3), len(gsc),
              "smallest post-apex scale minus one ramp step (StartAirHang, then += accel * fdt before the step)")


def fit_box(tr: Trace, terrains: dict, f: Fit) -> None:
    rest = tr.valid & tr.flag("onGround") & (np.abs(tr.vel).sum(axis=1) < 1e-6) & \
        np.r_[False, np.abs(np.diff(tr.pos[:, 0])) < 1e-6]
    b = tr.box[rest]
    p = tr.pos[rest]
    if len(b) < 10:
        return
    foot = np.median(p[:, 1] - b[:, 1])
    head = np.median(b[:, 3] - p[:, 1])
    hw = np.median(0.5 * (b[:, 2] - b[:, 0]))
    f.set("foot", _rnd(foot, 4), len(b), "pos.y - box bottom at rest")
    f.set("head", _rnd(head, 4), len(b), "box top - pos.y at rest")
    f.set("half_width", _rnd(hw, 4), len(b), "half box width at rest")
    gaps = []
    for name, t in terrains.items():
        sel = np.array([tr.scenes[s] == name for s in tr.scene[rest]])
        if not sel.any() or len(t.hseg) == 0:
            continue
        bb = b[sel]
        cx = 0.5 * (bb[:, 0] + bb[:, 2])
        for k in range(0, len(bb), max(1, len(bb) // 500)):
            under = (t.hseg[:, 1] < cx[k]) & (t.hseg[:, 2] > cx[k]) & (t.hseg[:, 0] <= bb[k, 1] + 1e-3)
            if under.any():
                gaps.append(bb[k, 1] - t.hseg[under, 0].max())
    if gaps:
        g = np.array(gaps)
        f.set("skin", _rnd(np.median(g), 4), len(g), "box bottom - floor segment at rest",
              _rnd(np.percentile(g, 95) - np.percentile(g, 5)), min_n=10)


def fit_recoil(tr: Trace, f: Fit) -> None:
    speeds, counts = [], []
    for name in ("recoilingLeft", "recoilingRight"):
        fl = tr.flag(name)
        for a, b in _runs(fl):
            if b - a > 30:
                continue
            steps = int(tr.fs[a + 1:b + 1].sum()) if b < len(tr) else None
            if steps is not None:
                counts.append(steps - 1)   # the run ends in the frame whose FixedUpdate cancels it
            v = np.abs(tr.vel[a:b, 0])
            speeds.extend(v[(v > 1) & (v < 5)].tolist())
    if speeds:
        f.set("recoil_velocity", _rnd(np.median(speeds), 3), len(speeds), "|vx| in nail recoil without input push")
    if counts:
        c = Counter(counts)
        f.set("recoil_steps", int(c.most_common(1)[0][0]), len(counts), f"steps after the hit frame {_counts(c)}")


def fit_downspike(tr: Trace, modes: np.ndarray, f: Fit) -> None:
    an = modes == km.M_DS_ANTIC
    sp = modes == km.M_DS_SPIKE
    antic_t, decel, clamp_hi, spike_v, spike_steps, end_vy = [], [], [], [], [], []
    for a, b in _runs(an):
        antic_t.append(float(tr.dt[a:b].sum()))
        for k in range(a + 1, b):
            if tr.fs[k] == 1 and abs(tr.vel[k - 1, 0]) > 0.5:
                decel.append(tr.vel[k, 0] / tr.vel[k - 1, 0])
        clamp_hi.append(tr.vel[a, 1])
    for a, b in _runs(sp):
        v = tr.vel[a:b]
        spike_v.extend(np.abs(v[np.abs(v[:, 1]) > 20]).ravel().tolist())
        spike_steps.append(int(tr.fs[a + 1:b].sum()))
        if b < len(tr) and modes[b] == km.M_NORMAL and not tr.flag("onGround")[b] and tr.fs[b] == 1:
            end_vy.append(tr.vel[b, 1] + f.p.gravity * FDT)
    if antic_t:
        # the antic flips to the spike in the first Update whose timer (dt summed from the press frame) reaches
        # DownSpikeAnticTime (crests.json 0.1): 6 or 7 frames depending on the frame times, so it is not refitted
        f.fit["ds_antic_runs"] = {"value": Counter(np.round(antic_t, 3).tolist()).most_common(4), "n": len(antic_t),
                                  "note": "scaled seconds in the antic (prefab 0.1 kept)"}
    if decel:
        f.set("ds_antic_decel", _rnd(np.median(decel), 4), len(decel), "vx ratio per antic step")
    if clamp_hi:
        f.fit["ds_antic_vy_at_press"] = {"value": sorted(set(np.round(clamp_hi, 2).tolist()))[:12],
                                         "n": len(clamp_hi), "note": "vy right after the press (clamp)"}
        lo = min(clamp_hi)
        if lo > -12.5:
            f.set("ds_antic_vy_min", _rnd(lo, 3), len(clamp_hi), "lowest vy at a down-attack press")
    if spike_v:
        f.set("ds_speed", _rnd(np.median(spike_v), 3), len(spike_v), "|v| components while spiking")
    if spike_steps:
        c = Counter(spike_steps)
        f.fit["ds_spike_steps"] = {"value": _counts(c), "n": len(spike_steps), "note": "steps in a spike (incl. cut)"}
    if end_vy:
        f.fit["ds_end_vy_seen"] = {"value": sorted(Counter(np.round(end_vy, 2).tolist()).most_common(4)),
                                   "n": len(end_vy), "note": "vy + g fdt in the frame after a spike (code: -10)"}


def fit_hurt(tr: Trace, modes: np.ndarray, f: Fit) -> None:
    """The hit-stop is not fitted: the model replays GameManager.FreezeMoment (wait 0.1 s of unscaled time summed in
    float32 from the second frame after the hit, then a 0.1 s ramp of the time scale); this checks it against the log
    (frame of the recoil start) and measures the recoil vector and length."""
    rep = km._freeze_replay(tr, f.p)
    ok, n_ev, rec_vec, rec_frames, frames = 0, 0, [], [], []
    hit = tr.flag("recoilFrozen") & ~np.r_[False, tr.flag("recoilFrozen")[:-1]]
    f.fit["damage_events"] = {"value": {"damage": int((tr.dmg != 0).sum()), "knockbacks": int(hit.sum())},
                              "n": int(hit.sum()), "note": "oracle damage events vs StartRecoil (recoilFrozen onsets)"}
    for i in np.flatnonzero(hit):
        k = i + 1
        while k < len(tr) and k < i + 40 and modes[k] == km.M_HURT_FREEZE:
            k += 1
        if k >= len(tr) or modes[k] != km.M_HURT_RECOIL or k - i < 5:
            continue
        n_ev += 1
        frames.append(k - i)
        pred = np.flatnonzero(rep[i:i + 40, 0] == 2)
        ok += int(len(pred) > 0 and i + pred[0] == k)
        e = k
        while e < len(tr) and modes[e] == km.M_HURT_RECOIL:
            e += 1
        rec_frames.append(e - k)
        steps = tr.fs[k + 1:e + 1].sum()
        if e < len(tr) and steps > 0:
            rec_vec.append((tr.phys[e] - tr.phys[k]) / (steps * FDT))
    if n_ev:
        f.fit["hurt_freeze_frames"] = {"value": _counts(Counter(frames)), "n": n_ev,
                                       "note": f"damage frame -> recoil start; FreezeMoment replay right in "
                                               f"{ok}/{n_ev}"}
    if rec_vec:
        v = np.abs(np.array(rec_vec))
        f.set("hurt_velocity", _rnd(np.median(v[:, 0]), 3), len(v), "|dx| / (steps fdt) over the damage recoil")
        f.set("hurt_vy_ratio", _rnd(np.median(v[:, 1]) / f.p.hurt_velocity, 4), len(v), "(dy / dx) over the recoil")
    if rec_frames:
        f.fit["hurt_recoil_frames"] = {"value": _counts(Counter(rec_frames)), "n": len(rec_frames),
                                       "note": "frames with the recoiling flag (RECOIL_DURATION 0.2 s, float32 dt sum)"}


def _threshold(intervals: list[tuple[float, float]]) -> tuple[float | None, list]:
    """A float32 threshold T with lo < T <= hi for the logged phase intervals (lo, hi]: the roundest value inside all
    of them (FSM wait times are round numbers), or, when they do not intersect, the value inside the most of them."""
    if not intervals:
        return None, []
    lo = max(a for a, _ in intervals)
    hi = min(b for _, b in intervals)
    if np.float32(lo) < np.float32(hi):
        for step in (0.05, 0.01, 0.005, 0.001, 1e-4, 1e-5):
            c = round(float(np.ceil(lo / step + 1e-9)) * step, 6)
            if np.float32(lo) < np.float32(c) <= np.float32(hi):
                return c, [lo, hi]
        return hi, [lo, hi]
    a = np.array(intervals, dtype=np.float32)
    cands = np.unique(a[:, 1])
    score = [int(((a[:, 0] < c) & (c <= a[:, 1])).sum()) for c in cands]
    best = float(cands[int(np.argmax(score))])
    return best, [lo, hi]


def _caps(tr: Trace, modes: np.ndarray, mode: int, decay: float, g: float, sign: int) -> list[float]:
    """|vy| / decay at the presses of an air cast / bind whose free vertical speed (rising: sign 1, falling: -1) was
    larger (the clip acted)."""
    out = []
    ground = tr.flag("onGround")
    for a, _ in _runs(modes == mode):
        if a < 1 or ground[a] or modes[a - 1] != km.M_NORMAL:
            continue
        free = tr.vel[a - 1, 1] - g * FDT * tr.fs[a]
        after = abs(tr.vel[a, 1]) / decay
        if free * sign > 0 and 1.0 < after < abs(free) - 0.5:
            out.append(after)
    return out


def fit_casts(tr: Trace, modes: np.ndarray, f: Fit) -> None:
    """Silkspear phases from the animation: antic (AnticG / AnticA), throw, catch; thresholds are scaled seconds
    summed (float32) over the frames after the press frame, as the model's timer."""
    clips = np.array(tr.clips, dtype=object)[tr.clip]
    ground = tr.flag("onGround")
    iv = {1: [], 2: [], 3: []}
    throw, catch = [], []
    decay, gdecay, cdecay, cspeed = [], [], [], []
    for a, b in _runs(modes == km.M_CAST):
        if b >= len(tr) or (tr.dmg[a:b + 1] != 0).any():
            continue
        k1 = next((k for k in range(a, b) if clips[k] == "NeedleThrow Throwing"), None)
        k2 = next((k for k in range(a, b) if clips[k] == "NeedleThrow Catch"), None)
        k3 = b if modes[b] == km.M_NORMAL else None
        # each phase is an FSM state with its own timer: float32 dt summed from the frame after its entry
        for key, (e, k) in ((1, (a, k1)), (2, (k1, k2)), (3, (k2, k3))):
            if e is None or k is None or k <= e or (tr.marks[e:k + 1] != 0).any():
                continue
            c = np.cumsum(tr.dt[e + 1:k + 1].astype(np.float32), dtype=np.float32)
            iv[key].append((float(c[-2]) if len(c) > 1 else 0.0, float(c[-1])))
            (throw if key == 2 else catch if key == 3 else []).append(float(c[-1]))
        end = k1 if k1 is not None else b
        for k in range(a + 1, end):
            if tr.fs[k] == 1 and abs(tr.vel[k - 1, 0]) > 0.5:
                (decay if not ground[a] else gdecay).append(tr.vel[k, 0] / tr.vel[k - 1, 0])
        if k2 is not None:
            cspeed.append(abs(tr.vel[k2, 0]))
            for k in range(k2 + 1, b):
                if tr.fs[k] == 1 and abs(tr.vel[k - 1, 0]) > 0.5:
                    cdecay.append(tr.vel[k, 0] / tr.vel[k - 1, 0])
    # the throw ends when the needle is back (26 or 27 frames for a full throw, earlier when it hits something
    # close): no single timer explains it, so the default is the longest full throw and the logged catch (EV_CATCH)
    # ends the shorter ones in replays; a planner should treat the catch frame as +-1 frame uncertain
    iv[2] = [x for x in iv[2] if x[1] > 0.3] or iv[2]
    for key, name, what in ((1, "cast_antic", "antic"), (2, "cast_throw", "throw"), (3, "cast_catch", "catch")):
        t, r = _threshold(iv[key])
        if t is None:
            continue
        if key == 2:
            t = max(b for _, b in iv[key])
        f.set(name, _rnd(t, 5), len(iv[key]),
              f"{what}: threshold in ({r[0]:.4f}, {r[1]:.4f}], runs {np.round([b for _, b in iv[key]], 4).tolist()}",
              min_n=1)
    if decay:
        f.set("cast_decay", _rnd(np.median(decay), 4), len(decay), "vx ratio per step in an air antic", min_n=5)
    if gdecay:
        f.set("cast_decay_ground", _rnd(np.median(gdecay), 4), len(gdecay), "vx ratio per step in a ground antic",
              min_n=5)
    cap = _caps(tr, modes, km.M_CAST, f.p.cast_decay, f.p.gravity, 1) + \
        _caps(tr, modes, km.M_CAST, f.p.cast_decay, f.p.gravity, -1)
    if cap:
        f.set("cast_vy_cap", _rnd(np.median(cap), 3), len(cap), "|vy| at clipped air cast presses / decay (both "
              f"directions: {sorted(np.round(cap, 2).tolist())[:6]}...)", min_n=1)
    if cspeed:
        f.set("cast_catch_speed", _rnd(np.median(cspeed), 3), len(cspeed), "|vx| when the catch starts", min_n=1)
    if cdecay:
        f.set("cast_catch_decay", _rnd(np.median(cdecay), 4), len(cdecay), "vx ratio per catch step", min_n=3)
    bdur, bend, bdec = [], [], []
    for a, b in _runs(modes == km.M_BIND):
        if b >= len(tr) or tr.flag("recoilFrozen")[a:b + 1].any():
            continue
        bdur.append(float(np.sum(tr.dt[a + 1:b + 1].astype(np.float32), dtype=np.float32)))
        if modes[b] == km.M_NORMAL:
            bend.append(tr.vel[b, 1])
        if not ground[a]:
            for k in range(a + 1, b):
                if tr.fs[k] == 1 and abs(tr.vel[k - 1, 0]) > 0.5:
                    bdec.append(tr.vel[k, 0] / tr.vel[k - 1, 0])

    if bdec:
        f.set("bind_decay", _rnd(np.median(bdec), 4), len(bdec), "vx ratio per step in an air bind", min_n=5)
    for key, sign in (("bind_vy_cap", 1), ("bind_vy_cap_down", -1)):
        bcap = _caps(tr, modes, km.M_BIND, f.p.bind_decay, f.p.gravity, sign)
        if bcap:
            f.set(key, _rnd(np.median(bcap), 3), len(bcap),
                  f"|vy| at clipped air bind presses / decay ({'rising' if sign > 0 else 'falling'})", min_n=1)
    if bdur:
        f.set("bind_time", _rnd(np.median(bdur), 4), len(bdur), "Bind: scaled time relinquished", min_n=1)
        f.fit["bind_runs"] = {"value": [round(x, 4) for x in bdur], "n": len(bdur), "note": "scaled s per bind"}
    if bend:
        f.set("bind_end_vy", _rnd(np.median(bend), 3), len(bend), "vy in the first frame after a bind", min_n=1)
    lk = modes == km.M_LOCKED
    rat = []
    for k in np.flatnonzero(lk[1:] & lk[:-1]) + 1:
        if tr.fs[k] == 1 and abs(tr.vel[k - 1, 0]) > 0.5:
            rat.append(tr.vel[k, 0] / tr.vel[k - 1, 0])
    if rat:
        f.set("lock_decay", _rnd(np.median(rat), 4), len(rat), "vx ratio per step while another FSM holds control")


def fit_landing(tr: Trace, terrains: dict, f: Fit) -> None:
    g = tr.flag("onGround")
    on = np.flatnonzero(g & ~np.r_[False, g[:-1]])
    rest = f.p.skin + f.p.foot
    late, now = [], []
    for i in on:
        k = i - 1
        while k > 0 and tr.fs[k] == 0:
            k -= 1
        t = terrains.get(tr.scenes[tr.scene[i]])
        if t is None or len(t.hseg) == 0:
            continue
        cx = tr.phys[i, 0]
        under = (t.hseg[:, 1] < cx + f.p.half_width) & (t.hseg[:, 2] > cx - f.p.half_width) & \
            (t.hseg[:, 0] <= tr.box[i, 1] + 0.01)
        if not under.any():
            continue
        floor = t.hseg[under, 0].max()
        if abs(tr.phys[k, 1] - tr.phys[i, 1]) < 3e-3 and tr.vel[k, 1] < -1:     # parked a step before the contact
            k2 = k - 1
            while k2 > 0 and tr.fs[k2] == 0:
                k2 -= 1
            late.append(tr.phys[k2, 1] + (tr.vel[k2, 1] - f.p.gravity * FDT) * FDT - (floor + rest))
        else:
            now.append(tr.phys[k, 1] + (tr.vel[k, 1] - f.p.gravity * FDT) * FDT - (floor + rest))
    if late:
        lo, hi = min(late), max(late)
        f.set("land_slop_lo", _rnd(max(-lo + 5e-4, 0.0), 4), len(late), f"late contacts end in [{lo:.4f}, {hi:.4f}]")
        f.set("land_slop_hi", _rnd(hi + 5e-4, 4), len(late), "upper edge of the late-contact band")
        f.fit["landings"] = {"value": {"same_step": len(now), "next_step": len(late)}, "n": len(on),
                             "note": "contact resolved in the landing step vs the next one"}


def fit_input_lag(tr: Trace, f: Fit) -> None:
    """Human sessions only: frames between the "input" jump bit rising and hero_state turning airborne."""
    if tr.mask_source != "input":
        return
    # the trace already moved the jump bit by input_jump_lag; measure what is left
    jm = (tr.mask & km.B_JUMP) != 0
    air = tr.hero_state == 3
    lags = []
    for i in np.flatnonzero(jm & ~np.r_[False, jm[:-1]]):
        for k in range(i - 3, i + 4):
            if 0 < k < len(tr) and air[k] and not air[k - 1] and tr.flag("onGround")[k - 1]:
                lags.append(k - i)
                break
    if lags:
        c = Counter(lags)
        f.set("input_jump_lag", int(f.p.input_jump_lag - c.most_common(1)[0][0]), len(lags),
              f"residual jump-bit lag after the shift {_counts(c)}", min_n=5)


def _in_polygon(x: np.ndarray, y: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Even-odd rule, vectorised over points."""
    inside = np.zeros(len(x), dtype=bool)
    n = len(poly)
    for i in range(n):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        if ya == yb:
            continue
        cross = (ya > y) != (yb > y)
        xi = xa + (y - ya) * (xb - xa) / (yb - ya)
        inside ^= cross & (x < xi)
    return inside


def infer_scene_overrides(tr: Trace, terrain_msgs: dict, f: Fit) -> None:
    """Solids that were not what the room-entry dump says: on ones the hero box went through (disable), off closed
    ones whose faces stopped the hero (enable)."""
    from ssbot.oracle.messages import Terrain
    for name, msg in terrain_msgs.items():
        sel = tr.valid & np.array([tr.scenes[s] == name for s in tr.scene]) & np.isfinite(tr.box[:, 0])
        if not sel.any():
            continue
        b = tr.box[sel]
        t = Terrain.decode(msg)
        enable, disable = [], []
        for sol in t.solids:
            for sh in sol.shapes:
                if not sh.closed or len(sh.verts) < 3:
                    continue
                x0, y0 = sh.verts.min(axis=0)
                x1, y1 = sh.verts.max(axis=0)
                inside = _in_polygon(0.5 * (b[:, 0] + b[:, 2]), 0.5 * (b[:, 1] + b[:, 3]), sh.verts)
                yov = (b[:, 3] > y0) & (b[:, 1] < y1)
                touch = yov & ((np.abs(b[:, 2] - x0) < 0.03) | (np.abs(b[:, 0] - x1) < 0.03))
                if sol.on and inside.sum() > 10:
                    disable.append(sol.go)
                elif not sol.on and touch.sum() > 10 and not inside.any():
                    enable.append(sol.go)
        if enable or disable:
            cur = dict(f.p.scenes.get(name, {}))
            cur["enable"] = sorted(set(cur.get("enable", [])) | set(enable))
            cur["disable"] = sorted(set(cur.get("disable", [])) | set(disable))
            f.p.scenes[name] = cur
            f.fit[f"scene:{name}"] = {"value": cur, "n": int(sel.sum()), "note": "solids inferred from logged boxes"}
            f.source[f"scenes.{name}"] = "kin_fit: hero boxes against the room-entry TERRAIN dump"


def run_fit(sources: list[str], params: HeroParams) -> Fit:
    f = Fit(params)
    traces = []
    for src in sources:
        tr, terrains = load_source(src, params)
        traces.append((src, tr, terrains, _terrain_msgs(src)))
    f.fit["data"] = {"value": [{"source": s, "frames": len(t), "mask": t.mask_source} for s, t, _, _ in traces],
                     "n": sum(len(t) for _, t, _, _ in traces), "note": "traces used"}
    bot = [x for x in traces if x[1].mask_source == "act"] or traces
    # scene overrides from the bot runs only: a person's playthrough crosses rooms in every state (gates open and
    # closed, breakables broken or not), so its inferences would be guesses about rooms the bot has not played
    for src, tr, terrains, msgs in bot:
        infer_scene_overrides(tr, msgs, f)
    # the measurements run over the concatenated bot traces (the human ones only add the input lag)
    tr = _concat([t for _, t, _, _ in bot])
    terrains = {}
    for _, _, t, _ in bot:
        terrains.update(t)
    modes = km.classify_modes(tr)
    fit_box(tr, terrains, f)
    fit_motion(tr, modes, f)
    fit_motion(tr, modes, f)   # second pass with the fitted gravity / jump speed
    fit_recoil(tr, f)
    fit_downspike(tr, modes, f)
    fit_hurt(tr, modes, f)
    fit_casts(tr, modes, f)
    fit_landing(tr, terrains, f)
    for _, t, _, _ in traces:
        fit_input_lag(t, f)
    return f


def _terrain_msgs(src: str) -> dict:
    p = Path(src)
    out = {}
    if p.suffix == ".npz":
        return out
    if (p / "state.raw.zst").is_file():
        from ssbot.ipc.framing import MsgType
        from ssbot.tools.raw_session import messages
        for t, m in messages(p):
            if t == MsgType.TERRAIN and m.get("scene_raw"):
                out.setdefault(m["scene_raw"], m)
        return out
    from ssbot.record.recorder import RecordingReader
    for _, m in RecordingReader(p).terrain():
        if isinstance(m, dict) and m.get("scene_raw"):
            out.setdefault(m["scene_raw"], m)
    return out


def _concat(trs: list[Trace]) -> Trace:
    """Traces joined with a gap frame between them (window and step logic never spans the seam)."""
    if len(trs) == 1:
        return trs[0]
    from dataclasses import fields
    out = {}
    scenes: list = []
    clips: list = []
    spells: list = []
    parts = []
    def remap(names: list, table: list) -> np.ndarray:
        out = []
        for x in names:
            if x not in table:
                table.append(x)
            out.append(table.index(x))
        return np.array(out or [0], dtype=np.int32)

    for t in trs:
        sc, cl, sp = remap(t.scenes, scenes), remap(t.clips, clips), remap(t.spells, spells)
        d = {fl.name: getattr(t, fl.name) for fl in fields(t) if isinstance(getattr(t, fl.name), np.ndarray)}
        d["scene"], d["clip"], d["spell"] = sc[t.scene], cl[t.clip], sp[t.spell]
        d["valid"] = d["valid"].copy()
        d["valid"][0] = False
        parts.append(d)
    for k in parts[0]:
        out[k] = np.concatenate([p[k] for p in parts])
    return Trace(**out, clips=clips, spells=spells, scenes=scenes, mask_source=trs[0].mask_source)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--base", default=None, help="start from this params JSON instead of the prefab defaults")
    ap.add_argument("--out", default=str(km.DEFAULT_PARAMS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    params = HeroParams.load(a.base) if a.base else HeroParams()
    f = run_fit(a.sources, params)
    for k in HeroParams.VECTOR:
        f.source.setdefault(k, "decompiled HeroController / crest config (docs/facts/1.0.30000 hero_constants.json, "
                               "crests.json) or a code constant; not refitted")
    f.p.source = f.source
    f.p.fit = f.fit
    for k, v in f.fit.items():
        print(f"{k:24s} {json.dumps(v.get('value'))[:90]:90s} n={v.get('n')}  {v.get('note', '')[:70]}")
    if not a.dry_run:
        print("wrote", f.p.save(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
