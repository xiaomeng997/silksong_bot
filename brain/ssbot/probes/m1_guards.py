"""M1 guards probe: LethalBlock (both nets), guard switches, SaveSuppression, AchievementGuard, SymbolCheck,
profiles and slot snapshots, exercised in the running training copy (DESIGN §3.1.1 Guards, "unit tests": scripted
spike, cog-like quick damage, grab-like special damage, lava, spike during i-frames; m0:C2, N1, §2.5).

Preconditions: the training copy runs SsOracle with the guards package wired in (Modules.InstallAll calls
Guards.GuardsModule.Install(host, harmony) first), profile TRAIN, a SANDBOX save is loaded and Hornet stands somewhere
quiet (no enemies, not a boss arena, not a memory scene). A Steel Soul save is fine and is the real test
(permadeathMode must stay On), but take a slot.snapshot first if the slot matters. The probe itself writes one real
save of the current slot at full health (SaveSuppression off check) and a snapshot named "m1probe".
Offline pre-check without the game: oracle/tools/symcheck (symbols, TakeHealth replay, patch signatures).

    cd brain
    uv run python -m ssbot.probes.m1_guards [--instance 0] [--skip-save] [--skip-snapshot] [--skip-profile]

Health is set through the debug line server ("pdset health N" on 127.0.0.1:47631+instance); damage goes through the
game's own entry points via the hurt.special RPC. Every check prints PASS / FAIL / SKIP; exit code 1 on any FAIL.

Fractured Mask semantics being asserted (1.0.30000, m0:C2): after blue health absorbs, a hit that would reach 0 HP is
survived at exactly 1 HP when the mask is equipped and AmountLeft > 0, whatever allowFracturedMaskBreak says; the flag
only decides whether the mask is consumed (AmountLeft -> 0). TakeDamage passes (flags & MidChain) == 0, so a MidChain
hit saves without consuming; TakeQuickDamage defaults to no break; chomp, frost, tags and HeroController.TakeHealth
break it. LethalBlock cancels a hit only when the replay reaches 0 HP ("catastrophe"); a hit the mask saves is left
alone. lethal.simulate tells the probe which branch the live state is in, so the expectations hold with or without
the mask equipped.
"""
import argparse
import os
import sys
import threading
import time
from pathlib import Path

import msgpack

from ssbot.io.sinks.oracle_inject import OracleClient
from ssbot.ipc.framing import HEADER, MsgType
from ssbot.ipc.oracle_link import OracleError, OracleLink

PLAYING = 4
DEBUG_PORT = 47631
OUR_RPCS = ("guards.get", "guards.set", "lethal.simulate", "hurt.special", "symbols.check", "profile.get", "profile.set",
            "slot.snapshot", "slot.restore", "slot.list", "save.trigger", "guards.test_achievement")


class Watch:
    """Collects every STATE's events and tracks the worst hero state seen, from the link's reader thread."""

    def __init__(self, link: OracleLink):
        self._lock = threading.Lock()
        self.events: list[tuple[int, str, dict]] = []
        self.dead_seen = False
        self.min_hp: int | None = None
        self.pdm_seen: set[int] = set()
        link.subscribe_raw(self._on_raw)

    def _on_raw(self, msg_type: int, raw: bytes) -> None:
        if msg_type != MsgType.STATE:
            return
        s = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
        g = s.get("guards") or {}
        with self._lock:
            for e in s.get("ev") or ():
                self.events.append((e["f"], e["k"], e.get("d") or {}))
            if g.get("dead"):
                self.dead_seen = True
            if g.get("hp") is not None:
                self.min_hp = g["hp"] if self.min_hp is None else min(self.min_hp, g["hp"])
            if g.get("pdm") is not None:
                self.pdm_seen.add(g["pdm"])

    def reset(self) -> int:
        with self._lock:
            self.dead_seen = False
            self.min_hp = None
            self.pdm_seen = set()
            return len(self.events)

    def since(self, mark: int, *kinds: str) -> list[tuple[int, str, dict]]:
        with self._lock:
            return [e for e in self.events[mark:] if not kinds or e[1] in kinds]

    def wait(self, mark: int, kind: str, timeout_s: float, pred=lambda d: True) -> dict | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for _, k, d in self.since(mark, kind):
                if pred(d):
                    return d
            time.sleep(0.02)
        return None


