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
import os

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


def _maestro(view, prefer: str | None = None):
    """(x, y, vx, vy) of the Maestro nearest to this Tiny now (prefer: a Maestro in that first-FSM state first: the
    one whose Fire Antic sent this Tiny's FIRE READY), or None."""
    if view.track is not None:
        tr, j = view.track, view.j
        if "mx" not in tr or not np.isfinite(tr["mx"][j]):
            return None
        return float(tr["mx"][j]), float(tr["my"][j]), float(tr["mvx"][j]), float(tr["mvy"][j])
    from ssbot.combat.attack_range import _first_state, _parked
    best = None
    for e in view.ents or ():
        if e.get("type_key") != MAESTRO or _parked(e):
            continue
        p = e.get("pos") or (0.0, 0.0)
        v = e.get("vel") or (0.0, 0.0)
        d = (float(p[0]) - view.x) ** 2 + (float(p[1]) - view.y) ** 2
        if prefer is not None and _first_state(e)[0] != prefer:
            d += 1e6
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


# ------------------------------------------------------------------------------------------------ the dive, early
# The chain (FSM: Song Pilgrim Maestro "Fire Antic" / "Slash 1"; Song Automaton Tiny prefab "Control", decoded from
# localpoolprefabs_assets_areahang.bundle; forum.md sec. 40). At the Maestro's Fire Antic entry it faces the hero, picks
# one ready Tiny at random (GetRandomChild of Ready Flies) and sends it FIRE READY the same frame; it recoils 15 u/s
# back (DecelerateV2 0.9 per physics step) and waits 0.7 s, then Slash 1 sends FIRE. In Fire Ready the Tiny flies to
# the Maestro's "Slash Point" (local (1.87, 1.88): behind the Maestro, away from the hero at the antic entry, and
# above) with DistanceFlySmooth (speedMax 7, force 20, targetRadius 0.15, deceleration 0.9). At FIRE it faces the hero
# (the dive side: the hero's side of the Tiny THEN), sets (24 forward, -39) u/s and decelerates y by 0.945 per step;
# a 2 u ray down hitting the floor -> Brake (y x 0.8 per step, x kept); "passed the hero by 5 u" (in its facing, once
# Is Active: 0.5 s into Fire / 0.25 s into Brake), 1.0 s (Fire, Brake) -> Pull Up (x x 0.935 per step, y up by 1 per
# step to 17 u/s, 0.35 s) -> Return (DistanceFlySmooth to the Maestro, speedMax 15, force 40) until within 5 u. A
# side wall -> Wall Bonk (back at 8 u/s, 0.35 s) -> Return. Everything runs on the 50 Hz physics step; nothing but the hero's x at FIRE (the side) and
# while it slides (the 5 u pass) is left open once Fire Ready has started.
FIXED_DT = 0.02
SLASH_POINT = (1.87, 1.88)
# FIRE: the antic's Wait 0.7 s counts whole frames, so the Fire state starts 0.7 s + one frame after the antic
# entry (R0 dev 60 Hz: 0.716-0.717, 7,769 / 7,769; the person's 0.5x sessions, 120 game frames per game s: 0.700-0.708);
# 0.8 frame puts the dive's first moves on the recorded frames (R0 dev 6 fights: path p50 0.24 u vs 0.62 at 1 frame)
ANTIC_WAIT = 0.7
ANTIC_FRAMES = 0.8
FR_FLY = (7.0, 20.0, 0.15, 0.9)    # Fire Ready: speedMax, force (mass 1), targetRadius, deceleration
RET_FLY = (15.0, 40.0, 1.0, 0.9)   # Return
M_DECEL = 0.9
FIRE_V = (24.0, -39.0)
FIRE_DY = 0.945
BRAKE_DY = 0.8
BRAKE_Y = 5.0                      # the Tiny's y when the 2 u ray down meets the arena floor (R0 dev Brake entries)
BONK_V = 8.0                       # Wall Bonk: bounced back at 8 u/s, x x 0.935 and y x 0.91 per step, 0.35 s
BONK_D = (0.935, 0.91)
BONK_T = 0.35
PULL_DX = 0.935
PULL_VY = 17.0
PULL_T = 0.35
PASS_U = 5.0
FIRE_ACTIVE, BRAKE_ACTIVE, FIRE_MAX, BRAKE_MAX = 0.5, 0.25, 1.0, 1.0
RET_END = 5.0
SLASH_V = (10.0, -0.5)             # the Maestro's Slash 1 lunge toward the hero (decays 0.9 per step after it)
# the hero's horizontal reach before FIRE (the side) and while the Tiny slides: R0 dev / person p99 of |hero dx| over
# the remaining time (u per s of it, forum.md sec. 40); the other side is drawn when the hero can still cross
HERO_REACH = 9.0


