"""The finite online pogo-chain entry on the SAME target (Task 179 #308, Sol seq 229; Tasks 143 / 145 / 148).

After a REAL DownSlash hit + bounce on the target L2 still names, B2 keeps one normal baseline (the centered next knife,
press at desired 33 from the hit, no umbrella). At the first STATE showing that same instance in Slam Antic (state ua)
the row is the unique one for that ua (knife_chain_bounce_rows148.json: Task 148's rows at the real 823 hit STATE 2915,
the all-9 witness with the largest POSITIVE send slack; zero-slack-only first sightings are not rows). That ONE stream
(the keys actually sent before its cut + the row's suffix) is re-verified once (verify: every timing variant, no pick)
from the tracker's own state of the sighting STATE (which carries the real bounce and its observed protection; the first
pogo is never injected again), its in-flight key, the observed dt and the target's pose. The verification runs in the
same thread after that tick's send (its cost belongs to the next tick); the sighting tick sends the baseline key, which
is still common to the row (positive slack), and the row switches on the next tick only if its first differing key can
still be sent. Keys already sent are never changed or shifted; each later knife continues only on the REAL next hit at
the verified Update and physics step; observed physics steps must keep the verified pairing. Anything else is
'uncovered' (B2 hands back with its failure exposure). Cross-target, a face-hook bounce, a dash exit and unverified
phases are uncovered here.

Model results and verified rows are evidence for one stream from one start, never a hit receipt."""
from dataclasses import dataclass, field
from functools import lru_cache
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from ssbot.knowledge import kinematics as K
from .knife_chain_format import MASK_NAMES as B

ROWS_PATH = Path(__file__).with_name("knife_chain_bounce_rows148.json")
TABLE = Path(__file__).with_name("knife_chain_bounce_v01.json")       # the air_bounce program (opt-in)
FIRST_ONSET_FROM = 12      # Root's evaluate searches the next swing's onset from state 12 (rising edge)
PROTECT = 8                # DOWNSPIKE_INVULNERABILITY_STEPS (serialized 8; real 2915 counter 8, 2916 7)


def knife(n, press, jopen=None, release=None, lo=0):
    """The one parameter interface for the baseline and every row: J [open, release), D [max(lo, press-1), press+3),
    A [press, press+2), by desired index from the hit (index 0 = the hit frame)."""
    return np.asarray([(B["J"] if jopen is not None and jopen <= j < release else 0)
                       | (B["D"] if max(lo, press - 1) <= j < press + 3 else 0)
                       | (B["A"] if press <= j < press + 2 else 0) for j in range(n)], np.int64)


@lru_cache(maxsize=1)
def rows():
    """{ua: row} with the full masks (Task 148's construction: the normal knife up to the cut; from it the normal second
    knife kept or not, plus the row's knife)."""
    d = json.loads(ROWS_PATH.read_text(encoding="utf-8"))
    total, normal = int(d["total"]), knife(int(d["total"]), int(d["normal_press"]))
    out = {}
    for r in d["rows"]:
        cut = int(r["cut"])
        m = normal.copy() if r["keep_normal_second"] else np.r_[normal[:cut], np.zeros(total - cut, np.int64)]
        if r["open"] is not None:
            m[int(r["open"]):int(r["release"])] |= B["J"]
        m |= knife(total, int(r["press"]), lo=cut) & (B["D"] | B["A"])
        first = next(j for j in range(cut, total) if m[j] != normal[j])
        if first != int(r["first_difference"]) or np.any(m[:cut] != normal[:cut]):
            raise ValueError(f"bounce table row ua {r['ua']}: masks disagree with Task 148's record")
        out[int(r["ua"])] = NS(ua=int(r["ua"]), H=int(r["H"]), cut=cut, masks=m, first=first,
                               contacts=[tuple(c) for c in r["contacts"]], slack=int(r["slack"]))
    return out


def normal_keys(n=None):
    d = json.loads(ROWS_PATH.read_text(encoding="utf-8"))
    return knife(int(n or d["total"]), int(d["normal_press"]))


# ---- one stream's re-verification from the ACTUAL start (Task 145's stream145, production functions only) --------------

@dataclass(frozen=True)
class Start:
    S: np.ndarray              # [K] hero state of STATE s
    hold: object               # K.HoldState of STATE s
    dt: float                  # observed per-Update dt (explicit; not params.frame_time)
    params: object
    terrain: object
    s: int = 0                 # state index of S relative to the real hit (state 1 = the hit's STATE)
    rel0: int = 0              # physics steps from the hit's STATE to STATE s (observed fc difference)


@dataclass(frozen=True)
class Target:
    iid: int
    x: float
    y: float
    face: int                  # +1 facing right (flipX True)
    ua: int                    # state index of the first STATE showing it in Slam Antic


@lru_cache(maxsize=1)
def timelines():
    """The nominal SlamTimeline and its 8 variants, read once (warm() loads them before combat)."""
    from .pogo_slam import SlamTimeline
    return (SlamTimeline.load(),) + tuple(SlamTimeline.variants())


