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
# Task 182 seq 312 #386 (Sol REVIEW385 2): the L2 entries of the shared seam strike (SeparatedSlam's way back after the slam: "seam_slam";
# MiddleReturn's: "seam_back"; 2.3's rune end keeps "rune_end"): one SWITCH stomp each, bound to its action (event_f) like the rune end, its
# strike bounded to the seam (GoalPrefs.strike_bound kind "seam"), the source move's family its HP responsibility
SEAM_SCOPES=frozenset({"seam_slam","seam_back"})
EXPOSURE_FAMILIES=frozenset({"CC_SLAM","CC_JUMP_CAST","CC_JUMP","CC_CAST"})   # knife_chain_failure's observed move families


def _plan_source_in_air(state,caster):
    from .tactics import clapper_plans
    if not clapper_plans.ENABLED:return False
    source=next((e for e in transfer.clappers(state) if e["iid"]==caster),None)
    return source is not None and transfer.control(source)[0] in ("Jump","Air")


def _sep312(frame):
    """Task 182 seq 312's chain changes act on this frame (clapper_separated.active: SSBOT_FORUM_SEP312 and its offline A/B start)."""
    from .tactics import clapper_separated as SEP
    return SEP.active(frame)


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
        self._opening_noted=None   # #387: the last recorded opening hook check (transfer_opening_check on change only)
        self._wall_pressure=None
        self._entry_attack_seen=None
        self._entry_attack_goal=None
        self.refused_strike=None   # Sol seq 272 B / 274: (frame, target, kind, source): the entry's strike a gate's contact refused
        self._return_admission_noted=None
        self._idle_ev={};self._alive_prev=None;self._alive_prev_f=None
        self._transfer_responsibility={}
        self._transfer_target_moves={}
        self._hold_seen=False   # Task 182 seq 312 #384: the last _hold_over reading (its notes only)
        self._held_goal=None    # Task 182 seq 312 #385: the BOUNCE goal L2's 1.2.2 hold named (its follow-up air-only, no new strike)
        self._seam_families={}  # Task 182 seq 312 #386: (source, event_f) of a bound seam entry -> its source move's family
        self._vault_ready=False
        self._vault_responsibility={}
        self._vault_origins={};self._vault_completed=set()
        self._bounce=None;self._bounce_frames={}
        self._waypoint_wanted=False;self._waypoint_failed=set();self._waypoint_declined=None;self._waypoint_responsibility={}
        self._vault_tried={}   # Task 182 seq 312 #385: per waypoint key, the start states ("air" / "ground") a vault row was searched from
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

    def key_commitment(self,state,ground=None):
        """Task 182 (Sol seq 255 A): what this owner holds of her keys past the in-flight prefix. None: nothing a plan must wait for
        (no Run; an approach-only or waypoint Run hands back at its next step when L2 moves on). Else (owner, release known, keys
        from the first free mask frame on); the source tail's release and keys are its own admission's; an owned bounce
        follow-up route's (seq 269 / 270) are its own (_follow_commitment; ground: the policy's ground flag of this STATE, the
        one the chain's tick gets); any other committed Run, recovery or hook: unknown."""
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
        fo=run.v.get("follow") if run.chain==transfer.PROGRAM and run.link in transfer.FOLLOW_LINKS else None
        if isinstance(fo,dict) and type(f) is int and isinstance(fo.get("F0"),(int,np.integer)) and isinstance(fo.get("land_f"),(int,np.integer)):
            return self._follow_commitment(state,run,fo,f,ground)
        return run.lid,False,()

    def _follow_commitment(self,state,run,fo,f,ground):
        """Task 182 seq 269 / 270: an owned middle / landing route (Task 183) is released on the tick the chain observes her actual
        landing (_follow_landed), so it sends keys through the frame after it. On the ground now with a landing that route
        accepts: released this tick, nothing past the in-flight prefix. In the air with its modelled landing past that prefix:
        the checked row transfer_follow_keys sends (masks[F - F0]) through land_f, then the key the last re-anchor
        (_owned_route) sends for land_f + 1 (the landing's own: none for the middle, its direction for a landing). A landing
        already due inside the prefix or past while she is still in the air, or a landing it does not accept (recovery
        follows): not confirmed, unknown (Sol seq 270: never a free hero on a stale prediction)."""
        if ground:return (run.lid,True,()) if self._follow_landing_inside(state,run)[0] else (run.lid,False,())
        land=int(fo["land_f"])
        if land<f+2:return run.lid,False,()
        masks=fo.get("masks") or ();F0=int(fo["F0"]);tail=0 if run.link=="middle" else int(fo.get("dir") or 0)
        return run.lid,True,tuple(int(masks[F-F0]) if 0<=F-F0<len(masks) else tail for F in range(f+2,land+2))

    @staticmethod
    def _follow_landing_inside(state,run):
        """Task 183: a follow-up landing the Run accepts (_follow_landed): any ground for a left / right landing, the middle only
        with her box between the two near body edges. (accepted, her box, the gap)."""
        hb=transfer._hero_box(state.get("hero"));gap=transfer.two_gap(state,run.v.get("caster"))
        return bool(run.link=="land" or (gap is not None and hb is not None and gap.lo<hb[0] and hb[2]<gap.hi)),hb,gap

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
        scope=getattr(entry,"scope",None)
        event_fam="RUNE_END" if scope=="rune_end" else "SEAM" if scope in SEAM_SCOPES else None
        if goal is not None and (goal.target,goal.caster)==(entry.target,entry.source):
            # Task 182 seq 312 #385 (C18 sy18_23x 136227): a rune_end entry is bound only to its own rune end: another goal on the same pair
            # (a spent bounce on the target that cast the rune) is no binding of it; #386: a seam entry only to its own action
            rm=getattr(goal,"responsibility",None)
            if (event_fam is None
                    or (goal.source_kind=="SWITCH" and getattr(rm,"family",None)==event_fam
                        and getattr(rm,"antic_frame",None)==getattr(entry,"event_f",None))):return
        if entry==self._entry_attack_seen:return
        if event_fam is not None:
            # Task 182 seq 312 (#384, Sol REVIEW383): 2.3's one closing strike after the small rune: no source move goes on, so the rune's end
            # is the instance (its frame), the failure responsibility that event's; one goal per rune end (its own (caster, frame) key).
            # #386 (Sol REVIEW385 2): the shared seam strike's L2 entries the same way, the action's first frame their instance (the
            # waypoint's convention: no backdated antic), the source move's family their responsibility (_failure_exposure)
            fa=getattr(entry,"event_f",None)
            if type(fa) is not int or not self._clock_known or not np.isfinite(self._clock):return
            if entry.source not in {e["iid"] for e in transfer.clappers(state)}:return
            if event_fam=="SEAM":self._seam_families[(int(entry.source),int(fa))]=str(entry.source_family)
            observed=(transfer.MoveInstance(entry.source,int(fa),event_fam),float(self._clock))
        else:
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
        # Task 182 seq 289 (the person: the blade after a dodge must connect; live #40 123959): L2's over_stay keeps its own target's down
        # slash (stay_pogo): the chain's stomp on it is that down slash, for a BOUNCE goal while its Idle is fresh (entered on the bounce
        # itself, the buddy attacking, no hit since: the evidence its strike witness needs)
        stay=frozenset(getattr(prefs,"stay_pogo",()))
        ev=self._idle_ev.get(goal.target)
        if goal.source_kind!="BOUNCE" or not (isinstance(ev,dict) and ev.get("hit") is None and ev.get("buddy") is True):stay=frozenset()
        # Task 182 seq 312 #385 (the person's 1.2.2): after its down slash N is no target (L2's no_hit) but the bounce's own follow-up still
        # holds her off the middle in the air (GoalPrefs.hold_over): it runs with no new strike (_transfer_offer's no_strike), ends on her
        # landing; a held goal never starts from the ground
        held=frozenset()
        if goal.source_kind=="BOUNCE" and _sep312(state.get("f")) and goal.target in frozenset(getattr(prefs,"hold_over",()) or ()):
            self._held_goal=goal
        if goal is self._held_goal and goal.source_kind=="BOUNCE":
            up=len(hb)==4 and type(hb[1]) in (int,float) and np.isfinite(hb[1]) and hb[1]>3.2
            if not up and not active:
                self._note("transfer_hold_goal_dropped",frame=state["f"],target=goal.target,reason="on the ground with no follow-up running")
                self._transfer_goal=None;self._held_goal=None;self._transfer_ready=False
                return prefs
            if up:held=frozenset({goal.target})
        if (side and not side_approach and not transfer.bounce_tail_pending(state,goal,self._clock)) or goal.target in frozenset(getattr(prefs,"no_hit",()))-stay-held:
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
        if move.family=="RUNE_END":
            # Task 182 seq 312 (#384): 2.3's closing strike answers the small rune cast whose end it follows: that cast (the same caster,
            # the rune end's frame) is its HP responsibility; observed outside its cast states, it keeps the 30-frame minimum
            move=transfer.MoveInstance(move.target_iid,move.antic_frame,"CC_CAST")
        if move.family=="SEAM":
            # Task 182 seq 312 #386: a seam entry's strike answers for its source move (the slam before the way back, the move whose end made
            # the return due) from the action's first frame; observed outside that family's states it keeps the 30-frame minimum
            fam=self._seam_families.get((move.target_iid,move.antic_frame))
            move=transfer.MoveInstance(move.target_iid,move.antic_frame,fam if fam in EXPOSURE_FAMILIES else "CC_CAST")
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
            return self._waypoint_offer(tick[1],tick[2],sim,forecast,prefs,ground=bool(tick[3]))
        if getattr(prefs,"press_walker",None) is not None and self.runner.run is None and self.commitment is None and self.post_context is None:
            return None  # Task 182 seq 311: the press stage asks no new strike or approach of the chain (keys already committed run on above)
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
            if self._context is None:return None
            vault=propose_vault(self,planner,forecast,prefs)
            # Task 182 seq 289 (the person: after a real bounce the next down slash, not the umbrella; live #40 123959 - 124000): the vault starts
            # only on the ground, so with the other Clapper in the air it took every airborne tick: with no vault action now a BOUNCE goal's own
            # strike goes on below, as the SWITCH stomp does above
            # (#387: with no vault action the small rune's opening goes on below too)
            opening=self._opening(prefs,f)
            if (vault is not None or self.recovery is not None or self.runner.run is not None or not (self._transfer_ready or opening)
                    or (getattr(self._transfer_goal,"source_kind",None)!="BOUNCE" and not opening)):return vault
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
        # #387 (Sol seq 335): the small rune's opening is the transfer Run's high hook: no manual air down slash before it
        if self._air_context is None or self._opening(prefs,f):return self._transfer_offer(state,game,sim,forecast,prefs,ground)
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

    def _waypoint_offer(self,state,game,sim,forecast,prefs,ground=None):
        """Task 182 (SSBOT_FORUM_TWO_PLAN; knife_chain_waypoint): one bounded floor approach of the running plan phase. L2 names
        the place and the frame each tick; withdrawing them or reaching the place hands back at this step, the keys already
        sent staying the next owner's actual prefix. A step blocked or a place no longer reachable in time hands back through
        recovery, which keeps its failure responsibility; a fresh start only ever declines.
        Task 182 seq 312 #385 (kind "vault", Sol REVIEW384 1-2): over one body to one place: its row chosen once
        (knife_chain_waypoint.vault_row) with the whole route scanned for all owners, then followed as an absolute row with its next
        transfer.FOLLOW_SCAN_F frames scanned every tick; the actual landing past its takeoff hands back. A start declined in the air is
        tried again once on the ground (no per-tick search)."""
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
        if goal.kind=="vault" or (active and run.v.get("kind")=="vault"):
            return self._vault_offer(state,game,sim,forecast,goal,active,key,back,ground)
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
        refused=False
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
                    refused=True
                else:self._note("waypoint_dash_checked",frame=f,**info)
            scan=geo.scan(path)
        except GeometryUnavailable as exc:
            return failed("geometry unavailable: "+str(exc))
        if not scan.complete or scan.contacts:
            return failed("external step blocked",first=None if not scan.contacts else asdict(scan.contacts[0]))
        ahead=self._waypoint_delayed_ahead(sim,plan,goal,f,game,geo,mask,active,refused)
        if ahead is not None:
            return failed("route meets a delayed hazard",first=asdict(ahead))
        if active:
            draft=logical_copy(self.runner);draft.run.v.update(x=float(goal.x),by_f=int(goal.by_f),what=what)
        else:
            draft=self.runner.fork_empty(AirAnchor())
            draft.run=Run(waypoint.PROGRAM,"go",{"iid":goal.source,"ta":float(game),"plan":list(goal.plan),"x":float(goal.x),
                                                 "by_f":int(goal.by_f),"kind":goal.kind,"f_open":f,"move":asdict(move),"what":what})
        return B2Offer("active" if active else "manual_commitment",path,draft,int(mask),0.,move,
            {"manual_air":True,"waypoint":True,"kind":goal.kind,"x":float(goal.x),"by_f":int(goal.by_f),"what":what,
             "phase":"go","predicted_bounce":None,"checked_through":path.through,
             "safety_basis":("bounded approach: the dash through its lock, every step through all owners"
                             +("; no route certificate" if goal.over is not None else
                               ", the route from the key sent through the delayed hazard layers; no route certificate for bodies "
                               "or moves"))})

    VAULT_TAIL_F=16   # Task 182 seq 312 #385: no-key frames past a vault row's keys, so a landing later than first modelled is still read
    VAULT_SCENE_U=2.  # ... a vault search's scene: the Clappers' roots to this many u
    VAULT_SEARCHES=6  # ... at most this many searches for one place (its waypoint key)

    def _vault_offer(self,state,game,sim,forecast,goal,active,key,back,ground):
        """Task 182 seq 312 #385 (Sol REVIEW384 1-2; the person's 1.2.2: over N into the middle once both hammer stages of F's slam are
        over): a waypoint of kind "vault", over goal.over to goal.land. Its rows (knife_chain_waypoint.vault_row: one jump from the floor,
        the key toward the place, the free air dash at a few fixed frames, the key released on a grid past the body; finite; the best and
        up to VAULT_ALTS next ones, one per landing place) are searched once per start state and scene (in the air / on the floor, the two
        Clappers' states: a later search only on such an event, no per-tick search); the first in their order with the model's landing
        inside the band and the whole route to it scanned clean for all owners is taken. Owned, it is followed as an absolute row re-anchored at each
        tick's first free mask frame through the modelled landing (the keys sent are the keys checked): the landing still inside the band
        and the next transfer.FOLLOW_SCAN_F frames clean (through the landing on a tick that presses a new dash: its whole motion), else
        recovery with its failure responsibility. Her box past the body in the air hands back (the ordinary owners take the fall: L2's air
        side slash or the shared seam strike), as does the actual landing past its takeoff (outside the band: through recovery); either is
        the key's last vault (no restart)."""
        from types import SimpleNamespace
        f=state["f"];run=self.runner.run
        lo,hi=goal.land if goal.land is not None else (float(goal.x)-goal.tol,float(goal.x)+goal.tol)
        lo,hi=float(lo),float(hi)
        def declined(reason,**data):
            # (every vault decline noted: its searches are event-limited, so no dedupe hides a later search's reasons)
            self._note("waypoint_rejected",frame=f,reason=reason,active=active,x=goal.x,by_f=goal.by_f,kind="vault",**data)
            self._waypoint_declined=(key,reason)
            if active:
                self._waypoint_failed.add(key)
                self._recover("waypoint vault "+reason,f)
            return None
        if goal.over is None:return declined("no body to pass")
        if active:
            v=dict(run.v.get("vault") or {})
            if not v:return declined("vault row missing")
            hb=(state.get("hero") or {}).get("box") or ()
            if not ground and len(hb)==4 and all(type(z) in (int,float) for z in hb):
                # past the body in the air: the way over it is done; the ordinary owners take her fall (L2's place: the air side slash, the
                # shared seam strike), the keys already sent their prefix
                d=int(v.get("dir") or 0)
                if ((d>0 and float(hb[0])>=float(goal.over[2])+waypoint.VAULT_PAD)
                        or (d<0 and float(hb[2])<=float(goal.over[0])-waypoint.VAULT_PAD)):
                    self._note("waypoint_vault_past",frame=f,box=[float(z) for z in hb],over=[float(z) for z in goal.over],
                               planned_land_f=v.get("land_f"))
                    self._vault_tried.setdefault(key,set()).add("done")
                    return back("waypoint vault past the body","waypoint_arrived")
            if not ground:v["air_seen"]=True
            elif v.get("air_seen"):
                hp=(state.get("hero") or {}).get("pos") or ()
                cx=float(hp[0]) if len(hp)>=1 and type(hp[0]) in (int,float) else None
                inside=cx is not None and lo<=cx<=hi
                if goal.end=="past":
                    # #386: an air hand-back route has no landing band: landed with her box past the body is its end (the hand-back's tick
                    # missed), short of it a failure
                    d=int(v.get("dir") or 0)
                    inside=bool(len(hb)==4 and all(type(z) in (int,float) for z in hb)
                                and ((d>0 and float(hb[0])>=float(goal.over[2])) or (d<0 and float(hb[2])<=float(goal.over[0]))))
                self._note("waypoint_vault_landed",frame=f,x=cx,lo=lo,hi=hi,inside=inside,planned_land_f=v.get("land_f"))
                if not inside:
                    self._waypoint_failed.add(key)
                    self._recover("waypoint vault landed outside its band",f);return None
                self._vault_tried.setdefault(key,set()).add("done")
                return back("waypoint vault landed past the body","waypoint_arrived")
            rows=[np.asarray(v.get("masks") or (),np.int64)[max(0,f+2-int(v["F0"])):]]
        else:
            start="ground" if ground else "air"
            # searched once per start state and scene (the two Clappers' states and roots to VAULT_SCENE_U): a later search only on such an
            # event, at most VAULT_SEARCHES per place, never per tick (C17 sy17_122: the slammer Idle again after an evade that took it 5 u
            # off the middle was the same scene by states; C19 tm19_122: 9 searches at 1 u in 40 frames of its evade)
            tag=(start,tuple(sorted((int(e["iid"]),str(transfer.control(e)[0]),
                                     int(round(float((e.get("pos") or (0.,))[0])/self.VAULT_SCENE_U))) for e in transfer.clappers(state))))
            tried=self._vault_tried.setdefault(key,set())
            if tag in tried or "done" in tried or len(tried)>=self.VAULT_SEARCHES:return None
            tried.add(tag)
            vr=waypoint.vault_row(sim,goal,f)
            if vr is None:return declined("no vault row from here",start=start,scene=list(tag[1]))
            cands=[vr]+list(vr.get("alts") or ())
            rows=[np.asarray(c["masks"],np.int64) for c in cands]
            hp=(state.get("hero") or {}).get("pos") or ()
            x0=float(hp[0]) if len(hp)>=1 and type(hp[0]) in (int,float) else .5*(float(vr["box"][0][0])+float(vr["box"][0][2]))
            v=dict(air_seen=not ground,start=start,dir=1 if float(goal.x)>x0 else -1)
        move=MoveInstance(**run.v["move"]) if active else MoveInstance(goal.source,f,waypoint.FAMILY)
        # a failure answers for the move this Run is about, from the Run's first frame (as the floor waypoint's)
        self._waypoint_responsibility.setdefault(move,(MoveInstance(goal.source,f,goal.family),None))
        current=getattr(getattr(getattr(forecast,"rs",None),"trk",None),"now",{}).get(goal.source)
        if current is None:return declined("support unavailable")
        plan=SimpleNamespace(iid=goal.source,move=move,origin=f,entry_k=0,press_k=None,contact_frame=None)
        why=[]
        end_mode=goal.end=="past";d_=int(v.get("dir") or 0)
        try:
            geo=B2Geometry(forecast,f,move,current[2])
            # a fresh start: its rows in vault_row's order, the first whose landing and whole route are clean; every row scanned through
            # the latest of their landings (one support for the search: the per-length supports cost ~60 ms on E16-23, C19 tm19_122;
            # a row's frames past its own landing are her standing there: scanned too); an owned Run: its own row only.
            # #386 (Sol REVIEW385): an end "past" route instead ends at its real air hand-back point (her box past the body, grown by
            # VAULT_PAD, in the air) and through the end of an air dash still locked there: no landing is chosen or checked
            built=[]
            for rank,rest in enumerate(rows):
                commands=np.r_[rest,np.zeros(self.VAULT_TAIL_F,np.int64)]
                path=model_path(sim,plan,commands,game)
                if end_mode:
                    from ssbot.knowledge import kinematics as K
                    edge=(float(goal.over[2])+waypoint.VAULT_PAD) if d_>0 else (float(goal.over[0])-waypoint.VAULT_PAD)
                    bx=np.asarray(path.box);fl=np.asarray(path.flags);idx=np.arange(len(bx))
                    past=(((bx[:,0]>=edge) if d_>0 else (bx[:,2]<=edge))&((fl&K.F_GROUND)==0)
                          &(idx>=len(sim.prefix)+1))
                    if not past.any():
                        why.append(dict(rank=rank,reason="no modelled hand-back past the body on the row"));continue
                    p=int(np.argmax(past))
                    j=waypoint.dash_lock_end(np.asarray(path.states)[K.MODE],p)
                    b=bx[p];cx=.5*(float(b[0])+float(b[2]))
                else:
                    j=transfer._landing_index(path.flags,len(sim.prefix)+1)
                    if j is None:
                        why.append(dict(rank=rank,reason="no modelled landing on the row"));continue
                    b=path.box[j];cx=.5*(float(b[0])+float(b[2]))
                    if not lo<=cx<=hi:
                        why.append(dict(rank=rank,reason="modelled landing outside its band",land_x=cx));continue
                built.append((rank,commands,path,int(j),b,cx))
            jmax=max((c[3] for c in built),default=0)
            for rank,commands,path,j,b,cx in built:
                new_dash=bool(int(commands[0])&B["DASH"]) and not int(sim.prefix[0])&B["DASH"]
                limit=(min(jmax,len(path.box)-1) if not active else int(j) if new_dash else min(int(j),transfer.FOLLOW_SCAN_F))
                scan=geo.scan(path,limit=limit)
                if not scan.complete or scan.contacts:
                    why.append(dict(rank=rank,reason="route blocked",land_x=cx,
                                    first=None if not scan.contacts else asdict(scan.contacts[0])));continue
                break
            else:
                return declined("no clean row" if len(rows)>1 else why[0]["reason"] if why else "no row",rows=why,limit=None)
        except GeometryUnavailable as exc:
            return declined("geometry unavailable: "+str(exc))
        if not active:
            c=cands[rank]
            v.update(recipe=c["recipe"],rank=rank,blocked_before=why)
        mask=int(commands[0])
        v.update(F0=f+2,masks=[int(m) for m in commands[:j-len(sim.prefix)]],land_f=int(path.origin+j),
                 landing_box=[float(x) for x in b])
        if active:
            draft=logical_copy(self.runner);draft.run.v.update(vault=v,what="vault")
        else:
            draft=self.runner.fork_empty(AirAnchor())
            draft.run=Run(waypoint.PROGRAM,"go",{"iid":goal.source,"ta":float(game),"plan":list(goal.plan),"x":float(goal.x),
                                                 "by_f":int(goal.by_f),"kind":"vault","f_open":f,"move":asdict(move),"what":"vault",
                                                 "vault":v})
            self._note("waypoint_vault_chosen",frame=f,recipe=v["recipe"],start=v["start"],land_f=v["land_f"],land_x=cx,lo=lo,hi=hi,
                       over=[float(x) for x in goal.over],over_iid=goal.over_iid,keys=len(v["masks"]),rank=v.get("rank"),
                       blocked_before=v.get("blocked_before"),end=goal.end,
                       basis=("air hand-back point past the body (and any air dash's locked end) scanned for all owners; no landing"
                              if end_mode else "the whole route to its modelled landing scanned for all owners"))
        return B2Offer("active" if active else "manual_commitment",path,draft,mask,0.,move,
            {"manual_air":True,"waypoint":True,"kind":"vault","x":float(goal.x),"by_f":int(goal.by_f),"what":"vault",
             "phase":"go","predicted_bounce":None,"checked_through":int(path.origin+limit),"land_f":v["land_f"],
             "safety_basis":("bounded vault over one body: the whole route to its modelled landing scanned for all owners when chosen, "
                             "its next %d frames every tick (through the landing on a new dash), the landing inside its band; "
                             "no route certificate")%transfer.FOLLOW_SCAN_F})

    def _waypoint_delayed_ahead(self,sim,plan,goal,f,game,geo,mask,active,refused=False):
        """Task 182 (Sol seq 271 / 272): the first delayed-hazard contact on this Run's whole route, or None.
        The step gate scans one tick's key, so it meets a delayed hazard one frame before it lights; the Run has no jump and no
        search, and by then the ordinary owners cannot leave it either (#341: 3380 hand-back, owner 335470's bomb lit 3383; the
        same geometry showed it on the route from the Run's first tick 3354; open-loop replays: a hand-back by 3372 cleared it,
        none from 3376 on).
        The delayed layers are the support's own: spawned hazards at their real clock, and the per-bomb small-rune forecast, which
        times a ring from its Cast 2 before the bomb entity appears (#341: the 30.18 bomb forecast from the 3344 Cast 2, its entity
        first seen 3363, lit 3383).
        The route starts from the key this tick actually sends, the one its gates passed (waypoint.route_keys; a dash its lock
        refused leaves the run of the key sent, never the refused dash), runs through the next owner's first key and stays within
        the support's own look-ahead (its last sample, 62 frames: no raster rebuilt for a long route; a hazard farther on is met on
        a later tick, still a second before it lights). scan_delayed asks the delayed layers alone: bodies, moves and the unknown
        layer stay the step gate's full scan. A place past a body is not checked (route() has no passage above it). No route from
        the key sent, or one the geometry cannot scan: noted, left to the step gate, as before."""
        if goal.over is not None:return None
        keys=waypoint.route_keys(sim,goal,f,mask,dash_refused=refused)
        if keys is None:
            self._note("waypoint_route_unchecked",frame=f,reason="no route from the key sent",active=active);return None
        try:
            path=model_path(sim,plan,keys,game)
            samples=getattr(getattr(getattr(geo,"forecast",None),"rs",None),"samples",None)
            scan=geo.scan_delayed(path,limit=min(len(path.commands),int(samples[-1])) if samples else None)
        except GeometryUnavailable as exc:
            self._note("waypoint_route_unchecked",frame=f,reason=str(exc),active=active);return None
        return scan.contacts[0] if scan.contacts else None

    def _route_keys(self,plan,draft,mask,link,f):
        """Task 182 seq 312: this approach Run's keys from this tick's key on: a chosen row up to its contact, else the link's own keys (the air
        recipe's held side and jump, or the walk / dash / jump link rendered), at most ROUTE_H; the first is the key sent now."""
        H=transfer.ROUTE_H
        row=draft.run.v.get("row")
        if row is not None and plan.contact_frame is not None and plan.contact_frame>f+2:
            masks=row["masks"];F0=int(row["F0"])
            frames=[F for F in range(f+2,min(int(plan.contact_frame),f+1+H)+1) if 0<=F-F0<len(masks)]
            if frames:return np.array([masks[F-F0] for F in frames],np.int64)
        if link=="air":
            k=plan.entry_k+2+np.arange(H)
            cmds=np.where(int(plan.jump_until)-k>0,int(plan.side)|B["J"],int(plan.side)).astype(np.int64)
        else:
            cmds=np.asarray(transfer.render(self.runner,plan,plan.entry_k,H,link),np.int64)
        cmds=cmds.copy()
        if len(cmds):cmds[0]=int(mask)
        return cmds

    def _route_ahead(self,state,game,sim,plan,draft,mask,f):
        """Task 182 seq 312 (design 3.1; the person: two Clappers crossing, she came down on the other one): where this approach Run's route,
        its remaining planned keys rolled from the actual prefix (_route_keys), first meets the OTHER Clapper's body, carried at its STATE
        motion (a jumper ballistic), before her box reaches the target's body (the strike cut) and within ROUTE_LAND_F frames past her own
        landing (a body coming down where she lands): dict, or None. The per-step
        gate reads only this tick's key; this reads what the Run commits to, on its boxes alone (the other's moves stay the step gate's)."""
        from ssbot.knowledge import kinematics as K
        es=transfer.clappers(state)
        target=next((e for e in es if e["iid"]==plan.iid),None)
        others=[e for e in es if e["iid"]!=plan.iid]
        if target is None or len(others)!=1:return None
        row=draft.run.v.get("row");cmds=None
        if row is None and draft.run.link=="air":
            # the air recipe's keys are arithmetic: its no-side-key exit (the commonest) is read before the pre-check
            cmds=self._route_keys(plan,draft,mask,draft.run.link,f)
            if not len(cmds) or not np.any(cmds&(B["L"]|B["R"])):return None
        if transfer.route_cannot_meet(transfer._hero_box(state.get("hero")),target,others[0],
                                      len(np.asarray(getattr(sim,"prefix",())))+transfer.ROUTE_H):
            return None   # arithmetic first: the other body stays at or beyond the target's edge on her side for the whole roll
        if cmds is None:
            cmds=self._route_keys(plan,draft,mask,draft.run.link,f)
            if not len(cmds):return None
            if row is None and not np.any(cmds&(B["L"]|B["R"])):
                return None   # no side key planned yet (an air recipe still holding): the route is not committed to a direction
        p=model_path(sim,plan,cmds,game)
        boxes=np.asarray(p.box,float)
        limit=len(boxes)-1
        if not (int(p.flags[0])&K.F_GROUND):
            j=transfer._landing_index(p.flags,1)
            if j is not None:limit=min(limit,j+transfer.ROUTE_LAND_F)   # and a little past her landing: a body coming down where she lands
        if plan.contact_frame is not None and plan.contact_frame>f:limit=min(limit,int(plan.contact_frame)-int(p.origin))
        tp=transfer.body_path(target,limit);op=transfer.body_path(others[0],limit)
        if tp is None or op is None:return None
        k,cut=transfer.route_meets_other(boxes,limit,tp,op)
        if k is None:return None
        return {"other":int(others[0]["iid"]),"meet_frame":int(p.origin)+int(k),"horizon":int(limit),"link":draft.run.link,
                "keys":"row" if draft.run.v.get("row") is not None else "link","other_state":transfer.control(others[0])[0],
                "her_box":[float(v) for v in boxes[k]],"other_box":[float(v) for v in op[k]]}

    def _opening(self,prefs,f,target=None):
        """Task 182 seq 312 #387 (the person 11-10, Sol seq 333): L2 asks the small rune's high hook opening on its target (the caster):
        GoalPrefs.hook_open names it (target: the Run's own target when one is active). The opening is the rune's start: a Run begun for
        it from the observed cast (opening_run), or a fresh one from that cast's goal; a bounce / switch Run already under way on the caster
        goes on with its own strikes (above the caster after a bounce there is no face to hook: its down slash is the follow-up)."""
        ho=getattr(prefs,"hook_open",None)
        run=self.runner.run
        active=run is not None and run.chain==transfer.PROGRAM
        if target is None:target=run.v.get("iid") if active else getattr(prefs,"target",None)
        if not (_sep312(f) and ho is not None and len(ho)>=1 and target is not None and ho[0]==target):return False
        return bool(run.v.get("opening_run")) if active else getattr(self._transfer_goal,"source_kind",None)=="CAST"

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
        if (active and changed and run.link in transfer.ROUTE_LINKS and self._press is None
                and getattr(prefs,"clapper_choice",None)=="rune_down" and _sep312(f)):
            # Task 182 seq 312 (plan 2.2; #387: the target is the caster throughout, the opening hook may take either body): L2's target
            # changed while this approach has no pressed strike (another caster): it hands back at this step through B2 recovery (the keys
            # already sent stay the next owner's prefix, the failure responsibility is kept). A pressed strike keeps its own target.
            self._note("transfer_rune_target_handoff",frame=f,old_target=target,target=wanted,link=run.link)
            self._recover("small rune: the down-slash target changed",f)
            return None
        bound=self._entry_attack_goal
        if (active and run.link in transfer.ROUTE_LINKS and self._press is None and _sep312(f)
                and getattr(bound,"scope",None) in {"rune_end","sep_slam"}|SEAM_SCOPES and self._transfer_goal is not None
                and self._transfer_goal.source_kind=="SWITCH" and getattr(prefs,"entry_attack",None)!=bound):
            # Task 182 seq 312 #384 (Sol REVIEW383: the action is bound to this move / phase / target; invalid: hand back): the package
            # scene that asked for this stomp (2.3's rune end, the separated slam) ended or lost before its press: B2 recovery at this
            # step (the keys already sent stay the next owner's prefix, the failure responsibility is kept)
            self._note("transfer_scene_entry_handoff",frame=f,target=target,link=run.link,scope=bound.scope)
            self._recover("seq 312: the scene's stomp entry ended before its press",f)
            return None
        sb=self._strike_bound(f,prefs,target)
        if active and sb is not None and run.link in ("jump","air") and self._press is None:
            from . import pogo_model as PM
            hp=(state.get("hero") or {}).get("pos") or ()
            late=f+2+PM.ACTIVE[0]>sb[3]          # the earliest contact from the next free key is past the frame
            # (kind "outside", 1.2.2: she never crosses the bound; kind "seam": she comes from the other side, only the contact is bound)
            past=sb[5]=="outside" and len(hp)>=1 and type(hp[0]) in (int,float) and (float(hp[0])-sb[1])*sb[2]<0.
            if late or past:
                # Task 182 seq 312 #385 (the person's 1.2.2): no row can meet its limits any more (its contact before N unlocks, her
                # centre outside the range): handed back while she is still above it (B2 recovery; the keys sent stay the next owner's
                # prefix, the failure responsibility is kept), never a fall onto N
                self._note("transfer_bound_handoff",frame=f,target=target,link=run.link,late=bool(late),past=bool(past),bound=list(sb))
                self._recover("seq 312: the bound down slash can no longer meet its limits (%s)"%sb[5],f)
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
        if active and ground and self._held_goal is not None and self._transfer_goal is self._held_goal:
            # Task 182 seq 312 #385 (the person's 1.2.2): the hold's flight over the hammers landed (off N's outer edge): its follow-up ends
            # here (no stomp approach on N from the ground); L2's place outside the range, then its way over N once both hammers are over
            self._note("transfer_hold_landed",frame=f,target=target,link=run.link)
            self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
            self._press=self._accepted=self._hit=None
            self._transfer_ready=False;self._transfer_goal=None;self._held_goal=None
            self._abandon("1.2.2 hold landed: L2's place outside the range")
            return None
        no_witness=None
        held_run=self._held_goal is not None and self._transfer_goal is self._held_goal
        hold=((active or held_run) and not ground and self._hold_over(state,game,prefs,target))   # #385: from a held follow-up's first tick
        if hold!=self._hold_seen:
            self._note("transfer_hold_over",frame=f,target=target,hold=bool(hold),link=None if run is None else run.link,
                       basis="L2's 1.2.2 near one after its real bounce; the slam that started this chain still has a hammer stage"
                             if hold else "held off the middle no more: the follow-up as before")
            self._hold_seen=bool(hold)
        if active and run.link=="air":
            why=self._no_strike_overhead(state,sim,target)
            if (why is not None and not ground
                    and transfer.follow_scope(self._transfer_goal,target,bool(run.v.get("follow_close")))):
                # Task 183 seq 262: the bounce follow-up reads the gap first; this hand-back stands if it takes nothing
                no_witness=why;why=None
            if hold and no_witness is not None:
                # Task 182 seq 312 #384 (plan 1.2.2): over N waiting for the hammer's end is the follow-up's own wait, not a Run that
                # lost its strike: no hand-back for the witness alone (every step is still scanned for all owners; a blocked one hands back)
                no_witness=None
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
        # Task 182 seq 312 #387 (the person 11-10, Sol seq 333): L2's small-rune opening on this Run's caster target (its high hook): a
        # fresh Run may start for it while the observed cast's goal holds (on the ground or already in the air: the first 0.2 s of the
        # Spell Antic on the ground is the plain transfer's own admission)
        opening=self._opening(prefs,f,target)
        if not (self._transfer_ready or opening) and (run is None or run.chain!=transfer.PROGRAM):return None
        queued,_=self.queued_prefix(f,state)
        if queued is None or int(sim.prefix[0])!=queued:
            if active:self._recover("rune transfer actual queued prefix mismatch",f)
            return None
        glide=False
        if not active:
            mode=self._locked_mode(sim)
            from ssbot.knowledge import kinematics as K
            if (mode==K.M_GLIDE and _sep312(f)
                    and (opening or getattr(getattr(prefs,"entry_attack",None),"scope",None) in {"rune_end"}|SEAM_SCOPES)):
                # Task 182 seq 312 #387 (Sol seq 334: 2.3 waited out the planner's own umbrella, #386 sy27_23s; a local release is
                # authorized): the umbrella is steerable (the jump key's release deflates it, an attack / dash cancels it): the package's
                # own seam / rune-end entries and the small rune's opening start from it; the Run's keys hold no J, the model rolls the
                # deflate, every step is scanned as before (rune_transfer_glide_release: the Run made from it, its first key)
                glide=True;mode=None
            if mode is not None:
                # Task 179 (live 786 2607: the SWITCH entry bound inside her own leftward air dash, 2610-2616 took
                # no input): a fresh transfer never starts inside a dash or a relinquished motion; its keys could
                # not change the route. The current owner keeps the keys; the start is retried once she is free.
                self._note("rune_transfer_start_deferred",frame=f,target=target,mode=mode,
                           owner="current owner keeps the keys",reason="hero in a dash or relinquished motion")
                return None
        rs=getattr(forecast,"rs",None)
        # #385 (the person's 1.2.2): a held follow-up never strikes N again (N unlocks at F's Slam 2 entry) and keeps drifting off N's outer
        # edge until its landing or a clean middle landing route (_follow_decide), also after both hammers
        strike_kw={"no_strike":True} if held_run else self._seam_strike_kw(prefs,target,run) if active else {}
        made=transfer.propose(self.runner,state,game,sim,target,ground,self._context[3],self._transfer_finished,self._transfer_goal,
                              **({"idle_evidence":self._idle_ev} if self._idle_ev else {}),
                              **({"approach_only":True} if approach_only else {}),
                              **({"hold_over":True} if hold or (held_run and not ground) else {}),
                              **({"bound":sb} if sb is not None else {}),
                              **({"hook_open":True} if opening else {}),
                              **strike_kw)
        if opening and made is not None and made[0] is not None:
            # #387: the opening's own hook check, recorded when its outcome changes (the hooked body, the reason, a lost opening)
            fc=made[0].run.v.get("face_hook_check");eh=made[0].run.v.get("early_hook")
            early=None if not isinstance(eh,dict) else {k:eh[k] for k in ("ok","why","decide_f","hooked_iid","lost","f") if k in eh}
            if early is not None and isinstance(early.get("why"),str):early["why"]=early["why"][:160]
            key=(made[0].run.link,None if not isinstance(fc,dict) else fc.get("why"),made[0].run.v.get("opening_lost"),
                 made[0].run.v.get("slash_iid"),None if early is None else (early.get("ok"),early.get("why")))
            if key!=getattr(self,"_opening_noted",None):
                self._opening_noted=key
                self._note("transfer_opening_check",frame=f,target=target,link=made[0].run.link,
                           check=None if not isinstance(fc,dict) else {k:fc[k] for k in ("ok","why","hooked_iid","held_low","held_high",
                                                                                          "band_lo","band_hi","vy_press") if k in fc},
                           hooked=made[0].run.v.get("hooked_iid"),lost=made[0].run.v.get("opening_lost"),early=early,
                           slash=made[0].run.v.get("slash_iid"))
        if made is None or made[0] is None:
            if active:self._recover((made[1].ended_reason if made is not None else None)
                                    or "rune transfer ended or target began a new move before real bounce",f)
            return None
        if active and type(run.v.get("slash_iid")) is int and made[0].run.v.get("slash_iid") is None and made[0].run.v.get("opening_slash_done"):
            # #387: the opening's rising side down slash missed (the body evaded) and the Run is back in the air, rising on to the hook: its
            # press / accept / hit records are spent (a later strike is its own); the commitment and its responsibility stay
            self._press=self._accepted=self._hit=None
            self._note("transfer_opening_slash_missed",frame=f,target=target,slash=run.v.get("slash_iid"),link=made[0].run.link)
        if glide:
            self._note("rune_transfer_glide_release",frame=f,target=target,opening=bool(opening),link=made[0].run.link,mask=int(made[3]),
                       scope=getattr(getattr(prefs,"entry_attack",None),"scope",None),
                       basis="a Run made in the planner's own umbrella; its keys hold no J (the release is the sent key, not this note)")
        draft,plan,path,mask=made
        b13=draft.run.v.get("b13")
        if isinstance(b13,dict):
            # Task 182 B13: the air link's body guard decision (knife_chain_transfer.b13_guard), noted once per decision
            key=(plan.move,b13.get("kind"),b13.get("steer"),b13.get("contact_F"),
                 None if b13.get("kind")=="wait" else b13.get("f"))
            if key!=getattr(self,"_b13_noted",None):
                self._b13_noted=key
                self._note("transfer_b13_guard",frame=f,target=plan.iid,link=draft.run.link,mask=int(mask),**b13)
        if draft.run.link=="strike" and draft.run.v.get("seam_bound_fallback") and (run is None or run.link!="strike"):
            # Task 182 seq 312 #386: the seam bound's rows out of reach: the target's ordinary stomp row (knife_chain_transfer.stomp_plan)
            self._note("transfer_seam_bound_fallback",frame=f,target=plan.iid,row=draft.run.v.get("row",{}).get("contact_frame"))
        if plan.move in self._failed_hook_moves:return None
        tgt_e=next((e for e in transfer.clappers(state) if e["iid"]==plan.iid),None)
        # (#387: after the opening's hook, or with no opening: the opening's own approach goes on toward the caster, its hook first)
        casting=bool(_sep312(f) and tgt_e is not None and transfer.control(tgt_e)[0] in transfer.HOOK_CAST_STATES
                     and not transfer.opening_pending(draft.run.v))
        if ((transfer.plan_over_call(draft.run.v) or casting) and draft.run.link in ("jump","air")
                and int(mask)&(B["L"]|B["R"])):
            # Task 182 (Sol seq 255 F2): rising to go over a body: no side key while holding it would carry her box into that body; she
            # rises first and the clean strike row (press_now_row clean) takes over from there. The hold and the J stay the link's.
            # #387 (g387_X14 54855: a body-corner contact after a real bounce off the caster): a caster's body in its cast stands taller
            # (top ~7.78 against 6.92) and the approach's step check leaves the target's own body to the strike: the same hold-back
            body=transfer.body_box(tgt_e or {})
            held=model_path(sim,plan,np.full(14,int(mask),np.int64),game)
            if body is not None and transfer.enters_body(held.box,body,len(held.box)):
                mask=int(mask)&~(B["L"]|B["R"])
                path=replace(model_path(sim,plan,np.array([mask],np.int64),game),stage=path.stage,assumptions=path.assumptions)
                self._note("transfer_side_held_back",frame=f,target=plan.iid,link=draft.run.link,casting=casting)
        current=None if rs is None else getattr(rs.trk,"now",{}).get(plan.iid)
        if current is None:
            if active:self._recover("rune transfer support unavailable",f)
            return None
        if not hold and self._follow_due(self._transfer_goal,draft,run,active,ground,approach_only):
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
                elif goal.responsibility.family in ("RUNE_END","SEAM"):
                    # Task 182 seq 312 (#384): 2.3's rune end is no move the tracker holds; its instance is the (caster, rune-end frame)
                    # L2 binds once (_bind_entry_attack), the caster still present (goal_preferences); L2's entry is its lifetime.
                    # #386: a seam entry's action the same (its source move may be over)
                    pass
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
                        if active:
                            if lock is not None and lock.complete and lock.contacts:self._strike_refused(f,plan,run,first)
                            self._recover("rune transfer air dash refused: locked motion blocked or unknown",f)
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
                # #387 (the person 11-10: "弹到最高点交给踩头代码接管就好"): the small rune's opening hands its bounce to this Run's own
                # stomp rules (the air link after the hook's release), not to the N=2 landing outs at its entry
                if scan.complete and not scan.contacts and not draft.run.v.get("hook_open"):
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
                           branch_first=draft.run.v.get("_hook_branch_first"),opening=bool(draft.run.v.get("hook_open")),
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
            if active:
                if scan.complete and scan.contacts:self._strike_refused(f,plan,run,first)
                self._recover("rune transfer external step blocked",f)
            return None
        if (draft.run.link in transfer.ROUTE_LINKS and not draft.run.v.get("seam_inner")
                and _sep312(f) and not (transfer.opening_pending(draft.run.v)
                                        and (draft.run.link in ("jump","air")
                                             or any((draft.run.v.get("early_hook") or {}).get(k) for k in ("ok","near"))))):
            # (#387: the small rune's opening up in the air, or on the ground with its early jump's hook passing: its hook's ray takes the
            # first body, the other one included (the person: either one is hooked); the route's keys know neither the next tick's jump
            # nor the hook (h387_hookN 102672: a fresh Run turned back 13 times, its early jump never stored); the per-step gate still
            # scans every owner)
            # Task 182 seq 312: the route ahead meets the other body before the target: a revocable approach hands back now (the keys already
            # sent stay the next owner's prefix; a strike row already chosen, a hook and a source tail are not approach links); a fresh one
            # does not start while it does
            try:blocked=self._route_ahead(state,game,sim,plan,draft,mask,f)
            except (GeometryUnavailable,NominalUnsupported,AttributeError,TypeError,ValueError,IndexError,KeyError) as exc:
                # the route's own read failing never blocks or crashes the Run: noted, the step gate as before
                blocked=None;self._note("transfer_route_unchecked",frame=f,reason=repr(exc)[:200])
            if blocked is not None:
                self._note("transfer_route_blocked",frame=f,active=active,target=plan.iid,**blocked,
                           owner=("B2 recovery hands back; failure responsibility kept" if active else "current owner keeps the keys"))
                if active:self._recover("rune transfer route meets the other Clapper's body before its target",f)
                return None
        goal=self._transfer_goal
        responsibility=(transfer.MoveInstance(plan.caster,plan.cast_fa,"CC_CAST") if goal is None else goal.responsibility)
        self._transfer_responsibility.setdefault(plan.move,(responsibility,None if goal is None else goal.cast_ta))
        return B2Offer("active" if active else "manual_commitment",path,draft,int(mask),0.,plan.move,
            {"manual_air":True,"rune_transfer":True,"caster":plan.caster,"cast_fa":plan.cast_fa,
             "opening":bool(draft.run.v.get("opening_run")),
             "target_ta":target_ta,"target_attack_checked":attacking,
             "target_move":None if target_move is None else asdict(target_move),
             "tail_checked_through":draft.run.v.get("source_tail_checked_through"),
             "tail_mask":draft.run.v.get("source_tail_mask"),
             "approach_recipe":draft.run.v.get("approach_recipe"),"approach_only":approach_only,
             **({"b13":(draft.run.v.get("b13") or {}).get("kind"),"b13_steer":draft.run.v.get("b13_steer")} if transfer.B13 else {}),
             "strike_direction":None if draft.run.v.get("row") is None else draft.run.v["row"].get("approach_direction"),
             "strike_support":None if draft.run.v.get("row") is None else draft.run.v["row"].get("support","still"),
             "strike_walk":None if draft.run.v.get("row") is None else draft.run.v["row"].get("walk"),
             "conditional_hit_check":conditional_contact is not None,"conditional_contact":conditional_contact,
             "checked_through":path.through,"phase":draft.run.link,"predicted_bounce":None,
             "handoff":("observed range or tactical boundary; ordinary side rows" if approach_only else
                        "real hit+bounce reopens tactical target knife; observed source hammer tail retained"),
             "safety_basis":"manual distance recipe; current external step only; no full-flight safety certificate"})

    def _seam_strike_kw(self,prefs,target,run):
        """Task 183 seq 267/268 (Sol; the person's middle rule): propose's new-strike limit for an active bounce follow-up
        Run (follow_scope) on a target in L2's no_hit. Only the manual-B middle return crossing that body with nothing else
        banning it (GoalPrefs.return_cross) gives way, and only to a seam down-slash row (seam_only: propose's seam_inner
        from the current close-pair geometry with a known inner side, the row's first contact checked on that side at its
        own contact index against the strike witness, seam_contact); no other row, no face hook. Any other no_hit source on
        the same iid: no new strike at all (no_strike: positioning only, or the existing gates hand back). Not in no_hit, or
        not a follow-up Run: no limit (the original semantics). The first transfer admission and a strike row already
        chosen are as before."""
        if (target not in getattr(prefs,"no_hit",())
                or not transfer.follow_scope(self._transfer_goal,target,bool(run.v.get("follow_close")))):return {}
        return {"seam_only":True} if target in getattr(prefs,"return_cross",()) else {"no_strike":True}

    def _hold_over(self,state,game,prefs,target):
        """Task 182 seq 312 (#384; the person, plan 1.2.2: over N into the middle once both hammer stages of F's slam are over): L2's
        1.2.2 near one (GoalPrefs.hold_over) after a real bounce on it, the slam that started this chain (the other Clapper's: the bounce
        goal's responsibility) still with a hammer stage live or to come (transfer.cross_hammer_pending). While it holds the follow-up
        stays off the middle (no middle landing, no seam aim or row) and the air Run over N is not handed back for its missing witness
        alone; every step is still scanned for all owners. Once over: the Task 183 follow-up as it was (the middle, its fall slash)."""
        if not _sep312(state.get("f")) or target not in frozenset(getattr(prefs,"hold_over",()) or ()):return False
        return transfer.cross_hammer_pending(state,self._transfer_goal,game)

    def _strike_bound(self,f,prefs,target):
        """Task 182 seq 312 (#385; the person's 1.2.2: while F slams, N locked, down slash N outside the range before it unlocks; Sol seq 326:
        the shared seam strike of 2.3): L2's GoalPrefs.strike_bound for this target, on its SWITCH stomp (never its bounce): (aim_x, bound_x,
        sign, by_f, jump_hold or None, kind), or None."""
        sb=getattr(prefs,"strike_bound",None);goal=self._transfer_goal
        if (sb is None or not _sep312(f) or sb[0]!=target or goal is None or goal.source_kind!="SWITCH"
                or isinstance(goal,transfer.ReturnGoal)):return None
        return (float(sb[1]),float(sb[2]),int(sb[3]),int(sb[4]),None if sb[5] is None else int(sb[5]),
                str(sb[6]) if len(sb)>6 else "outside")

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
        inside,hb,gap=self._follow_landing_inside(state,run)
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
        first decision) nearest the goal (a fresh route: transfer.near_landing_goal; an owned route keeps its goal), scanned whole to the modelled
        ground for all owners with no exemption, MIDDLE_SCAN_N per batched pass in that order; the first clean one, or None."""
        from ssbot.knowledge import kinematics as K
        f=state["f"]
        if old is not None:
            kept=self._owned_route(state,game,sim,geo,plan,gap,old,"middle")
            if kept is not None:return kept
        goal_x=transfer.near_landing_goal(gap,hb) if old is None else min(max(float(old["goal_x"]),gap.lo),gap.hi)
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
                fall=self._fall_slash(state,sim,geo,gap,c)
                if fall is not None:commands,p,sc,slash_at=fall;b=p.box[-1]
                else:slash_at=None
                follow={"kind":"middle","recipe":recipe,"dir":int(transfer.middle_direction(hb,goal_x)),"F0":f+2,
                        "masks":[int(m) for m in commands],
                        "release_F":f+2+int(r),"land_f":int(p.through),"goal_x":float(goal_x),"lo":gap.lo,"hi":gap.hi,
                        "other":int(gap.other),"landing_box":[float(v) for v in b],"rank":rank,"candidates":len(cands),
                        "fall_slash":slash_at}
                self._note("transfer_follow_middle",frame=f,owned=old is not None,dash_free=dash,
                           **{k:v for k,v in follow.items() if k!="masks"},rejected_before=firsts,
                           scope="whole route to the modelled ground, all owners, no exemption; landing inside the gap by MIDDLE_PAD_U")
                return "middle",follow,p,sc
        self._note("transfer_follow_middle_blocked",frame=f,lo=gap.lo,hi=gap.hi,goal_x=goal_x,owned=old is not None,
                   dash_free=dash,candidates=len(cands),scanned=firsts)
        return None

    def _fall_slash(self,state,sim,geo,gap,c):
        """Task 182 seq 289 (the person: falling to the Clapper's head height, one slash before the landing): the chosen clean row (a first
        middle route) with its pre-landing side slash (transfer.fall_slash_commands), rolled again and its whole route scanned for all owners
        with the same gates as the row itself. (commands, route, scan, press index) or None: the row stays as it was."""
        from ssbot.knowledge import kinematics as K
        made=transfer.fall_slash_commands(sim,c[2],c[5],gap,((state.get("hero") or {}).get("tm") or {}).get("atk_cd"))
        if made is None:return None
        commands,at=made
        ro=sim.roll(np.asarray([commands],np.int64));j=transfer._landing_index(ro.flags[0],sim.off)
        if j is None:return None
        b=ro.box[0,j];way=ro.box[0,1:j+1]
        if (not np.isfinite(b).all() or b[0]<gap.lo+transfer.MIDDLE_PAD_U or b[2]>gap.hi-transfer.MIDDLE_PAD_U
                or transfer._meets(way,gap.bounced) or transfer._meets(way,gap.other_body)):return None
        keys=commands[:j-sim.off+1]
        p=transfer.route_path(sim,keys,np.asarray(ro.box[0,:j+1],float).copy(),np.asarray(ro.flags[0,:j+1]).copy())
        sc=geo.scan_batch([p])[0]
        if not sc.complete or sc.contacts or not p.flags[-1]&K.F_GROUND:return None
        return keys,p,sc,at

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
        seam action or its own gate turns it down, the reason recorded. seq 266: an owned outer landing tries the seam too
        (released from it) and goes on only while the seam action is not legal and the landing itself still is."""
        f=state["f"];draft,plan,_,_=made
        keep=None if run is None or run.link not in transfer.FOLLOW_LINKS else run.link
        old=None if keep is None else run.v.get("follow")
        gap=transfer.two_gap(state,plan.caster);hb=transfer._hero_box(state.get("hero"))
        stand=bool(gap is not None and hb is not None and transfer.standable(gap,hb))
        if keep is None and self._held_goal is not None and self._transfer_goal is self._held_goal:
            # Task 182 seq 312 #385 (the person's 1.2.2): the held bounce once both hammers are over: a clean middle landing from her state
            # when one exists (Task 183's middle rows, the whole route scanned); otherwise the drift off N's outer edge goes on and her
            # landing ends it (L2's vault over N from there): no seam approach or outer landing across N from its outer side (C12 sy12_122
            # 131502: the seam approach's key toward N passed its two-frame step, the next step met N with that key in flight)
            choice=None
            if stand:
                try:
                    choice=self._middle_choice(state,game,sim,B2Geometry(forecast,f,plan.move,current[2]),plan,gap,hb,None)
                except (GeometryUnavailable,NominalUnsupported) as exc:
                    self._note("transfer_follow_unchecked",frame=f,link=keep,reason=str(exc));return False,None
            if choice is not None:return self._follow_install(state,game,sim,made,run,keep,choice)
            wp=getattr(prefs,"waypoint",None)
            if wp is not None and getattr(wp,"kind",None)=="vault" and wp.over_iid==plan.iid and _sep312(f):
                # Task 182 seq 312 #386 (the person 11-10 / Sol seq 330: back into the middle after the hammers; Sol REVIEW385 1): no clean
                # middle landing, and L2's way back names the vault over this body: it takes the keys here, in the air above its top, where
                # the body's floor growth cannot reach her (from the floor 1 u off it the growth met every row: sy21_122 131517-131552). No
                # strike was pressed in the hold; the keys already sent stay the next owner's prefix (the waypoint branch, this same tick)
                self._note("transfer_follow_held_to_vault",frame=f,target=plan.iid,plan=[str(v) for v in wp.plan[0]],
                           box=None if hb is None else [float(v) for v in hb])
                self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
                self._press=self._accepted=self._hit=None
                self._transfer_ready=False;self._transfer_goal=None;self._held_goal=None
                self._abandon("1.2.2 hold after the hammers: L2's way back over the bounced body from the air")
                return True,None
            self._note("transfer_follow_held",frame=f,standable=stand,width=None if gap is None else gap.width,
                       choice="no clean middle landing: the drift off the bounced body goes on, her landing ends it")
            return False,None
        if keep is None and hb is not None and _sep312(f) and transfer.small_gap(gap):
            # Task 182 seq 312 #385 (the person 11-10, Sol seq 326): the shared small-gap after-move of a return into the middle: one down
            # slash aligned with the seam before any middle landing (no double-hit proof, no standing-gap proof): the existing witnessed
            # seam strike (propose's seam rows, its aim the seam itself), its own gates deciding; without it the entry's rules below
            try:
                geo=B2Geometry(forecast,f,plan.move,current[2])
                taken=self._seam_follow(state,game,sim,geo,plan,prefs,made,run,keep,gap,hb,stand,old)
            except (GeometryUnavailable,NominalUnsupported) as exc:
                self._note("transfer_follow_unchecked",frame=f,link=keep,reason=str(exc));return False,None
            self._note("transfer_follow_small_gap",frame=f,width=gap.width,seam=gap.seam,
                       choice="seam strike" if taken else "no seam strike now: the follow-up's own rules")
            if taken:return False,None
        if keep is None and not stand:
            if gap is not None and hb is not None and _sep312(f):
                handled,offer=self._follow_stacked(state,game,sim,forecast,prefs,made,run,current,gap)
                if handled:return handled,offer
            # no standable gap: the existing witnessed down-slash on the target's inner side; its own gates decide
            if gap is not None and hb is not None:self._note_seam(f,gap,hb,made,False,None,prefs)
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
            if choice is None:
                # seq 312 #379: an owned outer landing with no standable gap goes on while legal (no single seam strike retakes it)
                stacked_land=keep=="land" and not stand and _sep312(f)
                if not stacked_land and self._seam_follow(state,game,sim,geo,plan,prefs,made,run,keep,gap,hb,stand,old):return False,None
                if keep=="land":choice=self._side_landing_choice(state,game,sim,geo,plan,prefs,old)   # goes on while legal
                elif stand:choice=self._side_landing_choice(state,game,sim,geo,plan,prefs,None)
        except (GeometryUnavailable,NominalUnsupported) as exc:
            self._note("transfer_follow_unchecked",frame=f,link=keep,reason=str(exc))
            if keep:
                self._recover("bounce follow-up route unchecked: "+str(exc),f);return True,None
            return False,None
        if choice is None:
            if keep:
                self._recover("bounce follow-up: no standable gap under the route" if keep=="middle" and not stand else
                              "bounce follow-up: no seam action and the owned outer landing no longer legal" if keep=="land" else
                              "bounce follow-up: no safe middle and no legal left / right landing",f);return True,None
            self._note("transfer_follow_none",frame=f,link=draft.run.link,owner="the existing air / strike link continues")
            return False,None
        return self._follow_install(state,game,sim,made,run,keep,choice)

    def _follow_stacked(self,state,game,sim,forecast,prefs,made,run,current,gap):
        """Task 182 seq 312 #379 (the person 11-09: two stacked with no seam down-slash on both, stand on the ground; "many times she sat on
        top of two close ones"): a bounce follow-up's first decision with no standable gap. The seam double's intent (the two near body
        edges within clapper_separated.DOUBLE_GAP_U, their tops within DOUBLE_TOP_U): the follow-up ends here and the ordinary rows take the
        seam (L2's seam stance and stomp; each body's contact is the rows' own model contact). Otherwise the existing ordinary left / right
        landing (each route scanned whole for all owners, the legal one by the B2 endpoint value), the side slashes after it from the ground
        (L2's ground stance in front of the near one). No legal landing: the existing seam strike goes on, as before. (handled, offer)."""
        from .tactics import clapper_separated as SEP
        f=state["f"]
        level=abs(float(gap.bounced[3])-float(gap.other_body[3]))<=SEP.DOUBLE_TOP_U
        if gap.width<=SEP.DOUBLE_GAP_U and (level or transfer.small_gap(gap)):
            # (#385, Sol seq 326: at most TIER_U no tops gate either: the rows' seam strike, never the outer landing for want of a double)
            # handed back through B2 recovery: the keys sent stay the next owner's prefix and the failure responsibility is kept
            self._note("transfer_follow_stacked",frame=f,choice="seam double intent: the ordinary rows",width=gap.width,
                       tops=[float(gap.bounced[3]),float(gap.other_body[3])])
            self._recover("bounce follow-up: stacked with the seam double's intent; the ordinary rows' seam down slashes",f)
            return True,None
        try:
            geo=B2Geometry(forecast,f,made[1].move,current[2])
            choice=self._side_landing_choice(state,game,sim,geo,made[1],prefs,None)
        except (GeometryUnavailable,NominalUnsupported) as exc:
            self._note("transfer_follow_unchecked",frame=f,link=None,reason=str(exc));return False,None
        if choice is None:
            self._note("transfer_follow_stacked",frame=f,choice="no legal outer landing: the existing seam strike",width=gap.width)
            return False,None
        self._note("transfer_follow_stacked",frame=f,choice=choice[1].get("kind"),width=gap.width,
                   basis="no seam double: the ordinary landing, then side slashes from the ground")
        return self._follow_install(state,game,sim,made,run,None,choice)

    def _note_seam(self,f,gap,hb,made,stand,released,prefs=None):
        v=made[0].run.v;link=made[0].run.link;row=v.get("row") if link=="strike" else None
        iid=made[1].iid
        self._note("transfer_follow_seam",frame=f,lo=gap.lo,hi=gap.hi,seam=gap.seam,side=int(v.get("side") or 0),
                   link=link,mask=int(made[3]),target_frame=f+2,inner=v.get("seam_inner"),
                   new_strike_ok=not v.get("no_strike"),seam_rows_only=bool(v.get("seam_only")),
                   l2_no_hit=iid in getattr(prefs,"no_hit",()),
                   return_cross_only=iid in getattr(prefs,"return_cross",()),
                   strike=None if not isinstance(row,dict) else {k:row.get(k) for k in ("contact_frame","contact_x","inner_bound","approach_direction")},
                   outer_rejected=v.get("seam_rejects"),hero_x=.5*(hb[0]+hb[2]),gap_standable=bool(stand),released=released,
                   middle="no clean middle landing route now" if stand else "no standable gap",
                   fallback=("the owned outer landing while it is still legal, else the gate's own hand-back" if released=="land" else
                             "the legal ordinary left / right landing if this action's own gate turns it down" if stand else
                             "the gate's own hand-back"),
                   basis="the middle is the follow-up's goal: the existing witnessed down-slash, its first contact on the target's "
                         "inner side (roots' order; bound read at the row's own contact index), every tick until a middle landing is clean")

    def _seam_follow(self,state,game,sim,geo,plan,prefs,made,run,keep,gap,hb,stand,old=None):
        """Task 183 seq 265: no clean middle landing now (a standable gap's landing routes blocked, or an owned middle route
        blocked / its gap closed): the follow-up stays on the middle by the existing seam approach or hold over the target's
        inner side and its witnessed inner down-slash (propose's seam rows; an owned middle route released to the air link).
        This tick's air / strike link gates it as before (current step for all owners, dash lock, strike witness). True: that
        action goes on (handled False); when the gate turns it down the fallback (_seam_fallback) is a standable gap's legal
        ordinary landing, or (seq 266) an owned outer landing released here: that landing goes on while it is still legal
        (its own route check: kept, or a fresh row the same way), else the gate's own hand-back. False: no seam action (no
        released link, not a close pair, the side unknown, or no strike witness possible on the target at all:
        _no_strike_witness)."""
        f=state["f"]
        if keep in transfer.FOLLOW_LINKS:   # an owned middle (seq 265) or outer landing (seq 266) route, released
            made=transfer.propose(self.runner,state,game,sim,plan.iid,False,self._context[3],self._transfer_finished,
                                  self._transfer_goal,follow_release=True,
                                  **(self._seam_strike_kw(prefs,plan.iid,run) if run is not None else {}),
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
        if keep=="land":   # seq 266: the owned outer landing goes on while legal if the seam's gate turns it down
            side=lambda:self._side_landing_choice(state,game,sim,geo,plan,prefs,old)
        elif stand:
            side=lambda:self._side_landing_choice(state,game,sim,geo,plan,prefs,None)
        else:side=None
        if side is not None:
            self._follow_fallback={"f":f,"state":state,"game":game,"sim":sim,"made":made,"run":run,"side":side}
        if keep in transfer.FOLLOW_LINKS:self._follow_made=made
        self._note_seam(f,gap,hb,made,stand,keep,prefs)
        return True

    def _seam_fallback(self,f,why):
        """Task 183 seq 265: this tick's seam action turned down by its own gate (why: the external step blocked or
        unchecked, its air dash refused). With a standable gap the existing legal ordinary left / right landing goes instead
        (scanned whole now); seq 266: released from an owned outer landing, that landing goes on while it is still legal
        (_side_landing_choice with the owned route). The reason recorded; None: the gate's own hand-back stands (no
        standable gap, or no legal landing)."""
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
            self._transfer_finished.add(self._finished_key(selected.details))
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
                # #387 (Sol seq 335): the hooked body's identity rides with the watch from this send (the small rune's opening may hook
                # the other one); the Move, its target (the caster) and its responsibility instance stay the Run's
                hook=transfer.hook_iid(run.v,selected.move.target_iid)
                self._hook_start={"move":selected.move,"origin":sent.frame,"targets":(cs.f_press,cs.f_press+1),
                                  "sent_targets":set(),"seen_frame":None,"hook_iid":hook}
                self._note("b2_hook_start_expected",frame=sent.frame,move=vars(selected.move),hook_iid=hook,
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
        hooked=transfer.hook_iid(v,c["move"].target_iid,watch)   # #387: the opening's hooked body (F or N), else the Move's target
        from .knife_chain_face_hook import hook_alt
        alt=hook_alt(v)   # #387: the opening's other body behind it on the ray (the needle meets it if the first one left)
        for ev in state.get("ev") or ():
            d=ev.get("d") or {}
            if ev.get("k")!="hit" or str(d.get("src") or "") not in ("Harpoon Damager","Harpoon Dash Damager"):continue
            ent=d.get("ent") if d.get("ent") is not None else d.get("iid");ef=ev.get("f",f)
            if type(ef) is not int or not watch["seen_frame"]<=ef<=f:continue
            if ent==hooked or (alt is not None and ent==alt):
                v.setdefault("hook_hit_f",ef);watch.setdefault("hook_hit_iid",int(ent))
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
            self._transfer_finished.add(self._finished_key(selected.details))
        return super()._abort_hook_dispatch(selected,**kwargs)

    def _strike_iid(self,c):
        """#387: while the transfer Run's chosen row is the opening's rising side down slash, its DownSlash is credited on that body (the
        one too near to hook, N or F); the Move, its target and its responsibility stay the caster's."""
        run=self.runner.run
        if run is not None and run.chain==transfer.PROGRAM and c is not None and run.v.get("iid")==c["move"].target_iid:
            return transfer.slash_iid(run.v,c["move"].target_iid)
        return super()._strike_iid(c)

    @staticmethod
    def _finished_key(details):
        """The per-cast no-retry key of a sent transfer Run: (caster, cast frame); #387: the small rune's opening its own (+ "opening"),
        so a plain transfer begun on the cast before L2's 2.2 took the scene does not spend it (transfer.propose reads the same keys)."""
        key=(details["caster"],details["cast_fa"])
        return key+("opening",) if details.get("opening") else key

    def _strike_refused(self,f,plan,run,first):
        """Sol seq 272 B / seq 274: the evidence the over_head stage's withdrawal reads (forum_planner._stage_withdrawn). Called only
        where the active transfer Run is about to be recovered because one of two action gates met a real contact in its COMPLETE
        scan (the new dash's lock scan, the external step scan) and no seam fallback took the tick; first: that PathContact. It
        counts only for the tactical entry's own strike: the Run's target and the plan's target and caster are the entry's target
        and source, the goal is that entry's (not a return), no real bounce yet. A prefix, support or context failure, an unknown or
        incomplete scan, a supervisor refusal and any other recovery record nothing."""
        entry=getattr(self,"_entry_attack_goal",None);goal=getattr(self,"_transfer_goal",None)
        if (entry is None or run is None or run.chain!=transfer.PROGRAM or run.v.get("bounced") or goal is None
                or isinstance(goal,transfer.ReturnGoal) or (goal.target,goal.caster)!=(entry.target,entry.source)
                or run.v.get("iid")!=entry.target or (plan.iid,plan.caster)!=(entry.target,entry.source)):
            return
        self.refused_strike=(int(f),int(entry.target),str(entry.kind),int(entry.source))
        self._note("transfer_strike_refused",frame=int(f),target=int(entry.target),kind=str(entry.kind),source=int(entry.source),
                   link=run.link,first=first)

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
            watch=self._hook_start if self._hook_start is not None and self._hook_start["move"]==source["move"] else None
            if bound is None and hooked and self._actual_state is not None:
                # The hook ticks bind nothing (their step branch runs first); the attack the needle provoked is the
                # target's observed current move (live: Slam Antic from 2654 when the release aborts at 2673); #387: the
                # hooked body's (the small rune's opening may hook the other one)
                bound=next((m for fam in ("CC_SLAM","CC_JUMP_CAST","CC_JUMP")
                            for m in (self._observed_transfer_move(self._actual_state,
                                                                   transfer.hooked_body(run.v,run.v.get("iid"),watch),fam),)
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
