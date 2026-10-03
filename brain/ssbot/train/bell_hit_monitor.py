"""The known-effect invariant for the hero's hits on drop bells (M2 plan, 2026-10-02, the person: "hitting a bell makes
the safe zone larger; a model that computes it smaller is wrong"), checked in both views, live and on recordings.

What it measures. For every drop bell the hero tinks (the recording's / STATE's FSM event to a Tink state; evaluation
only, the forecasts never see it), the danger zone that bell alone puts around the hero in the 1 s after the tink:
grid cells (x hero +- ZONE_X at ZONE_DX, y hero + ZONE_Y, t every frame) its support meets, counted

  hit    in the forecast the planner has EVAL_LAG_S after the tink (the vision view sees the tink 2-4 frames late and
         its track needs the detections to pick a branch, bell_track; the oracle view reads the logged velocity);
  nohit  for the same bell untouched: its exact path in the last forecast made before the tink (untinked branches only,
         both bounce sides while open), carried to the same times.

A violation is hit > nohit (the model made the hit enlarge the zone): the redirect sends the bell away from the hitter
(pogo_targets.tink), so the zone near the hero can only shrink once the tink is seen. The same zone counted at the
first forecast whose frame is past the tink (the vision view: the union of the untinked and tinked branches, by
design at least the untouched zone) is reported against the bell's self template, the wide union the vision view fell
back to before (it must never be larger). A bell without an exact path before the tink (not yet seen falling) is
skipped (no nohit to compare with).
"""
from dataclasses import dataclass, field

import numpy as np

DROP_BELL = "BoneBeast DropBell"
TINK_TO = frozenset({"Tink Right", "Tink Left", "Tink D", "Tink Right 2", "Tink Left 2", "Tink D 2"})
ZONE_X, ZONE_DX = 4.0, 0.25
ZONE_Y = (0.0, 1.5, 3.0)
ZONE_S = 1.0
EVAL_LAG_S = 0.2


def tinks_of(s: dict) -> list[tuple[int, str]]:
    """(iid, type key) of the drop bells a STATE's FSM events tink."""
    out = []
    for ev in s.get("ev") or ():
        d = ev.get("d") or {}
        if ev.get("k") == "fsm" and str(d.get("obj", "")).startswith(DROP_BELL) and d.get("to") in TINK_TO:
            out.append((int(d.get("iid") or 0), str(d.get("obj"))))
    return out


def zone(f, type_key: str, hx: float, hy: float, t_lo: float, t_hi: float, det=None, placements=None) -> int:
    """Cells of the grid around (hx, hy), t_lo .. t_hi s from the forecast's origin (every 1/60 s), that the bell
    type_key's support meets in forecast f: its exact paths (det: f.det, or the DetBells given) and its own self-template
    placements (placements: f.placements, or those given)."""
    if t_hi <= t_lo:
        return 0
    tk = np.arange(max(0.0, t_lo), t_hi + 1e-9, 1 / 60)
    if not len(tk):
        return 0
    xs = hx + np.arange(-ZONE_X, ZONE_X + 1e-9, ZONE_DX)
    px = np.tile(xs, len(ZONE_Y))
    py = np.repeat(hy + np.asarray(ZONE_Y), len(xs))
    X = np.ascontiguousarray(np.repeat(px[:, None], len(tk), axis=1))
    Y = np.ascontiguousarray(np.repeat(py[:, None], len(tk), axis=1))
    occ = np.zeros(X.shape, bool)
    # the forecast's path caches are keyed by the index in f.det: a swapped list gets its own (fresh) caches
    names = ("det", "_paths", "_groups", "_grid")
    saved = {k: getattr(f, k, None) for k in names}
    try:
        f.det = list(saved["det"] if det is None else det)
        f._paths, f._groups, f._grid = {}, {}, {}
        if f.det:
            occ |= f._det_occ(X, Y, tk, only=type_key)
    finally:
        for k, v in saved.items():
            setattr(f, k, v)
    pl = [p for p in (f.placements if placements is None else placements) if p.sources == frozenset({type_key})]
    if pl:
        occ |= f._occ(pl, X, Y, tk)
    return int(occ.sum())