def warm(params):
    """Before combat (opt-in table only): the rows, the timelines and one verification on a synthetic start, so the
    first online verification never compiles or reads files. Compile only: no admission or contact evidence."""
    import time
    t0 = time.perf_counter()
    row = rows()[5]
    S = K.initial_state(params, 30., 9.7, ground=False, mode=K.M_NORMAL)
    start = Start(S, K.HoldState.idle(1), 1 / 60, params, K.Terrain2D.empty(), row.ua, 0)
    cmd = list(normal_keys()[row.ua:row.cut]) + list(row.masks[row.cut:])
    verify(start, Target(1, 30.5, 7.45, -1, row.ua), cmd, len(row.contacts), timelines())
    return {"family": "bounce_table", "ms": (time.perf_counter() - t0) * 1000., "scope": "compile only"}


def _roll(start, cmd, ev, cache):
    from .holdfilter import hold_filter_jit
    from .knife_chain_air import _trace_events
    key = np.asarray(ev, np.int64).tobytes()
    if key not in cache:
        lat, _ = hold_filter_jit(np.asarray(cmd, np.int64)[None], start.hold)
        cache[key] = _trace_events(np.asarray(start.S, float).reshape(K.K), lat[0], ev, 0.0, float(start.dt),
                                   start.params.vector()[None, :], start.terrain.packed())
    return cache[key]


def _counts(states, dt, fdt):
    out = [0]
    for i in range(1, states.shape[1]):
        z = states[:, i - 1]
        d = float(np.float32(dt * (z[K.TS] if z[K.WF_S] == 1. else z[K.TS] * z[K.WF_S])))
        out.append(out[-1] + int(math.floor(float(z[K.ALPHA]) + d / fdt + 1e-9)))
    return np.asarray(out, np.int64)


def _onset_after(states, start):
    a = states[K.ATTACKING]
    return next((i for i in range(max(start, 1), len(a)) if a[i] > 0 and a[i - 1] <= 0), None)


def _evaluate(start, target, cmd, n_strikes, tl, cache):
    from . import air_chain as AC, pogo_model as PM
    s, ua = int(start.s), int(target.ua)
    if s > ua:
        return {"valid": False, "reason": f"start state {s} after the first sighting {ua}"}
    ctx = AC.Ctx(target.iid, float(target.x), float(target.y), int(target.face), s - ua + 1, None,
                 float(start.S[K.PX]), int(start.S[K.FACE]))
    ev = np.zeros(len(cmd), np.int64)
    if s == 0:
        ev[0] = K.EV_POGO
    actual, ages = [], []
    for _ in range(n_strikes):
        st, bx, ps, fl, gm = _roll(start, cmd, ev, cache)
        pi = _onset_after(st, FIRST_ONSET_FROM - s if not actual else actual[-1] + 1)
        if pi is None:
            return {"valid": False, "reason": "no attack onset"}
        if int(st[K.ATK_PDIR, pi]) != 2 or bool(st[K.GROUND, pi]):
            return {"valid": False, "reason": "swing not an airborne down slash"}
        c = int(AC._contacts(NS(flags=fl[None], pos=ps[None]), np.array([pi]), np.array([int(st[K.FACE, pi])]), ctx, tl,
                             "b")[0])
        if c < 0:
            return {"valid": False, "reason": "no real dynamic contact with the target"}
        if not PM.ACTIVE[0] <= c - pi <= PM.ACTIVE[1]:
            return {"valid": False, "reason": "contact outside ACTIVE"}
        actual.append(c)
        ages.append(c - pi)
        ev[c - 1] = K.EV_POGO
    st, bx, ps, fl, gm = _roll(start, cmd, ev, cache)
    cs = _counts(st, start.dt, start.params.fdt)
    rel = (cs - cs[1 - s]) if s == 0 else (int(start.rel0) + cs)
    idx = np.arange(len(fl))
    fl = fl.copy()
    fl[1:] &= ~K.F_INVULN
    fl[(idx + s >= 1) & (rel < PROTECT)] |= K.F_INVULN                     # the real hit's observed remaining window
    for c in actual:
        fl[(idx >= c) & (cs - cs[c] < PROTECT)] |= K.F_INVULN              # this row's own contacts only
    last = actual[-1]
    if not fl[last] & K.F_INVULN:
        return {"valid": False, "reason": "no bounce protection"}
    hs = next(k for k, name in enumerate(tl.state) if name == "Slam 1")
    hammer = int(rel[ua + hs - 1 - s] + 1)
    cstep = int(rel[last])
    left, right = hammer - cstep, cstep + PROTECT - 1 - (hammer + 2)
    through = min(ua + next(k for k, name in enumerate(tl.state) if name == "after") + 2 - s, len(fl) - 1)
    unsafe = int(AC._first_unsafe(NS(flags=fl[None], pos=ps[None], box=bx[None]), ctx, tl, np.array([actual], np.int64),
                                  np.array([through]), np.array([1]))[0])
    return {"valid": True, "contacts_update": [s + c for c in actual], "contact_age_updates": ages,
            "contact_physics": [int(rel[c]) for c in actual], "protection": [cstep, cstep + PROTECT - 1],
            "hammer": [hammer, hammer + 2], "margin_before": left, "margin_after": right,
            "unsafe_update": None if unsafe < 0 else s + unsafe, "through_update": s + through,
            "accepted": left >= 2 and right >= 2 and unsafe < 0, "rel": rel}


