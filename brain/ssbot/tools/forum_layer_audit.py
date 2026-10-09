"""Wave-0 support layer audit (task "wave-0 de-saturation", forum.md §23): which layer of the Forum support makes the
candidate rows unsafe, and how much of it is the family margins, the idle growth and the +-1 bin export lag.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_layer_audit C:/ssbot/data/runs/m2/<run> [<run> ...]
        --out <dir> [--forced-rank seen_cf] [--react escape] [--episodes 0,3] [--every 6] [--workers 2]
        [--threads 4] [--limit 0]

Recorded Forum planner episodes are replayed open loop (as tools.forum_react_audit / forum_hit_forensics: the recorded
STATEs drive ForumPlannerPolicy, the prefix of each tick is the recorded ACTION masks, the supervisor never takes the
keys). On every `every`-th battle tick the planner's known, allowed rows (ForumPlanner.debug) are tested by their
nominal box centre on frames 1 .. T (invulnerable frames clear) against the tick's forecast split into groups
(layer, type, family):

  body          the idle body tube (its last box moved along its velocity, grown by the type's idle growth g)
  collider      the current-collider tube (first COLLIDER_TUBE_S only)
  com_fine      the current attack's states whose entry is known to <= FINE_MAX_BINS bins (fine placements)
  com_win       ... whose entry is an interval (window placements: the coarse 0.25 u time pyramid)
  com_fam       the current attack's family template from its start (the family-wide union, a window placement)
  com_bbox      the current attack's family walk at a re-anchor / unknown anchor (bounding boxes)
  tail          the tails of the current and ended attacks
  chain         a committed multi-hit family (MULTI_HIT), any placement kind
  start_attack  attack instances that may start later (bounding boxes at the dead-reckoned anchor grown by g)
  start_idle    later idle instances; idle_now: the current idle instance's states (no tube)
  entry         entry families (the current wave's entries and the next wave's)
  haz_self      thrown hazards by their self templates; haz_path: on deterministic paths; haz_tube: hazard tubes
  death         death tails; arena: arena-wide boxes

Per tick (<out>/<run>_i<inst>_ep<k>.json, existing files skipped): rows R, rows clear of the whole support (over the
horizon and over its first 18 frames), the rows the recorded future leaves clear (hindsight, open loop: forum.md
§19.1), and for every layer and every group: the share of live cells it covers, whether it alone covers every row,
the rows clear without it (leave one out) and of those how many the recorded future leaves clear. Variants (each a
forecast of the same tick on other tables / tubes): m0 / m05 (every family margin x 0 / x 0.5), g0 / g05 (the idle
growth x 0 / x 0.5); per variant the rows clear under it, and with one layer (or one family's groups) taken from it
and the rest as is; "nolag": the template layers queried at t - 1 bin, t and t + 1 bin and and-ed (an approximation
from inside of the +-1 bin baked into the templates). A greedy peel removes, step by step, the group that clears the
most rows.
"""
import argparse
import copy
import json
import math
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

NOT_STARTED = ("start_attack", "start_idle", "entry_later")
COMMITTED = ("com_fine", "com_win", "com_fam", "com_bbox", "tail", "chain_fine", "chain_win", "chain_bbox", "idle_now",
             "entry_now")
LAYERS = ("body", "collider") + COMMITTED + ("haz_self", "haz_path", "haz_tube", "death", "arena") + NOT_STARTED
TEMPLATE_LAYERS = frozenset(COMMITTED + NOT_STARTED + ("haz_self",))
# combinations at level 1 (the not-started layer gone): the layers each one leaves out
COMBOS = {"no_win": ("com_win", "com_fam", "chain_win"),
          "no_fam": ("com_fam",),
          "no_win_tail": ("com_win", "com_fam", "chain_win", "tail"),
          "no_win_bbox": ("com_win", "com_fam", "chain_win", "com_bbox", "chain_bbox"),
          "no_body": ("body", "collider"),
          "no_haz": ("haz_self", "haz_path", "haz_tube"),
          "body_haz_only": COMMITTED,
          "committed_only": ("body", "collider", "haz_self", "haz_path", "haz_tube", "death", "arena")}
VARIANTS = ("m0", "m05", "g0", "g05")
EARLY_F = 18
PEEL_STEPS = 8


def _key_name(store, tid: int) -> str:
    tid = int(tid)
    if tid >= 0:
        return store.keys[tid]
    return store._base_key.get(tid, "")


