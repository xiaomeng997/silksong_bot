"""P17 probe: runtime crest and attack dumps (DESIGN §5 P17; the checklist is docs/research/crests.md §5, of which this
covers a, b, c and i, plus the hunter_meter events of f that happen during the run).

Preconditions: the training copy runs an SsOracle built with the Crest module (its HELLO lists crest.dump, slash.dump,
gameplay.dump and crest.equip), profile TRAIN, a SANDBOX save is loaded and Hornet stands idle somewhere quiet with the
inventory closed (on a bench is fine). An early save is the point: crests the save has not unlocked are unlocked for the
run (--no-unlock skips them instead) and relocked at the end. No key is pressed and no focus is needed.

Steps:
  1. gameplay.dump, crest.dump, and slash.dump {all_groups} with the crest the save has equipped.
  2. SaveSuppression on (guards.set) until the end, so no crest change can reach the save file even if the game saves.
  3. For every crest of --crests (default Wanderer, Reaper, Hunter_v2) other than the equipped one: crest.equip
     {name, unlock}, a few frames, crest.dump (its "current") and slash.dump. A refusal is recorded and the run goes on.
  4. crest.equip {restore}: the original crest, PreviousCrestID and temp flag back, what step 3 unlocked relocked;
     crest.dump must then show the original crest and the unlocked set of step 1. SaveSuppression back as it was.
  5. Writes --out (default docs/facts/<game>/crests.json) and prints the tables below. Exit code 1 when the restore
     check fails or no crest besides the equipped one could be dumped.

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.p17_crests [--instance 0] [--crests Wanderer,Reaper,Hunter_v2]
        [--no-unlock] [--out ../docs/facts/1.0.30000/crests.json]

Config table (every crest the game knows, from the serialized HeroControllerConfig fields, so Warrior shows its non-rage
values): swing = max(attackCooldownTime, attackDuration) (HeroController.DidAttack sets the cooldown so), quick = the same
with quickAttackCooldownTime (Quickening), rec = attackRecoveryTime, down = downSlashType, down_rec =
downspikeRecoveryTime (air recovery after FinishDownspike: a downspike, or a down-slash bounce), spike = downspike antic /
time / recovery (DownSpike type only), rule = how HeroController.UpdateConfig maps the crest to a config group
(crest.dump config_group.rule).

Attack table (each dumped crest, one row per attack slot of slash.dump): the damager SetConfigGroup paired with the slot
(else the attack object's own, else the first using nail damage). dmg = nailDamageMultiplier ("x") or a flat
damageDealt ("="), times damageMultiplier, then damage_mult_per_hit when set; silk = silkGeneration; spk =
NailAttackBase.canHitSpikes (false: a clash hurts Hornet for 1, DamageHero.cs:399); par = the swing clashes with enemy
attacks (not doesNotParry, DamageHero.cs:384); crit = Wanderer crits can apply (DamageEnemies.cs:1022: attackType Nail
and not doesNotCriticalHit, on the first hit, or the object is tagged "Nail Attack"); multi = multi-hitter steps / hits;
dsa = HeroDownAttack present (the downspike bounce and its i-frames); fwd/up/dn/back = extents of that damager's
colliders from the hero's pivot in world units, forward = the facing direction, using the swing-time outline when
NailAttackBase rescales the attack at swing start (without Long Needle); clash = forward extent of the attack's
"Clash Tink" collider (what has to touch an enemy attack for a clash).
"""
import argparse
import datetime as dt
import json
import sys
import threading
from collections.abc import Iterable, Sequence
from pathlib import Path

import msgpack

from ssbot.ipc.framing import HEADER, MsgType
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.probes.common import in_gameplay
from ssbot.record.recorder import find_repo_root

NEEDED_RPCS = ("crest.dump", "slash.dump", "gameplay.dump", "crest.equip", "guards.get", "guards.set")
DEFAULT_CRESTS = ("Wanderer", "Reaper", "Hunter_v2")
SETTLE_FRAMES = 3
EVENT_KINDS = ("hunter_meter", "guards", "save")
ERRORS = (OracleError, TimeoutError)


# ---- pure helpers (unit-tested in tests/test_p17_crests.py) ------------------------------------------------------

def crest_order(current: str | None, requested: Iterable[str]) -> list[str]:
    """The equipped crest first, then the requested ones in order, without repeats."""
    out = [current] if current else []
    for name in requested:
        if name and name not in out:
            out.append(name)
    return out


