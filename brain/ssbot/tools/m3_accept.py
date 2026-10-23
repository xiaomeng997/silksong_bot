"""Map v2 stage M3: THE ACCEPTANCE SUITE (docs/plans/forum_map_v2.md section 0 and 1b.1; forum.md section 94).
Offline only: the bot does not import this or ssbot.map2.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m3_accept situations [--sets held] [--per-move 12]
        # forced setups per move, the person's 33 slam strikes, recorded frames (the bot's runs) -> m3/sits.pkl
    ../scripts/uv.cmd run python -m ssbot.tools.m3_accept run --lib none|full [--jobs 6] [--cap 30]
        # the search on every situation: run 'none' = primitives + the strike module only (the real test: no P1-P5
        # macro exists), 'full' = with the combo library (knowledge/.../combos) -> m3/run_<lib>.json
    ../scripts/uv.cmd run python -m ssbot.tools.m3_accept report      # the table -> m3/report.txt / .json
    ../scripts/uv.cmd run python -m ssbot.tools.m3_accept horizon --set held [--jobs 6] [--limit N]
        # the needed horizon: per HP loss in the recordings, the frames before the hit at which the last exit (an
        # envelope pass in the realized branch's danger, <= 2 events, to the hit + 15) vanished

Per situation and move (its meta 'moves'): FOUND-SAME (the chosen plan has the move's label), FOUND-ALT (the chosen
plan is another one; a safe plan with the label was found but valued lower by the model), NOT FOUND (why: unsafe by
the model - its first reason -, the strike missed / the label's conditions not met by the candidates, no window /
candidate of the needed primitive, the time cap) - plus the chosen plan's model safety (every outcome safe, p_safe),
its expected hits, the decision time, the plan's length to its last contact.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.map2 import clapper as cm
from ssbot.tools import m2_validate as mv
from ssbot.tools.m2_clapper import DATA as M2DATA, idle_priority

OUT = Path(r"C:\ssbot\data\m2_play\map2\m3")
MOVE_LABEL = {"P1-idle": ("P1-idle",), "P1-idle-slam": ("P1-idle-slam",), "P1-idle-evade": ("P1-idle-evade",),
              "P1-far-jump": ("P1-far-jump",), "P1-far-jcast": ("P1-far-jcast",), "P1-slam": ("P1-slam",),
              "P1-cast": ("P1-cast",), "P1-jump": ("P1-jump",),
              "P1-locked": ("P1-locked",), "P2": ("P2",), "P3-face": ("P3-face",), "P3-cross": ("P3-cross",),
              "P4": ("P4",), "P5": ("P5",), "CLAWSTRIKE": ("CLAWSTRIKE",), "SLAMSTRIKE": ("SLAMSTRIKE",),
              "JUMPTRAP": ("JUMPTRAP",), "LOWHOP": ("LOWHOP",)}
PRIM_OF = {"P1-idle": "claw", "P1-slam": "claw", "P1-cast": "claw", "P1-jump": "claw", "P1-locked": "claw",
           "P1-idle-slam": "claw", "P1-idle-evade": "claw", "P1-far-jump": "claw", "P1-far-jcast": "claw",
           "CLAWSTRIKE": "claw", "P2": "dslash", "P3-face": "dslash", "P4": "dslash", "P5": "dslash",
           "SLAMSTRIKE": "dslash", "P3-cross": "safe", "JUMPTRAP": "safe", "LOWHOP": "safe"}
# a label that counts as the same move done another way (found, different kind): the slam struck in its second window
ALT_LABEL = {"P1-idle-slam": ("P1-idle-slam2",)}
# the person's three hook cases (MOVES_TODO P1, 2026-10-22): the reaction each one needs (and the far list's for the
# far ones) - when no outcome of any tried plan shows it, the model says it cannot happen there
REACTION_OF = {"P1-idle-slam": ("SLAM", False), "P1-idle-evade": ("EVADE", False), "P1-far-jump": ("JUMP", True),
               "P1-far-jcast": ("JUMP CAST", True)}
CLOSE_IDLE = ["P1-idle-slam", "P1-idle-evade"]
FAR_IDLE = ["P1-far-jump", "P1-far-jcast"]


# ---- situations -----------------------------------------------------------------------------------------------------

def _her(W, x: float, ground: bool = True, bb: float | None = None, vx: float = 0.0, vy: float = 0.0,
         face: int = 1) -> np.ndarray:
    """Her kin state: standing at x, or airborne with her box bottom at bb (world y) and velocity (vx, vy)."""
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import strike as sk
    if ground:
        return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, facing=face)
    return km.initial_state(W.params, x, bb + sk.FOOT, ground=False, vx=vx, vy=vy, facing=face)


def float_state(W, x: float, bb: float, key: int = 0, extra: int = 0, face: int = 1) -> np.ndarray:
    """Her kin state in the umbrella's Float Idle (`extra` frames after its start) with her box bottom at bb and her
    centre at x (the open rolled from rest and translated: M1's canonical A3 start)."""
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import strike as sk
    S0 = km.initial_state(W.params, 0.0, 20.0, ground=False, facing=face)
    h = {1: km.B_RIGHT, -1: km.B_LEFT}.get(key, 0)
    m = []
    for _ in range(60):
        m.append(km.B_JUMP | h)
        r = W.roll(S0, np.array(m))
        if r.final[km.MODE, 0] == km.M_GLIDE and r.final[km.PHASE, 0] == 2.0:
            break
    m += [km.B_JUMP | h] * extra
    S = W.roll(S0, np.array(m)).final[:, 0].copy()
    dx, dy = x - S[km.PX], (bb + sk.FOOT) - S[km.PY]
    for i in (km.PX, km.QX, km.SX):
        S[i] += dx
    for i in (km.PY, km.QY, km.SY):
        S[i] += dy
    return S


def _obs(st: str, x: float, face: int = -1, j: int = 2, iid: int = 1, will_evade=None) -> cm.Obs:
    return cm.Obs(iid, st, j / 60.0, x, cm.STAND_Y, 0.0, 0.0, face, 230, None, will_evade=will_evade, j=j)


def _sit(S, obs, name, moves, src="forced", **meta):
    from ssbot.map2 import search as ms
    return ms.Situation(S, list(obs), {o.iid: cm.Memory() for o in obs}, name=name,
                        meta=dict(moves=list(moves), src=src, **meta))


def forced_situations(W) -> list:
    """Forced setups per move (the live probes' kind: a Clapper put in a state, her at a distance / height)."""
    out = []
    C = 33.0
    # P1 on an Idle Clapper (in front of it: it faces her), from the ground and from the air
    # (the person's three cases, MOVES_TODO P1 2026-10-22: within Slam Range at the needle's hit the close list -
    # a SLAM -> the first window with an umbrella in between, an EVADE -> a second Clawline; from beyond it, ~8.3 u
    # centre to centre, the far list - a JUMP -> the ride, a JUMP CAST -> high / over its landing)
    for dx in (3.5, 5.0, 7.0, 9.0, 10.0):
        for side in (-1, 1):
            mv_ = ["P1-idle"] + (CLOSE_IDLE if dx <= 7.5 else FAR_IDLE if dx >= 8.5 else [])
            out.append(_sit(_her(W, C + side * dx, face=-side), [_obs("Idle", C, face=side, j=8)],
                            f"idle g dx{dx} s{side}", mv_))
    for dx, bb in ((5.0, 4.0), (7.0, 4.5), (6.0, 5.5), (9.0, 4.2), (10.0, 5.0)):
        mv_ = ["P1-idle"] + (CLOSE_IDLE if dx <= 7.5 else FAR_IDLE)
        out.append(_sit(_her(W, C - dx, False, bb, face=1), [_obs("Idle", C, face=-1, j=8)],
                        f"idle air dx{dx} bb{bb}", mv_))
    # P1 in a slam antic = CLAWSTRIKE's situations (SP13: from 5.6 u, k <= 14)
    for dx in (5.6, 7.0, 8.5, 10.0):
        for j in (2, 5):
            out.append(_sit(_her(W, C - dx, face=1), [_obs("Slam Antic", C, face=-1, j=j)],
                            f"slam g dx{dx} j{j}", ["P1-slam", "CLAWSTRIKE"]))
    for dx, bb in ((7.0, 4.2), (9.0, 4.6)):
        out.append(_sit(_her(W, C - dx, False, bb, face=1), [_obs("Slam Antic", C, face=-1, j=3)],
                        f"slam air dx{dx} bb{bb}", ["P1-slam", "CLAWSTRIKE"]))
    # P1 in a cast / a jump antic
    for dx in (5.0, 7.0, 9.0):
        out.append(_sit(_her(W, C - dx, face=1), [_obs("Spell Antic", C, face=-1, j=4)], f"cast g dx{dx}",
                        ["P1-cast"]))
    for dx in (4.0, 6.0, 8.0):
        out.append(_sit(_her(W, C - dx, face=1), [_obs("Jump Antic", C, face=-1, j=4)], f"jumpantic g dx{dx}",
                        ["P1-jump", "P4"]))
    # P1 on the locked one (A slams far away, B Idle near her: B's Close Range reads A attacking -> CANCEL)
    for dx in (5.0, 7.0):
        out.append(_sit(_her(W, 28.0 - dx, face=1), [_obs("Slam Antic", 45.0, face=-1, j=6, iid=1),
                                                     _obs("Idle", 28.0, face=-1, j=8, iid=2)],
                        f"locked dx{dx}", ["P1-locked"]))
    # P2: floating above / in front of a slam antic (the close -> drop -> strike on Slam 0)
    for dx, bb, j in ((1.5, 6.5, 18), (3.0, 6.0, 22), (0.0, 7.0, 24), (2.0, 5.5, 26)):
        out.append(_sit(float_state(W, C - dx, cm.FLOOR + bb), [_obs("Slam Antic", C, face=-1, j=j)],
                        f"float slam dx{dx} bb{bb} j{j}", ["P2"]))
    # P3: an Idle Clapper 6 - 10 u from the left wall facing the middle; her above it / in front of it; and a
    # slam antic facing the wall with her on its wall side (cross to the middle side)
    for cxw, hx, bb in ((8.0, 2.5, 4.5), (10.0, 3.0, 4.0), (6.0, 1.5, 5.0), (8.0, -1.0, 4.5)):
        cx = cm.WALL_L + cxw
        out.append(_sit(_her(W, cx + hx, False, cm.FLOOR + bb), [_obs("Idle", cx, face=1, j=8)],
                        f"wall idle air w{cxw} hx{hx}", ["P3-face"]))
    for cxw in (8.0, 10.0):
        cx = cm.WALL_L + cxw
        out.append(_sit(_her(W, cx + 6.0, face=-1), [_obs("Idle", cx, face=1, j=8)], f"wall idle g w{cxw}",
                        ["P3-face"]))
    for cxw, hx in ((8.0, -3.0), (10.0, -4.0)):
        cx = cm.WALL_L + cxw
        out.append(_sit(_her(W, cx + hx, face=1), [_obs("Slam Antic", cx, face=-1, j=3)],
                        f"wall slam cross w{cxw}", ["P3-cross"]))
    # P4: a jump at her face (the antic late, the take-off's rise)
    for dx, j in ((3.0, 20), (4.5, 24), (2.0, 26)):
        out.append(_sit(_her(W, C - dx, face=1), [_obs("Jump Antic", C, face=-1, j=j)], f"ride g dx{dx} j{j}",
                        ["P4"]))
    for dx, bb in ((2.5, 5.0), (4.0, 6.0)):
        o = _obs("Air", C, face=-1, j=2)
        o.vy = 38.0 - 1.68 * 3
        o.y = cm.STAND_Y + 0.6
        out.append(_sit(_her(W, C - dx, False, cm.FLOOR + bb, face=1), [o], f"ride air dx{dx} bb{bb}", ["P4"]))
    # P5: a Clapper under her falling path
    for st, dx, bb, vy in (("Idle", 0.3, 5.5, -3.0), ("Idle", -0.8, 6.5, -6.0), ("Slam Recover", 0.5, 5.0, -2.0),
                           ("Spell Antic", 0.0, 6.0, -4.0), ("Walk", 1.0, 5.5, -5.0)):
        out.append(_sit(_her(W, C + dx, False, cm.FLOOR + bb, vy=vy, face=1), [_obs(st, C, face=-1, j=6)],
                        f"landpogo {st} dx{dx} bb{bb}", ["P5"]))
    # JUMPTRAP: the jumper J aims at her, the other one F (or the wall) at her back
    for hx, jx, fx in ((32.0, 40.0, 27.0), (30.0, 38.0, 25.5), (35.0, 43.0, 30.5)):
        out.append(_sit(_her(W, hx, face=1), [_obs("Jump Antic", jx, face=-1, j=20, iid=1),
                                              _obs("Idle", fx, face=1, j=30, iid=2, will_evade=False)],
                        f"jumptrap h{hx} J{jx} F{fx}", ["JUMPTRAP"]))
    for hx, jx in ((16.5, 24.0), (18.0, 26.0)):
        out.append(_sit(_her(W, hx, face=1), [_obs("Jump Antic", jx, face=-1, j=20)],
                        f"jumptrap wall h{hx} J{jx}", ["JUMPTRAP"]))
    # LOWHOP: a cast's bomb row lighting under her
    for hx, k0 in ((29.0, 0), (30.5, -4), (28.0, -8)):
        o = _obs("Cast 2", C, face=-1, j=-k0)
        o.cast2 = (k0, C, cm.STAND_Y)
        out.append(_sit(_her(W, hx, face=1), [o], f"bombs h{hx} k{k0}", ["LOWHOP"]))
    return out


def human_situations(W) -> list:
    """The person's slam strikes of 2026-10-15 (m2_play/human_keys.json 'strikes': x0 at the antic, on the ground):
    the Clapper in Slam Antic at its first frames, her standing x0 in front (where the person succeeded)."""
    d = json.loads(Path(r"C:\ssbot\data\m2_play\human_keys.json").read_text("utf-8"))
    out = []
    C = 33.0
    for i, s in enumerate(d.get("strikes", [])):
        if not s.get("g0", True):
            continue
        x0 = float(s["x0"])
        out.append(_sit(_her(W, C - x0, face=1), [_obs("Slam Antic", C, face=-1, j=1)],
                        f"person slam {i} x0 {x0:.2f}", ["SLAMSTRIKE"], src="person",
                        person={k: s.get(k) for k in ("jump_k", "hold", "press_k", "contact_s0", "landed", "hp")}))
    return out


PLAIN_CLIPS = {"Airborne", "Idle", "Run", "Run To Idle", "Turn", "Idle To Run", "Land", "Land To Run",
               "Dash To Idle", "Dash To Run", "DownSpikeBounce 1", "DownSpikeBounce 2", "Slash To Run", "Slash",
               "SlashAlt", "Slash Land", "Slash Land Run", "Slash Land Run Alt", "Skid End 1", "Skid End 2"}


def rec_state(W, E, g):
    """Her kin state at game frame g of a trace (approximate: box centre, box bottom, velocity, grounded; plain
    control clips only, else None)."""
    i = E.g2i[g]
    H = E.tr["hero"]
    if H["clip"][i] not in PLAIN_CLIPS:
        return None
    box, vel = H["box"][i], H["vel"][i]
    if not np.all(np.isfinite(box)) or not np.all(np.isfinite(vel)):
        return None
    xc = 0.5 * (box[0] + box[2])
    face = 1 if vel[0] >= 0 else -1
    if bool(H["onGround"][i]):
        return _her(W, xc, True, face=face)
    return _her(W, xc, False, float(box[1]), vx=float(vel[0]), vy=float(vel[1]), face=face)


def _rec_scan(path: str) -> list:
    """Candidate situation frames of one trace: (path, g0, moves, tag, an HP loss within 120 frames)."""
    with open(path, "rb") as fh:
        tr = pickle.load(fh)
    E = mv.Episode(tr)
    out = []
    H = tr["hero"]
    hp_g = sorted({E.g_of(f) for (f, d, src) in tr["hp_ev"] if E.g_of(f) is not None})

    def lost(g):
        return any(g < h <= g + 120 for h in hp_g)

    for iid in E.iids:
        c = E.cl[iid]
        for (g, a, b, f) in E.trans[iid]:
            g0 = g + 2
            if g0 >= E.n_g - 130:
                continue
            i = E.g2i[g0]
            cx, face = float(c["pos"][i, 0]), int(c["face"][i])
            hx = float(H["pos"][i, 0])
            dxf = (hx - cx) * face
            ground = bool(H["onGround"][i])
            mv_ = None
            if b == "Slam Antic" and 5.6 <= dxf <= 10.5:
                mv_ = ["P1-slam", "CLAWSTRIKE"]
            elif b == "Slam Antic" and 2.7 <= dxf < 5.6 and ground:
                mv_ = ["SLAMSTRIKE"]
            elif b == "Spell Antic" and 3.0 <= abs(hx - cx) <= 10.0:
                mv_ = ["P1-cast"]
            elif b == "Jump Antic" and abs(hx - cx) <= 6.0:
                mv_ = ["P1-jump", "P4"] + (["JUMPTRAP"] if len(E.iids) > 1 else [])
            elif b == "Cast 2" and ground and abs(hx - cx) <= 7.0:
                mv_ = ["LOWHOP"]
            elif b == "Idle" and 3.0 <= abs(hx - cx) <= 10.5:
                mv_ = ["P1-idle"] + (CLOSE_IDLE if abs(hx - cx) <= 7.5 else FAR_IDLE if abs(hx - cx) >= 8.5 else [])
                wall = cm.WALL_L if cx - cm.WALL_L < cm.WALL_R - cx else cm.WALL_R
                if abs(cx - wall) <= 12.0:
                    mv_.append("P3-face")
            if mv_ is not None:
                out.append((path, g0, mv_, f"{b}:{iid % 1000}", lost(g0)))
    for g0 in range(30, E.n_g - 130, 7):
        i = E.g2i[g0]
        clip = H["clip"][i]
        hx, hb = float(H["pos"][i, 0]), float(H["box"][i, 1])
        for iid in E.iids:
            c = E.cl[iid]
            st = c["st"][i]
            if st is None or not np.isfinite(c["body"][i, 0]):
                continue
            top = float(c["body"][i, 3])
            if clip == "Airborne" and float(H["vel"][i, 1]) < 0 and c["body"][i, 0] - 0.5 <= hx <= \
                    c["body"][i, 2] + 0.5 and 0.3 <= hb - top <= 3.0 and st not in ("Jump", "Air"):
                out.append((path, g0, ["P5"], f"above:{st}", lost(g0)))
            if clip in ("Umbrella Float", "Umbrella Inflate") and st == "Slam Antic" and abs(hx - c["pos"][i, 0]) <= 5.0:
                out.append((path, g0, ["P2"], f"float:{st}", lost(g0)))
    return out


def rec_situations(W, sets=("held",), per_move: int = 12, seed: int = 7, jobs: int = 6) -> list:
    """Situations from the recordings (the bot's runs; where it failed: an HP loss within 120 frames; and where not):
    per move up to per_move, half of them before an HP loss when there are."""
    from ssbot.map2 import search as ms
    rng = np.random.default_rng(seed)
    paths = [str(p) for st in sets for p in sorted((M2DATA / "cache" / st).glob("*.pkl"))]
    rows = []
    if jobs > 1:
        from multiprocessing import Pool
        with Pool(jobs) as pool:
            for r in pool.imap_unordered(_rec_scan, paths):
                rows += r
    else:
        for p in paths:
            rows += _rec_scan(p)
    rows.sort(key=lambda r: (r[0], r[1]))
    by = defaultdict(list)
    for r in rows:
        for m in r[2]:
            by[m].append(r)
    pick = []
    for m, lst in sorted(by.items()):
        lo = [r for r in lst if r[4]]
        ke = [r for r in lst if not r[4]]
        n1 = min(len(lo), per_move // 2)
        sel = [lo[i] for i in rng.choice(len(lo), n1, replace=False)] if n1 else []
        n2 = min(len(ke), per_move - n1)
        sel += [ke[i] for i in rng.choice(len(ke), n2, replace=False)] if n2 else []
        pick += [(m, r) for r in sel]
    out = []
    cache: dict = {}
    K = cm.Know.load()
    for m, (path, g0, moves, tag, lost) in sorted(pick, key=lambda t: (t[1][0], t[1][1])):
        if path not in cache:
            with open(path, "rb") as fh:
                tr = pickle.load(fh)
            E = mv.Episode(tr)
            cache = {path: (E, mv._memories(E))}
        E, mem_at = cache[path]
        if m == "P2":
            i = E.g2i[g0]
            box = E.tr["hero"]["box"][i]
            S = float_state(W, 0.5 * (box[0] + box[2]), float(box[1]))
        else:
            S = rec_state(W, E, g0)
        if S is None:
            continue
        obs, mems = [], {}
        for jj in E.iids:
            mm = mem_at(jj, g0)
            o = E.obs(jj, g0, mm)
            if o is not None and o.st is not None:
                obs.append(o)
                mems[jj] = mm
        if not obs:
            continue
        hz = E.ghost_hazards(g0, {o.iid for o in obs}, K)
        out.append(ms.Situation(S, obs, mems, hz, name=f"{E.tr['meta']['id']}@{g0} {tag}",
                                meta=dict(moves=[m], src="rec", lost=bool(lost), unit=E.tr.get("unit"), tag=tag,
                                          g0=int(g0))))
    return out


def cmd_situations(a) -> int:
    idle_priority()
    from ssbot.map2 import search as ms
    W = ms.World()
    sits = forced_situations(W)
    n_f = len(sits)
    sits += human_situations(W)
    n_h = len(sits) - n_f
    sits += rec_situations(W, sets=tuple(a.sets.split(",")), per_move=a.per_move, jobs=a.jobs)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "sits.pkl", "wb") as fh:
        pickle.dump(sits, fh)
    cnt = defaultdict(lambda: defaultdict(int))
    for s in sits:
        for m in s.meta["moves"]:
            cnt[m][s.meta["src"]] += 1
    print(f"{len(sits)} situations: forced {n_f}, person {n_h}, recordings {len(sits) - n_f - n_h}")
    for m, d in sorted(cnt.items()):
        print(f"  {m:12s} " + " ".join(f"{k} {v}" for k, v in sorted(d.items())))
    return 0


# ---- the run -------------------------------------------------------------------------------------------------------

_W = None


def _run_one(args) -> dict:
    """One situation: the search, the labels of the chosen plan, the best plan per wanted move among the tried ones
    (finished: its exits checked), the reasons when none."""
    global _W
    i, sit, lib, cap, depth = args[:5]
    extra = args[5] if len(args) > 5 else {}
    from ssbot.map2 import search as ms, recognize as rz, combos as cb
    if extra.get("prio") == "high":
        from ssbot.tools.m4b_speed import boost_self
        boost_self("high")
    if _W is None:
        if extra.get("prio") == "high":
            from ssbot.tools.m4b_speed import _world
            _W = _world()                                 # warmed like a live worker
        else:
            _W = ms.World()
    cfg = ms.Cfg(cap_s=cap, depth=depth, library=tuple(cb.load_library()) if lib == "full" else (),
                 **extra.get("cfg", {}))
    S = ms.Searcher(_W, cfg)
    if extra.get("part") is not None:
        S.part = tuple(extra["part"])                 # M4b: one part of a split search
    if extra.get("vclock"):
        S.vclock = float(extra["vclock"])             # the cap in work units (deterministic)
    pre = None
    if extra.get("hold"):
        # M4c: every plan starts with one frame of no key (the live root's prefix: the key in flight); hold 2: and
        # every plan as the oracle's hold filter latches it (live.HoldRealizer: a press / release lasts >= 2 frames)
        pre = ms.Seg(np.zeros(1, np.int64), [], None, "pre")
        if int(extra["hold"]) == 2:
            from ssbot.knowledge import kinematics as km
            from ssbot.map2 import live as lv
            S.realizer = lv.HoldRealizer(1, lv.hold_tuple(km.HoldState.idle(1)))
    t0 = time.perf_counter()
    try:
        r = S.decide(sit) if pre is None else S.decide(sit, prefix=pre)
    except Exception as ex:                                       # a bug: count it, keep going
        import traceback
        return {"i": i, "name": sit.name, "error": repr(ex), "tb": traceback.format_exc()[-1500:]}
    ms_dec = (time.perf_counter() - t0) * 1e3
    ch = r.ev
    labels = rz.classify(ch, sit) if ch is not None else []
    # the kept plan's full re-check (the hysteresis path: re-evaluated in the closed loop with its exits) and the
    # per-tick check of the committed part (search.Evaluator.tick_check) - their times
    t1 = time.perf_counter()
    tick = None
    if ch is not None and ch.plan.segs:
        S.ev.reset()                                  # (M4b: no trajectory memo from the search)
        S.ev.evaluate(sit, ch.plan)
        S.ev.reset()
        tick = S.ev.tick_check(sit, ch.plan)
    ms_tick = (time.perf_counter() - t1) * 1e3 - (tick[2] if tick else 0.0)
    res = {"i": i, "part": list(extra["part"]) if extra.get("part") else None, "name": sit.name, "meta": sit.meta,
           "ms": round(ms_dec, 1), "ms_tick": round(ms_tick, 1),
           "n_cand": r.n_cand, "n_pred": r.n_pred, "n_exit": r.n_exit, "timed_out": r.timed_out,
           "ms_pred": round(r.ms_pred, 1), "ms_exit": round(r.ms_exit, 1), "stats": dict(S.stats),
           "labels": labels, "origin": ch.plan.origin if ch is not None else None,
           "value": round(float(ch.value), 3) if ch is not None else None,
           "hits": round(float(ch.hits), 3) if ch is not None else None,
           "p_safe": round(float(ch.p_safe), 3) if ch is not None else None,
           "safe": bool(ch.safe) if ch is not None else False,
           "log": ms.plan_log(ch) if ch is not None else None,
           "ms_check": round(tick[2], 1) if tick else None, "check_ok": bool(tick[0]) if tick else None,
           "contingent": getattr(ch, "contingent", None) if ch is not None else None,
           "anytime": [(round(a[0], 4), round(a[1], 1), round(a[2], 4), a[3], a[4], a[5]) for a in S.anytime],
           "first_safe_ms": next((a[1] for a in S.anytime if a[3] and a[4] != "noop"), None),
           "reactions": {k: (round(v[0], 3), v[1]) for k, v in rz.reaction_table(ch).items()} if ch is not None
           else {}}
    if ch is not None and ch.nominal is not None:
        cts = [k for (k, _, _) in ch.nominal.tr.contacts]
        res["last_contact"] = max(cts) if cts else None
        res["plan_frames"] = int(ch.nominal.tr.end)
    per = {}
    lab_of = {}
    for e in r.tried:
        if e.outcomes:
            lab_of[id(e)] = rz.classify(e, sit)
    for m in sit.meta.get("moves", []):
        want = MOVE_LABEL[m]
        cands = []
        for e in r.tried:
            lb = lab_of.get(id(e), ())
            if any(w in lb for w in want):
                cands.append(e)
        alt_w = ALT_LABEL.get(m, ())
        info = {"n_label": len(cands)}
        if not cands and alt_w:
            cands = [e for e in r.tried if any(w in lab_of.get(id(e), ()) for w in alt_w)]
            info["alt_label"] = bool(cands)
        if cands:
            ok = [e for e in cands if e.open_ok]
            best = None
            for e in sorted(ok, key=lambda e: -e.value_open):
                if not e.finished:
                    S.ev.finish(e)
                if e.safe:
                    best = e
                    break
            if best is not None:
                info.update(found=True, value=round(float(best.value), 3), hits=round(float(best.hits), 3),
                            origin=best.plan.origin, log=ms.plan_log(best))
            else:
                whys = Counter()
                for e in cands:
                    for o in e.outcomes:
                        if not o.safe:
                            whys[o.why.split("@")[0]] += 1
                            break
                info.update(found=False, why="unsafe", whys=dict(whys))
        else:
            prim = PRIM_OF[m]
            nwin = sum(v for k, v in S.stats.items() if k.startswith(f"win_{prim}"))
            why = ("timeout" if r.timed_out else "no window" if prim != "safe" and nwin == 0 else
                   "no candidate with the move's conditions")
            if m in REACTION_OF and not _reaction_seen(r.tried, *REACTION_OF[m]):
                why = "reaction not predicted"
            info.update(found=False, why=why, n_win=int(nwin))
        if info.get("alt_label") and info.get("found"):
            info["result"] = "alt"
        elif any(w in labels for w in want):
            info["result"] = "same"
        elif info.get("found"):
            info["result"] = "alt"
        else:
            info["result"] = "not"
        per[m] = info
    res["per"] = per
    return res


def _reaction_seen(tried, react: str, far: bool) -> bool:
    """Some outcome of a tried plan hooks an Idle / Walk Clapper that answers with `react` (from the far list when
    far) - the model predicts that reaction there."""
    from ssbot.map2 import search as ms, strike as sk
    for e in tried:
        for o in e.outcomes:
            for (P, iid, d, hooked, hit, ctrl) in getattr(o.tr, "claws", ()):
                if not hooked:
                    continue
                st = sk.state_at(o.branch, iid, P)
                if st is None or st[0] not in ("Idle", "Walk"):
                    continue
                rk = ms.reaction_key(o.branch, P)
                if (iid, react) not in rk:
                    continue
                if far and not any(c[0] == "far" and P + 7 <= c[2] <= P + 23 for c in o.branch.choices.get(iid, ())):
                    continue
                return True
    return False


def merge_split(res: list) -> list:
    """A split search's parts merged per situation (M4b): the chosen plan is the best part's (safe first, then
    the value), its labels; per move found when any part found it (the best value), 'same' when the merged chosen
    plan has the move's label; the times: the slowest part; the counters summed."""
    by: dict = {}
    for r in res:
        by.setdefault(r["i"], []).append(r)
    out = []
    for i, rr in sorted(by.items()):
        ok = [r for r in rr if "error" not in r]
        if not ok:
            out.append(dict(rr[0], part=None))
            continue
        best = max(ok, key=lambda r: (bool(r["safe"]), r["value"] if r["value"] is not None else -9.0))
        m = dict(best)
        m["part"] = None
        m["parts"] = len(rr)
        m["ms"] = max(r["ms"] for r in ok)
        for k in ("n_cand", "n_pred", "n_exit"):
            m[k] = sum(r.get(k) or 0 for r in ok)
        m["timed_out"] = any(r.get("timed_out") for r in ok)
        fs = [r.get("first_safe_ms") for r in ok if r.get("first_safe_ms") is not None]
        m["first_safe_ms"] = min(fs) if fs else None
        ev = sorted([a_ for r in ok for a_ in (r.get("anytime") or [])], key=lambda a_: a_[1])
        trace, cur = [], None
        for a_ in ev:
            if cur is None or (a_[3], a_[2]) > (cur[3], cur[2]):
                cur = a_
                trace.append(a_)
        m["anytime"] = trace
        st: dict = {}
        for r in ok:
            for k, v in (r.get("stats") or {}).items():
                if isinstance(v, (int, float)):
                    st[k] = st.get(k, 0) + v
        m["stats"] = st
        per = {}
        for mv in best["per"]:
            infos = [r["per"][mv] for r in ok if mv in r.get("per", {})]
            found = [x for x in infos if x.get("found")]
            if found:
                info = dict(max(found, key=lambda x: x.get("value") or -9.0))
            else:
                info = dict(next((x for x in infos if x.get("why") == "timeout"), infos[0]))
            want = MOVE_LABEL[mv]
            if info.get("alt_label") and info.get("found"):
                info["result"] = "alt"
            elif any(w in m["labels"] for w in want):
                info["result"] = "same"
            elif info.get("found"):
                info["result"] = "alt"
            else:
                info["result"] = "not"
            per[mv] = info
        m["per"] = per
        out.append(m)
    return out


def cmd_run(a) -> int:
    idle_priority()
    with open(OUT / "sits.pkl", "rb") as fh:
        sits = pickle.load(fh)
    from ssbot.knowledge import kinematics as km
    for s_ in sits:                          # states saved before M4a's rows (K 81 -> 83)
        s_.S = km.pad_state(s_.S)
    if a.limit:
        sits = sits[:a.limit]
    if a.only:
        sits = [s for s in sits if any(m in a.only.split(",") for m in s.meta["moves"])]
    if a.timeouts_of:
        # the situations whose search hit the cap in an earlier run (re-run with a longer cap: what time buys)
        prev = json.loads(Path(a.timeouts_of).read_text("utf-8"))
        names = {r["name"] for r in prev if r.get("timed_out")}
        sits = [s for s in sits if s.name in names]
    extra = {"prio": a.prio, "cfg": {"pass2_after": a.pass2_after}} if (a.prio != "idle" or a.pass2_after) else {}
    if a.safe_ts:
        extra.setdefault("cfg", {})["safe_ts"] = tuple(int(x) for x in a.safe_ts.split(","))
    if a.hold:
        extra["hold"] = int(a.hold)                  # M4c: the live prefix (1) and the hold filter's realizer (2)
    if a.vclock:
        extra["vclock"] = float(a.vclock)
    if a.cfg:
        # Cfg overrides k=v;k=v (M4b: the live configuration's flags)
        from ssbot.map2 import search as ms_
        for kv in a.cfg.split(";"):
            if kv.strip():
                k, v = kv.split("=")
                extra.setdefault("cfg", {})[k.strip()] = type(getattr(ms_.Cfg(), k.strip()))(eval(v))  # noqa: S307
        extra.setdefault("prio", a.prio)
    if a.split > 1:
        # a split search (M4b): each part of a situation its own job, merged per situation (merge_split)
        jobs = [(i, s, a.lib, a.cap, a.depth, dict(extra, part=(q, a.split))) for i, s in enumerate(sits)
                for q in range(a.split)]
    else:
        jobs = [(i, s, a.lib, a.cap, a.depth) + ((extra,) if extra else ()) for i, s in enumerate(sits)]
    jid = (lambda j: (j[0], j[5]["part"][0]) if len(j) > 5 and j[5].get("part") else (j[0], 0))
    t0 = time.time()
    res = []
    # every result as a line as it comes (M4a: a run whose pool lost its workers hung with 231 / 236 results in
    # memory): --resume takes the finished ones from it and runs the rest
    part = OUT / f"run_{a.lib}{a.tag}.partial.jsonl"
    done = {}
    if a.resume and part.exists():
        for line in part.read_text("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[(r["i"], (r.get("part") or [0])[0])] = r
        res = list(done.values())
        jobs = [j for j in jobs if jid(j) not in done]
        print(f"resume: {len(done)} done, {len(jobs)} to run", flush=True)
    elif part.exists():
        part.unlink()
    load = None
    if a.load:
        from ssbot.tools.m4b_speed import start_load
        load = start_load(4, 2)                      # the simulated load: 2 game instances, 2 bots (m4b_speed)
    if a.jobs > 1:
        # concurrent.futures: a worker that dies breaks the pool (BrokenProcessPool) instead of hanging it; the jobs
        # not finished are then re-submitted to a new pool (a job lost twice is recorded as an error)
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from concurrent.futures.process import BrokenProcessPool
        tries = Counter()
        left = {jid(j): j for j in jobs}
        n = len(res)
        with part.open("a", encoding="utf-8") as fh:
            while left:
                try:
                    # (workers recycled every 8 situations: a worker's caches grew to 11.7 GB and stalled the
                    # M4a run on a situation that takes 33 s alone)
                    with ProcessPoolExecutor(max_workers=a.jobs, max_tasks_per_child=8) as ex:
                        futs = {ex.submit(_run_one, j): i for i, j in left.items()}
                        for f in as_completed(futs):
                            i = futs[f]
                            r = f.result()
                            res.append(r)
                            fh.write(json.dumps(r, default=str) + "\n")
                            fh.flush()
                            left.pop(i, None)
                            n += 1
                            if n % 10 == 0:
                                print(f"{n}/{len(sits)} {time.time() - t0:.0f}s", flush=True)
                except BrokenProcessPool:
                    for i in list(left):
                        tries[i] += 1
                        if tries[i] >= 3:
                            r = {"i": i[0], "part": [i[1], a.split] if a.split > 1 else None,
                                 "name": left[i][1].name, "error": "worker lost"}
                            res.append(r)
                            fh.write(json.dumps(r, default=str) + "\n")
                            fh.flush()
                            left.pop(i)
                    print(f"a worker died: {len(left)} jobs re-submitted", flush=True)
    else:
        for j in jobs:
            res.append(_run_one(j))
            r = res[-1]
            print(r.get("name"), r.get("labels"), {m: v.get("result") for m, v in (r.get("per") or {}).items()},
                  r.get("ms"), r.get("error", ""), flush=True)
    if load is not None:
        from ssbot.tools.m4b_speed import stop_load
        stop_load(*load)
    if a.split > 1:
        res = merge_split(res)
    res.sort(key=lambda r: r["i"])
    out = OUT / f"run_{a.lib}{a.tag}.json"
    out.write_text(json.dumps(res, indent=1, default=str), "utf-8")
    print(f"done {len(res)} in {time.time() - t0:.0f}s -> {out}")
    return 0


# ---- the report ----------------------------------------------------------------------------------------------------

def _pct(v, qs=(50, 90, 99)):
    v = np.asarray([x for x in v if x is not None], float)
    if not len(v):
        return "-"
    return " / ".join(f"{np.percentile(v, q):.0f}" for q in qs)


def report_runs(runs: dict) -> str:
    lines = []
    for lib, res in runs.items():
        lines.append(f"=== run '{lib}' ({'primitives + the strike module only' if lib == 'none' else 'with the combo library'}"
                     f"): {len(res)} situations, errors {sum(1 for r in res if 'error' in r)}")
        tab = defaultdict(lambda: Counter())
        whys = defaultdict(Counter)
        alt_lab = defaultdict(Counter)
        safety = defaultdict(list)
        hits = defaultdict(list)
        for r in res:
            if "error" in r:
                continue
            for m, info in r["per"].items():
                src = r["meta"]["src"]
                tab[m][(src, info["result"])] += 1
                tab[m][("all", info["result"])] += 1
                tab[m][("all", "n")] += 1
                if info["result"] == "not":
                    w = info.get("why", "?")
                    if w == "unsafe" and info.get("whys"):
                        w = "unsafe:" + max(info["whys"], key=info["whys"].get)
                    whys[m][w] += 1
                if info["result"] == "alt":
                    alt_lab[m]["+".join(r["labels"]) or "(no strike)"] += 1
                safety[m].append(r["p_safe"] if r["p_safe"] is not None else 0.0)
                hits[m].append(r["hits"] or 0.0)
        lines.append(f"{'move':11s} {'n':>4s} {'same':>5s} {'alt':>4s} {'not':>4s}   by source (same/alt/not)          "
                     f"chosen plan: all-safe  E[hits]   not found: why")
        for m in MOVE_LABEL:
            if m not in tab:
                continue
            t = tab[m]
            bys = []
            for src in ("forced", "person", "rec"):
                n = sum(t[(src, x)] for x in ("same", "alt", "not"))
                if n:
                    bys.append(f"{src} {t[(src, 'same')]}/{t[(src, 'alt')]}/{t[(src, 'not')]}")
            sf = np.asarray(safety[m])
            lines.append(f"{m:11s} {t[('all', 'n')]:4d} {t[('all', 'same')]:5d} {t[('all', 'alt')]:4d} "
                         f"{t[('all', 'not')]:4d}   {', '.join(bys):34s} {np.mean(sf >= 0.999):.2f}     "
                         f"{np.mean(hits[m]):.2f}     " + ", ".join(f"{k} {v}" for k, v in whys[m].most_common(4)))
            if alt_lab[m]:
                lines.append(f"{'':11s} alt chosen: " + ", ".join(f"{k} {v}" for k, v in alt_lab[m].most_common(4)))
        # the person's hook cases: how the chosen plans do them
        det = defaultdict(Counter)
        for r in res:
            if "error" in r:
                continue
            for lb, (p_, d_) in (r.get("reactions") or {}).items():
                det[lb]["n"] += 1
                if "+umb" in str(d_):
                    det[lb]["umbrella"] += 1
        if det:
            lines.append("chosen plans showing a reaction move (situations; umbrella between control and the contact): " +
                         ", ".join(f"{lb} {c['n']}" + (f" (umb {c['umbrella']})" if c['umbrella'] else "")
                                   for lb, c in sorted(det.items())))
        ncont = sum(1 for r in res if r.get("contingent"))
        lines.append(f"contingent plans chosen (a continuation per reaction to a hook): {ncont}")
        ok = [r for r in res if "error" not in r]
        lines.append(f"decision time per situation (ms, p50 / p90 / p99): full search {_pct([r['ms'] for r in ok])}; "
                     f"the per-tick check of the committed plan {_pct([r.get('ms_check') for r in ok])} (fails "
                     f"{sum(1 for r in ok if r.get('check_ok') is False)}); "
                     f"the kept plan's full re-check {_pct([r['ms_tick'] for r in ok])}; predict calls "
                     f"{_pct([r['n_pred'] for r in ok])}, exit passes {_pct([r['n_exit'] for r in ok])}, candidates "
                     f"{_pct([r['n_cand'] for r in ok])}; timed out {sum(1 for r in ok if r['timed_out'])}")
        lines.append(f"horizon: chosen plans' frames to the last contact {_pct([r.get('last_contact') for r in ok])}, "
                     f"plan length {_pct([r.get('plan_frames') for r in ok])}")
        lines.append("")
    return "\n".join(lines)


def cmd_report(a) -> int:
    runs = {}
    for lib in ("none", "full"):
        p = OUT / f"run_{lib}{a.tag}.json"
        if p.exists():
            runs[lib] = json.loads(p.read_text("utf-8"))
    txt = report_runs(runs)
    (OUT / f"report{a.tag}.txt").write_text(txt, "utf-8")
    print(txt)
    return 0


# ---- the needed horizon (HP losses in the recordings) ------------------------------------------------------------

LEADS = (5, 10, 15, 20, 25, 30, 40, 50, 60, 80)


def _horizon_episode(args) -> list:
    path, every_n = args
    from ssbot.map2 import search as ms, strike as sk
    global _W
    if _W is None:
        _W = ms.World()
    W = _W
    with open(path, "rb") as fh:
        tr = pickle.load(fh)
    E = mv.Episode(tr)
    acts = mv.actual_decisions(E)
    mem_at = mv._memories(E)
    K = W.K
    out = []
    hits = sorted({g for (g, iid, skd, kind) in E.contacts if kind == "damage"})
    last = -999
    for gh in hits:
        if gh - last < 60:
            continue
        last = gh
        row = {"ep": tr["meta"]["id"], "g": int(gh), "exits": {}}
        for L in LEADS:
            g0 = gh - L
            if g0 < 30:
                continue
            S = rec_state(W, E, g0)
            if S is None:
                row["exits"][L] = None
                continue
            obs, mems = [], {}
            for jj in E.iids:
                mm = mem_at(jj, g0)
                o = E.obs(jj, g0, mm)
                if o is not None and o.st is not None:
                    obs.append(o)
                    mems[jj] = mm
            if not obs:
                continue
            T = L + 20
            hero = E.hero_path(g0, T, [o.iid for o in obs])
            try:
                P = cm.predict(obs, mems, hero, K, T=T, group=False, max_particles=400,
                               hazards=E.ghost_hazards(g0, {o.iid for o in obs}, K))
            except Exception:
                continue
            act_rel = {o.iid: [dict(d, k=d["g"] - g0) for d in acts.get(o.iid, ()) if g0 < d["g"] <= g0 + T]
                       for o in obs}
            real = next((b for b in P.branches
                         if all(mv.consistent(b.logs.get(o.iid, []), act_rel[o.iid], T) for o in obs)), None)
            if real is None:
                row["exits"][L] = None
                continue
            H = L + 15
            dz = [np.concatenate([ms.branch_danger(real, t, True), ms.WALL_BOXES]) for t in range(H + 1)]
            fw = W.E.forward(W.E.start_state(S), H, danger=dz, terrain=W.TT, max_events=2, claw=False)
            row["exits"][L] = int(fw.count(H))
        out.append(row)
    return out


def cmd_horizon(a) -> int:
    idle_priority()
    paths = sorted((M2DATA / "cache" / a.set).glob("*.pkl"))
    if a.limit:
        paths = paths[:a.limit]
    t0 = time.time()
    rows = []
    jobs = [(str(p), 1) for p in paths]
    if a.jobs > 1:
        from multiprocessing import Pool
        with Pool(a.jobs) as pool:
            for n, r in enumerate(pool.imap_unordered(_horizon_episode, jobs)):
                rows += r
                if n % 20 == 0:
                    print(f"{n + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    else:
        for j in jobs:
            rows += _horizon_episode(j)
    # per HP loss: the last lead (frames before the hit) with an exit; the vanish frame = the smallest lead >= it
    # with none ... the needed horizon is the earliest lead at which no exit exists while one existed earlier
    vanish, never, always = [], 0, 0
    for r in rows:
        ex = {int(k): v for k, v in r["exits"].items() if v is not None}
        if not ex:
            continue
        Ls = sorted(ex)
        with_exit = [L for L in Ls if ex[L] > 0]
        without = [L for L in Ls if ex[L] == 0]
        if not without:
            always += 1                  # an exit at every lead: the loss was a model miss / a choice
            continue
        if not with_exit:
            never += 1                   # no exit even 80 frames before
            continue
        # the largest lead without an exit that is below the smallest lead with one... (monotone usually)
        lo = max(L for L in without if L < max(with_exit)) if any(L < max(with_exit) for L in without) else None
        v = min(L for L in with_exit if lo is None or L > lo)
        vanish.append(v)
    res = {"set": a.set, "losses": len(rows), "vanish_leads": vanish, "always_exit": always, "never_exit": never,
           "p": {q: float(np.percentile(vanish, q)) for q in (10, 50, 90)} if vanish else {}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"horizon_{a.set}.json").write_text(json.dumps({"summary": res, "rows": rows}, default=str), "utf-8")
    print(json.dumps(res, default=str)[:3000])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="m3_accept")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("situations")
    p.add_argument("--sets", default="held")
    p.add_argument("--per-move", type=int, default=12)
    p.add_argument("--jobs", type=int, default=6)
    p.set_defaults(fn=cmd_situations)
    p = sub.add_parser("run")
    p.add_argument("--lib", default="none", choices=("none", "full"))
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--cap", type=float, default=30.0)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--only", default="")
    p.add_argument("--tag", default="")
    p.add_argument("--timeouts-of", default="", help="only the situations that timed out in this run json")
    p.add_argument("--resume", action="store_true", help="keep the finished situations of the partial results")
    p.add_argument("--prio", default="idle", choices=("idle", "high"),
                   help="the workers' priority: idle (offline), high (the live worker's rule, M4b)")
    p.add_argument("--pass2-after", type=int, default=0, help="Cfg.pass2_after (M4b's anytime order)")
    p.add_argument("--load", action="store_true", help="the simulated load of 2 games + 2 bots (M4b)")
    p.add_argument("--split", type=int, default=1, help="a split search: this many parts per situation (M4b)")
    p.add_argument("--safe-ts", default="", help="Cfg.safe_ts, comma-separated frames (M4b)")
    p.add_argument("--hold", type=int, default=0, help="M4c: 1 = every plan after one frame of no key (the live "
                                                         "prefix), 2 = and through the oracle's hold filter")
    p.add_argument("--vclock", type=float, default=0.0, help="the cap in work units: seconds per unit (deterministic)")
    p.add_argument("--cfg", default="", help="Cfg overrides k=v;k=v (M4b)")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("report")
    p.add_argument("--tag", default="")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("horizon")
    p.add_argument("--set", default="held")
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_horizon)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
