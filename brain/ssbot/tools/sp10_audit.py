"""The cause audit of live Clapper episodes (task 1v1 SP10a; the person, 2026-10-17: every stage audits its default's
live runs - every HP loss AND every missed planned action traced through the inputs and states of the preceding ~60
frames and classified).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp10_audit --manifest C:/ssbot/sandbox/1v1sp10base_manifest.txt \\
        --arms rnjb [--json out.json] [--traces <dir>] [--label new]

Causes (each item gets one, with a sub-label that says what exactly):
  attack cooldown         a press the plan needed was dropped by the attack cooldown (pressed while it was cooling down
                          and no attack came), or the script stood waiting for it
  airborne / landing      she was in the air (no dash left, a bounce, the umbrella) or in a landing / hurt recoil when
                          the threat became unavoidable, or the script declined because she was in the air
  script conflict         a script held the keys for the other Clapper (or a one-situation script acted while this one
                          hit her), a script was cut / handed back by another one, the slam playbook still busy with
                          the other Clapper's slam (the hand-off), a script that never got the keys (another one had them)
  L2 / planner decision   the planner, L2's target / stance or a script's own gate chose the place / the move that met the
                          threat, or declined the planned action (distance, behind, the other Clapper's danger)
  harness / host stall    the bot's keys were >= 3 frames late, or STATE frames were missing, in the decisive window

HP losses: every hp event with delta < 0 up to the fight's end (the kill). The decisive window is the 24 frames before
the hit (the last ~0.4 s an input could still change it); the trace covers 60. Who held the keys comes from the policy's
own_trace (fadc77a on; older runs: inferred from the scripts' run records and the decision log, marked "inferred").
Missed planned actions:
  slam       every Slam Antic of a Clapper with her in front of it within 8.3 u at its entry: struck (her down slash
             landed from antic + 40 to + 62) or the playbook's run (phase / why) and the cause
  idle       every Idle (re-)entry of the focus (L2's target) with her within 8.3 u while both live: hit within 30 frames
             or the IdleHit run's why (no run: another script had the keys)
  chase      every chase run (evade_chase) that ended Far (> 8.28 u)
  run ends   the scripts' runs that ended in an abort (slam playbook, chase, low hop, escape runs, cast_stab)
  press      every attack press (the latched mask's rising edge) that started no attack within 3 frames: whose keys,
             the cooldown left
Situational checks: the hits by her / its distance to a wall (two-Clapper rules near walls), the one-Clapper phase of a
two-Clapper episode (the one-Clapper scripts there), and the double slams (one Clapper's Slam Antic while the other's
slam runs): what hit her there and whether she was in the air (the person, 2026-10-17: while the first one recovers and
the second one winds up, both stand still - the air is safe; the damage colliders enabled in that gap).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from ssbot.ipc.framing import BIT
from ssbot.tools import sp7_two
from ssbot.tools.slam_play_live import manifest, pct

CD, AIR, SCR, L2, HOST = ("attack cooldown", "airborne / landing", "script conflict", "L2 / planner decision",
                          "harness / host stall")
CATS = (CD, AIR, SCR, L2, HOST)
WIN_TRACE = 60
WIN_DEC = 24                       # the decisive window before a hit
CLOSE_U = 8.3
A_BIT, J_BIT, D_BIT = 1 << BIT["attack"], 1 << BIT["jump"], 1 << BIT["dash"]
L_BIT, R_BIT, DN_BIT, UP_BIT = 1 << BIT["left"], 1 << BIT["right"], 1 << BIT["down"], 1 << BIT["up"]
LAND_CLIPS = ("Land", "Slash Land", "Hard Land", "HardLand")
HURT_CLIPS = ("Recoil", "Stun")
SCRIPT_OWN = ("slam", "stab", "low", "chase", "two", "claw")      # (SP10c: claw = CLAW_CHASE, two:jh = TWO_JUMPHIT)
MOVE_START = ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic", "Evade Scuttle")
FLOOR_Y = 3.01                     # the floor (her box bottom on the ground: her transform 4.57 - 1.56)


def _keys(m: int) -> str:
    return "".join(c if m & b else "." for c, b in (("j", J_BIT), ("a", A_BIT), ("d", D_BIT), ("u", UP_BIT),
                                                     ("v", DN_BIT), ("<", L_BIT), (">", R_BIT)))


def _src_kind(src: str) -> str:
    if "Slam Collider 1" in src:
        return "hammer"
    if "Slam Collider 2" in src:
        return "landing"
    if "rune bomb small" in src:
        return "small rune"
    if "rune slam" in src:
        return "big rune"
    if "Song Heavy Sentry" in src:
        return "body"
    return src.split("/")[-1]


# ---- per-episode data ----------------------------------------------------------------------------------------------

def _frames(states: list[dict]) -> dict:
    out = {}
    for s in states:
        f = int(s["f"])
        h = s.get("hero") or {}
        if not (h.get("box") or h.get("pos")):
            continue
        tm = h.get("tm") or {}
        a = s.get("act") or {}
        can = h.get("can") or {}
        C = {}
        for e in sp.clappers(s):
            st, tin = sp.control(e)
            C[e["iid"]] = (st, tin, float(e["pos"][0]), float(e["pos"][1]), tp.face_of(e), int(e.get("hp") or 0),
                           tp.body_span(e))
        ev_hp, ev_hit = [], []
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "hp" and (d.get("delta") or 0) < 0:
                ev_hp.append((-int(d.get("delta")), str(d.get("source"))))
            elif k == "hit" and d.get("type_key") == sp.CLAPPER and d.get("src") in HERO_ATTACKS:
                dealt = d.get("dealt", d.get("amount"))
                if dealt is None or float(dealt) > 0:
                    ev_hit.append((d.get("ent") or d.get("iid"), str(d.get("src"))))
        vel = h.get("vel") or [0.0, 0.0]
        out[f] = {"hx": sp.hero_x(s), "hy": float((h.get("pos") or [0.0, 0.0])[1]), "g": sp.on_ground(s),
                  "clip": str((h.get("anim") or {}).get("clip") or ""), "acd": float(tm.get("atk_cd") or 0.0) * 60.0,
                  "dcd": float(tm.get("dash_cd") or 0.0) * 60.0, "cd": bool(can.get("dash")),
                  "acc": bool(h.get("hero_accepting_input", True)), "m": int(a.get("mask") or 0),
                  "late": f - int(a.get("target") or f), "udt": float(s.get("udt") or 0.0),
                  "dt": float(s.get("dt") or 0.0), "hp": int(h.get("health") or 0), "vx": float(vel[0]),
                  "vy": float(vel[1]), "C": C, "hp_ev": ev_hp, "hit_ev": ev_hit}
    return out


HERO_ATTACKS = sp7_two._hero_attacks()


class Owner:
    """Who sent the keys latched at frame x: the tick x - 2's (the policy's own_trace), else inferred."""

    def __init__(self, pol: dict, dec_rows: dict):
        self.trace = pol.get("own_trace")
        self.exact = self.trace is not None
        self.iv: list[tuple[int, int, str]] = []
        self.dec = dec_rows
        self._f = sorted(dec_rows)
        if self.exact:
            self.tf = [int(r[0]) for r in self.trace]
            return
        # inferred: the scripts' run records (frames of the run) and the decision log's slam playbook masks
        for r in (pol.get("evade_chase") or {}).get("chase_runs") or ():
            if r.get("f0") is not None and r.get("k_end") is not None:
                self.iv.append((int(r["f0"]), int(r["f0"]) + int(r["k_end"]) - int(r.get("k0") or 0), "chase"))
        for r in (pol.get("rune_lowhop") or {}).get("hop_runs") or ():
            if r.get("f0") is not None:
                end = int(r.get("fa") or r["f0"]) + int(r.get("k") or 0)
                self.iv.append((int(r["f0"]), max(end, int(r["f0"])), "low"))
        for r in ((pol.get("two_play") or {}).get("idle_runs_rec") or ()):
            f0, k_press, walk = int(r[0]), r[3], int(r[5] or 0)
            n = (k_press + 2) if k_press is not None else walk
            if n:
                self.iv.append((f0, f0 + n, "two:idle"))
        for r in ((pol.get("cast_stab") or {}).get("runs") or ()):
            if r.get("f0") is not None:
                self.iv.append((int(r["f0"]), int(r["f0"]) + 60, "stab"))

    def at(self, x: int) -> tuple:
        """(own, crit, L2 target, goal, why) of the tick that sent frame x's keys."""
        t = x - sp.SEND_AHEAD
        if self.exact:
            i = int(np.searchsorted(self.tf, t, side="right")) - 1
            if i < 0:
                return ("plan", None, None, None, None)
            return tuple(self.trace[i][1:6])
        own = "plan"
        i = int(np.searchsorted(self._f, t, side="right")) - 1
        row = self.dec.get(self._f[i]) if i >= 0 and t - self._f[i] <= 3 else None
        if row is not None and (row.get("play") or {}).get("mask") is not None:
            own = "slam"
        elif row is not None and row.get("sup_mask"):
            own = "sup"
        else:
            for a, b, o in self.iv:
                if a <= t <= b:
                    own = o
                    break
        return (own, None, None if row is None else row.get("tgt"), None if row is None else row.get("goal"),
                None if row is None else row.get("goal_why"))


