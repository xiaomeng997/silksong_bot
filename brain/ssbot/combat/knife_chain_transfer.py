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
from .slam_play import _on as _env_on,_V2 as _ENV_V2

PROGRAM="rune_transfer"
# Task 182 B13 (docs/plans/forum_clapper_committed_chain.md 2.3 / 5.1 / 6.1; the person 11-12 "先做committed chain吧"): the Run's
# OWN target body under the conditional rule: her box may meet a still target only in the two frames before its modeled blade
# contact (contact-2 .. contact), never on the way there. The air link's body guard (transfer_body_guard) reads the Run's own keys
# ahead to her landing and, when they would put her into that body first, picks the Run's own follow-up (a down slash whose blade
# lands first, else steering off, else the latest meeting), never a hand-back. SSBOT_FORUM_CHAIN_B13 follows SSBOT_FORUM_V2 (=0:
# the old rows, no guard).
B13=_env_on("SSBOT_FORUM_CHAIN_B13",_ENV_V2)
B13_LEAD_F=8      # steering is chosen only when the planned keys meet the body within this many frames of F
B13_STRIKE_F=14   # the guard's own (relaxed) strike only within this many: farther, the Run's own rows still have time (a press needs
                  # its two in-flight frames, the slash's 3 to its first active frame and her box out of the body to contact-2)
B13_ROLL_F=48     # frames of the planned keys rolled ahead (past her landing from a held jump's apex)
# Task 182 committed chain, package 1 after B13 (the person 11-13 "你决定顺序", design 7.1): the ground route's jump out of a held
# ground dash / sprint is the shuttlecock jump (kinematics H2_SHUTTLE: her x speed locked along her facing while it runs, no turn), so
# the air guard has no way off a body it carries her into. When that flight enters her own still target's body from the side, the jump
# lets the dash go (an ordinary jump at the sprint's regain, steerable in the air). Switch SSBOT_FORUM_CHAIN_B13B (follows v2).
B13B=_env_on("SSBOT_FORUM_CHAIN_B13B",_ENV_V2)
B13B_GUARD_F=6    # an entry this many frames or fewer after the sprint jump's takeoff (or on the ground) is let go: the air guard's
                  # first tick is the takeoff, its strike's contact at least press (+2) + the slash's 3 to its first active frame, with
                  # her box out of the body to contact - 2 (closed loop 11-13: entries 8-10 frames after takeoff were the guard's strikes)
AIR_ATTACK_STATES=frozenset({"Slam Antic","Slam 0","Slam 1","Slam Effects?","Slam 2"})
# Target-bound face hook: one aimed face hook inside the SAME rune_transfer Run. Every number is an existing one
# (map2.strike / hero2 hooked Clawline, knife_chain_hook_target, knife_chain_empty_needle, vault far_lock, the
# Clapper Control FSM / are_type); none is a new calibration, and nothing here certifies a hook, a hit or a flight.
HOOK_LINKS=frozenset({"claw","claw_lock"})
HOOK_PRESS_AFTER_F=1        # turn key on the first mask frame F0, then CLAW for two frames at P=F0+1
HOOK_LATE_F=2               # knife_chain_empty_needle: a press may apply 0 .. 2 frames late (never a retiming)
HOOK_CTRL_LAST_F=34         # map2.strike.claw_hook: control P+23 .. 34 (the small-rune path's last frame)
HOOK_CTRL_MIN_F=12          # vault far_lock: no strike before claw_press > 12
HOOK_TIMEOUT_F=45           # vault far_lock: abort without control return by claw_press > 45
EVADE_U_S=15.               # Control FSM Evade Scuttle: 15 u/s straight back from her for 0.35 s
EVADE_MAX_S=44/60.          # are_type clapper: entered again at once in 7 % (40-44 frames in all)
HOOK_TARGET_STATES=frozenset({"Idle","Walk","Dmg Attack","Evade Scuttle"})  # target_states standing or scuttling


@lru_cache(maxsize=1)
def slam_tail_frames():
    """Family-specific empirical frame maxima, not mixed jump/slam dwell."""
    from .move_data import load_cl_slam
    limits={s.name:max(int(n) for n in s.frames) for s in load_cl_slam().states}
    return tuple((name,0 if name=="Slam Effects?" else limits[name])
                 for name in ("Slam Antic","Slam 0","Slam 1","Slam Effects?","Slam 2"))



@lru_cache(maxsize=1)
def _slam_antic_bounds():
    from .move_data import load_cl_slam,FRAME_S
    spec=load_cl_slam()
    poses=np.asarray(next(t for t in spec.tracks if t.name=="root").by_state["Slam Antic"],float)
    if poses.ndim!=2 or poses.shape[1]!=4 or not np.isfinite(poses).all():raise ValueError("unknown Slam Antic body poses")
    extent=(float(poses[:,0].min()),float(poses[:,1].max()),float(poses[:,2].min()),float(poses[:,3].max()))
    return min(int(n) for s in spec.states if s.name=="Slam Antic" for n in s.frames)*FRAME_S,extent


def stationary_antic_body_for_hit_check(state,iid,through):
    """Observed/model Antic pose union, with the short check before the earliest lunge.

    This is not a damage-invulnerability certificate. Unknown/armed colliders
    reject this narrow conditional check; other owners/hazards stay unprotected.
    """
    from .move_data import FRAME_S
    f=state.get("f")
    if type(f) is not int or type(through) is not int or not 0<through-f<=2:return None
    enemies=[e for e in clappers(state) if e.get("iid")==iid]
    if len(enemies)!=1:return None
    e=enemies[0];cs=[c for c in e.get("fsms") or () if c.get("name")=="Control"]
    if len(cs)!=1 or cs[0].get("state")!="Slam Antic":return None
    tin=cs[0].get("t");vel=e.get("vel");pos=e.get("pos");flip=e.get("flipX")
    if (type(tin) not in (int,float) or not math.isfinite(tin) or tin<0
            or not isinstance(vel,(list,tuple)) or len(vel)!=2
            or any(type(v) not in (int,float) or not math.isfinite(v) or v!=0 for v in vel)
            or type(flip) is not bool or not isinstance(pos,(list,tuple)) or len(pos)<2
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in pos[:2])):return None
    earliest,extent=_slam_antic_bounds()
    if tin+(through-f+1)*FRAME_S>=earliest:return None
    cols=e.get("colliders");bodies=0
    if not isinstance(cols,(list,tuple)) or not cols:return None
    for col in cols:
        if not isinstance(col,dict) or type(col.get("enabled")) is not bool:return None
        if not col["enabled"]:continue
        name=str(col.get("name") or "")
        if name.startswith("Slam Collider"):return None
        damage=col.get("damage")
        if damage is None:
            if col.get("layer")!=13 or name not in {"Slam Range","Wake Range"}:return None
            continue
        if (not isinstance(damage,dict) or col.get("layer")!=11
                or not str(col.get("name") or "").startswith("Song Heavy Sentry")
                or type(damage.get("flags")) is not int or damage["flags"]!=0
                or type(damage.get("hazard_type")) is not int or damage["hazard_type"]!=1):return None # ENEMY only
        bodies+=1
    if bodies!=1:return None
    try:
        observed=body_box(e)
        if observed is None:return None
        # Antic stands up before it lunges. Bound every model pose, rather
        # than freezing an early crouched snapshot through the contact window.
        x0,x1,y0,y1=extent
        if not flip:x0,x1=-x1,-x0
        model=np.array([pos[0]+x0,pos[1]+y0,pos[0]+x1,pos[1]+y1])
        return np.r_[np.minimum(observed[:2],model[:2]),np.maximum(observed[2:],model[2:])]
    except (ValueError,TypeError,OverflowError):return None


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
    ended_reason:str|None=None

    @property
    def move(self):return MoveInstance(self.iid,self.fa,"RUNE_TRANSFER")
    def variables(self):
        # cs is the active Run's absolute CsPlan (the chain default is None for a fresh Run): never re-time a hook.
        return {k:v for k,v in asdict(self).items() if k not in {"origin","entry_k","press_k","contact_frame","ended_reason"}}


@dataclass(frozen=True)
class TransferGoal:
    target:int
    caster:int
    cast_fa:int
    cast_ta:object=None
    source_kind:str="CAST"
    source_move:object=None

    @property
    def window_from(self):
        """The frame the max_frames admission window counts from (ReturnGoal: the request's first issue)."""
        return self.cast_fa

    @property
    def responsibility(self):
        return self.source_move or MoveInstance(self.caster,self.cast_fa,"CC_CAST")


@dataclass(frozen=True)
class ReturnGoal(TransferGoal):
    """SSBOT_FORUM_TWO_RETURN_AIR (Task 179 #316, Sol seq 239 a): an L2 air ReturnRequest run with the SWITCH
    execution (source_kind SWITCH). Its source move has ENDED: source_move / cast_fa are attribution and the
    one-return-per-instance key only (cast_fa the source's real first frame, never rewritten), no source phase or
    instance gate and no exemption anywhere. return_f: the request's first issue frame, the admission window's start."""
    return_f:int=0

    @property
    def window_from(self):
        return self.return_f


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
    return hammer_on(state,goal.caster,goal.cast_ta,game)


def hammer_on(state,iid,cast_ta,game):
    """bounce_tail_pending's reading of one Clapper's slam (the instance whose antic began at cast_ta): a hammer stage still live or
    to come until its observed Slam 2 collider is gone. A missing Clapper or an unknown observation keeps it on."""
    source=next((e for e in clappers(state) if e["iid"]==iid),None)
    if source is None:return True
    st,tin=control(source)
    if st in AIR_ATTACK_STATES:
        new=(st=="Slam Antic" and cast_ta is not None and abs(game-tin-cast_ta)>3/60.)
        if not new:return True
    if not st:return True
    cols=source.get("colliders")
    if not isinstance(cols,list) or not cols:return True
    if any(str(c.get("name","")).startswith("Slam Collider") and c.get("enabled") is not False for c in cols):return True
    return not any(str(c.get("name","")).startswith("Song Heavy Sentry") and c.get("enabled") is True for c in cols)


def cross_hammer_pending(state,goal,game):
    """Task 182 seq 312 (#384; the person, plan 1.2.2): a real bounce on one Clapper (the goal's caster) in a chain the other
    Clapper's slam started (the responsibility that one's CC_SLAM): that slam still has a hammer stage live or to come
    (hammer_on on that Clapper and instance). That Clapper gone: no."""
    if (goal is None or isinstance(goal,ReturnGoal) or goal.source_kind!="BOUNCE" or goal.responsibility.family!="CC_SLAM"
            or goal.responsibility.target_iid==goal.caster):return False
    src=goal.responsibility.target_iid
    if not any(e["iid"]==src for e in clappers(state)):return False
    return hammer_on(state,src,goal.cast_ta,game)


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
                0<=f-previous.window_from<=cfg["max_frames"]):
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


# Control states whose root stays put (map2.clapper Sim: vx 0 at the Idle / antic / cast entries; the slam lunge
# runs from the Slam 0 entry to the Slam 2 entry). Any other state can carry the body away from its observed root.
STILL_ROOT_STATES=frozenset({"Idle","Spell Antic","Cast 1","Cast 2","Slam Antic","Slam 2","Slam Recover"})
POSE_MATCH_U=.005           # clapper_m2.json body rows are rounded to 0.001 u; a larger miss is another pose / clock
# A witnessed contact leaves one active frame after it: a press whose only contact is the window's last frame waits a
# tick (the falling hero meets the body at the same frame, earlier in the next window). The person's 10-31 rule:
# prefer waiting over a precise boundary; live 2701 hit on its last frame with no margin.
CONTACT_END_MARGIN_F=1


@lru_cache(maxsize=1)
def _body_knowledge():
    from ssbot.map2 import clapper as cm
    return cm.Know.load(),cm.NEXT,(cm.WALL_L,cm.WALL_R),cm.FLOOR


# Will Evade is checked at her first in-range Idle frame from EV_K[1]; an evade starts within this many frames of
# it. EMPIRICAL, not a physical guarantee: the fit's evade frames 15/16/17 (map2.clapper EV_K, 210/1200/1552) lie
# within one frame of the nominal gate; one more frame of margin.
RANGE_LAG_F=2


@lru_cache(maxsize=1)
def _idle_exits():
    """map2.clapper's Idle exits: Will Evade starts from Can Evade (EV_K) at her first in-range frame from EV_K[1]
    (shown False when none starts there); Idle Time (IDLE_K, the shorter no-buddy); her Slam Range trigger."""
    from ssbot.map2 import clapper as cm
    return cm.EV_K[0],cm.EV_K[1],cm.IDLE_K[False][0],cm.SLAM_RANGE


def idle_time_of(evidence):
    """Task 179 #317 (Sol seq 240 甲): the Idle Time a witness may use for one Idle instance. map2.clapper reads Idle
    Time at the Idle ENTRY (idle_buddy): IDLE_K[True] (68 earliest) only with causal evidence that the buddy was alive
    at that entry (the native B2 owner's per-instance record, NativeManualAirChain._observe_idle_evidence); unknown,
    absent or revoked evidence keeps the shorter no-buddy IDLE_K[False] (39)."""
    if isinstance(evidence,dict) and evidence.get("buddy") is True and evidence.get("hit") is None:
        from ssbot.map2 import clapper as cm
        return cm.IDLE_K[True][0]
    return _idle_exits()[2]


def in_slam_range(enemy,hero_box):
    """The hero box overlaps her Slam Range trigger (map2.clapper SLAM_RANGE about her root)."""
    _,_,_,(rx,ry0,ry1)=_idle_exits()
    pos=enemy.get("pos")
    hb=np.asarray(hero_box,float) if hero_box is not None else np.full(1,np.nan)
    if hb.shape!=(4,) or not np.isfinite(hb).all() or not isinstance(pos,(list,tuple)) or len(pos)<2:return False
    x,y=float(pos[0]),float(pos[1])
    return bool(hb[0]<x+rx and hb[2]>x-rx and hb[1]<y+ry1 and hb[3]>y+ry0)


def contact_body_witness(enemy,frames,idle_no_evade=False,idle_time=None,hull=False):
    """[frames,4] body boxes (x0,y0,x1,y1) a downslash must touch at f+d; nan rows have no witness.

    hull (Task 182 B13, b13_danger only): the same supported poses, their UNION per frame instead of their intersection, each
    frame together with the previous one (the box her own box must stay out of; never a hit witness).

    A hit witness needs the box EVERY supported pose shares, never the safety
    union. It reuses the fitted body runs and duration tables of the current
    Control state and its fixed successors (map2.clapper Know/NEXT, as
    forum_knife.slam_body_paths), sampled from three frames before to one after
    each frame (a run's change point falls a frame either way; a taller pose's
    root takes up to two more frames to rise), and intersects each frame with
    the previous one (damage reads the previous frame's colliders). Idle keeps
    its pose only up to its first modelled exit (_idle_exits): from Can Evade
    while Will Evade is unknown (live 2617: Idle k17 -> Evade Scuttle 15 u/s
    out of a k19 contact), else (idle_no_evade: the caller saw Will Evade
    shown False) up to Idle Time (idle_time: idle_time_of the instance's evidence; default the no-buddy 39). The root x stays
    where it is observed; every pose stands on the arena floor and is cut at
    its walls (map2.clapper FLOOR / WALL_L / WALL_R: its grounded root and
    wall push). A state that can move the root, or one without fitted runs,
    leaves that frame and every later one without a witness. Hit recoil is not
    modelled (the transform slides about 4 frames with vel 0). None when the
    observed collider does not match the fitted pose at its clock, facing and
    root, when it does not stand on the floor (beyond the bottom change its
    root may still be settling from), when the clock of a timed state is past
    its longest supported duration (outside the fit, never its successor), or
    when a field is unknown. Usable domain: grounded still Clappers in w13.
    """
    know,successor,(wall_l,wall_r),floor=_body_knowledge()
    cs=[c for c in enemy.get("fsms") or () if c.get("name")=="Control"]
    if len(cs)!=1:return None
    st=cs[0].get("state");tin=cs[0].get("t");pos=enemy.get("pos");vel=enemy.get("vel");flip=enemy.get("flipX")
    if (st not in STILL_ROOT_STATES or st not in know.body or type(tin) not in (int,float) or not math.isfinite(tin)
            or tin<0 or type(flip) is not bool or not isinstance(pos,(list,tuple)) or len(pos)<2
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in pos[:2])
            or not isinstance(vel,(list,tuple)) or len(vel)!=2 or any(type(v) not in (int,float) or v!=0 for v in vel)):
        return None
    try:observed=body_box(enemy)
    except (TypeError,ValueError,OverflowError):return None
    if observed is None or len(observed)!=4 or not np.isfinite(observed).all():return None
    face=1. if flip else -1.;x,y=float(pos[0]),float(pos[1])

    def world(state,j):
        b=know.box(state,max(j,0));xa,xb=x+face*float(b[0]),x+face*float(b[1])
        return (min(xa,xb),y+float(b[2]),max(xa,xb),y+float(b[3]))

    k=int(round(tin*60.))
    if st!="Idle":
        # Idle's one fitted pose holds at any clock; a timed pose seen past its
        # longest supported duration is outside the fit (178-R1).
        dur=know.durations(st)
        if dur is None or k>=dur[2]:return None
    if not any(max(abs(a-o) for a,o in zip(world(st,j),observed))<=POSE_MATCH_U for j in (k-1,k,k+1)):return None
    bottoms=[float(know.box(st,max(j,0))[2]) for j in range(k-3,k+2)]
    if abs(float(observed[1])-floor)>max(bottoms)-min(bottoms)+POSE_MATCH_U:return None

    poses={}

    def standing(state,j):
        # pure in (state, j) within this call; each one is sampled by up to five frames (Task 178 tick cost)
        if (state,j) not in poses:
            x0,_,x1,_=world(state,j);b=know.box(state,max(j,0))
            poses[state,j]=(max(x0,wall_l),floor,min(x1,wall_r),floor+float(b[3])-float(b[2]))
        return poses[state,j]

    can_evade,_,no_buddy,_=_idle_exits()
    idle_time=no_buddy if idle_time is None else int(idle_time)
    # A successor Idle has not reached Can Evade yet: its decision is still open.
    idle_until=idle_time if st=="Idle" and idle_no_evade else can_evade
    core=np.full((frames,4),np.nan);active={(st,k)}
    for d in range(frames):
        if any(s not in STILL_ROOT_STATES or s not in know.body or (s=="Idle" and j>=idle_until)
               for s,j in active):break
        boxes=[standing(s,q) for s,j in active for q in range(j-3,j+2)]
        if hull:c=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
        else:
            c=(max(b[0] for b in boxes),max(b[1] for b in boxes),min(b[2] for b in boxes),min(b[3] for b in boxes))
            if not (c[0]<c[2] and c[1]<c[3]):break
        core[d]=c;following=set()
        for s,j in active:
            if s=="Idle":following.add((s,j+1));continue
            dur=know.durations(s)
            if dur is None:following=None;break
            lo,_,hi=dur
            if j+1<hi:following.add((s,j+1))
            if j+1>=lo:following.add((successor.get(s),0))
        if following is None:break
        active=following
    out=core.copy()
    if hull:
        out[1:,:2]=np.fmin(core[1:,:2],core[:-1,:2]);out[1:,2:]=np.fmax(core[1:,2:],core[:-1,2:])
        return out
    out[1:,:2]=np.maximum(core[1:,:2],core[:-1,:2]);out[1:,2:]=np.minimum(core[1:,2:],core[:-1,2:])
    with np.errstate(invalid="ignore"):out[~((out[:,0]<out[:,2])&(out[:,1]<out[:,3]))]=np.nan
    return out


