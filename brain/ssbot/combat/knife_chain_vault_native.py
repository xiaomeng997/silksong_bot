"""Existing Idle-vault table inside the manual-air B2 transaction owner.

The optional table shares one dispatch/receipt/budget lifecycle with the air and
transfer tables. It neither chooses a tactical target nor sends keys. Distance
selects a manual near jump or small-hop hook; only the current external step is
modeled. Full skill/contact/tail predictions are offline diagnostics.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import math

import numpy as np

from . import knife_chain_air as AIR, knife_chain_vault as V
from .knife_chain_eval import ChainRunner
from .knife_chain_format import ChainVocabulary
from .knife_chain_nominal import NominalUnsupported, logical_copy
from .knife_chain_geometry import B2Geometry, GeometryUnavailable
from .knife_chain_commitment import MoveInstance
from .knife_chain_b2 import B2Offer
from .knife_chain_slam import OBS_NAMES
from .slam_play import clappers, control


class AirVaultAnchor(V.VaultAnchor):
    def __init__(self, chains):
        super().__init__(chains, chains[V.CHAIN].cfg)

    def clock(self, x, name):
        if x.run.chain == V.CHAIN:
            return super().clock(x, name)
        return AIR.AirAnchor.clock(self, x, name)

    def close(self, x, kind, why):
        if x.run.chain == V.CHAIN:
            return super().close(x, kind, why)
        return AIR.AirAnchor.close(self, x, kind, why)


def _family_dispatch(air, vault):
    return lambda x, *a, **kw: (vault if x.run is not None and x.run.chain == V.CHAIN else air)(x, *a, **kw)


def load_runner():
    """Bind four families together; loading never starts a run."""
    air = AIR.load_runner()
    vault, _ = V.load_vault_runner()
    prims = deepcopy(air.P)
    for attr in ("guards", "values", "gens", "acts", "dirs"):
        dst, src = getattr(prims, attr), getattr(vault.P, attr)
        for name, fn in src.items():
            dst[name] = _family_dispatch(dst[name], fn) if name in dst else fn
    prims.meta.update(vault.P.meta)
    chains = dict(air.chains, **vault.chains)
    observations = set(OBS_NAMES) | {"f", "F", "k", "ready", "target_valid", "bounced", "entry_k",
                                   "gap", "height", "program", "jump_held", "ground", "overhead"}
    vocabulary = ChainVocabulary(clocks=V.VOCAB.clocks, directions=frozenset(prims.dirs))
    return ChainRunner(chains, AirVaultAnchor(chains), prims,
                       cfg0=dict(air.cfg0, native_vault_near=True), observation_names=observations,
                       literal_names=V.LITERALS, vocabulary=vocabulary)


def warm(params):
    """Compile only this family's missing signatures before any decisions."""
    import time
    from ssbot.core import forum as F
    from ssbot.knowledge import kinematics as K
    from .air_chain import ChainSim
    from .knife_chain_step import NominalStepper, hold_one
    from .knife_chain_vault_entry import near_proposals
    from .knife_chain_vault_nominal import _down_meets
    from .scene_field_event_shadow import _startup_inputs
    started=time.perf_counter()
    _startup_inputs()
    terrain=K.Terrain2D.from_boxes([(-200.,F.FLOOR_Y-10.,260.,F.FLOOR_Y)])
    start=K.initial_state(params,30.,F.FLOOR_Y+params.foot,ground=True)
    hold=K.HoldState.idle(1)
    hold_one(0,hold)
    stepper=NominalStepper(params,terrain)
    stepper.run(start,frames=0)
    stepper.run(start,1,event=K.EV_POGO)
    box=np.array([31.6,F.FLOOR_Y,35.19,F.FLOOR_Y+3.9])
    sim=ChainSim(start,np.zeros(1,np.int64),hold,params,terrain,100,100)
    recipe=load_runner().chains[V.CHAIN].cfg["NEAR_RECIPE"]
    _,diag=near_proposals(sim,box,1,recipes=(recipe,))
    V.side_meets(30.,5.,1,box)
    _down_meets(np.array([30.,8.]),1,box)
    from types import SimpleNamespace
    from .knife_chain_nominal import _nominal_hook,NominalProfile
    from ssbot.map2.oldwin_claw import control_state
    # Exercise the same existing hook-motion/control initializer before combat.
    air=stepper.run(start,K.B_JUMP).final[:,0].copy()
    world=SimpleNamespace(iid=7,box=lambda game:box)
    hook,_=_nominal_hook(air,world,0.,params,terrain,NominalProfile(),1)
    control=control_state(params,hook,terrain,alpha=.5)
    stepper.run(control,0)
    return {"family":"vault_near","ms":(time.perf_counter()-started)*1000.,
            "proposal_rows_warmed":diag["generated"],"hook_control_warmed":True,
            "scope":"compile only; no safety or action acceptance evidence"}


