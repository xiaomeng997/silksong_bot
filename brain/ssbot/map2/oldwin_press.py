"""Task oldwin STAGE N (the person, 2026-10-25 ~21:00 PDT: "turn off the old planner's specials and see whether the
new window table can take over"): the SLAM WINDOWS by the reflex's own path, for the old planner with its slam scripts
off (SSBOT_FORUM_SLAM_PLAY=0 SSBOT_FORUM_CLAWSTRIKE=0). SSBOT_FORUM_WINDOWS_PRESS=1 (default off; needs
SSBOT_FORUM_WINDOWS=1 and HERO2; off: nothing of this is imported or run).

THE PATH (HANDOFF 'Task reflex - stage 4', the integration plan, on the old planner):
  worker   a process of its own (spawned at warm-up; the live bot's worker rule: High, the E-cores 16 - 31, EcoQoS off)
           runs THE EXACT CHECK (map2.reflex.Reflex.check: every Clapper and the leftover hazards predicted fresh at
           the observation in closed loop under her path, in EVERY outcome the strike re-derived, no collision with
           anything - the bridge's frames included -, an exit after it) on a snapshot the bot sends while a slam window
           may open (a Clapper in its slam antic within reach). The keys assumed: the keys in flight, then the old
           planner's chosen row for L frames (THE BRIDGE: the press starts at the snapshot's f + L + 2).
           NOW: the table looked up for her state at the bridge's end (the slam types; Clawline windows only when her
           state before the press is in control with no attack under way - cl_ready, stage L's H1);
           APPROACH (none NOW): the old planner's approach shapes (walk / jump / drift: oldwin.WindowRows' vectorized
           keying) into a down-slash cell of the slam types (hop_slam0 / drop_slam0 / pogo_head2) - the approach and
           the cell's macro checked as ONE macro by the same exact check (hop_slam0 comes back only through it).
  bot      the verdict (a reflex.Press for f0 = f + L + 2) COMMITS when it arrives in time and the world is still the
           snapshot's: the keys sent since are the bridge's, no freeze since, the target in the same move at the frame
           the game clock gives, her observed position on the bridge's predicted path (within POS_TOL). Then the bot
           sends the bridge's rest (the old planner's CONTINUE row is held to it - the planner's hold_row - and a
           planner that leaves it (its own check finds it unsafe) cancels the commit) and the Press from f0.
  Press    owns the keys (own 'win'; the scripts are not stepped; the supervisor's keys win and end it) and CONFIRMS
           EACH PHASE from the STATE stream, ending (back to the planner) when one fails:
             approach / pre-press  her position on the macro's predicted lane (within LANE_TOL), the target in its move;
             a down slash          her clip DownSlash* (or the attack flag) by the press + SWING_F - 'no swing';
                                   the contact (a DownSlash hit on the target) by the active frames' end - 'no contact';
             a Clawline            M_CLAW latched at its press frame P - 'claw not latched'; a Harpoon clip by P + 3 -
                                   'no hook' (CLAWSTRIKE's live failure: an eaten Clawline taken as control); the hook's
                                   dash / catch clip before control - 'hook missed'; control (accepting input, no
                                   Harpoon clip, after the hook) and her stop picking the continuation (reflex.pick_alt)
                                   - 'no control' / 'off model'; then the down slash as above;
             a freeze (dt x 60 outside 0.9 .. 1.25) before the strike's press - 'freeze'.
           After the strike's tail (or any end) the planner has the keys again.
Offline (replays, tests): SSBOT_FORUM_WINDOWS_PRESS_INPROC=1 runs the check in the bot's process and makes its verdict
available ceil(check ms / 16.7) frames later (deterministic; the worker's latency modelled).
"""
from __future__ import annotations

import math
import os
import queue
import time
from collections import Counter, deque
from dataclasses import replace

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import reflex as rx

ENV = "SSBOT_FORUM_WINDOWS_PRESS"
SLAM_TYPES = ("claw_slam0", "claw_head2", "hop_slam0", "drop_slam0", "pogo_head2")
APPR_TYPES = ("drop_slam0",)        # (V1: hop_slam0 / pogo_head2 approach presses refuted from a frame later: below)
M_CLAW = rx.M_CLAW
DIRS = km.B_LEFT | km.B_RIGHT


def enabled() -> bool:
    return os.environ.get(ENV, "0").strip() == "1"


def _ienv(name: str, d: int) -> int:
    v = os.environ.get(name, "").strip()
    return int(v) if v else d


def _types(name: str, d: tuple) -> tuple:
    v = os.environ.get(name, "").strip()
    return tuple(t for t in v.split(",") if t in rx.WINDOWS) if v else d


LEAD_L = _ienv("SSBOT_FORUM_WINDOWS_PRESS_L", 3)          # the bridge (frames): the press from the snapshot's f + L + 2
TYPES = _types("SSBOT_FORUM_WINDOWS_PRESS_TYPES", SLAM_TYPES)
APPR = _types("SSBOT_FORUM_WINDOWS_PRESS_APPR", APPR_TYPES)   # 'none' -> () (no approach checks)
if os.environ.get("SSBOT_FORUM_WINDOWS_PRESS_APPR", "").strip() == "none":
    APPR = ()
