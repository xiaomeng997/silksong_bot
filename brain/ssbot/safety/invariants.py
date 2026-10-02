"""Invariants I1-I4 (DESIGN §3.7.2) as pure functions. The L0 safety filter vetoes plans that would break them
(§3.5.1); the supervisor turns a broken one into a trigger (I2 -> Q2). Geometry is not done here: the knockback
envelope (kinematics, M2 W1) is a callback that answers "does it touch this region", and commit zones are descriptors
built from the quit map, playbooks and the measured windows below.

    v = i2(hp=3, blue=0, ctx=Ctx(D1=2), h=2, regions=[Region("spikes", "hazard", 1, aabb)], touches=envelope.touches)
    if not v.ok: ...   # v.items names the regions the envelope must keep off

I1  quittable (pause and quit both reachable in the quit map) => hits_to_death >= 2. Quittability unknown (no or
    too little quit-map data) keeps I1 in force: a missing estimate never makes an invariant vacuous.
I2  HP - D1 <= a hazard's damage => the knockback envelope must not touch that hazard; with h <= 2 gates are soft
    hazards. HP here is health + blue - pending damage, and a CriticalDamage source in the support leaves 1 HP; the
    Fractured Mask is ignored (conservative: hazards pass i-frames, m0:N1, and a hazard death sequence is about 2.3 s
    of no pause, probe P7).
I3  any window with quit unreachable for more than 0.5 s, every kind listed in §3.7.2 whatever its length, and any
    unquittable window of unknown length ("unknown") is a commit zone: enter only at full HP, Fractured Mask not
    broken, and with h >= 2 after the window's worst event. Each zone key has its own G2 counter (ZoneLedger).
I4  every module confidence at or above its threshold, else the module's degradation rule applies.

Commit-zone kinds and the floors of their quit-unreachable lengths (seconds). A floor is the larger of the coded or
probed length and the longest window of that kind in quit map v0 (knowledge/1.0.30000/quit_map.json, rebuilt
2026-10-01 from the person's session 20260930_210337 and the closed Bell Beast recordings); QuitMap.zone() raises it
further when the map has seen longer:
  hazard_death       2.45 (spikes 1 mask 2.27-2.32 s, LAVA 2.43 s: disablePause from DieFromHazard to
                           FinishedEnteringScene; probe P7). Its worst event is the hazard damage plus D1 (an enemy
                           hit right after the respawn) unless a window Ctx is given
  arena_end_slowmo   1.9  (EnemyBattleEndSlow 0.1 / 1.0 / 0.75 at 0.25 speed, m0:N13; quit map 1.88-1.90 s)
  boss_death_slowmo  1.4  (BossDeathSlow 0.1 / 1.15 / 0.1 at 0.05 speed, m0:N13; quit map 1.38 s)
  room_entry         0.5  (HUDCamera.OnEnable PreventPause, entering from a cutscene, menu or stag scene; m0:N14)
  unpause_lockout    0.3  (real time after every unpause; m0:C12; also 0.20 s of HideMenu with no input, measured
                           in the human session 20260930_210337)
  boss_intro, elevator, cutscene, dialogue, arena_no_save_quit (disableSaveQuit), preload (the rest of a room once a
  ScenePreloader started, m0:C8), unknown: length from the quit map / playbook, else unbounded (math.inf).
A zone whose dangerous part is a FreezeMoment is not a moment the hero can be hit (the world is stopped), but its end
is: the zone's `window` Ctx describes what can land before quit is reachable again.
"""
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from ssbot.safety.hits_to_death import (MASK_BROKEN, MASK_INTACT, MASK_UNKNOWN, Ctx, hits_to_death,
                                        hits_to_death_after)

COMMIT_ZONE_S = 0.5
ZONE_KINDS = {   # kind -> floor of the quit-unreachable seconds (None: unknown, from the quit map or playbook)
    "hazard_death": 2.45, "arena_end_slowmo": 1.9, "boss_death_slowmo": 1.4, "room_entry": 0.5,
    "unpause_lockout": 0.3, "boss_intro": None, "elevator": None, "cutscene": None, "dialogue": None,
    "arena_no_save_quit": None, "preload": None, "unknown": None,
}


@dataclass(slots=True, frozen=True)
class Verdict:
    ok: bool
    rule: str
    reason: str = ""
    items: tuple[str, ...] = ()      # offending regions (I2), modules (I4)


@dataclass(slots=True, frozen=True)
class Region:
    """A hazard or a transition gate near the hero. geom is opaque here: whatever the envelope callback understands."""
    name: str
    kind: str                # "hazard" | "gate"
    damage: int = 0          # hazard damage after modifiers (SPIKES 1, LAVA 2, STEAM 2 ...; m0 §2.5); gates 0
    geom: object = None


EnvelopeTouches = Callable[[Region], bool]   # True: the knockback envelope (all reachable positions while frozen
                                             # and recoiling, any input, away from the source) meets the region


@dataclass(slots=True, frozen=True)
class CommitZone:
    key: str                         # G2 counter key, e.g. "Bone_05:boss_intro"
    kind: str                        # one of ZONE_KINDS, or "window" for a quit-map window
    unquittable_s: float | None = None   # None: the ZONE_KINDS floor (unknown: math.inf)
    window: Ctx | None = None        # worst event that can land inside the window; None: the current support (for
    #                                  hazard_death: the hazard damage on top of the support's D1)
    hazard_damage: int = 1           # hazard_death: the hazard's damage (SPIKES 1, LAVA 2 ...; m0 §2.5)

    @property
    def seconds(self) -> float:
        """Quit-unreachable length; math.inf when unknown (sizing U(c) from it can only over-cover)."""
        floor = ZONE_KINDS.get(self.kind)
        if self.unquittable_s is not None:
            return max(self.unquittable_s, floor or 0.0)
        return math.inf if floor is None else floor


