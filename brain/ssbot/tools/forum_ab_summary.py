"""Forum live A/B summary (task "wave-0 de-saturation", forum.md §23.12): per arm and paired over the run manifests
of the live drivers (C:/ssbot/sandbox/w0d_live.ps1: one line per chunk, "arm<TAB>seed<TAB>instance<TAB>run dir").

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_ab_summary <manifest> [<manifest> ...] [--json out.json]
        [--arms a,b] [--boot 4000]

Per arm (HARNESS_FAIL attempts left out): outcomes, the waves reached and wave 0 cleared, time alive (median / mean),
hits a minute, kills, the hit sources, the FORCED_RISK and late-tick shares, the hits outside the support at
UNPRED_LAGS (2-4 frames: "unpredicted", "unknown"), and from the decision logs (the 90 ticks kept before every hit;
any code version) the hits whose chosen plan was S = 0 at a lag of 12 / 24 / 30 frames or anywhere in the 30 frames
before ("planned safe": a risk the 2-4 frame check cannot see, the review of 2026-10-08), with a clean clash row chosen
S = 0 in those 30 frames, by source; the Reed-pin hits whose Reed was in a throw before its release at the 12-30 frame
lags; the escape check's audit (ticks, failed / unchecked shares, cut per tick, S = 1 by the escape check). Paired
(same instance, chunk seed, episode index): time alive, kills and hits a minute differences with bootstrap 95 % CIs.
"""
import argparse
import bisect
import itertools
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

LAGS = (12, 24, 30)
# the Reed's throw states before its release ("Throw": the pin flies on that frame; Reed.json attacks.RE_THROW)
REED_PRE_RELEASE = frozenset(("Throw Range", "Throw Recoil", "Throw Antic Anim", "Throw Antic", "Throw Aim",
                              "Throw Lock", "Lock L", "Throwing Up?", "Throw Down", "Lock R High", "Lock R Low",
                              "Throw Up", "Throw Transition"))


def load(manifests: list[str], arms: set | None) -> dict:
    eps = defaultdict(list)
    for man in manifests:
        for line in Path(man).read_text("utf-8-sig").splitlines():
            p = line.strip().split("\t")
            if len(p) < 4 or not p[3].strip() or (arms and p[0] not in arms):
                continue
            name, seed, inst, rd = p[0], int(p[1]), int(p[2]), Path(p[3].strip())
            f = rd / f"attempts_i{inst}.jsonl"
            if not f.exists():
                continue
            dec = defaultdict(list)
            df = rd / f"decisions_i{inst}.jsonl"
            if df.exists():
                for x in df.read_text("utf-8").splitlines():
                    if x.strip():
                        r = json.loads(x)
                        if "S" in r:
                            dec[r["ep"]].append(r)
            for x in f.read_text("utf-8").splitlines():
                if not x.strip():
                    continue
                r = json.loads(x)
                r["_key"] = (inst, seed, int(r["episode"]))
                r["_dec"] = sorted(dec.get(int(r["episode"]), ()), key=lambda d: d["f"])
                eps[name].append(r)
    return eps


def planned(rs: list) -> dict:
    """The decision-log hits (hp down within 3 frames of the last logged tick) against the plans before them."""
    c = Counter()
    src = Counter()
    for r in rs:
        L = r["_dec"]
        fs = [d["f"] for d in L]
        pol = r.get("policy") or {}
        paths = {h["f"]: str(h.get("path") or h.get("src_type")) for h in pol.get("hit_log") or ()
                 if h.get("kind") == "damage"}
        for i in range(1, len(L)):
            x = L[i]
            if not (x["hp"] < L[i - 1]["hp"] and x["f"] - L[i - 1]["f"] <= 3):
                continue
            F = x["f"]
            c["hits"] += 1
            for lag in LAGS:
                j = bisect.bisect_right(fs, F - lag) - 1
                if j < 0 or F - lag - fs[j] > 3:
                    c[f"unknown_{lag}"] += 1
                    continue
                y = L[j]
                c[f"safe_{lag}"] += int(y["S"] == 0)
                c[f"esc_unsafe_{lag}"] += int(bool(((y.get("fi") or {}).get("esc") or {}).get("unsafe")))
            j0 = bisect.bisect_left(fs, F - 30)
            win = L[j0:i]
            safe = [y for y in win if y["S"] == 0]
            c["any30"] += int(bool(safe))
            c["clash30"] += int(any(y.get("clash") and not y["clash"][2] for y in safe))
            path = next((paths[g] for g in range(F - 3, F + 4) if g in paths), "?")
            if safe:
                src[path] += 1
            if "Pin" in path:
                c["pin_hits"] += 1
                lagw = [y for y in L[bisect.bisect_left(fs, F - 30):bisect.bisect_right(fs, F - 12)]]
                c["pin_hits_throw_under_way"] += int(any(s[1] == "Song Reed" and s[2] in REED_PRE_RELEASE
                                                         for y in lagw for s in y.get("subj") or ()))
    return {**dict(c), "by_src": src.most_common(10)}


