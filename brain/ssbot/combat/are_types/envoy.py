"""Envoy (Song Pilgrim 01): attack-range type (Task "attack range: all types", stage B). Families and rules from the
v2 classification (docs/plans/forum_zones_v2.md sec. 1.4, C:/ssbot/data/m2_forum_v2/workflow_result.json) and the
first-FSM states the tracker sees (R0 dev):

  EN_SLASH      Slash Antic > Slash1 (0.48 s) > Slash1 2 > Slash1 Recover > Attack End (single) | JumpSlash Antic >
                JumpSlash 1-4 (jump): the facing is fixed at the antic start; its FIRST damage (P1 Damager, 0.483 s) is a
                backswing BEHIND and above the body, the front P2 Damager from 0.683 s. Combo? (0 s, unseen) picks the
                jump slash at random (50 %): the branch is known at the first state after Slash1 Recover, the union of
                the two until then
  EN_JUMPSLASH  JumpSlash Antic > JumpSlash 1-4 started from outside a slash (from a charge): the same template
  EN_CHARGE     Charge Antic (0.483-0.517 s, still) > Charge (13.0 u/s toward the hero's side at the antic start) >
                Charge End (a 0.26-1.3 u skid, 0.42 s): the direction and the timing are fixed at the start, the length
                is not (C14): the FSM stops it once it is 4 u past the hero (R0 dev: never more than 3.997 u past at
                its last Charge frame) or at a wall (x 17.37 / 45.57, the body). Drawn by charge_place: the Charge shape
                moving at 13 u/s from where it is now to 4 u past the hero's CURRENT position (or the wall), then the
                Charge End skid (its R0 dev median by frame) and the body
  EN_AMBUSH     Ambush Antic > Ambush 1 > Ambush 2: the wave-0 entry in place (the body damages from 1.25 s)
  idle          Walker (2.4 u/s toward the hero), Attack Wait and the 0 s decision states: the exact body now
"""
import math

from ssbot.combat.are_spec import EnemySpec

CHARGE_V = 13.0                 # u/s, every Charge frame of R0 dev
CHARGE_PAST = 4.0               # the FSM ends the charge 4 u past the hero
CHARGE_ANTIC_F = 30             # Charge Antic 0.483-0.517 s (p50 0.516): the charge starts at bin 30-31
CHARGE_WALLS = (17.37, 45.57)   # the body's x where R0 dev charges stopped at a wall (end x p0 / max)
# Charge End: the median skid (u along the charge) by frames since its entry (R0 dev, 117 charges), then the body
SKID = (0.26, 0.26, 0.348, 0.448, 0.448, 0.448, 0.565, 0.565, 0.565, 0.565, 0.565, 0.565, 0.565, 0.565, 0.565, 0.565,
        0.565, 0.565, 0.565, 0.565, 0.608, 0.839, 0.893, 1.238, 1.303)
CHARGING = frozenset({"Charge Antic", "Charge", "Reset"})

_STATE_SHAPES: dict = {}


def state_shape(tab, fam: str, br: str, st: str):
    """(shape, iu0, iv0): the union of a state's shapes over every bin of a state-gated template (the Charge's damager
    sits at the same place on the body in every frame of it), cached per table."""
    import numpy as np
    key = (id(tab), fam, br, st)
    if key not in _STATE_SHAPES:
        tp = tab.templates.get((fam, br))
        parts = [d[st] for d in (tp.sst or ()) if st in d] if tp is not None else []
        if not parts:
            _STATE_SHAPES[key] = None
        else:
            iu0 = min(p[1] for p in parts)
            iv0 = min(p[2] for p in parts)
            nu = max(p[1] + p[0].shape[1] for p in parts) - iu0
            nv = max(p[2] + p[0].shape[0] for p in parts) - iv0
            out = np.zeros((nv, nu), bool)
            for sh, u0, v0 in parts:
                out[v0 - iv0:v0 - iv0 + sh.shape[0], u0 - iu0:u0 - iu0 + sh.shape[1]] |= sh
            _STATE_SHAPES[key] = (out, iu0, iv0)
    return _STATE_SHAPES[key]


