"""Map v2: THE STRIKE-WINDOW REFLEX (the person's idea of 2026-10-23; HANDOFF 'Task reflex'). Stage 1: the window set,
the table's design and THE GENERATOR (exact, on the validated models), validated on live presses. Offline code: nothing
in the bot imports it; the runtime layer (Reflex) is behind SSBOT_FORUM_REFLEX (default off) and is NOT wired into the
policy (that comes after M4's gate, as one more layer on top of Map2Controller.pre()).

THE IDEA. The strike windows belong to the Clapper: around each of its moves there are a few bright windows (e.g. 'the
Clawline pressed at slam antic 5 - 11 -> the down slash on Slam 0, the first window'). They are computed OFFLINE and
stored on the Clapper as a table keyed by its (move state, frame in it, facing) and her state RELATIVE to it; each frame
the reflex looks up whether her state is inside an open window of a Clapper's current move and frame and, if the press
is safe, takes the keys, plays the window's fixed press macro to the strike and hands back. The search (re-planning every
0.25 - 0.6 s) misses the windows that open right after the Clapper reveals its move; a lookup costs < 1 ms.

    from ssbot.map2 import reflex as rx, search as ms
    W = ms.World(); ev = rx.judge_evaluator(W)
    v = rx.judge(W, ev, S, obs, iid, rx.WINDOWS["claw_slam0"], rx.Macro("cl", hop=3, k=47))   # exact, one start
    key = rx.cell_of(S, o_target, wt)            # her state relative to the Clapper -> the table's cell
    vc = rx.judge_cell(W, ev, key, wt, macro)    # the cell's verdict: every sample point of the cell (conservative)

THE WINDOW SET (WINDOWS; frames j = the Clapper's frame in its state at the frame BEFORE the macro's first key, M2's
convention - SP13's antic k = j + ~2 with its P two frames before the latched press):
  claw_slam0  slam, FIRST window by the Clawline: the Clawline toward it (from the ground after a hop of h frames, from
              the air at once), the hooked pull, control, the down slash pressed at an absolute frame K (>= control + 9:
              the 0.15 s cooldown) onto the Slam 0 body (Slam Antic j >= 44, Slam 0, Slam 1). Anchor Slam Antic 0 - 16.
  claw_head2  slam, SECOND window by the Clawline: the same macro with the strike on its head in the antic (Slam
              Antic j <= 43; the person: 29 - 42 after a hook; above the hammer, which reaches 7.6 u). Anchor Slam
              Antic 0 - 8 (in Idle: the search's).
  hop_slam0   slam, FIRST window from near on the ground (the old SLAMSTRIKE): a jump held h frames, the down slash at
              frame t, a drift key. Anchor Slam Antic 0 - 48.
  drop_slam0  slam, FIRST window from the air: the down slash at t from a fall / bounce, or from the umbrella's float
              (jump held to the press: its attack cancel; or the umbrella closed at once and the drop). Anchor 0 - 48.
  pogo_head2  slam, SECOND window from the air: the head pogo in the antic (Slam Antic j <= 43). Anchor 0 - 42.
  pogo_jantic the head pogo on a jump / jump cast's antic (Jump Antic, Cast Slam Antic 1 / 2) from the air; its take-off
              is the danger.
  ride_up     the jump ride: the down slash on the rising body (Jump / Air rising), from the ground (a hop) or the air.
              The person's recipe has a GROUND SIDE SLASH first: the side slash is not in the strike module (a missing
              primitive: its active frames and recoil are not measured for this target) - only the air part here.
  ride_down   the JUMP's continuation: follow it down, down slashes on the descending body (Air).
  cast_claw   the small rune cast's first-frame Clawline: the hook on Spell Antic (a cast holds no reaction: a free
              hit); the strike is the hook (4 damage). Its continuation (head pogos through Cast 1 / 2 against the
              bomb rows) is the search's / a later window.
  pogo_cast   the head pogo on a caster (Spell Antic / Cast 1 / Cast 2) from the air - what cast_claw leads to; the bomb
              rows lit after Cast 2 are its danger.
  evade_claw  the Clawline chasing an EVADING Clapper (Evade Scuttle, 15 u/s back for ~21 frames): the hook in the evade;
              the strike is the hook; safety through control + 13 (After Scuttle picks its next move from her
              position: the model's branches).
  jcast_rune  (not generated) the JUMP CAST's continuation: the umbrella against the big rune - a dodge, not a strike;
              the model has both (the rune's hazard, HERO2's umbrella); a table of safe floats would be its own kind.
  idle_hook   (not generated) the Clawline on an Idle / Walk Clapper: its follow-up depends on the reaction drawn at the
              needle's hit - the search's job (contingent plans); 'open' information at most.

THE TABLE (design; stage 1 builds only the cells the validation needs):
  key   window type, the Clapper's state and its frame j (exact), its facing (mirrored: dx = (her x - its x) x its
        facing, + in front), the wall band (WALL_BANDS: the distance from the Clapper to the wall it faces in 3 u bands
        within 12 u of either wall, 'open' between; her own wall distance follows from dx), her class:
          G  on the ground (normal control; x is instant, no vx key)
          A  airborne, normal control, jump not held (ballistic: vy is the curve's phase) - bb x vy
          F  the umbrella's Float Idle - bb x the float's frames since its start (4-frame bins) x its vx class
        bb = her box bottom above the floor (0.25 u bins), vy in 1.2 u/s bins (one physics step of gravity), dx
        0.25 u bins; flags: the air dash used (the exit check's), the Clawline / attack availability are gates.
  entry the macro (Macro: family + parameters), the strike frame range, her end state, and the SAFETY: every outcome
        of THIS move (its branches x both timing views x both hook variants, M2's margins on) lands the strike, touches
        nothing (her i-frames and the hooked body's harmless frames as measured) up to the macro's end, and keeps an
        exit (M3's coarse exit check, 40 f / to a big rune's end).
  cell  a window only if EVERY sample point of the cell is (the corners of its continuous bins, the wall band's
        ends): precision first.
  RESOLUTION (from the measured spreads): the kin model's plain motion is within 0.1 u in 99.6 % (M0 / M4a 96-97 %
        of the trials within 0.1 u throughout), the Clawline's hold height residual sd 0.09 u, the observed positions
        exact -> 0.25 u cells (2.5x the model's tolerance, ~1/8 of the down slash's reach past her box); vy 1.2 u/s =
        one physics step of the curve; the slam's own timing spread (antic 47 - 49) is in the outcomes, j is exact.

THE GENERATOR (judge): the macro as a search Plan rolled by the search's closed-loop evaluation (ssbot.map2.search
Evaluator: kin_jit HERO2, the strike module, the Clapper model's predict with her path, both timing views, both hook
variants, the margins) and judged strictly: lands in every outcome, no collision at all to the macro's end (the search
allows one after a reveal: the reflex does not), the exit check in every outcome.

Coordinates: u world units, her transform x (= her box centre x), bb her box bottom above the floor (3.015).
"""
from __future__ import annotations

import math
import os
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, replace

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import strike as sk

ENV = "SSBOT_FORUM_REFLEX"
J, A, D, L, R = km.B_JUMP, km.B_ATTACK, km.B_DOWN, km.B_LEFT, km.B_RIGHT
DIRS = L | R

FIRST_WIN = (("Slam Antic", 44, 999), ("Slam 0", 0, 999), ("Slam 1", 0, 999))
SECOND_WIN = (("Slam Antic", 0, 43),)      # the head pogo in the antic, before the first window


def enabled() -> bool:
    return os.environ.get(ENV, "0").strip() == "1"


# ---- the window set -------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Window:
    name: str
    zh: str
    anchor: tuple                  # ((state, j_lo, j_hi), ...): where the window may open
    classes: tuple                 # her classes at the macro's start
    family: str                    # "cl" (the Clawline, then the down slash) / "ds" (the down slash)
    strike: str                    # "down" / "claw": the strike that must land
    target: tuple                  # ((state, j_lo, j_hi), ...): the target's state at the strike's contact
    support: str                   # what the model supports / what data is missing
    generated: bool = True


WINDOWS = {w.name: w for w in (
    Window("claw_slam0", "飞针→冲锤第一窗口", (("Slam Antic", 0, 16),), ("G", "A", "F"), "cl", "down", FIRST_WIN,
           "model: claw_hook (M0 / M4a) + the down slash contact + the slam's timelines; live: SP13 CLAWSTRIKE"),
    Window("claw_head2", "飞针→头顶第二窗口", (("Slam Antic", 0, 8),), ("G", "A", "F"), "cl", "down", SECOND_WIN,
           "model: as claw_slam0 with the head pogo in the antic; live: few presses at antic 0 - 4"),
    Window("hop_slam0", "小跳下劈冲锤", (("Slam Antic", 0, 48),), ("G",), "ds", "down", FIRST_WIN,
           "model: kin_jit HERO2 + the down slash contact; live: the slam playbook, the person's 33 strikes"),
    Window("drop_slam0", "空中/收伞落下劈冲锤", (("Slam Antic", 0, 48),), ("A", "F"), "ds", "down", FIRST_WIN,
           "model: HERO2's umbrella cancel / Deflate (M0); live: the air show, AIRSTRIKE (5)"),
    Window("pogo_head2", "空中头顶下劈", (("Slam Antic", 0, 42),), ("A", "F"), "ds", "down", SECOND_WIN,
           "model: the head pogo (M0 bounce); live: the air show's pogos on the antic"),
    Window("pogo_jantic", "跳前头顶下劈", (("Jump Antic", 0, 30), ("Cast Slam Antic", 0, 16), ("Cast Slam Antic 2", 0, 40)),
           ("A", "F"), "ds", "down", (("Jump Antic", 0, 999), ("Cast Slam Antic", 0, 999), ("Cast Slam Antic 2", 0, 999)),
           "model: the head pogo on a jump's antic (its take-off is the danger); live: the bots' pogos on the jump "
           "casters' antics"),
    Window("ride_up", "骑跳上升下劈", (("Jump Antic", 0, 40), ("Cast Slam Antic", 0, 20), ("Cast Slam Antic 2", 0, 45),
                                    ("Air", 0, 26)), ("G", "A", "F"), "ds", "down",
           (("Jump", 0, 999), ("Air", 0, 26)),
           "partial: the air down slash on the rising body only; the person's GROUND SIDE SLASH first is a missing "
           "primitive (the side slash's active frames / recoil on this target not in the strike module)"),
    Window("ride_down", "跟落下劈", (("Air", 20, 70),), ("A", "F"), "ds", "down", (("Air", 27, 999),),
           "model: the descending Air body (M2's flight, the wall push); live: the air show"),
    Window("cast_claw", "小符文首帧飞针", (("Spell Antic", 0, 8),), ("G", "A", "F"), "cl", "claw",
           (("Spell Antic", 0, 999), ("Cast 1", 0, 999)),
           "model: the hook on the cast (no reaction); the continuation (head pogos vs the bombs) not in this window"),
    Window("pogo_cast", "施法头顶下劈", (("Spell Antic", 0, 44), ("Cast 1", 0, 6), ("Cast 2", 0, 26)), ("A", "F"), "ds",
           "down", (("Spell Antic", 0, 999), ("Cast 1", 0, 999), ("Cast 2", 0, 999)),
           "model: the head pogo on the caster (a cast holds no reaction), the bomb rows' timing (M2); what the cast's "
           "Clawline leads to; live: the air show's pogos on casters"),
    Window("evade_claw", "飞针追闪避", (("Evade Scuttle", 0, 18),), ("G", "A", "F"), "cl", "claw",
           (("Evade Scuttle", 0, 999),),
           "model: the hook on the moving evade body (claw_hook's dash to its front), After Scuttle's pick (M2); "
           "live: SP10c CLAW_CHASE, the air show's chase"),
    Window("jcast_rune", "伞挡大符文", (("Air", 0, 70),), ("A", "F"), "ds", "down", (),
           "not generated: a dodge (the umbrella vs the big rune), not a strike", generated=False),
    Window("idle_hook", "钩待机", (("Idle", 0, 999), ("Walk", 0, 999)), ("G", "A", "F"), "cl", "claw",
           (("Idle", 0, 999), ("Walk", 0, 999)),
           "not generated: the follow-up depends on the reaction (the search's contingent plans)", generated=False),
)}


def in_states(st: str | None, j: int, spec: tuple) -> bool:
    for (s, lo, hi) in spec:
        if st == s and lo <= j <= hi:
            return True
    return False


def windows_for(st: str | None, j: int) -> list:
    """The generated window types anchored at the Clapper's state and frame."""
    return [w for w in WINDOWS.values() if w.generated and in_states(st, j, w.anchor)]


# ---- macros ---------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Macro:
    """A fixed short key sequence from the macro's first frame (frame 1; frame 0 is the decision) to the strike.
    family "ds": a jump held `hop` frames (from the ground: the take-off; from the float with jh: the umbrella kept),
      the drift key dd (+1 toward the target's side at the start, -1 away, 0 none) held to the press, down held from
      the frame before the press, the attack pressed at frame t (2 frames: the oracle's hold filter), then `tail`
      frames of no key (her bounce / landing).
      From the umbrella's Float Idle: jh True keeps jump held to t + 1 (the umbrella's attack cancel: the slash on the
      press frame); jh False releases it at frame 1 (the close: the Deflate, then the fall).
    family "cl": a hop of `hop` frames (the ground; 0 in the air), `wait` frames, the Clawline toward the target on the
      last of the hop + wait frames (frame n = max(hop + wait, 1); its key and the direction latched there), the hooked
      pull to control, then the down slash pressed at the ABSOLUTE frame k from the decision (None: the hook is the
      strike - the macro ends at control + 13 + 2) with the drift key dd after control, and `tail` frames. Control is
      a branch point the reflex sees (her stop and its frame): `cont` gives the continuation PER HOOK VARIANT
      ((variant, k, dd), ...; judge_cl finds them) - the table stores one per variant.
    raw: explicit latched masks (a live macro): (pre masks frames 1 .. n, claw d or 0, post masks by absolute frame
      from n + 1, down slash press frames (absolute)) - the parameters are then ignored."""
    family: str
    hop: int = 0
    jh: bool = False
    wait: int = 0
    t: int = 1
    dd: int = 0
    k: int | None = None
    tail: int = 18
    raw: tuple | None = None
    cont: tuple = ()
    dlat: int = 0                  # (stage 4) a Clawline continuation's drift key from control + dlat (0 / 1: control + 1,
    #                                the model's; the runtime sends it later when the variants' drifts differ: DRIFT_LAT)

    def label(self) -> str:
        if self.raw is not None:
            return f"{self.family}:raw"
        if self.family == "ds":
            return f"ds h{self.hop}{' jh' if self.jh else ''} t{self.t} dd{self.dd:+d}"
        if self.cont:
            return f"cl h{self.hop} w{self.wait} " + " ".join(f"{v}:k{k}{dd:+d}" for (v, k, dd) in self.cont)
        return f"cl h{self.hop} w{self.wait} k{self.k} dd{self.dd:+d}"


@dataclass
class Raw:
    pre: np.ndarray                # latched masks of frames 1 .. n (n = len)
    claw: int                      # 0: no Clawline; +-1: pressed toward d on frame n (the segment's last frame)
    post: np.ndarray               # after a Clawline: masks of the absolute frames n + 1 .. (the block's frames ignored)
    ds: list                       # down slash press frames (absolute, from the decision)
    alts: dict = field(default_factory=dict)   # hook variant -> (post, ds): its own continuation after control
    dlat: int = 0                  # the continuation's drift key from control + dlat (Macro.dlat)


