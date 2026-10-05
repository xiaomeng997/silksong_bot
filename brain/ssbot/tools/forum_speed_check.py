"""Does the Forum play the same at another game speed? (Forum plan R1 item 4: collect data at 2x only if the enemies'
FSM timings, attack choices, physics paths and recorded hitboxes match 1x within the measured noise.)

Compares arm A (e.g. 1x) with arm B (e.g. 2x, combat_run --time-scale 2 --same-seeds on another instance). Everything
is in game time, and everything a frame rate changes by itself is put on a common footing first, so that a 2x arm
with the same game logic passes:

  dwell      per (type, FSM state) the game seconds spent in the state (t_in_prev of the event leaving it). A state's
             time is counted in frames, 1/60 s at 1x and 1/30 s at 2x: a 1x value coarsened alone to 1/30 s gives
             fight-level p < 0.05 for 155 of 270 keys (KS up to 1.0) with identical game logic (R1 fixer, 2026-10-04).
             So both arms go on the coarsest arm's frame grid, as integer grid steps (float values a ulp apart would
             still be a KS distance of 1): n = round(t / dt) frames of the arm's nominal frame (1/60 s times its
             speed; the STATE dt jitters 0.01665-0.01668 s), then ceil(n / k) with k = grid / dt (ceil(ceil(x) / k) =
             ceil(x / k): a timer of D seconds lands on the coarse arm's step).
  choices    per (type, hero |dx| bin at the decision) the family shares of attack starts (FORUM_SPECS; the bins
             only with entities, else per type): the hero's distance drives most choices, and a policy at another
             speed holds other distances.
  speed      per (type, state) the enemy transform's speed over windows of SPEED_WIN_S game seconds inside one state
             (per frame, |d pos| / dt aliases against the 0.02 s physics step differently at 1/60 and 1/30 s frames).
             Entities are read on the coarsest arm's frames in both arms (the finer arm every k-th STATE): a window
             starts at the first frame seen in the state, up to one frame after its entry, and with 1/60 s frames in
             one arm and 1/30 s in the other the windows of a short, uneven motion (an evade) would cover different
             parts of it (calibration: every Evade key at p 0.0002 with both arms read at their own rate).
  visits     per (type, FSM state) the visits (exits from the state, self-loops included) per minute of the type's
             FSM time (the sum of all its dwells in the fight): a state that re-enters itself on a frame-counted or
             real-time check changes its visit rate and its dwells together, and the dwell test alone missed it
             (Song Automaton Tiny Control "Ready": 1605 -> 1003 visits at 2x with the same time in the state, R1
             close-out review, 2026-10-04). Statistic |r_a - r_b| / mean(r_a, r_b) of the pooled rates.
  next       per (type, FSM state) the successor shares of its exits (self-loops included), total variation; only
             states with two successors or more (a fixed successor is not a test).
  hitbox     per (type, state, collider name) the damage collider's extent relative to the enemy transform, flipped
             to face +x, per 0.05 s state-time bin: max over bins of |extent difference| (u) against the same
             statistic between each arm's halves (no fight-level test: 2x samples every other 1/60 s bin, and an
             extent from fewer samples is smaller, so the support templates need their own check anyway).
  apex       Choir Clapper jumps, from the FSM events (the entry into "Jump" to the exit from "Air"; entity states
             read on the coarse frames miss a one-frame "Jump"): the body's highest point above its position at the
             takeoff (entities read on the common coarse frames in both arms) and the air time (Jump + Air dwells)
             as steps of the common grid. Informational (no verdict).

Tests are fight-level permutations (samples within one fight are not independent: the hero's play and HP differ per
fight): the fights of A and B are pooled and relabelled at random; p = share of relabellings whose statistic (KS,
total variation) is >= the observed one, extended from --perm to --perm-max relabellings for keys below 0.05. A metric
matches when no key is significant under Holm at family-wise 0.05 (a real difference confined to a few keys) and the
number of keys with p < 0.05 is within the 99 % binomial bound for its key count (Binomial(keys, 0.05): calibrated by
the key count, not a fixed share). Keys below 0.05 after --perm relabellings are extended to
max(--perm-max, 2 x keys / 0.05), so the smallest Holm threshold can be reached. A key's smallest attainable p is
1 / C(n_a + n_b, n_a) over the fights of each arm that contain the key (a fight without it adds nothing to the
statistic under any relabelling): a key is underpowered when that is above 0.05 / keys (Holm's first step cannot
reject it), and a metric is "underpowered" when every key is. Under a rotation of waves a type is in only the fights
of its waves: 4 + 4 fights (C(8, 4) = 70, p >= 1/70) can never pass Holm, so a check meant to be able to fail needs
every compared type in 8 fights or more per arm (C(16, 8) = 12870).

--simulate-b K: arm B as if recorded at K x speed with the same logic (every K-th STATE, dwell on the K-frame grid):
the check's own calibration (it must pass), next to A vs A' (two 1x runs).

    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_speed_check --a <run 1x> [...] --b <run 2x> [...] --json out.json
"""
import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.knowledge.behaviour_tables import fight_states, run_fights
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS

