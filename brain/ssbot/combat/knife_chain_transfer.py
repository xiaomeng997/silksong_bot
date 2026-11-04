"""Manual dash/sprint/jump/stomp table for the existing B2 input owner.

The observed distance selects the jump. A current downslash row, with at most
two horizontal braking fallbacks, is tested in the air. One optional air dash
uses the same Run. Model contact never credits a real hit. Runtime checks only the
current external step, like the manual vault, rather than a made-up full fall.
"""
from dataclasses import dataclass,asdict,replace
from types import SimpleNamespace as NS
import math
from functools import lru_cache
import numpy as np
from ssbot.knowledge import kinematics as K
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_eval import Run,X
from .knife_chain_commitment import MoveInstance
from .knife_chain_air import body_box,complete_hf,AirAnchor,model_path
from .slam_play import clappers,control

PROGRAM="rune_transfer"
AIR_ATTACK_STATES=frozenset({"Slam Antic","Slam 0","Slam 1","Slam Effects?","Slam 2"})


@lru_cache(maxsize=1)
def slam_tail_frames():
    """Family-specific empirical frame maxima, not mixed jump/slam dwell."""
    from .move_data import load_cl_slam
    limits={s.name:max(int(n) for n in s.frames) for s in load_cl_slam().states}
    return tuple((name,0 if name=="Slam Effects?" else limits[name])
                 for name in ("Slam Antic","Slam 0","Slam 1","Slam Effects?","Slam 2"))


def predicted_tail_end(state,goal):
    """Current Control phase through Slam 2, on the existing 60Hz family clock.

    An empirical prediction for one admission, never an observed hammer-off.
    The caller must bind the current source instance and scan every owner.
    """
    source=next((e for e in clappers(state) if e["iid"]==goal.caster),None)
    if source is None:return None
    controls=[m for m in source.get("fsms") or () if m.get("name")=="Control"]
    if len(controls)!=1:return None
    st=controls[0].get("state");tin=controls[0].get("t");f=state.get("f")
    if type(f) is not int or type(tin) not in (int,float) or not math.isfinite(tin) or tin<0:return None
    phases=slam_tail_frames();names=[s for s,_ in phases]
    if st not in names:return None
    end=f-int(round(tin*60.))+sum(n for _,n in phases[names.index(st):])
    return end if f<=end else None


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
    cast_ta:object=None
    source_kind:str="CAST"
    source_move:object=None

    @property
    def responsibility(self):
        return self.source_move or MoveInstance(self.caster,self.cast_fa,"CC_CAST")


def bounce_target(state):
    """A current, actual DownSlash hit AND bounce marker; never model contact."""
    from .knife_chain_observations import pogo_marker
    if not pogo_marker(state):return None
    f=state.get("f");hits=set()
    for ev in state.get("ev") or ():
        d=ev.get("d") or {};src=str(d.get("src") or "");ef=ev.get("f",f)
        iid=d.get("ent",d.get("iid"))
        if (ev.get("k")=="hit" and "DownSlash" in src and "Harpoon" not in src
                and type(ef) is int and ef==f and type(iid) is int):hits.add(iid)
    return next(iter(hits)) if len(hits)==1 else None


def bounce_tail_pending(state,goal,game):
    """Keep the old hammer tail until its observed Slam 2 collider is gone."""
    if goal is None or goal.source_kind!="BOUNCE" or goal.responsibility.family!="CC_SLAM":return False
    if goal.responsibility.target_iid!=goal.caster:return False
    source=next((e for e in clappers(state) if e["iid"]==goal.caster),None)
    if source is None:return True
    st,tin=control(source)
    if st in AIR_ATTACK_STATES:
        new=(st=="Slam Antic" and goal.cast_ta is not None and abs(game-tin-goal.cast_ta)>3/60.)
        if not new:return True
    if not st:return True
    cols=source.get("colliders")
    if not isinstance(cols,list) or not cols:return True
    if any(str(c.get("name","")).startswith("Slam Collider") and c.get("enabled") is not False for c in cols):return True
    return not any(str(c.get("name","")).startswith("Song Heavy Sentry") and c.get("enabled") is True for c in cols)


