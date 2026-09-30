"""M1 soak (DESIGN M1 exit: 4 instances x 12 h, reset <= 2 s, 0 writes outside the sandbox; R26 CPU stability).

    python -m ssbot.tools.soak --instances 4 --hours 12          # the M1 exit run
    python -m ssbot.tools.soak --instances 2 --minutes 4         # smoke test
    python -m ssbot.tools.soak --instances 2 --minutes 10 --abilities all   # full-ability mode (below)
    (create <out>/STOP to end a run early; the report is still written)

Supervisor (this process): refuses while any game process runs; verifies golden PlayerPrefs; drops single-instance
from the training copy when more than one instance is asked for (launcher --prepare-multi); gives instances 1..N-1 a
copy of sandbox save instance 0 if they have none (inside C:\\ssbot\\sandbox); snapshots the places a game or mod could
write outside the sandbox; watches C:\\Users\\<me>, C:\\ssbot, C:\\ProgramData and the Steam folder for changes
(ReadDirectoryChangesW); launches the instances (ssbot.tools.launcher: PrefsGuard, tiling) and one worker process per
instance; samples each game process (memory, handles, threads, CPU) and the GPU every minute; relaunches an instance
that crashed or hung, and a worker that died, counting each; at the end stops the workers, terminates the instances
(the last one restores the golden PlayerPrefs), and writes report.json + summary.txt.

Worker (--worker N, one process per instance): connects to the oracle, loads save slot 1 and stands up, saves a
savestate "soak_iN" there, then loops episodes until the deadline: savestate.load (the reset; timed), randomize_start
(seed N*1e6 + episode), 8-30 s of random play driven frame by frame (continuous control: left/right runs, jump, attack,
dash, down, rare bind; never up/pause/menus, so no NPC dialogue or menus open), input.release. Everything the oracle
sends is recorded (ssbot.record.Recorder, profile SOAK, a new segment every hour). Per episode one JSON line: reset
times, what the randomizer applied, frames and gaps, frame-time hitches, guard events, brain-lost events. A STATE
silence of HANG_S seconds while the link is open is a hang (exit 3); a closed link is exit 4; failures to reset or to
get back into gameplay are exit 5. The supervisor treats 3 and 5 as a hung game (kill + relaunch) and 4 as a crash.

Nothing here connects to an instance other than its own worker: IPC v1 serves one brain per instance.

Full-ability mode (--abilities movement|combat|all; the early sandbox save has none of these): after entering gameplay
and BEFORE its savestate, each worker turns save suppression on (guards.set), calls the oracle's training-only
abilities.grant (oracle/src/Train/AbilityGrant.cs), waits until STATE shows the grant (hero.can dash / harpoon /
super_jump for movement, the equipped skill and tool in hero.tools for combat) and logs one "abilities" line; the
savestate then carries the grant, so every reset keeps it. movement = Swift Step (dash, sprint), Cling Grip, Drifter's
Cloak, Faydown Cloak, Clawline, Silk Soar; combat = Needle Strike, all six silk skills (one equipped: SKILL_ROTATION by
instance, or --ability-skill) and a thrown tool (TOOL_ROTATION by instance, or --ability-tools); all = both + Needolin.
The policy adds (ability_keys): dash more often, sometimes held (sprint); jump sometimes held long (double jump, then
glide); clawline (S), never together with down (S with only down held is Silk Soar, m0:N41); a Silk Soar macro (down,
then S; left/right released); attack sometimes held 100-150 frames (Needle Strike); quickcast (F) without a direction
for the Neutral-bound skill or tool; a down + quickcast macro when a tool is bound to Down. Still never up, pause,
inventory, map, quick map, journal, quests, the tools pane, Enter, the pane keys, Needolin or taunt.
Risks of these keys: silk skills cost 4 silk and randomize_start draws 0-9, so some casts fail (a HUD flash, nothing
else); tools have limited uses and run out within an episode (the reset refills them; an empty tool just fails);
Clawline and Silk Soar carry Hornet much further, often into the next room (more cross-scene resets, which take
longer); Needle Strike, Clawline and the skills break more of the room (the savestate restores it); a failed grant does
not stop the soak but fails its "abilities" check. Save suppression keeps the grant out of the sandbox slot files every
soak starts from. Without --abilities nothing of this runs and the policy draws exactly the same numbers as before.
Evidence per episode (ability mode only): presses started per key and macro, frames per ability cState flag (dashing,
isSprinting, doubleJumping, floating, wallSliding ...), hero animation clips and Spell Control states, tool amounts.
"""
import argparse
import ctypes
import json
import os
import random
import re
import shutil
import statistics
import struct
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import msgpack

from ssbot.ipc.framing import HEADER, MsgType, mask
from ssbot.ipc.oracle_link import OracleError, OracleLink

HANG_S = 15.0
EXIT_HANG, EXIT_LINK_CLOSED, EXIT_STUCK = 3, 4, 5
SANDBOX = Path(r"C:\ssbot\sandbox")
SAVES = SANDBOX / "saves"
BRAIN_DIR = Path(__file__).resolve().parents[2]
REPO = BRAIN_DIR.parent
RUNS = REPO / "runs"
HOME = Path(os.environ.get("USERPROFILE", r"C:\Users\Meng"))
PACKAGE_CACHE = HOME / r"AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache"
MAX_RELAUNCH = 6          # per instance; after that the instance stays down and the run is a FAIL
RESET_LIMIT_MS = 2000.0   # DESIGN §3.9.1 / M1: reset <= 2 s
# Unity writes its window state into PlayerPrefs while running (launch resolution, fullscreen mode, and the window
# position once the launcher tiles it; seen in the 2026-09-30 smoke run). PrefsGuard's golden restore exists for
# exactly these (DESIGN §2.7, probe P9); any other key changing while the games run is a finding.
SCREEN_PREFS = "Screenmanager "
HITCH_MS = 25.0           # a frame longer than 1.5 refreshes at 60 Hz


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class JsonLog:
    """Append-only JSON lines, flushed per line (a crash loses nothing already written)."""

    def __init__(self, path: Path):
        self._f = path.open("a", encoding="utf-8", newline="\n")
        self._lock = threading.Lock()

    def write(self, **rec) -> None:
        rec.setdefault("t", now_iso())
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with self._lock:
            self._f.write(line + "\n")
            self._f.flush()

    def close(self) -> None:
        self._f.close()


# =====================================================================================================================
# Worker
# =====================================================================================================================

BIT = {name: mask(name) for name in ("left", "right", "jump", "attack", "dash", "down", "bind", "clawline", "quickcast")}

Holds = tuple[tuple[float, int, int], ...]
# Press patterns: key -> (start probability per idle frame, hold options). A hold option is (weight, min, max): the key
# stays down for 1 + randint(min, max) frames, then rests 3 frames. With one option no weight is drawn, so the default
# patterns draw exactly the numbers they always did (the default soak is unchanged).
DEFAULT_KEYS: dict[str, tuple[float, Holds]] = {
    "jump": (0.05, ((1.0, 2, 24),)), "attack": (0.06, ((1.0, 2, 4),)), "dash": (0.012, ((1.0, 2, 4),)),
    "down": (0.01, ((1.0, 10, 40),)), "bind": (0.0015, ((1.0, 2, 4),)),
}
ABILITY_MODES = ("movement", "combat", "all")
# Silk skills (ToolItem name -> in-game name) and simple thrown tools; ability workers take one of each by instance, so
# a 4-instance soak covers four of each. Tools left out: Rosary Cannon (spends rosaries), Pimpilo (its blast), and the
# ones with custom actions, buffs, silk costs or summons (Screw Attack, Conch Drill, Silk Snare, Flintstone, Flea Brew,
# Lifeblood Syringe, Extractor, Lightning Rod, Cogwork Flier, WebShot).
SKILLS = {"Silk Spear": "Silkspear", "Thread Sphere": "Thread Storm", "Parry": "Cross Stitch",
          "Silk Charge": "Sharpdart", "Silk Bomb": "Rune Rage", "Silk Boss Needle": "Pale Nails"}
SKILL_ROTATION = tuple(SKILLS)
TOOL_ROTATION = ("Straight Pin", "Tri Pin", "Sting Shard", "Curve Claws", "Tack", "Shakra Ring")
# Never started while down is held, and down never starts under them: S with only down held is Silk Soar, not Clawline
# (m0:N41), and QuickCast with down throws the Down-bound tool. Their down variants are macros.
NOT_WITH_DOWN = ("clawline", "quickcast")
# Keys no policy presses: up (NPC dialogue, benches, doors), pause, the inventory / map / journal / quests / tools
# screens and quick map, the menu keys (Enter, pane switches), Needolin (NPCs answer it, some objects start scripted
# sequences) and taunt.
FORBIDDEN_KEYS = ("up", "pause", "inventory", "map", "quickmap", "journal", "quests", "tools", "enter", "paneleft",
                  "paneright", "needolin", "taunt")
# hero.can flags a movement grant must turn true (the others do not depend on a grant: CanThrowTool(false), CanCast).
MOVEMENT_CAN = ("dash", "harpoon", "super_jump")


@dataclass(frozen=True)
class Macro:
    """A fixed press sequence, one mask per frame. Starts only when no key is held and the movement run has lasted two
    frames; left/right stay released for its length and a new run starts after it. Its keys rest 3 frames afterwards."""
    name: str
    p: float
    frames: tuple[int, ...]

    @property
    def keys(self) -> tuple[str, ...]:
        m = 0
        for f in self.frames:
            m |= f
        return tuple(k for k, b in BIT.items() if m & b)


_DOWN, _CLAW, _CAST = BIT["down"], BIT["clawline"], BIT["quickcast"]
SILK_SOAR = Macro("silk_soar", 0.002, (_DOWN, _DOWN, _DOWN | _CLAW, _DOWN | _CLAW, _DOWN | _CLAW, _DOWN))
DOWN_CAST = Macro("down_cast", 0.004, (_DOWN, _DOWN, _DOWN | _CAST, _DOWN | _CAST, _DOWN | _CAST, _DOWN))


