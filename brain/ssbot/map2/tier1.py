"""Map v2, t1 workflow stage S2: THE PER-FRAME TIER 1 (docs/plans/forum_map_v2.md 3.4.8b 'two tiers'; HANDOFF 'Task map2 -
fix together (t1) - stage S2 (tier 1)'). Behind LiveCfg.tier1 (default off: nothing here runs, the bot and the search as
before). Offline code and the tier-1 worker's decision; the controller's side is in live.py (Map2Controller._t1_*).

WHY (the live w7 audit of 2026-10-25): map2's plans ended at their contact / the hook's control with nothing committed
after them and handed the keys to the old planner while it had no safe option; it failed there in three repeating ways.
The person's decision (2026-10-25 ~07:10 PDT): map2 never hands the keys to the old planner in danger - a per-frame tier
1 that ALWAYS outputs keys; the deep search (tier 2) runs on and its committed plan wins while it has one.

ONE TIER-1 DECISION (t1_decide; <= 1 event, ~60 frames, from the newest observed state - the keys in flight and a short
bridge of tier 1's own plan as the root's prefix, as every search root):
  1. the root: the Clappers predicted under her prefix (the compiled predict: 0.6 ms p50 on rec w7) and every branch's
     danger arrays (fast_danger: 1.8 ms p50) - built once per decision, shared by every candidate below;
  2. CONT: the plan tier 1 is playing, re-anchored after the prefix - re-checked first (the hysteresis: a new plan must
     beat it by Cfg.w_switch);
  3. ESCAPES: the exit probes (search._probe_masks: her held keys kept / left / right, a jump, a dash - each held h
     frames) after the prefix, screened OPEN-LOOP against the root's prediction (one trajectory, every branch's timing
     views: the probability of a collision before that branch's reveal + lag, its frame) - the safest n_esc evaluated in
     closed loop with their exits (the deep search's exact evaluation);
  4. STRIKES: the 1-event 60-frame envelope pass (the A1_n tables), the windows of every primitive in Cfg.prims (S1's side
     / up slash, the down slash, the Clawline), realized and evaluated in closed loop (the quick screen first), round
     robin over (primitive, Clapper) as the deep search's depth 1, plus the pass's safe endpoints - until the cap;
  5. THE CHOICE: the best proven-safe plan (every outcome safe, its exits checked) by value; none -> THE LEAST-RISK plan
     (risk_key: the fewest expected hits - the probability of an outcome colliding before its reveal + lag -, then the
     latest such collision, then the fewest outcomes without an exit, then the open value) - tier 1 always answers with
     keys. A least-risk plan that only had the open-loop screen is evaluated in closed loop before it is returned.
The worker (live.worker_main, role 't1') answers every snapshot with such a plan (LivePlan.t1); the bot's thread plays
the newest one whose prefix it followed, every tick, whenever tier 2 has no plan in control - no commit check (the plan
was searched from her observed state with the keys actually sent as its prefix: 3.4.8b).

'TIER 1 ALONE' ON THE ACCEPTANCE (t1_chain): the same decision at the situation, then - where its chosen plan landed a
strike / hook and so ends at a branch point (the deep search's node: the pogo's bounce, the hook's control, one node
per reaction to a hook) - the same depth-1 decision again FROM THAT NODE (the state tier 1 would re-plan from there),
greedily, up to `steps` decisions; the per-reaction continuations joined into one contingent plan (search._combine) and
classified by the move recognizers. A move found only with a deep (multi-event) commitment shows up as found by the deep
search and not here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk


@dataclass
class T1Result:
    ev: object                   # the chosen plan's Eval (search.Eval)
    safe: bool                   # proven safe (every outcome safe, exits checked)
    kind: str                    # 'cont' / 'esc' / 'strike' / 'endpoint'
    risk: tuple                  # risk_key of the chosen plan
    tried: list
    n_cand: int
    ms: float
    stats: dict = field(default_factory=dict)
    kinds: dict = field(default_factory=dict)    # id(Eval) -> kind


def risk_key(e) -> tuple:
    """The least-risk order of an evaluated plan (smaller is better): (p of the outcomes colliding before their reveal +
    lag - 'hit@' / a bad press 'press@' -, minus the p-weighted mean frame of those collisions (later is better), p of the
    other unsafe outcomes - no exit / unchecked -, minus the open value)."""
    outs = getattr(e, "outcomes", None) or ()
    if not outs:
        return (1.0, 0.0, 1.0, 1.0)
    ph = kh = pe = 0.0
    for o in outs:
        w = str(o.why or "")
        if w.startswith(("hit@", "press@")):
            ph += o.p
            try:
                kh += o.p * int(w.split("@")[1])
            except ValueError:
                pass
        elif not o.safe:
            pe += o.p
    kmean = kh / ph if ph > 0 else 999.0
    return (round(ph, 4), -round(kmean, 2), round(pe, 4), -round(float(e.value_open), 4))


def _rv(b) -> int | None:
    rv = ms._reveal(b, 1)
    tv = getattr(b, "t_reveal", None)
    if tv is not None and tv >= 1:
        rv = tv if rv is None else min(rv, tv)
    return rv


def open_risk(S: ms.Searcher, sit: ms.Situation, plan: ms.Plan, pred, face0: int) -> tuple:
    """A plan without a strike of its own simulated once and checked against every branch view of the root's prediction
    (no re-prediction): (p colliding before the branch's reveal + lag, minus the mean such collision frame, minus the
    frames to the first collision of any kind - the room). Cheap: the escapes' open-loop screen."""
    tr = S.ev.sim(sit, plan, sk.HOOK_VARIANTS[0], face0)
    ptot = sum(b.p for b in pred.branches) or 1.0
    ph = kh = 0.0
    kfirst = 10 ** 6
    for b0 in pred.branches:
        vws = ms.timing_views(b0)
        for b in vws:
            k = ms.first_collision(b, tr, 1, min(tr.end, pred.T), S.cfg.margins)
            kx = ms.bad_frame(tr, 1, tr.end)
            if kx is not None and (k is None or kx < k):
                k = kx
            if k is None:
                continue
            kfirst = min(kfirst, k)
            rv = _rv(b)
            if rv is None or k < rv + S.cfg.lag:
                w = b0.p / ptot / len(vws)
                ph += w
                kh += w * k
    kmean = kh / ph if ph > 0 else 999.0
    return (round(ph, 4), -round(kmean, 2), -min(kfirst, 999))


