"""Does the Forum play the same at another game speed? (Forum plan R1 item 4: collect data at 2x only if the enemies'
FSM timings, attack choices, physics paths and recorded hitboxes match 1x within the measured noise.)

Compares arm A (e.g. 1x) with arm B (e.g. 2x, combat_run --time-scale 2 --same-seeds on another instance): each arm's
fights are split in two halves (alternating); the distance is the mean of A-half vs B-half, the noise the mean of
A-half vs A-half and B-half vs B-half, so both come from the same sample sizes. Everything in game time (STATE dt sums and the
"fsm" events' t_in_prev, the scaled StateTime), so the frame rate of each arm does not enter except as sampling:

  dwell      per (type, FSM state) the game seconds spent in the state (t_in_prev of the event leaving it):
             Kolmogorov-Smirnov distance between the arms, states with >= --min n in both
  choices    per type the family shares of attack starts (FORUM_SPECS): total variation distance
  speed      per (type, state) the enemy transform speed (|d pos| / dt per frame): KS distance (physics paths)
  hitbox     per (type, state, collider name) the damage collider's extent relative to the enemy transform, flipped
             to face +x, per 0.05 s state-time bin: max over bins of |extent difference| (u), and the share of 1/60 s
             state-time bins with a sample (a 2x recording samples every other one)
  apex       Choir Clapper jumps: the body's highest point above the takeoff and the air time (Jump -> Air -> landing)

Verdict per metric: B matches A when its distance is within the A-vs-A distance's (noise) value times --slack, for
the keys both have enough samples of.

    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_speed_check --a <run 1x> [...] --b <run 2x> [...] --json out.json
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.knowledge.behaviour_tables import fight_states, run_fights
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS

BIN_S = 0.05


def ks(a: list[float], b: list[float]) -> float:
    """Two-sample Kolmogorov-Smirnov distance."""
    if not a or not b:
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


def perm_tests(a: "Arm", b: "Arm", min_n: int, n_perm: int = 200, seed: int = 0) -> dict:
    """Fight-level permutation tests (samples within a fight are not independent: the hero's play and HP differ per
    fight, so per-sample KS p-values are far too small, see the halves of one arm): the fights of A and B are pooled
    and relabelled at random n_perm times; p = share of relabellings whose statistic (KS for dwell and speed, total
    variation for the family shares) is >= the observed one. Under no difference about 5 % of keys get p < 0.05."""
    rng = np.random.default_rng(seed)
    fa, fb = a.per_fight, b.per_fight
    pool = fa + fb
    labels = np.array([0] * len(fa) + [1] * len(fb))
    out = {}
    for m, attr, stat in (("dwell", "dwell", ks), ("speed", "speed", ks), ("choices", "choice", None)):
        keys = set(getattr(a, attr)) & set(getattr(b, attr))
        res = {}
        for k in keys:
            if stat is None:
                if sum(getattr(a, attr)[k].values()) < min_n or sum(getattr(b, attr)[k].values()) < min_n:
                    continue

                def val(sel):
                    c0, c1 = defaultdict(int), defaultdict(int)
                    for f, lab in zip(pool, sel):
                        for fam, n in (getattr(f, attr).get(k) or {}).items():
                            (c0 if lab == 0 else c1)[fam] += n
                    return tv(c0, c1)
            else:
                if len(getattr(a, attr)[k]) < min_n or len(getattr(b, attr)[k]) < min_n:
                    continue
                per = [getattr(f, attr).get(k) or [] for f in pool]

                def val(sel, per=per):
                    x = [v for p, lab in zip(per, sel) if lab == 0 for v in p]
                    y = [v for p, lab in zip(per, sel) if lab == 1 for v in p]
                    return ks(x, y) if x and y else 0.0
            obs = val(labels)
            ge = sum(val(rng.permutation(labels)) >= obs - 1e-12 for _ in range(n_perm))
            res["/".join(k) if isinstance(k, tuple) else k] = ((ge + 1) / (n_perm + 1), obs)
        low = sorted(((k, p, d) for k, (p, d) in res.items() if p < 0.05), key=lambda t: (t[1], -t[2]))
        out[m] = {"keys": len(res), "p_below_0.05": len(low),
                  "share_below_0.05": round(len(low) / len(res), 3) if res else None,
                  "lowest": [(k, round(p, 4), round(d, 3)) for k, p, d in low[:15]]}
    return out


HITBOX_SHARE_MAX = 0.05
PERM_SHARE_MAX = 0.10     # under no difference about 5 % of the keys get p < 0.05 (1x vs 1x: 0.7 %, forum.md R1)


def perm_verdict(perm: dict, noise: dict) -> dict:
    """B matches A on a metric when the share of its keys with a fight-level permutation p < 0.05 is at most
    PERM_SHARE_MAX and at most twice the share between A's own halves (the measured noise)."""
    out = {}
    for m, v in perm.items():
        sh, nz = v.get("share_below_0.05"), (noise.get(m) or {}).get("share_below_0.05")
        out[m] = {"share": sh, "noise_share": nz,
                  "match": None if sh is None else sh <= max(PERM_SHARE_MAX, 2.0 * (nz or 0.0))}
    return out


