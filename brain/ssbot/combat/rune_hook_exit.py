"""SSBOT_FORUM_RUNE_HOOK_EXIT (Task 182, design docs/plans/forum_clapper_committed_chain.md section 4.10; Sol seq 385 - 387): the
empty-hook big-rune exit's ADMISSION and its RECORD-ONLY wiring. Nothing here sends a key; the feature is NOT complete (no
executor / state machine; see 4.10's pending items).

    0 (default)  nothing is computed; the policy is byte-identical.
    2            at the final owner, record only (Recorder.record): the common gate, N1 (the planner's own row, forced), the
                 candidate edges H1 (a chain link handed back this tick) and H2 (the L2 target's Control entered an evade state;
                 a diagnostic candidate only), the chain's own failure events of this frame as the hand-back cause (unknown when
                 none: an ordinary hand-back or an evade edge is never written as a failed plan), the full entry (gate and an
                 edge) and - only then - the admission, their intersection, the first rejection and the cost. The final owner,
                 keys and send stay the policy's.
    1            refused at import: acting is not implemented.

Admission (admit): the facing side only; every variant of knife_chain_empty_needle.compile_empty (throw 9 / 8 x applied 0 .. 2
frames late), and for each, every branch of the Catch {measured, one frame early (hypothesis)} x the control frame {P + 30 ..
P + 33} (+ the throw's shift; the measured spread of the 173 unhooked presses, air and ground not separable): 8 branches. Each
branch starts from the real prefix / filtered entry (the variant's own state at P), runs hero2's frame rules (_track, the same
constants) to its control, takes the module's control state (_control) and goes on with the kinematic model and no keys
(_trace_events) to the common end E = 37 (press + 2 + 33), all on this tick's game clock (path index i = frame f + i =
t + i / 60). Every branch is checked in full: the module's pure-branch rules (knife_chain_empty_needle._branch_problem: the ray
against the observed bodies, swept contact, ram, horizontal / vertical rows, the terrain reach - rows in the ray band, slopes in
reach), the planner's forecast of this tick (every observed Clapper defined on every frame to E, else unknown; the ray band on
the frames it can be thrown with RAY_V_MARGIN; swept contact; the ram region), its damage support (occupied), the lit runes
(rune_life margins) and a sideways exit at the branch's control. The first failure, or missing data, rejects. The two short-flight
hypotheses are branches, not a certificate: the lost 1 / 173 record and any other mechanism stay unverified."""
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


def _targets(fplan, tk, obs_iids):
    """The forecast's bodies on the frames tk (non-hazard targets) or the reason they cannot be used."""
    try:
        tg = [t for t in fplan.targets(tk) if not getattr(t, "hazard", False) and not getattr(t, "blocked", False)]
    except Exception as e:      # an unusable forecast is unknown, never empty
        return None, "forecast targets unavailable: " + type(e).__name__
    seen = {int(t.iid) for t in tg}
    miss = [i for i in obs_iids if i not in seen]
    if miss:
        return None, f"forecast does not cover observed body {miss[0]}"
    for t in tg:
        if not bool(np.all(np.asarray(t.ok, bool)[:len(tk)])):
            return None, f"forecast body {int(t.iid)} undefined on some frame"
    return tg, None


def _forecast_problem(full, tg, d, P_idx, throw, rr, cs):
    """The planner's forecast bodies against one branch's boxes (index i = frame f + i): the ray band on the frames it can be
    thrown (P .. P + throw), swept contact on every frame (the body at i and at i - 1), the ram region (swept box + RAM_W ahead)
    on the dash .. Catch frames. The first frame with a problem, in that order, is reported."""
    from .knife_chain_empty_needle import RAY_LO, RAY_HI, RAY_REACH
    if not tg:
        return None
    tb = np.stack([np.asarray(t.box, float)[:len(full)] for t in tg])          # [n bodies, T, 4]
    ids = [int(t.iid) for t in tg]
    js = np.arange(P_idx, P_idx + throw + 1)
    x = 0.5 * (full[js, 0] + full[js, 2])
    lo, hi = full[js, 1] + RAY_LO, full[js, 1] + RAY_HI
    b = tb[:, js]                                                                 # [n, J, 4]
    near, far = ((b[..., 0] - x, b[..., 2] - x) if d > 0 else (x - b[..., 2], x - b[..., 0]))
    ray = (far >= 0) & (near <= RAY_REACH) & (b[..., 1] < hi) & (b[..., 3] + RAY_V_MARGIN > lo)
    if ray.any():
        k, j = np.unravel_index(int(np.argmax(ray.T.reshape(-1))), (len(js), len(ids)))[::-1]
        return f"ray meets forecast body {ids[k]} at index {int(js[j])}"
    sw = np.column_stack((np.minimum(full[:-1, :2], full[1:, :2]), np.maximum(full[:-1, 2:], full[1:, 2:])))    # frame i = row i - 1

    def hits(a, bx):
        return (a[None, :, 0] < bx[..., 2]) & (a[None, :, 2] > bx[..., 0]) & (a[None, :, 1] < bx[..., 3]) & (a[None, :, 3] > bx[..., 1])
    contact = (hits(sw, tb[:, 1:]) | hits(sw, tb[:, :-1])).any(0)
    sh = throw - H2.CLAW_THROW_F
    dash, catch = P_idx + H2.CLAW_DASH_F + sh, P_idx + H2.CLAW_CATCH_F + sh + cs
    i_ = np.arange(1, len(full))
    on = (i_ > dash) & (i_ <= catch)
    ram = np.column_stack((sw[:, 0] + min(0.0, RAM_W * d), sw[:, 1], sw[:, 2] + max(0.0, RAM_W * d), sw[:, 3]))
    rammed = on & hits(ram, tb[:, 1:]).any(0)
    bad = contact | rammed
    if bad.any():
        r = int(np.argmax(bad))
        who = hits(sw[r:r + 1], tb[:, r + 1:r + 2]) | hits(sw[r:r + 1], tb[:, r:r + 1])
        if contact[r]:
            return f"swept contact with forecast body {ids[int(np.argmax(who[:, 0]))]} at index {r + 1}"
        who = hits(ram[r:r + 1], tb[:, r + 1:r + 2])
        return f"ram region meets forecast body {ids[int(np.argmax(who[:, 0]))]} at index {r + 1}"
    return None


