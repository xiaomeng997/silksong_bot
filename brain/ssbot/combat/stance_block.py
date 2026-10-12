"""Blocked hits on a guard stance (task 1v1 T2, the Reed 1v1; C:/ssbot/data/m2_dash_slash/defenders): the frames on
which a nail hit on an enemy would be blocked (a tink) and start its counter, from the FSM (Song_Reed.txt, Control)
and the logged dwells (knowledge Reed.json dwell_s):

  Reed  Alert: Will Defend = RandomBool at the entry; every frame, Will Defend and the hero inside Defend Range (an
        AlertRange circle, radius 0.5 x 15.299 = 7.65 u around the transform) and not Just Did Defend -> DEFEND ->
        Defend Start (not invincible, 0.067-0.100 s) -> Defend (SetInvincible, InvincibleFromDirection 0: every side
        and height; Wait 1.0 s, 1.000-1.017 s) -> Defend End (0.233-0.258 s, vulnerable) -> Alert. Defend's BLOCKED
        HIT -> Block (0.48-0.52 s) -> Parry Y Aim -> Parry Slash (-22 u/s by scale, 0.75 s; it aims at the hero's
        height): the counter's first damage 0.483-0.508 s after the tink, its reach x -11.2 .. +11.3 u. Just Did
        Defend is set at Defend Start and cleared at Stab Antic / Throw Antic (from the tracker's last_entry).

blocked(fc, tr, t) -> [T] bool: the game times t (absolute) at which a hit on tracker tr would be blocked:
  Defend        from now to its entry + DEF_S + slack
  Defend Start  from its entry + DS_MIN_S to its entry + DS_MAX_S + DEF_S + slack
  Alert         when it may still defend (not Just Did Defend, and not seen with the hero well inside Defend Range on
                ALERT_SEEN_N frames of this Alert without defending: then Will Defend is false): from now + DS_MIN_S on
  other states  when the walk reaches Defend Start within the times asked and Just Did Defend is clear: from its
                earliest entry + DS_MIN_S on
None for every other type. The planner (forum_planner, SSBOT_FORUM_STANCE) puts a second hit target on such frames:
it scores no landed hit and its hit branch is unsafe (the counter runs 1.25 s past the tink, beyond the 0.6 s horizon:
the tink / counter branch cannot be shown safe, the person's rule for a locked move: both outcomes safe).
"""
from __future__ import annotations

import math
import os

import numpy as np

STANCE_ON = os.environ.get("SSBOT_FORUM_STANCE", "1").strip() != "0"

REED = "Song Reed"
FT = 1.0 / 60.0
DS_MIN_S = 0.05               # Defend Start's shortest dwell 0.0667 s less one frame
DS_MAX_S = 0.1
DEF_S = 1.0167                # Defend's longest dwell
SLACK_S = 2 * FT
COUNTER_F = 29                # the counter's first damage after the tink: 0.483 s (ParrySlash Hit, p0.5 of 935)
DEFEND_R = 0.5 * 15.299       # Defend Range: the AlertRange circle's radius (u)
ALERT_IN_U = 0.4              # the hero's box nearer than DEFEND_R - this: surely inside the circle
HERO_HW, HERO_HH = 0.25, 1.04
ALERT_SEEN_N = 3              # frames of one Alert seen with the hero surely inside and no Defend Start


class StanceMemory:
    """Per enemy: the Alert instance (its entry time) and on how many distinct frames of it the hero was surely
    inside Defend Range. Kept on the MultiForecaster (one per fight)."""

    def __init__(self):
        self.alert: dict = {}         # iid -> (t_entry, frames seen inside, last T counted)

    def see(self, tr, T: float, hero_box) -> int:
        """Count frame T for tracker tr (idempotent per T); the count for its current Alert."""
        if tr.state != "Alert" or tr.t_entry is None or tr.pos is None:
            self.alert.pop(tr.iid, None)
            return 0
        t0, n, last = self.alert.get(tr.iid, (tr.t_entry, 0, -math.inf))
        if t0 != tr.t_entry:
            t0, n, last = tr.t_entry, 0, -math.inf
        if hero_box is not None and T > last + 1e-6:
            x0, y0, x1, y1 = hero_box
            px, py = tr.pos
            dx = max(x0 - px, 0.0, px - x1)
            dy = max(y0 - py, 0.0, py - y1)
            if math.hypot(dx, dy) < DEFEND_R - ALERT_IN_U:
                n += 1
            last = T
        self.alert[tr.iid] = (t0, n, last)
        return n

    def count(self, tr) -> int:
        """Frames of tr's current Alert seen with the hero surely inside Defend Range."""
        a = self.alert.get(tr.iid)
        return a[1] if a is not None and tr.state == "Alert" and a[0] == tr.t_entry else 0


def observe(fc, T: float, ws) -> None:
    """Per frame (MultiForecaster.update): count the frame for every Reed in Alert."""
    if not STANCE_ON:
        return
    hb = None
    try:
        hx, hy = (float(v) for v in ws.hero.pos.v)      # the hurtbox centre; the Bounds box 0.5 x 2.079 around it
        if math.isfinite(hx) and math.isfinite(hy):
            hb = (hx - HERO_HW, hy - HERO_HH, hx + HERO_HW, hy + HERO_HH)
    except (AttributeError, TypeError, ValueError):
        pass
    mem = getattr(fc, "_stance_mem", None)
    for tr in fc.trackers.values():
        if tr.tk != REED or tr.dead:
            continue
        if mem is None:
            mem = fc._stance_mem = StanceMemory()
        mem.see(tr, T, hb)


def just_did_defend(tr) -> bool:
    le = tr.last_entry or {}
    d = le.get("Defend Start", -math.inf)
    return d > max(le.get("Stab Antic", -math.inf), le.get("Throw Antic", -math.inf))


def blocked(fc, tr, t: np.ndarray) -> np.ndarray | None:
    """[len(t)] bool: a hit at game time t[i] on tracker tr may be blocked (see the module doc); None: never."""
    if not STANCE_ON or tr.tk != REED or tr.dead or tr.state is None or tr.t_entry is None:
        return None
    T = float(fc.t)
    st, te = tr.state, float(tr.t_entry)
    if st == "Defend":
        return t <= te + DEF_S + SLACK_S
    if st == "Defend Start":
        return (t >= te + DS_MIN_S) & (t <= te + DS_MAX_S + DEF_S + SLACK_S)
    if just_did_defend(tr):
        return None
    if st == "Alert":
        mem = getattr(fc, "_stance_mem", None)
        n = mem.count(tr) if mem is not None else 0
        if n >= ALERT_SEEN_N:
            return None                       # in range on 3+ frames of this Alert without defending: Will Defend 0
        return t >= T + DS_MIN_S
    try:
        from ssbot.combat.multi_forecast import DWELL_SLACK_S
        tt = tr.table
        dw = tt.dwell.get(st)
        age = T - te
        overdue = dw is not None and age > dw[1] + DWELL_SLACK_S
        ref = T if overdue else te
        cur = tr.cur
        ctx = (cur.family, cur.start) if cur is not None else None
        lo = fc.walks.states(tt, st, ctx, tr.dead, overdue).get("Defend Start")
    except Exception:  # noqa: BLE001  (no walk: assume it can defend from the next Alert on, now)
        lo, ref = 0.0, T
    if lo is None:
        return None
    return t >= ref + lo + DS_MIN_S
