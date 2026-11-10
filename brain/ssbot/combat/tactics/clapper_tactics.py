"""The manual-B two-Clapper L2 tactics (Task 180): each complete tactic in one unit.

A unit holds its applicability (with the reason it does not apply), its maximum scores, its event memory and phases
and its whole L2 output: the target it offers, the entry attack it picks, the stance / contact style / scene /
no-hit it applies while it is the winner, and the outputs its event still owns afterwards. clapper_priority runs the
shared parts only: the scene facts (clapper_scene), the observation order, the re-pick triggers, one comparison of
the offers (maximum x applicability - switch cost, the kept target on a tie), the shared constraints of the
application and the logs. It never reads a tactic's name to build an output.

Hooks (each optional; the base class is the plain tactic):
  observe(sc)          advance its event memory every call; returns the live event context (or None)
  repick(sc)           its event asks for a pick now (besides the period and the scene changes)
  propose(sc)          [(rule, target subject, applicability)], or [] and why it does not apply
  commit(sc, ...)      the winner's own memory commitments (nothing for a tactic that did not win)
  release(sc, ...)     after every pick: end its own event when the outcome ends it (never a new commitment)
  pick_entry(sc, ...)  the winner's entry attack at the pick (default: the shared one, passed in)
  apply(sc, ...)       the winner's stance / style / scene / hit suppression every tick (None: the shared default)
  finish(sc, ...)      every tick after the shared outputs: the winner's late outputs and its event's aftermath
  log(sc, out)         its fields of tac.last
Declarations: scores (rule -> maximum), excluded_by (events under which it is not evaluated), owns_scene (while its
event is active only these other rules stay in the pool), switch_entry (a switch to its target takes the shared side /
stomp entry first), memory (its initial keys in the manual-B memory). Every action owner still makes its own key
checks; an L2 win is never an action's success.
"""
from dataclasses import dataclass, replace

from ssbot.combat import forum_v2, knife_chain_waypoint as WP
from ssbot.core.worldstate import Ev

# (clapper_plans reads only its own switch and the shared geometry; flag off its units below are never built into a call)

from . import clapper_middle, clapper_plans, clapper_separated as SEP
from .clapper_scene import AIR, ANTIC, JUMPS, NEAR, NEARER_U, STACK_U, ground_stance, stacked_nearer, standing_gap
from .forum_local import clapper_facing
from .modes import EntryAttack, ReturnRequest

BAIT_WIDTHS = 2.5          # the person (seq 230): back off about 2.5 visible body widths, return on the take-off
DOWN_OK_FAMS = (None, "CC_IDLE")   # Task 182 seq 280: Phase.down_ok only while its target is idle or walking (the subject reads
#                                    CC_IDLE for the whole Idle / Walk, gauntlet.SP4_IDLE_FAMS without the evade)
RETURN_LANDED_S = 0.5      # SSBOT_FORUM_TWO_RETURN_BODY: after the landing in the gap the narrowing stays this long
KEEP = object()            # Applied.style: keep the entry attack's style


def released(sc, tactic, end):
    """Log only (tac.last clapper_releases): the tactic's event ended in this call, and why."""
    sc.tac.last.setdefault("clapper_releases", []).append({"tactic": tactic.name, "end": end})


@dataclass
class Applied:
    """The winner's per-tick output. stance None: the shared default (a side entry's ground stance)."""
    stance: float | None = None
    style: object = KEEP
    scene: str | None = None
    suppress_hits: bool = False             # no hit on either Clapper and no entry attack this tick
    no_hit: frozenset = frozenset()         # more no-hit targets (a body passed over, the jumper)
    cross_no_hit: frozenset = frozenset()   # Task 183 seq 267: the part of no_hit that is the ordinary middle return's
    #                                         crossed body (MiddleReturn: no attack credit while crossing it); the
    #                                         application records it apart (GoalPrefs.return_cross) when no other rule bans it
    withdraw_f: int | None = None           # Task 182 seq 272 B: the frame the running over_head stage began; its stance and
    #                                         strike are withdrawable on the action layer's refusal (GoalPrefs.withdraw)
    down_ok: frozenset = frozenset()        # Task 182 seq 280: the stage's own target whose down slash from the air still counts
    #                                         (Phase.down_ok, idle / walking only); the application keeps it (GoalPrefs.stay_pogo)
    #                                         only when no other source bans that target


class Tactic:
    name = ""
    event = None
    scores: dict = {}
    excluded_by: tuple = ()
    owns_scene: frozenset | None = None
    switch_entry = True
    memory: dict = {}         # its keys in the manual-B memory at the first call

    def observe(self, sc):
        return None

    def repick(self, sc):
        return False

    def propose(self, sc):
        return [], "never offered"

    def commit(self, sc, rule, target):
        pass

    def release(self, sc, rule, target):
        pass

    def pick_entry(self, sc, rule, target, previous):
        return previous

    def apply(self, sc, rule, g, target):
        return None

    def finish(self, sc, rule, won, g, out):
        return out

    def log(self, sc, out):
        return {}


class FocusKeep(Tactic):
    """Keep the current focus: the kept target, else the nearer Clapper outside the pair or the one with more outer
    room in it. Always applies; the plain approach and the shared entry."""
    name = "keep focus"
    scores = {"keep": 50.}

    def repick(self, sc):
        # Task 182 seq 303: the pair stacked with the other one clearly nearer: this tick, not at the next period
        return sc.mem.get("winner") == "keep" and stacked_nearer(sc) is not None

    def propose(self, sc):
        return [("keep", sc.default, 1.)], None


class MiddleJump(Tactic):
    """One jump between the two (clapper_middle): its aim / flight stages choose guide, stand, under / over or hold
    inside the event and offer one candidate. Its declared far side is kept through a real stomp hand-off."""
    name = "middle jump"
    event = "middle_jump"
    scores = {"middle_jump": 95.}

    def observe(self, sc):
        before = sc.mem.get("middle_jump")
        ctx = clapper_middle.observe(sc.tac, sc.ws, sc.subjects, sc.geo, sc.t, sc.mem)
        if before is not None and ctx is not before:
            released(sc, self, "the jump ended, or another one is a new event")
        return ctx

    def repick(self, sc):
        # a guide whose arrival no longer fits the aim reserve picks at once
        middle = sc.events.get(self.event)
        if middle is None or (middle.get("decision") or {}).get("route") != "guide":
            return False
        prior = middle["decision"]
        elapsed = sc.t - middle["antic_at"]
        source = sc.subject(middle["move"][0])
        deadline = .48 if source.family == "CC_JUMP" else .88
        return deadline - elapsed < prior["guide_arrival"] + sc.tac.rules.margin_s

    def propose(self, sc):
        middle = sc.events.get(self.event)
        if middle is None:
            return [], "no jump between the two"
        mid = middle["decision"] = clapper_middle.choose(sc.tac, sc.ws, sc.fc, sc.geo, sc.hx, sc.t, middle)
        if mid["route"] == "hold":
            # A jumper in flight is no hold target: kept as the focus it drew the planner under its landing
            # (live 786 2580..2606; Task 179, the person 11-05: never the corner). Before take-off: unchanged.
            jumper = sc.subject(mid["source"])
            mid["target"] = sc.other.iid if jumper.iid == sc.default.iid and jumper.state in AIR else sc.default.iid
        return [("middle_jump", sc.subject(mid["target"]), 1.)], None

    def commit(self, sc, rule, target):
        middle = sc.events[self.event]
        if middle["decision"]["route"] == "over":
            middle.setdefault("exit_until", sc.t + 2.)

    def pick_entry(self, sc, rule, target, previous):
        middle = sc.events[self.event]
        mid = middle["decision"]
        source = sc.subject(mid["source"])
        if mid["kind"] is None:
            return None
        if previous is not None and (previous.target, previous.source, previous.kind) == (target.iid, source.iid,
                                                                                         mid["kind"]):
            return previous
        return EntryAttack(target.iid, mid["kind"], source.iid, middle["family"], abs(float(source.pos[0]) - sc.hx),
                           sc.t)

    def finish(self, sc, rule, won, g, out):
        middle = sc.events.get(self.event)
        mid = middle["decision"] if middle is not None else None
        if not won or mid is None:
            return out
        # After the shared face / antic stance helpers, which must not turn a refused guide or a middle interval into
        # target +/- face_u again.
        g.stance_x = float(mid["stance"])
        sc.scene = "middle jump: " + mid["route"]
        return replace(out, stance_x=g.stance_x)

    def log(self, sc, out):
        middle = sc.events.get(self.event)
        return {"clapper_middle": middle["decision"] if middle is not None else None}


class JumpIntercept(Tactic):
    """Legacy fallback of the jump between the two (no middle-jump event): a jump coming from behind her becomes the
    target (intercept) and that same jump is held (hold) until it ends or another target wins."""
    name = "jump intercept"
    event = "intercept_hold"
    scores = {"intercept": 130., "hold": 140.}
    excluded_by = ("middle_jump",)
    switch_entry = False
    memory = {"intercept": None}

    def observe(self, sc):
        tac, mem, t = sc.tac, sc.mem, sc.t
        hold = mem["intercept"]
        if hold is not None:
            held = next((s for s in sc.subjects if s.iid == hold[0]), None)
            why = ("the held one is gone" if held is None else
                   "a different jump" if held.family in JUMPS and tac.t_commit.get(held.iid) != hold[1] else
                   "its jump and rune circle are over" if held.family not in JUMPS and not (
                       held.iid in tac.rune and t <= tac.rune[held.iid][3]) else None)
            if why is not None:
                mem["intercept"] = hold = None
                released(sc, self, why)
        return hold

    def propose(self, sc):
        hold = sc.events.get(self.event)
        if hold is not None:
            return [("hold", sc.subject(hold[0]), 1.)], None
        tac, hx, other = sc.tac, sc.hx, sc.other
        if sc.keep is None or not (other.family in JUMPS and other.state in AIR):
            return [], "no focus, or the other one not in a jump's flight"
        rec = tac.jb_land.get(other.iid)
        ent = tac._ent(sc.ws, other.iid)
        face = clapper_facing(ent) if ent is not None else None
        origin, front = (rec[0], rec[1]) if rec is not None else (other.pos[0], face)
        rear = (front in (-1, 1) and (origin - hx) * (sc.default.pos[0] - hx) < 0 and (hx - origin) * front > 0)
        if not rear:
            return [], "the jump does not come from behind her"
        if sc.events.get("takeoff") == (other.iid, tac.t_commit.get(other.iid)):
            return [], "the jump she has just left (take-off)"
        return [("intercept", other, 1.)], None

    def commit(self, sc, rule, target):
        if rule == "intercept":
            sc.mem["intercept"] = (target.iid, sc.tac.t_commit.get(target.iid))

    def release(self, sc, rule, target):
        hold = sc.events.get(self.event)
        if rule != "intercept" and hold is not None and target.iid != hold[0]:
            sc.mem["intercept"] = None
            released(sc, self, "another target won: " + rule)


class NearThreat(Tactic):
    """The other one newly in a near antic within slam range: switch to it (applicability by distance)."""
    name = "near threat"
    scores = {"near": 110.}

    def propose(self, sc):
        from .gauntlet import TWO_SLAM_RANGE_U
        if sc.keep is None:
            return [], "no focus"
        other = sc.other
        previous = sc.mem["seen"].get(other.iid)
        if not (other.state in NEAR and sc.seen[other.iid][2]):
            return [], "the other one not in a near antic within slam range"
        if previous is not None and previous[:3] == sc.seen[other.iid][:3]:
            return [], "already seen in this antic"
        if (other.state == "Spell Antic" and abs(float(other.pos[0]) - float(sc.default.pos[0])) < STACK_U
                and abs(float(other.pos[0]) - sc.hx) - abs(float(sc.default.pos[0]) - sc.hx) > NEARER_U):
            return [], "a cast behind the near one of a stacked pair"       # Task 182 seq 303: stacked_nearer would hand it straight back
        return [("near", other, .8 + .2 * max(0., 1. - abs(other.pos[0] - sc.hx) / TWO_SLAM_RANGE_U))], None


