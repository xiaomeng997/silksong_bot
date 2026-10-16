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
STAGES = ("Slam 0", "Slam 1", "Slam 2", "Slam Recover")   # SG7: the stage entries the map's rows follow
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
# SSBOT_FORUM_SG8 (task 1v1 SG8, forum.md 64; needs SSBOT_FORUM_SPECIAL_MAP=1; default off: nothing here changes): the
# fixes from the first live runs (2026-10-15): the airborne locate (the map's own planned state first, then the facts
# the bot knows: its jump key, whether the arc began with a down slash; an open jump hold is the bot's own choice),
# the lunge shortfall re-anchored once the lunge is over (the hammer polygons are rigid in the Clapper's frame), no
# runtime loaded on a tick (every bucket at the construction; a missing one = no map for that slam), the off-board
# spot near the face (the person: never run away from a slam; stay at its face, 5-7 u)
SG8 = os.environ.get("SSBOT_FORUM_SG8", "0").strip() == "1"
LUNGE_DONE = ("Slam 2", "Slam Effects?", "Slam Recover")   # the lunge's last step lands on Slam 2's first frame
FACE_BAND = (4.5, 7.0)       # SG8: the stance band in front of the Clapper (centre to centre, u; the person's demo)
FACE_BEHIND = (3.0, 5.0)     # ... and behind it (its body's back edge ~2.2 u)
FACE_U = 6.0                 # SG8: L2's slam stance in front when the map has no spot for this slam
LATE_F = 3                   # SG8: the own event's start may be this many frames off the plan's (a late input)
HOLD_TOL = 2                 # SG8: a released jump's hold may be this many frames off the arc's count of held ticks


STAY_C_U = 1.0              # SG8: the clearance the hammer needs (the polygons are exact; the map's dilation holds the
                            # off-lattice hero and one late run step): no reward for more (map_lookahead.STAY)
STAY_MU = 0.2               # ... and the score per u off the face band (a run step 0.165 u: 0.033 > lambda 0.02)


def sg8_setup() -> None:
    """SG8: the map's run-time rules (map_lookahead.STAY / ALLD; the compiled kernels read them when a runtime's tables
    are built): once per process, before the first runtime loads."""
    from ssbot.combat import map_lookahead as ml
    if not SG8 or ml.STAY is not None:
        return
    from ssbot.combat.move_data import load_cl_slam
    vs = load_cl_slam().variants("observed")
    K = max(len(v.disp) for v in vs) + 40
    D = np.stack([np.pad(v.disp, (0, max(0, K - len(v.disp))), mode="edge")[:K] for v in vs])
    ml.STAY = {"caps": None, "c_need": STAY_C_U, "mu": STAY_MU, "dsp": 0.5 * (D.min(0) + D.max(0)),
               "fb": FACE_BAND, "bb": FACE_BEHIND}
    ml.ALLD = True


