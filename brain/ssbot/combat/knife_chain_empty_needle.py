"""Measured, unhooked Clawline as a reusable airborne approach primitive.

This only composes HERO2's existing M0 track with the current input prefix.
It neither sends a key nor admits a path. A caller must scan the entire path
against every owner and delayed hazard, and observe real control before using
the shared strike exit. Enemy/wall catches and the unmeasured ram successor
are deliberately outside this primitive.
"""
from dataclasses import dataclass
import math
import numpy as np

from ssbot.knowledge import kinematics as K, hero2 as H2
from .knife_chain_air import _trace_events
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_hook_target import first_ray_body
from .knife_chain_nominal import NominalPath, NominalUnsupported
from .holdfilter import hold_filter_jit


@dataclass(frozen=True)
class EmptyNeedle:
    path: NominalPath
    activation_frame: int
    control_frame: int
    control_state: np.ndarray
    direction: int
    throw_frames: int
    activation_delay: int


def command(frame, press, direction):
    """One absolute CLAW pulse, face through the latest throw, then release."""
    if type(frame) is not int or type(press) is not int or direction not in (-1,1):
        raise ValueError("invalid empty-needle command clock/direction")
    side=B['R'] if direction>0 else B['L']
    return (side if frame<=press+H2.CLAW_THROW_F+2 else 0)|(B['CLAW'] if frame==press else 0)


def _lattice(S,params,n):
    from ssbot.map2.strike import steps_of
    dt=float(params.frame_time);fdt=float(params.fdt);a=float(S[K.ALPHA])
    # This is the measured 60 Hz / 50 Hz clock, not arbitrary time dilation.
    if (not math.isclose(dt,1/60.,abs_tol=1e-6) or not math.isclose(fdt,H2.FDT,abs_tol=1e-8)
            or S[K.TS]!=1. or S[K.WF_S]!=1. or not 0<=a<1.):
        raise NominalUnsupported('empty needle clock outside measured lattice')
    counts=[int(math.floor(a+j*dt/fdt+1e-8)-math.floor(a+(j-1)*dt/fdt+1e-8)) for j in range(1,7)]
    phases=[p for p in range(6) if [steps_of(j,p) for j in range(1,7)]==counts]
    if not phases:raise NominalUnsupported('empty needle clock outside measured lattice')
    return np.array([steps_of(j,phases[0]) for j in range(1,n+1)],np.int64)


def _render(S,physical,steps,params):
    # Identical q/s/alpha interpolation to _nominal_hook, including no-step
    # frames. Picking the safer physical endpoint would change the checked path.
    moved=np.r_[False,np.asarray(steps[:len(physical)-1],bool)]
    latest=np.maximum.accumulate(np.where(moved,np.arange(len(physical)),0))
    q=physical[np.maximum(latest-1,0)].copy();v=physical[latest].copy()
    q[latest==0]=S[[K.QX,K.QY]];v[latest==0]=S[[K.SX,K.SY]]
    alpha=np.mod(S[K.ALPHA]+np.arange(len(physical))*params.frame_time/params.fdt,1.)
    return q*(1-alpha[:,None])+v*alpha[:,None]


def _boxes(pos,p):
    return np.column_stack((pos[:,0]-p[K.P_HW],pos[:,1]-p[K.P_FOOT],
                            pos[:,0]+p[K.P_HW],pos[:,1]+p[K.P_HEAD]))


def _overlap(a,b):
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]


