"""Forum branch model (forum_planner_plan §5 R5, behaviour-model half): decisions from the per-fight caches, their
covariates at several moments, held-out selection and the branch_model.json product.

    recs = scan_fight(cache, extra)          # one fight: a DecisionRecord per decision-state exit (SENSING states)
    res = study(records, fights_fold)         # per decision: CV log loss per timing, selected covariates, calibration
    model = build_model(records, res)         # the branch_model.json dict (ssbot.combat.branch_model.BranchModel)

A decision's covariates (ssbot.combat.branch_model): geometry (|dx|, dy, side, front, distance, the type's trigger
ranges, the hero's silk) at a timing, and history (BranchMemory.features: previous attack and its last state,
anti-repeat history of this state's choices, gate flags, hops, suck timer, recent hit, cross-enemy context). Timings:
"branch" (the frame the state is left), "entry" (the frame it was entered), "stored" (the entry of the state the
FSM stored the value in, SENSING "stored:<state>"), "lead<s>" (s seconds before the branch frame).

Selection (per decision and timing): greedy forward over the candidates by 2-fold (by fight) cross-validated log loss,
backoff tables (ssbot.combat.branch_model.DecisionModel); a covariate is kept when it lowers the CV log loss by at
least SELECT_GAIN nats. The timing with the lowest CV log loss is kept (ties to "branch").
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.combat.branch_model import (ALPHA_BACKOFF, SENSING, BranchMemory, _key, geometry)
from ssbot.knowledge.behaviour_tables import Fight, fight_states
from ssbot.knowledge.forum_cache import load_cache
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS

LEADS_S = (0.1, 0.2, 0.3, 0.4, 0.5)
TIMINGS = ("branch", "entry", "stored") + tuple(f"lead{x}" for x in LEADS_S)
STALE_S = 0.25                   # an enemy position older than this at the timing is "not seen"
SELECT_GAIN = 0.002              # nats per decision a covariate must gain on the CV log loss
MAX_COVARIATES = 4
TINY_DECISIONS = ("Ready", "Fire Ready", "Fire", "Brake", "Pull Up", "Return", "Defend Ready", "Defend Buzz", "Dead")
CLAPPER_ATTACKS = ("CC_SLAM", "CC_JUMP", "CC_CAST", "CC_JUMP_CAST")
TINY_DEAD = ("Death Fx", "Dead", "Die")
ARENA_X3 = (25.67, 37.33)        # thirds of the Forum band x 14.01-48.99 (R0's hero_x / last_seen_x stand-ins)
GEO_KEYS = ("x", "y", "flip", "hx", "hy", "b0", "b1", "b2", "b3", "silk")


def decisions_of(tk: str) -> tuple[str, ...]:
    if tk == "Song Automaton Tiny":
        return TINY_DECISIONS
    return tuple(SENSING.get(tk, {}))


@dataclass(slots=True)
class DecisionRecord:
    fight: str
    tk: str
    iid: int
    state: str
    outcome: str
    T: float                     # game time of the branch frame
    t_in: float                  # time in the state when it was left
    hist: dict
    geo: np.ndarray              # [len(TIMINGS), len(GEO_KEYS)] float32 (nan: not available)


# ---- hero extras (silk, health) from the recording ----------------------------------------------------------------

def hero_extra(meta: dict) -> dict[str, np.ndarray]:
    """Per-frame hero silk and health of a cached fight, read from its recording (about 2 s a fight)."""
    fight = Fight("rec", Path(meta["path"]), int(meta["f0"]), int(meta["f1"]), meta["id"], meta.get("outcome"))
    F, S, H = [], [], []
    for s in fight_states(fight, keys=("hero",)):
        f = s.get("f")
        if not isinstance(f, int):
            continue
        h = s.get("hero") or {}
        F.append(f)
        S.append(int(h.get("silk") if h.get("silk") is not None else -1))
        H.append(int(h.get("health") if h.get("health") is not None else -1))
    return {"f": np.asarray(F, np.int64), "silk": np.asarray(S, np.int16), "health": np.asarray(H, np.int16)}


# ---- scan --------------------------------------------------------------------------------------------------------

class _Rows:
    """One entity's exported rows, by frame index."""

    def __init__(self, c: dict, sel: np.ndarray):
        o = np.argsort(c["e_fi"][sel], kind="stable")
        idx = sel[o]
        self.fi = c["e_fi"][idx]
        self.x, self.y = c["e_x"][idx], c["e_y"][idx]
        self.flip, self.hidden = c["e_flip"][idx], c["e_hidden"][idx]
        self.st = c["e_st"][idx]

    def at(self, fi: int, T: np.ndarray) -> tuple | None:
        """(x, y, flip) of the last non-hidden row at or before frame index fi, at most STALE_S old."""
        k = int(np.searchsorted(self.fi, fi, side="right")) - 1
        while k >= 0 and self.hidden[k]:
            k -= 1
        if k < 0 or T[fi] - T[self.fi[k]] > STALE_S:
            return None
        return float(self.x[k]), float(self.y[k]), int(self.flip[k])


