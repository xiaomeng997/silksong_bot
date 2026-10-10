"""Bellbearer (Pilgrim 03 Song) and its bell: attack-range type (Task "attack range: all types", stage B). Families
and rules from the v2 classification (docs/plans/forum_zones_v2.md sec. 1.7, C:/ssbot/data/m2_forum_v2/
workflow_result.json, zone_cases_result.json) and R0 dev measurements (this module's constants):

  CB_THROW   Throw Antic (the aim is decided on its first frame) > Throw (the release, 0.65-0.68 s after the antic
             start in R0 dev) > Recover: the body (0.94 u back / 0.47 u up in the antic, p95); hits never cancel it
  CB_EVADE   Evade Antic (4-5 frames, faces the hero) > Evade: 32 u/s BACKWARD by the facing (x0.9 per frame, 4.3 u)
             and -8 u/s down (drop 1.25 u, max 3.46): backward from the observed facing, so an evade that starts
             facing away goes into the hero; the drop is what reaches a hero below
  CB_ENTRY   Fly In: the body
  idle       In Range / Out of Range / Insta Throw? / Startle: the exact body now ("Pilgrim 03 Song" 1.32 x 1.53)

The bell ("Throwing Bell" entities, circle r 0.425, the AABB 0.85 x 0.85) is drawn through the custom hook:
  in flight   on its real path: from its observed position and velocity now, 50 Hz semi-implicit Euler with g 60
              (vy -1.2 per step), one floor bounce (centre y 3.53: vy back to 20), the second floor contact ends it,
              the walls (x 14.435 / 48.565) send it back at 10 u/s; a bell that does not hurt now (hit back by the
              nail: Nail Hit, dealt 0 from then on) is not drawn. R0 dev k 12: p50 0.0 u, p90 0.42, p95 0.61.
  decided     before the release (Throw Antic, no bell of this throw yet): the arc decided at the antic start, Spit X =
              clamp(1.15 (hero x - x) + U(-1, 1), +-15) with abs(vx) >= 4, vy 20, spawned at the thrower + (0.94 u
              toward vx, -0.5 u) at a release time in the R0 dev window: the union over U and the release times.
Offline (tools.attack_range_build) the bells are attached to their thrower by the spawn rule (attach) and their
hurting frames are the thrower's "HZ:bell" truth; live, a bell belongs to the Bellbearer nearest to it when first seen.
"""
from __future__ import annotations

import math

import numpy as np

from ssbot.combat.are_spec import EnemySpec

FT = 1.0 / 60.0
BELL = "Throwing Bell"
BELL_R = 0.425
STEP = 0.02                        # the bell's physics step (50 Hz)
G_STEP = 1.2                       # g 60 u/s^2 per step
VY0 = 20.0
FLOOR_Y = 3.53                     # the bell's centre on the floor (where it bounces)
END_Y = 3.43                       # ... where it lies at its second floor contact, hurting 1-2 frames before it ends
END_HOLD = 2                       # steps
WALLS = (14.435, 48.565)           # its centre at the arena walls
WALL_VX = 10.0
SPAWN = (0.94, -0.5)               # from the thrower at the release: 0.94 u toward vx, 0.5 u down (1,648 / 1,660)
RELEASE = (0.649, 0.683)           # s after the antic start: the bell's spawn = the Throw entry (R0 dev, the first
#                                    20 fights: 1,660 throws, p50 0.666; the v2 classification's 0.617-0.721 is wider)
SPIT_GAIN = 1.15
SPIT_MAX = 15.0
SPIT_MIN = 4.0
SPIT_U = (-1.0, -0.5, 0.0, 0.5, 1.0)


def spit_vx(du_x: float, u: float) -> float:
    """The throw rule: the bell's vx for the hero's x offset du_x (hero x - x) at the antic start and the random u."""
    v = min(max(SPIT_GAIN * du_x + u, -SPIT_MAX), SPIT_MAX)
    if abs(v) < SPIT_MIN:
        v = math.copysign(SPIT_MIN, v if v != 0 else 1.0)
    return v


