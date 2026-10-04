"""Targeted behaviour-logging policy for the Forum, v2 (Forum plan R1 item 2, docs/plans/forum_planner_plan.md; the
person's answers in docs/plans/M2.md "Forum 打法问答"). Like GauntletDataPolicy (ssbot.train.data_policy) it is random
and not a fighter (in mode "data" LethalBlock keeps the hero alive), but its segments are tactics that put the hero
where the logs are thin:

  PRESS      close in and slash (v1's PRESS)
  KEEP       hold a random distance 3-10 u (v1's KEEP)
  BAIT       hold a distance near one of the target type's attack-choice boundaries (the largest hero distance at
             which the family was ever chosen, or its p99; boundaries.json of R0, a built-in copy until it is merged),
             stepping across it now and then: which side of the boundary draws which attack
  DASH_IN    from 3-9 u, dash at the target and slash during the dash (Reaper's dash attack), then back off
  CLAW_IN    Clawline (harpoon) at the target from 3-12 u when it is level with the hero: does a harpoon into an
             enemy hurt the hero (the person: no)
  UNDER      stand right under a flying target (the person: fliers strike diagonally down), up-slash now and then
  JUMP_OVER  run at a ground target and jump over it (the Envoy: its hop slash needs the hero above it, forum.md §11)
  WALL_BAIT  wait with the back to an arena wall while a ground target comes (the Envoy's "Hop Up?" ray looks for
             terrain 3 u ahead: does a hop slash ever come)
  CLASH      wait at slash reach facing the target and swing exactly when a parryable damage collider (parry clash /
             force bit) or a Throwing Bell enters the side-slash box: clash outcomes per attack, small bells first
  CLIMB      the left wall to its top with hold-toward-wall + dash (Wall Scramble, ssbot.train.climb.WallClimber),
             then cling there (the pocket), wall-slashing a target in reach now and then; with only Choir Clappers
             left it takes POCKET_SHARE of the time
  EVADE      move away from the target

Hold times are game seconds turned into frames with the STATE dt (so the policy plays the same at any time scale:
the 2x check, Forum plan R1 item 4). protect = type keys never to be hit (the Envoy campaign: the Envoy is the only
wave-0 enemy that dies fast, 38 HP; keeping it alive keeps wave 0 and its attacks going): no swing, spear or clawline
while a protected body at or below PROTECT_HP is near or in line. Training code: reads the oracle's STATE directly.
"""
import json
import math
import random
from pathlib import Path

from ssbot.ipc.framing import mask
from ssbot.train.climb import WallClimber
from ssbot.train.encounters import Encounter
from ssbot.train.wave_start import body_box, fighting, hero_flags, overlaps

B = {k: mask(k) for k in ("left", "right", "jump", "attack", "up", "down", "bind", "quickcast", "dash", "clawline")}
TACTICS = (("PRESS", 0.16), ("KEEP", 0.08), ("BAIT", 0.16), ("DASH_IN", 0.12), ("CLAW_IN", 0.07), ("UNDER", 0.10),
           ("JUMP_OVER", 0.05), ("WALL_BAIT", 0.03), ("CLASH", 0.13), ("CLIMB", 0.06), ("EVADE", 0.04))
ENVOY_TACTICS = (("BAIT", 0.24), ("DASH_IN", 0.10), ("JUMP_OVER", 0.20), ("WALL_BAIT", 0.12), ("CLASH", 0.16),
                 ("KEEP", 0.10), ("UNDER", 0.04), ("EVADE", 0.04))
SEG_S = (0.5, 2.0)            # game seconds of a PRESS / EVADE segment (v1: 20-90 frames)
TACTIC_S = {"KEEP": (1.0, 3.0), "BAIT": (2.5, 6.0), "DASH_IN": (2.0, 5.0), "CLAW_IN": (2.0, 4.0), "UNDER": (2.0, 5.0),
            "JUMP_OVER": (2.0, 4.0), "WALL_BAIT": (2.0, 5.0), "CLASH": (2.0, 5.0), "EVADE": (0.5, 1.5)}