BIN_S = 0.05
SPEED_WIN_S = 0.2
DIST_BINS = (0.0, 3.0, 6.0, 10.0, 99.0)
HITBOX_SHARE_MAX = 0.05
ALPHA = 0.05


def ks(a, b) -> float:
    """Two-sample Kolmogorov-Smirnov distance."""
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    x = np.sort(np.asarray(a, float))
    y = np.sort(np.asarray(b, float))
    grid = np.concatenate([x, y])
    fa = np.searchsorted(x, grid, side="right") / len(x)
    fb = np.searchsorted(y, grid, side="right") / len(y)
    return float(np.max(np.abs(fa - fb)))


def ks_p(d: float, n: int, m: int) -> float:
    """Asymptotic p-value of a two-sample KS distance d (Kolmogorov distribution, Stephens' small-sample factor)."""
    if not n or not m or math.isnan(d):
        return float("nan")
    ne = n * m / (n + m)
    lam = (math.sqrt(ne) + 0.12 + 0.11 / math.sqrt(ne)) * d
    if lam < 0.2:
        return 1.0
    return max(0.0, min(1.0, 2.0 * sum((-1) ** (j - 1) * math.exp(-2.0 * j * j * lam * lam) for j in range(1, 101))))


def chi2_p(a: dict[str, int], b: dict[str, int]) -> float:
    """p-value of the 2 x k contingency chi-square (shares of families in two arms), Wilson-Hilferty approximation."""
    keys = sorted(set(a) | set(b))
    na, nb = sum(a.values()), sum(b.values())
    if len(keys) < 2 or not na or not nb:
        return float("nan")
    x2 = 0.0
    for k in keys:
        tot = a.get(k, 0) + b.get(k, 0)
        for obs, n in ((a.get(k, 0), na), (b.get(k, 0), nb)):
            exp = tot * n / (na + nb)
            if exp > 0:
                x2 += (obs - exp) ** 2 / exp
    k = len(keys) - 1
    z = ((x2 / k) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * k))) / math.sqrt(2.0 / (9.0 * k))
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def tv(a: dict[str, int], b: dict[str, int]) -> float:
    na, nb = sum(a.values()), sum(b.values())
    if not na or not nb:
        return float("nan")
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0) / na - b.get(k, 0) / nb) for k in keys)


def holm(p: list[float]) -> list[float]:
    """Holm-adjusted p-values (step-down, monotone)."""
    order = sorted(range(len(p)), key=lambda i: p[i])
    out = [1.0] * len(p)
    run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (len(p) - r) * p[i]))
        out[i] = run
    return out


def binom_cap(n: int, p: float = ALPHA, q: float = 0.99) -> int:
    """The largest count c with P(Binomial(n, p) <= c) >= q: more keys than this below p fails the metric."""
    acc = 0.0
    for c in range(n + 1):
        acc += math.comb(n, c) * p ** c * (1 - p) ** (n - c)
        if acc >= q:
            return c
    return n


def nominal_dt(dt: float) -> float:
    """The nominal frame of a STATE dt: a multiple of 1/60 s (1/60 at 1x, 1/30 at 2x); freeze frames count as 1x."""
    return max(1, round(dt * 60.0)) / 60.0 if dt > 0.005 else 1.0 / 60.0


def grid_index(t: float, dt: float, k: int) -> int:
    """A state time of nominal frame dt as a step of the k-frame grid (module docstring)."""
    return math.ceil(max(0, round(t / dt)) / k)


def snap(t: float, dt: float, k: int) -> float:
    """A state time of nominal frame dt put on the k-frame grid (a recording at k x speed: --simulate-b)."""
    if k <= 1:
        return t
    return grid_index(t, dt, k) * k * dt


