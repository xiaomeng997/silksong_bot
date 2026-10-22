"""Map v2 stage M2: the Clapper model's data, fit and validation (docs/plans/forum_map_v2.md section 1 L1, 1b and
section 2 M2; forum.md section 93). Offline only: the bot does not import this or ssbot.map2.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m2_clapper extract --set fit|held [--jobs 6]
        # the recorded episodes of the manifests (SP13 .. SP-AIR1, w7 and w13) -> per-episode traces (pickles) in
        # C:/ssbot/data/m2_play/map2/m2/cache/<set>/
    ../scripts/uv.cmd run python -m ssbot.tools.m2_clapper fit        # the timelines / facts -> knowledge json
    ../scripts/uv.cmd run python -m ssbot.tools.m2_clapper validate --set held [--ks 0,6,12,36,60]

The trace of an episode (extract_episode): per STATE frame the hero (transform, physics box, velocity, hp, the cstate
bits of her HeroBox kind, invulnerable), per Clapper (its iid) its Control state and time in state, transform,
velocity, facing (+1 right), hp, animation clip / frame, the root box (body: DamageHero + hurtbox) and the hammer
polygons (Slam Collider 1 / 2 while enabled), the Slam Range trigger box; the small-rune bombs and the big rune circle
(centre, r, lit); the Control transitions (iid, from, to, frame, seconds in the previous state), the hero's hits on a
Clapper, the hero's damage / damage_blocked / hp events with their sources.

Frames are the recording's STATE frames (one per rendered 60 fps frame at 1.0x); u are world units (centre to centre
unless stated).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

CLAPPER = "Song Heavy Sentry"
DATA = Path(r"C:\ssbot\data\m2_play\map2\m2")
SANDBOX = Path(r"C:\ssbot\sandbox")
# the recorded episodes (the manifests of the live blocks): fit = SP13 / SP13b / SP-AIR1 b4-b10, held = SP14 /
# SP-AIR1 b11-b16, old = SP8 .. SP12 (the held-out sets are only evaluated, never fitted)
SETS = {
    "fit": ["1v1sp13_ab1", "1v1sp13_fp1", "1v1sp13b_ab1", "1v1sp13b_ab2", "1v1sp13b_w7chk", "1v1air1_b4",
            "1v1air1_b5", "1v1air1_b6", "1v1air1_b8", "1v1air1_b9", "1v1air1_b10"],
    "held": ["1v1sp14_ab1", "1v1sp14_ab2", "1v1sp14_w7chk", "1v1air1_b11", "1v1air1_b12", "1v1air1_b13",
             "1v1air1_b14", "1v1air1_b15", "1v1air1_b16"],
    # a second held-out set: the older stages SP8 .. SP12 (other scripts, the same Clapper)
    "old": ["1v1sp8ab2", "1v1sp10cab7", "1v1sp10cab13", "1v1sp11ab1", "1v1sp12a_ab1", "1v1sp12b_ab1"],
}
HERO_BITS = ("onGround", "downSpiking", "invulnerable", "recoiling", "downSpikeBouncing")


def manifest_rows(names: list[str]) -> list[tuple[str, str, int, Path]]:
    """(manifest, arm, instance, run dir) of the named manifests (C:/ssbot/sandbox/<name>_manifest.txt)."""
    out = []
    for nm in names:
        p = SANDBOX / f"{nm}_manifest.txt"
        for line in p.read_text("utf-8-sig").splitlines():
            parts = line.strip().split("\t")
            if len(parts) < 4:
                continue
            out.append((nm, parts[0], int(parts[2]), Path(parts[3].strip())))
    return out


def _cs_idx() -> dict:
    from ssbot.knowledge import kinematics as kin
    names = kin.cstate_names()
    return {n: names.index(n) for n in HERO_BITS if n in names}


def _bit(cs, i: int) -> bool:
    return bool(cs) and bool((int(cs[i >> 6]) >> (i & 63)) & 1)


def _verts(c: dict) -> np.ndarray | None:
    v = c.get("verts_world")
    if not v or len(v) < 6:
        return None
    return np.asarray(v, np.float64).reshape(-1, 2)


def _is_root(nm: str) -> bool:
    return nm == CLAPPER or nm.startswith(CLAPPER + " (")


def extract_episode(row: dict, meta: dict) -> dict:
    """One episode's trace (module docstring)."""
    from ssbot.record.recorder import RecordingReader
    idx = _cs_idx()
    f_wake, f_end = int(row["f_wake"]), int(row["f_end"])
    states = list(RecordingReader(row["recording"]).states(f_wake - 30, f_end))
    n = len(states)
    F = np.array([int(s["f"]) for s in states], np.int64)
    H = {"pos": np.full((n, 2), np.nan), "box": np.full((n, 4), np.nan), "vel": np.full((n, 2), np.nan),
         "hp": np.zeros(n, np.int16), "fs": np.zeros(n, np.int8), "dt": np.zeros(n, np.float32),
         "clip": [None] * n}
    for b in HERO_BITS:
        H[b] = np.zeros(n, bool)
    C: dict = {}
    bombs, runes = [], []
    trans, hits, dmg, hp_ev = [], [], [], []
    obj_iid: dict = {}

    def cl(iid: int) -> dict:
        if iid not in C:
            C[iid] = {"st": [None] * n, "t": np.full(n, np.nan), "pos": np.full((n, 2), np.nan),
                      "vel": np.full((n, 2), np.nan), "face": np.zeros(n, np.int8), "hp": np.zeros(n, np.int16),
                      "clip": [None] * n, "cf": np.zeros(n, np.int16), "body": np.full((n, 4), np.nan),
                      "body_on": np.zeros(n, bool), "sc1": {}, "sc2": {}, "range": np.full((n, 4), np.nan),
                      "dead": np.zeros(n, bool), "name": None}
        return C[iid]

    for i, s in enumerate(states):
        h = s.get("hero") or {}
        if h.get("pos"):
            H["pos"][i] = h["pos"][:2]
        if h.get("box"):
            H["box"][i] = h["box"][:4]
        if h.get("vel"):
            H["vel"][i] = h["vel"][:2]
        H["hp"][i] = int(h.get("health") or 0)
        H["fs"][i] = int(s.get("fs") or 0)
        H["dt"][i] = float(s.get("dt") or 0.0)
        H["clip"][i] = (h.get("anim") or {}).get("clip")
        cs = h.get("cstate")
        for b, j in idx.items():
            H[b][i] = _bit(cs, j)
        if h.get("invulnerable"):
            H["invulnerable"][i] = True
        bl, rl = [], []
        for e in s.get("ents") or ():
            tk = e.get("type_key")
            if tk == CLAPPER:
                if not e.get("pos"):
                    continue
                c = cl(int(e["iid"]))
                st, t_in = None, None
                for m in e.get("fsms") or ():
                    if m.get("name") == "Control":
                        st, t_in = m.get("state"), m.get("t")
                c["st"][i] = st
                c["t"][i] = float(t_in) if t_in is not None else np.nan
                c["pos"][i] = e["pos"][:2]
                c["vel"][i] = (e.get("vel") or [0.0, 0.0])[:2]
                c["face"][i] = 1 if e.get("flipX") else -1
                c["hp"][i] = int(e.get("hp") or 0)
                c["dead"][i] = bool(e.get("is_dead"))
                an = e.get("anim") or {}
                c["clip"][i] = an.get("clip")
                c["cf"][i] = int(an.get("frame") or 0)
                for col in e.get("colliders") or ():
                    nm = str(col.get("name") or "")
                    v = _verts(col)
                    if v is None:
                        continue
                    if _is_root(nm):
                        c["name"] = nm
                        c["body"][i] = (v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max())
                        d = col.get("damage") or {}
                        c["body_on"][i] = bool(col.get("enabled")) and float(d.get("eff") or 0) > 0
                    elif nm == "Slam Collider 1" and col.get("enabled"):
                        c["sc1"][i] = v.astype(np.float32)
                    elif nm == "Slam Collider 2" and col.get("enabled"):
                        c["sc2"][i] = v.astype(np.float32)
                    elif nm == "Slam Range":
                        c["range"][i] = (v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max())
            elif tk == "rune bomb small" or "damager" in str(tk) or "damager" in str(e.get("name")):
                for col in e.get("colliders") or e.get("cols") or ():
                    if col.get("kind") != "circle":
                        continue
                    v = _verts(col)
                    if v is None:
                        continue
                    r = col.get("r")
                    r = float(r) if r is not None else 0.5 * float(v[:, 0].max() - v[:, 0].min())
                    ctr = v.mean(axis=0)
                    d = col.get("damage") or {}
                    lit = bool(col.get("enabled")) and float(d.get("eff") or 0) > 0
                    rec = (int(e.get("iid") or 0), float(ctr[0]), float(ctr[1]), r, lit)
                    if abs(r - 2.166) < 0.3:
                        bl.append(rec)
                    elif abs(r - 7.187) < 0.4:
                        rl.append(rec)
                    break
        bombs.append(bl)
        runes.append(rl)
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "fsm" and d.get("fsm") == "Control" and str(d.get("obj") or "").startswith(CLAPPER):
                iid = int(d.get("iid") or d.get("ent") or 0)
                obj_iid[str(d.get("obj"))] = iid
                trans.append((int(s["f"]), iid, d.get("from"), d.get("to"), d.get("t_in_prev")))
            elif k == "hit" and d.get("type_key") == CLAPPER:
                hb, ha = d.get("hp_before"), d.get("hp_after")
                dmg_hp = (int(hb) - int(ha)) if hb is not None and ha is not None else d.get("dmg", d.get("dealt"))
                hits.append((int(s["f"]), int(d.get("ent") or 0), d.get("src"), d.get("attack"), dmg_hp,
                             bool(d.get("dead"))))
            elif k == "damage":
                dmg.append((int(s["f"]), "damage", str(d.get("source")), int(s["f"]), int(s["f"])))
            elif k == "damage_blocked":
                dmg.append((int(s["f"]), "blocked", str(d.get("source")), int(d.get("first_f") or s["f"]),
                            int(d.get("last_f") or s["f"])))
            elif k == "hp" and (d.get("delta") or 0) < 0:
                hp_ev.append((int(s["f"]), int(d.get("delta")), str(d.get("source"))))
    for c in C.values():
        c["face"] = np.asarray(c["face"])
    return {"meta": meta, "F": F, "f_wake": f_wake, "f_end": f_end, "f_kill": row.get("f_kill"),
            "outcome": row.get("outcome"), "unit": row.get("unit"), "hero": H, "cl": C, "bombs": bombs,
            "runes": runes, "trans": trans, "hits": hits, "dmg": dmg, "hp_ev": hp_ev, "obj_iid": obj_iid}


