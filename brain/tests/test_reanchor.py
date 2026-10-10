"""SSBOT_FORUM_REANCHOR (task precision push S2): the parts fam (no family union where the walk's nodes all have
per-state templates) and chain (a defender's counter only from the first frame a hit can reach it), on the synthetic
Reed of tests/test_multi_forecast.py (a defence extended by a Block and a Parry Slash for chain)."""
import copy

import numpy as np

from ssbot.combat import enemy_tables as et
from ssbot.combat import multi_forecast as mfm
from ssbot.combat.enemy_tables import EnemyTables, Tubes, type_table
from ssbot.combat.multi_forecast import MultiForecaster
from ssbot.core.forum import FORUM_TYPES
from ssbot.core.worldstate import ORACLE

from tests.test_multi_forecast import BIN, BODY, REED, _ent, _go, _reed_table, _run, _script_stab, _templates, _tpl


def _key(store, tid: int) -> str:
    from ssbot.tools.forum_layer_audit import _key_name
    return _key_name(store, tid)


def _grid(tk):
    xs = np.arange(10.0, 32.0, 0.25)
    ys = np.arange(2.0, 9.0, 0.25)
    X, Y = np.meshgrid(xs, ys)
    X, Y = X.reshape(-1), Y.reshape(-1)
    return np.repeat(X[:, None], len(tk), 1), np.repeat(Y[:, None], len(tk), 1)


def _forecaster(tables, ra):
    b = MultiForecaster(tables, ORACLE, waves=False)
    b.reanchor = frozenset(ra)
    return b


def test_fam_drops_the_family_union_and_keeps_the_per_state_nodes():
    from tests.test_multi_forecast import _tables
    tk = np.arange(0, 49) * BIN
    X, Y = _grid(tk)
    occ, names = {}, {}
    for ra in ((), ("fam",)):
        b = _forecaster(_tables(), ra)
        _run(b, _script_stab()[:17])                  # f 16: Stab 1 entered
        f = b.forecast(0.8)
        names[ra] = {_key(b.tables.store, int(t)) for t in np.asarray(f.P.tid).tolist() + np.asarray(f.W.tid).tolist()}
        occ[ra] = f.occupied(X, Y, tk)
    assert any(n.endswith("RE_STAB/anchor") and "/Stab" not in n for n in names[()])
    assert not any(n.endswith("RE_STAB/anchor") and "/Stab" not in n and "_tail" not in n for n in names[("fam",)])
    assert any("Stab 1" in n for n in names[("fam",)])
    assert not (occ[("fam",)] & ~occ[()]).any()       # a subset
    assert (occ[()] & ~occ[("fam",)]).any()           # and the union held more
    # the blade (1 .. 3 u forward of the Reed facing -x at about x 20.3) is still there while Stab 1 lasts
    blade = (X < 19.0) & (X > 17.5) & (np.abs(Y - 5.0) < 0.5)
    assert (occ[("fam",)] & blade)[:, :6].any()


def _defend_tables():
    """The synthetic Reed whose defence has a counter: Defend -> Block (0.48-0.5 s) -> Parry Slash (0.3-0.6 s, a blade
    2 .. 6 u forward) -> Alert; the family union holds the counter too."""
    d = copy.deepcopy(_reed_table())
    d["attacks"]["RE_DEFEND"]["states"] += ["Block", "Parry Slash"]
    d["dwell_s"]["Block"] = {"min": 0.48, "max": 0.5}
    d["dwell_s"]["Parry Slash"] = {"min": 0.3, "max": 0.6}
    d["dwell_s"]["Defend"] = {"min": 0.03, "max": 1.0}     # a hit can end the stance at once
    succ = d["support_transitions"]
    succ["Defend"] = ["Alert", "Block"]
    succ["Block"] = ["Parry Slash"]
    succ["Parry Slash"] = ["Alert"]
    d["graph"]["edges"] = [{"from": a, "to": b, "p": 1.0 / len(v)} for a, v in succ.items() for b in v]
    T = _templates()
    T["support/RE_DEFEND/Block/anchor"] = _tpl("support/RE_DEFEND/Block/anchor", [(0.0, 0.55, *BODY)])
    T["support/RE_DEFEND/Parry Slash/anchor"] = _tpl("support/RE_DEFEND/Parry Slash/anchor",
                                                     [(0.0, 0.65, *BODY), (0.0, 0.65, 2.0, -0.5, 6.0, 0.5)])
    T["support/RE_DEFEND/_tail/anchor"] = _tpl("support/RE_DEFEND/_tail/anchor", [(0.0, 0.05, *BODY)])
    T["support/RE_DEFEND/anchor"] = _tpl("support/RE_DEFEND/anchor", [(0.0, 2.5, *BODY),
                                                                     (0.6, 2.5, 2.0, -0.5, 6.0, 0.5)])
    tt = type_table(d, FORUM_TYPES[REED])
    store = EnemyTables._store([T])
    tubes = Tubes({REED: [0.0] + [0.05 * k for k in range(1, 41)]}, {REED: 50.0}, {REED: BODY})
    return EnemyTables({REED: tt}, store, tubes, {}, True, "synthetic", {"Song Reed/ParrySlash Hit": (2, 2)})


