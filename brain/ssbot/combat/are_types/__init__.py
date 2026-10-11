"""The attack-range type registry: one module per Forum type in this package, each defining SPEC (an
ssbot.combat.are_spec.EnemySpec). Adding a type = adding a file here (no shared lines to edit); the builder
(tools.attack_range_build --type <short>) and the live tracker (combat.attack_range.RangeTracker) find it by its type
key or short name. A module may also define, for the builder only:
  CASES        ((session, raw frame, why), ...): the person's own frames for the PNGs;
  SESSIONS     the person's sessions that hold the type (PNGs; the person set is every session);
  NOTES        free text for the build report.
"""
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

_MODS: dict | None = None


def modules() -> dict[str, ModuleType]:
    """{module name: module} of every type module that defines SPEC (imported once)."""
    global _MODS
    if _MODS is None:
        out = {}
        for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
            if m.name.startswith("_"):
                continue
            mod = importlib.import_module(f"{__name__}.{m.name}")
            if getattr(mod, "SPEC", None) is not None:
                out[m.name] = mod
        _MODS = out
    return _MODS


def specs() -> dict:
    """{type key: EnemySpec}."""
    return {mod.SPEC.type_key: mod.SPEC for mod in modules().values()}


def module_of(name: str) -> ModuleType:
    """The type module by its module name, short name or type key (case-insensitive)."""
    n = name.lower()
    for mn, mod in modules().items():
        if n in (mn.lower(), mod.SPEC.short.lower(), mod.SPEC.type_key.lower()):
            return mod
    raise KeyError(f"no attack-range type {name!r} (have {', '.join(modules())})")
