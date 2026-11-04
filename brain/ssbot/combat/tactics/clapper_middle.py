"""One middle-jump tactical event. Geometry/preferences never certify an action.

Use the observed primary Antic clock before aim and the velocity-backed landing
after it. Only the existing action owners can accept keys or report a real exit.
"""
import math

import numpy as np

from ssbot.combat import jump_behind as JB
from .forum_local import clapper_facing

JUMPS = {"CC_JUMP", "CC_JUMP_CAST"}
PRIMARY = {"CC_JUMP": "Jump Antic", "CC_JUMP_CAST": "Cast Slam Antic"}
ANTIC = {"Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2"}
AIR = {"Jump", "Air"}


def observe(tac, ws, subjects, geo, t, mem):
    """Remember the same observed move through role changes and timer resets."""
    ctx = mem.get("middle_jump")
    by_id = {s.iid: s for s in subjects}
    if ctx is not None:
        s = by_id.get(ctx["move"][0])
        if (s is None or s.family not in JUMPS or
                tac.t_commit.get(s.iid) != ctx["move"][1]):
            ctx = None
    jumping = [s for s in subjects if s.family in JUMPS]
    if len(jumping) != 1:
        ctx = None
    elif ctx is None and geo is not None and geo["region"] == "middle":
        s = jumping[0]
        if s.state in ANTIC | AIR:
            ctx = {"move": (s.iid, tac.t_commit.get(s.iid)), "antic_at": None,
                   "air_at": None, "decision": None}
    if ctx is not None:
        s = by_id[ctx["move"][0]]
        phase = getattr(tac._ent(ws, s.iid), "phase", None)
        elapsed = getattr(phase, "t_in_phase", None)
        if (s.state == PRIMARY[s.family] and getattr(phase, "top", None) == s.state
                and type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0):
            # Do not replace this with t_commit (a first-seen tick) or the
            # second Cast Antic timer, which restarts during the same move.
            ctx["antic_at"] = t - elapsed
        if s.state in AIR and ctx["air_at"] is None:
            ctx["air_at"] = t
    mem["middle_jump"] = ctx
    return ctx


def _clear(tac, fc, x, arrival, through):
    horizon = getattr(fc, "horizon", None)
    if (type(horizon) not in (int, float) or not math.isfinite(horizon)
            or not 0 <= arrival <= through <= horizon or getattr(fc, "known", False) is not True):
        return None
    ts = np.linspace(arrival, through, max(2, int(math.ceil((through-arrival)*30)) + 1))
    xx = np.full((1, len(ts)), x)
    occ = np.asarray(fc.occupied(xx, np.full_like(xx, tac.floor_y), ts))
    if occ.shape != xx.shape or occ.dtype.kind != "b":
        return None
    return not bool(occ.any())


def _standing(tac, fc, geo, source, other, land, face, hx, wait):
    """A hero-centre interval beyond the jump's full forward ground footprint.

    JT's empirical reach includes the landing hammer / large rune. The current
    forecast additionally checks the other body and hazards for the arrival and
    attack window. This is a standing preference, not a path safety certificate.
    """
    from .gauntlet import JT
    reach = land + face * (JT["reach_c"] if source.family == "CC_JUMP_CAST" else JT["reach_j"])
    a, b = geo["bodies"][other.iid]
    if face > 0:
        raw = a - reach - 2*JT["pad"]
        lo, hi = reach + JT["pad"] + geo["left"], a - JT["pad"] - geo["right"]
    else:
        raw = reach - b - 2*JT["pad"]
        lo, hi = b + JT["pad"] + geo["left"], reach - JT["pad"] - geo["right"]
    if raw < max(JT["gap_u"], geo["left"]+geo["right"]) or lo > hi:
        return None, "middle ground footprint closed"
    x = min(hi, max(lo, float(other.pos[0]) - face*tac.rules.face_u))
    arrival = max(wait, tac.rules.start_s + abs(x-hx)/tac.rules.run_u_s)
    clear = _clear(tac, fc, x, arrival, arrival+tac.rules.swing_s+tac.rules.margin_s)
    return (x, "middle ground window") if clear else (None, "middle ground covered" if clear is False else "middle ground window unknown")


