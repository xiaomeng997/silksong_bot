"""Attack-range stage B types: the Reed (stab decided at Stab 1, the pin decided at Throw Aim and in flight, the
counter from Block with its vertical aim) and the Minister (charge aim bins at the antic start, the parry counter),
and the stage B hooks (callable branches, decision extras / observed facing, hit-started families, type extras)."""
import math

import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.combat.are_types import minister, module_of, reed

FT = ar.FT


def test_registry_has_stage_b_types():
    for key, short in (("Song Reed", "Reed"), ("Song Administrator", "Minister")):
        sp = ar.SPECS[key]
        assert sp.short == short
        assert module_of(short).SPEC is sp
        for st, fam in sp.start.items():
            assert st in sp.fam_states[fam]
        for fam, st in sp.primary.items():
            assert st in sp.fam_states[fam]
        assert set(sp.branches) == set(sp.fam_states)


@pytest.mark.parametrize("dy,name", [(-2.0, "v-4"), (-8.0, "v-10"), (6.0, "v8"), (0.2, "v0"), (-0.6, "v-2")])
def test_counter_branch_is_the_speed_y_bin(dy, name):
    # Parry Y Aim: Speed Y = clamp(2 (hero y - y), +-10), bins of 2 u/s
    assert reed.counter_branch(x=0.0, y=10.0, s=1, hero_x=3.0, hero_y=10.0 + dy) == name


def _step(seg, st, T, x=20.0, y=6.0, s=1, hx=26.0, hy=4.0, tin=0.0, vx=0.0):
    return seg.step(st, T, x, y, s, hx, tin, vx=vx, hero_y=hy)


def test_counter_branch_union_until_parry_slash():
    seg = ar.Segmenter(reed.SPEC)
    T = 0.0
    for _ in range(3):
        _step(seg, "Defend", T)
        T += FT
    inst = None
    for n in range(31):
        inst = _step(seg, "Block", T, tin=n * FT)
        T += FT
    assert inst.fam == "RE_COUNTER" and inst.branch is None      # the vertical aim is still the union
    inst = _step(seg, "Parry Slash", T, y=6.0, hy=4.0)              # hero 2 u below: Speed Y -4
    assert inst.branch == "v-4" and inst.branch_t == pytest.approx(T)


def test_hit_that_starts_a_counter_does_not_interrupt_it():
    from ssbot.tools.attack_range_build import segment
    n = 60
    st = ["Defend"] * 5 + ["Block"] * 31 + ["Parry Slash"] * 20 + ["Alert"] * 4
    T = np.arange(n) * FT
    tr = {"T": T, "st": st, "flip": np.ones(n, np.int8), "hidden": np.zeros(n, np.int8), "x": np.full(n, 20.0),
          "y": np.full(n, 6.0), "hx": np.full(n, 26.0), "hy": np.full(n, 4.0), "tin": np.zeros(n),
          "vx": np.zeros(n), "hits": [float(T[4])], "clash": []}
    insts, _ = segment(tr, reed.SPEC, 1)
    assert [r["inst"].fam for r in insts] == ["RE_COUNTER"] and not insts[0]["interrupted"]
    tr["hits"] = [float(T[4]), float(T[20])]                          # a second hit during Block does
    insts, _ = segment(tr, reed.SPEC, 1)
    assert insts[0]["interrupted"]


def test_stab_decision_takes_the_observed_facing():
    seg = ar.Segmenter(reed.SPEC)
    T = 0.0
    for _ in range(38):
        _step(seg, "Stab Antic", T, s=1)
        T += FT
    inst = _step(seg, "Stab 1", T, s=-1)          # turned during the antic: the observed facing at Stab 1
    assert inst.fam == "RE_STAB" and inst.dec["s"] == -1 and inst.dec["L"] == pytest.approx(reed.STAB_L)


def test_pin_rule_aim_and_clamp():
    s, L, ex = reed.pin_rule(20.0, 8.0, -1.3, 30.0, 8.0 + 10.0 * math.tan(math.radians(20)))
    assert s == 0 and L == 0.0 and ex["aim"] == pytest.approx(20.0) and ex["vx0"] == pytest.approx(-1.3)
    assert reed.pin_rule(20.0, 8.0, 0.0, 21.0, 0.0)[2]["aim"] == -70.0      # straight down: clamped
    assert reed.pin_rule(20.0, 8.0, 0.0, 21.0, 20.0)[2]["aim"] == 45.0      # straight up: clamped