def classify(fcast) -> list[tuple[tuple, str, np.ndarray]]:
    """[(group key (layer, type, family), placement kind "pm" / "wm" / "bb", selection mask)] of a MultiForecast's
    placements."""
    from ssbot.combat.enemy_tables import TAIL
    from ssbot.combat.multi_forecast import ENTRY_OWNER, MULTI_HIT
    from ssbot.core.forum import FORUM_TYPES
    store = fcast.fc.tables.store
    tk_of = {s.iid: s.type_key for s in fcast.subjects}
    out = []
    for kind, meta, tids in (("pm", fcast.pm, fcast.P.tid), ("wm", fcast.wm, fcast.W.tid),
                             ("bb", fcast.bb, fcast.bb["tid"])):
        n = len(meta["owner"])
        if not n:
            continue
        g = defaultdict(list)
        for i in range(n):
            o, fam, com = int(meta["owner"][i]), str(meta["family"][i]), bool(meta["committed"][i])
            tk = tk_of.get(o)
            sp = FORUM_TYPES.get(tk) if tk else None
            key = _key_name(store, tids[i])
            parts = key.split("/")
            if fam.startswith("ent/"):
                lay, tk = "haz_self", fam[4:]
            elif o <= ENTRY_OWNER or (sp is not None and fam == sp.entry_family):
                lay = "entry_now" if com and o > ENTRY_OWNER and kind != "bb" else "entry_later"
            elif sp is not None and fam == sp.idle_family:
                lay = "idle_now" if kind != "bb" else "start_idle"
            elif com and (tk, fam) in MULTI_HIT:
                lay = {"pm": "chain_fine", "wm": "chain_win", "bb": "chain_bbox"}[kind]
            elif com and len(parts) >= 3 and parts[-2] == TAIL:
                lay = "tail"
            elif com:
                if kind == "pm":
                    lay = "com_fine"
                elif kind == "wm":
                    lay = "com_fam" if len(parts) == 3 else "com_win"
                else:
                    lay = "com_bbox"
            else:
                lay = "start_attack"
            g[(lay, str(tk or o), fam)].append(i)
        for k, idx in g.items():
            sel = np.zeros(n, bool)
            sel[idx] = True
            out.append((k, kind, sel))
    return out


BOX_LAYER = {"idle": "body", "collider": "collider", "hazard": "haz_tube", "death": "death", "arena": "arena"}


def group_occ(fcast, cx, cy, t, live, groups=None, placements_only: bool = False) -> dict:
    """{group key: [R, F] bool} of the support's groups at the rows' centres (live cells only); placements_only: the
    placements of `groups` alone (no tubes, death / arena boxes, hazard paths)."""
    occ: dict = {}

    def add(key, o):
        o = o & live
        if o.any():
            occ[key] = occ[key] | o if key in occ else o
    fn = {"pm": fcast._fine_occ, "wm": fcast._win_occ, "bb": fcast._bbox_occ}
    for key, kind, sel in (groups if groups is not None else classify(fcast)):
        add(key, fn[kind](cx, cy, t, sel))
    if placements_only:
        return occ
    tk_of = {s.iid: s.type_key for s in fcast.subjects}
    for o, kind in sorted({(int(b[0]), b[1]) for b in fcast.boxes}):
        tk = tk_of.get(o)
        if tk is None and kind == "hazard":
            h = fcast.fc.self_haz.get(o)
            tk = h[0] if h else None
        add((BOX_LAYER.get(kind, kind), str(tk or o), kind), fcast._box_occ(cx, cy, t, kinds=(kind,), only={o}))
    for p in fcast.paths:
        add(("haz_path", str(p.type_key), "path"), fcast._path_occ(cx, cy, t, only={int(p.iid)}))
    return occ


def _union(occs: dict, shape, skip=lambda k: False):
    u = np.zeros(shape, bool)
    for k, o in occs.items():
        if not skip(k):
            u |= o
    return u


def _clear(u: np.ndarray) -> tuple[int, int]:
    return int((~u.any(axis=1)).sum()), int((~u[:, :EARLY_F].any(axis=1)).sum())


