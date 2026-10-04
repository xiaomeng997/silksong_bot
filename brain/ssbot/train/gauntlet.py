"""Multi-wave arena fights (M2 W8, the High Halls Forum): which wave runs, who killed what, and when the gauntlet is over.

A gauntlet is one BattleScene component (1.0.30000 BattleScene.cs) that runs a list of BattleWaves itself: StartWave(i)
activates wave i's enemies after its startDelay and adds them to currentEnemies; HealthManager.Die calls
DecrementEnemy (DecrementBigEnemy: the same 1 s later); when currentEnemies drops to the wave's remainingEnemyToEnd the
next wave starts, after the last one EndBattle (FreezeMoment EnemyBattleEndSlow unless noEndSlomo, then 3 s later the
PlayerData bool setPDBoolOnEnd, Forum: hang04Battle, and the "battleEndEventRegister" event). The waves of the Forum
(Hang_04_boss, scene bundle, docs/facts/1.0.30000/forum.md) are in ssbot.train.encounters.FORUM_WAVES.

Sources, best first (GauntletTap):
  room.battles   oracle STATE (SceneDump.BattleWatch, commit 788aaa8; absent before that oracle is deployed): the
                 BattleScene's own wave index, started / completed and enemy count. Exact.
  kills          "hit" events with dead true (every source: the hero, helpers, Cogflies), replayed through the
                 BattleScene's wave rules on the known wave list (WaveSim: DecrementEnemy on each death of a wave
                 member, and the enemy-count check 1 s after each wave's activation).
  spawns         the FSM start ("fsm" event with from None) of a wave-0 enemy GameObject whose name no later wave
                 reuses (they are inactive until StartWave(0)) marks the battle start when room.battles is absent.
  end            freeze "EnemyBattleEndSlow" after the start, or the sim finishing the last wave: CLEAR.

Allies (STATE "allies", Entities.AllyWatch, commit cd215cc) are recorded when present; their kills are counted from
the "hit" events (src is the attacker's object name).
"""
import threading
from dataclasses import dataclass

from ssbot.ipc.ents import SRC_BITS


def type_key(name: str | None) -> str:
    """The oracle's EntityRegistry.TypeKey: a GameObject name without trailing " (n)" and "(Clone)" suffixes."""
    if not name:
        return name or ""
    s = name
    while True:
        s = s.rstrip(" ")
        if s.endswith("(Clone)"):
            s = s[:-7]
            continue
        if s.endswith(")"):
            i = s.rfind("(")
            if i >= 0 and i < len(s) - 2 and s[i + 1:-1].isdigit():
                s = s[:i]
                continue
        break
    return s or name


@dataclass(frozen=True)
class Wave:
    index: int                      # position in BattleScene.waves
    name: str                       # the BattleWave GameObject
    start_delay_s: float
    remaining_to_end: int           # BattleWave.remainingEnemyToEnd
    enemies: tuple[str, ...]        # GameObject names of its HealthManager children
    big: tuple[str, ...] = ()       # of those, the ones whose death is reported 1 s late (bigEnemyDeath)

    @property
    def types(self) -> tuple[str, ...]:
        return tuple(type_key(n) for n in self.enemies)


CHECK_AFTER_F = 60     # BattleScene.StartWave: DoCheckEnemies 1 s after a wave's enemies are activated


