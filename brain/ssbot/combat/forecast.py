"""Threat forecast (M2 W3; DESIGN §3.5.3 support vs probability, §3.5.4 `tubes = forecast(s, H)`, §3.9.2 the
vision-equivalent view): from the WorldState and the boss's knowledge files, where the boss's attacks can be over the
next H seconds.

    fc = Forecaster(BossModel.load("BellBeast"), view=ORACLE)       # or VISION_EQUIVALENT; margin for the hurtbox
    fc.reset(); fc.notify_wake(t_game)                              # every episode; the fight start (bot-observable)
    fc.update(ws)                                                   # every WorldState, in order
    f = fc.forecast(horizon_s=0.8)                                  # origin: ws.stamp.t_game_s
    hit = f.occupied(x, y, tk)                                      # [N, T] bool: hero collider centres at tk s
    p = f.prob(x, y, tk)                                            # [N] probability of contact (scoring only)
    f.support_set(...)                                              # SupportSet for the supervisor (hits_to_death)

Two outputs (§3.5.3). Support, conservative: the union over every branch the behaviour table has ever logged
(support_transitions), every logged dwell (min..max) and every logged instance's colliders, so it must cover every
logged contact; it decides S(c). Probability, for scoring only: each branch weighted by the table's smoothed
transition probabilities (Bell Burst? by fight phase, Rage? by the HP rule), P(c) = sum over leaves of p * contact.

How. The space-time templates of ssbot.knowledge.hitbox_tables are per Control state ("support/<family>/<state>/
<frame>", t from the state's entry; "_tail" from the attack's end, for what outlives it: the attack bells, DropBell
M2), already dilated by the validated contact residual and +-1 bin of export lag; SupportQuery dilates them by the
hero hurtbox plus a margin, so a point test of the hurtbox centre is an overlap test. The forecaster walks the Control
graph from the current state: each state's entry is an interval (the logged dwell min / max of the states before it
accumulate), and the state's template is placed once per 1/60 s bin of that interval (each placement keeps its own
+-1 bin for the export lag). Branches (burst / charge / leap, left / right, rage) are all placed; the walk stops past
the horizon. An attack's anchor is used when it is known (Set L / Set R fixed at x 75.03 / 95.72, the rage at 86.21;
a burst's from the boss's hidden x underground, which is its anchor: live runs 2026-10-02, 81 of 81 bursts and 336 of
336 charges / leaps exactly; in the vision view from its first drawn frame), else the world_all template of the state
(every logged anchor). The horizon is the caller's: at least 0.8 s (the policy asks 2 s: the Bind macro, the tactics'
risk map and the planner's adaptive horizon through a charge).
Tails: an attack that ends into the decision chain leaves the boss underground, so only what outlives it is placed
from its end (attack bells, DropBell M2 in P2); the tail templates also hold the body of instances killed mid-attack,
placed only after a death. A tracker that starts mid-attack (the start state missed) roots the walk in every family
with that state. Drop bells (oracle view): they hang in the export all fight and arm (FSM out of Dormant) at least
1.2 s before they can hurt, so an armed bell gets its own self template at its arming position and time, and the
drop-bell unions of the rage pattern and of P2 (Ptn L / R, Rage End, the M2 world templates) count only from that lead
on (Placement.t_from); a bell seen armed without its arming makes them count from the start again.

Measured (stage A, ssbot.tools.support_recall, 2026-10-02): a held-out behaviour build without live recordings i2_002 /
i3_002 and the trial run (C:/ssbot/data/m2_heldout/tables), contacts of those fights (every "damage" frame and every
frame of a "damage_blocked" stretch) inside the support forecast L frames earlier, box of frame c or c - 1 (the
planner's pairing), margin 0: 35 live fights 23,896 / 23,896 and 2 trial fights 1,795 / 1,795 for L = 2, 3 and 4, in
both views.

Views. ORACLE: the Control FSM state and time in state (Entity.phase, and the FSM_TRANSITION events, which also arrive
while the boss is not exported: before its first emergence). VISION_EQUIVALENT: the observable phase
(ssbot.core.bosses.BELL_BEAST_PHASES) with the time since it changed, the boss's position and facing while drawn, and
memory: "recover" is the end of a charge or of a leap (the phase before it says which), "hidden" after "recover" is
Submerged, after "burst" Burst Recovery (the bells still rolling), after "roar_end" Rage Submerge, and before the first
emergence the wake chain (Submerged Init 2.0 s, then a charge from the right: the first attack of every logged fight).
An observable phase's entry is known to +-1 frame (a transition frame can show the next clip early), a hidden boss's
position is unknown (both charge / leap anchors, the burst's world_all), a burst's anchor comes from the box centre
(fixed offset +-0.539, -2.68 by flipX, on its first drawn frame only: the box follows the sprite frames after it), a
charge's or leap's from its facing.
A boss lost over the image edge (a ghost: no phase) coasts: the last known state stays the root, and its successors
come in as their entry intervals pass.

Time. Templates count game time (1/60 s bins; game time stands still in hit-stop and pauses); offsets are game seconds
from the WorldState's frame (stamp.t_game_s). The planner's rollout frame k is at tk = k * frame_time.
"""
import functools
import json
import math
import os
from pathlib import Path
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import NamedTuple

import numpy as np

from ssbot.combat.bell_track import ATK_BELL, AtkBellTracks, DropBellTracks, SKIN_Z
from ssbot.combat.boss_model import TAIL, Anchor, BossModel
from ssbot.combat.fastquery import circle_hits, query_par
from ssbot.combat.pogo_targets import CERT_MARGIN_U, CERT_MAX_S, TargetPath, TargetTracker, simulate
from ssbot.core.bosses import BELL_BEAST_PHASES as VE_PHASE_OF
from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT, Entity, Ev, WorldState
from ssbot.knowledge import hitbox_tables as hb
from ssbot.safety.hits_to_death import SupportEvent, SupportSet

BIN = hb.BIN_S
MIN_HORIZON_S = 0.8
SUP_HORIZON_S = 0.8          # what the supervisor's support covers (hits_to_death's worst event "now")
VE_ENTRY_SLACK = 1           # bins of slack on an observable phase's entry (a transition frame shows a clip early)
FUSE_N = 10                  # VE: detections the boss's box x is averaged over (BossTracker.fused_pos) ...
FUSE_N_Y = 30                # ... and its y (the mean path's height is flat along a charge, its x grows less exact)
MAX_NODES = 400
HIDDEN, UNKNOWN = "hidden", "unknown"
DROP_BELL = "BoneBeast DropBell"
# the exact path's time slack: a hit lands in the physics step after the recorded position (fixture hit 62131: the bell
# 0.11 u short of the hurtbox in the hit frame's STATE), and hit-stop frames still step (game time vs steps, 0.37 u)
DET_SLACK_S = (-0.04, -0.02, 0.0, 0.02, 0.04)
# contact skin: held-out hit i3_002 f 603438 registered with the bell circle 0.004 u short of the recorded hurtbox
# (Box2D contact offset and polygon skin); the logged unions carry such slack implicitly
DET_SKIN_U = 0.1
# held-out recall (support_recall i2_002 / i3_002, held-out tables, lags 2-4, oracle): 100 % with the Submerge sink and
# the skin (28 misses before: a resting Submerge, contact skin)
DET_REPLACE = os.environ.get("SSBOT_DET_BELLS", "1") != "0"   # SSBOT_DET_BELLS=0: the logged unions (A/B)
# the vision view's drop-bell paths from their tracks (bell_track; SSBOT_DET_VE=0: the self templates, the A/B before)
DET_VE = os.environ.get("SSBOT_DET_VE", "1") != "0"
# the vision view's attack-bell paths from their tracks (bell_track.AtkBellTracks): a burst whose two bells are both on
# exact paths drops the attack-bell unions of its Burst Recovery and tail (SSBOT_DET_ATK=0: the unions, the A/B before)
DET_ATK = os.environ.get("SSBOT_DET_ATK", "1") != "0"
ATK_LAUNCH_STATE = "Burst Out"     # the boss's state on the attack bells' Launch frame (100 of 100, 20261002_171806 i0)
ATK_ANCHOR_TOL_U = 0.5             # a pair's middle this close to a burst's anchor is that burst's pair
ATK_LAG_SLACK_S = 0.05
# the vision view's hit targets (a down spike bounces off a bell, a slash recoils from it) from the bells on exact paths
# (Forecast.det): the certain circle shrinks by this much more than the oracle's (the track's centre error, p99 0.29 u
# at tk 0 and max 0.51 u: the 50 Hz step phase, bell_track_audit --kind atk on 20261002_171806), and a drop bell counts
# only while it falls (a down spike on a rising one clamps its vy: TINK DOWN), never for a side slash's redirect (the
# track does not follow a tinked bell: bell_track withdraws it). Off by default (SSBOT_VE_TARGETS=1 turns it on): on
# a recorded fight replayed in degraded_dust (view_compare 20261002_171806 i0 ep2) it generated bell pogos (0.34 per
# Ptn R tick, 6.1 per Burst Recovery tick) but accepted none and left FORCED_RISK unchanged; not yet run live
VE_TARGETS = os.environ.get("SSBOT_VE_TARGETS", "0") == "1"
VE_CERT_EXTRA_U = 0.35
# the vision view's HP is the hits it saw: a hit it missed leaves the count high, so just above the rage HP the rage is
# still likely (scoring only: the support always keeps Rage Pos while it is possible). Live degraded_dust run
# 20261002_224934 i1 ep8: the view counted 80 HP at the decision (the boss had 75), p_rage 0, and FORCED_RISK ranked
# the rage's eruption point (86.21, the hidden stance next to it) as the least likely contact; the rage burst hit
VE_RAGE_HP_SLACK = 10.0
VE_RAGE_P = 0.5
# the vision view's certain boss form only until its observable phase can end (SSBOT_CERT_PHASE_CUT=0: diagnostics)
CERT_PHASE_CUT = os.environ.get("SSBOT_CERT_PHASE_CUT", "1") != "0"
# the vision view's boss box changes its shape along the horizon (the hurtbox table's bin at the time in the phase +
# tk, not the origin's): a charge's end shrinks and sinks into Dig In within 0.6 s (SSBOT_SHAPE_T=0: the origin's shape
# for the whole horizon, the A/B before)
SHAPE_T = os.environ.get("SSBOT_SHAPE_T", "1") != "0"
HURT_BIN_S = 0.1             # the hurtbox table's time bins (ssbot.tools.hurtbox_table BIN_S)
MARGIN_BIN_S = 0.1           # the pogo gate's margins per time bin in the phase (boss_path_audit --margins "_tau")
DET_STATES = frozenset({"Drop", "Air", "Bounce Up", "Bounce Air", "Submerge", "Tink Right", "Tink R Min", "Tink Left",
                        "Tink L Min", "Tink D", "Tink Right 2", "Tink R Min 2", "Tink Left 2", "Tink L Min 2", "Tink D 2"})   # world-fixed hazards with self templates (entities.<tk>.self_template)
REST_STATES = ("Init", "Dormant")
BELL_TTL_S = 8.0                   # a disarmed bell (left the export, back to Dormant) is forgotten after this

# observable phase -> the Control state its first frame is (the root of the forecast walk)
PHASE_ROOT = {"emerge": "Charge Emerge", "charge_antic": "Charge Antic", "charge": "Charge", "leap": "Leap Out",
              "burst": "Burst Out", "roar": "Rage Burst", "roar_end": "Roar End", "burst_tell": "Burst Antic",
              "dust_low": "Emerge Antic C", "dust_tall": "Emerge Antic L", "dust_burst": "Burst Antic"}
