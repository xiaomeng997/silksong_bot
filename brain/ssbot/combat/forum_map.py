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
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ssbot.combat import special_map_rt as smrt
from ssbot.combat import special_mode, specials
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.knowledge import kinematics as kin

CLAPPER = "Song Heavy Sentry"
MOVE = "CL_SLAM"
BOARD: dict = {}            # iid -> {"tick", "on", "x", "k", "why", "ready_x"} (the planner's last map decision)
NEAR_U = 16.0               # a Clapper this close (x) is the map's
FORUM_ARENA = (14.01, 48.99)  # core.forum WALL_L / WALL_R


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
        if not self._loaded:
            self._loaded = True
            try:
                self._rt = smrt.runtime(self.pl.params, self.pl.terrain)
            except Exception as ex:  # noqa: BLE001 - a broken map file must not stop the planner
                self._rt = None
                self.load_error = repr(ex)
        return self._rt

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
        k_trk = int(mv[1])
        k0 = k_trk - int(getattr(rs, "k_shift", 0) or 0)
        face = 1 if e.get("flipX") else -1
        key = (iid, round(float(getattr(inst, "t0", 0.0) or 0.0), 3))
        mem = self.slam.get(iid)
        if mem is None or mem["key"] != key:
            # the anchor: the Clapper's x at the antic entry (the nominal lunge before k_trk taken off)
            x0 = float(e["pos"][0]) - face * float(rt.disp_lo[min(max(k_trk, 0), len(rt.disp_lo) - 1)])
            mem = {"key": key, "x0": x0, "face": face, "exit": None, "last_press": -100, "plans": 0, "taken": 0}
            self.slam[iid] = mem
        x0 = mem["x0"]
        info.update(k=k0, x0=round(x0, 3), face=face)
        if mem["exit"] is not None:
            info["why"] = mem["exit"]
            return None
        dev = rt.deviation(k_trk, float(e["pos"][0]), x0, face)
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
        phases = [p for p in smrt.phases_of(float(S[kin.ALO]), float(S[kin.AHI]), k) if p in rt.srcs]
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
        plan = rt.plan(k, x, ev, cdir, last_press, phases, T + smrt.ROW_EXTRA_F, face_hero=face_hero, face=face)
        mem["plans"] += 1
        info.update(on=True, why="row", x=round(x, 3), ev=ev["kind"], c=cdir, phases=phases, v=round(plan.value, 3),
                    act=list(plan.first) if plan.first else None, presses=plan.presses[:3], ms=round(plan.ms, 2))
        if not np.isfinite(plan.value):
            info["why"] = "no feasible continuation"
        cmd = np.asarray(plan.masks[:T], np.int64)
        if len(cmd) < T:
            cmd = np.concatenate([cmd, np.full(T - len(cmd), cmd[-1] & (kin.B_LEFT | kin.B_RIGHT) if len(cmd) else 0,
                                               np.int64)])
        ext = np.asarray(plan.masks, np.int64)
        meta = {"iid": iid, "tk": tk, "move": MOVE, "k_trk": k_trk, "k0": int(k0), "xa": float(x0),
                "cy": float(e["pos"][1]), "face": face, "lut": None, "by_map": True}
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
        for x in xs:
            v = min(rt.srcs[p].S(kk, 0, x, 0) if rt.keyed else rt.srcs[p].S(kk, 0, x) for p in rt.srcs)
            if v > best:
                best, bx = v, x
        if bx is not None and np.isfinite(best):
            BOARD[info["iid"]] = {"tick": ticks, "on": False, "x": float(x0 + face * bx), "k": k, "why": "ground"}

    # ---- readiness before the slam ----
    def readiness(self, f, start, r1, cmd: np.ndarray, P: int, ticks: int):
        """[N] penalty (landed-hit units) and [N] readiness of the rows' end states, or None when no Clapper can start
        its slam (a decision state, the hero within READY_RANGE_U)."""
        self.ready_info = None
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
        cx = float(e["pos"][0])
        if stt not in self._dec or abs(cx - hx) > smrt.READY_RANGE_U:
            return None
        rt = self.runtime()
        if rt is None:
            return None
        t0 = time.perf_counter()
        N = r1.box.shape[0]
        Te = r1.box.shape[1] - 1
        xe = 0.5 * (r1.box[:, -1, 0] + r1.box[:, -1, 2])
        side = np.where(xe >= cx, 1, -1)                          # it turns to face the hero at k = 0
        xm = np.abs(xe - cx)
        S0 = st0[:, 0]
        q0 = smrt.phases_of(float(S0[kin.ALO]), float(S0[kin.AHI]), 0)   # the cycle at rollout index 0 (k = 0 there)
        p_end = sorted({(q - Te) % 6 for q in q0} & set(rt.srcs))   # the phase of a slam starting at the row's end
        if not p_end:
            return None
        last = cmd[:, -1] if cmd.shape[1] else np.zeros(N, np.int64)
        kd = np.where((last & kin.B_RIGHT) != 0, 1, np.where((last & kin.B_LEFT) != 0, -1, 0)) * side
        gnd = (r1.flags[:, -1] & kin.F_GROUND) != 0
        glide = r1.mode[:, -1] == kin.M_GLIDE
        yb = r1.box[:, -1, 1] - rt.hm.stand_y0
        yp = r1.box[:, -2, 1] - rt.hm.stand_y0
        R = np.full(N, np.inf)
        for p in p_end:
            R = np.minimum(R, rt.readiness_rows(p, xm, kd, gnd, yb, yp))
        R[glide] = 0.0
        ref = rt.ready_ref
        pen = smrt.READY_W * np.maximum(0.0, ref - np.where(np.isfinite(R), R, 0.0))
        out_ = np.isneginf(R)
        if out_.any() and not out_.all():
            pen = np.where(out_, 100.0, pen)
        # L2 before the slam: the readiness argmax 3-6 u in front of it on the hero's side (standing, no key)
        xs = np.arange(3.0, 6.01, rt.ti.step)
        rv = [min(rt.readiness(float(x), 0, p) for p in p_end) for x in xs]
        bi = int(np.argmax(rv))
        sd = 1 if hx >= cx else -1
        BOARD[iid] = {"tick": ticks, "on": False, "x": None, "ready_x": float(cx + sd * xs[bi]), "k": None,
                      "why": "ready"}
        self.ready_info = {"iid": iid, "state": stt, "ref": round(ref, 3), "R_min": round(float(R.min()), 3),
                           "R_max": round(float(R.max()), 3), "pen_rows": int((pen > 0).sum()),
                           "out_rows": int(out_.sum()), "ready_x": round(float(cx + sd * xs[bi]), 2),
                           "ms": round((time.perf_counter() - t0) * 1e3, 2)}
        return pen, R


__all__ = ["MapHelper", "MapRow", "BOARD"]
