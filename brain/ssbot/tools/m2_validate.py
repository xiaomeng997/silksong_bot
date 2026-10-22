"""Map v2 stage M2: the Clapper model's validation on the recorded episodes (docs/plans/forum_map_v2.md section 1 L1
"Validation"; forum.md section 93). Offline only.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m2_validate run --set held [--jobs 6] [--limit N]
        [--every 60] [--ks 0,6,12,36,60] [--out C:/ssbot/data/m2_play/map2/m2/val_held.json]

Per episode (an m2_clapper trace) in GAME frames (a hit-stop freeze is not a frame):
  rules     at every recorded decision of every Clapper, the model's rule against what happened: the V4 choices
            (Close / Close after an evade / Far / Escape: the probability the replayed counters gave the actual move,
            p = 0 = a rule violation), Close vs Far at Dmg Attack / After Scuttle (her physics box in Slam Range at
            that frame), the Idle exits (Walk at Idle Time, Evade at Can Evade, Dmg Attack in the hit frame), Walk's
            Close at Attack Ready, Avoid Type, the escape ray, the buddy lock (CANCEL), the facing at each move start
            (FaceObjectV2 with its 0.5 s pause), a jump's landing x and flight frames (Jump Aim from her x, the roof's
            push) and the evade's slide.
  horizons  predict() from sampled start frames g0 (every --every frames, and k frames before every true damage
            contact for k in --ks) with her ACTUAL path and hits (the closed loop); the REALIZED branch is the
            particle whose choices match what happened (the V4 moves in order, Will Evade where it showed, Walk's
            Far bin where it fired):
            - timing: every state entry in the horizon against the realized particle's entry (frames off, inside its
              offset range [a, b] or not), by move and state;
            - contacts: every true damage contact (oracle damage / damage_blocked from a Clapper collider) at its
              frame: her HeroBox meets the predicted damage shapes of the realized particle / of every branch (frames
              g - 2 .. g: the trigger's lag), per k and source;
            - area: at frames k of the sampled starts, the actual damage colliders' area covered by the realized
              particle's damage shapes, and the predicted / actual area ratio, by the actual state.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.map2 import clapper as cm
from ssbot.tools.m2_clapper import DATA, game_clock, idle_priority, load_set

CL = cm
MOVE_OF = {"Slam Antic": "slam", "Slam 0": "slam", "Slam 1": "slam", "Slam 2": "slam", "Slam Recover": "slam",
           "Spell Antic": "cast", "Cast 1": "cast", "Cast 2": "cast", "Jump Antic": "jump", "Jump": "jump",
           "Air": "jump", "Cast Slam Antic": "jcast", "Cast Slam Antic 2": "jcast", "Evade Scuttle": "evade",
           "Idle": "idle", "Walk": "walk", "Drop In": "intro", "Enter Land": "intro", "Roar": "intro",
           "Roar End": "intro", "Drop Antic": "intro"}
V4_KINDS = ("close", "close_ev", "far", "escape")


def pct(v, qs=(5, 50, 95)):
    v = [x for x in v if x is not None and np.isfinite(x)]
    return [round(float(np.percentile(v, q)), 3) for q in qs] if v else None


class Episode:
    """One trace in game frames: g(i) = the game frame of recorded index i; per game frame the last recorded index
    (a freeze's frames collapse); her path; each Clapper's states / positions; the transitions, hits and contacts in
    game frames; the decision log replayed with the model's Memory."""

    def __init__(self, tr: dict):
        self.tr = tr
        F = tr["F"]
        self.F = F
        G = game_clock(tr)
        gi = np.floor(G - G[0] + 0.5).astype(np.int64)
        self.gi = gi
        n_g = int(gi[-1]) + 1
        g2i = np.full(n_g, -1, np.int64)
        for i, g in enumerate(gi):
            g2i[g] = i
        for g in range(n_g):                     # a game frame no recorded frame landed on: the previous one
            if g2i[g] < 0:
                g2i[g] = g2i[g - 1] if g else 0
        self.g2i = g2i
        self.n_g = n_g
        self.fi = {int(f): i for i, f in enumerate(F)}
        H = tr["hero"]
        self.hx, self.hy, self.hbox = H["pos"][g2i, 0], H["pos"][g2i, 1], H["box"][g2i]
        # physics steps per game frame (the recorded frames that collapse into it)
        st = np.zeros(n_g, np.int64)
        np.add.at(st, gi, H["fs"].astype(np.int64))
        self.steps = np.minimum(st, 2)
        self.g_of = lambda f: int(gi[self.fi[f]]) if f in self.fi else None
        self.hits = defaultdict(dict)
        for f, iid, src, att, dealt, dead in tr["hits"]:
            g = self.g_of(f)
            if g is None:
                continue
            kind = "down" if "Down" in str(src) else "side" if att == "Nail" else "other"
            prev = self.hits[iid].get(g)
            d = int(dealt or 0)
            self.hits[iid][g] = (kind if prev is None or prev[0] == "other" else prev[0], d + (prev[1] if prev else 0))
        self.trans = defaultdict(list)           # iid -> [(g, from, to, f)]
        for f, iid, a, b, tp in tr["trans"]:
            g = self.g_of(f)
            if g is not None:
                self.trans[iid].append((g, a, b, f))
        self.cl = tr["cl"]
        self.iids = [iid for iid in self.cl if len(self.trans.get(iid, ())) > 3]
        name_iid = {c.get("name"): iid for iid, c in self.cl.items() if c.get("name")}
        name_iid.update(tr.get("obj_iid") or {})
        self.contacts = []                       # (g, iid, source kind, "damage" / "blocked")
        for f, kind, src, f0, f1 in tr["dmg"]:
            owner = src.split("/")[0]
            iid = name_iid.get(owner)
            sk = "hammer1" if "Slam Collider 1" in src else "hammer2" if "Slam Collider 2" in src else \
                "bomb" if "rune bomb" in src else "rune" if "rune slam" in src else \
                "body" if owner.startswith(cm_name()) else None
            if sk is None:
                continue
            if iid is None and sk not in ("bomb", "rune"):
                continue                         # a collider whose owner the trace does not name
            for ff in ((f,) if kind == "damage" else range(f0, f1 + 1)):
                g = self.g_of(ff)
                if g is not None:
                    self.contacts.append((g, iid if iid is not None else 0, sk, kind))
        self.contacts = sorted(set(self.contacts))

    # ---- per game frame views ----
    def st(self, iid, g):
        return self.cl[iid]["st"][self.g2i[min(max(g, 0), self.n_g - 1)]]

    def hero_path(self, g0: int, T: int, iids) -> cm.HeroPath:
        idx = np.clip(np.arange(g0, g0 + T + 1), 0, self.n_g - 1)
        hits = {iid: {g - g0: v for g, v in self.hits.get(iid, {}).items() if g0 < g <= g0 + T} for iid in iids}
        return cm.HeroPath(self.hx[idx], self.hy[idx], self.hbox[idx], hits, self.steps[idx])

    def obs(self, iid, g0: int, mem: cm.Memory) -> cm.Obs | None:
        c = self.cl[iid]
        i = self.g2i[g0]
        st = c["st"][i]
        if st is None or c["hp"][i] <= 0 or c["dead"][i]:
            return None
        # frames in the state (game frames since the entry)
        ent = None
        for g, a, b, f in reversed(self.trans[iid]):
            if g <= g0 and b == st:
                ent = g
                break
        j = (g0 - ent) if ent is not None else int(round(float(c["t"][i]) * 60))
        # facing: game frames since its last change
        face = c["face"]
        k = i
        while k > 0 and face[k - 1] == face[i]:
            k -= 1
        turn_age = int(self.gi[i] - self.gi[k]) if k > 0 else 10 ** 6
        will = None
        if st == "Idle" and ent is not None:
            for g in range(ent + cm.EV_K[2], g0 + 1):
                if self._in_range(iid, g):
                    will = False
                    break
        idle_buddy = None
        if st == "Idle" and ent is not None:
            others = [o for o in self.iids if o != iid]
            ie = self.g2i[ent]
            idle_buddy = any(self.cl[o]["st"][ie] not in (None,) + cm.DEAD and self.cl[o]["hp"][ie] > 0
                             for o in others)
        prev = None
        L = self.trans[iid]
        persist = [x for x in L if x[0] <= g0 and x[2] not in cm.INSTANT]
        if len(persist) >= 2:
            prev = persist[-2][2]
        cast2, rune = self.seeds(iid, g0)
        return cm.Obs(iid, st, float(c["t"][i]), float(c["pos"][i, 0]), float(c["pos"][i, 1]), float(c["vel"][i, 0]),
                      float(c["vel"][i, 1]), int(face[i]), int(c["hp"][i]), c["clip"][i], will, turn_age,
                      bool(mem.charged), j, prev=prev, cast2=cast2, rune=rune, idle_buddy=idle_buddy)

    def seeds(self, iid, g0: int) -> tuple:
        """(cast2, rune): its last Cast 2 entry within 150 frames (k <= 0, x, y) and its last charged landing within
        100 frames (k <= 0, x, facing) - the hazards still to light."""
        c = self.cl[iid]
        L = self.trans[iid]
        cast2 = rune = None
        for n, (g, a, b, f) in enumerate(L):
            if g > g0:
                break
            if b == "Cast 2" and g0 - g <= 150:
                ii = self.fi[f]
                cast2 = (g - g0, float(c["pos"][ii, 0]), float(c["pos"][ii, 1]))
            if b == "Charged?" and g0 - g <= 100:
                back = [x[2] for x in L[max(0, n - 8):n]]
                if "Cast Slam Antic" in back and back.index("Cast Slam Antic") > max(
                        [k for k, v in enumerate(back) if v == "Jump Antic"], default=-1):
                    ii = self.fi[f]
                    rune = (g - g0, float(c["pos"][ii, 0]), int(c["face"][ii]))
        return cast2, rune

    def ghost_hazards(self, g0: int, live: set, K) -> list:
        """The hazards still to light of the Clappers not in the prediction (killed after their cast)."""
        out = []
        for iid in self.iids:
            if iid in live:
                continue
            cast2, rune = self.seeds(iid, g0)
            if cast2 is not None:
                out += [(iid, h) for h in cm.bomb_hazards(K, cast2[0], cast2[1], cast2[2])]
            if rune is not None:
                out += [(iid, h) for h in cm.rune_hazards(K, rune[0], rune[1], rune[2])]
        return out

    def _in_range(self, iid, g: int) -> bool:
        c = self.cl[iid]
        i = self.g2i[g]
        hx, ry0, ry1 = cm.SLAM_RANGE
        m = cm.RANGE_SKIN
        b = self.tr["hero"]["box"][i]
        x, y = c["pos"][i]
        return bool(b[0] < x + hx + m and b[2] > x - hx - m and b[1] < y + ry1 + m and b[3] > y + ry0 - m)


def cm_name() -> str:
    return "Song Heavy Sentry"


# ---- the decision log of what happened (replayed with the model's memory) ----

def actual_decisions(E: Episode) -> dict:
    """iid -> [dict(g, kind, outcome, ...)] of every decision that happened, with the replayed Memory's view."""
    out = {}
    for iid in E.iids:
        mem = cm.Memory()
        L = E.trans[iid]
        dec = []
        idle_ent = None
        walk_ent = None
        for n, (g, a, b, f) in enumerate(L):
            i = E.fi.get(f)
            clip_before = E.cl[iid]["clip"][i - 1] if i else None
            src = mem.source(a, b, clip_before)
            if src is not None:
                ev = cm.STATE_EV[b]
                p = {e: q for q, e in mem.v4[src].dist()}.get(ev, 0.0)
                dec.append({"g": g, "kind": src, "out": ev, "p": p, "dist": mem.v4[src].dist()})
            elif a == "Close Range" and b == "Slam Antic":
                dec.append({"g": g, "kind": "walkb", "out": "SLAM", "p": 1.0})
            if b == "Idle":
                idle_ent = g
            if a == "Idle" and idle_ent is not None and b in ("Evade Scuttle", "Walk", "Dmg Attack"):
                seen_in = None
                for gg in range(idle_ent + cm.EV_K[2], g + 1):
                    if E._in_range(iid, gg):
                        seen_in = gg
                        break
                if b == "Evade Scuttle":
                    dec.append({"g": g, "kind": "will_evade", "out": True, "j": g - idle_ent})
                elif seen_in is not None and seen_in < g:
                    dec.append({"g": g, "kind": "will_evade", "out": False, "j": g - idle_ent})
                else:
                    dec.append({"g": g, "kind": "will_evade", "out": None, "j": g - idle_ent})
            if b == "Walk":
                walk_ent = g
            if a == "Walk" and walk_ent is not None:
                dec.append({"g": g, "kind": "walk_far", "out": (g - walk_ent) if b == "Far Range" else None})
            mem.observe(a, b, clip_before)
        out[iid] = dec
    return out


def consistent(logs: list, acts: list, T: int) -> bool:
    """The particle's choices (its log) against what happened in its horizon (acts, k relative to the start)."""
    pv = [c for c in logs if c[0] in V4_KINDS]
    av = [d for d in acts if d["kind"] in V4_KINDS]
    n = min(len(pv), len(av))
    for c, d in zip(pv[:n], av[:n]):
        if c[1] != d["out"]:
            return False
    # an extra / missing move choice only near the horizon's end
    if len(pv) > n and any(c[2] < T - 4 for c in pv[n:]):
        return False
    if len(av) > n and any(d["k"] < T - 4 for d in av[n:]):
        return False
    pe = [c for c in logs if c[0] == "will_evade"]
    ae = [d for d in acts if d["kind"] == "will_evade" and d["out"] is not None]
    for c, d in zip(pe, ae):
        if c[1] != d["out"]:
            return False
    for d in acts:
        if d["kind"] != "walk_far" or d["out"] is None:
            continue
        cand = [c for c in logs if c[0] == "walk_far" and d["k"] - 125 < c[2] <= d["k"]]
        if not cand or cand[-1][1] is None or abs(cand[-1][1] - d["out"]) > 8:
            return False
    return True


# ---- geometry ----

def actual_damage(E: Episode, g: int, iid) -> list:
    """The actual damage shapes of Clapper iid at game frame g: (kind, shapely-free geometry) as cm.Shape."""
    c = E.cl[iid]
    i = E.g2i[g]
    out = []
    if c["body_on"][i] and np.isfinite(c["body"][i, 0]):
        b = c["body"][i]
        out.append(cm.Shape(cm.DAMAGE, iid, "body", box=(b[0], b[1], b[2], b[3])))
    for nm, key in (("Slam Collider 1", "sc1"), ("Slam Collider 2", "sc2")):
        v = c[key].get(i)
        if v is not None:
            out.append(cm.Shape(cm.DAMAGE, iid, nm, poly=np.asarray(v, float)))
    return out


def actual_hazards(E: Episode, g: int) -> list:
    """The lit bombs / big runes at game frame g that can reach the arena (a bomb beyond a wall cannot)."""
    i = E.g2i[g]
    out = []
    for (bid, x, y, r, lit) in E.tr["bombs"][i]:
        if lit and cm.WALL_L - r < x < cm.WALL_R + r:
            out.append(cm.Shape(cm.DAMAGE, 0, "bomb", circle=(x, y, r)))
    for (bid, x, y, r, lit) in E.tr["runes"][i]:
        if lit:
            out.append(cm.Shape(cm.DAMAGE, 0, "rune", circle=(x, y, r)))
    return out


def _sgeom(s: cm.Shape):
    from shapely.geometry import Point, Polygon, box as sbox
    if s.box is not None:
        return sbox(*s.box)
    if s.circle is not None:
        cx, cy, r = s.circle
        return Point(cx, cy).buffer(r, 32)
    return Polygon(s.poly).convex_hull


MARGINS = (0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)     # the growth grid (u) of the margin tables


def area_cover(actual: list, pred: list) -> tuple[float, list, float]:
    """(actual area, [the part of it inside pred grown by m, for m in MARGINS], pred area)."""
    from shapely.ops import unary_union
    if not actual:
        return 0.0, [0.0] * len(MARGINS), 0.0
    A = unary_union([_sgeom(s) for s in actual])
    a = A.area
    if not pred:
        return a, [0.0] * len(MARGINS), 0.0
    P = unary_union([_sgeom(s) for s in pred])
    cov = []
    for m in MARGINS:
        Pm = P if m <= 0 else P.buffer(m, join_style=2, mitre_limit=2.0)
        cov.append(round(A.intersection(Pm).area, 4))
    return a, cov, P.area


def her_box(E: Episode, g: int) -> tuple:
    i = E.g2i[g]
    x, y = E.tr["hero"]["pos"][i]
    return cm.hurtbox(float(x), float(y))


# ---- one episode ----

def run_episode(tr: dict, K: cm.Know, ks: tuple, every: int, T_area: int = 60) -> dict:
    E = Episode(tr)
    R = defaultdict(list)
    acts = actual_decisions(E)
    unit = "w13" if "w13" in str(tr.get("unit")) else "w7"
    # ---- rules at the decisions (k = 0) ----
    for iid, dec in acts.items():
        for d in dec:
            if d["kind"] in V4_KINDS:
                R["v4"].append((d["kind"], d["out"], d["p"], max(p for p, _ in d["dist"]), len(d["dist"])))
    for iid in E.iids:
        L = E.trans[iid]
        c = E.cl[iid]
        ent = {}
        for n, (g, a, b, f) in enumerate(L):
            i = E.fi.get(f)
            if i is None:
                continue
            if a in ("Dmg Attack", "After Scuttle") and b in ("Close Range", "Far Range"):
                inr = E._in_range(iid, g) or (a == "Dmg Attack" and g > 0 and E._in_range(iid, g - 1))
                pred = "Close Range" if inr else "Far Range"
                R["range"].append((a, b, pred == b))
            if a == "Close Range" or a == "Far Range":
                o = [o for o in E.iids if o != iid]
                if o:
                    o = o[0]
                    j = E.g2i[g - 1] if g > 0 else 0
                    oat = E.cl[o]["st"][j] in cm.ATTACKING or (E.cl[o]["st"][j] is None and False)
                    R["cancel"].append((a, b == "Idle", bool(oat)))
            if b in ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic", "Evade Scuttle") and i > 0:
                hx = E.tr["hero"]["pos"][i, 0]
                side = 1 if hx > c["pos"][i, 0] else -1
                # the last facing change before this frame
                k = i - 1
                while k > 0 and c["face"][k - 1] == c["face"][i - 1]:
                    k -= 1
                age = int(E.gi[i] - E.gi[k]) if k > 0 else 10 ** 6
                pred = side                     # a move's start state turns at once (its own FaceObjectV2)
                R["face"].append((b, int(c["face"][i]) == pred, int(c["face"][i]) == side, age))
            if a == "Evade Scuttle" or (b == "Evade Scuttle" and n + 1 < len(L)):
                pass
            if b == "Evade Scuttle" and i > 0 and n + 1 < len(L):
                x, fc = c["pos"][i - 1, 0], c["face"][i - 1]
                back = (x - cm.WALL_L) if fc > 0 else (cm.WALL_R - x)
                nxt = L[n + 1][2]
                R["escape"].append((round(float(back), 2), nxt == "Escape Jump" or nxt in ("Jump Antic", "Cast Slam Antic"),
                                    back < cm.ESCAPE_RAY))
            if a == "Idle" and b == "Walk":
                R["idle_walk"].append((unit, g - ent.get("Idle", g)))
            if a == "Idle" and b == "Avoid Type":
                pass
            ent[b] = g
    # ---- predictions ----
    starts = set()
    if every:
        for g in range(30, E.n_g - 5, every):
            starts.add((g, "grid"))
    for g, iid, sk, kind in E.contacts:
        for k in ks:
            if g - 2 - k >= 1:
                starts.add((g - 2 - k, "contact"))
    Tmax = max(max(ks) + 3, T_area)
    mem_at = _memories(E)
    for g0, why in sorted(starts):
        obs, mems = [], {}
        for iid in E.iids:
            m = mem_at(iid, g0)
            o = E.obs(iid, g0, m)
            if o is not None and o.st is not None:
                obs.append(o)
                mems[iid] = m
        if not obs:
            continue
        T = min(Tmax, E.n_g - 1 - g0)
        if T < 3:
            continue
        hero = E.hero_path(g0, T, [o.iid for o in obs])
        try:
            P = cm.predict(obs, mems, hero, K, T=T, group=False, max_particles=400,
                           hazards=E.ghost_hazards(g0, {o.iid for o in obs}, K))
        except Exception as ex:                                  # a model bug: count it, keep going
            R["errors"].append(f"{g0}: {ex!r}")
            continue
        R["ms"].append((len(obs), P.ms, len(P.branches)))
        # the realized particle
        act_rel = {}
        for o in obs:
            act_rel[o.iid] = [dict(d, k=d["g"] - g0) for d in acts.get(o.iid, ()) if g0 < d["g"] <= g0 + T]
        real = None
        for b in P.branches:
            if all(consistent(b.logs.get(o.iid, []), act_rel[o.iid], T) for o in obs):
                real = b
                break
        R["realized"].append(real is not None)
        if real is None:
            continue
        R["real_p"].append((why, len(P.branches), round(float(real.p), 5),
                            int(sum(1 for b in P.branches if b.p >= real.p - 1e-12))))
        # timing: every state entry within the horizon (the n-th entry of a state, actual vs predicted)
        for o in obs:
            pe = defaultdict(list)
            prev = None
            for r in real.recs[o.iid]:
                if r[3] != prev and r[0] > 0:
                    pe[r[3]].append((r[0], r[1], r[2]))
                prev = r[3]
            ae = defaultdict(list)
            prev_a = E.st(o.iid, g0)
            for kk in range(1, T + 1):
                sa = E.st(o.iid, g0 + kk)
                if sa != prev_a and sa is not None:
                    ae[sa].append(kk)
                prev_a = sa
            prec = {(r[3], r[0]): r for r in real.recs[o.iid]}
            for st, lst in ae.items():
                for n, ka in enumerate(lst):
                    if n < len(pe.get(st, ())):
                        kp, a_, b_ = pe[st][n]
                        R["timing"].append((MOVE_OF.get(st, st), st, ka, ka - kp, a_ <= ka - kp <= b_, why))
                        r = prec.get((st, kp))
                        ia = E.g2i[g0 + ka]
                        if r is not None and st in ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic",
                                                    "Evade Scuttle", "Jump"):
                            R["face_k"].append((st, ka, int(r[7]) == int(E.cl[o.iid]["face"][ia])))
                        if r is not None and st == "Slam 2" and E.st(o.iid, g0 + ka - 1) == "Air":
                            R["land_k"].append((ka, round(float(r[5]) - float(E.cl[o.iid]["pos"][ia, 0]), 3)))
                    else:
                        R["timing"].append((MOVE_OF.get(st, st), st, ka, None, False, why))
        # contacts in the horizon at k in ks
        for g, iid, sk, kind in E.contacts:
            k = g - 2 - g0                      # the contact's earliest overlap frame (the trigger's lag 0 - 2)
            if k not in ks or k + 2 > T or (iid not in real.recs and sk not in ("bomb", "rune")):
                continue
            m_r = m_a = None                    # the smallest margin of the grid at which it is covered
            for mi, m in enumerate(MARGINS):
                for kk in range(k, k + 3):
                    hb = her_box(E, g0 + kk)
                    if m_r is None and any(s.hits_box(hb, m) for s in real.damage(kk)):
                        m_r = m
                    if m_a is None and any(s.hits_box(hb, m) for b in P.branches for s in b.damage(kk)):
                        m_a = m
                if m_r is not None and m_a is not None:
                    break
            R["contact"].append((k, sk, kind, m_r == 0.0, m_a == 0.0, m_r, m_a))
        # area at the grid starts
        if why == "grid":
            for k in ks:
                if k > T:
                    continue
                g = g0 + k
                for o in obs:
                    act = actual_damage(E, g, o.iid)
                    if not act:
                        continue
                    pred = [s for s in real.damage(k) if s.iid == o.iid and s.name in ("body", "Slam Collider 1",
                                                                                          "Slam Collider 2")]
                    a, cov, pa = area_cover(act, pred)
                    stn = E.st(o.iid, g)
                    R["area"].append((k, MOVE_OF.get(stn, stn), stn, round(a, 3), cov, round(pa, 3),
                                      any(s.name != "body" for s in act)))
                hz = actual_hazards(E, g)
                if hz:
                    pred = [s for s in real.damage(k) if s.name in ("bomb", "rune")]
                    for kind in ("bomb", "rune"):
                        act = [s for s in hz if s.name == kind]
                        if act:
                            a, cov, pa = area_cover(act, [s for s in pred if s.name == kind])
                            R["area"].append((k, kind, kind, round(a, 3), cov, round(pa, 3), True))
    # the jumps: landing x / frames from the aim (the model's flight from the take-off state, her x at the aim)
    for iid in E.iids:
        L = E.trans[iid]
        c = E.cl[iid]
        for n, (g, a, b, f) in enumerate(L):
            if b != "Jump Aim":
                continue
            land = next(((g2, f2) for (g2, a2, b2, f2) in L[n + 1:] if b2 == "Charged?"), None)
            if land is None or land[0] - g > 90:
                continue
            i = E.fi[f]
            o = cm.Obs(iid, "Jump Antic", 0.5, float(c["pos"][i - 1, 0]), float(c["pos"][i - 1, 1]), 0.0, 0.0,
                       int(c["face"][i - 1]), 200, "Antic", None, 10 ** 6, False, 29)
            hero = E.hero_path(g - 1, 100, [iid])
            K_ = K
            s = cm.Sim(o, cm.Memory(), K_, buddy=False)
            s.dur = (1, 1, 1)
            s.last_turn = -10 ** 6 if c["face"][i] == c["face"][i - 1] else -10 ** 6
            land_p = None
            for k in range(1, 100):
                s.step(k, hero, False, None)
                if s.st == "Slam 2" and land_p is None:
                    land_p = (k, s.x)
                    break
            if land_p is None:
                continue
            xl = float(E.cl[iid]["pos"][E.fi[land[1]], 0])
            near = min(xl - cm.WALL_L, cm.WALL_R - xl)
            x0 = float(c["pos"][i - 1, 0])
            naive = x0 + 0.916 * float(np.clip(E.hx[g] - 5 * c["face"][i] - x0, -12, 12))
            R["jump"].append((round(land_p[1] - xl, 3), (land_p[0] - 1) - (land[0] - g), round(near, 2),
                              round(naive - xl, 3), land[0] - g))
    return {k: v for k, v in R.items()}