def visible(state):
    es = clappers(state)
    return len(es) == 2 and any(control(e)[0] in {"Jump", "Air"} for e in es) and any(
        control(e)[0] in {"Idle", "Walk"} for e in es)


def locked_context(state, forecast, target_iid, game):
    """Current observed instances plus the measured nominal flight clock.

    The clock is a model assumption, never recording future state. All actor
    and delayed-danger geometry still comes from the current full forecast.
    """
    es = clappers(state)
    target = next((e for e in es if e.get("iid") == target_iid), None)
    if len(es) != 2 or target is None or control(target)[0] not in {"Idle", "Walk"}:
        return None
    buddy = next(e for e in es if e is not target)
    rs = getattr(forecast, "rs", None)
    now = None if rs is None else getattr(rs.trk, "now", {}).get(buddy["iid"])
    inst = None if now is None else now[2]
    # The plain jump (CC_JUMP) flies the same decided jump as the jump cast (are_types.clapper: Jump > Air > Slam 2
    # with the shared Jump Aim decision), so the measured land clock below holds for both; Task 179 (#296, the
    # person 11-05: go over the walking one when the corner one jumps; live 786: CC_JUMP decided 2579, Slam 2 2628,
    # 49 frames inside the wall branch's 0.716 .. 0.917 s). Its responsibility keeps the buddy's own family.
    if (inst is None or inst.fam not in ("CC_JUMP_CAST", "CC_JUMP") or inst.dec is None or
            control(buddy)[0] not in {"Jump", "Air"}):
        return None
    from .scene_field_event_shadow import _startup_inputs
    inputs = _startup_inputs()
    dec = inst.dec
    if not all(type(v) in (int,float) and math.isfinite(v) for v in
               (game,rs.trk.T,inst.t0,dec.get("t"),dec.get("x"),dec.get("s"),dec.get("L"))):
        return None
    land_x = float(dec["x"]) + int(dec["s"]) * float(dec["L"])
    branch = "wall" if land_x < inputs.wall_zone[0] or land_x > inputs.wall_zone[1] else "open"
    remaining = float(inputs.clock[branch]["land"]["nominal"]) - (float(rs.trk.T) - float(dec["t"]))
    if not math.isfinite(remaining) or remaining <= 0:
        return None
    f = state["f"]
    if type(f) is not int or f < 0:
        return None
    box = AIR.body_box(target)
    hx = (state.get("hero") or {}).get("pos")
    if box is None or not hx:
        return None
    direction = 1 if .5 * (box[0] + box[2]) > float(hx[0]) else -1
    return {"target": target_iid, "buddy": buddy["iid"], "buddy_family": inst.fam, "buddy_t0": float(inst.t0),
            "buddy_ta":float(game)-(float(rs.trk.T)-float(inst.t0)),
            "buddy_lock_until": float(game) + remaining, "direction": direction, "box": box,
            "move": MoveInstance(target_iid, f, "VAULT_IDLE")}


def _contacts(geo, path):
    scan = geo.scan(path)
    if not scan.complete:
        raise GeometryUnavailable("vault geometry coverage incomplete")
    # Target-only buffered damage rule, conditional on THIS modeled slash.
    # Delayed hazards and every post-contact body contact remain authoritative.
    contact = path.contact_frame
    return [c for c in scan.contacts if not (contact is not None and
            c.owner_iid == geo.move.target_iid and c.kind in {"body", "move"} and
            contact - 2 <= c.frame <= contact)]