def row(name: str, rs: list) -> dict:
    rs = [r for r in rs if r.get("outcome") != "HARNESS_FAIL"]
    t = np.array([float(r.get("ingame_s") or 0.0) for r in rs])
    hits = np.array([float(r.get("hits") or 0) for r in rs])
    g = [r.get("gauntlet") or {} for r in rs]
    kills = np.array([float((x.get("kills") or {}).get("n") or 0) for x in g])
    wave = Counter(int(x.get("wave_reached") or 0) for x in g)
    kby, srcs = Counter(), Counter()
    for x, r in zip(g, rs):
        kby.update((x.get("kills") or {}).get("by_type") or {})
        for h in (r.get("policy") or {}).get("hit_log") or ():
            if h.get("kind") == "damage":
                srcs[str(h.get("path") or h.get("src_type"))] += 1
    pol = [r.get("policy") or {} for r in rs]
    au = Counter()
    for p in pol:
        for k, v in (p.get("audit") or {}).items():
            if isinstance(v, (int, float)) and k.startswith(("esc", "clash", "pin")):
                au[k] += v
    ticks = sum(int(p.get("ticks") or 0) for p in pol)
    mins = max(float(t.sum()) / 60.0, 1e-9)
    pl = planned(rs)
    esc = {"ticks": int(au["esc_ticks"]), "fail_share": round(1 - au["esc_pass"] / au["esc_ticks"], 3)
           if au["esc_ticks"] else None, "cut_per_tick": round(au["esc_cut"] / max(ticks, 1), 3),
           "unsafe": int(au["esc_unsafe"]), "failed": int(au["esc_failed"]), "unchecked": int(au["esc_unchecked"]),
           "carried": int(au["esc_carried"]), "forced_ticks": int(au["esc_forced_ticks"]),
           "forced_pass": int(au["esc_forced_pass"])}
    return {"arm": name, "n": len(rs), "outcomes": dict(Counter(r.get("outcome") for r in rs)),
            "wave_reached": dict(sorted(wave.items())), "wave0_cleared": sum(v for k, v in wave.items() if k >= 1),
            "t_med": round(float(np.median(t)), 2) if len(t) else None,
            "t_mean": round(float(t.mean()), 2) if len(t) else None, "minutes": round(mins, 1),
            "hits_per_min": round(float(hits.sum()) / mins, 2), "kills_per_ep": round(float(kills.mean()), 2)
            if len(t) else None, "kills_by_type": dict(kby), "hit_src_top": srcs.most_common(8),
            "forced_share": round(float(np.mean([(p.get("forced_risk_ticks") or 0) / max(p.get("ticks") or 1, 1)
                                                 for p in pol])), 3) if pol else None,
            "late_share": round(float(np.mean([(p.get("late_ticks") or 0) / max(p.get("ticks") or 1, 1)
                                               for p in pol])), 3) if pol else None,
            "unpredicted": sum(len(p.get("unpredicted") or ()) for p in pol),
            "unpredicted_unknown": sum(len(p.get("unpredicted_unknown") or ()) for p in pol),
            "planned_safe": pl,
            "planned_safe_per_min": {k: round(pl.get(k, 0) / mins, 3) for k in ("safe_12", "safe_24", "safe_30",
                                                                                 "any30", "clash30")},
            "clash": {k: int(v) for k, v in au.items() if k.startswith("clash") and v},
            "pin": {"ticks": int(au["pin_ticks"]), "rows": int(au["pin_rows"])}, "escape": esc}


def paired(eps: dict, a: str, b: str, boot: int) -> dict | None:
    ka = {r["_key"]: r for r in eps[a] if r.get("outcome") != "HARNESS_FAIL"}
    kb = {r["_key"]: r for r in eps[b] if r.get("outcome") != "HARNESS_FAIL"}
    common = sorted(set(ka) & set(kb))
    if not common:
        return None

    def kills(r):
        return float(((r.get("gauntlet") or {}).get("kills") or {}).get("n") or 0)

    def hpm(r):
        return float(r.get("hits") or 0) / max(float(r.get("ingame_s") or 0), 1.0) * 60

    out = {"a": a, "b": b, "n_pairs": len(common)}
    rng = random.Random(0)
    for nm, fn in (("dt", lambda r: float(r.get("ingame_s") or 0)), ("dkills", kills), ("dhits_per_min", hpm)):
        d = np.array([fn(kb[k]) - fn(ka[k]) for k in common])
        bs = sorted(float(np.mean([d[rng.randrange(len(d))] for _ in d])) for _ in range(boot))
        out[nm] = round(float(d.mean()), 3)
        out[nm + "_ci"] = [round(bs[int(0.025 * boot)], 3), round(bs[int(0.975 * boot) - 1], 3)]
    out["b_longer"] = int(sum(float(kb[k].get("ingame_s") or 0) > float(ka[k].get("ingame_s") or 0) for k in common))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("manifests", nargs="+")
    ap.add_argument("--json")
    ap.add_argument("--arms", help="comma-separated arm names (default: every arm in the manifests)")
    ap.add_argument("--boot", type=int, default=4000)
    a = ap.parse_args()
    eps = load(a.manifests, set(a.arms.split(",")) if a.arms else None)
    arms = {n: row(n, rs) for n, rs in sorted(eps.items())}
    for d in arms.values():
        print(json.dumps(d))
    pairs = [p for x, y in itertools.combinations(sorted(eps), 2) if (p := paired(eps, x, y, a.boot))]
    for p in pairs:
        print("paired", json.dumps(p))
    if a.json:
        Path(a.json).write_text(json.dumps({"arms": arms, "paired": pairs}, indent=1), "utf-8")


if __name__ == "__main__":
    main()