def unknown_zone(key: str) -> CommitZone:
    """An unquittable window whose length nothing has measured: a commit zone (I3) of unbounded length."""
    return CommitZone(key=key, kind="unknown")


def is_commit_zone(zone: CommitZone) -> bool:
    return zone.kind in ZONE_KINDS or zone.seconds > COMMIT_ZONE_S


def i1(h: int, quittable: bool | None) -> Verdict:
    """quittable None (unknown) keeps I1 in force."""
    if quittable is not False and h < 2:
        return Verdict(False, "I1", f"{'quittable' if quittable else 'quittability unknown'} with hits_to_death "
                                    f"{h} < 2")
    return Verdict(True, "I1")


def i2(hp: int, blue: int, ctx: Ctx, h: int, regions: Sequence[Region], touches: EnvelopeTouches) -> Verdict:
    after = hp + blue - ctx.pending_dmg - ctx.D1
    if ctx.critical_in_support:
        after = min(after, 1)
    bad = []
    for r in regions:
        if r.kind == "hazard" and after <= r.damage and touches(r):
            bad.append(r.name)
        elif r.kind == "gate" and h <= 2 and touches(r):
            bad.append(r.name)
    if bad:
        return Verdict(False, "I2", f"knockback envelope meets {', '.join(bad)} with {after} HP after the worst hit",
                       tuple(bad))
    return Verdict(True, "I2")


def i3(zone: CommitZone, hp: int, max_hp: int, blue: int, mask: str, ctx: Ctx) -> Verdict:
    """May the hero enter `zone` now? `mask` is a hits_to_death MASK_* state; NONE (not equipped, audited) has nothing
    to break, UNKNOWN counts as broken."""
    if not is_commit_zone(zone):
        return Verdict(True, "I3")
    why = []
    if hp < max_hp:
        why.append(f"HP {hp} < {max_hp}")
    if mask in (MASK_BROKEN, MASK_UNKNOWN):
        why.append(f"Fractured Mask {mask}")
    worst = zone.window
    if worst is None:
        worst = replace(ctx, D1=ctx.D1 + zone.hazard_damage) if zone.kind == "hazard_death" else ctx
    h_after = hits_to_death_after(hp, blue, mask == MASK_INTACT, worst, ctx)
    if h_after < 2:
        why.append(f"h {h_after} < 2 after the window's worst event")
    if why:
        return Verdict(False, "I3", f"commit zone {zone.key}: " + "; ".join(why), (zone.key,))
    return Verdict(True, "I3")


def i4(confidence: Mapping[str, float], thresholds: Mapping[str, float]) -> Verdict:
    """A module without a reported confidence counts as below its threshold."""
    low = tuple(sorted(k for k, th in thresholds.items() if not confidence.get(k, 0.0) >= th))
    if low:
        return Verdict(False, "I4", "below threshold: " + ", ".join(low), low)
    return Verdict(True, "I4")


def check_all(h: int, quittable: bool | None, hp: int, max_hp: int, blue: int, mask: str, ctx: Ctx,
              regions: Sequence[Region] = (), touches: EnvelopeTouches | None = None,
              zones: Sequence[CommitZone] = (), confidence: Mapping[str, float] | None = None,
              thresholds: Mapping[str, float] | None = None) -> list[Verdict]:
    """Every broken invariant for one state (empty = all hold). zones: commit zones the plan is about to enter, or
    the unquittable window it is in. quittable False with no zone means a window of unknown length: an "unknown"
    commit zone, so neither I1 nor I3 goes vacuous."""
    out = [i1(h, quittable)]
    if regions and touches is not None:
        out.append(i2(hp, blue, ctx, h, regions, touches))
    if quittable is False and not zones:
        zones = (unknown_zone("current:unknown"),)
    out.extend(i3(z, hp, max_hp, blue, mask, ctx) for z in zones)
    if thresholds:
        out.append(i4(confidence or {}, thresholds))
    return [v for v in out if not v.ok]


def hits_now(hp: int, blue: int, mask: str, ctx: Ctx) -> int:
    return hits_to_death(hp, blue, mask == MASK_INTACT, ctx)


def gate_regions(s: dict) -> list[Region]:
    """Oracle mode: the enabled battle / arena gates of STATE room.gates [{name, enabled, box}] as I2 gate regions
    (geom = the box x0, y0, x1, y1). Empty when the oracle does not export them."""
    out = []
    for g in (s.get("room") or {}).get("gates") or ():
        if g.get("enabled") and g.get("box") is not None:
            out.append(Region(str(g.get("name")), "gate", 0, tuple(g["box"])))
    return out


@dataclass(slots=True)
class ZoneCounter:
    entries: int = 0
    clean: int = 0          # left without a hit
    hit: int = 0
    lethal: int = 0         # WOULD_DIE inside the zone


@dataclass(slots=True)
class ZoneLedger:
    """Per commit-zone G2 counts (§3.7.2 I3: each zone has its own G2 counter; the gate itself is tools/bayes_gate)."""
    zones: dict[str, ZoneCounter] = field(default_factory=dict)

    def enter(self, key: str) -> None:
        self.zones.setdefault(key, ZoneCounter()).entries += 1

    def leave(self, key: str, hit: bool = False, lethal: bool = False) -> None:
        c = self.zones.setdefault(key, ZoneCounter())
        if lethal:
            c.lethal += 1
        elif hit:
            c.hit += 1
        else:
            c.clean += 1