def manual_entries(native, state, sim, ctx):
    """Two named actions with table-owned ranges; no online timing grid."""
    cfg=native.runner.chains[V.CHAIN].cfg
    h=state.get("hero") or {};hb=h.get("box");hp=h.get("pos")
    target=next((e for e in clappers(state) if e["iid"]==ctx["target"]),None)
    tp=None if target is None else target.get("pos")
    if (hb is None or hp is None or tp is None or len(hb)!=4 or len(hp)<2 or len(tp)<2 or
            not np.isfinite(np.asarray([*hb,*hp[:2],*tp[:2]],float)).all()):
        return []
    direction=ctx["direction"];box=ctx["box"]
    base={"iid":ctx["target"],"over_dir":direction,"nogo":[],
          "x_end":float(box[2] if direction>0 else box[0])}
    # #298 decision 1: an incoming walker is approached to the existing near jump, never hooked at 9.5 u; Idle and
    # walkers that are not closing keep the whole table (the hook range included)
    incoming=V.incoming_walk(target,float(hp[0]))
    kind,part,gap,root_distance=V.distance_entry(cfg,h,tp,box,direction,sim.params.attack_cooldown,not incoming)
    entries=[]
    far_from=0. if incoming else cfg["HOP_RECIPE"]["root_distance"][1]
    if kind=="near":entries.append(("near",{**base,"near":part,"far":None}))
    elif kind=="hop_hook":entries.append(("hop_hook",{**base,"near":None,"far":part}))
    elif gap>cfg["NEAR_RECIPE"]["box_gap"][1] and far_from<root_distance<=cfg["APPROACH"]["root_distance_max"]:
        # Task 179: farther than both entries but within the approach bound: run in on the ground (table link
        # vault_idle.approach) instead of leaving the planner to its corner (live 786 2580: 11.7 u, hop range 9.5 u);
        # an incoming walker also inside the hook range.
        entries.append(("approach",{**base,"near":None,"far":None,"approach":{"max_f":cfg["APPROACH"]["max_f"]}}))
    native._note("vault_manual_entries",frame=state["f"],box_gap=gap,root_distance=root_distance,incoming=incoming,
                 actions=[kind for kind,_ in entries],scope="fixed table recipes; no grid fallback")
    return entries


def _current_contact(path, frame, target_box, accepted):
    """Revalidate the original contact from current physics; never slide it."""
    from ssbot.knowledge import kinematics as K
    from . import pogo_model as PM
    from .knife_chain_vault_nominal import _down_meets
    if frame is None or target_box is None or not path.origin<=frame<=path.through:
        return None
    swinging=(path.flags&K.F_ATTACKING)!=0
    # Wanderer's DownSlash is an ordinary nail swing (M_NORMAL), not the
    # dedicated down-spike motion modes used by other down-attack types.
    if accepted is None and not swinging[0]:
        starts=np.flatnonzero(swinging[1:]&~swinging[:-1]&
                             ((path.latched&K.B_DOWN)!=0)&((path.flags[:-1]&K.F_GROUND)==0))
        if len(starts):accepted=path.origin+int(starts[0])+1
    if accepted is None or not PM.ACTIVE[0]<=frame-accepted<=PM.ACTIVE[1]:
        return None
    k=frame-path.origin
    if k==0 or path.flags[k]&K.F_GROUND or not swinging[k] or not path.latched[k-1]&K.B_DOWN:
        return None
    return frame if all(_down_meets(path.pos[k],face,target_box) for face in (-1,1)) else None


def _bounce_path(path, sim):
    from .holdfilter import hold_filter_jit
    if path.contact_frame is None:
        raise NominalUnsupported("vault path has no modeled downslash contact")
    k = path.contact_frame - path.origin
    if not 1 <= k < len(path.commands):
        raise NominalUnsupported("vault path does not cover the bounce prefix")
    commands = path.commands[:k].copy()
    lat, hold = hold_filter_jit(commands[None], sim.hold)
    return replace(path, stage="commitment", commands=commands, latched=lat[0], hold_end=hold,
        states=path.states[:, :k+1], box=path.box[:k+1], pos=path.pos[:k+1], flags=path.flags[:k+1],
        check_flags=path.check_flags[:k+1], game=path.game[:k+1], queued_next=int(path.commands[k]), end="bounce")


def manual_jump_watch(offer,frame):
    from .knife_chain_jump import JumpStartWatch
    from .knife_chain_format import MASK_NAMES as B
    run=offer.draft.run;cs=run.v.get("cs")
    if cs is not None:
        targets=tuple(range(cs.f0,min(cs.f0+cs.hop,cs.f_press)))
    elif run.v.get("row") is None:
        return None  # the ground approach link sends running keys only: no ground jump to watch yet
    else:
        row=run.v["row"];first=next((i for i,m in enumerate(row["masks"]) if m&B["J"]),None)
        end=first
        while end is not None and end<len(row["masks"]) and row["masks"][end]&B["J"]:end+=1
        targets=() if first is None else tuple(row["F0"]+i for i in range(first,end))
    return JumpStartWatch(offer.move,frame,targets) if targets else None


