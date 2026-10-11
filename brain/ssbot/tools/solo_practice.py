"""Single-enemy practice in the Forum (the person 2026-10-10: "can each test bring out one enemy to fight? best to
understand one enemy fully before several"): tools.human_session --solo "<type key>" starts the Forum from the wave
savestate that holds that type with the fewest others, and leaves one enemy of that type in play.

Only interfaces the deployed oracle already has (no new RPC):
  - the wave-start savestates fo_r1_w<i> (train.wave_start.STATE_PREFIX; the battle restarts at wave i);
  - the debug line server (train.wave_start.DebugLine, port 47631 + instance; pdget / pdset): while any OTHER enemy
    is in play, the hero is boosted as WaveSkipPolicy's skip does it (isInvincible True, nailUpgrades 4: nail damage
    21), so the person clears them in a few hits (Reed 55 hp: 3 hits, Envoy 38: 2); as soon as only one enemy of the
    type is left, the PlayerData values read before the boost are put back. There is no oracle RPC that removes or
    kills one chosen enemy (battle.wave kills whole earlier waves, enemy.hp never goes below 1), so the person does
    the clearing; a second enemy of the same type counts as "other" (the first one kept is the lowest iid);
  - protection (--solo-protect, default on): the kept enemy's HP is refilled through the oracle RPC "enemy.hp" {type_key,
    hp} when it falls below half of its highest seen HP, so it never dies and the wave never advances; enemy.hp is in
    the oracle source since 073abe0 (2026-10-06): when the deployed oracle answers "unknown", protection turns off and
    the session says so (reload the savestate with "load <savestate>" in C:/ssbot/sandbox/human_cmd.txt to retry).
A new battle (a savestate reload) starts the clearing again. Nothing here acts on the game's input.
"""
from __future__ import annotations

from dataclasses import dataclass

from ssbot.train.encounters import FORUM_WAVES
from ssbot.train.gauntlet import live_enemies, type_key
from ssbot.train.wave_start import BOOST, STATE_PREFIX

ALLY_WAVES = {1}                      # wave 1's "Call Ally": Garmond joins the fight (attacks the enemies)
PROTECT_FRAC = 0.5
# stage B: the kept type's own summons are part of its attack and stay in play (the Maestro's Tinies); a summoned type
# is practised with its summoner (--solo "Song Automaton Tiny" = one Maestro and its Tinies)
COMPANIONS = {"Song Pilgrim Maestro": ("Song Automaton Tiny",)}
HOSTS = {"Song Automaton Tiny": "Song Pilgrim Maestro"}


@dataclass(frozen=True)
class SoloPlan:
    type_key: str
    wave: int
    savestate: str
    others: tuple                     # the wave's other members (type keys), the extra same-type ones included
    ally: bool


def plan_for(tk: str, waves=FORUM_WAVES, prefix: str = STATE_PREFIX) -> SoloPlan:
    """The wave holding type tk (or its summoner, HOSTS) with the fewest other members (an ally wave counts one more),
    earliest first."""
    tk = HOSTS.get(tk, tk)
    best = None
    for w in waves:
        members = [type_key(m) for m in w.types]
        if tk not in members:
            continue
        others = list(members)
        others.remove(tk)
        ally = w.index in ALLY_WAVES
        score = (len(others) + (1 if ally else 0), w.index)
        if best is None or score < best[0]:
            best = (score, SoloPlan(tk, w.index, f"{prefix}{w.index}", tuple(others), ally))
    if best is None:
        raise ValueError(f"no Forum wave holds {tk!r}")
    return best[1]


def forum_battle(s: dict) -> dict | None:
    return next((b for b in (s.get("room") or {}).get("battles") or () if b.get("name") == "Battle Scene"), None)


