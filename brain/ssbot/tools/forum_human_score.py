"""The person's winning Forum games scored by the planner (task "the person's wins under the planner", forum.md §25):
open-loop replay of the person's recordings through ForumPlannerPolicy; per analysed tick the candidate row nearest
to what the person did, the planner's verdict on it, hindsight against the recorded colliders, and why the planner
ranks it below its own pick.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_human_score run --seg C:/ssbot/data/human/<session>:win:1,3
        [--seg <session>:w0] --out <dir> [--every 3] [--workers 3] [--threads 4] [--clash main] [--variants m0,g0]
        [--demo-cache <dir>] [--limit-s 0]
    ../scripts/uv.cmd run python -m ssbot.tools.forum_human_score summary <dir> [<dir> ...] [--json out.json]

Segments: "<session>:win:<attempts>" (forum_demo attempt indices: the whole attempt) or "<session>:w0[:<attempts>]"
(every attempt that cleared wave 0, or the ones listed: its wave-0 part, up to the first frame of wave index 1).
The planner's switches are the environment's (SSBOT_FORUM_FR / REACT / MARGIN / KF / PC / TV / T, read when the
worker builds its policy) and --clash (combat_run --forum-clash); the crest is the recording's (hero.crest).

Game time: a session recorded at time scale 0.5 (human_session --speed) has two STATEs per game frame (dt = 1/120 s);
consecutive pairs are merged into one STATE of a 1/60 s game frame (the second STATE with the pair's events, dt and
physics steps summed, the input masks or-ed, udt x 0.5 and ts / 0.5 as a 1x STATE reads: the kinematics step by
udt x ts and take ts < 1 for a world slow motion) and renumbered, so the planner, its kinematics and the hindsight all
run in game frames. The person's keys: STATE input.mask (gameplay buttons only) put into act.mask, so the policy's
prefix and hold state are the person's (the open-loop replay of tools.forum_hit_forensics, forum.md §19.1). The
planner's own jump / macro latches (jump_until, macro_until) come from its picks, which the replay never executes:
they are cleared before every frame (forum.md §25.11: otherwise "keep" ranks rows by a jump the person never held).

Per analysed tick (every `every`-th game frame; <out>/<session>_a<attempt>_<kind>.json):
  match     the recorded hero box centres of the next frames against every row's nominal box centre: err18 (mean
            over frames 1 .. 18), errH (the whole horizon); the best row: among the rows whose attack / jump / dash
            presses over frames 1 .. 18 (rising edges of the latched masks; the person's keys through the same hold
            filter) number the person's, the least err18, then errH (edge_ok False: no such row; the best row is then
            the position-only one, and the summary counts the tick outside the candidate set); best_pos: the
            position-only best row (the matching before forum.md §25.11); keys: the person's own masks rolled out
            from the tick's start state (the model's error on the person's keys, kerr18 / kerrH)
  person    what the person did over the next 18 frames (clips, cstate, buttons: harpoon, tool, bind, dash attack,
            wall, glide, down slash, air attacks, hurt) and whether a hit came within the horizon
  verdict   for the best row and the keys row: S (stage 1 centre / envelope / hit branch, computed when the planner
            left the row unknown), the planner's own S / known / ok, the row's rank in the planner's order (safe
            ticks: among the safe rows; FORCED_RISK: the preselection order), its keys; the pick's name and keys
  hindsight each row's first contact with the recorded damage colliders over its horizon (forum.md §19.1, open loop);
            all: the allowed rows and the planner's known unsafe rows, how many of each clear (the base rates)
  layers    a row judged unsafe: the support groups its centres meet (forum_layer_audit.classify, by layer, type and
            family), the layer categories each alone necessary (leave one out), margins / idle growth variants
  J         the best row and the pick: the score kernel's terms (hit, waste, jumps, stance, risk map, facing, ground)
            unweighted and the weights, cont / terminal, V / keep / mkeep, the escape check's failures
  context   targets, nearest enemies, fliers above, defending enemies
"""
import argparse
import json
import math
import random
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from ssbot.ipc.framing import BIT

GAME_MASK = sum(1 << BIT[n] for n in ("jump", "attack", "dash", "bind", "clawline", "needolin", "quickcast", "taunt",
                                      "up", "down", "left", "right"))
EARLY_K = 18
CLOSE_U = 0.35                  # summary default: a row within this mean centre error over 18 frames matches
FLYERS = frozenset({"Song Reed", "Song Administrator", "Song Pilgrim Maestro", "Song Automaton Tiny"})
DEFEND_FAMS = frozenset({"RE_DEFEND", "MI_PARRY"})
# forum_layer_audit layers -> the categories of the task
CATEGORY = {"body": "body", "collider": "body", "idle_now": "body",
            "com_fine": "committed", "com_bbox": "committed", "chain_fine": "committed", "chain_bbox": "committed",
            "tail": "tail",
            "com_win": "window", "com_fam": "window", "chain_win": "window",
            "start_attack": "not_started", "start_idle": "not_started", "entry_later": "not_started",
            "entry_now": "entry",
            "haz_self": "projectile", "haz_path": "projectile", "haz_tube": "projectile",
            "death": "death", "arena": "arena"}
TERMS = ("hit", "waste", "jump", "stance", "risk", "face", "ground")
DASH_ATTACK_CLIPS = ("Dash Upper", "Wanderer Dash Attack", "DashStab", "Dash Stab", "Dash Attack")


# ---------------------------------------------------------------------------------------------------- segments

def _rows_index(s: dict) -> dict:
    return {r["f"]: i for i, r in enumerate(s["rows"])}


def segments(spec: str, cache: Path | None) -> list[dict]:
    """The segments of one --seg spec (module docstring)."""
    from ssbot.tools.forum_demo import attempts, load
    path, _, rest = spec.partition(":")
    if len(path) == 1 and rest:              # a drive letter
        p2, _, rest = rest.partition(":")
        path = path + ":" + p2
    kind, _, which = rest.partition(":")
    session = Path(path)
    s = load(session, cache)
    fi = _rows_index(s)
    rows = s["rows"]
    want = {int(x) for x in which.split(",") if x} if which else None
    out = []
    for n, a in enumerate(attempts(s)):
        if want is not None and n not in want:
            continue
        i0, i1 = fi[a["f0"]], fi[a["f1"]]
        ts = rows[i0]["ts"] if rows[i0]["ts"] is not None else 1.0
        crest = a.get("crest") or rows[i0].get("crest")
        if kind == "win":
            out.append({"session": str(session), "attempt": n, "kind": "win", "f0": a["f0"], "f1": a["f1"],
                        "ts": ts, "crest": crest, "outcome": a.get("outcome")})
        elif kind == "w0":
            w1 = next((rows[j]["f"] for j in range(i0, i1 + 1)
                       if rows[j]["b_started"] and (rows[j]["b_wave"] or 0) >= 1), None)
            if w1 is None:
                continue
            out.append({"session": str(session), "attempt": n, "kind": "w0", "f0": a["f0"], "f1": w1, "ts": ts,
                        "crest": crest, "outcome": a.get("outcome")})
        else:
            raise ValueError(f"--seg {spec!r}: kind win or w0")
    return out


def _merge_pair(a: dict, b: dict, f: int, base: float) -> dict:
    """One game frame from two STATEs at time scale `base` (0.5): as a 1x STATE would read (the kinematics take
    dt = udt x ts, and a time scale below 1 for a world slow motion: ts / base, udt x base)."""
    m = dict(b)
    m["f"] = f
    m["_f_raw"] = b["f"]
    m["dt"] = float(a.get("dt") or 0.0) + float(b.get("dt") or 0.0)
    m["udt"] = (float(a.get("udt") or 0.0) + float(b.get("udt") or 0.0)) * base
    m["ts"] = min(1.0, float(b.get("ts") or 0.0) / base)
    m["fs"] = int(a.get("fs") or 0) + int(b.get("fs") or 0)
    evs = []
    for e in list(a.get("ev") or ()) + list(b.get("ev") or ()):
        if "f" in e:
            e = dict(e, f=f)
        evs.append(e)
    m["ev"] = evs
    ia, ib = a.get("input") or {}, b.get("input") or {}
    m["input"] = dict(ib, mask=int(ia.get("mask") or 0) | int(ib.get("mask") or 0))
    return m


