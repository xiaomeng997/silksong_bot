"""The Forum fast layer (forum_planner_plan §4.4 items 2 and 3, round R3): combat.forum_planner.ForumPlanner on the
synthetic Reed tables of test_multi_forecast, the Forum vocabulary, hit reactions, the Forum kill rule and the
supervisor's Forum settings."""
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ssbot.combat import candidates as cmod
from ssbot.combat.forum_planner import (EnvelopeAudit, ForumConfig, ForumPlanner, forum_kill_hp,
                                        forum_yellow_kill_hp, kill_freeze_s, posture_of)
from ssbot.combat.multi_forecast import MultiForecaster, hit_reactions
from ssbot.combat.planner import PlannerConfig
from ssbot.combat.safety_filter import FilterContext
from ssbot.combat.tactics.modes import HOLD, GoalPrefs
from ssbot.core.forum import FORUM_WAVES
from ssbot.core.primitives import N_PRIM
from ssbot.core.worldstate import E, ORACLE, WorldState
from ssbot.knowledge import kinematics as kin
from ssbot.safety.hits_to_death import SupportEvent
from ssbot.safety.supervisor import (POST_HIT_WINDOW_S, Q1_HIT, Supervisor, SupervisorConfig, SupervisorInput,
                                     WEIGHTED_POST_HIT_WINDOW_S, forum_supervisor_config)
from tests.test_multi_forecast import BIN, REED, _ent, _go, _run, _tables

FORUM_PARAMS = Path(__file__).resolve().parents[2] / "knowledge" / "1.0.30000" / "kinematics" / "hero_reaper_forum.json"
FLOOR = 3.0


@pytest.fixture(scope="module")
def params():
    return kin.HeroParams.load(FORUM_PARAMS)


@pytest.fixture(scope="module")
def arena():
    return kin.Terrain2D.from_boxes([(10.0, 0.0, 53.0, FLOOR), (10.0, 0.0, 14.01, 30.0), (48.99, 0.0, 53.0, 30.0)])


def _world(x: float, hp: int = 5) -> WorldState:
    ws = WorldState()
    ws.hero.pos = E((x, FLOOR + 1.04))
    ws.res.hp, ws.res.hp_max, ws.res.silk = E(hp), E(5), E(0)
    return ws


def _reed_forecaster(stab_at: int | None = 10, frames: int = 12, x: float = 30.0):
    """A Reed idling in Alert at x (flipX: facing +x), starting a stab at frame stab_at."""
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    script = []
    for f in range(frames):
        t = f * BIN
        evs = []
        st = "Alert" if stab_at is None or f < stab_at else "Stab Pos"
        if f == 0:
            evs.append(_go(7, "Alert", f, t))
        if stab_at is not None and f == stab_at:
            evs.append(_go(7, "Stab Pos", f, t))
        script.append((f, t, [_ent(7, x, FLOOR + 1.0, st, flip=True, box=(x - 0.5, FLOOR, x + 0.5, FLOOR + 2.0))],
                       evs))
    _run(mf, script)
    return mf


def _ctx(**kw):
    d = dict(allowed_mask=np.ones(N_PRIM, bool), hp=5, max_hp=5, silk=0, h=3, tier="GREEN", support_known=True)
    d.update(kw)
    return FilterContext(**d)


def _prefs(rng=None, x=27.0):
    if rng is None:
        return GoalPrefs(HOLD, x, {})
    w = {k: float(rng.uniform(0, 20)) for k in ("hit", "waste", "jump", "stance", "risk", "face", "ground", "cont")}
    rx = np.arange(14.0, 49.0, 0.5)
    return GoalPrefs("ENGAGE", float(rng.uniform(15, 48)), w, max_hits=int(rng.integers(0, 4)), risk_x=rx,
                     risk=rng.uniform(0, 1, len(rx)), boss_x=float(rng.uniform(15, 48)), hit_w={7: float(rng.uniform(0, 5))},
                     goal=str(rng.choice(["ENGAGE", "BAIT", "FOCUS"])), target=7)


# ---- the vocabulary ----