class FocusTakeoff(Tactic):
    """Legacy fallback: the focus has just taken off while she is between the two; switch to the other one and do
    not intercept the jump she left (departed)."""
    name = "focus take-off"
    event = "takeoff"
    scores = {"takeoff": 90.}
    excluded_by = ("middle_jump", "intercept_hold")
    memory = {"departed": None}

    def observe(self, sc):
        mem = sc.mem
        departed = mem["departed"]
        if departed is not None:
            leaving = next((s for s in sc.subjects if s.iid == departed[0]), None)
            if leaving is None or leaving.family not in JUMPS or sc.tac.t_commit.get(leaving.iid) != departed[1]:
                mem["departed"] = departed = None
                released(sc, self, "the jump she left is over")
        return departed

    def propose(self, sc):
        tac, keep, other, geo, hx, t = sc.tac, sc.keep, sc.other, sc.geo, sc.hx, sc.t
        if keep is None:
            return [], "no focus"
        # Task 179 #309 (the person 11-05/06, seq 229): leaving the jumper for the other Clapper (a vault / stomp
        # over it) is a dodge only while she is BETWEEN the two (actual body spans; root positions when a body is
        # unknown). Both beyond her (wall -> both -> hero -> open) is no switch into the cluster: the existing
        # retreat / keep stand, her room behind measured from the walls.
        between = (sc.region in {"middle", "tight"} if geo is not None else
                   min(float(s.pos[0]) for s in sc.subjects) < hx < max(float(s.pos[0]) for s in sc.subjects))
        if not (keep.family in JUMPS and keep.state in AIR
                and sc.mem["seen"].get(keep.iid, (None, None))[1] not in AIR):
            return [], "the focus has not just taken off"
        if other.family in JUMPS or (other.iid in tac.rune and t <= tac.rune[other.iid][3]):
            return [], "the other one jumping or its rune circle due"
        if not between:
            return [], "she is not between the two"
        return [("takeoff", other, 1.)], None

    def commit(self, sc, rule, target):
        # The focus we intentionally left is still the same jump, even when it becomes the nonfocus behind us on the
        # following tick.
        sc.mem["departed"] = (sc.keep.iid, sc.tac.t_commit.get(sc.keep.iid))


class EnterMiddle(Tactic):
    """On entering the middle: the one with more outer room (as the default pick there)."""
    name = "enter middle"
    scores = {"middle": 70.}
    excluded_by = ("middle_jump", "back")

    def propose(self, sc):
        if not (sc.region == "middle" and sc.mem["region"] != "middle"):
            return [], "not entering the middle"
        return [("middle", max(sc.subjects, key=lambda s: (sc.room[s.iid], -abs(s.pos[0] - sc.hx), -s.iid)), 1.)], None


class OuterRetreat(Tactic):
    """Outside the pair with the far one near its wall, room behind her and a jump in flight or a rune circle due:
    one step out (cast_out_u), no hit on either, no entry attack."""
    name = "outer jump retreat"
    scores = {"retreat": 150.}
    excluded_by = ("middle_jump",)

    def propose(self, sc):
        from .gauntlet import TWO_WALL_BAND_U
        tac, geo, region, t = sc.tac, sc.geo, sc.region, sc.t
        if region not in {"left", "right"}:
            return [], "not outside the pair"
        far = geo["high"] if region == "left" else geo["low"]
        far_room = geo["xb"] - far.pos[0] if region == "left" else far.pos[0] - geo["xa"]
        back_room = (sc.hx - geo["xa"] - tac.rules.wall_room_u if region == "left" else
                     geo["xb"] - tac.rules.wall_room_u - sc.hx)
        if not (far_room <= TWO_WALL_BAND_U and back_room >= tac.rules.cast_out_u):
            return [], "the far one is not at its wall or no room behind her"
        if not any(s.family in JUMPS and s.state in AIR or (s.iid in tac.rune and t <= tac.rune[s.iid][3])
                   for s in sc.subjects):
            return [], "no jump in flight and no rune circle due"
        return [("retreat", sc.default, 1.)], None

    def apply(self, sc, rule, g, target):
        direction = -1 if sc.region == "left" else 1
        return Applied(stance=sc.tac._clamp(sc.hx + direction * sc.tac.rules.cast_out_u), style=None,
                       scene="outer jump retreat", suppress_hits=True)


def _seam_after(sc):
    """#385 (the person 11-10, Sol seq 326; L2 plan "所有翻入/返回中间的共享小间隙后手"): a chosen move into the middle with the two facing body
    edges at most TIER_U apart (clapper_separated.seam_return) is one down slash aligned with the seam, whatever it meets: dict(stance: the
    seam, gap, posture "seam", no_hit: none, both bodies credited, how), or None (a wider gap: the entry's own place and slash). No
    double-hit proof (no tops gate), no standing-gap proof; the rows' own model contacts and checks (#379's seam double's executor)."""
    if sc.geo is None:
        return None
    ok, seam, gap = SEP.seam_return(sc.geo)
    if not ok:
        return None
    a = SEP._span(sc.geo, sc.geo["low"].iid)[0]
    b = SEP._span(sc.geo, sc.geo["high"].iid)[1]
    outside = sc.hx < a or sc.hx > b
    return dict(stance=float(seam), gap=float(gap), posture="seam", no_hit=frozenset(),
                how=" (from outside the pair)" if outside else "")


class FlipInward(Tactic):
    """Outside the pair with the default target in a near antic: the inward flip's stance and stomp style (an
    intent; the flip itself is the action owners'). #385: with the two at most TIER_U apart, the shared seam strike's stance."""
    name = "flip inward"
    scores = {"flip": 80.}
    excluded_by = ("middle_jump",)

    def propose(self, sc):
        if sc.region not in {"left", "right"}:
            return [], "not outside the pair"
        if sc.default.state not in NEAR:
            return [], "the default target not in a near antic"
        return [("flip", sc.default, 1.)], None

    def apply(self, sc, rule, g, target):
        if SEP.active():
            small = _seam_after(sc)
            if small is not None:
                return Applied(stance=small["stance"], style="stomp", scene="flip inward: seam strike")
        direction = 1 if sc.region == "left" else -1
        return Applied(stance=sc.tac._clamp(target.pos[0] + direction * sc.tac.rules.face_u), style="stomp",
                       scene="flip inward intent")


class TightOverhead(Tactic):
    """Already in a tight middle with no return intent: stand over the default target, stomp style."""
    name = "tight middle overhead"
    scores = {"overhead": 65.}
    excluded_by = ("middle_jump", "back")

    def propose(self, sc):
        if sc.region != "tight":
            return [], "not in a tight middle"
        if (SEP.active() and sc.geo is not None and not SEP.seam_return(sc.geo)[0]
                and not SEP.double_intent(sc.geo)[0]):
            # seq 312 #379 (the person: stacked without a seam double, stand on the ground): the near one on her side (#385: never with a gap
            # of at most TIER_U, the shared seam strike's)
            return [("overhead", SEP.outer_ground(sc.tac, sc.geo, sc.hx)[0], 1.)], None
        return [("overhead", sc.default, 1.)], None

    def apply(self, sc, rule, g, target):
        if SEP.active() and sc.geo is not None:
            small = _seam_after(sc)
            if small is not None:
                # #385 (the person 11-10, Sol seq 326): in the middle with the two at most TIER_U apart: the shared seam strike
                return Applied(stance=small["stance"], style="stomp", scene="tight middle: seam strike")
            ok, seam = SEP.double_intent(sc.geo)
            if ok:
                return Applied(stance=seam, style="stomp", scene="tight middle: seam double")
            return Applied(stance=SEP.outer_ground(sc.tac, sc.geo, sc.hx)[1], style=None,
                           scene="tight middle: ground in front of the near one")
        return Applied(stance=float(target.pos[0]), style="stomp", scene="tight middle overhead intent")


def return_pose(tac, target, geo, hx):
    """Task 179 #313: where 'back' puts her for one target, from the CURRENT bodies (not the roots' midpoint).

    ground: a standing gap (standing_gap): the existing ground_stance on the target's gap side. air: above the target's
    body at the seam between the two (inside its body span, so a down-slash from there meets it), the existing stomp
    style. crossed: the body between her and the seam (she passes it, a non-target is not hit on the way)."""
    low, high = geo["low"], geo["high"]
    (_, b1), (a2, _) = geo["bodies"][low.iid], geo["bodies"][high.iid]
    seam = .5 * (b1 + a2)
    crossed = low if hx < seam else high
    stand = ground_stance(tac, target, seam, geo) if standing_gap(geo) else None
    if stand is not None:
        return dict(posture="ground", stance=float(stand), crossed=crossed.iid, seam=float(seam), gap=float(a2 - b1))
    a, b = geo["bodies"][target.iid]
    return dict(posture="air", stance=float(min(b, max(a, seam))), crossed=crossed.iid, seam=float(seam),
                gap=float(a2 - b1))


