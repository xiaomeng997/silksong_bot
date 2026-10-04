"""Open-loop replay of Forum gauntlets through the offline Forum stack (M2 Forum round R0; docs/plans/
forum_planner_plan.md §5 R0: the synthesis of the hierarchical design's forum_sim and the incremental design's
forum_simul): the per-fight caches (ssbot.tools.forum_extract) are fed frame by frame to the enemies' trackers
(ssbot.knowledge.forum_support.SubjectTracker), and per frame the checks below are tallied.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_simul --cache C:/ssbot/data/m2_forum_r0/cache
        [--fights 20261003_074719_Forum_A_data/i3/ep0,...] [--first 12 --run 20261003_074719_Forum_A_data]
        [--forecast EXTRA --fold 0 --every 6] [--json out.json]

concurrency (always): the enemies in play per frame and per wave (the hierarchical design's table 1.2, which this
  reproduces on the same 12 fights): in play = a HealthManager entity (src bit 1), not hidden, hp > 0, its Control
  state set and not a waiting state (ssbot.train.gauntlet.WAITING_STATES), a Maestro summon not in "Dead"; the wave
  from room.battles; committed = the tracker's current instance is an attack (not the idle family); per wave: game
  seconds, in-play p50 / p95 / max, the share of frames with >= 2, the commonest combinations, and with >= 2 the
  median x span, the share with enemies on both sides of the hero within 12 u, the share with the two nearest less
  than 3 u apart in x, all idle / mixed / all committed, and the share with >= 1 / >= 2 enemies within 6 u of the hero.
forecast (--forecast EXTRA): every --every-th frame the support placements of every subject at horizon 0.8 s
  (forum_support.SubjectRecall.placements_of with the fold's tables and the held-out margins of the other fold; the
  anchors of attacks that start later every 0.2 s along the enemy's velocity: statistics, not a certified support) and
  whether a hero standing still is inside the support at 0 / 0.2 / 0.4 / 0.8 s: how much of the time the support
  leaves the hero no room where it stands, per wave.
"""
import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.knowledge.forum_cache import cache_name, load_cache
from ssbot.knowledge.forum_support import FoldTables, SubjectRecall, SubjectTracker, margins_from_contacts, \
    read_contacts, replay
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
from ssbot.train.gauntlet import WAITING_STATES

TINY = "Song Automaton Tiny"
SHORT = {"Song Pilgrim 03": "Choristor", "Song Pilgrim 01": "Envoy", "Pilgrim 03 Song": "Bellbearer",
         "Song Reed": "Reed", "Song Handmaiden": "Clawmaiden", "Song Administrator": "Minister",
         "Song Pilgrim Maestro": "Maestro", "Song Heavy Sentry": "Clapper", TINY: "Tiny"}
FORECAST_TK = (0.0, 0.2, 0.4, 0.8)


def in_play_rows(cache: dict, i: int, starts, specs=FORUM_SPECS) -> list[int]:
    c = cache
    out = []
    for r in range(starts[i], starts[i + 1]):
        tk = c["types"][int(c["e_tk"][r])]
        if tk not in specs or not int(c["e_src"][r]) & 1 or c["e_hidden"][r]:
            continue
        hp = float(c["e_hp"][r])
        if not math.isnan(hp) and hp <= 0:
            continue
        st = int(c["e_st"][r])
        s = c["states"][st] if st >= 0 else None
        if s is None or s in WAITING_STATES or (tk == TINY and s == "Dead"):
            continue
        out.append(r)
    return out


class Concurrency:
    def __init__(self, specs=FORUM_SPECS):
        self.specs = specs
        self.count = Counter()
        self.w: dict[int, dict] = defaultdict(lambda: {"s": 0.0, "n": [], "combo": Counter(), "span": [], "both": 0,
                                                       "close": 0, "mix": Counter(), "near1": 0, "near2": 0,
                                                       "multi": 0, "frames": 0, "fights": set()})

    def frame(self, cache: dict, i: int, rows: list[int], tr: SubjectTracker, fight: str) -> None:
        c = cache
        wave = int(c["wave"][i]) if "wave" in c else -1
        n = len(rows)
        self.count[n] += 1
        if wave < 0 or wave >= 100:
            return
        w = self.w[wave]
        w["frames"] += 1
        w["fights"].add(fight)
        w["s"] += float(c["dt"][i])
        w["n"].append(n)
        hx, hy = float(c["hx"][i]), float(c["hy"][i])
        xs = [float(c["e_x"][r]) for r in rows]
        d = [math.hypot(float(c["e_x"][r]) - hx, float(c["e_y"][r]) - hy) for r in rows]
        w["near1"] += sum(x <= 6.0 for x in d) >= 1
        w["near2"] += sum(x <= 6.0 for x in d) >= 2
        w["combo"][" + ".join(sorted(SHORT.get(c["types"][int(c["e_tk"][r])], "?") for r in rows))] += 1
        if n < 2:
            return
        w["multi"] += 1
        w["span"].append(max(xs) - min(xs))
        w["both"] += any(-12.0 <= x - hx < 0 for x in xs) and any(0 <= x - hx <= 12.0 for x in xs)
        sx = sorted(xs)
        w["close"] += min(b - a for a, b in zip(sx, sx[1:])) < 3.0
        com = 0
        for r in rows:
            s = tr.subjects.get(int(c["e_iid"][r]))
            sp = self.specs[c["types"][int(c["e_tk"][r])]]
            com += s is not None and s.cur is not None and s.cur.family != sp.idle_family
        w["mix"]["all idle" if com == 0 else ("all committed" if com == n else "mixed")] += 1

    def result(self) -> dict:
        tot = sum(self.count.values()) or 1
        waves = {}
        for k in sorted(self.w):
            w = self.w[k]
            nf = max(1, len(w["fights"]))
            n = np.array(w["n"])
            m = max(1, w["multi"])
            top = w["combo"].most_common(2)
            waves[str(k)] = {
                "s_per_fight": round(w["s"] / nf, 1), "in_play_p50": float(np.percentile(n, 50)),
                "in_play_p95": float(np.percentile(n, 95)), "in_play_max": int(n.max()),
                "share_ge2": round(w["multi"] / max(1, w["frames"]), 3),
                "top_combos": {a: round(b / max(1, w["frames"]), 3) for a, b in top},
                "x_span_median_u": round(float(np.median(w["span"])), 1) if w["span"] else None,
                "both_sides_12u": round(w["both"] / m, 3), "nearest_two_lt_3u": round(w["close"] / m, 3),
                "all_idle_mixed_committed": [round(w["mix"][x] / m, 3) for x in ("all idle", "mixed",
                                                                                  "all committed")],
                "within_6u_ge1_ge2": [round(w["near1"] / max(1, w["frames"]), 3),
                                      round(w["near2"] / max(1, w["frames"]), 3)]}
        return {"frames": tot, "in_play_share": {str(k): round(v / tot, 4) for k, v in sorted(self.count.items())},
                "by_wave": waves}