def _away_rank(masks: np.ndarray, S: np.ndarray, sit) -> list:
    """The escapes' tie order (search._baseline's): away from the nearest Clapper first, then no direction, then toward
    it; the held keys, a dash, a jump."""
    x = float(S[km.PX])
    cxs = [float(o.x) for o in sit.obs]
    away = 0
    if cxs:
        near = min(cxs, key=lambda c: abs(c - x))
        away = 1 if x >= near else -1

    def rank(i):
        m = int(masks[i, 0])
        d = 1 if m & km.B_RIGHT else (-1 if m & km.B_LEFT else 0)
        return (0 if (d == away and d != 0) else 1 if d == 0 else 2, bool(m & km.B_DASH), bool(m & km.B_JUMP))
    return sorted(range(len(masks)), key=rank)


def _prefix_dev(S: ms.Searcher, e, n_pre: int) -> None:
    """THE PREFIX IS COMMITTED: the keys in flight and the bridge are played whatever the Clappers reveal, so an outcome
    the reveal rule lets deviate before the prefix's end (its reveal + lag inside it, a collision after) cannot: its
    collision before the prefix's end + lag makes it unsafe ('hit@'), else its deviation moves to the prefix's end and
    its exit is checked from there (pending: finish() runs it). The evaluation's other outcomes are unchanged."""
    if n_pre <= 0 or not e.outcomes:
        return
    ch = False
    for o in e.outcomes:
        ke = int(getattr(o, "k_end", o.tr.end))
        if not (o.safe or getattr(o, "pending", False)) or ke >= int(o.tr.end) or ke >= n_pre:
            continue
        kc = o.k_col
        ch = True
        if kc is not None and int(kc) <= n_pre + int(S.cfg.lag):
            o.safe, o.why, o.value, o.pending = False, f"hit@{int(kc)}", -1.0, False
        else:
            o.k_end, o.dev, o.pending = int(n_pre), int(n_pre), True
            o.safe = True
    if ch:
        e.value = sum(o.p * o.value for o in e.outcomes)
        e.p_safe = sum(o.p for o in e.outcomes if o.safe)
        e.open_ok = all(ms._open(o) for o in e.outcomes)
        e.finished = not any(getattr(o, "pending", False) for o in e.outcomes)
        e.safe = all(o.safe for o in e.outcomes) and e.finished
        S.stats["prefix_dev"] = S.stats.get("prefix_dev", 0) + 1


