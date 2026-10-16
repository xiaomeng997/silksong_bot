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
import os
import random
import time
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path

import numpy as np

from ssbot.backends.oracle_backend import OracleBackend
from ssbot.combat import forum_v2, slam_play
from ssbot.combat.enemy_tables import EnemyTables
from ssbot.combat.forum_planner import (ForumConfig, ForumPlanner, forum_kill_hp, forum_yellow_kill_hp,
                                        kill_freeze_s, parse_ta)
from ssbot.combat.hero_damage import HeroDamage
from ssbot.combat.multi_forecast import MultiForecaster, ReactConfig
from ssbot.combat.planner import PlannerConfig
from ssbot.combat.projectiles import bells_mode
from ssbot.combat.safety_filter import FilterContext, KillKnowledge
from ssbot.combat.tactics.forum_local import ForumTactics, load_forum_playbook
from ssbot.combat.tactics.gauntlet import GauntletTactics, load_l2_rules
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
# the Forum loadout's kinematics per crest (fo_A: Reaper; fo_W: Wanderer, the R8 clash arm)
CREST_PARAMS = {"Reaper": FORUM_PARAMS,
                "Wanderer": REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json"}
# the R8 clash modes (ForumConfig): on = the EV_CLASH branch and its continuation rows in GREEN only (DESIGN 3.5.6's
# whitelist: no clash in YELLOW / RED or with a pause pending), yellow = also in YELLOW (the R8 experiment: the lead's
# decision before any production use), cont = the continuation rows without the branch (the A/B's control for them)
CLASH_MODES = {"off": {}, "on": {"clash": True}, "yellow": {"clash": True, "clash_tiers": ("GREEN", "YELLOW")},
               "cont": {"clash": True, "clash_branch": False},
               # the person's three-layer support (forum.md §23): a clean clash row is safe on the clash geometry, its
               # measured hit-anyway bound at most clash_max_fail, ranked after the plain safe rows by it; also in a
               # YELLOW that comes from the chosen plan's S = 1 (h >= 3), never at h 2, in RED or with a pause pending
               "main": {"clash": True, "clash_main": True, "clash_min_p": 0.0, "clash_max_fail": 0.3, "clash_depth": 3}}
END_SLOW_S = 1.85          # EnemyBattleEndSlow in real time (forum.md §3): the final blow's unpausable window
# the person 2026-10-12: the death slow motion's missing pause is not a reason to hold the killing blow back (the hero
# stays in control in it and a dead enemy cannot corner her): no U / I3 veto and no supervisor kill_prims. 0: the old
# rule (the blow that may end the battle only under I3, YELLOW's per-enemy kill freeze)
KILL_FREE = os.environ.get("SSBOT_FORUM_KILL_FREE", "1").strip() != "0"
ANKLET = "Weighted Anklet"
COG = kin.B_UP | kin.B_QUICKCAST
COG_FRAMES = 2
COG_MAX = 4                # fo_A's Cogwork Flier uses
FORCED_STREAK_GAP = 30     # a FORCED_RISK tick after this many ticks without one starts a streak (logged as an event)
BATTLE = "Battle Scene"
HOOK_LOOKBACK_F = 70       # a multi-hit chain's hook -> its Final Hit: 0.35 - 1.0 s (forum.md §9.2; tools.multi_recall)
HOOK_FSMS = ("Control", "Attack")
KEEP_F = 90                # forecasts, hero boxes and FSM entries kept for judging a Final Hit at its hook
# a hit's chosen plan this many frames before it (hit_log "lag", stats "planned_safe"; forum.md §23.12): the reaction
# lag (12), the commit lag of a typical move (24) and the 0.5 s a plan's first segment runs (30); UNPRED_LAGS (2-4)
# cannot see a risk the escape check or the idle-growth hold took on further ahead
PLAN_LAGS = (12, 24, 30)
PLAN_RING = 64
TICK_WAIT_F = HOOK_LOOKBACK_F   # a Multihit tick outside the support waits this long for its chain's Final Hit


def planned_safe(hit_log: list) -> dict:
    """The damage hits (hit_log, kind "damage") whose chosen plan was S = 0 at each PLAN_LAGS lag ("12" ...), with a
    plan chosen S = 0 in the 30 frames before ("any30") or a clean clash row chosen S = 0 there ("clash30"), whose plan
    at a lag was S = 1 by the escape check ("esc_<L>") or had an aimed-pin threat ("pin_<L>"), and the S = 0 ones by
    source path ("by_src": the 30-frame rule). A hit outside the support at UNPRED_LAGS is "unpredicted"; these are
    the hits a plan called safe that far ahead did not avoid (forum.md §23.12)."""
    out = Counter()
    src = Counter()
    for x in hit_log:
        if x.get("kind") != "damage":
            continue
        out["hits"] += 1
        for L, v in (x.get("lag") or {}).items():
            if v is None:
                out[f"unknown_{L}"] += 1
                continue
            out[L] += int(v[0] == 0)
            out[f"esc_{L}"] += int(bool(v[3]))
            out[f"pin_{L}"] += int(bool(v[4]))
        out["any30"] += int(bool(x.get("safe30")))
        out["clash30"] += int(bool(x.get("clash30")))
        if x.get("safe30"):
            src[str(x.get("path") or x.get("src_type"))] += 1
    return {**dict(out), "by_src": dict(src.most_common(12))}


def _tv_summary(rows: list) -> dict | None:
    """The chosen rows' terminal terms over an episode: mean E / overlap / H_exp, share trapped, mean share of rows
    trapped."""
    if not rows:
        return None
    a = [r for r in rows if r[0] is not None]
    m = (lambda i: round(float(np.mean([r[i] for r in a])), 4) if a else None)
    return {"ticks": len(rows), "E": m(0), "trapped": m(1), "overlap": m(2), "hexp": m(3),
            "rows_trapped": round(float(np.mean([r[4] for r in rows])), 4)}


def production_tables() -> EnemyTables:
    """The production tables; SSBOT_FORUM_MARGIN=state: with the per-state margins (support_margins_state.json,
    tools.forum_state_margins, forum.md §23) on top of the family ones."""
    if os.environ.get("SSBOT_FORUM_MARGIN", "family").strip().lower() == "state":
        from ssbot.combat.enemy_tables import FORUM_DIR
        return EnemyTables.production(state_margins_path=FORUM_DIR / "support_margins_state.json")
    return EnemyTables.production()


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
                 real_quit_p: float = 0.0, playbook: Path | str | None = None, tables: EnemyTables | None = None,
                 crest: str = "Reaper", clash: bool | str = False, branch_model: bool = False):
        import cv2
        import numba
        numba.set_num_threads(threads)
        cv2.setNumThreads(2)
        if view != "oracle":
            raise ValueError("ForumPlannerPolicy: the oracle view only (the Forum's vision view is M3)")
        self.view, self.threads, self.instance = view, threads, instance
        # the crest's kinematics and slash shapes; clash: the R8 EV_CLASH mode (CLASH_MODES; True = "on")
        self.crest, self.clash = crest, {True: "on", False: "off"}.get(clash, clash)
        if self.clash not in CLASH_MODES:
            raise ValueError(f"clash mode {clash!r}: one of {sorted(CLASH_MODES)}")
        self.crest_seen: str | None = None
        self.params0 = HeroParams.load(CREST_PARAMS[crest])
        self.params = self.params0
        self.pb, self.rules = load_forum_playbook(playbook)
        self.floor_hero_y = FLOOR_Y + hb.HERO_HALF_U[1]
        local = ForumTactics(self.pb, self.rules, self.floor_hero_y)
        # R6 v0's L2 target layer above LOCAL (Forum.yaml forum.l2; SSBOT_FORUM_L2=0: LOCAL alone, the A0 tactics)
        self.l2_rules = load_l2_rules(playbook, os.environ.get("SSBOT_FORUM_L2"))
        self.tac = GauntletTactics(local, self.l2_rules) if self.l2_rules.enabled else local
        # branch_model: the R5 branch model's history per enemy and Subject.next_p (scoring consumers: O / BAIT);
        # off by default, the planner does not read it yet
        branch = None
        if branch_model:
            from ssbot.combat.branch_model import BranchModel
            branch = BranchModel.load()
        self.fc = MultiForecaster(tables if tables is not None else production_tables(), branch=branch)
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
        self.ab = self._ab_arms()
        self.ab_arm: str | None = None
        self.free = False                       # track A "free" (_set_ta)
        self.v2feed: forum_v2.V2Feed | None = None   # v2-lite (SSBOT_FORUM_V2=1): the attack-range tracker + support
        # SSBOT_FORUM_SLAM_PLAY=1 (task 1v1 SP1, forum.md 65): the person's slam strike as a fixed playbook; None (the
        # default): nothing changes
        self.slam_play: slam_play.SlamPlay | None = slam_play.SlamPlay() if slam_play.ENABLED else None
        self._play_tick: dict | None = None

    @staticmethod
    def _ab_arms() -> list[tuple[str, dict]]:
        """SSBOT_FORUM_AB: arms switched per episode (episode k runs arm k mod n, so the arms share the machine's load
        within one batch; forum.md 20.11), "name:key=value,...;name:..." with the keys pc (commit_rank 0 / 1), fr
        (forced_rank share / seen / seen_cf), rx (the reactive support, SSBOT_FORUM_REACT's values) and ta (track A's
        tokens, SSBOT_FORUM_TA's values joined by "+", "none" for none: the supervisor's free mode and the L2 rules
        follow the arm, _set_ta). The clash mode
        is not an arm key (it changes the candidate sets the planner is built with: combat_run --forum-clash). Empty:
        one arm, the env switches below."""
        spec = os.environ.get("SSBOT_FORUM_AB", "").strip()
        arms = []
        for part in filter(None, (p.strip() for p in spec.split(";"))):
            name, _, kv = part.partition(":")
            over = {}
            for item in filter(None, (x.strip() for x in kv.split(","))):
                k, _, v = item.partition("=")
                if k == "pc" and v in ("0", "1"):
                    over["commit_rank"] = v == "1"
                elif k == "fr" and v in ("share", "seen", "seen_cf"):
                    over["forced_rank"] = v
                elif k == "rx" and v:
                    ReactConfig.parse(v)                 # validates
                    over["react"] = v
                elif k == "ta":
                    v = "" if v.strip().lower() == "none" else v     # "none": no track A token
                    parse_ta(v)                          # validates
                    over["ta"] = v
                else:
                    raise ValueError(f"SSBOT_FORUM_AB={spec!r}: {item!r} (pc=0|1, fr=share|seen|seen_cf, "
                                     f"rx=off|delay|escape[+c|+i|+p5], ta=none|<tokens>)")
            arms.append((name.strip(), over))
        return arms

    @staticmethod
    def _fcfg(clash: str = "off") -> ForumConfig:
        """ForumConfig of the R8 clash mode (CLASH_MODES) with the A/B switches SSBOT_FORUM_FR: FORCED_RISK's first
        risk key, "share" (default), "seen" or "seen_cf" (ForumConfig.forced_rank; forum.md §19); SSBOT_FORUM_REACT:
        the reactive support, "off" (default), "delay" or "escape", with "+c" / "+i" / "+p5" (ForumConfig.react;
        forum.md §22); SSBOT_FORUM_BELLS: "on" (default) or "off" (no bells as hit targets, ForumConfig.bell_hits; the
        HazardTracker keeps a hit-back bell a hazard: forum.md §23.12). The module-level switches SSBOT_FORUM_PC
        (commit_rank, default on), SSBOT_FORUM_TV (terminal value, default off) and SSBOT_FORUM_T (horizon, default 36)
        are ForumConfig's defaults (combat.forum_planner)."""
        fr = os.environ.get("SSBOT_FORUM_FR", "share").strip().lower() or "share"
        if fr not in ("share", "seen", "seen_cf"):
            raise ValueError(f"SSBOT_FORUM_FR={fr!r}: share | seen | seen_cf")
        rx = os.environ.get("SSBOT_FORUM_REACT", "off").strip().lower() or "off"
        ReactConfig.parse(rx)                    # validates
        ta = os.environ.get("SSBOT_FORUM_TA", "").strip().lower()
        parse_ta(ta)                             # validates (track A's tokens, combat.forum_planner.TA_TOKENS)
        return ForumConfig(forced_rank=fr, react=rx, bell_hits=bells_mode() == "on", ta=ta, **CLASH_MODES[clash])

    def _set_ta(self, fcfg: ForumConfig) -> None:
        """Track A's tokens (SSBOT_FORUM_TA, or the episode's AB arm) to the supervisor ("free": the DESIGN 3.5.6
        revision's free mode) and the L2 tactics ("whip", "guard", "edge"); the planner reads its own (fcfg)."""
        tac = fcfg.tac
        self.free = "free" in tac
        if isinstance(self.tac, GauntletTactics):
            self.tac.ta = tac

    def _set_react(self, fcfg: ForumConfig) -> None:
        """The forecaster's reactive support from the planner's config (None when off: the support as before)."""
        self.fc.react = ReactConfig.parse(fcfg.react)

    # ---- warm-up ----

    def warmup(self) -> float:
        """The tables' lazy parts (MultiForecaster.warm: family walks, pyramids, box tables) and the fast layer's numba
        paths on an empty forecast (ground and hit-stop start states, a Bind wanted, a kill target in reach)."""
        from ssbot.core.worldstate import E, WorldState
        t0 = time.perf_counter()
        self.fc.warm()
        fcfg = self._fcfg(self.clash)
        self._set_react(fcfg)
        planner = ForumPlanner(self.params, Terrain2D.empty(), PlannerConfig(T=fcfg.T, threads=self.threads,
                                                                             variants="bounds_lo"), fcfg,
                               crest=self.crest)
        fcast = self.fc.forecast(HORIZON_S)
        for x, mode in ((30.0, kin.M_NORMAL), (33.0, kin.M_NORMAL), (36.0, kin.M_HURT_FREEZE)):
            ws = WorldState()
            ws.hero.pos = E((x, self.floor_hero_y))
            ws.res.hp, ws.res.hp_max, ws.res.silk = E(5), E(7), E(9)
            prefs = self.tac.decide(ws, fcast, None, 3)
            prefs.want_bind = True
            ctx = FilterContext.from_world(ws, None, 3, want_bind=True, kill_hp=5.0, kill_window_s=END_SLOW_S,
                                           damage=HeroDamage.from_loadout(self.crest, 1, ()))
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
        if isinstance(self.tac, GauntletTactics):
            self.tac.reset()
            self.tac.rng = random.Random(self.episode)    # injected L2 failures: never from the episode's rng
        msg = None
        if self.terrain_tap is not None:
            msg = self.terrain_tap.wait(enc.scene, timeout_s=5.0)
        msg = msg or self.terrain_msg
        if msg is not None:
            self.terrain = Terrain2D.from_message(msg, self.params0.scene(enc.scene))
        self.terrain = self.terrain or Terrain2D.empty()
        self.params = self.params0
        if self.planner is None:
            fcfg = self._fcfg(self.clash)
            self.planner = ForumPlanner(self.params, self.terrain, PlannerConfig(T=fcfg.T, threads=self.threads,
                                                                                 variants="bounds_lo"),
                                        fcfg, crest=self.crest)
        self.planner.params = self.params
        self.planner.terrain = self.terrain
        if self.ab:
            self.ab_arm, over = self.ab[self.episode % len(self.ab)]
            self.planner.fcfg = replace(self._fcfg(self.clash), **over)
        self.planner.reset()
        mh = getattr(self.planner, "_map", None)
        if mh is not None and not mh._loaded:
            # SG8 (stalls, forum.md 64): the slam map and every wall bucket with the arena's terrain here (the episode's
            # start), not on its first tick (~0.6 s); the same runtimes either way
            mh.preload()
        if self.planner.fcfg.v2:
            self.v2feed = self.v2feed or forum_v2.V2Feed()
            self.v2feed.reset()
        else:
            self.v2feed = None
        self._set_react(self.planner.fcfg)
        self._set_ta(self.planner.fcfg)
        self._audit0 = self.planner.audit.as_dict()
        self.trk = StateTracker(self.params, self.terrain)
        self.fc.reset()
        self.weighted = None
        self.real_quit = self.real_quit_p > 0 and rng.random() < self.real_quit_p
        self.sc.cfg = forum_supervisor_config(free_until_hit=self.free)
        self.sc.pq_cfg = replace(self._pq_emulated, emulate_quit=not self.real_quit)
        self.rq: dict = {"armed": self.real_quit, "submits": [], "menus": []}
        self.sc.reset()
        self.sent: dict[int, int] = {}
        self.raw: dict[int, dict] = {}
        self.forecasts: deque = deque(maxlen=KEEP_F)
        self._boxes: dict[int, tuple] = {}         # frame -> (hero box, game time)
        self._enters: dict = {}                    # (instance, fsm) -> [(frame, to state)], kept KEEP_F frames
        self._obj_state: dict = {}                 # (instance, fsm) -> current state
        self._ent_obj: dict[int, str] = {}         # instance -> object name
        self._pending_ticks: list[int] = []        # Multihit ticks outside the support at their own frame
        self.mh_ticks: list = []                   # [frame, "own" | "chain" | "miss"] per Multihit tick
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
        self.tv_ms: list[float] = []               # the terminal value's share of the tick (field + rows + kill value)
        self.tv_rows: list[tuple] = []             # the chosen row's (E, trapped, overlap, H_exp), trapped share
        self._last_f = None
        self._unpred_backlog = 0
        self._unpred_src: list = []
        self._mon_raws: list[dict] = []
        self.unpredicted: list[int] = []
        self.unpredicted_unknown: list[int] = []
        self.unpred_sources: list = []
        self.hits_taken: list[int] = []
        # the chosen plan per tick (observation frame, S, FORCED_RISK, a clean clash row, S = 1 by the escape check,
        # an aimed-pin threat): a hit's plan PLAN_LAGS frames before it (forum.md §23.12: the hits the bot did not see
        # coming at the commit lag, not only at UNPRED_LAGS)
        self._plan_ring: deque = deque(maxlen=PLAN_RING)
        self._pin_ticks0: int | None = None
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
        if self.slam_play is not None:
            self.slam_play.reset()
        self._play_tick = None
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
        special, dealt = set(), set()
        for ev in raw0.get("ev") or ():
            d = ev.get("d") or {}
            k = ev.get("k")
            if k == "fsm" and d.get("fsm") in HOOK_FSMS and d.get("obj") and d.get("to"):
                ent = d.get("ent")
                key = (d["obj"] if ent is None else int(ent), d["fsm"])
                if ent is not None:
                    self._ent_obj[int(ent)] = d["obj"]
                self._enters.setdefault(key, []).append((fo, d["to"]))
                self._obj_state[key] = d["to"]
            elif k == "special_damage":
                special.add(d.get("fsm") or d.get("method"))
            elif k == "damage":
                dealt.add(d.get("source"))
        if fo % 30 == 0:
            self._boxes = {k: v for k, v in self._boxes.items() if k >= fo - KEEP_F}
            for key in list(self._enters):
                self._enters[key] = [x for x in self._enters[key] if x[0] >= fo - KEEP_F]
        for ev in ws.events:
            if ev.kind == Ev.HIT_TAKEN:
                d = ev.data
                # a Multihit tick (special_damage, TakeQuickDamage: no source) or a damage event's hit
                kind = "tick" if d.caller_path in special and d.caller_path not in dealt else "damage"
                self._hit_src.setdefault(ws.stamp.frame, []).append(
                    {"path": d.caller_path, "sid": d.source_id, "kind": kind, "used": False})
                raw = self.raw.get(ws.stamp.frame) or s
                wt, _ = true_wave(raw)
                self.hit_log.append({"f": ws.stamp.frame, "t": round(ws.stamp.t_game_s, 3), "amount": d.amount,
                                     "kind": kind, "path": d.caller_path,
                                     "src_type": d.source_type, "src_id": d.source_id, "wave_t": wt,
                                     "wave_v": self.fc.waves.current(ws.stamp.t_game_s), "S": getattr(self.planner_last, "S", None),
                                     "forced": bool(getattr(self.planner_last, "forced_risk", False)),
                                     "mode": getattr(self, "_mode_last", None),
                                     "tier": None if self.decision is None else self.decision.tier,
                                     "h": None if self.decision is None else self.decision.h,
                                     **self._plan_lags(ws.stamp.frame)})
                if wt is not None:
                    self.per_wave.setdefault(wt, Counter())["hits" if kind == "damage" else "mh_ticks"] += 1
        if not self.wake_sent and tap is not None and tap.wake_frame is not None:
            # PlannerPolicy._wake with the battle's first wave: a wave-start savestate (Forum_A_w<i>, its intro rebases
            # the start to the wave's activation) starts the WaveTracker at wave i
            dt = (s["f"] - tap.wake_frame) * self.params.frame_time
            name = str(getattr(self.enc, "name", ""))
            w0 = int(name.rsplit("_w", 1)[1]) if "_w" in name and name.rsplit("_w", 1)[1].isdigit() else 0
            self.fc.notify_wake(ws.stamp.t_game_s - dt, wave=w0)
            self.wake_sent = True

    def _plan_lags(self, fo: int) -> dict:
        """A hit at observation frame fo against the chosen plans before it: "lag" {L: [S, FORCED_RISK, clean clash,
        S = 1 by the escape check, aimed-pin threat] of the last tick at or before fo - L (None: none kept)} for
        PLAN_LAGS, "safe30": a plan chosen with S = 0 in the 30 frames before fo, "clash30": a clean clash row chosen
        with S = 0 there (forum.md §23.12)."""
        ring = list(self._plan_ring)
        lag = {}
        for L in PLAN_LAGS:
            x = next((x for x in reversed(ring) if x[0] <= fo - L), None)
            lag[str(L)] = None if x is None or fo - L - x[0] > 4 else list(x[1:])
        recent = [x for x in ring if fo - 30 <= x[0] < fo]
        return {"lag": lag, "safe30": any(x[1] == 0 for x in recent),
                "clash30": any(x[1] == 0 and x[3] for x in recent)}

    def _note_kill(self, ws) -> None:
        """No kill commitment in the Forum (R3: the final blow is I3 only, no certified kill plans)."""
        return None

    def _hook_of(self, sid: int | None, path: str, f: int) -> int | None:
        """The hook of a multi-hit chain whose Final Hit came at f: the latest entry of the source instance's Control /
        Attack FSM into the state it is in now, at most HOOK_LOOKBACK_F frames before (multi_recall.hook_contacts, keyed
        by instance). The instance is the Final Hit's HIT_TAKEN source iid; without one, or with no entry found for it,
        every instance whose object name is a part of the source path ("Wave 1/Song Reed/ParrySlash Hit": the Reeds)."""
        def latest(ents) -> int | None:
            best = None
            for e in ents:
                for fsm in HOOK_FSMS:
                    st = self._obj_state.get((e, fsm))
                    for fr, to in self._enters.get((e, fsm), ()):
                        if to == st and f - HOOK_LOOKBACK_F <= fr < f:
                            best = fr if best is None else max(best, fr)
            return best
        if sid is not None:
            hk = latest((int(sid),))
            if hk is not None:
                return hk
        parts = {p.replace("(Clone)", "").strip() for p in str(path or "").split("/") if p}
        return latest([e for e, o in self._ent_obj.items() if o in parts] + sorted(parts))

    @staticmethod
    def _take(hits: list, path) -> dict | None:
        """The first HIT_TAKEN of the frame not paired yet whose caller path is this event's (a rejected "damage"
        event is DAMAGE_BLOCKED, not HIT_TAKEN: None)."""
        for e in hits:
            if not e["used"] and e["path"] == path:
                e["used"] = True
                return e
        return None

    def _covered(self, fj: int | None, by_f: dict) -> bool | None:
        """The hero box at fj (or the frame before) inside the support forecast UNPRED_LAGS frames before fj; None:
        no forecast kept (unknown)."""
        old = None if fj is None else next((by_f[fj - lag] for lag in UNPRED_LAGS if fj - lag in by_f), None)
        if old is None:
            return None
        _, fcast, t_o = old
        for fr in (fj, fj - 1):
            bt = self._boxes.get(fr)
            if bt is None:
                continue
            bx, t = bt
            x, y = 0.5 * (bx[0] + bx[2]), 0.5 * (bx[1] + bx[3])
            if fcast.occupied(np.array([[x]]), np.array([[y]]), np.array([t - t_o]))[0, 0]:
                return True
        return False

    def _count(self, fo: int, sid, cover: bool | None) -> int:
        """1 for a hit outside the support (cover False) or not judged (None: unknown), noted with its source."""
        if cover:
            return 0
        (self.unpredicted_unknown if cover is None else self.unpredicted).append(fo)
        self._unpred_src.append(sid)
        self.unpred_sources.append([fo, sid])
        return 1

    def _unpredicted(self, raw: dict, fo: int) -> int:
        """PlannerPolicy._unpredicted with the Forum's multi-hit chains (R2 recall's rule): a chain's Final Hit (the
        hero's own "Roar and Wound States" FSM deals it, DamageHeroDirectly) is judged at the chain's hook, the
        source's entry into its chain state (_hook_of): the hero box there (or the frame before) against the
        support forecast UNPRED_LAGS frames before the hook. No hook found or no forecast kept: unknown (counted).
        A Multihit tick (special_damage that took health) is judged at its own frame; one outside the support there
        waits up to TICK_WAIT_F frames for its chain's Final Hit (which judges the chain at its hook) and is counted
        when none comes (or the episode ends first: _flush_ticks). Each "damage" event takes the source iid of the
        frame's HIT_TAKEN with its caller path (Q4 per instance); a rejected one (DAMAGE_BLOCKED) is judged with none."""
        n = 0
        by_f = {x[0]: x for x in self.forecasts}
        hits = self._hit_src.get(fo, [])
        finals = False
        for ev in raw.get("ev") or ():
            k = ev.get("k")
            if k not in ("damage", "special_damage"):
                continue
            d = ev.get("d") or {}
            if k == "special_damage":
                if self._take(hits, d.get("fsm") or d.get("method")) is not None:
                    if self._covered(fo, by_f):
                        self.mh_ticks.append([fo, "own"])
                    else:
                        self._pending_ticks.append(fo)
                continue
            self.hits_taken.append(fo)
            e = self._take(hits, d.get("source"))
            sid = None if e is None else e["sid"]
            fj = fo
            if "Final Hit" in str(d.get("fsm") or ""):
                path = str(d.get("source") or "")
                fj = self._hook_of(sid, path, fo)
                self.follow_ups.append([fo, path.split("/")[0], fj])
                finals = True
            n += self._count(fo, sid, self._covered(fj, by_f))
        if finals and self._pending_ticks:
            keep = []
            for x in self._pending_ticks:
                if fo - HOOK_LOOKBACK_F <= x <= fo:
                    self.mh_ticks.append([x, "chain"])      # judged with its chain's Final Hit, at the hook
                else:
                    keep.append(x)
            self._pending_ticks = keep
        return n + self._flush_ticks(fo)

    def _flush_ticks(self, fo: int | None) -> int:
        """Count the Multihit ticks outside the support at their own frame whose chain's Final Hit did not come
        within TICK_WAIT_F frames (fo None: the episode ended, all of them)."""
        n = 0
        keep = []
        for x in self._pending_ticks:
            if fo is None or fo - x >= TICK_WAIT_F:
                self.mh_ticks.append([x, "miss"])
                n += self._count(x, None, False)
            else:
                keep.append(x)
        self._pending_ticks = keep
        return n

    def _first_tick(self, ws, raw: dict | None = None) -> None:
        if self.weighted is not None:
            return
        # the crest the savestate has (the policy's kinematics and slash shapes are the constructor's: a mismatch is
        # counted in stats, never silently fixed)
        self.crest_seen = ((raw or {}).get("hero") or {}).get("crest")
        self.weighted = ANKLET in (ws.res.equipped or ())
        if self.weighted:
            self.params = self.params0.with_weighted()
            self.planner.params = self.params
            self.trk = StateTracker(self.params, self.terrain)
            self.sc.cfg = forum_supervisor_config(weighted=True, free_until_hit=self.free)
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
        self._first_tick(ws, raw)
        self.trk.push(raw)
        self._wake(ws, s, tap)
        self.fc.update(ws)
        wt = self._wave_check(raw, fo)
        fcast = self.fc.forecast(HORIZON_S)
        fplan = fcast
        if self.v2feed is not None:
            # v2: the attack-range tracker fed every game frame up to f (its support for the planner, origin fo, is
            # built after the L2 decision: the focus margin needs the controller's target)
            self.v2feed.feed(self.raw, f)
        self.forecasts.append((fo, fcast, ws.stamp.t_game_s))
        self._support = fcast.support_set(ws)
        if self.sc.pq is not None:
            return self._pause_tick(s, f, fo, ws, raw, t0)
        d = self.decision
        h, _ = self.sc.h_now(s, obs=raw, ws=ws)
        prefs = self.tac.decide(ws, fcast, d, h)
        self._mode_last = prefs.mode
        if self.v2feed is not None:
            fplan = self.v2feed.support(fcast, fo, focus=getattr(prefs, "target", None))
        dmg, _ = self.sc.kill_inputs(s, obs=raw, ws=ws)
        kill_hp = None if KILL_FREE else forum_kill_hp(self.fc)
        ykill = None if KILL_FREE else forum_yellow_kill_hp(self.fc, self.freeze)
        ctx = FilterContext.from_world(ws, d, h, want_bind=prefs.want_bind, damage=dmg, kill_hp=kill_hp,
                                       kill_window_s=self.kill_window_s)
        ctx.silk_reserve_full_hp = self.pb.bind_reserve_at_full_hp
        hold = HoldState.from_act(raw.get("act"))
        cogf = self.cog["frames"]
        prefix = np.array([self.sent.get(fr, 0) & ~(COG if fr in cogf else 0) for fr in range(fo + 1, f + 2)],
                          np.int64)
        t1 = time.perf_counter()
        S0 = self._start_state(ws, raw)
        res = self.planner.tick(ws, S0, hold, prefix, fplan, prefs, ctx)
        self.planner_last = res
        pt = self.planner.audit.pin_ticks
        cl = getattr(res, "clash", None)
        self._plan_ring.append((fo, int(res.S), bool(res.forced_risk), bool(cl and not cl[2]),
                                bool((self.planner.last_info.get("esc") or {}).get("unsafe")),
                                self._pin_ticks0 is not None and pt > self._pin_ticks0))
        self._pin_ticks0 = pt
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
        play = None
        if self.slam_play is not None:
            # SP1: the slam playbook's keys while its script runs (the supervisor's keys win and end the script)
            play = self.slam_play.step(f, s, ws.hero.contact.v == "GROUND",
                                       bool((s.get("hero") or {}).get("hero_accepting_input", True)),
                                       t_game=ws.stamp.t_game_s if slam_play.GAME_CLOCK else None)
            if play is not None and (r.mask is not None or self.pause_owned):
                self.slam_play.abort("supervisor")
                play = None
            rp = self.slam_play.run
            self._play_tick = None if rp is None else {"phase": rp.phase, "k": rp.k, "mask": play,
                                                        "why": rp.why}
            if play is not None:
                mask = play
                self.counts["slam_play"] += 1
        cog = None if play is not None else self._cogfly(f, ws, raw, res, r, fcast, S0, wt)
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
        self.keylog.tick(f, f + 2, res.cmd if r.mask is None and cog is None and play is None and len(res.cmd)
                         else (int(mask),), sup=r.mask is not None)
        self.tick_ms.append((time.perf_counter() - t0) * 1e3)
        self.plan_ms.append((t2 - t1) * 1e3)
        tvi = self.planner.last_info.get("tv")
        if tvi is not None:
            self.tv_ms.append(tvi["ms"])
            self.tv_rows.append((tvi.get("E"), tvi.get("trapped"), tvi.get("overlap"), tvi.get("hexp"),
                                 tvi["trapped_share"]))
        self.counts[prefs.mode] += 1
        self.counts["forced_risk"] += res.forced_risk
        if getattr(res, "clash", None):
            self.counts["clash_partial" if res.clash[2] else "clash_plan"] += 1
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
        if r.mask is not None or res.forced_risk or r.decision.pause_pending:
            c["hold"] = 0           # the supervisor's keys or the evasive ones: the throw's second frame is dropped
            return None
        if c["hold"] > 0:
            c["hold"] -= 1
            return COG
        if not cg.get("enabled") or res.S:
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
                                             "cut", "overrun", "tv", "seen", "seen_cf", "esc")},
               "pocket": self.tac.last.get("pocket_veto"), "goal": self.tac.last.get("goal"),
               "goal_why": self.tac.last.get("goal_why"), "goal_t_end": self.tac.last.get("goal_t_end"),
               "l2_cands": self.tac.last.get("l2_cands"), "ta": self.tac.last.get("ta"),
               "free": bool(getattr(r.decision, "free", False)), "subj": subj}
        if li.get("map") is not None:
            rec["map"] = li["map"]               # SSBOT_FORUM_SPECIAL_MAP (SG4): the map row / readiness this tick
        if self._play_tick is not None:
            rec["play"] = self._play_tick        # SSBOT_FORUM_SLAM_PLAY (SP1): the playbook's phase / frame / keys
            if self._play_tick["mask"] is not None:
                rec["mask"] = int(self._play_tick["mask"])
        if getattr(res, "clash", None):
            # the chosen plan relies on a clash: w (every clash in it happens), clashes, ranked in FORCED_RISK (partial,
            # or w below clash_min_p)
            rec["clash"] = [round(res.clash[0], 4), res.clash[1], bool(res.clash[2])]
        hit = any(ev.get("k") in ("damage", "catastrophe", "would_die") for ev in s.get("ev") or ())
        event = hit or streak or (r.decision.pause_pending and self.counts["_pend_logged"] == 0)
        if r.decision.pause_pending:
            self.counts["_pend_logged"] = 1
        self._emit(rec, event)

    def stats(self) -> dict:
        if not hasattr(self, "_pending_ticks"):
            # never reset: the first episode's intro failed (a solo_clear timeout) before the policy ran
            return {"reset": False}
        self._flush_ticks(None)
        self.flush_log()
        keys = self.flush_keys()
        q = (lambda v, p: round(float(np.percentile(v, p)), 3) if v else None)
        a1 = self.planner.audit.as_dict() if self.planner is not None else {}
        audit = {k: a1[k] - getattr(self, "_audit0", {}).get(k, 0) for k in a1}
        unpred_f = set(self.unpredicted) | set(self.unpredicted_unknown)
        for x in self.hit_log:
            x["unpred"] = x["f"] in unpred_f
        modes = {k: v for k, v in self.counts.items() if not k.startswith("_")}
        fc = self.planner.fcfg if self.planner is not None else None
        return {"view": self.view, "policy": "forum_planner", "k": 0, "modes": modes, "ab_arm": self.ab_arm,
                "fcfg": None if fc is None else {"forced_rank": fc.forced_rank, "react": fc.react,
                                                 "commit_rank": fc.commit_rank, "terminal": fc.terminal, "T": fc.T,
                                                 "ta": "+".join(sorted(fc.tac)), "v2": fc.v2,
                                                 "v2_margin": forum_v2.MARGIN_MODE if fc.v2 else None},
                "v2_support_ms_p50": q(self.v2feed.ms, 50) if self.v2feed is not None else None,
                "v2_support_ms_p99": q(self.v2feed.ms, 99) if self.v2feed is not None else None,
                "branch_model": self.fc.bv is not None,
                "tick_ms_p50": q(self.tick_ms, 50), "tick_ms_p99": q(self.tick_ms, 99),
                "plan_ms_p50": q(self.plan_ms, 50), "plan_ms_p99": q(self.plan_ms, 99),
                "tv_ms_p50": q(self.tv_ms, 50), "tv_ms_p99": q(self.tv_ms, 99), "terminal": _tv_summary(self.tv_rows),
                "ticks": len(self.tick_ms), "late_ticks": sum(1 for x in self.tick_ms if x > 16.7),
                "unpredicted": self.unpredicted, "unpredicted_unknown": self.unpredicted_unknown,
                "unpredicted_sources": self.unpred_sources, "follow_ups": self.follow_ups, "mh_ticks": self.mh_ticks, "hits_taken": self.hits_taken, "hit_log": self.hit_log,
                "planned_safe": planned_safe(self.hit_log),
                "forced_risk_ticks": len(self.forced_frames), "forced_streaks": self.forced_streaks,
                "per_wave": {str(k): dict(v) for k, v in sorted(self.per_wave.items())},
                "wave_check": dict(self.wave_chk), "wave_bad": self.wave_bad,
                "wave_tracker": {"wave": self.fc.waves.wave, "done": self.fc.waves.done,
                                 "resyncs": self.fc.waves.resyncs, "kills": self.fc.waves.kills},
                "audit": audit, "targets": dict(self.targets), "binds": self.binds,
                "cogfly": {"throws": self.cog["throws"], "n": len(self.cog["throws"])},
                "weighted": self.weighted, "crest": self.crest, "crest_seen": self.crest_seen, "clash": self.clash,
                "first_pending_f": self.first_pending_f, "first_pending_reasons": self.first_pending_reasons,
                "outcome_reason": self.outcome_reason, "alerts": list(self.sc.alerts),
                "q4_by_instance": {str(k): v for k, v in getattr(self.sc.sup, "unpredicted_by", {}).items()},
                "real_quit": self.real_quit_stats(), "keys": keys,
                "l2": self.tac.stats_dict() if isinstance(self.tac, GauntletTactics) else None,
                **({"slam_play": self.slam_play.stats()} if self.slam_play is not None else {})}
