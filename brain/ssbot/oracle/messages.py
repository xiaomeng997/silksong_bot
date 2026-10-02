"""Decoders for the oracle messages of M1 package events-scene-progress (DESIGN §4.6; oracle/src/Events,
oracle/src/SceneDump, oracle/src/Progress).

TERRAIN (one per gameplay room, on connect, on RPC "scene.dump"):
    {seq, reason, frame, transition, scene_raw, scene, scenes, loaded, cam, sm, cutscene,
     solids:  [{id, go, layer, on, body, flags, shapes}],        # TERRAIN / SOFT_TERRAIN colliders
     hazards: [{id, go, src, on, hazard, damage, flags, tink, trigger, body, shapes}],
              # src "dh" (DamageHero) or "fsm" (the legacy 'damages_hero' FSM, which HeroBox checks first; flags 0)
     gates, respawns, preloaders, battles, frost, no_clamber, cam_locks, harpoon, cogs, cutscene_info
         (each present only when the room has one): [{go, on, pos, shapes?, aabb?, ...}],
     layers, stats {objects, colliders_seen, verts, slices, frames, work_ms, ms}}
    gates:      + target, entry, side, door, inactive, non_hazard, listed, respawn?
    preloaders: + loads, started, has_trigger, trigger_on?, test_ok?, gate_white, gate_black
                  (shapes = the activate trigger's; no trigger = loads in Start; m0:C8)
    harpoon:    + id, kind ("pod" | "ring" | "tink", as HarpoonDashRayCheck classifies them), trigger, body
    battles:    + no_end_slomo, waves, set_pd_bool, gate_ids (solid ids of the arena walls)
    shape = {k: "box"|"poly"|"edge"|"circle"|"capsule", v: bin (little-endian float32 x, y pairs, world units), r?}

PROGRESS (<= 2 Hz; full snapshot on connect, PlayerData replacement and RPC "progress.full"):
    {seq, frame, full, reason, scene, t_live, changed: {field: value}}
    + when full: crest, tools, tool_equips, extra_equips, equipped, fields
    + in a diff whose tool data changed (Tools as GetToolData reads them, ToolEquips, ExtraToolEquips): crest,
      tools, tool_equips, extra_equips, equipped (complete sections, replacing the previous ones)
    A full snapshot is read at "frame" and written over a few frames.

STATE "ev": [{k, f, q, d}] with d["n"] a per-process event sequence number (gaps = events lost with a
dropped STATE). Events found by the per-frame poll (src "poll") are stamped with the frame they were seen in.
STATE sections: "tap" {n, hp, gates, freezes, respawns, poll_us, hooks_failed}, "room" {seq, transition, current,
busy, work_us (the TERRAIN dump's main-thread work in this frame), gates and gates_trunc (M2: live arena gates and
changed solids over the TERRAIN snapshot, docs/facts/1.0.30000/state_fields_m2.md section 11)}, "prog" {seq, pending,
chunk, fields, building, ok}.

Event kinds (k) and payload keys (d); "fsm" = "GameObject/Fsm/State:Action" when a PlayMaker FSM was executing,
"caller" = up to 6 managed frames, innermost first:
    hp            h, hb, delta, blue_delta, src (TakeHealth | AddHealth | MaxHealth | AddToMaxHealth | SetInt | IntAdd |
                  IncrementInt | DecrementInt | SetVariable | HeroItemsState.Apply | direct | poll), ctx?, hazard_type?,
                  source?, caller?, fsm?; TakeHealth adds amount, lifeblood, allow_mask_break, mask_left, mask_broke,
                  mask_saved
    damage        source, side, amount, hazard, flags, flag_names, can_take, invuln, parry_t, recoiling, h, hb,
                  re_respawn? (a hazard within 0.5 s of a hazard respawn: respawns again)  (attempts past the gates)
    damage_blocked source, hazard, why, n, amount, side, flags, first_f, last_f, end (ended | hit | full)
                  (TakeDamage no-ops of one contact, collapsed: HeroBox retries every physics step. why: iframes = its
                  invulnerability gate (i-frames, recoil, parry timer, hazard death, invincibility), zero = amount 0,
                  interact = Self damage while an interactable blocks)
    special_damage method, amount, event, can_die, allow_mask_break, just_take_health, frost, transitioning, h, hb
                  (or method + reached_special=False when the entry point never reached DoSpecialDamage)
    die           non_lethal, frost, dead_already, h, pd_mode, memory, ctx?, caller      (attempt; guards may block)
    death_catch   dead, h, hb, catch (this call starts Die), pd_mode, ctx?, caller, fsm?
    pd_mode       from, to, src (TakeDamage | DoSpecialDamage | CheckDeathCatch | poll), scene, h, ctx?, hazard_type?,
                  source?, fsm?                                                (every permadeathMode change)
    hazard_death  hazard, h, ctx?
    player_dead   wait, h, pd_mode
    gs            from, to, from_i, to_i, scene
    scene_leave   from_raw, from, to, gate, first_level, seq
    scene_enter   scene_raw, scene, gate, gameplay, state, seq, pos            (once per transition)
    hazard_respawn phase start (id, scene, from, marker, open) | end (id, reason, scene, pos, ms, frames)
                  end reason: done | transition (no ground point: it began a scene transition) | exception | disposed |
                  room_left | no_game_manager | game_manager_rebuilt; "end" comes from the coroutine's last step
    freeze        phase start (id, type, down, wait, up, speed, caller?) | end (id, type, ms, frames, reason)
                  type = FreezeMomentTypes name, or "direct:<caller>" (e.g. the hero's own damage freeze)
    hunter_meter  reason, from, to, crest, caller? (crest_reset), fsm?         (the Hunter combo meter, STATE
                  hero.hunter_meter, went down, i.e. was reset. reason: damage | special_damage | max_health | maggoted |
                  equips_changed | crest_reset (hero Awake, FixUpSaveState) | hero_rebuilt | unknown (seen by the poll))
    pause_gate    gate (disable_pause | disable_save_quit | disable_inventory | inventory_open | pause_allowed |
                  msg_canvas | in_msg), value, src (hook name or "poll"), key? (msg_canvas), object? (in_msg)
    save          phase begin (id, kind save|restore_point, slot, auto, auto_name, t_saved, t_live, caller) |
                  done (id, kind, ok, ms)                                       (no done = suppressed by a guard)
    ending        what check_completion (scene_raw, scene, frame, state, t_live, t_saved, pd_mode, completion,
                  endings, caller, executing_fsm, candidates, active_fsms) | set_ending_completed (ending, endings,
                  t_saved, t_live, scene_raw, frame, fsm)                       (also written to the BepInEx log)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import msgpack
import numpy as np

from ssbot.ipc.framing import HEADER

# "tap".gates bits (oracle/src/Events/GateTap.cs).
GATE_BITS = {
    "disable_pause": 1, "disable_save_quit": 2, "disable_inventory": 4,
    "inventory_open": 8, "pause_allowed": 16, "msg_canvas": 32,
}

# TERRAIN solid flags (oracle/src/SceneDump/SceneDumper.cs).
NON_SLIDER, STEEP_SLOPE, SLIDE_SURFACE, NON_BOUNCER, BREAKABLE, SOFT_TERRAIN = 1, 2, 4, 8, 16, 32
BODY_NAMES = {0: "static", 1: "kinematic", 2: "dynamic"}

ZONE_KEYS = ("gates", "respawns", "preloaders", "battles", "frost", "no_clamber", "cam_locks", "harpoon", "cogs",
             "cutscene_info")


def split_frame(raw: bytes) -> tuple[int, int, bytes]:
    """(msg_type, seq, payload) of one whole frame as OracleLink.subscribe_raw passes it."""
    _length, msg_type, _schema, _flags, seq = HEADER.unpack_from(raw, 0)
    return msg_type, seq, raw[HEADER.size:]


def unpack(payload: bytes) -> dict:
    return msgpack.unpackb(payload, raw=False, strict_map_key=False)


def verts(blob: bytes) -> np.ndarray:
    """A shape's vertex bin as an (n, 2) float32 array."""
    return np.frombuffer(blob, dtype="<f4").reshape(-1, 2)