WALK_SPEED_TOL=1e-3   # the oracle's body velocity: DistanceWalk sets exactly +-WALK_SPEED (786 2519-2611: -8.0)
WALK_SIDE_U=.25       # her transform vs the box centre the roll keeps (0.09 u in 786) plus margin
WALK_BAND_U=.25       # DistanceWalk's hysteresis read one frame either way


class WalkSupport:
    """Task 179 Walk support domain for one observed walking Clapper (the person 11-05: stomp the walking one; #296).

    One future body set serves both uses. Her root moves at the observed DistanceWalk velocity (map2.clapper
    WALK_SPEED; one 0.02 s physics step per game frame or none, so every step count a frame either way), in the
    fitted Walk pose at her clock (three frames before to one after, as contact_body_witness), on the arena floor,
    each frame together with the previous one (damage reads the previous frame's colliders). It ends before the
    first frame any of those bodies could touch a wall (map2.clapper clamps the whole body there and her root stops).
    The hit core is the INTERSECTION of that set, the safety hull its UNION; a frame outside the domain is nan in
    both (no witness and no safety claim), never a union posing as a hit.

    The domain is constant-velocity walking only, facing the hero (else FaceObjectV2 may turn her at any frame). It
    ends one frame before her earliest Walk exit (WaitRandom from WALK_FAR_MIN, Attack Ready from CLOSE_K lo: she
    may then stop, attack or evade), and, for a given hero path, at the first frame that could turn her: her root
    crossed (FaceObjectV2 and DistanceWalk's side) or the distance band that keeps her direction left (DistanceWalk:
    forward while >= 5.5 u, back while <= 8.5 u). After a row is chosen, a stop, turn or other velocity before its
    contact re-selects (transfer_walk_support_lost). Sol's 21 demo bouts hold only 16 frames of a walker within 4 u
    of an airborne hero (14 inside this domain, her 3+ u above the body, none with an L2 stomp request): a narrow
    explicit domain, rarely used."""
    kind="walk"

    def __init__(self,core,hull,x,step,toward,walk_dir,info):
        self.core,self.hull,self.x,self.step=core,hull,x,step
        self.toward,self.walk_dir,self.info=toward,walk_dir,info

    def __call__(self,hero_x):
        """(core, hull) [frames,4] for one hero x path indexed like the roll (nan past the domain)."""
        from ssbot.map2 import clapper as cm
        hx=np.asarray(hero_x,float).reshape(-1);core=self.core.copy();hull=self.hull.copy()
        lo,hi=cm.WALK_DIST-cm.WALK_RANGE+WALK_BAND_U,cm.WALK_DIST+cm.WALK_RANGE-WALK_BAND_U
        for d in range(len(core)):
            if not np.isfinite(hull[d]).all():break
            seen=hx[max(d-1,0):d+2]
            roots=self.x+self.step*np.asarray(self.info["steps"][d],float)
            gap=(seen[:,None]-roots[None,:])*self.toward
            if (len(seen)<min(3,d+2) or not np.isfinite(seen).all() or gap.min()<=WALK_SIDE_U
                    or (self.walk_dir>0 and gap.min()<lo) or (self.walk_dir<0 and gap.max()>hi)):
                core[d:]=np.nan;hull[d:]=np.nan;break
        return core,hull


def walk_body_support(enemy,frames,hero):
    """WalkSupport for frames roll steps of a walking Clapper, or None (not Walk, unknown or off-fit observation,
    or the current hero position already outside the domain)."""
    from ssbot.map2 import clapper as cm
    know,_,(wall_l,wall_r),floor=_body_knowledge()
    cs=[c for c in enemy.get("fsms") or () if c.get("name")=="Control"]
    if len(cs)!=1 or cs[0].get("state")!="Walk" or "Walk" not in know.body:return None
    tin=cs[0].get("t");pos=enemy.get("pos");vel=enemy.get("vel");flip=enemy.get("flipX")
    hp=(hero or {}).get("pos")
    if (type(tin) not in (int,float) or not math.isfinite(tin) or tin<0 or type(flip) is not bool
            or not isinstance(pos,(list,tuple)) or len(pos)<2 or not isinstance(vel,(list,tuple)) or len(vel)!=2
            or not isinstance(hp,(list,tuple)) or len(hp)<1
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in (*pos[:2],*vel,hp[0]))):
        return None
    vx=float(vel[0])
    if abs(abs(vx)-cm.WALK_SPEED)>WALK_SPEED_TOL or vel[1]!=0:return None
    try:observed=body_box(enemy)
    except (TypeError,ValueError,OverflowError):return None
    if observed is None or len(observed)!=4 or not np.isfinite(observed).all():return None
    x,y=float(pos[0]),float(pos[1]);face=1. if flip else -1.;k=int(round(tin*60.))

    def raw(j,root):
        b=know.box("Walk",max(j,0));xa,xb=root+face*float(b[0]),root+face*float(b[1])
        return (min(xa,xb),y+float(b[2]),max(xa,xb),y+float(b[3]))

    if not any(max(abs(a-o) for a,o in zip(raw(j,x),observed))<=POSE_MATCH_U for j in (k-1,k,k+1)):return None
    if abs(float(observed[1])-floor)>POSE_MATCH_U:return None
    exit_k=min(cm.WALK_FAR_MIN,cm.CLOSE_K[0])-1   # a frame before her earliest Walk exit (the fit's 16-frame minimum)
    toward=1 if float(hp[0])>x else -1;walk_dir=1 if vx*toward>0 else -1
    if face!=toward:return None  # FaceObjectV2 turns her toward the hero at an unknown pause: not constant
    ratio=(1/60.)/cm.DT;step=vx*cm.DT
    core=np.full((frames,4),np.nan);hull=np.full((frames,4),np.nan);steps=[]
    for d in range(frames):
        if k+d>=exit_k:break
        n=(0,0) if d==0 else (max(0,math.floor((d-1)*ratio)),math.ceil((d+1)*ratio))
        boxes=[]
        for q in range(k+d-3,k+d+2):
            for m in n:
                b=raw(q,x+step*m)
                boxes.append((b[0],floor,b[2],floor+b[3]-b[1]))
        # #298 R1 (Astra): at a wall map2.clapper._clamp_x holds the whole body and its root stops, so the constant
        # velocity is no longer her motion. The domain ends before the first frame any supported body could touch a
        # wall; no cut box stands in for the clamped one (a cut box missed the clamped front by 0.32 u).
        if any(b[0]<=wall_l or b[2]>=wall_r for b in boxes):break
        steps.append(n)
        core[d]=(max(b[0] for b in boxes),max(b[1] for b in boxes),min(b[2] for b in boxes),min(b[3] for b in boxes))
        hull[d]=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    if not steps:return None
    out=core.copy();out[1:,:2]=np.maximum(core[1:,:2],core[:-1,:2]);out[1:,2:]=np.minimum(core[1:,2:],core[:-1,2:])
    with np.errstate(invalid="ignore"):out[~((out[:,0]<out[:,2])&(out[:,1]<out[:,3]))]=np.nan
    hu=hull.copy();hu[1:,:2]=np.minimum(hull[1:,:2],hull[:-1,:2]);hu[1:,2:]=np.maximum(hull[1:,2:],hull[:-1,2:])
    support=WalkSupport(out,hu,x,step,toward,walk_dir,
                        {"iid":enemy.get("iid"),"vx":vx,"flip":flip,"clock_k":k,"exit_k":exit_k,"toward":toward,
                         "walk_dir":walk_dir,"domain_frames":len(steps),"steps":steps})
    # the current frame must already be inside the domain (no witness that starts from a turn)
    first,_=support(np.full(min(frames,3),float(hp[0])))
    return support if np.isfinite(first[0]).all() else None


def press_now_row(sim,body,F,hold,side,attacking_target=False,clean=False,contact_ok=None,rejects=None,danger=None):
    """Shared velocity-aware downslash exit, not a fixed position or hit receipt.
    clean (Task 182, the plans' over route, Sol seq 255 F2): a row whose hero box meets the body at all before its contact is no
    row (51 real DownSlash hits in the bots' recordings: none had her box in the body before the hit).
    danger (Task 182 B13): one box, or one per roll index (stomp_rows: the still target's certain body, the row's own hit witness;
    nan: no claim): a row whose hero box enters it (b13_first_meet) on a step before contact-2 (the conditional rule's two
    frames) is no row.
    contact_ok (Task 183 seq 263/264, the seam strike): contact_ok(her x, contact index, the witness box there, the
    WalkSupport or None) -> (ok, bound) at the row's first contact, read at the same index as the hit witness; a row whose
    first contact fails it is no row in that direction (listed in rejects: direction, contact frame, her x, the bound).

    Try the existing toward row first. Only on failure try releasing direction
    and then countersteering. These are three fixed rows, not a timing search.
    Each uses the actual S0, in-flight prefix and hold filter. body is one box
    held still, or one box per roll step (contact_body_witness; a nan row has
    no witness), or a WalkSupport: then each row's own path selects the domain,
    the hit uses its core and the target-body margin its hull (same body set);
    other external safety remains the caller's.
    """
    from .knife_chain_vault import strike_program
    from . import pogo_model as PM
    if body is None:return None
    support=body if isinstance(body,WalkSupport) else None
    if support is None:
        body=np.asarray(body,float)
        if body.shape==(4,):
            if not np.isfinite(body).all():return None
        elif body.ndim!=2 or body.shape[1]!=4:return None
    direction=1 if side==B["R"] else -1 if side==B["L"] else 0
    pj=len(sim.prefix)+2
    # A previous swing can still be F_ATTACKING after its bounce. It cannot
    # license a new knife before the actual start state's cooldown expires.
    cd=float(np.asarray(sim.start).reshape(K.K,-1)[K.ATK_CD,0]);dt=float(sim.params.frame_time)
    if not math.isfinite(cd) or not math.isfinite(dt) or dt<=0 or cd>pj*dt+1e-9:return None
    directions=(direction,0,-direction) if direction else (0,)
    rows=[strike_program(F,hold,1,d or 1,16) for d in directions]
    for d,row in zip(directions,rows):
        if d==0:row["masks"]=[m&~(B["L"]|B["R"]) for m in row["masks"]]
    # One batched roll of the fixed rows (every rollout row is independent of the others; Task 178 tick cost).
    ro=sim.roll(np.asarray([row["masks"] for row in rows],np.int64))
    slashes=[PM.slash_poly(face,alt) for face in (-1,1) for alt in (False,True)]
    for i,(d,row) in enumerate(zip(directions,rows)):
        flags=ro.flags[i]
        attacking=(flags&K.F_ATTACKING)!=0
        fresh=(attacking[pj] and not attacking[pj-1]) or (attacking[pj+1] and not attacking[pj])
        if not fresh or flags[pj-1]&K.F_GROUND:continue
        core,hull=(body,body) if support is None else support(ro.pos[i,:,0])
        for j in range(pj+PM.ACTIVE[0],min(pj+PM.ACTIVE[1]+1-CONTACT_END_MARGIN_F,len(flags))):
            if flags[j]&K.F_GROUND:break
            b=core if core.ndim==1 else core[j] if j<len(core) else None
            if b is None or not np.isfinite(b).all():continue
            poly=np.array([[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]])
            if all(PM.meets(slash+ro.pos[i,j],poly) for slash in slashes):
                # a moving body is always margin-checked on its hull up to the target-contact exemption
                if (attacking_target or support is not None) and grazes_body(ro.box[i],hull,j-2):break
                if clean and enters_body(ro.box[i],hull,j):break
                if danger is not None and b13_first_meet(ro.box[i],danger,1,j-2) is not None:break
                cx=float(ro.pos[i,j,0]);bound=None
                if contact_ok is not None:
                    ok,bound=contact_ok(cx,j,b,support)
                    if not ok:
                        if rejects is not None:
                            rejects.append({"direction":int(d),"contact_frame":int(sim.fo+j),"contact_x":cx,"bound":bound})
                        break
                row.update(contact_frame=sim.fo+j,approach_direction=d,
                           contact_velocity=ro.vel[i,j].tolist())
                if contact_ok is not None:row.update(contact_x=cx,inner_bound=bound)   # the seam strike's record
                if support is not None:
                    row.update(support=support.kind,
                               walk={k:v for k,v in support.info.items() if k!="steps"})
                return row
    return None


def antic_strike_out_of_time(sim,enemy,hold_left,side,dash_free):
    """Task 179 #305 (live 179-L2 w13_walk179L2 1263e9e3: after the 2761 bounce the air Run flew toward 335470's Slam
    Antic for 32 ticks with current-step checks only and handed back at 2793, two frames before its lunge).

    True when the target stands in Slam Antic and, along this Run's own approach rows (toward, released and, with the
    air dash still free, toward with that one dash; J kept for the remaining hold), no frame from the earliest
    down-slash contact (press_now_row's index) until the earliest lunge (CL_SLAM minimum antic) lets ANY slash polygon
    touch its standing antic body (observed box union the fitted antic poses). That is the existing transfer strike's
    own domain (stationary_antic_body_for_hit_check), here tested generously, so True means no strike is left before
    the hammer. In Slam 0 / Slam 1 the lunge and hammer are already on and the body moves (stomp_plan licenses no row
    on a moving body), so it is True as well. Unknown inputs return False: the approach and its current-step gate
    continue as before."""
    from . import pogo_model as PM
    from .move_data import FRAME_S
    st,tin=control(enemy)
    if st in ("Slam 0","Slam 1"):return True
    if st!="Slam Antic" or type(tin) not in (int,float) or not math.isfinite(tin) or tin<0:return False
    S=np.asarray(sim.start,float).reshape(K.K,-1)
    if S.shape[1]!=1 or not np.isfinite(S).all():return False
    pos=enemy.get("pos");flip=enemy.get("flipX")
    if (type(flip) is not bool or not isinstance(pos,(list,tuple)) or len(pos)<2
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in pos[:2])):return False
    try:
        observed=body_box(enemy)
        earliest,(x0,x1,y0,y1)=_slam_antic_bounds()
    except (ValueError,TypeError,OverflowError):return False
    if observed is None:return False
    if not flip:x0,x1=-x1,-x0
    b=np.r_[np.minimum(observed[:2],[pos[0]+x0,pos[1]+y0]),np.maximum(observed[2:],[pos[0]+x1,pos[1]+y1])]
    poly=np.array([[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]])
    pj=len(sim.prefix)+2
    last=int(math.ceil((earliest-float(tin))/FRAME_S))-1   # the last rollout index still inside the standing antic
    if last<pj+PM.ACTIVE[0]:return True
    n=last-sim.off+1
    rows=[np.full(n,side,np.int64),np.zeros(n,np.int64)]
    if dash_free and side:
        dash=np.full(n,side,np.int64);dash[:2]|=B["DASH"];rows.append(dash)
    rows=np.asarray(rows,np.int64)
    rows[:,:max(0,min(int(hold_left),n))]|=B["J"]
    ro=sim.roll(rows)
    slashes=[PM.slash_poly(face,alt) for face in (-1,1) for alt in (False,True)]
    for i in range(len(rows)):
        for j in range(pj+PM.ACTIVE[0],min(last+1,ro.flags.shape[1])):
            if ro.flags[i,j]&K.F_GROUND:break
            if any(PM.meets(s+ro.pos[i,j],poly) for s in slashes):return False
    return True