def middle_return(tac, subjects, geo, hx, t, mem, quiet_from, grounded=False, frame=None):
    """Task 179 #313 / #314 (the person via Sol seq 233-237): after a near attack, back between the two.

    A Clapper move (TWO_ATTACK_FAMS) is near when she was within TWO_SLAM_RANGE_U of its root on any tick of it; its
    end (the family leaves the attack families) makes the return due, whatever came before (she jumped out of the
    middle, or the two overlapped from the start), on the ground or in the air - unless she is between the roots
    with a standing gap then (on the ground there, or over a body's inner half as live 2626's pogo: the ordinary
    scene goes on). Between the roots without one she still needs the seam (Root's #313 probe: H 20.75 / y 9, roots
    20 / 21.5). While due it is offered when nothing else holds the scene (quiet_from: no middle-jump event,
    cluster route or intercept hold), neither Clapper is in an attack family, and no jump cast's circle still to
    burst lies over the destination (the circle is in front of the cast's facing, tac.rune). The pose follows the
    current bodies (return_pose): ground in a standing gap, else air at the seam until they part. Done only once she
    has landed (grounded: the hero's ground contact) in the standing gap; in the air over an open gap it goes on
    (a gap that closes again before she lands gives the air pose back), and a new near move makes it due again. An
    intent only: every key, crossing and landing still goes through the existing checks and owners."""
    from .gauntlet import TWO_ATTACK_FAMS, TWO_SLAM_RANGE_U
    moves = mem.setdefault("moves", {})
    roots = [float(s.pos[0]) for s in subjects]
    for s in subjects:
        m = moves.get(s.iid)
        if s.family in TWO_ATTACK_FAMS:
            if m is None or m["family"] != s.family:          # a direct follow-up keeps the earlier nearness
                moves[s.iid] = m = {"family": s.family, "start_t": t, "near": bool(m and m["near"])}
                if frame is not None:
                    m["start_f"] = frame                       # SSBOT_FORUM_TWO_RETURN_AIR only
            m["near"] = m["near"] or abs(float(s.pos[0]) - hx) <= TWO_SLAM_RANGE_U
        elif m is not None:
            del moves[s.iid]
            # #386 (the person 11-10, Sol seq 330: "锤后一律回中间"): a slam's end with both Clappers here makes the return due wherever she was
            slam = SEP.active() and m["family"] == SEP.CC_SLAM and len(subjects) == 2
            if (m["near"] or slam) and not (min(roots) <= hx <= max(roots) and standing_gap(geo) is not False):
                mem["back"] = dict(m, iid=s.iid, end_t=t, end_hx=hx, end_state=s.state, offered=False,
                                   **({} if frame is None else {"end_f": frame}))
    due = mem.get("back")
    if due is None or geo is None or quiet_from is not None:
        return None
    if any(s.family in TWO_ATTACK_FAMS for s in subjects):
        return None
    room = {s.iid: (float(s.pos[0]) - geo["xa"] if s.iid == geo["low"].iid else geo["xb"] - float(s.pos[0]))
            for s in subjects}
    target = max(subjects, key=lambda s: (room[s.iid], -abs(float(s.pos[0]) - hx), -s.iid))   # as the "middle" rule
    pose = return_pose(tac, target, geo, hx)
    if pose["posture"] == "ground" and geo["region"] == "middle" and grounded:
        # landed in the standing gap itself (crossing a root in the air over a body, or hanging over an open gap, is
        # not yet back: live 2812 closed the gap right after; Root's #313 probe re-closed it before the landing)
        if due["offered"]:
            mem["back_end"] = dict(due, end="landed in the standing gap", end_t=t, end_hx=hx)
        mem["back"] = None
        return None
    circle = [s.iid for s in subjects if s.iid in tac.rune and t <= tac.rune[s.iid][3]
              and (pose["stance"] - tac.rune[s.iid][0]) * tac.rune[s.iid][1] > 0]
    if not circle and SEP.active():
        # #386 (Sol seq 330: only a live big rune in the middle holds the return; the shared per-generation ledger, one burst not the end of
        # all): her place or the seam inside a live circle (grown by her half widths and the pad)
        from .gauntlet import JT
        circle = [(lo, hi) for lo, hi in SEP.live_circles(tac, t)
                  if any(lo - geo["right"] - JT["pad"] < x < hi + geo["left"] + JT["pad"] for x in (pose["stance"], pose["seam"]))]
    if circle:
        return None
    due["offered"] = True
    return dict(pose, target=target.iid, move=[due["iid"], due["family"]], near_end_t=due["end_t"],
                outer_room={str(k): float(v) for k, v in room.items()})


class MiddleReturn(Tactic):
    """Back between the two after a near attack (middle_return): offered while due and nothing else holds the scene;
    ground pose in a standing gap (side slash), else air at the seam (stomp style), the passed-over body not hit.
    Its event also owns the second-body narrowing (return_body) while it is applied and for RETURN_LANDED_S after the
    landing in the gap, and the air pose's request to the native B2 owner (return_request)."""
    name = "middle return"
    event = "back"
    scores = {"back": 70.}
    waits_for = (("middle_jump", "middle jump"), ("cluster", "cluster route"), ("intercept_hold", "intercept hold"))

    def observe(self, sc):
        quiet = next((why for ev, why in self.waits_for if sc.events.get(ev) is not None), None)
        before = sc.mem.get("back")
        home = middle_return(sc.tac, sc.subjects, sc.geo, sc.hx, sc.t, sc.mem, quiet, sc.grounded,
                             sc.frame if forum_v2.RETURN_AIR else None)
        if before is not None and sc.mem.get("back") is None:
            released(sc, self, "landed in the standing gap" + ("" if before.get("offered") else " before any offer"))
        due = sc.mem.get("back")
        if home is not None and due is not None and SEP.active() and sc.geo is not None and type(sc.frame) is int:
            # #386 (Sol REVIEW385 2): the seam tier's action (the shared seam strike's entry, its deadline): one from the tick the two
            # facing edges come within TIER_U, a new one past its deadline; none past TIER_U (a gap that opens turns the return to its
            # ground pose at once, as before: the chain hands an approach not yet pressed back)
            if _seam_after(sc) is None:
                due["seam_f"] = None
            elif type(due.get("seam_f")) is not int or sc.frame > due["seam_f"] + SEP.POST_ACT_F:
                due["seam_f"] = sc.frame
        return home

    def repick(self, sc):
        # a pick when the return becomes live or stops being live (back_live: whether it was at the last call); #386: on its seam action's
        # first tick (its entry)
        live = sc.events.get(self.event) is not None
        ask = live != sc.mem.get("back_live", False)
        sc.mem["back_live"] = live
        due = sc.mem.get("back")
        return ask or bool(live and due is not None and SEP.active() and due.get("seam_f") == sc.frame)

    def propose(self, sc):
        home = sc.events.get(self.event)
        if home is None:
            if sc.mem.get("back") is None:
                return [], "no return due"
            quiet = next((why for ev, why in self.waits_for if sc.events.get(ev) is not None), None)
            return [], ("due, waits for the " + quiet if quiet is not None else
                        "due, held back: an attack on, a jump cast's circle over the stance, or no geometry")
        # Task 179 #313: the near attack is over; back between the two (ground gap: stand and side slash; no gap:
        # the existing stomp style at the seam until they part). The middle score: the same place it values. It
        # holds the tight scene too (#314, Root's probe: the overhead root 20 tied it after the switch cost).
        target = sc.subject(home["target"])
        if (SEP.active() and sc.geo is not None and home["posture"] == "air" and not SEP.seam_return(sc.geo)[0]
                and not SEP.double_intent(sc.geo)[0]):
            # seq 312 #379 (the person: stacked without a seam double, stand on the ground): the near one on her side (#385: never with a gap
            # of at most TIER_U, the shared seam strike's)
            target = SEP.outer_ground(sc.tac, sc.geo, sc.hx)[0]
        return [("back", target, 1.)], None

    def pick_entry(self, sc, rule, target, previous):
        # #386 (Sol REVIEW385 2: the entries still on the ordinary rows bind to the shared executor): the seam tier's strike as the chain's
        # stomp entry on the target (scope "seam_back", event_f its action's first frame; the move that ended its source and responsibility)
        due = sc.mem.get("back")
        if (not SEP.active() or sc.events.get(self.event) is None or due is None or type(due.get("seam_f")) is not int
                or _seam_after(sc) is None or not _stompable(sc, target.iid)):
            return None
        src = next((s for s in sc.subjects if s.iid == due.get("iid")), None)
        if src is None:
            return None
        if (previous is not None and getattr(previous, "scope", None) == "seam_back"
                and (previous.target, previous.source, previous.event_f) == (target.iid, src.iid, due["seam_f"])):
            return previous
        return EntryAttack(target.iid, "stomp", src.iid, str(due["family"]), abs(float(src.pos[0]) - sc.hx), sc.t, scope="seam_back",
                           event_f=int(due["seam_f"]))

    def apply(self, sc, rule, g, target):
        if sc.events.get(self.event) is None:
            return None
        pose = sc.back_pose = return_pose(sc.tac, target, sc.geo, sc.hx)
        if SEP.active():
            small = _seam_after(sc)
            if small is not None:
                # #385 (the person 11-10, Sol seq 326): the shared small-gap after-move of a chosen return: one down slash at the seam (the
                # rows' seam stomp, as #379's seam double, without its tops gate)
                sc.back_pose = dict(pose, posture="seam", stance=small["stance"], gap=small["gap"])
                return Applied(stance=small["stance"], style="stomp", scene="middle return: seam strike")
        if SEP.active() and pose["posture"] == "air":
            # seq 312 #379: no standing gap. A seam double's intent: down slashes at the seam, both bodies credited (each contact is the
            # rows' own); without it the ground in front of the near one on her side, side slashes (no air pose, no crossing)
            ok, seam = SEP.double_intent(sc.geo)
            if ok:
                sc.back_pose = dict(pose, posture="seam", stance=seam)
                return Applied(stance=seam, style="stomp", scene="middle return: seam double")
            x = SEP.outer_ground(sc.tac, sc.geo, sc.hx)[1]
            sc.back_pose = dict(pose, posture="ground outside", stance=x)
            return Applied(stance=x, style=None, scene="middle return: no gap, ground in front of the near one")
        crossed = frozenset() if pose["crossed"] == g.target else frozenset({pose["crossed"]})
        return Applied(stance=pose["stance"], style="stomp" if pose["posture"] == "air" else None,
                       scene="middle return " + pose["posture"], no_hit=crossed, cross_no_hit=crossed)

    def finish(self, sc, rule, won, g, out):
        pose = sc.back_pose if won else None
        mem, t, geo = sc.mem, sc.t, sc.geo
        e, due = out.entry_attack, mem.get("back")
        if getattr(e, "scope", None) == "seam_back":
            t_ = next((s for s in sc.subjects if s.iid == e.target), None)
            if (pose is None or pose.get("posture") != "seam" or due is None or e.event_f != due.get("seam_f") or e.target != g.target
                    or t_ is None or not _stompable(sc, e.target)):
                # #386: the seam strike entry is this return's seam action's, one that can be executed now; the chain hands an approach not
                # yet pressed back (knife_chain_air_native)
                g.entry_attack = None
                out = replace(out, entry_attack=None)
            else:
                # (the shared executor: the air key only up to the seam, rows kept with her centre at the contact on the seam side of the
                # target's root, by the action's deadline)
                sign = 1 if float(pose["stance"]) > float(t_.pos[0]) else -1
                out = replace(out, strike_bound=(t_.iid, float(pose["stance"]), float(t_.pos[0]), sign,
                                                 int(due["seam_f"]) + SEP.POST_ACT_F, None, "seam"))
        landed = mem.get("back_end")
        landed = (landed is not None and landed.get("end") == "landed in the standing gap"
                  and 0. <= t - landed["end_t"] <= RETURN_LANDED_S and geo is not None and geo["region"] == "middle"
                  and sc.grounded)
        if (pose is not None or landed) and forum_v2.RETURN_BODY and all(s.state in forum_v2.RETURN_STATES
                                                                          for s in sc.subjects):
            # SSBOT_FORUM_TWO_RETURN_BODY (#315, Sol seq 238 G1-a): the return in force (or just landed in the gap,
            # still standing there: its side slash, w3on 2869) with both seen in Idle / Walk: the other one's idle body
            # may take the focus margin on the ordinary rows' revocable frames (forum_v2 checks the tracker's own state
            # again on the frame it builds; every other check keeps the original margins)
            out = replace(out, return_body=next(s.iid for s in sc.subjects if s.iid != g.target))
        due = mem.get("back")
        if (pose is not None and pose["posture"] == "air" and forum_v2.RETURN_AIR and due is not None
                and all(s.state in forum_v2.RETURN_STATES for s in sc.subjects)
                and type(due.get("start_f")) is int and type(due.get("end_f")) is int
                and type(sc.frame) is int):
            # SSBOT_FORUM_TWO_RETURN_AIR (#316, Sol seq 239 a): this tick's air return (the actual winner, both seen
            # in Idle / Walk) after the observed near move that ended: a request for the native B2 owner's existing
            # SWITCH execution; it is not made on any other tick (pose, target or state changed: the request is gone)
            if due.get("request_f") is None:
                due["request_f"] = int(sc.frame)
            out = replace(out, return_request=ReturnRequest(int(g.target), int(due["iid"]), str(due["family"]),
                                                            int(due["start_f"]), int(due["end_f"]),
                                                            int(due["request_f"])))
        return out

    def log(self, sc, out):
        home = sc.events.get(self.event)
        return {"clapper_back": None if home is None else dict(home, applied=sc.back_pose, **(
                    {} if out.return_body is None else {"return_body": out.return_body}), **(
                    {} if out.return_request is None else {"return_request": vars(out.return_request)})),
                "clapper_back_end": sc.mem.get("back_end")}


