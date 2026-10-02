"""Invariants I1-I4 (DESIGN §3.7.2) with a stand-in knockback envelope (an x interval) and commit-zone descriptors;
unknown quittability and unknown zone lengths never make I1 / I3 vacuous."""
import math

from ssbot.safety.hits_to_death import MASK_BROKEN, MASK_INTACT, MASK_NONE, MASK_UNKNOWN, Ctx
from ssbot.safety.invariants import (ZONE_KINDS, CommitZone, Region, ZoneLedger, check_all, gate_regions, i1, i2, i3,
                                     i4, is_commit_zone, unknown_zone)

BELL = Ctx(D1=2)


def envelope(x0: float, x1: float):
    """A knockback envelope covering x0..x1 (world units); regions carry (a, b) x intervals as geom."""
    def touches(r: Region) -> bool:
        a, b = r.geom
        return a <= x1 and b >= x0
    return touches


SPIKES_NEAR = Region("spikes L", "hazard", 1, (70.0, 72.0))
LAVA_FAR = Region("lava", "hazard", 2, (100.0, 104.0))
GATE = Region("left1", "gate", 0, (71.5, 72.0))


def test_i1_quittable_needs_two_hits():
    assert i1(2, True).ok and i1(3, True).ok
    v = i1(1, True)
    assert not v.ok and v.rule == "I1"
    assert i1(1, False).ok          # not quittable: I3 governs instead
    v = i1(1, None)                 # unknown (no quit-map data): I1 stays in force
    assert not v.ok and "unknown" in v.reason
    assert i1(2, None).ok


def test_i2_hazard_in_envelope_only_when_the_hit_leaves_too_little():
    touch = envelope(69.0, 74.0)
    # 5 HP, Bell Beast hit -> 3 left > spikes 1: the envelope may touch the spikes
    assert i2(5, 0, BELL, 3, [SPIKES_NEAR], touch).ok
    # 3 HP -> 1 left <= 1: must not touch
    v = i2(3, 0, BELL, 2, [SPIKES_NEAR], touch)
    assert not v.ok and v.items == ("spikes L",)
    # blue health counts, pending damage counts
    assert i2(2, 1, BELL, 2, [SPIKES_NEAR], touch).ok is False      # 3 - 2 = 1
    assert i2(3, 1, BELL, 2, [SPIKES_NEAR], touch).ok               # 4 - 2 = 2 > 1
    assert not i2(4, 0, Ctx(D1=2, pending_dmg=1), 2, [SPIKES_NEAR], touch).ok
    # CriticalDamage in support leaves 1 HP whatever the health
    assert not i2(9, 0, Ctx(D1=1, critical_in_support=True), 2, [SPIKES_NEAR], touch).ok
    # a hazard out of reach never matters; lava (2) is lethal from 2 HP after the hit
    assert i2(4, 0, BELL, 2, [LAVA_FAR], touch).ok
    assert not i2(4, 0, BELL, 2, [LAVA_FAR], envelope(99.0, 101.0)).ok


def test_i2_gates_are_soft_hazards_at_low_h():
    touch = envelope(69.0, 74.0)
    assert i2(9, 0, BELL, 3, [GATE], touch).ok
    v = i2(9, 0, BELL, 2, [GATE], touch)
    assert not v.ok and v.items == ("left1",)


def test_i3_commit_zones():
    # boss intro: full HP and the mask not broken; after the worst event h >= 2
    intro = CommitZone("Bone_05:boss_intro", "boss_intro", 2.0)
    assert i3(intro, 5, 5, 0, MASK_NONE, BELL).ok                 # 5 -> 3: h 2 after the hit
    v = i3(intro, 4, 5, 0, MASK_NONE, BELL)
    assert not v.ok and "HP 4 < 5" in v.reason
    assert not i3(intro, 5, 5, 0, MASK_BROKEN, BELL).ok
    assert not i3(intro, 5, 5, 0, MASK_UNKNOWN, BELL).ok          # UNKNOWN counts as broken
    assert i3(intro, 5, 5, 0, MASK_INTACT, BELL).ok
    # 3 masks max: 3 -> 1, h after = 1 < 2
    v = i3(intro, 3, 3, 0, MASK_NONE, BELL)
    assert not v.ok and "after the window" in v.reason
    # ... but the Fractured Mask makes it 2
    assert i3(intro, 3, 3, 0, MASK_INTACT, BELL).ok
    # a window whose worst event is bigger than the current support
    heavy = CommitZone("Bone_05:rage", "window", 1.2, window=Ctx(D1=4))
    assert not i3(heavy, 5, 5, 0, MASK_NONE, BELL).ok


