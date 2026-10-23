"""Map v2 stage M3: the move RECOGNIZERS of the acceptance suite (docs/plans/forum_map_v2.md section 0). Offline.

A plan (search.Eval) is classified on its most probable outcome (the nominal one; every outcome's safety and hits are
reported separately): the strike events with the target's state at the press / contact (the outcome branch's records
at nominal timing), her trajectory (mode, ground, position) and the Clappers' predicted paths. A CONTINGENT plan (a
continuation per reaction to a hook, search.Seg.out_alt) is classified per reaction as well: the reaction labels
below are read on every outcome of the plan (each plays its reaction's continuation). Labels:

  CLAWSTRIKE   a hooked Clawline on a Clapper in Slam Antic pressed at antic frame 4 .. 12 (its frame in the state at
               the press, the model's j; SP13: k 5 - 11) and a later down slash contact on the same Clapper in Slam 0
               / Slam 1 or Slam Antic j >= 44 (antic 47 - 51)
  SLAMSTRIKE   no Clawline; she was on the ground at the decision; a down slash contact on a Clapper in Slam 0 / Slam 1
               / Slam Antic j >= 44 (the playbook's / the person's strike)
  P1           a hooked Clawline whose target at the press is Idle / Walk (P1-idle), in Slam Antic j <= 11 (P1-slam),
               in Spell Antic / Cast (P1-cast), in Jump Antic / Cast Slam Antic(2) (P1-jump), or Idle / Walk while the
               other one is attacking (P1-locked: the buddy lock, a free hit)
  P2           the umbrella open (Float) in the plan, closed by the plan (not by landing), then a down slash contact
               within 45 frames of the close
  P3-face      a contact on a Clapper in Idle / Walk (the frame before the hit) within 12 u of its nearer wall whose
               next move (it starts at the hit, facing her side) faces that wall (no move in the plan's horizon: her
               centre on its wall side by >= 0.3 u at the contact)
  P3-cross     a Clapper in Slam Antic facing her: she ends behind it (the side opposite its facing) before its Slam 0
  P4           >= 2 down slash contacts on a Clapper in Jump / Air (its flight), or one on its rising body (vy > 0)
  P5           a down slash contact on a grounded Clapper (not in its flight) while she falls (her vy < 0 at the
               press) with its body under her: her x at the press within its body's x range + 0.5 u
  JUMPTRAP     a Clapper in a jump move (Jump Antic .. its landing) toward her: at its landing she is on the far side
               of it (behind its landing along its flight) and passed under it (her x crossed its x while it flew)
  LOWHOP       a lit bomb ring under her x during the plan while she is airborne with her box bottom above the bombs'
               top, on the ground before the hop
 THE REACTIONS TO A HOOK ON AN IDLE / WALK CLAPPER (the person, 2026-10-22, MOVES_TODO P1), read in the outcomes where
 that reaction happens (the search.reaction_key of the hook: what she has seen by control):
  P1-idle-slam    it answers with a SLAM and she strikes it in the FIRST window: a later down slash contact on it in
                  Slam 0 / Slam 1 or Slam Antic j >= 44 ('+umb' in the details when the umbrella opened between
                  control and the contact)
  P1-idle-slam2   the same reaction, struck in the second window instead (a head pogo at Slam Antic j 20 .. 43)
  P1-idle-evade   it answers with an EVADE and she hooks it again (a second hooked Clawline on it after control)
  P1-far-jump     a hook from beyond Slam Range (the far list) answered with a JUMP and she RIDES it (P4 on it after
                  control: a contact on its rising body or two in its flight)
  P1-far-jcast    the same answered with a JUMP CAST and she strikes it (any down slash contact on it in its move
                  after control: the ride or a head pogo through the burst) with the outcome safe
Several labels may hold at once.
"""
from __future__ import annotations

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import strike as sk

