"""The Clawmaiden's spear (entity type "Spear", its Control FSM: Idle > Antic Pause > Antic > Fire > Explode): an
attack-range type of its own, drawn on its DECIDED path (Task "attack range: all types", stage B; the rules of
forum.md sec. 31 / C:/ssbot/data/m2_forum_aimics/spear/workflow_result.json, the constants of tools.aim_ics SPEAR).

  decision  Get Antic Angle = the frame the spear enters Antic Pause (the Clawmaiden's Spear Cast Antic -> Spear Fire):
            aim = the spear transform -> the hero transform + (0, 0.25), its elevation toward her facing (the spear's
            flip, the same as hers in R0 dev) clamped to +-45 deg (a hero behind her gets the nearer edge). Before it
            (her Spear Cast Antic) the aim is pending: not drawn.
  Antic     Antic Pause 0.150-0.167 s still, then Antic 0.700-0.717 s: back along -aim at 30 u/s x0.875 per 50 Hz step
            (3.645 u in the open); harmless. Once in Antic its observed velocity gives the aim exactly.
  Fire      37 u/s along the aim, then ChaseObjectWisp toward the hero transform (force 45 x the offset clamped to
            length 1; the speed clamped to [its running max, 50] before each step): simulated toward the hero's
            CURRENT position (the hero's later motion is the error, reported). Collider: the triangle tip 3.759 u ahead
            of the transform, base 1.776 u behind, 1.256 u wide.
  Explode   when its contact point (1.45 u ahead) crosses the floor (y 3.0) or a wall (x 14.2 / 49.1) from 0.1 s
            after the Fire entry, or the triangle reaches the hero: the circle r 3.5529 0.9 u ahead of the transform
            for 0.108 s.
The fire time is known to a window (Antic Pause + Antic 0.85-0.88 s; 0.70-0.72 s once in Antic): the union of its
ends. No template: spear_place computes every bin (the table keeps only the meta).
"""
import math

from ssbot.combat.are_spec import EnemySpec

FDT = 0.02                       # the 50 Hz physics step
AIM_DY = 0.25
FAN = math.radians(45.0)
PAUSE = (0.150, 0.167)
ANTIC = (0.700, 0.717)
ANTIC_V, ANTIC_DECEL = 30.0, 0.875
V0, V_MAX, ACC = 37.0, 50.0, 45.0
TIP, BASE, HALF_W = 3.759, 1.776, 0.628
CONTACT, DETECT = 1.45, 0.1
FLOOR_Y, WALLS = 3.0, (14.2, 49.1)
EXPL_R, EXPL_ALONG, EXPL_S = 3.5529, 0.9, 0.108
FLIGHT_MAX = 1.5                 # s (none recorded over 0.87)
HERO_HALF, HERO_DY = (0.2277, 1.1249), -0.38


def aim_rule(sx: float, sy: float, s: int, hero) -> tuple[float, float]:
    """The unit aim at the decision from the spear (sx, sy), facing s, the hero transform hero = (x, y)."""
    if hero is None:
        return float(s), 0.0
    dx, dy = (float(hero[0]) - sx) * s, float(hero[1]) + AIM_DY - sy
    a = math.atan2(dy, dx)
    a = max(min(a, FAN), -FAN)
    return s * math.cos(a), math.sin(a)


def on_step(inst, st, prev, T, x, y, s, hero_x, hero_y, tin, vx):
    """The decision (the first Antic Pause frame: the aim rule) and the entry times of Antic / Fire / Explode."""
    ex = inst.extra
    if "aim" not in ex:
        ex["aim"] = (T, *aim_rule(x, y, s, None if hero_x is None else (hero_x, hero_y)))
    if st != prev and st in ("Antic", "Fire", "Explode") and st not in ex:
        ex[st] = T - max(float(tin or 0.0), 0.0)


def triangle(px: float, py: float, ux: float, uy: float):
    import numpy as np
    nx, ny = -uy, ux
    return np.array([[px + ux * TIP, py + uy * TIP], [px - ux * BASE + nx * HALF_W, py - uy * BASE + ny * HALF_W],
                     [px - ux * BASE - nx * HALF_W, py - uy * BASE - ny * HALF_W]])