def load_segment(seg: dict) -> tuple[dict | None, list[dict]]:
    """(the Hang_04 TERRAIN message, the segment's STATEs in game frames with the person's keys as act.mask)."""
    from ssbot.ipc.framing import MsgType
    from ssbot.tools.forum_demo import _stream
    terrain = None
    out: list[dict] = []
    pend = None
    half = seg["ts"] is not None and seg["ts"] < 0.75
    f_next = seg["f0"]
    for t, m in _stream(Path(seg["session"]) / "state.raw.zst"):
        if t == MsgType.TERRAIN:
            if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
                terrain = m
            continue
        if t != MsgType.STATE:
            continue
        f = m["f"]
        if f < seg["f0"]:
            continue
        if f > seg["f1"]:
            break
        if half:
            if pend is None:
                pend = m
                continue
            m = _merge_pair(pend, m, f_next, float(seg["ts"]))
            pend = None
        else:
            m["_f_raw"] = f
            m["f"] = f_next
        f_next += 1
        m["act"] = {"mask": int((m.get("input") or {}).get("mask") or 0) & GAME_MASK}
        out.append(m)
    return terrain, out


# ---------------------------------------------------------------------------------------------------- per frame

def frame_info(states: list[dict]) -> dict:
    """Compact per-frame arrays: hero box [n, 4], masks, clips, cstate flags, damage frames, hp."""
    from ssbot.tools.forum_demo import _cs_index, _flags
    idx = _cs_index()
    n = len(states)
    box = np.full((n, 4), np.nan)
    mask = np.zeros(n, np.int64)
    clip: list = []
    fl = {k: np.zeros(n, bool) for k in ("onGround", "dashing", "wallClinging", "wallSliding", "attacking")}
    dmg = np.zeros(n, bool)
    hp = np.zeros(n, np.int64)
    for i, s in enumerate(states):
        h = s.get("hero") or {}
        b = h.get("box")
        if b:
            box[i] = b[:4]
        mask[i] = int((s.get("act") or {}).get("mask") or 0)
        clip.append((h.get("anim") or {}).get("clip"))
        f = _flags(h.get("cstate"), idx) if h.get("cstate") else {}
        for k in fl:
            fl[k][i] = bool(f.get(k, False))
        dmg[i] = any(ev.get("k") == "damage" for ev in s.get("ev") or ())
        hp[i] = int(h.get("health") or 0)
    return {"box": box, "mask": mask, "clip": clip, "fl": fl, "dmg": dmg, "hp": hp}


def person_action(fi: dict, i: int, k: int = EARLY_K) -> dict:
    """What the person did over frames i + 1 .. i + k (module docstring)."""
    from ssbot.knowledge import kinematics as kin
    j1 = min(len(fi["mask"]), i + k + 1)
    clips = [c for c in fi["clip"][i + 1:j1] if c]
    m = fi["mask"][i:j1]
    rise = m[1:] & ~m[:-1]
    air = ~fi["fl"]["onGround"][i + 1:j1]
    att = (rise & kin.B_ATTACK) != 0
    out = {
        "harpoon": any(c.startswith("Harpoon") for c in clips) or bool((rise & (1 << BIT["clawline"])).any()),
        "tool": bool((rise & ((1 << BIT["quickcast"]) | (1 << BIT["needolin"]))).any()),
        "bind": any(c.startswith("BindCharge") for c in clips) or bool((rise & (1 << BIT["bind"])).any()),
        "dash_attack": any(any(c.startswith(d) for d in DASH_ATTACK_CLIPS) for c in clips),
        "wall": bool(fi["fl"]["wallClinging"][i + 1:j1].any() or fi["fl"]["wallSliding"][i + 1:j1].any()),
        "glide": any(c.startswith("Umbrella") for c in clips),
        "down_slash": any("DownSlash" in c or "Down Slash" in c for c in clips),
        "hurt": bool(fi["dmg"][i + 1:j1].any()),
        "air_attacks": int((att & air[:len(att)]).sum()),
        "attacks": int(att.sum()), "jumps": int(((rise & kin.B_JUMP) != 0).sum()),
        "dashes": int(((rise & kin.B_DASH) != 0).sum()),
        "air0": bool(not fi["fl"]["onGround"][i]),
    }
    return out


EDGE_NAMES = ("attack", "jump", "dash")


def press_counts(prev: int, masks: np.ndarray, k: int = EARLY_K) -> np.ndarray:
    """[N, 3] rising edges of attack / jump / dash over frames 1 .. k of each row of masks [N, >= k] (frame j's
    command in column j - 1), the press on frame 1 against `prev` (the latched mask before it)."""
    from ssbot.knowledge import kinematics as kin
    m = np.asarray(masks, np.int64)[:, :k]
    before = np.concatenate([np.full((m.shape[0], 1), int(prev), np.int64), m[:, :-1]], axis=1)
    rise = m & ~before
    return np.stack([((rise & b) != 0).sum(axis=1) for b in (kin.B_ATTACK, kin.B_JUMP, kin.B_DASH)], axis=1)


def latched_mask(hold) -> int:
    """The hold filter state's latched keys as a button mask (lane 0)."""
    return int(sum(1 << int(b) for b in np.flatnonzero(np.asarray(hold.latched)[0])))


def match_rows(err18: np.ndarray, errH: np.ndarray, row_edges: np.ndarray, person_edges: np.ndarray
               ) -> tuple[int, bool, int, list]:
    """(the best row, whether it has the person's presses, the rows that do, the buttons no row matches alone): the
    least err18 then errH among the rows whose attack / jump / dash press counts equal the person's; with none, the
    position-only best."""
    same = (row_edges == person_edges[None]).all(axis=1)
    miss = [EDGE_NAMES[j] for j in range(len(EDGE_NAMES)) if not (row_edges[:, j] == person_edges[j]).any()]
    order = np.lexsort((errH, err18))
    if same.any():
        return int(order[same[order]][0]), True, int(same.sum()), miss
    return int(order[0]), False, 0, miss


def action_class(a: dict) -> str:
    for k in ("hurt", "bind", "harpoon", "tool", "dash_attack", "wall", "glide", "down_slash"):
        if a.get(k):
            return k
    if a.get("air_attacks", 0) >= 2:
        return "air_combo"
    return "other"


# ---------------------------------------------------------------------------------------------------- the policy

_POL: dict = {}


def _policy(crest: str, threads: int, clash: str, variants: tuple):
    key = crest
    if key in _POL:
        return _POL[key]
    import dataclasses
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    pol = ForumPlannerPolicy(threads=threads, crest=crest, clash=clash)
    pol.warmup()
    step0 = pol.sc.step

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else \
            dataclasses.replace(r, mask=None, outcome=None)
    pol.sc.step = step
    vs = None
    if variants:
        from ssbot.tools.forum_layer_audit import Variants
        vs = Variants(pol.fc, variants)
    _POL[key] = (pol, {"wrapped": False}, vs)
    return _POL[key]


def _wrap(pol, cap: dict) -> None:
    """Capture each tick's arguments and its score dict (no effect on any decision)."""
    if cap.get("wrapped"):
        return
    pl = pol.planner
    tick0, score0 = pl.tick, pl._score_forum

    def tick(ws, start, hold, prefix, f, prefs, ctx):
        cap["args"] = (ws, start, hold, prefix, f, prefs, ctx)
        cap["sc"] = None
        return tick0(ws, start, hold, prefix, f, prefs, ctx)

    def score(*a, **k):
        r = score0(*a, **k)
        cap["sc"] = r
        return r
    pl.tick = tick
    pl._score_forum = score
    cap["score0"] = score0
    cap["wrapped"] = True


