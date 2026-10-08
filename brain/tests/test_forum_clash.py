"""Forum plan R8 (clash): the Wanderer crest's kinematics (AB_DOWN_SLASH), the parry-recover event, the clash table
and its builder, the swing finder the EV_CLASH branch uses."""
from pathlib import Path

import numpy as np
import pytest

from ssbot.combat.forum_planner import K_DOWN, K_SIDE, K_UP, PARRY_STOP_GROW, PARRY_STOPS, ClashTable, stop_grow, swings
from ssbot.knowledge import kinematics as kin
from ssbot.tools.forum_clash_stats import build_table, slot_of, wilson_ub

KDIR = Path(__file__).resolve().parents[2] / "knowledge" / "1.0.30000" / "kinematics"
FLOOR = 3.0


@pytest.fixture(scope="module")
def arena():
    return kin.Terrain2D.from_boxes([(10.0, 0.0, 53.0, FLOOR), (10.0, 0.0, 14.01, 30.0), (48.99, 0.0, 53.0, 30.0)])


@pytest.fixture(scope="module")
def wanderer():
    return kin.HeroParams.load(KDIR / "hero_wanderer_forum.json")


@pytest.fixture(scope="module")
def reaper():
    return kin.HeroParams.load(KDIR / "hero_reaper_forum.json")


def _onsets(flags: np.ndarray) -> list[int]:
    a = (flags & kin.F_ATTACKING) != 0
    return [int(k) for k in range(1, len(a)) if a[k] and not a[k - 1]]


def test_wanderer_params(wanderer, reaper):
    assert wanderer.crest == "Wanderer"
    assert (wanderer.attack_duration, wanderer.attack_cooldown, wanderer.attack_recovery) == (0.25, 0.3, 0.1)
    assert wanderer.abilities & kin.AB_DOWN_SLASH and not wanderer.abilities & kin.AB_RPR_DOWN
    assert not reaper.abilities & kin.AB_DOWN_SLASH
    # every other Forum loadout bit is the Reaper's
    assert wanderer.abilities & ~(kin.AB_DOWN_SLASH | kin.AB_RPR_DOWN) == reaper.abilities & ~kin.AB_RPR_DOWN


def test_down_attack_is_a_slash_for_wanderer(wanderer, reaper, arena):
    m = np.zeros((1, 30), np.int64)
    m[0, :8] = kin.B_JUMP
    m[0, 10:13] = kin.B_ATTACK | kin.B_DOWN
    for p, slash in ((wanderer, True), (reaper, False)):
        S = kin.initial_state(p, 30.0, FLOOR + p.foot)
        r = kin.rollout(S, m, p, arena)
        modes = set(int(x) for x in r.mode[0])
        if slash:
            assert _onsets(r.flags[0]), "the Wanderer down attack swings (cState.attacking)"
            assert kin.M_RPR_DS not in modes and kin.M_DS_ANTIC not in modes
        else:
            assert kin.M_RPR_DS in modes


def test_parry_recover_lets_the_next_swing_out(wanderer, arena):
    S = kin.initial_state(wanderer, 30.0, FLOOR + wanderer.foot)
    m = np.zeros((1, 40), np.int64)
    m[0, 0:2] = kin.B_ATTACK
    m[0, 12:14] = kin.B_ATTACK            # 0.2 s later: inside the 0.3 s cooldown
    ev = np.zeros((1, 40), np.int64)
    plain = _onsets(kin.rollout(S, m, wanderer, arena).flags[0])
    ev[0, 2 + 6] = kin.EV_PARRY_RECOVER   # a clash on the swing's first frames, recovered 0.1 s later
    parried = _onsets(kin.rollout(S, m, wanderer, arena, events=ev).flags[0])
    assert len(plain) >= 1 and len(parried) >= 2
    assert parried[0] == plain[0]
    # the second press is taken at once after the recover (without it: queued until the cooldown ends)
    assert parried[1] < (plain[1] if len(plain) > 1 else 99)
    assert parried[1] <= 15