def scan_fight(c: dict, extra: dict | None = None) -> list[DecisionRecord]:
    """Decision records of one cached fight (forum_cache.load_cache) with its hero extras (hero_extra)."""
    T = c["T"]
    fidx = {int(f): i for i, f in enumerate(c["f"])}
    types = c["types"]
    silk = None
    if extra is not None:
        xi = {int(f): i for i, f in enumerate(extra["f"])}
        silk = np.full(len(T), -1, np.int16)
        for i, f in enumerate(c["f"]):
            j = xi.get(int(f))
            if j is not None:
                silk[i] = extra["silk"][j]
    by_tk = {s.boss_type: s for s in FORUM_SPECS.values()}
    iids = np.unique(c["e_iid"])
    rows, tk_of = {}, {}
    order = np.argsort(c["e_iid"], kind="stable")
    sorted_iid = c["e_iid"][order]
    for iid in iids:
        lo, hi = np.searchsorted(sorted_iid, iid), np.searchsorted(sorted_iid, iid, side="right")
        sel = order[lo:hi]
        tk = types[int(c["e_tk"][sel[0]])]
        if tk not in by_tk:
            continue
        rows[int(iid)] = _Rows(c, sel)
        tk_of[int(iid)] = tk
    mems: dict[int, BranchMemory] = {}
    for iid, tk in tk_of.items():
        sp = by_tk[tk]
        mems[iid] = BranchMemory(tk, dict(sp.attack_starts), frozenset(sp.decision_states) | frozenset(decisions_of(tk)))
    dec = {tk: set(decisions_of(tk)) for tk in by_tk}
    tiny_owner = _tiny_owners(c, rows, tk_of, T)
    out: list[DecisionRecord] = []
    hb = c["hbox"]
    for f, kind, d in c["events"]:
        fi = fidx.get(int(f))
        if fi is None:
            continue
        if kind == "hit":
            m = mems.get(int(d.get("ent") or 0))
            if m is not None:
                m.hit(float(T[fi]))
            continue
        if kind != "fsm":
            continue
        iid = int(d.get("iid") or 0)
        m = mems.get(iid)
        if m is None or d.get("fsm") != by_tk[m.tk].control_fsm or not isinstance(d.get("to"), str):
            continue
        frm, to, Tb = d.get("from"), d["to"], float(T[fi])
        if frm is not None and frm in dec[m.tk] and m.state == frm and m.t_entry is not None:
            ctx = _context(m, iid, mems, rows, tk_of, tiny_owner, fi, T, silk)
            hist = m.features(frm, Tb, ctx)
            hist.update(_r0_features(m, frm, rows[iid], fi, T, c, hb))
            geo = _geo(m, frm, iid, rows[iid], fi, T, c, hb, silk)
            out.append(DecisionRecord(c["meta"]["id"], m.tk, iid, frm, to, Tb, Tb - m.t_entry, hist, geo))
        m.enter(frm, to, Tb)
    return out


def _fi_at(T: np.ndarray, t: float) -> int:
    return max(0, int(np.searchsorted(T, t, side="right")) - 1)


