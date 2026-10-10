"""Reed (Song Reed): attack-range type (Task "attack range: all types", stage B). Families from the v2 classification
(docs/plans/forum_zones_v2.md sec. 1.1, C:/ssbot/data/m2_forum_v2/workflow_result.json), the pin from
C:/ssbot/data/m2_forum_aimics (exact FSM rule) and the counter from C:/ssbot/data/m2_forum_cases (Reed counter) and
the Control FSM decode (Parry Y Aim: Speed Y = clamp(2 (hero y - y), +-10)):

  RE_STAB     Stab Antic (0.63-0.67 s; the body TRACKS the hero: DistanceFly to (hero -+ 5, +2.5)) > Stab 1-5 > Stab
              End > Stab Recover: three lunges, -20 u/s along the facing and -6 down. Decided at the Stab 1 entry
              (the start point, pending in the antic, group 2): anchored there in its observed facing; before it only
              the antic body is drawn
  RE_THROW    Throw Antic (Anim) > Throw Aim (the decision, 0.25-0.28 s) > Throw (Transition) > Throw Recover: the
              body only; the pin (below) is decided at the Throw Aim entry
  RE_COUNTER  Block (the hit happened: HIT_COND) > Parry Y Aim > Parry Slash > Multihit / Multihit Clashed / Parry
              Slash End: drawn from the Block entry in its facing (= the hero's side at the hit, 1300/1300); the
              vertical aim (Speed Y) is decided at the Parry Slash entry (Block + 30-31 frames): until then the union
              of the branches (one per 2 u/s of Speed Y), then its branch
  RE_EVADE    Evade Antic > Evade (> Evade End): 30 u/s away + 5 up, the body; it re-faces the hero at the Evade entry:
              branch "same" / "turned" against the antic start's facing (the union during the antic)
  RE_ENTRY    Fly In: the body falling in
  idle        Alert, Stab Pos (DistanceFly positioning), Defend Start / Defend / Defend End (the stance: no collider
              of its own without a hit), Throw Range, the 0 s choice states: the exact body now

The pin ("Song Reed Pin Projectile", pooled; the owner's extra): decided at the Throw Aim entry: elevation = the
Reed transform -> hero transform angle clamped to [-70, +45] deg on the facing side (error 0 on R0 dev); released
24-25 game frames later (28-30 with Throw Transition), at the Reed's position at the release + (1.53, -0.54) in its
facing frame, or (1.11, +0.48) when the elevation is >= 10 deg; then straight at 31.0 u/s in 50 Hz steps (0.62 u),
its damage collider a 2.031 x 0.098 box, axis-aligned on its spawn frame and turned to its flight from the next,
until it sticks (collider off). Before the release: its decided line at the release windows; in flight: its real
path from the observed position and velocity (the step count's floor / ceil); both stop at the arena's walls / floor
(the R0 dev extremes of the lit pin centres).
"""
import math

import numpy as np

from ssbot.combat.are_spec import Decision, EnemySpec

PIN_TYPE = "Song Reed Pin Projectile"
OBJ_TYPES = (PIN_TYPE,)
OBJ_NAME = "pin"
PIN_SPEED = 31.0
PIN_STEP = 0.02                     # s: its 50 Hz physics step (0.62 u)
AIM_CLAMP = (-70.0, 45.0)
UP_MIN = 10.0                       # deg: Throw Up (spawn SPAWN_UP) from this elevation on
SPAWN_DOWN = (1.53, -0.54)          # facing frame (u forward, v up) from the Reed at the release
SPAWN_UP = (1.11, 0.48)
REL = ((24, 25), (28, 30))          # game frames from the Throw Aim entry to the release (R0 dev 1995 / 158)
DRIFT_DECEL = 0.85                  # per frame in Throw Aim: the recoil left after the decision
# the pins' lit centres on R0 dev (attach: per episode); the line stops beyond them (walls / floor)
PIN_X = (13.9, 48.25)
PIN_Y_MIN = 3.15


def pin_rule(x: float, y: float, vx, hero_x, hero_y):
    """The pin's aim at the Throw Aim entry: (0 = the observed facing, L 0: the body stays, {aim, vx})."""
    if hero_x is None or hero_y is None:
        return 0, 0.0, {}
    el = math.degrees(math.atan2(float(hero_y) - y, abs(float(hero_x) - x)))
    el = min(max(el, AIM_CLAMP[0]), AIM_CLAMP[1])
    v = float(vx) if vx is not None and math.isfinite(vx) else 0.0
    return 0, 0.0, {"aim": el, "vx0": v}