CLIMB_S = (3.0, 9.0)
POCKET_CLIMB_S = (6.0, 14.0)
POCKET_SHARE = 0.85           # frames on the wall with only Choir Clappers left (as v1, data_policy.POCKET_CLING_SHARE)
POCKET_TYPES = frozenset(("Song Heavy Sentry",))
FLIER_DY = 2.5                # a target whose body bottom is this far above the hero's feet counts as flying
ENVOY = "Song Pilgrim 01"
BELL = "Throwing Bell"
# Reaper reach (+x forward, hero transform), as ssbot.train.wave_start
SIDE_X, SIDE_Y = (0.0, 3.4), (-0.4, 2.6)
UP_X, UP_Y = (-1.8, 0.7), (0.3, 3.6)
PROTECT_X, PROTECT_Y = 5.0, 3.5   # no swing while a protected body is this close (side reach 3.6 + a dash step)
PROTECT_HP = 20       # ... once its hp is down to this: the Envoy (38) takes two Reaper hits (9 each), so clashes with
                      # its parryable charge and the reactions to a hit (TOOK DAMAGE -> Leader? -> Charge) still come

# Attack-choice boundaries (hero |dx| when chosen: max "boundary_u" and p99) for the distance-dependent families, from
# R0's knowledge/1.0.30000/enemies/forum/boundaries.json (107 gauntlets; branch worktree-wf_198518ec-9ba-1, not merged
# yet). Families whose choice does not depend on distance (Maestro, Tiny, ranged families with p99 > 15 u) are left out.
BOUNDARIES_FALLBACK = {
    "Pilgrim 03 Song": {"CB_EVADE": (5.05, 12.7), "CB_THROW": (12.85, 19.61)},
    "Song Administrator": {"MI_CHARGE": (7.39, 16.82), "MI_EVADE": (5.12, 5.33), "MI_PARRY": (7.42, 11.95)},
    "Song Handmaiden": {"CM_SLASH": (4.31, 4.52), "CM_SPIN": (10.66, 10.92)},
    "Song Heavy Sentry": {"CC_SLAM": (8.46, 8.76), "CC_EVADE": (13.9, 26.85)},
    "Song Pilgrim 01": {"EN_SLASH": (4.9, 5.68)},
    "Song Pilgrim 03": {"CH_SLASH": (7.68, 8.05), "CH_JUMP": (12.83, 13.1), "CH_WHIP": (12.84, 13.03)},
    "Song Reed": {"RE_EVADE": (4.29, 18.3), "RE_DEFEND": (8.06, 26.2)},
}
BOUNDARY_MAX_U = 15.0


def load_boundaries(path: Path | None = None) -> dict[str, dict[str, tuple[float, float]]]:
    """{type_key: {family: (p99_u, boundary_u)}} from R0's boundaries.json when present, else the built-in copy."""
    p = path or Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum" / "boundaries.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return BOUNDARIES_FALLBACK
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for k, v in d.items():
        if not isinstance(v, dict) or "p99_u" not in v or "/" not in k:
            continue
        tk, fam = k.rsplit("/", 1)
        if v["p99_u"] <= BOUNDARY_MAX_U:
            out.setdefault(tk, {})[fam] = (float(v["p99_u"]), float(v.get("boundary_u") or v["p99_u"]))
    return out or BOUNDARIES_FALLBACK


def _parryable_boxes(s: dict) -> list[tuple[str, tuple[float, float, float, float]]]:
    """(owner type, box) of every enabled damage collider that clashes with the nail (damage.parryable), plus every
    Throwing Bell's (bells react to the nail through their own FSM: Tink / Nail Hit, forum.md §12.4)."""
    out = []
    for e in s.get("ents") or ():
        tk = str(e.get("type_key") or "")
        for c in e.get("colliders") or ():
            d = c.get("damage")
            if not c.get("enabled") or not d:
                continue
            if d.get("parryable") or tk == BELL:
                v = c.get("verts_world") or ()
                if v:
                    out.append((tk, (min(v[0::2]), min(v[1::2]), max(v[0::2]), max(v[1::2]))))
    return out