def _bbox(ps):
    a = np.vstack(ps)
    return a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()


def test_pin_decided_release_windows_and_spawn():
    dec = {"t": 1.0, "s": -1, "aim": 0.0, "vx0": 0.0}
    pos = (30.0, 8.0)
    assert reed.pin_decided(dec, 1.0, pos, 1.0 + 23 * FT) == []                # before the first release window
    boxes = reed.pin_decided(dec, 1.0, pos, 1.0 + 24 * FT)
    assert len(boxes) == 1                                                     # the release frame: the spawn box
    x0, y0, x1, y1 = _bbox(boxes)                                              # (axis-aligned on its first frame)
    assert (x0 + x1) / 2 == pytest.approx(30.0 - 1.53) and (y0 + y1) / 2 == pytest.approx(8.0 - 0.54)
    assert (x1 - x0, y1 - y0) == pytest.approx((reed.PIN_LEN, reed.PIN_WID))
    up = reed.pin_decided({**dec, "aim": 30.0}, 1.0, pos, 1.0 + 24 * FT)
    assert (_bbox(up)[1] + _bbox(up)[3]) / 2 == pytest.approx(8.0 + 0.48)     # Throw Up's spawn point
    later = reed.pin_decided(dec, 1.0, pos, 1.0 + 36 * FT)                     # both windows: steps 9-10 and 5-7
    assert len(later) == (2 + 3) * reed.PIECES
    assert _bbox(later)[0] == pytest.approx(30.0 - 1.53 - 10 * 0.62 - reed.PIN_LEN / 2, abs=1e-6)
    assert _bbox(later)[2] == pytest.approx(30.0 - 1.53 - 5 * 0.62 + reed.PIN_LEN / 2, abs=1e-6)


def test_pin_path_in_flight():
    b0 = reed.pin_path(30.0, 8.0, -31.0, 0.0, 0.0)
    assert _bbox(b0) == pytest.approx((30.0 - reed.PIN_LEN / 2, 8.0 - reed.PIN_WID / 2, 30.0 + reed.PIN_LEN / 2,
                                       8.0 + reed.PIN_WID / 2))
    b6 = reed.pin_path(30.0, 8.0, -31.0, 0.0, 6 * FT)                          # 0.1 s = 5 steps of 0.62 u
    assert (_bbox(b6)[0] + _bbox(b6)[2]) / 2 == pytest.approx(30.0 - 5 * 0.62) and len(b6) == reed.PIECES
    assert len(reed.pin_path(30.0, 8.0, -31.0, 0.0, FT)) == 2 * reed.PIECES     # 0 or 1 step
    assert reed.pin_path(30.0, 3.3, 0.0, -31.0, 0.2) == []                      # it reached the floor
    c = math.cos(math.radians(45))
    x0, y0, x1, y1 = _bbox(reed.pin_path(30.0, 8.0, -31.0 * c, -31.0 * c, 0.0))   # turned to its flight
    assert x1 - x0 == pytest.approx((reed.PIN_LEN + reed.PIN_WID) * c, abs=1e-6)


def test_real_pin_reads_the_exported_aabb():
    # its spawn frame: the axis-aligned box; then the AABB of the rectangle turned to its flight
    cx, cy, rot, ps = reed.real_pin([20.0, 5.0, 20.0 + reed.PIN_LEN, 5.0 + reed.PIN_WID], -30.96, 1.5)
    assert rot is False and len(ps) == 1
    a = math.atan2(1.5, 30.96)
    w = reed.PIN_LEN * math.cos(a) + reed.PIN_WID * math.sin(a)
    h = reed.PIN_LEN * math.sin(a) + reed.PIN_WID * math.cos(a)
    cx, cy, rot, ps = reed.real_pin([20.0, 5.0, 20.0 + w, 5.0 + h], -30.96, 1.5)
    assert rot is True and len(ps) == reed.PIECES
    assert _bbox(ps) == pytest.approx((20.0, 5.0, 20.0 + w, 5.0 + h), abs=0.01)


