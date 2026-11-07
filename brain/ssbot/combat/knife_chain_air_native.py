"""Opt-in manual air family inside the EXISTING B2 send/receipt/commit path.

Only this family's candidate availability suppresses the old slam script; ground
h2 remains available. No second keyboard owner or online action-tree search.
The table is a named unfitted probe, checked through predicted contact and the
existing N=2 short continuation policy;
Actual target hit AND observed bounce reopen the tactical target's next knife.
The old slam's observed hammer tail is retained before that air/strike suffix.
"""
from dataclasses import asdict,replace
from pathlib import Path
import os
import numpy as np
from .knife_chain_b2 import NativeChainB2,B2Offer
from .knife_chain_eval import Run,X
from .knife_chain_air import (AirAnchor,load_runner,entry_context,plan_entry,model_path,advance,complete_hf,render,direct_path_problem)
from .knife_chain_geometry import B2Geometry,GeometryUnavailable
from . import knife_chain_transfer as transfer
from . import knife_chain_waypoint as waypoint
from .knife_chain_commitment import MoveInstance
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_nominal import logical_copy,NominalUnsupported


PLAN_SIDE_NEAR_U=5.5   # SSBOT_FORUM_TWO_PLAN: a side approach under a source in the air stops at the slash's range (its sprint's
#                        skid takes her to the stance), not at the jump's distance: there she would stand under its landing


def _plan_source_in_air(state,caster):
    from .tactics import clapper_plans
    if not clapper_plans.ENABLED:return False
    source=next((e for e in transfer.clappers(state) if e["iid"]==caster),None)
    return source is not None and transfer.control(source)[0] in ("Jump","Air")


def _passes_under(source,obstacle,state):
    """SSBOT_FORUM_TWO_PLAN only: the side approach's source is in its jump's flight with its body's bottom above her head."""
    from .tactics import clapper_plans
    if not clapper_plans.ENABLED or transfer.control(source)[0] not in ("Jump","Air"):return False
    box=(state.get("hero") or {}).get("box") or ()
    return bool(len(box)==4 and type(box[3]) in (int,float) and np.isfinite(box[3]) and obstacle[1]>box[3])