def enters_body(boxes,body,until):
    """Her box meets the body itself (no margin) on a step before `until`. One box held still or one per step; nan: unknown, as met."""
    body=np.asarray(body,float)
    for i in range(1,min(until,len(boxes))):
        b=body if body.ndim==1 else body[i] if i<len(body) else None
        if b is None or not np.isfinite(b).all():return True
        h=boxes[i]
        if h[0]<=b[2] and h[2]>=b[0] and h[1]<=b[3] and h[3]>=b[1]:return True
    return False


def b13_danger(enemy,frames=None):
    """Task 182 B13: [frames,4] the box her own target body may occupy at each rollout index (0: the STATE frame): a still
    (STILL_ROOT_STATES) Clapper that is not attacking. Idle: its observed box at every index (one fitted pose). A timed still state:
    the union of its supported poses at each index (contact_body_witness hull: a caster's Spell Antic rises from top 6.19 to 7.78
    within a few frames), index 0 together with the observed box, past the fit the last box held. None for any other state (a
    walker, an evade, a jump, an attack: the existing rules), or an unknown box."""
    frames=B13_ROLL_F if frames is None else int(frames)
    st=control(enemy)[0]
    if st not in STILL_ROOT_STATES or st in AIR_ATTACK_STATES or frames<1:return None
    try:b=body_box(enemy)
    except (TypeError,ValueError,OverflowError):return None
    if b is None:return None
    b=np.asarray(b,float)
    if b.shape!=(4,) or not np.isfinite(b).all():return None
    out=np.tile(b,(frames,1))
    if st=="Idle":return out
    w=contact_body_witness(enemy,frames,idle_no_evade=True,hull=True)
    if w is None:return out
    w=np.asarray(w,float);last=b
    if w.ndim!=2 or w.shape[1]!=4:return out
    for d in range(frames):
        if d<len(w) and np.isfinite(w[d]).all():
            last=np.r_[np.minimum(b[:2],w[d][:2]),np.maximum(b[2:],w[d][2:])] if d==0 else w[d]
        out[d]=last
    return out


def b13_first_meet(boxes,body,start,stop,prot=None):
    """The first rollout index i in [start, stop) (start >= 1) where her box ENTERS the body: it meets it (exact overlap,
    enters_body's test) and did not at i - 1 (index 0: her box now). body: one box, or one per rollout index (b13_danger; past
    its end the last held). Already inside is no new meeting until she has left it: the pogo protection after a real bounce off
    it (not in the STATE or the start state), or a hit already taken. None when none.
    prot (B13B, package 2 after B13): one flag per rollout index, True while she cannot be hurt (the roll's F_INVULN: a real
    bounce's observed pogo protection POGO_OBS, a hit's i-frames, no input). The meeting is then her box in the body while
    unprotected after an index where it was out of it or protected: inside the body when the protection ends is a meeting there
    (c86 B01: in its body from 7098 after the bounce at 7097, the protection count 8 at 7097 down to 0 and the hit at 7107)."""
    a=max(start,1);n=min(stop,len(boxes))
    if n<=a:return None
    b=np.asarray(boxes,float)[a-1:n];body=np.asarray(body,float)
    if body.ndim==2:
        idx=np.minimum(np.arange(a-1,n),len(body)-1);body=body[idx]
        m=(b[:,0]<=body[:,2])&(b[:,2]>=body[:,0])&(b[:,1]<=body[:,3])&(b[:,3]>=body[:,1])
    else:m=(b[:,0]<=body[2])&(b[:,2]>=body[0])&(b[:,1]<=body[3])&(b[:,3]>=body[1])
    if prot is not None:
        p=np.asarray(prot,bool);m=m&~p[np.minimum(np.arange(a-1,n),len(p)-1)]
    hit=np.flatnonzero(m[1:]&~m[:-1])
    return a+int(hit[0]) if len(hit) else None


B13_HOLD_VY=-10.0   # a real bounce's hold: its STATE vy reads 17.4 (her real rise) and this frozen -10 in turn (s312 slam_notice)


def b13_bounce_hold(hero):
    """The STATE frames whose velocity is not her motion: vel exactly 0, 0 in the air (a hit's hit-stop, c86 ep13 41452; the first
    airborne frame of a jump, ep40 121806) and a bounce hold's frozen vy -10 reading (in a DownSpikeBounce or a Recoil Twirl clip
    alike: c86 ep13 41455-41456, ep33 101136 / 101139; between them the hold reads 17.4, her real rise, as a held jump does: ep14
    44485-44492). The model's start from such a velocity is wrong; the guard reads the next frame. A falling vy never reads -10
    exactly (it steps 1.2 from 17.4); a whole DownSpikeBounce clip can run through a fall with real values (p12 ep27 86686-86712)."""
    vel=(hero or {}).get("vel")
    if not isinstance(vel,(list,tuple)) or len(vel)<2:return False
    try:vx,vy=float(vel[0]),float(vel[1])
    except (TypeError,ValueError):return False
    return (vx==0. and vy==0.) or abs(vy-B13_HOLD_VY)<1e-3


def b13_held_back(x,e,sim,side,left):
    """The native adapter's transfer_side_held_back (knife_chain_air_native._transfer_offer) for a side key of the air link: on the
    plans' over route (plan_over_call), or with a casting target (HOOK_CAST_STATES, seq 312 active) once the small rune's opening
    is not pending, the side key goes out while 14 frames of the key held would carry her box into the target's observed body.
    True when the adapter would take this side key out (the guard then reads the keys without it)."""
    from .tactics import clapper_separated as SEP
    casting=bool(SEP.active(int(x.obs.f)) and control(e)[0] in HOOK_CAST_STATES and not opening_pending(x.v))
    if not (plan_over_call(x.v) or casting):return False
    body=body_box(e)
    if body is None:return False
    ro=sim.roll(np.full((1,14),int(side)|(B["J"] if left else 0),np.int64))
    return enters_body(ro.box[0],np.asarray(body,float),len(ro.box[0]))


def b13_landing(flags,start):
    """The first rollout index from start on with her on the ground (len(flags) when none)."""
    g=np.flatnonzero((np.asarray(flags)[start:]&K.F_GROUND)!=0)
    return start+int(g[0]) if len(g) else len(flags)


def b13_guard(x,strike_rows):
    """Task 182 B13 (design 2.2 / 2.3: the chain's own follow-up, no hand-back): the air link's look ahead at the Run's OWN target
    body. The Run's keys this tick (its side key, or a steer this guard chose earlier, with the jump hold it has left) are rolled
    B13_ROLL_F frames from the actual start, in-flight prefix and hold filter, to her landing. When her box enters the still target
    body (b13_danger; b13_first_meet: from outside it, already inside is no new meeting) on that roll (not read in a real bounce's
    hold, b13_bounce_hold):
      1. a down slash whose blade lands first: strike_rows(x) (the air link's stomp_rows, relaxed: the Run's own target even while
         the small rune's opening is pending, Idle's Will Evade taken as not evading, every other rule of the Run's rows as ever:
         no_strike, seam_only, the seam / bound predicates, a hit Idle, the B13 row rule on its certain body). Only within
         B13_STRIKE_F frames of F (farther the Run's own rows still have time): the strike link next;
      2. within B13_LEAD_F frames of F: steering, the first of releasing the side key and countersteering whose roll keeps her
         out of the body to her landing (the jump hold unchanged); later ticks keep that steer to the landing;
      3. within B13_LEAD_F with neither: the latest first meeting of the three (forced risk; a chain defect in the record).
    Farther than B13_LEAD_F with no strike: the Run's keys as they are (a strike row may come as she nears). The record goes
    to x.v["b13"] (the native adapter notes it); the guard never ends the Run. Returns a goto to the strike link or None.
    B13B (package 2 after B13, design 7.1): the meetings read her protection (b13_first_meet prot, the roll's F_INVULN). A meeting
    that is no entry from outside unprotected ("inside": in the body when the protection ends, or entered while protected) takes
    no strike (a down slash from inside the body) and no wait: the first of releasing and countersteering that keeps her out of it,
    else the latest (forced)."""
    if not B13 or x.v.get("_approach_only") or not hasattr(x.obs,"sim") or x.obs.ground:return None
    e=getattr(x.obs,"e",None)
    if e is None or control(e)[0] not in STILL_ROOT_STATES or control(e)[0] in AIR_ATTACK_STATES:return None
    if b13_bounce_hold(getattr(x.obs,"hero",None)):return None
    sim=x.obs.sim
    S=np.asarray(sim.start,float)
    if S.size!=K.K or not np.isfinite(S).all():return None
    st=control(e)[0]
    danger=b13_danger(e,len(sim.prefix)+1+B13_ROLL_F)   # one box per rollout index (a caster's pose grows: Spell Antic -> Cast)
    if danger is None:return None
    side=int(x.v.get("side") or 0);left=max(0,int(x.v["jump_until"])-int(x.obs.k))
    steer=x.v.get("b13_steer")
    # the keys the native adapter really sends: its transfer_side_held_back takes a side key out (b13_held_back)
    eff=lambda d:0 if d and b13_held_back(x,e,sim,d,left) else d
    planned=eff(side if steer is None else int(steer))
    counter=eff(B["L"] if side==B["R"] else B["R"] if side==B["L"] else 0)
    dirs=[planned]+[d for d in dict.fromkeys((0,counter)) if d!=planned]
    rows=np.zeros((len(dirs),B13_ROLL_F),np.int64)
    for i,d in enumerate(dirs):rows[i]=d
    rows[:,:min(left,B13_ROLL_F)]|=B["J"]
    ro=sim.roll(rows)
    off=int(sim.off)
    meets=[];inside=False
    for i in range(len(dirs)):
        stop=b13_landing(ro.flags[i],off)+1
        prot=(np.asarray(ro.flags[i])&K.F_INVULN)!=0 if B13B else None
        meets.append(b13_first_meet(ro.box[i],danger,1,stop,prot=prot))
        if B13B and i==0 and meets[0] is not None:inside=b13_inside_at(ro.box[i],danger,meets[0])
    if meets[0] is None:return None
    info={"f":int(x.obs.f),"meet_F":int(sim.fo+meets[0]),"lead":int(meets[0]-off),"planned":int(planned),"state":st,
          "opening":bool(opening_pending(x.v)),**({"inside":inside} if B13B else {})}
    out=strike_rows(x) if meets[0]-off<=B13_STRIKE_F and not inside else None
    if out is not None:
        row=x.v["row"]
        x.v.update(b13_steer=None,b13={**info,"kind":"strike","contact_F":int(row["contact_frame"]),"press_F":int(row["press_F"])})
        return out
    if meets[0]-off>B13_LEAD_F and not inside:
        x.v["b13"]={**info,"kind":"wait"}
        return None
    for i in range(1,len(dirs)):
        if meets[i] is None:
            x.v["b13_steer"]=int(dirs[i])
            x.v["b13"]={**info,"kind":"steer","steer":int(dirs[i])}
            return None
    best=max(range(len(dirs)),key=lambda i:meets[i])
    if best:x.v["b13_steer"]=int(dirs[best])
    x.v["b13"]={**info,"kind":"forced","steer":int(dirs[best]),"meets_F":[int(sim.fo+m) for m in meets]}
    return None


def b13b_flight(flags,start):
    """(takeoff, landing): her first airborne rollout index from start on and the first ground index after it; (None, len) when she
    never leaves the ground in the roll, (takeoff, len) when she does not land in it."""
    f=np.asarray(flags);air=np.flatnonzero((f[start:]&K.F_GROUND)==0)
    if not len(air):return None,len(f)
    t=start+int(air[0])
    return t,b13_landing(f,t)


def b13b_side_meet(boxes,danger,start,stop):
    """b13_first_meet in [start, stop) when that first entry is from the side: her box centre still below the body's top there
    (a landing on the head from above is the strike rows' business, not this check's)."""
    i=b13_first_meet(boxes,danger,start,stop)
    if i is None:return None
    b=np.asarray(boxes,float)[i];d=np.asarray(danger,float)
    top=d[min(i,len(d)-1),3] if d.ndim==2 else d[3]
    return i if (b[1]+b[3])/2.<top else None


def b13b_sprint_jump(runner,p,sim,enemy,k,link):
    """B13B: this tick's jump out of a held ground dash / sprint (propose's jump now with sprint_jump). Three key rows rolled
    B13_ROLL_F frames from the actual start, in-flight prefix and hold (transfer.render of the Run's link, from this tick's mask on):
      0. the plan: the sprint jump (DASH held into the jump);
      1. the dash let go: the same keys without DASH (an ordinary jump at the sprint's regain, the side key held);
      2. the dash and the side key let go (the jump alone; in the air the B13 guard steers off the body).
    Each is read against the still target's body (b13_danger) for an entry from the side (b13b_side_meet) up to her landing after the
    takeoff. Returns None (not checked: the target not still, an unknown start) or a record: kind "clear" (the plan does not enter),
    "guard" (it enters more than B13B_GUARD_F frames after its takeoff: the air link's B13 guard has its strike / steer ticks; the
    plan kept), "release" (it enters on the ground or within B13B_GUARD_F of the takeoff; the first of rows 1 and 2 that takes off
    and does not is the approved one: "row" 1 or 2 and its "side" key, the plan's or none; the caller sends that very row:
    sprint_jump off and that side key held through this flight, Sol REVIEW402), "forced" (no row does: the plan kept, a chain defect
    in the record)."""
    danger=b13_danger(enemy,len(sim.prefix)+1+B13_ROLL_F)
    if danger is None:return None
    S=np.asarray(sim.start,float)
    if S.size!=K.K or not np.isfinite(S).all():return None
    rows=np.zeros((3,B13_ROLL_F),np.int64)
    plan=np.asarray(render(runner,p,k,B13_ROLL_F,link),np.int64)
    rel=np.asarray(render(runner,replace(p,sprint_jump=False),k,B13_ROLL_F,link),np.int64)
    rows[0,:len(plan)]=plan;rows[1,:len(rel)]=rel;rows[2,:len(rel)]=rel&~(B["L"]|B["R"])
    ro=sim.roll(rows)
    off=int(sim.off);meets=[];takeoffs=[]
    for i in range(3):
        t,land=b13b_flight(ro.flags[i],off)
        takeoffs.append(t);meets.append(b13b_side_meet(ro.box[i],danger,1,land+1))
    F=lambda v:None if v is None else int(sim.fo+v)
    rec={"f":int(sim.f),"meet_F":F(meets[0]),"release_meets_F":[F(m) for m in meets[1:]],
         "takeoffs_F":[F(t) for t in takeoffs],"state":control(enemy)[0]}
    if meets[0] is None:return {**rec,"kind":"clear"}
    if takeoffs[0] is not None and meets[0]-takeoffs[0]>B13B_GUARD_F:return {**rec,"kind":"guard"}
    for i in (1,2):
        if meets[i] is None and takeoffs[i] is not None:
            return {**rec,"kind":"release","row":i,"side":int(p.side) if i==1 else 0}
    return {**rec,"kind":"forced"}


def b13_inside_at(boxes,body,i):
    """B13B: her box already in the body at rollout index i - 1, so the meeting at i (b13_first_meet with prot) is the protection ending
    around her, not an entry from outside (Sol REVIEW402: comparing the first meetings with and without the protection over the whole
    roll misnames a protected touch that she left before entering again from outside)."""
    if i is None or i<1:return False
    b=np.asarray(boxes,float)[i-1];d=np.asarray(body,float)
    d=d[min(i-1,len(d)-1)] if d.ndim==2 else d
    return bool(b[0]<=d[2] and b[2]>=d[0] and b[1]<=d[3] and b[3]>=d[1])