AIM_UP_DY = 2.0                     # CheckTargetDirection at Throw Antic Anim: Aiming Up when hero y > y + 2
AIM_UP_BAND = 0.3                   # within this of the line the flag is left open (the frame's update order)


def throw_branch(y=0.0, hero_y=None, **_):
    """The throw's Aiming Up flag at its antic start: "up" / "down" ("open" near the line: both). With the pin's
    Up / Down spawn (its decided elevation >= UP_MIN) it fixes the release: Throw Transition (+4-5 frames) when they
    differ."""
    if hero_y is None:
        return None
    d = float(hero_y) - y - AIM_UP_DY
    return "open" if abs(d) < AIM_UP_BAND else ("up" if d > 0 else "down")


def stab_rule(x: float, y: float, vx, hero_x, hero_y):
    """The stab at its Stab 1 entry: the observed facing, the lunges' median u extent (R0 dev)."""
    return 0, STAB_L


STAB_L = 10.0                       # u: the median of the R0 dev stabs' u displacement from Stab 1 to their end

SPEED_Y_EDGES = (-9.0, -7.0, -5.0, -3.0, -1.0, 1.0, 3.0, 5.0, 7.0)
SPEED_Y_NAMES = ("v-10", "v-8", "v-6", "v-4", "v-2", "v0", "v2", "v4", "v6", "v8")


# u: 180 of the 1,716 R0 dev evades turned, all with the hero within 2.22 u in front at the antic start (beyond it
# the direction is certain from the start; the CH_HOP branch rule's idea)
TURN_DU_MAX = 2.22


def evade_start(x=0.0, s=1, hero_x=None, **_):
    """At the antic start: "same" when the hero is too far in front to cross before the Evade entry, else pending."""
    if hero_x is None:
        return None
    return "same" if (float(hero_x) - x) * s > TURN_DU_MAX else None


def evade_branch(s=1, s0=1, **_):
    """The evade's direction at the Evade entry (it re-faces the hero there and flies away from it): "same" as the
    facing at the antic start, or "turned" (the hero crossed during the antic)."""
    return "same" if s == s0 else "turned"


def counter_branch(x=0.0, y=0.0, s=1, vx=None, hero_x=None, hero_y=None, **_):
    """The counter's vertical aim at Parry Y Aim (the Parry Slash entry): Speed Y = clamp(2 (hero y - y), +-10),
    binned by 2 u/s."""
    if hero_y is None:
        return None
    sy = min(max(2.0 * (float(hero_y) - y), -10.0), 10.0)
    return SPEED_Y_NAMES[int(np.searchsorted(SPEED_Y_EDGES, sy, side="right"))]


STAB = frozenset({"Stab Antic", "Stab 1", "Stab 2", "Stab 3", "Stab 4", "Stab 5", "Stab End", "Stab Recover"})
THROW = frozenset({"Throw Antic Anim", "Throw Antic", "Throw Aim", "Throw Lock", "Lock L", "Lock R High",
                   "Lock R Low", "Throwing Up?", "Throw Up", "Throw Down", "Throw Transition", "Throw",
                   "Throw Recover"})
COUNTER = frozenset({"Block", "Parry Y Aim", "Parry Slash", "Multihit", "Multihit Clashed", "Multihit End",
                     "Parry Slash End"})