def test_unused_bits_leave_reaper_rollouts_alone(reaper, arena):
    rng = np.random.default_rng(3)
    S = kin.initial_state(reaper, 30.0, FLOOR + reaper.foot)
    bits = (kin.B_ATTACK, kin.B_JUMP, kin.B_LEFT, kin.B_RIGHT, kin.B_UP, kin.B_DOWN, kin.B_DASH)
    m = np.zeros((16, 36), np.int64)
    for i in range(16):
        for k in range(0, 36, 4):
            m[i, k:k + 4] = sum(b for b in bits if rng.random() < 0.3)
    a = kin.rollout(S, m, reaper, arena, variants="bounds_lo")
    # a parry-recover event where nothing attacks changes nothing
    ev = np.zeros_like(m)
    ev[:, 0] = kin.EV_PARRY_RECOVER
    S2 = kin.initial_state(reaper, 30.0, FLOOR + reaper.foot)
    m2 = m.copy()
    m2[:, :12] &= ~kin.B_ATTACK
    b0 = kin.rollout(S2, m2, reaper, arena, variants="bounds_lo")
    b1 = kin.rollout(S2, m2, reaper, arena, variants="bounds_lo", events=ev)
    assert np.array_equal(b0.bound, b1.bound)
    assert a.bound.shape == b0.bound.shape


def test_swings_kinds(wanderer, arena):
    S = kin.initial_state(wanderer, 30.0, FLOOR + wanderer.foot)
    m = np.zeros((1, 60), np.int64)
    m[0, 0:2] = kin.B_ATTACK | kin.B_RIGHT
    m[0, 20:22] = kin.B_ATTACK | kin.B_UP
    m[0, 30:40] = kin.B_JUMP
    m[0, 44:46] = kin.B_ATTACK | kin.B_DOWN
    lat, _ = __import__("ssbot.combat.holdfilter", fromlist=["hold_filter_jit"]).hold_filter_jit(
        m, kin.HoldState.idle(1))
    r = kin.rollout(S, lat, wanderer, arena)
    sw = swings(r.flags[0], r.mode[0], lat[0], r.box[0], 1, True)
    kinds = [k for _, k, _ in sw]
    assert kinds[:3] == [K_SIDE, K_UP, K_DOWN], sw


def test_clash_table_and_builder(tmp_path):
    rows = []
    for out, n in (("clash", 30), ("hit", 1), ("neither", 9)):
        rows.append({"crest": "Wanderer", "type": "Song Pilgrim 01", "family": "EN_SLASH", "slot": "normal",
                     "side": "front", "clashable_collider_on": True, "n": n, out: n})
    rows.append({"crest": "Reaper", "type": "Song Pilgrim 01", "family": "EN_SLASH", "slot": "normal",
                 "side": "behind", "clashable_collider_on": True, "n": 50, "hit": 50})
    rows.append({"crest": "Reaper", "type": "Song Heavy Sentry", "family": "CC_SLAM", "slot": "normal",
                 "side": "front", "clashable_collider_on": False, "n": 50, "neither": 50})
    rows.append({"crest": "Reaper", "type": "Song Reed", "family": "RE_IDLE", "slot": "up",
                 "side": "front", "clashable_collider_on": False, "n": 50, "clash": 50})
    tab = build_table([{"union_setups": rows}], min_n=10)
    k = "Song Pilgrim 01|EN_SLASH|side"
    assert tab["p_fail"][k]["n"] == 40 and tab["p_fail"][k]["hit"] == 1      # the behind rows are left out
    assert tab["p_fail"][k]["p_fail"] == round(wilson_ub(1, 40), 4)
    assert "Song Heavy Sentry|CC_SLAM|side" in tab["left_out"]
    assert "Song Reed|RE_IDLE|up" in tab["left_out"]
    p = tmp_path / "clash.json"
    import json
    p.write_text(json.dumps(tab), encoding="utf-8")
    ct = ClashTable.load(p)
    assert ct.p_fail("Song Pilgrim 01", "EN_SLASH", "side") == pytest.approx(wilson_ub(1, 40), abs=1e-4)
    assert ct.p_fail("Song Pilgrim 01", None, "side") is None
    assert ct.p_fail("Song Heavy Sentry", "CC_SLAM", "side") is None
    assert slot_of("UpSlash", False) == "up" and slot_of("DownSlashAlt", False) == "down"
    assert slot_of("SlashAlt", False) == "normal" and slot_of("Slash", True) == "wall"


