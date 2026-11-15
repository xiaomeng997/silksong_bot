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
certificate: the lost 1 / 173 record and any other mechanism stay unverified."""
from __future__ import annotations

import copy
import os
import time

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


def lane_regions(piv, p, d, P_idx, throw, cs):
    """One lane (physical or rendered pivots [E + 1, 2], index i = frame f + i) as the regions it acts through: its boxes, its
    frame-to-frame sweeps (row i - 1 = frame i), the needle's ray band on the frames it can be thrown (P .. P + throw) and the ram
    box on the dash .. Catch frames (knife_chain_empty_needle's ram, from this lane's pivots)."""
    from . import knife_chain_empty_needle as EN
    piv = np.asarray(piv, float)
    boxes = EN._boxes(piv, p)
    sw = EN._sweeps(boxes)
    js = np.arange(P_idx, P_idx + throw + 1)
    rays = np.array([EN._ray_band(boxes[j], d) for j in js])
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


def admit(sim, game, bodies, d, fplan, rows, E=E_IDX, enemies=()):
    """(ok, first rejection or None, info) for an empty hook decided on this tick (sim = this tick's ChainSim: the real start,
    in-flight prefix and hold filter; game = its STATE's game clock t; bodies = the observed Clapper bodies [(iid, box)]; d = her
    facing; fplan = the planner's forecast of this tick (its damage support only); rows = the rune rows of this tick, frames from
    its STATE; enemies = this STATE's Clapper entities, for their body routes). Every dynamic check runs on BOTH lanes of every
    branch, the physical pivots and the rendered ones, on one index (frame f + i; seq 388 P2-A). Read-only."""
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
    routes, why = body_routes(enemies, E)
    if why is not None:
        return False, why, info
    tk = np.arange(E + 1, dtype=np.float64) * float(sim.params.frame_time)
    rows = np.asarray(rows, np.float64).reshape(-1, 6) if rows is not None and len(rows) else np.zeros((0, 6))
    big = rows[rows[:, 3] > 5.0]
    p = sim.params.vector()
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
                why = EN._branch_problem(phys, rend, bodies, d, throw, sim.params, sim.terrain, catch_shift=cs, p=p)
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


class Recorder:
    """SSBOT_FORUM_RUNE_HOOK_EXIT=2: one record per policy tick at its final owner; never a key, never a change to the tick.

    Edges are facts of two consecutive recorded ticks (seq 388 P2-C): H1 needs the previous tick's FINAL key owner to be the chain
    (the owner "chain", or the planner sending a chain row as its own pick) and this tick's to be the planner - a chain row that a
    supervisor or a script overrode never held the keys; H2 needs the same iid observed with a known Control state on the previous
    recorded tick (every observed Clapper is tracked, so a focus switch never reads as a transition) and a gap of at most MAX_GAP
    frames - a first sight, a missing or a stale previous state is unknown, never an edge. The chain's own failure events of the
    hand-back frame keep their identity fields as logged (no field is filled from the current focus)."""

    def __init__(self):
        self.prev_chain = None             # the last recorded tick's final owner was the chain (None: no tick yet)
        self.seen: dict = {}               # iid -> Control state on the last recorded tick
        self.prev_f = None

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
        events = self._chain_events(pol.chain_native, f, fo) if h1 else []
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
        rec = {"own": own, "gate": gate, "circle": circle, "n1": n1, "h1": h1,
               "h1_cause": (("chain failure event" if events else "unknown") if h1 else None), "h1_events": events,
               "h1_failure_targets": sorted({e["target"] for e in events if e.get("target") is not None}) if h1 else None,
               "h2": h2, "h2_status": h2_status, "h2_target": tgt, "h2_state": [prev, state] if state is not None else None}
        first = next((k for k, v in gate.items() if not v), None)
        entry = first is None and (n1 or h1 or h2)
        rec["entry"] = entry
        rec["admission"] = None
        if first is None and not entry:
            first = "no candidate edge (N1 / H1 / H2)"
        if entry:
            face = h.get("facing")
            d = int(face) if face in (1, -1) else (1 if S[K.FACE] >= 0 else -1)
            bodies = []
            for e in clappers:
                b = body_box(e)
                if b is not None and e.get("iid") is not None:
                    bodies.append((int(e["iid"]), tuple(float(v) for v in b)))
            try:
                sim = air_chain.ChainSim(S0, prefix, copy.deepcopy(hold), pol.params, pol.terrain, fo, f)
                ok, why, info = admit(sim, ws.stamp.t_game_s, bodies, d, fplan, rows, enemies=clappers)
            except Exception as e:      # an analysis failure is a rejection, never a crash of the tick
                ok, why, info = False, "admission error: " + type(e).__name__ + ": " + str(e)[:120], {}
            rec["admission"] = {"ok": bool(ok), "d": d, **info}
            first = why
        rec["intersection"] = bool(entry and rec["admission"] and rec["admission"]["ok"])
        rec["first_reject"] = first
        rec["ms"] = round((time.perf_counter() - t0) * 1e3, 3)
        self.prev_chain = chain_now
        self.seen = states
        self.prev_f = f
        return rec


__all__ = ["MODE", "RECORD", "E_IDX", "RESTORE", "CATCH_SHIFTS", "branch_paths", "admit", "Recorder"]
