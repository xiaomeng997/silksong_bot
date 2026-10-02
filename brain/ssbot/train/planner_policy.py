"""PlannerPolicy: the M2 combat stack as a run_episode policy (W3 + W4 integration; DESIGN §3.5, §3.7, §3.9.2).

    pol = PlannerPolicy(view="oracle")             # stage B; view="degraded": stage C (DegradedOracleBackend)
                                                    # "degraded_dust": stage C with the dust cues
    pol.attach(link)                                # once per link: the TERRAIN tap
    run_episode(link, BELL_BEAST, tap, pol, cfg, rec)   # reset(rng, enc) per episode, act(state, tap) -> mask per STATE

Per STATE (this is the only place where backends meet the combat stack, which reads WorldState only):
  1. backend: OracleBackend (stage B) or DegradedOracleBackend = ObservabilityFilter + SimpleNoise + DelayLine
     (stage C, k = 2-4 frames per episode); both reset per episode. In stage C the WorldState is k frames old.
  2. the hero's kinematic start state: StateTracker on the STATE of the WorldState's frame (the hero's self-state:
     its own inputs and kinematics; the vision-side self-estimator is M3), with the observed (noisy) position put in.
  3. forecast (combat.forecast) -> SupportSet for the supervisor; tactics (combat.tactics) -> mode and preferences;
     safety filter context (combat.safety_filter); planner tick (combat.planner) with the commanded masks already
     sent for the frames between the WorldState and the decision frame as its prefix.
  4. SupervisedControl (train/supervision.py): risk tier, triggers, PAUSE_PENDING and the emulated pause / quit;
     its keys replace the planner's while it pauses. A pause machine outcome ends the episode as QUIT
     (episode_outcome); the harness lets the policy own the pause (pause_owned).
  5. unpredicted hits: a hero hit whose box (frame c or c - 1) is outside the support forecast L = 3 frames earlier
     (the stage-A recall pairing) counts for the supervisor's Q4.
The decision log (decisions_i<N>.jsonl in the run directory) keeps the 90 ticks before every hero hit, lethal hit,
FORCED_RISK and supervisor pause, and 10 after, for ssbot.tools.postmortem.
"""
import json
import math
import os
import random
import time
from collections import Counter, deque
from pathlib import Path

import numpy as np

from ssbot.backends.degraded import DegradedOracleBackend
from ssbot.backends.observability import ObservabilityFilter
from ssbot.backends.oracle_backend import OracleBackend
from ssbot.combat.boss_model import BossModel
from ssbot.combat.forecast import Forecaster, load_planner_templates
from ssbot.combat.planner import Planner, PlannerConfig
from ssbot.combat.safety_filter import FilterContext
from ssbot.combat.tactics import Tactics, load_playbook
from ssbot.core.bosses import BOSSES
from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.kinematics import HeroParams, HoldState, StateTracker, Terrain2D
from ssbot.safety.pause_quit import TERMINAL
from ssbot.safety.supervisor import SupervisorConfig
from ssbot.train.supervision import SupervisedControl

MARGIN_ORACLE = (0.15, 0.25)          # DESIGN §3.5.3 m = 0.15 u; y + 0.10 u so a jump's lane spread fits one point
COMFORT = (0.25, 0.25)                # preferred extra clearance (planner: S = 0 > comfort > V > J)
NOISE_K = 3.0                         # stage C: + k * sigma of the hero / boss position noise
HORIZON_S = 2.0                       # forecast horizon: the risk map's and the Bind's
UNPRED_LAG = 3
LOG_BEFORE, LOG_AFTER = 90, 10
LOG_ALL = os.environ.get("SSBOT_LOG_ALL") == "1"     # debugging: every tick to the decision log
# Underground cues for the vision view (ObservabilityFilter tells; hypotheses until M3 measures tell_lead_vision in
# shadow mode). DUST_TELL: the emergence dust the person reported (2026-10-02), seen in screenshots of instance 3
# (C:/ssbot/sandbox/m2_tells, ssbot.probes.m2_tells: 10 charges, 12 leaps from both anchors, 9 bursts): none at
# +0.1 s after Emerge Antic C / L or Burst Antic, dust where the boss will come up from +0.3 s, low for a charge, a
# tall column with debris for a leap, told apart for certain at +0.6 s (the emergence antics last 1.0 s, the burst's
# 1.2 s). BURST_TELL: the burst position from the antic's first frame, the first experiment (run 20261002_061942).
DUST_TELL = {"Bone Beast": {"Emerge Antic C": [(0.3, "dust"), (0.6, "dust_low")],
                            "Emerge Antic L": [(0.3, "dust"), (0.6, "dust_tall")],
                            "Burst Antic": [(0.3, "dust_burst")]}}
