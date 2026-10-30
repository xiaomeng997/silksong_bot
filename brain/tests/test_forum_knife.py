"""Fixed proposals and conservative, shared escape checks."""
from types import SimpleNamespace

import numpy as np
import pytest

from ssbot.combat import forum_knife as fk
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.knowledge import kinematics as km
from ssbot.map2 import reflex as rx


def test_contingent_macro_is_only_a_new_fixed_proposal():
    macro = rx.Macro("cl", hop=3, cont=(("early", 42, -1), ("late", 46, 1)))
    row, p, k, fixed = fk.fixed_keys(macro, 1)
    assert macro.cont and not fixed.cont  # original evidence remains unchanged
    assert p == 3 and k == 46 and fixed.dd == 0
    assert np.flatnonzero(row & km.B_ATTACK).tolist() == [45, 46]
    assert np.flatnonzero(row & (1 << 4)).tolist() == [2, 3]
    assert np.array_equal(hold_filter_jit(row[None], km.HoldState.idle())[0][0], row)


def test_common_drift_is_kept_and_throw_direction_is_explicit():
    row, _, k, fixed = fk.fixed_keys(rx.Macro("cl", cont=(("early", 42, -1), ("late", 46, -1))), -1)
    assert k == 46 and fixed.dd == -1
    assert row[0] & km.B_LEFT and not row[0] & km.B_RIGHT


def test_unhooked_macro_cannot_claim_a_down_contact():
    with pytest.raises(ValueError, match="no down strike"):
        fk.fixed_keys(rx.Macro("cl"), 1)


def test_feature_requires_the_agreed_configuration():
    env = dict(SSBOT_FORUM_WINDOWS="1", SSBOT_FORUM_WINDOWS_CORE="2", SSBOT_FORUM_WINDOWS_PRESS="0",
               SSBOT_FORUM_SLAM_PLAY="0", SSBOT_FORUM_CLAWSTRIKE="0", SSBOT_FORUM_SLAM_PLAY_PREFS="1",
               SSBOT_FORUM_TV="0", SSBOT_FORUM_HERO2="1", SSBOT_FORUM_V2="1")
    fk.validate_environment(env)
    for key, value in (("SSBOT_FORUM_WINDOWS_CORE", "0"), ("SSBOT_FORUM_WINDOWS_PRESS", "1"),
                       ("SSBOT_FORUM_SLAM_PLAY", "1"), ("SSBOT_FORUM_TV", "1")):
        with pytest.raises(ValueError, match="incompatible"):
            fk.validate_environment({**env, key: value})


def test_envelope_keeps_an_unfavorable_hook_outcome():
    def lane(box, flags):
        return SimpleNamespace(bound=np.array([[box]], float), flags_all=np.array([[flags]], np.int64))
    bound, flags = fk.envelope([lane([0, 1, 2, 3], km.F_INVULN), lane([-4, 2, 1, 6], 0)])
    assert bound.tolist() == [[-4., 1., 2., 6.]]
    assert flags.tolist() == [0]


def test_body_shape_changes_without_changing_old_template_translation():
    class Knowledge:
        def box(self, state, frame):
            return np.array([-1., 1., -4., -1. if state == "Slam Antic" else 1.])
        def durations(self, state):
            return (2, 2, 2)
    obs = SimpleNamespace(st="Slam Antic", j=0, x=20., y=7., face=-1)
    old = np.tile([19., 3., 21., 6.], (20, 1))
    old[1:, [0, 2]] += 2.
    body = fk.slam_body_paths(obs, [old], Knowledge())[0]
    assert body[0].tolist() == [19., 3., 21., 6.]
    assert body[2].tolist() == [21., 3., 23., 8.]
    assert np.isnan(body[-1]).all()  # no fictitious stationary body after the Slam