def _clamp1(dx: float, dy: float, m: float = 1.0) -> tuple:
    d = math.hypot(dx, dy)
    return (dx, dy) if d <= m or d == 0.0 else (dx * m / d, dy * m / d)


def _fly(x, y, vx, vy, tx, ty, p) -> tuple:
    """One physics step of DistanceFlySmooth (distance 0) toward (tx, ty): the force on the clamped velocity, then the
    move; inside targetRadius the velocity decays."""
    vmax, force, rad, dec = p
    dx, dy = tx - x, ty - y
    if math.hypot(dx, dy) >= rad:
        fx, fy = _clamp1(dx, dy)
        vx, vy = _clamp1(vx, vy, vmax)
        vx, vy = vx + fx * force * FIXED_DT, vy + fy * force * FIXED_DT
    else:
        vx, vy = vx * dec, vy * dec
    return x + vx * FIXED_DT, y + vy * FIXED_DT, vx, vy


def simulate(phase: str, x: float, y: float, vx: float, vy: float, tph: float, m: tuple, sm: int, hero_x: float,
             t_fire: float = 0.0, side: int | None = None, active: bool = False, horizon: float = 2.5) -> list:
    """The chain from now, one row per physics step: [(tau, x, y, phase)] (tau: s from now; the first row is now).
    phase: "ready" (Fire Ready, FIRE in t_fire s), "fire", "brake", "pull", "ret" (tph: time in that phase);
    m = the Maestro (x, y, vx, vy) now, sm = its facing at the antic entry (+1: the hero was to its right), hero_x =
    the hero's x, held (at FIRE: the side unless `side` is given; while sliding: the 5 u pass)."""
    mx, my, mvx, mvy = m
    out = [(0.0, x, y, phase)]
    s = side if side is not None else (1 if vx >= 0 else -1)
    tau = 0.0
    n = int(horizon / FIXED_DT)
    for _ in range(n):
        tau += FIXED_DT
        tph += FIXED_DT
        if phase == "ready":
            mvx, mvy = mvx * M_DECEL, mvy * M_DECEL
            mx, my = mx + mvx * FIXED_DT, my + mvy * FIXED_DT
            x, y, vx, vy = _fly(x, y, vx, vy, mx - sm * SLASH_POINT[0], my + SLASH_POINT[1], FR_FLY)
            if tau >= t_fire - 1e-6:
                s = side if side is not None else (1 if hero_x >= x else -1)
                phase, tph = "fire", 0.0
                vx, vy = s * FIRE_V[0], FIRE_V[1] * FIRE_DY
                mvx, mvy = sm * SLASH_V[0], SLASH_V[1]
        elif phase in ("fire", "brake"):
            vy *= FIRE_DY if phase == "fire" else BRAKE_DY
            x, y = x + vx * FIXED_DT, y + vy * FIXED_DT
            mvx, mvy = mvx * M_DECEL, mvy * M_DECEL
            mx, my = mx + mvx * FIXED_DT, my + mvy * FIXED_DT
            if phase == "fire" and y <= BRAKE_Y:
                phase, tph = "brake", 0.0
            active = active or tph >= (FIRE_ACTIVE if phase == "fire" else BRAKE_ACTIVE)
            if x <= X_WALLS[0] or x >= X_WALLS[1]:
                x = min(max(x, X_WALLS[0]), X_WALLS[1])
                phase, tph, vx = "bonk", 0.0, -s * BONK_V
            elif (active and s * (x - (hero_x + s * PASS_U)) >= 0) or tph >= (FIRE_MAX if phase == "fire" else BRAKE_MAX):
                phase, tph = "pull", 0.0
                vy = min(vy + 1.0, PULL_VY)
        elif phase == "pull":
            vx *= PULL_DX
            vy = min(vy + 1.0, PULL_VY)
            x, y = x + vx * FIXED_DT, y + vy * FIXED_DT
            if x <= X_WALLS[0] or x >= X_WALLS[1]:
                x = min(max(x, X_WALLS[0]), X_WALLS[1])
                phase, tph, vx = "bonk", 0.0, -s * BONK_V
            elif tph >= PULL_T - 1e-6:
                phase, tph = "ret", 0.0
        elif phase == "bonk":
            vx, vy = vx * BONK_D[0], vy * BONK_D[1]
            x, y = min(max(x + vx * FIXED_DT, X_WALLS[0]), X_WALLS[1]), y + vy * FIXED_DT
            if tph >= BONK_T - 1e-6:
                phase, tph = "ret", 0.0
        elif phase == "ret":
            x, y, vx, vy = _fly(x, y, vx, vy, mx, my, RET_FLY)
            if math.hypot(x - mx, y - my) <= RET_END:
                out.append((tau, x, y, "done"))
                break
        out.append((tau, x, y, phase))
    return out


