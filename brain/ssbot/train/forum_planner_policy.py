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
import copy
import os
import random
import time
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path

import numpy as np

from ssbot.backends.oracle_backend import OracleBackend
from ssbot.combat import (air_chain, air_show, cast_stab, claw_chase, claw_strike, evade_chase, forum_v2, rune_lowhop, observed_slam,
                          slam_play, two_play)
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
# map v2 stage M4c (SSBOT_FORUM_MAP2, default off; ssbot.map2.live): the map2 search plays live - its worker processes
# search from the newest observed state, a plan passes the exact HERO2 re-simulation from the current state before it
# takes the keys, a failed per-frame check or no plan hands them back to this planner (and its scripts). Needs
# SSBOT_FORUM_HERO2=1. Off: ssbot.map2 is not imported and nothing below changes.
MAP2 = os.environ.get("SSBOT_FORUM_MAP2", "0").strip() == "1"
SCENE_FIELD_SHADOW = os.environ.get("SSBOT_FORUM_SCENE_FIELD_SHADOW", "0").strip() == "1"
SCENE_FIELD_RANK = os.environ.get("SSBOT_FORUM_SCENE_FIELD_RANK", "0").strip() == "1"
SCENE_FIELD_WEIGHT_HITS = float(os.environ.get("SSBOT_FORUM_SCENE_FIELD_WEIGHT_HITS", "1.0"))
if SCENE_FIELD_RANK and (not math.isfinite(SCENE_FIELD_WEIGHT_HITS) or SCENE_FIELD_WEIGHT_HITS < 0):
    raise ValueError("scene field weight must be finite and nonnegative")
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


def _win_rows_on() -> bool:
    """Task oldwin stage F2: SSBOT_FORUM_WINDOWS_ROWS=0 keeps the window table's Clapper tracker (the slam press path's,
    SSBOT_FORUM_WINDOWS_PRESS) without its rows in the planner (stage L: 0 rows chosen live, their cost late / deadline-
    cut ticks +3 %); default 1: as before."""
    return os.environ.get("SSBOT_FORUM_WINDOWS_ROWS", "1").strip() != "0"