def bell_path(x: float, y: float, vx: float, vy: float, tau: float, bounced: bool):
    """The bell's centre tau s from (x, y, vx, vy), or None once it has ended (its second floor contact)."""
    n = int(round(max(tau, 0.0) / STEP))
    for i in range(n):
        vy -= G_STEP
        x += vx * STEP
        y += vy * STEP
        if y < FLOOR_Y:
            if bounced:                         # it lies on the floor, still hurting, for END_HOLD more steps
                return (x, END_Y) if n - 1 - i <= END_HOLD else None
            y, vy, bounced = FLOOR_Y, VY0, True
        if x < WALLS[0]:
            x, vx = WALLS[0], WALL_VX
        elif x > WALLS[1]:
            x, vx = WALLS[1], -WALL_VX
    return x, y


def _circles(cs) -> object:
    from ssbot.combat.attack_range import circle_poly, poly_mask
    return poly_mask([circle_poly(cx, cy, BELL_R) for cx, cy in cs])


def predicted_arc(inst, T: float, t: float, x: float, y: float) -> list:
    """The decided bell of a throw not released yet (Throw Antic): its centres at time t over the release window
    (every frame of it not before now) and U, spawned from the thrower's position now."""
    du_x = inst.hero_du * inst.s
    out = []
    r0, r1 = inst.t0 + RELEASE[0], inst.t0 + RELEASE[1]
    n = int(round((r1 - r0) / FT))
    for i in range(n + 1):
        tr = r0 + i * FT
        if tr < T - 1e-9 or tr > t + 1e-9:
            continue
        for u in SPIT_U:
            vx = spit_vx(du_x, u)
            p = bell_path(x + math.copysign(SPAWN[0], vx), y + SPAWN[1], vx, VY0, t - tr, False)
            if p is not None:
                out.append(p)
    return out


# ------------------------------------------------------------------------------------------------ the hook

EVADE_DECAY = 0.9                  # Evade: the velocity x0.9 per frame (the FSM's decelerate); R0 dev k 12 position
#                                    error p50 0.16 / p90 0.47 u (the template's median path: coverage 87 %)


def _body(view) -> list:
    """Its body colliders now (CustomView.body: the tracker / the builder fill it)."""
    return list(view.body or [])


def evade_body(view):
    """In Evade: the body now carried by its decaying velocity (or None)."""
    from ssbot.combat.attack_range import poly_mask
    body = _body(view)
    if not body:
        return None
    n = max(view.t - view.T, 0.0) / FT
    g = (1.0 - EVADE_DECAY ** n) / (1.0 - EVADE_DECAY) * FT
    d = ((view.vx or 0.0) * g, (view.vy or 0.0) * g)
    return poly_mask([p + d for p in body], view.tab.cell)


def custom(view):
    """(the evading body (Evade) or None, the bells this Bellbearer owns at view.t): in flight on their simulated real
    path, or (before the release) the decided arc."""
    if view.track is not None:
        cs = _offline_bells(view)
    else:
        cs = _live_bells(view)
    if view.inst is not None and view.inst.fam == "CB_THROW" and view.st == "Throw Antic" \
            and not _seen_this_throw(view):
        cs += predicted_arc(view.inst, view.T, view.t, view.x, view.y)
    rep = evade_body(view) if view.st == "Evade" else None
    return rep, (_circles(cs) if cs else None)


def _seen_this_throw(view) -> bool:
    """A bell of the current throw is already out (offline: a flight attributed to this instance has started)."""
    if view.track is None:
        return False
    for fl in view.track.get("bells", ()):
        if abs(fl["t_ant"] - view.inst.t0) < 2 * FT and fl["T"][0] <= view.T + 1e-9:
            return True
    return False


def _offline_bells(view) -> list:
    out = []
    for fl in view.track.get("bells", ()):
        Tf = fl["T"]
        if Tf[0] > view.T + 1e-9 or Tf[-1] < view.T - 1e-9:
            continue
        a = int(np.searchsorted(Tf, view.T + 1e-9, "right")) - 1
        if a < 0 or Tf[a] < view.T - 2.5 * FT or not fl["hurt"][a]:
            continue
        p = bell_path(float(fl["x"][a]), float(fl["y"][a]), float(fl["vx"][a]), float(fl["vy"][a]),
                      view.t - float(Tf[a]), bool(fl["bounced"][a]))
        if p is not None:
            out.append(p)
    return out


