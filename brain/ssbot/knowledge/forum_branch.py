"""Forum branch model (forum_planner_plan §5 R5, behaviour-model half): decisions from the per-fight caches, their
covariates at several moments, held-out selection and the branch_model.json product.

    recs, samples = scan_fight(cache, extra, ahead_dt=AHEAD_DT)   # fire-frame records and forecast samples
    res = study(records, fights_fold)         # per decision: CV log loss per timing, selected covariates, calibration
    model = build_model(records, res)         # the branch_model.json dict (ssbot.combat.branch_model.BranchModel)

Two kinds of rows (ssbot.combat.branch_model, module docstring):
- a fire-frame record per exit of a decision state (SENSING states): covariates on the frame the state is left, the
  successor as the label (the "types" tables: P(successor | it decides now));
- forecast samples (ahead_dt): on the frames an enemy spends in a decision state, every AHEAD_DT s of each visit from
  its entry (AHEAD_DT_TINY for the Tiny; the Tiny's Dead, a 30 s wait for the Maestro's summon, is left out), the
  covariates the planner sees on that frame, labelled with the successor the visit ended in (the "ahead" tables).
  Instant decisions (left on the frame they are entered) have none: the planner never sees them as the current state.

A decision's covariates are those the runtime computes (ssbot.combat.branch_model): geometry (|dx|, dy, side, front,
distance, the type's trigger ranges, the hero's silk, the R0 tables' dist_visible / last_seen_x / hero_x) at a timing,
and history (BranchMemory.features: previous attack and its last state, anti-repeat history of this state's choices
and the V4 counters since_<family> / miss_<outcome>, gate flags, hops, suck timer, recent hit, time in the state,
cross-enemy context from clapper_context / TinyOwners). The scan walks the frames like the runtime: a frame's events in
order, then its end (Tiny owners, forecast samples). Timings: "branch" (the frame the state is left; "now" for a
forecast sample: its frame), "entry" (the frame it was entered), "stored" (the entry of the state the FSM stored the
value in, SENSING "stored:<state>"), "lead<s>" (s seconds before the branch frame; fire-frame records only).

Selection (per decision and timing): greedy forward over the candidates by 2-fold (by fight) cross-validated log loss,
backoff tables (ssbot.combat.branch_model.DecisionModel); a covariate is kept when it lowers the CV log loss by at
least SELECT_GAIN nats. The timing with the lowest CV log loss is kept (ties to the first timing).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.combat.branch_model import (ALPHA_BACKOFF, CLAPPER, MAESTRO, SENSING, STALE_S, TINY, BranchMemory,
                                       TinyOwners, _key, clapper_context, decisions_of, geometry, in_play)
from ssbot.knowledge.behaviour_tables import Fight, fight_states
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS

LEADS_S = (0.1, 0.2, 0.3, 0.4, 0.5)
TIMINGS = ("branch", "entry", "stored") + tuple(f"lead{x}" for x in LEADS_S)
AHEAD_TIMINGS = ("now", "entry", "stored")
AHEAD_DT = 0.1                   # forecast samples: one every AHEAD_DT s of a visit (from its entry frame)
AHEAD_DT_TINY = 0.25
AHEAD_SKIP = frozenset({(TINY, "Dead")})
SELECT_GAIN = 0.002              # nats per decision a covariate must gain on the CV log loss
MAX_COVARIATES = 4
GEO_KEYS = ("x", "y", "flip", "hx", "hy", "b0", "b1", "b2", "b3", "silk")


@dataclass(slots=True)
class DecisionRecord:
    fight: str
    tk: str
    iid: int
    state: str
    outcome: str
    T: float                     # game time of the row's frame (the branch frame; a forecast sample's frame)
    t_in: float                  # time in the state on that frame
    hist: dict
    geo: np.ndarray              # [len(timings), len(GEO_KEYS)] float32 (nan: not available)
    to_exit: float = 0.0         # forecast samples: s from the frame to the visit's exit (0: a fire-frame record)
    fi: int = -1                 # the frame's index in the cache


def memory_for(tk: str) -> BranchMemory:
    """A BranchMemory with the type's segmentation (gauntlet_tables.FORUM_SPECS; branch_model.json stores it for the
    runtime: segmentation()) and choice states."""
    sp = next(s for s in FORUM_SPECS.values() if s.boss_type == tk)
    return BranchMemory(tk, dict(sp.attack_starts), frozenset(sp.decision_states), frozenset(decisions_of(tk)))


def segmentation() -> dict:
    """branch_model.json "segmentation": per type the attack starts and decision states the scan kept history with."""
    return {s.boss_type: {"attack_starts": dict(s.attack_starts), "decision_states": sorted(s.decision_states)}
            for s in FORUM_SPECS.values()}


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
        """(x, y, flip) of the last non-hidden row at or before frame index fi, at most STALE_S old (BranchView's
        rows: the frames the enemy was seen)."""
        k = int(np.searchsorted(self.fi, fi, side="right")) - 1
        while k >= 0 and self.hidden[k]:
            k -= 1
        if k < 0 or T[fi] - T[self.fi[k]] > STALE_S + 1e-9:
            return None
        return float(self.x[k]), float(self.y[k]), int(self.flip[k])

    def now(self, fi: int) -> tuple | None:
        """(x, y) of its row on frame fi, when it was seen (exported, not hidden) on that frame."""
        k = int(np.searchsorted(self.fi, fi, side="right")) - 1
        if k < 0 or self.fi[k] != fi or self.hidden[k]:
            return None
        return float(self.x[k]), float(self.y[k])


def scan_fight(c: dict, extra: dict | None = None, ahead_dt: float | None = None,
               every_frame: bool = False) -> tuple[list[DecisionRecord], list[DecisionRecord]]:
    """(fire-frame records, forecast samples) of one cached fight (forum_cache.load_cache) with its hero extras
    (hero_extra). ahead_dt None: no forecast samples; every_frame: a forecast sample on every frame of every visit
    (unlabelled visits included, outcome ""; the runtime parity check)."""
    T = c["T"]
    fidx = {int(f): i for i, f in enumerate(c["f"])}
    types = c["types"]
    fid = c["meta"]["id"]
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
    mems: dict[int, BranchMemory] = {iid: memory_for(tk) for iid, tk in tk_of.items()}
    dec = {tk: set(decisions_of(tk)) for tk in by_tk}
    tinies = [j for j, tk in tk_of.items() if tk == TINY]
    maes = [j for j, tk in tk_of.items() if tk == MAESTRO]
    owners = TinyOwners()
    sc = _Scan(c, T, rows, tk_of, mems, owners, silk)
    out: list[DecisionRecord] = []
    samples: list[DecisionRecord] = []
    visits: dict[int, list] = {}             # iid -> [state, t_entry, next sample time, samples]
    events = c["events"]
    ne, ei = len(events), 0
    for fi in range(len(T)):
        Tf = float(T[fi])
        while ei < ne:
            f, kind, d = events[ei]
            fj = fidx.get(int(f))
            if fj is not None and fj > fi:
                break
            ei += 1
            if fj is None:
                continue
            if kind == "hit":
                m = mems.get(int(d.get("ent") or 0))
                if m is not None:
                    m.hit(Tf)
                continue
            if kind != "fsm":
                continue
            iid = int(d.get("iid") or 0)
            m = mems.get(iid)
            if m is None or d.get("fsm") != by_tk[m.tk].control_fsm or not isinstance(d.get("to"), str):
                continue
            frm, to = d.get("from"), d["to"]
            if frm is not None and frm in dec[m.tk] and m.state == frm and m.t_entry is not None:
                hist = m.features(frm, Tf, sc.context(m, iid, fi))
                geo = sc.geo(m, frm, iid, fi, TIMINGS)
                out.append(DecisionRecord(fid, m.tk, iid, frm, to, Tf, Tf - m.t_entry, hist, geo, 0.0, fi))
            v = visits.pop(iid, None)
            if v is not None:
                for r in v[3]:
                    r.outcome, r.to_exit = to, Tf - r.T
                samples += v[3]
            m.enter(frm, to, Tf)
        # ---- the frame's end: what the runtime's BranchView.observe and a planner query see
        if tinies and maes:
            tl = [(j, p) for j in tinies if mems[j].state == "Ready" and (p := rows[j].now(fi)) is not None]
            if tl:
                ml = [(j, (e[0], e[1])) for j in maes if (e := rows[j].at(fi, T)) is not None]
                owners.update(tl, ml)
        if ahead_dt is None:
            continue
        for iid, m in mems.items():
            st = m.state
            if st is None or m.t_entry is None or st not in dec[m.tk] or (m.tk, st) in AHEAD_SKIP:
                continue
            v = visits.get(iid)
            if v is None or v[0] != st or v[1] != m.t_entry:
                v = visits[iid] = [st, m.t_entry, m.t_entry, []]
            if not every_frame and Tf < v[2] - 1e-9:
                continue
            hist = m.features(st, Tf, sc.context(m, iid, fi))
            geo = sc.geo(m, st, iid, fi, AHEAD_TIMINGS)
            v[3].append(DecisionRecord(fid, m.tk, iid, st, "", Tf, Tf - m.t_entry, hist, geo, 0.0, fi))
            if not every_frame:
                dt = AHEAD_DT_TINY if m.tk == TINY else ahead_dt
                v[2] = m.t_entry + (math.floor((Tf - m.t_entry) / dt + 1e-6) + 1) * dt
    if every_frame:
        for v in visits.values():
            samples += v[3]
    return out, samples


def _fi_at(T: np.ndarray, t: float) -> int:
    return max(0, int(np.searchsorted(T, t + 1e-9, side="right")) - 1)


class _Scan:
    """One fight's lookups shared by the fire-frame records and the forecast samples."""

    def __init__(self, c: dict, T: np.ndarray, rows: dict, tk_of: dict, mems: dict, owners: TinyOwners,
                 silk: np.ndarray | None):
        self.c, self.T, self.rows, self.tk_of, self.mems, self.owners, self.silk = c, T, rows, tk_of, mems, owners, silk
        self.clappers = [j for j, tk in tk_of.items() if tk == CLAPPER]

    def context(self, m: BranchMemory, iid: int, fi: int) -> dict:
        """branch_model.BranchView.context on the scan's rows."""
        if m.tk == CLAPPER:
            T = self.T
            me = self.rows[iid].at(fi, T)
            buddies = [(self.mems[j], b) for j in self.clappers if j != iid and in_play(CLAPPER, self.mems[j].state)
                       and (b := self.rows[j].at(fi, T)) is not None]
            return clapper_context(me, buddies)
        if m.tk == MAESTRO:
            return {"dead_tinies": self.owners.dead(iid, lambda j: self.mems[j].state if j in self.mems else None)}
        return {}

    def geo(self, m: BranchMemory, state: str, iid: int, fi: int, timings: tuple) -> np.ndarray:
        """The enemy and hero rows at each timing (BranchView._rows_for)."""
        T, c, r, silk = self.T, self.c, self.rows[iid], self.silk
        g = np.full((len(timings), len(GEO_KEYS)), np.nan, np.float32)
        kind = SENSING.get(m.tk, {}).get(state, ("branch", ""))[0]
        stored = kind.split(":", 1)[1] if kind.startswith("stored:") else None
        for k, tm in enumerate(timings):
            if tm in ("branch", "now"):
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
            g[k, 5:9] = c["hbox"][fj]
            if silk is not None and silk[fj] >= 0:
                g[k, 9] = silk[fj]
        return g