class WaveSim:
    """BattleScene's wave rules replayed from kills: start(f) at the battle's first wave, kill(f) per death of a wave
    member, advance(f) as time passes (every STATE).

    StartWave(i) (BattleScene.cs:311) activates wave i after its startDelay (currentWave = i, enemiesToNext =
    remainingEnemyToEnd) and checks the enemy count 1 s later (DoCheckEnemies: the wave transforms' child count, which
    is the number of wave members still alive); DecrementEnemy on a death checks at once. Either check ends the wave
    when the count is <= enemiesToNext: StartWave(i + 1), or EndBattle after the last. A wave whose own size is within
    its remainingEnemyToEnd (Forum index 2: 2 enemies, 2) therefore ends 1 s after its activation, not with it (run
    20261002_231917 ep0: the Clawmaiden of index 3 activated at 59.77 s, index 2 at 58.03 s, + 1.0 s check + 0.5 s
    startDelay). A wave end while the next StartWave is still in its startDelay (a second kill of an overlapping wave)
    makes the game run StartWave(i + 1) a second time; its members are counted once by the child count, so the sim
    ignores it."""

    def __init__(self, waves: tuple[Wave, ...]):
        self.waves = waves
        self.wave = -1                               # BattleScene.currentWave (set at a wave's activation)
        self.alive = 0
        self.to_next = 0
        self.done = False
        self.starts: list[tuple[int, int]] = []      # (wave index, frame its enemies were activated), in time order
        self.end_frame: int | None = None
        self._queued: tuple[int, int] | None = None  # (wave index, activation frame) of a StartWave in its delay
        self._checks: list[tuple[int, int]] = []     # (frame, wave) of pending DoCheckEnemies

    def start(self, f: int) -> None:
        if self.wave < 0 and self._queued is None and not self.done:
            self._queue(0, f)
            self.advance(f)

    def _queue(self, i: int, f: int) -> None:
        if self._queued is None:
            self._queued = (i, f + round(self.waves[i].start_delay_s * 60))

    def _wave_end(self, f: int) -> None:
        if self.wave >= len(self.waves) - 1:
            self.done = True
            self.end_frame = f
        else:
            self._queue(self.wave + 1, f)

    def advance(self, f: int) -> None:
        """Run the activations and 1 s checks due by frame f, in time order."""
        while not self.done:
            nxt = []
            if self._queued is not None and self._queued[1] <= f:
                nxt.append((self._queued[1], 0))
            due = [c for c in self._checks if c[0] <= f]
            if due:
                nxt.append((min(due)[0], 1))
            if not nxt:
                return
            fe, kind = min(nxt)
            if kind == 0:
                i, fa = self._queued
                self._queued = None
                w = self.waves[i]
                self.wave = i
                self.alive += len(w.enemies)
                self.to_next = w.remaining_to_end
                self.starts.append((i, fa))
                self._checks.append((fa + CHECK_AFTER_F, i))
            else:
                c = min(due)
                self._checks.remove(c)
                if self.alive <= self.to_next:
                    self._wave_end(fe)

    def kill(self, f: int) -> None:
        if self.done or (self.wave < 0 and self._queued is None):
            return
        self.advance(f)
        if self.done:
            return
        self.alive -= 1
        if self.wave >= 0 and self.alive <= self.to_next:
            self._wave_end(f)
            self.advance(f)


DEAD_REPEAT_F = 60     # a second dead "hit" of one entity within this many frames is the same death