# Task 182 seq 312 (design 3.1; the person: after the two crossed she came down on the other one, bouts 18 / 19 / 41 / 47): the route an
# approach Run commits to, read against the OTHER Clapper's body before her box reaches the target. The step gate reads one tick's key.
ROUTE_LINKS=frozenset({"air","walk","dash","jump"})
ROUTE_H=40               # frames of the Run's remaining planned keys rolled (the shadow probe's H40)
ROUTE_REACH_U=.5         # the strike cut: her box this near the target's body (carried at its STATE vx) has reached its target first
ROUTE_LAND_F=12          # frames past her own landing still read (bout 38: she landed at 122103 and the jumper came down on her at 122106-122108)
CLAPPER_G=84.            # u/s^2: a Clapper body in Jump / Air falls at this until its bottom meets the floor
ROUTE_FLOOR_Y=3.0        # the w13 floor (a body bottom at or below it is down)


def body_path(enemy,n):
    """[n+1, 4] the enemy's body box (x0, y0, x1, y1) from this STATE's frame (row 0) on: carried at its STATE vx (none in a still-root
    state); in Jump / Air ballistic at CLAPPER_G from its STATE vy until its bottom meets the floor, still from there. None: unknown."""
    try:box=body_box(enemy)
    except (TypeError,ValueError,OverflowError):return None
    if box is None or not np.isfinite(box).all():return None
    st=control(enemy)[0];vel=enemy.get("vel") or (0.,0.)
    try:vx,vy=float(vel[0]),float(vel[1]) if len(vel)>1 else 0.
    except (TypeError,ValueError,IndexError):return None
    if not (math.isfinite(vx) and math.isfinite(vy)):return None
    flying=st in ("Jump","Air")
    if st in STILL_ROOT_STATES:vx=0.
    if not flying:vy=0.
    out=np.empty((n+1,4));dx=dy=0.
    out[0]=box
    if not flying:
        # the common case without the Python loop: add.accumulate sums the same steps in the same order from the first one
        if n>0:
            dxs=np.add.accumulate(np.full(n,vx/60.))
            out[1:,0]=box[0]+dxs;out[1:,1]=box[1]+dy;out[1:,2]=box[2]+dxs;out[1:,3]=box[3]+dy
        return out
    for k in range(1,n+1):
        dx+=vx/60.
        if flying:
            vy-=CLAPPER_G/60.;dy+=vy/60.
            if box[1]+dy<=ROUTE_FLOOR_Y and vy<0:dy=ROUTE_FLOOR_Y-box[1];flying=False;vx=0.
        out[k]=(box[0]+dx,box[1]+dy,box[2]+dx,box[3]+dy)
    return out


def route_meets_other(boxes,limit,target_path,other_path):
    """Along her boxes 1..limit (row k: frame +k): the first k where her box meets the other body before it comes within ROUTE_REACH_U of the
    target body (x only: the cut), and that cut. (k or None, cut or None)."""
    n=min(int(limit),len(boxes)-1,len(target_path)-1,len(other_path)-1)
    if n<1:return None,None
    # all rows at once, the first row that stops the old row-by-row reading wins in its order (unknown box, the cut, the meeting)
    h=np.asarray(boxes,float)[1:n+1];t=np.asarray(target_path,float)[1:n+1];o=np.asarray(other_path,float)[1:n+1]
    bad=~np.isfinite(h).all(axis=1)
    cut=(h[:,2]>=t[:,0]-ROUTE_REACH_U)&(h[:,0]<=t[:,2]+ROUTE_REACH_U)
    meet=(h[:,0]<=o[:,2])&(h[:,2]>=o[:,0])&(h[:,1]<o[:,3])&(h[:,3]>o[:,1])
    stop=bad|cut|meet
    if not stop.any():return None,None
    i=int(np.argmax(stop))
    if bad[i]:return None,None
    return (None,i+1) if cut[i] else (i+1,None)


ROUTE_CLEAR_PAD_U=2.5    # route_cannot_meet: her start box this far short of the cut (the model's start box vs the STATE's, her travel)


def _carried_vx(enemy):
    """body_path's x speed for this enemy (none in a still-root state); None: unknown."""
    vel=enemy.get("vel") or (0.,0.)
    try:vx=float(vel[0])
    except (TypeError,ValueError,IndexError):return None
    if not math.isfinite(vx):return None
    return 0. if control(enemy)[0] in STILL_ROOT_STATES else vx


def route_cannot_meet(hero_box,target,other,n):
    """Task 182 seq 312, arithmetic before the roll (a per-tick check is made cheap first): True when route_meets_other can find no meeting
    over rows 1..n whatever route she takes. Her box starts clear on one side of the target's cut (its body grown by ROUTE_REACH_U, with
    ROUTE_CLEAR_PAD_U to spare), and over all n rows the other body's edge on her side stays at or beyond the target's edge on her side
    less ROUTE_REACH_U (both carried as body_path carries them: x moves at most vx * n frames, toward one side). Her box moves under a unit
    a frame and the cut is wider, so it cannot pass the cut without a row inside it, and the cut is read before the meeting in each row:
    every row before the cut is short of the other body. False: unknown or possible (the roll decides)."""
    if hero_box is None:return False
    try:tb=body_box(target);ob=body_box(other)
    except (TypeError,ValueError,OverflowError):return False
    if tb is None or ob is None or not (np.isfinite(tb).all() and np.isfinite(ob).all()):return False
    vt=_carried_vx(target);vo=_carried_vx(other)
    if vt is None or vo is None:return False
    span=float(n)/60.
    if hero_box[2]<tb[0]-ROUTE_REACH_U-ROUTE_CLEAR_PAD_U:
        return bool(ob[0]+min(0.,vo*span)>=tb[0]+max(0.,vt*span)-ROUTE_REACH_U)
    if hero_box[0]>tb[2]+ROUTE_REACH_U+ROUTE_CLEAR_PAD_U:
        return bool(ob[2]+max(0.,vo*span)<=tb[2]+min(0.,vt*span)+ROUTE_REACH_U)
    return False


def plan_over_call(run_vars):
    """The stomp entry of a jump plan's over route (SSBOT_FORUM_TWO_PLAN only): the near table's rule for this strike."""
    from .tactics import clapper_plans
    return bool(clapper_plans.ENABLED and run_vars.get("switch_stomp"))


def grazes_body(boxes,body,until):
    """The hero box enters her body grown by FOCUS_M on a step before `until` (contact-2).

    The external step scans the target body with that margin up to its
    target-contact exemption (contact-2..contact), so such a row is rejected
    there and the Run would recover (live w13_pose178 2679: the toward row came
    0.444 u from her front; the release row struck from 0.61 u). One box held
    still or one per step (nan: not checked here; the external step still is).
    """
    from .forum_v2 import FOCUS_M
    body=np.asarray(body,float)
    for i in range(1,min(until,len(boxes))):
        b=body if body.ndim==1 else body[i] if i<len(body) else None
        if b is None or not np.isfinite(b).all():continue
        h=boxes[i]
        if h[0]<b[2]+FOCUS_M and h[2]>b[0]-FOCUS_M and h[1]<b[3]+FOCUS_M and h[3]>b[1]-FOCUS_M:return True
    return False