def _memories(E: Episode):
    """A function (iid, g0) -> the Memory after every transition at frames <= g0 (incremental for rising g0)."""
    state = {iid: [cm.Memory(), 0] for iid in E.iids}

    def at(iid, g0):
        m, n = state[iid]
        L = E.trans[iid]
        while n < len(L) and L[n][0] <= g0:
            g, a, b, f = L[n]
            i = E.fi.get(f)
            m.observe(a, b, E.cl[iid]["clip"][i - 1] if i else None)
            n += 1
        state[iid][1] = n
        return m.copy()
    return at


def _job(args) -> dict:
    path, ks, every = args
    import pickle
    with open(path, "rb") as fh:
        tr = pickle.load(fh)
    K = cm.Know.load()
    t0 = time.time()
    r = run_episode(tr, K, ks, every)
    r["_id"] = tr["meta"]["id"]
    r["_unit"] = tr.get("unit")
    r["_s"] = time.time() - t0
    return r


def summarize(results: list[dict]) -> dict:
    S = {}
    allr = defaultdict(list)
    for r in results:
        for k, v in r.items():
            if not k.startswith("_"):
                allr[k].extend(v)
    # V4
    v4 = defaultdict(lambda: {"n": 0, "viol": 0, "ll": 0.0, "acc": 0})
    for kind, out, p, pmax, nopt in allr["v4"]:
        d = v4[kind]
        d["n"] += 1
        d["viol"] += p <= 0
        d["ll"] += -math.log(max(p, 1e-9))
        d["acc"] += p >= pmax - 1e-9
    S["v4"] = {k: {"n": d["n"], "violations": d["viol"], "logloss": round(d["ll"] / max(d["n"], 1), 4),
                   "argmax_hit": round(d["acc"] / max(d["n"], 1), 4)} for k, d in v4.items()}
    S["range_close_far"] = dict(Counter(f"{a} -> {b} rule_ok={ok}" for a, b, ok in allr["range"]))
    S["cancel"] = dict(Counter(f"{a} cancel={c} buddy_attacking={o}" for a, c, o in allr["cancel"]))
    S["face_at_start"] = {st: {"n": sum(1 for x in allr["face"] if x[0] == st),
                               "rule_ok": sum(1 for x in allr["face"] if x[0] == st and x[1]),
                               "faces_her": sum(1 for x in allr["face"] if x[0] == st and x[2])}
                          for st in sorted({x[0] for x in allr["face"]})}
    S["escape_ray"] = dict(Counter(f"escaped={e} pred={p}" for b, e, p in allr["escape"]))
    S["idle_walk"] = dict(Counter(f"{u} {d}" for u, d in allr["idle_walk"]))
    S["realized"] = {"n": len(allr["realized"]), "found": int(sum(allr["realized"]))}
    ms = allr["ms"]
    S["predict_ms"] = {f"{n} clapper(s)": {"n": sum(1 for x in ms if x[0] == n), "ms": pct([x[1] for x in ms if x[0] == n], (50, 90, 99)),
                                           "particles": pct([x[2] for x in ms if x[0] == n], (50, 90, 99))} for n in (1, 2)}
    # timing per (move, state)
    tm = defaultdict(list)
    for mv, st, ka, err, ok, why in allr["timing"]:
        tm[(mv, st)].append((ka, err, ok))
    S["timing"] = {}
    for (mv, st), v in sorted(tm.items()):
        errs = [e for _, e, _ in v if e is not None]
        S["timing"][f"{mv}/{st}"] = {"n": len(v), "matched": len(errs), "in_range": int(sum(ok for _, _, ok in v)),
                                     "abs_err": pct([abs(e) for e in errs], (50, 90, 99)),
                                     "err": pct(errs, (5, 50, 95)),
                                     "far_k>36_in_range": int(sum(ok for ka, _, ok in v if ka > 36)),
                                     "far_k>36_n": int(sum(1 for ka, _, _ in v if ka > 36))}
    # contacts: covered at m = 0 by the realized branch / by any branch; the smallest margin covering each
    ct = defaultdict(list)
    for k, sk, kind, hr, ha, m_r, m_a in allr["contact"]:
        ct[(k, sk)].append((hr, ha, m_r, m_a))
    S["contacts"] = {}
    for (k, sk), v in sorted(ct.items()):
        n = len(v)
        S["contacts"][f"k={k} {sk}"] = {
            "n": n, "realized": int(sum(x[0] for x in v)), "any_branch": int(sum(x[1] for x in v)),
            "realized_by_margin": {str(m): int(sum(1 for x in v if x[2] is not None and x[2] <= m)) for m in MARGINS},
            "any_by_margin": {str(m): int(sum(1 for x in v if x[3] is not None and x[3] <= m)) for m in MARGINS}}
    # area: covered share at each margin, per (move, k); the margin reaching 99 %
    ar = defaultdict(lambda: [0.0, np.zeros(len(MARGINS)), 0.0, 0])
    for k, mv, st, a, cov, pa, ham in allr["area"]:
        d = ar[(k, mv)]
        d[0] += a
        d[1] += np.asarray(cov, float)
        d[2] += pa
        d[3] += 1
    S["area"] = {}
    S["margin99"] = {}
    for (k, mv), d in sorted(ar.items()):
        share = d[1] / max(d[0], 1e-9)
        S["area"][f"k={k} {mv}"] = {"n": d[3], "covered": round(float(share[0]), 4),
                                    "covered_by_margin": {str(m): round(float(c), 4) for m, c in zip(MARGINS, share)},
                                    "ratio": round(d[2] / max(d[0], 1e-9), 3)}
        m99 = next((m for m, c in zip(MARGINS, share) if c >= 0.99), None)
        S["margin99"].setdefault(mv, {})[str(k)] = m99
    # facing / landing at the horizons (the realized branch's record at the actual move start / landing)
    fk = defaultdict(lambda: [0, 0])
    for st, ka, ok in allr["face_k"]:
        b = "0-12" if ka <= 12 else "13-36" if ka <= 36 else "37+"
        fk[(st, b)][0] += 1
        fk[(st, b)][1] += ok
    S["face_horizon"] = {f"{st} k {b}": {"n": v[0], "ok": v[1]} for (st, b), v in sorted(fk.items())}
    lk = defaultdict(list)
    for ka, dx in allr["land_k"]:
        lk["0-12" if ka <= 12 else "13-36" if ka <= 36 else "37+"].append(dx)
    S["landing_horizon"] = {b: {"n": len(v), "dx": pct(v, (5, 50, 95)), "abs_dx": pct([abs(x) for x in v], (50, 90, 99))}
                            for b, v in sorted(lk.items())}
    rp = allr["real_p"]
    S["realized_branch"] = {"p": pct([x[2] for x in rp], (5, 25, 50, 75)), "rank": pct([x[3] for x in rp], (50, 90, 99)),
                            "n_particles": pct([x[1] for x in rp], (50, 90, 99))}
    jp = allr["jump"]
    if jp:
        far = [x for x in jp if x[2] > 6]
        near = [x for x in jp if x[2] <= 6]
        S["jump_landing"] = {"n": len(jp),
                             "far_from_wall": {"n": len(far), "dx": pct([x[0] for x in far], (5, 50, 95)),
                                               "abs_dx": pct([abs(x[0]) for x in far], (50, 90, 99)),
                                               "frames_off": dict(Counter(x[1] for x in far))},
                             "near_wall_<=6u": {"n": len(near), "model_dx": pct([x[0] for x in near], (5, 50, 95)),
                                                "model_abs_dx": pct([abs(x[0]) for x in near], (50, 90, 99)),
                                                "naive_abs_dx": pct([abs(x[3]) for x in near], (50, 90, 99)),
                                                "frames_off": dict(Counter(x[1] for x in near).most_common(8))}}
    S["errors"] = allr["errors"][:20]
    S["n_errors"] = len(allr["errors"])
    return S