def _better(a, b) -> bool:
    if b is None:
        return True
    if a.safe != b.safe:
        return a.safe
    if not a.safe:
        return risk_key(a) < risk_key(b)
    return a.value > b.value


def _node_decide(S: ms.Searcher, sit: ms.Situation, node, cap: float, t0c: float, *, prev=None, n_esc: int = 2,
                 h: int = 60, stats: dict, kinds: dict, tried: list, n_cand: list, esc: bool = True,
                 root: bool = True, n_pre: int = 0) -> object:
    """The depth-1 decision from one node (the root, or a node after a landed strike): CONT, the escapes, the strikes /
    endpoints of the node's 1-event pass, until the cap - the best safe Eval, else the least-risk one (None: nothing)."""
    cfg = S.cfg
    now = S._now
    until = (lambda: now() - t0c > cap)
    S._until = until
    face0 = int(sit.S[km.FACE]) if sit.S[km.FACE] != 0 else 1
    tagged = bool(node.tag)
    best = [None]
    cont = [None]
    mine: list = []

    def take(e, kind):
        if e is None:
            return None
        tried.append(e)
        mine.append(e)
        kinds[id(e)] = kind
        n_cand[0] += 1
        if tagged:
            return e                                    # (a reaction's node: chosen below by its conditional value)
        if root and n_pre > 0:
            _prefix_dev(S, e, n_pre)
        if not e.finished and e.open_ok and (best[0] is None or not best[0].safe or
                                             e.value_open > best[0].value + 1e-9):
            # (the first plan's exits run to their end whatever the cap: a decision has one checked answer at least)
            S.ev.finish(e, until=until if best[0] is not None else None)
        if (e.finished or e.outcomes) and _better(e, best[0]):
            best[0] = e
        return e
    t_mark = time.perf_counter()

    def mark(k):
        nonlocal t_mark
        t_ = time.perf_counter()
        stats[k] = round(stats.get(k, 0.0) + (t_ - t_mark) * 1e3, 2)
        t_mark = t_
    if prev is not None:
        e = S.ev.evaluate(sit, prev, exits=False, tag=node.tag, start=node.start, until=until)
        if e is not None:
            e.tag = node.tag
            cont[0] = take(e, "cont")
    mark("ms_cont")
    # the escapes: open-loop screen (at the root: one trajectory against the root's prediction); the safest one in
    # closed loop now only when CONT is not a safe plan (else after the strikes, when no safe plan is in hand)
    esc_l = []
    n_esc_done = 0
    if esc:
        Sn = np.asarray(node.S, float)
        masks = ms._probe_masks(Sn, int(h))
        order = _away_rank(masks, Sn, sit)
        after_claw = bool(node.plan.segs) and node.plan.segs[-1].claw is not None
        for j, i in enumerate(order):
            sg = ms.Seg(masks[i].copy(), [], None, "base")
            pl = S._merge(node, S._after_claw(sg) if after_claw else sg, "base")
            rk = open_risk(S, sit, pl, node.pred, face0) if (root and not tagged) else (0.0, 0.0, 0)
            esc_l.append((rk, j, pl))
        esc_l.sort(key=lambda t: (t[0], t[1]))
        stats["esc_open_safe"] = stats.get("esc_open_safe", 0) + sum(1 for t in esc_l if t[0][0] <= 0.0)

    def escapes(n_max):
        nonlocal n_esc_done
        while n_esc_done < min(len(esc_l), n_max):
            rk, j, pl = esc_l[n_esc_done]
            if best[0] is not None and best[0].safe and rk[0] > 0.0:
                break                                   # a safe plan is in hand: an escape that collides cannot beat it
            if n_cand[0] > 0 and until():
                break
            n_esc_done += 1
            e = S.ev.evaluate(sit, pl, exits=False, tag=node.tag, start=node.start, until=until)
            if e is None:
                break
            e.tag = node.tag
            take(e, "esc")
    if esc_l and (tagged or best[0] is None or not best[0].safe):
        escapes(1)
    mark("ms_esc")
    # the strikes and endpoints of the node's 1-event pass
    if not until():
        fws = S.passes(node, (0,))
        cs = []
        for fw in fws:
            ws = S.windows(node, fw)
            for c in ws:
                stats[f"win_{c[0]}"] = stats.get(f"win_{c[0]}", 0) + 1
            cs += [(fw, c) for c in ws]
        mark("ms_pass")
        groups: dict = {}
        for fc in cs:
            groups.setdefault((fc[1][0], fc[1][5]), []).append(fc)
        # ANYTIME ACROSS DECISIONS: the round robin over (primitive, Clapper) starts one group later each decision and
        # each group a window later every full turn (S._t1_rot) - successive decisions re-planned from nearly the same
        # state cover different windows instead of the same first few under the cap
        rot = int(getattr(S, "_t1_rot", 0))
        gl = list(groups.values())
        if gl:
            k_ = rot % len(gl)
            gl = gl[k_:] + gl[:k_]
            sh = rot // len(gl)
            gl = [g[sh % len(g):] + g[:sh % len(g)] for g in gl]
        rr = [g[i] for i in range(max((len(g) for g in gl), default=0)) for g in gl if i < len(g)]
        # (the pass's safe endpoints after the strikes: the escapes stand for them - evaluated first they cost a
        # decision two closed-loop evaluations that rarely beat CONT or an escape)
        queue = rr + ([(fws[0], c) for c in S.safe_cands(node, fws[0])][:2] if fws else [])
        for fw, c in queue:
            if until():
                stats["capped"] = stats.get("capped", 0) + 1
                break
            seg = S.realize(node, fw, c) if c[0] != "safe" else S.realize_safe(fw, c)
            if seg is None:
                continue
            plan, e = S.child(sit, node, seg, "prim" if c[0] != "safe" else "safe", c)
            e.tag = node.tag
            take(e, "strike" if c[0] != "safe" else "endpoint")
            stats["n_strike_eval"] = stats.get("n_strike_eval", 0) + (c[0] != "safe")
        mark("ms_strikes")
    # no safe plan yet: more escapes in closed loop
    if esc_l and (tagged or best[0] is None or not best[0].safe):
        escapes(max(1, int(n_esc)))
        mark("ms_esc2")
    if tagged:
        # a reaction's node (t1_chain): its continuations judged in that reaction's outcomes - the best open one whose
        # exits pass (search._gval), up to 3 tried; else the least-risk
        sc = []
        for e in mine:
            g = S._gval(e, node.tag, finish=False)
            if g is not None and g[0]:
                sc.append((g[1], e))
        for _, e in sorted(sc, key=lambda t: -t[0])[:3]:
            g = S._gval(e, node.tag, finish=True)
            if g is not None and g[0]:
                e.t1_safe = True
                return e
        return min(mine, key=risk_key) if mine else None
    # nothing evaluated in closed loop at all (a cap shorter than the root): the safest escape after all
    if best[0] is None and esc_l:
        e = S.ev.evaluate(sit, esc_l[0][2], exits=False, tag=node.tag, start=node.start)
        if e is not None:
            e.tag = node.tag
            take(e, "esc")                              # (its exits run whatever the cap: the first plan)
    b = best[0]
    c = cont[0]
    if b is not None and c is not None and b is not c and b.safe and c.safe and b.value < c.value + cfg.w_switch:
        b = c                                           # the hysteresis
    return b