PHASE_FAMILY = {"emerge": "BB_CHARGE", "charge_antic": "BB_CHARGE", "charge": "BB_CHARGE", "leap": "BB_LEAP",
                "burst": "BB_BURST", "roar": "BB_RAGE", "roar_end": "BB_RAGE", "burst_tell": "BB_BURST",
                "dust_low": "BB_CHARGE", "dust_tall": "BB_LEAP", "dust_burst": "BB_BURST"}
# Underground cues (ObservabilityFilter tells; hypotheses until M3 measures tell_lead_vision in shadow mode). The
# entity's x is the hidden transform's: the burst anchor (oracle view: 81 of 81 bursts) or the emergence anchor.
# Screenshots C:/ssbot/sandbox/m2_tells (ssbot.probes.m2_tells): nothing at +0.1 s, dust where it will come up from
# +0.3 s after Emerge Antic C / L and Burst Antic; low for a charge, a tall column with debris for a leap, told apart
# for certain at +0.6 s. "dust": at an anchor, charge or leap not yet told; "dust_low" / "dust_tall": a charge / a
# leap; "dust_burst": inside the burst range (bursts erupt at x 81.2-91.2, charges and leaps at the anchors 75.03 /
# 95.72). The antic began TELL_DELAY before the cue, give or take TELL_SLACK_S (when vision would first see it).
# "burst_tell": the burst position from the antic's first frame, the first experiment (run 20261002_061942).
TELL_PHASES = frozenset(("burst_tell", "dust", "dust_low", "dust_tall", "dust_burst"))
EMERGE_TELLS = frozenset(("dust", "dust_low", "dust_tall"))
TELL_DELAY = {"burst_tell": 0.0, "dust": 0.3, "dust_low": 0.6, "dust_tall": 0.6, "dust_burst": 0.3, "bell_dust": 0.3}
TELL_SLACK_S = {"burst_tell": BIN, "dust": 0.1, "dust_low": 0.1, "dust_tall": 0.1, "dust_burst": 0.1,
                "bell_dust": 0.1}
# A drop bell's cue: a narrow dust column from the ceiling at its x, from +0.3 s after it arms (Antic; none at +0.1 s;
# it falls about 1.25 s after arming), screenshots C:/ssbot/sandbox/m2_tells DropBell_*. The vision view places its
# self template from the cue (arming TELL_DELAY earlier, +-TELL_SLACK_S) like the oracle view does from the FSM.
# A cue's x is the mean of its detections (SimpleNoise: as noisy as any detection). The vision view's planner margin
# (planner_policy: NOISE_K x hypot(hero sigma, boss sigma 0.10)) covers a placement x this uncertain (1 sigma); a cue
# seen in fewer frames is placed at its x +- SKIN_Z sigma as well.
CUE_SIGMA_COVERED = 0.10
DUST_ROOTS = (("BB_CHARGE", "Emerge Antic C"), ("BB_LEAP", "Emerge Antic L"))
RECOVER_ROOT = {"BB_CHARGE": "Charge End", "BB_LEAP": "Leap Land"}
# the state a hidden phase starts in, by the last drawn family (None: before the first emergence)
HIDE_ROOT = {"BB_CHARGE": "Submerged", "BB_LEAP": "Submerged", "BB_BURST": "Burst Recovery", "BB_RAGE": "Rage Submerge"}


class DetBell(NamedTuple):
    """A bell on an exact path: its state (x, y, vx, vy, the index of its next bounce, the Submerge time left)
    at path time t0 (the forecast origin is path time t0: 0 for the oracle view's logged state, the time since the
    drop for the vision view's track estimate), the bounce sides still open (None: both when the next bounce is
    random) and an extra contact skin (the vision view's x uncertainty)."""
    sp: object
    x: float
    y: float
    vx: float
    vy: float
    nb: int
    rest: float | None
    type_key: str
    t0: float = 0.0
    sides: tuple | None = None
    skin: float = 0.0
    life: float | None = None      # path time its collider goes off (an attack bell's End Timer), None: never

    def branch_sides(self) -> tuple:
        if self.sides is not None:
            return self.sides
        b = self.sp.bounces
        return (1, -1) if self.nb < len(b) and b[self.nb].get("vx") == "random" else (0,)


@dataclass(slots=True)
class Ctx:
    """What the walk knows about the attack it is in and the fight."""
    family: str | None = None
    direction: str | None = None       # "Set L" | "Set R" | "-" (first attack) | None
    anchor: Anchor | None = None
    phase: str | None = None           # "P1" | "P2" | None (unknown)
    raged: bool | None = None
    hp: float | None = None


@dataclass(slots=True)
class Node:
    id: int
    state: str
    e_lo: float                        # entry interval, game s from the origin
    e_hi: float
    family: str | None
    p: float                           # probability of the path to here
    parent: int
    anchor: Anchor | None = None


@dataclass(slots=True)
class Placement:
    key: str
    t_ref: float                       # template time at the origin
    anchor: tuple[float, float] | None
    mirror: int
    node: int
    t_on: float                        # active interval relative to the origin
    t_off: float
    sources: frozenset[str]
    t_from: float = -math.inf          # ignored for query times before this (drop-bell unions, see Forecaster)


@dataclass(slots=True)
class Root:
    state: str
    e_lo: float
    e_hi: float
    ctx: Ctx
    p: float = 1.0
    current: bool = False              # the state is known to be the current one (its exit is after the origin)


