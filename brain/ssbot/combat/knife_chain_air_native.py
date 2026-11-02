"""Opt-in manual air family inside the EXISTING B2 send/receipt/commit path.

Only this family's candidate availability suppresses the old slam script; ground
h2 remains available. No second keyboard owner or online action-tree search.
The table is a named unfitted probe, checked through predicted contact and the
existing N=2 short continuation policy;
actual target hit AND observed bounce hand back to ordinary full-scene planning.
"""
from dataclasses import asdict,replace
from pathlib import Path
import numpy as np
from .knife_chain_b2 import NativeChainB2,B2Offer
from .knife_chain_eval import Run,X
from .knife_chain_air import (AirAnchor,load_runner,entry_context,plan_entry,model_path,advance,complete_hf,render)
from .knife_chain_geometry import B2Geometry,GeometryUnavailable
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_nominal import logical_copy,NominalUnsupported


class NativeManualAirChain(NativeChainB2):
    manual_air=True
    @staticmethod
    def load_program(profile):
        if profile.fixed_hook or profile.fast_hook:
            raise ValueError("manual air family does not activate fixed/fast hook programs")
        return load_runner()

    @staticmethod
    def program_tables():return (Path(__file__).with_name("knife_chain_air_v01.json"),)

    @property
    def candidate_generation(self):
        return bool(getattr(self,"_candidate_enabled",False) and
            (getattr(self,"_air_context",None) is not None or getattr(self,"commitment",None) is not None
             or getattr(self,"recovery",None) is not None or getattr(self,"post_context",None) is not None))

    @candidate_generation.setter
    def candidate_generation(self,value):self._candidate_enabled=bool(value)

    def reset(self,episode,*,start_frame=None):
        self._air_context=None;self._air_plan=None;self._air_finished=set()
        super().reset(episode,start_frame=start_frame)

    def begin(self,state,history=()):
        super().begin(state,history)
        self._air_context=(entry_context(state,self._clock,self.runner) if self.arm=="B" and
            self.commitment is None and self.post_context is None else None)

    def continuation_value_bound(self,prefs):return float("inf")

    def _arm_hook_start(self,offer,send):pass  # this table has no CLAW

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
                predicted=(f+plan.contact_k-k if self._hit is None else None)
                bad=self._query(forecast,plan.move,path,contact_frame=predicted)
            except GeometryUnavailable as exc:
                self._air_finished.add(plan.move);self._recover("manual air current geometry unknown: "+str(exc),f);return None
            if bad:
                self._air_finished.add(plan.move);self._recover("manual air current external path blocked",f);return None
            return B2Offer("active",None,draft,int(mask),0.,plan.move,{"manual_air":True,"phase":draft.run.link})
        if self._air_context is None:return None
        try:
            made=plan_entry(self.runner,state,game,sim,self._air_context)
            if made is None:return None
            plan,commands,contact=made
            if plan.move in self._air_finished or plan.move in self._failed_hook_moves:return None
            # The current commitment ends at modeled bounce, not at a guessed
            # landing. Post-bounce commands must be selected from real STATE.
            path=model_path(sim,plan,commands[:contact-1],game,contact=contact)
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
        draft=self.runner.fork_empty(AirAnchor());draft.run=Run("air_strike","align",plan.variables())
        mask=advance(draft,plan,state,game)
        if mask is None:return None
        self._air_plan=plan
        return B2Offer("manual_commitment",path,draft,int(mask),0.,plan.move,
            {"manual_air":True,"predicted_bounce":plan.contact_frame,"phase":draft.run.link,
             "entry_k":plan.entry_k,"safety_basis":"fresh nominal path through modeled contact; unfitted manual table",
             "post_bounce":"N=2 short or one full exit; normal planner after real bounce",
             "continuations":asdict(exits),"plan":vars(plan)})

    def before_send(self,*,frame,target,mask,flags,received_frame,dispatch_clock=None):
        selected=self._b2_selected
        if (selected is not None and selected.details.get("manual_air") and int(mask)&B["A"]
                and self._press is None and type(received_frame) is int and received_frame>=target):
            self._air_finished.add(selected.move)
            return self._abort_hook_dispatch(selected,frame=frame,target=target,mask=mask,flags=flags,
                received_frame=received_frame,event="air_strike_send_veto",reason="manual air attack slot already observed")
        return super().before_send(frame=frame,target=target,mask=mask,flags=flags,
                                  received_frame=received_frame,dispatch_clock=dispatch_clock)

    def summary(self):
        return {**super().summary(),"mode":"manual_air_probe","table":"air_strike",
                "online_search":False,"geometry_scope":"current/contact path plus existing N=2 continuations",
                "post_bounce":"ordinary planner from actual hit+bounce; no frozen future tail"}
