"""Reference chain evaluation and draft isolation, not a live execution certificate."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ssbot.combat.knife_chain_format import chains_from_json, ChainFormatError
from ssbot.combat.knife_chain_eval import ChainRunner, Prims, Run, X, register_core


def table(rules=None):
    links = {"start": {"id": "test.start", "phase": "start", "rules": rules or [], "keys": [{"mask": "R"}]},
             "end": {"id": "test.end", "phase": "end", "entry": {"p": "allow"}, "keys": [{"mask": "A"}]}}
    return chains_from_json({"test": {"id": "test", "start": "start", "links": links,
        "vars": {"a": 1, "b": 2, "tmp.n": None},
        "admission": {k: {"link": "test." + k, "observations": [], "conditions": []} for k in links}}})


class Anchor:
    def __init__(self):
        self.reset_count = 0
    def reset(self, runner):
        self.reset_count += 1
    def clock(self, x, name):
        return x.obs.f
    def step(self, runner, f, s, ground, accepting, *args):
        if runner.run is None:
            runner.run = Run("test", "start", {"a": 1, "b": 2})
        return runner.eval_link(X(runner, runner.run, SimpleNamespace(f=f, F=f+2, state=s, allow=s.get("allow", True))))
    def close(self, x, kind, why):
        x.run.closed = kind
        x.R.done.append(x.run)
        x.R.run = None
        x.run = None
    def reopen_wanted(self, why):
        return False


def runner(chains=None):
    p = Prims()
    register_core(p)
    p.guard("allow")(lambda x: x.obs.allow)
    p.action("mutate")(lambda x: x.obs.state["history"].append(9))
    return ChainRunner(chains or table(), Anchor(), p, observation_names={"f", "F", "state", "allow"})


@pytest.mark.parametrize("expression,expected", [
    ({"fn": "if", "c": True, "then": 3, "else": {"fn": "div", "a": 1, "b": 0}}, 3),
    ({"fn": "and", "of": [False, {"fn": "div", "a": 1, "b": 0}]}, False),
    ({"fn": "or", "of": [True, {"fn": "div", "a": 1, "b": 0}]}, True),
])
def test_lazy_branches_do_not_evaluate_unreachable_operand(expression, expected):
    r = runner()
    x = X(r, Run("test", "start", {}), SimpleNamespace(f=1))
    assert r.ev(x, expression) == expected


@pytest.mark.parametrize("mode,mask,link", [("same", 2, "end"), ("keys", 2, "end"),
                                            ("next", 1<<21, "end"), ("emit", 1, "end")])
def test_goto_key_timing_preserves_prototype_modes(mode, mask, link):
    rule = {"do": "goto", "to": "end", "mode": mode}
    if mode == "emit":rule["emit"] = "J"
    r = runner(table([rule]))
    assert r.step(10, {}, True) == mask and r.run.link == link
    assert r.run.sent == [(12, mask)]  # logical proposal only, not a transport receipt


def test_try_failure_and_hold_are_distinct_from_switch():
    r = runner(table([{"do": "try", "to": "end", "orelse": "hold"}]))
    assert r.step(10, {"allow": False}, True) is None and r.run.link == "start"
    assert r.step(11, {"allow": True}, True) == 2 and r.run.link == "end"


def test_set_reads_old_values_in_parallel_and_scratch_does_not_enter_run():
    r = runner(table([{"do": "set", "set": {"a": "var.b", "b": "var.a", "tmp.n": 7}}]))
    r.step(10, {}, True)
    assert r.run.v == {"a": 2, "b": 1}
    x = X(r, r.run, SimpleNamespace(f=11))
    assert r.ev(x, "var.tmp.n") is None


def test_preview_does_not_commit_run_or_mutate_supplied_state():
    r = runner(table([{"do": "act", "act": {"a": "mutate"}}, {"do": "goto", "to": "end"}]))
    state = {"history": []}
    preview = r.preview(10, state, True)
    assert preview.frame == 10 and preview.mask == 2
    assert r.run is None and r.done == [] and r.fired == {}
    assert state == {"history": []}
    assert preview.draft.run.link == "end"


def test_existing_active_run_is_also_isolated_from_draft():
    r = runner(table([{"do": "set", "set": {"a": {"add": ["var.a", 1]}}}]))
    r.step(10, {}, True)
    before = deepcopy(r.run.v)
    preview = r.preview(11, {}, True)
    assert r.run.v == before
    assert preview.draft.run.v["a"] == before["a"] + 1
    assert len(r.run.sent) == 1 and len(preview.draft.run.sent) == 2


def test_invalid_name_rejected_before_anchor_reset():
    a, p = Anchor(), Prims()
    with pytest.raises(ChainFormatError, match="unregistered guards"):
        ChainRunner(table(), a, p, observation_names={"allow"})
    assert a.reset_count == 0


def test_unsupported_path_is_explicit_not_successful_empty_output():
    r = runner(table([{"do": "abort", "why": "not encoded: example"}]))
    assert r.step(10, {}, True) is None
    assert r.unsupported == [[10, "test.start", "not encoded: example"]]


def test_entry_probe_recovers_values_but_does_not_emit_keys():
    c = table()
    c["test"].links["start"].rules = c["test"].links["start"].rules or []
    from ssbot.combat.knife_chain_format import Rule
    c["test"].links["start"].rules = [Rule("set", set={"a": 9}), Rule("goto", to="end", when={"p": "allow"})]
    r = runner(c)
    run = Run("test", "start", {"a": None, "b": 2})
    assert r.probe_entry(X(r, run, SimpleNamespace(allow=True)), r.chains["test"].links["start"]) == "end"
    assert run.v["a"] == 9 and run.sent == []
