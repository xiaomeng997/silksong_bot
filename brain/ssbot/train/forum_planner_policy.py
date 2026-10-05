"""ForumPlannerPolicy: the Forum's live combat loop (forum_planner_plan §5 R4, the A0 baseline): the R3 fast layer
(ForumPlanner over the MultiForecast) with the LOCAL tactics (combat.tactics.forum_local) and the Forum supervisor.

    pol = ForumPlannerPolicy(view="oracle", threads=4, log_dir=run_dir, instance=i, real_quit_p=0.2)
    (combat_run --encounter Forum_A --policy planner makes it for a gauntlet encounter)

The Bell Beast's PlannerPolicy is not touched: this subclass reuses its perception helpers (_catch_up, _start_state,
_unpredicted, _forced_clear_f, _inflight, the real quit, the key plan log, the decision log ring) and has its own
tick. Per STATE:
  1. OracleBackend (no boss spec) -> WorldState; StateTracker (the Forum loadout's kinematics, hero_reaper_forum.json,
     with_weighted() when ws.res.equipped shows the Weighted Anklet); MultiForecaster.update (one tracker per enemy
     instance on the shared production tables, the WaveTracker inside it) -> MultiForecast(2 s).
  2. ForumTactics -> GoalPrefs (mode, stance, hit weight per enemy iid, Bind wish).
  3. FilterContext.kill_hp = forum_kill_hp (U: the blow that may end the battle, I3 only); the supervisor's kill_prims
     from forum_yellow_kill_hp (YELLOW's per-enemy kill freeze, kill_freeze.json) against the hero's damage bounds.
  4. ForumPlanner.tick; SupervisedControl.step with forum_supervisor_config (worst_known_damage 2, Q4 per enemy
     instance: unpredicted_sources = the HIT_TAKEN source iid of each unpredicted hit; post-hit window 1.3 s with the
     anklet); the pause machine as for the Bell Beast.
  5. Cogfly (playbook forum.cogfly, the plan's default arm: 2 in wave index 6, 2 in the finale): Up + QuickCast for two
     frames, only on the ground, standing, the chosen plan safe (S = 0, no FORCED_RISK, no supervisor keys) and the
     support's t_min at the hero's spot >= min_clear_s. The throw is not in the kinematic model: the planner's prefix
     sees those frames without the throw keys (it plans from the real state the next ticks read).
Accounting (stats(), per episode, for ssbot.tools.forum_a0_report; room.battles is read only here, as test truth, never
by a decision): the WaveTracker against room.battles on every ticked frame, hits (source type / iid, view and true
wave, predicted or not), ticks and FORCED_RISK per true wave, tick times, the envelope audit's per-episode delta,
Cogfly throws, Binds. Decision log (decisions_i<N>.jsonl): 90 ticks before each hero hit, supervisor pause and the
first tick of a FORCED_RISK streak, 10 after.
"""
import math
import random
import time
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path

import numpy as np

from ssbot.backends.oracle_backend import OracleBackend
from ssbot.combat.enemy_tables import EnemyTables
from ssbot.combat.forum_planner import (ForumConfig, ForumPlanner, forum_kill_hp, forum_yellow_kill_hp,
                                        kill_freeze_s)
from ssbot.combat.hero_damage import HeroDamage
from ssbot.combat.multi_forecast import MultiForecaster
from ssbot.combat.planner import PlannerConfig
from ssbot.combat.safety_filter import FilterContext, KillKnowledge
from ssbot.combat.tactics.forum_local import ForumTactics, load_forum_playbook
from ssbot.core.forum import FLOOR_Y
from ssbot.core.worldstate import Ev
from ssbot.ipc.framing import ACTION_EXCLUSIVE
from ssbot.knowledge import hitbox_tables as hb
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.kinematics import HeroParams, HoldState, StateTracker, Terrain2D
from ssbot.safety.pause_quit import TERMINAL
from ssbot.safety.supervisor import forum_supervisor_config
from ssbot.train.keyplan import KeyPlanLog
from ssbot.train.planner_policy import HORIZON_S, LOG_BEFORE, UNPRED_LAGS, PlannerPolicy