def admit(sim, game, bodies, d, fplan, rows, E=E_IDX):
    """(ok, first rejection or None, info) for an empty hook decided on this tick (sim = this tick's ChainSim: the real start,
    in-flight prefix and hold filter; game = its STATE's game clock t; bodies = the observed Clapper bodies [(iid, box)]; d = her
    facing; fplan = the planner's forecast of this tick; rows = the rune rows of this tick, frames from its STATE). Read-only."""
    from . import knife_chain_empty_needle as EN
    from . import rune_life
    from .knife_chain_nominal import NominalUnsupported
    info = {"variants": 0, "branches": 0}
    opp = K.B_LEFT if d > 0 else K.B_RIGHT
    held = rune_life._held_bits(sim.hold)
    if any(int(m) & opp for m in np.asarray(sim.prefix).reshape(-1)) or held & opp:
        return False, "opposite side key in flight", info
    tk = np.arange(E + 1, dtype=np.float64) * float(sim.params.frame_time)
    tg, why = _targets(fplan, tk, [int(i) for i, _ in bodies])
    if why is not None:
        return False, why, info
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
            lead = np.asarray(made.path.box[:P_idx + 1], float)
            for cs, rr, phys, rend in branch_paths(made, sim, d, throw, E):
                btag = f"{tag} catch {cs:+d} control P+{rr}"
                why = EN._branch_problem(phys, rend, bodies, d, throw, sim.params, sim.terrain, catch_shift=cs, p=p)
                if why is not None:
                    return False, f"{btag}: {why}", info
                full = np.vstack((lead, EN._boxes(rend[1:], p)))
                if len(full) != E + 1:
                    return False, f"{btag}: path covers {len(full) - 1} of {E} frames", info
                why = _forecast_problem(full, tg, d, P_idx, throw, rr, cs)
                if why is not None:
                    return False, f"{btag}: {why}", info
                c = P_idx + rr
                near = 0.5 * (full[c][0] + full[c][2]) - d * HW
                for _o, cx, _cy, r, _on, off in big:
                    if off >= c and not d * (near - cx) > r:
                        return False, f"{btag}: not sideways out of the circle at x {cx:.2f} at control", info
                fulls.append(full)
                meta.append(btag)
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


class Recorder:
    """SSBOT_FORUM_RUNE_HOOK_EXIT=2: one record per policy tick at its final owner; never a key, never a change to the tick."""

    def __init__(self):
        self.prev_chain = False
        self.prev_states: dict = {}
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
                out.append([e.get("event"), str(e.get("reason"))[:160]])
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
        chain_now = own == "chain" or str(getattr(res, "name", "")).startswith("CHAIN")
        h1 = bool(self.prev_chain and not chain_now and own == "plan")
        events = self._chain_events(pol.chain_native, f, fo) if h1 else []
        tgt = getattr(prefs, "target", None)
        state = None
        for e in slam_play.clappers(s):
            if e.get("iid") == tgt:
                state = slam_play.control(e)[0]
        prev = self.prev_states.get(tgt)
        h2 = bool(state is not None and str(state).startswith(EVADE_PREFIX) and not str(prev or "").startswith(EVADE_PREFIX))
        n1 = own == "plan" and bool(getattr(res, "forced_risk", False))
        rec = {"own": own, "gate": gate, "circle": circle, "n1": n1, "h1": h1,
               "h1_cause": (("chain failure event" if events else "unknown") if h1 else None), "h1_events": events,
               "h2": h2, "h2_target": tgt, "h2_state": [prev, state] if h2 else None}
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
            for e in slam_play.clappers(s):
                b = body_box(e)
                if b is not None and e.get("iid") is not None:
                    bodies.append((int(e["iid"]), tuple(float(v) for v in b)))
            try:
                sim = air_chain.ChainSim(S0, prefix, copy.deepcopy(hold), pol.params, pol.terrain, fo, f)
                ok, why, info = admit(sim, ws.stamp.t_game_s, bodies, d, fplan, rows)
            except Exception as e:      # an analysis failure is a rejection, never a crash of the tick
                ok, why, info = False, "admission error: " + type(e).__name__ + ": " + str(e)[:120], {}
            rec["admission"] = {"ok": bool(ok), "d": d, **info}
            first = why
        rec["intersection"] = bool(entry and rec["admission"] and rec["admission"]["ok"])
        rec["first_reject"] = first
        rec["ms"] = round((time.perf_counter() - t0) * 1e3, 3)
        self.prev_chain = chain_now
        if tgt is not None:
            self.prev_states[tgt] = state
        self.prev_f = f
        return rec


__all__ = ["MODE", "RECORD", "E_IDX", "RESTORE", "CATCH_SHIFTS", "branch_paths", "admit", "Recorder"]
