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

from ssbot.combat import forum_v2

from . import clapper_middle
from .clapper_scene import AIR, ANTIC, JUMPS, NEAR, ground_stance, standing_gap
from .forum_local import clapper_facing
from .modes import EntryAttack, ReturnRequest

BAIT_WIDTHS = 2.5          # the person (seq 230): back off about 2.5 visible body widths, return on the take-off
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
        return [("middle", max(sc.subjects, key=lambda s: (sc.room[s.iid], -abs(s.pos[0] - sc.hx))), 1.)], None


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


class FlipInward(Tactic):
    """Outside the pair with the default target in a near antic: the inward flip's stance and stomp style (an
    intent; the flip itself is the action owners')."""
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
        return [("overhead", sc.default, 1.)], None

    def apply(self, sc, rule, g, target):
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
            if m["near"] and not (min(roots) <= hx <= max(roots) and standing_gap(geo) is not False):
                mem["back"] = dict(m, iid=s.iid, end_t=t, end_hx=hx, end_state=s.state, offered=False,
                                   **({} if frame is None else {"end_f": frame}))
    due = mem.get("back")
    if due is None or geo is None or quiet_from is not None:
        return None
    if any(s.family in TWO_ATTACK_FAMS for s in subjects):
        return None
    room = {s.iid: (float(s.pos[0]) - geo["xa"] if s.iid == geo["low"].iid else geo["xb"] - float(s.pos[0]))
            for s in subjects}
    target = max(subjects, key=lambda s: (room[s.iid], -abs(float(s.pos[0]) - hx)))   # as the "middle" rule
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
        return home

    def repick(self, sc):
        # a pick when the return becomes live or stops being live (back_live: whether it was at the last call)
        live = sc.events.get(self.event) is not None
        ask = live != sc.mem.get("back_live", False)
        sc.mem["back_live"] = live
        return ask

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
        return [("back", sc.subject(home["target"]), 1.)], None

    def pick_entry(self, sc, rule, target, previous):
        return None

    def apply(self, sc, rule, g, target):
        if sc.events.get(self.event) is None:
            return None
        pose = sc.back_pose = return_pose(sc.tac, target, sc.geo, sc.hx)
        return Applied(stance=pose["stance"], style="stomp" if pose["posture"] == "air" else None,
                       scene="middle return " + pose["posture"],
                       no_hit=frozenset() if pose["crossed"] == g.target else frozenset({pose["crossed"]}))

    def finish(self, sc, rule, won, g, out):
        pose = sc.back_pose if won else None
        mem, t, geo = sc.mem, sc.t, sc.geo
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


# The pool order (an equal score and keep flag goes to the earlier offer) and the observation order (an event that
# holds the scene is observed before the ones that wait for it).
TACTICS = (FocusKeep(), MiddleJump(), JumpIntercept(), NearThreat(), FocusTakeoff(), EnterMiddle(), OuterRetreat(),
           FlipInward(), TightOverhead(), MiddleReturn(), ClusterRoute())
OBSERVE = tuple(t for k in (MiddleJump, ClusterRoute, JumpIntercept, FocusTakeoff, MiddleReturn)
                for t in TACTICS if type(t) is k)
RULES = {rule: t for t in TACTICS for rule in t.scores}
DEFAULT_SCORES = {rule: t.scores[rule] for t in TACTICS for rule in t.scores}