def observe_goal(state,previous,cfg,finished,game_time=None):
    """A visible antic selects the destination; it is not a Run or key commitment."""
    es=clappers(state);h=state.get("hero") or {};f=state.get("f")
    if len(es)!=2 or type(f) is not int or h.get("health",0)<=0:return None
    byid={e["iid"]:e for e in es}
    casting=[e for e in es if control(e)[0]=="Spell Antic" and control(e)[1]<=cfg["entry_cast_s"]]
    if len(casting)==1:
        caster=casting[0];target=next(e for e in es if e is not caster)
        fa=max(0,f-int(round(control(caster)[1]*60.)))
        fresh=TransferGoal(target["iid"],caster["iid"],fa,
            None if game_time is None else float(game_time)-control(caster)[1])
        if previous is not None and (fresh.target,fresh.caster,fresh.cast_fa)==(previous.target,previous.caster,previous.cast_fa):
            return previous
        # Record the tactical destination for every live target state. The
        # blade adapter, not goal observation, decides which action can execute.
        if (caster["iid"],fa) not in finished and (previous is None or fresh!=previous):return fresh
    if previous is not None:
        if (previous.target in byid and previous.caster in byid and
                0<=f-previous.cast_fa<=cfg["max_frames"]):
            return previous
    return None


def head_clearance(cfg):
    # Same focus margin as the query, plus the two raster-cell boundary bands.
    # This strengthens the handoff definition; it never removes a contact.
    from .forum_v2 import FOCUS_M,CELL
    return max(float(cfg["head_clearance"]),FOCUS_M+2*CELL)


def flight_endpoint(path,body,clearance):
    ground=path.states[K.GROUND]>0
    was_air=np.r_[False,np.maximum.accumulate(~ground[:-1])]
    head=(path.pos[:,0]>=body[0])&(path.pos[:,0]<=body[2])&(path.box[:,1]>=body[3]+clearance)
    indices=np.arange(len(ground));over=np.flatnonzero(head&(indices>=2));land=np.flatnonzero(ground&was_air&(indices>=2))
    ends=[(int(over[0]),"overhead")] if len(over) else []
    if len(land):ends.append((int(land[0]),"landing"))
    return min(ends) if ends else (None,"uncovered")


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


def press_now_row(sim,body,F,hold,side):
    """Shared velocity-aware downslash exit, not a fixed position or hit receipt.

    Try the existing toward row first. Only on failure try releasing direction
    and then countersteering. These are three fixed rows, not a timing search.
    Each uses the actual S0, in-flight prefix and hold filter. The observed body
    is held still for this contact witness; external safety remains the caller's.
    """
    from .knife_chain_vault import strike_program
    from . import pogo_model as PM
    if body is None or not np.isfinite(body).all():return None
    direction=1 if side==B["R"] else -1 if side==B["L"] else 0
    poly=np.array([[body[0],body[1]],[body[2],body[1]],[body[2],body[3]],[body[0],body[3]]])
    pj=len(sim.prefix)+2
    for d in ((direction,0,-direction) if direction else (0,)):
        row=strike_program(F,hold,1,d or 1,16)
        if d==0:row["masks"]=[m&~(B["L"]|B["R"]) for m in row["masks"]]
        ro=sim.roll(np.asarray(row["masks"],np.int64)[None]);flags=ro.flags[0]
        if not np.any(flags[pj:pj+2]&K.F_ATTACKING) or flags[pj-1]&K.F_GROUND:continue
        for j in range(pj+PM.ACTIVE[0],min(pj+PM.ACTIVE[1]+1,len(flags))):
            if flags[j]&K.F_GROUND:break
            if all(PM.meets(PM.slash_poly(face,alt)+ro.pos[0,j],poly)
                    for face in (-1,1) for alt in (False,True)):
                row.update(contact_frame=sim.fo+j,approach_direction=d,
                           contact_velocity=ro.vel[0,j].tolist())
                return row
    return None


