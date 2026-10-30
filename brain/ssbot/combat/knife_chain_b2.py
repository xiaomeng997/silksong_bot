"""B2 chain candidates / in-flight bookkeeping inside the existing synchronous planner.

No keyboard, thread, separate controller or recursive search. The first choice is
conditional on the current table/h2 guard. Its real Run commits only AFTER the
existing transport succeeds. Actual hit+bounce observations release commitment;
all later suggestions compete normally. Unfitted conditions remain probe-only.
"""
from __future__ import annotations

from dataclasses import dataclass,asdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np
from ssbot.knowledge import kinematics as km
from .knife_chain_admission import AdmissionDecision,ConditionResult
from .knife_chain_candidates import NativeChainCandidates
from .knife_chain_native import NativeChainAudit,NativeChainAuditError
from .knife_chain_commitment import MoveInstance,TargetMoveAdmission,Continuation,assess_continuations,check_external_path
from .knife_chain_nominal import (NominalProfile,NominalUnsupported,compile_path,post_paths,logical_copy,is_committing,flag)
from .knife_chain_geometry import B2Geometry,GeometryUnavailable
from .knife_chain_eval import ChainObservationNotReady
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_budget import LearningBudget,LearningStop


@dataclass
class B2Offer:
    stage: str
    path: object
    draft: object
    mask: int
    value: float
    move: MoveInstance
    details: dict


