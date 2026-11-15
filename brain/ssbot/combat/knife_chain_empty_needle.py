"""Measured, unhooked Clawline as a reusable airborne approach primitive.

This only composes HERO2's existing M0 track with the current input prefix.
It neither sends a key nor admits a path. A caller must scan the entire path
against every owner and delayed hazard, and observe real control before using
the shared strike exit. Enemy/wall catches and the unmeasured ram successor
are deliberately outside this primitive. Task 182 seq 387: terrain is judged by
reach (reach_problem) - any row in the needle's ray band, and any slope a swept
body box, ray band or ram box can meet, rejects; a slope out of every region is
ignored (it used to reject the flight wherever it was).
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


RAY_REACH=10.5             # first_ray_body's reach ahead of her box centre (the measured 9.25 u needle + her half width, padded)
RAY_LO,RAY_HI=.50,1.98     # the ray band over her box bottom (first_ray_body)
REACH_M=.02                # margin of a reach region against a terrain row's bounding box (touching counts)


def _ray_band(hb,d):
    x=.5*(hb[0]+hb[2])
    return [min(x,x+d*RAY_REACH),hb[1]+RAY_LO,max(x,x+d*RAY_REACH),hb[1]+RAY_HI]


def _row_boxes(terrain):
    """The bounding boxes [n, 4] of the terrain's horizontal, vertical and slope rows."""
    h=np.asarray(terrain.hseg,float).reshape(-1,3);v=np.asarray(terrain.vseg,float).reshape(-1,3)
    s=np.asarray(terrain.slopes,float).reshape(-1,4)
    return (np.column_stack((h[:,1],h[:,0],h[:,2],h[:,0])),np.column_stack((v[:,0],v[:,1],v[:,0],v[:,2])),
            np.column_stack((np.minimum(s[:,0],s[:,2]),np.minimum(s[:,1],s[:,3]),
                             np.maximum(s[:,0],s[:,2]),np.maximum(s[:,1],s[:,3]))))


def _meets(regions,rows,m=REACH_M):
    """[len(regions)]: some row bounding box meets the region grown by m."""
    r=np.asarray(regions,float).reshape(-1,4)
    if not len(r) or not len(rows):return np.zeros(len(r),bool)
    return ((r[:,None,0]-m<=rows[None,:,2])&(r[:,None,2]+m>=rows[None,:,0])&
            (r[:,None,1]-m<=rows[None,:,3])&(r[:,None,3]+m>=rows[None,:,1])).any(axis=1)


def _sweeps(boxes):
    b=np.asarray(boxes,float)
    return np.column_stack((np.minimum(b[:-1,:2],b[1:,:2]),np.maximum(b[:-1,2:],b[1:,2:])))


def _terrain_rows(terrain,shared=None):
    """(_row_boxes(terrain), all rows stacked, h, v): once per terrain object within one caller's `shared` dict (an admission
    call: one tick, one terrain), else computed."""
    key=('terrain_rows',id(terrain))
    if shared is not None and key in shared and shared[key][0] is terrain:
        return shared[key][1]
    hr,vr,sr=_row_boxes(terrain)
    out=((hr,vr,sr),np.vstack((hr,vr,sr)),np.asarray(terrain.hseg,float).reshape(-1,3),np.asarray(terrain.vseg,float).reshape(-1,3))
    if shared is not None:
        shared[key]=(terrain,out)
    return out


def reach_problem(boxes,rendered_boxes,rays,rams,terrain,shared=None):
    """The terrain a flight could act through that the measured pure branch excludes (None: none). Only rows that are
    certainly out of reach are ignored: the needle's ray band (rays: every frame it can still be thrown, both poses)
    meeting any row - a wall, ledge or slope it could hook; then any slope row meeting a swept body box of either pose
    (boxes / rendered_boxes, frame to frame), a ray band or a ram box (rams). No hook, cling or motion on a slope is
    modelled here: a reachable slope rejects. shared (seq 392, optional): the caller's per-call dict - the rays' two
    answers (any row, any slope) are kept per exact ray bytes, the terrain rows per terrain object; the sweeps and
    rams are always checked here; same reasons, same order."""
    (hr,vr,sr),allrows,_h,_v=_terrain_rows(terrain,shared)
    ra=np.asarray(rays,float).reshape(-1,4)
    key=None if shared is None else ('rays',ra.tobytes())
    if key is not None and key in shared:
        ray_rows,ray_slopes=shared[key]
    else:
        ray_rows=bool(_meets(ra,allrows).any())
        ray_slopes=bool(len(sr)) and bool(len(ra)) and bool(_meets(ra,sr).any())
        if key is not None:
            shared[key]=(ray_rows,ray_slopes)
    if ray_rows:
        return 'empty needle ray meets terrain'
    if len(sr):
        regions=[_sweeps(boxes),_sweeps(rendered_boxes)]+[np.asarray(rams,float).reshape(-1,4)] if len(rams) else \
            [_sweeps(boxes),_sweeps(rendered_boxes)]
        if ray_slopes or _meets(np.vstack(regions),sr).any():
            return 'empty needle sloped terrain in reach'
    return None


