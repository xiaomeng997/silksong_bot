"""SSBOT_FORUM_RUNE_HOOK_EXIT (Task 182, design docs/plans/forum_clapper_committed_chain.md section 4.10; Sol seq 385 - 387): the
empty-hook big-rune exit's ADMISSION and its RECORD-ONLY wiring. Nothing here sends a key; the feature is NOT complete (no
executor / state machine; see 4.10's pending items).

    0 (default)  nothing is computed; the policy is byte-identical.
    2            at the final owner, record only (Recorder.record): the common gate, N1 (the planner's own row, forced), the
                 candidate edges H1 (the chain held the keys on the previous recorded tick, the planner on this one) and H2 (the
                 L2 target's Control entered an evade state from a known previous state; a diagnostic candidate only), the
                 chain's own failure events of this frame with their identity fields as the hand-back cause (unknown when none:
                 an ordinary hand-back or an evade edge is never written as a failed plan), the full entry (gate and an edge)
                 and - only then - the admission, their intersection, the first rejection and the cost. The final owner, keys
                 and send stay the policy's.
    1            refused at import: acting is not implemented.

Admission (admit): the facing side only; every variant of knife_chain_empty_needle.compile_empty (throw 9 / 8 x applied 0 .. 2
frames late), and for each, every branch of the Catch {measured, one frame early (hypothesis)} x the control frame {P + 30 ..
P + 33} (+ the throw's shift; the measured spread of the 173 unhooked presses, air and ground not separable): 8 branches. Each
branch starts from the real prefix / filtered entry (the variant's own state at P), runs hero2's frame rules (_track, the same
constants) to its control, takes the module's control state (_control) and goes on with the kinematic model and no keys
(_trace_events) to the common end E = 37 (press + 2 + 33), all on this tick's game clock (path index i = frame f + i =
t + i / 60). Every branch is checked in full: the module's pure-branch rules (knife_chain_empty_needle._branch_problem: the ray
against the observed bodies, swept contact, ram, horizontal / vertical rows, the terrain reach - rows in the ray band, slopes in
reach); then, on BOTH lanes (the physical pivots and the rendered ones, seq 388 P2-A), every observed Clapper's body ROUTE
(body_routes: the fitted support of its current Control state and fixed successors; no route for a state that can move the root
or past an Idle's first modelled exit - unknown, rejected; never the forecast's constant-velocity targets, seq 388 P2-B) against
the ray band on the frames it can be thrown (RAY_V_MARGIN), the swept box and the ram box, the planner's damage support
(occupied), the lit runes (rune_life margins) and a sideways exit at the branch's control. The first failure, or missing data,
rejects: the package only admits flights among grounded still Clappers. The two short-flight hypotheses are branches, not a
certificate: the lost 1 / 173 record and any other mechanism stay unverified.

Research path (seq 391, record-only; admit's default call is unchanged): admit(..., research=...) - only the Recorder uses it, and
only in mode 2 - first requires the pending-attack gate (pending_attack: none of her attacks may still land and no attack effect
on a Clapper may still be under way, from what is observed; missing evidence is unknown), then lets a body WITHOUT a complete
fitted route use the EMPIRICAL HEIGHT condition instead (height_support: a selected ground-sample reference HEIGHT_REF plus this
study's chosen HEIGHT_MARGIN, never a body certificate), inside HEIGHT_STATES only, with a validity period from the Control FSM's
path and the unfiltered duration samples (a model assumption), every other check unchanged. Its result is a would / candidate
("model-feasible under the empirical height condition"), never an admission and never a send. The Recorder also keeps the C1
candidate as a record (C1Record: the chain's failure hand-back with its Run move and the same-tick failure exposure, bound to the
big circle alive then, cleared by landing, any chain owning the keys again, the target lost, a supervisor or script owner, an
episode or scene change, the circle lit or gone, or a record gap); C1 sends nothing either."""
from __future__ import annotations

import copy
import math
import os
import time
from functools import lru_cache

import numpy as np

from ssbot.knowledge import kinematics as K, hero2 as H2

MODE = (os.environ.get("SSBOT_FORUM_RUNE_HOOK_EXIT", "0") or "0").strip()
if MODE not in ("0", "2"):
    raise ValueError(f"SSBOT_FORUM_RUNE_HOOK_EXIT={MODE!r}: only 0 (off) and 2 (record only) exist; acting (1) is not implemented - "
                     "no executor / state machine yet (design section 4.10)")
RECORD = MODE == "2"

E_IDX = 37                      # the common end as a path index from f: press + 2 (latest late application) + 33 (latest control)
RESTORE = (30, 31, 32, 33)      # control frames after P for the throw at P + 9 (measured spread; the throw's shift is added)
CATCH_SHIFTS = (0, -1)          # the measured Catch; the early-Catch hypothesis (one frame early, a 5-step dash)
RAY_V_MARGIN = 0.3              # the ray band's low edge over a forecast body top (else the body counts as in the ray)
RAM_W = 3.0                     # the dash damager ahead of her (knife_chain_empty_needle's ram box)
HW = 0.25                       # her box half width (the sideways exit)
EVADE_PREFIX = "Evade"          # H2: Control states of an evade (Evade Scuttle ...)
FAIL_EVENTS = ("chain_interrupted", "transfer_no_witness_handback", "b2_recovery")

# ---- seq 391 research path: the empirical height condition (Sol: "a selected ground-sample reference 7.90 + this study's
# chosen margin 0.50"; not the population's raw body maximum, not a model-proven value, not a hard body bound) ----
HEIGHT_REF = 7.90
HEIGHT_REF_SOURCE = ("knowledge/1.0.30000/enemies/forum/ChoirClapper_hitboxes.npz support/CC_CAST/Spell Antic/world_all: the upper "
                     "edge of its highest occupied 0.05 u cell over 3530 recorded instances (a damage-collider union); a selected "
                     "reference, not a body bound")
HEIGHT_MARGIN = 0.50            # this study's chosen margin: an engineering choice, not derived from any geometry
HEIGHT_THRESHOLD = HEIGHT_REF + HEIGHT_MARGIN
HEIGHT_STATES = ("Slam Recover", "Evade Scuttle")    # the domain: their state, standing, clock and walls are checked item by item
FLOOR_Y = 3.015                 # map2.clapper FLOOR (the floor's top)
WALL_L, WALL_R = 14.01, 48.99   # map2.clapper's wall faces
GROUND_TOL = 0.02               # standing: the body bottom within this of the floor, either way (bout 35 F104247: 3.004 vs 3.015)
EVADE_U_S = 15.0                # Control FSM Evade Scuttle: SetVelocityByScale 15 (away from its facing)
ESCAPE_RAY = 6.0                # Evade Scuttle's entry RayCast from Centre (offset 0) behind it: a wall this near -> Escape Jump
RECENT_F = 10                   # STATE frames back from f whose hit / freeze events count as an effect still under way (Recoil
#                                 0.15 s = 9 frames, + 1)
ATTACK_BITS = ("nailCharging", "attacking", "altAttack", "upAttacking", "downAttacking", "downSpikeAntic", "downSpiking",
               "parryAttack", "isScrewDownAttacking")
