"""Manual two-Clapper target preferences; action owners retain all key checks.

One scene chooses a target and contact preference. This does not certify a
crossing, an escape, repeated pogos, or any future input acceptance.

Task 180: every complete tactic (its applicability, maximum scores, event phases and whole L2 output) is one unit in
clapper_tactics; the scene facts are clapper_scene's. decide() runs only the shared parts: the observation in the
declared order, the pick triggers, one comparison of the offers, the winner's commitments, the shared constraints of
the application, and the logs (clapper_eval: per tactic offered / not applicable and why / excluded by which event /
filtered by the scene owner).
"""
import os
from dataclasses import replace

import numpy as np

from ssbot.combat import two_play

from .clapper_scene import (AIR, ANTIC, JUMPS, NEAR, Scene, entry, geometry, ground_stance, stacked_nearer,  # noqa: F401
                            standing_gap)
from .clapper_tactics import (BAIT_WIDTHS, DEFAULT_SCORES, KEEP, LEGACY_TABLE, OBSERVE, RETURN_LANDED_S, RULES,  # noqa: F401
                              TACTICS, Applied, cluster_route, middle_return, return_pose, table)
from . import clapper_separated as SEP
from .forum_local import CLAPPER, EVADE_HIT_X, EVADE_RISK_X
from .modes import EVADE, EntryAttack, StageWithdraw, entry_attack_prefs

# Task 182 (the person 11-13 "那就先修出圈吧"; Sol analysis/w13_50_b13b404_20261113/video_0250/REVIEW.md): a big rune circle's way out
# holds on the FINAL stance. The base spot's exit (gauntlet._clapper_spot, only the target's own rune) was overwritten by the winner's
# stage stance (b13b404 ep2: cluster attack_aim 29.0, then attack_retreat 33.8, both inside the circle 24.7..39.1; 2 HP at its lighting,
# 12361). runtime354's 21 big rune hits: L2's stance came from a rune branch in 5 only. "0": off (offline A/B only).
RUNE_EXIT_FINAL = os.environ.get("SSBOT_FORUM_RUNE_EXIT_FINAL", "1").strip() != "0"
RUNE_EXIT_HALF_U = .25      # her half width when the scene's boxes are unknown (geometry None)


def rune_exit_x(x, hx, circles, bodies, roots, walls, left, right, pad):
    """The stance x moved out of the live big rune circles (pure; _rune_exit reads the inputs).

    circles: [(lo, hi)] the x spans lit now or still to come; bodies: [(a, b)] the observed body spans; roots: the Clappers' root x;
    walls: (xa, xb); left / right: her half widths; pad: JT's pad. Her centre at x is in a circle when her box grown by the pad meets it
    (clapper_separated.in_circle's test). Every circle and every body is grown the same way (the centres where her box would meet it)
    and the overlapping or touching ones are merged: when x lies in a merged span that holds a circle, the candidates are that span's
    two ends inside the walls (her box and the pad inside them). The pick: an end whose way from her (hx) passes no Clapper's root
    first, then the one nearer to her. Returns (x, None) when x is in no circle; (x, rec) with rec["exit"] None when neither end lies
    inside the walls (the stance kept), else (the end, rec)."""
    grown = [(lo - right - pad, hi + left + pad) for lo, hi in circles]
    hits = [i for i, (a, b) in enumerate(grown) if a < x < b]
    if not hits:
        return x, None
    spans = sorted([(a, b, True) for a, b in grown] + [(a - right - pad, b + left + pad, False) for a, b in bodies])
    merged = []
    for a, b, circ in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2] = merged[-1][2] or circ
        else:
            merged.append([a, b, circ])
    lo, hi, _ = next(m for m in merged if m[2] and m[0] < x < m[1])
    xa, xb = walls
    ends = []
    for e in (lo, hi):
        inside = xa + left + pad <= e <= xb - right - pad
        cross = any(min(hx, e) < r < max(hx, e) for r in roots)
        ends.append(dict(x=round(float(e), 4), inside=bool(inside), crosses=bool(cross)))
    ok = [(d["crosses"], abs(d["x"] - hx), d["x"]) for d in ends if d["inside"]]
    best = min(ok)[2] if ok else None
    rec = dict(x0=round(float(x), 4), exit=best, hx=round(float(hx), 4), span=(round(float(lo), 4), round(float(hi), 4)),
               circles=[tuple(round(float(v), 4) for v in circles[i]) for i in hits], ends=ends)
    return (x if best is None else best), rec