def cluster_route(tac, subjects, geo, hx, t, mem, middle):
    """Task 179 #310 (the person, seq 230): both Clappers beyond her and one of them in a jump antic.

    bait: back off outward BAIT_WIDTHS visible body widths (the cluster member nearer to her; the damage-box body
    span, not the hammer or render bounds) from where she stood when the antic was first seen, capped by the
    existing wall clearance (tac._clamp). return: on the OBSERVED take-off (Jump / Air, never a guessed one) the
    grounded one is the target with an ordinary side entry (existing ground approach and ground_stance). The route
    ends with that jump; the grounded one starting its own attack or jump ends it (existing rules then). Between the
    two (clapper_middle) it never starts. An intent only: every key still goes through the existing action checks."""
    ctx = mem.get("cluster")
    by_id = {s.iid: s for s in subjects}
    if ctx is not None:
        j, g = by_id.get(ctx["jumper"]), by_id.get(ctx["grounded"])
        why = ("actor gone" if j is None or g is None else
               "jump ended" if j.family not in JUMPS or tac.t_commit.get(j.iid) != ctx["move"][1] else
               "grounded one started " + str(g.state) if g.family in JUMPS or g.state in NEAR | AIR else None)
        if why is not None:
            mem["cluster_end"] = dict(ctx, end=why, end_t=t, end_hx=hx)
            ctx = None
        elif ctx["phase"] == "bait" and j.state in AIR:
            ctx.update(phase="return", return_t=t, return_hx=hx, return_state=j.state)
    if ctx is None and middle is None and geo is not None and geo["region"] in ("left", "right"):
        jumping = [s for s in subjects if s.family in JUMPS]
        if len(jumping) == 1 and jumping[0].state in ANTIC:
            j = jumping[0]
            g = next(s for s in subjects if s.iid != j.iid)
            if g.state not in NEAR | AIR:
                out = -1 if geo["region"] == "left" else 1
                near = geo["low"] if out < 0 else geo["high"]
                a, b = geo["bodies"][near.iid]
                want = hx + out * BAIT_WIDTHS * (b - a)
                bait = tac._clamp(want)
                ctx = {"move": [j.iid, tac.t_commit.get(j.iid)], "jumper": j.iid, "grounded": g.iid,
                       "phase": "bait", "out": out, "width_u": b - a, "width_of": near.iid, "widths": BAIT_WIDTHS,
                       "hx0": hx, "want_x": want, "bait_x": bait, "wall_capped": abs(bait - want) > 1e-9,
                       "started_t": t, "reference": "hero x at the first antic tick + out * widths * body span"}
    mem["cluster"] = ctx
    return ctx


class ClusterRoute(Tactic):
    """Both beyond her and one in a jump antic (cluster_route): bait - back off outward until the observed take-off,
    no hit on either; return - an ordinary side slash on the grounded one, the jumper not hit. While the route is
    active it owns this jump event: only keep stays in the pool besides it (#310)."""
    name = "cluster bait and return"
    event = "cluster"
    scores = {"bait": 145., "return": 145.}
    owns_scene = frozenset({"keep"})

    def observe(self, sc):
        before = sc.mem.get("cluster")
        route = cluster_route(sc.tac, sc.subjects, sc.geo, sc.hx, sc.t, sc.mem, sc.events.get("middle_jump"))
        if before is not None and route is not before:
            released(sc, self, (sc.mem.get("cluster_end") or {}).get("end"))
        return route

    def propose(self, sc):
        route = sc.events.get(self.event)
        if route is None:
            return [], "no cluster jump"
        return [(route["phase"], sc.subject(route["jumper" if route["phase"] == "bait" else "grounded"]), 1.)], None

    def pick_entry(self, sc, rule, target, previous):
        if rule != "return":
            return None
        # an ordinary side slash on the grounded one, never a stomp / vault into the cluster
        src = sc.subject(sc.events[self.event]["jumper"])
        return EntryAttack(target.iid, "side", src.iid, src.family, abs(float(src.pos[0]) - sc.hx), sc.t)

    def apply(self, sc, rule, g, target):
        route = sc.events.get(self.event)
        if route is None:
            return None
        if rule == "bait":
            return Applied(stance=float(route["bait_x"]), style=None, scene="cluster bait retreat",
                           suppress_hits=True)
        return Applied(scene="cluster return side slash", no_hit=frozenset({route["jumper"]}))

    def log(self, sc, out):
        route = sc.events.get(self.event)
        return {"clapper_cluster": None if route is None else dict(route),
                "clapper_cluster_end": sc.mem.get("cluster_end")}


# ---- Task 182 (SSBOT_FORUM_TWO_PLAN=1): the jump scenes as plans (clapper_plans) run by the generic executor (l2_plan) ----


class PlanRun(Tactic):
    """Offers nothing: advances the plan runner first in every call (results, the executor's events, the requests)."""
    name = "plan runner"
    event = "plan"

    def observe(self, sc):
        sc.plans.tick(sc)
        return sc.plans.exec.plan


class _Planned(Tactic):
    """A parent scene's output is the running phase's: target, entry style, stance, no-hit, hit suppression. The unit holds
    no event memory: the plan is the worker's, the progress is the executor's."""
    scene = ""
    switch_entry = False      # the phase names its own entry (pick_entry)

    def observe(self, sc):
        return sc.plans.context(self.scene, sc.t)

    def repick(self, sc):
        return sc.plans.changed

    def pick_entry(self, sc, rule, target, previous):
        return sc.plans.entry(sc, target, previous)

    def apply(self, sc, rule, g, target):
        ex = sc.plans.exec
        ph = ex.phase
        if ph is None or ex.plan is None or ex.plan.scene != self.scene:
            return None
        style = KEEP if ph.attack else ph.contact
        no_hit = frozenset(ph.no_hit)
        stance = None
        if ph.stance is not None and ph.stance[0] == "middle" and sc.geo is not None:
            # back to the middle: a standing gap is a landing, no hit on the way (no new Run onto its body); no gap: the
            # existing air pose at the seam, its stomp style
            if return_pose(sc.tac, target, sc.geo, sc.hx)["posture"] == "air":
                style = "stomp"
                if SEP.active():
                    # seq 312 #379: the seam double's intent, else the ground in front of the near one on her side when that is this target
                    ok, seam = SEP.double_intent(sc.geo)
                    near, x = SEP.outer_ground(sc.tac, sc.geo, sc.hx)
                    if ok:
                        stance = seam
                    elif near.iid == target.iid:
                        stance, style = x, None
            else:
                no_hit = no_hit | {target.iid}
        # Sol seq 272 B: over_head's stance and stomp stand for the action layer's strike over the walker; its refusal takes them back
        withdraw_f = sc.plans.stage_frame(sc) if ph.name == "over_head" else None
        # Task 182 seq 280: over_stay's target, idle or walking (a new move - its slam's antic, an evade - ends it: re-judged on
        # the actual state), keeps its down slash for the ordinary rows; never another Clapper, never past this stage
        down_ok = (frozenset({target.iid}) if (ph.down_ok and target is not None and target.iid == ph.target
                                               and getattr(target, "family", None) in DOWN_OK_FAMS) else frozenset())
        return Applied(stance=sc.plans.stance(sc, ph) if stance is None else stance, style=style, scene=f"{self.scene} plan: {ph.name}",
                       suppress_hits=ph.suppress_hits, no_hit=no_hit, withdraw_f=withdraw_f, down_ok=down_ok)

    def finish(self, sc, rule, won, g, out):
        ph = sc.plans.exec.phase
        if won and ph is not None and ph.ground:
            # a way on the floor: rows without a jump key first among the safe ones (JT ground, fp1: she jumped on the way
            # under and met its landing); the existing preference, every safety rank above it stays
            out = replace(out, ground_first=frozenset(out.ground_first) | {g.target})
        if won and ph is not None and ph.go is not None:
            # where the phase must be by a time: the action layer's bounded approach (the ordinary rows stay its fallback)
            out = replace(out, waypoint=sc.plans.waypoint(sc, ph))
        if won and ph is not None and ph.no_chase:
            # seq 311: every real key owner keeps to this stage, not only the rows (the chase, the slam script, a new strike of the chain)
            out = replace(out, press_walker=sc.plans.exec.plan.get("other"))
        return out

    def log(self, sc, out):
        return {"clapper_plan": sc.plans.log_row(sc)}


class PlannedMiddle(_Planned):
    """She is between the two bodies, one in a jump: the plan's selected route runs (stay / under / over with the prepared
    fallback). No plan yet, blocked or invalid: no offer (never a 95-point empty route); the generic rules go on."""
    name = "middle jump"
    event = "middle_jump"
    scene = "middle"
    scores = {"middle_jump": 95.}

    def propose(self, sc):
        ex = sc.plans.exec
        ph = ex.phase if (ex.plan is not None and ex.plan.scene == self.scene) else None
        if ph is None:
            return [], sc.plans.why_not(self.scene)
        return [("middle_jump", sc.subject(ph.target) if ph.target is not None else sc.default, 1.)], None


class _PlannedCluster(_Planned):
    """She is outside the two, one in a jump's antic: one complete plan of the two; the public comparison chooses."""
    event = "cluster"
    scene = "cluster"
    owns_scene = frozenset({"keep", "cluster_lure", "cluster_attack", "cluster_vault"})
    branch = ""
    rule = ""

    def propose(self, sc):
        ex = sc.plans.exec
        plan = ex.plan
        if plan is None or plan.scene != self.scene:
            return [], sc.plans.why_not(self.scene)
        cand = plan.candidate(self.branch)
        if cand is None or not cand.feasible:
            return [], "not feasible: " + str(None if cand is None else cand.reason)
        if ex.selected not in (None, self.branch):
            return [], "the other plan runs"
        if ex.selected == self.branch:
            ph = ex.phase
        else:
            # as it would stand on this tick: a take-off already observed is taken with the choice, not a tick later
            ph, why = sc.plans.start_phase(sc, self.branch)
            if ph is None:
                return [], why
        return [(self.rule, sc.subject(ph.target) if ph.target is not None else sc.default, cand.applicability)], None

    def commit(self, sc, rule, target):
        sc.plans.commit_choice(sc, self.branch)


class ClusterLure(_PlannedCluster):
    """Back off to a sufficient interval (attacks legal until its departure), return under on the observed take-off."""
    name = "cluster lure and return"
    branch = "lure"
    rule = "cluster_lure"
    scores = {"cluster_lure": 145.}


class ClusterAttack(_PlannedCluster):
    """Slash the reachable one through the aim, retreat past the coverage on the take-off, come back after the hazards."""
    name = "cluster attack and retreat"
    branch = "attack"
    rule = "cluster_attack"
    scores = {"cluster_attack": 130.}    # below lure even after lure's target switch cost: lure first when its space holds


class ClusterVault(_PlannedCluster):
    """Task 182 seq 312 (plan 3.3, the outer variant only): over the near one into the middle in the aim, under the jumper on its observed
    take-off. Chosen by the plan itself: the lure whenever it can run, else the attack or this by the final place's wall room."""
    name = "cluster vault and under"
    branch = "vault"
    rule = "cluster_vault"
    scores = {"cluster_vault": 130.}


