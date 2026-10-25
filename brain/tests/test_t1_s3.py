"""Map v2, t1 workflow stage S3 (HANDOFF 'Task map2 - fix together (t1) - stage S3'): the verifiers' findings on S1 /
S2, each fix behind a switch default off (LiveCfg.su_fix / su_band - the side / up slash; t1_fix / t1_aim / t1_lazy -
tier 1); the switches off: S1 / S2 as before."""
from __future__ import annotations

import pickle
import queue

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import clapper_jit as cj
from ssbot.map2 import live as lv
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk
from ssbot.map2 import tier1 as t1

R, L, A, U, D = km.B_RIGHT, km.B_LEFT, km.B_ATTACK, km.B_UP, km.B_DOWN
C = 33.0
IDLE_H = lv.hold_tuple(km.HoldState.idle(1))


@pytest.fixture(scope="module")
def W():
    return ms.World()


@pytest.fixture(autouse=True)
def _switches():
    # (other suites drop ssbot.map2 from sys.modules and import it again: the current module objects here)
    import importlib
    global lv, ms, t1, cm, cj, sk
    lv, ms, t1 = (importlib.import_module("ssbot.map2." + n) for n in ("live", "search", "tier1"))
    cm, cj, sk = (importlib.import_module("ssbot.map2." + n) for n in ("clapper", "clapper_jit", "strike"))
    lv.set_switches(lv.LiveCfg())
    yield
    lv.set_switches(lv.LiveCfg())


def _on(**kw):
    lv.set_switches(lv.LiveCfg(prims_su=True, su_fix=True, **kw))


def _stand(W, x, face=1):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, facing=face)


def _box_rows(x0, x1, y0=sk.FLOOR, y1=sk.FLOOR + 3.9, n=40):
    return np.tile(np.array([x0, y0, x1, y1], float), (n, 1))


def _obs(st, x, face=-1, j=2, iid=1, y=cm.STAND_Y, vx=0.0, vy=0.0):
    return cm.Obs(iid, st, j / 60.0, x, y, vx, vy, face, 230, None, will_evade=None, j=j)


def test_switches_default_off():
    c = lv.LiveCfg()
    assert (c.su_fix, c.su_band, c.t1_fix, c.t1_aim, c.t1_lazy) == (False, 0.0, False, False, False)
    lv.set_switches(c)
    assert ms.SU_FIX[0] is False and ms.SU_BAND[0] == 0.0 and cm.UP_RECOIL[0] is False
    assert t1.T1_FIX[0] is False and t1.T1_AIM[0] is False
    _on(su_band=0.2, t1_fix=True, t1_aim=True)
    assert ms.SU_FIX[0] and ms.SU_BAND[0] == 0.2 and cm.UP_RECOIL[0] and t1.T1_FIX[0] and t1.T1_AIM[0]


# ---- the side / up slash (S1's findings) ----------------------------------------------------------------------------

def _keys_after_press(plan):
    out = []
    for seg in plan.segs:
        for (i, _) in seg.dsl:
            m = int(seg.masks[i])
            if not (m & D):
                out.append([int(v) for v in seg.masks[i:i + 8]])
    return out


def test_a_left_facing_slash_holds_the_direction_as_the_right_facing_one(W):
    """Finding 2: extra = face x 10 + dc decoded with % 10 gave dc 9 / 8 / 6 for face -1 - the direction key held 7
    frames after a left press instead of dc - 1 (<= 3). su_fix: the mirrored situations get mirrored keys."""
    from ssbot.tools import m3_accept as ma
    res = {}
    for fix in (False, True):
        lv.set_switches(lv.LiveCfg(prims_su=True, su_fix=fix))
        for (hx, hf, cf, dk) in ((C - 4.5, 1, -1, R), (C + 4.5, -1, 1, L)):
            sit = ma._sit(ma._her(W, hx, face=hf), [ma._obs("Spell Antic", C, face=cf, j=4)], "cast", [])
            S = ms.Searcher(W, ms.Cfg(cap_s=0.4, prims=("dslash", "claw", "side", "up")))
            S.vclock = 0.004
            r = S.decide(sit)
            ks = _keys_after_press(r.plan)
            assert ks, (fix, dk)
            res[(fix, dk)] = max(sum(1 for v in k[1:] if v & dk) for k in ks)
    assert res[(True, R)] <= 3 and res[(True, L)] <= 3
    assert res[(False, L)] >= 5                               # (the defect, reproduced with the switch off)