def _episodes(names: list[str]) -> list[tuple[dict, dict]]:
    out = []
    for nm, arm, inst, run in manifest_rows(names):
        p = run / f"attempts_i{inst}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("outcome") == "HARNESS_FAIL" or not row.get("recording") or row.get("f_wake") is None:
                continue
            ep_id = f"{run.name}_i{inst}_e{row.get('episode')}"
            out.append((row, {"id": ep_id, "manifest": nm, "arm": arm, "inst": inst, "run": str(run),
                              "episode": row.get("episode"), "unit": row.get("unit"), "code_rev": row.get("code_rev")}))
    return out


def _extract_one(args) -> str:
    row, meta, out_dir = args
    p = Path(out_dir) / f"{meta['id']}.pkl"
    if p.exists():
        return "cached"
    try:
        tr = extract_episode(row, meta)
    except Exception as ex:                    # a broken recording: skip it, say why
        return f"error {meta['id']}: {ex!r}"
    tmp = p.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(tr, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, p)
    return "ok"


def idle_priority() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    except Exception:
        pass


def cmd_extract(a) -> int:
    idle_priority()
    out_dir = DATA / "cache" / a.set
    out_dir.mkdir(parents=True, exist_ok=True)
    eps = _episodes(SETS[a.set])
    if a.limit:
        eps = eps[:a.limit]
    t0 = time.time()
    jobs = [(r, m, str(out_dir)) for r, m in eps]
    res = Counter()
    if a.jobs > 1:
        from multiprocessing import Pool
        with Pool(a.jobs) as pool:
            for k, r in enumerate(pool.imap_unordered(_extract_one, jobs)):
                res[r.split(" ")[0]] += 1
                if r.startswith("error"):
                    print(r, flush=True)
                if k % 50 == 0:
                    print(f"{k + 1}/{len(jobs)} {time.time() - t0:.0f}s {dict(res)}", flush=True)
    else:
        for k, j in enumerate(jobs):
            r = _extract_one(j)
            res[r.split(" ")[0]] += 1
            if r.startswith("error"):
                print(r, flush=True)
    print(f"done {len(jobs)} episodes in {time.time() - t0:.0f}s: {dict(res)}")
    return 0


