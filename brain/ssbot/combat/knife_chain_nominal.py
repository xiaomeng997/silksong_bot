"""Nominal B2 paths from the ported chain program and the existing HERO2 model.

No world search and no input owner. Future STATEs below are MODEL observations in
an isolated interpreter copy, never receipts/history in the live runner. The nail
contact is conditional on the h2 guard, not on the ordinary scorer's nh. Default
press-to-contact 4 is the median of the 34 development strikes (3/4/5/6: 11/8/8/7).
It is explicitly an estimate, not a hit certificate. Real handback needs evidence.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np

from ssbot.knowledge import kinematics as km
from .air_chain import ChainSim
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_eval import ChainObservationNotReady, Run


class NominalUnsupported(ValueError):
    pass


@dataclass(frozen=True)
class NominalProfile:
    contact_delay: int = 4
    max_frames: int = 160
    short_frames: int = 12
    jump_decision_k: int = 21
    close_entry_u: float = 3.
    # Explicit nominal hook, not a favorable member selected after checking safety.
    hook_dash_frame: int = 18
    hook_control_after: int = 5
    hook_dash_steps: int = 5

    def __post_init__(self):
        if not 3 <= self.contact_delay <= 9 or self.max_frames < 24 or self.short_frames <= 9 or self.jump_decision_k<0 or self.close_entry_u<0:
            raise ValueError("invalid nominal profile")


@dataclass
class NominalPath:
    origin: int
    stage: str
    commands: np.ndarray          # desired keys for origin+1..end, prefix included
    latched: np.ndarray
    states: np.ndarray            # [K, frames+1]
    box: np.ndarray               # [frames+1,4]
    pos: np.ndarray
    flags: np.ndarray
    check_flags: np.ndarray       # future contact's protection NOT applied to approach/strike check
    game: np.ndarray
    hold_end: object
    raw_end: dict
    runner_end: object
    queued_next: int
    end: str                     # decision | bounce | handback | horizon
    press_frame: int | None
    contact_frame: int | None
    assumptions: dict
    approach: object = None      # preparation prefix of this conditional full future
    first_draft: object = None   # actual branch decision only, before model futures

    @property
    def through(self):
        return self.origin + len(self.commands)

    @property
    def offered(self):
        if len(self.commands) < 2:
            raise NominalUnsupported("path does not cover in-flight prefix plus next offer")
        return self.commands[1:]


@lru_cache(maxsize=12)
def _timeline(antic):
    from .pogo_slam import SlamTimeline
    return SlamTimeline.load(antic=int(antic), K=360)


def logical_copy(runner):
    # The family only appends to audit lists and replaces anchor._args at each
    # step. Past records, observed history and model configuration are read-only;
    # mutable active vars / strike plans / anchor memory still fork privately.
    static = (runner.chains, runner.P, runner.cfg0, runner.binding,
              getattr(runner.anchor,"chains",None),getattr(runner.anchor,"cfg",None),
              getattr(runner.anchor,"hist",None),getattr(runner.anchor,"_args",None))
    memo={id(v):v for v in static if v is not None}
    memo[id(runner.done)]=list(runner.done)
    if runner.run is not None:
        for name in ("trace","path","sent"):
            v=getattr(runner.run,name);memo[id(v)]=list(v)
    cs=getattr(runner.anchor,"csx",None)
    for obj in (getattr(cs,"params",None),getattr(cs,"terrain",None)):
        if obj is not None:memo[id(obj)]=obj
    return deepcopy(runner,memo)


@lru_cache(maxsize=4)
def _schema_names(path):
    return tuple(km.cstate_names())


def state_names():
    return _schema_names(str(km.CSTATE_NAMES_PATH))


def is_committing(run, profile=None):
    if run is None:return False
    profile=profile or NominalProfile()
    if run.chain=="slam_claw" or run.link in {"jump","air","after"}:return True
    # k is the target mask-frame clock (SEND_AHEAD=2). This is the user's
    # first-smoke decision boundary, independent of the table's stable links.
    distance=run.v.get("_b2_entry_distance",run.v.get("x_start"))
    if distance is not None and abs(float(distance))<=profile.close_entry_u:return True
    return float(run.v.get("k",0))-2>=profile.jump_decision_k


def flag(raw, name):
    names = state_names()
    bits = (raw.get("hero") or {}).get("cstate")
    if bits is None or name not in names:
        return False
    i = names.index(name)
    return i // 64 < len(bits) and bool((int(bits[i // 64]) >> (i % 64)) & 1)


class NominalWorld:
    """One already-observed slam, advanced on one nominal game-time timeline."""
    def __init__(self, raw, run, game):
        from .slam_play import control, SlamPlay
        target = next((e for e in raw.get("ents") or () if e.get("iid") == run.v["iid"]), None)
        if target is None:
            raise NominalUnsupported("nominal target absent")
        self.iid, self.base = run.v["iid"], deepcopy(target)
        self.ta = float(run.v["ta"])
        self.k0 = max(0, int(round((game - self.ta) * 60)))
        st, tin = control(target)
        antic = int(run.v.get("ks0") or 49)
        if st == "Slam Antic":
            antic = max(antic, int(round(tin * 60)) + 1)
        self.tl = _timeline(antic)
        self.antic = antic
        self.face = int(run.v["face"])
        body = SlamPlay._cs_box(target)
        if body is None:
            raise NominalUnsupported("no body anchor")
        nominal = self.tl.world(np.array([self.k0]))[0]
        ncentre = np.array([.5*(nominal[0]+nominal[1])*self.face,
                            .5*(nominal[2]+nominal[3])])
        self.anchor = np.array([.5*(body[0]+body[2]), .5*(body[1]+body[3])]) - ncentre

    def box(self, game):
        k = max(0, min(len(self.tl.state)-1, int(round((game-self.ta)*60))))
        q = self.tl.world(np.array([k]))[0]
        x0,x1 = sorted((q[0]*self.face+self.anchor[0],q[1]*self.face+self.anchor[0]))
        return np.array([x0,q[2]+self.anchor[1],x1,q[3]+self.anchor[1]])

    def observe(self, raw, f, game):
        s = raw
        s["f"], s["dt"], s["ev"] = int(f), km.FT if hasattr(km,"FT") else 1/60, []
        e = next((e for e in s.get("ents") or () if e.get("iid")==self.iid),None)
        if e is None: raise NominalUnsupported("model target disappeared")
        k=max(0,min(len(self.tl.state)-1,int(round((game-self.ta)*60))))
        st=self.tl.state[k]
        st="Idle" if st=="after" else st
        j=k
        while j>0 and self.tl.state[j-1]==self.tl.state[k]:j-=1
        for fs in e.get("fsms") or ():
            if fs.get("name")=="Control":fs.update(state=st,t=(k-j)/60)
        bb=self.box(game)
        delta=(self.tl.disp[k]-self.tl.disp[min(self.k0,len(self.tl.disp)-1)])*self.face
        e["pos"]=[float(self.base["pos"][0])+delta,float(self.base["pos"][1])]
        if self.base.get("pos_transform"):
            e["pos_transform"]=[self.base["pos_transform"][0]+delta,self.base["pos_transform"][1]]
        for c in e.get("colliders") or ():
            if c.get("layer")==11 or str(c.get("name","")).startswith("Song Heavy Sentry"):
                c["verts_world"]=[float(bb[0]),float(bb[1]),float(bb[2]),float(bb[1]),
                                  float(bb[2]),float(bb[3]),float(bb[0]),float(bb[3])]
        return s


def _hero(raw, S, box, pos, vel, flags, *, hook=False):
    h=raw.setdefault("hero",{})
    h["box"],h["pos"],h["vel"]=list(map(float,box)),list(map(float,pos)),list(map(float,vel))
    h["facing"]=float(S[km.FACE])
    md=int(S[km.MODE])
    h.setdefault("tm",{}).update(atk_cd=float(S[km.ATK_CD]),dash_cd=float(S[km.DASH_CD]),
                                  ds_rec=float(S[km.DS_REC]))
    h["hero_accepting_input"]=not hook and md not in {km.M_LOCKED,km.M_HURT_FREEZE,km.M_HURT_RECOIL}
    h.setdefault("can",{})["input"]=h["hero_accepting_input"]
    clip="Harpoon Dash" if hook else ("DownSlash" if md in {km.M_DS_ANTIC,km.M_DS_SPIKE} or (S[km.ATTACKING]>0 and raw.get("_b2_nominal_down",False)) else
            "DownSpike" if S[km.BOUNCE]>=0 else "Idle" if flags&km.F_GROUND else "Airborne")
    h.setdefault("anim",{})["clip"]=clip
    bits=list(h.get("cstate") or [0,0])
    names=state_names()
    for name,value in {"onGround":bool(flags&km.F_GROUND),"attacking":bool(flags&km.F_ATTACKING),
                       "downSpikeAntic":md==km.M_DS_ANTIC,"downSpiking":md==km.M_DS_SPIKE,
                       "downSpikeBouncing":S[km.BOUNCE]>=0,"downSpikeRecovery":S[km.DS_REC]>=0}.items():
        if name in names:
            i=names.index(name)
            while len(bits)<=i//64:bits.append(0)
            bits[i//64]=(int(bits[i//64]) | (1<<(i%64))) if value else (int(bits[i//64]) & ~(1<<(i%64)))
    h["cstate"]=bits
    return raw


def _nominal_hook(S, world, game, params, terrain, profile, direction):
    from ssbot.map2 import strike as sk, oldwin_claw as oc
    from ssbot.knowledge import hero2
    dt=float(params.frame_time);fdt=float(params.fdt)
    a=float(S[km.ALPHA])
    counts=[int(math.floor(a+j*dt/fdt+1e-8)-math.floor(a+(j-1)*dt/fdt+1e-8)) for j in range(1,7)]
    phases=[p for p in range(6) if [sk.steps_of(j,p) for j in range(1,7)]==counts]
    if not phases:raise NominalUnsupported("hook model clock outside nominal phase lattice")
    phase=phases[0]
    boxes=np.array([world.box(game+j*dt) for j in range(180)])
    timing=sk.HookVariant("b2-nominal",profile.hook_dash_frame,2.1,profile.hook_control_after)
    steps=[sk.steps_of(j,phase) for j in range(1,181)]
    h=sk.claw_hook(S,0,direction,world.iid,boxes,timing,phase,discrete_stop=True,
                   hold_steps=sum(steps[:sk.HOOK_THROW_F]),dash_max_steps=profile.hook_dash_steps,
                   dash_damager=True,dash_motion_lag=1)
    if not h.ok:raise NominalUnsupported("nominal hook ray: "+h.why)
    antic=hero2.claw_unhooked(float(S[km.PX]),float(S[km.PY])-sk.FOOT,
                             float(S[km.VX]),float(S[km.VY]),direction,steps)
    physical=h.pos.copy();throw=sk.HOOK_THROW_F
    physical[:throw+1,1]=antic.bb[:throw+1]+sk.FOOT
    physical[throw+1:,1]=antic.bb[throw]+sk.FOOT
    h.y_hold=float(physical[-1,1]);h.physical=physical
    # Draw between successive fixed poses using the modeled alpha; do not choose
    # the q/s endpoint which happens to be safer.
    moved=np.r_[False,np.asarray(steps[:len(physical)-1],bool)]
    latest=np.maximum.accumulate(np.where(moved,np.arange(len(physical)),0))
    q=physical[np.maximum(latest-1,0)];v=physical[latest]
    q[latest==0]=S[[km.QX,km.QY]];v[latest==0]=S[[km.SX,km.SY]]
    alpha=np.mod(a+np.arange(len(physical))*dt/fdt,1.)
    h.pos=q*(1-alpha[:,None])+v*alpha[:,None]
    return h,phase


def compile_path(runner, raw, sim, game, *, stage, first_mask, profile=None,
                 branch=None, known_press=None):
    """Run a private chain copy forward with generated observations, never replay keys.

    `runner` already contains the current real tick's preview (except a branch,
    whose entry is evaluated here). The queued origin+1 key is always supplied by
    a real receipt, or by the parent nominal path when evaluating its bounce.
    """
    from .holdfilter import hold_filter_jit
    profile=profile or NominalProfile()
    if sim.fo!=sim.f or len(sim.prefix)!=1:raise NominalUnsupported("B2 needs current origin and one queued key")
    R=logical_copy(runner);s=deepcopy(raw);origin=int(sim.f)
    if R.run is None:raise NominalUnsupported("no admitted family program")
    world=NominalWorld(s,R.run,float(game))
    if branch is not None:
        face=R.run.v["face"]
        R.run.chain="slam_jump";R.run.link="out_dash" if branch=="dash_out" else ("out_front" if branch=="right_landing" and face>0 or branch=="left_landing" and face<0 else "out_behind")
        near=-1 if branch=="left_landing" else 1
        R.run.v.update(bounced=True,near=near,near_u=float(R.cfg0.get("NEAR_STAND_U",5.)),
                       side_why="b2_option",over_dir=None,k_dash=None)
        R.observation_cutoff=origin
        first_mask=R.step(origin,s,bool(sim.start[km.GROUND]),bool(s.get("hero",{}).get("hero_accepting_input",True)),
                          t_game=game,sim=sim)
        if first_mask is None:raise NominalUnsupported("post-bounce branch has no first action")
    branch_draft=logical_copy(R) if branch is not None else None
    desired={origin+1:int(sim.prefix[0]),origin+2:int(first_mask)}
    S=np.asarray(sim.start,float).reshape(km.K).copy();hold=sim.hold.copy()
    init=km.rollout(S,np.zeros((1,0),np.int64),sim.params,sim.terrain)
    boxes=[init.box[0,0]];poses=[init.pos[0,0]];flags=[int(init.flags[0,0])];checks=flags.copy()
    states=[S.copy()];games=[float(game)];commands=[];latched=[]
    press=known_press;contact=None;hook=None;hook_start=None;phase=None;end="horizon"
    stop_at=None
    entry_frame=origin if is_committing(R.run,profile) else None
    approach_path=None
    assumptions={"timing":"nominal", "contact":"h2_guard_conditional_median_press_plus_4",
                 "profile":dict(profile.__dict__),"future_state":"model_only"}
    for step in range(1,profile.max_frames+1):
        F=origin+step
        if F not in desired:raise NominalUnsupported("missing queued/compiled key")
        cmd=int(desired[F]);lat,hnext=hold_filter_jit(np.array([[cmd]],np.int64),hold)
        m=int(lat[0,0]);old=S.copy();is_hook=False
        dt=sim.params.frame_time*float(S[km.TS])*float(S[km.WF_S]);game+=dt
        event=0
        if hook is None:
            ro=km.rollout(S,np.array([[m & ~B["CLAW"]]],np.int64),sim.params,sim.terrain)
            S=ro.final[:,0].copy();box=ro.box[0,-1];pos=ro.pos[0,-1];vel=ro.vel[0,-1];fl=int(ro.flags[0,-1]);checkfl=fl
            if m&B["CLAW"] and not int(old[km.PREV])&B["CLAW"]:
                if S[km.GROUND]>0 or int(S[km.MODE])!=km.M_NORMAL:
                    raise NominalUnsupported("nominal hook launch not free airborne")
                direction=-1 if m&B["L"] else 1 if m&B["R"] else int(S[km.FACE])
                hook,phase=_nominal_hook(S,world,game,sim.params,sim.terrain,profile,direction)
                hook_start=F;assumptions["hook"]={"phase":phase,"control":F+hook.ctrl,"model":"discrete damager stop"}
        else:
            j=F-hook_start;is_hook=j<hook.ctrl
            if j>=hook.ctrl:
                from ssbot.map2.oldwin_claw import control_state
                alpha=(float(old[km.ALPHA])+sim.params.frame_time/sim.params.fdt)%1.
                S=control_state(sim.params,hook,sim.terrain,alpha=alpha)
                ro=km.rollout(S,np.zeros((1,0),np.int64),sim.params,sim.terrain)
                box=ro.box[0,0];pos=ro.pos[0,0];vel=ro.vel[0,0];fl=int(ro.flags[0,0]);checkfl=fl;hook=None
            else:
                S[[km.PX,km.PY]]=hook.pos[j];S[[km.SX,km.SY]]=hook.physical[j]
                S[[km.QX,km.QY]]=hook.physical[max(0,j-1)]
                S[km.ALPHA]=(float(old[km.ALPHA])+sim.params.frame_time/sim.params.fdt)%1.
                S[km.MODE]=km.M_LOCKED;S[km.GROUND]=0.;S[km.INV_T]=0.
                pos=hook.pos[j];vel=(hook.physical[j]-hook.physical[j-1])/sim.params.frame_time
                S[[km.VX,km.VY]]=vel
                ro=km.rollout(S,np.zeros((1,0),np.int64),sim.params,sim.terrain)
                box=ro.box[0,0];fl=int(ro.flags[0,0])&~km.F_INVULN;checkfl=fl
        # Accepted model downslash, not merely a requested D|A.
        down=(bool(fl&km.F_ATTACKING) and old[km.ATTACKING]<=0 and bool(m&B["D"]) and old[km.GROUND]<=0)
        if press is None and down:
            press=F
        s["_b2_nominal_down"]=bool(fl&km.F_ATTACKING) and press is not None
        if stage=="commitment" and press is not None and F>=press+profile.contact_delay:
            event=km.EV_POGO
            # Inject at this frame, not one frame earlier. Keep pre-contact flags
            # for foreign hazards on the commitment's last frame.
            ro=km.rollout(old,np.array([[m]],np.int64),sim.params,sim.terrain,events=np.array([[event]],np.int64))
            S=ro.final[:,0].copy();box=ro.box[0,-1];pos=ro.pos[0,-1];vel=ro.vel[0,-1];fl=int(ro.flags[0,-1]);contact=F
        commands.append(cmd);latched.append(m);hold=hnext
        boxes.append(np.array(box));poses.append(np.array(pos));flags.append(fl);checks.append(checkfl)
        states.append(S.copy());games.append(float(game))
        s=world.observe(s,F,game);_hero(s,S,box,pos,vel,fl,hook=is_hook)
        if entry_frame is not None and entry_frame>origin and F==entry_frame+1:
            # Future guard success is MODEL context only; retain an independent
            # no-admission prefix for the real approach tick.
            approach_path=NominalPath(origin,"approach",np.asarray(commands,np.int64).copy(),np.asarray(latched,np.int64).copy(),
                np.stack(states,axis=1),np.asarray(boxes).copy(),np.asarray(poses).copy(),np.asarray(flags,np.int64),
                np.asarray(checks,np.int64),np.asarray(games),hold.copy(),deepcopy(s),logical_copy(R),
                int(desired[F+1]),"decision",None,None,{"future_decision":entry_frame,"admission":"none"})
        if event:
            s["ev"]=[{"f":F,"k":"hit","d":{"type_key":"Song Heavy Sentry","iid":world.iid,"src":"DownSlash"}}]
            end="bounce";break
        if stop_at is not None and F>=stop_at:
            end="decision";break
        if stage=="continuation" and F>=origin+2 and fl&km.F_GROUND:
            end="handback";break
        R.observation_cutoff=F
        next_key=desired.get(F+1)
        if next_key is None:raise NominalUnsupported("future input pipeline incomplete")
        fsim=ChainSim(S,np.array([next_key],np.int64),hold,sim.params,sim.terrain,F,F)
        mask=R.step(F,s,bool(fl&km.F_GROUND),not is_hook and bool(s["hero"]["hero_accepting_input"]),t_game=game,sim=fsim)
        if mask is None:
            if stage=="approach":end="decision";break
            if stage=="continuation":
                # Handback is the program's actual termination, not invented
                # movement to make a tail pass. Normal planner can act here.
                end="handback";break
            raise NominalUnsupported(f"family aborted before conditional bounce at {F}; press={press}")
        desired[F+2]=int(mask)
        if entry_frame is None and is_committing(R.run,profile):
            entry_frame=F
            assumptions["future_entry_decision"]=F
        if stage=="approach" and is_committing(R.run,profile):
            stop_at=F+1
    if stage=="commitment" and end!="bounce":raise NominalUnsupported("no modeled accepted strike/bounce in horizon")
    if stage=="continuation" and end!="handback":raise NominalUnsupported("post branch did not hand back in horizon")
    through=origin+len(commands)
    if through+1 not in desired:raise NominalUnsupported("missing next queued command at endpoint")
    return NominalPath(origin,stage,np.asarray(commands,np.int64),np.asarray(latched,np.int64),
                       np.stack(states,axis=1),np.asarray(boxes),np.asarray(poses),np.asarray(flags,np.int64),
                       np.asarray(checks,np.int64),np.asarray(games),hold,s,R,int(desired[through+1]),end,press,contact,assumptions,approach_path,branch_draft)


def post_paths(parent, params, terrain, *, profile=None):
    """Three reusable table branches, modeled independently at the same bounce."""
    if parent.end!="bounce":raise NominalUnsupported("post options need conditional bounce")
    sim=ChainSim(parent.states[:,-1],np.array([parent.queued_next],np.int64),parent.hold_end,
                 params,terrain,parent.through,parent.through)
    paths={};errors={}
    for kind in ("left_landing","right_landing","dash_out"):
        try:
            paths[kind]=compile_path(parent.runner_end,parent.raw_end,sim,float(parent.game[-1]),
                stage="continuation",first_mask=0,profile=profile,branch=kind,known_press=parent.press_frame)
        except (NominalUnsupported,ChainObservationNotReady) as exc:errors[kind]=str(exc)
    return paths,errors


def compiled_signatures():
    """Loaded ssbot numba dispatchers, for warm-up vs first-call evidence."""
    import sys
    out={}
    for name,module in tuple(sys.modules.items()):
        if not name.startswith("ssbot.") or module is None:continue
        for key,value in tuple(vars(module).items()):
            if hasattr(value,"signatures") and hasattr(value,"py_func"):
                out[name+"."+key]=tuple(str(v) for v in value.signatures)
    return out


def warm_nominal(params):
    """Exercise B2's actual model call sites before combat; retain no future Run."""
    import json,time
    from pathlib import Path
    from types import SimpleNamespace
    from .knife_chain_format import chains_from_json
    from .knife_chain_slam import make_runner
    from . import claw_strike
    from ssbot.map2.oldwin_claw import control_state
    started=time.perf_counter();state_names()
    for antic in range(47,54):_timeline(antic)
    terrain=km.Terrain2D.from_boxes([(-100.,0.,100.,3.015),(0.,0.,14.,40.),(49.,0.,100.,40.)])
    S=km.initial_state(params,35.,4.568,ground=True,facing=-1,silk=9)
    raw={"f":1000,"dt":params.frame_time,"hero":{"health":7,"silk":9,"cstate":[0,0],"cstate_int":[0,0,0,0]},
         "ents":[{"iid":7,"type_key":"Song Heavy Sentry","hp":130,"flipX":True,"pos":[30.,7.449],
                  "fsms":[{"name":"Control","state":"Slam Antic","t":0.}]}],"ev":[]}
    # The warm runner is separate from the registered runtime runner. These cfg
    # changes choose deterministic warm branches; they never change live tables.
    chains=chains_from_json(json.loads(Path(__file__).with_name("knife_chain_slam_v01.json").read_text(encoding="utf-8")))
    for chain in chains.values():chain.cfg.update(CLAWSTRIKE=False,EARLY=False)
    R=make_runner(chains)
    zero=km.rollout(S,np.zeros((1,0),np.int64),params,terrain)
    _hero(raw,S,zero.box[0,0],zero.pos[0,0],zero.vel[0,0],int(zero.flags[0,0]))
    sim=ChainSim(S,np.zeros(1,np.int64),km.HoldState.idle(1),params,terrain,1000,1000)
    preview=R.preview(1000,raw,True,True,t_game=0.,sim=sim)
    if preview.mask is None:raise NominalUnsupported("B2 warm runner has no nominal jump")
    path=compile_path(preview.draft,raw,sim,0.,stage="commitment",first_mask=preview.mask)
    posts,errors=post_paths(path,params,terrain)
    if len(posts)!=3:raise NominalUnsupported("B2 warm post path missing: "+str(errors))
    world=NominalWorld(raw,preview.draft.run,0.)
    airborne=km.initial_state(params,40.,6.,ground=False,facing=-1,silk=9)
    airborne[km.ALPHA]=airborne[km.ALO]=airborne[km.AHI]=.25
    hook,_=_nominal_hook(airborne,world,0.,params,terrain,NominalProfile(),-1)
    control=control_state(params,hook,terrain,alpha=.5)
    # Including the hook-control view's layout is important: it can specialize
    # separately from a contiguous free-flight copy.
    for start in [S,control]:
        km.rollout(start,np.zeros((1,0),np.int64),params,terrain)
        km.rollout(start,np.zeros((1,1),np.int64),params,terrain)
        km.rollout(start,np.zeros((1,1),np.int64),params,terrain,events=np.full((1,1),km.EV_POGO,np.int64))
    claw_strike.warm(params)
    return {"seconds":time.perf_counter()-started,"jump_to_bounce":len(path.commands),"post_paths":len(posts),
            "hook_control":hook.ctrl,"compiled_signatures":compiled_signatures(),"scope":"warm models only, no real Run/contact credit"}