@dataclass
class _Pending:
    iid: int
    type_key: str
    f_tink: int
    t_tink: float              # game s of the tink
    hero: tuple[float, float]
    pre: object                # the DetBell of the bell in the last forecast before the tink (untinked branches)
    pre_t: float               # that forecast's origin (game s)
    first: dict | None = None  # the zone at the first forecast past the tink


@dataclass
class BellHitMonitor:
    """Feed every planning tick (the forecast and its origin frame / time) and the raw STATEs (for the tink events);
    stats() has the counts and the cases."""
    events: int = 0
    skipped: int = 0
    evaluated: int = 0
    violations: int = 0
    over_template: int = 0
    cases: list = field(default_factory=list)
    _pending: list = field(default_factory=list)
    _last: tuple | None = None          # (fo, t_o, forecast) of the latest tick

    def reset(self) -> None:
        self.__init__()

    def on_tick(self, fcast, fo: int, t_o: float, raws: list[dict]) -> None:
        """raws: the STATEs since the last call, in order (their FSM events; the tink's game time is estimated from the
        frame count when the STATE has none)."""
        for s in raws:
            for iid, tk in tinks_of(s):
                self._on_tink(iid, tk, s)
        self._last_tick = (fo, t_o)
        for p in list(self._pending):
            if p.first is None and fo >= p.f_tink:
                p.first = self._zones(fcast, t_o, p)
            if t_o >= p.t_tink + EVAL_LAG_S:
                self._pending.remove(p)
                z = self._zones(fcast, t_o, p)
                self.evaluated += 1
                bad = z["hit"] > z["nohit"]
                self.violations += int(bad)
                over = p.first is not None and p.first["template"] >= 0 and p.first["hit"] > p.first["template"]
                self.over_template += int(over)
                if bad or over or len(self.cases) < 40:
                    self.cases.append({"f": p.f_tink, "bell": p.type_key, "eval": z, "first": p.first,
                                       "violation": bool(bad), "over_template": bool(over)})
        self._last = (fo, t_o, fcast)

    def _on_tink(self, iid: int, type_key: str, s: dict) -> None:
        self.events += 1
        if self._last is None:
            self.skipped += 1
            return
        fo, t_o, f = self._last
        pre = next((d for d in f.det if d.type_key == type_key), None)
        hb = (s.get("hero") or {}).get("box")
        if pre is None or not hb:
            self.skipped += 1
            return
        if pre.branches is not None:
            un = tuple(b for b in pre.branches if not b[1])
            if not un:
                self.skipped += 1          # tinked already by an earlier hit: no untouched path to compare with
                return
            pre = pre._replace(branches=un)
        dt = (int(s.get("f", fo)) - fo) / 60.0
        self._pending.append(_Pending(iid, type_key, int(s.get("f", fo)), t_o + dt,
                                      (0.5 * (hb[0] + hb[2]), 0.5 * (hb[1] + hb[3])), pre, t_o))

    def _zones(self, f, t_o: float, p: _Pending) -> dict:
        lo, hi = max(0.0, p.t_tink - t_o), p.t_tink + ZONE_S - t_o
        hx, hy = p.hero
        hit = zone(f, p.type_key, hx, hy, lo, hi)
        pre = p.pre._replace(t0=p.pre.t0 + (t_o - p.pre_t))
        nohit = zone(f, p.type_key, hx, hy, lo, hi, det=[pre], placements=[])
        # the self template the vision view used to fall back to (Forecast.self_tpl: placed or not); -1: none (no cue,
        # or the oracle view's arming has passed)
        tpl_pl = getattr(f, "self_tpl", {}).get(p.type_key)
        tpl = zone(f, p.type_key, hx, hy, lo, hi, det=[], placements=tpl_pl) if tpl_pl else -1
        return {"t": round(t_o - p.t_tink, 3), "hit": hit, "nohit": nohit, "template": tpl,
                "branches": len(next((d.paths() for d in f.det if d.type_key == p.type_key), ()))}

    def stats(self) -> dict:
        return {"tinks": self.events, "skipped": self.skipped, "evaluated": self.evaluated,
                "violations": self.violations, "over_template": self.over_template, "cases": self.cases[-12:]}