class PlannedKeep(FocusKeep):
    """As FocusKeep; with no running plan a jumper in flight above her is no focus (live 786; the legacy hold's rule)."""

    def propose(self, sc):
        d = sc.default
        if (d.family in JUMPS and d.state in AIR and sc.region not in {"left", "right"} and sc.plans.blocked_for(d)):
            return [("keep", sc.other, 1.)], None
        return super().propose(sc)


class PlannedIntercept(JumpIntercept):
    """The trigger is JumpIntercept's. The hold is a running one-phase plan in the executor (bound to the jump's instance,
    ended by its jump and rune circle): no separate 140-point rule, no private memory."""
    scores = {"intercept": 130.}
    memory = {}

    def observe(self, sc):
        ex = sc.plans.exec
        hold = ex.plan.instance if (ex.plan is not None and ex.plan.scene == "intercept") else None
        if hold is None and sc.mem.get("plan_intercept"):
            released(sc, self, ex.reason or "its jump and rune circle are over")
        sc.mem["plan_intercept"] = hold is not None
        return hold

    def propose(self, sc):
        hold = sc.events.get(self.event)
        if hold is not None:
            return [("intercept", sc.subject(hold[0]), 1.)], None
        return super().propose(sc)

    def commit(self, sc, rule, target):
        if rule == "intercept" and sc.events.get(self.event) is None:
            sc.plans.respond(sc, target)

    def release(self, sc, rule, target):
        hold = sc.events.get(self.event)
        if rule != "intercept" and hold is not None and target.iid != hold[0]:
            sc.plans.exec.end("complete", "another target won: " + rule, sc.t)
            sc.mem["plan_intercept"] = False
            released(sc, self, "another target won: " + rule)


class PlannedTakeoff(FocusTakeoff):
    """The trigger stays for a take-off no plan covers; 'she left this jump' is the executor's event history."""
    memory = {}

    def observe(self, sc):
        return sc.plans.departed(sc)

    def commit(self, sc, rule, target):
        sc.plans.exec.record((sc.keep.iid, sc.tac.t_commit.get(sc.keep.iid)), "departed", sc.t)


# ---- Task 182 seq 312 (the person 11-09 / 11-10; facts: clapper_separated): the far one's slam with the near one or a big rune between
# them, the small rune's down slashes and its end. Intents only: every key, crossing, landing and hit stays with the action owners. ----

NEW_ANTICS = frozenset({"Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic"})
# #384 (Sol REVIEW383: an action that cannot be executed now is no entry; the existing rules go on): the target states a package stomp entry
# is given and kept in: the ones the chain's strike witness reads (a still Idle; a walker inside its WalkSupport)
STOMP_STATES = frozenset({"Idle", "Walk"})


def _stompable(sc, iid) -> bool:
    s = next((v for v in sc.subjects if v.iid == iid), None)
    return s is not None and s.state in STOMP_STATES


def _hit_on(sc, iids) -> bool:
    """A nail hit of hers on one of these bodies among this call's events (the view's HIT_DEALT)."""
    for ev in getattr(sc.ws, "events", ()) or ():
        if ev.kind == Ev.HIT_DEALT and getattr(ev.data, "target_id", None) in iids:
            return True
    return False


def _air_ok(out, iid):
    """Her side slash on this body from the air counts (the stage's fall slash): it leaves the ground-only sets."""
    return replace(out, ground_hit=frozenset(out.ground_hit) - {iid}, no_pogo=frozenset(out.no_pogo) - {iid},
                   ground_first=frozenset(out.ground_first) - {iid})


