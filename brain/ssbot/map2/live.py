"""Map v2 stage M4c: THE SEARCH PLAYED LIVE - SSBOT_FORUM_MAP2 (default off; HANDOFF 'Task map2 - stage M4' / 'M4c',
forum.md 97). The policy (ForumPlannerPolicy) imports this module only when the switch is on; with it off nothing here
runs and the bot's decisions stay bit-identical. With it on SSBOT_FORUM_HERO2 must be on too (the search's hero model).

THE PARTS
- WORKERS (worker_main): their own processes (parts=N, default 2: M4b's split search, Searcher.part = (i, N)), boosted
  (High, EcoQoS off; never Idle) on the E-cores by default (LiveCfg.cpus: on the P-cores they slowed the bot's own
  tick by 4 - 6 ms p50 in the smoke), numba on 2 threads. A worker raises a shared idle flag while it waits; the bot
  sends it the NEWEST snapshot then (a reader thread keeps the newest), so each search starts from the newest observed
  state (the background refresh: a free worker gets the next one) and runs Searcher.decide from it with
  the snapshot's PREFIX - the keys on their way to the game and the BRIDGE the bot expects to play while the search
  runs (the plan in control's own keys, or the fallback planner's plan), passed through the oracle's hold filter
  (kinematics.hold_filter: the search's masks are LATCHED masks) - and the plan in control re-anchored as the kept
  plan (the hysteresis). A safe plan that is not the noop goes back as a LivePlan: anchored at the snapshot's frame,
  per safe outcome its command timeline (the Clawline key with the direction for CLAW_PRESS_F frames from its press, as
  the M0 / M4a probes pressed it; nothing in its block), its planned positions, the Clappers' records (TickCheck's),
  its danger geometry and the strike targets' robust boxes over its committed part. A search is cut (abort) when the
  bot reports her hit or another plan in control (its prefix is gone).
- THE CONTROLLER (Map2Controller, on the bot's thread): ForumPlannerPolicy.act calls pre() before the planner (the
  keys map2 sends this tick, or None: the fallback's) and post() after the keys are chosen (the snapshot to the
  workers, the per-tick log). Per tick:
  1. COMMIT: a received plan is RE-ANCHORED to now (its frames already played dropped) and committed only after THE
     EXACT HERO2 SIMULATION CHECK FROM THE CURRENT STATE (commit_check): her observed kin state now, the keys in
     flight and the plan's commands through the hold filter, simulated with the strike module (simulate) in every
     outcome consistent with the Clappers seen now; each such outcome must stay within tol_commit of its planned path
     and touch none of its danger (its geometry, the margins on) up to the end of its committed part. A failed check
     drops the plan (logged with the reason); a plan older than `stale` frames is dropped unchecked.
  2. EXECUTE: the committed plan's command for the frame being chosen (f + 2), taken from the most probable outcome
     consistent with the observation (TickCheck's rule: every Clapper's state, its frame in it within tol_j, its x
     within tol_x, its facing; her position within tol_hero of the path re-simulated at the commit) whose committed
     part reaches that frame - so the contingent continuation after a hook and the hook variant's control are picked
     from what she sees. No consistent outcome (the check failed) or none reaching the frame (the committed part's
     end) -> the plan is dropped and the FALLBACK (the w7 / w13 default planner and its scripts) has the keys again;
     her freeze (hit-stop), her own hit and the supervisor's keys drop it too.
  3. HANDOVER: while map2 has the keys the scripts are not stepped (their runs are aborted on the tick it takes them);
     the planner keeps planning every tick from the keys actually sent (its prefix and the hold filter's state), so
     when map2 drops the plan the fallback continues from the real key state - held keys held or released as its
     plan wants, a press in flight not lost, no press repeated (the filter's edges). map2 takes the keys back when a
     new plan passes its commit check.
  4. TRIGGERS (branch points) in the snapshot: a Clapper's new state (its move choice revealed), a hit (hers: the
     search is cut; on a Clapper), the plan in control near its committed end (end_lead) or dropped.
  5. LOG (map2_i<N>.jsonl beside the decisions, one row per tick): who controls and why, the plan id, its age and the
     search's latency, the planned vs observed hero position and Clappers (state, frame in it, x) of the best
     consistent outcome, the commit checks with their reasons, the worker messages.

M4D (the review findings; HANDOFF 'M4d', forum.md 98; LiveCfg switches views_exact / ctl_check / dis_hold /
unsafe_drop, on by default):
- POSSIBLE OUTCOMES: the spread match (_clappers_ok) cannot tell a branch's two timing views apart; an outcome whose
  OWN timeline (its view's records) or whose Clawline control (her accepting input) the observation contradicts is no
  longer a possible truth (possible(); sticky for the plan in control; none left: all consistent ones). The plan ENDS
  when a possible outcome's committed part has ended (M3: it deviates at reveal + lag, a collision follows) - the
  commit check rejects it then ('ended'); possible outcomes disagreeing on a key: the agreed bits, the rest as sent
  for the frame before (no press none of them is sure of); the bridge is their agreed keys.
- the Clawline latched at its press P with her facing toward the target (the realizer moves the press later until it
  is; the commit check rejects 'claw latch'), a Clawline press the plan does not have ('unplanned Clawline', 'in a
  Clawline'), no commit while she has no control;
- a freeze / slow-time / long frame or her hit on a skipped tick drops the plan (hits counted by who had the keys);
  a newer search that found the plan in control unsafe drops it (or cuts it after its bridge when that is safe);
- the Cogfly throw's keys out of the model's keys; the bot side never raises (pre / post / feed fall back); the
  stats per episode; the workers exit with the bot, the bot's exit never waits on a worker's queue, the background
  pass thread's numba threads.

M4D2 (the map in control and the reveal latency; HANDOFF 'M4d2', forum.md 99; LiveCfg switches, on by default - all
off is M4d):
- THE FALLBACK FOLLOWS ITS BRIDGE (fb_hold): while a search from the planner's bridge runs (a part not answered, or
  its plan received and not decided), hold_row() gives the planner that bridge as its CONTINUE row; ForumPlanner
  ranks it first among its safe rows (below every safety key) and envelopes it first, so it is left only when the
  planner's own checks need a change - then the search is cut (a note with 'cut': break_cut). After a drop on the
  Clappers / her position / its end the dropped plan's bridge is held the same way and its searches go on
  (drop_keep; a kept answer comes back as a plan), or restarted at once with the short bridge (drop_rev).
- ONE DECISION, TWO PARTS (sync): a snapshot only when every worker is idle, the same one to each; a received plan
  waits for the other part (and its own better anytime plans) until its root (wait_parts); the search's cap is the
  frames to its root less dl_margin and the time already gone (deadline); the first safe plan and each one better
  by w_switch go out at once (first_send: final=False).
- MORE PLANS COMMITTED: a strike pressed right after the bridge is not 'too short' (short_fix); the noop (the bridge,
  then stop) loses to the best safe non-noop plan within alt_slack when map2 has no plan or its plan is ending
  (alt_noop); a plan whose bridge was not followed is REPAIRED from the keys actually sent (repair; repair_check in
  the strict replay); 'no input' in the umbrella / the sprint (the hero model's states) does not block a commit or a
  search (noinput_kin); a search that found nothing safe is followed by one with the short bridge (unsafe_short).
- THE REVEAL (rev_cut): a Clapper's move start (the antic's first frame) cuts the searches from before it and sends
  the newest snapshot to every worker at once with a bridge of rev_lead frames.
- THE REPLAY ONLY: replay_push (a Clapper the recording's hero just hit matched with a wider x); audit_runs (each
  control run's keys as sent re-simulated in the outcomes still possible: the safety audit).

M4 S1 (the safety fixes before the w7 gate; HANDOFF 'S1', forum.md 100; LiveCfg switches, on by default - all off
with SSBOT_FORUM_HERO2_OFF=1536 is M4d2):
- PRESS VALIDITY (press_check; ssbot.map2.press): a strike is credited only when her kin state starts it - the
  search's realizer keeps the witness's held jump / dash on a down slash's press frame (or holds down through the air
  sprint's Attack Cancel) or rejects the witness, simulate credits a down slash only where kin starts one and a
  Clawline only where env_jit.claw_allowed's rule holds (else the plan cannot be played: a forced collision); the
  snapshot carries the last Clawline's control (its lock, control + 13). The commit check, the repair, the audit and
  every outcome the bot executes come from simulate.
- THE LOW SIDE DOWN SLASH OUT OF THE AIR SPRINT (side_spr): a side contact of a slash out of the air dash / sprint is
  the body's contact (a forced collision), not a pogo.
- THE AIR DASH AFTER A POGO (HERO2 H2_POGO_DASH, kinematics / kin_jit): restored at a pogo bounce / a hooked control.
- THE LATE TICK (late_check): frames whose tick was skipped keep the previous ACTION's keys; when one of them is not
  the plan in control's own key there (its press / release slipped), the plan is re-checked from the keys actually
  sent (late_check: her anchor state, every key sent, the plan's own commands after; its down slash presses where the
  keys latch them) before it goes on, and dropped ('late') when the slip makes it unsafe.

Frames: STATE frames (the oracle applies a tick's keys at f + 2); a plan's frame 0 is its snapshot's observation frame
(its anchor), its command index k applies to frame anchor + k. u: world units, her transform (kin pos).
"""
from __future__ import annotations

import json
import math
import os
import queue
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np
from numba import njit

from ssbot.knowledge import kinematics as km
from ssbot.map2 import brnum
from ssbot.map2 import clapper as cm
from ssbot.map2 import press
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

MAP2_ENV = "SSBOT_FORUM_MAP2"
SET_ENV = "SSBOT_FORUM_MAP2_SET"
M_CLAW = 1 << 4                    # the Clawline button (ssbot.ipc.framing BUTTONS order; combat.claw_strike.M_CLAW)
M_DS = km.B_DOWN | km.B_ATTACK
COG = km.B_UP | km.B_QUICKCAST     # the Cogfly throw's keys (forum_planner_policy.COG: not the kinematics')
_COG_BITS = tuple(b for b in range(22) if (COG >> b) & 1)
CLAW_PRESS_F = 3                   # the Clawline key and the direction held this many frames from P (the probes')
DS_WIN = sk.DS_ACTIVE[1] + 1       # a slash's contact can still come this many frames after its press
CLAW_BLOCK_F = 36                  # a Clawline pressed this recently: she may still be in its block (control P + 34)
CTRL_SETTLE = 2                    # frames after a Clawline's control still treated as its block (the forced bounce)
# M4d2 (LiveCfg.noinput_kin): her clips whose 'no input' frames the hero model covers (HERO2: the umbrella's antic /
# inflate / float / deflate / turn, the air dash's sprint and its cancels, the ground sprint's turn and skid)
KIN_CLIPS = frozenset(("Umbrella Inflate Antic", "Umbrella Inflate", "Umbrella Float", "Umbrella Deflate",
                       "Umbrella Turn", "Sprint", "Sprint Air", "Sprint Air Short", "Sprint Turn", "Skid End 1",
                       "Skid End 2"))
VARIANTS = {v.name: v for v in sk.HOOK_VARIANTS}


def enabled() -> bool:
    return os.environ.get(MAP2_ENV, "0").strip() == "1"


@dataclass
class LiveCfg:
    parts: int = 2                 # search worker processes per game instance (M4b's split search)
    prio: str = "high"             # the workers' priority: high (the live bot's rule) / as (as started: tests)
    cpus: str = "16-31"            # the workers' CPUs: the 13900K's E-cores (High, EcoQoS off) - on the P-cores (the
    #                                live bot's rule, 0-15) two workers per instance slowed the bot's own tick by 4 - 6 ms
    #                                p50 (the M4c smoke: 2 replays at a time), here ~1 ms with the same plans
    numba_threads: int = 2         # the workers' numba threads (the parallel envelope pass); the bot keeps its own
    cap_fb: float = 0.25           # the search's cap (s) while the fallback has the keys
    cap_ch: float = 0.6            # ... while map2 has them (the chained search, anchored after its bridge)
    cap_min: float = 0.12
    fb_lead: int = 16              # the bridge's frames from the fallback planner's own plan
    ch_lead: int = 40              # the bridge's frames from the plan in control
    sc_lead: int = 8               # ... while a script of the fallback has the keys: its key now held (a guess)
    min_frames: int = 4            # a plan this short past its prefix is not sent
    tol_hero: float = 0.2          # TickCheck's tolerances (M4b's guesses; calibrate live)
    tol_x: float = 0.35
    tol_j: int = 1
    tol_commit: float = 0.2        # the commit re-simulation against the planned path (u)
    tol_reanchor: float = 0.5      # ... when the plan in control is re-anchored after her position left its path (the
    #                                Clappers still consistent): the collision check stays exact
    stale: int = 45                # a received plan older than this (frames since its anchor) is dropped
    end_lead: int = 20             # the 'end' trigger: the plan in control has this few committed frames left
    carry_f: int = 40              # a worker's last sent plan (not taken) is its next search's kept plan while it is this
    #                                young (frames): re-checked exactly from the newer snapshot and sent again when it
    #                                still wins - its anchor nearer the commit (the fallback's bridge rarely holds 10 f)
    commits_per_tick: int = 2      # commit checks per tick at most (the rest wait)
    mem_gb: float = 6.0            # a worker above this RSS exits after its search (the controller restarts it)
    hang_s: float = 3.0            # a search running this long: the worker reports its stack (and dumps the snapshot)
    dump_dir: str = ""             # where a hung search's snapshot is pickled ('': not)
    ready_s: float = 900.0         # the workers' start-up wait (a fresh checkout compiles the search: minutes)
    warm_rec: int = 6              # recorded situations searched in a worker's warm-up (the compiled paths)
    replay: bool = False           # an offline replay: her position is the recording's, not her keys' result - the
    #                                hero tolerances are logged, not enforced
    replay_strict: bool = False    # ... and a received plan is committed only when the keys sent since its anchor are
    #                                its prefix (in flight + bridge): the live path check's proxy in a replay
    # M4d (the review findings; on by default, a switch each to compare with M4c's rule)
    views_exact: bool = True       # an outcome whose OWN timeline (its timing view's records) the observation contradicts
    #                                is no longer a possible truth; the plan ENDS when any possible outcome's committed
    #                                part has ended (M3's deviation at reveal + lag) - none possible (a timing between
    #                                the views): all consistent ones count. Off: M4c (the most probable alive one's keys)
    ctl_check: bool = True         # her accepting input against each outcome's Clawline control (the hook variant seen)
    dis_hold: bool = True          # possible outcomes disagreeing on a key: the bits they agree on, the others as sent
    #                                for the frame before (no press nobody planned); the bridge stops there
    unsafe_drop: bool = True       # a newer search that evaluated the plan in control (kept plan) unsafe: dropped, or
    #                                cut after its bridge when the search's noop (the bridge, then stop) was safe
    dev_gap: int = 6               # a 'dev' outcome (its committed part ends at a deviation: a collision follows) must
    #                                leave the fallback this many frames from that end to the collision, else the plan
    #                                is not committed ('dev gap'; M3 accepts 0 - the commit check caught only a collision
    #                                AT the deviation frame); 0: M4c
    dt_lo: float = 0.9             # a STATE frame with dt x 60 outside dt_lo .. dt_hi (a hit-stop freeze, its slow-time
    dt_hi: float = 1.25            # ramp, a long frame) counts as a freeze: the plan in control is dropped
    err_max: int = 20              # errors on the bot's side in one episode: map2 off for the rest of it
    # M4d2 (the map in control and the reveal latency; on by default, a switch each - all off: M4d)
    fb_hold: bool = True           # the fallback FOLLOWS the bridge it sent while a search from it runs: the planner's
    #                                CONTINUE row is that bridge, first among its safe rows (only its own safety check
    #                                changes it); a key off a pending search's bridge cuts that search (M4d: the planner
    #                                re-planned every tick, 15 - 17 % of its 16-frame bridges were followed on w7)
    break_cut: bool = True         # a pending search whose bridge the keys left is cut (its plan could only be repaired)
    sync: bool = True              # a snapshot goes to every worker at once (the parts of one decision: M4b's split
    #                                search; M4d sent each idle worker its own snapshot - half a search each)
    wait_parts: bool = True        # a received plan waits for its decision's other parts until its root is near
    short_fix: bool = True         # a plan with a press after its prefix is never 'too short' (min_frames dropped
    #                                strikes pressed 1 - 3 frames after the bridge as 'noop')
    alt_noop: bool = True          # the search's best is the noop (with no plan in control) or the plan in control kept
    #                                near its end (left <= alt_left): its best safe non-noop plan within alt_slack of
    #                                that value is sent ('alt') - the noop is the fallback's bridge, then stop
    alt_slack: float = 0.3
    alt_left: int = 24
    deadline: bool = True          # the search's cap: the frames to its plan's root (the first own key) less dl_margin,
    dl_margin: int = 3             # less the wall time since the snapshot (M4d: (lead - 2) / 60, the queue's delay not
    cap_lo: float = 0.04           # counted); at least cap_lo
    first_send: bool = True        # anytime: the search's first safe plan goes to the bot at once, each one better by
    #                                w_switch after it; the bot commits the best by its root (wait_parts)
    rev_cut: bool = True           # a Clapper's MOVE START (the antic's first frame: the reveal of its choice) cuts the
    #                                searches from before it and the newest snapshot goes to every worker at once
    rev_lead: int = 6              # ... with a bridge of this many frames (the search rooted near now)
    rev_wait: int = 12             # a reveal not sent within this many frames (no search possible: busy) is dropped
    repair: bool = True            # a received plan whose bridge was NOT followed is REPAIRED instead of dropped: its own
    #                                commands after the keys actually sent, re-simulated from her state (live: observed
    #                                now; the strict replay: the plan's anchor state with the keys sent since), every
    #                                possible outcome within tol_repair of its planned path, collisions exact, no press
    #                                it does not have
    tol_repair: float = 0.3
    search_lag: int = 0            # the search's reaction lag after a reveal (Cfg.lag; 0: its own, 2 - M3: re-planning
    #                                at once): a plan's committed part ends there in an outcome that must deviate
    unsafe_short: bool = True      # a search that found nothing safe (the bridge itself unsafe by the map) is followed by
    #                                one from the newest snapshot with the short bridge (rev_lead)
    drop_rev: bool = True          # a plan dropped on the Clappers / her position restarts the search at once from the
    #                                newest snapshot with the short bridge (as a move start: rev_cut)
    noinput_kin: bool = True       # her 'no input' frames in the umbrella / the sprint / a skid (clips KIN_CLIPS: the
    #                                hero model's own states - M0 / M4a; the keys still act there: the cancels) count as
    #                                control for the commit and the search's start (M4d: no commit, no search); a
    #                                Clawline, the roar lock, a stun stay 'no input'
    replay_push: bool = True       # the REPLAY only (cfg.replay): a Clapper the recording's hero just hit (its HP fell
    push_tol: float = 0.55         # within push_f frames) is matched with its x within tol_x + push_tol - the
    push_f: int = 20               # recording's side slashes push it 0.36 - 0.48 u (clapper.RECOIL_*), map2's plans
    #                                (down slashes, the Clawline) do not; live this never acts
    drop_keep: bool = True         # a plan dropped on the Clappers / her position / its end: the searches from its bridge
    #                                go on (not cut), the fallback holds that bridge (fb_hold: its own check permitting)
    #                                and a search that kept the dropped plan sends it back (re-checked at the commit)
    audit_runs: bool = False       # (the smoke's safety audit) each control run's keys as sent, re-simulated from its
    #                                commit state in every outcome still possible at its end, against that outcome's
    #                                danger to the run's last frame (audit_run); off: nothing
    # M4 S1 (the safety fixes; on by default, a switch each - all off with SSBOT_FORUM_HERO2_OFF=1536: M4d2)
    press_check: bool = True       # a strike credited only when the kin state starts it (ssbot.map2.press.ON: the
    #                                realizer, simulate, the commit check); the last Clawline's lock in the snapshot
    side_spr: bool = True          # a side contact of a slash out of the air sprint is the body's (press.SIDE)
    late_check: bool = True        # a skipped tick slipped a key of the plan in control: re-checked from the keys
    tol_late: float = 0.5          # actually sent (late_check; the path from now within tol_late), dropped if unsafe
    plan_dump: str = ""            # a directory: every plan a worker sends pickled there (the press scan); '': not
    # M4 S1b (the verifiers' findings on S1; on by default - each at its S1 value gives S1's behaviour)
    free_pogo: int = 12            # press.FREE_POGO: a press only kin's downspike lock holds, credited this many frames
    #                                after a pogo's onset (the game's recovery 9 - 11 f); after a hooked Clawline's forced
    #                                bounce press.FREE_MIN (its recovery 1 f) - S1: 10 for both
    ds_shrink: float = 0.05        # press.SHRINK: a down slash contact meets the body box shrunk by this (u); S1: 0
    side_rule: str = "lag"         # press.SIDE_RULE ('lag' / 'top' / 'top0' = S1's) and its lead (u)
    side_lag: float = 0.5
    spr_xvx: float = 1.0           # press.XVX_MIN: 'out of the sprint' by the retained extra velocity from |XVX| (u/s);
    #                                S1: 0 (any non-zero - 40 frames of residue after a cancel)
    late_base: bool = True         # the late check re-simulates from the commit's own state (her observed one and the
    #                                keys sent since - where the commit / repair / re-anchoring checked the plan; the
    #                                strict replay: the anchor, its proxy world, as its audit), the Cogfly keys stripped
    #                                (S1: the anchor, the keys from it, as sent)
    log: bool = True

    @classmethod
    def from_env(cls, **kw) -> "LiveCfg":
        """SSBOT_FORUM_MAP2_SET="parts=1,cap_fb=0.3,..." overrides the defaults."""
        d: dict = {}
        types = {f.name: f.type for f in fields(cls)}
        for item in filter(None, (x.strip() for x in os.environ.get(SET_ENV, "").split(","))):
            k, _, v = item.partition("=")
            k = k.strip()
            if k not in types:
                raise ValueError(f"{SET_ENV}: unknown key {k!r} ({sorted(types)})")
            t = str(types[k])
            d[k] = (v.strip() in ("1", "true", "True")) if t == "bool" else int(v) if t == "int" else \
                float(v) if t == "float" else v.strip()
        d.update(kw)
        return cls(**d)

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def set_switches(cfg: LiveCfg) -> None:
    """M4 S1: the search's module switches from the configuration (the workers and the bot's thread: the commit
    check simulates too)."""
    press.ON[0] = bool(cfg.press_check)
    press.SIDE[0] = bool(cfg.side_spr)
    press.FREE_POGO[0] = int(cfg.free_pogo)          # M4 S1b
    press.SHRINK[0] = float(cfg.ds_shrink)
    press.SIDE_RULE[0] = str(cfg.side_rule)
    press.SIDE_LAG[0] = float(cfg.side_lag)
    press.XVX_MIN[0] = float(cfg.spr_xvx)