def air_approach_keys(x):
    """One optional dash impulse, after a failed current strike exit.

    A once-per-Run coast probe selects the recipe, not safety or future hit.
    If the nominal directional coast already reaches above the observed body,
    retain the dash. Otherwise a far entry may spend its available air dash.
    All emitted keys still use the normal same-owner send and current-step gate.
    """
    side=int(x.v["side"]);left=max(0,int(x.v["jump_until"])-int(x.obs.k))
    steer=x.v.get("b13_steer") if B13 else None
    if steer is not None:
        # Task 182 B13: the body guard's steer (release or countersteer) replaces the side key to her landing; no new dash
        return int(steer)|(B["J"] if left else 0)
    mask=side|(B["J"] if left else 0)
    # A side approach has no strike/bounce to finish an irreversible air dash.
    # Keep the actual prefix/hold untouched; only decline a NEW dash impulse.
    if (x.v.get("_approach_only") or not hasattr(x.obs,"sim") or x.obs.ground or x.v.get("air_dash_decided")
            or opening_pending(x.v)):return mask   # #387: no dash before the small rune's opening hook
    sim=x.obs.sim;S=np.asarray(sim.start).reshape(K.K);h=x.obs.hero
    # #387 (the person 11-10: "弹起以后冲刺下劈施法那只"): after the opening's real hook and bounce the caster target may take the dash
    after_opening=bool(x.v.get("hook_done") and type(x.v.get("hooked_iid")) is int)
    if (side==0 or (x.v["iid"]==x.v["caster"] and not after_opening) or h.get("hero_accepting_input") is not True or not np.isfinite(S).all()
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
    if control(x.obs.e)[0]=="Slam Antic":
        # Task 179 #305 (live 179-L2 2761): an attacking target is struck on its standing antic or not at all. The coast
        # reaching above its body some time (the probe below) is not enough there: unless the coast rows can make a
        # down-slash contact before the earliest lunge, this Run spends its one air dash (the dash-lock scan decides).
        x.v["air_dash_decided"]=True
        if not antic_strike_out_of_time(sim,x.obs.e,left,side,False):return mask
        x.v["approach_recipe"]="air_dash"
        return mask|B["DASH"]
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


# Task 183 (Sol seq 261; the person, relayed): two Clappers close or overlapping, a real DownSlash bounce off one's own slam
# (CC_SLAM, the bounced one its source) and that same Clapper still the tactical target: the chain's follow-up prefers the
# MIDDLE. A reachable, safe standing place between the two real bodies: go and land there from the first legal key after
# the hammer tail; done only when she really lands between the two near body edges. No clean landing there now (no
# standable gap, or seq 265: a standable one whose landing routes are all blocked): the existing witnessed down-slash on
# the target's inner side by the seam, every tick until a middle landing is clean, each real bounce reading the gap again
# (the person, seq 265: go to the middle whether or not there is room; with room stand, without it down-slash and wait).
# Only when that action's own gate turns it down does a standable gap take the existing ordinary left / right landing post
# types (knife_chain_post_actions) from the current state, if one is legal; an owned landing re-chooses a clean middle.
FOLLOW_LINKS=frozenset({"middle","land"})
MIDDLE_PAD_U=.5          # forum_v2.FOCUS_M: the chosen landing box stays this far inside each near body edge
LAND_GAP_U=2.0           # Task 182 seq 289: a first middle landing aims this far, box to box, from the just-hit body's Idle pose facing her: inside the side slash's reach (3.12 u from her centre, 2.87 box to box; real hits 2.36 median)
LAND_BODY_U=2.2516       # its Idle body from the root toward her (map2.clapper Idle / Walk fit: every pose within root +- 2.2516; Task 179 #321)
FALL_SLASH_BOTTOM=6.2    # Task 182 seq 289 (the person: falling to its head height, one slash before the landing): her box bottom at the press no higher than this (its Idle top 6.92; slam_play's near slash_y 3.2 u over the standing y)
FALL_SLASH_X=3.02        # the side slash's reach from her centre (slam_play.SLASH_X 3.12), the last .1 spare
MIDDLE_HORIZON_F=96      # hold-and-release rows rolled (the live flights land within 60 frames of the tail end)
SEAM_TOL_U=.25           # the seam aim: no side key within this of the aim point
SEAM_INSET_U=.5          # the seam aim stays over the target body this far inside its near edge
MIDDLE_STEP_F=2          # release grid of the middle rows (0.275 u of landing at the 8.25 u/s air walk)
MIDDLE_SCAN_N=8          # middle rows scanned per batched raster pass, nearest the goal first, until one is clean
FOLLOW_SCAN_F=12         # an owned route's per-tick scan: its next 12 frames (the whole route was scanned when chosen)
HOLD_OUT_U=1.25          # Task 182 seq 312 #385: a held bounce follow-up (hold_over) drifts to her centre this far off the bounced body's outer
#                          edge, away from the slammer: her box 1.0 u off it, at least .75 u within SEAM_TOL_U of the aim (C12 sy12_122: at .75 she
#                          hung 0.28 u off N and a stray step met it; the floor vault over N clears from 1.0 u: s312/vault385pad.py)


def follow_scope(goal,target,close=False):
    """Task 183: a real bounce in a chain that a Clapper's own slam (CC_SLAM, the hammer whose responsibility the chain
    keeps) started, this Run's target being the goal's tactical target: the bounced one itself, or (seq 262) the other
    one when the two were close at the bounce (close: bounce_close when this Run started, the person's overlapping or
    close Clappers; seq 265 a narrow standable gap too; L2's cross-Clapper continuation to a distant one stays as it was).
    A later bounce of the chain (a seam strike on either) stays in scope, so every real bounce reads the gap again."""
    return bool(goal is not None and not isinstance(goal,ReturnGoal) and goal.source_kind=="BOUNCE"
                and goal.responsibility.family=="CC_SLAM" and goal.target==target and (target==goal.caster or close))


def bounce_close(state,goal,h):
    """Task 183 seq 262: at a BOUNCE Run's start, the two Clappers are close (close_pair; seq 265: a narrow standable gap
    too, so L2's cross target after a bounce in such a pair still gets the follow-up and its re-read of the gap)."""
    if goal is None or goal.source_kind!="BOUNCE":return False
    return close_pair(two_gap(state,goal.caster),_hero_box(h))


def two_gap(state,caster):
    """Task 183: the gap between the two Clappers' observed bodies seen from the bounced one. None: not two Clappers or
    a body unknown. direction: the key from the bounced one toward the other; lo / hi: the gap's world x edges (the left
    body's right edge, the right body's left edge; hi < lo when they overlap); seam: their midpoint."""
    es=clappers(state)
    if len(es)!=2:return None
    b=next((e for e in es if e["iid"]==caster),None)
    if b is None:return None
    o=next(e for e in es if e is not b)
    try:bb,ob=body_box(b),body_box(o)
    except (TypeError,ValueError,OverflowError):return None
    if bb is None or ob is None or not np.isfinite([*bb,*ob]).all():return None
    right=float(bb[0])+float(bb[2])>float(ob[0])+float(ob[2])
    lo,hi=(float(ob[2]),float(bb[0])) if right else (float(bb[2]),float(ob[0]))
    return NS(caster=b["iid"],other=o["iid"],direction=B["L"] if right else B["R"],lo=lo,hi=hi,width=hi-lo,
              seam=.5*(lo+hi),bounced=tuple(float(v) for v in bb),other_body=tuple(float(v) for v in ob),root=float(b["pos"][0]))


def _hero_box(h):
    box=(h or {}).get("box")
    if not isinstance(box,(list,tuple)) or len(box)!=4:return None
    box=tuple(float(v) for v in box) if all(type(v) in (int,float) for v in box) else None
    return box if box is not None and np.isfinite(box).all() and box[2]>box[0] else None


def standable(gap,hero_box):
    """Task 183: her box fits between the two near body edges with MIDDLE_PAD_U on each side."""
    return bool(gap is not None and hero_box is not None and gap.width>=hero_box[2]-hero_box[0]+2*MIDDLE_PAD_U)


def fall_slash_commands(sim,row,boxes,gap,atk_cd_s):
    """Task 182 seq 289 (the person: falling to the Clapper's head height, one side slash before the landing): the row's keys with a
    pre-landing side slash at the just-hit body, or None: the first command frame m of the fall (box bottom <= FALL_SLASH_BOTTOM, before the
    landing, the attack cooldown over by then) from which its Idle body lies inside the slash's reach: one turn frame (the key toward it, m - 1), then
    the press (two frames, attack and the key toward it, as slam_play's near slash). row: the keys through the landing; boxes: the row's rollout
    (index sim.off + m). (commands, m). The caller rolls and scans the changed row again before it is used."""
    toward=B["L"] if gap.direction==B["R"] else B["R"]
    edge=gap.root+(LAND_BODY_U if gap.direction==B["R"] else -LAND_BODY_U)
    ready=max(1,int(math.ceil(max(float(atk_cd_s or 0.),0.)*60.))-2)
    row=np.asarray(row,np.int64)
    for m in range(ready,len(row)-1):
        b=boxes[sim.off+m]
        if not np.isfinite(b).all() or b[1]>FALL_SLASH_BOTTOM:continue
        centre=.5*(b[0]+b[2])
        if abs(centre-edge)>FALL_SLASH_X:continue
        out=row.copy();out[m-1]=toward;out[m:m+2]=B["A"]|toward
        return out,m
    return None


def near_landing_goal(gap,hero_box):
    """Task 182 seq 289 (the person: the blade after a dodge must connect): where a first middle landing aims. Still the
    gap between the two bodies, but the point LAND_GAP_U (box to box: her half width added) from the just-hit body's near
    edge as it will stand when she lands (Idle, turned to face her: root + LAND_BODY_U, so its slam pose now does not move the
    aim), the existing landing attack's reach, when that point lies on that body's side of the centre; a narrower gap keeps
    its centre, never squeezed toward the other body. Only the candidates' order: the rows, the whole-route scan for all
    owners, MIDDLE_PAD_U and an owned route's goal stay as they are."""
    off=LAND_BODY_U+LAND_GAP_U+.5*(hero_box[2]-hero_box[0])
    goal=gap.root+off if gap.direction==B["R"] else gap.root-off
    return gap.seam if (goal-gap.seam)*(1. if gap.direction==B["R"] else -1.)>=0. else goal


# seq 265: the person's close pair. Live 0ed5c779 3495 / 4156 / 4431 gaps 5.58 / 4.27 / 7.79 u and Sol seq 261's w13_331
# windows 9.16 / 6.91 u are close; the cross-Clapper continuation's tested pairs (17 u and more) are not. The transfer's
# own near / far split (rune_transfer STOMP dash_min_root 12.0: beyond it the approach dashes in).
CLOSE_PAIR_GAP_U=12.


def small_gap(gap):
    """Task 182 seq 312 #385 (the person 11-10, Sol seq 326; L2 plan "所有翻入/返回中间的共享小间隙后手"): the two facing body edges at most
    clapper_separated.TIER_U apart (overlapping always): a return into the middle takes one down slash aligned with the seam (gap.seam),
    whatever it meets, before any middle landing (no double-hit proof, no standing-gap proof). The L2 side reads the same value
    (clapper_separated.seam_return)."""
    from .tactics import clapper_separated as SEP
    return bool(gap is not None and SEP.active() and gap.width<=SEP.TIER_U)


def close_pair(gap,hero_box):
    """Task 183 seq 265: the two Clappers are close: no standable gap between them (seq 262), or a standable one at most
    CLOSE_PAIR_GAP_U wide. Only a close pair takes the seam strike on the target's inner side; a wider pair keeps the
    follow-up as it was (its middle landing first, the strike anywhere witnessed, the ordinary landing)."""
    return bool(gap is not None and (not standable(gap,hero_box) or gap.width<=CLOSE_PAIR_GAP_U))


ROOT_ORDER_EPS_U=.01     # the two Clappers' roots closer than this: which one is on the left is unknown


def _root(state,iid):
    e=next((e for e in clappers(state) if e["iid"]==iid),None)
    pos=None if e is None else e.get("pos")
    if not isinstance(pos,(list,tuple)) or not pos or type(pos[0]) not in (int,float) or not math.isfinite(pos[0]):return None
    return float(pos[0])


def seam_bound(sign,roots,witness):
    """Task 183 seq 264: the seam strike's inner bound at one contact index: the supported root range there (a WalkSupport's
    roots at that index; a still one's observed root) and the centre of the hit witness box at the same index; on the
    inner side of all of them. None when the side is unknown (sign 0) or a value is not finite."""
    roots=np.asarray(roots,float).reshape(-1)
    if sign==0 or not len(roots) or witness is None or not np.isfinite(roots).all():return None
    centre=.5*(float(witness[0])+float(witness[2]))
    if not math.isfinite(centre):return None
    return min(float(roots.min()),centre) if sign<0 else max(float(roots.max()),centre)


def seam_geometry(state,goal,target,close=False):
    """Task 183: where the existing witnessed down-slash goes when she cannot land between the two now, on the TARGET's inner
    side (the side facing the other Clapper). sign (seq 264): from the two real ROOTS' order (bodies overlapping deeply can
    swap their centres' order); roots within ROOT_ORDER_EPS_U: unknown (0), no seam strike row at all. aim: the x it is
    aimed from, next to the seam: her centre her half width plus MIDDLE_PAD_U clear of the other body's near edge, kept
    SEAM_INSET_U inside the target body (seq 262: aimed at the seam itself she came down on the other body; SEAM_TOL_U more,
    so stopping short of the aim still keeps MIDDLE_PAD_U); body edges, never the order. The inner bound itself (seq
    263/264) is read per strike row at its own first contact index (seam_bound): her x there must lie on the inner side of
    the target's supported root(s) and of the hit witness's centre; a row that would strike it from the outer side first is
    no seam strike (bound here: the current frame's, for the record). The person: a hit from the inner side turns it to face
    inward, so its evade may go outward (observed, never assumed). The target is L2's (the bounced one, or the other one in
    its cross-Clapper continuation); no search for another side. seq 265 (the person: go to the middle whether or not there
    is room): a close pair's standable gap too (close_pair), its aim then next to the target's near edge; the follow-up
    takes a clean middle landing first whenever one exists (NativeManualAirChain._follow_decide), this is for the ticks it
    does not. None outside the follow-up scope or for a wider pair."""
    if not follow_scope(goal,target,close):return None
    gap=two_gap(state,goal.caster);hb=_hero_box(state.get("hero"))
    if gap is None or hb is None or not close_pair(gap,hb) or target not in (gap.caster,gap.other):return None
    tb,nb=(gap.bounced,gap.other_body) if target==gap.caster else (gap.other_body,gap.bounced)
    other=gap.other if target==gap.caster else gap.caster
    root,oroot=_root(state,target),_root(state,other)
    if root is None or oroot is None:return None
    x0,_,x1,_=tb;nx0,_,nx1,_=nb;half=.5*(hb[2]-hb[0])
    if abs(root-oroot)<=ROOT_ORDER_EPS_U:
        return NS(aim=None,sign=0,root=root,other_root=oroot,bound=None)
    right=root>oroot                                       # the target on the right: its left side is the inner one
    sign=-1 if right else 1
    bound=seam_bound(sign,[root],tb)
    if small_gap(gap):aim=gap.seam                         # #385 (Sol seq 326): the shared small-gap strike, aligned with the seam itself
    elif x1-x0<=2*SEAM_INSET_U:aim=.5*(x0+x1)
    else:
        clear=half+MIDDLE_PAD_U+SEAM_TOL_U                 # stopping anywhere within SEAM_TOL_U still keeps MIDDLE_PAD_U
        aim=max(x0,nx1)+clear if right else min(x1,nx0)-clear
        aim=min(max(aim,x0+SEAM_INSET_U),x1-SEAM_INSET_U)
    return NS(aim=aim,sign=sign,root=root,other_root=oroot,bound=bound)


def seam_aim(state,goal,target,close=False):
    """Task 183: seam_geometry's aim, or None."""
    seam=seam_geometry(state,goal,target,close)
    return None if seam is None else seam.aim


def aim_side(x,aim):
    return 0 if abs(aim-x)<=SEAM_TOL_U else B["R"] if aim>x else B["L"]


def _landing_index(flags,off):
    ground=np.flatnonzero(((np.asarray(flags)&K.F_GROUND)!=0)&(np.arange(len(flags))>=off))
    return int(ground[0]) if len(ground) else None


def air_dash_free(sim):
    """Task 183: her one air dash is free now and nothing of a DASH press is in flight or held (air_approach_keys' test:
    after a real DownSlash bounce ResetAirMoves gives it back)."""
    S=np.asarray(sim.start,float).reshape(-1)
    if S.shape[0]!=K.K or not np.isfinite(S).all() or S[K.GROUND]>0 or S[K.MODE]!=K.M_NORMAL or S[K.AIRDASHED]>0 or S[K.DASH_CD]>0:
        return False
    i=B["DASH"].bit_length()-1
    return not (int(sim.prefix[0])&B["DASH"] or sim.hold.latched[0,i] or sim.hold.desired[0,i] or sim.hold.pending[0,i])


def _meets(boxes,body):
    """Her boxes meet the body itself (no margin) on any row; one vectorized enters_body."""
    b=np.asarray(body,float)
    return bool(np.any((boxes[:,0]<=b[2])&(boxes[:,2]>=b[0])&(boxes[:,1]<=b[3])&(boxes[:,3]>=b[1])))


def middle_direction(hero_box,goal_x):
    """Task 183 seq 262: the key toward the middle's goal from where she is now: from above the bounced body it points at
    the other one; past the goal (or near the other one's edge) it dials back."""
    return B["L"] if .5*(hero_box[0]+hero_box[2])>goal_x else B["R"]


def middle_candidates(sim,gap,hero_box,goal_x,dash=False):
    """Task 183: from the first free mask frame hold the key toward the middle's goal (middle_direction) for r frames (r on
    a MIDDLE_STEP_F grid up to the held row's landing), then no key to the modelled ground; with dash (her air dash free)
    also the same rows opening with that one air dash (DASH on the first two frames, the key held at least that long). The
    rows whose modelled landing box lies inside the gap (MIDDLE_PAD_U from each near edge, both current bodies never
    entered on the way), nearest goal_x first, a plain hold before a dash: [(recipe, r, commands through the landing,
    landing rollout index, landing box, the row's boxes and flags from frame fo through the landing)]. The batched rollout
    is the model (knife_chain_air.model_path traces the same rows bit for bit: review183/eq183.py)."""
    d=int(middle_direction(hero_box,goal_x));n=MIDDLE_HORIZON_F
    kinds=["hold"]+(["dash"] if dash else [])
    full=np.full((len(kinds),n),d,np.int64)
    if dash:full[1,:2]|=B["DASH"]
    ends={}
    for i,(kind,f) in enumerate(zip(kinds,sim.roll(full).flags)):
        j=_landing_index(f,sim.off)
        if j is not None:ends[kind]=j-sim.off+1   # held through the landing: every longer hold is this row
    recipes=[(kind,r) for kind in kinds if kind in ends
             for r in sorted(set(range(2 if kind=="dash" else 0,ends[kind]+1,MIDDLE_STEP_F))|{ends[kind]})]
    if not recipes:return []
    n=min(n,max(ends.values())+8)   # an earlier release lands no later than the held row (her fall does not change)
    rows=np.zeros((len(recipes),n),np.int64)
    for i,(kind,r) in enumerate(recipes):
        rows[i,:r]=d
        if kind=="dash":rows[i,:2]|=B["DASH"]
    ro=sim.roll(rows);out=[]
    for i,(kind,r) in enumerate(recipes):
        j=_landing_index(ro.flags[i],sim.off)
        if j is None:continue
        b=ro.box[i,j]
        if not (np.isfinite(b).all() and b[0]>=gap.lo+MIDDLE_PAD_U and b[2]<=gap.hi-MIDDLE_PAD_U):continue
        way=ro.box[i,1:j+1]
        if not np.isfinite(way).all() or _meets(way,gap.bounced) or _meets(way,gap.other_body):continue
        out.append((kind,r,rows[i,:j-sim.off+1].copy(),j,tuple(float(v) for v in b),
                    np.asarray(ro.box[i,:j+1],float).copy(),np.asarray(ro.flags[i,:j+1]).copy()))
    out.sort(key=lambda c:(abs(.5*(c[4][0]+c[4][2])-goal_x),c[0]!="hold",c[1]))
    return out


def route_path(sim,commands,box,flags):
    """Task 183: a candidate row as the B2 geometry scans it (origin fo, the in-flight prefix plus the row, its rolled
    boxes and flags; no event, no protection beyond the model's own flags)."""
    full=np.r_[np.asarray(sim.prefix,np.int64),np.asarray(commands,np.int64)]
    return NS(origin=int(sim.fo),stage="air_manual",commands=full,box=box,flags=flags,check_flags=flags,
              through=int(sim.fo)+len(full))


def landing_row(sim,direction):
    """Task 183: the ordinary left / right landing post type (knife_chain_post_actions.ordinary_post) from the current
    state: the key held to the modelled ground. (commands through the landing, landing rollout index) or None."""
    row=np.full((1,MIDDLE_HORIZON_F),int(direction),np.int64)
    ro=sim.roll(row);j=_landing_index(ro.flags[0],sim.off)
    if j is None:return None
    return row[0,:j-sim.off+1].copy(),j


def retreat_reserve(enemy,t_s,away):
    """Worst-case distance the target can move AWAY by t_s seconds after this observation (a bound, not a prediction).

    Evade Scuttle runs 15 u/s straight back from her (the owning Control FSM); a running one keeps only its remaining
    (double) time, any other state may start one at once; an observed walk away is the floor. Only the time to the
    ray counts: no whole-backstep deduction, no fixed 7 / 8 u."""
    st,tin=control(enemy)
    if type(t_s) not in (int,float) or not math.isfinite(t_s) or t_s<0 or away not in (-1,1):
        raise ValueError("unknown retreat input")
    rem=EVADE_MAX_S
    if st=="Evade Scuttle" and type(tin) in (int,float) and math.isfinite(tin):rem=max(0.,EVADE_MAX_S-float(tin))
    vel=enemy.get("vel") or [0.,0.]
    vx=float(vel[0]) if type(vel[0]) in (int,float) and math.isfinite(vel[0]) else 0.
    return max(EVADE_U_S*min(float(t_s),rem),max(0.,vx*away)*float(t_s))


HOOK_CAST_STATES=frozenset({"Spell Antic","Cast 1","Cast 2"})   # Task 182 seq 312 #387: a caster in its small-rune cast (the person: it cannot evade)
HOOK_CAST_SPAN_F=72      # #387: a small-rune cast's earliest end from its first frame (Spell Antic 43-44 + Cast 1 5-6 + Cast 2 25 frames: ep46
#                          132 147799-147873, J30 474 101845-101917): the caster's "move" label stands for its body no later than this


def needle_passes(sim,hooked,F0,toward,gap):
    """#387 (Sol seq 341, k387_hookN: the caster's branch assumed N off the ray while its scan still met N standing): the needle can pass
    the hooked one to the caster behind it only if the hooked one can leave the ray by the needle's latest hit (P + HOOK_LATE_F + the
    throw frame, map2.strike): its worst-case retreat from this observation (retreat_reserve, the face check's own bound: Evade Scuttle
    15 u/s straight back) reaches the caster's near face (gap). Jump Antic leaves the ground 29+ frames after it starts, past the hit.
    As in face_hook_check, a pose change (a crouch at a new state's entry, 6.194 against the Idle 6.916) is outside this bound."""
    from ssbot.map2 import strike as SK
    t=(int(F0)+HOOK_PRESS_AFTER_F+HOOK_LATE_F+SK.HOOK_THROW_F-int(sim.f))*float(sim.params.frame_time)
    return retreat_reserve(hooked,max(t,0.),toward)>=gap


def hook_iid(v,move_target,watch=None):
    """#387 (Sol seq 335): the body this Run's aimed hook takes, apart from the Move's target (the caster the Run strikes after the
    bounce, its responsibility instance unchanged): the hook watch's identity recorded at the hook's send, else the Run's (the
    opening's hooked one once face_hook_check_any set it: the B2 identity ray before the send), else the Move's own target (every other
    face hook). Read by the B2 identity veto, the hook watch's hit evidence, the hook step / entry model anchor and the recovery."""
    w=(watch or {}).get("hook_iid")
    if type(w) is int:return w
    h=(v or {}).get("hooked_iid")
    return h if type(h) is int else move_target


# #387: the opening's hook checks that only get worse as she closes in (she is past the face or too near it to press): the opening is
# lost for this Run and its ordinary down slash takes over (a caster right beside her is struck, not jumped past)
OPENING_LOST=frozenset({"target body behind the ray origin","face inside claw_strike's 0.5 u press minimum",
                        "antic drift inside the target body margin"})


def hooked_body(v,move_target,watch=None):
    """#387: the body the sent hook actually took (the watch's Harpoon hit: the planned one or the opening's other body behind it on
    the ray, knife_chain_face_hook.hook_alt), else the planned one (hook_iid). The hooked-body window and the recovery read it."""
    h=(watch or {}).get("hook_hit_iid")
    return h if type(h) is int else hook_iid(v,move_target,watch)


def opening_pending(v):
    """#387: the small rune's opening (GoalPrefs.hook_open this tick) whose hook is not done yet and still possible: no down-slash row
    and no air dash before it (Sol seq 335: the opening goes first; after the real hook and bounce, or once it is lost, the Run's
    ordinary rules: its dash down slash). The rising side down slash (opening_slash) is the opening's own row."""
    return bool(v.get("hook_open")) and not v.get("hook_done") and not v.get("opening_lost")


def _walk_support_lost(x,e):
    """Task 179: a Walk-supported row before its contact while that body left the constant-velocity Walk (stop, turn, other velocity)."""
    row=x.v.get("row")
    if not isinstance(row,dict) or row.get("support")!="walk" or x.obs.f>=row["contact_frame"]:return False
    w=row["walk"];vel=e.get("vel")
    return not (control(e)[0]=="Walk" and isinstance(vel,(list,tuple)) and len(vel)==2
                and vel[0]==w["vx"] and vel[1]==0 and e.get("flipX")==w["flip"])


def _rising(x):
    """#387 ("上升段"): her jump is still held (the Run's hold, J at the next key) or she still moves up."""
    S=np.asarray(x.obs.sim.start,float).reshape(-1)
    held=int(x.v.get("jump_until",0))-int(x.obs.k)>0
    return bool(held or (S.shape[0]==K.K and np.isfinite(S[K.VY]) and S[K.VY]>0))


def slash_iid(v,move_target):
    """#387 (the person 11-10: "如果太近就改成起跳，上升段在怪的侧面下劈不松开跳"): the body this Run's chosen down slash strikes: the
    opening's rising side down slash on the body too near to hook (N or F) while that row runs, else the Move's own target. Read by
    the B2 DownSlash hit attribution (the Move, its target and its responsibility stay the caster's)."""
    s=(v or {}).get("slash_iid")
    return s if type(s) is int else move_target


def face_hook_check_any(sim,hero,ents,F0,toward,bombs=None,next_key=None):
    """Task 182 seq 312 #387 (the person 11-10, Sol seq 333: the small rune's opening): one high Clawline toward the caster that takes the
    ray's first body of the observed Clappers, F or N, whichever it is (B2's identity ray at the press pose), then face_hook_check on that
    body in the "top" band with a caster in its cast held still. (ok, why, info) with info["hooked_iid"] (the hooked one, kept apart from
    the caster the Run strikes after the bounce). next_key: the key the Run sends at F0 if it does not hook now (the "top" band's next
    press)."""
    from .knife_chain_hook_target import first_ray_body
    info={}
    if toward not in (-1,1):return False,"unknown hook direction",info
    try:bodies=[(e.get("iid"),body_box(e)) for e in ents or ()]
    except (TypeError,ValueError,OverflowError):return False,"observed bodies unknown",info
    if not bodies or any(type(i) is not int or b is None or not np.isfinite(b).all() for i,b in bodies):
        return False,"observed bodies unknown",info
    tk=B["R"] if toward>0 else B["L"];j0=sim.off+HOOK_PRESS_AFTER_F
    ro=sim.roll(np.full((1,HOOK_PRESS_AFTER_F+1+HOOK_LATE_F),tk,np.int64))
    if ro.box.shape[1]!=j0+HOOK_LATE_F+1:return False,"press pose index mismatch",info
    try:first=first_ray_body([float(v) for v in ro.box[0,j0]],toward,[(i,[float(v) for v in b]) for i,b in bodies])
    except ValueError as exc:return False,"B2 identity ray unchecked: "+str(exc),info
    if first is None:return False,"no body on the hook ray",info
    hooked=next(e for e in ents if e.get("iid")==first[0])
    ok,why,info=face_hook_check(sim,hero,hooked,F0,toward,bombs,bodies,high_band="top",cast_still=True,next_key=next_key)
    info["hooked_iid"]=int(first[0])
    return ok,why,info


def face_hook_check(sim,hero,enemy,F0,toward,bombs=None,bodies=None,*,high_band=False,cast_still=False,next_key=None):
    """A cheap gate for one aimed Clawline at P=F0+1 against the OBSERVED target face; never a hit certificate.

    Her pose comes from the actual S0 / in-flight prefix rolled with the turn key and must stay in the measured
    Clawline entry (knife_chain_empty_needle). Two existing rays must take the target: the B2 CLAW identity veto's at
    P's key-frame pose (first_ray_body over every observed Clapper body), and the hooked-Clawline model's (map2.strike:
    her box centre after hero2's antic drift, her held box bottom, RAY_U) at the needle's hit P+8 / 9 of a press
    applied 0 .. 2 frames late, in every physics-step phase class, against the observed body moved AWAY by the
    target's worst-case retreat from this observation to that frame. With bombs, no lit small rune may meet her
    HeroBox (rune_bombs.occupied) between the press and the farthest stop until the latest control.
    high_band (Task 179 #308, Sol seq 229 with Root's parameters; entry_attack=stomp target switches only): the held
    foot height of every late-application branch must also lie in their common band, from the existing floor hover and
    the small runes' danger top + BOMB_M up to the target ray band (the ray's low edge under the body top), at its
    middle or higher: on a rising jump the earliest tick that reaches the middle and passes all the above; a jump that
    never reaches it, or no band at all, is unsupported (no lower hook instead). high_band "top" (#387, the small rune's
    opening): the whole band, its upper edge: on a rising jump the last press still wholly in it (next_key: the key sent at
    F0 when not hooking), falling at once. cast_still (#387): a caster in its cast is a still face. (ok, why, info)."""
    from ssbot.knowledge import hero2 as H2
    from ssbot.map2 import strike as SK
    from . import claw_strike as CS
    from .knife_chain_hook_target import first_ray_body
    from .rune_bombs import HB_HX
    from .forum_v2 import FOCUS_M
    info={}
    hero=hero or {};can=hero.get("can") or {};silk=hero.get("silk")
    if can.get("harpoon") is not True:return False,"harpoon unavailable",info
    if type(silk) not in (int,float) or not math.isfinite(silk) or silk<1:return False,"silk unavailable",info
    if hero.get("hero_accepting_input") is not True:return False,"input not accepted",info
    clocks=[c for c in enemy.get("fsms") or () if isinstance(c,dict) and c.get("name")=="Control"]
    if len(clocks)!=1:return False,"target motion/clock unknown",info
    st=clocks[0].get("state");tin=clocks[0].get("t")
    velocity=enemy.get("vel")
    if (not isinstance(velocity,(list,tuple)) or len(velocity)!=2
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in velocity)
            or type(tin) not in (int,float) or not math.isfinite(tin) or tin<0):
        return False,"target motion/clock unknown",info
    still=bool(cast_still and st in HOOK_CAST_STATES)   # #387: a caster in its cast stands (no retreat reserve), a hookable face
    if st not in HOOK_TARGET_STATES and not still:return False,"target state outside the face-hook scope",info
    reserve_of=(lambda t,away:0.) if still else (lambda t,away:retreat_reserve(enemy,t,away))
    body=body_box(enemy);iid=enemy.get("iid")
    seen=[(iid,body)] if bodies is None else list(bodies)
    if (iid not in [i for i,_ in seen] or
            any(type(i) is not int or b is None or not np.isfinite(b).all() for i,b in seen)):
        return False,"observed body unknown",info
    if toward not in (-1,1):return False,"unknown hook direction",info
    tk=B["R"] if toward>0 else B["L"];P=int(F0)+HOOK_PRESS_AFTER_F;j0=sim.off+HOOK_PRESS_AFTER_F
    ro=sim.roll(np.full((1,HOOK_PRESS_AFTER_F+1+HOOK_LATE_F),tk,np.int64))
    if ro.box.shape[1]!=j0+HOOK_LATE_F+1:return False,"press pose index mismatch",info
    S=np.asarray(ro.final[:,0],float);mode=int(S[K.MODE])
    if ((ro.flags[0,j0:]&K.F_GROUND).any() or mode not in (K.M_NORMAL,K.M_SPRINT) or (mode==K.M_SPRINT and S[K.PHASE]>1.)
            or S[K.SHUT]!=0 or S[K.XVX]!=0 or int(S[K.FACE])!=toward):
        return False,"press state outside the measured Clawline entry",info
    box=[float(v) for v in ro.box[0,j0]];xp=.5*(box[0]+box[2])
    front,back=(float(body[0]),float(body[2])) if toward>0 else (float(body[2]),float(body[0]))
    info.update(press_F=P,x_press=xp,bb_press=box[1]-CS.FLOOR,body_top=float(body[3])-CS.FLOOR)
    if (back-xp)*toward<=0:return False,"target body behind the ray origin",info
    if (front-xp)*toward<.5:return False,"face inside claw_strike's 0.5 u press minimum",info
    try:first=first_ray_body(box,toward,[(i,[float(v) for v in b]) for i,b in seen])
    except ValueError as exc:return False,"B2 identity ray unchecked: "+str(exc),info
    if first is None or first[0]!=iid:return False,"B2 identity ray does not take the target first",info
    names=("ray_margin","late_f","hit_after_press_f","phase","x_ray","held_bb","retreat_reserve","t_ray")
    worst=None;ext=0.;centres=[];helds=[]
    for d in range(HOOK_LATE_F+1):
        b=ro.box[0,j0+d];x0=.5*float(b[0]+b[2]);bb0=float(b[1]);half=.5*float(b[3]-b[1])
        vx0,vy0=(float(v) for v in ro.vel[0,j0+d])
        if not -19.6<=vy0<=17.4:return False,"press state outside the measured Clawline entry",info
        held=float(SK.hold_bb(bb0,vy0));centres+=[bb0+half,held+half];helds.append(held)
        if held-CS.FLOOR<CS.CsCfg().ray_lo:return False,"held height below claw_strike's floor hover",info
        for h in (SK.HOOK_HIT_F,SK.HOOK_THROW_F):
            t=(P+d+h-int(sim.f))*float(sim.params.frame_time)
            r=reserve_of(t,toward);moved=np.asarray(body,float)+toward*np.array([r,0.,r,0.])
            for ac in range(6):
                vx=min(max(vx0,-20.),20.)*H2.CLAW_ANTIC_DECEL[0];x=x0
                for k in range(1,h+1):
                    for _ in range(SK.steps_of(k,ac)):vx*=H2.CLAW_ANTIC_DECEL[0];x+=vx*H2.FDT
                ext=max(ext,(x-xp)*toward)
                row=((x+toward*SK.RAY_U-front-toward*r)*toward,d,h,ac,x,held-CS.FLOOR,r,t)
                if worst is None or row[0]<worst[0]:worst=row
                if h==SK.HOOK_THROW_F and (front-x)*toward<HB_HX+FOCUS_M:
                    info.update(zip(names,row))
                    return False,"antic drift inside the target body margin",info
                if not SK.ray_meets(x,held,toward,moved):
                    info.update(zip(names,row))
                    band=moved[1]<held+SK.RAY_BAND[1] and moved[3]>held+SK.RAY_BAND[0]
                    return False,("face out of the modeled ray after the retreat reserve" if band
                                  else "held height outside the observed face band"),info
    info.update(zip(names,worst))
    lo=CS.FLOOR+CS.CsCfg().ray_lo                      # the high band's floor hover (raised by the runes below)
    hi=float(body[3])-SK.RAY_BAND[0]                   # its top: the ray's low edge still under the body top
    if bombs is not None and len(bombs):
        from . import rune_bombs as RB
        t_end=(P+HOOK_LATE_F+HOOK_CTRL_LAST_F-int(sim.f))*float(sim.params.frame_time)
        stop=((front-xp)*toward+reserve_of(t_end,toward)-min(v.gap for v in SK.HOOK_VARIANTS)-SK.HALF_W)
        far=max(ext,min(stop,ext+SK.DASH_MAX_STEPS*SK.DASH_STEP_U))
        xs=np.linspace(xp,xp+toward*far,int(np.ceil(far/.25))+2)[:,None]   # samples finer than the HeroBox width
        ks=np.arange(P,P+HOOK_LATE_F+HOOK_CTRL_LAST_F+1)-int(sim.f)
        rows=np.asarray(bombs,float).reshape(-1,6);info.update(rune_far=far)
        if any(RB.occupied(rows,xs,y,ks,RB.BOMB_M).any() for y in centres):
            return False,"hook path meets a lit small rune",info
        # runes under the hook corridor (centre below its top), lit during the hook window, whose grown circle reaches
        # its horizontal path: the feet stay above their top + BOMB_M (runes above the corridor: the check above)
        a,z=min(xp,xp+toward*far),max(xp,xp+toward*far);reach=rows[:,3]+HB_HX+RB.BOMB_M
        under=((rows[:,4]<=ks[-1])&(rows[:,5]>=ks[0])&(rows[:,1]+reach>=a)&(rows[:,1]-reach<=z)
               &(rows[:,2]<hi))
        if under.any():lo=max(lo,float((rows[under,2]+rows[under,3]).max())+RB.BOMB_M)
    if high_band:
        mid=.5*(lo+hi)
        info.update(band_lo=lo-CS.FLOOR,band_hi=hi-CS.FLOOR,band_mid=mid-CS.FLOOR,
                    held_low=min(helds)-CS.FLOOR,held_high=max(helds)-CS.FLOOR)
        if not lo<hi:return False,"high hook unsupported: no common held band",info
        if max(helds)>=hi:return False,"high hook: held above the band",info
        if high_band=="top":
            # #387 (the person 11-10: "跳到能钩到怪的尽量高出钩吧"; Sol seq 333: the usable band's upper edge, its existing margins): every
            # held height in the band (its floor: the hover over the small runes); on a rising jump the last such press: it waits while
            # the next tick's press (next_key at F0, then the turn key; without one the turn key) lies wholly in the band and higher
            vy_p=float(ro.vel[0,j0,1]);info.update(band_mode=1.,vy_press=vy_p)
            if min(helds)<lo:return False,"high hook: held below the band floor",info
            if vy_p>0:
                rn=sim.roll(np.array([[tk if next_key is None else int(next_key)]+[tk]*(HOOK_PRESS_AFTER_F+1+HOOK_LATE_F)],np.int64))
                if rn.box.shape[1]!=j0+HOOK_LATE_F+2:return False,"press pose index mismatch",info
                nxt=[float(SK.hold_bb(float(rn.box[0,j0+1+d][1]),float(rn.vel[0,j0+1+d][1]))) for d in range(HOOK_LATE_F+1)]
                info.update(next_held_low=min(nxt)-CS.FLOOR,next_held_high=max(nxt)-CS.FLOOR)
                if min(nxt)>=lo and max(nxt)<hi:
                    return False,"high hook: a higher press in the band follows",info
        elif min(helds)<mid:return False,"high hook: held below the band middle",info
    return True,"ok",info


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

    def seam_contact(x,store=True):
        """Task 183 seq 263/264: on a seam tick the row's first contact must be on the target's inner side. The bound is
        read at that row's own contact index, the index its hit witness is read at (seam_bound): a walking target's
        WalkSupport roots there (the support's own step counts; no other predictor), a still one's observed root, and
        the witness box's centre. An unknown side or a contact index without supported roots turns the row down. The
        turned-down rows go to x.v["seam_rejects"] for the record (not with store False: B13's second look). (predicate or
        None, rejects list or None)"""
        seam=x.v.get("seam_inner")
        if not seam:return None,None
        root,sign=float(seam[0]),int(seam[1]);rejects=[]
        if store:x.v["seam_rejects"]=rejects

        def inner(cx,j,witness,support):
            if support is None:roots=[root]
            else:
                steps=support.info.get("steps") or ()
                if not 0<=j<len(steps):return False,None
                roots=support.x+support.step*np.asarray(steps[j],float)
            bound=seam_bound(sign,roots,witness)
            return bound is not None and (cx-bound)*sign>=0.,bound
        return inner,rejects

    def bound_contact(x,inner,rejects,store=True):
        """Task 182 seq 312 #385 (the person's 1.2.2: down slash N outside the range, before it unlocks): a row counts only with her
        centre at its first contact on her side of bound_x ((x - bound_x) * sign >= 0) and that contact by frame by_f (x.v["strike_bound"]),
        together with the seam predicate when there is one; the turned-down rows go to the same record. (predicate, rejects)"""
        sb=x.v.get("strike_bound")
        if not sb:return inner,rejects
        bx,sg,by_f=float(sb[0]),int(sb[1]),int(sb[2])
        fo=int(x.obs.sim.fo)
        if rejects is None:
            rejects=[]
            if store:x.v["seam_rejects"]=rejects

        def bounded(cx,j,witness,support):
            if (cx-bx)*sg<0. or fo+j>by_f:return False,bx
            return (True,None) if inner is None else inner(cx,j,witness,support)
        return bounded,rejects

    @prims.action("transfer_stomp_plan",doc="one press-now row against the currently observed body; not a hit receipt")
    def stomp_plan(x):
        return stomp_rows(x)

    def stomp_rows(x,relaxed=False):
        """stomp_plan's row choice. relaxed (Task 182 B13: b13_guard only, when the Run's own keys would put her into its still target's
        body first): the Run's own target even while the small rune's opening is pending (no opening slash: the hook did not fire this
        tick and she is coming down on the caster), Idle's Will Evade taken as not evading (if it evades the blade misses and the body
        has left: no worse than landing on it) with this Run's in-range record left untouched, every other rule as ever (no_strike,
        seam_only, the seam and bound predicates, a hit Idle, the pose witness; their rejects not recorded twice). With B13 every row of
        a still target is no row when her box enters its certain body (the hit witness) before contact-2."""
        if x.v.get("_approach_only") or x.v.get("no_strike") or not hasattr(x.obs,"sim") or x.obs.ground:return None
        # #387 (Sol seq 335): the small rune's high hook opening first (face_hook); its own row only: the rising side down slash on the
        # body too near to hook (the person 11-10, opening_slash), from the earliest press, the jump held (press_now_row's left)
        slash=x.v.get("opening_slash") if opening_pending(x.v) and not relaxed else None
        if opening_pending(x.v) and slash is None and not relaxed:return None
        tgt=x.obs.e
        if slash is not None:
            tgt=next((e for e in getattr(x.obs,"ents",None) or () if e.get("iid")==slash),None)
            if tgt is None or not _rising(x):
                # (falling with no rising side slash found, or that body gone: the opening is lost, the Run's own down slash next tick)
                x.v["opening_lost"]="no rising side down slash";x.v["opening_slash"]=None
                return None
        if not relaxed:x.v["slash_iid"]=None
        # Task 183 seq 268: the middle return's give-way (seam_only) is for a seam row only: no seam_inner this tick (not a
        # close pair now), no row on any side; a seam row is held to the target's inner side below (seam_contact)
        if x.v.get("seam_only") and not x.v.get("seam_inner"):return None
        from . import pogo_model as PM
        inner0,rejects0=seam_contact(x,store=not relaxed)
        inner,rejects=bound_contact(x,inner0,rejects0,store=not relaxed)
        # Task 182 seq 312 #386: a seam-kind bound (the shared seam strike) is the preferred contact, never a ban on the stomp over the body:
        # with no row meeting it (the seam side out of reach before the contact) the target's ordinary rows whose contact has her centre over
        # its body (sy23_seam 131555-131570: every row turned down over N's outer half, the side key held back, she fell onto N unstruck);
        # never a contact on its side from beside it (sy24_seam 131524: a side contact low beside N, the bounce's approach then met N).
        # 1.2.2's "outside" bound stays a hard limit.
        sb=x.v.get("strike_bound")
        soft=bool(sb) and len(sb)>3 and sb[3]=="seam"
        if not relaxed:x.v["seam_bound_fallback"]=False

        def over_body(cx,j,witness,support):
            if not float(witness[0])<=cx<=float(witness[2]):return False,None
            return (True,None) if inner0 is None else inner0(cx,j,witness,support)
        side=x.v.get("strike_dir") or x.v["side"]   # #385: 1.2.2's rows toward the target from the aim (the air key may be none there)
        if control(tgt)[0]=="Walk":
            if relaxed:return None   # (B13 guards still bodies only)
            # Task 179: the explicit constant-velocity Walk domain (WalkSupport); outside it no row, the
            # existing approach continues and the next tick re-selects. Never the still-body witness below.
            prefix=getattr(x.obs.sim,"prefix",None)
            support=(None if prefix is None else
                     walk_body_support(tgt,len(prefix)+3+PM.ACTIVE[1],getattr(x.obs,"hero",None)))
            if support is None:return None
            row=press_now_row(x.obs.sim,support,x.obs.F,max(0,int(x.v["jump_until"])-int(x.obs.k)),side,clean=plan_over_call(x.v),
                              contact_ok=inner,rejects=rejects)
            if row is None and soft:
                row=press_now_row(x.obs.sim,support,x.obs.F,max(0,int(x.v["jump_until"])-int(x.obs.k)),side,clean=plan_over_call(x.v),
                                  contact_ok=over_body,rejects=rejects0)
                x.v["seam_bound_fallback"]=row is not None
            if row is None:return None
            x.v["row"]=row;x.v["slash_iid"]=slash
            return {"do":"goto","to":"strike"}
        # The witness keeps the observed root and follows the fitted pose of
        # the current Control state. A moving/unknown body cannot license a
        # fresh row; keep the existing approach instead. This is not a motion
        # prediction or permission to rewrite an absolute row.
        enemy=tgt;velocity=enemy.get("vel")
        controls=[c for c in enemy.get("fsms") or () if c.get("name")=="Control"]
        if (not isinstance(velocity,(list,tuple)) or len(velocity)!=2
                or not all(type(v) in (int,float) and math.isfinite(v) for v in velocity)
                or velocity[0]!=0. or len(controls)!=1
                or not isinstance(controls[0].get("state"),str)
                or not controls[0]["state"] or controls[0]["state"] in {"Walk","Evade Scuttle"}):return None
        left=max(0,int(x.v["jump_until"])-int(x.obs.k))
        # Will Evade shown False needs this Run's own CONTINUOUS in-range observations of this Idle instance from
        # the gate (EV_K[1]) through RANGE_LAG_F; leaving her range, a missing tick or an unknown box restarts the
        # collection, a new Idle (or a hit, which leaves Idle) starts over; once shown it holds to this Idle's end.
        st0,t0=control(enemy);no_evade=bool(relaxed);f0=getattr(x.obs,"f",None)
        if not relaxed and st0=="Idle" and type(t0) in (int,float) and math.isfinite(t0) and type(f0) is int:
            k0=int(round(t0*60.));key=[enemy.get("iid"),f0-k0]
            w=x.v.get("idle_in_range")
            if not (isinstance(w,dict) and w.get("key")==key):w={"key":key,"start":None,"last_f":None,"done":False}
            if not w["done"]:
                inside=in_slam_range(enemy,(getattr(x.obs,"hero",None) or {}).get("box"))
                if not inside:w["start"]=None
                elif w["start"] is None or w["last_f"]!=f0-1:w["start"]=k0
                w["last_f"]=f0 if inside else None
                w["done"]=w["start"] is not None and k0>=max(w["start"],_idle_exits()[1])+RANGE_LAG_F
            x.v["idle_in_range"]=w;no_evade=w["done"]
        # Task 179 #317: the Idle instance's evidence (the native owner's record): a hit on this Idle since its entry
        # revokes it (a real hit on an Idle provokes Dmg Attack in the hit frame); the buddy at its entry sets Idle Time
        ev=getattr(x.obs,"idle_ev",None) if st0=="Idle" and tgt is x.obs.e else None   # (#387: the Run target's record only)
        if isinstance(ev,dict) and ev.get("hit") is not None:return None
        body=contact_body_witness(enemy,len(x.obs.sim.prefix)+3+PM.ACTIVE[1],idle_no_evade=no_evade,
                                  idle_time=idle_time_of(ev))
        if body is None:return None
        # The external step scans an ATTACKING target body with its margin (owner kind move); match it.
        # Task 182 B13: a still target's CERTAIN body (this hit witness: the poses every timing shares) is out of bounds before
        # contact-2 for every row (b13_first_meet); the guard's look ahead reads the possible one (b13_danger). None when off
        danger=body if B13 else None
        row=press_now_row(x.obs.sim,body,x.obs.F,left,side,attacking_target=st0 in AIR_ATTACK_STATES,clean=plan_over_call(x.v),
                          contact_ok=inner,rejects=None if relaxed else rejects,danger=danger)
        if row is None and soft:
            row=press_now_row(x.obs.sim,body,x.obs.F,left,side,attacking_target=st0 in AIR_ATTACK_STATES,clean=plan_over_call(x.v),
                              contact_ok=over_body,rejects=None if relaxed else rejects0,danger=danger)
            if not relaxed or row is not None:x.v["seam_bound_fallback"]=row is not None
        if row is not None:
            x.v["row"]=row;x.v["slash_iid"]=slash
            return {"do":"goto","to":"strike"}
        return None

    @prims.action("transfer_opening_slash_missed",doc="#387: the opening's rising side down slash missed (the body evaded): back to the "
                                                      "air link, rising on, the hook after its attack recovery; not a hit receipt")
    def opening_slash_missed(x):
        row=x.v.get("row");s=x.v.get("slash_iid")
        if type(s) is not int or not isinstance(row,dict):return None
        e=next((b for b in getattr(x.obs,"ents",None) or () if b.get("iid")==s),None)
        # it evaded: its walk support gone before the contact, the body gone, or no hit by the miss deadline
        if not (e is None or _walk_support_lost(x,e) or x.obs.f>row["press_F"]+int(x.cfg["STOMP"]["miss_after"])):return None
        x.v.update(row=None,slash_iid=None,opening_slash=None,opening_slash_done=True,opening_slash_missed_f=int(x.obs.f))
        return {"do":"goto","to":"air"}

    @prims.gen("transfer_air_keys",doc="same-owner optional one-shot air dash; never a new jump or umbrella")
    def air_keys(x,m):return m|air_approach_keys(x)

    @prims.action("transfer_body_guard",doc="Task 182 B13: the Run's own target body ahead to her landing: a blade-first down "
                                            "slash, else steering off, else the latest meeting; never a hand-back")
    def body_guard(x):return b13_guard(x,lambda x:stomp_rows(x,relaxed=True))

    @prims.gen("transfer_follow_keys",doc="Task 183: the bounce follow-up's checked absolute row (middle: the key toward "
                                          "the middle, an optional opening air dash, then none; land: the key to the ground); no strike")
    def follow_keys(x,m):
        fo=x.v.get("follow")
        if not isinstance(fo,dict):return m
        i=int(x.obs.F)-int(fo["F0"]);masks=fo.get("masks") or ()
        return m|(int(masks[i]) if 0<=i<len(masks) else 0)

    @prims.guard("transfer_antic_strike_late",doc="Task 179 #305: a Slam Antic target can no longer be struck on its "
                                                  "standing antic before its earliest lunge along this Run's approach")
    def antic_strike_late(x):
        if x.v.get("_approach_only") or not hasattr(x.obs,"sim") or x.obs.ground:return False
        S=np.asarray(x.obs.sim.start,float).reshape(-1)
        dash_free=bool(S.shape[0]==K.K and np.isfinite(S).all() and S[K.AIRDASHED]<=0 and S[K.DASH_CD]<=0
                       and (not x.v.get("air_dash_decided") or x.v.get("approach_recipe")=="air_dash"))
        return antic_strike_out_of_time(x.obs.sim,x.obs.e,max(0,int(x.v["jump_until"])-int(x.obs.k)),int(x.v["side"]),dash_free)

    @prims.gen("transfer_strike_row",doc="the original absolute downslash row; never re-time an already sent strike")
    def strike_row(x,m):
        row=x.v["row"];i=x.obs.F-row["F0"]
        return m|int(row["masks"][i] if 0<=i<len(row["masks"]) else x.v["side"])

    @prims.guard("transfer_walk_support_lost",doc="Task 179: a Walk-supported row before its contact while the target "
                                                  "left the constant-velocity Walk (stop, turn, other velocity): re-select")
    def walk_support_lost(x):
        if type(x.v.get("slash_iid")) is int:return False   # #387: the opening's rising side slash: transfer_opening_slash_missed
        return _walk_support_lost(x,x.obs.e)

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

    @prims.action("transfer_face_hook",doc="once per Run: an aimed Clawline at the next mask frame after the cheap face check; not a hit receipt")
    def face_hook(x):
        v=x.v
        if v.get("seam_only"):return None   # Task 183 seq 268: the middle return's give-way is a seam down-slash row only
        if v.get("strike_bound"):return None   # Task 182 seq 312 #385: 1.2.2's down slash outside the range (a hook pulls her to the face)
        # Task 182 seq 312 #387 (the person 11-10, Sol seq 333): the small rune's opening (L2's GoalPrefs.hook_open on this Run's caster target):
        # the high hook is the scene's own, whatever FACE_HOOK says, and may be aimed at the caster itself
        opening=bool(v.get("hook_open"))
        if (not (x.cfg.get("FACE_HOOK",False) or opening) or v.get("_approach_only") or v.get("no_strike") or v.get("cs") is not None
                or v.get("hook_done") or not hasattr(x.obs,"sim") or x.obs.ground or (v.get("iid")==v.get("caster") and not opening)):return None
        toward=1 if v.get("side")==B["R"] else -1 if v.get("side")==B["L"] else 0
        ents=getattr(x.obs,"ents",None)
        if opening:
            # the ray's first body (F or N) is the hooked one; the Run's target stays the caster (its dash down slash after the bounce).
            # The "top" band's next press: this link's own key at F0 when it does not hook (the side key, J while the jump is held)
            nk=int(v.get("side") or 0)|(B["J"] if int(v["jump_until"])-int(x.obs.k)>0 else 0)
            ok,why,info=face_hook_check_any(x.obs.sim,getattr(x.obs,"hero",None),ents,int(x.obs.F),toward,getattr(x.obs,"bombs",None),
                                            next_key=nk)
        else:
            try:bodies=None if ents is None else [(e.get("iid"),body_box(e)) for e in ents]
            except (TypeError,ValueError,OverflowError):bodies=[(None,None)]
            ok,why,info=face_hook_check(x.obs.sim,getattr(x.obs,"hero",None),x.obs.e,int(x.obs.F),toward,
                                        getattr(x.obs,"bombs",None),bodies,high_band=bool(v.get("switch_stomp")))
        v["face_hook_check"]={"ok":ok,"why":why,"opening":opening,**{k:float(w) for k,w in info.items()}}
        if not ok:
            if opening and why in OPENING_LOST and not v.get("opening_slash"):
                # #387 (the person 11-10: "如果太近就改成起跳，上升段在怪的侧面下劈不松开跳如果怪闪身还能继续上升，给出钩留出足够的冷却时间"):
                # too near to hook while she rises: one down slash on that body's side with the jump held (the next tick's stomp_plan, its
                # earliest row: the hook's attack recovery runs from there); a miss (it evaded) goes on rising to the hook. Falling, or
                # once that slash is spent: the opening is lost and the Run's own down slash takes over
                if _rising(x) and not v.get("opening_slash_done") and type(info.get("hooked_iid")) is int:v["opening_slash"]=int(info["hooked_iid"])
                else:v["opening_lost"]=why   # (the next tick's stomp_plan takes over)
            return None
        if opening:v["hooked_iid"]=int(info["hooked_iid"])
        from .claw_strike import CsPlan
        F0=int(x.obs.F)
        v["cs"]=CsPlan(F0,0,F0+HOOK_PRESS_AFTER_F,0,bb_press=info["bb_press"])
        v["air_dash_decided"]=True  # no air dash after an aimed hook in this Run
        from .knife_chain_face_hook import press_anchor
        hooked=x.obs.e if not opening else next((e for e in ents or () if e.get("iid")==v["hooked_iid"]),None)
        if hooked is None:return None
        # #387 (the person 11-10: "不管走路那只是否闪身肯定能钩到一只"): the opening's other body behind the hooked one on the ray, in its
        # cast (still), is the needle's body instead when the hooked one can leave the ray before the needle's hit (needle_passes); the
        # hook's checks then take it as the hooked body in that branch (knife_chain_face_hook.hook_alt). Otherwise the ray's first body is
        # the hooked one in every case: one branch (Sol seq 341, k387_hookN)
        alt=None
        if opening:
            other=next((e for e in ents or () if e.get("iid")!=v["hooked_iid"]),None)
            hb=body_box(hooked);ob=None if other is None else body_box(other)
            if hb is not None and ob is not None and control(other)[0] in HOOK_CAST_STATES:
                gap=(float(ob[0] if toward>0 else ob[2])-float(hb[0] if toward>0 else hb[2]))*toward
                if gap>=0. and needle_passes(x.obs.sim,hooked,F0,toward,gap):alt=int(other["iid"])
        v["hook_alt"]=alt
        # (#387: the hooked body's, F or N; a caster in its cast stands still: no retreat bound, as face_hook_check_any)
        v["hook_press"]=press_anchor(x.obs.sim,toward,F0,hooked,still=bool(opening and control(hooked)[0] in HOOK_CAST_STATES))
        if alt is not None and isinstance(v["hook_press"],dict):
            # the other branch (Sol seq 340): that caster itself, still; its "move"-labelled body exempt only through its cast's end
            v["hook_press"]["alt"]={"iid":alt,"body":[float(b) for b in body_box(other)],
                                    "move_until":int(v["cast_fa"])+HOOK_CAST_SPAN_F}
        return {"do":"goto","to":"claw"}

    @prims.gen("transfer_claw_keys",doc="the absolute CsPlan keys: turn key, CLAW for two frames; no J; never re-timed")
    def claw_keys(x,m):
        from .claw_strike import plan_mask
        cs=x.v.get("cs")
        if cs is None:return m
        return m|plan_mask(cs,int(x.obs.F),1 if x.v.get("side")==B["R"] else -1)

    @prims.guard("transfer_claw_slots_past")
    def claw_slots_past(x):
        cs=x.v.get("cs");return cs is not None and int(x.obs.F)>cs.f_press+1

    @prims.guard("transfer_hook_timeout")
    def hook_timeout(x):
        cs=x.v.get("cs");return cs is not None and int(x.obs.F)-cs.f_press>HOOK_TIMEOUT_F

    @prims.guard("transfer_hook_other")
    def hook_other(x):return x.v.get("hook_other_f") is not None

    @prims.action("transfer_hook_release",doc="actual control after the hook: back to the existing air / stomp rules; a hook hit or bounce is evidence only")
    def hook_release(x):
        cs=x.v.get("cs");h=getattr(x.obs,"hero",None) or {}
        clip=str((h.get("anim") or {}).get("clip",""))
        if cs is None or int(x.obs.F)-cs.f_press<=HOOK_CTRL_MIN_F:return None
        if h.get("hero_accepting_input") is not True or "harpoon" in clip.lower():return None
        if type(x.v.get("hook_seen_f")) is not int:return None
        if type(x.v.get("hook_hit_f")) is not int:
            return {"do":"abort","why":"transfer face hook ended without actual target Harpoon hit"}
        x.v["hook_done"]=True
        # Task 179 #308 (live 179-L3 2713: the target in Evade Scuttle, actual can.dash and the tracker's AIRDASHED 0 /
        # DASH_CD 0 agree): the hooked bounce restores the air dash, so face_hook's pre-hook "no air dash after an aimed
        # hook" is not carried across the lock; the air link's once-per-Run probe decides again from the actual state
        # after the hook (its dash-lock scan still gates the dash)
        x.v["air_dash_decided"]=False;x.v["approach_recipe"]=None
        return {"do":"goto","to":"air"}


