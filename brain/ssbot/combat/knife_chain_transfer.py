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


def contact_body_witness(enemy,frames,idle_no_evade=False,idle_time=None):
    """[frames,4] body boxes (x0,y0,x1,y1) a downslash must touch at f+d; nan rows have no witness.

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


def press_now_row(sim,body,F,hold,side,attacking_target=False,clean=False):
    """Shared velocity-aware downslash exit, not a fixed position or hit receipt.
    clean (Task 182, the plans' over route, Sol seq 255 F2): a row whose hero box meets the body at all before its contact is no
    row (51 real DownSlash hits in the bots' recordings: none had her box in the body before the hit).

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
                row.update(contact_frame=sim.fo+j,approach_direction=d,
                           contact_velocity=ro.vel[i,j].tolist())
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


def face_hook_check(sim,hero,enemy,F0,toward,bombs=None,bodies=None,*,high_band=False):
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
    never reaches it, or no band at all, is unsupported (no lower hook instead). (ok, why, info)."""
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
    if st not in HOOK_TARGET_STATES:return False,"target state outside the face-hook scope",info
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
            r=retreat_reserve(enemy,t,toward);moved=np.asarray(body,float)+toward*np.array([r,0.,r,0.])
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
        stop=((front-xp)*toward+retreat_reserve(enemy,t_end,toward)-min(v.gap for v in SK.HOOK_VARIANTS)-SK.HALF_W)
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
        if min(helds)<mid:return False,"high hook: held below the band middle",info
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

    @prims.action("transfer_stomp_plan",doc="one press-now row against the currently observed body; not a hit receipt")
    def stomp_plan(x):
        if x.v.get("_approach_only") or not hasattr(x.obs,"sim") or x.obs.ground:return None
        from . import pogo_model as PM
        if control(x.obs.e)[0]=="Walk":
            # Task 179: the explicit constant-velocity Walk domain (WalkSupport); outside it no row, the
            # existing approach continues and the next tick re-selects. Never the still-body witness below.
            prefix=getattr(x.obs.sim,"prefix",None)
            support=(None if prefix is None else
                     walk_body_support(x.obs.e,len(prefix)+3+PM.ACTIVE[1],getattr(x.obs,"hero",None)))
            if support is None:return None
            row=press_now_row(x.obs.sim,support,x.obs.F,max(0,int(x.v["jump_until"])-int(x.obs.k)),x.v["side"],clean=plan_over_call(x.v))
            if row is None:return None
            x.v["row"]=row
            return {"do":"goto","to":"strike"}
        # The witness keeps the observed root and follows the fitted pose of
        # the current Control state. A moving/unknown body cannot license a
        # fresh row; keep the existing approach instead. This is not a motion
        # prediction or permission to rewrite an absolute row.
        enemy=x.obs.e;velocity=enemy.get("vel")
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
        st0,t0=control(enemy);no_evade=False;f0=getattr(x.obs,"f",None)
        if st0=="Idle" and type(t0) in (int,float) and math.isfinite(t0) and type(f0) is int:
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
        ev=getattr(x.obs,"idle_ev",None) if st0=="Idle" else None
        if isinstance(ev,dict) and ev.get("hit") is not None:return None
        body=contact_body_witness(enemy,len(x.obs.sim.prefix)+3+PM.ACTIVE[1],idle_no_evade=no_evade,
                                  idle_time=idle_time_of(ev))
        if body is None:return None
        # The external step scans an ATTACKING target body with its margin (owner kind move); match it.
        row=press_now_row(x.obs.sim,body,x.obs.F,left,x.v["side"],attacking_target=st0 in AIR_ATTACK_STATES,clean=plan_over_call(x.v))
        if row is not None:
            x.v["row"]=row
            return {"do":"goto","to":"strike"}
        return None

    @prims.gen("transfer_air_keys",doc="same-owner optional one-shot air dash; never a new jump or umbrella")
    def air_keys(x,m):return m|air_approach_keys(x)

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
        row=x.v.get("row")
        if not isinstance(row,dict) or row.get("support")!="walk" or x.obs.f>=row["contact_frame"]:return False
        w=row["walk"];e=x.obs.e;vel=e.get("vel")
        return not (control(e)[0]=="Walk" and isinstance(vel,(list,tuple)) and len(vel)==2
                    and vel[0]==w["vx"] and vel[1]==0 and e.get("flipX")==w["flip"])

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
        if (not x.cfg.get("FACE_HOOK",False) or v.get("_approach_only") or v.get("cs") is not None or v.get("hook_done") or not hasattr(x.obs,"sim")
                or x.obs.ground or v.get("iid")==v.get("caster")):return None
        toward=1 if v.get("side")==B["R"] else -1 if v.get("side")==B["L"] else 0
        ents=getattr(x.obs,"ents",None)
        try:bodies=None if ents is None else [(e.get("iid"),body_box(e)) for e in ents]
        except (TypeError,ValueError,OverflowError):bodies=[(None,None)]
        ok,why,info=face_hook_check(x.obs.sim,getattr(x.obs,"hero",None),x.obs.e,int(x.obs.F),toward,
                                    getattr(x.obs,"bombs",None),bodies,high_band=bool(v.get("switch_stomp")))
        v["face_hook_check"]={"ok":ok,"why":why,**{k:float(w) for k,w in info.items()}}
        if not ok:return None
        from .claw_strike import CsPlan
        F0=int(x.obs.F)
        v["cs"]=CsPlan(F0,0,F0+HOOK_PRESS_AFTER_F,0,bb_press=info["bb_press"])
        v["air_dash_decided"]=True  # no air dash after an aimed hook in this Run
        from .knife_chain_face_hook import press_anchor
        v["hook_press"]=press_anchor(x.obs.sim,toward,F0,x.obs.e)
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
            idle_evidence=None):
    """One observed-distance recipe and a two-frame external path.

    approach_only uses the same walk/dash/air keys without choosing a strike.
    Its sent Run keeps that intent until the native adapter's planned handoff.
    defer_jump remains for offline callers; neither cancels an existing sprint.
    idle_evidence (Task 179 #317): the native owner's per-Clapper Idle instance records; the strike witness reads the
    target's (idle_time_of; a hit since the instance's entry: no witness).
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
        observed=(goal is not None and goal.target==target and goal.caster in {e["iid"] for e in es} and
                  0<=state["f"]-goal.window_from<=cfg["max_frames"])
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
    early=None
    if link in {"walk","dash"} and ground:
        held_dash=bool(current_mode in (K.M_DASH,K.M_SPRINT) and int(sim.prefix[0])&B["DASH"])
        if held_dash:link="dash"
        gap=abs(enemy["pos"][0]-hp[0])
        # Observe the distance now. A model's eventual body intersection must
        # not make us release DASH or wait in front of the destination.
        cache=None if active is None else active.v.get("early_hook")
        early_due=False
        if cfg.get("FACE_HOOK",False):
            from .knife_chain_face_hook import early_jump_due
            early_due=early_jump_due(cache,k,target_state)
        if not (defer_jump or approach_only) and (gap<=cfg["STOMP"]["jump_root"] or early_due):
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
        if (cfg.get("FACE_HOOK",False) and not (defer_jump or approach_only) and p.jump_k>k+2
                and p.iid!=p.caster and target_state in HOOK_TARGET_STATES
                and (active is None or active.v.get("cs") is None)):
            from .knife_chain_face_hook import early_jump_stale,early_jump
            if early_jump_stale(cache,state["f"],target_state):
                early=early_jump(runner,p,sim,game,state,enemy,bombs,k,link,held_dash,high_band=switch_stomp)
                if early.get("ok") and early.get("defer_new_dash"):
                    p=replace(p,dash_k=k+10000)
    elif not ground and not tail_pending:
        if active is None or link in {"walk","dash"}:
            p=replace(p,jump_until=k,jump_k=min(p.jump_k,k));air_entry=True
        elif not (state["act"]["hf"]["latched"]&B["J"] and int(sim.prefix[0])&B["J"]):p=replace(p,jump_until=k)
        if link!="strike" and link not in HOOK_LINKS:link="air"
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
    if early is not None:variables["early_hook"]=early
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