BURST_TELL = {"Bone Beast": {"Burst Antic": "burst_tell"}}
TELLS = {"degraded": None, "degraded_dust": DUST_TELL, "degraded_tell": BURST_TELL}
VIEWS = ("oracle", "degraded", "degraded_dust", "degraded_tell")


class TerrainTap:
    """The latest TERRAIN message per scene (sent once a room has finished entering)."""

    def __init__(self, link):
        import threading
        self.cv = threading.Condition()
        self.by_scene: dict = {}
        link.subscribe_raw(self._on_raw)

    def _on_raw(self, msg_type: int, raw: bytes) -> None:
        from ssbot.ipc.framing import MsgType
        if msg_type != MsgType.TERRAIN:
            return
        from ssbot.oracle.messages import split_frame, unpack
        msg = unpack(split_frame(raw)[2])
        with self.cv:
            self.by_scene[msg.get("scene_raw")] = (time.monotonic(), msg)
            self.cv.notify_all()

    def wait(self, scene: str, newer_than: float = 0.0, timeout_s: float = 15.0) -> dict | None:
        with self.cv:
            self.cv.wait_for(lambda: scene in self.by_scene and self.by_scene[scene][0] > newer_than, timeout_s)
            v = self.by_scene.get(scene)
            return v[1] if v else None


