"""Clawmaiden (Song Handmaiden): attack-range type (Task "attack range: all types", stage B). Families and rules from
the v2 classification (docs/plans/forum_zones_v2.md sec. 1.6) and the first-FSM states the tracker sees (R0 dev).
Her spear is its own type (are_types/spear.py: the Spear entity, drawn on its decided path from the decision on).

  CM_SLASH      Slash Antic (0.5 s; the body drifts back up to 3 u) > Slash 1 > Slash 2 > Slash 3 > Slash 4 > Slash 5 >
                Slash Recover. The side is decided TWICE, each time at the first damage: FaceObject(hero) at the Slash 1
                entry (12 % turned against the antic's facing in R0 dev, every one toward the hero) and again at the
                Slash 4 entry (20 % flip). Four templates in the antic-start facing frame, by (Slash 1 kept "f" /
                turned "t") x (Slash 4 kept "k" / flipped "f"); slash_place draws the union of those still possible:
                all four before Slash 1, two until Slash 4, then the one (the observed facing at the entry frame equals
                the hero's side and the collider's side in every R0 dev case)
  CM_SPIN       Spin Antic > Spin 0-2 > Spin Wind Down > Spin End (> Spear Cast Antic > Spear Fire Recover; or Spin
                Cancel): the moving body only (silk suck, no attack collider of her own); the spear is the Spear type
  CM_TELE       Tele Out Antic (0.18 s, drops 1.3 u, the body still damages) > Tele Out > Tele In > Tele In End >
                (Did Roar? > Roar): the body is off from Tele Out; the arrival is random (pending: not drawn) until
                Tele In shows where she is (slash_place: before it only the Tele Out Antic / Tele Out shapes)
  CM_ENTRY      Tele In from nothing (the wave entry) > Tele In End > Did Roar? > Roar
  CM_FLYTOSLASH Fly To Slash: the body homing to 4 u from the hero (<= 5 u/s, <= 1 s); the slash it may start is a
                new family (group 2)
  CM_FLY        Fly (+ Set Distance, Tele?): her body. Not an attack, but a family so that at k > 0 the body is carried
                along her velocity like the moves above (the task: "fly / fly-to-slash body motion"); CARRY_ON False is
                the approved idle rule (the body where it is now for every k), kept for the comparison (forum.md 34)
"""
from ssbot.combat.are_spec import EnemySpec

SLASH_BRANCHES = ("f_k", "f_f", "t_k", "t_f")
PRE_ARRIVAL = frozenset({"Tele Out Antic", "Tele Out"})
# her flying body (Fly 6-9 u/s, Fly To Slash homing <= 5 u/s, the spin holding 8 u at 7-9 u/s): at k > 0 its shape is
# carried along her velocity NOW (no acceleration, no growth); the template's median displacement means nothing for a
# body that tracks the hero
CARRY = frozenset({"CM_FLY", "CM_FLYTOSLASH", "CM_SPIN"})
CARRY_ON = True                  # False: the carried families' body stays where it is now (the comparison variant)


def attach(c: dict, tracks: list) -> None:
    """tr["vy"] (the carried body's velocity; tracks_from_cache keeps vx only)."""
    import numpy as np
    tk = list(c["types"]).index("Song Handmaiden")
    rows_all = np.nonzero(c["e_tk"] == tk)[0]
    for tr in tracks:
        rows = rows_all[c["e_iid"][rows_all] == tr["iid"]]
        rows = rows[np.argsort(c["e_fi"][rows], kind="stable")]
        tr["vy"] = c["e_vy"][rows].astype(np.float64)


def on_step(inst, st, prev, T, x, y, s, hero_x, hero_y, tin, vx):
    """CM_SLASH: the facing at the Slash 1 entry against the antic's ("f" kept / "t" turned) and at the Slash 4 entry
    against Slash 1's ("k" / "f"), with their game times; the branch once both are known."""
    if inst.fam != "CM_SLASH" or st == prev:
        return
    ex = inst.extra
    if st == "Slash 1" and "side1" not in ex:
        ex["side1"] = (T, "f" if s == inst.s else "t", s)
    elif st == "Slash 4" and "side1" in ex and "side4" not in ex:
        ex["side4"] = (T, "k" if s == ex["side1"][2] else "f", s)
        if inst.branch is None:
            inst.branch, inst.branch_t = f"{ex['side1'][1]}_{ex['side4'][1]}", T


def slash_branches(inst, T: float) -> tuple:
    """The CM_SLASH branches still possible at game time T."""
    ex = inst.extra if inst is not None else {}
    s1 = ex.get("side1")
    s4 = ex.get("side4")
    a = (s1[1],) if s1 is not None and s1[0] <= T + 1e-9 else ("f", "t")
    c = (s4[1],) if s4 is not None and s4[0] <= T + 1e-9 else ("k", "f")
    return tuple(f"{p}_{q}" for p in a for q in c)


def _states_shape(tp, bb: int, keep):
    """(shape, iu0, iv0) of the union of the states in `keep` at bin bb of a state-gated template, or None."""
    import numpy as np
    parts = [v for k, v in (tp.sst[bb] if tp.sst else {}).items() if k in keep]
    if not parts:
        return None
    iu0 = min(p[1] for p in parts)
    iv0 = min(p[2] for p in parts)
    nu = max(p[1] + p[0].shape[1] for p in parts) - iu0
    nv = max(p[2] + p[0].shape[0] for p in parts) - iv0
    out = np.zeros((nv, nu), bool)
    for sh, u0, v0 in parts:
        out[v0 - iv0:v0 - iv0 + sh.shape[0], u0 - iu0:u0 - iu0 + sh.shape[1]] |= sh
    return out, iu0, iv0