SPEC = EnemySpec(
    type_key="Song Reed", short="Reed",
    fam_states={
        "RE_STAB": STAB,
        "RE_THROW": THROW,
        "RE_COUNTER": COUNTER,
        "RE_EVADE": frozenset({"Evade Antic", "Evade", "Evade End"}),
        "RE_ENTRY": frozenset({"Fly In", "Battle Fly In"}),
    },
    start={"Stab Antic": "RE_STAB", "Throw Antic Anim": "RE_THROW", "Throw Antic": "RE_THROW",
           "Block": "RE_COUNTER", "Evade Antic": "RE_EVADE", "Evade": "RE_EVADE", "Fly In": "RE_ENTRY",
           "Battle Fly In": "RE_ENTRY"},
    primary={"RE_STAB": "Stab Antic", "RE_THROW": "Throw Antic", "RE_COUNTER": "Block", "RE_EVADE": "Evade Antic",
             "RE_ENTRY": "Fly In"},
    branch={"RE_COUNTER": {"Parry Y Aim": counter_branch, "Parry Slash": counter_branch},
            "RE_EVADE": {"Evade Antic": evade_start, "Evade": evade_branch},
            "RE_THROW": {"Throw Antic Anim": throw_branch, "Throw Antic": throw_branch}},
    branches={"RE_STAB": ("main",), "RE_THROW": ("up", "down", "open"), "RE_COUNTER": SPEED_Y_NAMES,
              "RE_EVADE": ("same", "turned"), "RE_ENTRY": ("main",)},
    decide={"RE_STAB": Decision(states=frozenset({"Stab 1"}), rule=stab_rule),
            "RE_THROW": Decision(states=frozenset({"Throw Aim"}), rule=pin_rule)},
    hit_started=frozenset({"RE_COUNTER"}),
    state_gate=True,
    aim=frozenset(),
    body=("Song Reed", "Song Reed (1)", "Song Reed (2)", "Song Reed (3)", "Song Reed (4)"),
    table="attack_range_reed",
    face_names=("Stab Hit",),
    left_out=(
        ("Stab Antic", "the stab's start point tracks the hero (DistanceFly) until Stab 1: a pending aim (group 2); "
         "only the antic body is drawn until the Stab 1 entry"),
        ("Throw Antic", "the pin's aim is pending until the Throw Aim entry (0.25-0.28 s): only the body"),
        ("Alert / Stab Pos / Defend / Throw Range", "the next attack is picked later (group 2); Defend has no "
         "collider of its own: its counter is drawn only once the hit happened (Block)"),
    ),
)

