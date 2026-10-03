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

from ssbot.ipc.ents import boss_entity
from ssbot.ipc.framing import mask
from ssbot.train.encounters import Encounter

B = {k: mask(k) for k in ("left", "right", "jump", "attack", "up", "down", "bind", "quickcast", "dash")}
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
        # A hidden boss (M2 oracle: underground, HealthManager off) was absent from "ents" when the policy was tuned;
        # skipping it keeps the logged data comparable across oracle versions.
        boss = boss_entity(s.get("ents"), enc.boss_type)
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
        return self._compose(move)

    def _compose(self, move: str | None) -> int:
        """This frame's button mask from the held keys and the movement direction."""
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


G_MODES = (("PRESS", 0.48), ("KEEP", 0.22), ("EVADE", 0.10), ("IDLE", 0.05), ("CLING", 0.15))
SEG_F = (20, 90)                 # frames of a PRESS / KEEP / EVADE / IDLE segment
CLING_F = (30, 150)              # of a CLING segment
POCKET_CLING_F = (120, 480)      # of a CLING segment with only Choir Clappers left
# With only Choir Clappers left (wave 7, the finale) CLING takes POCKET_CLING_SHARE of the time (by frames, not by
# picks: a pocket CLING segment lasts 300 frames on average, the others 55), on the left wall, climbing to the
# person's pocket at its top, so the Clappers' choices against a hero up there get logged (docs/facts/1.0.30000/
# forum.md §10: only Far Range decisions). Their ground attacks are already logged plenty (CC_SLAM 227, CC_CAST 232,
# CC_EVADE 509 instances in 8 gauntlets; jumps 130 and jump casts 122), the pocket was the scarce case (10 fights: 1712
# frames), so most of the time goes to it. Run 20261002_231917 (e589c0b) used a 0.5 pick weight, which is this share.
POCKET_CLING_SHARE = 0.85
_POCKET_OTHERS = (("PRESS", 0.50), ("KEEP", 0.20), ("EVADE", 0.20), ("IDLE", 0.10))


def _pocket_modes(share: float = POCKET_CLING_SHARE) -> tuple[tuple[str, float], ...]:
    """Pick weights giving CLING `share` of the frames: w * m_cling / (w * m_cling + (1 - w) * m_seg) = share."""
    m_cling, m_seg = sum(POCKET_CLING_F) / 2.0, sum(SEG_F) / 2.0
    w = share * m_seg / (share * m_seg + (1.0 - share) * m_cling)
    return tuple((m, (1.0 - w) * q) for m, q in _POCKET_OTHERS) + (("CLING", w),)


POCKET_MODES = _pocket_modes()
POCKET_TYPES = frozenset(("Song Heavy Sentry",))
POCKET_Y = 13.3          # hero transform at the top of the left-wall cling (highest still cling 13.45-13.60)
WALL_NEAR = 1.2          # hero centre to the arena's inner wall face when touching it, about (hero box half width 0.5)


