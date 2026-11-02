"""Manual airborne cut-in, in the shared knife-chain format; opt-in adapter only.

The table owns the action sequence/entry bounds. This adapter extracts observed
state and calculates one geometric press time; it does not search action trees,
issue inputs, exempt hazards, or count a modeled bounce as observed evidence.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
from numba import njit
from ssbot.knowledge import kinematics as K
from .knife_chain_format import load_chains,MASK_NAMES as B
from .knife_chain_eval import ChainRunner,Prims,Run,X,register_core
from .knife_chain_commitment import MoveInstance
from . import air_chain as AC,pogo_model as PM

TABLE=Path(__file__).with_name("knife_chain_air_v01.json")


def body_box(enemy):
    for col in enemy.get("colliders") or ():
        name=str(col.get("name") or "")
        v=col.get("verts_world")
        if col.get("enabled") and name.startswith("Song Heavy Sentry") and v:
            xy=np.asarray(v,float).reshape(-1,2)
            if len(xy)>=3 and np.isfinite(xy).all():
                return np.r_[xy.min(axis=0),xy.max(axis=0)]
    return None


def complete_hf(state):
    hf=(state.get("act") or {}).get("hf")
    if not isinstance(hf,dict):return False
    for name in ("latched","desired"):
        if type(hf.get(name)) is not int or not 0<=hf[name]<(1<<22):return False
    for name in ("pending","age"):
        a=hf.get(name)
        if not isinstance(a,(list,tuple)) or len(a)!=22 or any(type(v) is not int or v<0 for v in a):return False
    return True


@dataclass(frozen=True)
class AirPlan:
    iid:int
    fa:int
    ta:float
    entry_k:int
    side:int
    release_k:int
    drift_end_k:int
    press_k:int
    contact_k:int
    hp0:int
    origin:int
    contact_frame:int

    @property
    def move(self):return MoveInstance(self.iid,self.fa,"CC_SLAM")
    def variables(self):
        d=asdict(self);d.pop("origin");d.pop("contact_frame");d["cs"]=None
        return d


class AirAnchor:
    def reset(self,runner):pass
    def clock(self,x,name):
        if name!="antic":raise KeyError(name)
        return x.obs.k
    def close(self,x,kind,why):
        x.run.closed=kind;x.run.v["why"]=why;x.R.done.append(x.run);x.R.run=None;x.run=None
    def reopen_wanted(self,why):return False


def load_runner():
    chains=load_chains(TABLE);p=Prims();register_core(p)
    import operator
    ops={">=":operator.ge,"<=":operator.le,">":operator.gt}
    p.guard("cmp")(lambda x,a,op,b:ops[op](a,b))
    p.guard("air_ready")(lambda x:bool(x.obs.ready))
    p.guard("air_target_valid")(lambda x:bool(x.obs.target_valid))
    p.guard("air_bounced")(lambda x:bool(x.obs.bounced))
    p.direction("toward")(lambda x:int(x.v["side"]))
    return ChainRunner(chains,AirAnchor(),p,cfg0=chains["air_strike"].cfg,
        observation_names={"f","F","k","ready","target_valid","bounced","entry_k","gap","height"},
        literal_names={">=","<=",">"})


def entry_context(state,game,runner):
    """Observed fields only. No original-script key-history prerequisite."""
    from .slam_play import clappers,control
    h=state.get("hero") or {};cfg=runner.cfg0
    if not complete_hf(state):return None
    dt=state.get("dt")
    if not isinstance(dt,(int,float)) or not np.isfinite(dt) or dt<=0:return None
    enemies=clappers(state);targets=[e for e in enemies if control(e)[0]=="Slam Antic"]
    if not 1<=len(enemies)<=2 or len(targets)!=1:return None
    e=targets[0];other=[q for q in enemies if q is not e]
    if any(control(q)[0] not in cfg["other_states"] for q in other):return None
    box=body_box(e);hp=h.get("pos");vel=h.get("vel");tm=h.get("tm") or {};hf=state["act"]["hf"]
    if box is None or not hp or not vel or type(e.get("flipX")) is not bool:return None
    vals=[*hp[:2],*vel[:2],tm.get("atk_cd",float("nan")),game]
    if not np.isfinite(vals).all():return None
    clip=str((h.get("anim") or {}).get("clip") or "")
    if clip not in {"Umbrella Float","Umbrella Turn"} or h.get("stunned") or h.get("health",0)<=0:return None
    if tm["atk_cd"]>0 or hf["latched"]&B["A"] or not hf["latched"]&B["J"]:return None
    _,tin=control(e);k=int(round(tin*60.));hx=float(hp[0]);cx=float(e["pos"][0]);face=1 if e["flipX"] else -1
    if (hx-cx)*face<=0:return None
    gap=max(float(box[0])-hx,hx-float(box[2]),0.)-.25
    hb=h.get("box")
    if not hb or len(hb)!=4 or not np.isfinite(hb).all():return None
    height=float(hb[1])-float(box[3]);obs=NS(f=state["f"],F=state["f"]+2,k=k+2,
        entry_k=k,gap=gap,height=height,ready=True,target_valid=True,bounced=False)
    run=Run("air_strike","align",dict(runner.chains["air_strike"].vars));x=X(runner,run,obs)
    if not runner.guard(x,runner.chains["air_strike"].links["align"].entry):return None
    return obs,e,box,1 if cx>hx else -1,float(game)-tin


def render(runner,plan,k0,length):
    """Model-only table interpretation. Proposed Run.sent is not a receipt."""
    draft=runner.fork_empty(AirAnchor());draft.run=Run("air_strike","align",plan.variables())
    draft._nominal_projection_only=True;out=np.zeros(length,np.int64)
    for i in range(length):
        if draft.run is None:break
        obs=NS(f=plan.origin+i,F=plan.origin+i+2,k=k0+2+i,ready=True,target_valid=True,bounced=False,
               entry_k=plan.entry_k,gap=0.,height=0.)
        mask=draft.eval_link(X(draft,draft.run,obs));out[i]=0 if mask is None else mask
    return out


def advance(draft,plan,state,game):
    from .slam_play import control
    e=next((q for q in state.get("ents") or () if q.get("iid")==plan.iid),None)
    st,tin=control(e);valid=(e is not None and not e.get("is_dead") and e.get("hp",0)>0 and st.startswith("Slam")
        and (st!="Slam Antic" or abs((float(game)-tin)-plan.ta)<=3/60.))
    k=int(round((float(game)-plan.ta)*60.))+2
    obs=NS(f=state["f"],F=state["f"]+2,k=k,ready=False,target_valid=valid,bounced=False,
           entry_k=plan.entry_k,gap=0.,height=0.)
    return None if draft.run is None else draft.eval_link(X(draft,draft.run,obs))


def _contact_mask(pos,boxes):
    hit=np.ones(len(pos),bool)
    for poly in (PM.DOWN,PM.DOWN_ALT):
        for face in (-1,1):
            out=np.zeros(len(pos),bool)
            AC._sat(np.ascontiguousarray(poly[:,0]*face),np.ascontiguousarray(poly[:,1]),
                np.ascontiguousarray(pos[:,0]),np.ascontiguousarray(pos[:,1]),np.ascontiguousarray(boxes),out)
            hit &= out
    return hit


def plan_entry(runner,state,game,sim,context=None):
    """One manual recipe and one geometry-derived press; no iterative search.

    Nominal contact only. The receiving adapter MUST check the complete scene
    on this path. Replaying this program never credits a real hit or bounce.
    """
    context=entry_context(state,game,runner) if context is None else context
    if context is None:return None
    if sim.fo!=sim.f or sim.f!=state["f"] or len(sim.prefix)!=1:return None
    hf=state["act"]["hf"]
    if int(sim.prefix[0])&~(B["J"]|B["L"]|B["R"]) or any(hf["pending"]):return None
    if not hf["desired"]&B["J"]:return None
    if np.asarray(sim.start).shape not in ((K.K,),(K.K,1)) or not np.isfinite(sim.start).all():return None
    S=np.asarray(sim.start).reshape(K.K)
    if S[K.MODE]!=K.M_GLIDE or S[K.GROUND]>0:return None
    obs,e,box,direction,ta=context;cfg=runner.cfg0;k=obs.entry_k
    release=int(cfg["release_high_k"] if obs.height>=cfg["height_split"] else cfg["release_low_k"])
    if release<=k+2:return None
    empty=AirPlan(e["iid"],state["f"]-k,ta,k,B["R"] if direction>0 else B["L"],release,
        k+2+int(cfg["drift_frames"]),10000,10000,int(state["hero"]["health"]),state["f"],-1)
    T=64;cmd=render(runner,empty,k,T);coast=sim.roll(cmd[None])
    from .pogo_slam import SlamTimeline
    tl=SlamTimeline.load(K=160)
    ctx=AC.Ctx(e["iid"],float(e["pos"][0]),float(e["pos"][1]),1 if e["flipX"] else -1,
               k,None,float(state["hero"]["pos"][0]),direction,tls=[tl])
    indices=np.arange(coast.pos.shape[1]);boxes=AC._b_boxes(ctx,tl,indices,"root")
    hit=_contact_mask(coast.pos[0],boxes)
    valid=(indices+k>=release+4)&(indices+k<=cfg["max_contact_k"])
    landed=np.cumsum((coast.flags[0]&K.F_GROUND)!=0)>0
    js=np.flatnonzero(hit&valid&~landed)
    if not len(js):return None
    press=max(k+int(js[0])-int(cfg["contact_delay"]),release+1)
    plan=AirPlan(**{**asdict(empty),"press_k":press})
    commands=render(runner,plan,k,T);ro=sim.roll(commands[None]);pi=press-k
    contacts=[]
    for face in (-1,1):
        cc=AC._contacts(ro,np.array([pi]),np.array([face]),ctx,tl,"b")[0]
        if cc<0:return None
        contacts.append(int(cc))
    contact=max(contacts)
    # A common contact frame is required, not one favorable mirror per frame.
    if not _contact_mask(ro.pos[0,contact:contact+1],boxes[contact:contact+1])[0]:return None
    plan=AirPlan(**{**asdict(plan),"contact_k":k+contact,"contact_frame":state["f"]+contact})
    return plan,commands,contact


@njit(cache=True,error_model="numpy")
def _trace_events(start,latched,events,game,frame_time,params,terrain):
    state=start.copy();n=len(latched);states=np.empty((K.K,n+1));boxes=np.empty((n+1,4));pos=np.empty((n+1,2));flags=np.empty(n+1,np.int64);games=np.empty(n+1)
    states[:,0]=state;games[0]=game
    q=_one(state,0,0,0,frame_time,params,terrain);boxes[0]=q[5][0,0];pos[0]=q[1][0,0];flags[0]=q[4][0,0]
    for i in range(n):
        game+=frame_time*state[K.TS]*state[K.WF_S]
        q=_one(state,latched[i],events[i],1,frame_time,params,terrain);state=q[6][:,0].copy()
        states[:,i+1]=state;boxes[i+1]=q[5][0,1];pos[i+1]=q[1][0,1];flags[i+1]=q[4][0,1];games[i+1]=game
    return states,boxes,pos,flags,games


from .knife_chain_step import _one

def model_path(sim,plan,commands,game,*,contact=None):
    from .holdfilter import hold_filter_jit
    from .knife_chain_nominal import NominalPath
    full=np.r_[np.asarray(sim.prefix,np.int64),np.asarray(commands,np.int64)]
    lat,hold=hold_filter_jit(full[None],sim.hold);events=np.zeros(len(full),np.int64)
    if contact is not None:events[int(contact)-1]|=K.EV_POGO
    states,boxes,pos,flags,games=_trace_events(np.asarray(sim.start,float).reshape(K.K),lat[0],events,float(game),
        sim.params.frame_time,sim.params.vector()[None,:],sim.terrain.packed())
    return NominalPath(sim.fo,"air_manual",full,lat[0],states,boxes,pos,flags,flags.copy(),games,hold,
        None,None,0,"bounce" if contact is not None else "short",plan.origin+plan.press_k-plan.entry_k,
        plan.contact_frame if contact is not None else None,
        {"basis":"manual air table; nominal contact, not real evidence","target_iid":plan.iid,
         "move":asdict(plan.move),"input_owner":False,"safety":"unchecked"})


def warm(params):
    """Compile this family's own trace/SAT before combat, never in a first hook."""
    import time
    from .air_chain import ChainSim
    started=time.perf_counter();S=K.initial_state(params,25.,12.,ground=False,mode=K.M_GLIDE)
    S[K.PHASE]=2.;S[K.JHELD]=1.
    hold=K.HoldState.from_hf({"latched":B["J"],"desired":B["J"],"pending":[0]*22,"age":[100]*22})
    sim=ChainSim(S,np.array([B["J"]],np.int64),hold,params,K.Terrain2D.empty(),100,100)
    plan=AirPlan(7,100,0.,0,B["R"],26,18,27,30,7,100,130)
    cmds=render(load_runner(),plan,0,29);parent=model_path(sim,plan,cmds,0.,contact=30)
    from dataclasses import replace
    from .knife_chain_post_actions import ordinary_post
    ordinary_post(replace(parent,stage="commitment"),params,sim.terrain,kind="left_landing")
    _contact_mask(np.zeros((1,2)),np.array([[-1.,-3.,1.,0.]]))
    return {"family":"manual_air","ms":(time.perf_counter()-started)*1000.,
            "trace_signatures":len(_trace_events.signatures),"scope":"compile only; no admission or contact evidence"}
