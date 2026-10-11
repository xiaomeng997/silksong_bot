"""The Maestro's Tinies one by one (forum_planner_plan §5 R5 note): fit the defend orbit (angular rate, radius by
defend age) on some cached fights, measure the per-fly prediction error on others, and the charge (FIRE READY lead,
which fly is picked, direction, where a standing hero is hit).

    cd brain   # below-normal priority
    ..\\scripts\\uv.cmd run python -m ssbot.tools.tiny_orbit --fit C:/ssbot/data/m2_forum_r0/cache
        --fit C:/ssbot/data/m2_forum_r0/cache_fresh --test C:/ssbot/data/m2_forum_r1c/cache_fresh
        --out knowledge/1.0.30000/enemies/forum/tiny_orbit.json --json report.json

Defend episodes: a Maestro's Defend Start .. the end of its Defending; its flies are the Tinies whose Control went
Ready -> Defend Ready on the same frame (the Maestro's DEFEND READY). A fly's sample: its centre relative to the
Maestro's transform + (0, -0.22) (the Defense Formation), while it is in Defend Ready / Defend Buzz.
"""
import argparse
import ctypes
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat.tiny_orbit import CENTER_OFF, TinyOrbit
from ssbot.knowledge.forum_cache import load_cache

TINY, MAESTRO = "Song Automaton Tiny", "Song Pilgrim Maestro"
DEFEND = ("Defend Ready", "Defend Buzz")
CHARGE = ("Fire", "Brake", "Pull Up", "Wall Bonk")
HORIZONS = (0.1, 0.2, 0.3, 0.4, 0.6, 0.8)
AGE_BIN = 0.05
SETTLED_S = 1.0          # the flies are on the 5 u orbit from about 1 s after Defend Start (radius p1-p99 3.8-5.4)
GRID_DX = tuple(range(-8, 15))
HERO_HALF_W, HERO_H = 0.25, 2.08


def _below_normal() -> None:
    if os.name == "nt":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


class _Ent:
    def __init__(self, c: dict, sel: np.ndarray):
        o = np.argsort(c["e_fi"][sel], kind="stable")
        s = sel[o]
        self.fi, self.x, self.y = c["e_fi"][s], c["e_x"][s], c["e_y"][s]
        self.vx, self.vy, self.st, self.hid = c["e_vx"][s], c["e_vy"][s], c["e_st"][s], c["e_hidden"][s]
        self.box, self.flip = c["e_box"][s], c["e_flip"][s]
        self.pos = {int(f): k for k, f in enumerate(self.fi)}


def _ents(c: dict) -> tuple[dict, dict]:
    types = c["types"]
    order = np.argsort(c["e_iid"], kind="stable")
    iid_s = c["e_iid"][order]
    ents, tk = {}, {}
    for iid in np.unique(iid_s):
        sel = order[np.searchsorted(iid_s, iid):np.searchsorted(iid_s, iid, side="right")]
        t = types[int(c["e_tk"][sel[0]])]
        if t in (TINY, MAESTRO):
            ents[int(iid)], tk[int(iid)] = _Ent(c, sel), t
    return ents, tk


def _transitions(c: dict, tk: dict) -> list:
    fidx = {int(f): i for i, f in enumerate(c["f"])}
    out = []
    for f, k, d in c["events"]:
        if k != "fsm" or d.get("fsm") != "Control" or int(d.get("iid") or 0) not in tk:
            continue
        fi = fidx.get(int(f))
        if fi is not None and isinstance(d.get("to"), str):
            out.append((fi, int(d["iid"]), d.get("from"), d["to"]))
    return out