class Probe:
    def __init__(self, args):
        self.args = args
        self.link = OracleLink(instance=args.instance)
        self.dbg = OracleClient(port=DEBUG_PORT + args.instance)
        self.watch = Watch(self.link)
        self.results: list[tuple[str, str, str]] = []

    # ---- reporting ----------------------------------------------------------------------------------------

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        status = "PASS" if ok else "FAIL"
        self.results.append((status, name, detail))
        print(f"{status:4}  {name}{'  - ' + detail if detail else ''}", flush=True)
        return ok

    def skip(self, name: str, why: str) -> None:
        self.results.append(("SKIP", name, why))
        print(f"SKIP  {name}  - {why}", flush=True)

    # ---- game helpers -------------------------------------------------------------------------------------

    def g(self) -> dict:
        return self.link.state["guards"]

    def set_hp(self, hp: int, blue: int = 0) -> None:
        self.dbg._call(f"pdset healthBlue {blue}")
        self.dbg._call(f"pdset health {hp}")
        self.link.wait_state(lambda s: s["guards"]["hp"] == hp and s["guards"]["blue"] == blue, timeout_s=2)

    def settle(self, need_vulnerable: bool = True, timeout_s: float = 10.0) -> dict:
        """PLAYING, alive, accepting input, and (optionally) out of i-frames, then a few quiet frames."""
        s = self.link.wait_state(
            lambda s: s["game"]["gs"] == PLAYING and s["guards"]["dead"] is False and s["pause"]["hero_input"]
            and (not need_vulnerable or not s["guards"]["inv"]), timeout_s=timeout_s)
        time.sleep(0.25)
        return s

    def hurt(self, **args) -> dict:
        return self.link.rpc("hurt.special", **args)

    # ---- checks -------------------------------------------------------------------------------------------

    def run(self) -> int:
        self.check_handshake()
        self.check_symbols()
        self.check_defaults()
        s = self.link.wait_state(timeout_s=5)
        if not (s.get("game") and s["game"]["gs"] == PLAYING and s["guards"]["hp"] is not None):
            self.check("in game (PLAYING with a hero)", False, "load a sandbox save first; the damage tests need Hornet")
            return self.summary()
        self.pdm0 = s["guards"]["pdm"]
        self.hp_max = self.link.rpc("lethal.simulate", amount=0)["max"]
        print(f"      scene {s['game']['scene']}, permadeathMode {self.pdm0}, maxHealth {self.hp_max}, mask {s['guards']['mask']}")

        if s["game"]["cheat"] & 7:
            # HeroKeepHealth scenes, tools in Cutscene state or CheatManager invincibility skip TakeHealth entirely.
            self.skip("net 1 damage paths", f"cheat_flags {s['game']['cheat']}: damage never reaches TakeHealth here; "
                                            "move to a normal room and turn cheats off")
        else:
            self.lethal_cases()
        self.check_net2()
        self.check_zero_hp_watcher()
        self.check_critical()
        self.check_switches()
        if not self.args.skip_save:
            self.check_save_suppression()
        self.check_achievement_guard()
        if not self.args.skip_snapshot:
            self.check_snapshots()
        if not self.args.skip_profile:
            self.check_profiles()
        self.set_hp(self.hp_max)
        return self.summary()

    def check_handshake(self) -> None:
        rpcs = set(self.link.hello.get("rpcs", ()))
        missing = [r for r in OUR_RPCS if r not in rpcs]
        self.check("HELLO lists the guard RPCs", not missing, f"missing {missing}" if missing else "")

    def check_symbols(self) -> None:
        r = self.link.rpc("symbols.check", timeout_s=20)
        self.check("symbols.check ok", r["ok"] and not r["missing"],
                   f"{r['resolved_count']}/{r['total']} in {r['us']} us; missing {r['missing']}; soft missing {r['soft_missing']}")

    def check_defaults(self) -> None:
        g = self.link.rpc("guards.get")
        ok = (g["lethal_block"] == "block" and g["achievement_guard"] and not g["save_suppression"] and not g["refused"]
              and all(g["healthy"].values()) and g["profile"] == "TRAIN")
        self.check("guards.get TRAIN defaults (block / achievement on / suppression off / all healthy)", ok,
                   f"{ {k: g[k] for k in ('lethal_block', 'achievement_guard', 'save_suppression', 'healthy', 'refused', 'refusals', 'profile')} }")
        p = self.link.rpc("profile.get")
        self.check("profile.get TRAIN ok", p["name"] == "TRAIN" and p["ok"], f"violations {p['violations']}")
        st = self.link.wait_state(timeout_s=5)
        self.check("STATE has a 'guards' section", "guards" in st and st["guards"]["lb"] == 2 and st["guards"]["ok"],
                   f"{st.get('guards')}, cost {st['cost_ex'].get('guards')} us")

    # ---- LethalBlock net 1 ----------------------------------------------------------------------------------

    def lethal_case(self, name: str, hp: int, call: dict, sim_amount: int, allow_break: bool, cause: str,
                    hazard: str | None = None, prepare=None, expect_invuln: bool = False) -> None:
        try:
            self.settle()
            self.set_hp(hp)
            if prepare is not None and prepare() is False:
                return
            sim = self.link.rpc("lethal.simulate", amount=sim_amount, allow_mask_break=allow_break)
            mark = self.watch.reset()
            res = self.hurt(**call)
            if sim["reaches_zero"]:
                ev = self.watch.wait(mark, "catastrophe", 1.5, lambda d: d.get("cause") == cause)
                ok = ev is not None and ev["blocked"] and (hazard is None or ev.get("hazard") == hazard)
                detail = f"expected catastrophe cause={cause}; got {ev and {k: ev.get(k) for k in ('cause', 'path', 'hazard', 'hp', 'mask_eq', 'mask_left', 'blocked')}}"
            else:
                time.sleep(0.5)
                cats = self.watch.since(mark, "catastrophe")
                ok = not cats and res["hp_after"] == sim["hp_after"]
                detail = (f"mask saves (consumed={sim['mask_consumed']}): expected no catastrophe and hp {sim['hp_after']}; "
                          f"got hp {res['hp_after']}, catastrophes {len(cats)}")
            self.settle(need_vulnerable=False)
            time.sleep(0.3)
            wd = self.watch.since(mark, "would_die")
            g = self.g()
            alive = not self.watch.dead_seen and not wd and g["hp"] >= 1 and (self.watch.min_hp or 0) >= 1
            same_mode = g["pdm"] == self.pdm0 and self.watch.pdm_seen <= {self.pdm0}
            invuln_ok = res["invuln_before"] or not expect_invuln
            self.check(f"net 1: {name}", ok and alive and same_mode and invuln_ok,
                       f"{detail}; invulnerable at the hit {res['invuln_before']}; "
                       f"hp {res['hp_before']}->{res['hp_after']}, min hp seen {self.watch.min_hp}, dead seen "
                       f"{self.watch.dead_seen}, would_die {len(wd)}, permadeath {self.pdm0}->{g['pdm']}")
        except (OracleError, TimeoutError) as e:
            self.check(f"net 1: {name}", False, f"{type(e).__name__}: {e}")

    def lethal_cases(self) -> None:
        # Scripted spike: SPIKES is forced to 1 damage and ignores i-frames; after the blocked hit the hero still
        # hazard-respawns with unchanged health.
        self.lethal_case("scripted spike (TakeDamage SPIKES) at 1 HP", 1,
                         dict(kind="damage", hazard="SPIKES", amount=1), 1, True, "damage", "SPIKES")
        # Cog-like: CogMultiHitter lands TakeDamage(1, SPIKES) (m0:C3); cog/grab chains of quick damage use
        # TakeQuickDamage = DoSpecialDamage(canDie: false), which ignores i-frames and could leave 0 HP alive.
        self.lethal_case("cog-like quick damage (TakeQuickDamage) at 1 HP", 1,
                         dict(kind="quick", amount=1, allow_mask_break=False), 1, False, "quick")
        # Grab-like special damage: chomp = DoSpecialDamage(1, canDie, mask may break).
        self.lethal_case("grab-like special damage (TakeChompDamage) at 1 HP", 1, dict(kind="chomp"), 1, True, "chomp")
        # Lava: forced to 2 damage (1 with a ready Lava Bell); lethal at 1 HP either way.
        self.lethal_case("lava (TakeDamage LAVA, 2 damage) at 1 HP", 1,
                         dict(kind="damage", hazard="LAVA", amount=1), 2, True, "damage", "LAVA")
        self.lethal_case("frost (TakeFrostDamage) at 1 HP", 1, dict(kind="frost", amount=1), 1, True, "frost")
        self.lethal_case("FSM TakeHealth (HeroController.TakeHealth) at 1 HP", 1,
                         dict(kind="take_health", amount=1), 1, True, "hero_take_health")
        # MidChain: TakeDamage passes allowFracturedMaskBreak = False, so the mask saves without being consumed.
        self.lethal_case("MidChain enemy hit at 1 HP (mask saves, never consumed)", 1,
                         dict(kind="damage", hazard="ENEMY", amount=1, flags="MidChain"), 1, False, "damage", "ENEMY")
        self.lethal_case("blue health overflow (1 blue + 1 HP, 3 damage quick)", 1,
                         dict(kind="quick", amount=3), 3, False, "quick", prepare=lambda: self.set_hp(1, blue=1))

        # Spike during i-frames (m0:N1): an enemy hit takes 2 -> 1 HP and starts i-frames; SPIKES passes them.
        def enemy_first() -> bool:
            name = "net 1: spike during i-frames"
            r = self.hurt(kind="damage", hazard="ENEMY", amount=1)
            if r["hp_after"] != 1:
                self.skip(name, f"enemy hit did not land (hp {r['hp_before']}->{r['hp_after']}; Lucky Dice / Warding Bell / parry?)")
                return False
            try:
                self.link.wait_state(lambda s: s["guards"]["inv"], timeout_s=0.5)
            except TimeoutError:
                self.check(name, False, "hero not invulnerable after the enemy hit")
                return False
            return True

        self.lethal_case("spike during i-frames (ENEMY hit, then SPIKES while invulnerable)", 2,
                         dict(kind="damage", hazard="SPIKES", amount=1), 1, True, "damage", "SPIKES", prepare=enemy_first,
                         expect_invuln=True)

    # ---- LethalBlock net 2 and watchers ----------------------------------------------------------------------

    def check_net2(self) -> None:
        try:
            self.settle()
            self.set_hp(2)
            mark = self.watch.reset()
            res = self.hurt(kind="death_catch", set_health=0)
            ev = self.watch.wait(mark, "would_die", 1.5, lambda d: d.get("cause") == "death_catch")
            time.sleep(0.5)
            g = self.g()
            self.check("net 2: CheckDeathCatch at 0 HP -> Die blocked, would_die, HP restored",
                       ev is not None and ev["blocked"] and ev.get("net") == 2 and res["hp_after"] >= 1 and not res["dead"]
                       and not self.watch.dead_seen and g["pdm"] == self.pdm0,
                       f"event {ev and {k: ev.get(k) for k in ('cause', 'path', 'net', 'blocked', 'hp_restored')}}, "
                       f"hp_after {res['hp_after']}, dead {res['dead']}, permadeath {g['pdm']}")
        except (OracleError, TimeoutError) as e:
            self.check("net 2: CheckDeathCatch", False, f"{type(e).__name__}: {e}")

    def check_zero_hp_watcher(self) -> None:
        try:
            self.settle(need_vulnerable=False)
            mark = self.watch.reset()
            self.dbg._call("pdset health 0")  # an FSM SetPlayerDataInt could do this; death would only be postponed
            ev = self.watch.wait(mark, "catastrophe", 1.5, lambda d: d.get("cause") == "health_zero_observed")
            time.sleep(0.3)
            self.check("watcher: 0 HP while alive -> catastrophe, HP restored to 1",
                       ev is not None and self.g()["hp"] == 1 and not self.watch.dead_seen,
                       f"event {ev and ev.get('cause')}, hp {self.g()['hp']}, min hp in STATE {self.watch.min_hp}")
        except (OracleError, TimeoutError, RuntimeError) as e:
            self.check("watcher: 0 HP while alive", False, f"{type(e).__name__}: {e}")

    def check_critical(self) -> None:
        try:
            self.settle()
            self.set_hp(3, blue=1)
            mark = self.watch.reset()
            res = self.hurt(kind="critical")
            time.sleep(0.4)
            self.check("CriticalDamage at 3 HP + 1 blue -> 1 HP, blue 0, no catastrophe",
                       res["hp_after"] == 1 and res["blue_after"] == 0 and not self.watch.since(mark, "catastrophe", "would_die"),
                       f"hp {res['hp_before']}->{res['hp_after']}, blue {res['blue_before']}->{res['blue_after']}")
        except (OracleError, TimeoutError) as e:
            self.check("CriticalDamage", False, f"{type(e).__name__}: {e}")

    # ---- guard switches -------------------------------------------------------------------------------------

    def check_switches(self) -> None:
        try:
            g = self.link.rpc("guards.set", lethal_block=False)
            st = self.link.wait_state(lambda s: s["guards"]["lb"] == 0, timeout_s=2)
            self.settle()
            self.set_hp(3)
            mark = self.watch.reset()
            res = self.hurt(kind="quick", amount=1)
            time.sleep(0.4)
            quiet = not self.watch.since(mark, "catastrophe", "would_die")
            self.check("guards.set lethal_block=false -> off; non-lethal hit passes, no events",
                       g["lethal_block"] == "off" and st["guards"]["lb"] == 0 and res["hp_after"] == 2 and quiet,
                       f"hp {res['hp_before']}->{res['hp_after']}")
        except (OracleError, TimeoutError) as e:
            self.check("guards.set lethal_block=false", False, f"{type(e).__name__}: {e}")
        finally:
            g = self.link.rpc("guards.set", lethal_block="block")
        st = self.link.wait_state(lambda s: s["guards"]["lb"] == 2, timeout_s=2)
        self.check("guards.set lethal_block=block -> on again", g["lethal_block"] == "block" and st["guards"]["lb"] == 2)
        # Blocking works again after the toggle.
        self.lethal_case("after re-enable: quick damage at 1 HP", 1, dict(kind="quick", amount=1), 1, False, "quick")

        g = self.link.rpc("guards.set", save_suppression=True, achievement_guard=False)
        ok = g["save_suppression"] and not g["achievement_guard"]
        g = self.link.rpc("guards.set", save_suppression=False, achievement_guard=True)
        self.check("guards.set save_suppression / achievement_guard toggle (TRAIN allows both)",
                   ok and not g["save_suppression"] and g["achievement_guard"])
        try:
            self.link.rpc("guards.set", lethal_block="maybe")
            self.check("guards.set rejects a bad value", False)
        except OracleError as e:
            self.check("guards.set rejects a bad value", True, str(e))

    # ---- SaveSuppression ------------------------------------------------------------------------------------

    @staticmethod
    def slot_files(save_dir: Path, slot: int) -> dict[str, int]:
        """name -> mtime of every file the game keeps for the slot (primary, backups, versioned, restore points)."""
        primary = "user.dat" if slot == 0 else f"user{slot}.dat"
        files = [p for p in save_dir.glob(f"{primary}*")] + list(save_dir.glob(f"user{slot}_*.dat"))
        files += list((save_dir / f"Restore_Points{slot}").glob("*"))
        return {str(p.relative_to(save_dir)): p.stat().st_mtime_ns for p in files if p.is_file()}

    def check_save_suppression(self) -> None:
        try:
            # A real save happens at the end: write the save with full health, not a probe's 1 HP.
            self.settle(need_vulnerable=False)
            self.set_hp(self.hp_max)
            info = self.link.rpc("guards.get")["steel_soul"]
            save_dir, slot = Path(info["save_dir"]), info["slot"]
            if slot is None or slot < 0:
                self.skip("SaveSuppression", "current slot unknown (not PLAYING yet?)")
                return
            self.link.rpc("guards.set", save_suppression=True)
            t0 = self.link.wait_state(timeout_s=2)["game"]["t_saved"]
            time.sleep(1.0)
            for kind in ("save", "restore_point"):
                before = self.slot_files(save_dir, slot)
                mark = self.watch.reset()
                r = self.link.rpc("save.trigger", kind=kind, timeout_s=10)
                ev = self.watch.wait(mark, "save_suppressed", 1.0, lambda d: kind in d.get("kind", ""))
                time.sleep(0.5)
                after = self.slot_files(save_dir, slot)
                self.check(f"SaveSuppression on: {kind} reports success, writes nothing, emits save_suppressed",
                           r["ok"] and r["suppressed"] and ev is not None and before == after,
                           f"callback ok={r['ok']} after {r['frames']} frames, event {ev and ev.get('kind')}, "
                           f"files changed {sorted(set(after.items()) ^ set(before.items()))}")
            t1 = self.link.wait_state(timeout_s=2)["game"]["t_saved"]
            self.check("SaveSuppression still flushes the play timer into playerData.playTime (m0 §2.3)", t1 > t0,
                       f"t_saved {t0:.2f} -> {t1:.2f}")
            self.link.rpc("guards.set", save_suppression=False)
            path = save_dir / ("user.dat" if slot == 0 else f"user{slot}.dat")
            before = path.stat().st_mtime_ns if path.exists() else 0
            r = self.link.rpc("save.trigger", kind="save", timeout_s=15)
            after = path.stat().st_mtime_ns if path.exists() else 0
            self.check("SaveSuppression off: a real save writes the sandbox slot",
                       r["ok"] and not r["suppressed"] and after != before, f"{path}")
        except (OracleError, TimeoutError, OSError) as e:
            self.check("SaveSuppression", False, f"{type(e).__name__}: {e}")
        finally:
            self.link.rpc("guards.set", save_suppression=False)

    # ---- AchievementGuard ------------------------------------------------------------------------------------

    def check_achievement_guard(self) -> None:
        try:
            mark = self.watch.reset()
            r = self.link.rpc("guards.test_achievement", key="FIRST_TOOL")
            ev = self.watch.wait(mark, "achievement_blocked", 1.0, lambda d: d.get("key") == "FIRST_TOOL")
            passed = self.watch.since(mark, "achievement_passed")
            self.check("AchievementGuard blocks every entry point (Award/Push/Progress/MenuStyle)",
                       r["blocked"] == r["expected"] and ev is not None and not passed,
                       f"blocked {r['blocked']}/{r['expected']} via {r['calls']}, first event via {ev and ev.get('via')}")
        except (OracleError, TimeoutError) as e:
            self.check("AchievementGuard", False, f"{type(e).__name__}: {e}")

    # ---- snapshots ------------------------------------------------------------------------------------------

    def check_snapshots(self) -> None:
        try:
            slot = self.link.rpc("guards.get")["steel_soul"]["slot"]
            if slot is None or slot < 0:
                self.skip("slot.snapshot", "current slot unknown")
                return
            r = self.link.rpc("slot.snapshot", slot=slot, name="m1probe", timeout_s=30)
            primary = "user.dat" if slot == 0 else f"user{slot}.dat"
            on_disk = Path(r["dir"], primary).exists()
            self.check("slot.snapshot copies the slot inside the sandbox",
                       primary in r["entries"] and on_disk and r["dir"].lower().startswith("c:\\ssbot\\sandbox\\"),
                       f"{r['dir']}: {r['entries']}")
            lst = self.link.rpc("slot.list", slot=slot, timeout_s=10)
            self.check("slot.list shows it", any(x["name"] == "m1probe" for x in lst["snapshots"]))
            for bad, args in (("restore while in game", dict(slot=slot, name="m1probe")),
                              ("slot out of range", dict(slot=9)),
                              ("path-like name", dict(slot=slot, name="..\\..\\x"))):
                try:
                    self.link.rpc("slot.restore" if bad.startswith("restore") else "slot.snapshot", **args)
                    self.check(f"slot.* refuses {bad}", False)
                except OracleError as e:
                    self.check(f"slot.* refuses {bad}", True, str(e))
        except (OracleError, TimeoutError) as e:
            self.check("slot snapshots", False, f"{type(e).__name__}: {e}")

    # ---- profiles -------------------------------------------------------------------------------------------

    def check_profiles(self) -> None:
        try:
            p = self.link.rpc("profile.get")
            try:
                self.link.rpc("profile.set", name="REHEARSAL_FULL")
                full_ok = not p["debugmod_loaded"]
                self.link.rpc("profile.set", name="TRAIN")
            except OracleError as e:
                full_ok = p["debugmod_loaded"] and "savestates" in str(e)
            self.check("REHEARSAL_FULL refused while DebugMod (savestates) is loaded", full_ok,
                       f"debugmod_loaded={p['debugmod_loaded']}")
            try:
                q = self.link.rpc("profile.set", name="SHADOW")
                shadow = q["name"] == "SHADOW" and q["guards"]["lethal_block"] == "block"
                try:
                    self.hurt(kind="quick", amount=1)
                    tools_blocked = False
                except OracleError:
                    tools_blocked = True
                try:
                    self.link.rpc("guards.set", lethal_block="off")
                    fixed = False
                except OracleError:
                    fixed = True
                self.check("SHADOW: lethal block fixed on, probe tools refused", shadow and tools_blocked and fixed)
            except OracleError as e:
                self.check("SHADOW accepted (no cheats active)", False, str(e))
            finally:
                q = self.link.rpc("profile.set", name="TRAIN")
            self.check("back to TRAIN with its defaults", q["name"] == "TRAIN" and q["guards"]["lethal_block"] == "block")
        except (OracleError, TimeoutError) as e:
            self.check("profiles", False, f"{type(e).__name__}: {e}")

    def summary(self) -> int:
        fails = [r for r in self.results if r[0] == "FAIL"]
        g = self.link.rpc("guards.get")
        print(f"\n{len(self.results)} checks: {len(fails)} failed, {sum(r[0] == 'SKIP' for r in self.results)} skipped; "
              f"counts {g['counts']}")
        for _, name, detail in fails:
            print(f"  FAILED {name}: {detail}")
        self.dbg.close()
        self.link.close()
        return 1 if fails else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--instance", type=int, default=int(os.environ.get("SSBOT_INSTANCE", 0)))
    ap.add_argument("--skip-save", action="store_true", help="do not trigger saves (SaveSuppression checks)")
    ap.add_argument("--skip-snapshot", action="store_true", help="do not write a snapshot of the current slot")
    ap.add_argument("--skip-profile", action="store_true", help="do not switch profiles")
    sys.exit(Probe(ap.parse_args()).run())


if __name__ == "__main__":
    main()