def ability_keys(mode: str | None, bindings: dict | None = None) -> tuple[dict[str, tuple[float, Holds]], tuple[Macro, ...]]:
    """Press patterns and macros of an ability mode (None: the default soak). bindings: abilities.grant's "bindings"
    (what QuickCast throws per held direction); QuickCast is only pressed for a direction that throws something.
      movement: dash more often, 30 % of presses held 15-90 frames (sprint); 15 % of jumps held 30-80 frames (the double
                jump, then the glide, which lasts while jump is held); clawline 2-6 frames; the Silk Soar macro.
      combat:   5 % of attacks held 100-150 frames (Needle Strike charges for 0.3 + 1.35 s and strikes on release);
                quickcast 2-4 frames with no direction (the Neutral-bound skill or tool); the down + quickcast macro when
                a tool is bound to Down.
      all:      both."""
    keys = dict(DEFAULT_KEYS)
    if mode is None:
        return keys, ()
    if mode not in ABILITY_MODES:
        raise ValueError(f"ability mode must be one of {ABILITY_MODES}, not {mode!r}")
    macros: list[Macro] = []
    if mode in ("movement", "all"):
        keys["jump"] = (0.05, ((0.85, 2, 24), (0.15, 30, 80)))
        keys["dash"] = (0.02, ((0.7, 2, 4), (0.3, 15, 90)))
        keys["clawline"] = (0.008, ((1.0, 2, 6),))
        macros.append(SILK_SOAR)
    if mode in ("combat", "all"):
        keys["attack"] = (0.06, ((0.95, 2, 4), (0.05, 100, 150)))
        b = bindings or {}
        if b.get("neutral"):
            keys["quickcast"] = (0.01, ((1.0, 2, 4),))
        if b.get("down"):
            macros.append(DOWN_CAST)
    return keys, tuple(macros)


class Policy:
    """Random play with some persistence: runs of movement, presses of varied length with releases in between (the
    oracle's minimum press/release is 2 frames), occasional down (down-attacks in the air). Never up (NPC dialogue,
    benches, doors), pause, inventory, map or tools (FORBIDDEN_KEYS). keys / macros: ability_keys (default: the
    DEFAULT_KEYS patterns, no macros). counts: presses started per key and macro; macro: name of the macro that made
    the last mask (None otherwise)."""

    def __init__(self, rng: random.Random, keys: dict | None = None, macros: tuple[Macro, ...] = ()):
        self.r = rng
        self.keys = DEFAULT_KEYS if keys is None else keys
        self.macros = tuple(macros)
        self.move: str | None = None
        self.move_left = 0
        self.move_run = 0
        self.timers = {k: 0 for k in self.keys}
        self.rest = {k: 0 for k in self.keys}
        self.macro_only = sorted({k for mac in self.macros for k in mac.keys} - set(self.keys))
        for k in self.macro_only:
            self.rest[k] = 0
        self.script: list[int] = []
        self.script_keys: tuple[str, ...] = ()
        self.macro: str | None = None
        self.counts: Counter = Counter()

    def step(self) -> int:
        r = self.r
        if (not self.script and self.macros and not any(self.timers.values())
                and (self.move is None or self.move_run >= 2)):
            for mac in self.macros:
                if all(self.rest[k] == 0 for k in mac.keys) and r.random() < mac.p:
                    self.script, self.script_keys, self.macro = list(mac.frames), mac.keys, mac.name
                    self.counts[mac.name] += 1
                    self.move_left = 0
                    break
        if self.script:
            m = self.script.pop(0)
            if not self.script:
                for k in self.script_keys:
                    self.rest[k] = 3
            return m
        self.macro = None
        if self.move_left <= 0:
            self.move = r.choices(("left", "right", None), (0.42, 0.42, 0.16))[0]
            self.move_left = r.randint(8, 100)
            self.move_run = 0
        self.move_left -= 1
        self.move_run += 1
        m = BIT[self.move] if self.move else 0
        for k, (p, holds) in self.keys.items():
            if self.timers[k] > 0:
                self.timers[k] -= 1
                m |= BIT[k]
                if self.timers[k] == 0:
                    self.rest[k] = 3
            elif self.rest[k] > 0:
                self.rest[k] -= 1
            elif not self._blocked(k, m) and r.random() < p:
                self.timers[k] = self._hold(holds)
                self.counts[k] += 1
                m |= BIT[k]
        for k in self.macro_only:
            if self.rest[k] > 0:
                self.rest[k] -= 1
        return m

    def _blocked(self, k: str, m: int) -> bool:
        """NOT_WITH_DOWN keys never start while down is held (down comes first in the key order, so m has it), and down
        never starts under them. No draw is skipped for the default keys."""
        if k == "down":
            return any(self.timers.get(x, 0) for x in NOT_WITH_DOWN)
        return k in NOT_WITH_DOWN and bool(m & BIT["down"])

    def _hold(self, holds: Holds) -> int:
        if len(holds) == 1:
            return self.r.randint(holds[0][1], holds[0][2])
        _, lo, hi = self.r.choices(holds, [h[0] for h in holds])[0]
        return self.r.randint(lo, hi)


def ability_request(mode: str, instance: int, tools: str | None = None, skill: str | None = None) -> dict:
    """abilities.grant arguments for worker `instance`. movement grants the flags only; combat and all add one silk
    skill to equip and the thrown tools (comma-separated names; "" = none), by default one of each per instance
    (SKILL_ROTATION, TOOL_ROTATION), with unlock_slots: a crest whose only unlocked Red slot is bound to Up (never
    pressed) may then use its locked one, unlocked as a Memory Locket would."""
    if mode not in ABILITY_MODES:
        raise ValueError(f"ability mode must be one of {ABILITY_MODES}, not {mode!r}")
    req: dict = {"set": mode}
    if mode == "movement":
        return req
    req["skill"] = skill or SKILL_ROTATION[instance % len(SKILL_ROTATION)]
    req["tools"] = ([t.strip() for t in tools.split(",") if t.strip()] if tools is not None
                    else [TOOL_ROTATION[instance % len(TOOL_ROTATION)]])
    req["unlock_slots"] = True
    return req


def expected_can(mode: str) -> tuple[str, ...]:
    """hero.can flags STATE must show as true after a grant of `mode`."""
    return MOVEMENT_CAN if mode in ("movement", "all") else ()


def granted_equips(res: dict) -> list[str]:
    """Names from an abilities.grant reply's "requested" (skill, then tools) that sit in a slot of the current crest."""
    in_slots = {s.get("tool") for s in res.get("slots") or () if s.get("tool")}
    return [n for n in res.get("requested") or () if n in in_slots]


def ability_gaps(s: dict | None, want_can: tuple[str, ...], want_tools: list[str]) -> list[str]:
    """What a STATE does not show yet of a grant: hero.can flags that are not true, equipped names absent from
    hero.tools. Empty = verified."""
    hero = (s or {}).get("hero") or {}
    can = hero.get("can") or {}
    have = {t for t in hero.get("tools") or () if t}
    return [f"can.{k}" for k in want_can if can.get(k) is not True] + [f"tool {t}" for t in want_tools if t not in have]


# cState flags that show a granted ability in use (ability mode evidence; names from schema.cstate).
EVIDENCE_CSTATE = ("dashing", "airDashing", "isSprinting", "doubleJumping", "floating", "wallSliding", "wallClinging",
                   "wallJumping", "nailCharging", "isToolThrowing")


class FrameStats:
    """Per-frame counters from the raw STATE stream (reader thread). take() returns and resets the window. After
    track_abilities (ability mode only) the window also counts EVIDENCE_CSTATE flags, hero animation clips and Spell
    Control states."""

    def __init__(self):
        self._lock = threading.Lock()
        self.last_f: int | None = None
        self.last_rx = time.monotonic()
        self.total_frames = 0
        self.total_gaps = 0
        self.ability_bits: dict[str, int] | None = None
        self._reset()

    def track_abilities(self, cstate_names: list[str]) -> None:
        """cstate_names: schema.cstate "bools" (the bit order of hero.cstate)."""
        with self._lock:
            self.ability_bits = {n: i for i, n in enumerate(cstate_names) if n in EVIDENCE_CSTATE}

    def _reset(self) -> None:
        self.frames = 0
        self.gaps = 0
        self.missing = 0
        self.hitches = 0
        self.udt_max = 0.0
        self.play_frames = 0       # steady-gameplay frames (PLAYING, no transition): the frame-time sample
        self.udt_sum = 0.0
        self.udt_hist = [0] * 201  # 0.5 ms bins up to 100 ms (last bin: longer)
        self.cost_max = 0
        self.drop_counter = None
        self.events: Counter = Counter()
        self.dead_seen = False
        self.min_hp: int | None = None
        self.ab_cstate: Counter = Counter()
        self.ab_clips: Counter = Counter()
        self.ab_spell: Counter = Counter()

    def _count_abilities(self, hero: dict) -> None:
        words = hero.get("cstate")
        if words:
            for name, i in self.ability_bits.items():
                if (i >> 6) < len(words) and (words[i >> 6] >> (i & 63)) & 1:
                    self.ab_cstate[name] += 1
        clip = (hero.get("anim") or {}).get("clip")
        if clip:
            self.ab_clips[clip] += 1
        spell = hero.get("spell")
        if spell:
            self.ab_spell[spell[0]] += 1

    def on_raw(self, msg_type: int, raw: bytes) -> None:
        if msg_type != MsgType.STATE:
            return
        try:
            s = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
        except Exception:  # noqa: BLE001 - a bad frame is counted by the recorder; never kill the reader thread
            return
        with self._lock:
            self.last_rx = time.monotonic()
            f = s.get("f")
            if isinstance(f, int):
                if self.last_f is not None and f > self.last_f + 1:
                    self.gaps += 1
                    self.missing += f - self.last_f - 1
                    self.total_gaps += 1
                self.last_f = f
            self.frames += 1
            self.total_frames += 1
            udt = s.get("udt")
            if isinstance(udt, (int, float)):
                ms = udt * 1000.0
                self.udt_max = max(self.udt_max, ms)
                game = s.get("game") or {}
                # Loads legitimately take long frames; frame time and hitches count only steady gameplay.
                if game.get("gs") == 4 and not game.get("transition") and not game.get("paused"):
                    self.play_frames += 1
                    self.udt_sum += ms
                    self.udt_hist[min(200, int(ms * 2))] += 1
                    if ms > HITCH_MS:
                        self.hitches += 1
            c = s.get("cost_us")
            if isinstance(c, int):
                self.cost_max = max(self.cost_max, c)
            self.drop_counter = s.get("drop", self.drop_counter)
            for e in s.get("ev") or ():
                k = e.get("k")
                if k in ("catastrophe", "would_die", "save_suppressed", "achievement_blocked", "harness",
                         "hazard_death", "scene_enter", "damage", "damage_blocked", "die", "death_catch",
                         "hero_dead", "player_dead", "permadeath_dead", "steel_soul_unprotected",
                         "profile_violation", "save", "save_vetoed", "session_refused"):
                    self.events[k] += 1
            g = s.get("guards") or {}
            if g.get("dead"):
                self.dead_seen = True
            hp = g.get("hp")
            if isinstance(hp, int):
                self.min_hp = hp if self.min_hp is None else min(self.min_hp, hp)
            if self.ability_bits is not None and s.get("hero"):
                self._count_abilities(s["hero"])

    def take(self) -> dict:
        with self._lock:
            n = self.play_frames
            p99 = None
            if n:
                acc, want = 0, n * 0.99
                for b, c in enumerate(self.udt_hist):
                    acc += c
                    if acc >= want:
                        p99 = b / 2 + 0.5
                        break
            d = {"frames": self.frames, "gaps": self.gaps, "missing": self.missing, "hitches": self.hitches,
                 "play_frames": n, "udt_mean_ms": round(self.udt_sum / n, 3) if n else None, "udt_p99_ms": p99,
                 "udt_max_ms": round(self.udt_max, 1), "cost_max_us": self.cost_max, "drop_counter": self.drop_counter,
                 "events": dict(self.events), "dead_seen": self.dead_seen, "min_hp": self.min_hp}
            if self.ability_bits is not None:
                d["abilities"] = {"cstate": dict(self.ab_cstate), "clips": dict(self.ab_clips.most_common(20)),
                                  "spell": dict(self.ab_spell.most_common(10))}
            self._reset()
            return d

    def silent_s(self) -> float:
        with self._lock:
            return time.monotonic() - self.last_rx


