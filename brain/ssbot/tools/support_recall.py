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
        [--margins heldout|none] [--margin-q 1.0] [--area] [--write-margins margins.json] [--json out.json]
each fold's fights against the tables built from the other fold alone (behaviour_build --extra), every contact
against the forecast of the enemy it came from, plus per-family margins calibrated on the training fold's held-out
residuals (never on the contacts they are tested on).
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


def support_area(extra: Path, margins: dict, specs) -> dict:
    """Per (type, family) the mean occupied area (u^2 per occupied time bin) of the per-state anchor support templates
    of the full build's two folds (their union not formed: each fold's mean), without and with the family margin
    (the margin's cost; the hero hurtbox dilation is left out of both)."""
    from ssbot.knowledge import hitbox_tables as hb
    out: dict = {}
    for tk, sp in specs.items():
        acc: dict = defaultdict(lambda: [0.0, 0.0, 0])
        for k in range(2):
            npz = extra / f"{sp.enemy}_support_fold{k}.npz"
            if not npz.exists():
                continue
            raw, _ = hb.load_templates(npz, prefix=hb.SUPPORT)
            for key, t in raw.items():
                parts = key.split("/")
                if len(parts) != 4 or parts[3] != "anchor":
                    continue
                m = margins.get((tk, parts[1]), 0.0)
                a0 = np.unpackbits(t.bits, axis=2).reshape(t.nt, -1).sum(axis=1)
                d = t.dilated(rx=m, ry=m) if m > 0 else t
                a1 = np.unpackbits(d.bits, axis=2).reshape(d.nt, -1).sum(axis=1)
                occ = a0 > 0
                if not occ.any():
                    continue
                r = acc[parts[1]]
                r[0] += float(a0[occ].mean()) * t.cell ** 2
                r[1] += float(a1[a1 > 0].mean()) * t.cell ** 2
                r[2] += 1
        for fam, (a0, a1, n) in acc.items():
            out[f"{tk}/{fam}"] = {"margin_u": round(margins.get((tk, fam), 0.0), 3), "templates": n,
                                  "area_u2": round(a0 / n, 2), "area_with_margin_u2": round(a1 / n, 2),
                                  "ratio": round(a1 / a0, 3) if a0 else None}
    return out