def test_a_side_hit_re_predicts_in_every_state(W):
    """Finding 1: _hit_matters re-predicted only Idle / Walk / a state's last frames / a kill - a side hit's 0.48 u
    recoil in a Spell Antic was never in the boxes later strikes were credited on. su_fix: a side / up hit always."""
    sit = ms.Situation(_stand(W, C - 4.0), [_obs("Spell Antic", C, j=4)], {1: cm.Memory()})
    S = ms.Searcher(W, ms.Cfg(cap_s=0.4))
    plan = ms.Plan([ms.Seg(np.zeros(30, np.int64), [], None, "t")], "prim")
    tr = S.ev.sim(sit, plan, sk.HOOK_VARIANTS[0], 1)
    P = S.ev.predict(sit, ms.hero_path(tr, 60, {}), 60)
    b = P.branches[0]
    assert sk.state_at(b, 1, 5)[0] == "Spell Antic"
    assert not S.ev._hit_matters(sit, b, {}, [], 6, 1, ("side", 10))
    _on()
    assert S.ev._hit_matters(sit, b, {}, [], 6, 1, ("side", 10))
    assert S.ev._hit_matters(sit, b, {}, [], 6, 1, ("up", 10))
    assert not S.ev._hit_matters(sit, b, {}, [], 6, 1, ("down", 10))


@pytest.mark.parametrize("pred", ["py", "jit"])
def test_an_up_hit_in_the_air_pushes_the_clapper_up(W, pred):
    """Finding 3: an UpSlash hit on an airborne Clapper (the recordings: +0.06 u per physics step for 8 steps, 0.48 u)
    had no recoil in either model. su_fix (clapper.UP_RECOIL): up 0.48 u in the air, the x track unchanged."""
    fn = cm.predict if pred == "py" else cj.predict
    obs = [_obs("Air", C, face=-1, j=3, y=cm.STAND_Y + 2.0, vx=-3.0, vy=14.0)]
    mems = {1: cm.Memory()}
    T = 40
    xs = np.full(T + 1, C - 8.0)
    ys = np.full(T + 1, sk.FLOOR + sk.FOOT)
    box = np.tile(np.array([C - 8.4, sk.FLOOR, C - 7.6, sk.FLOOR + 1.3]), (T + 1, 1))

    def top(hits):
        P = fn(obs, mems, cm.HeroPath(xs, ys, box, hits), W.K, T=T)
        bx = sk.robust_boxes(P.branches[0], 1, T)
        return bx[:, 3].copy(), bx[:, 0].copy()
    y0, x0 = top({})
    y1, x1 = top({1: {4: ("up", 10)}})
    cm.UP_RECOIL[0] = True
    y2, x2 = top({1: {4: ("up", 10)}})
    ok = ~np.isnan(y0) & ~np.isnan(y2)
    assert np.allclose(y1[ok], y0[ok]) and np.allclose(x2[ok], x0[ok])
    d = (y2 - y0)[ok]
    assert d[:5].max() < 1e-9 and 0.40 <= d.max() <= 0.49


