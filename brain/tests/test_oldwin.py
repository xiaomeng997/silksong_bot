"""Task oldwin: the strike-window table's rows in the old planner (ssbot.map2.oldwin, SSBOT_FORUM_WINDOWS)."""
import os
import re
from pathlib import Path

import numpy as np
import pytest

from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import oldwin as ow
from ssbot.map2 import reflex as rx
from ssbot.map2 import strike as sk


def test_switch_default_off(monkeypatch):
    monkeypatch.delenv(ow.ENV, raising=False)
    assert not ow.enabled()
    monkeypatch.setenv(ow.ENV, "1")
    assert ow.enabled()


def test_planner_does_not_import_map2():
    """The old planner reaches the table only through the object the policy hands it (planner.win): forum_planner.py
    imports no ssbot.map2 (off: nothing of it is loaded)."""
    src = (Path(ow.__file__).resolve().parents[1] / "combat" / "forum_planner.py").read_text("utf-8")
    assert not re.search(r"^\s*(from|import)\s+ssbot\.map2|ssbot\.map2\s+import", src, re.M)


def test_pack_np_is_pack_key():
    rng = np.random.default_rng(3)
    for _ in range(300):
        wt = rng.choice(sorted(rx.WINDOWS))
        st = rng.choice(sorted(rx._ST_IDS))
        cls = rng.choice(["G", "A", "F"])
        k = rx.CellKey(wt, st, int(rng.integers(0, 200)), int(rng.integers(0, 9)), int(rng.integers(-60, 60)), cls,
                       int(rng.integers(-1, 30)), int(rng.integers(-12, 8)), int(rng.integers(-1, 2)),
                       int(rng.integers(0, 2)), int(rng.integers(-6, 6)), int(rng.integers(0, 2)))
        v = ow._pack_np(rx._WT_IDS[k.wt], rx._ST_IDS[k.st], k.j, k.band, k.dxq, rx._CLS_IDS[k.cls], k.bbq, k.sub,
                        k.vxc, k.adash, k.cvx, k.chg)
        assert int(v) == rx.pack_key(k)


def _ent(st, j, x, face, hp=230, iid=7):
    return {"iid": iid, "type_key": cm.CLAPPER, "pos": [x, 7.449], "vel": [0.0, 0.0], "flipX": face > 0, "hp": hp,
            "fsms": [{"name": "Control", "state": st, "t": j / 60.0}], "anim": {"clip": None}}


@pytest.mark.skipif(not rx.TABLE_PATH.exists(), reason="the window table (knowledge, gitignored) is not here")
def test_now_row_from_a_table_cell(monkeypatch):
    """A hop_slam0 ground cell of the table: her state put inside it, the Clapper in the cell's move / frame / band /
    facing -> WindowRows.rows gives the cell's macro as a NOW row with the table's contact; the cell keyed exactly."""
    from ssbot.map2 import search as ms
    params = ms.World().params
    monkeypatch.setattr(ow, "DS_TYPES", ow.ALL_DS)      # (hop_slam0 is off by default: this cell type is the probe)
    monkeypatch.setattr(ow, "MARGIN", False)
    wr = ow.WindowRows()
    keys = wr.keys
    pick = None
    for pk in keys[::997]:
        k = rx.unpack_key(int(pk))
        if k.wt == "hop_slam0" and k.cls == "G" and 4 <= k.j <= 30 and k.band == 4 and k.cvx == 0:
            e = wr.table._entry(int(pk))
            if e.conf[0] == e.conf[1]:
                pick = (k, e)
                break
    assert pick is not None
    k, e = pick
    face = 1
    cx = rx._clapper_x(k.band, face, 0)
    hx = cx + face * (k.dxq + 0.5) * rx.DX_Q
    S = km.initial_state(params, hx, sk.FLOOR + sk.FOOT, ground=True, facing=face)
    trk_k = 1000
    for i in range(k.j + 1):
        wr.feed({"hero": {"box": [hx - 0.23, 3.015, hx + 0.23, 5.09]}, "ents": [_ent("Slam Antic", i, cx, face)],
                 "ev": []}, trk_k + i)
    o = wr.obs()[0]
    assert o.st == "Slam Antic" and o.j == k.j
    assert rx.cell_of(S, o, rx.WINDOWS["hop_slam0"]) == k
    cands, info = wr.rows(S, np.zeros(0, np.int64), km.HoldState.idle(1), 36, params, None, hold_filter_jit,
                          trk_k + k.j - 1, trk_k + k.j, 1, "ground")
    now = [c for c in cands if c.kind == "now" and c.wt == "hop_slam0"]
    assert now, (info, [(c.kind, c.wt) for c in cands])
    c = now[0]
    d = 1 if cx >= hx else -1
    assert np.array_equal(c.cmd, rx.render(e.macro, d).pre)
    assert c.k0 == e.k_strike[0] and c.j == 0 and c.key == k.short()


def test_dx_neighbour_is_one_bin():
    """MARGIN's neighbour keys: dx +- one bin is the packed key +- _DX1."""
    from dataclasses import replace
    k = rx.CellKey("pogo_cast", "Cast 2", 14, 4, 7, "A", 5, -2, 0, 1, 0, 0)
    assert rx.pack_key(replace(k, dxq=8)) == rx.pack_key(k) + ow._DX1
    assert rx.pack_key(replace(k, dxq=6)) == rx.pack_key(k) - ow._DX1


def test_default_types_leave_out_hop_slam0(monkeypatch):
    """The default row types: every generated down-slash type but hop_slam0 (the audit's refuted rows)."""
    assert "hop_slam0" not in ow.DS_TYPES and "pogo_cast" in ow.DS_TYPES and "drop_slam0" in ow.DS_TYPES
    assert set(ow.ALL_DS) - set(ow.DS_TYPES) == {"hop_slam0"}