def _geo(m: BranchMemory, state: str, iid: int, r: _Rows, fi: int, T: np.ndarray, c: dict, hb: np.ndarray,
         silk: np.ndarray | None) -> np.ndarray:
    g = np.full((len(TIMINGS), len(GEO_KEYS)), np.nan, np.float32)
    kind = SENSING.get(m.tk, {}).get(state, ("branch", ""))[0]
    stored = kind.split(":", 1)[1] if kind.startswith("stored:") else None
    for k, tm in enumerate(TIMINGS):
        if tm == "branch":
            fj = fi
        elif tm == "entry":
            fj = _fi_at(T, m.t_entry)
        elif tm == "stored":
            if stored is None or stored not in m.entries:
                continue
            fj = _fi_at(T, m.entries[stored])
        else:
            fj = _fi_at(T, T[fi] - float(tm[4:]))
        e = r.at(fj, T)
        if e is not None:
            g[k, 0:3] = e
        g[k, 3], g[k, 4] = c["hx"][fj], c["hy"][fj]
        g[k, 5:9] = hb[fj]
        if silk is not None and silk[fj] >= 0:
            g[k, 9] = silk[fj]
    return g


def geo_features(tk: str, g: np.ndarray, timing: str) -> dict:
    """ssbot.combat.branch_model.geometry of one record's row at a timing (prefixed by nothing; the timing is the
    model's)."""
    v = g[TIMINGS.index(timing)]
    ex = None if math.isnan(v[0]) else float(v[0])
    hx = None if math.isnan(v[3]) else float(v[3])
    box = None if math.isnan(v[5]) else tuple(float(x) for x in v[5:9])
    s = None if math.isnan(v[9]) else int(v[9])
    return geometry(tk, ex, None if ex is None else float(v[1]), 0 if ex is None else int(v[2]), hx,
                    None if hx is None else float(v[4]), box, s)


def _context(m: BranchMemory, iid: int, mems: dict, rows: dict, tk_of: dict, tiny_owner: dict, fi: int,
             T: np.ndarray, silk: np.ndarray | None) -> dict:
    ctx: dict = {}
    if m.tk == "Song Heavy Sentry":
        buddies = [j for j, t in tk_of.items() if t == m.tk and j != iid and mems[j].state is not None
                   and mems[j].state not in ("Init", "Rest", "On-plane Rest", "Start Idle")
                   and rows[j].at(fi, T) is not None]
        ctx["buddy"] = bool(buddies)
        ctx["buddy_attacking"] = any(mems[j].fam in CLAPPER_ATTACKS for j in buddies)
        me = rows[iid].at(fi, T)
        ctx["buddy_close"] = bool(me is not None and any(
            (b := rows[j].at(fi, T)) is not None and abs(b[0] - me[0]) < 4.0 for j in buddies))
    elif m.tk == "Song Pilgrim Maestro":
        mine = [j for j, o in tiny_owner.items() if o == iid]
        ctx["dead_tinies"] = sum(1 for j in mine if mems[j].state in TINY_DEAD)
    return ctx


def _tiny_owners(c: dict, rows: dict, tk_of: dict, T: np.ndarray) -> dict[int, int]:
    """Tiny iid -> the Maestro iid it hovers by: the Maestro nearest to it over the frames it is in Ready (the Tinies'
    Idle Pos is (+-3, 2.5) / (0, 4.5) from their own Maestro)."""
    states = c["states"]
    ready = {i for i, s in enumerate(states) if s == "Ready"}
    maes = [j for j, t in tk_of.items() if t == "Song Pilgrim Maestro"]
    out = {}
    for j, t in tk_of.items():
        if t != "Song Automaton Tiny" or not maes:
            continue
        r = rows[j]
        votes: Counter = Counter()
        for k in range(0, len(r.fi), 15):
            if int(r.st[k]) not in ready or r.hidden[k]:
                continue
            best = None
            for mj in maes:
                e = rows[mj].at(int(r.fi[k]), T)
                if e is None:
                    continue
                dd = math.hypot(e[0] - float(r.x[k]), e[1] - float(r.y[k]))
                if best is None or dd < best[0]:
                    best = (dd, mj)
            if best is not None and best[0] < 8.0:
                votes[best[1]] += 1
        if votes:
            out[j] = votes.most_common(1)[0][0]
    return out