def charge_place(tab, fam, branch, b, anchor, s, hero_du, now, b_now, dec, st_now, ctx):
    """EN_CHARGE at bin b > b_now (k = 0 and the other families: the template's placement): from the observed
    position, still in the antic until bin CHARGE_ANTIC_F, then 13 u/s along the antic-start facing s until 4 u past
    the hero's current x or the wall, then the Charge End skid and the body there."""
    from ssbot.combat.attack_range import FT, empty_mask, place_shape
    if fam != "EN_CHARGE" or now is None or b_now is None or b <= b_now or st_now not in CHARGING:
        return None
    inst = ctx.get("inst")
    hero = ctx.get("hero")
    x, y = float(now[0]), float(now[1])
    if st_now == "Charge Antic":
        b_c = CHARGE_ANTIC_F
    else:
        b_c = b_now
        tc = (inst.extra.get("charge_t") if inst is not None else None)
        if tc is not None and tc <= ctx["T"] + 1e-9:
            b_c = min(b_now, int(math.floor((tc - inst.t0) / FT + 0.5)))
    wall = CHARGE_WALLS[1] if s > 0 else CHARGE_WALLS[0]
    room = max((wall - x) * s, 0.0)
    if hero is not None:
        room = min(room, max((float(hero[0]) + CHARGE_PAST * s - x) * s, 0.0))
    if b < b_c:
        st, u = "Charge Antic", 0.0
    else:
        go = CHARGE_V * (b - max(b_now, b_c)) * FT
        if go < room or (st_now == "Charge Antic" and b == b_c):
            st, u = "Charge", min(go, room)
        else:
            b_end = max(b_now, b_c) + int(math.ceil(room / (CHARGE_V * FT) - 1e-9))
            d = b - b_end
            if d < len(SKID):
                st, u = "Charge End", room + SKID[max(d, 0)]
            else:
                st, u = "<end>", room + SKID[-1]
    shp = state_shape(tab, fam, "main", st) or state_shape(tab, fam, "main", "Charge End")
    if shp is None:
        return empty_mask()
    lo, hi = CHARGE_WALLS
    px = min(max(x + s * u, lo), hi)
    return place_shape(shp[0], shp[1], shp[2], px, y, s, tab.cell)


def on_step(inst, st, prev, T, x, y, s, hero_x, hero_y, tin, vx):
    """EN_CHARGE: the game time the charge itself started (the Charge entry, back-dated by its time in state)."""
    if inst.fam == "EN_CHARGE" and st == "Charge" and "charge_t" not in inst.extra:
        inst.extra["charge_t"] = T - max(float(tin or 0.0), 0.0)


SLASH = frozenset({"Slash Antic", "Slash1", "Slash1 2", "Slash1 Recover", "Combo?", "Attack End"})
JUMPSLASH = frozenset({"JumpSlash Antic", "Forward", "JumpSlash 1", "JumpSlash 2", "JumpSlash 3", "JumpSlash 4"})

SPEC = EnemySpec(
    type_key="Song Pilgrim 01", short="Envoy",
    fam_states={
        "EN_SLASH": SLASH | JUMPSLASH,
        "EN_JUMPSLASH": JUMPSLASH,
        "EN_CHARGE": frozenset({"Charge Antic", "Charge", "Reset", "Wall Bonk", "Deflect", "Bump Up", "Charge End"}),
        "EN_AMBUSH": frozenset({"Ambush Antic", "Ambush 1", "Ambush 2"}),
    },
    start={"Slash Antic": "EN_SLASH", "JumpSlash Antic": "EN_JUMPSLASH", "Charge Antic": "EN_CHARGE",
           "Ambush Antic": "EN_AMBUSH"},
    primary={"EN_SLASH": "Slash Antic", "EN_JUMPSLASH": "JumpSlash Antic", "EN_CHARGE": "Charge Antic",
             "EN_AMBUSH": "Ambush Antic"},
    branch={"EN_SLASH": {"Attack End": "single", "JumpSlash Antic": "jump", "JumpSlash 1": "jump"}},
    branches={"EN_SLASH": ("single", "jump"), "EN_JUMPSLASH": ("main",), "EN_CHARGE": ("main",),
              "EN_AMBUSH": ("main",)},
    aim=frozenset(),
    body="Song Pilgrim 01",
    table="attack_range_envoy",
    face_names=("P2 Damager", "Charge Damager", "JumpSlash Damager 2"),
    state_gate=True,
    on_step=on_step,
    place_fn=charge_place,
    left_out=(
        ("Walker / Attack Wait / Hop Up? / Leader?", "the next attack is picked there (group 2): the body now; a hit "
         "on a walking Envoy starts a charge (HIT_COND start trigger, not a counter: drawn from its Charge Antic)"),
        ("EN_HOPSLASH", "never seen (0 in 490 fights)"),
    ),
)

SESSIONS = ("20261004_002749", "20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
CASES = (("20261009_085824", 7939, "frame 7939 (the person: Bellbearer / Reed)"),
         ("20261009_085824", 10427, "frame 10427 (the person: Reed counter)"))