def at(rows: list, tau: float) -> tuple:
    """(x, y) of a simulate() row list at tau s from now (linear between the physics steps)."""
    if tau <= 0 or len(rows) == 1:
        return rows[0][1], rows[0][2]
    i = min(int(tau / FIXED_DT), len(rows) - 2)
    a, b = rows[i], rows[i + 1]
    w = min(max((tau - a[0]) / max(b[0] - a[0], 1e-9), 0.0), 1.0)
    return a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w


def antic_state(view):
    """While a Tiny is in Fire Ready: (t0 (the antic entry, game time), the Maestro now (x, y, vx, vy), sm (its facing
    at the antic entry: the hero's side of it then)), or None. Live: kept per Tiny from its first Fire Ready frame in
    the type memory; offline: from the track's first Fire Ready frame of this run (attach adds the Maestro)."""
    t0 = view.T - (view.tin or 0.0)
    if view.track is not None:
        tr, j = view.track, view.j
        if "mx" not in tr or not np.isfinite(tr["mx"][j]):
            return None
        j0 = j
        while j0 > 0 and tr["st"][j0 - 1] == "Fire Ready":
            j0 -= 1
        hx0 = float(tr["hx"][j0])
        mx0 = float(tr["mx"][j0])
        m = (float(tr["mx"][j]), float(tr["my"][j]), float(tr["mvx"][j]), float(tr["mvy"][j]))
        return t0, m, (1 if hx0 >= mx0 else -1)
    m = _maestro(view, prefer="Fire Antic")
    if m is None:
        return None
    mem = view.mem if view.mem is not None else {}
    rec = mem.setdefault("antic", {})
    r = rec.get(view.iid)
    if r is None or abs(r[0] - t0) > 0.05:
        hx = view.hero[0] if view.hero is not None else view.x
        r = rec[view.iid] = (t0, 1 if hx >= m[0] else -1)
    return t0, m, r[1]


def dive_paths(view) -> list:
    """[(rows, sure)] of the chain from now while in Fire Ready (the dive's early path): sure = the hero held where it
    is now (both its side at FIRE and its x while sliding); not sure = the variants the hero can still make: the
    other side when it can cross the predicted FIRE point before FIRE, the longer slide when it moves on along the
    dive. [] when the Maestro is not seen."""
    if view.st != "Fire Ready":
        return []
    a = antic_state(view)
    if a is None:
        return []
    t0, m, sm = a
    hx = view.hero[0] if view.hero is not None else view.x
    t_fire = max(t0 + ANTIC_WAIT + ANTIC_FRAMES * _frame_dt(view) - view.T, 0.0)
    return _cached(view, "ready", lambda: variants(view.x, view.y, view.vx or 0.0, view.vy or 0.0, m, sm, hx,
                                                   t_fire))


def _cached(view, key: str, fn):
    """fn() once per enemy and frame (every look-ahead of a frame reads the same simulation): kept in the track
    offline, in the type memory live (cleared past 64 entries)."""
    store = view.track if view.track is not None else view.mem
    if store is None:
        return fn()
    c = store.setdefault("_sim", {})
    k = (view.iid, view.j if view.track is not None else round(view.T, 6), key)
    r = c.get(k)
    if r is None:
        if len(c) > 64:
            c.clear()
        r = c[k] = fn()
    return r