def render(m: Macro, d: int) -> Raw:
    """The macro's latched masks for a target on side d (+1: to her right)."""
    if m.raw is not None:
        pre, claw, post, ds = m.raw[:4]
        r = Raw(np.asarray(pre, np.int64), int(claw), np.asarray(post, np.int64), [int(x) for x in ds], dlat=m.dlat)
        if m.cont and r.claw:
            r.alts = {v: (_cl_post(len(r.pre), k, d * dd, m.tail), [k]) for (v, k, dd) in m.cont}
        return r
    tw = R if d > 0 else L
    aw = L if d > 0 else R
    dk = tw if m.dd > 0 else aw if m.dd < 0 else 0
    if m.family == "ds":
        t = max(int(m.t), 1)
        n = t + 1 + m.tail
        x = np.zeros(n, np.int64)
        for i in range(min(m.hop, n)):
            x[i] |= J
        if m.jh:
            x[:min(t + 1, n)] |= J
        x[:t] |= dk
        x[max(t - 2, 0):min(t + 1, n)] |= D
        x[t - 1:min(t + 1, n)] |= A
        return Raw(x, 0, np.zeros(0, np.int64), [t])
    n = max(int(m.hop) + int(m.wait), 1)
    pre = np.zeros(n, np.int64)
    for i in range(min(m.hop, n)):
        pre[i] |= J
    pre[max(n - 2, 0):] |= tw
    alts = {v: (_cl_post(n, k, d * dd, m.tail), [k]) for (v, k, dd) in m.cont}
    if m.k is None:
        return Raw(pre, d, np.zeros(CL_HOOK_END, np.int64), [], alts, m.dlat)
    return Raw(pre, d, _cl_post(n, int(m.k), d * m.dd, m.tail), [int(m.k)], alts, m.dlat)


CL_HOOK_END = 35 + 15              # a hook-only macro: no key to control (<= P + 34) + 13 + 2


def _cl_post(n: int, k: int, sd: int, tail: int) -> np.ndarray:
    """A Clawline's continuation by absolute frame from n + 1 (the block's frames are ignored): the drift key toward
    side sd (+1 right / -1 left / 0) to the press, down from k - 1 to k + 1, the attack at k and k + 1, `tail` frames."""
    dk = R if sd > 0 else L if sd < 0 else 0
    post = np.zeros(max(k + 1 + tail - n, 1), np.int64)
    post[:max(k - n, 0)] |= dk
    for f in range(k - 1, k + 2):
        if 0 <= f - n - 1 < len(post):
            post[f - n - 1] |= D
    for f in (k, k + 1):
        if 0 <= f - n - 1 < len(post):
            post[f - n - 1] |= A
    return post


def plan_of(raw: Raw, iid: int, ctrls: dict | None = None):
    """The raw macro as a search Plan. A Clawline's continuation is cut from the absolute masks at each hook
    variant's control (ctrls: variant name -> control frame; Seg.var_alt), so the down slash keeps its absolute frame
    (the slam's timing is absolute; the reflex sees control and presses at frame k)."""
    from ssbot.map2 import search as ms
    if not raw.claw:
        dsl = [(t - 1, iid) for t in raw.ds if 1 <= t <= len(raw.pre)]
        return ms.Plan([ms.Seg(raw.pre.copy(), dsl, None, "reflex")], "reflex")
    n = len(raw.pre)
    seg1 = ms.Seg(raw.pre.copy(), [], (int(raw.claw), iid), "reflex")
    if not len(raw.post):
        return ms.Plan([seg1], "reflex")

    def cont(ctrl: int, post: np.ndarray, ds: list):
        lo = ctrl - n                                   # post index of frame ctrl + 1
        m = post[max(lo, 0):].copy() if lo < len(post) else np.zeros(1, np.int64)
        dsl = [(K - ctrl - 1, iid) for K in ds if K - ctrl - 1 >= 0 and K - ctrl - 1 < len(m)]
        if not len(m):
            m = np.zeros(1, np.int64)
        if raw.dlat > 1:
            m[:raw.dlat - 1] &= ~DIRS                   # the drift key sent from control + dlat (DRIFT_LAT)
        return ms.Seg(m, dsl, None, "reflex+")
    ctrls = ctrls or {}
    alts = {v.name: cont(int(ctrls.get(v.name, n + 26)), *raw.alts.get(v.name, (raw.post, raw.ds)))
            for v in sk.HOOK_VARIANTS}
    seg2 = alts[sk.HOOK_VARIANTS[0].name]
    seg2 = ms.Seg(seg2.masks.copy(), list(seg2.dsl), None, "reflex+", var_alt=alts)
    return ms.Plan([seg1, seg2], "reflex")


# ---- the judge (exact) ------------------------------------------------------------------------------------------------

@dataclass
class Verdict:
    window: bool
    lands: int                     # outcomes whose strike landed (on the target, in the window's target states)
    safe: int                      # outcomes with no collision to the macro's end
    exit: int                      # outcomes with an exit after it
    n: int                         # outcomes
    why: str = ""                  # the first failure (most probable outcome first)
    k_strike: tuple = ()           # (first, last) strike contact frame over the outcomes (from the decision)
    k_end: int = 0
    end: tuple = ()                # her end state of the most probable outcome: (dx along its facing, bb, vx, vy)
    ms: float = 0.0
    detail: list = field(default_factory=list)
    by_var: dict = field(default_factory=dict)  # hook variant -> [outcomes, landed, safe, exit]
    cont: tuple = ()               # judge_cl: the continuation found per hook variant ((variant, k, dd), ...)

    def short(self) -> str:
        return (f"{'WIN' if self.window else 'no '} lands {self.lands}/{self.n} safe {self.safe}/{self.n} exit "
                f"{self.exit}/{self.n} {self.why} k {self.k_strike} {self.ms:.0f}ms")


# ---- the judge's robustness (stage 1 validation; reflex_val) ------------------------------------------------------------
# THE HOOK'S STOP: the strike module's two hook variants stop her box front 1.7 / 2.5 u short of the body front. Live
# (1,057 hooked Clawlines of the bots' runs with the body known; reflex_val events, scripts/hook_gap3.py), her box
# front short of the body front at control, by her box bottom at the press minus the body's top at the dash (P + 18):
#   a STATIC target (the same state family at the press and control: Slam Antic, a cast, Idle) - below -3.5 u p5 / p50
#   / p95 0.79 / 1.94 / 2.60 (n 380, min 0.28), -3.5 .. -2.5 0.65 / 1.88 / 2.71 (196), -2.5 .. -1.5 0.16 / 2.01 / 2.86
#   (127), -1.5 .. 0 -0.04 / 1.90 / 2.62 (79);
#   a MOVING target (an evade, a jump, a walk, a lunge by control) - 1.55 / 2.44 / 4.24 .. 4.85 from -3.5 u up, and below
#   -3.5 the jumps' bodies rising over her (p5 -2.3).
# So the judge adds a NEAR variant (0.8 u: p5 - p10 of the static low holds; a ground hook stopped 0.81 u short in a false
# window of the first run; 0.5 - 0.7 u closes every CLAWSTRIKE window at antic 0 - 2: the antic body grown by the slam's
# in-move margin, 0.5 u, touches her at the bounce - a static body, so that is the margin's conservatism, not a live
# risk) and, for a moving target, a FAR one (4.5 u: its p95); a static target's hold within 2.5 u of its top (its near
# tail reaches 0 / below: the dash passes along / over the body) is outside the judge's domain.
NEAR = sk.HookVariant("near", 17, 0.8, 5)
FAR = sk.HookVariant("far", 19, 4.5, 6)
JUDGE_HOOK_VARIANTS = sk.HOOK_VARIANTS + (NEAR,)
MOVING = ("Evade Scuttle", "Walk", "Jump", "Air", "Slam 0", "Slam 1")
HOOK_HOLD_MAX = -2.5               # her box bottom at the press minus the target's body top (u): the hook's domain


def judge_variants(o, robust: bool = True) -> tuple:
    """The hook variants the judge uses for a Clawline at the Clapper o (its state at the decision)."""
    if not robust:
        return sk.HOOK_VARIANTS
    return JUDGE_HOOK_VARIANTS + ((FAR,) if o.st in MOVING else ())
# THE STRIKE'S TIMING: a down slash counts only if it also lands (at any of its active frames) with the target's records
# shifted one frame later and one frame earlier: the Clapper one frame early or late still takes it (live: the slam's
# lunge started a frame after the model's Slam 0 entry + 1 in a false window of the first run); the contact frame and
# the bounce are the unshifted one's. And a landing between the press and the contact ends the swing (strike.dslash_
# contact looks for the ground only in the active frames t + 3 .. 9: a press 2 frames above the floor, a landing at t + 2
# and a jump at t + 3 'landed' its contact at t + 8 in a false window of the second run)
CONTACT_W = 1
LAND_BB = 0.02                     # her box bottom this near the floor counts as a landing (a frame's ground flag misses
#                                    a touch-down with a jump in the same frame: live the swing ended there)


class _Robust:
    """Context: the judge's hook variants and time-robust down slash contacts patched into the strike module for the
    evaluation (the search module reads both at call time); restored after."""

    def __init__(self, on: bool = True, w: int = CONTACT_W, variants: tuple | None = None):
        self.on, self.w, self.variants = on, w, variants

    def __enter__(self):
        self._hv, self._dc = sk.HOOK_VARIANTS, sk.dslash_contact
        if not self.on:
            if self.variants is not None:
                sk.HOOK_VARIANTS = self.variants
            return self
        orig, w = self._dc, self.w

        def contact(pos, face, ground, t, boxes, *a, **kw):
            # (oldwin port: strike.dslash_contact took shrink / c_min on the map2 t1 branch - passed through)
            c = orig(pos, face, ground, t, boxes, *a, **kw)
            if c < 0:
                return c
            bb = np.asarray(pos)[t + 1:c + 1, 1] - sk.FOOT - sk.FLOOR
            if np.any(np.asarray(ground)[t + 1:c + 1]) or np.any(bb <= LAND_BB):
                return -1                                     # she landed after the press: the swing ended
            for sh in range(1, w + 1):
                for s_ in (sh, -sh):
                    if orig(pos, face, ground, t, _shifted(boxes, s_), *a, **kw) < 0:
                        return -1
            return c
        sk.HOOK_VARIANTS = JUDGE_HOOK_VARIANTS if self.variants is None else self.variants
        sk.dslash_contact = contact
        return self

    def __exit__(self, *exc):
        sk.HOOK_VARIANTS, sk.dslash_contact = self._hv, self._dc
        return False


def _shifted(boxes: np.ndarray, sh: int) -> np.ndarray:
    """The target's boxes sh frames late (sh > 0: at frame k it is where it was at k - sh; NaN where unknown)."""
    B = np.asarray(boxes, float)
    out = np.full_like(B, np.nan)
    if sh > 0:
        out[sh:] = B[:-sh]
    elif sh < 0:
        out[:sh] = B[-sh:]
    else:
        out[:] = B
    return out


# (stage 4) THE CLAPPERS' PHYSICS STEPS ANCHORED TO HERS. A Clapper moves only on frames with a physics step (50 Hz in
# 60 Hz frames); the model's default puts the frame without one at k % 6 == 5 from the PREDICTION's frame 0, so two
# predictions made a frame apart disagree on a moving body by a step (0.5 u in the Slam 0 lunge) - the cached-world
# finding. The game's steps are global: in the recordings a moving Clapper (Evade Scuttle / Slam 0 / Walk) moved
# exactly on her kin step frames in 9,204 of 9,211 frames (reflex s4/clapper_steps). Every prediction of the reflex and
# of its judge takes the steps from her ALPHA at its frame 0 (kinematics' accumulator: + frame_time / fdt per frame, a
# step each time it passes 1). The generator's reference predictions (the tables) keep the default.
def clapper_steps(W, S, T: int) -> np.ndarray:
    """The physics steps of frames 0 .. T from her kin state S at frame 0 (kinematics.rollout's ALPHA accumulator);
    ANCHOR[0] False: the model's default (no step at k % 6 == 5)."""
    if not ANCHOR[0]:
        return np.array([0 if k % 6 == 5 else 1 for k in range(int(T) + 1)], np.int64)
    a = float(np.asarray(S, float).reshape(km.K, -1)[km.ALPHA, 0])
    key = (round(a, 7), int(T))
    c = _STEPS_CACHE.get(key)
    if c is not None:
        return c
    fdt = float(W.params.vector()[km.P_FDT])
    dt = float(np.float32(W.params.frame_time))
    out = np.ones(int(T) + 1, np.int64)
    for k in range(1, int(T) + 1):
        a = a + dt / fdt
        st = math.floor(a + 1e-9)
        a = min(max(a - st, 0.0), 1.0)
        out[k] = st
    if len(_STEPS_CACHE) > 4096:
        _STEPS_CACHE.clear()
    _STEPS_CACHE[key] = out
    return out


_STEPS_CACHE: dict = {}
ANCHOR = [True]                    # (a switch for the comparison: the anchored steps vs the model's default)


def _anchored(W, path, S, T: int):
    """The path with the Clappers' physics steps from her ALPHA (clapper_steps), unless it has its own."""
    if getattr(path, "steps", None) is None:
        path.steps = clapper_steps(W, S, max(int(T), path.T))
    return path


def judge_evaluator(W, anchor: bool = True, **cfg_kw):
    """The search's closed-loop evaluation with the margins on (the judge's settings); anchor (stage 4): its
    predictions' physics steps from her ALPHA at the situation's frame 0 (clapper_steps)."""
    from ssbot.map2 import search as ms
    ev = ms.Evaluator(W, ms.Cfg(margins=True, **cfg_kw))
    if anchor:
        orig = ev.predict

        def predict(sit, path, T, _orig=orig):
            return _orig(sit, _anchored(W, path, sit.S, T), T)
        ev.predict = predict
    return ev


def _hook_ctrls(W, S, raw: Raw, iid: int, br, alpha_c: int) -> dict:
    """Each hook variant's control frame for a Clawline pressed on the raw macro's frame n at the target (its robust
    body boxes in the branch): the strike module's claw_hook on her state at the end of frame n."""
    n = len(raw.pre)
    r = W.roll(S, raw.pre)
    Sp = r.final[:, 0]
    bx = sk.robust_boxes(br, iid)
    if len(bx) < n + 62:
        bx = np.concatenate([bx, np.full((n + 62 - len(bx), 4), np.nan)])
    out = {}
    for v in sk.HOOK_VARIANTS:
        h = sk.claw_hook(Sp, n, raw.claw, iid, bx, v, alpha_c)
        out[v.name] = h.ctrl if h.ok else -1
    return out


def _state_near(br, iid: int, k: int, back: int = 4):
    """The Clapper's (state, frame, x, y, face) at frame k of a timing view, else of the last frame before it that has a
    record (a view draws its records at k + a or k + b: where the offset grows, frames have none)."""
    for kk in range(k, max(k - back, -1), -1):
        st = sk.state_at(br, iid, kk)
        if st is not None:
            return st if kk == k else (st[0], st[1] + (k - kk)) + tuple(st[2:])
    return None


TARGET_SLACK = 1                   # the target state must hold this many frames before and after the hit's frame (live:
#                                    pogos at a cast's last frames landed on the Idle after it - its timing a frame off)


def _in_target(br, iid: int, k: int, target: tuple) -> bool:
    """The hit at frame k counts for the window: the Clapper was in a target state in the frame before the hit (it
    reacts in the hit's frame) and stays in one for TARGET_SLACK frames around it."""
    st0 = _state_near(br, iid, k - 1)
    if st0 is None or not in_states(st0[0], int(st0[1]), target):
        return False
    after = () if st0[0] in ("Idle", "Walk") else range(k, k + TARGET_SLACK)   # (Idle / Walk react in the hit frame)
    for kk in list(range(k - 1 - TARGET_SLACK, k - 1)) + list(after):
        st = _state_near(br, iid, kk)
        if st is None or not in_states(st[0], int(st[1]), target):
            return False
    return True


def judge(W, ev, S: np.ndarray, obs: list, iid: int, wt: Window, macro: Macro, mems: dict | None = None,
          hazards: list | None = None, detail: bool = False, robust: bool = True,
          variants: tuple | None = None, select=None, ctrls_over: dict | None = None) -> Verdict:
    """The window's verdict for the macro from her exact kin state S (frame 0) with the Clappers obs (frame 0; iid the
    target): lands / safe / exit in EVERY outcome (module docstring). robust: the judge's hook variants (+ near) and
    time-robust contacts (_Robust) and the hook's height domain. ctrls_over: a Clawline's continuation cut at these
    control frames per variant (judge_press)."""
    if variants is None and robust:
        variants = judge_variants(next(o for o in obs if o.iid == iid))
    with _Robust(robust, variants=variants):
        return _judge(W, ev, S, obs, iid, wt, macro, mems, hazards, detail, robust, select, ctrls_over)


