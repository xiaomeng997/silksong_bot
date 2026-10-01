"""Invariants I1-I4 (DESIGN §3.7.2) as pure functions. The L0 safety filter vetoes plans that would break them
(§3.5.1); the supervisor turns a broken one into a trigger (I2 -> Q2). Geometry is not done here: the knockback
envelope (kinematics, M2 W1) is a callback that answers "does it touch this region", and commit zones are descriptors
built from the quit map, playbooks and the measured windows below.

    v = i2(hp=3, blue=0, ctx=Ctx(D1=2), h=2, regions=[Region("spikes", "hazard", 1, aabb)], touches=envelope.touches)
    if not v.ok: ...   # v.items names the regions the envelope must keep off

I1  quittable (pause and quit both reachable in the quit map) => hits_to_death >= 2.
I2  HP - D1 <= a hazard's damage => the knockback envelope must not touch that hazard; with h <= 2 gates are soft
    hazards. HP here is health + blue - pending damage, and a CriticalDamage source in the support leaves 1 HP; the
    Fractured Mask is ignored (conservative: hazards pass i-frames, m0:N1, and a hazard death sequence is about 2.3 s
    of no pause, probe P7).
I3  any window with quit unreachable for more than 0.5 s, and every kind listed in §3.7.2 whatever its length, is a
    commit zone: enter only at full HP, Fractured Mask not broken, and with h >= 2 after the window's worst event.
    Each zone key has its own G2 counter (ZoneLedger).
I4  every module confidence at or above its threshold, else the module's degradation rule applies.

Commit-zone kinds and their measured or coded lengths (seconds, quit unreachable):
  hazard_death       2.3  (spikes, 1 mask: disablePause from DieFromHazard to FinishedEnteringScene; probe P7)
  arena_end_slowmo   1.85 (EnemyBattleEndSlow 0.1 / 1.0 / 0.75 at 0.25 speed; m0:N13)
  boss_death_slowmo  1.35 (BossDeathSlow 0.1 / 1.15 / 0.1 at 0.05 speed; m0:N13)
  room_entry         0.5  (HUDCamera.OnEnable PreventPause, entering from a cutscene, menu or stag scene; m0:N14)
  unpause_lockout    0.3  (real time after every unpause; m0:C12; also 0.20 s of HideMenu with no input, measured
                           in the human session 20260930_210337)
  boss_intro, elevator, cutscene, dialogue, arena_no_save_quit (disableSaveQuit), preload (the rest of a room once a
  ScenePreloader started, m0:C8): lengths come from the quit map / playbook.
A zone whose dangerous part is a FreezeMoment is not a moment the hero can be hit (the world is stopped), but its end
is: the zone's `window` Ctx describes what can land before quit is reachable again.
"""
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from ssbot.safety.hits_to_death import (MASK_BROKEN, MASK_INTACT, MASK_UNKNOWN, Ctx, hits_to_death,
                                        hits_to_death_after)

COMMIT_ZONE_S = 0.5
ZONE_KINDS = {   # kind -> quit-unreachable seconds when known from code or probes (None: from the quit map)
    "hazard_death": 2.3, "arena_end_slowmo": 1.85, "boss_death_slowmo": 1.35, "room_entry": 0.5,
    "unpause_lockout": 0.3, "boss_intro": None, "elevator": None, "cutscene": None, "dialogue": None,
    "arena_no_save_quit": None, "preload": None,
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
    unquittable_s: float | None = None   # None: ZONE_KINDS default
    window: Ctx | None = None        # worst event that can land inside the window; None: the current support

    @property
    def seconds(self) -> float:
        if self.unquittable_s is not None:
            return self.unquittable_s
        return ZONE_KINDS.get(self.kind) or 0.0


def is_commit_zone(zone: CommitZone) -> bool:
    return zone.kind in ZONE_KINDS or zone.seconds > COMMIT_ZONE_S


def i1(h: int, quittable: bool) -> Verdict:
    if quittable and h < 2:
        return Verdict(False, "I1", f"quittable with hits_to_death {h} < 2")
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
    worst = zone.window if zone.window is not None else ctx
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


def check_all(h: int, quittable: bool, hp: int, max_hp: int, blue: int, mask: str, ctx: Ctx,
              regions: Sequence[Region] = (), touches: EnvelopeTouches | None = None,
              zones: Sequence[CommitZone] = (), confidence: Mapping[str, float] | None = None,
              thresholds: Mapping[str, float] | None = None) -> list[Verdict]:
    """Every broken invariant for one state (empty = all hold). zones: commit zones the plan is about to enter."""
    out = [i1(h, quittable)]
    if regions and touches is not None:
        out.append(i2(hp, blue, ctx, h, regions, touches))
    out.extend(i3(z, hp, max_hp, blue, mask, ctx) for z in zones)
    if thresholds:
        out.append(i4(confidence or {}, thresholds))
    return [v for v in out if not v.ok]


def hits_now(hp: int, blue: int, mask: str, ctx: Ctx) -> int:
    return hits_to_death(hp, blue, mask == MASK_INTACT, ctx)


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