def _rune_exit(sc, x):
    """rune_exit_x on this call's facts: the shared ledger's live circles (clapper_separated.live_circles), the observed bodies and
    her half widths (clapper_scene.geometry; unknown: no bodies, RUNE_EXIT_HALF_U), the arena walls and the Clappers' roots."""
    from .gauntlet import JT
    circles = SEP.live_circles(sc.tac, sc.t)
    if not circles:
        return x, None
    geo = sc.geo
    if geo is not None:
        left, right, walls, bodies = geo["left"], geo["right"], (geo["xa"], geo["xb"]), list(geo["bodies"].values())
    else:
        left = right = RUNE_EXIT_HALF_U
        walls, bodies = tuple(map(float, sc.tac.pb.arena_x)), []
    roots = [float(s.pos[0]) for s in sc.subjects]
    return rune_exit_x(float(x), float(sc.hx), circles, bodies, roots, walls, float(left), float(right), float(JT["pad"]))


# Task 182 item 3, the landing-hammer exit (TO_SOL #421 / #422; Sol seq362 / seq363, Astra DESIGN_REVIEW421 / DESIGN_REVIEW422): a final stance
# preference, default off. runtime354: in 4 of the 10 losses to the other Clapper's jump landing hammer L2's final stance (keep / intercept,
# attack focus) lay inside the landing hammer for most of the flight. While ANOTHER Clapper's jump is committed (forum_v2.committed: past its
# Jump Aim, or landed) its landing hammer band is a place the final stance leaves early: the landing Slam Collider 2 along its facing from the
# landing root (LEXIT_BAND: the model's boxes of runtime354 bout 22's two hurts, 70734 a CC_JUMP_CAST and 71442 a CC_JUMP, both on open
# floor) and its standing body (LEXIT_BODY each side). A bounded preference with these two examples' extents, x only: not a hammer safety
# envelope; every safety gate stays as it is. Its domain: CC_JUMP / CC_JUMP_CAST, the instance's decided branch "open" (are_types.clapper
# .jump_branch) and its landing root inside the open zone (clapper.WALL_ZONE: no wall correction), the observed flipX (forum_local
# .clapper_facing's convention without its Entity.facing fallback) bound at the instance's first committed tick. The landing root: observed
# once landed; in the air the ballistic body (knife_chain_transfer.body_path from the STATE pos / vel) carried to the floor, re-predicted
# every tick; from Slam Recover on no band. A committed jump outside the domain (a wall or unknown branch, no observed flipX or a changed
# one, a STATE input missing, a ballistic landing in the wall zone) or a scene without its geometry: both stances kept, the reasons logged.
# L2's own target's jump never triggers it (its landing is the jump rule's); its band is merged as an obstacle. The exit (landing_exit_x):
# an end of the span holding the stance, inside the walls, whose way from her crosses no Clapper's root and no committed jump's predicted
# landing root interval; the side kept per jump instance and output while it stays allowed; neither end allowed: the stance kept. Ordinary
# stance and StageWithdraw only; waypoints, chains and entry attacks are not covered. "1": on.
LANDING_EXIT = os.environ.get("SSBOT_FORUM_LANDING_EXIT", "0").strip() == "1"
LEXIT_BAND = (.67, 7.75)        # the landing Slam Collider 2's x extent from the landing root along the facing
LEXIT_BODY = 2.3                # the standing body's x extent each side of its root
LEXIT_ROOT_U = .3               # the predicted landing root's uncertainty each side, plus its x speed over 2 frames
LEXIT_HAMMER_STATES = ("Charged?", "Slam Effects?", "Slam 2")
LEXIT_PATH_F = 90               # the ballistic body's frames (a jump's flight is ~55)