def scan(c: dict) -> dict:
    """Defend samples and charges of one cached fight."""
    T = c["T"]
    states = c["states"]
    ents, tk = _ents(c)
    tr = _transitions(c, tk)
    fight = c["meta"]["id"]
    # defend episodes
    starts = [(fi, iid) for fi, iid, a, b in tr if tk[iid] == MAESTRO and b == "Defend Start"]
    ends: dict[int, list] = defaultdict(list)
    for fi, iid, a, b in tr:
        if tk[iid] == MAESTRO and a in ("Defending", "Defend Start") and b != "Defending":
            ends[iid].append(fi)
    samples = []
    owner: dict[int, int] = {}
    for k, (fs, m) in enumerate(starts):
        fe = min([x for x in ends[m] if x > fs] or [len(T) - 1])
        flies = [iid for fi, iid, a, b in tr if tk[iid] == TINY and b == "Defend Ready" and abs(fi - fs) <= 1]
        for t in flies:
            owner[t] = m
        me = ents[m]
        for t in flies:
            te = ents[t]
            for fi in range(fs, fe + 1):
                j, q = te.pos.get(fi), me.pos.get(fi)
                if j is None or q is None or te.hid[j] or me.hid[q] or states[te.st[j]] not in DEFEND:
                    continue
                samples.append((f"{fight}#{k}", t, float(T[fi] - T[fs]), float(te.x[j]), float(te.y[j]),
                                float(me.x[q]), float(me.y[q]), float(me.vx[q]), float(me.vy[q]), float(T[fi]),
                                states[te.st[j]], int(me.flip[q])))
    # charges
    gy = float(np.nanpercentile(c["hbox"][:, 1], 2)) if len(c["hbox"]) else math.nan
    charges = []
    fire_antic = [(fi, iid) for fi, iid, a, b in tr if tk[iid] == MAESTRO and b == "Fire Antic"]
    for fi, iid, a, b in tr:
        if tk[iid] != TINY or b != "Fire Ready":
            continue
        te = ents[iid]
        m = next((mm for ff, mm in fire_antic if abs(ff - fi) <= 1), None)
        f_fire = next((x for x, i2, a2, b2 in tr if i2 == iid and b2 == "Fire" and x >= fi), None)
        f_end = next((x for x, i2, a2, b2 in tr if i2 == iid and x > (f_fire or fi) and b2 not in CHARGE), None)
        row = {"fight": fight, "tiny": iid, "maestro": m,
               "lead_s": None if f_fire is None else float(T[f_fire] - T[fi])}
        if m is not None:
            mine = [t for t, o in owner.items() if o == m]
            ready = []
            for t in set(mine) | {iid}:
                j = ents[t].pos.get(fi - 1) if fi > 0 else None
                if j is not None and states[ents[t].st[j]] == "Ready":
                    ready.append(t)
            row["n_ready"] = len(ready)
            hx = float(c["hx"][fi])
            if ready and iid in ready:
                d = {t: abs(float(ents[t].x[ents[t].pos[fi - 1]]) - hx) for t in ready}
                row["picked_nearest"] = min(d, key=d.get) == iid
            q = ents[m].pos.get(fi)
            row["maestro_x"] = None if q is None else float(ents[m].x[q])
        if f_fire is not None:
            j0 = te.pos.get(f_fire)
            j1 = te.pos.get(min(f_fire + 6, len(T) - 1))
            if j0 is not None and j1 is not None:
                dx, dy = float(te.x[j1] - te.x[j0]), float(te.y[j1] - te.y[j0])
                row["angle_deg"] = math.degrees(math.atan2(dy, dx))
                row["start"] = (float(te.x[j0]), float(te.y[j0]))
                row["hero_side"] = 1 if float(c["hx"][f_fire]) >= float(te.x[j0]) else -1
                row["dir"] = 1 if dx >= 0 else -1
                row["hero_dx"] = float(c["hx"][f_fire]) - float(te.x[j0])
                row["hero_dy"] = float(c["hy"][f_fire]) - float(te.y[j0])
            if f_end is not None and not math.isnan(gy):
                boxes = []
                for fj in range(f_fire, f_end + 1):
                    j = te.pos.get(fj)
                    if j is not None and not math.isnan(te.box[j][0]):
                        boxes.append(tuple(float(v) for v in te.box[j]))
                row["min_y"] = min((b[1] for b in boxes), default=None)
                row["boxes"] = boxes
                row["ground_y"] = gy
                row["dur_s"] = float(T[f_end] - T[f_fire])
        charges.append(row)
    return {"samples": samples, "charges": charges}


