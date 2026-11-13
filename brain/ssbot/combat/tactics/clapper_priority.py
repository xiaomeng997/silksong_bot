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
    g.why = g.why.split("; ")[0] + "; " + sc.scene + "; " + str(how)
    logs = {}
    for tactic in sc.table.tactics:
        logs.update(tactic.log(sc, out))
    tac.last.update(goal=RUSH, goal_why=g.why, target_type=CLAPPER, goal_t_end=None,
                    entry_attack=None if out.entry_attack is None else vars(out.entry_attack),
                    clapper_scene=sc.scene, clapper_region=sc.region, **logs, clapper_return_body=out.return_body)
    tac.stats["goals"][RUSH] = tac.stats["goals"].get(RUSH, 0) + 1
    return out