def test_different_escapes_for_different_outcomes_are_not_a_common_escape(monkeypatch):
    # Model two valid control outcomes. Left is safe only in the first;
    # right is safe only in the second. A favorable outcome must not win.
    def rollout(state, masks, *args, **kwargs):
        direction = 1 if masks[0, -1] & km.B_RIGHT else -1
        box = np.tile([state[km.PX], direction, state[km.PX] + .5, direction + .5], (1, masks.shape[1] + 1, 1))
        return SimpleNamespace(bound=box, flags_all=np.zeros(box.shape[:2], np.int64))
    monkeypatch.setattr(km, "rollout", rollout)
    params = km.HeroParams()
    starts = {q: km.initial_state(params, q, 8, ground=False) for q in range(2)}
    path = SimpleNamespace(control_frames=np.array([2, 2]), control_states=starts)
    planner = SimpleNamespace(params=params, terrain=None, cfg=SimpleNamespace(threads=1),
                              _esc_cmds=lambda length: np.array([[km.B_LEFT] * length, [km.B_RIGHT] * length]))
    def contacts(f, bound, tk, skip, query):
        x, direction = bound[0, 0, :2]
        fail = (x < .5 and direction > 0) or (x > .5 and direction < 0)
        return np.full(bound.shape[:2], fail, bool)
    planner._contacts_fn = contacts
    forecast = SimpleNamespace(rs=SimpleNamespace(occupied_esc=lambda *a: None))
    assert fk.common_escape(planner, forecast, [path], np.zeros(40, np.int64),
                            np.zeros(2, np.int64), km.HoldState.idle(), 38) is None


def _native_hook_case(monkeypatch):
    """Exercise the accepted plumbing in an empty synthetic danger field.

    The contact oracle is controlled; this tests row/envelope/escape ownership,
    not that a real Clapper is hittable or that the treatment is effective.
    """
    from ssbot.map2.envelope import load_params
    params = load_params(hero2=True)
    obs = fk.cm.Obs(7, "Slam Antic", 2 / 60, 5., 7., 0., 0., -1, 100, None, j=2)
    class Knowledge:
        def box(self, state, frame): return np.array([-1.5, 1.5, -4., 1.])
        def durations(self, state): return (48, 48, 48)
    win = SimpleNamespace(knife_scope=True, harpoon=False, lat_s=0, fo=100, last_freeze=None,
                           obs=lambda: [obs], knife_knowledge=Knowledge(),
                           _has_full=lambda key: np.ones(len(key), bool),
                           _margin=lambda key: np.ones(len(key), bool),
                           _entry=lambda key: SimpleNamespace(macro=rx.Macro("cl", k=45)))
    target = SimpleNamespace(iid=7, hazard=False)
    def targets(ws, f, tk, prefs):
        return np.tile([3.5, 3., 6.5, 8.], (1, len(tk), 1)), np.ones((1, len(tk)), bool), None, [target]
    def contacts(ro, masks, *args):
        n = len(ro.hooks)
        return np.full(n, 46), np.full(n, 49), np.zeros(n, np.int64), np.ones(n, bool)
    planner = SimpleNamespace(params=params, terrain=None, cfg=SimpleNamespace(threads=1, max_points=8),
                               shapes=(None, None, None, np.zeros((4, 1))),
                               _forum_targets=targets, _ds_move_paths=lambda tr, keep, boxes: {0: [boxes[0]]},
                               _ds_hits=contacts, _contacts=lambda f, b, tk, sk: np.zeros(b.shape[:2], bool),
                               _contacts_fn=lambda f, b, tk, sk, fn: np.zeros(b.shape[:2], bool),
                               _esc_cmds=lambda length: np.zeros((1, length), np.int64))
    from ssbot.combat import forum_knife_coupled as coupled
    def occupied(x, y, t, *args): return np.zeros(x.shape, bool)
    forecast = SimpleNamespace(targets=lambda tk: [target],
        fc=SimpleNamespace(half=(.5, 1.2)), occupied=occupied,
        rs=SimpleNamespace(trk=None, samples=(0, 200), k_shift=0, occupied_esc=occupied))
    def paired(source, observation, durations, shift, roots):
        return SimpleNamespace(fc=source.fc, occupied=source.occupied,
            rs=SimpleNamespace(samples=source.rs.samples, k_shift=0, occupied_esc=source.rs.occupied_esc,
                knife_coupled_world=dict(iid=observation.iid, durations=tuple(durations), shift=shift)))
    monkeypatch.setattr(coupled, "conditioned_slam", paired)
    state = km.initial_state(params, 0., 6., ground=False)
    ws = SimpleNamespace(stamp=SimpleNamespace(frame=100))
    args = (planner, win, ws, forecast, state, km.HoldState.idle(),
            np.zeros(1, np.int64), SimpleNamespace(), 36, "air", None)
    return args