def landing_exit_x(x, hx, bands, circles, bodies, roots, root_ivs, walls, left, right, pad):
    """The stance x moved out of the landing hammer bands (pure; _landing_exit reads the inputs). bands: [(lo, hi)] the triggering bands;
    circles: [(lo, hi)] the obstacles merged with them (the live big rune circles, L2's own target's band); bodies: [(a, b)] the observed
    body spans; roots: the Clappers' root x; root_ivs: [(lo, hi)] the committed jumps' predicted landing roots; walls: (xa, xb); left /
    right: her half widths; pad: JT's pad. Every span is grown by her half widths and the pad and the overlapping or touching ones are
    merged; when x lies in a merged span holding a band, its two ends are the candidates. An end must lie inside the walls (her box and the
    pad) and its way from her (hx) cross no root and no predicted landing root interval (a hard filter, no path certificate). Returns
    (x, None) when x is in no band; else (x or the nearer allowed end, rec): rec["exit"] None when neither end is allowed (the stance
    kept), rec["ends"] each end with its reasons ("wall", "current root", "predicted landing root")."""
    grown_b = [(lo - right - pad, hi + left + pad) for lo, hi in bands]
    if not any(a < x < b for a, b in grown_b):
        return x, None
    spans = sorted([(a, b, True) for a, b in grown_b] + [(lo - right - pad, hi + left + pad, False) for lo, hi in circles]
                   + [(a - right - pad, b + left + pad, False) for a, b in bodies])
    merged = []
    for a, b, band in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2] = merged[-1][2] or band
        else:
            merged.append([a, b, band])
    lo, hi, _ = next(m for m in merged if m[2] and m[0] < x < m[1])
    xa, xb = walls
    ends = []
    for e in (lo, hi):
        why = []
        if not xa + left + pad <= e <= xb - right - pad:
            why.append("wall")
        if any(min(hx, e) < r < max(hx, e) for r in roots):
            why.append("current root")
        if any(min(hx, e) < b and max(hx, e) > a for a, b in root_ivs):
            why.append("predicted landing root")
        ends.append(dict(x=round(float(e), 4), why=why))
    ok = [(abs(d["x"] - hx), d["x"]) for d in ends if not d["why"]]
    best = min(ok)[1] if ok else None
    rec = dict(x0=round(float(x), 4), exit=best, hx=round(float(hx), 4), span=(round(float(lo), 4), round(float(hi), 4)), ends=ends)
    return (x if best is None else best), rec