class WorkerExit(Exception):
    def __init__(self, code: int, why: str):
        super().__init__(why)
        self.code = code


class Worker:
    def __init__(self, args):
        self.i = args.worker
        self.out = Path(args.out)
        self.deadline = args.deadline
        self.stop_file = self.out / "STOP"
        self.log = JsonLog(self.out / f"worker_{self.i}.jsonl")
        self.name = f"{self.out.name}_i{self.i}"  # e.g. soak_062944_i0: one savestate per soak and instance
        self.save_scene: str | None = None
        self.rng = random.Random(1_000_003 * (self.i + 1) + int(args.deadline))
        self.link: OracleLink | None = None
        self.stats = FrameStats()
        self.rec = None
        self.rec_started = 0.0
        self.segment = 0
        self.episode = 0
        self.abilities: str | None = getattr(args, "abilities", None)
        self.ability_args = (ability_request(self.abilities, self.i, getattr(args, "ability_tools", None),
                                             getattr(args, "ability_skill", None)) if self.abilities else None)
        self.keys, self.macros = ability_keys(None)  # grant_abilities sets the ability patterns

    # ---- plumbing ----------------------------------------------------------------------------------------------------

    def done(self) -> bool:
        return time.time() >= self.deadline or self.stop_file.exists()

    def wait(self, pred, timeout_s: float, newer_than: int | None = None) -> dict:
        try:
            return self.link.wait_state(pred, timeout_s=timeout_s, newer_than=newer_than)
        except TimeoutError:
            self.check_alive()
            raise

    def check_alive(self) -> None:
        if self.link.closed:
            raise WorkerExit(EXIT_LINK_CLOSED, "oracle link closed")
        if self.stats.silent_s() > HANG_S:
            raise WorkerExit(EXIT_HANG, f"no STATE for {self.stats.silent_s():.1f} s with the link open")

    def rpc(self, name: str, timeout_s: float = 30.0, **args):
        try:
            return self.link.rpc(name, timeout_s=timeout_s, **args)
        except OracleError:
            self.check_alive()
            raise
        except TimeoutError:  # concurrent.futures.TimeoutError is TimeoutError on 3.11+
            self.check_alive()
            raise

    def start_segment(self) -> None:
        from ssbot.record.recorder import Recorder

        old = self.rec
        self.segment += 1
        self.rec = Recorder(self.link, out_dir=RUNS, profile="SOAK",
                            episode=f"{self.out.name}_i{self.i}_s{self.segment:02d}_{datetime.now():%H%M%S}",
                            config={"soak": str(self.out), "instance": self.i, "segment": self.segment}).start()
        self.rec_started = time.monotonic()
        if old is not None:
            self.close_segment(old)

    def close_segment(self, rec) -> None:
        try:
            s = rec.close()
            c = s.get("continuity") or {}
            self.log.write(kind="segment", path=s.get("path"), drops=s.get("drops"), error=s.get("error"),
                           delivery=c.get("delivery"), expected=c.get("expected"), received=c.get("states"),
                           missing=c.get("missing"), gap_count=c.get("gap_count"), nonmonotonic=c.get("nonmonotonic"),
                           unexplained=c.get("unexplained"), cost_us=c.get("cost_us"), latency_ms=c.get("latency_ms"),
                           duration_s=c.get("duration_s"), continuity_error=c.get("error"), ok=c.get("ok"))
        except Exception as e:  # noqa: BLE001 - a failed close is a finding, not a reason to stop the soak
            self.log.write(kind="segment_error", path=str(getattr(rec, "path", "")), error=repr(e))

    # ---- getting into gameplay ---------------------------------------------------------------------------------------

    def unpause(self) -> None:
        """Pause menu -> Continue (the default selection) with Submit; Esc (MenuCancel) as the fallback."""
        from ssbot.probes.common import tap

        for key in ("enter", "enter", "pause", "enter"):
            time.sleep(0.8)  # the pause menu fades in; a press during the fade is dropped
            tap(self.link, key, hold_frames=3)
            try:
                self.wait(lambda s: not s["game"]["paused"], 2.0)
            except TimeoutError:
                continue
            # An Esc can be handled twice (DESIGN §3.7.5): count it only if the game stays unpaused for 10 frames.
            if self.stays(lambda s: not s["game"]["paused"] and s["game"]["gs"] == 4, frames=10):
                self.rpc("input.release")
                self.log.write(kind="note", note=f"unpaused with {key}", f=self.link.frame)
                return
        self.rpc("input.release")
        raise WorkerExit(EXIT_STUCK, "could not unpause")

    def stays(self, pred, frames: int) -> bool:
        """pred holds on `frames` consecutive new STATEs."""
        last = self.link.frame
        for _ in range(frames):
            s = self.wait(lambda s: True, 2.0, newer_than=last)
            last = s["f"]
            try:
                if not pred(s):
                    return False
            except (KeyError, TypeError):
                return False
        return True

    def enter_gameplay(self) -> None:
        from ssbot.probes.common import in_gameplay, load_slot, stand_up

        s = self.wait(lambda s: s.get("game") is not None, 180)
        if s["game"].get("paused"):
            self.unpause()
        if not in_gameplay(self.link.state):
            load_slot(self.link, 1, timeout_s=180)
        stand_up(self.link, timeout_s=30)
        self.rpc("input.release")

    def ensure_ready_for_reset(self) -> None:
        s = self.link.state or {}
        if (s.get("game") or {}).get("paused"):
            self.log.write(kind="note", note="paused before reset (brain-lost tap?)", f=s.get("f"))
            self.unpause()

    def grant_abilities(self) -> None:
        """--abilities, in gameplay and before the savestate: save suppression on (the grant must never reach the
        sandbox slot files every soak starts from), abilities.grant, then wait until STATE shows it. One "abilities"
        line; a failure is logged (ok false, which fails the report's abilities check) and the soak goes on. The policy
        gets the ability patterns either way, QuickCast only for the directions the grant says throw something."""
        rec = {"kind": "abilities", "mode": self.abilities, "request": self.ability_args, "ok": False}
        bindings = {}
        try:
            self.stats.track_abilities(self.rpc("schema.cstate", timeout_s=10)["bools"])
            if "abilities.grant" not in (self.link.hello.get("rpcs") or ()):
                raise OracleError("this SsOracle has no abilities.grant (build and deploy the plugin once no soak runs)")
            g = self.rpc("guards.set", timeout_s=10, save_suppression=True)
            if not (g or {}).get("save_suppression"):
                raise OracleError(f"save suppression did not turn on: {g}")
            res = self.rpc("abilities.grant", timeout_s=30, **self.ability_args)
            bindings = res.get("bindings") or {}
            want_can, want_tools = expected_can(self.abilities), granted_equips(res)
            rec.update(grant=res, want_can=want_can, want_tools=want_tools)
            gaps = [f"unplaced: {u}" for u in res.get("unplaced") or ()]
            try:
                rec["verified_f"] = self.wait(lambda s: not ability_gaps(s, want_can, want_tools), 5.0)["f"]
            except TimeoutError:
                s = self.link.state or {}
                gaps += ability_gaps(s, want_can, want_tools)
                rec["can"] = (s.get("hero") or {}).get("can")
            rec.update(ok=not gaps, gaps=gaps)
        except (OracleError, TimeoutError, KeyError, TypeError) as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        self.keys, self.macros = ability_keys(self.abilities, bindings)
        rec.update(keys=sorted(self.keys), macros=[m.name for m in self.macros])
        self.log.write(**rec)

    # ---- episodes ----------------------------------------------------------------------------------------------------

    def reset(self) -> dict:
        """savestate.load, timed. reset_wall_ms is the successful call; reset_total_ms runs from the first attempt
        (retries and unpausing included), which is what the <= 2 s check uses. cross_scene: the hero had wandered
        into another room, so the load includes a scene load; transition: a room transition was running."""
        errors = []
        t_first = time.perf_counter()
        s = self.link.state or {}
        game = s.get("game") or {}
        info = {"scene_before": game.get("scene"), "transition_before": bool(game.get("transition")),
                "cross_scene": game.get("scene") != self.save_scene}
        for attempt in range(4):
            self.ensure_ready_for_reset()
            t0 = time.perf_counter()
            try:
                res = self.rpc("savestate.load", timeout_s=40, state=self.name, timeout=30)
                now = time.perf_counter()
                return {**info, "reset_wall_ms": round((now - t0) * 1000.0, 1),
                        "reset_total_ms": round((now - t_first) * 1000.0, 1), "reset": res,
                        "attempts": attempt + 1, "errors": errors}
            except (OracleError, TimeoutError) as e:
                errors.append(f"{type(e).__name__}: {e}")
                self.log.write(kind="reset_error", ep=self.episode, attempt=attempt + 1, error=errors[-1], **info)
                time.sleep(2.0)
        raise WorkerExit(EXIT_STUCK, f"savestate.load failed 4 times: {errors}")

    def play(self, seconds: float) -> dict:
        policy = Policy(self.rng, self.keys, self.macros)
        last = self.link.frame
        end = last + int(seconds * 60)
        acts = 0
        interrupted = None
        try:
            while last < end:
                if self.done():
                    break
                try:
                    s = self.link.wait_state(newer_than=last, timeout_s=1.0)
                except TimeoutError:
                    self.check_alive()
                    continue
                last = s["f"]
                # Paused (a brain-lost tap, or anything else): the policy's keys are the pause menu's keys too
                # (Submit, Cancel, arrows), so stop at once instead of working the menu towards "Quit".
                if (s.get("game") or {}).get("paused"):
                    self.link.act(last + 2, 0, hold_frames=0)
                    interrupted = f"paused at frame {last}"
                    break
                self.link.act(last + 2, policy.step(), hold_frames=0)
                acts += 1
        finally:
            try:
                self.rpc("input.release", timeout_s=10)
            except (OracleError, TimeoutError):
                pass
        out = {"acts": acts, "end_frame": last, "interrupted": interrupted}
        if self.abilities:
            out["presses"] = dict(policy.counts)
        return out

    def episode_once(self) -> None:
        self.episode += 1
        rec = {"kind": "episode", "ep": self.episode}
        # Frames since the previous episode's play ended (its RPCs, a segment rotation, this reset): kept, not dropped.
        rec["stats_between"] = self.stats.take()
        rec.update(self.reset())
        seed = self.i * 1_000_000 + self.episode
        try:
            r = self.rpc("randomize_start", timeout_s=30, seed=seed, hp=[1, 5], silk=[0, 9], dx=[-3, 3],
                         facing="random", wait_frames=[0, 20])
            rec["rand"] = {k: r.get(k) for k in ("seed", "hp", "silk", "dx", "facing", "wait_frames")} if isinstance(r, dict) else r
        except (OracleError, TimeoutError) as e:
            rec["rand_error"] = f"{type(e).__name__}: {e}"
        secs = self.rng.uniform(8.0, 30.0)
        rec["play_s"] = round(secs, 1)
        rec.update(self.play(secs))
        g = self.link.state or {}
        rec["scene_end"] = (g.get("game") or {}).get("scene")
        if self.abilities:
            hero = g.get("hero") or {}
            rec["silk_end"] = hero.get("silk")
            rec["tools_end"] = {t: a for t, a in zip(hero.get("tools") or (), hero.get("tool_amounts") or ()) if t}
        rec["stats"] = self.stats.take()
        try:
            st = self.rpc("input.stats", timeout_s=10)
            rec["input"] = {k: st.get(k) for k in ("lost_events", "lost_pause_taps", "lost_pauses_confirmed",
                                                    "stale", "suppressed", "rejected", "coalesced")} if isinstance(st, dict) else None
        except (OracleError, TimeoutError) as e:
            rec["input_error"] = str(e)
        if self.episode % 25 == 1:
            try:
                gd = self.rpc("guards.get", timeout_s=10)
                rec["guards"] = {"healthy": gd.get("healthy"), "lethal_block": gd.get("lethal_block"),
                                 "profile": gd.get("profile"), "refusals": gd.get("refusals")}
            except (OracleError, TimeoutError) as e:
                rec["guards_error"] = str(e)
            if self.abilities:  # the reset keeps the grant: the savestate carries it
                try:
                    ab = self.rpc("abilities.list", timeout_s=10)
                    rec["abilities"] = {k: ab.get(k) for k in ("sets", "bindings", "save_suppression")}
                except (OracleError, TimeoutError) as e:
                    rec["abilities_error"] = str(e)
        self.log.write(**rec)

    def run(self) -> int:
        self.log.write(kind="start", pid=os.getpid(), deadline=datetime.fromtimestamp(self.deadline).isoformat())
        try:
            self.link = OracleLink(instance=self.i, connect_timeout_s=180)
            self.link.subscribe_raw(self.stats.on_raw)
            self.log.write(kind="hello", hello={k: self.link.hello.get(k) for k in ("plugin", "game", "instance")})
            self.enter_gameplay()
            if self.abilities:
                self.grant_abilities()  # before the savestate, so every reset keeps the grant
            # One savestate per soak and instance, taken once: a restarted worker (its game may have been left
            # anywhere) reuses it instead of capturing wherever Hornet happens to be.
            listed = self.rpc("savestate.list", timeout_s=30)
            mine = [x for x in (listed or {}).get("states", []) if x.get("name") == self.name]
            if mine:
                self.save_scene = mine[0].get("scene")
                self.log.write(kind="savestate", name=self.name, scene=self.save_scene, reused=True)
            else:
                s = self.link.state
                self.rpc("savestate.save", timeout_s=30, state=self.name)
                self.save_scene = s["game"]["scene"]
                self.log.write(kind="savestate", name=self.name, scene=self.save_scene, pos=s["hero"]["pos"])
            self.start_segment()
            while not self.done():
                if time.monotonic() - self.rec_started > 3600:
                    self.start_segment()
                self.episode_once()
            code, why = 0, "deadline" if time.time() >= self.deadline else "stop file"
        except WorkerExit as e:
            code, why = e.code, str(e)
        except Exception as e:  # noqa: BLE001
            code, why = 1, f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            if self.link is not None and self.link.closed:
                code = EXIT_LINK_CLOSED
        if self.rec is not None:
            self.close_segment(self.rec)
        self.log.write(kind="exit", code=code, why=why, episodes=self.episode,
                       total_frames=self.stats.total_frames, total_gaps=self.stats.total_gaps)
        if self.link is not None and not self.link.closed:
            try:
                self.link.rpc("input.release", timeout_s=5)
            except Exception:  # noqa: BLE001
                pass
            self.link.close()
        self.log.close()
        return code


