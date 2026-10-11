"""Tiny (Song Automaton Tiny, the Maestro's automatons): attack-range type (Task "attack range: all types", stage B).
Families and rules from the v2 classification (docs/plans/forum_zones_v2.md sec. 1.3) and R0 dev measurements. A Tiny
deals damage with its body only ("Song Automaton Tiny(Clone)", 1.00 x 1.08); it does not hurt in Swoop In Pause /
Swoop In (the entry), Leave, Die or Dead. Up to 6 at once; each is tracked on its own.

  AT_FIRE_READY  Fire Ready (0.70-0.77 s, in sync with the Maestro's Fire Antic): the body drifts +-5-7 u toward its
                 start point; the dive's side and start are pending (group 2): only this antic is drawn
  AT_DIVE        Fire > Brake > Pull Up / Wall Bonk > Return: decided at the Fire entry, anchored there in its facing
                 (the dive side: the flip agrees in 1,114 of 1,117): (24, -36.9) u/s at the entry, flattening, until
                 the floor (y 5.0: Brake), a wall (Wall Bonk) or Pull Up; Brake slides 1-23 u; Return flies back
  AT_DEFEND      Defend Ready > Defend Buzz: the orbit around the Maestro (custom below), not a template
  AT_ENTRY       Swoop In Pause > Swoop In: no damage; the body once it is Ready
  AT_LEAVE       Leave Pause > Leave: the body in Leave Pause, none in Leave
  idle           Ready (the formation flight, 6 u/s p50) and the rest: the exact body now

The custom hook (it replaces the template there):
  Defend Buzz    an orbit around the nearest Maestro: centre = the Maestro now + its velocity x tau, the angle turns by
                 the R0 dev angular-speed profile over the time in state (ramping to about 210 deg/s by 0.3 s, then
                 180-215) in the direction it turns now, the radius follows the profile (5.0 -> 2.2 at 0.3 s -> 5.05)
                 from its radius now. R0 dev k 12 position error p50 0.67 u (frozen body 3.65, velocity 1.78).
  Defend Ready   the body carried by its velocity now (k 12 error p50 0.33 u; frozen 0.64)
"""
from __future__ import annotations

import math

import numpy as np

from ssbot.combat.are_spec import EnemySpec

MAESTRO = "Song Pilgrim Maestro"
PROFILE_DT = 0.05
# Defend Buzz, per 0.05 s of time in state (R0 dev, 12 fights, 98,742 frames, the nearest Maestro within 8 u)
R_PROF = (4.81, 4.67, 4.43, 3.82, 3.04, 2.42, 2.18, 2.31, 2.75, 3.36, 3.85, 4.32, 4.6, 4.83, 4.99, 5.07, 5.09, 5.04,
          5.01, 4.99, 5.01, 5.02, 5.04, 5.06, 5.07, 5.07, 5.06, 5.05, 5.04, 5.04, 5.04, 5.02)
W_PROF = (17, 24, 39, 73, 139, 250, 346, 307, 214, 195, 199, 205, 214, 218, 217, 216, 210, 210, 208, 203, 194, 189,
          186, 185, 183, 183, 181, 181, 181, 179, 179, 180)      # deg/s (abs)


def _prof(p, t: float) -> float:
    return float(p[min(max(int(t / PROFILE_DT), 0), len(p) - 1)])


def _turn(tin: float, tau: float, n: int = 12) -> float:
    """The angle (rad, abs) the formation turns over [tin, tin + tau] of Defend Buzz."""
    if tau <= 0:
        return 0.0
    return sum(math.radians(_prof(W_PROF, tin + tau * (i + 0.5) / n)) for i in range(n)) * tau / n


def orbit_shift(x: float, y: float, vx: float, vy: float, m: tuple, tin: float, tau: float) -> tuple:
    """(dx, dy) of a Tiny in Defend Buzz over tau around the Maestro m = (x, y, vx, vy)."""
    mx, my, mvx, mvy = m
    dx, dy = x - mx, y - my
    r = math.hypot(dx, dy)
    w = (dx * (vy - mvy) - dy * (vx - mvx)) / max(r * r, 1e-6)
    phi = math.atan2(dy, dx) + math.copysign(_turn(tin, tau), w if w != 0 else 1.0)
    r1 = max(r + _prof(R_PROF, tin + tau) - _prof(R_PROF, tin), 0.3)
    return mx + mvx * tau + r1 * math.cos(phi) - x, my + mvy * tau + r1 * math.sin(phi) - y