N_APPR = _ienv("SSBOT_FORUM_WINDOWS_PRESS_NAPPR", 2)      # approach candidates checked per snapshot (the earliest first)
INPROC = os.environ.get("SSBOT_FORUM_WINDOWS_PRESS_INPROC", "0").strip() == "1"
# the re-check of a running down-slash press: 'judge' (default: reflex.judge_press - the generator's exact judge, the
# project's exact check in stages B / F; V1: the runtime check from two frames later refuted 2.5 % fewer than the judge
# from one frame later) or 'check' (Reflex._check, the runtime check's steps A / B)
RECHECK = os.environ.get("SSBOT_FORUM_WINDOWS_PRESS_RECHECK", "judge").strip() or "judge"
REACH_U = 12.0
POS_TOL = 0.15                     # u: her observed position vs the bridge's predicted (the commit)
LANE_TOL = 0.25                    # u: ... vs the macro's predicted lane before the strike's press (the Press)
SWING_F = 2                        # her down slash under way by the press + SWING_F
HOOK_F = 3                         # a Harpoon clip by the Clawline's press + HOOK_F
FREEZE_LO, FREEZE_HI = 0.9, 1.25
FRAME_MS = 1000.0 / 60.0


# ---- the check (the worker's; inproc too; the offline V1 uses it) ------------------------------------------------------