class SeparatedSlam(Tactic):
    """Plan 1.x: F's slam with N (or a live big rune) between her and it. She stays outside its range on her side and F is not hit: at the
    range edge, N slashed only within reach (1.2.3); over N's outer part with down slashes when its body reaches out past the edge (1.2.2);
    past N on its inner side when that room is itself outside the range (1.2.1: down slashes take her over it, then side slashes from the
    inside); at the outer one of the circle's and the range's edges, whatever she reaches slashed (1.1). Inside the range: the action layer's
    bounded way out to the edge before the earliest first hammer frame (waypoint Run; its own step checks, dash lock and late hand-back).
    #386 (the person 11-10, Sol seq 330): once both hammer stages are over, every branch back into the middle, unless a live big rune lies
    over it (postponed): the two facing edges at most TIER_U apart, the shared seam strike (the chain's seam executor); wider, over the body
    between her and the middle (the vault to its air hand-back point) and her air side slash on it as she falls (no landing first). A hit, an
    evade, no standing room or a tier change never ends it; in the middle, its seam strike's hit, a new antic or a body gone does. No place
    outside the range on her side inside the walls: not offered (the existing rules: design 3.2's wall cases)."""
    name = "separated slam"
    event = "sep_slam"
    scores = {"sep_slam": 125.}
    excluded_by = ("middle_jump", "cluster", "intercept_hold")   # a running jump plan keeps its own stages

    def observe(self, sc):
        mem = sc.mem
        for s in sc.subjects:
            SEP.slam_record(sc, mem, s)
        post = mem.get("sep_post")
        if post is not None:
            why = self._post_end(sc, post)
            if why is not None:
                mem["sep_post"] = post = None
                released(sc, self, "after the slam: " + why)
        sep = SEP.separated(sc, {SEP.CC_SLAM}) or self._latched(sc)
        if sep is not None:
            rec = mem["sep_slam"].get(sep["far"].iid)
            if rec is not None:
                near = sep["near"]
                if near.state == SEP.EVADE_STATE and rec.get("near_evaded") is None:
                    rec["near_evaded"] = sc.frame    # #385 (the person): N evading in this slam: outside the range until it is over
                if _hit_on(sc, {near.iid}):
                    if rec.get("near_hit") is None:
                        rec["near_hit"] = sc.frame   # #384: N struck in this slam (1.2.1: one witnessed strike per Idle, no second entry)
                    if rec.get("mode") == "strike" and rec.get("strike_hit") is None:
                        rec["strike_hit"] = sc.frame   # #385: 1.2.2's down slash met N (its side slashes before it do not count)
            if rec is not None and not SEP.hammer_over(sc, sep["far"], rec):
                place = SEP.slam_place(sc, sep, rec)
                if place is not None:
                    rec["branch"] = place["branch"]
                    rec["pogo"] = rec["pogo"] or place["branch"] == "1.2.2"
                    rec.setdefault("near", sep["near"].iid)
                    rec.setdefault("kind", sep["kind"])
                    if place.get("mode") != rec.get("mode"):
                        rec["mode"], rec["mode_f"] = place.get("mode"), sc.frame
                    return dict(phase="slam", far=sep["far"].iid, near=sep["near"].iid, kind=sep["kind"], place=place,
                                rec=rec)
            elif rec is not None and rec.get("branch") is not None and post is None and not rec.get("post_done"):
                # #386 (the person 11-10, Sol seq 330): after both hammer stages, with both Clappers here, always back into the middle, every
                # branch (1.1 / 1.2.1 / 1.2.2 / 1.2.3)
                post = self._post_start(sc, sep, rec)
        if post is not None:
            tier = self._post_tier(sc, post)
            self._post_act(sc, post, tier)
            return dict(phase="post", far=post["far"], near=post["near"], post=post, tier=tier)
        return None

    def repick(self, sc):
        # the way into the middle is picked on each of its actions' first tick (its start: the hammer's end is no new state of its own; #386:
        # a tier change, a landing outside, a deadline: the seam strike's entry is that action's); #385: 1.2.2's strike window too (its stomp
        # entry is picked as it opens)
        ctx = sc.events.get(self.event)
        if not SEP.active() or ctx is None:
            return False
        if ctx["phase"] == "post":
            return ctx["post"].get("act_f") == sc.frame
        return ctx["place"].get("mode") == "strike" and ctx["rec"].get("mode_f") == sc.frame

    def _latched(self, sc):
        """The slam she was separated from at its start, held with its near one until both hammer stages are over: past the near one's root
        (1.2.1's crossing, 1.2.2's pogo drifting in) she still keeps outside its range and slashes the near one, never goes at the slammer."""
        if sc.geo is None:
            return None
        for s in sc.subjects:
            rec = sc.mem.get("sep_slam", {}).get(s.iid)
            if rec is None or rec.get("near") is None or s.family != SEP.CC_SLAM:
                continue
            near = next((v for v in sc.subjects if v.iid == rec["near"]), None)
            if near is None:
                continue
            a, b = SEP._span(sc.geo, s.iid)
            return dict(far=s, near=near, kind=rec.get("kind", "body"), toward=1 if float(s.pos[0]) > sc.hx else -1,
                        circles=SEP.circles_across(sc.tac, sc.t, sc.hx, a if float(s.pos[0]) > sc.hx else b))
        return None

    def _post_start(self, sc, sep, rec):
        """#386 (the person 11-10, Sol seq 330: "锤后一律回中间，除非中间有大符文"): once both hammer stages of F's slam are over, with both
        Clappers here, every branch (1.1 / 1.2.1 / 1.2.2 / 1.2.3) goes back into the middle: an intent kept until she is in the middle (on the
        floor between the two facing edges) or its seam strike met a body, a new antic (its own rules first) or a body gone. N evaded or struck
        in the slam, no standing room, no double hit: none of them prevents or ends it (each kept for the record); a live big rune in the
        middle postpones it (the ordinary rules meanwhile). Its action is chosen every tick from the current bodies (_post_tier), each action
        one of its own (_post_act: its deadline, waypoint key and entry)."""
        rec["post_done"] = True
        far, near = sep["far"], sep["near"]
        post = sc.mem["sep_post"] = dict(far=far.iid, near=near.iid, face=rec["face"], t0=sc.t, f0=sc.frame, branch=rec.get("branch"),
                                         slam_f=rec.get("f0"), near_hit=rec.get("near_hit"), strike_hit=rec.get("strike_hit"),
                                         near_evaded=rec.get("near_evaded"), air_seen=not sc.grounded, tier=None, act_f=None, acts=0)
        return post

    @staticmethod
    def _post_tier(sc, post=None):
        """#386 (Sol seq 330: geometry and action follow the current bodies; a hit or a tier change never drops the intent): the way back's
        action this tick. dict(tier: "seam" (the two facing edges at most TIER_U apart: the shared seam strike, the chain's executor), "fall"
        (wider: over the body between her and the middle, then her air side slash on it as she falls FALL_U inside its edge: 1.2.2's own
        target), "rune" (her place in the middle inside a live big rune circle: postponed); between: the body between her and the middle (on
        her side of the seam), other, x: her place, seam, gap). An action already in the air keeps its seam / fall tier until she lands."""
        geo = sc.geo
        low, high = geo["low"], geo["high"]
        small, seam, gap = SEP.seam_return(geo)
        if post is not None and post.get("tier") in ("seam", "fall") and not sc.grounded:
            small = post["tier"] == "seam"
        between, other = (low, high) if sc.hx <= seam else (high, low)
        toward = 1 if between is low else -1                    # from the between body toward the middle
        if small:
            x = seam
        else:
            room = SEP.middle_room(geo, between, other, -toward)
            x = seam if room is None else SEP.fall_x(geo, between.iid, toward, *room)
        tier = "rune" if SEP.in_circle(sc, x) else "seam" if small else "fall"
        return dict(tier=tier, between=between.iid, other=other.iid, toward=toward, x=float(x), seam=float(seam), gap=float(gap))

    @staticmethod
    def _post_act(sc, post, tier):
        """#386 (Sol seq 330: the intent apart from its action; an action's own timeout and hand-back stay): a new action of the way back on
        a tier change, a landing outside the middle (one inside it ended the intent) or its deadline (POST_ACT_F): its own waypoint key, entry
        and contact deadline."""
        why = None
        if tier["tier"] != post.get("tier"):
            why = "tier " + tier["tier"]
        elif sc.grounded and post.get("air_seen"):
            why = "landed outside the middle"
        elif type(sc.frame) is int and type(post.get("act_f")) is int and sc.frame > post["act_f"] + SEP.POST_ACT_F:
            why = "deadline"
        if why is None:
            post["air_seen"] = bool(post.get("air_seen") or not sc.grounded)
            return
        post.update(tier=tier["tier"], act_f=sc.frame, acts=post.get("acts", 0) + 1, air_seen=not sc.grounded)
        hist = post.setdefault("act_log", [])
        if len(hist) < 12:
            hist.append([sc.frame, tier["tier"], why])

    @staticmethod
    def _below_tops(sc, low, high):
        """Her box bottom under the lower of the two bodies' tops (the scene's tops); unknown: False."""
        tops = (sc.geo or {}).get("tops") or {}
        ta, tb = tops.get(low.iid), tops.get(high.iid)
        try:
            bottom = min(float(p[1]) for p in sc.ws.hero.hurtbox)
        except (AttributeError, TypeError, ValueError, IndexError):
            return False
        return ta is not None and tb is not None and bottom < min(float(ta), float(tb))

    @staticmethod
    def _short_of(sc, iid, toward):
        """Her centre not yet past that body's edge toward the middle, or no facts to tell."""
        if sc.geo is None or iid not in sc.geo["bodies"]:
            return True
        a, b = SEP._span(sc.geo, iid)
        return (sc.hx - (b if toward > 0 else a)) * toward <= 0

    def _post_vault(self, sc, post, tier):
        """The fall tier's way over the body between her and the middle as the action layer's bounded vault (#385; #386, Sol REVIEW385 1:
        no landing band: the route ends at its real air hand-back point past that body, knife_chain_waypoint end "past", its en-route
        checks for all owners, sent prefix and dash lock kept), while that body still lies between her and the middle; None once her box is
        past its inner edge (the ordinary owners: the stance, her air side slash on it) or without the facts."""
        if sc.geo is None or type(post.get("act_f")) is not int:
            return None
        n = next((s for s in sc.subjects if s.iid == tier["between"]), None)
        if n is None:
            return None
        a, b = SEP._span(sc.geo, n.iid)
        toward = tier["toward"]
        root = float(n.pos[0])
        over = (min(a, root - clapper_plans.BODY_HALF), 0., max(b, root + clapper_plans.BODY_HALF), clapper_plans.BODY_TOP)
        far = over[2] if toward > 0 else over[0]                    # the passed box's edge toward the middle (the chain's own test)
        trail = sc.geo["left"] if toward > 0 else sc.geo["right"]    # her half width toward it on her way
        if (sc.hx - far) * toward > trail + WP.VAULT_PAD:
            return None
        # its place: the hand-back point itself, beyond that edge toward the middle (vault_row takes the direction from the place: a place
        # at the fall's x, inside that box edge, pointed back over the body once she was past it: sy25_vault3 131562)
        x = far + toward * (trail + WP.VAULT_PAD + .25)
        return WP.WaypointGoal(float(x), int(post["act_f"]) + SEP.POST_ACT_F, "vault", int(post["far"]),
                               (("sep_post", int(post["far"]), round(float(post["t0"]), 4), int(post["act_f"])), 0, "vault"),
                               over=over, family=SEP.CC_SLAM, over_iid=int(n.iid), end="past")

    def _post_end(self, sc, post):
        by = {s.iid: s for s in sc.subjects}
        if by.get(post["far"]) is None or by.get(post["near"]) is None or sc.geo is None or len(sc.subjects) != 2:
            return "a body gone or no geometry"
        if any(s.state in NEW_ANTICS for s in sc.subjects):
            return "a new antic (its own rules first)"
        low, high = sc.geo["low"], sc.geo["high"]
        b1, a2 = SEP._span(sc.geo, low.iid)[1], SEP._span(sc.geo, high.iid)[0]
        if b1 < sc.hx < a2:
            if sc.grounded:
                return "in the middle"
            # dropped below both tops there: her fall slash's frames, then done (sy25_vault3 131534: the planner hopped on its landing
            # frame and the intent stayed open over the middle; sy26_vault: ended at once, it took the fall slash's frames too)
            if type(sc.frame) is int and self._below_tops(sc, low, high) and type(post.get("mid_f")) is not int:
                post["mid_f"] = sc.frame
            if type(sc.frame) is int and type(post.get("mid_f")) is int and sc.frame - post["mid_f"] >= SEP.MIDDLE_HOLD_F:
                return "in the middle (in the air)"
        else:
            post["mid_f"] = None
        small, seam, _ = SEP.seam_return(sc.geo)
        small = small or post.get("tier") == "seam"
        if small and sc.t > post["t0"] and _hit_on(sc, {low.iid, high.iid}) and abs(sc.hx - seam) <= SEP.SEAM_DONE_U:
            return "its seam strike met a body"
        return None

    def propose(self, sc):
        if not SEP.active():
            return [], "seq 312 off"
        ctx = sc.events.get(self.event)
        if ctx is None:
            return [], "no separated slam"
        if ctx["phase"] == "post":
            tier = ctx["tier"]
            if tier["tier"] == "rune":
                # (Sol seq 330: the only condition that holds the way back; the intent stays and its action is chosen again once it is over)
                return [], "after the slam: a live big rune over the middle: the way back postponed"
            target = next((s for s in sc.subjects if s.iid == tier["between"]), None)
            return ([("sep_slam", target, 1.)], None) if target is not None else ([], "after the slam: no body to pass")
        return [("sep_slam", ctx["place"]["target"], 1.)], None

    def pick_entry(self, sc, rule, target, previous):
        # Sol REVIEW383 (#384): 1.2.1 / 1.2.2 are the action owners' down slash on N: the existing EntryAttack stomp, bound by the chain to
        # F's observed slam (its approach and strike checks; after the real bounce the existing bounce goal with F's slam its responsibility and
        # the Task 183 follow-up: the middle landing with its fall slash, held off the middle while F's slam still has a hammer stage in 1.2.2:
        # GoalPrefs.hold_over). One entry for the whole slam (kept across picks: the chain never re-binds it) and none once N is struck by it
        # (its real contact completes the entry); 1.2.3, 1.1 and inside the range: none (the edge, the way out). #385: 1.2.2's entry only in
        # its strike window. #386 (Sol REVIEW385 2): the way back's seam tier is the shared seam strike's entry (scope "seam_slam", one per
        # action: event_f its first frame), bound by the chain to its seam executor; the fall tier has none (the vault waypoint).
        ctx = sc.events.get(self.event)
        if not SEP.active() or ctx is None:
            return None
        if ctx["phase"] == "post":
            tier, post = ctx["tier"], ctx["post"]
            far = next((s for s in sc.subjects if s.iid == ctx["far"]), None)
            if (tier["tier"] != "seam" or target.iid != tier["between"] or type(post.get("act_f")) is not int or far is None
                    or not _stompable(sc, target.iid)):
                return None
            if (previous is not None and getattr(previous, "scope", None) == "seam_slam"
                    and (previous.target, previous.source, previous.event_f) == (target.iid, far.iid, post["act_f"])):
                return previous
            return EntryAttack(target.iid, "stomp", far.iid, SEP.CC_SLAM, abs(float(far.pos[0]) - sc.hx), sc.t, scope="seam_slam",
                               event_f=int(post["act_f"]))
        p, rec = ctx["place"], ctx["rec"]
        # (the floor way out: inside the range on the ground; an approach in the air keeps its entry and its place bound; #385: 1.2.2's
        # only in its strike window, until its down slash meets N, side slashes before it not counting)
        if ((p["inside"] and sc.grounded) or p["branch"] not in ("1.2.1", "1.2.2") or p["target"].iid != target.iid
                or (p["branch"] == "1.2.1" and rec.get("near_hit") is not None)
                or (p["branch"] == "1.2.2" and (p.get("mode") != "strike" or rec.get("strike_hit") is not None))):
            return None
        far = next((s for s in sc.subjects if s.iid == ctx["far"]), None)
        if far is None or not _stompable(sc, target.iid):
            return None
        if (previous is not None and (previous.target, previous.source, previous.kind, getattr(previous, "scope", None))
                == (target.iid, far.iid, "stomp", "sep_slam")):
            return previous
        return EntryAttack(target.iid, "stomp", far.iid, SEP.CC_SLAM, abs(float(far.pos[0]) - sc.hx), sc.t, scope="sep_slam")

    def apply(self, sc, rule, g, target):
        ctx = sc.events.get(self.event)
        if ctx is None:
            return None
        if ctx["phase"] == "post":
            tier = ctx["tier"]
            head = "separated slam " + str(ctx["post"].get("branch")) + " after: "
            if tier["tier"] == "seam":
                # Sol seq 326 / 330: the shared seam strike (both bodies credited, no double-hit proof, no standing-gap proof)
                return Applied(stance=tier["x"], style="stomp", scene=head + "seam strike")
            return Applied(stance=tier["x"], style=None, scene=head + "into the middle", no_hit=frozenset({tier["other"]}))
        p = ctx["place"]
        return Applied(stance=float(p["stance"]), style=p["style"], scene="separated slam " + p["branch"] + (
            " " + p["mode"] if p.get("mode") else "") + (" (way out)" if p["inside"] else ""), no_hit=p["no_hit"])

    def finish(self, sc, rule, won, g, out):
        ctx = sc.events.get(self.event)
        e = out.entry_attack
        if getattr(e, "scope", None) == "sep_slam" and (not won or ctx is None or not _stompable(sc, e.target)):
            # #384 (Sol REVIEW383: the action is this slam's and this scene's, and one that can be executed now): its stomp entry ends with
            # the scene, another winner or N out of the states a strike witness reads; the chain hands an approach not yet pressed back
            # (knife_chain_air_native)
            g.entry_attack = None
            out = replace(out, entry_attack=None)
        e = out.entry_attack
        if getattr(e, "scope", None) == "seam_slam" and (
                not won or ctx is None or ctx["phase"] != "post" or ctx["tier"]["tier"] != "seam"
                or (e.target, e.event_f) != (ctx["tier"]["between"], ctx["post"].get("act_f")) or not _stompable(sc, e.target)):
            # #386: the way back's seam strike entry is its action's (its tier, its body, its first frame) and one that can be executed now;
            # the chain hands an approach not yet pressed back (knife_chain_air_native)
            g.entry_attack = None
            out = replace(out, entry_attack=None)
        if not won or ctx is None:
            return out
        near = ctx["near"]
        w = float(out.hit_w.get(near, 1.))
        if ctx["phase"] == "post":
            return self._post_finish(sc, ctx, out)
        p, rec = ctx["place"], ctx["rec"]
        e = out.entry_attack
        way_out = p["inside"] and sc.grounded       # the floor way out (the waypoint); in the air an approach keeps its entry and place bound
        if (e is not None and e.kind == "stomp" and e.target == near
                and (way_out or p["branch"] not in ("1.2.1", "1.2.2") or p["style"] is None)):
            # #384: this branch's strike on N is no down slash now (the way out; 1.2.3 / 1.1; 1.2.1 past N's inner side: its side slash there)
            kw = dict(out.hit_kw)
            if near not in out.no_hit and p["style"] is None:
                kw[near] = (w, 0., 0., 0.)
            out = replace(out, entry_attack=None, hit_kw=kw)
        if p["branch"] == "1.2.2" and p.get("mode") == "side" and near not in out.no_hit:
            # #385 (the person 11-10): side slashes on the locked N from the floor (no down slash, no jump for it: the strike window's own)
            kw = dict(out.hit_kw)
            kw[near] = (w, 0., 0., 0.)
            out = replace(out, hit_kw=kw, no_pogo=frozenset(out.no_pogo) | {near}, ground_hit=frozenset(out.ground_hit) | {near})
        if p["branch"] == "1.2.2" and not p["inside"]:
            # #384 (the person: the way into the middle once both hammer stages of this slam are over): a real bounce on N outside the range
            # keeps the chain's follow-up off the middle while F's slam still has a hammer stage (hold_over, also once N is no target any
            # more; inside the range there is no waiting: the action owners' own checks take her out)
            out = replace(out, hold_over=frozenset({near}))
            e = out.entry_attack
            if p.get("strike") is not None and e is not None and e.kind == "stomp" and e.target == near:
                # #385: the strike window's down slash: its short jump, her aim over N's outer part, its contact outside the range by the frame
                # N unlocks (the chain's stomp_plan bound and its late / past hand-back)
                out = replace(out, strike_bound=p["strike"])
        far = sc.subject(ctx["far"])
        if p["inside"] and rec.get("f0") is not None and type(sc.frame) is int and far.state in ("Slam Antic", "Slam 0"):
            by_f = int(rec["f0"]) + SEP.SLAM_FIRST_F - SEP.ESCAPE_LEAD_F
            if sc.frame < by_f:
                out = replace(out, waypoint=WP.WaypointGoal(float(p["escape_x"]), by_f, "retreat", far.iid,
                                                            (("sep_slam", far.iid, round(float(rec["t0"]), 4)), 0, "escape"),
                                                            family=SEP.CC_SLAM))
        return out

    def _post_finish(self, sc, ctx, out):
        """#386: the way back's outputs. Seam tier (Sol seq 326 / REVIEW385 2): the shared seam strike's chain stomp (its entry from
        pick_entry; GoalPrefs.strike_bound kind "seam": the air key only up to the seam, its rows preferred with her centre at the contact on
        the seam side of the target's root, by the action's deadline; out of reach, the target's ordinary stomp: knife_chain_transfer); for
        the rows down slashes only on either body (no floor slash on the unlocked N: C14 sy14_122; no ban on the down slash either, which
        left her falling onto N unstruck: sy23_seam 131570). Fall tier: the vault over the body between her and the middle while she is short
        of its inner edge (no hit on it then), then her air side slash on it (and its down slash)."""
        post, tier = ctx["post"], ctx["tier"]
        between, other = tier["between"], tier["other"]
        b = next((s for s in sc.subjects if s.iid == between), None)
        if b is None:
            return out
        if tier["tier"] == "seam":
            toward = 1 if tier["seam"] > float(b.pos[0]) else -1
            kw = dict(out.hit_kw)
            for i in (between, other):
                if i not in out.no_hit:
                    kw[i] = (0., 0., 0., float(out.hit_w.get(i, 1.)))
                    out = _air_ok(out, i)
            out = replace(out, hit_kw=kw)
            e = out.entry_attack
            if getattr(e, "scope", None) == "seam_slam" and e.target == between and type(post.get("act_f")) is int:
                out = replace(out, strike_bound=(between, float(tier["seam"]), float(b.pos[0]), toward,
                                                 int(post["act_f"]) + SEP.POST_ACT_F, None, "seam"))
            return out
        wp = self._post_vault(sc, post, tier)
        if self._short_of(sc, between, tier["toward"]):
            return replace(out, no_hit=frozenset(out.no_hit) | {between}, waypoint=wp)
        kw = dict(out.hit_kw)
        if between not in out.no_hit:
            w = float(out.hit_w.get(between, 1.))
            kw[between] = (w, 0., 0., w)
        out = _air_ok(replace(out, hit_kw=kw), between)
        return out if wp is None else replace(out, waypoint=wp)

    def log(self, sc, out):
        ctx = sc.events.get(self.event)
        if ctx is None:
            return {"clapper_sep_slam": None}
        wp = None if out.waypoint is None else [out.waypoint.x, out.waypoint.by_f, out.waypoint.kind, out.waypoint.end]
        if ctx["phase"] == "post":
            e = out.entry_attack
            return {"clapper_sep_slam": dict(
                phase="post", waypoint=wp, now=ctx["tier"],
                entry=None if getattr(e, "scope", None) != "seam_slam" else [e.target, e.source, e.event_f],
                strike_bound=None if out.strike_bound is None else [
                    round(float(v), 3) if type(v) in (int, float) else v for v in out.strike_bound],
                **{k: v for k, v in ctx["post"].items()})}
        p, rec = ctx["place"], ctx["rec"]
        return {"clapper_sep_slam": dict(phase="slam", kind=ctx["kind"], far=ctx["far"], near=ctx["near"], branch=p["branch"],
                                         edge=round(float(p["edge"]), 3), stance=round(float(p["stance"]), 3), inside=p["inside"],
                                         style=p["style"], no_hit=sorted(p["no_hit"]), antic_f=rec.get("f0"), seen=rec.get("seen"),
                                         face=rec["face"], waypoint=wp, mode=p.get("mode"), mode_why=p.get("mode_why"),
                                         strike=None if p.get("strike") is None else [
                                             round(float(v), 3) if type(v) in (int, float) else v for v in p["strike"]],
                                         shallow_122=p.get("shallow_122"), near_hit=rec.get("near_hit"),
                                         strike_hit=rec.get("strike_hit"), near_evaded=rec.get("near_evaded"))}


