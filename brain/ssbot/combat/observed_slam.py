"""Opt-in observed CC_SLAM motion and finite seen-ranking metadata.

No controller or admission rule. A stop belongs to the exact Segmenter instance;
unknown observations reset it. The default path retains the old forecast. Bodies,
other enemies and delayed hazards never receive a finite lifetime here.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import os

def _flag(value: str) -> bool:
    if value not in {"0", "1"}:
        raise ValueError("SSBOT_FORUM_OBSERVED_SLAM must be 0 or 1")
    return value == "1"

ENABLED = _flag(os.environ.get("SSBOT_FORUM_OBSERVED_SLAM", "0").strip())
CLAPPER = "Song Heavy Sentry"
PHASES = frozenset({"Slam Antic", "Slam 0", "Slam 1", "Slam 2", "Slam Recover"})
PAIRS = {"Slam Collider 1": "Slam 1", "Slam Collider 2": "Slam 2"}

def revision_fields() -> dict:
    return {"observed_slam": ENABLED, "observed_slam_revision": 1}

def finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

@dataclass
class Motion:
    token: object
    f: int
    fc: int
    x: float
    s: int
    saw_antic: bool
    armed: bool = False
    stopped: bool = False
    stop_f: int | None = None

class Monitor:
    def __init__(self):
        self.by_iid = {}
        self.clock = {}
        self.stops = 0

    def feed(self, raw, now):
        self.clock = {k: raw.get(k) for k in ("f", "fc", "fs", "ts", "dt", "fdt")}
        keep = {}
        for iid, (tk, e, inst) in now.items():
            if tk != CLAPPER or inst is None or inst.fam != "CC_SLAM":
                continue
            f, fc, fs = raw.get("f"), raw.get("fc"), raw.get("fs")
            ts, dt, fd = raw.get("ts"), raw.get("dt"), raw.get("fdt")
            control = next((q for q in e.get("fsms") or () if q.get("name") == "Control"), None)
            pos, vel, flip = e.get("pos") or (), e.get("vel") or (), e.get("flipX")
            if (control is None or control.get("state") not in PHASES or len(pos) < 2 or len(vel) < 2
                    or not all(finite(v) for v in (f, fc, fs, ts, dt, fd, *pos[:2], *vel[:2]))):
                continue
            if (not isinstance(f, int) or not isinstance(fc, int) or not isinstance(fs, int)
                    or fs not in (0, 1) or not 0 < fd <= .05 or ts <= 0 or dt <= 0
                    or not isinstance(flip, bool) or e.get("is_dead") or e.get("hidden")
                    or not finite(e.get("hp")) or e["hp"] <= 0):
                continue
            sign = 1 if flip else -1
            if sign != inst.s:
                continue
            old = self.by_iid.get(iid)
            state = control["state"]
            contiguous = (old is not None and old.token is inst and old.f + 1 == f
                          and old.s == sign and fc - old.fc == fs)
            row = Motion(inst, f, fc, float(pos[0]), sign,
                         state == "Slam Antic" or bool(contiguous and old.saw_antic))
            if contiguous and row.saw_antic and state != "Slam Antic":
                row.armed, row.stopped, row.stop_f = old.armed, old.stopped, old.stop_f
                if fs == 1:
                    dx = (row.x - old.x) * sign
                    if old.armed and dx < .05 and abs(float(vel[0])) <= .5:
                        row.stopped = True
                        if not old.stopped:
                            row.stop_f = f
                            self.stops += 1
                    elif dx >= .05:
                        row.armed, row.stopped, row.stop_f = True, False, None
            keep[iid] = row
        self.by_iid = keep

    def stop_for(self, iid, inst):
        row = self.by_iid.get(iid)
        return row if (row and row.token is inst and row.saw_antic and row.armed and row.stopped) else None

def predicted_offset(table, inst, template, b_from: int, b_to: int, stop: Motion | None):
    """Same displacement for attack support and certain-hit bodies, by instance.

    This function receives explicit state, never a table/global context. Only a
    matching observed stop suppresses future x; y and nominal defaults persist.
    """
    anchor = (inst.x0, inst.y0)
    p0 = table.position(template, b_from, anchor, inst.s, inst.hero_du, inst.fam)
    p1 = table.position(template, b_to, anchor, inst.s, inst.hero_du, inst.fam)
    dx = p1[0] - p0[0]
    if (stop is not None and stop.token is inst and stop.stopped and stop.armed
            and stop.saw_antic and inst.fam == "CC_SLAM" and b_to > b_from):
        dx = 0.0
    return dx, p1[1] - p0[1]

def lifetime_owner(now, focus):
    living = []
    for iid, item in (now or {}).items():
        if len(item) < 3 or item[0] != CLAPPER:
            continue
        e = item[1]
        if finite(e.get("hp")) and e["hp"] > 0 and not e.get("is_dead") and not e.get("hidden"):
            living.append(iid)
    if isinstance(focus, int) and not isinstance(focus, bool) and focus in living:
        return focus
    return living[0] if len(living) == 1 else None

def expiry_for_entity(e, collider, forecast, raw, slack):
    """Longest remaining empirical game-time dwell, not a real-time guarantee."""
    from .multi_forecast import BIN
    if e.type_key.v != CLAPPER or collider.name not in PAIRS:
        return math.inf
    state = PAIRS[collider.name]
    rs = getattr(forecast, "rs", None)
    rt = getattr(rs, "trk", None)
    now = getattr(rt, "now", {}) or {}
    item = now.get(e.id)
    inst = item[2] if item and len(item) >= 3 else None
    if (item is None or item[0] != CLAPPER or inst is None or inst.fam != "CC_SLAM"
            or not inst.states or inst.states[-1] != state
            or lifetime_owner(now, getattr(rs, "focus", None)) != e.id):
        return math.inf
    fsm = next((x for x in e.fsm or () if x[0] == "Control"), None)
    fc = getattr(forecast, "fc", None)
    tr = getattr(fc, "trackers", {}).get(e.id)
    if (fsm is None or len(fsm) < 3 or fsm[1] != state or tr is None
            or tr.state != state or tr.t_entry is None):
        return math.inf
    dw, tin, origin = tr.table.dwell.get(state), fsm[2], getattr(forecast, "origin_t", None)
    if not finite(origin) or not finite(tr.t_entry):
        return math.inf
    age = origin - tr.t_entry
    fdt, dt, ts = raw.get("fdt"), raw.get("dt"), raw.get("ts")
    if not dw or not all(finite(x) for x in (*dw, tin, age, fdt, dt, ts)):
        return math.inf
    # tk in the seen ranking is a real-time horizon. Empirical dwells are
    # game time; scaled/frozen clocks have no validated conversion here.
    if (dt <= 0 or ts != 1.0 or not 0 < fdt <= .05 or tin < 0 or age < -.00001
            or abs(age - tin) > 2 * BIN + .00001):
        return math.inf
    latest = float(dw[1]) + slack
    if dw[0] < 0 or dw[1] < dw[0] or age > latest + .00001:
        return math.inf
    return max(float(fdt), latest - age + float(fdt))

def seen_expiries(ws, forecast):
    """Match seen_polys' order, using only the actual current tracker clock."""
    import numpy as np
    from .multi_forecast import DWELL_SLACK_S
    rt = getattr(getattr(forecast, "rs", None), "trk", None)
    monitor = getattr(rt, "observed_motion", None)
    raw = monitor.clock if monitor is not None else {}
    frame = raw.get("f")
    if not isinstance(frame, int) or isinstance(frame, bool) or frame != ws.stamp.frame:
        return None
    return np.asarray([expiry_for_entity(e, b, forecast, raw, DWELL_SLACK_S)
                       for e in ws.entities or () for b in e.dmg_boxes
                       if b.active and len(b.poly) >= 3], np.float64)