def forum_main(a: argparse.Namespace) -> int:
    """--encounter Forum: held-out recall of the gauntlet tables (ssbot.knowledge.forum_support), fold k's fights
    against the tables of the other fold, each enemy's contacts against its own forecast."""
    from ssbot.knowledge.forum_cache import cache_name, load_cache
    from ssbot.knowledge.forum_support import FoldTables, SubjectRecall, margins_from_contacts, read_contacts
    from ssbot.knowledge.gauntlet_tables import FORUM_SPECS

    extra = a.extra
    rows = read_contacts(extra / "contacts.jsonl.gz")
    build = json.loads((extra / "build.json").read_text("utf-8"))
    folds = {f["id"]: f["fold"] for f in build["fights"]}
    by_fight: dict[str, list] = defaultdict(list)
    for r in rows:
        by_fight[r["fight"].rsplit("/", 1)[0]].append(r)
    lags = [int(x) for x in a.lags.split(",")]
    out: dict = {"encounter": "Forum", "extra": str(extra), "lags": lags, "base_margin": a.margin,
                 "margins": a.margins, "margin_q": a.margin_q, "folds": {}}
    stats: dict = defaultdict(Counter)
    misses: list = []
    margins_used = {}
    fights_done = 0
    for k in (0, 1):
        train = k if a.in_sample else 1 - k
        if a.margins == "heldout":
            # calibrated on the training fold's contacts (their residual against fold k's occupancy), certified on
            # fold k's: the contacts that set a margin are never the ones it is tested on
            m = margins_from_contacts(rows, fold=train, q=a.margin_q)
        else:
            m = {}
        margins_used[k] = m
        t0 = time.perf_counter()
        tables = FoldTables(extra, train, margins=m, base=a.margin, specs=FORUM_SPECS)
        print(f"fold {k}: tables of fold {train}, {len(tables.templates)} templates ({time.perf_counter() - t0:.0f} s)",
              flush=True)
        rec = SubjectRecall(tables, lags)
        ids = [fid for fid, fd in folds.items() if fd == k]
        if a.max_fights:
            ids = ids[:a.max_fights]
        for i, fid in enumerate(ids):
            path = a.cache / cache_name(fid)
            if not path.exists():
                print(f"  no cache for {fid}", flush=True)
                continue
            t1 = time.perf_counter()
            rec.run(load_cache(path), by_fight.get(fid, []), label=f"fold{k}")
            fights_done += 1
            n = sum(v["n"] for (tk, L), v in rec.stats.items() if L)
            c = sum(v["covered"] for (tk, L), v in rec.stats.items() if L)
            print(f"  [{i + 1}/{len(ids)}] {fid} {time.perf_counter() - t1:.1f} s  covered {c}/{n}", flush=True)
        for key, v in rec.stats.items():
            stats[key].update(v)
        misses += rec.misses
        out["folds"][str(k)] = {"train_fold": train, "fights": len(ids), "placements": dict(rec.placements)}
    by = {}
    for (tk, L), v in sorted(stats.items()):
        if not L:
            by[f"{tk}"] = dict(v)
            continue
        by[f"{tk}/L{L}"] = {"n": v["n"], "covered": v["covered"], "outside_attacks": v["outside_attacks"],
                            "recall": round(v["covered"] / v["n"], 6) if v["n"] else None}
    tot = {L: [sum(v["n"] for (tk, l2), v in stats.items() if l2 == L),
               sum(v["covered"] for (tk, l2), v in stats.items() if l2 == L)] for L in lags}
    out["recall"] = {f"L{L}": {"n": n, "covered": c, "recall": round(c / n, 6) if n else None}
                     for L, (n, c) in tot.items()}
    out["by_type"] = by
    out["fights"] = fights_done
    out["margins_by_fold"] = {str(k): {f"{tk}/{fam}": round(v, 4) for (tk, fam), v in m.items()}
                              for k, m in margins_used.items()}
    out["n_misses"] = len(misses)
    out["miss_by"] = dict(Counter(f"{m['type']}/{m['family']}/{m['state']}/L{m['lag']}" for m in misses)
                          .most_common(60))
    out["misses"] = misses[:400]
    if a.area:
        full = margins_from_contacts(rows, fold=None, q=a.margin_q) if a.margins == "heldout" else {}
        out["support_area"] = support_area(extra, full, FORUM_SPECS)
    print(json.dumps({k: out[k] for k in ("recall", "n_misses", "miss_by")}, indent=1))
    if a.write_margins:
        # the planner's margins: per family the largest held-out residual over both folds' contacts (the per-fold
        # margins above were each certified on the fold they were not calibrated on)
        full = margins_from_contacts(rows, fold=None, q=a.margin_q)
        per_type: dict = {}
        for (tk, fam), v in full.items():
            per_type[tk] = max(per_type.get(tk, 0.0), v)
        cert = all(r["covered"] == r["n"] for r in out["recall"].values())
        doc = {"what": "per-family support margins (u) of the Forum behaviour tables: the largest held-out residual of "
                       "the per-state support (behaviour_tables R_MARGIN_SEARCH_U caps it); the planner dilates every "
                       "support template of the family by it on top of the hero hurtbox and its own margin",
               "quantile": a.margin_q, "certified": cert, "recall": out["recall"], "lags": lags,
               "base_margin": a.margin, "fights": fights_done, "extra": str(extra),
               "by_family": {f"{tk}/{fam}": round(v, 4) for (tk, fam), v in sorted(full.items())},
               "by_type": {tk: round(v, 4) for tk, v in sorted(per_type.items())},
               "by_fold": out["margins_by_fold"], "support_area": out.get("support_area")}
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
    ap.add_argument("--write-margins", type=Path, default=None,
                    help="Forum: write the planner's per-family margins and this recall to this JSON")
    ap.add_argument("--in-sample", action="store_true",
                    help="Forum: each fold's fights against its own tables (a check of the tracker, not a recall)")
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