class Arm:
    def __init__(self):
        self.dwell = defaultdict(list)
        self.choice = defaultdict(lambda: defaultdict(int))
        self.speed = defaultdict(list)
        self.trans = defaultdict(lambda: defaultdict(int))     # (type, from) -> to -> exits (self-loops included)
        self.type_s: dict[str, float] = defaultdict(float)     # type -> FSM seconds (sum of its dwells)
        self.box = defaultdict(lambda: defaultdict(list))      # (type, state, name) -> bin -> [(x0, x1, y0, y1)]
        self.tbins = defaultdict(set)                          # (type, state) -> 1/60 s state-time bins seen
        self.apex = []                                         # (height u, air s, nominal frame s) per jump
        self.dts: Counter = Counter()                          # STATE dt (rounded to 1e-4) -> frames
        self.game_s = 0.0
        self.fights = 0
        self.per_fight: list["Arm"] = []                       # one Arm per fight (dwell, choice, speed, trans)

    @property
    def dt(self) -> float:
        """The arm's nominal frame in game seconds (of its most common STATE dt)."""
        common = [d for d, n in self.dts.most_common() if d > 0.005 and n > 0]
        return nominal_dt(common[0]) if common else 1.0 / 60.0

    def merge(self, o: "Arm") -> None:
        for k, v in o.dwell.items():
            self.dwell[k] += v
        for k, v in o.speed.items():
            self.speed[k] += v
        for tk, fams in o.choice.items():
            for fam, n in fams.items():
                self.choice[tk][fam] += n
        for k, tos in o.trans.items():
            for to, n in tos.items():
                self.trans[k][to] += n
        for tk, v in o.type_s.items():
            self.type_s[tk] += v
        for k, bins in o.box.items():
            for bn, v in bins.items():
                self.box[k][bn] += v
        for k, v in o.tbins.items():
            self.tbins[k] |= v
        self.apex += o.apex
        self.dts.update(o.dts)
        self.game_s += o.game_s
        self.fights += o.fights


def dist_bin(d: float) -> str:
    for lo, hi in zip(DIST_BINS[:-1], DIST_BINS[1:]):
        if lo <= d < hi:
            return f"{lo:g}-{hi:g}"
    return f">{DIST_BINS[-1]:g}"


def scan(fight, arm: Arm, with_ents: bool = True, stride: int = 1, sim_k: int = 1) -> None:
    """One fight into `arm`. stride / sim_k simulate a recording at that many times the speed (module docstring):
    entities read from every stride-th STATE (dt summed over the skipped ones), dwell put on the sim_k-frame grid."""
    starts = {(tk, s.control_fsm): dict(s.attack_starts) for tk, s in FORUM_SPECS.items()}
    ctl = {tk: s.control_fsm for tk, s in FORUM_SPECS.items()}
    keys = ("f", "dt", "ents", "ev", "hero") if with_ents else ("f", "dt", "ev")
    win: dict[int, tuple] = {}            # iid -> (state, x0, y0, game s so far)
    jump: dict[int, dict] = {}            # Clapper iid -> {"y0", "top", "t"} from its "Jump" entry to its "Air" exit
    pos: dict[int, float] = {}            # iid -> x of its last read
    pos_y: dict[int, float] = {}          # iid -> y of its last read
    hero_x = None
    acc_dt = 0.0
    n = 0
    for s in fight_states(fight, keys=keys):
        dt = float(s.get("dt") or 0.0)
        arm.game_s += dt
        acc_dt += dt
        n += 1
        read = with_ents and (n % stride == 0)
        if dt > 0:
            arm.dts[round(dt * sim_k, 4)] += 1 if (n % stride == 0) else 0
        if read:
            hero_x = ((s.get("hero") or {}).get("pos") or [None])[0]
            for e in s.get("ents") or ():
                if e.get("type_key") in FORUM_SPECS and e.get("pos"):
                    pos[e["iid"]] = e["pos"][0]
                    pos_y[e["iid"]] = e["pos"][1]
                    if e["iid"] in jump:
                        jump[e["iid"]]["top"] = max(jump[e["iid"]]["top"], e["pos"][1])
        for ev in s.get("ev") or ():
            if ev.get("k") != "fsm":
                continue
            d = ev.get("d") or {}
            obj = str(d.get("obj") or "")
            tk = obj.rsplit(" (", 1)[0] if obj.endswith(")") else obj
            tk = tk.replace("(Clone)", "").strip()
            if tk not in FORUM_SPECS or d.get("fsm") != ctl[tk]:
                continue
            frm, to, t_prev = d.get("from"), d.get("to"), d.get("t_in_prev")
            if frm is not None and t_prev is not None:
                arm.dwell[(tk, frm)].append(snap(float(t_prev), nominal_dt(dt), sim_k))
                arm.type_s[tk] += float(t_prev)
            if frm is not None and to is not None:
                arm.trans[(tk, frm)][to] += 1
            if tk == "Song Heavy Sentry" and with_ents:
                iid = d.get("ent")
                if to == "Jump" and iid in pos_y:
                    jump[iid] = {"y0": pos_y[iid], "top": pos_y[iid], "t": 0.0}
                elif iid in jump and frm in ("Jump", "Air") and t_prev is not None:
                    jump[iid]["t"] += float(t_prev)
                    if frm == "Air":
                        j = jump.pop(iid)
                        arm.apex.append((j["top"] - j["y0"], j["t"], nominal_dt(dt)))
                    elif to != "Air":
                        del jump[iid]
            fam = starts[(tk, d.get("fsm"))].get(d.get("to"))
            if fam:
                ex = pos.get(d.get("ent"))
                key = (tk, dist_bin(abs(hero_x - ex))) if (with_ents and ex is not None and hero_x is not None) \
                    else (tk, "*")
                arm.choice[key][fam] += 1
        if not read:
            continue
        step = acc_dt
        acc_dt = 0.0
        for e in s.get("ents") or ():
            tk = e.get("type_key")
            if tk not in FORUM_SPECS or not e.get("pos"):
                continue
            st = next((f.get("state") for f in e.get("fsms") or () if f.get("name") == ctl[tk]), None)
            t_in = next((f.get("t") for f in e.get("fsms") or () if f.get("name") == ctl[tk]), None)
            if st is None:
                continue
            iid = e["iid"]
            x, y = e["pos"][0], e["pos"][1]
            w = win.get(iid)
            if w is None or w[0] != st:
                win[iid] = (st, x, y, 0.0)
            else:
                g = w[3] + step
                if g >= SPEED_WIN_S - 1e-6:
                    arm.speed[(tk, st)].append(math.hypot(x - w[1], y - w[2]) / g)
                    win[iid] = (st, x, y, 0.0)
                else:
                    win[iid] = (st, w[1], w[2], g)
            if t_in is not None:
                arm.tbins[(tk, st)].add(int(round(float(t_in) * 60)))
                b = int(float(t_in) / BIN_S)
                flip = -1.0 if not e.get("flipX") else 1.0      # FACES_LEFT: flipX False faces -x
                for c in e.get("colliders") or ():
                    if not c.get("enabled") or not ((c.get("damage") or {}).get("eff")):
                        continue
                    v = c.get("verts_world") or ()
                    if not v:
                        continue
                    xs = [(vx - x) * flip for vx in v[0::2]]
                    ys = [vy - y for vy in v[1::2]]
                    arm.box[(tk, st, c.get("name"))][b].append((min(xs), max(xs), min(ys), max(ys)))
    arm.fights += 1


