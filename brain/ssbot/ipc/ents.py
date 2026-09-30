"""Readers for the oracle's STATE "ents" section and "fsm" events (oracle/src/Entities, DESIGN §3.1.2).

    for e in state["ents"] or []:
        for c in e["colliders"]:
            pts = collider_points(c)           # [(x, y), ...] world units
            if c["damage"] and c["enabled"] and c["damage"]["eff"] > 0: ...

Entity map: iid (unique within one STATE), type_key, category, src, layer, pos [x,y,z], vel [x,y]|None,
gravity_scale|None, hp|None, is_dead|None, inv|None (all three present exactly when src has the health_manager bit),
fsms [{name, state, t, rt}], anim {clip, frame, n}|None, flipX, render_aabb|None, colliders.
fsms[].t: FsmState.StateTime (scaled; PlayMaker stops it once all of the state's actions have finished);
fsms[].rt: FsmState.StateRealTime (unscaled seconds since entry; never stops, but runs through pauses and hit-stop).
Collider: kind, verts_world (flat x0, y0, x1, y1, ...), enabled, layer, r (circles), damage|None.
Damage: dealt, eff, hazard_type, flags, parry, parryable, can_cause_damage. parryable = parry bit clash or force
(the source itself reacts to the nail: canClashTink, or an enabled forceParry); the counter bit (hazard ENEMY, what
the Cross Stitch stance catches) is not part of it.
"fsm" event payload (state["ev"][i]["d"] where k == "fsm"): iid (GameObject holding the FSM), ent (its entity root),
obj (GameObject name), fsm, from (None on a start/restart), to, t_in_prev (StateTime of `from`), rt_in_prev
(StateRealTime of `from`); both None exactly when from is None. Exact scaled dwell: game time between this event's
frame and the event that entered `from`.
"""
from collections import Counter
from collections.abc import Iterable

CATEGORIES = ("enemy", "hazard", "terrain", "player", "player_attack", "hazard_respawn", "gate", "breakable",
              "interactable", "other")
KINDS = ("box", "circle", "poly", "capsule", "edge", "aabb")

# GlobalEnums.HazardType
HAZARD_TYPES = ("NON_HAZARD", "ENEMY", "SPIKES", "ACID", "LAVA", "PIT", "COAL", "ZAP", "EXPLOSION", "SINK", "STEAM",
                "RESPAWN_PIT", "COAL_SPIKES")

# Entity "src" bits (EntityRegistry.Src)
SRC_BITS = {"health_manager": 1, "damage_hero": 2, "damages_hero_fsm": 4, "multi_wounder": 8, "cog": 16,
            "projectile": 32}
# Collider damage "parry" bits (EntityExporter.Parry*); damage["parryable"] == bool(parry & PARRYABLE)
PARRY_BITS = {"clash": 1, "force": 2, "counter": 4}
PARRYABLE = PARRY_BITS["clash"] | PARRY_BITS["force"]
# src bits of an entity that can hurt the hero (EntityRegistry.Src.Damage)
DAMAGE_SRC = SRC_BITS["damage_hero"] | SRC_BITS["damages_hero_fsm"] | SRC_BITS["multi_wounder"] | SRC_BITS["cog"]
# GlobalEnums.DamagePropertyFlags
DAMAGE_FLAGS = {"silk_acid": 1, "non_lethal": 2, "flame": 4, "void": 8, "acid": 16, "self": 32, "mid_chain": 64}

ENTITY_KEYS = frozenset(("iid", "type_key", "category", "src", "layer", "pos", "vel", "gravity_scale", "hp", "is_dead",
                         "inv", "fsms", "anim", "flipX", "render_aabb", "colliders"))
DAMAGE_KEYS = frozenset(("dealt", "eff", "hazard_type", "flags", "parry", "parryable", "can_cause_damage"))
FSM_KEYS = frozenset(("name", "state", "t", "rt"))
FSM_EVENT_KEYS = frozenset(("iid", "ent", "obj", "fsm", "from", "to", "t_in_prev", "rt_in_prev"))


def bits(value: int, table: dict[str, int]) -> list[str]:
    return [name for name, bit in table.items() if value & bit]


def hazard_name(h: int) -> str:
    return HAZARD_TYPES[h] if 0 <= h < len(HAZARD_TYPES) else f"?{h}"


