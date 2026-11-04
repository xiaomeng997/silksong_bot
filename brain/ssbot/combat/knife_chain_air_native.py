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
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_nominal import logical_copy,NominalUnsupported


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
        return tables

    @property
    def candidate_generation(self):
        return bool(getattr(self,"_candidate_enabled",False) and
            (getattr(self,"_air_context",None) is not None or getattr(self,"_transfer_ready",False) or getattr(self,"_vault_ready",False)
             or (self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM) or getattr(self,"commitment",None) is not None
             or (self.runner.run is not None and self.runner.run.chain=="vault_idle")
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
        self._wall_pressure=None
        self._entry_attack_seen=None
        self._entry_attack_goal=None
        self._transfer_responsibility={}
        self._transfer_target_moves={}
        self._vault_ready=False
        self._vault_responsibility={}
        self._vault_origins={};self._vault_completed=set()
        super().reset(episode,start_frame=start_frame)
        transfer.slam_tail_frames()  # preload before timed decisions, share immutable counts
        self.vault_enabled="vault_idle" in self.runner.chains

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
        self._transfer_goal=transfer.TransferGoal(target,hit,state["f"],ta,"BOUNCE",source)
        self._note("target_transfer_bounce_goal",frame=state["f"],**asdict(self._transfer_goal))
        return True

    def _observed_transfer_move(self,state,iid,family):
        """Use the existing causal antic history for a real move's identity."""
        phases={"CC_CAST":("Spell Antic",{"Spell Antic","Cast 1","Cast 2"}),
                "CC_SLAM":("Slam Antic",set(transfer.AIR_ATTACK_STATES)|{"Slam Recover"}),
                "CC_JUMP":("Jump Antic",{"Jump Antic","Jump Aim","Jump","Air","Charged?","Slam Effects?","Slam 2","Slam Recover"}),
                "CC_JUMP_CAST":("Cast Slam Antic",{"Cast Slam Antic","Cast Slam Antic 2","Cast Jump","Jump Aim","Jump","Air","Charged?","Slam Effects?","Slam 2","Slam Recover"})}
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
        from .knife_chain_wall_native import prepare_goal
        if prepare_goal(self,state,prefs,handoff=handoff):
            from .knife_chain_wall_native import preferences as wall_preferences
            return wall_preferences(self,prefs)
        if (self.arm!="B" or not handoff or self.commitment is not None or
                self.recovery is not None or getattr(prefs,"want_bind",False)):
            self._transfer_ready=False
            return prefs
        if (self._transfer_goal is not None and self._transfer_goal.source_kind=="SWITCH" and
                self.runner.run is None and self._entry_attack_goal!=getattr(prefs,"entry_attack",None)):
            self._transfer_goal=None;self._entry_attack_goal=None
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
            return self._transfer_offer(tick[1],tick[2],sim,forecast,prefs,tick[3])
        pressure=getattr(prefs,"wall_pressure",None)
        if (self.commitment is None and self.post_context is None and pressure is not None
                and pressure.target==getattr(prefs,"target",None) and pressure.kind=="side"):
            return None  # L2's wall-gap ground slash must not become a fresh jump/vault
        entry=getattr(prefs,"entry_attack",None)
        if (self.commitment is None and self.post_context is None and entry is not None
                and entry.target==getattr(prefs,"target",None) and entry.kind in {"side","stomp"}):
            if (self._transfer_ready and self._context is not None and self._transfer_goal is not None
                    and self._transfer_goal.source_kind=="SWITCH"):
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

    def _transfer_offer(self,state,game,sim,forecast,prefs,ground):
        f=state["f"];target=getattr(prefs,"target",None)
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
        approach_only=bool(run.v.get("_approach_only")) if active else bool(side and self._transfer_goal is not None
            and self._transfer_goal.source_kind=="SWITCH")
        if approach_only:
            enemy=next((e for e in transfer.clappers(state) if e["iid"]==target),None)
            hp=(state.get("hero") or {}).get("pos") or ()
            ep=() if enemy is None else enemy.get("pos") or ()
            near=(len(hp)>=1 and len(ep)>=1 and type(hp[0]) in (int,float)
                  and type(ep[0]) in (int,float) and np.isfinite([hp[0],ep[0]]).all()
                  and abs(ep[0]-hp[0])<=self.runner.chains[transfer.PROGRAM].cfg["STOMP"]["jump_root"])
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
        rs=getattr(forecast,"rs",None)
        made=transfer.propose(self.runner,state,game,sim,target,ground,self._context[3],self._transfer_finished,self._transfer_goal,
                              **({"approach_only":True} if approach_only else {}))
        if made is None or made[0] is None:
            if active:self._recover((made[1].ended_reason if made is not None else None)
                                    or "rune transfer ended or target began a new move before real bounce",f)
            return None
        draft,plan,path,mask=made
        if plan.move in self._failed_hook_moves:return None
        current=None if rs is None else getattr(rs.trk,"now",{}).get(plan.iid)
        if current is None:
            if active:self._recover("rune transfer support unavailable",f)
            return None
        target_ta=None;target_move=None;conditional_contact=None
        try:
            goal=self._transfer_goal
            if goal is not None and goal.source_kind=="SWITCH" and not draft.run.v.get("_entry_source_confirmed"):
                if not self._transfer_source_matches(rs,goal):
                    raise GeometryUnavailable("tactical switch source instance unavailable or changed")
                draft.run.v["_entry_source_confirmed"]=True
            geo=B2Geometry(forecast,f,plan.move,current[2])
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
            attacking=transfer.control(next(e for e in transfer.clappers(state) if e["iid"]==plan.iid))[0] in transfer.AIR_ATTACK_STATES
            if attacking:
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
            elif approach_only or draft.run.link=="bounce_tail" or (draft.run.link=="air" and draft.run.v.get("approach_recipe")=="air_dash"):
                scan=geo.scan(path)
            # A selected strike keeps the existing target-contact contract:
            # this short path has no modeled pogo, so its future body overlap
            # must not cancel an already pressed downslash as a false failure.
            else:scan=geo.preflight(path)
        except GeometryUnavailable as exc:
            self._note("rune_transfer_unchecked",frame=f,reason=str(exc))
            if draft.run.link=="bounce_tail" and goal is not None:
                self._decline_source_tail(goal,state)
            if active:self._recover("rune transfer external step unchecked",f)
            return None
        if not scan.complete or scan.contacts:
            first=None if not scan.contacts else asdict(scan.contacts[0])
            self._note("rune_transfer_rejected",frame=f,first=first)
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
             "conditional_hit_check":conditional_contact is not None,"conditional_contact":conditional_contact,
             "checked_through":path.through,"phase":draft.run.link,"predicted_bounce":None,
             "handoff":("observed range or tactical boundary; ordinary side rows" if approach_only else
                        "real hit+bounce reopens tactical target knife; observed source hammer tail retained"),
             "safety_basis":"manual distance recipe; current external step only; no full-flight safety certificate"})

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
        if selected is not None and sent.chain_outcome=="sent" and selected.details.get("distance_vault"):
            if selected.stage=="manual_commitment":
                from .knife_chain_vault_native import manual_jump_watch
                self._jump_start=manual_jump_watch(selected,sent.frame)
                if self._jump_start is not None:self._jump_start.record_send(sent.target_frame,sent.desired_mask)
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
        return sent

    def before_send(self,*,frame,target,mask,flags,received_frame,dispatch_clock=None):
        selected=self._b2_selected
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
        source=self.commitment
        if source is not None and source["move"].family=="RUNE_TRANSFER" and self._press is not None:
            bound=self._transfer_target_moves.get(source["move"])
            if bound is not None:
                # A successful sent strike explicitly continued against this
                # observed destination attack. Keep its liability alongside
                # the original source, but do not ban a fresh counter to it.
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
