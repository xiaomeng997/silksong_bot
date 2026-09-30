"""M1 guards probe: LethalBlock (both nets), guard switches, SaveSuppression, AchievementGuard, SymbolCheck,
profiles and slot snapshots, exercised in the running training copy (DESIGN §3.1.1 Guards, "unit tests": scripted
spike, cog-like quick damage, grab-like special damage, lava, spike during i-frames; m0:C2, N1, §2.5).

Preconditions: the training copy runs SsOracle with the guards package wired in (Modules.InstallAll calls
Guards.GuardsModule.Install(host, harmony) first), profile TRAIN, a SANDBOX save is loaded and Hornet stands somewhere
quiet (no enemies, not a boss arena, not a memory scene). A Steel Soul save is fine and is the real test
(permadeathMode must stay On). For the Fractured Mask branches the save needs the Fractured Mask equipped with its
charge intact; without it those checks SKIP (FAIL with --require-mask) and only the blocking path is tested.

What the probe writes: first, before any damage, a snapshot of the current slot named "m1probe" (slot.snapshot;
--skip-snapshot turns it off); at the end one real save of the current slot at full health (SaveSuppression off
check; --skip-save turns it off). The real save is skipped, and reported as a FAIL, if anything earlier in the run
looked like a death (hero dead, an unblocked would_die, permadeath_dead, permadeathMode changed), so a guard failure
can never be written to disk by the probe itself.
Offline pre-check without the game: oracle/tools/symcheck (symbols, TakeHealth replay, patch signatures).

    cd brain
    uv run python -m ssbot.probes.m1_guards [--instance 0] [--skip-save] [--skip-snapshot] [--skip-profile] [--require-mask]

Health is set through the debug line server ("pdset health N" on 127.0.0.1:47631+instance); damage goes through the
game's own entry points via the hurt.special RPC. "No death" means, over the whole case: GameState stays PLAYING (a
hazard respawn does; a death goes on to a scene load), cState.dead never set, permadeathMode unchanged, HP >= 1 in
every STATE, and no would_die. Every check prints PASS / FAIL / SKIP; exit code 1 on any FAIL. An ENEMY hit that never
reached PlayerData.TakeHealth (hurt.special take_health_calls == 0: Lucky Dice, Warding Bell, a parry) is a SKIP.

Fractured Mask semantics being asserted (1.0.30000, m0:C2): after blue health absorbs, a hit that would reach 0 HP is
survived at exactly 1 HP when the mask is equipped and AmountLeft > 0, whatever allowFracturedMaskBreak says; the flag
only decides whether the mask is consumed (AmountLeft -> 0). TakeDamage passes (flags & MidChain) == 0, so a MidChain
hit saves without consuming; TakeQuickDamage defaults to no break; chomp, frost, tags and HeroController.TakeHealth
break it. LethalBlock cancels a hit only when the replay reaches 0 HP ("catastrophe"); a hit the mask saves is left
alone. lethal.simulate tells the probe which branch the live state is in. The mask cases run first (MidChain and quick
keep the charge, chomp uses it up), each asserting the charge left afterwards; every later case then tests the
blocking path.
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
# RuntimeError covers OracleError (an "err" reply, including the 2 s main-thread timeout) and the debug line server's
# "err" replies; TimeoutError covers wait_state and RPC timeouts.
ERRORS = (OracleError, TimeoutError, RuntimeError)


class Watch:
    """Collects every STATE's events and tracks the worst hero state seen, from the link's reader thread.

    The per-case fields are cleared by reset(); ever_dead and pdm_ever cover the whole run (death evidence).
    """

    def __init__(self, link: OracleLink):
        self._lock = threading.Lock()
        self.events: list[tuple[int, str, dict]] = []
        self.dead_seen = False
        self.min_hp: int | None = None
        self.pdm_seen: set[int] = set()
        self.gs_seen: set[int | None] = set()
        self.ever_dead = False
        self.pdm_ever: set[int] = set()
        link.subscribe_raw(self._on_raw)

    def _on_raw(self, msg_type: int, raw: bytes) -> None:
        if msg_type != MsgType.STATE:
            return
        s = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
        g = s.get("guards") or {}
        game = s.get("game")
        with self._lock:
            for e in s.get("ev") or ():
                self.events.append((e["f"], e["k"], e.get("d") or {}))
            if g.get("dead"):
                self.dead_seen = True
                self.ever_dead = True
            if g.get("hp") is not None:
                self.min_hp = g["hp"] if self.min_hp is None else min(self.min_hp, g["hp"])
            if g.get("pdm") is not None:
                self.pdm_seen.add(g["pdm"])
                self.pdm_ever.add(g["pdm"])
            # A hazard respawn stays PLAYING; a death goes on to a scene load (EXITING_LEVEL) or the PermaDeath scene.
            self.gs_seen.add(game.get("gs") if game else None)

    def reset(self) -> int:
        with self._lock:
            self.dead_seen = False
            self.min_hp = None
            self.pdm_seen = set()
            self.gs_seen = set()
            return len(self.events)

    def stayed_playing(self) -> bool:
        with self._lock:
            return self.gs_seen <= {PLAYING}

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

    def death_evidence(self, pdm0: int | None, mark: int = 0) -> list[str]:
        """Anything since `mark` that says a death may be in memory (a blocked would_die is the guard working)."""
        why = []
        with self._lock:
            if self.ever_dead:
                why.append("hero dead (cState.dead) in some STATE")
            if pdm0 is not None and self.pdm_ever - {pdm0}:
                why.append(f"permadeathMode {pdm0} -> {sorted(self.pdm_ever - {pdm0})}")
            for f, k, d in self.events[mark:]:
                if k == "would_die" and not d.get("blocked"):
                    why.append(f"unblocked would_die at frame {f} (cause {d.get('cause')})")
                elif k in ("hero_dead", "permadeath_dead", "player_dead"):
                    why.append(f"{k} at frame {f}")
        return why


class Probe:
    def __init__(self, args):
        self.args = args
        self.link = OracleLink(instance=args.instance)
        self.dbg = OracleClient(port=DEBUG_PORT + args.instance)
        self.watch = Watch(self.link)
        self.results: list[tuple[str, str, str]] = []
        self.pdm0: int | None = None
        self.run_mark = 0
        self.snapshot: dict | None = None
        self.snapshot_error: str | None = None
        self.mask_start: dict | None = None
        self.mask_branches: set[str] = set()

    # ---- reporting ----------------------------------------------------------------------------------------

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        status = "PASS" if ok else "FAIL"
        self.results.append((status, name, detail))
        print(f"{status:4}  {name}{'  - ' + detail if detail else ''}", flush=True)
        return ok

    def skip(self, name: str, why: str) -> None:
        self.results.append(("SKIP", name, why))
        print(f"SKIP  {name}  - {why}", flush=True)

    def error(self, name: str, e: Exception) -> None:
        """A check that raised: FAIL, except the oracle's refusal to hurt an unprotected Steel Soul slot (SKIP)."""
        if isinstance(e, OracleError) and "has no snapshot" in str(e):
            self.skip(name, f"refused, as it must be, for a Steel Soul slot without a snapshot: {e}")
        else:
            self.check(name, False, f"{type(e).__name__}: {e}")

    # ---- game helpers -------------------------------------------------------------------------------------

    def g(self) -> dict:
        return self.link.state["guards"]

    def set_hp(self, hp: int, blue: int = 0) -> None:
        self.dbg._call(f"pdset healthBlue {blue}")
        self.dbg._call(f"pdset health {hp}")
        self.link.wait_state(lambda s: s["guards"]["hp"] == hp and s["guards"]["blue"] == blue, timeout_s=2)

    def settle(self, need_vulnerable: bool = True, timeout_s: float = 10.0) -> dict:
        """PLAYING, alive, accepting input, and (optionally) out of i-frames and able to take damage, then a few quiet
        frames. can_take_damage is HeroController.CanTakeDamage(): false through a hazard death, whose hit the game
        drops without a trace (TakeDamage returns early), so a case started then would test nothing."""
        s = self.link.wait_state(
            lambda s: s["game"]["gs"] == PLAYING and s["guards"]["dead"] is False and s["pause"]["hero_input"]
            and (not need_vulnerable or (not s["guards"]["inv"] and s["hero"]["can_take_damage"])), timeout_s=timeout_s)
        time.sleep(0.25)
        return s

    def await_hazard_respawn(self, mark: int, timeout_s: float = 6.0) -> None:
        """A hazard hit (blocked or not) still sends the hero through DieFromHazard and HazardRespawn. Wait for the
        respawn's end: TakeDamage within 0.5 s of HazardRespawn's start is turned into another respawn (no damage),
        and hero_input can read true for a few frames before the hazard death takes control."""
        if self.watch.wait(mark, "hazard_death", 0.5) is None:
            return
        start = self.watch.wait(mark, "hazard_respawn", timeout_s, lambda d: d.get("phase") == "start")
        if start is not None:
            self.watch.wait(mark, "hazard_respawn", timeout_s, lambda d: d.get("phase") == "end" and d.get("id") == start["id"])

    def hurt(self, **args) -> dict:
        return self.link.rpc("hurt.special", **args)

    def mask(self) -> dict:
        """Fresh Fractured Mask state (lethal.simulate reads it the way TakeHealth does)."""
        sim = self.link.rpc("lethal.simulate", amount=0)
        return {"equipped": sim["mask_eq"], "left": sim["mask_left"]}

    # ---- checks -------------------------------------------------------------------------------------------

    def run(self) -> int:
        try:
            self.run_checks()
        except Exception as e:  # noqa: BLE001 - every check catches its own errors; this only keeps the summary
            self.check("probe run", False, f"aborted by {type(e).__name__}: {e}")
        return self.summary()

    def run_checks(self) -> None:
        self.check_handshake()
        self.check_symbols()
        self.check_defaults()
        s = self.link.wait_state(timeout_s=5)
        if not (s.get("game") and s["game"]["gs"] == PLAYING and s["guards"]["hp"] is not None):
            self.check("in game (PLAYING with a hero)", False, "load a sandbox save first; the damage tests need Hornet")
            return
        self.pdm0 = s["guards"]["pdm"]
        self.run_mark = self.watch.reset()
        self.hp_max = self.link.rpc("lethal.simulate", amount=0)["max"]
        self.mask_start = self.mask()
        print(f"      scene {s['game']['scene']}, permadeathMode {self.pdm0}, maxHealth {self.hp_max}, "
              f"Fractured Mask {self.mask_start}")
        if not self.args.skip_snapshot:
            self.take_snapshot()  # before any damage: the slot as it was when the probe started

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
        try:
            self.set_hp(self.hp_max)
        except ERRORS as e:
            print(f"      could not restore full health: {type(e).__name__}: {e}")

    def check_handshake(self) -> None:
        rpcs = set(self.link.hello.get("rpcs", ()))
        missing = [r for r in OUR_RPCS if r not in rpcs]
        self.check("HELLO lists the guard RPCs", not missing, f"missing {missing}" if missing else "")

    def check_symbols(self) -> None:
        r = self.link.rpc("symbols.check", timeout_s=20)  # the cached report of the last pass: no frame hitch
        self.check("symbols.check ok", r["ok"] and not r["missing"],
                   f"{r['resolved_count']}/{r['total']} in {r['us']} us ({r.get('when')}); missing {r['missing']}; "
                   f"soft missing {r['soft_missing']}")

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

    def take_snapshot(self) -> None:
        try:
            slot = self.link.rpc("guards.get")["steel_soul"]["slot"]
            if slot is None or slot < 0:
                self.snapshot_error = "current slot unknown"
                return
            self.snapshot = self.link.rpc("slot.snapshot", slot=slot, name="m1probe", timeout_s=30)
            print(f"      snapshot m1probe of slot {slot}: {self.snapshot['dir']}")
        except ERRORS as e:
            self.snapshot_error = f"{type(e).__name__}: {e}"
            print(f"      snapshot m1probe failed: {self.snapshot_error}")

    # ---- LethalBlock net 1 ----------------------------------------------------------------------------------

    def lethal_case(self, name: str, hp: int, call: dict, sim_amount: int, allow_break: bool, cause: str,
                    hazard: str | None = None, prepare=None, expect_invuln: bool = False) -> dict | None:
        """One scripted hit at `hp`; returns lethal.simulate's prediction when the case ran to a verdict."""
        name = f"net 1: {name}"
        try:
            self.settle()
            self.set_hp(hp)
            if prepare is not None and prepare() is False:
                return None
            sim = self.link.rpc("lethal.simulate", amount=sim_amount, allow_mask_break=allow_break)
            mark = self.watch.reset()
            res = self.hurt(**call)
            enemy = call.get("kind") == "damage" and str(call.get("hazard", "ENEMY")).upper() == "ENEMY"
            if enemy and res.get("take_health_calls") == 0 and not self.watch.since(mark, "catastrophe"):
                self.settle(need_vulnerable=False)
                self.skip(name, f"the hit never reached PlayerData.TakeHealth (Lucky Dice / Warding Bell / parry?); "
                                f"hp {res['hp_before']}->{res['hp_after']}")
                return None
            mask_detail = ""
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
                if sim["mask_saved"]:
                    left = self.mask()["left"]
                    mask_ok = left == sim["mask_left_after"]
                    ok = ok and mask_ok
                    mask_detail = f"; mask charge {sim['mask_left']}->{left} (expected {sim['mask_left_after']})"
                    if mask_ok:
                        self.mask_branches.add("consumed" if sim["mask_consumed"] else "kept")
            self.await_hazard_respawn(mark)
            self.settle(need_vulnerable=False)
            time.sleep(0.3)
            wd = self.watch.since(mark, "would_die")
            g = self.g()
            alive = (not self.watch.dead_seen and not wd and g["hp"] >= 1 and (self.watch.min_hp or 0) >= 1
                     and self.watch.stayed_playing())
            same_mode = g["pdm"] == self.pdm0 and self.watch.pdm_seen <= {self.pdm0}
            invuln_ok = res["invuln_before"] or not expect_invuln
            self.check(name, ok and alive and same_mode and invuln_ok,
                       f"{detail}{mask_detail}; invulnerable at the hit {res['invuln_before']}; "
                       f"hp {res['hp_before']}->{res['hp_after']}, min hp seen {self.watch.min_hp}, dead seen "
                       f"{self.watch.dead_seen}, would_die {len(wd)}, game states {sorted(self.watch.gs_seen, key=str)}, "
                       f"permadeath {self.pdm0}->{g['pdm']}")
            return sim
        except ERRORS as e:
            self.error(name, e)
            return None

    def lethal_cases(self) -> None:
        mask_ready = bool(self.mask_start and self.mask_start["equipped"] and self.mask_start["left"] > 0)
        print(f"      Fractured Mask {'equipped and charged: the mask cases test its branches first' if mask_ready else 'absent or spent: every case tests the blocking path'}")
        # Mask cases first, while the charge is intact: two hits the mask saves without consuming, then one that uses
        # it up. Without the mask each of them is an ordinary lethal hit that must be blocked.
        # MidChain: TakeDamage passes allowFracturedMaskBreak = False, so the mask saves without being consumed.
        self.lethal_case("MidChain enemy hit at 1 HP (mask: saves, never consumed)", 1,
                         dict(kind="damage", hazard="ENEMY", amount=1, flags="MidChain"), 1, False, "damage", "ENEMY")
        # Cog-like: CogMultiHitter lands TakeDamage(1, SPIKES) (m0:C3); cog/grab chains of quick damage use
        # TakeQuickDamage = DoSpecialDamage(canDie: false), which ignores i-frames and could leave 0 HP alive.
        self.lethal_case("cog-like quick damage (TakeQuickDamage) at 1 HP (mask: saves, not consumed)", 1,
                         dict(kind="quick", amount=1, allow_mask_break=False), 1, False, "quick")
        # Grab-like special damage: chomp = DoSpecialDamage(1, canDie, mask may break).
        self.lethal_case("grab-like special damage (TakeChompDamage) at 1 HP (mask: saves and is consumed)", 1,
                         dict(kind="chomp"), 1, True, "chomp")
        self.check_mask_branches(mask_ready)

        # Scripted spike: SPIKES is forced to 1 damage and ignores i-frames; after the blocked hit the hero still
        # hazard-respawns with unchanged health.
        self.lethal_case("scripted spike (TakeDamage SPIKES) at 1 HP", 1,
                         dict(kind="damage", hazard="SPIKES", amount=1), 1, True, "damage", "SPIKES")
        # Lava: forced to 2 damage (1 with a ready Lava Bell); lethal at 1 HP either way.
        self.lethal_case("lava (TakeDamage LAVA, 2 damage) at 1 HP", 1,
                         dict(kind="damage", hazard="LAVA", amount=1), 2, True, "damage", "LAVA")
        self.lethal_case("frost (TakeFrostDamage) at 1 HP", 1, dict(kind="frost", amount=1), 1, True, "frost")
        self.lethal_case("FSM TakeHealth (HeroController.TakeHealth) at 1 HP", 1,
                         dict(kind="take_health", amount=1), 1, True, "hero_take_health")
        self.lethal_case("blue health overflow (1 blue + 1 HP, 3 damage quick)", 1,
                         dict(kind="quick", amount=3), 3, False, "quick", prepare=lambda: self.set_hp(1, blue=1))

        # Spike during i-frames (m0:N1): an enemy hit takes 2 -> 1 HP and starts i-frames; SPIKES passes them.
        def enemy_first() -> bool:
            name = "net 1: spike during i-frames"
            r = self.hurt(kind="damage", hazard="ENEMY", amount=1)
            if r["hp_after"] != 1:
                self.skip(name, f"enemy hit did not land (hp {r['hp_before']}->{r['hp_after']}, TakeHealth calls "
                                f"{r.get('take_health_calls')}; Lucky Dice / Warding Bell / parry?)")
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

    def check_mask_branches(self, mask_ready: bool) -> None:
        name = "Fractured Mask: a save that keeps the charge and a save that consumes it, both seen in the game"
        if not mask_ready:
            why = (f"mask {self.mask_start}: equip the Fractured Mask with its charge intact to test its branches; "
                   "only the blocking path was tested")
            if self.args.require_mask:
                self.check(name, False, why)
            else:
                self.skip(name, why)
            return
        left = None
        try:
            left = self.mask()["left"]
        except ERRORS:
            pass
        self.check(name, {"kept", "consumed"} <= self.mask_branches,
                   f"branches seen {sorted(self.mask_branches)}, charge now {left}")

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
                       and not self.watch.dead_seen and g["pdm"] == self.pdm0 and self.watch.stayed_playing(),
                       f"event {ev and {k: ev.get(k) for k in ('cause', 'path', 'net', 'blocked', 'hp_restored')}}, "
                       f"hp_after {res['hp_after']}, dead {res['dead']}, game states {sorted(self.watch.gs_seen, key=str)}, "
                       f"permadeath {g['pdm']}")
        except ERRORS as e:
            self.error("net 2: CheckDeathCatch", e)

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
        except ERRORS as e:
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
        except ERRORS as e:
            self.check("CriticalDamage", False, f"{type(e).__name__}: {e}")

    # ---- guard switches -------------------------------------------------------------------------------------

    def check_switches(self) -> None:
        name = "guards.set lethal_block=false -> off; non-lethal hit passes, no events"
        try:
            try:
                g = self.link.rpc("guards.set", lethal_block=False)
            except OracleError as e:
                if "no snapshot" not in str(e):
                    raise
                # A Steel Soul session without any snapshot keeps LethalBlock blocking (DESIGN §3.1.1).
                self.skip(name, f"refused, as it must be for an unprotected Steel Soul slot: {e}")
            else:
                st = self.link.wait_state(lambda s: s["guards"]["lb"] == 0, timeout_s=2)
                self.settle()
                self.set_hp(3)
                mark = self.watch.reset()
                res = self.hurt(kind="quick", amount=1)
                time.sleep(0.4)
                quiet = not self.watch.since(mark, "catastrophe", "would_die")
                # Only a non-lethal hit here: hurt.special refuses hits that could kill while LethalBlock is not
                # blocking, and testing that refusal in the game would risk a real death if it failed.
                self.check(name, g["lethal_block"] == "off" and st["guards"]["lb"] == 0 and res["hp_after"] == 2 and quiet,
                           f"hp {res['hp_before']}->{res['hp_after']}")
        except ERRORS as e:
            self.check("guards.set lethal_block=false", False, f"{type(e).__name__}: {e}")
        try:
            g = self.link.rpc("guards.set", lethal_block="block")
            st = self.link.wait_state(lambda s: s["guards"]["lb"] == 2, timeout_s=2)
            self.check("guards.set lethal_block=block -> on again", g["lethal_block"] == "block" and st["guards"]["lb"] == 2)
        except ERRORS as e:
            self.check("guards.set lethal_block=block -> on again", False, f"{type(e).__name__}: {e}")
            return  # no further damage without the guard
        # Blocking works again after the toggle.
        self.lethal_case("after re-enable: quick damage at 1 HP", 1, dict(kind="quick", amount=1), 1, False, "quick")

        try:
            g = self.link.rpc("guards.set", save_suppression=True, achievement_guard=False)
            ok = g["save_suppression"] and not g["achievement_guard"]
            g = self.link.rpc("guards.set", save_suppression=False, achievement_guard=True)
            self.check("guards.set save_suppression / achievement_guard toggle (TRAIN allows both)",
                       ok and not g["save_suppression"] and g["achievement_guard"])
        except ERRORS as e:
            self.check("guards.set save_suppression / achievement_guard toggle", False, f"{type(e).__name__}: {e}")
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
            name = "SaveSuppression off: a real save writes the sandbox slot"
            # Never let the probe write a death to disk: any sign of one earlier in the run skips the real save.
            evidence = self.watch.death_evidence(self.pdm0, self.run_mark)
            g = self.g()
            if g["pdm"] != self.pdm0:
                evidence.append(f"permadeathMode now {g['pdm']} (was {self.pdm0})")
            if evidence:
                self.check(name, False, f"real save SKIPPED, a death may be in memory: {evidence}")
                return
            path = save_dir / ("user.dat" if slot == 0 else f"user{slot}.dat")
            before = path.stat().st_mtime_ns if path.exists() else 0
            r = self.link.rpc("save.trigger", kind="save", timeout_s=15)
            after = path.stat().st_mtime_ns if path.exists() else 0
            self.check(name, r["ok"] and not r["suppressed"] and after != before, f"{path}")
        except (*ERRORS, OSError) as e:
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
            self.check("AchievementGuard blocks every entry point (Award/Push/Progress/MenuStyle/shared SetBool)",
                       r["blocked"] == r["expected"] and "CustomSharedData.SetBool" in r["calls"] and ev is not None
                       and not passed,
                       f"blocked {r['blocked']}/{r['expected']} via {r['calls']}, first event via {ev and ev.get('via')}")
        except ERRORS as e:
            self.check("AchievementGuard", False, f"{type(e).__name__}: {e}")

    # ---- snapshots ------------------------------------------------------------------------------------------

    def check_snapshots(self) -> None:
        name = "slot.snapshot (taken before any damage) copies the slot inside the sandbox"
        if self.snapshot is None:
            self.check(name, False, self.snapshot_error or "no snapshot")
            return
        try:
            r = self.snapshot
            slot = r["slot"]
            primary = "user.dat" if slot == 0 else f"user{slot}.dat"
            on_disk = Path(r["dir"], primary).exists()
            self.check(name, primary in r["entries"] and on_disk and r["dir"].lower().startswith("c:\\ssbot\\sandbox\\"),
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
        except ERRORS as e:
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
        except ERRORS as e:
            self.check("profiles", False, f"{type(e).__name__}: {e}")

    def summary(self) -> int:
        fails = [r for r in self.results if r[0] == "FAIL"]
        try:
            counts = self.link.rpc("guards.get")["counts"]
        except ERRORS as e:
            counts = f"unavailable ({type(e).__name__}: {e})"
        print(f"\n{len(self.results)} checks: {len(fails)} failed, {sum(r[0] == 'SKIP' for r in self.results)} skipped; "
              f"counts {counts}")
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
    ap.add_argument("--require-mask", action="store_true",
                    help="FAIL (instead of SKIP) when the Fractured Mask is not equipped and charged at the start")
    sys.exit(Probe(ap.parse_args()).run())


if __name__ == "__main__":
    main()
