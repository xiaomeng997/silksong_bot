"""Task 178 round 5: the tick-cost changes return exactly what the code before them returned.

coarse() is the strided OR of the padded any-pooling; B2's owner stacks and the hazard stacks are filled only on the
samples a query reads, with the whole stacks' cells there; press_now_row rolls its fixed rows as one batch, and every
batched row is that row rolled alone.
"""
import math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K
from ssbot.combat import forum_v2 as v2, knife_chain_transfer as T, pogo_model as PM
from ssbot.combat.attack_range import Mask
from ssbot.combat.knife_chain_air import body_box
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_geometry import B2Geometry
from tests.test_knife_chain_b2 import params, terrain
from tests.test_transfer_pose_witness178 import ROWS, live_sim, target


def coarse_before(m, from_cell, cell=v2.CELL):
    """forum_v2.coarse as it was (057c702a): any() over the zero-padded r x r blocks."""
    r = int(round(cell / from_cell))
    if r <= 1:
        return m.m, m.ix0, m.iy0
    ix0 = m.ix0 // r
    iy0 = m.iy0 // r
    px, py = m.ix0 - ix0 * r, m.iy0 - iy0 * r
    ny = -(-(m.m.shape[0] + py) // r)
    nx = -(-(m.m.shape[1] + px) // r)
    big = np.zeros((ny * r, nx * r), bool)
    big[py:py + m.m.shape[0], px:px + m.m.shape[1]] = m.m
    return big.reshape(ny, r, nx, r).any(axis=(1, 3)), ix0, iy0


def test_coarse_equals_the_padded_any_pooling():
    rng = np.random.default_rng(178)
    for _ in range(3000):
        h, w = (int(v) for v in rng.integers(0, 30, 2))
        m = Mask(rng.random((h, w)) < rng.random(), int(rng.integers(-40, 40)), int(rng.integers(-40, 40)))
        for from_cell, cell in ((0.05, 0.1), (0.05, 0.15), (0.025, 0.1), (0.1, 0.1)):
            a, b = coarse_before(m, from_cell, cell), v2.coarse(m, from_cell, cell)
            assert a[1:] == b[1:] and a[0].dtype == b[0].dtype and a[0].shape == b[0].shape
            assert np.array_equal(a[0], b[0])


def _support():
    """A two-owner RangeSupport with bodies and delayed hazards on every sample (fake tracker)."""
    def cell(x, y, w=3, hgt=5):
        n = int(round(1 / 0.05))
        return Mask(np.ones((hgt * n // 10, w * n // 10), bool), int(round(x / 0.05)), int(round(y / 0.05)))
    units = {7: (30.0, 8.0), 9: (36.0, 9.0)}
    now = {iid: ("Song Heavy Sentry", {"pos": p}, None) for iid, p in units.items()}
    trk = NS(now=now, tables={"Song Heavy Sentry": NS(cell=0.05)}, hero=None, T=0.0,
             estimate=lambda iid, k: NS(raw=cell(units[iid][0] + .02 * k, units[iid][1]), fam="X", core=None,
                                        haz=cell(units[iid][0] + 1.0 + .05 * k, units[iid][1] - .5, 2, 2)))
    rs = v2.RangeSupport.build(trk, margin_mode="rule")
    assert rs.haz_raw and len(rs.raw[0]) >= 2
    return rs


def _queries(rs):
    rng = np.random.default_rng(5)
    for _ in range(12):
        a = int(rng.integers(0, 60)); n = int(rng.integers(1, 12))
        tk = (np.arange(a, a + n) + rng.integers(0, 2, n)) / 60.0
        x = rng.uniform(26.0, 40.0, (3, n)); y = rng.uniform(6.0, 11.0, (3, n))
        yield x, y, tk


def test_hazard_stack_is_filled_on_the_read_samples_with_the_whole_stack_cells():
    rs = _support()
    for iid in (7, 9):
        whole = rs.parts_stacks(list(rs.haz_raw[iid]))[0]
        seen = set()
        for x, y, tk in _queries(rs):
            got = rs.occupied_hazards(x, y, tk, {iid})
            assert np.array_equal(got, rs.occ_stack_b(whole, x, y, tk, {iid}))
            seen |= rs.samples_read(tk)
        stack, filled = rs._hazard_cache[frozenset({iid})]
        assert filled == seen and all(np.array_equal(stack[s], whole[s]) for s in seen)
        assert not any(stack[s].any() for s in range(len(rs.samples)) if s not in seen)   # unread: never dilated


def test_b2_owner_stack_is_filled_on_the_read_samples_with_the_whole_stack_cells():
    rs = _support()
    geo = B2Geometry(forecast=None, origin=0, move=None, instance=None)
    for iid in (7, 9):
        whole = rs._stack_of(lambda owner: owner == iid)
        assert whole.any()
        for x, y, tk in _queries(rs):
            got = geo._owner_occupancy(rs, x, y, tk, iid)
            assert np.array_equal(got, rs.occ_stack_b(whole, x, y, tk, {iid}))
        _, stack, filled = geo._owners[(id(rs), iid)]
        assert filled and all(np.array_equal(stack[s], whole[s]) for s in filled)
        assert len(filled) < len(rs.samples) and not any(stack[s].any() for s in range(len(rs.samples)) if s not in filled)


def test_partial_stack_of_pastes_only_the_named_samples():
    rs = _support()
    whole = rs._stack_of(lambda owner: owner != 9)
    part = np.zeros_like(whole)
    assert rs._stack_of(lambda owner: owner != 9, into=part, samples={0, 3, 7}) is part
    assert all(np.array_equal(part[s], whole[s]) for s in (0, 3, 7))
    assert not part[[s for s in range(len(rs.samples)) if s not in (0, 3, 7)]].any()


def test_batched_strike_rows_roll_as_each_row_alone(params, terrain):
    from ssbot.combat.knife_chain_vault import strike_program
    for s in (0, 3, 5):
        sim = live_sim(params, terrain, s)
        rows = [strike_program(2737 + s, 2, 1, d, 16)["masks"] for d in (1, 1, -1)]
        rows[1] = [m & ~(B["L"] | B["R"]) for m in rows[1]]
        both = sim.roll(np.asarray(rows, np.int64))
        for i, row in enumerate(rows):
            one = sim.roll(np.asarray(row, np.int64)[None])
            for name in ("flags", "pos", "vel", "box"):
                assert np.array_equal(getattr(both, name)[i], getattr(one, name)[0])


def press_now_row_before(sim, body, F, hold, side, attacking_target=False):
    """knife_chain_transfer.press_now_row as it was (057c702a): one roll per row, in order."""
    from ssbot.combat.knife_chain_vault import strike_program
    if body is None:
        return None
    body = np.asarray(body, float)
    if body.shape == (4,):
        if not np.isfinite(body).all():
            return None
    elif body.ndim != 2 or body.shape[1] != 4:
        return None
    direction = 1 if side == B["R"] else -1 if side == B["L"] else 0
    pj = len(sim.prefix) + 2
    cd = float(np.asarray(sim.start).reshape(K.K, -1)[K.ATK_CD, 0]); dt = float(sim.params.frame_time)
    if not math.isfinite(cd) or not math.isfinite(dt) or dt <= 0 or cd > pj * dt + 1e-9:
        return None
    for d in ((direction, 0, -direction) if direction else (0,)):
        row = strike_program(F, hold, 1, d or 1, 16)
        if d == 0:
            row["masks"] = [m & ~(B["L"] | B["R"]) for m in row["masks"]]
        ro = sim.roll(np.asarray(row["masks"], np.int64)[None]); flags = ro.flags[0]
        attacking = (flags & K.F_ATTACKING) != 0
        fresh = (attacking[pj] and not attacking[pj - 1]) or (attacking[pj + 1] and not attacking[pj])
        if not fresh or flags[pj - 1] & K.F_GROUND:
            continue
        for j in range(pj + PM.ACTIVE[0], min(pj + PM.ACTIVE[1] + 1 - T.CONTACT_END_MARGIN_F, len(flags))):
            if flags[j] & K.F_GROUND:
                break
            b = body if body.ndim == 1 else body[j] if j < len(body) else None
            if b is None or not np.isfinite(b).all():
                continue
            poly = np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]])
            if all(PM.meets(PM.slash_poly(face, alt) + ro.pos[0, j], poly) for face in (-1, 1) for alt in (False, True)):
                if attacking_target and T.grazes_body(ro.box[0], body, j - 2):
                    break
                row.update(contact_frame=sim.fo + j, approach_direction=d, contact_velocity=ro.vel[0, j].tolist())
                return row
    return None


def _same(a, b):
    if a is None or b is None:
        return a is None and b is None
    return a.keys() == b.keys() and all(np.array_equal(np.asarray(a[k]), np.asarray(b[k])) for k in a)


@pytest.mark.parametrize("margin", [0, 1])
def test_press_now_row_returns_what_one_roll_per_row_returned(params, terrain, monkeypatch, margin):
    monkeypatch.setattr(T, "CONTACT_END_MARGIN_F", margin)
    found = 0
    for s in range(0, 7):
        sim = live_sim(params, terrain, s); e = target(2735 + s)
        held = body_box(e); w = T.contact_body_witness(e, ROWS)
        for body in (held, w, held + np.array([1.5, 0., 1.5, 0.]), held - np.array([1.2, 0., 1.2, 0.])):
            for side in (0, B["R"], B["L"]):
                for attacking in (False, True):
                    for hold in (0, 2):
                        a = press_now_row_before(sim, body, 2737 + s, hold, side, attacking)
                        b = T.press_now_row(sim, body, 2737 + s, hold, side, attacking)
                        assert _same(a, b)
                        found += a is not None
    assert found   # the comparison covers accepted rows, not only rejections