def _attack_starts(fr: dict) -> set:
    """Frames where an attack started (the attack cooldown jumps up)."""
    out = set()
    prev = None
    for f in sorted(fr):
        c = fr[f]["acd"]
        if prev is not None and c > prev + 5.0:
            out.add(f)
        prev = c
    return out


def _presses(fr: dict, starts: set, owner: Owner, f_lo: int, f_hi: int) -> list[dict]:
    """Every attack rising edge in the latched masks: did an attack start within 3 frames, the cooldown left, whose keys."""
    out = []
    fl = sorted(f for f in fr if f_lo <= f <= f_hi)
    prev_m = 0
    for f in fl:
        m = fr[f]["m"]
        if m & A_BIT and not prev_m & A_BIT:
            ok = any(g in starts for g in range(f, f + 4))
            st = next((g for g in sorted(starts) if g >= f), None) if not ok else None
            acd = fr[f]["acd"]
            # the game keeps a press made while cooling down: the attack then starts as the cooldown ends (delayed)
            buf = (not ok) and st is not None and acd > 1.0 and abs((st - f) - acd) <= 3
            out.append({"f": f, "ok": ok or buf, "delayed": round(acd, 1) if buf else 0, "acd": round(acd, 1),
                        "clip": fr[f]["clip"], "g": fr[f]["g"], "down": bool(m & DN_BIT),
                        "own": owner.at(f)[0], "next_start": None if st is None else st - f})
        prev_m = m
    return out


def _attacker(fr: dict, g: int, src: str, names: dict) -> object:
    """The Clapper that dealt a hit (sp7_two's mapping: the name -> iid once one fits exactly, else the nearest)."""
    r = fr.get(g) or fr.get(g - 1)
    if r is None or not r["C"]:
        return None
    nm = sp7_two._name(src)
    if nm is not None and nm in names and names[nm] in r["C"]:
        return names[nm]
    kind = _src_kind(src)
    hx = r["hx"]
    C = r["C"]
    if kind in ("small rune", "big rune"):
        # the caster: the Clapper whose cast (small runes: Spell Antic .. Cast 2; the big rune: the jump cast's antic)
        # came last within 5 s
        sts = ("Spell Antic", "Cast 1", "Cast 2") if kind == "small rune" else ("Cast Slam Antic", "Cast Slam Antic 2")
        last = {}
        for f in range(g - 300, g + 1):
            rr = fr.get(f)
            if rr is None:
                continue
            for i, c in rr["C"].items():
                if c[0] in sts:
                    last[i] = f
        cand = [i for i in last if i in C]
        if cand:
            return max(cand, key=lambda i: last[i])
        return min(C, key=lambda i: abs(C[i][2] - hx))
    else:
        fit = [i for i, c in C.items() if sp7_two._fits(src, c[0])]
        # the collider's own states first (Slam Collider 1: the hammer's swing, 2: the landing)
        own_st = (("Slam 0", "Slam 1", "Slam Effects?") if kind == "hammer" else ("Slam 2", "Land") if kind == "landing"
                  else ())
        fit = [i for i in fit if C[i][0] in own_st] or fit
    pool = fit or list(C)
    best = min(pool, key=lambda i: abs(C[i][2] - hx))
    if nm is not None and len(fit) == 1 and nm not in names:
        names[nm] = best
    return best