def test_a_swing_credits_every_clapper_it_meets(W):
    """Finding 4: simulate tested a side swing against its own target only - the game damages every Clapper the
    polygons meet. su_fix: su_fn.ids - the other Clapper's hit credited too (and so re-predicted)."""
    S = _stand(W, 30.0, face=1)
    masks = np.array([A | R, R, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], np.int64)
    a, b = _box_rows(32.4, 36.0), _box_rows(32.8, 36.4)
    boxes = {7: a, 8: b}
    plan = ms.Plan([ms.Seg(masks, [(0, 7)], None, "t")], "prim")

    def su(iid):
        return boxes.get(iid)
    su.ids = (7, 8)
    lv.set_switches(lv.LiveCfg(prims_su=True))
    off = ms.simulate(W, plan, su, 1, S, sk.HOOK_VARIANTS[0], su_fn=su)
    assert {c[1] for c in off.contacts} == {7}
    _on()
    on = ms.simulate(W, plan, su, 1, S, sk.HOOK_VARIANTS[0], su_fn=su)
    assert {c[1] for c in on.contacts} == {7, 8} and 8 in on.hits
    assert np.allclose(on.pos, off.pos)                      # (one recoil: the first contact's)
    assert len(on.susw) == 2


def test_the_uncertain_band_of_a_miss(W):
    """Finding 6 (su_band): a press the model calls a miss whose polygons meet the target grown by the band is a forced
    collision ('su_band'); off: a plain miss."""
    S = _stand(W, 30.0, face=1)
    masks = np.array([A | R, R, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], np.int64)
    plan = ms.Plan([ms.Seg(masks, [(0, 7)], None, "t")], "prim")
    hit = ms.simulate(W, plan, lambda i: _box_rows(32.4, 36.0), 1, S, sk.HOOK_VARIANTS[0],
                      su_fn=lambda i: _box_rows(32.4, 36.0))
    assert hit.contacts
    reach = None
    for x0 in np.arange(32.4, 35.0, 0.02):
        bx = _box_rows(x0, x0 + 3.0)
        tr = ms.simulate(W, plan, lambda i, bx=bx: bx, 1, S, sk.HOOK_VARIANTS[0], su_fn=lambda i, bx=bx: bx)
        if not tr.contacts:
            reach = x0
            break
    assert reach is not None
    near = _box_rows(reach + 0.05, reach + 3.05)
    _on()
    tr0 = ms.simulate(W, plan, lambda i: near, 1, S, sk.HOOK_VARIANTS[0], su_fn=lambda i: near)
    assert not tr0.contacts and not tr0.bad
    _on(su_band=0.2)
    tr1 = ms.simulate(W, plan, lambda i: near, 1, S, sk.HOOK_VARIANTS[0], su_fn=lambda i: near)
    assert not tr1.contacts and [w for (_, w) in tr1.bad] == ["su_band"]


def test_the_tube_keeps_a_side_contact_on_a_small_offset(W):
    """Finding 5: a side / up contact ahead always sent the tube to the exact re-check, which refuses a side swing under
    way. su_fix: su_kept re-tests the contact on her offset path - 0.03 u keeps it, 1.5 u away does not."""
    from ssbot.tools import m3_accept as ma
    _on()
    sit = ma._sit(ma._her(W, C - 4.5, face=1), [ma._obs("Spell Antic", C, face=-1, j=4)], "cast", [])
    S = ms.Searcher(W, ms.Cfg(cap_s=0.4, prims=("dslash", "claw", "side", "up")))
    S.vclock = 0.004
    r = S.decide(sit)
    outs = lv.build_outs(r.ev)
    o = next(o for o in outs if any(kd == "side" for (_, _, kd) in o.contacts))
    k = min(int(c[0]) for c in o.contacts if c[2] == "side")
    n = k - 2
    assert lv.contact_kept(o, o.pos, n, 0.03, 0.03, 0.0, 0.0, 4)
    assert not lv.contact_kept(o, o.pos, n, -1.5, 0.0, 0.0, 0.0, 4)
    lv.set_switches(lv.LiveCfg(prims_su=True))
    assert not lv.contact_kept(o, o.pos, n, 0.03, 0.03, 0.0, 0.0, 4)       # (S1: always the re-check)


# ---- tier 1 (S2's findings) -----------------------------------------------------------------------------------------