def t1_decide(S: ms.Searcher, sit: ms.Situation, prefix: ms.Seg | None = None, prev=None, cap: float = 0.06,
              n_esc: int = 2, h: int = 60) -> T1Result:
    """ONE TIER-1 DECISION (module docstring). S: a Searcher with the tier-1 configuration (t1_cfg: depth 1, the
    1-event 60-frame pass) and, live, the hold filter's realizer; prefix: the keys in flight + the bridge; prev: the
    plan tier 1 is playing, re-anchored after the prefix (live.reanchor_prev). Always a result with an Eval when the
    root could be evaluated."""
    t0 = time.perf_counter()
    cfg = S.cfg
    S.ev.n_pred = S.ev.n_exit = 0
    S.ev.units = 0
    S.ev.reset()
    S._stop_bg()
    if cfg.tables:
        lib = S.W.table_lib(cfg.tables_file, cfg.tables_budget)
        if lib is not None and cfg.tables_budget > 0 and lib.grown() > cfg.tables_budget:
            lib.reset()
    S.stats = {}
    S.splits = {}
    stats: dict = {}
    kinds: dict = {}
    tried: list = []
    n_cand = [0]
    t0c = S._now()
    try:
        rt = S.root(sit) if prefix is None else S.root(sit, prefix)
        stats["root_ms"] = round((time.perf_counter() - t0) * 1e3, 2)
        b = _node_decide(S, sit, rt, cap, t0c, prev=prev, n_esc=n_esc, h=h, stats=stats, kinds=kinds, tried=tried,
                         n_cand=n_cand, n_pre=0 if prefix is None else len(prefix.masks))
    finally:
        S._stop_bg()
        S._until = None
        S._t1_rot = int(getattr(S, "_t1_rot", 0)) + 1
    if b is not None and not b.finished:
        S.ev.finish(b)                                  # (a least-risk plan whose exits were not run)
    stats.update({k: v for k, v in S.stats.items() if isinstance(v, (int, float))})
    ms_ = (time.perf_counter() - t0) * 1e3
    return T1Result(b, bool(b is not None and b.safe), kinds.get(id(b), "") if b is not None else "",
                    risk_key(b) if b is not None else (1.0, 0.0, 1.0, 1.0), tried, n_cand[0], ms_, stats, kinds)


