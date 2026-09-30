"""Offline checks of the P17 crest probe: the pure table/extent helpers and the equip/restore flow against a fake link
(the probe itself needs the running game)."""
import copy

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
    assert lines[0].split()[:3] == ["crest", "slot", "object"] and set(lines[1]) <= {"-", " "}
    assert "Wanderer" in lines[2] and "3" in lines[2] and len(lines) == 4


def test_crest_order_and_rounded():
    assert p17.crest_order("Hunter", ["Wanderer", "Hunter", "", "Wanderer", "Reaper"]) == ["Hunter", "Wanderer", "Reaper"]
    assert p17.crest_order(None, ["A"]) == ["A"]
    assert p17.rounded({"a": [0.30000001192092896, (1, 2.123456789)], "b": b"\x01"}) == {"a": [0.3, [1, 2.12346]], "b": "01"}


# ---- the equip / restore flow against a fake oracle ----------------------------------------------------------------

class FakeGame:
    """Just enough of crest.dump / slash.dump / crest.equip / guards.* to drive p17.run."""

    CONFIGS = {"Default": config("Default", 0.35, 0.41, 0.15, down="DownSpike"),
               "Wanderer": config("Wanderer", 0.25, 0.3, 0.1), "Reaper": config("Reaper", 0.3, 0.35, 0.12)}

    def __init__(self, relock=True):
        self.crest, self.previous = "Hunter", "Wanderer"
        self.unlocked = {"Hunter": True, "Hunter_v2": False, "Wanderer": False, "Reaper": False}
        self.snapshot = None
        self.save_suppression = False
        self.relock = relock
        self.calls = []

    def config_of(self, name):
        return {"Wanderer": "Wanderer", "Reaper": "Reaper"}.get(name)

    def crest_dump(self):
        crests = [crest_entry(n, u, self.config_of(n), {"Wanderer": 1, "Reaper": 2}.get(n, 0),
                              "match" if self.config_of(n) else "no_config:configs[0]") for n, u in self.unlocked.items()]
        return {"frame": 1, "crests": crests,
                "current": {"crest": self.crest, "previous": self.previous, "config": self.config_of(self.crest) or "Default"},
                "groups": [{"index": i, "kind": "configs", "config": c} for i, c in enumerate(("Default", "Wanderer", "Reaper"))],
                "configs": copy.deepcopy(self.CONFIGS), "extra_equips": {}}

    def rpc(self, name, args):
        self.calls.append((name, args))
        if name == "gameplay.dump":
            return {"asset": "Global Gameplay Settings", "hunter": {"combo_hits": 6}}
        if name == "crest.dump":
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
        raise OracleError(f"unknown rpc '{name}'")

    def equip(self, args):
        if args.get("restore"):
            if self.snapshot is None:
                raise OracleError("nothing to restore: crest.equip changed nothing on this PlayerData")
            crest, previous, unlocked = self.snapshot
            self.crest, self.previous = crest, previous
            if self.relock:
                self.unlocked = unlocked
            self.snapshot = None
            return {"restored": True, "crest": self.crest}
        name = args["name"]
        if name not in self.unlocked:
            raise OracleError(f"no crest '{name}'")
        if not self.unlocked[name] and not args.get("unlock"):
            raise OracleError(f"crest '{name}' is not unlocked on this save (pass unlock=true)")
        if self.snapshot is None:
            self.snapshot = (self.crest, self.previous, dict(self.unlocked))
        newly = [] if self.unlocked[name] else [name]
        self.unlocked[name] = True
        self.previous, self.crest = self.crest, name
        return {"crest": name, "unlocked": newly, "config": self.config_of(name) or "Default"}


class FakeLink:
    def __init__(self, game):
        self.game = game
        self.hello = {"game": "1.0.30000", "plugin": "0.1.0", "rpcs": list(p17.NEEDED_RPCS)}
        self.frame = 100
        self.raw = []

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
        if name == "crest.equip" and args.get("name") == "Hunter_v2":
            self.feed([("hunter_meter", {"reason": "equips_changed", "from": 4, "to": 0, "crest": "Hunter"})])
        return self.game.rpc(name, args)


def test_run_dumps_each_crest_and_restores():
    game = FakeGame()
    result, failures = p17.run(FakeLink(game), ["Wanderer", "Reaper", "Hunter_v2", "Nope"], unlock=True, log=lambda *_: None)
    assert failures == []
    per = result["crests"]
    assert list(per) == ["Hunter", "Wanderer", "Reaper", "Hunter_v2", "Nope"]
    assert per["Nope"]["error"] == "no crest 'Nope'" and per["Nope"]["slash"] is None
    assert per["Wanderer"]["equip"]["unlocked"] == ["Wanderer"] and per["Wanderer"]["current"]["config"] == "Wanderer"
    assert result["all_groups"] and "groups" not in per["Hunter"]["slash"]
    assert result["after"] == {"crest": "Hunter", "previous": "Wanderer", "unlocked": ["Hunter"]}
    assert game.save_suppression is False
    sets = [a["save_suppression"] for n, a in game.calls if n == "guards.set"]
    assert sets == [True, False]
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


def test_run_without_unlock_dumps_nothing_and_says_so():
    game = FakeGame()
    game.save_suppression = True           # already on: the probe must leave it on
    result, failures = p17.run(FakeLink(game), ["Wanderer"], unlock=False, log=lambda *_: None)
    assert "not unlocked" in result["crests"]["Wanderer"]["error"]
    assert "nothing to restore" in result["restore"]["error"]
    assert failures == ["no crest besides the equipped one could be dumped"]
    assert game.save_suppression is True and not [c for c in game.calls if c[0] == "guards.set"]


def test_run_reports_a_restore_that_did_not_relock():
    game = FakeGame(relock=False)
    _, failures = p17.run(FakeLink(game), ["Reaper"], unlock=True, log=lambda *_: None)
    assert failures == ["restore: unlocked crests ['Hunter', 'Reaper'], were ['Hunter']"]