# ---- the oracle's hold filter, one lane (kinematics.hold_filter, compiled) ------------------------------------------

@njit(cache=True)
def _hf1(cmds, lat0, des0, pen0, age0, min_press, min_release, max_pending, age_long):
    T = cmds.shape[0]
    nb = lat0.shape[0]
    lat = lat0.copy()
    des = des0.copy()
    pen = pen0.copy()
    age = age0.copy()
    out = np.zeros(T, np.int64)
    nxt = np.zeros(nb, np.bool_)
    prs = np.zeros(nb, np.bool_)
    for t in range(T):
        m = cmds[t]
        for b in range(nb):
            w = ((m >> b) & 1) == 1
            if w != des[b]:
                pen[b] += 1
            des[b] = w
            if pen[b] > max_pending:
                pen[b] -= 2
            has = pen[b] > 0
            r = has and lat[b] and age[b] >= min_press
            p = has and (not lat[b]) and age[b] >= min_release
            nxt[b] = lat[b]
            if r:
                nxt[b] = False
            if p:
                nxt[b] = True
            prs[b] = p
            if r or p:
                pen[b] -= 1
        both = nxt[20] and nxt[21]
        for b in (20, 21):
            if both and prs[b]:
                nxt[b] = False
                pen[b] += 1
                if not des[b]:
                    pen[b] = 0
        v = 0
        for b in range(nb):
            if nxt[b] != lat[b]:
                age[b] = 1
            else:
                age[b] = min(age[b] + 1, age_long)
            lat[b] = nxt[b]
            if lat[b]:
                v |= 1 << b
        out[t] = v
    return out, lat, des, pen, age


def hold_filter1(cmds, hold: tuple) -> np.ndarray:
    """kinematics.hold_filter for one lane from a hold tuple (latched, desired, pending, age: [22] each): the latched
    masks of the commands."""
    c = np.ascontiguousarray(np.asarray(cmds, np.int64).reshape(-1))
    if not len(c):
        return np.zeros(0, np.int64)
    lat, des, pen, age = hold
    out, *_ = _hf1(c, np.asarray(lat, np.bool_), np.asarray(des, np.bool_), np.asarray(pen, np.int64),
                   np.asarray(age, np.int64), 2, 2, 3, km._AGE_LONG)
    return out


def hold_run(cmds, hold: tuple) -> tuple:
    """(latched masks, the filter's state after them) for one lane's commands from a hold tuple."""
    c = np.ascontiguousarray(np.asarray(cmds, np.int64).reshape(-1))
    lat, des, pen, age = hold
    if not len(c):
        return np.zeros(0, np.int64), hold
    out, l2, d2, p2, a2 = _hf1(c, np.asarray(lat, np.bool_), np.asarray(des, np.bool_), np.asarray(pen, np.int64),
                               np.asarray(age, np.int64), 2, 2, 3, km._AGE_LONG)
    return out, (l2, d2, p2, a2)


def _press_at(lat: np.ndarray, i: int, prev: int, look: int = 2) -> int:
    """The frame (index) of the latched down slash press for one commanded at i: the first rising attack with down
    in i .. i + look; -1 when the filter takes it away."""
    for j in range(i, min(i + look + 1, len(lat))):
        m = int(lat[j])
        pm = int(lat[j - 1]) if j > 0 else int(prev)
        if _rising(m, pm, km.B_ATTACK):
            return j if (m & M_DS) == M_DS else -1
    return -1


class HoldRealizer:
    """A plan as the oracle's hold filter latches it (Searcher.realizer in the live worker): the search's masks
    (M1's witness keys, kin_jit's latched masks) may press or release a key for one frame, which the filter cannot
    latch (a press lasts >= 2 frames, a release too): every plan is turned into what the game will receive before it
    is evaluated. The first n_pre masks (the prefix: already the latched result of the bot's commands) are kept; the
    rest of the first segment goes through the filter as commands from its state after the prefix; a segment after a
    Clawline (and its per-variant / per-reaction alternatives) from the filter's state after the press (the key for
    CLAW_PRESS_F frames) and a block of no key; a down slash press moves to its latched press frame (dropped when the
    filter takes the press away: the strike is then not in the plan)."""

    def __init__(self, n_pre: int, hold_after: tuple, face0: int | None = None):
        self.n_pre, self.hold = int(n_pre), hold_after
        self.face0 = None if face0 is None else (1 if face0 >= 0 else -1)   # her facing at the plan's start
        self.n_moved = 0
        self.n_dropped = 0
        self.n_claw_shift = 0              # M4d: Clawline presses moved later so she faces the target at P
        self.n_claw_bad = 0                # ... none of the shifts does it (the commit check rejects the plan)

    @staticmethod
    def _run(m: np.ndarray, h: tuple, base: int) -> tuple:
        if base > 0:
            head = m[:base]
            tail, h2 = hold_run(m[base:], h)
            lat = np.concatenate([head, tail]).astype(np.int64)
            prev = int(head[-1]) if len(head) else 0
        else:
            lat, h2 = hold_run(m, h)
            prev = 0
        return lat, prev, h2

    def _claw(self, m: np.ndarray, d: int, h: tuple, base: int, face) -> tuple:
        """M4d: a Clawline segment as it is sent (outcome_cmds: the key with the direction from its P, the segment's
        last mask frame) and latched: the game throws the Clawline toward her FACING at P (strike.facing_track: the
        last direction key latched), so at P the Clawline must latch (a rising edge) with her facing toward the
        target - the direction latched with it, or none and she already faced it (face: her facing at the segment's
        start; None: unknown - the direction must latch). M4c modelled the keys from P + 1 and sent them from P: a tap
        of the other direction at P - 1 stayed latched at P (its minimum press) - the throw went the other way. When it
        cannot be so at P the press moves j frames later with the direction alone first (j <= 3); the evaluation then
        decides from the actual press frame. (latched masks to the press, prev, state after the press and the block)."""
        dk, opp = _claw_dirs(d)
        body = m[:-1]
        lat_b, prev, hb = self._run(body, h, min(base, len(body)))
        pm0 = int(lat_b[-1]) if len(lat_b) else prev
        fb = None if face is None else int(sk.facing_track(face, lat_b)[-1])
        for j in range(4):
            cmds = np.array([dk] * j + [M_CLAW | dk] * CLAW_PRESS_F + [0] * 22, np.int64)
            out, h2 = hold_run(cmds, hb)
            mp = int(out[j])
            pj = int(out[j - 1]) if j > 0 else pm0
            if fb is None:
                faces = bool(mp & dk) and not (mp & opp)
            else:
                faces = int(sk.facing_track(fb, out[:j + 1])[-1]) == (1 if d > 0 else -1)
            if (mp & M_CLAW) and not (pj & M_CLAW) and faces:
                if j:
                    self.n_claw_shift += 1
                break
        else:
            self.n_claw_bad += 1
        lat = np.concatenate([lat_b, (out[:j + 1] & ~M_CLAW)]).astype(np.int64)
        return lat, prev, h2

    def _seg(self, s, h: tuple, base: int, face) -> tuple:
        m = np.asarray(s.masks, np.int64)
        if s.claw is not None and len(m):
            lat, prev, h2 = self._claw(m, int(s.claw[0]), h, base, face)
        else:
            lat, prev, h2 = self._run(m, h, base)
        dsl = []
        for (i, iid) in s.dsl:
            if i < base:
                dsl.append((i, iid))
                continue
            j = _press_at(lat, int(i), prev)
            if j < 0:
                self.n_dropped += 1
                continue
            if j != i:
                self.n_moved += 1
            dsl.append((j, iid))
        return lat, dsl, h2

    def _chain(self, segs: list, h: tuple, base0: int, face) -> list:
        out = []
        for si, s in enumerate(segs):
            lat, dsl, h2 = self._seg(s, h, base0 if si == 0 else 0, face)
            var_alt = None if s.var_alt is None else {k: self._chain([v], h, 0, face)[0]
                                                      for k, v in s.var_alt.items()}
            out_alt = None if s.out_alt is None else {k: self._chain(v, h, 0, face) for k, v in s.out_alt.items()}
            out.append(ms.Seg(lat, dsl, s.claw, s.tag, var_alt, out_alt))
            h = h2
            if s.claw is not None:
                face = 1 if s.claw[0] > 0 else -1          # after a hook she faces its direction (simulate)
        return out

    def __call__(self, plan):
        return ms.Plan(self._chain(list(plan.segs), self.hold, self.n_pre, self.face0), plan.origin, plan.note)


def hold_tuple(hold: km.HoldState) -> tuple:
    return (hold.latched[0].copy(), hold.desired[0].copy(), hold.pending[0].copy(), hold.age[0].copy())


def _rising(m: int, pm: int, bit: int) -> bool:
    return bool(m & bit) and not bool(pm & bit)


# ---- a plan as the bot executes it --------------------------------------------------------------------------------

def outcome_cmds(tr) -> np.ndarray:
    """The outcome's COMMANDS per frame 0 .. tr.end (index 0 unused): its played segments' masks at their frames, a
    Clawline's key with the direction for CLAW_PRESS_F frames from its press P (the segment's last mask frame), no key
    in the block until the next segment (its control)."""
    end = int(tr.end)
    c = np.zeros(end + 1, np.int64)
    for seg, k0 in zip(getattr(tr, "segs", ()), tr.seg_start):
        m = np.asarray(seg.masks, np.int64)
        hi = min(int(k0) + len(m), end)
        if hi > k0:
            c[int(k0) + 1:hi + 1] = m[:hi - int(k0)]
        if seg.claw is not None:
            P = int(k0) + len(m)
            dk = km.B_RIGHT if seg.claw[0] > 0 else km.B_LEFT
            for j in range(CLAW_PRESS_F):
                if P + j <= end:
                    c[P + j] = M_CLAW | dk
    return c


class OutData:
    """One safe outcome of a sent plan (frames from the anchor): p, kc (its committed part's end: the reveal + lag of a
    later collision, else its end), end, cmds (outcome_cmds), pos [kc + 1, 2] her planned transform, recs / sids
    (TickCheck's records of the Clappers to kc), segs [(start frame, masks, dsl, claw)] as played, presses [(frame,
    iid)], variant, boxes {iid: robust body rows} (the strikes' targets), geo (off, BX, IIDB, coff, CO to kc), rare
    {k: grown shapes} (the hammers), rare_k, label; M4d: why ('dev': its committed part ends at a deviation because a
    collision follows), kcol (that collision's frame), ctrls [(P, control)] of its hooked / unhooked Clawlines whose
    control is known (her accepting input from control on: the hook variant seen live); M4 S1b: tops {iid: the
    highest body top per frame} (strike.union_tops: the side rule's; unset in older plans - the robust top then)."""
    __slots__ = ("p", "kc", "end", "cmds", "pos", "recs", "vrecs", "sids", "segs", "presses", "variant", "boxes", "geo",
                 "rare", "rare_k", "label", "contacts", "blocks", "why", "kcol", "ctrls", "tops")

    def in_block(self, n: int) -> bool:
        """Frame n inside a Clawline's block (its press .. control + CTRL_SETTLE: no control, the forced bounce's
        first frames) - her position is the pull's, not her keys'."""
        return any(P < n <= c + CTRL_SETTLE for (P, c) in self.blocks)


def _geo_cut(br, kc: int, margins: bool) -> tuple:
    g = ms.geo(br, margins)
    n = min(kc + 2, len(g.off))
    off = g.off[:n].copy()
    BX, IIDB = g.BX[:int(off[-1])].copy(), g.IIDB[:int(off[-1])].copy()
    nc = min(kc + 2, len(g.coff))
    coff = g.coff[:nc].copy()
    CO = g.CO[:int(coff[-1])].copy() if len(coff) else np.zeros((0, 3))
    rare = {}
    for k in g.rare_k:
        if int(k) <= kc:
            rare[int(k)] = list(g.rare_grown(br, int(k), margins))
    return (off, BX, IIDB, coff, CO), rare


def build_outs(ev, margins: bool = True) -> list:
    outs = []
    gcache: dict = {}
    sid_of: dict = {}
    for o in ev.outcomes:
        if not o.safe:
            continue
        tr = o.tr
        kc = int(getattr(o, "k_end", tr.end))
        d = OutData()
        d.p, d.kc, d.end = float(o.p), kc, int(tr.end)
        d.cmds = outcome_cmds(tr)
        d.pos = np.asarray(tr.pos[:kc + 1], float).copy()
        arr, tb = brnum.barr(o.branch)
        vrecs = {}
        for iid, a in arr.items():
            a = a[(a[:, 0] >= 0) & (a[:, 0] <= kc)]
            a = a[np.argsort(a[:, 0], kind="stable")]
            vrecs[iid] = (a[:, 0].astype(np.int64), a[:, 3].astype(np.int64), a[:, 4], a[:, 5], a[:, 7])
        d.vrecs = vrecs
        # the matching uses the branch the timing view was drawn from: a record (state, frame in it, x, facing) is
        # seen at any frame k + a .. k + b of its spread (an observed timing between the two views' extremes)
        arr0, tb0 = brnum.barr(getattr(o.branch, "_base", o.branch))
        recs = {}
        for iid, a in arr0.items():
            lo, hi = a[:, 0] + a[:, 1], a[:, 0] + a[:, 2]
            a, lo, hi = a[(hi >= 0) & (lo <= kc)], lo[(hi >= 0) & (lo <= kc)], hi[(hi >= 0) & (lo <= kc)]
            o_ = np.argsort(lo, kind="stable")
            recs[iid] = (lo[o_].astype(np.int64), hi[o_].astype(np.int64), a[o_, 3].astype(np.int64), a[o_, 4],
                         a[o_, 5], a[o_, 7])
        d.recs = recs
        if tb0 is not tb:
            assert dict(tb0.sid) == dict(tb.sid)
        d.sids = sid_of.setdefault(id(tb), dict(tb.sid))
        d.segs = [(int(k0), np.asarray(s.masks, np.int64).copy(), list(s.dsl), s.claw)
                  for s, k0 in zip(getattr(tr, "segs", ()), tr.seg_start)]
        d.presses = [(int(k0) + 1 + int(i), int(iid)) for (k0, _, dsl, _) in d.segs for (i, iid) in dsl]
        d.variant = tr.variant or sk.HOOK_VARIANTS[0].name
        tgt = {iid for (_, iid) in d.presses} | {int(c[1]) for (_, _, _, c) in d.segs if c is not None}
        d.boxes = {iid: np.asarray(sk.robust_boxes(o.branch, iid, None), float) for iid in sorted(tgt)}
        d.tops = {iid: np.asarray(sk.union_tops(o.branch, iid, None), float) for iid in sorted(tgt)}
        key = (id(o.branch), kc)
        if key not in gcache:
            gcache[key] = _geo_cut(o.branch, kc, margins)
        d.geo, d.rare = gcache[key]
        d.rare_k = np.array(sorted(d.rare), np.int64)
        d.label = o.branch.label() if hasattr(o.branch, "label") else ""
        d.contacts = [(int(k), int(i), str(kd)) for (k, i, kd) in tr.contacts]
        d.blocks = []
        d.ctrls = []
        for si, (k0, m, _, c) in enumerate(d.segs):
            if c is not None:
                P = k0 + len(m)
                d.blocks.append((P, d.segs[si + 1][0] if si + 1 < len(d.segs) else P + 34))
                if si + 1 < len(d.segs):
                    d.ctrls.append((P, d.segs[si + 1][0]))
        d.why = str(getattr(o, "why", "") or "")
        kcol = getattr(o, "k_col", None)
        d.kcol = int(kcol) if (kcol is not None and kc < tr.end) else None
        outs.append(d)
    return outs


class LivePlan:
    """A plan the worker sends (frames from the anchor t_a = its snapshot's observation frame)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def consistent(self, n: int, her_xy, obs: list, cfg: LiveCfg, idx=None, hero: bool = True,
                   pos_over: dict | None = None) -> tuple:
        """(indices of the outcomes consistent with the observation at frame n, outcomes failing on her position,
        outcomes failing on the Clappers) - TickCheck.check's rule per outcome."""
        out, bad_h, bad_c = [], 0, 0
        hx, hy = float(her_xy[0]), float(her_xy[1])
        for i in (range(len(self.outs)) if idx is None else idx):
            o = self.outs[i]
            if n < 0 or n > o.kc:
                continue
            pos = pos_over.get(i, o.pos) if pos_over else o.pos
            if n >= len(pos):
                continue
            if hero and not o.in_block(n) and (abs(pos[n, 0] - hx) > cfg.tol_hero or abs(pos[n, 1] - hy) > cfg.tol_hero):
                bad_h += 1
                continue
            if not _clappers_ok(o, n, obs, cfg):
                bad_c += 1
                continue
            out.append(i)
        return out, bad_h, bad_c