def _centres(box: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return 0.5 * (box[..., 0] + box[..., 2]), 0.5 * (box[..., 1] + box[..., 3])


def _hind(fp, box: np.ndarray, inv: np.ndarray, fo: int) -> int:
    """First contact frame (1 .. ) of one row's nominal box with the recorded damage colliders, -1: none."""
    from ssbot.tools.forum_hit_forensics import first_contact
    fb, m = fp.window(fo, box.shape[0])
    return int(first_contact(np.ascontiguousarray(box[None], np.float64), np.ascontiguousarray(inv[None]),
                             fp.verts, fp.starts, fb, m, 0.0)[0])


def _hind_all(fp, box: np.ndarray, inv: np.ndarray, fo: int) -> np.ndarray:
    """[N] first contact frames (-1: none) of every row's nominal box [N, T1, 4]."""
    from ssbot.tools.forum_hit_forensics import first_contact
    fb, m = fp.window(fo, box.shape[1])
    return first_contact(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(inv), fp.verts, fp.starts, fb,
                         m, 0.0)


def _owner(fp, fo: int, k: int, box) -> list:
    return [list(x) for x in fp.who(fo + k, box)][:2]


def verdict(pl, cap: dict, fcast, start, latched_row: np.ndarray, roll=None, sc_row=None) -> dict:
    """The planner's S for one row (latched [P + T]): stage 1 (the nominal box centre on stage 1's frames), the
    envelope (bounds_lo lanes' hull), the hit branch (uncapped); roll: its nominal rollout (None: rolled here);
    sc_row: its score dict (None: scored here)."""
    from ssbot.knowledge import kinematics as kin
    from ssbot.knowledge.kinematics import F_INVULN
    ws, _, _, _, f, prefs, ctx = cap["args"]
    params, terrain, threads = pl.params, pl.terrain, pl.cfg.threads
    lat = np.ascontiguousarray(latched_row[None], np.int64)
    if roll is None:
        roll = kin.rollout(start, lat, params, terrain, threads=threads)
    T1 = roll.box.shape[1]
    tk = np.arange(T1, dtype=np.float64) * params.frame_time
    enemy_only = not any(fm.hazard for fm in f.fc.model.families.values())
    fr = pl._s1_frames(T1)
    cx, cy = _centres(roll.box[:, fr])
    o = f.occupied(cx, cy, tk[fr])
    if enemy_only:
        o &= (roll.flags[:, fr] & F_INVULN) == 0
    s1 = bool(o.any())
    r2 = kin.rollout(start, lat, params, terrain, variants=pl.fcfg.variants, threads=threads)
    skip = ((r2.flags_all & F_INVULN) != 0) if enemy_only else np.zeros(r2.flags_all.shape, bool)
    occ = pl._contacts(f, r2.bound, tk, skip)
    s_env = bool(occ.any())
    t_env = int(occ.argmax(axis=1)[0]) if s_env else -1
    if sc_row is None:
        sc_row = cap["score0"](ws, roll, lat, start, f, prefs, tk, ctx)
    s_hit = False
    has_hit = bool(sc_row["first_f"][0] >= 0)
    if not s_env and has_hit:
        budget = {"hitfx": 0, "react": 0, "capped": 0, "react_cache": {}}
        sh, _, _ = pl._hit_branch(f, start, lat, sc_row, np.array([0], np.int64), tk, enemy_only, budget, cap=False)
        s_hit = bool(sh[0])
    S = s1 or s_env or s_hit
    src = "stage1" if s1 else "envelope" if s_env else "hit_branch" if s_hit else None
    return {"S": bool(S), "src": src, "t_env": t_env, "has_hit": has_hit, "hits": float(sc_row["hits"][0]),
            "unmod": bool(sc_row["unmod"][0]), "J": float(sc_row["J"][0]), "roll": roll, "sc": sc_row}


def layers_of(fcast, groups, box: np.ndarray, inv: np.ndarray, tk: np.ndarray) -> dict:
    """The support groups one row's centres (frames 1 .. T1 - 1, invulnerable ones clear) meet: per category the
    frames and the first frame, per group (layer, type, family) the frames; the categories each necessary (leave one
    out: without it the centre path is clear)."""
    from ssbot.tools.forum_layer_audit import group_occ
    cx, cy = _centres(box[1:])
    live = ~inv[1:]
    occ = group_occ(fcast, cx[None], cy[None], tk[1:], live[None], groups)
    cats: dict = {}
    grp = []
    for key, o in occ.items():
        o = o[0]
        if not o.any():
            continue
        c = CATEGORY.get(key[0], key[0])
        n, k0 = int(o.sum()), int(o.argmax()) + 1
        if c not in cats:
            cats[c] = [n, k0, o.copy()]
        else:
            cats[c][0] = int((cats[c][2] | o).sum())
            cats[c][1] = min(cats[c][1], k0)
            cats[c][2] |= o
        grp.append([key[0], key[1], key[2], n, k0])
    grp.sort(key=lambda g: (g[4], -g[3]))
    need = []
    for c in cats:
        rest = np.zeros(len(live), bool)
        for c2, v in cats.items():
            if c2 != c:
                rest |= v[2]
        if not rest.any():
            need.append(c)
    return {"cats": {c: v[:2] for c, v in cats.items()}, "need": need, "groups": grp[:8]}


def variant_clear(pol, vs, fcast, box: np.ndarray, inv: np.ndarray, tk: np.ndarray) -> dict:
    """Per variant (m0: margins x 0, g0: idle growth x 0): the row's centre path clear of the variant's support."""
    from ssbot.train.planner_policy import HORIZON_S
    out = {}
    cx, cy = _centres(box[1:])
    live = ~inv[1:]
    try:
        for v in vs.sets:
            vs.swap(v)
            f2 = pol.fc.forecast(HORIZON_S, origin_t=fcast.origin_t)
            out[v] = not bool((f2.occupied(cx[None], cy[None], tk[1:]) & live[None]).any())
    finally:
        vs.restore()
    return out


def j_terms(pl, cap: dict, box, flags, mode, latched) -> np.ndarray:
    """[n, 7] the score kernel's terms (TERMS, unweighted: hits, -waste, -jumps, -stance, -risk, face, ground)."""
    from ssbot.combat.forum_planner import WALL_L, WALL_R, _forum_score_kernel
    from ssbot.knowledge import kinematics as kin
    ws, start, _, _, f, prefs, ctx = cap["args"]
    n, T1 = flags.shape
    tk = np.arange(T1, dtype=np.float64) * pl.params.frame_time
    face0 = 1 if np.asarray(start).reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
    tbox, tok, tw, keep = pl._forum_targets(ws, f, tk, prefs)
    rx = prefs.risk_x if len(prefs.risk_x) else np.zeros(1)
    rv = prefs.risk if len(prefs.risk) else np.zeros(1)
    vr, vl, st, win = pl.shapes
    real = np.array([not t.hazard for t in keep], np.bool_)
    out = np.zeros((n, len(TERMS)))
    for t in range(len(TERMS)):
        wv = np.zeros(8)
        wv[t] = 1.0
        J = np.zeros(n)
        # the kernel's target weights are [K, 4] by slash kind (track A, GoalPrefs.hit_kw) and it counts the hits
        # landed (nh); the J terms track A adds after the kernel (under, eml, whip) are not in TERMS
        _forum_score_kernel(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(flags),
                            np.ascontiguousarray(mode), np.ascontiguousarray(latched, np.int64), face0,
                            tbox if len(keep) else np.zeros((0, T1, 4)), tok if len(keep) else np.zeros((0, T1), bool),
                            np.ascontiguousarray(tw, np.float64), vr, vl, st, win, WALL_L, WALL_R, wv,
                            float(prefs.stance_x),
                            np.ascontiguousarray(rx, np.float64), np.ascontiguousarray(rv, np.float64),
                            prefs.boss_x if prefs.boss_x is not None else np.nan,
                            float(prefs.max_hits) if prefs.max_hits is not None else np.inf,
                            J, np.zeros(n), np.full(n, -1, np.int64), np.full(n, -1, np.int64), np.zeros(n, np.int64),
                            np.zeros(n, np.int64), np.zeros(n), np.zeros(n, np.bool_), pl.down_slash, pl.combo_f,
                            np.full(n, -1, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), real,
                            np.zeros(n), np.zeros(len(real), np.bool_))
        out[:, t] = J
    return out


def weights(prefs) -> list:
    w = prefs.weights
    return [w.get("hit", 10.0), w.get("waste", 0.6), w.get("jump", 0.15), w.get("stance", 0.6), w.get("risk", 3.0),
            w.get("face", 0.3), w.get("ground", 0.2)]


def escape_fails(pl, cap: dict, row_full: np.ndarray) -> tuple[int | None, list]:
    """The escape check's failures of one row (full commands [P + T]); None: no check (off / no threats)."""
    from ssbot.combat.holdfilter import hold_filter_jit
    from ssbot.knowledge import kinematics as kin
    if not pl.fcfg.escape:
        return None, []
    ws, start, hold, _, f, _, _ = cap["args"]
    full = np.ascontiguousarray(row_full[None], np.int64)
    lat, hold_end = hold_filter_jit(full, hold)
    r1 = kin.rollout(start, lat, pl.params, pl.terrain, threads=pl.cfg.threads)
    hero = (0.0, 0.0) if ws is None or ws.hero is None else (float(ws.hero.pos.v[0]), float(ws.hero.pos.v[1]))
    row, nf, _, nth, lab = pl._escape_pick(f, start, hold, full, hold_end, r1, np.array([0], np.int64), hero, 1, None)
    if row is None:
        return None, []
    return int(nf), sorted(set(lab))


def _order_keys(ls: dict) -> list:
    """The planner's selection keys (ForumPlanner.tick's lexsort, primary first) over every row."""
    return [ls["hz"], ls["hz_soft"], ls["U"], ls["S"], ls["clash_p"], ~ls["keep"], ~ls["mkeep"], ~ls["V"],
            ls["sk_n"], -ls["sk_f"], ls["sk_c"], ls["Pc"], ls["Pcm"], ls["Pf"], -ls["t_c"], -ls["t_hit"], -ls["J"]]


KEY_NAMES = ("hz", "hz_soft", "U", "S", "clash_p", "keep", "mkeep", "V", "seen", "seen_first", "seen_cf", "P", "P_cm",
             "P_f", "t_c", "t_hit", "J")
PRE_NAMES = ("seen", "seen_first", "seen_cf", "P_cm", "P_f", "t_hit", "J")     # FORCED_RISK's preselection


def _rank(keys: list, pool: np.ndarray, n: int, over: dict | None = None, names: tuple = KEY_NAMES
          ) -> tuple[int, str | None]:
    """1 + the rows of `pool` ahead of row n in the lexicographic order of keys (over: n's own key values that the
    planner did not compute), and the first key that puts the pool's best row ahead of n."""
    vals = [np.asarray(k, np.float64) for k in keys]
    vn = [float(v[n]) for v in vals]
    if over:
        for i, x in over.items():
            vn[i] = float(x)
    ahead = np.zeros(len(pool), bool)
    tie = np.ones(len(pool), bool)
    for v, x in zip(vals, vn):
        a = v[pool]
        ahead |= tie & (a < x)
        tie &= a == x
    rank = int(ahead[pool != n].sum()) + 1
    first = None
    if ahead.any():
        b = pool[np.lexsort(tuple(v[pool] for v in reversed(vals)))][0]
        for name, v, x in zip(names, vals, vn):
            if v[b] != x:
                first = name
                break
    return rank, first


def context(ws, fcast, prefs, tac_last: dict, hero) -> dict:
    hx, hy = hero
    subs = []
    for sj in fcast.subjects:
        if not (sj.alive and sj.in_play) or sj.pos is None:
            continue
        dx, dy = float(sj.pos[0]) - hx, float(sj.pos[1]) - hy
        subs.append((math.hypot(dx, dy), sj, dx, dy))
    subs.sort(key=lambda z: z[0])
    tgt = next((z for z in subs if z[1].iid == prefs.target), None)
    return {"n": len(subs),
            "near": [[z[1].type_key, z[1].family, z[1].state, round(z[0], 2), round(z[2], 2), round(z[3], 2)]
                     for z in subs[:3]],
            "tgt": None if tgt is None else [tgt[1].type_key, tgt[1].family, tgt[1].state, round(tgt[0], 2)],
            "tgt_type": tac_last.get("target_type"), "goal": getattr(prefs, "goal", None), "mode": prefs.mode,
            "stance_x": round(float(prefs.stance_x), 2), "boss_x": prefs.boss_x,
            "flier_above": any(z[1].type_key in FLYERS and abs(z[2]) < 1.5 and 1.0 < z[3] < 6.0 for z in subs),
            "defending": [z[1].type_key for z in subs if z[1].family in DEFEND_FAMS and z[0] < 6.0]}


def analyse(pol, cap: dict, vs, i: int, states: list, fi: dict, fp, groups_cache: dict) -> dict | None:
    from ssbot.knowledge import kinematics as kin
    from ssbot.knowledge.kinematics import F_INVULN
    from ssbot.tools.forum_layer_audit import classify
    pl = pol.planner
    li = pl.last_info or {}
    dbg = li.get("dbg")
    res = pol.planner_last
    ls = pl.last_sel
    if dbg is None or res is None or res.idx < 0 or cap.get("args") is None or ls is None:
        return None
    ws, start, hold, prefix, fcast, prefs, ctx = cap["args"]
    box, flags, mode, latched = dbg["box"], dbg["flags"], dbg["mode"], dbg["latched"]
    N, T1 = flags.shape
    fo = int(states[i]["f"])
    m = min(T1, len(states) - i)
    if m < EARLY_K + 1:
        return None
    pb = fi["box"][i:i + m]
    pcx, pcy = _centres(pb)
    rcx, rcy = _centres(box[:, :m])
    d = np.hypot(rcx[:, 1:] - pcx[None, 1:], rcy[:, 1:] - pcy[None, 1:])
    d = np.where(np.isfinite(d), d, 99.0)
    err18, errH = d[:, :EARLY_K].mean(axis=1), d.mean(axis=1)
    best_pos = int(np.lexsort((errH, err18))[0])
    # the person's own keys from the tick's start state (the prefix is the recorded next frame already)
    P = int(dbg["P"])
    pm = np.zeros(T1 - 1, np.int64)
    seg = fi["mask"][i + 1:i + T1]
    pm[:len(seg)] = seg
    if len(seg) < T1 - 1 and len(seg):
        pm[len(seg):] = seg[-1]
    # the presses: rows' latched masks against the person's keys through the same hold filter
    from ssbot.combat.holdfilter import hold_filter_jit
    prev = latched_mask(hold)
    p_lat, _ = hold_filter_jit(pm[None], hold)
    pe = press_counts(prev, p_lat)[0]
    re_ = press_counts(prev, latched)
    best, edge_ok, n_edge, edge_miss = match_rows(err18, errH, re_, pe)
    rk = kin.rollout(start, pm[None], pl.params, pl.terrain, threads=pl.cfg.threads)
    kcx, kcy = _centres(rk.box[0, :m])
    kd = np.hypot(kcx[1:] - pcx[1:], kcy[1:] - pcy[1:])
    kd = np.where(np.isfinite(kd), kd, 99.0)
    inv_rows = (flags & F_INVULN) != 0
    forced = bool(res.forced_risk)
    S_pl, known, ok = li["S"], dbg["known"], dbg["ok"]
    pick = int(res.idx)
    names = dbg["names"]
    tk = dbg["tk"]
    # ---- verdicts ----
    vb = verdict(pl, cap, fcast, start, latched[best], roll=_RollRow(box[best], flags[best], mode[best]),
                 sc_row=_sc_row(cap["sc"], best))
    vk = verdict(pl, cap, fcast, start, pm, roll=rk)
    h_all = _hind_all(fp, box, inv_rows, fo)
    hb = int(h_all[best])
    hk = _hind(fp, rk.box[0], (rk.flags[0] & F_INVULN) != 0, fo)
    hp_ = int(h_all[pick])
    unsafe_known = known & (np.asarray(S_pl) != 0)
    hit_f = np.flatnonzero(fi["dmg"][i + 1:i + T1])
    pool = np.flatnonzero(ok & known)
    keys = _order_keys(ls)
    over = {}
    if not known[best]:
        over[KEY_NAMES.index("S")] = int(vb["S"])
    safe_pool = pool[~np.asarray(ls["S"], bool)[pool]] if not forced else pool
    if forced:
        pre_keys = [ls["sk_n"], -ls["sk_f"], ls["sk_c"], ls["Pcm"], ls["Pf"], -ls["t_hit"], -ls["J"]]
        rank, why = _rank(pre_keys, pool, best, names=PRE_NAMES) if ok[best] and known[best] else (None, None)
    else:
        rank, why = _rank(keys, safe_pool, best, over) if ok[best] and not vb["S"] else (None, None)
    rec = {"i": i, "f": fo, "f_raw": states[i].get("_f_raw"), "wave": _wave(states[i]), "hp": int(fi["hp"][i]),
           "forced": forced, "n_safe": int(res.n_safe), "N": N, "m": m, "posture": li.get("posture"),
           "pick": [names[pick] if pick < len(names) else str(pick), int(S_pl[pick]), hp_],
           "pick_first": int(ls.get("first", pick)), "chosen_moved": int(ls.get("first", pick)) != pick,
           "best": [names[best], round(float(err18[best]), 3), round(float(errH[best]), 3)],
           "edge_ok": edge_ok, "n_edge": n_edge, "edges": [int(x) for x in pe], "edge_miss": edge_miss,
           "best_pos": [names[best_pos], round(float(err18[best_pos]), 3), round(float(errH[best_pos]), 3),
                        bool((re_[best_pos] == pe).all()), best_pos == best],
           "pick_err": [round(float(err18[pick]), 3), round(float(errH[pick]), 3), bool((re_[pick] == pe).all())],
           "all": [int(ok.sum()), int((ok & (h_all < 0)).sum()), int(unsafe_known.sum()),
                   int((unsafe_known & (h_all < 0)).sum())],
           # the rows the planner called safe (allowed, known, S = 0) and how many of them clear in hindsight
           "safe_rows": [int((ok & known & (np.asarray(S_pl) == 0)).sum()),
                         int((ok & known & (np.asarray(S_pl) == 0) & (h_all < 0)).sum())],
           "kerr": [round(float(kd[:EARLY_K].mean()), 3), round(float(kd.mean()), 3)],
           "same_as_pick": best == pick,
           "person": person_action(fi, i), "hit_in": int(hit_f[0]) + 1 if len(hit_f) else -1,
           "vb": {"S": vb["S"], "src": vb["src"], "pl_S": int(S_pl[best]), "known": bool(known[best]),
                  "ok": bool(ok[best]), "hind": hb, "rank": rank, "why": why, "J": round(float(dbg["J"][best]), 3),
                  "hits": vb["hits"], "unmod": vb["unmod"], "t_env": vb["t_env"],
                  "keys": {k: round(float(np.asarray(ls[k])[best]), 4) for k in ("sk_n", "sk_c", "Pc", "Pcm", "Pf",
                                                                                 "t_hit", "V", "keep", "mkeep")}},
           "vk": {"S": vk["S"], "src": vk["src"], "hind": hk, "hits": vk["hits"], "unmod": vk["unmod"],
                  "J": round(vk["J"], 3)},
           "pick_keys": {k: round(float(np.asarray(ls[k])[pick]), 4) for k in ("sk_n", "sk_c", "Pc", "Pcm", "Pf",
                                                                                "t_hit", "V", "keep", "mkeep", "J")},
           "ctx": context(ws, fcast, prefs, pol.tac.last, (float(ws.hero.pos.v[0]), float(ws.hero.pos.v[1])))}
    # ---- layers of an unsafe row (the best row and the keys row) ----
    gk = id(fcast)
    if gk not in groups_cache:
        groups_cache.clear()
        groups_cache[gk] = classify(fcast)
    groups = groups_cache[gk]
    for tag, v, bx, iv in (("vb", vb, box[best], inv_rows[best]),
                           ("vk", vk, rk.box[0], (rk.flags[0] & F_INVULN) != 0)):
        if not v["S"]:
            continue
        rec[tag]["layers"] = layers_of(fcast, groups, bx, iv, tk)
        if vs is not None and (rec[tag]["hind"] < 0 or vs.react):
            # (the reactive variants also on the rows hit in hindsight: the true alarms they would remove)
            rec[tag]["var"] = variant_clear(pol, vs, fcast, bx, iv, tk)
    if vs is not None and vs.react and pl.fcfg.escape and ok[best]:
        # the escape check on the person's row where it would be safe: under the base config when safe, under each
        # reactive variant (its threats: ForumConfig.body_reach) when safe or freed by it (task forum push 2 track B)
        full_b = np.concatenate([np.asarray(prefix, np.int64), ls["cmd"][best]])
        if not vb["S"]:
            rec["vb"]["esc_b"] = escape_fails(pl, cap, full_b)[0]
        ve = {}
        react0 = pl.fcfg.react
        try:
            for v in vs.react:
                if not vb["S"] or (rec["vb"].get("var") or {}).get(v):
                    pl.fcfg.react = react0 + ("+br" if v == "rbr" else "+b")
                    ve[v] = escape_fails(pl, cap, full_b)[0]
        finally:
            pl.fcfg.react = react0
        rec["vb"]["var_esc"] = ve
    # ---- a row safe but hit in hindsight: what hit it ----
    for tag, v, bx in (("vb", vb, box[best]), ("vk", vk, rk.box[0])):
        if rec[tag]["hind"] >= 0 and (not v["S"] or any((rec[tag].get("var") or {}).get(x) for x in ("rb", "rbr"))):
            # (and a hit row a reactive variant frees: what its true alarm was)
            rec[tag]["hit_by"] = _owner(fp, fo, rec[tag]["hind"], bx[rec[tag]["hind"]])
    # ---- J terms of the best row and the pick ----
    rows2 = np.array([best, pick], np.int64)
    jt = j_terms(pl, cap, box[rows2], flags[rows2], mode[rows2], latched[rows2])
    w = weights(prefs)
    cont_w = prefs.weights.get("cont", 0.0)
    rec["J"] = {"w": [round(x, 3) for x in w], "best": [round(float(x), 4) for x in jt[0]],
                "pick": [round(float(x), 4) for x in jt[1]],
                "cont": [cont_w if names[best] == "CONTINUE" else 0.0, cont_w if names[pick] == "CONTINUE" else 0.0],
                "tv": None if cap["sc"] is None or cap["sc"].get("J_tv") is None else
                [round(float(cap["sc"]["J_tv"][best]), 4), round(float(cap["sc"]["J_tv"][pick]), 4)],
                "J": [round(float(dbg["J"][best]), 4), round(float(dbg["J"][pick]), 4)]}
    if not forced and not vb["S"] and ok[best] and best != pick:
        full_b = np.concatenate([np.asarray(prefix, np.int64), ls["cmd"][best]])
        nf, lab = escape_fails(pl, cap, full_b)
        rec["vb"]["esc"] = [nf, lab]
    esc = li.get("esc") or {}
    rec["pick_esc"] = [esc.get("fail"), esc.get("why")] if esc else None
    # the keys row's J terms (its own score dict)
    if vk["sc"] is not None:
        jk = j_terms(pl, cap, rk.box, rk.flags, rk.mode, pm[None])
        rec["J"]["keys"] = [round(float(x), 4) for x in jk[0]]
    return rec


class _RollRow:
    """One row of stage 1's rollout (the score / verdict helpers read box, flags, mode, vel)."""

    def __init__(self, box, flags, mode):
        self.box = np.ascontiguousarray(box[None])
        self.flags = np.ascontiguousarray(flags[None])
        self.mode = np.ascontiguousarray(mode[None])
        self.vel = np.zeros(self.box.shape[:2] + (2,))


def _sc_row(sc: dict | None, n: int) -> dict | None:
    if sc is None:
        return None
    out = {}
    for k, v in sc.items():
        if isinstance(v, np.ndarray) and v.ndim >= 1 and len(v) > n:
            out[k] = v[n:n + 1]
        else:
            out[k] = v
    return out


def _wave(s: dict) -> int | None:
    b = next((x for x in (s.get("room") or {}).get("battles") or () if x.get("name") == "Battle Scene"), None)
    return None if not b or not b.get("started") else b.get("wave")


def clear_latches(pl) -> None:
    """The planner's jump / macro latches come from its own picks, which an open-loop replay never executes (the
    person's keys are): no jump hold for "keep" to protect, no attack row or-ed with a jump, no macro for "mkeep"."""
    pl.jump_until = -1
    pl.macro_until = -1


def run_segment(job: dict) -> dict:
    from ssbot.tools.forum_hit_forensics import FramePolys
    from ssbot.train.encounters import ENCOUNTERS
    seg = job["seg"]
    t0 = time.perf_counter()
    crest = seg["crest"] if seg["crest"] in ("Wanderer", "Reaper") else "Reaper"
    pol, cap, vs = _policy(crest, job["threads"], job["clash"], job["variants"])
    t_init = time.perf_counter() - t0
    terrain, states = load_segment(seg)
    t_load = time.perf_counter() - t0 - t_init
    if job.get("limit_s"):
        states = states[:int(job["limit_s"] * 60)]
    pol.terrain_msg = terrain
    pol.reset(random.Random(0), ENCOUNTERS["Forum"])
    _wrap(pol, cap)
    pl = pol.planner
    pl.debug = True
    pl.fcfg.deadline_ms = math.inf
    pl.fcfg.esc_deadline_ms = math.inf
    pl.fcfg.clash_deadline_ms = math.inf
    fp = FramePolys(states)
    fi = frame_info(states)
    groups_cache: dict = {}
    ticks, errors = [], []
    every = job["every"]
    for i, s in enumerate(states):
        if i + 1 < len(states):
            pol.sent[int(states[i + 1]["f"])] = int(states[i + 1]["act"]["mask"])
        clear_latches(pl)
        pol.act(s, None)
        if i % every or i < 3:
            continue
        try:
            r = analyse(pol, cap, vs, i, states, fi, fp, groups_cache)
        except Exception:
            import traceback
            errors.append([i, traceback.format_exc()[-1500:]])
            continue
        if r is not None:
            ticks.append(r)
    st = pol.stats()
    return {"seg": seg, "crest": crest, "fcfg": st.get("fcfg"), "clash": job["clash"], "n_states": len(states),
            "ticks": ticks, "errors": errors[:20], "n_errors": len(errors), "init_s": round(t_init, 1),
            "load_s": round(t_load, 1),
            "secs": round(time.perf_counter() - t0, 1), "plan_ms_p50": st.get("plan_ms_p50"),
            "forced_risk_ticks": st.get("forced_risk_ticks"), "planner_ticks": len(pol.tick_ms),
            "hits_taken": len(fi["dmg"].nonzero()[0])}


def _init(threads: int) -> None:
    try:
        import psutil
        p_ = psutil.Process()   # never raise an Idle job (the person: long runs at Idle)
        if p_.nice() != getattr(psutil, "IDLE_PRIORITY_CLASS", None):
            p_.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def _job_safe(job: dict) -> dict:
    try:
        return run_segment(job)
    except Exception:
        import traceback
        return {"seg": job["seg"], "error": traceback.format_exc()[-3000:]}


def _name(seg: dict) -> str:
    return f"{Path(seg['session']).name}_a{seg['attempt']}_{seg['kind']}"


def cmd_run(a) -> int:
    a.out.mkdir(parents=True, exist_ok=True)
    segs = []
    for spec in a.seg:
        segs += segments(spec, a.demo_cache)
    jobs = [{"seg": s, "every": a.every, "threads": a.threads, "clash": a.clash, "variants": a.variants,
             "limit_s": a.limit_s} for s in segs if not (a.out / f"{_name(s)}.json").exists()]
    # longest first (wins at 0.5x), so the pool's tail is short
    jobs.sort(key=lambda j: -(j["seg"]["f1"] - j["seg"]["f0"]) * (j["seg"]["ts"] or 1.0))
    print(f"{len(jobs)} segments", flush=True)
    t0 = time.perf_counter()

    def write(res):
        p = a.out / f"{_name(res['seg'])}.json"
        p.write_text(json.dumps(res, default=str), "utf-8")
        print(f"{p.name} {'ERROR ' + res['error'][-300:] if 'error' in res else ''} {res.get('secs')} s "
              f"({time.perf_counter() - t0:.0f} s)", flush=True)
    if a.workers <= 1:
        _init(a.threads)
        for j in jobs:
            write(_job_safe(j))
    else:
        with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.threads,)) as ex:
            for res in ex.map(_job_safe, jobs):
                write(res)
    return 0