def _maestro(view):
    """(x, y, vx, vy) of the Maestro nearest to this Tiny now, or None."""
    if view.track is not None:
        tr, j = view.track, view.j
        if "mx" not in tr or not np.isfinite(tr["mx"][j]):
            return None
        return float(tr["mx"][j]), float(tr["my"][j]), float(tr["mvx"][j]), float(tr["mvy"][j])
    from ssbot.combat.attack_range import _parked
    best = None
    for e in view.ents or ():
        if e.get("type_key") != MAESTRO or _parked(e):
            continue
        p = e.get("pos") or (0.0, 0.0)
        v = e.get("vel") or (0.0, 0.0)
        d = (float(p[0]) - view.x) ** 2 + (float(p[1]) - view.y) ** 2
        if best is None or d < best[0]:
            best = (d, (float(p[0]), float(p[1]), float(v[0]), float(v[1])))
    return None if best is None else best[1]


def _body(view) -> list:
    """Its body colliders now (CustomView.body: the tracker / the builder fill it)."""
    return list(view.body or [])


# The dive and its recovery, the antic's drift and Defend Ready: the body carried by its velocity now ("vel") or by its
# velocity and its acceleration over the last frame ("acc"), not below a floor, between the walls (R0 dev, 8 fights,
# k 12 position error p50 / p90 per state: Fire 0.61 / 1.67 u (frozen 5.82 / 7.36), Brake 0.80 / 1.19, Pull Up 0.75 /
# 1.75, Wall Bonk 0.45 / 1.01, Return 0.26 / 1.46, Fire Ready 0.23 / 5.34, Defend Ready 0.33 / 1.51; the template's
# median path left AT_DIVE at 32 % k 12 coverage on R0 fresh)
KINEMATIC = {"Fire Ready": ("acc", None), "Fire": ("acc", 4.7), "Brake": ("vel", 4.7), "Pull Up": ("acc", 4.7),
             "Wall Bonk": ("vel", None), "Return": ("acc", None), "Defend Ready": ("vel", None),
             "Leave Pause": ("vel", None)}
X_WALLS = (14.5, 48.5)
ACC_MAX = 150.0                    # u/s^2: the dive's steering is <= about 90 (vy -26.2 -> -24.8 per frame)


def _prev_vel(view):
    """(vx, vy, dt) of the frame before now: offline the track's previous frame, live the type memory."""
    if view.track is not None:
        tr, j = view.track, view.j
        if j < 1 or tr.get("vy") is None:
            return None
        dt = float(tr["T"][j] - tr["T"][j - 1])
        return (float(tr["vx"][j - 1]), float(tr["vy"][j - 1]), dt) if 0 < dt < 0.1 else None
    mem = view.mem if view.mem is not None else {}
    last = mem.setdefault("vel", {})
    s = last.get(view.iid)                      # [T, vx, vy, T before, vx before, vy before]
    if s is None:
        s = last[view.iid] = [view.T, view.vx or 0.0, view.vy or 0.0, None, None, None]
    elif s[0] < view.T - 1e-9:                  # the first estimate of a new frame: shift
        s[3:6] = s[0:3]
        s[0:3] = [view.T, view.vx or 0.0, view.vy or 0.0]
    if s[3] is None or not 0 < view.T - s[3] < 0.1:
        return None
    return s[4], s[5], view.T - s[3]


def kinematic_shift(view, tau: float) -> tuple:
    mode, floor = KINEMATIC[view.st]
    vx, vy = view.vx or 0.0, view.vy or 0.0
    ax = ay = 0.0
    if mode == "acc":
        pv = _prev_vel(view)
        if pv is not None:
            ax, ay = (vx - pv[0]) / pv[2], (vy - pv[1]) / pv[2]
            # a velocity zeroed / turned by a wall or the floor is a collision, not the move's steering
            ax = ax if abs(ax) <= ACC_MAX else 0.0
            ay = ay if abs(ay) <= ACC_MAX else 0.0
    x1 = min(max(view.x + vx * tau + 0.5 * ax * tau * tau, X_WALLS[0]), X_WALLS[1])
    y1 = view.y + vy * tau + 0.5 * ay * tau * tau
    if floor is not None:
        y1 = max(y1, min(floor, view.y))
    return x1 - view.x, y1 - view.y


def custom(view):
    """(the body moved by the orbit (Defend Buzz) or by its velocity (KINEMATIC states), None); else (None, None)."""
    if view.st != "Defend Buzz" and view.st not in KINEMATIC:
        return None, None
    from ssbot.combat.attack_range import poly_mask
    tau = max(view.t - view.T, 0.0)
    if view.st in KINEMATIC:
        dx, dy = kinematic_shift(view, tau)         # (also keeps the live velocity memory current)
    body = _body(view)
    if not body:
        return None, None
    if view.st == "Defend Buzz":
        vx, vy = view.vx or 0.0, view.vy or 0.0
        m = _maestro(view)
        if m is not None and math.hypot(view.x - m[0], view.y - m[1]) <= 8.0:
            dx, dy = orbit_shift(view.x, view.y, vx, vy, m, view.tin, tau)
        else:
            dx, dy = vx * tau, vy * tau
    return poly_mask([p + (dx, dy) for p in body], view.tab.cell), None


