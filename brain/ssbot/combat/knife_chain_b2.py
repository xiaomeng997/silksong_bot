"""B2 chain candidates / in-flight bookkeeping inside the existing synchronous planner.

No keyboard, thread, separate controller or recursive search. The first choice is
conditional on the current table/h2 guard. Its real Run commits only AFTER the
existing transport succeeds. Actual hit+bounce observations release commitment;
all later suggestions compete normally. Unfitted conditions remain probe-only.
"""
from __future__ import annotations

from dataclasses import dataclass,asdict
from collections import Counter
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
from .knife_chain_receipts import Opt1ReceiptMixin
from .knife_chain_commitment import MoveInstance,TargetMoveAdmission,Continuation,assess_continuations,check_external_path
from .knife_chain_nominal import (NominalProfile,NominalUnsupported,compile_path,post_paths,logical_copy,is_committing,flag)
from .knife_chain_geometry import B2Geometry,GeometryUnavailable
from .knife_chain_eval import ChainObservationNotReady
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_budget import LearningBudget,LearningStop,LOW_HP_POLICY


def _fresh_downslash_start(state, previous):
    """A new observed downward swing, never the old clip persisting after a key."""
    if previous is None or previous.get("f") != state["f"]-1:return False
    def down(s):
        h=s.get("hero") or {};clip=(h.get("anim") or {}).get("clip")
        return (isinstance(clip,str) and "DownSlash" in clip) or flag(s,"downSpikeAntic") or flag(s,"downSpiking")
    if not down(state):return False
    old=previous.get("hero") or {};new=state.get("hero") or {}
    old_clip=(old.get("anim") or {}).get("clip")
    if not down(previous) and isinstance(old_clip,str) and old_clip:return True
    a=old.get("tm") or {};b=new.get("tm") or {}
    values=(a.get("atk_cd"),b.get("atk_cd"),a.get("atk_t"),b.get("atk_t"))
    if not all(type(v) in (int,float) and np.isfinite(v) for v in values):return False
    cd0,cd1,t0,t1=values
    return cd1>cd0+1e-6 and t1<t0-1e-6


@dataclass
class B2Offer:
    stage: str
    path: object
    draft: object
    mask: int
    value: float
    move: MoveInstance
    details: dict
    proposal_ms: float | None = None