def tests(a: "Arm", b: "Arm", min_n: int, alpha: float = 0.01) -> dict:
    """Per key significance (Bonferroni over the keys of each metric): dwell and speed by KS, choices by chi-square."""
    out = {}
    for m, da, db, fn in (("dwell", a.dwell, b.dwell, None), ("speed", a.speed, b.speed, None),
                          ("choices", a.choice, b.choice, "chi2")):
        res = {}
        for k in set(da) & set(db):
            if fn == "chi2":
                if sum(da[k].values()) >= min_n and sum(db[k].values()) >= min_n:
                    res[k] = chi2_p(da[k], db[k])
            elif len(da[k]) >= min_n and len(db[k]) >= min_n:
                res["/".join(k)] = ks_p(ks(da[k], db[k]), len(da[k]), len(db[k]))
        cut = alpha / max(1, len(res))
        sig = sorted(((k, p) for k, p in res.items() if not math.isnan(p) and p < cut), key=lambda t: t[1])
        out[m] = {"keys": len(res), "significant": [(k, float(f"{p:.2g}")) for k, p in sig[:20]],
                  "n_significant": len(sig)}
    return out


def tv(a: dict[str, int], b: dict[str, int]) -> float:
    na, nb = sum(a.values()), sum(b.values())
    if not na or not nb:
        return float("nan")
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0) / na - b.get(k, 0) / nb) for k in keys)


class Arm:
    def __init__(self):
        self.dwell = defaultdict(list)
        self.choice = defaultdict(lambda: defaultdict(int))
        self.speed = defaultdict(list)
        self.box = defaultdict(lambda: defaultdict(list))      # (type, state, name) -> bin -> [(x0, x1, y0, y1)]
        self.tbins = defaultdict(set)                          # (type, state) -> 1/60 s state-time bins seen
        self.apex = []
        self.game_s = 0.0
        self.fights = 0
        self.per_fight: list["Arm"] = []                       # one Arm per fight (dwell, choice, speed only)

    def merge(self, o: "Arm") -> None:
        for k, v in o.dwell.items():
            self.dwell[k] += v
        for k, v in o.speed.items():
            self.speed[k] += v
        for tk, fams in o.choice.items():
            for fam, n in fams.items():
                self.choice[tk][fam] += n
        for k, bins in o.box.items():
            for bn, v in bins.items():
                self.box[k][bn] += v
        for k, v in o.tbins.items():
            self.tbins[k] |= v
        self.apex += o.apex
        self.game_s += o.game_s
        self.fights += o.fights


