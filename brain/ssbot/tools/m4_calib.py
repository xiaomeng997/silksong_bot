"""Map v2 stage M4a: the numbers from the m4_probe recordings (the air dash, the dash with jump held, the restore by
the Clawline, the hooked body's contact after control, the jump in the pogo bounce, the dash re-pressed at its end;
forum.md section 95).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m4_calib <recording dir> [...] [--rows OUT.pkl | --from-rows IN.pkl]
        [--json C:/ssbot/data/m2_play/map2/m4/probes_calib.json] [--kin]

Frames are rendered 60 fps frames; P is the first frame whose latched ACTION mask holds the key (M0's convention); u
world units (her box centre unless stated). The trial rows are m0_calib's plus the damage_blocked attempts (source,
first_f, last_f), the damage events, her health and invincibility.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.tools import m0_calib as mc
from ssbot.tools.m0_calib import M_A, M_CLAW, M_D, M_DASH, M_J, cnt, first, fsm_list, is_slash, press_idx, q

BODY_SRC = "Song Heavy Sentry"         # the Clapper's root object (its body's DamageHero)
# her HeroBox (HeroBoxNormal, movement_kinematics.md): x half width 0.2277, y from her box bottom + 0.0477 to + 2.2977
HB_HW, HB_Y0, HB_Y1 = 0.2277, 0.0477, 2.2977
HERO_EXPS = ("adash", "adash_claw", "gdash_jump", "dash_end")


def frame_row(s: dict, idx: dict, hero_names: set) -> dict:
    r = mc.frame_row(s, idx, hero_names)
    h = s.get("hero") or {}
    r["dblk"] = [ev.get("d") or {} for ev in (s.get("ev") or ()) if ev.get("k") == "damage_blocked"]
    r["dmg"] = [ev.get("d") or {} for ev in (s.get("ev") or ()) if ev.get("k") == "damage"]
    r["hp"] = h.get("health")
    r["isinv"] = h.get("is_invincible")
    r["ctd"] = h.get("can_take_damage")
    return r


def extract(rec_dir: Path) -> list[dict]:
    from ssbot.record.recorder import RecordingReader
    idx = mc._cs_index()
    trials = [json.loads(l) for l in (rec_dir / "m4_trials.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rr = RecordingReader(rec_dir)
    out = []
    for t in trials:
        res = t.get("res") or {}
        f0, f1 = res.get("f0"), res.get("f1")
        t["rec"] = str(rec_dir)
        if f0 is None or f1 is None or res.get("skip"):
            t["rows"] = []
            out.append(t)
            continue
        t["rows"] = [frame_row(s, idx, set()) for s in rr.states(f0 - 4, f1 + 1)]
        out.append(t)
    return out


def body_src(src) -> bool:
    return str(src or "").split("/")[-1] == BODY_SRC


def herobox(r: dict) -> tuple:
    b = r["box"]
    return (r["x"] - HB_HW, b[1] + HB_Y0, r["x"] + HB_HW, b[1] + HB_Y1)


def overlap(a, b) -> bool:
    return a is not None and b is not None and a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def sprint_ev(rows, start=0):
    return [(i, fr, to) for (i, fr, to) in fsm_list(rows, "Sprint") if i >= start]


# ---- (a) / (b) the air dash ------------------------------------------------------------------------------------------

CANCEL_BIT = {"atk": M_A, "datk": M_A, "jump": M_J, "claw": M_CLAW, "dash2": M_DASH}


def an_adash(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows:
        return None
    iP = press_idx(rows, M_DASH)
    if iP is None:
        return None
    air = not rows[iP - 1]["onGround"]
    d = p.get("d") or 1
    se = sprint_ev(rows, iP)
    i_dashing = first(rows, lambda r: r["dashing"], iP)
    i_try = next((i for i, fr, to in se if to == "Try"), None)
    i_as = next((i for i, fr, to in se if to.startswith("Air Sprint")), None)
    i_loop = next((i for i, fr, to in se if "Loop" in to), None)
    i_out = next((i for i, fr, to in se if i_as is not None and i > i_as and fr.startswith("Air Sprint")), None)
    out_to = next((to for i, fr, to in se if i == i_out and fr.startswith("Air Sprint")), None)
    i_idle = next((i for i, fr, to in se if to == "Idle" and i > iP), None)
    i_acc = first(rows, lambda r: r["acc"], (i_try or iP) + 1)
    x0, y0 = rows[iP - 1]["x"], rows[iP - 1]["yb"]
    prof = [(round(d * (rows[i]["x"] - x0), 3), round(rows[i]["yb"] - y0, 3), round(d * rows[i]["vx"], 2),
             round(rows[i]["vy"], 2)) for i in range(iP, min(iP + 40, len(rows)))]
    o = {"air": air, "jh": bool(rows[iP]["m"] & M_J), "tap": p.get("tap"), "h": p.get("h"), "cancel": p.get("cancel"),
         "c": p.get("c"), "k": p.get("k"), "after": p.get("after"),
         "dash_on": None if i_dashing is None else i_dashing - iP, "try": None if i_try is None else i_try - iP,
         "air_sprint": None if i_as is None else i_as - iP, "loop": None if i_loop is None else i_loop - iP,
         "out": None if i_out is None else i_out - iP, "out_to": out_to,
         "idle": None if i_idle is None else i_idle - iP, "acc": None if i_acc is None else i_acc - iP,
         "prof": prof, "yb0": y0, "vy0": rows[iP - 1]["vy"], "gs_hint": None}
    # the cancel: its press edge, the FSM's exit from the air sprint and what followed
    cn = p.get("cancel")
    if cn in CANCEL_BIT:
        iC = press_idx(rows, CANCEL_BIT[cn], iP + 1)
        o["cancel_press"] = None if iC is None else iC - iP
        if iC is not None:
            nxt = None
            for i in range(iC, min(iC + 30, len(rows))):
                r = rows[i]
                if cn in ("atk", "datk") and is_slash(r["clip"]):
                    nxt = ("slash", i - iC, r["clip"])
                    break
                if cn == "jump" and any(f_ == "Umbrella Float" and to == "Antic" for (f_, fr, to) in r["fsm"]):
                    nxt = ("umbrella", i - iC, None)
                    break
                if cn == "jump" and r.get("jumping") and not rows[i - 1].get("jumping"):
                    nxt = ("jump", i - iC, None)
                    break
                if cn == "claw" and str(r["clip"]).startswith("Harpoon"):
                    nxt = ("harpoon", i - iC, r["clip"])
                    break
                if cn == "dash2" and r["dashing"] and not rows[i - 1]["dashing"]:
                    nxt = ("dash", i - iC, None)
                    break
            o["cancel_effect"] = nxt
            o["state_at_cancel"] = ("sprint" if (i_as is not None and i_as <= iC and (i_out is None or iC <= i_out))
                                    else ("dash" if i_dashing is not None and iC < (i_as or 10 ** 9) else "after"))
            o["fsm_after_cancel"] = [(i - iC, fr, to) for (i, fr, to) in se if iC <= i < iC + 12][:6]
    return o


def report_adash(trials) -> dict:
    res = [a for t in trials if t["exp"] == "adash" and (a := an_adash(t))]
    air = [a for a in res if a["air"]]
    out: dict = {"n": len(res), "air": len(air)}
    print(f"\n== (a) the air dash: {len(res)} presses, airborne {len(air)} ==")
    taps = [a for a in air if a["tap"] and a["cancel"] in ("none", None)]
    print(f"  tapped, no cancel: n {len(taps)}")
    print(f"    dashing from P+ {cnt(a['dash_on'] for a in taps)}; Sprint Try P+ {cnt(a['try'] for a in taps)}; "
          f"Air Sprint P+ {cnt(a['air_sprint'] for a in taps)}; loop P+ {cnt(a['loop'] for a in taps)}; "
          f"its exit P+ {cnt(a['out'] for a in taps)} -> {cnt(a['out_to'] for a in taps)}; control P+ "
          f"{cnt(a['acc'] for a in taps)}")
    for kf in (2, 5, 10, 15, 20, 25):
        dx = [a["prof"][kf][0] for a in taps if len(a["prof"]) > kf]
        dy = [a["prof"][kf][1] for a in taps if len(a["prof"]) > kf]
        print(f"    P+{kf:2d}: dx {q(dx, (10, 50, 90))}  dy {q(dy, (10, 50, 90))}")
    out["tap_events"] = {k: cnt(a[k] for a in taps) for k in ("dash_on", "try", "air_sprint", "loop", "out", "acc")}
    held = [a for a in air if not a["tap"] and a["cancel"] in ("none", None)]
    print(f"  held h frames, no cancel: n {len(held)}; loop P+ {cnt(a['loop'] for a in held)}; exit - h "
          f"{cnt((a['out'] - a['h']) if a['out'] is not None else None for a in held)}")
    for cn in ("atk", "datk", "jump", "claw", "dash2"):
        g = [a for a in air if a["cancel"] == cn and a.get("cancel_press") is not None]
        tab = defaultdict(list)
        for a in g:
            e = a.get("cancel_effect")
            tab[a["cancel_press"]].append(None if e is None else e[1])
        print(f"  cancel {cn:5s}: n {len(g)}  per press frame P+c: delay to its effect (x = none) "
              f"{mc._seq_str(tab)}")
        print(f"      effects {cnt(None if a.get('cancel_effect') is None else a['cancel_effect'][0] for a in g)}; "
              f"FSM exits {cnt(a['out_to'] for a in g)}")
        out[f"cancel_{cn}"] = {int(c): v for c, v in tab.items()}
    jh = [a for a in air if a["jh"]]
    print(f"  jump held at the press: n {len(jh)} (b)")
    return out


# ---- the restore by the Clawline -----------------------------------------------------------------------------------

def an_adash_claw(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows:
        return None
    iC = press_idx(rows, M_CLAW)
    if iC is None:
        return None
    pre = p.get("pre")
    iD = press_idx(rows, M_DASH) if pre else None
    i_h = first(rows, lambda r: str(r["clip"]).startswith("Harpoon"), iC)
    i_ctl = first(rows, lambda r: r["acc"] and not str(r["clip"]).startswith("Harpoon"), (i_h or iC) + 2)
    i2 = press_idx(rows, M_DASH, (i_ctl or iC) + 0) if i_ctl is not None else None
    dash2 = None
    if i2 is not None:
        i_on = first(rows, lambda r: r["dashing"], i2)
        dash2 = None if i_on is None or i_on - i2 > 12 else i_on - i2
    can_ctl = None if i_ctl is None else rows[i_ctl]["can"].get("dash")
    se = sprint_ev(rows, iD or 0)
    in_sprint = None
    if pre and iD is not None:
        i_as = next((i for i, fr, to in se if to.startswith("Air Sprint")), None)
        i_out = next((i for i, fr, to in se if i_as is not None and i > i_as and fr.startswith("Air Sprint")), None)
        in_sprint = i_as is not None and i_as <= iC and (i_out is None or iC < i_out)
    return {"pre": pre, "airdash_used": bool(iD is not None and first(rows, lambda r: r["dashing"], iD) is not None),
            "c": p.get("c"), "claw_delay": None if i_h is None else i_h - iC, "in_sprint": in_sprint,
            "ctrl": None if i_ctl is None else i_ctl - iC, "j2": None if i2 is None or i_ctl is None else i2 - i_ctl,
            "dash2": dash2, "can_dash_ctl": can_ctl, "ground_ctl": None if i_ctl is None else rows[i_ctl]["onGround"]}


def report_adash_claw(trials) -> dict:
    res = [a for t in trials if t["exp"] == "adash_claw" and (a := an_adash_claw(t))]
    print(f"\n== (a) the restore by the unhooked Clawline: {len(res)} ==")
    out = {}
    for lab, g in (("air dash used before", [a for a in res if a["pre"] and a["airdash_used"]]),
                   ("no air dash before", [a for a in res if not a["pre"]])):
        g2 = [a for a in g if not a["ground_ctl"]]
        print(f"  {lab}: n {len(g)} (airborne at control {len(g2)}); the Clawline from its press P+ "
              f"{cnt(a['claw_delay'] for a in g)}; pressed in the air sprint {cnt(a['in_sprint'] for a in g)}")
        print(f"    can.dash at control {cnt(a['can_dash_ctl'] for a in g2)}; the dash at control + j fired after "
              f"{cnt(a['dash2'] for a in g2)} (None = never)")
        out[lab] = {"n": len(g), "can_dash_ctl": cnt(a["can_dash_ctl"] for a in g2), "dash2": cnt(a["dash2"] for a in g2),
                    "claw_delay": cnt(a["claw_delay"] for a in g), "in_sprint": cnt(a["in_sprint"] for a in g)}
    sp = [a for a in res if a["in_sprint"]]
    tab = defaultdict(list)
    for a in sp:
        tab[a["c"]].append(a["claw_delay"])
    print(f"  the Clawline pressed in the air sprint: per c (frames after the dash press) the delay to its antic: "
          f"{mc._seq_str(tab)}")
    out["claw_in_sprint"] = {int(c): v for c, v in tab.items()}
    return out


# ---- (b) on the ground, the dash re-pressed at its end ---------------------------------------------------------------

def an_gdash_jump(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows:
        return None
    iD = press_idx(rows, M_DASH)
    iJ = press_idx(rows, M_J)
    if iD is None or iJ is None:
        return None
    i_off = first(rows, lambda r: not r["onGround"], min(iD, iJ))
    i_land = first(rows, lambda r: r["onGround"], (i_off or iJ) + 2)
    top = max(r["yb"] for r in rows[min(iD, iJ):])
    se = sprint_ev(rows, iD)
    d = p.get("d") or 1
    return {"v": p.get("v"), "j": p.get("j"), "H": p.get("H"), "held": p.get("held"), "off": None if i_off is None
            else i_off - iJ, "top": round(top, 3), "air_frames": None if i_off is None or i_land is None
            else i_land - i_off, "dx_land": None if i_land is None else round(d * (rows[i_land]["x"] - rows[iD]["x"]), 3),
            "fsm": [(i - iD, fr, to) for i, fr, to in se][:10]}


def an_dash_end(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows:
        return None
    iD = press_idx(rows, M_DASH)
    if iD is None:
        return None
    i2 = press_idx(rows, M_DASH, iD + 1)
    se = sprint_ev(rows, iD)
    i_end = first(rows, lambda r: not r["dashing"], first(rows, lambda r: r["dashing"], iD) or iD)
    # sprinting on: still faster than the run 5 frames after the re-press (the FSM may enter Ground Sprint and skid at
    # once: its state names do not tell)
    j = (i2 or iD) + 5
    spr = j < len(rows) and abs(rows[j]["vx"]) > 12.0
    vx = [round(abs(rows[i]["vx"]), 1) for i in range(i2 or iD, min((i2 or iD) + 14, len(rows)))]
    return {"j": p.get("j"), "re": None if i2 is None or i_end is None else i2 - i_end, "sprint_after": spr,
            "fsm": [(i - iD, fr, to) for i, fr, to in se][:12], "vx": vx}


# ---- (c) the hooked body's contact after control ------------------------------------------------------------------

def an_hook_touch(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows or p.get("skip"):
        return None
    iP = press_idx(rows, M_CLAW)
    if iP is None:
        return None
    he = fsm_list(rows, "Harpoon Dash")
    i_hit = first(rows, lambda r: any(h.get("src") == "Harpoon Damager" for h in r["hits"]), iP)
    if i_hit is None:
        return {"hooked": False, "inv": p.get("inv")}
    i_ctl = first(rows, lambda r: r["acc"], iP + 2)
    if i_ctl is None:
        return None
    i_idle = next((i for i, fr, to in he if to == "Idle" and i > i_ctl - 2), None)
    i_dash_to = next((i for i, fr, to in he if to in ("Dash To Enemy", "Dash") and i >= iP), None)
    f_ctl = rows[i_ctl]["f"]
    ov = [i - i_ctl for i in range(iP, len(rows))
          if overlap(herobox(rows[i]), ((rows[i].get("cl") or {}).get("body") or (None,) * 4)[:4]
                     if (rows[i].get("cl") or {}).get("body") else None)]
    att = []
    for i in range(iP, len(rows)):
        for d_ in rows[i]["dblk"]:
            if body_src(d_.get("source")):
                att.append((d_.get("first_f") - f_ctl, d_.get("last_f") - f_ctl, d_.get("why")))
    dmg = [(i - i_ctl, d_.get("source"), d_.get("amount")) for i in range(iP, len(rows)) for d_ in rows[i]["dmg"]]
    hp_drop = first(rows, lambda r: r["hp"] is not None and rows[iP]["hp"] is not None and r["hp"] < rows[iP]["hp"], iP)
    i_act = None
    if p.get("act") == "dash":
        i_act = press_idx(rows, M_DASH, i_ctl)
    dash_ok = None
    if i_act is not None:
        i_on = first(rows, lambda r: r["dashing"], i_act)
        dash_ok = None if i_on is None or i_on - i_act > 6 else i_on - i_act
    return {"hooked": True, "inv": p.get("inv"), "act": p.get("act"), "k": p.get("k"), "ctrl_P": i_ctl - iP,
            "hit_P": i_hit - iP, "dash_to": None if i_dash_to is None else i_dash_to - iP,
            "idle": None if i_idle is None else i_idle - i_ctl, "ov": ov, "att": att, "dmg": dmg,
            "hp_drop": None if hp_drop is None else hp_drop - i_ctl,
            "act_at": None if i_act is None else i_act - i_ctl, "dash_ok": dash_ok,
            "st_hit": (rows[i_hit].get("cl") or {}).get("st"),
            "st_ctl": (rows[i_ctl].get("cl") or {}).get("st"), "gap_ctl": _gap(rows[i_ctl])}


def _gap(r: dict):
    b = (r.get("cl") or {}).get("body")
    if not b:
        return None
    hb = herobox(r)
    return round(max(b[0] - hb[2], hb[0] - b[2]), 3)


def report_hook_touch(trials) -> dict:
    res = [a for t in trials if t["exp"] == "hook_touch" and (a := an_hook_touch(t))]
    hk = [a for a in res if a.get("hooked")]
    print(f"\n== (c) the hooked body after control: {len(res)} trials, hooked {len(hk)} "
          f"(invincible {sum(bool(a['inv']) for a in hk)}) ==")
    print(f"  control P+ {cnt(a['ctrl_P'] for a in hk)}; the Harpoon FSM's Idle control+ {cnt(a['idle'] for a in hk)}; "
          f"gap at control (HeroBox to body, u) {q([a['gap_ctl'] for a in hk], (10, 50, 90))}")
    print(f"  the air dash at control + k fired after {cnt(a['dash_ok'] for a in hk if a['act'] == 'dash')}")
    rows_out = []
    for a in hk:
        ov = a["ov"]
        ov_after = [k for k in ov if k >= -12]
        first_ov = min(ov_after) if ov_after else None
        last_ov = max(ov_after) if ov_after else None
        att_first = min((x[0] for x in a["att"] if x[0] >= -30), default=None)
        dmg_body = [x for x in a["dmg"] if body_src(x[1])]
        dmg_first = min((x[0] for x in dmg_body), default=None)
        rows_out.append({"inv": a["inv"], "act": a["act"], "k": a["k"], "idle": a["idle"], "ov": (first_ov, last_ov),
                         "att": att_first, "dmg": dmg_first, "dmg_other": [x for x in a["dmg"] if not body_src(x[1])],
                         "st": a["st_ctl"]})
    for r in sorted(rows_out, key=lambda r: (r["inv"], r["ov"][0] if r["ov"][0] is not None else 999)):
        print(f"   inv {str(r['inv']):5s} {r['act']:5s} k {r['k']:2d}  Idle c+{r['idle']}  her box in the body c+ "
              f"{r['ov']}  body attempts from c+ {r['att']}  body damage at c+ {r['dmg']}  other {r['dmg_other']}  "
              f"{r['st']}")
    # the verdict: a trial whose overlap starts before the Idle and lasts past it shows the first frame the body hurts
    span = [r for r in rows_out if r["ov"][0] is not None and r["idle"] is not None and r["ov"][0] < r["idle"]
            and r["ov"][1] >= r["idle"]]
    print(f"  overlaps across the Idle: n {len(span)}; the first body attempt / damage - Idle "
          f"{cnt((r['att'] if r['inv'] else r['dmg']) - r['idle'] if (r['att'] if r['inv'] else r['dmg']) is not None else None for r in span)}")
    pre = [r for r in rows_out if r["ov"][0] is not None and r["idle"] is not None and r["ov"][1] < r["idle"]]
    print(f"  overlaps ending before the Idle: n {len(pre)}; any body attempt / damage in them "
          f"{cnt(bool(r['att'] is not None and r['att'] < r['idle']) or bool(r['dmg'] is not None and r['dmg'] < r['idle']) for r in pre)}")
    return {"n": len(res), "hooked": len(hk), "rows": rows_out}


def an_hook_pd(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows or p.get("skip"):
        return None
    iD = press_idx(rows, M_DASH)
    iC = press_idx(rows, M_CLAW)
    if iD is None or iC is None:
        return None
    dashed = first(rows, lambda r: r["dashing"], iD)
    i_h = first(rows, lambda r: str(r["clip"]).startswith("Harpoon"), iC)
    i_hit = first(rows, lambda r: any(h.get("src") == "Harpoon Damager" for h in r["hits"]), iC)
    i_ctl = first(rows, lambda r: r["acc"] and not str(r["clip"]).startswith("Harpoon"), (i_h or iC) + 2)
    i2 = press_idx(rows, M_DASH, i_ctl) if i_ctl is not None else None
    dash2 = None
    if i2 is not None:
        i_on = first(rows, lambda r: r["dashing"], i2)
        dash2 = None if i_on is None or i_on - i2 > 8 else i_on - i2
    se = sprint_ev(rows, iD)
    i_as = next((i for i, fr, to in se if to.startswith("Air Sprint")), None)
    i_out = next((i for i, fr, to in se if i_as is not None and i > i_as and fr.startswith("Air Sprint")), None)
    return {"airdash": dashed is not None and not rows[iD - 1]["onGround"], "c": p.get("c"), "hooked": i_hit is not None,
            "claw_delay": None if i_h is None else i_h - iC,
            "in_sprint": i_as is not None and i_as <= iC and (i_out is None or iC < i_out),
            "can_dash_ctl": None if i_ctl is None else rows[i_ctl]["can"].get("dash"),
            "ground_ctl": None if i_ctl is None else rows[i_ctl]["onGround"],
            "j2": None if i2 is None or i_ctl is None else i2 - i_ctl, "dash2": dash2, "inv": p.get("inv"),
            "dmg": [(i - (i_ctl or iC), d_.get("source")) for i in range(iD, len(rows)) for d_ in rows[i]["dmg"]]}


def report_hook_pd(trials) -> dict:
    res = [a for t in trials if t["exp"] == "hook_pd" and (a := an_hook_pd(t))]
    g = [a for a in res if a["airdash"] and a["hooked"]]
    print(f"\n== (a) the restore by the HOOKED Clawline: {len(res)} trials, air dash then hooked {len(g)} ==")
    tab = defaultdict(list)
    for a in res:
        if a["airdash"] and a["in_sprint"]:
            tab[a["c"]].append(a["claw_delay"])
    print(f"  the Clawline pressed in the air sprint, per c: the delay to its antic {mc._seq_str(tab)}")
    ga = [a for a in g if not a["ground_ctl"]]
    print(f"  airborne at control {len(ga)}: can.dash {cnt(a['can_dash_ctl'] for a in ga)}; the dash at control + j "
          f"fired after {cnt(a['dash2'] for a in ga)}")
    print(f"  damage events (frame from control, source) {[a['dmg'] for a in res if a['dmg']]}")
    return {"n": len(res), "hooked_after_dash": len(g), "can_dash_ctl": cnt(a["can_dash_ctl"] for a in ga),
            "dash2": cnt(a["dash2"] for a in ga), "claw_in_sprint": {int(c): v for c, v in tab.items()}}


# ---- (d) the jump in the pogo bounce ------------------------------------------------------------------------------

def an_bounce_jump(t: dict) -> dict | None:
    rows, p = t["rows"], t.get("res") or {}
    if not rows or p.get("skip"):
        return None
    iA = press_idx(rows, M_A)
    if iA is None:
        return None
    iC = first(rows, lambda r: any(str(h.get("src") or "").startswith("DownSlash") and h.get("type") for h in r["hits"]), iA)
    iJ = press_idx(rows, M_J, iA)
    if iJ is None:
        return None
    ue = fsm_list(rows, "Umbrella Float")
    i_ant = next((i for i, fr, to in ue if to == "Antic" and i >= iJ), None)
    i_inf = next((i for i, fr, to in ue if to == "Inflate" and i >= iJ), None)
    i_land = first(rows, lambda r: r["onGround"], iJ)
    return {"contact": None if iC is None else iC - iA, "jc": None if iC is None else iJ - iC, "k": iJ - iA,
            "J": p.get("J"), "antic": None if i_ant is None else i_ant - iJ, "inflate": None if i_inf is None else i_inf - iJ,
            "land": None if i_land is None else i_land - iJ, "bouncing": rows[iJ].get("bouncing"),
            "vy_at_J": round(rows[iJ]["vy"], 2), "yb_J": round(rows[iJ]["yb"], 2),
            "clip_J": rows[iJ]["clip"]}


def report_bounce_jump(trials) -> dict:
    res = [a for t in trials if t["exp"] == "bounce_jump" and (a := an_bounce_jump(t))]
    hit = [a for a in res if a["contact"] is not None]
    print(f"\n== (d) the jump in the pogo bounce: {len(res)} presses, with a contact {len(hit)} "
          f"(contact P+ {cnt(a['contact'] for a in hit)}) ==")
    tab = defaultdict(list)
    for a in hit:
        tab[a["jc"]].append(a["antic"] if a["land"] is None or a["antic"] is None or a["antic"] < a["land"] else None)
    print(f"  per jump press frame (contact + j): the umbrella's antic after the press (x = none before landing) "
          f"{mc._seq_str(tab)}")
    return {"n": len(res), "contact": len(hit), "antic_by_jc": {int(c): v for c, v in tab.items()}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recs", nargs="*")
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
    out["adash"] = report_adash(trials)
    out["adash_claw"] = report_adash_claw(trials)
    g = [x for t in trials if t["exp"] == "gdash_jump" and (x := an_gdash_jump(t))]
    print(f"\n== (b) the ground dash with jump: {len(g)} ==")
    for x in g[:40]:
        print("   ", {k: v for k, v in x.items() if k != "fsm"}, x["fsm"][:6])
    out["gdash_jump"] = g
    de = [x for t in trials if t["exp"] == "dash_end" and (x := an_dash_end(t))]
    print(f"\n== the dash re-pressed at its end: {len(de)} ==")
    tab = defaultdict(list)
    for x in de:
        tab[x["re"]].append(int(x["sprint_after"]))
    print(f"  per re-press frame (relative to the first frame not dashing): sprint after (1) {mc._seq_str(tab)}")
    out["dash_end"] = de
    out["hook_touch"] = report_hook_touch(trials)
    out["hook_pd"] = report_hook_pd(trials)
    out["bounce_jump"] = report_bounce_jump(trials)
    if a.json:
        Path(a.json).write_text(json.dumps(out, default=str, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
