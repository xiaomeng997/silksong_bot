"""Map v2 stage M0: the calibration numbers from the m0_probe recordings (docs/plans/forum_map_v2.md section 2, M0;
forum.md section 91).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m0_calib <recording dir> [<recording dir> ...] \
        [--json C:/ssbot/data/m2_play/map2/m0_calib.json] [--rows C:/ssbot/data/m2_play/map2/m0_rows.pkl]

Every trial of <recording>/m0_trials.jsonl is cut out of the recording (STATE rows from its first latched frame - 4
to its last frame) into per-frame rows (the latched mask, her box / pos / velocity, the clip, the cstate bits that
matter, the can flags and timers, her FSM transitions, hits, the Clapper's Control state and body box), then each
experiment's measurements are made (see the functions below) and printed with their spreads and trial counts.
Frames are rendered 60 fps frames; "P" is the first frame whose latched mask holds the pressed key; u are world units
(her box centre, its transform or its body box edge as stated).
"""
from __future__ import annotations

import argparse
import json
import pickle
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.ipc.framing import mask

M_L, M_R, M_U, M_D = mask("left"), mask("right"), mask("up"), mask("down")
M_J, M_A, M_DASH, M_CLAW = mask("jump"), mask("attack"), mask("dash"), mask("clawline")
FLOOR = 3.015
CLAPPER = "Song Heavy Sentry"
CS_KEEP = ("onGround", "attacking", "downAttacking", "dashing", "airDashing", "jumping", "falling", "bouncing",
           "downSpikeBouncing", "downSpiking", "invulnerable", "recoiling", "floating", "isInCancelableFSMMove",
           "facingRight", "wallSliding", "upAttacking", "recoilFrozen", "doubleJumping", "freezeCharge")


def _cs_index():
    from ssbot.knowledge import kinematics as kin
    names = kin.cstate_names()
    return {n: i for i, n in enumerate(names) if n in CS_KEEP}


def _bits(cs, idx: dict) -> dict:
    out = {}
    for n, i in idx.items():
        out[n] = bool(cs) and bool((int(cs[i >> 6]) >> (i & 63)) & 1)
    return out


def _body(e: dict | None):
    for c in (e or {}).get("colliders") or ():
        if c.get("kind") == "box" and c.get("name") == CLAPPER:
            v = c.get("verts_world") or []
            xs, ys = v[0::2], v[1::2]
            if xs:
                return (min(xs), min(ys), max(xs), max(ys), bool(c.get("enabled", True)))
    return None


def frame_row(s: dict, idx: dict, hero_names: set) -> dict:
    h = s.get("hero") or {}
    b = h.get("box") or [0, 0, 0, 0]
    act = s.get("act") or {}
    an = h.get("anim") or {}
    r = {"f": s["f"], "m": int(act.get("mask") or 0), "x": 0.5 * (b[0] + b[2]), "yb": b[1] - FLOOR, "box": b,
         "px": (h.get("pos") or [0, 0])[0], "py": (h.get("pos") or [0, 0])[1],
         "vx": (h.get("vel") or [0, 0])[0], "vy": (h.get("vel") or [0, 0])[1],
         "clip": an.get("clip"), "cf": an.get("frame"), "acc": bool(h.get("hero_accepting_input")),
         "relq": bool(h.get("control_relinquished")), "hs": h.get("hero_state"), "can": h.get("can") or {},
         "tm": h.get("tm") or {}, "inv": bool(h.get("invulnerable")), "silk": h.get("silk"),
         "face": h.get("facing"), "dt": s.get("dt"), "fs": s.get("fs"),
         "dsinv": (h.get("cstate_int") or [0, 0])[1] if len(h.get("cstate_int") or []) > 1 else None}
    r.update(_bits(h.get("cstate"), idx))
    fsm, hits, cfsm = [], [], []
    for ev in s.get("ev") or ():
        k = ev.get("k")
        d = ev.get("d") or {}
        if k == "fsm":
            if d.get("obj") in hero_names or str(d.get("obj") or "").startswith("Hero_Hornet"):
                fsm.append((d.get("fsm"), d.get("from"), d.get("to")))
            elif d.get("obj") == CLAPPER and d.get("fsm") == "Control":
                cfsm.append((d.get("from"), d.get("to")))
        elif k == "hit":
            hits.append({"src": d.get("src"), "type": d.get("type_key"), "dmg": d.get("dmg"), "attack": d.get("attack"),
                         "hp_after": d.get("hp_after")})
        elif k in ("damage", "hp"):
            hits.append({"k": k, **{kk: d.get(kk) for kk in ("src", "amount", "hp", "type", "hazard")}})
    r["fsm"], r["hits"], r["cfsm"] = fsm, hits, cfsm
    e = next((e for e in s.get("ents") or () if e.get("type_key") == CLAPPER and not e.get("is_dead")), None)
    if e is not None:
        st_, t_ = None, None
        for m in e.get("fsms") or ():
            if m.get("name") == "Control":
                st_, t_ = m.get("state"), m.get("t")
        r["cl"] = {"st": st_, "t": t_, "x": e["pos"][0], "y": e["pos"][1], "hp": e.get("hp"), "flip": e.get("flipX"),
                   "body": _body(e), "clip": (e.get("anim") or {}).get("clip"), "vx": (e.get("vel") or [0, 0])[0]}
    else:
        r["cl"] = None
    return r