def test_evade_direction_is_decided_at_the_evade_entry():
    for sp, turned in ((reed.SPEC, -1), (minister.SPEC, -1)):
        seg = ar.Segmenter(sp)
        _step(seg, "Evade Antic", 0.0, s=1, hx=21.0)                         # the hero 1 u in front: it may
        assert seg.cur.branch is None                                          # cross: the union in the antic
        inst = _step(seg, "Evade", 8 * FT, s=turned, hx=19.0)
        assert inst.branch == "turned"
        seg = ar.Segmenter(sp)
        assert _step(seg, "Evade Antic", 0.0, s=1, hx=24.0).branch == "same"   # too far to cross: from the start
    seg = ar.Segmenter(reed.SPEC)
    assert _step(seg, "Evade", 0.0, s=1).branch == "same"                      # no antic: its own facing

def test_minister_charge_bins():
    # aim to the hero + (0, 1.5) in the facing frame, clamped +-45
    assert minister.charge_branch(x=20.0, y=8.0, s=1, hero_x=28.0, hero_y=6.5) == "a0"
    assert minister.charge_branch(x=20.0, y=8.0, s=-1, hero_x=12.0, hero_y=0.0) == "a-45"
    assert minister.charge_branch(x=20.0, y=8.0, s=1, hero_x=10.0, hero_y=8.0) == "a+45"    # behind: the edge
    seg = ar.Segmenter(minister.SPEC)
    _step(seg, "Chase", 0.0)
    inst = seg.step("Attack Antic", FT, 20.0, 8.0, 1, 28.0, 0.0, hero_y=8.0 + 8.0 * math.tan(math.radians(30)) - 1.5)
    assert inst.fam == "MI_CHARGE" and inst.branch == "a+30"


def test_tracker_draws_a_pin_in_flight_and_owns_it():
    tab = ar.RangeTable(spec=reed.SPEC, templates={}, meta={})
    trk = ar.RangeTracker({"Song Reed": tab})

    def state(px):
        return {"dt": FT, "hero": {"pos": [10.0, 4.0]},
                "ents": [{"type_key": "Song Reed", "iid": 7, "pos": [30.0, 8.0], "flipX": False,
                          "fsms": [{"state": "Alert", "t": 1.0}],
                          "cols": [{"name": "Song Reed", "enabled": True, "damage": 1,
                                    "verts_world": [29.5, 6.6, 30.6, 6.6, 30.6, 9.4, 29.5, 9.4]}]},
                         {"type_key": reed.PIN_TYPE, "iid": 99, "pos": [px, 7.5], "vel": [-31.0, 0.0],
                          "fsms": [{"state": "Fly", "t": 0.1}],
                          "cols": [{"name": "Song Reed Pin Projectile(Clone)", "enabled": True, "damage": 1}]}]}
    trk.feed(state(25.0))
    assert trk.obj_owner == {99: (7, pytest.approx(FT))}
    e0, e6 = trk.estimate(7, 0), trk.estimate(7, 6)
    bb0, bb6 = e0.haz.bbox(), e6.haz.bbox()
    assert bb0[0] == pytest.approx(25.0 - reed.PIN_LEN / 2, abs=0.06)
    assert bb0[0] - bb6[0] == pytest.approx(5 * 0.62, abs=0.06)                 # 5 physics steps later


def test_choristor_and_clapper_specs_unchanged_by_the_hooks():
    for key in ("Song Pilgrim 03", "Song Heavy Sentry"):
        sp = ar.SPECS[key]
        assert sp.hit_started == frozenset()
        assert not any(callable(v) for d in sp.branch.values() for v in d.values())
        assert getattr(module_of(sp.short), "extra", None) is None


def test_throw_transition_from_the_aiming_up_flag():
    assert reed.throw_branch(y=6.0, hero_y=9.0) == "up" and reed.throw_branch(y=6.0, hero_y=4.0) == "down"
    assert reed.throw_branch(y=6.0, hero_y=8.1) == "open"                     # near the line: both windows
    dec = {"t": 1.0, "s": 1, "aim": -20.0, "vx0": 0.0}                        # a Down throw
    t = 1.0 + 28 * FT
    plain = reed.pin_decided(dec, 1.0, (30.0, 8.0), t, aim_up="down")       # no transition: released at 24-25
    late = reed.pin_decided(dec, 1.0, (30.0, 8.0), t, aim_up="up")          # flag up, spawn down: 28-30
    both = reed.pin_decided(dec, 1.0, (30.0, 8.0), t, aim_up="open")
    assert len(late) == 1 and len(plain) > 1 and len(both) == len(plain) + len(late)
