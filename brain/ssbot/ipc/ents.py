"""Readers for the oracle's STATE "ents" section and the "fsm" / "hit" events (oracle/src/Entities, oracle/src/Events,
DESIGN §3.1.2; the M2 additions are listed with their sources in docs/facts/1.0.30000/state_fields_m2.md).

    for e in state["ents"] or []:
        if is_hidden(e): ...                   # seen before, HealthManager inactive now: no colliders
        for c in e["colliders"]:
            pts = collider_points(c)           # [(x, y), ...] world units
            if c["damage"] and c["enabled"] and c["damage"]["eff"] > 0: ...

Entity map: iid (unique within one STATE), type_key, category, src, layer, pos [x,y,z], vel [x,y]|None,
gravity_scale|None, hp|None, is_dead|None, inv|None (all three present exactly when src has the health_manager bit),
fsms [{name, state, t, rt}], anim {clip, frame, n}|None, flipX, render_aabb|None, hidden (M2), colliders.
pos is the root transform's position (the oracle's reference; WorldState.Entity.pos is derived from the colliders or
render_aabb by the backend, DESIGN §4.1).
fsms[].t: FsmState.StateTime (scaled; PlayMaker stops it once all of the state's actions have finished);
fsms[].rt: FsmState.StateRealTime (unscaled seconds since entry; never stops, but runs through pauses and hit-stop).
hidden (M2; absent in recordings made before it): True for a HealthManager root that was exported earlier in the same
scene and whose HealthManager is inactive now (component disabled or GameObject inactive, not dead), e.g. the Bell
Beast while underground (Submerged, Emerge Antic, Burst Antic, Rage Pos/Antic). It keeps pos, flipX, fsms, anim and
hp; colliders is always [] and render_aabb is None unless the GameObject is still active. An entity that an active
damage source of its own pulls into the export is never hidden, so hiding never drops a threat collider. Read it as
e.get("hidden", False).
Collider: kind, name (M2: the collider's GameObject name, e.g. "PolyCollider", "LeapCollider", or the root's own name
for a collider on the root; every path of a polygon has the same name), verts_world (flat x0, y0, x1, y1, ...),
enabled, layer, r (circles), damage|None.
Damage: dealt, eff, hazard_type, flags, parry, parryable, can_cause_damage. parryable = parry bit clash or force
(the source itself reacts to the nail: canClashTink, or an enabled forceParry); the counter bit (hazard ENEMY, what
the Cross Stitch stance catches) is not part of it.
Colliders that tk2d sprites add at run time (tk2dBaseSprite.UpdateCollider adds the BoxCollider2D the first time a
frame with a box is shown) are picked up the frame they appear. Before the M2 oracle they were missed until an
unrelated cache rebuild: recordings up to 2026-10-01 export the Bell Beast with colliders == [] during its whole first
Charge Emerge after each savestate load (trial run f42726-42769 and f56714-56758; live i0_000: 1209 of 1211 frames).
"fsm" event payload (state["ev"][i]["d"] where k == "fsm"): iid (GameObject holding the FSM), ent (its entity root),
obj (GameObject name), fsm, from (None on a start/restart), to, t_in_prev (StateTime of `from`), rt_in_prev
(StateRealTime of `from`); both None exactly when from is None. Exact scaled dwell: game time between this event's
frame and the event that entered `from`.
"hit" event payload (M2, k == "hit"; one per call of HealthManager.TakeDamage / ApplyExtraDamage that changed hp or
killed): ent (iid of the HealthManager root that lost hp, also when it is not in "ents"), type_key, dmg
(hp_before - hp_after), dealt (HitInstance.DamageDealt as passed, before the target's scaling), attack (AttackTypes
name), src (HitInstance.Source name, e.g. "Slash"; None without one), hp_before, hp_after, dead (hp_after <= 0 or
isDead), crit, plus the EventTap sequence number n.
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
# Written by the M2 oracle on every entity; absent in older recordings, so optional for validation.
ENTITY_KEYS_M2 = frozenset(("hidden",))
COLLIDER_KEYS = frozenset(("kind", "verts_world", "enabled", "layer", "damage"))   # + "r" for circles
COLLIDER_KEYS_M2 = frozenset(("name",))
DAMAGE_KEYS = frozenset(("dealt", "eff", "hazard_type", "flags", "parry", "parryable", "can_cause_damage"))
FSM_KEYS = frozenset(("name", "state", "t", "rt"))
FSM_EVENT_KEYS = frozenset(("iid", "ent", "obj", "fsm", "from", "to", "t_in_prev", "rt_in_prev"))
HIT_EVENT_KEYS = frozenset(("ent", "type_key", "dmg", "dealt", "attack", "src", "hp_before", "hp_after", "dead", "crit"))


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


def is_hidden(e: dict) -> bool:
    """A seen HealthManager root whose HealthManager is inactive now (M2 oracle; False for older recordings)."""
    return bool(e.get("hidden"))


def fsm_events(state: dict) -> list[dict]:
    """The "fsm" events carried by one STATE (payload dicts, with the event frame added as "f")."""
    return [dict(ev["d"], f=ev["f"]) for ev in state.get("ev") or () if ev.get("k") == "fsm" and ev.get("d")]


def hit_events(state: dict) -> list[dict]:
    """The "hit" events carried by one STATE (M2 oracle; payload dicts with the event frame added as "f")."""
    return [dict(ev["d"], f=ev["f"]) for ev in state.get("ev") or () if ev.get("k") == "hit" and ev.get("d")]


def count_categories(ents: Iterable[dict]) -> Counter:
    return Counter(e["category"] for e in ents)


def validate_entity(e: dict) -> list[str]:
    """Schema problems of one entity (empty list = valid)."""
    errs = []
    missing = ENTITY_KEYS - e.keys()
    if missing:
        errs.append(f"missing keys {sorted(missing)}")
    extra = e.keys() - ENTITY_KEYS - ENTITY_KEYS_M2
    if extra:
        errs.append(f"unexpected keys {sorted(extra)}")
    if "hidden" in e and not isinstance(e["hidden"], bool):
        errs.append("hidden not bool")
    if e.get("hidden") and e.get("colliders"):
        errs.append("hidden entity with colliders")
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
    missing = COLLIDER_KEYS - c.keys()
    if missing:
        errs.append(f"missing keys {sorted(missing)}")
    extra = c.keys() - COLLIDER_KEYS - COLLIDER_KEYS_M2 - {"r"}
    if extra:
        errs.append(f"unexpected keys {sorted(extra)}")
    if "name" in c and not isinstance(c["name"], str):
        errs.append("name not str")
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
    hidden = " hidden" if is_hidden(e) else ""
    return (f"{e['type_key']} [{e['category']}; {'+'.join(bits(e['src'], SRC_BITS)) or '-'}] ({x:.1f}, {y:.1f}){hp}"
            f"{hidden} colliders={len(e.get('colliders') or ())} threats={threats} fsms=[{fsms}]")