def probe_dt(runs: list[Path], frames: int = 600) -> float:
    """The nominal frame of an arm (its first fight's most common STATE dt)."""
    for run in runs:
        fights, _ = run_fights(Path(run))
        for fight in fights[:1]:
            c: Counter = Counter()
            for i, s in enumerate(fight_states(fight, keys=("f", "dt"))):
                dt = float(s.get("dt") or 0.0)
                if dt > 0.005:
                    c[round(dt, 4)] += 1
                if i >= frames:
                    break
            if c:
                return nominal_dt(c.most_common(1)[0][0])
    return 1.0 / 60.0


def _match(pat: str, v: str) -> bool:
    return pat in ("*", "") or pat == v


def parse_inject(spec: str):
    """A known change applied to each fight of arm B after its scan (the check's power: it must catch a difference of
    the size that matters for the tables). Specs:
      dwell:TYPE:STATE:+S      add S game seconds to every dwell of the matching (type, state) keys (* = any)
      dwellx:TYPE:STATE:F      multiply those dwells by F
      choice:TYPE:FROM:TO:P    move a share P of TYPE's FROM family starts to TO (every distance bin)
      speed:TYPE:F             multiply TYPE's window speeds by F
      trans:TYPE:FROM:TO:F     multiply the count of TYPE's FROM -> TO exits by F (rounded; e.g. a self-loop that
                               runs on real time: visit rate and successor shares; the dwells are left as they are)
    Returns fn(arm) that changes one fight's Arm in place."""
    p = spec.split(":")
    kind = p[0]
    if kind == "trans":
        tk, frm, to, f = p[1], p[2], p[3], float(p[4])

        def fn(arm: Arm) -> None:
            tos = arm.trans.get((tk, frm))
            if tos and tos.get(to):
                tos[to] = int(math.floor(tos[to] * f + 0.5))
        return fn
    if kind in ("dwell", "dwellx"):
        tk, st, v = p[1], p[2], float(p[3])

        def fn(arm: Arm) -> None:
            for (k_tk, k_st), vals in arm.dwell.items():
                if _match(tk, k_tk) and _match(st, k_st):
                    arm.dwell[(k_tk, k_st)] = [t + v if kind == "dwell" else t * v for t in vals]
        return fn
    if kind == "choice":
        tk, frm, to, share = p[1], p[2], p[3], float(p[4])

        def fn(arm: Arm) -> None:
            for key, fams in arm.choice.items():
                if key[0] != tk or not fams.get(frm):
                    continue
                n = fams[frm]
                moved = int(math.floor(n * share)) + (1 if (n * share) % 1.0 >= 0.5 else 0)
                fams[frm] -= moved
                fams[to] = fams.get(to, 0) + moved
        return fn
    if kind == "speed":
        tk, f = p[1], float(p[2])

        def fn(arm: Arm) -> None:
            for (k_tk, k_st), vals in arm.speed.items():
                if _match(tk, k_tk):
                    arm.speed[(k_tk, k_st)] = [v * f for v in vals]
        return fn
    raise SystemExit(f"unknown --inject {spec!r}")