def before_send(native, selected, *, frame, target, mask, flags, received_frame, dispatch_clock):
    """Keep the existing calibrated first-J deadline for this ground entry."""
    from .knife_chain_format import MASK_NAMES as B
    from .knife_chain_jump import JumpStartWatch
    if int(mask) != selected.mask:
        return None
    if type(received_frame) is not int:
        native._stop("missing critical vault received frame", frame)
    jump = native._jump_start
    if selected.details.get("distance_vault") and (selected.stage=="manual_commitment" or
                                                   selected.details.get("approach_entry")):
        jump=manual_jump_watch(selected,frame)
    elif selected.stage == "commitment":
        jump = JumpStartWatch.from_path(selected.path, selected.move, frame, native._receipts)
    if jump is None or jump.sent_targets or not int(mask) & B["J"]:
        return None
    reason = None
    if target != min(jump.targets) or received_frame >= target:
        reason = "vault first ground-jump slot already missed"
    elif native.require_send_clock:
        from .knife_chain_deadline import first_jump_clock
        try:
            clock = first_jump_clock(dispatch_clock, target)
        except ValueError as exc:
            native._stop("missing critical vault first-J receive clock: " + str(exc), frame)
        native._note("b2_jump_dispatch_clock", frame=frame, target=target, **clock)
        if clock["late"]:
            reason = "vault first-J calibrated send deadline elapsed"
    if reason is None:
        return None
    return native._abort_hook_dispatch(selected, frame=frame, target=target, mask=mask, flags=flags,
        received_frame=received_frame, event="b2_jump_send_veto", reason=reason)


