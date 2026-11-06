"""ONE watched observational bout (Task 179 #310; the person, Sol seq 230).

Opt-in and labelled: SSBOT_FORUM_OBSERVE_BOUT=1. Ordinary and chain-related HP losses are logged, never a stop (no
low-HP quit, no first-loss stop). A lethal hit the oracle's LethalBlock vetoed (a "catastrophe" / "would_die" event
with blocked true: the existing TRAIN guard, no new cheat) is recorded - the first one and every later hit apart - and
play goes on. An unblocked lethal hit, a dead hero, guard / input / receipt / log / resource faults and a user stop
still stop. One bout, the eval start (7 HP), a 45 s game-time bound or the natural end. Without the switch every
normal eval / statistics path is unchanged; a bout run with it is never an ordinary survival or no-hit result.
"""
from __future__ import annotations

import os

ENV = "SSBOT_FORUM_OBSERVE_BOUT"
POLICY = "observe-one-bout-v1"
GAME_LIMIT_S = 45.0
LETHAL_KINDS = ("catastrophe", "would_die")


def enabled(environ=None) -> bool:
    env = os.environ if environ is None else environ
    value = str(env.get(ENV, "0")).strip()
    if value not in {"0", "1"}:
        raise ValueError("invalid " + ENV)
    return value == "1"


def vetoed(data) -> bool:
    """A lethal event the guard blocked (a healthy veto): never a stop under the observation semantics."""
    return isinstance(data, dict) and data.get("blocked") is True


def guard_ok(guards) -> bool:
    """The oracle's guards.get: LethalBlock on (block), every guard healthy, TRAIN profile, nothing refused. The
    observation's no-HP-stop rests on it; without it the bout must not start."""
    return (isinstance(guards, dict) and guards.get("lethal_block") == "block" and guards.get("profile") == "TRAIN"
            and isinstance(guards.get("healthy"), dict) and bool(guards["healthy"])
            and all(v is True for v in guards["healthy"].values()) and not guards.get("refused"))


def label() -> dict:
    return {"policy": POLICY, "game_limit_s": GAME_LIMIT_S, "bouts": 1, "start": "eval start, 7 HP",
            "hp_stop": None, "lethal": "blocked veto recorded, play goes on; unblocked lethal / dead hero stops",
            "scope": "behaviour observation; not a no-hit, survival or mortality result"}
