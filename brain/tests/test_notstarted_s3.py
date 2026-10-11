"""Task precision push S3, the not-started layer: SSBOT_FORUM_WALKFLOOR (no node after the walk's root before the root
state's earliest exit), SSBOT_FORUM_NSBOX bin (a later instance from its earliest start on, not a bin before it) and
SSBOT_FORUM_GATES (FSM history gates), on the synthetic Reed of tests/test_multi_forecast.py."""
import math

import numpy as np
import pytest

from ssbot.combat import multi_forecast as mfm
from ssbot.combat.enemy_tables import type_table
from ssbot.combat.multi_forecast import DWELL_SLACK_S, MultiForecaster, nsbox_parts, walk
from ssbot.core.forum import FORUM_TYPES
from ssbot.core.worldstate import ORACLE

from tests.test_multi_forecast import BIN, REED, _ent, _go, _reed_table, _run, _tables


def _loop_table():
    d = _reed_table()
    d["dwell_s"]["Alert"] = {"min": 0.0, "max": 0.5}
    d["support_transitions"]["Alert"] = ["Alert", "Stab Pos", "Defend Start", "Death"]
    return type_table(d, FORUM_TYPES[REED])


def test_walk_floor_holds_every_later_node_at_the_roots_earliest_exit():
    tt = _loop_table()
    for st in ("Stab 1", "Defend", "Alert"):
        dw = tt.dwell[st]
        off = walk(tt, st, None, False, False, floor=False)
        on = walk(tt, st, None, False, False, floor=True)
        lo_min = max(dw[0] - DWELL_SLACK_S, -DWELL_SLACK_S)
        assert min(n.lo for n in on if not n.current) >= lo_min - 1e-9
        # the same nodes, each entered no earlier than before, the latest entries unchanged
        k_off = {(n.state, n.family, n.start, n.kind, n.dead, n.current): n for n in off}
        k_on = {(n.state, n.family, n.start, n.kind, n.dead, n.current): n for n in on}
        assert set(k_off) == set(k_on)
        for k, n in k_on.items():
            assert n.lo >= k_off[k].lo - 1e-9 and abs(n.hi - k_off[k].hi) < 1e-9
    # Defend (0.5 s least dwell): the roots after it moved from about -1 bin to 0.5 s - a bin
    on = walk(tt, "Defend", None, False, False, floor=True)
    assert min(n.lo for n in on if not n.current) == pytest.approx(0.5 - DWELL_SLACK_S)
    # overdue: walked from the origin, nothing before the next frame
    on = walk(tt, "Defend", None, False, True, floor=True)
    assert min(n.lo for n in on if not n.current) >= BIN - 1e-9


def test_walk_cache_keys_the_floor():
    tt = _loop_table()
    a, b = mfm._WalkCache(floor=False), mfm._WalkCache(floor=True)
    ra, rb = a.get(tt, "Defend", None, False, False), b.get(tt, "Defend", None, False, False)
    assert min(n.lo for n in rb[1]) > min(n.lo for n in ra[1])


def test_nsbox_parts_parse():
    assert nsbox_parts(None) == frozenset() and nsbox_parts("0") == frozenset()
    assert nsbox_parts("1") == frozenset(mfm.NSBOX_PARTS) and nsbox_parts("bin") == {"bin"}
    assert nsbox_parts("bin0") == {"bin0"}
    with pytest.raises(ValueError):
        nsbox_parts("bin,nope")


def _idle_script():
    return [(0, 0.0, [_ent(7, 20.0, 5.0, "Alert", box=(19.5, 4.0, 20.5, 6.0))], [_go(7, "Alert", 0, 0.0)]),
            (1, BIN, [_ent(7, 20.0, 5.0, "Alert", box=(19.5, 4.0, 20.5, 6.0))], [])]


