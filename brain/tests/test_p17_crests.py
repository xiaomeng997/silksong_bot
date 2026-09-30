"""Offline checks of the P17 crest probe: the pure table/extent helpers and the equip/restore flow against a fake link
(the probe itself needs the running game)."""
import copy
from concurrent.futures import Future

import msgpack
import pytest

from ssbot.ipc.framing import MsgType, encode
from ssbot.ipc.oracle_link import OracleError
from ssbot.probes import p17_crests as p17


def box(x0, y0, x1, y1, r=0.0):
    return {"k": "box", "v": [x0, y0, x1, y0, x1, y1, x0, y1], "r": r}


def damager(path, shapes, swing=None, **kw):
    col = {"type": "PolygonCollider2D", "enabled": False, "trigger": True, "layer": 17, "shapes": shapes}
    if swing is not None:
        col["shapes_swing"] = swing
    d = {"path": path, "attack_type": "Nail", "nail_tag": False, "use_nail_damage": True, "nail_damage_mult": 1.0,
         "damage_dealt": 0, "damage_mult": 1.0,
         "damage_mult_per_hit": [], "multi_hitter": False, "steps_per_hit": 0, "hits_until_death": 0,
         "silk_generation": "Full", "does_not_parry": False, "does_not_critical_hit": False, "colliders": [col]}
    d.update(kw)
    return d


def attack(slot, path, damagers, paired=None, spikes=True, down=(), clash=None):
    nail = {"path": path, "type": "NailSlash", "can_hit_spikes": spikes}
    if clash is not None:
        nail["clash_tink"] = [{"type": "PolygonCollider2D", "enabled": False, "shapes": clash}]
    return {"slot": slot, "source": "hero", "go": path.rsplit("/", 1)[-1], "path": path, "active": True,
            "component": "NailSlash", "damager": paired, "nail": [nail], "damagers": damagers, "down_attacks": list(down)}


def slash_dump(crest, reach, facing=1, pos=(10.0, 5.0)):
    """A normal slash reaching `reach` forward of a hero at `pos`, and a down slash with HeroDownAttack."""
    x0, x1 = (pos[0] + 0.5, pos[0] + reach) if facing > 0 else (pos[0] - reach, pos[0] - 0.5)
    cx0, cx1 = (x0, x1 - 0.25) if facing > 0 else (x0 + 0.25, x1)      # the clash poly is 0.25 shorter
    return {
        "crest": crest, "config": crest + "Config", "hero": {"pos": [pos[0], pos[1], 0.004], "facing": facing},
        "attacks": [
            attack("normal", "Attacks/" + crest + "/Slash",
                   [damager("Attacks/" + crest + "/Slash", [box(x0, pos[1] - 1, x1, pos[1] + 1.5)])],
                   paired="Attacks/" + crest + "/Slash", clash=[box(cx0, pos[1] - 0.5, cx1, pos[1] + 0.5)]),
            attack("down", "Attacks/" + crest + "/DownSlash",
                   [damager("Attacks/" + crest + "/DownSlash", [box(pos[0] - 1, pos[1] - 3, pos[0] + 1, pos[1] - 0.5)],
                            damage_mult_per_hit=[1.0, 0.5])],
                   down=["Attacks/" + crest + "/DownSlash"]),
        ],
    }


def crest_entry(name, unlocked, config=None, index=None, rule="match"):
    return {"name": name, "unlocked": unlocked, "config": config,
            "config_group": {"index": index, "special": None, "rule": rule}}


def config(name, dur, cd, rec, down="Slash", **extra):
    fields = {"attackDuration": dur, "attackCooldownTime": cd, "attackRecoveryTime": rec,
              "quickAttackCooldownTime": cd * 0.8, "downSlashType": down, "downspikeAnticTime": 0.1,
              "downspikeTime": 0.2, "downspikeRecoveryTime": 0.25, "dashStabTime": 0.15, **extra}
    return {"name": name, "type": "HeroControllerConfig", "fields": fields, "values": None}


# ---- pure helpers ---------------------------------------------------------------------------------------------------

def test_extents_follow_facing():
    shapes = [box(10.5, 4.0, 13.0, 6.5)]
    assert p17.extents(shapes, (10.0, 5.0), 1) == {"fwd": 3.0, "back": -0.5, "up": 1.5, "dn": 1.0}
    mirrored = [box(7.0, 4.0, 9.5, 6.5)]
    assert p17.extents(mirrored, (10.0, 5.0), -1) == {"fwd": 3.0, "back": -0.5, "up": 1.5, "dn": 1.0}
    # The same shape seen from a hero facing the other way reaches backwards.
    assert p17.extents(shapes, (10.0, 5.0), -1)["back"] == 3.0
    assert p17.extents([], (0.0, 0.0), 1) is None