# ---------------------------------------------------------------------------------------------------- summary

def _q(v, p):
    return round(float(np.percentile(v, p)), 3) if len(v) else None


def _share(n, d):
    return round(n / d, 4) if d else None


def summarize(files: list[Path], close_u: float = CLOSE_U) -> dict:
    """The numbers of forum.md §25 from the per-segment files of one configuration."""
    segs = []
    T = []
    for p in files:
        d = json.loads(p.read_text("utf-8"))
        if "error" in d:
            continue
        segs.append({"name": p.stem, "kind": d["seg"]["kind"], "ticks": len(d["ticks"]), "secs": d["secs"],
                     "n_errors": d.get("n_errors"), "fcfg": d.get("fcfg"), "clash": d.get("clash")})
        for t in d["ticks"]:
            t["_kind"] = d["seg"]["kind"]
            t["_seg"] = p.stem
            T.append(t)
    out = {"segments": segs, "by_kind": {}}
    groups = {"all": lambda t: True, "w0": lambda t: t["_kind"] == "w0", "win": lambda t: t["_kind"] == "win",
              "win_wave0": lambda t: t["_kind"] == "win" and (t.get("wave") or 0) == 0,
              "win_later": lambda t: t["_kind"] == "win" and (t.get("wave") or 0) >= 1,
              "wave0_all": lambda t: (t.get("wave") or 0) == 0}
    for kind, fn in groups.items():
        out["by_kind"][kind] = summarize_ticks([t for t in T if fn(t)], close_u)
    return out