def pick_units(pool: list, units: str) -> list:
    """Fights of the given AttemptRecord units "U1:n1,U2:n2,..." (the first n of each, in run order; n omitted = all):
    e.g. an independent 1x arm of the same waves as another run, from a long rotation run with other seeds."""
    want = {}
    for part in units.split(","):
        u, _, k = part.partition(":")
        want[u.strip()] = int(k) if k else None
    out, got = [], Counter()
    for fight in pool:
        u = fight.info.get("unit")
        if u in want and (want[u] is None or got[u] < want[u]):
            out.append(fight)
            got[u] += 1
    return out


def load(runs: list[Path], max_fights: int | None, with_ents: bool, stride: int = 1,
         sim_k: int = 1, fight_slice: str | None = None, inject=(), units: str | None = None) -> tuple[Arm, Arm, Arm]:
    """The whole arm and its two halves (alternating fights). fight_slice "start:stop:step" picks fights of the runs'
    list (e.g. an arm's even fights against its odd ones); units: pick_units; inject: parse_inject functions applied
    to each fight."""
    whole, h1, h2 = Arm(), Arm(), Arm()
    n = 0
    pool = []
    for run in runs:
        pool += run_fights(Path(run))[0]
    if units:
        pool = pick_units(pool, units)
    if fight_slice:
        pool = pool[slice(*[int(x) if x else None for x in fight_slice.split(":")])]
    for fight in pool[:max_fights] if max_fights is not None else pool:
        half = h1 if n % 2 == 0 else h2
        one = Arm()
        scan(fight, one, with_ents, stride, sim_k)
        for fn in inject:
            fn(one)
        for arm in (whole, half):
            arm.merge(one)
        one.box, one.tbins, one.apex = {}, {}, []
        whole.per_fight.append(one)
        half.per_fight.append(one)
        n += 1
    return whole, h1, h2


def on_grid(arm: Arm, grid: float) -> list[dict]:
    """Each fight's dwell lists as integer steps of the common grid (k = grid / the arm's nominal frame)."""
    dt = arm.dt
    k = max(1, round(grid / dt))
    return [{key: [float(grid_index(t, dt, k)) for t in v] for key, v in f.dwell.items()} for f in arm.per_fight]


def _perm_p(per: list, labels: np.ndarray, stat, rng, n_perm: int, n_max: int) -> tuple[float, float]:
    """Fight-level permutation p of stat(pooled per-fight data, labels), extended to n_max when below ALPHA."""
    obs = stat(per, labels)
    ge, done = 0, 0
    target = n_perm
    while done < target:
        ge += stat(per, rng.permutation(labels)) >= obs - 1e-12
        done += 1
        if done == target and target < n_max and (ge + 1) / (done + 1) < ALPHA:
            target = n_max
    return (ge + 1) / (done + 1), obs


def _ks_stat(per, lab):
    x = [p for p, l_ in zip(per, lab) if l_ == 0 and len(p)]
    y = [p for p, l_ in zip(per, lab) if l_ == 1 and len(p)]
    if not x or not y:
        return 0.0
    return ks(np.concatenate(x), np.concatenate(y))


def _tv_stat(per, lab):
    c0, c1 = Counter(), Counter()
    for p, l_ in zip(per, lab):
        (c0 if l_ == 0 else c1).update(p)
    return tv(c0, c1) if c0 and c1 else 0.0