def _r0_features(m: BranchMemory, state: str, r: _Rows, fi: int, T: np.ndarray, c: dict, hb) -> dict:
    """The R0 tables' covariates (behaviour_tables._covariates) at the branch frame, for the baseline."""
    out: dict = {}
    e = r.at(fi, T)
    hx = float(c["hx"][fi])
    if e is not None and not math.isnan(hx):
        dx = abs(hx - e[0])
        out["dist_visible"] = 0 if dx < 3.0 else 1 if dx < 6.0 else 2 if dx < 10.0 else 3
        out["side_visible"] = "L" if hx - e[0] < 0 else "R"
        out["last_seen_x"] = 0 if e[0] < ARENA_X3[0] else 2 if e[0] >= ARENA_X3[1] else 1
    if not math.isnan(hx):
        out["hero_x"] = 0 if hx < ARENA_X3[0] else 2 if hx >= ARENA_X3[1] else 1
    for fam, k in m.since.items():
        out[f"since_{fam}"] = min(k, 4)
    loc = list(m.local.get(state) or ())
    for o in set(loc):
        k = next(j for j, x in enumerate(reversed(loc)) if x == o)
        out[f"miss_{o}"] = min(k, 4)
    return out


# ---- fit / evaluate ----------------------------------------------------------------------------------------------

class _Enc:
    """Integer codes of one covariate over records (-1: not available)."""

    def __init__(self, values: list):
        lv = sorted({_key(v) for v in values if v is not None})
        self.levels = lv
        ix = {v: i for i, v in enumerate(lv)}
        self.codes = np.array([-1 if v is None else ix[_key(v)] for v in values], np.int64)


def _prefix_keys(codes: list[np.ndarray]) -> list[np.ndarray]:
    """Per prefix length k (1..): a key per record (-1 where any of the first k codes is unavailable)."""
    out = []
    key = np.zeros(len(codes[0]) if codes else 0, np.int64)
    bad = np.zeros_like(key, bool)
    for cc in codes:
        width = int(cc.max()) + 2 if len(cc) else 2
        key = key * width + (cc + 1)
        bad |= cc < 0
        out.append(np.where(bad, -1, key))
    return out


def _fit_predict(y: np.ndarray, K: int, keys: list[np.ndarray], train: np.ndarray, test: np.ndarray,
                 alpha: float = ALPHA_BACKOFF) -> np.ndarray:
    """[n_test, K] backoff predictions (DecisionModel.predict) from the training records' counts."""
    n0 = np.bincount(y[train], minlength=K).astype(np.float64)
    p = np.tile((n0 + 0.5) / (n0.sum() + 0.5 * K), (int(test.sum()), 1))
    alive = np.ones(int(test.sum()), bool)
    yt = y[train]
    for kk in keys:
        ktr, kte = kk[train], kk[test]
        ok = ktr >= 0
        uk, inv = np.unique(ktr[ok], return_inverse=True)
        if not len(uk):
            break
        cnt = np.zeros((len(uk), K))
        np.add.at(cnt, (inv, yt[ok]), 1.0)
        pos = np.clip(np.searchsorted(uk, kte), 0, len(uk) - 1)
        hit = alive & (kte >= 0) & (uk[pos] == kte)
        if not hit.any():
            break
        cc = cnt[pos[hit]]
        n = cc.sum(axis=1, keepdims=True)
        p[hit] = (cc + alpha * p[hit]) / (n + alpha)
        alive &= hit
    return p


def cv_logloss(y: np.ndarray, K: int, fold: np.ndarray, codes: list[np.ndarray]) -> tuple[float, np.ndarray]:
    """Mean held-out log loss (nats per decision) over the two folds and the held-out predictions [n, K]."""
    keys = _prefix_keys(codes) if codes else []
    P = np.zeros((len(y), K))
    for f in (0, 1):
        te = fold == f
        if not te.any() or te.all():
            continue
        P[te] = _fit_predict(y, K, keys, ~te, te)
    ll = -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1.0))
    return float(ll.mean()), P