class Forecast:
    """One tick's tubes. Placements are SupportQuery placements of planner templates; nodes the walk's tree."""

    def __init__(self, fc: "Forecaster", origin_t: float, horizon: float, nodes: list[Node],
                 placements: list[Placement], known: bool, roots: list[Root], boss: Entity | None):
        self.fc = fc
        self.origin_t = origin_t
        self.horizon = horizon
        self.nodes = nodes
        self.placements = placements
        self.known = known
        self.roots = roots
        self.boss = boss
        self.det: list = []           # drop bells on exact paths (Forecaster._det_bell)
        self.truncated = 0            # walk branches inside the horizon cut by MAX_NODES / depth
        self._paths: dict = {}        # drop-bell path cache (_bell_path)
        kids = {}
        for n in nodes:
            kids.setdefault(n.parent, []).append(n.id)
        self.leaves = [n.id for n in nodes if n.id not in kids]

    # ---- queries ------------------------------------------------------------------------------------------------

    def _query(self, placements: Iterable[Placement], comfort: bool = False) -> hb.SupportQuery:
        q = self.fc.query_c if comfort and self.fc.query_c is not None else self.fc.query
        q.clear()
        for p in placements:
            q.place(p.key, p.t_ref, p.anchor, p.mirror)
        return q

    def _occ(self, placements: list[Placement], x, y, tk: np.ndarray, comfort: bool = False) -> np.ndarray:
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        out = np.zeros(x.shape, bool)
        cuts = sorted({p.t_from for p in placements if tk[0] < p.t_from <= tk[-1]})
        edges = [-math.inf] + cuts + [math.inf]
        for a, b in zip(edges, edges[1:]):
            sel = np.flatnonzero((tk >= a) & (tk < b))
            if not len(sel):
                continue
            t_lo, t_hi = tk[sel[0]], tk[sel[-1]]
            act = [p for p in placements if p.t_from <= t_lo and p.t_off >= t_lo - BIN and p.t_on <= t_hi + BIN]
            if not act:
                continue
            q = self._query(act, comfort)
            xs, ys, ts = x[:, sel], y[:, sel], tk[sel]
            out[:, sel] = query_par(q, xs, ys, ts)
        return out

    def occupied(self, x, y, tk, comfort: bool = False) -> np.ndarray:
        """[N, T] bool: the hurtbox (grown by the forecaster's margin) centred at (x, y) [N, T] at tk [T] game s from
        the origin overlaps some support tube. comfort: against the templates grown by the comfort margin too (the
        planner's preference for clearance; Forecaster(comfort=...))."""
        tk = np.asarray(tk, np.float64)
        out = self._occ(self.placements, x, y, tk, comfort)
        if self.det:
            out |= self._det_occ(np.asarray(x, np.float64), np.asarray(y, np.float64), tk, comfort)
        return out

    def _det_occ(self, x, y, tk: np.ndarray, comfort: bool = False, exclude: str | None = None,
                 only: str | None = None) -> np.ndarray:
        """Contact with the drop bells on exact paths (Forecaster._det_bell): the hurtbox grown like the templates'
        dilation (comfort: and the comfort margin) meets the bell's circle on either bounce branch."""
        out = np.zeros(np.shape(x), bool)
        hx, hy = self.fc.half
        if comfort and self.fc.comfort is not None:
            hx, hy = hx + self.fc.comfort[0], hy + self.fc.comfort[1]
        by_r: dict = {}
        for j, d in enumerate(self.det):
            tk_ = d.type_key
            if exclude is not None and tk_.endswith(exclude) or only is not None and tk_ != only:
                continue
            for sd in d.branch_sides():
                for dt in DET_SLACK_S:
                    by_r.setdefault(d.sp.r + DET_SKIN_U + d.skin, []).append(self._bell_path(j, sd, dt, tk))
        if not by_r:
            return out
        shp = out.shape
        T = shp[-1] if len(shp) else 1
        # writable copies: a read-only view (broadcast_to) is another numba specialization, compiled mid-fight
        x2 = np.require(np.broadcast_to(np.asarray(x, np.float64), shp).reshape(-1, T), np.float64, ["C", "W"])
        y2 = np.require(np.broadcast_to(np.asarray(y, np.float64), shp).reshape(-1, T), np.float64, ["C", "W"])
        flat = out.reshape(-1, T)
        for rr, paths in by_r.items():
            cx = np.ascontiguousarray([np.broadcast_to(np.asarray(p[0], np.float64), (T,)) for p in paths])
            cy = np.ascontiguousarray([np.broadcast_to(np.asarray(p[1], np.float64), (T,)) for p in paths])
            ok = np.ascontiguousarray([np.broadcast_to(np.asarray(p[2], np.bool_), (T,)) for p in paths])
            flat |= circle_hits(x2, y2, cx, cy, ok, float(hx), float(hy), float(rr))
        return flat.reshape(shp)

    def _bell_path(self, j: int, sd: int, dt: float, tk: np.ndarray, redirect: tuple | None = None):
        """Drop bell j's centre (x, y, ok) at tk + dt on bounce side sd (or knocked aside: redirect = (t_hit, d)),
        cached per forecast: the planner asks the same times for every candidate block of a tick (pogo_targets.simulate
        was 135,499 calls, 5.5 s of an 8,000-tick bench before the cache)."""
        key = (j, sd, dt, len(tk), float(tk[0]), float(tk[-1]), redirect)
        r = self._paths.get(key)
        if r is None:
            sp, bx, by, vx, vy, nb, rest, _, t0 = self.det[j][:9]
            life = self.det[j].life
            t = np.maximum(tk + dt + t0, 0.0)
            if redirect is not None:
                r = simulate(sp, bx, by, vx, vy, nb, life, t, side=sd, redirect=(redirect[0] + t0, redirect[1]))
            else:
                if rest is not None:
                    nb = len(sp.bounces)          # in Submerge: sinking, no more floor contacts
                r = simulate(sp, bx, by, vx, vy, nb, rest if rest is not None else life, t, side=sd)
            self._paths[key] = r
        return r

    def redirect_occ(self, x, y, tk, type_key: str, t_hit: float, d: int, comfort: bool = False
                     ) -> np.ndarray | None:
        """Contact with the drop bell `type_key` on its one path after a side slash moving d (+1 right) at t_hit;
        None when not applicable (not on an exact path, resting, or no side redirect in its registry entry)."""
        j = next((i for i, e in enumerate(self.det) if e.type_key == type_key), None)
        if j is None:
            return None
        sp, rest = self.det[j].sp, self.det[j].rest
        if rest is not None or "side" not in sp.redirect:
            return None
        tk = np.asarray(tk, np.float64)
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        hx, hy = self.fc.half
        if comfort and self.fc.comfort is not None:
            hx, hy = hx + self.fc.comfort[0], hy + self.fc.comfort[1]
        rr = sp.r + DET_SKIN_U + self.det[j].skin
        out = np.zeros(x.shape, bool)
        for dt in DET_SLACK_S:
            cx, cy, ok = self._bell_path(j, d, dt, tk, (t_hit, d))
            dx = np.maximum(np.abs(x - cx) - hx, 0.0)
            dy = np.maximum(np.abs(y - cy) - hy, 0.0)
            out |= ((dx * dx + dy * dy) <= rr * rr) & ok
        return out

    def occupied_redirect(self, x, y, tk, type_key: str, t_hit: float, d: int, comfort: bool = False
                          ) -> np.ndarray | None:
        """occupied() with the drop bell `type_key` knocked aside at t_hit by a side slash moving d (+1 right): its
        own placements replaced by its one redirected path (pogo_targets.simulate redirect). None: not applicable (the
        bell is not on an exact path, or its random bounce comes before the hit). comfort: as occupied()."""
        one = self.redirect_occ(x, y, tk, type_key, t_hit, d, comfort)
        if one is None:
            return None
        return self.occupied_without(x, y, tk, type_key, comfort) | one

    def occupied_without(self, x, y, tk, exclude: str, comfort: bool = False) -> np.ndarray:
        """occupied() without the placements whose only source is the entity type `exclude` (a bell disarmed by a
        down attack: its DamageHero cooldown; a placement shared with other sources still counts)."""
        pl = [p for p in self.placements if not (p.sources and all(src.endswith(exclude) for src in p.sources))]
        tk = np.asarray(tk, np.float64)
        out = self._occ(pl, x, y, tk, comfort)
        if self.det:
            out |= self._det_occ(np.asarray(x, np.float64), np.asarray(y, np.float64), tk, comfort, exclude=exclude)
        return out

    def node_hits(self, x, y, tk) -> np.ndarray:
        """[nodes, N] bool: contact with each node's own placements."""
        x = np.asarray(x, np.float64)
        tk = np.asarray(tk, np.float64)
        out = np.zeros((len(self.nodes), x.shape[0]), bool)
        by_node: dict[int, list[Placement]] = {}
        for p in self.placements:
            by_node.setdefault(p.node, []).append(p)
        for nid, ps in by_node.items():
            out[nid] = self._occ(ps, x, y, tk).any(axis=1)
        return out

    def prob(self, x, y, tk) -> np.ndarray:
        """[N]: sum over the walk's leaves of p(leaf) * (contact with a placement on its path); scoring only."""
        x = np.asarray(x, np.float64)
        nh = self.node_hits(x, y, tk)
        p = np.zeros(x.shape[0])
        parent = {n.id: n.parent for n in self.nodes}
        for leaf in self.leaves:
            hit = np.zeros(x.shape[0], bool)
            nid = leaf
            while nid >= 0:
                hit |= nh[nid]
                nid = parent[nid]
            p += self.nodes[leaf].p * hit
        return np.minimum(p, 1.0)

    def t_min(self, x: float, y: float, t_max: float = 3.0) -> float:
        """Earliest game time (s from the origin) at which a support tube reaches a hurtbox standing at (x, y);
        inf when none does within t_max (the Bind commit test's T_min, §3.5.6)."""
        tk = np.arange(0, int(t_max / BIN) + 1) * BIN
        hit = self.occupied(np.full((1, len(tk)), x), np.full((1, len(tk)), y), tk)[0]
        i = np.flatnonzero(hit)
        return float(tk[i[0]]) if len(i) else math.inf

    def committed(self) -> "Forecast":
        """The same forecast restricted to what is already decided: the current attack up to the next decision
        state, its tail, ended attacks' tails and armed bells (scoring and tactics only; the support is all of it).
        In the vision view underground, the next attack's union covers the whole floor; this part does not."""
        dec = set(self.fc.model.decision_states)
        pre: dict[int, bool] = {}
        for n in self.nodes:                    # the walk appends a parent before its children
            pre[n.id] = (n.parent < 0 or pre.get(n.parent, False)) and n.state not in dec
        kept = [p for p in self.placements if pre.get(p.node, False)]
        out = Forecast(self.fc, self.origin_t, self.horizon, self.nodes, kept, self.known, self.roots, self.boss)
        # armed bells on exact paths are decided too (their self templates are not placed: without them the tactics'
        # underground risk map did not see a falling drop bell at all)
        out.det = self.det
        out._paths = self._paths
        return out

    def active_sources(self, t0: float = 0.0, t1: float = SUP_HORIZON_S) -> frozenset[str]:
        out: set[str] = set()
        for p in self.placements:
            if p.t_off >= t0 and max(p.t_on, p.t_from) <= t1:
                out |= p.sources
        return frozenset(out)

    def support_set(self, ws: WorldState | None = None, t1: float = SUP_HORIZON_S) -> SupportSet:
        """The supervisor's support (hits_to_death events): one event per threat instance in support within t1, the
        boss's iid for the boss, a visible entity's iid for a bell, else its type key; plus every visible entity with
        an active damage box the walk does not explain. Certified (known) only when the tracker is."""
        m = self.fc.model
        dmg = max(f.damage for f in m.families.values())
        hazard = any(f.hazard for f in m.families.values())
        by_type: dict[str, int] = {}
        if ws is not None:
            for e in ws.entities:
                by_type.setdefault(e.type_key.v, e.id)
        srcs = self.active_sources(0.0, t1)
        events = []
        for s in sorted(srcs):
            iid = self.fc.tracker.iid if s == m.boss_type else by_type.get(s)
            events.append(SupportEvent(s, dmg, hazard=hazard, instance=iid))
        if ws is not None:
            for e in ws.entities:
                if e.type_key.v in srcs or e.id == self.fc.tracker.iid:
                    continue
                if any(b.active for b in e.dmg_boxes):
                    events.append(SupportEvent(e.type_key.v or "entity", dmg, instance=e.id))
        return SupportSet(tuple(events), self.known, certified_empty=self.known and not events)

    # ---- J helpers ----------------------------------------------------------------------------------------------

    def _shape_override(self) -> list | None:
        """ORACLE: the polygons to predict the boss with when its current state borrows a later state's shape
        (Forecaster.shape_from: the emerge -> the charge's), at the current transform; [] when that shape is not
        known yet (no hit is predicted then); None when the current shape stands."""
        fc, b = self.fc, self.boss
        if fc.view != ORACLE or b is None or not fc.shape_from:
            return None
        src = fc.shape_from.get(fc.tracker.state or "")
        if src is None:
            return None
        q = fc.tracker.shapes.get((src, bool(b.flip_x)))
        if q is None or b.pos_transform is None:
            return []
        tx, ty = b.pos_transform
        return [p + (tx, ty) for p in q]

    def _hurt_box(self) -> tuple[float, float, float, float] | None:
        """The boss's hittable box now: its enabled colliders (oracle view), or in the vision view the hurtbox table's
        median box for the observable phase and its time (ssbot.tools.hurtbox_table) at the observed position, the
        sprite's render box only where the table has nothing."""
        b = self.boss
        if b is None:
            return None
        tab = self.fc.hurtbox
        st = self.fc.tracker.shape_key(tab)
        if self.fc.view != ORACLE and tab and st in tab and self.fc.tracker.t_entry is not None:
            bins = tab[st]
            k = str(min(int(max(0.0, self.origin_t - self.fc.tracker.t_entry) / 0.1), max(int(x) for x in bins)))
            m = (bins.get(k) or bins[min(bins, key=lambda x: abs(int(x) - int(k)))])["median"]
            x0, y0, x1, y1 = m
            if b.flip_x:
                x0, x1 = -x1, -x0
            px, py = self.fc.tracker.fused_pos(self.origin_t, b)
            return px + x0, py + y0, px + x1, py + y1
        ov = self._shape_override()
        if ov:
            p = np.concatenate(ov)
            return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())
        return _body_box(b)

    def _table_rel(self, tk: np.ndarray) -> np.ndarray | None:
        """VE: the hurtbox table's median box relative to the boss's position (mirrored with the sprite) at each tk,
        from the time bin of (time in the phase + tk), the phase's last bin past its end: [T, 4]; None without a
        table entry for the phase."""
        tab = self.fc.hurtbox
        tr = self.fc.tracker
        st = tr.shape_key(tab)
        if self.fc.view == ORACLE or not tab or st not in tab or tr.t_entry is None or self.boss is None:
            return None
        bins = tab[st]
        keys = np.array(sorted(int(k) for k in bins))
        tau = self.origin_t - tr.t_entry + np.asarray(tk, np.float64)
        want = np.clip((np.maximum(tau, 0.0) / HURT_BIN_S).astype(np.int64), keys[0], keys[-1])
        near = keys[np.abs(keys[None, :] - want[:, None]).argmin(axis=1)]
        rel = np.array([bins[str(int(k))]["median"] for k in near], np.float64)
        if self.boss.flip_x:
            rel = np.stack([-rel[:, 2], rel[:, 1], -rel[:, 0], rel[:, 3]], axis=1)
        return rel

    def _table_entry(self) -> dict | None:
        tab = self.fc.hurtbox
        st = self.fc.tracker.shape_key(tab)
        if self.fc.view == ORACLE or not tab or st not in tab or self.fc.tracker.t_entry is None:
            return None
        bins = tab[st]
        k = str(min(int(max(0.0, self.origin_t - self.fc.tracker.t_entry) / 0.1), max(int(x) for x in bins)))
        return bins.get(k) or bins[min(bins, key=lambda x: abs(int(x) - int(k)))]

    def body_polys(self) -> tuple[np.ndarray, np.ndarray]:
        """body_shape of the boss, or in the vision view the hurtbox table's polygon (else its box) for the phase
        at the observed position, mirrored with the sprite (scoring)."""
        ent = self._table_entry()
        if ent is not None and ent.get("poly") and self.boss is not None:
            q = np.asarray(ent["poly"], np.float64)
            if self.boss.flip_x:
                q = q * (-1.0, 1.0)
            q = q + self.fc.tracker.fused_pos(self.origin_t, self.boss)
            return q, np.array([0, len(q)], np.int64)
        ov = self._shape_override()
        if ov:
            starts = np.zeros(len(ov) + 1, np.int64)
            starts[1:] = np.cumsum([len(q) for q in ov])
            return np.concatenate(ov), starts
        if self.fc.view != ORACLE and self.fc.hurtbox:
            bb = self._hurt_box()
            if bb is not None:
                x0, y0, x1, y1 = bb
                return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64), np.array([0, 4], np.int64)
        return body_shape(self.boss)

    def certain_boss(self, box: np.ndarray, okb: np.ndarray, polys: np.ndarray, starts: np.ndarray,
                     tk: np.ndarray) -> list | None:
        """The pogo gate's certain form of the boss (DESIGN 3.5.6: a pogo stands only if its spike meets the boss in
        every timing lane; a miss lands the hero on it) in the vision view: per horizon bucket k_max (frames from the
        origin), the shape eroded by how far the real box was seen inside the predicted one at that horizon while the
        boss stayed in this observable phase (Forecaster.box_margin, ssbot.tools.boss_path_audit --margins), moved
        along the nominal box, and only until the phase can end at the earliest (its states' shortest logged
        dwells: the shape changes there, a charge's into its end, which the margins do not cover):
        [(k_max, cbox [T, 4], ok [T], polys, starts, base)]. None in the oracle view (its box is the colliders'
        own); [] when the phase has no measured margin (no pogo is certain then)."""
        fc = self.fc
        if fc.view == ORACLE or fc.box_margin is None:
            return None
        key = fc.tracker.shape_key(fc.box_margin) or ""
        tab = fc.box_margin.get(key)
        tau_tab = (fc.box_margin.get("_tau") or {}).get(key)
        if tau_tab and fc.tracker.t_entry is not None:
            # the margins measured from origins in this time bin of the phase (a charge's end and its Dig In differ)
            b = str(int(max(0.0, self.origin_t - fc.tracker.t_entry) / MARGIN_BIN_S))
            tab = tau_tab.get(b, tab)
        if not tab or not len(polys):
            return []
        t_cut = fc.tracker.phase_left_min(self.origin_t) if CERT_PHASE_CUT else math.inf
        okc = np.ascontiguousarray(okb & (np.asarray(tk) <= t_cut))
        if not okc.any():
            return []
        b0 = np.array([polys[:, 0].min(), polys[:, 1].min(), polys[:, 0].max(), polys[:, 1].max()])
        out = []
        for kb in sorted(tab, key=int):
            l, r, b, t = tab[kb]
            cp = _eroded(polys, starts, float(l), float(r), float(b), float(t))
            if cp is None:
                continue
            q, qs = cp
            c0 = np.array([q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()])
            out.append((int(kb), np.ascontiguousarray(box + (c0 - b0)[None, :]), okc, q, qs,
                        np.ascontiguousarray(c0[:2])))
        return out

    def target_paths(self, tk: np.ndarray) -> list:
        """Registry targets (pogo_targets: bells) on their predicted paths, tk seconds from the observation: the
        oracle view's from the logged state, the vision view's from the bells on exact paths (Forecast.det)."""
        ws = self.fc._ws
        if ws is None:
            return []
        if self.fc.view == ORACLE:
            return self.fc.targets.paths(ws, tk)
        return self._det_targets(np.asarray(tk, np.float64)) if VE_TARGETS else []

    def _det_targets(self, tk: np.ndarray) -> list:
        """VE: one TargetPath per bell on an exact path with one branch (a drop bell before its bounce: until the
        bounce), nominal centre (no time slack), determined where simulate says so, collider on until its life;
        a drop bell only while falling."""
        out = []
        for j, d in enumerate(self.det):
            sides = d.branch_sides()
            sd = sides[0] if len(sides) == 1 else 0
            cx, cy, ok = self._bell_path(j, sd, 0.0, tk)
            ok = np.asarray(ok, bool).copy()
            if d.type_key.startswith(DROP_BELL):
                dy = np.diff(cy, append=cy[-1] - 1e-6) if len(cy) else cy
                ok &= dy < 0.0
            r = d.sp.r
            box = np.stack([cx - r, cy - r, cx + r, cy + r], axis=1)
            out.append(TargetPath(d.type_key, -1 - j, np.ascontiguousarray(box), ok, ok & (tk <= CERT_MAX_S), r,
                                  CERT_MARGIN_U + VE_CERT_EXTRA_U + d.skin, False))
        return out

    def boss_box(self, tk: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Nominal boss hurtbox [T, 4] (x0, y0, x1, y1) and hittable [T] along the most likely path (scoring only):
        the current body box moved along the family's logged mean path, hittable while the boss stays drawn."""
        tk = np.asarray(tk, np.float64)
        box = np.zeros((len(tk), 4))
        ok = np.zeros(len(tk), bool)
        tr = self.fc.tracker
        b = self.boss
        if b is None or b.hidden or b.visible_frac <= 0.0 and self.fc.view != ORACLE:
            return box, ok
        bb = self._hurt_box()
        if bb is None or self._shape_override() == []:
            return box, ok
        box[:] = bb
        if SHAPE_T:
            # the shape along the horizon (vision view): the table's bin at each frame's time in the phase, moved
            # with the origin's box (the same reference: the box at tk 0 is the origin's)
            rel = self._table_rel(tk)
            if rel is not None:
                box += rel - self._table_rel(np.zeros(1))[0]
        t_left = tr.drawn_left(self.origin_t)
        ok[:] = tk <= t_left
        if tr.state in self.fc.no_hurtbox:
            # no hurtbox while the boss stays in this state (its longest logged dwell), not over the whole horizon: the
            # charge that follows the antic is hittable, and a pogo planned in the antic must see it (spike_audit on
            # gate chunk 20261002_123347: no pogo plan was ever offered in Charge Emerge / Charge Antic)
            st = PHASE_ROOT.get(tr.state, tr.state)
            info = self.fc.model.states.get(st)
            if info is None or tr.t_entry is None:
                ok[:] = False
            else:
                ok[tk < tr.t_entry + info.dwell[1] - self.origin_t] = False
        # the vision view's tracker keeps the attack in last_family / last_anchor (ctx is the oracle's): without them
        # the box stood still while the boss moved (stage C run 20261002_093052, predict_audit: boss centre 7.3 u off
        # at +0.5 s for side slashes, 9.4 u at a down spike's active frame)
        fam = tr.ctx.family if self.fc.view == ORACLE else tr.last_family
        anchor = tr.ctx.anchor if self.fc.view == ORACLE else (tr.fit_anchor or tr.last_anchor)
        f = self.fc.model.families.get(fam) if fam else None
        if f is not None and f.path is not None and tr.t_start is not None and anchor is not None:
            t_att = self.origin_t - tr.t_start
            path = f.path
            xs = np.interp(t_att + tk, path[:, 0], path[:, 6])
            ys = np.interp(t_att + tk, path[:, 0], path[:, 7])
            x0 = np.interp(t_att, path[:, 0], path[:, 6])
            y0 = np.interp(t_att, path[:, 0], path[:, 7])
            m = anchor.mirror
            box[:, [0, 2]] += (m * (xs - x0))[:, None]
            box[:, [1, 3]] += (ys - y0)[:, None]
        return box, ok


@functools.lru_cache(maxsize=256)
def _eroded_cached(key: bytes, n: int, starts: tuple, l: float, r: float, b: float, t: float):
    from shapely.affinity import translate
    from shapely.geometry import Polygon
    pts = np.frombuffer(key, np.float64).reshape(n, 2)
    outs = []
    for a, z in zip(starts[:-1], starts[1:]):
        p = Polygon(pts[a:z])
        if not p.is_valid:
            p = p.buffer(0)
        # the real shape is this one moved by (dx, dy), dx in [-r, l], dy in [-t, b]: what all of them cover
        q = p
        for dx in (-r, l):
            for dy in (-t, b):
                q = q.intersection(translate(p, dx, dy))
        if q.is_empty:
            continue
        geoms = getattr(q, "geoms", [q])
        best = max((g for g in geoms if g.geom_type == "Polygon"), key=lambda g: g.area, default=None)
        if best is None or best.area <= 1e-6:
            continue
        outs.append(np.asarray(best.exterior.coords, np.float64)[:-1])
    if not outs:
        return None
    st = np.zeros(len(outs) + 1, np.int64)
    st[1:] = np.cumsum([len(o) for o in outs])
    return np.ascontiguousarray(np.concatenate(outs)), st


def _eroded(polys: np.ndarray, starts: np.ndarray, l: float, r: float, b: float, t: float):
    """Polygons (flat vertices, starts) eroded by a translation box: the part every shift (dx in [-r, l], dy in
    [-t, b]) of them still covers (Minkowski erosion, exact for convex parts), or None when nothing is left."""
    p = np.ascontiguousarray(polys, np.float64)
    return _eroded_cached(p.tobytes(), len(p), tuple(int(x) for x in starts), round(l, 4), round(r, 4), round(b, 4),
                          round(t, 4))


def body_shape(e: Entity | None) -> tuple[np.ndarray, np.ndarray]:
    """The boss's enabled collider polygons as flat vertices [V, 2] and starts [P + 1] (scoring: nail hits land on
    them). During an attack the root box is disabled and the attack polygon takes the hits (live run 20261002_064001:
    Leap Out / Descending have only LeapCollider enabled, a 9-vertex shape whose box is 11.7 x 3.8 u, the root box
    2.2 x 1.8 u disabled; Charge only PolyCollider); its bounding box credited side, up and down slashes alike, while
    side slashes in Leap Out hit 6 times of 56. Vision view: the render box as a rectangle."""
    polys = [np.asarray(p, np.float64).reshape(-1, 2) for p in (e.body_polys if e is not None else ()) if len(p) >= 3]
    if not polys:
        return np.zeros((0, 2)), np.zeros(1, np.int64)
    starts = np.zeros(len(polys) + 1, np.int64)
    starts[1:] = np.cumsum([len(q) for q in polys])
    return np.concatenate(polys), starts


def _body_box(e: Entity) -> tuple[float, float, float, float] | None:
    if e.body_polys:
        p = np.concatenate([np.asarray(q, np.float64).reshape(-1, 2) for q in e.body_polys])
        return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())
    if e.render_box is not None:
        return e.render_box
    return None


