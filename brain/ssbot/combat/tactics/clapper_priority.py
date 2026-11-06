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

from .clapper_scene import (AIR, ANTIC, JUMPS, NEAR, Scene, entry, geometry, ground_stance,  # noqa: F401
                            standing_gap)
from .clapper_tactics import (BAIT_WIDTHS, DEFAULT_SCORES, KEEP, LEGACY_TABLE, OBSERVE, RETURN_LANDED_S, RULES,  # noqa: F401
                              TACTICS, Applied, cluster_route, middle_return, return_pose, table)
from .forum_local import CLAPPER, EVADE_HIT_X, EVADE_RISK_X
from .modes import EVADE, entry_attack_prefs


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
        sc.default = (keep or (min(subjects, key=lambda s: abs(s.pos[0] - hx)) if region in {"left", "right", "over"}
                               else max(subjects, key=lambda s: (room[s.iid], -abs(s.pos[0] - hx)))))
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
                  vocab=frozenset(prefs.vocab) | g.vocab)
    if ap.suppress_hits or (target.family in JUMPS and target.state in AIR):
        # no hit while backing off (the winner's suppression), and never on a target in its jump's flight
        out = replace(out, no_hit=frozenset(out.no_hit) | ({s.iid for s in subjects} if ap.suppress_hits else {g.target}),
                      entry_attack=None)
    else:
        out = tac._contact_preferences(fc, out, g, target, hx, how)
        out = entry_attack_prefs(out)
        if style == "stomp":
            kw = dict(out.hit_kw); kw[g.target] = (0., 0., 0., hw[g.target])
            out = replace(out, hit_kw=kw, ground_hit=frozenset(out.ground_hit) - {g.target},
                          no_pogo=frozenset(out.no_pogo) - {g.target}, ground_first=frozenset(out.ground_first) - {g.target})
        if ap.no_hit:
            out = replace(out, no_hit=frozenset(out.no_hit) | ap.no_hit)
    if tac.ta: out, _ = tac._ta_rules(ws, fc, out, g, target, hx)
    for tactic in sc.table.tactics:
        out = tactic.finish(sc, rule, tactic is won, g, out)
    g.why = g.why.split("; ")[0] + "; " + sc.scene + "; " + str(how)
    logs = {}
    for tactic in sc.table.tactics:
        logs.update(tactic.log(sc, out))
    tac.last.update(goal=RUSH, goal_why=g.why, target_type=CLAPPER, goal_t_end=None,
                    entry_attack=None if out.entry_attack is None else vars(out.entry_attack),
                    clapper_scene=sc.scene, clapper_region=sc.region, **logs, clapper_return_body=out.return_body)
    tac.stats["goals"][RUSH] = tac.stats["goals"].get(RUSH, 0) + 1
    return out