def _clappers_ok(o: OutData, n: int, obs: list, cfg: LiveCfg) -> bool:
    """TickCheck's rule with the timing spread: every observed Clapper matches a record of the outcome's branch seen
    at frame n (n inside its k + a .. k + b), its state, its frame in it within tol_j, its x within tol_x, its
    facing."""
    for ob in obs:
        r = o.recs.get(ob.iid)
        if r is None:
            continue
        lo, hi, st, j, x, f = r
        b = np.searchsorted(lo, n, side="right")
        w = hi[:b] >= n
        sid = o.sids.get(ob.st, -9)
        oj = ob.j if ob.j is not None else int(round(ob.t * 60.0))
        tx = getattr(ob, "xtol", None) or cfg.tol_x                    # (M4d2: replay_push)
        if not np.any(w & (st[:b] == sid) & (np.abs(j[:b] - oj) <= cfg.tol_j) & (np.abs(x[:b] - ob.x) <= tx) &
                      (f[:b] == ob.face)):
            return False
    return True


def _exact_ok(o: OutData, n: int, obs: list, cfg: LiveCfg) -> bool:
    """M4d: the outcome's OWN timeline at frame n (its timing view's records, M4b TickCheck's rule): every observed
    Clapper with a record at n matches one of them (state, frame in it within tol_j, x within tol_x, facing). No record
    at n: no evidence. False: this timing view is not the truth (the spread rule, _clappers_ok, cannot tell the two
    views of a branch apart)."""
    for ob in obs:
        r = o.vrecs.get(ob.iid)
        if r is None:
            continue
        ks, st, j, x, f = r
        a = int(np.searchsorted(ks, n, side="left"))
        b = int(np.searchsorted(ks, n, side="right"))
        if a == b:
            continue
        sid = o.sids.get(ob.st, -9)
        oj = ob.j if ob.j is not None else int(round(ob.t * 60.0))
        tx = getattr(ob, "xtol", None) or cfg.tol_x                    # (M4d2: replay_push)
        if not np.any((st[a:b] == sid) & (np.abs(j[a:b] - oj) <= cfg.tol_j) & (np.abs(x[a:b] - ob.x) <= tx) &
                      (f[a:b] == ob.face)):
            return False
    return True


def _control_ok(o: OutData, n: int, acc) -> bool:
    """M4d: her accepting input at frame n against the outcome's Clawline controls (the hook variant): from the press
    she has no control until control (M4a probes: 0 of 250 accepting in P + 3 .. control - 1), and has it from control
    on. False: control seen before this outcome's (n <= control - 2), or not seen after it (control + 1 .. + 3)."""
    if acc is None:
        return True
    for (P, c) in o.ctrls:
        if P + 3 <= n <= c - 2 and acc:
            return False
        if c + 1 <= n <= c + CTRL_SETTLE + 1 and not acc:
            return False
    return True


def possible(lp: "LivePlan", cons: list, n: int, obs: list, cfg: LiveCfg, acc=None, excl: set | None = None) -> list:
    """M4d: the consistent outcomes (cons) that can still be the truth - not contradicted on their own timeline
    (_exact_ok) or by her control (_control_ok) at frame n, nor before (excl: the sticky set of the plan in control,
    updated here). None left (a timing between the views, a control between the variants): all of cons."""
    if not cfg.views_exact and not cfg.ctl_check:
        return list(cons)
    out = []
    for i in cons:
        if excl is not None and i in excl:
            continue
        o = lp.outs[i]
        if (cfg.views_exact and not _exact_ok(o, n, obs, cfg)) or (cfg.ctl_check and not _control_ok(o, n, acc)):
            if excl is not None:
                excl.add(i)
            continue
        out.append(i)
    return out or list(cons)


def _merge_keys(keys: list, prev: int) -> tuple:
    """M4d: one command from the possible outcomes' commands for a frame: theirs when they agree; else the bits they
    agree on and, for the others, the bit as sent for the frame before (no press none of them is sure of: a key
    pressed in a Clawline's pull is queued to its control) - (mask, disagreeing bits)."""
    a = o_ = int(keys[0])
    for k in keys[1:]:
        a &= int(k)
        o_ |= int(k)
    dis = a ^ o_
    return (a | (dis & int(prev))), dis


def _clapper_pred(o: OutData, n: int) -> dict:
    """The outcome's Clappers at frame n: {iid: (state, frame in it, x)} (its first record of frame n)."""
    inv = {v: k for k, v in o.sids.items()}
    out = {}
    for iid, (ks, st, j, x, f) in o.vrecs.items():
        a = np.searchsorted(ks, n)
        if a < len(ks) and ks[a] == n:
            out[iid] = (inv.get(int(st[a]), "?"), int(j[a]), round(float(x[a]), 2))
    return out


# ---- re-anchoring and the exact commit check ---------------------------------------------------------------------

def reanchor_outcome(o: OutData, s: int, lat: np.ndarray, lat_s: int, move: int = 0) -> tuple:
    """The outcome's played segments from frame s on, with the LATCHED masks lat (frames s + 1 .. s + len(lat)); its
    down slash presses kept where the latched masks press them (a rising attack with down); lat_s: the latched mask at
    frame s. M4 S1 move > 0 (the late check): a press the keys latch up to `move` frames later is moved there (one
    they do not latch is left out: that strike is not played). (Plan, '') or (None, why)."""
    segs = []
    first = True
    for si, (k0, masks, dsl, claw) in enumerate(o.segs):
        k1 = k0 + len(masks)                    # the segment's last frame (a Clawline's press P)
        if k1 <= s:
            if claw is not None and si + 1 < len(o.segs) and o.segs[si + 1][0] + CTRL_SETTLE > s:
                return None, "in a Clawline"
            if claw is not None and si + 1 >= len(o.segs) and k1 + 34 > s:
                return None, "in a Clawline"
            continue
        if first and k0 > s:
            return None, "in a Clawline"
        a = max(k0, s)
        lo, hi = a - s, k1 - s
        if hi > len(lat):
            return None, "short"
        m = (lat[lo:hi] & ~M_CLAW).astype(np.int64)
        nd = []
        for (i, iid) in dsl:
            kp = k0 + 1 + int(i)
            if kp <= s:
                if kp + DS_WIN > s:
                    return None, "slash under way"
                continue
            j = kp - (a + 1)
            q = lo + j
            pm = int(lat[q - 1]) if q > 0 else int(lat_s)
            if (int(lat[q]) & M_DS) != M_DS or (pm & km.B_ATTACK):
                if move <= 0:
                    return None, "press moved"
                q2 = _press_at(lat, q, lat_s if q == 0 else int(lat[q - 1]), look=move)
                if q2 < 0 or q2 >= hi:
                    continue
                j = q2 - lo
            nd.append((j, int(iid)))
        segs.append(ms.Seg(m, nd, claw, "re"))
        first = False
    if not segs:
        return None, "played"
    return ms.Plan(segs, "re"), ""


def _first_collision_out(o: OutData, tr, s: int, k1: int) -> int | None:
    """brnum.first_hit + the rare shapes for a trajectory re-simulated from frame s (its index k = frame s + k)
    against the outcome's geometry (frames from the anchor), frames s + 1 .. k1."""
    n = s + len(tr.pos)
    px = np.zeros(n)
    py = np.zeros(n)
    px[s:] = tr.pos[:, 0]
    py[s:] = tr.pos[:, 1]
    ifr = np.ones(n, np.bool_)
    ifr[s:] = tr.ifr[:len(tr.pos)]
    k1 = min(k1, n - 1)
    if k1 < s + 1:
        return None
    hk = [(h.iid, h.P + s + sk.HOOK_BODY_OFF[0], h.ctrl + s + sk.HOOK_BODY_OFF[1]) for h in tr.hooks if h.ok]
    hki = np.array([h[0] for h in hk], np.int64)
    hlo = np.array([h[1] for h in hk], np.int64)
    hhi = np.array([h[2] for h in hk], np.int64)
    off, BX, IIDB, coff, CO = o.geo
    kb, _ = brnum.first_hit(px, py, ifr, s + 1, k1, off, BX, IIDB, hki, hlo, hhi, ms._HW, ms._HH, ms._HDY,
                            ms.WALL_L, ms.WALL_R, coff, CO)
    top = kb - 1 if kb >= 0 else k1
    res = kb if kb >= 0 else None
    for k in o.rare_k:
        k = int(k)
        if s + 1 <= k <= top and not ifr[k]:
            if ms.shapes_hit(o.rare[k], cm.hurtbox(px[k], py[k])):
                res = k
                break
    # M4 S1: a forced collision of the re-simulation (a Clawline the kin state would not start, a side contact out
    # of the air sprint: search.Traj.bad, frames from s)
    kx = ms.bad_frame(tr, 1, k1 - s)
    if kx is not None and (res is None or kx + s < res):
        return kx + s
    return res


def _tops_fn(o: OutData, s: int = 0):
    """M4 S1b: simulate's tops_fn for a re-simulation of the outcome from frame s (None: an older plan without tops -
    the robust box's top)."""
    tops = getattr(o, "tops", None)
    if tops is None:
        return None
    return lambda iid: (tops[iid][s:] if iid in tops else None)


def _claw_dirs(d: int) -> tuple:
    return (km.B_RIGHT, km.B_LEFT) if d > 0 else (km.B_LEFT, km.B_RIGHT)


def commit_check(W, lp: LivePlan, fo: int, S0: np.ndarray, inflight: np.ndarray, hold: tuple, lat_s: int, her_xy,
                 obs: list, cfg: LiveCfg, idx=None, tol: float | None = None, acc=None) -> tuple:
    """THE EXACT HERO2 SIMULATION CHECK FROM THE CURRENT STATE of a received plan (module docstring, 1): (ok, why,
    info) - info: the outcomes kept (alive at f + 2), their re-simulated paths (pos_over), the max path deviation,
    the outcomes checked and simulated, ms. M4d: the outcomes that can still be the truth (possible(): not contradicted
    on their own timing view's records, her control) must all reach the frame being chosen ('ended': one of them has to
    deviate before it), every one is re-simulated; a Clawline press the plan does not have, or one of its own not
    latched with the direction toward its target at P (the game throws it toward her facing), rejects it."""
    t0 = time.perf_counter()
    s = int(fo - lp.t_a)
    info = {"s": s}
    if s < 0:
        return False, "future", info
    L = len(inflight)
    r0 = s + L + 1                           # the frame being chosen (f + 2)
    if all(lp.outs[i].kc < r0 for i in (range(len(lp.outs)) if idx is None else idx)):
        return False, "expired", info        # every outcome's committed part ends before the frame being chosen
    if int(lat_s) & M_CLAW:
        return False, "in a Clawline", info  # a Clawline latched now: she is in its antic / pull (no control)
    cons, bad_h, bad_c = lp.consistent(s, her_xy, obs, cfg, idx=idx, hero=False)
    info["cons"] = len(cons)
    tol = cfg.tol_commit if tol is None else tol
    if not cons:
        # the log: the most probable outcome's Clappers at s against the observed ones
        o_ = max(lp.outs, key=lambda o: o.p) if lp.outs else None
        if o_ is not None:
            info["pred"] = {str(k % 1000): v for k, v in _clapper_pred(o_, s).items()}
            info["obs"] = [[ob.iid % 1000, ob.st, ob.j, round(float(ob.x), 2), ob.face] for ob in obs]
        return False, "clappers", info
    if cfg.views_exact:
        poss = possible(lp, cons, s, obs, cfg, acc)
        info["poss"] = len(poss)
        ended = [i for i in poss if lp.outs[i].kc < r0]
        if ended:
            # a possible truth's committed part ends before the frame being chosen (M3: she deviates there - a
            # collision follows with the plan's keys): not this plan's keys then
            info.update(out=ended[0], kc=int(lp.outs[ended[0]].kc))
            return False, "ended", info
        alive = poss
    else:
        alive = [i for i in cons if lp.outs[i].kc >= r0]
    if not alive:
        return False, "short", info
    if cfg.dev_gap > 0:
        near = [i for i in alive if lp.outs[i].kcol is not None and lp.outs[i].kcol - lp.outs[i].kc < cfg.dev_gap]
        if near:
            # (finding safety 6) a possible truth hands the keys back just before a collision: the fallback would have
            # fewer than dev_gap frames to take the escape the search's exit check found
            o_ = lp.outs[near[0]]
            info.update(out=near[0], kc=int(o_.kc), col=int(o_.kcol))
            return False, "dev gap", info
    face0 = int(S0[km.FACE]) if S0[km.FACE] != 0 else 1
    alpha_c = int(round(float(S0[km.ALPHA]) * 6.0)) % 6
    memo: dict = {}
    pos_over: dict = {}
    dev_max = 0.0
    n_sim = 0
    for i in alive:
        o = lp.outs[i]
        cmds = np.concatenate([np.asarray(inflight, np.int64), o.cmds[r0:o.end + 1]])
        lat = hold_filter1(cmds, hold)
        # a press of the fallback's still in flight (or one the filter moved) that the plan does not have; M4d: the
        # same for a Clawline press, and the plan's own Clawline latched at its P with the direction toward the target
        planned = {k for (k, _) in o.presses}
        claws = {int(k0) + len(m): c for (k0, m, _, c) in o.segs if c is not None}
        fac = sk.facing_track(face0, lat) if claws else None
        pm = int(lat_s)
        for q in range(min(len(lat), max(0, o.kc - s))):
            m = int(lat[q])
            k = s + 1 + q
            if _rising(m, pm, km.B_ATTACK) and k not in planned:
                return False, "unplanned slash", info
            if _rising(m, pm, M_CLAW) and k not in claws:
                return False, "unplanned Clawline", info
            if k in claws and not (_rising(m, pm, M_CLAW) and int(fac[q + 1]) == (1 if claws[k][0] > 0 else -1)):
                info.update(claw_lat=int(m), claw_k=int(k))
                return False, "claw latch", info
            pm = m
        key = (o.variant, lat.tobytes(), tuple((iid, o.boxes[iid].tobytes()) for iid in sorted(o.boxes)),
               tuple((k0, c) for (k0, _, _, c) in o.segs),
               tuple((iid, t_.tobytes()) for iid, t_ in sorted((getattr(o, "tops", None) or {}).items())))
        tr = memo.get(key)
        if tr is None:
            plan, why = reanchor_outcome(o, s, lat, lat_s)
            if plan is None:
                return False, why, info
            boxes = {iid: b[s:] for iid, b in o.boxes.items()}
            tr = ms.simulate(W, plan, lambda iid: boxes.get(iid), face0, S0, VARIANTS[o.variant], alpha_c,
                             claw_lock=int(getattr(lp, "claw_lock", -99)) - s, tops_fn=_tops_fn(o, s))
            memo[key] = tr
            n_sim += 1
        kk = min(o.kc - s, len(tr.pos) - 1)
        if kk < L + 1:
            return False, "short", info
        dev = np.abs(tr.pos[:kk + 1] - o.pos[s:s + kk + 1]).max(axis=1) if kk >= 0 else np.zeros(0)
        dmax = float(dev.max()) if len(dev) else 0.0
        dev_max = max(dev_max, dmax)
        if dmax > tol and not cfg.replay:
            info.update(dev=round(dmax, 3), dev_k=int(np.argmax(dev)) + s, out=i)
            return False, "path", info
        kc_ = _first_collision_out(o, tr, s, o.kc)
        if kc_ is not None:
            info.update(col=int(kc_), out=i)
            return False, "danger", info
        po = o.pos.copy()
        po[s:s + kk + 1] = tr.pos[:kk + 1]
        pos_over[i] = po
    info.update(alive=alive, pos_over=pos_over, dev=round(dev_max, 3), n_sim=n_sim,
                ms=round((time.perf_counter() - t0) * 1e3, 2))
    return True, "ok", info


def audit_run(W, lp: LivePlan, s: int, S0: np.ndarray, cmds: np.ndarray, hold: tuple, lat_s: int, idx: list,
              k_last: int) -> list:
    """M4d2 (LiveCfg.audit_runs, the smoke's safety audit): a control run's keys AS SENT - the keys in flight at its
    commit and map2's keys after it (cmds, frames s + 1 .. of the plan; the plan's own commands after the run complete
    its segments) - re-simulated from the commit's state S0 in each outcome idx still possible at the run's end and
    checked against that outcome's danger to frame k_last (from the anchor): [(outcome, collision frame or None, why)]."""
    out = []
    face0 = int(S0[km.FACE]) if S0[km.FACE] != 0 else 1
    alpha_c = int(round(float(S0[km.ALPHA]) * 6.0)) % 6
    for i in idx:
        o = lp.outs[i]
        n_run = len(cmds)
        tail = o.cmds[s + n_run + 1:o.end + 1] if s + n_run + 1 <= o.end else np.zeros(0, np.int64)
        lat = hold_filter1(np.concatenate([np.asarray(cmds, np.int64), tail]), hold)
        plan, why = reanchor_outcome(o, s, lat, lat_s)
        if plan is None:
            out.append((int(i), None, why))
            continue
        boxes = {iid: b[s:] for iid, b in o.boxes.items()}
        tr = ms.simulate(W, plan, lambda iid: boxes.get(iid), face0, S0, VARIANTS[o.variant], alpha_c,
                         claw_lock=int(getattr(lp, "claw_lock", -99)) - s, tops_fn=_tops_fn(o, s))
        kc = _first_collision_out(o, tr, s, min(int(k_last), int(o.kc)))
        out.append((int(i), None if kc is None else int(kc), ""))
    return out