def collider_points(c: dict) -> list[tuple[float, float]]:
    v = c["verts_world"]
    return [(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]


def is_threat(c: dict) -> bool:
    """An enabled collider that would hurt on contact now (eff -1 = amount known only to an FSM)."""
    d = c.get("damage")
    return bool(c.get("enabled") and d and d["can_cause_damage"] and d["eff"] != 0)


def fsm_events(state: dict) -> list[dict]:
    """The "fsm" events carried by one STATE (payload dicts, with the event frame added as "f")."""
    return [dict(ev["d"], f=ev["f"]) for ev in state.get("ev") or () if ev.get("k") == "fsm" and ev.get("d")]


def count_categories(ents: Iterable[dict]) -> Counter:
    return Counter(e["category"] for e in ents)


def validate_entity(e: dict) -> list[str]:
    """Schema problems of one entity (empty list = valid)."""
    errs = []
    missing = ENTITY_KEYS - e.keys()
    if missing:
        errs.append(f"missing keys {sorted(missing)}")
    extra = e.keys() - ENTITY_KEYS
    if extra:
        errs.append(f"unexpected keys {sorted(extra)}")
    if not isinstance(e.get("iid"), int):
        errs.append("iid not int")
    if e.get("category") not in CATEGORIES:
        errs.append(f"bad category {e.get('category')!r}")
    pos = e.get("pos")
    if not (isinstance(pos, list) and len(pos) == 3):
        errs.append("pos not [x, y, z]")
    if e.get("vel") is not None and len(e["vel"]) != 2:
        errs.append("vel not [x, y]")
    if (e.get("hp") is None) != (e.get("is_dead") is None):
        errs.append("hp and is_dead disagree on presence")
    if isinstance(e.get("src"), int) and bool(e["src"] & SRC_BITS["health_manager"]) != (e.get("hp") is not None):
        errs.append("hp present without the health_manager src bit, or missing with it")
    if e.get("render_aabb") is not None:
        a = e["render_aabb"]
        if len(a) != 4 or a[0] > a[2] or a[1] > a[3]:
            errs.append(f"bad render_aabb {a}")
    anim = e.get("anim")
    if anim is not None and anim["n"] > 0 and not 0 <= anim["frame"] < anim["n"]:
        errs.append(f"anim frame {anim['frame']} outside [0, {anim['n']})")
    for f in e.get("fsms") or ():
        if set(f) != FSM_KEYS:
            errs.append(f"bad fsm entry {f}")
    for i, c in enumerate(e.get("colliders") or ()):
        errs.extend(f"collider {i}: {m}" for m in validate_collider(c))
    return errs


def validate_collider(c: dict) -> list[str]:
    errs = []
    if c.get("kind") not in KINDS:
        errs.append(f"bad kind {c.get('kind')!r}")
    v = c.get("verts_world")
    if not isinstance(v, list) or len(v) % 2:
        errs.append("verts_world not a flat even-length list")
    elif c.get("kind") == "box" and len(v) != 8:
        errs.append(f"box with {len(v) // 2} points")
    elif c.get("kind") == "circle" and (len(v) != 16 or "r" not in c):
        errs.append("circle needs 8 points and r")
    d = c.get("damage")
    if d is not None and set(d) != DAMAGE_KEYS:
        errs.append(f"bad damage keys {sorted(d)}")
    elif d is not None and d["parryable"] != bool(d["parry"] & PARRYABLE):
        errs.append(f"parryable {d['parryable']} disagrees with parry bits {d['parry']}")
    return errs


def describe(e: dict) -> str:
    """One-line summary for logs."""
    hp = f" hp={e['hp']}{' dead' if e['is_dead'] else ''}" if e.get("hp") is not None else ""
    fsms = ", ".join(f"{f['name']}:{f['state']}@{f['t']:.2f}" for f in e.get("fsms") or ())
    threats = sum(is_threat(c) for c in e.get("colliders") or ())
    x, y, _ = e["pos"]
    return (f"{e['type_key']} [{e['category']}; {'+'.join(bits(e['src'], SRC_BITS)) or '-'}] ({x:.1f}, {y:.1f}){hp} "
            f"colliders={len(e.get('colliders') or ())} threats={threats} fsms=[{fsms}]")