def test_clear_fixed_row_is_appended_with_its_real_hook_envelope(monkeypatch):
    args = _native_hook_case(monkeypatch)
    result = fk.append_rows(*args)

    assert result is not None and len(result.cmd) == 1
    assert not result.cert[0] and result.extra[0] == 1
    custom = result.custom[0]
    assert custom["bound"].shape == (38, 4) and custom["escape"] == 0
    assert custom["final"].shape == (km.K,)
    assert "worlds" not in args[0]._knife_info["hit_exit"]
    assert set(args[0]._knife_info["phase_ms"]) == {"expected_domain", "support_hook_clocks_bodies",
        "contact_worlds", "paired_forecasts", "common_escape", "checked_tail"}
    assert np.array_equal(custom["latched"], hold_filter_jit(
        np.r_[0, result.cmd[0]][None], km.HoldState.idle())[0][0])



def test_native_generator_declares_worlds_before_contact_and_never_checks_miss(monkeypatch):
    from ssbot.combat import forum_knife_coupled as coupled
    args = _native_hook_case(monkeypatch)
    order = []
    original = coupled.expected_slam_worlds
    monkeypatch.setattr(coupled, "expected_slam_worlds", lambda *a: (order.append("domain"), original(*a))[1])
    contact = coupled.contact_bounds
    monkeypatch.setattr(coupled, "contact_bounds", lambda *a, **kw: (order.append("contact"), contact(*a, **kw))[1])
    def forbidden(*a, **kw): raise AssertionError("legacy miss/H-abort path was called")
    monkeypatch.setattr(fk, "_clear", forbidden)
    monkeypatch.setattr(fk, "common_escape", forbidden)
    result = fk.append_rows(*args)
    assert order[0] == "domain" and order.count("contact") == 5
    tail = result.custom[0]["checked_tail"]
    assert len(tail.worlds) == 5 and tail.horizon == 37 and tail.jump == 50
    assert tail.through >= tail.jump + 24
    assert tail.for_runtime_row(win=args[1], forecast=args[3], frame=100, start=args[4], hold=args[5],
        prefix=args[6], T=36, cmd=result.cmd[0], latched=result.custom[0]["latched"]).shape[0] > 36



def test_reference_domain_exists_before_table_proposal_filtering(monkeypatch):
    from ssbot.combat import forum_knife_coupled as coupled
    args = _native_hook_case(monkeypatch); seen = []
    original = coupled.expected_slam_worlds
    monkeypatch.setattr(coupled, "expected_slam_worlds", lambda *a: (seen.append("domain"), original(*a))[1])
    def absent(keys):
        assert seen == ["domain"]
        seen.append("table")
        return np.zeros(len(keys), bool)
    args[1]._has_full = absent
    assert fk.append_rows(*args) is None
    assert seen == ["domain", "table"]


@pytest.mark.parametrize("P,T,passed", [(1,32,True),(2,36,True),(3,40,True),(1,45,False),(1,48,False)])
def test_native_generator_uses_actual_P_T_and_contact_boundary(monkeypatch,P,T,passed):
    args = list(_native_hook_case(monkeypatch));args[6]=np.zeros(P,np.int64);args[8]=T
    result = fk.append_rows(*args)
    assert (result is not None) == passed
    if passed:
        tail = result.custom[0]["checked_tail"]
        assert tail.horizon == P+T and result.cmd.shape == (1,T)
    else:
        assert args[0]._knife_info["gate"] == "unsupported_strike_inside_main_horizon"