def extents(shapes: Iterable[dict], hero_pos: Sequence[float], facing: int) -> dict | None:
    """{fwd, back, up, dn}: how far the shapes reach from the hero's pivot, forward = the facing direction (+1 right).
    Negative means the shapes do not reach that side of the pivot. A vertex with a radius (circle centre, rounded box
    or edge) counts as a disc."""
    hx, hy = hero_pos[0], hero_pos[1]
    fwd = back = up = dn = None
    for s in shapes:
        v = s.get("v") or ()
        r = float(s.get("r") or 0.0)
        for i in range(0, len(v) - 1, 2):
            x = (v[i] - hx) * facing
            y = v[i + 1] - hy
            fwd = x + r if fwd is None else max(fwd, x + r)
            back = -x + r if back is None else max(back, -x + r)
            up = y + r if up is None else max(up, y + r)
            dn = -y + r if dn is None else max(dn, -y + r)
    if fwd is None:
        return None
    return {"fwd": fwd, "back": back, "up": up, "dn": dn}


def collider_shapes(colliders: Iterable[dict] | None) -> list[dict]:
    """The outlines of slash.dump colliders, the swing-time one where the oracle sent it."""
    shapes: list[dict] = []
    for c in colliders or ():
        shapes.extend(c.get("shapes_swing") or c.get("shapes") or ())
    return shapes


def damager_shapes(damager: dict | None) -> list[dict]:
    """Every collider outline of one damager."""
    return collider_shapes((damager or {}).get("colliders"))


def primary_damager(attack: dict) -> dict | None:
    """The damager SetConfigGroup paired with the slot, else the one on the attack object, else the first using nail
    damage, else the first."""
    ds = attack.get("damagers") or []
    for key in ("damager", "path"):
        want = attack.get(key)
        if want:
            for d in ds:
                if d.get("path") == want:
                    return d
    for d in ds:
        if d.get("use_nail_damage"):
            return d
    return ds[0] if ds else None


def primary_nail(attack: dict) -> dict | None:
    """The NailAttackBase on the attack object itself, else the first below it."""
    ns = attack.get("nail") or []
    for n in ns:
        if n.get("path") == attack.get("path"):
            return n
    return ns[0] if ns else None


def damage_text(d: dict | None) -> str:
    if d is None:
        return "-"
    text = f"x{d.get('nail_damage_mult', 0):g}" if d.get("use_nail_damage") else f"={d.get('damage_dealt', 0)}"
    mult = d.get("damage_mult")
    if mult is not None and abs(mult - 1.0) > 1e-6:
        text += f"*{mult:g}"
    per_hit = d.get("damage_mult_per_hit")
    if per_hit:
        text += "[" + ",".join(f"{m:g}" for m in per_hit) + "]"
    return text


def config_of(crest: dict, crest_dump: dict) -> str | None:
    """The HeroControllerConfig a crest runs with: its own, or the group UpdateConfig falls back to (configs[0])."""
    if crest.get("config"):
        return crest["config"]
    index = (crest.get("config_group") or {}).get("index")
    for g in crest_dump.get("groups") or ():
        if g.get("kind") == "configs" and g.get("index") == index:
            return g.get("config")
    return None