def scan(fight, arm: Arm, with_ents: bool = True) -> None:
    starts = {(tk, s.control_fsm): dict(s.attack_starts) for tk, s in FORUM_SPECS.items()}
    ctl = {tk: s.control_fsm for tk, s in FORUM_SPECS.items()}
    keys = ("f", "dt", "ents", "ev") if with_ents else ("f", "dt", "ev")
    last_pos: dict[int, tuple[float, float]] = {}
    jump: dict[int, dict] = {}
    for s in fight_states(fight, keys=keys):
        dt = float(s.get("dt") or 0.0)
        arm.game_s += dt
        tks = {}
        for ev in s.get("ev") or ():
            if ev.get("k") != "fsm":
                continue
            d = ev.get("d") or {}
            obj = str(d.get("obj") or "")
            tk = obj.rsplit(" (", 1)[0] if obj.endswith(")") else obj
            tk = tk.replace("(Clone)", "").strip()
            if tk not in FORUM_SPECS or d.get("fsm") != ctl[tk]:
                continue
            if d.get("from") is not None and d.get("t_in_prev") is not None:
                arm.dwell[(tk, d["from"])].append(float(d["t_in_prev"]))
            fam = starts[(tk, d.get("fsm"))].get(d.get("to"))
            if fam:
                arm.choice[tk][fam] += 1
        if not with_ents:
            continue
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
            if iid in last_pos and dt > 0:
                px, py = last_pos[iid]
                arm.speed[(tk, st)].append(math.hypot(x - px, y - py) / dt)
            last_pos[iid] = (x, y)
            tks[iid] = tk
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
            if tk == "Song Heavy Sentry":
                if st == "Jump" and iid not in jump:
                    jump[iid] = {"y0": y, "top": y, "t": 0.0}
                elif iid in jump:
                    j = jump[iid]
                    j["top"] = max(j["top"], y)
                    j["t"] += dt
                    if st not in ("Jump", "Air"):
                        arm.apex.append((j["top"] - j["y0"], j["t"]))
                        del jump[iid]
    arm.fights += 1


def load(runs: list[Path], max_fights: int | None, with_ents: bool) -> tuple[Arm, Arm, Arm]:
    """The whole arm and its two halves (alternating fights)."""
    whole, h1, h2 = Arm(), Arm(), Arm()
    n = 0
    for run in runs:
        fights, _ = run_fights(Path(run))
        for fight in fights:
            if max_fights is not None and n >= max_fights:
                break
            half = h1 if n % 2 == 0 else h2
            one = Arm()
            scan(fight, one, with_ents)
            for arm in (whole, half):
                arm.merge(one)
            one.box, one.tbins, one.apex = {}, {}, []
            whole.per_fight.append(one)
            half.per_fight.append(one)
            n += 1
    return whole, h1, h2


def compare(a: Arm, b: Arm, min_n: int) -> dict:
    out = {"dwell": {}, "choices": {}, "speed": {}, "hitbox": {}, "sampling": {}}
    for k in set(a.dwell) & set(b.dwell):
        if len(a.dwell[k]) >= min_n and len(b.dwell[k]) >= min_n:
            out["dwell"]["/".join(k)] = ks(a.dwell[k], b.dwell[k])
    for tk in set(a.choice) & set(b.choice):
        if sum(a.choice[tk].values()) >= min_n and sum(b.choice[tk].values()) >= min_n:
            out["choices"][tk] = tv(a.choice[tk], b.choice[tk])
    for k in set(a.speed) & set(b.speed):
        if len(a.speed[k]) >= 5 * min_n and len(b.speed[k]) >= 5 * min_n:
            out["speed"]["/".join(k)] = ks(a.speed[k], b.speed[k])
    for k in set(a.box) & set(b.box):
        worst = 0.0
        n = 0
        for bn in set(a.box[k]) & set(b.box[k]):
            ea, eb = np.asarray(a.box[k][bn]), np.asarray(b.box[k][bn])
            if len(ea) < 3 or len(eb) < 3:
                continue
            ext_a = np.array([ea[:, 0].min(), ea[:, 1].max(), ea[:, 2].min(), ea[:, 3].max()])
            ext_b = np.array([eb[:, 0].min(), eb[:, 1].max(), eb[:, 2].min(), eb[:, 3].max()])
            worst = max(worst, float(np.max(np.abs(ext_a - ext_b))))
            n += 1
        if n >= 3:
            out["hitbox"]["/".join(str(x) for x in k)] = worst
    for k in set(a.tbins) | set(b.tbins):
        for name, arm in (("a", a), ("b", b)):
            bins = arm.tbins.get(k)
            if bins and len(bins) > 10:
                span = max(bins) - min(bins) + 1
                out["sampling"].setdefault("/".join(k), {})[name] = round(len(bins) / span, 3)
    if a.apex and b.apex:
        aa, bb = np.asarray(a.apex), np.asarray(b.apex)
        out["apex"] = {"height_ks": ks(list(aa[:, 0]), list(bb[:, 0])), "air_ks": ks(list(aa[:, 1]), list(bb[:, 1])),
                       "a_p50": [float(np.median(aa[:, 0])), float(np.median(aa[:, 1]))],
                       "b_p50": [float(np.median(bb[:, 0])), float(np.median(bb[:, 1]))], "n": [len(aa), len(bb)]}
    return out