REPO = Path(__file__).resolve().parents[3]
FORUM_PARAMS = REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_reaper_forum.json"
END_SLOW_S = 1.85          # EnemyBattleEndSlow in real time (forum.md §3): the final blow's unpausable window
ANKLET = "Weighted Anklet"
COG = kin.B_UP | kin.B_QUICKCAST
COG_FRAMES = 2
COG_MAX = 4                # fo_A's Cogwork Flier uses
FORCED_STREAK_GAP = 30     # a FORCED_RISK tick after this many ticks without one starts a streak (logged as an event)
BATTLE = "Battle Scene"
HOOK_LOOKBACK_F = 70       # a multi-hit chain's hook -> its Final Hit: 0.35 - 1.0 s (forum.md §9.2; tools.multi_recall)
HOOK_FSMS = ("Control", "Attack")
KEEP_F = 90                # forecasts, hero boxes and FSM entries kept for judging a Final Hit at its hook


def true_wave(raw: dict) -> tuple[int | None, bool]:
    """(BattleScene.currentWave from STATE room.battles while the battle runs, completed): test truth only."""
    battles = (raw.get("room") or {}).get("battles") or ()
    if not battles:
        return None, False
    b = next((x for x in battles if x.get("name") == BATTLE), battles[0])
    if b.get("completed"):
        return None, True
    return (int(b["wave"]) if b.get("started") and b.get("wave") is not None else None), False