def verify(start, target, cmd, n_strikes, tls=None):
    """All timing variants of the SAME stream; no favourable pick. cmd[0] is the key applied at desired index s."""
    tls = timelines() if tls is None else tls
    cache = {}
    per = [_evaluate(start, target, cmd, n_strikes, tl, cache) for tl in tls]
    ok = all(p.get("accepted") for p in per)
    why = None if ok else next((f"variant {i}: " + (p.get("reason") or
                                f"margins {p['margin_before']}/{p['margin_after']} unsafe {p['unsafe_update']}"))
                               for i, p in enumerate(per) if not p.get("accepted"))
    nominal = per[0]
    rel = None if not nominal.get("valid") else {int(start.s) + i: int(v) for i, v in enumerate(nominal["rel"])}
    return {"pass": ok, "why": why, "per_variant": [{k: v for k, v in p.items() if k != "rel"} for p in per],
            "rel_by_state": rel, "receipt": False}


# ---- the state machine (Task 145's BounceEntry145, same target, positive-slack rows, verify after send) ---------------

@dataclass
class Chain:
    iid: int
    hit_frame: int
    hit_fc: int
    instance_t0: float | None
    sent: dict = field(default_factory=dict)
    seen: dict = field(default_factory=dict)
    state: str = "baseline"          # baseline | pending | switched | done | uncovered | handback
    row: object = None
    pending: object = None           # (row, start, target, cmd) to verify after this tick's send
    verified: dict = None
    reason: str = ""
    next_contact: int = 0
    verify_ms: float | None = None