def test_nsbox_bin_places_nothing_before_the_earliest_start():
    tk = np.arange(0, 49) * BIN
    xs = np.arange(10.0, 32.0, 0.25)
    ys = np.arange(1.0, 10.0, 0.25)
    X, Y = np.meshgrid(xs, ys)
    X = np.repeat(X.reshape(-1)[:, None], len(tk), 1)
    Y = np.repeat(Y.reshape(-1)[:, None], len(tk), 1)
    occ = {}
    for parts in ((), ("bin",), ("bin0",)):
        mf = MultiForecaster(_tables(), ORACLE, waves=False, collider_tube=False)
        mf.nsbox = frozenset(parts)
        _run(mf, _idle_script())
        f = mf.forecast(0.8)
        occ[parts] = f.occupied_parts(X, Y, tk)["forecast"]
    assert not (occ[("bin",)] & ~occ[()]).any()          # a subset
    # Alert (least dwell 0.2 s, entered at 0, the origin one frame later): the roots start from 0.2 s - a bin - the
    # frame elapsed on; nothing of them before that with bin, one bin earlier without
    first_on = int(np.flatnonzero(occ[("bin",)].any(axis=0))[0])
    first_off = int(np.flatnonzero(occ[()].any(axis=0))[0])
    assert first_on == first_off + 1
    # bin0: only the origin (k0) loses the pre-start bin
    assert not (occ[("bin0",)] & ~occ[()]).any() and not occ[("bin0",)][:, 0].any()
    assert (occ[("bin0",)][:, 1:] == occ[()][:, 1:]).all()


def test_gate_floors_a_gated_root_at_its_lift_states_walk_entry(monkeypatch):
    # a made-up gate on the synthetic Reed: no stab after a stab before a Defend Start
    monkeypatch.setattr(mfm, "_FSM_GATES", {(REED, "RE_STAB"): ("Defend Start", 10.0)})
    script = [(0, 0.0, [_ent(7, 20.0, 5.0, "Stab Pos", box=(19.5, 4.0, 20.5, 6.0))], [_go(7, "Stab Pos", 0, 0.0)])]
    script += [(f, f * BIN, [_ent(7, 20.0, 5.0, "Stab Pos", box=(19.5, 4.0, 20.5, 6.0))], []) for f in (1, 2)]
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    mf.gates = True
    _run(mf, script)
    tr = mf.trackers[7]
    assert tr.last_start.get("RE_STAB") == 0.0 and "Stab Pos" in tr.last_entry
    ctx = (tr.cur.family, tr.cur.start)
    b = mfm._Builder(mf, 2 * BIN, 0.8)
    fl = b._gate_floor(tr, ctx, False, tr.t_entry)
    st = mf.walks.states(tr.table, tr.state, ctx, False, False)
    roots = mf.walks.get(tr.table, tr.state, ctx, False, False)[1]
    stab_lo = min(tr.t_entry + n.lo - 2 * BIN for n in roots if n.family == "RE_STAB")
    assert fl["RE_STAB"] == pytest.approx(tr.t_entry + st["Defend Start"] - 2 * BIN + BIN)
    assert fl["RE_STAB"] > stab_lo                         # later than the walk alone allows
    # the vision view has no gates
    mf.view, keep = "vision_equivalent", mf.view
    assert b._gate_floor(tr, ctx, False, tr.t_entry) == {}
    mf.view = keep
    # lifted once the lift state is entered after the start
    for k, s_ in enumerate(("Stab 1", "Stab Recover", "Alert", "Defend Start")):
        tr.enter(s_, (3 + k) * BIN)
    assert tr.last_entry["Defend Start"] > tr.last_start["RE_STAB"]
    b.origin = 7 * BIN
    assert b._gate_floor(tr, (tr.cur.family, tr.cur.start), False, tr.t_entry) == {}


def test_unknown_transition_lifts_the_gate():
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    _run(mf, [(0, 0.0, [_ent(7, 20.0, 5.0, "Stab Pos")], [_go(7, "Stab Pos", 0, 0.0)])])
    tr = mf.trackers[7]
    assert tr.t_odd == -math.inf
    tr.enter("Defend", BIN)                               # Stab Pos -> Defend: not in the table
    assert tr.t_odd == BIN


def test_mined_gates_parse():
    g = mfm.fsm_gates()
    if g:
        assert ("Pilgrim 03 Song", "CB_EVADE") in g
        lift, tmo = g[("Pilgrim 03 Song", "CB_EVADE")]
        assert isinstance(lift, str) and tmo > 0.0