EFFECT_BITS = ATTACK_BITS + ("casting", "castRecoiling", "spellQuake", "focusing", "parrying", "isToolThrowing",
                             "needolinPlayingMemory")
B_NEEDOLIN = 1 << 5             # ssbot.ipc.framing.BUTTONS "needolin" (Control FSM Idle / Walk: CheckHeroPerformanceRegion -> SING)
EFFECT_KEYS = K.B_ATTACK | B_NEEDOLIN | K.B_QUICKCAST
LIFECYCLE_KEYS = ((5, "needolin"), (6, "quickcast"))     # button bits never latched this episode (KeyPlanLog actual / act_on)
CREST = "Wanderer"              # the crest whose attacks the kinematics model holds (seq 392 A: the verified loadout)
ALLY_PASSIVE = ("Dormant", "Away")   # the Forum allies' FSM states seen idle (any other: their attacks are unknown)
RESEARCH_LABEL = "would / candidate: model-feasible under the empirical height condition; not an admission, never sent"


@lru_cache(maxsize=1)
def _raw_durations() -> dict:
    """{Control state: (non-zero minimum, maximum)} in game frames from the fit's duration histograms (knowledge clapper_m2.json
    durations, unfiltered - a 0 is an Evade Scuttle entry's Escape Jump pass-through, never a duration). Know.durations' filtered
    lo (share >= 0.5 %, >= 0.6 x mode) is not used."""
    from .knife_chain_transfer import _body_knowledge
    know = _body_knowledge()[0]
    out = {}
    for st, h in know.dur.items():
        ks = [int(k) for k, v in h.items() if int(k) > 0 and v > 0]
        if ks:
            out[st] = (min(ks), max(ks))
    return out


def height_support(e, E=E_IDX):
    """(valid_to, info) or (None, why): the research path's empirical height condition for one observed Clapper without a complete
    fitted route. Its DOMAIN, each item checked on this STATE (else None, unknown): the Control state in HEIGHT_STATES with a finite
    clock under the state's raw maximum; a well-formed observed body box whose top is already at or under HEIGHT_THRESHOLD (seq 392
    B); standing (body bottom within GROUND_TOL of the floor either way, no vertical speed); a Slam Recover
    still (vx 0) and past its frame 0 even with one frame of clock tolerance (no hammer tail of its own), an Evade Scuttle at
    EVADE_U_S away from its facing; and every root x it can reach in E + 1 frames ESCAPE_RAY or more from BOTH walls (no Escape
    Jump at a later Evade entry, whichever way it then faces - a single-point exclusion re-checked on every STATE, never
    generalised). Its VALIDITY PERIOD, a model assumption labelled per step in info: the decompiled Control FSM's paths (a take-off
    only Jump Antic -> Jump Aim -> Jump; a hammer collider only Slam Antic -> Slam 0 -> Slam 1; a new small-rune row only Spell
    Antic -> Cast 1 -> Cast 2; the state may end at once into an antic - Evade: After Scuttle -> Close / Far; Recover: Idle ->
    Avoid Type / Dmg Attack) with the unfiltered non-zero minimum durations and one frame of clock tolerance; valid through the
    frame before the earliest take-off, hammer or new small-rune row. It governs the body height only: the damage support, the
    runes and every other check stay."""
    from .slam_play import control
    from .knife_chain_air import body_box
    cs = [c for c in e.get("fsms") or () if c.get("name") == "Control"]
    if len(cs) != 1:
        return None, "Control clock unknown"
    st, tin = control(e)
    if st not in HEIGHT_STATES:
        return None, f"state {st} outside the height domain"
    tin = cs[0].get("t")
    if type(tin) not in (int, float) or not math.isfinite(tin) or tin < 0:
        return None, "Control clock unknown"
    raw = _raw_durations()
    need = (st, "Jump Antic", "Slam Antic", "Slam 0", "Spell Antic", "Cast 1")
    if any(x not in raw for x in need):
        return None, "duration samples missing"
    k = int(round(float(tin) * 60.0))
    if k >= raw[st][1]:
        return None, f"clock {k} at or past the raw maximum {raw[st][1]} of {st}"
    pos, vel, flip = e.get("pos"), e.get("vel"), e.get("flipX")
    if (not isinstance(pos, (list, tuple)) or len(pos) < 2 or not isinstance(vel, (list, tuple)) or len(vel) != 2
            or type(flip) is not bool or any(type(v) not in (int, float) or not math.isfinite(v) for v in (*pos[:2], *vel))):
        return None, "position / velocity / facing unknown"
    try:
        b = body_box(e)
    except (TypeError, ValueError, OverflowError):
        b = None
    if b is None or len(b) != 4 or not np.isfinite(np.asarray(b, float)).all():
        return None, "body box unknown"
    if not (float(b[0]) < float(b[2]) and float(b[1]) < float(b[3])):
        return None, "body box malformed"
    # seq 392 B: the observed body itself must already be under the condition (never a later frame only), and standing is
    # two-sided: the bottom within GROUND_TOL of the floor either way (a body sunk or lifted further is outside the domain)
    if float(b[3]) > HEIGHT_THRESHOLD:
        return None, f"the observed body top {float(b[3]):.3f} over the empirical height {HEIGHT_THRESHOLD:.2f}"
    if abs(float(b[1]) - FLOOR_Y) > GROUND_TOL or float(vel[1]) != 0.0:
        return None, "not standing (body bottom off the floor by more than GROUND_TOL, or a vertical speed)"
    face = 1 if flip else -1
    x, vx = float(pos[0]), float(vel[0])
    if st == "Slam Recover":
        if vx != 0.0:
            return None, "Slam Recover moving"
        if k - 1 < 1:
            return None, "Slam Recover frame 0 within the clock tolerance (hammer tail)"
        xs = (x,)
    else:
        if abs(abs(vx) - EVADE_U_S) > 1e-6 or vx * face > 0:
            return None, "Evade Scuttle not at 15 u/s away from its facing"
        xs = (x, x + vx * (E + 1) / 60.0)
    wall = min(min(v - WALL_L, WALL_R - v) for v in xs)
    if wall < ESCAPE_RAY:
        return None, f"a wall {wall:.3f} u from a reachable root (Escape Jump possible)"
    rem = raw[st][0] - k - 1
    risen = rem + raw["Jump Antic"][0] + 1
    hammer = rem + raw["Slam Antic"][0] + raw["Slam 0"][0]
    bombs = rem + raw["Spell Antic"][0] + raw["Cast 1"][0]
    valid_to = min(risen, hammer, bombs) - 1
    info = {"state": st, "clock_k": k, "state_end_from": rem, "take_off_from": risen, "hammer_from": hammer, "new_bombs_from": bombs,
            "valid_to": valid_to, "wall_u": round(wall, 3), "threshold": HEIGHT_THRESHOLD,
            "basis": "[FSM] decompiled Control paths, [RAW] unfiltered non-zero minima (clapper_m2.json), [TIME] this STATE's clock "
                     "(one frame of tolerance), [LOCAL] walls from the reachable roots: a model assumption for the body height only"}
    return valid_to, info