def _hits_hero(tri, hero) -> bool:
    """The triangle against the hero hurtbox (separating axes)."""
    import numpy as np
    hx, hy = float(hero[0]), float(hero[1]) + HERO_DY
    box = np.array([[hx - HERO_HALF[0], hy - HERO_HALF[1]], [hx + HERO_HALF[0], hy - HERO_HALF[1]],
                    [hx + HERO_HALF[0], hy + HERO_HALF[1]], [hx - HERO_HALF[0], hy + HERO_HALF[1]]])
    axes = [(1.0, 0.0), (0.0, 1.0)]
    for i in range(3):
        e = tri[(i + 1) % 3] - tri[i]
        axes.append((-e[1], e[0]))
    for a in axes:
        p, q = tri @ a, box @ a
        if p.max() < q.min() or q.max() < p.min():
            return False
    return True


def flight(px: float, py: float, vx: float, vy: float, smin: float, t_fire: float, t: float, hero,
           first: bool) -> tuple:
    """The spear from (px, py) with velocity (vx, vy) at game time t_fire (first: the Fire entry, its OnEnter force)
    to game time t: ("fire", x, y, ux, uy) in flight, ("expl", cx, cy, t_expl) once it exploded (its circle centre),
    homing toward the hero held at `hero` (straight when None)."""
    fx = fy = 0.0

    def home(px_, py_):
        if hero is None:
            return 0.0, 0.0
        dx, dy = float(hero[0]) - px_, float(hero[1]) - py_
        d = math.hypot(dx, dy)
        if d > 1.0:
            dx, dy = dx / d, dy / d
        return ACC * dx, ACC * dy
    if first:
        fx, fy = home(px, py)
    n = 0
    tt = t_fire
    sp = math.hypot(vx, vy)
    ux, uy = (vx / sp, vy / sp) if sp > 1e-6 else (1.0, 0.0)
    # the 50 Hz steps done by the render frame at t: its phase is unknown, so the nearest whole count (floor lagged
    # by up to one step, 0.74-1.0 u: the motion over the first 2 Fire frames is p50 46.9 u/s at 37 u/s)
    while tt + 0.5 * FDT <= t + 1e-9 and tt - t_fire < FLIGHT_MAX:
        gx, gy = home(px, py)
        fx += gx
        fy += gy
        s = math.hypot(vx, vy)
        if s > V_MAX:
            vx, vy, s = vx * V_MAX / s, vy * V_MAX / s, V_MAX
        if 1e-6 < s < smin:
            vx, vy, s = vx * smin / s, vy * smin / s, smin
        smin = max(smin, s)
        vx += fx * FDT
        vy += fy * FDT
        fx = fy = 0.0
        px, py = px + vx * FDT, py + vy * FDT
        tt += FDT
        n += 1
        s = math.hypot(vx, vy)
        ux, uy = vx / s, vy / s
        if hero is not None and _hits_hero(triangle(px, py, ux, uy), hero):
            return ("expl", px + ux * EXPL_ALONG, py + uy * EXPL_ALONG, tt)
        if tt - t_fire >= DETECT - 1e-9:
            cx, cy = px + ux * CONTACT, py + uy * CONTACT
            pen = -1.0
            if cy <= FLOOR_Y and uy < 0:
                pen = (FLOOR_Y - cy) / -uy
            if cx <= WALLS[0] and ux < 0:
                pen = max(pen, (WALLS[0] - cx) / -ux)
            if cx >= WALLS[1] and ux > 0:
                pen = max(pen, (cx - WALLS[1]) / ux)
            if pen >= 0:
                pen = min(pen, s * FDT)
                ex, ey = px - ux * pen, py - uy * pen
                return ("expl", ex + ux * EXPL_ALONG, ey + uy * EXPL_ALONG, tt)
    return ("fire", px, py, ux, uy)


def antic_path(px: float, py: float, ux: float, uy: float, t0: float, t1: float, started: bool,
               vx: float | None = None, vy: float | None = None) -> tuple[float, float]:
    """The spear's position at game time t1 flying back from (px, py) at t0 (started: already in Antic with the
    observed velocity (vx, vy); else it enters Antic at t0 with 30 x 0.875 u/s along -aim)."""
    if not started or vx is None:
        vx, vy = -ux * ANTIC_V * ANTIC_DECEL, -uy * ANTIC_V * ANTIC_DECEL
    t = t0
    while t + 0.5 * FDT <= t1 + 1e-9:
        vx *= ANTIC_DECEL
        vy *= ANTIC_DECEL
        px, py = px + vx * FDT, py + vy * FDT
        if py < FLOOR_Y + 0.5:
            py, vy = FLOOR_Y + 0.5, 0.0
        t += FDT
    return px, py


