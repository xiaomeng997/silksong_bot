import os,sys,json
os.environ.update(NUMBA_DISABLE_JIT='1',NUMBA_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
sys.dont_write_bytecode=True
import psutil
proc=psutil.Process();proc.cpu_affinity(list(range(24,32)));proc.nice(psutil.IDLE_PRIORITY_CLASS)
sys.path.insert(0,'C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain')
import numpy as np
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_shared_strike_approach import flight
T.B13=T.B13B=True
out={'source':'b394463dee3f947b702b7f6abb6a52ca98efff13','affinity':proc.cpu_affinity(),'priority':int(proc.nice()),
     'scope':'Bounded real model probe with synthetic production-shaped observed bounce protection; no stubs, no replay/send/game.'}
samples=[]
for vy in (17.4,):
    for y in (7.,):
        r,s,sim=flight(x=33.6,y=y,vx=8.25,vy=vy,target_x=36.5)
        sim.start[K.POGO_OBS]=8.;sim.start[K.ATK_CD]=.3
        sim.start[K.JUMPING]=1.;sim.start[K.JSTEPS]=sim.params.pogo_jump_steps;sim.start[K.JDSTEPS]=sim.params.pogo_jumped_steps;sim.start[K.BOUNCE]=1.
        sim.start[K.PREV]=B['R'];sim.start[K.MOVE]=1.
        s['act']['hf'].update(latched=B['R'],desired=B['R'])
        sim.hold=K.HoldState.from_act(s['act']);sim.prefix[:]=B['R']
        danger=T.b13_danger(s['ents'][1],len(sim.prefix)+1+T.B13_ROLL_F)
        ro=sim.roll(np.full((1,T.B13_ROLL_F),B['R'],np.int64))
        stop=T.b13_landing(ro.flags[0],sim.off)+1
        prot=(ro.flags[0]&K.F_INVULN)!=0
        geom=T.b13_first_meet(ro.box[0],danger,1,stop)
        unsafe=T.b13_first_meet(ro.box[0],danger,1,stop,prot=prot)
        boxes=ro.box[0];n=min(len(boxes),len(danger))
        overlap=(boxes[:n,0]<=danger[:n,2])&(boxes[:n,2]>=danger[:n,0])&(boxes[:n,1]<=danger[:n,3])&(boxes[:n,3]>=danger[:n,1])
        samples.append({'y':y,'vy':vy,'geometric_first':geom,'unsafe_first':unsafe})
        if unsafe is None or geom==unsafe or overlap[unsafe-1]:continue
        made=T.propose(r,s,0.,sim,8,False,np.zeros((0,6)),set())
        if made is None or made[0] is None:continue
        rec=made[0].run.v.get('b13')
        if not rec or not rec.get('inside'):continue
        out['counterexample']={'x':33.6,'y':y,'vx':8.25,'vy':vy,'pogo_obs':8.,'atk_cd':.3,
             'record':rec,'actual_mask':int(made[3]),'geom_first_F':1000+geom,'unsafe_first_F':1000+unsafe,
             'timeline':[{'f':1000+i,'overlap':bool(overlap[i]),'protected':bool(prot[i]),'hero_box':boxes[i].tolist()}
                         for i in range(0,unsafe+2)],'state':s,'model_start':sim.start.tolist()}
        break
    if 'counterexample' in out:break
out['samples']=samples
print(json.dumps({k:v for k,v in out.items() if k!='counterexample'},indent=2))
if 'counterexample' in out:print(json.dumps({k:v for k,v in out['counterexample'].items() if k not in ('timeline','state','model_start')},indent=2))
with open('C:/modeling/silksong_bot/tmp/b13b_inside_probe.json','w',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