def load_set(name: str, limit: int = 0):
    """Yield the cached traces of a set (extract first)."""
    d = DATA / "cache" / name
    ps = sorted(d.glob("*.pkl"))
    if limit:
        ps = ps[:limit]
    for p in ps:
        with open(p, "rb") as fh:
            yield pickle.load(fh)


# ---- helpers on a trace ----

def game_clock(tr: dict) -> np.ndarray:
    """[N] game frames since the trace's first frame (cumulative dt x 60: a hit-stop freeze does not advance it)."""
    return np.cumsum(np.clip(tr["hero"]["dt"].astype(np.float64), 0.0, 0.05)) * 60.0


def runs_of(tr: dict) -> dict:
    """iid -> [(state, f_entry, f_exit, next state, seconds in it)] from the Control transitions (instant states
    included: f_exit == f_entry)."""
    by = defaultdict(list)
    for f, iid, a, b, tp in tr["trans"]:
        by[iid].append((f, a, b, tp))
    out = {}
    for iid, L in by.items():
        rr = []
        for i in range(len(L) - 1):
            f, a, b, tp = L[i]
            f2, a2, b2, tp2 = L[i + 1]
            if a2 != b:
                continue
            rr.append((b, f, f2, b2, tp2))
        out[iid] = rr
    return out