class _Trk:
    def __init__(self, obs):
        self.o = obs
        self.cl = {o.iid: {"st": o.st, "ent": 0, "e": {}} for o in obs}

    def obs(self):
        return self.o

    def mems(self):
        return {o.iid: cm.Memory() for o in self.o}

    def hazards(self, K):
        return []


def _ctl_with_plan(W, fix: bool, x=C - 9.0, **kw):
    cfg = lv.LiveCfg(prio="as", parts=0, tier1=True, t1_workers=1, t1_cap=1.0, t1_fix=fix, **kw)
    lv.set_switches(cfg)
    ctl = lv.Map2Controller(cfg=cfg)
    out_q, t1q = queue.Queue(), queue.Queue()
    ctl.attach_inproc([], out_q, t1_qs=[t1q])
    ctl.reset(0)
    sit = ms.Situation(_stand(W, x), [_obs("Idle", C, j=8)], {1: cm.Memory()})
    ctl.trk = _Trk(sit.obs)
    raw = {"hero": {"pos": [float(sit.S[km.PX]), float(sit.S[km.PY])], "hero_accepting_input": True}, "dt": 1 / 60,
           "act": {"mask": 0}}
    hold = km.HoldState.idle(1)
    inf = np.zeros(1, np.int64)
    ctl.pre(100, 100, raw, sit.S, inf, hold)
    ctl.post(100, 100, raw, sit.S, inf, hold, 0, "plan", np.zeros(20, np.int64), False)
    snap = t1q.get_nowait()
    S = lv._Searcher(W, t1.t1_cfg(ms.Cfg.live()))
    S.vclock = 0.01
    snap["t_wall"] = None
    lp = lv._t1_search_one(S, cfg, snap, 100, {}, lambda: False)
    assert isinstance(lp, lv.LivePlan)
    lp.ep = 0
    return ctl, out_q, lp, sit, raw, hold, inf


def test_tier1_plays_an_outcome_only_to_its_committed_end(W):
    """Finding 7: tier 1 kept an outcome playable while r < len(cmds) - past its committed end kc (a 'dev' outcome's
    keys into the collision the search avoided only by deviating). t1_fix: the plan ends when a possible outcome's kc
    passed (tier 2's M4d rule); off: it plays on."""
    for fix in (False, True):
        ctl, out_q, lp, sit, raw, hold, inf = _ctl_with_plan(W, fix, t1_past=8)
        for o in lp.outs:
            o.kc, o.kcol, o.why = 4, 9, "dev"
        out_q.put(lp)
        whys = []
        for k in range(1, 6):
            m = ctl.pre(100 + k, 100 + k, raw, sit.S, inf, hold)
            whys.append(ctl.row.get("why"))
            ctl.post(100 + k, 100 + k, raw, sit.S, inf, hold, 0 if m is None else m, "m2" if m is not None else "plan",
                     None, False)
        c = ctl.stats()["counts"]
        if fix:
            # (her observed position here is not the plan's: no outcome consistent - played only within kc, then
            # ended; consistent ones end at kc by the same rule - 't1_end_kc')
            assert whys[:2] == ["t1", "t1"] and all(w != "t1" for w in whys[2:]), whys
            assert c.get("t1_end_kc_dev", 0) + c.get("t1_end_kc", 0) + c.get("t1_exhausted", 0) >= 1, c
        else:
            assert whys == ["t1"] * 5 and not c.get("t1_end_kc_dev")