class BounceTable:
    def __init__(self, n=160):
        self.rows = rows()
        self.normal = normal_keys(n)
        self.press = int(np.flatnonzero(self.normal & B["A"])[0])     # the normal knife's press, desired index from the hit
        self.n = n
        self.chain = None

    def _uncovered(self, why):
        if self.chain is not None:
            self.chain.state, self.chain.reason = "uncovered", why
        return {"decision": "uncovered", "why": why}

    def anchor(self, *, frame, fc, iid, instance_t0, sent):
        """A REAL DownSlash hit + bounce marker on the target L2 still names (the caller checks both). sent: the keys
        actually sent for the hit frame and the next (desired index 0 and 1), before the hit was known."""
        if type(fc) is not int or type(frame) is not int:
            return self._uncovered("hit physics counter or frame unknown")
        self.chain = Chain(int(iid), int(frame), int(fc), instance_t0, {int(k): int(v) for k, v in sent.items()},
                           {int(frame): int(fc)})
        return {"decision": "anchored"}

    def key(self, F):
        """The key for desired frame F: the switched row's from its cut, else the normal baseline."""
        c = self.chain
        j = F - c.hit_frame
        masks = c.row.masks if c.state == "switched" else self.normal
        return int(masks[j]) if 0 <= j < len(masks) else 0

    def record_sent(self, frame, mask):
        if self.chain is not None:
            self.chain.sent[int(frame)] = int(mask)

    def verified_through(self):
        """The last state index the switched row's verification covers (all variants), else None."""
        c = self.chain
        if c is None or c.state != "switched" or not c.verified:
            return None
        return min(int(p["through_update"]) for p in c.verified["per_variant"])

    def on_state(self, st):
        """st: frame, fc, control (the target's Control state), instance_t0, prev_seen (the previous STATE was received
        with the target not in Slam Antic), pose (x, y, face), start (Start of this STATE). Decides desired f + 2."""
        c = self.chain
        if c is None or c.state in ("uncovered", "done", "handback"):
            return {"decision": "noop", "state": None if c is None else c.state}
        f, fc = st["frame"], st.get("fc")
        i = f - c.hit_frame + 1
        if type(fc) is not int:
            return self._uncovered("physics counter unknown")
        c.seen[f] = fc
        if c.state == "pending":                       # verified after the sighting tick's send
            row, v = c.row, c.verified
            if v is None:
                return self._uncovered(f"H{row.H}: verification not done before its first differing key")
            if not v["pass"]:
                return self._uncovered(f"H{row.H} single-stream verification: {v['why']}")
            if c.hit_frame + row.first - 2 < f:        # the first differing key (desired hit + first) is sent at - 2
                return self._uncovered(f"H{row.H}: its first differing key can no longer be sent")
            rel = v["rel_by_state"]
            bad = [k for k, x in c.seen.items() if k - c.hit_frame + 1 >= v["start_s"] and
                   x - c.hit_fc != rel.get(k - c.hit_frame + 1)]
            if bad:
                return self._uncovered(f"verified roll does not reproduce the observed physics steps at {sorted(bad)[:4]}")
            c.state = "switched"
            sets = sorted({tuple((u, rel[u]) for u in p["contacts_update"]) for p in v["per_variant"]})
            v["strike_sets"] = sets
            h = c.hit_frame
            return {"decision": "switch", "row": row.H, "first_difference_frame": h + row.first,
                    "contacts": sorted({h - 1 + u for s_ in sets for u, _ in s_}), "verify_ms": c.verify_ms}
        if c.state == "switched":
            rel = c.verified["rel_by_state"]
            if rel.get(i) is None or fc - c.hit_fc != rel[i]:
                return self._uncovered(f"observed physics pairing left the verified roll at state {i}; keys in flight "
                                       "stay, existing failure/responsibility path")
            due = max((s_[c.next_contact][0] for s_ in c.verified["strike_sets"] if c.next_contact < len(s_)),
                      default=None)
            if due is not None and i > due + 1:
                return self._uncovered(f"the verified next hit (state <= {due}) was not observed")
            return {"decision": "keep_row", "row": c.row.H}
        if st.get("control") != "Slam Antic":
            # past the rows' last first sighting the normal knife stays B2's ordinary strike: its real hit re-anchors,
            # a miss is B2's ordinary missed-strike recovery
            return {"decision": "keep_normal"}
        t0 = st.get("instance_t0")
        if t0 is None or (c.instance_t0 is not None and t0 < c.instance_t0 - 1e-6):
            return self._uncovered("target instance unknown or older than the anchor")
        if not st.get("prev_seen"):
            return self._uncovered("first sighting not proven (previous STATE missing or already in Slam Antic)")
        row = self.rows.get(i)
        if row is None:
            return self._uncovered(f"no positive-slack row for a first sighting at state {i}")
        if any(f2 - c.hit_frame >= row.cut for f2 in c.sent):
            return self._uncovered(f"a key at desired >= cut {row.cut} is already sent: no rewrite of keys in flight")
        if row.first - 1 - i <= 0:
            return self._uncovered(f"H{row.H}: zero send slack")
        start = st.get("start")
        if start is None or start.s != i:
            return self._uncovered("no actual tracker state of the sighting STATE to verify from")
        missing = [j for j in range(start.s, row.cut) if c.hit_frame + j not in c.sent and j != i + 1]
        if missing:
            return self._uncovered(f"keys actually sent for desired {missing[:4]} unknown: the stream cannot be "
                                   "re-verified")
        pose = st["pose"]
        c.row, c.state = row, "pending"
        c.pending = (row, start, Target(c.iid, pose["x"], pose["y"], pose["face"], i))
        return {"decision": "verify_after_send", "row": row.H, "slack": row.first - 1 - i}

    def verify_now(self):
        """After the sighting tick's send (same thread): the ONE stream = the keys actually sent from the start STATE to
        the cut (this tick's key included) + the row's suffix."""
        import time
        c = self.chain
        if c is None or c.state != "pending" or c.pending is None:
            return None
        row, start, target = c.pending
        c.pending = None
        keys = [c.sent.get(c.hit_frame + j) for j in range(start.s, row.cut)]
        if any(k is None for k in keys):
            c.verified = {"pass": False, "why": "a key before the cut was not sent", "per_variant": [], "rel_by_state": {}}
            return c.verified
        t0 = time.perf_counter_ns()
        v = verify(start, target, keys + list(row.masks[row.cut:]), len(row.contacts))
        c.verify_ms = (time.perf_counter_ns() - t0) / 1e6
        v["start_s"] = start.s
        c.verified = v
        return v

    def on_real_hit(self, *, frame, fc, iid, marker):
        """A REAL follow-up DownSlash hit + marker on the same target while switched: it must land on the verified
        Update and physics step; the last one ends the chain."""
        c = self.chain
        if c is None or c.state != "switched" or not marker or iid != c.iid:
            return {"decision": "ignored"}
        u, p = frame - c.hit_frame + 1, fc - c.hit_fc
        k = c.next_contact
        want = sorted({s_[k] for s_ in c.verified["strike_sets"] if k < len(s_)})
        if (u, p) not in want:
            return self._uncovered(f"real follow-up hit at state {u} / physics {p} not at the verified {want}; old keys "
                                   "not shifted")
        c.next_contact += 1
        if c.next_contact >= max(len(s_) for s_ in c.verified["strike_sets"]):
            c.state = "done"
        return {"decision": "confirmed", "state_index": u, "physics": p, "row": c.row.H, "state": c.state}


# ---- the B2 adapter (NativeManualAirChain): observe -> frame record and responsibility, observe_bounce_goal -> anchor,
# _propose -> offer, before_send -> late key, sent -> the single-row verification ----------------------------------------

ENV = "SSBOT_FORUM_CHAIN_BOUNCE_TABLE"
PROGRAM = "air_bounce"
POST_KEYS = ("bounce", "hit", "press", "simple_wait")     # what B2's real-bounce release adds to its commitment


def enabled():
    import os
    v = os.environ.get(ENV, "0").strip()
    if v not in {"0", "1"}:
        raise ValueError("invalid " + ENV)
    return v == "1"