def test_extents_count_radius_as_disc():
    circle = {"k": "circle", "v": [12.0, 5.0], "r": 1.0}
    assert p17.extents([circle], (10.0, 5.0), 1) == {"fwd": 3.0, "back": -1.0, "up": 1.0, "dn": 1.0}
    rounded_box = box(10.5, 4.0, 13.0, 6.5, r=0.25)
    assert p17.extents([rounded_box], (10.0, 5.0), 1)["fwd"] == 3.25


def test_damager_shapes_prefer_swing_outline():
    d = damager("a", [box(0, 0, 1, 1)], swing=[box(0, 0, 2, 2)])
    assert p17.damager_shapes(d) == [box(0, 0, 2, 2)]
    assert p17.damager_shapes(damager("a", [box(0, 0, 1, 1)])) == [box(0, 0, 1, 1)]
    assert p17.damager_shapes(None) == []


def test_primary_damager_and_nail():
    main = damager("Attacks/S", [box(0, 0, 1, 1)])
    extra = damager("Attacks/S/Extra Damager", [box(0, 0, 5, 5)])
    paired = damager("Attacks/Other", [box(0, 0, 2, 2)])
    a = attack("normal", "Attacks/S", [extra, main, paired], paired="Attacks/Other")
    assert p17.primary_damager(a) is paired             # the damager SetConfigGroup paired with the slot
    a["damager"] = None
    assert p17.primary_damager(a) is main               # else the one on the attack object
    a["path"] = "Attacks/Elsewhere"
    assert p17.primary_damager(a) is extra              # else the first using nail damage
    assert p17.primary_nail(attack("x", "A", [])) == {"path": "A", "type": "NailSlash", "can_hit_spikes": True}
    assert p17.primary_damager({"damagers": []}) is None


def test_damage_text():
    assert p17.damage_text(damager("a", [])) == "x1"
    assert p17.damage_text(damager("a", [], damage_mult_per_hit=[1.0, 0.5], damage_mult=1.5)) == "x1*1.5[1,0.5]"
    assert p17.damage_text(damager("a", [], use_nail_damage=False, damage_dealt=5)) == "=5"
    assert p17.damage_text(None) == "-"


def test_config_row_swing_and_fallback_group():
    dump = {
        "groups": [{"index": 0, "kind": "configs", "config": "Default"}, {"index": 1, "kind": "configs", "config": "Wanderer"},
                   {"index": 0, "kind": "special", "config": "Warrior"}],
        "configs": {"Default": config("Default", 0.35, 0.41, 0.15, down="DownSpike"),
                    "Wanderer": config("Wanderer", 0.25, 0.2, 0.1)},
    }
    hunter = p17.config_row(crest_entry("Hunter", True, None, 0, "no_config:configs[0]"), dump)
    assert hunter["config"] == "Default" and hunter["rule"] == "no_config:configs[0]"
    assert hunter["swing"] == 0.41 and hunter["recovery"] == 0.15
    assert hunter["spike"] == [0.1, 0.2, 0.25] and hunter["down"] == "DownSpike"
    wanderer = p17.config_row(crest_entry("Wanderer", False, "Wanderer", 1), dump)
    assert wanderer["swing"] == 0.25          # duration longer than the cooldown: DidAttack raises the cooldown
    assert wanderer["quick"] == 0.25 and wanderer["spike"] is None
    unknown = p17.config_row(crest_entry("Ghost", False, "Missing", None, "no_group"), dump)
    assert unknown["swing"] is None and unknown["config"] == "Missing"


def test_attack_rows_and_tables():
    rows = p17.attack_rows("Wanderer", slash_dump("Wanderer", 3.0, facing=-1))
    normal, down = rows
    assert normal["slot"] == "normal" and normal["dmg"] == "x1" and normal["silk"] == "Full"
    assert normal["spikes"] is True and normal["parry"] is True and normal["crit"] is True and not normal["dsa"]
    assert normal["fwd"] == pytest.approx(3.0) and normal["back"] == pytest.approx(-0.5)
    assert normal["clash"] == pytest.approx(2.75) and down["clash"] is None
    slash = slash_dump("Reaper", 3.0)
    slash["attacks"][0]["damagers"][0].update(attack_type="Generic")
    slash["attacks"][1]["damagers"][0].update(attack_type="Generic", nail_tag=True, does_not_critical_hit=True)
    assert [r["crit"] for r in p17.attack_rows("Reaper", slash)] == [False, True]   # the "Nail Attack" tag always may
    assert down["dsa"] and down["dmg"] == "x1[1,0.5]" and down["dn"] == pytest.approx(3.0)
    text = p17.format_table(rows, p17.ATTACK_COLUMNS)
    lines = text.splitlines()
    assert lines[0].split()[:4] == ["crest", "slot", "src", "object"] and set(lines[1]) <= {"-", " "}
    assert "Wanderer" in lines[2] and "3" in lines[2] and len(lines) == 4