def judge_press(W, ev, S: np.ndarray, obs: list, iid: int, wt: Window, macro: Macro, mems: dict | None = None,
                hazards: list | None = None, ref: dict | None = None, dlat: int = 0) -> Verdict:
    """A PRESS as the runtime plays it, judged exactly: like judge, but a Clawline window's continuation keeps its
    down slash at its ABSOLUTE frame whatever control the outcome's hook reaches, and (stage 4) it is the continuation
    the RUNTIME picks for the stop and control the outcome shows (ref: the Press's reference stops per variant,
    Press.ref_rel(); pick_alt - an outcome no variant's stop explains ends the press: a failure), its drift from control
    + dlat: each (variant, control, picked continuation) group of outcomes judged once, the continuation cut there.
    Without ref: each variant's own continuation (stage 2's convention)."""
    v0 = judge(W, ev, S, obs, iid, wt, replace(macro, dlat=dlat), mems, hazards, detail=True)
    if macro.family != "cl" or not macro.cont or (v0.window and ref is None) or (not v0.window and not v0.detail):
        return v0                                       # (no outcomes: the judge's domain / low HP / no swing)
    tgt = next(o for o in obs if o.iid == iid)
    vs_all = judge_variants(tgt)
    names = {c[0] for c in macro.cont}
    own = {c[0]: (c[1], c[2]) for c in macro.cont}
    lands = safe = exit_ = n = 0
    why = ""
    for var in vs_all:
        if var.name not in names:
            continue
        groups = Counter()
        for d in v0.detail:
            if d[2] != var.name:
                continue
            hk = [h for h in d[7] if h[3]]
            if not hk:
                n += 1
                why = why or f"{var.name}:unhooked"
                continue
            c, dx = int(hk[0][2]), float(hk[0][4])
            if ref is not None:
                a = pick_alt(ref, c, dx)
                if a is None:
                    n += 1
                    why = why or f"{var.name}@ctrl{c}:off model"
                    continue
                groups[(c, a[0])] += 1
            else:
                groups[(c, var.name)] += 1
        for (c, an) in sorted(groups):
            k_a, dd_a = (ref[an][3], ref[an][4]) if ref is not None else own[an]
            m2 = replace(macro, cont=((var.name, int(k_a), int(dd_a)),), dlat=dlat)

            def sel(outs, c_=c, an_=an):
                out = []
                for o in outs:
                    hh = [h for h in o.tr.hooks if h.ok and h.iid == iid]
                    if not hh or hh[0].ctrl != c_:
                        continue
                    if ref is not None:
                        a_ = pick_alt(ref, hh[0].ctrl, _stop_dx(hh[0], o.branch, iid))
                        if a_ is None or a_[0] != an_:
                            continue
                    out.append(o)
                return out
            v = judge(W, ev, S, obs, iid, wt, m2, mems, hazards, variants=(var,), select=sel,
                      ctrls_over={var.name: c})
            lands, safe, exit_, n = lands + v.lands, safe + v.safe, exit_ + v.exit, n + v.n
            if not v.window and not why:
                why = f"{var.name}@ctrl{c}>{an}:{v.why}"
    ok = n > 0 and lands == n and safe == n and exit_ == n
    return Verdict(ok, lands, safe, exit_, n, why, v0.k_strike, v0.k_end, v0.end, v0.ms)


def swings(W, S: np.ndarray, raw: Raw) -> bool:
    """(stage 4) Every down slash press of a down slash macro starts the kin's slash ON its press frame (the
    attacking flag rises there): HERO2's umbrella Deflate eats an attack pressed on the frame the umbrella is released
    (the float's 'release + attack at frame 1': no slash at all - SP13 AIRSTRIKE fp2), a cooldown delays one."""
    if raw.claw or not raw.ds:
        return True
    r = W.roll(np.asarray(S, float).reshape(km.K, -1)[:, 0], raw.pre)
    fl = r.flags[0]
    for t in raw.ds:
        if not 1 <= t < len(fl):
            return False
        if not (int(fl[t]) & km.F_ATTACKING) or (int(fl[t - 1]) & km.F_ATTACKING):
            return False
    return True


def _judge(W, ev, S, obs, iid, wt, macro, mems, hazards, detail, robust, select=None, ctrls_over=None,
           kill_alive=True) -> Verdict:
    from ssbot.map2 import clapper_jit as cj
    from ssbot.map2 import search as ms
    t0 = time.perf_counter()
    tgt = next(o for o in obs if o.iid == iid)
    hx = float(S[km.PX])
    d = 1 if tgt.x >= hx else -1
    raw = render(macro, d)
    if not raw.claw and raw.ds and not swings(W, S, raw):
        # (stage 4) the kin's slash does not start at the press (the umbrella's Deflate eats an attack pressed on the
        # frame the umbrella is released): search.simulate finds contacts from her positions only, a phantom strike
        return Verdict(False, 0, 0, 0, 0, "noswing", (), 0, (), (time.perf_counter() - t0) * 1e3)
    if raw.claw and int(tgt.hp) <= LOW_HP_CL:
        # (stage 4) a Clawline at a target this low: the needle's hit and the dash's damage can kill it before the
        # pull's end (the model has no killing hook) - the runtime does not take it (Reflex.check 'cl low hp'); the
        # validation's 28 claw_slam0 false windows at hp <= 14 were these
        return Verdict(False, 0, 0, 0, 0, "low hp", (), 0, (), (time.perf_counter() - t0) * 1e3)
    if kill_alive:
        obs = [replace(o, hp=max(int(o.hp), KILL_HP)) if o.iid == iid else o for o in obs]
    sit = ms.Situation(np.asarray(S, float), list(obs), mems if mems is not None else {o.iid: cm.Memory() for o in obs},
                       list(hazards or ()))
    ctrls = None
    if raw.claw and len(raw.post):
        T = len(raw.pre) + 70
        P0 = cj.predict(sit.obs, sit.mems, cm.HeroPath.constant(hx, float(S[km.PY]), T=T,
                                                              steps=clapper_steps(W, S, T)), W.K, T=T,
                        hazards=sit.hazards)
        br = max(P0.branches, key=lambda b: b.p)
        ctrls = _hook_ctrls(W, sit.S, raw, iid, br, sit.alpha_c)
        if ctrls_over:
            ctrls.update(ctrls_over)
        if robust and tgt.st not in MOVING:
            # the hook's domain: a static target's top at the dash (P + 18) >= 2.5 u above her box bottom at the press
            # (else the stop's near tail reaches the body: JUDGE_HOOK_VARIANTS)
            Sp = W.roll(sit.S, raw.pre).final[:, 0]
            rb = sk.robust_boxes(br, iid)
            P_ = len(raw.pre)
            top = float(np.nanmax(rb[P_ + 16:P_ + 20, 3])) if len(rb) > P_ + 19 else np.nan
            if np.isfinite(top) and float(Sp[km.PY]) - sk.FOOT - top > HOOK_HOLD_MAX:
                return Verdict(False, 0, 0, 0, 0, "domain:hold", (), 0, (), (time.perf_counter() - t0) * 1e3)
    plan = plan_of(raw, iid, ctrls)
    ev.reset()
    e = ev.evaluate(sit, plan, exits=True)
    lands = safe = exit_ = 0
    why = ""
    ks = []
    det = []
    by_var: dict = {}
    outs = sorted(e.outcomes, key=lambda o: -o.p)
    if select is not None:
        outs = select(outs)                      # (validation: only the outcomes that match what happened live)
    for o in outs:
        tr = o.tr
        ok_l = False
        if wt.strike == "claw":
            for h in tr.hooks:
                if h.ok and h.iid == iid:
                    if _in_target(o.branch, iid, h.hit, wt.target):
                        ok_l = True
                        ks.append(h.hit)
                        break
        else:
            for (kc, ii, kind) in tr.contacts:
                if kind == "down" and ii == iid:
                    if _in_target(o.branch, iid, kc, wt.target):
                        ok_l = True
                        ks.append(kc)
                        break
        if ctrls is not None and raw.ds:
            for h in tr.hooks:
                if h.iid == iid and h.ok and ctrls.get(h.variant, -2) != h.ctrl:
                    ok_l = False                       # the continuation was cut at another control
        ok_s = o.k_col is None
        ok_e = ok_s and o.safe
        lands += ok_l
        safe += ok_s
        exit_ += ok_e
        bv = by_var.setdefault(tr.variant or "-", [0, 0, 0, 0])
        bv[0] += 1
        bv[1] += ok_l
        bv[2] += ok_s
        bv[3] += ok_e
        if not why:
            if not ok_l:
                why = "miss" + ("" if not tr.missed else f":{tr.missed[0][0]}@{tr.missed[0][1]}")
            elif not ok_s:
                why = f"hit@{o.k_col}"
            elif not ok_e:
                why = o.why or "exit"
        if detail:
            det.append((round(o.p, 3), getattr(o.branch, "tview", ""), tr.variant, ok_l, o.k_col, o.why,
                        list(tr.contacts), [(h.P, h.hit, h.ctrl, h.ok, _stop_dx(h, o.branch, iid) if h.ok and
                                             h.iid == iid else float("nan")) for h in tr.hooks], tr.end))
    n = len(outs)
    nom = outs[0] if outs else None
    end = ()
    if nom is not None:
        st = ms.state_at(W, nom.tr, nom.tr.end)
        if st is not None:
            Se = st[0]
            end = (round((float(Se[km.PX]) - tgt.x) * tgt.face, 3), round(float(Se[km.PY]) - sk.FOOT - sk.FLOOR, 3),
                   round(float(Se[km.VX]) * tgt.face, 2), round(float(Se[km.VY]), 2))
    win = n > 0 and lands == n and safe == n and exit_ == n
    return Verdict(win, lands, safe, exit_, n, why, (min(ks), max(ks)) if ks else (), nom.tr.end if nom else 0, end,
                   (time.perf_counter() - t0) * 1e3, det, by_var)


def judge_cl(W, ev, S: np.ndarray, obs: list, iid: int, wt: Window, macro: Macro, mems: dict | None = None,
             hazards: list | None = None, robust: bool = True, dds: tuple = (0, 1, -1)) -> Verdict:
    """The Clawline window with its continuation chosen PER HOOK VARIANT (control is a branch point the reflex sees):
    the macro's press part (hop / wait, or a raw pre), then for each variant the earliest down slash frame k (abs from
    the decision; >= its control + 9) with the drift dd in dds whose every outcome of that variant lands, touches
    nothing and keeps an exit. A window when every variant has one (Verdict.cont). A hook-only window (wt.strike
    'claw'): the plain judge."""
    if wt.strike == "claw" or wt.family != "cl":
        return judge(W, ev, S, obs, iid, wt, macro, mems, hazards, robust=robust)
    from ssbot.map2 import clapper_jit as cj
    from ssbot.map2 import search as ms
    t0 = time.perf_counter()
    tgt = next(o for o in obs if o.iid == iid)
    if int(tgt.hp) <= LOW_HP_CL:
        return Verdict(False, 0, 0, 0, 0, "low hp", (), 0, (), (time.perf_counter() - t0) * 1e3)
    hx = float(S[km.PX])
    d = 1 if tgt.x >= hx else -1
    base = render(replace(macro, k=None, cont=()), d)
    pre = base.pre
    sit = ms.Situation(np.asarray(S, float), list(obs), mems if mems is not None else {o.iid: cm.Memory() for o in obs},
                       list(hazards or ()))
    variants = judge_variants(tgt, robust)
    with _Robust(robust, variants=variants):
        T = len(pre) + 80
        P0 = cj.predict(sit.obs, sit.mems, cm.HeroPath.constant(hx, float(S[km.PY]), T=T,
                                                              steps=clapper_steps(W, S, T)), W.K, T=T,
                        hazards=sit.hazards)
        br = max(P0.branches, key=lambda b: b.p)
        ctrls = _hook_ctrls(W, sit.S, base, iid, br, sit.alpha_c)
    # the target window's frames in the do-nothing branch: the press from its first frame - 9 to its last - 3
    kt = [k for k in range(len(pre) + 1, T) if (lambda st: st is not None and in_states(st[0], int(st[1]), wt.target))(
        _state_near(br, iid, k))]
    found, last = {}, {}
    raw_pre = macro.raw[0] if macro.raw is not None else None
    claw_d = int(macro.raw[1]) if macro.raw is not None and macro.raw[1] else d
    for v in variants:
        c = ctrls.get(v.name, -1)
        if c < 0 or not kt:
            continue
        lo, hi = max(c + 9, kt[0] - 9), min(kt[-1] - 3, c + 40)
        for dd in dds:
            for k in range(lo, hi + 1):
                m = (Macro("cl", raw=(raw_pre if raw_pre is not None else pre, claw_d, np.zeros(1, np.int64), []),
                           cont=((v.name, k, dd),), tail=macro.tail))
                vd = judge(W, ev, S, obs, iid, wt, m, mems, hazards, robust=robust, variants=(v,))
                last[v.name] = vd
                if vd.window:
                    found[v.name] = (k, dd, vd)
                    break
            if v.name in found:
                break
    ok = len(found) == len(variants)
    vs = [found[v.name][2] if v.name in found else last.get(v.name) for v in variants]
    vs = [x for x in vs if x is not None]
    why = "" if ok else next((f"{v.name}:" + (last[v.name].why if v.name in last else "no ctrl / target")
                              for v in variants if v.name not in found), "")
    ks = [k for x in vs for k in x.k_strike]
    out = Verdict(ok, sum(x.lands for x in vs), sum(x.safe for x in vs), sum(x.exit for x in vs),
                  sum(x.n for x in vs), why, (min(ks), max(ks)) if ks else (), max((x.k_end for x in vs), default=0),
                  vs[0].end if vs else (), (time.perf_counter() - t0) * 1e3, [],
                  {v.name: (found[v.name][2].by_var if v.name in found else {}) for v in variants},
                  tuple((v.name, found[v.name][0], found[v.name][1]) for v in variants if v.name in found))
    return out


# ---- the cells ------------------------------------------------------------------------------------------------------

# THE RESOLUTION (stage 2, table v1; stage 1 validated at dx / bb 0.25 u, vy 1.2 u/s, float 4 f: its dense table had
# 1.35e9 cells): on the ground dx 0.25 u (one dimension, cheap); in the air dx / bb 0.5 u, vy 2.4 u/s (two physics
# steps of gravity), the float's frames in 8-frame bins - 1/8 of the cells, each verdict at its corners; the runtime
# re-checks the cell's macro from her exact state (Reflex.check), so a coarse cell costs recall, not precision
DX_Q = 0.25                        # u: dx on the ground
DXA_Q = 0.5                        # u: dx in the air / the float
BB_Q = 0.5                         # u
VY_Q = 2.4                         # u/s
FPH_Q = 8                          # the float's frames since Float Idle started
WALL_SPAN = cm.WALL_R - cm.WALL_L  # 34.98
WALL_BANDS = (0.0, 3.0, 6.0, 9.0, 12.0, WALL_SPAN - 12.0, WALL_SPAN - 9.0, WALL_SPAN - 6.0, WALL_SPAN - 3.0, WALL_SPAN)
#                                    the distance from the Clapper to the wall it FACES: 3 u bands within 12 u of either
#                                    wall (the hammer's 7.76 u + her box, the jump's 12 u clamp, the escape ray's 6 u),
#                                    'open' (index 4) between


def front_dist(o) -> float:
    return (cm.WALL_R - o.x) if o.face > 0 else (o.x - cm.WALL_L)


def wall_band(o) -> int:
    f = front_dist(o)
    return int(min(max(np.searchsorted(WALL_BANDS, f, side="right") - 1, 0), len(WALL_BANDS) - 2))


