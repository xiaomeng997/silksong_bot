"""The shared primitive vocabulary (ssbot.core.primitives) against DESIGN.md §3.5.4 / §3.6.3, its parser, and the
supervisor's allowlists built on it (an unknown name is never allowed)."""
import re
from pathlib import Path

from ssbot.core import primitives as pr
from ssbot.core.primitives import Prim

DESIGN = Path(__file__).resolve().parents[2] / "docs" / "DESIGN.md"


def _design_list(pattern: str) -> list[str]:
    text = DESIGN.read_text("utf-8")
    m = re.search(pattern, text)
    assert m, pattern
    return m


def test_combat_vocabulary_is_design_3_5_4_verbatim():
    m = _design_list(r"\*\*原语：\*\* (.+?)。每个都做合法性检查")
    items = [x.strip().strip("*") for x in m.group(1).split("、")]
    assert tuple(items) == pr.COMBAT_VOCABULARY


def test_interaction_vocabulary_is_design_3_6_3():
    text = DESIGN.read_text("utf-8")
    block = text[text.index("**新增原语：**"):text.index("**规则：** 每一步闭环验证")]
    assert tuple(re.findall(r"`([A-Z_]+\([^`]*\))`", block)) == pr.INTERACTION_VOCABULARY


def test_every_design_primitive_has_a_code():
    kinds = {re.match(r"[A-Z_]+", x).group(0) for x in pr.COMBAT_VOCABULARY + pr.INTERACTION_VOCABULARY}
    for k in kinds:
        assert k in pr._ARGS, k
    assert pr.N_PRIM == len(Prim) == 18 and pr.COMBAT | pr.INTERACTIONS == pr.ALL
    assert pr.EVASIVE.isdisjoint(pr.DAMAGING) and pr.EVASIVE.isdisjoint(pr.INTERACTIONS)
    assert Prim.BIND not in pr.EVASIVE | pr.DAMAGING          # a Bind is neither: forbidden whenever EVASIVE-only


def test_parse_and_name_round_trip():
    cases = {"MOVE": (Prim.MOVE, None), "JUMP(12)": (Prim.JUMP, 12), "JUMP(max)": (Prim.JUMP, "max"),
             "ATTACK(side)": (Prim.ATTACK_SIDE, None), "ATTACK(up)": (Prim.ATTACK_UP, None),
             "ATTACK(down)": (Prim.ATTACK_DOWN, None), "TOOL(0)": (Prim.TOOL, 0), "SILKSKILL(2)": (Prim.SILKSKILL, 2),
             "WAIT": (Prim.WAIT, None), "WAIT(8)": (Prim.WAIT, 8), "ABORT": (Prim.ABORT, None),
             "INTERACT(UP)": (Prim.INTERACT_UP, None), "NEEDOLIN_PLAY(90)": (Prim.NEEDOLIN_PLAY, 90),
             "HIT_TARGET(bell)": (Prim.HIT_TARGET, "bell"), " DASH ": (Prim.DASH, None)}
    for text, want in cases.items():
        assert pr.parse(text) == want, text
        p, arg = want
        assert pr.parse(pr.name(p, arg)) == want


def test_unknown_or_malformed_names_parse_to_none():
    for bad in ("ATTACK", "ATTACK(left)", "TOOL", "TOOL(x)", "TOOL(-1)", "SILKSKILL", "HARPOON", "PARRY", "move",
                "MOVE(1)", "JUMP", "JUMP(1.5)", "INTERACT", "INTERACT(DOWN)", "HIT_TARGET(door)", "", "ATTACK(down",
                None, 3.0):
        assert pr.parse(bad) is None, bad
        assert pr.code(bad) is None, bad
    assert pr.code(Prim.DASH) is Prim.DASH and pr.code(3) is Prim.DASH
    assert pr.code(99) is None and pr.code(-1) is None and pr.code(True) is None
