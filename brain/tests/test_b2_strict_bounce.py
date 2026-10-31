"""B-only table and history pogo proof; default legacy predicates stay intact.

No physics rollout, game, P-core timing or recorded-input replay is performed.
"""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from ssbot.knowledge import kinematics as kin
from ssbot.combat.knife_chain_observations import pogo_marker,target_pogo_hit
from ssbot.combat.knife_chain_slam import g_s_hit
from ssbot.combat.knife_chain_history import HistView
from ssbot.combat import slam_play as SP


def state(f=100,*,source="DownSlash",target=7,marker="counter"):
    s={"f":f,"hero":{"cstate":[0,0],"cstate_int":[0,0,0,0],"vel":[0.,0.]},
       "ev":[{"f":f,"k":"hit","d":{"iid":target,"type_key":SP.CLAPPER,"src":source}}]}
    if marker=="counter":s["hero"]["cstate_int"][1]=8
    elif marker in {"downSpikeBouncing","downSpikeBouncingShort"}:
        i=kin.cstate_names().index(marker);s["hero"]["cstate"][i//64]|=1<<(i%64)
    return s


def context(s,strict=None):
    anchor=SimpleNamespace()
    if strict is not None:anchor.b2_strict_observations=strict
    return SimpleNamespace(R=SimpleNamespace(anchor=anchor),obs=SimpleNamespace(s=s),v={"iid":7})


@pytest.mark.parametrize("marker",["counter","downSpikeBouncing","downSpikeBouncingShort"])
def test_target_downslash_and_each_actual_pogo_lane_are_required(marker):
    s=state(marker=marker);before=deepcopy(s)
    assert pogo_marker(s) and target_pogo_hit(s,7) and g_s_hit(context(s,True))
    assert s==before


@pytest.mark.parametrize("source",["Slash","SlashAlt","Harpoon","Harpoon DownSlash","DownSpike"])
def test_other_attacks_never_become_pogo_even_with_a_positive_counter(source):
    s=state(source=source)
    assert pogo_marker(s) and not target_pogo_hit(s,7) and not g_s_hit(context(s,True))


@pytest.mark.parametrize("source",["DownSlash","DownSlashAlt","DownSlash(Clone)"])
def test_observed_downslash_sources_include_existing_variant_names(source):
    assert target_pogo_hit(state(source=source),7)


@pytest.mark.parametrize("decoy",["vy","clip","other_counter","negative_counter","antic","recovery","generic_invuln"])
def test_non_pogo_observations_do_not_fake_a_bounce(decoy):
    s=state(marker=None);h=s["hero"]
    if decoy=="vy":h["vel"][1]=12.
    elif decoy=="clip":h["anim"]={"clip":"DownSlash"}
    elif decoy=="other_counter":h["cstate_int"]=[8,0,8,8]
    elif decoy=="negative_counter":h["cstate_int"][1]=-1
    elif decoy in {"antic","recovery"}:
        name="downSpikeAntic" if decoy=="antic" else "downSpikeRecovery"
        i=kin.cstate_names().index(name);h["cstate"][i//64]|=1<<(i%64)
    elif decoy=="generic_invuln":h["tm"]={"invuln":1.}
    assert not pogo_marker(s) and not target_pogo_hit(s,7)


def test_marker_and_hit_must_identify_same_target_in_the_supplied_observation():
    s=state(target=8);assert not target_pogo_hit(s,7)
    s=state();s["ev"][0]["d"]={"ent":8,"iid":7,"src":"DownSlash"};assert not target_pogo_hit(s,7)
    s["ev"][0]["d"]={"ent":7,"src":"DownSlash"};assert target_pogo_hit(s,7)
    s["ev"]=[];assert pogo_marker(s) and not target_pogo_hit(s,7)
    assert not target_pogo_hit(state(),None)


@pytest.mark.parametrize("event_frame,since,expected",[(99,99,True),(99,100,False),(101,None,False),(100,100,True),(100,101,False),(None,None,False)])
def test_hit_clock_is_causal_and_press_lower_bound_is_inclusive(event_frame,since,expected):
    s=state();s["ev"][0]["f"]=event_frame
    assert target_pogo_hit(s,7,since=since) is expected


def test_missing_event_frame_uses_known_enclosing_frame_but_unknown_state_frame_does_not():
    s=state();del s["ev"][0]["f"]
    assert target_pogo_hit(s,7,since=100)
    del s["f"];assert not target_pogo_hit(s,7)
    assert not target_pogo_hit(state(),7,since="100")


@pytest.mark.parametrize("bad",[None,{}, {"hero":None},{"hero":{"cstate":None,"cstate_int":None}},
 {"hero":{"cstate":["137438953472"],"cstate_int":[0,"8"]}},
 {"hero":{"cstate":[],"cstate_int":[0,True]}}, {"hero":{"cstate":[],"cstate_int":[0,.5]}}])
def test_unknown_or_malformed_marker_lanes_fail_closed(bad):
    assert not pogo_marker(bad) and not target_pogo_hit(bad,7)


@pytest.mark.parametrize("source,marker",[("Slash",None),("Slash","counter"),("DownSlash",None),
 ("DownSlash","counter"),("Harpoon","counter"),("Harpoon DownSlash","counter")])
def test_default_and_explicit_false_keep_the_exact_legacy_predicate(source,marker):
    s=state(source=source,marker=marker)
    expected=SP.SlamPlay._cs_s_hit(s,SimpleNamespace(iid=7))
    assert g_s_hit(context(s)) is expected
    assert g_s_hit(context(s,False)) is expected


def history(cut=102,strict=False):
    samples=[state(100,source="Slash",marker=None),state(101,marker=None),state(102)]
    rows=[(s["f"],s,(s["f"]-100)/60,s["f"]==100,True) for s in samples]
    return HistView(rows,{},cut,strict_pogo=strict),{"iid":7,"first_tick":100,"ta":0.}


def test_historical_s_hit_uses_opt_in_strict_predicate_and_legacy_is_unchanged():
    old,an=history();strict,_=history(strict=True)
    assert old.first_tick(an,None,"s_hit",None,7)==100
    assert strict.first_tick(an,None,"s_hit",None,7)==102
    assert strict.first_tick(an,None,"s_hit",None,8) is None
    assert strict.first_tick(an,None,"s_hit",None,7,before_f=102) is None
    assert strict.first_tick(an,4,"s_hit",None,7) is None
    assert strict.first_tick(an,3,"s_hit",None,7)==102
    assert old.first_tick(an,None,"ground",None,7)==strict.first_tick(an,None,"ground",None,7)==100
    cut,_=history(cut=101,strict=True)
    assert cut.first_tick(an,None,"s_hit",None,7) is None


def test_separate_unpaired_frames_do_not_make_a_table_bounce():
    hit=state(100,marker=None);marker=state(101);marker["ev"]=[]
    H=HistView([(100,hit,0.,False,True),(101,marker,1/60,False,True)],{},101,strict_pogo=True)
    assert H.first_tick({"iid":7,"first_tick":100,"ta":0.},None,"s_hit",None,7) is None
    assert not target_pogo_hit(hit,7) and not target_pogo_hit(marker,7)
    # The runtime observer may separately retain a press-bound hit and join it
    # to pogo_marker later; this stateless helper deliberately does not do so.


def test_histview_rejects_a_misspelled_truthy_opt_in():
    with pytest.raises(TypeError,match="explicit bool"):HistView([],{},0,strict_pogo="false")
