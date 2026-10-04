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
off-screen is not seen: the next wave's window then stays open (t_hi = inf) until a member shows up.
"""
import math
from dataclasses import dataclass, field

from ssbot.core.forum import BATTLE_START_PAUSE_S, FORUM_TYPES, FORUM_WAVES, WAVE_CHECK_S, WAVE_TYPES
from ssbot.core.worldstate import Ev, WorldState

SLACK_S = 2.0 / 60.0          # kill / activation times are frame times (+- the export lag)


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
                    self._kill(t)
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
    def _in_play(e) -> bool:
        spec = FORUM_TYPES.get(e.type_key.v)
        if spec is None:
            return False
        st = e.fsm[0][1] if e.fsm else (e.phase.top if e.phase is not None else None)
        return st is not None and st not in spec.waiting

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