def matched(t: dict, close_u: float) -> bool:
    """The tick's best row has the person's presses (edge_ok; files before forum.md §25.11: position only) and lies
    within close_u of the person's path."""
    return bool(t.get("edge_ok", True)) and t["best"][1] <= close_u


def cause(t: dict, close_u: float) -> str:
    """One reason per tick, in order: outside the candidate set, vetoed, the pick itself, then (a tick with a safe
    row) the row judged unsafe (false / true alarm by hindsight) or safe but ranked behind, and (FORCED_RISK: every
    allowed row unsafe, so the preselection keys decide) the first key that put the pick ahead."""
    if not matched(t, close_u):
        return "outside"
    v = t["vb"]
    if not v["ok"]:
        return "vetoed"
    if t["same_as_pick"]:
        return "pick"
    if t["forced"]:
        return f"forced:{v['why']}"
    if v["S"]:
        return "unsafe:false_alarm" if v["hind"] < 0 else "unsafe:true_alarm"
    return "safe_ranked_behind"


def react_variants(M: list[dict]) -> dict:
    """The reactive variants (rb / rbr: ReactConfig.bodyreach) on the matched rows (task forum push 2 track B): of
    the rows the base support calls unsafe, those the variant frees (clear of its support) that hindsight leaves
    clear (false alarms removed) and that hindsight hits (true alarms removed); misses (safe, hit in hindsight) under
    the base and under the variant (base-safe or freed), by the support alone and with the escape check's veto (a row
    the check fails is not safe: ForumConfig.esc_veto), and the share of freed rows the escape check fails."""
    def ok(t):
        return t["vb"].get("ok", True) and not t["vb"].get("unmod")
    rows = [t for t in M if ok(t) and t["vb"].get("var_esc") is not None]
    if not rows:
        return {}
    names = sorted({v for t in rows for v in (t["vb"].get("var") or {})}
                   | {v for t in rows for v in t["vb"]["var_esc"]})
    names = [v for v in names if v in ("rb", "rbr")]
    uns = [t for t in rows if t["vb"]["S"]]
    fa = [t for t in uns if t["vb"]["hind"] < 0]
    tr = [t for t in uns if t["vb"]["hind"] >= 0]
    safe = [t for t in rows if not t["vb"]["S"]]

    def passes(nf):
        return nf is None or nf == 0
    base_miss = sum(t["vb"]["hind"] >= 0 for t in safe)
    base_miss_esc = sum(t["vb"]["hind"] >= 0 and passes(t["vb"].get("esc_b")) for t in safe)
    out = {"n": len(rows), "unsafe": len(uns), "false_alarms": len(fa), "true_alarms": len(tr), "safe": len(safe),
           "base": {"misses": base_miss, "misses_esc": base_miss_esc,
                    "safe_esc": sum(passes(t["vb"].get("esc_b")) for t in safe)}}
    for v in names:
        fr = [t for t in uns if (t["vb"].get("var") or {}).get(v)]
        ffa = [t for t in fr if t["vb"]["hind"] < 0]
        ftr = [t for t in fr if t["vb"]["hind"] >= 0]
        ve = [t["vb"]["var_esc"].get(v) for t in fr]
        new_safe = safe + fr
        out[v] = {"freed": len(fr), "false_alarms_removed": len(ffa), "true_alarms_removed": len(ftr),
                  "fa_removed_share": _share(len(ffa), len(fa)), "ta_removed_share": _share(len(ftr), len(tr)),
                  "freed_fail_escape": _share(sum(not passes(x) for x in ve), len(fr)),
                  "fa_removed_esc": sum(passes(t["vb"]["var_esc"].get(v)) for t in ffa),
                  "ta_removed_esc": sum(passes(t["vb"]["var_esc"].get(v)) for t in ftr),
                  "misses": base_miss + len(ftr),
                  "misses_esc": sum(t["vb"]["hind"] >= 0 and passes(t["vb"]["var_esc"].get(v)) for t in new_safe),
                  "safe_esc": sum(passes(t["vb"]["var_esc"].get(v)) for t in new_safe),
                  "miss_by": dict(Counter(
                      ((t["vb"].get("hit_by") or [[None, "?", "?"]])[0][1] or "?")
                      for t in ftr).most_common(8))}
    return out