def _frame_dt(view) -> float:
    """The game time of one game frame now (1/60 s at 1x, 1/120 at the person's 0.5x): live the tracker's feed step
    (CustomView.dt); offline the track's shortest time in state (a state's first frame; the person's caches merge two
    game frames into one row, so their row step is not it)."""
    from ssbot.combat.attack_range import FT
    if view.track is not None:
        tr = view.track
        dt = tr.get("_gdt")
        if dt is None:
            tin = np.asarray(tr["tin"], np.float64)
            tin = tin[tin > 1.0 / 400]
            d = np.diff(np.asarray(tr["T"], np.float64))
            d = d[d > 1e-6]
            dt = tr["_gdt"] = min(float(tin.min()) if len(tin) else FT, float(np.median(d)) if len(d) else FT)
    else:
        dt = view.dt or FT
    return dt if 1.0 / 400 < dt < 0.05 else FT


def variants(x: float, y: float, vx: float, vy: float, m: tuple, sm: int, hx: float, t_fire: float) -> list:
    """dive_paths from a Tiny in Fire Ready at (x, y) moving (vx, vy), FIRE in t_fire s, the Maestro m = (x, y, vx,
    vy) now with its antic facing sm, the hero at x = hx now: [(simulate rows, sure)]."""
    base = simulate("ready", x, y, vx, vy, 0.0, m, sm, hx, t_fire=t_fire)
    out = [(base, True)]
    xf = next((r[1] for r in base if r[3] != "ready"), base[-1][1])
    s = 1 if hx >= xf else -1
    if abs(hx - xf) <= HERO_REACH * t_fire:
        out.append((simulate("ready", x, y, vx, vy, 0.0, m, sm, hx, t_fire=t_fire, side=-s), False))
    # the slide ends 5 u past the hero: the hero moving on along the dive lengthens it (to the timer / the wall)
    far = hx + s * HERO_REACH * (t_fire + FIRE_MAX)
    out.append((simulate("ready", x, y, vx, vy, 0.0, m, sm, far, t_fire=t_fire, side=s), False))
    return out


PHASE = {"Fire": "fire", "Brake": "brake", "Pull Up": "pull"}


def dive_rest(view) -> list:
    """[(rows, sure)] of the rest of a dive under way (Fire / Brake / Pull Up), as dive_paths: sure = the hero held
    (the slide ends 5 u past it), not sure = the longer slide when it moves on along the dive."""
    ph = PHASE.get(view.st)
    if ph is None:
        return []
    m = _maestro(view) or (view.x, view.y + 5.0, 0.0, 0.0)
    vx, vy = view.vx or 0.0, view.vy or 0.0
    s = 1 if vx >= 0 else -1
    hx = view.hero[0] if view.hero is not None else view.x
    tin = view.tin or 0.0
    active = ph == "pull" or tin >= (FIRE_ACTIVE if ph == "fire" else BRAKE_ACTIVE)

    def run():
        out = [(simulate(ph, view.x, view.y, vx, vy, tin, m, s, hx, side=s, active=active), True)]
        if ph != "pull":
            far = hx + s * HERO_REACH * FIRE_MAX
            out.append((simulate(ph, view.x, view.y, vx, vy, tin, m, s, far, side=s, active=active), False))
        return out
    return _cached(view, ph, run)


def _shifted(body: list, x0: float, y0: float, x: float, y: float) -> list:
    return [np.asarray(p, np.float64) + (x - x0, y - y0) for p in body]


def path(view):
    """The type's whole-path hook (attack_range.RangeTracker.ladder with a sweep: the overlay's key 9): (sure Mask,
    maybe Mask) of the body along the chain from now to its return, or None: from Fire Ready on (the dive is then
    drawn from the Maestro's antic entry, 0.7 s before it starts) to the end of its Pull Up."""
    paths = dive_paths(view) or dive_rest(view)
    body = _body(view)
    if not paths or not body:
        return None
    from ssbot.combat.attack_range import poly_mask, union
    sure, maybe = [], []
    for rows, ok in paths:
        polys = [p for r in rows if r[3] not in ("ret", "done") for p in _shifted(body, view.x, view.y, r[1], r[2])]
        (sure if ok else maybe).append(poly_mask(polys, view.tab.cell))
    return union(sure), union(maybe)