def propose(runner,state,game,sim,target,ground,bombs,finished,goal=None,*,defer_jump=False,approach_only=False,
            idle_evidence=None,follow_release=False,no_strike=False,seam_only=False,hold_over=False,bound=None,hook_open=False):
    """One observed-distance recipe and a two-frame external path.

    hook_open (Task 182 seq 312 #387, the person 11-10 / Sol seq 333): this tick's small-rune opening on the caster (L2's
    GoalPrefs.hook_open): the Run's face hook may fire whatever cfg FACE_HOOK says, on the ray's first body of the two (F or N) in the
    "top" band (face_hook_check_any); the Run keeps the caster as its target.

    hold_over (Task 182 seq 312 #384, plan 1.2.2): a bounce follow-up held off the middle this tick (the other Clapper's slam
    still has a hammer stage: knife_chain_air_native._hold_over): no seam aim and no seam row; #385: the side key toward
    HOLD_OUT_U off the bounced body's outer edge (away from the slammer), none within SEAM_TOL_U of it.
    bound (Task 182 seq 312 #385, the person's 1.2.2 and Sol seq 326's seam strike; GoalPrefs.strike_bound): (aim_x, bound_x, sign,
    by_f, jump_hold, kind) for a stomp that is no bounce: the jump held jump_hold (1.2.2: a short one, its apex box just over the top,
    the strike near it; None: the stomp's own), in the air the
    side key only up to aim_x (no key within SEAM_TOL_U), the strike rows still tried toward the target (strike_dir), each kept only
    with her centre at its first contact on her side of bound_x and that contact by by_f (stomp_plan's bound_contact); no face hook.

    approach_only uses the same walk/dash/air keys without choosing a strike.
    Its sent Run keeps that intent until the native adapter's planned handoff.
    defer_jump remains for offline callers; neither cancels an existing sprint.
    idle_evidence (Task 179 #317): the native owner's per-Clapper Idle instance records; the strike witness reads the
    target's (idle_time_of; a hit since the instance's entry: no witness).
    follow_release (Task 183 seq 265): an owned bounce follow-up route (a FOLLOW_LINKS link) is released to the air link
    this tick: the seam approach and its witnessed inner down-slash, the route itself dropped.
    no_strike (Task 183 seq 267): no NEW strike this tick (no down-slash row, no face hook): the approach / positioning
    keys only; a strike row already chosen goes on (its absolute keys).
    seam_only (Task 183 seq 268): a new strike this tick only as a seam down-slash row (this tick's seam_inner, its first
    contact on the inner side: seam_contact); without seam_inner no row, and no face hook either way.
    """
    h=state.get("hero") or {};es=clappers(state);active=runner.run if runner.run is not None and runner.run.chain==PROGRAM else None
    approach_only=bool(active.v.get("_approach_only")) if active is not None else approach_only
    # Task 179 #308 (Sol seq 229): the entry_attack=stomp target switch (a SWITCH goal that is not the side approach)
    # aims its face hook in the high held band (face_hook_check high_band); other transfers keep their hook unchanged
    switch_stomp=(bool(active.v.get("switch_stomp")) if active is not None
                  else bool(goal is not None and goal.source_kind=="SWITCH" and not approach_only))
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
    # An accepted hook finishes in its own lock even if the target starts an ordinary move. The strike after actual
    # control re-reads the current body (stomp_plan); it is never admitted from a static Idle assumption.
    hook_locked=active is not None and active.link in HOOK_LINKS
    if target_state not in cfg["target_states"] and not (attacking and goal is not None and not ground) and not hook_locked:return None
    if sim.fo!=sim.f or sim.f!=state["f"] or len(sim.prefix)!=1:return None
    if int(sim.prefix[0])&~(B["L"]|B["R"]|B["J"]|B["DASH"]|B["D"]|B["A"]|(B["CLAW"] if hook_locked else 0)):return None
    hp=h.get("pos");vel=h.get("vel")
    if not isinstance(hp,(list,tuple)) or not isinstance(vel,(list,tuple)) or min(len(hp),len(vel))<2:return None
    if np.asarray(sim.start).shape not in ((K.K,),(K.K,1)) or not np.isfinite(sim.start).all() or not np.isfinite([game,*hp[:2],*vel[:2]]).all():return None
    cd=(h.get("tm") or {}).get("dash_cd")
    if type(cd) not in (int,float) or not math.isfinite(cd):return None
    if active is None:
        if h.get("hero_accepting_input") is not True:return None
        # #387 (the person 11-10, Sol seq 333): the small rune's opening runs on the caster itself, from the observed cast (its goal)
        observed=(goal is not None and (goal.target==target or (hook_open and goal.source_kind=="CAST" and goal.caster==target))
                  and goal.caster in {e["iid"] for e in es} and 0<=state["f"]-goal.window_from<=cfg["max_frames"])
        if not observed and (st!="Spell Antic" or tin>cfg["entry_cast_s"]):return None
        if ground and (int(sim.prefix[0])&B["J"] or state["act"]["hf"]["latched"]&B["J"]):return None
        cast_fa=goal.cast_fa if observed else max(0,state["f"]-int(round(tin*60.)))
        source=goal.caster if observed else other["iid"]
        # #387 (g387_C40 130618-130623: a plain transfer to the other one began on the cast before L2's 2.2 took the scene and spent
        # the cast): the opening has its own once-per-cast key
        opening_key=bool(hook_open and goal is not None and goal.source_kind=="CAST" and goal.caster==target)
        if ((source,cast_fa,"opening") if opening_key else (source,cast_fa)) in finished:return None
        side=B["R"] if enemy["pos"][0]>h["pos"][0] else B["L"]
        if bounce_entry and target==source and body[0]<=hp[0]<=body[2]:side=0
        p=TransferPlan(target,source,cast_fa,state["f"],game,
            side,2+int(math.ceil(max(0.,cd)*60.)),10000,10000,False,state["f"],0)
        link="walk" if ground else "air"
    else:
        if active.v["iid"]!=target:return None
        p=TransferPlan(**{k:active.v[k] for k in TransferPlan.__dataclass_fields__ if k in active.v},origin=state["f"],entry_k=int(round((game-active.v["ta"])*60.)))
        link=active.link
        if follow_release and link in FOLLOW_LINKS:link="air"   # Task 183 seq 265: the seam approach takes over the route
    if bounce_entry and target==p.caster and link!="strike":
        side=B["R"] if enemy["pos"][0]>hp[0] else B["L"]
        p=replace(p,side=0 if body[0]<=hp[0]<=body[2] else side)
        if hold_over:
            # Task 182 seq 312 #385 (the person's 1.2.2): the hold waits out the slammer's hammers off the bounced body's outer edge (straight
            # down over it the fall meets it; outward is away from the slammer): the side key toward HOLD_OUT_U off that edge, none near it
            out=1 if float(enemy["pos"][0])>float(other["pos"][0]) else -1
            p=replace(p,side=aim_side(float(hp[0]),(float(body[2]) if out>0 else float(body[0]))+out*HOLD_OUT_U))
    close=bool(active.v.get("follow_close")) if active is not None else bounce_close(state,goal,h)
    seam=None
    if bounce_entry and link!="strike" and not ground and not hold_over:
        seam=seam_geometry(state,goal,target,close)    # Task 183: the target's inner side by the seam (seq 265: a close pair)
        # seq 264: roots in the same place (side unknown): no aim, the original approach side stays and no seam row
        if seam is not None and seam.aim is not None:p=replace(p,side=aim_side(float(hp[0]),seam.aim))
    if bound is not None and not bounce_entry and link in {"jump","air"}:
        # Task 182 seq 312 #385 (the person's 1.2.2): the jump and the air no farther than the aim over the target's outer part
        p=replace(p,side=aim_side(float(hp[0]),float(bound[0])))
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
    early=None;b13b=None
    if link in {"walk","dash"} and ground:
        held_dash=bool(current_mode in (K.M_DASH,K.M_SPRINT) and int(sim.prefix[0])&B["DASH"])
        if held_dash:link="dash"
        gap=abs(enemy["pos"][0]-hp[0])
        # Observe the distance now. A model's eventual body intersection must
        # not make us release DASH or wait in front of the destination.
        cache=None if active is None else active.v.get("early_hook")
        early_due=False
        if cfg.get("FACE_HOOK",False) or hook_open:
            from .knife_chain_face_hook import early_jump_due
            early_due=early_jump_due(cache,k,target_state)
        if not (defer_jump or approach_only) and (gap<=cfg["STOMP"]["jump_root"] or early_due):
            hold=int(cfg["STOMP"]["jump_hold"]) if bound is None or bound[4] is None else int(bound[4])   # #385: 1.2.2's short jump
            p=replace(p,jump_k=k+2,jump_until=k+2+hold,sprint_jump=held_dash)
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
        # #387: the small rune's opening takes the same jump expansion (its first decision whose high hook passes: the "top" band, the
        # ray's first body of the two, the caster held still), whatever FACE_HOOK says ("起手就应该直接跳到高于小符文的高度然后钩怪的脸")
        if (((cfg.get("FACE_HOOK",False) and p.iid!=p.caster and target_state in HOOK_TARGET_STATES) or hook_open)
                and not (defer_jump or approach_only) and p.jump_k>k+2
                and (active is None or active.v.get("cs") is None)):
            from .knife_chain_face_hook import early_jump_stale,early_jump
            if early_jump_stale(cache,state["f"],target_state):
                early=early_jump(runner,p,sim,game,state,enemy,bombs,k,link,held_dash,
                                 high_band="top" if hook_open else switch_stomp,any_body=bool(hook_open))
                if early.get("ok") and early.get("defer_new_dash"):
                    p=replace(p,dash_k=k+10000)
                elif hook_open and early.get("near") and p.jump_k>k+2:
                    # #387 (the person 11-10: "如果太近就改成起跳"): too near to hook from any press of the jump: jump now, the whole hold
                    # (the rising side down slash in the air, the jump held; the hook after it if the body evades), no new dash
                    p=replace(p,jump_k=k+2,jump_until=k+2+int(cfg["STOMP"]["jump_hold"]),sprint_jump=held_dash,dash_k=k+10000)
        if B13B and held_dash and p.sprint_jump and p.jump_k<=k+2:
            # package 1 after B13 (design 7.1): no shuttlecock jump into her own still target's side (b13b_sprint_jump)
            b13b=b13b_sprint_jump(runner,p,sim,enemy,k,link)
            if b13b is not None and b13b["kind"]=="release":p=replace(p,sprint_jump=False,side=int(b13b["side"]))   # its approved row
    elif not ground and not tail_pending:
        if active is None or link in {"walk","dash"}:
            p=replace(p,jump_until=k,jump_k=min(p.jump_k,k));air_entry=True
        elif not (state["act"]["hf"]["latched"]&B["J"] and int(sim.prefix[0])&B["J"]):p=replace(p,jump_until=k)
        if link!="strike" and link not in HOOK_LINKS and link not in FOLLOW_LINKS:link="air"
    if defer_jump and (not ground or (state["act"]["hf"]["latched"]|int(sim.prefix[0]))&B["J"]):return None
    if defer_jump or (approach_only and ground):
        p=replace(p,jump_k=k+10000,jump_until=k+10000,sprint_jump=False)
        # Deferring J must not release a dash already in progress (which
        # cancels its sprint transition), or slide a pending far dash clock.
        link="dash" if current_mode in (K.M_DASH,K.M_SPRINT) else "walk"
    held=None
    if B13B:
        # Sol REVIEW402: the approved row's side key (b13b_sprint_jump's release) holds through this flight: the jump link on the ground
        # to its takeoff and the air link to her landing, whatever a later tick's side says (a 1.2.2 bound, a seam aim); on the ground
        # past the jump link or on any other link (a strike row, a hook, a follow-up) its flight is over
        if b13b is not None and b13b.get("kind")=="release":held=int(b13b["side"])
        elif (active is not None and active.v.get("b13b_side") is not None and link in ("jump","air")
              and not (ground and link=="air")):
            held=int(active.v["b13b_side"]);p=replace(p,side=held)
    draft=runner.fork_empty(AirAnchor())
    variables=dict(runner.chains[PROGRAM].vars)
    if active is not None:variables.update(active.v)
    variables.update(p.variables());variables["air_entry"]=air_entry
    if follow_release:variables["follow"]=None
    variables["no_strike"]=bool(no_strike)   # Task 183 seq 267: this tick's only (read by the stomp plan and the face hook)
    variables["seam_only"]=bool(seam_only)   # Task 183 seq 268: this tick's only (the same two readers)
    variables["follow_close"]=close   # Task 183 seq 262: the two were close when this Run started (a BOUNCE Run)
    # Task 183 seq 263/264: this tick's inner-side condition for a new seam strike row (None: not a seam tick): the
    # target's observed root, the inner direction from the roots' order (0 unknown: every row turned down), the aim;
    # the stomp plan reads the bound at each row's own contact index and lists the rows it turned down
    variables["seam_inner"]=None if seam is None else [float(seam.root),int(seam.sign),
                                                       None if seam.aim is None else float(seam.aim)]
    variables["seam_rejects"]=None
    variables["hold_over"]=bool(hold_over)   # Task 182 seq 312 #384: this tick's only (the record of the held follow-up)
    # Task 182 seq 312 #385: this tick's only: 1.2.2's contact limits (stomp_plan's bound_contact) and the strike rows' direction
    variables["strike_bound"]=None if bound is None or bounce_entry else [float(bound[1]),int(bound[2]),int(bound[3]),
                                                                          str(bound[5]) if len(bound)>5 else "outside"]
    variables["strike_dir"]=None if bound is None or bounce_entry else (B["R"] if enemy["pos"][0]>hp[0] else B["L"])
    variables["hook_open"]=bool(hook_open)   # #387: this tick's only (read by the face hook)
    if active is None:variables["opening_run"]=bool(hook_open)   # #387: a Run begun as the small rune's opening (the native's _opening)
    if early is not None:variables["early_hook"]=early
    variables["b13b"]=b13b   # B13B: this tick's sprint-jump check record (None: not checked)
    variables["b13b_side"]=held   # B13B: the approved row's side key held through this flight (None: none held)
    variables["_approach_only"]=approach_only
    variables["switch_stomp"]=switch_stomp
    variables["source_tail_done"]=bool(tail_done or (bounce_entry and not tail_pending))
    draft.run=Run(PROGRAM,link,variables)
    clearance=head_clearance(cfg)
    obs=_observation(p,state,game,body,ground,clearance)
    obs.sim=sim;obs.e=enemy;obs.hero=h;obs.bombs=bombs;obs.ents=clappers(state)
    obs.idle_ev=None if idle_evidence is None else idle_evidence.get(target)   # Task 179 #317: the Idle instance record
    obs.bounced=bool(variables.get("bounced"))
    mask=draft.eval_link(X(draft,draft.run,obs))
    if mask is None:
        why=draft.done[-1].v.get("why") if draft.done else None
        return (None,replace(p,ended_reason=why),None,None)
    if B13 and (draft.run.link!="air" or ground):
        # Task 182 B13 (Sol REVIEW399 1): a steer belongs to the flight it was chosen in, kept by the air link's keys to that flight's
        # landing; on the ground or on any other link this tick (a landed Run that jumps again, a hook, a strike) its flight is over
        draft.run.v.pop("b13_steer",None)
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