def _hurting(e: dict) -> bool:
    for c in e.get("cols") or e.get("colliders") or ():
        d = c.get("damage") or {}
        if c.get("enabled", True) and int(d.get("dealt") or 0) > 0:
            return True
    return False


def _bell_state(e: dict) -> str | None:
    for f in e.get("fsms") or ():
        return f.get("state")
    return None


def _live_bells(view) -> list:
    """The bells in flight now that belong to this Bellbearer (the nearest one when first seen), on their path."""
    mem = view.mem if view.mem is not None else {}
    if mem.get("T") != view.T:                      # once per frame: attribute new bells, forget ended ones
        mem["T"] = view.T
        owner = mem.setdefault("owner", {})
        bounced = mem.setdefault("bounced", {})
        from ssbot.combat.attack_range import _parked
        throwers = [(float((e.get("pos") or (0, 0))[0]), float((e.get("pos") or (0, 0))[1]), int(e.get("iid") or -1))
                    for e in view.ents or () if e.get("type_key") == SPEC.type_key and not _parked(e)]
        live = {}
        for e in view.ents or ():
            if e.get("type_key") != BELL or e.get("hidden"):
                continue
            st = _bell_state(e)
            if st in (None, "Deactivate"):
                continue
            bid = int(e.get("iid") or -1)
            p = e.get("pos") or (0.0, 0.0)
            if bid not in owner and throwers:
                owner[bid] = min(throwers, key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2)[2]
            v = e.get("vel") or (0.0, 0.0)
            if st == "Bounce" and float(v[1]) > 5.0:
                bounced[bid] = True
            if st != "Nail Hit" and _hurting(e):
                live[bid] = (float(p[0]), float(p[1]), float(v[0]), float(v[1]))
        for bid in [b for b in owner if b not in live]:
            owner.pop(bid, None)
            bounced.pop(bid, None)
        mem["live"] = live
    out = []
    for bid, (bx, by, bvx, bvy) in (mem.get("live") or {}).items():
        if (mem.get("owner") or {}).get(bid) != view.iid:
            continue
        p = bell_path(bx, by, bvx, bvy, view.t - view.T, bool((mem.get("bounced") or {}).get(bid)))
        if p is not None:
            out.append(p)
    return out


# ------------------------------------------------------------------------------------------------ offline truth