class ForumDataPolicyV2:
    """Module docstring. reset / act / stats as ssbot.train.data_policy.DataPolicy (run_episode's policy interface)."""

    act_after_clear = True

    def __init__(self, protect: tuple[str, ...] = (), tactics=None, focus: tuple[str, ...] = (),
                 protect_hp: int = PROTECT_HP):
        self.protect = frozenset(protect)
        self.protect_hp = protect_hp
        self.tactics = tuple(tactics or (ENVOY_TACTICS if ENVOY in self.protect else TACTICS))
        self.focus = frozenset(focus)              # prefer these types as targets
        self.boundaries = load_boundaries()
        self.r = random.Random(0)

    # ---- episode -----------------------------------------------------------------------------------------------

    def reset(self, rng: random.Random, enc: Encounter) -> None:
        self.r = rng
        self.enc = enc
        self.tactic = "PRESS"
        self.left_s = 0.0
        self.keep_d = 5.0
        self.bait: tuple[str, float] | None = None
        self.target_iid: int | None = None
        self.hold = {k: 0 for k in B}
        self.rest = {k: 0 for k in B}
        self.counts: dict[str, int] = {}
        self.tactic_s: dict[str, float] = {}
        self.tactic_n: dict[str, int] = {}
        self.climber = WallClimber(rng)
        self.climbs: list[dict] = []
        self.climb_t = 0.0
        self.under_s = 0.0
        self.pocket_s = 0.0
        self.clash_swings: dict[str, int] = {}
        self.dash_phase = 0
        self.claw_presses = 0
        self.dash_ins = 0
        self.dash_attacks = 0
        self.jump_overs = 0
        self.bait_samples: dict[str, int] = {}
        self.g = 0.0

    def stats(self) -> dict:
        return {"presses": dict(self.counts), "tactic_s": {k: round(v, 2) for k, v in self.tactic_s.items()},
                "tactic_n": dict(self.tactic_n), "climbs": self.climbs[-200:],
                "climb_ok": sum(1 for c in self.climbs if c["ok"]), "climb_n": len(self.climbs),
                "under_s": round(self.under_s, 2), "pocket_s": round(self.pocket_s, 2),
                "clash_swings": dict(self.clash_swings), "claw_presses": self.claw_presses,
                "dash_ins": self.dash_ins, "dash_attacks": self.dash_attacks,
                "jump_overs": self.jump_overs, "bait_samples": dict(self.bait_samples),
                "protect": sorted(self.protect)}

    # ---- keys --------------------------------------------------------------------------------------------------

    def _frames(self, s: dict, sec: float) -> int:
        dt = float(s.get("dt") or 1.0 / 60.0) or 1.0 / 60.0
        return max(2, math.ceil(sec / dt))

    def _press(self, k: str, frames: int) -> bool:
        if self.hold[k] == 0 and self.rest[k] == 0:
            self.hold[k] = max(2, frames)
            self.counts[k] = self.counts.get(k, 0) + 1
            return True
        return False

    def _compose(self, move: str | None, extra: int = 0) -> int:
        m = extra
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
            m &= ~(B["up"] | B["down"])
        return m

    # ---- helpers -----------------------------------------------------------------------------------------------

    def _safe_to_hit(self, s: dict, hx: float, hy: float, facing: int, reach_x: float = PROTECT_X,
                     line: bool = False) -> bool:
        """False when a protected enemy is near (or, for a spear / clawline, anywhere ahead on the hero's line)."""
        if not self.protect:
            return True
        for e in fighting(s):
            if e.get("type_key") not in self.protect or (e.get("hp") or 0) > self.protect_hp:
                continue
            x0, y0, x1, y1 = body_box(e)
            gx = max(x0 - hx, hx - x1, 0.0)
            if gx < reach_x and overlaps(hy - PROTECT_Y, hy + PROTECT_Y, y0, y1):
                return False
            if line and overlaps(hy - 1.5, hy + 2.5, y0, y1) and ((x0 + x1) / 2.0 - hx) * facing > 0:
                return False
        return True

    def _pick_target(self, live: list[dict], hx: float, hy: float) -> dict | None:
        if not live:
            return None
        pool = [e for e in live if e.get("type_key") in self.focus] or live
        if self.r.random() < 0.6:
            return min(pool, key=lambda e: abs(e["pos"][0] - hx) + abs(e["pos"][1] - hy))
        return self.r.choice(pool)

    def _new_segment(self, s: dict, live: list[dict], pocket: bool, hx: float, hy: float) -> None:
        r = self.r
        if pocket:
            w_cl = POCKET_SHARE * (sum(SEG_S) / 2) / (POCKET_SHARE * (sum(SEG_S) / 2)
                                                      + (1 - POCKET_SHARE) * (sum(POCKET_CLIMB_S) / 2))
            tactics = (("CLIMB", w_cl), ("PRESS", (1 - w_cl) * 0.4), ("BAIT", (1 - w_cl) * 0.3),
                       ("CLASH", (1 - w_cl) * 0.15), ("DASH_IN", (1 - w_cl) * 0.15))
        else:
            tactics = self.tactics
        self.tactic = r.choices([t for t, _ in tactics], [w for _, w in tactics])[0]
        lo, hi = (POCKET_CLIMB_S if pocket else CLIMB_S) if self.tactic == "CLIMB" else TACTIC_S.get(self.tactic,
                                                                                                         SEG_S)
        self.left_s = r.uniform(lo, hi)
        self.keep_d = r.uniform(3.0, 10.0)
        tgt = self._pick_target(live, hx, hy)
        self.target_iid = tgt["iid"] if tgt else None
        self.bait = None
        if self.tactic == "BAIT" and tgt is not None:
            fams = self.boundaries.get(tgt.get("type_key"), {})
            if fams:
                fam = r.choice(sorted(fams))
                p99, mx = fams[fam]
                centre = mx if r.random() < 0.5 else p99
                self.bait = (fam, max(0.8, centre + r.uniform(-1.2, 1.2)))
            else:
                self.tactic = "KEEP"
        if self.tactic == "CLIMB":
            self.climber.reset()
            self.climb_t = 0.0
            self.climbs.append({"g0": round(self.g, 2), "ok": False, "t_top": None, "pocket": pocket})
        self.dash_phase = 0
        self.tactic_n[self.tactic] = self.tactic_n.get(self.tactic, 0) + 1

    # ---- the policy --------------------------------------------------------------------------------------------

    def act(self, s: dict, tap) -> int:
        r = self.r
        enc = self.enc
        hero = s["hero"]
        hx, hy = hero["pos"][0], hero["pos"][1]
        dt = float(s.get("dt") or 0.0)
        self.g += dt
        lo, hi = enc.arena_x
        live = [e for e in fighting(s) if lo - 3.0 <= e["pos"][0] <= hi + 3.0 and e["pos"][1] < enc.floor_y + 25.0]
        pocket = bool(live) and all(e.get("type_key") in POCKET_TYPES for e in live)
        self.left_s -= dt
        if self.left_s <= 0.0:
            if self.tactic == "CLIMB" and self.climbs and not self.climbs[-1]["ok"]:
                self.climbs[-1]["end"] = "timeout"
            self._new_segment(s, live, pocket, hx, hy)
        self.tactic_s[self.tactic] = self.tactic_s.get(self.tactic, 0.0) + dt
        cs = hero_flags(s)
        grounded = bool(cs.get("onGround", hy <= enc.floor_y + 0.3))
        facing = 1 if (hero.get("facing") or 1) > 0 else -1
        tgt = next((e for e in live if e["iid"] == self.target_iid), None)
        if tgt is None and live and self.tactic != "CLIMB":
            tgt = self._pick_target(live, hx, hy)
            self.target_iid = tgt["iid"]
        move = None
        t = self.tactic

        if t == "CLIMB":
            m = self.climber.act(s, cs)
            self.climb_t += dt
            c = self.climbs[-1] if self.climbs else None
            if self.climber.phase == "TOP":
                if c is not None and not c["ok"]:
                    c.update(ok=True, t_top=round(self.climb_t, 3))
                if pocket and hx < lo + 0.6:
                    self.pocket_s += dt
                # wall slash at a target in reach (WallSlash from the left wall reaches x ~18.3, forum.md §10.4)
                near = [e for e in live if body_box(e)[0] - hx < 4.0 and overlaps(hy - 1.5, hy + 2.5, body_box(e)[1],
                                                                                    body_box(e)[3])]
                if near and r.random() < 0.08 and self._safe_to_hit(s, hx, hy, facing):
                    self._press("attack", self._frames(s, 0.05))
            # the climber holds left; key edges of attack come from _compose
            return self._compose(None, m)

        if tgt is not None:
            x0, y0, x1, y1 = body_box(tgt)
            cx = (x0 + x1) / 2.0
            dx = cx - hx
            gx = max(x0 - hx, hx - x1, 0.0)
            toward = "right" if dx > 0 else "left"
            away = "left" if dx > 0 else "right"
            side = 1 if dx > 0 else -1
            flier = y0 > hy - 1.0 + FLIER_DY
            fx0, fx1 = (hx + SIDE_X[0], hx + SIDE_X[1]) if side > 0 else (hx - SIDE_X[1], hx - SIDE_X[0])
            in_side = overlaps(fx0, fx1, x0, x1) and overlaps(hy + SIDE_Y[0], hy + SIDE_Y[1], y0, y1)
            in_up = overlaps(hx + UP_X[0], hx + UP_X[1], x0, x1) and overlaps(hy + UP_Y[0], hy + UP_Y[1], y0, y1)
            may_hit = self._safe_to_hit(s, hx, hy, facing)
            if t == "PRESS":
                move = toward if gx > 0.8 else None
                if in_side and may_hit and r.random() < 0.3:
                    move = toward if facing != side else move
                    self._press("attack", self._frames(s, 0.05))
                elif in_up and may_hit and r.random() < 0.2:
                    move = move or toward
                    self._press("up", self._frames(s, 0.15))
                    self._press("attack", self._frames(s, 0.05))
                elif flier and abs(dx) < 2.0 and grounded and r.random() < 0.1:
                    self._press("jump", self._frames(s, r.uniform(0.2, 0.45)))
            elif t in ("KEEP", "BAIT"):
                d = self.keep_d if t == "KEEP" or self.bait is None else self.bait[1]
                if abs(dx) > d + 0.4:
                    move = toward
                elif abs(dx) < d - 0.4:
                    move = away
                elif facing != side and r.random() < 0.2:
                    move = toward                                   # face it at the distance (a turn, no step)
                if t == "BAIT" and self.bait is not None:
                    if abs(abs(dx) - self.bait[1]) < 0.6:
                        self.bait_samples[self.bait[0]] = self.bait_samples.get(self.bait[0], 0) + 1
                    if r.random() < 0.01:                           # step across the boundary
                        self.bait = (self.bait[0], self.bait[1] + r.choice((-1.0, 1.0)) * r.uniform(0.6, 1.5))
            elif t == "DASH_IN":
                if self.dash_phase == 0:
                    if 3.0 <= gx <= 9.0 and abs(y0 - hy) < 3.5:
                        if facing != side:
                            move = toward
                        elif may_hit and self._press("dash", 2):
                            self.dash_ins += 1
                            self.dash_phase = 1
                            self.dash_wait = self._frames(s, r.uniform(0.04, 0.14))
                            move = toward
                    elif gx < 3.0:
                        move = away
                    else:
                        move = toward
                elif self.dash_phase == 1:
                    move = toward
                    self.dash_wait -= 1
                    if self.dash_wait <= 0:
                        if self._safe_to_hit(s, hx, hy, facing) and self._press("attack", self._frames(s, 0.05)):
                            self.dash_attacks += 1
                        self.dash_phase = 2
                        self.dash_wait = self._frames(s, 0.5)
                else:
                    self.dash_wait -= 1
                    move = away if self.dash_wait < self._frames(s, 0.3) else None
                    if self.dash_wait <= 0:
                        self.dash_phase = 0
            elif t == "CLAW_IN":
                level = overlaps(hy - 1.0, hy + 2.5, y0, y1)
                if 3.0 <= gx <= 12.0 and level and grounded:
                    if facing != side:
                        move = toward
                    elif self._safe_to_hit(s, hx, hy, facing, line=True) and self._press("clawline",
                                                                                         self._frames(s, 0.05)):
                        self.claw_presses += 1
                elif gx < 3.0:
                    move = away
                else:
                    move = toward if not level else None
            elif t == "UNDER":
                if flier:
                    move = "right" if dx > 0.35 else "left" if dx < -0.35 else None
                    if abs(dx) < 0.6:
                        self.under_s += dt
                        if in_up and may_hit and r.random() < 0.05:
                            move = toward
                            self._press("up", self._frames(s, 0.15))
                            self._press("attack", self._frames(s, 0.05))
                else:
                    move = toward if gx > 2.0 else None
            elif t == "JUMP_OVER":
                if not flier:
                    move = toward
                    if gx < 2.2 and grounded and self._press("jump", self._frames(s, r.uniform(0.32, 0.45))):
                        self.jump_overs += 1
                    if not grounded and abs(dx) < 1.0 and hy > y1 and may_hit and r.random() < 0.15:
                        self._press("down", self._frames(s, 0.2))
                        self._press("attack", self._frames(s, 0.05))
                else:
                    move = toward if gx > 2.0 else None
            elif t == "WALL_BAIT":
                wall = lo if abs(hx - lo) < abs(hx - hi) else hi
                wx = wall + (0.6 if wall == lo else -0.6)
                if abs(hx - wx) > 0.4:
                    move = "left" if hx > wx else "right"
                elif facing != side:
                    move = toward
            elif t == "CLASH":
                boxes = _parryable_boxes(s)
                bells = [b for tk, b in boxes if tk == BELL]
                focus_box = None
                if bells:
                    focus_box = min(bells, key=lambda b: abs((b[0] + b[2]) / 2.0 - hx) + abs((b[1] + b[3]) / 2.0 - hy))
                bx0, by0, bx1, by1 = focus_box or (x0, y0, x1, y1)
                bdx = (bx0 + bx1) / 2.0 - hx
                bside = 1 if bdx > 0 else -1
                gap = max(bx0 - hx, hx - bx1, 0.0)
                if gap > 3.0:
                    move = "right" if bdx > 0 else "left"
                elif gap < 1.2 and focus_box is None:
                    move = "left" if bdx > 0 else "right"
                elif facing != bside:
                    move = "right" if bdx > 0 else "left"
                sx0, sx1 = (hx + SIDE_X[0], hx + SIDE_X[1]) if facing > 0 else (hx - SIDE_X[1], hx - SIDE_X[0])
                for tk, (cx0, cy0, cx1, cy1) in boxes:
                    if overlaps(sx0, sx1, cx0, cx1) and overlaps(hy + SIDE_Y[0], hy + SIDE_Y[1], cy0, cy1):
                        if may_hit and self._press("attack", self._frames(s, 0.05)):
                            self.clash_swings[tk] = self.clash_swings.get(tk, 0) + 1
                        break
            elif t == "EVADE":
                move = away
            if hx < lo + 1.0 and move == "left" or hx > hi - 1.0 and move == "right":
                move = "right" if hx < (lo + hi) / 2 else "left"
        if r.random() < 0.01 and t not in ("CLASH", "WALL_BAIT", "BAIT"):
            self._press("jump", self._frames(s, r.uniform(0.05, 0.4)))
        if hero.get("health", 5) <= 2 and hero.get("silk", 0) >= 9 and r.random() < 0.03:
            self._press("bind", 3)
        return self._compose(move)
