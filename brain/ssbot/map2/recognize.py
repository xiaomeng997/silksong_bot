"""Map v2 stage M3: the move RECOGNIZERS of the acceptance suite (docs/plans/forum_map_v2.md section 0). Offline.

A plan (search.Eval) is classified on its most probable outcome (the nominal one; every outcome's safety and hits are
reported separately): the strike events with the target's state at the press / contact (the outcome branch's records
at nominal timing), her trajectory (mode, ground, position) and the Clappers' predicted paths. Labels:

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
ATTACKING = set(cm.ATTACKING)


def _st(br, iid, k):
    return sk.state_at(br, iid, k)


def presses(plan, tr) -> list:
    """[(kind, frame, iid)] of the plan's strike presses in this trajectory's frames (a down slash press at its mask
    frame, a Clawline at its P)."""
    out = []
    for si, seg in enumerate(plan.segs):
        k0 = tr.seg_start[si] if si < len(tr.seg_start) else 0
        for (i, iid) in seg.dsl:
            out.append(("dslash", k0 + i + 1, iid))
        if seg.claw is not None:
            out.append(("claw", k0 + len(seg.masks), seg.claw[1]))
    return out


def classify(ev, sit) -> list:
    """The labels of the plan's nominal outcome (see the module docstring)."""
    o = ev.nominal
    if o is None:
        return []
    tr, br = o.tr, o.branch
    labels = set()
    ps = presses(ev.plan, tr)
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
        fl = []
        for (kc, i2) in downs:
            if i2 != iid:
                continue
            st = _st(br, iid, kc)
            st1 = _st(br, iid, kc + 1)
            if st is not None and st[0] in FLIGHT:
                rising = st1 is not None and st1[3] > st[3]
                fl.append((kc, rising))
        if len(fl) >= 2 or any(r for (_, r) in fl):
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
    return sorted(labels)


__all__ = ["classify", "presses"]
