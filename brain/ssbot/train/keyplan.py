"""Key plan log (M2 plan "key economy"; DESIGN 2, the formal run's key track): every key press the controller decides,
from the tick that first put it into a plan to the frames the game latched it.

The person's standard (2026-10-03): a good controller presses as few keys as possible and changes its key plans as
little as possible (third after safety and time). Measuring it needs, per key, the frame a press was first decided
for a future frame, every later change or cancellation, and the actual press and release; the same record drives the
rhythm-game key track rendered over the formal run's video (ssbot.tools.key_track).

    log = KeyPlanLog()
    log.reset(ep)
    log.observe(f, act_mask)                  # every STATE: the latched mask the oracle applied at f (act.mask)
    log.tick(f, d, plan, sup=False)           # every tick: commanded masks for frames d, d+1, ... (plan[0] is sent)
    rec = log.record()                        # one JSON-able dict per episode

Notes. A note is one press of one key in the commanded stream: a run of frames with the key's bit set. At each tick
the plan's runs are matched to the open notes of the same key: a run that starts at d while the key was down in the
mask sent for d - 1 continues the held note (only its release can change); the other runs are matched one to one to
the pending notes (press not sent yet), nearest press first, when the presses lie within MATCH_F frames or the runs
overlap. A matched note whose (press, release) differs is changed (one history entry); an unmatched pending note is
cancelled; an unmatched run is a new note, born at this tick. A note whose press frame is d is executed (sent). A
pending note whose press frame a late tick skipped (d > press) was never sent: cancelled ("late").

Release frames are the first frame the key is up; a run that reaches the plan's end is held at least that far and is
logged as the negative of the plan's end (-r: "held through r - 1 at least"). Such an open release is changed only
when a later plan releases it before that frame.

Jitter. Frame level, over the frames both of two consecutive plans cover (all still in the future): a bit that
changes at a frame is a plan change; a change of a bit that already changed at that frame (binary: it goes back) is
a flip-flop; one that undoes the previous tick's change at that frame is a one-tick flip-flop.

Record (one line of keys_i<N>.jsonl per episode, ssbot.train.planner_policy):
  {"ep", "f0", "f1", "ticks", "sup_ticks",
   "notes": [[key, born, press, release, status, exec, sup, hist], ...]
       key: button name; born: tick frame f of the first decision; press / release: as first decided;
       status "x" executed, "c" cancelled, "l" cancelled by a late tick, "o" open at the end, "h" held before the log
       began (press unknown: born); exec: tick frame that sent the press (or null); sup: born while the supervisor's
       keys replaced the planner's; hist: [[f, press, release], ...] each change, [f, -1, -1] the cancellation,
   "actual": {key: [[press, release], ...]}   latched act.mask (release -1: still down at the end),
   "flips": {key: [changes, flipflops, flipflops_1tick]}}
"""
from __future__ import annotations

import numpy as np

from ssbot.ipc.framing import BUTTONS

MATCH_F = 6             # frames two presses of one key may lie apart and still be the same note (moved)
NB = len(BUTTONS)


class _Note:
    __slots__ = ("key", "born", "press", "release", "p0", "r0", "status", "exec", "sup", "hist")

    def __init__(self, key: int, born: int, press: int, release: int, sup: bool):
        self.key, self.born, self.press, self.release = key, born, press, release
        self.p0, self.r0 = press, release
        self.status = "p"            # pending (press not sent), "x" executed, "c" / "l" cancelled, "h" held at start
        self.exec: int | None = None
        self.sup = sup
        self.hist: list[list[int]] = []

    def row(self) -> list:
        st = "o" if self.status == "p" else self.status
        return [BUTTONS[self.key], self.born, self.p0, self.r0, st, self.exec, int(self.sup), self.hist]