class RuneDownSlash(Tactic):
    """Plan 2.1 / 2.2: while a small rune is on (a cast, or a bomb not yet over near her and the bodies: the shared per-bomb forecast).
    Separated from the caster by a live big rune: at that circle's outer edge on her side (the existing low hop takes the bombs), the caster
    not hit (2.1). Otherwise down slashes, the target in the order both > F > N: the seam when both near body edges lie within one blade at
    level tops (the planner's rows score each body's own predicted contact: one body met is a single hit), else the caster when nothing stands
    between her and it, else the other one; no gap is required and the end of the rune is not waited for. Re-chosen on every call: the target
    she follows when it evades is the current one (the evade chase reads it); a strike already sent keeps its own target (its owner's)."""
    name = "small rune down slash"
    event = "rune_down"
    scores = {"rune_down": 120.}
    excluded_by = ("middle_jump", "cluster", "intercept_hold")   # a running jump plan keeps its own stages

    def observe(self, sc):
        mem = sc.mem
        was = bool(mem.get("rune_on"))
        need = was or any(s.family == SEP.CC_CAST for s in sc.subjects)
        bombs = SEP.bombs_now(sc.tac) if need else None
        on, casters = SEP.rune_on(sc, bombs) if need else (False, set())
        mem["rune_on"] = on
        mem["rune_bombs_now"] = bombs         # #384: this call's forecast for the strike's own coverage (_decide)
        if on and casters:
            mem["rune_casters"] = sorted(casters)
        if was and not on:
            mem["rune_end"] = dict(t=sc.t, f=sc.frame, casters=list(mem.get("rune_casters") or ()))
        if not on or sc.geo is None:
            return None
        return dict(casters=sorted(casters), bombs=None if bombs is None else int(len(bombs)), new=not was)

    def repick(self, sc):
        # a pick when the rune turns on by its bombs alone, or when the down slash's target changes (the evader crossing the other one)
        ctx = sc.events.get(self.event)
        if ctx is None or not SEP.active():
            return False
        if ctx["new"]:
            return True
        g = sc.tac.goal
        if sc.mem.get("winner") != "rune_down" or g is None:
            return False
        # (a decision with nothing she can strike asks a pick too: another rule takes the scene). This call's decision is kept for its
        # propose / apply / log (#384: one decision per call, its strike coverage read once)
        ctx["decision"] = d = self._decide(sc, ctx)
        return g.target != d["target"]

    def _decide(self, sc, ctx):
        geo, hx = sc.geo, sc.hx
        subs = sorted(sc.subjects, key=lambda s: (abs(float(s.pos[0]) - hx), s.iid))
        casters = [s for s in subs if s.iid in ctx["casters"]] or subs
        F = next((s for s in casters if SEP.reachable(sc, s, next(v for v in subs if v.iid != s.iid))), casters[0])
        N = next(v for v in subs if v.iid != F.iid)
        a, b = SEP._span(geo, F.iid)
        circles = SEP.circles_across(sc.tac, sc.t, hx, a if float(F.pos[0]) > hx else b)
        if circles:
            # 2.1: at the outer circle's edge on her side; what she reaches outside it may be hit, never the caster across it
            side = -1 if float(F.pos[0]) > hx else 1
            half = geo["right"] if side < 0 else geo["left"]
            edge = (min(lo for lo, _ in circles) - half - .25) if side < 0 else (max(hi for _, hi in circles) + half + .25)
            n_ok = SEP.reachable(sc, N, F)
            return dict(case="2.1 rune between", target=(N if n_ok else F).iid, stance=float(edge), style=None,
                        no_hit=frozenset({F.iid}) if n_ok else frozenset({F.iid, N.iid}), circles=[list(c) for c in circles])
        ok, seam = SEP.double_intent(geo)
        # Sol REVIEW383 (X14, #384): a strike whose own place is covered by the small rune's bombs over its whole window is not one she can
        # take now (rune_bombs.occupied at her contact height and time), whatever stands between
        bombs = sc.mem.get("rune_bombs_now")
        cov = []                                  # (the record: the strike places read covered)

        def covered(s, x, key):
            c = SEP.strike_covered(sc, s, x, bombs)
            if c:
                cov.append(key)
            return c

        f_ok = SEP.reachable(sc, F, N) and not covered(F, float(F.pos[0]), F.iid)
        n_ok = SEP.reachable(sc, N, F) and not covered(N, float(N.pos[0]), N.iid)
        if ok and not covered(F, seam, "seam"):
            return dict(case="2.2 both", target=F.iid, stance=seam, style="stomp", no_hit=frozenset(), covered=cov)
        if f_ok:
            return dict(case="2.2 caster", target=F.iid, stance=float(F.pos[0]), style="stomp", no_hit=frozenset(), covered=cov)
        if n_ok:
            return dict(case="2.2 other", target=N.iid, stance=float(N.pos[0]), style="stomp", no_hit=frozenset(), covered=cov)
        # nothing she can strike now: no intent is held over the bombs (the existing rules: avoidance, the low hop)
        return dict(case="2.2 none strikable", target=None, stance=None, style=None, no_hit=frozenset(), covered=cov)

    def propose(self, sc):
        if not SEP.active():
            return [], "seq 312 off"
        ctx = sc.events.get(self.event)
        if ctx is None:
            return [], "no small rune on"
        ctx["decision"] = d = ctx.get("decision") or self._decide(sc, ctx)
        if d["target"] is None:
            return [], "small rune: no strike she can take now (bombs over every strike place)"
        return [("rune_down", sc.subject(d["target"]), 1.)], None

    def pick_entry(self, sc, rule, target, previous):
        return None

    def apply(self, sc, rule, g, target):
        ctx = sc.events.get(self.event)
        d = None if ctx is None else (ctx.get("decision") or self._decide(sc, ctx))
        if d is None:
            return None
        ctx["decision"] = d
        if d["target"] is None:
            return Applied(scene="small rune: " + d["case"])     # (until the pick this asks hands the scene on)
        return Applied(stance=d["stance"], style=d["style"], scene="small rune: " + d["case"], no_hit=d["no_hit"])

    def finish(self, sc, rule, won, g, out):
        # 2.2 is down slashes only (the person: until the rune is over, down slash what she reaches): the other body's credit is its down slash
        # too, from the air (a side slash on the ground among the rings is no part of it); a double then scores both bodies' own contacts
        ctx = sc.events.get(self.event)
        d = None if ctx is None else ctx.get("decision")
        if not won or d is None or d["style"] != "stomp":
            return out
        kw = dict(out.hit_kw)
        down = {s.iid for s in sc.subjects if s.iid != g.target and s.iid not in out.no_hit}
        for iid in down:
            kw[iid] = (0., 0., 0., float(out.hit_w.get(iid, 1.)))
        return replace(out, hit_kw=kw, ground_hit=frozenset(out.ground_hit) - down, no_pogo=frozenset(out.no_pogo) - down,
                       ground_first=frozenset(out.ground_first) - down)

    def log(self, sc, out):
        ctx = sc.events.get(self.event)
        if ctx is None:
            return {"clapper_rune_down": None}
        d = ctx.get("decision")
        return {"clapper_rune_down": dict(casters=ctx["casters"], bombs=ctx["bombs"], **({} if d is None else dict(
            case=d["case"], target=d["target"], stance=None if d["stance"] is None else round(float(d["stance"]), 3), style=d["style"],
            no_hit=sorted(d["no_hit"]), covered=d.get("covered"))))}