def _rate_stat(per, lab):
    """|r_0 - r_1| / mean(r_0, r_1) of the pooled visit rates (per fight: (visits, type seconds))."""
    v0 = s0 = v1 = s1 = 0.0
    for (v, s), l_ in zip(per, lab):
        if l_ == 0:
            v0, s0 = v0 + v, s0 + s
        else:
            v1, s1 = v1 + v, s1 + s
    if s0 <= 0 or s1 <= 0:
        return 0.0
    r0, r1 = v0 / s0, v1 / s1
    return abs(r0 - r1) / ((r0 + r1) / 2.0) if r0 + r1 > 0 else 0.0


def _present(x) -> bool:
    """Does one fight's data for a key take part in the statistic (module docstring: attainable p)?"""
    if isinstance(x, tuple):
        return x[1] > 0
    if isinstance(x, dict):
        return sum(x.values()) > 0
    return len(x) > 0


def visits_per_fight(arm: Arm) -> list[dict]:
    """Each fight's (visits, the type's FSM seconds) per (type, state)."""
    out = []
    for f in arm.per_fight:
        out.append({k: (float(sum(tos.values())), float(f.type_s.get(k[0], 0.0))) for k, tos in f.trans.items()})
    return out


def perm_tests(a: Arm, b: Arm, min_n: int, n_perm: int = 200, seed: int = 0, n_perm_max: int = 5000,
               grid: float | None = None) -> dict:
    """Fight-level permutation tests per key (module docstring) with Holm and the binomial bound per metric."""
    rng = np.random.default_rng(seed)
    fa, fb = a.per_fight, b.per_fight
    labels = np.array([0] * len(fa) + [1] * len(fb))
    if grid:
        dwell_a, dwell_b = on_grid(a, grid), on_grid(b, grid)
    else:
        dwell_a, dwell_b = [f.dwell for f in fa], [f.dwell for f in fb]
    visits = visits_per_fight(a) + visits_per_fight(b)
    pooled = {"dwell": dwell_a + dwell_b, "speed": [f.speed for f in fa + fb],
              "choices": [f.choice for f in fa + fb], "next": [f.trans for f in fa + fb], "visits": visits}
    tot = {"dwell": (a.dwell, b.dwell), "speed": (a.speed, b.speed), "choices": (a.choice, b.choice),
           "next": (a.trans, b.trans), "visits": (a.trans, b.trans)}
    out = {}
    for m in ("dwell", "speed", "choices", "visits", "next"):
        ta, tb = tot[m]
        res = {}
        for k in sorted(set(ta) & set(tb), key=str):
            if m in ("choices", "next", "visits"):
                if sum(ta[k].values()) < min_n or sum(tb[k].values()) < min_n:
                    continue
                if m == "next" and len(set(ta[k]) | set(tb[k])) < 2:
                    continue                                   # a fixed successor: nothing to compare
                if m == "visits":
                    per = [f.get(k) or (0.0, 0.0) for f in pooled[m]]
                    if k[0] not in a.type_s or k[0] not in b.type_s:
                        continue
                    stat = _rate_stat
                else:
                    per = [dict(f.get(k) or {}) for f in pooled[m]]
                    stat = _tv_stat
            else:
                if len(ta[k]) < min_n or len(tb[k]) < min_n:
                    continue
                per = [np.asarray(f.get(k) or (), float) for f in pooled[m]]
                stat = _ks_stat
            res["/".join(k) if isinstance(k, tuple) else k] = (per, stat)
        n_max = max(n_perm_max, math.ceil(2 * len(res) / ALPHA))
        # per key: the fights of each arm that take part, and the smallest p a relabelling can give
        attain = {}
        for k, (per, _) in res.items():
            na = sum(_present(x) for x in per[:len(fa)])
            nb = sum(_present(x) for x in per[len(fa):])
            attain[k] = (na, nb, max(1.0 / math.comb(na + nb, na), 1.0 / (n_max + 1)) if na and nb else 1.0)
        res = {k: _perm_p(per, labels, stat, rng, n_perm, n_max) for k, (per, stat) in res.items()}
        names = list(res)
        ps = [res[k][0] for k in names]
        adj = holm(ps) if ps else []
        low = sorted(((k, p, d) for k, (p, d) in res.items() if p < ALPHA), key=lambda t: (t[1], -t[2]))
        cap = binom_cap(len(res)) if res else 0
        weak = sorted(k for k in names if attain[k][2] > ALPHA / len(names))
        min_p = min((attain[k][2] for k in names), default=1.0)
        out[m] = {"keys": len(res), "p_below_0.05": len(low),
                  "share_below_0.05": round(len(low) / len(res), 3) if res else None,
                  "binom_cap": cap,
                  "holm_significant": sorted(((k, round(pa, 5)) for k, pa in zip(names, adj) if pa < ALPHA),
                                             key=lambda t: t[1]),
                  "min_attainable_p": round(min_p, 6),
                  "underpowered": bool(res) and len(weak) == len(names),
                  "underpowered_keys": len(weak),
                  "underpowered_list": weak[:40],
                  # (key, p, statistic, fights of A / of B with the key, the key's smallest attainable p)
                  "lowest": [(k, round(p, 5), round(d, 3), attain[k][0], attain[k][1], round(attain[k][2], 6))
                             for k, p, d in low[:15]]}
    return out