def pending_attack(sim, hero, raws, f, iids, keylog=None) -> tuple[bool, str | None]:
    """(True, None) when what is observed shows none of her attacks or effects still to land and no attack effect on a Clapper still
    under way (seq 391's actual gate for the research path, seq 392 A), else (False, why); missing evidence is unknown (False), never
    "none". The oracle exports no object of hers or of an ally (the entities are health managers and sources that hurt HER), so an
    effect already thrown cannot be seen; the gate instead requires a LOADOUT AND INPUT LIFECYCLE that cannot leave one, checked on
    this tick's evidence:
      her cstate (STATE hero.cstate against kinematics.cstate_names) with none of EFFECT_BITS (the nail's colliders act only while
      cState.attacking; casting, the parry, a tool throw, binding and a Needolin performance have their own bits);
      the crest CREST (the one whose attacks the kinematics model holds), no tool equipped (hero.tools all empty, tools_extra 0)
      and the silk skill FSM (hero.spell) in Idle;
      the episode's latched input history (keylog, the policy's KeyPlanLog fed with every STATE's act.mask) without any
      LIFECYCLE_KEYS press (the Needolin - the Clapper's Idle / Walk answer a performance with SING - and the quick cast), so no
      effect of theirs can still be out;
      the model start with no attack running or queued (ATTACKING 0, AQ < 0, QQ < 0) and no EFFECT_KEYS in the in-flight prefix
      or in the hold filter (latched, desired, pending);
      the STATE of every frame f - RECENT_F .. f seen (raws: the policy's frame history) with its event list and its allies list:
      every ally in ALLY_PASSIVE (an ally's attacks are not observed either), no hit on an observed Clapper (iids), no hit whose
      target is unknown, no freeze."""
    from . import rune_life
    names = K.cstate_names()
    hero = hero if isinstance(hero, dict) else {}
    cs = hero.get("cstate")
    if not isinstance(cs, (list, tuple)) or not cs or any(type(v) is not int for v in cs):
        return False, "her cstate unknown"
    for n in EFFECT_BITS:
        if n not in names:
            return False, f"cstate bit {n} unknown"
        i = names.index(n)
        if (i >> 6) >= len(cs):
            return False, "her cstate too short"
        if (int(cs[i >> 6]) >> (i & 63)) & 1:
            return False, f"her effect under way ({n})"
    if hero.get("crest") != CREST:
        return False, f"crest {hero.get('crest')!r}: its attack effects are not verified here"
    tools = hero.get("tools")
    if not isinstance(tools, (list, tuple)) or any(x is not None for x in tools) or hero.get("tools_extra") != 0:
        return False, "a tool equipped, or the tool slots unknown (tool effects are not observed)"
    spell = hero.get("spell")
    if not isinstance(spell, (list, tuple)) or not spell or spell[0] != "Idle":
        return False, f"the silk skill FSM not in Idle ({spell[0] if isinstance(spell, (list, tuple)) and spell else 'unknown'})"
    actual, on = getattr(keylog, "actual", None), getattr(keylog, "act_on", None)
    if not isinstance(actual, dict) or not isinstance(on, dict):
        return False, "the episode's latched input history unknown"
    for b, name in LIFECYCLE_KEYS:
        if actual.get(b) or b in on:
            return False, f"the {name} latched this episode (its effects are not observed)"
    S = np.asarray(sim.start, float).reshape(-1)
    if S[K.ATTACKING] > 0:
        return False, "the model start is attacking"
    if S[K.AQ] >= 0:
        return False, "the model start has an attack queued"
    if S[K.QQ] >= 0:
        return False, "the model start has a quick cast queued"
    if any(int(m) & EFFECT_KEYS for m in np.asarray(sim.prefix).reshape(-1)):
        return False, "an attack or effect key in flight"
    if rune_life._held_bits(sim.hold) & EFFECT_KEYS:
        return False, "an attack or effect key in the hold filter"
    for g in range(int(f) - RECENT_F, int(f) + 1):
        st = (raws or {}).get(g)
        if not isinstance(st, dict) or not isinstance(st.get("ev"), list):
            return False, f"the STATE of frame {g} not seen or without its event list (events unknown)"
        allies = st.get("allies")
        if not isinstance(allies, list):
            return False, f"the allies of frame {g} unknown"
        for a in allies:
            if not isinstance(a, dict) or a.get("state") not in ALLY_PASSIVE:
                nm, sa = (a.get("name"), a.get("state")) if isinstance(a, dict) else (None, None)
                return False, f"ally {nm} in {sa} at {g} (an ally's attacks are not observed)"
        for ev in st.get("ev") or ():
            if not isinstance(ev, dict):
                return False, f"an unreadable event at {g}"
            if ev.get("k") == "freeze":
                return False, f"a freeze at {g}"
            if ev.get("k") == "hit":
                d = ev.get("d") if isinstance(ev.get("d"), dict) else {}
                ent = d.get("ent") if type(d.get("ent")) is int else d.get("iid")
                if type(ent) is not int:
                    return False, f"a hit with an unknown target at {g}"
                if ent in iids:
                    return False, f"a hit on {ent} at {g} (its effect may still be under way)"
    return True, None


def _track(x0, bb0, vx0, vy0, d, fs, throw_f, catch_shift, ctrl):
    """hero2.claw_unhooked's frame rules (its constants, unchanged) with the Catch catch_shift frames off the measured one and
    control at P + ctrl (any frame of the measured spread; a later one keeps the Catch's per-step 0.75). catch_shift 0 with the
    measured control is claw_unhooked exactly (tests/test_rune_hook_exit.py)."""
    sh = throw_f - H2.CLAW_THROW_F
    T_F, D_F, C_F = H2.CLAW_THROW_F + sh, H2.CLAW_DASH_F + sh, H2.CLAW_CATCH_F + sh + catch_shift
    fs = list(fs)
    if len(fs) < ctrl or ctrl <= C_F:
        raise ValueError(f"branch control P + {ctrl} needs {ctrl} frames of steps after the Catch at P + {C_F}")
    vx = min(max(vx0, -20.0), 20.0) * H2.CLAW_ANTIC_DECEL[0]
    vy = min(max(vy0, H2.CLAW_VY_CLAMP[0]), H2.CLAW_VY_CLAMP[1]) * H2.CLAW_ANTIC_DECEL[1]
    X, B_, VX, VY = [x0], [bb0], [vx], [vy]
    x, bb = x0, bb0
    for j in range(1, ctrl + 1):
        for _ in range(int(fs[j - 1])):
            if j <= T_F:
                vx *= H2.CLAW_ANTIC_DECEL[0]
                vy *= H2.CLAW_ANTIC_DECEL[1]
            elif j > C_F:
                vx *= H2.CLAW_CATCH_DECEL
            x += vx * H2.FDT
            bb += vy * H2.FDT
        if j == T_F:
            vx = vy = 0.0
        elif j == D_F:
            vx, vy = d * H2.CLAW_SPEED, 0.0
        elif j == C_F:
            vx *= H2.CLAW_CATCH_DECEL
        X.append(x), B_.append(bb), VX.append(vx), VY.append(vy)
    return H2.ClawTrack(np.array(X), np.array(B_), np.array(VX), np.array(VY), ctrl)


