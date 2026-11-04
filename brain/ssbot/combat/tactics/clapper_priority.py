"""Manual two-Clapper target preferences; action owners retain all key checks.

One scene chooses a target and contact preference. This does not certify a
crossing, an escape, repeated pogos, or any future input acceptance.
"""
import math
import os
from dataclasses import replace

import numpy as np
from ssbot.combat import two_play

from .forum_local import CLAPPER, EVADE_HIT_X, EVADE_RISK_X, clapper_facing
from .modes import EVADE, EntryAttack, entry_attack_prefs
from . import clapper_middle

JUMPS = {"CC_JUMP", "CC_JUMP_CAST"}
NEAR = {"Slam Antic", "Spell Antic"}
AIR = {"Jump", "Air"}
DEFAULT_SCORES = {"keep": 50., "intercept": 130., "hold": 140., "near": 110.,
                  "takeoff": 90., "middle": 70., "retreat": 150., "flip": 80., "overhead": 65.,
                  "middle_jump": 95.}


def enabled(fc):
    live = [s for s in fc.subjects if s.alive and s.in_play and s.pos is not None]
    return (len(live) == 2 and all(s.type_key == CLAPPER for s in live)
            and not (two_play.ASW or two_play.JUMPHIT or two_play.SP11B or two_play.RUNETIER or two_play.FLIPB)
            and os.environ.get("SSBOT_FORUM_CHAIN_ARM") == "B"
            and all(os.environ.get(k, "0").strip() == "1" for k in
                    ("SSBOT_FORUM_CHAIN_NATIVE", "SSBOT_FORUM_CHAIN_B2", "SSBOT_FORUM_CHAIN_AIR_MANUAL")))


def geometry(tac, ws, subjects):
    """Observed horizontal standing spans only; unknown boxes stay unknown."""
    try:
        hx = float(ws.hero.pos.v[0])
        if not .8 <= ws.hero.pos.conf <= 1.: return None
        hurt = np.asarray(ws.hero.hurtbox, float)
        if hurt.ndim != 2 or hurt.shape[0] < 3 or hurt.shape[1] != 2 or not np.isfinite(hurt).all(): return None
        left, right = hx - hurt[:, 0].min(), hurt[:, 0].max() - hx
        xa, xb = map(float, tac.pb.arena_x)
        if min(left, right) <= 0 or not np.isfinite([hx, xa, xb]).all() or not xa <= hx <= xb: return None
        bodies = {}
        for s in subjects:
            boxes = [b for b in getattr(tac._ent(ws, s.iid), "dmg_boxes", ()) or ()
                     if b.active is True and isinstance(b.name, str) and b.name.startswith(CLAPPER)]
            if len(boxes) != 1: return None
            p = np.asarray(boxes[0].poly, float)
            if p.ndim != 2 or p.shape[0] < 3 or p.shape[1] != 2 or not np.isfinite(p).all(): return None
            a, b = float(p[:, 0].min()), float(p[:, 0].max())
            if a >= b: return None
            bodies[s.iid] = (a, b)
        low, high = sorted(subjects, key=lambda s: float(s.pos[0]))
        lo, hi = bodies[low.iid][1] + left, bodies[high.iid][0] - right
        region = ("left" if hx + right <= bodies[low.iid][0] else
                  "right" if hx - left >= bodies[high.iid][1] else
                  "middle" if lo <= hx <= hi else
                  "tight" if lo > hi and low.pos[0] <= hx <= high.pos[0] else "over")
        return dict(bodies=bodies, left=float(left), right=float(right), xa=xa, xb=xb,
                    low=low, high=high, lo=float(lo), hi=float(hi), region=region)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def ground_stance(tac, target, hx, geo):
    if geo is None: return None
    a, b = geo["bodies"][target.iid]
    other = geo["high"] if target.iid == geo["low"].iid else geo["low"]
    c, d = geo["bodies"][other.iid]
    if hx < target.pos[0]:
        lo = max(geo["xa"], d if c < a else geo["xa"]) + geo["left"]
        hi = a - geo["right"]
    else:
        lo = b + geo["left"]
        hi = min(geo["xb"], c if d > b else geo["xb"]) - geo["right"]
    return (min(hi, max(lo, target.pos[0] + (-1 if hx < target.pos[0] else 1) * tac.rules.face_u))
            if lo < hi else None)