SESSIONS = ("20261004_002749", "20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
CASES = (("20261009_085824", 7939, "Bellbearer / Reed, frame 7939 (the person)"),
         ("20261009_085824", 10427, "Reed counter, frame 10427 (the person)"))


# ------------------------------------------------------------------------------------------------ the pin

PIN_LEN, PIN_WID = 2.031, 0.098     # its damage collider (the exported AABB on its spawn frame)
PIECES = 40                         # a rotated pin as axis-aligned pieces (within 0.02 u of the rectangle)


def pin_boxes(cx: float, cy: float, ux: float = 0.0, uy: float = 0.0) -> list:
    """The pin's collider centred at (cx, cy): rotated along the unit direction (ux, uy) as PIECES axis-aligned
    boxes (the caches keep AABBs: attach writes the real ones the same way, so the estimate and the truth are
    rasterized alike), or (0, 0) the axis-aligned box of its spawn frame (it turns to its flight from the next)."""
    def box(x, y, hx, hy):
        return np.array([[x - hx, y - hy], [x + hx, y - hy], [x + hx, y + hy], [x - hx, y + hy]])
    if ux == 0.0 and uy == 0.0:
        return [box(cx, cy, 0.5 * PIN_LEN, 0.5 * PIN_WID)]
    seg = PIN_LEN / PIECES
    hx = 0.5 * seg * abs(ux) + 0.5 * PIN_WID * abs(uy)
    hy = 0.5 * seg * abs(uy) + 0.5 * PIN_WID * abs(ux)
    return [box(cx + ux * (i + 0.5 - 0.5 * PIECES) * seg, cy + uy * (i + 0.5 - 0.5 * PIECES) * seg, hx, hy)
            for i in range(PIECES)]


def _inside(cx: float, cy: float) -> bool:
    return PIN_X[0] <= cx <= PIN_X[1] and cy >= PIN_Y_MIN


def _steps(n_lo: int, n_hi: int, x0: float, y0: float, vx: float, vy: float, rot0: bool = True) -> list:
    """The pin's collider at step counts n_lo..n_hi from its centre (x0, y0) at velocity (vx, vy) (rot0: already
    turned at step 0), up to where it leaves the arena (it sticks there)."""
    sp = math.hypot(vx, vy)
    ux, uy = (vx / sp, vy / sp) if sp > 1e-6 else (0.0, 0.0)
    out = []
    for n in range(max(n_lo, 0), max(n_hi, 0) + 1):
        cx, cy = x0 + n * vx * PIN_STEP, y0 + n * vy * PIN_STEP
        if n > 0 and not _inside(cx, cy):     # where it is now (step 0) is not checked: it is there
            break
        out += pin_boxes(cx, cy, *((ux, uy) if (n > 0 or rot0) else (0.0, 0.0)))
    return out


def pin_path(x: float, y: float, vx: float, vy: float, dt: float, rot: bool = True) -> list:
    """A pin in flight whose collider centre is (x, y) with velocity (vx, vy) (rot: turned already, not its spawn
    frame), dt game seconds later: its collider at the step counts possible (50 Hz steps against 60 Hz frames:
    floor / ceil of dt x 50, snapped within 0.02 of a whole step: the game time's dt jitter)."""
    if dt <= 1e-6:
        return _steps(0, 0, x, y, vx, vy, rot)
    q = dt / PIN_STEP
    return _steps(int(math.floor(q + 0.02)), int(math.ceil(q - 0.02)), x, y, vx, vy, rot)


def pin_decided(dec: dict, T: float, pos: tuple, t: float, ft: float = 1.0 / 60.0,
                aim_up: str | None = None) -> list:
    """The decided pin before its release (dec: the Throw Aim decision with its aim): at game time t, for each
    release window, its collider at the step counts possible (on the release frame the axis-aligned spawn box).
    aim_up: the throw's Aiming Up branch (throw_branch): the window with / without Throw Transition; else both."""
    el = math.radians(float(dec["aim"]))
    s = int(dec["s"])
    fu, fv = SPAWN_UP if dec["aim"] >= UP_MIN else SPAWN_DOWN
    m = max((T - float(dec["t"])) / ft, 0.0)
    drift = float(dec.get("vx0", 0.0)) * DRIFT_DECEL ** m * ft / (1.0 - DRIFT_DECEL)
    x0 = pos[0] + drift + s * fu
    y0 = pos[1] + fv
    vx, vy = s * math.cos(el) * PIN_SPEED, math.sin(el) * PIN_SPEED
    out = []
    wins = REL
    if aim_up in ("up", "down"):
        wins = (REL[1] if (aim_up == "up") != (dec["aim"] >= UP_MIN) else REL[0],)
    for r0, r1 in wins:
        t_lo, t_hi = float(dec["t"]) + r0 * ft, float(dec["t"]) + r1 * ft
        if t < t_lo - 1e-6:
            continue
        n_lo = int(math.floor(max(t - t_hi, 0.0) / PIN_STEP + 0.02))
        n_hi = int(math.ceil((t - t_lo) / PIN_STEP - 0.02)) if t > t_lo + 1e-6 else 0
        out += _steps(n_lo, n_hi, x0, y0, vx, vy, rot0=False)
    return out


def extra(tab, inst, T: float, pos: tuple, t: float, objs) -> object:
    """The Reed's pins at game time t (attack_range.type_extra): those in flight on their real paths, and the decided
    one of a throw not yet released (from the Throw Aim entry until the last release window)."""
    from ssbot.combat.attack_range import poly_mask
    polys = []
    for o in objs or ():
        polys += pin_path(o.get("cx", o["x"]), o.get("cy", o["y"]), o["vx"], o["vy"], t - o["t"],
                          o.get("rot", o["t"] > o.get("t0", -1e9) + 1e-6))
    dec = inst.dec if inst is not None and inst.fam == "RE_THROW" else None
    if dec is not None and "aim" in dec and T <= float(dec["t"]) + (REL[-1][1] + 1) / 60.0 and \
            not any(o.get("t0", -1e9) >= float(dec["t"]) - 1e-6 for o in objs or ()):
        polys += pin_decided(dec, T, pos, t, aim_up=inst.branch)
    return poly_mask(polys, getattr(tab, "cell", 0.05))


def real_pin(box, vx: float, vy: float) -> tuple:
    """(centre x, centre y, rotated, pieces) of a pin's exported AABB: the rotated rectangle when the AABB fits it
    (from its second frame), the axis-aligned box on its spawn frame, else the AABB itself (rotated None)."""
    x0, y0, x1, y1 = (float(v) for v in box)
    cx, cy, w, h = 0.5 * (x0 + x1), 0.5 * (y0 + y1), x1 - x0, y1 - y0
    sp = math.hypot(vx, vy)
    if sp > 1e-6:
        ux, uy = vx / sp, vy / sp
        if abs(w - (PIN_LEN * abs(ux) + PIN_WID * abs(uy))) < 0.02 and \
                abs(h - (PIN_LEN * abs(uy) + PIN_WID * abs(ux))) < 0.02:
            return cx, cy, True, pin_boxes(cx, cy, ux, uy)
    if abs(w - PIN_LEN) < 0.02 and abs(h - PIN_WID) < 0.02:
        return cx, cy, False, pin_boxes(cx, cy)
    return cx, cy, None, [np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])]


