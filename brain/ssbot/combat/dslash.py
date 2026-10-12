"""Delayed and chained down slashes in the Forum planner (task 1v1 G3; the person 2026-10-12, plan doc "绝招带后手；规划器加
延迟下劈" (3)): the Forum planner could down-slash only "now" (ATTACK(down)L/R as an air row's first 4 frames, always
with a side key); a ground jump followed by a down slash was two separate decisions, so choosing the jump never counted
the strike, and no row had a second down slash. The boss planner's pogo macro (candidates.pogo_grid) has these; this is
the Forum planner's family:

- ground: jump now x hold (GROUND_HOLDS) x press delay (GROUND_PRESS frames from the jump press) x key before the
  press (L / N / R);
- air: down slash now or after w frames (AIR_W), key before the press L / N / R (N: in place, no side key);
- after a bounce: a second down slash with NO jump press in the air, CHAIN_B frames after the bounce; rows run past
  the horizon where the second press needs it (the planner's row is the first T frames, the rest is checked as the
  row's tail).

Waits before the jump are not enumerated: the planner re-plans every frame. Prefilter: a template is kept only when
its blade, in the down slash's active frames, meets a target's predicted body (grown PREFILTER_GROW_U); only those get
the keys after the press (L / N / R), the chain and the full checks.

The certain-hit rule (the person 2026-10-11: a down slash on an enemy in a move is a certain hit): when the target is
in a tracked move (attack_range.Segmenter instance) and the contact holds under the move's timing variants (the
predicted body shifted by CERT_SHIFTS frames along its path) and its lunge-phase variant (the body stopped where it is
now: the prediction moves it on at its present velocity, a lunge may end any frame; on the Clapper's slam the moving
prediction put strikes up to 9 u in front of where the body stops), the row is judged from the press on on its bounce branch
only; else on both branches as today (the miss lane and the hit branch). A second strike that is certain counts as an
extra landed hit; one past the horizon is credited to the ranking.

Switches (all default off; with SSBOT_FORUM_DSLASH off nothing here runs):
- SSBOT_FORUM_DSLASH=1: the family.
- SSBOT_FORUM_DSLASH_CERT=0: no certain-hit rule (every family row on both branches, no chain rows).
- SSBOT_FORUM_DSLASH_CHAIN=0: no second strike.
- SSBOT_FORUM_DSLASH_MAX (24): rows per tick at most (chains, then certain rows, then the earliest contact);
  at most SURV_MAX templates pass the prefilter (the earliest contact first).
"""
import os

import numpy as np

from ssbot.knowledge.kinematics import B_ATTACK, B_DOWN, B_JUMP, B_LEFT, B_RIGHT

DSLASH = os.environ.get("SSBOT_FORUM_DSLASH", "0") == "1"
CERT = os.environ.get("SSBOT_FORUM_DSLASH_CERT", "1") != "0"
CHAIN = os.environ.get("SSBOT_FORUM_DSLASH_CHAIN", "1") != "0"
MAX_ROWS = int(os.environ.get("SSBOT_FORUM_DSLASH_MAX", "24") or 24)
# SSBOT_FORUM_DSLASH_EVPRE=1 (task 1v1 G4, 5b): the bounce event on the mask before the contact frame (the bounce
# on the contact frame itself: SlamTheory's and the special mode's convention; T1's live probe1 27 bounces, the
# real position 6 frames on: p50 0.002 u with it vs 0.307 u with the event on the contact frame's mask)
EVPRE = os.environ.get("SSBOT_FORUM_DSLASH_EVPRE", "0") == "1"
SURV_MAX = 12                                 # prefilter survivors expanded at most (the earliest contact first)