def region(state: str, st_t0: float, pos, vel, aim, hero, T: float, t: float) -> list:
    """The spear's damaging polygons at game time t >= T seen in `state` (entered at st_t0) at pos / vel now."""
    px, py = float(pos[0]), float(pos[1])
    vx, vy = (float(vel[0]), float(vel[1])) if vel is not None else (0.0, 0.0)
    out = []
    if state == "Explode":
        return out                               # spear_place draws the observed explosion (expl_at)
    if state == "Fire":
        sp = math.hypot(vx, vy)
        if sp < 1e-3:
            return out
        r = flight(px, py, vx, vy, sp, T, t, hero, first=False)
        return _draw(r, t, out)
    ux, uy = aim
    sp = math.hypot(vx, vy)
    moving = state == "Antic" and sp > 0.5
    if moving:
        ux, uy = -vx / sp, -vy / sp              # it flies back exactly along -aim
    for p, a in zip(PAUSE, ANTIC):               # the two ends of the fire-time window
        ta = T if state == "Antic" else max(st_t0 + p, T)
        tf = max((st_t0 if state == "Antic" else st_t0 + p) + a, T)
        if t < tf:
            continue
        ax, ay = antic_path(px, py, ux, uy, ta, tf, moving, vx, vy)
        r = flight(ax, ay, ux * V0, uy * V0, V0, tf, t, hero, first=True)
        _draw(r, t, out)
    return out


def _draw(r, t: float, out: list) -> list:
    from ssbot.combat.attack_range import circle_poly
    if r[0] == "fire":
        out.append(triangle(r[1], r[2], r[3], r[4]))
    elif t <= r[3] + EXPL_S + 1e-9:
        out.append(circle_poly(r[1], r[2], EXPL_R))
    return out


def spear_place(tab, fam, branch, b, anchor, s, hero_du, now, b_now, dec, st_now, ctx):
    """Every bin of SP_SPEAR from the rules above (k = 0: the triangle now in Fire, the explosion while it is lit)."""
    from ssbot.combat.attack_range import FT, empty_mask, poly_mask
    if fam != "SP_SPEAR" or now is None or b_now is None:
        return None
    inst = ctx.get("inst")
    T = float(ctx["T"])
    t = T + (b - b_now) * FT
    ex = inst.extra if inst is not None else {}
    # the entry time of the state seen now (an eval row reads the whole instance's record: by state, not the last)
    st_t0 = (inst.t0 if inst is not None else T) if st_now == "Antic Pause" else ex.get(st_now, T)
    aim = ex.get("aim", (0.0, float(s), 0.0))[1:]
    if st_now == "Explode":
        te = ex.get("Explode", st_t0)
        if te <= T + 1e-9 and t <= te + EXPL_S + 1e-9 and ex.get("expl_at") is not None:
            from ssbot.combat.attack_range import circle_poly
            return poly_mask([circle_poly(*ex["expl_at"], EXPL_R)], tab.cell)
        return empty_mask()
    polys = region(st_now or "Antic Pause", st_t0, now, ctx.get("vel"), aim, ctx.get("hero"), T, t)
    return poly_mask(polys, tab.cell) if polys else empty_mask()