@dataclass
class Shape:
    kind: str
    verts: np.ndarray
    radius: float = 0.0

    @property
    def closed(self) -> bool:
        return self.kind in ("box", "poly", "capsule")


def _shapes(items: list | None) -> list[Shape]:
    return [Shape(s["k"], verts(s["v"]), float(s.get("r", 0.0))) for s in items or ()]


@dataclass
class Solid:
    id: int
    go: str
    layer: int
    on: bool
    body: int
    flags: int
    shapes: list[Shape]

    def has(self, flag: int) -> bool:
        return bool(self.flags & flag)


@dataclass
class Hazard:
    id: int
    go: str
    on: bool
    hazard: str
    damage: int
    flags: int
    tink: bool
    trigger: bool
    body: int
    shapes: list[Shape]
    src: str = "dh"


@dataclass
class Terrain:
    """A decoded TERRAIN message. Zones keep their dict form with "shapes" decoded into Shape lists."""
    seq: int
    scene_raw: str
    scene: str
    reason: str
    frame: int
    solids: list[Solid]
    hazards: list[Hazard]
    zones: dict[str, list[dict]]
    cam: dict
    sm: dict
    stats: dict
    raw: dict = field(repr=False, default_factory=dict)

    @classmethod
    def decode(cls, msg: dict) -> "Terrain":
        solids = [Solid(s["id"], s["go"], s["layer"], s["on"], s["body"], s["flags"], _shapes(s["shapes"]))
                  for s in msg.get("solids", ())]
        hazards = [Hazard(h["id"], h["go"], h["on"], h["hazard"], h["damage"], h["flags"], h["tink"], h["trigger"],
                          h["body"], _shapes(h["shapes"]), h.get("src", "dh")) for h in msg.get("hazards", ())]
        zones = {}
        for key in ZONE_KEYS:
            items = []
            for z in msg.get(key, ()):
                z = dict(z)
                if "shapes" in z:
                    z["shapes"] = _shapes(z["shapes"])
                items.append(z)
            zones[key] = items
        return cls(msg["seq"], msg["scene_raw"], msg["scene"], msg["reason"], msg["frame"], solids, hazards, zones,
                   msg.get("cam", {}), msg.get("sm", {}), msg.get("stats", {}), msg)

    def bounds(self, active_only: bool = False) -> tuple[float, float, float, float] | None:
        """(xmin, ymin, xmax, ymax) over all solid vertices."""
        pts = [s.verts for sol in self.solids if sol.on or not active_only for s in sol.shapes if len(s.verts)]
        if not pts:
            return None
        allv = np.concatenate(pts)
        return float(allv[:, 0].min()), float(allv[:, 1].min()), float(allv[:, 0].max()), float(allv[:, 1].max())

    def summary(self) -> dict:
        return {
            "seq": self.seq, "scene": self.scene_raw, "reason": self.reason, "solids": len(self.solids),
            "solids_on": sum(s.on for s in self.solids), "hazards": len(self.hazards),
            "verts": int(sum(len(s.verts) for sol in self.solids for s in sol.shapes)),
            **{k: len(v) for k, v in self.zones.items() if v},
        }