def summarize_ticks(T: list[dict], close_u: float) -> dict:
    n = len(T)
    if not n:
        return {"ticks": 0}
    e18 = np.array([t["best"][1] for t in T])
    k18 = np.array([t["kerr"][0] for t in T])
    close = np.array([matched(t, close_u) for t in T])
    edge = [t for t in T if "edge_ok" in t]
    out = {"ticks": n, "forced": _share(sum(t["forced"] for t in T), n),
           "match": {"err18_p50": _q(e18, 50), "err18_p90": _q(e18, 90), "kerr18_p50": _q(k18, 50),
                     "kerr18_p90": _q(k18, 90), "close": _share(int(close.sum()), n),
                     "close_at": {str(u): _share(sum(matched(t, u) for t in T), n)
                                  for u in (0.2, 0.35, 0.5, 0.75, 1.0)},
                     "best_is_pick": _share(sum(t["same_as_pick"] for t in T), n)}}
    if edge:
        pos_close = [t for t in edge if t["best_pos"][1] <= close_u]
        att = [t for t in pos_close if t["edges"][0] > 0]
        out["match"].update({
            "no_press_match": _share(sum(not t["edge_ok"] for t in edge), len(edge)),
            "no_press_match_by_button": {k: _share(v, len(edge)) for k, v in
                                         Counter(b for t in edge for b in t["edge_miss"]).most_common()},
            "close_position_only": _share(len(pos_close), len(edge)),
            "position_best_same_presses": _share(sum(t["best_pos"][3] for t in pos_close), len(pos_close)),
            "position_best_same_presses_when_attacking": _share(sum(t["best_pos"][3] for t in att), len(att)),
            "best_changed": _share(sum(not t["best_pos"][4] for t in edge), len(edge)),
            "pick_near": _share(sum(t["pick_err"][0] <= close_u for t in edge), len(edge)),
            "pick_near_same_presses": _share(sum(t["pick_err"][0] <= close_u and t["pick_err"][2] for t in edge),
                                             len(edge))})
        al = np.array([t["all"] for t in edge], np.float64)
        out["all_rows"] = {"allowed_clear": _share(float(al[:, 1].sum()), float(al[:, 0].sum())),
                           "unsafe_clear": _share(float(al[:, 3].sum()), float(al[:, 2].sum()))}
        sr = np.array([t["safe_rows"] for t in edge if "safe_rows" in t], np.float64).reshape(-1, 2)
        if len(sr):
            # open-loop hindsight of the planner's safe rows: the share of them a recorded damage collider meets
            out["all_rows"].update(safe_rows=int(sr[:, 0].sum()), safe_hit=_share(float(sr[:, 0].sum() - sr[:, 1].sum()),
                                                                                  float(sr[:, 0].sum())),
                                   ticks_any_safe_hit=_share(float(((sr[:, 0] - sr[:, 1]) > 0).sum()), float(len(sr))))
    # ---- moves outside the candidate set ----
    far = [t for t, c in zip(T, close) if not c]
    cls = Counter(action_class(t["person"]) for t in far)
    cls_all = Counter(action_class(t["person"]) for t in T)
    far_pos = [t for t in far if t.get("edge_ok", True)]
    timing = [t for t in far_pos if t["kerr"][0] <= close_u and action_class(t["person"]) == "other"]
    out["outside"] = {"n": len(far), "share": _share(len(far), n),
                      "no_press_match": _share(len(far) - len(far_pos), n),
                      "by_action": {k: [v, _share(v, len(far)), _share(cls_all[k] - v, cls_all[k])]
                                    for k, v in cls.most_common()},
                      "keys_model_close": _share(sum(t["kerr"][0] <= close_u for t in far), len(far)),
                      "timing": _share(len(timing), len(far)),
                      "timing_jump_dash": _share(sum(t["person"].get("jumps", 0) + t["person"].get("dashes", 0) > 0
                                                     for t in timing), len(far))}
    out["causes"] = {k: _share(v, n) for k, v in Counter(cause(t, close_u) for t in T).most_common()}
    # ---- verdicts on the matched ticks ----
    M = [t for t, c in zip(T, close) if c]
    out["matched"] = verdicts(M, "vb")
    rv = react_variants(M)
    if rv:
        out["react_variants"] = rv
    out["keys_row"] = verdicts([t for t in T if t["kerr"][0] <= close_u], "vk")
    out["keys_row_all"] = verdicts(T, "vk")
    out["pick"] = {"hind_clear": _share(sum(t["pick"][2] < 0 for t in T), n),
                   "hind_clear_safe": _share(sum(t["pick"][2] < 0 for t in T if not t["forced"]),
                                             sum(not t["forced"] for t in T)),
                   "hind_clear_forced": _share(sum(t["pick"][2] < 0 for t in T if t["forced"]),
                                               sum(t["forced"] for t in T)),
                   "person_hit_in_horizon": _share(sum(t["hit_in"] > 0 for t in T), n)}
    out["safe_differ"] = safe_differ([t for t in M if not t["forced"] and not t["vb"]["S"] and t["vb"]["ok"]
                                      and not t["same_as_pick"]])
    out["forced_rank"] = forced_rank([t for t in M if t["forced"]])
    return out