def air_approach_keys(x):
    """One optional dash impulse, after a failed current strike exit.

    A once-per-Run coast probe selects the recipe, not safety or future hit.
    If the nominal directional coast already reaches above the observed body,
    retain the dash. Otherwise a far entry may spend its available air dash.
    All emitted keys still use the normal same-owner send and current-step gate.
    """
    side=int(x.v["side"]);left=max(0,int(x.v["jump_until"])-int(x.obs.k))
    mask=side|(B["J"] if left else 0)
    # A side approach has no strike/bounce to finish an irreversible air dash.
    # Keep the actual prefix/hold untouched; only decline a NEW dash impulse.
    if x.v.get("_approach_only") or not hasattr(x.obs,"sim") or x.obs.ground or x.v.get("air_dash_decided"):return mask
    sim=x.obs.sim;S=np.asarray(sim.start).reshape(K.K);h=x.obs.hero
    if (side==0 or x.v["iid"]==x.v["caster"] or h.get("hero_accepting_input") is not True or not np.isfinite(S).all()
            or S[K.GROUND]>0 or S[K.MODE]!=K.M_NORMAL or S[K.AIRDASHED]>0 or S[K.DASH_CD]>0):return mask
    dash_index=B["DASH"].bit_length()-1
    # Finish releasing a previous jump before selecting a new air impulse.
    # This also keeps the existing same-target bounce and held-jump entries.
    if int(sim.prefix[0])&B["J"] or sim.hold.latched[0,0] or sim.hold.desired[0,0]:return mask
    if (int(sim.prefix[0])&B["DASH"] or sim.hold.latched[0,dash_index]
            or sim.hold.desired[0,dash_index] or sim.hold.pending[0,dash_index]):return mask
    body=body_box(x.obs.e)
    if body is None:return mask
    hx=float(S[K.PX]);gap=max(body[0]-hx,hx-body[2],0.)
    # A manual distance selector, scaled by the target's width. Near entries
    # keep their ordinary drift/strike and do not burn a dash to cross the body.
    if gap<=body[2]-body[0]:return mask
    commands=np.full(int(x.cfg["flight_check_frames"]),side,np.int64)
    commands[:min(left,len(commands))]|=B["J"]
    coast=sim.roll(commands[None]);flags=coast.flags[0]
    x.v["air_dash_decided"]=True
    lands=np.flatnonzero(((flags&K.F_GROUND)!=0)&(np.arange(len(flags))>=sim.off))
    if not len(lands):return mask  # uncovered: keep the dash, do not repeat the long probe
    end=int(lands[0]);pos=coast.pos[0,sim.off:end];box=coast.box[0,sim.off:end]
    if not len(pos) or np.any((pos[:,0]>=body[0])&(pos[:,0]<=body[2])&(box[:,1]>=body[3])):return mask
    x.v["approach_recipe"]="air_dash"
    return mask|B["DASH"]


def register(prims):
    @prims.gen("transfer_source_tail_keys",doc="legacy neutral tail or the checked absolute wall-successor row")
    def source_tail_keys(x,m):
        if x.v.get("_wall_pressure"):
            from .knife_chain_nominal import NominalUnsupported
            row=x.v.get("row");i=x.obs.F-row["F0"] if isinstance(row,dict) else -1
            masks=() if not isinstance(row,dict) else row.get("masks",())
            if type(i) is not int or not 0<=i<len(masks):
                raise NominalUnsupported("absolute wall-pressure row unavailable or expired")
            return m|int(masks[i])
        return m|int(x.v.get("source_tail_mask",0))

    @prims.action("transfer_stomp_plan",doc="one press-now row against the currently observed body; not a hit receipt")
    def stomp_plan(x):
        if x.v.get("_approach_only") or not hasattr(x.obs,"sim") or x.obs.ground:return None
        left=max(0,int(x.v["jump_until"])-int(x.obs.k))
        row=press_now_row(x.obs.sim,body_box(x.obs.e),x.obs.F,left,x.v["side"])
        if row is not None:
            x.v["row"]=row
            return {"do":"goto","to":"strike"}
        return None

    @prims.gen("transfer_air_keys",doc="same-owner optional one-shot air dash; never a new jump or umbrella")
    def air_keys(x,m):return m|air_approach_keys(x)

    @prims.gen("transfer_strike_row",doc="the original absolute downslash row; never re-time an already sent strike")
    def strike_row(x,m):
        row=x.v["row"];i=x.obs.F-row["F0"]
        return m|int(row["masks"][i] if 0<=i<len(row["masks"]) else x.v["side"])

    @prims.guard("transfer_missed")
    def missed(x):
        row=x.v.get("row")
        return row is not None and x.obs.f>row["press_F"]+int(x.cfg["STOMP"]["miss_after"])

    @prims.guard("transfer_landed")
    def landed(x):
        return bool(x.obs.ground and x.obs.k>x.v["jump_k"]+2)

    @prims.guard("transfer_jump_failed")
    def jump_failed(x):
        antic=int(x.cfg["jump_antic_frames"]) if x.v["sprint_jump"] else 0
        # obs.k is the mask clock (two ahead). Do not use the entire J hold
        # as a takeoff deadline, or apply a four-frame normal-jump deadline to
        # the sprint jump's seven-frame grounded antic.
        return bool(x.obs.ground and x.obs.k>x.v["jump_k"]+antic+x.cfg["STOMP"]["takeoff_grace"]+2)