def repair_check(W, lp: LivePlan, fo: int, f: int, keys: np.ndarray, her_xy, obs: list, cfg: LiveCfg,
                 acc=None) -> tuple:
    """M4d2 (repair, the strict replay): a received plan whose bridge was not followed, judged on the keys actually
    sent: her ANCHOR state (the snapshot's) with the keys sent for frames t_a + 1 .. f + 1 (keys) and the plan's own
    commands from f + 2 on, through the snapshot's hold filter state, re-simulated in every outcome that can still be
    the truth at fo (the Clappers seen now: commit_check's rule); each must stay within tol_repair of its planned path
    from now (fo) to its committed end, touch none of its danger from the anchor on and press nothing the plan does not
    have. (ok, why, info) as commit_check's."""
    t0 = time.perf_counter()
    s = int(fo - lp.t_a)
    info = {"s": s, "repair": True}
    r0 = int(f + 2 - lp.t_a)
    if s < 0:
        return False, "future", info
    cons, bad_h, bad_c = lp.consistent(s, her_xy, obs, cfg, hero=False)
    info["cons"] = len(cons)
    if not cons:
        return False, "clappers", info
    if cfg.views_exact:
        poss = possible(lp, cons, s, obs, cfg, acc)
        ended = [i for i in poss if lp.outs[i].kc < r0]
        if ended:
            return False, "ended", info
        alive = poss
    else:
        alive = [i for i in cons if lp.outs[i].kc >= r0]
    if not alive:
        return False, "short", info
    if cfg.dev_gap > 0 and any(lp.outs[i].kcol is not None and lp.outs[i].kcol - lp.outs[i].kc < cfg.dev_gap
                               for i in alive):
        return False, "dev gap", info
    S_a = lp.S_a
    face0 = int(S_a[km.FACE]) if S_a[km.FACE] != 0 else 1
    alpha_c = int(round(float(S_a[km.ALPHA]) * 6.0)) % 6
    keys = np.asarray(keys, np.int64)
    pos_over, dev_max, n_sim = {}, 0.0, 0
    for i in alive:
        o = lp.outs[i]
        cmds = np.concatenate([keys, o.cmds[r0:o.end + 1]])
        lat = hold_filter1(cmds, lp.hold_a)
        planned = {k for (k, _) in o.presses}
        claws = {int(k0) + len(m): c for (k0, m, _, c) in o.segs if c is not None}
        fac = sk.facing_track(face0, lat) if claws else None
        pm = int(lp.lat_a)
        for q in range(min(len(lat), o.kc)):
            m = int(lat[q])
            k = 1 + q
            if _rising(m, pm, km.B_ATTACK) and k not in planned:
                return False, "unplanned slash", info
            if _rising(m, pm, M_CLAW) and k not in claws:
                return False, "unplanned Clawline", info
            if k in claws and not (_rising(m, pm, M_CLAW) and int(fac[q + 1]) == (1 if claws[k][0] > 0 else -1)):
                return False, "claw latch", info
            pm = m
        plan, why = reanchor_outcome(o, 0, lat, lp.lat_a)
        if plan is None:
            return False, why, info
        tr = ms.simulate(W, plan, lambda iid: o.boxes.get(iid), face0, S_a, VARIANTS[o.variant], alpha_c,
                         claw_lock=int(getattr(lp, "claw_lock", -99)), tops_fn=_tops_fn(o, 0))
        n_sim += 1
        kk = min(o.kc, len(tr.pos) - 1, len(o.pos) - 1)
        if kk < r0:
            return False, "short", info
        # the path from now on (frames s .. its committed end: the past is played - as live, where the check starts
        # from her observed state)
        dev = np.abs(tr.pos[s:kk + 1] - o.pos[s:kk + 1]).max(axis=1)
        dmax = float(dev.max()) if len(dev) else 0.0
        dev_max = max(dev_max, dmax)
        if dmax > cfg.tol_repair:
            info.update(dev=round(dmax, 3), dev_k=int(np.argmax(dev)) + s, out=i)
            return False, "path", info
        kc_ = _first_collision_out(o, tr, 0, o.kc)
        if kc_ is not None:
            info.update(col=int(kc_), out=i)
            return False, "danger", info
        po = o.pos.copy()
        po[:kk + 1] = tr.pos[:kk + 1]
        pos_over[i] = po
    info.update(alive=alive, pos_over=pos_over, dev=round(dev_max, 3), n_sim=n_sim,
                ms=round((time.perf_counter() - t0) * 1e3, 2))
    return True, "ok", info


def late_check(W, lp: LivePlan, fo: int, f: int, keys: np.ndarray, idx: list, tol: float,
               pos_ref: dict | None = None, slip: list | None = None, base: dict | None = None) -> tuple:
    """M4 S1 (LiveCfg.late_check): the plan in control after a skipped tick slipped one of its keys (the oracle held
    the previous ACTION for that frame) - re-simulated from her ANCHOR state (the snapshot's) with the keys actually
    applied for frames t_a + 1 .. f + 1 (keys: a skipped frame's held keys) and the plan's own commands from f + 2,
    through the snapshot's hold filter state, in every outcome idx still possible; a down slash press the keys latch up
    to 2 frames late is moved there (simulate then credits it only where it lands: press.ON), a Clawline that no longer
    latches at its P with her facing toward the target, or a press the plan does not have, fails it. Each must touch
    none of its danger from the anchor to its committed end, and the SLIP'S OWN EFFECT on her path from now (fo) on -
    the same re-simulation with the slipped frames' keys as the plan has them (slip: their frames; the model and the
    anchor the same, so a model drift or a replay's recorded position does not count) - must stay within tol. The
    path of the plan in control (pos_ref: its re-simulated path at the commit / the last re-anchoring) moves by that
    effect (info pos_over). (ok, why, info) as commit_check's.
    M4 S1b base (LiveCfg.late_base): {'s', 'S', 'hold', 'lat'} - re-simulated from that state instead (frame s from
    the anchor: the commit's / the re-anchoring's observed state, its hold filter state and latched mask; keys: the
    keys applied for frames t_a + s + 1 .. f + 1) - the world in which the commit checked the plan (the strict
    replay's repair: the anchor, s 0); the press scan then starts after s, as the commit check's does."""
    t0 = time.perf_counter()
    s = int(fo - lp.t_a)
    r0 = int(f + 2 - lp.t_a)
    info = {"s": s, "late": True}
    if base is None:
        sb, S_b, hold_b, lat_b = 0, lp.S_a, lp.hold_a, int(lp.lat_a)
    else:
        sb, S_b, hold_b, lat_b = int(base["s"]), base["S"], base["hold"], int(base["lat"])
        info["base"] = sb
    face0 = int(S_b[km.FACE]) if S_b[km.FACE] != 0 else 1
    alpha_c = int(round(float(S_b[km.ALPHA]) * 6.0)) % 6
    keys = np.asarray(keys, np.int64)
    pos_over, dev_max, n_sim = {}, 0.0, 0
    lock = int(getattr(lp, "claw_lock", -99)) - sb

    def sim(o, kk_):
        cmds = np.concatenate([kk_, o.cmds[r0:o.end + 1]])
        lat = hold_filter1(cmds, hold_b)
        plan, why_ = reanchor_outcome(o, sb, lat, lat_b, move=2)
        if plan is None:
            return None, lat, why_
        boxes = {iid: b[sb:] for iid, b in o.boxes.items()}
        tr_ = ms.simulate(W, plan, lambda iid: boxes.get(iid), face0, S_b, VARIANTS[o.variant], alpha_c,
                          claw_lock=lock, tops_fn=_tops_fn(o, sb))
        return tr_, lat, ""
    for i in idx:
        o = lp.outs[i]
        tr, lat, why = sim(o, keys)
        planned = {k for (k, _) in o.presses}
        claws = {int(k0) + len(m): c for (k0, m, _, c) in o.segs if c is not None}
        fac = sk.facing_track(face0, lat) if claws else None
        pm = lat_b
        for q in range(min(len(lat), o.kc - sb)):
            m = int(lat[q])
            k = sb + 1 + q
            if _rising(m, pm, km.B_ATTACK) and not any(0 <= k - kp <= 2 for kp in planned):
                return False, "unplanned slash", info
            if _rising(m, pm, M_CLAW) and k not in claws:
                return False, "unplanned Clawline", info
            if k in claws and not (_rising(m, pm, M_CLAW) and int(fac[q + 1]) == (1 if claws[k][0] > 0 else -1)):
                return False, "claw latch", info
            pm = m
        if tr is None:
            return False, why, info
        n_sim += 1
        kk = min(o.kc, sb + len(tr.pos) - 1, len(o.pos) - 1)
        if kk < r0:
            return False, "short", info
        kc_ = _first_collision_out(o, tr, sb, o.kc)
        if kc_ is not None:
            info.update(col=int(kc_), out=i)
            return False, "danger", info
        # the slip's own effect: the same keys with the slipped frames' as the plan has them
        ks = keys.copy()
        for k in (slip or ()):
            q = int(k) - int(lp.t_a) - sb - 1
            if 0 <= q < len(ks) and int(k) - int(lp.t_a) < len(o.cmds):
                ks[q] = int(o.cmds[int(k) - int(lp.t_a)])
        trb, _, _ = sim(o, ks)
        n_sim += 1
        if trb is None:
            trb = tr
        kk = min(kk, sb + len(trb.pos) - 1)
        eff = np.zeros((kk + 1, 2))
        eff[sb:kk + 1] = tr.pos[:kk + 1 - sb] - trb.pos[:kk + 1 - sb]
        dev = np.abs(eff[s:kk + 1]).max(axis=1) if kk >= s else np.zeros(0)
        dmax = float(dev.max()) if len(dev) else 0.0
        dev_max = max(dev_max, dmax)
        if dmax > tol:
            info.update(dev=round(dmax, 3), dev_k=int(np.argmax(dev)) + s, out=i)
            return False, "path", info
        ref = (pos_ref or {}).get(i, o.pos)
        po = np.array(ref, copy=True)
        n_ = min(len(po), kk + 1)
        po[:n_] = po[:n_] + eff[:n_]
        pos_over[i] = po
    info.update(alive=list(idx), pos_over=pos_over, dev=round(dev_max, 3), n_sim=n_sim,
                ms=round((time.perf_counter() - t0) * 1e3, 2))
    return True, "ok", info


# ---- the worker process ---------------------------------------------------------------------------------------------

def boost_self(prio: str, cpus_spec: str | None = None) -> str:
    """The live bot's worker rule (combat_run.boost_worker): High, the P-cores (cpus_spec, else SSBOT_WORKER_CPUS,
    default 0-15), EcoQoS off; 'as': as started."""
    if prio != "high":
        return "as started"
    if os.name != "nt" or os.environ.get("SSBOT_WORKER_BOOST", "1").strip() == "0":
        return "boost off"
    msgs = []
    try:
        import ctypes
        import psutil
        p = psutil.Process()
        p.nice(psutil.HIGH_PRIORITY_CLASS)
        msgs.append("High")
        spec = cpus_spec or os.environ.get("SSBOT_WORKER_CPUS", "0-15")
        cpus = []
        for part in spec.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                cpus += range(int(a), int(b) + 1)
            elif part.strip():
                cpus.append(int(part))
        cpus = [c for c in cpus if c < (psutil.cpu_count() or 0)] or list(range(psutil.cpu_count() or 1))
        if cpus:
            p.cpu_affinity(cpus)
            msgs.append(f"cpus {cpus[0]}-{cpus[-1]}")

        class _PT(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_uint32), ("ControlMask", ctypes.c_uint32), ("StateMask", ctypes.c_uint32)]
        st = _PT(1, 1, 0)
        k32 = ctypes.windll.kernel32
        ok = k32.SetProcessInformation(ctypes.c_void_p(k32.GetCurrentProcess()), 4, ctypes.byref(st),
                                       ctypes.sizeof(st))
        msgs.append("throttling off" if ok else "throttling unchanged")
    except Exception as e:  # noqa: BLE001 - best effort
        msgs.append(f"boost failed: {e}")
    return ", ".join(msgs)


class _Searcher(ms.Searcher):
    """The worker's searcher: its clock jumps past the cap once the search is to be cut (abort_fn)."""
    abort_fn = None

    def _now(self) -> float:
        t = time.perf_counter() if self.vclock is None else self.ev.units * self.vclock
        f = self.abort_fn
        return t + 1.0e6 if (f is not None and f()) else t


def build_prefix(snap: dict) -> tuple:
    """The snapshot's commands (in flight + bridge) through the hold filter -> (Seg of latched masks with the down
    slash presses of the plan in control, '') or (None, why) when a press the search cannot place is in flight (the
    bridge is cut before one)."""
    cmds = np.asarray(snap["cmds"], np.int64)
    L = int(snap["n_inflight"])
    lat = hold_filter1(cmds, snap["hold"])
    fo = int(snap["fo"])
    presses = {int(k): int(i) for (k, i) in snap.get("presses") or ()}
    n = len(lat)
    pm = int(snap.get("lat_s") or 0)
    dsl = []
    for q in range(len(lat)):
        m = int(lat[q])
        if m & M_CLAW:
            if q < L:
                return None, "Clawline in flight"
            n = q
            break
        if _rising(m, pm, km.B_ATTACK):
            iid = presses.get(fo + 1 + q) if (m & M_DS) == M_DS else None
            if iid is None:
                if q < L:
                    return None, "slash in flight"
                n = q
                break
            dsl.append((q, iid))
        pm = m
    if n == 0:
        return None, "no prefix"
    _, hold_after = hold_run(cmds[:n], snap["hold"])
    seg = ms.Seg((lat[:n] & ~M_CLAW).astype(np.int64), dsl, None, "pre")
    seg.hold_after = hold_after
    return seg, ""


def reanchor_prev(plan, t_a: int, fo: int, pre) -> object | None:
    """The plan in control (anchored at t_a) as the kept plan of a search from fo whose prefix is pre: the prefix,
    then its own masks after it (its first segment not played past the prefix), its later segments."""
    s = int(fo - t_a)
    n = len(pre.masks)
    seg0 = plan.segs[0]
    cut = s + n
    if s < 0 or cut >= len(seg0.masks):
        return None
    masks = np.concatenate([np.asarray(pre.masks, np.int64), np.asarray(seg0.masks, np.int64)[cut:]])
    dsl = list(pre.dsl) + [(int(i) - s, int(iid)) for (i, iid) in seg0.dsl if int(i) >= cut]
    return ms.Plan([ms.Seg(masks, dsl, seg0.claw, seg0.tag)] + [x.copy() for x in plan.segs[1:]], plan.origin, "kept")


def _search_one(S, cfg: LiveCfg, snap: dict, part: int, plans: dict, aborted, carry: dict | None = None,
                send=None, dropped=None) -> object:
    """One search from a snapshot (module docstring, WORKERS): a LivePlan or a status dict. M4d2: send (a callable:
    the worker's queue) gets the anytime plans (first_send: final=False) while the search runs."""
    base = {"kind": "status", "part": part, "seq": snap["seq"], "ep": snap["ep"], "fo": snap["fo"],
            "ctrl_seen": (snap.get("ctrl") or (None,))[0]}
    if snap.get("busy"):
        return {**base, "status": "busy:" + str(snap["busy"])}
    if not snap.get("obs"):
        return {**base, "status": "no clapper"}
    pre, why = build_prefix(snap)
    if pre is None:
        return {**base, "status": "busy:" + why}
    sit = ms.Situation(np.asarray(snap["S"], float), list(snap["obs"]), dict(snap["mems"]), list(snap["hazards"]),
                       name=f"f{snap['fo']}")
    if snap.get("claw_ctl") is not None:
        sit.meta["claw_ctrl"] = int(snap["claw_ctl"]) - int(snap["fo"])     # M4 S1: a Clawline's lock (control + 13)
    ctrl = snap.get("ctrl")
    prev = None
    carried = False
    if ctrl is not None and ctrl[0] in plans:
        prev = reanchor_prev(plans[ctrl[0]], ctrl[1], snap["fo"], pre)
    elif ctrl is None and carry and carry.get("ep") == snap["ep"] and 0 < snap["fo"] - carry["t_a"] <= cfg.carry_f:
        prev = reanchor_prev(carry["plan"], carry["t_a"], snap["fo"], pre)
        carried = prev is not None
    lead = len(pre.masks) - int(snap["n_inflight"])
    cap_hi = cfg.cap_ch if ctrl is not None else cfg.cap_fb
    if cfg.deadline and snap.get("t_wall") is not None:
        # M4d2: the plan must reach the bot dl_margin frames before its root (the first own key: the tick choosing it
        # is root - 2), the time since the snapshot already gone (the queue, an aborted search before it)
        avail = (lead + 1 - cfg.dl_margin) / 60.0 - max(0.0, time.time() - float(snap["t_wall"]))
        cap = min(max(avail, cfg.cap_lo), cap_hi)
    else:
        cap = min(max((lead - 2) / 60.0, cfg.cap_min), cap_hi)
    if aborted():
        return {**base, "status": "abort"}
    S.abort_fn = aborted
    f0 = float(np.asarray(snap["S"], float).reshape(km.K, -1)[km.FACE, 0])
    S.realizer = HoldRealizer(len(pre.masks), pre.hold_after, face0=1 if f0 >= 0 else -1)
    n_pre = len(pre.masks)
    sent = {"e": None, "n": 0}

    def on_best(e, kept):
        # M4d2 (first_send): the first safe plan at once, each one better by w_switch after it (the bot waits for the
        # best by the plan's root); never the kept plan's equal (the search's own hysteresis)
        if send is None or aborted():
            return
        if kept is not None and e.value < kept.value + S.cfg.w_switch:
            return
        if _short(e, n_pre, cfg) or (sent["e"] is not None and e.value < sent["e"].value + S.cfg.w_switch):
            return
        lp = _live_plan(S, e, snap, part, n_pre, base, cap, prev, carried, (time.perf_counter() - t0) * 1e3,
                        res_meta=None, final=False, pid=f"{part}:{snap['seq']}i{sent['n']}")
        if lp is not None:
            sent["e"] = e
            sent["n"] += 1
            send(lp)
    S.on_best = on_best if (cfg.first_send and send is not None) else None
    t0 = time.perf_counter()
    try:
        res = S.decide(sit, prev=prev, cap_s=cap, prefix=pre)
    finally:
        S.on_best = None
    ms_ = (time.perf_counter() - t0) * 1e3
    # M4d: the plan in control (the kept plan) evaluated from this newer snapshot: safe or not; and whether its
    # bridge is safe to follow - every plan of this search starts with the prefix (the keys in flight and that
    # bridge): the noop (the prefix, then stop) or the chosen plan safe. The controller drops the plan in control on
    # 'not safe', or cuts it after the bridge when the bridge is (noop_safe)
    noop_ev = next((e for e in res.tried if e is not None and e.plan.origin == "noop"), None)
    ch = res.ev
    base.update(ms=round(ms_, 1), cap=round(cap, 3), n_pre=len(pre.masks), n_cand=res.n_cand, had_prev=prev is not None,
                moved=S.realizer.n_moved, dropped=S.realizer.n_dropped, claw_shift=S.realizer.n_claw_shift,
                claw_bad=S.realizer.n_claw_bad,
                prev_safe=None if (prev is None or carried) else any(e is not None and e.plan is prev and e.safe
                                                                     for e in res.tried),
                noop_safe=bool((noop_ev is not None and getattr(noop_ev, "finished", True) and noop_ev.safe) or
                               (ch is not None and ch.safe and getattr(ch, "finished", True))))
    if aborted():
        return {**base, "status": "abort"}
    e = res.ev
    if e is None:
        return {**base, "status": "none"}
    is_kept = bool(res.kept and not carried)
    # M4d2 (drop_keep): the plan in control was dropped while this search ran - its kept answer goes back as a plan
    back = bool(ctrl is not None and dropped is not None and ctrl[0] in dropped)
    if back and is_kept:
        is_kept = False
        base["back"] = True
    noop_like = e.safe and (e.plan.origin == "noop" or _short(e, n_pre, cfg))
    alt = False
    # (M4d2: the plan in control's frames left at this search's END - the search took frames of it)
    left_now = None if snap.get("left") is None else int(snap["left"]) - (
        int((time.time() - float(snap["t_wall"])) * 60.0) if snap.get("t_wall") is not None else 0)
    ending = ctrl is not None and left_now is not None and left_now <= cfg.alt_left
    if cfg.alt_noop and e.safe and (((ctrl is None or back) and noop_like) or (ending and (noop_like or is_kept))):
        # M4d2: the noop is the fallback's bridge, then stop (or the plan in control's, at its end): the best safe
        # non-noop plan of this search within alt_slack of it keeps the map in control
        others = [x for x in res.tried if x is not None and x is not e and x.safe and x.finished and
                  not getattr(x, "tag", ()) and x.plan.origin != "noop" and (prev is None or x.plan is not prev) and
                  not _short(x, n_pre, cfg)]
        if others:
            b = max(others, key=lambda x: x.value)
            if b.value >= e.value - cfg.alt_slack:
                base["alt_from"] = [("kept" if is_kept else "noop"), round(float(e.value), 3)]
                e, alt = b, True
    if not alt:
        if is_kept:
            return {**base, "status": "kept", "value": round(float(e.value), 3)}
        if not e.safe:
            return {**base, "status": "unsafe"}
        if noop_like:
            return {**base, "status": "noop", "value": round(float(e.value), 3)}
    if e is sent["e"]:
        # M4d2: the final answer is the plan already sent (anytime): the part's decision is done
        return {**base, "status": "sent", "value": round(float(e.value), 3), "n_sent": sent["n"]}
    lp = _live_plan(S, e, snap, part, n_pre, base, cap, prev, carried, ms_, res_meta=res, final=True,
                    pid=f"{part}:{snap['seq']}" + ("c" if (carried and res.kept) else "") + ("a" if alt else "") +
                    ("k" if base.get("back") else ""))
    if lp is None:
        return {**base, "status": "unsafe"}
    lp.alt = alt
    lp.n_sent = sent["n"]
    return lp