def _landing_facts(sc):
    """This call's committed jumps, read once: (bands, unknown). bands: [dict(iid, own, key, state, face, root, root_iv, land_k, band)]
    for each one in the domain (LANDING_EXIT's note) with its hammer still ahead (own: the jumper is L2's target); unknown: [(iid, state,
    reason)] for each one outside it, and (None, None, reason) for a missing tracker or scene geometry. Binds each instance's facing on its
    first committed tick in sc.mem["lexit"], keyed by its iid and t0 (a facing seen to change later keeps the instance unknown), and drops
    the instances that ended."""
    from ssbot.combat import knife_chain_transfer as T
    from ssbot.combat.are_types.clapper import WALL_ZONE
    from ssbot.combat.forum_v2 import committed
    trk = getattr(sc.tac, "v2trk", None)
    if trk is None:
        return [], [(None, None, "no tracker")]
    now = getattr(trk, "now", None) or {}
    tgt = getattr(getattr(sc.tac, "goal", None), "target", None)
    mem = sc.mem.setdefault("lexit", {})
    bands, unknown, live = [], [], set()
    for s in sc.subjects:
        cur = now.get(s.iid)
        inst = None if cur is None else cur[2]
        if not committed(inst):
            continue
        iid, st = int(s.iid), str(inst.states[-1])
        key = (iid, round(float(inst.t0), 4))
        live.add(key)
        if st not in ("Jump", "Air") + LEXIT_HAMMER_STATES:
            continue                                      # Slam Recover: no hammer ahead
        if inst.branch != "open":
            unknown.append((iid, st, f"branch {inst.branch}"))
            continue
        ent = sc.tac._ent(sc.ws, iid)
        fl = None if ent is None else getattr(ent, "flip_x", None)
        if fl is None:
            unknown.append((iid, st, "no observed flipX"))
            continue
        face = 1 if fl else -1
        m = mem.setdefault(key, {})
        if m.setdefault("face", face) != face:
            m["face_changed"] = True
        if m.get("face_changed"):
            unknown.append((iid, st, "facing changed"))
            continue
        e = cur[1] if isinstance(cur[1], dict) else None
        vel = None if e is None else e.get("vel")
        try:
            x0, vx = float(s.pos[0]), (0. if vel is None else float(vel[0]))
        except (TypeError, ValueError, IndexError):
            x0 = vx = float("nan")
        if not (np.isfinite(x0) and np.isfinite(vx)):
            unknown.append((iid, st, "no finite STATE x / velocity"))
            continue
        land_k = 0
        if st in ("Jump", "Air"):
            bp = None if vel is None else T.body_path(e, LEXIT_PATH_F)
            if bp is None:
                unknown.append((iid, st, "no STATE velocity" if vel is None else "no ballistic body"))
                continue
            down = np.nonzero(bp[1:, 1] <= T.ROUTE_FLOOR_Y + 1e-6)[0]
            if not len(down):
                unknown.append((iid, st, f"no landing within {LEXIT_PATH_F} frames"))
                continue
            land_k = int(down[0]) + 1
            root = x0 + float(bp[land_k][0] - bp[0][0])
        else:
            root = x0
        if not WALL_ZONE[0] <= root <= WALL_ZONE[1]:
            unknown.append((iid, st, "landing root in the wall zone"))
            continue
        du = LEXIT_ROOT_U + abs(vx) * 2 / 60.
        a, b = root + face * LEXIT_BAND[0], root + face * LEXIT_BAND[1]
        band = (min(a, b, root - LEXIT_BODY), max(a, b, root + LEXIT_BODY))
        bands.append(dict(iid=iid, own=bool(tgt is not None and iid == int(tgt)), key=key, state=st, face=face,
                          root=round(root, 4), root_iv=(round(root - du, 4), round(root + du, 4)), land_k=land_k,
                          band=(round(band[0], 4), round(band[1], 4))))
    for k in [k for k in mem if k not in live]:
        del mem[k]                                        # the instance ended: its bound facing and kept sides go
    if bands and sc.geo is None:
        unknown.append((None, None, "no scene geometry"))
    return bands, unknown


def _landing_exit(sc, bands, x, which):
    """landing_exit_x for one output (which: "stance" / "withdraw") on this call's bands (_landing_facts, no unknown), the live big rune
    circles, the observed bodies, the roots, the walls and her half widths (clapper_scene.geometry); the side kept per jump instance and
    output while it stays allowed (sc.mem["lexit"]). (x, rec); rec None when no band of another Clapper's jump holds x."""
    from .gauntlet import JT
    trig = [b for b in bands if not b["own"]]
    if not trig:
        return x, None
    geo = sc.geo
    roots = [float(s.pos[0]) for s in sc.subjects]
    nx, rec = landing_exit_x(float(x), float(sc.hx), [b["band"] for b in trig],
                             list(SEP.live_circles(sc.tac, sc.t)) + [b["band"] for b in bands if b["own"]],
                             list(geo["bodies"].values()), roots, [b["root_iv"] for b in bands], (geo["xa"], geo["xb"]),
                             float(geo["left"]), float(geo["right"]), float(JT["pad"]))
    if rec is None:
        return x, None
    mem, slot = sc.mem.setdefault("lexit", {}), "side_" + which
    keys = [b["key"] for b in trig]
    side = next((mem[k][slot] for k in keys if mem.get(k, {}).get(slot) is not None), None)
    if side is not None:
        end = rec["ends"][0 if side < 0 else 1]           # the span's left / right end
        if not end["why"]:
            rec["exit"], rec["kept_side"] = end["x"], side
    if rec["exit"] is not None:
        for k in keys:
            mem.setdefault(k, {})[slot] = -1 if rec["exit"] == rec["ends"][0]["x"] else 1
    rec["bands"] = bands
    return (x if rec["exit"] is None else rec["exit"]), rec


