"""A crouched Antic snapshot cannot certify clearance when the body stands."""
import pytest
from types import SimpleNamespace as NS
from ssbot.knowledge import kinematics as K
from ssbot.combat import knife_chain_transfer as T
from tests.test_transfer_hit244 import setup


def place(s,sim,antic_k,hero_py,face):
 e=s['ents'][1];e['flipX']=face;e['fsms'][0]['t']=antic_k/60
 for c in e['colliders']:
  pts=c['verts_world'];top=max(pts[1::2]);pts[1::2]=[6.19 if y==top and antic_k<5 else y for y in pts[1::2]]
  if not face:pts[::2]=[2*e['pos'][0]-x for x in pts[::2]]
 sim.start[K.PY]=hero_py;s['hero']['pos'][1]=hero_py
 s['hero']['box']=[37.75,hero_py-1.553,38.25,hero_py+.526]


@pytest.mark.parametrize('antic_k',[3,4,6])
@pytest.mark.parametrize('face',[False,True])
def test_standing_pose_overlap_rejects_even_from_an_early_crouched_snapshot(monkeypatch,antic_k,face):
 n,s,sim,fc,scans=setup(monkeypatch,'body_padding_after_hit');place(s,sim,antic_k,8.,face)
 assert n._transfer_offer(s,0.,sim,fc,NS(target=8),False) is None
 assert n._hit is None and n.post_context is None


@pytest.mark.parametrize('antic_k',[3,4])
@pytest.mark.parametrize('face',[False,True])
def test_early_clear_knife_still_uses_the_same_conditional_branch(monkeypatch,antic_k,face):
 n,s,sim,fc,scans=setup(monkeypatch,'body_padding_after_hit');place(s,sim,antic_k,9.253,face)
 offer=n._transfer_offer(s,0.,sim,fc,NS(target=8),False)
 assert offer is not None and offer.details['conditional_hit_check']
 assert n._hit is None and n.post_context is None


@pytest.mark.parametrize('unknown',['face','position','nonfinite_position'])
def test_unknown_pose_transform_never_invents_a_world_bound(monkeypatch,unknown):
 n,s,sim,fc,scans=setup(monkeypatch,'body_padding_after_hit');e=s['ents'][1]
 if unknown=='face':e['flipX']=None
 if unknown=='position':e['pos']=None
 if unknown=='nonfinite_position':e['pos']=[float('nan'),7.45]
 assert T.stationary_antic_body_for_hit_check(s,8,1042) is None
