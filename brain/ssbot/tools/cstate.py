"""Decode STATE "hero"["cstate"] (HeroControllerStates bool fields as uint64 words).

Bit (i % 64) of word (i // 64) is field i of the order returned by RPC "schema.cstate" (declaration order in
1.0.30000: facingRight, onGround, jumping, ...). Never hard-code bit numbers: fetch the schema once per connection.

    schema = link.rpc("schema.cstate")
    cs = decode(state["hero"]["cstate"], schema["bools"])
    cs["onGround"]
"""
from collections.abc import Sequence


def decode(words: Sequence[int], names: Sequence[str]) -> dict[str, bool]:
    need = (len(names) + 63) // 64
    if len(words) != need:
        raise ValueError(f"{len(words)} cstate words for {len(names)} fields (expected {need})")
    return {name: bool((words[i >> 6] >> (i & 63)) & 1) for i, name in enumerate(names)}


def encode(values: dict[str, bool], names: Sequence[str]) -> list[int]:
    """Inverse of decode (tests, replay tools)."""
    words = [0] * ((len(names) + 63) // 64)
    for i, name in enumerate(names):
        if values.get(name):
            words[i >> 6] |= 1 << (i & 63)
    return words


def ints(values: Sequence[int], names: Sequence[str]) -> dict[str, int]:
    """STATE "hero"["cstate_int"] with schema.cstate "ints"."""
    if len(values) != len(names):
        raise ValueError(f"{len(values)} cstate ints for {len(names)} names")
    return dict(zip(names, values))
