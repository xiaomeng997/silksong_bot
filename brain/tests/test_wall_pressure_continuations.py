"""Wall restrictions also apply to the two existing N2 continuation kinds."""
from dataclasses import dataclass
from types import SimpleNamespace as NS

from ssbot.combat.knife_chain_air_native import NativeManualAirChain as Native
from ssbot.combat.knife_chain_commitment import ContactScan, MoveInstance
from ssbot.combat import knife_chain_post_actions as Post


@dataclass
class Path:
    origin: int = 90
    through: int = 100
    stage: str = "approach"
    end: str = "bounce"
    kind: str = "parent"
    full: bool = False


def setup(monkeypatch):
    calls = []
    def ordinary(parent, params, terrain, *, kind, profile, full=False):
        assert parent.stage == "commitment"
        calls.append((kind, full))
        return Path(100, 150 if full else 112, "continuation", "handback" if full else "short", kind, full)
    monkeypatch.setattr(Post, "ordinary_post", ordinary)
    geo = NS(ref=lambda p: p.kind,
             scan=lambda p: ContactScan(p.kind, p.origin, p.through, (), "enemy geometry clear"))
    n = NS(profile=NS(short_frames=12), continuation_executable=lambda kind, p: True)
    args = (n, Path(), NS(params=object(), terrain=object()), geo, MoveInstance(7, 80, "CC_SLAM"))
    return args, calls


def test_default_has_the_original_two_kind_lower_bound_and_no_full_query(monkeypatch):
    args, calls = setup(monkeypatch)
    out = Native._continuations(*args)
    assert (out.verdict, out.mode) == ("pass", "lower_bound")
    assert out.qualifying_kinds == ("left_landing", "right_landing")
    assert calls == [("left_landing", False), ("right_landing", False)]


def test_short_wall_contact_cannot_count_either_kind_or_relabel_an_exit(monkeypatch):
    args, calls = setup(monkeypatch)
    out = Native._continuations(*args, wall_validator=lambda p: False)
    assert out.verdict == "reject" and out.qualifying_kinds == ()
    assert len(out.checks) == 2 and all(c.stage == "entry" and c.verdict == "reject" for c in out.checks)
    assert calls == [("left_landing", False), ("right_landing", False)]


def test_wall_in_full_survivor_cannot_produce_a_full_exit_pass(monkeypatch):
    args, calls = setup(monkeypatch)
    def wall_free(p):
        return p.kind == "left_landing" and not p.full
    out = Native._continuations(*args, wall_validator=wall_free)
    assert out.verdict != "pass" and out.qualifying_kinds == ("left_landing",)
    assert out.full_checked == ("left_landing",)
    assert calls == [("left_landing", False), ("right_landing", False), ("left_landing", True)]
    assert out.checks[-1].stage == "full" and out.checks[-1].verdict != "pass"


def test_yielded_context_is_residual_accounting_without_candidate_ownership():
    n = Native.__new__(Native)
    n._candidate_enabled = True
    n.runner = NS(run=None)
    move = MoveInstance(7, 80, "CC_SLAM")
    n._wall_pressure = dict(goal=NS(responsibility=move), landing=False, yielded=False)
    assert n.candidate_generation and n.residual_context() is None
    n._wall_pressure.update(landing=True, yielded=True)
    assert not n.candidate_generation
    assert n.residual_context() == {"source_move": {"target_iid": 7, "antic_frame": 80, "family": "CC_SLAM"},
                                    "kind": "wall_pressure_residual", "input_owner": False}
    n._wall_pressure = None
    assert n.residual_context() is None