class NativeChainB2(Opt1ReceiptMixin,NativeChainCandidates):
    b2=True
    require_send_clock=False  # direct offline transaction fixtures; from_env requires it
    def __init__(self,*,runner_factory,probe_ref,journal=None,profile=None,arm="B",budget=None,trace_limit=2048):
        if arm not in {"A","B"}:raise ValueError("B2 arm must be A or B")
        self.profile=profile or NominalProfile();self.arm=arm;self.budget=budget
        self.candidate_generation=arm=="B"
        from .knife_chain_eval_fast import bind_slam_runner
        super().__init__(runner_factory=lambda:bind_slam_runner(runner_factory()),probe_ref=probe_ref,journal=journal,trace_limit=trace_limit)

    @classmethod
    def from_env(cls,*,journal):
        from .knife_chain_slam import load_runner
        batch=os.environ.get("SSBOT_FORUM_CHAIN_BATCH","")
        arm=os.environ.get("SSBOT_FORUM_CHAIN_ARM","")
        if not journal or not batch or arm not in {"A","B"}:
            raise ValueError("B2 needs journal, named batch and explicit A/B arm")
        fast=os.environ.get("SSBOT_FORUM_CHAIN_FAST_HOOK","0").strip()
        if fast not in {"0","1"}:raise ValueError("invalid SSBOT_FORUM_CHAIN_FAST_HOOK")
        fixed=os.environ.get("SSBOT_FORUM_CHAIN_FIXED_HOOK","0").strip()
        if fixed not in {"0","1"}:raise ValueError("invalid SSBOT_FORUM_CHAIN_FIXED_HOOK")
        profile=NominalProfile(short_frames=int(os.environ.get("SSBOT_FORUM_CHAIN_SHORT_FRAMES","12")),fast_hook=fast=="1",fixed_hook=fixed=="1")
        # Binding/compile once; changing source, program or config cannot silently
        # reset a previous budget under the same batch name/path.
        runner=cls.load_program(profile)
        digest=hashlib.sha256()
        source=Path(__file__).resolve().parents[1]
        for f in sorted(source.rglob("*.py")):
            digest.update(str(f.relative_to(source)).encode());digest.update(f.read_bytes())
        for table in cls.program_tables():digest.update(table.read_bytes())
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
        from .observed_slam import revision_fields
        digest.update(json.dumps(revision_fields(),sort_keys=True).encode())
        # Optional observation and utility have distinct cost/selection profiles;
        # never mix their on/off configurations under one batch ledger.
        digest.update(json.dumps({"scene_field_shadow": os.environ.get(
            "SSBOT_FORUM_SCENE_FIELD_SHADOW", "0").strip() == "1", "scene_field_shadow_schema": 2,
            "scene_field_rank": os.environ.get("SSBOT_FORUM_SCENE_FIELD_RANK","0").strip()=="1",
            "scene_field_weight_hits": float(os.environ.get("SSBOT_FORUM_SCENE_FIELD_WEIGHT_HITS","1.0")),
            "scene_field_rank_schema": 1,
            "remaining_hp_quit": int(os.environ.get("SSBOT_FORUM_REMAINING_HP_QUIT","0"))},
            sort_keys=True).encode())
        path=os.environ.get("SSBOT_FORUM_CHAIN_BUDGET","")
        if not path:raise ValueError("B2 needs explicit shared SSBOT_FORUM_CHAIN_BUDGET path")
        budget=LearningBudget(path,batch=batch,revision=digest.hexdigest(),worker=str(Path(journal).resolve()),policy=LOW_HP_POLICY)
        instance=cls(runner_factory=lambda:runner,probe_ref=os.environ.get("SSBOT_FORUM_CHAIN_PROBE",""),
                     journal=journal,profile=profile,arm=arm,budget=budget)
        instance.require_send_clock=True
        return instance

    @staticmethod
    def load_program(profile):
        from .knife_chain_slam import load_runner
        return load_runner(fixed_hook=True) if profile.fixed_hook else load_runner()

    @staticmethod
    def program_tables():
        return (Path(__file__).with_name("knife_chain_slam_v01.json"),
                Path(__file__).with_name("knife_chain_fixed_hook_v1.json"))

    def reset(self,episode,*,start_frame=None):
        super().reset(episode,start_frame=start_frame)
        self.commitment=None;self.post_context=None;self._b2_selected=None;self._b2_path=None
        self._press=None;self._accepted=None;self._hit=None;self._bounce_marker=False
        self._last_budget_f=None;self._budget_hp=None;self._kill_frame=None;self.learning_stop=None
        self._episode_start=start_frame
        self.exit_transition=False;self._exit_scene_frame=None
        self._budget_targets=set();self._budget_dead=set()
        self._application={};self._late_bound_targets=set();self._last_matching_report=None;self._actual_state=None;self.recovery=None
        self._post_seed=None;self._post_kind=None
        self._committed_future=None
        self._post_keys={};self._post_key_move=None;self._post_prepare_cursor=0
        self._proposal_started=None;self._receipt_counts=Counter();self._last_no_candidate=None
        self._hook_start=None;self._failed_hook_moves=set()
        self._failure_exposures=[];self._jump_start=None;self.policy_gate_reason=None
        self._vetoed_preparation=None
        self._fixed_hook_mode=self.arm=="B" and self.profile.fixed_hook
        self.runner.anchor.fixed_hook_enabled=self._fixed_hook_mode
        self._fixed_jump_sent_for=None
        self._fast_j_mode=self.arm=="B" and self.profile.fast_hook and not self.profile.fixed_hook
        self._fast_j_pending_commit=None;self._fast_j_commit=None;self._fast_j_sent=None;self._last_c5_calls=None
        self.runner.anchor.b2_strict_observations=self.arm=="B"
        if self.budget is not None:self.budget.check()

    def _note(self,event,**data):
        started=getattr(self,"_proposal_started",None)
        if event.startswith("b2_") and started is not None:
            # Cumulative time to this event, not an exclusive child-stage cost.
            data.setdefault("ms",(time.perf_counter()-started)*1000.)
            data.setdefault("timing_scope","proposal_elapsed_to_event")
        return super()._note(event,**data)

    def _receipt_note(self,kind,frame,**data):
        self._receipt_counts[kind]+=1
        self._note("b2_receipt",frame=frame,kind=kind,**data,
                   scope="pending chain command resolution; not hero action acceptance")

    def _no_candidate(self,reason,*,frame=None,state=None):
        f=self.dispatch.frame if frame is None else frame
        if state is None:state=self._actual_state or {}
        key=(f,reason)
        if self._last_no_candidate==key:return
        self._last_no_candidate=key
        from .slam_play import clappers,control
        antic=[]
        for e in clappers(state):
            st,tin=control(e)
            if st=="Slam Antic":
                # Do not infer an unseen entry from state time. Known fa is
                # supplied only by a causal history observation.
                fa=None
                hist=getattr(self.runner.anchor,"hist",None)
                if hist is not None:
                    seen=hist.antic(e["iid"],"Slam Antic",())
                    if seen is not None:fa=seen["fa"]
                antic.append({"iid":e["iid"],"fa":fa,"observed_state":st,"state_time":tin})
        self._note("b2_no_candidate",frame=f,reason=reason,antics=antic,
                   observed_frame=state.get("f"),scope="current observation/history only")

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
        scene=(state.get("game") or {}).get("scene")
        # A confirmed pause alone is NOT permission to ignore combat HP. First
        # observe the actual Quit_To_Menu scene, then admit only menu/unloaded
        # frames at/after that boundary. Unknown battle frames still hard-stop.
        if self.exit_transition and scene=="Quit_To_Menu":self._exit_scene_frame=f
        if type(hp) is not int:
            left=(scene in {"Quit_To_Menu","Menu_Title"} or (scene in {None,""} and not h))
            if (self.exit_transition and self._exit_scene_frame is not None and
                    f>=self._exit_scene_frame and left):
                self._last_budget_f=f
                self._note("b2_exit_frame_no_hp",frame=f,scene=scene,exit_scene_frame=self._exit_scene_frame,
                           scope="confirmed real-quit scene transition; no combat HP/loss inferred")
                return
            self._stop("missing critical hero HP log",f)
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
        for exposure in self._failure_exposures:exposure.observe(state,game_time=self._clock)
        exposed=[x for x in self._failure_exposures if x.active(f)]
        residual=getattr(self,"residual_context",lambda:None)()
        related=bool(exposed or self.commitment or self.post_context or self.recovery or residual or (self.runner.run is not None and self.arm=="B"))
        if loss:
            sources=[]
            for ev in state.get("ev") or ():
                d=ev.get("d") or {}
                if (ev.get("k")=="damage" and ev.get("f",f)==f and
                        d.get("can_take",True) and not d.get("invuln")):
                    source=d.get("source") or d.get("src")
                    if source is not None:sources.append(str(source))
            phase=("recovery_after_failure" if exposed else "commitment" if self.commitment is not None else "post" if self.post_context is not None
                   else "recovery" if self.recovery is not None else "residual" if residual else "approach" if related else "none")
            # Preserve the HP fact before any fatal/legacy stop. Under the new
            # policy low HP requests Q1 pause/real quit in the normal supervisor.
            self._note("b2_hp_loss",frame=f,hp=hp,loss=loss,tail=tail,chain_related=related,phase=phase,
                       failure_exposure=[x.as_dict() for x in exposed],sources=sorted(set(sources)) or ["unknown"],
                       residual_context=residual,
                       source_scope="same-frame eligible damage-call candidates; no predicted/near-frame attribution")
        if self.budget is not None:
            try:self.budget.observe(episode=self.episode,frame=f,arm=self.arm,hp_loss=loss,chain_related=related,
                                   tail=tail,fatal="death" if hp<=0 or flag(state,"dead") else None)
            except LearningStop as exc:
                self.learning_stop=str(exc);self._note("b2_learning_stop",frame=f,reason=str(exc));self.flush();raise


    # _observe_application: the shared user Opt1 criterion (knife_chain_receipts.Opt1ReceiptMixin).


    def queued_prefix(self,frame,state):
        """Desired prefix from our send, or known held desired if no action queued.

        Neither kind proves a HoldFilter latch, an accepted attack or a bounce.
        """
        wanted=self._receipts.get(frame+1)
        if wanted is not None:return int(wanted),"queued_successful_send"
        act=state.get("act") or {};t=act.get("target");a=act.get("applied")
        desired=(act.get("hf") or {}).get("desired")
        if (type(t) is int and type(a) is int and type(desired) is int and
                t<=a<=frame and a<=t+2 and self._receipts.get(t)==desired):
            return desired,"held_observed_desired_no_queued_send"
        return None,"unknown_queued_or_held_desired"

    @staticmethod
    def _hook_in_flight(state):
        h=(state or {}).get("hero") or {}
        clip=str((h.get("anim") or {}).get("clip", ""))
        return "harpoon" in clip.lower() and not bool(h.get("hero_accepting_input",False))

    def _arm_hook_start(self,offer,send):
        # Only the already checked commitment path declares the window. Missing
        # its keys never moves the window or permits a retry of the same slam.
        path=offer.path
        if offer.stage=="fixed_commitment":
            cs=offer.draft.run.v["cs"];targets=(cs.f_press,cs.f_press+1)
        else:targets=tuple(path.origin+i+1 for i,m in enumerate(path.commands) if int(m)&B["CLAW"])
        self._hook_start=None
        if not targets:return
        self._hook_start={"move":offer.move,"origin":send.frame,"targets":targets,
                          "sent_targets":set(),"seen_frame":None}
        self._note("b2_hook_start_expected",frame=send.frame,move=vars(offer.move),targets=list(targets),
                   source="empirical fixed table; no model certificate" if offer.stage=="fixed_commitment" else "checked commitment nominal commands; keys only, not accepted hook")

    def _observe_hook_start(self,state):
        watch=self._hook_start
        if (watch is None or self.commitment is None or watch["move"]!=self.commitment["move"] or
                not watch["sent_targets"] or watch["seen_frame"] is not None):return
        f=state["f"];clip=str(((state.get("hero") or {}).get("anim") or {}).get("clip", ""))
        if f>=min(watch["sent_targets"]) and "harpoon" in clip.lower():
            watch["seen_frame"]=f
            self._note("b2_hook_start_seen",frame=f,move=vars(watch["move"]),clip=clip,
                       source="actual Harpoon animation only; no strike/bounce credit")

    def _check_hook_start(self,frame):
        # Called BEFORE preview can advance its planned clock into lock/strike.
        watch=self._hook_start
        if watch is None:return False
        if self.commitment is None or watch["move"]!=self.commitment["move"]:
            self._hook_start=None;return False
        if watch["seen_frame"] is not None:return False
        reason=None
        if not watch["sent_targets"]:
            if frame+2>max(watch["targets"]):
                reason="planned hook window elapsed without successful CLAW send"
        elif frame>max(watch["sent_targets"])+4:
            reason="sent CLAW had no observed Harpoon within four-frame upper bound"
        if reason is None:return False
        self._failed_hook_moves.add(watch["move"])
        self._note("b2_controller_defect",frame=frame,reason=reason,move=vars(watch["move"]),
                   planned_targets=list(watch["targets"]),sent_targets=sorted(watch["sent_targets"]),
                   hook_observed=False,no_retry_same_move=True)
        self._recover(reason,frame)
        return True

    def observe(self,state):
        f=state["f"];previous=self.last_observed
        if previous is not None and f>previous+1:self._stop("missing critical STATE frames",f)
        # Budget is also fed by the harness before its lethal/clear early exits.
        self.observe_learning(state,kill_frame=self._kill_frame)
        previous_state=self._actual_state
        self._actual_state=state
        self._observe_application(state)
        self._observe_hook_start(state)
        if self._jump_start is not None and self._jump_start.observe(state):
            self._note("b2_jump_start_seen",frame=f,move=vars(self._jump_start.move),
                sent_targets=sorted(self._jump_start.sent_targets),source="actual observed airborne after own J")
        unresolved=self._pending
        self._pending={}  # opt1 owns this audit; do not inherit the old2-frame abandon
        try:super().observe(state)
        finally:self._pending=unresolved
        if self.post_context is not None and self.post_context.get("simple_wait"):
            target=next((e for e in state.get("ents") or () if e.get("iid")==self.post_context["move"].target_iid),None)
            if target is not None and (target.get("is_dead") or target.get("hp",1)<=0):
                self._note("b2_fixed_wait_handoff",frame=f,released=False,reason="observed target death")
                self.post_context=None;self._post_seed=None;self._post_kind=None;self._abandon("observed target death")
        if self.post_context is not None and not self.post_context.get("simple_wait") and f>self.post_context["bounce"]+8 and flag(state,"onGround"):
            self._note("b2_post_landed",frame=f)
            self.post_context=None;self._post_seed=None;self._post_kind=None
        if self.recovery is not None:
            if self._hook_in_flight(state):self.recovery["hook_seen"]=True
            waiting=(not self.recovery.get("hook_seen",False) and f<=self.recovery.get("uncertain_until",-1))
            if not self._hook_in_flight(state) and not waiting:
                self._note("b2_hook_recovery_handoff",frame=f,reason="observed hook ended / supported interrupted state")
                self.recovery=None
            elif f>self.recovery["first"]+self.profile.max_frames:
                self._stop("hook recovery exceeded existing nominal max_frames without observed control return",f)
        c=self.commitment
        if c is None:return
        from .knife_chain_jump import grounded_strike
        if self._press is not None and grounded_strike(state,self._press):
            self._note("b2_controller_defect",frame=f,reason="planned downslash became grounded Slash",move=vars(c["move"]))
            self._recover("planned downslash became grounded Slash",f);return
        accepted=_fresh_downslash_start(state,previous_state)
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
            self.post_context={**c,"bounce":f,"hit":self._hit,"press":self._press,"simple_wait":self._fixed_hook_mode}
            self.commitment=None;self._hook_start=None;self._jump_start=None;self._committed_future=None
            self._fast_j_pending_commit=None;self._fast_j_commit=None;self._fast_j_sent=None
            if self.runner.run is not None:
                self.runner.run.v["bounced"]=True
                if self._fixed_hook_mode and self.runner.run.chain=="slam_jump":self.runner.run.link="wait"
            self._post_seed=None if self._fixed_hook_mode else logical_copy(self.runner);self._post_kind=None
            self._note("b2_simple_bounce_wait" if self._fixed_hook_mode else "b2_real_bounce_handback",frame=f,hit=self._hit,press=self._press,
                       source="target DownSlash hit plus observed bounce/counter",predicted=c["predicted_bounce"])
            return
        e=next((e for e in state.get("ents") or () if e.get("iid")==c["move"].target_iid),None)
        if e is None or e.get("is_dead") or e.get("hp",1)<=0:
            self._recover("target dead/absent",f);return
        from .slam_play import control
        st,tin=control(e)
        # A transfer's origin is an approach, not this enemy's slam origin.
        # Its adapter binds/checks the actual target attack instance separately.
        if c["move"].family!="RUNE_TRANSFER" and st=="Slam Antic" and abs((self._clock-tin)-c["ta"])>3/60:
            self._recover("target started a new slam instance",f);return
        if self._press is not None and f>self._press+int(self.runner.cfg0.get("bounce_by",14)):
            self._note("b2_controller_defect",frame=f,reason="missed planned strike",press=self._press,accepted=self._accepted)
            self._recover("strike not accepted" if self._accepted is None else "planned strike missed / no real bounce",f)


    def _recover(self,reason,f):
        self._note("b2_recovery",frame=f,reason=reason,press=self._press,accepted=self._accepted,hit=self._hit)
        source=self.commitment
        old_move=None if source is None else source["move"]
        if source is not None:
            exposure=self._failure_exposure(old_move,source.get("responsibility_origin",source["origin"]),f,source.get("ta"))
            if self._actual_state is not None:exposure.observe(self._actual_state,game_time=self._clock)
            self._failure_exposures.append(exposure)
            self._failed_hook_moves.add(old_move)
            self._note("b2_failure_exposure",frame=f,exposure=exposure.as_dict())
        self._jump_start=None
        pending_hook=(self._hook_start is not None and bool(self._hook_start["sent_targets"]) and
                      self._hook_start["seen_frame"] is None)
        if self._hook_in_flight(self._actual_state) or pending_hook:
            self.recovery={"first":f,"reason":reason,"move":old_move,
                "hook_seen":self._hook_in_flight(self._actual_state),
                "uncertain_until":max(self._hook_start["sent_targets"])+4 if pending_hook else -1}
            self._note("b2_hook_recovery_enter",frame=f,reason=reason,action="release/wait until observed hook end",path="unchecked")
        self.commitment=None;self.post_context=None;self._post_seed=None;self._post_kind=None
        self._committed_future=None
        self._hook_start=None
        self._fast_j_pending_commit=None;self._fast_j_commit=None;self._fast_j_sent=None
        self._post_keys.clear();self._post_key_move=None
        self._abandon(reason)

    def _failure_exposure(self,move,origin,failed,ta):
        from .knife_chain_failure import FailureExposure
        return FailureExposure(move,origin,failed,ta)


    def _prepare_tick_state(self,state):
        # Trusted Slam primitives only READ actual STATEs during this synchronous
        # call. Historical rows still own their snapshot; modeled futures below
        # copy every lane they mutate, never the whole oracle debug payload.
        return state

    def _preview(self,fast=None):
        if self._context is None:
            self._no_candidate("no current model context");return None
        tick,sim,guard,bombs=self._context
        f,state,game,ground,accepting=tick
        if sim.fo!=f or sim.f!=f or len(sim.prefix)!=1:
            self._note("b2_unchecked",frame=f,reason="lagged/current model mismatch")
            self._no_candidate("lagged/current model mismatch",frame=f,state=state);return None
        receipt,source=self.queued_prefix(f,state)
        if receipt is None:
            self._note("b2_unchecked",frame=f,reason=source)
            self._no_candidate(source,frame=f,state=state);return None
        if receipt!=int(sim.prefix[0]):
            from .air_chain import ChainSim
            sim=ChainSim(sim.start, np.array([receipt],np.int64),sim.hold,sim.params,sim.terrain,sim.fo,sim.f)
            self._context=(tick,sim,guard,bombs)
            self._note("b2_prefix_rebased",frame=f,source=source,desired=receipt)
        elif source!="queued_successful_send":self._note("b2_prefix_held",frame=f,source=source,desired=receipt)
        from .knife_chain_history import HistView
        from .slam_play import clappers,control
        es=clappers(state)
        if len(es)!=1:
            self._no_candidate("single live Clapper scope" if es else "no live Clapper",frame=f,state=state);return None
        hist=HistView(list(self._ticks),self._receipts,f,lag=self.runner.cfg0.get("lag",0),strict_pogo=self.arm=="B")
        an=hist.antic(es[0]["iid"],"Slam Antic",())
        if an is not None and MoveInstance(int(an["iid"]),int(an["fa"]),"CC_SLAM") in self._failed_hook_moves:
            self._no_candidate("planned hook failed for this Move; no automatic retry",frame=f,state=state)
            return None
        self.runner.anchor.hist=hist
        self.runner.anchor.external=self.runner.run is None and hist.complete_antic_receipts(an)
        if self.runner.run is None and control(es[0])[0]!="Slam Antic" and not self.runner.anchor.external:
            self._no_candidate("no active Run or traceable external antic entry",frame=f,state=state);return None
        # Family-specific fork: share read-only history/model configuration,
        # fork all active mutable state. Generic evaluator preview stays intact.
        from .air_chain import ChainSim
        from .knife_chain_eval import ChainPreview
        draft=logical_copy(self.runner);draft.observation_cutoff=f
        draft.anchor.fixed_release=None
        model=ChainSim(sim.start.copy(),sim.prefix.copy(),sim.hold.copy(),sim.params,sim.terrain,sim.fo,sim.f)
        from .knife_chain_cs_cache import exact_cs_step
        calls=[] if self._fast_j_mode else None
        if self._fast_j_mode:
            draft.anchor.b2_fast_j=fast;draft.anchor.b2_c5_calls=calls
            pending=self._fast_j_sent
            draft.anchor.b2_c5_catchup=(pending["move"] if fast is None and pending is not None and
                pending["deferred"] is None and f>pending["frame"] and self.commitment is not None and
                pending["move"]==self.commitment["move"] else None)
        try:
            with exact_cs_step(draft.anchor,enabled=bool(draft.cfg0.get("CLAWSTRIKE")) and control(es[0])[0]=="Slam Antic") as cache:
                mask=draft.step(f,state,ground,accepting,t_game=game,sim=model,guard=deepcopy(guard),bombs=deepcopy(bombs))
        finally:
            if self._fast_j_mode:
                draft.anchor.b2_fast_j=None;draft.anchor.b2_c5_calls=None;draft.anchor.b2_c5_catchup=None
        self._last_c5_calls=calls
        if cache is not None:
            self._note("b2_cs_exact_step_cache",frame=f,**cache.stats())
        preview=ChainPreview(f,mask,draft) # first key f+2: actual information has >=2f lead
        if preview.mask is None or preview.draft.run is None:
            if self.post_context is not None and self.post_context.get("simple_wait"):
                release=getattr(draft.anchor,"fixed_release",None)
                self._note("b2_fixed_wait_handoff",frame=f,move=vars(self.post_context["move"]),
                           released=release is not None,observed_release=release,
                           reason="Recover plus two new physics steps" if release else "table ended/interrupted; no release certificate")
                self.post_context=None;self._post_seed=None;self._post_kind=None;self.runner=draft
            self._no_candidate("family program offered no current action",frame=f,state=state);return None
        v=preview.draft.run.v
        if "_b2_entry_distance" not in v:
            distance=v.get("x_start")
            if distance is None and self.runner.run is None:
                from .slam_play import hero_x
                h=state.get("hero") or {}
                if (h.get("pos") or h.get("box")) and es[0].get("pos"):
                    distance=abs(hero_x(state)-float(es[0]["pos"][0]))
            v["_b2_entry_distance"]=None if distance is None else abs(float(distance))
            v["_b2_entry_distance_frame"]=f
        if an is None or int(v["fa"])!=int(an["fa"]) or v["iid"]!=an["iid"]:
            self._note("b2_unchecked",frame=f,reason="h2 guard and observed antic identities differ")
            self._no_candidate("h2 guard and observed antic identities differ",frame=f,state=state);return None
        move=MoveInstance(int(v["iid"]),int(an["fa"]),"CC_SLAM")
        return preview,move

    @staticmethod
    def _endpoint(planner,path,prefs):
        c=.5*(path.box[-1,:2]+path.box[-1,2:]);w=prefs.weights
        risk=float(np.interp(c[0],prefs.risk_x,prefs.risk)) if len(prefs.risk_x) else 0.
        value=-float(w.get("stance",.6))*abs(c[0]-prefs.stance_x)-float(w.get("risk",3))*risk
        if path.flags[-1]&km.F_GROUND:value+=float(w.get("ground",.2))
        if prefs.boss_x is not None and (prefs.boss_x-c[0])*path.states[km.FACE,-1]>0:value+=float(w.get("face",.3))
        field=getattr(planner,"scene_field_values",None)
        if field is not None:value+=field.path_bonus(path,prefs)
        return float(value)

    def continuation_value_bound(self,prefs):
        # Endpoint score is -stance*distance -risk*risk(x) +ground +facing.
        # With a nonnegative stance coefficient, dropping that nonpositive
        # term and taking optimistic risk/boolean terms is a true upper bound.
        # No geometry/admission result or endpoint position is reused.
        import math
        if self.post_context is None or self.commitment is not None or self.recovery is not None or self.post_context.get("simple_wait"):
            return math.inf
        w=prefs.weights
        stance=float(w.get("stance",.6));rw=float(w.get("risk",3.))
        ground=float(w.get("ground",.2));face=float(w.get("face",.3))
        if stance<0 or not all(math.isfinite(v) for v in (stance,rw,ground,face)):return math.inf
        risk=np.asarray(prefs.risk,float) if len(prefs.risk_x) else np.array([0.])
        if not risk.size or not np.isfinite(risk).all():return math.inf
        rv=float(risk.min() if rw>=0 else risk.max())
        return math.nextafter(-rw*rv+max(0.,ground)+max(0.,face),math.inf)

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

    def _post_cache_for(self,move):
        if self._post_key_move!=move:
            self._post_keys.clear();self._post_key_move=move;self._post_prepare_cursor=0

    def _remember_post_keys(self,path,kind,move,frame):
        from .knife_chain_post import PostKeys
        self._post_cache_for(move)
        try:
            self._post_keys[kind]=PostKeys.from_path(path,move=move,kind=kind,source_frame=frame,
                table_digest=self.runner.binding["table_digest"],profile=self.profile)
        except NominalUnsupported:return
        self._note("b2_post_keys_prepared",frame=frame,kind=kind,move=vars(move),origin=path.origin,
                   through=path.through,scope="keys only; no safety credit")

    def _post_path(self,seed,state,sim,game,*,kind,move,frame,mask,continuing=False,press=None):
        from .knife_chain_post import reroll_post
        self._post_cache_for(move)
        template=self._post_keys.get(kind)
        if template is not None:
            try:
                path=reroll_post(template,seed,state,sim,game,move=move,kind=kind,frame=frame,
                    profile=self.profile,first_mask=mask,continuing=continuing,
                    observed_history=self.runner.anchor.hist,known_press=press)
                self._note("b2_post_keys_reused",frame=frame,kind=kind,template_source=template.source_frame,
                           through=path.through,model_origin=sim.f,
                           scope="fresh table key, rerolled physics; geometry still required")
                return path
            except (NominalUnsupported,ChainObservationNotReady) as exc:
                self._note("b2_post_keys_miss",frame=frame,kind=kind,reason=str(exc))
        path=compile_path(seed,state,sim,game,stage="continuation",first_mask=mask,
            profile=self.profile,branch=None if continuing else kind,known_press=press,
            observed_history=self.runner.anchor.hist)
        self._remember_post_keys(path,kind,move,frame)
        return path

    def _prepare_post_keys(self,future,sim,move,frame):
        # One missing key template per approach tick. This is speculative table
        # work, never a future admission or a cached geometry result.
        from .knife_chain_post import KINDS
        from .air_chain import ChainSim
        self._post_cache_for(move)
        missing=[k for k in KINDS if k not in self._post_keys]
        if not missing:return
        kind=missing[self._post_prepare_cursor%len(missing)];self._post_prepare_cursor+=1
        bs=ChainSim(future.states[:,-1],np.array([future.queued_next],np.int64),future.hold_end,
                    sim.params,sim.terrain,future.through,future.through)
        try:
            path=compile_path(future.runner_end,future.raw_end,bs,float(future.game[-1]),stage="continuation",
                first_mask=0,profile=self.profile,branch=kind,known_press=future.press_frame)
            self._remember_post_keys(path,kind,move,frame)
        except (NominalUnsupported,ChainObservationNotReady) as exc:
            self._note("b2_post_prepare_unchecked",frame=frame,kind=kind,reason=str(exc))

    def _recovery_offer(self):
        return None if self.recovery is None else B2Offer("recovery",None,None,0,0.,self.recovery["move"],dict(self.recovery))


    def _arm_jump_start(self,offer,send):
        from .knife_chain_jump import JumpStartWatch
        if self._jump_start is None and offer.path is not None:
            self._jump_start=JumpStartWatch.from_path(offer.path,offer.move,send.frame,self._receipts)
            if self._jump_start is not None:
                self._note("b2_jump_start_expected",frame=send.frame,move=vars(offer.move),
                           targets=list(self._jump_start.targets),source="first modeled ground-jump block")


    def _check_jump_start(self,frame):
        watch=self._jump_start
        if watch is None:return False
        reason=watch.failure(frame)
        if reason is None:return False
        self._failed_hook_moves.add(watch.move)
        self._note("b2_controller_defect",frame=frame,reason=reason,move=vars(watch.move),
                   planned_targets=list(watch.targets),sent_targets=sorted(watch.sent_targets),no_retry_same_move=True)
        self._recover(reason,frame)
        return True


    def _fast_j_reproduced(self,fast,bundle):
        from .knife_chain_hook_fast import plan_key
        preview,_=bundle;run=preview.draft.run
        ok=(fast["used"] and preview.mask is not None and run is not None and run.lid=="slam_claw.pre" and
            plan_key(run.v.get("cs"))==fast["key"] and int(preview.mask)==fast["mask"])
        if not ok:
            self._note("b2_fast_j_fallback",frame=self.dispatch.frame,reason="fast step did not reproduce the committed J",
                       used=fast["used"],mask=None if preview.mask is None else int(preview.mask),want=fast["mask"],
                       path="unchanged full path (C5 recheck + nominal accounting) this tick")
        return ok

    def _fast_j_record_deferred(self,f,move):
        calls=self._last_c5_calls or []
        pending=self._fast_j_sent
        if not calls or pending is None or pending["move"]!=move or f<=pending["frame"]:return
        outcome=("p_only_pass" if calls[0]["ok"] else "replan" if len(calls)>1 and calls[1]["ok"] else "lost_plan_kept")
        pending["deferred"]={"frame":f,"outcome":outcome}
        self._note("b2_fast_j_deferred_check",frame=f,move=vars(move),outcome=outcome,calls=calls,
                   verdict="ran",semantics="full C5 ran; failed recheck in CS_KEEP_F retains the h2 plan")


    def propose(self,planner,ws,start,hold,prefix,forecast,prefs,ctx):
        """Time this synchronous proposal, separately from selection/send costs."""
        self._proposal_started=time.perf_counter()
        from .knife_chain_raster_cache import exact_dilation_scope
        try:
            with exact_dilation_scope() as cache:
                offer=self._propose(planner,ws,start,hold,prefix,forecast,prefs,ctx)
            if cache.hits or cache.misses or cache.uncacheable:
                self._note("b2_dilation_cache",frame=self.dispatch.frame,**cache.stats())
            if offer is not None:offer.proposal_ms=(time.perf_counter()-self._proposal_started)*1000.
            return offer
        finally:self._proposal_started=None

    def _propose(self,planner,ws,start,hold,prefix,forecast,prefs,ctx):
        """One actual tick; active commitment bypasses ordinary-tail competition."""
        if self.arm!="B":return None
        if self.budget is not None:self.budget.check()
        gate=self.policy_gate_reason
        if gate is not None:
            if self.commitment is not None:self._recover("policy priority gate: "+str(gate),self.dispatch.frame)
            self._no_candidate("policy priority gate: "+str(gate));return None
        if self.recovery is not None:return B2Offer("recovery",None,None,0,0.,self.recovery["move"],dict(self.recovery))
        if self._check_jump_start(self.dispatch.frame):return self._recovery_offer()
        if self._check_hook_start(self.dispatch.frame):
            return (B2Offer("recovery",None,None,0,0.,self.recovery["move"],dict(self.recovery))
                    if self.recovery is not None else None)
        fast=None
        if self._fast_j_mode and self.commitment is not None:
            from .knife_chain_hook_fast import admit
            fast=admit(self,forecast)
        try:
            bundle=self._preview(fast=fast) if fast is not None else self._preview()
            if fast is not None and bundle is not None and not self._fast_j_reproduced(fast,bundle):
                fast=None;bundle=self._preview()
        except ChainObservationNotReady as exc:
            self._note("b2_unchecked",frame=self.dispatch.frame,reason=str(exc));return None
        if bundle is None:
            if self.post_context is not None and self.post_context.get("simple_wait"):
                self._note("b2_fixed_wait_handoff",frame=self.dispatch.frame,released=False,reason="current wait observation unavailable")
                self.post_context=None;self._post_seed=None;self._post_kind=None;self._abandon("wait observation unavailable")
            if self.commitment:self._recover("current family program cannot continue",self.dispatch.frame)
            if self.recovery is not None:return B2Offer("recovery",None,None,0,0.,self.recovery["move"],dict(self.recovery))
            return None
        preview,move=bundle
        tick,sim,guard,bombs=self._context;f,state,game,ground,accepting=tick
        if fast is None and self._fast_j_sent is not None and self._fast_j_sent["deferred"] is None:
            self._fast_j_record_deferred(f,move)
        if move in self._failed_hook_moves:
            self._no_candidate("planned hook failed for this Move; no automatic retry",frame=f,state=state)
            return None
        if preview.draft.run.chain=="fixed_hook" or preview.draft.run.lid=="slam_jump.wait":
            # User100: direct empirical keys through observed bounce + the simple
            # hammer wait. No nominal path/C5/N2/exact-support construction here.
            if self.commitment is not None and self.commitment["move"]!=move:
                self._recover("fixed hook instance mismatch",f);return self._recovery_offer()
            if self.post_context is not None and self.post_context["move"]!=move:
                self._note("b2_fixed_wait_handoff",frame=f,released=False,reason="observed different Move instance")
                self.post_context=None;self._post_seed=None;self._post_kind=None
            if self.commitment is None and self.post_context is None:
                if preview.draft.run.chain=="fixed_hook":
                    queued,basis=self.queued_prefix(f,state)
                    held=((state.get("act") or {}).get("hf") or {}).get("desired")
                    if queued is None or queued!=held:
                        self._note("b2_fixed_prefix_rejected",frame=f,queued=queued,held=held,basis=basis)
                        self._no_candidate("fixed hook needs its admitted direction through the queued frame",frame=f,state=state)
                        return None
                stage="fixed_commitment"
            else:stage="active"
            return B2Offer(stage,None,preview.draft,int(preview.mask),0.,move,
                {"fixed_hook":preview.draft.run.chain=="fixed_hook","simple_wait":preview.draft.run.link=="wait","safety_basis":"empirical table; geometry unchecked",
                 "phase":preview.draft.run.link,"entry_k":preview.draft.run.v.get("k_start")})
        rs=getattr(forecast,"rs",None)
        observed=None if rs is None else getattr(rs.trk,"now",{}).get(move.target_iid)
        if observed is None:
            self._no_candidate("target tracker observation unavailable",frame=f,state=state);return None
        geo=B2Geometry(forecast,f,move,observed[2])
        if preview.draft.run.v.get("bounced") and self.post_context is None:
            self._failed_hook_moves.add(move)
            self._note("b2_table_bounce_mismatch",frame=f,move=vars(move),observed_bounce=False)
            self._recover("table claimed bounce without actual DownSlash/bounce observation",f)
            return self._recovery_offer()
        if self.commitment is not None:
            if self.commitment["move"]!=move:
                self._recover("commitment instance mismatch",f);return self._recovery_offer()
            if fast is not None:
                details={"commitment":True,"fast_j":{"tick":fast["tick"],"key":list(fast["key"]),"delta":fast["delta"],
                    "application":fast["application"],"owners":fast["owners"],
                    "skipped":["C5 rule-0 recheck","_prepare_post_keys"]}}
                self._note("b2_fast_j",frame=f,move=vars(move),mask=int(preview.mask),**details["fast_j"])
                return B2Offer("active",None,preview.draft,int(preview.mask),0.,move,details)
            if self._committed_future is not None and f<self._committed_future.through:
                self._prepare_post_keys(self._committed_future,sim,move,f)
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
                    path=self._post_path(seed,state,sim,game,kind=kind,move=move,frame=f,
                        mask=preview.mask,continuing=continuing,press=self._press)
                    scan=geo.scan(path)
                    ok=check_external_path(scan,path_ref=geo.ref(path),target_move=move,first_frame=f,
                        last_frame=path.through,stage="continuation")
                    if ok.verdict!="pass":
                        self._note("b2_post_rejected",frame=f,kind=kind,verdict=ok.verdict,reason=ok.reason,
                                   retained_contacts=len(ok.retained));continue
                    real=preview.draft if continuing else path.first_draft
                    mask=int(path.offered[0])
                    offers.append(B2Offer("continuation",path,real,int(mask),self._endpoint(planner,path,prefs),move,{"kind":kind}))
                except (NominalUnsupported,GeometryUnavailable,ChainObservationNotReady) as exc:
                    self._note("b2_post_unchecked",frame=f,kind=kind,reason=str(exc))
            if not offers:self._no_candidate("no checked post-bounce branch",frame=f,state=state)
            return max(offers,key=lambda o:o.value) if offers else None
        try:
            future=compile_path(preview.draft,state,sim,game,stage="commitment",first_mask=preview.mask,profile=self.profile,selected_claw=True)
            if not is_committing(preview.draft.run,self.profile):
                path=future.approach
                if path is None:raise NominalUnsupported("no next entry decision in nominal approach")
                scan=geo.scan(path)
                ok=check_external_path(scan,path_ref=geo.ref(path),target_move=move,first_frame=f,last_frame=path.through,stage="approach")
                preflight=geo.preflight(future)
                if ok.verdict!="pass" or preflight.contacts:
                    self._note("b2_approach_rejected",frame=f,path=ok.reason,preflight=[asdict(c) for c in preflight.contacts]);return None
                self._prepare_post_keys(future,sim,move,f)
                return B2Offer("approach",path,preview.draft,int(preview.mask),0.,move,
                               {"preflight_through":future.through,"next_decision":path.assumptions.get("future_decision")})
            admission=TargetMoveAdmission(move,f,future.through,
                self.runner.binding["table_digest"]+":"+preview.draft.run.lid,"pass")
            scan=geo.scan(future)
            ok=check_external_path(scan,path_ref=geo.ref(future),target_move=move,first_frame=f,last_frame=future.through,
                                   stage="commitment",admission=admission)
            if ok.verdict!="pass":
                self._note("b2_commit_rejected",frame=f,reason=ok.reason,contacts=[asdict(c) for c in ok.retained]);return None
            from .air_chain import ChainSim
            from .knife_chain_post import KINDS
            bs=ChainSim(future.states[:,-1],np.array([future.queued_next],np.int64),future.hold_end,
                        sim.params,sim.terrain,future.through,future.through)
            # The N=2 contract asks only for short executable types. Do not
            # interpret every tail to ground merely to discover that threshold.
            paths={};errors={};full_paths={}
            self._post_cache_for(move)
            for kind in KINDS:
                try:
                    if kind in self._post_keys:
                        paths[kind]=self._post_path(future.runner_end,future.raw_end,bs,float(future.game[-1]),
                            kind=kind,move=move,frame=f,mask=0,press=future.press_frame)
                    else:
                        from .knife_chain_post_actions import ordinary_post
                        paths[kind]=ordinary_post(future,sim.params,sim.terrain,kind=kind,profile=self.profile)
                except (NominalUnsupported,ChainObservationNotReady) as exc:errors[kind]=str(exc)
            bgeo=B2Geometry(forecast,f,move,observed[2])
            bounce_ref=f"{move}:{future.through}"
            opts=[]
            for kind,path in paths.items():
                short=bgeo.scan(path,min(self.profile.short_frames,len(path.commands)))
                opts.append(Continuation(kind,kind,bounce_ref,bgeo.ref(path),
                    path.through if path.end=="handback" else None,
                    self.continuation_executable(kind,path),"pass",short))
            def finish(kind):
                if kind not in full_paths:
                    from .knife_chain_nominal import finish_post
                    if paths[kind].assumptions.get("projection")=="ordinary_post_action_type":
                        from .knife_chain_post_actions import ordinary_post
                        full_paths[kind]=ordinary_post(future,sim.params,sim.terrain,kind=kind,profile=self.profile,full=True)
                    else:
                        full_paths[kind]=finish_post(paths[kind],sim.params,sim.terrain,profile=self.profile)
                        self._remember_post_keys(full_paths[kind],kind,move,f)
                return full_paths[kind]
            def full_scan(option):
                from dataclasses import replace
                from .knife_chain_commitment import FullContinuationScan
                p=finish(option.option_id)
                # Same command program, now extended from its recorded checkpoint.
                scan=replace(bgeo.scan(p),path_ref=option.path_ref)
                return FullContinuationScan(scan,p.through)
            exits=assess_continuations(tuple(opts),target_move=move,bounce_state_ref=bounce_ref,bounce_frame=future.through,
                short_frames=self.profile.short_frames,full_scan=full_scan,
                unavailable_errors=(NominalUnsupported,GeometryUnavailable,ChainObservationNotReady))
            details={"nominal_contact":future.contact_frame,"assumptions":future.assumptions,
                     "continuations":asdict(exits),"unavailable_branches":errors,"admission":asdict(admission)}
            if exits.verdict!="pass":
                self._note("b2_no_exit",frame=f,kinds=list(exits.qualifying_kinds),errors=errors,
                    reason=exits.reason,continuations=asdict(exits),no_repeat_downslash=True);return None
            # A guaranteed planned nail strike is valued in the SAME ordinary hit
            # unit (weights.hit), not by the known-zero static-body nh/hit_w.
            # Ranking is not a second admission gate. A wall-stuck modeled
            # tail cannot erase an already passed N=2 short-path result.
            from .knife_chain_value import handback_value
            stance,projection=handback_value(paths,exits,finish,
                lambda p:self._endpoint(planner,p,prefs),
                unavailable_errors=(NominalUnsupported,GeometryUnavailable,ChainObservationNotReady))
            details["value_projection"]=projection
            if projection["value_fallback"]:
                self._note("b2_value_fallback",frame=f,move=vars(move),projection=projection)
            self._note("b2_short_post",frame=f,short_kinds=list(exits.qualifying_kinds),
                full_expanded=list(full_paths),value_kind=projection["kind"],value_projection=projection["mode"])
            value=float(prefs.weights.get("hit",10.))+stance
            if self._fast_j_mode:
                from .knife_chain_hook_fast import owners,target_obs,observed_hold,hold_equivalent
                e=next((e for e in state.get("ents") or () if e.get("iid")==move.target_iid),None)
                known_hold=observed_hold((state.get("act") or {}).get("hf"))
                self._fast_j_pending_commit={"move":move,"frame":f,"instance":observed[2],
                    "owners":owners(forecast),"hold_start":sim.hold.copy(),"target":target_obs(e),
                    "hold_known":known_hold is not None and hold_equivalent(known_hold,sim.hold)}
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
        if offer.draft is not None and getattr(offer.draft,"_nominal_projection_only",False):
            raise NativeChainAuditError("model-only selected strike cannot own runtime input")
        """Planner's selected B2 candidate; no physical action is sent here."""
        from .planner import PlanResult
        f=self.dispatch.frame
        if offer.stage=="recovery":
            planner.prev_cmd=None;planner.prev_tail_ok=False;planner.prev_esc_unsafe=True
            res=PlanResult(0,-1,"CHAIN B2 hook recovery release",1,True,n=0,n_allowed=0,n_safe=0,tail_ok=None)
            planner.prev_name=res.name
            planner.last_info={"b2":{"stage":"recovery","reason":self.recovery["reason"]},
                               "esc":{"unsafe":True,"b2":"hook_motion_unchecked_release_until_control"}}
            if planner.measurement_enabled:planner.measurement_result=res
            self._note("b2_hook_recovery_wait",frame=f,mask=0,path="unchecked")
            return res
        # The named probe remains visible; h2 guard use isn't relabelled fitted.
        admission_name=("vault_near_entry" if offer.details.get("vault_near") else
                        "manual_air_entry" if offer.details.get("manual_air") else "legacy_h2_guard")
        adm=AdmissionDecision(offer.draft.run.lid,"unchecked",f,None,
                             (ConditionResult(admission_name,"unchecked","named B2 learning protocol"),))
        wire=self.dispatch.offer(offer.draft.run.lid,offer.mask,table_ref=self.runner.binding["table_digest"],admission=adm)
        self.register_row(0,wire,probe_ref=self.probe_ref)
        self._draft,self._offer,self._b2_selected=offer.draft,wire,offer
        self._projection=self._projection_pool=None
        p=offer.path
        cmd=np.array([offer.mask],np.int64) if p is None else p.offered.copy()
        res=PlanResult(offer.mask,0,"CHAIN B2 "+offer.stage+" "+offer.draft.run.lid,0,False,J=offer.value,V=True,
                       n=1,n_allowed=1,n_safe=0 if (offer.details.get("fixed_hook") or offer.details.get("simple_wait") or offer.details.get("manual_air")) else 1,cmd=cmd,path=None if p is None else p.box,
                       tail_ok=None,hits=1. if offer.stage=="commitment" else 0.)
        if offer.stage in {"commitment","fixed_commitment","manual_commitment"}:
            from .knife_chain_score_bound import clear_ordinary_action_memo
            clear_ordinary_action_memo(planner)
        planner.prev_cmd=None if offer.stage!="continuation" else cmd.copy()
        planner.prev_name=res.name;planner.prev_tail_ok=False;planner.prev_esc_unsafe=False
        planner.last_info={"b2":{"stage":offer.stage,"move":vars(offer.move),"details":offer.details,
                                  "ordinary":None if ordinary is None else {"J":ordinary.J,"name":ordinary.name}},
                           "esc":{"b2":"unchecked_manual_air" if offer.details.get("manual_air") else "unchecked_empirical_table" if (offer.details.get("fixed_hook") or offer.details.get("simple_wait")) else "empirical_lower_bound" if offer.stage=="commitment" else "not_a_commitment",
                                  "unsafe":False},"S":np.zeros(1,np.int64),"N":1}
        if planner.measurement_enabled:planner.measurement_result=res
        if p is not None:
            self._note("b2_nominal_path",frame=f,stage=offer.stage,move=vars(offer.move),
                through=p.through,commands=p.commands.tolist(),latched=p.latched.tolist(),
                box=p.box.tolist(),flags=p.flags.tolist(),check_flags=p.check_flags.tolist(),
                press=p.press_frame,conditional_contact=p.contact_frame,assumptions=p.assumptions,
                observations="private modeled future only; no actual application/contact credit")
        self._note("b2_selected",frame=f,stage=offer.stage,mask=offer.mask,move=vars(offer.move),
                   through=None if p is None else p.through,value=offer.value,details=offer.details,
                   ms=offer.proposal_ms,timing_scope="complete proposal only; excludes ordinary planner/install/send")
        return res

    def _abort_hook_dispatch(self,selected,*,frame,target,mask,flags,received_frame,event,reason,**details):
        self._failed_hook_moves.add(selected.move)
        self._note(event,frame=frame,target=target,received_frame=received_frame,
                   proposed_mask=int(mask),replacement_mask=0,reason=reason,**details)
        if event in {"b2_jump_send_veto","b2_fast_j_claw_veto"}:
            self._note("b2_controller_defect",frame=frame,reason=reason,move=vars(selected.move),
                       no_retry_same_move=True,action="neutral recovery before unsupported hook")
        preparation=None
        if selected.stage in {"commitment","fixed_commitment","manual_commitment"} and self.commitment is None:
            # A vetoed first key is not a successful chain dispatch. Once its
            # neutral replacement IS sent, it is nevertheless a sent failed
            # preparation and retains the original strict HP responsibility.
            preparation={"move":selected.move,"origin":frame,"target":target,"failed":received_frame,
                         "ta":selected.draft.run.v.get("ta")}
            self._press=self._accepted=self._hit=None
        self._recover(reason,received_frame);self._b2_selected=None
        self._vetoed_preparation=preparation
        self.final("b2_deadline_abort",0)
        super().before_send(frame=frame,target=target,mask=0,flags=flags,received_frame=received_frame)
        return 0

    def _hook_target_check(self,selected,frame,target,mask):
        """Veto a different first ray body in a multi-Clapper scene.

        Single-Clapper admission stays with its existing guard. This checks
        current bodies at the modeled key-frame pose, not the later throw.
        """
        from .slam_play import clappers
        es=clappers(self._actual_state or {})
        if len(es)<2:return None
        prev=self._receipts.get(target-1)
        if prev is None:prev,_=self.queued_prefix(frame,self._actual_state)
        if prev is not None and prev&B["CLAW"]:return None  # hold, not a new press
        info={"planned_target":selected.move.target_iid,
              "scope":"current-body identity veto; later throw/motion and empty needle are not admitted"}
        try:
            if prev is None:raise ValueError("unknown pre-hook input prefix")
            if self._actual_state.get("f")!=frame or target!=frame+2:raise ValueError("stale hook identity observation")
            if self._context is None:raise ValueError("no current hook-pose model")
            sim=self._context[1]
            if sim is None or sim.f!=frame or sim.fo!=frame or len(sim.prefix)!=1 or int(sim.prefix[0])!=prev:
                raise ValueError("hook-pose model/prefix mismatch")
            from ssbot.knowledge import kinematics as km
            from .knife_chain_air import body_box
            from .knife_chain_hook_target import first_ray_body
            ro=sim.roll(np.array([[mask]],np.int64))
            box=ro.box[0,sim.off].tolist();face=float(ro.final[km.FACE,0])
            if face not in (-1.,1.):raise ValueError("unknown modeled hook facing")
            bodies=[]
            for e in es:
                body=body_box(e)
                bodies.append((e["iid"],None if body is None else body.tolist()))
            hit=first_ray_body(box,int(face),bodies)
            info.update(pose_frame=target,hero_box=box,face=int(face),
                        first_target=None if hit is None else hit[0],distance=None if hit is None else hit[1])
            if hit is None:return "hook ray has no observed target body",info
            if hit[0]!=selected.move.target_iid:return "hook ray first body differs from planned target",info
            return None,info
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            return "hook target identity unchecked: "+str(exc),info

    def before_send(self, *, frame, target, mask, flags, received_frame, dispatch_clock=None):
        if type(received_frame) is not int or received_frame>target+4:
            self._stop("send deadline beyond four frames / missing current frame",frame)
        selected=self._b2_selected;last=None;jump=self._jump_start
        # Before any fixed/manual early return, including already retained CS
        # plans. A second Clapper can intercept a perfectly timed hook.
        if selected is not None and int(mask)==selected.mask and int(mask)&B["CLAW"]:
            check=self._hook_target_check(selected,frame,target,int(mask))
            if check is not None:
                reason,info=check
                if reason is not None:
                    return self._abort_hook_dispatch(selected,frame=frame,target=target,mask=mask,flags=flags,
                        received_frame=received_frame,event="b2_hook_target_veto",reason=reason,**info)
                self._note("b2_hook_target_checked",frame=frame,target=target,**info)
        if selected is not None and selected.details.get("fixed_hook") and int(mask)==selected.mask:
            cs=selected.draft.run.v["cs"];reason=None
            if int(mask)&B["J"] and self._fixed_jump_sent_for!=selected.move:
                if target!=cs.f0 or received_frame>=target:reason="fixed first-J slot missed"
                elif self.require_send_clock:
                    from .knife_chain_deadline import first_jump_clock
                    try:clock=first_jump_clock(dispatch_clock,target)
                    except ValueError as exc:self._stop("missing critical first-J receive clock: "+str(exc),frame)
                    self._note("b2_jump_dispatch_clock",frame=frame,target=target,**clock)
                    if clock["late"]:reason="fixed first-J calibrated send deadline elapsed"
            if int(mask)&B["CLAW"] and (self._fixed_jump_sent_for!=selected.move or target not in (cs.f_press,cs.f_press+1) or received_frame>=cs.f_press+1):
                reason="fixed hook absolute CLAW slot missed / no successful J send"
            if reason is not None:
                return self._abort_hook_dispatch(selected,frame=frame,target=target,mask=mask,flags=flags,
                    received_frame=received_frame,event="b2_jump_send_veto",reason=reason)
            if received_frame>=target:self._note("b2_send_late",frame=frame,target=target,received_frame=received_frame)
            return super().before_send(frame=frame,target=target,mask=mask,flags=flags,received_frame=received_frame)
        if selected is not None and selected.stage=="commitment" and selected.path is not None:
            slots=[selected.path.origin+i+1 for i,m in enumerate(selected.path.commands) if int(m)&B["CLAW"]]
            if slots:
                last=max(slots)
                from .knife_chain_jump import JumpStartWatch
                jump=JumpStartWatch.from_path(selected.path,selected.move,frame,self._receipts)
        watch=self._hook_start
        # A deferred first J is emitted by an active tick, not the original
        # commitment tick. Its absolute jump block still belongs to this hook.
        if last is None and watch is not None and watch["seen_frame"] is None:
            last=max(watch["targets"])
        matches=selected is not None and int(mask)==selected.mask
        fj=self._fast_j_sent
        if (matches and fj is not None and fj["deferred"] is None and int(mask)&B["CLAW"] and selected.move==fj["move"]):
            return self._abort_hook_dispatch(selected,frame=frame,target=target,mask=mask,flags=flags,
                received_frame=received_frame,event="b2_fast_j_claw_veto",
                reason="fast J had no later full C5 recheck before the first CLAW",fast_j_target=fj["target"])
        if matches and last is not None and jump is not None and jump.seen_frame is None:
            reason=None
            if int(mask)&B["J"]:
                if not jump.sent_targets and target!=min(jump.targets):
                    reason="first pre-hook ground-jump target skipped before send"
                elif not jump.sent_targets and received_frame>=target:
                    reason="pre-hook ground-jump target already observed before send"
                elif not jump.sent_targets and self.require_send_clock:
                    from .knife_chain_deadline import first_jump_clock
                    try:clock=first_jump_clock(dispatch_clock,target)
                    except ValueError as exc:
                        if self.require_send_clock:self._stop("missing critical first-J receive clock: "+str(exc),frame)
                        reason="pre-hook ground-jump receive clock unknown"
                    else:
                        self._note("b2_jump_dispatch_clock",frame=frame,target=target,**clock)
                        if clock["late"]:reason="pre-hook ground-jump calibrated send deadline elapsed"
            elif int(mask)&B["CLAW"]:
                reason="pre-hook ground jump not observed before CLAW dispatch"
            if reason is not None:
                return self._abort_hook_dispatch(selected,frame=frame,target=target,mask=mask,flags=flags,
                    received_frame=received_frame,event="b2_jump_send_veto",reason=reason,
                    jump_targets=list(jump.targets),jump_seen=jump.seen_frame)
        # Retain the hook deadline's original commitment/CLAW scope; a later
        # neutral tick may still be waiting for an already sent hook to appear.
        if (last is not None and matches and received_frame>=last and
                (selected.stage=="commitment" or int(mask)&B["CLAW"])):
            return self._abort_hook_dispatch(selected,frame=frame,target=target,mask=mask,flags=flags,
                received_frame=received_frame,event="b2_hook_send_veto",
                reason="hook dispatch window expired before actual send",last_hook_target=last)
        if received_frame>=target:
            self._note("b2_send_late",frame=frame,target=target,received_frame=received_frame,
                       target_already_observed=True,application="unchecked until bounded report/coverage")
        return super().before_send(frame=frame,target=target,mask=mask,flags=flags,received_frame=received_frame)

    def sent(self):
        selected=self._b2_selected
        sent=super().sent()
        preparation=self._vetoed_preparation
        if preparation is not None:
            if sent.frame!=preparation["origin"] or sent.target_frame!=preparation["target"] or sent.desired_mask!=0:
                self._stop("veto neutral replacement does not match successful send",sent.frame)
            exposure=self._failure_exposure(preparation["move"],preparation["origin"],preparation["failed"],preparation["ta"])
            if self._actual_state is not None:exposure.observe(self._actual_state,game_time=self._clock)
            self._failure_exposures.append(exposure)
            self._note("b2_failure_exposure",frame=preparation["failed"],exposure=exposure.as_dict(),
                       source="successful neutral replacement after initial dispatch veto")
            self._vetoed_preparation=None
        committed=selected is not None and sent.chain_outcome=="sent"
        if committed:
            if selected.stage in {"fixed_commitment","manual_commitment"}:
                self.commitment={"move":selected.move,"origin":sent.frame,"ta":self.runner.run.v["ta"],
                                 "predicted_bounce":selected.details.get("predicted_bounce"),"fixed_hook":selected.stage=="fixed_commitment",
                                 "manual_air":bool(selected.details.get("manual_air"))}
                self._press=self._accepted=self._hit=None;self._fixed_jump_sent_for=None
                self._arm_hook_start(selected,sent)
            elif selected.stage=="commitment":
                self._arm_jump_start(selected,sent)
                self._committed_future=selected.path
                self.commitment={"move":selected.move,"origin":sent.frame,"ta":self.runner.run.v["ta"],
                    "predicted_bounce":selected.path.contact_frame}
                self._press=self._accepted=self._hit=None
                self._arm_hook_start(selected,sent)
                pending=self._fast_j_pending_commit
                if self._fast_j_mode and pending is not None and pending["move"]==selected.move:
                    from .knife_chain_hook_fast import plan_key
                    self._fast_j_commit={**pending,"origin":sent.frame,"path":selected.path,
                        "key":plan_key(self.runner.run.v.get("cs"))}
            elif selected.stage=="active" and selected.details.get("fast_j") is not None:
                # One record per Move for the skipped re-plans (wait step, first J); it owes a full C5
                # on a LATER tick. A wait step's key has no J: target stays None, no jump send is claimed.
                tick=selected.details["fast_j"].get("tick","J");fs=self._fast_j_sent
                if fs is None or fs["move"]!=selected.move or fs["deferred"] is not None:
                    fs=self._fast_j_sent={"move":selected.move,"frame":sent.frame,"target":None,"deferred":None,"skips":[]}
                fs["frame"]=sent.frame;fs["skips"].append(tick)
                if sent.desired_mask&B["J"]:fs["target"]=sent.target_frame
                self._note("b2_fast_j_sent",frame=sent.frame,target=sent.target_frame,move=vars(selected.move),
                           tick=tick,j_sent=bool(sent.desired_mask&B["J"]),skips=list(fs["skips"]),
                           deferred="full C5 required on a later tick before CLAW")
            if selected.details.get("fixed_hook") and sent.desired_mask&B["J"]:self._fixed_jump_sent_for=selected.move
            watch=self._hook_start
            if (watch is not None and self.commitment is not None and
                    self.commitment["move"]==watch["move"] and selected.move==watch["move"] and
                    selected.stage in {"commitment","fixed_commitment","active"} and sent.frame>=watch["origin"] and
                    sent.desired_mask&B["CLAW"]):
                watch["sent_targets"].add(sent.target_frame)
                self._note("b2_hook_start_sent",frame=sent.frame,target=sent.target_frame,move=vars(watch["move"]),
                           in_planned_window=sent.target_frame in watch["targets"],
                           physical_action="unchecked; wait for actual Harpoon animation")
            if self._jump_start is not None:self._jump_start.record_send(sent.target_frame,sent.desired_mask)
            if selected.stage=="continuation":self._post_kind=selected.details["kind"]
            if selected.mask&(B["D"]|B["A"])==(B["D"]|B["A"]):
                prev=self._receipts.get(sent.target_frame-1)
                if prev is None and self._actual_state is not None:
                    prev,_=self.queued_prefix(sent.frame,self._actual_state)
                if prev is not None and not prev&B["A"] and self.commitment:self._press=sent.target_frame
        elif self.commitment is not None:
            self._recover("final owner/keys overridden",sent.frame)
        elif self.post_context is not None:
            self._post_kind=None
            if self.post_context.get("simple_wait"):
                self._note("b2_fixed_wait_handoff",frame=sent.frame,released=False,reason="higher-priority owner/keys interrupted wait")
                self.post_context=None;self._post_seed=None
        self._fast_j_pending_commit=None
        self._b2_selected=None
        return sent

    def summary(self):
        return {**super().summary(),"mode":"b2_probe","arm":self.arm,"candidate_generation":self.candidate_generation,
                "projection":"nominal_chain_program","failure_exposures":[e.as_dict() for e in self._failure_exposures],"commitment":None if self.commitment is None else
                {**self.commitment,"move":vars(self.commitment["move"])},
                "post_context":None if self.post_context is None else {**self.post_context,"move":vars(self.post_context["move"])},
                "recovery":None if self.recovery is None else {**self.recovery,"move":None if self.recovery["move"] is None else vars(self.recovery["move"])},
                "learning_stop":self.learning_stop,"budget":None if self.budget is None else self.budget.state,
                "receipt_counts":dict(self._receipt_counts),
                "receipt_scope":"pending chain command resolution; not all IPC/hero actions",
                "live_ready":False}
