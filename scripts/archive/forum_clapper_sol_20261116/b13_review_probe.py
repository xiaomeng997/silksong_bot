import os, sys, json, copy
os.environ.update(NUMBA_DISABLE_JIT='1', NUMBA_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
sys.dont_write_bytecode = True
import psutil
p = psutil.Process(); p.cpu_affinity(list(range(24, 32))); p.nice(psutil.IDLE_PRIORITY_CLASS)
sys.path.insert(0, 'C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain')
import numpy as np
from types import SimpleNamespace as NS
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_eval import X
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.knowledge import kinematics as K
from tests.test_shared_strike_approach import flight
T.B13=True
out={'source':'0e3d65936ae195ad1da4c64f48344461bd958d6f','affinity':p.cpu_affinity(),'priority':int(p.nice()),
     'scope':'Small synthetic production-shaped state sequence through transfer.propose; no replay, send, game or performance result.'}
r,s,sim=flight(x=34.15,y=9.2,vx=0.,vy=-4.,target_x=36.5)
sim.start[K.ATK_CD]=1.
made=T.propose(r,s,0.,sim,8,False,np.zeros((0,6)),set())
assert made is not None and made[0] is not None
d,plan,path,mask=made
out['guard']={'link':d.run.link,'mask':int(mask),'b13':d.run.v.get('b13'),'steer':d.run.v.get('b13_steer')}
assert d.run.link=='air' and d.run.v.get('b13_steer')==B['L']
# The same outside-air-entry Run lands outside the target's 0.5 u ground margin.
s2=copy.deepcopy(s); s2['f']=1012
s2['hero'].update(pos=[32.5,4.568],box=[32.25,3.015,32.75,5.1],vel=[0.,0.])
s2['act']['hf'].update(latched=0,desired=0)
S=K.initial_state(sim.params,32.5,4.568,vx=0.,ground=True); S[K.ATK_CD]=.8
sim2=ChainSim(S,np.array([0],np.int64),K.HoldState.from_act(s2['act']),sim.params,sim.terrain,1012,1012)
land=T.propose(d,s2,12/60.,sim2,8,True,np.zeros((0,6)),set())
assert land is not None and land[0] is not None
out['landing']={'link':land[0].run.link,'mask':int(land[3]),'steer':land[0].run.v.get('b13_steer'),
                'air_entry':land[0].run.v.get('air_entry')}
# A current observed airborne frame after this new jump; J has been sent and latched.
s3=copy.deepcopy(s2); s3['f']=1016
s3['hero'].update(pos=[32.8,5.2],box=[32.55,3.647,33.05,5.732],vel=[8.25,17.4])
s3['act']['hf'].update(latched=B['R']|B['J'],desired=B['R']|B['J'])
S3=K.initial_state(sim.params,32.8,5.2,vx=8.25,vy=17.4,ground=False); S3[K.ATK_CD]=.7; S3[K.JHELD]=1.
S3[K.PREV]=B['R']|B['J']; S3[K.JUMPING]=1.; S3[K.JSTEPS]=2.
sim3=ChainSim(S3,np.array([B['R']|B['J']],np.int64),K.HoldState.from_act(s3['act']),sim.params,sim.terrain,1016,1016)
again=T.propose(land[0],s3,16/60.,sim3,8,False,np.zeros((0,6)),set())
assert again is not None and again[0] is not None
out['next_air']={'link':again[0].run.link,'mask':int(again[3]),'steer':again[0].run.v.get('b13_steer'),
                 'side':int(again[0].run.v['side']),'b13':again[0].run.v.get('b13')}
clean=copy.deepcopy(land[0]); clean.run.v.pop('b13_steer',None)
fixed=T.propose(clean,s3,16/60.,sim3,8,False,np.zeros((0,6)),set())
out['next_air_without_stale_steer']={'link':fixed[0].run.link,'mask':int(fixed[3]),'steer':fixed[0].run.v.get('b13_steer')}
# Exact production route key helper on the guard's own returned air draft.
n=NativeManualAirChain.__new__(NativeManualAirChain)
route=n._route_keys(plan,d,int(mask),'air',1000)
actual=[]
for k in range(2,8):
    actual.append(T.air_approach_keys(X(d,d.run,NS(k=k))))
out['route_keys']={'plan_side':int(plan.side),'steer':d.run.v.get('b13_steer'),
                   'route_first_six':[int(v) for v in route[:6]],'actual_first_six':[int(v) for v in actual]}
print(json.dumps(out,ensure_ascii=False,indent=2))
with open('C:/modeling/silksong_bot/tmp/b13_review_probe.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2)