def _rel_changed(old: int, new: int) -> bool:
    """Releases (>= 0 known, < 0 held at least to -r): changed when the plans disagree on a frame both cover."""
    if old >= 0 and new >= 0:
        return old != new
    if old < 0 and new < 0:
        return False
    if old < 0:                      # was held at least to -old, now released at new
        return new < -old
    return True                      # was released at old (inside that plan), now held past it


def runs_of(plan: np.ndarray, d: int, bit: int) -> list[tuple[int, int]]:
    """Runs of one key in a plan for frames d, d+1, ...: (press, release) absolute, release -(d + len) when the run
    reaches the plan's end."""
    on = ((plan >> bit) & 1).astype(np.int8)
    if not on.any():
        return []
    e = np.diff(np.concatenate([[0], on, [0]]))
    starts = np.flatnonzero(e == 1)
    ends = np.flatnonzero(e == -1)
    n = len(plan)
    return [(d + int(s), d + int(t) if t < n else -(d + n)) for s, t in zip(starts, ends)]


class KeyPlanLog:
    def __init__(self, match_f: int = MATCH_F):
        self.match_f = match_f
        self.reset(-1)

    def reset(self, ep: int) -> None:
        self.ep = ep
        self.notes: list[_Note] = []
        self.open: dict[int, list[_Note]] = {}       # key -> pending notes (press not sent), by press
        self.held: dict[int, _Note] = {}             # key -> the executed note still down in the sent stream
        self.last_sent = 0                           # the mask sent for the last decided frame (persists)
        self.last_d: int | None = None
        self.f0: int | None = None
        self.f1: int | None = None
        self.ticks = 0
        self.sup_ticks = 0
        self.prev_plan: np.ndarray | None = None      # previous plan's masks, frames prev_d ...
        self.prev_d = 0
        self.chg = np.zeros(0, np.int64)              # bits that changed at least once at each of those frames
        self.lastx = np.zeros(0, np.int64)            # bits the previous tick changed there
        self.flips = np.zeros((NB, 3), np.int64)
        self.act_on: dict[int, int] = {}              # key -> latched press frame (down now)
        self.actual: dict[int, list[list[int]]] = {}
        self.act_last_f: int | None = None
        self.act_last = 0

    # ---- what the game latched -------------------------------------------------------------------------------------

    def observe(self, f: int, mask: int) -> None:
        """The latched mask at frame f (STATE act.mask). Frames must come in order; repeats and older ones are ignored."""
        if self.act_last_f is not None and f <= self.act_last_f:
            return
        mask = int(mask or 0)
        x = mask ^ self.act_last
        while x:
            b = (x & -x).bit_length() - 1
            x &= x - 1
            if mask >> b & 1:
                self.act_on[b] = f
            else:
                p = self.act_on.pop(b, None)
                if p is not None:
                    self.actual.setdefault(b, []).append([p, f])
        self.act_last, self.act_last_f = mask, f

    # ---- what the controller decided -------------------------------------------------------------------------------

    def tick(self, f: int, d: int, plan, sup: bool = False) -> None:
        """One decision at tick frame f: commanded masks for frames d, d+1, ... (plan[0] is the one sent for d).
        sup: the supervisor's keys replaced the planner's (plan is then just the sent mask)."""
        plan = np.asarray(plan, np.int64).reshape(-1)
        if not len(plan):
            plan = np.zeros(1, np.int64)
        if self.last_d is not None and d <= self.last_d:
            return                                   # a repeated decision frame: the first one was sent
        self.f0 = f if self.f0 is None else self.f0
        self.f1 = f
        self.ticks += 1
        self.sup_ticks += int(sup)
        self._jitter(d, plan)
        sent_prev = self.last_sent
        used = int(np.bitwise_or.reduce(plan)) | sent_prev
        for b in list(self.open):
            used |= 1 << b
        for b in range(NB):
            if used >> b & 1:
                self._key(b, f, d, plan, sent_prev >> b & 1, sup)
        self.last_sent = int(plan[0])
        self.last_d = d

    def _key(self, b: int, f: int, d: int, plan: np.ndarray, was_down: int, sup: bool) -> None:
        runs = runs_of(plan, d, b)
        pend = self.open.get(b, [])
        # presses a late tick skipped were never sent
        keep = []
        for n in pend:
            if n.press < d:
                n.status = "l"
                n.hist.append([f, -1, -1])
            else:
                keep.append(n)
        pend = keep
        h = self.held.get(b)
        if was_down:
            if runs and runs[0][0] == d:
                r = runs.pop(0)[1]
                if h is None:                        # down before the log began (or the supervisor's)
                    h = _Note(b, f, d - 1, r, sup)
                    h.status, h.exec = "h", f
                    self.notes.append(h)
                    self.held[b] = h
                else:
                    if _rel_changed(h.release, r):
                        h.hist.append([f, h.press, r])
                    h.release = r
            elif h is not None:                      # released at d
                if _rel_changed(h.release, d):
                    h.hist.append([f, h.press, d])
                h.release = d
                del self.held[b]
        elif h is not None:
            del self.held[b]
        # pending notes <-> the plan's other runs, nearest press first
        pairs = []
        for i, n in enumerate(pend):
            for j, (p, r) in enumerate(runs):
                dp = abs(p - n.press)
                rel_end = n.release if n.release >= 0 else -n.release
                r_end = r if r >= 0 else -r
                if dp <= self.match_f or (p < rel_end and n.press < r_end):
                    pairs.append((dp, i, j))
        pairs.sort()
        used_i, used_j = set(), set()
        new_open = []
        for dp, i, j in pairs:
            if i in used_i or j in used_j:
                continue
            used_i.add(i)
            used_j.add(j)
            n = pend[i]
            p, r = runs[j]
            if p != n.press or _rel_changed(n.release, r):
                n.hist.append([f, p, r])
            n.press, n.release = p, r
            new_open.append(n)
        for i, n in enumerate(pend):
            if i not in used_i:
                n.status = "c"
                n.hist.append([f, -1, -1])
        for j, (p, r) in enumerate(runs):
            if j not in used_j:
                n = _Note(b, f, p, r, sup)
                self.notes.append(n)
                new_open.append(n)
        still = []
        for n in new_open:
            if n.press == d:
                n.status, n.exec = "x", f
                self.held[b] = n
            else:
                still.append(n)
        still.sort(key=lambda n: n.press)
        if still:
            self.open[b] = still
        else:
            self.open.pop(b, None)

    def _jitter(self, d: int, plan: np.ndarray) -> None:
        n = len(plan)
        chg = np.zeros(n, np.int64)
        lastx = np.zeros(n, np.int64)
        old = self.prev_plan
        if old is not None:
            s = d - self.prev_d
            L = min(len(old) - s, n) if s >= 0 else 0
            if L > 0:
                x = plan[:L] ^ old[s:s + L]
                c0 = self.chg[s:s + L]
                l0 = self.lastx[s:s + L]
                bits = int(np.bitwise_or.reduce(x)) if L else 0
                b = 0
                while bits:
                    if bits & 1:
                        xb = (x >> b) & 1
                        self.flips[b, 0] += int(xb.sum())
                        self.flips[b, 1] += int((xb & (c0 >> b)).sum())
                        self.flips[b, 2] += int((xb & (l0 >> b)).sum())
                    bits >>= 1
                    b += 1
                chg[:L] = c0 | x
                lastx[:L] = x
        self.prev_plan, self.prev_d, self.chg, self.lastx = plan.copy(), d, chg, lastx

    def record(self) -> dict:
        actual = {BUTTONS[b]: list(v) for b, v in self.actual.items()}
        for b, p in self.act_on.items():
            actual.setdefault(BUTTONS[b], []).append([p, -1])
        return {"ep": self.ep, "f0": self.f0, "f1": self.f1, "ticks": self.ticks, "sup_ticks": self.sup_ticks,
                "notes": [n.row() for n in self.notes], "actual": actual,
                "flips": {BUTTONS[b]: [int(v) for v in self.flips[b]] for b in range(NB) if self.flips[b].any()}}