class NativeManualAirChain(NativeChainB2):
    manual_air=True
    @staticmethod
    def load_program(profile):
        if profile.fixed_hook or profile.fast_hook:
            raise ValueError("manual air family does not activate fixed/fast hook programs")
        vault=os.environ.get("SSBOT_FORUM_CHAIN_VAULT","0").strip()
        if vault not in {"0","1"}:raise ValueError("invalid SSBOT_FORUM_CHAIN_VAULT")
        if vault=="1":
            from .knife_chain_vault_native import load_runner as load_vault_air
            return load_vault_air()
        return load_runner()

    @staticmethod
    def program_tables():
        tables=(Path(__file__).with_name("knife_chain_air_v01.json"),)
        if os.environ.get("SSBOT_FORUM_CHAIN_VAULT","0").strip()=="1":
            tables+=(Path(__file__).with_name("knife_chain_vault_v01.json"),)
        from .knife_chain_bounce_table import enabled as bounce_table_enabled,TABLE as BOUNCE_TABLE
        if bounce_table_enabled():tables+=(BOUNCE_TABLE,)
        return tables

    @property
    def candidate_generation(self):
        return bool(getattr(self,"_candidate_enabled",False) and
            (getattr(self,"_air_context",None) is not None or getattr(self,"_transfer_ready",False) or getattr(self,"_vault_ready",False)
             or (self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM) or getattr(self,"commitment",None) is not None
             or (self.runner.run is not None and self.runner.run.chain=="vault_idle")
             or getattr(self,"_waypoint_wanted",False)
             or getattr(self,"recovery",None) is not None or getattr(self,"post_context",None) is not None
              or (getattr(self,"_wall_pressure",None) is not None and not (self._wall_pressure.get("yielded",False) or self._wall_pressure.get("landing",False)))))

    @candidate_generation.setter
    def candidate_generation(self,value):self._candidate_enabled=bool(value)

    def residual_context(self):
        ctx=getattr(self,"_wall_pressure",None)
        if ctx is not None and (ctx.get("landing") or ctx.get("yielded")):
            return {"source_move":asdict(ctx["goal"].responsibility),
                    "kind":"wall_pressure_residual","input_owner":False}
        return None

    def reset(self,episode,*,start_frame=None):
        self._air_context=None;self._air_plan=None;self._air_finished=set()
        self._transfer_ready=False;self._transfer_finished=set();self._transfer_goal=None
        self._transfer_blade=None
        self._follow_fallback=None;self._follow_made=None   # Task 183 seq 265: one tick's seam fallback / released draft
        self._wall_pressure=None
        self._entry_attack_seen=None
        self._entry_attack_goal=None
        self._return_admission_noted=None
        self._idle_ev={};self._alive_prev=None;self._alive_prev_f=None
        self._transfer_responsibility={}
        self._transfer_target_moves={}
        self._vault_ready=False
        self._vault_responsibility={}
        self._vault_origins={};self._vault_completed=set()
        self._bounce=None;self._bounce_frames={}
        self._waypoint_wanted=False;self._waypoint_failed=set();self._waypoint_declined=None;self._waypoint_responsibility={}
        super().reset(episode,start_frame=start_frame)
        from . import knife_chain_bounce_table as bounce_table
        # Task 179 (#309, Sol seq 229): the finite same-target bounce table (Tasks 143 / 145 / 148), opt-in.
        self._bounce_mode=bounce_table.enabled() and self.arm=="B"
        transfer.slam_tail_frames()  # preload before timed decisions, share immutable counts
        self.vault_enabled="vault_idle" in self.runner.chains
        face_hook=os.environ.get("SSBOT_FORUM_CHAIN_FACE_HOOK","0").strip()
        if face_hook not in {"0","1"}:raise ValueError("invalid SSBOT_FORUM_CHAIN_FACE_HOOK")
        self._face_hook_mode=face_hook=="1" and self.arm=="B"
        self.runner.chains[transfer.PROGRAM].cfg["FACE_HOOK"]=self._face_hook_mode

    def begin(self,state,history=()):
        super().begin(state,history)
        if self.vault_enabled:
            from .knife_chain_vault_native import visible
            self._vault_ready=visible(state)
        previous=self._transfer_goal
        transfer_active=self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM
        if not transfer_active:
            self._transfer_goal=transfer.observe_goal(state,previous,self.runner.chains[transfer.PROGRAM].cfg,self._transfer_finished,self._clock)
        self._transfer_ready=transfer.visible(state,self.runner.chains[transfer.PROGRAM].cfg)
        if self._transfer_goal is not None and self._transfer_goal!=previous:
            self._note("rune_transfer_candidate",frame=state["f"],**asdict(self._transfer_goal),source="observed Spell Antic; destination only")
        self._air_context=(entry_context(state,self._clock,self.runner) if self.arm=="B" and
            self.commitment is None and self.post_context is None else None)

    def observe_bounce_goal(self,state,prefs,legacy_run=None,*,game_time=None):
        """Bind the next tactical target at a real bounce, before old after keys."""
        if self.arm!="B" or self.recovery is not None or self.commitment is not None:return False
        hit=transfer.bounce_target(state);target=getattr(prefs,"target",None)
        post=self.post_context
        if (hit is None and post is not None and post.get("bounce")==state["f"] and
                self._hit is not None and post.get("hit")==self._hit):
            # Base B2 has already joined our press-bound earlier hit to THIS
            # observed bounce; the hit need not be repeated in the same STATE.
            hit=post["move"].target_iid
        es={e["iid"]:e for e in transfer.clappers(state)}
        if len(es)!=2 or hit not in es or target not in es:return False
        source=None;ta=None
        if (legacy_run is not None and legacy_run.phase=="after" and legacy_run.iid==hit):
            source=transfer.MoveInstance(hit,legacy_run.fa,"CC_SLAM");ta=legacy_run.ta
            if game_time is not None:
                if not np.isfinite([game_time,ta,self._clock]).all():return False
                ta=self._clock-(float(game_time)-float(ta))
            elif self.require_send_clock:
                self._note("target_transfer_unchecked",frame=state["f"],reason="legacy source clock unavailable")
                return False
        elif self.post_context is not None and self.post_context["move"].target_iid==hit:
            source=self.post_context["move"];ta=self.post_context.get("ta")
            if source.family=="RUNE_TRANSFER":
                attacking=transfer.control(es[hit])[0] in transfer.AIR_ATTACK_STATES
                physical=self._observed_transfer_move(state,hit,"CC_SLAM") if attacking else None
                if attacking:physical=physical or self._transfer_target_moves.get(source)
                if attacking and physical is None:
                    self._note("target_transfer_unchecked",frame=state["f"],reason="actual bounced target slam origin unavailable")
                    self.post_context=self._post_seed=self._post_kind=None
                    self._abandon("real bounce with unknown target slam: ordinary handback")
                    return False
                source,ta=physical or self._transfer_responsibility.get(source,(None,None))
            elif source.family=="VAULT_IDLE":source,ta=self._vault_responsibility.get(source,(None,None))
        if source is None:return False  # no invented parent move or CC_CAST label
        if getattr(self,"_bounce_mode",False):
            from . import knife_chain_bounce_table as bounce_table
            if bounce_table.try_anchor(self,state,prefs,hit,source,ta):return True
        self._transfer_goal=transfer.TransferGoal(target,hit,state["f"],ta,"BOUNCE",source)
        self._note("target_transfer_bounce_goal",frame=state["f"],**asdict(self._transfer_goal))
        return True

    def key_commitment(self,state):
        """Task 182 (Sol seq 255 A): what this owner holds of her keys past the in-flight prefix. None: nothing a plan must wait for
        (no Run; an approach-only or waypoint Run hands back at its next step when L2 moves on). Else (owner, release known, keys
        from the first free mask frame on); the source tail's release and keys are its own admission's; any other committed Run,
        recovery or hook: unknown."""
        run=self.runner.run;f=state.get("f")
        if self.recovery is not None:return "b2 recovery",False,()
        wall=getattr(self,"_wall_pressure",None)
        if wall is not None and not (wall.get("yielded") or wall.get("landing")):return "b2 wall pressure",False,()
        if run is None:
            return None if self.commitment is None else ("b2 commitment",False,())
        if self.own_bounce_released(state):return None
        if run.chain==waypoint.PROGRAM or (run.chain==transfer.PROGRAM and run.v.get("_approach_only")):return None
        if run.chain==transfer.PROGRAM and run.link=="bounce_tail" and self._transfer_goal is not None and type(f) is int:
            end=transfer.predicted_tail_end(state,self._transfer_goal)
            if end is None:return run.lid,False,()
            return run.lid,True,(int(run.v.get("source_tail_mask",0)),)*max(0,end-(f+1))
        return run.lid,False,()

    def own_bounce_released(self,state):
        """Task 182 (Sol seq 256): this STATE's real bounce of this chain's own strike: observe has already released its commitment and
        this tick's goal step takes the Run (observe_bounce_goal, goal_preferences): nothing past the in-flight prefix holds her keys.
        Read only, along that same path; not when the old hammer tail goes on (bounce_tail_pending: still a holder), nor when
        that path has no parent move to bind (no goal, the Run stays)."""
        if not self.own_bounce_now(state) or self.arm!="B" or self.recovery is not None or self.commitment is not None:return False
        post=self.post_context;source=post["move"];hit=source.target_iid;ta=post.get("ta")
        es={e["iid"]:e for e in transfer.clappers(state)}
        if len(es)!=2 or hit not in es:return False
        if source.family=="RUNE_TRANSFER":
            attacking=transfer.control(es[hit])[0] in transfer.AIR_ATTACK_STATES
            physical=self._observed_transfer_move(state,hit,"CC_SLAM") if attacking else None
            if attacking:physical=physical or self._transfer_target_moves.get(source)
            if attacking and physical is None:return True   # that path's ordinary hand-back
            source,ta=physical or self._transfer_responsibility.get(source,(None,None))
        elif source.family=="VAULT_IDLE":source,ta=self._vault_responsibility.get(source,(None,None))
        if source is None:return False
        return not transfer.bounce_tail_pending(state,transfer.TransferGoal(hit,hit,state["f"],ta,"BOUNCE",source),self._clock)

    def own_bounce_now(self,state):
        """Task 181 (Sol seq 253 R2): this STATE's real bounce released this chain's own strike: its post_context was made
        on this very frame (B2 observe) with that strike's own hit (after its sent press, on its move's target). An older
        post of the same Clapper or a hook bounce is not it, whatever hit this STATE shows."""
        post=self.post_context
        return bool(post is not None and post.get("bounce")==state["f"] and type(post.get("hit")) is int
                    and post["hit"]==self._hit and type(post.get("press")) is int and post["press"]<=post["hit"]<=state["f"])

    @staticmethod
    def _move_phases():
        """Each Clapper attack family's primary antic state and the states its move holds."""
        return {"CC_CAST":("Spell Antic",{"Spell Antic","Cast 1","Cast 2"}),
                "CC_SLAM":("Slam Antic",set(transfer.AIR_ATTACK_STATES)|{"Slam Recover"}),
                "CC_JUMP":("Jump Antic",{"Jump Antic","Jump Aim","Jump","Air","Charged?","Slam Effects?","Slam 2","Slam Recover"}),
                "CC_JUMP_CAST":("Cast Slam Antic",{"Cast Slam Antic","Cast Slam Antic 2","Cast Jump","Jump Aim","Jump","Air","Charged?","Slam Effects?","Slam 2","Slam Recover"})}

    def _observed_transfer_move(self,state,iid,family):
        """Use the existing causal antic history for a real move's identity."""
        phases=self._move_phases()
        if family not in phases or not self._clock_known:return None
        primary,states=phases[family]
        source=next((e for e in transfer.clappers(state) if e["iid"]==iid),None)
        if source is None or transfer.control(source)[0] not in states:return
        def known_clock(enemy):
            clocks=[m for m in enemy.get("fsms") or () if m.get("name")=="Control"]
            return (len(clocks)==1 and type(clocks[0].get("t")) in (int,float)
                    and np.isfinite(clocks[0]["t"]) and clocks[0]["t"]>=0)
        if not known_clock(source):return
        from .knife_chain_history import HistView
        ticks=list(self._ticks)
        if not ticks or ticks[-1][0]!=state["f"]:ticks.append((state["f"],state,self._clock,False,False))
        hist=HistView(ticks,{},state["f"])
        for row in reversed(hist.rows):
            enemy,ctl=hist._ctl(row[1],iid)
            if enemy is None or ctl[0]!=primary:break
            if not known_clock(enemy):return
        an=hist.antic(iid,primary,())
        if an is None or not np.isfinite([an["ta"],self._clock]).all():return
        return transfer.MoveInstance(iid,an["fa"],family),an["ta"]

    def _return_source_ended(self,state,goal):
        """A ReturnGoal's source has left the move that made the return due: none of its family's move states holds
        (an unknown family or an absent source is not ended)."""
        phases=self._move_phases()
        fam=getattr(goal.source_move,"family",None)
        source=next((e for e in transfer.clappers(state) if e["iid"]==goal.caster),None)
        return fam in phases and source is not None and transfer.control(source)[0] not in phases[fam][1]

    def _return_admission(self,state,sim,plan,game,geo):
        """A fresh ReturnGoal start (Task 179 #316) runs the transfer recipe's own straight approach (side held, J over
        the plan's jump hold; the actual S0, hold state and keys in flight: ChainSim.roll, flight_check_frames long) with
        the one air dash air_approach_keys would add: in the air, normal mode, dash unspent, a target other than the
        source, farther than its body width, and this plain coast landing without getting above that body; pressed on
        the first step after her J and DASH are no longer pressed or latched (air_approach_keys waits for both; A3 2798:
        the planner's held jump, the Run's dash at 2802) and the dash cooldown is over. That dash must pass the existing
        locked-motion scan on this tick's B2 geometry (_dash_lock_scan with the whole row; A3 2790-2792: refused at its
        own step, the started Run recovered and the return was spent). It starts only if that approach
        - passes the other Clapper's observed body, when it lies between her and the target's root, without entering
          it grown by FOCUS_M (grazes_body, the recipe's close-body backstop; a landing short of it walks into it): the
          recipe is a straight approach, never a crossing skill (the side approach's source_blocked rule; A2 2770-2796
          drifted into the crossed body and landed short of it), and
        - gets above the target's body (its centre over the body, the box bottom above its top: air_approach_keys'
          overhead test) at a frame where the recipe's existing strike witness still holds: contact_body_witness with
          the no-evade proof the Run collects in range assumed (Idle up to Idle Time), WalkSupport for a walker along
          this approach (A2 2798-2823: over an Idle past its modelled exits no press-now row can exist, the Run only
          descends onto her).
        Returns None, or why the start waits: the current owner keeps the keys, nothing is sent or spent. Admission
        only; every step keeps its full check."""
        from ssbot.knowledge import kinematics as K
        from .holdfilter import hold_filter_jit
        es=transfer.clappers(state)
        enemy=next((e for e in es if e["iid"]==plan.iid),None)
        other=next((e for e in es if e["iid"]!=plan.iid),None)
        hp=(state.get("hero") or {}).get("pos")
        try:body,tbody=(None if other is None else transfer.body_box(other)),(None if enemy is None else transfer.body_box(enemy))
        except (TypeError,ValueError,OverflowError):body=tbody=None
        if (body is None or tbody is None or not isinstance(hp,(list,tuple)) or not hp
                or not np.isfinite([hp[0],enemy["pos"][0],*body,*tbody]).all()):
            return "Clapper bodies unknown"
        side=int(plan.side)
        if side not in (B["L"],B["R"]):return "no approach side"
        cfg=self.runner.chains[transfer.PROGRAM].cfg
        n=int(cfg["flight_check_frames"])
        commands=np.full(n,side,np.int64)
        k=int(plan.entry_k)
        commands[max(0,min(n,int(plan.jump_k)-k)):max(0,min(n,int(plan.jump_until)-k))]|=B["J"]
        S=np.asarray(sim.start,float).reshape(-1)
        coast=sim.roll(commands[None])
        box=np.asarray(coast.box[0],float);pos=np.asarray(coast.pos[0],float)
        after=np.arange(len(box))>=sim.off
        lands=np.flatnonzero(((np.asarray(coast.flags[0])&K.F_GROUND)!=0)&after)
        gap=max(tbody[0]-float(S[K.PX]),float(S[K.PX])-tbody[2],0.)
        if (S[K.GROUND]<=0 and S[K.MODE]==K.M_NORMAL and S[K.AIRDASHED]<=0 and plan.iid!=plan.caster
                and (state.get("hero") or {}).get("hero_accepting_input") is True and gap>tbody[2]-tbody[0]
                and len(lands)):
            reach=after[:int(lands[0])]&(pos[:int(lands[0]),0]>=tbody[0])&(pos[:int(lands[0]),0]<=tbody[2])&(
                box[:int(lands[0]),1]>=tbody[3])
            if not reach.any():
                full=np.concatenate([np.asarray(sim.prefix,np.int64),commands])
                lat,_=hold_filter_jit(np.ascontiguousarray(full[None]),sim.hold)
                P,dt=len(sim.prefix),float(sim.params.frame_time)
                busy=(full|np.asarray(lat[0],np.int64))&(B["J"]|B["DASH"])
                free=[i for i in range(n) if not busy[P+i-1] and float(S[K.DASH_CD])-(i+1)*dt<=0]
                if free:
                    commands[free[0]]|=B["DASH"]
                    lock,_=self._dash_lock_scan(sim,plan,commands[free[0]],game,geo,"air",commands=commands)
                    if lock is None or not lock.complete or lock.contacts:
                        return "the approach's air dash is refused through its locked motion (step %d)"%free[0]
                    coast=sim.roll(commands[None])
                    box=np.asarray(coast.box[0],float);pos=np.asarray(coast.pos[0],float)
        hx,tx=float(hp[0]),float(enemy["pos"][0])
        if min(hx,tx)<=body[2] and max(hx,tx)>=body[0]:
            past=(box[:,0]>body[2]) if side==B["R"] else (box[:,2]<body[0])
            idx=np.flatnonzero(past&after)
            if not len(idx):return "the straight approach does not pass the other body within flight_check_frames"
            if transfer.grazes_body(box[:int(idx[0])+1],body,int(idx[0])+1):
                return "the straight approach enters the other body grown by FOCUS_M before passing it"
        over=np.flatnonzero((pos[:,0]>=tbody[0])&(pos[:,0]<=tbody[2])&(box[:,1]>=tbody[3])&after)
        if not len(over):return "the straight approach never gets above the target within flight_check_frames"
        j=int(over[0])
        st=transfer.control(enemy)[0];ev=self._idle_ev.get(plan.iid) if st=="Idle" else None
        if st=="Walk":
            support=transfer.walk_body_support(enemy,j+1,state.get("hero"))
            witness=None if support is None else support(pos[:j+1,0])[0]
        elif ev is not None and ev.get("hit") is not None:
            witness=None             # #317: an Idle hit since its entry: no witness until a new instance
        else:
            witness=transfer.contact_body_witness(enemy,j+1,idle_no_evade=True,idle_time=transfer.idle_time_of(ev))
        if witness is None or not np.isfinite(witness[j]).all():
            return "no strike witness for the target when the approach gets above it (frame +%d)"%j
        return None

    def _no_strike_overhead(self,state,sim,target):
        """Task 179 #317 (Sol seq 240 乙): why an air Run over its target can no longer strike her, or None. Over: the
        hero centre inside her observed body span and the hero box bottom above its top. Only DEFINITE ends count,
        never one tick without a press-now row or a witness that is momentarily absent:
        - an Idle whose clock is past its modelled Idle Time with the no-evade proof assumed (the no-buddy 39, or 68
          with the Idle-entry buddy evidence) and so has no witness on any frame of the press horizon
          (len(prefix) + 3 + ACTIVE[1], as transfer_stomp_plan), or an Idle hit since its entry (evidence revoked);
        - a walker outside WalkSupport;
        - a state with no fitted still pose at all (not Walk, not transfer.STILL_ROOT_STATES: Dmg Attack, Evade
          Scuttle, Slam 0 / 1, the jump antics ...).
        A still state whose witness is absent now (its pose still settling, past its longest fitted duration with
        the successor to come: live prefix 2612 Slam Recover, struck at 2632 on the Idle after it) keeps the Run;
        unknown inputs do too."""
        enemy=next((e for e in transfer.clappers(state) if e["iid"]==target),None)
        h=state.get("hero") or {};hb=h.get("box");hp=h.get("pos")
        try:body=None if enemy is None else transfer.body_box(enemy)
        except (TypeError,ValueError,OverflowError):body=None
        if (body is None or not isinstance(hb,(list,tuple)) or len(hb)<4 or not isinstance(hp,(list,tuple)) or not hp
                or not np.isfinite([hp[0],hb[1],*body]).all()):return None
        if not (body[0]<=hp[0]<=body[2] and hb[1]>=body[3]):return None
        return self._no_strike_witness(state,sim,target,enemy)

    def _no_strike_witness(self,state,sim,target,enemy):
        """The definite ends of _no_strike_overhead (Task 179 #317) wherever she is: why no strike witness is possible on
        this target now, or None. Task 183 seq 265: the seam action reads it before it approaches."""
        from . import pogo_model as PM
        if enemy is None:return None
        h=state.get("hero") or {}
        frames=len(sim.prefix)+3+PM.ACTIVE[1]
        st=transfer.control(enemy)[0]
        if st=="Walk":
            return None if transfer.walk_body_support(enemy,frames,h) is not None else "walker outside WalkSupport"
        if st not in transfer.STILL_ROOT_STATES:return "no fitted still pose in %s"%st
        if st!="Idle":return None
        ev=self._idle_ev.get(target)
        if ev is not None and ev.get("hit") is not None:
            return "Idle hit at %d since its entry: evidence revoked"%ev["hit"]
        idle_time=transfer.idle_time_of(ev);tin=transfer.control(enemy)[1]
        if type(tin) not in (int,float) or not np.isfinite(tin) or int(round(tin*60.))<idle_time:return None
        w=transfer.contact_body_witness(enemy,frames,idle_no_evade=True,idle_time=idle_time)
        if w is None or not np.isfinite(w).all(axis=1).any():
            return "no strike witness: Idle k %d past its Idle Time %d"%(int(round(tin*60.)),idle_time)
        return None

    @staticmethod
    def _return_request_holds(prefs,goal):
        """L2 makes this ReturnGoal's request on this tick, for its current target (the request's own identity)."""
        req=getattr(prefs,"return_request",None)
        return (req is not None and req.target==getattr(prefs,"target",None) and
                (req.target,req.source,req.source_start_f,req.made_f)==(goal.target,goal.caster,goal.cast_fa,goal.return_f))

    def _bind_return_request(self,state,prefs):
        """SSBOT_FORUM_TWO_RETURN_AIR (Task 179 #316, Sol seq 239 a): L2's current air ReturnRequest becomes a ReturnGoal
        run with the existing SWITCH approach / down-slash execution. Bound only on a tick L2 makes the request (its
        actual winner) for the current target, inside its finite window (max_frames from its first issue), while no Run
        of this program is out and no other goal holds the destination; one return per source instance (the finished
        key). A pending ReturnGoal whose request L2 no longer makes (target, pose or state changed) is withdrawn before
        it starts; a sent one is released at its next approach step (_transfer_offer), a committed strike row finishes
        under its own ownership. The ended source is attribution only: no phase or instance gate, no clock rewrite, no
        exemption."""
        from .forum_v2 import RETURN_AIR
        if not RETURN_AIR:return
        req=getattr(prefs,"return_request",None)
        goal=self._transfer_goal
        active=self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM
        if isinstance(goal,transfer.ReturnGoal) and not active and not self._return_request_holds(prefs,goal):
            self._transfer_goal=goal=None
            self._note("return_request_withdrawn",frame=state["f"],request=None if req is None else asdict(req),
                       reason="L2 no longer makes this air return request")
        if req is None or active or goal is not None or req.target!=getattr(prefs,"target",None):return
        if not 0<=state["f"]-req.made_f<=self.runner.chains[transfer.PROGRAM].cfg["max_frames"]:return
        if (req.source,req.source_start_f) in self._transfer_finished:return
        src=transfer.MoveInstance(req.source,req.source_start_f,req.source_family)
        self._transfer_goal=transfer.ReturnGoal(req.target,req.source,req.source_start_f,None,"SWITCH",src,req.made_f)
        self._note("return_request_bound",frame=state["f"],request=asdict(req),
                   source="observed near move ended: attribution and the one-return key only, no exemption")

    def _bind_entry_attack(self,state,prefs):
        """Bind a tactical entry to observed source history, not a guessed move."""
        from .tactics.modes import EntryAttack
        entry=getattr(prefs,"entry_attack",None)
        if not isinstance(entry,EntryAttack) or entry.target!=getattr(prefs,"target",None) or entry.kind not in {"stomp","side"}:return
        goal=self._transfer_goal
        if goal is not None and (goal.target,goal.caster)==(entry.target,entry.source):return
        if entry==self._entry_attack_seen:return
        observed=self._observed_transfer_move(state,entry.source,entry.source_family)
        if observed is None:return
        move,ta=observed
        self._transfer_goal=transfer.TransferGoal(entry.target,entry.source,state["f"],ta,"SWITCH",move)
        self._entry_attack_goal=entry
        self._entry_attack_seen=entry
        self._note("target_entry_attack_bound",frame=state["f"],entry_attack=asdict(entry),source_move=asdict(move))

    def goal_preferences(self,state,prefs,*,handoff):
        """One destination before forecasting; critical/committed actions retain ownership."""
        self._waypoint_wanted=getattr(prefs,"waypoint",None) is not None
        from .knife_chain_wall_native import prepare_goal
        if prepare_goal(self,state,prefs,handoff=handoff):
            from .knife_chain_wall_native import preferences as wall_preferences
            return wall_preferences(self,prefs)
        if (self.arm!="B" or not handoff or self.commitment is not None or
                self.recovery is not None or getattr(prefs,"want_bind",False)):
            self._transfer_ready=False
            return prefs
        if (self._transfer_goal is not None and self._transfer_goal.source_kind=="SWITCH" and
                not isinstance(self._transfer_goal,transfer.ReturnGoal) and
                self.runner.run is None and self._entry_attack_goal!=getattr(prefs,"entry_attack",None)):
            self._transfer_goal=None;self._entry_attack_goal=None
        self._bind_return_request(state,prefs)
        self._bind_entry_attack(state,prefs)
        goal=self._transfer_goal
        if goal is None:
            self._transfer_ready=False;return prefs
        enemies={e["iid"]:e for e in transfer.clappers(state)}
        target=enemies.get(goal.target);caster=enemies.get(goal.caster)
        active=self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM
        spent=(goal.caster,goal.cast_fa) in self._transfer_finished
        if target is None or caster is None:
            self._transfer_goal=None;self._transfer_ready=False
            if active:self._abandon("rune transfer no longer owns this observed cast")
            return prefs
        # The action table does not choose an enemy. It can only execute the
        # destination already selected by tactics, with that enemy's full prefs.
        if getattr(prefs,"target",None)!=goal.target:
            self._transfer_ready=False;return prefs
        if self.post_context is not None:
            if goal.source_kind!="BOUNCE" or self.post_context["move"].target_iid!=goal.caster:
                self._transfer_ready=False;return prefs
            old=self.post_context["move"]
            self._air_finished.add(old)
            self.post_context=self._post_seed=self._post_kind=None;self._air_plan=None
            self._abandon("real bounce: next target knife handoff")
            self._air_context=entry_context(state,self._clock,self.runner)
        # A destination is not keyboard ownership: a newly observed target
        # attack must still reach the existing ground/air attack adapters.
        st=transfer.control(target)[0]
        hb=(state.get("hero") or {}).get("box") or ()
        air_attack=(st in transfer.AIR_ATTACK_STATES and len(hb)==4 and
                    type(hb[1]) in (int,float) and np.isfinite(hb[1]) and hb[1]>3.2)
        self._transfer_ready=((st in self.runner.chains[transfer.PROGRAM].cfg["target_states"] or air_attack) and (active or not spent))
        entry=getattr(prefs,"entry_attack",None)
        side=entry is not None and entry.target==goal.target and entry.kind=="side"
        side_approach=side and goal.source_kind=="SWITCH"
        if (side and not side_approach and not transfer.bounce_tail_pending(state,goal,self._clock)) or goal.target in getattr(prefs,"no_hit",()):
            self._transfer_ready=False
        blade="side" if side else "air_contact" if air_attack and self._transfer_ready else "stomp" if self._transfer_ready else "slam" if st=="Slam Antic" else "unavailable"
        status=(goal,st,blade,spent)
        if status!=self._transfer_blade:
            self._note("target_transfer_blade",frame=state["f"],target=goal.target,state=st,blade=blade,
                       source_kind=goal.source_kind,spent=spent,goal_retained=True)
            self._transfer_blade=status
        if spent and not active:return prefs  # retain intent, never re-claim an ended action's after segment
        return replace(prefs)  # acknowledge handoff; preserve every tactical field

    def continuation_value_bound(self,prefs):return float("inf")

    def _vault_domain(self,forecast,prefs):
        """The existing vault's own domain for this tactical target: the other Clapper in a decided jump, this one
        Idle / Walk (knife_chain_vault_native.locked_context). Only the domain; never a recipe, contact or path claim."""
        if not (self.vault_enabled and getattr(self,"_vault_ready",False) and self._context is not None):return False
        from .knife_chain_vault_native import locked_context
        tick=self._context[0]
        return locked_context(tick[1],forecast,getattr(prefs,"target",None),tick[2]) is not None

    DASH_LOCK_MAX=45  # frames from the dash send to the modeled input return; none by then: the lock is unknown

    @staticmethod
    def _locked_mode(sim):
        """The current modeled mode when it is a dash, relinquished or no-input motion (keys cannot steer it)."""
        from ssbot.knowledge import kinematics as K
        S=np.asarray(getattr(sim,"start",np.nan),float).reshape(-1)
        if S.shape[0]!=K.K or not np.isfinite(S[K.MODE]):return None
        mode=int(S[K.MODE])
        return mode if mode in (K.M_DASH,*K.RELINQUISHED,*K.NO_INPUT) else None

    def _dash_lock_scan(self,sim,plan,mask,game,geo,link,commands=None):
        """Task 179 (#296, live 786 2617): scan a NEW dash impulse through the motion it locks.

        The dash and the input-less inertia after it (Sprint Air Short or the skid, control relinquished) carry her
        where new keys cannot change the route; the scan runs from the send through the first modeled input frame
        plus the two-frame send delay, on the actual prefix, hold and abilities (model_path from the current
        ChainSim), with the Run's own planned keys behind the impulse (transfer.render of its link). The ground
        sprint (phase 2) takes the dash release and the sprint jump (Sprint FSM), so it is steerable, not locked.
        (scan, info); scan None when the dash start or the input return is not modeled inside DASH_LOCK_MAX frames
        (unknown, never a pass). commands (Task 179 #316, _return_admission): the whole planned key row with the
        impulse pressed on a later step, in place of mask on the first one and the link's own keys behind it."""
        from ssbot.knowledge import kinematics as K
        given=commands is not None
        if given:
            commands=np.asarray(commands,np.int64)[:self.DASH_LOCK_MAX].copy()
        elif link=="air":
            # transfer.render of the air link, in closed form: its own coast keys (air_approach_keys without the
            # one-shot dash) are the side key plus J while jump_until is ahead of the mask clock
            k=plan.entry_k+2+np.arange(self.DASH_LOCK_MAX)
            commands=np.where(int(plan.jump_until)-k>0,int(plan.side)|B["J"],int(plan.side)).astype(np.int64)
        else:
            commands=np.zeros(self.DASH_LOCK_MAX,np.int64)
            planned=np.asarray(transfer.render(self.runner,plan,plan.entry_k,self.DASH_LOCK_MAX,link),np.int64)
            commands[:len(planned)]=planned
        if not given:commands[0]=int(mask)
        path=model_path(sim,plan,commands,game)
        modes=np.asarray(path.states[K.MODE]);flags=np.asarray(path.flags)
        steer=(modes==K.M_SPRINT)&(np.asarray(path.states[K.PHASE])==2)&(np.asarray(path.states[K.GROUND])>0)
        locked=(np.isin(modes,(K.M_DASH,*K.RELINQUISHED,*K.NO_INPUT))|((flags&(K.F_RELINQ|K.F_NO_INPUT))!=0))&~steer
        lead=len(path.commands)-len(commands)  # path index j is frame origin+j; commands[0] is index lead+1
        start=np.flatnonzero(modes[lead+1:]==K.M_DASH)
        info={"dash_mask":int(mask),"lock_max":self.DASH_LOCK_MAX}
        if not len(start):return None,{**info,"reason":"modeled dash never starts"}
        j0=lead+1+int(start[0])
        free=np.flatnonzero(~locked[j0:])
        if not len(free):
            return None,{**info,"dash_frame":path.origin+j0,"reason":"input return not modeled inside lock_max"}
        j1=j0+int(free[0]);through=j1+2
        if through>len(path.commands) or through>self.profile.max_frames:
            return None,{**info,"dash_frame":path.origin+j0,"input_frame":path.origin+j1,
                         "reason":"lock end past the checked horizon"}
        # the roll is causal: its first `through` frames are the roll of the cut commands (the scan reads only box,
        # flags, check_flags, commands, origin and stage; hold_end is not re-derived)
        n=through
        check=replace(path,commands=path.commands[:n],latched=path.latched[:n],states=path.states[:,:n+1],
                      box=path.box[:n+1],pos=path.pos[:n+1],flags=path.flags[:n+1],check_flags=path.check_flags[:n+1],
                      game=path.game[:n+1])
        return geo.scan(check),{**info,"dash_frame":path.origin+j0,"input_frame":path.origin+j1,
                                "checked_through":check.through,
                                "scope":"dash + input-less inertia + send delay; all owners and delayed hazards"}

    def _transfer_source_matches(self,rs,goal):
        trk=getattr(rs,"trk",None)
        source=getattr(trk,"now",{}).get(goal.caster) if goal is not None else None
        if source is None or getattr(source[2],"fam",None)!=goal.responsibility.family:return False
        values=(getattr(trk,"T",None),getattr(source[2],"t0",None),self._clock,goal.cast_ta)
        if any(isinstance(v,bool) or not isinstance(v,(int,float,np.number)) for v in values):return False
        return bool(np.isfinite(values).all() and abs((values[0]-values[1])-(values[2]-values[3]))<=2/60.)

    def _arm_hook_start(self,offer,send):
        if offer.details.get("vault_hook"):
            if offer.details.get("distance_vault"):
                cs=offer.draft.run.v["cs"]
                self._hook_start={"move":offer.move,"origin":send.frame,"targets":(cs.f_press,cs.f_press+1),
                                  "sent_targets":set(),"seen_frame":None}
                self._note("b2_hook_start_expected",frame=send.frame,move=vars(offer.move),
                           targets=[cs.f_press,cs.f_press+1],source="explicit manual table; no trajectory certificate")
            else:super()._arm_hook_start(offer,send)

    def _failure_exposure(self,move,origin,failed,ta):
        if move.family==waypoint.FAMILY:
            context=self._waypoint_responsibility.get(move)
            if context is None:self._stop("missing critical waypoint failure responsibility",failed)
            move,ta=context
        if move.family=="RUNE_TRANSFER":
            context=self._transfer_responsibility.get(move)
            if context is None:self._stop("missing critical rune-transfer failure responsibility",failed)
            move,ta=context
        if move.family=="VAULT_IDLE":
            context=self._vault_responsibility.get(move)
            if context is None:self._stop("missing critical vault failure responsibility",failed)
            self._note("vault_failure_responsibility",frame=failed,strike_target=vars(move),responsible_jump=vars(context[0]),
                       frame_basis="first observed vault opportunity, not a backdated antic; jump game origin bound separately")
            move,ta=context
        return super()._failure_exposure(move,origin,failed,ta)

    def _geometry(self,forecast,move,origin,ta=None):
        rs=getattr(forecast,"rs",None)
        obs=None if rs is None else getattr(rs.trk,"now",{}).get(move.target_iid)
        if obs is None:raise GeometryUnavailable("manual air target instance unavailable")
        if getattr(obs[2],"fam",None)!="CC_SLAM":raise GeometryUnavailable("manual air target no longer slamming")
        if ta is not None and abs((float(rs.trk.T)-float(obs[2].t0))-(self._clock-ta))>2/60.:
            raise GeometryUnavailable("manual air target clock belongs to another instance")
        return B2Geometry(forecast,origin,move,obs[2])

    def _query(self,forecast,move,path,contact_frame=None,*,geometry=None):
        geo=geometry or self._geometry(forecast,move,path.origin,ta=self._air_plan.ta if self._air_plan is not None else None);scan=geo.scan(path)
        if not scan.complete:raise GeometryUnavailable("manual air geometry coverage incomplete")
        retained=[]
        for c in scan.contacts:
            # Existing 2-frame buffered enemy-hit rule, bound only to this
            # modeled target contact. Its delayed hazards are never removed.
            if (contact_frame is not None and c.owner_iid==move.target_iid and c.kind in {"body","move"}
                    and contact_frame-2<=c.frame<=contact_frame):continue
            retained.append(c)
        return retained

    def _continuations(self,path,sim,geo,move,*,wall_validator=None):
        """Reuse the B2 lower bound; no pre-contact target exemption after bounce."""
        from .knife_chain_post_actions import ordinary_post
        from .knife_chain_commitment import Continuation,FullContinuationScan,assess_continuations
        parent=replace(path,stage="commitment")
        ref=f"air:{move}:{path.through}";options=[];paths={}
        for kind in ("left_landing","right_landing"):
            p=ordinary_post(parent,sim.params,sim.terrain,kind=kind,profile=self.profile)
            paths[kind]=p
            executable=self.continuation_executable(kind,p)
            if wall_validator is not None:
                executable=bool(executable and wall_validator(p))
            options.append(Continuation(kind,kind,ref,geo.ref(p),
                p.through if p.end=="handback" else None,
                executable,"pass",geo.scan(p)))
        def full(option):
            p=ordinary_post(parent,sim.params,sim.terrain,kind=option.kind,profile=self.profile,full=True)
            scan=replace(geo.scan(p),path_ref=option.path_ref)
            if wall_validator is not None and not wall_validator(p):
                scan=replace(scan,complete=False,source=scan.source+"; wall-free validator rejected continuation")
            return FullContinuationScan(scan,p.through)
        return assess_continuations(tuple(options),target_move=move,bounce_state_ref=ref,
            bounce_frame=path.through,short_frames=self.profile.short_frames,minimum_kinds=2,
            full_scan=full,unavailable_errors=(NominalUnsupported,GeometryUnavailable))

    def _propose(self,planner,ws,start,hold,prefix,forecast,prefs,ctx):
        if self.arm!="B":return None
        if self.budget is not None:self.budget.check()
        f=self.dispatch.frame
        if self.policy_gate_reason is not None:
            if self.commitment:self._recover("policy priority gate: "+self.policy_gate_reason,f)
            return None
        if self.recovery is not None:return self._recovery_offer()
        if getattr(self,"_bounce",None) is not None:
            from . import knife_chain_bounce_table as bounce_table
            if self.post_context is None:return bounce_table.offer(self,forecast,prefs)
            bounce_table.end(self,"handback","real bounce not taken by the table")
        if (getattr(self,"_wall_pressure",None) is not None and not (self._wall_pressure.get("yielded",False) or self._wall_pressure.get("landing",False))):
            from .knife_chain_wall_native import propose as wall_propose
            if self._context is None:
                self._recover("wall-side current context unavailable",f);return None
            tick,sim,_,_=self._context
            return wall_propose(self,tick[1],tick[2],sim,forecast,prefs,tick[3])
        if self._check_hook_start(f):
            return self._recovery_offer() if self.recovery is not None else None
        transfer_active=self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM
        if transfer_active and self.post_context is not None:
            self._transfer_bounce_exit()
            transfer_active=self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM
        if transfer_active:
            if self._context is None:
                self._recover("rune transfer current context unavailable",f);return None
            tick,sim,_,_=self._context
            offer=self._transfer_offer(tick[1],tick[2],sim,forecast,prefs,tick[3])
            if offer is not None or getattr(prefs,"waypoint",None) is None or self.runner.run is not None:return offer
            # its approach was handed back at this step: the plan's next stage starts on the same tick
        if self._plan_takes_vault_approach(prefs):
            # Task 182: running keys only (no jump, no strike claim) and the plan's next stage names its place: it takes the keys at this
            # step, as a side approach hands back at a tactical boundary; the keys already sent stay the next owner's prefix.
            self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
            self._press=self._accepted=self._hit=None
            self._vault_ready=False
            self._note("vault_approach_handoff",frame=f,target=self.runner.run.v.get("iid"),kind=prefs.waypoint.kind)
            self._abandon("the plan's stage took over from the vault approach")
        if self.runner.run is not None and self.runner.run.chain==waypoint.PROGRAM or (
                getattr(prefs,"waypoint",None) is not None and self.runner.run is None
                and self.commitment is None and self.post_context is None):
            if self._context is None:
                if self.runner.run is not None:self._recover("waypoint current context unavailable",f)
                return None
            tick,sim,_,_=self._context
            return self._waypoint_offer(tick[1],tick[2],sim,forecast,prefs)
        pressure=getattr(prefs,"wall_pressure",None)
        if (self.commitment is None and self.post_context is None and pressure is not None
                and pressure.target==getattr(prefs,"target",None) and pressure.kind=="side"):
            return None  # L2's wall-gap ground slash must not become a fresh jump/vault
        entry=getattr(prefs,"entry_attack",None)
        if (self.runner.run is None and self.commitment is None and self.post_context is None and entry is not None
                and entry.target==getattr(prefs,"target",None) and entry.kind in {"side","stomp"}):
            if (self._transfer_ready and self._context is not None and self._transfer_goal is not None
                    and self._transfer_goal.source_kind=="SWITCH"):
                if entry.kind=="stomp" and self._vault_domain(forecast,prefs):
                    # Task 179 (#296, the person 11-05: when the other one jumps, go OVER the standing / walking
                    # target; reuse the existing Idle / Walk vault): inside the vault's own domain its distance
                    # table (near jump, small-hop hook, ground approach) goes first. With no vault action now the
                    # SWITCH stomp below keeps its first contact, as before.
                    from .knife_chain_vault_native import propose as propose_vault
                    vault=propose_vault(self,planner,forecast,prefs)
                    if vault is not None or self.recovery is not None or self.runner.run is not None:return vault
                # The explicit, observed SWITCH entry owns its first contact.
                # Optional Idle-vault detection must not swallow it by returning
                # no recipe. Active owners and every transfer check still apply.
                tick,sim,_,_=self._context
                return self._transfer_offer(tick[1],tick[2],sim,forecast,prefs,tick[3])
            if entry.kind=="side":
                return None  # ordinary side-slash rows after approach, never a fresh stomp/vault
        vault_active=self.runner.run is not None and self.runner.run.chain=="vault_idle"
        if self.vault_enabled and (vault_active or (self._vault_ready and self.commitment is None and self.post_context is None)):
            from .knife_chain_vault_native import propose as propose_vault
            if self._context is not None:
                return propose_vault(self,planner,forecast,prefs)
            return None
        if self.post_context is not None:
            move=self.post_context["move"];self._air_finished.add(move)
            self._note("air_real_bounce_handoff",frame=f,move=vars(move),source="observed target DownSlash hit plus bounce")
            self.post_context=None;self._post_seed=None;self._post_kind=None;self._air_plan=None
            self._abandon("manual air real bounce handback");return None
        if self._context is None:return None
        tick,sim,guard,bombs=self._context;_,state,game,ground,accepting=tick
        if sim.fo!=f or sim.f!=f or len(sim.prefix)!=1 or not complete_hf(state):return None
        queued,basis=self.queued_prefix(f,state)
        if queued is None or queued!=int(sim.prefix[0]):
            if self.commitment:self._recover("manual air input prefix mismatch",f)
            return None
        if self.commitment is not None:
            plan=self._air_plan
            if plan is None or plan.move!=self.commitment["move"]:
                self._recover("manual air commitment identity missing",f);return None
            draft=logical_copy(self.runner);mask=advance(draft,plan,state,game)
            if mask is None:
                self._air_finished.add(plan.move);self._recover("manual air table ended before observed bounce",f);return None
            # Check the actual queued/current path afresh, not cached safety.
            # A short current check cannot certify the unexamined later tail.
            k=int(round((game-plan.ta)*60.))
            commands=render(self.runner,plan,k,3)
            try:
                path=model_path(sim,plan,commands,game)
                problem=direct_path_problem(plan,path,sim.hold)
                if problem:
                    self._air_finished.add(plan.move);self._recover(problem,f);return None
                predicted=(f+plan.contact_k-k if self._hit is None else None)
                bad=self._query(forecast,plan.move,path,contact_frame=predicted)
            except GeometryUnavailable as exc:
                self._air_finished.add(plan.move);self._recover("manual air current geometry unknown: "+str(exc),f);return None
            if bad:
                self._air_finished.add(plan.move);self._recover("manual air current external path blocked",f);return None
            return B2Offer("active",None,draft,int(mask),0.,plan.move,{"manual_air":True,"phase":draft.run.link})
        if self._air_context is None:return self._transfer_offer(state,game,sim,forecast,prefs,ground)
        if self._transfer_ready and self._air_context[1]["iid"]!=getattr(prefs,"target",None):
            return self._transfer_offer(state,game,sim,forecast,prefs,ground)
        try:
            made=plan_entry(self.runner,state,game,sim,self._air_context)
            if made is None:return self._transfer_offer(state,game,sim,forecast,prefs,ground)
            plan,commands,contact=made
            if plan.move in self._air_finished or plan.move in self._failed_hook_moves:return None
            # The current commitment ends at modeled bounce, not at a guessed
            # landing. Post-bounce commands must be selected from real STATE.
            path=model_path(sim,plan,commands[:contact-1],game,contact=contact)
            problem=direct_path_problem(plan,path,sim.hold)
            if problem:
                self._note("air_entry_rejected",frame=f,program=plan.program,reason=problem);return None
            geo=self._geometry(forecast,plan.move,f,ta=plan.ta)
            bad=self._query(forecast,plan.move,path,contact_frame=plan.contact_frame,geometry=geo)
            exits=None if bad else self._continuations(path,sim,geo,plan.move)
        except (GeometryUnavailable,NominalUnsupported) as exc:
            self._note("air_entry_unchecked",frame=f,reason=str(exc));return None
        if bad:
            self._note("air_entry_rejected",frame=f,first={"frame":bad[0].frame,"owner":bad[0].owner_iid,"kind":bad[0].kind})
            return None
        if exits.verdict!="pass":
            self._note("air_no_exit",frame=f,continuations=asdict(exits));return None
        draft=self.runner.fork_empty(AirAnchor());draft.run=Run(plan.program,"align",plan.variables())
        mask=advance(draft,plan,state,game)
        if mask is None:return None
        self._air_plan=plan
        return B2Offer("manual_commitment",path,draft,int(mask),0.,plan.move,
            {"manual_air":True,"predicted_bounce":plan.contact_frame,"phase":draft.run.link,
             "entry_k":plan.entry_k,"safety_basis":"fresh nominal path through modeled contact; unfitted manual table",
             "post_bounce":"N=2 short or one full exit; normal planner after real bounce",
             "continuations":asdict(exits),"plan":vars(plan)})

    def _decline_source_tail(self,goal,state):
        """Account for the observed own bounce's failed tail, not a new send."""
        key=(goal.caster,goal.cast_fa)
        first=key not in self._transfer_finished
        self._transfer_finished.add(key)
        if (not first or self.commitment is not None or goal.source_kind!="BOUNCE"
                or goal.responsibility.family!="CC_SLAM"):return  # a failure with commitment is recorded by _recover
        exposure=self._failure_exposure(goal.responsibility,goal.cast_fa,state["f"],goal.cast_ta)
        exposure.observe(state,game_time=self._clock)
        self._failure_exposures.append(exposure)
        self._note("b2_failure_exposure",frame=state["f"],exposure=exposure.as_dict(),
                   source="observed own DownSlash hit+bounce; tail admission declined; no new tail send")

    def _transfer_hit_check(self,state,sim,plan,path,game):
        """An accepted strike's conditional hit path, not a hit/handback receipt."""
        f=state["f"];cf=plan.contact_frame;source=self.commitment
        if (source is None or source["move"]!=plan.move or type(self._press) is not int
                or type(self._accepted) is not int or not self._press<=self._accepted<=f
                or type(cf) is not int or not 1<=cf-f<=2
                or plan.move not in self._transfer_target_moves):return path,frozenset()
        body=transfer.stationary_antic_body_for_hit_check(state,plan.iid,path.through)
        if body is None:return path,frozenset()
        hit=model_path(sim,plan,path.offered,game,contact=cf-f)
        # Do not waive a real body overlap or infer protection from unknown
        # noBounceCooldown settings. Only a clear post-hit body margin can pass.
        boxes=hit.box[cf-f:]
        overlap=(boxes[:,0]<=body[2])&(boxes[:,2]>=body[0])&(boxes[:,1]<=body[3])&(boxes[:,3]>=body[1])
        if np.any(overlap):return path,frozenset()
        from ssbot.knowledge import kinematics as K
        protected=frozenset(hit.origin+j for j in range(cf-f+1,len(hit.flags)) if hit.flags[j]&K.F_INVULN)
        # Keep the physical hit branch, but NEW predicted protection must not
        # erase another owner, any delayed hazard, or an armed target collider.
        flags=(hit.check_flags&~K.F_INVULN)|(path.check_flags&K.F_INVULN)
        return replace(hit,check_flags=flags),protected

    def _plan_takes_vault_approach(self,prefs):
        run=self.runner.run
        return (getattr(prefs,"waypoint",None) is not None and run is not None and run.chain=="vault_idle" and run.link=="approach"
                and self.post_context is None and self.recovery is None)

    def _waypoint_offer(self,state,game,sim,forecast,prefs):
        """Task 182 (SSBOT_FORUM_TWO_PLAN; knife_chain_waypoint): one bounded floor approach of the running plan phase. L2 names
        the place and the frame each tick; withdrawing them or reaching the place hands back at this step, the keys already
        sent staying the next owner's actual prefix. A step blocked or a place no longer reachable in time hands back through
        recovery, which keeps its failure responsibility; a fresh start only ever declines."""
        from types import SimpleNamespace
        f=state["f"];run=self.runner.run
        active=run is not None and run.chain==waypoint.PROGRAM
        goal=getattr(prefs,"waypoint",None)
        def back(why,event):
            if active:
                self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
                self._press=self._accepted=self._hit=None
                self._note(event,frame=f,reason=why,x=run.v.get("x"),by_f=run.v.get("by_f"),kind=run.v.get("kind"))
                self._abandon(why)
            return None
        if goal is None or (active and tuple(run.v["plan"][:1])+tuple(run.v["plan"][2:])!=tuple(goal.plan[:1])+tuple(goal.plan[2:])):
            return back("L2 withdrew the place","waypoint_withdrawn")
        key=(tuple(goal.plan[0]),goal.plan[2])
        if key in self._waypoint_failed:return None
        if sim.fo!=f or sim.f!=f or len(sim.prefix)!=1 or not complete_hf(state):
            if active:self._recover("waypoint input context unavailable",f)
            return None
        queued,_=self.queued_prefix(f,state)
        if queued is None or int(sim.prefix[0])!=queued:
            if active:self._recover("waypoint actual queued prefix mismatch",f)
            return None
        if not active:
            mode=self._locked_mode(sim)
            if mode is not None or (state.get("hero") or {}).get("hero_accepting_input") is not True:
                self._note("waypoint_start_deferred",frame=f,mode=mode,owner="current owner keeps the keys")
                return None
        mask,what=waypoint.next_mask(sim,goal,f)
        if what=="arrived":
            return back("waypoint reached","waypoint_arrived")
        def failed(reason,**data):
            if active or self._waypoint_declined!=(key,reason):
                self._note("waypoint_rejected",frame=f,reason=reason,active=active,x=goal.x,by_f=goal.by_f,kind=goal.kind,**data)
            self._waypoint_declined=(key,reason)
            if active:
                self._waypoint_failed.add(key)
                self._recover("waypoint "+reason,f)
            return None
        if what=="late":return failed("cannot arrive by its frame from here")
        move=MoveInstance(**run.v["move"]) if active else MoveInstance(goal.source,f,waypoint.FAMILY)
        # a failure answers for the jump this Run is about, from the Run's first frame (no backdated antic, no invented clock)
        self._waypoint_responsibility.setdefault(move,(MoveInstance(goal.source,f,goal.family),None))
        current=getattr(getattr(getattr(forecast,"rs",None),"trk",None),"now",{}).get(goal.source)
        if current is None:return failed("support unavailable")
        plan=SimpleNamespace(iid=goal.source,move=move,origin=f,entry_k=0,press_k=None,contact_frame=None)
        try:
            path=model_path(sim,plan,np.array([mask],np.int64),game)
            geo=B2Geometry(forecast,f,move,current[2])
            dash_bit=B["DASH"].bit_length()-1
            if (int(mask)&B["DASH"] and not int(sim.prefix[0])&B["DASH"] and not sim.hold.latched[0,dash_bit]
                    and not sim.hold.desired[0,dash_bit]):
                # a new dash impulse: through the motion it locks, as every other owner's
                lock,info=self._dash_lock_scan(sim,plan,mask,game,geo,waypoint.PROGRAM,commands=np.full(self.DASH_LOCK_MAX,int(mask),np.int64))
                if lock is None or not lock.complete or lock.contacts:
                    first=None if lock is None or not lock.contacts else asdict(lock.contacts[0])
                    self._note("waypoint_dash_refused",frame=f,first=first,active=active,**info)
                    mask=0 if goal.over is not None else int(mask)&~B["DASH"]   # past a body the key alone is no way
                    path=model_path(sim,plan,np.array([mask],np.int64),game)
                else:self._note("waypoint_dash_checked",frame=f,**info)
            scan=geo.scan(path)
        except GeometryUnavailable as exc:
            return failed("geometry unavailable: "+str(exc))
        if not scan.complete or scan.contacts:
            return failed("external step blocked",first=None if not scan.contacts else asdict(scan.contacts[0]))
        if active:
            draft=logical_copy(self.runner);draft.run.v.update(x=float(goal.x),by_f=int(goal.by_f),what=what)
        else:
            draft=self.runner.fork_empty(AirAnchor())
            draft.run=Run(waypoint.PROGRAM,"go",{"iid":goal.source,"ta":float(game),"plan":list(goal.plan),"x":float(goal.x),
                                                 "by_f":int(goal.by_f),"kind":goal.kind,"f_open":f,"move":asdict(move),"what":what})
        return B2Offer("active" if active else "manual_commitment",path,draft,int(mask),0.,move,
            {"manual_air":True,"waypoint":True,"kind":goal.kind,"x":float(goal.x),"by_f":int(goal.by_f),"what":what,
             "phase":"go","predicted_bounce":None,"checked_through":path.through,
             "safety_basis":"bounded approach: the dash through its lock, every step through all owners; no route certificate"})

    def _transfer_offer(self,state,game,sim,forecast,prefs,ground):
        f=state["f"];target=getattr(prefs,"target",None)
        self._follow_fallback=None;self._follow_made=None
        run=self.runner.run
        active=run is not None and run.chain==transfer.PROGRAM
        if active:target=run.v["iid"]  # the already-sent action keeps the same target through its real bounce
        entry=getattr(prefs,"entry_attack",None)
        wanted=getattr(prefs,"target",None)
        changed=wanted is not None and wanted!=target
        side=entry is not None and entry.target==target and entry.kind=="side"
        if (active and run.link=="bounce_tail" and (changed or side)
                and not transfer.bounce_tail_pending(state,self._transfer_goal,game)):
            # The real hammer-off is a planned boundary. A long source tail
            # must not carry its old target into another approach commitment.
            self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
            self._press=self._accepted=self._hit=None
            self._transfer_ready=False
            self._abandon("observed source hammer tail ended: tactical target changed" if changed else
                          "observed source hammer tail ended: tactical side attack")
            self._note("target_entry_target_handoff" if changed else "target_entry_side_handoff",
                       frame=f,old_target=target,target=wanted if changed else target)
            return None
        goal=self._transfer_goal
        if (active and isinstance(goal,transfer.ReturnGoal) and run.link in ("walk","dash","jump","air")
                and not self._return_request_holds(prefs,goal)):
            # SSBOT_FORUM_TWO_RETURN_AIR (#316, Sol seq 239 a): L2 no longer makes this air return (target, pose or
            # state changed; a standing gap opened: the ground return takes over). Its approach is handed back at
            # this step, the keys already sent stay the next owner's actual prefix; a strike row already chosen
            # (link strike) finishes under its own ownership (real hit + bounce, or its miss).
            link=run.link;req=getattr(prefs,"return_request",None)
            self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
            self._press=self._accepted=self._hit=None
            self._transfer_ready=False;self._transfer_goal=None
            self._abandon("air return request withdrawn: approach handed back")
            self._note("return_request_released",frame=f,target=target,link=link,
                       request=None if req is None else asdict(req))
            return None
        if active and run.link in transfer.FOLLOW_LINKS and ground:
            self._follow_landed(state,run)   # Task 183: the actual landing ends the follow-up Run
            return None
        no_witness=None
        if active and run.link=="air":
            why=self._no_strike_overhead(state,sim,target)
            if (why is not None and not ground
                    and transfer.follow_scope(self._transfer_goal,target,bool(run.v.get("follow_close")))):
                # Task 183 seq 262: the bounce follow-up reads the gap first; this hand-back stands if it takes nothing
                no_witness=why;why=None
            if why is not None:
                # Task 179 #317 (Sol seq 240 乙): an air transfer / continuation Run already over its target with no
                # strike witness possible for her current state hands back at this step through B2 recovery: the
                # keys already sent and latched stay the next owner's actual prefix, the failure exposure and the
                # same-move no-retry stay; a chosen strike row (link strike), a source tail or a hook is not here.
                self._note("transfer_no_witness_handback",frame=f,target=target,reason=why,
                           owner="B2 recovery hands back; failure responsibility kept")
                self._recover("transfer air run over its target with no strike witness: "+why,f)
                return None
        approach_only=bool(run.v.get("_approach_only")) if active else bool(side and self._transfer_goal is not None
            and self._transfer_goal.source_kind=="SWITCH")
        if approach_only:
            enemy=next((e for e in transfer.clappers(state) if e["iid"]==target),None)
            hp=(state.get("hero") or {}).get("pos") or ()
            ep=() if enemy is None else enemy.get("pos") or ()
            near_u=self.runner.chains[transfer.PROGRAM].cfg["STOMP"]["jump_root"]
            if side and _plan_source_in_air(state,run.v["caster"] if active else self._transfer_goal.caster):
                near_u=min(near_u,PLAN_SIDE_NEAR_U)
            near=(len(hp)>=1 and len(ep)>=1 and type(hp[0]) in (int,float)
                  and type(ep[0]) in (int,float) and np.isfinite([hp[0],ep[0]]).all()
                  and abs(ep[0]-hp[0])<=near_u)
            target_attack=enemy is not None and transfer.control(enemy)[0] in (transfer.AIR_ATTACK_STATES |
                {"Jump Antic","Cast Slam Antic","Jump","Air"})
            source_blocked=False
            if not (changed or not side or target_attack or near):
                # This recipe is a straight approach, never a crossing skill.
                # Keep the active Run's source, rather than a new tactical hint.
                caster=run.v["caster"] if active else self._transfer_goal.caster
                source=next((e for e in transfer.clappers(state) if e["iid"]==caster),None)
                sp=None if source is None else source.get("pos")
                known=(len(hp)>=1 and len(ep)>=1 and isinstance(sp,(list,tuple)) and len(sp)>=1
                       and all(type(v) in (int,float) and np.isfinite(v) for v in (hp[0],ep[0],sp[0])))
                try:obstacle=transfer.body_box(source) if known else None
                except (TypeError,ValueError,OverflowError):obstacle=None
                if obstacle is None:
                    self._note("rune_transfer_unchecked",frame=f,reason="side approach source geometry unavailable")
                    if active:self._recover("side approach source geometry unavailable",f)
                    return None
                source_blocked=(min(hp[0],ep[0])<=obstacle[2] and max(hp[0],ep[0])>=obstacle[0])
                if source_blocked and _passes_under(source,obstacle,state):
                    # Task 182 (SSBOT_FORUM_TWO_PLAN; design: the lure's return goes back under the jumper on its observed
                    # take-off): a source in the air whose body is above her head is no obstacle now. The Run's own
                    # per-step scan and the dash-lock scan still read its body and hammer on the way; once it comes down
                    # to her head this is blocked again and the Run hands back as before.
                    source_blocked=False
                if source_blocked:self._note("target_entry_side_source_blocked",frame=f,source=caster,active=active)
            if changed or not side or target_attack or near or source_blocked:
                if active:
                    self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
                    self._press=self._accepted=self._hit=None
                    self._transfer_ready=False
                    self._abandon("side approach reached observed range/tactical boundary")
                    self._note("target_entry_side_handoff",frame=f,old_target=target,target=wanted,
                               arrived=bool(near),target_attack=bool(target_attack),intent_ended=not side,source_blocked=bool(source_blocked))
                return None  # current queued keys remain actual prefix for the next owner
        if not self._transfer_ready and (run is None or run.chain!=transfer.PROGRAM):return None
        queued,_=self.queued_prefix(f,state)
        if queued is None or int(sim.prefix[0])!=queued:
            if active:self._recover("rune transfer actual queued prefix mismatch",f)
            return None
        if not active:
            mode=self._locked_mode(sim)
            if mode is not None:
                # Task 179 (live 786 2607: the SWITCH entry bound inside her own leftward air dash, 2610-2616 took
                # no input): a fresh transfer never starts inside a dash or a relinquished motion; its keys could
                # not change the route. The current owner keeps the keys; the start is retried once she is free.
                self._note("rune_transfer_start_deferred",frame=f,target=target,mode=mode,
                           owner="current owner keeps the keys",reason="hero in a dash or relinquished motion")
                return None
        rs=getattr(forecast,"rs",None)
        made=transfer.propose(self.runner,state,game,sim,target,ground,self._context[3],self._transfer_finished,self._transfer_goal,
                              **({"idle_evidence":self._idle_ev} if self._idle_ev else {}),
                              **({"approach_only":True} if approach_only else {}))
        if made is None or made[0] is None:
            if active:self._recover((made[1].ended_reason if made is not None else None)
                                    or "rune transfer ended or target began a new move before real bounce",f)
            return None
        draft,plan,path,mask=made
        if plan.move in self._failed_hook_moves:return None
        if transfer.plan_over_call(draft.run.v) and draft.run.link in ("jump","air") and int(mask)&(B["L"]|B["R"]):
            # Task 182 (Sol seq 255 F2): rising to go over a body: no side key while holding it would carry her box into that body; she
            # rises first and the clean strike row (press_now_row clean) takes over from there. The hold and the J stay the link's.
            body=transfer.body_box(next((e for e in transfer.clappers(state) if e["iid"]==plan.iid),None) or {})
            held=model_path(sim,plan,np.full(14,int(mask),np.int64),game)
            if body is not None and transfer.enters_body(held.box,body,len(held.box)):
                mask=int(mask)&~(B["L"]|B["R"])
                path=replace(model_path(sim,plan,np.array([mask],np.int64),game),stage=path.stage,assumptions=path.assumptions)
                self._note("transfer_side_held_back",frame=f,target=plan.iid,link=draft.run.link)
        current=None if rs is None else getattr(rs.trk,"now",{}).get(plan.iid)
        if current is None:
            if active:self._recover("rune transfer support unavailable",f)
            return None
        if self._follow_due(self._transfer_goal,draft,run,active,ground,approach_only):
            handled,offer=self._follow_offer(state,game,sim,forecast,prefs,made,run if active else None,current)
            if handled:return offer
            if self._follow_made is not None:
                # Task 183 seq 265: an owned middle route released to the seam approach: its air / strike draft goes on below
                made=self._follow_made;self._follow_made=None;draft,plan,path,mask=made
        if no_witness is not None:
            # (the deferred Task 179 #317 hand-back: the follow-up took nothing this tick)
            self._note("transfer_no_witness_handback",frame=f,target=target,reason=no_witness,
                       owner="B2 recovery hands back; failure responsibility kept")
            self._recover("transfer air run over its target with no strike witness: "+no_witness,f)
            return None
        target_ta=None;target_move=None;conditional_contact=None
        try:
            goal=self._transfer_goal
            if goal is not None and goal.source_kind=="SWITCH" and not draft.run.v.get("_entry_source_confirmed"):
                if isinstance(goal,transfer.ReturnGoal):
                    if not self._return_source_ended(state,goal):
                        raise GeometryUnavailable("return request source move not ended")
                elif not self._transfer_source_matches(rs,goal):
                    raise GeometryUnavailable("tactical switch source instance unavailable or changed")
                draft.run.v["_entry_source_confirmed"]=True
            geo=B2Geometry(forecast,f,plan.move,current[2])
            if not active and isinstance(goal,transfer.ReturnGoal):
                why=self._return_admission(state,sim,plan,game,geo)
                if why is not None:
                    key=(goal.caster,goal.cast_fa,why)
                    if self._return_admission_noted!=key:
                        self._return_admission_noted=key
                        self._note("return_request_start_deferred",frame=f,target=plan.iid,reason=why,
                                   owner="current owner keeps the keys")
                    return None
            if draft.run.link in transfer.HOOK_LINKS and not isinstance(draft.run.v.get("hook_press"),dict):
                raise GeometryUnavailable("transfer hook press anchor unavailable")
            if draft.run.link=="bounce_tail":
                if goal is None or goal.responsibility.family!="CC_SLAM" or not self._transfer_source_matches(rs,goal):
                    raise GeometryUnavailable("source hammer tail instance unavailable or changed")
                admitted=bool(active and run.v.get("source_tail_admitted"))
                if not admitted:
                    if f!=goal.cast_fa:raise GeometryUnavailable("source tail admission missed actual bounce decision")
                    end=transfer.predicted_tail_end(state,goal)
                    if end is None or not 1<=end-f+1<=self.profile.max_frames:
                        raise GeometryUnavailable("source hammer tail family clock unavailable")
                    # Wallward travel now requires a separate L2 wall-pressure
                    # successor with a checked landing/next knife. Never hold a
                    # direction for an entire hammer tail as a wall-cling route.
                    tail_mask=0
                    tail=model_path(sim,plan,np.full(end-f,tail_mask,np.int64),game)
                    whole=geo.scan(tail)  # ALL owners, including the source and destination; no admission exemption
                    if not whole.complete or whole.contacts:
                        self._note("source_tail_declined",frame=f,through=tail.through,complete=whole.complete,
                            first=None if not whole.contacts else asdict(whole.contacts[0]))
                        self._decline_source_tail(goal,state)
                        if active:self._recover("source hammer tail admission blocked",f)
                        return None
                    draft.run.v["source_tail_admitted"]=True
                    draft.run.v["source_tail_checked_through"]=tail.through
                    draft.run.v["source_tail_mask"]=tail_mask
                    self._note("source_tail_admitted",frame=f,through=tail.through,mask=tail_mask,
                        basis="current source instance; empirical slam-family end+1; all-owner fixed tail row",
                        scope="one go/no-go, current two-frame checks afterwards; no escape guarantee")
                tail_mask=int(draft.run.v.get("source_tail_mask",0))
                if tail_mask!=mask:
                    mask=tail_mask
                    path=model_path(sim,plan,np.array([mask],np.int64),game)
            dash_bit=B["DASH"].bit_length()-1
            if (int(mask)&B["DASH"] and not int(sim.prefix[0])&B["DASH"] and not sim.hold.latched[0,dash_bit]
                    and not sim.hold.desired[0,dash_bit]):
                # Task 179: a dash impulse pressed on THIS tick (the air recipe or the walk / dash link's clock) is
                # checked through the motion it locks, never the two-frame step only (live 786 2617: DASH+R from
                # the wall into the 2628 Slam 2; fork 786 closed loop 2633: a ground DASH+R into Slam 2).
                lock,info=self._dash_lock_scan(sim,plan,mask,game,geo,draft.run.link)
                if lock is None or not lock.complete or lock.contacts:
                    first=None if lock is None or not lock.contacts else asdict(lock.contacts[0])
                    if draft.run.link in {"walk","dash"} and ground:
                        # On the ground the same Run keeps running without the impulse (its owner and move); the
                        # next tick re-checks the due dash, the current step stays behind the ordinary gate.
                        self._note("rune_transfer_dash_refused",frame=f,first=first,active=active,
                                   complete=None if lock is None else lock.complete,**info,
                                   owner="same transfer Run runs without the dash this tick")
                        mask=int(mask)&~B["DASH"]
                        path=replace(model_path(sim,plan,np.array([mask],np.int64),game),stage=path.stage,
                                     assumptions={**path.assumptions,"dash_refused":True})
                    else:
                        # The air recipe chose this dash because the coast alone does not reach her: without it
                        # the Run has no route. A fresh start never starts (the current owner keeps the keys); an
                        # active Run hands back through B2 recovery, which keeps its failure responsibility.
                        self._note("rune_transfer_dash_refused",frame=f,first=first,active=active,
                                   complete=None if lock is None else lock.complete,**info,
                                   owner=("B2 recovery hands back" if active else "current owner keeps the keys"))
                        fb=self._seam_fallback(f,"air dash refused: locked motion blocked or unknown")
                        if fb is not None:return fb
                        if active:self._recover("rune transfer air dash refused: locked motion blocked or unknown",f)
                        return None
                else:self._note("rune_transfer_dash_checked",frame=f,**info)
            attacking=transfer.control(next(e for e in transfer.clappers(state) if e["iid"]==plan.iid))[0] in transfer.AIR_ATTACK_STATES
            w=self._hook_start
            hook_sent=bool(draft.run.link in transfer.HOOK_LINKS and w is not None and w["move"]==plan.move
                           and (w["sent_targets"] or w["seen_frame"] is not None))
            if hook_sent:
                from .knife_chain_face_hook import step_scan
                scan=step_scan(geo,path,draft.run.v,w,f,state)
                self._note("transfer_hook_step_checked",frame=f,contacts=len(scan.contacts),complete=scan.complete,
                           source=scan.source,scope="all owners and delayed hazards; current step only; no protection")
            elif draft.run.link in transfer.HOOK_LINKS:
                # Task 179 #308 (live L3 2682): the CLAW is not sent yet, so this tick commits the whole locked hook
                # and its forced bounce: all of the hook (knife_chain_face_hook.entry_scan), not one step, then at
                # every model control point the existing N=2 continuation lower bound's short pass (entry_outs)
                from .knife_chain_face_hook import entry_scan,entry_outs
                import time
                t0=time.perf_counter_ns()
                scan,controls=entry_scan(geo,path,draft.run.v,f)
                failed,outs=None,0
                if scan.complete and not scan.contacts:
                    failed,outs=entry_outs(geo,sim,draft.run.v,f,controls,self.profile.short_frames)
                    if failed is not None:
                        # a blocked type rejects with its first contact; an unknown or non-executable one as unchecked
                        first=failed["first"]
                        scan=replace(scan,contacts=() if first is None else (first,),complete=first is not None,
                                     source=scan.source+f"; forced bounce at control {failed['control']}: {failed['kind']} "
                                            +("not executable" if not failed["executable"] else "blocked or unknown")
                                            +"; below the N=2 short lower bound, no full-exit fallback at entry")
                self._note("transfer_hook_entry_checked",frame=f,contacts=len(scan.contacts),complete=scan.complete,
                           first=None if not scan.contacts else asdict(scan.contacts[0]),source=scan.source,
                           controls=len(controls),bounce_paths=outs,elapsed_ms=(time.perf_counter_ns()-t0)/1e6,
                           timing_scope="entry scan and bounce outs only")
            elif attacking:
                if getattr(current[2],"fam",None)!="CC_SLAM":raise GeometryUnavailable("air continuation attack family unsupported")
                identity=(plan.iid,current[2].fam,float(current[2].t0))
                prior=None if run is None else run.v.get("_target_attack")
                if prior is not None and prior!=identity:raise GeometryUnavailable("air continuation target began another attack")
                draft.run.v["_target_attack"]=identity
                target_ta=self._clock-(float(rs.trk.T)-float(current[2].t0))
                bound=self._transfer_target_moves.get(plan.move)
                if bound is None:bound=self._observed_transfer_move(state,plan.iid,"CC_SLAM")
                if bound is None or abs(bound[1]-target_ta)>2/60.:
                    raise GeometryUnavailable("air continuation target antic identity unavailable")
                target_move=bound[0]
                check=path;row=draft.run.v.get("row")
                if row is not None and plan.contact_frame is not None and plan.contact_frame>f+2:
                    commands=np.array([row["masks"][F-row["F0"]] for F in range(f+2,plan.contact_frame+1)],np.int64)
                    check=model_path(sim,plan,commands,game)
                protected=frozenset()
                if check is path:
                    check,protected=self._transfer_hit_check(state,sim,plan,path,game)
                    if check is not path:
                        conditional_contact=plan.contact_frame
                        self._note("transfer_conditional_hit_check",frame=f,contact_frame=conditional_contact,
                            target_iid=plan.iid,postcontact_body_frames=sorted(protected),actual_hit_receipt=False,
                            scope="accepted strike; clear stationary antic body only; other owners/all delayed unprotected")
                bad=self._query(forecast,plan.move,check,contact_frame=plan.contact_frame,geometry=geo)
                bad=[c for c in bad if not (c.frame in protected and c.owner_iid==plan.iid and c.kind in {"body","move"})]
                from .knife_chain_commitment import ContactScan
                scan=ContactScan(geo.ref(check),check.origin,check.through,tuple(bad),"same attack instance; actual contact-path query")
            elif (approach_only or draft.run.link=="bounce_tail" or (draft.run.link=="air" and draft.run.v.get("approach_recipe")=="air_dash")
                    or (draft.run.link=="air" and draft.run.v.get("seam_inner"))):
                # (Task 183 seq 263: a seam tick with no inner-side strike row is positioning, not a strike: its step is
                # checked against the target body too, so coming down on it hands back instead of an outer strike)
                scan=geo.scan(path)
            # A selected strike keeps the existing target-contact contract:
            # this short path has no modeled pogo, so its future body overlap
            # must not cancel an already pressed downslash as a false failure.
            else:scan=geo.preflight(path)
        except GeometryUnavailable as exc:
            self._note("rune_transfer_unchecked",frame=f,reason=str(exc))
            if draft.run.link=="bounce_tail" and goal is not None:
                self._decline_source_tail(goal,state)
            fb=self._seam_fallback(f,"external step unchecked: "+str(exc))
            if fb is not None:return fb
            if active:self._recover("rune transfer external step unchecked",f)
            return None
        if not scan.complete or scan.contacts:
            first=None if not scan.contacts else asdict(scan.contacts[0])
            self._note("rune_transfer_rejected",frame=f,first=first)
            fb=self._seam_fallback(f,"external step blocked"+("" if first is None else
                                   " (first contact frame %s, owner %s, %s)"%(first.get("frame"),first.get("owner_iid"),first.get("kind"))))
            if fb is not None:return fb
            if active:self._recover("rune transfer external step blocked",f)
            return None
        goal=self._transfer_goal
        responsibility=(transfer.MoveInstance(plan.caster,plan.cast_fa,"CC_CAST") if goal is None else goal.responsibility)
        self._transfer_responsibility.setdefault(plan.move,(responsibility,None if goal is None else goal.cast_ta))
        return B2Offer("active" if active else "manual_commitment",path,draft,int(mask),0.,plan.move,
            {"manual_air":True,"rune_transfer":True,"caster":plan.caster,"cast_fa":plan.cast_fa,
             "target_ta":target_ta,"target_attack_checked":attacking,
             "target_move":None if target_move is None else asdict(target_move),
             "tail_checked_through":draft.run.v.get("source_tail_checked_through"),
             "tail_mask":draft.run.v.get("source_tail_mask"),
             "approach_recipe":draft.run.v.get("approach_recipe"),"approach_only":approach_only,
             "strike_direction":None if draft.run.v.get("row") is None else draft.run.v["row"].get("approach_direction"),
             "strike_support":None if draft.run.v.get("row") is None else draft.run.v["row"].get("support","still"),
             "strike_walk":None if draft.run.v.get("row") is None else draft.run.v["row"].get("walk"),
             "conditional_hit_check":conditional_contact is not None,"conditional_contact":conditional_contact,
             "checked_through":path.through,"phase":draft.run.link,"predicted_bounce":None,
             "handoff":("observed range or tactical boundary; ordinary side rows" if approach_only else
                        "real hit+bounce reopens tactical target knife; observed source hammer tail retained"),
             "safety_basis":"manual distance recipe; current external step only; no full-flight safety certificate"})

    def _follow_due(self,goal,draft,run,active,ground,approach_only):
        """Task 183 (Sol seq 261): this tick decides the bounce follow-up: a real bounce off the target's own slam (two
        Clappers), airborne, its hammer tail over, not an approach; a sent strike row or hook finishes under its own
        ownership."""
        if (approach_only or ground
                or not transfer.follow_scope(goal,draft.run.v.get("iid"),bool(draft.run.v.get("follow_close")))):return False
        if draft.run.link=="bounce_tail" or not draft.run.v.get("source_tail_done"):return False
        if active and run.link not in transfer.FOLLOW_LINKS|{"air","bounce_tail"}:return False
        return draft.run.link in transfer.FOLLOW_LINKS|{"air","strike"}

    def _follow_landed(self,state,run):
        """Task 183: an owned follow-up Run on the actual ground. The middle is done only with her box between the two near
        body edges; a landing elsewhere is a failure (B2 recovery: failure responsibility kept); a left / right landing is
        done on the ground."""
        f=state["f"];fo=run.v.get("follow") or {}
        hb=transfer._hero_box(state.get("hero"));gap=transfer.two_gap(state,run.v.get("caster"))
        inside=bool(run.link=="land" or (gap is not None and hb is not None and gap.lo<hb[0] and hb[2]<gap.hi))
        self._note("transfer_follow_landed" if inside else "transfer_follow_missed",frame=f,link=run.link,kind=fo.get("kind"),
                   box=None if hb is None else list(hb),lo=None if gap is None else gap.lo,hi=None if gap is None else gap.hi,
                   planned_land_f=fo.get("land_f"),planned_box=fo.get("landing_box"))
        if not inside:
            self._recover("bounce follow-up landed outside the gap between the two bodies",f);return
        self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
        self._press=self._accepted=self._hit=None
        self._transfer_ready=False
        self._abandon("bounce follow-up done: "+("landed between the two bodies" if run.link=="middle" else "landed"))

    def _owned_route(self,state,game,sim,geo,plan,gap,old,link):
        """Task 183: an owned follow-up route goes on (its absolute row; past it no key for the middle, the same key for a
        landing) while the model still reaches the ground (the middle: inside the gap by MIDDLE_PAD_U) and the route's next
        transfer.FOLLOW_SCAN_F frames (through the landing once it is that near) scan clean for all owners: the whole route
        was scanned when it was chosen (as the source tail's one admission, then the current steps). seq 262: the row it
        returns is the checked key stream itself, re-anchored at this tick's first free mask frame through the modelled
        landing, so the keys sent are the keys checked even when she lands later than first planned. None: blocked (noted),
        the caller searches again with whole routes."""
        f=state["f"];i=f+2-int(old["F0"]);rest=np.asarray(old.get("masks") or (),np.int64)[max(0,i):]
        tail=0 if link=="middle" else int(old["dir"])
        commands=np.r_[rest,np.full(transfer.MIDDLE_HORIZON_F,tail,np.int64)]
        p=model_path(sim,plan,commands,game)
        j=transfer._landing_index(p.flags,len(sim.prefix)+1)
        why=None
        if j is None:why="no modelled ground within the horizon"
        else:
            b=p.box[j]
            if link=="middle" and not (b[0]>=gap.lo+transfer.MIDDLE_PAD_U and b[2]<=gap.hi-transfer.MIDDLE_PAD_U):
                why="modelled landing no longer inside the gap"
            else:
                sc=geo.scan(p,limit=min(j,transfer.FOLLOW_SCAN_F))
                if sc.complete and not sc.contacts:
                    row=[int(m) for m in commands[:j-len(sim.prefix)]]
                    return link,{**old,"F0":f+2,"masks":row,"land_f":int(p.origin+j),
                                 "release_F":int(old["release_F"]) if link=="middle" else f+2+len(row),
                                 "landing_box":[float(v) for v in b]},p,sc
                hit=None if not sc.contacts else sc.contacts[0]
                why="route blocked"
                self._note("transfer_follow_route_blocked",frame=f,link=link,complete=sc.complete,
                           first=None if hit is None else asdict(hit),
                           first_box=None if hit is None else [float(v) for v in p.box[hit.frame-p.origin]])
        if why!="route blocked":self._note("transfer_follow_route_blocked",frame=f,link=link,reason=why)
        return None

    def _middle_choice(self,state,game,sim,geo,plan,gap,hb,old):
        """Task 183: the middle rows (transfer.middle_candidates: hold and release, or opening with her free air dash on a
        first decision) nearest the goal (the gap's centre; an owned route keeps its goal), scanned whole to the modelled
        ground for all owners with no exemption, MIDDLE_SCAN_N per batched pass in that order; the first clean one, or None."""
        from ssbot.knowledge import kinematics as K
        f=state["f"]
        if old is not None:
            kept=self._owned_route(state,game,sim,geo,plan,gap,old,"middle")
            if kept is not None:return kept
        goal_x=gap.seam if old is None else min(max(float(old["goal_x"]),gap.lo),gap.hi)
        dash=old is None and transfer.air_dash_free(sim)
        cands=transfer.middle_candidates(sim,gap,hb,goal_x,dash=dash)
        if not cands:
            self._note("transfer_follow_middle_unreachable",frame=f,lo=gap.lo,hi=gap.hi,goal_x=goal_x,owned=old is not None,
                       dash=dash,basis="no hold-and-release row lands inside the gap clear of both current bodies")
            return None
        firsts=[]
        for at in range(0,len(cands),transfer.MIDDLE_SCAN_N):
            top=cands[at:at+transfer.MIDDLE_SCAN_N]
            paths=[transfer.route_path(sim,c[2],c[5],c[6]) for c in top]
            scans=geo.scan_batch(paths)
            for rank,(c,p,sc) in enumerate(zip(top,paths,scans),start=at):
                b=p.box[-1]
                inside=bool(p.flags[-1]&K.F_GROUND and b[0]>=gap.lo+transfer.MIDDLE_PAD_U and b[2]<=gap.hi-transfer.MIDDLE_PAD_U)
                if not inside or not sc.complete or sc.contacts:
                    hit=None if not sc.contacts else sc.contacts[0]
                    firsts.append({"recipe":c[0],"release":int(c[1]),"inside":inside,"complete":sc.complete,
                                   "land_x":float(.5*(b[0]+b[2])),"first":None if hit is None else asdict(hit),
                                   "first_box":None if hit is None else [float(v) for v in p.box[hit.frame-p.origin]]})
                    continue
                recipe,r,commands,j,box,_,_=c
                follow={"kind":"middle","recipe":recipe,"dir":int(transfer.middle_direction(hb,goal_x)),"F0":f+2,
                        "masks":[int(m) for m in commands],
                        "release_F":f+2+int(r),"land_f":int(p.through),"goal_x":float(goal_x),"lo":gap.lo,"hi":gap.hi,
                        "other":int(gap.other),"landing_box":[float(v) for v in b],"rank":rank,"candidates":len(cands)}
                self._note("transfer_follow_middle",frame=f,owned=old is not None,dash_free=dash,
                           **{k:v for k,v in follow.items() if k!="masks"},rejected_before=firsts,
                           scope="whole route to the modelled ground, all owners, no exemption; landing inside the gap by MIDDLE_PAD_U")
                return "middle",follow,p,sc
        self._note("transfer_follow_middle_blocked",frame=f,lo=gap.lo,hi=gap.hi,goal_x=goal_x,owned=old is not None,
                   dash_free=dash,candidates=len(cands),scanned=firsts)
        return None

    def _side_landing_choice(self,state,game,sim,geo,plan,prefs,old):
        """Task 183: the existing ordinary left / right landing post types from the current state (the key held to the
        modelled ground), each scanned whole for all owners; the legal ones by the B2 endpoint value (an owned landing keeps
        its key), or None."""
        from ssbot.knowledge import kinematics as K
        f=state["f"];opts=[]
        if old is not None:
            kept=self._owned_route(state,game,sim,geo,plan,None,old,"land")
            if kept is not None:return kept
        kinds=(("left_landing",B["L"]),("right_landing",B["R"]))
        if old is not None:kinds=tuple(k for k in kinds if k[1]==int(old["dir"]))
        for kind,bit in kinds:
            row=transfer.landing_row(sim,bit)
            if row is not None:opts.append((kind,bit,row[0],model_path(sim,plan,row[0],game)))
        if not opts:
            self._note("transfer_follow_side_none",frame=f,owned=old is not None,reason="no modelled ground within the horizon")
            return None
        scans=geo.scan_batch([o[3] for o in opts])
        verdicts=[];legal=[]
        for (kind,bit,commands,p),sc in zip(opts,scans):
            ok=bool(sc.complete and not sc.contacts and p.flags[-1]&K.F_GROUND)
            value=self._endpoint(None,p,prefs) if ok else None
            hit=None if not sc.contacts else sc.contacts[0]
            verdicts.append({"kind":kind,"legal":ok,"complete":sc.complete,"value":value,"land_box":[float(v) for v in p.box[-1]],
                             "first":None if hit is None else asdict(hit),
                             "first_box":None if hit is None else [float(v) for v in p.box[hit.frame-p.origin]]})
            if ok:legal.append((value,kind,bit,commands,p,sc))
        self._note("transfer_follow_side",frame=f,owned=old is not None,verdicts=verdicts,
                   scope="ordinary left / right landing post types from the current state; whole route, all owners")
        if not legal:return None
        _,kind,bit,commands,p,sc=max(legal,key=lambda t:t[0])
        follow={"kind":kind,"dir":int(bit),"F0":f+2,"masks":[int(m) for m in commands],"release_F":f+2+len(commands),
                "land_f":int(p.through),"landing_box":[float(v) for v in p.box[-1]]}
        return "land",follow,p,sc

    def _follow_offer(self,state,game,sim,forecast,prefs,made,run,current):
        """Task 183 (Sol seq 261; the person: the chain's follow-up after a real bounce off one Clapper's slam prefers the
        middle). (handled, offer): handled False leaves the existing air / strike link (no clean middle landing now: the
        seam strike propose aims, seq 265; nothing safe on a first decision); an owned follow-up Run that cannot go on
        hands back through B2 recovery (failure responsibility kept)."""
        import time
        t0=time.perf_counter_ns()
        handled,offer=self._follow_decide(state,game,sim,forecast,prefs,made,run,current)
        self._note("transfer_follow_decision",frame=state["f"],handled=handled,
                   link=None if offer is None else offer.draft.run.link,mask=None if offer is None else int(offer.mask),
                   owned=None if run is None else run.link,elapsed_ms=(time.perf_counter_ns()-t0)/1e6,
                   timing_scope="follow-up decision only (rows, paths, scans)")
        return handled,offer

    def _follow_decide(self,state,game,sim,forecast,prefs,made,run,current):
        """Task 183. seq 265 (the person, via Sol: go to the middle whether or not there is room; with room stand there,
        without it down-slash and wait for room): the middle is the follow-up's goal. A clean middle landing whenever the gap
        is standable (an owned left / right landing re-chooses it, its whole route scanned as on a first choice). Otherwise,
        no standable gap or a standable one whose landing routes are blocked now, the seam action (_seam_follow) every tick
        until a middle landing is clean. The existing ordinary left / right landing (a standable gap) only when there is no
        seam action or its own gate turns it down, the reason recorded; an owned landing goes on as it was."""
        f=state["f"];draft,plan,_,_=made
        keep=None if run is None or run.link not in transfer.FOLLOW_LINKS else run.link
        old=None if keep is None else run.v.get("follow")
        gap=transfer.two_gap(state,plan.caster);hb=transfer._hero_box(state.get("hero"))
        stand=bool(gap is not None and hb is not None and transfer.standable(gap,hb))
        if keep is None and not stand:
            # no standable gap: the existing witnessed down-slash on the target's inner side; its own gates decide
            if gap is not None and hb is not None:self._note_seam(f,gap,hb,made,False,None)
            return False,None
        if keep=="middle" and not stand:
            self._note("transfer_follow_gap_closed",frame=f,link=keep,lo=None if gap is None else gap.lo,
                       hi=None if gap is None else gap.hi)
        try:
            geo=B2Geometry(forecast,f,plan.move,current[2])
            choice=None if not stand else self._middle_choice(state,game,sim,geo,plan,gap,hb,old if keep=="middle" else None)
            if choice is not None and keep=="land":
                self._note("transfer_follow_rechosen",frame=f,old_kind=(old or {}).get("kind"),new=choice[0],
                           basis="a clean middle landing from her current state; the whole route scanned as on a first choice")
            if choice is None and keep=="land":
                choice=self._side_landing_choice(state,game,sim,geo,plan,prefs,old)   # the owned landing goes on
            if choice is None and keep!="land":
                if self._seam_follow(state,game,sim,geo,plan,prefs,made,run,keep,gap,hb,stand):return False,None
                if stand:choice=self._side_landing_choice(state,game,sim,geo,plan,prefs,None)
        except (GeometryUnavailable,NominalUnsupported) as exc:
            self._note("transfer_follow_unchecked",frame=f,link=keep,reason=str(exc))
            if keep:
                self._recover("bounce follow-up route unchecked: "+str(exc),f);return True,None
            return False,None
        if choice is None:
            if keep:
                self._recover("bounce follow-up: no standable gap under the route" if keep=="middle" and not stand else
                              "bounce follow-up: no safe middle and no legal left / right landing",f);return True,None
            self._note("transfer_follow_none",frame=f,link=draft.run.link,owner="the existing air / strike link continues")
            return False,None
        return self._follow_install(state,game,sim,made,run,keep,choice)

    def _note_seam(self,f,gap,hb,made,stand,released):
        v=made[0].run.v;link=made[0].run.link;row=v.get("row") if link=="strike" else None
        self._note("transfer_follow_seam",frame=f,lo=gap.lo,hi=gap.hi,seam=gap.seam,side=int(v.get("side") or 0),
                   link=link,mask=int(made[3]),target_frame=f+2,inner=v.get("seam_inner"),
                   strike=None if not isinstance(row,dict) else {k:row.get(k) for k in ("contact_frame","contact_x","inner_bound","approach_direction")},
                   outer_rejected=v.get("seam_rejects"),hero_x=.5*(hb[0]+hb[2]),gap_standable=bool(stand),released=released,
                   middle="no clean middle landing route now" if stand else "no standable gap",
                   fallback=("the legal ordinary left / right landing if this action's own gate turns it down" if stand else
                             "the gate's own hand-back"),
                   basis="the middle is the follow-up's goal: the existing witnessed down-slash, its first contact on the target's "
                         "inner side (roots' order; bound read at the row's own contact index), every tick until a middle landing is clean")

    def _seam_follow(self,state,game,sim,geo,plan,prefs,made,run,keep,gap,hb,stand):
        """Task 183 seq 265: no clean middle landing now (a standable gap's landing routes blocked, or an owned middle route
        blocked / its gap closed): the follow-up stays on the middle by the existing seam approach or hold over the target's
        inner side and its witnessed inner down-slash (propose's seam rows; an owned middle route released to the air link).
        This tick's air / strike link gates it as before (current step for all owners, dash lock, strike witness). True: that
        action goes on (handled False); a standable gap then keeps the legal ordinary landing as the fallback when the gate
        turns it down (_seam_fallback). False: no seam action (no released link, not a close pair, the side unknown, or no
        strike witness possible on the target at all: _no_strike_witness)."""
        f=state["f"]
        if keep=="middle":
            made=transfer.propose(self.runner,state,game,sim,plan.iid,False,self._context[3],self._transfer_finished,
                                  self._transfer_goal,follow_release=True,
                                  **({"idle_evidence":self._idle_ev} if self._idle_ev else {}))
            if made is None or made[0] is None:
                self._note("transfer_follow_seam_unavailable",frame=f,link=keep,
                           reason=(made[1].ended_reason if made is not None else None) or "released seam approach has no link")
                return False
        seam=made[0].run.v.get("seam_inner")
        why=None
        if made[0].run.link not in ("air","strike") or not seam or int(seam[1])==0:
            wide=gap is not None and hb is not None and not transfer.close_pair(gap,hb)
            why=("the draft is not an air / strike link" if made[0].run.link not in ("air","strike") else
                 "not a close pair: the gap is %.2f u wide"%gap.width if wide else
                 "the target's inner side unknown" if seam else "no seam geometry")
        else:
            # a witnessed inner down-slash is the point: a target no strike witness is possible on (Task 179 #317's
            # definite ends: no fitted still pose, a walker outside WalkSupport, an Idle past its Idle Time or hit since
            # its entry) is not approached (0ed5c779 w13_331 3725: the recorded 476 in Evade Scuttle toward her)
            target=next((e for e in transfer.clappers(state) if e["iid"]==plan.iid),None)
            gone=self._no_strike_witness(state,sim,plan.iid,target)
            if gone is not None:why="no strike witness possible: "+gone
        if why is not None:
            self._note("transfer_follow_seam_unavailable",frame=f,link=keep,draft_link=made[0].run.link,inner=seam,reason=why)
            return False
        if stand:
            self._follow_fallback={"f":f,"state":state,"game":game,"sim":sim,"made":made,"run":run,
                                   "side":lambda:self._side_landing_choice(state,game,sim,geo,plan,prefs,None)}
        if keep=="middle":self._follow_made=made
        self._note_seam(f,gap,hb,made,stand,keep)
        return True

    def _seam_fallback(self,f,why):
        """Task 183 seq 265: this tick's seam action turned down by its own gate (why: the external step blocked or
        unchecked, its air dash refused). With a standable gap the existing legal ordinary left / right landing goes instead
        (scanned whole now), the reason recorded; None: the gate's own hand-back stands (no standable gap, or no legal
        landing)."""
        fb=self._follow_fallback;self._follow_fallback=None
        if fb is None or fb["f"]!=f:return None
        try:choice=fb["side"]()
        except (GeometryUnavailable,NominalUnsupported) as exc:
            self._note("transfer_follow_unchecked",frame=f,link=None,reason=str(exc));choice=None
        self._note("transfer_follow_seam_blocked",frame=f,reason=why,fallback=None if choice is None else choice[1].get("kind"),
                   owner="the legal ordinary landing" if choice is not None else "the gate's own hand-back")
        if choice is None:return None
        return self._follow_install(fb["state"],fb["game"],fb["sim"],fb["made"],fb["run"],None,choice)[1]

    def _follow_install(self,state,game,sim,made,run,keep,choice):
        """Task 183: the chosen follow-up link (middle / land) with its checked row as this tick's offer. (handled, offer)."""
        f=state["f"];link,follow,route,scan=choice
        made2=transfer.follow_draft(self.runner,made,state,game,sim,link,follow,self._idle_ev or None)
        if made2 is None:
            if keep:
                self._recover("bounce follow-up link ended",f);return True,None
            return False,None
        draft2,plan2,path2,mask2=made2
        goal=self._transfer_goal
        self._transfer_responsibility.setdefault(plan2.move,(goal.responsibility,goal.cast_ta))
        return True,B2Offer("active" if run is not None else "manual_commitment",path2,draft2,int(mask2),0.,plan2.move,
            {"manual_air":True,"rune_transfer":True,"caster":plan2.caster,"cast_fa":plan2.cast_fa,
             "follow":{k:v for k,v in follow.items() if k!="masks"},"follow_masks":follow.get("masks"),
             "follow_route_through":follow.get("land_f"),"follow_route_contacts":len(scan.contacts),
             "tail_checked_through":draft2.run.v.get("source_tail_checked_through"),
             "tail_mask":draft2.run.v.get("source_tail_mask"),"approach_only":False,
             "checked_through":scan.last_frame,"phase":link,"predicted_bounce":None,
             "handoff":("actual landing between the two near body edges" if link=="middle" else "actual landing"),
             "safety_basis":("whole route to the modelled ground when chosen, then its next %d frames every tick; all owners, "
                             "no exemption")%transfer.FOLLOW_SCAN_F})

    def _transfer_bounce_exit(self):
        """Reuse the existing over/fall/ground table only after the REAL B2 bounce."""
        run=self.runner.run;context=self.post_context;move=context["move"]
        self._note("rune_transfer_real_bounce_exit",frame=self.dispatch.frame,move=vars(move),hit=self._hit,press=self._press)
        if not self.vault_enabled:
            self.post_context=self._post_seed=self._post_kind=None
            self._abandon("rune transfer real hit+bounce handback");return
        from .knife_chain_vault_native import AirVaultAnchor
        from .knife_chain_vault import CHAIN
        direction=1 if run.v["side"]==B["R"] else -1
        v=dict(self.runner.chains[CHAIN].vars)
        v.update(iid=move.target_iid,over_dir=direction,ta=run.v["ta"],F_open=move.antic_frame+2,
            f_open=move.antic_frame,hp0=self._actual_state["hero"]["health"],req={"nogo":[]},
            bounced=True,bounce_f=context["bounce"],down_hit_f=self._hit,side_hits=[],
            _native_vault={"move":vars(move),"buddy":run.v["caster"],"entry_kind":"rune_stomp"})
        self.runner.anchor=AirVaultAnchor(self.runner.chains);self.runner.run=Run(CHAIN,"over",v)
        self.post_context=self._post_seed=self._post_kind=None

    def install(self,offer,planner,ordinary=None):
        if offer.details.get("rune_transfer"):
            from .knife_chain_score_bound import clear_ordinary_action_memo
            clear_ordinary_action_memo(planner)
        return super().install(offer,planner,ordinary)

    def sent(self):
        selected=self._b2_selected;sent=super().sent()
        from .knife_chain_wall_native import sent as wall_sent
        wall_sent(self,selected,sent)
        if getattr(self,"_bounce",None) is not None:
            from . import knife_chain_bounce_table as bounce_table
            bounce_table.after_send(self,selected,sent)
        if selected is not None and sent.chain_outcome=="sent" and selected.details.get("distance_vault"):
            if selected.stage=="manual_commitment" or selected.details.get("approach_entry"):
                from .knife_chain_vault_native import manual_jump_watch
                self._jump_start=manual_jump_watch(selected,sent.frame)
                if self._jump_start is not None:self._jump_start.record_send(sent.target_frame,sent.desired_mask)
                # Task 179: the approach's own commitment send armed nothing; its near / hop-hook entry arms here.
                if selected.details.get("approach_entry"):self._arm_hook_start(selected,sent)
            run=self.runner.run
            if run is not None and run.v.get("fallback_hook") and not run.v.get("near_miss_recorded"):
                origin=self.commitment["origin"]
                exposure=self._failure_exposure(selected.move,origin,sent.frame,self.commitment.get("ta"))
                if self._actual_state is not None:exposure.observe(self._actual_state,game_time=self._clock)
                self._failure_exposures.append(exposure)
                run.v["near_miss_recorded"]=True
                self._press=self._accepted=self._hit=None
                self._arm_hook_start(selected,sent)
                self._note("vault_miss_to_hook_sent",frame=sent.frame,move=vars(selected.move),
                           missed_press=run.v.get("near_miss_press"),exposure=exposure.as_dict(),
                           scope="one in-air branch in the same Run; first miss responsibility retained")
        if selected is not None and sent.chain_outcome=="sent" and selected.details.get("rune_transfer"):
            self._transfer_finished.add((selected.details["caster"],selected.details["cast_fa"]))
            if self.commitment is not None and selected.details.get("target_ta") is not None:
                self.commitment["ta"]=selected.details["target_ta"]
            if selected.details.get("target_move") is not None:
                self._transfer_target_moves[selected.move]=(transfer.MoveInstance(**selected.details["target_move"]),selected.details["target_ta"])
            if sent.desired_mask&B["J"]:
                from .knife_chain_jump import JumpStartWatch
                if self._jump_start is None:self._jump_start=JumpStartWatch(selected.move,sent.frame,(sent.target_frame,))
                self._jump_start.record_send(sent.target_frame,sent.desired_mask)
            run=self.runner.run;cs=None if run is None else run.v.get("cs");watch=self._hook_start
            if (cs is not None and run.chain==transfer.PROGRAM and run.link in transfer.HOOK_LINKS
                    and self.commitment is not None and self.commitment["move"]==selected.move
                    and (watch is None or watch["move"]!=selected.move)):
                # Face hook: arm the existing same-Move hook watch on the first SUCCESSFUL send of the absolute plan;
                # never from a draft, never re-armed per tick. B2's own sent() then records the CLAW sends ("active")
                # and keeps the late-slot veto, the missed-window / no-Harpoon recovery and _failed_hook_moves.
                self._hook_start={"move":selected.move,"origin":sent.frame,"targets":(cs.f_press,cs.f_press+1),
                                  "sent_targets":set(),"seen_frame":None}
                self._note("b2_hook_start_expected",frame=sent.frame,move=vars(selected.move),
                           targets=[cs.f_press,cs.f_press+1],source="transfer aimed face hook; absolute CsPlan; no certificate")
        return sent

    def _observe_idle_evidence(self,state):
        """Task 179 #317/#318 (Sol seq 240 甲, seq 241 P2): causal evidence per Clapper Idle instance. map2.clapper
        reads Idle Time at the Idle ENTRY (idle_buddy: the buddy alive then -> IDLE_K[True]). An instance is bound only
        by an explicit Control -> Idle FSM event of this frame (its real entry frame; every such event rebinds, whatever
        the clocks: the oracle's Control time is scaled and may stop, so no entry is rebuilt from it). buddy, from this
        frame's STATE: another Clapper alive at the end of the entry frame was alive at the entry (True); none alive now
        and none alive on the previous observed frame: False; one alive on the previous frame and not now (it died on
        this frame, order unknown) or no previous observed frame: None. An Idle shown without its entry event and every
        record across an observation gap (the same instance cannot be confirmed) are unknown (None: the no-buddy 39).
        hit: a hit event on her in a frame after the instance's entry frame revokes it (a real hit on an Idle provokes
        Dmg Attack in the hit frame, so an Idle still shown after it has no valid witness); a hit in the frame whose
        events end in a new Idle belongs to the old instance (the new one is not revoked). Leaving Idle drops it."""
        f=state["f"];es=transfer.clappers(state)
        alive={e["iid"] for e in es if (e.get("hp") or 0)>0 and not e.get("is_dead")}
        gap=self._alive_prev_f is not None and self._alive_prev_f!=f-1
        prev=None if gap or self._alive_prev_f is None else self._alive_prev
        if gap:
            for rec in self._idle_ev.values():rec["buddy"]=None

        def buddy(iid):
            if any(o!=iid for o in alive):return True
            if prev is None or any(o!=iid for o in prev):return None
            return False

        evs=state.get("ev") or ()
        for ev in evs:
            d=ev.get("d") or {};iid=d.get("iid") if d.get("iid") is not None else d.get("ent")
            if ev.get("k")!="fsm" or d.get("fsm")!="Control" or d.get("to")!="Idle" or type(iid) is not int:continue
            same=ev.get("f",f)==f
            self._idle_ev[iid]={"entry":f if same else None,"buddy":buddy(iid) if same else None,"hit":None}
        for ev in evs:
            if ev.get("k")!="hit":continue
            rec=self._idle_ev.get((ev.get("d") or {}).get("ent"))
            if rec is not None and rec["hit"] is None and (rec["entry"] is None or rec["entry"]<f):rec["hit"]=f
        shown={e["iid"] for e in es if transfer.control(e)[0]=="Idle"}
        for iid in shown:self._idle_ev.setdefault(iid,{"entry":None,"buddy":None,"hit":None})
        for iid in [k for k in self._idle_ev if k not in shown]:del self._idle_ev[iid]
        self._alive_prev,self._alive_prev_f=alive,f

    def observe(self,state):
        if getattr(self,"_bounce_mode",False):
            from . import knife_chain_bounce_table as bounce_table
            bounce_table.observe_frame(self,state)
        super().observe(state)
        self._observe_idle_evidence(state)
        if getattr(self,"_bounce",None) is not None:
            from . import knife_chain_bounce_table as bounce_table
            bounce_table.observe_identity(self,state)
        # Face hook: a transfer hook's Harpoon hit / control are EVIDENCE in the same Run only. The B2 hook-bounce
        # handover stays VAULT_IDLE-only, so no _hit / _accepted / post_context / bounced comes from a hook.
        run=self.runner.run;watch=self._hook_start;c=self.commitment
        if (run is None or run.chain!=transfer.PROGRAM or run.link not in transfer.HOOK_LINKS or watch is None
                or watch["seen_frame"] is None or c is None or watch["move"]!=c["move"]):return
        f=state["f"];v=run.v
        v.setdefault("hook_seen_f",watch["seen_frame"])
        for ev in state.get("ev") or ():
            d=ev.get("d") or {}
            if ev.get("k")!="hit" or str(d.get("src") or "") not in ("Harpoon Damager","Harpoon Dash Damager"):continue
            ent=d.get("ent") if d.get("ent") is not None else d.get("iid");ef=ev.get("f",f)
            if type(ef) is not int or not watch["seen_frame"]<=ef<=f:continue
            if ent==c["move"].target_iid:v.setdefault("hook_hit_f",ef)
            else:v.setdefault("hook_other_f",[ef,ent])
        h=state.get("hero") or {}
        if ("hook_ctrl_f" not in v and h.get("hero_accepting_input") is True
                and "harpoon" not in str((h.get("anim") or {}).get("clip","")).lower()):v["hook_ctrl_f"]=f

    def before_send(self,*,frame,target,mask,flags,received_frame,dispatch_clock=None):
        selected=self._b2_selected
        if selected is not None and selected.details.get("bounce_table") and int(mask)==selected.mask:
            from . import knife_chain_bounce_table as bounce_table
            veto=bounce_table.before_send(self,selected,frame=frame,target=target,mask=mask,flags=flags,
                                          received_frame=received_frame)
            if veto is not None:return veto
        if (selected is not None and selected.details.get("rune_transfer") and int(mask)&B["J"]
                and self._jump_start is None):
            from .knife_chain_deadline import first_jump_clock
            reason="rune transfer first-J target already received" if type(received_frame) is int and received_frame>=target else None
            if self.require_send_clock:
                try:clock=first_jump_clock(dispatch_clock,target)
                except ValueError as exc:self._stop("missing critical rune-transfer first-J clock: "+str(exc),frame)
                self._note("b2_jump_dispatch_clock",frame=frame,target=target,**clock)
                if clock["late"]:reason="rune transfer first-J calibrated deadline elapsed"
            if reason is not None:
                return self._abort_hook_dispatch(selected,frame=frame,target=target,mask=mask,flags=flags,
                    received_frame=received_frame,event="b2_jump_send_veto",reason=reason)
        if selected is not None and (selected.details.get("vault_near") or selected.details.get("distance_vault")):
            from .knife_chain_vault_native import before_send as vault_before_send
            veto=vault_before_send(self,selected,frame=frame,target=target,mask=mask,flags=flags,
                                  received_frame=received_frame,dispatch_clock=dispatch_clock)
            if veto is not None:return veto
        if (selected is not None and selected.details.get("manual_air") and int(mask)&B["A"]
                and self._press is None and type(received_frame) is int and received_frame>=target):
            self._air_finished.add(selected.move)
            return self._abort_hook_dispatch(selected,frame=frame,target=target,mask=mask,flags=flags,
                received_frame=received_frame,event="air_strike_send_veto",reason="manual air attack slot already observed")
        return super().before_send(frame=frame,target=target,mask=mask,flags=flags,
                                  received_frame=received_frame,dispatch_clock=dispatch_clock)

    def _abort_hook_dispatch(self,selected,**kwargs):
        if selected is not None and selected.details.get("rune_transfer"):
            # Per-cast no-retry bookkeeping, not credit for a sent jump. The
            # existing base still creates preparation exposure only after the
            # neutral replacement is actually sent.
            self._transfer_finished.add((selected.details["caster"],selected.details["cast_fa"]))
        return super()._abort_hook_dispatch(selected,**kwargs)

    def _recover(self,reason,frame):
        if getattr(self,"_bounce",None) is not None:
            from . import knife_chain_bounce_table as bounce_table
            bounce_table.end(self,"recovered",reason)
        source=self.commitment
        run=self.runner.run
        hooked=bool(run is not None and run.chain==transfer.PROGRAM and run.v.get("cs") is not None
                    and type(run.v.get("hook_hit_f")) is int)
        if source is not None and source["move"].family=="RUNE_TRANSFER" and (self._press is not None or hooked):
            bound=self._transfer_target_moves.get(source["move"])
            if bound is None and hooked and self._actual_state is not None:
                # The hook ticks bind nothing (their step branch runs first); the attack the needle provoked is the
                # target's observed current move (live: Slam Antic from 2654 when the release aborts at 2673).
                bound=next((m for fam in ("CC_SLAM","CC_JUMP_CAST","CC_JUMP")
                            for m in (self._observed_transfer_move(self._actual_state,run.v.get("iid"),fam),)
                            if m is not None),None)
            if bound is not None:
                # A successful sent strike, or this Run's own Harpoon hit that
                # provoked it (live 2654 -> Slam 1 at 2709), explicitly continued
                # against this observed destination attack. Keep its liability
                # alongside the source, but do not ban a fresh counter to it.
                target,ta=bound
                origin=max(source.get("responsibility_origin",source["origin"]),target.antic_frame)
                exposure=super()._failure_exposure(target,origin,frame,ta)
                if self._actual_state is not None:exposure.observe(self._actual_state,game_time=self._clock)
                self._failure_exposures.append(exposure)
                self._note("b2_failure_exposure",frame=frame,exposure=exposure.as_dict(),
                           source="sent rune-transfer strike against bound destination attack")
        ctx=getattr(self,"_wall_pressure",None)
        # A different action's recovery cannot end the old hammer's liability.
        # Retain only bookkeeping, never revive its Run or candidate permission.
        if ctx is None or not (ctx.get("landing") or ctx.get("yielded")):
            self._wall_pressure=None
        return super()._recover(reason,frame)

    def summary(self):
        return {**super().summary(),"mode":"manual_air_probe","table":"manual_air+vault_near" if self.vault_enabled else "air_strike","tables":list(self.runner.chains),
                "online_search":False,"geometry_scope":("vault: current external step only, empirical skill; other air: contact path and N=2" if self.vault_enabled else "current/contact path plus existing N=2 continuations"),
                "post_bounce":"observed hammer-off hands to current tactical target; declined bounce-tail admission hands to ordinary planner"}