SLAM_HIT_STATES = ("Slam 0", "Slam 1")
MOVE_STARTS = ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic", "Evade Scuttle")
FLIGHT = ("Jump", "Air")
JUMP_MOVE = ("Jump Antic", "Jump Aim", "Jump", "Air", "Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump", "Charged?")
JCAST_MOVE = ("Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump", "Jump", "Air", "Charged?")
ATTACKING = set(cm.ATTACKING)
REACTION_LABELS = ("P1-idle-slam", "P1-idle-slam2", "P1-idle-evade", "P1-far-jump", "P1-far-jcast")


def _st(br, iid, k):
    return sk.state_at(br, iid, k)


def presses(plan, tr) -> list:
    """[(kind, frame, iid)] of the plan's strike presses in this trajectory's frames (a down slash press at its mask
    frame, a Clawline at its P) - the segments this outcome played (a reaction's continuation, a hook variant's)."""
    out = []
    segs = getattr(tr, "segs", None) or plan.segs
    for si, seg in enumerate(segs):
        k0 = tr.seg_start[si] if si < len(tr.seg_start) else 0
        for (i, iid) in seg.dsl:
            out.append(("dslash", k0 + i + 1, iid))
        if seg.claw is not None:
            out.append(("claw", k0 + len(seg.masks), seg.claw[1]))
    return out


def _p4(br, downs, iid) -> bool:
    fl = []
    for (kc, i2) in downs:
        if i2 != iid:
            continue
        st = _st(br, iid, kc)
        st1 = _st(br, iid, kc + 1)
        if st is not None and st[0] in FLIGHT:
            rising = st1 is not None and st1[3] > st[3]
            fl.append((kc, rising))
    return len(fl) >= 2 or any(r for (_, r) in fl)