def test_native_generator_rejects_missing_body_world_as_contract_error(monkeypatch):
    args = _native_hook_case(monkeypatch)
    monkeypatch.setattr(fk, "slam_body_variants", lambda *a, **kw: iter(()))
    assert fk.append_rows(*args) is None
    info = args[0]._knife_info
    assert info["contract_rejections"] == 3
    assert all(a["checks"][-1]["stage"] == "contact_worlds" for a in info["attempts"])


def test_native_generator_contact_failure_is_not_a_contract_error(monkeypatch):
    from ssbot.combat import forum_knife_coupled as coupled
    args = _native_hook_case(monkeypatch)
    def failed(*a, **kw):
        n = len(a[1].hooks)
        return np.full(n, 46), np.full(n, 49), np.full(n, 49), np.zeros(n, bool)
    monkeypatch.setattr(coupled, "contact_bounds", failed)
    assert fk.append_rows(*args) is None
    assert args[0]._knife_info["contract_rejections"] == 0
    assert args[0]._knife_info["gate"] == "contact_gate"


@pytest.mark.parametrize("change", ["domain", "forecast", "knowledge", "target"])
def test_native_receiver_rechecks_current_source_and_domain(monkeypatch, change):
    from ssbot.combat import forum_knife_coupled as coupled
    args = _native_hook_case(monkeypatch)
    result = fk.append_rows(*args); tail = result.custom[0]["checked_tail"]
    win, forecast = args[1], args[3]
    if change == "domain":
        previous = coupled.expected_slam_worlds
        monkeypatch.setattr(coupled, "expected_slam_worlds", lambda *a: previous(*a)[:-1])
    elif change == "forecast": forecast = object()
    elif change == "knowledge": win.knife_knowledge = object()
    else: win.obs = lambda: []
    with pytest.raises(ValueError):
        tail.for_runtime_row(win=win, forecast=forecast, frame=100, start=args[4], hold=args[5],
            prefix=args[6], T=36, cmd=result.cmd[0], latched=result.custom[0]["latched"])



def test_safety_support_extends_without_mutating_the_planner_forecast(monkeypatch):
    from ssbot.combat import forum_v2 as v2
    cv = v2.Canvas(cell=.25, box=(0, 0, 4, 4))
    rs = v2.RangeSupport(cv, (0, 2), k_shift=-1)
    rs.trk, rs.margin_mode = object(), "zero"
    rs.stack[:, 1, 1] = True
    rs.raw[0] = [(7, np.ones((1, 1), bool), 1, 1, 0., None)]
    rs.bombs = np.array([[7., 1., 1., .5, 0., 10.]])
    original = rs.stack.copy()
    def build(cls, trk, *, samples, k_shift, **kwargs):
        assert trk is rs.trk and samples == (7,) and k_shift == -1
        extra = v2.RangeSupport(cv, samples, k_shift)
        extra.stack[:, 2, 2] = True
        extra.stack_esc = np.zeros_like(extra.stack)
        return extra
    monkeypatch.setattr(v2.RangeSupport, "build", classmethod(build))
    f = v2.V2Forecast(SimpleNamespace(fc=None), rs)
    out = fk.safety_forecast(f, 6)
    assert out.rs is not rs and out.rs.samples == (0, 2, 7)
    assert max(out.rs.samples) + out.rs.k_shift == 6
    assert np.array_equal(rs.stack, original) and rs.samples == (0, 2)
    assert np.array_equal(out.rs.stack[:2], original)
    assert out.rs.stack[2, 2, 2]
    assert np.array_equal(out.rs.stack_esc[:2], original)
    assert not out.rs.stack_esc[2].any()
    assert out.rs.bombs is rs.bombs and out.rs.raw[0] is rs.raw[0]
    assert fk.safety_forecast(out, 6) is out


