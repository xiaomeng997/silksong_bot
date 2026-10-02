"""Candidate command sequences for the planner (DESIGN §3.5.4 `expand(s, prefs, depth=3, dt=4 frames)`; M2 plan:
long moves as macro primitives).

A candidate is a commanded button mask per frame over the horizon, built from a first primitive (frames 0-3, the part
that is executed: the planner re-plans every frame) and a continuation (frames 4..T-1) that shows the first primitive
leaves a safe way on. Front-dense: the continuations are a library of whole-horizon behaviours (stay, run, jump now
or after a wait, attack, run then jump ...) rather than two more 4-frame levels, so 21 first primitives x 17
continuations (357) stay well within the 512-rollout budget while still holding the jump timings a charge or a rolling bell
needs (the planner re-plans each frame, so finer timing comes from the next tick). A JUMP(h) holds jump h frames from
its start whatever comes after (a committed hold; the kinematics' HoldFilter replays min press / release).

Bell Beast vocabulary (the savestate hero has no dash, double jump, wall jump or glide): MOVE(L/R), WAIT, JUMP(hold
4 / 11 / 24 / 48 frames: a release halves the rising speed every frame, so the apex grows up to about 24 frames of hold
(box bottom 5.4 u up) and the air hang with it: with 48 frames the box stays more than 3.2 u up for 35 frames, what
clearing a charge needs, kinematics rollout from the floor), ATTACK(side, with
none / L / R held: a side key turns first), ATTACK(up) and ATTACK(down) with a side key held (an up / down edge without
one starts an interaction, InteractManager.cs:244), SILKSKILL (Silkspear, quickcast), BIND (macro: the whole 1.34-1.37 s
Bind plus the rest of its horizon). Attack, quickcast and bind are 3-frame presses (holding attack charges a nail art).

Codes (ssbot.core.primitives) per candidate make the supervisor's allowlist a mask: a candidate is allowed when every
primitive it uses is.
"""
from dataclasses import dataclass

import numpy as np

from ssbot.core.primitives import Prim
from ssbot.knowledge.kinematics import B_ATTACK, B_BIND, B_DOWN, B_JUMP, B_LEFT, B_QUICKCAST, B_RIGHT, B_UP

FIRST = 4                      # frames of the first primitive
PRESS = 3                      # attack / quickcast / bind press length
JUMP_HOLDS = (11, 24, 48)
DIRS = {"N": 0, "L": B_LEFT, "R": B_RIGHT}


@dataclass(frozen=True, slots=True)
class Piece:
    name: str
    masks: np.ndarray          # [n] commanded masks from its first frame
    prims: frozenset[Prim]


def _seq(n: int, base: int = 0) -> np.ndarray:
    return np.full(n, base, np.int64)


def _first_pieces() -> list[Piece]:
    out = [Piece("WAIT", _seq(FIRST), frozenset({Prim.WAIT}))]
    for d in ("L", "R"):
        out.append(Piece(f"MOVE({d})", _seq(FIRST, DIRS[d]), frozenset({Prim.MOVE})))
    for h in JUMP_HOLDS:
        for d in ("N", "L", "R"):
            m = _seq(max(h, FIRST))
            m[:FIRST] |= DIRS[d]
            m[:h] |= B_JUMP
            prims = {Prim.JUMP} | ({Prim.MOVE} if d != "N" else set())
            out.append(Piece(f"JUMP({h}){d}", m, frozenset(prims)))
    for d in ("N", "L", "R"):
        m = _seq(FIRST, DIRS[d])
        m[1:1 + PRESS] |= B_ATTACK
        out.append(Piece(f"ATTACK(side){d}", m, frozenset({Prim.ATTACK_SIDE} | ({Prim.MOVE} if d != "N" else set()))))
    for d in ("L", "R"):
        m = _seq(FIRST, DIRS[d] | B_UP)
        m[1:1 + PRESS] |= B_ATTACK
        out.append(Piece(f"ATTACK(up){d}", m, frozenset({Prim.ATTACK_UP, Prim.MOVE})))
        m = _seq(FIRST, DIRS[d] | B_DOWN)
        m[1:1 + PRESS] |= B_ATTACK
        out.append(Piece(f"ATTACK(down){d}", m, frozenset({Prim.ATTACK_DOWN, Prim.MOVE})))
    for d in ("L", "R"):
        m = _seq(FIRST, DIRS[d])
        m[1:1 + PRESS] |= B_QUICKCAST
        out.append(Piece(f"SILKSKILL(0){d}", m, frozenset({Prim.SILKSKILL} | ({Prim.MOVE} if d != "N" else set()))))
    return out


