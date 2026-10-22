"""Map v2 L3: the COMBO LIBRARY (docs/plans/forum_map_v2.md section 1 L3 'STORAGE'; stage M3). Offline / planning code.

One JSON per combo under knowledge/1.0.30000/enemies/forum/combos/<NAME>.json:
  name, zh (an optional Chinese name), status (candidate / verified / promoted / demoted), evidence (where it was
  measured), source (the script it comes from),
  anchor     {"kind": "clapper_state" | "bomb_ring", "states": [...], "j": [lo, hi]} - the enemy event it is bound to
             (its frame in that state now, or a bomb ring's lit frame)
  pre        preconditions as ranges (u centre to centre, along the anchor's facing where it says so)
  steps      the macro in anchor-relative frames: [{"ref": "anchor" | "ctrl" | "start", "f": [lo, hi], "do": ...,
             "keys": ...}] - the timing windows the instantiation grids over ("grid" per step)
  branch_points  where the search re-plans after the macro (the Clawline's control, a contact, a landing)
  uncertain  mechanics it relies on that were not measured live (a forced trial first)
  impl       the instantiation function below (the step list is the documentation and the log format; the function
             turns its grid into concrete Plans: ssbot.map2.search.Plan with segments)
The search (search.Searcher.decide) evaluates every instantiated plan like a primitive one (the closed loop, the
reveal rule, the exit check) and expands it further when its strike lands (a macro is one segment, the search goes
on after it). The ACCEPTANCE RUN WITHOUT THE LIBRARY is the real test (1b.1): P1-P5 have no macro here at all.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import strike as sk

COMBO_DIR = cm.REPO / "knowledge" / "1.0.30000" / "enemies" / "forum" / "combos"
L, R, J, A, D, S = km.B_LEFT, km.B_RIGHT, km.B_JUMP, km.B_ATTACK, km.B_DOWN, km.B_DASH


@dataclass
class Combo:
    name: str
    d: dict
    impl: str

    @classmethod
    def load(cls, path: Path) -> "Combo":
        d = json.loads(Path(path).read_text("utf-8"))
        return cls(d["name"], d, d["impl"])

    def instantiate(self, W, sit, pred=None) -> list:
        fn = IMPLS.get(self.impl)
        if fn is None:
            return []
        out = []
        for plan in fn(W, sit, self.d, pred):
            plan.origin = self.name
            out.append(plan)
        return out


def load_library(names=None) -> list:
    out = []
    for p in sorted(COMBO_DIR.glob("*.json")):
        c = Combo.load(p)
        if names is None or c.name in names:
            out.append(c)
    return out


# ---- helpers -------------------------------------------------------------------------------------------------------

def _her(sit):
    S = sit.S
    return float(S[km.PX]), float(S[km.PY]) - sk.FOOT, bool(S[km.GROUND] > 0)


def _toward(hx: float, cx: float) -> int:
    return km.B_RIGHT if cx > hx else km.B_LEFT


def _plan(segs):
    from ssbot.map2.search import Plan
    return Plan(segs)


def _seg(masks, dsl=(), claw=None, tag=""):
    from ssbot.map2.search import Seg
    return Seg(np.asarray(masks, np.int64), list(dsl), claw, tag)


def _in(v, rng) -> bool:
    return rng[0] <= v <= rng[1]


# ---- CLAWSTRIKE (SP13): the hop + the Clawline at the slam antic; the strike is the search's from control --------

def impl_clawstrike(W, sit, d, pred):
    pre = d["pre"]
    hx, bb, ground = _her(sit)
    out = []
    for o in sit.obs:
        if o.st != "Slam Antic" or not _in(o.j or 0, d["anchor"]["j"]):
            continue
        dxc = (hx - o.x) * o.face                       # her centre in front of its centre (along its facing)
        if not _in(dxc, pre["front_u"]) or bb - sk.FLOOR > pre["bb_max"]:
            continue
        tw = _toward(hx, o.x)
        dirn = 1 if o.x > hx else -1
        hops = d["grid"]["hop"] if ground else [0]
        for hop in hops:
            for kp in d["grid"]["k_press"]:
                n = kp - int(o.j or 0)                  # the press frame from now
                if n < max(hop, 1):
                    continue
                m = [0] * n
                for i in range(hop):
                    m[i] = J
                m[-2 if n >= 2 else -1] |= tw           # the turn key toward it on the frame before and the press
                m[-1] |= tw
                out.append(_plan([_seg(m, (), (dirn, o.iid), f"CLAWSTRIKE hop{hop} k{kp}")]))
    return out


# ---- SLAMSTRIKE (SP1 playbook): walk to the stand band, jump straight up, down slash on Slam 0 ----------------------

def impl_slamstrike(W, sit, d, pred):
    hx, bb, ground = _her(sit)
    out = []
    if not ground:
        return out
    g = d["grid"]
    for o in sit.obs:
        if o.st != "Slam Antic" or not _in(o.j or 0, d["anchor"]["j"]):
            continue
        dxc = (hx - o.x) * o.face
        if not _in(dxc, d["pre"]["front_u"]):
            continue
        j0 = int(o.j or 0)
        for stand in g["stand"]:
            target = o.x + o.face * stand
            for kj in g["k_jump"]:
                for hold in g["hold"]:
                    for kpr in g["k_press"]:
                        n = kpr - j0 + 12
                        nj = kj - j0
                        npress = kpr - j0
                        if nj < 1 or npress <= nj:
                            continue
                        m = [0] * n
                        # walk (8.25 u/s) toward the stand point, then no key
                        steps = int(abs(target - hx) / (8.25 / 60.0))
                        key = _toward(hx, target)
                        for i in range(min(steps, nj - 1)):
                            m[i] = key
                        for i in range(nj - 1, min(nj - 1 + hold, n)):
                            m[i] |= J
                        for i in range(max(npress - 6, 0), min(npress + 2, n)):
                            m[i] |= D
                        m[npress - 1] |= A | D
                        out.append(_plan([_seg(m, [(npress - 1, o.iid)], None,
                                               f"SLAMSTRIKE s{stand} j{kj} h{hold} p{kpr}")]))
    return out


# ---- JUMPTRAP (SP14): the way under a jumping Clapper to behind its landing ---------------------------------------

def impl_jumptrap(W, sit, d, pred):
    hx, bb, ground = _her(sit)
    out = []
    if not ground:
        return out
    g = d["grid"]
    for o in sit.obs:
        if o.st not in d["anchor"]["states"]:
            continue
        # its landing from the aim (her x now, Jump Aim's target her x - 5 x facing; travel 0.916 x clamp 12)
        land = o.x + 0.916 * float(np.clip(hx - 5.0 * o.face - o.x, -12.0, 12.0))
        if o.st in ("Jump", "Air") and abs(o.vx) > 0:
            land = o.x + o.vx * 0.9
        dirn = 1 if land > hx else -1
        if abs(land - hx) > d["pre"]["max_u"]:
            continue
        for behind in g["behind_u"]:
            target = land + dirn * behind
            if not (cm.WALL_L + 0.6 < target < cm.WALL_R - 0.6):
                continue
            for dash_f in g["dash_f"]:
                n = int(abs(target - hx) / (8.25 / 60.0)) + 2
                n = min(n, 90)
                key = R if dirn > 0 else L
                m = [key] * n
                if dash_f >= 0 and dash_f < n:
                    m[dash_f] |= S
                    n2 = max(n - 18, dash_f + 10)
                    m = m[:n2]
                out.append(_plan([_seg(m + [0] * 6, (), None, f"JUMPTRAP b{behind} dash{dash_f}")]))
    return out


# ---- LOWHOP (SP13b BOMBS2): the low hop over a lit small-rune row ------------------------------------------------

def impl_lowhop(W, sit, d, pred):
    hx, bb, ground = _her(sit)
    out = []
    if not ground or pred is None:
        return out
    g = d["grid"]
    # the first frame a bomb at her x is lit (any branch)
    lit = None
    for k in range(1, min(pred.T, 120)):
        for b in pred.branches:
            for s in b.damage(k):
                if s.name == "bomb" and s.circle is not None and abs(s.circle[0] - hx) < s.circle[2] + 0.6:
                    lit = k
                    break
            if lit is not None:
                break
        if lit is not None:
            break
    if lit is None:
        return out
    for lead in g["lead"]:
        for hold in g["hold"]:
            f = lit - lead
            if f < 1:
                continue
            m = [0] * (f + 40)
            for i in range(f - 1, f - 1 + hold):
                m[i] = J
            out.append(_plan([_seg(m, (), None, f"LOWHOP lead{lead} h{hold}")]))
    return out


IMPLS = {"clawstrike": impl_clawstrike, "slamstrike": impl_slamstrike, "jumptrap": impl_jumptrap,
         "lowhop": impl_lowhop}

__all__ = ["Combo", "load_library", "COMBO_DIR", "IMPLS"]