class GauntletTap:
    """FightTap's counterpart for a gauntlet (same interface for ssbot.train.episode.run_episode): wake_frame = the
    battle start, death_frame = the gauntlet finished (CLEAR), plus waves, kills and per-type FSM state entries. Fed by
    every STATE (OracleLink.subscribe_state, reader thread); reset() starts a new episode."""

    def __init__(self, link, enc):
        self.enc = enc
        self._lock = threading.Lock()
        # wave 0's enemy GameObjects whose name no later wave reuses (Forum: "Song Reed" is also wave 12's, which is
        # active from the load and runs its FSM before the battle); their FSM start (from None) is the activation
        later = {n for w in enc.waves[1:] for n in w.enemies}
        self._wave0 = set(enc.waves[0].enemies) - later if enc.waves else set()
        # only wave members count for DecrementEnemy: the Maestro's summoned "Song Automaton Tiny" also die with a
        # "hit" event (run 20261002_221727 i2 ep0: 6 of 28 kills), and counting them ended the sim's last wave early
        self._wave_types = {t for w in enc.waves for t in w.types}
        self.reset()
        link.subscribe_state(self._on)

    def reset(self) -> None:
        with self._lock:
            self.control: str | None = None
            self.control_log: list[tuple[int, str | None, str]] = []
            self.wake_frame: int | None = None
            self.death_frame: int | None = None
            self.end_source: str | None = None
            self.damage: list[tuple[int, dict]] = []
            self.lethal: list[tuple[int, str, dict]] = []
            self.freezes: list[dict] = []
            self.hp: list[tuple[int, dict]] = []
            self.other: list[tuple[int, str, dict]] = []
            self.kills: list[tuple[int, str, str | None]] = []     # (frame, type_key, src)
            self._dead: dict[int, int] = {}                       # ent -> frame of its last counted death
            self.state_entries: dict[str, int] = {}               # "<type>/<fsm>/<state>" -> entries
            self.sim = WaveSim(self.enc.waves)
            self.waves_exact: list[tuple[int, int]] = []          # (wave index, frame) from room.battles
            self.battle_seen = False                              # room.battles present in this oracle
            self.allies_seen: dict[str, int] = {}                 # ally name -> frames active and not dormant
            self.ally_first: dict[str, int] = {}                  # ally name -> first such frame

    @property
    def waves(self) -> list[tuple[int, int]]:
        return list(self.waves_exact) if self.battle_seen else list(self.sim.starts)

    @property
    def wave(self) -> int:
        w = self.waves
        return w[-1][0] if w else -1

    def _start(self, f: int, why: str) -> None:
        if self.wake_frame is None:
            self.wake_frame = f
            self.control = why
            self.control_log.append((f, None, why))

    def rebase_start(self, f: int, why: str) -> None:
        """Move the battle start (wake_frame) and the first wave's frame to `f`: a wave-start savestate's battle reports
        its wave from the battle start, startDelay before the members are activated (ssbot.train.wave_start), so
        its intro calls this with the activation frame; wave times then mean the same as in a full gauntlet."""
        with self._lock:
            if self.wake_frame is None or f < self.wake_frame:
                return
            self.control_log.append((f, self.control, f"REBASE {why} from {self.wake_frame}"))
            self.wake_frame = f
            if self.waves_exact:
                w, f0 = self.waves_exact[0]
                if f0 < f:
                    self.waves_exact[0] = (w, f)

    def _end(self, f: int, why: str) -> None:
        if self.death_frame is None and self.wake_frame is not None:
            self.death_frame = f
            self.end_source = why
            self.control_log.append((f, self.control, "END " + why))

    def _on(self, s: dict) -> None:
        f = s["f"]
        room = s.get("room") or {}
        battles = room.get("battles")
        allies = s.get("allies")
        evs = s.get("ev")
        if self.wake_frame is not None and not self.battle_seen and not self.sim.done:
            with self._lock:
                self.sim.advance(f)        # wave activations and 1 s checks due by now, in time order
                if self.sim.done:
                    self._end(self.sim.end_frame, "kills")
        if not evs and battles is None and not allies:
            return
        with self._lock:
            if battles:
                b = next((x for x in battles if x.get("name") == self.enc.battle_name), battles[0])
                if "wave" in b:
                    self.battle_seen = True
                    if b["started"] or b["completed"]:
                        self._start(f, "room.battles")
                        if b["started"] and (not self.waves_exact or self.waves_exact[-1][0] != b["wave"]):
                            self.waves_exact.append((b["wave"], f))
                    if b["completed"]:
                        self._end(f, "room.battles")
            for a in allies or ():
                # "Away": Shakra Fighter's state when she was not called (every Forum load with the Garmond flag;
                # forum.md §4), counted as a helper before 2026-10-04 (R1: the wave-start records)
                if a.get("active") and a.get("state") not in (None, "Dormant", "Init", "Wait Hero In Position",
                                                               "Wait An Additional Frame", "Auto Target?", "Away"):
                    n = a.get("name") or "?"
                    self.allies_seen[n] = self.allies_seen.get(n, 0) + 1
                    self.ally_first.setdefault(n, f)
            for ev in evs or ():
                k = ev.get("k")
                d = ev.get("d") or {}
                if k == "fsm":
                    obj = d.get("obj")
                    if (self.wake_frame is None and obj in self._wave0 and d.get("from") is None
                            and not self.battle_seen):
                        self._start(f, "wave0 spawn")
                        self.sim.start(f)
                    if self.wake_frame is not None and d.get("to"):
                        key = f"{type_key(obj)}/{d.get('fsm')}/{d['to']}"
                        self.state_entries[key] = self.state_entries.get(key, 0) + 1
                elif k == "hit":
                    if self._new_death(f, d):
                        self.kills.append((f, d.get("type_key"), d.get("src")))
                        if self.wake_frame is not None and d.get("type_key") in self._wave_types:
                            if self.sim.wave < 0:
                                self.sim.start(self.wake_frame)
                            self.sim.kill(f)
                            if self.sim.done and not self.battle_seen:
                                self._end(f, "kills")
                elif k == "damage":
                    self.damage.append((f, d))
                elif k in ("catastrophe", "would_die"):
                    self.lethal.append((f, k, d))
                elif k == "freeze":
                    if d.get("phase") == "start":
                        self.freezes.append({"f": f, **d})
                        if d.get("type") == "EnemyBattleEndSlow" and not self.battle_seen:
                            self._end(f, "freeze")
                elif k == "hp":
                    self.hp.append((f, d))
                elif k in ("special_damage", "hazard_respawn", "hazard_death", "die", "hero_dead", "player_dead",
                           "gs", "scene_leave"):
                    self.other.append((f, k, d))

    def _new_death(self, f: int, d: dict) -> bool:
        """A "hit" with dead that is a new death: the hit took the enemy from hp > 0 (every dead hit of the four
        Forum runs of 2026-10-02 did), and not a repeat report of the same entity within DEAD_REPEAT_F. The Maestro's
        pooled "Song Automaton Tiny" come back under the same iid (run 20261002_231917 ep0: -693612 died 4 times,
        907+ frames apart), so an iid may die again."""
        if not d.get("dead"):
            return False
        hp0 = d.get("hp_before")
        if hp0 is not None and hp0 <= 0:
            return False
        ent = d.get("ent")
        last = self._dead.get(ent)
        if last is not None and f - last < DEAD_REPEAT_F:
            return False
        self._dead[ent] = f
        return True

    def lethal_frames(self) -> list[int]:
        return sorted({f for f, _, _ in self.lethal})

    def summary(self) -> dict:
        """What run_episode stores in the AttemptRecord for a gauntlet."""
        with self._lock:
            w0 = self.wake_frame
            waves = [{"wave": i, "f": f, "t": round((f - w0) / 60.0, 2) if w0 is not None else None}
                     for i, f in self.waves]
            by_type: dict[str, int] = {}
            by_src: dict[str, int] = {}
            for _, tk, src in self.kills:
                by_type[tk] = by_type.get(tk, 0) + 1
                by_src[str(src)] = by_src.get(str(src), 0) + 1
            return {"waves": waves, "wave_source": "room.battles" if self.battle_seen else "kills",
                    "wave_reached": self.wave, "end_source": self.end_source,
                    "kills": {"n": len(self.kills), "by_type": by_type, "by_src": by_src},
                    "allies": {n: {"frames": c, "first_t": round((self.ally_first[n] - w0) / 60.0, 2)
                                   if w0 is not None else None} for n, c in self.allies_seen.items()},
                    "sim_alive": self.sim.alive}