def verdicts(M: list[dict], tag: str) -> dict:
    n = len(M)
    if not n:
        return {"n": 0}
    unsafe = [t for t in M if t[tag]["S"]]
    clear = [t for t in M if t[tag]["hind"] < 0]
    fa = [t for t in unsafe if t[tag]["hind"] < 0]
    miss = [t for t in M if not t[tag]["S"] and t[tag]["hind"] >= 0]
    out = {"n": n, "safe": _share(n - len(unsafe), n), "unsafe": _share(len(unsafe), n),
           "unsafe_src": dict(Counter(t[tag]["src"] for t in unsafe)),
           "hind_clear": _share(len(clear), n), "false_alarm": _share(len(fa), n),
           "false_alarm_of_unsafe": _share(len(fa), len(unsafe)), "false_alarm_of_clear": _share(len(fa), len(clear)),
           "miss": _share(len(miss), n), "miss_of_safe": _share(len(miss), n - len(unsafe)),
           "forced_ticks": _share(sum(t["forced"] for t in M), n),
           "unsafe_in_safe_ticks": _share(sum(t[tag]["S"] for t in M if not t["forced"]),
                                          sum(not t["forced"] for t in M))}
    if tag == "vb":
        out["not_ok"] = _share(sum(not t["vb"]["ok"] for t in M), n)
        out["unmod"] = _share(sum(t["vb"]["unmod"] for t in M), n)
        out["pl_known"] = _share(sum(t["vb"]["known"] for t in M), n)
        agree = [t for t in M if t["vb"]["known"]]
        out["pl_S_agree"] = _share(sum(int(t["vb"]["S"]) == t["vb"]["pl_S"] for t in agree), len(agree))
    # false alarms by layer: any coverage, the necessary ones, sole category
    cov, need, sole, grp, src = Counter(), Counter(), Counter(), Counter(), Counter()
    var = Counter()
    nvar = 0
    for t in fa:
        L = t[tag].get("layers")
        src[t[tag]["src"]] += 1
        if L is None:
            continue
        for c in L["cats"]:
            cov[c] += 1
        for c in L["need"]:
            need[c] += 1
        if len(L["cats"]) == 1:
            sole[next(iter(L["cats"]))] += 1
        if not L["cats"]:
            sole["(none: " + str(t[tag]["src"]) + ")"] += 1
        for g in L["groups"][:3]:
            grp[f"{g[0]}|{g[1]}|{g[2]}"] += 1
        v = t[tag].get("var")
        if v:
            nvar += 1
            for k, x in v.items():
                var[k] += int(x)
    nf = max(len(fa), 1)
    out["fa_by_src"] = dict(src)
    out["fa_cover"] = {k: _share(v, nf) for k, v in cov.most_common()}
    out["fa_need"] = {k: _share(v, nf) for k, v in need.most_common()}
    out["fa_sole"] = {k: _share(v, nf) for k, v in sole.most_common()}
    out["fa_groups"] = {k: _share(v, nf) for k, v in grp.most_common(25)}
    out["fa_var_clear"] = {k: _share(v, nvar) for k, v in var.items()} if nvar else None
    # true alarms (unsafe and hit) by layer, to compare
    ta = [t for t in unsafe if t[tag]["hind"] >= 0]
    tc = Counter()
    for t in ta:
        for c in (t[tag].get("layers") or {}).get("cats", {}):
            tc[c] += 1
    out["ta_cover"] = {k: _share(v, max(len(ta), 1)) for k, v in tc.most_common()}
    # precision of each category: of the unsafe rows it covers, the share clear in hindsight
    prec = {}
    for c in set(cov) | set(tc):
        prec[c] = _share(cov[c], cov[c] + tc[c])
    out["cat_false_share"] = prec
    mb = Counter()
    for t in miss:
        hb = t[tag].get("hit_by") or []
        mb[(hb[0][1] + "|" + hb[0][2]) if hb else "?"] += 1
    out["miss_by"] = dict(mb.most_common(12))
    return out


