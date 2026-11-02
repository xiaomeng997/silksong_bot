"""Manual rune-transfer approach for the existing B2 owner; no input transport.

The table approaches the selected second Clapper's head. Current STATE and the
existing bomb forecast choose one jump clock; every proposal checks its modeled
approach path with ALL target/foreign/delayed layers. No future enemy STATE or
old recording attack time is supplied. An observed slam can cut into air_direct.
"""
from dataclasses import dataclass,asdict,replace
from types import SimpleNamespace as NS
import math
import numpy as np
from ssbot.knowledge import kinematics as K
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_eval import Run,X
from .knife_chain_commitment import MoveInstance
from .knife_chain_air import body_box,complete_hf,AirAnchor,model_path
from .slam_play import clappers,control

PROGRAM="rune_transfer"


@dataclass(frozen=True)
class TransferPlan:
    iid:int
    caster:int
    cast_fa:int
    fa:int
    ta:float
    side:int
    dash_k:int
    jump_k:int
    jump_until:int
    sprint_jump:bool
    origin:int
    entry_k:int
    press_k:object=None
    contact_frame:object=None

    @property
    def move(self):return MoveInstance(self.iid,self.fa,"RUNE_TRANSFER")
    def variables(self):
        return {k:v for k,v in asdict(self).items() if k not in {"origin","entry_k","press_k","contact_frame"}}|{"cs":None}


@dataclass(frozen=True)
class TransferGoal:
    target:int
    caster:int
    cast_fa:int


def observe_goal(state,previous,cfg,finished):
    """A visible antic selects the destination; it is not a Run or key commitment."""
    es=clappers(state);h=state.get("hero") or {};f=state.get("f")
    if len(es)!=2 or type(f) is not int or h.get("health",0)<=0:return None
    byid={e["iid"]:e for e in es}
    casting=[e for e in es if control(e)[0]=="Spell Antic" and control(e)[1]<=cfg["entry_cast_s"]]
    if len(casting)==1:
        caster=casting[0];target=next(e for e in es if e is not caster)
        fa=max(0,f-int(round(control(caster)[1]*60.)))
        fresh=TransferGoal(target["iid"],caster["iid"],fa)
        if ((caster["iid"],fa) not in finished and control(target)[0] in cfg["target_states"] and
                (previous is None or fresh!=previous)):return fresh
    if previous is not None:
        if (previous.target in byid and previous.caster in byid and
                0<=f-previous.cast_fa<=cfg["max_frames"]):
            box=body_box(byid[previous.target]);hb=h.get("box");pos=h.get("pos")
            if (box is not None and hb and pos and box[0]<=pos[0]<=box[2] and
                    hb[1]>=box[3]+cfg["head_clearance"]):return None
            return previous
    return None


def visible(state,cfg=None):
    """Cheap candidate availability; actual focus/ground/HF are checked later."""
    h=state.get("hero") or {};box=h.get("box") or []
    es=clappers(state)
    return bool(len(es)==2 and len(box)==4 and type(box[1]) in (int,float) and math.isfinite(box[1]) and box[1]<3.2 and
        h.get("hero_accepting_input") is True and any(control(e)[0]=="Spell Antic" and
        control(e)[1]<=(cfg or {}).get("entry_cast_s",.2) for e in es))


def _observation(plan,state,game,body,ground,clearance):
    h=state["hero"];k=int(round((game-plan.ta)*60.))
    overhead=(body[0]<=h["pos"][0]<=body[2] and h["box"][1]>=body[3]+clearance)
    return NS(f=state["f"],F=state["f"]+2,k=k+2,target_valid=True,ground=bool(ground),
        overhead=overhead,entry_k=0,gap=0.,height=0.,ready=False,bounced=False,
        program=PROGRAM,jump_held=False)


def render(runner,plan,k0,length,link="walk"):
    draft=runner.fork_empty(AirAnchor());draft.run=Run(PROGRAM,link,plan.variables())
    draft._nominal_projection_only=True;out=np.zeros(length,np.int64)
    for i in range(length):
        obs=NS(f=plan.origin+i,F=plan.origin+i+2,k=k0+i+2,target_valid=True,
            ground=(link!="air" and k0+i+2 < plan.jump_k+(int(runner.chains[PROGRAM].cfg["jump_antic_frames"]) if plan.sprint_jump else 1)),overhead=False)
        m=draft.eval_link(X(draft,draft.run,obs))
        if m is None:break
        out[i]=m
    return out


def path_problem(path,hold):
    modes=path.states[K.MODE]
    if not np.isfinite(modes).all() or np.any(modes==K.M_GLIDE):return "transfer unexpectedly opens umbrella"
    jump=(path.latched&B["J"])!=0;prev=np.r_[bool(hold.latched[0,0]),jump[:-1]]
    if np.any((jump&~prev)&(path.states[K.GROUND,:-1]<=0)):return "transfer represses jump in air"
    return None


