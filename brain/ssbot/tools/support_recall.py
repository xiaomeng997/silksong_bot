"""Support recall of the threat forecast on logged fights (M2 W3 stage A): every contact frame must lie inside the
support forecast made L frames earlier.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.support_recall C:/ssbot/data/runs/m2/<run> [--recordings i2_002,i3_002]
        [--lags 2,3,4] [--view oracle|ve] [--table DIR] [--margin 0] [--max-fights N] [--json out.json]

Contacts are what the behaviour builder validates its templates against (ssbot.knowledge.behaviour_tables): every
"damage" frame and every frame of a "damage_blocked" stretch (first_f..last_f, the hero touched while in i-frames).
The pairing is the planner's: the contact at frame c counts as covered when the hero box of c at t_c or the box of
c - 1 at t_(c-1) is inside the forecast's support, the forecast being made from the WorldState of frame c - L
(origin t_(c-L), nothing later used). The query is the planner's own: SupportQuery on the support templates dilated
by the hero hurtbox (plus --margin), the box centre tested.

Views: "oracle" feeds OracleBackend; "ve" adds the ObservabilityFilter (the vision-equivalent view; no noise and no
delay here: the lag L stands for the delay), "ve_dust" with the dust cues (planner_policy.DUST_TELL). Two passes per
recording: the events alone give the contact frames, then
the backend, filter and tracker run over every frame and forecast only at the frames some contact needs.
--table points the forecaster at another behaviour build (a held-out build: C:/ssbot/data/m2_heldout/tables holds
one without i2_002 / i3_002 and the trial run).
Forum (round R0, the certification before any Forum evaluation; ssbot.knowledge.forum_support):
    ../scripts/uv.cmd run python -m ssbot.tools.support_recall --encounter Forum
        --extra C:/ssbot/data/m2_forum_r0/build_all/extra --cache C:/ssbot/data/m2_forum_r0/cache
        [--margins heldout|none] [--margin-q 1.0] [--split 3way|2way] [--no-idle-tube] [--family-wide] [--area]
        [--fresh DIR --fresh-cache DIR] [--write-margins margins.json [--dev-json dev.json]] [--json out.json]
each fold's fights against the tables built from the other fold alone (behaviour_build --extra), every contact
against the forecast of the enemy it came from, plus per-family margins calibrated on fights that are neither the
tables' nor the certified ones (forum_main); --fresh certifies fights the build never saw (the certification proper:
the configuration frozen before it runs).
--noise-seed N (vision views, task V): SimpleNoise after the filter (position noise, missed detections that coast),
as on the simulated final path: what the vision view's drop-bell paths are estimated from (combat.bell_track). The
hero's box stays the recorded one (the planner's margin covers the hero's own position noise).
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def fights_of(run: Path, recordings: set[str] | None) -> list[dict]:
    rows = []
    for p in sorted(run.glob("attempts_i*.jsonl")):
        for line in p.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            a = json.loads(line)
            if a.get("f_wake") is None or a.get("f_end") is None or not a.get("recording"):
                continue
            rec = Path(a["recording"])
            if not rec.is_dir():
                found = list(run.glob(f"rec/*/*/{rec.name}"))
                rec = found[0] if found else rec
            if recordings and rec.name not in recordings:
                continue
            rows.append({"rec": rec, "f0": int(a["f_wake"]), "f1": int(a["f_end"]),
                         "id": f"{run.name}/i{a.get('instance')}/ep{a.get('episode')}"})
    return rows


def contacts_of(reader, f0: int, f1: int) -> dict[int, str]:
    """Contact frames in [f0, f1] -> source (damage frames and blocked stretches)."""
    out: dict[int, str] = {}
    for s in reader.states(f0, f1 + 600, keys=("f", "ev")):
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "damage" and f0 <= s["f"] <= f1:
                out[s["f"]] = str(d.get("source"))
            elif k == "damage_blocked" and isinstance(d.get("first_f"), int) and isinstance(d.get("last_f"), int):
                for c in range(max(f0, d["first_f"]), min(f1, d["last_f"]) + 1):
                    out.setdefault(c, str(d.get("source")))
    return out


def run_fight(fight: dict, fc, view: str, lags: list[int], stats: dict, misses: list, bosses,
              noise_seed: int | None = None) -> None:
    from ssbot.backends.observability import ObservabilityFilter
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.core.worldstate import VISION_EQUIVALENT
    from ssbot.record.recorder import RecordingReader

    r = RecordingReader(fight["rec"])
    f0, f1 = fight["f0"], fight["f1"]
    contacts = contacts_of(r, f0, f1)
    if not contacts:
        return
    need: dict[int, list[int]] = defaultdict(list)          # origin frame -> contact frames
    for c in contacts:
        for L in lags:
            need[c - L].append(c)
    backend = OracleBackend(bosses=bosses)
    filt = None
    noise = None
    if view in ("ve", "ve_dust"):
        from ssbot.train.planner_policy import DUST_TELL, TELL_ONSET
        filt = ObservabilityFilter(bosses=bosses, tells=DUST_TELL if view == "ve_dust" else None,
                                   tell_onset=TELL_ONSET)
        filt.reset(noise_seed if noise_seed is not None else 0)       # the cue onsets' draws
        if noise_seed is not None:
            from ssbot.backends.noise_simple import SimpleNoise
            noise = SimpleNoise(seed=noise_seed)
    fc.reset()
    t_of: dict[int, float] = {}
    box_of: dict[int, tuple] = {}
    forecasts: dict[int, object] = {}
    state_of: dict[int, str] = {}
    start = f0 - 300                     # the wake chain needs the Control events before the wake frame
    for s in r.states(start, f1):
        f = s["f"]
        ws = backend.feed(s)
        if filt is not None:
            ws = filt.apply(ws)
        if noise is not None:
            ws = noise.apply(ws)
        if f == f0 and view != "oracle":
            fc.notify_wake(ws.stamp.t_game_s)
        fc.update(ws)
        t_of[f] = ws.stamp.t_game_s
        b = (s.get("hero") or {}).get("box")
        box_of[f] = tuple(b[:4]) if b else None
        if f in need:
            forecasts[f] = fc.forecast(1.0)
            state_of[f] = str(fc.tracker.state)
    for c, src in sorted(contacts.items()):
        for L in lags:
            o = c - L
            fcast = forecasts.get(o)
            key = (view, L)
            stats[key]["n"] += 1
            if fcast is None or o not in t_of:
                stats[key]["no_origin"] += 1
                continue
            ok = False
            for fr in (c, c - 1):
                bx = box_of.get(fr)
                if bx is None or fr not in t_of:
                    continue
                x, y = 0.5 * (bx[0] + bx[2]), 0.5 * (bx[1] + bx[3])
                hit = fcast.occupied(np.array([[x]]), np.array([[y]]), np.array([t_of[fr] - t_of[o]]))
                if hit[0, 0]:
                    ok = True
                    break
            if ok:
                stats[key]["covered"] += 1
            else:
                bx = box_of.get(c)
                misses.append({"fight": fight["id"], "frame": c, "lag": L, "view": view, "source": src,
                               "state": state_of.get(o), "known": fcast.known, "roots": [
                                   (rt.state, round(rt.e_lo, 3), rt.ctx.family,
                                    None if rt.ctx.anchor is None else (rt.ctx.anchor.x, rt.ctx.anchor.mirror))
                                   for rt in fcast.roots],
                               "hero": None if bx is None else [round(v, 3) for v in bx],
                               "n_place": len(fcast.placements)})


ARENA_BAND = (14.01, 3.0, 48.99, 18.0)    # the Forum's band the hero moves in (x between the walls, floor to the
#                                          highest platforms; docs/facts/1.0.30000/forum.md §8): the absolute measure


def band_cover(t, cx: float, cy: float, band=ARENA_BAND) -> np.ndarray:
    """Per bin of template t anchored at (cx, cy) (mirror 1), the share of the band's cells it occupies."""
    c = t.cell
    xs = (t.ix0 + np.arange(t.nx) + 0.5) * c + cx
    ys = (t.iy0 + np.arange(t.ny) + 0.5) * c + cy
    mx = np.flatnonzero((xs >= band[0]) & (xs <= band[2]))
    my = np.flatnonzero((ys >= band[1]) & (ys <= band[3]))
    total = ((band[2] - band[0]) / c) * ((band[3] - band[1]) / c)
    out = np.zeros(t.nt)
    if not len(mx) or not len(my):
        return out
    for b in range(t.nt):
        p = t.plane(b)
        out[b] = p[my[0]:my[-1] + 1, mx[0]:mx[-1] + 1].sum() / total
    return out