class ProgressMirror:
    """PlayerData primitive fields (and the tool/crest snapshot) rebuilt from PROGRESS messages."""

    def __init__(self) -> None:
        self.fields: dict = {}
        self.tools: dict = {}
        self.crest: dict = {}
        self.tool_equips: dict = {}
        self.extra_equips: dict = {}
        self.equipped: list = []
        self.seq = 0
        self.full_seq = 0
        self.messages = 0

    @property
    def synced(self) -> bool:
        """True once a full snapshot has been applied (diffs before that are partial)."""
        return self.full_seq > 0

    def apply(self, msg: dict) -> dict:
        """Apply one PROGRESS message; returns its changed fields."""
        changed = msg.get("changed", {})
        if msg.get("full"):
            self.fields = dict(changed)
            self.full_seq = msg["seq"]
        else:
            self.fields.update(changed)
        # Full snapshots always carry the tool sections; diffs carry them (complete) when the tool data changed.
        if "tools" in msg:
            self.tools = msg.get("tools", {})
            self.crest = msg.get("crest", {})
            self.tool_equips = msg.get("tool_equips", {})
            self.extra_equips = msg.get("extra_equips", {})
            self.equipped = msg.get("equipped", [])
        self.seq = msg["seq"]
        self.messages += 1
        return changed


class EventLog:
    """Collects STATE events in order and counts gaps in their sequence numbers (events lost with dropped STATEs)."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.last_n: int | None = None
        self.lost = 0

    def add_state(self, state: dict) -> list[dict]:
        new = []
        for e in state.get("ev", ()):
            d = e.get("d") or {}
            n = d.get("n")
            if n is not None:
                if self.last_n is not None and n > self.last_n + 1:
                    self.lost += n - self.last_n - 1
                if self.last_n is None or n > self.last_n:
                    self.last_n = n
            flat = {"k": e["k"], "f": e["f"], **d}
            self.events.append(flat)
            new.append(flat)
        return new

    def of(self, *kinds: str, since_frame: int = -1) -> list[dict]:
        return [e for e in self.events if e["k"] in kinds and e["f"] > since_frame]