# ---- fit: the timing and geometry tables of the knowledge file ----

FIT_STATES_SKIP = ("Start Battle?", "Start Battle 2", "Init", "Rest")


def _box_rel(c: dict, i: int):
    fc = int(c["face"][i])
    px, py = c["pos"][i]
    b = c["body"][i]
    xa, xb = (b[0] - px) * fc, (b[2] - px) * fc
    return (min(xa, xb), max(xa, xb), b[1] - py, b[3] - py)


def cmd_fit(a) -> int:
    idle_priority()
    dur = defaultdict(Counter)
    special = defaultdict(Counter)
    box = defaultdict(lambda: defaultdict(list))
    rune_l0, rune_l1, rune_dx, rune_cy, rune_r = [], [], [], [], []
    bomb_app, bomb_lead, bomb_dur, bomb_y = defaultdict(list), [], [], []
    drop_v, land_dy, evade_d = [], [], []
    walk_v = []
    n_ep = 0
    for tr in load_set("fit", a.limit):
        n_ep += 1
        F = tr["F"]
        fi = {int(f): i for i, f in enumerate(F)}
        G = game_clock(tr)
        buddy = "w13" in str(tr.get("unit"))
        R = runs_of(tr)
        for iid, rr in R.items():
            c = tr["cl"].get(iid)
            if c is None:
                continue
            for k, (st, f0, f1, nxt, tp) in enumerate(rr):
                if f0 not in fi or f1 not in fi or st in FIT_STATES_SKIP or nxt == "Start Battle?":
                    continue
                d = int(round(G[fi[f1]] - G[fi[f0]]))
                dur[st][d] += 1
                prev = rr[k - 1][0] if k else None
                if st == "Idle":
                    if nxt == "Walk":
                        special[f"idle_walk_{'buddy' if buddy else 'solo'}"][d] += 1
                    elif nxt == "Evade Scuttle" and d > 0:
                        special["idle_evade"][d] += 1
                elif st == "Walk":
                    special[f"walk_{'close' if nxt == 'Close Range' else 'far'}"][d] += 1
                elif st == "Evade Scuttle" and nxt == "After Scuttle":
                    i0, i1 = fi[f0], fi[f1]
                    evade_d.append(float((c["pos"][i1, 0] - c["pos"][i0, 0]) * -c["face"][i0]))
                elif st == "Drop In":
                    i0, i1 = fi[f0], fi[f1]
                    if i1 - i0 > 3:
                        drop_v.append(float((c["pos"][i0 + 3, 1] - c["pos"][i0 + 1, 1]) / max(G[i0 + 3] - G[i0 + 1], 1e-6) * 60))
                elif st == "Charged?":
                    i0 = fi[f0]
                    lit = [G[j] - G[i0] for j in range(i0, min(i0 + 150, len(F)))
                           if any(r[4] and abs((r[1] - c["pos"][i0, 0]) * c["face"][i0] - 6.7) < 1.0
                                  for r in tr["runes"][j])]
                    ctr = [r for j in range(i0, min(i0 + 40, len(F))) for r in tr["runes"][j]
                           if abs((r[1] - c["pos"][i0, 0]) * c["face"][i0] - 6.7) < 1.0]
                    if lit and ctr:
                        rune_l0.append(lit[0])
                        rune_l1.append(lit[-1])
                        rune_dx.append(float((ctr[0][1] - c["pos"][i0, 0]) * c["face"][i0]))
                        rune_cy.append(float(ctr[0][2]))
                        rune_r.append(float(ctr[0][3]))
                    land_dy.append(float(c["pos"][i0, 1] - c["pos"][fi[rr[k - 3][1]] - 1, 1]) if k >= 3 and
                                   rr[k - 3][0] == "Jump" and rr[k - 3][1] in fi else np.nan)
                elif st == "Cast 2":
                    i0 = fi[f0]
                    x0, y0 = c["pos"][i0]
                    seen = {}
                    for j in range(i0, min(i0 + 150, len(F))):
                        for (bid, x, y, r, lit) in tr["bombs"][j]:
                            m = int(round((x - x0) / 4.2))
                            if abs(m) > 9 or abs(x - x0 - 4.2 * m) > 0.35:
                                continue
                            g = G[j] - G[i0]
                            s = seen.setdefault((bid, m), [g, None, None, y - y0])
                            if lit:
                                if s[1] is None:
                                    s[1] = g
                                s[2] = g
                    first = {}
                    for (bid, m), s in seen.items():
                        if s[0] <= 110 and (abs(m) not in first or s[0] < first[abs(m)][0]):
                            first[abs(m)] = s
                    for m, s in first.items():
                        bomb_app[m].append(s[0])
                        bomb_y.append(s[3])
                        if s[1] is not None:
                            bomb_lead.append(s[1] - s[0])
                            bomb_dur.append(s[2] - s[1] + 1)
        for iid, c in tr["cl"].items():
            st = c["st"]
            ent = None
            for i in range(len(F)):
                if st[i] is None:
                    ent = None
                    continue
                if ent is None or st[i] != st[i - 1]:
                    ent = i
                if not np.isfinite(c["body"][i, 0]) or st[i] in FIT_STATES_SKIP:
                    continue
                j = int(round(G[i] - G[ent]))
                box[st[i]][min(j, 240)].append(_box_rel(c, i))
                if st[i] == "Walk" and i > 0 and st[i - 1] == "Walk" and tr["hero"]["fs"][i] == 1:
                    walk_v.append(abs(float(c["pos"][i, 0] - c["pos"][i - 1, 0])) / 0.02)
    # the body table: per state, per j the median box (runs of equal boxes compressed), and the p95 deviation
    body = {}
    for st, per in box.items():
        rows, devs = [], []
        for j in sorted(per):
            arr = np.asarray(per[j], float)
            if len(arr) < 8:
                continue
            med = np.median(arr, axis=0)
            devs.append(float(np.percentile(np.abs(arr - med).max(axis=1), 95)))
            r = [int(j)] + [round(float(v), 3) for v in med]
            if rows and rows[-1][1:] == r[1:]:
                continue
            rows.append(r)
        if rows:
            body[st] = {"runs": rows, "dev95": round(max(devs), 3) if devs else 0.0, "n": int(sum(len(v) for v in per.values()))}

    def cnt(c: Counter) -> dict:
        return {str(k): v for k, v in sorted(c.items())}

    def q(v, qs=(1, 5, 50, 95, 99)):
        v = [x for x in v if x is not None and np.isfinite(x)]
        return [round(float(np.percentile(v, p)), 3) for p in qs] if v else None

    out = {
        "format": "ssbot.map2.clapper/1",
        "source": f"ssbot.tools.m2_clapper fit: {n_ep} recorded episodes of the fit set ({', '.join(SETS['fit'])})",
        "clock": "game frames (cumulative dt x 60; a hit-stop freeze does not count) from the state's entry frame",
        "durations": {st: cnt(c) for st, c in sorted(dur.items())},
        "special": {k: cnt(c) for k, c in sorted(special.items())},
        "body": body,
        "evade_back_u": q(evade_d),
        "walk_speed": q(walk_v),
        "drop_vy": q(drop_v),
        "jump_land_dy": q(land_dy),
        "rune": {"lit0": q(rune_l0), "lit1": q(rune_l1), "dx": q(rune_dx), "cy": q(rune_cy), "r": q(rune_r),
                 "n": len(rune_l0)},
        "bombs": {"appear": {str(m): q(v) for m, v in sorted(bomb_app.items())},
                  "n": {str(m): len(v) for m, v in sorted(bomb_app.items())},
                  "lead": q(bomb_lead), "lit": q(bomb_dur), "dy": q(bomb_y)},
    }
    path = Path(a.out)
    path.write_text(json.dumps(out, indent=1), "utf-8")
    print(f"fit: {n_ep} episodes -> {path}")
    for k in ("evade_back_u", "walk_speed", "drop_vy", "jump_land_dy", "rune", "bombs"):
        print(k, json.dumps(out[k])[:300])
    return 0