def test_tier1_plays_on_past_kc_to_the_collision_or_a_clawline(W):
    """t1_past (with t1_fix): past kc the outcome's own keys are played up to t1_past frames before its collision and
    never into a Clawline pressed after kc - the bridge carries the same keys; then the plan ends."""
    assert lv.t1_lim(type("O", (), {"kc": 4, "kcol": 16, "cmds": np.zeros(40, np.int64)})(), 1) == 15
    cl = np.zeros(40, np.int64)
    cl[11] = lv.M_CLAW
    assert lv.t1_lim(type("O", (), {"kc": 4, "kcol": 16, "cmds": cl})(), 1) == 10
    assert lv.t1_lim(type("O", (), {"kc": 4, "kcol": None, "cmds": cl})(), 1) == 10
    assert lv.t1_lim(type("O", (), {"kc": 4, "kcol": 16, "cmds": cl})(), 0) == 4
    ctl, out_q, lp, sit, raw, hold, inf = _ctl_with_plan(W, True, t1_past=8)
    c0 = np.asarray(lp.outs[0].cmds, np.int64).copy() & ~np.int64(lv.M_CLAW)
    for o in lp.outs:
        o.kc, o.kcol, o.why = 4, 16, "dev"
        o.cmds = c0.copy()                       # (one key per frame: no disagreement merge)
    out_q.put(lp)
    sent, whys = [], []
    for k in range(1, 12):
        m = ctl.pre(100 + k, 100 + k, raw, sit.S, inf, hold)
        whys.append(ctl.row.get("why"))
        if m is not None:
            sent.append((102 + k - int(lp.t_a), int(m)))
            if k == 3:
                br, _ = ctl._t1_bridge(100 + k, 10)
                assert br and len(br) <= 8 - (100 + k + 3 - int(lp.t_a)) + 1
        ctl.post(100 + k, 100 + k, raw, sit.S, inf, hold, 0 if m is None else m, "m2" if m is not None else "plan",
                 None, False)
    assert max(r for (r, _) in sent) == max(lv.t1_lim(o, 8) for o in lp.outs) == 8, (sent, whys)
    assert all(m == int(c0[r]) for (r, m) in sent), sent                  # (its own keys past kc)
    assert ctl.stats()["counts"].get("ticks_t1_past", 0) >= 3


def test_tier1_bridge_capped_at_kc(W):
    """Finding 9: _t1_bridge extended to the cmds' end - past the outcomes' kc. t1_fix: capped there."""
    for fix in (False, True):
        ctl, out_q, lp, sit, raw, hold, inf = _ctl_with_plan(W, fix)
        out_q.put(lp)
        ctl.pre(101, 101, raw, sit.S, inf, hold)
        for o in lp.outs:
            o.kc, o.kcol = 8, 12                      # (the collision near: t1_past's limit is kc)
        ctl.cfg.t1_past = 8
        br, _ = ctl._t1_bridge(101, 10)
        r = 101 + 3 - int(lp.t_a)
        assert (len(br) <= 8 - r + 1) == fix or len(lp.outs[0].cmds) <= 9


def test_tier1_holds_its_own_clawline_block(W):
    """Finding 11: live, her 'no input' inside tier 1's own Clawline made tier 1 yield (the fallback's keys, then the
    plan 'left' at control). t1_fix: tier 1 holds the keys through its own block."""
    for fix in (False, True):
        ctl, out_q, lp, sit, raw, hold, inf = _ctl_with_plan(W, fix)
        for o in lp.outs:
            o.blocks = [(1, 30)]
        out_q.put(lp)
        m = ctl.pre(101, 101, raw, sit.S, inf, hold)
        assert m is not None and ctl.row["why"] == "t1"
        ctl.post(101, 101, raw, sit.S, inf, hold, m, "m2", None, False)
        raw2 = {**raw, "hero": {**raw["hero"], "hero_accepting_input": False, "anim": {"clip": "Harpoon Dash"}}}
        m2 = ctl.pre(102, 102, raw2, sit.S, inf, hold)
        assert (m2 is not None and ctl.row["why"] == "t1") == fix