def extract(rec_dir: Path) -> list[dict]:
    """Every trial of one recording with its frame rows."""
    from ssbot.record.recorder import RecordingReader
    idx = _cs_index()
    trials = [json.loads(l) for l in (rec_dir / "m0_trials.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rr = RecordingReader(rec_dir)
    hero_names: set = set()
    out = []
    for t in trials:
        res = t.get("res") or {}
        f0, f1 = res.get("f0"), res.get("f1")
        if f0 is None or f1 is None or res.get("skip"):
            t["rows"] = []
            out.append(t)
            continue
        rows = [frame_row(s, idx, hero_names) for s in rr.states(f0 - 4, f1 + 1)]
        t["rows"] = rows
        t["rec"] = str(rec_dir)
        out.append(t)
    return out


# ---- helpers ----------------------------------------------------------------------------------------------------------

def first(rows, pred, start=0):
    for i in range(max(start, 0), len(rows)):
        try:
            if pred(rows[i]):
                return i
        except (KeyError, TypeError):
            pass
    return None


def press_idx(rows, bit, start=0):
    """The first row from start whose latched mask holds bit after a row without it."""
    for i in range(max(start, 1), len(rows)):
        if rows[i]["m"] & bit and not rows[i - 1]["m"] & bit:
            return i
    return None


def fsm_idx(rows, fsm, to, start=0):
    return first(rows, lambda r: any(e[0] == fsm and e[2] == to for e in r["fsm"]), start)


def q(vals, ps=(0, 10, 50, 90, 100)):
    v = [x for x in vals if x is not None]
    if not v:
        return "n 0"
    a = np.asarray(v, dtype=float)
    return f"n {len(v)} " + " / ".join(f"{np.percentile(a, p):.3g}" for p in ps) + f" (p{'/'.join(map(str, ps))})"


def cnt(vals):
    return dict(Counter(vals).most_common())


SLASH = ("DownSlash", "DownSlashAlt", "Slash", "SlashAlt", "UpSlash")


def is_slash(c) -> bool:
    return bool(c) and str(c) in SLASH


def fsm_list(rows, fsm):
    return [(i, fr, to) for i, r in enumerate(rows) for (f_, fr, to) in r["fsm"] if f_ == fsm]


def state_before(ev, i):
    """The FSM state entered last at a row before i (its transitions at row i happen in that frame)."""
    s = None
    for j, fr, to in ev:
        if j < i:
            s = to
    return s


def _seq_str(tab: dict) -> str:
    return " ".join(f"{j}:{''.join('x' if d is None else str(d) for d in v)}"
                    for j, v in sorted(tab.items(), key=lambda x: (x[0] is None, x[0])))


# ---- (1) / (3) the attack and the Clawline from the umbrella ---------------------------------------------------------

CANCELS = ("Attack Cancel", "Harpoon Cancel", "Force Cancel", "Cancel All")


def an_fl(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows:
        return None
    claw = t["exp"] == "fl_claw"
    bit = M_CLAW if claw else M_A
    ue = fsm_list(rows, "Umbrella Float")
    i_antic = next((i for i, fr, to in ue if to == "Antic"), None)
    if i_antic is None:
        return {"why": "no umbrella"}
    i_infl = next((i for i, fr, to in ue if to == "Inflate"), None)
    i_float = next((i for i, fr, to in ue if to == "Float Idle"), None)
    iP = press_idx(rows, bit, i_antic)
    if iP is None:
        return {"why": "no press"}
    iR = first(rows, lambda r: not r["m"] & M_J, i_antic + 1)
    sb = state_before(ue, iP)
    out = {"v": p.get("v"), "side": bool(p.get("side")), "st": sb, "k_rel": None if iR is None else iP - iR,
           "t_float": None if i_float is None else iP - i_float, "t_infl": None if i_infl is None else iP - i_infl,
           "t_antic": iP - i_antic, "hp": p.get("hp"), "yb": rows[iP]["yb"], "vy": rows[iP]["vy"]}
    if claw:
        iS = first(rows, lambda r: str(r["clip"]).startswith("Harpoon Antic"), iP)
        he = fsm_list(rows, "Harpoon Dash")
        iDo = next((i for i, fr, to in he if to == "Can Do?" and i >= iP), None)
        out["do_move"] = None if iDo is None else iDo - iP
    else:
        iS = first(rows, lambda r: is_slash(r["clip"]), iP)
    out["delay"] = None if iS is None or iS - iP > 40 else iS - iP
    out["lost"] = out["delay"] is None
    iD = next((i for i, fr, to in ue if to == "Deflate" and i >= min(iR or iP, iP) - 1), None)
    out["deflate_at"] = None if iD is None else iD - iP
    iC = next(((i, to) for i, fr, to in ue if to in CANCELS and i >= iP - 1), None)
    out["cancel"] = None if iC is None else (iC[0] - iP, iC[1])
    if iD is not None:
        iRel = next(((i, to) for i, fr, to in ue if fr == "Deflate" and i > iD), None)
        out["deflate_len"] = None if iRel is None else iRel[0] - iD
        out["deflate_to"] = None if iRel is None else iRel[1]
        iAcc = first(rows, lambda r: r["acc"], iD)
        out["ctrl_after_deflate"] = None if iAcc is None else iAcc - iD
    if out["lost"]:
        iAcc = first(rows, lambda r: r["acc"], iP)
        out["ctrl"] = None if iAcc is None else iAcc - iP
    return out


def report_fl(trials, kind) -> dict:
    res = [dict(a, exp=t["exp"]) for t in trials if t["exp"] == kind and (a := an_fl(t)) and "why" not in a]
    print(f"\n== {kind}: {len(res)} trials ==")
    out = {}
    groups = defaultdict(list)
    for a in res:
        groups[a["v"] + ("/side" if a["side"] else "")].append(a)
    for key, g in sorted(groups.items()):
        d = [a["delay"] for a in g if a["delay"] is not None]
        print(f"  {key:10s} n {len(g):3d}  fired {len(d):3d}  delay {cnt(d)}  states at P {cnt(a['st'] for a in g)}")
        out[key] = {"n": len(g), "fired": len(d), "delay": d, "states": cnt(a["st"] for a in g)}
    print("  by the umbrella state at the press (before its frame's transitions) x frames since the jump release:")
    tab = defaultdict(lambda: [0, 0, []])
    for a in res:
        k = a["k_rel"]
        kk = "held" if k is None or k < 0 else (f"rel+{k:02d}" if k <= 12 else "rel+13..")
        cell = tab[(a["st"], kk)]
        cell[0] += 1
        if not a["lost"]:
            cell[1] += 1
            cell[2].append(a["delay"])
    for (s_, kk), (n, f, d) in sorted(tab.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        print(f"    {str(s_):16s} {kk:9s} n {n:3d} fired {f:3d}  delay {cnt(d)}")
    out["by_state"] = {f"{s_}|{kk}": {"n": n, "fired": f, "delay": cnt(d)} for (s_, kk), (n, f, d) in tab.items()}
    dl = [a["deflate_len"] for a in res if a.get("deflate_len") is not None]
    print(f"  Deflate length (its entry to its exit, frames) {cnt(dl)}; exit to {cnt(a.get('deflate_to') for a in res)}")
    ca = [a["ctrl_after_deflate"] for a in res if a.get("ctrl_after_deflate") is not None]
    print(f"  control (accepting) after the Deflate's entry {cnt(ca)}")
    lost = [a for a in res if a["lost"]]
    print(f"  lost presses: {len(lost)}: states {cnt(a['st'] for a in lost)}, k_rel {cnt(a['k_rel'] for a in lost)}, "
          f"control after P {cnt(a.get('ctrl') for a in lost)}")
    out["deflate_len"] = cnt(dl)
    out["lost"] = len(lost)
    out["rows"] = [{k: a.get(k) for k in ("v", "side", "st", "k_rel", "t_float", "delay", "lost", "deflate_at",
                                          "deflate_len", "hp", "yb", "vy")} for a in res]
    if kind == "fl_claw":
        inf = [a for a in res if a["v"] == "infl"]
        for hp in sorted({a["hp"] for a in inf if a["hp"]}):
            g = [a for a in inf if a["hp"] == hp]
            print(f"  infl, the key held {hp} f: n {len(g)} fired {sum(not a['lost'] for a in g)} (delay "
                  f"{cnt(a['delay'] for a in g if not a['lost'])}; Float Idle - press {cnt(-a['t_float'] if a['t_float'] is not None else None for a in g)})")
    return out


# ---- (2) the float's horizontal motion ---------------------------------------------------------------------------------

def umbrella_x(vx, key, acc, dec, vmax):
    if key > 0:
        if vx < vmax:
            vx += acc
    elif key < 0:
        if vx > -vmax:
            vx -= acc
    elif vx > 0:
        vx = max(vx - dec, 0.0)
    elif vx < 0:
        vx = min(vx + dec, 0.0)
    return min(max(vx, -vmax), vmax)


def keyof(m: int) -> int:
    return (1 if m & M_R else 0) - (1 if m & M_L else 0)


def an_drift(trials) -> dict:
    """Per physics step of the umbrella's phases: the observed vx change against UmbrellaMotionX with the key of
    the frame lag 0 / 1 / 2 (the FSM reads the input the frame's FixedUpdates see)."""
    stats = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    resid = defaultdict(list)
    defl = []
    for t in trials:
        if t["exp"] not in ("drift", "fl_atk", "fl_claw"):
            continue
        rows = t["rows"]
        ue = fsm_list(rows, "Umbrella Float")
        if not ue:
            continue
        for i in range(3, len(rows)):
            st_ = state_before(ue, i + 1)
            if st_ not in ("Antic", "Inflate", "Float Idle", "Deflate"):
                continue
            if any(e[0] == "Umbrella Float" for e in rows[i]["fsm"]):
                continue                           # a transition frame: OnEnter actions mix in
            if not rows[i].get("fs"):
                continue
            v0, v1 = rows[i - 1]["vx"], rows[i]["vx"]
            if st_ == "Deflate":
                defl.append((round(v1 - v0, 3), keyof(rows[i]["m"]), round(v0, 2)))
                continue
            acc = {"Antic": 8.5, "Inflate": 1.0, "Float Idle": 1.0}[st_]
            for lag in (0, 1, 2):
                k = keyof(rows[i - lag]["m"])
                pred = umbrella_x(v0, k, acc, 0.25, 8.5)
                ok = abs(pred - v1) < 1e-3
                stats[st_][lag][0] += 1
                stats[st_][lag][1] += ok
                if lag == 1 and not ok:
                    resid[st_].append((round(v0, 2), k, round(v1, 2), rows[i]["clip"]))
    out = {}
    print("\n== the umbrella's vx per physics step vs UmbrellaMotionX (accel 8.5 antic / 1.0, decel 0.25, max 8.5) ==")
    for st_, d in stats.items():
        print(f"  {st_:10s} " + "  ".join(f"lag {lag}: {ok}/{n}" for lag, (n, ok) in sorted(d.items())))
        out[st_] = {lag: [n, ok] for lag, (n, ok) in d.items()}
        if resid[st_]:
            print(f"     misses (lag 1) e.g. {resid[st_][:8]}  clips {cnt(r[3] for r in resid[st_])}")
    print(f"  Deflate steps: (dvx, key, vx) {cnt((x[0], x[1]) for x in defl)}")
    out["deflate_dvx"] = cnt(x[0] for x in defl)
    return out


def an_inflate_entry(trials) -> dict:
    """vx at the Inflate's first frame vs the antic's key / vx (UmbrellaMotionX OnEnter from 0)."""
    rr = []
    for t in trials:
        if t["exp"] not in ("drift", "fl_atk", "fl_claw"):
            continue
        rows = t["rows"]
        ue = fsm_list(rows, "Umbrella Float")
        i = next((i for i, fr, to in ue if to == "Inflate"), None)
        if i is None or i < 1 or i + 1 >= len(rows):
            continue
        rr.append((round(rows[i - 1]["vx"], 2), keyof(rows[i]["m"]), keyof(rows[i - 1]["m"]), round(rows[i]["vx"], 2),
                   round(rows[i + 1]["vx"], 2)))
    print(f"\n  Inflate entry (vx before, key at the entry, key before, vx entry, vx next): {cnt(rr)}")
    return {"inflate_entry": [list(r) for r in rr]}


def an_reopen(trials) -> dict:
    """The umbrella's re-open after a close: the jump pressed again k frames after the release."""
    tab = defaultdict(list)
    rows_out = []
    for t in trials:
        if t["exp"] != "reopen":
            continue
        rows = t["rows"]
        ue = fsm_list(rows, "Umbrella Float")
        i_antic = next((i for i, fr, to in ue if to == "Antic"), None)
        if i_antic is None:
            continue
        iR = first(rows, lambda r: not r["m"] & M_J, i_antic + 1)
        iD = next((i for i, fr, to in ue if to == "Deflate" and i >= (iR or 0)), None)
        if iR is None or iD is None:
            continue
        iJ = press_idx(rows, M_J, iR)
        if iJ is None:
            continue
        iA2 = next((i for i, fr, to in ue if to == "Antic" and i >= iJ), None)
        iCd = next((i for i, fr, to in ue if fr == "Cooldown" and to == "Idle" and i >= iD), None)
        iCtl = first(rows, lambda r: r["acc"], iD)
        g = rows[iJ]["onGround"]
        o = {"k": iJ - iR, "deflate": iD - iR, "ctrl": None if iCtl is None else iCtl - iR,
             "fsm_idle": None if iCd is None else iCd - iR, "reopen": None if iA2 is None or iA2 - iJ > 26 else iA2 - iJ,
             "yb": rows[iJ]["yb"], "g": g, "clip": rows[iJ]["clip"]}
        rows_out.append(o)
        tab[o["k"]].append("G" if g else ("x" if o["reopen"] is None else str(o["reopen"])))
    print("\n== the umbrella's re-open: the jump pressed again k frames after the release (k: delays / x none / G landed) ==")
    print("  " + " ".join(f"{k}:{''.join(v)}" for k, v in sorted(tab.items())))
    print(f"  the close: Deflate at release + {cnt(o['deflate'] for o in rows_out)}, control at + {cnt(o['ctrl'] for o in rows_out)}, "
          f"its FSM Idle at + {cnt(o['fsm_idle'] for o in rows_out)}")
    return {"rows": rows_out}


# ---- (9) / (7) / (8) the unhooked Clawline, its hold height and a second action at control --------------------------

def an_claw(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows or p.get("skip"):
        return None
    iP = press_idx(rows, M_CLAW)
    if iP is None:
        return None
    he = fsm_list(rows, "Harpoon Dash")
    iA = first(rows, lambda r: str(r["clip"]).startswith("Harpoon Antic"), iP)
    if iA is None or iA - iP > 10:
        return {"why": "no antic", "clip": rows[iP]["clip"], "g": rows[iP]["onGround"]}
    iT = next((i for i, fr, to_ in he if to_ == "Throw" and i >= iP), None)
    iDash = next((i for i, fr, to_ in he if to_ in ("Dash", "Dash To Enemy") and i >= iP), None)
    iCatch = next((i for i, fr, to_ in he if to_ in ("Catch", "Enemy Bounce", "Tag Enemy Steal", "Catch Back")
                   and i >= (iDash or iP)), None)
    iEnd = next((i for i, fr, to_ in he if to_ == "Harpoon Dash End" and i >= iP), None)
    iCtl = first(rows, lambda r: r["acc"], iA)
    needle = next((to_ for i, fr, to_ in he if i >= iP and "Needle" in str(to_)), None)
    pr, prev = rows[iP], rows[iP - 1]
    hold = [rows[i]["yb"] for i in range(iT, (iDash or iT) + 1)] if iT is not None else []
    o = {"air": not prev["onGround"], "yb_P": pr["yb"], "yb_prev": prev["yb"], "vy_prev": prev["vy"], "vy_P": pr["vy"],
         "x_P": pr["x"], "antic": iA - iP, "throw": None if iT is None else iT - iP,
         "dash": None if iDash is None else iDash - iP, "catch": None if iCatch is None else iCatch - iP,
         "end": None if iEnd is None else iEnd - iP, "ctrl": None if iCtl is None else iCtl - iP, "needle": needle,
         "hold_yb": hold[0] if hold else None, "hold_span": (max(hold) - min(hold)) if hold else None,
         "antic_dx": None if iT is None else rows[iT]["x"] - pr["x"],
         "antic_dy": None if iT is None else rows[iT]["yb"] - prev["yb"]}
    d = 1 if iDash is None or rows[iDash]["vx"] >= 0 else -1
    o["dir"] = d
    if o["antic_dx"] is not None:
        o["antic_dx"] *= d
    if iDash is not None and iCatch is not None:
        o["dash_dx"] = (rows[iCatch]["x"] - rows[iDash - 1]["x"]) * d
        o["dash_frames"] = iCatch - iDash
    if iCtl is not None:
        c = rows[iCtl]
        o.update(ctl_vx=c["vx"] * d, ctl_vy=c["vy"], ctl_yb=c["yb"], pull=(c["x"] - pr["x"]) * d,
                 ctl_clip=c["clip"], ctl_g=c["onGround"])
        if iCatch is not None:
            o["catch_dx"] = (c["x"] - rows[iCatch - 1]["x"]) * d
        i2 = press_idx(rows, M_CLAW | M_A | M_DASH | M_J, iCtl) or len(rows)
        free = [(rows[i]["vx"] * d, rows[i]["x"]) for i in range(iCtl, min(i2, len(rows)))
                if not rows[i]["m"] and not rows[i]["onGround"]]
        o["after_vx"] = [round(v, 2) for v, _ in free[:12]]
        o["drift_after"] = (free[-1][1] - c["x"]) * d if len(free) > 1 else None
        o["drift_n"] = len(free)
        ih = first(rows, lambda r: r["can"].get("harpoon"), iCtl)
        o["harpoon_ready"] = None if ih is None else ih - iCtl
        iw = next((i for i, fr, to_ in he if fr == "Wait" and to_ == "Idle" and i >= iCtl), None)
        o["fsm_idle"] = None if iw is None else iw - iCtl
        ia = first(rows, lambda r: r["can"].get("attack"), iCtl)
        o["attack_ready"] = None if ia is None else ia - iCtl
        idd = first(rows, lambda r: r["can"].get("dash"), iCtl)
        o["dash_ready"] = None if idd is None else idd - iCtl
        sec = p.get("second")
        o["second"] = sec
        if sec and sec != "none":
            sb = {"claw": M_CLAW, "atk": M_A, "dash": M_DASH, "umb": M_J, "claw_away": M_CLAW}[sec]
            i2 = press_idx(rows, sb, iCtl)
            if i2 is not None:
                o["j2"] = i2 - iCtl
                if sec in ("claw", "claw_away"):
                    iA2 = first(rows, lambda r: str(r["clip"]).startswith("Harpoon Antic"), i2)
                elif sec == "atk":
                    iA2 = first(rows, lambda r: is_slash(r["clip"]), i2)
                elif sec == "dash":
                    iA2 = first(rows, lambda r: str(r["clip"]) in ("Dash", "Air Dash", "Dash Down", "Sprint Air"), i2)
                else:
                    iA2 = first(rows, lambda r: str(r["clip"]).startswith("Umbrella"), i2)
                o["second_delay"] = None if iA2 is None or iA2 - i2 > 12 else iA2 - i2
                o["second_g"] = rows[i2]["onGround"]
    return o


def report_claw(trials) -> dict:
    res = [dict(a, exp=t["exp"]) for t in trials if t["exp"] in ("claw_air", "claw_gnd", "fl_claw")
           and (a := an_claw(t)) and "why" not in a]
    out = {}
    un = [a for a in res if a.get("needle") and "Air Needle" in a["needle"]]
    print(f"\n== the Clawline, unhooked: {len(un)} of {len(res)} with an antic; needle states {cnt(a['needle'] for a in res)} ==")
    for k in ("antic", "throw", "dash", "catch", "end", "ctrl", "dash_frames"):
        print(f"  {k:12s} {cnt(a.get(k) for a in un)}")
    for k in ("antic_dx", "antic_dy", "dash_dx", "catch_dx", "pull", "drift_after", "ctl_vx", "ctl_vy", "hold_span"):
        print(f"  {k:12s} {q([a.get(k) for a in un])}")
    print(f"  after control, vx with no key, e.g. {[a['after_vx'] for a in un[:4]]}")
    print(f"  ready after control: harpoon {cnt(a.get('harpoon_ready') for a in un)}  attack "
          f"{cnt(a.get('attack_ready') for a in un)}  dash {cnt(a.get('dash_ready') for a in un)}  its FSM Idle "
          f"{cnt(a.get('fsm_idle') for a in un)}")
    print(f"  clip at control {cnt(a.get('ctl_clip') for a in un)}, grounded at control {cnt(a.get('ctl_g') for a in un)}")
    out["unhooked"] = {k: [a.get(k) for a in un] for k in ("air", "antic", "throw", "dash", "catch", "ctrl", "pull",
                                                           "dash_dx", "catch_dx", "antic_dx", "antic_dy", "ctl_vx",
                                                           "ctl_vy", "drift_after", "drift_n", "harpoon_ready",
                                                           "attack_ready", "dash_ready", "fsm_idle", "after_vx")}
    air = [a for a in un if a["air"] and a.get("hold_yb") is not None]
    if len(air) >= 3:
        X = np.array([[1.0, a["yb_prev"], a["vy_prev"]] for a in air])
        y = np.array([a["hold_yb"] for a in air])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        r = y - X @ coef
        print(f"  (7) hold box bottom = {coef[0]:+.3f} + {coef[1]:.3f} yb + {coef[2]:.4f} vy (the frame before P), "
              f"n {len(air)}, resid sd {r.std():.3f} max {abs(r).max():.3f}; vy range {q([a['vy_prev'] for a in air])}")
        r13 = y - np.array([a["yb_P"] - 0.261 + 0.0788 * a["vy_P"] for a in air])
        print(f"      SP13's fit (yb_P - 0.261 + 0.0788 vy_P, fitted for vy -6..9): resid {q(r13)}")
        bands = {}
        for lo, hi in ((-40, -12), (-12, -6), (-6, 9), (9, 20)):
            g = [(a, rr) for a, rr in zip(air, r13) if lo <= a["vy_P"] < hi]
            if g:
                print(f"        vy_P in [{lo}, {hi}): n {len(g)} SP13 resid {q([rr for _, rr in g])}")
                bands[f"{lo}..{hi}"] = [rr for _, rr in g]
        out["hold_fit"] = {"coef": coef.tolist(), "n": len(air), "sd": float(r.std()), "max": float(abs(r).max()),
                           "sp13_resid": [float(x) for x in r13], "bands": bands}
        out["hold_rows"] = [[a["yb_prev"], a["vy_prev"], a["yb_P"], a["vy_P"], a["hold_yb"]] for a in air]
    gnd = [a for a in un if not a["air"]]
    print(f"  from the ground: n {len(gnd)} hold yb {q([a.get('hold_yb') for a in gnd])} pull {q([a.get('pull') for a in gnd])}")
    for sec in ("claw", "atk", "dash", "umb"):
        g = [a for a in res if a.get("second") == sec and a.get("j2") is not None and a["exp"] != "fl_claw"]
        if not g:
            continue
        tab = defaultdict(list)
        for a in g:
            tab[a["j2"]].append(a.get("second_delay"))
        print(f"  (8) second {sec:5s} at control + j (j: delays, x = none): {_seq_str(tab)}")
        out[f"second_{sec}"] = {int(j): v for j, v in tab.items()}
    return out


# ---- (10) the ground dash / sprint ---------------------------------------------------------------------------------

def an_dash(trials) -> dict:
    out: dict = {"twice": [], "sprint": []}
    for t in trials:
        if t["exp"] != "dash_g":
            continue
        rows, p = t["rows"], t.get("res") or {}
        i1 = press_idx(rows, M_DASH)
        if i1 is None:
            continue
        d1 = first(rows, lambda r: r["clip"] == "Dash", i1)
        e1 = None if d1 is None else first(rows, lambda r: r["clip"] != "Dash", d1)
        if p.get("v") == "twice":
            i2 = press_idx(rows, M_DASH, i1 + 1)
            d2 = None if i2 is None else first(rows, lambda r: r["clip"] == "Dash" and r["tm"].get("dash_cd", 0) > 0.39,
                                                  i2)
            out["twice"].append({"j": None if i2 is None else i2 - i1, "d1": None if d1 is None else d1 - i1,
                                 "d2": None if d2 is None or i2 is None or d2 - i2 > 10 else d2 - i2,
                                 "dcd_at_2": None if i2 is None else rows[i2]["tm"].get("dash_cd"),
                                 "len": None if d1 is None or e1 is None else e1 - d1,
                                 "dx": None if d1 is None or e1 is None else abs(rows[e1]["x"] - rows[d1 - 1]["x"])})
        else:
            iRel = first(rows, lambda r: not r["m"] & M_DASH, i1)
            out["sprint"].append({"h": p.get("h"), "rel": p.get("rel"),
                                  "vx": [round(abs(r["vx"]), 2) for r in rows[i1:i1 + 110]],
                                  "clips": [r["clip"] for r in rows[i1:i1 + 110]],
                                  "rel_i": None if iRel is None else iRel - i1})
    tw = out["twice"]
    print(f"\n== the ground dash: {len(tw)} double dashes ==")
    tab = defaultdict(list)
    for a in tw:
        tab[a["j"]].append(a["d2"])
    print(f"  second press at j frames after the first (j: delays / x none): {_seq_str(tab)}")
    print(f"  first dash delay {cnt(a['d1'] for a in tw)}, Dash clip frames {cnt(a['len'] for a in tw)}, "
          f"dx {q([a['dx'] for a in tw])}")
    sp = out["sprint"]
    print(f"== the sprint: {len(sp)} held dashes ==")
    steady = [v for a in sp for i, v in enumerate(a["vx"]) if a["clips"][i] == "Sprint"
              and (a["rel_i"] is None or i < a["rel_i"])]
    print(f"  |vx| in the Sprint clip {q(steady)}; at the release {cnt(a['vx'][a['rel_i'] - 1] for a in sp if a['rel_i'])}")
    for a in sp[:3]:
        print(f"   h {a['h']} rel {a['rel']} at {a['rel_i']}: {list(zip(a['vx'][:72:3], [str(c)[:10] for c in a['clips'][:72:3]]))}")
    return out


# ---- (5) the slash cadence after a whiff ------------------------------------------------------------------------------

def an_whiff(trials) -> dict:
    tab = defaultdict(list)
    first_delay = []
    for t in trials:
        if t["exp"] != "ds_whiff":
            continue
        rows, p = t["rows"], t.get("res") or {}
        i1 = press_idx(rows, M_A)
        if i1 is None:
            continue
        s1 = first(rows, lambda r: is_slash(r["clip"]), i1)
        first_delay.append(None if s1 is None else s1 - i1)
        i2 = press_idx(rows, M_A, i1 + 1)
        if i2 is None:
            continue
        s2 = first(rows, lambda r: r["attacking"] and r["tm"].get("atk_cd", 0) > 0.27, i2)
        g = rows[i2]["onGround"]
        tab[("side" if p.get("side") else "down", i2 - i1, g)].append(None if s2 is None or s2 - i2 > 6 else s2 - i2)
    print("\n== the slash cadence after a whiff: second press j frames after the first (kind, j, grounded): delays ==")
    for k, v in sorted(tab.items()):
        print(f"  {k}: {''.join('x' if d is None else str(d) for d in v)}")
    print(f"  first slash delay {cnt(first_delay)}")
    return {f"{a}|{b}|{c}": v for (a, b, c), v in tab.items()}


# ---- (4) / (5) pogo and side contacts on the Clapper -------------------------------------------------------------------

def an_pogo(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows or p.get("skip"):
        return None
    iP = press_idx(rows, M_A)
    if iP is None:
        return None
    iC = first(rows, lambda r: any(h.get("src") in ("DownSlash", "DownSlashAlt") and h.get("type") == CLAPPER
                                   for h in r["hits"]), iP)
    s = first(rows, lambda r: is_slash(r["clip"]), iP)
    o = {"kind": t["exp"], "pre_dash": p.get("pre_dash"), "yb_P": rows[iP]["yb"], "vy_P": rows[iP]["vy"],
         "slash": None if s is None else s - iP, "st": (rows[iP].get("cl") or {}).get("st")}
    if iC is None or iC - iP > 12:
        o["hit"] = False
        return o
    o["hit"] = True
    o["contact"] = iC - iP
    r = rows[iC]
    cb = (r.get("cl") or {}).get("body")
    hb = r["box"]
    if cb:
        gap = max(cb[0] - hb[2], hb[0] - cb[2], 0.0)
        o.update(gap_x=gap, above=hb[1] - cb[3], top=cb[3] - FLOOR, her_yb=r["yb"])
        o["side_contact"] = hb[1] < cb[3] - 0.05
        o["box_clear"] = gap > 0.0 or hb[1] > cb[3]
    seq = [(rows[i]["vy"], rows[i]["yb"], rows[i]["clip"], rows[i]["inv"]) for i in range(iC, min(iC + 45, len(rows)))]
    o["vy_seq"] = [round(x[0], 2) for x in seq[:14]]
    ys = [x[1] for x in seq]
    o["rise"] = max(ys) - rows[iC]["yb"] if ys else None
    o["apex_f"] = int(np.argmax(ys)) if ys else None
    o["bounce"] = any(x[0] > 15 for x in seq[:8])
    inv = [i - iC for i in range(iC - 2, min(iC + 30, len(rows))) if rows[i]["inv"] or (rows[i].get("dsinv") or 0) > 0]
    o["inv"] = (min(inv), max(inv), len(inv)) if inv else None
    o["dsinv_seq"] = [rows[i].get("dsinv") for i in range(iC - 1, min(iC + 14, len(rows)))]
    dc = [i - iC for i in range(iC, min(iC + 45, len(rows))) if rows[i]["can"].get("dash")]
    o["dash_can"] = dc[0] if dc else None
    o["dash_can_before"] = bool(rows[iC - 1]["can"].get("dash"))
    sec = p.get("second")
    o["second"] = sec
    if sec in ("ds", "dash"):
        b = M_A if sec == "ds" else M_DASH
        i2 = press_idx(rows, b, iP + 1)
        if i2 is not None:
            o["j2"] = i2 - iP
            o["j2c"] = i2 - iC
            if sec == "ds":
                s2 = first(rows, lambda r: r["attacking"] and r["tm"].get("atk_cd", 0) > 0.27, i2)
            else:
                s2 = first(rows, lambda r: str(r["clip"]) in ("Air Dash", "Dash", "Sprint Air"), i2)
            o["second_delay"] = None if s2 is None or s2 - i2 > 6 else s2 - i2
            o["second_g"] = rows[i2]["onGround"]
    return o


def report_pogo(trials) -> dict:
    res = [a for t in trials if t["exp"] in ("pogo", "side") and (a := an_pogo(t))]
    out = {}
    hits = [a for a in res if a["hit"]]
    print(f"\n== contacts on the Clapper: {len(res)} tries, {len(hits)} hits (its state at the press {cnt(a['st'] for a in hits)}) ==")
    for name, g in (("top", [a for a in hits if a.get("side_contact") is False]),
                    ("side (her box bottom below its body top)", [a for a in hits if a.get("side_contact")]),
                    ("side + her box clear of its body", [a for a in hits if a.get("side_contact") and a.get("box_clear")])):
        print(f"  {name}: n {len(g)} bounce {sum(a['bounce'] for a in g)} rise {q([a['rise'] for a in g])} "
              f"apex frame {cnt(a['apex_f'] for a in g)} gap_x {q([a.get('gap_x') for a in g])}")
        print(f"      i-frames (first, last, count; frames from the contact) {cnt(a['inv'] for a in g)}")
        print(f"      vy from the contact frame e.g. {[a['vy_seq'] for a in g[:3]]}")
        out[name] = {"n": len(g), "bounce": sum(a["bounce"] for a in g), "rise": [a["rise"] for a in g],
                     "apex": [a["apex_f"] for a in g], "inv": [a["inv"] for a in g], "gap": [a.get("gap_x") for a in g]}
    print(f"  contact frame after the press {cnt(a['contact'] for a in hits)}")
    pre = [a for a in hits if a.get("pre_dash")]
    print(f"  after a pogo that followed an air dash: n {len(pre)}, can.dash before the contact "
          f"{cnt(a['dash_can_before'] for a in pre)}, first true at contact + {cnt(a['dash_can'] for a in pre)}; "
          f"without a pre-dash: {cnt(a['dash_can'] for a in hits if not a.get('pre_dash'))}")
    for sec in ("ds", "dash"):
        g = [a for a in hits if a.get("second") == sec and a.get("j2") is not None]
        tab = defaultdict(list)
        for a in g:
            tab[a["j2"]].append(a.get("second_delay"))
        print(f"  second {sec} at j frames after the first press (j: delays / x none): {_seq_str(tab)}")
        out[f"second_{sec}"] = {int(j): v for j, v in tab.items()}
        if sec == "dash":
            print("     after a pre-dash (j: delay): " + " ".join(f"{a['j2']}:{'x' if a.get('second_delay') is None else a['second_delay']}" for a in g if a.get("pre_dash")))
    out["rows"] = [{k: a.get(k) for k in ("kind", "pre_dash", "hit", "contact", "gap_x", "above", "top", "side_contact",
                                          "box_clear", "rise", "apex_f", "bounce", "inv", "dash_can", "j2",
                                          "second", "second_delay", "st")} for a in res]
    return out


# ---- (6) the Idle hook --------------------------------------------------------------------------------------------------

MOVES = ("Slam Antic", "Evade Scuttle", "Spell Antic", "Jump Antic", "Cast Slam Antic", "Jump Aim")


def an_hook(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows or p.get("skip"):
        return None
    iP = press_idx(rows, M_CLAW)
    if iP is None:
        return None
    he = fsm_list(rows, "Harpoon Dash")
    iN = first(rows, lambda r: any(h.get("src") == "Harpoon Damager" for h in r["hits"]), iP)
    iD = first(rows, lambda r: any(h.get("src") == "Harpoon Dash Damager" for h in r["hits"]), iP)
    iDash = next((i for i, fr, to_ in he if to_ in ("Dash", "Dash To Enemy") and i >= iP), None)
    iCtl = first(rows, lambda r: r["acc"], iP + 2)
    cl0 = rows[iP].get("cl") or {}
    ce = [(i, fr, to) for i, r in enumerate(rows) for (fr, to) in r["cfsm"] if i >= iP]
    o = {"st_P": cl0.get("st"), "t_P": cl0.get("t"), "dx_P": None if not cl0 else cl0["x"] - rows[iP]["x"],
         "needle": None if iN is None else iN - iP, "dmg": None if iD is None else iD - iP,
         "dash": None if iDash is None else iDash - iP, "ctrl": None if iCtl is None else iCtl - iP,
         "first_tr": None if not ce else (ce[0][0] - iP, ce[0][1], ce[0][2]),
         "chain": [(i - iP, fr, to) for i, fr, to in ce[:6]]}
    iDmg = next((i for i, fr, to in ce if to == "Dmg Attack"), None)
    o["dmg_attack"] = None if iDmg is None else iDmg - iP
    nxt = next(((i, to) for i, fr, to in ce if to in MOVES), None)
    o["next_move"] = None if nxt is None else (nxt[0] - iP, nxt[1])
    sec = p.get("second")
    o["second"] = sec
    if iCtl is not None:
        o["ctl_vy"] = rows[iCtl]["vy"]
        o["vy_after"] = [round(rows[i]["vy"], 2) for i in range(iCtl, min(iCtl + 12, len(rows)))]
        if sec in ("claw_away", "atk"):
            b = M_CLAW if sec == "claw_away" else M_A
            i2 = press_idx(rows, b, iCtl)
            if i2 is not None:
                o["j2"] = i2 - iCtl
                s2 = first(rows, (lambda r: str(r["clip"]).startswith("Harpoon Antic")) if sec == "claw_away"
                           else (lambda r: is_slash(r["clip"])), i2)
                o["second_delay"] = None if s2 is None or s2 - i2 > 12 else s2 - i2
                o["vy_at_2"] = [round(rows[i]["vy"], 2) for i in range(i2, min(i2 + 8, len(rows)))]
    return o


def report_hook(trials) -> dict:
    res = [a for t in trials if t["exp"] == "hook" and (a := an_hook(t))]
    out = {}
    print(f"\n== the Clawline at the Clapper: {len(res)} presses; its state at the press {cnt(a['st_P'] for a in res)} ==")
    for st_ in sorted({a["st_P"] for a in res}, key=str):
        g = [a for a in res if a["st_P"] == st_]
        print(f"  {st_}: n {len(g)}  |dx| {q([abs(a['dx_P']) for a in g if a['dx_P'] is not None])}")
        print(f"     needle hit P+ {cnt(a['needle'] for a in g)}   dash P+ {cnt(a['dash'] for a in g)}   "
              f"dash damage P+ {cnt(a['dmg'] for a in g)}   control P+ {cnt(a['ctrl'] for a in g)}")
        print(f"     its first Control transition P+ {cnt(a['first_tr'][0] if a['first_tr'] else None for a in g)}; "
              f"Dmg Attack P+ {cnt(a['dmg_attack'] for a in g)}")
        print(f"     next move first frame (P+, move) {cnt(a['next_move'] for a in g)}")
        rel = [a["next_move"][0] - a["needle"] for a in g if a["next_move"] and a["needle"] is not None]
        print(f"     next move - needle hit {cnt(rel)}")
        rel2 = [a["next_move"][0] - a["dmg"] for a in g if a["next_move"] and a["dmg"] is not None]
        print(f"     next move - dash damage {cnt(rel2)}")
        out[str(st_)] = {"n": len(g), "needle": [a["needle"] for a in g], "dmg": [a["dmg"] for a in g],
                         "ctrl": [a["ctrl"] for a in g], "next": [a["next_move"] for a in g],
                         "dmg_attack": [a["dmg_attack"] for a in g], "dx": [a["dx_P"] for a in g],
                         "chain": [a["chain"] for a in g]}
    print(f"  example chains: {[a['chain'] for a in res[:3]]}")
    print(f"  vy from control (hooked) {cnt(tuple(a.get('vy_after', [])[:4]) for a in res)}")
    for sec in ("claw_away", "atk"):
        g = [a for a in res if a.get("second") == sec and a.get("j2") is not None]
        tab = defaultdict(list)
        for a in g:
            tab[a["j2"]].append(a.get("second_delay"))
        print(f"  (8) hooked, second {sec} at control + j: {_seq_str(tab)}")
        out[f"second_{sec}"] = {int(j): v for j, v in tab.items()}
        if sec == "claw_away":
            print(f"     vy from the second press: {[a.get('vy_at_2') for a in g[:6]]}")
    return out


def an_idle_hit(t: dict) -> dict | None:
    """A side / up slash on the Idle Clapper: the hit frame to its Control FSM's Dmg Attack and the next move."""
    rows, p = t["rows"], t.get("res") or {}
    if not rows or p.get("skip"):
        return None
    iP = press_idx(rows, M_A)
    if iP is None:
        return None
    iH = first(rows, lambda r: any(h.get("type") == CLAPPER and h.get("src") not in ("Harpoon Damager",
                                                                                    "Harpoon Dash Damager")
                                   for h in r["hits"]), iP)
    cl0 = rows[iP].get("cl") or {}
    ce = [(i, fr, to) for i, r in enumerate(rows) for (fr, to) in r["cfsm"] if i >= iP]
    iDmg = next((i for i, fr, to in ce if to == "Dmg Attack"), None)
    nxt = next(((i, to) for i, fr, to in ce if to in MOVES), None)
    src = None if iH is None else next(h.get("src") for h in rows[iH]["hits"] if h.get("type") == CLAPPER)
    stH = None if iH is None else (rows[iH - 1].get("cl") or {}).get("st")     # before the hit frame's transitions
    return {"kind": p.get("kind"), "st_P": cl0.get("st"), "t_P": cl0.get("t"), "hit": None if iH is None else iH - iP,
            "src": src, "st_hit": stH, "dmg_attack": None if iDmg is None else iDmg - iP,
            "next_move": None if nxt is None else (nxt[0] - iP, nxt[1]), "chain": [(i - iP, fr, to) for i, fr, to in ce[:5]]}


def report_idle_hit(trials) -> dict:
    res = [a for t in trials if t["exp"] == "idle_hit" and (a := an_idle_hit(t))]
    hits = [a for a in res if a["hit"] is not None and a["st_hit"] in ("Idle", "Walk")]
    print(f"\n== a slash on the Idle Clapper: {len(res)} presses, {len(hits)} hits while it was Idle "
          f"(hit sources {cnt(a['src'] for a in hits)}) ==")
    d = [a["dmg_attack"] - a["hit"] for a in hits if a["dmg_attack"] is not None]
    print(f"  states before the hit {cnt(a['st_hit'] for a in hits)}")
    print(f"  Dmg Attack - the hit (frames) {cnt(d)}; no Dmg Attack {sum(a['dmg_attack'] is None for a in hits)}")
    n = [a["next_move"][0] - a["hit"] for a in hits if a["next_move"]]
    print(f"  next move - the hit {cnt(n)}; moves {cnt(a['next_move'][1] for a in hits if a['next_move'])}")
    print(f"  chains e.g. {[a['chain'] for a in hits[:4]]}")
    miss = [a for a in res if a["hit"] is None or a["st_hit"] != "Idle"]
    print(f"  not a hit on Idle: {len(miss)} (its state at the hit {cnt(a['st_hit'] for a in miss)})")
    return {"n": len(res), "hits": len(hits), "dmg_minus_hit": d, "next_minus_hit": n,
            "rows": [{k: a.get(k) for k in ("kind", "st_P", "t_P", "hit", "src", "st_hit", "dmg_attack", "next_move")}
                     for a in res]}


# ---- the kinematics model against the hero-only trials ----------------------------------------------------------------

KIN_EXPS = ("fl_atk", "fl_claw", "drift", "claw_air", "claw_gnd", "dash_g", "ds_whiff", "reopen")
KIN_KEYS = ("hero", "input", "act", "game", "fs", "dt", "udt", "ts", "ev", "pause", "f")


def kin_check(recs, params=None, tol: float = 0.1, replay: bool = True, verbose: int = 0,
              trials_name: str = "m0_trials.jsonl", exps=None) -> dict:
    """Roll the hero model (kinematics / kin_jit) from each hero-only trial's last standing frame with the logged
    latched masks (and, replay=True, the logged dt / physics steps), compare her box centre frame by frame; a Clawline
    press ends the comparison (the model has no Clawline). Returns per trial the first frame over tol (its clip and
    the model's mode), the max error and the error at the end. trials_name / exps: another probe's trial log and
    hero-only experiments (m4_probe)."""
    from ssbot.knowledge import kinematics as km
    from ssbot.record.recorder import RecordingReader
    params = params or km.HeroParams.load(km.REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json")
    out = []
    for rec in recs:
        rec = Path(rec)
        rr = RecordingReader(rec)
        terr = None
        for _, m in rr.terrain():
            if isinstance(m, dict) and m.get("scene_raw"):
                terr = km.Terrain2D.from_message(m, params.scene(m["scene_raw"]))
                break
        trials = [json.loads(l) for l in (rec / trials_name).read_text(encoding="utf-8").splitlines() if l.strip()]
        for t in trials:
            if t["exp"] not in (exps or KIN_EXPS):
                continue
            res = t.get("res") or {}
            f0, f1 = res.get("f0"), res.get("f1")
            if f0 is None or f1 is None:
                continue
            states = list(rr.states(f0 - 40, f1 + 1, keys=KIN_KEYS))
            tr = km.Trace.from_states(states, params, mask_source="act")
            fr = np.asarray(tr.f)
            ist = np.flatnonzero(fr == f0 - 1)
            if not len(ist):
                continue
            st = int(ist[0])
            end = len(fr) - 1
            claw = [i for i in range(st + 1, end + 1) if int(tr.mask[i]) & M_CLAW]
            if claw:
                end = claw[0] - 1
            if end - st < 3:
                continue
            S = km.estimate_state(tr, [st], params, terrain=terr)
            I = np.arange(st + 1, end + 1)
            kw = dict(dt=tr.dt[I][None], fs=tr.fs[I][None], udt=tr.udt[I][None]) if replay else {}
            r = km.rollout(S, np.asarray(tr.mask)[I][None], params, terr, **kw)
            obs = 0.5 * (np.asarray(tr.box)[I, :2] + np.asarray(tr.box)[I, 2:])
            mod = r.centre[0, 1:]
            err = np.linalg.norm(mod - obs, axis=1)
            bad = np.flatnonzero(err > tol)
            clips = [tr.clips[c] if hasattr(tr, "clips") else None for c in np.asarray(tr.clip)[I]] if hasattr(tr, "clip") else None
            o = {"exp": t["exp"], "v": res.get("v"), "n": len(I), "max": float(err.max()), "end": float(err[-1]),
                 "first_bad": None if not len(bad) else int(bad[0]), "claw_cut": bool(claw), "rec": str(rec), "f0": f0}
            # the attacks: the frames where the logged cstate attacking / the model's F_ATTACKING turn on
            a_obs = np.asarray(tr.flag("attacking"))[I].astype(bool)
            a_mod = (r.flags[0, 1:] & km.F_ATTACKING) != 0
            on_obs = [int(i) for i in np.flatnonzero(a_obs & ~np.r_[False, a_obs[:-1]])]
            on_mod = [int(i) for i in np.flatnonzero(a_mod & ~np.r_[False, a_mod[:-1]])]
            o["atk_obs"], o["atk_mod"] = on_obs, on_mod
            o["atk_ok"] = on_obs == on_mod
            if len(bad):
                b = int(bad[0])
                o["bad_clip"] = clips[b] if clips else None
                o["bad_mode"] = int(r.mode[0, b + 1])
                o["bad_err"] = (float(mod[b, 0] - obs[b, 0]), float(mod[b, 1] - obs[b, 1]))
            out.append(o)
            if verbose:
                print(o)
    return {"trials": out}


def report_kin(res: dict, label: str) -> dict:
    tr = res["trials"]
    print(f"\n== the hero model vs the trials ({label}): {len(tr)} trials ==")
    by = defaultdict(list)
    for o in tr:
        by[(o["exp"], o.get("v"))].append(o)
    summ = {}
    for k, g in sorted(by.items(), key=lambda x: str(x[0])):
        ok = sum(o["first_bad"] is None for o in g)
        aok = sum(bool(o.get("atk_ok")) for o in g)
        print(f"  {str(k):28s} n {len(g):3d} within 0.1 u throughout {ok:3d}  attack onsets equal {aok:3d}  max err {q([o['max'] for o in g], (50, 90, 100))}"
              f"  first miss at frame {cnt(o['first_bad'] for o in g if o['first_bad'] is not None)}  clip "
              f"{cnt(o.get('bad_clip') for o in g if o['first_bad'] is not None)}")
        summ[str(k)] = {"n": len(g), "ok": ok, "max": [o["max"] for o in g]}
    return summ


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recs", nargs="+")
    ap.add_argument("--kin", action="store_true", help="also roll the hero model against the hero-only trials")
    ap.add_argument("--rows", default=None, help="write the extracted trials (pickle)")
    ap.add_argument("--from-rows", default=None, help="read the trials from this pickle instead")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    if a.from_rows:
        trials = pickle.loads(Path(a.from_rows).read_bytes())
    else:
        trials = []
        for d in a.recs:
            trials += extract(Path(d))
        if a.rows:
            Path(a.rows).write_bytes(pickle.dumps(trials))
    print(f"{len(trials)} trials: {cnt(t['exp'] for t in trials)}")
    out = {"n": cnt(t["exp"] for t in trials)}
    out["fl_atk"] = report_fl(trials, "fl_atk")
    out["fl_claw"] = report_fl(trials, "fl_claw")
    out["drift"] = an_drift(trials)
    out["inflate"] = an_inflate_entry(trials)
    out["claw"] = report_claw(trials)
    out["dash"] = an_dash(trials)
    out["whiff"] = an_whiff(trials)
    out["pogo"] = report_pogo(trials)
    out["hook"] = report_hook(trials)
    out["idle_hit"] = report_idle_hit(trials)
    out["reopen"] = an_reopen(trials)
    if a.kin:
        out["kin"] = report_kin(kin_check(a.recs), "the current model")
    if a.json:
        Path(a.json).write_text(json.dumps(out, default=str, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
