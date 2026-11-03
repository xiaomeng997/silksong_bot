"""Synthetic finite cases for the vault near-entry nominal path (Task 79 candidate).

Both directions: a modeled down-slash hit with its bounce and the table's own close; a miss without a phantom bounce;
first_draft without any model future; the queued key and the first offer unchanged; unknown clock / missing Run
rejected; the caller's runner untouched. run_tests79.py loads knife_chain_vault_nominal.py as
ssbot.combat.knife_chain_vault_nominal on the review snapshot before collecting this file."""
import math
import sys

import numpy as np
import pytest

from ssbot.combat import knife_chain_vault as KV
from ssbot.combat import knife_chain_step as KS_STEP
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_nominal import NominalUnsupported, logical_copy
from ssbot.combat.knife_chain_vault_entry import near_proposals
from ssbot.core.forum import FLOOR_Y, WALL_L, WALL_R
from ssbot.knowledge import kinematics as K

from ssbot.combat import knife_chain_vault_nominal as VN
P = K.hero2(K.HeroParams.load(K.REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json"),on=True)
TER = K.Terrain2D.from_boxes([(-200.0, FLOOR_Y - 10.0, 260.0, FLOOR_Y), (0.0, 0.0, WALL_L, 40.0), (WALL_R, 0.0, 70.0, 40.0)])
F0, GAME0, TARGET, BUDDY = 1000, 10.0, 2, 1
W, TOP = 3.59, FLOOR_Y + 3.90                    # an Idle Clapper body (raw 31.97..35.56, 3.015..6.917)


def rect(b):
    return [b[0], b[1], b[2], b[1], b[2], b[3], b[0], b[3]]


def scene(direction, *, gap=2.0, shift=0.0):
    """She stands on the ground; the target's near edge `gap` u in front (toward direction); the buddy airborne far
    behind her. shift moves the observed body after the proposal was made (the miss case)."""
    x0 = 32.0 if direction > 0 else 37.0
    near = x0 + direction * gap
    tb = [near, FLOOR_Y, near + W, TOP] if direction > 0 else [near - W, FLOOR_Y, near, TOP]
    S = K.initial_state(P, x0, FLOOR_Y + P.foot, facing=direction, ground=True)
    ro = K.rollout(S.reshape(K.K, 1), np.zeros((1, 1), np.int64), P, TER, backend="numba")
    hold = K.HoldState.idle(1)
    sim = ChainSim(S, np.array([0], np.int64), hold, P, TER, F0, F0)
    recipe=KV.load_vault_runner()[0].chains["vault_idle"].cfg["NEAR_RECIPE"]
    props, _ = near_proposals(sim, np.array(tb), direction, max_results=1,recipes=(recipe,))
    assert props, "fixture: no nominal near proposal"
    seen = [tb[0] + shift, tb[1], tb[2] + shift, tb[3]]
    raw = {"f": F0, "dt": 1 / 60,
           "hero": {"pos": [float(v) for v in ro.pos[0, 0]], "box": [float(v) for v in ro.box[0, 0]], "vel": [0.0, 0.0],
                    "facing": direction, "health": 7, "silk": 9, "hero_accepting_input": True,
                    "can": {"input": True, "dash": True, "harpoon": True, "attack": True},
                    "tm": {"atk_cd": 0.0, "dash_cd": 0.0}, "anim": {"clip": "Idle"}, "cstate": [0, 0], "cstate_int": [0, 0]},
           "act": {"hf": {"latched": 0, "desired": 0, "pending": [0] * 22, "age": [100] * 22}},
           "ev": [],
           "ents": [{"type_key": "Song Heavy Sentry", "iid": TARGET, "hp": 100, "is_dead": False,
                     "pos": [0.5 * (seen[0] + seen[2]), FLOOR_Y + 4.43], "flipX": direction < 0,
                     "fsms": [{"name": "Control", "state": "Idle", "t": 0.4}],
                     "colliders": [{"name": "Song Heavy Sentry", "enabled": True, "layer": 11, "verts_world": rect(seen)}]},
                    {"type_key": "Song Heavy Sentry", "iid": BUDDY, "hp": 100, "is_dead": False,
                     "pos": [x0 - direction * 9.0, 12.0], "flipX": direction > 0,
                     "fsms": [{"name": "Control", "state": "Air", "t": 0.2}], "colliders": []}]}
    p0 = props[0]
    far = tb[2] if direction > 0 else tb[0]
    request = {"iid": TARGET, "over_dir": direction, "near": {"h": int(p0.hold), "p": int(p0.press), "before": p0.before},
               "far": None, "nogo": [], "x_end": far}
    runner = KV.load_vault_runner()[0]
    return runner, raw, sim, request, tb


@pytest.mark.parametrize("direction", [-1, 1])
def test_modeled_hit_bounces_and_the_table_closes_by_itself(direction):
    runner, raw, sim, request, tb = scene(direction)
    path = VN.compile_near(runner, raw, sim, GAME0, request=request, buddy_iid=BUDDY, buddy_lock_until=GAME0 + 0.85)
    assert path.stage == "approach" and path.end == "handback"
    assert path.press_frame is not None and path.contact_frame is not None
    assert 3 <= path.contact_frame - path.press_frame <= 9
    done = path.runner_end.done[-1]
    assert done.closed in ("done", "handback") and done.v.get("bounced") is True
    hits = path.assumptions["contacts"]
    assert hits[0]["kind"] == "down" and hits[0]["F"] == path.contact_frame
    end_cx = 0.5 * (path.box[-1][0] + path.box[-1][2])
    assert (end_cx - 0.5 * (tb[0] + tb[2])) * direction > 0          # she ends on the far side of the body
    # the caller's runner never received the request, the preview or the model future
    assert runner.run is None and runner.done == [] and runner.anchor.request is None


@pytest.mark.parametrize("direction", [-1, 1])
def test_first_draft_holds_only_the_real_preview(direction):
    runner, raw, sim, request, _ = scene(direction)
    path = VN.compile_near(runner, raw, sim, GAME0, request=request, buddy_iid=BUDDY, buddy_lock_until=GAME0 + 0.85)
    d = path.first_draft
    assert d.run is not None and d.done == []
    assert d.run.v.get("down_hit_f") is None and not d.run.v.get("bounced") and d.run.v.get("unlocked_hit_f") is None
    assert path.runner_end.done and path.runner_end.done[-1].v.get("bounced") is True


@pytest.mark.parametrize("direction", [-1, 1])
def test_queued_key_and_first_offer_are_the_real_pipeline(direction):
    runner, raw, sim, request, _ = scene(direction)
    prefix = sim.prefix.copy()
    path = VN.compile_near(runner, raw, sim, GAME0, request=request, buddy_iid=BUDDY, buddy_lock_until=GAME0 + 0.85)
    np.testing.assert_array_equal(sim.prefix, prefix)
    assert int(path.commands[0]) == int(prefix[0])
    R = logical_copy(runner)
    R.anchor.open(request)
    first = R.step(F0, raw, True, True, t_game=GAME0, sim=sim)
    assert int(path.offered[0]) == int(first)


@pytest.mark.parametrize("direction", [-1, 1])
def test_a_miss_injects_no_bounce_and_is_unsupported(direction, monkeypatch):
    runner, raw, sim, request, _ = scene(direction, shift=direction * 4.0)
    events = []
    original = KS_STEP.NominalStepper.run

    def spy(self, start, mask=0, *, event=0, frames=1):
        events.append(int(event))
        return original(self, start, mask, event=event, frames=frames)
    monkeypatch.setattr(KS_STEP.NominalStepper, "run", spy)
    with pytest.raises(NominalUnsupported):
        VN.compile_near(runner, raw, sim, GAME0, request=request, buddy_iid=BUDDY, buddy_lock_until=GAME0 + 0.85)
    assert K.EV_POGO not in events
    assert runner.run is None and runner.done == []


@pytest.mark.parametrize("clock", [float("nan"), float("inf"), None, True])
def test_unknown_lock_clock_is_unsupported(clock):
    runner, raw, sim, request, _ = scene(-1)
    with pytest.raises(NominalUnsupported):
        VN.compile_near(runner, raw, sim, GAME0, request=request, buddy_iid=BUDDY, buddy_lock_until=clock)


def test_continuing_needs_an_active_run():
    runner, raw, sim, _, _ = scene(-1)
    with pytest.raises(NominalUnsupported):
        VN.compile_near(runner, raw, sim, GAME0, request=None, buddy_iid=BUDDY, buddy_lock_until=GAME0 + 0.85)


def test_each_model_frame_uses_the_already_loaded_cstate_schema(monkeypatch):
    from ssbot.combat.knife_chain_nominal import state_names
    names=state_names()
    index=names.index("downSpikeBouncingShort")
    bits=[(1<<64)-1 for _ in range(index//64+1)]
    s={"hero":{"cstate":bits.copy()}}
    def unexpected_read():pytest.fail("model frame reread the schema file")
    monkeypatch.setattr(K,"cstate_names",unexpected_read)
    VN._clear_short_bounce(s);VN._clear_short_bounce(s)
    expected=bits.copy();expected[index//64]&=~(1<<(index%64))
    assert s["hero"]["cstate"]==expected


def test_a_lock_that_never_ends_cannot_be_called_a_handback():
    runner, raw, sim, request, _ = scene(-1)
    with pytest.raises(NominalUnsupported):
        VN.compile_near(runner, raw, sim, GAME0, request=request, buddy_iid=BUDDY, buddy_lock_until=GAME0 + 1000.0, max_frames=90)


def test_recorded_collider_names_still_reach_the_handback():
    runner, raw, sim, request, _ = scene(-1)
    for e in raw["ents"]:
        for c in e.get("colliders") or ():
            c["name"] = "Song Heavy Sentry (2)" if e["iid"] == TARGET else "Song Heavy Sentry (3)"
    path = VN.compile_near(runner, raw, sim, GAME0, request=request, buddy_iid=BUDDY, buddy_lock_until=GAME0 + 0.85)
    assert path.end == "handback"


@pytest.mark.parametrize("direction",[-1,1])
def test_real_post_bounce_memory_continues_original_exit_without_another_pogo(direction,monkeypatch):
    from copy import deepcopy
    from ssbot.combat.knife_chain_nominal import _hero
    from ssbot.combat.holdfilter import hold_filter_jit
    runner,raw,sim,request,_=scene(direction)
    path=VN.compile_near(runner,raw,sim,GAME0,request=request,buddy_iid=BUDDY,buddy_lock_until=GAME0+.85)
    k=path.contact_frame-F0
    # A synthetic observed checkpoint, with only its already elapsed history.
    actual=deepcopy(raw);actual["f"]=F0+k
    _hero(actual,path.states[:,k],path.box[k],path.pos[k],np.zeros(2),int(path.flags[k]))
    actual["ev"]=[{"k":"hit","f":F0+k,"d":{"iid":TARGET,"src":"DownSlash"}}]
    _,hold=hold_filter_jit(path.commands[None,:k],sim.hold)
    follow=ChainSim(path.states[:,k],path.commands[k:k+1].copy(),hold,P,TER,F0+k,F0+k)
    r=KV.load_vault_runner()[0]
    run=deepcopy(path.runner_end.done[-1]);run.closed=None;run.link="over"
    run.sent=[(f,m) for f,m in run.sent if f<=actual["f"]+1]
    run.v.update(bounced=True,down_hit_f=path.contact_frame,bounce_f=path.contact_frame,
                 unlocked_hit_f=None,side_hits=[],air_press_F=None,g_press_F=None,n_side=0)
    r.run=run
    events=[];original=KS_STEP.NominalStepper.run
    def spy(self,start,mask=0,*,event=0,frames=1):
        events.append(event);return original(self,start,mask,event=event,frames=frames)
    monkeypatch.setattr(KS_STEP.NominalStepper,"run",spy)
    out=VN.compile_near(r,actual,follow,float(path.game[k]),request=None,buddy_iid=BUDDY,buddy_lock_until=GAME0+.85)
    assert out.contact_frame==path.contact_frame and out.end=="handback"
    assert K.EV_POGO not in events