def test_forum_families_share_the_core_rows_and_drop_the_silk_skill():
    sets = {p: cmod.build_forum(36, p) for p in cmod.POSTURES}
    cores = [cs.cmd[core] for cs, core in sets.values()]
    assert all(c.shape == (56, 36) for c in cores)
    assert all(np.array_equal(cores[0], c) for c in cores[1:])
    for p, (cs, core) in sets.items():
        assert len(cs.cmd) <= 441
        assert not ((cs.cmd & kin.B_QUICKCAST) != 0).any()
        assert ((cs.cmd[core] & kin.B_ATTACK) == 0).all()          # the evasion set has no attack (no hit branch)
    assert any(n.startswith("ATTACK(down)") for n in sets["air"][0].first_names)
    assert not any(n.startswith("ATTACK(down)") for n in sets["ground"][0].first_names)


def test_timing_rows_follow_the_rows_as_they_were():
    """waits (SSBOT_FORUM_WAITS): the old rows keep their indices; WAIT then a jump / dash after 3-12 frames; an attack
    first piece then one press at the Reed's / Minister's counter; ground with the clash rows stays within 512."""
    for p in cmod.POSTURES:
        a, core_a = cmod.build_forum(36, p, clash=True)
        b, core_b = cmod.build_forum(36, p, clash=True, waits=True)
        n = len(a.cmd)
        assert np.array_equal(b.cmd[:n], a.cmd) and np.array_equal(core_b[:n], core_a) and not core_b[n:].any()
        assert len(b.cmd) - n == 16 + 4 * sum(f in cmod.TIMED_FIRSTS for f in b.first_names)
    b, _ = cmod.build_forum(36, "ground", clash=True, waits=True)
    assert len(b.cmd) <= 512
    names = [b.name(i) for i in range(len(b.cmd))]
    row = b.cmd[names.index("WAIT+wait6_dashL")]
    assert not row[:cmod.FIRST + 6].any() and (row[cmod.FIRST + 6:cmod.FIRST + 9] & kin.B_DASH).all()
    row = b.cmd[names.index("WAIT+wait12_jumpR")]
    assert (row[cmod.FIRST + 12:] & kin.B_JUMP).all() and not (row[:cmod.FIRST + 12] & kin.B_JUMP).any()
    row = b.cmd[names.index("ATTACK(up)L+clashat_ministerU")]
    k = cmod.FIRST + cmod.TIMED_PRESS["minister"]
    presses = np.flatnonzero((row[cmod.FIRST:] & kin.B_ATTACK) != 0) + cmod.FIRST
    assert list(presses) == [k, k + 1] and (row[k] & kin.B_UP)


def test_posture_of_the_start_state(params):
    s = kin.initial_state(params, 30.0, FLOOR + params.foot)
    assert posture_of(s) == "ground"
    s[kin.GROUND] = 0.0
    assert posture_of(s) == "air"
    s[kin.WSIDE] = -1.0
    assert posture_of(s) == "wall"


# ---- §4.4 item 2: the core rows' S / Hz / U do not depend on the goal ----

@pytest.mark.parametrize("hero_x,stab_at", [(27.0, 10), (31.5, 10), (24.0, None), (30.2, 10)])
def test_core_rows_s_hz_u_are_the_same_under_any_goal(params, arena, hero_x, stab_at):
    mf = _reed_forecaster(stab_at)
    f = mf.forecast(0.8)
    start = kin.initial_state(params, hero_x, FLOOR + params.foot)
    ws = _world(hero_x)
    rng = np.random.default_rng(int(hero_x * 10))
    ref = None
    forced_default = None
    for k in range(8):
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=0.0 if k % 2 else 50.0))
        prefs = _prefs(None if k == 0 else rng, hero_x)
        r = pl.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, prefs, _ctx(kill_hp=5.0))
        li = pl.last_info
        core = li["core_mask"]
        got = (li["S"][core].copy(), li["Hz"][core].copy(), li["U"][core].copy())
        # every core row past stage 1 was enveloped, whatever the deadline
        assert pl.audit.core_not_enveloped == 0
        if ref is None:
            ref, forced_default = got, r.forced_risk
        else:
            for a, b in zip(ref, got):
                assert np.array_equal(a, b)
            # a goal never makes FORCED_RISK where the default goal is not (§4.4 item 2)
            assert not r.forced_risk or forced_default