def perm_verdict(perm: dict) -> dict:
    """Per metric: match when no Holm-significant key and the keys below 0.05 within the binomial bound; None when
    nothing was compared. "underpowered": Holm could not have rejected any key (more fights per type needed);
    "underpowered_keys": the keys Holm could not reject on their own (their types are in too few fights)."""
    out = {}
    for m, v in perm.items():
        if not v.get("keys"):
            out[m] = {"match": None}
            continue
        ok = not v["holm_significant"] and v["p_below_0.05"] <= v["binom_cap"]
        out[m] = {"match": ok, "keys": v["keys"], "below_0.05": v["p_below_0.05"], "cap": v["binom_cap"],
                  "holm": len(v["holm_significant"]), "underpowered": v["underpowered"],
                  "underpowered_keys": v["underpowered_keys"]}
    return out


def hitbox_cmp(a: Arm, b: Arm) -> dict:
    """Per (type, state, collider) the worst |extent difference| over the 0.05 s bins both have >= 3 samples of."""
    out = {}
    for k in set(a.box) & set(b.box):
        worst, n = 0.0, 0
        for bn in set(a.box[k]) & set(b.box[k]):
            ea, eb = np.asarray(a.box[k][bn]), np.asarray(b.box[k][bn])
            if len(ea) < 3 or len(eb) < 3:
                continue
            ext_a = np.array([ea[:, 0].min(), ea[:, 1].max(), ea[:, 2].min(), ea[:, 3].max()])
            ext_b = np.array([eb[:, 0].min(), eb[:, 1].max(), eb[:, 2].min(), eb[:, 3].max()])
            worst = max(worst, float(np.max(np.abs(ext_a - ext_b))))
            n += 1
        if n >= 3:
            out["/".join(str(x) for x in k)] = worst
    return out


def sampling(a: Arm, b: Arm) -> dict:
    out = {}
    for k in set(a.tbins) | set(b.tbins):
        for name, arm in (("a", a), ("b", b)):
            bins = arm.tbins.get(k)
            if bins and len(bins) > 10:
                span = max(bins) - min(bins) + 1
                out.setdefault("/".join(k), {})[name] = round(len(bins) / span, 3)
    return out


def apex_cmp(a: Arm, b: Arm, grid: float | None = None) -> dict | None:
    """Clapper jumps of both arms (module docstring: apex): height KS, air time KS in seconds and as steps of the
    common grid (each jump's air time on its recording's frame, then on the grid as the dwells are)."""
    if not (a.apex and b.apex):
        return None
    aa, bb = np.asarray(a.apex, float), np.asarray(b.apex, float)

    def steps(arr):
        if not grid:
            return arr[:, 1]
        return np.array([grid_index(t, ndt, max(1, round(grid / ndt))) for _, t, ndt in arr], float)
    sa, sb = steps(aa), steps(bb)
    return {"height_ks": ks(aa[:, 0], bb[:, 0]), "air_ks": ks(aa[:, 1], bb[:, 1]), "air_steps_ks": ks(sa, sb),
            "a_p50": [float(np.median(aa[:, 0])), float(np.median(aa[:, 1]))],
            "b_p50": [float(np.median(bb[:, 0])), float(np.median(bb[:, 1]))],
            "air_steps": {"a": dict(Counter(int(x) for x in sa).most_common(4)),
                          "b": dict(Counter(int(x) for x in sb).most_common(4))},
            "n": [len(aa), len(bb)]}