def geo_features(tk: str, g: np.ndarray, timing: str, timings: tuple = TIMINGS) -> dict:
    """ssbot.combat.branch_model.geometry of one row's geometry at a timing (prefixed by nothing; the timing is the
    model's)."""
    v = g[timings.index(timing)]
    ex = None if math.isnan(v[0]) else float(v[0])
    hx = None if math.isnan(v[3]) else float(v[3])
    box = None if math.isnan(v[5]) else tuple(float(x) for x in v[5:9])
    s = None if math.isnan(v[9]) else int(v[9])
    return geometry(tk, ex, None if ex is None else float(v[1]), 0 if ex is None else int(v[2]), hx,
                    None if hx is None else float(v[4]), box, s)


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
    to_exit: np.ndarray | None = None        # forecast samples: s to the visit's exit


def decision_data(recs: list[DecisionRecord], fold_of: dict[str, int], timings: tuple | None = None) -> DecisionData:
    """One decision's rows as covariate columns. timings: those to decode (default: all the rows carry: TIMINGS for
    fire-frame records, AHEAD_TIMINGS for forecast samples)."""
    tk, state = recs[0].tk, recs[0].state
    all_tm = TIMINGS if recs[0].geo.shape[0] == len(TIMINGS) else AHEAD_TIMINGS
    outs = sorted({r.outcome for r in recs})
    y = np.array([outs.index(r.outcome) for r in recs], np.int64)
    fold = np.array([fold_of.get(r.fight, 0) for r in recs], np.int64)
    hk = sorted({k for r in recs for k in r.hist})
    hist = {k: [r.hist.get(k) for r in recs] for k in hk}
    geo: dict[str, dict[str, list]] = {}
    avail = {}
    for tm in timings or all_tm:
        gf = [geo_features(tk, r.geo, tm, all_tm) for r in recs]
        keys = sorted({k for g in gf for k in g})
        geo[tm] = {k: [g.get(k) for g in gf] for k in keys}
        avail[tm] = sum(1 for g in gf if g.get("dx") is not None)
    return DecisionData(tk, state, outs, y, fold, hist, geo, avail, np.array([r.to_exit for r in recs]))