def _pure_branch(physical,rendered,bodies,d,throw,params,terrain):
    """Reject a different FSM successor; this is not external-hazard admission."""
    p=params.vector();boxes=_boxes(physical,p)
    rendered_boxes=_boxes(rendered,p)
    # The ray can be evaluated before Throw enters. Both physical and rendered
    # poses must be empty for the current observed bodies, through that prefix.
    for j in range(throw+1):
        for hb in (boxes[j],rendered_boxes[j]):
            if first_ray_body(hb.tolist(),d,bodies) is not None:
                raise NominalUnsupported('empty needle would hook an observed body')
    dash=H2.CLAW_DASH_F+throw-H2.CLAW_THROW_F
    catch=H2.CLAW_CATCH_F+throw-H2.CLAW_THROW_F
    for j in range(1,len(physical)):
        # Swept boxes also reject a wall/floor catch or physical body contact.
        sweep=np.r_[np.minimum(boxes[j-1,:2],boxes[j,:2]),np.maximum(boxes[j-1,2:],boxes[j,2:])]
        if any(_overlap(sweep,b) for _,b in bodies):
            raise NominalUnsupported('empty needle body contact is outside pure branch')
        if dash<j<=catch:
            x0=min(physical[j-1,0],physical[j,0]);x1=max(physical[j-1,0],physical[j,0])
            ram=[x0+min(0.,3*d),min(physical[j-1,1],physical[j,1])-1.05,
                 x1+max(0.,3*d),max(physical[j-1,1],physical[j,1])+.45]
            if any(_overlap(ram,b) for _,b in bodies):
                raise NominalUnsupported('empty needle ram successor is unmeasured')
        for y,x0,x1 in terrain.hseg:
            if sweep[1]<=y<=sweep[3] and sweep[0]<x1 and sweep[2]>x0:
                raise NominalUnsupported('empty needle touches terrain')
        for x,y0,y1 in terrain.vseg:
            if sweep[0]<=x<=sweep[2] and sweep[1]<y1 and sweep[3]>y0:
                raise NominalUnsupported('empty needle touches terrain')
    if len(terrain.slopes):raise NominalUnsupported('empty needle sloped terrain unsupported')


def _control(S,track,d,params):
    """Existing env_jit.claw_control / HarpoonDashEnd state, without a bounce.

    No extra-velocity composition is modeled here; entry rejects an existing
    SHUT/XVX. The remaining catch velocity becomes XVX with Decay 4 / second.
    """
    out=S.copy();elapsed=track.ctrl*params.frame_time
    for name in ('ATK_CD','DASH_CD','GL_CD','CLING_CD','INV_T'):
        i=getattr(K,name);out[i]=max(0.,out[i]-elapsed) if out[i]>0 else out[i]
    values={'MODE':K.M_NORMAL,'MODE_T':0.,'PHASE':0.,'VX':0.,'VY':0.,'GS':1.,'PREV_GS':1.,
            'JUMPING':0.,'JSTEPS':0.,'BOUNCE':-1.,'ATTACKING':0.,'AIRHANG':1.,'GROUND':0.,
            'DASH_T':0.,'DQ':-1.,'AQ':-1.,'JQ':-1.,'QQ':-1.,'JBUF':0.,'FALL_T':0.,'HARD':0.,
            'MOVE':0.,'JHELD':0.,'PREV':0.,'DS_REC':-1.,'RDIR':0.,'LEDGE':0.,'SHUT':0.,
            'TOUCH':0.,'LANDQ':0.,'FACE':d,'XVX':d*abs(track.vx[-1]),'XVXD':4.}
    for name,value in values.items():out[getattr(K,name)]=value
    x=track.x[-1];y=track.bb[-1]+params.vector()[K.P_FOOT]
    for i,j in ((K.PX,K.PY),(K.QX,K.QY),(K.SX,K.SY),(K.RX0,K.RY0)):out[i],out[j]=x,y
    out[K.ALPHA]=(S[K.ALPHA]+elapsed/params.fdt)%1.
    out[K.SILK]=S[K.SILK]-1.
    return out