def entry(tac, ws, fc, source, target, t, geo):
    """Ground room plus the existing forecast window chooses side versus stomp."""
    if source is None or source.iid == target.iid or source.family not in JUMPS | {"CC_CAST", "CC_SLAM"}:
        return None, None
    hx = float(ws.hero.pos.v[0]); stance = ground_stance(tac, target, hx, geo)
    if stance is not None:
        arrival = tac.rules.start_s + abs(stance - hx) / tac.rules.run_u_s
        end = arrival + tac.rules.swing_s + tac.rules.margin_s
        if end > tac.rules.window_max_s:
            stance = None
        else:
            times = np.linspace(arrival, end, max(2, int(math.ceil((end - arrival) * 30)) + 1))
            X = np.full((1, len(times)), stance)
            occ = np.asarray(fc.occupied(X, np.full_like(X, tac.floor_y), times))
            if occ.shape != X.shape or occ.dtype.kind != "b" or occ.any(): stance = None
    kind = "stomp" if stance is None else "side"
    return EntryAttack(target.iid, kind, source.iid, source.family,
                       abs(float(source.pos[0]) - hx), t), stance


def decide(tac, ws, fc, prefs, hx, t):
    """Choose once, then apply only that scene's scores and stance."""
    from .gauntlet import RUSH, TWO_SLAM_RANGE_U, TWO_WALL_BAND_U
    subjects = [s for s in fc.subjects if s.alive and s.in_play and s.pos is not None]
    mem = tac._clapper_priority
    if mem is None: mem = tac._clapper_priority = {"seen": {}, "intercept": None, "departed": None, "region": None}
    geo = geometry(tac, ws, subjects)
    region = None if geo is None else geo["region"]
    middle = clapper_middle.observe(tac, ws, subjects, geo, t, mem)
    seen = {s.iid: (s.family, s.state, abs(s.pos[0] - hx) <= TWO_SLAM_RANGE_U,
                    tac.t_commit.get(s.iid)) for s in subjects}
    old = tac.goal
    keep = next((s for s in subjects if old is not None and s.iid == old.target), None)
    hold = mem["intercept"]
    if hold is not None:
        held = next((s for s in subjects if s.iid == hold[0]), None)
        if (held is None or (held.family in JUMPS and tac.t_commit.get(held.iid) != hold[1])
                or (held.family not in JUMPS and not (held.iid in tac.rune and t <= tac.rune[held.iid][3]))):
            mem["intercept"] = hold = None
    departed = mem["departed"]
    if departed is not None:
        leaving = next((s for s in subjects if s.iid == departed[0]), None)
        if leaving is None or leaving.family not in JUMPS or tac.t_commit.get(leaving.iid) != departed[1]:
            mem["departed"] = departed = None
    changed = seen != mem["seen"] or region != mem["region"]
    if middle is not None and (middle.get("decision") or {}).get("route") == "guide":
        prior = middle["decision"]
        elapsed = t - middle["antic_at"]
        source = next(s for s in subjects if s.iid == middle["move"][0])
        deadline = .48 if source.family == "CC_JUMP" else .88
        changed |= deadline-elapsed < prior["guide_arrival"]+tac.rules.margin_s
    if keep is None or changed or tac.n % tac.rules.period == 0:
        cands = tac.candidates(ws, fc, hx, None if keep is None else keep.iid)
        by_id = {c.s.iid: c for c in cands}
        a, b = cands
        room = {a.s.iid: tac._outer_room(a, b), b.s.iid: tac._outer_room(b, a)}
        default = keep or (min(subjects, key=lambda s: abs(s.pos[0] - hx)) if region in {"left", "right", "over"}
                           else max(subjects, key=lambda s: (room[s.iid], -abs(s.pos[0] - hx))))
        other = next(s for s in subjects if s.iid != default.iid)
        caps = DEFAULT_SCORES | tac.rules.clapper_scores
        choices = []
        def offer(rule, target, applicability=1.):
            cost = tac.rules.clapper_switch_cost if keep is not None and target.iid != keep.iid else 0.
            choices.append(dict(rule=rule, target=target.iid, maximum=caps[rule], applicability=applicability,
                                switch_cost=cost, score=caps[rule] * applicability - cost))
        offer("keep", default)
        if middle is not None:
            mid = middle["decision"] = clapper_middle.choose(tac, ws, fc, geo, hx, t, middle)
            if mid["route"] == "hold": mid["target"] = default.iid
            offer("middle_jump", next(s for s in subjects if s.iid == mid["target"]))
        rear = False
        if keep is not None and other.family in JUMPS and other.state in AIR:
            rec = tac.jb_land.get(other.iid)
            ent = tac._ent(ws, other.iid)
            face = clapper_facing(ent) if ent is not None else None
            origin, front = (rec[0], rec[1]) if rec is not None else (other.pos[0], face)
            rear = (front in (-1, 1) and (origin - hx) * (default.pos[0] - hx) < 0
                    and (hx - origin) * front > 0)
        if hold is not None and middle is None:
            offer("hold", next(s for s in subjects if s.iid == hold[0]))
        elif middle is None and rear and departed != (other.iid, tac.t_commit.get(other.iid)):
            offer("intercept", other)
        if keep is not None:
            previous = mem["seen"].get(other.iid)
            if other.state in NEAR and seen[other.iid][2] and (previous is None or previous[:3] != seen[other.iid][:3]):
                offer("near", other, .8 + .2 * max(0., 1. - abs(other.pos[0] - hx) / TWO_SLAM_RANGE_U))
            if (middle is None and hold is None and keep.family in JUMPS and keep.state in AIR
                  and mem["seen"].get(keep.iid, (None, None))[1] not in AIR
                  and other.family not in JUMPS
                  and not (other.iid in tac.rune and t <= tac.rune[other.iid][3])):
                offer("takeoff", other)
        if middle is None and region == "middle" and mem["region"] != "middle":
            offer("middle", max(subjects, key=lambda s: (room[s.iid], -abs(s.pos[0] - hx))))
        if middle is None and region in {"left", "right"}:
            far = geo["high"] if region == "left" else geo["low"]
            far_room = geo["xb"] - far.pos[0] if region == "left" else far.pos[0] - geo["xa"]
            back_room = (hx - geo["xa"] - tac.rules.wall_room_u if region == "left" else
                         geo["xb"] - tac.rules.wall_room_u - hx)
            if (far_room <= TWO_WALL_BAND_U and back_room >= tac.rules.cast_out_u and any(
                    s.family in JUMPS and s.state in AIR or (s.iid in tac.rune and t <= tac.rune[s.iid][3])
                    for s in subjects)):
                offer("retreat", default)
            if default.state in NEAR: offer("flip", default)
        if middle is None and region == "tight": offer("overhead", default)
        winner = max(choices, key=lambda c: (c["score"], keep is not None and c["target"] == keep.iid))
        target = next(s for s in subjects if s.iid == winner["target"])
        reason = winner["rule"]
        mem["winner"] = reason
        if reason == "takeoff":
            # The focus we intentionally left is still the same jump, even
            # when it becomes the nonfocus behind us on the following tick.
            mem["departed"] = (keep.iid, tac.t_commit.get(keep.iid))
        if reason == "intercept": mem["intercept"] = (target.iid, tac.t_commit.get(target.iid))
        elif hold is not None and target.iid != hold[0]: mem["intercept"] = None
        tac.last["clapper_choices"] = choices
        tac.last["clapper_winner"] = dict(winner)
        goal = tac._goal(ws, by_id[target.iid], RUSH, t, winner["score"], why="two manual: " + reason)
        if old is not None and old.target == target.iid:
            goal.t_pick, goal.t_goal, goal.landed, goal.entry_attack = old.t_pick, old.t_goal, old.landed, old.entry_attack
        elif keep is not None and reason not in {"intercept", "hold"}:
            goal.entry_attack, _ = entry(tac, ws, fc, keep, target, t, geo)
        if reason == "middle_jump":
            mid = middle["decision"]
            previous = goal.entry_attack
            source = next(s for s in subjects if s.iid == mid["source"])
            if mid["kind"] is None:
                goal.entry_attack = None
            elif not (previous is not None and (previous.target, previous.source, previous.kind) ==
                      (target.iid, source.iid, mid["kind"])):
                goal.entry_attack = EntryAttack(target.iid, mid["kind"], source.iid, source.family,
                                               abs(float(source.pos[0])-hx), t)
        if old is None or old.target != target.iid or old.name != RUSH:
            tac.stats["changes"] += 1
            if old is not None and old.target != target.iid:
                tac.stats["tgt_switches"] += 1
                tac.stats["switches"] += int(keep is not None)
                sk = tac.stats["switch_kinds"]; sk[reason] = sk.get(reason, 0) + 1
        tac.stats["picks"] += 1
        tac.goal = goal
    mem["seen"], mem["region"] = seen, region
    g = tac.goal
    target = next(s for s in subjects if s.iid == g.target)
    g.stance_x, g.vocab, how = tac._spot(ws, target, hx)
    g.face_x = float(target.pos[0])
    style = None; scene = "attack focus"
    if g.entry_attack is not None:
        age = t - g.entry_attack.picked_at
        if not 0 <= age < 2. or (g.entry_attack.kind == "side" and target.family in JUMPS | {"CC_SLAM"}):
            g.entry_attack = None
        else: style = g.entry_attack.kind
    if target.family in JUMPS and target.state not in AIR and target.state in {"Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2"}:
        g.stance_x = tac._clamp(target.pos[0] + (-1 if hx < target.pos[0] else 1) * tac.rules.face_u)
        how = "face: hold until takeoff"
    retreat = mem["winner"] == "retreat"
    if retreat:
        direction = -1 if region == "left" else 1
        g.stance_x = tac._clamp(hx + direction * tac.rules.cast_out_u)
        style, scene = None, "outer jump retreat"
    elif mem["winner"] == "flip":
        direction = 1 if region == "left" else -1
        g.stance_x = tac._clamp(target.pos[0] + direction * tac.rules.face_u)
        style, scene = "stomp", "flip inward intent"
    elif mem["winner"] == "overhead":
        g.stance_x = float(target.pos[0]); style, scene = "stomp", "tight middle overhead intent"
    elif g.entry_attack is not None and style == "side":
        stand = ground_stance(tac, target, hx, geo)
        if stand is not None: g.stance_x = stand
    weights = dict(prefs.weights)
    if prefs.mode == EVADE:
        weights["hit"] /= EVADE_HIT_X; weights["risk"] /= EVADE_RISK_X
    for k, v in (tac.rules.weights.get(RUSH) or {}).items(): weights[k] = weights.get(k, 0.) * float(v)
    hw = {iid: min(w, tac.local.rules.other_hit_w) if w > 0 and iid != g.target else w for iid, w in prefs.hit_w.items()}
    hw[g.target] = max(hw.get(g.target, 0.), tac.rules.target_hit_w * tac.rules.priority.get(CLAPPER, 1.))
    out = replace(prefs, mode=RUSH, goal=RUSH, target=g.target, stance_x=float(g.stance_x), boss_x=g.face_x,
                  weights=weights, hit_w=hw, entry_attack=g.entry_attack, clapper_choice=mem["winner"],
                  vocab=frozenset(prefs.vocab) | g.vocab)
    if retreat or (target.family in JUMPS and target.state in AIR):
        out = replace(out, no_hit=frozenset(out.no_hit) | ({s.iid for s in subjects} if retreat else {g.target}), entry_attack=None)
    else:
        out = tac._contact_preferences(fc, out, g, target, hx, how)
        out = entry_attack_prefs(out)
        if style == "stomp":
            kw = dict(out.hit_kw); kw[g.target] = (0., 0., 0., hw[g.target])
            out = replace(out, hit_kw=kw, ground_hit=frozenset(out.ground_hit) - {g.target},
                          no_pogo=frozenset(out.no_pogo) - {g.target}, ground_first=frozenset(out.ground_first) - {g.target})
    if tac.ta: out, _ = tac._ta_rules(ws, fc, out, g, target, hx)
    mid = middle["decision"] if middle is not None else None
    if mem["winner"] == "middle_jump" and mid is not None:
        # Apply after legacy face/antic stance helpers, which must not turn a
        # refused guide or a middle interval into target +/- face_u again.
        g.stance_x = float(mid["stance"])
        out = replace(out, stance_x=g.stance_x)
        scene = "middle jump: " + mid["route"]
    g.why = g.why.split("; ")[0] + "; " + scene + "; " + str(how)
    tac.last.update(goal=RUSH, goal_why=g.why, target_type=CLAPPER, goal_t_end=None,
                    entry_attack=None if out.entry_attack is None else vars(out.entry_attack),
                    clapper_scene=scene, clapper_region=region, clapper_middle=mid)
    tac.stats["goals"][RUSH] = tac.stats["goals"].get(RUSH, 0) + 1
    return out
