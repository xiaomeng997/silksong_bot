"""Opt-in CC_SLAM motion, local damage clock and finite seen-ranking metadata.

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
    return {"observed_slam": ENABLED, "observed_slam_revision": 3}

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
    support_calls: int = 0
    support_changes: int = 0
    body_calls: int = 0
    body_changes: int = 0

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

def predicted_offset(table, inst, template, b_from: int, b_to: int, stop: Motion | None, *, audit_kind: str | None = None):
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
        if audit_kind in ('support', 'body'):
            field = audit_kind + '_calls'
            setattr(stop, field, getattr(stop, field, 0) + 1)
            if dx != 0.0:
                field = audit_kind + '_changes'
                setattr(stop, field, getattr(stop, field, 0) + 1)
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

def _expiry_result(value, reason, audit):
    if audit is not None:
        audit.update(expiry_kind='finite' if math.isfinite(value) else 'infinite',
                     expiry_s=float(value) if math.isfinite(value) else None, reason=reason)
    return value


def expiry_for_entity(e, collider, forecast, raw, slack, *, audit=None):
    """Longest remaining empirical game-time dwell; optional read-only evidence."""
    from .multi_forecast import BIN
    if e.type_key.v != CLAPPER or collider.name not in PAIRS:
        return _expiry_result(math.inf, 'not_clapper_hammer', audit)
    state = PAIRS[collider.name]
    rs = getattr(forecast, 'rs', None)
    rt = getattr(rs, 'trk', None)
    now = getattr(rt, 'now', {}) or {}
    item = now.get(e.id)
    inst = item[2] if item and len(item) >= 3 else None
    if item is None or item[0] != CLAPPER:
        return _expiry_result(math.inf, 'missing_tracked_clapper', audit)
    if inst is None or inst.fam != 'CC_SLAM' or not inst.states or inst.states[-1] != state:
        return _expiry_result(math.inf, 'tracked_move_or_phase_mismatch', audit)
    if lifetime_owner(now, getattr(rs, 'focus', None)) != e.id:
        return _expiry_result(math.inf, 'not_lifetime_owner', audit)
    fsm = next((x for x in e.fsm or () if x[0] == 'Control'), None)
    fc = getattr(forecast, 'fc', None)
    tr = getattr(fc, 'trackers', {}).get(e.id)
    if fsm is None or len(fsm) < 3 or fsm[1] != state:
        return _expiry_result(math.inf, 'world_control_mismatch', audit)
    if tr is None or tr.state != state or tr.t_entry is None:
        return _expiry_result(math.inf, 'inner_control_mismatch', audit)
    dw, tin, origin = tr.table.dwell.get(state), fsm[2], getattr(forecast, 'origin_t', None)
    if not finite(origin) or not finite(tr.t_entry):
        return _expiry_result(math.inf, 'unknown_inner_clock', audit)
    age = origin - tr.t_entry
    fdt, dt, ts = raw.get('fdt'), raw.get('dt'), raw.get('ts')
    if not dw or not all(finite(x) for x in (*dw, tin, age, fdt, dt, ts)):
        return _expiry_result(math.inf, 'unknown_dwell_or_clock', audit)
    if ts != 1.0:
        return _expiry_result(math.inf, 'scaled_or_frozen_clock', audit)
    if dt <= 0 or not 0 < fdt <= .05:
        return _expiry_result(math.inf, 'invalid_step_clock', audit)
    if tin < 0 or age < -.00001 or abs(age - tin) > 2 * BIN + .00001:
        return _expiry_result(math.inf, 'inner_world_age_mismatch', audit)
    latest = float(dw[1]) + slack
    if dw[0] < 0 or dw[1] < dw[0] or age > latest + .00001:
        return _expiry_result(math.inf, 'outside_empirical_dwell', audit)
    return _expiry_result(max(float(fdt), latest - age + float(fdt)),
                          'mapped_latest_with_fixed_guard', audit)


def seen_expiries(ws, forecast, *, audit=None):
    """Match seen_polys order; audit records evaluated values, never substitutes."""
    import numpy as np
    from .multi_forecast import DWELL_SLACK_S
    rt = getattr(getattr(forecast, 'rs', None), 'trk', None)
    monitor = getattr(rt, 'observed_motion', None)
    raw = monitor.clock if monitor is not None else {}
    frame = raw.get('f')
    match = isinstance(frame, int) and not isinstance(frame, bool) and frame == ws.stamp.frame
    if audit is not None:
        audit.update(origin_frame=ws.stamp.frame, tracker_frame=frame, frame_match=match,
                     expiry_status='not_evaluated', polygons=None)
    if not match:
        if audit is not None:
            audit['reason'] = 'tracker_frame_mismatch'
        return None
    if audit is None:
        return np.asarray([expiry_for_entity(e, b, forecast, raw, DWELL_SLACK_S)
                           for e in ws.entities or () for b in e.dmg_boxes
                           if b.active and len(b.poly) >= 3], np.float64)
    values, polygons = [], []
    for e in ws.entities or ():
        for b in e.dmg_boxes:
            if b.active and len(b.poly) >= 3:
                info = {'index': len(values), 'iid': e.id, 'collider': b.name}
                values.append(expiry_for_entity(e, b, forecast, raw, DWELL_SLACK_S, audit=info))
                polygons.append(info)
    audit.update(expiry_status='evaluated', polygons=polygons)
    return np.asarray(values, np.float64)


def motion_snapshot(rt):
    """Scalars only, no references to live STATE/forecast graphs or extra queries.

    Counts belong to the real tracker row since its last raw feed. Copied nominal
    worlds have their own rows; function changes do not certify final raster cells.
    """
    monitor = getattr(rt, 'observed_motion', None)
    clock = {} if monitor is None else {k: v if finite(v) else None for k, v in monitor.clock.items()}
    units = []
    for iid, item in (getattr(rt, 'now', None) or {}).items():
        if not item or len(item) < 3 or item[0] != CLAPPER:
            continue
        inst = item[2]
        row = None if monitor is None else monitor.by_iid.get(iid)
        matching = row is not None and row.token is inst
        units.append({'iid': iid, 'instance_token': None if inst is None else id(inst),
                      'family': getattr(inst, 'fam', None),
                      'instance_t0': getattr(inst, 't0', None) if finite(getattr(inst, 't0', None)) else None,
                      'phase': (getattr(inst, 'states', None) or [None])[-1],
                      'motion_frame': None if row is None else row.f,
                      'same_instance': matching, 'saw_antic': bool(matching and row.saw_antic),
                      'armed': bool(matching and row.armed), 'stopped': bool(matching and row.stopped),
                      'stop_f': row.stop_f if matching else None,
                      'offset_calls': {k: getattr(row, k, 0) if matching else None for k in
                                       ('support_calls', 'support_changes', 'body_calls', 'body_changes')}})
    return {'tracker_frame': clock.get('f'), 'clock': clock,
            'monitor_available': monitor is not None,
            'stops_total': None if monitor is None else monitor.stops, 'units': units,
            'count_scope': 'real row since raw feed; clones local; offset function before coast/raster'}


def audit_start(ws, forecast):
    return {'schema': 1, 'origin_frame': ws.stamp.frame,
            'motion_before': motion_snapshot(getattr(getattr(forecast, 'rs', None), 'trk', None)),
            'seen_status': 'not_evaluated', 'seen_evaluations': []}