def test_parry_stop_growth_is_the_next_measured_step():
    gx, gy = stop_grow("Song Pilgrim 01", np.array([0, 2, 3, 5, 6, 30, 47]))
    assert gx.tolist() == [0.372, 0.372, 0.6, 0.6, 0.701, 0.932, 0.932]
    assert gy.tolist() == [0.01] * 7
    gx, gy = stop_grow("Song Reed", np.array([0, 8, 26, 27, 47]))
    assert gx.tolist() == [0.36, 0.96, 0.96, 0.96, 0.96]
    assert gy.tolist() == [0.312, 0.832, 1.222, 2.392, 3.952]
    # every PARRIED-catching attack has a measured stop, and its growth never shrinks
    assert {tk for tk, _ in PARRY_STOPS} == set(PARRY_STOP_GROW)
    for gx, gy in PARRY_STOP_GROW.values():
        assert list(gx) == sorted(gx) and list(gy) == sorted(gy)


def test_active_window_is_half_open_with_the_last_active_frame_in():
    """attack_table_build writes frames (first, last) inclusive; the kernel's window is [first, last + 1) (it scores the
    last active frame), the clash pass puts its clash frame in the same half-open window, the stats' Reach keeps
    (first, last) inclusive and the Reaper down slash's last frame is the planner's 19."""
    from ssbot.combat.forum_planner import RPR_ANTIC_F, RPR_SLASH_F, SLOTS, _shapes
    from ssbot.knowledge.attack_shapes import AttackTable
    from ssbot.tools.forum_clash_stats import RPR_DOWN, Reach
    for crest in ("Wanderer", "Reaper"):
        tab = AttackTable.load(crest)
        win = _shapes(crest)[3]
        for i, s in enumerate(SLOTS):
            sh = tab[s]
            if s == "down" and tab.config.get("down") == "Custom":
                assert tuple(win[i]) == (RPR_ANTIC_F, RPR_ANTIC_F + RPR_SLASH_F)
                assert Reach().get(crest, "down")[1] == RPR_DOWN == (win[i][0], win[i][1] - 1)
            elif sh.frames:
                assert tuple(win[i]) == (sh.frames[0], sh.frames[1] + 1)
                assert Reach().get(crest, s)[1] == tuple(sh.frames)


def test_clash_windows_follow_the_walk():
    from ssbot.combat.enemy_tables import type_table
    from ssbot.combat.forum_planner import clash_windows
    from ssbot.core.forum import FORUM_TYPES
    from tests.test_multi_forecast import REED, _reed_table
    tt = type_table(_reed_table(), FORUM_TYPES[REED])
    c, stop = frozenset({"Stab 1"}), frozenset({"Stab 1"})
    # Stab Pos (0.1 s) -> Stab 1 (0.2 - 0.3 s) -> Stab Recover
    w = clash_windows(tt, "RE_STAB", "Stab Pos", 1.0, 1.0, c, stop, 0.6)
    assert w == [pytest.approx((1.1, 1.4, True))]
    w = clash_windows(tt, "RE_STAB", "Stab 1", 1.0, 1.05, c, frozenset(), 0.6)
    assert w == [pytest.approx((1.0, 1.3, False))]
    # an overdue state may end any time: from now on
    w = clash_windows(tt, "RE_STAB", "Stab Pos", 1.0, 1.5, c, stop, 0.6)
    assert w[0][0] == pytest.approx(1.5) and w[0][1] == pytest.approx(1.8)
    assert clash_windows(tt, "RE_STAB", "Stab Recover", 1.0, 1.05, c, stop, 0.6) == []
    assert clash_windows(tt, "RE_STAB", "Alert", 1.0, 1.05, c, stop, 0.6) == []     # not a state of the family
    # capped at the horizon
    w = clash_windows(tt, "RE_STAB", "Stab Pos", 1.0, 1.0, c, stop, 0.2)
    assert w[0][1] == pytest.approx(1.2)