class NativeChainB2(NativeChainCandidates):
    b2=True
    def __init__(self,*,runner_factory,probe_ref,journal=None,profile=None,arm="B",budget=None,trace_limit=2048):
        if arm not in {"A","B"}:raise ValueError("B2 arm must be A or B")
        self.profile=profile or NominalProfile();self.arm=arm;self.budget=budget
        self.candidate_generation=arm=="B"
        super().__init__(runner_factory=runner_factory,probe_ref=probe_ref,journal=journal,trace_limit=trace_limit)

    @classmethod
    def from_env(cls,*,journal):
        from .knife_chain_slam import load_runner
        batch=os.environ.get("SSBOT_FORUM_CHAIN_BATCH","")
        arm=os.environ.get("SSBOT_FORUM_CHAIN_ARM","")
        if not journal or not batch or arm not in {"A","B"}:
            raise ValueError("B2 needs journal, named batch and explicit A/B arm")
        profile=NominalProfile(short_frames=int(os.environ.get("SSBOT_FORUM_CHAIN_SHORT_FRAMES","12")))
        # Binding/compile once; changing source, program or config cannot silently
        # reset a previous budget under the same batch name/path.
        runner=load_runner()
        digest=hashlib.sha256()
        source=Path(__file__).resolve().parents[1]
        for f in sorted(source.rglob("*.py")):
            digest.update(str(f.relative_to(source)).encode());digest.update(f.read_bytes())
        table=Path(__file__).with_name("knife_chain_slam_v01.json")
        digest.update(table.read_bytes())
        knowledge=Path(__file__).resolve().parents[3]/"knowledge/1.0.30000"
        for f in sorted((knowledge/"enemies/forum").glob("*.npz")):
            digest.update(f.name.encode());digest.update(f.read_bytes())
        for f in sorted((knowledge/"kinematics").glob("hero*.json")):
            digest.update(f.name.encode());digest.update(f.read_bytes())
        from .attack_range import load_table
        from .are_types.clapper import SPEC
        if not load_table(spec=SPEC).meta.get("hammer_polygon_revision"):
            raise ValueError("B2 requires measured polygon hammer model in BOTH arms")
        digest.update(json.dumps(runner.cfg0,sort_keys=True,default=str).encode())
        digest.update(json.dumps(profile.__dict__,sort_keys=True).encode())
        path=os.environ.get("SSBOT_FORUM_CHAIN_BUDGET","")
        if not path:raise ValueError("B2 needs explicit shared SSBOT_FORUM_CHAIN_BUDGET path")
        budget=LearningBudget(path,batch=batch,revision=digest.hexdigest(),worker=str(Path(journal).resolve()))
        return cls(runner_factory=lambda:runner,probe_ref=os.environ.get("SSBOT_FORUM_CHAIN_PROBE",""),
                   journal=journal,profile=profile,arm=arm,budget=budget)

    def reset(self,episode,*,start_frame=None):
        super().reset(episode,start_frame=start_frame)
        self.commitment=None;self.post_context=None;self._b2_selected=None;self._b2_path=None
        self._press=None;self._accepted=None;self._hit=None;self._bounce_marker=False
        self._last_budget_f=None;self._budget_hp=None;self._kill_frame=None;self.learning_stop=None
        self._episode_start=start_frame
        self._budget_targets=set();self._budget_dead=set()
        self._post_seed=None;self._post_kind=None
        if self.budget is not None:self.budget.check()

    def rows(self,**kwargs):
        return None                 # never insert a short pulse + ordinary tail

    def _stop(self,reason,frame=None):
        frame=self.last_observed if frame is None else frame
        self.learning_stop=str(reason)
        try:
            if self.budget is not None:
                self.budget.observe(episode=self.episode,frame=frame or 0,arm=self.arm,fatal=str(reason))
        except LearningStop:pass
        self._note("b2_learning_stop",frame=frame,reason=str(reason))
        self.flush()
        raise LearningStop(str(reason))

    def observe_learning(self,state,*,kill_frame=None):
        f=state["f"]
        if self._last_budget_f is not None and f<=self._last_budget_f:return
        h=state.get("hero") or {};hp=h.get("health")
        if type(hp) is not int:self._stop("missing critical hero HP log",f)
        loss=0 if self._budget_hp is None else max(0,self._budget_hp-hp)
        self._budget_hp=hp;self._last_budget_f=f
        from .slam_play import CLAPPER
        for e in state.get("ents") or ():
            if e.get("type_key")==CLAPPER and not e.get("is_dead") and e.get("hp",0)>0:
                self._budget_targets.add(e["iid"])
        for ev in state.get("ev") or ():
            d=ev.get("d") or {}
            iid=d.get("ent") or d.get("iid")
            if ev.get("k")=="hit" and d.get("dead") and d.get("type_key")==CLAPPER:
                self._budget_targets.add(iid);self._budget_dead.add(iid)
                if self._budget_targets<=self._budget_dead:
                    ef=int(ev.get("f",f))
                    self._kill_frame=ef if self._kill_frame is None else min(self._kill_frame,ef)
                    self._note("b2_fight_end",frame=ef,source="actual final Clapper killing hit; inclusive")
        if kill_frame is not None:self._kill_frame=int(kill_frame) if self._kill_frame is None else min(self._kill_frame,int(kill_frame))
        tail=self._kill_frame is not None and f>self._kill_frame
        related=bool(self.commitment or self.post_context or (self.runner.run is not None and self.arm=="B"))
        if self.budget is not None:
            try:self.budget.observe(episode=self.episode,frame=f,arm=self.arm,hp_loss=loss,chain_related=related,
                                   tail=tail,fatal="death" if hp<=0 or flag(state,"dead") else None)
            except LearningStop as exc:
                self.learning_stop=str(exc);self._note("b2_learning_stop",frame=f,reason=str(exc));self.flush();raise
        if loss:self._note("b2_hp_loss",frame=f,hp=hp,loss=loss,tail=tail,chain_related=related)

    def observe(self,state):
        f=state["f"];previous=self.last_observed
        if previous is not None and f>previous+1:self._stop("missing critical STATE frames",f)
        # Budget is also fed by the harness before its lethal/clear early exits.
        self.observe_learning(state,kill_frame=self._kill_frame)
        prior_pending=dict(getattr(self,"_pending",{}))
        act=state.get("act") or {};target=act.get("target")
        if target in prior_pending and act.get("applied") is not None:
            if act.get("applied")!=target or (act.get("hf") or {}).get("desired")!=prior_pending[target]:
                self._stop("key application desync / missing desired log",f)
        if any(t<f-2 and t!=target for t in prior_pending):self._stop("missing critical application receipt",f)
        super().observe(state)
        if self.post_context is not None and f>self.post_context["bounce"]+8 and flag(state,"onGround"):
            self._note("b2_post_landed",frame=f)
            self.post_context=None;self._post_seed=None;self._post_kind=None
        c=self.commitment
        if c is None:return
        clip=str((state.get("hero",{}).get("anim") or {}).get("clip", ""))
        accepted=("DownSlash" in clip or flag(state,"downSpikeAntic") or flag(state,"downSpiking"))
        if self._press is not None and f>=self._press and accepted and self._accepted is None:
            self._accepted=f;self._note("b2_strike_accepted",frame=f,press=self._press)
        for ev in state.get("ev") or ():
            d=ev.get("d") or {};src=str(d.get("src") or "")
            if (self._press is not None and ev.get("k")=="hit" and (d.get("ent") or d.get("iid"))==c["move"].target_iid
                    and "DownSlash" in src and "Harpoon" not in src):
                ef=int(ev.get("f",f))
                if self._press<=ef<=f:self._hit=ef
        ints=(state.get("hero") or {}).get("cstate_int") or ()
        counter=int(ints[1]) if len(ints)>1 else 0
        marker=counter>0 or flag(state,"downSpikeBouncing") or flag(state,"downSpikeBouncingShort")
        if self._hit is not None and marker and f>=self._hit:
            self.post_context={**c,"bounce":f,"hit":self._hit,"press":self._press}
            self.commitment=None
            if self.runner.run is not None:self.runner.run.v["bounced"]=True
            self._post_seed=logical_copy(self.runner);self._post_kind=None
            self._note("b2_real_bounce_handback",frame=f,hit=self._hit,press=self._press,
                       source="target DownSlash hit plus observed bounce/counter",predicted=c["predicted_bounce"])
            return
        e=next((e for e in state.get("ents") or () if e.get("iid")==c["move"].target_iid),None)
        if e is None or e.get("is_dead") or e.get("hp",1)<=0:
            self._recover("target dead/absent",f);return
        from .slam_play import control
        st,tin=control(e)
        if st=="Slam Antic" and abs((self._clock-tin)-c["ta"])>3/60:
            self._recover("target started a new slam instance",f);return
        if self._press is not None and f>self._press+int(self.runner.cfg0.get("bounce_by",14)):
            self._note("b2_controller_defect",frame=f,reason="missed planned strike",press=self._press,accepted=self._accepted)
            self._recover("strike not accepted" if self._accepted is None else "planned strike missed / no real bounce",f)

    def _recover(self,reason,f):
        self._note("b2_recovery",frame=f,reason=reason,press=self._press,accepted=self._accepted,hit=self._hit)
        self.commitment=None;self.post_context=None;self._post_seed=None;self._post_kind=None
        self._abandon(reason)

    def _preview(self):
        if self._context is None:return None
        tick,sim,guard,bombs=self._context
        f,state,game,ground,accepting=tick
        if sim.fo!=f or sim.f!=f or len(sim.prefix)!=1:
            self._note("b2_unchecked",frame=f,reason="lagged/current model mismatch");return None
        receipt=self._receipts.get(f+1)
        if receipt is None or receipt!=int(sim.prefix[0]):
            self._note("b2_unchecked",frame=f,reason="queued prefix has no matching real receipt");return None
        from .knife_chain_history import HistView
        from .slam_play import clappers,control
        es=clappers(state)
        if len(es)!=1:return None
        hist=HistView(list(self._ticks),self._receipts,f,lag=self.runner.cfg0.get("lag",0))
        an=hist.antic(es[0]["iid"],"Slam Antic",())
        self.runner.anchor.hist=hist
        self.runner.anchor.external=self.runner.run is None and hist.complete_antic_receipts(an)
        if self.runner.run is None and control(es[0])[0]!="Slam Antic" and not self.runner.anchor.external:return None
        # Family-specific fork: share read-only history/model configuration,
        # fork all active mutable state. Generic evaluator preview stays intact.
        from .air_chain import ChainSim
        from .knife_chain_eval import ChainPreview
        draft=logical_copy(self.runner);draft.observation_cutoff=f
        model=ChainSim(sim.start.copy(),sim.prefix.copy(),sim.hold.copy(),sim.params,sim.terrain,sim.fo,sim.f)
        mask=draft.step(f,deepcopy(state),ground,accepting,t_game=game,sim=model,guard=deepcopy(guard),bombs=deepcopy(bombs))
        preview=ChainPreview(f,mask,draft) # first key f+2: actual information has >=2f lead
        if preview.mask is None or preview.draft.run is None:return None
        v=preview.draft.run.v
        if an is None or int(v["fa"])!=int(an["fa"]) or v["iid"]!=an["iid"]:
            self._note("b2_unchecked",frame=f,reason="h2 guard and observed antic identities differ");return None
        move=MoveInstance(int(v["iid"]),int(an["fa"]),"CC_SLAM")
        return preview,move

    @staticmethod
    def _endpoint(planner,path,prefs):
        c=.5*(path.box[-1,:2]+path.box[-1,2:]);w=prefs.weights
        risk=float(np.interp(c[0],prefs.risk_x,prefs.risk)) if len(prefs.risk_x) else 0.
        value=-float(w.get("stance",.6))*abs(c[0]-prefs.stance_x)-float(w.get("risk",3))*risk
        if path.flags[-1]&km.F_GROUND:value+=float(w.get("ground",.2))
        if prefs.boss_x is not None and (prefs.boss_x-c[0])*path.states[km.FACE,-1]>0:value+=float(w.get("face",.3))
        return float(value)

    @staticmethod
    def continuation_executable(kind,path):
        # A table branch can begin with neutral/down-hold while waiting for its
        # observed Slam-0 clock. Check the FIRST branch action at its own model
        # state, not demand a dash/direction on the bounce tick itself.
        if len(path.commands)<2:return False
        bit=B["DASH"] if kind=="dash_out" else B["L"] if kind=="left_landing" else B["R"]
        for i in range(1,len(path.latched)):
            m=int(path.latched[i]);prev=int(path.latched[i-1])
            if not m&bit:continue
            state=path.states[:,i];after=path.states[:,i+1]
            if kind=="dash_out":
                if prev&bit:continue
                return bool(state[km.DASH_CD]<=0 and (state[km.GROUND]>0 or state[km.AIRDASHED]<=0)
                            and any(int(path.states[km.MODE,j]) in {km.M_DASH,km.M_SPRINT}
                                    for j in range(i+1,min(i+5,path.states.shape[1]))))
            direction=-1 if kind=="left_landing" else 1
            return any(direction*(path.states[km.VX,j]-state[km.VX])>0 or direction*path.states[km.VX,j]>0
                       for j in range(i+1,min(i+5,path.states.shape[1])))
        return False

    def propose(self,planner,ws,start,hold,prefix,forecast,prefs,ctx):
        """One actual tick; active commitment bypasses ordinary-tail competition."""
        if self.arm!="B":return None
        if self.budget is not None:self.budget.check()
        try:bundle=self._preview()
        except ChainObservationNotReady as exc:
            self._note("b2_unchecked",frame=self.dispatch.frame,reason=str(exc));return None
        if bundle is None:
            if self.commitment:self._recover("current family program cannot continue",self.dispatch.frame)
            return None
        preview,move=bundle
        tick,sim,guard,bombs=self._context;f,state,game,ground,accepting=tick
        rs=getattr(forecast,"rs",None)
        observed=None if rs is None else getattr(rs.trk,"now",{}).get(move.target_iid)
        if observed is None:return None
        geo=B2Geometry(forecast,f,move,observed[2])
        if self.commitment is not None:
            if self.commitment["move"]!=move:
                self._recover("commitment instance mismatch",f);return None
            return B2Offer("active",None,preview.draft,int(preview.mask),0.,move,{"commitment":True})
        # Once real bounce was seen, NONE of the old target admission follows it.
        post=bool(self.post_context or preview.draft.run.v.get("bounced"))
        if post:
            offers=[]
            for kind in ("left_landing","right_landing","dash_out"):
                try:
                    continuing=(kind==self._post_kind and self.runner.run is not None)
                    seed=preview.draft if continuing else (self._post_seed or self.runner)
                    # Reuse the current read-only actual history, never a modeled
                    # future or a stale branch decision from the bounce tick.
                    seed=logical_copy(seed);seed.anchor.hist=self.runner.anchor.hist
                    path=compile_path(seed,state,sim,game,stage="continuation",first_mask=preview.mask,
                        profile=self.profile,branch=None if continuing else kind,known_press=self._press)
                    scan=geo.scan(path)
                    ok=check_external_path(scan,path_ref=geo.ref(path),target_move=move,first_frame=f,
                        last_frame=path.through,stage="continuation")
                    if ok.verdict!="pass":continue
                    real=preview.draft if continuing else path.first_draft
                    mask=int(path.offered[0])
                    offers.append(B2Offer("continuation",path,real,int(mask),self._endpoint(planner,path,prefs),move,{"kind":kind}))
                except (NominalUnsupported,GeometryUnavailable,ChainObservationNotReady) as exc:
                    self._note("b2_post_unchecked",frame=f,kind=kind,reason=str(exc))
            return max(offers,key=lambda o:o.value) if offers else None
        try:
            future=compile_path(preview.draft,state,sim,game,stage="commitment",first_mask=preview.mask,profile=self.profile)
            if not is_committing(preview.draft.run,self.profile):
                path=future.approach
                if path is None:raise NominalUnsupported("no next entry decision in nominal approach")
                scan=geo.scan(path)
                ok=check_external_path(scan,path_ref=geo.ref(path),target_move=move,first_frame=f,last_frame=path.through,stage="approach")
                preflight=geo.preflight(future)
                if ok.verdict!="pass" or preflight.contacts:
                    self._note("b2_approach_rejected",frame=f,path=ok.reason,preflight=[asdict(c) for c in preflight.contacts]);return None
                return B2Offer("approach",path,preview.draft,int(preview.mask),0.,move,
                               {"preflight_through":future.through,"next_decision":path.assumptions.get("future_decision")})
            admission=TargetMoveAdmission(move,f,future.through,
                self.runner.binding["table_digest"]+":"+preview.draft.run.lid,"pass")
            scan=geo.scan(future)
            ok=check_external_path(scan,path_ref=geo.ref(future),target_move=move,first_frame=f,last_frame=future.through,
                                   stage="commitment",admission=admission)
            if ok.verdict!="pass":
                self._note("b2_commit_rejected",frame=f,reason=ok.reason,contacts=[asdict(c) for c in ok.retained]);return None
            paths,errors=post_paths(future,sim.params,sim.terrain,profile=self.profile)
            bgeo=B2Geometry(forecast,f,move,observed[2])
            bounce_ref=f"{move}:{future.through}"
            opts=[]
            for kind,path in paths.items():
                short=bgeo.scan(path,min(self.profile.short_frames,len(path.commands)))
                opts.append(Continuation(kind,kind,bounce_ref,bgeo.ref(path),path.through,self.continuation_executable(kind,path),"pass",short))
            exits=assess_continuations(tuple(opts),target_move=move,bounce_state_ref=bounce_ref,bounce_frame=future.through,
                short_frames=self.profile.short_frames,full_scan=lambda o:bgeo.scan(paths[o.option_id]))
            details={"nominal_contact":future.contact_frame,"assumptions":future.assumptions,
                     "continuations":asdict(exits),"unavailable_branches":errors,"admission":asdict(admission)}
            if exits.verdict!="pass":
                self._note("b2_no_exit",frame=f,kinds=list(exits.qualifying_kinds),errors=errors,
                    reason=exits.reason,continuations=asdict(exits),no_repeat_downslash=True);return None
            # A guaranteed planned nail strike is valued in the SAME ordinary hit
            # unit (weights.hit), not by the known-zero static-body nh/hit_w.
            stance=max(self._endpoint(planner,p,prefs) for p in paths.values())
            value=float(prefs.weights.get("hit",10.))+stance
            return B2Offer("commitment",future,preview.draft,int(preview.mask),value,move,details)
        except (NominalUnsupported,GeometryUnavailable,ChainObservationNotReady) as exc:
            self._note("b2_unchecked",frame=f,reason=str(exc));return None

    @staticmethod
    def first_allowed(offer,prefix,start,ctx):
        from ssbot.core.primitives import Prim
        mask=offer.mask;before=int(prefix[-1]) if len(prefix) else 0
        known=0
        for v in B.values():known|=v
        if mask&~known or mask&B["L"] and mask&B["R"]:return False
        new=mask&~before;needs=[]
        if new&(B["L"]|B["R"]):needs.append(Prim.MOVE)
        if new&B["J"]:needs.append(Prim.JUMP if start[km.GROUND]>0 else Prim.GLIDE)
        if new&B["DASH"]:needs.append(Prim.DASH)
        if new&B["CLAW"]:needs.append(Prim.CLAWLINE)
        if new&B["A"]:needs.append(Prim.ATTACK_DOWN if mask&B["D"] else Prim.ATTACK_UP if mask&B["U"] else Prim.ATTACK_SIDE)
        if new&B["U"] and not mask&B["A"]:needs.append(Prim.INTERACT_UP)
        return all(bool(ctx.allowed_mask[int(p)]) for p in needs)

    def install(self,offer,planner,ordinary=None):
        """Planner's selected B2 candidate; no physical action is sent here."""
        from .planner import PlanResult
        f=self.dispatch.frame
        # The named probe remains visible; h2 guard use isn't relabelled fitted.
        adm=AdmissionDecision(offer.draft.run.lid,"unchecked",f,None,
                             (ConditionResult("legacy_h2_guard","unchecked","named B2 learning protocol"),))
        wire=self.dispatch.offer(offer.draft.run.lid,offer.mask,table_ref=self.runner.binding["table_digest"],admission=adm)
        self.register_row(0,wire,probe_ref=self.probe_ref)
        self._draft,self._offer,self._b2_selected=offer.draft,wire,offer
        self._projection=self._projection_pool=None
        p=offer.path
        cmd=np.array([offer.mask],np.int64) if p is None else p.offered.copy()
        res=PlanResult(offer.mask,0,"CHAIN B2 "+offer.stage+" "+offer.draft.run.lid,0,False,J=offer.value,V=True,
                       n=1,n_allowed=1,n_safe=1,cmd=cmd,path=None if p is None else p.box,
                       tail_ok=None,hits=1. if offer.stage=="commitment" else 0.)
        planner.prev_cmd=None if offer.stage!="continuation" else cmd.copy()
        planner.prev_name=res.name;planner.prev_tail_ok=False;planner.prev_esc_unsafe=False
        planner.last_info={"b2":{"stage":offer.stage,"move":vars(offer.move),"details":offer.details,
                                  "ordinary":None if ordinary is None else {"J":ordinary.J,"name":ordinary.name}},
                           "esc":{"b2":"empirical_lower_bound" if offer.stage=="commitment" else "not_a_commitment",
                                  "unsafe":False},"S":np.zeros(1,np.int64),"N":1}
        if planner.measurement_enabled:planner.measurement_result=res
        if p is not None:
            self._note("b2_nominal_path",frame=f,stage=offer.stage,move=vars(offer.move),
                through=p.through,commands=p.commands.tolist(),latched=p.latched.tolist(),
                box=p.box.tolist(),flags=p.flags.tolist(),check_flags=p.check_flags.tolist(),
                press=p.press_frame,conditional_contact=p.contact_frame,assumptions=p.assumptions,
                observations="private modeled future only; no actual application/contact credit")
        self._note("b2_selected",frame=f,stage=offer.stage,mask=offer.mask,move=vars(offer.move),
                   through=None if p is None else p.through,value=offer.value,details=offer.details)
        return res

    def before_send(self, *, frame, target, mask, flags, received_frame):
        if type(received_frame) is not int or received_frame>=target:
            self._stop("send deadline missed / missing current frame; no late action sent",frame)
        return super().before_send(frame=frame,target=target,mask=mask,flags=flags,received_frame=received_frame)

    def sent(self):
        selected=self._b2_selected
        sent=super().sent()
        committed=selected is not None and sent.chain_outcome=="sent"
        if committed:
            if selected.stage=="commitment":
                self.commitment={"move":selected.move,"origin":sent.frame,"ta":self.runner.run.v["ta"],
                    "predicted_bounce":selected.path.contact_frame}
                self._press=self._accepted=self._hit=None
            if selected.stage=="continuation":self._post_kind=selected.details["kind"]
            if selected.mask&(B["D"]|B["A"])==(B["D"]|B["A"]):
                prev=self._receipts.get(sent.target_frame-1,0)
                if not prev&B["A"] and self.commitment:self._press=sent.target_frame
        elif self.commitment is not None:
            self._recover("final owner/keys overridden",sent.frame)
        elif self.post_context is not None:
            self._post_kind=None
        self._b2_selected=None
        return sent

    def summary(self):
        return {**super().summary(),"mode":"b2_probe","arm":self.arm,"candidate_generation":self.candidate_generation,
                "projection":"nominal_chain_program","commitment":None if self.commitment is None else
                {**self.commitment,"move":vars(self.commitment["move"])},
                "post_context":None if self.post_context is None else {**self.post_context,"move":vars(self.post_context["move"])},
                "learning_stop":self.learning_stop,"budget":None if self.budget is None else self.budget.state,
                "live_ready":False}