class GauntletDataPolicy(DataPolicy):
    """DataPolicy for a multi-wave arena (the Forum, M2 W8): the same random modes around a sticky target picked among
    the live enemies (nearest 60 %, else any), plus CLING (go to an arena wall, mostly the left one, jump at it and
    hold toward it: a wall slide, or a cling with Ascendant's Grip, 1.0.30000 HeroController.cs:2230; occasional
    attacks and re-jumps from there), so the enemies' choices are also logged against a hero on the wall, the
    person's plan for the last wave. Silk skills and tools: quickcast now and then (neutral or with up held, so both
    the Silkspear and a Cogfly binding get used). With helpers on, enemies die and waves advance without the hero."""

    def reset(self, rng: random.Random, enc: Encounter) -> None:
        super().reset(rng, enc)
        self.mode_frames = {m: 0 for m, _ in G_MODES}
        self.target_iid: int | None = None
        self.wall = 0
        self.targets: dict[str, int] = {}
        self.cling_frames = 0
        self.pocket_frames = 0
        self.names: list[str] | None = None

    def stats(self) -> dict:
        return {**super().stats(), "targets": dict(self.targets), "cling_frames": self.cling_frames,
                "pocket_frames": self.pocket_frames}

    def _cstate(self, s: dict) -> dict:
        if self.names is None:
            import json
            from pathlib import Path
            p = Path(__file__).resolve().parents[3] / "docs" / "facts" / "1.0.30000" / "cstate_schema.json"
            self.names = json.loads(p.read_text(encoding="utf-8"))["bools"]
        from ssbot.tools.cstate import decode
        try:
            return decode(s["hero"]["cstate"], self.names)
        except (KeyError, ValueError, TypeError):
            return {}

    def act(self, s: dict, tap) -> int:
        from ssbot.train.gauntlet import live_enemies
        r = self.r
        enc = self.enc
        hero = s["hero"]
        hx, hy = hero["pos"][0], hero["pos"][1]
        lo, hi = enc.arena_x
        live = [e for e in live_enemies(s) if lo - 3.0 <= e["pos"][0] <= hi + 3.0 and e["pos"][1] < enc.floor_y + 25.0]
        pocket = bool(live) and all(e.get("type_key") in POCKET_TYPES for e in live)
        if self.mode_left <= 0:
            modes = POCKET_MODES if pocket else G_MODES
            self.mode = r.choices([m for m, _ in modes], [w for _, w in modes])[0]
            if self.mode == "CLING":
                self.mode_left = r.randint(*POCKET_CLING_F) if pocket else r.randint(*CLING_F)
            else:
                self.mode_left = r.randint(*SEG_F)
            self.keep_d = r.uniform(3.0, 10.0)
            self.wall = -1 if r.random() < (0.95 if pocket else 0.8) else 1
            if live:
                tgt = (min(live, key=lambda e: abs(e["pos"][0] - hx) + abs(e["pos"][1] - hy)) if r.random() < 0.6
                       else r.choice(live))
                self.target_iid = tgt["iid"]
        self.mode_left -= 1
        self.mode_frames[self.mode] += 1
        tgt = next((e for e in live if e["iid"] == self.target_iid), None)
        if tgt is None and live:
            tgt = min(live, key=lambda e: abs(e["pos"][0] - hx) + abs(e["pos"][1] - hy))
            self.target_iid = tgt["iid"]
        if tgt is not None:
            tk = tgt.get("type_key", "?")
            self.targets[tk] = self.targets.get(tk, 0) + 1
        cs = self._cstate(s)
        grounded = cs.get("onGround", hy <= enc.floor_y + 0.3)
        move = None

        if self.mode == "CLING":
            wall_x = lo if self.wall < 0 else hi
            toward = "left" if self.wall < 0 else "right"
            on_wall = cs.get("wallClinging") or cs.get("wallSliding") or cs.get("touchingWall")
            if abs(hx - wall_x) > WALL_NEAR + 1.5 and not on_wall:
                move = toward
                if grounded and abs(hx - wall_x) < 4.0 and r.random() < 0.3:
                    self._press("jump", r.randint(18, 26))
            else:
                move = toward                      # hold toward the wall: slide, or cling with the Grip
                if grounded:
                    self._press("jump", r.randint(18, 26))
                elif on_wall:
                    self.cling_frames += 1
                    high = self.wall < 0 and hy >= POCKET_Y
                    self.pocket_frames += high
                    # wall jumps climb, then re-grab; in the finale, climb to the pocket and stay there
                    if r.random() < (0.0 if high and pocket else 0.08 if pocket else 0.015):
                        self._press("jump", r.randint(8, 16))
                    if r.random() < (0.03 if pocket else 0.04):
                        self._press("attack", 3)
        elif tgt is not None:
            bx, by = tgt["pos"][0], tgt["pos"][1]
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
            if hx < lo + 1.0 and move == "left" or hx > hi - 1.0 and move == "right":
                move = "right" if hx < (lo + hi) / 2 else "left"
            if abs(dx) < REACH_X + 0.8 and abs(dy) < REACH_Y and r.random() < 0.25:
                if (hero.get("facing", 1) > 0) != (dx > 0):
                    move = toward
                self._press("attack", r.randint(2, 4))
            if 1.5 < dy < 6.0 and abs(dx) < 2.5 and r.random() < 0.12:
                move = move or toward
                if grounded and dy > 2.5:
                    self._press("jump", r.randint(10, 22))
                self._press("up", r.randint(6, 12))
                self._press("attack", 3)
            if not grounded and dy < -1.0 and abs(dx) < 1.8 and r.random() < 0.2:
                move = move or toward
                self._press("down", r.randint(6, 14))
                self._press("attack", 3)
            antic = any("Antic" in str(f.get("state")) for f in tgt.get("fsms") or ())
            if antic and abs(dx) < 7.0 and grounded and r.random() < 0.15:
                self._press("jump", r.randint(14, 24))
            if self.mode != "IDLE" and r.random() < 0.012 and abs(dx) < 3.0:
                self._press("dash", 3)
            if self.mode != "IDLE" and r.random() < 0.015 and abs(dx) < 10.0:
                if (hero.get("facing", 1) > 0) == (dx > 0):
                    move = move or toward
                    if r.random() < 0.5:
                        self._press("up", 6)
                    self._press("quickcast", 3)
        if r.random() < 0.02 and self.mode != "CLING":
            self._press("jump", r.randint(3, 24))
        if hero.get("health", 5) <= 2 and hero.get("silk", 0) >= 9 and r.random() < 0.05:
            self._press("bind", 3)
        return self._compose(move)