def _apply_landing_exit(sc, g, out, how):
    """LANDING_EXIT on _apply's final output: (out, how) with only stance_x (and g.stance_x) and the StageWithdraw's stance_x moved; the
    record in tac.last["clapper_landing_exit"] (stance / withdraw / unknown, the waypoint and entry attack left as they are)."""
    bands, unknown = _landing_facts(sc)
    if unknown:
        sc.tac.last["clapper_landing_exit"] = dict(unknown=[list(u) for u in unknown], bands=bands)
        return out, how
    if not bands:
        return out, how
    x, rec = _landing_exit(sc, bands, float(out.stance_x), "stance")
    w = out.withdraw
    wx, wrec = _landing_exit(sc, bands, float(w.stance_x), "withdraw") if isinstance(w, StageWithdraw) else (None, None)
    if rec is not None and rec["exit"] is not None:
        out = replace(out, stance_x=float(x))
        g.stance_x = float(x)
        how = f"{how}; landing exit {rec['x0']:.2f}->{rec['exit']:.2f}"
    if wrec is not None and wrec["exit"] is not None:
        out = replace(out, withdraw=replace(w, stance_x=float(wx)))
    if rec is not None or wrec is not None:
        sc.tac.last["clapper_landing_exit"] = dict(
            stance=rec, withdraw=wrec, waypoint=None if out.waypoint is None else [float(out.waypoint.x), out.waypoint.kind],
            entry=None if out.entry_attack is None else [out.entry_attack.target, out.entry_attack.kind])
    return out, how


def plan_runner(tac):
    """SSBOT_FORUM_TWO_PLAN: this tactics object's runner (made once; the policy gives it its channel at startup)."""
    if tac.plan_runner is None:
        from .clapper_plans import PlanRunner
        tac.plan_runner = PlanRunner(tac)
    return tac.plan_runner


def enabled(fc):
    live = [s for s in fc.subjects if s.alive and s.in_play and s.pos is not None]
    return (len(live) == 2 and all(s.type_key == CLAPPER for s in live)
            and not (two_play.ASW or two_play.JUMPHIT or two_play.SP11B or two_play.RUNETIER or two_play.FLIPB)
            and os.environ.get("SSBOT_FORUM_CHAIN_ARM") == "B"
            and all(os.environ.get(k, "0").strip() == "1" for k in
                    ("SSBOT_FORUM_CHAIN_NATIVE", "SSBOT_FORUM_CHAIN_B2", "SSBOT_FORUM_CHAIN_AIR_MANUAL")))


def _pick(sc, caps):
    """One comparison of every applicable offer; returns (choices, winner, evaluation log)."""
    tac, keep = sc.tac, sc.keep
    choices, evals = [], []

    def offer(rule, target, applicability):
        cost = tac.rules.clapper_switch_cost if keep is not None and target.iid != keep.iid else 0.
        choices.append(dict(rule=rule, target=target.iid, maximum=caps[rule], applicability=applicability,
                            switch_cost=cost, score=caps[rule] * applicability - cost))

    tb = sc.table
    for tactic in tb.tactics:
        rec = {"tactic": tactic.name}
        blocked = [ev for ev in tactic.excluded_by if sc.events.get(ev) is not None]
        if blocked:
            rec["excluded_by"] = blocked
        else:
            offers, why = tactic.propose(sc)
            for rule, target, applicability in offers:
                offer(rule, target, applicability)
            if offers:
                rec["offers"] = [rule for rule, _, _ in offers]
            else:
                rec["not_applicable"] = why
        evals.append(rec)
    for owner in tb.tactics:
        if owner.owns_scene is not None and sc.events.get(owner.event) is not None:
            # an active scene owner: only its own rules and the ones it allows stay in the pool
            keep_rules = owner.owns_scene | owner.scores.keys()
            for rec in evals:
                if any(c["rule"] not in keep_rules and tb.rules[c["rule"]].name == rec["tactic"] for c in choices):
                    rec["filtered_by"] = owner.name
            choices[:] = [c for c in choices if c["rule"] in keep_rules]
    winner = max(choices, key=lambda c: (c["score"], keep is not None and c["target"] == keep.iid))
    return choices, winner, evals


