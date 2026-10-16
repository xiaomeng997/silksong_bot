"""The slam map in the Forum planner (task 1v1 SG4; SSBOT_FORUM_SPECIAL_MAP=1, default off; forum.md 59).

Per tick (ForumPlanner.tick calls MapHelper):
  * row(): during a tracked Clapper's CL_SLAM, the map row: the lookahead (special_map_rt.MapRuntime.plan) rolled from
    the hero's state after the prefix over the planner's horizon (+ ROW_EXTRA_F frames of template for the tail
    check). The planner judges it as a special row (special_mode's support: the Clapper's move dropped, its body kept
    outside the pre-protect frames, every other enemy and hazard kept; its bounce lane from the contact) and ranks it
    first among the safe rows. Off the map (no row): the hero off a macro state (umbrella, dash, recoil, wall, a slash
    the map did not press), the deviation exit (the Clapper off its anchor + the move's displacement: a wall-stopped
    lunge, knockback; sticky for that slam), a wall within WALL_FRONT_U in front of / WALL_BACK_U behind the anchor
    (no wall buckets for the SG4 maps), past the move.
  * readiness(): before a slam can start (a tracked Clapper in a decision state, the hero within its Slam Range), each
    row's end state's readiness (the map at k = 0 with the antic starting then: it faces the hero) -> a penalty in
    landed-hit units READY_W x max(0, R_ref - R), -inf (no safe continuation): out unless every row has it; a row ending
    in the umbrella counts as 0. Replaces SSBOT_FORUM_CL_NODOWN.
  * BOARD (the L2 controller, tactics.gauntlet._clapper_spot): during the slam the map row's spot (on) or the map's
    best ground spot near the hero; before it the readiness argmax 3-6 u in front.
  * SSBOT_FORUM_CHASE=1 (task 1v1 SG5, forum.md 61; needs SSBOT_FORUM_SPECIAL_MAP=1; default off: nothing here changes):
    the readiness also runs while the Clapper evades (Evade Scuttle: After Scuttle branches at once, in its Slam Range
    to SLAM / CAST; the Clapper carried by its velocity to the scuttle's end), and BOARD gets "chase_x": the readiness
    argmax inside CHASE_BAND (the slash stance the L2 controller chases to), "R_ref" the threshold the planner's
    readiness tier uses. Review (forum.md 61.6): only where the map handles a slam starting now (MapHelper.chase_gate:
    the map loaded, no wall exit for the Clapper facing the hero; else BOARD "chase_off" and rnmap's readiness), and
    while it evades the readiness is read at the scuttle's end (the slam starts there), not at the row's end.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np

from ssbot.combat import special_map_rt as smrt
from ssbot.combat import special_mode, specials
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.knowledge import kinematics as kin

CLAPPER = "Song Heavy Sentry"
MOVE = "CL_SLAM"
ANTIC = "Slam Antic"         # the antic: the Clapper stands (knockback aside); the lunge starts with Slam 0
BOARD: dict = {}            # iid -> {"tick", "on", "x", "k", "why", "ready_x"} (the planner's last map decision)
NEAR_U = 16.0               # a Clapper this close (x) is the map's
FORUM_ARENA = (14.01, 48.99)  # core.forum WALL_L / WALL_R
# SSBOT_FORUM_CHASE (SG5): chasing and slashing outside the slam, on the map's readiness (default off)
CHASE = os.environ.get("SSBOT_FORUM_CHASE", "0").strip() == "1"
# the chase stance's band in front (centre to centre, u): the map's ground readiness stays >= 3.28 (R_ref 3.0 = two
# strikes with full clearance) from 3.0 to 4.5 u for an antic that starts up to 12 frames before the hero is free (a
# slash's lock: attack_duration 15 frames), 5.0 u drops to 1.93 at k 12; landed ground slashes 4.2-5.4 u
CHASE_BAND = (3.5, 4.6)
EVADE_STATE = "Evade Scuttle"
EVADE_S = 0.35               # Evade Scuttle -> After Scuttle (forum.md 18.1)
MAP_READY = {"ok": False}    # review: the map runtime loaded (MapHelper.runtime); the L2 chase needs it


def chase_wall(cx: float, hx: float, arena: tuple | None = None) -> bool:
    """SSBOT_FORUM_CHASE review: a slam the Clapper at cx starts now (facing the hero at hx, as at every antic) gets no
    map row (the map row's wall exit: a wall within WALL_FRONT_U in front of / WALL_BACK_U behind the anchor)."""
    return bool(smrt.MapRuntime.wall_exit(float(cx), 1 if hx >= cx else -1, arena or FORUM_ARENA))


def _decision_states() -> frozenset:
    from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
    return frozenset(FORUM_SPECS[CLAPPER].decision_states)


@dataclass
class MapRow:
    cmd: np.ndarray            # [T] the row's masks after the prefix
    ext: np.ndarray            # [T + ROW_EXTRA_F] the template (the tail check)
    meta: dict                 # the special context's meta (ForumPlanner._special_ctx)
    plan: object               # special_map_rt.MapPlan
    info: dict = field(default_factory=dict)


class MapHelper:
    def __init__(self, planner):
        self.pl = planner
        self._rt = None
        self._loaded = False
        self.slam: dict = {}           # iid -> the slam instance's memory (anchor, facing, exit, presses)
        self.info: dict | None = None
        self.ready_info: dict | None = None
        self._dec = None
        self.yh: list = []             # (tick, box bottom above the floor at the start) of the last ticks

    def runtime(self):
        terr = getattr(self.pl, "terrain", None)
        if not self._loaded and (terr is None or not len(getattr(terr, "hseg", ()))):
            # review: never built on an empty terrain (the policy constructs the planner with Terrain2D.empty() and
            # sets the arena's at the episode start: floorless hero macros made plans without presses)
            return None
        if not self._loaded:
            self._loaded = True
            try:
                self._rt = smrt.runtime(self.pl.params, self.pl.terrain)
            except Exception as ex:  # noqa: BLE001 - a broken map file must not stop the planner
                self._rt = None
                self.load_error = repr(ex)
            MAP_READY["ok"] = self._rt is not None
        return self._rt

    def preload(self) -> None:
        """Load the map, the decision states and touch the lookup paths once (the planner's construction, else its
        first tick with the arena's terrain), so the first tick near a Clapper does not pay for them. SG6: the
        compiled kernels are compiled (or loaded from numba's cache) at the planner's construction already."""
        if self._loaded:
            return
        t0 = time.perf_counter()
        if smrt.JIT and getattr(self, "jit_warm_ms", None) is None:
            try:
                self.jit_warm_ms = round(smrt.smj.warm(), 1)
            except Exception as ex:  # noqa: BLE001 - a compile failure must not stop the planner
                self.jit_warm_ms = -1.0
                self.load_error = repr(ex)
        rt = self.runtime()
        if rt is None:
            return                     # no arena terrain yet (or no map file): the first tick with one loads it
        self._dec = _decision_states()
        if rt is not None:
            try:
                p = sorted(rt.srcs)[0]
                rt.plan(10, 4.0, {"kind": "ground", "k": 10}, 0, -100, [p], 8)
                rt.readiness_rows(p, np.array([4.0, 5.0]), np.array([0, 1]), np.array([True, False]),
                                  np.array([0.0, 1.0]), np.array([0.0, 0.8]))
                rt.readiness_min([p], np.array([4.0, 5.0]), np.array([0, 1]), np.array([True, False]),
                                 np.array([0.0, 1.0]), np.array([0.0, 0.8]))
                rt.S_min([p], 0, 0, np.array([4.0, 5.0]), 0)
            except Exception as ex:  # noqa: BLE001 - a warm-up failure must not stop the planner
                self.load_error = repr(ex)
        self.preload_ms = round((time.perf_counter() - t0) * 1e3, 1)

    # ---- SSBOT_FORUM_CHASE (SG5 review) ----
    @staticmethod
    def clapper_x(e: dict, stt) -> tuple[float, int | None]:
        """(x, frames until a slam can start or None): while it evades (CHASE), where the scuttle ends (carried by its
        velocity) and the frames until then (After Scuttle branches at once); else where it is now."""
        cx = float(e["pos"][0])
        if not (CHASE and stt == EVADE_STATE):
            return cx, None
        t_in = 0.0
        for m in e.get("fsms") or ():
            if m.get("name") == "Control":
                t_in = float(m.get("t") or 0.0)
        v = e.get("vel") or (0.0, 0.0)
        dt = max(0.0, EVADE_S - t_in)
        return cx + float(v[0]) * dt, int(round(dt * 60.0))

    def chase_gate(self, cx: float, hx: float) -> str | None:
        """None when the chase may run against the Clapper at cx (the map handles a slam it starts now), else why not:
        "no map" (no map file: the planner runs without it), "wall" (chase_wall: the map would leave that slam to the
        full checks; a scuttle carried past the wall lands here too)."""
        if self.runtime() is None:
            return "no map"
        if chase_wall(cx, hx):
            return "wall"
        return None

    # ---- the Clapper and its slam ----
    def _clapper(self, f, hx: float):
        trk = getattr(getattr(f, "rs", None), "trk", None)
        if trk is None:
            return None
        best = None
        for iid, (tk, e, inst) in trk.now.items():
            if (e.get("type_key") or tk) != CLAPPER or not e.get("pos"):
                continue
            d = abs(float(e["pos"][0]) - hx)
            if d <= NEAR_U and (best is None or d < best[0]):
                best = (d, int(iid), tk, e, inst)
        return best

    def _state_at_prefix(self, start, hold, prefix):
        """The hero's state, boxes and flags at rollout index P (after the committed prefix)."""
        pl = self.pl
        P = len(prefix)
        m = np.zeros((1, max(P, 1)), np.int64)
        m[0, :P] = prefix
        lat, _ = hold_filter_jit(m, hold)
        r = kin.rollout(start, lat, pl.params, pl.terrain)
        S = r.final[:, 0] if P >= 1 else np.asarray(start).reshape(kin.K, -1)[:, 0]
        return S, r.box[0, :P + 1], r.flags[0, :P + 1], r.mode[0, :P + 1]

    def row(self, f, start, hold, prefix, T: int, ticks: int) -> MapRow | None:
        t0 = time.perf_counter()
        st0 = np.asarray(start).reshape(kin.K, -1)
        hx = float(st0[kin.PX, 0])
        self.info = None
        c = self._clapper(f, hx)
        if c is None:
            return None
        _, iid, tk, e, inst = c
        mv = specials.enemy_move({"type_key": e.get("type_key") or tk, "fsms": e.get("fsms")})
        if mv is None or mv[0] != MOVE or not special_mode.in_family(MOVE, inst):
            self.slam.pop(iid, None)
            return None
        rt = self.runtime()
        info = {"iid": iid, "on": False}
        self.info = info
        if rt is None:
            info["why"] = "no map file"
            return None
        rs = getattr(f, "rs", None)
        trk = getattr(rs, "trk", None)
        k_trk = int(mv[1])
        T_, t0_ = getattr(trk, "T", None), getattr(inst, "t0", None)
        if T_ is not None and t0_ is not None:
            k_trk = int(round((float(T_) - float(t0_)) * 60.0))     # frames since the antic entry (game time)
        k0 = k_trk - int(getattr(rs, "k_shift", 0) or 0)
        face = 1 if e.get("flipX") else -1
        key = (iid, round(float(t0_ or 0.0), 3))
        mem = self.slam.get(iid)
        if mem is None or mem["key"] != key:
            # the anchor: the Clapper's x at the antic entry (the tracked instance's start; else the nominal lunge
            # before k_trk taken off)
            x0 = float(getattr(inst, "x0", None) if getattr(inst, "x0", None) is not None else
                       float(e["pos"][0]) - face * float(rt.disp_lo[min(max(k_trk, 0), len(rt.disp_lo) - 1)]))
            mem = {"key": key, "x0": x0, "face": face, "exit": None, "last_press": -100, "plans": 0, "taken": 0}
            self.slam[iid] = mem
        st_ = next((m.get("state") for m in e.get("fsms") or () if m.get("name") == "Control"), None)
        if st_ == ANTIC and mem["exit"] is None:
            # the person (2026-10-15): a still, not aimed move binds to the enemy's position at the antic's last
            # frame; during the antic the anchor follows it (a horizontal slash's knockback moves it 0.48 u), the
            # deviation check starts with the lunge
            mem["x0"] = float(e["pos"][0])
            mem["plan"] = None if abs(mem.get("x0_prev", mem["x0"]) - mem["x0"]) > 1e-3 else mem.get("plan")
            mem["x0_prev"] = mem["x0"]
        x0 = mem["x0"]
        info.update(k=k0, x0=round(x0, 3), face=face)
        if mem["exit"] is not None:
            info["why"] = mem["exit"]
            return None
        dev = 0.0 if st_ == ANTIC else rt.deviation(k_trk, float(e["pos"][0]), x0, face)
        info["dev"] = round(dev, 3)
        if dev > smrt.DEV_TOL_U:
            mem["exit"] = "deviation"
            info["why"] = "deviation"
            return None
        if rt.wall_exit(x0, face, FORUM_ARENA):
            mem["exit"] = "wall"
            info["why"] = "wall"
            return None
        P = len(prefix)
        S, box, fl, md = self._state_at_prefix(start, hold, prefix)
        k = k0 + P
        if k < 0 or k >= min(rt.ti.K - smrt.ROW_EXTRA_F - 6, rt.end_min + 2):
            info["why"] = "past the move"
            return None
        if int(md[-1]) != kin.M_NORMAL:
            info["why"] = f"mode {int(md[-1])}"
            return None
        if fl[-1] & kin.F_ATTACKING and mem["last_press"] < k - 12:
            info["why"] = "attacking (not the map's slash)"
            return None
        # review: the phase p = (cycle + move frame) % 6 is constant along the lane, so read it at rollout index 0
        # (k0) from the start's ALPHA interval: kin.rollout advances ALPHA but not ALO / AHI, so the state after the
        # prefix still holds index 0's interval (pairing it with k = k0 + P put the steps and tubes P frames off)
        phases = [p for p in smrt.phases_of(float(st0[kin.ALO, 0]), float(st0[kin.AHI, 0]), k0) if p in rt.srcs]
        p_nom = smrt.phases_of(float(st0[kin.ALPHA, 0]), float(st0[kin.ALPHA, 0]), k0)[0]
        if p_nom in phases:
            # the map rolls its path on the first phase: the nominal one, the planner lane's (the others still bound
            # every decision, decide_multi)
            phases = [p_nom] + [p for p in phases if p != p_nom]
        if not phases:
            info["why"] = "phase not in the map"
            return None
        bx = 0.5 * (box[-1, 0] + box[-1, 2])
        x = (bx - x0) * face
        y_floor = rt.hm.stand_y0
        cdir = int(np.sign(S[kin.MOVE])) * face
        ground = bool(fl[-1] & kin.F_GROUND)
        if ground:
            ev = {"kind": "ground", "k": k}
        else:
            ys = [float(b[1]) - y_floor for b in box[::-1][:3]]
            best = None
            for p in phases:
                for s in rt.locate(k, ys, p):
                    v = min(rt.srcs[q].S(k, s, x, cdir) if rt.keyed else rt.srcs[q].S(k, s, x) for q in phases)
                    if best is None or v < best[0]:
                        best = (v, s, p)
            if best is None:
                info["why"] = "airborne off the macros"
                return None
            ev = rt.ev_of_slice(best[1], k, best[2])
        last_press = mem["last_press"]
        cd = float(S[kin.ATK_CD]) if 0.0 < float(S[kin.ATK_CD]) < 1.0 else 0.0
        if cd > 0:
            last_press = max(last_press, k + int(np.ceil(cd * 60.0)) - smrt.ml.PRESS_COOL)
        face_hero = (1 if S[kin.FACE] >= 0 else -1) * face
        L = T + smrt.ROW_EXTRA_F
        slash = None
        if fl[-1] & kin.F_ATTACKING:
            slash = {"P": int(mem["last_press"]), "face": face_hero}     # the map's own slash in flight
        # the hero followed last tick's map row: continue it (deterministic) instead of planning again
        plan, prev = None, mem.get("plan")
        if prev is not None and prev.phases == phases:
            i = k - prev.k0
            if 1 <= i < len(prev.states):
                s_ = prev.states[i]
                same_ev = s_[2] == ev["kind"] and (ev["kind"] == "ground" or (s_[3] == ev["k"] and s_[4] == ev.get("h")
                                                                             and s_[5] == ev.get("yc")))
                if s_[0] == k and abs(s_[1] - x) < 0.02 and same_ev and s_[6] == cdir and s_[8] == (slash is not None):
                    plan = rt.extend(prev, i, L, face=face)
                    info["cached"] = True
        if plan is None:
            plan = rt.plan(k, x, ev, cdir, last_press, phases, L, face_hero=face_hero, face=face, slash=slash)
        mem["plan"] = plan
        mem["plans"] += 1
        info.update(on=True, why="row", x=round(x, 3), ev=ev["kind"], c=cdir, phases=phases, v=round(plan.value, 3),
                    act=list(plan.first) if plan.first else None, presses=plan.presses[:3], ms=round(plan.ms, 2))
        if not np.isfinite(plan.value) or plan.first is None or plan.first[0] == "slash" and not np.isfinite(
                plan.value):
            # nothing feasible from here: no map row (the planner's own rows decide; never a map jump)
            info.update(on=False, why="no feasible continuation")
            mem["plan"] = None
            return None
        cmd = np.asarray(plan.masks[:T], np.int64)
        if len(cmd) < T:
            cmd = np.concatenate([cmd, np.full(T - len(cmd), cmd[-1] & (kin.B_LEFT | kin.B_RIGHT) if len(cmd) else 0,
                                               np.int64)])
        ext = np.asarray(plan.masks, np.int64)
        meta = {"iid": iid, "tk": tk, "move": MOVE, "k_trk": k_trk, "k0": int(k0), "xa": float(x0),
                "cy": float(e["pos"][1]), "face": face, "lut": None, "by_map": True,
                # review: the map's own lane (world x / box bottom per row frame, rollout index P + 1 + t), its
                # contacts (the bounce events at rollout index P + c), the move frame from which the full support is
                # read again (every observed variant over: the Clapper may start its next move)
                "map_x": x0 + face * np.asarray(plan.xs, float), "map_y": y_floor + np.asarray(plan.ys, float),
                "map_ev": [P + int(c) for c in plan.contacts], "k_full": int(rt.end_max) + 1}
        # L2: the spot a few frames ahead on the map row (its first press if earlier)
        tb = min(len(plan.xs) - 1, plan.presses[0] if plan.presses else 10)
        BOARD[iid] = {"tick": ticks, "on": True, "x": float(x0 + face * plan.xs[max(tb, 0)]) if len(plan.xs) else None,
                      "k": k, "why": "row"}
        info["total_ms"] = round((time.perf_counter() - t0) * 1e3, 2)
        return MapRow(cmd, ext, meta, plan, info)

    def chosen(self, taken: bool, plan) -> None:
        """The planner took (or not) this tick's map row: remember its press (the cooldown, the slash in flight)."""
        if self.info is None:
            return
        self.info["taken"] = bool(taken)
        iid = self.info.get("iid")
        mem = self.slam.get(iid)
        if mem is None or plan is None:
            return
        if taken:
            mem["taken"] += 1
            if plan.presses and plan.presses[0] == 0:
                mem["last_press"] = plan.k0 + 1

    def off_board(self, f, start, ticks: int) -> None:
        """No map row this tick during the slam: L2's spot from the map's ground layer near the hero (the best ground
        value 10 frames ahead within 4 u), else nothing (L2 keeps its own rule)."""
        info = self.info
        if info is None or info.get("on") or "k" not in info:
            return
        rt = self.runtime()
        if rt is None or info.get("why") in ("deviation", "wall"):
            BOARD.pop(info.get("iid"), None)
            return
        hx = float(np.asarray(start).reshape(kin.K, -1)[kin.PX, 0])
        x0, face, k = info["x0"], info["face"], int(info["k"])
        xs = (hx - x0) * face + np.arange(-4.0, 4.01, rt.ti.step)
        kk = min(k + 10, rt.ti.K - 1)
        best, bx = -np.inf, None
        if rt.use_jit and rt.jit_tables() is not None:
            # SG6: one compiled call (the first x with the best value, as the loop below)
            V = rt.S_min(list(rt.srcs), kk, 0, xs, 0)
            i_ = int(np.argmax(V)) if len(V) else 0
            if len(V) and V[i_] > best:
                best, bx = V[i_], xs[i_]
        else:
            for x in xs:
                v = min(rt.srcs[p].S(kk, 0, x, 0) if rt.keyed else rt.srcs[p].S(kk, 0, x) for p in rt.srcs)
                if v > best:
                    best, bx = v, x
        if bx is not None and np.isfinite(best):
            BOARD[info["iid"]] = {"tick": ticks, "on": False, "x": float(x0 + face * bx), "k": k, "why": "ground"}

    # ---- readiness before the slam ----
    def readiness(self, f, start, r1, cmd: np.ndarray, P: int, ticks: int, rows: np.ndarray | None = None):
        """[N] penalty (landed-hit units) and [N] readiness of the rows' end states, or None when no Clapper can start
        its slam (a decision state, the hero within READY_RANGE_U). rows (review: the safe rows, the only ones the
        penalty ranks): computed for those only (penalty 0, readiness nan elsewhere); the order among them is the
        same as computed over all rows."""
        self.ready_info = None
        self.ready_cx = None
        self.ready_j = None
        self.chase_off = None
        st0 = np.asarray(start).reshape(kin.K, -1)
        hx = float(st0[kin.PX, 0])
        c = self._clapper(f, hx)
        if c is None:
            return None
        _, iid, tk, e, inst = c
        if self._dec is None:
            self._dec = _decision_states()
        stt = None
        for m in e.get("fsms") or ():
            if m.get("name") == "Control":
                stt = m.get("state")
        evading = CHASE and stt == EVADE_STATE
        cx, k_ev = self.clapper_x(e, stt)                         # SG5: while it evades, where the scuttle ends
        if (stt not in self._dec and not evading) or abs(cx - hx) > smrt.READY_RANGE_U:
            return None
        rt = self.runtime()
        if rt is None:
            return None
        gate = self.chase_gate(cx, hx) if CHASE else None
        self.chase_off = gate
        if evading and gate is not None:
            # review: the map would not handle this slam: rnmap's behaviour (no readiness while it evades), and the
            # L2 controller told so (BOARD "chase_off": its own branches, not the chase)
            BOARD[iid] = {"tick": ticks, "on": False, "x": None, "ready_x": None, "k": None, "why": "chase_off",
                          "chase_off": gate}
            return None
        chase = CHASE and gate is None
        t0 = time.perf_counter()
        N = r1.box.shape[0]
        Te = r1.box.shape[1] - 1
        # review: the rollout index whose state meets the slam's k = 0: the row's end; while it evades, the scuttle's
        # end (After Scuttle branches at once; not before the first frame after the prefix)
        je = Te if k_ev is None else int(min(Te, max(P + 1, k_ev)))
        self.ready_j = je
        idx = np.arange(N) if rows is None else np.asarray(rows, np.int64)
        if not len(idx):
            return np.zeros(N), np.full(N, np.nan)
        bx_ = r1.box[idx]
        xe = 0.5 * (bx_[:, je, 0] + bx_[:, je, 2])
        side = np.where(xe >= cx, 1, -1)                          # it turns to face the hero at k = 0
        xm = np.abs(xe - cx)
        S0 = st0[:, 0]
        q0 = smrt.phases_of(float(S0[kin.ALO]), float(S0[kin.AHI]), 0)   # the cycle at rollout index 0 (k = 0 there)
        p_end = sorted({(q - je) % 6 for q in q0} & set(rt.srcs))   # the phase of a slam starting at index je
        if not p_end:
            return None
        ce = je - P - 1                                           # cmd's column read at index je
        last = cmd[idx, ce] if (cmd.shape[1] and 0 <= ce < cmd.shape[1]) else np.zeros(len(idx), np.int64)
        kd = np.where((last & kin.B_RIGHT) != 0, 1, np.where((last & kin.B_LEFT) != 0, -1, 0)) * side
        gnd = (r1.flags[idx, je] & kin.F_GROUND) != 0
        glide = r1.mode[idx, je] == kin.M_GLIDE
        yb = bx_[:, je, 1] - rt.hm.stand_y0
        yp = bx_[:, je - 1, 1] - rt.hm.stand_y0
        R = rt.readiness_min(p_end, xm, kd, gnd, yb, yp)   # SG6: one compiled call with the JIT
        R[glide] = 0.0
        if chase:
            # SG5: a row ending in a ground swing: the hero is locked until the swing ends (attack_duration), so a
            # slam starting at the row's end meets her free only k_lock frames into its antic: the map's value there
            # (review: at index je)
            fl = r1.flags[idx, :je + 1]
            att = (fl[:, -1] & kin.F_ATTACKING) != 0
            if att.any():
                n_att = np.zeros(len(idx), np.int64)                  # trailing swing frames at the end
                run_ = att.copy()
                for j in range(fl.shape[1] - 1, -1, -1):
                    run_ &= (fl[:, j] & kin.F_ATTACKING) != 0
                    if not run_.any():
                        break
                    n_att += run_
                att_f = int(round(float(getattr(self.pl.params, "attack_duration", 0.25)) * 60.0))
                if rt.use_jit and rt.jit_tables() is not None:
                    # SG6: the swing lock's lookups in one compiled call
                    ia_ = np.flatnonzero(att & gnd & np.isfinite(R))
                    kl_ = np.maximum(0, att_f - n_att[ia_])
                    ia_, kl_ = ia_[kl_ > 0], kl_[kl_ > 0]
                    if len(ia_):
                        V_ = rt.S_min(p_end, kl_, 0, xm[ia_], kd[ia_])
                        for i, v in zip(ia_.tolist(), V_.tolist()):
                            R[i] = min(R[i], v)
                else:
                    for i in np.flatnonzero(att & gnd & np.isfinite(R)):
                        kl = max(0, att_f - int(n_att[i]))
                        if kl > 0:
                            v = min(rt.srcs[p].S(kl, 0, float(xm[i]), int(kd[i])) if rt.keyed else
                                    rt.srcs[p].S(kl, 0, float(xm[i])) for p in p_end)
                            R[i] = min(R[i], v)
                self.swing_rows = int(att.sum())
        ref = rt.ready_ref
        pen = smrt.READY_W * np.maximum(0.0, ref - np.where(np.isfinite(R), R, 0.0))
        out_ = np.isneginf(R)
        if out_.any() and not out_.all():
            pen = np.where(out_, 100.0, pen)
        # L2 before the slam: the readiness argmax 3-6 u in front of it on the hero's side (standing, no key)
        xs = np.arange(3.0, 6.01, rt.ti.step)
        if rt.use_jit and rt.jit_tables() is not None:
            rv = rt.S_min(p_end, 0, 0, xs, 0)                     # SG6: rt.readiness(x, 0, p) in one call
        else:
            rv = [min(rt.readiness(float(x), 0, p) for p in p_end) for x in xs]
        bi = int(np.argmax(rv))
        sd = 1 if hx >= cx else -1
        BOARD[iid] = {"tick": ticks, "on": False, "x": None, "ready_x": float(cx + sd * xs[bi]), "k": None,
                      "why": "ready"}
        if CHASE and not chase:
            BOARD[iid]["chase_off"] = gate                        # review: rnmap's readiness, no chase spot / tier
        if chase:
            # SG5: the chase stance (the L2 controller): the readiness argmax inside the slash band
            band = (xs >= CHASE_BAND[0] - 1e-9) & (xs <= CHASE_BAND[1] + 1e-9)
            ib = np.flatnonzero(band)
            ci = int(ib[int(np.argmax(np.asarray(rv)[ib]))]) if len(ib) else bi
            BOARD[iid].update(chase_x=float(cx + sd * xs[ci]), R_ref=float(ref), evading=bool(evading))
            self.ready_cx = cx                                    # (the planner's readiness tier: near rows)
        self.ready_info = {"iid": iid, "state": stt, "ref": round(ref, 3), "R_min": round(float(R.min()), 3),
                           "R_max": round(float(R.max()), 3), "pen_rows": int((pen > 0).sum()),
                           "out_rows": int(out_.sum()), "ready_x": round(float(cx + sd * xs[bi]), 2),
                           "ms": round((time.perf_counter() - t0) * 1e3, 2), "rows": int(len(idx))}
        if rows is None:
            return pen, R
        pen_f, R_f = np.zeros(N), np.full(N, np.nan)
        pen_f[idx], R_f[idx] = pen, R
        return pen_f, R_f


__all__ = ["MapHelper", "MapRow", "BOARD", "MAP_READY", "chase_wall"]