class ForumPlannerPolicy(PlannerPolicy):
    act_after_clear = True

    def __init__(self, view: str = "oracle", threads: int = 4, log_dir: Path | None = None, instance: int = 0,
                 real_quit_p: float = 0.0, playbook: Path | str | None = None, tables: EnemyTables | None = None):
        import cv2
        import numba
        numba.set_num_threads(threads)
        cv2.setNumThreads(2)
        if view != "oracle":
            raise ValueError("ForumPlannerPolicy: the oracle view only (the Forum's vision view is M3)")
        self.view, self.threads, self.instance = view, threads, instance
        self.params0 = HeroParams.load(FORUM_PARAMS)
        self.params = self.params0
        self.pb, self.rules = load_forum_playbook(playbook)
        self.floor_hero_y = FLOOR_Y + hb.HERO_HALF_U[1]
        self.tac = ForumTactics(self.pb, self.rules, self.floor_hero_y)
        self.fc = MultiForecaster(tables if tables is not None else EnemyTables.production())
        self.freeze = kill_freeze_s()
        self.kill_know = KillKnowledge.load()
        self.kill_window_s = END_SLOW_S
        from ssbot.train.supervision import SupervisedControl
        self.sc = SupervisedControl(cfg=forum_supervisor_config(), support=lambda s: self._support, vision=False,
                                    needle_level=self.pb.needle_level, kill_know=self.kill_know)
        self._pq_emulated = self.sc.pq_cfg
        self.real_quit_p = real_quit_p
        self.real_quit = False
        self.planner: ForumPlanner | None = None
        self.terrain_tap = None
        self.terrain_msg: dict | None = None      # offline replay: the recording's TERRAIN message
        self._inbox = None
        self._last_f = None
        self.terrain: Terrain2D | None = None
        self.log_path = (Path(log_dir) / f"decisions_i{instance}.jsonl") if log_dir else None
        self.keys_path = (Path(log_dir) / f"keys_i{instance}.jsonl") if log_dir else None
        self.keylog = KeyPlanLog()
        self._keys_done = True
        self._log_buf: list[dict] = []
        self.episode = -1
        self._support = None
        self.k = 0

    # ---- warm-up ----

    def warmup(self) -> float:
        """The tables' lazy parts (MultiForecaster.warm: family walks, pyramids, box tables) and the fast layer's numba
        paths on an empty forecast (ground and hit-stop start states, a Bind wanted, a kill target in reach)."""
        from ssbot.core.worldstate import E, WorldState
        t0 = time.perf_counter()
        self.fc.warm()
        planner = ForumPlanner(self.params, Terrain2D.empty(), PlannerConfig(T=36, threads=self.threads,
                                                                             variants="bounds_lo"), ForumConfig())
        fcast = self.fc.forecast(HORIZON_S)
        for x, mode in ((30.0, kin.M_NORMAL), (33.0, kin.M_NORMAL), (36.0, kin.M_HURT_FREEZE)):
            ws = WorldState()
            ws.hero.pos = E((x, self.floor_hero_y))
            ws.res.hp, ws.res.hp_max, ws.res.silk = E(5), E(7), E(9)
            prefs = self.tac.decide(ws, fcast, None, 3)
            prefs.want_bind = True
            ctx = FilterContext.from_world(ws, None, 3, want_bind=True, kill_hp=5.0, kill_window_s=END_SLOW_S,
                                           damage=HeroDamage.from_loadout("Reaper", 1, ()))
            ctx.support_known = True
            S = kin.initial_state(self.params, x, FLOOR_Y + self.params.foot, mode=mode)
            planner.tick(ws, S, HoldState.idle(1), np.zeros(1, np.int64), fcast, prefs, ctx)
        planner.warm_kernels()
        self.fc.reset()
        return time.perf_counter() - t0

    # ---- per episode ----

    def reset(self, rng: random.Random, enc) -> None:
        self.flush_log()
        self.flush_keys()
        self.episode += 1
        self.keylog.reset(self.episode)
        self._keys_done = False
        rng.randrange(1 << 30)
        self.backend = OracleBackend()
        self.k = 0
        msg = None
        if self.terrain_tap is not None:
            msg = self.terrain_tap.wait(enc.scene, timeout_s=5.0)
        msg = msg or self.terrain_msg
        if msg is not None:
            self.terrain = Terrain2D.from_message(msg, self.params0.scene(enc.scene))
        self.terrain = self.terrain or Terrain2D.empty()
        self.params = self.params0
        if self.planner is None:
            self.planner = ForumPlanner(self.params, self.terrain, PlannerConfig(T=36, threads=self.threads,
                                                                                 variants="bounds_lo"), ForumConfig())
        self.planner.params = self.params
        self.planner.terrain = self.terrain
        self.planner.reset()
        self._audit0 = self.planner.audit.as_dict()
        self.trk = StateTracker(self.params, self.terrain)
        self.fc.reset()
        self.weighted = None
        self.real_quit = self.real_quit_p > 0 and rng.random() < self.real_quit_p
        self.sc.cfg = forum_supervisor_config()
        self.sc.pq_cfg = replace(self._pq_emulated, emulate_quit=not self.real_quit)
        self.rq: dict = {"armed": self.real_quit, "submits": [], "menus": []}
        self.sc.reset()
        self.sent: dict[int, int] = {}
        self.raw: dict[int, dict] = {}
        self.forecasts: deque = deque(maxlen=KEEP_F)
        self._boxes: dict[int, tuple] = {}         # frame -> (hero box, game time)
        self._enters: dict = {}                    # (object, fsm) -> [(frame, to state)], kept KEEP_F frames
        self._obj_state: dict = {}                 # (object, fsm) -> current state
        self.follow_ups: list = []                 # [frame, object, hook frame or None]
        self.decision = None
        self.episode_outcome = None
        self.outcome_reason = None
        self.pause_owned = False
        self.action_flags = 0
        self.wake_sent = False
        self.first_pending_reasons: list[str] = []
        self.ring: deque = deque(maxlen=LOG_BEFORE)
        self.log_after = 0
        self.counts: Counter = Counter()
        self.tick_ms: list[float] = []
        self.plan_ms: list[float] = []
        self._last_f = None
        self._unpred_backlog = 0
        self._unpred_src: list = []
        self._mon_raws: list[dict] = []
        self.unpredicted: list[int] = []
        self.unpredicted_unknown: list[int] = []
        self.unpred_sources: list = []
        self.hits_taken: list[int] = []
        self.forced_frames: list[int] = []
        self._since_forced = FORCED_STREAK_GAP
        self.forced_streaks = 0
        self.first_pending_f = None
        self.planner_last = None
        self.last_clear_f = None
        self.enc = enc
        self.commit = None
        self.commits: list = []
        self._hit_src: dict[int, list] = {}
        self.hit_log: list[dict] = []
        self.per_wave: dict = {}
        self.wave_chk = Counter()
        self.wave_bad: list = []
        self.targets = Counter()
        self.binds = 0
        self.cog = {"throws": [], "used": Counter(), "hold": 0, "last_t": -math.inf, "frames": set()}
        self._wave_v = -1
        self._wave_t = None

    # ---- perception hooks ----

    def _wake(self, ws, s: dict, tap) -> None:
        """Every WorldState fed (ticks and caught-up frames): the hits it shows, with their source, before the
        unpredicted-hit check reads them (PlannerPolicy._catch_up / act call this first)."""
        raw0 = self.raw.get(ws.stamp.frame) or s
        fo = ws.stamp.frame
        b = (raw0.get("hero") or {}).get("box")
        if b:
            self._boxes[fo] = (b, ws.stamp.t_game_s)
        for ev in raw0.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "fsm" and d.get("fsm") in HOOK_FSMS and d.get("obj") and d.get("to"):
                key = (d["obj"], d["fsm"])
                self._enters.setdefault(key, []).append((fo, d["to"]))
                self._obj_state[key] = d["to"]
        if fo % 30 == 0:
            self._boxes = {k: v for k, v in self._boxes.items() if k >= fo - KEEP_F}
            for key in list(self._enters):
                self._enters[key] = [x for x in self._enters[key] if x[0] >= fo - KEEP_F]
        for ev in ws.events:
            if ev.kind == Ev.HIT_TAKEN:
                d = ev.data
                self._hit_src.setdefault(ws.stamp.frame, []).append(d.source_id)
                raw = self.raw.get(ws.stamp.frame) or s
                wt, _ = true_wave(raw)
                self.hit_log.append({"f": ws.stamp.frame, "t": round(ws.stamp.t_game_s, 3), "amount": d.amount,
                                     "src_type": d.source_type, "src_id": d.source_id, "wave_t": wt,
                                     "wave_v": self.fc.waves.current(ws.stamp.t_game_s), "S": getattr(self.planner_last, "S", None),
                                     "forced": bool(getattr(self.planner_last, "forced_risk", False)),
                                     "mode": getattr(self, "_mode_last", None),
                                     "tier": None if self.decision is None else self.decision.tier,
                                     "h": None if self.decision is None else self.decision.h})
                if wt is not None:
                    self.per_wave.setdefault(wt, Counter())["hits"] += 1
        super()._wake(ws, s, tap)

    def _note_kill(self, ws) -> None:
        """No kill commitment in the Forum (R3: the final blow is I3 only, no certified kill plans)."""
        return None

    def _hook_of(self, obj: str, f: int) -> int | None:
        """The hook of a multi-hit chain whose Final Hit came at f: the latest entry of the source object's Control /
        Attack FSM into the state it is in now, at most HOOK_LOOKBACK_F frames before (multi_recall.hook_contacts)."""
        best = None
        for fsm in HOOK_FSMS:
            st = self._obj_state.get((obj, fsm))
            for fr, to in self._enters.get((obj, fsm), ()):
                if to == st and f - HOOK_LOOKBACK_F <= fr < f:
                    best = fr if best is None else max(best, fr)
        return best

    def _unpredicted(self, raw: dict, fo: int) -> int:
        """PlannerPolicy._unpredicted with the Forum's multi-hit chains (R2 recall's rule): a chain's Final Hit (the
        hero's own "Roar and Wound States" FSM deals it, DamageHeroDirectly) is judged at the chain's hook, the
        source's entry into its chain state (_hook_of): the hero box there (or the frame before) against the
        support forecast UNPRED_LAGS frames before the hook. No hook found or no forecast kept: unknown (counted)."""
        n = 0
        by_f = {x[0]: x for x in self.forecasts}
        src = list(self._hit_src.get(fo, ()))
        k = 0
        for ev in raw.get("ev") or ():
            if ev.get("k") != "damage":
                continue
            d = ev.get("d") or {}
            self.hits_taken.append(fo)
            sid = src[k] if k < len(src) else None
            k += 1
            fj = fo
            if "Final Hit" in str(d.get("fsm") or ""):
                obj = str(d.get("source") or "").split("/")[0]
                fj = self._hook_of(obj, fo)
                self.follow_ups.append([fo, obj, fj])
            old = None if fj is None else next((by_f[fj - lag] for lag in UNPRED_LAGS if fj - lag in by_f), None)
            if old is None:
                n += 1
                self.unpredicted_unknown.append(fo)
                self._unpred_src.append(sid)
                self.unpred_sources.append([fo, sid])
                continue
            _, fcast, t_o = old
            cover = False
            for fr in (fj, fj - 1):
                bt = self._boxes.get(fr)
                if bt is None:
                    continue
                bx, t = bt
                x, y = 0.5 * (bx[0] + bx[2]), 0.5 * (bx[1] + bx[3])
                if fcast.occupied(np.array([[x]]), np.array([[y]]), np.array([t - t_o]))[0, 0]:
                    cover = True
                    break
            if not cover:
                n += 1
                self.unpredicted.append(fo)
                self._unpred_src.append(sid)
                self.unpred_sources.append([fo, sid])
        return n

    def _first_tick(self, ws) -> None:
        if self.weighted is not None:
            return
        self.weighted = ANKLET in (ws.res.equipped or ())
        if self.weighted:
            self.params = self.params0.with_weighted()
            self.planner.params = self.params
            self.trk = StateTracker(self.params, self.terrain)
            self.sc.cfg = forum_supervisor_config(weighted=True)
            self.sc.sup.cfg = self.sc.cfg

    def _wave_check(self, raw: dict, f: int) -> int | None:
        """WaveTracker (the view's) against room.battles (truth) on this frame. The view's wave: the last activated
        one, before wave 0's activation the queued one (BattleScene reports currentWave 0 from StartBattle, 0.75 s
        before wave 0's members are activated; every later wave from its activation). Also counted: the activated
        wave alone and queued-or-activated. Mismatches kept as runs [f0, f1, truth, view] (first 60)."""
        wt, done = true_wave(raw)
        w = self.fc.waves
        if wt is None:
            return None
        self.wave_chk["frames"] += 1
        va = w.wave
        vq = w.queued[0] if w.queued is not None else w.wave
        v = w.current(float(raw.get("_t", self.fc.t)))
        self.wave_chk["agree"] += int(v == wt)
        self.wave_chk["agree_active"] += int(va == wt)
        self.wave_chk["agree_queued"] += int(vq == wt)
        if v != wt:
            b = self.wave_bad
            if b and b[-1][1] == f - 1 and b[-1][2] == wt and b[-1][3] == v:
                b[-1][1] = f
            elif len(b) < 60:
                b.append([f, f, wt, v])
        return wt

    # ---- the tick ----

    def act(self, s: dict, tap=None) -> int:
        t0 = time.perf_counter()
        f = s["f"]
        if self.real_quit_active:
            return self._real_quit_step(s, f)
        self._catch_up(f, tap)
        self.keylog.observe(f, (s.get("act") or {}).get("mask", 0))
        self.raw[f] = s
        for old in [k for k in self.raw if k < f - 12]:
            del self.raw[old]
        ws = self.backend.feed(s)
        if ws is None:
            self.sent[f + 2] = 0
            self.keylog.tick(f, f + 2, (0,))
            return 0
        fo = ws.stamp.frame
        raw = self.raw.get(fo, s)
        raw["_t"] = ws.stamp.t_game_s
        self._first_tick(ws)
        self.trk.push(raw)
        self._wake(ws, s, tap)
        self.fc.update(ws)
        wt = self._wave_check(raw, fo)
        fcast = self.fc.forecast(HORIZON_S)
        self.forecasts.append((fo, fcast, ws.stamp.t_game_s))
        self._support = fcast.support_set(ws)
        if self.sc.pq is not None:
            return self._pause_tick(s, f, fo, ws, raw, t0)
        d = self.decision
        h, _ = self.sc.h_now(s, obs=raw, ws=ws)
        prefs = self.tac.decide(ws, fcast, d, h)
        self._mode_last = prefs.mode
        dmg, _ = self.sc.kill_inputs(s, obs=raw, ws=ws)
        kill_hp = forum_kill_hp(self.fc)
        ykill = forum_yellow_kill_hp(self.fc, self.freeze)
        ctx = FilterContext.from_world(ws, d, h, want_bind=prefs.want_bind, damage=dmg, kill_hp=kill_hp,
                                       kill_window_s=self.kill_window_s)
        ctx.silk_reserve_full_hp = self.pb.bind_reserve_at_full_hp
        hold = HoldState.from_act(raw.get("act"))
        cogf = self.cog["frames"]
        prefix = np.array([self.sent.get(fr, 0) & ~(COG if fr in cogf else 0) for fr in range(fo + 1, f + 2)],
                          np.int64)
        t1 = time.perf_counter()
        S0 = self._start_state(ws, raw)
        res = self.planner.tick(ws, S0, hold, prefix, fcast, prefs, ctx)
        self.planner_last = res
        t2 = time.perf_counter()
        unpred = self._unpredicted(raw, fo) + self._unpred_backlog
        self._unpred_backlog = 0
        src, self._unpred_src = tuple(self._unpred_src), []
        clear = self._forced_clear_f(res, fcast, S0, len(prefix)) if res.forced_risk else None
        self.last_clear_f = clear
        kw = {}
        if dmg is not None:
            kp = dmg.kill_prims(ykill)
            kw = {"kill_prims": kp, "next_hit_may_kill": bool(kp)}
        r = self.sc.step(s, obs=raw, ws=ws, inflight=self._inflight(s, f), plan_s=res.S, forced_risk=res.forced_risk,
                         unpredicted_hits=unpred, unpredicted_sources=src, p_death=res.P,
                         forced_clear_s=None if clear is None else clear * self.params.frame_time,
                         idle_clear_s=None if res.idle_clear is None else res.idle_clear * self.params.frame_time,
                         **kw)
        self.decision = r.decision
        self.pause_owned = self.sc.pq is not None
        self.action_flags = ACTION_EXCLUSIVE if self.pause_owned else 0
        if r.decision.pause_pending and self.first_pending_f is None:
            self.first_pending_f = f
            self.first_pending_reasons = list(r.decision.reasons)
        mask = res.mask if r.mask is None else r.mask
        cog = self._cogfly(f, ws, raw, res, r, fcast, S0, wt) if r.mask is None else None
        if cog is not None:
            mask = cog
            self.cog["frames"].add(f + 2)
        if r.outcome is not None and r.outcome in TERMINAL and self.episode_outcome is None:
            self.episode_outcome = "QUIT"
            self.outcome_reason = f"{r.outcome}: {'; '.join(r.decision.reasons) or 'supervisor'}"
        self.sent[f + 2] = int(mask)
        for old in [k for k in self.sent if k < f - 12]:
            del self.sent[old]
        self.cog["frames"] = {x for x in self.cog["frames"] if x >= f - 12}
        self.keylog.tick(f, f + 2, res.cmd if r.mask is None and cog is None and len(res.cmd) else (int(mask),),
                         sup=r.mask is not None)
        self.tick_ms.append((time.perf_counter() - t0) * 1e3)
        self.plan_ms.append((t2 - t1) * 1e3)
        self.counts[prefs.mode] += 1
        self.counts["forced_risk"] += res.forced_risk
        self.binds += int(res.name == "BIND")
        tt = self.tac.last.get("target_type")
        if tt:
            self.targets[tt] += 1
        streak = False
        if res.forced_risk:
            self.forced_frames.append(f)
            streak = self._since_forced >= FORCED_STREAK_GAP
            self.forced_streaks += int(streak)
            self._since_forced = 0
        else:
            self._since_forced += 1
        if wt is not None:
            pw = self.per_wave.setdefault(wt, Counter())
            pw["ticks"] += 1
            pw["forced"] += int(res.forced_risk)
            pw["streaks"] += int(streak)
        self.counts[f"tier_{r.decision.tier}"] += 1
        self._log(s, f, fo, ws, fcast, prefs, res, r, unpred, wt, kill_hp, ykill, streak)
        return int(mask)

    def _cogfly(self, f, ws, raw, res, r, fcast, S0, wt) -> int | None:
        """The Cogfly throw (module docstring, 5): the second frame of a throw under way, or a new one."""
        cg, c = self.rules.cogfly, self.cog
        if c["hold"] > 0:
            c["hold"] -= 1
            return COG
        if not cg.get("enabled") or res.S or res.forced_risk or r.decision.pause_pending:
            return None
        w = self.fc.waves.current(ws.stamp.t_game_s)
        if c["used"][w] >= cg["uses"].get(w, 0) or sum(c["used"].values()) >= COG_MAX:
            return None
        t = ws.stamp.t_game_s
        if t - c["last_t"] < cg["gap_s"]:
            return None
        if not any(x.alive and x.in_play for x in fcast.subjects):
            return None
        st = np.asarray(S0).reshape(kin.K, -1)[:, 0]
        if st[kin.GROUND] <= 0 or int(st[kin.MODE]) != kin.M_NORMAL:
            return None
        prev = self.raw.get(ws.stamp.frame - 1)
        hp0, hp1 = ((prev or {}).get("hero") or {}).get("pos"), (raw.get("hero") or {}).get("pos")
        if not hp0 or not hp1 or abs(hp1[0] - hp0[0]) > 0.02:
            return None
        hx, hy = ws.hero.pos.v
        if fcast.t_min(float(hx), float(hy), t_max=cg["min_clear_s"] + 0.1) < cg["min_clear_s"]:
            return None
        c["used"][w] += 1
        c["last_t"] = t
        c["hold"] = COG_FRAMES - 1
        c["throws"].append([f, w, wt, round(t, 2), round(float(hx), 2)])
        return COG

    def _pause_tick(self, s: dict, f: int, fo: int, ws, raw: dict, t0: float) -> int:
        unpred = self._unpredicted(raw, fo) + self._unpred_backlog
        self._unpred_backlog = 0
        src, self._unpred_src = tuple(self._unpred_src), []
        r = self.sc.step(s, obs=raw, ws=ws, inflight=self._inflight(s, f), plan_s=None, forced_risk=False,
                         unpredicted_hits=unpred, unpredicted_sources=src)
        self.decision = r.decision
        self.pause_owned = self.sc.pq is not None
        self.action_flags = ACTION_EXCLUSIVE if self.pause_owned else 0
        mask = 0 if r.mask is None else int(r.mask)
        if r.outcome is not None and r.outcome in TERMINAL and self.episode_outcome is None:
            self.episode_outcome = "QUIT"
            self.outcome_reason = f"{r.outcome}: {'; '.join(r.decision.reasons) or 'supervisor'}"
        if self.sc.pq is None:
            self.planner.reset()
        self.sent[f + 2] = mask
        self.keylog.tick(f, f + 2, (mask,), sup=True)
        for old in [k for k in self.sent if k < f - 12]:
            del self.sent[old]
        self.tick_ms.append((time.perf_counter() - t0) * 1e3)
        self.counts["PAUSE"] += 1
        self.counts[f"tier_{r.decision.tier}"] += 1
        pq = self.sc.pq
        rec = {"ep": self.episode, "f": f, "fo": fo, "t": round(ws.stamp.t_game_s, 4),
               "hero": [round(v, 3) for v in ws.hero.pos.v], "hp": ws.res.hp.v, "silk": ws.res.silk.v,
               "mode": "PAUSE", "plan": "PAUSE", "S": None, "forced": False, "mask": mask, "sup_mask": True,
               "tier": r.decision.tier, "h": r.decision.h, "pending": r.decision.pause_pending,
               "triggers": list(r.decision.triggers), "unpred": unpred, "pq": None if pq is None else pq.state,
               "outcome": r.outcome}
        self._emit(rec, any(ev.get("k") in ("damage", "catastrophe", "would_die") for ev in s.get("ev") or ()))
        return mask

    # ---- logs and stats ----

    def _log(self, s, f, fo, ws, fcast, prefs, res, r, unpred, wt, kill_hp, ykill, streak) -> None:
        li = self.planner.last_info
        subj = [[x.iid, x.type_key, x.state, round(float(x.hp_est), 1),
                 None if x.pos is None else [round(float(x.pos[0]), 2), round(float(x.pos[1]), 2)], bool(x.committed)]
                for x in fcast.subjects if x.alive and x.in_play]
        rec = {"ep": self.episode, "f": f, "fo": fo, "t": round(ws.stamp.t_game_s, 4),
               "hero": [round(v, 3) for v in ws.hero.pos.v], "hp": ws.res.hp.v, "silk": ws.res.silk.v,
               "wave_v": self.fc.waves.current(ws.stamp.t_game_s), "wave_t": wt, "known": bool(fcast.known), "mode": prefs.mode,
               "tgt": prefs.target, "tgt_type": self.tac.last.get("target_type"), "stance": round(prefs.stance_x, 2),
               "hit_w": {str(k): v for k, v in prefs.hit_w.items() if v != 1.0}, "plan": res.name, "S": res.S,
               "forced": res.forced_risk, "clear": self.last_clear_f, "P": round(res.P, 3), "J": round(res.J, 2),
               "n_safe": res.n_safe, "n_ok": res.n_allowed, "alts": res.alternatives,
               "mask": int(res.mask if r.mask is None else r.mask), "sup_mask": r.mask is not None,
               "tier": r.decision.tier, "h": r.decision.h, "pending": r.decision.pause_pending,
               "triggers": list(r.decision.triggers), "unpred": unpred, "ms": round(res.t_ms.get("total", 0.0), 3),
               "kill_hp": kill_hp, "ykill": ykill, "kill_prims": sorted(p.name for p in r.decision.kill_prims),
               "fi": {k: li.get(k) for k in ("posture", "N", "stage1_pass", "enveloped", "hitfx", "react", "capped",
                                             "cut", "overrun")},
               "pocket": self.tac.last.get("pocket_veto"), "subj": subj}
        hit = any(ev.get("k") in ("damage", "catastrophe", "would_die") for ev in s.get("ev") or ())
        event = hit or streak or (r.decision.pause_pending and self.counts["_pend_logged"] == 0)
        if r.decision.pause_pending:
            self.counts["_pend_logged"] = 1
        self._emit(rec, event)

    def stats(self) -> dict:
        self.flush_log()
        keys = self.flush_keys()
        q = (lambda v, p: round(float(np.percentile(v, p)), 3) if v else None)
        a1 = self.planner.audit.as_dict() if self.planner is not None else {}
        audit = {k: a1[k] - getattr(self, "_audit0", {}).get(k, 0) for k in a1}
        unpred_f = set(self.unpredicted) | set(self.unpredicted_unknown)
        for x in self.hit_log:
            x["unpred"] = x["f"] in unpred_f
        modes = {k: v for k, v in self.counts.items() if not k.startswith("_")}
        return {"view": self.view, "policy": "forum_planner", "k": 0, "modes": modes,
                "tick_ms_p50": q(self.tick_ms, 50), "tick_ms_p99": q(self.tick_ms, 99),
                "plan_ms_p50": q(self.plan_ms, 50), "plan_ms_p99": q(self.plan_ms, 99),
                "ticks": len(self.tick_ms), "late_ticks": sum(1 for x in self.tick_ms if x > 16.7),
                "unpredicted": self.unpredicted, "unpredicted_unknown": self.unpredicted_unknown,
                "unpredicted_sources": self.unpred_sources, "follow_ups": self.follow_ups, "hits_taken": self.hits_taken, "hit_log": self.hit_log,
                "forced_risk_ticks": len(self.forced_frames), "forced_streaks": self.forced_streaks,
                "per_wave": {str(k): dict(v) for k, v in sorted(self.per_wave.items())},
                "wave_check": dict(self.wave_chk), "wave_bad": self.wave_bad,
                "wave_tracker": {"wave": self.fc.waves.wave, "done": self.fc.waves.done,
                                 "resyncs": self.fc.waves.resyncs, "kills": self.fc.waves.kills},
                "audit": audit, "targets": dict(self.targets), "binds": self.binds,
                "cogfly": {"throws": self.cog["throws"], "n": len(self.cog["throws"])},
                "weighted": self.weighted,
                "first_pending_f": self.first_pending_f, "first_pending_reasons": self.first_pending_reasons,
                "outcome_reason": self.outcome_reason, "alerts": list(self.sc.alerts),
                "q4_by_instance": {str(k): v for k, v in getattr(self.sc.sup, "unpredicted_by", {}).items()},
                "real_quit": self.real_quit_stats(), "keys": keys}