GROUND_HOLDS = (3, 8, 14, 20)
GROUND_PRESS = tuple(range(3, 34, 3))          # the attack's first mask, frames after the jump press
AIR_W = (0, 1, 2, 3, 4, 6, 8, 10, 12, 15, 18, 21, 24, 28, 32)   # air: the press after w frames (mask w + 1)
CHAIN_B = (20, 24, 28, 32, 36, 40)            # the second press, frames after the first bounce
KEYS = {"L": B_LEFT, "N": 0, "R": B_RIGHT}
PREFILTER_GROW_U = 0.4                        # the prefilter's target box growth (the keys after the press move it)
CERT_SHIFTS = np.array([-2, -1, 1, 2], np.int64)   # frames: the body's timing variants for the certain-hit rule
DOWN_PRE = 1                                  # the down key from the press - DOWN_PRE ...
DOWN_LEN = 6                                  # ... for DOWN_LEN frames (candidates.pogo_grid)
PRESS = 3                                     # the attack press (frames)
POST_F = 14                                   # template frames after a press (the active window and a margin)
LMAX = 80                                     # the longest row (frames after the prefix): the chain's second press
CHAIN_MAX = 16                                # chain rows per tick at most


def strike(m: np.ndarray, p: int) -> None:
    """The down slash pressed on mask p of m (in place): down from p - DOWN_PRE for DOWN_LEN frames, attack p..p+2."""
    L = len(m)
    m[max(p - DOWN_PRE, 0):min(p - DOWN_PRE + DOWN_LEN, L)] |= B_DOWN
    m[p:min(p + PRESS, L)] |= B_ATTACK


def templates(posture: str, jump_rem: int = 0) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """The prefilter templates of a posture ("ground" / "air"): masks [n, L] (L: the last press + POST_F), the press
    mask index [n] and names. jump_rem (air): the committed jump hold's remaining frames, held from mask 0."""
    rows, pj, names = [], [], []
    if posture == "ground":
        L = max(GROUND_PRESS) + POST_F
        for h in GROUND_HOLDS:
            for p in GROUND_PRESS:
                for d, kb in KEYS.items():
                    m = np.zeros(L, np.int64)
                    m[:h] |= B_JUMP
                    m[:p] |= kb
                    strike(m, p)
                    rows.append(m)
                    pj.append(p)
                    names.append(f"DS j{h}p{p}{d}")
    elif posture == "air":
        L = max(AIR_W) + 1 + POST_F
        for w in AIR_W:
            p = w + 1
            for d, kb in KEYS.items():
                m = np.zeros(L, np.int64)
                if jump_rem > 0:
                    m[:jump_rem] |= B_JUMP
                m[:p] |= kb
                strike(m, p)
                rows.append(m)
                pj.append(p)
                names.append(f"DS a{w}{d}")
    if not rows:
        return np.zeros((0, 1), np.int64), np.zeros(0, np.int64), []
    return np.asarray(rows, np.int64), np.asarray(pj, np.int64), names


def expand(tpl: np.ndarray, pj: np.ndarray, names: list[str], T: int) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """The survivors with the key after the press (L / N / R from the press on, the slash's own down / attack kept):
    masks [n * 3, T], press [n * 3], names."""
    out, pp, nm = [], [], []
    for q in range(len(tpl)):
        p = int(pj[q])
        for d, kb in KEYS.items():
            m = np.zeros(T, np.int64)
            k = min(T, tpl.shape[1])
            m[:k] = tpl[q, :k]
            m[p:] &= ~(B_LEFT | B_RIGHT)
            m[p:] |= kb
            out.append(m)
            pp.append(p)
            nm.append(f"{names[q]}>{d}")
    return np.asarray(out, np.int64).reshape(-1, T), np.asarray(pp, np.int64), nm


def chain(m: np.ndarray, p2: int, L: int) -> np.ndarray:
    """The row m (the first strike, its key after the press held on) run on to L masks with a second down slash on mask
    p2 and no jump press after the first strike's press."""
    out = np.zeros(L, np.int64)
    k = min(L, len(m))
    out[:k] = m[:k]
    if L > k:
        out[k:] = m[-1] & (B_LEFT | B_RIGHT)
    strike(out, p2)
    return out


__all__ = ["DSLASH", "CERT", "CHAIN", "MAX_ROWS", "templates", "expand", "chain", "strike", "CERT_SHIFTS",
           "PREFILTER_GROW_U", "CHAIN_B", "LMAX", "CHAIN_MAX"]
