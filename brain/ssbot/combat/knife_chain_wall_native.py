"""Wall-side successors of an OBSERVED own target hit and bounce.

L2 supplies the target/contact intent. Each landing or next knife is a separate
finite transaction, checked with all owners and actual S0/HF/queued input. No
wall cling, sustained wallward fallback, fabricated antic or future-hit credit.
"""
from dataclasses import asdict, replace
import numpy as np
from ssbot.knowledge import kinematics as K
from .knife_chain_air import AirAnchor, model_path
from .knife_chain_b2 import B2Offer
from .knife_chain_eval import Run
from .knife_chain_geometry import B2Geometry, GeometryUnavailable
from .knife_chain_nominal import NominalUnsupported
from .knife_chain_format import MASK_NAMES as B
from . import knife_chain_transfer as T
from . import knife_chain_wall_pressure as W


def _real_bounce(n, state, iid):
    if T.bounce_target(state) == iid:
        return state['f']
    p = n.post_context
    if (p is not None and p['move'].target_iid == iid and p.get('hit') is not None
            and p.get('bounce') == state['f'] and p.get('hit') == n._hit):
        return p['bounce']
    return None


def _source_finished(n, state, ctx):
    """Confirmed source death or observed hammer-off; absence stays unknown."""
    iid = ctx['intent'].target
    for e in state.get('ents') or ():
        hp = e.get('hp')
        if e.get('iid') == iid and (e.get('is_dead') is True or
                (type(hp) in (int, float) and np.isfinite(hp) and hp <= 0)):
            return True
    for ev in state.get('ev') or ():
        d = ev.get('d') or {}
        if (ev.get('k') == 'hit' and ev.get('f', state['f']) == state['f']
                and d.get('dead') is True and d.get('ent', d.get('iid')) == iid):
            return True
    return not T.bounce_tail_pending(state, ctx['goal'], n._clock)


def _clear_transaction(n):
    # Preserve actual receipts, HoldFilter and queued commands for the next owner.
    n.commitment = n.post_context = n._post_seed = n._post_kind = None
    n._hook_start = n._jump_start = n._committed_future = None
    n._press = n._accepted = n._hit = None


def _finish(n, why):
    ctx = n._wall_pressure
    if ctx is not None:
        g = ctx['goal']
        n._transfer_finished.add((g.caster, g.cast_fa))
    _clear_transaction(n)
    n._wall_pressure = None
    n._transfer_ready = False
    n._abandon(why)


def prepare_goal(n, state, prefs, *, handoff):
    """Consume a same-focus L2 intent only at a verified physical boundary."""
    if n.arm != 'B' or not handoff or n.recovery is not None or getattr(prefs, 'want_bind', False):
        return False
    ctx = getattr(n, '_wall_pressure', None)
    pressure = getattr(prefs, 'wall_pressure', None)
    g = n._transfer_goal
    if ctx is None:
        if (n.commitment is not None or pressure is None or g is None
                or g.source_kind != 'BOUNCE' or g.target != g.caster
                or pressure.target != g.caster or getattr(prefs, 'target', None) != pressure.target
                or getattr(prefs, 'entry_attack', None) is not None
                or pressure.target in getattr(prefs, 'no_hit', ())):
            return False
        bounce = _real_bounce(n, state, pressure.target)
        if bounce is None or g.responsibility in n._failed_hook_moves:
            return False
        ctx = n._wall_pressure = {'goal':g, 'intent':pressure, 'bounce':bounce,
            'stroke':0, 'proposal':None, 'sent':False, 'source_signature':None,
            'source_ta':g.cast_ta, 'landing':False}
        _clear_transaction(n)
        n._abandon('real bounce: wall-side L2 successor')
        n._note('wall_pressure_enter', frame=state['f'], target=pressure.target,
                kind=pressure.kind, wall_side=pressure.wall_side, bounce=bounce,
                source_move=asdict(g.responsibility), geometry_candidate=True)
    elif ctx.get('yielded') or ctx.get('landing'):
        # This is source-hazard bookkeeping, not a keyboard owner. It must not
        # clear a different new target's commitment when the old hammer ends.
        if _source_finished(n, state, ctx):
            n._transfer_finished.add((ctx['goal'].caster, ctx['goal'].cast_fa))
            n._wall_pressure = None
            n._note('wall_pressure_residual_off', frame=state['f'], target=ctx['intent'].target)
        return False
    elif n.post_context is not None:
        bounce = _real_bounce(n, state, ctx['intent'].target)
        if bounce is not None and bounce != ctx['bounce']:
            _clear_transaction(n)
            n._abandon('real wall-side hit+bounce: next stroke decision')
            physical = n._observed_transfer_move(state, ctx['intent'].target, 'CC_SLAM')
            if physical is not None:
                move, ta = physical
                ctx['goal'] = T.TransferGoal(move.target_iid, move.target_iid, bounce,
                                             ta, 'BOUNCE', move)
                ctx['source_ta'] = ta
            ctx.update(bounce=bounce, stroke=ctx['stroke']+1, proposal=None,
                       sent=False, source_signature=None, landing=False)
            n._note('wall_pressure_real_bounce', frame=state['f'], target=ctx['intent'].target,
                    bounce=bounce, stroke=ctx['stroke'], actual=True)
    allowed = (pressure is not None and pressure.target == ctx['intent'].target
               and getattr(prefs, 'target', None) == pressure.target
               and getattr(prefs, 'entry_attack', None) is None
               and pressure.target not in getattr(prefs, 'no_hit', ()))
    if not allowed and n._press is None:
        # Stop authorising new old-target knives; retain only the observed
        # source's residual danger while ordinary/new-target control resumes.
        _clear_transaction(n)
        n._abandon('L2 wall intent withdrawn: keys handed back with source residual')
        ctx.update(yielded=True, proposal=None, sent=False)
        n._transfer_ready = False
        return False
    # A new L2 target wins at the actual old hammer-off boundary, never by
    # dropping the old source's residual hazard while a strike is in flight.
    if (n.commitment is None and getattr(prefs, 'target', None) != ctx['intent'].target
            and _source_finished(n, state, ctx)):
        _finish(n, 'wall-side residual hammer off: tactical target handoff')
        return True
    if (pressure is not None and pressure.target == ctx['intent'].target
            and n.commitment is None):
        ctx['intent'] = pressure
    n._transfer_ready = False
    return True