def _branch_problem(physical,rendered,bodies,d,throw,params,terrain,catch_shift=0,p=None,shared=None):
    """Why a flight is not the measured pure branch, None when it is: physical / rendered pivots from P (index 0 = P,
    as far as the caller's path goes), the Catch catch_shift frames off the measured one (a derived branch). A different
    FSM successor only; this is not external-hazard admission. The frame checks are the original ones, in the same order
    and with the same reasons; the terrain reach (reach_problem) replaces the former rejection of any slope anywhere.
    p: params.vector() when the caller has it."""
    p=params.vector() if p is None else p;boxes=_boxes(physical,p)
    rendered_boxes=_boxes(rendered,p)
    # The ray can be evaluated before Throw enters. Both physical and rendered
    # poses must be empty for the current observed bodies, through that prefix.
    # shared (seq 392): the answer is kept per exact input (both poses' boxes 0 .. throw, d, throw, the bodies) for the
    # caller's other branches with the same pre-throw segment; the first branch computes it as before (an exception
    # from first_ray_body still raises there, at the same frame).
    key=None
    if shared is not None:
        key=('pre_throw_ray',int(d),int(throw),np.ascontiguousarray(boxes[:throw+1]).tobytes(),
             np.ascontiguousarray(rendered_boxes[:throw+1]).tobytes(),
             tuple((i,None if b is None else tuple(float(v) for v in b)) for i,b in bodies))
    if key is not None and key in shared:
        hooked=shared[key]
    else:
        hooked=any(first_ray_body(hb.tolist(),d,bodies) is not None for j in range(throw+1)
                   for hb in (boxes[j],rendered_boxes[j]))
        if key is not None:
            shared[key]=hooked
    if hooked:
        return 'empty needle would hook an observed body'
    dash=H2.CLAW_DASH_F+throw-H2.CLAW_THROW_F
    catch=H2.CLAW_CATCH_F+throw-H2.CLAW_THROW_F+catch_shift
    # Frame j = 1 .. n-1 (row j-1), all frames at once; the first frame with a problem wins and, within it, the order of
    # the former frame loop: body contact, the ram (dash < j <= catch), a horizontal row, a vertical row (same reasons).
    # Swept boxes also reject a wall/floor catch or physical body contact.
    phys=np.asarray(physical,float)
    sw=_sweeps(boxes)
    bb=np.array([b for _,b in bodies],float).reshape(-1,4)
    js=np.arange(1,len(phys))
    on=(js>dash)&(js<=catch)
    ram=np.column_stack((np.minimum(phys[:-1,0],phys[1:,0])+min(0.,3*d),np.minimum(phys[:-1,1],phys[1:,1])-1.05,
                         np.maximum(phys[:-1,0],phys[1:,0])+max(0.,3*d),np.maximum(phys[:-1,1],phys[1:,1])+.45))
    contact=_strict_any(sw,bb)
    rammed=on&_strict_any(ram,bb)
    _rows,_all,h,v=_terrain_rows(terrain,shared)
    touch=(((sw[:,None,1]<=h[None,:,0])&(h[None,:,0]<=sw[:,None,3])&(sw[:,None,0]<h[None,:,2])&(sw[:,None,2]>h[None,:,1])).any(1)
           |((sw[:,None,0]<=v[None,:,0])&(v[None,:,0]<=sw[:,None,2])&(sw[:,None,1]<v[None,:,2])&(sw[:,None,3]>v[None,:,1])).any(1))
    bad=contact|rammed|touch
    if bad.any():
        k=int(np.argmax(bad))
        return ('empty needle body contact is outside pure branch' if contact[k] else
                'empty needle ram successor is unmeasured' if rammed[k] else 'empty needle touches terrain')
    rays=[_ray_band(hb,d) for j in range(throw+1) for hb in (boxes[j],rendered_boxes[j])]
    return reach_problem(boxes,rendered_boxes,rays,ram[on],terrain,shared=shared)


def _strict_any(a,b):
    """[len(a)]: box a[i] overlaps some box of b (strict, as _overlap)."""
    a=np.asarray(a,float).reshape(-1,4);b=np.asarray(b,float).reshape(-1,4)
    if not len(a) or not len(b):return np.zeros(len(a),bool)
    return ((a[:,None,0]<b[None,:,2])&(a[:,None,2]>b[None,:,0])&(a[:,None,1]<b[None,:,3])&(a[:,None,3]>b[None,:,1])).any(1)


def _pure_branch(physical,rendered,bodies,d,throw,params,terrain):
    """Reject a different FSM successor; this is not external-hazard admission."""
    why=_branch_problem(physical,rendered,bodies,d,throw,params,terrain)
    if why is not None:
        raise NominalUnsupported(why)


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