def summarize(base: dict, var: dict, nolag: dict, shape, hind: np.ndarray | None, margins_fam: set) -> dict:
    """The tick's numbers (see the module docstring); hind [R] bool: the recorded future leaves the row clear.
    Level 0: the whole support; level 1: without the not-started layer (NOT_STARTED: the reactive support's ideal,
    those attacks left to the escape check); the leave-one-out, variants and the peel are taken at level 1."""
    R = shape[0]
    tot = max(int(shape[0] * shape[1]), 1)

    def cl(u) -> list:
        c = ~u.any(axis=1)
        r = [int(c.sum()), int((~u[:, :EARLY_F].any(axis=1)).sum())]
        if hind is not None:
            r.append(int((c & hind).sum()))
        return r
    ns = lambda k: k[0] in NOT_STARTED                                  # noqa: E731
    b1 = {k: o for k, o in base.items() if not ns(k)}
    out = {"R": R, "clear0": cl(_union(base, shape)), "clear1": cl(_union(b1, shape))}
    if hind is not None:
        out["hind"] = int(hind.sum())
    lay = {}
    for L in LAYERS:
        ks = [k for k in base if k[0] == L]
        if not ks:
            continue
        o = _union({k: base[k] for k in ks}, shape)
        lay[L] = {"share": round(float(o.sum() / tot), 4), "alone": bool(o.any(axis=1).all()),
                  "loo1": None if L in NOT_STARTED else cl(_union(b1, shape, lambda k, L=L: k[0] == L))}
    out["layers"] = lay
    out["groups"] = [[list(k), round(float(o.sum() / tot), 4), bool(o.any(axis=1).all()),
                      cl(_union(b1, shape, lambda kk, k=k: kk == k))] for k, o in b1.items()]
    out["combos"] = {c: cl(_union(b1, shape, lambda k, drop=drop: k[0] in drop)) for c, drop in COMBOS.items()}
    vv = {}
    for v, occ in var.items():
        if occ is None:
            continue
        o1 = {k: x for k, x in occ.items() if not ns(k)}
        d = {"all": cl(_union(o1, shape)), "all0": cl(_union(occ, shape))}
        for L in lay:
            if L in NOT_STARTED:
                continue
            d[L] = cl(_union(b1, shape, lambda k, L=L: k[0] == L) | _union(o1, shape, lambda k, L=L: k[0] != L))
        for c, drop in COMBOS.items():
            d["combo:" + c] = cl(_union(o1, shape, lambda k, drop=drop: k[0] in drop))
        if v == "m0":
            fam = {}
            for (L, tk, f) in b1:
                if not ((tk, f) in margins_fam or (L == "haz_self" and ("ent", tk) in margins_fam)):
                    continue
                key = f"{tk}/{f}"
                if key in fam:
                    continue

                def is_f(k, tk=tk, f=f):
                    return k[1] == tk and k[2] == f
                fam[key] = cl(_union(b1, shape, is_f) | _union(o1, shape, lambda k, is_f=is_f: not is_f(k)))
            d["fam"] = fam
        vv[v] = d
    if nolag:
        nl = {k: nolag.get(k, o) for k, o in b1.items()}
        d = {"all": cl(_union(nl, shape))}
        for L in lay:
            if L in TEMPLATE_LAYERS and L not in NOT_STARTED:
                d[L] = cl(_union(b1, shape, lambda k, L=L: k[0] == L) | _union(
                    {k: nl[k] for k in b1 if k[0] == L}, shape))
        for c, drop in COMBOS.items():
            d["combo:" + c] = cl(_union(nl, shape, lambda k, drop=drop: k[0] in drop))
        vv["nolag"] = d
    out["var"] = vv
    # greedy peel at level 1
    rest = dict(b1)
    steps = []
    for _ in range(PEEL_STEPS):
        if not rest:
            break
        best, bc = None, -1
        for k in rest:
            c = int((~_union(rest, shape, lambda kk, k=k: kk == k).any(axis=1)).sum())
            if c > bc:
                best, bc = k, c
        steps.append([list(best), bc])
        rest.pop(best)
        if bc >= R:
            break
    out["peel"] = steps
    return out