def _continuations(T: int) -> list[Piece]:
    """Whole-horizon behaviours after the first primitive. Stops at several run lengths matter: with only "run to the
    end" and "wait, then run", a target 6 u away is reached without overshooting only by waiting first, and a plan
    re-chosen every frame then waits forever (live run 20261002_033921: the hero stood 6 u from every Leap Land).
    Pruned by use in 16 cleared episodes (run 20261002_042949, 122 k ticks: moving 24-frame jumps, run-then-jump and
    the 16-frame wait-then-jump chosen in under 0.1 % of ticks each) to keep the tick in budget."""
    n = T - FIRST
    out = [Piece("idle", _seq(n), frozenset({Prim.WAIT}))]
    for d in ("L", "R"):
        out.append(Piece(f"run{d}", _seq(n, DIRS[d]), frozenset({Prim.MOVE})))
        for k in (8, 16, 28):
            m = _seq(n)
            m[:k] = DIRS[d]
            out.append(Piece(f"run{d}{k}_stop", m, frozenset({Prim.MOVE, Prim.WAIT})))
        m = _seq(n)
        m[:16] = DIRS[d]
        m[16:16 + PRESS] |= B_ATTACK
        out.append(Piece(f"run{d}16_attack", m, frozenset({Prim.MOVE, Prim.ATTACK_SIDE, Prim.WAIT})))
    for h, dirs in ((24, ("N",)), (48, ("N", "L", "R"))):
        for d in dirs:
            m = _seq(n, DIRS[d])
            m[:h] |= B_JUMP
            out.append(Piece(f"jump{h}{d}", m, frozenset({Prim.JUMP} | ({Prim.MOVE} if d != "N" else set()))))
    m = _seq(n)
    m[8:8 + 48] |= B_JUMP
    out.append(Piece("wait8_jump", m, frozenset({Prim.JUMP, Prim.WAIT})))
    m = _seq(n)
    m[2:2 + PRESS] |= B_ATTACK
    out.append(Piece("attack", m, frozenset({Prim.ATTACK_SIDE})))
    return out


@dataclass
class CandidateSet:
    """cmd [N, T] commanded masks; first [N] index of the first primitive; cont [N] index of the continuation;
    names; prim_bits [N] bit set of the primitive codes used (1 << Prim)."""
    cmd: np.ndarray
    first: np.ndarray
    cont: np.ndarray
    first_names: list[str]
    cont_names: list[str]
    prim_bits: np.ndarray
    bind: np.ndarray           # [N] bool: a Bind macro
    T: int

    def name(self, i: int) -> str:
        if self.bind[i]:
            return "BIND"
        c = self.cont[i]
        return f"{self.first_names[self.first[i]]}+{self.cont_names[c]}" if c >= 0 else self.first_names[self.first[i]]

    def subset(self, keep: np.ndarray) -> "CandidateSet":
        """The candidates where keep [N] is true (first-primitive indices kept as they are)."""
        k = np.asarray(keep, bool)
        return CandidateSet(self.cmd[k], self.first[k], self.cont[k], self.first_names, self.cont_names,
                            self.prim_bits[k], self.bind[k], self.T)

    def allowed(self, allowed_mask: np.ndarray) -> np.ndarray:
        """[N] bool: every primitive the candidate uses is in the supervisor's allowlist (bool[N_PRIM])."""
        ok_bits = int(sum(1 << i for i, a in enumerate(allowed_mask) if a))
        return (self.prim_bits & ~ok_bits) == 0


def _bits(prims) -> int:
    return int(sum(1 << int(p) for p in prims))


def build(T: int = 48) -> CandidateSet:
    """The standard set: every first primitive x every continuation (21 x 17 = 357 for T = 48)."""
    firsts, conts = _first_pieces(), _continuations(T)
    N = len(firsts) * len(conts)
    cmd = np.zeros((N, T), np.int64)
    first = np.zeros(N, np.int64)
    cont = np.zeros(N, np.int64)
    bits = np.zeros(N, np.int64)
    i = 0
    for a, fp in enumerate(firsts):
        for b, cp in enumerate(conts):
            cmd[i, FIRST:] = cp.masks
            k = min(len(fp.masks), T)
            cmd[i, :FIRST] = fp.masks[:FIRST]
            if k > FIRST:                          # a committed jump hold runs on into the continuation
                cmd[i, FIRST:k] |= fp.masks[FIRST:k] & B_JUMP
            first[i], cont[i] = a, b
            bits[i] = _bits(fp.prims | cp.prims)
            i += 1
    return CandidateSet(cmd, first, cont, [p.name for p in firsts], [p.name for p in conts], bits,
                        np.zeros(N, bool), T)


NO_CONTROL_FIRST = ("WAIT", "MOVE(L)", "MOVE(R)", "JUMP(11)N", "JUMP(11)L", "JUMP(11)R")


def no_control(cs: CandidateSet) -> CandidateSet:
    """While the hero has no control (hit-stop, recoil, a cast, a Bind, another FSM's lock) the first frames' keys
    only queue, so the first primitive matters little: keep a few (6 x the continuations). Hurt lanes do not collapse
    in the rollout (every timing lane differs), so this is also where the tick is most expensive."""
    names = {n: i for i, n in enumerate(cs.first_names)}
    keep = np.isin(cs.first, [names[n] for n in NO_CONTROL_FIRST if n in names])
    return cs.subset(keep)


def bind_macro(T: int) -> CandidateSet:
    """BIND: bind pressed for PRESS frames, then nothing until T (the Bind runs 81-83 frames)."""
    cmd = np.zeros((1, T), np.int64)
    cmd[0, :PRESS] = B_BIND
    return CandidateSet(cmd, np.zeros(1, np.int64), np.full(1, -1, np.int64), ["BIND"], [],
                        np.array([_bits({Prim.BIND, Prim.WAIT})], np.int64), np.ones(1, bool), T)


def continue_plan(prev: np.ndarray, shift: int, T: int) -> np.ndarray:
    """A previous plan's commanded masks moved on by `shift` frames, padded with its last frame's movement keys."""
    out = np.zeros(T, np.int64)
    rest = prev[shift:]
    k = min(len(rest), T)
    out[:k] = rest[:k]
    if k < T:
        out[k:] = (prev[-1] if len(prev) else 0) & (B_LEFT | B_RIGHT)
    return out