def propose(runner,state,game,sim,target,ground,bombs,finished,goal=None,*,defer_jump=False,approach_only=False):
    """One observed-distance recipe and a two-frame external path.

    approach_only uses the same walk/dash/air keys without choosing a strike.
    Its sent Run keeps that intent until the native adapter's planned handoff.
    defer_jump remains for offline callers; neither cancels an existing sprint.
    """
    h=state.get("hero") or {};es=clappers(state);active=runner.run if runner.run is not None and runner.run.chain==PROGRAM else None
    approach_only=bool(active.v.get("_approach_only")) if active is not None else approach_only
    if len(es)!=2 or target is None or not complete_hf(state):return None
    enemy=next((e for e in es if e["iid"]==target),None)
    if enemy is None:return None
    other=next(e for e in es if e is not enemy);st,tin=control(other);target_state,_=control(enemy)
    cfg=runner.chains[PROGRAM].cfg;body=body_box(enemy)
    attacking=target_state in AIR_ATTACK_STATES
    bounce_entry=goal is not None and goal.source_kind=="BOUNCE"
    tail_done=bool(active is not None and active.v.get("source_tail_done"))
    tail_pending=not tail_done and bounce_tail_pending(state,goal,game)
    if body is None or h.get("health",0)<=0 or h.get("stunned"):return None
    if target_state not in cfg["target_states"] and not (attacking and goal is not None and not ground):return None
    if sim.fo!=sim.f or sim.f!=state["f"] or len(sim.prefix)!=1:return None
    if int(sim.prefix[0])&~(B["L"]|B["R"]|B["J"]|B["DASH"]|B["D"]|B["A"]):return None
    hp=h.get("pos");vel=h.get("vel")
    if not isinstance(hp,(list,tuple)) or not isinstance(vel,(list,tuple)) or min(len(hp),len(vel))<2:return None
    if np.asarray(sim.start).shape not in ((K.K,),(K.K,1)) or not np.isfinite(sim.start).all() or not np.isfinite([game,*hp[:2],*vel[:2]]).all():return None
    cd=(h.get("tm") or {}).get("dash_cd")
    if type(cd) not in (int,float) or not math.isfinite(cd):return None
    if active is None:
        if h.get("hero_accepting_input") is not True:return None
        observed=(goal is not None and goal.target==target and goal.caster in {e["iid"] for e in es} and
                  0<=state["f"]-goal.cast_fa<=cfg["max_frames"])
        if not observed and (st!="Spell Antic" or tin>cfg["entry_cast_s"]):return None
        if ground and (int(sim.prefix[0])&B["J"] or state["act"]["hf"]["latched"]&B["J"]):return None
        cast_fa=goal.cast_fa if observed else max(0,state["f"]-int(round(tin*60.)))
        source=goal.caster if observed else other["iid"]
        if (source,cast_fa) in finished:return None
        side=B["R"] if enemy["pos"][0]>h["pos"][0] else B["L"]
        if bounce_entry and target==source and body[0]<=hp[0]<=body[2]:side=0
        p=TransferPlan(target,source,cast_fa,state["f"],game,
            side,2+int(math.ceil(max(0.,cd)*60.)),10000,10000,False,state["f"],0)
        link="walk" if ground else "air"
    else:
        if active.v["iid"]!=target:return None
        p=TransferPlan(**{k:active.v[k] for k in TransferPlan.__dataclass_fields__ if k in active.v},origin=state["f"],entry_k=int(round((game-active.v["ta"])*60.)))
        link=active.link
    if bounce_entry and target==p.caster and link!="strike":
        side=B["R"] if enemy["pos"][0]>hp[0] else B["L"]
        p=replace(p,side=0 if body[0]<=hp[0]<=body[2] else side)
    landed_entry=bool(active is not None and active.link in {"air","bounce_tail"} and
                      ground and active.v.get("air_entry") and not tail_pending)
    if tail_pending:
        link="bounce_tail";p=replace(p,jump_k=min(p.jump_k,p.entry_k),jump_until=p.entry_k)
    elif link=="bounce_tail":link="walk" if ground else "air"
    k=p.entry_k
    current_mode=int(np.asarray(sim.start).reshape(K.K)[K.MODE])
    air_entry=bool(tail_pending or (active is not None and active.v.get("air_entry")))
    if landed_entry:
        # An outside bounce/flight is an entry, not our missed jump. Keep the
        # same destination and owner across landing and select the normal jump.
        link="walk";air_entry=False;p=replace(p,jump_k=10000,jump_until=10000)
    if link in {"walk","dash"} and ground:
        held_dash=bool(current_mode in (K.M_DASH,K.M_SPRINT) and int(sim.prefix[0])&B["DASH"])
        if held_dash:link="dash"
        gap=abs(enemy["pos"][0]-hp[0])
        # Observe the distance now. A model's eventual body intersection must
        # not make us release DASH or wait in front of the destination.
        if not (defer_jump or approach_only) and gap<=cfg["STOMP"]["jump_root"]:
            p=replace(p,jump_k=k+2,jump_until=k+2+int(cfg["STOMP"]["jump_hold"]),sprint_jump=held_dash)
        elif (link=="walk" and current_mode not in (K.M_DASH,K.M_SPRINT) and
                not (int(sim.prefix[0])|state["act"]["hf"]["latched"])&B["DASH"] and
                gap<=cfg["STOMP"]["dash_min_root"]):
            # A newly available near dash buffers J until its tail, then slides
            # through the seven-frame sprint-jump antic (live f2959..2975).
            # Walk to the ordinary-jump distance; never withdraw in-flight DASH.
            p=replace(p,dash_k=k+10000)
        # Cooldown is evaluated at the first free mask frame, not slid on each
        # tick. Re-arm only a suppressed clock if the target moves away again.
        elif active is None or p.dash_k>=10000:
            p=replace(p,dash_k=k+max(2,int(math.ceil(max(0.,cd)*60.))))
    elif not ground and not tail_pending:
        if active is None or link in {"walk","dash"}:
            p=replace(p,jump_until=k,jump_k=min(p.jump_k,k));air_entry=True
        elif not (state["act"]["hf"]["latched"]&B["J"] and int(sim.prefix[0])&B["J"]):p=replace(p,jump_until=k)
        if link!="strike":link="air"
    if defer_jump and (not ground or (state["act"]["hf"]["latched"]|int(sim.prefix[0]))&B["J"]):return None
    if defer_jump or (approach_only and ground):
        p=replace(p,jump_k=k+10000,jump_until=k+10000,sprint_jump=False)
        # Deferring J must not release a dash already in progress (which
        # cancels its sprint transition), or slide a pending far dash clock.
        link="dash" if current_mode in (K.M_DASH,K.M_SPRINT) else "walk"
    draft=runner.fork_empty(AirAnchor())
    variables=dict(runner.chains[PROGRAM].vars)
    if active is not None:variables.update(active.v)
    variables.update(p.variables());variables["air_entry"]=air_entry
    variables["_approach_only"]=approach_only
    variables["source_tail_done"]=bool(tail_done or (bounce_entry and not tail_pending))
    draft.run=Run(PROGRAM,link,variables)
    clearance=head_clearance(cfg)
    obs=_observation(p,state,game,body,ground,clearance)
    obs.sim=sim;obs.e=enemy;obs.hero=h
    obs.bounced=bool(variables.get("bounced"))
    mask=draft.eval_link(X(draft,draft.run,obs))
    if mask is None:return (None,p,None,None)
    row=draft.run.v.get("row")
    if row is not None:p=replace(p,press_k=k+row["press_F"]-state["f"],contact_frame=row["contact_frame"])
    path=model_path(sim,p,np.array([mask],np.int64),game)
    if landed_entry:
        # Keep R1's close-body backstop: a landing may continue only when the
        # already queued ground step stays clear before our next jump applies.
        from .forum_v2 import FOCUS_M
        b=path.box;grounded=path.states[K.GROUND,:len(b)]>0
        overlap=(b[:,0]<body[2]+FOCUS_M)&(b[:,2]>body[0]-FOCUS_M)&(b[:,1]<body[3]+FOCUS_M)&(b[:,3]>body[1]-FOCUS_M)
        if np.any(grounded&overlap):return (None,p,None,None)
    path=replace(path,stage="approach",assumptions={**path.assumptions,
        "basis":"manual observed-distance dash/sprint/jump/stomp; current external step only",
        "next_decision":"actual target DownSlash hit plus bounce, miss, or new target move",
        "flight_checked":False,"flight_endpoint":"not certified","jump_deferred":bool(defer_jump or approach_only),"approach_only":approach_only})
    if path_problem(path,sim.hold):return None
    return draft,p,path,int(mask)