class SoloController:
    """Called about once a second by the session loop with the newest STATE (tick). `debug` makes a
    wave_start.DebugLine-like object (pdget / pdset / close), `rpc` is OracleLink.rpc-like; both may fail: the
    controller then says so once and carries on without that part."""

    def __init__(self, tk: str, debug, rpc, protect: bool = True, log=print):
        self.tk = HOSTS.get(tk, tk)
        self._debug_factory = debug
        self.rpc = rpc
        self.protect = protect
        self.log = log
        self.dbg = None
        self.debug_ok = True
        self.saved: dict | None = None        # PlayerData values before the boost
        self.boosted = False
        self.phase = "wait"                  # wait (no battle) / clear (others in play) / solo
        self.bid = None
        self.keep: int | None = None
        self.hp_max = 0
        self.events: list = []

    def _say(self, text: str) -> None:
        self.events.append(text)
        self.log(f"solo: {text}")

    def _line(self):
        if self.dbg is None and self.debug_ok:
            try:
                self.dbg = self._debug_factory()
            except Exception as e:  # noqa: BLE001 - no debug line: the person clears without the boost
                self.debug_ok = False
                self._say(f"debug line unavailable ({e!r}): no boost, clear the others yourself")
        return self.dbg

    def _boost(self, on: bool) -> None:
        if on == self.boosted:
            return
        d = self._line()
        if d is None:
            return
        try:
            if on:
                self.saved = {k: d.pdget(k) for k, _ in BOOST}
                for k, v in BOOST:
                    d.pdset(k, v)
            else:
                for k, v in (self.saved or {k: dv for k, dv in (("nailUpgrades", "1"), ("isInvincible", "False"))}
                             ).items():
                    d.pdset(k, _value(v))
            self.boosted = on
        except Exception as e:  # noqa: BLE001 - a refused pdset: say so, stop trying
            self.debug_ok = False
            self._say(f"boost {'on' if on else 'off'} failed ({e!r})")

    def tick(self, s: dict | None) -> str:
        if not s:
            return self.phase
        b = forum_battle(s)
        if not b or not b.get("started"):
            if self.phase != "wait":
                self._boost(False)
                self.phase, self.bid, self.keep = "wait", None, None
            return self.phase
        if b.get("id") != self.bid:                      # a new battle: a (re)load
            self.bid, self.keep, self.hp_max = b.get("id"), None, 0
            self.phase = "clear"
        live = live_enemies(s)
        mine = sorted((e for e in live if type_key(e.get("type_key")) == self.tk), key=lambda e: int(e.get("iid", 0)))
        if self.keep is not None and not any(int(e.get("iid", 0)) == self.keep for e in mine):
            self.keep = None
        if self.keep is None and mine:
            self.keep = int(mine[0].get("iid", 0))
        comp = COMPANIONS.get(self.tk, ())
        others = [e for e in live if int(e.get("iid", 0)) != self.keep and type_key(e.get("type_key")) not in comp]
        if others:
            if self.phase != "clear" or not self.boosted:
                if self.phase != "clear":
                    self.phase = "clear"
                self._boost(True)
                if not any(t.startswith("clear") for t in self.events[-1:]):
                    names = ", ".join(sorted(type_key(e.get("type_key")) for e in others))
                    self._say(f"clear the others first ({names})" + (": invincible, nail 4" if self.boosted else ""))
            return self.phase
        if self.keep is None:
            return self.phase                                # nothing of the type in play (yet)
        if self.phase != "solo":
            self._boost(False)
            self.phase = "solo"
            self._say(f"only {self.tk} left (iid {self.keep}); boost off")
        e = mine[0] if mine else None
        hp = int((e or {}).get("hp") or 0)
        self.hp_max = max(self.hp_max, hp)
        if self.protect and e is not None and self.hp_max and hp < PROTECT_FRAC * self.hp_max:
            try:
                self.rpc("enemy.hp", timeout_s=10, type_key=self.tk, hp=int(self.hp_max))
                self._say(f"refilled {self.tk} hp {hp} -> {self.hp_max}")
            except Exception as e2:  # noqa: BLE001 - the deployed oracle lacks enemy.hp: no protection
                self.protect = False
                self._say(f"protection off: enemy.hp failed ({e2!r})")
        return self.phase

    def close(self) -> None:
        self._boost(False)
        if self.dbg is not None:
            try:
                self.dbg.close()
            except Exception:  # noqa: BLE001
                pass


def _value(v) -> str:
    """pdget's reply as a pdset value ("ok <value>" or the bare value)."""
    t = str(v).strip()
    return t.split(None, 1)[1] if t.lower().startswith("ok ") else t