@pytest.mark.parametrize("hero_x,stab_at", [(27.0, 10), (30.2, 10), (28.5, 8)])
def test_forced_risk_does_not_depend_on_the_caps_order(params, arena, hero_x, stab_at):
    """The hit-branch caps are handed out in queue order (J: the prefs); with hitfx_k = 1 and react_k = 0 they bind on
    every tick, and still a goal's FORCED_RISK implies the default goal's (the capped rows get their hit branch
    uncapped before FORCED_RISK), and the safe set without a cap is the same under every goal."""
    mf = _reed_forecaster(stab_at)
    f = mf.forecast(0.8)
    start = kin.initial_state(params, hero_x, FLOOR + params.foot)
    ws = _world(hero_x)
    rng = np.random.default_rng(int(hero_x * 10) + 1)
    forced_default = None
    for k in range(6):
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, hitfx_k=1, react_k=0, chunk=16))
        r = pl.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None if k == 0 else rng,
                                                                                         hero_x), _ctx(kill_hp=5.0))
        if k == 0:
            forced_default = r.forced_risk
        else:
            assert not r.forced_risk or forced_default


def test_note_hit_puts_the_hit_branch_into_the_forced_ranking():
    """A row safe on its miss branch whose hit branch meets the support (or whose reaction a cap left unchecked) is
    not contact-free for FORCED_RISK's ranking: t_hit drops to the branch's first contact (to the hit frame for a
    capped one) and its contact frames are kept for the share."""
    T1 = 12
    rows = np.array([3, 5, 8])
    sh = np.array([True, False, True])
    oh = np.zeros((3, T1), bool)
    oh[0, 6:9] = True
    cp = np.array([False, False, True])
    sc = {"first_f": np.array([0, 0, 0, 2, 0, 4, 0, 0, 7, 0])}
    t_hit = np.full(10, T1, np.int64)
    hit_occ, capped = {5: np.ones(T1, bool)}, []
    ForumPlanner._note_hit(rows, sh, oh, cp, sc, t_hit, hit_occ, capped, T1)
    assert t_hit[3] == 6 and hit_occ[3][6:9].all() and hit_occ[3].sum() == 3
    assert 5 not in hit_occ and t_hit[5] == T1                     # its hit branch is clear: nothing to add
    assert t_hit[8] == 7 and hit_occ[8][7:].all() and not hit_occ[8][:7].any() and capped == [8]


def test_forced_ranking_never_takes_a_row_in_contact_for_contact_free(params, arena):
    """FORCED_RISK ranks its candidates on one lane over every frame: a candidate in contact at stage 1, or whose hit
    branch meets the support, has a share in contact above 0 and a first contact no later than its estimate's."""
    rng = np.random.default_rng(11)
    forced = 0
    for x in (30.6, 31.0, 31.6, 32.0):
        mf = _reed_forecaster(10, frames=17)
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, chunk=16))
        r = pl.tick(_world(x), kin.initial_state(params, x, FLOOR + params.foot), kin.HoldState.idle(1),
                    np.zeros(1, np.int64), mf.forecast(0.8), _prefs(rng, x), _ctx())
        li = pl.last_info
        if not r.forced_risk:
            continue
        forced += 1
        for i in np.flatnonzero(li["cand"]):
            if not li["env"][i] or int(i) in li["hit_occ"]:
                assert li["Pc"][i] > 0
            h = li["hit_occ"].get(int(i))
            if h is not None:
                assert li["t_c"][i] <= int(np.argmax(h))
    assert forced > 0