def _reject(n, state, reason):
    ctx = n._wall_pressure
    n._note('wall_pressure_rejected', frame=state['f'], reason=reason,
            target=ctx['intent'].target, stroke=ctx['stroke'])
    n._failed_hook_moves.add(ctx['goal'].responsibility)
    n._decline_source_tail(ctx['goal'], state)
    if n.commitment is not None:
        n._recover(reason, state['f'])
    else:
        _finish(n, reason)
    return None


def _plan(ctx, state, game):
    # fa is the ACTION STROKE's actual bounce boundary, never a new enemy antic.
    p = ctx['intent']
    return T.TransferPlan(p.target, p.target, ctx['goal'].cast_fa,
        ctx['bounce'], game, B['R'] if p.wall_side > 0 else B['L'],
        10000, 10000, 10000, False, state['f'], 0)


def propose(n, state, game, sim, forecast, prefs, ground):
    ctx = n._wall_pressure
    if ctx is None or ctx.get('yielded') or ctx.get('landing'):
        return None  # ordinary owns the keys; residual cleanup is prepare_goal's job
    iid = ctx['intent'].target
    queued, _ = n.queued_prefix(state['f'], state)
    if (queued is None or sim.fo != sim.f or sim.f != state['f']
            or len(sim.prefix) != 1 or int(sim.prefix[0]) != queued):
        return _reject(n, state, 'wall-side actual input/prefix unavailable')
    source = next((e for e in T.clappers(state) if e['iid'] == iid), None)
    rs = getattr(forecast, 'rs', None)
    current = None if rs is None else getattr(rs.trk, 'now', {}).get(iid)
    if source is None or current is None:
        return _reject(n, state, 'wall-side source support unavailable')
    if state['f'] - ctx['bounce'] > n.profile.max_frames:
        return _reject(n, state, 'wall-side stroke exceeded original frame limit')
    p = _plan(ctx, state, game)
    physical = n._observed_transfer_move(state, iid, 'CC_SLAM')
    if T.control(source)[0] in T.AIR_ATTACK_STATES and physical is None:
        # A stored real-bounce source can supply the existing causal identity;
        # a missing/mismatched current slam clock is never a new permission.
        if (ctx['goal'].responsibility.target_iid != iid or
                ctx['goal'].responsibility.family != 'CC_SLAM' or
                not n._transfer_source_matches(rs, ctx['goal'])):
            return _reject(n, state, 'wall-side current slam identity/clock unavailable')
        physical = (ctx['goal'].responsibility, ctx['goal'].cast_ta)
    if T.control(source)[0] in T.AIR_ATTACK_STATES:
        observed_move, observed_ta = physical
        observed_goal = T.TransferGoal(iid, iid, ctx['bounce'], observed_ta,
                                       'BOUNCE', observed_move)
        if not n._transfer_source_matches(rs, observed_goal):
            return _reject(n, state, 'wall-side observed/tracked slam clocks disagree')
    sig = (T.control(source)[0], None if physical is None else physical[0].antic_frame)
    proposal = ctx['proposal']
    # Before A is in flight, an observed source phase is a real new decision.
    # Replanning never alters an already queued attack or retimes a sent one.
    hf = (state.get('act') or {}).get('hf') or {}
    attack_in_flight = bool((int(sim.prefix[0]) | int(hf.get('latched', 0)) |
                             int(hf.get('desired', 0))) & B['A'])
    replan = proposal is None or (not ctx['sent'])
    if (proposal is not None and ctx['source_signature'] != sig
            and n._press is None and not attack_in_flight):
        replan = True
    if replan and physical is not None:
        move, ta = physical
        ctx['goal'] = T.TransferGoal(iid, iid, ctx['bounce'], ta, 'BOUNCE', move)
        ctx['source_ta'] = ta
    try:
        geo = B2Geometry(forecast, state['f'], p.move, current[2])
        if replan:
            declines = []
            proposal = None
            # Two tactical branches, not a timing tree: try the verified gap
            # landing first, then one rear-contact recipe if landing is blocked.
            for allow_landing in (True, False):
                candidate = W.propose(sim, state, game, ctx['intent'], p,
                    max_frames=min(96, n.profile.max_frames), allow_landing=allow_landing)
                if candidate is None:
                    declines.append('no finite '+('landing/contact' if allow_landing else 'rear-contact')+' recipe')
                    continue
                contact = candidate.contact_frame
                path = candidate.path
                if contact is not None:
                    cp = replace(p, press_k=candidate.press_frame-state['f'], contact_frame=contact)
                    parent = model_path(sim, cp, candidate.commands, game, contact=contact-state['f'])
                    # No hypothetical protection in pre-contact admission.
                    bad = n._query(forecast, p.move, path, contact_frame=contact, geometry=geo)
                    region = W._terrain(sim, T.body_box(source), ctx['intent'].wall_side)
                    if region is None:
                        declines.append('continuation terrain unavailable')
                        break
                    exits = None if bad else n._continuations(parent, sim, geo, p.move,
                        wall_validator=lambda future: W._wall_free(future, sim, region[3]))
                    if bad or exits.verdict != 'pass':
                        declines.append('rear knife path/continuations blocked')
                        break  # repeating the same stomp recipe cannot repair it
                    # Finite neutral wait for the real contact/bounce STATE.
                    # Same selected-strike preflight as the existing transfer;
                    # this does not extend/re-time the actual attack slot.
                    candidate = replace(candidate, commands=np.r_[candidate.commands,np.zeros(4,np.int64)])
                else:
                    scan = geo.scan(path)
                    if not scan.complete or scan.contacts:
                        declines.append('wall-gap landing path blocked')
                        continue
                proposal = candidate
                break
            else:
                proposal = None
            if proposal is None or (declines and 'rear knife path/continuations blocked' in declines):
                return _reject(n, state, '; '.join(declines) or 'no verified wall-side successor')
            ctx.update(proposal=proposal, source_signature=sig, sent=False,
                       admitted_frame=state['f'])
            n._note('wall_pressure_admitted', frame=state['f'], target=iid,
                    kind=proposal.kind, recipe=proposal.recipe, stroke=ctx['stroke'],
                    through=path.through, contact=proposal.contact_frame, landing=proposal.landing_frame,
                    floor_span=proposal.floor_span, earlier_declines=declines,
                    scope='finite conditional segment; no actual hit credit')
        # Ground-side successor yields keys to the existing ordinary side-slash
        # planner after ACTUAL landing; keep a residual Run until hammer-off.
        physical = np.asarray(sim.start).reshape(K.K)
        if proposal.kind == 'side' and ground and physical[K.GROUND] > 0:
            region = W._terrain(sim, T.body_box(source), ctx['intent'].wall_side)
            x = float(physical[K.PX])
            span = None if region is None else region[0]
            if span is None or not span[0] <= x <= span[1]:
                return _reject(n, state, 'observed landing is outside current wall-gap span')
            neutral = model_path(sim, p, np.zeros(1, np.int64), game)
            scan = geo.scan(neutral)
            if not scan.complete or scan.contacts or not W._wall_free(neutral, sim, region[3]):
                return _reject(n, state, 'observed wall-gap ground handoff blocked')
            if not ctx['landing']:
                _clear_transaction(n)
                n._abandon('actual wall-gap landing: ordinary owns the keys')
                ctx.update(landing=True, yielded=True)
                n._transfer_ready = False
                # Landing is an actual ownership boundary. Later ordinary
                # jumps/steps/source phases cannot restart this old stroke.
                n._note('wall_pressure_ground_handoff', frame=state['f'], target=iid,
                        floor_span=span, actual_ground=True, next='ordinary side-slash rows')
            if _source_finished(n, state, ctx):
                _finish(n, 'wall-side ground slash handoff after residual hammer off')
            return None
        if proposal.press_frame is not None and n._press is None and state['f']+2 > proposal.press_frame:
            return _reject(n, state, 'wall-side first attack absolute slot missed; no retiming')
        if proposal.contact_frame is not None and state['f'] > proposal.contact_frame+2:
            return _reject(n, state, 'wall-side real hit+bounce missing; no model bounce credit')
        mask = proposal.mask_at(state['f']+2)
        if mask is None:
            return _reject(n, state, 'wall-side absolute row ended without actual landing/hit+bounce')
        commands = np.asarray([proposal.mask_at(F) for F in range(state['f']+2,
                            min(state['f']+3, proposal.F0+len(proposal.commands)-1)+1)],np.int64)
        short = model_path(sim, p, commands, game)
        body_region = W._terrain(sim, T.body_box(source), ctx['intent'].wall_side)
        if body_region is None or not W._wall_free(short, sim, body_region[3]):
            return _reject(n, state, 'wall-side current step touches wall or geometry unknown')
        if (n._press is not None and proposal.contact_frame is not None
                and short.through > proposal.contact_frame):
            # Already-sent strike: preserve the existing transfer contact
            # contract while waiting <=2 frames for real hit+bounce. Other
            # owners AND target delayed hazards are still checked without pogo.
            check = geo.preflight(short)
            if not check.complete:
                return _reject(n, state, 'wall-side strike observation coverage incomplete')
            bad = check.contacts
        else:
            bad = n._query(forecast, p.move, short, contact_frame=proposal.contact_frame, geometry=geo)
        if bad:
            return _reject(n, state, 'wall-side current all-owner path blocked')
    except (GeometryUnavailable, NominalUnsupported, TypeError, ValueError, OverflowError) as exc:
        return _reject(n, state, 'wall-side geometry unavailable: '+str(exc))
    draft = n.runner.fork_empty(AirAnchor())
    variables = dict(n.runner.chains[T.PROGRAM].vars)
    variables.update(p.variables())
    variables['_wall_pressure'] = {'target':iid,'stroke':ctx['stroke'],
        'kind':proposal.kind, 'F0':proposal.F0, 'press':proposal.press_frame,
        'contact':proposal.contact_frame, 'landing':proposal.landing_frame}
    # The source table can replay every admitted key from its own Run snapshot;
    # the private proposal is not a second hidden keyboard controller.
    variables['row'] = {'F0':proposal.F0,'masks':proposal.commands.tolist(),
                        'press_F':proposal.press_frame,'contact_frame':proposal.contact_frame}
    draft.run = Run(T.PROGRAM, 'bounce_tail', variables)
    from .knife_chain_eval import X
    obs = T._observation(p,state,game,T.body_box(source),ground,
                         T.head_clearance(n.runner.chains[T.PROGRAM].cfg))
    try:
        table_mask = draft.eval_link(X(draft,draft.run,obs))
    except (NominalUnsupported,TypeError,ValueError,KeyError) as exc:
        return _reject(n,state,'wall-successor table row unavailable: '+str(exc))
    if table_mask != mask:
        return _reject(n,state,'wall-successor table and proposed key disagree')
    n._transfer_responsibility[p.move] = (ctx['goal'].responsibility, ctx['source_ta'])
    return B2Offer('manual_commitment' if not ctx['sent'] else 'active',
        path if replan else short, draft, mask, 0., p.move,
        {'manual_air':True,'wall_pressure':True,'kind':proposal.kind,
         'stroke':ctx['stroke'],'phase':'wall_'+proposal.kind,
         'predicted_bounce':proposal.contact_frame,'source_move':asdict(ctx['goal'].responsibility),
         'finite_segment':True})


def sent(n, selected, result):
    if selected is None or not selected.details.get('wall_pressure'):
        return
    ctx = getattr(n, '_wall_pressure', None)
    if ctx is None:
        return
    if result.chain_outcome == 'sent':
        ctx['sent'] = True
    else:
        ctx['proposal'] = None


def preferences(n, prefs):
    """Refine only L2's same-target style with the admitted physical recipe.

    This remains a preference: the actual floor and all-owner current path are
    checked again before ground handoff. A cached span is not a safety permit.
    """
    from .tactics.modes import WallPressure, wall_pressure_prefs
    ctx = getattr(n, '_wall_pressure', None)
    if ctx is None or ctx.get('yielded') or getattr(prefs, 'target', None) != ctx['intent'].target:
        return replace(prefs)
    p = ctx['proposal']
    intent = ctx['intent'] if p is None else WallPressure(ctx['intent'].target, p.kind,
                ctx['intent'].wall_side, p.floor_span, geometry_candidate=True)
    return wall_pressure_prefs(prefs, intent)