KEYS = ("f", "T", "st", "tin", "x", "y", "flip", "hidden", "hx", "hy", "cols", "fi", "vx", "vy")


def attach(c: dict, tracks: list) -> None:
    """Offline: drops the frames a Tiny is not in play (Dead / no state / hidden: about 3 / 4 of its pooled rows) and
    gives each frame the nearest Maestro in play (mx, my, mvx, mvy; NaN without one)."""
    types = list(c["types"])
    states = c["states"]
    mrows: dict = {}
    if MAESTRO in types:
        for x in np.nonzero(c["e_tk"] == types.index(MAESTRO))[0]:
            s = c["e_st"][x]
            nm = str(states[s]) if s >= 0 else ""
            if not nm or c["e_hidden"][x] or any(w in nm for w in ("Ready", "Dormant", "Sleep", "Wait")):
                continue
            mrows.setdefault(int(c["e_fi"][x]), []).append((float(c["e_x"][x]), float(c["e_y"][x]),
                                                            float(c["e_vx"][x]), float(c["e_vy"][x])))
    out = []
    for tr0 in tracks:
        keep = [j for j in range(len(tr0["T"])) if tr0["st"][j] not in (None, "Dead") and not tr0["hidden"][j]]
        if not keep:
            continue
        # one track per life: the pooled Tiny object comes back elsewhere after Dead (a look-ahead across the gap
        # would compare it with its next life)
        fi = np.asarray(tr0["fi"])[keep]
        cuts = np.nonzero(np.diff(fi) > 2)[0] + 1
        for part in np.split(np.asarray(keep), cuts):
            tr = {k: v for k, v in tr0.items() if k not in KEYS}
            for k in KEYS:
                v = tr0.get(k)
                if v is not None:
                    tr[k] = [v[j] for j in part] if isinstance(v, list) else np.asarray(v)[part]
            M = np.full((len(part), 4), np.nan)
            for n in range(len(part)):
                ms = mrows.get(int(tr["fi"][n]))
                if ms:
                    M[n] = min(ms, key=lambda q: (q[0] - tr["x"][n]) ** 2 + (q[1] - tr["y"][n]) ** 2)
            tr["mx"], tr["my"], tr["mvx"], tr["mvy"] = M[:, 0], M[:, 1], M[:, 2], M[:, 3]
            out.append(tr)
    tracks[:] = out


SPEC = EnemySpec(
    type_key="Song Automaton Tiny", short="Tiny",
    fam_states={
        "AT_FIRE_READY": frozenset({"Fire Ready"}),
        "AT_DIVE": frozenset({"Fire", "Brake", "Pull Up", "Wall Bonk", "Return"}),
        "AT_DEFEND": frozenset({"Defend Ready", "Defend Buzz"}),
        "AT_ENTRY": frozenset({"Swoop In Pause", "Swoop In"}),
        "AT_LEAVE": frozenset({"Leave Pause", "Leave"}),
    },
    start={"Fire Ready": "AT_FIRE_READY", "Fire": "AT_DIVE", "Defend Ready": "AT_DEFEND", "Defend Buzz": "AT_DEFEND",
           "Swoop In Pause": "AT_ENTRY", "Swoop In": "AT_ENTRY", "Leave Pause": "AT_LEAVE"},
    primary={"AT_FIRE_READY": "Fire Ready", "AT_DIVE": "Fire", "AT_DEFEND": "Defend Ready",
             "AT_ENTRY": "Swoop In Pause", "AT_LEAVE": "Leave Pause"},
    branch={},
    branches={"AT_FIRE_READY": ("main",), "AT_DIVE": ("main",), "AT_DEFEND": ("main",), "AT_ENTRY": ("main",),
              "AT_LEAVE": ("main",)},
    aim=frozenset(),
    body=("Song Automaton Tiny(Clone)", "Song Automaton Tiny"),
    table="attack_range_tiny",
    parked=("Dead", "Dormant", "Sleep", "Wait"),      # its "Ready" is the formation flight (in play)
    custom=custom,
    attach=attach,
    left_out=(
        ("Fire Ready", "the dive's side and start point are pending until the Fire entry (group 2): only the antic "
         "body is drawn, the dive from Fire on"),
        ("Ready", "the next move (Fire Ready on the Maestro's FIRE, Defend Ready) is the Maestro's call (group 2); "
         "the formation flight (6 u/s) is drawn as the body now"),
    ),
)

SESSIONS = ("20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
CASES = ()