def _rel(s) -> tuple[float, float, float]:
    cx, cy = s[5] + CENTER_OFF[0], s[6] + CENTER_OFF[1]
    return math.hypot(s[3] - cx, s[4] - cy), math.atan2(s[4] - cy, s[3] - cx), cx


def fit(samples: list) -> tuple[TinyOrbit, dict]:
    by = defaultdict(list)
    for s in samples:
        by[(s[0], s[1])].append(s)
    rates = {0: [], 1: []}
    for seq in by.values():
        seq.sort(key=lambda s: s[9])
        for a, b in zip(seq, seq[1:]):
            dt = b[9] - a[9]
            if 0 < dt <= 0.05 and a[2] >= SETTLED_S and a[10] == b[10] == "Defend Buzz" and a[11] == b[11]:
                d = _rel(b)[1] - _rel(a)[1]
                d = (d + math.pi) % (2 * math.pi) - math.pi
                rates[a[11]].append(math.degrees(d) / dt)
    omega = {k: float(np.median(v)) if v else (-180.0 if k == 0 else 180.0) for k, v in rates.items()}
    bins = defaultdict(list)
    for s in samples:
        bins[int(s[2] / AGE_BIN)].append(_rel(s)[0])
    r_age = [[round((k + 0.5) * AGE_BIN, 3), round(float(np.median(v)), 4)] for k, v in sorted(bins.items())
             if len(v) >= 20]
    xs = np.array([s[3] for s in samples])
    ys = np.array([s[4] for s in samples])
    bounds = tuple(round(float(v), 3) for v in (np.percentile(xs, 0.05), np.percentile(xs, 99.95),
                                                np.percentile(ys, 0.05), np.percentile(ys, 99.95)))
    orb = TinyOrbit(omega, r_age, bounds=bounds)
    orb.margin_u = {}
    return orb, {"omega_deg_s": {k: round(v, 2) for k, v in omega.items()},
                 "omega_p25_p75": {k: [round(float(x), 2) for x in np.percentile(v, [25, 75])] for k, v in
                                   rates.items() if v},
                 "rate_samples": {k: len(v) for k, v in rates.items()}, "samples": len(samples), "bounds": bounds}


def evaluate(orb: TinyOrbit, samples: list, every: int = 2) -> dict:
    by = defaultdict(list)
    for s in samples:
        by[(s[0], s[1])].append(s)
    err = defaultdict(list)
    for seq in by.values():
        seq.sort(key=lambda s: s[9])
        Ts = np.array([s[9] for s in seq])
        for i in range(0, len(seq), every):
            s = seq[i]
            for h in HORIZONS:
                j = int(np.searchsorted(Ts, s[9] + h - 1e-4))
                if j >= len(seq) or abs(Ts[j] - (s[9] + h)) > 0.02:
                    continue
                p = orb.predict((s[3], s[4]), (s[5], s[6]), (s[7], s[8]), s[2], [Ts[j] - s[9]], s[11])[0]
                band = "settled" if s[2] >= SETTLED_S and s[10] == "Defend Buzz" else "forming"
                e = math.hypot(p[0] - seq[j][3], p[1] - seq[j][4])
                err[(band, h)].append(e)
                err[("all", h)].append(e)
    out = {}
    for (band, h), v in sorted(err.items()):
        a = np.array(v)
        out.setdefault(band, {})[str(h)] = {"n": int(len(a)), "p50": round(float(np.median(a)), 3),
                                            "p99": round(float(np.percentile(a, 99)), 3),
                                            "max": round(float(a.max()), 3)}
    return out