class BossTracker:
    """The boss's state as the view can know it. ORACLE: Control state, entry time, attack start, direction, anchor
    (transform at the first drawn frame of the attack, or the fixed one). VISION_EQUIVALENT: observable phase and its
    entry, memory of the last drawn family / anchor, hide time, burst anchor from the box centre."""

    def __init__(self, model: BossModel, view: str):
        self.model = model
        self.view = view
        self.reset()

    def reset(self) -> None:
        self.state: str | None = None          # ORACLE: Control state; VE: observable phase
        self.t_entry: float | None = None      # game time the state / phase began
        self.t_start: float | None = None      # game time the current attack began (ORACLE; VE estimate)
        self.ctx = Ctx(phase=self.model.initial_phase, raged=False)
        self.iid: int | None = None
        self.seen = False                      # the boss was drawn at least once
        self.t_wake: float | None = None
        self.dead = False
        self.last_family: str | None = None    # VE: family of the last drawn phase
        self.last_anchor: Anchor | None = None
        self.t_hide: float | None = None
        self.tell_dir: str | None = None       # VE: the anchor side of the last emergence dust
        self.fit = getattr(self, "fit", None)  # VE: AttackFit for committed attacks (kept across resets)
        if self.fit is not None:
            self.fit.reset()
        self.fit_ok = False
        self.fit_anchor: Anchor | None = None
        self.fit_anomalies = 0
        self._t_start0: float | None = None
        self._phase_t0: tuple | None = None    # VE: the drawn phase (and its entry) t_start was last anchored at
        self._obs: list[tuple[float, float, float]] = []   # VE: detections (t, x, y) of the boss in this phase
        self.coasting = False                  # VE: no phase this frame (a ghost)
        self._anchor_sum: list[float] = []
        self.t = 0.0
        self.hidden_x: dict[str, float] = {}   # ORACLE: the hidden boss's x per state of this attack (anchor check)
        self.ends: list[tuple] = []   # last attacks' ends: (family, anchor, t_end lo, t_end hi, phase, by a death):
        #                               their tails (bells; the body too when the boss died mid-attack) outlive them
        self._drawn_anchor: tuple | None = None
        self.n_attacks = 0
        self.bells: dict[int, tuple[str, float, tuple[float, float]]] = {}   # ORACLE: armed drop bells: (type,
        #                                                                    arm time, arm position)
        self.bells_unknown = False             # an armed drop bell whose arming was not seen
        self._cued: set[int] = set()           # VE: drop bells with their cue in the last frame
        self._cue_obs: dict[int, list[tuple[float, float, float]]] = {}   # VE: the cue's detections (x, y, sigma)
        self.bell_sx: dict[int, float] = {}    # VE: 1 sigma of an armed bell's x (the mean of its cue detections)
        self.anchor_log: list[tuple[str, float, float]] = []   # ORACLE: (family, hidden x, drawn transform x)
        self.bell_y: float | None = getattr(self, "bell_y", None)   # VE: drop bells' hang height (registry `start`)
        # ORACLE: body shapes seen per (state, flipX), polygons relative to the transform (kept across episodes: the
        # same boss), for the states the playbook predicts others with (Forecaster.shape_from)
        self.shapes: dict = getattr(self, "shapes", {})
        self.shape_states: frozenset = getattr(self, "shape_states", frozenset())

    # ---- ORACLE -------------------------------------------------------------------------------------------------

    def _enter(self, state: str, t: float) -> None:
        m = self.model
        prev = self.state
        self.state, self.t_entry = state, t
        if state in m.death_states:
            if self.ctx.family is not None and not self.dead:     # the bells of a killed attack roll on: its tail
                self._ended(self.ctx.family, self.ctx.anchor, t, t, death=True)
            self.dead = True
            return
        if state == "Submerged Init":
            self.ctx.direction = "-"
            self.t_wake = self.t_wake if self.t_wake is not None else t
        if state in m.dir_states:
            self.ctx.direction = state
        if state in m.attack_starts:
            fam = m.attack_starts[state]
            if self.ctx.direction is None and self.n_attacks == 0 and self.t_wake is not None:
                self.ctx.direction = "-"          # the first attack after the wake (its Set state came before us)
            self.ctx.family = fam
            self.ctx.anchor = m.anchor(fam, self.ctx.direction)
            self.t_start = t
            self.hidden_x = {}
            self.n_attacks += 1
        elif self.ctx.family is None and state not in m.decision_states:
            # the attack's start state was missed (the policy began after it: live run 20261002_152649, 11 of 24
            # episodes replayed began their first act in Emerge Antic C, 2.9 s after the wake, and first saw the boss
            # in Charge Emerge): the one family with this state, its start placed by the logged entry offset (its
            # middle; Charge Emerge 1.000-1.017 s after Emerge Antic C). Without it the boss box (Forecast.boss_box)
            # stood still through the whole first charge (boss_path_audit: front edge p10 9.7 u behind at +24 frames)
            fams = [f for f in m.families.values() if state in f.states and state in f.entry]
            if len(fams) == 1:
                f = fams[0]
                self.ctx.family = f.name
                self.ctx.anchor = m.anchor(f.name, self.ctx.direction)
                self.t_start = t - 0.5 * (f.entry[state][0] + f.entry[state][1])
                self.hidden_x = {}
                self.n_attacks += 1
        elif state in m.decision_states and prev is not None and prev not in m.decision_states:
            if self.ctx.family is not None:
                self._ended(self.ctx.family, self.ctx.anchor, t, t)
            self.ctx.family, self.ctx.anchor, self.t_start = None, None, None
            if state == "Submerged":
                self.ctx.direction = None
        if state == "Rage Pos":
            self.ctx.raged = True
        if state in m.phase_marks:
            self.ctx.phase = m.phase_marks[state]

    def _ended(self, family: str, anchor: Anchor | None, t_lo: float, t_hi: float, death: bool = False) -> None:
        self.ends = (self.ends + [(family, anchor, t_lo, t_hi, self.ctx.phase, death)])[-2:]

    def update(self, ws: WorldState) -> Entity | None:
        m = self.model
        t = ws.stamp.t_game_s
        self.t = t
        boss = next((e for e in ws.entities if e.type_key.v == m.boss_type), None)
        if boss is not None:
            self.iid = boss.id
            if boss.hp_est is not None:
                self.ctx.hp = boss.hp_est.v
        for ev in ws.events:
            if (ev.kind == Ev.ENEMY_KILLED and ev.data is not None and ev.data.type_key == m.boss_type
                    and not self.dead):
                if self.view == ORACLE and self.ctx.family is not None:
                    self._ended(self.ctx.family, self.ctx.anchor, ev.t_game_s, ev.t_game_s, death=True)
                elif self.view != ORACLE and self.state not in (None, HIDDEN) and self.last_family is not None:
                    self._ended(self.last_family, self.last_anchor, ev.t_game_s - BIN, ev.t_game_s + BIN,
                                death=True)
                self.dead = True
        if self.view == ORACLE:
            self._update_oracle(ws, boss, t)
        else:
            self._update_ve(ws, boss, t)
        return boss

    def _update_oracle(self, ws: WorldState, boss: Entity | None, t: float) -> None:
        m = self.model
        for ev in ws.events:
            d = ev.data
            if ev.kind == Ev.FSM_TRANSITION and d is not None and d.fsm == m.control_fsm and d.to_state \
                    and str(d.type_key or "").startswith(m.boss_type):
                if d.from_state in ("Dormant", "Init") and self.t_wake is None:
                    self.t_wake = ev.t_game_s
                self._enter(d.to_state, ev.t_game_s)
        self._bells(ws, t)
        if boss is None:
            return
        if boss.phase is not None and boss.phase.top:
            st, tau = boss.phase.top, boss.phase.t_in_phase
            if st != self.state:
                self._enter(st, t - tau)
            else:
                self.t_entry = t - tau
        if boss.hidden:
            fam = self.ctx.family
            if fam is not None:
                self.hidden_x[self.state or ""] = boss.pos.v[0]
                f = m.families[fam]
                # the burst's x is set underground at Burst Pos and the boss erupts there: the hidden x is the
                # anchor (live runs 2026-10-02: 81 of 81 bursts exactly, and 336 of 336 charges / leaps at their
                # fixed anchors), known 1.2 s before the eruption
                if self.ctx.anchor is None and not f.directed and f.anchor_y is not None and self.state != f.start:
                    self.ctx.anchor = Anchor(float(boss.pos.v[0]), f.anchor_y, f.mirror)
            return
        self.seen = True
        if self.state in self.shape_states and boss.body_polys and boss.pos_transform is not None:
            tx, ty = boss.pos_transform
            self.shapes[(self.state, bool(boss.flip_x))] = [np.asarray(q, np.float64).reshape(-1, 2) - (tx, ty)
                                                             for q in boss.body_polys if len(q) >= 3]
        fam = self.ctx.family
        # A variable anchor (the burst) is the transform at the attack's first drawn frame (behaviour_tables' anchor
        # definition; the burst's transform does not move while drawn). Fixed anchors stay: a tracker that starts in
        # the middle of a charge would otherwise anchor on a moving transform.
        if fam is not None and boss.pos_transform is not None and self._drawn_anchor != (fam, self.t_start):
            self._drawn_anchor = (fam, self.t_start)
            ax, ay = boss.pos_transform
            hx = next(iter(self.hidden_x.values()), math.nan)
            self.anchor_log.append((fam, hx, float(ax)))
            f = m.families[fam]
            if f.directed and self.ctx.anchor is None:
                # direction missed (the tracker started after the Set state): the facing tells it (Set L flipX
                # False, Set R True in every logged instance)
                self.ctx.anchor = m.anchor(fam, "Set R" if boss.flip_x else "Set L")
            elif m.anchor(fam, self.ctx.direction) is None and not f.directed:
                self.ctx.anchor = Anchor(float(ax), float(ay), f.mirror)

    def _bells(self, ws: WorldState, t: float) -> None:
        """ORACLE: drop bells hang in the export all fight (FSM Dormant) and arm (leave Dormant: Antic, the shake)
        about 1.2 s before they can hurt (self templates start 1.217 s after arming). Arm time and position (the
        transform: they hang still while shaking) make their self template placeable."""
        seen = set()
        unknown = False
        for e in ws.entities:
            tk = e.type_key.v
            if not tk.startswith(DROP_BELL) or not e.fsm:
                continue
            st, tau = e.fsm[0][1], e.fsm[0][2]
            if st in REST_STATES:
                self.bells.pop(e.id, None)     # disarmed: the same bell object re-arms for a later drop
                continue
            seen.add(e.id)
            if e.id not in self.bells:
                if st == "Antic" and e.pos_transform is not None:
                    self.bells[e.id] = (tk, t - tau, (float(e.pos_transform[0]), float(e.pos_transform[1])))
                else:
                    unknown = True
        for iid in [i for i in self.bells if i not in seen]:
            if t - self.bells[iid][1] > BELL_TTL_S:
                del self.bells[iid]
        self.bells_unknown = unknown

    # ---- VISION_EQUIVALENT ----------------------------------------------------------------------------------------

    def _bells_ve(self, ws: WorldState, t: float) -> None:
        """VE with the bell cue (ObservabilityFilter tells, phase "bell_dust"): arming time from the cue, the bell's x
        from the mean of the cue's detections (each as noisy as any other detection; a missed one coasts and does
        not count), its y the hang height every drop bell has (registry `start`: 13.74, the transform in Antic in
        13,479 of 13,479 frames of live run 20261002_171806 i0_000), else the cue's mean y."""
        cued = set()
        for e in ws.entities:
            if not e.type_key.v.startswith(DROP_BELL) or e.phase is None or e.phase.top != "bell_dust":
                continue
            cued.add(e.id)
            if e.id not in self._cued:             # a new cue: this bell (re-)armed
                t_arm = t - e.phase.t_in_phase - TELL_DELAY["bell_dust"]
                self.bells[e.id] = (e.type_key.v, t_arm, (float(e.pos.v[0]), float(e.pos.v[1])))
                self._cue_obs[e.id] = []
            obs = self._cue_obs.setdefault(e.id, [])
            if e.pos.age_ms <= 0.0:                # detected in this frame (a coasted cue's age grows)
                s = e.pos.sigma if math.isfinite(e.pos.sigma) else 1.0
                obs.append((float(e.pos.v[0]), float(e.pos.v[1]), float(s)))
            if obs:
                a = np.asarray(obs, np.float64)
                y = self.bell_y if self.bell_y is not None else float(a[:, 1].mean())
                tk, t_arm, _ = self.bells[e.id]
                self.bells[e.id] = (tk, t_arm, (float(a[:, 0].mean()), y))
                self.bell_sx[e.id] = float(np.sqrt(np.mean(a[:, 2] ** 2)) / math.sqrt(len(a)))
        self._cued = cued
        for iid in [i for i in self._cue_obs if i not in cued]:
            del self._cue_obs[iid]
        for iid in [i for i in self.bells if i not in cued]:
            if t - self.bells[iid][1] > BELL_TTL_S:
                del self.bells[iid]
                self.bell_sx.pop(iid, None)

    def _update_ve(self, ws: WorldState, boss: Entity | None, t: float) -> None:
        m = self.model
        self._bells_ve(ws, t)
        self.coasting = boss is None or boss.phase is None or boss.phase.top == UNKNOWN
        if boss is None or boss.phase is None:
            return
        ph, tau = boss.phase.top, boss.phase.t_in_phase
        if ph == UNKNOWN:
            return
        if ph != self.state:
            prev = self.state
            self.state, self.t_entry = ph, t - tau
            if ph == HIDDEN:
                self._obs = []
            if ph == HIDDEN:
                self.t_hide = t - tau
                if prev == "roar":
                    self.last_family = "BB_RAGE"
                if prev == "recover" and self.last_family in RECOVER_ROOT:
                    self._ended(self.last_family, self.last_anchor, self.t_hide - VE_ENTRY_SLACK * BIN,
                                self.t_hide + VE_ENTRY_SLACK * BIN)
            else:
                fam = PHASE_FAMILY.get(ph)
                if ph == "recover":
                    fam = self.last_family if self.last_family in RECOVER_ROOT else None
                if fam is not None and fam != self.last_family or ph in ("emerge", "leap", "burst", "roar",
                                                                         *TELL_PHASES) \
                        and prev in (HIDDEN, None, "recover", "roar_end"):
                    self._anchor_sum = []
                    self.last_anchor = None
                    self.t_start = None
                    self._t_start0, self.fit_ok, self.fit_anchor = None, False, None
                    self._obs = []         # a new attack: its own path (the fused position spans its phases)
                self.last_family = fam if fam is not None else (None if ph == "dust" else self.last_family)
                if ph == "roar":
                    self.ctx.raged = True
                if ph == "roar_end":
                    self.ctx.phase = "P2"      # the drop-bell pattern follows; P2 from its end
        if ph == HIDDEN:
            return
        self.seen = True
        if ph not in TELL_PHASES and boss.visible_frac > 0.0 and boss.pos.conf > 0.0 and not boss.hidden:
            self._obs = (self._obs + [(t, float(boss.pos.v[0]), float(boss.pos.v[1]))])[-FUSE_N_Y:]
        if ph in EMERGE_TELLS and boss.pos.conf > 0:
            xl, xr = m.anchor("BB_CHARGE", "Set L").x, m.anchor("BB_CHARGE", "Set R").x
            self.tell_dir = "Set L" if boss.pos.v[0] < 0.5 * (xl + xr) else "Set R"
            if ph == "dust":
                self.last_anchor = m.anchor("BB_CHARGE", self.tell_dir)     # charge and leap share the anchors
                return
        fam = self.last_family
        if fam is None:
            return
        f = m.families[fam]
        root = RECOVER_ROOT.get(fam) if ph == "recover" else PHASE_ROOT.get(ph)
        if root in f.entry and (self.t_start is None or (self._phase_t0 != (ph, self.t_entry)
                                                         and ph not in TELL_PHASES)):
            # the attack began this long before the phase's first state (the family's logged entry offsets, their
            # middle): the boss box then moves along the family's mean path (Forecast.boss_box). Re-anchored at
            # every drawn phase's entry (seen +-1 frame): a start guessed from the dust cue (+-0.1 s) and fitted over
            # frames of a boss standing at its anchor (no timing in them) put the charge's box up to 2 u off at
            # +0.1 s (task V, boss_path_audit --view degraded_dust on live run 20261002_171806)
            lo, hi = f.entry[root]
            self.t_start = t - tau - TELL_DELAY.get(ph, 0.0) - 0.5 * (lo + hi)
            self._t_start0 = self.t_start
            self._phase_t0 = (ph, self.t_entry)
        if fam == "BB_BURST":
            # set per burst and kept to its end (an earlier version fell through to the family's named anchor,
            # which a burst has none of, from the second drawn frame on: the whole burst range for the rest of the
            # burst, FORCED_RISK in every stage C burst, run 20261002_060151). The cue's dust stands at the anchor:
            # the mean of all its detections (each as noisy as a boss detection); without a cue the first drawn frame
            if boss.pos.conf > 0 and boss.pos.age_ms <= 0.0:       # detected in this frame (not coasted)
                if ph in TELL_PHASES:
                    self._anchor_sum.append(boss.pos.v[0])
                elif not self._anchor_sum:
                    # the box follows the sprite frame (live i2_002 f605393-605452: box centre x 89.93 -> 91.57 while
                    # the transform stays at 90.47), so only the first drawn frame has the behaviour table's offset
                    self._anchor_sum.append(boss.pos.v[0] - f.box_offset.get(bool(boss.flip_x), (0.0, 0.0))[0])
            if self._anchor_sum:
                y = f.anchor_y if f.anchor_y is not None else boss.pos.v[1] + 2.68
                self.last_anchor = Anchor(float(np.mean(self._anchor_sum)), y, 1)
        elif f.directed:
            told = ph in TELL_PHASES and self.tell_dir is not None
            base = m.anchor(fam, self.tell_dir if told else ("Set R" if boss.flip_x else "Set L"))
            self.last_anchor = base
            if self.fit is not None and ph not in TELL_PHASES and boss.pos.conf > 0 and self.t_start is not None:
                # multi-frame fusion (combat.attack_fit): the committed attack's template fitted to every frame seen
                # since it came up; a rejected fit keeps the phase-level estimate (broad support) and flags it
                self.fit.start(fam, base, self._t_start0 if self._t_start0 is not None else self.t_start)
                self.fit.observe(t, float(boss.pos.v[0]), float(boss.pos.v[1]))
                r = self.fit.result()
                self.fit_ok = bool(r is not None and r.ok)
                if r is not None and not r.ok:
                    self.fit_anomalies += 1
                if self.fit_ok:
                    # scoring only (Forecast.boss_box): moving the support's anchor by the fit lost 3.3 % of the
                    # held-out contacts (support_recall ve / ve_dust 23,117 of 23,896, emerge / charge body)
                    self.t_start = r.t_start
                    self.fit_anchor = Anchor(base.x + r.dx, base.y, base.mirror)
        else:
            self.last_anchor = m.anchor(fam, None)

    # ---- roots ----------------------------------------------------------------------------------------------------

    def roots(self, origin_t: float) -> tuple[list[Root], bool]:
        """Where the walk starts: [(state, entry interval relative to the origin, context, p)] and whether the view
        certifies it (False: nothing known about the boss)."""
        if self.dead:
            return [], True
        if self.view == ORACLE:
            return self._roots_oracle(origin_t)
        return self._roots_ve(origin_t)

    def _wake_root(self, origin_t: float) -> list[Root]:
        if self.t_wake is None:
            return []
        e = self.t_wake - origin_t
        # the wake comes from the episode's frame count (+-2 bins: game time and frames part in a hit-stop)
        return [Root("Submerged Init", e - 2 * BIN, e + 2 * BIN,
                     Ctx(direction="-", phase="P1", raged=False, hp=self.ctx.hp))]

    def _roots_oracle(self, origin_t: float) -> tuple[list[Root], bool]:
        if self.state is None or self.t_entry is None:
            r = self._wake_root(origin_t)
            return r, bool(r)
        e = self.t_entry - origin_t
        ctx = replace(self.ctx)
        fams = [f.name for f in self.model.families.values() if self.state in f.states]
        if ctx.family is None and fams:
            # the attack's start was missed (the tracker began mid-attack): every family with this state, its fixed
            # anchor when it has one, else world_all
            return [Root(self.state, e, e, replace(ctx, family=fam, anchor=self.model.anchor(fam, ctx.direction)),
                         1.0 / len(fams), current=True) for fam in fams], True
        return [Root(self.state, e, e, ctx, current=True)], True

    def _roots_ve(self, origin_t: float) -> tuple[list[Root], bool]:
        m = self.model
        base = Ctx(phase=self.ctx.phase, raged=self.ctx.raged, hp=self.ctx.hp)
        if self.state is None or self.t_entry is None:
            r = self._wake_root(origin_t)
            return r, bool(r)
        e = self.t_entry - origin_t
        lo, hi = e - VE_ENTRY_SLACK * BIN, e + VE_ENTRY_SLACK * BIN
        if self.state == HIDDEN:
            if not self.seen:
                r = self._wake_root(origin_t)
                return r, bool(r)
            fam = self.last_family
            states = [HIDE_ROOT[fam]] if fam in HIDE_ROOT else sorted(set(HIDE_ROOT.values()))
            out = []
            for st in states:
                ctx = replace(base)
                if st != "Submerged":
                    ctx.family = "BB_BURST" if st == "Burst Recovery" else "BB_RAGE"
                    ctx.anchor = self.last_anchor if self.last_family == ctx.family else m.anchor(ctx.family, None)
                out.append(Root(st, lo, hi, ctx, 1.0 / len(states)))
            return out, True
        fam = self.last_family
        if self.state == "recover":
            fams = [fam] if fam in RECOVER_ROOT else list(RECOVER_ROOT)
            out = []
            for f in fams:
                ctx = replace(base, family=f, anchor=self.last_anchor if f == fam else None)
                out.append(Root(RECOVER_ROOT[f], lo, hi, ctx, 1.0 / len(fams)))
            return out, True
        direction = None
        if self.state in TELL_PHASES:
            d, sl = TELL_DELAY[self.state], TELL_SLACK_S[self.state]
            lo, hi = e - d - sl, e - d + sl
            if self.state in EMERGE_TELLS:
                direction = self.tell_dir
            if self.state == "dust":
                return [Root(st, lo, hi, replace(base, family=f, direction=direction, anchor=m.anchor(f, direction)),
                             1.0 / len(DUST_ROOTS)) for f, st in DUST_ROOTS], True
        st = PHASE_ROOT.get(self.state)
        if st is None:
            return [], False
        fam_r = PHASE_FAMILY[self.state]
        ctx = replace(base, family=fam_r, anchor=self.last_anchor, direction=direction)
        return [Root(st, lo, hi, ctx)], True

    def shape_key(self, table: dict | None = None) -> str | None:
        """VE: the key of the boss's shape tables (hurtbox per phase, pogo-gate margins): the observable phase,
        "recover/<family>" for the end of a charge or of a leap (one phase, two shapes: Charge End's box vs Leap
        Land's) when the table has it."""
        st = self.state
        if st == "recover" and self.last_family in RECOVER_ROOT:
            k = f"recover/{self.last_family}"
            if table is None or k in table:
                return k
        return st

    def _path_xy(self, t: float) -> tuple[float, float] | None:
        """The current attack's mean path (anchor frame: x mirrored) at game time t, or None."""
        fam = self.last_family
        f = self.model.families.get(fam) if fam else None
        anchor = self.fit_anchor or self.last_anchor
        if f is None or f.path is None or self.t_start is None or anchor is None:
            return None
        ta = t - self.t_start
        return (anchor.mirror * float(np.interp(ta, f.path[:, 0], f.path[:, 6])),
                float(np.interp(ta, f.path[:, 0], f.path[:, 7])))

    def fused_pos(self, origin_t: float, boss: Entity) -> tuple[float, float]:
        """VE: the boss's position at the origin from its last FUSE_N detections in this attack (its phases share
        the family's mean path and the reference point, the root box's centre), each moved to the origin along
        that path (Forecast.boss_box moves the box the same way): the noise of one detection averages down (task V:
        the pogo gate's box margins are sized from the residual of this position; reset per phase, the first
        frames of a charge left 0.2 u of top error). A boss without a path (a burst, a roar) takes the plain mean."""
        obs = self._obs[-FUSE_N_Y:]
        if len(obs) < 2:
            return boss.pos.v
        p0 = self._path_xy(origin_t)
        xs, ys = [], []
        for t, x, y in obs:
            pi = self._path_xy(t) if p0 is not None else None
            if pi is None:
                xs.append(x)
                ys.append(y)
            else:
                xs.append(x + p0[0] - pi[0])
                ys.append(y + p0[1] - pi[1])
        return float(np.mean(xs[-FUSE_N:])), float(np.mean(ys))

    def phase_left_min(self, origin_t: float) -> float:
        """VE: game s from the origin until the observable phase can end at the earliest: the shortest logged dwells
        of its Control states from its first one (PHASE_ROOT / RECOVER_ROOT) along the likeliest successor while that
        is still in the same phase. 0 when unknown."""
        m = self.model
        ph = self.state
        if self.t_entry is None or ph is None:
            return 0.0
        st = RECOVER_ROOT.get(self.last_family or "") if ph == "recover" else PHASE_ROOT.get(ph)
        if st is None or st not in m.states:
            return 0.0
        t = self.t_entry - origin_t
        for _ in range(8):
            info = m.states.get(st)
            if info is None:
                break
            t += info.dwell[0]
            if not info.succ:
                break
            nxt = max(info.succ, key=lambda x: x[1])[0]
            if VE_PHASE_OF.get(nxt) != ph:
                break
            st = nxt
        return max(0.0, t)

    def drawn_left(self, origin_t: float) -> float:
        """Game s the boss stays drawn from the origin along the shortest logged dwells (scoring only)."""
        m = self.model
        if self.state is None or self.t_entry is None:
            return 0.0
        st = self.state if self.view == ORACLE else (
            RECOVER_ROOT.get(self.last_family or "", "Charge End") if self.state == "recover"
            else PHASE_ROOT.get(self.state))
        if st is None or not m.drawn(st):
            return 0.0
        t = self.t_entry - origin_t
        for _ in range(12):
            info = m.states.get(st)
            if info is None or not m.drawn(st):
                break
            t += info.dwell[0]
            if not info.succ:
                break
            st = max(info.succ, key=lambda x: x[1])[0]
        return max(0.0, t)