# =====================================================================================================================
# Supervisor: write watch, snapshots, sampling
# =====================================================================================================================

FILE_ACTIONS = {1: "added", 2: "removed", 3: "modified", 4: "renamed_from", 5: "renamed_to"}


class DirWatcher(threading.Thread):
    """Recursive ReadDirectoryChangesW on one root; aggregates paths (first/last seen, count, actions). The blocking
    call is never cancelled: the thread is a daemon and stop() only freezes the result."""

    FLAGS = 0x1 | 0x2 | 0x8 | 0x10 | 0x40  # FILE_NAME, DIR_NAME, SIZE, LAST_WRITE, CREATION

    def __init__(self, root: Path):
        super().__init__(daemon=True, name=f"watch:{root}")
        self.root = Path(root)
        self.paths: dict[str, list] = {}
        self.overflows = 0
        self.error: str | None = None
        self.started = False
        self._lock = threading.Lock()
        self._frozen = False

    def run(self) -> None:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.ReadDirectoryChangesW.restype = wintypes.BOOL
        k32.ReadDirectoryChangesW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL,
                                              wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
                                              ctypes.c_void_p]
        h = k32.CreateFileW(str(self.root), 0x1, 0x7, None, 3, 0x02000000, None)  # LIST_DIRECTORY, share all, OPEN_EXISTING, BACKUP_SEMANTICS
        if h in (None, wintypes.HANDLE(-1).value):
            self.error = f"CreateFileW failed ({ctypes.get_last_error()})"
            return
        buf = ctypes.create_string_buffer(1 << 20)
        n = wintypes.DWORD()
        self.started = True
        while True:
            ok = k32.ReadDirectoryChangesW(h, buf, len(buf), True, self.FLAGS, ctypes.byref(n), None, None)
            if not ok:
                self.error = f"ReadDirectoryChangesW failed ({ctypes.get_last_error()})"
                return
            if n.value == 0:
                with self._lock:
                    self.overflows += 1
                continue
            self._parse(buf.raw[:n.value])

    def _parse(self, data: bytes) -> None:
        t = time.time()
        off = 0
        with self._lock:
            if self._frozen:
                return
            while off + 12 <= len(data):
                nxt, action, ln = struct.unpack_from("<III", data, off)
                name = data[off + 12:off + 12 + ln].decode("utf-16-le", errors="replace")
                full = str(self.root / name)
                e = self.paths.get(full)
                if e is None:
                    self.paths[full] = [t, t, 1, {FILE_ACTIONS.get(action, str(action))}]
                else:
                    e[1] = t
                    e[2] += 1
                    e[3].add(FILE_ACTIONS.get(action, str(action)))
                if nxt == 0:
                    break
                off += nxt

    def result(self, freeze: bool = False) -> dict:
        with self._lock:
            self._frozen = self._frozen or freeze
            return {"root": str(self.root), "started": self.started, "error": self.error, "overflows": self.overflows,
                    "paths": {p: {"first": datetime.fromtimestamp(v[0]).isoformat(timespec="seconds"),
                                  "last": datetime.fromtimestamp(v[1]).isoformat(timespec="seconds"),
                                  "count": v[2], "actions": sorted(v[3])} for p, v in self.paths.items()}}