def test_commit_rank_refines_forced_risk_by_the_committed_support(params, arena):
    """commit_rank (SSBOT_FORUM_PC, forum.md 20.7): S / Hz / U and FORCED_RISK are the same with and without it; in
    a FORCED_RISK tick no candidate tied with the chosen row on every key before (P_cm, P_f) is lower on them; off,
    P_cm and P_f are 0 everywhere."""
    from ssbot.knowledge.kinematics import F_INVULN
    seen_pf = False
    for x in (30.6, 31.0, 31.6, 32.0):
        got = {}
        for on in (False, True):
            mf = _reed_forecaster(10, frames=17)
            f = mf.forecast(0.8)
            pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                              ForumConfig(deadline_ms=math.inf, chunk=16, commit_rank=on))
            r = pl.tick(_world(x), kin.initial_state(params, x, FLOOR + params.foot), kin.HoldState.idle(1),
                        np.zeros(1, np.int64), f, _prefs(None, x), _ctx())
            li = pl.last_info
            got[on] = (r, {k: li[k].copy() for k in ("S", "Hz", "U")}, np.stack([li["Pcm"], li["Pf"]], axis=1),
                       li["cand"].copy(), pl.last_sel, f)
        (r0, k0, pf0, _, _, _), (r1, k1, pf1, cand, ls, f) = got[False], got[True]
        assert r0.forced_risk == r1.forced_risk
        for k in k0:
            assert np.array_equal(k0[k], k1[k])
        assert not pf0.any()
        if not r1.forced_risk:
            continue
        seen_pf |= bool(pf1[cand].any())
        # the keys from stage 1's split query are the second queries' (the pre-17.11 computation) on every candidate
        al = np.flatnonzero(ls["allowed"])
        fr = ForumPlanner._s1_frames(ls["T1"])
        b = ls["box"][al][:, fr]
        X, Y = 0.5 * (b[..., 0] + b[..., 2]), 0.5 * (b[..., 1] + b[..., 3])
        live = (ls["flags"][al][:, fr] & F_INVULN) == 0
        assert np.array_equal(pf1[al, 0], (f._union_occ(X, Y, ls["tk"][fr], committed_only=True) & live).mean(1))
        assert np.array_equal(pf1[al, 1], (f._fine_occ(X, Y, ls["tk"][fr]) & live).mean(1))
        i = r1.idx
        pre = lambda j: (ls["hz"][j], ls["hz_soft"][j], ls["U"][j], ls["S"][j], ls["keep"][j], ls["mkeep"][j],
                         ls["V"][j], ls["Pc"][j])
        for j in np.flatnonzero(cand):
            if pre(j) == pre(i):
                assert tuple(pf1[j]) >= tuple(pf1[i])
    assert seen_pf


# ---- FORCED_RISK's "seen" key (forum.md §19; ported from the wave-0 forensics track's 3608489) ----

def _with_collider(ws: WorldState, box: tuple, vx: float) -> WorldState:
    from ssbot.core.worldstate import DamageBox, Entity
    x0, y0, x1, y1 = box
    ws.entities = [Entity(id=99, vel=E((vx, 0.0)),
                          dmg_boxes=[DamageBox(poly=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], active=True)])]
    return ws


def test_seen_contacts_counts_frames_against_the_moving_collider():
    from ssbot.combat.forum_planner import seen_contacts
    T1 = 11
    tk = np.arange(T1) * 0.1
    box = np.zeros((2, T1, 4))
    box[0] = (10.0, 0.0, 10.5, 2.0)             # stands still at x 10
    box[1] = (0.0, 0.0, 0.5, 2.0)               # stands far away
    inv = np.zeros((2, T1), np.bool_)
    verts = np.array([[14.0, 0.0], [15.0, 0.0], [15.0, 2.0], [14.0, 2.0]])
    pbox = np.array([[14.0, 0.0, 15.0, 2.0]])
    cnt, first = seen_contacts(box, inv, verts, np.array([0, 4], np.int64), pbox, np.array([[-10.0, 0.0]]), tk,
                               np.arange(2, dtype=np.int64), 0.0)
    # its left edge reaches x 10.5 at 0.35 s, its right edge leaves x 10 at 0.5 s: frames 4 and 5
    assert first[0] == 4 and cnt[0] == 2 and first[1] == T1 and cnt[1] == 0
    inv[0, :5] = True                           # invulnerable frames are clear
    cnt, first = seen_contacts(box, inv, verts, np.array([0, 4], np.int64), pbox, np.array([[-10.0, 0.0]]), tk,
                               np.arange(2, dtype=np.int64), 0.0)
    assert first[0] == 5 and cnt[0] == 1


def test_seen_rank_without_seen_colliders_is_the_share_ranking(params, arena):
    """No damage collider seen: the "seen" key ties on every row and the choice is the share ranking's (with and
    without commit_rank stacked on it)."""
    for pc in (False, True):
        for x in (30.6, 31.0, 31.6, 32.0):
            picks = []
            for fr in ("share", "seen"):
                mf = _reed_forecaster(10, frames=17)
                pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                                  ForumConfig(deadline_ms=math.inf, chunk=16, forced_rank=fr, commit_rank=pc))
                r = pl.tick(_world(x), kin.initial_state(params, x, FLOOR + params.foot), kin.HoldState.idle(1),
                            np.zeros(1, np.int64), mf.forecast(0.8), _prefs(np.random.default_rng(int(x * 10)), x),
                            _ctx())
                picks.append((r.idx, r.S, r.forced_risk))
            assert picks[0] == picks[1]