def _move_of(fr: dict, iid, g: int, back: int = 240) -> tuple[str | None, int | None]:
    """The attacker's latest move start (MOVE_START) at or before g, within `back` frames: (state, frame)."""
    prev = None
    found = (None, None)
    for f in range(g - back, g + 1):
        r = fr.get(f)
        if r is None or iid not in r["C"]:
            continue
        st = r["C"][iid][0]
        if st in MOVE_START and st != prev:
            found = (st, f)
        prev = st
    return found


def _wall_d(x: float) -> float:
    return min(x - sp.WALL_L, sp.WALL_R - x)


# ---- HP losses -----------------------------------------------------------------------------------------------------

def _hp_losses(ep: dict) -> list[dict]:
    fr, owner, dec = ep["fr"], ep["owner"], ep["dec"]
    starts = ep["starts"]
    out = []
    names: dict = {}
    prev_hit = None
    slam_runs = ep["slam_runs"]
    for g in sorted(fr):
        if g > ep["fk"]:
            break
        for amt, src in fr[g]["hp_ev"]:
            att = _attacker(fr, g, src, names)
            kind = _src_kind(src)
            r = fr[g]
            C = r["C"]
            ca = C.get(att)
            other = next((i for i in C if i != att), None)
            mv, fa = _move_of(fr, att, g) if att is not None else (None, None)
            if att is not None and kind in ("small rune", "big rune"):
                # a rune's move is its cast (the caster may have moved on since)
                want = "Spell Antic" if kind == "small rune" else "Cast Slam Antic"
                fr_c = [f for f in range(g - 420, g + 1) if f in fr and att in fr[f]["C"] and fr[f]["C"][att][0] == want
                        and (f - 1 not in fr or att not in fr[f - 1]["C"] or fr[f - 1]["C"][att][0] != want)]
                if fr_c:
                    mv, fa = want, fr_c[-1]
            x_rel = None if ca is None else round((r["hx"] - ca[2]) * ca[4], 2)
            win = [f for f in range(g - WIN_TRACE, g + 1) if f in fr]
            dwin = [f for f in range(g - WIN_DEC, g) if f in fr]
            owns = [owner.at(f) for f in dwin]
            own_set = Counter(o[0] for o in owns)
            own_g = owner.at(g)
            tgt_g = own_g[2]
            air_dec = sum(1 for f in dwin if not fr[f]["g"])
            land = any(any(fr[f]["clip"].startswith(c) for c in LAND_CLIPS) for f in dwin[-8:])
            hurt = any(any(fr[f]["clip"].startswith(c) for c in HURT_CLIPS) for f in dwin[-12:])
            late = max((fr[f]["late"] for f in dwin), default=0)
            gaps = sum(1 for a, b in zip(win, win[1:]) if b - a > 1)
            hitch = max((fr[f]["udt"] for f in dwin), default=0.0)
            # a press the plan needed and the cooldown dropped: a script's, or the planner's down slash
            pr = [p for p in ep["presses"] if g - 45 <= p["f"] <= g - 3 and not p["ok"] and p["acd"] > 1.0
                  and (p["own"].split(":")[0] in SCRIPT_OWN or p["down"])]
            dash_left = any(fr[f]["cd"] for f in dwin[-12:])
            # did she move into it: her own travel toward it >= 0.75 u over the window with keys toward it
            moved_in, toward_keys = False, 0
            if ca is not None and dwin:
                fa0 = next((f for f in dwin if att in fr[f]["C"]), None)
                if fa0 is not None:
                    # her own travel toward it (its own motion - a jump's flight, the slam's lunge - not counted)
                    sgn = 1.0 if fr[fa0]["C"][att][2] > fr[fa0]["hx"] else -1.0
                    travel = (fr[dwin[-1]]["hx"] - fr[fa0]["hx"]) * sgn
                    for f in dwin:
                        c_ = fr[f]["C"].get(att)
                        if c_ is None:
                            continue
                        look = L_BIT if c_[2] < fr[f]["hx"] else R_BIT
                        toward_keys += bool(fr[f]["m"] & look)
                    moved_in = travel >= 0.75 and toward_keys >= 4
            air_g = not fr[dwin[-1]]["g"] if dwin else not r["g"]
            # an escape key in the window: the dash ready on >= 6 frames; the umbrella; a dash she already used
            dash_any = sum(1 for f in dwin if fr[f]["cd"]) >= 6
            umb = sum(1 for f in dwin if fr[f]["clip"].startswith("Umbrella")) >= 6
            dashed = any("Dash" in fr[f]["clip"] or fr[f]["clip"].startswith("Sprint") for f in dwin)
            air_how = "umbrella" if umb else "after its dash" if dashed else "dash ready" if dash_any else "no dash"
            # a jump move from its wall (an escape jump: its back within 6.2 u of the wall at the antic entry)
            esc_jump = jump_d0 = None
            if mv in ("Jump Antic", "Cast Slam Antic") and fa is not None and fa in fr and att in fr[fa]["C"]:
                c0 = fr[fa]["C"][att]
                back = (c0[2] - sp.WALL_L) if c0[4] > 0 else (sp.WALL_R - c0[2])
                esc_jump = round(back, 2)
                jump_d0 = round(abs(fr[fa]["hx"] - c0[2]), 2)
            # the slam runs on the attacker's slam / the other's
            run_att = next((x for x in slam_runs if x[0] == att and fa is not None and abs(x[1] - fa) <= 3), None)
            # its slam not struck: the playbook declined / aborted before a press (she was in front within 8.3 u at the
            # antic entry: the playbook's case)
            slam_decl = None
            if kind in ("hammer", "landing") and mv == "Slam Antic" and fa is not None and fa in fr and                     att in fr[fa]["C"] and (run_att is None or run_att[6] is None):
                c0 = fr[fa]["C"][att]
                x0 = (fr[fa]["hx"] - c0[2]) * c0[4]
                if 0 < x0 <= CLOSE_U:
                    slam_decl = _slam_why(ep, att, fa, run_att)
            # the second hammer: its slam began while the playbook ran the other one's slam and got no strike run
            handoff = False
            if kind in ("hammer", "landing") and mv == "Slam Antic" and fa is not None:
                if ep["slam_runs_known"]:
                    busy = [x for x in slam_runs if x[0] != att and x[1] <= fa <= x[1] + (x[10] or 0) + 2]
                    handoff = bool(busy) and (run_att is None or run_att[4] is None)
                else:
                    o_fa = [owner.at(f)[0] for f in range(fa, fa + 6)]
                    struck_other = any(fa - 60 <= f_ <= fa + 5 and t_ != att and "Down" in s_
                                       for f_, t_, s_ in ep["landed"])
                    handoff = "slam" in o_fa and struck_other
            run_any = [x for x in slam_runs if x[1] <= g <= x[1] + 140]
            dec_row = None
            fl = [f for f in ep["dec_f"] if g - 6 <= f <= g]
            if fl:
                dec_row = dec[fl[-1]]
            forced = None if dec_row is None else bool(dec_row.get("forced"))
            plan = None if dec_row is None else dec_row.get("plan")
            after_prev = prev_hit is not None and g - prev_hit <= 150
            # classification (module docstring; the first rule that holds)
            cat, sub = None, ""
            n_scr = Counter({o: n for o, n in own_set.items() if o.split(":")[0] in SCRIPT_OWN})
            l2t = ("L2 on the other" if (tgt_g is not None and att is not None and tgt_g != att) else
                   "L2 on it" if tgt_g is not None else "L2 ?")
            if late >= 3 or gaps:
                cat, sub = HOST, f"keys {late} frames late" if late >= 3 else f"{gaps} STATE gaps"
            elif pr:
                cat, sub = CD, f"{pr[-1]['own']}'s {'down ' if pr[-1]['down'] else ''}press dropped by the cooldown"
            elif hurt:
                cat, sub = AIR, "hurt recoil / stun (the previous hit)"
            elif handoff:
                cat, sub = SCR, "the playbook still on the other's slam (hand-off)"
            elif slam_decl is not None and slam_decl[0] is not None:
                cat, sub = slam_decl[0], "slam not struck: " + slam_decl[1]
            elif n_scr and sum(n_scr.values()) >= 6:
                # a script held the keys in the decisive window
                main = n_scr.most_common(1)[0][0]
                subj = _script_subject(main, ep, g, att, own_g)
                if subj is not None and subj != att:
                    cat, sub = SCR, f"{main} on the other Clapper while this one hit"
                elif main == "slam" and run_att is not None and run_att[6] is not None and not run_att[7]:
                    cat, sub = (CD if _press_dropped(ep, run_att) else L2), "strike pressed, no bounce"
                elif moved_in:
                    cat, sub = L2, f"{main} moved her into it"
                elif air_dec >= 20 and not dash_any:
                    cat, sub = AIR, f"{main}: in the air ({air_how})"
                else:
                    cat, sub = L2, f"{main} stayed in its reach" + (" (in the air)" if air_dec >= 12 else "")
            elif moved_in:
                cat, sub = L2, f"planner moved into it ({'forced' if forced else 'not forced'}; {l2t})"
            elif land:
                cat, sub = AIR, "landing"
            elif air_dec >= 20 and not dash_any:
                cat, sub = AIR, f"planner: in the air ({air_how})"
            elif air_dec >= 12:
                cat, sub = L2, f"planner: in the air, dash ready ({'forced' if forced else 'not forced'}; {l2t})"
            else:
                cat, sub = L2, f"planner stayed in its reach ({'forced' if forced else 'not forced'}; {l2t})"
            if n_scr and cat in (L2, AIR) and own_g[0] == "plan" and sum(n_scr.values()) < 6:
                sub += f" (after {n_scr.most_common(1)[0][0]})"
            out.append({"f": g, "t": round((g - ep["f_wake"]) / 60.0, 2), "amount": amt, "src": kind, "src_full": src,
                        "by": att, "st": None if ca is None else ca[0], "move": mv,
                        "k_move": None if fa is None else g - fa,
                        "other_st": None if other is None else C[other][0],
                        "other_d": None if other is None else round(abs(C[other][2] - r["hx"]), 2),
                        "x": x_rel, "air": air_g, "jump_back": esc_jump,
                        "jump_d0": jump_d0,
                        "esc_jump": esc_jump is not None and esc_jump <= 6.2 and jump_d0 is not None and jump_d0 <= CLOSE_U, "clip": r["clip"], "air_dec": air_dec, "moved_in": moved_in,
                        "toward_keys": toward_keys,
                        "own": dict(own_set), "own_g": own_g[0], "tgt_is_att": tgt_g == att if tgt_g is not None else None,
                        "why": own_g[4], "forced": forced, "plan": plan, "late": late, "gaps": gaps,
                        "hitch_ms": round(hitch * 1e3, 1), "dash_left": dash_left, "dropped": [p["f"] - g for p in pr],
                        "slam_run": run_att, "slam_runs_near": [[x[0] == att, x[1] - g, x[2], x[3]] for x in run_any],
                        "after_prev": after_prev, "wall_her": round(_wall_d(r["hx"]), 2),
                        "wall_it": None if ca is None else round(_wall_d(ca[2]), 2), "alive": len(C),
                        "cat": cat, "sub": sub, "exact_own": owner.exact})
            prev_hit = g
    return out