def cmd_margins(a) -> int:
    """The margin table of the knowledge file from a validation summary of the FIT set (ssbot.tools.m2_validate):
    per move and look-ahead k the smallest growth m (u, on the validation's grid) whose covered share of the actual
    damage area (the realized branch) reaches 99 % - or, where no growth on the grid reaches it (the rest is a timing /
    branch miss a margin cannot fix: a late bomb of the pool, a decision at another frame), the smallest m within 0.2 %
    of the share at the grid's largest growth (the knee). Monotone in k. The residual share is listed."""
    S = json.loads(Path(a.val).read_text("utf-8"))
    know = Path(a.out)
    d = json.loads(know.read_text("utf-8"))
    by_move, residual = defaultdict(list), {}
    for key, v in S["area"].items():
        k, mv = key.split(" ", 1)
        k = int(k[2:])
        cov = sorted((float(m), float(c)) for m, c in v["covered_by_margin"].items())
        top = cov[-1][1]
        target = 0.99 if top >= 0.99 else top - 0.002
        m = next(mm for mm, c in cov if c >= target)
        by_move[mv].append([k, m])
        if top < 0.99:
            residual[f"{mv}@{k}"] = round(1.0 - top, 4)
    out = {}
    for mv, rows in sorted(by_move.items()):
        rows.sort()
        for i in range(1, len(rows)):
            rows[i][1] = max(rows[i][1], rows[i - 1][1])
        out[mv] = rows
    d["margins"] = {"source": f"{Path(a.val).name} ({S['_meta']['set']}, {S['_meta']['episodes']} episodes)",
                    "rule": ">= 99 % of the actual damage area covered by the realized branch's union grown by m, else "
                            "the knee (within 0.2 % of the share at 1.0 u); monotone in k",
                    "by_move": out, "residual_at_1u": residual, "default": 0.5}
    know.write_text(json.dumps(d, indent=1), "utf-8")
    print(json.dumps({mv: rows for mv, rows in out.items()}))
    print("residual (not covered even at 1.0 u):", residual)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract")
    p.add_argument("--set", choices=sorted(SETS), required=True)
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("fit")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies"
                                        / "forum" / "clapper_m2.json"))
    p = sub.add_parser("margins")
    p.add_argument("--val", default=str(DATA / "val_fit.json"))
    p.add_argument("--out", default=str(Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies"
                                        / "forum" / "clapper_m2.json"))
    a = ap.parse_args(argv)
    if a.cmd == "extract":
        return cmd_extract(a)
    if a.cmd == "fit":
        return cmd_fit(a)
    if a.cmd == "margins":
        return cmd_margins(a)
    return 1


if __name__ == "__main__":
    sys.exit(main())