def propose(runner,state,game,sim,target,ground,bombs,finished,goal=None):
    """One manual recipe, two hero rollouts; no action-tree or height search."""
    h=state.get("hero") or {};es=clappers(state);active=runner.run if runner.run is not None and runner.run.chain==PROGRAM else None
    if len(es)!=2 or target is None or not complete_hf(state):return None
    enemy=next((e for e in es if e["iid"]==target),None)
    if enemy is None:return None
    other=next(e for e in es if e is not enemy);st,tin=control(other);target_state,_=control(enemy)
    cfg=runner.chains[PROGRAM].cfg;body=body_box(enemy)
    if body is None or target_state not in cfg["target_states"] or h.get("health",0)<=0 or h.get("stunned"):return None
    if sim.fo!=sim.f or sim.f!=state["f"] or len(sim.prefix)!=1:return None
    if int(sim.prefix[0])&~(B["L"]|B["R"]|B["J"]|B["DASH"]):return None
    hp=h.get("pos");vel=h.get("vel")
    if not isinstance(hp,(list,tuple)) or not isinstance(vel,(list,tuple)) or min(len(hp),len(vel))<2:return None
    if np.asarray(sim.start).shape not in ((K.K,),(K.K,1)) or not np.isfinite(sim.start).all() or not np.isfinite([game,*hp[:2],*vel[:2]]).all():return None
    cd=(h.get("tm") or {}).get("dash_cd")
    if type(cd) not in (int,float) or not math.isfinite(cd):return None
    if active is None:
        if not ground or h.get("hero_accepting_input") is not True:return None
        observed=(goal is not None and goal.target==target and goal.caster==other["iid"] and
                  0<=state["f"]-goal.cast_fa<=cfg["max_frames"])
        if not observed and (st!="Spell Antic" or tin>cfg["entry_cast_s"]):return None
        if int(sim.prefix[0])&B["J"] or state["act"]["hf"]["latched"]&B["J"]:return None
        cast_fa=goal.cast_fa if observed else max(0,state["f"]-int(round(tin*60.)))
        if (other["iid"],cast_fa) in finished:return None
        p=TransferPlan(target,other["iid"],cast_fa,state["f"],game,
            B["R"] if enemy["pos"][0]>h["pos"][0] else B["L"],2+int(math.ceil(max(0.,cd)*60.)),10000,10000,False,state["f"],0)
        link="walk"
    else:
        if active.v["iid"]!=target:return None
        p=TransferPlan(**{k:active.v[k] for k in TransferPlan.__dataclass_fields__ if k in active.v},origin=state["f"],entry_k=int(round((game-active.v["ta"])*60.)))
        link=active.link
    k=p.entry_k;T=int(cfg["lookahead_frames"])
    if link in {"walk","dash"} and ground:
        coast=render(runner,replace(p,jump_k=10000,jump_until=10000),k,T,link);ro=sim.roll(coast[None])
        idx=np.arange(ro.pos.shape[1]);near=np.flatnonzero(np.abs(ro.pos[0,:,0]-enemy["pos"][0])<=cfg["jump_distance"])
        start=int(near[0]) if len(near) else 10000
        if bombs is not None and len(bombs):
            from .rune_bombs import occupied
            centers=.5*(ro.box[0,:,:2]+ro.box[0,:,2:]);bad=np.flatnonzero(occupied(bombs,centers[:,0],centers[:,1],idx,.15))
            if len(bad):start=min(start,max(0,int(bad[0])-int(cfg["jump_lead_frames"])))
        jump=max(k+2,k+start)
        ji=min(len(idx)-1,max(0,jump-k));sprint=bool(ro.mode[0,ji] in (K.M_DASH,K.M_SPRINT))
        # An outside ground-jump already queued ahead of us is a normal jump,
        # not permission to press DASH as it becomes airborne.
        if (int(sim.prefix[0])|state["act"]["hf"]["latched"])&B["J"]:sprint=False
        if jump<=k+2:
            clip=str((h.get("anim") or {}).get("clip") or "")
            sprint=sprint and clip in {"Dash","Dash To Run","Sprint","Land To Sprint"} and abs(h["vel"][0])>=16.5
        p=replace(p,jump_k=jump,jump_until=jump+int(cfg["jump_hold_frames"]),sprint_jump=sprint)
    elif not ground:
        if link in {"walk","dash"}:p=replace(p,jump_until=k)  # an outside jump is not ours to re-press
        elif not (state["act"]["hf"]["latched"]&B["J"] and int(sim.prefix[0])&B["J"]):p=replace(p,jump_until=k)
        link="air"
    draft=runner.fork_empty(AirAnchor());draft.run=Run(PROGRAM,link,p.variables())
    obs=_observation(p,state,game,body,ground,cfg["head_clearance"])
    mask=draft.eval_link(X(draft,draft.run,obs))
    if mask is None:return (None,p,None,None)
    commands=render(runner,p,k,T,draft.run.link);path=model_path(sim,p,commands[:T-1],game)
    # Handback is an observed overhead state. Stop the nominal check at that
    # decision, rather than checking a made-up fall after the program returns.
    overhead=(path.pos[:,0]>=body[0])&(path.pos[:,0]<=body[2])&(path.box[:,1]>=body[3]+cfg["head_clearance"])
    hits=np.flatnonzero(overhead & (np.arange(len(overhead))>=2));end=int(hits[0]) if len(hits) else len(path.commands)
    if end<len(path.commands):path=model_path(sim,p,commands[:end-1],game)
    path=replace(path,stage="approach",assumptions={**path.assumptions,"basis":"manual rune transfer; future target position held nominally, actual move continuously observed","next_decision":"observed overhead or observed slam; no target exemption"})
    if path_problem(path,sim.hold):return None
    return draft,p,path,int(mask)