# FSM states of enemies that are in the scene but not in the fight (Forum, fo_A before the battle, instance 2,
# 2026-10-02: later waves' Song Pilgrim Maestro and Song Reed wait in "Fly In Ready"; the Maestro's three pooled
# "Song Automaton Tiny" (hp 28) sit in "Die" at its position; wave 1's Song Pilgrim 03 pair has its "Attack" FSM
# disabled (state None) until BattleSceneEnemy enables it; Song Heavy Sentry rests in "Rest" until BATTLE START).
WAITING_STATES = frozenset(("Fly In Ready", "Die", "Dormant", "Rest", "On-plane Rest", "Start Idle"))


def in_play(e: dict) -> bool:
    """An enemy that takes part now: its FSMs run (some state set) and none is a waiting state."""
    states = [f.get("state") for f in e.get("fsms") or ()]
    if not states:
        return True
    return any(st is not None for st in states) and not any(st in WAITING_STATES for st in states)


def live_enemies(s: dict) -> list[dict]:
    """The HealthManager entities of a STATE that are in play: not hidden, not dead, hp > 0, not waiting."""
    out = []
    for e in s.get("ents") or ():
        if not (e.get("src", 0) & SRC_BITS["health_manager"]) or e.get("hidden") or e.get("is_dead"):
            continue
        if (e.get("hp") or 0) <= 0 or not in_play(e):
            continue
        out.append(e)
    return out
