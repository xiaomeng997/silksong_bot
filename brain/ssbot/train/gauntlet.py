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
                 BattleScene's DecrementEnemy rule on the known wave list (WaveSim). Exact for the DecrementEnemy
                 path; BattleScene also ends a wave when the wave transforms' child count drops to remainingEnemyToEnd
                 (DoCheckEnemies, 1 s after each start), which the sim does not see.
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


class WaveSim:
    """BattleScene's DecrementEnemy rule replayed from kills: start(f) at the battle's first wave, kill(f) per death."""

    def __init__(self, waves: tuple[Wave, ...]):
        self.waves = waves
        self.wave = -1
        self.alive = 0
        self.to_next = 0
        self.done = False
        self.starts: list[tuple[int, int]] = []      # (wave index, frame its enemies were activated)
        self.end_frame: int | None = None

    def start(self, f: int) -> None:
        if self.wave < 0:
            self._start_wave(0, f)

    def _start_wave(self, i: int, f: int) -> None:
        w = self.waves[i]
        f_on = f + round(w.start_delay_s * 60)
        self.wave = i
        self.alive += len(w.enemies)
        self.to_next = w.remaining_to_end
        self.starts.append((i, f_on))

    def kill(self, f: int) -> None:
        if self.wave < 0 or self.done:
            return
        self.alive -= 1
        while self.alive <= self.to_next and not self.done:
            if self.wave >= len(self.waves) - 1:
                self.done = True
                self.end_frame = f
            else:
                self._start_wave(self.wave + 1, f)


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
            self._dead: set[int] = set()
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
                if a.get("active") and a.get("state") not in (None, "Dormant", "Init", "Wait Hero In Position",
                                                               "Wait An Additional Frame", "Auto Target?"):
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
                    if d.get("dead") and d.get("ent") not in self._dead:
                        self._dead.add(d.get("ent"))
                        self.kills.append((f, d.get("type_key"), d.get("src")))
                        if self.wake_frame is not None:
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


def live_enemies(s: dict) -> list[dict]:
    """The HealthManager entities of a STATE that are in play: not hidden, not dead, hp > 0."""
    out = []
    for e in s.get("ents") or ():
        if not (e.get("src", 0) & SRC_BITS["health_manager"]) or e.get("hidden") or e.get("is_dead"):
            continue
        if (e.get("hp") or 0) <= 0:
            continue
        out.append(e)
    return out