def calibration(P: np.ndarray, y: np.ndarray, bins: int = 10) -> dict:
    """Expected calibration error over every (decision, outcome) pair and the reliability table."""
    K = P.shape[1]
    p = P.ravel()
    o = (np.arange(K)[None, :] == y[:, None]).ravel().astype(float)
    b = np.minimum((p * bins).astype(int), bins - 1)
    rows, ece = [], 0.0
    for i in range(bins):
        s = b == i
        if not s.any():
            continue
        mp, fr = float(p[s].mean()), float(o[s].mean())
        ece += s.sum() / len(p) * abs(mp - fr)
        rows.append([round(mp, 4), round(fr, 4), int(s.sum())])
    return {"ece": round(ece, 5), "reliability": rows}


def greedy(y: np.ndarray, K: int, fold: np.ndarray, cand: dict[str, np.ndarray]) -> tuple[list[str], float, list]:
    """Forward selection of covariates by CV log loss: (selected names, CV log loss, trace)."""
    sel: list[str] = []
    best, _ = cv_logloss(y, K, fold, [])
    trace = [("", round(best, 5))]
    while len(sel) < MAX_COVARIATES:
        step = None
        for name, cc in cand.items():
            if name in sel or (cc >= 0).sum() < 30:
                continue
            ll, _ = cv_logloss(y, K, fold, [cand[s] for s in sel] + [cc])
            if step is None or ll < step[1]:
                step = (name, ll)
        if step is None or step[1] > best - SELECT_GAIN:
            break
        sel.append(step[0])
        best = step[1]
        trace.append((step[0], round(best, 5)))
    return sel, best, trace


@dataclass
class DecisionData:
    tk: str
    state: str
    outcomes: list[str]
    y: np.ndarray
    fold: np.ndarray
    hist: dict[str, list]
    geo: dict[str, dict[str, list]]          # timing -> covariate -> values
    available: dict[str, int] = field(default_factory=dict)


def decision_data(recs: list[DecisionRecord], fold_of: dict[str, int], timings=TIMINGS) -> DecisionData:
    tk, state = recs[0].tk, recs[0].state
    outs = sorted({r.outcome for r in recs})
    y = np.array([outs.index(r.outcome) for r in recs], np.int64)
    fold = np.array([fold_of.get(r.fight, 0) for r in recs], np.int64)
    hk = sorted({k for r in recs for k in r.hist})
    hist = {k: [r.hist.get(k) for r in recs] for k in hk}
    geo: dict[str, dict[str, list]] = {}
    avail = {}
    for tm in timings:
        gf = [geo_features(tk, r.geo, tm) for r in recs]
        keys = sorted({k for g in gf for k in g})
        geo[tm] = {k: [g.get(k) for g in gf] for k in keys}
        avail[tm] = sum(1 for g in gf if g.get("dx") is not None)
    return DecisionData(tk, state, outs, y, fold, hist, geo, avail)