class Forecaster:
    """Tracker + walk + one SupportQuery over the planner templates (packed once; about 2 s and 0.2-0.3 GB for the
    Bell Beast per-state templates)."""

    def __init__(self, model: BossModel, view: str = ORACLE, margin: float | tuple[float, float] = 0.0,
                 templates: dict[str, hb.SpaceTimeTemplate] | None = None, npz: str | None = None,
                 comfort: float | tuple[float, float] | None = None,
                 comfort_templates: dict[str, hb.SpaceTimeTemplate] | None = None):
        if view not in (ORACLE, VISION_EQUIVALENT):
            raise ValueError(view)
        self.model = model
        self.view = view
        self.margin = margin_xy(margin)
        if templates is None:
            templates = load_planner_templates(model, self.margin, npz)
        self.templates = templates
        self.meta = {k: (t.t0, t.t1) for k, t in templates.items()}
        # half-extents of the box a point test covers (the templates' dilation)
        self.half = (hb.HERO_HALF_U[0] + self.margin[0], hb.HERO_HALF_U[1] + self.margin[1])
        # earliest damage after a drop bell arms (its self template's first occupied bin, padding included)
        leads = [t.active()[0] for k, t in templates.items() if k.startswith(f"{hb.SUPPORT}ent/{DROP_BELL}")
                 and t.active() is not None]
        self.bell_lead = (min(leads) - BIN) if leads else -math.inf
        self.query = hb.SupportQuery(templates, hero_half=hb.HERO_HALF_U)
        # comfort: the same templates grown by an extra margin, a preference above the score (clearance against the
        # one-frame drift of a plan that is safe by millimetres)
        self.comfort = None if comfort is None else margin_xy(comfort)
        self.query_c = None
        if self.comfort is not None:
            if comfort_templates is None:
                mx, my = self.margin
                comfort_templates = load_planner_templates(model, (mx + self.comfort[0], my + self.comfort[1]), npz)
            self.query_c = hb.SupportQuery(comfort_templates, hero_half=hb.HERO_HALF_U)
        self.tracker = BossTracker(model, view)
        # registry hit targets (bells): their predicted paths for the planner's hit effects (pogo off a bell)
        self.targets = TargetTracker()
        # VE: drop bells' falls from their tracks (bell_track: column, drop time, bounce side), the exact paths the
        # oracle view reads from the FSM and the logged velocity
        sp = self.targets.spec_of(DROP_BELL)
        self.drop_tracks = DropBellTracks(sp) if sp is not None and view != ORACLE else None
        asp = self.targets.spec_of(ATK_BELL)
        self.atk_tracks = AtkBellTracks(asp) if asp is not None and view != ORACLE else None
        self.det_atk = DET_ATK
        self._atk_cover: list[tuple[float, float]] = []    # VE: (pair middle x, launch time from the origin)
        self._atk_lag = self._launch_lags()
        if self.drop_tracks is not None and self.drop_tracks.ok:
            self.tracker.bell_y = self.drop_tracks.y0
        self.det_ve = DET_VE
        self._ws: WorldState | None = None
        self.boss: Entity | None = None
        self.no_hurtbox: frozenset[str] = frozenset()     # states / phases with the body box disabled (playbook)
        self._shape_from: dict[str, str] = {}
        self.bell_tells = False        # VE: the drop bells' cue is in the view (ObservabilityFilter tells)
        self.truncated = 0
        self.hurtbox: dict | None = None   # VE: the boss's hittable box per phase (load_hurtbox; scoring only)
        self.box_margin: dict | None = None   # VE: the pogo gate's margins per phase (load_box_margin)
        self.t = 0.0

    @property
    def shape_from(self) -> dict[str, str]:
        """State -> the state whose body shape the boss box is predicted with (playbook shape_from, oracle view)."""
        return self._shape_from

    @shape_from.setter
    def shape_from(self, m: dict[str, str]) -> None:
        self._shape_from = dict(m)
        self.tracker.shape_states = frozenset(m.values())

    def reset(self) -> None:
        self.tracker.reset()
        self.targets.reset()
        if self.drop_tracks is not None:
            self.drop_tracks.reset()
        if self.atk_tracks is not None:
            self.atk_tracks.reset()
        self._ws = None
        self.boss = None

    def notify_wake(self, t_game: float) -> None:
        """The fight started at this game time (the bot walked into the trigger; vision sees the arena gates close)."""
        if self.tracker.t_wake is None:
            self.tracker.t_wake = t_game

    def update(self, ws: WorldState) -> None:
        self.t = ws.stamp.t_game_s
        self.boss = self.tracker.update(ws)
        self.targets.update(ws, self.t)
        if self.drop_tracks is not None:
            self.drop_tracks.update(ws, self.t)
        if self.atk_tracks is not None:
            tr = self.tracker
            ax = tr.last_anchor.x if tr.last_family == "BB_BURST" and tr.last_anchor is not None else None
            self.atk_tracks.update(ws, self.t, ax)
        self._ws = ws

    # ---- the walk -----------------------------------------------------------------------------------------------

    def forecast(self, horizon_s: float = MIN_HORIZON_S, origin_t: float | None = None) -> Forecast:
        H = max(MIN_HORIZON_S, horizon_s)
        origin = self.t if origin_t is None else origin_t
        self.truncated = 0
        roots, known = self.tracker.roots(origin)
        nodes: list[Node] = []
        placements: list[Placement] = []
        det: list = []
        self._atk_cover = self._atk_bells(origin, det) if self.atk_tracks is not None and self.det_atk else []
        for r in roots:
            self._walk(r.state, r.e_lo, r.e_hi, replace(r.ctx), r.p, -1, H, nodes, placements, r.current, 0)
        tr = self.tracker
        if self.drop_tracks is not None and self.det_ve:
            # VE: a drop bell seen falling without its cue (the cue missed) is support on its path too
            for iid in self.drop_tracks.obs:
                if iid not in tr.bells:
                    self._det_bell(iid, det)
        if tr.bells:
            nid = len(nodes)
            nodes.append(Node(nid, "bells", 0.0, 0.0, None, 1.0, -1, None))
            # oracle: the arming frame; vision: from the cue, +-its slack in 1/60 s steps
            k = 0 if self.view == ORACLE else int(round(TELL_SLACK_S["bell_dust"] / BIN))
            for iid, (tk, t_arm, pos) in tr.bells.items():
                key = f"{hb.SUPPORT}ent/{tk}/self"
                if key not in self.meta:
                    continue
                if self._det_bell(iid, det):
                    continue                  # falling or bounced: its exact path (two branches) replaces the template
                t0, t1 = self.meta[key]
                # VE: a cue seen in few frames: its x +- 3 sigma as well, beyond what the view's margin covers
                sx = tr.bell_sx.get(iid, 0.0)
                dxs = (0.0,) if sx <= CUE_SIGMA_COVERED else (-SKIN_Z * sx, 0.0, SKIN_Z * sx)
                for j in range(-k, k + 1):
                    e = t_arm + j * BIN - origin
                    if e + t1 < -BIN or e + t0 > H + BIN:
                        continue
                    for dx in dxs:
                        placements.append(Placement(key, -e, (pos[0] + dx, pos[1]), 1, nid, e + t0, e + t1,
                                                    frozenset({tk})))
        for fam, anchor, lo, hi, phase, death in self.tracker.ends:
            nid = len(nodes)
            nodes.append(Node(nid, TAIL, lo - origin, hi - origin, fam, 1.0, -1, anchor))
            self._place(fam, TAIL, lo - origin, hi - origin, Ctx(family=fam, anchor=anchor, phase=phase), nid, H,
                        placements, death_tail=death)
        if not roots and self.tracker.dead:
            known = True
        out = Forecast(self, origin, H, nodes, placements, known, roots, self.boss)
        out.det = det
        out.truncated = self.truncated
        return out

    def _det_bell(self, iid: int, det: list) -> bool:
        """ORACLE: an armed drop bell already falling (Drop, Air) or bounced (Bounce Air, Submerge) has an exact path
        (pogo_targets.simulate, centre error 0.000 u over 0.8 s in game time on 2 recordings): it is support as two
        branches, one per bounce side (p 0.5 each; the bounce speed is fixed, 4 u/s), or one once it bounced, instead
        of the logged union of its self template.
        VISION_EQUIVALENT (det_ve): the same path from the bell's track instead (bell_track.DropBellTracks: column x,
        drop time, bounce side once seen), started at the drop and sampled at the time since it, its contact skin grown
        by SKIN_Z sigma of the column's x; while the bell is not seen falling, or its track leaves the model, its self
        template stays."""
        if self.view != ORACLE:
            if not (DET_REPLACE and self.det_ve) or self.drop_tracks is None or self._ws is None:
                return False
            est = self.drop_tracks.estimate(iid)
            if est is None:
                return False
            dt_ = self.drop_tracks
            tk_ = dt_.type_of.get(iid, DROP_BELL)
            det.append(DetBell(dt_.spec, est.x, dt_.y0, dt_.vx0, dt_.vy0, 0, None, tk_, t0=self.t - est.t_drop,
                               sides=(est.side,) if est.side else (1, -1), skin=SKIN_Z * est.sx))
            return True
        if not DET_REPLACE or self._ws is None:
            return False
        e = next((x for x in self._ws.entities if x.id == iid), None)
        if e is None or not e.fsm or e.vel.conf <= 0:
            return False
        sp = self.targets.spec_of(e.type_key.v)
        st = e.fsm[0][1]
        if sp is None or st not in DET_STATES:
            return False
        rest = None
        if st == "Submerge":
            rest = max(0.0, 0.75 - e.fsm[0][2])
        det.append(DetBell(sp, float(e.pos.v[0]), float(e.pos.v[1]), float(e.vel.v[0]), float(e.vel.v[1]),
                           int(sp.next_bounce.get(st, len(sp.bounces))), rest, e.type_key.v))
        return True

    def _launch_lags(self) -> dict[str, tuple[float, float]]:
        """State (and _tail) -> (min, max) game s from the attack bells' launch to its entry (the attack's end for
        _tail): the burst's logged entry offsets and dwells."""
        f = self.model.families.get("BB_BURST")
        if f is None or ATK_LAUNCH_STATE not in f.entry:
            return {}
        lo0, hi0 = f.entry[ATK_LAUNCH_STATE]
        out = {st: (lo - hi0, hi - lo0) for st, (lo, hi) in f.entry.items()}
        last = f.states[-1]
        if last in f.entry and last in self.model.states:
            d = self.model.states[last].dwell
            out[TAIL] = (f.entry[last][0] + d[0] - hi0, f.entry[last][1] + d[1] - lo0)
        return out

    def _atk_bells(self, origin: float, det: list) -> list[tuple[float, float]]:
        """VE: attack bells on exact paths (bell_track.AtkBellTracks: launch time and x, side; one branch per side
        still open, gone at its End Timer) into det; returns the bursts whose two bells are both on exact paths:
        (their middle x = the burst's anchor, launch time from the origin)."""
        at = self.atk_tracks
        ests = at.estimates()
        for e in ests:
            tk_ = at.type_of.get(e.iid, ATK_BELL)
            for sd in ((e.side,) if e.side else (1, -1)):
                x0, y0, vx0, vy0 = at.path_args(e, sd)
                det.append(DetBell(at.spec, x0, y0, vx0, vy0, 0, None, tk_, t0=origin - e.t_launch, sides=(0,),
                                   skin=SKIN_Z * e.sx, life=e.t_end - e.t_launch))
        cover = []
        paired = [e for e in ests if e.pair and e.side]
        for i, a in enumerate(paired):
            for b in paired[i + 1:]:
                if a.side == -b.side and abs(a.t_launch - b.t_launch) <= 0.05:
                    xm = 0.5 * (at.x0(a, a.side) + at.x0(b, b.side))
                    cover.append((xm, 0.5 * (a.t_launch + b.t_launch) - origin))
        return cover

    def _atk_covered(self, state: str, e_lo: float, e_hi: float, anchor: Anchor | None) -> bool:
        """A burst state's (or tail's) attack-bell union whose bells are both on exact paths (VE)."""
        lag = self._atk_lag.get(state)
        if anchor is None or lag is None:
            return False
        for xm, tl in self._atk_cover:
            if abs(xm - anchor.x) <= ATK_ANCHOR_TOL_U and \
                    e_lo - lag[1] - ATK_LAG_SLACK_S <= tl <= e_hi - lag[0] + ATK_LAG_SLACK_S:
                return True
        return False

    def _place(self, fam: str, state: str, e_lo: float, e_hi: float, ctx: Ctx, node: int, H: float,
               out: list[Placement], death_tail: bool = False) -> None:
        m = self.model
        f = m.families[fam]
        ws = f.world_sources.get(state, frozenset())
        p2 = ctx.phase == "P1" and ws and ws <= f.p2_only.get(state, frozenset())
        if ctx.anchor is not None:
            frames = ["anchor"]
            if not p2:
                frames.append("world")
        else:
            frames = ["world_all"]
        if state == TAIL and not death_tail:
            # An attack that ended into the decision chain left the boss underground: its tail is what outlives it
            # (attack bells, drop bells). The tail templates also hold the body of instances killed mid-attack
            # (support/BB_CHARGE/_tail: 66 instances, no tail source logged), which only a death end places.
            anchored = f.sources.get(TAIL, frozenset()) - ws - {m.boss_type}
            world = ws if not p2 else frozenset()
            if ctx.anchor is not None:
                frames = (["anchor"] if anchored else []) + (["world"] if world else [])
            else:
                frames = ["world_all"] if (anchored or world) else []
        srcs = f.sources.get(state, frozenset())
        if ctx.phase == "P1":
            srcs = srcs - f.p2_only.get(state, frozenset())
        n = int(math.floor((e_hi - e_lo) / BIN + 1e-6)) + 1
        es = [e_lo + i * BIN for i in range(n)]
        if es[-1] < e_hi - 1e-3:            # a 1 ms remainder rounds to the same 1/60 s bin
            es.append(e_hi)
        for fr in frames:
            key = m.key(fam, state, fr)
            if key is None:
                continue
            t0, t1 = self.meta[key]
            anchor = (ctx.anchor.x, ctx.anchor.y) if fr == "anchor" else None
            mirror = ctx.anchor.mirror if fr == "anchor" else 1
            # a union of drop-bell falls: in the oracle view every armed bell has its own self template, and a bell
            # not armed yet cannot hurt sooner than its arming lead, so the union only counts from then on
            allsrc = f.sources.get(state, frozenset())
            fsrc = ws if fr == "world" else (allsrc - ws if fr == "anchor" else allsrc)
            t_from = -math.inf
            if fr == "anchor" and fsrc and self._atk_cover and all(x.startswith(ATK_BELL) for x in fsrc) \
                    and self._atk_covered(state, e_lo, e_hi, ctx.anchor):
                continue           # VE: both of this burst's attack bells are on exact paths (Forecast.det)
            if fsrc and all(x.startswith(DROP_BELL) for x in fsrc) and not self.tracker.bells_unknown:
                if self.view == ORACLE:
                    t_from = self.bell_lead
                elif self.bell_tells:      # a bell whose cue is not out yet armed less than the cue's delay ago
                    t_from = self.bell_lead - TELL_DELAY["bell_dust"] - TELL_SLACK_S["bell_dust"]
            for e in es:
                on, off = e + t0, e + t1
                if off < -BIN or on > H + BIN:
                    continue
                if t_from > H + BIN:
                    continue
                out.append(Placement(key, -e, anchor, mirror, node, on, off, srcs, t_from))

    def _walk(self, state: str, e_lo: float, e_hi: float, ctx: Ctx, p: float, parent: int, H: float,
              nodes: list[Node], out: list[Placement], current: bool, depth: int) -> None:
        m = self.model
        if e_lo > H:
            return
        if len(nodes) >= MAX_NODES or depth > 40:
            self.truncated += 1          # a branch inside the horizon left out (tools/safe_windows counts them)
            return
        info = m.states.get(state)
        if info is None:
            return
        if state in m.attack_starts:
            fam = m.attack_starts[state]
            if ctx.family != fam:
                ctx.family = fam
                ctx.anchor = m.anchor(fam, ctx.direction)
        if state in m.dir_states:
            ctx.direction = state
        if state == "Rage Pos":
            ctx.raged = True
        if state in m.phase_marks:
            ctx.phase = m.phase_marks[state]
        nid = len(nodes)
        nodes.append(Node(nid, state, e_lo, e_hi, ctx.family, p, parent, ctx.anchor))
        fam = ctx.family
        if fam is not None and state in m.families[fam].states:
            self._place(fam, state, e_lo, e_hi, ctx, nid, H, out)
        x_lo, x_hi = e_lo + info.dwell[0], e_hi + info.dwell[1]
        if current:
            x_lo, x_hi = max(x_lo, BIN), max(x_hi, BIN)
        for nxt, pn in self._successors(state, ctx):
            c2 = replace(ctx)
            if fam is not None and state in m.families[fam].states and nxt in m.decision_states:
                self._place(fam, TAIL, x_lo, x_hi, ctx, nid, H, out)
                c2.family, c2.anchor, c2.direction = None, None, None
            if nxt in m.attack_starts and c2.family is not None and c2.family != m.attack_starts[nxt]:
                c2.family, c2.anchor = None, None
            dirs = None
            if nxt in m.attack_starts and c2.direction is None:
                fam2 = m.attack_starts[nxt]
                dirs = m.directions(fam2) or None
            if dirs:
                for dname in dirs:
                    c3 = replace(c2, direction=dname)
                    self._walk(nxt, x_lo, x_hi, c3, p * pn / len(dirs), nid, H, nodes, out, False, depth + 1)
            else:
                self._walk(nxt, x_lo, x_hi, c2, p * pn, nid, H, nodes, out, False, depth + 1)

    def _successors(self, state: str, ctx: Ctx) -> list[tuple[str, float]]:
        """Support successors with the scoring probability; structural rules: Rage Pos only before the rage
        (P1, not raged), with p 1 at hp <= the logged rage HP else 0; Bell Burst? by phase."""
        m = self.model
        succ = list(m.states[state].succ)
        if state == "Rage?":
            rage_possible = ctx.phase != "P2" and not ctx.raged
            p_rage = 0.0
            if rage_possible and ctx.phase == "P1" and ctx.hp is not None and m.rage_hp is not None:
                p_rage = 1.0 if ctx.hp <= m.rage_hp else 0.0
                if self.view != ORACLE and m.rage_hp < ctx.hp <= m.rage_hp + VE_RAGE_HP_SLACK:
                    p_rage = VE_RAGE_P
            elif rage_possible:
                p_rage = 0.03
            if p_rage == 1.0 and any(s == "Rage Pos" for s, _ in succ):
                # the rage is the FSM's rule, not a draw: every logged P1 decision with the boss at <= 75 HP went to
                # Rage Pos (311 of 311) and none above it did (1,990), live / gate runs 20261002_123347 ... 173956
                # (HP = 150 - the logged hits). The view's HP only counts hits it saw: a missed hit makes it higher,
                # never lower, so a count at or below the threshold is certain. Without this the vision view, which
                # cannot see Rage Pos underground, kept every other attack in support too and was FORCED_RISK through
                # all of Rage Pos / Rage Antic (view_compare, run 20261002_171806 i0 ep2)
                return [("Rage Pos", 1.0)]
            out = []
            for s, _ in succ:
                if s == "Rage Pos":
                    if rage_possible:
                        out.append((s, p_rage))
                else:
                    out.append((s, 1.0 - p_rage))
            return out
        if state == "Bell Burst?" and ctx.phase in m.p_burst:
            pb = m.p_burst[ctx.phase]
            return [(s, pb if s == "Burst Pos" else 1.0 - pb) for s, _ in succ]
        return succ