def attach(c: dict, tracks: list) -> None:
    """The spear's truth: its Fire collider as the triangle along its velocity (the cache keeps the rotated
    triangle's AABB only), the explosion damager (the 7.106 u circle) on the frames it hurts after the Explode entry;
    and tr["vy"]."""
    import numpy as np
    box = c["c_box"]
    w = box[:, 2] - box[:, 0]
    dsel = np.nonzero((np.abs(w - 2 * EXPL_R) < 0.03) & (c["c_dealt"] > 0))[0]
    dfi = c["e_fi"][c["c_ei"][dsel]]
    tk = list(c["types"]).index("Spear")
    rows_all = np.nonzero(c["e_tk"] == tk)[0]
    for tr in tracks:
        rows = rows_all[c["e_iid"][rows_all] == tr["iid"]]
        rows = rows[np.argsort(c["e_fi"][rows], kind="stable")]
        vy = c["e_vy"][rows].astype(np.float64)
        tr["vy"] = vy
        for j in range(len(tr["st"])):
            cols = []
            for nm, bx in tr["cols"][j]:
                if nm == "Spear":
                    sp = math.hypot(tr["vx"][j], vy[j])
                    if sp > 1e-3:
                        bx = triangle(tr["x"][j], tr["y"][j], tr["vx"][j] / sp, vy[j] / sp).reshape(-1)
                cols.append((nm, bx))
            tr["cols"][j] = cols
        for j in range(1, len(tr["st"])):
            if tr["st"][j] == "Explode" and tr["st"][j - 1] != "Explode":
                fi0 = int(tr["fi"][j])
                k = dsel[(dfi >= fi0 - 1) & (dfi <= fi0 + 12)]
                for x in k:
                    b = box[x]
                    cx, cy = 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])
                    if math.hypot(cx - tr["x"][j], cy - tr["y"][j]) > 2.5:
                        continue
                    jj = int(np.searchsorted(tr["fi"], int(c["e_fi"][c["c_ei"][x]])))
                    if jj < len(tr["fi"]) and int(tr["fi"][jj]) == int(c["e_fi"][c["c_ei"][x]]):
                        tr["cols"][jj].append(("HZ:spear explosion", b.astype(np.float64)))


def spear_step(inst, st, prev, T, x, y, s, hero_x, hero_y, tin, vx):
    on_step(inst, st, prev, T, x, y, s, hero_x, hero_y, tin, vx)
    # the explosion's centre: 0.9 u ahead of the Explode frame's transform along the last flight direction (the motion
    # between the last two Fire frames: the velocity's direction; the Explode frame itself is backed to the contact,
    # its motion direction is off by p50 0.69 u at the centre, the velocity's by the 0.065 u across offset only)
    ex = inst.extra
    if st == "Fire":
        ex["_fire"] = (ex["_fire"][-1], (x, y)) if "_fire" in ex else ((x, y),)
    if st == "Explode" and prev == "Fire" and "expl_at" not in ex and "_fire" in ex:
        (ax, ay), (bx, by) = ex["_fire"] if len(ex["_fire"]) == 2 else (ex["_fire"][0], (x, y))
        d = math.hypot(bx - ax, by - ay)
        ux, uy = ((bx - ax) / d, (by - ay) / d) if d > 1e-6 else (float(s), 0.0)
        ex["expl_at"] = (x + ux * EXPL_ALONG, y + uy * EXPL_ALONG)


SPEC = EnemySpec(
    type_key="Spear", short="Spear",
    fam_states={"SP_SPEAR": frozenset({"Antic Pause", "Antic", "Fire", "Explode"})},
    start={"Antic Pause": "SP_SPEAR", "Antic": "SP_SPEAR", "Fire": "SP_SPEAR"},
    primary={"SP_SPEAR": "Antic Pause"},
    branch={},
    branches={"SP_SPEAR": ("main",)},
    aim=frozenset(),
    body="Spear",
    table="attack_range_spear",
    face_names=("Spear",),
    on_step=spear_step,
    place_fn=spear_place,
    left_out=(("the Clawmaiden's Spear Cast Antic", "the aim is pending until Get Antic Angle (the spear's Antic "
               "Pause entry)"),),
)

SESSIONS = ("20261004_002749", "20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
# the flights of the person's sessions (the per-family picks land on the long Explode tail): first / middle / last
# Fire frame, and one Antic frame before each
CASES = tuple((s, f, f"spear {w}") for s, fs in (("20261009_085824", (13140, 13153, 13167, 13183)),
                                                 ("20261009_161454", (13185, 13198, 13216, 13234)),
                                                 ("20261008_231544", (9345, 9360, 9382, 9406)),
                                                 ("20261005_160435", (12980, 12996, 13014, 13032)))
              for f, w in zip(fs, ("antic (decided: the path ahead)", "fire entry", "in flight", "last fire frame")))