def compile_empty(sim,game,bodies,direction,*,throw_frames=9,activation_delay=0):
    """One fixed empty-needle flight; P is the modeled actual latch frame.

    activation_delay 0..2 is the existing permitted late-application envelope,
    never a command retiming. Callers must check every variant, not select a
    favorable one. No future recording state, hit protection, or pogo is used.
    Actual CanHarpoon/silk/input readiness still belong to the runtime caller.
    """
    if (type(direction) is not int or direction not in (-1,1) or type(throw_frames) is not int
            or throw_frames not in (8,9) or type(activation_delay) is not int or activation_delay not in (0,1,2)):
        raise NominalUnsupported('invalid empty needle fixed variant')
    S=np.asarray(sim.start,float).reshape(K.K)
    if (sim.fo!=sim.f or len(sim.prefix)!=1 or S[K.GROUND]>0 or not np.isfinite(S).all() or not math.isfinite(game)
            or not int(sim.params.vector()[K.P_H2])&K.H2_CLAW_SPR):
        raise NominalUnsupported('unknown empty needle current model')
    bodies=tuple((iid,None if box is None else tuple(float(v) for v in box)) for iid,box in bodies)
    press=sim.f+2;P=press+activation_delay;n=H2.CLAW_CTRL_F+throw_frames-H2.CLAW_THROW_F
    commands=np.array([*sim.prefix,*[command(f,press,direction) for f in range(press,P+n+1)]],np.int64)
    lat,hold=hold_filter_jit(commands[None],sim.hold)
    edge=sim.off-1
    if (int(sim.prefix[0])&B['CLAW'] or sim.hold.latched[0,B['CLAW'].bit_length()-1]
            or not lat[0,edge]&B['CLAW'] or (np.count_nonzero(lat[0]&B['CLAW'])>2)):
        raise NominalUnsupported('empty needle is not a fresh executable CLAW pulse')
    lead=P-sim.fo
    states,boxes,pos,flags,games=_trace_events(S,lat[0,:lead],np.zeros(lead,np.int64),float(game),
        sim.params.frame_time,sim.params.vector()[None,:],sim.terrain.packed())
    SP=states[:,-1].copy();p=sim.params.vector();mode=int(SP[K.MODE])
    if (SP[K.GROUND]>0 or mode not in (K.M_NORMAL,K.M_SPRINT) or
            (mode==K.M_SPRINT and SP[K.PHASE]>1.) or SP[K.SHUT]!=0 or SP[K.XVX]!=0
            or SP[K.SILK]<1 or not -19.6<=SP[K.VY]<=17.4):
        raise NominalUnsupported('empty needle entry outside measured pure branch')
    steps=_lattice(SP,sim.params,n)
    tr=H2.claw_unhooked(SP[K.PX],SP[K.PY]-p[K.P_FOOT],SP[K.VX],SP[K.VY],direction,steps,throw_frames)
    physical=np.column_stack((tr.x,tr.bb+p[K.P_FOOT]));rendered=_render(SP,physical,steps,sim.params)
    _pure_branch(physical,rendered,bodies,direction,throw_frames,sim.params,sim.terrain)
    end=_control(SP,tr,direction,sim.params)
    # Frozen-state lanes are geometry/clock data, never runnable normal-control
    # successors. Only control_state below is a valid post-flight K state.
    frozen=np.repeat(SP[:,None],n,axis=1)
    frozen[K.PX]=physical[1:,0];frozen[K.PY]=physical[1:,1]
    frozen[K.VX]=tr.vx[1:];frozen[K.VY]=tr.vy[1:]
    frozen[K.GROUND]=frozen[K.ATTACKING]=frozen[K.INV_T]=0.
    frozen[:,-1]=end
    states=np.column_stack((states,frozen));pos=np.vstack((pos,rendered[1:]))
    boxes=np.vstack((boxes,_boxes(rendered[1:],p)))
    flags=np.r_[flags,np.zeros(n,np.int64)];checks=flags.copy();checks[lead:]=0
    games=np.r_[games,games[-1]+np.arange(1,n+1)*sim.params.frame_time]
    path=NominalPath(sim.fo,'empty_needle',commands,lat[0],states,boxes,pos,flags,checks,games,hold,
        None,None,0,'control',None,None,
        {'basis':'existing measured HERO2 M0 unhooked track; pure branch only','safety':'unchecked',
         'actual_control_required':True,'activation_frame':P,'throw_frames':throw_frames,
         'activation_delay':activation_delay,'no_future_protection':True,'no_pogo':True})
    for a in (commands,lat,states,boxes,pos,flags,checks,games,end):a.flags.writeable=False
    return EmptyNeedle(path,P,P+n,end,direction,throw_frames,activation_delay)