def decide(tac, ws, fc, prefs, hx, t):
    """Observe every event, pick when due (one comparison of all offers), then apply the winner's outputs."""
    from .gauntlet import RUSH, TWO_SLAM_RANGE_U
    subjects = [s for s in fc.subjects if s.alive and s.in_play and s.pos is not None]
    mem = tac._clapper_priority
    tb = table()
    if mem is None:
        mem = tac._clapper_priority = {"seen": {}, "region": None}
        for tactic in tb.tactics:
            mem.update(tactic.memory)
    geo = geometry(tac, ws, subjects)
    region = None if geo is None else geo["region"]
    sc = Scene(tac, ws, fc, prefs, hx, t, subjects, mem, geo, region)
    SEP.NOW_F = sc.frame                    # Task 182 seq 312: the frame its offline A/B start (SSBOT_FORUM_SEP312_FROM) is read against
    sc.table = tb
    if tb is not LEGACY_TABLE:
        sc.plans = plan_runner(tac)
    for tactic in tb.observe:
        sc.events[tactic.event] = tactic.observe(sc)
    sc.seen = {s.iid: (s.family, s.state, abs(s.pos[0] - hx) <= TWO_SLAM_RANGE_U,
                       tac.t_commit.get(s.iid)) for s in subjects}
    old = tac.goal
    sc.keep = keep = next((s for s in subjects if old is not None and s.iid == old.target), None)
    asked = [tactic.repick(sc) for tactic in tb.tactics]
    changed = sc.seen != mem["seen"] or region != mem["region"] or any(asked)
    if keep is None or changed or tac.n % tac.rules.period == 0:
        triggers = ((["no focus"] if keep is None else []) + (["subjects changed"] if sc.seen != mem["seen"] else [])
                    + (["region changed"] if region != mem["region"] else [])
                    + [tactic.name + " asked" for tactic, ask in zip(tb.tactics, asked) if ask]
                    + (["period"] if tac.n % tac.rules.period == 0 else []))
        sc.cands = cands = tac.candidates(ws, fc, hx, None if keep is None else keep.iid)
        sc.by_id = {c.s.iid: c for c in cands}
        a, b = cands
        sc.room = room = {a.s.iid: tac._outer_room(a, b), b.s.iid: tac._outer_room(b, a)}
        sc.default = (stacked_nearer(sc) or keep
                      or (min(subjects, key=lambda s: (abs(s.pos[0] - hx), s.iid)) if region in {"left", "right", "over"}
                          else max(subjects, key=lambda s: (room[s.iid], -abs(s.pos[0] - hx), -s.iid))))
        sc.other = next(s for s in subjects if s.iid != sc.default.iid)
        choices, winner, evals = _pick(sc, tb.scores | tac.rules.clapper_scores)
        target = sc.subject(winner["target"])
        reason = winner["rule"]
        won = tb.rules[reason]
        mem["winner"] = reason
        won.commit(sc, reason, target)
        for tactic in tb.tactics:
            tactic.release(sc, reason, target)
        tac.last["clapper_choices"] = choices
        tac.last["clapper_winner"] = dict(winner)
        tac.last["clapper_eval"] = {"triggers": triggers, "tactics": evals, "winner": dict(winner, tactic=won.name)}
        goal = tac._goal(ws, sc.by_id[target.iid], RUSH, t, winner["score"], why="two manual: " + reason)
        if old is not None and old.target == target.iid:
            goal.t_pick, goal.t_goal, goal.landed, goal.entry_attack = old.t_pick, old.t_goal, old.landed, old.entry_attack
        elif keep is not None and won.switch_entry:
            goal.entry_attack, _ = entry(tac, ws, fc, keep, target, t, geo)
        goal.entry_attack = won.pick_entry(sc, reason, target, goal.entry_attack)
        if old is None or old.target != target.iid or old.name != RUSH:
            tac.stats["changes"] += 1
            if old is not None and old.target != target.iid:
                tac.stats["tgt_switches"] += 1
                tac.stats["switches"] += int(keep is not None)
                sk = tac.stats["switch_kinds"]; sk[reason] = sk.get(reason, 0) + 1
        tac.stats["picks"] += 1
        tac.goal = goal
    mem["seen"], mem["region"] = sc.seen, region
    return _apply(sc, tb.rules[mem["winner"]], mem["winner"])