class Checker:
    """The exact check on one snapshot: Reflex.check (NOW, the slam types) and, with none, the approach candidates."""

    def __init__(self, table: "rx.Table | None" = None, W=None, types: tuple = TYPES, appr: tuple = APPR,
                 n_appr: int = N_APPR):
        from ssbot.map2 import oldwin as ow
        from ssbot.map2 import search as ms
        self.table = table if table is not None else rx.Table.load()
        self.W = W if W is not None else ms.World()
        self.R = rx.Reflex(self.table, W=self.W, types=types, cl_ready=True, max_cand=2)
        self.wr = ow.WindowRows(self.table)          # its vectorized approach keying (its tracker unused)
        self.appr = tuple(t for t in appr if t in ow.ALL_DS)
        self.n_appr = int(n_appr)
        self.stats = Counter()
        self.ev = None                                # the judge's evaluator (the re-check; made on first use)

    def check(self, sn: dict) -> dict:
        """sn: S0 (her kin state at fo), inflight (the commands fo + 1 .. f + 1 + L: in flight then the bridge), hold
        (km.HoldState before them), obs / mems / hazards, fo, f (the snapshot's tick), L, claw_free, lat_s,
        claw_lock_until, intro. -> {'press': reflex.Press | None, 'kind', 'why', 'ms', 'pred': her predicted
        positions fo .. f + L + 1, 'lane': the macro's nominal positions from f0 - 1}."""
        t0 = time.perf_counter()
        W = self.W
        L = int(sn["L"])
        f_t = int(sn["f"]) + L
        S0 = np.asarray(sn["S0"], float).reshape(km.K, -1)[:, 0]
        inflight = np.asarray(sn["inflight"], np.int64)
        out = {"press": None, "kind": None, "why": None, "seq": sn.get("seq"), "f": int(sn["f"]), "L": L}
        p = self.R.check(S0, inflight, sn["hold"], sn["obs"], sn["mems"], sn["hazards"], int(sn["fo"]), f_t,
                         claw_free=bool(sn["claw_free"]), lat_s=int(sn["lat_s"]),
                         claw_lock_until=sn["claw_lock_until"], intro=bool(sn["intro"]), bridge=L)
        why = list(self.R.last.get("why") or ())
        kind = "now" if p is not None else None
        if p is None and self.appr and not any(w in ("intro", "in a Clawline") for w in why):
            p, w2 = self._approach(sn, S0, inflight, f_t)
            why += w2
            kind = "appr" if p is not None else None
        out.update(press=p, kind=kind, why=why[:8])
        if p is not None:
            lat_inf = rx._hold_run(inflight, sn["hold"]) if sn["hold"] is not None else inflight
            r = W.roll(S0, lat_inf)
            out["pred"] = np.asarray(r.pos[0, :len(lat_inf) + 1], float)
            S = r.final[:, 0]
            if p.t_abs is not None:
                rl = W.roll(S, p.cmds)
                out["lane"] = np.asarray(rl.pos[0, :len(p.cmds) + 1], float)
            else:
                rl = W.roll(S, p.cmds[:max(p.p_abs - p.f0 + 1, 1)])
                out["lane"] = np.asarray(rl.pos[0], float)
        out["ms"] = (time.perf_counter() - t0) * 1e3
        self.stats["checks"] += 1
        self.stats["press_" + str(kind)] += 1
        return out

    def recheck(self, sn: dict) -> dict:
        """THE RE-CHECK of a running down-slash press (the bridge's rest and the press's keys from the snapshot's f + 2
        - `rest` -, its slash at rest frame t_rel) from a newer observation: the same exact check (Reflex._check, steps
        A and B) as one raw macro after the keys in flight. {'ok', 'why', 'ms'}."""
        t0 = time.perf_counter()
        W = self.W
        S0 = np.asarray(sn["S0"], float).reshape(km.K, -1)[:, 0]
        inflight = np.asarray(sn["inflight"], np.int64)
        hold = sn["hold"]
        lat_inf = rx._hold_run(inflight, hold) if (hold is not None and len(inflight)) else inflight
        lead = len(lat_inf)
        S = W.roll(S0, lat_inf).final[:, 0] if len(lat_inf) else S0
        live = [o for o in sn["obs"] if o.st is not None and o.hp > 0 and o.st not in cm.DEAD]
        o0 = next((o for o in live if int(o.iid) == int(sn["iid"])), None)
        out = {"kind": "recheck", "seq": sn.get("seq"), "f": int(sn["f"]), "ok": False, "why": "", "ms": 0.0}
        rest = np.asarray(sn["rest"], np.int64)
        t_rel = int(sn["t_rel"])
        if o0 is None:
            out["why"] = "target gone"
        elif t_rel < 1 or t_rel > len(rest):
            out.update(ok=True, why="past the press")
        elif any(o.st in cm.INTRO for o in sn["obs"] if o.st is not None and o.hp > 0):
            out["why"] = "intro"
        elif RECHECK == "check":
            m = rx.Macro("ds", raw=(rest, 0, np.zeros(0, np.int64), [t_rel]))
            ok, r, _ = self.R._check(S0, lat_inf, S, lead, int(sn["fo"]), live, sn["mems"], sn["hazards"], o0,
                                     rx.WINDOWS[sn["window"]], m, int(sn["d"]))
            out.update(ok=bool(ok), why=r)
        else:
            # THE JUDGE (map2.reflex.judge_press: the generator's exact judge, the stage B / F audits' authority) from
            # her state at the observation with the keys in flight prepended to the press's rest - every Clapper as
            # observed, in closed loop over the whole path
            if self.ev is None:
                self.ev = rx.judge_evaluator(W)
            obs_j = [o for o in live if o.st not in cm.INTRO]
            m = rx.Macro("ds", raw=(np.concatenate([np.asarray(lat_inf, np.int64), rest]), 0, np.zeros(0, np.int64),
                                    [lead + t_rel]))
            v = rx.judge_press(W, self.ev, S0, obs_j, int(sn["iid"]), rx.WINDOWS[sn["window"]], m, mems=sn["mems"],
                               hazards=sn["hazards"])
            out.update(ok=bool(v.window), why=v.why, n=(v.lands, v.safe, v.exit, v.n))
        out["ms"] = (time.perf_counter() - t0) * 1e3
        self.stats["recheck_" + ("ok" if out["ok"] else "fail")] += 1
        return out

    def _approach(self, sn: dict, S0, inflight, f_t: int) -> tuple:
        """The approach shapes into a down-slash cell of the slam types (oldwin.WindowRows._approach's keying from her
        state at the bridge's end), the earliest strikes first; each approach + the cell's macro exact-checked as one
        macro (Reflex._check: steps A and B). (Press | None, why list)."""
        from ssbot.map2 import oldwin as ow
        W = self.W
        why = []
        hold = sn["hold"]
        inflight = np.asarray(inflight, np.int64)
        lat_inf = rx._hold_run(inflight, hold) if (hold is not None and len(inflight)) else inflight
        P = len(inflight)                              # f_t + 1 - fo: the shapes start after the bridge
        S = W.roll(S0, lat_inf).final[:, 0] if len(lat_inf) else S0
        live = [o for o in sn["obs"] if o.st is not None and o.hp > 0 and o.st not in cm.DEAD]
        near = [o for o in live if abs(o.x - float(S[km.PX])) <= REACH_U and o.j is not None and
                ow._types_in(o.st, int(o.j) + P, int(o.j) + P + 36, self.appr)]
        if not near:
            return None, why
        T = 36
        M, names = ow._templates(T, bool(int(S[km.GROUND])))
        # the shapes after the keys in flight + the bridge, latched by the hold filter from the snapshot's state
        lat_full, _ = km.hold_filter(np.concatenate([np.broadcast_to(inflight, (len(M), P)), M], axis=1),
                                     rx._hold_tuple(hold) if hold is not None else None)
        ro = km.rollout(S0, lat_full, W.params, W.terr, threads=1)
        cands, info = [], {"part": Counter(), "appr_found": 0, "appr_rekey_miss": 0}
        wr = self.wr
        wr._params, wr._terrain, wr._threads = W.params, W.terr, 1
        wr._approach(S0, lat_inf, ro, lat_full, M, names, near, P, T, cands, info, types=self.appr, margin=False)
        if not cands:
            return None, why
        cands.sort(key=lambda c: c.k0)
        n = 0
        for c in cands:
            if n >= self.n_appr:
                why.append("appr cap")
                break
            o0 = next((x for x in live if int(x.iid) == int(c.iid)), None)
            if o0 is None:
                continue
            wt = rx.WINDOWS[c.wt]
            cmd = np.asarray(c.cmd, np.int64)
            t_rel = int(c.j) + int(c.macro.t)
            if hold is not None and not rx._hold_ok(cmd, inflight, hold):
                why.append("appr hold")
                continue
            if float(S[km.ATK_CD]) > (t_rel - 1) / 60.0 + 1e-6:
                why.append("appr attack")
                continue
            ox = o0.x + (float(o0.vx) * P / 60.0 if o0.st in rx.JUMPING else 0.0)
            d = 1 if ox >= float(S[km.PX]) else -1
            lead = P
            m = rx.Macro("ds", raw=(cmd, 0, np.zeros(0, np.int64), [t_rel]))
            n += 1
            tc = time.perf_counter()
            ok, r, _ = self.R._check(S0, lat_inf, S, lead, int(sn["fo"]), live, sn["mems"], sn["hazards"], o0, wt, m,
                                     d, k_lo=lead + 1 - int(sn["L"]))
            self.R.ms["check_appr"].append((time.perf_counter() - tc) * 1e3)
            if not ok:
                why.append("appr " + r)
                continue
            b = int(sn["f"]) + int(sn["L"]) + 1          # f0 - 1 (= fo + P)
            ks = (int(sn["fo"]) + int(c.k0), int(sn["fo"]) + int(c.k1))   # (Cand.k0: state index from fo)
            p = rx.Press(c.wt, int(c.iid), None, m, (1, 1), b + 1, cmd.copy(), b + len(cmd), ks, {}, 0,
                         rx._value(wt), 0.0, d=d, t_abs=b + t_rel, strike=wt.strike)
            p.__dict__["appr"] = (c.tpl, int(c.j), c.label)
            return p, why
        return None, why