def _short(e, n_pre: int, cfg: LiveCfg) -> bool:
    """A plan too short past its prefix to be sent (min_frames). M4d2 (short_fix): one with a press after its prefix
    (a down slash, a Clawline, a segment after one) never is - M4d sent strikes pressed 1 - 3 frames after the bridge
    as 'noop'."""
    if e.plan.n_frames() - n_pre >= cfg.min_frames:
        return False
    if cfg.short_fix:
        s0 = e.plan.segs[0]
        if len(e.plan.segs) > 1 or s0.claw is not None or any(int(i) >= n_pre for (i, _) in s0.dsl):
            return False
    return True


def _live_plan(S, e, snap: dict, part: int, n_pre: int, base: dict, cap: float, prev, carried: bool, ms_: float,
               res_meta=None, final: bool = True, pid: str = "") -> "LivePlan | None":
    """The LivePlan of one evaluated plan of a search (its safe outcomes' data, build_outs); None: no safe outcome."""
    outs = build_outs(e, S.cfg.margins)
    if not outs:
        return None
    log = ms.plan_log(e, snap["fo"])
    return LivePlan(pid=pid, part=part, ep=snap["ep"], seq=snap["seq"], t_a=int(snap["fo"]), f_snap=int(snap["f"]),
                    n_pre=n_pre, n_inflight=int(snap["n_inflight"]), plan=e.plan, outs=outs,
                    value=float(e.value), hits=float(e.hits), p_safe=float(e.p_safe), origin=e.plan.origin,
                    note=e.plan.note, ms=round(ms_, 1), cap=cap, ctrl_seen=base["ctrl_seen"],
                    had_prev=prev is not None,
                    n_cand=res_meta.n_cand if res_meta is not None else -1,
                    timed_out=bool(res_meta.timed_out) if res_meta is not None else False,
                    steps=log.get("steps"), outcomes=log.get("outcomes"), t_sent=time.time(),
                    carried=bool(carried and res_meta is not None and res_meta.kept),
                    prev_safe=base.get("prev_safe"), noop_safe=base.get("noop_safe", False),
                    cmds_pre=np.asarray(snap["cmds"], np.int64)[:n_pre].copy(), final=bool(final),
                    S_a=np.asarray(snap["S"], float).reshape(km.K, -1)[:, 0].copy(), hold_a=snap["hold"],
                    lat_a=int(snap.get("lat_s") or 0),
                    rev=bool(snap.get("rev")), alt=False, n_sent=0,
                    claw_lock=-99 if snap.get("claw_ctl") is None else
                    int(snap["claw_ctl"]) - int(snap["fo"]) + press.CLAW_LOCK_F)


WARM_SITS = Path(r"C:\ssbot\data\m2_play\map2\m3\sits.pkl")   # the acceptance set (M3): the warm-up's situations


def _warm_search(S, W, n_rec: int = 6) -> float:
    """Every compiled path of the search before the first live snapshot: searches on a VIRTUAL clock (work units, so
    a cold numba cache's compile time does not use up the cap and leave paths untouched - the first live searches of
    a fresh checkout otherwise compiled the parallel pass and the witnesses for 40 s each, hung for the bot): an Idle
    Clapper from the ground, the same after a prefix through the hold filter's realizer, two Clappers from the air
    (one in its slam antic), and a few recorded situations of the acceptance set when it is on this machine."""
    t0 = time.perf_counter()
    vc, rl = S.vclock, S.realizer
    S.vclock = 0.01
    try:
        hold_filter1(np.array([1, 0, 0, 2, 2, 0], np.int64), hold_tuple(km.HoldState.idle(1)))
        S0 = km.initial_state(W.params, 26.0, sk.FLOOR + sk.FOOT, ground=True, facing=1)
        o = cm.Obs(1, "Idle", 8 / 60.0, 33.0, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=8)
        sit = ms.Situation(S0, [o], {1: cm.Memory()})
        S.decide(sit, cap_s=0.4)
        S.realizer = HoldRealizer(5, hold_tuple(km.HoldState.idle(1)))
        S.decide(sit, cap_s=0.4, prefix=ms.Seg(np.array([km.B_RIGHT] * 3 + [0] * 2, np.int64), [], None, "pre"))
        S.realizer = rl
        Sa = km.initial_state(W.params, 30.0, sk.FLOOR + 2.0 + sk.FOOT, ground=False, vy=-2.0, facing=1)
        o2 = cm.Obs(2, "Slam Antic", 5 / 60.0, 40.0, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=5)
        S.decide(ms.Situation(Sa, [o, o2], {1: cm.Memory(), 2: cm.Memory()}), cap_s=0.4)
        if n_rec and WARM_SITS.exists():
            import pickle
            with open(WARM_SITS, "rb") as fh:
                sits = pickle.load(fh)
            pick, seen = [], set()
            for s_ in sits:
                g = (s_.meta.get("src"), len(s_.obs), (s_.meta.get("moves") or [""])[0][:2])
                if g not in seen:
                    seen.add(g)
                    pick.append(s_)
            for s_ in pick[:n_rec]:
                s_.S = km.pad_state(s_.S)
                S.realizer = HoldRealizer(1, hold_tuple(km.HoldState.idle(1)))
                S.decide(s_, cap_s=0.3, prefix=ms.Seg(np.zeros(1, np.int64), [], None, "pre"))
    finally:
        S.vclock, S.realizer = vc, rl
    return time.perf_counter() - t0


def worker_main(cfg_d: dict, part: int, nparts: int, in_q, out_q, inst: int = 0, idle=None) -> None:
    """One search worker (module docstring, WORKERS): runs until a {'stop': True} snapshot or its queue closes. idle:
    a shared flag the worker raises while it waits for a snapshot (the bot sends one only then: a snapshot every
    tick cost the bot's thread its pickling under the GIL); a message with 'note' set only updates the plan registry
    and the abort rule (a hit, another plan in control, a new episode)."""
    cfg = LiveCfg(**cfg_d)
    set_switches(cfg)
    boost = boost_self(cfg.prio, cfg.cpus)
    try:
        import numba
        nt = max(1, min(int(cfg.numba_threads), numba.config.NUMBA_NUM_THREADS))
        numba.set_num_threads(nt)
        # M4d: numba's thread count is per thread - the search's background pass thread (search._bg_pool) ran its
        # parallel pass on NUMBA_NUM_THREADS threads; set there too
        nb = ms._bg_pool().submit(lambda: (numba.set_num_threads(nt), numba.get_num_threads())[1]).result()
        boost += f", numba {numba.get_num_threads()} (bg {nb})"
    except Exception as e:  # noqa: BLE001
        boost += f", numba threads unchanged ({e})"
    W = ms.World()
    S = _Searcher(W, ms.Cfg.live(**({"lag": int(cfg.search_lag)} if cfg.search_lag > 0 else {})))
    if nparts > 1:
        S.part = (part, nparts)
    t0 = time.perf_counter()
    try:
        _warm_search(S, W, cfg.warm_rec)
    except Exception as e:  # noqa: BLE001 - reported, the worker goes on
        out_q.put({"kind": "error", "part": part, "where": "warm", "error": repr(e)[:400]})
    state = {"latest": None, "plans": {}, "abort": False, "cur": None, "stop": False, "dropped": set()}
    cond = threading.Condition()

    def reader():
        while True:
            try:
                snap = in_q.get()
            except (EOFError, OSError, ValueError):
                snap = {"stop": True}
            with cond:
                if snap.get("stop"):
                    state["stop"] = True
                    state["abort"] = True
                    cond.notify_all()
                    return
                po = snap.get("plan_obj")
                if po is not None and snap.get("ctrl") is not None:
                    state["plans"][snap["ctrl"][0]] = po
                    if len(state["plans"]) > 16:
                        state["plans"].pop(next(iter(state["plans"])))
                if not snap.get("note"):
                    state["latest"] = snap
                cur = state["cur"]
                chg = cur is not None and (snap.get("ctrl") or (None,))[0] != (cur.get("ctrl") or (None,))[0]
                if chg and snap.get("keep") and snap.get("ctrl") is None:
                    # M4d2 (drop_keep): the plan in control was dropped, its bridge held by the fallback - the search
                    # from it goes on; a kept answer is sent back as a plan
                    if len(state["dropped"]) > 64:
                        state["dropped"].clear()
                    state["dropped"].add((cur.get("ctrl") or (None,))[0])
                    chg = False
                if cur is not None and ("hit" in (snap.get("trig") or ()) or snap.get("ep") != cur.get("ep") or
                                        chg or
                                        # M4d2: a cut - the search's bridge broken (the fallback left it) or a newer
                                        # snapshot after a Clapper's move start (rev_cut)
                                        (snap.get("cut") is not None and cur["seq"] <= int(snap["cut"]))):
                    state["abort"] = True
                cond.notify_all()
    th = threading.Thread(target=reader, daemon=True, name="map2-reader")
    th.start()
    main_id = threading.get_ident()

    parent = None
    try:
        import multiprocessing as _mp
        parent = _mp.parent_process()            # None in the bot's own process (a worker in a thread: tests)
    except Exception:  # noqa: BLE001
        parent = None

    def watchdog():
        # a search past hang_s: its stack to the bot (and its snapshot to dump_dir), once per search; M4d: the bot's
        # process gone (killed outright: its exit handlers never ran) -> this worker exits (M4c's orphans kept running)
        seen = None
        while not state["stop"]:
            time.sleep(0.5)
            if parent is not None:
                try:
                    alive = parent.is_alive()
                except Exception:  # noqa: BLE001
                    alive = True
                if not alive:
                    os._exit(0)
            cur, t_cur = state.get("cur"), state.get("t_cur")
            if cur is None or t_cur is None or cur["seq"] == seen or time.perf_counter() - t_cur < cfg.hang_s:
                continue
            seen = cur["seq"]
            import sys as _sys
            import traceback
            fr = _sys._current_frames().get(main_id)
            msg = {"kind": "error", "where": "hang", "part": part, "seq": cur["seq"], "ep": cur.get("ep"),
                   "s": round(time.perf_counter() - t_cur, 1),
                   "stack": "".join(traceback.format_stack(fr))[-3000:] if fr is not None else ""}
            if cfg.dump_dir:
                try:
                    import pickle
                    Path(cfg.dump_dir).mkdir(parents=True, exist_ok=True)
                    with open(Path(cfg.dump_dir) / f"hang_{inst}_{part}_{cur['seq']}.pkl", "wb") as fh:
                        pickle.dump(cur, fh)
                except Exception as e:  # noqa: BLE001
                    msg["dump"] = repr(e)[:200]
            try:
                out_q.put(msg)
            except Exception:  # noqa: BLE001
                pass
    threading.Thread(target=watchdog, daemon=True, name="map2-watchdog").start()
    out_q.put({"kind": "ready", "part": part, "boost": boost, "os_pid": os.getpid(),
               "warm_s": round(time.perf_counter() - t0, 1)})
    done = -1
    while True:
        with cond:
            while not state["stop"] and (state["latest"] is None or state["latest"]["seq"] <= done):
                if idle is not None:
                    idle.value = 1
                cond.wait(0.5)
            if idle is not None:
                idle.value = 0
            if state["stop"]:
                break
            snap = state["latest"]
            state["cur"] = snap
            state["t_cur"] = time.perf_counter()
            state["abort"] = False
            plans = dict(state["plans"])
        done = snap["seq"]

        def _dump(m):
            # M4 S1 (plan_dump): every plan sent, pickled for the press scan (ssbot.tools.press_scan)
            if not cfg.plan_dump:
                return
            try:
                import pickle
                Path(cfg.plan_dump).mkdir(parents=True, exist_ok=True)
                with open(Path(cfg.plan_dump) / f"plans_i{inst}_p{part}.pkl", "ab") as fh:
                    pickle.dump(m, fh, protocol=pickle.HIGHEST_PROTOCOL)
            except Exception:  # noqa: BLE001
                pass

        def _send(m):
            if isinstance(m, LivePlan):
                state["carry"] = {"plan": m.plan, "t_a": m.t_a, "ep": m.ep}
                _dump(m)
            try:
                out_q.put(m)
            except Exception:  # noqa: BLE001
                pass
        try:
            msg = _search_one(S, cfg, snap, part, plans, lambda: state["abort"], carry=state.get("carry"), send=_send,
                              dropped=state["dropped"])
            if isinstance(msg, LivePlan):
                state["carry"] = {"plan": msg.plan, "t_a": msg.t_a, "ep": msg.ep}
                _dump(msg)
        except Exception as e:  # noqa: BLE001 - one bad snapshot must not end the worker
            import traceback
            msg = {"kind": "error", "part": part, "seq": snap["seq"], "ep": snap["ep"], "error": repr(e)[:300],
                   "tb": traceback.format_exc()[-1500:]}
        with cond:
            state["cur"] = None
        try:
            out_q.put(msg)
        except Exception as e:  # noqa: BLE001
            out_q.put({"kind": "error", "part": part, "seq": snap["seq"], "error": "send: " + repr(e)[:300]})
        if cfg.mem_gb > 0:
            try:
                import psutil
                if psutil.Process().memory_info().rss > cfg.mem_gb * 2 ** 30:
                    out_q.put({"kind": "exit", "part": part, "why": "memory"})
                    return
            except Exception:  # noqa: BLE001
                pass


# ---- the controller (the bot's thread) -----------------------------------------------------------------------------

def _pct(v, q):
    return round(float(np.percentile(v, q)), 2) if len(v) else None