def _script_defend(n=40):
    """A Reed at x 20 facing +x: Alert, Defend Start at f 0.1 s, Defend from 0.2 s on (not hit)."""
    out = []
    for f in range(n):
        t = f * BIN
        st = "Alert" if f < 6 else "Defend Start" if f < 12 else "Defend"
        evs = []
        if f == 0:
            evs.append(_go(7, "Alert", f, t))
        if f == 6:
            evs.append(_go(7, "Defend Start", f, t))
        if f == 12:
            evs.append(_go(7, "Defend", f, t))
        out.append((f, t, [_ent(7, 20.0, 5.0, st, 0.0, flip=False, box=(19.5, 4.0, 20.5, 6.0), hp=999)], evs))
    return out


def test_chain_places_the_counter_only_after_a_hit_can_land(monkeypatch):
    tk = np.arange(0, 49) * BIN
    X, Y = _grid(tk)
    # the Parry Slash blade ahead of the Reed, from frame 6 on (the current-collider tube grows 50 u/s for 5 frames)
    # (either side: the template frame's +x is the Reed's facing), the current attack's (committed) part only
    blade = (np.abs(np.abs(X - 20.0) - 4.0) < 1.5) & (np.abs(Y - 5.0) < 0.5) & (np.arange(len(tk)) >= 6)
    script = _script_defend()
    got = {}
    for ra, k in (((), 0), (("chain",), 0), (("chain",), 20), (("chain",), 60)):
        monkeypatch.setattr(mfm._Builder, "_hero_hit_k", lambda self, tr, k=k: k)
        b = _forecaster(_defend_tables(), ra)
        _run(b, script[:16])                          # f 15: in Defend 0.05 s
        f = b.forecast(0.8)
        got[(ra, k)] = f.committed().occupied(X, Y, tk)
    off = got[((), 0)]
    first = lambda o: int(np.flatnonzero((o & blade).any(0))[0]) if (o & blade).any() else None  # noqa: E731
    # off: the walk's counter right after the Block's 0.48 s from now (the stance may end at once)
    assert first(off) is not None and first(off) <= int(round(0.48 / BIN)) + 1
    # chain, a hit can land now: the counter no earlier than the Block's 0.48 s (less a bin of slack)
    assert first(got[(("chain",), 0)]) >= int(round(0.48 / BIN)) - 2
    # a hit 20 frames away: the blade 20 frames later still
    assert first(got[(("chain",), 20)]) >= 20 + int(round(0.48 / BIN)) - 2
    # no hit can land within the horizon: no counter at all
    assert first(got[(("chain",), 60)]) is None
    for key in ((("chain",), 0), (("chain",), 20), (("chain",), 60)):
        assert not (got[key] & ~off).any()            # never more than off
    # the stance body stays
    body = (np.abs(X - 20.0) < 0.6) & (np.abs(Y - 5.0) < 1.0)
    assert got[(("chain",), 60)][body[:, 0]][:, :10].all()


def test_reanchor_parts_parse():
    import pytest
    for v, want in (("", frozenset()), ("0", frozenset()), (None, frozenset()), ("1", frozenset(mfm.REANCHOR_PARTS)),
                    ("fam", frozenset({"fam"})), ("chain, fam", frozenset({"fam", "chain"}))):
        assert mfm.reanchor_parts(v) == want
    with pytest.raises(ValueError):
        mfm.reanchor_parts("fam,kin")
    assert mfm.REANCHOR == frozenset() and et.BIN == BIN