# ---- the worker process ------------------------------------------------------------------------------------------------

def worker_main(in_q, out_q, idle, prio: str = "high", cpus: str = "16-31") -> None:
    """The check worker: one snapshot at a time (the bot sends one only while `idle` is raised)."""
    try:
        from ssbot.map2 import live as m2live
        boost = m2live.boost_self(prio, cpus)
    except Exception as e:  # noqa: BLE001
        boost = f"boost failed {e!r}"
    try:
        import numba
        numba.set_num_threads(max(1, min(2, numba.config.NUMBA_NUM_THREADS)))
    except Exception:  # noqa: BLE001
        pass
    t0 = time.perf_counter()
    ck = Checker()
    warm_ms = warm_checker(ck)
    out_q.put({"kind": "ready", "boost": boost, "s": time.perf_counter() - t0, "warm_ms": warm_ms})
    while True:
        idle.value = 1
        try:
            sn = in_q.get()
        except (EOFError, OSError):
            return
        idle.value = 0
        if sn is None or sn.get("stop"):
            return
        try:
            v = ck.recheck(sn) if sn.get("kind") == "recheck" else ck.check(sn)
        except Exception as e:  # noqa: BLE001 - reported; the bot goes on without a verdict
            v = {"kind": "error", "seq": sn.get("seq"), "error": repr(e)[:300]}
        v.setdefault("kind_msg", "verdict")
        out_q.put(v)


def warm_checker(ck: Checker) -> float:
    """The check's compiled paths before the first slam (a synthetic slam antic in front of her: the lookup, the
    closed-loop prediction, a down slash check, a Clawline check, an approach)."""
    t0 = time.perf_counter()
    try:
        from ssbot.map2 import strike as sk
        W = ck.W
        S0 = km.initial_state(W.params, 30.0, sk.FLOOR + sk.FOOT, ground=True, facing=1)
        for dx, j in ((5.5, 2), (4.5, 10), (8.0, 0), (3.0, 30)):
            o = cm.Obs(7, "Slam Antic", j / 60.0, 30.0 + dx, sk.FLOOR + 1.2, 0.0, 0.0, -1, 230, "Slam Antic", j=j)
            sn = {"S0": S0, "inflight": np.zeros(4, np.int64), "hold": km.HoldState.idle(1) if hasattr(
                km.HoldState, "idle") else None, "obs": [o], "mems": {7: cm.Memory()}, "hazards": [], "fo": 1000,
                  "f": 1000, "L": 3, "claw_free": True, "lat_s": 0, "claw_lock_until": None, "intro": False}
            ck.check(sn)
        rest = np.zeros(30, np.int64)
        rest[:12] |= km.B_JUMP
        rest[18:20] |= km.B_ATTACK | km.B_DOWN
        ck.recheck({"S0": S0, "inflight": np.zeros(2, np.int64), "hold": sn["hold"], "obs": [o], "mems": {7: cm.Memory()},
                    "hazards": [], "fo": 1000, "f": 1001, "rest": rest, "t_rel": 19, "iid": 7, "window": "hop_slam0",
                    "d": 1})
    except Exception:  # noqa: BLE001 - a failed warm-up only costs the first check's compile
        pass
    return (time.perf_counter() - t0) * 1e3


# ---- the bot side ------------------------------------------------------------------------------------------------------

