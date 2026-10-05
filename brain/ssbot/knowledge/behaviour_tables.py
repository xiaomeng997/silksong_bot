"""Behaviour tables of a boss from combat logs (M2 W2; DESIGN §3.2.6 phase tables, §3.5.3 support vs probability,
§3.5.8 behaviour tables: counts, Dirichlet smoothing, quantiles; templates inflated by the validated residual; §4.4
enemy file).

    b = BehaviourBuilder(SPECS["BellBeast"])
    fights, skipped = run_fights(Path(r"C:\\ssbot\\data\\runs\\m2\\<run>"))     # closed recordings only
    for fight in fights + [human_fight(Path(r"C:\\ssbot\\data\\human\\<session>"), f0, f1)]:
        b.scan(fight)
    b.write(out_dir)          # <enemy>.json (§4.4 fields the data supports) + <enemy>_hitboxes.npz; raises
                              # ValidationFailed when a logged contact is not covered by the support

Input: fights, i.e. frame ranges of STATE streams: combat-run recordings (one per AttemptRecord line of
<run>/attempts_i*.jsonl, frames f_wake..f_end) and human sessions (ssbot.tools.raw_session, a range given by hand).
Output (BehaviourBuilder.build):
  graph      the boss's Control FSM edges with counts and, per source state (and per phase), Dirichlet(ALPHA = 0.5)
             smoothed successor probabilities with one extra "unseen" outcome (p_unseen); worst_case = fewer than
             N_WORST = 30 exits logged (users then assume the fastest reachable attack, DESIGN §3.2.6 item 5). Edges
             into the death states are kept as support but not normalised (a kill can interrupt any state).
             coverage.fsm_edges_extracted is true only with the FSM's static graph (--fsm-graph).
  dwell_s    per state game-time dwell quantiles (p0_5, p5, p50, p95, p99_5, n), from the frames of the fsm events
             (cumulative STATE "dt" = Time.deltaTime, so hit-stop counts as zero) with the FSM's own StateTime
             (t_in_prev) alongside; exits into a death state are left out.
  decisions  every branching state: which decision-time covariates the choice depends on (probability only). The
             candidates (each tagged V seen / O oracle only / D derived from what was seen before): distance and
             side to the boss when it is visible, its hidden position when the oracle exports it, hero world-x thirds
             over the observed range, phase, boss HP quarter, the fight's attack history (previous family, its run,
             attacks since each family, the facing of the last directed attack, where the boss was last seen) and
             this state's own choice history (last choice, its run, decisions since each outcome: the counters of
             PlayMaker's SendRandomEventV3 max-repeat / max-miss rule). Each gets a G-test of independence (chi2 by
             Cochran's rule, else a numba Monte Carlo permutation test of up to N_PERM_MAX draws), Holm-corrected over
             all tests at ALPHA_TEST; significant ones are added in order of p while they stay significant given the
             ones already kept (stratified test) and lower the log loss on held-out recordings (2 folds); the choice
             is tabulated on the kept ones ("*" = the unconditional row). Every p-value and the held-out log loss are
             published. No distance bins are assumed.
  attacks    per attack family: instance counts (by phase and direction), state sequence, durations, anchor support
             (min/max; quantiles are probability only), body-collider offsets in the anchor frame and the hidden-
             position offset, time-to-damage per state, hitbox windows (+-1 frame of export lag) with presence per
             phase, damage, reach unions of the support templates and the validated contact residual.
  entities   every damage source seen: category, src bits, collider kinds and names, FSM states with the fraction of
             exported frames their damage colliders are enabled (frames exported without colliders are counted
             apart), what arms them, lifetimes, where and when they arm (arm_pos) and their self template.
  build_info code revision and dirty flag, every input recording with its meta status and hashes, the npz sha256.
The space-time templates (ssbot.knowledge.hitbox_tables) are accumulated in the same pass.

Attack instance: starts when the Control FSM enters an attack-start state (the per-encounter table), ends when it
returns to a decision state or the boss dies. It keeps the entry of every state, the boss trajectory, the hits taken
and every enabled damage collider per frame of the boss and of the entities armed during it. An entity is armed while
its FSM is out of the rest states or one of its damage colliders is enabled; it belongs to the instance current when
it armed and is followed after that instance ends until it disarms, stays out of the export for ABSENT_CLOSE_F frames
(left the view), or tail_max_s passes. Entities armed when a fight's scan starts are ambient until they first disarm.
Templates take every collider that is enabled with damage and eff != 0 (support_threat): can_cause_damage is false
only in the post-hit / down-spike cooldown, which depends on what the hero did (trial run: 75 boss poly and 30 AtkBell
frames), so it is kept for statistics only.

Validation (DESIGN §3.5.8 "inflated by the p99 residual", M2 round-1 review): every damage frame and every frame of a
blocked contact (damage_blocked first_f..last_f) is a contact. Its residual, per template set (anchor frame + arena
hazards, world_all, per state (both), the source entity's self template), is the distance from the hero hurtbox
(STATE hero.box) to the logged occupancy, pairing each box with its own frame's time as the planner does: the box of
f-1 at t_f-1 +- 1 bin or the box of f at t_f +- 1 bin, whichever is closer (pairing the box of f-1 with t_f +- 1 bin
matched it against geometry from f+1, and five contacts then lay 0.014-0.059 u outside the support the planner
queries, M2 round-2 verifier). Support templates ("support/<key>" in the npz) are the logged ones dilated by the
largest residual of their set and +-1 bin, so the planner's query (box_k at t_k against the support plus the
hurtbox) flags frame f-1 or f of every logged contact. A contact farther than R_FAIL_U from any of its sets, outside
every attack, or whose source had no exported damage collider in f-2..f (with the oracle's collider names: not the
collider the damage event named) and was not exported without colliders then (an export hole), makes the build
fail. Ambient hazards (armed when a scan starts) form one static world template, in support at every time
(_ambient/world); their contacts are checked against it alone.
Damage-dealing entities exported without any collider while not hidden are export holes (oracle bug after a savestate
load: the boss's first Charge Emerge of every fight has colliders == [] although its body deals damage, M2 round-1
review); the hitbox windows of the holed states and every ttd span containing a holed frame are left out of the
statistics (the templates keep the instance), and the counts are reported. In sample the residual is the
export-vs-contact gap; for instances the support was not built from, recordings alternate between N_FOLDS folds,
every template is also kept per fold, and every contact is measured against the other fold's occupancy (residual_u
.holdout, coverage.validation.heldout, also with +-HELD_T_BINS bins of timing slack).
Self templates (ent/<type_key>/self): every armed stretch of a hazard entity relative to its position and time of
arming. The family templates are the union of the logged instances, so a bell that starts anywhere in a range is
covered only where some instance started; the self template follows it from wherever it starts (on 27 fights the
Rage family template held out only 319 of 608 contacts, the bells' self templates 7,140 of 7,180; on all 266 fights
both hold out every contact).

Measured on Bell Beast (knowledge/1.0.30000/enemies/BellBeast.json, 2026-10-01: the trial run 20261001_121446 (2
data-policy episodes), the 263 closed fights of run 20261001_122249 (i0..i3_000..002) and the person's fight of
2026-09-30, frames 64000-68460: 266 fights, 2.87 M frames, 45,515 s of game time):
- Instances: BB_CHARGE 3054, BB_LEAP 2821, BB_BURST 3031, BB_RAGE 266 (once per fight); no FSM edge or state with
  fewer than 30 logged exits.
- 184,521 contacts (11,676 hits, 172,845 i-frame-blocked frames): none uncovered, none unexplained, none outside an
  attack; 1,297 (170 hits) had no exported collider and were explained by the first charge's export hole (13,679 holed
  Charge Emerge frames over 266 fights, plus 70 Charge End / Dig In frames in the person's fight). Residual max
  (each hero box at its own frame's time): Charge 0, Leap 0.153 (anchor) / 0.163 u (world_all), Burst 0.126 / 0.136,
  Rage 0 (Ptn L per-state 0.065); self templates 0-0.127 u (AtkBell L 0.127, R 0.109, DropBell L2 0.107); p99 0
  everywhere. The old pairing (box of f-1 at t_f) gave Burst 0.096 and AtkBell R 0.010, and the planner's query then
  missed five contacts (tests/fixtures/bellbeast_planner_contacts.msgpack.zst). Held out by recording: 184,516 of
  184,521 contacts inside the full build's support for the anchor and world_all sets (5 up to 0.214 u away), 184,520
  / 184,519 for the per-state sets, all within +-4 bins; all 69,133 for the self templates.
- Hitbox presence counts only instances without an export hole in the state: the Charge Emerge body box is enabled in
  every one (P1 and P2 1.0; the 267 holed first charges are n_export_holes, not "box absent").
- Body box centre minus the anchor (attacks.<A>.anchor.body_offset.by_dir_flip) is fixed per facing: Burst (+0.539,
  -2.68) with flipX False, (-0.539, -2.68) with flipX True, so Entity.pos converts to the anchor without a sweep.
- STATE hero.box is 0.5 x 2.0789 u on all 2.87 M frames (hitbox_tables.HERO_HALF_U).
- The decision chain Submerged -> Rage? -> Bell Burst? -> Choose Dir -> Set L|R -> Move Choice -> attack start runs
  within one frame after Submerged's 1.000-1.017 s. Set L / Set R name the side the boss emerges on (x 75.03 /
  95.72; y 5.49 for the charge, 0.99 for the leap; flipX False / True, every time) and it attacks toward the other
  side: Set L -> mirror +1, Set R -> mirror -1. The first attack after the wake comes straight from Submerged Init
  (no Set state; direction from flipX at the anchor): a charge from the right in every fight.
- Decisions follow the SendRandomEventV3 counters, not distance (the boss is hidden at every decision, so distance to
  it could not be tested on these recordings, which predate ents[].hidden): Choose Dir and Move Choice are 50/50
  until one outcome has been missed twice, then forced (about 800 decisions per side, p >= 0.998); Bell Burst? never
  bursts three times in a row and is forced after three misses (p 0.99), else 0.36-0.44, with fewer bursts at boss
  HP > 75 %; held-out log loss 0.49 / 0.48 / 0.49 nats against 0.69 / 0.69 / 0.65 unconditional. Hero world x is
  significant for Choose Dir alone (p 3e-29) and still in sample given the counters (p 3e-5), but does not lower the
  held-out log loss, so it is not kept. Rage? -> Rage Pos exactly at the first decision of P1 with boss HP <= 75
  (observed 60-75; held-out log loss 0.001). Choose 1st Pattern (Ptn L 134 / Ptn R 132) depends on nothing tested.
- The FSM's own StateTime (fsm event t_in_prev) equals the frame-time dwell for every Control state.
- The boss is not in "ents" (not in the HealthManager active list) from Submerged through the antic states, so the
  anchor is its first exported position: Charge Emerge and Leap Out 1.00-1.02 s, Burst Out 1.20-1.22 s, Rage Burst
  2.20-2.23 s after the start. The burst emerges anywhere in x 81.2-91.2, unrelated to the hero; hence the world_all
  templates. With the oracle's ents[].hidden export the boss's underground position is recorded as anchor_hidden.
- Boss colliders: a body box ("Boss Scene/Bone Beast" in damage events) and one poly, 7 points while charging,
  9 points while leaping ("PolyCollider", "LeapCollider"); all 2 masks, hazard ENEMY, parry bits COUNTER only.
- AtkBell L / R (hazard; damage_hero + projectile; circle r 1.274) arm on Burst Out's first frame 2 u left / right
  of the boss and outlive the attack; DropBell L/L2/M/M2/R/R2 hang at y 13.74 and drop from an x that varies over
  ~8 u per bell (e.g. M2 81.2-89.2): in the Rage pattern on a fixed schedule after Ptn L / Ptn R, and M2 in P2 at
  Burst Out + 0.5 s and on Leap Land.
"""
import bisect
import functools
import hashlib
import json
import math
import time
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import numba
import numpy as np

from ssbot.ipc.ents import DAMAGE_FLAGS, DAMAGE_SRC, PARRY_BITS, SRC_BITS, bits, hazard_name, is_threat
from ssbot.knowledge import hitbox_tables as hb
from ssbot.train.encounters import BELL_BEAST as _BELL_BEAST_ENC

SCHEMA = 2
BUILD = "1.0.30000"
QUANTILES = (0.005, 0.05, 0.5, 0.95, 0.995)
QKEYS = ("p0_5", "p5", "p50", "p95", "p99_5")
ALPHA = 0.5
N_WORST = 30
TARGET_INSTANCES = 200        # M2 exit: >= 200 logged instances per A-class attack (DESIGN §5)
ABSENT_CLOSE_F = 30           # an armed entity missing from the export this long has left the view
STATE_KEYS = ("dt", "hero", "ents", "ev")
TAIL = "_tail"
SELF = "ent"                  # self templates: ent/<type_key>/self
AMBIENT = "_ambient/world"    # hazards armed when a scan started: one time-invariant (static) world template
ORPHAN = "_orphan"            # contacts of an armed hazard owned by no instance (checked against its self template)
R_FAIL_U = 0.5                # a contact farther than this from its family's occupancy is a support hole
R_SEARCH_U = 1.0
# held-out residuals of the per-state sets are searched this far (the per-family margins of a multi-enemy build come
# from them: support_recall --encounter; beyond R_SEARCH_U the in-sample validation already fails)
R_MARGIN_SEARCH_U = 3.0
LAG_F = 2                    # a contact's source must show an exported damage collider within f-2..f
RING_F = 1800                 # frames of per-frame contact context kept (blocked stretches are reported late)
MW_FOLLOW_F = 90              # a multi-hit's follow-up hits land up to this long after its collider was exported
ALPHA_TEST = 0.01             # family-wise level of the decision covariate tests (Holm)
RUN_CAP, SINCE_CAP = 4, 5     # history covariate levels: run 1..4+, attacks since 0..5+ / never
HELD_LL_GAIN = 1e-3           # a conditioner is kept only if it lowers the held-out log loss by this (nats)
N_FOLDS = 2                   # held-out folds of recordings for the residual on unseen instances
HELDOUT_MISS_MAX = 0.001      # held-out contacts beyond R_FAIL_U above this share: the support is not shown to cover
                              # unseen instances (validation.support_conservative false)
HELD_T_BINS = 4               # held-out residual also measured with +-4 bins (67 ms): spatial gap vs timing spread
N_PERM = 2000
N_PERM_MAX = 50000
EVENT_KINDS = ("fsm", "damage", "damage_blocked", "hit")


class ValidationFailed(RuntimeError):
    """A logged contact is not covered by the support templates, or its source has no exported geometry."""


def support_threat(c: dict) -> bool:
    """A collider that belongs in the support templates: enabled, with damage, eff != 0 (can_cause_damage ignored)."""
    d = c.get("damage")
    return bool(c.get("enabled") and d and d.get("eff") != 0)


def multi_wounder_threat(c: dict) -> bool:
    """An enabled DamageHero collider exported with damage 0 on an entity with the multi_wounder src bit: a multi-hit
    collider whose hits the hornet_multi_wounder FSM deals (Forum run 20261002_221727 i2 ep0: Choristor "Whip Hit 2",
    Reed "ParrySlash Hit", Minister "Slash Collider" damage events, 1 mask each, while exported with dealt 0)."""
    d = c.get("damage")
    return bool(c.get("enabled") and d is not None and not d.get("dealt"))


def _cols_box(cols: list) -> tuple | None:
    """Bounding box (x0, y0, x1, y1) of colliders' world vertices."""
    xs, ys = [], []
    for c in cols:
        v = c.get("verts_world") or ()
        xs += v[0::2]
        ys += v[1::2]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _nearest(entries: list, box: tuple | None):
    """Of (owner, arm, box) entries, the one whose box is nearest to the hero box (the first without a hero box)."""
    if len(entries) == 1 or box is None:
        return entries[0]

    def gap(en):
        b = en[2]
        if b is None:
            return math.inf
        return math.hypot(max(b[0] - box[2], box[0] - b[2], 0.0), max(b[1] - box[3], box[1] - b[3], 0.0))
    return min(entries, key=gap)


@dataclass(frozen=True, slots=True)
class BehaviourSpec:
    """Per-encounter segmentation table."""
    enemy: str
    scene: str
    boss_type: str                     # entity type_key of the boss
    control_fsm: str
    hp: int
    dormant: tuple[str, ...]           # Control states before the wake
    death_states: tuple[str, ...]
    attack_starts: dict[str, str]      # Control state -> attack family
    decision_states: tuple[str, ...]   # the chain between attacks; entering one ends the current attack
    dir_states: dict[str, int]         # decision state -> mirror of the next attack (+1 faces +x, -1 faces -x)
    directed: tuple[str, ...]          # families that face a direction (mirrored anchor templates)
    phase_marks: dict[str, str]        # entering this Control state switches to that phase
    phases: dict[str, str]
    initial_phase: str
    world_fixed: tuple[str, ...]       # type_key prefixes of arena-fixed hazards (world-frame templates)
    rest_states: tuple[str, ...] = ("Init", "Dormant")   # FSM states of a hazard entity that mean "not armed"
    flip_mirror: tuple[int, int] = (1, -1)               # mirror for flipX False / True when no direction state
    dist_bins_u: tuple[float, ...] = (0.0, 3.0, 6.0, 10.0, 99.0)   # distance covariate bins (tested, not assumed)
    # hero height above floor_y bins (covariate "hero_height", tested like the others; None: not a candidate). The
    # Forum sets it: the left-wall top pocket changes the Choir Clapper's choices within the same distance cells
    # (forum.md 13.8: Idle at |dx| 3-10 u, pocket 0 / 214 Evade Scuttle or Dmg Attack, ground 35 / 122)
    height_bins_u: tuple[float, ...] | None = None
    arena_x: tuple[float, float] = (0.0, 0.0)
    floor_y: float = 0.0
    tail_max_s: float = 6.0
    # multi-enemy fights (ssbot.knowledge.gauntlet_tables): the time between attacks as one more family (enemies whose
    # body deals contact damage while they walk or fly about), a kill ("hit" event with dead) as the death when the
    # Control FSM has no death state, and the type_key prefixes of the hazard entities this enemy spawns
    idle_family: str | None = None
    death_on_kill: bool = False
    projectiles: tuple[str, ...] = ()
    # hazards that arm after the attack that made them is over (the Choir Clapper's Bomb Cast bombs explode while it
    # walks again; the rune of a Jump Cast 1.3 s after the landing): (type_key prefix, owner families); such a hazard
    # arming within spawn_window_s after an instance of those families ended belongs to that instance
    spawns: tuple[tuple[str, tuple[str, ...]], ...] = ()
    spawn_window_s: float = 4.0
    # enemies with the oracle's multi_wounder src bit: their multi-hit colliders (Choristor Whip Hit 1-6, Reed
    # ParrySlash Hit, Minister Slash Collider) are exported with damage dealt 0 but hurt (hornet_multi_wounder FSM)
    multi_wounder: bool = False
    # attack families or Control states the FSM cannot reach (structure, not missing data): (name, reason) pairs.
    # The tables list them under "structurally_absent" and the coverage does not count such a family as missing
    absent: tuple[tuple[str, str], ...] = ()