def follow_draft(runner,made,state,game,sim,link,follow,idle_evidence=None):
    """Task 183: the same transfer proposal on a bounce follow-up link (middle / land) with its checked row: the Run, its
    owner and its variables stay this Run's; only the link and its keys change. (draft, plan, current-step path, mask) or
    None when the link ends (the Run's stop rules)."""
    old,p,_,_=made
    es=clappers(state);enemy=next((e for e in es if e["iid"]==p.iid),None)
    body=None if enemy is None else body_box(enemy)
    if body is None:return None
    draft=runner.fork_empty(AirAnchor())
    variables=dict(old.run.v);variables["follow"]=dict(follow)
    variables.pop("b13_steer",None)   # (B13: a follow-up route is a motion of its own; Sol REVIEW399 1)
    draft.run=Run(PROGRAM,link,variables)
    h=state.get("hero") or {}
    obs=_observation(p,state,game,body,False,head_clearance(runner.chains[PROGRAM].cfg))
    obs.sim=sim;obs.e=enemy;obs.hero=h;obs.bombs=None;obs.ents=es
    obs.idle_ev=None if idle_evidence is None else idle_evidence.get(p.iid)
    obs.bounced=bool(variables.get("bounced"))
    mask=draft.eval_link(X(draft,draft.run,obs))
    if mask is None:return None
    path=model_path(sim,p,np.array([mask],np.int64),game)
    path=replace(path,stage="approach",assumptions={**path.assumptions,
        "basis":("Task 183 bounce follow-up: %s; its whole route to the modelled ground scanned when chosen, then its next "
                 "%d frames every tick; all owners")%(follow.get("kind"),FOLLOW_SCAN_F),
        "next_decision":"actual landing between the two bodies (middle) or on the ground (left / right landing)",
        "flight_checked":True,"flight_endpoint":"modelled ground","jump_deferred":False,"approach_only":False})
    if path_problem(path,sim.hold):return None
    return draft,p,path,int(mask)