def test_custom_down_slash_rows_are_flagged():
    slash = slash_dump("Witch", 3.0)
    down = slash["attacks"][1]
    down.update(source="group", component=None, down_slash_event="WITCH DOWN")
    rows = p17.attack_rows("Witch", slash)
    assert [(r["slot"], r["source"], r["down_slash_event"]) for r in rows] == [
        ("normal", "hero", None), ("down", "group", "WITCH DOWN")]
    assert rows[1]["dmg"] == "x1[1,0.5]" and rows[1]["dn"] == pytest.approx(3.0)
    assert "group" in p17.format_table(rows, p17.ATTACK_COLUMNS).splitlines()[3].split()


def test_crest_order_and_rounded():
    assert p17.crest_order("Hunter", ["Wanderer", "Hunter", "", "Wanderer", "Reaper"]) == ["Hunter", "Wanderer", "Reaper"]
    assert p17.crest_order(None, ["A"]) == ["A"]
    assert p17.rounded({"a": [0.30000001192092896, (1, 2.123456789)], "b": b"\x01"}) == {"a": [0.3, [1, 2.12346]], "b": "01"}


def test_restore_state_and_diffs():
    dump = {"current": {"crest": "Hunter", "previous": "Wanderer", "temp": False, "silk": 12},
            "crests": [{"name": "Hunter", "unlocked": True, "slots": [{"i": 0, "saved": {"tool": "Compass", "unlocked": True}}]},
                       {"name": "Reaper", "unlocked": False, "slots": [{"i": 0, "saved": None}]}],
            "tool_amounts": {"Straight Pin": 10, "Compass": 0}}
    before = p17.restore_state(dump)
    assert before == {"crest": "Hunter", "previous": "Wanderer", "temp": False, "silk": 12, "silk_max": None,
                      "unlocked": ["Hunter"],
                      "slots": {"Hunter": [{"tool": "Compass", "unlocked": True}], "Reaper": [None]},
                      "tool_amounts": {"Straight Pin": 10, "Compass": 0}}
    assert p17.restore_diffs(before, copy.deepcopy(before)) == []
    after = copy.deepcopy(before)
    after.update(temp=True, silk=9)
    after["slots"]["Hunter"][0]["tool"] = None
    after["tool_amounts"]["Straight Pin"] = 7
    assert p17.restore_diffs(before, after) == [
        "restore: temp flag is True, was False",
        "restore: silk is 9, was 12",
        "restore: saved slots of Hunter are [{'tool': None, 'unlocked': True}], were [{'tool': 'Compass', 'unlocked': True}]",
        "restore: tool amounts {'Straight Pin': '7 (was 10)'}",
    ]


def test_silk_may_grow_from_regen_but_not_drop_or_pass_the_max():
    before = {"silk": 2, "silk_max": 12}
    assert p17.silk_diff(before, {"silk": 2, "silk_max": 12}) is None
    assert p17.silk_diff(before, {"silk": 3, "silk_max": 12}) is None           # a Silk Heart regen tick
    assert p17.silk_diff(before, {"silk": 12, "silk_max": 12}) is None
    assert p17.silk_diff(before, {"silk": 1, "silk_max": 12}) == "restore: silk is 1, was 2"
    assert p17.silk_diff(before, {"silk": 13, "silk_max": 12}) == "restore: silk is 13, was 2, max 12"
    # Without the max (an older oracle, or no hero) only unchanged silk passes.
    assert p17.silk_diff(before, {"silk": 3, "silk_max": None}) == "restore: silk is 3, was 2, max None"
    assert p17.silk_diff({"silk": 2}, {"silk": None}) == "restore: silk is None, was 2"
    assert p17.restore_diffs({"silk": 5, "silk_max": 9}, {"silk": 6, "silk_max": 9}) == []
    assert p17.restore_diffs({"silk": 5, "silk_max": 9}, {"silk": 4, "silk_max": 9}) == ["restore: silk is 4, was 5"]


# ---- the equip / restore flow against a fake oracle ----------------------------------------------------------------