# ---- metrics ---------------------------------------------------------------------------------------------------------

def final_press(row: list) -> int:
    """A note's last planned press frame (the one sent, for an executed note)."""
    p = row[2]
    for hf, hp, _hr in row[7]:
        if hp >= 0 and (row[5] is None or hf <= row[5]):
            p = hp
    return p


def match_actual(rec: dict, max_lag: int = 4) -> dict[int, tuple[int, int]]:
    """Executed notes (index in rec["notes"]) -> the latched (press, release) the game applied: per key, the first
    latched press in [sent press, sent press + max_lag] not taken by an earlier note (the hold filter delays a press
    by at most min_release frames; a late ACTION by a frame or two)."""
    out: dict[int, tuple[int, int]] = {}
    by_key: dict[str, list[tuple[int, int]]] = {}
    for i, n in enumerate(rec["notes"]):
        if n[4] == "x":
            by_key.setdefault(n[0], []).append((final_press(n), i))
    for k, lst in by_key.items():
        act = sorted(tuple(x) for x in rec["actual"].get(k, ()))
        j = 0
        for p, i in sorted(lst):
            while j < len(act) and act[j][0] < p:
                j += 1
            if j < len(act) and act[j][0] <= p + max_lag:
                out[i] = act[j]
                j += 1
    return out