def test_escape_support_horizon_uses_the_forecast_origin_shift():
    planner = SimpleNamespace()
    forecast = SimpleNamespace(rs=SimpleNamespace(samples=(0, 62), k_shift=-2))
    with pytest.raises(ValueError, match="support horizon"):
        fk.common_escape(planner, forecast, [], np.zeros(38, np.int64),
                         np.zeros(2, np.int64), km.HoldState.idle(), 38)


@pytest.fixture
def slam_support():
    from ssbot.combat import attack_range as ar, forum_v2 as v2
    cv=v2.Canvas(cell=.25,box=(0,0,12,12))
    inst=SimpleNamespace(fam="CC_SLAM",t0=0.)
    tp=SimpleNamespace(sst=[{"Slam 1":None} if k==2 else {"Slam 2":None} if k==4 else {} for k in range(8)])
    tab=SimpleNamespace(cell=.25,templates={("CC_SLAM","main"):tp})
    def estimate(iid,k):
        # The real short-lived core, a far standing body, and a persistent
        # same-owner hazard. The hazard overlaps one part of the old arc.
        core=ar.Mask(np.ones((1,8),bool) if k==2 else np.ones((1,1),bool),12 if k==2 else 36,12)
        hazard=ar.Mask(np.ones((1,1),bool),12,12)
        return SimpleNamespace(core=core,haz=hazard,raw=ar.union([core,hazard]))
    trk=SimpleNamespace(now={7:(v2.CLAPPER,{},inst)},tables={v2.CLAPPER:tab},T=0.,estimate=estimate)
    rs=v2.RangeSupport(cv,(0,2,7),k_shift=-1)
    rs.trk,rs.focus,rs.margin_mode=trk,7,"focus"
    rs.bombs=np.array([[7.,8.,8.,.25,0.,10.]])
    for si,k in enumerate(rs.samples):
        c,x,y=v2.coarse(estimate(7,k).raw,tab.cell,cv.cell)
        rs.add_raw(si,7,c,x,y,rs.m_of(7,v2.CLAPPER,k),.5)
        # A different owner whose sparse danger must be byte-for-byte equal
        # pointwise, including its distinct escape margin.
        rs.add_raw(si,9,np.ones((1,1),bool),20+k,20,.25,.75)
    rs.finish()
    return rs


def test_slam_clock_removes_sparse_hold_but_preserves_hazards_and_other_owners(slam_support):
    rs=slam_support
    old_stack=rs.stack.copy()
    out=fk._slam_clock_support(rs,7)
    assert rs.samples==(0,2,7) and np.array_equal(rs.stack,old_stack)
    assert out.bombs is rs.bombs and out.trk is rs.trk
    assert out.knife_slam_clock==dict(iid=7,age=0,dense_from=1,dense_through=6,previous_game_bin=True)
    # Canvas points distinguish vanished arc from a hazard in the same owner.
    x=np.array([[4.8,4.8,4.8],[3.1,3.1,3.1],[8.,8.,8.]])
    y=np.array([[3.1]*3,[3.1]*3,[8.]*3])
    tk=np.array([2.,3.,4.])/60  # tracker bins 3,4,5 with k_shift=-1
    before=rs.occupied_only(x,y,tk,[7]);after=out.occupied_only(x,y,tk,[7])
    assert before[0].all() and after[0].tolist()==[True,False,False]
    assert after[1:].all()  # overlapping same-owner hazard and per-bomb clocks survive
    xx,yy=np.meshgrid(np.arange(.125,12,.25),np.arange(.125,12,.25))
    for j in range(7):
        times=np.full(xx.shape,j/60)
        assert np.array_equal(out.occupied_only(xx,yy,times,[9]),rs.occupied_only(xx,yy,times,[9]))
    assert out.stack_esc is not None


def test_slam_clock_unknown_pieces_or_owner_are_rejected(slam_support):
    rs=slam_support
    with pytest.raises(ValueError,match="focused"):
        fk._slam_clock_support(rs,8)
    rs.raw[0].append(rs.raw[0][0])
    with pytest.raises(ValueError,match="unrecognized"):
        fk._slam_clock_support(rs,7)