class FakeGame:
    """Just enough of crest.dump / slash.dump / crest.equip / guards.* to drive p17.run. crest.equip follows CrestEquip:
    errors carry the exception type (Rpc.Invoke), the snapshot is taken before the unlock check, and the bench path's
    side effects are there: leaving Hunter (it carries Shell Satchel and Spool Extender) caps Straight Pin and silk the
    way UpdateToolCap and RefreshSilk do, and equipping Hunter empties its Compass slot (Compass is also in an extra
    slot), which restore puts back unless restore_extras is off. Restore only ever gives silk back (PlayerData.AddSilk);
    regen=True adds a Silk Heart regen tick (up to REGEN_MAX) after every switch."""

    REGEN_MAX = 3

    CONFIGS = {"Default": config("Default", 0.35, 0.41, 0.15, down="DownSpike"),
               "Wanderer": config("Wanderer", 0.25, 0.3, 0.1), "Reaper": config("Reaper", 0.3, 0.35, 0.12)}

    def __init__(self, relock=True, restore_extras=True, refuse_restore=False, dump_fails_after_restore=False,
                 regen=False):
        self.crest, self.previous, self.temp = "Hunter", "Wanderer", False
        self.unlocked = {"Hunter": True, "Hunter_v2": False, "Wanderer": False, "Reaper": False}
        self.slots = {"Hunter": [{"tool": "Straight Pin", "unlocked": True}, {"tool": "Compass", "unlocked": True}]}
        self.silk = 12
        self.amounts = {"Straight Pin": 10, "Compass": 0}
        self.snapshot = None
        self.restore_called = False
        self.save_suppression = False
        self.relock, self.restore_extras, self.refuse_restore = relock, restore_extras, refuse_restore
        self.dump_fails_after_restore = dump_fails_after_restore
        self.regen = regen
        self.calls = []

    def silk_max(self):
        return 12 if self.crest == "Hunter" else 9          # Hunter carries Spool Extender

    def config_of(self, name):
        return {"Wanderer": "Wanderer", "Reaper": "Reaper"}.get(name)

    def crest_dump(self):
        crests = []
        for n, u in self.unlocked.items():
            e = crest_entry(n, u, self.config_of(n), {"Wanderer": 1, "Reaper": 2}.get(n, 0),
                            "match" if self.config_of(n) else "no_config:configs[0]")
            saved = self.slots.get(n)
            e["slots"] = [{"i": i, "saved": copy.deepcopy(saved[i]) if saved else None} for i in range(2)]
            crests.append(e)
        return {"frame": 1, "crests": crests,
                "current": {"crest": self.crest, "previous": self.previous, "temp": self.temp, "silk": self.silk,
                            "silk_max": self.silk_max(), "config": self.config_of(self.crest) or "Default"},
                "groups": [{"index": i, "kind": "configs", "config": c} for i, c in enumerate(("Default", "Wanderer", "Reaper"))],
                "configs": copy.deepcopy(self.CONFIGS), "extra_equips": {"extra_0": "Compass"},
                "tool_amounts": dict(self.amounts)}

    def rpc(self, name, args):
        self.calls.append((name, args))
        if name == "gameplay.dump":
            return {"asset": "Global Gameplay Settings", "hunter": {"combo_hits": 6}}
        if name == "crest.dump":
            if self.restore_called and self.dump_fails_after_restore:
                raise TimeoutError("no reply to crest.dump")
            return self.crest_dump()
        if name == "slash.dump":
            d = slash_dump(self.crest, {"Wanderer": 2.9}.get(self.crest, 3.0))
            if args.get("all_groups"):
                d["groups"] = [{"index": 0, "kind": "configs", "config": "Default", "attacks": []}]
            return d
        if name == "guards.get":
            return {"save_suppression": self.save_suppression}
        if name == "guards.set":
            self.save_suppression = args["save_suppression"]
            return {"save_suppression": self.save_suppression}
        if name == "crest.equip":
            return self.equip(args)
        raise OracleError(f"ArgumentException: unknown rpc '{name}'")

    def switch(self, name):
        """ToolItemManager.SetEquippedCrest + SendEquippedChangedEvent, with their side effects."""
        if name == "Hunter":
            self.slots["Hunter"][1]["tool"] = None
        elif self.crest == "Hunter":
            self.amounts["Straight Pin"] = min(self.amounts["Straight Pin"], 7)
        if name != self.crest:
            self.previous, self.crest, self.temp = self.crest, name, False
        self.silk = min(self.silk, self.silk_max())                         # RefreshSilk
        if self.regen and self.silk < min(self.REGEN_MAX, self.silk_max()):
            self.silk += 1

    def equip(self, args):
        if args.get("restore"):
            self.restore_called = True
            if self.snapshot is None:
                raise OracleError("InvalidOperationException: nothing to restore: crest.equip changed nothing on this PlayerData")
            if self.refuse_restore:
                raise OracleError("InvalidOperationException: close the inventory first")
            snap, self.snapshot = self.snapshot, None
            self.switch(snap["crest"])
            self.previous, self.temp = snap["previous"], snap["temp"]
            if self.relock:
                self.unlocked = snap["unlocked"]
            if self.restore_extras:
                self.slots, self.amounts = snap["slots"], snap["amounts"]
                if self.silk < snap["silk"]:
                    self.silk = min(snap["silk"], self.silk_max())
            return {"restored": True, "crest": self.crest, "previous": self.previous, "temp": self.temp}
        name = args["name"]
        if name not in self.unlocked:
            raise OracleError(f"ArgumentException: no crest '{name}'")
        if self.snapshot is None:
            self.snapshot = {"crest": self.crest, "previous": self.previous, "temp": self.temp,
                             "unlocked": dict(self.unlocked), "slots": copy.deepcopy(self.slots),
                             "amounts": dict(self.amounts), "silk": self.silk}
        if not self.unlocked[name] and not args.get("unlock"):
            raise OracleError(f"InvalidOperationException: crest '{name}' is not unlocked on this save (pass unlock=true)")
        newly = [] if self.unlocked[name] else [name]
        self.unlocked[name] = True
        self.switch(name)
        return {"crest": name, "unlocked": newly, "config": self.config_of(name) or "Default"}


def connection_reset():
    return ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")