def cmd_run(a) -> int:
    idle_priority()
    ks = tuple(int(x) for x in a.ks.split(","))
    d = DATA / "cache" / a.set
    paths = sorted(d.glob("*.pkl"))
    if a.limit:
        paths = paths[:a.limit]
    t0 = time.time()
    jobs = [(str(p), ks, a.every) for p in paths]
    results = []
    if a.jobs > 1:
        from multiprocessing import Pool
        with Pool(a.jobs) as pool:
            for n, r in enumerate(pool.imap_unordered(_job, jobs)):
                results.append(r)
                if n % 25 == 0:
                    print(f"{n + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    else:
        for j in jobs:
            results.append(_job(j))
    S = summarize(results)
    S["_meta"] = {"set": a.set, "episodes": len(results), "ks": ks, "every": a.every, "s": round(time.time() - t0, 1)}
    out = Path(a.out or (DATA / f"val_{a.set}.json"))
    out.write_text(json.dumps(S, indent=1, default=str), "utf-8")
    raw = out.with_suffix(".raw.pkl")
    import pickle
    with open(raw, "wb") as fh:
        pickle.dump(results, fh)
    print(json.dumps(S, indent=1, default=str)[:6000])
    return 0


def report(S: dict, margins: dict | None = None) -> str:
    """A readable text of a validation summary (the margins: the knowledge file's table, to read the coverage at
    the fit's margin)."""
    L = []
    m = S.get("_meta", {})
    L.append(f"set {m.get('set')}: {m.get('episodes')} episodes, look-aheads {m.get('ks')}, grid every {m.get('every')} f")
    rz = S["realized"]
    L.append(f"realized branch found: {rz['found']} / {rz['n']} starts ({100 * rz['found'] / max(rz['n'], 1):.1f} %); "
             f"its probability p5/25/50/75 {S['realized_branch']['p']}, its rank p50/90/99 {S['realized_branch']['rank']}")
    for n, v in S["predict_ms"].items():
        L.append(f"predict {n}: n {v['n']}, ms p50/90/99 {v['ms']}, particles {v['particles']}")
    L.append("")
    L.append("RULES (at the decision frame)")
    for kind, v in S["v4"].items():
        L.append(f"  V4 {kind:9s} n {v['n']:5d}  violations {v['violations']}  log-loss {v['logloss']}  argmax {v['argmax_hit']}")
    L.append(f"  Close / Far at Dmg Attack / After Scuttle: {S['range_close_far']}")
    L.append(f"  the buddy lock: {S['cancel']}")
    L.append(f"  the escape ray: {S['escape_ray']}")
    L.append(f"  Idle -> Walk frames: {S['idle_walk']}")
    for st, v in S["face_at_start"].items():
        L.append(f"  facing at {st}: rule {v['rule_ok']} / {v['n']} (faces her {v['faces_her']})")
    if "jump_landing" in S:
        J = S["jump_landing"]
        L.append(f"  jump landing from the aim: far from a wall n {J['far_from_wall']['n']} |dx| p50/90/99 "
                 f"{J['far_from_wall']['abs_dx']}, frames off {J['far_from_wall']['frames_off']}; within 6 u of a wall "
                 f"n {J['near_wall_<=6u']['n']} model |dx| {J['near_wall_<=6u']['model_abs_dx']} vs the formula "
                 f"without the push {J['near_wall_<=6u']['naive_abs_dx']}, frames off {J['near_wall_<=6u']['frames_off']}")
    L.append("")
    L.append("TIMING (every state entry in the horizon vs the realized branch: frames off; in range = inside its [a, b])")
    for key, v in S["timing"].items():
        if v["n"] < 5:
            continue
        L.append(f"  {key:28s} n {v['n']:5d} matched {v['matched']:5d} in range {100 * v['in_range'] / max(v['matched'], 1):5.1f} %"
                 f"  |err| p50/90/99 {v['abs_err']}  k>36: {v['far_k>36_in_range']}/{v['far_k>36_n']}")
    L.append("")
    L.append("FACING / LANDING at the horizons (the realized branch's record at the actual move start / landing)")
    for key, v in S["face_horizon"].items():
        L.append(f"  facing {key:28s} {v['ok']} / {v['n']}")
    for key, v in S["landing_horizon"].items():
        L.append(f"  landing x k {key:6s} n {v['n']} dx p5/50/95 {v['dx']} |dx| p50/90/99 {v['abs_dx']}")
    L.append("")
    L.append("CONTACTS (true damage contacts: her HeroBox meets the predicted damage shapes; k = frames before the overlap)")
    for key, v in S["contacts"].items():
        L.append(f"  {key:16s} n {v['n']:4d}  realized {v['realized']:4d}  any branch {v['any_branch']:4d}"
                 f"  realized at 0.1 / 0.3 u {v['realized_by_margin']['0.1']} / {v['realized_by_margin']['0.3']}")
    L.append("")
    L.append("AREA (the actual damage colliders covered by the realized branch's shapes; ratio = predicted / actual area)")
    for key, v in S["area"].items():
        k, mv = key.split(" ", 1)
        kk = int(k[2:])
        extra = ""
        if margins and mv in margins:
            mm = next((x[1] for x in margins[mv] if kk <= x[0]), margins[mv][-1][1])
            c = v["covered_by_margin"].get(str(mm)) or v["covered_by_margin"].get(str(float(mm)))
            extra = f"  at the fit margin {mm} u: {c}"
        L.append(f"  {key:14s} n {v['n']:4d}  covered {v['covered']:.4f}  ratio {v['ratio']:.3f}{extra}")
    L.append("")
    L.append(f"margin for 99 % (this set): {S['margin99']}")
    return chr(10).join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--set", default="held")
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--every", type=int, default=60)
    p.add_argument("--ks", default="0,6,12,36,60")
    p.add_argument("--out", default=None)
    p = sub.add_parser("report")
    p.add_argument("summary")
    p.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "report":
        S = json.loads(Path(a.summary).read_text("utf-8"))
        mt = (cm.Know.load().d.get("margins") or {}).get("by_move")
        txt = report(S, mt)
        print(txt)
        if a.out:
            Path(a.out).write_text(txt, "utf-8")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