def t1_tail(S: ms.Searcher, sit: ms.Situation, e, H: int = 40, n_min: int = 0) -> tuple:
    """THE ESCAPE TAIL (the person's decision (a), 2026-10-25: a committed plan never ends at a contact / a hook's
    control with nothing after it): the plan's own exit appended as its committed tail - the exit probes (search.
    _probe_masks: the exit check's own first test) from the state at the plan's end, away from the nearest Clapper
    first. COMMON: one probe appended to the plan itself (after a Clawline: a segment anchored at its control, every
    hook variant), the extended plan re-realized (the hold filter) and re-simulated in every safe outcome that ends at
    the plan's end - kept only when every one keeps its strikes and path to the end and touches no danger of its branch
    (margins on) through the tail. DEV: the outcomes whose committed part ends at a deviation (a collision follows after
    their reveal + lag), grouped by that frame: the plan cut there and one probe appended, re-realized and re-simulated in
    each of them the same way - kept outcomes replace theirs (a plan of one segment without a Clawline; not inside the
    prefix, not from a state mid-swing / mid-bounce).
    n_min: the plan's own keys start there (the prefix before it is played whatever happens): no dev tail before it.
    -> (the Eval with the common tail's outcomes - or e itself -, {id(outcome): (k0, masks, pos)} the dev tails)."""
    import copy as _copy
    import dataclasses as _dc
    W, cfg = S.W, S.cfg
    face0 = int(sit.S[km.FACE]) if sit.S[km.FACE] != 0 else 1
    outs = list(e.outcomes)
    nd = [o for o in outs if o.safe and int(getattr(o, "k_end", o.tr.end)) == int(o.tr.end)]
    dev = [o for o in outs if o.safe and int(getattr(o, "k_end", o.tr.end)) < int(o.tr.end)]
    e_ext = e
    if nd:
        o0 = max(nd, key=lambda o: o.p)
        st = ms.state_at(W, o0.tr, int(o0.tr.end))
        if st is not None:
            masks = ms._probe_masks(st[0], int(H))
            for i in _away_rank(masks, st[0], sit):
                segs = [s.copy() for s in e.plan.segs]
                sg = ms.Seg(masks[i].copy(), [], None, "tail")
                if segs and segs[-1].claw is None:
                    last = segs[-1]
                    last.masks = np.concatenate([last.masks, sg.masks])
                    last.tag = (last.tag + "+tail").strip("+")
                else:
                    segs.append(S._after_claw(sg))
                pe = ms.Plan(segs, e.plan.origin, (e.plan.note + " tail").strip())
                if S.realizer is not None:
                    pe = S.realizer(pe)
                new, ok = [], True
                for o in nd:
                    T = int(getattr(getattr(o, "P", None), "T", None) or e.pred.T)
                    var = next((v for v in sk.HOOK_VARIANTS if v.name == o.tr.variant), sk.HOOK_VARIANTS[0])
                    tr = S.ev.sim(sit, pe, var, face0, o.branch, T, cfg.lag)
                    k0 = int(o.tr.end)
                    same = (len(tr.pos) > k0 and sorted(tr.contacts) == sorted(o.tr.contacts) and
                            np.allclose(tr.pos[:k0 + 1], o.tr.pos[:k0 + 1], atol=1e-9))
                    if not same:
                        ok = False
                        break
                    k1 = min(int(tr.end), T)
                    kc = ms.first_collision(o.branch, tr, k0 + 1, k1, cfg.margins) if k1 > k0 else None
                    kx = ms.bad_frame(tr, k0 + 1, int(tr.end))
                    if kc is not None or kx is not None:
                        ok = False
                        break
                    o2 = _dc.replace(o, tr=tr)
                    for k_, v_ in o.__dict__.items():
                        if k_ not in ("tr",) and k_ not in {f.name for f in _dc.fields(o)}:
                            o2.__dict__[k_] = v_
                    o2.k_end = int(tr.end)
                    new.append((o, o2))
                if ok:
                    rep = {id(a): b for (a, b) in new}
                    e_ext = _copy.copy(e)
                    e_ext.plan = pe
                    e_ext.outcomes = [rep.get(id(o), o) for o in outs]
                    e_ext.nominal = rep.get(id(e.nominal), e.nominal) if e.nominal is not None else None
                    e_ext.t1_tail = int(i)
                    break
    # DEV: the outcomes that must deviate (grouped by their deviation frame): the plan cut there and one probe
    # appended, re-realized and re-simulated exactly in each of them (as the common tail) - plans of one segment
    # without a Clawline only; the outcomes so tailed replace theirs (their own keys and path from the deviation on)
    dev_tails = {}
    by_k: dict = {}
    for o in dev:
        by_k.setdefault(int(o.k_end), []).append(o)
    one_seg = len(e.plan.segs) == 1 and e.plan.segs[0].claw is None
    rep_dev = {}
    for k0, grp in sorted(by_k.items()):
        if k0 < int(n_min) or not one_seg:
            continue
        o0 = max(grp, key=lambda o: o.p)
        st = ms.state_at(W, o0.tr, k0)
        if st is None:
            continue
        Sk = np.asarray(st[0], float).reshape(km.K, -1)[:, 0]
        if Sk[km.ATTACKING] > 0 or Sk[km.BOUNCE] >= 0:
            # (mid-swing / mid-bounce at the deviation: no tail there - b0fffa1's smokes)
            continue
        seg0 = e.plan.segs[0]
        if k0 > len(seg0.masks):
            continue
        masks = ms._probe_masks(st[0], int(H))
        for i in _away_rank(masks, st[0], sit):
            sg = ms.Seg(np.concatenate([np.asarray(seg0.masks[:k0], np.int64), masks[i]]).astype(np.int64),
                        [(j, iid) for (j, iid) in seg0.dsl if j < k0], None, (seg0.tag + "+dtail").strip("+"))
            pe = ms.Plan([sg], e.plan.origin, (e.plan.note + " dtail").strip())
            if S.realizer is not None:
                pe = S.realizer(pe)
            new, ok = [], True
            for o in grp:
                T = int(getattr(getattr(o, "P", None), "T", None) or e.pred.T)
                var = next((v for v in sk.HOOK_VARIANTS if v.name == o.tr.variant), sk.HOOK_VARIANTS[0])
                tr = S.ev.sim(sit, pe, var, face0, o.branch, T, cfg.lag)
                same = (len(tr.pos) > k0 and
                        sorted(c for c in tr.contacts if c[0] <= k0) == sorted(c for c in o.tr.contacts if c[0] <= k0)
                        and np.allclose(tr.pos[:k0 + 1], o.tr.pos[:k0 + 1], atol=1e-9))
                if not same:
                    ok = False
                    break
                k1 = min(int(tr.end), T)
                kc = ms.first_collision(o.branch, tr, k0 + 1, k1, cfg.margins) if k1 > k0 else None
                kx = ms.bad_frame(tr, k0 + 1, int(tr.end))
                if kc is not None or kx is not None:
                    ok = False
                    break
                o2 = _dc.replace(o, tr=tr, safe=True, why="tail", k_col=None, dev=None)
                for k_, v_ in o.__dict__.items():
                    if k_ not in {f.name for f in _dc.fields(o)}:
                        o2.__dict__[k_] = v_
                o2.k_end = int(tr.end)
                new.append((o, o2))
            if ok:
                for (a, b) in new:
                    rep_dev[id(a)] = b
                break
    if rep_dev:
        if e_ext is e:
            e_ext = _copy.copy(e)
        e_ext.outcomes = [rep_dev.get(id(o), o) for o in e_ext.outcomes]
        e_ext.t1_dev = len(rep_dev)
    return e_ext, dev_tails


