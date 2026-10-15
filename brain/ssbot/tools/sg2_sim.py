"""Task 1v1 SG2: closed-loop simulation of the score map (ssbot.combat.special_map; forum.md 56). No planner, no game.

A one-step lookahead on the map (the person's online rule S8: step the model for each input possible now, read the
next node's score, subtract lambda per key change, take the best; press the slash at a strike cell; never jump without
a reachable strike) drives the hero (SG1's macros: exact run steps and vertical profiles per physics phase) against the
slam's REAL boxes of one timing variant at a time (not the union, no dilation): the contact with the real polygon
(the alternation drawn at random), the bounce from the real contact height, the i-frames and PRE_PROTECT_F, and the
damage with the undilated hero box. Execution noise as measured live: the hero off the lattice (uniform +- half a
cell), 20 % of key changes and presses one frame late.

    ../scripts/uv.cmd run python -m ssbot.tools.sg2_sim [--out C:/ssbot/data/m2_map/sg2] [--quick] [--lams 0,0.02,0.05,0.1]

Writes <out>/sim.json (+ sim_rows.jsonl) and <out>/sim_rollout_check.json (a sample replayed through the full
kinematics rollout: the hero box per frame against the macro model, and the damage verdict on the rollout's boxes).
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.combat import special_map as sm
from ssbot.combat.hero_macros import IFRAMES, key_mask
from ssbot.combat.pogo_model import ACTIVE, slash_poly
from ssbot.combat.pogo_slam import CX, PRE_PROTECT_F, clip_band
from ssbot.knowledge import kinematics as kin
from ssbot.tools.special_map_build import OUT, setup

LATE_P = 0.20


@dataclass
class Ep:
    start: str
    k0: int
    x0: float
    variant: str
    p: int
    lam: float
    hits: int = 0
    contacts: list = field(default_factory=list)
    presses: list = field(default_factory=list)
    overlaps: list = field(default_factory=list)
    key_changes: int = 0
    damage_f: int = -1
    damage_src: str = ""
    readiness: float = float("nan")
    x_start: float = 0.0
    d0: int = 0
    misses: int = 0
    noise_free_damage: int | None = None
    masks: list = field(default_factory=list)       # per frame from k0 + 1: (dir, jump held, attack)
    trace: list = field(default_factory=list)       # per frame: (k, x, y)


class Sim:
    def __init__(self, geo: sm.Geometry, pm: sm.PhaseMap, rng: np.random.Generator):
        self.g, self.pm, self.rng = geo, pm, rng
        self.p = pm.p
        self.st = geo.steps(self.p)
        self.hm = geo.hm
        self.tube_of = {("jump", t.param): i for i, t in enumerate(geo.tubes) if t.kind == "jump"}
        self.jump_h = [t.param for t in geo.tubes if t.kind == "jump"]
        self.polys = [slash_poly(f, a) for f in (1, -1) for a in (False, True)]
        self.late_p, self.offset = LATE_P, True       # execution noise (off: the attribution replays)

    # ---- the map lookups ----
    def slice_of(self, ev: dict, j: int) -> int:
        g = self.g
        if ev["kind"] == "ground":
            return 0
        if ev["kind"] == "jump":
            t = g.tubes[self.tube_of[("jump", ev["h"])]]
        else:
            cb = int(np.clip(np.floor(ev["yc"] / g.cfg.cb_w), 0, g.ncb - 1))
            t = g.tubes[g.ST[g.bounce0[cb]]]
        return t.s0 + j if j < t.n else -1

    def S(self, k: int, s: int, x: float) -> float:
        if s < 0 or not 0 <= k < self.g.K:
            return -np.inf
        xi = int(np.rint((x - self.g.cfg.x_lo) / self.g.step))
        if not 0 <= xi < self.g.NX:
            return -np.inf
        return float(self.pm.S[k, s, xi])

    def SV(self, k: int, s: int, x: float, d: int) -> float:
        if s < 0 or not 0 <= k < self.g.K:
            return -np.inf
        xi = int(np.rint((x - self.g.cfg.x_lo) / self.g.step))
        if not 0 <= xi < self.g.NX:
            return -np.inf
        return float(self.pm.SV[k, s, xi, d + 1])

    # ---- the hero's vertical per event ----
    def prof(self, ev: dict):
        """(y box bottom above the floor, rendered y offset, landing index) of the event from its start."""
        hm = self.hm
        if ev["kind"] == "jump":
            p = hm.jumps[(ev["h"], ev["q0"])]
            return p.y, p.py, p.land
        if ev["kind"] == "bounce":
            b = hm.bounces[ev["q0"]]
            y = ev["yc"] + b.y
            below = np.flatnonzero(y[b.apex:] <= 0.0)
            return y, b.py, b.apex + int(below[0])
        return None

    def run(self, tl, start: str, k0: int, x0: float, ev0: dict, lam: float, d0: int = 0, debug: list | None = None) -> Ep:
        g, rng, hm = self.g, self.rng, self.hm
        pa = g.spec.pos_above_floor
        e = Ep(start, k0, x0, tl.name, self.p, lam)
        x = x0 + (rng.uniform(-0.5, 0.5) * g.step if self.offset else 0.0)
        e.x_start, e.d0 = x, d0
        ev = dict(ev0)
        dir_cur = d0                       # input read in the current frame (moves in the next)
        dir_pending = None                 # a late key change
        facing = 1 if x0 < 0 else -1       # toward the Clapper
        if d0:
            facing = d0
        last_press = -100
        press_pending = None               # (frame, dir) of a late press
        slash = None                       # active slash: press frame, facing, alt
        last_step_d = 0
        kend = min(g.K - 3, tl.end_k + 25)
        e.readiness = self.S(k0, self.slice_of(ev, k0 - ev["k"]) if ev["kind"] != "ground" else 0, x)
        k = k0
        while k < kend:
            j = k - ev["k"]
            # ---- the policy at the end of frame k: inputs for frame k + 1
            jump_now, press_now = None, False
            if slash is None and press_pending is None:
                s_now = self.slice_of(ev, j) if ev["kind"] != "ground" else 0
                x1 = x + dir_cur * g.step * self.st[k + 1]
                cands = []
                if ev["kind"] == "ground":
                    for d in (-1, 0, 1):
                        x2 = x1 + d * g.step * self.st[k + 2]
                        cands.append((self.S(k + 2, 0, x2) - lam * (d != dir_cur), ("dir", d)))
                    for h in self.jump_h:
                        s2 = self.g.tubes[self.tube_of[("jump", h)]].s0 + 2
                        best = -np.inf
                        for d in (-1, 0, 1):
                            x2 = x1 + d * g.step * self.st[k + 2]
                            best = max(best, self.S(k + 2, s2, x2) - lam * (d != dir_cur))
                        if best > g.cfg.wc + 1e-3:            # a reachable strike (R > 0): never jump without one
                            cands.append((best - lam, ("jump", h)))
                else:
                    _, _, land = self.prof(ev)
                    s1 = self.slice_of(ev, j + 1) if j + 1 < land else -1
                    for d in (-1, 0, 1):
                        x2 = x1 + d * g.step * self.st[k + 2]
                        s2 = self.slice_of(ev, j + 2) if j + 2 < land else 0
                        v = self.S(k + 2, s2, x2)
                        # the input read now is the key a strike pressed from the next node holds (input latency):
                        # that strike's value belongs to this key
                        if s1 >= 0 and k + 2 - last_press >= 19:
                            v = max(v, self.SV(k + 1, s1, x1, d))
                        cands.append((v - lam * (d != dir_cur), ("dir", d)))
                    if k + 1 - last_press >= 19 and s_now >= 0:
                        sv = self.SV(k, s_now, x, dir_cur)
                        if np.isfinite(sv) and sv >= self.S(k, s_now, x) - 1e-2:
                            cands.append((np.inf, ("press", dir_cur)))
                if cands:
                    v, act = max(cands, key=lambda c: c[0])
                    if debug is not None:
                        debug.append((k, round(x, 3), ev["kind"], j, dir_cur, [(round(float(c[0]), 3), c[1]) for c in cands], act))
                    if not np.isfinite(v) and v < 0:              # nothing feasible: retreat on the ground
                        act = ("dir", 1 if x >= 0 else -1) if ev["kind"] == "ground" else ("dir", dir_cur)
                    if act[0] == "dir" and act[1] != dir_cur:
                        if rng.random() < self.late_p:
                            dir_pending = act[1]
                        else:
                            dir_cur_next = act[1]
                            e.key_changes += 1
                            dir_pending = ("now", dir_cur_next)
                    elif act[0] == "jump":
                        jump_now = act[1]
                        e.key_changes += 1
                    elif act[0] == "press":
                        e.key_changes += 1
                        press_pending = (k + 1 + (1 if rng.random() < self.late_p else 0), dir_cur)
            # ---- frame k + 1
            new_dir = dir_cur
            if isinstance(dir_pending, tuple):
                new_dir, dir_pending = dir_pending[1], None
            elif dir_pending is not None:                         # the late change lands one frame later
                dir_pending = ("now", dir_pending)
                e.key_changes += 1
            # the body moves in frame k + 1 by the input read in frame k (dir_cur)
            if self.st[k + 1]:
                x += dir_cur * g.step
                last_step_d = dir_cur
            if jump_now is not None:
                late = rng.random() < self.late_p
                ev = {"kind": "jump", "h": jump_now, "k": k + (1 if late else 0), "q0": (self.p - k - (1 if late else 0)) % 6}
            dir_cur = new_dir
            if dir_cur:
                facing = dir_cur
            k += 1
            j = k - ev["k"]
            # vertical
            if ev["kind"] != "ground":
                y_arr, py_arr, land = self.prof(ev)
                if j >= land:
                    ev = {"kind": "ground", "k": k}
                    y, py = 0.0, hm.jumps[(1, 0)].py[0]
                else:
                    y, py = float(y_arr[j]), float(py_arr[j])
            else:
                y, py = 0.0, hm.jumps[(1, 0)].py[0]
            e.masks.append((dir_cur, 1 if (ev["kind"] == "jump" and 1 <= j <= ev["h"]) else 0,
                            1 if (press_pending is not None and press_pending[0] == k) else 0))
            e.trace.append((k, round(x, 4), round(y, 4)))
            # the press
            if press_pending is not None and press_pending[0] == k:
                if ev["kind"] != "ground":
                    slash = {"P": k, "face": facing, "alt": bool(rng.random() < 0.5)}
                    last_press = k
                    e.presses.append(k)
                press_pending = None
            # the contact
            if slash is not None:
                i = k - slash["P"]
                if ev["kind"] == "ground" or i > ACTIVE[1]:
                    e.misses += 1
                    slash = None
                elif i >= ACTIVE[0]:
                    lag = hm.lag[self.p, 12 + (k - 12) % 6]
                    xr = x - lag * last_step_d * g.step
                    yr = y + py
                    poly = slash_poly(slash["face"], slash["alt"])
                    hit = False
                    for t in tl.targets(k):
                        r = clip_band(poly, t[2] + pa - yr, t[3] + pa - yr)
                        if r is not None and t[0] - r[1] < xr < t[1] - r[0]:
                            hit = True
                            break
                    if hit:
                        e.contacts.append(k)
                        ev = {"kind": "bounce", "yc": y, "k": k, "q0": (self.p - k) % 6}
                        slash = None
            # damage (the undilated box; the i-frames / pre-protect are applied at the end)
            for b in tl.damage(k):
                if b[0] < x + g.hw and b[1] > x - g.hw and b[2] + pa < y + g.H and b[3] + pa > y:
                    e.overlaps.append(k)
                    break
        # the damage events: overlaps not covered by a contact's [c - PRE_PROTECT_F, c + 8]
        for f in e.overlaps:
            if not any(c - PRE_PROTECT_F <= f <= c + IFRAMES[1] for c in e.contacts):
                e.damage_f = f
                break
        e.hits = sum(1 for c in e.contacts if e.damage_f < 0 or c < e.damage_f)
        return e


def starts(quick: bool) -> list[tuple]:
    out = []
    ks = (0, 10, 20, 30, 40) if not quick else (0, 30)
    xs = [x for x in np.arange(-8.0, 13.01, 1.0) if abs(x) >= 2.5] if not quick else [-3.0, 3.0, 4.0, 6.0, 10.0]
    for k0 in ks:
        for x0 in xs:
            out.append(("ground", k0, float(x0), {"kind": "ground", "k": k0}, 0))
    for x0 in ((3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 13.0) if not quick else (4.0, 10.0)):   # the antic entry
        for d0 in (-1, 0):
            out.append(("antic_entry", 0, x0, {"kind": "ground", "k": 0}, d0))
    for h in ((3, 4, 6) if not quick else (4,)):                                       # after a small-rune hop
        for jj in (2, 6, 10):
            for x0 in (2.5, 3.5, 4.5, 6.0):
                out.append((f"hop_h{h}", 0, x0, {"kind": "jump", "h": h, "k": -jj}, 0))
    for yc in ((4.3, 4.6) if not quick else (4.6,)):                                   # after a bounce on its head
        for jj in (0, 6, 12):
            for x0 in (-1.0, 0.0, 1.0):
                out.append((f"bounce_{yc}", 0, x0, {"kind": "bounce", "yc": yc, "k": -jj}, 0))
    return out


def sim_variants(geo: sm.Geometry, quick: bool):
    vs = []
    for a in ((47, 48, 49) if not quick else (47, 49)):
        for s0 in (4, 5):
            for s2 in (5, 6):
                for ph in (0.2, 0.8):
                    vs.append(geo.spec.timeline({"Slam Antic": a, "Slam 0": s0, "Slam 2": s2}, ph, K=geo.K + 20))
    return vs


def rollout_check(geo: sm.Geometry, eps: list[Ep], tls: dict, n: int, rng) -> dict:
    """Replay ground-start episodes through kin.rollout (the sim's inputs, EV_POGO on the sim's contacts): the hero
    box per frame against the macro model's, and the damage verdict on the rollout's own boxes and i-frame flags."""
    hm = geo.hm
    pa = geo.spec.pos_above_floor
    sel = [e for e in eps if e.start in ("ground", "antic_entry")]
    if not sel:
        return {}
    pick = rng.choice(len(sel), size=min(n, len(sel)), replace=False)
    errs, same_dmg, rows = [], 0, 0
    for i in pick:
        e = sel[int(i)]
        T = len(e.masks)
        m = np.zeros((1, T), np.int64)
        ev = np.zeros((1, T), np.int64)
        for t, (d, jh, att) in enumerate(e.masks):
            m[0, t] |= key_mask(d) | (kin.B_JUMP if jh else 0)
            if att:
                m[0, t] |= kin.B_ATTACK
                m[0, max(t - 3, 0):t + 3] |= kin.B_DOWN
        for c in e.contacts:
            if 1 <= c - e.k0 <= T:
                ev[0, c - e.k0 - 1] = kin.EV_POGO
        S = kin.initial_state(hm.params, CX + e.x_start, hm.stand_py, vx=e.d0 * hm.params.run_speed,
                              facing=e.d0 or 1, ground=True, alpha=((((e.p - e.k0) % 6) - 0.5) / 6) % 1.0)
        S[kin.MOVE] = e.d0
        S[kin.PREV] = key_mask(e.d0)
        ro = kin.rollout(S, m, hm.params, hm.terrain, events=ev)
        bx = (ro.box[0, 1:, 0] + ro.box[0, 1:, 2]) / 2 - CX
        by = ro.box[0, 1:, 1] - hm.stand_y0
        sx = np.array([t[1] for t in e.trace])
        sy = np.array([t[2] for t in e.trace])
        errs.append(float(np.max(np.abs(np.r_[bx - sx, by - sy]))))
        tl = tls[e.variant]
        first = -1
        for t in range(T):
            k = e.k0 + 1 + t
            if ro.flags[0, t + 1] & kin.F_INVULN:
                continue
            if any(c - PRE_PROTECT_F <= k < c for c in e.contacts):
                continue
            x0, y0, x1, y1 = ro.box[0, t + 1]
            for b in tl.damage(k):
                if b[0] + CX < x1 and b[1] + CX > x0 and b[2] + pa + hm.stand_y0 < y1 and b[3] + pa + hm.stand_y0 > y0:
                    first = k
                    break
            if first >= 0:
                break
        same_dmg += int((first >= 0) == (e.damage_f >= 0))
        rows += 1
    a = np.array(errs)
    return {"n": rows, "max_err_u_p50": round(float(np.median(a)), 3), "max_err_u_p90": round(float(np.quantile(a, 0.9)), 3),
            "max_err_u_max": round(float(a.max()), 3), "share_le_0.05": round(float((a <= 0.05).mean()), 3),
            "damage_verdict_agree": round(same_dmg / max(rows, 1), 3)}


def summarize(eps: list[Ep]) -> dict:
    out = {}
    groups = {}
    for e in eps:
        g = e.start.split("_h")[0].split("_4")[0] if e.start.startswith(("hop", "bounce")) else e.start
        groups.setdefault(g, []).append(e)
    groups["all"] = eps
    for nm, es in groups.items():
        n = len(es)
        reach = sum(1 for e in es if e.hits > 0 and e.damage_f < 0)
        dmg = sum(1 for e in es if e.damage_f >= 0)
        out[nm] = {"n": n, "strike_no_damage": round(reach / n, 3), "damage_eps": dmg,
                   "hits_per_slam": round(sum(e.hits for e in es) / n, 3),
                   "two_hits": round(sum(1 for e in es if e.hits >= 2 and e.damage_f < 0) / n, 3),
                   "key_changes_per_slam": round(sum(e.key_changes for e in es) / n, 2),
                   "presses_per_slam": round(sum(len(e.presses) for e in es) / n, 3),
                   "misses": sum(e.misses for e in es)}
    return out


def readiness_table(eps: list[Ep]) -> list[dict]:
    rows = []
    bins = [(-np.inf, -np.inf), (0.0, 0.31), (0.31, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 10.0)]
    for lo, hi in bins:
        if np.isneginf(lo):
            es = [e for e in eps if np.isneginf(e.readiness)]
            lab = "infeasible"
        else:
            es = [e for e in eps if lo <= e.readiness < hi]
            lab = f"[{lo:g}, {hi:g})"
        if es:
            rows.append({"readiness": lab, "n": len(es),
                         "strike_no_damage": round(sum(1 for e in es if e.hits and e.damage_f < 0) / len(es), 3),
                         "damage": round(sum(1 for e in es if e.damage_f >= 0) / len(es), 3),
                         "hits_per_slam": round(sum(e.hits for e in es) / len(es), 3)})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--lams", default="0,0.02,0.05,0.1")
    ap.add_argument("--lam", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=56)
    ap.add_argument("--phases", default="0-5")
    a = ap.parse_args(argv)
    t0 = time.time()
    rng = np.random.default_rng(a.seed)
    geo = setup()
    b = sm.MapBuilder(geo)
    vs = sim_variants(geo, a.quick)
    st = starts(a.quick)
    lo, hi = (int(v) for v in a.phases.split("-"))
    eps, lam_eps = [], []
    lams = [float(v) for v in a.lams.split(",")]
    for p in range(lo, hi + 1):
        pm = b.build(p, keep_full=True)
        sim = Sim(geo, pm, rng)
        for tl in vs:
            for (nm, k0, x0, ev0, d0) in st:
                ev = dict(ev0)
                if ev["kind"] != "ground":
                    ev["q0"] = (p - ev["k"]) % 6
                eps.append(sim.run(tl, nm, k0, x0, ev, a.lam, d0))
        # attribution: every damage episode from a feasible start replayed without execution noise (no late keys
        # or presses, on the lattice): damage that stays is a map / policy limit, damage that goes is the noise
        sim.late_p, sim.offset = 0.0, False
        for e in [e for e in eps if e.p == p and e.damage_f >= 0 and np.isfinite(e.readiness)]:
            tl = next(v for v in vs if v.name == e.variant)
            st0 = next(s_ for s_ in st if s_[0] == e.start and s_[1] == e.k0 and s_[2] == e.x0 and s_[4] == e.d0)
            ev = dict(st0[3])
            if ev["kind"] != "ground":
                ev["q0"] = (p - ev["k"]) % 6
            e2 = sim.run(tl, e.start, e.k0, e.x0, ev, a.lam, e.d0)
            e.noise_free_damage = e2.damage_f
        sim.late_p, sim.offset = LATE_P, True
        if p == lo:                                               # the lambda sweep on one phase
            for lam in lams:
                for tl in vs[::3]:
                    for (nm, k0, x0, ev0, d0) in st:
                        ev = dict(ev0)
                        if ev["kind"] != "ground":
                            ev["q0"] = (p - ev["k"]) % 6
                        lam_eps.append(sim.run(tl, nm, k0, x0, ev, lam, d0))
        del pm, sim
    res = {"seconds": round(time.time() - t0, 1), "episodes": len(eps), "variants": [v.name for v in vs],
           "lam": a.lam, "summary": summarize(eps), "readiness_k0": readiness_table(
               [e for e in eps if e.start in ("ground", "antic_entry") and e.k0 == 0]),
           "readiness_all": readiness_table(eps)}
    res["lambda_sweep"] = {f"{lam:g}": summarize([e for e in lam_eps if e.lam == lam])["all"] for lam in lams}
    def ex(e):
        return {"start": e.start, "k0": e.k0, "x0": e.x0, "variant": e.variant, "p": e.p, "lam": e.lam,
                "damage_f": e.damage_f, "contacts": e.contacts, "presses": e.presses, "misses": e.misses,
                "readiness": e.readiness, "noise_free_damage": e.noise_free_damage,
                "trace": [t for t in e.trace if e.damage_f < 0 or e.damage_f - 15 <= t[0] <= e.damage_f + 1]}
    dm = [e for e in eps + lam_eps if e.damage_f >= 0]
    res["damage_examples"] = [ex(e) for e in dm[:60]]
    feas = [e for e in eps if e.damage_f >= 0 and np.isfinite(e.readiness)]
    res["feasible_start_damage"] = {"n": len(feas), "of": sum(1 for e in eps if np.isfinite(e.readiness)),
                                    "noise_free_still_damage": sum(1 for e in feas if e.noise_free_damage is not None and e.noise_free_damage >= 0),
                                    "examples": [ex(e) for e in feas[:40]]}
    res["miss_examples"] = [ex(e) for e in eps + lam_eps if e.misses][:30]
    res["rollout_check"] = rollout_check(geo, eps, {v.name: v for v in vs}, 200, rng)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / ("sim_quick.json" if a.quick else "sim.json")).write_text(json.dumps(res, indent=1, default=float), "utf-8")
    print(json.dumps({k: res[k] for k in ("seconds", "episodes", "summary", "readiness_k0", "lambda_sweep",
                                          "rollout_check")}, indent=1, default=float))
    print("feasible-start damage", {k: v for k, v in res["feasible_start_damage"].items() if k != "examples"})
    print("damage episodes", len(dm))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