def her_class(S: np.ndarray, rise_ok: bool = False) -> tuple | None:
    """Her class at frame 0 for the table: ("G",) / ("A", bb, vy) / ("F", bb, float frames, vx) or None (a state the
    table does not cover: a dash, the sprint, a slash under way or its recoil, the umbrella's antic / inflate /
    deflate, a Clawline, hurt, rising - with jump held or from a bounce). rise_ok (stage 4: a Clawline window): a
    rise is class A too - an air Clawline is pressed on frame 1 and its cell is keyed by her HOLD height (the antic
    clamps vy to -10 .. 5), not by the curve's phase; the check simulates the hook from her exact state (CLAWSTRIKE's
    air presses: 92 of 130 were rising without jump held, none keyable before)."""
    mode = int(S[km.MODE])
    bb = float(S[km.PY]) - sk.FOOT - sk.FLOOR
    if S[km.ATTACKING] > 0 or S[km.RSTEPS] > 0:
        return None                # (stage 2) a slash under way or its recoil: her next frames are not her keys' (the
        #                            table's sample points are at rest; a w13 replay's Clawline missed from a recoil)
    if mode == km.M_NORMAL:
        if S[km.GROUND] > 0:
            return ("G",)
        if rise_ok:
            return ("A", bb, float(S[km.VY]))
        if int(S[km.PREV]) & J and float(S[km.VY]) > 0:
            return None
        if float(S[km.VY]) > 0 or S[km.BOUNCE] >= 0:
            # (stage 2) a RISE without jump held is a pogo / Clawline bounce (its jumped steps below the cut's minimum:
            # it cannot be cut) - the table's corner states rise with the cut on (initial_state), so their verdicts
            # do not hold for it: the replay's show missed 1,826 of 3,097 cast pogos from bounces. Rises not keyed.
            return None
        return ("A", bb, float(S[km.VY]))
    if mode == km.M_GLIDE and int(S[km.PHASE]) == 2:
        return ("F", bb, int(round(float(S[km.MODE_T]) * 60.0)), float(S[km.VX]))
    return None


@dataclass(frozen=True)
class CellKey:
    wt: str
    st: str
    j: int
    band: int
    dxq: int
    cls: str
    bbq: int = 0                   # A / F: her box bottom bin (a Clawline window's A: her HOLD height's bin)
    sub: int = 0                   # A: the vy bin (a Clawline window: the vy class, CL_VY_EDGES); F: the float's frames
    vxc: int = 0                   # F: the float's vx class along the Clapper's facing (-1 / 0 / +1)
    adash: int = 0
    cvx: int = 0                   # stage 2: a jumping Clapper (Jump / Air): its vx along its facing in CVX_Q bins
    chg: int = 0                   # stage 2: ... and its charge (a jump cast: the big rune at its landing)

    def short(self) -> str:
        return (f"{self.wt} {self.st}:{self.j} b{self.band} dx{self.dxq * dx_q(self.cls):+.2f} {self.cls}"
                + (f" bb{self.bbq * BB_Q:.2f} s{self.sub}" if self.cls != "G" else "") + (f" vx{self.vxc:+d}" if self.cls == "F" else "")
                + (f" cvx{self.cvx * CVX_Q:+.0f}{' chg' if self.chg else ''}" if self.st in JUMPING else ""))


# ---- stage 2: the key's extra parts ---------------------------------------------------------------------------------
JUMPING = ("Jump", "Air")          # a Clapper in flight: its path depends on its vx (Jump X: the jump's aim, +-12 u/s) and
#                                    its charge (a jump cast lights the big rune at the landing) - both in the key
CVX_Q = 2.0                        # u/s: the flight's vx bins (2 u/s x the ~0.9 s flight = 1.8 u at the landing)
CVX_LIM = 6                        # bins -6 .. 5 (+-12 u/s)
CL_VY_EDGES = (-10.0, -5.0, 0.0, 5.0)   # a Clawline window from the air: her vy class (the antic clamps vy to -10 .. 5;
#                                         the hold height is the key, the class keeps the press frame's own fall)
CL_VY_SAMPLE = ((-30.0, -10.0), (-10.0, -5.0), (-5.0, 0.0), (0.0, 5.0), (5.0, 19.2))   # the classes' sampled ends


def dx_q(cls: str) -> float:
    return DX_Q if cls == "G" else DXA_Q


def hold_height(S: np.ndarray) -> float:
    """Her box bottom above the floor held through a Clawline pressed now (strike.hold_bb of her state)."""
    return sk.hold_bb(float(S[km.PY]) - sk.FOOT, float(S[km.VY])) - sk.FLOOR


def _hold_off(vy: float) -> float:
    return sk.hold_bb(0.0, vy)


def cl_vy_class(vy: float) -> int:
    return int(np.searchsorted(CL_VY_EDGES, vy, side="right"))


def clapper_extra(o) -> tuple:
    """(cvx, chg) of the key: a jumping Clapper's vx bin along its facing and its charge (0, 0 otherwise)."""
    if o.st not in JUMPING:
        return 0, 0
    v = float(o.vx) * (1 if o.face >= 0 else -1)
    return int(min(max(math.floor(v / CVX_Q), -CVX_LIM), CVX_LIM - 1)), int(bool(o.charged))