class RuneAfter(Tactic):
    """Plan 2.3: once the small rune has passed by the shared per-bomb state, one strike chosen by the gap between the two near body edges:
    at most TIER_U (exactly at it too) a down slash aimed at the middle of the two, whatever it meets (no double-hit proof first); past it
    the hittable one (on the ground, in no attack) farther from its nearest wall, her fall FALL_U from its edge inside the gap with a side
    slash on the way down (no landing first, not the gap's centre). It ends with a real hit on either, her landing after it began, a new
    antic, the small rune on again or POST_S; then the ordinary rules (#379's stacked follow-up among them)."""
    name = "small rune end"
    event = "rune_after"
    scores = {"rune_after": 118.}
    excluded_by = ("middle_jump", "cluster", "intercept_hold")   # a running jump plan keeps its own stages

    def observe(self, sc):
        mem = sc.mem
        ctx = mem.get("rune_after")
        end = mem.pop("rune_end", None)
        if end is not None and sc.geo is not None and len(sc.subjects) == 2:
            ctx = mem["rune_after"] = self._start(sc, end)
        if ctx is not None:
            why = self._end(sc, ctx)
            if why is not None:
                mem["rune_after"] = ctx = None
                released(sc, self, why)
        return ctx

    def repick(self, sc):
        # the rune's end is no state change of either body: the one strike is picked on its first tick
        ctx = sc.events.get(self.event)
        return SEP.active() and ctx is not None and ctx["f0"] == sc.frame

    def _start(self, sc, end=None):
        from .gauntlet import JT
        geo = sc.geo
        low, high = geo["low"], geo["high"]
        gap = SEP.gap_of(geo)
        here = {s.iid for s in sc.subjects}
        source = next((c for c in (end or {}).get("casters") or () if c in here), None)
        base = dict(gap=float(gap), t0=sc.t, f0=sc.frame, air_seen=not sc.grounded, source=source)
        small, seam, _ = SEP.seam_return(geo)          # #385: the shared small-gap decision (the same TIER_U and seam as before)
        if small:
            if not SEP.place_clear(sc, seam):
                # Sol #382 R1: the middle in or across a live big rune circle is no strike she can take now: the existing rules
                sc.tac.last.setdefault("clapper_sep_notes", []).append(dict(what="small rune end: the middle in or across a live big rune",
                                                                            gap=gap, f=sc.frame))
                return None
            target = min((low, high), key=lambda s: (abs(float(s.pos[0]) - sc.hx), s.iid))
            return dict(base, tier="seam", target=target.iid, stance=float(seam), style="stomp")
        lo = SEP._span(geo, low.iid)[1] + JT["pad"] + geo["left"]
        hi = SEP._span(geo, high.iid)[0] - JT["pad"] - geo["right"]
        # Sol #382 R1: first the ones she can strike now (on the ground, in no attack, its fall place clear of every live big rune circle and
        # her way there crossing none), then of those the one farther from its nearest wall; none: the existing rules
        cands = []
        for s in (low, high):
            if s.state in AIR or s.family in SEP.ATTACKS:
                continue
            x = SEP.fall_x(geo, s.iid, 1 if s.iid == low.iid else -1, lo, hi)
            if SEP.place_clear(sc, x):
                cands.append((s, x))
        if not cands:
            sc.tac.last.setdefault("clapper_sep_notes", []).append(dict(what="small rune end: nothing hittable", gap=gap, f=sc.frame))
            return None
        chosen, x = max(cands, key=lambda c: (SEP.wall_room(geo, c[0]), -c[0].iid))
        return dict(base, tier="fall", target=chosen.iid, stance=float(x), style=None,
                    wall_room={str(s.iid): round(SEP.wall_room(geo, s), 3) for s in (low, high)},
                    strikable=sorted(int(s.iid) for s, _ in cands))

    def _end(self, sc, ctx):
        if all(s.iid != ctx["target"] for s in sc.subjects):
            return "its target is gone"
        if sc.t > ctx["t0"] and _hit_on(sc, {s.iid for s in sc.subjects}):
            return "a hit landed"
        if not sc.grounded:
            ctx["air_seen"] = True
        elif ctx["air_seen"] and sc.t > ctx["t0"]:
            return "landed"
        if any(s.state in NEW_ANTICS for s in sc.subjects):
            return "a new antic"
        if sc.mem.get("rune_on"):
            return "the small rune is on again"
        if sc.t - ctx["t0"] > SEP.POST_S:
            return "timed out"
        return None

    def propose(self, sc):
        if not SEP.active():
            return [], "seq 312 off"
        ctx = sc.events.get(self.event)
        if ctx is None:
            return [], "no small rune just over"
        return [("rune_after", sc.subject(ctx["target"]), 1.)], None

    def pick_entry(self, sc, rule, target, previous):
        # Sol REVIEW383 (#384): 2.3 at most 2.5 u is one stomp entry at the seam (the action owners' down slash; this rune end the event it is
        # bound to: no source move goes on, so one entry per rune end, never restarted by a re-pick); its real hit / bounce / landing is the
        # result. The fall tier keeps the rows' side slash in the air.
        ctx = sc.events.get(self.event)
        if (not SEP.active() or ctx is None or ctx["tier"] != "seam" or ctx["target"] != target.iid or ctx.get("source") is None
                or not _stompable(sc, target.iid)):
            return None
        if (previous is not None and getattr(previous, "scope", None) == "rune_end" and previous.event_f == ctx["f0"]
                and previous.target == target.iid):
            return previous
        src = next((s for s in sc.subjects if s.iid == ctx["source"]), None)
        if src is None:
            return None
        return EntryAttack(target.iid, "stomp", src.iid, "RUNE_END", abs(float(src.pos[0]) - sc.hx), sc.t, scope="rune_end",
                           event_f=int(ctx["f0"]))

    def apply(self, sc, rule, g, target):
        ctx = sc.events.get(self.event)
        if ctx is None:
            return None
        return Applied(stance=ctx["stance"], style=ctx["style"], scene="small rune end: " + ctx["tier"])

    def finish(self, sc, rule, won, g, out):
        ctx = sc.events.get(self.event)
        e = out.entry_attack
        if getattr(e, "scope", None) == "rune_end" and (not won or ctx is None or e.event_f != ctx["f0"] or not _stompable(sc, e.target)):
            # #384 (Sol REVIEW383: the action is this phase's, and one that can be executed now): the closing strike ends with its rune
            # end's scene (its end, another winner, a later rune end) or its target out of the states a strike witness reads (an evade:
            # no strike, only a way into its path); the chain hands an approach not yet pressed back (knife_chain_air_native)
            g.entry_attack = None
            out = replace(out, entry_attack=None)
        if won and ctx is not None and ctx["tier"] == "fall":
            out = _air_ok(out, ctx["target"])
        e = out.entry_attack
        if (won and ctx is not None and ctx["tier"] == "seam" and getattr(e, "scope", None) == "rune_end" and e.target == ctx["target"]
                and type(ctx.get("f0")) is int and sc.geo is not None):
            # #385 (the person 11-10, Sol seq 326: the shared seam strike, aligned with the seam): the chain's stomp aims at the seam (its side
            # key only up to it) and keeps strike rows whose contact has her centre on the seam side of the target's root, by POST_S
            t = sc.subject(ctx["target"])
            other = next((s for s in sc.subjects if s.iid != t.iid), None)
            if t is not None and other is not None:
                sign = 1 if float(other.pos[0]) > float(t.pos[0]) else -1
                out = replace(out, strike_bound=(t.iid, float(ctx["stance"]), float(t.pos[0]), sign,
                                                 int(ctx["f0"]) + int(round(SEP.POST_S * 60)), None, "seam"))
        return out

    def log(self, sc, out):
        ctx = sc.events.get(self.event)
        return {"clapper_rune_after": None if ctx is None else {k: v for k, v in ctx.items()}}


@dataclass(frozen=True)
class Table:
    tactics: tuple
    observe: tuple
    rules: dict
    scores: dict


def _table(tactics, observe_first=()):
    order = (SeparatedSlam, RuneDownSlash, RuneAfter,       # (seq 312: the small rune's end is read after its own observation)
             PlannedMiddle, MiddleJump, ClusterLure, ClusterAttack, ClusterVault, ClusterRoute, PlannedIntercept, JumpIntercept,
             PlannedTakeoff, FocusTakeoff, MiddleReturn)
    return Table(tactics, tuple(observe_first) + tuple(t for k in order for t in tactics if type(t) is k),
                 {rule: t for t in tactics for rule in t.scores}, {rule: t.scores[rule] for t in tactics for rule in t.scores})


# The pool order (an equal score and keep flag goes to the earlier offer) and the observation order (an event that
# holds the scene is observed before the ones that wait for it).
TACTICS = (FocusKeep(), MiddleJump(), JumpIntercept(), NearThreat(), FocusTakeoff(), EnterMiddle(), OuterRetreat(),
           FlipInward(), TightOverhead(), MiddleReturn(), ClusterRoute())
OBSERVE = tuple(t for k in (MiddleJump, ClusterRoute, JumpIntercept, FocusTakeoff, MiddleReturn)
                for t in TACTICS if type(t) is k)
RULES = {rule: t for t in TACTICS for rule in t.scores}
DEFAULT_SCORES = {rule: t.scores[rule] for t in TACTICS for rule in t.scores}
LEGACY_TABLE = Table(TACTICS, OBSERVE, RULES, DEFAULT_SCORES)
PLAN_TABLE = _table((PlannedKeep(), PlannedMiddle(), PlannedIntercept(), NearThreat(), PlannedTakeoff(), EnterMiddle(),
                     OuterRetreat(), FlipInward(), TightOverhead(), MiddleReturn(), ClusterLure(), ClusterAttack())
                    + ((SeparatedSlam(), RuneDownSlash(), RuneAfter(), ClusterVault()) if SEP.ENABLED else ()),
                    observe_first=(PlanRun(),))


def table():
    """The tactic set of this call: the plan units only with SSBOT_FORUM_TWO_PLAN=1."""
    return PLAN_TABLE if clapper_plans.ENABLED else LEGACY_TABLE
