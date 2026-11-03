"""Opt-in manual air family inside the EXISTING B2 send/receipt/commit path.

Only this family's candidate availability suppresses the old slam script; ground
h2 remains available. No second keyboard owner or online action-tree search.
The table is a named unfitted probe, checked through predicted contact and the
existing N=2 short continuation policy;
actual target hit AND observed bounce hand back to ordinary full-scene planning.
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
             or getattr(self,"recovery",None) is not None or getattr(self,"post_context",None) is not None))

    @candidate_generation.setter
    def candidate_generation(self,value):self._candidate_enabled=bool(value)

    def reset(self,episode,*,start_frame=None):
        self._air_context=None;self._air_plan=None;self._air_finished=set()
        self._transfer_ready=False;self._transfer_finished=set();self._transfer_goal=None
        self._transfer_responsibility={}
        self._vault_ready=False
        self._vault_responsibility={}
        self._vault_origins={};self._vault_completed=set()
        super().reset(episode,start_frame=start_frame)
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

    def goal_preferences(self,state,prefs,*,handoff):
        """One destination before forecasting; critical/committed actions retain ownership."""
        goal=self._transfer_goal
        if (self.arm!="B" or goal is None or not handoff or self.commitment is not None or
                self.recovery is not None or self.post_context is not None or getattr(prefs,"want_bind",False)):
            self._transfer_ready=False
            return prefs
        enemies={e["iid"]:e for e in transfer.clappers(state)}
        target=enemies.get(goal.target);caster=enemies.get(goal.caster)
        active=self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM
        valid_caster=caster is not None and transfer.control(caster)[0] in {"Spell Antic","Cast 1","Cast 2","Idle","Walk"}
        spent=(goal.caster,goal.cast_fa) in self._transfer_finished
        if target is None or not valid_caster or (spent and not active):
            self._transfer_goal=None;self._transfer_ready=False
            if active:self._abandon("rune transfer no longer owns this observed cast")
            return prefs
        # The action table does not choose an enemy. It can only execute the
        # destination already selected by tactics, with that enemy's full prefs.
        if getattr(prefs,"target",None)!=goal.target:
            self._transfer_ready=False;return prefs
        # A destination is not keyboard ownership: a newly observed target
        # attack must still reach the existing ground/air attack adapters.
        self._transfer_ready=transfer.control(target)[0] in self.runner.chains[transfer.PROGRAM].cfg["target_states"]
        return replace(prefs)  # acknowledge handoff; preserve every tactical field

    def continuation_value_bound(self,prefs):return float("inf")

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

    def _continuations(self,path,sim,geo,move):
        """Reuse the B2 lower bound; no pre-contact target exemption after bounce."""
        from .knife_chain_post_actions import ordinary_post
        from .knife_chain_commitment import Continuation,FullContinuationScan,assess_continuations
        parent=replace(path,stage="commitment")
        ref=f"air:{move}:{path.through}";options=[];paths={}
        for kind in ("left_landing","right_landing"):
            p=ordinary_post(parent,sim.params,sim.terrain,kind=kind,profile=self.profile)
            paths[kind]=p
            options.append(Continuation(kind,kind,ref,geo.ref(p),
                p.through if p.end=="handback" else None,
                self.continuation_executable(kind,p),"pass",geo.scan(p)))
        def full(option):
            p=ordinary_post(parent,sim.params,sim.terrain,kind=option.kind,profile=self.profile,full=True)
            return FullContinuationScan(replace(geo.scan(p),path_ref=option.path_ref),p.through)
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
        if self.runner.run is not None and self.runner.run.chain==transfer.PROGRAM and self._air_context[1]["iid"]!=getattr(prefs,"target",None):
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

    def _transfer_offer(self,state,game,sim,forecast,prefs,ground):
        f=state["f"];target=getattr(prefs,"target",None)
        run=self.runner.run
        active=run is not None and run.chain==transfer.PROGRAM
        if active:target=run.v["iid"]  # the already-sent action keeps the same target through its real bounce
        if not self._transfer_ready and (run is None or run.chain!=transfer.PROGRAM):return None
        queued,_=self.queued_prefix(f,state)
        if queued is None or int(sim.prefix[0])!=queued:
            if active:self._recover("rune transfer actual queued prefix mismatch",f)
            return None
        rs=getattr(forecast,"rs",None)
        made=transfer.propose(self.runner,state,game,sim,target,ground,self._context[3],self._transfer_finished,self._transfer_goal)
        if made is None or made[0] is None:
            if active:self._recover("rune transfer ended or target began a new move before real bounce",f)
            return None
        draft,plan,path,mask=made
        if plan.move in self._failed_hook_moves:return None
        current=None if rs is None else getattr(rs.trk,"now",{}).get(plan.iid)
        if current is None:
            if active:self._recover("rune transfer support unavailable",f)
            return None
        try:scan=B2Geometry(forecast,f,plan.move,current[2]).preflight(path)
        except GeometryUnavailable as exc:
            self._note("rune_transfer_unchecked",frame=f,reason=str(exc))
            if active:self._recover("rune transfer external step unchecked",f)
            return None
        if not scan.complete or scan.contacts:
            first=None if not scan.contacts else asdict(scan.contacts[0])
            self._note("rune_transfer_rejected",frame=f,first=first)
            if active:self._recover("rune transfer external step blocked",f)
            return None
        goal=self._transfer_goal
        self._transfer_responsibility.setdefault(plan.move,(transfer.MoveInstance(plan.caster,plan.cast_fa,"CC_CAST"),
            None if goal is None else goal.cast_ta))
        return B2Offer("active" if active else "manual_commitment",path,draft,int(mask),0.,plan.move,
            {"manual_air":True,"rune_transfer":True,"caster":plan.caster,"cast_fa":plan.cast_fa,
             "checked_through":path.through,"phase":draft.run.link,"predicted_bounce":None,
             "handoff":"observed target DownSlash hit plus bounce; original vault exit",
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

    def summary(self):
        return {**super().summary(),"mode":"manual_air_probe","table":"manual_air+vault_near" if self.vault_enabled else "air_strike","tables":list(self.runner.chains),
                "online_search":False,"geometry_scope":("vault: current external step only, empirical skill; other air: contact path and N=2" if self.vault_enabled else "current/contact path plus existing N=2 continuations"),
                "post_bounce":("vault uses its observed original exit; other air hands back to ordinary planner" if self.vault_enabled else
                               "ordinary planner from actual hit+bounce; no frozen future tail")}