def observe_frame(chain, state):
    """Every observed STATE (inbox history included): its physics counter and each Clapper's Control state."""
    from .slam_play import clappers, control
    f = state.get("f")
    if type(f) is not int:
        return
    fc = state.get("fc")
    chain._bounce_frames[f] = (fc if type(fc) is int else None, {e.get("iid"): control(e)[0] for e in clappers(state)})
    for old in [k for k in chain._bounce_frames if k < f - 240]:
        del chain._bounce_frames[old]


def end(chain, kind, why):
    """The table stops owning keys; the caller keeps or releases B2's commitment."""
    c = None if chain._bounce is None else chain._bounce.chain
    chain._note("bounce_table_end", frame=chain.dispatch.frame, kind=kind, why=why,
                state=None if c is None else c.state, row=None if c is None or c.row is None else c.row.H,
                hit=None if c is None else c.hit_frame)
    chain._bounce = None


def release(chain, kind, why):
    """'uncovered' goes through B2 recovery (the commitment's failure exposure is kept); anything else is an ordinary
    handback (keys already sent stay). No offer this tick."""
    end(chain, kind, why)
    if kind == "uncovered":
        chain._recover("bounce table uncovered: " + why, chain.dispatch.frame)
    else:
        chain.commitment = None
        chain._press = chain._accepted = chain._hit = None
        chain._abandon("bounce table: " + why)
    return None


def _hit_frame(chain, state, hit):
    """The REAL hit's STATE frame: this STATE's own DownSlash hit (bounce_target), or B2's own hit joined to this
    bounce (a face-hook bounce has no DownSlash hit and is not a table anchor)."""
    from . import knife_chain_transfer as transfer
    if transfer.bounce_target(state) == hit:
        return state["f"]
    post = chain.post_context
    if (post is not None and post.get("bounce") == state["f"] and post["move"].target_iid == hit
            and type(post.get("hit")) is int and post.get("kind") != "hook_bounce"):
        return int(post["hit"])
    return None


# The 148 domain: the same Clapper starts a NEW slam antic during the bounce flight. Only from these Control states
# can that antic start inside the rows' first sightings; casting, walking, evading, jumping or attacking targets
# stay with the existing successor (live L1 8f9e9629 2561: a casting body met the centered normal knife early).
TABLE_FROM = frozenset({"Idle", "Slam Recover"})


def _outside(chain, state, prefs, hit, hit_f, source, ta):
    """Why this real bounce is outside the table's domain (None: inside). The table takes a same-target bounce only
    where its baseline fits: the Clapper L2 still names, the responsibility on that same Clapper, no L2 wall-side / side-entry
    / no-hit intent on it, the bounced source's own hammer tail over (knife_chain_transfer.bounce_tail_pending: that tail
    stays the existing BOUNCE goal's bounce_tail successor) and the target Idle / Slam Recover at the hit (TABLE_FROM)."""
    from . import knife_chain_transfer as transfer
    entry = getattr(prefs, "entry_attack", None)
    if hit_f is None:
        return "no DownSlash hit STATE for this bounce"
    if hit != getattr(prefs, "target", None):
        return "cross target"
    if source.target_iid != hit:
        # Task 181 (o8 3267-3314): B2 reads the strike's hits and its target's life from commitment["move"]; a responsibility
        # still on the other Clapper (an earlier cross-target hand-off, a vault's buddy) would count hits on the wrong one
        return "the responsibility is the other Clapper's move"
    if (getattr(prefs, "wall_pressure", None) is not None or getattr(chain, "_wall_pressure", None) is not None
            or (entry is not None and (entry.target != hit or entry.kind != "stomp")) or hit in getattr(prefs, "no_hit", ())):
        return "L2 intent on this target"
    if transfer.bounce_tail_pending(state, transfer.TransferGoal(hit, hit, state["f"], ta, "BOUNCE", source),
                                    chain._clock):
        return "the bounced source's hammer tail is pending"
    e = next((q for q in transfer.clappers(state) if q.get("iid") == hit), None)
    if e is None or transfer.control(e)[0] not in TABLE_FROM:
        return "target " + ("absent" if e is None else transfer.control(e)[0]) + ": outside the table domain"
    return None