def load_hurtbox(path: str | Path | None = None) -> dict:
    """The hurtbox-per-phase table (ssbot.tools.hurtbox_table): {phase: {time bin: {median, p10, p90, n}}}."""
    p = Path(path) if path else Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / \
        "BellBeast_hurtbox.json"
    return json.loads(p.read_text("utf-8"))["phases"] if p.exists() else {}


def load_box_margin(path: str | Path | None = None) -> dict | None:
    """The vision view's box margins (ssbot.tools.boss_path_audit --margins): {phase: {k_max: [left, right, bottom,
    top]}, "_tau": {phase: {time bin: {k_max: [...]}}}}; None when the file is missing (the pogo gate then has no
    certain form in the vision view)."""
    p = Path(path) if path else Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / \
        "BellBeast_vision_box_margin.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text("utf-8"))
    return d["phases"] | ({"_tau": d["phases_tau"]} if d.get("phases_tau") else {})


def margin_xy(margin: float | tuple[float, float]) -> tuple[float, float]:
    return (float(margin), float(margin)) if isinstance(margin, (int, float)) else (float(margin[0]), float(margin[1]))


def load_planner_templates(model: BossModel, margin: float | tuple[float, float] = 0.0, npz: str | None = None
                           ) -> dict[str, hb.SpaceTimeTemplate]:
    """Cached per (enemy, margin, file): the dilation takes 1-2 s and the result is read-only."""
    return _load_planner_templates(model.enemy, margin_xy(margin), None if npz is None else str(npz))