def _apply(sc, won, rule):
    """Every tick: the shared stance / contact constraints, then the winner's own outputs (Applied, finish) and every
    event's aftermath (finish)."""
    from .gauntlet import RUSH
    tac, ws, fc, prefs, hx, t, geo, subjects = sc.tac, sc.ws, sc.fc, sc.prefs, sc.hx, sc.t, sc.geo, sc.subjects
    g = tac.goal
    target = sc.subject(g.target)
    g.stance_x, g.vocab, how = tac._spot(ws, target, hx)
    g.face_x = float(target.pos[0])
    style = None
    if g.entry_attack is not None:
        age = t - g.entry_attack.picked_at
        if not 0 <= age < 2. or (g.entry_attack.kind == "side" and target.family in JUMPS | {"CC_SLAM"}):
            g.entry_attack = None
        else: style = g.entry_attack.kind
    if target.family in JUMPS and target.state not in AIR and target.state in ANTIC:
        g.stance_x = tac._clamp(target.pos[0] + (-1 if hx < target.pos[0] else 1) * tac.rules.face_u)
        how = "face: hold until takeoff"
    own_x = float(g.stance_x)                   # L2's own stance, before the winner's stage overrides it (Sol seq 272 B)
    ap = won.apply(sc, rule, g, target) or Applied()
    if ap.stance is not None:
        g.stance_x = ap.stance
    elif g.entry_attack is not None and style == "side":
        stand = ground_stance(tac, target, hx, geo)
        if stand is not None: g.stance_x = stand
    if ap.style is not KEEP:
        style = ap.style
    if ap.scene is not None:
        sc.scene = ap.scene
    weights = dict(prefs.weights)
    if prefs.mode == EVADE:
        weights["hit"] /= EVADE_HIT_X; weights["risk"] /= EVADE_RISK_X
    for k, v in (tac.rules.weights.get(RUSH) or {}).items(): weights[k] = weights.get(k, 0.) * float(v)
    hw = {iid: min(w, tac.local.rules.other_hit_w) if w > 0 and iid != g.target else w for iid, w in prefs.hit_w.items()}
    hw[g.target] = max(hw.get(g.target, 0.), tac.rules.target_hit_w * tac.rules.priority.get(CLAPPER, 1.))
    out = replace(prefs, mode=RUSH, goal=RUSH, target=g.target, stance_x=float(g.stance_x), boss_x=g.face_x,
                  weights=weights, hit_w=hw, entry_attack=g.entry_attack, clapper_choice=rule,
                  vocab=frozenset(prefs.vocab) | g.vocab, return_cross=frozenset(), withdraw=None, stay_pogo=frozenset(),
                  hold_over=frozenset(), strike_bound=None, hook_open=None)
    pre = None                                  # the preferences before the strike's own weights (Sol seq 272 B)
    if ap.suppress_hits or (target.family in JUMPS and target.state in AIR):
        # no hit while backing off (the winner's suppression), and never on a target in its jump's flight
        out = replace(out, no_hit=frozenset(out.no_hit) | ({s.iid for s in subjects} if ap.suppress_hits else {g.target}),
                      entry_attack=None)
    else:
        out = tac._contact_preferences(fc, out, g, target, hx, how)
        pre = out
        out = entry_attack_prefs(out)
        if style == "stomp":
            kw = dict(out.hit_kw); kw[g.target] = (0., 0., 0., hw[g.target])
            out = replace(out, hit_kw=kw, ground_hit=frozenset(out.ground_hit) - {g.target},
                          no_pogo=frozenset(out.no_pogo) - {g.target}, ground_first=frozenset(out.ground_first) - {g.target})
        if ap.down_ok:
            # Task 182 seq 280: the stage's own no_hit on its target gives way to that target's down slash only; a ban from
            # any other source (every earlier one is in out.no_hit, before the stage's own is merged) keeps it
            out = replace(out, stay_pogo=frozenset(ap.down_ok) - frozenset(out.no_hit))
        if ap.no_hit:
            # Task 183 seq 267: the middle return's crossed body (Applied.cross_no_hit) is recorded apart when no other
            # source bans it (every earlier one is in out.no_hit, the winner's own others in ap.no_hit; nothing after
            # this adds to no_hit); the merged no_hit is as before
            others = frozenset(out.no_hit) | (frozenset(ap.no_hit) - frozenset(ap.cross_no_hit))
            out = replace(out, no_hit=frozenset(out.no_hit) | ap.no_hit, return_cross=frozenset(ap.cross_no_hit) - others)
    if tac.ta: out, _ = tac._ta_rules(ws, fc, out, g, target, hx)
    if SEP.active():
        out = replace(out, blocked=SEP.blocked_iids(sc))      # Task 182 seq 312: the shared fact every key owner reads
    for tactic in sc.table.tactics:
        out = tactic.finish(sc, rule, tactic is won, g, out)
    e = out.entry_attack
    if (getattr(ap, "withdraw_f", None) is not None and pre is not None and isinstance(e, EntryAttack) and e.kind == "stomp"
            and e.target == g.target):
        # Sol seq 272 B: the over_head stage's stance and stomp stand for the action layer's strike; the planner takes them back
        # for its ordinary rows on the tick that strike is refused, and on the later ticks of this stage
        tg = g.target
        out = replace(out, withdraw=StageWithdraw(own_x, (tg, e.kind, e.source), int(ap.withdraw_f), pre.hit_kw.get(tg),
                                                  (tg in pre.ground_hit, tg in pre.no_pogo, tg in pre.ground_first)))
    if RUNE_EXIT_FINAL:
        # the final stance (every stage, finish and withdraw above) out of the live big rune circles (RUNE_EXIT_FINAL's note)
        x, rec = _rune_exit(sc, float(out.stance_x))
        w = out.withdraw
        wx, wrec = _rune_exit(sc, float(w.stance_x)) if isinstance(w, StageWithdraw) else (None, None)
        if rec is not None and rec["exit"] is not None:
            out = replace(out, stance_x=float(x))
            g.stance_x = float(x)
            how = f"{how}; rune exit {rec['x0']:.2f}->{rec['exit']:.2f}"
        if wrec is not None and wrec["exit"] is not None:
            out = replace(out, withdraw=replace(w, stance_x=float(wx)))
        if rec is not None or wrec is not None:
            tac.last["clapper_rune_exit"] = dict(stance=rec, withdraw=wrec)
    if LANDING_EXIT:
        # the final stance and withdraw out of another Clapper's committed landing hammer (LANDING_EXIT's note), after the rune exit and
        # jointly with its live circles
        out, how = _apply_landing_exit(sc, g, out, how)
    g.why = g.why.split("; ")[0] + "; " + sc.scene + "; " + str(how)
    logs = {}
    for tactic in sc.table.tactics:
        logs.update(tactic.log(sc, out))
    tac.last.update(goal=RUSH, goal_why=g.why, target_type=CLAPPER, goal_t_end=None,
                    entry_attack=None if out.entry_attack is None else vars(out.entry_attack),
                    clapper_scene=sc.scene, clapper_region=sc.region, **logs, clapper_return_body=out.return_body)
    tac.stats["goals"][RUSH] = tac.stats["goals"].get(RUSH, 0) + 1
    return out