class Variants:
    """Alternative tables / tubes for the same trackers: m0 / m05 (margins x 0 / x 0.5), g0 / g05 (the idle growth
    x 0 / x 0.5); rb / rbr: the reactive support with "+b" / "+br" (multi_forecast.ReactConfig.bodyreach: the body-
    only families not started out; needs a "+n" support). swap(name) puts them on the forecaster (tables, family
    walk ids, reactive support), restore() puts the production ones back."""

    def __init__(self, fc, names=VARIANTS):
        import dataclasses
        from ssbot.combat.enemy_tables import FORUM_DIR, EnemyTables, Tubes
        self.fc = fc
        self.base = (fc.tables, fc._fwalk)
        self.react0 = fc.react
        self.react = {}
        self.sets = {}
        md = json.loads((FORUM_DIR / "support_margins.json").read_text("utf-8"))
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="layer_audit_"))
        for v in names:
            if v in ("rb", "rbr"):
                if fc.react is None or not fc.react.notstarted:
                    raise ValueError(f"variant {v}: the support has no +n")
                self.react[v] = dataclasses.replace(fc.react, bodyreach=True, bodyreach_all=v == "rbr")
                self.sets[v] = self.base
                continue
            if v.startswith("m"):
                s = 0.0 if v == "m0" else 0.5
                d = copy.deepcopy(md)
                d["by_family"] = {k: float(x) * s for k, x in (md.get("by_family") or {}).items()}
                p = tmp / f"margins_{v}.json"
                p.write_text(json.dumps(d), "utf-8")
                tb = EnemyTables.production(margins_path=p)
                self.sets[v] = (tb, {})
                keep = (fc.tables, fc._fwalk)
                fc.tables, fc._fwalk = self.sets[v]
                fc.warm()
                fc.tables, fc._fwalk = keep
            else:
                s = 0.0 if v == "g0" else 0.5
                tb = copy.copy(fc.tables)
                pt = md.get("production_tubes") or {}
                tub = Tubes.from_doc(pt)
                tub.growth = {k: [x * s for x in g] for k, g in tub.growth.items()}
                # past the calibrated bins the growth goes on at the top speed: scaled as well
                tub.speed = {k: x * s for k, x in tub.speed.items()}
                tb.tubes = tub
                self.sets[v] = (tb, fc._fwalk)
        self.fam_margins: set = set()

    def swap(self, v: str) -> None:
        self.fc.tables, self.fc._fwalk = self.sets[v]
        self.fc.react = self.react.get(v, self.react0)

    def restore(self) -> None:
        self.fc.tables, self.fc._fwalk = self.base
        self.fc.react = self.react0


def run_episode(job: dict) -> dict:
    from ssbot.knowledge.kinematics import F_INVULN
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.forum_hit_forensics import FramePolys, _mask_of, first_contact
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.planner_policy import HORIZON_S
    pol, vs = _POL["pol"], _POL["vs"]
    row = job["row"]
    t_job = time.perf_counter()
    rd = RecordingReader(row["recording"])
    for _, m in rd.terrain():
        if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
            pol.terrain_msg = m
    states = list(rd.states(row["f_wake"], row["f_end"]))
    fp = FramePolys(states)
    pol.reset(random.Random(0), ENCOUNTERS[row["unit"]])
    pol.planner.debug = True
    pol.planner.fcfg.deadline_ms = math.inf
    pol.planner.fcfg.esc_deadline_ms = math.inf
    pol.planner.fcfg.forced_rank = job["forced_rank"]
    pol.planner.fcfg.react = job["react"]
    pol._set_react(pol.planner.fcfg)
    f_first = int(states[0]["f"])
    ticks = []
    margins_fam = set(vs.fam_margins)
    for i, s in enumerate(states):
        nxt = states[i + 1] if i + 1 < len(states) else None
        if nxt is not None:
            pol.sent[int(nxt["f"])] = _mask_of(nxt)
        pol.act(s, None)
        fo = int(s["f"])
        if (fo - f_first) % job["every"]:
            continue
        li = pol.planner.last_info
        dbg = li.get("dbg") if li else None
        res = pol.planner_last
        if dbg is None or res is None or not pol.forecasts or pol.forecasts[-1][0] != fo:
            continue
        rows = np.flatnonzero(dbg["ok"] & dbg["known"])
        if not len(rows):
            continue
        box, flags = dbg["box"], dbg["flags"]
        inv = (flags & F_INVULN) != 0
        T1 = box.shape[1]
        fr = np.arange(1, T1)
        br = box[rows][:, fr]
        cx, cy = 0.5 * (br[..., 0] + br[..., 2]), 0.5 * (br[..., 1] + br[..., 3])
        t = dbg["tk"][fr]
        live = ~inv[rows][:, fr]
        fcast = pol.forecasts[-1][1]
        fb, m = fp.window(fo, T1)
        first = first_contact(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(inv), fp.verts,
                              fp.starts, fb, m, 0.0)
        hind = first[rows] < 0
        t0 = time.perf_counter()
        groups = classify(fcast)
        base = group_occ(fcast, cx, cy, t, live, groups)
        nolag = {}
        bin_s = float(t[1] - t[0]) if len(t) > 1 else 1.0 / 60.0
        tmpl = [g for g in groups if g[0][0] in TEMPLATE_LAYERS and g[0][0] not in NOT_STARTED]
        if tmpl:
            a = group_occ(fcast, cx, cy, t - bin_s, np.ones_like(live), tmpl, placements_only=True)
            b = group_occ(fcast, cx, cy, t + bin_s, np.ones_like(live), tmpl, placements_only=True)
            for k in {g[0] for g in tmpl}:
                if k in base:
                    nolag[k] = base[k] & a.get(k, np.zeros_like(live)) & b.get(k, np.zeros_like(live))
        var = {}
        try:
            for v in vs.sets:
                vs.swap(v)
                f2 = pol.fc.forecast(HORIZON_S, origin_t=fcast.origin_t)
                var[v] = group_occ(f2, cx, cy, t, live)
        finally:
            vs.restore()
        ms = (time.perf_counter() - t0) * 1e3
        rec = {"f": fo, "rel": fo - f_first, "forced": bool(res.forced_risk), "n_safe": int(res.n_safe),
               "pick": res.name, "hero": (s.get("hero") or {}).get("pos"), "ms": round(ms, 1),
               "subj": [[sj.type_key, sj.state, sj.family, sj.committed] for sj in fcast.subjects if sj.alive],
               **summarize(base, var, nolag, live.shape, hind, margins_fam)}
        ticks.append(rec)
    return {"run": job["run"], "inst": row["_inst"], "ep": row["episode"], "seed": row.get("seed"),
            "outcome": row.get("outcome"), "n_states": len(states), "ticks": ticks,
            "secs": round(time.perf_counter() - t_job, 1)}