# Classification of a written path. Order matters: the first match wins.
_ALLOWED = [
    (r"^c:\\ssbot\\sandbox(\\|$)", "sandbox"),
    (re.escape(str(RUNS).lower()) + r"(\\|$)", "soak recordings (runs/)"),
    (r"^c:\\ssbot\\game\\train\\bepinex\\(logoutput\.log(\.\d+)?|config(\\|$)|cache(\\|$))", "BepInEx log/config (training copy)"),
]
_MINE = [
    (r"^c:\\ssbot\\tools(\\|$)", "my tooling (uv, ffmpeg)"),
    (re.escape(str(REPO).lower()) + r"(\\|$)", "repository"),
    (r"\\appdata\\roaming\\(claude|rerun|uv)(\\|$)", "Claude app / my tools"),
    (r"\\appdata\\local\\(claude|claude-cli-nodejs|anthropicclaude|uv|rerun)(\\|$)", "Claude app / my tools"),
    (r"\\\.claude(\\|$)", "Claude Code"),
    (r"\\appdata\\local\\packages\\claude_[^\\]+(\\(?!localcache\\)[^\\]+.*)?$", "Claude app package (not LocalCache)"),
    (r"\\appdata\\local\\temp\\claude(\\|$)", "Claude scratch"),
]
# MSIX: a process started from the Claude desktop app may have its new AppData files redirected into the app's
# package LocalCache. Such paths are classified as the AppData path they stand for.
_MSIX = re.compile(r"^(.*\\appdata\\)local\\packages\\claude_[^\\]+\\localcache\\(local|roaming|locallow)(\\.*)?$")
_DRIVER = [
    (r"\\nvidia(\\|$)|\\nvidia corporation(\\|$)|\\d3dscache(\\|$)|\\intel\\shadercache", "GPU driver caches"),
    (r"\\appdata\\locallow\\[0-9a-f]{64}$", "Intel shader cache (LocalLow root, 64-hex names)"),
    (r"\\appdata\\locallow\\intel(\\|$)", "Intel shader cache"),
]
_GAME = re.compile(r"team cherry|silksong|hollow knight|bepinex|debugmod|\\unity|unity3d|ssbot|1030300", re.I)


def classify(path: str, actions: list | None = None) -> str:
    """Class of a path written during the soak. actions: the watcher's actions for it; a directory whose only
    action is 'modified' is its own metadata changing because a child changed (ReadDirectoryChangesW with
    LAST_WRITE reports the parent too), so the child's own entry carries the verdict."""
    p = path.lower()
    if actions is not None and set(actions) == {"modified"} and os.path.isdir(path):
        return "dir metadata (a child changed)"
    m = _MSIX.match(p)
    if m:
        return "(MSIX-redirected) " + classify(m.group(1) + m.group(2) + (m.group(3) or ""))
    for pat, name in _ALLOWED:
        if re.search(pat, p):
            return "allowed: " + name
    if p.startswith(r"c:\ssbot\game\final"):
        return "VIOLATION: final (vanilla) copy"
    if re.search(r"\\locallow\\team cherry(\\|$)", p) or re.search(r"\\steam\\userdata\\", p) and "1030300" in p:
        return "VIOLATION: real saves / Steam cloud"
    if p.startswith(r"c:\ssbot\game\train"):
        return "VIOLATION: training copy outside BepInEx log/config"
    for pat, name in _MINE:
        if re.search(pat, p):
            return "mine: " + name
    for pat, name in _DRIVER:
        if re.search(pat, p):
            return "driver: " + name
    if re.search(r"\\steamapps\\(appmanifest_1030300\.acf|(shadercache|downloading|temp)\\1030300(\\|$)|"
                 r"common\\hollow knight silksong(\\|$)|workshop\\appworkshop_1030300\.acf)", p):
        # Steam updating or bookkeeping its own install of the game; the training copy runs without Steam.
        return "steam: Steam client and its own Silksong install"
    if _GAME.search(p):
        return "REVIEW: game-related name outside the sandbox"
    return "other"


def tree_snapshot(root: Path) -> dict[str, list]:
    out: dict[str, list] = {}
    if not root.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            try:
                st = p.stat()
                out[str(p)] = [st.st_size if p.is_file() else -1, st.st_mtime_ns]
            except OSError:
                pass
    return out


def tree_diff(a: dict, b: dict) -> dict:
    return {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
            "changed": sorted(k for k in set(a) & set(b) if a[k] != b[k])}


def steam_dir() -> Path | None:
    try:
        r = subprocess.run(["reg", "query", r"HKCU\Software\Valve\Steam", "/v", "SteamPath"], capture_output=True,
                           text=True, timeout=10)
        m = re.search(r"SteamPath\s+REG_SZ\s+(.+)", r.stdout)
        return Path(m.group(1).strip().replace("/", "\\")) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def whea_events(since_utc: str | None = None) -> dict:
    """WHEA-Logger events in the System log (newest 1000), or only those at/after since_utc
    ('YYYY-MM-DDTHH:MM:SS.000Z'): comparing counts before/after would be fooled by the log wrapping."""
    q = "*[System[Provider[@Name='Microsoft-Windows-WHEA-Logger']"
    q += f" and TimeCreated[@SystemTime>='{since_utc}']]]" if since_utc else "]]"
    try:
        r = subprocess.run(["wevtutil", "qe", "System", f"/q:{q}", "/f:xml", "/c:1000", "/rd:true"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": repr(e)}
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout).strip()[:300]}
    # Level 1-3 (critical/error/warning) are hardware errors (corrected ones included: ID 19 / 2 on this machine
    # before the BIOS 1836 update). Level 4 ID 3 records are informational and appear around reboots.
    events = re.findall(r"<Event .*?</Event>", r.stdout, flags=re.S)
    errors = [e for e in events if (m := re.search(r"<Level>(\d+)</Level>", e)) and int(m.group(1)) <= 3]
    def summary(es):
        return {"count": len(es), "latest": [m.group(1) for e in es[:5] if (m := re.search(r"SystemTime='([^']+)'", e))],
                "ids": dict(Counter(m.group(1) for e in es if (m := re.search(r"<EventID[^>]*>(\d+)</EventID>", e))))}
    return {"count": len(errors), "errors": summary(errors), "all": summary(events)}


def gpu_sample() -> dict | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--query-gpu=utilization.gpu,memory.used,temperature.gpu,power.draw,clocks.gr",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15)
        v = [x.strip() for x in r.stdout.strip().split(",")]
        return dict(zip(("util", "mem_mb", "temp_c", "power_w", "clock_mhz"), v)) if len(v) == 5 else {"raw": r.stdout.strip()}
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": repr(e)}


_PROCS: dict[int, object] = {}


def proc_sample(pid: int) -> dict | None:
    """Memory, handles, threads, CPU % since the previous sample of the same pid (psutil needs the same Process
    object for cpu_percent; the first sample of a pid reads 0)."""
    import psutil

    try:
        p = _PROCS.get(pid)
        if p is None:
            p = _PROCS[pid] = psutil.Process(pid)
        with p.oneshot():
            mi = p.memory_info()
            return {"rss_mb": round(mi.rss / 2**20, 1), "private_mb": round(getattr(mi, "private", 0) / 2**20, 1),
                    "handles": p.num_handles(), "threads": p.num_threads(), "cpu_pct": p.cpu_percent(None)}
    except Exception as e:  # noqa: BLE001
        _PROCS.pop(pid, None)
        return {"error": type(e).__name__}


class KillOnCloseJob:
    """A Windows job object that kills every process assigned to it when this process exits (its handle closes):
    if the supervisor dies, the games and workers go with it instead of running unattended forever."""

    def __init__(self):
        self.handle = None
        self.error: str | None = None
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._k32 = k32

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount",
                                                       "OtherOperationCount", "ReadTransferCount",
                                                       "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        h = k32.CreateJobObjectW(None, None)
        if not h:
            self.error = f"CreateJobObjectW failed ({ctypes.get_last_error()})"
            return
        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):  # ExtendedLimitInformation
            self.error = f"SetInformationJobObject failed ({ctypes.get_last_error()})"
            return
        self.handle = h

    def assign(self, proc: subprocess.Popen) -> bool:
        if self.handle is None:
            return False
        ok = bool(self._k32.AssignProcessToJobObject(self.handle, int(proc._handle)))
        if not ok:
            self.error = f"AssignProcessToJobObject failed ({ctypes.get_last_error()})"
        return ok


# =====================================================================================================================
# Supervisor
# =====================================================================================================================


def worker_command(args, i: int, out: Path, deadline: float) -> list[str]:
    """Command line of the worker process for instance i (the ability options pass through)."""
    cmd = [sys.executable, "-m", "ssbot.tools.soak", "--worker", str(i), "--out", str(out), "--deadline", f"{deadline:.0f}"]
    if getattr(args, "abilities", None):
        cmd += ["--abilities", args.abilities]
        if args.ability_tools is not None:
            cmd += ["--ability-tools", args.ability_tools]
        if args.ability_skill:
            cmd += ["--ability-skill", args.ability_skill]
    return cmd


def ability_evidence(episodes: list[dict]) -> dict:
    """Ability mode: presses, cState flag frames, clips and Spell Control states summed over all episode windows."""
    presses, cstate, clips, spell = Counter(), Counter(), Counter(), Counter()
    for e in episodes:
        presses.update(e.get("presses") or {})
        for key in ("stats_between", "stats"):
            a = (e.get(key) or {}).get("abilities") or {}
            cstate.update(a.get("cstate") or {})
            clips.update(a.get("clips") or {})
            spell.update(a.get("spell") or {})
    return {"presses": dict(presses), "cstate_frames": dict(cstate), "clips": dict(clips.most_common(30)),
            "spell_states": dict(spell.most_common(15))}