def support_area(extra: Path, margins: dict, specs, base: float = 0.0, idle: dict | None = None) -> dict:
    """The margins' cost per (type, family) over the per-state anchor support templates, and per thrown hazard
    ("ent/<hazard>") over its self template, of the build's two folds (each fold's mean, their union not formed):
      area_u2 / area_with_margin_u2 / ratio   mean occupied area per occupied time bin without and with the margin
                                              (the hero hurtbox left out of both)
      band_cover / band_cover_with_margin     the absolute measure (a ratio near 1 can hide a template that already
                                              covers the arena): anchored at the centre of the Forum band ARENA_BAND
                                              with the hero half-extents (+ base + margin), the share of the band its
                                              bins occupy: the median over the family's templates of each one's median
                                              occupied bin ("median") and the largest bin of any ("max")
    idle: type -> {"growth_l4": g at 4 frames, "hull": body hull}: the idle families under the idle body tube get the
    tube's area and band share at L4 (the body hull grown by the hero half-extents and g) in "idle_body_tube"."""
    from ssbot.knowledge import hitbox_tables as hb
    hx, hy = hb.HERO_HALF_U
    cx, cy = 0.5 * (ARENA_BAND[0] + ARENA_BAND[2]), 0.5 * (ARENA_BAND[1] + ARENA_BAND[3])
    band_area = (ARENA_BAND[2] - ARENA_BAND[0]) * (ARENA_BAND[3] - ARENA_BAND[1])
    out: dict = {}
    for tk, sp in specs.items():
        acc: dict = defaultdict(lambda: {"a0": 0.0, "a1": 0.0, "n": 0, "c0": [], "c1": [], "c0max": 0.0,
                                         "c1max": 0.0, "margin": 0.0})
        for k in range(2):
            npz = extra / f"{sp.enemy}_support_fold{k}.npz"
            if not npz.exists():
                continue
            raw, _ = hb.load_templates(npz, prefix=hb.SUPPORT)
            for key, t in raw.items():
                parts = key.split("/")
                if len(parts) != 4:
                    continue
                if parts[1] == "ent" and parts[3] == "self":
                    name, m = f"ent/{parts[2]}", margins.get(("ent", parts[2]), 0.0)
                elif parts[3] == "anchor":
                    name, m = f"{tk}/{parts[1]}", margins.get((tk, parts[1]), 0.0)
                else:
                    continue
                a0 = np.unpackbits(t.bits, axis=2).reshape(t.nt, -1).sum(axis=1)
                occ = a0 > 0
                if not occ.any():
                    continue
                d = t.dilated(rx=m, ry=m) if m > 0 else t
                a1 = np.unpackbits(d.bits, axis=2).reshape(d.nt, -1).sum(axis=1)
                h0 = t.dilated(rx=hx + base, ry=hy + base)
                h1 = t.dilated(rx=hx + base + m, ry=hy + base + m)
                c0, c1 = band_cover(h0, cx, cy), band_cover(h1, cx, cy)
                r = acc[name]
                r["a0"] += float(a0[occ].mean()) * t.cell ** 2
                r["a1"] += float(a1[a1 > 0].mean()) * t.cell ** 2
                r["n"] += 1
                r["margin"] = m
                r["c0"].append(float(np.median(c0[c0 > 0])) if (c0 > 0).any() else 0.0)
                r["c1"].append(float(np.median(c1[c1 > 0])) if (c1 > 0).any() else 0.0)
                r["c0max"], r["c1max"] = max(r["c0max"], float(c0.max())), max(r["c1max"], float(c1.max()))
        for name, r in acc.items():
            n = r["n"]
            row = {"margin_u": round(r["margin"], 3), "templates": n, "area_u2": round(r["a0"] / n, 2),
                   "area_with_margin_u2": round(r["a1"] / n, 2), "ratio": round(r["a1"] / r["a0"], 3) if r["a0"] else None,
                   "band_cover": {"median": round(float(np.median(r["c0"])), 4), "max": round(r["c0max"], 4)},
                   "band_cover_with_margin": {"median": round(float(np.median(r["c1"])), 4),
                                              "max": round(r["c1max"], 4)}}
            fam = name.split("/", 1)[1]
            if idle and fam == sp.idle_family and tk in idle:
                g, h = idle[tk]["growth_l4"], idle[tk]["hull"]
                w, ht = h[2] - h[0] + 2 * (hx + base + g), h[3] - h[1] + 2 * (hy + base + g)
                row["idle_body_tube"] = {"growth_l4_u": round(g, 3), "box_u": [round(w, 2), round(ht, 2)],
                                         "band_cover": round(min(1.0, w * ht / band_area), 4),
                                         "note": "replaces the current idle instance's templates (they are placed "
                                                 "only for an idle entered within the horizon, from a fresh anchor)"}
            out[name] = row
    return out