def try_anchor(chain, state, prefs, hit, source, ta):
    """observe_bounce_goal at a REAL DownSlash hit + bounce marker, after the existing source responsibility is derived.
    Inside the table's domain (_outside): the switched row's next verified hit continues that row; any other real hit
    anchors a fresh table (the normal baseline from this hit). True: the table owns the keys from here. False: the
    existing BOUNCE goal path continues (a table that was running ends)."""
    f = state["f"]
    hit_f = _hit_frame(chain, state, hit)
    why = _outside(chain, state, prefs, hit, hit_f, source, ta)
    if why is not None:
        if chain._bounce is not None:
            end(chain, "handback", "real bounce outside the table's domain: " + why)
        chain._note("bounce_table_not_anchored", frame=f, target=hit, hit=hit_f, reason=why)
        return False
    fc = (chain._bounce_frames.get(hit_f) or (None,))[0]
    old = chain._bounce
    if old is not None and old.chain is not None and old.chain.state == "switched":
        res = (old.on_real_hit(frame=hit_f, fc=fc, iid=hit, marker=True) if type(fc) is int
               else old._uncovered("follow-up hit physics counter unknown"))
        chain._note("bounce_table_hit", frame=f, hit=hit_f, hit_fc=fc, **res)
        if res["decision"] == "confirmed" and old.chain.state == "switched":
            post = chain.post_context
            if post is not None and post.get("bounce_table"):
                # the verified row continues on the same move: B2's own real-bounce release is undone
                chain.commitment = {k: v for k, v in post.items() if k not in POST_KEYS}
                chain.post_context = chain._post_seed = chain._post_kind = None
                chain._press = chain._accepted = chain._hit = None
                return True
            old._uncovered("confirmed hit without the table's own strike record")
    if old is not None:
        end(chain, "reanchor" if old.chain is not None and old.chain.state == "done" else "superseded",
            "a real same-target hit + bounce anchors a fresh table")
    table = BounceTable()
    sent = {F: int(chain._receipts[F]) for F in range(hit_f, f + 2) if F in chain._receipts}
    a = table.anchor(frame=hit_f, fc=fc, iid=hit, instance_t0=None, sent=sent)
    if a["decision"] != "anchored":
        chain._note("bounce_table_unanchored", frame=f, target=hit, hit=hit_f, reason=a["why"])
        return False
    if chain.runner.run is not None:
        chain._abandon("same-target real bounce: the bounce table takes the keys")
    chain.post_context = chain._post_seed = chain._post_kind = None
    chain._air_plan = None
    chain._press = chain._accepted = chain._hit = None
    chain.commitment = {"move": source, "origin": f, "ta": ta, "predicted_bounce": None, "manual_air": True,
                        "bounce_table": True}
    chain._bounce = table
    chain._note("bounce_table_anchored", frame=f, target=hit, hit=hit_f, hit_fc=fc, sent=sent, rows=sorted(table.rows),
                responsibility=vars(source), scope="same target only; normal baseline until the first sighting; the "
                "row is re-verified once from the actual sighting STATE; no receipt")
    return True


def observe_identity(chain, state):
    """After B2's observe of each STATE: the table's responsibility follows the target's first NEW slam instance after
    the anchor (the sighting); a second new instance is the existing 'target started a new slam instance' recovery.
    (B2's own instance check skips the table's commitment for this reason only.)"""
    from .knife_chain_commitment import MoveInstance
    from .slam_play import control
    c, table = chain.commitment, chain._bounce
    if c is None or not c.get("bounce_table") or table is None or table.chain is None:
        return
    iid, f = table.chain.iid, state["f"]
    e = next((q for q in state.get("ents") or () if q.get("iid") == iid), None)
    if e is None:
        return
    st, tin = control(e)
    if st != "Slam Antic":
        return
    ta = chain._clock - tin
    m = c["move"]
    if m.target_iid == iid and m.family == "CC_SLAM" and c.get("ta") is not None and abs(ta - c["ta"]) <= 3 / 60:
        return
    if c.get("sighted"):
        chain._recover("bounce table: target started a new slam instance", f)
        return
    c.update(move=MoveInstance(iid, f, "CC_SLAM"), ta=ta, sighted=True,
             responsibility_origin=max(c.get("responsibility_origin", c["origin"]), f))
    chain._note("bounce_table_responsibility", frame=f, move=vars(c["move"]), ta=ta,
                source="first new Slam Antic STATE after the anchor")


def knife_witness(chain, table, sim, plan, game, state, enemy):
    """Task 181 (Sol seq 253 R1): the frame this table's normal knife meets its target on the model, or None (no witness).
    The knife: its press actually sent (B2's _press), its swing observed accepted (else modeled on the press frame or the
    next, while that lies ahead), the frames ACTIVE after it less CONTACT_END_MARGIN_F, as press_now_row, after this STATE
    (which showed no hit). The path: the actual S0, in-flight key and hold filter with the table's keys through that window.
    The body: the target's current pose witness (contact_body_witness, WalkSupport for a walker; a state with neither, or
    an Idle hit since its entry, #317, has none; the Idle no-evade proof is assumed, an evade only takes the body away).
    Every slash variant must meet it, in the air and swinging. A model contact, never a hit receipt."""
    from . import knife_chain_transfer as transfer, pogo_model as PM
    from .knife_chain_air import model_path
    c, f = table.chain, sim.f
    press = c.hit_frame + table.press
    seen = chain._accepted
    if chain._press != press or (seen is None and f > press):
        return None
    last = (press if seen is None else seen) + PM.ACTIVE[1] - transfer.CONTACT_END_MARGIN_F
    if last <= f:
        return None
    keys = np.array([table.key(F) for F in range(f + 2, max(last, f + 2) + 1)], np.int64)
    path = model_path(sim, plan, keys, game)
    flags, pos = np.asarray(path.flags), np.asarray(path.pos)
    if seen is None:
        swing = (flags & K.F_ATTACKING) != 0
        if not any(swing[j] and not swing[j - 1] for j in (press - f, press - f + 1) if 1 <= j < len(swing)):
            return None
        seen = press
    st = transfer.control(enemy)[0]
    ev = chain._idle_ev.get(c.iid) if st == "Idle" else None
    if isinstance(ev, dict) and ev.get("hit") is not None:
        return None
    if st == "Walk":
        support = transfer.walk_body_support(enemy, len(flags), state.get("hero"))
        core = None if support is None else support(pos[:, 0])[0]
    else:
        core = transfer.contact_body_witness(enemy, len(flags), idle_no_evade=True, idle_time=transfer.idle_time_of(ev))
    if core is None:
        return None
    slashes = [PM.slash_poly(face, alt) for face in (-1, 1) for alt in (False, True)]
    for j in range(max(seen + PM.ACTIVE[0] - f, 1), min(last - f + 1, len(flags))):
        if flags[j] & K.F_GROUND:
            return None
        if not flags[j] & K.F_ATTACKING or not np.isfinite(core[j]).all():
            continue
        b = core[j]
        body = np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]])
        if all(PM.meets(slash + pos[j], body) for slash in slashes):
            return f + j
    return None


