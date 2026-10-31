"""Post-failure HP responsibility uses observed move end, never elapsed guesswork."""
import json
import pytest
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_failure import FailureExposure


def exposure(**kw):
    return FailureExposure(MoveInstance(7,100,"CC_SLAM"),origin=105,failed_frame=110,ta=1.,**kw)


def state(f,st="Slam Antic",tin=.2,*,iid=7,hp=130,dead=False):
    return {"f":f,"ents":[{"iid":iid,"hp":hp,"is_dead":dead,
        "fsms":[{"name":"Control","state":st,"t":tin}]}],"ev":[]}


def test_unknown_move_end_does_not_expire_after_thirty_frames():
    x=exposure()
    for f in [110,140,200,10000]:
        x.observe({"f":f,"ents":None});assert x.active(f)
    assert x.through is None and x.as_dict()["end_status"]=="unknown"
    assert not x.active(104) and x.active(105)


@pytest.mark.parametrize("end,through",[(120,140),(180,180)])
def test_inclusive_deadline_is_max_of_observed_end_and_failed_plus_thirty(end,through):
    x=exposure();x.observe(state(end,"Idle"))
    assert x.observed_end_frame==end and x.through==through
    assert x.active(through) and not x.active(through+1)


def test_frozen_same_antic_cannot_be_reidentified_from_render_frame():
    x=exposure()
    # A hundred reported frames pass while game/FSM clocks are frozen.
    for f in range(110,211):
        x.observe(state(f,"Slam Antic",.4),game_time=1.4)
    assert x.observed_end_frame is None and x.active(211)
    x.observe(state(212,"Slam 0",.0),game_time=1.8)
    x.observe(state(300,"Slam Recover",.0),game_time=1.95)
    assert x.active(300) and x.through is None
    x.observe(state(301,"Idle"),game_time=2.0)
    assert x.through==301 and not x.active(302)


def test_clock_quantization_does_not_end_same_antic():
    x=exposure()
    for f,delta in [(110,-.02),(111,0.),(112,.02)]:
        x.observe(state(f,"Slam Antic",.3),game_time=1.3+delta)
    assert x.observed_end_frame is None and x.active(1000)


def test_new_antic_by_actual_game_clock_closes_old_and_never_extends_to_new_move():
    x=exposure();x.observe(state(110,"Slam Antic",.4),game_time=1.4)
    x.observe(state(200,"Slam Antic",.01),game_time=3.01)
    assert x.observed_end_frame==200 and x.new_antic_entry_time==pytest.approx(3.)
    assert x.move.antic_frame==100 and x.ta==1.
    x.observe(state(300,"Slam Recover",.2),game_time=4.)
    assert x.through==200 and not x.active(300)


def test_new_antic_after_observed_slam_phase_needs_no_invented_entry_frame():
    x=exposure();x.observe(state(111,"Slam 2",.02))
    x.observe(state(160,"Slam Antic",0.))
    assert x.observed_end_frame==160
    assert x.new_antic_entry_time is None and x.move.antic_frame==100
    assert "phase returned" in x.observed_end_source


def test_time_only_and_missing_control_cannot_fake_move_end():
    x=exposure()
    x.observe({"f":200,"ents":[{"iid":7,"hp":100,"fsms":[]}]},game_time=999.)
    assert x.through is None and x.active(999)
    x.observe(state(201,"Slam Recover",.2))
    assert x.through is None


def test_game_clock_regression_keeps_antic_identity_unknown():
    x=exposure();x.observe(state(111,"Slam 0",.02),game_time=1.82)
    x.observe(state(112,"Slam Antic",0.),game_time=0.)
    x.observe(state(113,"Slam Antic",.01),game_time=.01)
    assert x.through is None and x.as_dict()["clock_identity_uncertain"]
    x.observe(state(140,"Idle"),game_time=.5)
    assert x.through==140


@pytest.mark.parametrize("kind",["hp","dead","event"])
def test_target_death_is_observed_end_but_does_not_cut_minimum(kind):
    x=exposure();s=state(115)
    if kind=="hp":s["ents"][0]["hp"]=0
    elif kind=="dead":s["ents"][0]["is_dead"]=True
    else:s={"f":115,"ents":None,"ev":[{"f":114,"k":"hit","d":{"ent":7,"dead":True}}]}
    x.observe(s)
    assert x.observed_end_frame==115 and x.through==140
    assert x.active(140) and not x.active(141)


def test_missing_target_other_death_and_future_event_are_not_death_evidence():
    x=exposure()
    x.observe({"f":150,"ents":[],"ev":[{"f":150,"k":"hit","d":{"ent":8,"dead":True}},
        {"f":151,"k":"hit","d":{"ent":7,"dead":True}}]})
    assert x.through is None and x.active(150)


def test_duplicate_and_out_of_order_observation_cannot_retroactively_end_exposure():
    x=exposure();x.observe(state(200,"Slam Recover",.4))
    x.observe(state(200,"Idle"));x.observe(state(199,"Idle"));x.observe(state(99,"Idle"))
    assert x.through is None and x.last_frame==200
    x.observe(state(201,"Idle"));assert x.through==201


def test_serialized_state_is_plain_owned_evidence_not_a_move_or_safety_certificate():
    x=exposure();data=x.as_dict();json.dumps(data,allow_nan=False)
    data["move"]["antic_frame"]=999
    assert x.move.antic_frame==100 and "not collider causality" in x.as_dict()["scope"]


@pytest.mark.parametrize("origin,failed,ta",[(99,110,1.),(105,104,1.),(105,110,float("nan")),(True,110,1.)])
def test_invalid_identity_or_frame_is_not_silently_normalized(origin,failed,ta):
    with pytest.raises(ValueError):FailureExposure(MoveInstance(7,100,"CC_SLAM"),origin,failed,ta)


def test_wrong_family_is_rejected():
    with pytest.raises(ValueError):FailureExposure(MoveInstance(7,100,"CC_JUMP"),105,110,1.)