class Map2Controller:
    """Module docstring, THE CONTROLLER."""

    def __init__(self, instance: int = 0, log_dir=None, cfg: LiveCfg | None = None):
        self.cfg = cfg or LiveCfg.from_env()
        set_switches(self.cfg)
        self.instance = instance
        self.K = cm.Know.load()
        self.W = ms.World(self.K)
        self.log_dir = Path(log_dir) if log_dir else None
        self.log_path: Path | None = (self.log_dir / f"map2_i{instance}.jsonl") if self.log_dir else None
        self.procs: list = []
        self.in_qs: list = []
        self.idles: list = []               # the workers' idle flags (shared): a snapshot goes to a waiting worker only
        self._note_key = None
        self.out_q = None
        self._ctx = None
        self.ready: dict = {}
        self.ep = -1
        self.seq = 0
        self.st = Counter()                 # counters over the run (stats()['run_counts'])
        self.run_ms = {"pre": [], "post": [], "check": [], "search": [], "age": []}   # the run's times (stats()['run'])
        self.errors: list = []
        self._stopped = False
        self._reset_ep()

    # ---- processes ----
    def start(self, wait: bool = True) -> float:
        """Spawn the workers (their own processes) and wait until each reports ready (warmed). M4d: the workers'
        input queues never block the bot's exit (cancel_join_thread: notes still unsent to a worker that stopped
        reading are dropped - M4c's bot could hang at exit on a full pipe to a dead or warming worker), and stop() runs
        at exit (atexit: before multiprocessing's own exit handler)."""
        import atexit
        import multiprocessing as mp
        t0 = time.perf_counter()
        self._ctx = mp.get_context("spawn")
        self.out_q = self._ctx.Queue()
        n = max(1, int(self.cfg.parts))
        for part in range(n):
            q = self._ctx.Queue()
            q.cancel_join_thread()
            self.in_qs.append(q)
            self.idles.append(self._ctx.Value("b", 0))
            self.procs.append(self._spawn(part, n, q))
        atexit.register(self.stop)
        if wait:
            self._wait_ready(n, t0)
        return time.perf_counter() - t0

    def _spawn(self, part: int, n: int, q):
        p = self._ctx.Process(target=worker_main, args=(self.cfg.as_dict(), part, n, q, self.out_q, self.instance,
                                                        self.idles[part] if part < len(self.idles) else None),
                              daemon=True, name=f"map2-worker-{self.instance}-{part}")
        p.start()
        return p

    def _wait_ready(self, n: int, t0: float) -> None:
        while len(self.ready) < n and time.perf_counter() - t0 < self.cfg.ready_s:
            try:
                msg = self.out_q.get(timeout=1.0)
            except queue.Empty:
                if not all(p.is_alive() for p in self.procs):
                    break
                continue
            if msg.get("kind") == "ready":
                self.ready[msg["part"]] = msg
            elif msg.get("kind") == "error":
                self.errors.append(msg)

    def attach_inproc(self, in_qs: list, out_q, idles: list | None = None) -> None:
        """Tests: workers run elsewhere (threads) on these queues (idles: their flags; None: a snapshot every tick)."""
        self.in_qs, self.out_q, self.idles = list(in_qs), out_q, list(idles or [])

    def stop(self, timeout: float = 5.0) -> None:
        """The workers asked to stop, joined (timeout), the ones still alive terminated (they are this bot's own
        processes); safe to call twice (M4d: also at exit)."""
        if self._stopped:
            return
        self._stopped = True
        for q in self.in_qs:
            try:
                q.put({"stop": True})
            except Exception:  # noqa: BLE001
                pass
        t_end = time.perf_counter() + timeout
        for p in self.procs:
            try:
                p.join(timeout=max(0.0, t_end - time.perf_counter()))
                if p.is_alive():
                    p.terminate()
                    p.join(timeout=1.0)
            except Exception:  # noqa: BLE001
                pass

    def _check_procs(self) -> None:
        for part, p in enumerate(self.procs):
            if not p.is_alive():
                self._inc("worker_restarts")
                self.errors.append({"kind": "restart", "part": part, "exitcode": p.exitcode, "ep": self.ep})
                self.ready.pop(part, None)          # (M4d2: not waited for by the snapshots until it is warm again)
                for d in self.snaps_out.values():
                    d["parts"].discard(part)
                try:
                    self.procs[part] = self._spawn(part, len(self.procs), self.in_qs[part])
                except Exception as e:  # noqa: BLE001 - (M4d) e.g. CreateProcess failing under memory pressure
                    self._error("spawn", e)

    def warm(self) -> float:
        """The bot side's compiled paths (the hold filter, a re-simulation, the collision kernel)."""
        t0 = time.perf_counter()
        hold_filter1(np.array([1, 0, 0, 2], np.int64), hold_tuple(km.HoldState.idle(1)))
        S0 = km.initial_state(self.W.params, 26.0, sk.FLOOR + sk.FOOT, ground=True, facing=1)
        ms.simulate(self.W, ms.Plan([ms.Seg(np.full(6, km.B_RIGHT, np.int64))]), lambda iid: None, 1, S0,
                    sk.HOOK_VARIANTS[0], 0)
        # M4 S1b (finding others 2): the press check's compiled trace and the strike paths - a credited down slash
        # with its bounce re-roll, a hooked Clawline and the slash after its control (the trace's first load cost 16 ms
        # on the bot's thread at the first commit check of a strike plan: a 2 - 4 frame stall at the commit tick)
        Sa = km.initial_state(self.W.params, 30.0, sk.FLOOR + 3.0 + sk.FOOT, ground=False, vy=-2.0, facing=1)
        md = np.array([0, 0, M_DS, km.B_DOWN, 0, 0, 0, 0, 0, 0, 0, 0], np.int64)
        press.trace(self.W, Sa, md, None, [3])
        body = np.tile(np.array([[29.0, sk.FLOOR, 31.0, sk.FLOOR + 2.4]]), (90, 1))
        side = np.tile(np.array([[33.0, sk.FLOOR + 1.0, 35.0, sk.FLOOR + 6.0]]), (90, 1))
        for bx in (body, side):
            ms.simulate(self.W, ms.Plan([ms.Seg(md, [(2, 7)])]), lambda iid, b_=bx: b_, 1, Sa, sk.HOOK_VARIANTS[0],
                        0, tops_fn=lambda iid, b_=bx: b_[:, 3])
        for bx in (side, body):
            ms.simulate(self.W, ms.Plan([ms.Seg(np.array([0, 0, km.B_RIGHT], np.int64), [], (1, 7)),
                                         ms.Seg(np.zeros(16, np.int64) | np.array([0] * 10 + [M_DS] + [0] * 5),
                                                [(10, 7)])]),
                        lambda iid, b_=bx: b_, 1, Sa, sk.HOOK_VARIANTS[0], 0, tops_fn=lambda iid, b_=bx: b_[:, 3])
        z = np.zeros(3)
        brnum.first_hit(z, z, np.zeros(3, np.bool_), 1, 2, np.zeros(4, np.int64), np.zeros((0, 4)),
                        np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64),
                        ms._HW, ms._HH, ms._HDY, ms.WALL_L, ms.WALL_R, np.zeros(4, np.int64), np.zeros((0, 3)))
        return time.perf_counter() - t0

    # ---- per episode ----
    def _reset_ep(self) -> None:
        self.trk = cm.Tracker()
        self.g = None                       # the game-frame clock (cumsum of dt x 60: a freeze does not advance it)
        self.lat_hist: deque = deque(maxlen=64)   # (f, latched act.mask)
        self.ctrl: LivePlan | None = None
        self.ctrl_idx: list = []
        self.ctrl_pos: dict = {}
        self.ctrl_since = None
        self.ctrl_base: dict | None = None  # M4 S1b (late_base): the state the commit / re-anchoring checked it from
        self.pending: list = []
        self.sent_hist: dict = {}           # frame -> the command sent for it (this controller's view of the keys)
        self.trig: list = []
        self.took = False
        self.last_freeze = -10 ** 9
        self.last_hit = -10 ** 9
        self._st_seen: dict = {}
        self._hp_seen: dict = {}
        self.new_plan_obj = None
        self.rows: list = []
        self.row: dict = {}
        self.last_msg: dict = {}
        self.ep_c = Counter()               # this episode's counters (stats()['counts']; M4d: every counter, per episode)
        # this episode's times (M4d: the stats per episode - an attempt row is one episode)
        self.ms_pre: list = []
        self.ms_post: list = []
        self.ms_check: list = []
        self.lat: list = []                 # sent plans: the search's ms
        self.age_commit: list = []          # frames from a committed plan's anchor to its commit
        self.bridge_hist = {"plan": Counter(), "m2": Counter(), "script": Counter()}   # frames a bridge was followed
        self.bridges: list = []             # [kind, first frame, keys, frames followed, alive] (the bridge audit)
        # M4d
        self.ctrl_excl: set = set()         # the plan in control's outcomes contradicted so far (not the truth)
        self.ctrl_cut = None                # its last frame allowed by a newer search (its bridge, then stop)
        self._exe = None                    # the last execution: (pid, r, possible outcomes, best)
        self._fo_prev = -10 ** 9            # the previous tick's observation frame (a freeze / hit between ticks)
        self._verdict = None                # a newer search's verdict on the plan in control: (pid, cut frame | None)
        self.own_hist: dict = {}            # frame -> who sent its keys ('m2', 'cog', the fallback's owner)
        self.dmg_frames: list = []          # her damage frames this episode
        self.n_err = 0
        self.disabled = False               # too many errors on the bot's side: map2 off for this episode
        self.last_drop = None               # (frame, why) of the last plan dropped (end_dev: a 'dev' outcome's end)
        # M4d2
        self.snaps_out: dict = {}           # seq -> the snapshot's bridge and owner, its parts not answered yet
        self._hold = None                   # (seq, the key expected for f + 2) of this tick's held bridge
        self.rev_new = None                 # (fo, [iid, state]) of a Clapper's move start not searched from yet
        self.rev_log: list = []             # [fo of the move start, iid, state, seq of the snapshot from it, f sent]
        self._run = None                    # the control run's commit data (audit_runs)
        self.hit_k: dict = {}               # iid -> the frame its HP last fell (replay_push)
        self._short_next = False            # the next snapshot with the short bridge (unsafe_short)
        # M4 S1
        self._claw_P = None                 # her last Clawline's press (a rising Clawline latched) ...
        self._claw_ctl = None               # ... and its control (her input back from P + 3): the lock to control + 13
        self._lat_prev = 0
        self._f_prev = None                 # the previous tick's frame (the late check: frames whose tick was skipped)

    def _inc(self, key: str, n: int = 1) -> None:
        self.st[key] += n
        self.ep_c[key] += n

    def _error(self, where: str, e: BaseException) -> None:
        """M4d: an exception on the bot's side (pre / post / feed): logged, the plan dropped by the caller, the fallback
        has the keys; after err_max in an episode map2 is off for the rest of it."""
        import traceback
        self.n_err += 1
        self._inc("errors_" + where)
        if len(self.errors) < 50:
            self.errors.append({"kind": "bot", "where": where, "error": repr(e)[:300],
                                "tb": traceback.format_exc()[-1500:], "ep": self.ep})
        if self.n_err >= self.cfg.err_max:
            self.disabled = True

    def reset(self, episode: int) -> None:
        try:
            self.flush()
        except Exception as e:  # noqa: BLE001 - the log is not worth the episode
            self._error("flush", e)
        self.ep = int(episode)
        self._reset_ep()

    def feed(self, raw: dict, f: int) -> None:
        """Every STATE (ticks and caught-up frames): the Clapper tracker in game frames, her latched keys, her freezes
        (M4d: any frame whose dt is not one game frame - the freeze, its slow-time ramp) and hits."""
        try:
            dt_ = raw.get("dt")
            dt = 1.0 / 60.0 if dt_ is None else float(dt_)
            self.g = 0.0 if self.g is None else self.g + min(max(dt, 0.0), 0.05) * 60.0
            self.trk.feed(raw, int(round(self.g)))
            lm = int((raw.get("act") or {}).get("mask") or 0)
            self.lat_hist.append((int(f), lm))
            # M4 S1: her Clawline's press and control (the next one's lock: control + 13) for the snapshot
            if (lm & M_CLAW) and not (self._lat_prev & M_CLAW):
                self._claw_P, self._claw_ctl = int(f), None
            elif self._claw_P is not None and self._claw_ctl is None and int(f) >= self._claw_P + 3:
                h = raw.get("hero") or {}
                clip = str(((h.get("anim") or {}).get("clip")) or "")
                if bool(h.get("hero_accepting_input", True)) and not clip.startswith("Harpoon"):
                    self._claw_ctl = int(f)
            self._lat_prev = lm
            if not (self.cfg.dt_lo <= dt * 60.0 <= self.cfg.dt_hi):
                self.last_freeze = int(f)
            for ev in raw.get("ev") or ():
                if ev.get("k") == "damage":
                    self.last_hit = int(f)
                    self.dmg_frames.append(int(f))
        except Exception as e:  # noqa: BLE001 - map2 must not end the run (M4d)
            self._error("feed", e)

    # ---- the tick ----
    def _drain(self, fo: int) -> None:
        if self.out_q is None:
            return
        while True:
            try:
                msg = self.out_q.get_nowait()
            except (queue.Empty, EOFError, OSError):
                break
            if isinstance(msg, LivePlan):
                self._inc("plans_recv")
                if getattr(msg, "final", True):
                    self._answered(msg.seq, msg.part)
                else:
                    self._inc("plans_interim")
                self.lat.append(msg.ms)
                self.run_ms["search"].append(msg.ms)
                self.last_msg = {"part": msg.part, "seq": msg.seq, "status": "plan", "ms": msg.ms, "pid": msg.pid,
                                 "value": round(msg.value, 3), "n_cand": msg.n_cand, "n_pre": msg.n_pre}
                if msg.ep != self.ep:
                    self._inc("stale_ep")
                    continue
                self._note_verdict(getattr(msg, "ctrl_seen", None), getattr(msg, "prev_safe", None),
                                   getattr(msg, "noop_safe", False), msg.t_a, msg.n_pre, "plan")
                msg.t_recv_f = int(fo)
                self.pending.append(msg)
                self._inc("plans")
            elif isinstance(msg, dict):
                k = msg.get("kind")
                if k == "status":
                    self._answered(msg.get("seq"), msg.get("part"))
                    if self.cfg.unsafe_short and msg.get("status") == "unsafe" and msg.get("ep") == self.ep and                             msg.get("seq") == self.seq - 1:
                        self._short_next = True     # M4d2: the next snapshot with the short bridge
                    self._inc("w_" + str(msg.get("status")).split(":")[0])
                    if msg.get("alt_from"):
                        self._inc("w_alt_" + str(msg["alt_from"][0]))
                    self.last_msg = {kk: msg.get(kk) for kk in ("part", "seq", "status", "ms", "cap", "n_pre", "n_cand",
                                                                "moved", "dropped", "value", "prev_safe")
                                     if msg.get(kk) is not None}
                    if msg.get("ep") == self.ep:
                        self._note_verdict(msg.get("ctrl_seen"), msg.get("prev_safe"), msg.get("noop_safe", False),
                                           msg.get("fo"), msg.get("n_pre"), str(msg.get("status")))
                elif k == "ready":
                    self.ready[msg["part"]] = msg
                elif k in ("error", "exit"):
                    if msg.get("where") != "hang":
                        self._answered(msg.get("seq"), msg.get("part"), all_=k == "exit")
                    self._inc("w_" + k + ("_" + str(msg.get("where")) if msg.get("where") else ""))
                    self.last_msg = {"part": msg.get("part"), "seq": msg.get("seq"),
                                     "status": f"{k}:{msg.get('where') or msg.get('why') or ''}", "s": msg.get("s")}
                    if len(self.errors) < 50:
                        self.errors.append(msg)

    def _note_verdict(self, ctrl_seen, prev_safe, noop_safe, fo_snap, n_pre, status: str) -> None:
        """M4d: a search from a newer snapshot evaluated the plan in control (its kept plan) and found it UNSAFE: the
        plan is cut after that search's bridge when its noop (the bridge, then stop) was safe, else dropped (pre)."""
        if not self.cfg.unsafe_drop or self.ctrl is None or ctrl_seen != self.ctrl.pid or prev_safe is not False or                 status.startswith("abort"):
            return
        cut = int(fo_snap) + int(n_pre) if (noop_safe and fo_snap is not None and n_pre is not None) else None
        self._inc("verdict_" + ("cut" if cut is not None else "drop"))
        v = self._verdict
        if v is None or v[0] != self.ctrl.pid or (v[1] is not None and (cut is None or cut < v[1])):
            self._verdict = (self.ctrl.pid, cut, status)

    def _answered(self, seq, part, all_: bool = False) -> None:
        """M4d2: a worker's final answer to a snapshot (a plan, a status, an error): that part is done with it."""
        d = self.snaps_out.get(seq) if seq is not None else None
        if d is None:
            return
        if all_ or part is None:
            d["parts"].clear()
        else:
            d["parts"].discard(int(part))

    def hold_row(self, f: int):
        """M4d2 (fb_hold): the planner's CONTINUE row for this tick - the bridge it sent with the newest snapshot whose
        search still runs (a part not answered), from frame f + 2 on (the planner's full plan of that tick, aligned by
        the frames elapsed) - or None: no hold (map2 has the keys, the bridge is over or was not the planner's)."""
        self._hold = None
        if not self.cfg.fb_hold or self.disabled or self.ctrl is not None:
            return None
        try:
            best = None
            pend = {getattr(x, "seq", None) for x in self.pending}
            for seq, d in self.snaps_out.items():
                # a search still running, or its plan received and not decided yet (waiting for its root / her input)
                if not (d["parts"] or seq in pend) or d.get("broken") or not (d["own"] == "plan" or (
                        d["own"] == "m2" and self.cfg.drop_keep)):
                    continue
                if d["k0"] <= f + 2 <= d["k0"] + len(d["bridge"]) - 1 and (best is None or seq > best[0]):
                    best = (seq, d)
            if best is None:
                return None
            d = best[1]
            i = int(f + 2 - d["k2"])
            row = np.asarray(d["res_cmd"], np.int64)[i:]
            if not len(row):
                return None
            self._hold = (best[0], int(row[0]))
            self._inc("hold_ticks")
            self.row["hold"] = int(best[0])
            return row
        except Exception as e:  # noqa: BLE001 - map2 must not end the run
            self._error("hold", e)
            return None

    def _audit_end(self) -> None:
        """M4d2 (audit_runs): the control run that ends now (a drop, a replacement) - its keys as sent, re-simulated
        (audit_run) in the outcomes still possible; collisions counted ('audit_col') and logged on the row."""
        r_ = getattr(self, "_run", None)
        self._run = None
        if r_ is None or self.ctrl is None or r_["lp"] is not self.ctrl:
            return
        try:
            lp = r_["lp"]
            ks = [k for k, v in self.own_hist.items() if v == "m2" and k >= r_["f"] + 2]
            if not ks:
                return
            k1 = max(ks)
            idx = (self._exe[2] if (self._exe is not None and self._exe[0] == lp.pid) else self.ctrl_idx)
            if self.cfg.replay and self.cfg.replay_strict and getattr(lp, "S_a", None) is not None:
                # the strict replay's world: her ANCHOR state and every key sent since the anchor (her observed state
                # is the recording's)
                cmds = []
                for k in range(lp.t_a + 1, k1 + 1):
                    v = self._sent_at(k)
                    v = 0 if v is None else int(v)
                    cmds.append(v & ~COG if self._own_at(k) == "cog" else v)
                res = audit_run(self.W, lp, 0, lp.S_a, np.asarray(cmds, np.int64), lp.hold_a, int(lp.lat_a),
                                list(idx), int(k1 - lp.t_a))
            else:
                cmds = list(np.asarray(r_["inflight"], np.int64))
                for k in range(r_["f"] + 2, k1 + 1):
                    v = self._sent_at(k)
                    cmds.append(0 if v is None else int(v))
                res = audit_run(self.W, lp, int(r_["fo"] - lp.t_a), r_["S0"], np.asarray(cmds, np.int64),
                                r_["hold"], r_["lat_s"], list(idx), int(k1 - lp.t_a))
            self._inc("audit_runs")
            self._inc("audit_out", len(res))
            cols = [x for x in res if x[1] is not None]
            if cols:
                self._inc("audit_col")
            for x in res:
                if x[2]:
                    self._inc("audit_skip_" + x[2].replace(" ", "_"))
            self.row["audit"] = [lp.pid, len(res), [list(x) for x in res if x[1] is not None or x[2]], int(k1)]
        except Exception as e:  # noqa: BLE001 - an audit never ends the run
            self._error("audit", e)

    def _drop(self, why: str, info: dict | None = None) -> None:
        if self.ctrl is not None and self.cfg.audit_runs:
            self._audit_end()
        if self.ctrl is not None:
            self._inc("drop_" + why)
            self.trig.append("drop")
            self.last_drop = (int(self._fo_prev), str(why))
            if self.cfg.drop_rev and why in ("clappers", "hero"):
                self.rev_new = (int(self._fo_prev), [-1, "drop:" + why])      # M4d2: restart now (rev_cut's path)
        self.ctrl, self.ctrl_idx, self.ctrl_pos, self.ctrl_since = None, [], {}, None
        self.ctrl_excl, self.ctrl_cut, self._exe, self._verdict = set(), None, None, None
        self.ctrl_base = None

    def _tm(self, kind: str, v: float) -> None:
        getattr(self, {"pre": "ms_pre", "post": "ms_post", "check": "ms_check", "age": "age_commit"}[kind]).append(v)
        self.run_ms[kind].append(v)

    def pre(self, f: int, fo: int, raw: dict, S0: np.ndarray, inflight: np.ndarray, hold) -> int | None:
        """The keys map2 sends for frame f + 2, or None (the fallback's): module docstring 1 - 2. M4d: an exception
        here drops the plan and returns None (the fallback), as the commit check's always did."""
        if self.disabled:
            self.row = {"f": int(f), "fo": int(fo), "why": "off"}
            return None
        try:
            return self._pre(f, fo, raw, S0, inflight, hold)
        except Exception as e:  # noqa: BLE001 - map2 must not end the run
            self._error("pre", e)
            self._drop("error")
            self.pending = []
            self.took = False
            self.row = {"f": int(f), "fo": int(fo), "why": "error"}
            return None

    def _hit_owner(self, f0: int, f1: int) -> None:
        """M4d: her hits in frames f0 + 1 .. f1 by who sent the keys applied at the hit frame (map2 or the fallback) -
        drop_hit counts only the hits the plan in control saw."""
        for d in self.dmg_frames:
            if f0 < d <= f1:
                own = self._own_at(d)
                self._inc("hits")
                self._inc("hit_" + ("m2" if own == "m2" else "fb"))
                ld = self.last_drop
                if own != "m2" and ld is not None and 0 <= d - ld[0] <= 40:
                    # (the stage audit, S6: a hit within 40 frames after map2 handed the keys back, by why)
                    self._inc("hit_after_drop_" + ld[1])

    def _own_at(self, k: int) -> str | None:
        v = self.own_hist.get(k)
        if v is not None:
            return v
        before = [kk for kk in self.own_hist if kk < k]
        return self.own_hist[max(before)] if before else None

    def _pre(self, f: int, fo: int, raw: dict, S0: np.ndarray, inflight: np.ndarray, hold) -> int | None:
        t0 = time.perf_counter()
        S0 = np.asarray(S0, float).reshape(km.K, -1)[:, 0]
        row = {"f": int(f), "fo": int(fo)}
        self.row = row
        self.took = False
        self._hold = None                    # M4d2: set by hold_row (after this, before the planner) when it holds
        if self.procs and f % 120 == 0:
            self._check_procs()
        self._drain(fo)
        h = raw.get("hero") or {}
        her = h.get("pos")
        acc = bool(h.get("hero_accepting_input", True))
        # M4d2 (noinput_kin): 'no input' in a clip the hero model covers counts as control for the commit
        acc_c = acc or (self.cfg.noinput_kin and str(((h.get("anim") or {}).get("clip")) or "") in KIN_CLIPS)
        obs = self.trk.obs()
        # M4d: a hit or a freeze since the previous tick (a skipped tick's frames too: the plan's frame count is
        # STATE frames, a freeze stops the game's), the hit first (its own freeze follows it)
        prev_fo, self._fo_prev = self._fo_prev, int(fo)
        hit_new = self.last_hit > prev_fo
        if hit_new:
            self._hit_owner(prev_fo, fo)
        self._triggers(fo, obs, hit_new)
        if self.cfg.replay and self.cfg.replay_push and self.hit_k:
            # M4d2 (replay only): a Clapper the recording's hero just hit - its x pushed by the recording's slash
            import copy as _copy
            obs2 = []
            for ob in obs:
                if fo - self.hit_k.get(ob.iid, -10 ** 9) <= self.cfg.push_f:
                    ob = _copy.copy(ob)
                    ob.xtol = self.cfg.tol_x + self.cfg.push_tol
                    self._inc("replay_push_obs")
                obs2.append(ob)
            obs = obs2
        why = None
        dt_ = raw.get("dt")
        if hit_new or self.last_hit >= fo - 1:
            self._drop("hit")
            why = "hit"
        elif her is None or (dt_ is not None and float(dt_) <= 0.0) or self.last_freeze > prev_fo:
            self._drop("freeze")
            why = "freeze"
        elif self._verdict is not None and self.ctrl is not None and self._verdict[0] == self.ctrl.pid and \
                self._verdict[1] is None:
            # M4d: a newer search found the plan in control unsafe and its noop unsafe or unchecked (a replacement may
            # still be committed below)
            row["verdict"] = self._verdict[2]
            self._drop("unsafe")
            why = "unsafe"
        inflight = self._eff_inflight(fo, f, inflight)
        hold_t = self._hold_clean(hold_tuple(hold), fo)
        lat_s = int((raw.get("act") or {}).get("mask") or 0)
        if self._cog_near(fo):
            lat_s &= ~COG                    # M4d: a Cogfly throw's keys are not the kinematics' (the policy's rule)
        # 1. commit (M4d: never while she has no control - a Clawline under way, its antic, a stun)
        no_input = (not acc_c) or bool(self._busy_claw(fo, h))
        if no_input and self.pending and why is None:
            self._inc("commit_wait_noinput")
            row["noinput"] = 1
        if why in (None, "unsafe") and self.pending and not no_input:
            self.pending = [x for x in self.pending if fo - x.t_a <= self.cfg.stale and x.t_a > self.last_freeze]
            cands = self.pending
            if self.ctrl is not None:
                # a replacement must come from a search that knew the plan in control (and so beat it by w_switch),
                # or the plan in control is ending
                left = self._left(fo)
                cands = [x for x in cands if x.ctrl_seen == self.ctrl.pid and
                         (x.had_prev or left <= self.cfg.end_lead)]
                # M4d2: an 'alt' plan (sent over the noop / the kept plan) only once the plan in control is ending
                cands = [x for x in cands if not getattr(x, "alt", False) or left <= self.cfg.alt_left]
            if self.cfg.wait_parts:
                # M4d2: a plan waits for its decision's other parts (and its own better anytime plans) until its root
                n0 = len(cands)
                cands = [x for x in cands if self._ready(x, f)]
                if len(cands) < n0:
                    row["wait_parts"] = n0 - len(cands)
            cands = sorted(cands, key=lambda x: (-x.value, -x.t_a))[:self.cfg.commits_per_tick]
            for lp in cands:
                tc = time.perf_counter()
                # the keys sent since the plan's anchor against its prefix (the keys in flight then and the bridge):
                # followed -> the re-simulation reproduces the planned path; not -> it decides (live) / the strict
                # replay's proxy rejects it
                pre = getattr(lp, "cmds_pre", None)
                o_b = max(lp.outs, key=lambda o_: o_.p)
                # M4 S1b (late_base): the world the late check re-simulates in - live (and the open replay) her observed
                # state now, where commit_check / the repair check the plan; the strict replay's proxy world is the
                # anchor's (its repair_check and its audit's: her observed state is the recording's there)
                if self.cfg.replay and self.cfg.replay_strict and getattr(lp, "S_a", None) is not None:
                    base_c = {"s": 0, "S": lp.S_a, "hold": lp.hold_a, "lat": int(lp.lat_a)}
                else:
                    base_c = {"s": int(fo - lp.t_a), "S": S0.copy(), "hold": hold_t, "lat": int(lat_s)}

                def expect(k, _pre=pre, _o=o_b, _t=lp.t_a):
                    r_ = k - _t
                    if r_ <= len(_pre):
                        return int(_pre[r_ - 1])
                    return int(_o.cmds[r_]) if r_ < len(_o.cmds) else -1
                bridge_ok = pre is not None and all(self._sent_at(k) == expect(k)
                                                    for k in range(lp.t_a + 1, f + 2))
                self._inc("bridge_" + ("ok" if bridge_ok else "broken"))
                try:
                    if self.cfg.repair and not bridge_ok and getattr(lp, "S_a", None) is not None:
                        # M4d2: the plan REPAIRED from the keys actually sent - the strict replay from its anchor state
                        # (her observed one follows the recording), live from her state now with a wider path check
                        if self.cfg.replay and self.cfg.replay_strict:
                            keys_ = np.array([self._sent_at(k) or 0 for k in range(lp.t_a + 1, f + 2)], np.int64)
                            ok, why_c, info = repair_check(self.W, lp, fo, f, keys_, her, obs, self.cfg, acc=acc)
                        else:
                            ok, why_c, info = commit_check(self.W, lp, fo, S0, inflight, hold_t, lat_s, her, obs,
                                                           self.cfg, acc=acc, tol=self.cfg.tol_repair)
                            info["repair"] = True
                        self._inc("repair_" + ("ok" if ok else why_c.replace(" ", "_")))
                    elif self.cfg.replay and self.cfg.replay_strict and not bridge_ok:
                        ok, why_c, info = False, "bridge", {"s": int(fo - lp.t_a)}
                        # M4d2: the first frame off (from the anchor), the key expected and sent, who sent it
                        k_ = next((k for k in range(lp.t_a + 1, f + 2) if self._sent_at(k) != expect(k)), None)
                        if k_ is not None:
                            info["col"] = [int(k_ - lp.t_a), int(lp.n_pre), expect(k_), self._sent_at(k_),
                                           self._own_at(k_)]
                    else:
                        ok, why_c, info = commit_check(self.W, lp, fo, S0, inflight, hold_t, lat_s,
                                                       her, obs, self.cfg, acc=acc)
                    info["bridge"] = bool(bridge_ok)
                except Exception as e:  # noqa: BLE001 - a bad plan is dropped, the bot goes on
                    ok, why_c, info = False, "error", {"error": repr(e)[:200]}
                    if len(self.errors) < 50:
                        import traceback
                        self.errors.append({"kind": "check", "error": repr(e)[:300],
                                            "tb": traceback.format_exc()[-1200:]})
                msc = (time.perf_counter() - tc) * 1e3
                self._tm("check", msc)
                self.pending.remove(lp)
                row.setdefault("chk", []).append([lp.pid, bool(ok), why_c, round(msc, 2), info.get("s"),
                                                  info.get("cons"), info.get("dev"), info.get("col")] +
                                                 ([info.get("pred"), info.get("obs")] if "pred" in info else []))
                self._inc("check_" + why_c)
                if ok:
                    if self.ctrl is not None:
                        self._inc("replaced")
                    self.ctrl_excl, self.ctrl_cut, self._exe, self._verdict = set(), None, None, None
                    self._audit_end()
                    self.ctrl, self.ctrl_idx, self.ctrl_pos = lp, list(info["alive"]), dict(info["pos_over"])
                    self.ctrl_since = int(f)
                    self.ctrl_base = base_c
                    if self.cfg.audit_runs:
                        self._run = {"lp": lp, "fo": int(fo), "f": int(f), "S0": S0.copy(),
                                     "inflight": np.asarray(inflight, np.int64).copy(), "hold": hold_t,
                                     "lat_s": int(lat_s)}
                    self.took = True
                    why = None
                    self.new_plan_obj = lp.plan
                    self._tm("age", int(fo - lp.t_a))
                    self._inc("commits")
                    row["commit"] = {"pid": lp.pid, "t_a": lp.t_a, "value": round(lp.value, 3), "hits": round(lp.hits, 3),
                                     "repair": bool(info.get("repair")),
                                     "origin": lp.origin, "note": lp.note, "ms": lp.ms, "n_pre": lp.n_pre,
                                     "outs": len(lp.outs), "alive": len(info["alive"]), "steps": lp.steps,
                                     "bridge": bool(info.get("bridge")), "carried": bool(getattr(lp, "carried", False)),
                                     "outcomes": lp.outcomes, "poss": info.get("poss"),
                                     "dev": sorted({(o.kc, o.kcol) for o in lp.outs if o.kcol is not None}),
                                     "cp": sorted({(k, i, kd) for o in lp.outs for (k, i, kd) in o.contacts})}
                    self.trig.append("commit")
                    # M4d2: the plans of this decision and older ones are done with
                    self.pending = [x for x in self.pending if getattr(x, "seq", -1) > getattr(lp, "seq", -1)]
                    break
        # M4 S1 (late_check): frames since the previous tick whose tick was skipped kept that tick's ACTION; a key of the
        # plan in control slipped there -> the plan re-checked from the keys actually sent before it goes on
        f_prev, self._f_prev = self._f_prev, int(f)
        if self.cfg.late_check and why is None and self.ctrl is not None and f_prev is not None and \
                int(f) > int(f_prev) + 1 and not self.took:
            why = self._late(f_prev, f, fo, row)
        # M4d: the newer search's verdict on the plan still in control: its noop (the bridge, then stop) was safe -
        # the plan is cut after that bridge
        if self._verdict is not None and self.ctrl is not None and self._verdict[0] == self.ctrl.pid and                 self._verdict[1] is not None:
            self.ctrl_cut = self._verdict[1] if self.ctrl_cut is None else min(self.ctrl_cut, self._verdict[1])
            row["cut"] = int(self.ctrl_cut)
            self._verdict = None
        # 2. execute
        mask = None
        if self.ctrl is not None and why is None:
            lp = self.ctrl
            n = int(fo - lp.t_a)
            r = int(f + 2 - lp.t_a)
            cons, bad_h, bad_c = lp.consistent(n, her, obs, self.cfg, idx=self.ctrl_idx, hero=not self.cfg.replay,
                                               pos_over=self.ctrl_pos)
            if not cons and bad_h:
                # her position left the path while the Clappers are consistent: the plan re-anchored to her state
                # now (the exact re-simulation, the collisions; the path within tol_reanchor) or dropped
                tc = time.perf_counter()
                try:
                    ok, why_r, info = commit_check(self.W, lp, fo, S0, inflight, hold_t, lat_s, her, obs, self.cfg,
                                                   idx=self.ctrl_idx, tol=self.cfg.tol_reanchor, acc=acc)
                except Exception as e:  # noqa: BLE001
                    ok, why_r, info = False, "error", {"error": repr(e)[:200]}
                self._tm("check", (time.perf_counter() - tc) * 1e3)
                row.setdefault("chk", []).append([lp.pid, bool(ok), "re:" + why_r, round((time.perf_counter() - tc) * 1e3, 2),
                                                  info.get("s"), info.get("cons"), info.get("dev"), info.get("col")])
                self._inc("reanchor_" + why_r)
                if ok:
                    self.ctrl_idx, self.ctrl_pos = list(info["alive"]), dict(info["pos_over"])
                    self.ctrl_base = {"s": int(n), "S": S0.copy(), "hold": hold_t, "lat": int(lat_s)}   # (S1b)
                    cons, bad_h, bad_c = lp.consistent(n, her, obs, self.cfg, idx=self.ctrl_idx, hero=True,
                                                       pos_over=self.ctrl_pos)
            if not cons:
                # the log: the most probable kept outcome's Clappers and her position against the observed ones
                o = max((lp.outs[i] for i in self.ctrl_idx), key=lambda o_: o_.p, default=None)
                if o is not None:
                    pc_ = _clapper_pred(o, n)
                    row["dc"] = [[ob.iid % 1000, ob.st, *(pc_.get(ob.iid) or (None, None, None))[:1],
                                  None if ob.iid not in pc_ else int((ob.j or 0) - pc_[ob.iid][1]),
                                  None if ob.iid not in pc_ else round(float(ob.x - pc_[ob.iid][2]), 3)] for ob in obs]
                    i_ = lp.outs.index(o)
                    pos = self.ctrl_pos.get(i_, o.pos)
                    if her is not None and 0 <= n < len(pos):
                        row["dh"] = [round(float(her[0] - pos[n, 0]), 3), round(float(her[1] - pos[n, 1]), 3)]
                self._drop("hero" if bad_h and not bad_c else "clappers")
                why = "fail:" + ("hero" if bad_h and not bad_c else "clappers")
            else:
                mask, why = self._execute(lp, cons, n, r, f, her, obs, acc, row)
        if mask is None and why is None:
            why = "none" if not self.pending else "wait"
        row["why"] = why
        self._tm("pre", (time.perf_counter() - t0) * 1e3)
        return mask

    def _late(self, f_prev: int, f: int, fo: int, row: dict) -> str | None:
        """M4 S1 (late_check): the frames f_prev + 3 .. f + 1 got no ACTION (their ticks were skipped: the oracle held
        f_prev + 2's keys). When the plan in control wanted another key at one of them (in no outcome still possible
        it is the held one), it is re-checked (late_check) from the keys actually sent; failed: dropped ('late').
        Returns the drop's why or None."""
        lp = self.ctrl
        idx = self._exe[2] if (self._exe is not None and self._exe[0] == lp.pid) else list(self.ctrl_idx)
        if not idx:
            return None
        k_lo = max(int(f_prev) + 3, int(self.ctrl_since or 0) + 2)
        slip = []
        for k in range(k_lo, int(f) + 2):
            if k in self.sent_hist:
                continue
            held = self._sent_at(k)
            r = k - int(lp.t_a)
            want = {int(lp.outs[i].cmds[r]) for i in idx if 0 <= r < len(lp.outs[i].cmds)}
            if held is not None and want and int(held) not in want:
                slip.append(int(k))
        if not slip:
            return None
        self._inc("late_slip")
        tc = time.perf_counter()
        base = self.ctrl_base if (self.cfg.late_base and self.ctrl_base is not None) else None
        if self.cfg.late_base:
            # M4 S1b: from the commit's own state (the keys applied since it), a Cogfly throw's keys stripped (the
            # audit's / the keys in flight's rule: the kinematics would cast)
            k0 = int(lp.t_a) + (int(base["s"]) if base is not None else 0) + 1
            keys = np.array([(int(v) & ~COG if self._own_at(k) == "cog" else int(v)) if v is not None else 0
                             for k in range(k0, int(f) + 2) for v in (self._sent_at(k),)], np.int64)
        else:
            keys = np.array([self._sent_at(k) or 0 for k in range(int(lp.t_a) + 1, int(f) + 2)], np.int64)
        try:
            ok, why_l, info = late_check(self.W, lp, fo, f, keys, idx, self.cfg.tol_late, pos_ref=self.ctrl_pos,
                                         slip=slip, base=base)
        except Exception as e:  # noqa: BLE001
            ok, why_l, info = False, "error", {"error": repr(e)[:200]}
        msc = (time.perf_counter() - tc) * 1e3
        self._tm("check", msc)
        row.setdefault("chk", []).append([lp.pid, bool(ok), "late:" + why_l, round(msc, 2), info.get("s"), slip,
                                          info.get("dev"), info.get("col")])
        self._inc("late_" + ("ok" if ok else why_l.replace(" ", "_")))
        if ok:
            self.ctrl_idx = [i for i in self.ctrl_idx if i in info["alive"]] or list(info["alive"])
            self.ctrl_pos.update(info["pos_over"])
            return None
        row["late"] = slip
        self._drop("late")
        return "late"

    def _ready(self, x: LivePlan, f: int) -> bool:
        """M4d2 (wait_parts): a received plan is checked for its commit once every part of its decision has answered
        (their finals) or when its root - its first own key, after the prefix - is due within a frame."""
        d = self.snaps_out.get(getattr(x, "seq", None))
        if d is None or not d["parts"]:
            return True
        return int(f) + 2 >= int(x.t_a) + int(x.n_pre)

    def _execute(self, lp: LivePlan, cons: list, n: int, r: int, f: int, her, obs: list, acc: bool, row: dict) -> tuple:
        """The plan in control's command for frame r (from its anchor) from its consistent outcomes cons (module
        docstring 2). M4d: only the POSSIBLE ones (possible(): the sticky exclusions of the timing views and the hook
        variants) count, and the plan ENDS as soon as one of them has to deviate (its committed part ended: M3's
        reveal + lag before a collision) - M4c ran on with another outcome's keys (a late timing view's) into the
        collision the search had avoided only by deviating; disagreeing outcomes: the bits they agree on, the others
        as sent for the frame before. (mask | None, why)."""
        cfg = self.cfg
        if cfg.views_exact or cfg.ctl_check:
            poss = possible(lp, cons, n, obs, cfg, acc, self.ctrl_excl)
        else:
            poss = list(cons)
        if self.ctrl_cut is not None and f + 2 > self.ctrl_cut:
            self._drop("cut")
            return None, "cut"
        if cfg.views_exact:
            ended = [i for i in poss if lp.outs[i].kc < r or r >= len(lp.outs[i].cmds)]
            if ended:
                o = lp.outs[ended[0]]
                row["ended"] = [int(o.kc), o.why, o.kcol, len(poss), len(cons)]
                # (S6: a 'dev' outcome's end - a collision follows its committed part; the fallback must take the
                # escape the search's exit check found - counted apart for the gate's audit)
                self._drop("end_dev" if any(lp.outs[i].kcol is not None for i in ended) else "end")
                return None, "end"
            alive = poss
        else:
            alive = [i for i in poss if lp.outs[i].kc >= r and r < len(lp.outs[i].cmds)]   # (both off: M4c's rule)
            if not alive:
                self._drop("end")
                return None, "end"
        best = max(alive, key=lambda i: lp.outs[i].p)
        keys = [int(lp.outs[i].cmds[r]) for i in alive]
        mask = int(lp.outs[best].cmds[r])
        agree = all(k == mask for k in keys)
        if not agree:
            row["dis"] = len(set(keys))
            self._inc("disagree")
            if cfg.dis_hold:
                prev = self._sent_at(int(f) + 1)
                mask, dis = _merge_keys(keys, 0 if prev is None else prev)
                row["dis_bits"] = int(dis)
        self._exe = (lp.pid, r, list(alive), best)
        why = "commit" if self.took else "keep"
        row.update(pid=lp.pid, n=n, left=min(lp.outs[i].kc for i in alive) - r,
                   pc=round(sum(lp.outs[i].p for i in cons), 3), age=int(n), lat=lp.ms, poss=len(alive))
        o = lp.outs[best]
        pos = self.ctrl_pos.get(best, o.pos)
        if her is not None and n < len(pos):
            row["dh"] = [round(float(her[0] - pos[n, 0]), 3), round(float(her[1] - pos[n, 1]), 3)]
        pc_ = _clapper_pred(o, n)
        row["dc"] = [[ob.iid % 1000, ob.st, *(pc_.get(ob.iid) or (None, None, None))[:1],
                      None if ob.iid not in pc_ else int((ob.j or 0) - pc_[ob.iid][1]),
                      None if ob.iid not in pc_ else round(float(ob.x - pc_[ob.iid][2]), 3)] for ob in obs]
        if any(k == n for o_ in (lp.outs[i] for i in cons) for (k, _, _) in o_.contacts):
            row["cp"] = "contact"
        return mask, why

    def _sent_at(self, k: int) -> int | None:
        """The command the oracle applies at frame k: the ACTION sent for k, else the last one before it (an ACTION
        holds its keys from its frame on: a frame whose tick was skipped keeps the previous keys); None: unknown."""
        v = self.sent_hist.get(k)
        if v is not None:
            return v
        before = [kk for kk in self.sent_hist if kk < k]
        return self.sent_hist[max(before)] if before else None

    def _eff_inflight(self, fo: int, f: int, inflight) -> np.ndarray:
        """The keys in flight for frames fo + 1 .. f + 1 as the oracle applies them (_sent_at; the policy's prefix
        counts a frame without an ACTION as no key) - the policy's where this controller has no record. M4d: a Cogfly
        throw's keys (Up + QuickCast) stripped as the policy's prefix strips them (the kinematics would cast)."""
        pol = np.asarray(inflight, np.int64)
        out = pol.copy()
        for q, k in enumerate(range(int(fo) + 1, int(f) + 2)):
            v = self._sent_at(k)
            if v is not None and q < len(out):
                if self._own_at(k) == "cog":
                    v = int(v) & ~COG
                out[q] = v
        return out

    def _cog_near(self, fo: int) -> bool:
        """M4d: a Cogfly throw's keys sent for a frame near fo (fo - 3 .. fo + 2: latched now or on their way)."""
        return any(self.own_hist.get(k) == "cog" for k in range(int(fo) - 3, int(fo) + 3))

    def _hold_clean(self, hold_t: tuple, fo: int) -> tuple:
        """M4d: the hold filter's state with a Cogfly throw's Up + QuickCast taken out (the policy's prefix has no
        such keys; latched they make the kinematics cast)."""
        if not self._cog_near(fo):
            return hold_t
        lat, des, pen, age = (np.array(x, copy=True) for x in hold_t)
        for b in _COG_BITS:
            lat[b], des[b], pen[b] = False, False, 0
        return lat, des, pen, age

    def _left(self, fo: int) -> int:
        """The plan in control's committed frames left: M4d: to the first end of its possible outcomes (where it ends),
        M4c: to the last of its outcomes."""
        lp = self.ctrl
        if lp is None or not self.ctrl_idx:
            return -1
        idx = self._exe[2] if (self._exe is not None and self._exe[0] == lp.pid) else self.ctrl_idx
        kcs = [lp.outs[i].kc for i in idx]
        return (min(kcs) if self.cfg.views_exact else max(kcs)) - int(fo - lp.t_a)

    def _triggers(self, fo: int, obs: list, hit_new: bool = False) -> None:
        for ob in obs:
            key = (ob.st, int(self.trk.cl.get(ob.iid, {}).get("ent") or 0))
            if self._st_seen.get(ob.iid) not in (None, key):
                self.trig.append("reveal")
                self.row.setdefault("rev", []).append([ob.iid % 1000, ob.st])   # (M4d: the reveal latency audit)
                if ob.st in brnum.MOVE_STARTS:
                    self.rev_new = (int(fo), [ob.iid % 1000, ob.st])           # M4d2: a move start (rev_cut)
            self._st_seen[ob.iid] = key
            hp0 = self._hp_seen.get(ob.iid)
            if hp0 is not None and ob.hp < hp0:
                self.trig.append("landed")
                self.hit_k[ob.iid] = int(fo)    # M4d2 (replay_push)
            self._hp_seen[ob.iid] = ob.hp
        if hit_new or self.last_hit >= fo - 1:
            self.trig.append("hit")
        if self.ctrl is not None and self._left(fo) <= self.cfg.end_lead:
            self.trig.append("end")

    def _busy_claw(self, fo: int, h: dict) -> str | None:
        """She is in a Clawline (pressed in the last CLAW_BLOCK_F frames, its Harpoon clip on or no control)."""
        if any(m & M_CLAW for (fr, m) in self.lat_hist if fo - CLAW_BLOCK_F < fr <= fo):
            clip = str(((h.get("anim") or {}).get("clip")) or "")
            if clip.startswith("Harpoon") or not bool(h.get("hero_accepting_input", True)):
                return "Clawline"
        return None

    def _busy(self, fo: int, raw: dict) -> str | None:
        h = raw.get("hero") or {}
        if not bool(h.get("hero_accepting_input", True)) and not (
                self.cfg.noinput_kin and str(((h.get("anim") or {}).get("clip")) or "") in KIN_CLIPS):
            return "no input"
        if self.last_freeze >= fo - 1:
            return "freeze"
        if any(t.get("st") in cm.INTRO for t in self.trk.cl.values() if t.get("e") is not None):
            return "intro"                      # the battle has not started (the model's intro is coarse)
        hist = [m for (fr, m) in self.lat_hist if fo - DS_WIN < fr <= fo]
        prev = [m for (fr, m) in self.lat_hist if fr == fo - DS_WIN]
        pm = prev[0] if prev else (hist[0] if hist else 0)
        for m in hist:
            if _rising(m, pm, km.B_ATTACK):
                return "slash"
            pm = m
        return self._busy_claw(fo, h)

    def post(self, f: int, fo: int, raw: dict, S0: np.ndarray, inflight: np.ndarray, hold, mask: int, own: str,
             res_cmd, sup: bool) -> None:
        """After the keys are chosen: the controller's state when the supervisor took the keys, the snapshot to the
        workers (module docstring, WORKERS), the per-tick log row. M4d: an exception here is logged and dropped (the
        plan too); the fallback's keys stand."""
        try:
            self._post(f, fo, raw, S0, inflight, hold, mask, own, res_cmd, sup)
        except Exception as e:  # noqa: BLE001 - map2 must not end the run
            self._error("post", e)
            self._drop("error")
            self.sent_hist[int(f) + 2] = int(mask)
            self.own_hist[int(f) + 2] = str(own)
            self.trig = []
            self.row = {}

    def _bridge_keys(self, f: int) -> tuple:
        """The plan in control's keys expected from frame f + 3 on (the bridge): M4d: the keys its POSSIBLE outcomes
        (as the execution chose them this tick) agree on, to the first end among them (the plan ends there), a newer
        search's cut, a Clawline press or ch_lead frames - M4c took the most probable outcome of all those kept at the
        commit, which after a hook could be the other variant's keys. (keys, [(frame, target)] down slash presses)."""
        lp = self.ctrl
        r = int(f + 3 - lp.t_a)
        if self._exe is not None and self._exe[0] == lp.pid:
            idx, best = self._exe[2], self._exe[3]
        else:
            idx = [i for i in self.ctrl_idx if lp.outs[i].kc >= r]
            best = max(idx, key=lambda i: lp.outs[i].p) if idx else None
        if best is None or not idx:
            return [], []
        ks = [lp.outs[i].kc for i in idx]
        hi = min(min(ks) if self.cfg.views_exact else lp.outs[best].kc, lp.outs[best].end, r + self.cfg.ch_lead - 1)
        if self.ctrl_cut is not None:
            hi = min(hi, int(self.ctrl_cut) - lp.t_a)
        bridge = []
        for k in range(r, hi + 1):
            vals = {int(lp.outs[i].cmds[k]) for i in idx if k < len(lp.outs[i].cmds)}
            if len(vals) == 0 or (self.cfg.dis_hold and len(vals) != 1):
                break
            c = int(lp.outs[best].cmds[k])
            if c & M_CLAW:
                break
            bridge.append(c)
        pk = {int(k): iid for (k, iid) in lp.outs[best].presses}
        presses = [(lp.t_a + k, pk[k]) for k in range(r, r + len(bridge)) if k in pk]
        return bridge, presses

    def _post(self, f: int, fo: int, raw: dict, S0: np.ndarray, inflight: np.ndarray, hold, mask: int, own: str,
              res_cmd, sup: bool) -> None:
        t0 = time.perf_counter()
        S0 = np.asarray(S0, float).reshape(km.K, -1)[:, 0]
        inflight = self._eff_inflight(fo, f, inflight)
        row = self.row if self.row.get("f") == f else {"f": int(f), "fo": int(fo)}
        if sup and self.ctrl is not None:
            self._drop("sup")
            row["why"] = "sup"
        row.update(own=own, mask=int(mask), m2=int(own == "m2"))
        if own == "m2":
            self._inc("ticks_m2")
        self._inc("ticks")
        # the bridge: the keys expected while the search runs
        bridge, presses = [], []
        if own == "m2" and self.ctrl is not None:
            bridge, presses = self._bridge_keys(f)
        elif own == "plan" and res_cmd is not None and len(res_cmd) > 1 and int(res_cmd[0]) == int(mask):
            bridge = [int(x) for x in np.asarray(res_cmd, np.int64)[1:1 + self.cfg.fb_lead]]
        elif own not in ("sup", "m2", "plan", "cog"):
            bridge = [int(mask)] * self.cfg.sc_lead     # a script: its keys ahead are unknown - the held key (a guess)
        self._bridge_audit(f, int(mask))
        # M4d2: the key sent for f + 2 against the pending searches' bridges (a break cuts those searches); a Clawline
        # pressed (whoever sent it) logged with the Clappers' states (the CLAWSTRIKE count)
        self._check_bridges(f, fo, int(mask), own, row)
        pm_ = self._sent_at(int(f) + 1)
        if (int(mask) & M_CLAW) and not ((pm_ or 0) & M_CLAW):
            row["claw"] = [str(own), [[ob.iid % 1000, ob.st, ob.j, round(float(ob.x), 2), ob.face]
                                      for ob in self.trk.obs()]]
        self.sent_hist[int(f) + 2] = int(mask)
        self.own_hist[int(f) + 2] = str(own)
        if len(self.sent_hist) > 240:
            for k in [k for k in self.sent_hist if k < f - 180]:
                del self.sent_hist[k]
            for k in [k for k in self.own_hist if k < f - 180]:
                del self.own_hist[k]
        if bridge:
            kind = own if own in ("plan", "m2") else "script"
            self.bridges.append([kind, int(f) + 3, list(bridge), 0, True])
            if len(self.bridges) > 80:
                self.bridges = self.bridges[-80:]
        busy = self._busy(fo, raw)
        ctrl_t = None if self.ctrl is None else (self.ctrl.pid, int(self.ctrl.t_a))
        note_key = (self.ep, None if ctrl_t is None else ctrl_t[0], "hit" in self.trig)
        if self.in_qs and (note_key != self._note_key or self.new_plan_obj is not None):
            # a note to every worker (busy ones too): the plan in control (its plan for the kept-plan check) and her
            # hit - a search from before them is cut
            note = {"note": True, "ep": self.ep, "ctrl": ctrl_t, "trig": sorted(set(self.trig))}
            ld = self.last_drop
            if self.cfg.drop_keep and ctrl_t is None and "hit" not in self.trig and ld is not None and \
                    ld[0] == int(self._fo_prev) and ld[1] in ("clappers", "hero", "end", "end_dev"):
                note["keep"] = True             # M4d2: the searches from the dropped plan's bridge go on
                self._inc("drop_keep")
            if self.new_plan_obj is not None and self.ctrl is not None:
                note["plan_obj"] = self.new_plan_obj
            self.new_plan_obj = None
            self._note_key = note_key
            for i, q in enumerate(self.in_qs):
                if i < len(self.procs) and not self.procs[i].is_alive():
                    continue                    # (M4d: not into a dead worker's queue)
                q.put(note)
        obs_now = self.trk.obs()
        row["nc"] = len(obs_now)
        # (the workers alive and warmed: a restarted one warming up does not hold the others' snapshots back)
        alive = [i for i in range(len(self.in_qs)) if i >= len(self.procs) or
                 (self.procs[i].is_alive() and (i in self.ready or not self.ready))]
        idle = [i for i in alive if not self.idles or self.idles[i].value == 1]
        rev = False
        if self.rev_new is not None:
            if not self.cfg.rev_cut or fo - self.rev_new[0] > self.cfg.rev_wait:
                if self.cfg.rev_cut:
                    self._inc("rev_expired")
                self.rev_new = None
            elif not busy and obs_now and alive:
                rev = True                      # M4d2: the newest snapshot to every worker now, their searches cut
        if rev:
            want = alive
        elif self.cfg.sync and self.idles:
            want = alive if (alive and len(idle) == len(alive)) else []
        else:
            want = idle
        if want and not busy and (not self.idles or obs_now):
            m_ = int(mask) & ~COG if own == "cog" else int(mask)
            short = rev or self._short_next
            self._short_next = False
            if short:
                if not rev:
                    self._inc("short_sent")
                bridge = list(bridge)[:self.cfg.rev_lead]
                presses = [p_ for p_ in presses if p_[0] < int(f) + 3 + self.cfg.rev_lead]
            snap = {"seq": self.seq, "ep": self.ep, "f": int(f), "fo": int(fo), "S": S0.copy(),
                    "cmds": np.concatenate([np.asarray(inflight, np.int64), [m_],
                                            np.asarray(bridge, np.int64)]).astype(np.int64),
                    "n_inflight": len(inflight) + 1, "hold": self._hold_clean(hold_tuple(hold), fo),
                    "lat_s": int((raw.get("act") or {}).get("mask") or 0) & (~COG if self._cog_near(fo) else -1),
                    "presses": presses,
                    "obs": obs_now, "mems": self.trk.mems(), "hazards": self.trk.hazards(self.K),
                    "ctrl": None if self.ctrl is None else (self.ctrl.pid, int(self.ctrl.t_a)),
                    "trig": sorted(set(self.trig)), "busy": busy, "own": own,
                    # M4d2: the wall time (the worker's deadline), the plan in control's frames left (alt), the cut
                    "t_wall": time.time(), "left": None if self.ctrl is None else int(self._left(fo)),
                    "rev": bool(rev),
                    # M4 S1: her last Clawline's control while its lock lasts (control + 13)
                    "claw_ctl": self._claw_ctl if (self.cfg.press_check and self._claw_ctl is not None and
                                                   self._claw_ctl + press.CLAW_LOCK_F > int(fo)) else None}
            if rev:
                snap["cut"] = self.seq - 1      # every search from an older snapshot is cut (the reader's rule)
                self.rev_log.append([int(self.rev_new[0]), *self.rev_new[1], self.seq, int(f)])
                row["rev_sent"] = [self.seq, int(self.rev_new[0])]
                self._inc("rev_sent")
                self.rev_new = None
            for i in want:
                self.in_qs[i].put(snap)
                if self.idles:
                    self.idles[i].value = 0
            res_cmd_ = [m_] + [int(x) for x in bridge]
            if own == "plan" and res_cmd is not None and len(res_cmd) > 1 and int(res_cmd[0]) == int(mask):
                res_cmd_ = [int(x) for x in np.asarray(res_cmd, np.int64)]
            self.snaps_out[self.seq] = {"f": int(f), "k0": int(f) + 3, "k2": int(f) + 2, "bridge": list(bridge),
                                        "res_cmd": res_cmd_, "own": str(own), "parts": set(want), "rev": bool(rev)}
            if len(self.snaps_out) > 64:
                for k_ in sorted(self.snaps_out)[:-64]:
                    del self.snaps_out[k_]
            self.seq += 1
            self._inc("snapshots")
        if self.trig:
            row["trig"] = sorted(set(self.trig))
        if busy:
            row["busy"] = busy
            if busy == "no input":
                row["clip"] = str((((raw.get("hero") or {}).get("anim") or {}).get("clip")) or "")
        if self.pending:
            row["pend"] = len(self.pending)
        if self.last_msg:
            row["w"] = self.last_msg
            self.last_msg = {}
        self.trig = []
        ms_ = (time.perf_counter() - t0) * 1e3
        self._tm("post", ms_)
        row["ms"] = round((self.ms_pre[-1] if self.ms_pre and self.row is row else 0.0) + ms_, 2)
        if self.cfg.log:
            self.rows.append(row)
        self.row = {}

    def _check_bridges(self, f: int, fo: int, mask: int, own: str, row: dict) -> None:
        """M4d2: the key sent for f + 2 against every pending search's bridge (a snapshot with a part not answered):
        a different key breaks it - those searches are cut (a note: their prefix will not be played) and their
        workers start from the newest snapshot. The hold's audit: the held key followed or not."""
        k = int(f) + 2
        if self._hold is not None:
            ok_ = int(mask) == int(self._hold[1])
            self._inc("hold_" + ("followed" if ok_ else "broken"))
            if not ok_:
                row["hold_broken"] = [self._hold[0], str(own)]
        cut = None
        pend = {getattr(x, "seq", None) for x in self.pending}
        for seq, d in self.snaps_out.items():
            if not (d["parts"] or seq in pend) or d.get("broken"):
                continue
            j = k - d["k0"]
            if 0 <= j < len(d["bridge"]) and int(d["bridge"][j]) != int(mask):
                d["broken"] = True
                self._inc("bridge_cut_" + str(d["own"]).split(":")[0])
                cut = seq if cut is None else max(cut, seq)
        if cut is not None and self.cfg.fb_hold and self.cfg.break_cut and self.in_qs:
            note = {"note": True, "ep": self.ep, "cut": int(cut), "trig": [],
                    "ctrl": None if self.ctrl is None else (self.ctrl.pid, int(self.ctrl.t_a))}
            for i, q in enumerate(self.in_qs):
                if i < len(self.procs) and not self.procs[i].is_alive():
                    continue
                q.put(note)
            row["cut_seq"] = int(cut)

    def _bridge_audit(self, f: int, mask: int) -> None:
        """The keys the bridges expected against the key sent for frame f + 2: per bridge the frames followed before
        the first difference (or all of them)."""
        k = int(f) + 2
        keep = []
        for b in self.bridges:
            kind, k0, keys, n, alive = b
            if not alive:
                continue
            if k0 <= k < k0 + len(keys):
                if int(keys[k - k0]) == mask:
                    b[3] += 1
                    if b[3] == len(keys):
                        self.bridge_hist[kind][len(keys)] += 1
                        continue
                else:
                    self.bridge_hist[kind][n] += 1
                    continue
            keep.append(b)
        self.bridges = keep

    def yield_sup(self, f: int, fo: int) -> None:
        """A pause tick of the supervisor: map2 drops its plan."""
        try:
            self._drop("sup")
            self._inc("ticks")
            self._inc("ticks_pause")
            if self.cfg.log:
                self.rows.append({"f": int(f), "fo": int(fo), "own": "sup", "why": "pause", "m2": 0})
        except Exception as e:  # noqa: BLE001
            self._error("pause", e)

    # ---- logs and stats ----
    def flush(self) -> None:
        if self.log_path is None or not self.rows:
            self.rows = []
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            for r in self.rows:
                fh.write(json.dumps({"ep": self.ep, **r}, default=_jdefault) + "\n")
        self.rows = []

    def stats(self) -> dict:
        """THIS EPISODE's counters and times (M4d: an attempt row is one episode - M4c's counters and times added up
        over the controller's life, one combat_run chunk of 4 episodes: summing the rows counted episode 1 four
        times), the run's in run_counts / run; the workers, the first errors (the per-tick rows are flushed to the
        log). 'episode' (M4c's per-episode block) is kept: the same counters with the episode number."""
        try:
            self.flush()
        except Exception as e:  # noqa: BLE001
            self._error("flush", e)
        st, ep = dict(self.st), dict(self.ep_c)
        rm = self.run_ms
        return {"cfg": self.cfg.as_dict(), "ep": self.ep, "counts": ep, "run_counts": st,
                "episode": {"ep": self.ep, **ep},
                "share_m2": round(ep.get("ticks_m2", 0) / max(1, ep.get("ticks", 0)), 4),
                "pre_ms_p50": _pct(self.ms_pre, 50), "pre_ms_p99": _pct(self.ms_pre, 99),
                "post_ms_p50": _pct(self.ms_post, 50), "post_ms_p99": _pct(self.ms_post, 99),
                "check_ms_p50": _pct(self.ms_check, 50), "check_ms_p99": _pct(self.ms_check, 99),
                "search_ms_p50": _pct(self.lat, 50), "search_ms_p90": _pct(self.lat, 90),
                "commit_age_p50": _pct(self.age_commit, 50), "commit_age_p90": _pct(self.age_commit, 90),
                "bridge_followed": {k: dict(sorted(v.items())) for k, v in self.bridge_hist.items()},
                "run": {"share_m2": round(st.get("ticks_m2", 0) / max(1, st.get("ticks", 0)), 4),
                        "pre_ms_p50": _pct(rm["pre"], 50), "pre_ms_p99": _pct(rm["pre"], 99),
                        "check_ms_p99": _pct(rm["check"], 99), "search_ms_p50": _pct(rm["search"], 50),
                        "search_ms_p90": _pct(rm["search"], 90)},
                "disabled": bool(self.disabled),
                "workers": {str(k): v for k, v in self.ready.items()}, "errors": self.errors[:20]}


def _jdefault(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    return str(o)


__all__ = ["enabled", "LiveCfg", "Map2Controller", "LivePlan", "OutData", "commit_check", "build_prefix",
           "reanchor_prev", "reanchor_outcome", "outcome_cmds", "hold_filter1", "worker_main", "build_outs"]
