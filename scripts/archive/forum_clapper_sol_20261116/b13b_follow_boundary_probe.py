import os,sys,json,copy,hashlib
from pathlib import Path
os.environ.update(NUMBA_DISABLE_JIT='1',NUMBA_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
sys.dont_write_bytecode=True
import psutil
proc=psutil.Process();proc.cpu_affinity(list(range(24,32)));proc.nice(psutil.IDLE_PRIORITY_CLASS)
root=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
files=['brain/ssbot/combat/knife_chain_transfer.py','brain/ssbot/combat/knife_chain_air_native.py']
hashes=lambda:{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files}
before=hashes();sys.path.insert(0,str(root/'brain'))
import numpy as np
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_shared_strike_approach import flight
from tests.test_knife_chain_transfer import fit_pose
T.B13=T.B13B=True
r,s,sim=flight(x=30.,y=11.,vx=0.,vy=-.6,target_x=36.5)
s['ents'][0]['flipX']=False;fit_pose(s['ents'][0],state='Idle',t=20/60.,x=33.)
r.run.v.update(b13b_side=0,follow_close=True,source_tail_done=True,air_dash_decided=True)
sim.start[K.ATK_CD]=1.
goal=T.TransferGoal(8,7,990,0.,'BOUNCE',T.MoveInstance(7,940,'CC_SLAM'))
made=T.propose(r,s,0.,sim,8,False,np.zeros((0,6)),set(),goal)
assert made and made[0]
follow={'kind':'middle','F0':1002,'masks':[B['R']]*20,'release_F':1010,'land_f':1030,'goal_x':34.}
fd=T.follow_draft(r,made,s,0.,sim,'middle',follow)
assert fd and fd[0]
# Preserve the actually installed follow-up runner for the next tick, as _seam_follow uses self.runner, not its temporary made.
s2=copy.deepcopy(s);s2['f']=1001
sim2=ChainSim(sim.start.copy(),np.array([B['R']],np.int64),sim.hold,sim.params,sim.terrain,1001,1001)
normal=T.propose(fd[0],s2,1/60.,sim2,8,False,np.zeros((0,6)),set(),goal)
released=T.propose(fd[0],s2,1/60.,sim2,8,False,np.zeros((0,6)),set(),goal,follow_release=True)
clean=copy.deepcopy(fd[0]);clean.run.v.pop('b13b_side',None)
control=T.propose(clean,s2,1/60.,sim2,8,False,np.zeros((0,6)),set(),goal,follow_release=True)
def show(z):
    if z is None or z[0] is None:return None
    return {'link':z[0].run.link,'side':int(z[1].side),'mask':int(z[3]),'b13b_side':z[0].run.v.get('b13b_side'),
            'seam_inner':z[0].run.v.get('seam_inner'),'b13':z[0].run.v.get('b13')}
out={'scope':'Uncommitted source boundary probe, synthetic valid b13b_side=0 and supplied follow route; real follow_draft/propose, not full native decision/send/closed-loop or live HP.',
     'source_hash_before':before,'source_hash_after':hashes(),'affinity':proc.cpu_affinity(),'priority':int(proc.nice()),
     'initial_air':show(made),'follow_draft':show(fd),'ordinary_follow_propose':show(normal),
     'follow_release_on_installed_runner':show(released),'follow_release_without_old_side':show(control)}
assert out['source_hash_before']==out['source_hash_after'],'source changed during probe'
print(json.dumps(out,ensure_ascii=False,indent=2))
Path('C:/modeling/silksong_bot/tmp/b13b_follow_boundary_probe.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