class PlannerPolicy:
    def __init__(self, view: str = "oracle", threads: int = 8, enemy: str = "BellBeast", log_dir: Path | None = None,
                 instance: int = 0):
        import cv2
        import numba
        numba.set_num_threads(threads)
        # the template dilation (cv2) uses every core by default: a worker starting next to running ones starved
        # them past the oracle's 250 ms brain-lost watchdog (run 20261002_050217: three games paused at once)
        cv2.setNumThreads(2)
        if view not in VIEWS:
            raise ValueError(f"unknown view {view!r}")
        self.view = view
        self.threads = threads
        self.params = HeroParams.load()
        self.model = BossModel.load(enemy)
        self.spec = BOSSES[self.model.boss_type]
        if view == "oracle":
            margin = MARGIN_ORACLE
            fview = ORACLE
        else:
            from ssbot.backends.noise_simple import SIGMA_HERO_U, SIGMA_POS_U
            from ssbot.core.worldstate import Kind
            s = NOISE_K * math.hypot(SIGMA_HERO_U, SIGMA_POS_U[Kind.BOSS])
            margin = (MARGIN_ORACLE[0] + s, MARGIN_ORACLE[1] + s)
            fview = VISION_EQUIVALENT
        self.fc = Forecaster(self.model, fview, margin=margin, templates=load_planner_templates(self.model, margin),
                             comfort=COMFORT)
        self.pb = load_playbook(enemy)
        self.fc.no_hurtbox = self.pb.no_hurtbox
        self.tac = Tactics(self.pb)
        if view == "degraded" and self.pb.hidden_x_vision is not None:
            self.tac.hidden_x = self.pb.hidden_x_vision      # no cues: the stance with the least unreactable risk
        self.planner: Planner | None = None
        self.terrain_tap: TerrainTap | None = None
        self.terrain: Terrain2D | None = None
        self.log_path = (Path(log_dir) / f"decisions_i{instance}.jsonl") if log_dir else None
        self.episode = -1
        self.sc = SupervisedControl(cfg=SupervisorConfig(worst_known_damage=2), support=lambda s: self._support)
        self._support = None

    def attach(self, link) -> None:
        self.terrain_tap = TerrainTap(link)
        self.link = link

    def warmup(self) -> float:
        """Compile every numba path before the first episode (a first call mid-fight compiles for seconds, and the
        oracle's brain-lost watchdog pauses the game after 250 ms without an ACTION): a synthetic tick at h = 2 next to
        an arena gate (knockback hull), inside the support (FORCED_RISK: probabilities), with a Bind wanted, and with
        the hero in hit-stop (the no-control candidates)."""
        from ssbot.combat.boss_model import Anchor
        from ssbot.combat.forecast import Ctx, Root
        from ssbot.combat.tactics import TacticPrefs
        from ssbot.core.worldstate import E, Gate, WorldState
        t0 = time.perf_counter()
        terrain = Terrain2D.from_boxes([(60.0, 0.0, 110.0, 2.0), (67.2, 0.0, 69.2, 14.0), (102.0, 0.0, 104.0, 14.0)])
        planner = Planner(self.params, terrain, PlannerConfig(threads=self.threads))
        fc = self.fc
        roots = fc.tracker.roots
        an = self.model.anchor("BB_CHARGE", "Set L")
        for x, mode in ((76.0, kin.M_NORMAL), (80.0, kin.M_NORMAL), (85.0, kin.M_HURT_FREEZE)):
            fc.tracker.roots = lambda origin: ([Root("Charge Antic", -0.3, -0.3, Ctx(
                family="BB_CHARGE", direction="Set L", anchor=an, phase="P1", raged=False, hp=100.0), current=True)],
                True)
            f = fc.forecast(HORIZON_S, 0.0)
            ws = WorldState()
            ws.hero.pos = E((x, 3.0544))
            ws.res.hp, ws.res.hp_max, ws.res.silk = E(3), E(5), E(9)
            ws.terrain.gates = [Gate("Gate", True, (67.2, 0.0, 69.2, 14.0))]
            prefs = self.tac.decide(ws, f, None, 2)
            prefs.want_bind = True
            ctx = FilterContext.from_world(ws, None, 2, want_bind=True)
            S = kin.initial_state(self.params, x, 2.015 + self.params.foot, mode=mode)
            planner.tick(ws, S, HoldState.idle(1), np.zeros(1, np.int64), f, prefs, ctx)
            f.prob(np.full((3, 5), x), np.full((3, 5), 3.05), np.arange(5) * 0.0167)
            f.t_min(x, 3.05)
        fc.tracker.roots = roots
        fc.reset()
        return time.perf_counter() - t0

    # ---- per episode -----------------------------------------------------------------------------------------

    def reset(self, rng: random.Random, enc) -> None:
        self.episode += 1
        seed = rng.randrange(1 << 30)
        if self.view == "oracle":
            self.backend = OracleBackend(bosses=[self.spec])
            self.k = 0
        else:
            self.backend = DegradedOracleBackend(OracleBackend(bosses=[self.spec]),
                                                 ObservabilityFilter(bosses=[self.spec], tells=TELLS[self.view]))
            self.k = self.backend.reset(seed)
        if self.terrain_tap is not None:
            msg = self.terrain_tap.wait(enc.scene, timeout_s=5.0)
            if msg is not None:
                self.terrain = Terrain2D.from_message(msg, self.params.scene(enc.scene))
        self.terrain = self.terrain or Terrain2D.empty()
        if self.planner is None:
            self.planner = Planner(self.params, self.terrain, PlannerConfig(threads=self.threads))
        self.planner.terrain = self.terrain
        self.planner.reset()
        self.trk = StateTracker(self.params, self.terrain)
        self.fc.reset()
        self.sc.reset()
        self.sent: dict[int, int] = {}
        self.raw: dict[int, dict] = {}
        self.forecasts: deque = deque(maxlen=8)
        self.decision = None
        self.episode_outcome: str | None = None
        self.outcome_reason: str | None = None
        self.pause_owned = False
        self.wake_sent = False
        self.ring: deque = deque(maxlen=LOG_BEFORE)
        self.log_after = 0
        self.counts: Counter = Counter()
        self.tick_ms: list[float] = []
        self.plan_ms: list[float] = []
        self.unpredicted: list[int] = []
        self.hits_taken: list[int] = []
        self.forced_frames: list[int] = []
        self.first_pending_f: int | None = None
        self.planner_last = None
        self.enc = enc

    # ---- per STATE ---------------------------------------------------------------------------------------------

    def _wake(self, ws, s: dict, tap) -> None:
        if self.wake_sent or tap is None or tap.wake_frame is None:
            return
        dt = (s["f"] - tap.wake_frame) * self.params.frame_time
        self.fc.notify_wake(ws.stamp.t_game_s - dt + self.k * self.params.frame_time)   # ws is k frames old
        self.wake_sent = True

    def _start_state(self, ws, raw: dict) -> np.ndarray:
        S = self.trk.state().copy()
        if self.view != "oracle":
            b = (raw.get("hero") or {}).get("box")
            if b:
                dx = ws.hero.pos.v[0] - 0.5 * (b[0] + b[2])
                dy = ws.hero.pos.v[1] - 0.5 * (b[1] + b[3])
                for r in (kin.PX, kin.QX, kin.SX):
                    S[r] += dx
                for r in (kin.PY, kin.QY, kin.SY):
                    S[r] += dy
        return S

    def _unpredicted(self, raw: dict, fo: int) -> int:
        """Hero hits in the WorldState's frame (the delayed one in stage C) outside the support forecast UNPRED_LAG
        frames earlier (box of fo or fo - 1, the recall pairing)."""
        n = 0
        for ev in raw.get("ev") or ():
            if ev.get("k") != "damage":
                continue
            self.hits_taken.append(fo)
            cover = False
            old = next((x for x in self.forecasts if x[0] == fo - UNPRED_LAG), None)
            if old is not None:
                _, fcast, t_o = old
                for fr in (fo, fo - 1):
                    st = self.raw.get(fr)
                    b = ((st or {}).get("hero") or {}).get("box")
                    t = (st or {}).get("_t")
                    if not b or t is None:
                        continue
                    x, y = 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])
                    if fcast.occupied(np.array([[x]]), np.array([[y]]), np.array([t - t_o]))[0, 0]:
                        cover = True
                        break
            if not cover:
                n += 1
                self.unpredicted.append(fo)
        return n

    def act(self, s: dict, tap=None) -> int:
        t0 = time.perf_counter()
        f = s["f"]
        self.raw[f] = s
        for old in [k for k in self.raw if k < f - 12]:
            del self.raw[old]
        ws = self.backend.feed(s)
        if ws is None:                                   # stage C: the delay line is filling
            self.sent[f + 2] = 0
            return 0
        fo = ws.stamp.frame
        raw = self.raw.get(fo, s)
        raw["_t"] = ws.stamp.t_game_s
        self.trk.push(raw)
        self._wake(ws, s, tap)
        self.fc.update(ws)
        fcast = self.fc.forecast(HORIZON_S)
        self.forecasts.append((fo, fcast, ws.stamp.t_game_s))
        self._support = fcast.support_set(ws)
        d = self.decision
        h = d.h if d is not None else None
        prefs = self.tac.decide(ws, fcast, d, h)
        ctx = FilterContext.from_world(ws, d, h, want_bind=prefs.want_bind)
        hold = HoldState.from_act(raw.get("act"))
        prefix = np.array([self.sent.get(fr, 0) for fr in range(fo + 1, f + 2)], np.int64)
        t1 = time.perf_counter()
        res = self.planner.tick(ws, self._start_state(ws, raw), hold, prefix, fcast, prefs, ctx)
        self.planner_last = res
        t2 = time.perf_counter()
        unpred = self._unpredicted(raw, fo)
        r = self.sc.step(s, plan_s=res.S, forced_risk=res.forced_risk, unpredicted_hits=unpred, p_death=res.P)
        self.decision = r.decision
        self.pause_owned = self.sc.pq is not None
        if r.decision.pause_pending and self.first_pending_f is None:
            self.first_pending_f = f
        mask = res.mask if r.mask is None else r.mask
        if r.outcome is not None and r.outcome in TERMINAL and self.episode_outcome is None:
            self.episode_outcome = "QUIT"
            self.outcome_reason = f"{r.outcome}: {'; '.join(r.decision.reasons) or 'supervisor'}"
        self.sent[f + 2] = int(mask)
        for old in [k for k in self.sent if k < f - 12]:
            del self.sent[old]
        self.tick_ms.append((time.perf_counter() - t0) * 1e3)
        self.plan_ms.append((t2 - t1) * 1e3)
        self.counts[prefs.mode] += 1
        self.counts["forced_risk"] += res.forced_risk
        if res.forced_risk:
            self.forced_frames.append(f)
        self.counts[f"tier_{r.decision.tier}"] += 1
        self._log(s, f, fo, ws, fcast, prefs, res, r, unpred)
        return int(mask)

    # ---- decision log ------------------------------------------------------------------------------------------

    def _log(self, s, f, fo, ws, fcast, prefs, res, r, unpred) -> None:
        tr = self.fc.tracker
        rec = {"ep": self.episode, "f": f, "fo": fo, "t": round(ws.stamp.t_game_s, 4),
               "hero": [round(v, 3) for v in ws.hero.pos.v], "hp": ws.res.hp.v, "silk": ws.res.silk.v,
               "boss_state": tr.state, "boss_hp": tr.ctx.hp, "family": tr.ctx.family,
               "anchor": None if tr.ctx.anchor is None else [tr.ctx.anchor.x, tr.ctx.anchor.y, tr.ctx.anchor.mirror],
               "roots": [(x.state, round(x.e_lo, 3), round(x.e_hi, 3), x.ctx.family) for x in fcast.roots],
               "n_place": len(fcast.placements), "known": fcast.known, "mode": prefs.mode,
               "stance": round(prefs.stance_x, 2), "plan": res.name, "S": res.S, "forced": res.forced_risk,
               "P": round(res.P, 3), "J": round(res.J, 2), "V": res.V, "n_safe": res.n_safe, "n_ok": res.n_allowed,
               "alts": res.alternatives, "mask": int(res.mask if r.mask is None else r.mask),
               "sup_mask": r.mask is not None, "tier": r.decision.tier, "h": r.decision.h,
               "pending": r.decision.pause_pending, "triggers": list(r.decision.triggers), "unpred": unpred,
               "ms": round(res.t_ms.get("total", 0.0), 3), "tail": res.tail_ok,
               "path": None if res.path is None else np.round(res.path[::4, :], 3).tolist()}
        self.ring.append(rec)
        hit = any(ev.get("k") in ("damage", "catastrophe", "would_die") for ev in s.get("ev") or ())
        event = hit or res.forced_risk or (r.decision.pause_pending and self.counts["_pend_logged"] == 0)
        if r.decision.pause_pending:
            self.counts["_pend_logged"] = 1
        if self.log_path is None:
            return
        if LOG_ALL:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            self.ring.clear()
            return
        if event:
            with self.log_path.open("a", encoding="utf-8") as fh:
                for x in self.ring:
                    fh.write(json.dumps(x) + "\n")
            self.ring.clear()
            self.log_after = LOG_AFTER
        elif self.log_after > 0:
            self.log_after -= 1
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            self.ring.clear()

    def stats(self) -> dict:
        q = (lambda v, p: round(float(np.percentile(v, p)), 3) if v else None)
        tr = self.fc.tracker
        modes = {k: v for k, v in self.counts.items() if not k.startswith("_")}
        return {"view": self.view, "k": self.k, "modes": modes,
                "tick_ms_p50": q(self.tick_ms, 50), "tick_ms_p99": q(self.tick_ms, 99),
                "plan_ms_p50": q(self.plan_ms, 50), "plan_ms_p99": q(self.plan_ms, 99),
                "unpredicted": self.unpredicted, "hits_taken": self.hits_taken,
                "forced_risk_ticks": len(self.forced_frames), "forced_first": self.forced_frames[:20],
                "first_pending_f": self.first_pending_f, "outcome_reason": self.outcome_reason,
                "alerts": list(self.sc.alerts), "anchor_log": tr.anchor_log[-40:]}