class FakeLink:
    """breaks_at(name, args): from the first RPC it matches on, every RPC raises error(): by default what
    OracleLink._send's sendall does on a dead socket; error=TimeoutError is a hung oracle (OracleLink.rpc's
    Future.result raises a TimeoutError without text)."""

    def __init__(self, game, breaks_at=None, error=connection_reset):
        self.game = game
        self.hello = {"game": "1.0.30000", "plugin": "0.1.0", "rpcs": list(p17.NEEDED_RPCS)}
        self.frame = 100
        self.raw = []
        self.closed = False
        self.breaks_at, self.broken, self.error = breaks_at, False, error

    def subscribe_raw(self, fn):
        self.raw.append(fn)

    def feed(self, events):
        s = {"f": self.frame, "ev": [{"k": k, "f": self.frame, "q": 0, "d": d} for k, d in events]}
        for fn in self.raw:
            fn(MsgType.STATE, encode(MsgType.STATE, 1, msgpack.packb(s)))

    def wait_state(self, pred=lambda s: True, timeout_s=10.0, newer_than=None):
        if newer_than is not None:
            self.frame = max(self.frame, newer_than + 1)
        s = {"f": self.frame, "game": {"gs": 4, "scene": "Bone_01"}, "hero": {"hero_accepting_input": True},
             "pause": {"bench": False, "inv": False}}
        assert pred(s)
        return s

    def rpc(self, name, /, timeout_s=10.0, **args):
        self.broken = self.broken or (self.breaks_at is not None and self.breaks_at(name, args))
        if self.broken:
            raise self.error()
        if name == "crest.equip" and args.get("name") == "Hunter_v2":
            self.feed([("hunter_meter", {"reason": "equips_changed", "from": 4, "to": 0, "crest": "Hunter"})])
        return self.game.rpc(name, args)

    def close(self):
        self.closed = True


def guard_sets(game):
    return [a["save_suppression"] for n, a in game.calls if n == "guards.set"]


def open_inventory(link):
    """The inventory is open in every STATE: run() refuses before it changes anything."""
    wait_state = link.wait_state

    def inventory_open(pred=lambda s: True, timeout_s=10.0, newer_than=None):
        s = wait_state(pred, timeout_s, newer_than)
        s["pause"]["inv"] = True
        return s

    link.wait_state = inventory_open


def lose_reply(link, rpc_name, applied):
    """rpc_name gets no reply: OracleLink.rpc raises a TimeoutError without text. applied: the oracle ran it anyway."""
    rpc = link.rpc

    def lost(name, /, timeout_s=10.0, **args):
        if name != rpc_name:
            return rpc(name, timeout_s=timeout_s, **args)
        if applied:
            rpc(name, timeout_s=timeout_s, **args)
        raise TimeoutError()

    link.rpc = lost


def test_run_dumps_each_crest_and_restores():
    game = FakeGame()
    result, failures = p17.run(FakeLink(game), ["Wanderer", "Reaper", "Hunter_v2", "Nope"], unlock=True, log=lambda *_: None)
    assert failures == []
    per = result["crests"]
    assert list(per) == ["Hunter", "Wanderer", "Reaper", "Hunter_v2", "Nope"]
    assert per["Nope"]["error"] == "ArgumentException: no crest 'Nope'" and per["Nope"]["slash"] is None
    assert per["Wanderer"]["equip"]["unlocked"] == ["Wanderer"] and per["Wanderer"]["current"]["config"] == "Wanderer"
    assert result["all_groups"] and "groups" not in per["Hunter"]["slash"]
    assert result["after"] == {"crest": "Hunter", "previous": "Wanderer", "temp": False, "silk": 12, "silk_max": 12,
                               "unlocked": ["Hunter"]}
    assert game.slots["Hunter"][1]["tool"] == "Compass" and game.amounts["Straight Pin"] == 10
    assert result["save_suppression_kept"] is False and game.save_suppression is False
    assert guard_sets(game) == [True, False]
    # Save suppression goes on before the first crest.equip and off after the restore.
    names = [n for n, _ in game.calls]
    assert names.index("guards.set") < names.index("crest.equip")
    assert len(names) - 1 - names[::-1].index("guards.set") > len(names) - 1 - names[::-1].index("crest.equip")
    table = result["table"]
    assert [r["crest"] for r in table["configs"]] == ["Hunter", "Hunter_v2", "Wanderer", "Reaper"]
    assert {r["crest"] for r in table["attacks"]} == {"Hunter", "Wanderer", "Reaper", "Hunter_v2"}
    wand = next(r for r in table["attacks"] if r["crest"] == "Wanderer" and r["slot"] == "normal")
    assert wand["fwd"] == pytest.approx(2.9)
    assert [e["reason"] for e in result["events"] if e["k"] == "hunter_meter"] == ["equips_changed"]