def _script_subject(own: str, ep: dict, g: int, att, own_g: tuple):
    """The Clapper a script was acting on near frame g (None: unknown)."""
    if own == "slam":
        r = [x for x in ep["slam_runs"] if x[1] <= g <= x[1] + 150]
        return r[-1][0] if r else None
    if own in ("two:idle", "two:esc", "two:asw", "two:jh", "chase", "low"):
        # IdleHit / the chase / the low hop act on the focus (L2's target) or the caster in front; SP10c's jumphit on
        # the other one (L2's target)
        tgt = own_g[2]
        return tgt
    if own == "claw":
        # SP10c: the late Clawline acts on the jumper whose run is open near g
        r = [x for x in ((ep["pol"].get("claw_chase") or {}).get("claw_runs") or [])
             if int(x["f_a"]) <= g <= int(x["f_a"]) + int(x.get("f_end") or 150)]
        return r[-1]["J"] if r else None
    return None


def _press_dropped(ep: dict, run) -> bool:
    fa, kp = run[1], run[6]
    if kp is None:
        return False
    f = fa + kp - sp.SEND_AHEAD
    return any(not p["ok"] for p in ep["presses"] if abs(p["f"] - f) <= 3)


# ---- missed planned actions ----------------------------------------------------------------------------------------