class WinPress:
    """The bot's side (policy): the snapshots, the verdicts, the commit, the running Press and its phase checks."""

    def __init__(self, win, inproc: bool = INPROC, L: int = LEAD_L):
        self.win = win                     # oldwin.WindowRows: its Clapper tracker (game clock) and gates
        self.inproc = bool(inproc)
        self.L = int(L)
        self.K = cm.Know.load()
        self.ck: Checker | None = None
        self.proc = None
        self.in_q = self.out_q = self.idle = None
        self.ready = None
        self.st = Counter()
        self.ms: dict = {k: deque(maxlen=200000) for k in ("decide", "post", "check", "latency_f", "recheck",
                                                             "recheck_latency_f")}
        self.log: list = []                # (offline) the commits / presses / ends
        self.reset()

    # ---- processes ----
    def start(self, wait: bool = True, timeout: float = 240.0) -> float:
        t0 = time.perf_counter()
        if self.inproc:
            self.ck = Checker()
            self.ready = {"warm_ms": warm_checker(self.ck)}
            return time.perf_counter() - t0
        import atexit
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        self.in_q, self.out_q = ctx.Queue(), ctx.Queue()
        self.in_q.cancel_join_thread()
        self.idle = ctx.Value("b", 0)
        self.proc = ctx.Process(target=worker_main, args=(self.in_q, self.out_q, self.idle), daemon=True,
                                name="oldwin-press-worker")
        self.proc.start()
        atexit.register(self.stop)
        while wait and time.perf_counter() - t0 < timeout:
            try:
                m = self.out_q.get(timeout=1.0)
            except queue.Empty:
                if not self.proc.is_alive():
                    break
                continue
            if m.get("kind") == "ready":
                self.ready = m
                break
        return time.perf_counter() - t0

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            self.in_q.put({"stop": True})
            self.proc.join(timeout=3.0)
            if self.proc.is_alive():
                self.proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        self.proc = None

    # ---- per episode / per STATE ----
    def reset(self) -> None:
        self.seq = 0
        self.out: dict | None = None       # the snapshot in the worker: {seq, f, fo, g, keys, iids ...}
        self.pend: list = []               # inproc: (available frame, verdict)
        self.commit: dict | None = None    # a verdict committed: its bridge keys and the Press
        self.press = None                  # the running reflex.Press
        self.pinfo: dict = {}
        self.claw_P = None                 # her Clawlines (the lock): the last press frame, its control
        self.claw_ctl = None
        self._lat_prev = 0
        self.last_freeze = None
        self.clip_hist: deque = deque(maxlen=90)     # (f, clip, accepting input, x, y, latched mask)
        self.hits: deque = deque(maxlen=64)          # (f, ent, src)
        self.verdict = None
        self.abort_f = None

    def feed(self, raw: dict, f: int) -> None:
        """Every STATE (the policy's _wake, after WindowRows.feed): her clip / input / latched keys, her hits, freezes,
        her Clawlines' press and control (the lock)."""
        h = raw.get("hero") or {}
        clip = str(((h.get("anim") or {}).get("clip")) or "")
        acc = bool(h.get("hero_accepting_input", True))
        pos = h.get("pos") or (np.nan, np.nan)
        lm = int((raw.get("act") or {}).get("mask") or 0)
        self.clip_hist.append((int(f), clip, acc, float(pos[0]), float(pos[1]), lm))
        if (lm & M_CLAW) and not (self._lat_prev & M_CLAW):
            self.claw_P, self.claw_ctl = int(f), None
        elif self.claw_P is not None and self.claw_ctl is None and int(f) >= self.claw_P + 3 and acc and \
                not clip.startswith("Harpoon"):
            self.claw_ctl = int(f)
        self._lat_prev = lm
        dt_ = raw.get("dt")
        dt = 1.0 / 60.0 if dt_ is None else float(dt_)
        if not (FREEZE_LO <= dt * 60.0 <= FREEZE_HI):
            self.last_freeze = int(f)
        for e in raw.get("ev") or ():
            if e.get("k") == "hit":
                d = e.get("d") or {}
                self.hits.append((int(f), int(d.get("ent") or 0), str(d.get("src") or "")))

    # ---- helpers ----
    def _clip_at(self, k: int):
        for (ff, c, a, x, y, lm) in reversed(self.clip_hist):
            if ff == k:
                return c, a, x, y, lm
            if ff < k:
                break
        return None

    def _obs(self, iid: int):
        return next((o for o in self.win.obs() if int(o.iid) == int(iid)), None)

    def busy(self) -> bool:
        return self.press is not None or self.commit is not None

    def hold_row(self, f: int):
        """The old planner's CONTINUE row while a commit's bridge runs (its keys from f + 2), else None."""
        c = self.commit
        if c is None:
            return None
        i = int(f) + 2 - c["k2"]
        b = c["bridge"]
        if 0 <= i < len(b):
            return np.asarray(b[i:], np.int64)
        return None

    def _end(self, why: str, f: int) -> None:
        p = self.press
        if p is not None:
            self.st["end_" + why.split(":")[0]] += 1
            self.log.append({"ev": "end", "f": int(f), "why": why, "window": p.window, "iid": p.iid,
                             "f0": p.f0, **{k: v for k, v in self.pinfo.items() if k in ("kind", "contact", "ctrl")}})
        self.press = None
        self.pinfo = {}

    # ---- the tick: the keys for f + 2 (None: the planner's / the scripts') ----
    def decide(self, f: int, fo: int, raw: dict, S0, prefix, hold, res, sent: dict, sup: bool,
               crit: bool = False) -> int | None:
        t0 = time.perf_counter()
        try:
            return self._decide(int(f), int(fo), raw, S0, prefix, hold, res, sent, sup, crit)
        finally:
            self.ms["decide"].append((time.perf_counter() - t0) * 1e3)

    def _decide(self, f, fo, raw, S0, prefix, hold, res, sent, sup, crit) -> int | None:
        if sup:
            if self.press is not None:
                self._end("supervisor", f)
            if self.commit is not None:
                self.st["commit_sup"] += 1
                self.commit = None
            return None
        self._drain(f)
        if self.press is None and self.commit is None and self.verdict is not None:
            self._try_commit(f, fo, S0, sent, crit)
        if self.commit is not None:
            c = self.commit
            k = f + 2
            if k < c["f0"]:
                # the bridge: the planner held to it; it left it (its own check) -> cancelled
                bk = int(c["bridge"][k - c["k2"]])
                if c["f_commit"] != f and res is not None and len(getattr(res, "cmd", ())) and int(res.cmd[0]) != bk:
                    self.st["commit_planner_left"] += 1
                    self.log.append({"ev": "cancel", "f": f, "why": "planner left the bridge", "window": c["press"].window})
                    self.commit = None
                    return None
                if not self._still(c, fo, S0, f):
                    self.commit = None
                    return None
                return bk
            self.press = c["press"]
            self.pinfo = {"kind": c["kind"], "lane": c.get("lane"), "contact": None, "hooked": False,
                          "ctrl": None, "dx": None, "f_commit": c["f_commit"]}
            self.commit = None
            self.st["press_" + self.press.window] += 1
            self.log.append({"ev": "press", "f": f, "window": self.press.window, "iid": self.press.iid,
                             "f0": self.press.f0, "kind": self.pinfo["kind"], "label": self.press.macro.label()})
        if self.press is None:
            return None
        return self._step(f, fo, raw, S0)

    def _still(self, c: dict, fo: int, S0, f: int) -> bool:
        """The world still the snapshot's (the commit and each bridge tick)."""
        if self.last_freeze is not None and self.last_freeze > c["fo"]:
            self.st["commit_freeze"] += 1
            return False
        o = self._obs(c["iid"])
        if o is None or o.st != c["st"] or int(o.j) != c["oj"] + (self.win.gk - c["g"]):
            self.st["commit_clapper"] += 1
            return False
        i = fo - c["fo"]
        pred = c["pred"]
        st0 = np.asarray(S0).reshape(km.K, -1)[:, 0]
        if 0 <= i < len(pred) and (abs(float(st0[km.PX]) - pred[i, 0]) > POS_TOL or
                                   abs(float(st0[km.PY]) - pred[i, 1]) > POS_TOL):
            self.st["commit_pos"] += 1
            return False
        return True

    def _drain(self, f: int) -> None:
        """The worker's / the inproc verdicts that are due."""
        self.verdict = None
        msgs = []
        if self.inproc:
            due = [v for (k, v) in self.pend if k <= f]
            self.pend = [(k, v) for (k, v) in self.pend if k > f]
            msgs = due
        elif self.out_q is not None:
            while True:
                try:
                    msgs.append(self.out_q.get_nowait())
                except queue.Empty:
                    break
                except Exception:  # noqa: BLE001
                    break
        for v in msgs:
            if v.get("kind") == "ready":
                self.ready = v
                continue
            o = self.out
            if o is None or v.get("seq") != o["seq"]:
                self.st["verdict_stale"] += 1
                continue
            self.out = None
            if v.get("kind") == "error":
                self.st["verdict_error"] += 1
                continue
            if o.get("kind") == "recheck":
                self.ms["recheck"].append(float(v.get("ms") or 0.0))
                self.ms["recheck_latency_f"].append(f - o["f"])
                ok = bool(v.get("ok"))
                self.st["recheck_" + ("ok" if ok else "fail")] += 1
                p_now = self.press if self.press is not None else (self.commit or {}).get("press")
                if not ok and p_now is not None and (p_now.window, p_now.f0) == o["pk"]:
                    why = "recheck " + str(v.get("why") or "")
                    self.log.append({"ev": "recheck_fail", "f": f, "why": why, "window": p_now.window,
                                     "f0": p_now.f0, "snap_f": o["f"]})
                    if self.press is not None:
                        self._end(why, f)
                        self.abort_f = f
                    else:
                        self.st["commit_recheck"] += 1
                        self.commit = None
                continue
            self.ms["check"].append(float(v.get("ms") or 0.0))
            self.ms["latency_f"].append(f - o["f"])
            if v.get("press") is None:
                self.st["verdict_none"] += 1
                continue
            v["_snap"] = o
            self.verdict = v

    def _try_commit(self, f: int, fo: int, S0, sent: dict, crit: bool) -> None:
        v, self.verdict = self.verdict, None
        o = v["_snap"]
        p = v["press"]
        if crit:
            self.st["commit_crit"] += 1                   # a script's critical window (LOWHOP's bomb hop): not now
            return
        if f + 2 > p.f0:
            self.st["commit_late"] += 1
            return
        # the keys sent since the snapshot (f_s + 2 .. f + 1) are the bridge's
        for k in range(o["f"] + 2, f + 2):
            if int(sent.get(k, -1)) != int(o["bridge"][k - (o["f"] + 2)]):
                self.st["commit_keys"] += 1
                return
        tgt = next((x for x in o["obs"] if int(x.iid) == int(p.iid)), None)
        c = {"press": p, "kind": v.get("kind"), "lane": v.get("lane"), "pred": v["pred"], "fo": o["fo"], "g": o["g"],
             "iid": p.iid, "st": None if tgt is None else tgt.st, "oj": None if tgt is None else int(tgt.j),
             "bridge": o["bridge"], "k2": o["f"] + 2, "f0": p.f0, "f_commit": f}
        if not self._still(c, fo, S0, f):
            return
        self.commit = c
        self.st["commit"] += 1
        self.log.append({"ev": "commit", "f": f, "window": p.window, "iid": p.iid, "f0": p.f0, "kind": v.get("kind"),
                         "label": p.macro.label(), "snap_f": o["f"], "check_ms": v.get("ms")})

    def _step(self, f: int, fo: int, raw: dict, S0) -> int | None:
        """The running Press: its phase checks on the STATE at fo, then its key for f + 2."""
        p = self.press
        pi = self.pinfo
        iid = int(p.iid)
        # the contact: a DownSlash hit on the target since the strike could land
        k_ds = p.t_abs if p.t_abs is not None else None
        if pi.get("contact") is None:
            for (ff, ent, src) in self.hits:
                if ent == iid and "Down" in src and ff >= (k_ds if k_ds is not None else (p.p_abs or p.f0)):
                    pi["contact"] = ff
                    break
        o = self._obs(iid)
        strike_k = p.t_abs if p.t_abs is not None else None
        if p.p_abs is None:
            # a down slash press (incl. an approach): the lane before the press, the swing, the contact
            if fo < p.t_abs:
                if self.last_freeze is not None and self.last_freeze >= p.f0 - 1:
                    self._end("freeze", f)
                    return None
                if o is None or o.hp <= 0:
                    self._end("target gone", f)
                    return None
                lane = pi.get("lane")
                i = fo - (p.f0 - 1)
                if lane is not None and 0 <= i < len(lane):
                    st0 = np.asarray(S0).reshape(km.K, -1)[:, 0]
                    if abs(float(st0[km.PX]) - lane[i, 0]) > LANE_TOL or abs(float(st0[km.PY]) - lane[i, 1]) > LANE_TOL:
                        self._end("off lane", f)
                        return None
            elif fo >= p.t_abs + SWING_F and pi.get("contact") is None:
                c = self._clip_at(fo)
                if c is not None and not c[0].startswith("DownSlash") and not c[0].startswith("DownSpike"):
                    self._end("no swing", f)
                    return None
        else:
            P = int(p.p_abs)
            if fo < P:
                if self.last_freeze is not None and self.last_freeze >= p.f0 - 1:
                    self._end("freeze", f)
                    return None
                if o is None or o.hp <= 0:
                    self._end("target gone", f)
                    return None
                lane = pi.get("lane")
                i = fo - (p.f0 - 1)
                if lane is not None and 0 <= i < len(lane):
                    st0 = np.asarray(S0).reshape(km.K, -1)[:, 0]
                    if abs(float(st0[km.PX]) - lane[i, 0]) > LANE_TOL or abs(float(st0[km.PY]) - lane[i, 1]) > LANE_TOL:
                        self._end("off lane", f)
                        return None
            else:
                cP = self._clip_at(P)
                if cP is not None and not (cP[4] & M_CLAW):
                    self._end("claw not latched", f)
                    return None
                if fo >= P + HOOK_F and not pi.get("harpoon"):
                    seen = any(c.startswith("Harpoon") for (ff, c, a, x, y, lm) in self.clip_hist if P <= ff <= fo)
                    if not seen:
                        self._end("no hook", f)
                        return None
                    pi["harpoon"] = True
                if not pi.get("hooked"):
                    pi["hooked"] = any(c in ("Harpoon Dash", "Harpoon Catch") for (ff, c, a, x, y, lm)
                                       in self.clip_hist if P <= ff <= fo)
                if pi.get("ctrl") is None and pi.get("harpoon"):
                    for (ff, c, a, x, y, lm) in self.clip_hist:
                        if ff >= P + HOOK_F and a and not c.startswith("Harpoon") and ff <= fo:
                            if not pi.get("hooked"):
                                self._end("hook missed", f)
                                return None
                            pi["ctrl"] = ff
                            ob = self._obs(iid)
                            if ob is not None:
                                pi["dx"] = (x - float(ob.x)) * int(p.d)
                            break
                strike_k = None
                if pi.get("ctrl") is not None and p.alts:
                    a = p.pick(pi["ctrl"], pi.get("dx"))
                    strike_k = None if a is None else a[1][3]
                if strike_k is not None and fo >= strike_k + SWING_F and pi.get("contact") is None:
                    c = self._clip_at(fo)
                    if c is not None and not c[0].startswith("DownSlash") and not c[0].startswith("DownSpike"):
                        self._end("no swing", f)
                        return None
        why = p.status(fo, pi.get("contact") is not None, pi.get("ctrl"), pi.get("dx"))
        if why is not None:
            self._end(why, f)
            return None
        m = p.cmd_at(f + 2, pi.get("ctrl"), pi.get("dx"))
        if m is None:
            self._end("done" if pi.get("contact") is not None or p.strike != "down" else (p.ended or "over"), f)
            return None
        return int(m)

    # ---- after the tick: the snapshot to the worker ----
    def post(self, f: int, fo: int, raw: dict, S0, prefix, hold, mask: int, own: str, res_cmd, sup: bool) -> None:
        t0 = time.perf_counter()
        try:
            self._post(int(f), int(fo), raw, S0, prefix, hold, int(mask), own, res_cmd, sup)
        finally:
            self.ms["post"].append((time.perf_counter() - t0) * 1e3)

    def _send(self, sn: dict, out: dict) -> None:
        self.out = out
        if self.inproc:
            ck = self.ck
            v = ck.recheck(sn) if sn.get("kind") == "recheck" else ck.check(sn)
            k = int(sn["f"]) + max(1, int(math.ceil(float(v.get("ms") or 0.0) / FRAME_MS)))
            self.pend.append((k, v))
        else:
            try:
                self.in_q.put(sn)
            except Exception:  # noqa: BLE001
                self.out = None
                self.st["post_error"] += 1

    def _recheck(self, f, fo, S0, prefix, hold, mask) -> None:
        """A running / committed down-slash press re-checked from this observation (its keys from f + 2: the bridge's
        rest and the press's), while its slash is still ahead; a failing re-check ends it (_drain)."""
        p = self.press if self.press is not None else (self.commit or {}).get("press")
        if p is None or p.t_abs is None or f + 2 >= p.t_abs:
            return
        if self.commit is not None:
            c = self.commit
            i = f + 2 - c["k2"]
            rest = np.concatenate([np.asarray(c["bridge"][max(i, 0):], np.int64), np.asarray(p.cmds, np.int64)])
        else:
            rest = np.asarray(p.cmds[max(f + 2 - p.f0, 0):], np.int64)
        if not len(rest) or int(rest[0]) != int(mask):
            return
        win = self.win
        self.seq += 1
        sn = {"kind": "recheck", "seq": self.seq, "S0": np.asarray(S0).reshape(km.K, -1)[:, 0].copy(),
              "inflight": np.asarray(prefix, np.int64), "hold": hold, "obs": list(win.obs()), "mems": win.trk.mems(),
              "hazards": win.trk.hazards(self.K), "fo": fo, "f": f, "rest": rest, "t_rel": int(p.t_abs) - (f + 1),
              "iid": int(p.iid), "window": p.window, "d": int(p.d)}
        self.st["recheck_sent"] += 1
        self._send(sn, {"seq": self.seq, "f": f, "fo": fo, "kind": "recheck", "pk": (p.window, p.f0)})

    def _post(self, f, fo, raw, S0, prefix, hold, mask, own, res_cmd, sup) -> None:
        if sup:
            return
        if self.out is not None:
            if f - self.out["f"] > self.L + 30:
                self.out = None                         # a lost answer: send again
            else:
                return
        if not self.inproc and (self.idle is None or not self.idle.value):
            return
        if self.busy():
            if own == "win":
                self._recheck(f, fo, S0, prefix, hold, mask)
            return
        if own != "plan" or res_cmd is None or len(res_cmd) < self.L:
            return
        win = self.win
        st0 = np.asarray(S0).reshape(km.K, -1)[:, 0]
        hx = float(st0[km.PX])
        allo = win.obs()
        live = [o for o in allo if o.st is not None and o.hp > 0 and abs(o.x - hx) <= REACH_U]
        lead = f + 1 - fo + self.L
        if not any(rx.in_states(o.st, int(o.j) + lead + jj, w.anchor) for o in live for w in
                   (rx.WINDOWS[t] for t in TYPES) for jj in (0, 2)):
            return
        bridge = np.concatenate([[mask], np.asarray(res_cmd[1:self.L], np.int64)]).astype(np.int64)
        inflight = np.concatenate([np.asarray(prefix, np.int64), bridge])
        claw_busy = self.claw_P is not None and self.claw_ctl is None and f - self.claw_P < 36
        lock = (self.claw_ctl + 13) if self.claw_ctl is not None else None
        self.seq += 1
        sn = {"seq": self.seq, "S0": st0.copy(), "inflight": inflight, "hold": hold, "obs": list(allo),
              "mems": win.trk.mems(), "hazards": win.trk.hazards(self.K), "fo": fo, "f": f, "L": self.L,
              "claw_free": not claw_busy, "lat_s": int((raw.get("act") or {}).get("mask") or 0),
              "claw_lock_until": lock, "intro": False}
        self.st["snap"] += 1
        self._send(sn, {"seq": self.seq, "f": f, "fo": fo, "g": win.gk, "bridge": bridge, "obs": list(allo),
                        "kind": "check"})

    def stats(self) -> dict:
        def pc(v, q):
            return round(float(np.percentile(list(v), q)), 3) if len(v) else None
        return {"counts": dict(self.st), **{f"{k}_p50": pc(v, 50) for k, v in self.ms.items()},
                **{f"{k}_p99": pc(v, 99) for k, v in self.ms.items()}, "ready": self.ready}


__all__ = ["ENV", "enabled", "Checker", "WinPress", "SLAM_TYPES", "TYPES", "worker_main"]