def branch_paths(made, sim, d, throw, E=E_IDX):
    """[(catch_shift, control frame after P, physical [n, 2], rendered [n, 2])]: every branch of one compiled variant, pivots from
    P (index 0) through path index E (frame f + E). The lead f .. P is the module's own (made.path)."""
    from . import knife_chain_empty_needle as EN
    from .knife_chain_air import _trace_events
    p = sim.params.vector()
    P_idx = int(made.activation_frame - sim.fo)
    SP = np.asarray(made.path.states[:, P_idx], float)
    sh = throw - H2.CLAW_THROW_F
    steps = EN._lattice(SP, sim.params, max(RESTORE) + sh + 1)
    out = []
    for cs in CATCH_SHIFTS:
        for r in RESTORE:
            rr = r + sh
            tr = _track(float(SP[K.PX]), float(SP[K.PY] - p[K.P_FOOT]), float(SP[K.VX]), float(SP[K.VY]), d, steps, throw, cs, rr)
            phys = np.column_stack((tr.x, tr.bb + p[K.P_FOOT]))
            rend = EN._render(SP, phys, steps, sim.params)
            m = E - (P_idx + rr)
            if m > 0:
                ctrl_state = np.asarray(EN._control(SP, tr, d, sim.params), float)
                game_c = float(made.path.game[P_idx]) + rr * float(sim.params.frame_time)
                st, _bx, ps, _fl, _gm = _trace_events(ctrl_state, np.zeros(m, np.int64), np.zeros(m, np.int64), game_c,
                                                      sim.params.frame_time, p[None, :], sim.terrain.packed())
                phys = np.vstack((phys, np.asarray(st[[K.PX, K.PY], 1:], float).T))
                rend = np.vstack((rend, np.asarray(ps[1:], float)))
            out.append((cs, rr, phys[:E - P_idx + 1], rend[:E - P_idx + 1]))
    return out