def absent_marks(spec: BehaviourSpec, tables: dict) -> dict:
    """Mark the spec's structurally absent families and states in a tables dict (BehaviourBuilder.tables, or a table
    JSON written before the spec carried them): "structurally_absent" {name: reason}, and per absent family in
    coverage.families "absent" (its reason) with "missing" 0. Returns the dict."""
    if not spec.absent:
        return tables
    marks = dict(spec.absent)
    tables["structurally_absent"] = marks
    fams = (tables.get("coverage") or {}).get("families") or {}
    for fam, reason in marks.items():
        if fam in fams:
            fams[fam]["absent"] = reason
            fams[fam]["missing"] = 0
    return tables


BELL_BEAST = BehaviourSpec(
    enemy="BellBeast", scene=_BELL_BEAST_ENC.scene, boss_type=_BELL_BEAST_ENC.boss_type,
    control_fsm=_BELL_BEAST_ENC.control_fsm, hp=150, dormant=_BELL_BEAST_ENC.dormant,
    death_states=_BELL_BEAST_ENC.death_states,
    attack_starts={"Emerge Antic C": "BB_CHARGE", "Emerge Antic L": "BB_LEAP", "Burst Pos": "BB_BURST",
                   "Rage Pos": "BB_RAGE"},
    decision_states=("Submerged Init", "Submerged", "Rage?", "Bell Burst?", "Choose Dir", "Set L", "Set R",
                     "Move Choice"),
    dir_states={"Set L": 1, "Set R": -1}, directed=("BB_CHARGE", "BB_LEAP"),
    phase_marks={"Rage End": "P2"},
    phases={"P1": "from the wake until the Rage pattern ends", "P2": "after Rage End (DropBell M2 joins Bell Burst "
            "and Leap)"},
    initial_phase="P1", world_fixed=("BoneBeast DropBell",), arena_x=_BELL_BEAST_ENC.arena_x,
    floor_y=_BELL_BEAST_ENC.floor_y)

SPECS = {s.enemy: s for s in (BELL_BEAST,)}


# ---- small statistics --------------------------------------------------------------------------------------

def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), nd)


def quantiles(values: Iterable[float], nd: int = 4) -> dict:
    """{p0_5, p5, p50, p95, p99_5, min, max, n} (linear interpolation); {"n": 0} when empty."""
    v = np.asarray([x for x in values if x is not None and math.isfinite(x)], np.float64)
    if v.size == 0:
        return {"n": 0}
    q = np.quantile(v, QUANTILES)
    out = {k: _r(x, nd) for k, x in zip(QKEYS, q)}
    out.update(min=_r(v.min(), nd), max=_r(v.max(), nd), n=int(v.size))
    return out


def dirichlet(counts: dict[str, int], alpha: float = ALPHA) -> tuple[dict[str, float], float]:
    """Posterior-mean successor probabilities under a symmetric Dirichlet(alpha) prior over the logged successors
    plus one "unseen" outcome: p_j = (n_j + alpha) / (N + alpha (K + 1)). Returns (p by successor, p_unseen)."""
    n = sum(counts.values())
    denom = n + alpha * (len(counts) + 1)
    return {k: (c + alpha) / denom for k, c in counts.items()}, alpha / denom


def dist_bin(d: float | None, edges: tuple[float, ...]) -> int | None:
    if d is None or not math.isfinite(d):
        return None
    i = int(np.searchsorted(np.asarray(edges), d, side="right")) - 1
    return min(max(i, 0), len(edges) - 2)


def chi2_sf(x: float, df: int) -> float:
    """P(chi2_df >= x): the regularised upper incomplete gamma Q(df / 2, x / 2) (series / Lentz continued fraction)."""
    if df <= 0:
        return 1.0
    if x <= 0.0:
        return 1.0
    a, z = 0.5 * df, 0.5 * x
    lead = -z + a * math.log(z) - math.lgamma(a)
    if z < a + 1.0:
        ap, s = a, 1.0 / a
        d = s
        for _ in range(10000):
            ap += 1.0
            d *= z / ap
            s += d
            if abs(d) < abs(s) * 1e-15:
                break
        return max(0.0, 1.0 - s * math.exp(lead))
    tiny = 1e-300
    b = z + 1.0 - a
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return min(1.0, math.exp(lead) * h)


def g_stat(y: np.ndarray, x: np.ndarray, s: np.ndarray, ky: int, kx: int,
           ks: int) -> tuple[float, int, float, float]:
    """G statistic of independence of codes y and x within strata s, its degrees of freedom (non-empty rows and
    columns per stratum), the smallest expected count and the share of expected counts below 5 (strata with at
    least two rows and columns)."""
    n = np.bincount((s * kx + x) * ky + y, minlength=ks * kx * ky).reshape(ks, kx, ky).astype(np.float64)
    tot = n.sum(axis=(1, 2))
    r, c = n.sum(axis=2), n.sum(axis=1)
    e = r[:, :, None] * c[:, None, :] / np.where(tot > 0, tot, 1.0)[:, None, None]
    nz = n > 0
    g = 2.0 * float((n[nz] * np.log(n[nz] / e[nz])).sum())
    rows, cols = (r > 0).sum(axis=1), (c > 0).sum(axis=1)
    live = tot > 0
    df = int(((rows - 1) * (cols - 1))[live].sum())
    cells = (live & (rows > 1) & (cols > 1))[:, None, None] & (r > 0)[:, :, None] & (c > 0)[:, None, :]
    if not cells.any():
        return g, df, math.inf, 0.0
    ec = e[cells]
    return g, df, float(ec.min()), float((ec < 5.0).mean())


@numba.njit(cache=True)
def _g_table(n: np.ndarray) -> float:
    g = 0.0
    ks, kx, ky = n.shape
    for k in range(ks):
        tot = 0.0
        for i in range(kx):
            for j in range(ky):
                tot += n[k, i, j]
        if tot == 0.0:
            continue
        for i in range(kx):
            r = 0.0
            for j in range(ky):
                r += n[k, i, j]
            for j in range(ky):
                if n[k, i, j] > 0.0:
                    c = 0.0
                    for i2 in range(kx):
                        c += n[k, i2, j]
                    g += n[k, i, j] * math.log(n[k, i, j] * tot / (r * c))
    return 2.0 * g


@numba.njit(cache=True)
def _perm_exceed(ys: np.ndarray, xs: np.ndarray, ss: np.ndarray, starts: np.ndarray, ky: int, kx: int, ks: int,
                 g_obs: float, n_perm: int, seed: int) -> int:
    """Permutations (y shuffled within each stratum; arrays sorted by stratum, starts = stratum offsets) whose G
    reaches g_obs."""
    np.random.seed(seed)
    y = ys.copy()
    n = np.zeros((ks, kx, ky))
    ge = 0
    for _ in range(n_perm):
        for k in range(ks):
            a, b = starts[k], starts[k + 1]
            for i in range(b - 1, a, -1):
                j = a + np.random.randint(0, i - a + 1)
                y[i], y[j] = y[j], y[i]
        n[:] = 0.0
        for i in range(y.shape[0]):
            n[ss[i], xs[i], y[i]] += 1.0
        if _g_table(n) >= g_obs - 1e-9:
            ge += 1
    return ge


def perm_exceed_ref(ys: np.ndarray, xs: np.ndarray, ss: np.ndarray, starts: np.ndarray, ky: int, kx: int, ks: int,
                    g_obs: float, n_perm: int, seed: int) -> int:
    """Python reference of _perm_exceed (same shuffles, parity test)."""
    return _perm_exceed.py_func(ys, xs, ss, starts, ky, kx, ks, g_obs, n_perm, seed)


def independence_test(y: np.ndarray, x: np.ndarray, s: np.ndarray | None = None, n_perm: int = N_PERM,
                      seed: int = 0, n_perm_max: int = N_PERM_MAX) -> dict:
    """G-test of y independent of x given strata s: chi2 when the expected counts allow it (Cochran: none below 1,
    at most 20 % below 5), else a Monte Carlo permutation test (y shuffled within strata, numba): n_perm
    permutations, extended to n_perm_max while p < 0.05, so the smallest p (1 / (n_perm_max + 1)) can pass a Holm
    correction over the ~100 tests of a build. Codes are small ints >= 0."""
    y, x = np.asarray(y, np.int64), np.asarray(x, np.int64)
    s = np.zeros_like(y) if s is None else np.asarray(s, np.int64)
    ky, kx, ks = int(y.max()) + 1, int(x.max()) + 1, int(s.max()) + 1
    g, df, emin, small = g_stat(y, x, s, ky, kx, ks)
    if df == 0:
        return {"G": _r(g), "df": 0, "p": 1.0, "method": "none (one level)"}
    if emin >= 1.0 and small <= 0.2:
        return {"G": _r(g), "df": df, "p": chi2_sf(g, df), "method": "chi2"}
    order = np.argsort(s, kind="stable")
    ys, xs, ss = y[order], x[order], s[order]
    starts = np.searchsorted(ss, np.arange(ks + 1)).astype(np.int64)
    ge = done = 0
    for target in (n_perm, max(n_perm, n_perm_max)):
        if done and (1 + ge) / (1 + done) >= 0.05:
            break
        ge += _perm_exceed(ys, xs, ss, starts, ky, kx, ks, g, target - done, seed + done)
        done = target
    return {"G": _r(g), "df": df, "p": (1 + ge) / (1 + done), "method": f"permutation ({done})"}


def _cap_tail(values: list, cap: int, min_n: int = N_WORST) -> tuple[list, int]:
    """Ordinal history levels as strings: ints >= k become "k+", with k the largest cap' <= cap whose tail holds at
    least min_n values (sparse tails would force permutation tests); non-int levels ("never", "none") are kept."""
    ints = Counter(v for v in values if isinstance(v, int))
    k = max(1, cap)
    while k > 1 and sum(n for v, n in ints.items() if v >= k) < min_n:
        k -= 1
    return [v if not isinstance(v, int) else (str(v) if v < k else f"{k}+") for v in values], k


def holm(p: list[float]) -> list[float]:
    m = len(p)
    order = sorted(range(m), key=lambda i: p[i])
    out, run = [1.0] * m, 0.0
    for j, i in enumerate(order):
        run = max(run, min(1.0, (m - j) * p[i]))
        out[i] = run
    return out


def collider_key(type_key: str, c: dict) -> str:
    kind = c.get("kind", "?")
    n = len(c.get("verts_world") or ()) // 2
    return f"{type_key}:{kind}{n}" if kind in ("poly", "edge") else f"{type_key}:{kind}"


def _strip_clone(name: str) -> str:
    name = name.strip()
    if name.endswith("(Clone)"):
        name = name[:-7].strip()
    if name.endswith(")") and " (" in name and name[name.rindex(" (") + 2:-1].isdigit():
        name = name[:name.rindex(" (")]
    return name


def match_source(src: str, known: Iterable[str]) -> tuple[str | None, str | None]:
    """(type_key, child name) of a damage event source path: the deepest path component that is a known entity
    type_key (exact, after dropping "(Clone)" / " (n)"), and the component below it (a collider GameObject such as
    "LeapCollider"), if any. (None, None) when no component matches."""
    known = known if isinstance(known, (set, frozenset, dict)) else set(known)
    parts = [p for p in str(src).split("/") if p]
    for i in range(len(parts) - 1, -1, -1):
        name = parts[i] if parts[i] in known else _strip_clone(parts[i])
        if name in known:
            return name, (parts[i + 1] if i + 1 < len(parts) else None)
    return None, None


# ---- fights (inputs) ---------------------------------------------------------------------------------------

@dataclass(slots=True)
class Fight:
    """One fight to scan: frames f0..f1 of a recording (kind "rec") or of a human session (kind "human")."""
    kind: str
    path: Path
    f0: int
    f1: int
    id: str
    outcome: str | None = None
    info: dict = field(default_factory=dict)


def recording_status(path: Path) -> str | None:
    try:
        return json.loads((Path(path) / "meta.json").read_text("utf-8")).get("status")
    except (OSError, json.JSONDecodeError):
        return None


