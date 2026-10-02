"""Behaviour-logging policy for boss encounters (M2 W2): random but boss-aware play that keeps the fight going at
every distance, so the boss's attack choices and timings are logged over the whole range of hero positions.

Not a fighter: it is not meant to avoid hits (in mode "data" LethalBlock keeps the hero at >= 1 HP and the episode
goes on). Segments of 20-90 frames each pick a mode: PRESS (close in and attack), KEEP (hold a random distance
3-10 u), EVADE (move away), IDLE. Within a segment: attacks when the boss is in reach (up-slash when it is above,
down-slash pogo when below in the air), random jumps, jumps over a charge, a bind at low HP with 9 silk, rare silk
skills. Keys follow the oracle's minimum press/release of 2 frames, and up/down are pressed only with left or right
held (InteractManager starts an interaction on an up/down edge without one, 1.0.30000 InteractManager.cs:244).

It reads the oracle's STATE directly (boss entity, hero), which only training code may do.
"""
import random

from ssbot.ipc.framing import mask
from ssbot.train.encounters import Encounter

B = {k: mask(k) for k in ("left", "right", "jump", "attack", "up", "down", "bind", "quickcast")}
MODES = (("PRESS", 0.60), ("KEEP", 0.25), ("EVADE", 0.10), ("IDLE", 0.05))
REACH_X, REACH_Y = 2.6, 2.2      # Hunter side slash reach, roughly (slash.dump: about 2.3 u forward from the centre)
CHARGE_STATES = ("Charge Antic", "Charge")


class DataPolicy:
    def __init__(self):
        self.r = random.Random(0)
        self.enc: Encounter | None = None
        self.counts: dict[str, int] = {}

    def reset(self, rng: random.Random, enc: Encounter) -> None:
        self.r = rng
        self.enc = enc
        self.mode = "PRESS"
        self.mode_left = 0
        self.keep_d = 5.0
        self.hold = {k: 0 for k in B}      # frames the key stays down
        self.rest = {k: 0 for k in B}      # frames the key stays up after a release
        self.counts = {}
        self.mode_frames = {m: 0 for m, _ in MODES}

    def stats(self) -> dict:
        return {"presses": dict(self.counts), "mode_frames": dict(self.mode_frames)}

    def _press(self, k: str, frames: int) -> None:
        if self.hold[k] == 0 and self.rest[k] == 0:
            self.hold[k] = max(2, frames)
            self.counts[k] = self.counts.get(k, 0) + 1

    def act(self, s: dict, tap) -> int:
        r = self.r
        enc = self.enc
        hero = s["hero"]
        hx, hy = hero["pos"][0], hero["pos"][1]
        boss = None
        for e in s.get("ents") or ():
            # A hidden boss (M2 oracle: underground, HealthManager off) was absent from "ents" when the policy was
            # tuned; skipping it keeps the logged data comparable across oracle versions.
            if e["type_key"] == enc.boss_type and not e.get("hidden"):
                boss = e
                break
        if self.mode_left <= 0:
            self.mode = r.choices([m for m, _ in MODES], [w for _, w in MODES])[0]
            self.mode_left = r.randint(20, 90)
            self.keep_d = r.uniform(3.0, 10.0)
        self.mode_left -= 1
        self.mode_frames[self.mode] += 1

        move = None
        if boss is not None:
            bx, by = boss["pos"][0], boss["pos"][1]
            dx, dy = bx - hx, by - hy
            toward = "right" if dx > 0 else "left"
            away = "left" if dx > 0 else "right"
            if self.mode == "PRESS":
                move = toward if abs(dx) > 1.6 else None
            elif self.mode == "KEEP":
                if abs(dx) > self.keep_d + 1.0:
                    move = toward
                elif abs(dx) < self.keep_d - 1.0:
                    move = away
            elif self.mode == "EVADE":
                move = away
            # stay off the arena's ends: turn back toward the middle
            lo, hi = enc.arena_x
            if hx < lo + 1.0 and move == "left" or hx > hi - 1.0 and move == "right":
                move = "right" if hx < (lo + hi) / 2 else "left"
            airborne = hy > enc.floor_y + 0.5
            ctl = tap.control or ""
            if abs(dx) < REACH_X + 0.5 and abs(dy) < REACH_Y and r.random() < 0.25:
                if (hero.get("facing", 1) > 0) != (dx > 0):
                    move = toward                       # turn first
                self._press("attack", r.randint(2, 4))
            if dy > 1.5 and abs(dx) < 2.0 and r.random() < 0.15:
                move = move or toward
                self._press("up", r.randint(6, 12))
                self._press("attack", 3)
            if airborne and dy < -1.0 and abs(dx) < 1.8 and r.random() < 0.2:
                move = move or toward
                self._press("down", r.randint(6, 14))
                self._press("attack", 3)
            if ctl in CHARGE_STATES and abs(dx) < 7.0 and not airborne and r.random() < 0.3:
                self._press("jump", r.randint(14, 24))
            if ctl and self.mode != "IDLE" and r.random() < 0.02 and hero.get("silk", 0) >= 4 and abs(dx) < 8.0:
                if (hero.get("facing", 1) > 0) == (dx > 0):
                    self._press("quickcast", 3)
        if r.random() < 0.02:
            self._press("jump", r.randint(3, 24))
        if hero.get("health", 5) <= 2 and hero.get("silk", 0) >= 9 and r.random() < 0.05:
            self._press("bind", 3)

        m = 0
        for k in B:
            if self.hold[k] > 0:
                self.hold[k] -= 1
                m |= B[k]
                if self.hold[k] == 0:
                    self.rest[k] = 2
            elif self.rest[k] > 0:
                self.rest[k] -= 1
        if move:
            m |= B[move]
        if m & (B["up"] | B["down"]) and not m & (B["left"] | B["right"]):
            m &= ~(B["up"] | B["down"])    # never an up/down without a side key (see the module docstring)
        return m