def _max(*xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def config_row(crest: dict, crest_dump: dict) -> dict:
    name = config_of(crest, crest_dump)
    f = ((crest_dump.get("configs") or {}).get(name) or {}).get("fields") or {}
    dur = f.get("attackDuration")
    down = f.get("downSlashType")
    spike = None
    if down == "DownSpike":
        spike = [f.get("downspikeAnticTime"), f.get("downspikeTime"), f.get("downspikeRecoveryTime")]
    return {
        "crest": crest["name"],
        "unlocked": crest.get("unlocked"),
        "config": name,
        "rule": (crest.get("config_group") or {}).get("rule"),
        "swing": _max(f.get("attackCooldownTime"), dur),
        "quick": _max(f.get("quickAttackCooldownTime"), dur),
        "duration": dur,
        "cooldown": f.get("attackCooldownTime"),
        "recovery": f.get("attackRecoveryTime"),
        "down": down,
        "down_recovery": f.get("downspikeRecoveryTime"),
        "spike": spike,
        "dash_stab": f.get("dashStabTime"),
    }


def attack_rows(crest: str, slash: dict) -> list[dict]:
    hero = slash.get("hero") or {}
    pos, facing = hero.get("pos") or (0.0, 0.0), hero.get("facing") or 1
    rows = []
    for a in slash.get("attacks") or ():
        d = primary_damager(a)
        n = primary_nail(a)
        ext = extents(damager_shapes(d), pos, facing) or {}
        clash = extents(collider_shapes((n or {}).get("clash_tink")), pos, facing)
        multi = None
        if d is not None and d.get("multi_hitter"):
            multi = f"{d.get('steps_per_hit')}/{d.get('hits_until_death')}"
        crit = None
        if d is not None and d.get("does_not_critical_hit") is not None:
            crit = bool(d.get("nail_tag")) or (d.get("attack_type") == "Nail" and not d["does_not_critical_hit"])
        rows.append({
            "crest": crest,
            "slot": a.get("slot"),
            "source": a.get("source"),
            "object": a.get("go"),
            "active": a.get("active"),
            "dmg": damage_text(d),
            "silk": d.get("silk_generation") if d else None,
            "spikes": n.get("can_hit_spikes") if n else None,
            "parry": None if d is None else not d.get("does_not_parry"),
            "crit": crit,
            "multi": multi,
            "dsa": bool(a.get("down_attacks")),
            "fwd": ext.get("fwd"),
            "up": ext.get("up"),
            "dn": ext.get("dn"),
            "back": ext.get("back"),
            "clash": clash.get("fwd") if clash else None,
            "clash_extents": clash,
        })
    return rows


def build_tables(result: dict) -> dict:
    crest_dump = result.get("crest_dump") or {}
    configs = [config_row(c, crest_dump) for c in crest_dump.get("crests") or ()]
    attacks = []
    for name, entry in (result.get("crests") or {}).items():
        if entry.get("slash"):
            attacks.extend(attack_rows(name, entry["slash"]))
    return {"configs": configs, "attacks": attacks}


def _cell(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "y" if v else "n"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:.0f}"
    if isinstance(v, (list, tuple)):
        return "/".join(_cell(x) for x in v)
    return str(v)


def format_table(rows: Sequence[dict], columns: Sequence[tuple[str, str]]) -> str:
    """Plain fixed-width table: columns = [(key, header)]."""
    cells = [[h for _, h in columns]] + [[_cell(r.get(k)) for k, _ in columns] for r in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(columns))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip() for row in cells]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


CONFIG_COLUMNS = (("crest", "crest"), ("unlocked", "unl"), ("config", "config"), ("rule", "rule"), ("swing", "swing"),
                  ("quick", "quick"), ("duration", "dur"), ("cooldown", "cd"), ("recovery", "rec"), ("down", "down"),
                  ("down_recovery", "down_rec"), ("spike", "spike a/t/r"), ("dash_stab", "dstab"))
ATTACK_COLUMNS = (("crest", "crest"), ("slot", "slot"), ("object", "object"), ("dmg", "dmg"), ("silk", "silk"),
                  ("spikes", "spk"), ("parry", "par"), ("crit", "crit"), ("multi", "multi"), ("dsa", "dsa"),
                  ("fwd", "fwd"), ("up", "up"), ("dn", "dn"), ("back", "back"), ("clash", "clash"))


def rounded(v, nd: int = 5):
    """Floats rounded for the JSON file (msgpack float32 values print as 0.30000001192092896 otherwise)."""
    if isinstance(v, float):
        return round(v, nd)
    if isinstance(v, dict):
        return {k: rounded(x, nd) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [rounded(x, nd) for x in v]
    if isinstance(v, bytes):
        return v.hex()
    return v


def unlocked_set(crest_dump: dict) -> list[str]:
    return sorted(c["name"] for c in crest_dump.get("crests") or () if c.get("unlocked"))


# ---- in-game run --------------------------------------------------------------------------------------------------

class EventTail:
    """Collects the STATE events of EVENT_KINDS on the link's reader thread (hunter_meter resets during crest switches,
    the SaveSuppression switch and any save the game attempts)."""

    def __init__(self, link) -> None:
        self._lock = threading.Lock()
        self.events: list[dict] = []
        link.subscribe_raw(self._on_raw)

    def _on_raw(self, msg_type: int, raw: bytes) -> None:
        if msg_type != MsgType.STATE:
            return
        s = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
        with self._lock:
            for e in s.get("ev") or ():
                if e.get("k") in EVENT_KINDS:
                    self.events.append({"k": e["k"], "f": e.get("f"), **(e.get("d") or {})})

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self.events)


def settle(link, frames: int = SETTLE_FRAMES) -> None:
    f = link.frame
    link.wait_state(lambda s: True, newer_than=f + frames, timeout_s=5.0)


