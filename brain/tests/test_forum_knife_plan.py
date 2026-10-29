"""A post-bounce exit must not become an H abort or stale CONTINUE proof."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat import forum_knife_plan as plan
from ssbot.combat import forum_knife_hit as hit
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.knowledge import kinematics as k


@pytest.fixture
def case():
    prefix = np.array([k.B_RIGHT], np.int64)
    raw = np.zeros(85, np.int64); raw[:1] = prefix
    raw[43:45] = k.B_DOWN | k.B_ATTACK
    raw[52:] = k.B_LEFT
    hold = k.HoldState.idle()
    wire = hold_filter_jit(raw[None], hold)[0][0]
    ro = SimpleNamespace(hooks=[object()], commands=wire.copy(), bound=np.zeros((1, 86, 4)))
    cert = hit.HitExit(52, 85, 2, raw, wire, [ro], [np.array([48])], ["world"], 37, ("world",))
    state = k.initial_state(k.HeroParams(), 3., 8., ground=False)
    args = dict(frame=1000, start=state, hold=hold, prefix=prefix, T=36)
    tail = plan.CheckedTail.from_exit(cert, world_keys=["world"], **args)
    row = dict(**args, cmd=raw[1:37].copy(), latched=wire[:37].copy())
    return tail, cert, row


def test_retaining_the_plan_keeps_the_strike_after_H_and_checked_exit(case):
    tail, cert, row = case
    future = tail.for_row(**row)
    result = SimpleNamespace(idx=8, S=0, cmd=row["cmd"], mask=int(row["cmd"][0]))
    kept = plan.selected_tail(result, {8: future}, T=36)
    assert len(kept) == 84
    assert np.array_equal(kept, cert.raw[1:])
    assert np.flatnonzero(kept & k.B_ATTACK).tolist() == [42, 43]
    assert (kept[51:] == k.B_LEFT).all()
    # A legacy H + 24 escape would have discarded both attack presses.
    assert not (kept[:36] & k.B_ATTACK).any()


@pytest.mark.parametrize("change", ["tick", "prefix", "pending", "age", "state", "T", "raw", "wire"])
def test_a_changed_tick_or_queue_cannot_inherit_the_certificate(case, change):
    tail, cert, row = case
    row = dict(row)
    if change == "tick": row["frame"] += 1
    if change == "prefix": row["prefix"] = np.array([0], np.int64)
    if change in ("pending", "age"):
        hold = k.HoldState(*(getattr(row["hold"], n).copy() for n in ("latched", "desired", "pending", "age")))
        getattr(hold, change)[0, 0] += 1; row["hold"] = hold
    if change == "state":
        row["start"] = row["start"].copy(); row["start"][k.PX] += .01
    if change == "T": row["T"] += 1
    if change in ("raw", "wire"):
        field = "cmd" if change == "raw" else "latched"
        row[field] = row[field].copy(); row[field][-1] ^= k.B_ATTACK
    with pytest.raises(ValueError):
        tail.for_row(**row)


def test_mutating_the_source_certificate_does_not_mutate_the_saved_tail(case):
    tail, cert, row = case
    cert.raw[43] = 0; cert.latched[43] = 0
    assert tail.raw[43] & k.B_ATTACK and tail.latched[43] & k.B_ATTACK
    with pytest.raises(ValueError): tail.raw[43] = 0


@pytest.mark.parametrize("change", ["H", "coverage", "wire", "partial", "contact"])
def test_incomplete_or_mismatched_exit_cannot_become_a_tail(case, change):
    tail, cert, row = case
    args = {n: row[n] for n in ("frame", "start", "hold", "prefix", "T")}
    if change == "H": cert.horizon = 36
    if change == "coverage": cert.world_keys = []
    if change == "wire": cert.latched = cert.latched.copy(); cert.latched[-1] ^= k.B_RIGHT
    if change == "partial": cert.raw = cert.raw[:60]; cert.latched = cert.latched[:60]
    if change == "contact": cert.contacts = [np.array([37])]
    with pytest.raises(ValueError):
        plan.CheckedTail.from_exit(cert, world_keys=["world"], **args)


def test_an_unsafe_or_different_selection_does_not_retain_the_checked_tail(case):
    tail, _, row = case
    saved = {8: tail.for_row(**row)}
    result = SimpleNamespace(idx=7, S=0, cmd=row["cmd"], mask=int(row["cmd"][0]))
    assert plan.selected_tail(result, saved, T=36) is None
    result.idx = 8; result.S = 1
    assert plan.selected_tail(result, saved, T=36) is None
    result.S = 0; result.mask ^= k.B_ATTACK
    with pytest.raises(ValueError): plan.selected_tail(result, saved, T=36)


def test_ranked_ordinary_safe_tail_wins_before_a_checked_knife_tail():
    calls = []
    def ordinary(*args):
        row = int(args[3][0]); calls.append(row); return row, row == 2
    planner = SimpleNamespace(cfg=SimpleNamespace(tail_k=3), _tail_pick=ordinary)
    args = (planner, None, None, None)
    assert plan.pick_tail(*args, np.array([1, 2, 3]), 37, 1, {3: object()}) == (2, True)
    assert calls == [1, 2]


def test_checked_tail_is_not_replayed_from_H_without_its_hook_or_pogo():
    calls = []
    def ordinary(*args):
        row = int(args[3][0]); calls.append(row); return row, False
    planner = SimpleNamespace(cfg=SimpleNamespace(tail_k=2), _tail_pick=ordinary)
    assert plan.pick_tail(planner, None, None, None, np.array([1, 3]), 37, 1, {3: object()}) == (3, True)
    assert calls == [1]
    # The original check count still applies; the third row is not inspected.
    assert plan.pick_tail(planner, None, None, None, np.array([1, 2, 3]), 37, 1, {3: object()}) == (1, False)


def test_feature_absent_preserves_the_ordinary_batch_and_return_value():
    calls = []
    def ordinary(*args): calls.append(args); return 4, None
    planner = SimpleNamespace(_tail_pick=ordinary)
    ranked = np.array([4, 7])
    assert plan.pick_tail(planner, "f", "r", "h", ranked, 37, 4, {}) == (4, None)
    assert len(calls) == 1 and calls[0][3] is ranked



@pytest.mark.parametrize("hits_first", [False, True])
@pytest.mark.parametrize("stale", [False, True])
def test_native_tick_preserves_the_checked_tail_without_an_H_abort(monkeypatch, hits_first, stale):
    """Controlled contact oracle: exercise native ranking/escape/storage, not real hit physics."""
    import math
    from ssbot.combat import forum_planner as fp, forum_v2 as v2, forum_knife as fk, special_mode, dslash
    from ssbot.combat.planner import PlannerConfig
    from ssbot.combat.tactics.modes import GoalPrefs
    from tests.test_forum_planner import _ctx, _world, _reed_forecaster
    from tests.test_forum_v2 import _support_with
    from ssbot.map2.envelope import load_params
    params = load_params(hero2=True)
    arena = k.Terrain2D.from_boxes([(10., 0., 53., 3.)])
    start = k.initial_state(params, 27., 3. + params.foot)
    hold = k.HoldState.idle(); prefix = np.array([k.B_RIGHT], np.int64)
    raw = np.zeros(85, np.int64); raw[:1] = prefix
    raw[43:45] = k.B_DOWN | k.B_ATTACK; raw[52:] = k.B_LEFT
    wire = hold_filter_jit(raw[None], hold)[0][0]
    ro = SimpleNamespace(hooks=[object()], commands=wire, bound=np.zeros((1, 86, 4)))
    cert = hit.HitExit(52, 85, 2, raw, wire, [ro], [np.array([48])], ["world"], 37, ("world",))
    ws = _world(27.); ws.stamp.frame = 1000
    tail = plan.CheckedTail.from_exit(cert, frame=1000, start=start, hold=hold, prefix=prefix, T=36,
                                      world_keys=["world"])
    if stale:
        tail = replace(tail, frame=999)
    main = k.rollout(start, wire[:37][None], params, arena, variants="bounds")
    custom = {"checked_tail": tail, "latched": wire[:37],
              "nominal": {n: getattr(main, n)[0] for n in ("phys", "pos", "vel", "mode", "flags", "box")},
              "final": main.final[:, 0], "bound": main.bound[0], "flags_all": main.flags_all[0],
              "escape": 2, "checks": []}
    rows = fp.DsRows(raw[1:37][None], ["WIN knife synthetic"], [raw[1:]],
        np.zeros((1, 37), np.int64), np.zeros(1, bool), np.array([48]), np.array([-1]),
        np.array([7]), np.ones(1, np.int64), None, custom={0: custom})
    planner = fp.ForumPlanner(params, arena, PlannerConfig(T=36, threads=1, variants="bounds"),
        fp.ForumConfig(v2=True, deadline_ms=math.inf, esc_deadline_ms=math.inf), crest="Wanderer")
    planner.win = SimpleNamespace(knife=True, harpoon=False, note_chosen=lambda *a: None)
    monkeypatch.setattr(planner, "_win_rows", lambda *a: rows)
    monkeypatch.setattr(fk, "append_rows", lambda *a: a[-1])
    monkeypatch.setattr(special_mode, "HITS_FIRST", hits_first)
    monkeypatch.setattr(dslash, "DSLASH", False)
    monkeypatch.setattr(v2, "ESC_TAIL", True)
    def forbidden_abort(*args):
        raise AssertionError("a checked post-bounce tail must not be replaced/replayed from H")
    if not stale:
        monkeypatch.setattr(planner, "_esc_cmds", forbidden_abort)
    forecast = v2.V2Forecast(_reed_forecaster(None, x=45.).forecast(.8), _support_with([]))
    result = planner.tick(ws, start, hold, prefix, forecast,
                          GoalPrefs("ENGAGE", 27., {"hit": 1000.}, hit_w={7: 1.}), _ctx())
    if stale:
        assert result.name != "WIN knife synthetic"
        assert planner.last_info["knife"]["full_checked_tail_frames"] == 0
        assert custom["checks"][0]["check"] == "checked_tail_identity"
        assert custom["checks"][0]["status"] == "failed"
    else:
        assert result.name == "WIN knife synthetic" and result.S == 0
        assert np.array_equal(planner.prev_cmd, raw[1:])
        assert planner.last_info["knife"]["full_checked_tail_frames"] == 84
        assert not custom["checks"]


def test_forced_selection_and_shortened_result_do_not_keep_a_tail(case):
    tail, _, row = case
    saved = {8: tail.for_row(**row)}
    result = SimpleNamespace(idx=8, S=0, forced_risk=True, cmd=row["cmd"], mask=int(row["cmd"][0]))
    assert plan.selected_tail(result, saved, T=36) is None
    result.forced_risk = False; result.cmd = result.cmd[:1]
    with pytest.raises(ValueError):
        plan.selected_tail(result, saved, T=36)


def test_zero_lane_certificate_cannot_carry_a_checked_tail(case):
    tail, cert, row = case
    cert.paths[0].hooks = []
    cert.paths[0].bound = np.zeros((0, 86, 4))
    cert.contacts = [np.array([], np.int64)]
    args = {n: row[n] for n in ("frame", "start", "hold", "prefix", "T")}
    with pytest.raises(ValueError):
        plan.CheckedTail.from_exit(cert, world_keys=["world"], **args)


def test_tail_cannot_drop_a_declared_world_from_the_exit_certificate(case):
    tail, cert, row = case
    cert.expected_world_keys = ("world", "missing_world")
    args = {n: row[n] for n in ("frame", "start", "hold", "prefix", "T")}
    with pytest.raises(ValueError, match="expected world domain"):
        plan.CheckedTail.from_exit(cert, world_keys=["world"], **args)