def mean_cmp(x: dict, y: dict) -> dict:
    """Key-wise mean of two compare() results (keys both have); sampling taken from the first."""
    out = {}
    for m in ("dwell", "choices", "speed", "hitbox"):
        out[m] = {k: (x[m][k] + y[m][k]) / 2.0 for k in set(x[m]) & set(y[m])}
    out["sampling"] = x.get("sampling", {})
    return out


def verdict(ab: dict, noise: dict, slack: float) -> dict:
    """Per metric: keys compared, how many exceed slack x noise (noise keys missing count as exceeding)."""
    out = {}
    for m in ("dwell", "choices", "speed", "hitbox"):
        over = []
        for k, v in ab[m].items():
            nz = noise[m].get(k)
            if nz is None or (isinstance(v, float) and math.isnan(v)):
                continue
            if v > slack * max(nz, 1e-9) and v - nz > (0.05 if m != "hitbox" else 0.1):
                over.append((k, round(v, 3), round(nz, 3)))
        out[m] = {"keys": sum(1 for k in ab[m] if k in noise[m]), "over": sorted(over, key=lambda t: -t[1])[:20],
                  "match": not over}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", type=Path, nargs="+", required=True)
    ap.add_argument("--b", type=Path, nargs="+", required=True)
    ap.add_argument("--min", type=int, default=20)
    ap.add_argument("--slack", type=float, default=1.5)
    ap.add_argument("--max-fights", type=int)
    ap.add_argument("--perm", type=int, default=200, help="fight-level permutations per key")
    ap.add_argument("--events-only", action="store_true", help="dwell and choices only (no ents decode)")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    A, A1, A2 = load(a.a, a.max_fights, not a.events_only)
    B, B1, B2 = load(a.b, a.max_fights, not a.events_only)
    # like against like: the halves of A against the halves of B, and each arm's halves against each other (the noise),
    # so both distances come from the same sample sizes
    m = max(5, a.min // 2)
    ab = mean_cmp(compare(A1, B1, m), compare(A2, B2, m))
    noise = mean_cmp(compare(A1, A2, m), compare(B1, B2, m))
    if A.apex and B.apex:
        ab["apex"] = compare(A, B, a.min).get("apex")
    res = {"a": {"fights": A.fights, "game_s": round(A.game_s, 1)}, "b": {"fights": B.fights, "game_s": round(B.game_s, 1)},
           # significance on the whole arms, and the same test between A's halves (its false positives: should be 0)
           "tests": tests(A, B, a.min), "tests_noise": tests(A1, A2, max(5, a.min // 2)),
           "perm": perm_tests(A, B, a.min, a.perm), "perm_noise": perm_tests(A1, A2, max(5, a.min // 2), a.perm),
           "verdict": verdict(ab, noise, a.slack), "ab": ab, "noise": noise}
    res["perm_verdict"] = perm_verdict(res["perm"], res["perm_noise"])
    hb = res["verdict"]["hitbox"]
    # hitbox extents have no fight-level test: B matches when at most HITBOX_SHARE_MAX of the keys differ by more
    # than twice the noise and 0.1 u (1x vs 1x, 4 + 4 gauntlets: 2 of 239 keys, 0.8 %)
    n_over = len([o for o in res["ab"]["hitbox"] if o in res["noise"]["hitbox"]
                  and res["ab"]["hitbox"][o] > max(2.0 * res["noise"]["hitbox"][o], res["noise"]["hitbox"][o] + 0.1)])
    res["perm_verdict"]["hitbox"] = {"keys": hb["keys"], "share": round(n_over / hb["keys"], 3) if hb["keys"] else None,
                                       "match": (n_over / hb["keys"] <= HITBOX_SHARE_MAX) if hb["keys"] else None}
    if a.json:
        a.json.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("a", "b", "perm", "perm_noise", "perm_verdict", "verdict")}, indent=1))
    if "apex" in ab:
        print("apex", json.dumps(ab["apex"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