SLAM_WHY = (
    ("other ", L2, "playbook gate: the other Clapper"),
    ("no input (sprint", AIR, "no input at the antic (sprint / recoil)"),
    ("behind", L2, "behind it at the antic"),
    ("distance", L2, "outside the reach band at the antic"),
    ("wall", L2, "the stand point at the wall"),
    ("no time to walk", L2, "too far to walk to the stand by the jump"),
    ("outside the band", L2, "outside the band at the jump"),
    ("in the air", AIR, "in the air at the antic"),
    ("no landing", AIR, "no landing in time"),
    ("no input in the air", AIR, "no input in the air"),
    ("not on the ground", AIR, "not on the ground at the jump"),
    ("hurt", AIR, "hurt in the slam (an HP loss)"),
    ("supervisor", SCR, "the supervisor took the keys"),
    ("asw", SCR, "the antic switch"),
    ("no bounce", L2, "pressed, no bounce"),
    ("late jump", L2, "the jump came late"),
)


def _slams(ep: dict) -> list[dict]:
    fr, owner = ep["fr"], ep["owner"]
    out = []
    prev = {}
    landed = ep["landed"]
    for f in sorted(fr):
        if f > ep["fk"]:
            break
        r = fr[f]
        for iid, c in r["C"].items():
            st = c[0]
            if st == "Slam Antic" and prev.get(iid) != "Slam Antic":
                fa = f - int(round(c[1] * 60.0))
                x = (r["hx"] - c[2]) * c[4]
                other = next((i for i in r["C"] if i != iid), None)
                o = r["C"].get(other) if other is not None else None
                struck = any(fa + 40 <= g <= fa + 62 and t == iid and "Down" in s for g, t, s in landed)
                run = next((x_ for x_ in ep["slam_runs"] if x_[0] == iid and abs(x_[1] - fa) <= 3), None)
                hp = [h for h in ep["hits"] if fa <= h["f"] <= fa + 170]
                # the other Clapper's slam running at this antic (a double slam)
                dbl = o is not None and o[0] in sp.SLAM_STATES
                out.append({"f": fa, "iid": iid, "x": round(x, 2), "front": x > 0, "close": 0 < x <= CLOSE_U,
                            "struck": struck, "run": run, "alive": len(r["C"]),
                            "other_st": None if o is None else o[0],
                            "other_d": None if o is None else round(abs(o[2] - r["hx"]), 2),
                            "double": dbl, "air0": not r["g"], "own0": owner.at(f)[0],
                            "hp": [[h["f"] - fa, h["src"], h["by"] == iid, h["cat"], h["sub"], h["air"]] for h in hp]})
            prev[iid] = st
    for s in out:
        # killed in its antic (her hits before Slam 0): nothing left to strike
        s["killed"] = any(f in fr and s["iid"] not in fr[f]["C"] for f in range(s["f"], s["f"] + 50))
        if s["struck"] or not s["close"] or s["killed"]:
            s["cat"], s["sub"] = None, ""
            continue
        s["cat"], s["sub"] = _slam_why(ep, s["iid"], s["f"], s["run"])
    return out


def _slam_why(ep: dict, iid, fa: int, run) -> tuple:
    """Why the playbook did not strike this slam (antic entry fa): (cause, sub-label)."""
    if run is None:
        if ep["slam_runs_known"]:
            busy = [x for x in ep["slam_runs"] if x[0] != iid and x[1] <= fa <= x[1] + (x[10] or 0) + 2]
            return (SCR, "no run: the playbook on the other Clapper's slam (hand-off)") if busy else (L2, "no run")
        return None, "unknown (no slam_runs before fadc77a)"
    phase, why = run[2], run[3] or ""
    if run[6] is not None and run[7]:
        return L2, "bounced on it, no down-slash hit recorded"
    if phase in ("abort", "wait") and why.startswith("late"):
        busy = [x for x in ep["slam_runs"] if x[0] != iid and x[1] < fa + (run[10] or 0) and x[1] + 140 > fa]
        return (SCR, "late: the playbook was on the other Clapper's slam (hand-off)") if busy else (
            L2, "late (no start condition met in time)")
    for key, cat, sub in SLAM_WHY:
        if key in why:
            return cat, sub + (f" ({why})" if key == "other " else "")
    if run[6] is not None and not run[7]:
        return (CD if _press_dropped(ep, run) else L2), "pressed, no bounce"
    return L2, f"{phase}: {why or 'no start'}"


IDLE_WHY = (("air", AIR, "she was in the air"), ("no input", AIR, "no input (recoil / sprint)"),
            ("far", L2, "too far to reach by frame 30"), ("cooldown", CD, "the attack cooling down"),
            ("other ", L2, "gate: the other Clapper can reach her"), ("rune circle", L2, "gate: a rune circle"),
            ("esc", SCR, "the escape / switch run's no-hit"), ("focus", L2, "L2 switched the focus"),
            ("hurt", AIR, "hurt"), ("gone", None, ""), ("one", None, ""))