def classify_outcome(o, plan, sit) -> list:
    """The labels of one outcome of the plan (module docstring, without the reaction labels)."""
    tr, br = o.tr, o.branch
    labels = set()
    ps = presses(plan, tr)
    contacts = sorted(tr.contacts)
    iids = sorted(br.recs.keys())
    ground0 = bool(sit.S[km.GROUND] > 0)
    # ---- the Clawline ----
    claw_hits = [(k, iid) for (k, iid, kd) in contacts if kd == "claw"]
    for (kind, P, iid) in ps:
        if kind != "claw":
            continue
        hit = next((k for (k, i2) in claw_hits if i2 == iid and P < k <= P + 12), None)
        if hit is None:
            continue
        st = _st(br, iid, P)
        if st is None:
            continue
        s, j = st[0], st[1]
        others_att = any((_st(br, o2, P) or (None,))[0] in ATTACKING for o2 in iids if o2 != iid)
        if s in ("Idle", "Walk"):
            labels.add("P1-locked" if others_att else "P1-idle")
        elif s == "Slam Antic" and j <= 11:
            labels.add("P1-slam")
        elif s in ("Spell Antic", "Cast 1", "Cast 2"):
            labels.add("P1-cast")
        elif s in ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2"):
            labels.add("P1-jump")
        else:
            labels.add("P1-other")
        if s == "Slam Antic" and 4 <= j <= 12:
            later = [(k, i2) for (k, i2, kd) in contacts if kd == "down" and i2 == iid and k > hit]
            for (kc, _) in later:
                stc = _st(br, iid, kc)
                if stc is not None and (stc[0] in SLAM_HIT_STATES or (stc[0] == "Slam Antic" and stc[1] >= 44)):
                    labels.add("CLAWSTRIKE")
    # ---- the down slash contacts ----
    downs = [(k, iid) for (k, iid, kd) in contacts if kd == "down"]
    has_claw = any(p[0] == "claw" for p in ps)
    for (kc, iid) in downs:
        st = _st(br, iid, kc)
        if st is None:
            continue
        s, j, cx, cy, face = st
        if not has_claw and ground0 and (s in SLAM_HIT_STATES or (s == "Slam Antic" and j >= 44)):
            labels.add("SLAMSTRIKE")
        # P5: a grounded Clapper under her falling path
        prs = [p[1] for p in ps if p[0] == "dslash" and p[2] == iid and p[1] <= kc]
        press = max(prs) if prs else None
        if press is not None and s not in FLIGHT and press >= 1:
            vy = (tr.pos[press, 1] - tr.pos[press - 1, 1]) * 60.0
            b = sk.robust_boxes(br, iid)[kc] if kc < br.T else np.full(4, np.nan)
            if vy < 0 and not np.isnan(b[0]) and b[0] - 0.5 <= tr.pos[press, 0] <= b[2] + 0.5 and \
                    not tr.ground[max(press - 1, 0)]:
                labels.add("P5")
        # P3-face: an Idle / Walk Clapper (the frame before the hit) near a wall, hit from its wall side: its next
        # move (starting at the hit) faces the wall
        sb = _st(br, iid, kc - 1)
        if sb is not None and sb[0] in ("Idle", "Walk"):
            wall = cm.WALL_L if cx - cm.WALL_L < cm.WALL_R - cx else cm.WALL_R
            if abs(cx - wall) <= 12.0:
                to_wall = 1 if wall > cx else -1
                hx = tr.pos[kc, 0]
                nxt = next(((r[0], r[7]) for r in sorted(br.recs.get(iid, ()), key=lambda r: r[0])
                            if r[0] >= kc and r[3] in MOVE_STARTS and r[4] <= 1), None)
                if (nxt is not None and nxt[1] == to_wall) or (nxt is None and (hx - cx) * to_wall >= 0.3):
                    labels.add("P3-face")
    # P4: contacts on its flight
    for iid in iids:
        if _p4(br, downs, iid):
            labels.add("P4")
    # ---- P2: umbrella open -> closed by the plan -> a down slash contact ----
    mode = tr.mode
    glide = mode == km.M_GLIDE
    for k in range(1, len(mode)):
        if glide[k - 1] and not glide[k] and not tr.ground[k]:
            if any(k < kc <= k + 45 for (kc, _) in downs):
                labels.add("P2")
                break
    # ---- P3-cross: in a slam antic facing her she ends behind it before Slam 0 ----
    for iid in iids:
        st0 = _st(br, iid, 0)
        if st0 is None or st0[0] != "Slam Antic":
            continue
        face = st0[4]
        side0 = 1 if tr.pos[0, 0] > st0[2] else -1
        if side0 != face:
            continue                                  # she starts behind it already
        k_s0 = next((k for k in range(1, br.T) if (_st(br, iid, k) or ("",))[0] == "Slam 0"), None)
        if k_s0 is None or k_s0 >= len(tr.pos):
            continue
        side = 1 if tr.pos[k_s0, 0] > st0[2] else -1
        if side != face:
            labels.add("P3-cross")
    # ---- JUMPTRAP: under a jumper to behind its landing (at its landing, or at the plan's end if earlier) ----
    for iid in iids:
        traj = [(k, _st(br, iid, k)) for k in range(0, br.T + 1)]
        fly = [(k, s) for (k, s) in traj if s is not None and s[0] in FLIGHT]
        st0 = _st(br, iid, 0)
        if not fly or st0 is None or st0[0] not in JUMP_MOVE:
            continue
        land_x = fly[-1][1][2]
        take_x = fly[0][1][2]
        d = 1 if land_x > take_x else -1 if land_x < take_x else 0
        if d == 0:
            continue
        hx0 = tr.pos[0, 0]
        if (hx0 - take_x) * d <= 0:
            continue                                   # it does not jump toward her side
        k_end = min(fly[-1][0] + 1, len(tr.pos) - 1)
        behind = (tr.pos[k_end, 0] - land_x) * d > 0.5
        if behind and not any(i2 == iid for (_, i2) in downs):
            labels.add("JUMPTRAP")
    # ---- LOWHOP: airborne over a lit bomb row ----
    for k in range(1, min(br.T, len(tr.pos) - 1) + 1):
        lit = [s for s in br.shapes(k) if s.name == "bomb" and s.circle is not None]
        if not lit:
            continue
        x = tr.pos[k, 0]
        bb = tr.pos[k, 1] - sk.FOOT
        under = [s for s in lit if abs(s.circle[0] - x) <= s.circle[2] + 0.3]
        if under and not tr.ground[k] and bb > cm.FLOOR + 0.3 and ground0:
            labels.add("LOWHOP")
            break
    return labels