def tube_params(a: argparse.Namespace, ids: list[str], cache_dir: Path, label: str) -> dict:
    """The tubes' calibration from the given (training) fights' caches: the current-collider tube's per-type top
    speed and the body hulls from every 4th fight (as the certification of 2026-10-04 05:41 had them), the idle body
    tube's growth from all of them (forum_support.IdleTubeCalibration, quantile --idle-q)."""
    from ssbot.knowledge.forum_cache import cache_name, load_cache
    from ssbot.knowledge.forum_support import IdleTubeCalibration, body_hulls, top_speeds
    t0 = time.perf_counter()
    paths = [cache_dir / cache_name(fid) for fid in ids]
    paths = [p for p in paths if p.exists()]
    sub = [load_cache(p) for p in paths[::4]]
    speeds, hulls = top_speeds(sub), body_hulls(sub)
    del sub
    growth, samples = None, None
    if a.idle_tube:
        cal = IdleTubeCalibration(hulls)
        for p in paths:
            cal.add(load_cache(p))
        growth, samples = cal.growth(a.idle_q), cal.samples()
    print(f"  tube calibration on {label} ({len(paths)} fights, {time.perf_counter() - t0:.0f} s): top speeds "
          + ", ".join(f"{tk} {v:.1f}" for tk, v in sorted(speeds.items()))
          + ("" if growth is None else "; idle growth at 4 frames "
             + ", ".join(f"{tk} {g[4]:.2f}" for tk, g in sorted(growth.items()))), flush=True)
    return {"speeds": speeds, "hulls": hulls, "growth": growth, "samples": samples, "fights": len(paths)}