def _idles(ep: dict) -> list[dict]:
    """F's Idle (re-)entries with her within 8.3 u while both live: hit within 30 frames, else why."""
    fr, owner = ep["fr"], ep["owner"]
    runs = {int(r[0]): r for r in ep["idle_runs"]}
    landed = ep["landed"]
    prev = {}
    out = []
    for f in sorted(fr):
        if f > ep["fk"]:
            break
        r = fr[f]
        if len(r["C"]) != 2:
            prev = {i: (c[0], c[1]) for i, c in r["C"].items()}
            continue
        tgt = owner.at(f + sp.SEND_AHEAD)[2]
        for iid, c in r["C"].items():
            p = prev.get(iid)
            entry = c[0] == "Idle" and (p is None or p[0] != "Idle" or c[1] + 0.5 / 60.0 < p[1])
            if not entry:
                continue
            focus = (tgt == iid) if tgt is not None else (iid == min(r["C"], key=lambda i: abs(r["C"][i][2] - r["hx"])))
            d = abs(r["hx"] - c[2])
            if not focus or d > CLOSE_U:
                continue
            hit = next((g - f for g, t, s in landed if t == iid and f <= g <= f + 30), None)
            run = runs.get(f)
            item = {"f": f, "iid": iid, "d0": round(d, 2), "re": p is not None and p[0] == "Idle", "hit_k": hit,
                    "g0": r["g"], "own0": owner.at(f + sp.SEND_AHEAD)[0], "run": run}
            if hit is not None:
                item["cat"], item["sub"] = None, ""
            elif run is None:
                o = item["own0"]
                item["cat"], item["sub"] = (SCR, f"no IdleHit run: {o} had the keys") if o not in ("plan", "sup") else (
                    L2, "no IdleHit run")
            else:
                why = str(run[6] or "")
                if run[3] is not None:
                    item["cat"], item["sub"] = L2, "pressed, no hit within 30 frames"
                else:
                    for key, cat, sub in IDLE_WHY:
                        if why.startswith(key):
                            item["cat"], item["sub"] = cat, sub + (f" ({why})" if key == "other " else "")
                            break
                    else:
                        item["cat"], item["sub"] = (SCR, f"run never stepped ({why})") if why in (
                            "left idle", "window", "re-entry") else (L2, why or "?")
            out.append(item)
        prev = {i: (c[0], c[1]) for i, c in r["C"].items()}
    return out


def _chases(ep: dict) -> list[dict]:
    out = []
    for r in ep["chase_runs"]:
        far = r.get("x_end") is not None and float(r["x_end"]) > 8.28
        why = f"{r.get('end')} {r.get('why')}"
        item = {"f": r.get("f0"), "x_end": r.get("x_end"), "ground0": r.get("ground0"), "air": r.get("air"),
                "dash_tries": r.get("dash_tries"), "end": why, "next": r.get("next"), "far": far}
        if not far:
            item["cat"], item["sub"] = None, ""
        elif "hurt" in why:
            item["cat"], item["sub"] = AIR, "hurt during the chase"
        elif "other" in why or "two" in why or "rune" in why:
            item["cat"], item["sub"] = SCR, f"cut ({why})"
        elif not r.get("ground0") and not r.get("dash_k"):
            item["cat"], item["sub"] = AIR, "started in the air without a dash"
        else:
            item["cat"], item["sub"] = L2, f"ended far ({why})"
        out.append(item)
    return out


def _run_ends(ep: dict) -> Counter:
    c = Counter()
    pol = ep["pol"]
    for x in ep["slam_runs"]:
        if x[2] == "abort":
            c[f"slam abort: {x[3]}"] += 1
    for r in (pol.get("evade_chase") or {}).get("chase_runs") or ():
        if r.get("end") == "abort":
            c[f"chase abort: {r.get('why')}"] += 1
    for r in (pol.get("rune_lowhop") or {}).get("hop_runs") or ():
        if r.get("end") == "abort":
            c[f"low hop abort: {r.get('why')}"] += 1
    for r in ((pol.get("two_play") or {}).get("esc") or {}).get("esc_runs") or ():
        c[f"esc {r.get('mode')}: {r.get('exit')}"] += 1
    for r in (pol.get("cast_stab") or {}).get("runs") or ():
        if r.get("end") == "abort":
            c[f"cast_stab abort: {r.get('why')}"] += 1
    return c


def _double_slams(ep: dict) -> list[dict]:
    """One Clapper's Slam Antic while the other one's slam runs (Slam Antic .. Slam Recover): the gap - A in Slam 2 / Slam
    Recover / Idle and B in Slam Antic (before its Slam 0) - her air frames there, the damage colliders enabled then, the
    HP lost from B's antic to its Slam Recover end and whether B's slam was struck."""
    out = []
    for s in ep["slams"]:
        if not s["double"] or s["alive"] != 2:
            continue
        fa = s["f"]
        b = s["iid"]
        fr = ep["fr"]
        a = next((i for i in (fr.get(fa) or {"C": {}})["C"] if i != b), None)
        gap = air = 0
        cols = Counter()
        top = defaultdict(float)
        f = fa
        while f in fr and b in fr[f]["C"] and fr[f]["C"][b][0] == "Slam Antic":
            r = fr[f]
            ca = r["C"].get(a)
            if ca is not None and ca[0] in ("Slam 2", "Slam Recover", "Idle", "Walk"):
                gap += 1
                air += not r["g"]
                for st, nm, ytop, x0, x1 in ep["cols_f"].get(f, ()):
                    cols[f"{st}: {nm}"] += 1
                    top[f"{st}: {nm}"] = max(top[f"{st}: {nm}"], ytop)
                    span = top.setdefault(f"{st}: {nm} x", [x0, x1])
                    span[0], span[1] = min(span[0], x0), max(span[1], x1)
            f += 1
        out.append({"f": fa, "x": s["x"], "struck": s["struck"], "gap_f": gap, "gap_air_f": air, "k_s0": f - fa,
                    "hp": list(s["hp"]), "hp_antic": [h for h in s["hp"] if h[0] < f - fa], "run": s["run"],
                    "cols": dict(cols), "top": dict(top), "own0": s["own0"]})
    return out


