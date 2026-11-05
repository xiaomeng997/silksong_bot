"""282 finite counterexamples: harmful Antic drift and a bounded, evidence-based hooked-body window."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import knife_chain_face_hook as FH
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_geometry import B2Geometry
from ssbot.combat.knife_chain_commitment import ContactScan,PathContact
from tests.test_knife_chain_face_hook_step import anchor,seen,step_path,scene,rs_stub
from tests.test_knife_chain_face_hook import check


@pytest.mark.parametrize('gap',[2.6,3.0,3.4,3.8])
def test_near_hook_margin_rejects_drift_before_body_off(gap):
    s,sim=scene(gap=gap)
    ok,why,_=check(s,sim)
    assert not ok and 'body margin' in why


def raw_hook_state(f):
    s,_=scene(f=f);s['hero']['hero_accepting_input']=False
    s['hero']['anim']['clip']='Harpoon Dash'
    return s


def own_scan(f,kind='body',state=None,hit=True,control=None):
    a=anchor();P=a['P'];path=step_path(f)
    class Geo:
        def scan(self,q):
            return ContactScan('fixed',f,f+2,(PathContact(f+1,8,kind),PathContact(f+1,9,'body'),
                              PathContact(f+1,8,'delayed'),PathContact(f+1,None,'other')),'fixed all owners')
    v={'hook_press':a}
    if hit:v['hook_hit_f']=P+8
    if control is not None:v['hook_ctrl_f']=control
    return FH.step_scan(Geo(),path,v,seen(P),f,state)


@pytest.mark.parametrize('kind',['body','move'])
def test_proven_hook_window_only_exempts_the_hooked_body(kind):
    P=anchor()['P'];f=P+20
    scan=own_scan(f,kind,state=raw_hook_state(f))
    assert (8,kind) not in {(c.owner_iid,c.kind) for c in scan.contacts}
    assert {(9,'body'),(8,'delayed'),(None,'other')} <= {(c.owner_iid,c.kind) for c in scan.contacts}


@pytest.mark.parametrize('case',['before_dash','no_hit','no_actual_state','after_absolute_cap','control_window_over','armed','unexpected_early_antic'])
def test_hook_body_window_cannot_erase_unproven_or_armed_contacts(case):
    P=anchor()['P'];f=P+20;hit=True;control=None
    if case=='before_dash':f=P+5
    if case=='after_absolute_cap':f=P+65
    if case=='control_window_over':f=P+35;control=P+22
    state=raw_hook_state(f)
    if case=='no_hit':hit=False
    if case=='no_actual_state':state=None
    if case=='armed':state['ents'][1]['colliders'].append({'name':'Slam Collider 1','enabled':True})
    if case=='unexpected_early_antic':state['ents'][1]['fsms'][0].update(state='Slam Antic',t=.83)
    scan=own_scan(f,state=state,hit=hit,control=control)
    assert any(c.owner_iid==8 and c.kind=='body' for c in scan.contacts)


def test_real_body_raster_is_passable_only_in_the_proven_window():
    a=anchor();P=a['P'];f=P+20;path=step_path(f)
    rows=FH.step_paths(path,{'hook_press':a},seen(P),f)
    x0=.5*(path.box[0,0]+path.box[0,2])
    geo=B2Geometry(NS(rs=rs_stub((x0+.7,x0+3.),owner=8)),f,seen(P)['move'],None)
    assert FH.step_scan(geo,path,{'hook_press':a},seen(P),f).contacts
    assert not FH.step_scan(geo,path,{'hook_press':a,'hook_hit_f':P+8},seen(P),f,raw_hook_state(f)).contacts