def test_seen_rank_takes_the_row_clear_of_a_collider_coming_at_the_hero(params, arena):
    """FORCED_RISK with a damage box charging at the hero from the right: "seen" picks a row whose nominal path the
    moving box meets least (none when one exists), also with commit_rank stacked after it; safe ticks unchanged."""
    from ssbot.combat.forum_planner import seen_contacts, seen_polys
    n_forced = 0
    for pc in (False, True):
        for x in (30.6, 31.0, 31.6):
            ws = _with_collider(_world(x), (x + 4.0, FLOOR, x + 5.5, FLOOR + 2.0), -18.0)
            mf = _reed_forecaster(10, frames=17)
            pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                              ForumConfig(deadline_ms=math.inf, chunk=16, forced_rank="seen", commit_rank=pc))
            r = pl.tick(ws, kin.initial_state(params, x, FLOOR + params.foot), kin.HoldState.idle(1),
                        np.zeros(1, np.int64), mf.forecast(0.8), _prefs(), _ctx())
            if not r.forced_risk:
                continue
            n_forced += 1
            ls = pl.last_sel
            verts, starts, pbox, pvel = seen_polys(ws)
            rows = np.flatnonzero(ls["allowed"])
            cnt, _ = seen_contacts(np.ascontiguousarray(ls["box"], np.float64),
                                   np.ascontiguousarray((ls["flags"] & kin.F_INVULN) != 0), verts, starts, pbox, pvel,
                                   np.ascontiguousarray(ls["tk"], np.float64), rows, 0.0)
            assert cnt[rows].max() > 0                     # standing still is met
            assert pl.last_info["seen"] == cnt[rows].min() == cnt[r.idx]
    assert n_forced > 0


# ---- §4.4 item 3: the chosen plan is always enveloped ----

def test_the_chosen_safe_plan_was_always_enveloped(params, arena):
    rng = np.random.default_rng(5)
    for deadline in (0.0, 2.0, 50.0):
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=deadline, chunk=16))
        for x in np.linspace(22.0, 34.0, 13):
            mf = _reed_forecaster(int(rng.integers(5, 12)))
            r = pl.tick(_world(float(x)), kin.initial_state(params, float(x), FLOOR + params.foot),
                        kin.HoldState.idle(1), np.zeros(1, np.int64), mf.forecast(0.8), _prefs(rng, float(x)),
                        _ctx())
            if r.S == 0:
                assert pl.last_info["env"][r.idx]
        a = pl.audit
        assert a.ticks == 13 and a.chosen_safe > 0
        assert a.chosen_safe == a.chosen_safe_enveloped and a.core_not_enveloped == 0
        assert a.chosen_safe + a.forced == a.ticks


def test_inside_the_stab_every_way_out_is_checked_before_forced_risk(params, arena):
    """Hero in front of a committed stab: FORCED_RISK only once every row past stage 1 was enveloped."""
    mf = _reed_forecaster(10, frames=17)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=0.0, chunk=8))
    r = pl.tick(_world(31.6), kin.initial_state(params, 31.6, FLOOR + params.foot), kin.HoldState.idle(1),
                np.zeros(1, np.int64), mf.forecast(0.8), _prefs(), _ctx())
    li = pl.last_info
    if r.forced_risk:
        assert li["enveloped"] == li["stage1_pass"]
    else:
        assert li["env"][r.idx] and r.S == 0


# ---- FORCED_RISK's "seen" key (forum.md §19; the wave-0 forensics track's copies of _with_collider and the seen
# tests above were merged here twice, the R5 value port's stacked versions kept) ----

def test_the_policy_reads_the_forced_rank_switch(monkeypatch):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    monkeypatch.delenv("SSBOT_FORUM_FR", raising=False)
    assert ForumPlannerPolicy._fcfg().forced_rank == "share" == ForumConfig().forced_rank
    monkeypatch.setenv("SSBOT_FORUM_FR", "seen")
    assert ForumPlannerPolicy._fcfg().forced_rank == "seen"
    monkeypatch.setenv("SSBOT_FORUM_FR", "seen_cf")
    assert ForumPlannerPolicy._fcfg().forced_rank == "seen_cf"
    monkeypatch.setenv("SSBOT_FORUM_FR", "bogus")
    with pytest.raises(ValueError):
        ForumPlannerPolicy._fcfg()