def _knife_kept(chain, table, geo, sim, plan, path, keys, game, state, enemy, kept):
    """What still blocks the normal knife's external step. The target's own body / move on the way down is explained only by
    this knife's contact witness: at the existing buffered target contact (witness - 2 .. witness, B2 _query) and, on the
    hit branch of this step, where that branch keeps her protected. Her box really overlapping the observed body, before
    the contact (a side collision) or on the hit branch, is never waived (_transfer_hit_check's rule). Another owner or a
    delayed hazard blocks as before; no witness: the original block."""
    from dataclasses import replace
    from . import knife_chain_transfer as transfer
    from .knife_chain_air import model_path
    c, f = table.chain, sim.f

    def own(x):
        return x.owner_iid == c.iid and x.kind in ("move", "body")

    if not any(own(x) for x in kept):
        return kept
    contact = knife_witness(chain, table, sim, plan, game, state, enemy)
    chain._note("bounce_table_knife_witness", frame=f, contact=contact, press=chain._press, accepted=chain._accepted,
                scope="model contact from the actual start; no hit receipt")
    if contact is None or not all(own(x) for x in kept):
        return kept
    body = transfer.body_box(enemy)
    if body is None:
        return kept

    def overlap(boxes):
        return np.any((boxes[:, 0] <= body[2]) & (boxes[:, 2] >= body[0]) & (boxes[:, 1] <= body[3]) & (boxes[:, 3] >= body[1]))

    contacts, protected, d = kept, frozenset(), contact - f
    if overlap(np.asarray(path.box)[:d]):
        return kept
    if d <= len(keys) + len(sim.prefix):
        hit = model_path(sim, plan, keys, game, contact=d)
        if overlap(np.asarray(hit.box)[d:]):
            return kept
        protected = frozenset(hit.origin + j for j in range(d + 1, len(hit.flags)) if hit.flags[j] & K.F_INVULN)
        # the hit's NEW protection never erases another owner, a delayed hazard or the target before it
        branch = geo.scan(replace(hit, check_flags=(hit.check_flags & ~K.F_INVULN) | (path.check_flags & K.F_INVULN)))
        if not branch.complete:
            return kept
        contacts = branch.contacts
    return [x for x in contacts if not (own(x) and (contact - 2 <= x.frame <= contact or x.frame in protected))]