def test_clash_mix_and_the_table_rates(tmp_path):
    from ssbot.combat.forum_planner import clash_mix
    assert clash_mix(1.0, 0.0, 0.8) == 0.0 and clash_mix(0.0, 0.0, 0.8) == 0.8
    assert clash_mix(0.6, 0.25, 0.5) == pytest.approx(0.6 * 0.25 + 0.4 * 0.5)
    # the builder: clashable states, rates over them, n_eff = instances, a crest's own row once it has min_n
    rows = []
    for crest, st, out, n, insts in (("Reaper", "Stab 1", "clash", 30, 10), ("Reaper", "Stab 1", "hit", 2, 2),
                                     ("Reaper", "Stab 1", "neither", 8, 8), ("Reaper", "Stab Recover", "hit", 20, 20),
                                     ("Wanderer", "Stab 1", "clash", 12, 12)):
        rows.append({"crest": crest, "type": "Song Reed", "family": "RE_STAB", "slot": "normal", "side": "front",
                     "state": st, "n": n, out: n, "inst": [f"{crest}{st}{out}{k}" for k in range(insts)]})
    tab = build_table([{"union_setups": rows}], min_n=10)
    r = tab["p_fail"]["Song Reed|RE_STAB|side"]
    assert tab["clash_states"] == {"Song Reed|RE_STAB": ["Stab 1"]}
    assert (r["n"], r["clash"], r["hit"], r["neither"]) == (52, 42, 2, 8)      # Stab Recover's 20 hits left out
    assert r["n_eff"] == 32 and not r["states"]["Stab Recover"]["clash_state"]
    from ssbot.tools.forum_clash_stats import wilson_lb
    assert r["p_clash_lb"] == round(wilson_lb(42 / 52 * 32, 32), 4)
    assert r["p_fail"] == round(wilson_ub(2 / 52 * 32, 32), 4)
    assert r["by_crest"]["Wanderer"]["n_eff"] == 12
    import json
    p = tmp_path / "clash.json"
    p.write_text(json.dumps(tab), encoding="utf-8")
    ct = ClashTable.load(p)
    assert ct.clash_states("Song Reed", "RE_STAB") == frozenset({"Stab 1"})
    assert ct.rate("Song Reed", "RE_STAB", "side", "Wanderer") == (r["by_crest"]["Wanderer"]["p_fail"],
                                                                  r["by_crest"]["Wanderer"]["p_clash_lb"])
    assert ct.rate("Song Reed", "RE_STAB", "side", "Reaper") == (r["by_crest"]["Reaper"]["p_fail"],
                                                                r["by_crest"]["Reaper"]["p_clash_lb"])
    assert ct.rate("Song Reed", "RE_STAB", "up") is None


def _tr(iid, tk, fam, x, y=4.0, idle="RE_IDLE"):
    from types import SimpleNamespace
    return SimpleNamespace(iid=iid, tk=tk, pos=(x, y), cur=SimpleNamespace(family=fam, t_end=None),
                           table=SimpleNamespace(spec=SimpleNamespace(idle_family=idle)))


def test_owner_rule():
    """One committed clashable attack in its clashable span on the slash's side suffices; an enemy behind a side
    slash or outside its clashable span is not clashed (counted as a co-owner); co-owners do not block (the parry
    i-frames take every enemy's damage; the branch meets their support after them)."""
    from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
    from ssbot.combat.planner import PlannerConfig
    params = kin.HeroParams.load(KDIR / "hero_reaper_forum.json")
    pl = ForumPlanner(params, kin.Terrain2D.empty(), PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(clash=True))
    pl.clash_tab = ClashTable({("Song Reed", "RE_STAB", "side"): 0.05}, {("Song Reed", "RE_STAB", "side"): 0.9},
                              {("Song Reed", "RE_STAB"): frozenset({"Stab 1"})})
    reed = _tr(1, "Song Reed", "RE_STAB", 30.0)
    cw = {1: [(1.0, 1.3, False)]}
    rates, clashed, others = pl._owner_rule([reed], K_SIDE, -1, 32.0, 4.0, 1.1, 1.2, cw)
    assert rates == [(0.05, 0.9)] and clashed == [(reed, False)] and others == 0
    # facing away: the Reed is behind the side slash
    rates, _, others = pl._owner_rule([reed], K_SIDE, 1, 32.0, 4.0, 1.1, 1.2, cw)
    assert not rates and others == 1
    # outside its clashable span (its recovery)
    n0 = pl.audit.clash_off_state
    rates, _, others = pl._owner_rule([reed], K_SIDE, -1, 32.0, 4.0, 1.4, 1.5, cw)
    assert not rates and others == 1 and pl.audit.clash_off_state == n0 + 1
    # a committed co-owner the table does not clash is counted, an idle one is not; neither blocks
    guard = _tr(2, "Song Reed", "RE_DEFEND", 33.0)
    rates, clashed, others = pl._owner_rule([reed, guard], K_SIDE, -1, 32.0, 4.0, 1.1, 1.2, cw)
    assert rates == [(0.05, 0.9)] and clashed == [(reed, False)] and others == 1
    idle = _tr(3, "Song Reed", "RE_IDLE", 33.0)
    rates, _, others = pl._owner_rule([reed, idle], K_SIDE, -1, 32.0, 4.0, 1.1, 1.2, cw)
    assert rates and others == 0