class ForecastCheck:
    def __init__(self, extra: Path, fold: int):
        rows = read_contacts(extra / "contacts.jsonl.gz")
        m = margins_from_contacts(rows, fold=1 - fold)
        self.rec = SubjectRecall(FoldTables(extra, fold, margins=m))
        self.n: dict[int, Counter] = defaultdict(Counter)
        self.ms: list[float] = []
        self.npl: list[int] = []

    def frame(self, cache: dict, i: int, tr: SubjectTracker, T: float) -> None:
        wave = int(cache["wave"][i]) if "wave" in cache else -1
        t0 = time.perf_counter()
        pl = []
        for s in tr.subjects.values():
            if s.state is not None:
                pl += self.rec.placements_of(s, T, 0.8 + 1e-6, anchor_step=12)
        q = self.rec.t.query
        hx = float(0.5 * (cache["hbox"][i, 0] + cache["hbox"][i, 2]))
        hy = float(0.5 * (cache["hbox"][i, 1] + cache["hbox"][i, 3]))
        q.clear()
        for key, t_ref, anchor, mirror in pl:
            q.place(key, t_ref, anchor, mirror)
        tk = np.array(FORECAST_TK)
        hit = q.query(np.full((1, len(tk)), hx), np.full((1, len(tk)), hy), tk)[0] if pl else np.zeros(len(tk), bool)
        self.ms.append((time.perf_counter() - t0) * 1e3)
        self.npl.append(len(pl))
        c = self.n[wave]
        c["frames"] += 1
        for t, h in zip(FORECAST_TK, hit):
            c[f"inside at +{t:g} s"] += bool(h)

    def result(self) -> dict:
        ms = np.array(self.ms or [0.0])
        return {"ms_p50": round(float(np.percentile(ms, 50)), 3), "ms_p99": round(float(np.percentile(ms, 99)), 3),
                "placements_p50": int(np.percentile(self.npl or [0], 50)),
                "placements_p99": int(np.percentile(self.npl or [0], 99)),
                "by_wave": {str(k): {kk: round(vv / c["frames"], 3) if kk != "frames" else vv for kk, vv in c.items()}
                            for k, c in sorted(self.n.items())}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--fights", default="", help="comma-separated fight ids (default: every cache)")
    ap.add_argument("--run", default="", help="only fights of this run directory name")
    ap.add_argument("--first", type=int, default=0, help="only the first N fights (by episode)")
    ap.add_argument("--forecast", type=Path, default=None, help="the build's --extra directory: forecast check")
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.fights:
        paths = [a.cache / cache_name(x) for x in a.fights.split(",") if x]
    else:
        paths = sorted(a.cache.glob("*.npz"))
        if a.run:
            paths = [p for p in paths if p.name.startswith(a.run + "__")]
        paths.sort(key=lambda p: (p.name.split("__ep")[0], int(p.stem.rsplit("ep", 1)[1])))
    if a.first:
        paths = paths[:a.first]
    conc = Concurrency()
    fc = ForecastCheck(a.forecast, a.fold) if a.forecast else None
    t_all = time.perf_counter()
    for k, p in enumerate(paths):
        t0 = time.perf_counter()
        cache = load_cache(p)
        starts = np.searchsorted(cache["e_fi"], np.arange(len(cache["f"]) + 1))
        tr = SubjectTracker(FORUM_SPECS)
        for i, f, T in replay(cache, tr):
            conc.frame(cache, i, in_play_rows(cache, i, starts), tr, p.stem)
            if fc is not None and i % a.every == 0:
                fc.frame(cache, i, tr, T)
        print(f"[{k + 1}/{len(paths)}] {p.stem} ({time.perf_counter() - t0:.1f} s)", flush=True)
    out = {"fights": [p.stem for p in paths], "concurrency": conc.result()}
    if fc is not None:
        out["forecast"] = fc.result()
    print(json.dumps(out["concurrency"]["in_play_share"]))
    for w, r in out["concurrency"]["by_wave"].items():
        print(w, json.dumps(r))
    if fc is not None:
        print(json.dumps(out["forecast"]))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    print(f"{len(paths)} fights in {time.perf_counter() - t_all:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