def summarize(rec: dict, f_lo: int | None = None, f_hi: int | None = None, fps: float = 60.0) -> dict:
    """Key economy numbers of one episode's record, for notes whose press is sent (or due) in [f_lo, f_hi] and the
    latched presses there (None: unbounded; presses per second only with both): decided presses (the planner's notes; the supervisor's and keys held before the log began
    are left out), executed, changed before the press was sent, cancelled, the decision lead (first decision to the
    press sent, frames), the plan change rate ((changed + cancelled) / decided), latched presses per key and the
    frame-level flips (the whole episode)."""
    lo = -1 if f_lo is None else f_lo
    hi = 1 << 62 if f_hi is None else f_hi
    dec = ex = chg = canc = late = sup = rel_chg = 0
    leads: list[int] = []
    for n in rec["notes"]:
        _key, born, _p0, _r0, st, exf, s, hist = n
        if st == "h":
            continue
        p = final_press(n)
        if not lo <= p <= hi:
            continue
        if s:
            sup += 1
            continue
        dec += 1
        if st == "x":
            ex += 1
            chg += any(h[0] <= exf for h in hist)
            rel_chg += any(h[0] > exf for h in hist)
            leads.append(p - born)
        elif st in ("c", "l"):
            canc += 1
            late += st == "l"
    pressed: dict[str, int] = {}
    for k, iv in rec["actual"].items():
        c = sum(1 for p, _r in iv if lo <= p <= hi)
        if c:
            pressed[k] = c
    span = (hi - lo + 1) / fps if f_lo is not None and f_hi is not None else None
    flips = rec.get("flips") or {}
    return {"decided": dec, "executed": ex, "changed_before_press": chg, "cancelled": canc, "cancelled_late": late,
            "hold_changed_after_press": rel_chg, "supervisor_notes": sup,
            "plan_change_rate": round((chg + canc) / dec, 4) if dec else None,
            "leads": leads, "latched_presses": pressed, "latched_total": sum(pressed.values()),
            "presses_per_s": round(sum(pressed.values()) / span, 3) if span else None,
            "flips": dict(flips), "flip_changes": sum(v[0] for v in flips.values()),
            "flipflops": sum(v[1] for v in flips.values()), "flipflops_1tick": sum(v[2] for v in flips.values())}
