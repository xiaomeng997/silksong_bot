"""Existing Idle-vault table inside the manual-air B2 transaction owner.

The optional table shares one dispatch/receipt/budget lifecycle with the air and
transfer tables. It neither chooses a tactical target nor sends keys. Near
entries use a fresh model path; the far-hook entry remains unavailable.
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
    """Bind the unchanged four tables together; loading never starts a run."""
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
    _,diag=near_proposals(sim,box,1)
    V.side_meets(30.,5.,1,box)
    _down_meets(np.array([30.,8.]),1,box)
    return {"family":"vault_near","ms":(time.perf_counter()-started)*1000.,
            "proposal_rows_warmed":diag["generated"],"scope":"compile only; no safety or action acceptance evidence"}


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
    if (inst is None or inst.fam != "CC_JUMP_CAST" or inst.dec is None or
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
    return {"target": target_iid, "buddy": buddy["iid"], "buddy_t0": float(inst.t0),
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


def before_send(native, selected, *, frame, target, mask, flags, received_frame, dispatch_clock):
    """Keep the existing calibrated first-J deadline for this ground entry."""
    from .knife_chain_format import MASK_NAMES as B
    from .knife_chain_jump import JumpStartWatch
    if int(mask) != selected.mask:
        return None
    if type(received_frame) is not int:
        native._stop("missing critical vault received frame", frame)
    jump = native._jump_start
    if selected.stage == "commitment":
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
    """Offer the selected target's near route; commit remains in B2.sent()."""
    from .knife_chain_vault_entry import near_proposals
    from .knife_chain_vault_nominal import compile_near
    tick, sim, guard, bombs = native._context
    f, state, game, ground, accepting = tick
    active = native.runner.run is not None and native.runner.run.chain == V.CHAIN
    if (bombs is None or not AIR.complete_hf(state) or type((state.get("hero") or {}).get("hero_accepting_input")) is not bool
            or sim.fo != f or sim.f != f or len(sim.prefix) != 1):
        if active: native._recover("vault current model input unavailable", f)
        return None
    queued, _ = native.queued_prefix(f, state)
    if queued is None or int(sim.prefix[0]) != queued:
        if active: native._recover("vault current queued prefix mismatch", f)
        return None
    if active:
        saved = native.runner.run.v.get("_native_vault")
        if saved is None:
            native._recover("vault run identity missing", f)
            return None
        move = MoveInstance(**saved["move"])
        current_buddy=getattr(getattr(forecast,"rs",None),"trk",None)
        current_buddy=None if current_buddy is None else current_buddy.now.get(saved["buddy"])
        instance=None if current_buddy is None else current_buddy[2]
        if instance is not None and (instance.fam!="CC_JUMP_CAST" or instance.t0!=saved["buddy_t0"]):
            native._recover("vault buddy changed the bound jump-cast instance",f)
            return None
        # The real bounce releases B2's strike commitment, then this SAME table
        # supplies over/fall/ground. There is no model-credited bounce here.
        if native.post_context is not None:
            native._note("vault_real_bounce_exit", frame=f, move=asdict(move))
            if native._hit is not None:
                native.runner.run.v["down_hit_f"]=native._hit
            native.post_context = native._post_seed = native._post_kind = None
        actual=logical_copy(native.runner)
        mask=actual.step(f,state,ground,accepting,t_game=game,sim=sim,guard=guard,bombs=bombs)
        if mask is None or actual.run is None:
            if native.commitment is not None:
                native._recover("vault table ended before real target bounce",f)
            else:
                native._note("vault_observed_handoff",frame=f,move=asdict(move))
                native._vault_completed.add(move)
                native.runner=actual
            return None
        if native.commitment is not None:
            # The committed near row is fixed until REAL bounce. Recheck the
            # current prefix/next commands without synthesizing a second hit
            # or demanding another attack edge after the accepted press.
            from types import SimpleNamespace
            row=actual.run.v.get("row")
            if row is None:
                native._recover("vault committed near row missing",f)
                return None
            predicted=native.commitment["predicted_bounce"]
            last=max(f+4,predicted or f)
            indices=range(f+2-row["F0"],last+1-row["F0"])
            if min(indices)<0 or max(indices)>=len(row["masks"]):
                native._recover("vault near row ended without real bounce",f)
                return None
            commands=np.array([row["masks"][i] for i in indices],np.int64)
            if int(commands[0])!=int(mask):
                native._recover("vault table/current row mask mismatch",f)
                return None
            plan=SimpleNamespace(iid=move.target_iid,move=move,origin=f,entry_k=0,
                                 press_k=row["press_F"]-f,contact_frame=predicted)
            try:
                path=AIR.model_path(sim,plan,commands,game)
                current=forecast.rs.trk.now.get(move.target_iid)
                if current is None:raise GeometryUnavailable("vault current target absent")
                geo=B2Geometry(forecast,f,move,current[2])
                # Only the initial checked contact remains the conditional
                # buffer anchor; no new or slid hit time is inferred here.
                target=next((e for e in clappers(state) if e["iid"]==move.target_iid),None)
                path.contact_frame=_current_contact(path,plan.contact_frame,None if target is None else AIR.body_box(target),native._accepted)
                if _contacts(geo,path):
                    native._recover("vault current path blocked",f)
                    return None
            except (NominalUnsupported,GeometryUnavailable) as exc:
                native._recover("vault current path unknown: "+str(exc),f)
                return None
            return B2Offer("active",path,actual,int(mask),0.,move,
                {"manual_air":True,"vault_near":True,"phase":actual.run.link,"current_only":True,
                 "safety_basis":"fresh current prefix/row; no model pogo; full original exit checked at entry"})
        choices = [(None, saved)]
    else:
        ctx = locked_context(state, forecast, getattr(prefs, "target", None), game)
        if ctx is None or not ground or not accepting:
            return None
        key=(ctx["target"],ctx["buddy"],ctx["buddy_t0"])
        anchor=native._vault_origins.setdefault(key,f)
        ctx["move"]=MoveInstance(ctx["target"],anchor,"VAULT_IDLE")
        if ctx["move"] in native._failed_hook_moves or ctx["move"] in native._vault_completed:
            return None
        rows, diag = near_proposals(sim, ctx["box"], ctx["direction"], max_results=2)
        native._note("vault_near_proposals", frame=f, diagnostics=diag)
        saved = {k:v for k,v in ctx.items() if k not in {"box", "move"}}
        saved["move"] = asdict(ctx["move"])
        saved["frame_basis"]="first observed vault opportunity; buddy instance identified by its observed t0"
        choices = [({"iid": ctx["target"], "over_dir": ctx["direction"], "near": row.request_entry(),
                     "far": None, "nogo": [], "x_end": float(ctx["box"][2] if ctx["direction"] > 0 else ctx["box"][0])}, saved)
                   for row in rows]
    for request, saved in choices:
        move = MoveInstance(**saved["move"])
        seed = native.runner if active else native.runner.fork_empty(AirVaultAnchor(native.runner.chains))
        try:
            path = compile_near(seed, state, sim, game, request=request, buddy_iid=saved["buddy"],
                                buddy_lock_until=saved["buddy_lock_until"], max_frames=native.profile.max_frames,bombs=bombs)
            draft = path.first_draft
            if draft.run is None:
                if native.commitment is not None:
                    native._recover("vault table ended before real target bounce", f)
                else:
                    native._note("vault_observed_handoff", frame=f, move=asdict(move))
                    native.runner = draft
                return None
            current = forecast.rs.trk.now.get(move.target_iid)
            if current is None:
                raise GeometryUnavailable("vault target absent from tracker")
            geo = B2Geometry(forecast, f, move, current[2])
            bad = _contacts(geo, path)
            if bad:
                native._note("vault_path_rejected", frame=f, first=asdict(bad[0]), active=active)
                continue
            exits = None
            if not active:
                exits = native._continuations(_bounce_path(path, sim), sim, geo, move)
                if exits.verdict != "pass":
                    native._note("vault_no_exit", frame=f, continuations=asdict(exits))
                    continue
            draft.run.v["_native_vault"] = saved
            draft.run.v.setdefault("ta", float(game))
            # The vault target is Idle. Failure responsibility must instead
            # remain open through the OTHER actor's real jump-cast ending.
            native._vault_responsibility[move]=(MoveInstance(saved["buddy"],move.antic_frame,"CC_JUMP_CAST"),saved["buddy_ta"])
            value = float(prefs.weights.get("hit", 10.)) + native._endpoint(planner, path, prefs)
            return B2Offer("active" if active else "commitment", path, draft, int(path.offered[0]), value, move,
                {"manual_air": True, "vault_near": True, "phase": draft.run.link,
                 "safety_basis": "full original near-vault nominal exit; target contact buffered at most two frames",
                 "predicted_bounce": path.contact_frame, "continuations": None if exits is None else asdict(exits),
                 "assumptions": path.assumptions})
        except (NominalUnsupported, GeometryUnavailable) as exc:
            native._note("vault_path_unchecked", frame=f, reason=str(exc), active=active)
    if active:
        native._recover("vault original exit no longer has a checked path", f)
    return None