def run(link, crests: Sequence[str], unlock: bool, log=print) -> tuple[dict, list[str]]:
    """Steps 1-4 of the module doc. Returns (result, failures)."""
    failures: list[str] = []
    tail = EventTail(link)
    s = link.wait_state(in_gameplay, timeout_s=30.0)
    if (s.get("pause") or {}).get("inv"):
        raise RuntimeError("the inventory is open: close it first")
    hello = link.hello or {}
    result: dict = {
        "probe": "P17",
        "game": hello.get("game"),
        "plugin": hello.get("plugin"),
        "captured": dt.datetime.now().isoformat(timespec="seconds"),
        "scene": (s.get("game") or {}).get("scene"),
        "unlock": unlock,
    }
    result["gameplay"] = link.rpc("gameplay.dump")
    cd0 = link.rpc("crest.dump")
    result["crest_dump"] = cd0
    original = cd0["current"]["crest"]
    unlocked0 = unlocked_set(cd0)
    log(f"equipped: {original}; unlocked: {', '.join(unlocked0)}")
    first = link.rpc("slash.dump", all_groups=True)
    result["all_groups"] = first.pop("groups", [])
    per: dict = {original: {"equip": None, "error": None, "current": cd0["current"], "slash": first}}
    result["crests"] = per

    ss0 = bool(link.rpc("guards.get").get("save_suppression"))
    if not ss0:
        link.rpc("guards.set", save_suppression=True)
    equipped_any = False
    try:
        for name in crest_order(original, crests)[1:]:
            entry: dict = {"equip": None, "error": None, "current": None, "slash": None}
            per[name] = entry
            try:
                entry["equip"] = link.rpc("crest.equip", name=name, unlock=unlock)
                equipped_any = True
                settle(link)
                entry["current"] = link.rpc("crest.dump")["current"]
                entry["slash"] = link.rpc("slash.dump")
                log(f"{name}: dumped (config {entry['current'].get('config')}, unlocked now {entry['equip'].get('unlocked')})")
            except ERRORS as e:
                entry["error"] = str(e)
                log(f"{name}: {e}")
    finally:
        try:
            result["restore"] = link.rpc("crest.equip", restore=True)
        except ERRORS as e:
            result["restore"] = {"error": str(e)}
            if equipped_any:
                failures.append(f"crest.equip restore failed: {e}")
        settle(link)
        cd1 = link.rpc("crest.dump")
        crest1, unlocked1 = cd1["current"]["crest"], unlocked_set(cd1)
        result["after"] = {"crest": crest1, "previous": cd1["current"].get("previous"), "unlocked": unlocked1}
        if crest1 != original:
            failures.append(f"restore: crest is {crest1}, was {original}")
        if unlocked1 != unlocked0:
            failures.append(f"restore: unlocked crests {unlocked1}, were {unlocked0}")
        if cd1["current"].get("previous") != cd0["current"].get("previous"):
            failures.append(f"restore: PreviousCrestID {cd1['current'].get('previous')}, was {cd0['current'].get('previous')}")
        if not ss0:
            link.rpc("guards.set", save_suppression=False)
    if not any(e.get("slash") for n, e in per.items() if n != original):
        failures.append("no crest besides the equipped one could be dumped")
    result["events"] = tail.snapshot()
    result["table"] = build_tables(result)
    return result, failures


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--crests", default=",".join(DEFAULT_CRESTS), help="comma-separated ToolCrest names")
    ap.add_argument("--no-unlock", action="store_true", help="skip crests the save has not unlocked")
    ap.add_argument("--out", type=Path, default=None, help="default: <repo>/docs/facts/<game>/crests.json")
    a = ap.parse_args(argv)

    link = OracleLink(instance=a.instance)
    try:
        missing = [r for r in NEEDED_RPCS if r not in (link.hello.get("rpcs") or ())]
        if missing:
            print(f"the oracle does not offer {missing}: deploy an SsOracle built with the Crest module", file=sys.stderr)
            return 2
        result, failures = run(link, [c.strip() for c in a.crests.split(",") if c.strip()], unlock=not a.no_unlock)
    except (RuntimeError, TimeoutError) as e:   # OracleError is a RuntimeError
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    finally:
        link.close()

    out = a.out
    if out is None:
        root = find_repo_root()
        if root is None:
            print("repo root not found; pass --out", file=sys.stderr)
            return 2
        out = root / "docs" / "facts" / (result.get("game") or "unknown") / "crests.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rounded(result), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")

    tables = result["table"]
    print("\n== configs ==")
    print(format_table(tables["configs"], CONFIG_COLUMNS))
    print("\n== attacks (extents in world units from the hero pivot; forward = facing) ==")
    print(format_table(tables["attacks"], ATTACK_COLUMNS))
    meter = [e for e in result["events"] if e["k"] == "hunter_meter"]
    if meter:
        print(f"\nhunter_meter events: {meter}")
    for f in failures:
        print(f"[FAIL] {f}")
    if not failures:
        print("[PASS] original crest, PreviousCrestID and unlocked set restored")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