R0_ALIASES = {"side_visible": "side"}        # an R0 conditioner the geometry carries under another name


def _r0_codes(dd: DecisionData, henc: dict, names: list[str]) -> list[np.ndarray]:
    tm0 = next(iter(dd.geo), None)
    codes = []
    for name in names:
        k = R0_ALIASES.get(name, name)
        if k in henc:
            codes.append(henc[k])
        elif tm0 is not None and k in dd.geo[tm0]:
            codes.append(_Enc(dd.geo[tm0][k]).codes)
    return codes


def study_decision(dd: DecisionData, r0_conditioners: list[str] | None = None) -> dict:
    """Per timing: geometry-only and geometry + history greedy selections; baselines (the unconditional table; the
    R0 tables' conditioner names refit on these rows with this backoff, "r0_refit": not the shipped R0 tables, whose
    runtime use is the unconditional p_succ); the chosen model."""
    K = len(dd.outcomes)
    henc = {k: _Enc(v).codes for k, v in dd.hist.items()}
    hist_cand = dict(henc)
    res: dict = {"n": int(len(dd.y)), "outcomes": dd.outcomes,
                 "counts": dict(Counter(dd.outcomes[i] for i in dd.y))}
    ll_u, P_u = cv_logloss(dd.y, K, dd.fold, [])
    res["uncond"] = {"logloss": round(ll_u, 5), **calibration(P_u, dd.y)}
    if r0_conditioners:
        codes = _r0_codes(dd, henc, r0_conditioners)
        ll, P = cv_logloss(dd.y, K, dd.fold, codes)
        res["r0_refit"] = {"conditioners": r0_conditioners, "used": len(codes), "logloss": round(ll, 5),
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
    first = next(iter(dd.geo), "branch")
    if per:
        best_tm = min(per, key=lambda t: (per[t]["full"]["logloss"] - (1e-9 if t == first else 0.0)))
        best = per[best_tm]["full"]
    else:
        best_tm, best = first, {"covariates": sel_h, "logloss": ll_h}
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


def holdout_ll(train: DecisionData, test: DecisionData, timing: str, covariates: list[str],
               test_timing: str | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(P [n, K + 1], y, per-row log loss) on `test` of the tables fit on `train` (test outcomes unseen in training
    get the smoothed floor, column K). test_timing: the test rows' timing for the geometry (default: timing; a
    forecast sample's "now" for a fire-frame model's "branch")."""
    from ssbot.combat.branch_model import DecisionModel
    t = fit_tables(train, timing, covariates)
    m = DecisionModel(t["outcomes"], t["covariates"], timing, t["counts"])
    K = len(m.outcomes)
    P = np.zeros((len(test.y), K + 1))
    y = np.zeros(len(test.y), np.int64)
    gsrc = test.geo.get(test_timing or timing, {})
    cols = []
    for name in covariates:
        kind, k = name.split(":", 1)
        cols.append((k, gsrc.get(k) if kind == "g" else test.hist.get(k)))
    for i in range(len(test.y)):
        p = m.predict({k: None if src is None else src[i] for k, src in cols})
        P[i, :K] = [p[o] for o in m.outcomes]
        o = test.outcomes[int(test.y[i])]
        y[i] = m.outcomes.index(o) if o in m.outcomes else K
    P[:, K] = 1e-6
    P /= P.sum(axis=1, keepdims=True)
    ll = -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1.0))
    return P, y, ll


def holdout_eval(train: DecisionData, test: DecisionData, timing: str, covariates: list[str],
                 test_timing: str | None = None) -> dict:
    """Log loss and calibration on another set of fights of the tables fit on `train` (holdout_ll)."""
    P, y, ll = holdout_ll(train, test, timing, covariates, test_timing)
    return {"n": int(len(y)), "logloss": round(float(ll.mean()), 5), **calibration(P, y)}