def run_group(a: argparse.Namespace, tables, params: dict, lags: list[int], ids: list[str], by_fight: dict,
              cache_dir: Path, label: str):
    from ssbot.knowledge.forum_cache import cache_name, load_cache
    from ssbot.knowledge.forum_support import SubjectRecall
    rec = SubjectRecall(tables, lags, tube_speed=params["speeds"] if a.tube else None,
                        idle_growth=params["growth"] if a.idle_tube else None)
    rec.body_rel = params["hulls"]
    done = 0
    for i, fid in enumerate(ids):
        path = cache_dir / cache_name(fid)
        if not path.exists():
            print(f"  no cache for {fid}", flush=True)
            continue
        t1 = time.perf_counter()
        rec.run(load_cache(path), by_fight.get(fid, []), label=label)
        done += 1
        n = sum(v["n"] for (tk, L), v in rec.stats.items() if L)
        c = sum(v["covered"] for (tk, L), v in rec.stats.items() if L)
        print(f"  [{i + 1}/{len(ids)}] {fid} {time.perf_counter() - t1:.1f} s  covered {c}/{n}", flush=True)
    return rec, done


def summarise(stats: dict, misses: list, lags: list[int]) -> dict:
    by = {}
    for (tk, L), v in sorted(stats.items()):
        if not L:
            by[f"{tk}"] = dict(v)
            continue
        by[f"{tk}/L{L}"] = {"n": v["n"], "covered": v["covered"], "outside_attacks": v["outside_attacks"],
                            "recall": round(v["covered"] / v["n"], 6) if v["n"] else None,
                            **{x: v[x] for x in sorted(v) if x.startswith(("covered by", "forecast:"))}}
    tot = {L: [sum(v["n"] for (tk, l2), v in stats.items() if l2 == L),
               sum(v["covered"] for (tk, l2), v in stats.items() if l2 == L)] for L in lags}
    how: Counter = Counter()
    model: Counter = Counter()
    for (tk, L), v in stats.items():
        for x in v:
            if x.startswith("covered by"):
                how[f"L{L} {x}"] += v[x]
            elif x.startswith("forecast:"):
                model[f"L{L} {x}"] += v[x]
    return {"recall": {f"L{L}": {"n": n, "covered": c, "recall": round(c / n, 6) if n else None}
                       for L, (n, c) in tot.items()},
            "covered_other_than_by_the_forecast": dict(sorted(how.items())),
            "forecast_parts_counted_apart": dict(sorted(model.items())),
            "by_type": by, "n_misses": len(misses),
            "miss_by": dict(Counter(f"{m['type']}/{m['family']}/{m['state']}/L{m['lag']}" for m in misses)
                            .most_common(60)),
            "misses": misses[:400]}