def propose(native, planner, forecast, prefs):
    """Distance-selected manual table; no skill/contact/tail search.

    Only the ordinary two-frame external-danger gate is queried. The target's
    walking body is not a strike-admission problem here. Every delayed hazard,
    other owner and unknown occupancy stays in that gate. Locked hook motion
    cannot be changed: keep neutral until the actual input-control edge.
    """
    from types import SimpleNamespace
    tick,sim,guard,bombs=native._context
    f,state,game,ground,accepting=tick
    active=native.runner.run is not None and native.runner.run.chain==V.CHAIN
    if (bombs is None or not AIR.complete_hf(state) or sim.fo!=f or sim.f!=f or len(sim.prefix)!=1):
        if active:native._recover("vault current input/danger context unavailable",f)
        return None
    queued,_=native.queued_prefix(f,state)
    if queued is None or int(sim.prefix[0])!=queued:
        if active:native._recover("vault current queued prefix mismatch",f)
        return None
    hook_end=None
    prev_link=native.runner.run.link if active else None
    if active:
        saved=native.runner.run.v.get("_native_vault")
        if saved is None:native._recover("vault run identity missing",f);return None
        move=MoveInstance(**saved["move"])
        if native.post_context is not None:
            native._note("vault_real_bounce_exit",frame=f,move=asdict(move),kind=native.post_context.get("kind","downslash"))
            if native._hit is not None:native.runner.run.v["down_hit_f"]=native._hit
            if native.post_context.get("kind")=="hook_bounce":hook_end=native.post_context
            native.post_context=native._post_seed=native._post_kind=None
        draft=logical_copy(native.runner)
        # #150b: only the same Move's SEEN Harpoon (a successful CLAW send, then the actual clip), still in
        # flight, holds the target-moved watch; a pending, ended or other hook keeps it.
        hs=native._hook_start
        draft.run.v["_hook_locked"]=bool(native.commitment is not None and hs is not None and hs["seen_frame"] is not None
                                         and hs["move"]==move==native.commitment["move"] and native._hook_in_flight(state))
    else:
        ctx=locked_context(state,forecast,getattr(prefs,"target",None),game)
        if ctx is None or not ground or not accepting:return None
        anchor=native._vault_origins.setdefault((ctx["target"],ctx["buddy"],ctx["buddy_t0"]),f)
        move=MoveInstance(ctx["target"],anchor,"VAULT_IDLE")
        if move in native._failed_hook_moves or move in native._vault_completed:return None
        entries=manual_entries(native,state,sim,ctx)
        if not entries:return None
        kind,request=entries[0]
        saved={k:v for k,v in ctx.items() if k not in {"box","move"}}
        saved.update(move=asdict(move),entry_kind=kind)
        draft=native.runner.fork_empty(AirVaultAnchor(native.runner.chains))
        draft.anchor.open(request)
    mask=draft.step(f,state,ground,accepting,t_game=game,sim=sim,guard=guard,bombs=bombs)
    if mask is None or draft.run is None:
        if not active:
            native._note("vault_entry_declined",frame=f,move=asdict(move),
                         attack_cd=(state.get("hero",{}).get("tm") or {}).get("atk_cd"),
                         near=request.get("near"),why=draft.done[-1].v.get("why") if draft.done else None)
            return None  # No successful send/run: retain the opportunity and current owner.
        if native.commitment is not None:native._recover("vault table ended without real target bounce",f)
        else:
            if hook_end is not None:
                # #152: a hook bounce that ends the vault on its own tick (off the body, or any other same-tick end)
                # never reached over: keep the vault failure HP responsibility, as the near-miss hook send does.
                exposure=native._failure_exposure(move,hook_end.get("responsibility_origin",hook_end["origin"]),f,hook_end.get("ta"))
                if native._actual_state is not None:exposure.observe(native._actual_state,game_time=native._clock)
                native._failure_exposures.append(exposure)
                native._note("b2_failure_exposure",frame=f,exposure=exposure.as_dict(),
                             source="hook bounce ended the vault without over; failure responsibility kept")
            native._vault_completed.add(move);native.runner=draft
            native._note("vault_observed_handoff",frame=f,move=asdict(move))
        return None
    draft.run.v.update(_native_vault=saved)
    draft.run.v.setdefault("ta",float(game))
    hook=draft.run.v.get("cs") is not None
    watch=native._hook_start
    pending=(watch is not None and bool(watch["sent_targets"]) and watch["seen_frame"] is None)
    locked=hook and (pending or native._hook_in_flight(state) or (draft.run.link=="far_lock" and not accepting))
    if locked:
        # Finish the existing two-frame CLAW hold even if its first frame is
        # still pending. This is not a new hook or a free-flight prediction.
        planned_claw=(mask&V.B["CLAW"] and watch is not None and f+2 in watch.get("targets",())
                      and f+2 not in watch["sent_targets"])
        if not planned_claw:mask=0
    # A cheap current-step gate, never whole-skill/target-hit certification.
    if not locked:
        current=getattr(getattr(forecast,"rs",None),"trk",None)
        current=None if current is None else current.now.get(move.target_iid)
        if current is None:
            if active:native._recover("vault current external support unavailable",f)
            return None
        try:
            plan=SimpleNamespace(iid=move.target_iid,move=move,origin=f,entry_k=0,press_k=None,contact_frame=None)
            path=AIR.model_path(sim,plan,np.array([mask],np.int64),game)
            scan=B2Geometry(forecast,f,move,current[2]).preflight(path)
            if not scan.complete or scan.contacts:
                native._note("vault_external_step_rejected",frame=f,first=None if not scan.contacts else asdict(scan.contacts[0]))
                if active:native._recover("vault current external danger",f)
                return None
        except (NominalUnsupported,GeometryUnavailable) as exc:
            native._note("vault_external_step_unchecked",frame=f,reason=str(exc))
            if active:native._recover("vault external danger unknown",f)
            return None
    if move.family=="VAULT_IDLE":
        native._vault_responsibility[move]=(MoveInstance(saved["buddy"],move.antic_frame,saved.get("buddy_family","CC_JUMP_CAST")),
                                            saved["buddy_ta"])
    stage="manual_commitment" if not active else "active"
    approach=draft.run.link=="approach"
    # Task 179: the approach just named its table entry. That entry's first ground jump / hook window starts on
    # THIS send, so sent() arms the same watches a fresh manual entry arms, and before_send keeps the first-J slot.
    approach_entry=prev_link=="approach" and draft.run.link in ("near","far")
    return B2Offer(stage,None,draft,int(mask),0.,move,
        {"manual_air":True,"distance_vault":True,"vault_near":not hook and not approach,"vault_hook":hook,
         "vault_approach":approach,"approach_entry":approach_entry,
         "entry_kind":"hop_hook" if hook else "approach" if approach else "near","phase":draft.run.link,
         "predicted_bounce":None,"miss_hook":bool(draft.run.v.get("fallback_hook")),
         "safety_basis":"explicit manual distance policy; no skill/contact/tail prediction; external current-step gate only"})