def _wall_forecaster(defend: bool = False):
    """The synthetic Reed at x 30 facing +x, in Stab Pos from frame 10, its Stab 1 blade filling the arena on both
    sides (no way out: every row in contact from ~12 frames on)."""
    from ssbot.combat.enemy_tables import EnemyTables, Tubes, type_table
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.core.forum import FORUM_TYPES
    from ssbot.core.worldstate import ORACLE
    from tests.test_multi_forecast import BIN, BODY, REED, _ent, _go, _reed_table, _run, _templates, _tpl
    T = _templates()
    T["support/RE_STAB/Stab 1/anchor"] = _tpl("support/RE_STAB/Stab 1/anchor",
                                              [(0.0, 0.3, *BODY), (0.15, 0.3, -30.0, -3.0, 30.0, 20.0)])
    T["support/RE_STAB/anchor"] = _tpl("support/RE_STAB/anchor", [(0.0, 0.7, *BODY), (0.25, 0.4, -30.0, -3.0, 30.0,
                                                                                       20.0)])
    tabs = EnemyTables({REED: type_table(_reed_table(), FORUM_TYPES[REED])}, EnemyTables._store([T]),
                       Tubes({REED: [0.0] + [0.05 * k for k in range(1, 41)]}, {REED: 50.0}, {REED: BODY}), {}, True,
                       "synthetic", {"Song Reed/ParrySlash Hit": (2, 2)})
    mf = MultiForecaster(tabs, ORACLE, waves=False)
    script = []
    for fr in range(12):
        t = fr * BIN
        st = "Alert" if fr < 10 else "Stab Pos"
        evs = [_go(7, "Alert", fr, t)] if fr == 0 else [_go(7, "Stab Pos", fr, t)] if fr == 10 else []
        script.append((fr, t, [_ent(7, 30.0, FLOOR + 1.0, st, flip=True, box=(29.5, FLOOR, 30.5, FLOOR + 2.0))], evs))
    _run(mf, script)
    return mf


def _clash_tick(states=frozenset({"Stab 1"}), **kw):
    import math
    from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
    from ssbot.combat.planner import PlannerConfig
    from ssbot.combat.safety_filter import FilterContext
    from ssbot.combat.tactics.modes import HOLD, GoalPrefs
    from ssbot.core.primitives import N_PRIM
    from ssbot.core.worldstate import E, WorldState
    params = kin.HeroParams.load(KDIR / "hero_reaper_forum.json")
    arena = kin.Terrain2D.from_boxes([(10.0, 0.0, 53.0, FLOOR), (10.0, 0.0, 14.01, 30.0), (48.99, 0.0, 53.0, 30.0)])
    ctx_kw = {k: kw.pop(k) for k in ("tier", "pause_pending", "h") if k in kw}
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, **kw), crest="Reaper")
    keys = [("Song Reed", "RE_STAB", s) for s in ("side", "up", "down", "wall")]
    pl.clash_tab = ClashTable({k: 0.05 for k in keys}, {k: 0.9 for k in keys}, {("Song Reed", "RE_STAB"): states})
    pl.clash_fams = pl.clash_tab.families()
    f = _wall_forecaster().forecast(0.8)
    x = 36.0                                  # the blade comes ~12 frames on: a swing can be out
    start = kin.initial_state(params, x, FLOOR + params.foot)
    start[kin.FACE] = -1.0
    ws = WorldState()
    ws.hero.pos = E((x, FLOOR + 1.04))
    ws.res.hp, ws.res.hp_max, ws.res.silk = E(5), E(5), E(0)
    ctx = FilterContext(**{**dict(allowed_mask=np.ones(N_PRIM, bool), hp=5, max_hp=5, silk=0, h=3, tier="GREEN",
                                  support_known=True, kill_hp=None), **ctx_kw})
    r = pl.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, GoalPrefs(HOLD, x, {}), ctx)
    return pl, r


