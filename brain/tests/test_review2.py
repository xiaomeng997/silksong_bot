"""Task 1v1 review 2 (git diff 05271df..4fc31d8): regression tests for the defects the adversarial review confirmed in
the G3 down-slash family (SSBOT_FORUM_DSLASH), KEEP (SSBOT_FORUM_SPECIAL_KEEP) and the special table v2
(SSBOT_FORUM_SPECIAL_TABLE=v2)."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import dslash, special_mode
from ssbot.combat import forum_v2 as v2
from ssbot.combat import specials as sp
from ssbot.combat.forum_planner import K_DOWN, ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.knowledge import kinematics as kin
from tests.test_dslash import FLOOR_HAZARD, RX, _rising, _Tab, params  # noqa: F401
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena  # noqa: F401
from tests.test_special_mode import _support


def _tick(params, arena, monkeypatch, parts=None, prefix=None, setup=None, hx=34.0, start=None, T0=0.0):
    """test_dslash._tick with a prefix and a hook on the planner before its tick (the Reed in RE_STAB, certain)."""
    from ssbot.combat import stance_block
    monkeypatch.setattr(stance_block, "blocked", lambda *a, **k: None)
    monkeypatch.setattr(v2.RangeSupport, "reaction", lambda self, *a, **k: None)
    monkeypatch.setattr(dslash, "DSLASH", True)
    monkeypatch.setattr(dslash, "CERT", True)
    inst = NS(fam="RE_STAB", branch=None, t0=0.0, x0=RX, y0=FLOOR + 1.0, s=-1, hero_du=0.0)
    trk = NS(now={7: ("Song Reed", {"pos": (RX, FLOOR + 1.0), "type_key": "Song Reed"}, inst)},
             tables={"Song Reed": _Tab(0.0)}, hero=None, T=T0)
    rs = _support(parts or {}, trk)
    f = v2.V2Forecast(_reed_forecaster(None, x=RX).forecast(0.8), rs)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True), crest="Wanderer")
    pl.debug = True
    if setup is not None:
        setup(pl)
    start = kin.initial_state(params, hx, FLOOR + params.foot) if start is None else start
    pre = np.zeros(1, np.int64) if prefix is None else np.asarray(prefix, np.int64)
    r = pl.tick(_world(hx), start, kin.HoldState.idle(1), pre, f, _prefs(None, hx), _ctx())
    return pl, r


def test_certain_rows_get_the_hit_branch_at_their_contact(params, arena, monkeypatch):
    """A certain row whose scorer sees no hit (its body moved on at its present velocity) still gets its hit branch
    (the hit enemy's reaction and knockback), anchored at the certain contact; a dangerous reaction makes it unsafe.
    Before review2 such a row skipped the hit branch and stayed safe."""
    orig_score, orig_hb = ForumPlanner._score_forum, ForumPlanner._hit_branch
    seen = {}

    def score(self, *a, **k):
        sc = orig_score(self, *a, **k)
        ds = getattr(self, "_ds", None)
        if ds is not None:
            for k_ in ("first_f", "nh", "hits"):
                sc[k_] = np.asarray(sc[k_]).copy()
            q = self._ds_D0 + np.arange(len(ds.cmd))
            sc["first_f"][q] = -1                       # the scorer sees no hit on any family row
        return sc

    def hit_branch(self, f, start, latched, sc, rows, *a, **k):
        s, occ, cp = orig_hb(self, f, start, latched, sc, rows, *a, **k)
        ds = self._ds
        for n, r in enumerate(rows):
            q = int(r) - self._ds_D0
            if 0 <= q < len(ds.cmd) and ds.cert[q]:
                seen[int(r)] = (int(sc["first_f"][r]), int(sc["first_k"][r]), int(ds.c1[q]))
                s[n] = True                             # the hit enemy's reaction meets the hero
        return s, occ, cp

    monkeypatch.setattr(ForumPlanner, "_score_forum", score)
    monkeypatch.setattr(ForumPlanner, "_hit_branch", hit_branch)
    pl, r = _tick(params, arena, monkeypatch)
    ds, D0 = pl._ds, pl._ds_D0
    assert ds is not None and ds.cert.any()
    env = D0 + np.flatnonzero(ds.cert)
    assert seen and all(ff == c1 and kk == K_DOWN for ff, kk, c1 in seen.values())
    assert pl.audit.ds_anchor >= len(seen)
    safe = np.asarray(pl.last_sel["safe"])
    assert not safe[env].any()                          # the dangerous reaction is seen on every certain row


def test_no_certain_row_while_a_swing_is_pressed_in_the_prefix(params, arena, monkeypatch):
    """A swing already pressed (in the prefix) is on no family lane: no row is certain that tick (the certain lane and
    its hit-branch events would drop that swing's outcome)."""
    pl0, _ = _tick(params, arena, monkeypatch)
    assert pl0._ds is not None and pl0._ds.cert.any()
    pl, r = _tick(params, arena, monkeypatch, prefix=[kin.B_ATTACK | kin.B_DOWN])
    assert pl._ds is None or (not pl._ds.cert.any() and (pl._ds.c2 < 0).all())
    assert pl.audit.ds_busy == 1 and pl0.audit.ds_busy == 0


def _chain_ext(params, arena, monkeypatch):
    """A chain row of a first tick and the tick s frames later (the hero rolled along the row, the Reed's move clock on)
    at which its continuation "DS cont" holds both presses, the first still ahead: (name, ext, s, start, prefix)."""
    pl, _ = _tick(params, arena, monkeypatch)
    ds = pl._ds
    for q in np.flatnonzero(ds.c2 >= 0):
        ext = np.asarray(ds.ext[q], np.int64)
        pr = _rising(ext & kin.B_ATTACK)
        if len(pr) == 2 and pr[1] - pr[0] <= 32:
            s = int(pr[0]) - 1                          # "DS cont" = ext[s:]: the first press on its mask 1
            from ssbot.combat.holdfilter import hold_filter_jit
            start0 = kin.initial_state(params, 34.0, FLOOR + params.foot)
            lat, _ = hold_filter_jit(np.concatenate([[0], ext[:s - 1]])[None].astype(np.int64), kin.HoldState.idle(1))
            ro = kin.rollout(start0, lat, params, arena)
            return ds.names[q], ext, s, np.ascontiguousarray(ro.final[:, 0]), ext[s - 1:s].copy()
    pytest.skip("no chain row with both presses close enough in this scene")


def test_a_continued_chain_is_judged_with_both_bounces(params, arena, monkeypatch):
    """The continued chain ("DS cont") with its second press inside the horizon: before review2 it was a certain row
    whose lane had no bounce for its second strike (the certified second bounce on no lane). Now every certain row
    holding a second press is its chain twin: c2 set and both bounces on its events."""
    name, ext, s_, st, pre = _chain_ext(params, arena, monkeypatch)
    monkeypatch.setattr(dslash, "MAX_ROWS", 400)      # every row kept (the continuation is not cut by the row cap)

    def setup(pl):
        pl._ds_prev = ext[s_ - 1:].copy()

    pl, r = _tick(params, arena, monkeypatch, setup=setup, start=st, prefix=pre, T0=s_ * params.frame_time)
    ds = pl._ds
    assert ds is not None
    for q in range(len(ds.cmd)):
        pr = _rising(np.asarray(ds.cmd[q]) & kin.B_ATTACK)
        if ds.cert[q] and len(pr) >= 2:
            assert ds.c2[q] >= 0, ds.names[q]
            n_ev = int(np.count_nonzero(ds.ev[q] & kin.EV_POGO))
            assert n_ev == (2 if ds.c2[q] - int(dslash.EVPRE) < ds.ev.shape[1] else 1), ds.names[q]
    assert "DS cont" not in [n for q, n in enumerate(ds.names) if ds.cert[q] and len(_rising(ds.cmd[q] & kin.B_ATTACK)) >= 2]
    assert pl.audit.ds_cont2 >= 1


def test_keep_holds_the_chain_twin_not_the_plain_continuation(params, arena, monkeypatch):
    """KEEP (G4 4b) on a chain with both presses ahead: the kept row is the "+c<b>" twin (both bounces), never the plain
    "DS cont" (no second bounce on its lane)."""
    name, ext, s_, st, pre = _chain_ext(params, arena, monkeypatch)
    b = int(name.rsplit("+c", 1)[1])
    monkeypatch.setattr(special_mode, "KEEP", True)

    def setup(pl):
        pl._ds_prev = ext[s_ - 1:].copy()
        pl._kp = "ds"
        pl._ds_keep_b = b

    pl, r = _tick(params, arena, monkeypatch, setup=setup, start=st, prefix=pre, T0=s_ * params.frame_time)
    assert pl.audit.kp_ticks == 1
    if pl.audit.kp_kept:
        assert r.name == f"DS cont+c{b}"
    assert r.name != "DS cont"


def _v2_scene():
    """A synthetic theory grid: key 0 (in place), vy class 1; a block good only with jpost 1, a smaller block inside it
    good with jpost 0 as well; the rest reached and bad."""
    K, X, Y = 12, 12, 12
    shp = (K, X, Y, 3, 2, 3, 2)
    R = {4: np.zeros(shp, np.float32), 2: np.zeros(shp, np.float32)}
    R[4][1:10, 1:11, 1:11, 1, :, 1, 1] = 1.0
    R[4][2:10, 3:10, 3:10, 1, :, 1, 0] = 1.0
    return R, {"KP": K, "DX0": 0.0, "DY0": 0.0, "B": 0.25}


def test_v2_entries_are_certified_with_their_own_jump_after_the_press(monkeypatch):
    """specials_v2 (G4 took the best jump per cell for the cores and the slack): every entry's cells, and the late /
    space slack around them, hold with the entry's own jpost."""
    from ssbot.tools import specials_v2 as sv
    R, meta = _v2_scene()
    monkeypatch.setattr(sv, "robust_shares", lambda paths: (R, meta))
    ents, rep = sv.build([], thr=0.8, late=3, space_u=0.5, min_cells=1, kmax=11)
    assert ents
    for e in ents:
        xi = int(round(e.dx0 / 0.25))
        for yi in range(int(round(e.dy0 / 0.25)), int(round(e.dy1 / 0.25))):
            for dk in range(4):                         # the late slack: 3 frames
                for dx in (-2, 0, 2):
                    for dy in (-2, 0, 2):
                        assert R[4][e.k0 + dk, xi + dx, yi + dy, 1, 0, 1, e.jpost] >= 0.8 or \
                            R[4][e.k0 + dk, xi + dx, yi + dy, 1, 1, 1, e.jpost] >= 0.8
    assert {e.jpost for e in ents} == {0, 1}


def test_v2_lut_keeps_the_best_rank_in_a_shared_cell():
    """Two v2 entries of one key in one cell (another jpost / cert): the Lut keeps the better rank whatever the order
    (G4 kept the last written)."""
    def ent(cert, jp, share):
        return sp.Entry(id=f"e{cert}{jp}", type_key="Song Heavy Sentry", move="CL_SLAM", kind="down", k0=3, k1=3,
                        dx0=0.5, dx1=0.75, dy0=1.0, dy1=1.25, vy=1, key=0, jpost=jp, cert=cert, share=share)
    for es in ([ent("both", 0, 0.9), ent("bounce", 1, 0.95)], [ent("bounce", 1, 0.95), ent("both", 0, 0.9)]):
        lut = sp.Lut(es, True, cell=(0.25, 0.25))
        i = lut.find(np.array([3]), np.array([0.6]), np.array([1.1]), np.array([1]))[0]
        assert es[int(i)].cert == "both"


def test_hits_first_reuses_its_tier_escape_check(params, arena, monkeypatch):
    """HITS_FIRST (G4 4c) ran the escape check on its tier inside the envelope; the selection ran it again under the
    escape deadline, which the tier's time could exhaust before the first batch: the strike row was then flagged
    unsafe as "unchecked". The tier's result now stands for the first row in the order."""
    import dataclasses
    monkeypatch.setattr(special_mode, "HITS_FIRST", True)

    def setup(pl):
        pl.fcfg = dataclasses.replace(pl.fcfg, esc_deadline_ms=0.0)       # the selection's escape check: no time

    pl, r = _tick(params, arena, monkeypatch, setup=setup)
    assert pl.audit.hf_stop == 1
    assert not r.S
    assert pl.audit.hf_esc_reused == 1
    # the tier cache is its own attribute (a first version reused _esc_cache, _esc_cmds' escape commands)
    assert getattr(pl, "_hf_esc", None) is None
    assert pl._esc_cmds(24).ndim == 2


def test_hits_first_with_rows_past_the_tier_cache(params, arena, monkeypatch):
    """While the tier cache is handed to the selection's escape check, that check can still build its escape commands
    (_esc_cmds) for the rows past the cache: the smoke runs of gsav2 / allv2 crashed on a first version whose cache
    took _esc_cmds' own attribute."""
    monkeypatch.setattr(special_mode, "HITS_FIRST", True)
    orig = ForumPlanner._escape_pick
    n = [0]

    def pick(self, *a, **k):
        n[0] += 1
        assert self._esc_cmds(24).ndim == 2             # a row past the cache needs them
        return orig(self, *a, **k)

    monkeypatch.setattr(ForumPlanner, "_escape_pick", pick)
    pl, r = _tick(params, arena, monkeypatch)
    assert n[0] >= 1 and pl.audit.hf_esc_reused >= 1