def test_run_without_unlock_restores_an_unchanged_snapshot():
    game = FakeGame()
    game.save_suppression = True           # already on: the probe must leave it on
    result, failures = p17.run(FakeLink(game), ["Wanderer"], unlock=False, log=lambda *_: None)
    assert result["crests"]["Wanderer"]["error"].startswith("InvalidOperationException: crest 'Wanderer' is not unlocked")
    # The oracle took its snapshot before refusing, so the restore succeeds and changes nothing.
    assert result["restore"]["restored"] is True and result["save_suppression_kept"] is False
    assert failures == ["no crest besides the equipped one could be dumped"]
    assert game.save_suppression is True and guard_sets(game) == []


def test_run_with_only_unknown_crests_has_nothing_to_restore():
    game = FakeGame()
    result, failures = p17.run(FakeLink(game), ["Nope"], unlock=True, log=lambda *_: None)
    assert "nothing to restore" in result["restore"]["error"]
    assert failures == ["no crest besides the equipped one could be dumped"]
    assert result["save_suppression_kept"] is False and guard_sets(game) == [True, False]


def test_run_reports_a_restore_that_did_not_relock_and_keeps_saves_off():
    game = FakeGame(relock=False)
    result, failures = p17.run(FakeLink(game), ["Reaper"], unlock=True, log=lambda *_: None)
    assert failures == ["restore: unlocked crests ['Hunter', 'Reaper'], were ['Hunter']"]
    assert result["save_suppression_kept"] is True
    assert game.save_suppression is True and guard_sets(game) == [True]


def test_run_checks_the_side_effects_of_the_switches():
    game = FakeGame(restore_extras=False)
    result, failures = p17.run(FakeLink(game), ["Reaper"], unlock=True, log=lambda *_: None)
    assert failures == [
        "restore: silk is 9, was 12",
        "restore: saved slots of Hunter are [{'tool': 'Straight Pin', 'unlocked': True}, {'tool': None, 'unlocked': True}], "
        "were [{'tool': 'Straight Pin', 'unlocked': True}, {'tool': 'Compass', 'unlocked': True}]",
        "restore: tool amounts {'Straight Pin': '7 (was 10)'}",
    ]
    assert result["save_suppression_kept"] is True and game.save_suppression is True


def test_run_keeps_saves_off_when_the_restore_is_refused_or_unverified():
    game = FakeGame(refuse_restore=True)
    result, failures = p17.run(FakeLink(game), ["Reaper"], unlock=True, log=lambda *_: None)
    assert failures[0] == "crest.equip restore failed: InvalidOperationException: close the inventory first"
    assert "restore: crest is Reaper, was Hunter" in failures
    assert result["save_suppression_kept"] is True and guard_sets(game) == [True]

    game = FakeGame(dump_fails_after_restore=True)
    result, failures = p17.run(FakeLink(game), ["Reaper"], unlock=True, log=lambda *_: None)
    assert result["restore"]["restored"] is True
    assert failures == ["restore not verified: crest.dump failed: no reply to crest.dump"]
    assert result["save_suppression_kept"] is True and game.save_suppression is True and "after" not in result


def test_main_says_save_suppression_stays_on(monkeypatch, tmp_path, capsys):
    game = FakeGame(refuse_restore=True)
    link = FakeLink(game)
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    out = tmp_path / "crests.json"
    assert p17.main(["--crests", "Reaper", "--out", str(out)]) == 1
    text = capsys.readouterr().out
    assert p17.SAVE_KEPT.format(instance=0) in text and "[PASS]" not in text
    assert link.closed and out.exists() and game.save_suppression is True
    # The failures and the guidance come before the write.
    assert text.index("[FAIL] crest.equip restore failed") < text.index(p17.SAVE_KEPT.format(instance=0))
    assert text.index(p17.SAVE_KEPT.format(instance=0)) < text.index(f"wrote {out}")