def test_seen_cf_then_takes_the_row_least_in_the_committed_strike(params, arena):
    """"seen_cf": no damage collider seen (the stab not out yet), the committed stab's fine placements decide: the pick
    has the least share of stage 1's frames in them among the known rows."""
    from ssbot.combat.forum_planner import committed_fine_share
    n_checked = 0
    for x in (30.6, 31.0, 31.6, 32.0):
        mf = _reed_forecaster(10, frames=12)
        f = mf.forecast(0.8)
        if not np.asarray(f.pm["committed"], bool).any():
            continue
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, chunk=16, forced_rank="seen_cf"))
        pl.debug = True
        r = pl.tick(_world(x), kin.initial_state(params, x, FLOOR + params.foot), kin.HoldState.idle(1),
                    np.zeros(1, np.int64), f, _prefs(), _ctx())
        if not r.forced_risk:
            continue
        dbg = pl.last_info["dbg"]
        rows = np.flatnonzero(dbg["ok"] & dbg["known"])
        cf = committed_fine_share(f, dbg["box"], (dbg["flags"] & kin.F_INVULN) != 0, rows, dbg["fr"], dbg["tk"])
        assert cf.max() > cf.min()                       # the strike separates the rows
        assert pl.last_info["seen_cf"] == round(float(cf.min()), 3)
        n_checked += 1
    assert n_checked > 0


# ---- hit reactions ----

def test_a_hit_reed_in_alert_stabs_at_once():
    """hero_caused.json: a Reed hit in Alert goes to Stab Pos at once; the plain forecast has the stab only after
    Alert's least dwell (0.2 s in the synthetic table)."""
    assert hit_reactions()[REED]["Alert"] == "Stab Pos"
    mf = _reed_forecaster(None, frames=3)
    assert mf.reaction_state(7) == "Stab Pos"
    f = mf.forecast(0.8)
    T = mf.t
    rf = mf.forecast_reaction(7, "Stab Pos", T + 0.05, 0.8, T)
    tk = np.arange(0, 16) * BIN                        # the first 0.25 s
    X, Y = np.full((1, 16), 32.0), np.full((1, 16), FLOOR + 1.0)
    # past the collider tube's 5 bins: only the reaction's stab reaches the blade's place
    assert not f.occupied(X, Y, tk)[0][6:13].any()
    assert rf.occupied(X, Y, tk)[0][6:13].any()
    assert mf.trackers[7].state == "Alert"             # the real state is untouched


@pytest.mark.parametrize("stab_at", [None, 10])
def test_occupied_is_the_union_of_its_parts(stab_at):
    """The support query's boxes of every kind in one call (R3 fix) answer exactly what the parts do."""
    mf = _reed_forecaster(stab_at, frames=12)
    f = mf.forecast(0.8)
    tk = np.arange(0, 40) * BIN
    xs = np.linspace(24.0, 36.0, 49)
    X = np.repeat(xs[:, None], len(tk), axis=1)
    for y in (FLOOR + 0.5, FLOOR + 1.5, FLOOR + 3.5):
        Y = np.full_like(X, y)
        parts = f.occupied_parts(X, Y, tk)
        union = np.logical_or.reduce(list(parts.values()))
        assert np.array_equal(f.occupied(X, Y, tk), union)
        assert union.any()


def test_reactions_come_from_every_state_the_walk_allows_at_the_hit():
    """A Reed in Stab Pos now (its TOOK DAMAGE exit: Stab Antic) is back in Alert (exit: Stab Pos) by a hit 0.8 s on,
    not by one 2 frames on; the reaction forecast holds all of them, anchored at the hit time."""
    mf = _reed_forecaster(10, frames=12)
    T = mf.t
    assert mf.trackers[7].state == "Stab Pos"
    ex = hit_reactions()[REED]
    soon = mf.reaction_states(7, T + 2 * BIN, 0.8)
    late = mf.reaction_states(7, T + 0.8, 0.8)
    assert soon == [ex["Stab Pos"]]
    assert set(late) >= {ex["Stab Pos"], ex["Alert"]}
    rf = mf.forecast_reaction(7, late, T + 0.8, 1.2, T)
    assert rf is not None and mf.trackers[7].state == "Stab Pos"
    # a reaction entering the stab again at 0.8 s: its blade is placed from then (both mirrors) at the anchor box
    tk = np.arange(0, 80) * BIN
    X, Y = np.full((1, 80), 30.0 + 2.0), np.full((1, 80), FLOOR + 1.0)
    Xl = np.full((1, 80), 30.0 - 2.0)
    late_occ = rf.occupied(X, Y, tk)[0] | rf.occupied(Xl, Y, tk)[0]
    assert late_occ[49:].any()