def episode(arm: str, inst: int, run: Path, row: dict, dec: dict) -> dict:
    from ssbot.record.recorder import RecordingReader
    f_wake, f_end = int(row["f_wake"]), int(row["f_end"])
    fk = row.get("f_kill") or f_end
    states = list(RecordingReader(row["recording"]).states(f_wake - 30, f_end))
    fr = _frames(states)
    pol = row.get("policy") or {}
    drows = dec.get(int(row["episode"]), {})
    owner = Owner(pol, drows)
    starts = _attack_starts(fr)
    landed = [(f, t, s) for f in sorted(fr) for t, s in fr[f]["hit_ev"]]
    ep = {"id": f"{run.name[:15]}{run.name[-2:] if run.name.endswith('_2') else ''}_i{inst}_e{row['episode']}",
          "arm": arm, "run": str(run), "inst": inst, "episode": row["episode"], "outcome": row.get("outcome"),
          "f_wake": f_wake, "f_end": f_end, "fk": fk, "fight_s": round((fk - f_wake) / 60.0, 2), "fr": fr,
          "owner": owner, "dec": drows, "dec_f": sorted(drows), "starts": starts, "pol": pol, "landed": landed,
          "slam_runs": pol.get("slam_runs") or [], "slam_runs_known": "slam_runs" in pol,
          "idle_runs": (pol.get("two_play") or {}).get("idle_runs_rec") or [],
          "chase_runs": (pol.get("evade_chase") or {}).get("chase_runs") or []}
    ep["presses"] = _presses(fr, starts, owner, f_wake, fk)
    # the damage colliders enabled on each Clapper per frame (only the frames of a slam antic: the double slam check)
    cols = defaultdict(list)
    for s in states:
        f = int(s["f"])
        for e in sp.clappers(s):
            if sp.control(e)[0] != "Slam Antic":
                continue
            for o in sp.clappers(s):
                if o["iid"] == e["iid"]:
                    continue
                for c in o.get("colliders") or ():
                    if c.get("damage") and c.get("enabled") and c.get("verts_world"):
                        xs, ys = c["verts_world"][0::2], c["verts_world"][1::2]
                        cx, fc = float(o["pos"][0]), tp.face_of(o)
                        a_, b_ = (min(xs) - cx) * fc, (max(xs) - cx) * fc
                        nm = c.get("name", "").replace("Song Heavy Sentry", "body").split(" (")[0]
                        cols[f].append((sp.control(o)[0], nm, round(max(ys) - FLOOR_Y, 2), round(min(a_, b_), 2),
                                        round(max(a_, b_), 2)))
    ep["cols_f"] = cols
    ep["hits"] = _hp_losses(ep)
    ep["slams"] = _slams(ep)
    ep["doubles"] = _double_slams(ep)
    ep["idles"] = _idles(ep)
    ep["chases"] = _chases(ep)
    ep["run_ends"] = _run_ends(ep)
    ep["one_phase_s"] = round(sum(1 for f in fr if f <= fk and len(fr[f]["C"]) == 1) / 60.0, 2)
    # who held the keys, by the number of live Clappers (a one-Clapper script acting with two, and the reverse)
    ep["own_frames"] = Counter(f"{len(fr[f]['C'])}: {owner.at(f)[0]}" for f in fr if f_wake <= f <= fk)
    return ep


# ---- traces --------------------------------------------------------------------------------------------------------

def trace(ep: dict, g: int, att, n: int = WIN_TRACE) -> str:
    """The frames g - n .. g: her x from the attacker (+ = in front of it), height, ground / air, clip, the attack
    cooldown, dash ready, the latched keys, who sent them, L2's target (A = the attacker, B = the other), the attacker's
    and the other one's states and the other's distance, late frames."""
    fr, owner = ep["fr"], ep["owner"]
    lines = []
    last = None
    for f in range(g - n, g + 1):
        r = fr.get(f)
        if r is None:
            lines.append(f"  {f - g:+4d}  (no STATE)")
            continue
        C = r["C"]
        ca = C.get(att)
        oth = next((i for i in C if i != att), None)
        co = C.get(oth)
        own = owner.at(f)
        tg = "A" if own[2] == att else ("B" if own[2] is not None and own[2] == oth else str(own[2])[-4:])
        x = "      " if ca is None else f"{(r['hx'] - ca[2]) * ca[4]:+6.2f}"
        st_a = "" if ca is None else ca[0][:13]
        st_b = "" if co is None else co[0][:13]
        d_b = "" if co is None else f"{abs(co[2] - r['hx']):5.1f}"
        crit = "!" + own[1] if own[1] else ""
        late = f" late{r['late']}" if r["late"] > 1 else ""
        hp = f" HP-{r['hp_ev'][0][0]}" if r["hp_ev"] else ""
        hit = " hit" if r["hit_ev"] else ""
        line = (f"{x} y{r['hy']:5.2f} {'g' if r['g'] else 'A'} {r['clip'][:14]:14s} cd{r['acd']:4.0f} "
                f"{'D' if r['cd'] else '-'} {_keys(r['m'])} {own[0]:9s}{crit} L2:{tg} | A {st_a:13s} | B {st_b:13s} "
                f"{d_b}{late}{hp}{hit}")
        key = line
        if key == last and f not in (g, g - n) and (f - g) % 6:
            continue
        last = key
        why = own[4] if own[4] else ""
        lines.append(f"  {f - g:+4d} {line}" + (f"  [{why}]" if (f - g) % 12 == 0 and why else ""))
    return "\n".join(lines)


# ---- summary -------------------------------------------------------------------------------------------------------