def test_slam_clock_keeps_the_observed_absolute_age(slam_support):
    rs=slam_support
    rs.trk.T=1/60
    out=fk._slam_clock_support(rs,7)
    assert out.knife_slam_clock["age"]==1
    assert out.knife_slam_clock["dense_from"]==0
    assert out.knife_slam_clock["dense_through"]==5


def test_slam_clock_does_not_hold_the_last_swept_bin_until_a_late_sample(slam_support):
    from ssbot.combat import attack_range as ar
    rs=slam_support
    original=rs.trk.estimate
    def estimate(iid,k):
        e=original(iid,k)
        if k==4:
            e.core=ar.Mask(np.ones((1,8),bool),12,12)
            e.raw=ar.union([e.core,e.haz])
        return e
    rs.trk.estimate=estimate
    out=fk._slam_clock_support(rs,7)
    # Last dangerous bin 4, lagged callback bin 5, first clear bin 6.
    times=np.array([3.,4.,5.,6.])/60
    x=np.full((1,4),4.8);y=np.full((1,4),3.1)
    assert out.occupied_only(x,y,times,[7]).tolist()==[[True,True,False,False]]


def test_slam_clock_does_not_replace_an_unknown_split_hazard_support(slam_support):
    slam_support.haz_raw={7:[object()]}
    with pytest.raises(ValueError,match="split hazard"):
        fk._slam_clock_support(slam_support,7)


def test_coherent_body_variants_keep_every_old_timing_and_animation_margin():
    class Knowledge:
        def box(self,st,j):
            n={"Slam Antic":0,"Slam 0":1,"Slam 1":2,"Slam 2":3,"Slam Recover":4}[st]
            return np.array([-1.-.1*j,1.+.1*j,-4.,float(n)+.1*j])
        def durations(self,st):return (2,2,3)
    obs=SimpleNamespace(st="Slam Antic",j=0,x=20.,y=7.,face=-1)
    path=np.tile([19.,3.,21.,6.],(18,1));path[1:,0::2]+=.2
    old=fk.slam_body_paths(obs,[path],Knowledge())[0]
    variants=list(fk.slam_body_variants(obs,[path],Knowledge()))
    assert len(variants)==2**5
    bs=np.stack([p for _,p in variants])
    intersection=np.concatenate((bs[...,:2].max(axis=0),bs[...,2:].min(axis=0)),axis=1)
    assert np.allclose(intersection,old,equal_nan=True)
    # The common prefix is reused by exact identity, not an epsilon test.
    assert all(np.array_equal(v[:2],old[:2]) for _,v in variants)
    outer=list(fk.slam_body_variants(obs,[path],Knowledge(),outer=True))
    for (da,inner),(db,wide) in zip(variants,outer,strict=True):
        assert da==db
        finite=np.isfinite(inner).all(axis=1)
        assert (wide[finite,:2]<=inner[finite,:2]).all()
        assert (wide[finite,2:]>=inner[finite,2:]).all()


def test_throw_waits_for_latched_turn_without_moving_the_fixed_attack():
    row,p,k,_=fk.fixed_keys(rx.Macro("cl",k=41),-1)
    aligned,press,raw,lat,delay=fk.align_throw(row,np.array([km.B_RIGHT]),km.HoldState.idle(),p,-1,80)
    assert delay==1 and press==p+1
    assert lat[0,press]&fk.ow.M_CLAW and lat[0,press]&km.B_LEFT
    assert not lat[0,press]&km.B_RIGHT
    assert np.array_equal(np.flatnonzero(aligned&km.B_ATTACK),np.flatnonzero(row&km.B_ATTACK))
    assert np.array_equal(lat,hold_filter_jit(raw[None],km.HoldState.idle())[0])
    same,press,_,_,delay=fk.align_throw(row,np.array([km.B_LEFT]),km.HoldState.idle(),p,-1,80)
    assert delay==0 and press==p and np.array_equal(same,row)