def reaction_details(o, lag: int = 2) -> list:
    """The reaction labels of one outcome: [(label, detail)] per hooked Clawline on an Idle / Walk Clapper (module
    docstring)."""
    from ssbot.map2.search import reaction_key
    tr, br = o.tr, o.branch
    out = []
    contacts = sorted(tr.contacts)
    downs = [(k, iid) for (k, iid, kd) in contacts if kd == "down"]
    for (P, iid, d, hooked, hit, ctrl) in getattr(tr, "claws", ()):
        if not hooked:
            continue
        st = _st(br, iid, P)
        if st is None or st[0] not in ("Idle", "Walk"):
            continue
        rk = reaction_key(br, P, lag)
        react = {out_ for (i2, out_) in rk if i2 == iid}
        chs = br.choices.get(iid, ())
        far = any(c[0] == "far" and P + 7 <= c[2] <= P + 23 for c in chs)
        later = [(k, i2) for (k, i2) in downs if i2 == iid and k > ctrl]
        if "SLAM" in react:
            first = second = None
            for (kc, _) in later:
                stc = _st(br, iid, kc)
                if stc is None:
                    continue
                if stc[0] in SLAM_HIT_STATES or (stc[0] == "Slam Antic" and stc[1] >= 44):
                    first = first or (kc, stc[0], stc[1])
                elif stc[0] == "Slam Antic" and 20 <= stc[1] <= 43:
                    second = second or (kc, stc[0], stc[1])
            if first is not None:
                umb = bool(np.any(tr.mode[ctrl:first[0] + 1] == km.M_GLIDE)) if ctrl < len(tr.mode) else False
                out.append(("P1-idle-slam", f"contact {first[0]} {first[1]} j{first[2]}" + (" +umb" if umb else "")))
            elif second is not None:
                out.append(("P1-idle-slam2", f"contact {second[0]} {second[1]} j{second[2]}"))
        if "EVADE" in react:
            again = [c for c in tr.claws if c[1] == iid and c[3] and c[0] > ctrl]
            if again:
                c2 = again[0]
                st2 = _st(br, iid, c2[0])
                out.append(("P1-idle-evade", f"second hook P {c2[0]} on {None if st2 is None else st2[0]}"))
        if far and "JUMP" in react and _p4(br, later, iid):
            out.append(("P1-far-jump", f"ride contacts {[k for (k, _) in later]}"))
        if far and "JUMP CAST" in react and o.safe:
            hits_ = [(kc, (_st(br, iid, kc) or ("?",))[0]) for (kc, _) in later]
            hits_ = [h for h in hits_ if h[1] in JCAST_MOVE or h[1] in ("Idle",)]
            if hits_:
                out.append(("P1-far-jcast", f"contacts {hits_}"))
    return out


def classify(ev, sit) -> list:
    """The labels of the plan: its nominal outcome's (module docstring) and, over all its outcomes, the reaction
    labels (a contingent plan plays a continuation per reaction)."""
    o = ev.nominal
    if o is None:
        return []
    labels = set(classify_outcome(o, ev.plan, sit))
    seen = set()
    for oo in ev.outcomes:
        if not getattr(oo.tr, "claws", None):
            continue
        key = (id(oo.branch.choices), oo.tr.variant)
        if key in seen:
            continue
        seen.add(key)
        for (lb, _) in reaction_details(oo):
            labels.add(lb)
    return sorted(labels)


def reaction_table(ev) -> dict:
    """{reaction label: (p of the outcomes that show it, a detail)} over the plan's outcomes (the acceptance report)."""
    out: dict = {}
    for oo in ev.outcomes:
        for (lb, det) in reaction_details(oo):
            p, d0 = out.get(lb, (0.0, det))
            out[lb] = (p + oo.p, d0)
    return out


__all__ = ["classify", "classify_outcome", "presses", "reaction_details", "reaction_table", "REACTION_LABELS"]