def offer(chain, forecast, prefs):
    """One tick of the anchored table (B2 _propose): the state machine decides desired f + 2; the current external step
    (in-flight key + the table's next 3 keys) is scanned for every owner with protection only from the observed state;
    after the switch the target's own contacts inside the verified horizon are the verified row's domain, before it only
    the ones this knife's contact witness explains (_knife_kept). L2's tactical target is not read here: it takes effect
    at the table's hand-back (try_anchor's cross target, or a recovery). The key goes out through the ordinary B2 send path."""
    from .knife_chain_b2 import B2Offer
    from .knife_chain_geometry import B2Geometry, GeometryUnavailable
    from .knife_chain_air import model_path, AirAnchor
    from .knife_chain_eval import Run
    from . import knife_chain_transfer as transfer
    table = chain._bounce
    c = table.chain
    if chain.commitment is None or not chain.commitment.get("bounce_table"):
        return release(chain, "handback", "no table commitment")
    if chain._context is None:
        return release(chain, "uncovered", "current model context unavailable")
    tick, sim, _, _ = chain._context
    f, state, game, ground, accepting = tick
    if sim.fo != f or sim.f != f or len(sim.prefix) != 1:
        return release(chain, "uncovered", "lagged or incomplete current model")
    queued, basis = chain.queued_prefix(f, state)
    if queued is None or queued != int(sim.prefix[0]) or c.sent.get(f + 1, queued) != queued:
        return release(chain, "uncovered", "in-flight key unknown or differs from the table's record")
    c.sent.setdefault(f + 1, int(queued))
    e = next((q for q in transfer.clappers(state) if q.get("iid") == c.iid), None)
    if e is None:
        return release(chain, "uncovered", "target not observed")
    rs = getattr(forecast, "rs", None)
    cur = None if rs is None else getattr(rs.trk, "now", {}).get(c.iid)
    t0 = None if cur is None else getattr(cur[2], "t0", None)
    if c.instance_t0 is None and t0 is not None:
        c.instance_t0 = float(t0)
    ctl = transfer.control(e)[0]
    prev = chain._bounce_frames.get(f - 1)
    fc, dt = state.get("fc"), state.get("dt")
    start = (Start(np.asarray(sim.start, float).reshape(K.K), sim.hold, float(np.float32(dt)), sim.params, sim.terrain,
                   f - c.hit_frame + 1, fc - c.hit_fc)
             if type(fc) is int and isinstance(dt, (int, float)) and np.isfinite(dt) and dt > 0 else None)
    d = table.on_state({"frame": f, "fc": fc, "control": ctl, "instance_t0": None if t0 is None else float(t0),
                        "prev_seen": prev is not None and prev[1].get(c.iid) not in (None, "Slam Antic"),
                        "pose": {"x": float(e["pos"][0]), "y": float(e["pos"][1]), "face": 1 if e.get("flipX") else -1},
                        "start": start})
    chain._note("bounce_table_tick", frame=f, state_index=f - c.hit_frame + 1, control=ctl, table_state=c.state,
                l2_target=getattr(prefs, "target", None), **d)
    if d["decision"] == "uncovered":
        return release(chain, "uncovered", d["why"])
    if d["decision"] == "noop":
        return release(chain, "handback", d.get("why") or str(d.get("state")))
    move = chain.commitment["move"]
    keys = np.array([table.key(F) for F in (f + 2, f + 3, f + 4)], np.int64)
    try:
        plan = NS(origin=f, press_k=None, entry_k=0, contact_frame=None, iid=c.iid, move=move)
        path = model_path(sim, plan, keys, game)
        geo = B2Geometry(forecast, f, move, None if cur is None else cur[2])
        scan = geo.scan(path)
        if not scan.complete:
            return release(chain, "uncovered", "current external step coverage incomplete")
        horizon = table.verified_through()
        kept = [x for x in scan.contacts if not (horizon is not None and x.owner_iid == c.iid
                                                 and x.kind in ("move", "body") and x.frame - c.hit_frame + 1 <= horizon)]
        if kept and c.state in ("baseline", "pending"):
            kept = _knife_kept(chain, table, geo, sim, plan, path, keys, game, state, e, kept)
    except GeometryUnavailable as exc:
        return release(chain, "uncovered", "current external step unchecked: " + str(exc))
    if kept:
        return release(chain, "uncovered", f"current external step blocked: {kept[0].kind} of {kept[0].owner_iid} at "
                                           f"{kept[0].frame}")
    draft = chain.runner.fork_empty(AirAnchor())
    draft.run = Run(PROGRAM, "run", {"iid": c.iid, "hit_f": c.hit_frame, "keys": {f + 2: int(keys[0])}, "cs": None})
    return B2Offer("active", None, draft, int(keys[0]), 0., move,
                   {"manual_air": True, "bounce_table": True, "decision": d["decision"], "table_state": c.state,
                    "row": None if c.row is None else c.row.H, "hit": c.hit_frame,
                    "checked": {"through": path.origin + len(path.commands), "exempt_target_through_state": horizon},
                    "safety_basis": "row verified from the actual sighting STATE; current external step for all owners"})


def before_send(chain, selected, *, frame, target, mask, flags, received_frame):
    """A table key for a frame the game already passed is not the verified stream unless it equals the key before it."""
    table = chain._bounce
    if table is None or type(received_frame) is not int or received_frame < target:
        return None
    if table.chain.sent.get(target - 1) == int(mask):
        chain._note("bounce_table_send_late", frame=frame, target=target, received_frame=received_frame,
                    same_as_previous=True)
        return None
    return chain._abort_hook_dispatch(selected, frame=frame, target=target, mask=mask, flags=flags,
                                      received_frame=received_frame, event="bounce_table_send_veto",
                                      reason="table key target already received: the sent stream would differ")


def after_send(chain, selected, sent):
    """After the tick's send (same thread): record the key; a pending row is verified now, its cost lands on the next
    tick's serial time."""
    table = chain._bounce
    if table is None or selected is None or not selected.details.get("bounce_table") or sent.chain_outcome != "sent":
        return
    table.record_sent(sent.target_frame, sent.desired_mask)
    if table.chain.state == "pending" and table.chain.pending is not None:
        v = table.verify_now()
        chain._note("bounce_table_verified", frame=sent.frame, row=table.chain.row.H, ok=bool(v and v["pass"]),
                    why=None if v is None else v["why"], verify_ms=table.chain.verify_ms,
                    per_variant=None if v is None else v["per_variant"],
                    timing_scope="single-row verification after this send, same thread; the next tick waits for it")