def run_fights(run_dir: Path, closed_only: bool = True) -> tuple[list[Fight], list[str]]:
    """The fights of a combat run (ssbot.tools.combat_run): one per AttemptRecord with a wake frame, an end frame
    and a recording; with closed_only, recordings still being written (meta status != "closed") are skipped."""
    run_dir = Path(run_dir)
    fights, skipped = [], []
    for p in sorted(run_dir.glob("attempts_i*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                skipped.append(f"{p.name}: unreadable line (being written?)")
                continue
            fid = f"{run_dir.name}/i{a.get('instance')}/ep{a.get('episode')}"
            if a.get("f_wake") is None or a.get("f_end") is None or not a.get("recording"):
                skipped.append(f"{fid}: no wake / end / recording ({a.get('outcome')}: {a.get('reason')})")
                continue
            rec = Path(a["recording"])
            if not rec.is_dir():  # moved run: the recording sits under <run>/rec/<date>/<profile>/<name>
                found = list(run_dir.glob(f"rec/*/*/{rec.name}"))
                rec = found[0] if found else rec
            status = recording_status(rec)
            if closed_only and status != "closed":
                skipped.append(f"{fid}: recording {rec.name} is {status or 'missing'}")
                continue
            pol = a.get("policy") or {}
            fights.append(Fight("rec", rec, int(a["f_wake"]), int(a["f_end"]), fid, a.get("outcome"),
                                {"seed": a.get("seed"), "mode": a.get("mode"), "hits": a.get("hits"),
                                 "would_die": a.get("would_die"), "unit": a.get("unit"),
                                 # R1 provenance (ssbot.train.forum_policy): types the policy never hit below
                                 # protect_hp, and its tactic segments [frame, tactic, target, pocket, protect]
                                 "protect": list(pol.get("protect") or ()), "protect_hp": pol.get("protect_hp"),
                                 "segments": pol.get("segments")}))
    return fights, skipped


def human_fight(session: Path, f0: int, f1: int, outcome: str | None = None) -> Fight:
    session = Path(session)
    return Fight("human", session, int(f0), int(f1), f"human/{session.name}", outcome)


def raw_session_states(session: Path, f0: int | None = None, f1: int | None = None,
                       keys: tuple[str, ...] | None = None) -> Iterator[dict]:
    """STATE dicts with f0 <= f <= f1 from a human session's state.raw.zst (ssbot.tools.raw_session layout),
    streamed: frames before f0 are only peeked for "f", and reading stops after f1."""
    import zstandard

    from ssbot.ipc.framing import HEADER, MsgType
    from ssbot.record import formats

    with (Path(session) / "state.raw.zst").open("rb") as fh:
        rd = zstandard.ZstdDecompressor().stream_reader(fh, read_size=1 << 20)
        buf = bytearray()
        pos = 0
        while True:
            if len(buf) - pos < 4 or len(buf) - pos < 4 + int.from_bytes(buf[pos:pos + 4], "little"):
                del buf[:pos]
                pos = 0
                more = rd.read(1 << 22)
                if not more:
                    return
                buf += more
                continue
            n = int.from_bytes(buf[pos:pos + 4], "little")
            body = bytes(buf[pos + 4:pos + 4 + n])
            pos += 4 + n
            if body[0] != MsgType.STATE:
                continue
            flags = int.from_bytes(body[2:4], "little")
            payload = memoryview(body)[HEADER.size - 4:]
            f = formats.peek(payload, ("f",), flags).get("f")
            if not isinstance(f, int) or (f0 is not None and f < f0):
                continue
            if f1 is not None and f > f1:
                return
            yield formats.decode(payload, flags) if keys is None else formats.peek(payload, ("f", *keys), flags)


def fight_states(fight: Fight, keys: tuple[str, ...] | None = STATE_KEYS) -> Iterator[dict]:
    if fight.kind == "rec":
        from ssbot.record.recorder import RecordingReader
        return RecordingReader(fight.path).states(fight.f0, fight.f1, keys=keys)
    if fight.kind == "human":
        return raw_session_states(fight.path, fight.f0, fight.f1, keys=keys)
    raise ValueError(f"unknown fight kind {fight.kind!r}")


@functools.lru_cache(maxsize=2)
def _recording_events(path: Path, kinds: tuple[str, ...]) -> tuple[list[int], list[tuple[int, str, dict]]]:
    """A recording's events.jsonl of the given kinds, parsed once for all the fights in it: (frames, events)."""
    from ssbot.record.recorder import RecordingReader
    evs = sorted(((ev["frame"], ev["kind"], ev.get("data") or {}) for ev in RecordingReader(path).events(set(kinds))
                  if isinstance(ev.get("frame"), int)), key=lambda e: e[0])
    return [e[0] for e in evs], evs


def fight_events(fight: Fight, kinds: tuple[str, ...] = ("fsm", "damage")) -> Iterator[tuple[int, str, dict]]:
    """(frame, kind, data) of the fight's STATE events; a recording's events.jsonl avoids decoding STATEs."""
    if fight.kind == "rec" and (fight.path / "events.jsonl").is_file():
        frames, evs = _recording_events(Path(fight.path), tuple(kinds))
        yield from evs[bisect.bisect_left(frames, fight.f0):bisect.bisect_right(frames, fight.f1)]
        return
    for s in fight_states(fight, keys=("ev",)):
        for ev in s.get("ev") or ():
            if ev.get("k") in kinds:
                yield ev.get("f", s["f"]), ev["k"], ev.get("d") or {}


def static_edges(graph: dict | None) -> tuple[set[tuple[str, str]], set[str]]:
    """(from, to) edges of an FSM graph in the oracle's RPC "fsm.graph" shape ({states: [{name, transitions
    {event: to}}], global {event: to}}), and the targets of its global transitions."""
    if not graph:
        return set(), set()
    edges = {(st["name"], to) for st in graph.get("states") or () for to in (st.get("transitions") or {}).values()
             if to}
    return edges, {to for to in (graph.get("global") or {}).values() if to}


# ---- per-fight scan ----------------------------------------------------------------------------------------

@dataclass(slots=True)
class Transition:
    """One Control transition with its decision-time context (nothing after frame f is used)."""
    fight: str
    f: int
    t: float                 # game time since the scan start (s)
    frm: str | None
    to: str
    t_in_prev: float | None
    hero_x: float | None
    hero_y: float | None
    boss_x: float | None     # the boss's position when it is exported and not hidden this frame (else None)
    boss_y: float | None
    boss_hidden: tuple | None   # (x, y) of a hidden export this frame (oracle only, ents[].hidden)
    boss_hp: int | None      # last exported HP, updated by "hit" events while the boss is not exported
    phase: str
    prev: str | None = None  # family of the previous attack of the fight
    run: int = 0             # how many attacks in a row were of that family
    since: dict = field(default_factory=dict)   # family -> attacks since its last instance (absent: never)
    prev_mirror: int | None = None   # mirror of the last directed attack (+1 faced +x)
    last_seen: tuple | None = None   # (x, y) of the boss's last non-hidden export (history, not its position now)
    fold: int = 0                    # held-out fold of the recording
    local: tuple = ()                # earlier outcomes of this same state in the fight, oldest first

    @property
    def dx(self) -> float | None:
        return None if self.hero_x is None or self.boss_x is None else self.hero_x - self.boss_x

    @property
    def dy(self) -> float | None:
        return None if self.hero_y is None or self.boss_y is None else self.hero_y - self.boss_y


@dataclass(slots=True)
class Dwell:
    state: str
    dwell_s: float
    state_time_s: float | None
    to: str
    frames: int
    phase: str
    fold: int = 0            # held-out fold of the fight (support_recall --encounter: per-fold dwell ranges)


@dataclass(slots=True)
class Sample:
    """One enabled damage collider in one frame of an attack instance."""
    t: float                 # s since the attack start
    state: str               # the boss's Control state then (TAIL once the attack is over)
    ts: float                # s since that state's entry (since the attack's end for TAIL)
    src: str                 # collider_key
    world: bool              # arena-fixed hazard (world frame) or anchor frame
    verts: np.ndarray        # (k, 2) world coordinates
    dmg: tuple               # (dealt, eff, hazard_type, flags, parry, can_cause_damage)
    name: str | None = None  # collider GameObject name (oracle ents[].colliders[].name), when exported


@dataclass(slots=True)
class EntitySeg:
    """One armed stretch of a non-boss damage entity."""
    iid: int
    type_key: str
    world: bool
    t_on: float              # s since the owner's start (game time since scan start when unowned)
    trigger: str | None      # boss Control state when it armed
    owner: "Instance | None"
    t_off: float | None = None   # last armed frame (same clock as t_on)
    last_f: int = 0
    last_t: float = 0.0
    end: str | None = None
    arm_T: float = 0.0           # game time since the scan start when it armed
    arm_pos: tuple = (0.0, 0.0)  # its transform position then (the origin of its "self" template)
    uid: int = 0                 # unique over the build (BehaviourBuilder.arming)
    box: tuple | None = None     # its damage colliders' bounding box on the last armed frame (x0, y0, x1, y1)


@dataclass(slots=True)
class Instance:
    family: str
    phase: str
    fight: str
    f_start: int
    t_start: float
    dir: str | None
    mirror: int | None
    states: list                            # [(state, frame, s since start)], start state first
    ctx: Transition | None = None
    hero_start: tuple | None = None
    boss_hp: int | None = None
    f_end: int | None = None
    t_end: float | None = None              # s since start
    end: str | None = None                  # "rest" | "death" | "chain" | "fight_end"
    anchor: tuple | None = None             # boss transform position at its first non-hidden export
    anchor_t: float | None = None
    anchor_flip: bool | None = None
    anchor_body: tuple | None = None        # (body box centre - anchor, render_aabb centre - anchor) at the anchor
    anchor_hidden: tuple | None = None      # (x, y, t) of the first hidden export in the instance
    path: list = field(default_factory=list)       # [(t, x, y)] boss world positions
    hits: list = field(default_factory=list)       # [(t, state, source, amount, hazard)]
    samples: list = field(default_factory=list)
    ents: list = field(default_factory=list)       # EntitySeg
    t_last: float = 0.0                             # last sample / tail time (s since start)
    holes: int = 0                                  # frames a damage entity of it was exported without colliders
    hole_t: list = field(default_factory=list)      # s since start of those frames
    fold: int = 0                                   # held-out fold of its recording (BehaviourBuilder.validate)

    def state_at(self, t: float) -> tuple[str, float]:
        """(Control state, s since its entry) at t s after the start; TAIL after the end."""
        if self.t_end is not None and t > self.t_end + 1e-9:
            return TAIL, t - self.t_end
        name, t0 = self.states[0][0], 0.0
        for st, _, ts in self.states:
            if ts <= t + 1e-9:
                name, t0 = st, ts
            else:
                break
        return name, t - t0


@dataclass(slots=True)
class Contact:
    """A frame of hero contact with a damage source: a hit ("damage") or an i-frame-blocked one ("blocked")."""
    kind: str
    f: int
    fight: str
    src: str
    tk: str | None
    inst: Instance | None
    t: float | None          # s since the owner's start
    state: str | None
    ts: float | None
    boxes: list              # hero boxes (x0, y0, x1, y1) at f-1 and f
    exported: bool           # the source had a support_threat collider in f-2..f (the collider it named, when the
    hole: bool               # oracle exports collider names); hole: exported without colliders in f-2..f
    T: float = 0.0           # game time since the scan start
    arm: tuple | None = None   # (arm_T, arm_pos) of a non-boss source's armed stretch (its "self" template)
    box_dt: list = field(default_factory=list)   # game time of each box minus T: [-(T_f - T_f-1), 0.0]
    ambient: bool = False    # the source is an ambient hazard (armed when the scan started): _ambient/world only
    named_gap: bool = False  # the oracle exported the source's other colliders by name, but not the one it named
    fold: int = 0            # held-out fold of the recording
    res: dict = field(default_factory=dict)   # template set -> residual (u; inf = none within R_SEARCH_U)
    ho: dict = field(default_factory=dict)    # template set -> held-out residual (against the other folds'
    #                                           occupancy; per-state sets searched to R_MARGIN_SEARCH_U)
    follow: bool = False    # a follow-up hit of a connected multi-hit (BehaviourSpec.multi_wounder): its collider
                             # was exported within MW_FOLLOW_F, not now; left out of the validation


@dataclass(slots=True)
class _Frame:
    T: float
    box: tuple | None
    cur: Instance | None
    owners: dict             # type_key -> [(owning instance or None, (arm_T, arm_pos), box)] of its armed entities
    armed: dict              # type_key -> [(arm_T, arm_pos)] of their armed stretches
    threat: set              # type_keys with a support_threat collider
    names: dict              # type_key -> names (without "(Clone)" / " (n)") of its support_threat colliders, when
    holes: set               #   exported; holes: type_keys exported without colliders while not hidden
    ambient: set             # type_keys of ambient hazards armed this frame
    ended: Instance | None = None   # the instance that ended on this frame (a kill frame's contact belongs to it)


class FightScanner:
    """Streams one fight's STATEs into transitions, dwells, attack instances and contacts (handed to the builder)."""

    def __init__(self, spec: BehaviourSpec, fight_id: str, builder: "BehaviourBuilder", fold: int = 0):
        self.spec, self.fight, self.b, self.fold = spec, fight_id, builder, fold
        self.T = 0.0
        self.last_f: int | None = None
        self.frames = 0
        self.gaps = 0
        self.hero: tuple | None = None
        self.hero_box: tuple | None = None
        self.boss_now: dict | None = None       # the boss entity exported and not hidden this frame
        self.boss_hidden: tuple | None = None   # (x, y) when exported hidden this frame
        self.boss_last: tuple | None = None     # (x, y) of the last non-hidden export
        self.last_mirror: int | None = None     # mirror of the last directed attack
        self.boss_hp: int | None = None
        self.ctl: str | None = None
        self.ctl_t: float | None = None
        self.ctl_f: int | None = None
        self.phase = spec.initial_phase
        self.dir: str | None = None
        self.cur: Instance | None = None
        self.done: list[Instance] = []          # ended, waiting for their armed entities to disarm
        self.segs: dict[int, EntitySeg] = {}
        self.ambient: set[int] = set()
        self.dead = False
        self.hist: list[str] = []
        self.local: dict[str, list[str]] = defaultdict(list)   # Control state -> its outcomes so far
        self.known: set[str] = {spec.boss_type}
        self.ring: dict[int, _Frame] = {}
        self.pending: list[tuple] = []
        self.ended_now: Instance | None = None
        self.ambient_now: set[str] = set()      # type_keys of ambient hazards armed on the last frame
        self.mw_seen: dict[tuple, int] = {}     # (type_key, collider name) -> last frame enabled as a multi-hit

    # ---- feed ----

    def feed(self, s: dict) -> None:
        f = s.get("f")
        if not isinstance(f, int) or (self.last_f is not None and f <= self.last_f):
            return
        dt = float(s.get("dt") or 0.0)
        if self.last_f is not None:
            gap = f - self.last_f
            if gap > 1:
                self.gaps += gap - 1
            self.T += dt * gap
        first = self.last_f is None
        self.last_f = f
        self.frames += 1
        hero = s.get("hero") or {}
        pos = hero.get("pos")
        if pos:
            self.hero = (float(pos[0]), float(pos[1]))
        box = hero.get("box")
        self.hero_box = (float(box[0]), float(box[1]), float(box[2]), float(box[3])) if box else None
        if self.hero_box is not None:
            self.b.hero_box_size(self.hero_box)
        ents = s.get("ents") or []
        boss = None
        self.boss_hidden = None
        for e in ents:
            self.known.add(e.get("type_key"))
            if e.get("type_key") == self.spec.boss_type:
                if e.get("hidden"):
                    self.boss_hidden = (float(e["pos"][0]), float(e["pos"][1]))
                elif boss is None:
                    boss = e
        self.boss_now = boss
        if boss is not None:
            self.boss_last = (float(boss["pos"][0]), float(boss["pos"][1]))
            if boss.get("hp") is not None:
                self.boss_hp = boss.get("hp")
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "fsm" and d.get("fsm") == self.spec.control_fsm and self._is_boss(d.get("obj")):
                self._control(f, d)
            elif k == "damage":
                self._hit(f, d)
                self.pending.append(("damage", f, f, str(d.get("source"))))
            elif k == "damage_blocked" and isinstance(d.get("first_f"), int) and isinstance(d.get("last_f"), int):
                self.pending.append(("blocked", d["first_f"], d["last_f"], str(d.get("source"))))
            elif k == "hit" and d.get("type_key") == self.spec.boss_type and d.get("hp_after") is not None:
                self.boss_hp = d.get("hp_after")
                if d.get("dead") and self.spec.death_on_kill:
                    self._kill(f)
        threat, names, holes, ambient = set(), {}, set(), set()
        self._boss(f, boss, threat, names, holes)
        if self.cur is not None and self.boss_hidden is not None and self.cur.anchor_hidden is None \
                and self.cur.anchor is None:
            self.cur.anchor_hidden = (*self.boss_hidden, self.T - self.cur.t_start)
        owners, armed = self._entities(f, ents, first, threat, names, holes, ambient)
        self.ring[f] = _Frame(self.T, self.hero_box, self.cur, owners, armed, threat, names, holes, ambient,
                              self.ended_now)
        self.ambient_now = ambient - set(armed)
        self.ended_now = None
        self.ring.pop(f - RING_F, None)
        if self.pending:
            self._resolve(f)
        self._retire(f)

    def _is_boss(self, name) -> bool:
        b = self.spec.boss_type
        return isinstance(name, str) and (name == b or name.startswith(b + "(") or name.startswith(b + " ("))

    # ---- Control FSM ----

    def _context(self, f: int, frm, to: str, t_in_prev) -> Transition:
        hx, hy = self.hero if self.hero else (None, None)
        b = self.boss_now
        bx, by = (float(b["pos"][0]), float(b["pos"][1])) if b is not None else (None, None)
        since = {}
        for k, fam in enumerate(reversed(self.hist)):
            since.setdefault(fam, k)
        run = 0
        for fam in reversed(self.hist):
            if fam != self.hist[-1]:
                break
            run += 1
        return Transition(self.fight, f, self.T, frm, to, t_in_prev, hx, hy, bx, by, self.boss_hidden, self.boss_hp,
                          self.phase, self.hist[-1] if self.hist else None, run, since, self.last_mirror,
                          self.boss_last, self.fold, tuple(self.local[frm]) if frm else ())

    def _control(self, f: int, d: dict) -> None:
        spec = self.spec
        frm, to = d.get("from"), d.get("to")
        if not isinstance(to, str):
            return
        tr = self._context(f, frm, to, d.get("t_in_prev"))
        self.b.transitions.append(tr)
        if frm is not None and to not in spec.death_states:
            self.local[frm].append(to)
        if frm is not None and frm == self.ctl and self.ctl_t is not None and to not in spec.death_states:
            self.b.dwells.append(Dwell(frm, self.T - self.ctl_t, d.get("t_in_prev"), to, f - self.ctl_f, self.phase,
                                       self.fold))
        self.ctl, self.ctl_t, self.ctl_f = to, self.T, f
        cur = self.cur
        idle = spec.idle_family
        if to in spec.death_states:
            if cur is not None:
                self._end(cur, f, "death")
            self.dead = True
        elif to in spec.attack_starts and cur is not None and cur.family == spec.attack_starts[to] \
                and to != cur.states[0][0]:
            # another entry state of the attack already running (Reed: Stab Pos -> Stab Antic; Stab Antic is also
            # entered straight from Evade End)
            cur.states.append((to, f, self.T - cur.t_start))
        elif to in spec.attack_starts:
            if cur is not None:
                self._end(cur, f, "chain")
            self.dead = False      # a pooled enemy (the Maestro's Song Automaton Tiny) comes back after a kill
            self._start(spec.attack_starts[to], to, f, tr)
            self.hist.append(spec.attack_starts[to])
        elif to in spec.decision_states:
            if cur is not None and cur.family != idle:
                self._end(cur, f, "rest")
            if to in spec.dir_states:
                self.dir = to
            if idle is not None and not self.dead:
                if self.cur is None:
                    self._start(idle, to, f, tr)
                else:
                    self.cur.states.append((to, f, self.T - self.cur.t_start))
        elif cur is not None:
            cur.states.append((to, f, self.T - cur.t_start))
        elif to not in spec.dormant:
            self.b.counters[f"control state outside attacks: {to}"] += 1
        if to in spec.phase_marks:
            self.phase = spec.phase_marks[to]

    def _start(self, fam: str, to: str, f: int, tr: Transition) -> None:
        spec = self.spec
        mirror = spec.dir_states.get(self.dir) if fam in spec.directed else 1
        self.cur = Instance(family=fam, phase=self.phase, fight=self.fight, f_start=f, t_start=self.T,
                            dir=self.dir if fam in spec.directed else None, mirror=mirror,
                            states=[(to, f, 0.0)], ctx=tr, hero_start=self.hero, boss_hp=self.boss_hp,
                            fold=self.fold)
        if fam in spec.directed and mirror is not None:
            self.last_mirror = mirror
        if fam != spec.idle_family:
            self.dir = None

    def _kill(self, f: int) -> None:
        """A kill without a death state in the Control FSM (BehaviourSpec.death_on_kill)."""
        if self.cur is not None:
            self._end(self.cur, f, "death")
        self.dead = True

    def _end(self, inst: Instance, f: int, reason: str) -> None:
        inst.f_end, inst.t_end, inst.end = f, self.T - inst.t_start, reason
        self.done.append(inst)
        self.ended_now = inst
        if self.cur is inst:
            self.cur = None

    # ---- hits ----

    def _owner_now(self, tk: str | None, f: int) -> Instance | None:
        """The instance owning an armed entity of type tk (a bell still bouncing; with several armed, the owner of
        the one nearest to the hero box), else the current one, else one that ended this frame (the kill's own hit
        lands after the transition)."""
        if tk is not None and tk != self.spec.boss_type:
            fr = self.ring.get(f) or self.ring.get(f - 1)   # events are read before this frame's entities
            entries = fr.owners.get(tk) if fr is not None else None
            if entries:
                return _nearest(entries, self.hero_box)[0]
            for inst in ([self.cur] if self.cur else []) + self.done[::-1]:
                if any(seg.end is None and seg.type_key == tk for seg in inst.ents):
                    return inst
        return self.cur or next((i for i in reversed(self.done) if i.f_end == f), None)

    def _hit(self, f: int, d: dict) -> None:
        src = str(d.get("source"))
        tk, _ = match_source(src, self.known)
        if tk in self.ambient_now:   # an ambient hazard's hit belongs to no attack (validated against _ambient/world)
            self.b.counters["hits by ambient hazards"] += 1
            return
        owner = self._owner_now(tk, f)
        if owner is None:
            self.b.counters["hits outside attacks"] += 1
            self.b.loose_hits.append((self.fight, f, src, self.ctl))
            return
        t = self.T - owner.t_start
        st, _ = owner.state_at(t)
        owner.hits.append((t, st, src, int(d.get("amount") or 0), str(d.get("hazard"))))

    def _resolve(self, f: int) -> None:
        """Turn the contacts reported so far into Contact records (blocked stretches arrive when they end)."""
        for kind, f0, f1, src in self.pending:
            tk, _ = match_source(src, self.known)
            go = _strip_clone(str(src).split("/")[-1])  # the GameObject that dealt the damage: its collider's name
            for ff in range(f0, f1 + 1):
                fr = self.ring.get(ff)
                if fr is None:
                    self.b.counters["contact frames outside the scanned range"] += 1
                    continue
                near = [self.ring[g] for g in range(ff - LAG_F, ff + 1) if g in self.ring]
                boss = tk == self.spec.boss_type
                ambient = tk is not None and not boss and any(tk in r.ambient for r in near) \
                    and not any(tk in r.armed for r in near)
                # several armed entities of one type (bells of different throws): the one nearest the hero box
                entry = None
                if tk is not None and not boss and not ambient:
                    entry = next((_nearest(self.ring[g].owners[tk], fr.box) for g in range(ff, ff - LAG_F - 1, -1)
                                  if g in self.ring and self.ring[g].owners.get(tk)), None)
                if tk is None or ambient:
                    owner = None
                elif boss:
                    owner = fr.cur
                else:
                    owner = (entry[0] if entry is not None else None) or fr.cur
                if owner is None and not ambient:  # a kill frame: the ended attack's geometry was exported until then
                    owner = next((self.ring[g].ended for g in range(ff, ff - LAG_F - 1, -1)
                                  if g in self.ring and self.ring[g].ended is not None), None)
                # with collider names in the export, the source must show the collider it named (the boss exported
                # with its body box but without LeapCollider is a partial export hole, not "exported")
                named = [r.names[tk] for r in near if tk in r.names]
                listed = tk is not None and any(tk in r.threat for r in near)
                exported = any(go in n for n in named) if named else listed
                hole = tk is not None and any(tk in r.holes for r in near)
                prev = self.ring.get(ff - 1)
                pairs = [(r.box, r.T - fr.T) for r in (prev, fr) if r is not None and r.box is not None]
                t = st = ts = None
                if owner is not None:
                    t = fr.T - owner.t_start
                    st, ts = owner.state_at(t)
                arm = entry[1] if entry is not None else None
                self.b.contacts.append(Contact(kind, ff, self.fight, src, tk, owner, t, st, ts, [b for b, _ in pairs],
                                               exported, hole, fr.T, arm, [d for _, d in pairs], ambient,
                                               bool(named) and not exported, self.fold,
                                               follow=not exported and ff - self.mw_seen.get((tk, go), -10**9)
                                               <= MW_FOLLOW_F))
        self.pending = []

    # ---- colliders ----

    @staticmethod
    def _dmg(c: dict) -> tuple:
        d = c["damage"]
        return d.get("dealt"), d.get("eff"), d.get("hazard_type"), d.get("flags"), d.get("parry"), \
            d.get("can_cause_damage")

    def _sample(self, inst: Instance, type_key: str, c: dict, world: bool) -> None:
        t = self.T - inst.t_start
        st, ts = inst.state_at(t)
        v = np.asarray(c["verts_world"], np.float32).reshape(-1, 2)
        inst.samples.append(Sample(t, st, ts, collider_key(type_key, c), world, v, self._dmg(c), c.get("name")))
        inst.t_last = max(inst.t_last, t)

    def _threats(self, e: dict, tk: str, threat: set, names: dict) -> list:
        mw = self.spec.multi_wounder and bool(int(e.get("src") or 0) & SRC_BITS["multi_wounder"])
        out = [c for c in e.get("colliders") or () if support_threat(c) or (mw and multi_wounder_threat(c))]
        if mw and self.last_f is not None:
            for c in out:
                if c.get("name") and multi_wounder_threat(c):   # dealt 0 (Whip Hit: eff 2, dealt 0)
                    self.mw_seen[(tk, _strip_clone(c["name"]))] = self.last_f
        if out:
            threat.add(tk)
            named = {_strip_clone(c["name"]) for c in out if c.get("name")}
            if named:
                names.setdefault(tk, set()).update(named)
        return out

    def _boss(self, f: int, boss: dict | None, threat: set, names: dict, holes: set) -> None:
        if boss is None:
            return
        tk = self.spec.boss_type
        hole = bool(int(boss.get("src") or 0) & DAMAGE_SRC) and isinstance(boss.get("colliders"), list) \
            and not boss["colliders"]
        self.b.entity_frame(boss, self.ctl, boss=True)
        cur = self.cur
        threats = self._threats(boss, tk, threat, names)
        if hole:
            holes.add(tk)
            self.b.holes[(tk, str(self.ctl))] += 1
            if cur is not None:
                cur.holes += 1
                cur.hole_t.append(self.T - cur.t_start)
        if cur is None:
            if threats:
                self.b.counters[f"boss damage colliders outside attacks ({self.ctl})"] += 1
            return
        t = self.T - cur.t_start
        bx, by = float(boss["pos"][0]), float(boss["pos"][1])
        if cur.anchor is None:
            cur.anchor, cur.anchor_t, cur.anchor_flip = (bx, by), t, bool(boss.get("flipX"))
            body = next((c for c in boss.get("colliders") or () if c.get("kind") == "box"), None)
            bc = np.asarray(body["verts_world"], np.float64).reshape(-1, 2).mean(axis=0) if body else None
            ra = boss.get("render_aabb")
            cur.anchor_body = (None if bc is None else (bc[0] - bx, bc[1] - by),
                               None if not ra else ((ra[0] + ra[2]) / 2 - bx, (ra[1] + ra[3]) / 2 - by))
            if cur.mirror is None:
                cur.mirror = self.spec.flip_mirror[1 if cur.anchor_flip else 0]
                if cur.family in self.spec.directed:
                    self.last_mirror = cur.mirror
        cur.path.append((t, bx, by))
        for c in threats:
            self._sample(cur, tk, c, False)

    def _entities(self, f: int, ents: list, first: bool, threat: set, names: dict, holes: set,
                  ambient: set) -> tuple[dict, dict]:
        spec = self.spec
        seen = set()
        for e in ents:
            tk = e.get("type_key")
            if tk == spec.boss_type or not (int(e.get("src") or 0) & DAMAGE_SRC):
                continue
            if e.get("hidden"):
                self.b.entity_frame(e, self.ctl, boss=False, hidden=True)
                continue
            iid = e["iid"]
            seen.add(iid)
            fsms = e.get("fsms") or ()
            fst = fsms[0]["state"] if fsms else None
            threats = self._threats(e, tk, threat, names)
            if isinstance(e.get("colliders"), list) and not e["colliders"]:
                holes.add(tk)
                self.b.holes[(tk, str(fst))] += 1
            armed = bool(threats) or (fst is not None and fst not in spec.rest_states)
            self.b.entity_frame(e, self.ctl, boss=False, fsm_state=fst, enabled=bool(threats))
            if first and armed:
                self.ambient.add(iid)
            if iid in self.ambient:
                if armed:
                    ambient.add(tk)
                    self.b.ambient_sample(tk, threats, self.fold)
                    continue
                self.ambient.discard(iid)  # ambient only until it first disarms; a later arming is attributed
                continue
            seg = self.segs.get(iid)
            if armed and seg is None:
                owner = self._spawner(tk)
                world = tk.startswith(spec.world_fixed)
                t_on = self.T - owner.t_start if owner else self.T
                seg = self.segs[iid] = EntitySeg(iid, tk, world, t_on, self.ctl, owner, last_f=f, last_t=t_on,
                                                 arm_T=self.T, arm_pos=(float(e["pos"][0]), float(e["pos"][1])))
                if owner is not None:
                    owner.ents.append(seg)
                else:
                    self.b.counters[f"armed outside attacks: {tk}"] += 1
                self.b.arming(seg, owner)
            if seg is None:
                continue
            seg.last_f = f
            if not armed:
                self._close(seg, "disarmed")
                continue
            seg.last_t = self.T - seg.owner.t_start if seg.owner else self.T
            seg.box = _cols_box(threats) or (float(e["pos"][0]), float(e["pos"][1])) * 2
            for c in threats:
                self.b.self_sample(seg, self.T - seg.arm_T, c, self.fold)
            if seg.owner is not None:
                if isinstance(e.get("colliders"), list) and not e["colliders"]:
                    seg.owner.holes += 1
                    seg.owner.hole_t.append(seg.last_t)
                for c in threats:
                    self._sample(seg.owner, tk, c, seg.world)
        # per type_key every armed entity: (owning instance or None, (arm_T, arm_pos), its colliders' box now)
        owners: dict[str, list] = defaultdict(list)
        armed: dict[str, list] = defaultdict(list)
        for iid, seg in list(self.segs.items()):
            if iid not in seen and f - seg.last_f > ABSENT_CLOSE_F:
                self._close(seg, "left view")
                continue
            if seg.owner is not None and seg.owner.t_end is not None and \
                    self.T - seg.owner.t_start - seg.owner.t_end > spec.tail_max_s:
                self._close(seg, "tail cap")
                continue
            owners[seg.type_key].append((seg.owner, (seg.arm_T, seg.arm_pos), seg.box))
            armed[seg.type_key].append((seg.arm_T, seg.arm_pos))
        return dict(owners), dict(armed)

    def _spawn_families(self, tk: str) -> tuple[str, ...]:
        return next((fams for p, fams in self.spec.spawns if tk == p or tk.startswith(p)), ())

    def _spawner(self, tk: str) -> "Instance | None":
        """The instance a hazard arming now belongs to: the current one, unless BehaviourSpec.spawns names the
        families that make it and the current one is not of them: then the latest of them that ended within
        spawn_window_s (else the current one)."""
        fams = self._spawn_families(tk)
        cur = self.cur
        if not fams or (cur is not None and cur.family in fams):
            return cur
        late = next((i for i in reversed(self.done) if i.family in fams and i.t_end is not None
                     and self.T - i.t_start - i.t_end <= self.spec.spawn_window_s), None)
        return late or cur

    def _close(self, seg: EntitySeg, why: str) -> None:
        seg.end = why
        seg.t_off = seg.last_t
        self.segs.pop(seg.iid, None)

    def _retire(self, f: int) -> None:
        keep = []
        spawners = {fam for _, fams in self.spec.spawns for fam in fams}
        for inst in self.done:
            if any(seg.end is None for seg in inst.ents) or (
                    inst.family in spawners and inst.t_end is not None
                    and self.T - inst.t_start - inst.t_end <= self.spec.spawn_window_s):
                keep.append(inst)
            else:
                self.b.add_instance(inst)
        self.done = keep

    def close(self) -> None:
        """End of the fight: close everything still open."""
        if self.pending and self.last_f is not None:
            self._resolve(self.last_f)
        if self.cur is not None:
            self._end(self.cur, self.last_f or 0, "fight_end")
        for seg in list(self.segs.values()):
            self._close(seg, "fight_end")
        for inst in self.done:
            self.b.add_instance(inst)
        self.done = []
        self.ring = {}


# ---- aggregation -------------------------------------------------------------------------------------------

class _PathAcc:
    """Boss positions (anchor frame) per time bin over instances: n, x/y min, max, sum."""

    def __init__(self):
        self.d: dict[int, list] = {}

    def add(self, b: int, x: float, y: float) -> None:
        r = self.d.get(b)
        if r is None:
            self.d[b] = [1, x, x, y, y, x, y]
        else:
            r[0] += 1
            r[1], r[2], r[3], r[4] = min(r[1], x), max(r[2], x), min(r[3], y), max(r[4], y)
            r[5] += x
            r[6] += y

    def array(self, bin_s: float) -> np.ndarray:
        """(nt, 8): t, n, x_min, x_max, y_min, y_max, x_mean, y_mean."""
        rows = [[b * bin_s, r[0], r[1], r[2], r[3], r[4], r[5] / r[0], r[6] / r[0]] for b, r in sorted(self.d.items())]
        return np.array(rows, np.float64).reshape(-1, 8)


@dataclass(slots=True)
class _InstSummary:
    """What is kept of an instance once its samples are rasterised."""
    family: str
    phase: str
    fight: str
    f_start: int
    dir: str | None
    mirror: int | None
    anchor: tuple | None
    anchor_t: float | None
    anchor_flip: bool | None
    anchor_body: tuple | None
    anchor_hidden: tuple | None
    hero_start: tuple | None
    boss_hp: int | None
    ctx: Transition | None
    states: list
    t_end: float | None
    end: str | None
    t_tail: float
    hits: list
    n_samples: int
    sources: list
    ttd: dict                # state -> s from its entry to the next enabled damage collider (export holes left out)
    ttd_start: float | None
    holes: int
    hole_states: frozenset   # states with export-hole frames (their windows and spanning ttd are left out)
    ttd_holed: frozenset     # ttd entries left out because an export hole lies in their span ("start" included)
    path: np.ndarray | None  # (n, 3) t, x', y' (anchor frame)
    windows: list            # [(state, src, frame, t_on, t_off, x0, y0, x1, y1)] in the template frame


@dataclass(slots=True)
class Built:
    tables: dict
    raw: dict                # key -> SpaceTimeTemplate (logged occupancy)
    support: dict            # "support/<key>" -> raw dilated by its residual and +-1 bin
    extra: dict


class BehaviourBuilder:
    """Accumulates scanned fights into the behaviour tables and the space-time templates."""

    def __init__(self, spec: BehaviourSpec, cell: float = hb.CELL_U, bin_s: float = hb.BIN_S,
                 keep_paths: bool = False, fsm_graph: dict | None = None):
        self.spec, self.cell, self.bin_s, self.keep_paths = spec, cell, bin_s, keep_paths
        self.fsm_graph = fsm_graph  # the Control FSM's static graph (oracle RPC "fsm.graph"), if dumped
        self.transitions: list[Transition] = []
        self.dwells: list[Dwell] = []
        self.instances: list[_InstSummary] = []
        self.fights: list[dict] = []
        self.counters: Counter = Counter()
        self.holes: Counter = Counter()      # (type_key, state) -> frames exported without colliders
        self.ambient_frames: Counter = Counter()   # type_key -> armed frames while ambient (before its first disarm)
        self.loose_hits: list = []
        self.contacts: list[Contact] = []
        self.acc: dict[str, hb.TemplateAccumulator] = {}
        self.paths: dict[str, _PathAcc] = defaultdict(_PathAcc)
        # (family, state, src) -> per-instance windows [t_on_state, t_off_state, t_on, t_off, phase]
        self.windows: dict[tuple, list] = defaultdict(list)
        self.src_info: dict[tuple, dict] = {}
        self.ent: dict[str, dict] = {}
        self.segs: list[tuple] = []          # (EntitySeg, family of its owner or None)
        self._n_inst = 0
        self._built: Built | None = None
        self.recordings: dict[str, int] = {}
        self._folds: dict[str, dict[int, hb.SpaceTimeTemplate]] = {}
        self.hero_box: list[float] = [math.inf, -math.inf, math.inf, -math.inf, 0]   # w min/max, h min/max, n
        self.arm_at: dict[str, list] = defaultdict(list)   # type_key -> [(x, y, owner family, boss state)]
        self._n_self = 0

    def hero_box_size(self, box: tuple) -> None:
        w, h = box[2] - box[0], box[3] - box[1]
        hb_ = self.hero_box
        hb_[0], hb_[1], hb_[2], hb_[3] = min(hb_[0], w), max(hb_[1], w), min(hb_[2], h), max(hb_[3], h)
        hb_[4] += 1

    # ---- input ----

    def scan(self, fight: Fight, states: Iterable[dict] | None = None) -> dict:
        """Scan one fight (its STATEs from fight_states unless given). Returns a per-fight summary."""
        self._built = None
        rec = fight.id if fight.kind == "states" else str(fight.path)
        fold = self.recordings.setdefault(rec, len(self.recordings)) % N_FOLDS  # recordings alternate between folds
        sc = FightScanner(self.spec, fight.id, self, fold)
        n0 = len(self.instances)
        for s in fight_states(fight) if states is None else states:
            sc.feed(s)
        sc.close()
        info = {"id": fight.id, "kind": fight.kind, "path": str(fight.path), "f0": fight.f0, "f1": fight.f1,
                "outcome": fight.outcome, "frames": sc.frames, "gaps": sc.gaps, "game_s": _r(sc.T, 2),
                "instances": len(self.instances) - n0, "died": sc.dead, "fold": fold}
        self.fights.append(info)
        return info

    def scan_states(self, states: Iterable[dict], fight_id: str = "states") -> dict:
        f = Fight("states", Path("."), -1, -1, fight_id)
        return self.scan(f, states)

    def entity_frame(self, e: dict, ctl: str | None, boss: bool, fsm_state: str | None = None,
                     enabled: bool = False, hidden: bool = False) -> None:
        """Per type_key bookkeeping: category, src, collider kinds and names, frames per FSM state and enabled
        frames (frames exported without colliders or hidden are counted apart, not in the fractions)."""
        tk = e["type_key"]
        info = self.ent.get(tk)
        if info is None:
            info = self.ent[tk] = {"category": e.get("category"), "src": 0, "layers": set(), "colliders": Counter(),
                                   "names": Counter(), "radius": set(), "by_state": defaultdict(Counter),
                                   "boss": boss, "hidden": 0, "no_colliders": 0, "cooldown": 0}
        info["src"] |= int(e.get("src") or 0)
        info["layers"].add(e.get("layer"))
        if hidden or e.get("hidden"):
            info["hidden"] += 1
            return
        key = ctl if boss else fsm_state
        row = info["by_state"][key]
        cols = e.get("colliders")
        if isinstance(cols, list) and not cols:
            info["no_colliders"] += 1
            row["no_colliders"] += 1
            return
        row["frames"] += 1
        for c in cols or ():
            ck = collider_key("", c)[1:]
            info["colliders"][ck] += 1
            if c.get("name"):
                info["names"][f"{ck}={c['name']}"] += 1
            if c.get("r") is not None:
                info["radius"].add(round(float(c["r"]), 3))
            if support_threat(c):
                row[f"enabled {ck}"] += 1
                if not is_threat(c):
                    info["cooldown"] += 1
        if enabled or (boss and any(support_threat(c) for c in cols or ())):
            row["enabled"] += 1

    def arming(self, seg: EntitySeg, owner: Instance | None) -> None:
        self.segs.append((seg, owner.family if owner else None))
        ts = owner.state_at(seg.t_on)[1] if owner is not None else None
        self.arm_at[seg.type_key].append((*seg.arm_pos, owner.family if owner else None, seg.trigger, ts))
        self._n_self += 1
        seg.uid = self._n_self  # unique over fights: the instance id of its self-template samples

    def self_sample(self, seg: EntitySeg, t: float, c: dict, fold: int) -> None:
        """One enabled damage collider of an armed entity relative to where it armed, t s after arming: its "self"
        template (ent/<type_key>/self, anchor frame with the arming position as anchor, mirror 1)."""
        v = np.asarray(c["verts_world"], np.float64).reshape(-1, 2) - seg.arm_pos
        r = hb.rasterize(v, self.cell)
        if r is not None:
            self._acc(f"{SELF}/{seg.type_key}", "anchor", f"self@{fold}").add_patch(
                int(round(t / self.bin_s)), *r, instance=seg.uid)

    def ambient_sample(self, tk: str, threats: list, fold: int = 0) -> None:
        """An ambient (armed at the scan start) hazard's colliders: the union over every armed frame, a static
        (time-invariant) world template, in support at every t."""
        for c in threats:
            r = hb.rasterize(np.asarray(c["verts_world"], np.float64).reshape(-1, 2), self.cell)
            if r is not None:
                self._acc(AMBIENT.split("/")[0], "world", f"world@{fold}", static=True).add_patch(0, *r)
        self.ambient_frames[tk] += 1

    def _acc(self, key: str, frame: str, suffix: str | None = None, static: bool = False) -> hb.TemplateAccumulator:
        k = f"{key}/{suffix or frame}"
        a = self.acc.get(k)
        if a is None:
            a = self.acc[k] = hb.TemplateAccumulator(k, frame, self.cell, self.bin_s, static=static)
        return a

    def add_instance(self, inst: Instance) -> None:
        """Rasterise an ended instance into the templates, keep its summary, drop its samples."""
        self._n_inst += 1
        iid = self._n_inst
        fam = inst.family
        first_dmg = None
        per_src: dict[tuple, list] = {}
        skipped = 0
        # state segments (TAIL from the end): a sample within one bin of a boundary also goes to the neighbouring
        # state's template, so a contact on a state's first frame finds the geometry of the frame before it
        seg_t = [(st, ts) for st, _, ts in inst.states] + ([(TAIL, inst.t_end)] if inst.t_end is not None else [])
        seg_starts = [ts for _, ts in seg_t]
        edge = self.bin_s + 1e-6
        for smp in inst.samples:
            rw = hb.rasterize(smp.verts, self.cell)
            if rw is None:
                continue
            bt = int(round(smp.t / self.bin_s))
            j = max(0, bisect.bisect_right(seg_starts, smp.t + 1e-9) - 1)
            if smp.state == TAIL:
                j = len(seg_t) - 1
            st_bins = [(smp.state, int(round(smp.ts / self.bin_s)))]
            if j + 1 < len(seg_t) and seg_t[j + 1][1] - smp.t <= edge:
                st_bins.append((seg_t[j + 1][0], int(round((smp.t - seg_t[j + 1][1]) / self.bin_s))))
            if j > 0 and smp.t - seg_t[j][1] <= edge:
                st_bins.append((seg_t[j - 1][0], int(round((smp.t - seg_t[j - 1][1]) / self.bin_s))))
            self._acc(fam, "world", f"world_all@{inst.fold}").add_patch(bt, *rw, instance=iid)
            for st, bs in st_bins:
                self._acc(f"{fam}/{st}", "world", f"world_all@{inst.fold}").add_patch(bs, *rw, instance=iid)
            if smp.world:
                verts, frame, r = smp.verts, "world", rw
            elif inst.anchor is not None:
                verts, frame = hb.to_anchor(smp.verts, inst.anchor, inst.mirror or 1), "anchor"
                r = hb.rasterize(verts, self.cell)
            else:
                skipped += 1
                continue
            self._acc(fam, frame, f"{frame}@{inst.fold}").add_patch(bt, *r, instance=iid)
            for st, bs in st_bins:
                self._acc(f"{fam}/{st}", frame, f"{frame}@{inst.fold}").add_patch(bs, *r, instance=iid)
            first_dmg = smp.t if first_dmg is None else min(first_dmg, smp.t)
            w = per_src.get((smp.state, smp.src))
            vmin, vmax = verts.min(axis=0), verts.max(axis=0)
            if w is None:
                per_src[(smp.state, smp.src)] = [smp.ts, smp.ts, smp.t, smp.t, vmin, vmax, {smp.dmg[:5]}, frame,
                                                 {smp.name} if smp.name else set()]
            else:
                w[0], w[1] = min(w[0], smp.ts), max(w[1], smp.ts)
                w[2], w[3] = min(w[2], smp.t), max(w[3], smp.t)
                w[4], w[5] = np.minimum(w[4], vmin), np.maximum(w[5], vmax)
                w[6].add(smp.dmg[:5])
                if smp.name:
                    w[8].add(smp.name)
        if skipped:
            self.counters["anchor-frame samples without an anchor (world_all only)"] += skipped
        hole_states = frozenset(inst.state_at(t)[0] for t in inst.hole_t)
        if hole_states:
            self.counters["instances with export holes (those states left out of ttd / window statistics)"] += 1
        wins = []
        for (state, src), w in per_src.items():
            wins.append((state, src, w[7], w[2], w[3], *w[4].tolist(), *w[5].tolist()))
            info = self.src_info.get((fam, state, src))
            if info is None:
                info = self.src_info[(fam, state, src)] = {"lo": w[4], "hi": w[5], "dmg": set(), "frame": w[7],
                                                          "phases": Counter(), "names": set(), "holes": 0}
            info["lo"], info["hi"] = np.minimum(info["lo"], w[4]), np.maximum(info["hi"], w[5])
            info["dmg"] |= w[6]
            info["names"] |= w[8]
            if state not in hole_states:   # presence and windows count the instances exported without a hole there
                info["phases"][inst.phase] += 1
                self.windows[(fam, state, src)].append((w[0], w[1], w[2], w[3], inst.phase))
            else:
                info["holes"] += 1
        path = None
        if inst.anchor is not None and inst.path:
            path = np.array(inst.path, np.float64)
            path[:, 1] = (inst.mirror or 1) * (path[:, 1] - inst.anchor[0])
            path[:, 2] -= inst.anchor[1]
            pa = self.paths[fam]
            for t, x, y in path:
                pa.add(int(round(t / self.bin_s)), x, y)
        # time to damage: from each state entry (and the start) to the next enabled damage collider of the instance;
        # left out when a frame exported without colliders lies in that span (the damage may have started earlier)
        times = np.sort(np.array([s.t for s in inst.samples], np.float64))
        hole_t = np.sort(np.array(inst.hole_t, np.float64))

        def holed(t0: float, t1: float) -> bool:
            k = int(np.searchsorted(hole_t, t0 - edge))
            return k < len(hole_t) and hole_t[k] <= t1 + edge

        ttd, ttd_holed = {}, set()
        for st, _, ts in inst.states:
            i = int(np.searchsorted(times, ts - 1e-6))
            if st in ttd or st in ttd_holed:
                continue
            end = float(times[i]) if i < len(times) else (inst.t_end or ts)
            if holed(ts, end):
                ttd_holed.add(st)
            elif i < len(times):
                ttd[st] = float(times[i] - ts) if times[i] > ts else 0.0
        ttd_start = None if first_dmg is None else float(first_dmg)
        if holed(0.0, ttd_start if ttd_start is not None else (inst.t_end or 0.0)):
            ttd_holed.add("start")
            ttd_start = None
        t_tail = max([inst.t_end or 0.0, inst.t_last] + [s.t_off for s in inst.ents if s.t_off is not None])
        self.instances.append(_InstSummary(
            fam, inst.phase, inst.fight, inst.f_start, inst.dir, inst.mirror, inst.anchor, inst.anchor_t,
            inst.anchor_flip, inst.anchor_body, inst.anchor_hidden, inst.hero_start, inst.boss_hp, inst.ctx,
            list(inst.states), inst.t_end, inst.end, t_tail, inst.hits, len(inst.samples),
            sorted({s.src for s in inst.samples}), ttd, ttd_start, inst.holes, hole_states, frozenset(ttd_holed),
            path.astype(np.float32) if path is not None else None, wins))
        inst.samples = []

    # ---- validation --------------------------------------------------------------------------------------

    @staticmethod
    def contact_sets(c: Contact) -> dict[str, list[tuple]]:
        """Template sets a contact is checked against: name -> [(raw key, anchor or None (world), mirror, template
        time at the contact frame)]; an anchor-frame member of an instance whose anchor was never seen is skipped
        (anchor None, key in anchor frame: marked by mirror 0). An ambient source has its own time-invariant set."""
        if c.ambient:
            return {"ambient": [(AMBIENT, None, 1, 0.0)]}
        if c.inst is None:   # an armed hazard whose attack is unknown (it outlived the owner): its own template only
            return {f"self:{c.tk}": [(f"{SELF}/{c.tk}/self", c.arm[1], 1, c.T - c.arm[0])]}
        fam = c.inst.family
        a, m = c.inst.anchor, c.inst.mirror or 1
        anc = (a, m) if a is not None else (None, 0)
        sets = {"anchor": [(f"{fam}/anchor", *anc, c.t), (f"{fam}/world", None, 1, c.t)],
                "world_all": [(f"{fam}/world_all", None, 1, c.t)]}
        if c.state is not None:
            sets[f"state:{c.state}"] = [(f"{fam}/{c.state}/anchor", *anc, c.ts), (f"{fam}/{c.state}/world", None, 1,
                                                                                  c.ts)]
            sets[f"state_world_all:{c.state}"] = [(f"{fam}/{c.state}/world_all", None, 1, c.ts)]
        if c.arm is not None:
            sets[f"self:{c.tk}"] = [(f"{SELF}/{c.tk}/self", c.arm[1], 1, c.T - c.arm[0])]
        return sets

    @staticmethod
    def _residual(c: Contact, members: list, lookup, tol: int = 1, r_max: float = R_SEARCH_U) -> tuple[float, bool]:
        """(distance from the contact's hero boxes to the nearest occupied cell of the members' templates, each box
        at its own frame's template time +- tol bins (the box of f-1 at t_f-1, the box of f at t_f: the pairing the
        planner's query makes, so the support dilated by this residual and +-1 bin flags f-1 or f), whether any
        member template was usable; inf beyond r_max); lookup(key) -> templates to search."""
        d, usable = math.inf, False
        for key, anchor, mirror, t in members:
            if anchor is None and mirror == 0:
                continue
            for tpl in lookup(key):
                usable = True
                for box, dt in zip(c.boxes, c.box_dt):
                    b = hb.box_to_anchor(box, anchor, mirror) if anchor is not None else box
                    d = min(d, tpl.box_distance(t + dt, b, tol_bins=tol, r_max=r_max))
                    if d == 0.0:
                        return 0.0, True
        return d, usable

    def validate(self, raw: dict[str, hb.SpaceTimeTemplate]) -> dict:
        """Residual of every contact per template set (in sample, and held out against the other folds' logged
        occupancy); the dilation radius of every raw template; failures."""
        radius: dict[str, float] = {}
        per_set: dict[tuple, list] = defaultdict(list)       # (family, set) -> residuals
        heldout: dict[tuple, list] = defaultdict(list)       # (family, set) -> (residual, residual +- HELD_T_BINS,
        fails, outside, unexplained = [], [], []             #                  member keys)
        own = lambda k: [raw[k]] if k in raw else []  # noqa: E731
        for c in self.contacts:
            if c.follow:
                continue
            if c.inst is None and not c.ambient and c.arm is None:
                outside.append(c)
                continue
            if not c.exported and not c.hole:
                unexplained.append(c)
            if not c.boxes:
                continue
            fold = c.inst.fold if c.inst is not None else c.fold
            fam = c.inst.family if c.inst is not None else (AMBIENT.split("/")[0] if c.ambient else ORPHAN)
            others = lambda k: [t for fd, t in self._folds.get(k, {}).items() if fd != fold]  # noqa: E731
            for name, members in self.contact_sets(c).items():
                d, usable = self._residual(c, members, own)
                if not usable:
                    if c.ambient:
                        fails.append((c, name, math.inf))
                    continue
                c.res[name] = d
                per_set[(fam, name)].append(d)
                if d <= R_FAIL_U:
                    for key, *_ in members:
                        if key in raw:
                            radius[key] = max(radius.get(key, 0.0), d)
                else:
                    fails.append((c, name, d))
                dh, usable = self._residual(c, members, others)
                if usable and dh == math.inf and name.startswith("state:"):
                    dh = self._residual(c, members, others, r_max=R_MARGIN_SEARCH_U)[0]
                if usable:
                    c.ho[name] = dh
                    dt = self._residual(c, members, others, HELD_T_BINS)[0] if dh > 0.0 else 0.0
                    heldout[(fam, name)].append((dh, dt, tuple(m[0] for m in members if m[0] in raw)))
        fam_r: dict[str, float] = defaultdict(float)
        for key, r in radius.items():
            fam_r[key.split("/")[0]] = max(fam_r[key.split("/")[0]], r)
        glob = max(fam_r.values(), default=0.0)
        out_r = {}
        for key in raw:
            fam = key.split("/")[0]
            if key in radius:
                out_r[key] = (radius[key], "contacts")
            elif fam in fam_r:
                out_r[key] = (fam_r[fam], "family max (no contact of its own)")
            else:
                out_r[key] = (glob, "global max (no contact in the family)")
        return {"radius": out_r, "per_set": per_set, "heldout": heldout, "fails": fails, "outside": outside,
                "unexplained": unexplained}

    # ---- output ----

    def families(self) -> list[str]:
        order = list(dict.fromkeys(self.spec.attack_starts.values()))
        return order + sorted({i.family for i in self.instances} - set(order))

    def graph(self) -> dict:
        spec = self.spec
        edges = Counter((t.frm, t.to) for t in self.transitions if t.frm is not None)
        out_by: dict[str, Counter] = defaultdict(Counter)
        kills: dict[str, Counter] = defaultdict(Counter)
        for (a, b), n in edges.items():
            (kills if b in spec.death_states else out_by)[a][b] += n
        st_edges, st_global = static_edges(self.fsm_graph)
        for a, b in st_edges - set(edges):  # in the FSM, never logged: support, and a Dirichlet outcome with n = 0
            (kills if b in spec.death_states else out_by)[a][b] += 0
        by_phase: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        for t in self.transitions:
            if t.frm is not None and t.to not in spec.death_states:
                by_phase[t.frm][t.phase][t.to] += 1
        states = sorted({s for e in edges for s in e} | {t.to for t in self.transitions} |
                        {s for e in st_edges for s in e})
        from_rows = {}
        edge_rows = []
        for a in sorted(set(out_by) | set(kills)):
            n = sum(out_by[a].values())
            p, p_unseen = dirichlet(dict(out_by[a]))
            row = {"n": n, "successors": dict(out_by[a].most_common()), "worst_case": n < N_WORST,
                   "p_unseen": _r(p_unseen), "kills": dict(kills[a])}
            if len([s for s, c in out_by[a].items() if c]) >= 2:
                row["by_phase"] = {}
                for ph, cnt in sorted(by_phase[a].items()):
                    pp, pu = dirichlet({k: cnt.get(k, 0) for k in out_by[a]})
                    row["by_phase"][ph] = {"n": sum(cnt.values()), "successors": dict(cnt.most_common()),
                                           "p": {k: _r(v) for k, v in pp.items()}, "p_unseen": _r(pu),
                                           "worst_case": sum(cnt.values()) < N_WORST}
            from_rows[a] = row
            for b, c in out_by[a].most_common():
                er = {"from": a, "to": b, "n": c, "p": _r(p[b]), "p_mle": _r(c / n) if n else None,
                      "low_n": c < N_WORST}
                if c == 0:
                    er["static_only"] = True
                edge_rows.append(er)
            for b, c in kills[a].items():
                edge_rows.append({"from": a, "to": b, "n": c, "kill": True})
        starts = Counter(t.to for t in self.transitions if t.frm is None)
        return {"fsm": spec.control_fsm, "alpha": ALPHA, "n_worst": N_WORST, "states": states, "starts": dict(starts),
                "from": from_rows, "edges": edge_rows, "static_graph": self.fsm_graph is not None,
                "global_targets": sorted(st_global),
                "branching": sorted(a for a, c in out_by.items() if sum(1 for v in c.values() if v) >= 2)}

    def dwell(self) -> dict:
        by: dict[str, list[Dwell]] = defaultdict(list)
        for d in self.dwells:
            by[d.state].append(d)
        out = {}
        for st, ds in sorted(by.items()):
            dw = [d.dwell_s for d in ds]
            row = quantiles(dw)
            row["state_time_s"] = quantiles([d.state_time_s for d in ds])
            row["frames"] = quantiles([d.frames for d in ds], 1)
            row["instant"] = max(dw) < 1e-9
            row["worst_case"] = len(ds) < N_WORST
            diffs = [abs(d.dwell_s - d.state_time_s) for d in ds if d.state_time_s is not None]
            row["max_abs_dwell_minus_state_time"] = _r(max(diffs)) if diffs else None
            by_to = defaultdict(list)
            for d in ds:
                by_to[d.to].append(d.dwell_s)
            if len(by_to) > 1:
                row["by_successor"] = {k: quantiles(v) for k, v in by_to.items()}
            out[st] = row
        return out

    # ---- decision covariates ----

    def _covariates(self, trs: list[Transition], outs: list[str]) -> tuple[dict[str, list], dict]:
        """Decision-time covariate levels per transition (None = not available) and their definitions."""
        spec = self.spec
        fams = self.families()

        def thirds(xs: list) -> tuple[list[float], float, float]:
            v = [x for x in xs if x is not None]
            lo, hi = (min(v), max(v)) if v else (0.0, 1.0)
            w = (hi - lo) / 3.0 or 1.0
            return [lo + w, hi - w], lo, hi

        def third(x: float | None, edges: list[float]) -> str | None:
            return None if x is None else "W" if x < edges[0] else "E" if x >= edges[1] else "C"

        hx_e, hx_lo, hx_hi = thirds([t.hero_x for t in trs])
        ls_e, ls_lo, ls_hi = thirds([t.last_seen[0] if t.last_seen else None for t in trs])
        cov: dict[str, list] = defaultdict(list)
        for t in trs:
            vis = t.boss_x is not None and t.hero_x is not None
            cov["dist_visible"].append(dist_bin(abs(t.dx), spec.dist_bins_u) if vis else None)
            cov["side_visible"].append(("L" if t.dx < 0 else "R") if vis else None)
            if t.boss_hidden is not None and t.hero_x is not None:
                cov["dist_hidden"].append(dist_bin(abs(t.hero_x - t.boss_hidden[0]), spec.dist_bins_u))
            else:
                cov["dist_hidden"].append(None)
            cov["hero_x"].append(third(t.hero_x, hx_e))
            if spec.height_bins_u:
                cov["hero_height"].append(None if t.hero_y is None else
                                          dist_bin(t.hero_y - spec.floor_y, spec.height_bins_u))
            cov["phase"].append(t.phase)
            cov["boss_hp"].append(None if t.boss_hp is None else
                                  f"q{min(4, max(1, math.ceil(4 * t.boss_hp / spec.hp)))}")
            cov["prev"].append(t.prev or "none")
            cov["run"].append("none" if t.prev is None else t.run)
            cov["prev_dir"].append({1: "faced +x", -1: "faced -x"}.get(t.prev_mirror, "none"))
            cov["last_seen_x"].append(third(t.last_seen[0], ls_e) if t.last_seen else None)
            for fam in fams:
                k = t.since.get(fam)
                cov[f"since_{fam}"].append("never" if k is None else k)
            loc = t.local
            cov["last_choice"].append(loc[-1] if loc else "none")
            run = 0
            for o in reversed(loc):
                if o != loc[-1]:
                    break
                run += 1
            cov["choice_run"].append(run if loc else "none")
            for o in outs:
                k = next((j for j, x in enumerate(reversed(loc)) if x == o), None)
                cov[f"miss_{o}"].append("never" if k is None else k)
        caps = {}
        for name, cap in [("run", RUN_CAP), ("choice_run", RUN_CAP)] + \
                [(f"since_{fam}", SINCE_CAP) for fam in fams] + [(f"miss_{o}", SINCE_CAP) for o in outs]:
            cov[name], caps[name] = _cap_tail(cov[name], cap)
        defs = {"dist_visible": f"|hero x - boss x| bin of {list(spec.dist_bins_u)} u, boss exported and not hidden "
                                f"(V)",
                "side_visible": "hero left (L) / right (R) of the visible boss (V)",
                "dist_hidden": "|hero x - hidden boss x| bin (O: the oracle's ents[].hidden position)",
                "hero_x": f"hero world-x third over the observed range {_r(hx_lo, 2)}..{_r(hx_hi, 2)} (edges "
                          f"{[_r(e, 2) for e in hx_e]}; V)",
                "phase": "encounter phase (D: the phase mark is visible)",
                "boss_hp": f"boss HP quarter of {spec.hp} (q1 <= 25 %; O: in the final run D = {spec.hp} minus the "
                           f"damage the bot dealt)",
                "prev": "family of the previous attack of the fight",
                "run": f"consecutive attacks of that family (top level {caps['run']}+)",
                "prev_dir": "facing of the last directed attack (history)",
                "last_seen_x": f"third of the boss's last non-hidden x over {_r(ls_lo, 2)}..{_r(ls_hi, 2)} (history: "
                               f"where it was last seen, not where it is)",
                **{f"since_{fam}": f"attacks since the last {fam} (0 = the previous one; top level "
                                   f"{caps[f'since_{fam}']}+)" for fam in fams},
                "last_choice": "this state's previous outcome in the fight",
                "choice_run": f"times in a row this state chose that outcome (top level {caps['choice_run']}+)",
                **{f"miss_{o}": f"decisions of this state since it last chose {o} (0 = the previous one; top level "
                                f"{caps[f'miss_{o}']}+)" for o in outs}}
        if spec.height_bins_u:
            defs["hero_height"] = (f"hero transform height above the floor (y {spec.floor_y}) bin of "
                                   f"{list(spec.height_bins_u)} u (V)")
        defs["observability"] = ("V: seen on screen at decision time; O: oracle only; D: derived from what was seen "
                                 "before. The history covariates (prev, run, since_*, prev_dir, last_seen_x, "
                                 "last_choice, choice_run, miss_*) are D: every outcome of these decisions shows as "
                                 "the attack family and the side the boss emerges on.")
        return cov, defs

    def decisions(self, branching: list[str]) -> dict:
        rows, tests = {}, []
        for st in branching:
            trs = [t for t in self.transitions if t.frm == st and t.to not in self.spec.death_states]
            outs = sorted({t.to for t in trs})
            cov, defs = self._covariates(trs, outs)
            y_all = np.array([outs.index(t.to) for t in trs], np.int64)
            row = {"n": len(trs), "to": dict(Counter(t.to for t in trs).most_common()),
                   "worst_case": len(trs) < N_WORST,
                   "probability_only": True, "covariates": defs, "tests": {}, "untestable": {}}
            for name, levels in cov.items():
                ok = np.array([v is not None for v in levels])
                lv = sorted({v for v in levels if v is not None}, key=str)
                if ok.sum() < N_WORST or len(lv) < 2:
                    row["untestable"][name] = (f"available at {int(ok.sum())} of {len(trs)} decisions (< {N_WORST})"
                                               if ok.sum() < N_WORST else f"one level ({lv[0] if lv else '-'})")
                    continue
                x = np.array([lv.index(v) for v in levels if v is not None], np.int64)
                y = y_all[ok]
                res = independence_test(y, x, seed=zlib.crc32(f"{st}|{name}".encode()))
                tab = defaultdict(Counter)
                for v, t in zip(levels, trs):
                    if v is not None:
                        tab[str(v)][t.to] += 1
                res.update(n=int(ok.sum()), levels=[str(v) for v in lv], table={k: dict(v) for k, v in tab.items()})
                row["tests"][name] = res
                tests.append((st, name))
            rows[st] = (row, trs, cov, outs)
        p_adj = holm([rows[st][0]["tests"][name]["p"] for st, name in tests])
        for (st, name), pa in zip(tests, p_adj):
            r = rows[st][0]["tests"][name]
            r["p_holm"] = pa
            r["significant"] = pa < ALPHA_TEST
        out = {}
        for st, (row, trs, cov, outs) in rows.items():
            cand = sorted((n for n, r in row["tests"].items() if r["significant"]), key=lambda n: row["tests"][n]["p"])
            kept: list[str] = []
            ll_best = self._decision_heldout(trs, cov, [], outs).get("logloss_conditioned")
            for name in cand:
                if kept:
                    ok = np.array([all(cov[k][i] is not None for k in kept + [name]) for i in range(len(trs))])
                    strata = [tuple(cov[k][i] for k in kept) for i in range(len(trs)) if ok[i]]
                    sl = sorted(set(strata), key=str)
                    s = np.array([sl.index(v) for v in strata], np.int64)
                    xl = sorted({cov[name][i] for i in range(len(trs)) if ok[i]}, key=str)
                    x = np.array([xl.index(cov[name][i]) for i in range(len(trs)) if ok[i]], np.int64)
                    y = np.array([outs.index(trs[i].to) for i in range(len(trs)) if ok[i]], np.int64)
                    res = independence_test(y, x, s, seed=zlib.crc32(f"{st}|{name}|given".encode()))
                    row["tests"][name]["given"] = kept[:]
                    row["tests"][name]["p_given"] = res["p"]
                    if res["p"] >= ALPHA_TEST / max(1, len(cand)):
                        continue
                ll = self._decision_heldout(trs, cov, kept + [name], outs).get("logloss_conditioned")
                row["tests"][name]["heldout_logloss_with"] = ll
                if ll is not None and ll_best is not None and ll >= ll_best - HELD_LL_GAIN:
                    continue   # significant in sample, no better on held-out recordings: too many cells for the data
                ll_best = ll
                kept.append(name)
            row["conditioners"] = kept
            table = {}
            groups = defaultdict(Counter)
            for i, t in enumerate(trs):
                key = tuple(cov[k][i] for k in kept)
                if all(v is not None for v in key):
                    groups["|".join(f"{k}={v}" for k, v in zip(kept, key)) or "all"][t.to] += 1
            if kept:  # the unconditional row, for a decision whose conditioner is not observed
                groups["*"] = Counter(t.to for t in trs)
            for g, cnt in sorted(groups.items()):
                p, pu = dirichlet({o: cnt.get(o, 0) for o in outs})
                table[g] = {"n": sum(cnt.values()), "counts": dict(cnt), "p": {k: _r(v) for k, v in p.items()},
                            "p_unseen": _r(pu), "low_n": sum(cnt.values()) < N_WORST}
            row["table"] = table
            row["heldout"] = self._decision_heldout(trs, cov, kept, outs)
            out[st] = row
        return out

    @staticmethod
    def _decision_heldout(trs: list[Transition], cov: dict, kept: list[str], outs: list[str]) -> dict:
        """Mean log loss (nats per decision) of the choices of each recording fold under the tables fitted on the
        other folds, conditioned on the kept covariates vs unconditional (a cell unseen in training falls back to the
        unconditional table). The conditioners themselves were selected on all recordings."""
        folds = sorted({t.fold for t in trs})
        if len(folds) < 2:
            return {"n": 0, "note": "one fold"}
        ll_c = ll_u = 0.0
        n = 0
        for f in folds:
            groups: dict[tuple, Counter] = defaultdict(Counter)
            uc: Counter = Counter()
            for i, t in enumerate(trs):
                if t.fold != f:
                    uc[t.to] += 1
                    groups[tuple(cov[k][i] for k in kept)][t.to] += 1
            pu = dirichlet({o: uc.get(o, 0) for o in outs})[0]
            for i, t in enumerate(trs):
                if t.fold != f:
                    continue
                key = tuple(cov[k][i] for k in kept)
                g = groups.get(key) if None not in key else None
                pc = dirichlet({o: g.get(o, 0) for o in outs})[0] if g else pu
                ll_c -= math.log(pc[t.to])
                ll_u -= math.log(pu[t.to])
                n += 1
        return {"n": n, "folds": len(folds), "logloss_conditioned": _r(ll_c / n), "logloss_unconditional": _r(ll_u / n),
                "note": "nats per decision on held-out recordings; conditioners selected on all recordings"}

    # ---- attacks ----

    def attacks(self, val: dict | None = None, reach: dict | None = None) -> dict:
        spec = self.spec
        out = {}
        for fam in self.families():
            ins = [i for i in self.instances if i.family == fam]
            holed = [i for i in ins if i.holes]
            states = list(dict.fromkeys(st for i in ins for st, _, _ in i.states))
            starts = sorted({i.states[0][0] for i in ins})
            anchor = {"frame": "boss transform position (STATE ents[].pos) at its first non-hidden export in the "
                               "instance; WorldState Entity.pos = transform + body_offset (by_dir_flip: per "
                               "direction and facing)",
                      "probability_only": ["t_s", "by_dir.*.x", "by_dir.*.y", "by_dir.*.x_minus_hero_x"],
                      "t_s": quantiles([i.anchor_t for i in ins]), "missing": sum(i.anchor is None for i in ins)}
            by_dir = defaultdict(list)
            for i in ins:
                by_dir[i.dir or "-"].append(i)
            anchor["by_dir"] = {}
            for d, v in sorted(by_dir.items()):
                ax = [i.anchor[0] for i in v if i.anchor]
                ay = [i.anchor[1] for i in v if i.anchor]
                anchor["by_dir"][d] = {
                    "n": len(v), "mirror": dict(Counter(str(i.mirror) for i in v)),
                    "support": {"x": [_r(min(ax), 3), _r(max(ax), 3)], "y": [_r(min(ay), 3), _r(max(ay), 3)]}
                    if ax else None,
                    "x": quantiles(ax), "y": quantiles(ay), "flipX": dict(Counter(str(i.anchor_flip) for i in v)),
                    "x_minus_hero_x": quantiles([i.anchor[0] - i.hero_start[0] for i in v
                                                 if i.anchor and i.hero_start])}
            anchor["body_offset"] = self._body_offsets(ins)
            hid = [i for i in ins if i.anchor_hidden and i.anchor]
            anchor["hidden"] = {"n": len(hid), "desc": "first hidden export (ents[].hidden) before the anchor",
                                "t_s": quantiles([i.anchor_hidden[2] for i in hid]),
                                "anchor_minus_hidden_x": quantiles([i.anchor[0] - i.anchor_hidden[0] for i in hid]),
                                "anchor_minus_hidden_y": quantiles([i.anchor[1] - i.anchor_hidden[1] for i in hid])}
            hits = Counter()
            hits_state = Counter()
            for i in ins:
                for _, st, src, _, _ in i.hits:
                    hits[src] += 1
                    hits_state[st] += 1
            ttd = {st: quantiles([i.ttd[st] for i in ins if st in i.ttd]) for st in states}
            ttd_out = Counter(st for i in ins for st in i.ttd_holed)
            row = {
                "start_states": starts, "states": states, "n": len(ins),
                "n_by_phase": dict(Counter(i.phase for i in ins)), "n_by_dir": dict(Counter(i.dir or "-" for i in ins)),
                "ends": dict(Counter(i.end for i in ins)), "mirrored": fam in spec.directed,
                "export_holes": {"instances": len(holed), "frames": sum(i.holes for i in ins),
                                 "states": dict(Counter(st for i in holed for st in i.hole_states)),
                                 "ttd_left_out": dict(ttd_out),
                                 "note": "frames a damage entity of the instance was exported without colliders: the "
                                         "hitbox windows of those states and every ttd span containing such a frame "
                                         "are left out of the statistics; the templates keep the instance"},
                "boss_hp_at_start": quantiles([i.boss_hp for i in ins], 1),
                "duration_s": quantiles([i.t_end for i in ins if i.end == "rest"]),
                "tail_s": quantiles([i.t_tail for i in ins]),
                "state_entry_s": {st: quantiles([ts for i in ins for s2, _, ts in i.states if s2 == st])
                                  for st in states},
                "ttd_s": {"start": quantiles([i.ttd_start for i in ins]), **ttd},
                "anchor": anchor,
                "select": {"probability_only": True, "counts_by_phase": dict(Counter(i.phase for i in ins)),
                           "decided_at": "decisions[<state>] (covariates tested; no distance bins assumed)"},
                "hits_taken": {"n": sum(len(i.hits) for i in ins), "by_source": dict(hits.most_common()),
                               "by_state": dict(hits_state.most_common())},
                "coverage": {"n": len(ins), "target": TARGET_INSTANCES, "ok": len(ins) >= TARGET_INSTANCES},
                "hitboxes": self._hitboxes(fam),
            }
            if val is not None:
                row["residual_u"] = self._residual_rows(fam, val)
            if reach is not None:
                row["reach_union"] = {k.split("/")[-1]: v for k, v in reach.items()
                                      if k.count("/") == 1 and k.split("/")[0] == fam}
            out[fam] = row
        return out

    @staticmethod
    def _body_offsets(ins: list[_InstSummary]) -> dict:
        """Body box centre and render_aabb centre minus the anchor on the anchor frame, in the anchor frame (x' =
        mirror * dx), per direction and per direction and facing (flipX at the anchor, observable): anchor =
        Entity.pos (body collider centre, DESIGN §4.1) - offset. A conservative placement takes the support (min /
        max) of its (direction, flipX) key, not the quantiles."""
        out: dict = {"frame": "anchor: dx' = mirror * (centre x - anchor x), dy = centre y - anchor y", "by_dir": {},
                     "by_dir_flip": {}}
        by, by_flip = defaultdict(list), defaultdict(list)
        for i in ins:
            if i.anchor_body:
                by[i.dir or "-"].append(i)
                by_flip[f"{i.dir or '-'} / flipX={i.anchor_flip}"].append(i)
        for grp, rows in (("by_dir", by), ("by_dir_flip", by_flip)):
            for d, v in sorted(rows.items()):
                row = {"n": len(v)}
                for j, name in ((0, "box_centre"), (1, "render_centre")):
                    o = [((i.mirror or 1) * i.anchor_body[j][0], i.anchor_body[j][1]) for i in v
                         if i.anchor_body[j] is not None]
                    if o:
                        xs, ys = [a for a, _ in o], [b for _, b in o]
                        row[name] = {"support": {"dx": [_r(min(xs), 3), _r(max(xs), 3)],
                                                 "dy": [_r(min(ys), 3), _r(max(ys), 3)]},
                                     "dx": quantiles(xs, 3), "dy": quantiles(ys, 3)}
                out[grp][d] = row
        return out

    def _residual_rows(self, fam: str, val: dict) -> dict:
        sets = {}
        for (f, name), ds in sorted(val["per_set"].items()):
            if f != fam:
                continue
            v = np.array(ds, np.float64)
            fin = v[np.isfinite(v)]
            sets[name] = {"n": int(v.size), "covered_at_0": int((v == 0).sum()),
                          "p50": _r(float(np.quantile(fin, 0.5)) if fin.size else None),
                          "p99": _r(float(np.quantile(fin, 0.99)) if fin.size else None),
                          "max": _r(float(fin.max()) if fin.size else None),
                          "beyond_r_fail": int((v > R_FAIL_U).sum())}
        by_src = defaultdict(list)
        for c in self.contacts:
            if c.inst is not None and c.inst.family == fam and "anchor" in c.res:
                by_src[c.src].append(c.res["anchor"])
        radius = {k: {"u": _r(r, 4), "from": why} for k, (r, why) in sorted(val["radius"].items())
                  if k.split("/")[0] == fam}
        held = {name: _held_row(items, val["radius"]) for (f, name), items in sorted(val["heldout"].items())
                if f == fam}
        return {"desc": "distance (u) from the hero hurtbox to the family's logged occupancy, per template set: the "
                        "smaller of the box of f-1 at t_f-1 +- 1 bin and the box of f at t_f +- 1 bin (the planner's "
                        "pairing); support templates are dilated by the set's max (radius) and +-1 bin",
                "sets": sets,
                "holdout": {"desc": f"the same distance to the occupancy logged in the other recordings only "
                                    f"({N_FOLDS} folds by recording, each built from about half the instances): "
                                    f"coverage of unseen instances. within_radius: inside the support of the full "
                                    f"build; within_radius_t{HELD_T_BINS}: also with +-{HELD_T_BINS} bins of timing "
                                    f"slack", **held},
                "by_source_anchor": {s: {"n": len(d), "p99": _r(float(np.quantile(d, 0.99))), "max": _r(max(d))}
                                     for s, d in sorted(by_src.items()) if np.isfinite(d).all()},
                "radius": radius}

    def _hitboxes(self, fam: str) -> list[dict]:
        """Per (state, source): windows (+-1 frame of export lag), extent, damage; presence = share of the instances
        entering the state (per phase) without an export hole there in which the source was enabled there; n =
        instances in the window statistics, n_export_holes = instances of the family with an export hole in that
        state (left out of presence and windows for every source, whether or not the source showed)."""
        rows = []
        lag = self.bin_s
        ins = [i for i in self.instances if i.family == fam]
        entered = Counter((st, i.phase) for i in ins for st in ({s for s, _, _ in i.states} | {TAIL}) - i.hole_states)
        holed = Counter(st for i in ins for st in i.hole_states)
        for (f, state, src), info in sorted(self.src_info.items()):
            if f != fam:
                continue
            seen = sum(info["phases"].values())
            n_in = sum(n for (st, _), n in entered.items() if st == state)
            pres = {ph: _r(info["phases"].get(ph, 0) / n, 3) for (st, ph), n in sorted(entered.items())
                    if st == state and n}
            ws = self.windows.get((f, state, src)) or []
            w = np.array([x[:4] for x in ws], np.float64).reshape(-1, 4)
            dealt = sorted({d[0] for d in info["dmg"] if d[0] is not None})
            eff = sorted({d[1] for d in info["dmg"] if d[1] is not None})
            haz = sorted({hazard_name(int(d[2])) for d in info["dmg"] if d[2] is not None})
            flags = sorted({n for d in info["dmg"] if d[3] for n in bits(int(d[3]), DAMAGE_FLAGS)})
            parry = sorted({n for d in info["dmg"] if d[4] for n in bits(int(d[4]), PARRY_BITS)})
            lo, hi = info["lo"], info["hi"]
            row = {"state": state, "source": src, "names": sorted(info["names"]), "frame": info["frame"],
                   "n": len(ws), "n_export_holes": holed.get(state, 0), "phases": dict(info["phases"]),
                   "presence": _r(seen / n_in, 3) if n_in else None, "presence_by_phase": pres}
            if len(w):
                row.update({"t0_state": _r(float(w[:, 0].min()) - lag), "t1_state": _r(float(w[:, 1].max()) + lag),
                            "t0": _r(float(w[:, 2].min()) - lag), "t1": _r(float(w[:, 3].max()) + lag),
                            "t_on_state": quantiles(w[:, 0]), "t_off_state": quantiles(w[:, 1]),
                            "t_on": quantiles(w[:, 2]), "t_off": quantiles(w[:, 3])})
            row.update({"x": [_r(float(lo[0]), 3), _r(float(hi[0]), 3)],
                        "y": [_r(float(lo[1]), 3), _r(float(hi[1]), 3)],
                        "dmg": dealt, "eff": eff, "type": haz, "flags": flags, "parry": parry,
                        "parryable": "clash" in parry or "force" in parry})
            rows.append(row)
        return rows

    def entities(self, val: dict | None = None) -> dict:
        out = {}
        seg_by = defaultdict(list)
        for seg, fam in self.segs:
            seg_by[seg.type_key].append((seg, fam))
        for tk, info in sorted(self.ent.items()):
            by_state = {}
            for st, c in sorted(info["by_state"].items(), key=lambda kv: str(kv[0])):
                frames = c["frames"]
                by_state[str(st)] = {"frames": frames, "no_colliders": c.get("no_colliders", 0),
                                     **{k: _r(v / frames, 3) for k, v in sorted(c.items())
                                        if k.startswith("enabled") and frames}}
            segs = seg_by.get(tk, [])
            out[tk] = {
                "category": info["category"], "src": bits(info["src"], SRC_BITS), "layers": sorted(
                    x for x in info["layers"] if x is not None),
                "colliders": dict(info["colliders"]), "names": dict(info["names"]), "radius": sorted(info["radius"]),
                "boss": info["boss"], "hidden_frames": info["hidden"], "no_collider_frames": info["no_colliders"],
                "cooldown_frames": info["cooldown"], "by_state": by_state, "armed": len(segs),
                "armed_by_family": dict(Counter(str(fam) for _, fam in segs)),
                "armed_at_boss_state": dict(Counter(str(s.trigger) for s, _ in segs).most_common()),
                "lifetime_s": quantiles([s.t_off - s.t_on for s, _ in segs if s.t_off is not None]),
                "end": dict(Counter(str(s.end) for s, _ in segs)),
                "world_frame": tk.startswith(self.spec.world_fixed)}
            if self.arm_at.get(tk):
                out[tk]["arm_pos"] = self._arm_pos(tk)
            if val is not None and f"{SELF}/{tk}/self" in val["radius"]:
                out[tk]["self_template"] = self._self_row(tk, val)
        return out

    def _arm_pos(self, tk: str) -> dict:
        """Where and when the entity armed (transform position; s since the entry of the owner's Control state then):
        the support (min / max) a self template is swept over before the entity is seen arming (dilated by half the
        x / y ranges about their centre, the time range added as time bins), per owner family and boss state;
        quantiles are probability only."""
        rows = self.arm_at[tk]
        by = defaultdict(list)
        for x, y, fam, trig, ts in rows:
            by[f"{fam} / {trig}"].append((x, y, ts))

        def sup(v):
            xs, ys, ts = [a[0] for a in v], [a[1] for a in v], [a[2] for a in v if a[2] is not None]
            out = {"n": len(v), "x": [_r(min(xs), 3), _r(max(xs), 3)], "y": [_r(min(ys), 3), _r(max(ys), 3)]}
            if ts:
                out["t_since_state_entry_s"] = [_r(min(ts)), _r(max(ts))]
            return out

        return {"support": sup([r[:2] + (None,) for r in rows]),
                "by_owner_state": {k: sup(v) for k, v in sorted(by.items())},
                "x": quantiles([r[0] for r in rows], 3), "y": quantiles([r[1] for r in rows], 3),
                "probability_only": ["x", "y"]}

    def _self_row(self, tk: str, val: dict) -> dict:
        key = f"{SELF}/{tk}/self"
        r, why = val["radius"][key]
        name = f"self:{tk}"
        ds = [d for (fam, n), v in val["per_set"].items() if n == name for d in v]
        held = [h for (fam, n), v in val["heldout"].items() if n == name for h in v]
        v = np.array(ds, np.float64)
        fin = v[np.isfinite(v)]
        return {"npz": hb.SUPPORT + key, "frame": "anchor = the arming position (STATE ents[].pos), mirror 1; t = s "
                                                  "since arming",
                "radius_u": _r(r), "radius_from": why, "contacts": int(v.size),
                "p99": _r(float(np.quantile(fin, 0.99))) if fin.size else None,
                "max": _r(float(fin.max())) if fin.size else None,
                "holdout": _held_row(held, val["radius"]) if held else {"n": 0}}

    def phases(self) -> dict:
        out = {k: {"desc": v} for k, v in self.spec.phases.items()}
        for st, ph in self.spec.phase_marks.items():
            out.setdefault(ph, {})["entered_at"] = st
            out[ph]["boss_hp_at_entry"] = quantiles([t.boss_hp for t in self.transitions if t.to == st], 1)
        return out

    def _contact_row(self, c: Contact, d: float | None = None) -> dict:
        return {"fight": c.fight, "f": c.f, "kind": c.kind, "source": c.src,
                "family": c.inst.family if c.inst else None,
                "state": c.state, "t": _r(c.t), "exported": c.exported, "export_hole": c.hole,
                "residual_u": None if d is None else (_r(d) if math.isfinite(d) else "inf")}

    def validation_summary(self, val: dict) -> dict:
        cs = self.contacts
        dmg = [c for c in cs if c.kind == "damage"]
        unexpl = val["unexplained"]
        fails = val["fails"]
        hole_c = [c for c in cs if not c.exported and c.hole]
        gaps = [c for c in cs if c.named_gap]
        follow = [c for c in cs if c.follow]
        amb = [c for c in cs if c.ambient]
        ok = not fails and not unexpl and not val["outside"]
        ho: dict[str, list] = defaultdict(list)
        for (fam, name), items in val["heldout"].items():
            ho[name.split(":")[0]].extend(items)
        held_rows = {k: _held_row(v, val["radius"]) for k, v in sorted(ho.items())}
        held_bad = {k: r for k, r in held_rows.items() if k in ("anchor", "self")
                    and (not r["n"] or r["beyond_r_fail"] > HELDOUT_MISS_MAX * r["n"])}
        conservative = ok and "anchor" in held_rows and not held_bad
        return {
            "support_conservative": conservative,
            "support_note": ("in sample every contact is covered and held out (other fold) at most "
                             f"{HELDOUT_MISS_MAX:.1%} of the anchor / self contacts lie beyond {R_FAIL_U} u"
                             if conservative else
                             "NOT shown to cover unseen instances: " + "; ".join(
                                 ([] if ok else ["in-sample validation failed"]) +
                                 ([] if "anchor" in held_rows else ["no held-out anchor contacts"]) +
                                 [f"held out {k}: {r['beyond_r_fail']} of {r['n']} contacts beyond {R_FAIL_U} u"
                                  for k, r in held_bad.items()]) +
                             " - inflate it or keep it out of the planner until more data closes this"),
            "heldout": {"desc": f"{N_FOLDS} folds (by recording; by fight for a gauntlet): contacts against the "
                                f"other fold's logged occupancy; "
                                f"within_radius = inside the support radius of the full build; "
                                f"within_radius_t{HELD_T_BINS} = also with +-{HELD_T_BINS} bins of timing slack; "
                                f"state / state_world_all pool the per-state sets",
                        **held_rows},
            "ok": ok, "r_fail_u": R_FAIL_U, "lag_frames": LAG_F,
            "multi_hit_follow_ups": {"desc": f"hits of a connected multi-hit (multi_wounder) whose collider was "
                                             f"exported within {MW_FOLLOW_F} frames before, not then: not checked "
                                             f"against the support", "n": len(follow),
                                     "by_source": dict(Counter(c.src for c in follow))},
            "contacts": len(cs), "damage": len(dmg), "blocked_frames": len(cs) - len(dmg),
            "no_hero_box": sum(1 for c in cs if not c.boxes),
            "no_exported_collider_explained_by_export_hole": {"n": len(hole_c), "damage": sum(
                c.kind == "damage" for c in hole_c), "by_source": dict(Counter(c.src for c in hole_c))},
            "unexplained": {"n": len(unexpl), "first": [self._contact_row(c) for c in unexpl[:20]]},
            "partial_export_holes": {
                "desc": "contacts whose source entity was exported with named damage colliders but not the one the "
                        "damage event named (oracle ents[].colliders[].name): unexplained unless the entity was also "
                        "exported without colliders then", "n": len(gaps),
                "explained_by_export_hole": sum(c.hole for c in gaps),
                "by_source": dict(Counter(c.src for c in gaps)),
                "first": [self._contact_row(c) for c in gaps[:20]]},
            "ambient": {"desc": f"contacts with an ambient hazard (armed when the scan started), checked against the "
                                f"static {AMBIENT} support only", "n": len(amb),
                        "by_source": dict(Counter(c.src for c in amb)),
                        "radius_u": _r(val["radius"][AMBIENT][0]) if AMBIENT in val["radius"] else None},
            "uncovered": {"n": len(fails), "contacts": len({id(c) for c, _, _ in fails}),
                          "desc": "n counts (contact, template set) pairs; contacts the distinct contacts",
                          "first": [{**self._contact_row(c, d), "set": name} for c, name, d in fails[:20]]},
            "outside_attacks": {"n": len(val["outside"]), "first": [self._contact_row(c) for c in val["outside"][:20]]},
            "uncovered_by_set": dict(Counter(name.split(":")[0] for _, name, _ in fails)),
        }

    def coverage(self, attacks: dict, graph: dict, val: dict | None) -> dict:
        fams = {f: {"n": a["n"], "by_phase": a["n_by_phase"], "target": TARGET_INSTANCES,
                    "missing": max(0, TARGET_INSTANCES - a["n"])} for f, a in attacks.items()}
        holes = defaultdict(dict)
        for (tk, st), n in sorted(self.holes.items()):
            holes[tk][st] = n
        return {"logged_instances_min": min((a["n"] for a in attacks.values()), default=0),
                "target": TARGET_INSTANCES, "families": fams,
                "fsm_edges_extracted": self.fsm_graph is not None,
                "logged_edges": sum(1 for e in graph["edges"] if not e.get("static_only")),
                "edges_n_lt_30": [f"{e['from']} -> {e['to']} ({e['n']})" for e in graph["edges"]
                                  if e["n"] < N_WORST and not e.get("kill")],
                "states_n_lt_30": [f"{s} ({r['n']})" for s, r in graph["from"].items() if r["worst_case"]],
                "hero_x_at_transitions": quantiles([t.hero_x for t in self.transitions], 2),
                "hits_outside_attacks": [{"fight": h[0], "f": h[1], "source": h[2], "control": h[3]}
                                         for h in self.loose_hits[:20]],
                "export_holes": {"desc": "frames a damage entity was exported (not hidden) with colliders == [], by "
                                         "type_key and Control / own FSM state", "frames": dict(holes),
                                 "instances": sum(1 for i in self.instances if i.holes)},
                "partial_presence": {
                    "desc": "sources enabled in 90-99.9 % of the instances entering a state (per phase): candidates "
                            "for export gaps the empty-collider check does not see (or a source that left the view)",
                    "rows": [f"{fam} / {h['state']} / {h['source']} / {ph}: {p}" for fam, a in attacks.items()
                             for h in a["hitboxes"] for ph, p in h["presence_by_phase"].items() if 0.9 <= p < 1.0]},
                "hero_box_u": self._hero_box_row(),
                "validation": self.validation_summary(val) if val is not None else None,
                "ambient_frames": dict(self.ambient_frames),
                "fights": len(self.fights), "frames": sum(f["frames"] for f in self.fights),
                "game_s": _r(sum(f["game_s"] or 0 for f in self.fights), 1),
                "counters": dict(self.counters.most_common())}

    def _hero_box_row(self) -> dict:
        """The logged hero hurtbox (STATE hero.box) against the half-extents the planner templates assume."""
        w0, w1, h0, h1, n = self.hero_box
        if not n:
            return {"n": 0}
        hx, hy = hb.HERO_HALF_U
        return {"n": int(n), "w": [_r(w0), _r(w1)], "h": [_r(h0), _r(h1)], "half_u_assumed": [hx, hy],
                "ok": bool(w1 <= 2 * hx + 1e-3 and h1 <= 2 * hy + 1e-3)}

    def raw_templates(self) -> dict[str, hb.SpaceTimeTemplate]:
        """Finished raw templates; the family-level ones are the union of their per-fold parts (kept in _folds)."""
        out: dict[str, hb.SpaceTimeTemplate] = {}
        folds: dict[str, dict[int, hb.SpaceTimeTemplate]] = defaultdict(dict)
        for k, a in sorted(self.acc.items()):
            t = a.finish()
            if t is None:
                continue
            if "@" in k:
                base, fold = k.rsplit("@", 1)
                t.key = base
                folds[base][int(fold)] = t
            else:
                out[k] = t
        for base, fs in folds.items():
            if len(fs) == 1:
                out[base] = next(iter(fs.values()))
            else:
                out[base] = hb.union(fs.values(), base)
                out[base].n_instances = sum(t.n_instances for t in fs.values())
        self._folds = dict(folds)
        return dict(sorted(out.items()))

    def templates(self) -> dict[str, hb.SpaceTimeTemplate]:
        """Raw (logged) templates; build() also returns the support templates."""
        return self.raw_templates()

    def build(self) -> Built:
        """Tables, raw and support templates, extra arrays (cached until the next scan)."""
        if self._built is not None:
            return self._built
        spec = self.spec
        raw = self.raw_templates()
        val = self.validate(raw)
        self._val = val
        support = {}
        for k, t in raw.items():
            r = val["radius"].get(k, (0.0, ""))[0]
            support[hb.SUPPORT + k] = t.dilated(r_disk=r, t_bins=1, key=hb.SUPPORT + k)
        reach = reach_summary({k[len(hb.SUPPORT):]: v for k, v in support.items()})
        g = self.graph()
        atk = self.attacks(val, reach)
        support_tr = {a: sorted(set(r["successors"]) | set(r["kills"])) for a, r in g["from"].items()}
        obs = {}
        for fam, a in atk.items():
            for st in a["states"]:
                parry = any(h["parryable"] for h in a["hitboxes"] if h["state"] == st)
                obs.setdefault(st, {"fsm_states": [st], "families": [], "ttd_s": a["ttd_s"].get(st),
                                    "parryable": parry})["families"].append(fam)
        tables = {
            "schema": SCHEMA, "enemy": spec.enemy, "build": BUILD, "scene": spec.scene, "boss_type": spec.boss_type,
            "hp": spec.hp, "fsms": sorted({spec.control_fsm}), "phases": self.phases(),
            "sources": self.fights, "graph": g, "dwell_s": self.dwell(), "decisions": self.decisions(g["branching"]),
            "observable_phases": obs, "attacks": atk, "support_transitions": support_tr, "entities": self.entities(val),
            "coverage": absent_marks(spec, {"coverage": self.coverage(atk, g, val)})["coverage"],
            **({"structurally_absent": dict(spec.absent)} if spec.absent else {}),
            "templates": {
                "cell_u": self.cell, "bin_s": self.bin_s, "file": f"{spec.enemy}_hitboxes.npz",
                "keys": "<family>/<frame> (t from the attack start), <family>/<state>/<frame> (t from the state's "
                        "entry; _tail = after the attack ended, t from its end); frame anchor | world (arena-fixed "
                        "hazards) | world_all (every collider of the family in world coordinates: the support before "
                        "the anchor or the side is known); ent/<type_key>/self: one hazard entity relative to where "
                        "it armed (anchor = its position then, mirror 1, t from arming; entities.<tk>.self_template, "
                        "arm_pos); _ambient/world: hazards armed when a scan started (static: one bin, in support at every t)",
                "support": "support/<key>: the logged occupancy dilated by its validated residual (attacks.<A>."
                           "residual_u.radius[<key>], entities.<tk>.self_template.radius_u) and +-1 time bin; these "
                           "are the support (DESIGN §3.5.3). The npz also keeps the logged family templates "
                           "(<family>/<frame>, for the viewer). For the planner: hitbox_tables.planner_templates (+ "
                           "hero hurtbox half-extents and margin) and SupportQuery",
                "hero_half_u": list(hb.HERO_HALF_U),
                "frames": {"anchor": "x' = mirror * (x - anchor x), y' = y - anchor y (anchor = boss transform)",
                           "world": "world coordinates"},
                "instance_columns": list(INSTANCE_COLUMNS), "window_columns": list(WINDOW_COLUMNS),
                "instance_codes": {"phase": list(spec.phases), "dir": "dir_states value, 0 = none", "end": END_CODES},
                "arrays": "<family>/instances (n, instance_columns), state_t (n, states: s from the start, nan = not "
                          "entered), state_f (entry frames, -1), state_names, fights, windows (per instance, state "
                          "and source: window_columns, template frame), window_states, window_sources, boss_path (t, "
                          "n, x_min, x_max, y_min, y_max, x_mean, y_mean; anchor frame), paths (instance, t, x', y'; "
                          "families with a variable anchor, or all with --paths). Frame-by-frame colliders: the "
                          "recordings (sources[].path, frames f_start..)"},
            "spec": {"attack_starts": spec.attack_starts, "decision_states": list(spec.decision_states),
                     "dir_states": spec.dir_states, "directed": list(spec.directed), "phase_marks": spec.phase_marks,
                     "world_fixed": list(spec.world_fixed), "rest_states": list(spec.rest_states),
                     "dist_bins_u": list(spec.dist_bins_u), "tail_max_s": spec.tail_max_s},
        }
        self._built = Built(tables, raw, support, self.extra_arrays(atk))
        return self._built

    def tables(self) -> dict:
        return self.build().tables

    def fold_support(self, fold: int) -> dict[str, hb.SpaceTimeTemplate]:
        """Support templates from one held-out fold's instances only, as build() makes them from all: that fold's
        logged occupancy dilated by the largest residual of that fold's own contacts against it (family max, then
        global max for keys without a contact of their own) and +-1 bin. The other fold's contacts are unseen by
        them (ssbot.tools.support_recall --encounter: held-out recall)."""
        self.build()
        folds = self._folds
        radius: dict[str, float] = {}
        for c in self.contacts:
            if c.follow or not c.boxes or (c.inst is None and not c.ambient and c.arm is None):
                continue
            if (c.inst.fold if c.inst is not None else c.fold) != fold:
                continue
            own = lambda k: [folds[k][fold]] if fold in folds.get(k, {}) else []  # noqa: E731
            for members in self.contact_sets(c).values():
                d, usable = self._residual(c, members, own)
                if usable and d <= R_FAIL_U:
                    for key, *_ in members:
                        if fold in folds.get(key, {}):
                            radius[key] = max(radius.get(key, 0.0), d)
        fam_r: dict[str, float] = defaultdict(float)
        for key, r in radius.items():
            fam_r[key.split("/")[0]] = max(fam_r[key.split("/")[0]], r)
        glob = max(fam_r.values(), default=0.0)
        out = {}
        for key, fs in sorted(folds.items()):
            t = fs.get(fold)
            if t is None:
                continue
            r = radius.get(key, fam_r.get(key.split("/")[0], glob))
            out[hb.SUPPORT + key] = t.dilated(r_disk=r, t_bins=1, key=hb.SUPPORT + key)
        return out

    def contact_rows(self, residuals: bool = True) -> list[dict]:
        """Every contact with its attribution and residuals (in sample, held out) for the support recall of a
        multi-enemy build (fight = "<run>/i<n>/ep<k>/<type>#<iid>": the subject the gauntlet builder gave it to).
        residuals=False: the scan's attribution only (no build; res / ho empty), for fights a recall tests against
        tables built from other fights (behaviour_build --contacts-only)."""
        if residuals:
            self.build()
        rows = []
        for c in self.contacts:
            rows.append({
                "fight": c.fight, "f": c.f, "kind": c.kind, "src": c.src, "tk": c.tk,
                "family": c.inst.family if c.inst is not None else None, "state": c.state,
                "ts": _r(c.ts, 4), "t": _r(c.t, 4), "fold": c.inst.fold if c.inst is not None else c.fold,
                "f_start": c.inst.f_start if c.inst is not None else None, "follow": c.follow,
                "exported": c.exported, "hole": c.hole, "ambient": c.ambient, "boxes": [list(map(float, b)) for b in c.boxes],
                "res": {k: (None if v == math.inf else _r(v, 4)) for k, v in c.res.items()},
                "ho": {k: (None if v == math.inf else _r(v, 4)) for k, v in c.ho.items()}})
        return rows

    def extra_arrays(self, atk: dict | None = None) -> dict[str, np.ndarray]:
        out = {}
        for fam, pa in self.paths.items():
            out[f"{fam}/boss_path"] = pa.array(self.bin_s)
        for fam in self.families():
            ins = [i for i in self.instances if i.family == fam]
            if not ins:
                continue
            states = list(dict.fromkeys(st for i in ins for st, _, _ in i.states))
            phases = list(self.spec.phases)
            rows, st_t = [], np.full((len(ins), len(states)), np.nan)
            st_f = np.full((len(ins), len(states)), -1, np.int64)
            w_states = list(dict.fromkeys(w[0] for i in ins for w in i.windows))
            w_srcs = list(dict.fromkeys(w[1] for i in ins for w in i.windows))
            wins = []
            for k, i in enumerate(ins):
                ax, ay = i.anchor if i.anchor else (np.nan, np.nan)
                hx, hy = i.hero_start if i.hero_start else (np.nan, np.nan)
                rows.append([i.f_start, phases.index(i.phase) if i.phase in phases else -1, i.mirror or 0,
                             self.spec.dir_states.get(i.dir, 0), ax, ay,
                             np.nan if i.anchor_t is None else i.anchor_t, hx, hy,
                             np.nan if i.boss_hp is None else i.boss_hp, np.nan if i.t_end is None else i.t_end,
                             i.t_tail, len(i.hits), END_CODES.get(i.end, -1), i.holes])
                for st, fr, ts in i.states:
                    j = states.index(st)
                    if np.isnan(st_t[k, j]):
                        st_t[k, j], st_f[k, j] = ts, fr
                for st, src, frame, t_on, t_off, x0, y0, x1, y1 in i.windows:
                    wins.append([k, w_states.index(st), w_srcs.index(src), hb.FRAMES.index(frame), t_on, t_off,
                                 x0, y0, x1, y1])
            out[f"{fam}/instances"] = np.array(rows, np.float64)
            out[f"{fam}/state_t"] = st_t
            out[f"{fam}/state_f"] = st_f
            out[f"{fam}/windows"] = np.array(wins, np.float32).reshape(-1, len(WINDOW_COLUMNS))
            out[f"{fam}/window_states"] = np.array(w_states)
            out[f"{fam}/window_sources"] = np.array(w_srcs)
            variable = False
            if atk is not None:
                for d in atk[fam]["anchor"]["by_dir"].values():
                    sup = d.get("support")
                    variable |= bool(sup) and sup["x"][1] - sup["x"][0] > 1.0
            if self.keep_paths or variable:
                out[f"{fam}/paths"] = np.concatenate(
                    [np.column_stack([np.full(len(i.path), k, np.float32), i.path]) for k, i in enumerate(ins)
                     if i.path is not None] or [np.zeros((0, 4), np.float32)])
            out[f"{fam}/state_names"] = np.array(states)
            out[f"{fam}/fights"] = np.array([i.fight for i in ins])
        return out

    def write(self, out_dir: Path, allow_failed: bool = False, code: dict | None = None) -> tuple[Path, Path, dict]:
        """Write <enemy>.json and <enemy>_hitboxes.npz. Raises ValidationFailed (and writes nothing) when a contact
        is uncovered or unexplained, unless allow_failed (then coverage.validation.ok stays false in the file).
        code: the git revision and dirty flag taken when the scan started (ssbot.record.recorder.git_info); taken
        now when not given."""
        out_dir = Path(out_dir)
        b = self.build()
        tables = b.tables
        v = tables["coverage"]["validation"]
        if not v["ok"] and not allow_failed:
            raise ValidationFailed(f"{v['uncovered']['n']} uncovered, {v['unexplained']['n']} unexplained, "
                                   f"{v['outside_attacks']['n']} outside-attack contacts: "
                                   f"{(v['uncovered']['first'] + v['unexplained']['first'])[:3]}")
        from ssbot.record.recorder import find_repo_root, git_info
        if code is None:  # before the outputs are written: their own change is not "dirty" code
            code = git_info(find_repo_root())
        out_dir.mkdir(parents=True, exist_ok=True)
        raw = {k: v for k, v in b.raw.items() if k.count("/") == 1}  # logged family templates (viewer); the rest
        npz = hb.save_templates(out_dir / f"{self.spec.enemy}_hitboxes.npz", {**raw, **b.support}, b.extra)
        tables["build_info"] = provenance(self.fights, npz, code)
        js = out_dir / f"{self.spec.enemy}.json"
        js.write_text(json.dumps(tables, indent=1, default=_json_default) + "\n", encoding="utf-8")
        return js, npz, tables


INSTANCE_COLUMNS = ("f_start", "phase", "mirror", "dir", "anchor_x", "anchor_y", "anchor_t", "hero_x", "hero_y",
                    "boss_hp", "dur_s", "tail_s", "hits", "end", "export_hole_frames")
WINDOW_COLUMNS = ("instance", "state", "source", "frame", "t_on", "t_off", "x0", "y0", "x1", "y1")
END_CODES = {"rest": 0, "death": 1, "chain": 2, "fight_end": 3}


def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with Path(path).open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def provenance(fights: list[dict], npz: Path | None, code: dict | None = None) -> dict:
    """Code revision, dirty flag (tracked files; taken before the outputs are written when given), inputs (status and
    hashes of each recording's meta.json and index / raw state), and the npz sha256 (DESIGN §3.1.9: knowledge files
    are versioned, with hashes)."""
    from ssbot.record.recorder import find_repo_root, git_info
    if code is None:
        code = git_info(find_repo_root())
    inputs: dict[str, dict] = {}
    for f in fights:
        p = Path(f.get("path") or ".")
        if f.get("kind") not in ("rec", "human"):
            continue
        r = inputs.get(str(p))
        if r is None:
            r = inputs[str(p)] = {"kind": f["kind"], "status": recording_status(p) if f["kind"] == "rec" else None,
                                  "meta_sha256": _sha256(p / "meta.json"), "fights": 0, "frames": [f["f0"], f["f1"]],
                                  "fold": f.get("fold")}
            if f["kind"] == "rec":
                r["state_index_sha256"] = _sha256(p / "state.index.jsonl")
                r["events_sha256"] = _sha256(p / "events.jsonl")
            else:
                r["state_raw_sha256"] = _sha256(p / "state.raw.zst")
        r["fights"] += 1
        r["frames"] = [min(r["frames"][0], f["f0"]), max(r["frames"][1], f["f1"])]
    import cv2
    import numba
    return {"code": code, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "versions": {"numpy": np.__version__, "numba": numba.__version__, "cv2": cv2.__version__},
            "inputs": inputs, "npz_sha256": _sha256(npz) if npz else None}


def reach_summary(tpls: dict[str, hb.SpaceTimeTemplate], max_boxes: int = 64) -> dict:
    """Per family template (<family>/<frame>): extent, active window, and a conservative box cover of the reach
    union (DESIGN §4.4 reach_union), coarsened to at most max_boxes boxes."""
    out = {}
    for key, t in tpls.items():
        if key.count("/") != 1:
            continue
        ext = t.extent()
        act = t.active()
        out[key] = {"npz": hb.SUPPORT + key if t.t_pad else key, "frame": t.frame, "n_instances": t.n_instances,
                    "pad_u": _r(t.pad_x, 4), "t_pad_bins": t.t_pad,
                    "extent": [_r(v, 3) for v in ext] if ext else None,
                    "active_s": ("always (static)" if t.static else [_r(v, 4) for v in act]) if act else None,
                    "cells": int(t.reach().sum()), "boxes": [[_r(v, 3) for v in b] for b in coarse_boxes(t, max_boxes)]}
    return out


def coarse_boxes(t: hb.SpaceTimeTemplate, max_boxes: int = 64) -> np.ndarray:
    """A conservative cover of the reach union with at most max_boxes boxes: the exact row-run cover, made coarser
    (the mask is max-pooled into larger cells) until it fits."""
    mask = t.reach()
    k = 1
    while True:
        if k == 1:
            m = mask
        else:
            ny, nx = (mask.shape[0] + k - 1) // k, (mask.shape[1] + k - 1) // k
            pad = np.zeros((ny * k, nx * k), bool)
            pad[:mask.shape[0], :mask.shape[1]] = mask
            m = pad.reshape(ny, k, nx, k).any(axis=(1, 3))
        b = hb.mask_boxes(m).astype(np.float64) * k
        if len(b) <= max_boxes or k >= max(mask.shape):
            break
        k *= 2
    b[:, [0, 2]] += t.ix0
    b[:, [1, 3]] += t.iy0
    return b * t.cell


def _held_row(items: list[tuple], radius: dict[str, tuple]) -> dict:
    """Held-out residuals (residual, residual with +-HELD_T_BINS, member keys) against the support radius of the
    full build (the smallest radius among the set's templates)."""
    v = np.array([i[0] for i in items], np.float64)
    vt = np.array([i[1] for i in items], np.float64)
    r = np.array([min((radius[k][0] for k in i[2] if k in radius), default=0.0) for i in items], np.float64)
    fin = v[np.isfinite(v)]
    return {"n": int(v.size), "within_radius": int((v <= r + 1e-9).sum()),
            f"within_radius_t{HELD_T_BINS}": int((vt <= r + 1e-9).sum()),
            "p99": _r(float(np.quantile(fin, 0.99))) if fin.size else None,
            "max": (_r(float(v.max())) if np.isfinite(v).all() else "inf") if v.size else None,
            "beyond_r_fail": int((v > R_FAIL_U).sum()), f"beyond_r_fail_t{HELD_T_BINS}": int((vt > R_FAIL_U).sum())}


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")