def slash_place(tab, fam, branch, b, anchor, s, hero_du, now, b_now, dec, st_now, ctx):
    """CM_SLASH: the union over the branches still possible at the frame's time; CM_TELE before the arrival is seen:
    only the shapes of the states before it (the random arrival is a pending aim). Others: the template's."""
    from ssbot.combat.attack_range import FT, empty_mask, place_shape, union
    inst = ctx.get("inst")
    if fam == "CM_SLASH":
        brs = [br for br in slash_branches(inst, ctx["T"]) if (fam, br) in tab.templates]
        if not brs:
            return None
        return union([tab._place1(tab.templates[(fam, br)], b, anchor, s, hero_du, fam, now, b_now, None, st_now)
                      for br in brs])
    vel = ctx.get("vel")
    body = ctx.get("body")
    if fam in CARRY and b_now is not None and b >= b_now and body:
        # the body colliders now (exact at k 0), carried along the velocity now at k > 0, kept inside the arena (the
        # idle bodies' rule: attack_range.carry_body)
        from ssbot.combat.attack_range import carry_body
        return carry_body(body, vel, (b - b_now) * FT, tab.cell, on=CARRY_ON)
    if fam in CARRY and now is not None and b_now is not None and b > b_now and vel is not None:
        tp = tab.templates.get((fam, "main"))
        if tp is None:
            return None
        sh, iu0, iv0 = tab._shape(tp, min(max(b, 0), tp.nb - 1), False, st_now)
        if sh is None or not sh.size:
            return empty_mask()
        dt = (b - b_now) * FT if CARRY_ON else 0.0
        lo, hi = tab.walls
        return place_shape(sh, iu0, iv0, min(max(now[0] + vel[0] * dt, lo), hi), now[1] + vel[1] * dt, s, tab.cell)
    if fam == "CM_TELE" and b_now is not None and b > b_now and st_now in PRE_ARRIVAL:
        tp = tab.templates.get((fam, "main"))
        if tp is None:
            return None
        o = (tp.order or {}).get(st_now, 0)
        keep = {k for k in PRE_ARRIVAL if (tp.order or {}).get(k, -1) >= o}
        bb = min(max(b, 0), tp.nb - 1)
        shp = _states_shape(tp, bb, keep)
        if shp is None:
            return empty_mask()
        px, py = tab.position(tp, b, anchor, s, hero_du, fam)
        if now is not None:
            qx, qy = tab.position(tp, b_now, anchor, s, hero_du, fam)
            px, py = now[0] + px - qx, now[1] + py - qy
        return place_shape(shp[0], shp[1], shp[2], px, py, s, tab.cell)
    return None


SPEC = EnemySpec(
    type_key="Song Handmaiden", short="Clawmaiden",
    fam_states={
        "CM_SLASH": frozenset({"Slash Antic", "Slash 1", "Slash 2", "Slash 3", "Slash 4", "Slash 5", "Slash Recover"}),
        "CM_SPIN": frozenset({"Spin Antic", "Spin 0", "Spin 1", "Spin 2", "Spin Wind Down", "Spin End", "Spin Cancel",
                              "Silk Break", "Spear Cast Antic", "Spear Fire", "Spear Fire Recover"}),
        "CM_TELE": frozenset({"Tele Out Antic", "Tele Out", "Select Target", "Tele Pos", "Tele In", "Tele In End",
                              "Did Roar?", "Roar"}),
        "CM_ENTRY": frozenset({"Tele In", "Tele In End", "Did Roar?", "Roar"}),
        "CM_FLYTOSLASH": frozenset({"Fly To Slash"}),
        "CM_FLY": frozenset({"Fly", "Set Distance", "Tele?"}),
    },
    start={"Slash Antic": "CM_SLASH", "Spin Antic": "CM_SPIN", "Spear Cast Antic": "CM_SPIN",
           "Tele Out Antic": "CM_TELE", "Tele In": "CM_ENTRY", "Fly To Slash": "CM_FLYTOSLASH", "Fly": "CM_FLY"},
    primary={"CM_SLASH": "Slash Antic", "CM_SPIN": "Spin Antic", "CM_TELE": "Tele Out Antic", "CM_ENTRY": "Tele In",
             "CM_FLYTOSLASH": "Fly To Slash", "CM_FLY": "Fly"},
    branch={},
    branches={"CM_SLASH": SLASH_BRANCHES, "CM_SPIN": ("main",), "CM_TELE": ("main",), "CM_ENTRY": ("main",),
              "CM_FLYTOSLASH": ("main",), "CM_FLY": ("main",)},
    aim=frozenset(),
    body="Song Handmaiden",
    table="attack_range_clawmaiden",
    face_names=("Slash Collider",),
    state_gate=True,
    on_step=on_step,
    place_fn=slash_place,
    left_out=(
        ("Fly / Set Distance / Tele?", "the next move is picked there (group 2): only her flying body is drawn"),
        ("Fly To Slash -> Slash Antic", "the slash it may start (64 %) is a new family (group 2)"),
        ("Tele Out .. Tele In", "the arrival point is random until Tele In shows it: the body after the teleport is "
         "not drawn before then"),
        ("Spear Cast Antic", "the spear's aim is pending until Get Antic Angle (the Spear Fire frame); from then the "
         "Spear type draws it"),
    ),
)

SESSIONS = ("20261004_002749", "20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
CASES = (("20261009_085824", 7939, "frame 7939 (the person: Bellbearer / Reed)"),
         ("20261009_085824", 10427, "frame 10427 (the person: Reed counter)"))