def safe_differ(D: list[dict]) -> dict:
    """Ticks with a safe row (the person's matched row safe and allowed) whose pick is another row."""
    n = len(D)
    if not n:
        return {"n": 0}
    why = Counter(t["vb"]["why"] for t in D)
    moved = sum(t["chosen_moved"] for t in D)
    esc_fail = sum(1 for t in D if (t["vb"].get("esc") or [None])[0])
    dJ = []
    worst = Counter()
    for t in D:
        w = np.array(t["J"]["w"])
        b, p = np.array(t["J"]["best"]), np.array(t["J"]["pick"])
        d = w * (b - p)
        cont = t["J"]["cont"][0] - t["J"]["cont"][1]
        tv = (t["J"]["tv"][0] - t["J"]["tv"][1]) if t["J"].get("tv") else 0.0
        dJ.append(list(d) + [cont, tv])
        allt = list(d) + [cont, tv]
        k = int(np.argmin(allt))
        if allt[k] < 0:
            worst[(list(TERMS) + ["cont", "tv"])[k]] += 1
    dJ = np.array(dJ)
    names = list(TERMS) + ["cont", "tv"]
    sit = Counter(situation(t) for t in D)
    return {"n": n, "why": {str(k): _share(v, n) for k, v in why.most_common()},
            "pick_moved_by_escape_or_tail": _share(moved, n), "person_row_fails_escape": _share(esc_fail, n),
            "dJ_mean": {k: round(float(dJ[:, j].mean()), 3) for j, k in enumerate(names)},
            "dJ_neg_share": {k: _share(int((dJ[:, j] < -1e-6).sum()), n) for j, k in enumerate(names)},
            "worst_term": {k: _share(v, n) for k, v in worst.most_common()},
            "hits_person_vs_pick": [round(float(np.mean([t["J"]["best"][0] for t in D])), 3),
                                    round(float(np.mean([t["J"]["pick"][0] for t in D])), 3)],
            "situations": {k: _share(v, n) for k, v in sit.most_common()},
            "pick_hind_clear": _share(sum(t["pick"][2] < 0 for t in D), n),
            "person_hind_clear": _share(sum(t["vb"]["hind"] < 0 for t in D), n)}


def situation(t: dict) -> str:
    """A coarse label of a safe-differ tick (the person's row against the pick)."""
    c = t["ctx"]
    b, p = t["J"]["best"], t["J"]["pick"]
    hb, hp = b[0], p[0]
    near = c["near"][0] if c["near"] else None
    if c.get("defending") and hb <= hp:
        return "waits_by_defender"
    if hp > hb + 1e-6:
        if near is not None and near[3] < 4.0:
            return "no_swing_in_reach"
        return "positions_no_swing"
    if c.get("flier_above"):
        return "under_flier"
    if b[3] < p[3] - 0.5:
        return "off_stance"
    if b[4] < p[4] - 0.05:
        return "risk_map"
    if b[2] < p[2]:
        return "more_jumps"
    if b[1] < p[1]:
        return "waste"
    return "other"


def forced_rank(F: list[dict]) -> dict:
    n = len(F)
    if not n:
        return {"n": 0}
    rk = [t["vb"]["rank"] for t in F if t["vb"]["rank"] is not None]
    return {"n": n, "rank_p50": _q(rk, 50), "rank_p90": _q(rk, 90),
            "in_preselection": _share(sum(r <= 16 for r in rk), len(rk)),
            "why": {str(k): _share(v, n) for k, v in Counter(t["vb"]["why"] for t in F).most_common()},
            "person_seen_gt_pick": _share(sum(t["vb"]["keys"]["sk_n"] > t["pick_keys"]["sk_n"] for t in F), n),
            "person_cf_gt_pick": _share(sum(t["vb"]["keys"]["sk_c"] > t["pick_keys"]["sk_c"] for t in F), n),
            "person_hind_clear": _share(sum(t["vb"]["hind"] < 0 for t in F), n),
            "pick_hind_clear": _share(sum(t["pick"][2] < 0 for t in F), n)}


def cmd_summary(a) -> int:
    out = {}
    for d in a.dirs:
        files = sorted(d.glob("*.json"))
        out[d.name] = summarize(files, a.close)
    js = json.dumps(out, indent=1, default=str)
    if a.json:
        a.json.write_text(js, "utf-8")
    print(js[:20000])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--seg", action="append", required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--every", type=int, default=3)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--threads", type=int, default=4)
    r.add_argument("--clash", default="off", choices=("off", "on", "yellow", "cont", "main"))
    r.add_argument("--variants", type=lambda s: tuple(x for x in s.split(",") if x), default=())
    r.add_argument("--demo-cache", type=Path, default=None)
    r.add_argument("--limit-s", type=float, default=0.0, help="only the first this many game seconds (tests)")
    s = sub.add_parser("summary")
    s.add_argument("dirs", nargs="+", type=Path)
    s.add_argument("--close", type=float, default=CLOSE_U)
    s.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    return cmd_run(a) if a.cmd == "run" else cmd_summary(a)


if __name__ == "__main__":
    sys.exit(main())
