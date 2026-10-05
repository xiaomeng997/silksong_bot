"""Which Forum wave runs and when the next one can start, from what the view sees (Forum plan R2, §4.6: never from
room.battles, which is the test truth only).

    wt = WaveTracker()
    wt.start(t_battle)                 # the battle start (the gates close / the bot walked into Start Range)
    wt.update(ws)                      # every WorldState: kills (ENEMY_KILLED / killing HIT_DEALT) and sightings
    wt.wave, wt.next_window(t)         # the current wave index; (wave, t_lo, t_hi) of the next activation, game time

The rules are BattleScene's (ssbot.core.forum.FORUM_WAVES; forum.md §2, ssbot.train.gauntlet.WaveSim): StartWave(i)
activates wave i startDelay(i) after it is queued; a wave ends when its count of living members drops to
remainingEnemyToEnd, checked at every member's death and once 1 s after the activation; then the next is queued. The
tracker counts the members it saw die (a member type's ENEMY_KILLED or killing HIT_DEALT; the Tinies are not members)
and confirms an activation when a member type of the expected wave is first seen in play. In the vision view a kill
off-screen is not seen: the count stays too high and no wave is queued. The tracker resyncs when an enemy of a type of
the next wave comes into play that is not one of the running waves' members it knows alive (an instance never seen in
play, or one seen killed: BattleScene reuses GameObjects across waves) RESYNC_AFTER_S after the activation: the running
wave has ended (its count drops to remainingEnemyToEnd) and the next one is active (a late estimate, not an early one:
until then its entries are not placed).
"""
import math
from dataclasses import dataclass, field

from ssbot.core.forum import BATTLE_START_PAUSE_S, FORUM_TYPES, FORUM_WAVES, WAVE_CHECK_S, WAVE_TYPES
from ssbot.core.worldstate import Ev, WorldState

SLACK_S = 2.0 / 60.0          # kill / activation times are frame times (+- the export lag)
RESYNC_AFTER_S = 2.0          # a running wave's members are all in play this long after its activation


@dataclass
class WaveTracker:
    waves: tuple = FORUM_WAVES
    t_battle: float | None = None
    wave: int = -1                       # the last wave known to have been activated
    t_active: float | None = None        # its activation time (estimate)
    alive: int = 0                       # members of the running waves still alive (BattleScene.currentEnemies)
    to_next: int = 0
    queued: tuple | None = None          # (wave, t_lo, t_hi) queued and not activated yet
    starts: list = field(default_factory=list)   # (wave, t) activations, as estimated
    kills: int = 0
    seen: set = field(default_factory=set)
    live: set = field(default_factory=set)         # member iids seen in play and not seen killed since
    killed: set = field(default_factory=set)       # member iids seen killed and not out of play since
    resyncs: int = 0
    done: bool = False
    _checked: bool = False

    def reset(self) -> None:
        self.__init__(self.waves)

    def start(self, t: float, wave: int = 0) -> None:
        """The battle started at t (wave 0 queued: activation after battleStartPause + its startDelay); a wave-start
        savestate's battle starts at its wave (forum.md 13.1)."""
        if self.t_battle is None:
            self.t_battle = t
            lo = t + (BATTLE_START_PAUSE_S if wave == 0 else 0.0) + self.waves[wave].start_delay_s
            self.queued = (wave, lo - SLACK_S, lo + SLACK_S)

    def update(self, ws: WorldState) -> None:
        t = ws.stamp.t_game_s
        for ev in ws.events:
            if ev.kind == Ev.ENEMY_KILLED or (ev.kind == Ev.HIT_DEALT and ev.data.killing):
                d = ev.data
                tk = getattr(d, "type_key", "") or ""
                if tk in WAVE_TYPES and (d.target_id, round(t, 3)) not in self.seen:
                    self.seen.add((d.target_id, round(t, 3)))
                    self.live.discard(d.target_id)
                    self.killed.add(d.target_id)
                    self._kill(t)
        play = {e.id: e for e in ws.entities
                if e.type_key.v in WAVE_TYPES and not e.hidden and self._in_play(e, alive=True)}
        # a killed member that left play (gone, hidden, waiting): its GameObject's next activation is a new member
        self.killed &= set(play)
        if self.queued is None and not self.done and 0 <= self.wave < len(self.waves) - 1 \
                and self.t_active is not None and t >= self.t_active + RESYNC_AFTER_S:
            # a kill not seen: a next-wave member in play that is none of the running waves' members alive
            exp = set(self.waves[self.wave + 1].types)
            if any(e.type_key.v in exp and i not in self.live and i not in self.killed for i, e in play.items()):
                self.resyncs += 1
                self.alive = min(self.alive, self.to_next)
                self._activate(self.wave + 1, t)
        self.live |= set(play) - self.killed
        if self.queued is not None:
            w, lo, hi = self.queued
            exp = set(self.waves[w].types)
            # a member of the queued wave seen in play: activated (an earlier-loaded member, waves 1 / 6 / 12, may sit
            # in its waiting state: not counted)
            for e in ws.entities:
                tk = e.type_key.v
                if tk in exp and not e.hidden and self._in_play(e):
                    self._activate(w, min(max(lo, t - 1.0), t))
                    break
            else:
                if math.isfinite(hi) and t > hi + 0.5:
                    self._activate(w, 0.5 * (lo + hi))      # nobody seen (out of the image): the rule's time
        if self.wave >= 0 and not self._checked and self.t_active is not None and t >= self.t_active + WAVE_CHECK_S:
            self._checked = True
            if self.alive <= self.to_next:
                self._end(self.t_active + WAVE_CHECK_S)

    @staticmethod
    def _in_play(e, alive: bool = False) -> bool:
        """Out of its waiting state (alive: and not in a death state; a state not seen counts as not in play)."""
        spec = FORUM_TYPES.get(e.type_key.v)
        if spec is None:
            return False
        st = e.fsm[0][1] if e.fsm else (e.phase.top if e.phase is not None else None)
        return st is not None and st not in spec.waiting and not (alive and st in spec.death_states)

    def _activate(self, w: int, t: float) -> None:
        self.queued = None
        self.wave, self.t_active, self._checked = w, t, False
        self.alive += len(self.waves[w].members)
        self.to_next = self.waves[w].remaining_to_end
        self.starts.append((w, t))

    def _kill(self, t: float) -> None:
        self.kills += 1
        if self.wave < 0:
            return
        self.alive = max(0, self.alive - 1)
        if self.alive <= self.to_next:
            self._end(t)

    def _end(self, t: float) -> None:
        if self.queued is not None:
            return                       # a second end inside the next wave's startDelay (WaveSim ignores it)
        if self.wave >= len(self.waves) - 1:
            self.done = True
            return
        w = self.wave + 1
        d = self.waves[w].start_delay_s
        self.queued = (w, t + d - SLACK_S, t + d + SLACK_S)

    def next_window(self) -> tuple[int, float, float] | None:
        """(wave, earliest, latest activation) of the next wave, None when none is queued yet or the battle is over:
        the queued one, else the running wave's end is not known yet (its members still alive)."""
        if self.done:
            return None
        return self.queued
