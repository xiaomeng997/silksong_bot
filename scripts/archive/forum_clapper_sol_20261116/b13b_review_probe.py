import os,sys,json,copy
os.environ.update(NUMBA_DISABLE_JIT='1',NUMBA_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
sys.dont_write_bytecode=True
import psutil
proc=psutil.Process();proc.cpu_affinity(list(range(24,32)));proc.nice(psutil.IDLE_PRIORITY_CLASS)
sys.path.insert(0,'C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain')
import numpy as np
from dataclasses import replace
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_knife_chain_transfer import transfer_at_gap,fit_pose
T.B13=T.B13B=True
out={'source':'b394463dee3f947b702b7f6abb6a52ca98efff13','affinity':proc.cpu_affinity(),'priority':int(proc.nice()),
     'scope':'Synthetic production-shaped fixture through real propose/render/ChainSim; no helper stubs, no send, game, replay or timing.'}
samples=[];found=None
for mode in (K.M_SPRINT,K.M_DASH):
    for gap in (2.5,3.,3.5,4.,4.5,5.,5.5,6.,7.,8.):
        r,s,sim=transfer_at_gap(gap,mode)
        sim.params=K.hero2(sim.params,on=True)
        sim.start[K.PREV]=int(sim.prefix[0]);sim.start[K.MOVE]=1.
        if mode==K.M_SPRINT:sim.start[K.MODE_T]=.1
        # Idle also lies in the implemented still-target domain; unlike a non-opening caster, the native adapter has no
        # casting side-hold-back which could accidentally repair the wrong row's first key.
        fit_pose(s['ents'][1],state='Idle',t=.05)
        made=T.propose(r,s,0.,sim,8,True,np.zeros((0,6)),set())
        if made is None or made[0] is None:continue
        d,p,path,mask=made;rec=d.run.v.get('b13b')
        samples.append({'mode':int(mode),'gap':gap,'rec':rec,'mask':int(mask)})
        if rec and rec['kind']=='release' and rec['release_meets_F'][0] is not None and rec['release_meets_F'][1] is None:
            found=(r,s,sim,made,mode,gap);break
    if found:break
out['samples']=samples
if found:
    r,s,sim,(d,p,path,mask),mode,gap=found
    original=replace(p,sprint_jump=True)
    row0=T.render(r,original,0,T.B13_ROLL_F,'dash')
    row1=T.render(r,p,0,T.B13_ROLL_F,'dash')
    row2=np.asarray(row1,np.int64)&~(B['L']|B['R'])
    ro=sim.roll(np.asarray([row0,row1,row2],np.int64))
    danger=T.b13_danger(s['ents'][1],len(sim.prefix)+1+T.B13_ROLL_F)
    rowfacts=[]
    for i in range(3):
        takeoff,land=T.b13b_flight(ro.flags[i],sim.off)
        meet=T.b13b_side_meet(ro.box[i],danger,1,land+1)
        rowfacts.append({'row':i,'first_mask':int([row0,row1,row2][i][0]),'takeoff_F':None if takeoff is None else sim.fo+takeoff,
                         'side_meet_F':None if meet is None else sim.fo+meet,'landing_F':sim.fo+land,
                         'meet_box':None if meet is None else ro.box[i,meet].tolist(),
                         'target_box':None if meet is None else danger[meet].tolist()})
    out['counterexample']={'mode':int(mode),'gap':gap,'record':d.run.v['b13b'],'actual_mask':int(mask),
                          'actual_plan_sprint_jump':bool(p.sprint_jump),'side_retained':bool(mask&B['R']),
                          'rowfacts':rowfacts,'input_state':s,'model_start':sim.start.tolist(),'prefix':sim.prefix.tolist()}
print(json.dumps(out,ensure_ascii=False,indent=2))
with open('C:/modeling/silksong_bot/tmp/b13b_review_probe.json','w',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