def choose(tac, ws, fc, geo, hx, t, ctx):
    """Return one causal stage/route, including explicit unknowns."""
    s = next(s for s in fc.subjects if s.iid == ctx["move"][0])
    o = next(o for o in fc.subjects if o.alive and o.in_play and o.iid != s.iid)
    info = dict(source=s.iid, move=ctx["move"], target=s.iid, route="hold", stance=hx,
                kind=None, reason="geometry unknown", endpoints=[], path_checked=False)
    if geo is None:
        return info
    ent = tac._ent(ws, s.iid)
    face = clapper_facing(ent) if ent is not None else None
    if face not in (-1, 1):
        info["reason"] = "facing unknown"
        return info
    if s.state in ANTIC:
        start = ctx["antic_at"]
        if start is None:
            info["reason"] = "aim clock unknown"
            return info
        can = getattr(ws.hero, "can", None) or {}
        contact = getattr(getattr(ws.hero, "contact", None), "v", None)
        if can.get("input") is not True or contact != "GROUND":
            info["reason"] = "guide movement readiness unknown"
            return info
        remaining = (.48 if s.family == "CC_JUMP" else .88) - (t-start)
        aim = JB.aim_spot(float(s.pos[0]), face)
        speed = tac.rules.run_u_s if can.get("dash") is True else JB.CFG["walk_v"]*60
        arrival = tac.rules.start_s + abs(aim-hx)/speed
        info.update(remaining_aim=remaining, guide_arrival=arrival)
        if remaining < arrival + tac.rules.margin_s:
            info["reason"] = "guide arrives after aim reserve"
            return info
        back = float(s.pos[0])-geo["xa"] if face > 0 else geo["xb"]-float(s.pos[0])
        if back < JB.CFG["push_from_u"]:
            info["reason"] = "guided wall landing unknown"
            return info
        land = JB.landing(float(s.pos[0]), aim, face)
        # Only guide toward the side containing the other monster. Neither
        # a late first observation nor an already locked aim is a guide.
        if (float(o.pos[0])-land)*face <= 0:
            info["reason"] = "other monster not beyond guided landing"
            return info
        stand, why = _standing(tac, fc, geo, s, o, land, face, hx, remaining+.916)
        info.update(landing=land, reason=why)
        if stand is not None:
            info.update(route="guide", stance=aim)
        return info
    # _spot/candidates has already updated the same existing jb_land record.
    rec = tac.jb_land.get(s.iid)
    if rec is None or len(rec) != 4 or rec[3] is not True or not np.isfinite(rec[:3]).all():
        info["reason"] = "locked landing unknown"
        return info
    x0, face, land, _ = rec
    back = x0-geo["xa"] if face > 0 else geo["xb"]-x0
    info.update(landing=land, landing_basis="observed velocity + existing model")
    wall_bound = back < JB.CFG["push_from_u"]
    if (float(o.pos[0])-land)*face <= 0:
        info["reason"] = "landing crossed standing monster"
        return info
    stand, why = _standing(tac, fc, geo, s, o, land, face, hx, 0.)
    info["reason"] = why
    if wall_bound:
        info["landing_basis"] += "; wall lower bound only"
        if why != "middle ground footprint closed":
            info["reason"] = "wall landing is only a bound"
            return info
        # A forward wall push can only close this forward gap further. It
        # cannot turn an already closed lower-bound footprint into standing room.
    if stand is not None:
        info.update(route="stand", target=o.iid, stance=stand, kind="side")
        return info
    # An unknown future window is not the same claim as a closed middle.
    if why.endswith("unknown"):
        return info
    spot = JB.behind_spot(land, face)
    age = 0. if ctx["air_at"] is None else max(0., (t-ctx["air_at"])*60+2)
    a, b = geo["bodies"][o.iid]
    way_lo, way_hi = sorted((hx, spot)) if spot is not None else (hx, hx)
    body_on_way = way_lo-geo["left"] <= b and a <= way_hi+geo["right"]
    if (spot is not None and not body_on_way and
            JB.walk_fits(hx, land, int(face), age)):
        room = spot-geo["xa"] if face > 0 else geo["xb"]-spot
        info["endpoints"].append(dict(route="under", x=spot, wall_room=room, target=s.iid,
                                      kind=None, certified=False,
                                      basis="declared behind_spot; existing walk_fits; path pending"))
    # This is an explicitly DECLARED L2 destination, not a prediction that
    # SWITCH has already checked the flight. The existing stomp recipe ends
    # at a REAL bounce; ordinary planning then still sees this far-side stance.
    # It must not be presented as transfer.flight_endpoint (an unused helper).
    can = getattr(ws.hero, "can", None) or {}
    contact = getattr(getattr(ws.hero, "contact", None), "v", None)
    far = (b + max(1.2, geo["left"]) if face > 0 else a - max(1.2, geo["right"]))
    room = geo["xb"]-far if face > 0 else far-geo["xa"]
    if (o.state in {"Idle", "Walk", "Spell Antic", "Cast 1", "Cast 2", "Slam Recover"}
            and can.get("input") is True and contact in {"GROUND", "AIR"}
            and ctx["antic_at"] is not None and room >= .5
            and tac.rules.start_s + abs(far-hx)/tac.rules.run_u_s < 2.):
        info["endpoints"].append(dict(route="over", x=far, wall_room=room, target=o.iid,
                                      kind="stomp", certified=False,
                                      basis="declared far-side stance; SWITCH stomp then ordinary; native checks pending"))
    else:
        info["over_unknown"] = "current transfer entry prerequisites or far-side room unknown"
    if info["endpoints"]:
        best = max(info["endpoints"], key=lambda v: v["wall_room"])
        info.update(route=best["route"], stance=best["x"], target=best["target"], kind=best["kind"],
                    reason="declared destination wall room; execution unverified")
    return info