class ForumPlannerPolicy(PlannerPolicy):
    act_after_clear = True
    win = None                  # task oldwin: ssbot.map2.oldwin.WindowRows with SSBOT_FORUM_WINDOWS=1 (a class default:
    #                             off, no instance attribute is added - see __init__)
    wpress = None               # task oldwin stage N: ssbot.map2.oldwin_press.WinPress with SSBOT_FORUM_WINDOWS_PRESS=1
    #                             (the slam windows by the reflex's exact check on a worker; a class default as win)

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
        # SSBOT_FORUM_HERO2 (map v2 M0, default off): the hero model with the M0 calibration (kin.hero2: the same
        # object when off)
        self.params0 = kin.hero2(HeroParams.load(CREST_PARAMS[crest]))
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
        self.measurement = None
        self.measurement_choice = None
        self.chain_native = None           # opt-in audit bridge, not a key owner
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
        # SP6 (SSBOT_FORUM_JB_DASH_SLASH): the dash slash in the jump cast's antic (combat.cast_stab); SP8: + the
        # RecoilStab (SSBOT_FORUM_JB_DASH_COMBO), or dash, stop, side slashes (SSBOT_FORUM_JB_DASH_STOP)
        self.cast_stab: cast_stab.CastStab | None = cast_stab.CastStab() if cast_stab.ENABLED else None
        # SP8c (SSBOT_FORUM_EVADE_CHASE, default off): chase the Clapper's evade (combat.evade_chase); SP9a
        # (SSBOT_FORUM_TWO_CHASE, default off): the focus's evade with two Clappers
        self.evade_chase: evade_chase.EvadeChase | None = (
            evade_chase.EvadeChase(one=evade_chase.ENABLED, two=two_play.CHASE)
            if (evade_chase.ENABLED or two_play.CHASE) else None)
        # SP8d (SSBOT_FORUM_RUNE_LOWHOP, follows v2): the small runes on the ground, slashes through, one low hop per
        # bomb at her x (combat.rune_lowhop); SP9a (SSBOT_FORUM_TWO_CAST, default off): also on the focus's close cast
        # with two Clappers
        self.rune_lowhop: rune_lowhop.RuneLowHop | None = (rune_lowhop.RuneLowHop(two=two_play.CAST)
                                                           if rune_lowhop.ENABLED else None)
        # SP9a (SSBOT_FORUM_TWO_IDLEHIT / _SPACE / _OPEN, default off; combat.two_play): two Clappers
        self.two: two_play.TwoPlay | None = two_play.TwoPlay() if two_play.ANY else None
        # SP10c (SSBOT_FORUM_CLAW_CHASE, default off): the late Clawline on a far jump (combat.claw_chase)
        self.claw: claw_chase.ClawChase | None = (claw_chase.ClawChase()
                                                  if (claw_chase.ENABLED or claw_chase.CLAWAIR) else None)   # SP14 CLAWAIR
        # SP-AIR1 (SSBOT_FORUM_AIRSHOW, default off; a show arm): one Clapper killed without landing (combat.air_show)
        self.air_show = None
        if air_show.AIRSHOW:
            self.air_show = air_show.AirShow()
        self._wake_f: int | None = None
        self._play_tick: dict | None = None
        self.own_trace: list = []                 # SP10a: see reset()
        self._own_last: tuple | None = None
        # M4c (SSBOT_FORUM_MAP2): the map2 controller (its workers start in warmup); None: off
        self.m2 = None
        if MAP2:
            if not kin.hero2_on():
                raise ValueError("SSBOT_FORUM_MAP2=1 needs SSBOT_FORUM_HERO2=1 (the map2 search's hero model)")
            if crest != "Wanderer":
                raise ValueError("SSBOT_FORUM_MAP2: the Wanderer crest only (the search's hero model)")
            from ssbot.map2 import live as m2live
            self.m2 = m2live.Map2Controller(instance=instance, log_dir=log_dir)
            self._m2_final: tuple | None = None
        # task oldwin (SSBOT_FORUM_WINDOWS=1, default off): the strike-window table's rows in this planner
        # (ssbot.map2.oldwin.WindowRows: its Clapper tracker fed every STATE; the planner's _win_rows). Off: the class's
        # None (no instance attribute: an added one moved the slam script's decision on 3 replay ticks - HANDOFF),
        # ssbot.map2 not imported. The table was generated with HERO2: needs it on.
        if os.environ.get("SSBOT_FORUM_WINDOWS", "0").strip() == "1":
            if not kin.hero2_on():
                raise ValueError("SSBOT_FORUM_WINDOWS=1 needs SSBOT_FORUM_HERO2=1 (the table's hero model)")
            from ssbot.map2 import oldwin as m2oldwin
            self.win = m2oldwin.WindowRows()
            # stage N (SSBOT_FORUM_WINDOWS_PRESS=1, default off): the slam windows (claw_slam0, claw_head2, hop_slam0,
            # drop_slam0, pogo_head2) by the reflex's own path - the exact check on a worker, a bridge of the planner's
            # keys, a Press owning the keys with its phases confirmed (ssbot.map2.oldwin_press); meant with the slam
            # scripts off (SSBOT_FORUM_SLAM_PLAY=0 SSBOT_FORUM_CLAWSTRIKE=0)
            if os.environ.get("SSBOT_FORUM_WINDOWS_PRESS", "0").strip() == "1":
                from ssbot.map2 import oldwin_press as m2op
                self.wpress = m2op.WinPress(self.win)
        elif os.environ.get("SSBOT_FORUM_WINDOWS_PRESS", "0").strip() == "1":
            raise ValueError("SSBOT_FORUM_WINDOWS_PRESS=1 needs SSBOT_FORUM_WINDOWS=1 (its Clapper tracker)")
        if os.environ.get("SSBOT_FORUM_KNIFE_ROWS", "0").strip() == "1":
            from ssbot.combat import forum_knife
            forum_knife.validate_environment()
            self.win.knife = True
            self.win.knife_scope = False
            from ssbot.map2.clapper import Know
            self.win.knife_knowledge = Know.load()

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
        if fcfg.v2:
            forum_v2.warm_aim_tables()
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
        if self.win is not None:
            from ssbot.combat.holdfilter import hold_filter_jit as _hf
            self.win.warm(kin.initial_state(self.params, 30.0, FLOOR_Y + self.params.foot), self.params,
                          Terrain2D.empty(), self.threads, _hf, HoldState.idle(1))     # task oldwin
            if _win_rows_on():
                planner.warm_win(kin.initial_state(self.params, 30.0, FLOOR_Y + self.params.foot))
            if getattr(self.win, "knife", False):
                from ssbot.combat import forum_knife
                forum_knife.warm(planner)
            if self.wpress is not None and self.wpress.ready is None:
                self.wpress.start()           # stage N: the check worker (spawned, warmed; inproc: the checker here)
        if air_chain.AIRCHAIN or claw_strike.AIRSTRIKE:
            air_chain.warm(self.params)       # SP10b: the air chain's numba paths (else compiled inside a tick)
        if claw_strike.CLAWSTRIKE:
            claw_strike.warm(self.params)     # SP13: the Clawline strike's plan paths (air_chain's evaluate)
        if two_play.RUNETIER or rune_lowhop.BOMBS2 or two_play.PMCAST:
            from ssbot.combat import rune_pogo
            rune_pogo.warm(self.params)       # SP11a: the pogo tier's planner (else compiled inside a tick); SP13b
            #                                   the low hop's air plans (BOMBS2) use the same rollouts / SAT kernel
        if two_play.PMCAST:
            from ssbot.combat import push_cast
            push_cast.warm(self.params)       # SP13b: the cast route's over planner
        if air_show.AIRSHOW:
            air_show.warm(self.params)        # SP-AIR1: the air show's planner
        if self.m2 is not None:
            self.m2.warm()                    # M4c: the commit check's compiled paths
            if not self.m2.procs:
                self.m2.start()               # the search workers (spawned, warmed; waits until they are ready)
        if os.environ.get("SSBOT_FORUM_CHAIN_B2", "0").strip() == "1":
            from ssbot.combat.knife_chain_nominal import warm_nominal
            self.b2_warmup_report=warm_nominal(self.params)
            # A B2 smoke may run without the A/A measurement wrapper. It still
            # needs the real nonempty parallel query signatures before combat.
            from ssbot.train.measurement import warm_query_kernels
            from ssbot.combat.knife_chain_nominal import compiled_signatures
            self.b2_warmup_report["query_warmup"]=warm_query_kernels()
            self.b2_warmup_report["compiled_signatures"]=compiled_signatures()
        self.fc.reset()
        return time.perf_counter() - t0

    # ---- per episode ----

    def _reset_chain_native(self, *, observe_baseline=True) -> None:
        native = os.environ.get("SSBOT_FORUM_CHAIN_NATIVE", "0").strip() == "1"
        b2 = os.environ.get("SSBOT_FORUM_CHAIN_B2", "0").strip() == "1"
        if b2 and not native:
            raise ValueError("B2 requires explicit CHAIN_NATIVE=1")
        if native:
            if not kin.hero2_on() or self.crest != "Wanderer":
                raise ValueError("native chain probe needs HERO2 and the Wanderer crest")
            if os.environ.get("SSBOT_FORUM_KNIFE_ROWS", "0").strip() == "1":
                raise ValueError("new chains cannot activate the paused strict knife generator")
            if any(getattr(self, n, None) is not None for n in ("m2", "air_show", "wpress")):
                raise ValueError("native chain probe conflicts with another controller/cache")
            from ssbot.combat.knife_chain_candidates import NativeChainCandidates
            selected = NativeChainCandidates
            if b2:
                if not self._fcfg(self.clash).v2:
                    raise ValueError("B2 requires the live V2 danger tracker")
                from ssbot.combat.knife_chain_b2 import NativeChainB2
                selected = NativeChainB2
            journal = None if self.log_path is None else str(self.log_path.with_suffix(".chain.jsonl"))
            existing = getattr(self, "chain_native", None)
            if type(existing) is selected:
                if not existing.can_reuse(journal=journal):
                    raise ValueError("native probe configuration changed; start a new fixed-config controller")
            else:
                self.chain_native = selected.from_env(journal=journal)
        elif os.environ.get("SSBOT_FORUM_CHAIN_AUDIT", "0").strip() != "1":
            self.chain_native = None
        elif type(getattr(self, "chain_native", None)).__name__ != "NativeChainAudit":
            from ssbot.combat.knife_chain_native import NativeChainAudit
            self.chain_native = NativeChainAudit()
        if self.chain_native is not None:
            frame = getattr(getattr(self, "link", None), "frame", None)
            self.chain_native.reset(self.episode, start_frame=frame if type(frame) is int else None)
            baseline = getattr(getattr(self, "link", None), "state", None)
            if b2 and observe_baseline and baseline is not None:
                self.chain_native.observe_learning(baseline)
        if getattr(self, "planner", None) is not None:
            self.planner.chain_native = self.chain_native

    def prepare_learning_batch(self, options):
        """Resolve fixed B2 config/budget before warm-up, with no hero/action credit."""
        from ssbot.combat.knife_chain_budget import execution_conditions,LearningStop
        try:
            self._reset_chain_native(observe_baseline=False)
        except ValueError as exc:
            raise LearningStop("B2 batch configuration failure: "+str(exc)) from exc
        if not getattr(self.chain_native,"b2",False):raise LearningStop("B2 batch policy bridge missing")
        self.chain_native.budget.bind_execution(execution_conditions(options))
        return self.chain_native.budget

    def _begin_chain_native(self, state) -> None:
        audit = getattr(self, "chain_native", None)
        if audit is None:
            return
        history = ()
        if self._inbox is not None:
            with self._inbox_lock:
                history = tuple(self._inbox)
        audit.begin(state, history)

    def learning_check(self, state, tap) -> None:
        """Account actual HP before harness lethal/clear exits, including catch-up."""
        audit = getattr(self, "chain_native", None)
        if not getattr(audit, "b2", False):
            return
        history = ()
        if self._inbox is not None:
            with self._inbox_lock:
                history = tuple(self._inbox)
        for item in (*history, state):
            if (audit._episode_start is None or item["f"] >= audit._episode_start) and item["f"] <= state["f"]:
                audit.observe_learning(item, kill_frame=tap.death_frame)
        if tap.lethal:
            audit._stop("lethal hit", state["f"])

    def reset(self, rng: random.Random, enc) -> None:
        self.flush_log()
        self.flush_keys()
        self.episode += 1
        if os.environ.get("SSBOT_FORUM_CHAIN_B2", "0").strip() == "1" and enc.name != "Forum_W_w7":
            raise ValueError("first B2 learning profile is restricted to Forum_W_w7")
        try:
            self._reset_chain_native()
        except ValueError as exc:
            if os.environ.get("SSBOT_FORUM_CHAIN_B2", "0").strip() != "1":
                raise
            from ssbot.combat.knife_chain_budget import LearningStop
            raise LearningStop("B2 bootstrap/configuration failure: " + str(exc)) from exc
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
        if self.win is not None and _win_rows_on():
            self.planner.win = self.win           # task oldwin (stage F2: SSBOT_FORUM_WINDOWS_ROWS=0 - the tracker only)
        if self.ab:
            self.ab_arm, over = self.ab[self.episode % len(self.ab)]
            self.planner.fcfg = replace(self._fcfg(self.clash), **over)
        self.planner.reset()
        self.planner.chain_native = self.chain_native  # future row producer's audit hook; None when off
        if self.win is not None and getattr(self.win, "knife", False):
            self.win.knife_scope = enc.name == "Forum_W_w7"
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
        if SCENE_FIELD_SHADOW or SCENE_FIELD_RANK:
            from ssbot.combat.scene_field_shadow import SceneFieldShadow
            self._scene_field_reader = SceneFieldShadow.for_forum(self.pb.arena_x)
            from ssbot.combat.scene_field_event_shadow import SceneFieldEventShadow
            self._scene_field_event_reader = SceneFieldEventShadow.for_forum(egress_only=SCENE_FIELD_RANK)
            self._scene_field_current = None
            self._scene_field_error = False
            self._scene_field_rank_current = None
        if SCENE_FIELD_RANK:
            from ssbot.combat.scene_field_values import SceneFieldValues
            self._scene_field_rank_type = SceneFieldValues
            self.planner.scene_field_values = None
        self._audit0 = self.planner.audit.as_dict()
        self.trk = StateTracker(self.params, self.terrain)
        self.fc.reset()
        self.weighted = None
        self.real_quit = self.real_quit_p > 0 and rng.random() < self.real_quit_p
        self.sc.cfg = forum_supervisor_config(free_until_hit=self.free,
            remaining_hp_quit=getattr(getattr(self.chain_native,"budget",None),"remaining_hp_quit",None))
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
        if self.cast_stab is not None:
            self.cast_stab.reset()
        if self.claw is not None:
            self.claw.reset()
        if self.evade_chase is not None:
            self.evade_chase.reset()
        if self.rune_lowhop is not None:
            self.rune_lowhop.reset()
        if self.two is not None:
            self.two.reset()
        if self.air_show is not None:
            self.air_show.reset()
            self._air_k = 0
        self._wake_f = None
        self._play_tick = None
        self._wave_v = -1
        self._wave_t = None
        # SP10a (logging only): who sent each tick's keys, run-length coded - [f, own, crit, L2 target, goal, why] on
        # every tick where one of them changes (own: plan / sup / slam / stab / low / chase / two:<part> / cog)
        self.own_trace: list = []
        self._own_last: tuple | None = None
        if self.m2 is not None:
            self.m2.reset(self.episode)          # M4c: a new tracker, no plan, the episode's log
            self._m2_final = None
        if self.win is not None:
            self.win.reset()                     # task oldwin: a new Clapper tracker, no continued row
        if self.wpress is not None:
            self.wpress.reset()                  # stage N: no snapshot / commit / Press carried over

    # ---- perception hooks ----

    def _wake(self, ws, s: dict, tap) -> None:
        """Every WorldState fed (ticks and caught-up frames): the hits it shows, with their source, before the
        unpredicted-hit check reads them (PlannerPolicy._catch_up / act call this first)."""
        raw0 = self.raw.get(ws.stamp.frame) or s
        fo = ws.stamp.frame
        if self.m2 is not None:
            self.m2.feed(raw0, fo)               # M4c: the Clapper tracker, every STATE
        if self.win is not None:
            self.win.feed(raw0, fo)              # task oldwin: the window table's Clapper tracker, every STATE
        if self.wpress is not None:
            self.wpress.feed(raw0, fo)           # stage N: her clip / input / hits / freezes (the Press's phases)
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

    def _b2_priority_chain(self):
        chain=getattr(self,"chain_native",None)
        return chain if (getattr(chain,"b2",False) and getattr(chain,"arm",None)=="B"
                         and getattr(chain,"candidate_generation",False)) else None

    @staticmethod
    def _b2_policy_gate(*, low_crit, asw_crit, m2_on, supervisor):
        if supervisor:return "supervisor"
        if m2_on:return "m2"
        if low_crit:return "low_crit"
        if asw_crit:return "asw_crit"
        return None

    def _b2_script_critical(self, f, s):
        # B2 must know the SAME current script gates before proposing. Observe
        # LOWHOP once here; its later h2 priority block reuses this snapshot.
        low=False
        if self.rune_lowhop is not None:
            self.rune_lowhop.observe(f,s)
            low=self.rune_lowhop.critical()
        skip=self.two.asw_skip() if (self.two is not None and two_play.ASW) else None
        asw=(not low) and self.two is not None and two_play.ASW and self.two.asw_critical()
        rt=(two_play.RUNETIER or two_play.FLIPB) and self.two is not None and self.two.rt_critical()
        return low,skip,asw or rt,rt

    def _b2_selected_for_policy(self, res, *, fresh):
        chain=self._b2_priority_chain()
        if chain is None or not fresh or not str(getattr(res,"name","")).startswith("CHAIN B2 "):
            return False
        info=self.planner.last_info.get("b2")
        if not isinstance(info,dict):return False
        selected=getattr(chain,"_b2_selected",None)
        if selected is not None:
            return selected.stage==info.get("stage") and int(selected.mask)==int(res.mask)
        # Recovery release has no row/Run offer, but is still the planner's
        # current B2 result. It must not be replaced by a lower-priority script.
        return info.get("stage")=="recovery" and int(res.mask)==0

    def act(self, s: dict, tap=None) -> int:
        t0 = time.perf_counter()
        f = s["f"]
        if SCENE_FIELD_SHADOW:
            self._scene_field_current = None
        if observed_slam.ENABLED and getattr(self, "measurement", None) is not None:
            # A policy tick can return before calling the planner. Never attach
            # an older tick's model evaluation to that early return.
            self.planner.observed_slam_audit = None
        if SCENE_FIELD_RANK:
            self.planner.scene_field_values = None
            self._scene_field_rank_current = None
        self._begin_chain_native(s)
        diag = self.measurement.diagnostics if self.measurement is not None else None
        if diag is not None: diag.phase("catch_up")
        if self.measurement is not None:
            self.measurement_choice = None
        if self.real_quit_active:
            mask = self._real_quit_step(s, f)
            self._measure_choice("real_quit", mask, frame=f)
            return mask
        self._catch_up(f, tap)
        self.keylog.observe(f, (s.get("act") or {}).get("mask", 0))
        self.raw[f] = s
        for old in [k for k in self.raw if k < f - 12]:
            del self.raw[old]
        if diag is not None: diag.phase("observe")
        ws = self.backend.feed(s)
        if ws is None:
            self.sent[f + 2] = 0
            self.keylog.tick(f, f + 2, (0,))
            self._measure_choice("no_world_state", 0, frame=f)
            return 0
        fo = ws.stamp.frame
        raw = self.raw.get(fo, s)
        raw["_t"] = ws.stamp.t_game_s
        self._first_tick(ws, raw)
        self.trk.push(raw)
        self._wake(ws, s, tap)
        if diag is not None: diag.phase("prediction")
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
            if diag is not None: diag.phase("pause_script")
            return self._pause_tick(s, f, fo, ws, raw, t0)
        if diag is not None: diag.phase("tactics")
        d = self.decision
        h, _ = self.sc.h_now(s, obs=raw, ws=ws)
        esc_on = self.two is not None and (two_play.ESC or two_play.ASW)
        pre_obs = esc_on or (self.two is not None and (two_play.JUMPHIT or two_play.PMANY))
        if pre_obs:
            # SP9b / SP9c: the bookkeeping first, so L2 sees this tick's escape run (the focus's jump at the wall) or
            # antic switch; SP10c: TWO_JUMPHIT's run
            self.two.observe(f, s, ws.stamp.t_game_s)
            if isinstance(self.tac, GauntletTactics):
                if esc_on:
                    self.tac.two_esc = self.two.esc_view()
                if two_play.JUMPHIT:
                    self.tac.two_jh = self.two.jh_view()
                if two_play.PMANY:
                    self.tac.two_pm = self.two.pm_view()      # SP11b: L2 holds F in the herd
        prefs = self.tac.decide(ws, fcast, d, h)
        if self.two is not None:
            # SP9a: the per-tick bookkeeping (Idle entries, jump take-offs, rune circles) and TWO_SPACE's stance
            if not pre_obs:
                self.two.observe(f, s, ws.stamp.t_game_s)
            prefs = self.two.space(prefs, s, ws.stamp.t_game_s, getattr(prefs, "target", None))
            if two_play.RUNEEXIT:
                # SP12a: the jump casts' circles still to light for the planner's exit tier
                rx = self.two.rune_exit(f, s, ws.stamp.t_game_s)
                if rx:
                    prefs = replace(prefs, rune_exit=rx)
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
        if getattr(self.chain_native,"b2",False) and fo==f and len(prefix)==1:
            desired,source=self.chain_native.queued_prefix(f,s)
            if desired is not None:
                prefix[0]=desired & ~(COG if f+1 in cogf else 0)
        t1 = time.perf_counter()
        if diag is not None: diag.phase("planner")
        S0 = self._start_state(ws, raw)
        # M4c (SSBOT_FORUM_MAP2): map2's keys for f + 2 (a received plan committed after its exact re-simulation from
        # this state, or the plan in control's next keys while its per-frame check holds); None: the fallback's
        m2_mask = self.m2.pre(f, fo, raw, S0, prefix, hold) if self.m2 is not None else None
        if self.m2 is not None:
            # M4d2: while map2 searches from the bridge this planner sent, its CONTINUE row is that bridge (followed
            # unless its own checks need a change); None: no hold (map2 has the keys, or nothing searched from it)
            self.planner.hold_row = None if m2_mask is not None else self.m2.hold_row(f)
        # SP-AIR1 (SSBOT_FORUM_AIRSHOW): while the show owns the keys its planner and this one alternate (the tick's
        # cost): on the show's ticks the last plan result stands for the supervisor
        air_tick = False
        if self.air_show is not None and not self.air_show.done and self.planner_last is not None:
            self._air_k += 1
            air_tick = self._air_k % 2 == 1
        if self.wpress is not None:
            # stage N: while a committed press's bridge runs the planner's CONTINUE row is that bridge (M4d2's hold)
            self.planner.hold_row = self.wpress.hold_row(f)
        b2_priority=self._b2_priority_chain()
        b2_critical=None
        if b2_priority is not None:
            b2_critical=self._b2_script_critical(f,s)
            b2_priority.policy_gate_reason=self._b2_policy_gate(low_crit=b2_critical[0],asw_crit=b2_critical[2],
                m2_on=m2_mask is not None,supervisor=self.pause_owned or self.sc.pq is not None)
        if air_tick:
            res = self.planner_last
        else:
            if self.chain_native is not None:
                self.chain_native.planner_input(origin=fo, prefix=prefix, hold=hold, hero_state=S0)
            if callable(getattr(self.chain_native, "prepare", None)):
                sim_chain = air_chain.ChainSim(S0, prefix, hold, self.params, self.terrain, fo, f)
                b2_bombs = None
                if getattr(self.chain_native, "b2", False) and self.v2feed is not None:
                    from ssbot.combat import rune_bombs as _rbm
                    trk_ = self.v2feed.trk
                    b2_bombs = _rbm.frames(trk_.rune.predict(trk_.T), trk_.T)
                self.chain_native.prepare(s, ground=ws.hero.contact.v == "GROUND",
                    accepting=bool((s.get("hero") or {}).get("hero_accepting_input", True)), sim=sim_chain,
                    **({"bombs": b2_bombs} if getattr(self.chain_native, "b2", False) else {}))
            if SCENE_FIELD_RANK:
                self._scene_field_before_plan(fplan, s, f)
            res = self.planner.tick(ws, S0, hold, prefix, fplan, prefs, ctx)
        self.planner_last = res
        if SCENE_FIELD_SHADOW:
            if diag is not None: diag.phase("scene_field_shadow")
            self._scene_field_after_plan(res, fplan, f, fo, fresh=not air_tick, state=s)
            if diag is not None: diag.phase("planner")
        if self.chain_native is not None:
            self.chain_native.planner_result(res, fresh=not air_tick)
        if two_play.RUNEEXIT and self.two is not None and getattr(prefs, "rune_exit", None):
            self.two.rx_note(f, self.planner.last_info.get("rx"))      # SP12a
        pt = self.planner.audit.pin_ticks
        cl = getattr(res, "clash", None)
        self._plan_ring.append((fo, int(res.S), bool(res.forced_risk), bool(cl and not cl[2]),
                                bool((self.planner.last_info.get("esc") or {}).get("unsafe")),
                                self._pin_ticks0 is not None and pt > self._pin_ticks0))
        self._pin_ticks0 = pt
        t2 = time.perf_counter()
        if diag is not None: diag.phase("scripts")
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
        own = "plan" if r.mask is None else "sup"
        play = None
        # M4c: map2 has the keys (the supervisor's still win): the scripts are not stepped (their runs aborted on the
        # tick it takes them), the planner above keeps planning from the keys actually sent (the clean handover)
        m2_on = m2_mask is not None and r.mask is None and not self.pause_owned
        if m2_on:
            mask = play = int(m2_mask)
            own = "m2"
            self.counts["map2"] += 1
            self._play_tick = None
            if self.m2.took:
                self._m2_take()
        # SP11-0 (SSBOT_FORUM_TWO_GUARD): the other Clapper's danger spans for the one-Clapper scripts (None: off)
        gsp = (self.two.guard_spans(f, s, ws.stamp.t_game_s)
               if (two_play.GUARD and self.two is not None) else None)
        if self.cast_stab is not None:
            self.cast_stab.observe(f, s)          # SP8: the rune circles' first frame and lit state, every tick
        if self.evade_chase is not None:
            self.evade_chase.observe(f, s)        # SP8c: the same for the chase
        # SP8d: while the low hop's hold or a bomb window over her is on, its script keeps the keys (the other scripts
        # are not stepped: they start from the air a few frames later)
        if b2_critical is not None:
            low_crit,asw_skip,asw_crit,rt_crit=b2_critical
        else:
            low_crit = False
            if self.rune_lowhop is not None:
                self.rune_lowhop.observe(f, s)
                low_crit = self.rune_lowhop.critical()
            # SP9c (SSBOT_FORUM_TWO_ANTICSWITCH): the antic switch's F - the slam playbook and the low hop leave its move
            asw_skip = self.two.asw_skip() if (self.two is not None and two_play.ASW) else None
            # SP9c: its bomb hop over F's small runes at her x is committed - its script keeps the keys (the others are not
            # stepped, like the low hop's critical window)
            asw_crit = (not low_crit) and self.two is not None and two_play.ASW and self.two.asw_critical()
            # SP11a (SSBOT_FORUM_TWO_RUNETIER): the pogo tier's run holds the keys - no other script is stepped (its keys
            # come from TwoPlay.step below; the supervisor's still win)
            rt_crit = (two_play.RUNETIER or two_play.FLIPB) and self.two is not None and self.two.rt_critical()   # SP14 FLIPB
            asw_crit = asw_crit or rt_crit
        if self.wpress is not None:
            # stage N (SSBOT_FORUM_WINDOWS_PRESS): a committed slam-window press / its bridge owns the keys; the scripts
            # are not stepped (as under map2); a script's critical window (LOWHOP's bomb hop, ASW) defers a new commit
            wm_ = self.wpress.decide(f, fo, raw, S0, prefix, hold, res, self.sent,
                                     r.mask is not None or self.pause_owned or m2_on, crit=low_crit or asw_crit)
            if wm_ is not None:
                mask = play = int(wm_)
                own = "win"
                m2_on = True                      # (the scripts' own gates: not stepped while it has the keys)
                self.counts["win_press"] += 1
                self._play_tick = None
        if self.air_show is not None and not self.pause_owned and r.mask is None and not m2_on:
            # SP-AIR1 (SSBOT_FORUM_AIRSHOW): the air show owns the keys to the kill (no other script is stepped)
            trk_ = self.v2feed.trk if self.v2feed is not None else None
            abk = None
            if trk_ is not None and getattr(trk_, "rune", None) is not None:
                from ssbot.combat import rune_bombs as _rbm
                abk = _rbm.frames(trk_.rune.predict(trk_.T), trk_.T)
            am = self.air_show.step(f, s, ws.hero.contact.v == "GROUND",
                                    bool((s.get("hero") or {}).get("hero_accepting_input", True)),
                                    air_chain.ChainSim(S0, prefix, hold, self.params, self.terrain, fo, f), bombs=abk,
                                    plan=air_tick or self.air_show.plan is None)
            if am is not None:
                mask = play = int(am)
                own = "air"
                asw_crit = True
                self.counts["air_show"] += 1
        if b2_priority is not None:
            # Restore SLAM_PLAY's original script priority for a selected B2
            # candidate. Critical scripts / map2 / supervisor still keep keys.
            b2_priority.policy_gate_reason=self._b2_policy_gate(low_crit=low_crit,asw_crit=asw_crit,
                m2_on=m2_on,supervisor=r.mask is not None or self.pause_owned)
            if b2_priority.policy_gate_reason is None and self._b2_selected_for_policy(res,fresh=not air_tick):
                mask=play=int(res.mask)
                own="chain"
                self.counts["b2_script_priority"]+=1
        if (self.slam_play is not None and not low_crit and not asw_crit and not m2_on
                and not getattr(self.chain_native, "candidate_generation", False)):
            # SP1: the slam playbook's keys while its script runs (the supervisor's keys win and end the script)
            # SP10b (SSBOT_FORUM_TWO_AIRCHAIN): the hero model of this tick for the air chain's plan
            sim = (air_chain.ChainSim(S0, prefix, hold, self.params, self.terrain, fo, f)
                   if ((air_chain.AIRCHAIN and self.two is not None) or claw_strike.CLAWSTRIKE
                       or claw_strike.AIRSTRIKE) else None)
            if two_play.PUSHMID and self.two is not None:
                self.slam_play.side_hint = self.two.pm_hint()  # SP11b: F's slam's way out to its wall side
            bks = None
            if ((slam_play.STRIKEGUARD and slam_play.SG_BOMBS) or claw_strike.CLAWSTRIKE) and self.v2feed is not None:
                # SP12a: the small-rune bombs (frames from this STATE) for the strike's path
                trk_ = self.v2feed.trk
                if getattr(trk_, "rune", None) is not None:
                    from ssbot.combat import rune_bombs as _rbm
                    bks = _rbm.frames(trk_.rune.predict(trk_.T), trk_.T)
            play = self.slam_play.step(f, s, ws.hero.contact.v == "GROUND",
                                       bool((s.get("hero") or {}).get("hero_accepting_input", True)),
                                       t_game=ws.stamp.t_game_s if slam_play.GAME_CLOCK else None, skip=asw_skip,
                                       sim=sim, guard=gsp, bombs=bks)
            if play is not None and (r.mask is not None or self.pause_owned):
                self.slam_play.abort("supervisor")
                play = None
            rp = self.slam_play.run
            self._play_tick = None if rp is None else {"phase": rp.phase, "k": rp.k, "mask": play,
                                                        "why": rp.why}
            if play is not None:
                mask = play
                own = "slam"
                self.counts["slam_play"] += 1
        if self.claw is not None and play is None and not low_crit and not asw_crit:
            # SP10c: the late Clawline on a far jump while its script runs (the supervisor's keys win)
            cm = self.claw.step(f, s, ws.hero.contact.v == "GROUND",
                                bool((s.get("hero") or {}).get("hero_accepting_input", True)), ws.stamp.t_game_s,
                                **({"req": self.two.claw_req} if (two_play.RT2 and self.two is not None) else {}))
            if cm is not None and (r.mask is not None or self.pause_owned):
                self.claw.abort("supervisor")
                cm = None
            if cm is not None:
                mask = play = cm
                own = "claw"
                self.counts["claw_chase"] += 1
        if self.cast_stab is not None and play is None and not low_crit and not asw_crit:
            # SP6: the dash slash in the jump cast's antic while its script runs (the supervisor's keys win)
            def latch(m: int, _h=hold, _p=prefix) -> int:
                # the key mask the oracle's hold filter latches at f + 2 when m is sent for it
                lat, _ = kin.hold_filter(np.append(_p, np.int64(m)), _h)
                return int(lat[-1])
            stab = self.cast_stab.step(f, s, ws.hero.contact.v == "GROUND",
                                       bool((s.get("hero") or {}).get("hero_accepting_input", True)),
                                       t_game=ws.stamp.t_game_s, latch=latch,
                                       esc=self.two.esc_view() if esc_on else None)
            if stab is not None and (r.mask is not None or self.pause_owned):
                self.cast_stab.abort("supervisor")
                stab = None
            if stab is not None:
                mask = play = stab
                own = "stab"
                self.counts["cast_stab"] += 1
        if self.rune_lowhop is not None and play is not None:
            self.rune_lowhop.yield_to(s)          # SP8d: another script has the keys (outside the hop's window)
        elif self.rune_lowhop is not None and not asw_crit:
            # SP8d: the small-rune cast script (the supervisor's keys win)
            def latch_h(m: int, _h=hold, _p=prefix) -> int:
                lat, _ = kin.hold_filter(np.append(_p, np.int64(m)), _h)
                return int(lat[-1])
            lh_kw = {}
            if self.rune_lowhop.pmc and self.two is not None:
                # SP13b (SSBOT_FORUM_TWO_PMCAST): the cast route's F (its over plan instead of the hop)
                lh_kw["pm"] = self.two.pm_cast()
            if self.rune_lowhop.b2 or self.rune_lowhop.pmc:
                # SP13b (SSBOT_FORUM_TWO_BOMBS2): every caster's bombs (the tracker's forecast, frames from this
                # STATE) and, in the air, the hero model of this tick for the umbrella / drift plans
                trk_ = self.v2feed.trk if self.v2feed is not None else None
                if trk_ is not None and getattr(trk_, "rune", None) is not None:
                    from ssbot.combat import rune_bombs as _rbm
                    lh_kw["bombs"] = _rbm.frames(trk_.rune.predict(trk_.T), trk_.T)
                if (self.rune_lowhop.pmc and (lh_kw.get("pm") or self.rune_lowhop.active())) or (
                        ws.hero.contact.v != "GROUND" and self.rune_lowhop.active()):
                    lh_kw["sim"] = air_chain.ChainSim(S0, prefix, hold, self.params, self.terrain, fo, f)
            lh = self.rune_lowhop.step(f, s, ws.hero.contact.v == "GROUND",
                                       bool((s.get("hero") or {}).get("hero_accepting_input", True)),
                                       t_game=ws.stamp.t_game_s, latch=latch_h,
                                       skip=(asw_skip if not (two_play.RT2 and self.two is not None
                                                              and self.two.rt_hold_block(f))
                                             else frozenset(e.get("iid") for e in slam_play.clappers(s))),
                                       guard=gsp if (gsp is not None and self.two.gcfg.low) else None, **lh_kw)
            if self.rune_lowhop.pm_giveup and self.two is not None:
                self.two.pm_note(f, "low " + self.rune_lowhop.pm_giveup)     # SP13b: the cast route given up
            if lh is not None and (r.mask is not None or self.pause_owned):
                self.rune_lowhop.abort("supervisor")
                lh = None
            if lh is not None:
                mask = play = lh
                own = "low"
                self.counts["rune_lowhop"] += 1
        if self.evade_chase is not None and play is not None:
            self.evade_chase.yield_to(s)          # SP8c: another script has the keys: the chase run ends
        elif self.evade_chase is not None and not asw_crit:
            # SP8c: the chase of the Clapper's evade while its script runs (the supervisor's keys win)
            def latch_c(m: int, _h=hold, _p=prefix) -> int:
                lat, _ = kin.hold_filter(np.append(_p, np.int64(m)), _h)
                return int(lat[-1])
            ch = self.evade_chase.step(f, s, ws.hero.contact.v == "GROUND",
                                       bool((s.get("hero") or {}).get("hero_accepting_input", True)), latch=latch_c,
                                       focus=getattr(prefs, "target", None),
                                       block=((self.two.jh_block(f) if (self.two is not None and two_play.JUMPHIT)
                                               else None)
                                              or (self.two.rt_hold_block(f) if (self.two is not None and two_play.RT2)
                                                  else None)), guard=gsp)
            if ch is not None and (r.mask is not None or self.pause_owned):
                self.evade_chase.abort("supervisor")
                ch = None
            if ch is not None:
                mask = play = ch
                own = "chase"
                self.counts["evade_chase"] += 1
        if self.two is not None and play is None:
            # SP9a S2 IdleHit / S6 the opening (the supervisor's keys win)
            if self._wake_f is None and tap is not None and getattr(tap, "wake_frame", None) is not None:
                self._wake_f = int(tap.wake_frame)
            latch_t = None
            if two_play.ASW or two_play.JUMPHIT:
                def latch_t(m: int, _h=hold, _p=prefix) -> int:
                    lat, _ = kin.hold_filter(np.append(_p, np.int64(m)), _h)
                    return int(lat[-1])
            # SP11a: the hero model of this tick for the pogo tier's plans (only while its run is on)
            rt_sim = (air_chain.ChainSim(S0, prefix, hold, self.params, self.terrain, fo, f)
                      if (two_play.RUNETIER and self.two.rt_critical()) else None)
            rt_kw = {"sim": rt_sim} if two_play.RUNETIER else {}
            if two_play.RT2 and rt_sim is not None and self.v2feed is not None:
                # SP12b: the small-rune bombs (frames from this STATE) for the run's plans
                trk_ = self.v2feed.trk
                if getattr(trk_, "rune", None) is not None:
                    from ssbot.combat import rune_bombs as _rbm
                    rt_kw["bombs"] = _rbm.frames(trk_.rune.predict(trk_.T), trk_.T)
            tm_ = self.two.step(f, s, ws.hero.contact.v == "GROUND",
                                bool((s.get("hero") or {}).get("hero_accepting_input", True)),
                                getattr(prefs, "target", None), ws.stamp.t_game_s, wake_f=self._wake_f,
                                two_enc="_w13" in str(getattr(self.enc, "name", "")), latch=latch_t, **rt_kw)
            if tm_ is not None and not (r.mask is not None or self.pause_owned):
                mask = play = tm_
                own = "two:" + str(getattr(self.two, "last_part", None))
                self.counts["two_play"] += 1
        elif esc_on or (self.two is not None and two_play.WALKOUT):
            if esc_on:
                self.two.esc_yield(f, s)          # SP9b: another script has the keys: a running hop ends
            if two_play.WALKOUT:
                self.two.wo_yield(f)              # SP11b: the walk-out ends
        cog = None if play is not None else self._cogfly(f, ws, raw, res, r, fcast, S0, wt)
        if cog is not None:
            mask = cog
            own = "cog"
            self.cog["frames"].add(f + 2)
        if self.pause_owned:
            own = "sup"
        key = (own, "low" if low_crit else "rt" if (two_play.RUNETIER and rt_crit) else "asw" if asw_crit else None,
               getattr(prefs, "target", None),
               self.tac.last.get("goal"), self.tac.last.get("goal_why"))
        if key != self._own_last:
            self._own_last = key
            self.own_trace.append([f, *key])
        if r.outcome is not None and r.outcome in TERMINAL and self.episode_outcome is None:
            self.episode_outcome = "QUIT"
            self.outcome_reason = f"{r.outcome}: {'; '.join(r.decision.reasons) or 'supervisor'}"
        if self.wpress is not None:
            # stage N: the snapshot to the check worker (a slam window may open: the planner's row as the bridge) or
            # a running press's re-check
            self.wpress.post(f, fo, raw, S0, prefix, hold, int(mask), own, getattr(res, "cmd", None),
                             r.mask is not None or self.pause_owned)
        if self.m2 is not None:
            # M4c: the snapshot to the search workers (the keys in flight with this one, the bridge expected while
            # they search) and map2's per-tick log row
            self.m2.post(f, fo, raw, S0, prefix, hold, int(mask), own, getattr(res, "cmd", None),
                         r.mask is not None or self.pause_owned)
            self._m2_final = (own, int(mask))
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
        if diag is not None: diag.phase("logging")
        self._log(s, f, fo, ws, fcast, prefs, res, r, unpred, wt, kill_hp, ykill, streak)
        if diag is not None: diag.phase("choice_capture")
        self._measure_choice(own, mask, res, prefix=prefix, hold=hold, prefs=prefs,
                             frame=f, origin_frame=fo)
        return int(mask)

    def _scene_field_before_plan(self, forecast, state, frame):
        """Pin the low-frequency field before candidate scoring; no prediction call."""
        from ssbot.combat import scene_field_events as events, scene_field_locked as locked
        from ssbot.combat.scene_field_grid import SceneFieldGrid
        started=time.perf_counter()
        feed=getattr(self,"v2feed",None);rs=getattr(forecast,"rs",None)
        base={"schema":1,"frame":frame,"component":"egress","applied_to_ranking":False}
        self._scene_field_rank_current=base
        if self.crest != "Wanderer" or not kin.hero2_on():
            base["status"]="reference_hero_model_unsupported";return
        if feed is None or rs is None:
            base["status"]="support_unknown";return
        trk=feed.trk;T=float(trk.T)
        if getattr(rs,"scene_field_bombs_T",None)!=T:
            base["status"]="small_runes_stale_or_unknown";return
        reader=self._scene_field_event_reader
        view=locked.locked_scene(trk,frame=frame,room=locked.room_of_state(state),arenas=reader.arenas,
                                 bombs=getattr(rs,"scene_field_bombs",None),pend=rs.pend)
        previous=reader.cache._field
        fs,reason=locked.field_for_tick(reader.cache,events,view,reader.inputs,SceneFieldGrid,
                                       events.Config(),prepared=reader.prepared,select=reader.select)
        base.update(status=reason,prepare_ms=(time.perf_counter()-started)*1000.,
                    rebuilt=fs is not None and fs is not previous)
        if fs is None:return
        values=self._scene_field_rank_type(fs,now_s=T,k_shift=rs.k_shift,frame_time=self.params.frame_time,
                                abilities=self.params.abilities,weight_hits=SCENE_FIELD_WEIGHT_HITS,frame=frame)
        self.planner.scene_field_values=values
        base.update(applied_to_ranking=True,snapshot_id=fs.meta["identity"][:16],weight_hits=SCENE_FIELD_WEIGHT_HITS)

    def _scene_field_after_plan(self, res, forecast, frame, origin_frame, *, fresh, state=None):
        """Optional observation only; one bounded measurement record, no action edits."""
        measurement = getattr(self, "measurement", None)
        if measurement is None or not measurement.detail or getattr(self, "_scene_field_error", False):
            return
        rs = getattr(forecast, "rs", None)
        feed = getattr(self, "v2feed", None)
        if rs is None or feed is None:
            return
        started = time.perf_counter()
        try:
            event_reader = getattr(self, "_scene_field_event_reader", None)
            if not rs.pend and state is not None and event_reader is not None:
                self._scene_field_current = event_reader.inspect(
                    feed.trk, state, rs.pend, res.path, frame=frame, origin_frame=origin_frame,
                    k_shift=rs.k_shift, fresh=fresh,
                    bombs=getattr(rs, "scene_field_bombs", None),
                    bombs_T=getattr(rs, "scene_field_bombs_T", None))
            else:
                self._scene_field_current = self._scene_field_reader.inspect(
                    feed.trk, rs.pend, res.path, frame=frame, origin_frame=origin_frame,
                    k_shift=rs.k_shift, fresh=fresh)
            if self._scene_field_current is not None:
                self._scene_field_current["cost_ms"] = (time.perf_counter() - started) * 1000.0
        except Exception as exc:
            # Non-controlling telemetry fails visibly once, then stays disabled
            # until reset. It must not take the controller's keys or hide a bug.
            self._scene_field_current = {"schema": 1, "policy_frame": frame,
                "origin_frame": origin_frame, "status": "error", "error_type": type(exc).__name__,
                "message": str(exc)[:160], "applied_to_ranking": False,
                "cost_ms": (time.perf_counter() - started) * 1000.0}
            self._scene_field_error = True

    def _measure_choice(self, owner, mask, res=None, *, prefix=None, hold=None, prefs=None,
                        frame=None, origin_frame=None) -> None:
        if getattr(self, "chain_native", None) is not None:
            # Public policy ownership is chain; the native dispatch still uses
            # its original selected planner-row identity at the send boundary.
            self.chain_native.final("plan" if owner=="chain" and self._b2_priority_chain() is not None else owner, mask)
        if getattr(self, "measurement", None) is None:
            return
        if not self.measurement.detail:
            return
        from ssbot.train.measurement import escape_evidence
        idx = int(res.idx) if res is not None else None
        fresh = res is not None and getattr(self.planner, "measurement_result", None) is res
        info = self.planner.last_info if fresh else {}
        esc = escape_evidence(info, idx)
        score = float(res.J) if res is not None and hasattr(res, "J") else None
        goal = copy.deepcopy({k: getattr(getattr(self, "tac", None), "last", {}).get(k)
                              for k in ("goal", "goal_why")})
        self.measurement_choice = {
            "owner": owner, "planner_row": idx,
            "planner_name": res.name if res is not None else None,
            "planner_mask": int(res.mask) if res is not None else None,
            "script_override": owner not in ("plan", "chain", "no_world_state"),
            "planner_escape": esc,
            "final_key_escape": esc["status"] if owner in ("plan", "chain") else "unchecked",
            "plan_ms": float(res.t_ms.get("total", 0.0)) if res is not None else None,
            "candidate_S": int(res.S) if res is not None and hasattr(res, "S") else None,
            "forced_risk": bool(res.forced_risk) if res is not None and hasattr(res, "forced_risk") else None,
            "score": score if score is None or math.isfinite(score) else {"float": str(score)},
            "deadline_cut": bool(info["cut"]) if "cut" in info else None,
            "deadline_overrun": bool(info["overrun"]) if "overrun" in info else None,
            "enveloped_rows": int(info["enveloped"]) if "enveloped" in info else None,
            "target_iid": int(prefs.target) if prefs is not None and prefs.target is not None else None,
            "stance_x": float(prefs.stance_x) if prefs is not None else None,
            "mode": prefs.mode if prefs is not None else None, **goal,
            "inflight_prefix": prefix.tolist() if prefix is not None else None,
            "planner_hold": {k: getattr(hold, k).tolist() for k in ("latched", "desired", "pending", "age")}
                if hold is not None else None}
        if SCENE_FIELD_RANK:
            rank=getattr(self,"_scene_field_rank_current",None)
            if rank is not None and rank.get("frame")==frame:
                self.measurement_choice["scene_field_rank"]=dict(rank)
                detail=self.planner.last_info.get("scene_field_rank")
                if detail is not None and detail.get("frame")==frame:
                    self.measurement_choice["scene_field_rank"]["rows"]=dict(detail)
        if SCENE_FIELD_SHADOW:
            shadow = getattr(self, "_scene_field_current", None)
            if shadow is not None and shadow.get("policy_frame") == frame:
                self.measurement_choice["scene_field_shadow"] = dict(shadow)
        if observed_slam.ENABLED:
            audit = getattr(self.planner, 'observed_slam_audit', None)
            # self.raw is a frame-indexed history, not the current STATE.
            # The policy frame and the forecast origin may legitimately differ.
            if audit is not None and origin_frame is not None and audit['origin_frame'] == origin_frame:
                evidence = dict(audit)
                evidence['status'] = 'captured'
            else:
                evidence = {'schema': 1, 'origin_frame': origin_frame,
                            'status': 'no_current_planner_context', 'seen_status': 'unknown_no_current_context',
                            'seen_evaluations': None,
                            'previous_context_frame': None if audit is None else audit['origin_frame']}
            evidence['policy_frame'] = frame
            evidence['captured_at'] = 'choice_before_send'
            evidence['motion_after'] = observed_slam.motion_snapshot(getattr(getattr(self, 'v2feed', None), 'trk', None))
            self.measurement_choice['observed_slam'] = evidence

    def _m2_take(self) -> None:
        """M4c: map2 takes the keys - the scripts' runs end (aborted, as when the supervisor takes them), so they start
        afresh when the keys come back."""
        for sc in (self.slam_play, self.claw, self.cast_stab, self.rune_lowhop, self.evade_chase):
            if sc is not None and sc.active():
                sc.abort("map2")
                self.counts["map2_aborted"] += 1

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
        if self.m2 is not None:
            self.m2.yield_sup(f, fo)             # M4c: the pause machine has the keys: map2 drops its plan
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
        self._measure_choice("sup", mask, frame=f, origin_frame=fo)
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
        if self.m2 is not None and self._m2_final is not None:
            rec["final"] = list(self._m2_final)  # M4c: who sent the keys (map2 / the fallback's owner) and the mask
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
                **({"slam_play": self.slam_play.stats()} if self.slam_play is not None else {}),
                **({"cast_stab": self.cast_stab.stats()} if self.cast_stab is not None else {}),
                **({"claw_chase": self.claw.stats()} if self.claw is not None else {}),
                **({"evade_chase": self.evade_chase.stats()} if self.evade_chase is not None else {}),
                **({"rune_lowhop": self.rune_lowhop.stats()} if self.rune_lowhop is not None else {}),
                **({"two_play": self.two.stats()} if self.two is not None else {}),
                **({"air_show": self.air_show.stats()} if self.air_show is not None else {}),
                **({"map2": self.m2.stats()} if self.m2 is not None else {}),
                # task oldwin stage L2: the press path's live trace (its snapshots, verdicts, commits / refusals, the
                # bridge / Press ticks with their phases, the ends) and counters - only with SSBOT_FORUM_WINDOWS_PRESS=1
                **({"win_press": self.wpress.trace_dict()} if self.wpress is not None else {}),
                **({"slam_runs": self.slam_play.runs_rec()} if self.slam_play is not None else {}),
                **({"slam_holds": self.slam_play.holds} if self.slam_play is not None and self.slam_play.holds
                   else {}),
                **({"chain_native": self.chain_native.summary()} if self.chain_native is not None else {}),
                "own_trace": self.own_trace}