_POL: dict = {}


def _init(threads: int, crest: str, variants: tuple) -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    import dataclasses
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    pol = ForumPlannerPolicy(threads=threads, crest=crest)
    pol.warmup()
    step0 = pol.sc.step

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else \
            dataclasses.replace(r, mask=None, outcome=None)
    pol.sc.step = step
    vs = Variants(pol.fc, variants)
    vs.fam_margins = {k for k, v in pol.fc.tables.margins.items() if v > 0}
    _POL["pol"], _POL["vs"] = pol, vs


def _job_safe(job: dict) -> dict:
    try:
        return run_episode(job)
    except Exception:
        import traceback
        return {"run": job["run"], "inst": job["row"]["_inst"], "ep": job["row"]["episode"],
                "error": traceback.format_exc()[-3000:]}


def jobs_of(run: Path, a) -> list[dict]:
    out = []
    for p in sorted(run.glob("attempts_i*.jsonl")):
        inst = int(p.stem.split("_i")[1])
        for x in p.read_text("utf-8").splitlines():
            if not x.strip():
                continue
            r = json.loads(x)
            if r.get("outcome") == "HARNESS_FAIL" or not r.get("recording"):
                continue
            if a.episodes and r["episode"] not in a.episodes:
                continue
            r["_inst"] = inst
            r.pop("acts", None)
            out.append({"run": run.name, "row": r, "every": a.every, "forced_rank": a.forced_rank,
                        "react": a.react})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--forced-rank", default="seen_cf", choices=("share", "seen", "seen_cf"))
    ap.add_argument("--react", default="escape")
    ap.add_argument("--episodes", type=lambda s: [int(x) for x in s.split(",") if x], default=None)
    ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="at most this many episodes per run (0: all)")
    ap.add_argument("--variants", type=lambda s: tuple(x for x in s.split(",") if x), default=VARIANTS)
    ap.add_argument("--crest", default=None)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for r in a.runs:
        js = [j for j in jobs_of(r, a)
              if not (a.out / f"{j['run']}_i{j['row']['_inst']}_ep{j['row']['episode']}.json").exists()]
        jobs += js[:a.limit] if a.limit else js
    print(f"{len(jobs)} episodes", flush=True)
    t0 = time.perf_counter()

    def write(res):
        p = a.out / f"{res['run']}_i{res['inst']}_ep{res['ep']}.json"
        p.write_text(json.dumps(res, default=str), "utf-8")
        print(f"{p.name} {'ERROR' if 'error' in res else ''} {res.get('secs')} s ({time.perf_counter() - t0:.0f} s)",
              flush=True)
    crest = a.crest
    if crest is None and jobs:
        from ssbot.train.encounters import ENCOUNTERS
        crest = "Wanderer" if ENCOUNTERS[jobs[0]["row"]["unit"]].savestate == "fo_W" else "Reaper"
    crest = crest or "Reaper"
    if a.workers <= 1:
        _init(a.threads, crest, a.variants)
        for j in jobs:
            write(_job_safe(j))
    else:
        with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.threads, crest, a.variants)) as ex:
            for res in ex.map(_job_safe, jobs):
                write(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