def attach(c: dict, tracks: list) -> None:
    """Each bell flight of the fight (a "Throwing Bell" run of frames outside Deactivate, gaps <= 2 frames) goes to
    the Bellbearer whose Throw entry (back-dated by its time in state) is within 3 frames of the bell's spawn and
    whose spawn point (+ (0.94 toward vx, -0.5)) is nearest (<= 1.5 u): tr["bells"] gets its arrays, and its hurting
    frames (a collider dealing damage) become the thrower's "HZ:bell" cols at the same game frames."""
    types = list(c["types"])
    if BELL not in types:
        return
    states, T = c["states"], c["T"]
    throws = []                                        # (t_release, t_antic, x, y, track index)
    for n, tr in enumerate(tracks):
        tr.setdefault("bells", [])
        st = tr["st"]
        t_ant = None
        for j in range(len(st)):
            if st[j] == "Throw Antic" and (j == 0 or st[j - 1] != "Throw Antic"):
                t_ant = float(tr["T"][j] - tr["tin"][j])
            if st[j] == "Throw" and (j == 0 or st[j - 1] != "Throw") and t_ant is not None:
                throws.append((float(tr["T"][j] - tr["tin"][j]), t_ant, float(tr["x"][j]), float(tr["y"][j]), n))
                t_ant = None
    hurt_box = {}
    for x in np.nonzero(c["c_dealt"] > 0)[0]:
        hurt_box.setdefault(int(c["c_ei"][x]), c["c_box"][x].astype(np.float64))
    pos = [{int(fi): j for j, fi in enumerate(tr["fi"])} for tr in tracks]
    sel = np.nonzero(c["e_tk"] == types.index(BELL))[0]
    for bid in np.unique(c["e_iid"][sel]):
        r = sel[c["e_iid"][sel] == bid]
        r = r[np.argsort(c["e_fi"][r], kind="stable")]
        st = [str(states[s]) if s >= 0 else None for s in c["e_st"][r]]
        fi = c["e_fi"][r]
        a = 0
        while a < len(r):
            if st[a] in (None, "Deactivate") or c["e_hidden"][r[a]]:
                a += 1
                continue
            b = a
            while b + 1 < len(r) and st[b + 1] not in (None, "Deactivate") and not c["e_hidden"][r[b + 1]] \
                    and fi[b + 1] - fi[b] <= 2:
                b += 1
            q = r[a:b + 1]
            t_sp = float(T[fi[a]] - c["e_tin"][q[0]])
            x0, y0, vx0 = float(c["e_x"][q[0]]), float(c["e_y"][q[0]]), float(c["e_vx"][q[0]])
            best = None
            for t_rel, t_ant, xr, yr, n in throws:
                if abs(t_rel - t_sp) > 3 * FT + 1e-6:
                    continue
                d = math.hypot(x0 - (xr + math.copysign(SPAWN[0], vx0)), y0 - (yr + SPAWN[1]))
                if d <= 1.5 and (best is None or d < best[0]):
                    best = (d, t_ant, n)
            if best is not None:
                _, t_ant, n = best
                tr = tracks[n]
                sts = st[a:b + 1]
                vy = c["e_vy"][q].astype(np.float64)
                bounced = np.cumsum([s_ == "Bounce" and v_ > 5.0 for s_, v_ in zip(sts, vy)]) > 0
                hurt = np.array([int(x) in hurt_box for x in q], bool)
                tr["bells"].append({"t_ant": t_ant, "T": np.asarray(T[fi[a:b + 1]], np.float64),
                                    "x": c["e_x"][q].astype(np.float64), "y": c["e_y"][q].astype(np.float64),
                                    "vx": c["e_vx"][q].astype(np.float64), "vy": vy, "st": sts, "hurt": hurt,
                                    "bounced": bounced})
                for x_, f_, h_ in zip(q, fi[a:b + 1], hurt):
                    j = pos[n].get(int(f_))
                    if h_ and j is not None:
                        tr["cols"][j].append(("HZ:bell", hurt_box[int(x_)]))
            a = b + 1


SPEC = EnemySpec(
    type_key="Pilgrim 03 Song", short="Bellbearer",
    fam_states={
        "CB_THROW": frozenset({"Throw Antic", "Throw", "Recover", "Rethrow?", "Throw Antic Quick"}),
        "CB_EVADE": frozenset({"Evade Antic", "Evade", "Evade End"}),
        "CB_ENTRY": frozenset({"Fly In", "Fly In Instant", "Battle Fly In", "Check Pos", "Shift", "Activate"}),
    },
    start={"Throw Antic": "CB_THROW", "Evade Antic": "CB_EVADE", "Evade": "CB_EVADE", "Fly In": "CB_ENTRY",
           "Fly In Instant": "CB_ENTRY", "Battle Fly In": "CB_ENTRY"},
    primary={"CB_THROW": "Throw Antic", "CB_EVADE": "Evade Antic", "CB_ENTRY": "Fly In"},
    branch={},
    branches={"CB_THROW": ("main",), "CB_EVADE": ("main",), "CB_ENTRY": ("main",)},
    aim=frozenset(),
    body=("Pilgrim 03 Song", "Pilgrim 03 Song (1)", "Pilgrim 03 Song (2)", "Pilgrim 03 Song (3)"),
    table="attack_range_bellbearer",
    custom=custom,
    attach=attach,
    left_out=(
        ("In Range / Out of Range / Insta Throw?", "the next attack (throw / evade) is picked at 0 s (group 2)"),
    ),
)

SESSIONS = ("20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
# the person's frames: 085824 frame 7939 (the Bellbearer's evade the zone boxes made into rings, the person)
CASES = (("20261009_085824", 7939, "Bellbearer evade, frame 7939 (the person)"),
         ("20261005_160435", 22420, "Throw Antic about 6 frames before the release: the decided bell arc at k 12"),
         ("20261005_160435", 22426, "Throw Antic about 3 frames before the release: the decided bell arc at k 12"))