def charge_report(charges: list) -> dict:
    lead = [r["lead_s"] for r in charges if r.get("lead_s") is not None]
    ang = [r["angle_deg"] for r in charges if "angle_deg" in r]
    toward = [r["dir"] == r["hero_side"] for r in charges if "dir" in r]
    picks = [r for r in charges if r.get("n_ready") and "picked_nearest" in r]
    nr = Counter(r["n_ready"] for r in picks)
    exp_near = sum(1.0 / r["n_ready"] for r in picks)
    # where a standing hero is hit: hero box at x offsets from the Maestro (charge direction positive), on the ground
    grid_m, grid_s = Counter(), Counter()
    n_m = n_s = 0
    for r in charges:
        if not r.get("boxes") or "dir" not in r:
            continue
        g0 = r["ground_y"]
        for ref, grid in ((r.get("maestro_x"), grid_m), (r["start"][0], grid_s)):
            if ref is None:
                continue
            for dxo in GRID_DX:
                px = ref + r["dir"] * dxo
                hb = (px - HERO_HALF_W, g0, px + HERO_HALF_W, g0 + HERO_H)
                if any(b[0] <= hb[2] and b[2] >= hb[0] and b[1] <= hb[3] and b[3] >= hb[1] for b in r["boxes"]):
                    grid[dxo] += 1
        n_m += r.get("maestro_x") is not None
        n_s += 1
    pct = lambda v: [round(float(x), 3) for x in np.percentile(v, [1, 5, 50, 95, 99])] if v else None  # noqa: E731
    return {"n": len(charges), "lead_s_p1_5_50_95_99": pct(lead),
            "angle_deg_p1_5_50_95_99": pct([abs(a) if abs(a) <= 90 else 180 - abs(a) for a in ang]),
            "angle_below_horizontal": sum(1 for a in ang if a < 0), "angle_n": len(ang),
            "toward_hero_side": [sum(toward), len(toward)],
            "pick": {"n": len(picks), "n_ready": dict(nr), "picked_nearest_to_hero": sum(r["picked_nearest"] for r in
                                                                                         picks),
                     "expected_if_random": round(exp_near, 1)},
            "hit_standing_from_maestro_x": {"n": n_m, "share": {d: round(grid_m[d] / n_m, 4) for d in GRID_DX} if n_m
                                            else {}},
            "hit_standing_from_start_x": {"n": n_s, "share": {d: round(grid_s[d] / n_s, 4) for d in GRID_DX} if n_s
                                          else {}},
            "duration_s_p50_95": pct([r["dur_s"] for r in charges if r.get("dur_s") is not None])}


def _collect(dirs: list[Path], max_fights: int = 0) -> dict:
    out = {"samples": [], "charges": []}
    paths = [p for d in dirs for p in sorted(Path(d).glob("*.npz")) if not p.name.endswith(".hero.npz")]
    for p in paths[:max_fights or None]:
        r = scan(load_cache(p))
        out["samples"] += r["samples"]
        out["charges"] += r["charges"]
        print(f"{p.name}: {len(r['samples'])} samples, {len(r['charges'])} charges", flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fit", type=Path, action="append", required=True)
    ap.add_argument("--test", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--max-fights", type=int, default=0)
    a = ap.parse_args(argv)
    _below_normal()
    tr = _collect(a.fit, a.max_fights)
    orb, info = fit(tr["samples"])
    rep = {"fit": info, "train_error": evaluate(orb, tr["samples"]), "charge_train": charge_report(tr["charges"])}
    if a.test:
        te = _collect(a.test, a.max_fights)
        rep["test_error"] = evaluate(orb, te["samples"])
        rep["charge_test"] = charge_report(te["charges"])
        orb.margin_u = {str(h): v["max"] for h, v in rep["test_error"].get("settled", {}).items()}
    a.out.write_text(json.dumps({"omega_deg_s": {str(k): v for k, v in orb.omega_deg_s.items()}, "r_age": orb.r_age,
                                 "center_off": list(orb.center_off), "bounds": list(orb.bounds),
                                 "margin_u": orb.margin_u, "fit": info,
                                 "note": "ssbot.tools.tiny_orbit; scoring only until held-out containment is 100 %"},
                                indent=1), "utf-8")
    a.json.write_text(json.dumps(rep, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "train_error"}, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