def attach(c: dict, tracks: list, spec) -> dict:
    """The pins of one fight cache given to the Reed tracks that threw them (builder hook): per pin episode (the
    pooled entity's runs of lit frames, gaps <= 2), the owner is the track that entered Throw at its first frame
    (+-2) with the spawn point (position + offset) within 0.3 u of it, else the nearest Reed within 3 u. Adds per
    frame tr["objs"][j] ({x, y, vx, vy, t, t0} of its pins in flight) and the collider as ("OBJ:pin", AABB) to
    tr["cols"][j] (real_pin: the rotated rectangle as pieces); returns the counts."""
    st = {"episodes": 0, "attributed": 0, "by_throw": 0, "unfit": 0}
    for tr in tracks:
        tr.setdefault("objs", [[] for _ in range(len(tr["T"]))])
    types = list(c["types"])
    if PIN_TYPE not in types or not tracks:
        return st
    tk = types.index(PIN_TYPE)
    sel = np.nonzero(c["e_tk"] == tk)[0]
    if not len(sel):
        return st
    cei = c["c_ei"]
    order = np.argsort(cei, kind="stable")
    ceis = cei[order]
    lit_box = {}
    lo = np.searchsorted(ceis, sel, "left")
    hi = np.searchsorted(ceis, sel, "right")
    for r, a, b in zip(sel, lo, hi):
        for q in order[a:b]:
            if c["c_dealt"][q] > 0:
                lit_box[int(r)] = c["c_box"][q].astype(np.float64)
                break
    T = c["T"]
    pos = [{int(fi): j for j, fi in enumerate(tr["fi"])} for tr in tracks]
    throws = []                                  # (cache frame, track n, j) of each Throw entry
    for n, tr in enumerate(tracks):
        for j in range(1, len(tr["T"])):
            if tr["st"][j] == "Throw" and tr["st"][j - 1] != "Throw":
                throws.append((int(tr["fi"][j]), n, j))
    e_iid, e_fi = c["e_iid"], c["e_fi"]
    for iid in np.unique(e_iid[sel]):
        rows = sel[e_iid[sel] == iid]
        rows = rows[np.argsort(e_fi[rows], kind="stable")]
        rows = np.array([r for r in rows if int(r) in lit_box], np.int64)
        if not len(rows):
            continue
        ff = e_fi[rows]
        cuts = np.nonzero(np.diff(ff) > 2)[0] + 1
        for part in np.split(np.arange(len(rows)), cuts):
            rr = rows[part]
            st["episodes"] += 1
            r0 = int(rr[0])
            fi0 = int(e_fi[r0])
            px, py = float(c["e_x"][r0]), float(c["e_y"][r0])
            best = None
            for fi, n, j in throws:
                if abs(fi - fi0) > 2:
                    continue
                tr = tracks[n]
                for s, (fu, fv) in ((1, SPAWN_DOWN), (1, SPAWN_UP), (-1, SPAWN_DOWN), (-1, SPAWN_UP)):
                    d = math.hypot(px - (tr["x"][j] + s * fu), py - (tr["y"][j] + fv))
                    if d <= 0.3 and (best is None or d < best[0]):
                        best = (d, n, True)
            if best is None:
                for n, tr in enumerate(tracks):
                    j = pos[n].get(fi0)
                    if j is None or tr["hidden"][j]:
                        continue
                    d = math.hypot(px - tr["x"][j], py - tr["y"][j])
                    if d <= 3.0 and (best is None or d < best[0]):
                        best = (d, n, False)
            if best is None:
                continue
            _, n, by_throw = best
            st["attributed"] += 1
            st["by_throw"] += int(by_throw)
            tr = tracks[n]
            t0 = float(T[fi0])
            for r in rr:
                j = pos[n].get(int(e_fi[r]))
                if j is None:
                    continue
                vx, vy = float(c["e_vx"][r]), float(c["e_vy"][r])
                cx, cy, rot, pieces = real_pin(lit_box[int(r)], vx, vy)
                st["unfit"] += int(rot is None)
                tr["objs"][j].append({"x": float(c["e_x"][r]), "y": float(c["e_y"][r]), "cx": cx, "cy": cy,
                                      "vx": vx, "vy": vy, "t": float(T[e_fi[r]]), "t0": t0, "rot": bool(rot)})
                for p in pieces:
                    tr["cols"][j].append(("OBJ:pin", np.array([p[:, 0].min(), p[:, 1].min(), p[:, 0].max(),
                                                               p[:, 1].max()])))
    return st

