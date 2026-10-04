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
     its keys replace the planner's while it pauses, and from the tick after the trigger the tactics and the planner
     are not ticked at all (_pause_tick). A FORCED_RISK reaches Q6 with how long the best plan stays clear
     (_forced_clear_f: Q6 only within the design horizon). A pause machine outcome ends the episode as QUIT
     (episode_outcome); the harness lets the policy own the pause (pause_owned). In stage C the supervisor and the
     pause machine read only the delayed view (the WorldState and the vision form of its STATE's pause cues).
  5. unpredicted hits: a hero hit whose box (frame c or c - 1) is outside the support forecast L = 3 frames earlier
     (the stage-A recall pairing; 4, else 2 when a late tick left a gap; none of these: unknown, counted the same)
     counts for the supervisor's Q4.
  6. the known-effect invariant (train/bell_hit_monitor.py): every drop bell the hero tinks must leave the bell's
     danger zone around her no larger than the untouched bell's (violations counted in stats()["bell_hits"]).
The decision log (decisions_i<N>.jsonl in the run directory) keeps the 90 ticks before every hero hit, lethal hit,
FORCED_RISK and supervisor pause, and 10 after, for ssbot.tools.postmortem.
"""
import json
import math
import os
import random
import time
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path

import numpy as np

from ssbot.backends.degraded import DegradedOracleBackend
from ssbot.backends.observability import ObservabilityFilter
from ssbot.backends.oracle_backend import OracleBackend
from ssbot.combat.boss_model import BossModel
from ssbot.combat.forecast import Forecaster, load_box_margin, load_hurtbox, load_planner_templates
from ssbot.combat.hero_damage import HeroDamage
from ssbot.combat.planner import Planner, PlannerConfig
from ssbot.combat.safety_filter import FilterContext
from ssbot.combat.tactics import Tactics, load_playbook
from ssbot.core.bosses import BOSSES
from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT, Ev
from ssbot.ipc.framing import ACTION_EXCLUSIVE, BIT
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.kinematics import HeroParams, HoldState, StateTracker, Terrain2D
from ssbot.safety.pause_quit import TERMINAL
from ssbot.safety.supervisor import SupervisorConfig
from ssbot.train.bell_hit_monitor import BellHitMonitor
from ssbot.train.supervision import SupervisedControl

MARGIN_ORACLE = (0.15, 0.25)          # DESIGN §3.5.3 m = 0.15 u; y + 0.10 u so a jump's lane spread fits one point
COMFORT = (0.25, 0.25)                # preferred extra clearance (planner: S = 0 > comfort > V > J)
NOISE_K = 3.0                         # stage C: + k * sigma of the hero / boss position noise
HORIZON_S = 2.0                       # forecast horizon: the risk map's and the Bind's
UNPRED_LAG = 3
UNPRED_LAGS = (3, 4, 2)   # the forecast a hit is judged against: lag 3, else 4, else 2 (the lags support_recall
#                           validates, the DelayLine's range); none of them kept (a late tick's gap): unknown
CATCH_UP_MAX = 64      # STATEs kept for _catch_up (a tick later than this many frames loses the oldest)
LOG_BEFORE, LOG_AFTER = 90, 10
LOG_ALL = os.environ.get("SSBOT_LOG_ALL") == "1"     # debugging: every tick to the decision log
# Underground cues for the vision view (ObservabilityFilter tells; hypotheses until M3 measures tell_lead_vision in
# shadow mode). DUST_TELL: the emergence dust the person reported (2026-10-02), seen in screenshots of instance 3
# (C:/ssbot/sandbox/m2_tells, ssbot.probes.m2_tells: 10 charges, 12 leaps from both anchors, 9 bursts): none at
# +0.1 s after Emerge Antic C / L or Burst Antic, dust where the boss will come up from +0.3 s, low for a charge, a
# tall column with debris for a leap, told apart for certain at +0.6 s (the emergence antics last 1.0 s, the burst's
# 1.2 s); a narrow dust column from the ceiling above a drop bell from +0.3 s after it arms (Antic; it falls about
# 1.25 s after arming). BURST_TELL: the burst position from the antic's first frame, the first experiment (run
# 20261002_061942).
DUST_TELL = {"Bone Beast": {"Emerge Antic C": [(0.3, "dust"), (0.6, "dust_low")],
                            "Emerge Antic L": [(0.3, "dust"), (0.6, "dust_tall")],
                            "Burst Antic": [(0.3, "dust_burst")]}} | {
    f"BoneBeast DropBell {b}": {"Antic": [(0.3, "bell_dust")]} for b in ("L", "L2", "M", "M2", "R", "R2")}
BURST_TELL = {"Bone Beast": {"Burst Antic": "burst_tell"}}
# each cue's onset drawn in the bracket the screenshots give its nominal delay (forecast.TELL_DELAY; task V review)
TELL_ONSET = {0.3: (0.1, 0.3), 0.6: (0.3, 0.6)}
TELLS = {"degraded": None, "degraded_dust": DUST_TELL, "degraded_tell": BURST_TELL}
# Vision view: the attack fit (combat.attack_fit) re-times the boss's predicted path; off by default since the tracker
# anchors the attack's start at every drawn phase's entry (task V, boss_path_audit --view degraded_dust on live run
# 20261002_171806, 8 fights: the fit changed the charge's box errors by < 0.1 u and put the leap's top 4.4 u off at
# p99, +12 frames, against 0.8 u without it). SSBOT_FUSION=1 turns it back on.
FUSION = os.environ.get("SSBOT_FUSION", "0") == "1"
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


class AttackMonitor:
    """Runtime check of the attack-outcome model (the attack half of I4 "planner", DESIGN 3.7.2): every attack the
    planner predicted to hit, at the press, is resolved after its window against the hit events the view shows (any
    hit on the boss in [start + window, end + 2 frames]). confidence() is the share of predicted hits that landed over
    the last `window` resolved ones, over the share the model is calibrated to (expected), capped at 1; None before
    min_n. The policy scales J's hit credit by it and limits punishes to one hit below `tighten` (YELLOW's rule)."""

    WINDOWS = {1: (0, 6), 2: (2, 8), 3: (0, 16), 4: (17, 20)}

    def __init__(self, window: int = 40, min_n: int = 10, expected: float = 0.85, tighten: float = 0.5):
        self.window, self.min_n, self.expected, self.tighten = window, min_n, expected, tighten
        self.reset()

    def reset(self) -> None:
        self.pending: list[tuple[int, int]] = []      # (window start, window end) absolute frames, predicted hits
        self.hit_frames: deque = deque(maxlen=64)
        self.results: deque = deque(maxlen=self.window)

    def predict(self, fo: int, attacks: list | None, first: tuple | None = None) -> None:
        """attacks: the prediction log (audit runs); otherwise the chosen plan's first attack scored as a hit
        (PlanResult.attack, from the scoring kernel at no extra cost), counted once at its start frame."""
        if attacks is None and first is not None:
            kind, k, _box = first
            if k <= 3:
                attacks = [(kind, k, True, 1.0, k, None, "")]
        for kind, k, hit, _p, _j, _box, _eff in attacks or ():
            if hit:
                w0, w1 = self.WINDOWS[kind]
                self.pending.append((fo + k + w0, fo + k + w1 + 2))

    def observe(self, f: int, hit_frames) -> None:
        self.hit_frames.extend(hit_frames)
        keep = []
        for a, b in self.pending:
            if f <= b + 2:
                keep.append((a, b))
            else:
                self.results.append(any(a <= h <= b for h in self.hit_frames))
        self.pending = keep

    def confidence(self) -> float | None:
        if len(self.results) < self.min_n:
            return None
        return round(min(1.0, (sum(self.results) / len(self.results)) / self.expected), 3)


class PlannerPolicy:
    def __init__(self, view: str = "oracle", threads: int = 8, enemy: str = "BellBeast", log_dir: Path | None = None,
                 instance: int = 0, real_quit_p: float = 0.0):
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
        self.fc.shape_from = self.pb.shape_from          # the emerge predicted with the charge's shape
        self.fc.bell_tells = view == "degraded_dust"
        if fview != ORACLE and FUSION:
            from ssbot.combat.attack_fit import AttackFit
            self.fc.tracker.fit = AttackFit(self.model)   # multi-frame fusion of committed attacks
        if fview != ORACLE and os.environ.get("SSBOT_ATTACK_MODEL", "v2") != "v1":
            self.fc.hurtbox = load_hurtbox()     # vision: the hittable box per phase, not the sprite's (v1: the
            #                                      first attack model, for the audit's before)
        if fview != ORACLE:
            # the pogo gate's certain box: the predicted one eroded by the residuals measured in this view
            # (boss_path_audit --margins); missing: {} (no pogo is ever certain), never the nominal box
            self.fc.box_margin = load_box_margin() or {}
        self.tac = Tactics(self.pb)
        if view == "degraded" and self.pb.hidden_x_vision is not None:
            self.tac.hidden_x = self.pb.hidden_x_vision      # no cues: the stance with the least unreactable risk
        self.planner: Planner | None = None
        self.terrain_tap: TerrainTap | None = None
        self._inbox: deque | None = None        # every STATE of the link (attach), for _catch_up
        self._last_f: int | None = None
        self.terrain: Terrain2D | None = None
        self.log_path = (Path(log_dir) / f"decisions_i{instance}.jsonl") if log_dir else None
        self._log_buf: list[dict] = []
        self.episode = -1
        # stage C: the supervisor and the pause machine read the delayed view too (SupervisedControl vision=True)
        # the hero's per-attack damage bounds (combat.hero_damage) come from the audited crest and tools of the first
        # frame and the playbook's needle level (loadout.needle_level: not in the per-frame export)
        self.sc = SupervisedControl(cfg=SupervisorConfig(worst_known_damage=2), support=lambda s: self._support,
                                    vision=view != "oracle", needle_level=self.pb.needle_level)
        self.real_quit_p = real_quit_p
        self.atk_mon = AttackMonitor()
        self._pq_emulated = self.sc.pq_cfg
        self.real_quit = False
        self._support = None

    def attach(self, link) -> None:
        self.terrain_tap = TerrainTap(link)
        self.link = link
        import threading
        self._inbox_lock = threading.Lock()
        self._inbox: deque = deque(maxlen=CATCH_UP_MAX)
        link.subscribe_state(self._on_state)

    def _on_state(self, s: dict) -> None:
        with self._inbox_lock:          # the reader thread: every STATE, in order
            self._inbox.append(s)

    def _catch_up(self, f: int, tap) -> None:
        """The STATEs between the last one acted on and f (the episode loop hands the policy only the newest one, so a
        late tick skips frames: 2.5 a fight in degraded_dust run 20261002_224934) go through the perception path too:
        the backend (filter, noise, delay line: one push per frame), the hero's state tracker and the forecaster's
        trackers, without planning. Their events were lost before: a hit dealt on a skipped frame was never counted
        (that run's i1 ep8: the view's boss HP stayed 80 after an up-slash took it to 75, and the rage rule did not
        fire); a vision pipeline processes every captured frame whatever the planner's latency."""
        last, self._last_f = self._last_f, f
        if self._inbox is None or last is None or f <= last + 1:
            return
        with self._inbox_lock:
            pending = [x for x in self._inbox if last < x.get("f", -1) < f]
        for sk in sorted(pending, key=lambda x: x["f"]):
            self.raw[sk["f"]] = sk
            ws = self.backend.feed(sk)
            if ws is None:
                continue
            raw = self.raw.get(ws.stamp.frame, sk)
            raw["_t"] = ws.stamp.t_game_s
            self.trk.push(raw)
            self._wake(ws, sk, tap)
            self.fc.update(ws)
            self.counts["caught_up"] += 1
            self._unpred_backlog += self._unpredicted(raw, ws.stamp.frame)
            self._mon_raws.append(sk)

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
        # the arena as a TERRAIN message (floor, walls, an arena gate the scene overrides enable), built the way a
        # live room's is (Terrain2D.from_message: the planner's real arrays), not from boxes
        box = lambda x0, y0, x1, y1: {"k": "box", "v": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "r": 0.0}  # noqa
        msg = {"solids": [{"go": "Floor", "on": True, "shapes": [box(60.0, 0.0, 110.0, 2.0)]},
                          {"go": "Wall L", "on": True, "shapes": [box(64.0, 0.0, 66.0, 20.0)]},
                          {"go": "Wall R", "on": True, "shapes": [box(105.0, 0.0, 107.0, 20.0)]},
                          {"go": "Gate", "on": False, "shapes": [box(67.2, 0.0, 69.2, 14.0)]},
                          {"go": "Gate 2", "on": False, "shapes": [box(102.0, 0.0, 104.0, 14.0)]}]}
        terrain = Terrain2D.from_message(msg, {"enable": ["Gate", "Gate 2"]})
        planner = Planner(self.params, terrain, PlannerConfig(threads=self.threads))
        if self.view != "oracle":
            # the vision view's filter kernel runs from the first STATE of a fight
            from ssbot.backends.observability import clip_fractions
            clip_fractions(np.zeros((5, 2)), np.array([1, 5], np.int64), np.zeros(1, np.int64), 1,
                           np.array([0.0, 0.0, 1.0, 1.0]))
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
        planner.warm_kernels()
        fc.tracker.roots = roots
        fc.reset()
        return time.perf_counter() - t0

    # ---- per episode -----------------------------------------------------------------------------------------

    def reset(self, rng: random.Random, enc) -> None:
        self.flush_log()
        self.episode += 1
        seed = rng.randrange(1 << 30)
        if self.view == "oracle":
            self.backend = OracleBackend(bosses=[self.spec])
            self.k = 0
        else:
            self.backend = DegradedOracleBackend(OracleBackend(bosses=[self.spec]),
                                                 ObservabilityFilter(bosses=[self.spec], tells=TELLS[self.view],
                                                                     tell_onset=TELL_ONSET))
            self.k = self.backend.reset(seed)
        if self.terrain_tap is not None:
            msg = self.terrain_tap.wait(enc.scene, timeout_s=5.0)
            if msg is not None:
                self.terrain = Terrain2D.from_message(msg, self.params.scene(enc.scene))
        self.terrain = self.terrain or Terrain2D.empty()
        if self.planner is None:
            self.planner = Planner(self.params, self.terrain, PlannerConfig(
                threads=self.threads, attack_model=os.environ.get("SSBOT_ATTACK_MODEL", "v2"),
                predict_log=os.environ.get("SSBOT_PREDICT_LOG") == "1"))
        self.planner.terrain = self.terrain
        self.planner.reset()
        self.trk = StateTracker(self.params, self.terrain)
        self.fc.reset()
        self.atk_mon.reset()
        self._fam_state = None
        # real quits (--real-quit p): this episode's confirmed pause runs the whole quit sequence to the main menu
        self.real_quit = self.real_quit_p > 0 and rng.random() < self.real_quit_p
        self.sc.pq_cfg = replace(self._pq_emulated, emulate_quit=not self.real_quit)
        self.rq: dict = {"armed": self.real_quit, "submits": [], "menus": []}
        self.sc.reset()
        self.sent: dict[int, int] = {}
        self.raw: dict[int, dict] = {}
        self.forecasts: deque = deque(maxlen=8)
        self.decision = None
        self.episode_outcome: str | None = None
        self.outcome_reason: str | None = None
        self.pause_owned = False
        self.action_flags = 0                  # ACTION flags for this tick's mask (episode._act): EXCLUSIVE while the
        #                                        pause machine owns the keys (no planner key reaches the pause menu)
        self.wake_sent = False
        self.first_pending_reasons: list[str] = []
        self.ring: deque = deque(maxlen=LOG_BEFORE)
        self.log_after = 0
        self.counts: Counter = Counter()
        self.tick_ms: list[float] = []
        self.plan_ms: list[float] = []
        self._last_f: int | None = None          # the last STATE acted on (_catch_up)
        self._unpred_backlog = 0                 # unpredicted hits found on caught-up frames, for the next tick
        self.bell_mon = BellHitMonitor()
        self._mon_raws: list[dict] = []
        self.unpredicted: list[int] = []
        self.unpredicted_unknown: list[int] = []     # hits with no forecast at the validated lags (counted for Q4)
        self.hits_taken: list[int] = []
        self.forced_frames: list[int] = []
        self.first_pending_f: int | None = None
        self.planner_last = None
        self.last_clear_f: int | None = None
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
        # oracle view: a hit the hero took after the WorldState's frame starts her i-frames, which block enemy damage:
        # without them every plan of the first ticks after a hit met the support, and Q6 ended the attempt (stage C
        # run 20261002_102538: the 4 Q6 quits checked were FORCED_RISK on the hit frame itself with the start state's
        # INV_T 0, the hero invulnerable). Stage C: the hero's hit is seen as late as the rest of the view (the hit
        # frame's screen and HUD, k frames on), so no hit newer than the WorldState counts (task V review, 2026-10-03)
        fo = int(raw.get("f", 0)) if raw else 0
        hit_f = [] if self.view != "oracle" else \
            [f for f in sorted(self.raw) if f > fo for ev in (self.raw[f].get("ev") or ()) if ev.get("k") == "damage"]
        if hit_f:
            Sv = S.reshape(kin.K, -1)
            Sv[kin.INV_T] = np.maximum(Sv[kin.INV_T], self.params.invul_time + (hit_f[-1] - fo) * self.params.frame_time)
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
        frames earlier (box of fo or fo - 1, the recall pairing). A late tick leaves gaps in the forecasts kept: then
        the one 4, else 2 frames earlier (UNPRED_LAGS, the lags the held-out recall validates). With none of those the
        hit is unpredicted_unknown, which the supervisor counts like an unpredicted one (Q4); both are reported
        (task V review, 2026-10-03: a fallback to forecasts up to 9 frames old, outside the validated lags, had counted
        degraded_dust 20261003_022259 i0 ep9 as predicted)."""
        n = 0
        by_f = {x[0]: x for x in self.forecasts}
        for ev in raw.get("ev") or ():
            if ev.get("k") != "damage":
                continue
            self.hits_taken.append(fo)
            cover = False
            old = next((by_f[fo - lag] for lag in UNPRED_LAGS if fo - lag in by_f), None)
            if old is None:
                n += 1
                self.unpredicted_unknown.append(fo)
                continue
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

    def _forced_clear_f(self, res, fcast, S0: np.ndarray, P: int) -> int | None:
        """At a FORCED_RISK tick: frames after the decision frame that a plan stays out of the support, i-frames
        counted (the supervisor's forced_clear_s: Q6 only within DESIGN §3.5.4's H = 0.8 s). The planner's exact
        value when it exports one (PlanResult.t_clear: the latest first contact over the allowed, non-Hz candidates);
        else a lower bound from the chosen plan's hull, checked the planner's own way (Planner._contacts):
        - i-frames skipped only while every source is i-frame blocked, and only for frames certainly inside them
          (the start state's INV_T run down at the longest frame time; the planner skips per lane, so this skips less);
        - the hull is exact only up to the plan's first attack, cast or Bind press (the planner re-rolls hit effects
          and locks from there), so the bound stops at that press;
        - no hull (no allowed plan): None, i.e. unknown, which the supervisor takes as 0.
        Why: through a committed charge the planner rolls out to the charge's end plus 0.3 s (playbook long_horizon,
        up to 2 s), and FORCED_RISK there was an open-loop contact near that end. Replayed (ssbot.tools.quit_timeline
        --replay), the Charge Emerge triggers of the gate / live QUITs (20261002_123347 ... 152649) had the best plan
        clear for 120 of 120 frames, its first contact on the last one (Charge End's support where the jump lands); at
        h >= 3, 2266 FORCED_RISK streaks began in Charge Emerge and 13 (0.6 %) were followed by a hit within 3 s."""
        t = getattr(res, "t_clear", None)
        if t is not None:
            return max(0, int(t))
        if res.hull is None or not len(res.cmd):
            return None
        hull = np.asarray(res.hull, np.float64)[None]
        T1 = hull.shape[1]
        p = self.params
        tk = np.arange(T1, dtype=np.float64) * p.frame_time
        skip = np.zeros((1, T1), bool)
        if not any(fm.hazard for fm in fcast.fc.model.families.values()):
            inv = float(np.asarray(S0).reshape(kin.K, -1)[kin.INV_T, 0])
            skip[0] = np.arange(T1) * p.frame_time_max < inv
        occ = self.planner._contacts(fcast, hull, tk, skip)
        if occ is None:
            return None
        hit = np.flatnonzero(occ[0])
        k = int(hit[0]) if len(hit) else T1 - 1
        press = np.flatnonzero((np.asarray(res.cmd) & (kin.B_ATTACK | kin.B_QUICKCAST | kin.B_BIND)) != 0)
        if len(press):
            k = min(k, P + int(press[0]))
        return max(0, k - P)

    def act(self, s: dict, tap=None) -> int:
        t0 = time.perf_counter()
        f = s["f"]
        if self.real_quit_active:
            return self._real_quit_step(s, f)
        self._catch_up(f, tap)
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
        self._mon_raws.append(s)
        if self.sc.pq is None:
            self.bell_mon.on_tick(fcast, fo, ws.stamp.t_game_s, self._mon_raws)
        self._mon_raws = []
        if self.sc.pq is not None:
            return self._pause_tick(s, f, fo, ws, raw, t0)
        d = self.decision
        # this tick's h (SupervisedControl.h_now: the step below decides on the same inputs after the planner), not the
        # decision of the tick before: on the tick a hit or frost takes h from 2 to 1 that one still said h 2 and heal
        # first, and the tactics could want a Bind at h 1 (fixer review 2026-10-03)
        h, _ = self.sc.h_now(s, obs=raw, ws=ws)
        prefs = self.tac.decide(ws, fcast, d, h)
        self.atk_mon.observe(fo, [ev.frame for ev in ws.events if ev.kind == Ev.HIT_DEALT])
        conf = self.atk_mon.confidence()
        if conf is not None:
            # the attack model drifting: its hit credit counts for less, and below `tighten` punishes take one hit
            prefs.weights = dict(prefs.weights, hit=prefs.weights.get("hit", 10.0) * max(0.3, conf))
            if conf < self.atk_mon.tighten:
                prefs.max_hits = 1 if prefs.max_hits is None else min(prefs.max_hits, 1)
        if self.sc.damage is None:
            # the loadout before the supervisor's first step reads it: the planner's killing-blow rule needs it now
            self.sc.damage = HeroDamage.from_loadout(ws.res.crest.v if ws.res.crest.conf > 0 else None,
                                                     self.pb.needle_level, ws.res.equipped)
        ctx = FilterContext.from_world(ws, d, h, want_bind=prefs.want_bind, damage=self.sc.damage)
        ctx.silk_reserve_full_hp = self.pb.bind_reserve_at_full_hp
        hold = HoldState.from_act(raw.get("act"))
        prefix = np.array([self.sent.get(fr, 0) for fr in range(fo + 1, f + 2)], np.int64)
        t1 = time.perf_counter()
        S0 = self._start_state(ws, raw)
        res = self.planner.tick(ws, S0, hold, prefix, fcast, prefs, ctx)
        self.planner_last = res
        self.atk_mon.predict(fo, res.attacks, res.attack)
        t2 = time.perf_counter()
        unpred = self._unpredicted(raw, fo) + self._unpred_backlog
        self._unpred_backlog = 0
        clear = self._forced_clear_f(res, fcast, S0, len(prefix)) if res.forced_risk else None
        self.last_clear_f = clear
        r = self.sc.step(s, obs=raw, ws=ws, inflight=self._inflight(s, f), plan_s=res.S, forced_risk=res.forced_risk,
                         unpredicted_hits=unpred, p_death=res.P,
                         forced_clear_s=None if clear is None else clear * self.params.frame_time)
        self.decision = r.decision
        self.pause_owned = self.sc.pq is not None
        self.action_flags = ACTION_EXCLUSIVE if self.pause_owned else 0
        if r.decision.pause_pending and self.first_pending_f is None:
            self.first_pending_f = f
            self.first_pending_reasons = list(r.decision.reasons)     # what started the pause (the end's reasons
            #                                                           include what the quit itself caused, e.g. Q5)
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

    def _inflight(self, s: dict, f: int) -> list[int]:
        """The masks sent but not applied yet before f + 2, the frame this tick's mask is for: from the frame after
        the last ACTION the oracle applied (STATE act.target; an ACTION that missed its frame is still pending) to
        f + 1 (the menu key guard replays the key path through them)."""
        tgt = (s.get("act") or {}).get("target")
        f0 = f + 1 if not isinstance(tgt, int) or tgt < f - 4 else min(tgt + 1, f + 1)
        return [self.sent.get(fr, 0) for fr in range(f0, f + 2) if fr in self.sent]

    def _pause_tick(self, s: dict, f: int, fo: int, ws, raw: dict, t0: float) -> int:
        """The pause machine owns the keys (PAUSE_PENDING onwards; DESIGN §3.7.5): its keys replace the planner's
        whole mask, so the tactics and the planner are not ticked (3-30 ms a tick in the live runs, all of it
        discarded), and the trackers, the forecast and the supervisor still run (the support and h stay current for a
        resume). Every tick's keys go out as soon as the supervisor has them, so the loop's 34 ms presses keep their
        frames and its first press after the pause gate opens is not held up by planning. A resumed attempt (UNPAUSED)
        restarts the planner without the plan carried from before the pause (the keys sent meanwhile were the
        machine's)."""
        unpred = self._unpredicted(raw, fo) + self._unpred_backlog
        self._unpred_backlog = 0
        r = self.sc.step(s, obs=raw, ws=ws, inflight=self._inflight(s, f), plan_s=None, forced_risk=False,
                         unpredicted_hits=unpred)
        self.decision = r.decision
        self.pause_owned = self.sc.pq is not None
        self.action_flags = ACTION_EXCLUSIVE if self.pause_owned else 0
        mask = 0 if r.mask is None else int(r.mask)     # never the planner's: its last plan is from before the pause
        if r.outcome is not None and r.outcome in TERMINAL and self.episode_outcome is None:
            self.episode_outcome = "QUIT"
            self.outcome_reason = f"{r.outcome}: {'; '.join(r.decision.reasons) or 'supervisor'}"
        if self.sc.pq is None:
            self.planner.reset()
        self.sent[f + 2] = mask
        for old in [k for k in self.sent if k < f - 12]:
            del self.sent[old]
        self.tick_ms.append((time.perf_counter() - t0) * 1e3)
        self.counts["PAUSE"] += 1
        self.counts[f"tier_{r.decision.tier}"] += 1
        pq = self.sc.pq
        rec = {"ep": self.episode, "f": f, "fo": fo, "t": round(ws.stamp.t_game_s, 4),
               "hero": [round(v, 3) for v in ws.hero.pos.v], "hp": ws.res.hp.v, "silk": ws.res.silk.v,
               "boss_state": self.fc.tracker.state, "mode": "PAUSE", "plan": "PAUSE", "S": None, "forced": False,
               "clear": None, "mask": mask, "sup_mask": True, "tier": r.decision.tier, "h": r.decision.h,
               "pending": r.decision.pause_pending, "triggers": list(r.decision.triggers), "unpred": unpred,
               "pq": None if pq is None else pq.state, "outcome": r.outcome}
        hit = any(ev.get("k") in ("damage", "catastrophe", "would_die") for ev in s.get("ev") or ())
        self._emit(rec, hit)
        return mask

    # ---- decision log ------------------------------------------------------------------------------------------

    def _emit(self, rec: dict, event: bool) -> None:
        """Keep the 90 ticks before an event and LOG_AFTER after it. While the pause loop presses, rows are only
        buffered: the trigger tick's 90-row write (about 150 KB of JSON) used to run before that tick's keys went out;
        they are written once the loop has stopped (the game paused) or the episode ends (stats)."""
        self.ring.append(rec)
        if self.log_path is None:
            return
        if LOG_ALL:
            self._log_buf.extend(self.ring)
            self.ring.clear()
        elif event:
            self._log_buf.extend(self.ring)
            self.ring.clear()
            self.log_after = LOG_AFTER
        elif self.log_after > 0:
            self.log_after -= 1
            self._log_buf.append(rec)
            self.ring.clear()
        pq = self.sc.pq
        if self._log_buf and not (pq is not None and pq.pressing):
            self.flush_log()

    def flush_log(self) -> None:
        if self._log_buf and self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8") as fh:
                for x in self._log_buf:
                    fh.write(json.dumps(x) + "\n")
        self._log_buf.clear()

    def _log(self, s, f, fo, ws, fcast, prefs, res, r, unpred) -> None:
        tr = self.fc.tracker
        rec = {"ep": self.episode, "f": f, "fo": fo, "t": round(ws.stamp.t_game_s, 4),
               "hero": [round(v, 3) for v in ws.hero.pos.v], "hp": ws.res.hp.v, "silk": ws.res.silk.v,
               "boss_state": tr.state, "boss_hp": tr.ctx.hp, "family": tr.ctx.family,
               "anchor": None if tr.ctx.anchor is None else [tr.ctx.anchor.x, tr.ctx.anchor.y, tr.ctx.anchor.mirror],
               "roots": [(x.state, round(x.e_lo, 3), round(x.e_hi, 3), x.ctx.family) for x in fcast.roots],
               "n_place": len(fcast.placements), "known": fcast.known, "mode": prefs.mode,
               "stance": round(prefs.stance_x, 2), "plan": res.name, "S": res.S, "forced": res.forced_risk,
               "clear": self.last_clear_f,
               "P": round(res.P, 3), "J": round(res.J, 2), "V": res.V, "n_safe": res.n_safe, "n_ok": res.n_allowed,
               "alts": res.alternatives, "mask": int(res.mask if r.mask is None else r.mask),
               "sup_mask": r.mask is not None, "tier": r.decision.tier, "h": r.decision.h,
               "pending": r.decision.pause_pending, "triggers": list(r.decision.triggers), "unpred": unpred,
               "ms": round(res.t_ms.get("total", 0.0), 3), "tail": res.tail_ok, "attack": res.attack,
               "attacks": res.attacks, "atk_conf": self.atk_mon.confidence(), "fam_p": self._fam_p(fcast),
               "best_up": res.best_up, "hits": res.hits, "pogo": dict(self.planner.pogo_log),
               "kill": list(self.planner.last_kill), "kill_rule": r.decision.kill_rule,
               "kill_prims": sorted(p.name for p in r.decision.kill_prims), "stall": round(r.decision.stall_s, 2),
               "path": None if res.path is None else np.round(res.path[::4, :], 3).tolist()}
        hit = any(ev.get("k") in ("damage", "catastrophe", "would_die") for ev in s.get("ev") or ())
        event = hit or res.forced_risk or (r.decision.pause_pending and self.counts["_pend_logged"] == 0)
        if r.decision.pause_pending:
            self.counts["_pend_logged"] = 1
        self._emit(rec, event)

    UNDECIDED = frozenset(("Submerged", "Submerged Init", "Burst Recovery", "Rage Submerge", "hidden"))

    def _fam_p(self, fcast) -> dict | None:
        """The threat half of the audit: at the first tick of an underground phase, the walk's probability of each
        family for the next attack (sum of p over its start nodes), for predict_audit's calibration."""
        st = self.fc.tracker.state
        first = st in self.UNDECIDED and st != self._fam_state
        self._fam_state = st
        if not first:
            return None
        m = self.model
        out: dict[str, float] = {}
        for n in fcast.nodes:
            fam = m.attack_starts.get(n.state)
            if fam is not None:
                out[fam] = out.get(fam, 0.0) + n.p
        tot = sum(out.values())
        return {k: round(v / tot, 3) for k, v in out.items()} if tot > 0 else None

    def _real_quit_step(self, s: dict, f: int) -> int:
        """A confirmed pause in a real-quit episode: only the pause machine acts (menus, the exit prompt, the
        quit to the main menu); the oracle's own menu export records what each Submit landed on."""
        obs = None
        if self.view != "oracle":
            # the backend is not fed through the menus: the cues come from the STATE k frames back, as the view's
            self.raw[f] = s
            for old in [k for k in self.raw if k < f - 12]:
                del self.raw[old]
            old = [fr for fr in self.raw if fr <= f - self.k]
            obs = self.raw[max(old)] if old else s
        r = self.sc.step(s, obs=obs, inflight=self._inflight(s, f))
        mask = int(r.mask or 0)
        self.action_flags = ACTION_EXCLUSIVE
        menu = s.get("menu") or {}
        g = s.get("game") or {}
        key = (g.get("menu"), menu.get("sel"))
        if not self.rq["menus"] or self.rq["menus"][-1][1:] != list(key):
            self.rq["menus"].append([f, *key])
        if mask & (1 << BIT["enter"]):
            sub = [x for x in self.sc.pq.log if x[1] == "submit"]
            want = sub[-1][2].split(":", 1)[1] if sub else None
            if not self.rq["submits"] or self.rq["submits"][-1][0] < f - 6:
                self.rq["submits"].append([f, menu.get("sel"), want])
        if r.outcome is not None and r.outcome in TERMINAL and self.episode_outcome is None:
            self.episode_outcome = "QUIT"
            self.outcome_reason = f"{r.outcome}: {'; '.join(r.decision.reasons) or 'supervisor'}"
        self.sent[f + 2] = mask
        return mask

    @property
    def real_quit_active(self) -> bool:
        """A real quit is under way (the pause confirmed in a real-quit episode)."""
        return bool(self.real_quit and self.sc.pq is not None and self.sc.pq.t_confirm is not None)

    def real_quit_stats(self) -> dict | None:
        """Pause latency, menu steps and the checks of a real quit (None: not a real-quit episode)."""
        if not self.rq.get("armed"):
            return None
        pq = self.sc.pq
        out = dict(self.rq)
        if pq is not None:
            out.update(outcome=pq.outcome, presses=pq.presses, false_cues=pq.false_cues, nav_flips=pq.nav_flips,
                       unexpected_unpauses=pq.unexpected_unpauses, key_waits=pq.key_waits,
                       key_waits_expired=pq.key_waits_expired,
                       pause_latency_s=None if pq.t_confirm is None or pq.t_start is None
                       else round(pq.t_confirm - pq.t_start, 3),
                       steps=[[round(t - (pq.t_start or 0.0), 3), k, d] for t, k, d in pq.log
                              if k in ("cue", "confirmed", "nav", "nav_no_effect", "submit", "submit_lost", "quitting",
                                       "done", "fail", "unexpected_unpause", "refused", "greyed")])
        out["wrong_submits"] = sum(1 for _, got, want in self.rq["submits"] if want is not None and got != want)
        out["main_menu"] = bool(pq is not None and pq.outcome == "QUIT")
        return out

    def stats(self) -> dict:
        self.flush_log()                        # the episode is over: rows held back while the loop pressed
        q = (lambda v, p: round(float(np.percentile(v, p)), 3) if v else None)
        tr = self.fc.tracker
        modes = {k: v for k, v in self.counts.items() if not k.startswith("_")}
        return {"view": self.view, "k": self.k, "modes": modes,
                "tick_ms_p50": q(self.tick_ms, 50), "tick_ms_p99": q(self.tick_ms, 99),
                "plan_ms_p50": q(self.plan_ms, 50), "plan_ms_p99": q(self.plan_ms, 99),
                "unpredicted": self.unpredicted, "unpredicted_unknown": self.unpredicted_unknown,
                "hits_taken": self.hits_taken,
                "forced_risk_ticks": len(self.forced_frames), "forced_first": self.forced_frames[:20],
                "first_pending_f": self.first_pending_f, "first_pending_reasons": self.first_pending_reasons,
                "outcome_reason": self.outcome_reason,
                "alerts": list(self.sc.alerts), "anchor_log": tr.anchor_log[-40:],
                "bell_hits": self.bell_mon.stats(),
                "real_quit": self.real_quit_stats()}