# ---- the Forum kill rules ----

def _tr(tk, hp, sd=0.0, in_play=True, dead=False):
    return SimpleNamespace(tk=tk, hp_est=hp, hp_sd=sd, in_play=in_play, dead=dead)


def test_the_unpausable_blow_is_the_one_that_may_end_the_battle():
    last = len(FORUM_WAVES) - 1
    clap = "Song Heavy Sentry"
    mf = SimpleNamespace(waves=SimpleNamespace(done=False, wave=last - 1, queued=None),
                         trackers={1: _tr(clap, 5.0)})
    assert forum_kill_hp(mf) is None                   # another wave to come: an ordinary kill
    mf.waves.wave = last
    mf.trackers = {1: _tr(clap, 40.0, 1.0), 2: _tr(clap, 9.0, 1.0)}
    assert forum_kill_hp(mf) == pytest.approx(37.0)    # one blow ends it only if both die
    mf.trackers[1].dead = True
    assert forum_kill_hp(mf) == pytest.approx(6.0)
    freeze = kill_freeze_s()
    assert set(freeze) >= {clap, REED}
    # only the kill's own freeze counts (the Clapper's death slow motion); the hero's NailClashEffect / StartRecoil that
    # started on a kill frame of the wave-0 types are not theirs (forum.md 12.3)
    assert freeze[clap] > 1.0
    assert freeze[REED] == 0.0 and freeze["Song Pilgrim 01"] == 0.0 and freeze["Song Pilgrim 03"] == 0.0
    assert kill_freeze_s(any_kind=True)[REED] > 0.3          # SSBOT_FORUM_KF=any: the rule before
    mf2 = SimpleNamespace(trackers={1: _tr(REED, 20.0, 2.0), 2: _tr(clap, 8.0)})
    assert forum_yellow_kill_hp(mf2, {REED: 0.25, clap: 0.0}) == pytest.approx(14.0)
    assert forum_yellow_kill_hp(mf2, {REED: 0.0, clap: 0.0}) is None


# ---- the supervisor's Forum settings ----

def test_q4_counts_unpredicted_hits_per_enemy_instance():
    sup = Supervisor(forum_supervisor_config())
    ev = (SupportEvent(REED, 1, instance=7),)
    base = dict(hp=5, max_hp=5, support=ev, support_known=True, plan_s=0)
    d = sup.step(SupervisorInput(t=0.0, unpredicted_hits=1, unpredicted_sources=(7,), **base))
    d = sup.step(SupervisorInput(t=1.0, unpredicted_hits=1, unpredicted_sources=(8,), **base))
    assert "Q4" not in d.triggers                      # two instances, one each
    d = sup.step(SupervisorInput(t=2.0, unpredicted_hits=1, unpredicted_sources=(7,), **base))
    assert "Q4" in d.triggers                          # instance 7 twice
    sup2 = Supervisor(forum_supervisor_config())
    for i, src in enumerate((1, 2, 3)):
        d = sup2.step(SupervisorInput(t=float(i), unpredicted_hits=1, unpredicted_sources=(src,), **base))
    assert "Q4" in d.triggers                          # the attempt-wide total (3)
    old = Supervisor(SupervisorConfig(worst_known_damage=2))
    old.step(SupervisorInput(t=0.0, unpredicted_hits=1, **base))
    assert "Q4" in old.step(SupervisorInput(t=1.0, unpredicted_hits=1, **base)).triggers   # Bell Beast unchanged