def cell_of(S: np.ndarray, o, wt: Window) -> CellKey | None:
    """The table cell of her state S relative to the Clapper o (both at frame 0) for the window type."""
    hc = her_class(S, rise_ok=wt.family == "cl")
    if hc is None or hc[0] not in wt.classes:
        return None
    dx = (float(S[km.PX]) - o.x) * o.face
    dxq = int(math.floor(dx / dx_q(hc[0])))
    j = int(o.j or 0)
    ad = 1                         # (stage 2) her air dash keyed as USED in the air: a window built with it spent
    #                                holds with it free (the exit only gains options) - one cell for both
    cvx, chg = clapper_extra(o)
    if hc[0] == "G":
        return CellKey(wt.name, o.st, j, wall_band(o), dxq, "G", adash=0, cvx=cvx, chg=chg)
    bbq = int(math.floor(hc[1] / BB_Q))
    if hc[0] == "A":
        if wt.family == "cl":
            return CellKey(wt.name, o.st, j, wall_band(o), dxq, "A", int(math.floor(hold_height(S) / BB_Q)),
                           cl_vy_class(hc[2]), 0, ad, cvx, chg)
        return CellKey(wt.name, o.st, j, wall_band(o), dxq, "A", bbq, int(math.floor(hc[2] / VY_Q)), 0, ad, cvx, chg)
    vx = hc[3] * o.face
    vxc = 0 if abs(vx) < 1.0 else (1 if vx > 0 else -1)
    return CellKey(wt.name, o.st, j, wall_band(o), dxq, "F", bbq, int(hc[2]) // FPH_Q, vxc, ad, cvx, chg)


def _clapper_x(band: int, face: int, edge: int) -> float:
    """A Clapper x inside the wall band (edge 0: the band's near end to the front wall + 0.05, 1: the far end - 0.05)."""
    lo, hi = WALL_BANDS[band], WALL_BANDS[band + 1]
    f = (lo + 0.05) if edge == 0 else (hi - 0.05)
    if band == 4:                  # 'open': its ends are 12 u from either wall
        f = (lo + 0.05) if edge == 0 else (hi - 0.05)
    return (cm.WALL_R - f) if face > 0 else (cm.WALL_L + f)


def cell_samples(W, key: CellKey, o_template, eps: float = 0.01) -> list:
    """The sample points of the cell: [(S, obs)] at the corners of its continuous bins and the wall band's two ends
    (the Clapper facing +1; mirrored keys are the same cell). o_template: the Clapper's Obs at frame 0 (its state, j,
    and what the history tells); its x / face are replaced."""
    out = []
    face = 1
    q = dx_q(key.cls)
    dxs = (key.dxq * q + eps, (key.dxq + 1) * q - eps)
    wt = WINDOWS.get(key.wt)
    cl = wt is not None and wt.family == "cl"
    if key.st in JUMPING:
        # a jumping Clapper: its vx at the bin's two ends (its y / vy are the template's: the flight's frame j)
        vxs = (key.cvx * CVX_Q + eps, (key.cvx + 1) * CVX_Q - eps)
        o_ts = [replace(o_template, vx=v * (1 if o_template.face >= 0 else -1), charged=bool(key.chg)) for v in vxs]
    else:
        o_ts = [o_template]
    for edge in (0, 1):
        cx = _clapper_x(key.band, face, edge)
        for o_t in o_ts:
            # the Clapper relocated into the band, facing +1 (its velocity along its facing kept); its own leftover
            # hazards (a bomb row / big rune still to light) are not in the cell: the runtime's gates
            o = replace(o_t, x=cx, face=face, vx=o_t.vx * o_t.face * face, cast2=None, rune=None)
            for dx in dxs:
                hx = cx + dx * face
                tw = 1 if cx >= hx else -1
                if key.cls == "G":
                    out.append((km.initial_state(W.params, hx, sk.FLOOR + sk.FOOT, ground=True, facing=tw), [o]))
                    continue
                if key.cls == "A" and cl:
                    # a Clawline window: her HOLD height at the bin's ends, her vy at its class's ends
                    for h in (key.bbq * BB_Q + eps, (key.bbq + 1) * BB_Q - eps):
                        for vy in CL_VY_SAMPLE[key.sub]:
                            vy = min(max(vy, CL_VY_SAMPLE[key.sub][0] + eps), CL_VY_SAMPLE[key.sub][1] - eps)
                            bb = h - _hold_off(vy)
                            S = km.initial_state(W.params, hx, sk.FLOOR + bb + sk.FOOT, ground=False, vy=vy, facing=tw)
                            S[km.AIRDASHED] = float(key.adash)
                            out.append((S, [o]))
                    continue
                for bb in (key.bbq * BB_Q + eps, (key.bbq + 1) * BB_Q - eps):
                    if key.cls == "A":
                        for vy in (key.sub * VY_Q + eps, (key.sub + 1) * VY_Q - eps):
                            S = km.initial_state(W.params, hx, sk.FLOOR + bb + sk.FOOT, ground=False, vy=vy, facing=tw)
                            S[km.AIRDASHED] = float(key.adash)
                            out.append((S, [o]))
                    else:
                        from ssbot.tools import m3_accept as ma
                        for fr in (key.sub * FPH_Q, key.sub * FPH_Q + FPH_Q - 1):
                            S = ma.float_state(W, hx, sk.FLOOR + bb, key=key.vxc * face, extra=fr, face=tw)
                            S[km.AIRDASHED] = float(key.adash)
                            out.append((S, [o]))
    return out


def judge_cell(W, ev, key: CellKey, wt: Window, macro: Macro, o_template, stop: bool = True) -> tuple:
    """(window, [Verdict per sample point]): a window only if every sample point is one."""
    vs = []
    jf = judge_cl if wt.family == "cl" else judge
    for (S, obs) in cell_samples(W, key, o_template):
        v = jf(W, ev, S, obs, obs[0].iid, wt, macro)
        vs.append(v)
        if stop and not v.window:
            break
    return (bool(vs) and all(v.window for v in vs)), vs


# ---- the table's dimensions (the design's size; stage 2 builds it) -------------------------------------------------------

# her relative x range per window type (dx along the Clapper's facing, u: the macro's reach - the Clawline's ray and
# pull, the down slash's 1.7 u past her box, a hop's drift) and her box bottom range (A / F, u above the floor)
DX_RANGE = {"claw_slam0": (0.0, 12.0), "claw_head2": (0.0, 12.0), "hop_slam0": (0.0, 9.0), "drop_slam0": (-3.0, 9.0),
            "pogo_head2": (-4.0, 6.0), "pogo_jantic": (-4.0, 6.0), "ride_up": (-6.0, 8.0), "ride_down": (-8.0, 8.0),
            "pogo_cast": (-4.0, 6.0), "cast_claw": (0.0, 12.0), "evade_claw": (0.0, 12.0)}
BB_RANGE = (0.0, 9.0)
VY_RANGE = (-30.0, 19.2)
FLOAT_F = 60                       # the float's frames binned (FPH_Q each): its vy is the curve's phase to ~60 f


DS_BB_SPAN = 8.0                   # ds windows: her box bottom within -2 .. +6 u of the target's body top (the slash
#                                    reaches 1.17 u below her feet + its 3 - 9 frames of fall; higher: no window this frame)


def table_dims(wt: Window, reduced: bool = False) -> dict:
    """The cell count of the window type's table: dense at the base resolution (every anchor frame x wall band x dx x
    her class's sub-cells x the air dash flag in the air), or REDUCED (stage 2's plan): the Clawline family keyed by
    her HOLD height (bb + 0.0774 clamp(vy, -10, 5): after the press her vertical is the hold - one key instead of
    bb x vy; the float adds its vx class), the down slash family's height within DS_BB_SPAN of the target's top, the
    air dash flag only as 'used' (a window with it used is one with it free: the exit only gains options)."""
    nj = sum(hi - lo + 1 for (_, lo, hi) in wt.anchor if hi < 999)
    ndx_g = int(round((DX_RANGE[wt.name][1] - DX_RANGE[wt.name][0]) / DX_Q))
    ndx = int(round((DX_RANGE[wt.name][1] - DX_RANGE[wt.name][0]) / DXA_Q))
    nbb = int(round((BB_RANGE[1] - BB_RANGE[0]) / BB_Q))
    nvy = int(round((VY_RANGE[1] - VY_RANGE[0]) / VY_Q))
    nfl = FLOAT_F // FPH_Q
    if not reduced:
        sub = {"G": 1, "A": nbb * nvy * 2, "F": nbb * nfl * 3 * 2}
    elif wt.family == "cl":
        sub = {"G": 1, "A": nbb * len(CL_VY_SAMPLE), "F": nbb * nfl * 3}
    else:
        nds = int(round(DS_BB_SPAN / BB_Q))
        sub = {"G": 1, "A": nds * nvy, "F": nds * nfl * 3}
    nb = len(WALL_BANDS) - 1
    per = {c: nj * nb * (ndx_g if c == "G" else ndx) * sub[c] for c in wt.classes}
    return {"anchor_frames": nj, "bands": nb, "dx_bins": ndx, "per_class": per, "cells": sum(per.values())}


# ---- the table (stage 2 builds it; the container and the O(1) lookup) -------------------------------------------------

@dataclass
class Entry:
    macro: Macro
    k_strike: tuple
    end: tuple
    conf: tuple = (1, 1)           # (sample points that passed, sample points): (n, n) a full window, else partial


_WT_IDS = {n: i for i, n in enumerate(sorted(WINDOWS))}
_ST_IDS = {n: i for i, n in enumerate(sorted({s for w in WINDOWS.values() for (s, _, _) in w.anchor}))}
_CLS_IDS = {"G": 0, "A": 1, "F": 2}


def pack_key(k: CellKey) -> int:
    """A cell key as one int64 (window type 5 bits, state 5, j 9, band 4, dx 9 (+256), class 2, bb 7, sub 8 (+128),
    vx 2 (+1), air dash 1, the flight's vx 4 (+8), its charge 1 = 57 bits)."""
    v = _WT_IDS[k.wt]
    for x, b in ((_ST_IDS[k.st], 5), (k.j, 9), (k.band, 4), (k.dxq + 256, 9), (_CLS_IDS[k.cls], 2), (k.bbq, 7),
                 (k.sub + 128, 8), (k.vxc + 1, 2), (k.adash, 1), (k.cvx + 8, 4), (k.chg, 1)):
        v = (v << b) | (int(x) & ((1 << b) - 1))
    return v


_WT_NAMES = {i: n for n, i in _WT_IDS.items()}
_ST_NAMES = {i: n for n, i in _ST_IDS.items()}
_CLS_NAMES = {i: n for n, i in _CLS_IDS.items()}


def unpack_key(v: int) -> CellKey:
    out = []
    for b in (1, 4, 1, 2, 8, 7, 2, 9, 4, 9, 5):
        out.append(v & ((1 << b) - 1))
        v >>= b
    chg, cvx, adash, vx, sub, bbq, cls, dxq, band, j, st = out
    if bbq >= 64:
        bbq -= 128                 # (stage 4) bbq is stored in 7 bits with no offset: a negative bin (a Clawline window's
        #                            hold height below the floor, -0.5 .. 0 u) came back as 127 (63.5 u)
    return CellKey(_WT_NAMES[v], _ST_NAMES[st], j, band, dxq - 256, _CLS_NAMES[cls], bbq, sub - 128, vx - 1, adash,
                   cvx - 8, chg)


VERSION = "clapper_windows_v2"     # (stage 4: v1 patched - reflex_build fix; the key format is v1's)
TABLE_PATH = cm.REPO / "knowledge" / "1.0.30000" / "enemies" / "forum" / "clapper_windows_v2.npz"
VERSIONS_OK = ("clapper_windows_v1", VERSION)       # the files Table.load reads (the same key and row format)
VARIANT_IDS = {"early": 0, "late": 1, "near": 2, "far": 3}
_VARIANT_NAMES = {i: n for n, i in VARIANT_IDS.items()}


class Table:
    """The windows of one Clapper type: packed cell key (pack_key) -> row; per row the macro's parameters, a Clawline
    window's continuation per hook variant, the strike frames, her end state, the confidence (sample points passed /
    sample points). Only the window cells are stored. Built in memory: a dict per packed key; LOADED from its file:
    the sorted packed keys and the row arrays (a binary search per lookup, ~2 us; millions of cells load in a second
    and stay arrays). save / load: an npz (keys, macro, cont, k_strike, end, conf) with a JSON meta (VERSION, the
    resolution, what was built)."""

    def __init__(self, cells: dict | None = None, meta: dict | None = None):
        self.meta = dict(meta or {})
        self.idx: dict = {}
        self._rows: list = []
        self._ent: dict = {}
        self._arr = None                       # (sorted keys, macro, cont, k_strike, end, conf) of a loaded file
        for k, e in (cells or {}).items():
            self.add(k, e)

    def add(self, key: "CellKey", e: Entry) -> None:
        self._thaw()
        pk = pack_key(key)
        if pk in self.idx:
            self._rows[self.idx[pk]] = e
        else:
            self.idx[pk] = len(self._rows)
            self._rows.append(e)
        self._ent.pop(pk, None)

    def __len__(self) -> int:
        return len(self._arr[0]) if self._arr is not None else len(self.idx)

    def keys(self):
        """The packed keys of the window cells."""
        return [int(k) for k in self._arr[0]] if self._arr is not None else list(self.idx)

    def _thaw(self) -> None:
        """A loaded table made editable (its rows into the dict form)."""
        if self._arr is None:
            return
        keys, mac, cont, ks, end, conf = self._arr
        self.idx = {int(k): i for i, k in enumerate(keys)}
        self._rows = list(zip(mac, cont, ks, end, conf))
        self._arr = None

    @property
    def cells(self) -> dict:
        """{CellKey: Entry} (materialized: tests and small tables)."""
        return {unpack_key(pk): self._entry(pk) for pk in self.keys()}

    def _row(self, pk: int):
        """The row index of a packed key (None: no window)."""
        if self._arr is not None:
            keys = self._arr[0]
            i = int(np.searchsorted(keys, pk))
            return i if i < len(keys) and int(keys[i]) == pk else None
        return self.idx.get(pk)

    def _entry(self, pk: int) -> Entry:
        e = self._ent.get(pk)
        if e is None:
            i = self._row(pk)
            if self._arr is not None:
                _, mac, cont, ks, end, conf = self._arr
                e = self._decode((mac[i], cont[i], ks[i], end[i], conf[i]))
                if len(self._ent) > 20000:
                    self._ent.clear()
            else:
                e = self._rows[i]
                if not isinstance(e, Entry):
                    e = self._decode(e)
                    self._rows[i] = e
            self._ent[pk] = e
        return e

    def get(self, key: "CellKey | None") -> Entry | None:
        if key is None:
            return None
        pk = pack_key(key)
        return self._entry(pk) if self._row(pk) is not None else None

    @staticmethod
    def _encode(e: Entry) -> tuple:
        m = e.macro
        if m.raw is not None:
            raise ValueError("a table entry holds parameters, not raw masks")
        mac = [0 if m.family == "ds" else 1, m.hop, int(m.jh), m.wait, m.t, m.dd, -1 if m.k is None else m.k, m.tail]
        cont = [[-1, -1, 0]] * 4
        for i, (v, k, dd) in enumerate(m.cont[:4]):
            cont[i] = [VARIANT_IDS[v], k, dd]
        ks = list(e.k_strike) + [-1] * (2 - len(e.k_strike))
        end = list(e.end) + [np.nan] * (4 - len(e.end))
        return mac, cont, ks, end, list(e.conf)

    @staticmethod
    def _decode(row: tuple) -> Entry:
        m, cont, ks, en, conf = row
        cont_t = tuple((_VARIANT_NAMES[int(c[0])], int(c[1]), int(c[2])) for c in cont if c[0] >= 0)
        mac = Macro("ds" if m[0] == 0 else "cl", hop=int(m[1]), jh=bool(m[2]), wait=int(m[3]), t=int(m[4]),
                    dd=int(m[5]), k=None if m[6] < 0 else int(m[6]), tail=int(m[7]), cont=cont_t)
        return Entry(mac, tuple(int(x) for x in ks if x >= 0), tuple(float(x) for x in en if np.isfinite(x)),
                     (int(conf[0]), int(conf[1])))

    def save(self, path) -> None:
        import json
        pks = sorted(self.keys())
        enc = [self._encode(self._entry(pk)) for pk in pks]
        n = len(enc)
        np.savez_compressed(
            path, keys=np.array(pks, np.int64),
            macro=np.array([e[0] for e in enc], np.int16).reshape(n, 8),
            cont=np.array([e[1] for e in enc], np.int16).reshape(n, 4, 3),
            k_strike=np.array([e[2] for e in enc], np.int16).reshape(n, 2),
            end=np.array([e[3] for e in enc], np.float64).reshape(n, 4),
            conf=np.array([e[4] for e in enc], np.int16).reshape(n, 2),
            meta=np.array(json.dumps({"version": VERSION, **self.meta})))

    @classmethod
    def load(cls, path=None) -> "Table":
        """The table file (default: the knowledge file TABLE_PATH); entries decoded on first use."""
        import json
        z = np.load(TABLE_PATH if path is None else path)
        meta = json.loads(str(z["meta"])) if "meta" in z.files else {}
        if meta.get("version", VERSION) not in VERSIONS_OK:
            raise ValueError(f"table version {meta.get('version')} not in {VERSIONS_OK}")
        T = cls(meta=meta)
        keys = np.asarray(z["keys"], np.int64)
        mac, ks, end = z["macro"], z["k_strike"], z["end"]
        cont = z["cont"] if "cont" in z.files else np.full((len(keys), 4, 3), -1, np.int16)
        conf = z["conf"] if "conf" in z.files else np.ones((len(keys), 2), np.int16)
        o = np.argsort(keys, kind="stable")
        if not np.all(o == np.arange(len(keys))):
            keys, mac, cont, ks, end, conf = keys[o], mac[o], cont[o], ks[o], end[o], conf[o]
        T._arr = (keys, mac, cont, ks, end, conf)
        return T

    def lookup(self, S: np.ndarray, obs: list, lead: int = 0) -> list:
        """[(o, window, key, entry)] for every Clapper o and window type anchored at its state at frame `lead`
        (her state S must be her predicted state at that frame)."""
        out = []
        for o in obs:
            j = int(o.j or 0) + lead
            for wt in windows_for(o.st, j):
                key = cell_of(S, replace(o, j=j), wt)
                e = self.get(key)
                if e is not None:
                    out.append((o, wt, key, e))
        return out



# ---- the runtime layer (behind SSBOT_FORUM_REFLEX; NOT wired: after M4's gate it goes on top of Map2Controller.pre()) --
#
# THE PLAN FOR M4'S CONTROLLER (ssbot/map2/live.py Map2Controller on the M4 branch as of its S1; no edit there yet).
#  A. THE TICK (_pre, after the hit / freeze / unsafe drops, before '1. commit'):
#   - a Press running (self.rx): her hit, a freeze, the supervisor's keys, the end of its frames, or Press.status(fo,
#     contact, ctrl_seen, dx_seen) giving a reason ends it (hand back, own falls to the fallback); else
#     Press.cmd_at(f + 2, ctrl_seen, dx_seen) is the tick's mask (own 'reflex'; None: it ended). ctrl_seen = the
#     Clawline's control as the S1 feed finds it (self._claw_ctl: the first frame >= P + 3 accepting input, no Harpoon
#     clip); dx_seen = (her x - the target's x) x Press.d at that frame (the STATE hero pos, the tracker's Clapper) -
#     the continuation is chosen by her STOP first, the frame second (stage 4: the variants early / near often share
#     their control frame); contact = a down slash hit on Press.iid seen after the press (the tracker's HP fall on it,
#     _triggers' 'landed', or a DownSlash hit event);
#   - else, unless _busy(fo, raw) says 'freeze' / 'no input': Reflex.check(S0, _eff_inflight(fo, f, inflight),
#     _hold_clean(hold_tuple(hold), fo), self.trk.obs(), mems, hazards, fo, f, claw_free=(not _busy_claw(fo, h) and
#     not (self._claw_P is not None and self._claw_ctl is None)), lat_s=lat_s, claw_lock_until=(self._claw_ctl +
#     press.CLAW_LOCK_F if self._claw_ctl is not None else None), intro=(_busy(fo, raw) == 'intro')). inflight = the
#     COMMANDS of fo + 1 .. f + 1 (the reflex latches them through the hold filter from `hold`, the filter's state
#     before them, as commit_check does); a Press drops the plan in control (_drop('reflex')) and its first command is
#     the tick's mask. The reflex goes first: a strike window beats the plan's next keys (the search re-plans every
#     0.25 - 0.6 s; the reflex sees a window the frame it opens).
#  B. post(): own 'reflex' recorded in sent_hist / own_hist like 'm2'; the snapshot's bridge = Press.cmds_from(f + 3,
#   ctrl_seen, dx_seen) (M4c's handover: the fallback plans from the keys actually sent).
#  C. THE COST (the replay, reflex_build report): the lookup and the gates ~0.04 ms p50 / ~0.2 ms p99 on the ticks
#   without a window; THE CHECK (stage 4: always, from her exact state; a closed-loop prediction of every Clapper fresh
#   at fo under the macro's path, the strike re-derived in every outcome) costs tens of ms -> it runs OFF the bot's
#   thread: a reflex worker beside the search workers checks the windows of the frames ahead along the bridge (her
#   states for the next ~8 frames looked up, the windows found checked) and the thread fires a verdict whose frame,
#   cell and inputs (inflight, lat_s, the Clappers' states) match the observation (the lookup + the gates: well under
#   1 ms). Until then Reflex.check runs it in line (the offline replay; a live smoke should cap it: max_cand 1).

M_CLAW = 1 << 4                    # the Clawline button (ssbot.ipc.framing BUTTONS order; live.M_CLAW)
CLAW_PRESS_F = 3                   # the Clawline key and the direction held this many frames from its press (live)
WIN_VALUE = {"down": 10.0, "claw": 4.0}
DRIFT_LAT = 3                      # (stage 4) a Clawline continuation's drift key from control + 3 when the hook
#                                    variants' drifts differ (control is seen 1 - 2 frames late, keys land at f + 2)
STOP_TOL = 0.5                     # u: her stop at control within this of a variant's stop picks that variant (the
#                                    variants stop 0.8 / 1.7 / 2.5 u short: half their spacing); farther: the press ends
CTRL_LATE = 36                     # a Clawline press with no control seen by P + 36 ends (the model's control <= P + 34)
EXIT_H, EXIT_H_MAX = 40, 180       # the exit check's horizon after a macro (to a big rune's end, at most 180 f)
LOW_HP_CL = sk.CLAW_DMG + sk.DS_DMG    # a target this low is not taken by a Clawline window (its hook / slash kills it:
#                                         the pull and control after a killing needle are not in the model)
SOLO_ONLY = ("evade_claw", "cast_claw")   # the HOOK-ONLY windows: taken only with no other Clapper alive - their safety
#                                    rests on the other Clapper's closed-loop reaction to her pull and bounce, and the
#                                    check and the replay's judge (observations 1 - 2 frames apart) disagreed with two
#                                    Clappers: evade 150 / 215 (alone 91 / 92), cast 328 / 360 (332 / 333) at lead 2; the
#                                    judge itself as the check from fo: evade 6 / 10, cast 339 / 370 at lead 1 (442 / 443)


def _jit(f):
    try:
        from numba import njit
        return njit(cache=True)(f)
    except Exception:  # noqa: BLE001
        return f


def pick_alt(alts: dict, ctrl, dx=None):
    """The Clawline continuation the runtime plays for the control frame and stop she shows: (variant, alt) with alt =
    (control, stop dx, ...) - the variant whose stop is nearest (STOP_TOL; None: none explains it, the press ends),
    the control frame breaking ties; without a stop, the nearest control frame (Press.cmd_at's fallback)."""
    if not alts:
        return None
    items = list(alts.items())
    if dx is not None:
        best = min(items, key=lambda a: (abs(float(a[1][1]) - float(dx)), abs(int(a[1][0]) - int(ctrl))))
        return best if abs(float(best[1][1]) - float(dx)) <= STOP_TOL else None
    return min(items, key=lambda a: abs(int(a[1][0]) - int(ctrl)))


@dataclass
class Press:
    """A window taken: its commands from frame f0 (the frame of its first key: the tick's f + 2) - the macro's latched
    masks, the Clawline key + direction for CLAW_PRESS_F frames from its press - to its last frame `end`; a Clawline
    window's continuation per hook variant (alts: variant -> (its control frame, her stop dx at it (her x - the target's
    x, times d), the commands of the frames from base on, the down slash frame k, the drift)): after control the
    variant her stop matches plays (pick_alt). Frames absolute (the bot's STATE frames). status() ends it when what
    happens leaves its model (no contact by the slash's last active frame + 1, no control by P + CTRL_LATE, a stop no
    variant explains)."""
    window: str
    iid: int
    key: CellKey
    macro: Macro
    conf: tuple
    f0: int
    cmds: np.ndarray
    end: int
    k_strike: tuple
    alts: dict = field(default_factory=dict)
    base: int = 0
    value: float = 0.0
    ms: float = 0.0
    d: int = 1                     # the target's side (+1: to her right) - the Clawline's direction
    t_abs: int | None = None       # a down slash macro: its press frame
    p_abs: int | None = None       # a Clawline macro: its press frame P
    drift: bool = False            # the variants' continuations share their drift key: it is sent through the block
    strike: str = "down"
    ended: str | None = None

    def pick(self, ctrl_seen, dx_seen=None):
        return pick_alt(self.alts, ctrl_seen, dx_seen)

    def ref_rel(self) -> dict:
        """The alts with frames from the macro's frame 0 (= f0 - 1): {variant: (control, stop dx, None, k, dd)}."""
        b = self.f0 - 1
        return {v: (a[0] - b, a[1], None, None if a[3] is None else a[3] - b, a[4]) for v, a in self.alts.items()}

    def status(self, fo: int, contact: bool = False, ctrl_seen: int | None = None, dx_seen: float | None = None):
        """None while the press runs as modelled, else why it ends (recorded: cmd_at returns None from then on)."""
        if self.ended is not None:
            return self.ended
        fo = int(fo)
        if self.t_abs is not None:
            if not contact and fo > self.t_abs + sk.DS_ACTIVE[1] + 1:
                self.ended = "no contact"
        elif self.p_abs is not None:
            if ctrl_seen is None:
                if fo > self.p_abs + CTRL_LATE:
                    self.ended = "no control"
            elif self.alts:
                a = self.pick(ctrl_seen, dx_seen)
                if a is None:
                    self.ended = "off model"
                elif self.strike == "down" and a[1][3] is not None and not contact and \
                        fo > a[1][3] + sk.DS_ACTIVE[1] + 1:
                    self.ended = "no contact"
        return self.ended

    def cmd_at(self, k: int, ctrl_seen: int | None = None, dx_seen: float | None = None) -> int | None:
        """The command for frame k (None: the press is over). A Clawline press: after the Clawline key's frames no
        key until control (the drift key when every variant's continuation has the same one), then the continuation
        of the variant her stop picks (its drift not before control + DRIFT_LAT when the variants' drifts differ)."""
        if self.ended is not None or k > self.end:
            return None
        i = k - self.f0
        if 0 <= i < len(self.cmds):
            return int(self.cmds[i])
        if not self.alts:
            return 0
        q = k - self.base
        if ctrl_seen is None or k <= ctrl_seen:
            if self.drift:
                post = next(iter(self.alts.values()))[2]
                return int(post[q]) & DIRS if 0 <= q < len(post) else 0
            return 0
        a = self.pick(ctrl_seen, dx_seen)
        if a is None:
            self.ended = "off model"
            return None
        post = a[1][2]
        v = int(post[q]) if 0 <= q < len(post) else 0
        if not self.drift and k < ctrl_seen + DRIFT_LAT:
            v &= ~DIRS
        return v

    def cmds_from(self, k: int, ctrl_seen=None, dx_seen=None) -> np.ndarray:
        return np.array([self.cmd_at(kk, ctrl_seen, dx_seen) or 0 for kk in range(k, self.end + 1)], np.int64)


@dataclass
class _World:
    fo0: int
    T: int
    views: list
    p: np.ndarray
    key: tuple


class Reflex:
    """THE PER-FRAME REFLEX (behind SSBOT_FORUM_REFLEX, default off; nothing in the bot imports it yet). Each tick,
    before map2's plan and the fallback planner (check):
      0. the gates before anything: a Clapper in its intro (cm.INTRO; or the caller's intro), a Clawline latched now
         (lat_s) or among the keys in flight -> no press;
      1. her state at the frame before the first key it could send (f + 1: the keys in flight LATCHED through the hold
         filter from `hold` and rolled - the oracle applies a tick's keys at f + 2) and every Clapper's state and frame
         at that frame (the observation advanced);
      2. the table looked up (a binary search per anchored window type) -> candidate windows;
      3. the cheap gates: the attack ready by the press (a down slash), the Clawline free and past the previous one's
         lock (control + 13), not at a target its needle / dash can kill (LOW_HP_CL), a hook-only window only with no
         other Clapper alive (SOLO_ONLY), the macro latched unchanged by the hold filter after the keys in flight;
      4. THE CHECK - always (stage 4: the table's cells are judged at their corners at one physics phase, on a template
         Clapper, with the target alone: they are candidates, not verdicts), from her exact state:
         A (cheap) a down slash window: the robust contact in the window's target states in every consistent view of
           the reflex's prediction and no collision over the macro; a Clawline window: the target alone predicted at fo,
           each hook variant's stop, control and own continuation in its most probable view (the reference stops the
           Press picks by);
         B (authoritative) every Clapper and the leftover hazards predicted FRESH at fo in closed loop under the
           macro's path (her inflight frames, then the macro; to the exit's horizon, a big rune's end included), and in
           EVERY outcome (branch x timing view): the strike re-derived there (the down slash's robust contact and the
           slash's start; a Clawline's hook, the continuation the runtime would pick for that stop, simulated), the
           target state at the strike, no collision with anything (the target included: the hooked body harmless only
           in its measured window), an exit after the macro (the exit check's probes, 40 f / to a big rune's end);
      5. the best window that passes (the strike value, the earliest strike, a full cell before a partial one, the
         fewest frames) -> a Press, else None."""

    def __init__(self, table: Table, W=None, lead: int | None = None, max_cand: int = 1, check: bool = True,
                 T: int = 120, tol_j: int = 1, tol_x: float = 0.35, cl_partial: bool = True,
                 types: tuple | None = None, cl_ready: bool = False):
        self.table = table
        # task oldwin stage N (ssbot.map2.oldwin_press; the defaults: as before): types - only these window types are
        # looked up (None: every generated one); cl_ready - a Clawline window only when her state on the frame before
        # its press is in normal control with no attack / recoil under way (oldwin stage L's live H1: a Clawline pressed
        # inside a side slash's attack lock never fired - the hook model starts it regardless)
        self.types = None if types is None else frozenset(types)
        self.cl_ready = bool(cl_ready)
        self.W = W
        self.lead = lead
        self.max_cand = max_cand                   # candidates checked per tick (the best first; cost: one check)
        self.do_check = check
        self.cl_partial = cl_partial               # a Clawline window's PARTIAL cell taken (stage 4: on - every press
        #                                            is checked from her exact state; off: full cells only)
        self.T, self.tol_j, self.tol_x = T, tol_j, tol_x
        self.world: _World | None = None
        self.stats: Counter = Counter()
        self.ms: dict = defaultdict(lambda: deque(maxlen=50000))     # the recent times per kind (ms)
        self.last: dict = {}

    # ---- the prediction (the check's cheap step A for down slash windows) ----
    def _consistent(self, w: _World, n: int, obs: list) -> list:
        """Indices of the world's views whose Clappers at frame n match the observation (TickCheck's rule)."""
        out = []
        for i, v in enumerate(w.views):
            ok = True
            for o in obs:
                st = sk.state_at(v, o.iid, n)
                if st is None:
                    st = _state_near(v, o.iid, n)
                if st is None or st[0] != o.st or abs(int(st[1]) - int(o.j or 0)) > self.tol_j or \
                        abs(float(st[2]) - o.x) > self.tol_x:
                    ok = False
                    break
            if ok:
                out.append(i)
        return out

    def set_world(self, P, fo0: int) -> None:
        """An outside prediction of the Clappers (cm.Prediction made at the observation frame fo0 - M4's search
        workers predict for every snapshot): step A's world while it stays consistent."""
        from ssbot.map2 import search as ms
        views, p = [], []
        for b in P.branches:
            vs = ms.timing_views(b)
            for v in vs:
                views.append(v)
                p.append(b.p / len(vs))
                v.__dict__["_rx_branch"] = id(b)
                ms.geo(v, True)
        key = tuple(sorted({int(i) for b in P.branches for i in b.recs})) if P.branches and \
            getattr(P.branches[0], "recs", None) is not None else None
        self.world = _World(int(fo0), int(P.T), views, np.asarray(p), key)

    def _world(self, obs: list, mems: dict, hazards: list, fo: int, her_xy, T_need: int = 0, S0=None) -> tuple:
        """(world, consistent view indices, frame n in it): the cached prediction if still consistent and long enough
        (T_need frames from fo), else a new one from the observation."""
        from ssbot.map2 import clapper_jit as cj
        from ssbot.map2 import search as ms
        key = tuple(sorted(o.iid for o in obs))
        w = self.world
        if w is not None and (w.key is None or w.key == key) and fo - w.fo0 + max(70, T_need) <= w.T:
            n = fo - w.fo0
            idx = self._consistent(w, n, obs)
            if idx:
                return w, idx, n
        t0 = time.perf_counter()
        T = max(self.T, T_need + 2)
        path = cm.HeroPath.constant(float(her_xy[0]), float(her_xy[1]), T=T,
                                    steps=None if S0 is None else clapper_steps(self.W, S0, T))
        P = cj.predict(list(obs), {o.iid: (mems or {}).get(o.iid) or cm.Memory() for o in obs}, path, self.W.K,
                       T=T, hazards=list(hazards or ()))
        views, p = [], []
        for b in P.branches:
            vs = ms.timing_views(b)
            for v in vs:
                views.append(v)
                p.append(b.p / len(vs))
                v.__dict__["_rx_branch"] = id(b)
        for v in views:                            # the geometry now (the checks' first use would build it)
            ms.geo(v, True)
        w = _World(int(fo), int(P.T), views, np.asarray(p), key)
        self.world = w
        self.stats["refresh"] += 1
        self.ms["refresh"].append((time.perf_counter() - t0) * 1e3)
        idx = self._consistent(w, 0, obs) or list(range(len(views)))
        return w, idx, 0

    # ---- the tick ----
    def check(self, S0: np.ndarray, inflight, hold, obs: list, mems: dict | None, hazards: list | None, fo: int,
              f: int, claw_free: bool = True, lat_s: int = 0, claw_lock_until: int | None = None,
              intro: bool = False, inflight_latched: bool = False, bridge: int = 0) -> Press | None:
        """The Press to take now (the class docstring), or None. S0: her kin state at the observation frame fo;
        inflight: the COMMANDS of frames fo + 1 .. f + 1 (inflight_latched: already latched - then `hold` is the hold
        filter's state AFTER them); hold: the filter's state (km.HoldState or the live hold tuple) before them; obs /
        mems / hazards: the tracker's Clappers (Obs, Memory) and the leftover hazards; lat_s: the latched mask at fo;
        claw_lock_until: the first frame a Clawline may be pressed (the previous one's control + 13; None: free);
        intro: the caller's tracker sees a Clapper in its intro. bridge (task oldwin stage N): the last `bridge` frames of
        `inflight` are keys not sent yet (the caller's planned bridge to the press): step B checks her collisions from
        the bridge's first frame (0: from the macro's first frame, as before)."""
        t0 = time.perf_counter()
        self.last = {"f": int(f)}
        S0 = np.asarray(S0, float).reshape(km.K, -1)[:, 0]
        inflight = np.asarray(inflight if inflight is not None else (), np.int64).reshape(-1)
        lead = int(f) + 1 - int(fo) if self.lead is None else int(self.lead)
        self.stats["ticks"] += 1
        # 0. the gates before the lookup
        why0 = None
        if intro or any(o.st in cm.INTRO for o in obs if o.st is not None and o.hp > 0):
            why0 = "intro"                         # a Clapper dropping in / roaring: its body and its first move are
            #                                        not in any check (the replay's obs had them removed)
        elif (int(lat_s) & M_CLAW) or bool(np.any(inflight & M_CLAW)):
            why0 = "in a Clawline"                 # her Clawline latched now or on its way: no control, its hook
            #                                        takes her away (M4's commit_check rejects the same)
        if why0 is not None:
            self.stats[why0] += 1
            self.last["why"] = [why0]
            self.ms["tick"].append((time.perf_counter() - t0) * 1e3)
            return None
        # 1. her state at f + 1: the keys in flight as the oracle latches them
        if hold is not None and len(inflight) and not inflight_latched:
            lat_inf = _hold_run(inflight, hold)
        else:
            lat_inf = inflight
        S = self.W.roll(S0, lat_inf).final[:, 0] if len(lat_inf) else S0
        live = [o for o in obs if o.st is not None and o.hp > 0 and o.st not in cm.DEAD]
        # 2. the lookup (cheap: no prediction unless a window opens)
        hits = []
        for o in live:
            j = int(o.j or 0) + lead
            for wt in windows_for(o.st, j):
                if self.types is not None and wt.name not in self.types:
                    continue
                o2 = replace(o, j=j, x=o.x + float(o.vx) * lead / 60.0)
                key = cell_of(S, o2, wt)
                e = self.table.get(key)
                if e is not None:
                    hits.append((o, o2, wt, key, e))
        if not hits:
            self.ms["tick"].append((time.perf_counter() - t0) * 1e3)
            return None
        self.stats["hits"] += 1
        hits.sort(key=lambda h: (-_value(h[2]), h[4].k_strike[0] if h[4].k_strike else 999,
                                 h[4].conf[0] < h[4].conf[1], _n_frames(h[4].macro)))
        out = None
        why = []
        n_checked = 0
        for (o, o2, wt, key, e) in hits:
            if n_checked >= self.max_cand:
                why.append("cap")
                break
            d = 1 if o2.x >= float(S[km.PX]) else -1
            raw = render(e.macro, d)
            # 3. the gates
            if e.macro.family == "cl":
                if not claw_free:
                    why.append("claw busy")
                    continue
                if claw_lock_until is not None and int(f) + 1 + len(raw.pre) < int(claw_lock_until):
                    why.append("claw lock")            # a Clawline before the previous one's control + 13 is lost
                    continue
                if not self.cl_partial and e.conf[0] < e.conf[1]:
                    why.append("cl partial")
                    continue
                if int(o.hp) <= LOW_HP_CL:
                    why.append("cl low hp")
                    continue
                if wt.name in SOLO_ONLY and len(live) > 1:
                    why.append("solo only")            # (stage 4) the model cannot vouch for it with another Clapper
                    continue
                if self.cl_ready and not _cl_ready(self.W, S, raw):
                    why.append("claw attack")          # (oldwin stage N) an attack / recoil at the press: eaten live
                    continue
            elif float(S[km.ATK_CD]) > (e.macro.t - 1) / 60.0 + 1e-6:
                why.append("attack")
                continue
            if hold is not None and not _hold_ok(raw.pre, np.zeros(0, np.int64) if inflight_latched else inflight,
                                                 hold):
                why.append("hold")
                continue
            # 4. the check
            info = None
            if self.do_check:
                n_checked += 1
                tc = time.perf_counter()
                ok, r, info = self._check(S0, lat_inf, S, lead, int(fo), live, mems, hazards, o, wt, e.macro, d,
                                          k_lo=(lead + 1 - int(bridge)) if bridge else None)
                self.ms["check"].append((time.perf_counter() - tc) * 1e3)
                if not ok:
                    why.append(r)
                    self.stats["check_fail"] += 1
                    self.stats["check_fail_" + r.split(":")[0]] += 1
                    continue
            else:
                if e.macro.family == "cl":
                    info = _ctrls(self.W, S, o2, e.macro, d)
                self.stats["check_skipped"] += 1
            out = _press(e, wt, o, key, raw, d, int(f) + 2, (time.perf_counter() - t0) * 1e3, info)
            break
        self.last.update(hits=[(h[2].name, h[0].iid, h[4].conf[0] == h[4].conf[1]) for h in hits], why=why,
                         press=None if out is None else out.window)
        self.stats["press" if out is not None else "no_press"] += 1
        self.ms["tick"].append((time.perf_counter() - t0) * 1e3)
        return out

    def _check(self, S0, lat_inf, S, lead: int, fo: int, live: list, mems, hazards, o, wt: Window, m: Macro,
               d: int, k_lo: int | None = None) -> tuple:
        """(ok, why, info): steps A and B of the check (the class docstring); info: a Clawline window's (reference
        stops per variant, the drift latency)."""
        her0 = (float(S0[km.PX]), float(S0[km.PY]))
        if m.family == "ds":
            raw = render(m, d)
            if not swings(self.W, S, raw):
                return False, "noswing", None
            w, idx, n = self._world(live, mems, hazards, fo, her0, T_need=lead + len(raw.pre) + 2, S0=S0)
            ok, r, _, paths = _check_ds(self.W, w, idx, n + lead, S, o.iid, wt, m, d)
            if not ok:
                return False, "A:" + r, None
            ok, r = _closed_ds(self.W, S0, lat_inf, S, lead, live, mems, hazards, o, wt, m, d, paths, k_lo)
            return ok, r, None
        tw_ = time.perf_counter()
        w = _target_world(self.W, o, mems, hazards, fo, her0, self.T, S0)
        self.ms["refresh_target"].append((time.perf_counter() - tw_) * 1e3)
        ok, r, info, paths = _check_cl(self.W, w, lead, S, o, wt, m, d)
        if not ok:
            return False, "A:" + r, None
        ok, r = _closed_cl(self.W, S0, lat_inf, S, lead, live, mems, hazards, o, wt, m, d, info, paths, k_lo)
        return ok, r, info

    def candidates(self, S_pred: np.ndarray, obs: list, hold=None, claw_free: bool = True) -> list:
        """[(o, window, key, entry, commands)] of the windows open for her predicted state S_pred (the frame before the
        first key; obs at the observation frame, advanced by self.lead or 1) that pass the cheap gates (stage 1's)."""
        out = []
        for (o, wt, key, e) in self.table.lookup(S_pred, obs, self.lead or 1):
            d = 1 if o.x >= float(S_pred[km.PX]) else -1
            raw = render(e.macro, d)
            if e.macro.family == "cl":
                if not claw_free:
                    continue
            elif float(S_pred[km.ATK_CD]) > (e.macro.t - 1) / 60.0 + 1e-6:
                continue                                      # the attack would not be ready at the press
            if hold is not None and not _hold_ok(raw.pre, np.zeros(0, np.int64), hold):
                continue                                      # the filter would change it (a key held / just pressed)
            out.append((o, wt, key, e, raw.pre))
        return out


def _cl_ready(W, S: np.ndarray, raw: Raw) -> bool:
    """(task oldwin stage N) her state on the frame before a Clawline macro's press (S: the frame before the macro's
    first key, rolled through the macro's keys before the press): normal control, no attack and no recoil under way -
    the game eats a Clawline pressed inside an attack's lock (oldwin stage L's live H1)."""
    n = len(raw.pre)
    Sx = W.roll(S, raw.pre[:n - 1]).final[:, 0] if n > 1 else np.asarray(S, float).reshape(km.K, -1)[:, 0]
    return int(Sx[km.MODE]) == km.M_NORMAL and float(Sx[km.ATTACKING]) <= 0.0 and int(Sx[km.RSTEPS]) <= 0


def _value(wt: Window) -> float:
    return WIN_VALUE["down"] + (WIN_VALUE["claw"] if wt.family == "cl" else 0.0) if wt.strike == "down" else \
        WIN_VALUE["claw"]


def _n_frames(m: Macro) -> int:
    return (m.t + 1 + m.tail) if m.family == "ds" else max((k for (_, k, _) in m.cont), default=50) + m.tail


def _hold_tuple(hold):
    if isinstance(hold, km.HoldState):
        return hold
    lat, des, pen, age = hold
    return km.HoldState(np.asarray(lat, bool)[None], np.asarray(des, bool)[None], np.asarray(pen, np.int64)[None],
                        np.asarray(age, np.int64)[None])


def _hold_run(cmds: np.ndarray, hold) -> np.ndarray:
    """The commands latched by the oracle's hold filter from its state `hold` (kinematics.hold_filter, one lane)."""
    h = _hold_tuple(hold)
    return _hold1(np.asarray(cmds, np.int64), h.latched[0].copy(), h.desired[0].copy(),
                  h.pending[0].astype(np.int64).copy(), h.age[0].astype(np.int64).copy(), km.N_BUTTONS, 2, 2, 3,
                  int(km._AGE_LONG), int(np.log2(km.B_LEFT)), int(np.log2(km.B_RIGHT)))


def _hold_ok(pre: np.ndarray, inflight: np.ndarray, hold) -> bool:
    """The macro's masks latched unchanged by the oracle's hold filter after the keys in flight
    (kinematics.hold_filter, one lane, compiled: _hold1)."""
    cmds = np.concatenate([np.asarray(inflight, np.int64), np.asarray(pre, np.int64)])
    lat = _hold_run(cmds, hold)
    return bool(np.array_equal(lat[len(inflight):], np.asarray(pre, np.int64)))


@_jit
def _hold1(cmds, latched, desired, pending, age, nb, min_press, min_release, max_pending, age_long, lb, rb_):
    """kinematics.hold_filter for one lane (the same steps, compiled)."""
    T = cmds.shape[0]
    out = np.zeros(T, np.int64)
    for t in range(T):
        nxt = latched.copy()
        prs = np.zeros(nb, np.bool_)
        for b in range(nb):
            want = ((cmds[t] >> b) & 1) == 1
            if want != desired[b]:
                pending[b] += 1
            desired[b] = want
            if pending[b] > max_pending:
                pending[b] -= 2
            has = pending[b] > 0
            if has and latched[b] and age[b] >= min_press:
                nxt[b] = False
                pending[b] -= 1
            elif has and (not latched[b]) and age[b] >= min_release:
                nxt[b] = True
                prs[b] = True
                pending[b] -= 1
        if nxt[lb] and nxt[rb_]:
            for b in (lb, rb_):
                if prs[b]:
                    nxt[b] = False
                    pending[b] += 1
                    if not desired[b]:
                        pending[b] = 0
        m = 0
        for b in range(nb):
            if nxt[b] != latched[b]:
                age[b] = 1
            else:
                age[b] = min(age[b] + 1, age_long)
            latched[b] = nxt[b]
            if latched[b]:
                m |= (1 << b)
        out[t] = m
    return out


def _press(e: Entry, wt: Window, o, key: CellKey, raw: Raw, d: int, f0: int, ms_: float, info) -> Press:
    """The commands of the window's macro with its frame 1 at f0 (its frame k at f0 - 1 + k). info: a Clawline
    window's (reference stops per variant {variant: (control, stop dx, None, k, dd)} from the macro's frame 0, the drift
    latency)."""
    m = e.macro
    b = f0 - 1
    ks = tuple(b + k for k in e.k_strike)
    if not raw.claw:
        cmds = np.asarray(raw.pre, np.int64).copy()
        t = raw.ds[0] if raw.ds else 1
        return Press(wt.name, o.iid, key, m, e.conf, f0, cmds, b + len(cmds), ks, {}, 0, _value(wt), ms_, d=d,
                     t_abs=b + t, strike=wt.strike)
    n = len(raw.pre)
    cmds = np.zeros(n - 1 + CLAW_PRESS_F, np.int64)
    cmds[:n] = raw.pre
    dk = km.B_RIGHT if raw.claw > 0 else km.B_LEFT
    for jj in range(CLAW_PRESS_F):
        cmds[n - 1 + jj] = M_CLAW | dk             # the Clawline key with the direction from its press (frame n)
    ref, dlat = info if info else ({}, 0)
    alts = {}
    for (v, k, dd) in m.cont:
        c, dx = (ref.get(v) or (n + 26, 0.0))[:2]
        alts[v] = (b + int(c), float(dx), _cl_post(n, k, d * dd, m.tail), b + int(k), int(dd))
    last = max((k for (_, k, _) in m.cont), default=n + CL_HOOK_END - m.tail - 1)
    drift = bool(alts) and dlat == 0
    return Press(wt.name, o.iid, key, m, e.conf, f0, cmds, b + last + m.tail + 1, ks, alts, b + n + 1, _value(wt), ms_,
                 d=int(raw.claw), p_abs=b + n, drift=drift, strike=wt.strike)


def _check_ds(W, w: _World, idx: list, n0: int, S: np.ndarray, iid: int, wt: Window, m: Macro, d: int) -> tuple:
    """Step A of a down slash window's check: from her state S at the views' frame n0, the macro's robust contact in
    the window's target states in every consistent view of the reflex's (cached) prediction and no collision over its
    frames in any (all Clappers, hazards, walls). (ok, why, None, the paths per contact frame: (pos, ifr, c))."""
    from ssbot.map2 import reflex_gen as rg
    raw = render(m, d)
    masks = raw.pre
    n = len(masks)
    t = raw.ds[0]
    if n0 + n >= w.T:
        return False, "horizon", None, []
    r = W.roll(S, masks)
    face = rg._facing(np.array([int(S[km.FACE]) if S[km.FACE] != 0 else 1]), masks[None])
    gnd = (r.flags & km.F_GROUND) != 0
    Bs = np.stack([_rb(v, iid, w.T) for v in (w.views[i] for i in idx)])
    cs = rg.contacts(r.pos, face, gnd, np.array([t]), np.array([n]), Bs, np.array([n0]))[0]
    if (cs < 0).any():
        return False, "miss", None, []
    rolled = {}
    paths = []
    for c, i in zip(cs, idx):
        v = w.views[i]
        c = int(c)
        if not _in_target(v, iid, n0 + c, wt.target):
            return False, "tgt", None, []
        rb = rolled.get(c)
        if rb is None:
            ev = np.zeros(n, np.int64)
            ev[c - 1] |= km.EV_POGO
            rb = W.roll(S, masks, ev)
            rolled[c] = rb
            ifr_r = np.zeros(n + 1, bool)
            ifr_r[c + sk.DS_IFR[0]:c + sk.DS_IFR[1] + 1] = True
            paths.append((rb.pos[0, :n + 1].copy(), ifr_r, c))
        pos = np.zeros((n0 + n + 1, 2))
        pos[n0:] = rb.pos[0, :n + 1]
        ifr = np.zeros(n0 + n + 1, bool)
        ifr[n0 + c + sk.DS_IFR[0]:n0 + c + sk.DS_IFR[1] + 1] = True
        kc = _collision(v, pos, ifr, [], n0 + 1, n0 + n, None)
        if kc is not None:
            return False, f"hit@{kc - n0}", None, []
    return True, "", None, paths


def _pre_pos(W, S0: np.ndarray, lat_inf: np.ndarray, lead: int) -> np.ndarray:
    """Her transform at fo .. fo + lead (= f + 1) under the keys in flight ([lead + 1, 2])."""
    if len(lat_inf):
        r = W.roll(S0, np.asarray(lat_inf, np.int64)[:lead])
        pos = r.pos[0, :lead + 1]
        if len(pos) < lead + 1:
            pos = np.concatenate([pos, np.repeat(pos[-1:], lead + 1 - len(pos), axis=0)])
        return pos
    return np.repeat(np.array([[float(S0[km.PX]), float(S0[km.PY])]]), lead + 1, axis=0)


def _exit_h(v, k_end: int, T: int) -> int:
    """The exit check's horizon from frame k_end of a view: 40 f, to a big rune's end (at most 180 f), never past the
    prediction's horizon T (search.branch_danger sees nothing there: _predict_closed predicts far enough)."""
    from ssbot.map2 import search as ms
    H = EXIT_H
    re_ = ms.rune_end(v)
    if re_ is not None and re_ > k_end + H:
        H = min(re_ - k_end + 2, EXIT_H_MAX)
    return max(min(H, T - k_end), 1)


def _predict_closed(W, pre: np.ndarray, pos_m: np.ndarray, lead: int, live: list, mems, hazards, S0,
                    hits: dict | None = None):
    """Every Clapper (and the leftover hazards) predicted at fo in closed loop under her path - the keys in flight's
    frames (pre), then the macro's (pos_m, from its frame 0 = f + 1) and its hits on the Clappers (hits: {iid: {macro
    frame: (kind, damage)}}: their reactions, as the judge's cascade has them) - far enough for the exit check after it
    (40 f, to a big rune's end lit in the prediction, at most 180 f); the physics steps from her state S0 at fo."""
    hk = {i: {lead + int(k): v for k, v in h.items()} for i, h in (hits or {}).items()}
    from ssbot.map2 import clapper_jit as cj
    from ssbot.map2 import search as ms
    L = len(pos_m) - 1
    k_end = lead + L

    def run(T):
        x = np.full(T + 1, float(pos_m[-1, 0]))
        y = np.full(T + 1, float(pos_m[-1, 1]))
        x[:lead + 1] = pre[:lead + 1, 0]
        y[:lead + 1] = pre[:lead + 1, 1]
        x[lead:lead + L + 1] = pos_m[:, 0]
        y[lead:lead + L + 1] = pos_m[:, 1]
        box = np.stack([x - sk.HALF_W, y - sk.FOOT, x + sk.HALF_W, y - sk.FOOT + 2 * sk.HALF_H], axis=1)
        return cj.predict(list(live), {o.iid: (mems or {}).get(o.iid) or cm.Memory() for o in live},
                          cm.HeroPath(x, y, box, {i: dict(h) for i, h in hk.items()}, clapper_steps(W, S0, T)), W.K,
                          T=T, hazards=list(hazards or ()))
    T = k_end + EXIT_H + 2
    P = run(T)
    re_ = max((r for b in P.branches for v in ms.timing_views(b) for r in (ms.rune_end(v),) if r is not None),
              default=None)
    if re_ is not None and re_ > k_end + EXIT_H:
        P = run(min(re_ + 4, k_end + EXIT_H_MAX + 2))
    return P


# (stage 4) A KILLING DOWN SLASH BOUNCES HER: of 541 killing down slashes in the recordings (fit / held / old) 77.6 %
# rise > 1 u in their first 15 moving frames (p50 2.27 u; the rest the wave's last kill in its slow motion), 98.7 % of
# 12,765 others (p50 2.66 u) - reflex s4/kill_bounce. The model drops a killed target's box at once, so its contact (and
# the bounce) vanished and a kill counted as a miss in the judge: the judge and the check keep the target ALIVE through
# its hit (hp raised to KILL_HP - the model reads hp only for the death): the bounce as live, the target's later danger
# kept (conservative).
KILL_HP = 230


def _closed_ds(W, S0, lat_inf, S, lead: int, live: list, mems, hazards, o, wt: Window, m: Macro, d: int,
               paths: list, k_lo: int | None = None) -> tuple:
    """Step B of a down slash window's check (the Reflex docstring): per step A path (one per contact frame), every
    Clapper predicted fresh at fo under it; in every outcome the robust contact re-derived, in the window's target
    states, the bounce rolled from it (a killing slash bounces too: KILL_HP), no collision with anything over the
    macro, an exit after it. (ok, why)."""
    from ssbot.map2 import reflex_gen as rg
    from ssbot.map2 import search as ms
    iid = o.iid
    raw = render(m, d)
    masks = raw.pre
    n = len(masks)
    t = raw.ds[0]
    r0 = W.roll(S, masks)
    face = rg._facing(np.array([int(S[km.FACE]) if S[km.FACE] != 0 else 1]), masks[None])
    gnd = (r0.flags & km.F_GROUND) != 0
    pre = _pre_pos(W, S0, lat_inf, lead)
    live = [replace(x, hp=max(int(x.hp), KILL_HP)) if x.iid == iid else x for x in live]   # (a killing slash bounces)
    rolled = {}
    for (pos_nom, _, c_nom) in paths[:2]:
        P = _predict_closed(W, pre, pos_nom, lead, live, mems, hazards, S0, {iid: {int(c_nom): ("down", sk.DS_DMG)}})
        for b in P.branches:
            for v in ms.timing_views(b):
                B = _rb(v, iid, P.T)
                c = int(rg.contacts(r0.pos, face, gnd, np.array([t]), np.array([n]), B[None], np.array([lead]))[0, 0])
                if c < 0:
                    return False, "B:miss"
                if not _in_target(v, iid, lead + c, wt.target):
                    return False, "B:tgt"
                rb = rolled.get(c)
                if rb is None:
                    ev = np.zeros(n, np.int64)
                    ev[c - 1] |= km.EV_POGO
                    rb = W.roll(S, masks, ev)
                    rolled[c] = rb
                pos = np.concatenate([pre[:lead], rb.pos[0, :n + 1]])
                ifr = np.zeros(lead + n + 1, bool)
                ifr[lead + c + sk.DS_IFR[0]:lead + c + sk.DS_IFR[1] + 1] = True
                kc = _collision(v, pos, ifr, [], lead + 1 if k_lo is None else int(k_lo), lead + n, None)
                if kc is not None:
                    return False, f"B:hit@{kc - lead}"
                H = _exit_h(v, lead + n, P.T)
                if not rg._exit(W, None, rb.final[:, 0], lead + n, v, lead + c + sk.DS_IFR[1], H, False):
                    return False, f"B:exit@{n}"
    return True, ""


_VARS = {v.name: v for v in sk.HOOK_VARIANTS + (NEAR, FAR)}


def _cl_names(m: Macro, o) -> list:
    """The hook variants a Clawline window's check plays: its continuations' (a strike window), else every variant the
    judge has for the target (a hook-only window: an evade's far stop too)."""
    return [c[0] for c in m.cont] or [v.name for v in judge_variants(o)]


def _stop_dx(h, br, iid: int, k_off: int = 0) -> float:
    """Her stop at a hook's control relative to the target: (her x - its x) x the Clawline's side (the target's x
    in the view at control)."""
    st = _state_near(br, iid, k_off + int(h.ctrl))
    x_t = float(st[2]) if st is not None else float("nan")
    return (float(h.pos[-1, 0]) - x_t) * int(h.d)


def _check_cl(W, w: _World, n0: int, S: np.ndarray, o, wt: Window, m: Macro, d: int) -> tuple:
    """Step A of a Clawline window's check: the target alone predicted at fo (w), its most probable view: each hook
    variant's stop, control and the continuation it plays (the table's) simulated - the strike must land there.
    (ok, why, (reference stops {variant: (control, stop dx, None, k, dd)} from the macro's frame 0, the drift
    latency), the nominal paths [(variant, her transform per macro frame, her hits per Clapper)])."""
    from ssbot.map2 import search as ms
    iid = o.iid
    best = max(range(len(w.views)), key=lambda i: w.p[i])
    v = w.views[best]
    raw = render(m, d)
    n = len(raw.pre)
    Sp = W.roll(S, raw.pre).final[:, 0]
    alpha_c = int(round(float(S[km.ALPHA]) * 6.0)) % 6
    face0 = int(S[km.FACE]) if S[km.FACE] != 0 else 1
    names = _cl_names(m, o)
    cont = {c[0]: (c[1], c[2]) for c in m.cont}
    dlat = 0 if len({c[2] for c in m.cont}) <= 1 else DRIFT_LAT
    bx = _rb(v, iid, w.T)[n0:]
    bxa = bx if len(bx) >= n + 62 else np.concatenate([bx, np.full((n + 62 - len(bx), 4), np.nan)])
    if o.st not in MOVING:
        # the judge's hook domain (HOOK_HOLD_MAX): a static target's top at the dash (P + 16 .. 19) at least 2.5 u above
        # her box bottom at the press - nearer, the hook's stop is not modelled (the replay's judge refused 18 presses)
        top = float(np.nanmax(bxa[n + 16:n + 20, 3])) if np.isfinite(bxa[n + 16:n + 20, 3]).any() else np.nan
        if np.isfinite(top) and float(Sp[km.PY]) - sk.FOOT - top > HOOK_HOLD_MAX:
            return False, "domain:hold", None, []
    ref = {}
    for vn in names:
        h = sk.claw_hook(Sp, n, raw.claw, iid, bxa, _VARS[vn], alpha_c)
        if not h.ok:
            return False, f"hook:{vn}", None, []
        k, dd = cont.get(vn, (None, 0))
        ref[vn] = (int(h.ctrl), _stop_dx(h, v, iid, n0), None, k, dd)
    paths = []
    with _Robust(True, variants=tuple(_VARS[vn] for vn in names)):
        for vn in names:
            raw2 = render(replace(m, dlat=dlat), d)
            plan = plan_of(raw2, iid, {vn: ref[vn][0]})
            tr = ms.simulate(W, plan, lambda i_: bxa if i_ == iid else None, face0, S, _VARS[vn], alpha_c)
            if wt.strike == "down":
                hit = [kc for (kc, ii, kind) in tr.contacts if kind == "down" and ii == iid]
                if not hit or not _in_target(v, iid, n0 + hit[0], wt.target):
                    return False, f"miss:{vn}", None, []
            elif not any(h.ok and h.iid == iid and _in_target(v, iid, n0 + h.hit, wt.target) for h in tr.hooks):
                return False, f"hook:{vn}", None, []
            paths.append((vn, np.asarray(tr.pos, float).copy(), {i: dict(h) for i, h in tr.hits.items()}))
    return True, "", (ref, dlat), paths


def _closed_cl(W, S0, lat_inf, S, lead: int, live: list, mems, hazards, o, wt: Window, m: Macro, d: int, info,
               paths: list, k_lo: int | None = None) -> tuple:
    """Step B of a Clawline window's check (the Reflex docstring): per hook variant, every Clapper predicted fresh at
    fo under its nominal path; in every outcome that variant's hook on the target's boxes there, the continuation the
    runtime picks for the stop and control it shows (pick_alt over step A's reference stops; none -> the press would
    end: a failure), simulated (its drift from control + DRIFT_LAT when the variants' drifts differ): the strike in
    the window's target states, no collision with anything (the target included; the hooked body harmless from P + 17
    to control + 12), an exit after it. (ok, why)."""
    from ssbot.map2 import reflex_gen as rg
    from ssbot.map2 import search as ms
    ref, dlat = info
    iid = o.iid
    raw = render(m, d)
    n = len(raw.pre)
    Sp = W.roll(S, raw.pre).final[:, 0]
    alpha_c = int(round(float(S[km.ALPHA]) * 6.0)) % 6
    face0 = int(S[km.FACE]) if S[km.FACE] != 0 else 1
    pre = _pre_pos(W, S0, lat_inf, lead)
    live = [replace(x, hp=max(int(x.hp), KILL_HP)) if x.iid == iid else x for x in live]
    with _Robust(True, variants=tuple(_VARS[x[0]] for x in paths)):
        for (vn, pos_nom, hits_nom) in paths:
            P = _predict_closed(W, pre, pos_nom, lead, live, mems, hazards, S0, hits_nom)
            for b in P.branches:
                for v in ms.timing_views(b):
                    bx = _rb(v, iid, P.T)[lead:]
                    bxa = bx if len(bx) >= n + 62 else np.concatenate([bx, np.full((n + 62 - len(bx), 4), np.nan)])
                    h = sk.claw_hook(Sp, n, raw.claw, iid, bxa, _VARS[vn], alpha_c)
                    if not h.ok:
                        return False, f"B:hook:{vn}"
                    if wt.strike == "down":
                        a = pick_alt(ref, h.ctrl, _stop_dx(h, v, iid, lead))
                        if a is None:
                            return False, f"B:off model:{vn}"
                        m2 = replace(m, cont=((vn, int(a[1][3]), int(a[1][4])),), dlat=dlat)
                        plan = plan_of(render(m2, d), iid, {vn: int(h.ctrl)})
                    else:
                        plan = plan_of(raw, iid, {vn: int(h.ctrl)})
                    tr = ms.simulate(W, plan, lambda i_: bxa if i_ == iid else None, face0, S, _VARS[vn], alpha_c)
                    if wt.strike == "down":
                        hit = [kc for (kc, ii, kind) in tr.contacts if kind == "down" and ii == iid]
                        if not hit or not _in_target(v, iid, lead + hit[0], wt.target):
                            return False, f"B:miss:{vn}"
                    elif not any(hh.ok and hh.iid == iid and _in_target(v, iid, lead + hh.hit, wt.target)
                                 for hh in tr.hooks):
                        return False, f"B:hook:{vn}"
                    Lt = len(tr.pos)
                    pos = np.concatenate([pre[:lead], np.asarray(tr.pos, float)])
                    ifr = np.concatenate([np.zeros(lead, bool), np.asarray(tr.ifr, bool)])
                    hk = [_ShiftHook(x, lead) for x in tr.hooks]
                    kc = _collision(v, pos, ifr, hk, lead + 1 if k_lo is None else int(k_lo), lead + Lt - 1, None)
                    if kc is not None:
                        return False, f"B:hit@{kc - lead}:{vn}"
                    st_e = ms.state_at(W, tr, tr.end)
                    if st_e is None:
                        return False, "B:end"
                    iu = max([kc_ + sk.DS_IFR[1] for (kc_, _, kind) in tr.contacts if kind == "down"], default=-1)
                    H = _exit_h(v, lead + tr.end, P.T)
                    if not rg._exit(W, None, st_e[0], lead + tr.end, v, lead + iu if iu >= 0 else -1, H, False):
                        return False, f"B:exit:{vn}"
    return True, ""


def _ctrls(W, S: np.ndarray, o, m: Macro, d: int) -> tuple:
    """A Clawline macro taken without a check (Reflex(check=False)): the reference stops per variant from
    strike.claw_hook on the target's body as observed (its state's box frame by frame from its frame now, moving with
    its observed vx) - (reference stops, drift latency) as _check_cl gives them."""
    raw = render(m, d)
    n = len(raw.pre)
    T = n + 64
    bx = np.full((T, 4), np.nan)
    xs = np.full(T, np.nan)
    for k in range(T):
        try:
            b = W.K.box(o.st, int(o.j or 0) + k)
        except Exception:  # noqa: BLE001
            break
        x = o.x + float(o.vx) * k / 60.0
        xs[k] = x
        xa, xb = x + o.face * b[0], x + o.face * b[1]
        bx[k] = (min(xa, xb), o.y + b[2], max(xa, xb), o.y + b[3])
    Sp = W.roll(S, raw.pre).final[:, 0]
    alpha_c = int(round(float(S[km.ALPHA]) * 6.0)) % 6
    cont = {c[0]: (c[1], c[2]) for c in m.cont}
    out = {}
    for vn in _cl_names(m, o):
        h = sk.claw_hook(Sp, n, raw.claw, o.iid, bx, _VARS[vn], alpha_c)
        c = h.ctrl if h.ok else n + 26
        x_t = xs[min(c, T - 1)] if np.isfinite(xs[min(c, T - 1)]) else o.x
        k, dd = cont.get(vn, (None, 0))
        out[vn] = (int(c), (float(h.pos[-1, 0]) - x_t) * raw.claw if h.ok else 0.0, None, k, dd)
    return out, (0 if len({c[2] for c in m.cont}) <= 1 else DRIFT_LAT)


def _target_world(W, o, mems: dict | None, hazards, fo: int, her_xy, T: int, S0=None) -> "_World":
    """The target Clapper alone predicted from its observation now (her constant path; the physics steps from her
    state at fo): its outcomes' timing views."""
    from ssbot.map2 import clapper_jit as cj
    from ssbot.map2 import search as ms
    path = cm.HeroPath.constant(float(her_xy[0]), float(her_xy[1]), T=T,
                                steps=None if S0 is None else clapper_steps(W, S0, T))
    P = cj.predict([o], {o.iid: (mems or {}).get(o.iid) or cm.Memory()}, path, W.K, T=T, hazards=list(hazards or ()))
    views, p = [], []
    for b in P.branches:
        vs = ms.timing_views(b)
        for v in vs:
            views.append(v)
            p.append(b.p / len(vs))
            v.__dict__["_rx_branch"] = id(b)
    return _World(int(fo), int(P.T), views, np.asarray(p), (o.iid,))


def _rb(v, iid: int, T: int) -> np.ndarray:
    b = sk.robust_boxes(v, iid, T)
    if len(b) < T + 1:
        b = np.concatenate([b, np.full((T + 1 - len(b), 4), np.nan)])
    return b[:T + 1]


def _collision(br, pos, ifr, hooks, k0: int, k1: int, skip_iid=None) -> int | None:
    """search.first_collision (the body boxes, the hazard circles and the walls: brnum.first_hit) with the rare
    shapes - the hammers, grown by their margins - tested compiled (_rare_pack: per view their convex polygons, a
    circle as its 16-gon as clapper.Shape.polygon draws it); skip_iid: that Clapper left out (the table vouches)."""
    from ssbot.map2 import brnum
    from ssbot.map2 import search as ms
    if k1 < k0:
        return None
    g = ms.geo(br, True)
    hk = [(h.iid, h.P + sk.HOOK_BODY_OFF[0], h.ctrl + sk.HOOK_BODY_OFF[1]) for h in hooks if h.ok]
    if skip_iid is not None:
        hk.append((int(skip_iid), k0, k1))
    hki = np.array([x[0] for x in hk], np.int64)
    hlo = np.array([x[1] for x in hk], np.int64)
    hhi = np.array([x[2] for x in hk], np.int64)
    kb, _ = brnum.first_hit(np.ascontiguousarray(pos[:, 0]), np.ascontiguousarray(pos[:, 1]), ifr, k0, k1, g.off,
                            g.BX, g.IIDB, hki, hlo, hhi, ms._HW, ms._HH, ms._HDY, ms.WALL_L, ms.WALL_R, g.coff, g.CO)
    top = kb - 1 if kb >= 0 else k1
    if len(g.rare_k):
        rk, roff, rpoff, rxy, riid = _rare_pack(br, g)
        kr = _rare_first(np.ascontiguousarray(pos[:, 0]), np.ascontiguousarray(pos[:, 1]), ifr, k0, top, rk, roff,
                         rpoff, rxy, riid, -1 if skip_iid is None else int(skip_iid), cm.HURTBOX[0], cm.HURTBOX[1],
                         cm.HURTBOX[2])
        if kr >= 0:
            return kr
    return kb if kb >= 0 else None


def _rare_pack(br, g) -> tuple:
    """The view's rare shapes as arrays (cached on the view): frames rk, per frame its shapes roff[i] .. roff[i + 1],
    per shape its polygon rows rpoff[s] .. rpoff[s + 1] of rxy and its Clapper riid."""
    c = br.__dict__.get("_rxpack")
    if c is not None:
        return c
    rk, roff, rpoff, rxy, riid = [], [0], [0], [], []
    for k in g.rare_k:
        k = int(k)
        shapes = g.rare_grown(br, k, True)
        for x in shapes:
            poly = x.polygon(16) if x.poly is None else x.poly
            rxy.append(np.asarray(poly, float))
            rpoff.append(rpoff[-1] + len(poly))
            riid.append(int(x.iid))
        rk.append(k)
        roff.append(roff[-1] + len(shapes))
    c = (np.array(rk, np.int64), np.array(roff, np.int64), np.array(rpoff, np.int64),
         np.ascontiguousarray(np.concatenate(rxy)) if rxy else np.zeros((0, 2)), np.array(riid, np.int64))
    br.__dict__["_rxpack"] = c
    return c


def _rare_first(px, py, ifr, k0, k1, rk, roff, rpoff, rxy, riid, skip, hw, hh, dy) -> int:
    return _rare_first_jit(px, py, ifr, k0, k1, rk, roff, rpoff, rxy, riid, skip, hw, hh, dy)


@_jit
def _rare_first_jit(px, py, ifr, k0, k1, rk, roff, rpoff, rxy, riid, skip, hw, hh, dy):
    """The first frame k0 .. k1 (her i-frames skipped) where her hurtbox meets a rare shape's polygon (the separating
    axis test, clapper.poly_box_hit), -1 none."""
    for i in range(rk.shape[0]):
        k = rk[i]
        if k < k0 or k > k1 or ifr[k]:
            continue
        x0, y0, x1, y1 = px[k] - hw, py[k] + dy - hh, px[k] + hw, py[k] + dy + hh
        for s_ in range(roff[i], roff[i + 1]):
            if riid[s_] == skip:
                continue
            a, b = rpoff[s_], rpoff[s_ + 1]
            m = b - a
            mnx, mxx, mny, mxy = 1e300, -1e300, 1e300, -1e300
            for q in range(a, b):
                mnx = min(mnx, rxy[q, 0])
                mxx = max(mxx, rxy[q, 0])
                mny = min(mny, rxy[q, 1])
                mxy = max(mxy, rxy[q, 1])
            if mxx <= x0 or mnx >= x1 or mxy <= y0 or mny >= y1:
                continue
            sep = False
            for e in range(m):
                p0 = a + e
                p1 = a + (e + 1) % m
                nx = -(rxy[p1, 1] - rxy[p0, 1])
                ny = rxy[p1, 0] - rxy[p0, 0]
                amin, amax = 1e300, -1e300
                for q in range(a, b):
                    v = rxy[q, 0] * nx + rxy[q, 1] * ny
                    amin = min(amin, v)
                    amax = max(amax, v)
                cmin, cmax = 1e300, -1e300
                for (qx, qy) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                    v = qx * nx + qy * ny
                    cmin = min(cmin, v)
                    cmax = max(cmax, v)
                if amax <= cmin or cmax <= amin:
                    sep = True
                    break
            if not sep:
                return k
    return -1


class _TrH:
    __slots__ = ("pos", "ifr", "hooks")

    def __init__(self, pos, ifr, hooks):
        self.pos, self.ifr, self.hooks = pos, ifr, hooks


class _ShiftHook:
    """A hook with its frames moved to the views' frames (search.first_collision reads iid, P, ctrl, ok)."""
    __slots__ = ("iid", "P", "ctrl", "ok")

    def __init__(self, h, n0: int):
        self.iid, self.P, self.ctrl, self.ok = h.iid, h.P + n0, h.ctrl + n0, h.ok


def _pct(v, q) -> float:
    return float(np.percentile(v, q)) if len(v) else 0.0


__all__ = ["table_dims", "WINDOWS", "Window", "Macro", "Raw", "render", "plan_of", "judge", "judge_evaluator", "Verdict",
           "CellKey", "cell_of", "cell_samples", "judge_cell", "her_class", "wall_band", "Table", "Entry", "enabled",
           "in_states", "windows_for", "FIRST_WIN", "SECOND_WIN", "pack_key", "unpack_key", "Reflex", "Press",
           "JUDGE_HOOK_VARIANTS", "HOOK_HOLD_MAX", "CONTACT_W", "judge_cl", "judge_variants", "NEAR", "FAR", "VERSION",
           "TABLE_PATH", "hold_height", "cl_vy_class", "clapper_extra", "JUMPING", "M_CLAW", "swings", "pick_alt",
           "judge_press", "KILL_HP", "STOP_TOL", "DRIFT_LAT", "CTRL_LATE", "clapper_steps"]