def test_commit_zone_kinds():
    assert is_commit_zone(CommitZone("x:unpause", "unpause_lockout"))          # 0.3 s but always a zone
    assert is_commit_zone(CommitZone("x:entry", "room_entry"))
    # floors at or above the longest windows of quit map v0 (review: 2.3 / 1.85 / 1.35 under-covered by <= 130 ms)
    assert CommitZone("x:hz", "hazard_death").seconds == 2.45
    assert CommitZone("x:hz", "hazard_death", 2.2).seconds == 2.45                 # a shorter estimate never lowers it
    assert CommitZone("x:hz", "hazard_death", 2.6).seconds == 2.6
    assert (ZONE_KINDS["arena_end_slowmo"], ZONE_KINDS["boss_death_slowmo"]) == (1.9, 1.4)
    # a kind without a code length and no estimate: unbounded; so is an unknown window
    assert CommitZone("x:intro", "boss_intro").seconds == math.inf
    z = unknown_zone("Nowhere:unknown")
    assert z.seconds == math.inf and is_commit_zone(z)
    assert is_commit_zone(CommitZone("x:w", "window", 0.6))
    assert not is_commit_zone(CommitZone("x:w", "window", 0.4))
    assert i3(CommitZone("x:w", "window", 0.4), 1, 5, 0, MASK_NONE, BELL).ok  # not a zone: I3 says nothing


def test_i3_hazard_death_adds_the_hazard_to_the_worst_event():
    """Review: a hazard_death zone without a window Ctx checked h after the enemy support only."""
    spikes = CommitZone("Bone_05:hazard_death:SPIKES", "hazard_death", hazard_damage=1)
    assert i3(spikes, 5, 5, 0, MASK_NONE, Ctx(D1=1)).ok               # 5 - (1 + 1) = 3, then h 3 >= 2
    v = i3(spikes, 5, 5, 0, MASK_NONE, BELL)                          # 5 - (1 + 2) = 2, then one Bell hit kills
    assert not v.ok and "after the window" in v.reason
    lava = CommitZone("x:hazard_death:LAVA", "hazard_death", hazard_damage=2)
    assert i3(lava, 5, 5, 0, MASK_NONE, Ctx(D1=1)).ok                 # 5 - (2 + 1) = 2, then h 2
    assert not i3(lava, 4, 4, 0, MASK_NONE, Ctx(D1=1)).ok             # 4 - 3 = 1, then h 1
    assert not i3(CommitZone("x:hz", "hazard_death"), 3, 3, 0, MASK_INTACT, BELL).ok   # 3 - (1 + 2): dead


def test_i4_confidences():
    assert i4({"hud": 0.99, "hero": 0.97}, {"hud": 0.95, "hero": 0.95}).ok
    v = i4({"hud": 0.90}, {"hud": 0.95, "hero": 0.95})
    assert not v.ok and v.items == ("hero", "hud")


def test_check_all_and_ledger():
    bad = check_all(1, True, 3, 5, 0, MASK_NONE, BELL, regions=[SPIKES_NEAR], touches=envelope(69.0, 74.0),
                    zones=[CommitZone("Bone_05:boss_intro", "boss_intro", 2.0)], confidence={"hud": 0.5},
                    thresholds={"hud": 0.9})
    assert [v.rule for v in bad] == ["I1", "I2", "I3", "I4"]
    assert check_all(3, True, 5, 5, 0, MASK_NONE, BELL) == []
    # quittable unknown: I1 in force; not quittable and no zone known: an unknown commit zone, so I3 applies
    assert [v.rule for v in check_all(1, None, 5, 5, 0, MASK_NONE, BELL)] == ["I1"]
    bad = check_all(2, False, 4, 5, 0, MASK_NONE, BELL)
    assert [v.rule for v in bad] == ["I3"] and "HP 4 < 5" in bad[0].reason
    assert check_all(2, False, 5, 5, 0, MASK_NONE, BELL) == []       # full HP, h 2 after the worst event
    # a known short window (quit map: hurt0, 0.25 s) is no commit zone
    assert check_all(2, False, 4, 5, 0, MASK_NONE, BELL, zones=[CommitZone("Bone_05:hurt0", "window", 0.25)]) == []
    led = ZoneLedger()
    led.enter("Bone_05:boss_intro")
    led.leave("Bone_05:boss_intro")
    led.enter("Bone_05:boss_intro")
    led.leave("Bone_05:boss_intro", hit=True)
    c = led.zones["Bone_05:boss_intro"]
    assert (c.entries, c.clean, c.hit, c.lethal) == (2, 1, 1, 0)


def test_gate_regions_from_state():
    """STATE room.gates (cross-module decision 5) as I2 gate regions; disabled gates and old STATEs give none."""
    s = {"room": {"gates": [{"name": "Battle Gate L", "enabled": True, "box": [70.0, 0.0, 71.0, 8.0]},
                            {"name": "Battle Gate R", "enabled": False, "box": [120.0, 0.0, 121.0, 8.0]}]}}
    rs = gate_regions(s)
    assert [(r.name, r.kind, r.geom) for r in rs] == [("Battle Gate L", "gate", (70.0, 0.0, 71.0, 8.0))]
    assert gate_regions({}) == [] and gate_regions({"room": {}}) == []