def _overlap(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def body_routes(enemies, E=E_IDX):
    """({iid: [E + 1, 4]}, None) or (None, reason): every observed Clapper's body SUPPORT per path index (0 = this STATE's frame):
    knife_chain_transfer.contact_body_witness with hull - the union of the poses its current Control state and its fixed successors
    can take, from their fitted runs and durations, each frame with the previous one. It has no rows for a state that can move the
    root (Walk, Evade, Jump, an attack), without fitted runs, or (Idle) past its first modelled exit; any such frame makes the whole
    route unknown and the admission rejects: this package is only for flights among grounded still Clappers. The forecast's
    targets (the observed box carried at its velocity) are never used for a body route (seq 388 P2-B)."""
    from .knife_chain_transfer import contact_body_witness
    from .slam_play import control
    routes = {}
    for e in enemies or ():
        iid = e.get("iid")
        try:
            w = contact_body_witness(e, E + 1, hull=True)
        except Exception as ex:          # an unreadable entity is unknown, never empty
            return None, f"body route unknown for {iid} ({type(ex).__name__})"
        w = None if w is None else np.asarray(w, float)
        if w is None or w.shape != (E + 1, 4) or not np.isfinite(w).all():
            return None, f"body route unknown for {iid} ({control(e)[0]})"
        routes[int(iid)] = w
    return routes, None


def research_supports(enemies, E=E_IDX):
    """The research path's body supports (seq 391): ({iid: route}, {iid: height info}, None) or (None, None, why). A complete fitted
    route (body_routes' witness) first; a body without one may take the empirical height condition (height_support) only inside
    its domain and only when its validity period covers index E; anything else is unknown and rejects."""
    from .knife_chain_transfer import contact_body_witness
    from .slam_play import control
    routes, heights = {}, {}
    for e in enemies or ():
        iid = e.get("iid")
        try:
            w = contact_body_witness(e, E + 1, hull=True)
        except Exception as ex:          # an unreadable entity is unknown, never empty
            return None, None, f"body route unknown for {iid} ({type(ex).__name__})"
        w = None if w is None else np.asarray(w, float)
        if w is not None and w.shape == (E + 1, 4) and np.isfinite(w).all():
            routes[int(iid)] = w
            continue
        valid_to, hinfo = height_support(e, E)
        if valid_to is None:
            return None, None, f"body route unknown for {iid} ({control(e)[0]}) and no empirical height: {hinfo}"
        if valid_to < E:
            return None, None, f"body route unknown for {iid} and its empirical height holds only to index {valid_to}"
        heights[int(iid)] = hinfo
    return routes, heights, None


def _height_problem(lane, regions):
    """(why or None, margin): one lane's regions against the empirical height condition (HEIGHT_THRESHOLD as the top of every body
    that uses it, at every index; x is not used): the swept boxes, the boxes and the ram boxes on their frames must stay above it,
    the ray band above it plus RAY_V_MARGIN (as _route_problem counts a body top within RAY_V_MARGIN of the band)."""
    boxes, sw, js, rays, ram, on = regions
    low = min(float(boxes[1:, 1].min()), float(sw[:, 1].min()), float(ram[on, 1].min()) if on.any() else float("inf"))
    ray_low = float(rays[:, 1].min())
    margin = min(low - HEIGHT_THRESHOLD, ray_low - HEIGHT_THRESHOLD - RAY_V_MARGIN)
    if low <= HEIGHT_THRESHOLD:
        return f"{lane} region down to {low:.3f}, at or under the empirical height {HEIGHT_THRESHOLD:.2f}", margin
    if ray_low <= HEIGHT_THRESHOLD + RAY_V_MARGIN:
        return f"{lane} ray band down to {ray_low:.3f}, within {RAY_V_MARGIN} of the empirical height", margin
    return None, margin


class _Params:
    """sim.params with its vector() computed once (the admission read it about 80 times a tick; read-only everywhere)."""

    def __init__(self, params):
        self._params = params
        self._v = params.vector()

    def vector(self):
        return self._v

    def __getattr__(self, name):
        return getattr(self._params, name)


class _Sim:
    """A view of this tick's ChainSim with the cached params (every other attribute is the sim's own)."""

    def __init__(self, sim):
        self._sim = sim
        self.params = _Params(sim.params)

    def __getattr__(self, name):
        return getattr(self._sim, name)


def lane_regions(piv, p, d, P_idx, throw, cs):
    """One lane (physical or rendered pivots [E + 1, 2], index i = frame f + i) as the regions it acts through: its boxes, its
    frame-to-frame sweeps (row i - 1 = frame i), the needle's ray band on the frames it can be thrown (P .. P + throw) and the ram
    box on the dash .. Catch frames (knife_chain_empty_needle's ram, from this lane's pivots)."""
    from . import knife_chain_empty_needle as EN
    piv = np.asarray(piv, float)
    boxes = EN._boxes(piv, p)
    sw = EN._sweeps(boxes)
    js = np.arange(P_idx, P_idx + throw + 1)
    # knife_chain_empty_needle._ray_band for every frame at once (the same arithmetic, element by element)
    x = 0.5 * (boxes[js, 0] + boxes[js, 2])
    rays = np.column_stack((np.minimum(x, x + d * EN.RAY_REACH), boxes[js, 1] + EN.RAY_LO, np.maximum(x, x + d * EN.RAY_REACH),
                            boxes[js, 1] + EN.RAY_HI))
    sh = throw - H2.CLAW_THROW_F
    dash, catch = P_idx + H2.CLAW_DASH_F + sh, P_idx + H2.CLAW_CATCH_F + sh + cs
    i_ = np.arange(1, len(piv))
    ram = np.column_stack((np.minimum(piv[:-1, 0], piv[1:, 0]) + min(0.0, RAM_W * d), np.minimum(piv[:-1, 1], piv[1:, 1]) - 1.05,
                           np.maximum(piv[:-1, 0], piv[1:, 0]) + max(0.0, RAM_W * d), np.maximum(piv[:-1, 1], piv[1:, 1]) + 0.45))
    on = (i_ > dash) & (i_ <= catch)
    return boxes, sw, js, rays, ram, on


def _route_problem(lane, regions, routes, d):
    """The body routes against one lane's regions: first the ray band on its frames (the route at the same index; a body top
    within RAY_V_MARGIN of the band's low edge counts), then frame by frame the swept box before the ram box (the route at i,
    which already holds i - 1). The first frame with a problem is reported, with the body and the lane."""
    from .knife_chain_empty_needle import RAY_REACH
    if not routes:
        return None
    boxes, sw, js, rays, ram, on = regions
    ids = list(routes)
    W = np.stack([routes[i] for i in ids])                       # [n, E + 1, 4]
    x = 0.5 * (boxes[js, 0] + boxes[js, 2])
    b = W[:, js]
    near, far = ((b[..., 0] - x, b[..., 2] - x) if d > 0 else (x - b[..., 2], x - b[..., 0]))
    hit = (far >= 0) & (near <= RAY_REACH) & (b[..., 1] < rays[:, 3]) & (b[..., 3] + RAY_V_MARGIN > rays[:, 1])
    if hit.any():
        j = int(np.argmax(hit.any(0)))
        return f"{lane} ray meets body route {ids[int(np.argmax(hit[:, j]))]} at index {int(js[j])}"
    w1 = W[:, 1:]
    c = (sw[:, 0] < w1[..., 2]) & (sw[:, 2] > w1[..., 0]) & (sw[:, 1] < w1[..., 3]) & (sw[:, 3] > w1[..., 1])
    r = on & (ram[:, 0] < w1[..., 2]) & (ram[:, 2] > w1[..., 0]) & (ram[:, 1] < w1[..., 3]) & (ram[:, 3] > w1[..., 1])
    bad = (c | r).any(0)
    if bad.any():
        k = int(np.argmax(bad))
        if c[:, k].any():
            return f"{lane} swept contact with body route {ids[int(np.argmax(c[:, k]))]} at index {k + 1}"
        return f"{lane} ram box meets body route {ids[int(np.argmax(r[:, k]))]} at index {k + 1}"
    return None


def admit(sim, game, bodies, d, fplan, rows, E=E_IDX, enemies=(), research=None):
    """(ok, first rejection or None, info) for an empty hook decided on this tick (sim = this tick's ChainSim: the real start,
    in-flight prefix and hold filter; game = its STATE's game clock t; bodies = the observed Clapper bodies [(iid, box)]; d = her
    facing; fplan = the planner's forecast of this tick (its damage support only); rows = the rune rows of this tick, frames from
    its STATE; enemies = this STATE's Clapper entities, for their body routes). Every dynamic check runs on BOTH lanes of every
    branch, the physical pivots and the rendered ones, on one index (frame f + i; seq 388 P2-A). Read-only.

    research (seq 391; None, the default, is the strict admission unchanged): {"pending": (ok, why)} from pending_attack - the
    research path: the pending-attack gate first, then research_supports (a body without a complete fitted route may take the
    empirical height condition inside its domain) and _height_problem on both lanes of every branch for those bodies; every other
    check as above. Its ok is a would / candidate under the empirical height condition, never an admission."""
    from . import knife_chain_empty_needle as EN
    from . import rune_life
    from .knife_chain_nominal import NominalUnsupported
    info = {"variants": 0, "branches": 0}
    opp = K.B_LEFT if d > 0 else K.B_RIGHT
    held = rune_life._held_bits(sim.hold)
    if any(int(m) & opp for m in np.asarray(sim.prefix).reshape(-1)) or held & opp:
        return False, "opposite side key in flight", info
    if {int(i) for i, _ in bodies} - {int(e.get("iid")) for e in enemies or () if e.get("iid") is not None}:
        return False, "an observed body has no entity for its route", info
    heights = {}
    if research is None:
        routes, why = body_routes(enemies, E)
        if why is not None:
            return False, why, info
    else:
        ok_p, why_p = research.get("pending") or (False, "pending-attack evidence missing")
        info["pending_attack"] = "none observed" if ok_p else why_p
        if not ok_p:
            return False, "pending attack / effect: " + str(why_p), info
        routes, heights, why = research_supports(enemies, E)
        if why is not None:
            return False, why, info
        info["supports"] = {**{str(i): "fitted route" for i in routes}, **{str(i): "empirical height" for i in heights}}
        info["heights"] = {str(i): h for i, h in heights.items()}
        info["height_margin"] = None
    sim = _Sim(sim)
    tk = np.arange(E + 1, dtype=np.float64) * float(sim.params.frame_time)
    rows = np.asarray(rows, np.float64).reshape(-1, 6) if rows is not None and len(rows) else np.zeros((0, 6))
    big = rows[rows[:, 3] > 5.0]
    p = sim.params.vector()
    # seq 392: one dict for this call (one tick, one terrain): knife_chain_empty_needle keeps there the static answers of a variant's
    # identical pre-throw segment (per exact input bytes) and the terrain's rows; every branch-specific check still runs per branch
    shared = {}
    fulls, meta = [], []
    for throw in (9, 8):
        for late in (0, 1, 2):
            tag = f"throw {throw} late {late}"
            try:
                made = EN.compile_empty(sim, float(game), bodies, int(d), throw_frames=throw, activation_delay=late)
            except NominalUnsupported as e:
                return False, f"{tag}: {e}", info
            except ValueError as e:
                return False, f"{tag}: unknown ({e})", info
            info["variants"] += 1
            P_idx = int(made.activation_frame - sim.fo)
            if (1 if made.path.states[K.FACE, P_idx] >= 0 else -1) != d:
                return False, f"{tag}: facing at P is not {d}", info
            lead_phys = np.asarray(made.path.states[[K.PX, K.PY], :P_idx + 1], float).T
            lead_rend = np.asarray(made.path.pos[:P_idx + 1], float)
            for cs, rr, phys, rend in branch_paths(made, sim, d, throw, E):
                btag = f"{tag} catch {cs:+d} control P+{rr}"
                why = EN._branch_problem(phys, rend, bodies, d, throw, sim.params, sim.terrain, catch_shift=cs, p=p, shared=shared)
                if why is not None:
                    return False, f"{btag}: {why}", info
                lanes = {"physical": np.vstack((lead_phys, phys[1:])), "rendered": np.vstack((lead_rend, rend[1:]))}
                for lane, piv in lanes.items():
                    if len(piv) != E + 1:
                        return False, f"{btag}: the {lane} path covers {len(piv) - 1} of {E} frames", info
                    reg = lane_regions(piv, p, d, P_idx, throw, cs)
                    why = _route_problem(lane, reg, routes, d)
                    if why is not None:
                        return False, f"{btag}: {why}", info
                    if heights:
                        why, hm = _height_problem(lane, reg)
                        info["height_margin"] = hm if info["height_margin"] is None else min(info["height_margin"], hm)
                        if why is not None:
                            return False, f"{btag}: {why}", info
                    c = P_idx + rr
                    near = 0.5 * (reg[0][c][0] + reg[0][c][2]) - d * HW
                    for _o, cx, _cy, r, _on, off in big:
                        if off >= c and not d * (near - cx) > r:
                            return False, f"{btag}: {lane} not sideways out of the circle at x {cx:.2f} at control", info
                    fulls.append(reg[0])
                    meta.append(f"{btag} {lane}")
                info["branches"] += 1
    B = np.stack(fulls)
    cx_, cy_ = 0.5 * (B[..., 0] + B[..., 2]), 0.5 * (B[..., 1] + B[..., 3])
    try:
        occ = np.asarray(fplan.occupied(cx_, cy_, tk), bool).reshape(len(B), -1)
    except Exception as e:
        return False, "forecast occupied unavailable: " + type(e).__name__, info
    for k in range(len(B)):
        if occ[k].any():
            return False, f"{meta[k]}: forecast damage support at index {int(np.argmax(occ[k]))}", info
    if len(rows):
        hit = rune_life._box_hits(B, rows, 0, rune_life.MARGIN_BIG, rune_life.MARGIN_BOMB)
        for k in range(len(B)):
            if hit[k].any():
                return False, f"{meta[k]}: rune lit over her at index {int(np.argmax(hit[k]))}", info
    return True, None, info


MAX_GAP = 3            # frames between two recorded ticks for an edge to count (a longer gap: the change may lie in it, unknown)
EVENT_FIELDS = ("event", "frame", "episode", "target", "link", "owner", "reason")
MOVE_EVENTS = ("b2_selected", "b2_nominal_path")    # the chain's own Run move, logged on every tick it proposes


def _move(mv):
    """A logged move dict with its three identity fields, or None."""
    if (isinstance(mv, dict) and type(mv.get("target_iid")) is int and type(mv.get("antic_frame")) is int
            and isinstance(mv.get("family"), str)):
        return {"target_iid": mv["target_iid"], "antic_frame": mv["antic_frame"], "family": mv["family"]}
    return None


class Recorder:
    """SSBOT_FORUM_RUNE_HOOK_EXIT=2: one record per policy tick at its final owner; never a key, never a change to the tick.

    Edges are facts of two consecutive recorded ticks (seq 388 P2-C): H1 needs the previous tick's FINAL key owner to be the chain
    (the owner "chain", or the planner sending a chain row as its own pick) and this tick's to be the planner - a chain row that a
    supervisor or a script overrode never held the keys; H2 needs the same iid observed with a known Control state on the previous
    recorded tick (every observed Clapper is tracked, so a focus switch never reads as a transition) and a gap of at most MAX_GAP
    frames - a first sight, a missing or a stale previous state is unknown, never an edge. The chain's own failure events of the
    hand-back frame keep their identity fields as logged (no field is filled from the current focus).

    seq 391 (record-only research): the C1 candidate as a RECORD (c1, c1_entry) and, on a tick with a full entry or a C1 entry, the
    research path's would / candidate (research: admit(..., research=...) after pending_attack). C1 is not "the Run" - the chain's
    Run ends at its failure hand-back (chain_interrupted); the record keeps the failure's identity: the hand-back event (frame,
    episode, target, reason, as logged), the Run's own move (the chain's b2_selected / b2_nominal_path move on its last
    final-owner tick, at most MAX_GAP frames before) and the same-frame failure exposure (b2_failure_exposure: its source move and
    responsibility window), bound to the ONE big circle alive in the rune ledger at that frame (its object iid, the generation's
    first frame, its centre). A missing identity, a failure target that is not the Run move's, or a circle association that is not
    unique is unknown: no record (no Run id is made up, no target taken from the focus). The record lives within one air phase and
    is cleared by: a record gap over MAX_GAP frames, an episode or scene change, landing, any chain link owning the keys again, a
    supervisor or script owner, the failure target dead or unseen for over MAX_GAP frames, the bound circle gone, re-created (a new
    generation of its object iid) or lit. Its source move's owner dying does not clear it (the circle outlives its owner); being
    outside the circle only fails that tick's entry (the gate). Nothing here is an admission, a certificate or a send."""

    def __init__(self):
        self.prev_chain = None             # the last recorded tick's final owner was the chain (None: no tick yet)
        self.seen: dict = {}               # iid -> Control state on the last recorded tick
        self.prev_f = None
        self.run_move = None               # the chain's own Run move on its last final-owner tick (with its frame)
        self.c1 = None                     # the live C1 record, or None

    def reset(self):
        self.__init__()

    @staticmethod
    def _chain_events(chain, f, fo):
        out = []
        for e in reversed(list(getattr(chain, "events", None) or ())):
            fr = e.get("frame")
            if fr is not None and fr < min(f, fo):
                break
            if e.get("event") in FAIL_EVENTS and fr in (f, fo):
                out.append({k: (str(e[k])[:160] if isinstance(e[k], str) else e[k]) for k in EVENT_FIELDS if k in e})
        return out[::-1]

    @staticmethod
    def _run_move(chain, f, fo):
        """The chain's own Run move of this tick (its latest b2_selected / b2_nominal_path at most MAX_GAP frames back), or None."""
        for e in reversed(list(getattr(chain, "events", None) or ())):
            fr = e.get("frame")
            if fr is not None and fr < min(f, fo) - MAX_GAP:
                break
            if e.get("event") in MOVE_EVENTS and type(fr) is int and fr <= max(f, fo):
                mv = _move(e.get("move"))
                return None if mv is None else {**mv, "frame": fr}
        return None

    @staticmethod
    def _exposure(chain, f, fo):
        """The chain's failure exposure of this frame (b2_failure_exposure) with its source move, or None."""
        for e in reversed(list(getattr(chain, "events", None) or ())):
            fr = e.get("frame")
            if fr is not None and fr < min(f, fo):
                break
            if e.get("event") == "b2_failure_exposure" and fr in (f, fo):
                ex = e.get("exposure")
                mv = _move(ex.get("move")) if isinstance(ex, dict) else None
                if mv is None:
                    return None
                return {"source_move": mv, **{k: ex.get(k) for k in ("origin", "failed_frame", "minimum_through", "end_status")}}
        return None

    def _c1_make(self, pol, s, f, fo, gate, events, chain):
        """(record, None) or (None, why unknown) on an H1 hand-back."""
        if not gate.get("air"):
            return None, "not in the air at the failure"
        fail = next((e for e in events if e.get("event") == "transfer_no_witness_handback"), None)
        if fail is None:
            return None, "no failure hand-back event with a target on this hand-back"
        if type(fail.get("frame")) is not int or type(fail.get("target")) is not int or fail.get("episode") is None:
            return None, "failure identity incomplete (frame, episode, target)"
        rm = self.run_move
        if rm is None or rm["frame"] < fail["frame"] - MAX_GAP or rm["frame"] > fail["frame"]:
            return None, "the Run's own move not observed on the chain's last ticks"
        if rm["target_iid"] != fail["target"]:
            return None, "the failure target is not the Run move's target"
        ex = self._exposure(chain, f, fo)
        if ex is None:
            return None, "no same-frame failure exposure with its source move"
        ledger = getattr(pol, "rune_life", None)
        live = list(ledger.live()) if ledger is not None else None
        if live is None:
            return None, "no rune ledger"
        if len(live) != 1:
            return None, "no big circle alive at the failure" if not live else "big circle association not unique"
        c = live[0]
        if c.iid is None:
            return None, "the circle has no object id"
        circle = {"iid": c.iid, "first_f": int(c.first_f), "cx": round(float(c.cx), 3), "cy": round(float(c.cy), 3)}
        identity = {"failure": {k: fail[k] for k in EVENT_FIELDS if k in fail}, "run_move": rm, **ex, "circle": circle, "created_f": int(f)}
        return {"identity": identity, "target": fail["target"], "target_seen_f": int(f), "circle": circle,
                "episode": getattr(chain, "episode", None), "room": s.get("room")}, None

    def _c1_clear(self, pol, s, f, own, gate, chain_now, clappers, rec):
        """Why the live record ends on this tick, or None."""
        if self.prev_f is None or f - self.prev_f > MAX_GAP:
            return "a record gap over MAX_GAP frames"
        if getattr(getattr(pol, "chain_native", None), "episode", None) != rec["episode"]:
            return "episode changed"
        if s.get("room") != rec["room"]:
            return "scene changed"
        if not gate.get("air"):
            return "landing (the air phase ended)"
        if chain_now:
            return "a chain link is the final key owner again"
        if own != "plan":
            return f"a supervisor or script owner ({own})"
        tgt = rec["target"]
        if any(e.get("iid") == tgt and (e.get("is_dead") or (type(e.get("hp")) in (int, float) and e.get("hp") <= 0))
               for e in s.get("ents") or ()):
            return "the failure target dead"
        if any(e.get("iid") == tgt for e in clappers):
            rec["target_seen_f"] = int(f)
        elif f - rec["target_seen_f"] > MAX_GAP:
            return "the failure target unseen over MAX_GAP frames"
        c = (getattr(getattr(pol, "rune_life", None), "recs", None) or {}).get(rec["circle"]["iid"])
        if c is None:
            return "the bound circle gone"
        if int(c.first_f) != rec["circle"]["first_f"]:
            return "the bound circle's object re-created (a new generation)"
        if c.gone_f is not None:
            return "the bound circle not listed"
        if c.lit or c.t_on is not None:
            return "the bound circle lit"
        return None

    def _c1_circle_gate(self, pol, box):
        """The live record's own circle on this tick (seq 392 C): {"inside_bound": her box meets ITS octagon, "bound_not_lit": its lit
        window still ahead and not lit} from the rune ledger's record of the same object iid AND generation (first frame); anything
        else (another generation, a missing record, an unknown box) is not inside - never another circle of the rows."""
        from . import rune_life
        circ = self.c1["circle"]
        ledger = getattr(pol, "rune_life", None)
        c = (getattr(ledger, "recs", None) or {}).get(circ["iid"])
        if c is None or int(c.first_f) != circ["first_f"] or box is None or len(box) != 4:
            return {"inside_bound": False, "bound_not_lit": False, "why": "the bound circle or her box unknown on this tick"}
        t = float(getattr(ledger, "t", 0.0))
        on_k = math.floor(max(0.0, (c.t0 + rune_life.ON_F / 60.0 - t) * 60.0) + 1e-6)     # RuneCircles.rows' on_k, as the gate reads it
        not_lit = bool(not c.lit and c.t_on is None and not c.burst and on_k > 0)
        inside = bool(rune_life._over_big(np.array([box[0]]), np.array([box[1]]), np.array([box[2]]), np.array([box[3]]),
                                          c.cx, c.cy, rune_life.RUNE_R)[0])
        return {"inside_bound": inside, "bound_not_lit": not_lit, "why": None}

    def _c1_step(self, pol, s, f, fo, own, gate, chain_now, h1, events, chain, clappers):
        out = None
        if self.c1 is not None:
            why = self._c1_clear(pol, s, f, own, gate, chain_now, clappers, self.c1)
            if why is not None:
                out = {"status": "cleared", "reason": why, "record": self.c1["identity"]}
                self.c1 = None
        if h1:
            made, why = self._c1_make(pol, s, f, fo, gate, events, chain)
            if made is not None:
                note = None if self.c1 is None else "a newer failure record replaces the live one"
                self.c1 = made
                return {"status": "live", "reason": "created on this hand-back" + (f"; {note}" if note else ""), "record": made["identity"]}
            if out is None and self.c1 is None:
                out = {"status": "unknown", "reason": why, "record": None}
        if self.c1 is not None:
            return {"status": "live", "reason": None, "record": self.c1["identity"]}
        return out or {"status": "none", "reason": None, "record": None}

    def record(self, pol, s, f, fo, ws, S0, prefix, hold, res, fplan, prefs, own) -> dict:
        from . import air_chain, rune_life, slam_play
        from .knife_chain_air import body_box
        t0 = time.perf_counter()
        h = s.get("hero") or {}
        can = h.get("can") or {}
        S = np.asarray(S0, float).reshape(-1)
        box = h.get("box")
        rows = pol._rune_rows()
        rows = np.asarray(rows, np.float64).reshape(-1, 6) if rows is not None and len(rows) else np.zeros((0, 6))
        circle = None
        if box is not None and len(rows):
            for _o, cx, cy, r, on, off in rows[rows[:, 3] > 5.0]:
                if on > 0 and rune_life._over_big(np.array([box[0]]), np.array([box[1]]), np.array([box[2]]), np.array([box[3]]),
                                                  cx, cy, r)[0]:
                    circle = [round(float(cx), 3), int(on)]
                    break
        silk = h.get("silk")
        gate = {"plan": own == "plan", "air": bool(S[K.GROUND] <= 0) and getattr(getattr(ws.hero, "contact", None), "v", None) != "GROUND",
                "harpoon": can.get("harpoon") is True, "silk": isinstance(silk, (int, float)) and silk >= 1,
                "input": h.get("hero_accepting_input") is True, "inside_not_lit": circle is not None}
        # the final key owner: the chain itself, or the planner sending a chain row as its own pick (its mask is that row's)
        chain_now = own == "chain" or (own == "plan" and str(getattr(res, "name", "")).startswith("CHAIN"))
        fresh = self.prev_f is not None and 0 < f - self.prev_f <= MAX_GAP
        h1 = bool(fresh and self.prev_chain and not chain_now and own == "plan")
        chain = getattr(pol, "chain_native", None)
        events = self._chain_events(chain, f, fo) if h1 else []
        clappers = slam_play.clappers(s)
        states = {int(e["iid"]): slam_play.control(e)[0] for e in clappers if e.get("iid") is not None}
        tgt = getattr(prefs, "target", None)
        state = states.get(tgt) if tgt is not None else None
        prev = self.seen.get(tgt) if fresh and tgt is not None else None
        if state is None or prev is None:
            h2, h2_status = False, ("unknown: no current state" if state is None else "unknown: no previous state")
        else:
            h2 = str(state).startswith(EVADE_PREFIX) and not str(prev).startswith(EVADE_PREFIX)
            h2_status = "edge" if h2 else "no change"
        n1 = own == "plan" and bool(getattr(res, "forced_risk", False))
        if chain_now:
            mv = self._run_move(chain, f, fo)
            if mv is not None:
                self.run_move = mv
        c1 = self._c1_step(pol, s, f, fo, own, gate, chain_now, h1, events, chain, clappers)
        rec = {"own": own, "gate": gate, "circle": circle, "n1": n1, "h1": h1,
               "h1_cause": (("chain failure event" if events else "unknown") if h1 else None), "h1_events": events,
               "h1_failure_targets": sorted({e["target"] for e in events if e.get("target") is not None}) if h1 else None,
               "h2": h2, "h2_status": h2_status, "h2_target": tgt, "h2_state": [prev, state] if state is not None else None,
               "c1": c1}
        first = next((k for k, v in gate.items() if not v), None)
        entry = first is None and (n1 or h1 or h2)
        # seq 392 C: the C1 entry reads its OWN bound circle (object iid and generation) for "inside, not lit", never any circle of
        # the rows; the other gate items are the common ones. N1 / H1 / H2 keep the common gate as it was.
        c1_gate = self._c1_circle_gate(pol, box) if c1["status"] == "live" and self.c1 is not None else None
        c1_entry = bool(c1_gate is not None and all(gate[k] for k in ("plan", "air", "harpoon", "silk", "input"))
                        and c1_gate["inside_bound"] and c1_gate["bound_not_lit"])
        rec["c1_gate"] = c1_gate
        rec["entry"] = entry
        rec["c1_entry"] = c1_entry
        rec["admission"] = None
        rec["research"] = None
        if first is None and not entry:
            first = "no candidate edge (N1 / H1 / H2)"
        if entry or c1_entry:
            face = h.get("facing")
            d = int(face) if face in (1, -1) else (1 if S[K.FACE] >= 0 else -1)
            bodies = []
            for e in clappers:
                b = body_box(e)
                if b is not None and e.get("iid") is not None:
                    bodies.append((int(e["iid"]), tuple(float(v) for v in b)))
            if entry:
                try:
                    sim = air_chain.ChainSim(S0, prefix, copy.deepcopy(hold), pol.params, pol.terrain, fo, f)
                    ok, why, info = admit(sim, ws.stamp.t_game_s, bodies, d, fplan, rows, enemies=clappers)
                except Exception as e:      # an analysis failure is a rejection, never a crash of the tick
                    ok, why, info = False, "admission error: " + type(e).__name__ + ": " + str(e)[:120], {}
                rec["admission"] = {"ok": bool(ok), "d": d, **info}
                first = why
            try:
                sim = air_chain.ChainSim(S0, prefix, copy.deepcopy(hold), pol.params, pol.terrain, fo, f)
                pend = pending_attack(sim, h, getattr(pol, "raw", None), f, {i for i, _ in bodies}, keylog=getattr(pol, "keylog", None))
                ok, why, info = admit(sim, ws.stamp.t_game_s, bodies, d, fplan, rows, enemies=clappers, research={"pending": pend})
            except Exception as e:          # an analysis failure is a rejection, never a crash of the tick
                ok, why, info = False, "research error: " + type(e).__name__ + ": " + str(e)[:120], {}
            rec["research"] = {"label": RESEARCH_LABEL, "from": ("entry" if entry else "") + (" c1" if c1_entry else ""),
                               "height": {"ref": HEIGHT_REF, "margin": HEIGHT_MARGIN, "threshold": round(HEIGHT_THRESHOLD, 3),
                                          "ref_source": HEIGHT_REF_SOURCE, "domain": list(HEIGHT_STATES)},
                               "ok": bool(ok), "first_reject": why, "d": d, **info}
        rec["intersection"] = bool(entry and rec["admission"] and rec["admission"]["ok"])
        rec["first_reject"] = first
        rec["sent"] = False                  # mode 2 never sends: no executor exists (mode 1 is refused at import)
        rec["ms"] = round((time.perf_counter() - t0) * 1e3, 3)
        self.prev_chain = chain_now
        self.seen = states
        self.prev_f = f
        return rec


__all__ = ["MODE", "RECORD", "E_IDX", "RESTORE", "CATCH_SHIFTS", "HEIGHT_REF", "HEIGHT_MARGIN", "HEIGHT_THRESHOLD", "branch_paths",
           "admit", "height_support", "pending_attack", "research_supports", "Recorder"]