def summarize(E: list[dict]) -> dict:
    H = [h for e in E for h in e["hits"]]
    S = [s for e in E for s in e["slams"]]
    I = [x for e in E for x in e["idles"]]
    Ch = [x for e in E for x in e["chases"]]
    P = [p for e in E for p in e["presses"]]
    mins = sum(e["fight_s"] for e in E) / 60.0

    def tab(items):
        c = Counter((x["cat"], x["sub"]) for x in items if x.get("cat"))
        ex = defaultdict(list)
        for x in items:
            if x.get("cat") and len(ex[(x["cat"], x["sub"])]) < 3:
                ex[(x["cat"], x["sub"])].append(f"{x['ep']}@{x['f']}")
        return {"by_cat": dict(Counter(x["cat"] for x in items if x.get("cat"))),
                "top": [[k[0], k[1], n, ex[k]] for k, n in c.most_common(25)]}

    close = [s for s in S if s["close"]]
    drop = [p for p in P if not p["ok"]]
    out = {
        "episodes": len(E), "fight_min": round(mins, 2),
        "hp_losses": len(H), "hp_losses_per_min": round(len(H) / mins, 2) if mins else None,
        "hp_by_src": dict(Counter(h["src"] for h in H)),
        "hp": tab(H),
        "hp_by_alive": dict(Counter(h["alive"] for h in H)),
        "hp_by_move": dict(Counter(f"{h['move']}{' (escape jump)' if h['esc_jump'] else ''}" for h in H).most_common()),
        "hp_escape_jump": {"n": sum(1 for h in H if h["esc_jump"]),
                           "cat": dict(Counter(f"{h['cat']}: {h['sub']}" for h in H if h["esc_jump"]))},
        "hp_air": sum(1 for h in H if h["air"]), "hp_moved_in": sum(1 for h in H if h["moved_in"]),
        "hp_after_prev_150f": sum(1 for h in H if h["after_prev"]),
        "slams": len(S), "slams_close": len(close), "slams_close_struck": sum(1 for s in close if s["struck"]),
        "slams_close_killed_in_antic": sum(1 for s in close if s.get("killed") and not s["struck"]),
        "slams_missed": tab(close),
        "idle_entries": len(I), "idle_hit": sum(1 for x in I if x["hit_k"] is not None), "idles_missed": tab(I),
        "chases": len(Ch), "chases_far": sum(1 for x in Ch if x["far"]), "chases_missed": tab(Ch),
        "presses": len(P), "presses_dropped": len(drop),
        "presses_delayed": sum(1 for p in P if p.get("delayed")),
        "dropped_by_own": dict(Counter(p["own"] for p in drop)),
        "dropped_cooldown": sum(1 for p in drop if p["acd"] > 1.0),
        "dropped_clip": dict(Counter(p["clip"] for p in drop).most_common(8)),
        "run_ends": dict(sum((e["run_ends"] for e in E), Counter()).most_common(30)),
        "wall": {"her_within_3u": sum(1 for h in H if h["wall_her"] < 3.0),
                 "it_within_6u": sum(1 for h in H if h["wall_it"] is not None and h["wall_it"] < 6.0)},
        "own_frames_by_alive": dict(sum((e["own_frames"] for e in E), Counter()).most_common()),
        "hp_by_own_alive": dict(Counter(f"{h['alive']}: {h['own_g']}" for h in H).most_common()),
        "wall_cat": dict(Counter(f"{h['cat']}: {h['sub']}" for h in H
                                 if h["wall_her"] < 3.0 or (h["wall_it"] is not None and h["wall_it"] < 6.0))),
        "one_phase": {"s": round(sum(e["one_phase_s"] for e in E), 1),
                      "hp": sum(1 for h in H if h["alive"] == 1),
                      "hp_cat": dict(Counter(f"{h['cat']}: {h['sub']}" for h in H if h["alive"] == 1))},
    }
    D = [d for e in E for d in e["doubles"]]
    out["double_slams"] = {
        "n": len(D), "struck": sum(1 for d in D if d["struck"]),
        "gap_frames_p50": pct([d["gap_f"] for d in D], (50,)),
        "gap_air_share": round(sum(d["gap_air_f"] for d in D) / max(sum(d["gap_f"] for d in D), 1), 3),
        "hp": dict(Counter(f"{h[1]} ({'this' if h[2] else 'other'})" for d in D for h in d["hp"])),
        "hp_cat": dict(Counter(f"{h[3]}: {h[4]}" for d in D for h in d["hp"])),
        "gap_cols_frames": dict(sum((Counter(d["cols"]) for d in D), Counter()).most_common(10)),
        "gap_cols_top_above_floor_max": {k: max(d["top"].get(k, 0.0) for d in D if k in d["top"]) for k in
                                         set(k for d in D for k in d["top"] if not k.endswith(" x"))},
        "gap_cols_x_span_in_front": {k: [min(d["top"][k][0] for d in D if k in d["top"]),
                                         max(d["top"][k][1] for d in D if k in d["top"])]
                                     for k in set(k for d in D for k in d["top"] if k.endswith(" x"))},
        "hp_in_antic": [[h[1], h[2], h[5], h[3], h[4]] for d in D for h in d["hp_antic"]],
        "runs": dict(Counter("none" if d["run"] is None else f"{d['run'][2]}: {d['run'][3]}" for d in D).most_common(12)),
    }
    return out


def load(manifests: list[str], arms: set) -> dict:
    E = defaultdict(list)
    for arm, inst, run in manifest(manifests, arms):
        dec = sp7_two._decisions(run, inst)
        p = run / f"attempts_i{inst}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("outcome") == "HARNESS_FAIL" or not row.get("recording"):
                continue
            ep = episode(arm, inst, run, row, dec)
            for key in ("hits", "slams", "idles", "chases"):
                for x in ep[key]:
                    x["ep"] = ep["id"]
            E[arm].append(ep)
    return E


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--arms", default="")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--traces", type=Path, default=None, help="write one trace file per arm (every HP loss, 60 frames)")
    a = ap.parse_args(argv)
    arms = set(filter(None, a.arms.split(",")))
    E = load(a.manifest, arms)
    res = {}
    for arm, eps in E.items():
        res[arm] = summarize(eps)
        print(f"== {arm} ({len(eps)} episodes)")
        print(json.dumps(res[arm], indent=1, default=str))
        if a.traces:
            a.traces.mkdir(parents=True, exist_ok=True)
            with (a.traces / f"hp_{arm}.txt").open("w", encoding="utf-8") as fh:
                for ep in eps:
                    for h in ep["hits"]:
                        fh.write(f"### {ep['id']} f {h['f']} t {h['t']} {h['src']} by {h['st']} ({h['move']} +"
                                 f"{h['k_move']}) x {h['x']} other {h['other_st']} {h['other_d']} u | {h['cat']}: "
                                 f"{h['sub']} | own {h['own']} forced {h['forced']} plan {h['plan']} why {h['why']} "
                                 f"slam_run {h['slam_run']} near {h['slam_runs_near']}\n")
                        fh.write(trace(ep, h["f"], h["by"]) + "\n\n")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        slim = {arm: [{k: v for k, v in e.items() if k in ("id", "outcome", "fight_s", "hits", "slams", "idles",
                                                           "chases", "doubles", "one_phase_s")}
                      for e in eps] for arm, eps in E.items()}
        for arm in slim:
            for e, ep in zip(slim[arm], E[arm]):
                e["run_ends"] = dict(ep["run_ends"])
                e["presses_dropped"] = [p for p in ep["presses"] if not p["ok"]]
        a.json.write_text(json.dumps({"summary": res, "episodes": slim}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