@pytest.fixture(scope="module")
def clash_on():
    return _clash_tick(clash=True)


def test_clash_branch_on_a_tick_without_a_way_out(clash_on):
    pl, r = clash_on
    au = pl.audit
    assert r.forced_risk and au.clash_ticks == 1 and au.clash_tier_skip == 0
    assert au.clash_inwin > 0 and au.clash_known > 0
    # every branch it kept is ranked (the blade outlasts the i-frames: no clean branch), weighted 0.9 per clash
    assert au.clash_rows == 0 and au.clash_partial > 0
    if r.clash is not None:
        assert r.clash[0] in (pytest.approx(0.9), pytest.approx(0.81)) and r.clash[2]


@pytest.mark.parametrize("kw,why", [({"clash": True, "tier": "YELLOW"}, "tier"),
                                    ({"clash": True, "pause_pending": True}, "tier"),
                                    ({"clash": True, "h": 1}, "h"),
                                    ({"clash": True, "clash_branch": False}, "branch"),
                                    ({"clash": True, "states": frozenset({"Stab Recover"})}, "state"),
                                    ({"clash": True, "states": frozenset()}, "none")])
def test_clash_branch_gates(clash_on, kw, why):
    """DESIGN 3.5.6: no clash in YELLOW or with a pause pending (unless clash_tiers says so), h >= clash_min_h; the
    continuation rows alone with clash_branch off; a contact outside the family's clashable states is not clashed.
    A skipped pass leaves the tick as the clash continuations alone make it."""
    states = kw.pop("states", frozenset({"Stab 1"}))
    ctx_kw = {k: v for k, v in kw.items() if k in ("tier", "pause_pending", "h")}
    pl, r = _clash_tick(states, **kw)
    au = pl.audit
    assert au.clash_known == 0 and au.clash_partial == 0 and au.clash_rows == 0 and r.clash is None
    assert au.clash_tier_skip == (1 if why == "tier" else 0)
    if why == "state":
        assert au.clash_inwin > 0 and au.clash_off_state > 0
    if why in ("tier", "branch", "none"):
        ref, r0 = _clash_tick(clash=True, clash_branch=False, **ctx_kw)
        assert (r.name, r.S, r.P, r.cmd.tolist()) == (r0.name, r0.S, r0.P, r0.cmd.tolist())
        assert np.array_equal(pl.last_info["Pc"], ref.last_info["Pc"])


def test_yellow_clash_is_the_experiment_switch():
    pl, r = _clash_tick(clash=True, tier="YELLOW", clash_tiers=("GREEN", "YELLOW"))
    assert pl.audit.clash_tier_skip == 0 and pl.audit.clash_known > 0


def test_minister_below_policy():
    from ssbot.ipc.framing import mask
    from ssbot.train.forum_policy import MinisterBelowPolicy
    pol = MinisterBelowPolicy()
    assert pol.stats()["frames"] == 0              # stats before any episode (a harness failure in the intro)

    def st(mx):
        m = {"type_key": "Song Administrator", "pos": [mx, 9.0], "hp": 60, "src": 1, "fsms": [{"state": "Chase"}],
             "colliders": [{"enabled": True, "damage": {"eff": 1}, "verts_world": [mx - 0.5, 8.0, mx + 0.5, 8.0,
                                                                                     mx + 0.5, 10.0, mx - 0.5, 10.0]}]}
        return {"hero": {"pos": [30.0, 4.6]}, "ents": [m]}
    outs = [pol.act(st(33.0), None) for _ in range(4)]
    assert all(o & mask("up") and o & mask("right") for o in outs)
    assert sum(bool(o & mask("attack")) for o in outs) == 2
    o = pol.act(st(30.1), None)
    assert not o & (mask("left") | mask("right"))
    assert pol.act({"hero": {"pos": [30.0, 4.6]}, "ents": []}, None) == 0
    s = pol.stats()
    assert s["frames_under"] == 1 and s["frames_minister"] == 5