@functools.lru_cache(maxsize=8)
def _load_planner_templates(enemy: str, margin: tuple[float, float], npz: str | None
                            ) -> dict[str, hb.SpaceTimeTemplate]:
    """The per-state and tail support templates of the model's families, dilated for a point query of the hurtbox
    centre: hero half-extents plus margin (x, y). Family-wide templates (t from the attack start) are not needed by
    the walk."""
    from ssbot.combat.boss_model import KNOWLEDGE
    mx, my = margin
    path = npz or (KNOWLEDGE / "enemies" / f"{enemy}_hitboxes.npz")
    tpls, _ = hb.load_templates(path, prefix=hb.SUPPORT)
    out = {}
    for k, t in tpls.items():
        if k.count("/") != 3 or k.split("/")[2].startswith("ent"):
            continue
        if t.t_pad < 1:
            raise ValueError(f"{k}: not a support template (no +-1 bin of export lag baked in)")
        out[k] = t.dilated(rx=hb.HERO_HALF_U[0] + mx, ry=hb.HERO_HALF_U[1] + my, key=k)
    return out


def offsets(T: int, frame_time: float) -> np.ndarray:
    """tk for rollout frames 0..T (frame k at k * frame_time game seconds from the origin)."""
    return np.arange(T + 1, dtype=np.float64) * frame_time


__all__: Sequence[str] = ("Forecaster", "Forecast", "BossTracker", "load_planner_templates", "offsets")
