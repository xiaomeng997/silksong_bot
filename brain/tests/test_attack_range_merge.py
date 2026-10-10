"""Stage C (task attack range: all types): the merged registry and the shared hooks of the three stage B branches."""
from __future__ import annotations

import inspect

from ssbot.combat.are_spec import EnemySpec
from ssbot.combat.are_types import specs
from ssbot.combat.attack_range import RangeTable
from ssbot.tools.attack_range_build import _attach

TYPES = {"Song Pilgrim 03", "Song Heavy Sentry", "Song Pilgrim 01", "Song Handmaiden", "Spear", "Song Reed",
         "Song Administrator", "Pilgrim 03 Song", "Song Pilgrim Maestro", "Song Automaton Tiny"}


def test_registry_has_every_forum_type():
    assert TYPES <= set(specs())


def test_spec_carries_every_stage_b_hook():
    names = {f for f in EnemySpec.__dataclass_fields__}
    assert {"on_step", "place_fn", "coast", "hit_started", "custom", "attach"} <= names


def test_place_takes_vel_and_ctx():
    ps = inspect.signature(RangeTable.place).parameters
    assert "vel" in ps and "ctx" in ps


def test_attach_dispatches_two_and_three_parameter_hooks():
    seen = []

    def two(c, trs):
        seen.append(("two", c, len(trs)))

    def three(c, trs, spec):
        seen.append(("three", c, len(trs), spec))

    _attach(two, "cache", [1, 2], "spec")
    _attach(three, "cache", [1], "spec")
    assert seen == [("two", "cache", 2), ("three", "cache", 1, "spec")]


def test_each_type_uses_one_attach_form():
    """A spec's own attach and its module's attach are the same function when both exist (one call per build)."""
    from ssbot.combat.are_types import modules
    for mod in modules().values():
        sp, ma = mod.SPEC.attach, getattr(mod, "attach", None)
        if sp is not None and ma is not None:
            assert sp is ma, mod.__name__