def study_decision(dd: DecisionData, r0_conditioners: list[str] | None = None) -> dict:
    """Per timing: geometry-only and geometry + history greedy selections; baselines; the chosen model."""
    K = len(dd.outcomes)
    henc = {k: _Enc(v).codes for k, v in dd.hist.items()}
    r0_names = {"dist_visible", "side_visible", "hero_x", "last_seen_x"} | {k for k in henc if
                                                                             k.startswith(("since_", "miss_"))}
    hist_cand = {k: v for k, v in henc.items() if k not in r0_names}
    res: dict = {"n": int(len(dd.y)), "outcomes": dd.outcomes,
                 "counts": dict(Counter(dd.outcomes[i] for i in dd.y))}
    ll_u, P_u = cv_logloss(dd.y, K, dd.fold, [])
    res["uncond"] = {"logloss": round(ll_u, 5), **calibration(P_u, dd.y)}
    if r0_conditioners:
        mp = {"run": "run", "prev": "prev", "last_choice": "last_choice", "choice_run": "choice_run"}
        codes = []
        for name in r0_conditioners:
            k = mp.get(name, name)
            if k in henc:
                codes.append(henc[k])
        ll, P = cv_logloss(dd.y, K, dd.fold, codes)
        res["r0"] = {"conditioners": r0_conditioners, "used": len(codes), "logloss": round(ll, 5),
                     **calibration(P, dd.y)}
    per = {}
    for tm, gv in dd.geo.items():
        genc = {k: _Enc(v).codes for k, v in gv.items()}
        if not any((cc >= 0).any() for cc in genc.values()):
            continue
        sel_g, ll_g, _ = greedy(dd.y, K, dd.fold, genc)
        cand = {**{f"g:{k}": v for k, v in genc.items()}, **{f"h:{k}": v for k, v in hist_cand.items()}}
        sel, ll, trace = greedy(dd.y, K, dd.fold, cand)
        per[tm] = {"geo_only": {"covariates": sel_g, "logloss": round(ll_g, 5)},
                   "full": {"covariates": sel, "logloss": round(ll, 5), "trace": trace},
                   "available": dd.available.get(tm)}
    sel_h, ll_h, _ = greedy(dd.y, K, dd.fold, {f"h:{k}": v for k, v in hist_cand.items()})
    res["history_only"] = {"covariates": sel_h, "logloss": round(ll_h, 5)}
    res["timings"] = per
    if per:
        best_tm = min(per, key=lambda t: (per[t]["full"]["logloss"] - (1e-9 if t == "branch" else 0.0)))
        best = per[best_tm]["full"]
    else:
        best_tm, best = "branch", {"covariates": sel_h, "logloss": ll_h}
    codes = []
    for name in best["covariates"]:
        kind, k = name.split(":", 1)
        codes.append(_Enc(dd.geo[best_tm][k]).codes if kind == "g" else henc[k])
    ll, P = cv_logloss(dd.y, K, dd.fold, codes)
    res["chosen"] = {"timing": best_tm, "covariates": best["covariates"], "logloss": round(ll, 5),
                     **calibration(P, dd.y)}
    return res


def fit_tables(dd: DecisionData, timing: str, covariates: list[str]) -> dict:
    """The DecisionModel dict (branch_model.json) on all of the given records."""
    K = len(dd.outcomes)
    vals = []
    for name in covariates:
        kind, k = name.split(":", 1)
        vals.append(dd.geo[timing][k] if kind == "g" else dd.hist[k])
    counts: list[dict] = [{"": np.bincount(dd.y, minlength=K).tolist()}]
    for depth in range(1, len(covariates) + 1):
        acc: dict = defaultdict(lambda: [0] * K)
        for i in range(len(dd.y)):
            key = []
            for v in vals[:depth]:
                if v[i] is None:
                    break
                key.append(_key(v[i]))
            if len(key) == depth:
                acc["|".join(key)][int(dd.y[i])] += 1
        counts.append(dict(acc))
    return {"outcomes": dd.outcomes, "covariates": [n.split(":", 1)[1] for n in covariates], "timing": timing,
            "counts": counts, "alpha": ALPHA_BACKOFF, "n": int(len(dd.y))}


def holdout_eval(train: DecisionData, test: DecisionData, timing: str, covariates: list[str]) -> dict:
    """Log loss and calibration on another set of fights of the tables fit on `train` (test outcomes unseen in
    training get the smoothed floor)."""
    from ssbot.combat.branch_model import DecisionModel
    t = fit_tables(train, timing, covariates)
    m = DecisionModel(t["outcomes"], t["covariates"], timing, t["counts"])
    K = len(m.outcomes)
    P = np.zeros((len(test.y), K + 1))
    y = np.zeros(len(test.y), np.int64)
    for i in range(len(test.y)):
        feats = {}
        for name in covariates:
            kind, k = name.split(":", 1)
            src = test.geo[timing].get(k) if kind == "g" else test.hist.get(k)
            feats[k] = None if src is None else src[i]
        p = m.predict(feats)
        P[i, :K] = [p[o] for o in m.outcomes]
        o = test.outcomes[int(test.y[i])]
        y[i] = m.outcomes.index(o) if o in m.outcomes else K
    P[:, K] = 1e-6
    P /= P.sum(axis=1, keepdims=True)
    ll = -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1.0))
    return {"n": int(len(y)), "logloss": round(float(ll.mean()), 5), **calibration(P, y)}