def hitbox_verdict(a1: Arm, a2: Arm, b1: Arm, b2: Arm) -> dict:
    """Hitbox extents have no fight-level test: B matches when at most HITBOX_SHARE_MAX of the keys differ (halves of A
    against halves of B) by more than twice the noise (each arm's halves against each other) and 0.1 u."""
    ab = [hitbox_cmp(a1, b1), hitbox_cmp(a2, b2)]
    nz = [hitbox_cmp(a1, a2), hitbox_cmp(b1, b2)]
    keys = set(ab[0]) & set(ab[1]) & set(nz[0]) & set(nz[1])
    over = []
    for k in keys:
        d = (ab[0][k] + ab[1][k]) / 2.0
        n = (nz[0][k] + nz[1][k]) / 2.0
        if d > max(2.0 * n, n + 0.1):
            over.append((k, round(d, 3), round(n, 3)))
    return {"keys": len(keys), "over": sorted(over, key=lambda t: -t[1])[:20],
            "share": round(len(over) / len(keys), 3) if keys else None,
            "match": (len(over) / len(keys) <= HITBOX_SHARE_MAX) if keys else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", type=Path, nargs="+", required=True)
    ap.add_argument("--b", type=Path, nargs="+", required=True)
    ap.add_argument("--min", type=int, default=20)
    ap.add_argument("--max-fights", type=int)
    ap.add_argument("--perm", type=int, default=200, help="fight-level permutations per key")
    ap.add_argument("--perm-max", type=int, default=5000, help="... extended to this many for keys below 0.05")
    ap.add_argument("--events-only", action="store_true", help="dwell and choices only (no ents decode)")
    ap.add_argument("--no-grid", action="store_true", help="dwell without the common frame grid (for comparison)")
    ap.add_argument("--simulate-b", type=int, default=1, metavar="K",
                    help="arm B as if recorded at K x speed (calibration)")
    ap.add_argument("--a-slice", default=None, help="start:stop:step of arm A's fights (e.g. ::2)")
    ap.add_argument("--b-slice", default=None, help="start:stop:step of arm B's fights (e.g. 1::2)")
    ap.add_argument("--a-units", default=None, help="arm A's fights by unit, e.g. Forum_A_w7:4,Forum_A_w13:4 (pick_units)")
    ap.add_argument("--b-units", default=None, help="arm B's fights by unit (pick_units)")
    ap.add_argument("--inject", action="append", default=[], metavar="SPEC",
                    help="a known change in arm B (parse_inject: dwell / dwellx / choice / speed); repeatable")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    # entities of both arms read on the coarsest arm's frames (module docstring: speed)
    dt_a, dt_b = probe_dt(a.a), probe_dt(a.b) * a.simulate_b
    frame = max(dt_a, dt_b)
    A, A1, A2 = load(a.a, a.max_fights, not a.events_only, stride=max(1, round(frame / dt_a)), fight_slice=a.a_slice,
                     units=a.a_units)
    B, B1, B2 = load(a.b, a.max_fights, not a.events_only, stride=a.simulate_b * max(1, round(frame / dt_b)),
                     sim_k=a.simulate_b, fight_slice=a.b_slice, inject=[parse_inject(s) for s in a.inject],
                     units=a.b_units)
    grid = None if a.no_grid else max(A.dt, B.dt)
    res = {"a": {"fights": A.fights, "game_s": round(A.game_s, 1), "dt": A.dt, "read_stride": round(frame / dt_a),
                 "slice": a.a_slice, "units": a.a_units},
           "b": {"fights": B.fights, "game_s": round(B.game_s, 1), "dt": B.dt, "simulated_k": a.simulate_b,
                 "slice": a.b_slice, "units": a.b_units, "inject": a.inject},
           "grid_s": grid,
           "perm": perm_tests(A, B, a.min, a.perm, n_perm_max=a.perm_max, grid=grid),
           # the same tests between each arm's halves: their false positives (informational)
           "perm_noise_a": perm_tests(A1, A2, max(5, a.min // 2), a.perm, n_perm_max=a.perm_max, grid=grid),
           "perm_noise_b": perm_tests(B1, B2, max(5, a.min // 2), a.perm, n_perm_max=a.perm_max, grid=grid)}
    res["perm_verdict"] = perm_verdict(res["perm"])

    def fam_totals(arm: Arm) -> dict:
        out: dict = {}
        for (tk, _), fams in arm.choice.items():
            for fam, n in fams.items():
                out.setdefault(tk, Counter())[fam] += n
        return {tk: dict(c.most_common()) for tk, c in out.items()}
    # per type, the family counts of each arm (B after --inject): the size of an injected choice change in points
    res["choice_totals"] = {"a": fam_totals(A), "b": fam_totals(B)}
    if not a.events_only:
        res["perm_verdict"]["hitbox"] = hitbox_verdict(A1, A2, B1, B2)
        res["sampling"] = sampling(A, B)
        res["apex"] = apex_cmp(A, B, grid)
    if a.json:
        a.json.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("a", "b", "grid_s", "perm_verdict")}, indent=1))
    for m, v in res["perm"].items():
        print(m, {k: v[k] for k in ("keys", "p_below_0.05", "binom_cap", "holm_significant", "underpowered",
                                    "underpowered_keys")})
    if res.get("apex"):
        print("apex", json.dumps(res["apex"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