def early(view):
    """Fire Ready (and Fire / Brake / Pull Up) at look-ahead k: the body where the chain puts it at t (union over the
    variants dive_paths / dive_rest keep open), or None (no Maestro seen: the kinematic rule)."""
    paths = dive_paths(view) if view.st == "Fire Ready" else dive_rest(view)
    body = _body(view)
    if not paths or not body:
        return None
    from ssbot.combat.attack_range import poly_mask
    tau = max(view.t - view.T, 0.0)
    polys = []
    for rows, _ok in paths:
        x, y = at(rows, tau)
        polys += _shifted(body, view.x, view.y, x, y)
    return poly_mask(polys, view.tab.cell)


# Fire Ready drawn by the chain (SSBOT_TINY_EARLY=0: the old kinematic rule, for the before / after comparison)
EARLY = os.environ.get("SSBOT_TINY_EARLY", "1") != "0"


def custom(view):
    """(the body where the chain puts it (Fire Ready, Fire, Brake, Pull Up: simulate), moved by the orbit (Defend
    Buzz) or by its velocity (the other KINEMATIC states), None); else (None, None)."""
    if view.st != "Defend Buzz" and view.st not in KINEMATIC:
        return None, None
    from ssbot.combat.attack_range import poly_mask
    tau = max(view.t - view.T, 0.0)
    if view.st in KINEMATIC:
        dx, dy = kinematic_shift(view, tau)         # (also keeps the live velocity memory current)
    if EARLY and (view.st == "Fire Ready" or view.st in PHASE):
        m = early(view)
        if m is not None:
            return m, None
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
    gives each frame the nearest Maestro in play (mx, my, mvx, mvy; NaN without one; in Fire Ready the one whose Fire
    Antic started with it)."""
    types = list(c["types"])
    states = c["states"]
    mrows: dict = {}
    if MAESTRO in types:
        for x in np.nonzero(c["e_tk"] == types.index(MAESTRO))[0]:
            s = c["e_st"][x]
            nm = str(states[s]) if s >= 0 else ""
            if not nm or c["e_hidden"][x] or any(w in nm for w in ("Ready", "Dormant", "Sleep", "Wait")):
                continue
            # the 5th field: the game time its Fire Antic started (NaN in other states)
            ta = float(c["T"][c["e_fi"][x]] - c["e_tin"][x]) if nm == "Fire Antic" else math.nan
            mrows.setdefault(int(c["e_fi"][x]), []).append((float(c["e_x"][x]), float(c["e_y"][x]),
                                                            float(c["e_vx"][x]), float(c["e_vy"][x]), ta))
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
                    # a Tiny in Fire Ready: the Maestro whose Fire Antic started with it (it sent the FIRE READY)
                    t0 = float(tr["T"][n] - tr["tin"][n]) if tr["st"][n] == "Fire Ready" else math.nan
                    M[n] = min(ms, key=lambda q: (not abs(q[4] - t0) < 0.05,
                                                  (q[0] - tr["x"][n]) ** 2 + (q[1] - tr["y"][n]) ** 2))[:4]
            tr["mx"], tr["my"], tr["mvx"], tr["mvy"] = M[:, 0], M[:, 1], M[:, 2], M[:, 3]
            out.append(tr)
    tracks[:] = out


SPEC = EnemySpec(
    type_key="Song Automaton Tiny", short="Tiny",
    fam_states={
        # the antic and the dive it leads to are one family: the dive is drawn from the antic (dive_paths), and a
        # look-ahead from Fire Ready into the dive is this family's, not "the next move"
        "AT_FIRE_READY": frozenset({"Fire Ready", "Fire", "Brake", "Pull Up", "Wall Bonk", "Return"}),
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
        ("Fire Ready", "the dive's side is the hero's side of the Tiny at FIRE (0.72 s after the antic entry): both "
         "sides are drawn while the hero can still cross the predicted FIRE point (HERO_REACH), the slide's end at "
         "the hero now + 5 u and its longest plausible extension"),
        ("Ready", "the next move (Fire Ready on the Maestro's FIRE, Defend Ready) is the Maestro's call (group 2); "
         "the formation flight (6 u/s) is drawn as the body now"),
    ),
)

SESSIONS = ("20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
CASES = ()