def forum_main(a: argparse.Namespace) -> int:
    """--encounter Forum: held-out recall of the gauntlet tables (ssbot.knowledge.forum_support), each enemy's
    contacts against its own forecast.

    --split 3way (the default): fold k's fights against the tables of the other fold; fold k's fights are split in two
    halves (alternating) and each half is certified with the margins calibrated on the other half's contacts (their
    held-out residuals are against the tables' fold): tables, margins and the certified contacts come from three
    disjoint sets of fights. --split 2way: the margins of fold k's certification from the training fold's contacts,
    whose residuals are against fold k's own occupancy (the leaky calibration of the first R0 run; for comparison).
    --fresh DIR: the certification on fights the build never saw (behaviour_build --contacts-only), against each
    fold's tables with the production margins (every build contact's held-out residual) and tubes calibrated on all
    the build's fights."""
    from ssbot.knowledge.forum_support import FoldTables, fight_of, margins_from_contacts, read_contacts
    from ssbot.knowledge.gauntlet_tables import FORUM_SPECS

    extra = a.extra
    rows = read_contacts(extra / "contacts.jsonl.gz")
    build = json.loads((extra / "build.json").read_text("utf-8"))
    folds = {f["id"]: f["fold"] for f in build["fights"]}
    skip = {sp.idle_family for sp in FORUM_SPECS.values()} if a.idle_tube else set()
    lags = [int(x) for x in a.lags.split(",")]
    out: dict = {"encounter": "Forum", "extra": str(extra), "lags": lags, "base_margin": a.margin,
                 "margins": a.margins, "margin_q": a.margin_q, "family_wide": a.family_wide, "tube": a.tube,
                 "idle_tube": a.idle_tube, "idle_q": a.idle_q, "split": "fresh" if a.fresh else a.split,
                 "groups": []}
    from ssbot.record.recorder import find_repo_root, git_info
    out["code"] = git_info(find_repo_root())
    stats: dict = defaultdict(Counter)
    misses: list = []
    fights_done = 0
    if a.fresh is not None:
        frows = read_contacts(a.fresh / "contacts.jsonl.gz")
        fbuild = json.loads((a.fresh / "build.json").read_text("utf-8"))
        fids = [f["id"] for f in fbuild["fights"]]
        if a.max_fights:
            fids = fids[:a.max_fights]
        seen = set(folds) & set(fids)
        if seen:
            raise SystemExit(f"--fresh fights are in the build: {sorted(seen)[:5]}")
        by_fight: dict[str, list] = defaultdict(list)
        for r in frows:
            by_fight[fight_of(r)].append(r)
        m = margins_from_contacts(rows, fold=None, q=a.margin_q, skip_families=skip) if a.margins == "heldout" \
            else {}
        params = tube_params(a, list(folds), a.cache, "all the build's fights")
        out["fresh"] = {"dir": str(a.fresh), "fights": len(fids), "build_code": fbuild.get("code")}
        out["production"] = {"margins": {f"{tk}/{fam}": round(v, 4) for (tk, fam), v in sorted(m.items())},
                             "tube_speed": {tk: round(v, 2) for tk, v in params["speeds"].items()},
                             "body_hull": {tk: [round(v, 3) for v in h] for tk, h in params["hulls"].items()},
                             "idle_growth": params["growth"], "idle_samples": params["samples"]}
        per_table: dict = {}
        for j in (0, 1):
            t0 = time.perf_counter()
            tables = FoldTables(extra, j, margins=m, base=a.margin, specs=FORUM_SPECS, family_wide=a.family_wide)
            print(f"fresh fights against the tables of fold {j}, {len(tables.templates)} templates "
                  f"({time.perf_counter() - t0:.0f} s)", flush=True)
            rec, done = run_group(a, tables, params, lags, fids, by_fight, a.fresh_cache, f"fresh/tables{j}")
            fights_done += done
            per_table[str(j)] = summarise(rec.stats, rec.misses, lags)
            per_table[str(j)]["placements"] = dict(rec.placements)
            for key, v in rec.stats.items():
                stats[key].update(v)
            misses += rec.misses
        out["by_tables"] = per_table
    else:
        by_fight = defaultdict(list)
        for r in rows:
            by_fight[fight_of(r)].append(r)
        out["margins_by_group"] = {}
        out["tube_by_fold"] = {}
        for k in (0, 1):
            train = k if a.in_sample else 1 - k
            ids_all = [fid for fid, fd in folds.items() if fd == k]
            ids = ids_all[:a.max_fights] if a.max_fights else ids_all
            params = tube_params(a, [fid for fid, fd in folds.items() if fd == train], a.cache, f"fold {train}")
            out["tube_by_fold"][str(k)] = {"train_fold": train,
                                           "tube_speed": {tk: round(v, 2) for tk, v in params["speeds"].items()},
                                           "body_hull": {tk: [round(v, 3) for v in h]
                                                         for tk, h in params["hulls"].items()},
                                           "idle_growth": params["growth"]}
            if a.split == "3way" and a.margins == "heldout" and not a.in_sample:
                half = {fid: i % 2 for i, fid in enumerate(ids_all)}
                groups = [(h, [fid for fid in ids if half[fid] == h], {fid for fid in ids_all if half[fid] != h})
                          for h in (0, 1)]
            else:
                groups = [(None, ids, None)]
            for h, gids, cal in groups:
                if a.margins != "heldout":
                    m = {}
                elif cal is None:
                    m = margins_from_contacts(rows, fold=train, q=a.margin_q, skip_families=skip)
                else:
                    m = margins_from_contacts(rows, fold=k, q=a.margin_q, fights=cal, skip_families=skip)
                name = f"fold{k}" + ("" if h is None else f"/half{h}")
                t0 = time.perf_counter()
                tables = FoldTables(extra, train, margins=m, base=a.margin, specs=FORUM_SPECS,
                                    family_wide=a.family_wide)
                print(f"{name}: {len(gids)} fights against the tables of fold {train}, margins from "
                      f"{'none' if a.margins != 'heldout' else (f'fold {train} (2-way)' if cal is None else f'{len(cal)} other fights of fold {k}')}"
                      f" ({time.perf_counter() - t0:.0f} s)", flush=True)
                rec, done = run_group(a, tables, params, lags, gids, by_fight, a.cache, name)
                fights_done += done
                for key, v in rec.stats.items():
                    stats[key].update(v)
                misses += rec.misses
                out["margins_by_group"][name] = {f"{tk}/{fam}": round(v, 4) for (tk, fam), v in sorted(m.items())}
                out["groups"].append({"group": name, "train_fold": train, "fights": done,
                                      "margin_fights": None if cal is None else len(cal),
                                      "recall": summarise(rec.stats, rec.misses, lags)["recall"],
                                      "placements": dict(rec.placements)})
    out.update(summarise(stats, misses, lags))
    out["fights"] = fights_done
    if a.area:
        full = margins_from_contacts(rows, fold=None, q=a.margin_q, skip_families=skip) \
            if a.margins == "heldout" else {}
        idle = None
        prod = out.get("production") or {}
        if a.idle_tube and prod.get("idle_growth"):
            idle = {tk: {"growth_l4": g[4], "hull": prod["body_hull"][tk]} for tk, g in prod["idle_growth"].items()
                    if tk in prod["body_hull"]}
        out["support_area"] = support_area(extra, full, FORUM_SPECS, base=a.margin, idle=idle)
    print(json.dumps({k: out[k] for k in ("recall", "n_misses", "miss_by")}, indent=1))
    if a.write_margins:
        # the planner's margins: per family the largest held-out residual over every contact of the build (both
        # folds); the per-group margins above were each certified on fights they were not calibrated on
        full = margins_from_contacts(rows, fold=None, q=a.margin_q, skip_families=skip)
        per_type: dict = {}
        for (tk, fam), v in full.items():
            per_type[tk] = max(per_type.get(tk, 0.0), v)
        cert = all(r["covered"] == r["n"] for r in out["recall"].values())
        doc = {"what": "per-family support margins (u) of the Forum behaviour tables: the largest held-out residual of "
                       "the per-state support over the build's contacts (behaviour_tables R_MARGIN_SEARCH_U caps it); "
                       "the planner dilates every support template of the family by it on top of the hero hurtbox and "
                       "its own margin. Idle families (idle_tube) have none: an enemy in its idle family is forecast "
                       "by the idle body tube (its body as last seen, moved along its velocity, grown by "
                       "idle_growth[type][frames since the sighting]) instead of its idle templates",
               "quantile": a.margin_q, "certified": cert, "certification": out["split"], "recall": out["recall"],
               "lags": lags, "base_margin": a.margin, "fights": fights_done, "extra": str(extra),
               "code": out["code"], "idle_tube": a.idle_tube,
               "by_family": {f"{tk}/{fam}": round(v, 4) for (tk, fam), v in sorted(full.items())},
               "by_type": {tk: round(v, 4) for tk, v in sorted(per_type.items())},
               "support_area": out.get("support_area")}
        if out.get("production"):
            doc["production_tubes"] = {k: v for k, v in out["production"].items() if k != "margins"}
            doc["fresh"] = out["fresh"]
            doc["by_tables"] = {j: v["recall"] for j, v in out["by_tables"].items()}
        if a.dev_json is not None and a.dev_json.exists():
            dev = json.loads(a.dev_json.read_text("utf-8"))
            doc["development"] = {"file": str(a.dev_json), "split": dev.get("split"), "recall": dev.get("recall"),
                                  "covered_other_than_by_the_forecast": dev.get("covered_other_than_by_the_forecast"),
                                  "forecast_parts_counted_apart": dev.get("forecast_parts_counted_apart"),
                                  "groups": [{k: g[k] for k in ("group", "fights", "margin_fights", "recall")}
                                             for g in dev.get("groups", [])]}
        a.write_margins.parent.mkdir(parents=True, exist_ok=True)
        a.write_margins.write_text(json.dumps(doc, indent=1) + "\n", "utf-8")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--encounter", default="BellBeast", choices=("BellBeast", "Forum"))
    ap.add_argument("--extra", type=Path, default=None,
                    help="Forum: the build's --extra directory (per-fold supports, contacts, walk tables)")
    ap.add_argument("--cache", type=Path, default=None, help="Forum: the forum_extract caches")
    ap.add_argument("--margins", default="heldout", choices=("heldout", "none"),
                    help="Forum: per-family margins from the training fold's held-out residuals, or none")
    ap.add_argument("--margin-q", type=float, default=1.0, help="Forum: the residual quantile a margin takes")
    ap.add_argument("--area", action="store_true", help="Forum: report the margins' support area cost")
    ap.add_argument("--family-wide", action="store_true",
                    help="Forum: also the current attack's family template (every state's union, t from the attack "
                         "start): a structural union for rare branches")
    ap.add_argument("--no-tube", dest="tube", action="store_false",
                    help="Forum: leave out the current-collider tube (forum_support.SubjectRecall.in_tube)")
    ap.add_argument("--write-margins", type=Path, default=None,
                    help="Forum: write the planner's per-family margins and this recall to this JSON")
    ap.add_argument("--in-sample", action="store_true",
                    help="Forum: each fold's fights against its own tables (a check of the tracker, not a recall)")
    ap.add_argument("--split", default="3way", choices=("3way", "2way"),
                    help="Forum: 3way = tables of the other fold, margins from the other half of the certified fold "
                         "(disjoint); 2way = margins from the training fold (leaky: their residuals are against the "
                         "certified fold's occupancy)")
    ap.add_argument("--no-idle-tube", dest="idle_tube", action="store_false",
                    help="Forum: forecast idle enemies by their idle templates + margins instead of the idle body "
                         "tube (forum_support.SubjectRecall.in_idle_tube)")
    ap.add_argument("--idle-q", type=float, default=1.0, help="Forum: the idle body tube's growth quantile")
    ap.add_argument("--fresh", type=Path, default=None,
                    help="Forum: certify the fights of this behaviour_build --contacts-only directory (not in the "
                         "build) against both folds' tables with the production margins")
    ap.add_argument("--fresh-cache", type=Path, default=None, help="Forum: the forum_extract caches of --fresh")
    ap.add_argument("--dev-json", type=Path, default=None,
                    help="Forum, with --write-margins: a development run's --json whose recall the margins file keeps")
    ap.add_argument("--recordings", default="")
    ap.add_argument("--lags", default="2,3,4")
    ap.add_argument("--view", default="oracle,ve")
    ap.add_argument("--table", type=Path, default=None)
    ap.add_argument("--margin", type=float, default=0.0)
    ap.add_argument("--noise-seed", type=int, default=None,
                    help="vision views: SimpleNoise after the filter, seeded with this + the fight's index (the "
                         "simulated final path's position noise and missed detections; the lag stands for the delay)")
    ap.add_argument("--max-fights", type=int, default=0)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.encounter == "Forum":
        if a.extra is None or a.cache is None:
            ap.error("--encounter Forum needs --extra and --cache")
        if a.fresh is not None and a.fresh_cache is None:
            ap.error("--fresh needs --fresh-cache")
        return forum_main(a)
    if not a.runs:
        ap.error("no runs")

    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster, load_planner_templates
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT

    table = (a.table / "BellBeast.json") if a.table else None
    model = BossModel.load("BellBeast", table=table)
    npz = str(a.table / "BellBeast_hitboxes.npz") if a.table else None
    t0 = time.perf_counter()
    tpls = load_planner_templates(model, a.margin, npz)
    print(f"templates: {len(tpls)} in {time.perf_counter() - t0:.1f} s", flush=True)
    recs = {x for x in a.recordings.split(",") if x} or None
    fights = [f for run in a.runs for f in fights_of(run, recs)]
    if a.max_fights:
        fights = fights[: a.max_fights]
    lags = [int(x) for x in a.lags.split(",")]
    views = [v for v in a.view.split(",") if v]
    stats: dict = defaultdict(Counter)
    misses: list = []
    for v in views:
        fc = Forecaster(model, ORACLE if v == "oracle" else VISION_EQUIVALENT, margin=a.margin, templates=tpls)
        fc.bell_tells = v == "ve_dust"
        from ssbot.train.planner_policy import FUSION
        if v != "oracle" and FUSION:
            from ssbot.combat.attack_fit import AttackFit
            fc.tracker.fit = AttackFit(model)      # multi-frame fusion of committed attacks (vision views)
        for i, fight in enumerate(fights):
            t1 = time.perf_counter()
            run_fight(fight, fc, v, lags, stats, misses, [BELL_BEAST],
                      None if a.noise_seed is None else a.noise_seed + i)
            line = " ".join(f"L{L} {stats[(v, L)]['covered']}/{stats[(v, L)]['n']}" for L in lags)
            print(f"[{v}] {i + 1}/{len(fights)} {fight['id']} {time.perf_counter() - t1:.1f} s  {line}", flush=True)
    out = {"fights": len(fights), "lags": lags, "margin": a.margin, "table": str(a.table) if a.table else None,
           "recall": {f"{v}/L{L}": dict(stats[(v, L)]) for v in views for L in lags},
           "misses": misses[:500], "n_misses": len(misses),
           "miss_sources": dict(Counter(m["source"] for m in misses)),
           "miss_states": dict(Counter(f"{m['view']}:{m['state']}" for m in misses))}
    print(json.dumps({k: out[k] for k in ("recall", "n_misses", "miss_sources", "miss_states")}, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
