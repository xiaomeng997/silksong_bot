"""A previous swing must not witness a new transfer knife or its acceptance."""
from types import SimpleNamespace as NS
from copy import deepcopy
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_transfer import press_now_row
from tests.test_knife_chain_b2 import params,terrain,native_committed,next_state

@pytest.mark.parametrize('old_clip',['DownSlash','DownSlashAlt'])
def test_old_downslash_clip_and_running_timers_do_not_accept_a_new_press(params,terrain,old_clip):
 n=native_committed(params,terrain)
 a=next_state(1001);a['hero']['anim']['clip']=old_clip;a['hero']['tm'].update(atk_cd=.20,atk_t=.0833)
 n.observe(a)
 z=next_state(1002);z['hero']['anim']['clip']=old_clip;z['hero']['tm'].update(atk_cd=.1833,atk_t=.10)
 n.observe(z)
 assert n._accepted is None and n._hit is None and n.post_context is None

@pytest.mark.parametrize('old_clip',['Recoil Twirl','DownSlash'])
def test_actual_new_downslash_start_is_accepted_after_own_press(params,terrain,old_clip):
 n=native_committed(params,terrain)
 a=next_state(1001);a['hero']['anim']['clip']=old_clip;a['hero']['tm'].update(atk_cd=.0,atk_t=.23)
 n.observe(a)
 z=next_state(1002);z['hero']['anim']['clip']='DownSlash';z['hero']['tm'].update(atk_cd=.2833,atk_t=0.)
 n.observe(z)
 assert n._accepted==1002 and n._hit is None and n.post_context is None

@pytest.mark.parametrize('column',[False,True])
@pytest.mark.parametrize('cooldown,fresh,allowed',[(.1833,False,False),(0.,False,False),(0.,True,True)])
def test_press_now_requires_its_own_model_swing_not_inherited_attacking(params,monkeypatch,cooldown,fresh,allowed,column):
 from ssbot.combat import pogo_model as PM
 S=np.zeros(K.K);S[K.ATK_CD]=cooldown;S[K.ATK_T]=.1
 if column:S=S.reshape(K.K,1)
 flags=np.full((1,42),K.F_ATTACKING,dtype=np.int64)
 if fresh:flags[:,:3]=0
 ro=NS(flags=flags,pos=np.zeros((1,42,2)),vel=np.zeros((1,42,2)))
 sim=NS(start=S,prefix=np.zeros(1,dtype=np.int64),params=params,fo=3064,roll=lambda *a:ro)
 monkeypatch.setattr(PM,'meets',lambda *a:True)
 row=press_now_row(sim,np.array([0.,0.,2.,4.]),3066,0,B['R'])
 assert (row is not None)==allowed
