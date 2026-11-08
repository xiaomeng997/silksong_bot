"""Task 182 seq 287: V2Feed's per-tick support builds reuse their own pure dilations (SupportDilationCache through
forum_v2.dilate_group): exact on the whole input, private copies, this tick's and the previous tick's results only, owned by
one feed. The real support (RangeTracker -> V2Feed.support -> RangeSupport) is the same stack for stack and query for query
with the reuse on and off."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import attack_range as ar, forum_v2 as v2
from ssbot.combat.knife_chain_raster_cache import (ExactDilationCache, SupportDilationCache, current_dilation_cache,
                                                   exact_dilation_scope, support_dilation_scope)
from tests.test_attack_range_types import CLAPPER, _cl, _clapper_table


def parts():
    a = np.zeros((5, 8), bool)
    a[1:4, 2:6] = True
    return [(a, -7, 11), (np.eye(4, dtype=bool), -2, 13)]


def other():
    a = np.zeros((6, 6), bool)
    a[2:5, 1:3] = True
    return [(a, 4, 2)]


def same(a, b):
    assert a[1:] == b[1:] and a[0].dtype == b[0].dtype
    assert np.array_equal(a[0], b[0])


def tick(cache, frame, *inputs, m=.5):
    """One support-build scope of tick `frame`, one dilate_group per input; each result checked against the original."""
    out = []
    with support_dilation_scope(cache, frame) as c:
        assert c is cache and current_dilation_cache() is cache
        for ps in inputs:
            got = v2.dilate_group(ps, m)
            same(got, v2._dilate_group_uncached(ps, m))
            out.append(got)
    assert current_dilation_cache() is None
    return out


def counts(c):
    return c.hits, c.misses


# ---- reuse and copies

def test_a_repeat_in_the_tick_is_the_same_result_as_a_private_copy():
    c = SupportDilationCache()
    a, b = tick(c, 10, parts(), [(x.copy(), i, j) for x, i, j in parts()])
    assert counts(c) == (1, 1) and a[0] is not b[0] and not np.shares_memory(a[0], b[0])


def test_changing_a_returned_array_never_changes_a_later_result():
    c = SupportDilationCache()
    ps = parts()
    want = v2._dilate_group_uncached(ps, .5)
    with support_dilation_scope(c, 10):
        first = v2.dilate_group(ps, .5)
        first[0][:] = False                                                  # the miss's own array
        second = v2.dilate_group(ps, .5)
        same(second, want)
        second[0][:] = False                                                 # a hit's copy
        same(v2.dilate_group(ps, .5), want)
    with support_dilation_scope(c, 11):
        same(v2.dilate_group(ps, .5), want)                                  # the previous tick's entry, untouched
    assert counts(c) == (3, 1)


# ---- what must not hit

def _shape(ps):
    a, x, y = ps[0]
    return [(np.pad(a, ((0, 1), (0, 0))), x, y)] + ps[1:]


def _pixel(ps):
    a, x, y = ps[0]
    b = a.copy()
    b[0, 0] = not b[0, 0]
    return [(b, x, y)] + ps[1:]


def _dtype(ps):
    a, x, y = ps[0]
    return [(a.astype(np.uint8), x, y)] + ps[1:]


def _x(ps):
    a, x, y = ps[0]
    return [(a, x + 1, y)] + ps[1:]


def _y(ps):
    a, x, y = ps[0]
    return [(a, x, y + 1)] + ps[1:]


@pytest.mark.parametrize("change", [_pixel, _shape, _dtype, _x, _y, lambda ps: list(reversed(ps))],
                         ids=["pixel", "shape", "dtype", "x", "y", "order"])
def test_every_change_of_the_rasters_misses(change):
    c = SupportDilationCache()
    ps = parts()
    tick(c, 10, ps)
    with support_dilation_scope(c, 11):
        q = change(ps)
        same(v2.dilate_group(q, .5), v2._dilate_group_uncached(q, .5))
    assert counts(c) == (0, 2)


def test_margin_and_cell_are_part_of_the_key():
    c = SupportDilationCache()
    ps = parts()
    with support_dilation_scope(c, 10):
        for m, cell in ((.5, v2.CELL), (.75, v2.CELL), (.5, v2.CELL * 2)):
            same(v2.dilate_group(ps, m, cell), v2._dilate_group_uncached(ps, m, cell))
    assert counts(c) == (0, 3)


def test_the_kernel_constants_are_part_of_the_key(monkeypatch):
    c = SupportDilationCache()
    ps = parts()
    tick(c, 10, ps)
    monkeypatch.setattr(v2, "HB_HX", v2.HB_HX + .25)
    tick(c, 11, ps)
    assert counts(c) == (0, 2)


@pytest.mark.parametrize("which", ["box_kernel", "_dilate_group_uncached"])
def test_a_replaced_kernel_or_implementation_takes_the_original_path(monkeypatch, which):
    c = SupportDilationCache()
    ps = parts()
    calls = []
    old = getattr(v2, which)

    def wrapped(*a, **k):
        calls.append(1)
        return old(*a, **k)

    monkeypatch.setattr(v2, which, wrapped)
    with support_dilation_scope(c, 10):
        v2.dilate_group(ps, .5)
        v2.dilate_group(ps, .5)
    assert len(calls) == 2 and not c.entries and counts(c) == (0, 0)


class _Sub(np.ndarray):
    pass


@pytest.mark.parametrize("bad", ["subclass", "scalar"])
def test_an_unknown_input_is_computed_every_time(bad):
    c = SupportDilationCache()
    a, x, y = parts()[0]
    ps = [(a.view(_Sub), x, y)] if bad == "subclass" else [(a, type("I", (int,), {})(x), y)]
    with support_dilation_scope(c, 10):
        one = v2.dilate_group(ps, .5)
        two = v2.dilate_group(ps, .5)
    same(one, two)
    assert c.uncacheable == 2 and counts(c) == (0, 0) and not c.entries


# ---- the lifetime

def test_the_previous_tick_serves_and_what_it_used_stays_for_the_next():
    c = SupportDilationCache()
    ps = parts()
    tick(c, 10, ps)
    tick(c, 11, ps)
    tick(c, 12, ps)
    assert counts(c) == (2, 1)


def test_a_result_no_tick_used_for_two_ticks_is_gone():
    c = SupportDilationCache()
    a, b = parts(), other()
    tick(c, 10, a)
    tick(c, 11, b)                                                           # a is the previous tick's
    assert len(c.previous) == 1 and len(c.entries) == 1
    tick(c, 12, b)                                                           # hit from the previous tick; a is gone
    assert counts(c) == (1, 2) and len(c.previous) == 1
    tick(c, 13, a)
    assert counts(c) == (1, 3)


def test_only_two_generations_are_held():
    c = SupportDilationCache()
    for f in range(10, 16):
        tick(c, f, [(parts()[0][0], f, 0)])
    assert len(c.entries) == 1 and len(c.previous) == 1


def test_a_skipped_frame_is_no_tick():
    c = SupportDilationCache()
    ps = parts()
    tick(c, 10, ps)
    tick(c, 12, ps)                                                          # the tick after, two frames on
    assert counts(c) == (1, 1)


def test_a_second_build_of_the_tick_keeps_its_results():
    c = SupportDilationCache()
    a, b = parts(), other()
    tick(c, 10, a)
    tick(c, 11, b)
    tick(c, 11, a, b)                                                        # same frame: no rotation
    assert counts(c) == (2, 2) and len(c.previous) == 1


def test_a_frame_rewind_clears_everything():
    c = SupportDilationCache()
    ps = parts()
    tick(c, 10, ps)
    tick(c, 11, ps)
    tick(c, 5, ps)
    assert counts(c) == (1, 2) and not c.previous and len(c.entries) == 1 and c.frame == 5


def test_reset_clears_everything_and_the_cache_stays_usable():
    c = SupportDilationCache()
    ps = parts()
    tick(c, 10, ps)
    tick(c, 11, ps)
    c.reset()
    assert not c.entries and not c.previous and c.frame is None and c.active
    tick(c, 12, ps)
    assert counts(c) == (1, 2)


def test_one_tick_is_bounded(monkeypatch):
    monkeypatch.setattr(SupportDilationCache, "MAX_ENTRIES", 2)
    c = SupportDilationCache()
    inputs = [[(parts()[0][0], i, 0)] for i in range(4)]
    tick(c, 10, *inputs)
    tick(c, 10, inputs[3])                                                   # past the bound: computed again
    assert len(c.entries) == 2 and counts(c) == (0, 5)
    tick(c, 10, inputs[0])
    assert counts(c) == (1, 5)


# ---- scopes, instances, threads

def test_an_exception_in_the_build_ends_the_scope_and_the_cache_goes_on():
    c = SupportDilationCache()
    ps = parts()
    with pytest.raises(RuntimeError, match="in the build"):
        with support_dilation_scope(c, 10):
            v2.dilate_group(ps, .5)
            raise RuntimeError("in the build")
    assert current_dilation_cache() is None and c.active and len(c.entries) == 1
    tick(c, 11, ps)
    assert counts(c) == (1, 1)


def test_two_owners_never_share_a_result():
    a, b = SupportDilationCache(), SupportDilationCache()
    ps = parts()
    tick(a, 10, ps)
    tick(b, 10, ps)
    assert counts(a) == (0, 1) and counts(b) == (0, 1) and a.entries is not b.entries


def test_a_proposal_inside_a_build_has_its_own_cache_and_the_build_goes_on():
    c = SupportDilationCache()
    ps = parts()
    with support_dilation_scope(c, 10):
        v2.dilate_group(ps, .5)
        with exact_dilation_scope() as prop:
            assert type(prop) is ExactDilationCache and current_dilation_cache() is prop
            v2.dilate_group(ps, .5)
            v2.dilate_group(ps, .5)
            assert prop.misses == 1 and prop.hits == 1
        assert current_dilation_cache() is c and not prop.active and not prop.entries
        v2.dilate_group(ps, .5)
    assert counts(c) == (1, 1) and len(c.entries) == 1


def test_a_build_inside_a_proposal_uses_the_proposals_cache_and_leaves_the_feeds_alone():
    c = SupportDilationCache()
    ps = parts()
    with exact_dilation_scope() as prop:
        with support_dilation_scope(c, 10) as got:
            assert got is prop
            v2.dilate_group(ps, .5)
        assert current_dilation_cache() is prop and prop.misses == 1
    assert c.frame is None and not c.entries and counts(c) == (0, 0)


def test_the_scope_is_private_to_its_thread():
    c = SupportDilationCache()
    with support_dilation_scope(c, 10):
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(current_dilation_cache).result() is None


# ---- the real support, reuse on against off

def _feeds(monkeypatch, reuse=True):
    monkeypatch.setattr(v2, "SUPPORT_DILATE_REUSE", reuse)
    fd = v2.V2Feed()
    fd.trk = ar.RangeTracker(tables={CLAPPER: _clapper_table()})
    return fd


IDLE, CAST = ["Idle"] * 5, ["Cast Slam Antic", "Jump", "Slam 2"]
SCRIPT = [(a, b) for a, b in zip(IDLE + CAST + IDLE + ["Jump Antic"] * 4 + ["Idle"] * 3,
                                 IDLE + ["Idle"] * 3 + IDLE + ["Idle"] * 4 + ["Walk"] * 3)]


def _ent(st, x, **k):
    e = _cl(st, x=x, **k)
    e["cols"][0]["verts_world"] = [x - 1.0, 3.0, x + 1.0, 3.0, x + 1.0, 6.8, x - 1.0, 6.8]      # inside the standing-pose box
    return e


def _state(i, a, b):
    return {"dt": ar.FT, "f": 100 + i, "hero": {"pos": [24.0 + .1 * i, 4.5]},
            "ents": [_ent(a, 30.0, iid=3, tin=i * ar.FT), _ent(b, 38.0, flip=True, iid=4, tin=i * ar.FT)]}


GRID = np.array(np.meshgrid(np.arange(20.0, 48.0, .35), np.arange(3.0, 12.0, .35))).reshape(2, -1)
TKS = np.array([0, 2, 5, 9, 14, 21, 30, 40, 55]) * ar.FT


def _queries(rs):
    x, y = np.repeat(GRID[0][:, None], len(TKS), axis=1), np.repeat(GRID[1][:, None], len(TKS), axis=1)
    tk = TKS
    out = {"occupied": rs.occupied(x, y, tk), "esc": rs.occupied_esc(x, y, tk), "ret": rs.occupied_ret(x, y, tk),
           "only3": rs.occupied_only(x, y, tk, [3]), "only4": rs.occupied_only(x, y, tk, [4]),
           "without3": rs.occupied_without(x, y, tk, 3), "without4": rs.occupied_without(x, y, tk, {4}),
           "haz3": rs.occupied_hazards(x, y, tk, [3]), "haz34": rs.occupied_hazards(x, y, tk, [3, 4])}
    dash = rs.occupied_dash(x, y, tk)
    out["dash"] = None if dash is None else dash
    return out


def _arrays_equal(a, b, what):
    if a is None or b is None:
        assert a is None and b is None, what
    else:
        assert a.dtype == b.dtype and np.array_equal(a, b), what


def _same_structure(a, b, what):
    if isinstance(a, np.ndarray):
        _arrays_equal(a, b, what)
    elif isinstance(a, dict):
        assert set(a) == set(b), what
        for k in a:
            _same_structure(a[k], b[k], (what, k))
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), what
        for i, (u, v) in enumerate(zip(a, b)):
            _same_structure(u, v, (what, i))
    elif isinstance(a, (set, frozenset)):
        assert a == b, what
    else:
        assert a == b, what


def _compare(on, off, what):
    for name in ("stack", "stack_esc", "stack_dash", "stack_ret"):
        _arrays_equal(getattr(on, name, None), getattr(off, name, None), (what, name))
    for name in ("raw", "layers", "haz_raw", "ret_tags", "ret_parts", "n_est", "focus", "dash_focus", "k_shift", "samples"):
        _same_structure(getattr(on, name, None), getattr(off, name, None), (what, name))
    qa, qb = _queries(on), _queries(off)
    for k in qa:
        _arrays_equal(qa[k], qb[k], (what, k))


@pytest.mark.parametrize("focus", [None, 3, 4], ids=["no_focus", "focus3", "focus4"])
def test_the_real_support_is_the_same_with_the_reuse(monkeypatch, focus):
    on, off = _feeds(monkeypatch, True), _feeds(monkeypatch, False)
    assert isinstance(on.dil, SupportDilationCache) and off.dil is None
    seen = dict(haz=0, dash=0)
    fcast = NS(fc=None)
    for i, (a, b) in enumerate(SCRIPT):
        f = 100 + i
        st = {f: _state(i, a, b)}
        on.feed(st, f)
        off.feed(st, f)
        ra, rb = on.support(fcast, f, focus=focus).rs, off.support(fcast, f, focus=focus).rs
        assert current_dilation_cache() is None
        _compare(ra, rb, (i, a, b))
        seen["haz"] += bool(ra.haz_raw)
        seen["dash"] += ra.stack_dash is not None
        if i == 0:
            assert ra.stack.any()
    assert on.dil.hits > 0 and on.dil.misses > 0 and on.dil.uncacheable == 0
    assert seen["haz"] > 0
    if focus is not None:
        assert seen["dash"] > 0


def _ret_tracker(x3, x4):
    """As tests/test_return_body315._tracker: two idle units whose estimates are their 1-cell bodies, with standing poses."""
    from tests.test_forum_v2 import _cell_mask

    def est(iid, k):
        core = _cell_mask(x3 if iid == 3 else x4, 6.0)
        return NS(raw=core, core=core, haz=None, fam=None)

    now = {3: (CLAPPER, {"pos": (x3, 6.0), "fsms": [{"state": "Idle", "t": 0.0}]}, None),
           4: (CLAPPER, {"pos": (x4, 6.0), "fsms": [{"state": "Walk", "t": 0.0}]}, None)}
    return NS(now=now, tables={CLAPPER: NS(cell=0.05)}, hero=None, T=0.0, estimate=est,
              standing_body=lambda iid, k: _cell_mask(x3 if iid == 3 else x4, 6.0))


def test_the_return_body_layer_is_the_same_with_the_reuse(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    on, off = _feeds(monkeypatch, True), _feeds(monkeypatch, False)
    fcast = NS(fc=None)
    for f, (x3, x4) in enumerate([(24.0, 30.0), (24.0, 30.0), (24.2, 30.0), (24.2, 30.0), (24.4, 29.5)], 100):
        on.trk = off.trk = _ret_tracker(x3, x4)
        on.feed({}, f)
        off.feed({}, f)
        ra, rb = on.support(fcast, f, focus=3, body2=4).rs, off.support(fcast, f, focus=3, body2=4).rs
        assert ra.body2 == 4 and ra.stack_ret is not None and ra.ret_tags
        _compare(ra, rb, f)
    assert on.dil.hits > 0 and on.dil.uncacheable == 0


def test_a_build_runs_inside_the_feeds_own_scope_only(monkeypatch):
    fd = _feeds(monkeypatch, True)
    seen = []
    build = v2.RangeSupport.build

    def spy(*a, **k):
        seen.append(current_dilation_cache())
        return build(*a, **k)

    monkeypatch.setattr(v2.RangeSupport, "build", spy)
    st = {100: _state(0, "Idle", "Idle")}
    fd.feed(st, 100)
    fd.support(NS(fc=None), 100)
    assert seen == [fd.dil] and current_dilation_cache() is None
    assert fd.dil.frame == 100


def test_nothing_fed_yet_builds_without_the_cache(monkeypatch):
    fd = _feeds(monkeypatch, True)
    seen = []
    build = v2.RangeSupport.build

    def spy(*a, **k):
        seen.append(current_dilation_cache())
        return build(*a, **k)

    monkeypatch.setattr(v2.RangeSupport, "build", spy)
    fd.support(NS(fc=None), 100)
    assert seen == [None] and fd.dil.frame is None and not fd.dil.entries


def test_the_switch_off_has_no_cache_and_no_scope(monkeypatch):
    fd = _feeds(monkeypatch, False)
    seen = []
    build = v2.RangeSupport.build

    def spy(*a, **k):
        seen.append(current_dilation_cache())
        return build(*a, **k)

    monkeypatch.setattr(v2.RangeSupport, "build", spy)
    st = {100: _state(0, "Idle", "Idle")}
    fd.feed(st, 100)
    fd.support(NS(fc=None), 100)
    assert fd.dil is None and seen == [None]


def test_the_feeds_reset_clears_its_results(monkeypatch):
    fd = _feeds(monkeypatch, True)
    st = {100: _state(0, "Idle", "Idle")}
    fd.feed(st, 100)
    fd.support(NS(fc=None), 100)
    assert fd.dil.entries
    fd.reset()
    assert not fd.dil.entries and not fd.dil.previous and fd.dil.frame is None


def test_two_feeds_do_not_share_results(monkeypatch):
    a, b = _feeds(monkeypatch, True), _feeds(monkeypatch, True)
    assert a.dil is not b.dil
    st = {100: _state(0, "Idle", "Idle")}
    a.feed(st, 100)
    a.support(NS(fc=None), 100)
    b.feed(st, 100)
    b.support(NS(fc=None), 100)
    assert b.dil.misses > 0 and counts(a.dil) == counts(b.dil)              # (repeats inside one build hit; nothing from a)


def test_a_support_kept_between_rebuilds_runs_no_build(monkeypatch):
    monkeypatch.setattr(v2, "SUPPORT_DILATE_REUSE", True)
    fd = v2.V2Feed(every=2)
    fd.trk = ar.RangeTracker(tables={CLAPPER: _clapper_table()})
    st = {100: _state(0, "Idle", "Idle"), 101: _state(1, "Idle", "Idle")}
    fd.feed(st, 100)
    a = fd.support(NS(fc=None), 100)
    n = counts(fd.dil)
    fd.feed(st, 101)
    b = fd.support(NS(fc=None), 101)
    assert b.rs.stack is a.rs.stack and fd.reused == 1 and counts(fd.dil) == n


def test_the_switch_has_a_runtime_manifest_binding(tmp_path):
    from ssbot.train.forum_measure_manifest import configuration_manifest
    src = tmp_path / "ssbot"
    (src / "combat").mkdir(parents=True)
    (src / "combat/forum_v2.py").write_bytes(Path(v2.__file__).read_bytes())
    m = configuration_manifest(src, None, environ={"SSBOT_FORUM_SUPPORT_DILATE_REUSE": "0"}, modules={"ssbot.combat.forum_v2": v2})
    e = m["switches"]["SSBOT_FORUM_SUPPORT_DILATE_REUSE"]
    assert e["resolution"] == "runtime_binding"
    assert e["effective"] == {"ssbot.combat.forum_v2.SUPPORT_DILATE_REUSE": v2.SUPPORT_DILATE_REUSE}


def test_the_reuse_is_on_by_default():
    import os
    if "SSBOT_FORUM_SUPPORT_DILATE_REUSE" not in os.environ:
        assert v2.SUPPORT_DILATE_REUSE is True
