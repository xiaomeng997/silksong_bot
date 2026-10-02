"""The action-primitive vocabulary shared by the planner (combat/, W4), the interaction scripts (run/interact) and the
safety supervisor, so a supervisor allowlist and a planner candidate always speak the same names.

DESIGN §3.5.4 lists the combat primitives: MOVE, JUMP(hold), DOUBLEJUMP, DASH, WALLJUMP, GLIDE, ATTACK(side/up/down),
TOOL(i), SILKSKILL(k), CLAWLINE, BIND, WAIT, ABORT; §3.6.3 adds three interaction primitives: INTERACT(UP),
NEEDOLIN_PLAY(duration), HIT_TARGET(lever|bell|cage). tests/test_primitives.py checks both lists against DESIGN.md.

Codes are small ints so a numba planner can index a boolean allow mask (SupervisorDecision.allowed_mask) per
candidate. ATTACK has one code per direction because safety rules differ by direction (a down-slash over spikes is
never allowed, §3.5.6); TOOL / SILKSKILL / JUMP / WAIT / NEEDOLIN_PLAY / HIT_TARGET carry their argument outside the
code (slot, skill, hold frames ...), which no safety rule depends on.

Text form (logs, playbook YAML): "MOVE", "JUMP(12)", "ATTACK(down)", "TOOL(0)", "SILKSKILL(1)", "INTERACT(UP)",
"HIT_TARGET(bell)". parse() returns None for anything it does not know, and a caller must treat None as forbidden.
"""
import re
from enum import IntEnum

COMBAT_VOCABULARY = ("MOVE", "JUMP(hold)", "DOUBLEJUMP", "DASH", "WALLJUMP", "GLIDE", "ATTACK(side/up/down)", "TOOL(i)",
                     "SILKSKILL(k)", "CLAWLINE", "BIND", "WAIT", "ABORT")                         # §3.5.4, verbatim
INTERACTION_VOCABULARY = ("INTERACT(UP)", "NEEDOLIN_PLAY(duration)", "HIT_TARGET(lever|bell|cage)")  # §3.6.3


class Prim(IntEnum):
    MOVE = 0
    JUMP = 1
    DOUBLEJUMP = 2
    DASH = 3
    WALLJUMP = 4
    GLIDE = 5
    ATTACK_SIDE = 6
    ATTACK_UP = 7
    ATTACK_DOWN = 8
    TOOL = 9
    SILKSKILL = 10
    CLAWLINE = 11
    BIND = 12
    WAIT = 13
    ABORT = 14
    INTERACT_UP = 15
    NEEDOLIN_PLAY = 16
    HIT_TARGET = 17


N_PRIM = len(Prim)
ALL: frozenset[Prim] = frozenset(Prim)
COMBAT: frozenset[Prim] = frozenset(p for p in Prim if p <= Prim.ABORT)
INTERACTIONS: frozenset[Prim] = frozenset({Prim.INTERACT_UP, Prim.NEEDOLIN_PLAY, Prim.HIT_TARGET})
ATTACKS: frozenset[Prim] = frozenset({Prim.ATTACK_SIDE, Prim.ATTACK_UP, Prim.ATTACK_DOWN})
# Movement that neither strikes anything nor starts an interaction: the only primitives PAUSE_PENDING allows (§3.7.4).
EVASIVE: frozenset[Prim] = frozenset({Prim.MOVE, Prim.JUMP, Prim.DOUBLEJUMP, Prim.DASH, Prim.WALLJUMP, Prim.GLIDE,
                                      Prim.WAIT, Prim.ABORT})
# Can land a hit on an enemy, so can kill it (the kill freeze swallows a pause, §3.7.3 YELLOW).
DAMAGING: frozenset[Prim] = ATTACKS | {Prim.TOOL, Prim.SILKSKILL, Prim.CLAWLINE, Prim.HIT_TARGET}

_ATTACK_DIR = {"side": Prim.ATTACK_SIDE, "up": Prim.ATTACK_UP, "down": Prim.ATTACK_DOWN}
_TARGETS = ("lever", "bell", "cage")
_RE = re.compile(r"^([A-Z_]+)(?:\(([^()]*)\))?$")
# kind -> argument rule: None (no argument), "int" (required non-negative int), "int?" (optional), or a tuple of words
_ARGS: dict[str, object] = {
    "MOVE": None, "JUMP": "int|max", "DOUBLEJUMP": None, "DASH": None, "WALLJUMP": None, "GLIDE": None,
    "ATTACK": tuple(_ATTACK_DIR), "TOOL": "int", "SILKSKILL": "int", "CLAWLINE": None, "BIND": None, "WAIT": "int?",
    "ABORT": None, "INTERACT": ("UP",), "NEEDOLIN_PLAY": "int", "HIT_TARGET": _TARGETS,
}


def _int(a: str) -> int | None:
    return int(a) if a.isdigit() else None


def parse(name: str) -> tuple[Prim, int | str | None] | None:
    """'ATTACK(down)' -> (Prim.ATTACK_DOWN, None); 'TOOL(2)' -> (Prim.TOOL, 2); 'JUMP(max)' -> (Prim.JUMP, 'max').
    None for an unknown kind or a malformed / missing / extra argument."""
    m = _RE.match(name.strip()) if isinstance(name, str) else None
    if m is None:
        return None
    kind, arg = m.group(1), m.group(2)
    rule = _ARGS.get(kind, "unknown")
    if rule == "unknown":
        return None
    if rule is None:
        return (Prim[kind], None) if arg is None else None
    if isinstance(rule, tuple):
        if arg not in rule:
            return None
        if kind == "ATTACK":
            return _ATTACK_DIR[arg], None
        return (Prim.INTERACT_UP, None) if kind == "INTERACT" else (Prim[kind], arg)
    if arg is None:
        return (Prim[kind], None) if rule == "int?" else None
    if rule == "int|max" and arg == "max":
        return Prim[kind], arg
    v = _int(arg)
    return None if v is None else (Prim[kind], v)


def code(p: "Prim | int | str") -> Prim | None:
    """A primitive code from a code, an int or a text name; None when unknown."""
    if isinstance(p, Prim):
        return p
    if isinstance(p, int) and not isinstance(p, bool):
        return Prim(p) if 0 <= p < N_PRIM else None
    r = parse(p) if isinstance(p, str) else None
    return None if r is None else r[0]


def name(p: Prim, arg: int | str | None = None) -> str:
    """Text form of a primitive instance (the inverse of parse)."""
    if p in ATTACKS:
        return f"ATTACK({p.name.split('_')[1].lower()})"
    if p == Prim.INTERACT_UP:
        return "INTERACT(UP)"
    return p.name if arg is None else f"{p.name}({arg})"