def test_yellow_withholds_a_freezing_kill_even_when_known_at_h2():
    """forum_planner_plan §4.4 item 7 (R4 fixer round): the Forum cannot certify a kill (no kill branches, and the L0
    filter's kill_hp is only the battle's last blow), so YELLOW withholds kill_prims with a certified support at h = 2
    too; Bell Beast's config keeps them for the L0 filter's certification."""
    from ssbot.combat.hero_damage import HeroDamage
    from ssbot.core.primitives import Prim
    dmg = HeroDamage.from_loadout("Reaper", 0)
    kp = dmg.kill_prims(5.0)                           # an Envoy at hp_est 5 (forum_yellow_kill_hp)
    assert Prim.ATTACK_SIDE in kp
    base = dict(t=10.0, hp=3, max_hp=5, support=(SupportEvent(REED, 2, instance=7),), support_known=True, plan_s=0,
                pausable=True, idle_clear_s=1.0, kill_prims=kp, next_hit_may_kill=True)
    d = Supervisor(forum_supervisor_config()).step(SupervisorInput(**base))
    assert d.tier == "YELLOW" and d.h == 2 and d.support_known
    assert not d.allows("ATTACK(side)") and not d.allows("ATTACK(up)") and not d.allowed & kp
    assert d.allows("DASH") and d.kill_rule
    bb = Supervisor(SupervisorConfig(worst_known_damage=2)).step(SupervisorInput(**base))
    assert bb.allows("ATTACK(side)")                   # Bell Beast unchanged: left to kill_certified
    d0 = Supervisor(forum_supervisor_config()).step(SupervisorInput(**{**base, "hp": 5}))
    assert d0.tier == "GREEN" and d0.allows("ATTACK(side)")   # GREEN: the L0 filter's (I3 / forum_kill_hp)


def test_the_weighted_anklet_widens_the_post_hit_window():
    assert forum_supervisor_config(weighted=True).post_hit_window_s == WEIGHTED_POST_HIT_WINDOW_S == 1.3
    assert forum_supervisor_config().post_hit_window_s == POST_HIT_WINDOW_S
    for cfg, q1 in ((forum_supervisor_config(weighted=True), Q1_HIT), (forum_supervisor_config(), "no_hit")):
        sup = Supervisor(cfg)
        sup.t_hit = 0.0
        assert (sup.q1_cause(1.2) == Q1_HIT) == (q1 == Q1_HIT)


def test_envelope_audit_is_a_plain_record():
    a = EnvelopeAudit()
    assert a.as_dict()["chosen_safe"] == 0


# ---- the Reaper's shapes (M2.md: the side slash reaches the front-up, the up slash only above and behind) ----

def test_reaper_side_slash_reaches_front_up_and_up_slash_overhead(params, arena):
    from ssbot.combat.holdfilter import hold_filter_jit
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=1, variants="bounds_lo"))
    cs, _ = cmod.build_forum(36, "ground")
    names = [cs.name(i) for i in range(len(cs.cmd))]
    rows = [names.index("ATTACK(side)R+idle"), names.index("ATTACK(up)R+idle")]
    x0 = 30.0
    start = kin.initial_state(params, x0, FLOOR + params.foot, facing=1)
    full = np.concatenate([np.zeros((2, 1), np.int64), cs.cmd[rows]], axis=1)
    latched, _ = hold_filter_jit(full, kin.HoldState.idle(2))
    roll = kin.rollout(start, latched, params, arena)
    tk = np.arange(roll.box.shape[1]) * params.frame_time
    b = roll.box[0, 0]
    cx, cy = 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])

    def fc(box):
        return SimpleNamespace(targets=lambda t: [SimpleNamespace(iid=1, type_key=REED, hazard=False,
                                                                 box=np.tile(np.array(box), (len(t), 1)),
                                                                 ok=np.ones(len(t), bool))])

    front_up = (cx + 1.8, cy + 1.6, cx + 2.4, cy + 2.2)
    overhead = (cx - 0.9, cy + 2.8, cx - 0.3, cy + 3.4)
    sc = pl._score_forum(_world(x0), roll, latched, start, fc(front_up), _prefs(), tk)
    assert sc["hits"][0] > 0 and sc["hits"][1] == 0 and sc["first_k"][0] == 1
    sc = pl._score_forum(_world(x0), roll, latched, start, fc(overhead), _prefs(), tk)
    assert sc["hits"][1] > 0 and sc["hits"][0] == 0 and sc["first_k"][1] == 2