def test_a_proven_safe_plan_replaces_one_with_no_consistent_outcome(W):
    """Finding 10: the 'unaware' rule refused newer proven-safe plans while the plan in hand had had no consistent
    outcome for many ticks. t1_fix: such a plan in hand is proven safe no more."""
    for fix in (False, True):
        ctl, out_q, lp, sit, raw, hold, inf = _ctl_with_plan(W, fix)
        out_q.put(lp)
        m = ctl.pre(101, 101, raw, sit.S, inf, hold)
        ctl.post(101, 101, raw, sit.S, inf, hold, m, "m2", None, False)
        assert ctl.t1_ctrl is lp and lp.t1_safe
        import copy
        b = copy.copy(lp)
        b.pid, b.t_a, b.seq, b.t1_prev_pid = "t0:99", lp.t_a + 1, lp.seq + 1, None
        b.value = float(lp.value)
        ctl.t1_exe = (lp.pid, ctl.t1_exe[1], ctl.t1_exe[2], True)          # (no outcome consistent on its last tick)
        out_q.put(b)
        ctl.pre(102, 102, raw, sit.S, inf, hold)
        c = ctl.stats()["counts"]
        if fix:
            assert ctl.t1_ctrl is b, c
        else:
            assert ctl.t1_ctrl is lp and c.get("t1_unaware", 0) >= 1


def test_risk_key_counts_no_exit_with_the_hits():
    """Finding 14 (t1_fix): a plan whose every outcome has no exit no longer ranks ahead of a 1 % hit."""
    from types import SimpleNamespace as NS

    def ev(*outs):
        return NS(outcomes=[NS(p=p, why=w, safe=False) for (p, w) in outs], value_open=0.0)
    noexit = ev((1.0, "exit@40"))
    hit1 = ev((0.01, "hit@50"), (0.99, ""))
    hit1.outcomes[1].safe = True
    assert t1.risk_key(noexit) < t1.risk_key(hit1)
    t1.T1_FIX[0] = True
    assert t1.risk_key(hit1) < t1.risk_key(noexit)


def test_lazy_geometry_round_trip(W):
    """Finding 15 (t1_lazy): the outcomes' geometry shipped as bytes, unpickled on first use, equal to the original;
    the pickled plan smaller."""
    ctl, out_q, lp, sit, raw, hold, inf = _ctl_with_plan(W, True)
    ctl2, out_q2, lpz, *_ = _ctl_with_plan(W, True, t1_lazy=True)
    assert "outs" not in lpz.__dict__ and "_outz" in lpz.__dict__
    lp2 = pickle.loads(pickle.dumps(lpz))
    assert "_outz" in lp2.__dict__ and lp2.t1_safe == lpz.t1_safe and lp2.cmds_pre is not None
    n0 = lv.LAZY_STATS["unpacked"]
    assert len(lp2.outs) == len(lp.outs) and lv.LAZY_STATS["unpacked"] == n0 + 1 and "_outz" not in lp2.__dict__
    for o, o2 in zip(lp.outs, lp2.outs):
        for a, b in zip(o.geo, o2.geo):
            assert np.array_equal(np.asarray(a), np.asarray(b))
        assert np.array_equal(o.cmds, o2.cmds) and set(o2.rare) == set(o.rare)
    # the controller adopts and plays the lazy plan as the plain one
    out_q2.put(lpz)
    m = ctl2.pre(101, 101, raw, sit.S, inf, hold)
    assert m is not None and ctl2.row["why"] == "t1"


def test_the_tail_aim_check_runs(W):
    """Finding 12 (t1_aim): the escape tail re-checked against the Clappers re-predicted under it."""
    t1.T1_AIM[0] = True
    t1.AIM_STATS.update(checked=0, rejected=0, unmatched=0, pred=0)
    S = ms.Searcher(W, t1.t1_cfg(ms.Cfg.live()))
    S.realizer = lv.HoldRealizer(1, IDLE_H, face0=1)
    S.vclock = 0.01
    sit = ms.Situation(_stand(W, C - 6.0), [_obs("Idle", C, j=8)], {1: cm.Memory()})
    r = t1.t1_decide(S, sit, ms.Seg(np.zeros(1, np.int64), [], None, "pre"), None, 1.0)
    e, _ = t1.t1_tail(S, sit, r.ev, 40, n_min=1)
    assert t1.AIM_STATS["checked"] >= 1 and t1.AIM_STATS["pred"] >= 1