def test_main_prints_save_kept_when_the_output_cannot_be_written(monkeypatch, tmp_path, capsys):
    game = FakeGame(refuse_restore=True)
    link = FakeLink(game)
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    # --out is a directory: the write fails, after the failures and SAVE_KEPT, and without a traceback.
    assert p17.main(["--instance", "1", "--crests", "Reaper", "--out", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "[FAIL] crest.equip restore failed: InvalidOperationException: close the inventory first" in captured.out
    assert p17.SAVE_KEPT.format(instance=1) in captured.out and "wrote" not in captured.out
    assert f"[FAIL] could not write {tmp_path}: " in captured.err
    assert link.closed and game.save_suppression is True

    # No --out and no repo root: the same failures and guidance, then "pass --out".
    game = FakeGame(refuse_restore=True)
    link = FakeLink(game)
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    monkeypatch.setattr(p17, "find_repo_root", lambda: None)
    assert p17.main(["--crests", "Reaper"]) == 2
    captured = capsys.readouterr()
    assert "[FAIL] restore: crest is Reaper, was Hunter" in captured.out
    assert p17.SAVE_KEPT.format(instance=0) in captured.out and "wrote" not in captured.out
    assert "repo root not found; pass --out" in captured.err
    assert link.closed and game.save_suppression is True


def test_run_accepts_silk_that_idle_regen_added():
    game = FakeGame(regen=True)
    game.silk = 2                          # below the Silk Heart regen cap: a tick lands while Reaper is equipped
    result, failures = p17.run(FakeLink(game), ["Reaper"], unlock=True, log=lambda *_: None)
    assert result["crest_dump"]["current"]["silk"] == 2 and result["after"]["silk"] == 3
    assert failures == [] and result["save_suppression_kept"] is False
    assert game.save_suppression is False and guard_sets(game) == [True, False]


def test_save_kept_says_how_to_turn_save_suppression_off_again():
    text = p17.SAVE_KEPT.format(instance=2)
    assert "Save & Quit" in text and "start it again" in text
    # SaveSuppression outlives Save & Quit and a reload (Profile.ApplyDefaults runs at game start only).
    assert r"..\scripts\uv.cmd run python -m ssbot.probes.p17_crests --instance 2 --save-suppression-off" in text


def test_main_save_suppression_off(monkeypatch, capsys):
    game = FakeGame()
    game.save_suppression = True
    link = FakeLink(game)
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    assert p17.main(["--instance", "2", "--save-suppression-off"]) == 0
    assert "SaveSuppression is off" in capsys.readouterr().out
    assert game.save_suppression is False and [n for n, _ in game.calls] == ["guards.set"] and link.closed

    link = FakeLink(FakeGame(), breaks_at=lambda name, args: True)
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    assert p17.main(["--save-suppression-off"]) == 1
    err = capsys.readouterr().err
    assert "[FAIL] ConnectionResetError" in err and "--save-suppression-off" not in err


def test_run_survives_a_broken_link_and_keeps_saves_off():
    game = FakeGame()
    link = FakeLink(game, breaks_at=lambda name, args: name == "crest.equip" and args.get("name") == "Reaper")
    result, failures = p17.run(link, ["Wanderer", "Reaper", "Hunter_v2"], unlock=True, log=lambda *_: None)
    assert result["crests"]["Wanderer"]["slash"] is not None
    assert result["crests"]["Reaper"]["error"].startswith("ConnectionResetError: ")
    assert "Hunter_v2" not in result["crests"]            # the loop stops: every further RPC would fail too
    assert [f.split(": ")[0] for f in failures] == ["crest.equip restore failed", "restore not verified"]
    assert "ConnectionResetError" in failures[0] and "ConnectionResetError" in failures[1]
    assert result["save_suppression_kept"] is True and game.save_suppression is True and guard_sets(game) == [True]


def test_run_keeps_saves_off_when_turning_them_back_on_fails():
    game = FakeGame()
    link = FakeLink(game, breaks_at=lambda name, args: name == "guards.set" and args["save_suppression"] is False)
    result, failures = p17.run(link, ["Reaper"], unlock=True, log=lambda *_: None)
    assert result["after"]["crest"] == "Hunter"           # the restore itself was verified
    assert len(failures) == 1
    assert failures[0].startswith("SaveSuppression not turned off: guards.set failed: ConnectionResetError")
    assert result["save_suppression_kept"] is True and game.save_suppression is True


def test_main_prints_save_kept_on_a_broken_link(monkeypatch, tmp_path, capsys):
    game = FakeGame()
    link = FakeLink(game, breaks_at=lambda name, args: name == "slash.dump" and not args.get("all_groups"))
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    assert p17.main(["--instance", "3", "--crests", "Reaper", "--out", str(tmp_path / "crests.json")]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] crest.equip restore failed: ConnectionResetError" in out
    assert p17.SAVE_KEPT.format(instance=3) in out and "[PASS]" not in out
    assert link.closed and game.save_suppression is True

    # Broken before run() reaches its first crest.equip (here at guards.set): no traceback, and since the game cannot
    # be asked any more, the guidance is printed.
    game = FakeGame()
    link = FakeLink(game, breaks_at=lambda name, args: name == "guards.set")
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    out_path = tmp_path / "early.json"
    assert p17.main(["--crests", "Reaper", "--out", str(out_path)]) == 1
    err = capsys.readouterr().err
    assert "[FAIL] ConnectionResetError: " in err and p17.SAVE_KEPT.format(instance=0) in err
    assert link.closed and not out_path.exists()


def test_main_no_save_kept_when_run_changed_nothing(monkeypatch, tmp_path, capsys):
    """A failure before run() sends guards.set or crest.equip leaves the save as it was: no SAVE_KEPT, whatever
    SaveSuppression is."""
    for save_suppression in (False, True):    # True: the user had it on before the probe
        game = FakeGame()
        game.save_suppression = save_suppression
        link = FakeLink(game)
        open_inventory(link)
        monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
        assert p17.main(["--crests", "Reaper", "--out", str(tmp_path / "crests.json")]) == 1
        err = capsys.readouterr().err
        assert "[FAIL] the inventory is open" in err and "SaveSuppression" not in err
        assert game.save_suppression is save_suppression and game.calls == []

    # The link closed right after HELLO: wait_state gives up at once, and the game cannot be asked any more.
    game = FakeGame()
    link = FakeLink(game, breaks_at=lambda name, args: True)

    def closed(pred=lambda s: True, timeout_s=10.0, newer_than=None):
        raise TimeoutError(f"state condition not met within {timeout_s}s (last frame -1)")

    link.wait_state = closed
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    assert p17.main(["--crests", "Reaper", "--out", str(tmp_path / "crests.json")]) == 1
    assert capsys.readouterr().err == "[FAIL] state condition not met within 30.0s (last frame -1)\n"
    assert link.closed and not (tmp_path / "crests.json").exists()

    # A hung oracle before the first change: the timeout is named, and nothing more is said.
    game = FakeGame()
    link = FakeLink(game, breaks_at=lambda name, args: name == "gameplay.dump", error=TimeoutError)
    monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
    assert p17.main(["--crests", "Reaper", "--out", str(tmp_path / "crests.json")]) == 1
    assert capsys.readouterr().err == "[FAIL] TimeoutError\n"


def test_main_asks_the_game_after_a_lost_guards_set_reply(monkeypatch, tmp_path, capsys):
    """guards.set save_suppression=true got no reply: SAVE_KEPT only when the game says SaveSuppression is on."""
    for applied in (True, False):
        game = FakeGame()
        link = FakeLink(game)
        lose_reply(link, "guards.set", applied)
        monkeypatch.setattr(p17, "OracleLink", lambda instance: link)
        assert p17.main(["--crests", "Reaper", "--out", str(tmp_path / "crests.json")]) == 1
        err = capsys.readouterr().err
        assert err.startswith("[FAIL] TimeoutError\n")
        assert (p17.SAVE_KEPT.format(instance=0) in err) is applied
        assert game.save_suppression is applied and [n for n, _ in game.calls][-1] == "guards.get"
        assert "crest.equip" not in [n for n, _ in game.calls]


def test_run_progress_is_set_before_the_first_change():
    progress = p17.Progress()
    link = FakeLink(FakeGame())
    open_inventory(link)
    with pytest.raises(RuntimeError, match="the inventory is open"):
        p17.run(link, ["Reaper"], unlock=True, log=lambda *_: None, progress=progress)
    assert progress.changed is False

    # The guards.set that turns SaveSuppression on counts even when it fails.
    progress = p17.Progress()
    link = FakeLink(FakeGame(), breaks_at=lambda name, args: name == "guards.set")
    with pytest.raises(ConnectionResetError):
        p17.run(link, ["Reaper"], unlock=True, log=lambda *_: None, progress=progress)
    assert progress.changed is True

    # SaveSuppression on already: no guards.set, so the first crest.equip is the first change.
    game = FakeGame()
    game.save_suppression = True
    progress = p17.Progress()
    link = FakeLink(game, breaks_at=lambda name, args: name == "crest.equip")
    result, failures = p17.run(link, ["Reaper"], unlock=True, log=lambda *_: None, progress=progress)
    assert progress.changed is True and result["save_suppression_kept"] is True and guard_sets(game) == []


def test_err_text_names_the_type_when_the_text_is_empty():
    with pytest.raises(TimeoutError) as info:
        Future().result(timeout=0)            # what OracleLink.rpc raises when no reply comes
    assert p17.err_text(info.value) == "TimeoutError"
    assert p17.err_text(ConnectionError()) == "ConnectionError"
    assert p17.err_text(OracleError("")) == "OracleError"
    assert p17.err_text(TimeoutError("no reply to crest.dump")) == "no reply to crest.dump"
    assert p17.err_text(OracleError("ArgumentException: no crest 'Nope'")) == "ArgumentException: no crest 'Nope'"
    assert p17.err_text(ConnectionResetError(10054, "reset")) == "ConnectionResetError: [Errno 10054] reset"


def test_run_names_timeouts_of_a_hung_oracle():
    game = FakeGame()
    link = FakeLink(game, breaks_at=lambda name, args: name == "crest.equip", error=TimeoutError)
    result, failures = p17.run(link, ["Wanderer", "Reaper"], unlock=True, log=lambda *_: None)
    # A timeout is no broken link: every crest is tried.
    assert [result["crests"][n]["error"] for n in ("Wanderer", "Reaper")] == ["TimeoutError", "TimeoutError"]
    assert failures == ["crest.equip restore failed: TimeoutError",
                        "restore not verified: crest.dump failed: TimeoutError",
                        "no crest besides the equipped one could be dumped"]
    assert result["restore"] == {"error": "TimeoutError"} and result["save_suppression_kept"] is True


def test_main_without_a_link(monkeypatch, capsys):
    def refused(instance):
        raise ConnectionRefusedError(10061, "the target machine actively refused it")

    monkeypatch.setattr(p17, "OracleLink", refused)
    assert p17.main(["--instance", "1"]) == 2
    assert "[FAIL] no link to the oracle of instance 1: ConnectionRefusedError" in capsys.readouterr().err