def t1_cfg(base: ms.Cfg | None = None, **kw) -> ms.Cfg:
    """Tier 1's search configuration: the live flags (Cfg.live) with depth 1 and the single 1-event 60-frame pass
    (3.4.8b: <= 1 event, ~60 f), no deep-search baseline (tier 1 evaluates its own escapes) - the rest (the tables, the
    E1 speed switches, the primitives) from base / kw."""
    d = dict((base or ms.Cfg.live()).__dict__)
    d.update(depth=1, passes=((1, 60),), baseline=False, pass2_after=0, pass2_bg=False, split=False)
    d.update(kw)
    return ms.Cfg(**d)


# ---- 'tier 1 alone' on the M3 acceptance: the greedy chain of tier-1 decisions --------------------------------------

def t1_chain(S: ms.Searcher, sit: ms.Situation, prefix: ms.Seg | None = None, cap: float = 0.06, steps: int = 3,
             n_esc: int = 2, n_first: int = 1) -> dict:
    """The tier-1 decision at the situation, then again from each node its chosen plan reaches by a landed strike /
    hook (one per reaction to a hook: its own prediction), greedily, up to steps decisions in a row; the continuations
    per reaction joined into one contingent plan. {'first': T1Result, 'chosen': Eval (the joined chain or the first
    decision's), 'tried': every Eval, 'steps': decisions made, 'ms'}."""
    t0 = time.perf_counter()
    S._t1_rot = 0
    r1 = t1_decide(S, sit, prefix, None, cap, n_esc)
    tried = list(r1.tried)
    for _ in range(int(n_first) - 1):
        # (re-planned from the same state: the chosen plan carried as CONT, the windows rotated - tier 1's first
        # decisions in the frames after the situation, its state barely changed)
        if r1.ev is None:
            break
        r1 = t1_decide(S, sit, prefix, r1.ev.plan.copy(), cap, n_esc)
        tried += list(r1.tried)
    chosen = r1.ev
    n_dec = 1
    if chosen is None:
        return {"first": r1, "chosen": None, "tried": tried, "steps": 0, "ms": (time.perf_counter() - t0) * 1e3}
    S.splits = {}
    cfg = S.cfg
    S.cfg = ms.Cfg(**{**cfg.__dict__, "split": True})      # one node per reaction to a hook (its own danger)
    try:
        frontier = [(chosen, 1)]
        joined = chosen
        for depth in range(2, int(steps) + 1):
            nxt = []
            conts = []
            for (e, d) in frontier:
                if e is None or not e.plan.segs:
                    continue
                for node in S._mk_nodes(e.plan, e, d, getattr(e, "tag", ())):
                    kinds: dict = {}
                    sub: list = []
                    n_c = [0]
                    b = _node_decide(S, sit, node, cap, S._now(), n_esc=n_esc, stats={}, kinds=kinds, tried=sub,
                                     n_cand=n_c, esc=True, root=False)
                    n_dec += 1
                    tried += sub
                    ok = b is not None and (getattr(b, "t1_safe", False) if getattr(b, "tag", ()) else b.safe)
                    if ok:
                        conts.append(b)
                        nxt.append((b, depth))
            if not conts:
                break
            # the reactions' continuations joined (the deep search's recombination of the given continuations only)
            made = S._combine(sit, conts, S._now() + 10.0 * cap) if S.splits else []
            whole = [x for x in made if x.safe] + [x for x in conts if not getattr(x, "tag", ()) and x.safe]
            tried += made
            if whole:
                joined = max(whole, key=lambda x: (x.hits, x.value))
            frontier = nxt
        chosen = joined
    finally:
        S.cfg = cfg
    return {"first": r1, "chosen": chosen, "tried": tried, "steps": n_dec, "ms": (time.perf_counter() - t0) * 1e3}


__all__ = ["T1Result", "t1_decide", "t1_cfg", "t1_chain", "risk_key", "open_risk"]