def chase_wall(cx: float, hx: float, arena: tuple | None = None, buckets: bool = False) -> bool:
    """SSBOT_FORUM_CHASE review: a slam the Clapper at cx starts now (facing the hero at hx, as at every antic) gets no
    map row (the map row's wall exit: a wall within WALL_FRONT_U in front of / WALL_BACK_U behind the anchor; SG7
    stage maps with buckets: a wall nearer than every bucket)."""
    face = 1 if hx >= cx else -1
    if buckets:
        return smrt.MapRuntime.wall_bucket(float(cx), face, arena or FORUM_ARENA) is None
    return bool(smrt.MapRuntime.wall_exit(float(cx), face, arena or FORUM_ARENA))


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
        self._bucket_rt: dict = {}           # SG7: wall-bucket maps by tag
        self.slam: dict = {}           # iid -> the slam instance's memory (anchor, facing, exit, presses)
        self.info: dict | None = None
        self.ready_info: dict | None = None
        self._dec = None
        self.yh: list = []             # (tick, box bottom above the floor at the start) of the last ticks
        self._arc = None               # SG8: the hero's current airborne arc {"ds": a down slash in it} (None: unknown)
        self.locate_stats = {"plan": 0, "mem": 0, "facts": 0, "open": 0, "min": 0, "fallback": 0}
        self._last_spot: dict = {}     # SG8: iid -> (tick, x) of this slam's last map spot (L2 between rows)
        sg8_setup()

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

    def runtime_for(self, x0: float, face: int):
        """SG7: the slam's map: the plain one on open floor, a wall bucket near a wall (stage maps only: the SG4
        maps keep their wall exit); (runtime, why) with why "wall" when no bucket fits."""
        rt = self.runtime()
        if rt is None or not getattr(rt, "stage", None):
            return rt, ("wall" if rt is not None and rt.wall_exit(x0, face, FORUM_ARENA) else None)
        b = rt.wall_bucket(x0, face, FORUM_ARENA)
        if b is None:
            return rt, "wall"
        if b == "":
            return rt, None
        tag = smrt.MAP_TAG + b
        if tag not in self._bucket_rt and SG8 and self._loaded:
            # SG8: never a runtime load on a tick (live: a bucket's first use decompressed 1.5 GB mid-fight, ~3 s);
            # every bucket is loaded at the construction (preload): one missing here has no file -> no map
            return rt, "wall"
        if tag not in self._bucket_rt:
            try:
                self._bucket_rt[tag] = smrt.runtime(self.pl.params, self.pl.terrain, tag)
            except Exception as ex:  # noqa: BLE001
                self._bucket_rt[tag] = None
                self.load_error = repr(ex)
        brt = self._bucket_rt[tag]
        return (brt, None) if brt is not None else (rt, "wall")

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
        if rt is not None and getattr(rt, "stage", None):
            # SG8 (stalls): every wall bucket of the tag now (the construction), never on a slam tick; decisions as
            # before (the same runtimes), only when they load
            t_b = time.perf_counter()
            for u in smrt.WALL_BUCKETS_F + smrt.WALL_BUCKETS_B + ((smrt.WALL_BUCKET_B15,) if SG8 else ()):
                sfx = (f"_f{u:g}" if u in smrt.WALL_BUCKETS_F else f"_b{u:g}")
                tag = smrt.MAP_TAG + sfx
                if tag in self._bucket_rt:
                    continue
                try:
                    self._bucket_rt[tag] = smrt.runtime(self.pl.params, self.pl.terrain, tag)
                except Exception as ex:  # noqa: BLE001
                    self._bucket_rt[tag] = None
                    self.load_error = repr(ex)
            self.bucket_ms = round((time.perf_counter() - t_b) * 1e3, 1)
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
        rt = self.runtime()
        if rt is None:
            return "no map"
        if chase_wall(cx, hx, buckets=bool(getattr(rt, "stage", None))):
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

    def arc_update(self, st0) -> None:
        """SG8: the hero's airborne arc from the start state (every tick): reset on the ground, a down slash in it
        noted (a bounce can follow only then)."""
        if float(st0[kin.GROUND, 0]) > 0:
            self._arc = {"ds": False, "held": 0, "rel": False}
            return
        if self._arc is None:
            return
        if int(st0[kin.MODE, 0]) in (kin.M_DS_ANTIC, kin.M_DS_SPIKE):
            self._arc["ds"] = True
        # the jump key's run in this arc (ticks: one per frame; a late tick skips frames: HOLD_TOL)
        if float(st0[kin.JHELD, 0]) > 0 and not self._arc["rel"]:
            self._arc["held"] += 1
        elif self._arc["held"] > 0:
            self._arc["rel"] = True

    def _locate_sg8(self, rt, mem, k: int, x: float, cdir: int, phases: list, ys: list, S, md):
        """SG8: the airborne hero's map event (ev with q0, how) or (None, "none"). The slices matching the last three
        box bottoms (MapRuntime.locate, every possible phase); then (1) the map's own planned state at this frame (its
        last plan; else the event it used last tick in this arc) when it is among them; (2) else the ones the facts
        allow: the jump key (Jump.IsPressed after the prefix: held -> a hold h >= j - 1, released -> h <= j; one frame
        of slack), a bounce only in an arc with a down slash; (3) the value: per event the minimum over the phases (an
        unknown); the jump holds still open (key held, h >= j) are the bot's own choice (the row's masks hold the key
        to h and the lane guard checks the planner's lane on them): the best of them; every other remaining event is
        unknown: the minimum. Nothing left after (2): every matching slice (the minimum, as before)."""
        evs = [(p, s, rt.ev_of_slice(s, k, p)) for p in phases for s in rt.locate(k, ys, p, bin_off=True)]
        cbw = float(rt.ti.cb_w)

        def key_of(e):
            if e["kind"] == "jump":
                return ("jump", int(e["k"]), float(e["h"]))
            return ("bounce", int(e["k"]), int(np.floor(float(e["yc"]) / cbw)))
        exp, how = None, "plan"
        prev = mem.get("plan")
        if prev is not None and getattr(prev, "states", None):
            i = k - prev.k0
            if 1 <= i < len(prev.states):
                s_ = prev.states[i]
                if s_[0] == k and s_[2] in ("jump", "bounce"):
                    exp = {"kind": s_[2], "k": int(s_[3])}
                    if s_[2] == "jump":
                        exp["h"] = s_[4]
                    else:
                        exp["yc"] = float(s_[5])
        if exp is None and mem.get("air_ev") is not None:
            exp, how = mem["air_ev"], "mem"
        if exp is not None and not evs:
            # right after a contact (or at a bounce's last frames) no tube slice matches yet: the plan's own event
            # when its own profile matches the heights (its start or LATE_F frames later: a late press / contact)
            for dk in range(-1 if exp["kind"] == "bounce" else 0, LATE_F + 1):
                e_ = dict(exp, k=int(exp["k"]) + dk)
                e_["q0"] = (phases[0] - e_["k"]) % 6
                if rt.ev_matches(e_, k, ys):
                    self.locate_stats[how] += 1
                    return e_, how
        if not evs:
            return None, "none"
        if exp is not None:
            # the same jump hold / contact-height bin, its start within LATE_F frames of the planned one (a late
            # press or contact): the matching slice nearest the plan's start
            ke = key_of(exp)
            m_ = sorted((abs(key_of(e)[1] - ke[1]), i_, e) for i_, (_, _, e) in enumerate(evs)
                        if key_of(e)[0] == ke[0] and key_of(e)[2] == ke[2] and abs(key_of(e)[1] - ke[1]) <= LATE_F)
            if m_:
                e_ = m_[0][2]
                ev = dict(exp)
                ev["k"], ev["q0"] = int(e_["k"]), int(e_["q0"])
                self.locate_stats[how] += 1
                return ev, how
        jheld = float(S[kin.JHELD]) > 0
        ds = self._arc is None or bool(self._arc.get("ds")) or bool(
            np.isin(np.asarray(md), (kin.M_DS_ANTIC, kin.M_DS_SPIKE)).any())
        # released in this arc before the prefix: the hold its key had (the arc's count; frames the prefix still held
        # it count too)
        hold_n = None
        if not jheld and self._arc is not None and self._arc.get("rel") and not ds:
            hold_n = int(self._arc["held"])
        keep = []
        for p, s, e in evs:
            j = k - int(e["k"])
            if e["kind"] == "jump":
                h = float(e["h"])
                if (jheld and h < j - 1) or (not jheld and h > j):
                    continue
                if hold_n is not None and abs(h - hold_n) > HOLD_TOL:
                    continue
            elif not ds:
                continue
            keep.append((p, s, e))
        how = "facts"
        if not keep:
            keep, how = list(evs), "fallback"
        groups: dict = {}
        for p, s, e in keep:
            groups.setdefault(key_of(e), []).append((p, s, e))
        vals = {g: min(min(rt.S_obs(q, k, s, x, cdir) for q in phases) for _, s, _ in lst)
                for g, lst in groups.items()}
        open_ = [g for g in groups if g[0] == "jump" and jheld and g[2] >= k - g[1]] if how == "facts" else []
        cv = []
        if open_:
            go = max(open_, key=lambda g: (vals[g], -g[2]))
            cv.append((vals[go], go))
        cv += [(vals[g], g) for g in groups if g not in open_]
        v, g = min(cv, key=lambda t: t[0])
        if how == "facts":
            how = "open" if (open_ and g in open_) else ("facts" if len(groups) == 1 else "min")
        self.locate_stats[how] += 1
        return dict(groups[g][0][2]), how

    def row(self, f, start, hold, prefix, T: int, ticks: int) -> MapRow | None:
        t0 = time.perf_counter()
        st0 = np.asarray(start).reshape(kin.K, -1)
        hx = float(st0[kin.PX, 0])
        self.info = None
        if SG8:
            self.arc_update(st0)
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
        if SG8:
            info["cx"] = round(float(e["pos"][0]), 3)       # (the planner's FORCED_RISK keys in a slam)
        # SG7: the stage entries seen (the tracker's state start: back-dated by the time in state when first seen)
        # and the slam's map (a wall bucket near a wall). SG7 review (forum.md 63.5): the entries in game time x 60,
        # not rounded (half frames at 120 fps / x0.5); the observation is at the tracker's frame (st_ and st_t0 are the
        # tracker's now: k_trk), so neither carries k_shift (the planner origin's offset from the tracker)
        seen = mem.setdefault("seen", {})
        if st_ in STAGES and st_ not in seen and t0_ is not None and getattr(inst, "st_t0", None) is not None:
            seen[st_] = round((float(inst.st_t0) - float(t0_)) * 60.0, 3)
        k_obs = float(k_trk)
        if T_ is not None and t0_ is not None:
            k_obs = (float(T_) - float(t0_)) * 60.0
        if getattr(rt, "stage", None):
            rt_b, why_b = self.runtime_for(x0, face)
            if why_b is None:
                rt = rt_b
                info["tag"] = getattr(rt, "tag", None)
        if mem["exit"] is not None:
            info["why"] = mem["exit"]
            return None
        ok_v = None
        if getattr(rt, "stage", None):
            # SG7 review: off the 60 Hz grid once (120 fps / x0.5 / a part frame), no stage rows for this slam
            if smrt.off_grid(k_obs) or any(smrt.off_grid(v) for v in seen.values()):
                mem["obs_off"] = True
            ok_v = rt.observe(None if mem.get("obs_off") else seen, k_trk, smrt.OBS_LAT, k_frac=k_obs)
            info["obs_off"] = bool(mem.get("obs_off"))
            info["seen"] = dict(seen)
            info["nv"] = len(ok_v)
        dev = 0.0 if st_ == ANTIC else rt.deviation(k_trk, float(e["pos"][0]), x0, face)
        info["dev"] = round(dev, 3)
        if dev > smrt.DEV_TOL_U and SG8 and getattr(rt, "stage", None):
            # SG8: a lunge shorter than every variant (live: 1.8-3.1 u; the observed 3.6 / 4.2): the hammer polygons are
            # rigid in the Clapper's frame, so once the lunge is over (Slam 2 entered: its last step lands on that
            # frame) the anchor moves to put the Clapper on the consistent variants' smallest displacement there (the
            # most-behind variant is where it is; the others are ahead: their union covers it); while it still lunges:
            # no row this tick (not sticky); ahead of the range (knockback forward): the exit as before
            cx_ = float(e["pos"][0])
            kk_ = int(np.clip(k_trk, 0, len(rt.disp_lo) - 1))
            short = (cx_ - x0) * face < float(rt.disp_lo[kk_])
            if short and st_ in LUNGE_DONE:
                vv = [rt.vtl[v] for v in (ok_v or range(len(rt.vtl)))]
                dmin = min(float(v.disp[min(kk_, len(v.disp) - 1)]) for v in vv)
                mem["x0"] = x0 = cx_ - face * dmin
                mem["plan"] = None
                mem["reanchor"] = mem.get("reanchor", 0) + 1
                info.update(x0=round(x0, 3), reanchor=round(dev, 3))
                rt_b, why_b = self.runtime_for(x0, face)
                if why_b is None:
                    rt = rt_b
                    info["tag"] = getattr(rt, "tag", None)
                    ok_v = rt.observe(None if mem.get("obs_off") else seen, k_trk, smrt.OBS_LAT, k_frac=k_obs)
                dev = rt.deviation(k_trk, cx_, x0, face)
                info["dev"] = round(dev, 3)
            elif short:
                info["why"] = "deviation (lunge short, waiting)"
                return None
        if dev > smrt.DEV_TOL_U:
            mem["exit"] = "deviation"
            info["why"] = "deviation"
            return None
        if (self.runtime_for(x0, face)[1] if getattr(rt, "stage", None) else
                rt.wall_exit(x0, face, FORUM_ARENA)):
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
            if SG8:
                mem["air_ev"] = None
        elif SG8:
            ys = [float(b[1]) - y_floor for b in box[::-1][:3]]
            ev, how_ = self._locate_sg8(rt, mem, k, x, cdir, phases, ys, S, md)
            info["loc"] = how_
            if ev is None:
                info["why"] = "airborne off the macros"
                return None
            mem["air_ev"] = {kk: ev[kk] for kk in ("kind", "k", "h", "yc") if kk in ev}
        else:
            ys = [float(b[1]) - y_floor for b in box[::-1][:3]]
            best = None
            for p in phases:
                for s in rt.locate(k, ys, p):
                    v = min(rt.S_obs(q, k, s, x, cdir) for q in phases)
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
        if prev is not None and prev.phases == phases and getattr(prev, "obs_sig", None) == rt.obs_sig and                 getattr(prev, "rt_id", id(rt)) == id(rt):
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
        plan.obs_sig, plan.rt_id = rt.obs_sig, id(rt)
        mem["plan"] = plan
        mem["rt"] = rt
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
        if SG8 and BOARD[iid]["x"] is not None:
            self._last_spot[iid] = (ticks, BOARD[iid]["x"])
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
        rt = (self.slam.get(info.get("iid")) or {}).get("rt") or self.runtime()
        if SG8 and info.get("why") in ("deviation", "wall"):
            # SG8: no map for this slam: the last map spot of this slam (L2 keeps the hit weight), else L2's face
            ls = self._last_spot.get(info.get("iid"))
            if ls is not None:
                BOARD[info["iid"]] = {"tick": ticks, "on": False, "x": ls[1], "k": info.get("k"), "why": "last"}
            else:
                BOARD.pop(info.get("iid"), None)
            return
        if rt is None or info.get("why") in ("deviation", "wall"):
            BOARD.pop(info.get("iid"), None)
            return
        hx = float(np.asarray(start).reshape(kin.K, -1)[kin.PX, 0])
        x0, face, k = info["x0"], info["face"], int(info["k"])
        if SG8:
            # SG8: the best ground spot 10 frames ahead within 8 u, scored as the map's own fallback (map_lookahead
            # .STAY): no strike there -> its value capped at the clearance the hammer needs, minus the distance from
            # the face band; a strike value as it is
            from ssbot.combat import map_lookahead as ml
            st_ = ml.STAY
            xs = (hx - x0) * face + np.arange(-8.0, 8.01, rt.ti.step)
            kk = min(k + 10, rt.ti.K - 1)
            V = rt.S_min(list(rt.srcs), kk, 0, xs, 0)
            fin = np.isfinite(V)
            if fin.any() and st_ is not None and st_.get("caps") is not None:
                fd = np.array([ml.face_dist(float(v_), kk, st_) for v_ in xs])
                sc_ = np.where(V > rt.wc + 1e-3, V, np.minimum(V, st_["caps"])) - st_["mu"] * fd
                sc_ = np.where(fin, sc_, -np.inf)
                i_ = int(np.argmax(sc_))
                x_ = float(x0 + face * xs[i_])
                BOARD[info["iid"]] = {"tick": ticks, "on": False, "x": x_, "k": k, "why": "ground"}
                self._last_spot[info["iid"]] = (ticks, x_)
                return
            ls = self._last_spot.get(info.get("iid"))
            if ls is not None:
                BOARD[info["iid"]] = {"tick": ticks, "on": False, "x": ls[1], "k": k, "why": "last"}
            return
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
                v = min(rt.S_obs(p, kk, 0, x, 0) for p in rt.srcs)
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
        if getattr(rt, "stage", None):
            # SG7: near a wall the slam's bucket map (the hero limited at the wall), facing the hero at the antic
            rt_b, why_b = self.runtime_for(cx, 1 if hx >= cx else -1)
            if why_b is None and rt_b is not None:
                rt = rt_b
            rt.observe(None)
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
        rmode = None
        if SG8:
            # SG8: an airborne end's own jump key (the row's mask read at index je): held -> the open holds are the
            # bot's choice (the best), released -> the holds it had; a bounce only after a down press (the row's, or
            # one earlier in the arc)
            col = cmd[idx, ce] if (cmd.shape[1] and 0 <= ce < cmd.shape[1]) else np.zeros(len(idx), np.int64)
            dn_ = ((cmd[idx, :max(ce + 1, 0)] & (kin.B_DOWN | kin.B_ATTACK)) == (kin.B_DOWN | kin.B_ATTACK)).any(axis=1) \
                if ce >= 0 else np.zeros(len(idx), bool)
            arc_ds = self._arc is None or bool(self._arc.get("ds"))
            rmode = np.where(gnd, 0, np.where((col & kin.B_JUMP) != 0, 1, 2) + np.where(dn_ | arc_ds, 4, 0))
            rmode = rmode.astype(np.int64)
        R = rt.readiness_min(p_end, xm, kd, gnd, yb, yp, rmode=rmode)   # SG6: one compiled call with the JIT
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