class Supervisor:
    def __init__(self, args):
        from ssbot.tools.launcher import Launcher, PrefsGuard

        self.args = args
        self.n = args.instances
        self.indices = list(range(args.first, args.first + self.n))
        stamp = datetime.now()
        self.out = Path(args.out) / f"{stamp:%Y-%m-%d}" / "SOAK" / f"soak_{stamp:%H%M%S}"
        self.out.mkdir(parents=True)
        self.log = JsonLog(self.out / "supervisor.jsonl")
        self.metrics = JsonLog(self.out / "metrics.jsonl")
        self.duration_s = args.hours * 3600 + args.minutes * 60
        self.guard = PrefsGuard.default()
        self.launcher = Launcher(width=args.width, height=args.height, guard=self.guard,
                                 log=lambda m: self.say(m))
        self.workers: dict[int, subprocess.Popen] = {}
        self.worker_logs: dict[int, object] = {}
        self.relaunches = Counter()
        self.worker_restarts = Counter()
        self.crashes: list[dict] = []
        self.down: set[int] = set()
        self.deadline = 0.0
        self.t_start = time.time()
        self.watchers: list[DirWatcher] = []
        self.snap_roots: dict[str, Path] = {}
        self.snap0: dict[str, dict] = {}
        self.job = KillOnCloseJob()
        self.loop_errors = 0

    def say(self, msg: str, **extra) -> None:
        print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)
        self.log.write(kind="log", msg=msg, **extra)

    # ---- setup ----------------------------------------------------------------------------------------------------

    def preconditions(self) -> None:
        from ssbot.tools.launcher import TRAIN_DIR, prepare_multi, running_game_pids, single_instance_enabled

        pids = running_game_pids()
        if pids:
            raise SystemExit(f"refusing: game process(es) running: {pids}")
        self.say(f"golden PlayerPrefs verified: {self.guard.verify_golden()}")
        if self.n > 1 and single_instance_enabled(TRAIN_DIR):
            self.say(prepare_multi(TRAIN_DIR))
        src = SAVES / str(self.indices[0]) / "default"
        if not (src / "user1.dat").exists():
            raise SystemExit(f"refusing: no save slot 1 in {src}")
        for i in self.indices[1:]:
            # Every instance starts from the same slot 1 as the first one: (re)copy it when missing or older.
            dst = SAVES / str(i) / "default"
            mine = dst / "user1.dat"
            if not mine.exists() or mine.stat().st_mtime < (src / "user1.dat").stat().st_mtime:
                dst.mkdir(parents=True, exist_ok=True)
                for f in src.iterdir():
                    if f.is_file():
                        shutil.copy2(f, dst / f.name)
                self.say(f"seeded sandbox saves for instance {i} from {src}")
        self.say(f"kill-on-close job: {'ok' if self.job.handle else self.job.error}")

    def start_watch(self) -> None:
        roots = [HOME, Path(r"C:\ssbot"), Path(r"C:\ProgramData")]
        steam = steam_dir()
        if steam and steam.exists():
            roots.append(steam)
        for r in roots:
            w = DirWatcher(r)
            w.start()
            self.watchers.append(w)
        time.sleep(1.0)
        self.say("write watch: " + ", ".join(f"{w.root} ({'ok' if w.started else w.error})" for w in self.watchers))
        self.snap_roots = {
            "real LocalLow/Team Cherry": HOME / r"AppData\LocalLow\Team Cherry",
            "package LocalCache/LocalLow": PACKAGE_CACHE / "LocalLow",
            "package LocalCache/Roaming": PACKAGE_CACHE / "Roaming",
            "training copy": Path(r"C:\ssbot\game\train"),
            "final copy": Path(r"C:\ssbot\game\final"),
            "Temp/Team Cherry": HOME / r"AppData\Local\Temp\Team Cherry",
        }
        if steam:
            for d in (steam / "userdata").glob("*/1030300"):
                self.snap_roots[f"Steam {d.parent.name}/1030300"] = d
        self.snap0 = {k: tree_snapshot(p) for k, p in self.snap_roots.items()}
        self.say("snapshots: " + ", ".join(f"{k} {len(v)}" for k, v in self.snap0.items()))

    # ---- instances and workers -------------------------------------------------------------------------------------

    def current(self, i: int):
        xs = [x for x in self.launcher.instances if x.index == i]
        return xs[-1] if xs else None

    def stop_game(self, x, grace_s: float = 0.0) -> None:
        """Terminate (TerminateProcess: no PlayerPrefs write), wait with a bound, release its PrefsGuard entry only
        once it is really gone (a live pid unregistered would let a golden restore race its exit)."""
        if x.proc.poll() is None:
            x.proc.terminate() if grace_s else x.proc.kill()
            for _ in range(2):
                try:
                    x.proc.wait(max(grace_s, 10.0))
                    break
                except subprocess.TimeoutExpired:
                    x.proc.kill()
        if x.proc.poll() is None:
            self.say(f"instance {x.index} (pid {x.pid}) would not exit; leaving it registered")
            return
        if not x.released:
            self.launcher._release(x)

    def launch(self, indices: list[int]) -> None:
        for attempt in range(3):
            before = len(self.launcher.instances)
            try:
                self.launcher.start(indices)
                for x in self.launcher.instances[before:]:
                    self.job.assign(x.proc)
                self.launcher.wait_ready(timeout_s=240)
                return
            except Exception as e:  # noqa: BLE001 - any failure: clean up this attempt and retry
                self.say(f"launch of {indices} failed (attempt {attempt + 1}): {type(e).__name__}: {e}")
                for x in self.launcher.instances[before:]:
                    self.job.assign(x.proc)
                    self.stop_game(x)
                    x.ready_s = x.ready_s or -1.0  # never wait on this entry again
                time.sleep(5)
        raise RuntimeError(f"could not launch {indices}")

    def start_worker(self, i: int) -> None:
        old = self.worker_logs.get(i)
        if old is not None:
            old.close()
        f = (self.out / f"worker_{i}.log").open("ab")
        self.worker_logs[i] = f
        self.workers[i] = subprocess.Popen(worker_command(self.args, i, self.out, self.deadline), cwd=str(BRAIN_DIR),
                                           stdout=f, stderr=subprocess.STDOUT)
        self.job.assign(self.workers[i])
        self.say(f"worker {i} started (pid {self.workers[i].pid})")

    def kill_worker(self, i: int) -> None:
        w = self.workers.get(i)
        if w is not None and w.poll() is None:
            w.kill()
            try:
                w.wait(30)
            except subprocess.TimeoutExpired:
                self.say(f"worker {i} (pid {w.pid}) would not exit")

    def relaunch(self, i: int, why: str) -> None:
        x = self.current(i)
        self.kill_worker(i)
        if x is not None:
            self.stop_game(x)
            tail = ""
            try:
                tail = "".join(x.log.read_text(encoding="utf-8", errors="replace").splitlines(True)[-40:])
            except OSError:
                pass
            self.crashes.append({"instance": i, "t": now_iso(), "why": why, "pid": x.pid, "exit_code": x.proc.returncode,
                                 "log_tail": tail})
        self.relaunches[i] += 1
        if self.relaunches[i] > MAX_RELAUNCH:
            self.down.add(i)
            self.say(f"instance {i}: {why}; relaunch limit reached, leaving it down")
            return
        if x is not None and x.proc.poll() is None:
            self.down.add(i)  # stop_game left it registered: a new instance with this id would be refused
            self.say(f"instance {i}: {why}; the old game would not exit, leaving it down")
            return
        self.say(f"instance {i}: {why}; relaunching ({self.relaunches[i]})")
        try:
            self.launch([i])
            self.start_worker(i)
        except (Exception, SystemExit) as e:  # noqa: BLE001 - PrefsGuard refuses with SystemExit
            self.down.add(i)
            self.say(f"instance {i}: relaunch failed ({type(e).__name__}: {e}); leaving it down")

    def poll(self) -> None:
        for i in self.indices:
            if i in self.down:
                continue
            x = self.current(i)
            w = self.workers.get(i)
            if x is None or x.proc.poll() is not None:
                self.relaunch(i, f"game exited (code {x.proc.returncode if x else None})")
                continue
            if w is not None and w.poll() is not None:
                code = w.returncode
                if code in (EXIT_HANG, EXIT_STUCK):
                    self.relaunch(i, f"worker reported {'hang' if code == EXIT_HANG else 'stuck'} (exit {code})")
                elif code == EXIT_LINK_CLOSED:
                    self.relaunch(i, "oracle link closed with the game still running")
                elif time.time() < self.deadline - 60:
                    self.worker_restarts[i] += 1
                    self.say(f"worker {i} exited with {code}; restarting it ({self.worker_restarts[i]})")
                    if self.worker_restarts[i] > MAX_RELAUNCH:
                        self.relaunch(i, "worker keeps failing")
                    else:
                        self.start_worker(i)

    def sample(self) -> None:
        rec = {"kind": "sample", "elapsed_s": round(time.time() - self.t_start), "gpu": gpu_sample(),
               "instances": {}}
        for i in self.indices:
            x = self.current(i)
            if x is not None and x.proc.poll() is None:
                rec["instances"][i] = {"pid": x.pid, **(proc_sample(x.pid) or {})}
        self.metrics.write(**rec)
        status = {"t": now_iso(), "out": str(self.out), "deadline": datetime.fromtimestamp(self.deadline).isoformat(),
                  "relaunches": dict(self.relaunches), "worker_restarts": dict(self.worker_restarts),
                  "down": sorted(self.down), "last_sample": rec}
        (self.out / "status.json").write_text(json.dumps(status, indent=1, default=str), encoding="utf-8")

    # ---- run -------------------------------------------------------------------------------------------------------

    def run(self) -> int:
        self.say(f"soak: {self.n} instance(s) {self.indices}, {self.duration_s / 3600:.2f} h, out {self.out}"
                 + (f", abilities {self.args.abilities}" if getattr(self.args, "abilities", None) else ""))
        (self.out / "args.json").write_text(json.dumps(vars(self.args), indent=1), encoding="utf-8")
        self.preconditions()
        whea0 = whea_events()
        self.say(f"WHEA events before: {whea0}")
        self.start_watch()
        from ssbot.tools.launcher import current_prefs
        t_start = self.t_start = time.time()
        stop = self.out / "STOP"
        prefs_running = None
        self.aborted: str | None = None
        # Keep the display and the machine awake: the power plan turns the display off after 10 minutes idle, and
        # what 4 VSync'd windowed instances do with the display off is not what training will see.
        es = ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
        self.say(f"keep-awake (system + display): {'ok' if es else 'FAILED'}")
        try:
            self.launcher.preflight(self.indices)
            self.deadline = time.time() + self.duration_s + 180  # workers get their startup on top
            self.launch(self.indices)
            for i in self.indices:
                self.start_worker(i)
            next_sample = 0.0
            while time.time() < self.deadline and not stop.exists():
                try:  # one bad poll or sample must not end a 12 h run
                    self.poll()
                    if time.time() >= next_sample:
                        next_sample = time.time() + 60
                        self.sample()
                except Exception as e:  # noqa: BLE001
                    self.loop_errors += 1
                    self.say(f"supervisor loop error ({self.loop_errors}): {type(e).__name__}: {e}",
                             tb=traceback.format_exc())
                    if self.loop_errors > 50:
                        raise
                if len(self.down) == self.n:
                    self.say("every instance is down; ending early")
                    break
                time.sleep(5)
            self.say("stopping: " + ("deadline" if time.time() >= self.deadline else "STOP file / all down"))
        except KeyboardInterrupt:
            self.aborted = "interrupted"
            self.say("interrupted")
        except BaseException as e:  # noqa: BLE001 - still stop everything and write the report
            self.aborted = f"{type(e).__name__}: {e}"
            self.say(f"soak aborted: {self.aborted}", tb=traceback.format_exc())
        finally:
            stop.touch()
            end_wait = time.time() + 300
            for i, w in self.workers.items():
                try:
                    w.wait(max(1.0, end_wait - time.time()))
                except subprocess.TimeoutExpired:
                    self.say(f"worker {i} did not stop; killing it")
                    self.kill_worker(i)
            try:
                # Unity writes PlayerPrefs on a clean exit or PlayerPrefs.Save; the instances are killed below, so
                # anything different from golden now was written while they ran.
                prefs_running = current_prefs(self.guard.store)
            except Exception as e:  # noqa: BLE001
                prefs_running = {"error": repr(e)}
            for x in list(self.launcher.instances):
                try:
                    self.stop_game(x, grace_s=15)
                except Exception as e:  # noqa: BLE001
                    self.say(f"could not stop instance {x.index}: {e}")
            for f in self.worker_logs.values():
                f.close()
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # ES_CONTINUOUS alone: back to normal
        time.sleep(3)
        try:
            return self.report(t_start, whea0, prefs_running)
        except Exception as e:  # noqa: BLE001 - leave at least the raw material and the reason
            self.say(f"report failed: {type(e).__name__}: {e}", tb=traceback.format_exc())
            return 2

    # ---- report ----------------------------------------------------------------------------------------------------

    def report(self, t_start: float, whea0: dict, prefs_running) -> int:
        from ssbot.tools.launcher import current_prefs, prefs_diff, read_reg_file

        golden = read_reg_file(self.guard.golden)
        prefs_after = current_prefs(self.guard.store)
        whea1 = whea_events()
        since_utc = datetime.fromtimestamp(t_start, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        whea_new = whea_events(since_utc=since_utc)
        watch = [w.result(freeze=True) for w in self.watchers]
        snap1 = {k: tree_snapshot(p) for k, p in self.snap_roots.items()}
        snap_diff = {k: tree_diff(self.snap0.get(k, {}), snap1.get(k, {})) for k in self.snap_roots}

        by_class: dict[str, list] = {}
        for w in watch:
            for p, info in w["paths"].items():
                by_class.setdefault(classify(p, info["actions"]), []).append((p, info))
        for k, d in snap_diff.items():
            for kind in ("added", "removed", "changed"):
                for p in d[kind]:
                    is_dir = (snap1.get(k, {}).get(p) or self.snap0.get(k, {}).get(p) or [0])[0] == -1
                    c = "dir metadata (a child changed)" if kind == "changed" and is_dir else classify(p)
                    by_class.setdefault(c, []).append((p, {"snapshot": f"{k}: {kind}"}))
        violations = {c: sorted(v, key=lambda x: x[0]) for c, v in by_class.items() if "VIOLATION" in c or "REVIEW" in c}
        review = {c: v for c, v in violations.items() if "REVIEW" in c}

        # Recordings of killed workers never got a "segment" line: check them from disk (the reader rebuilds what
        # it can from the chunks written before the kill).
        from ssbot.record.recorder import RecordingReader
        logged = set()
        for i in self.indices:
            p = self.out / f"worker_{i}.jsonl"
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if '"segment' in line:
                        try:
                            logged.add(str(Path(json.loads(line).get("path") or "")))
                        except json.JSONDecodeError:
                            pass
        orphan_segments = []
        for d in sorted(RUNS.glob(f"*/SOAK/{self.out.name}_i*_s*")):
            if str(d) in logged:
                continue
            try:
                c = RecordingReader(d).check().as_dict()
                orphan_segments.append({"path": str(d), "delivery": c.get("delivery"), "expected": c.get("expected"),
                                        "missing": c.get("missing"), "ok": c.get("ok")})
            except Exception as e:  # noqa: BLE001
                orphan_segments.append({"path": str(d), "error": repr(e)})

        episodes, segments, exits, notes, reset_errors, segment_errors, grants = [], [], [], [], [], [], []
        for i in self.indices:
            p = self.out / f"worker_{i}.jsonl"
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                r["instance"] = i
                {"episode": episodes, "segment": segments, "exit": exits, "note": notes, "reset_error": reset_errors,
                 "segment_error": segment_errors, "abilities": grants}.get(r.get("kind"), []).append(r)
        # A reset is the whole savestate.load step as training sees it: retries and unpausing included.
        resets = [e["reset_total_ms"] for e in episodes if "reset_total_ms" in e]
        same = [e["reset_total_ms"] for e in episodes if "reset_total_ms" in e and not e.get("cross_scene")]
        cross = [e["reset_total_ms"] for e in episodes if "reset_total_ms" in e and e.get("cross_scene")]
        over = [e for e in episodes if e.get("reset_total_ms", 0) > RESET_LIMIT_MS]
        interrupted = [e for e in episodes if e.get("interrupted")]
        lost_total = 0
        for i in self.indices:  # lost_events is cumulative per game process: sum the last value of each process run
            last_by_run, run = {}, 0
            for e in episodes:
                if e["instance"] != i or not e.get("input"):
                    continue
                v = e["input"].get("lost_events") or 0
                if v < last_by_run.get(run, 0):
                    run += 1
                last_by_run[run] = v
            lost_total += sum(last_by_run.values())
        ev = Counter()
        hitches = frames = gaps = play_frames = 0
        udt_sum = 0.0
        hourly: dict[int, list] = {}  # hour since start -> [(udt_mean, play_frames, udt_p99)]
        death_kinds = ("hero_dead", "player_dead", "permadeath_dead")
        dead = []
        for e in episodes:
            for key in ("stats_between", "stats"):
                st = e.get(key) or {}
                ev.update(st.get("events") or {})
                hitches += st.get("hitches", 0)
                frames += st.get("frames", 0)
                gaps += st.get("gaps", 0)
                if st.get("dead_seen") or any((st.get("events") or {}).get(k) for k in death_kinds):
                    dead.append({k: e.get(k) for k in ("instance", "ep", "t", "scene_end")})
                if st.get("play_frames") and st.get("udt_mean_ms") is not None:
                    play_frames += st["play_frames"]
                    udt_sum += st["udt_mean_ms"] * st["play_frames"]
                    try:
                        h = int((datetime.fromisoformat(e["t"]).timestamp() - t_start) // 3600)
                    except (KeyError, ValueError):
                        h = -1
                    hourly.setdefault(h, []).append((st["udt_mean_ms"], st["play_frames"], st.get("udt_p99_ms")))
        frame_time = {"mean_ms": round(udt_sum / play_frames, 3) if play_frames else None, "hourly": {
            h: {"mean_ms": round(sum(m * n for m, n, _ in xs) / max(1, sum(n for _, n, _ in xs)), 3),
                "p99_ms_max_episode": max((p for _, _, p in xs if p is not None), default=None),
                "frames": sum(n for _, n, _ in xs)} for h, xs in sorted(hourly.items())}}
        lost = {}
        for e in episodes:
            if e.get("input"):
                lost[e["instance"]] = e["input"].get("lost_events")
        idle_gaps = []
        for i in self.indices:
            ts = sorted(datetime.fromisoformat(e["t"]).timestamp() for e in episodes if e["instance"] == i and e.get("t"))
            edges = [t_start + 600] + ts + [time.time() - 300]  # 10 min for startup; the last few minutes are shutdown
            for a, b in zip(edges, edges[1:]):
                if b - a > 600:
                    idle_gaps.append({"instance": i, "from": datetime.fromtimestamp(a).isoformat(timespec="seconds"),
                                      "to": datetime.fromtimestamp(b).isoformat(timespec="seconds"),
                                      "minutes": round((b - a) / 60, 1)})
        seg_rows = segments + orphan_segments
        # Delivery is an M1 metric over ~60 min: a short segment (the tail before the deadline, or one cut by a
        # relaunch) is folded into the previous segment of the same instance before the 99.9 % comparison.
        judged: list[dict] = []
        by_inst: dict[str, list] = {}
        for s in seg_rows:
            m = re.search(r"_i(\d+)_s(\d+)_", s.get("path") or "")
            if m and s.get("expected"):
                by_inst.setdefault(m.group(1), []).append((int(m.group(2)), s))
        for inst, xs in by_inst.items():
            acc = None
            for _, s in sorted(xs, key=lambda t: t[0]):
                exp, miss = int(s.get("expected") or 0), int(s.get("missing") or 0)
                if acc is not None and exp < 30 * 60 * 60:
                    acc["expected"] += exp
                    acc["missing"] += miss
                    acc["folded"] += 1
                    continue
                acc = {"instance": inst, "first": s.get("path"), "expected": exp, "missing": miss, "folded": 0}
                judged.append(acc)
        for j in judged:
            j["delivery"] = (j["expected"] - j["missing"]) / j["expected"] if j["expected"] else None
        deliveries = [j["delivery"] for j in judged if j["delivery"] is not None]
        bad_segments = [s for s in seg_rows if s.get("delivery") is None or s.get("ok") is False
                        or s.get("error") or s.get("continuity_error")] + segment_errors
        mem = self.memory_trend()

        def pct(xs, q):
            xs = sorted(xs)
            return round(xs[min(len(xs) - 1, int(len(xs) * q))], 1) if xs else None

        checks = {
            "no crashes or hangs": not self.crashes,
            "all instances up at the end": not self.down,
            "delivery >= 99.9 % in every segment (killed workers' recordings included)":
                bool(deliveries) and min(deliveries) >= 0.999 and not bad_segments,
            "reset <= 2 s (every reset, retries and cross-scene loads included)": bool(resets) and not over,
            "no failed savestate.load": not reset_errors,
            "no brain-lost events (workers kept up at 60 Hz)": lost_total == 0,
            "no death seen (LethalBlock blocks every lethal hit)": not dead,
            "0 writes outside the sandbox (no VIOLATION paths; every watcher ran without overflow)":
                not any("VIOLATION" in c for c in violations)
                and all(w["started"] and not w["error"] and not w["overflows"] for w in watch),
            "PlayerPrefs unchanged while running (vs golden; Unity's Screenmanager keys excepted)":
                isinstance(prefs_running, dict) and "error" not in prefs_running
                and not [k for k in prefs_diff(prefs_running, golden) if not k.startswith(SCREEN_PREFS)],
            "golden PlayerPrefs restore succeeded": not prefs_diff(prefs_after, golden),
            "no game-related writes left to review (REVIEW paths)": not review,
            "no memory growth > 100 MB/h in any game process (runs >= 2 h)":
                self.duration_s < 7200 or all(m["mb_per_hour"] <= 100 for m in mem.values() if m["samples"] >= 60),
            "ran to the end (not aborted)": not getattr(self, "aborted", None),
            "no worker failures (every exit clean, no restarts)":
                not self.worker_restarts and all(x.get("code") == 0 for x in exits),
            "every instance kept producing episodes (no gap > 10 min)": not idle_gaps,
            "no WHEA hardware errors during the run": "error" not in whea_new and whea_new.get("count") == 0,
        }
        abilities = getattr(self.args, "abilities", None)
        if abilities:
            checks[f"abilities '{abilities}' granted and seen in STATE on every instance (every worker start)"] = (
                set(self.indices) <= {g["instance"] for g in grants} and all(g.get("ok") for g in grants))
        rep = {
            "out": str(self.out), "started": datetime.fromtimestamp(t_start).isoformat(timespec="seconds"),
            "ended": now_iso(), "hours": round((time.time() - t_start) / 3600, 2), "instances": self.indices,
            "checks": checks, "pass": all(checks.values()), "aborted": getattr(self, "aborted", None),
            "supervisor_loop_errors": self.loop_errors, "job": self.job.error or "ok",
            "episodes": len(episodes), "episodes_per_instance": dict(Counter(e["instance"] for e in episodes)),
            "reset_ms": {"n": len(resets), "p50": pct(resets, 0.5), "p99": pct(resets, 0.99), "max": max(resets) if resets else None,
                         "same_scene": {"n": len(same), "p50": pct(same, 0.5), "p99": pct(same, 0.99), "max": max(same) if same else None},
                         "cross_scene": {"n": len(cross), "p50": pct(cross, 0.5), "p99": pct(cross, 0.99), "max": max(cross) if cross else None},
                         "over_2s": [{k: e.get(k) for k in ("instance", "ep", "t", "reset_total_ms", "reset_wall_ms", "attempts",
                                                            "scene_before", "cross_scene", "transition_before", "reset")} for e in over[:20]],
                         "errors": reset_errors[:50]},
            "brain_lost_events": lost_total, "episodes_interrupted_by_pause": len(interrupted), "idle_gaps": idle_gaps,
            "frames_seen_by_workers": frames, "worker_seen_gaps": gaps, "hitches_over_25ms_in_gameplay": hitches,
            "frame_time_steady_gameplay": frame_time,
            "segments": [{k: s.get(k) for k in ("instance", "path", "delivery", "expected", "received", "missing", "ok", "drops", "error")} for s in seg_rows],
            "bad_segments": bad_segments[:50], "delivery_windows": judged,
            "events": dict(ev), "deaths_seen": dead[:50], "brain_lost_events_last": lost,
            "crashes": self.crashes, "relaunches": dict(self.relaunches), "worker_restarts": dict(self.worker_restarts),
            "worker_exits": exits, "notes": notes[:50],
            "memory": mem,
            "whea": {"before": whea0, "after": whea1, "during_run": whea_new, "since_utc": since_utc},
            "prefs": {"diff_while_running_vs_golden": prefs_diff(prefs_running, golden) if isinstance(prefs_running, dict) and "error" not in prefs_running else prefs_running,
                      "diff_after_restore_vs_golden": prefs_diff(prefs_after, golden)},
            "writes": {"watchers": [{k: w[k] for k in ("root", "started", "error", "overflows")} | {"paths": len(w["paths"])} for w in watch],
                       "by_class_counts": {c: len(v) for c, v in sorted(by_class.items())},
                       "violations_and_review": {c: [[p, i] for p, i in v[:200]] for c, v in violations.items()},
                       "snapshot_diff": snap_diff},
        }
        if abilities:
            rep["abilities"] = {
                "mode": abilities, "evidence": ability_evidence(episodes),
                "grants": [{k: g.get(k) for k in ("instance", "t", "ok", "error", "gaps", "request", "keys", "macros")}
                           | {k: (g.get("grant") or {}).get(k) for k in ("changed", "unplaced", "bindings", "slots", "config")}
                           for g in grants]}
        (self.out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        other = sorted(by_class.get("other", []), key=lambda x: -x[1].get("count", 1) if isinstance(x[1], dict) else 0)
        (self.out / "writes_other.json").write_text(json.dumps([[p, i] for p, i in other[:5000]], indent=0, default=str), encoding="utf-8")
        lines = [f"SOAK {'PASS' if rep['pass'] else 'FAIL'}  {rep['hours']} h, instances {self.indices}, {len(episodes)} episodes",
                 *[f"  {'PASS' if ok else 'FAIL'}  {name}" for name, ok in checks.items()],
                 f"  reset ms p50 {rep['reset_ms']['p50']} p99 {rep['reset_ms']['p99']} max {rep['reset_ms']['max']} (n {len(resets)}); "
                 f"same scene {rep['reset_ms']['same_scene']}; cross scene {rep['reset_ms']['cross_scene']}",
                 f"  brain-lost events {lost_total}; episodes cut short by a pause {len(interrupted)}; failed loads {len(reset_errors)}",
                 f"  delivery per segment: min {min(deliveries) if deliveries else None} over {len(deliveries)} segments",
                 f"  hitches > {HITCH_MS} ms in steady gameplay: {hitches} of {play_frames} frames; frame time {json.dumps(frame_time)}",
                 f"  events {dict(ev)}; crashes {len(self.crashes)}, relaunches {dict(self.relaunches)}, worker restarts {dict(self.worker_restarts)}",
                 f"  memory: {json.dumps(mem)}",
                 f"  WHEA hardware errors during the run: {whea_new.get('count', whea_new)} (all-time {whea1.get('count')})",
                 f"  writes by class: {rep['writes']['by_class_counts']}",
                 *[f"  {c}: {p}  {i}" for c, v in violations.items() for p, i in v[:30]]]
        if abilities:
            ev = rep["abilities"]["evidence"]
            lines += [f"  abilities {abilities}: grants ok {sum(1 for g in grants if g.get('ok'))}/{len(grants)}; "
                      f"presses {ev['presses']}; cState frames {ev['cstate_frames']}",
                      f"  abilities: spell states {ev['spell_states']}; clips {ev['clips']}",
                      *[f"  abilities i{g['instance']}: {g.get('error') or g.get('gaps') or 'ok'}; bindings "
                        f"{(g.get('grant') or {}).get('bindings')}; unplaced {(g.get('grant') or {}).get('unplaced')}"
                        for g in grants]]
        (self.out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines), flush=True)
        return 0 if rep["pass"] else 1

    def memory_trend(self) -> dict:
        """Per instance and pid: private MB in the first and the last sampled hour (or the first/last 20 %)."""
        rows = []
        p = self.out / "metrics.jsonl"
        if not p.exists():
            return {}
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        out = {}
        series: dict[tuple, list] = {}
        for r in rows:
            for i, d in (r.get("instances") or {}).items():
                if "private_mb" in d:
                    series.setdefault((i, d["pid"]), []).append((r["elapsed_s"], d["private_mb"], d.get("handles")))
        for (i, pid), xs in series.items():
            if len(xs) < 5:
                continue
            # Least-squares slope of private MB over time (the first 10 minutes skipped: the game settles).
            ys = [x for x in xs if x[0] - xs[0][0] >= 600] or xs
            n = len(ys)
            tm = sum(x[0] for x in ys) / n
            mm = sum(x[1] for x in ys) / n
            var = sum((x[0] - tm) ** 2 for x in ys)
            slope_h = (sum((x[0] - tm) * (x[1] - mm) for x in ys) / var * 3600) if var > 0 else 0.0
            out[f"i{i}/pid{pid}"] = {"samples": len(xs), "private_mb_first": xs[0][1], "private_mb_last": xs[-1][1],
                                     "private_mb_max": max(x[1] for x in xs), "mb_per_hour": round(slope_h, 1),
                                     "handles_first": xs[0][2], "handles_last": xs[-1][2]}
        return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", type=int, default=4)
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--hours", type=float, default=0.0)
    ap.add_argument("--minutes", type=float, default=0.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--out", default=str(RUNS))
    ap.add_argument("--abilities", choices=ABILITY_MODES,
                    help="grant these abilities before each worker's savestate and play with their keys (see above)")
    ap.add_argument("--ability-tools", metavar="NAMES",
                    help='comma-separated ToolItem names for combat/all ("" = none; default one of '
                         f'{", ".join(TOOL_ROTATION)} by instance)')
    ap.add_argument("--ability-skill", metavar="NAME",
                    help=f"silk skill to equip for combat/all (default one of {', '.join(SKILL_ROTATION)} by instance)")
    ap.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--deadline", type=float, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if (args.ability_tools is not None or args.ability_skill) and args.abilities not in ("combat", "all"):
        ap.error("--ability-tools and --ability-skill need --abilities combat or all")
    if args.ability_skill and args.ability_skill.lower() not in {n.lower() for kv in SKILLS.items() for n in kv}:
        ap.error(f"--ability-skill must be one of {', '.join(f'{k} ({v})' for k, v in SKILLS.items())}")
    if args.worker is None and args.hours <= 0 and args.minutes <= 0:
        ap.error("give --hours and/or --minutes")
    return args


def main() -> int:
    args = parse_args()
    if args.worker is not None:
        return Worker(args).run()
    return Supervisor(args).run()


if __name__ == "__main__":
    sys.exit(main())
