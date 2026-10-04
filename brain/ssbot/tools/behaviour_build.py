"""Build an enemy's behaviour tables and hitbox templates from combat runs and human sessions (M2 W2), and report
coverage against the M2 exit target (>= 200 logged instances per A-class attack, DESIGN §5).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.behaviour_build C:/ssbot/data/runs/m2/<run> [<run> ...]
        [--human C:/ssbot/data/human/20260930_210337:64000:68460] [--encounter BellBeast]
        [--out ../knowledge/1.0.30000/enemies] [--max-fights N] [--report-only] [--paths] [--fsm-graph G.json]
        [--allow-failed-validation]

Each run contributes one fight per AttemptRecord (<run>/attempts_i*.jsonl, frames f_wake..f_end) whose recording is
closed; recordings a live run is still writing are skipped and listed. --human SESSION:F0:F1 adds a human session's
frame range (repeatable). Writes <out>/<enemy>.json and <out>/<enemy>_hitboxes.npz (ssbot.knowledge.behaviour_tables,
ssbot.knowledge.hitbox_tables) unless --report-only, then prints the coverage report: instances per attack family
(and phase) against the target, FSM edges and states with fewer than 30 logged exits, the contact validation (every
logged hit and blocked contact against the support templates), export holes and the decision covariates kept.

A multi-enemy arena (--encounter Forum: ssbot.knowledge.gauntlet_tables) gets one table per enemy type, written to
<out>/forum/<enemy>.json and _hitboxes.npz, plus <out>/forum/coverage.json with the attack instances per family, their
rate per hour of fight time and the hours still needed for the target, and "validation": per type the in-sample
result (distinct uncovered / unexplained / outside contacts), the held-out (other fold) coverage and whether the
support is shown to be conservative (validation.support_conservative), plus the hero contacts no enemy could take.

Exit codes: 0 ok; 1 nothing to scan; 3 validation failed (a contact farther than R_FAIL_U from its family's logged
occupancy, a contact whose source had no exported damage collider and no export hole near it, or a contact outside
every attack): nothing is written unless --allow-failed-validation (then coverage.validation.ok is false in the file).

Cost (2026-10-01, i9-13900K, one core, the committed Bell Beast build at adda74a): scanning 2.87 M STATE frames of
266 fights took 656 s (0.23 ms per frame, ~2.5 s per data episode; the human session's range streams in 2 s), and
finishing the templates, validating 184,521 contacts in sample and held out, dilating, testing the decision
covariates and writing took 130 s (786 s in all).
"""
import argparse
import json
import sys
import time
from pathlib import Path

from ssbot.knowledge.behaviour_tables import (
    N_WORST,
    SPECS,
    TARGET_INSTANCES,
    BehaviourBuilder,
    ValidationFailed,
    human_fight,
    run_fights,
)
from ssbot.knowledge.gauntlet_tables import GAUNTLET_SPECS


def default_out() -> Path:
    from ssbot.record.recorder import find_repo_root
    root = find_repo_root() or Path.cwd()
    return root / "knowledge" / "1.0.30000" / "enemies"


def parse_human(arg: str):
    path, f0, f1 = arg.rsplit(":", 2)
    return human_fight(Path(path), int(f0), int(f1))


def report(tables: dict) -> str:
    cov = tables["coverage"]
    lines = [f"{tables['enemy']}: {cov['fights']} fights, {cov['frames']} frames, {cov['game_s']} s of game time",
             f"instances per attack family (target {TARGET_INSTANCES}):"]
    for fam, c in cov["families"].items():
        ph = ", ".join(f"{k} {v}" for k, v in sorted(c["by_phase"].items()))
        mark = "ok" if c["n"] >= TARGET_INSTANCES else f"{c['missing']} missing"
        lines.append(f"  {fam:12s} {c['n']:5d}  ({ph})  {mark}")
    lines.append(f"FSM edges with n < {N_WORST}: {len(cov['edges_n_lt_30'])}")
    lines += [f"  {e}" for e in cov["edges_n_lt_30"]]
    lines.append(f"states with < {N_WORST} logged exits (worst case): {len(cov['states_n_lt_30'])}")
    lines += [f"  {s}" for s in cov["states_n_lt_30"]]
    v = cov.get("validation")
    if v:
        lines.append(f"validation {'ok' if v['ok'] else 'FAILED'}: {v['contacts']} contacts ({v['damage']} hits, "
                     f"{v['blocked_frames']} blocked frames), uncovered {v['uncovered']['n']}, unexplained "
                     f"{v['unexplained']['n']}, outside attacks {v['outside_attacks']['n']}, no exported collider "
                     f"but an export hole {v['no_exported_collider_explained_by_export_hole']['n']}")
        lines += [f"  {c}" for c in (v["uncovered"]["first"] + v["unexplained"]["first"] +
                                     v["outside_attacks"]["first"])[:10]]
        pg, am = v.get("partial_export_holes") or {}, v.get("ambient") or {}
        if pg.get("n") or am.get("n"):
            lines.append(f"  named collider missing from the export (partial holes): {pg.get('n', 0)}; ambient hazard "
                         f"contacts: {am.get('n', 0)} (radius {am.get('radius_u')} u)")
    for fam, a in tables["attacks"].items():
        sets = (a.get("residual_u") or {}).get("sets") or {}
        if sets:
            lines.append(f"  residual {fam}: " + ", ".join(
                f"{k} p99 {sets[k]['p99']} max {sets[k]['max']} u (n {sets[k]['n']})" for k in ("anchor", "world_all")
                if k in sets))
    if v:
        for name, h in v.get("heldout", {}).items():
            if isinstance(h, dict):
                lines.append(f"  held out ({name}): {h['within_radius']} of {h['n']} contacts inside the support "
                             f"({h.get('within_radius_t4')} with +-4 bins)")
    for tk, e in tables.get("entities", {}).items():
        st = e.get("self_template")
        if st:
            h = st["holdout"]
            lines.append(f"  self template {tk}: radius {st['radius_u']} u, {st['contacts']} contacts; held out "
                         f"{h.get('within_radius')} of {h.get('n')} inside")
    eh = cov.get("export_holes") or {}
    if eh.get("frames"):
        lines.append(f"export holes (exported without colliders, frames): {eh['frames']}; {eh['instances']} instances")
    hb = cov.get("hero_box_u") or {}
    if hb.get("n"):
        lines.append(f"hero box w {hb['w']} h {hb['h']} u over {hb['n']} frames: planner half-extents "
                     f"{'ok' if hb['ok'] else 'TOO SMALL'}")
    for st, d in tables.get("decisions", {}).items():
        sig = {n: f"{r['p']:.2g}" for n, r in d["tests"].items() if r.get("significant")}
        ho = d.get("heldout") or {}
        lines.append(f"decision {st} (n {d['n']}): kept {d['conditioners'] or '-'}; held-out log loss "
                     f"{ho.get('logloss_conditioned')} vs {ho.get('logloss_unconditional')} unconditional; "
                     f"significant {sig or '-'}")
    if cov["counters"]:
        lines.append("counters:")
        lines += [f"  {k}: {v}" for k, v in cov["counters"].items()]
    return "\n".join(lines)


def type_validation(v: dict) -> dict:
    """One enemy type's validation for coverage.json: distinct failing contacts in sample, the held-out coverage
    (anchor and self sets) and the support status."""
    def held(r: dict | None) -> dict:
        if not isinstance(r, dict) or not r.get("n"):
            return {"n": 0}
        return {"n": r["n"], "within_radius": r["within_radius"], "beyond_r_fail": r["beyond_r_fail"],
                "share_beyond": round(r["beyond_r_fail"] / r["n"], 4), "beyond_r_fail_t4": r.get("beyond_r_fail_t4")}
    ho = v.get("heldout") or {}
    return {"ok": v["ok"], "support_conservative": v.get("support_conservative", v["ok"]),
            "support_note": v.get("support_note"), "contacts": v["contacts"],
            "uncovered_contacts": v["uncovered"].get("contacts", v["uncovered"]["n"]),
            "uncovered_pairs": v["uncovered"]["n"], "unexplained": v["unexplained"]["n"],
            "outside_attacks": v["outside_attacks"]["n"], "heldout_anchor": held(ho.get("anchor")),
            "heldout_self": held(ho.get("self"))}


def write_extra(extra: Path, g, code: dict) -> None:
    """The held-out material of a multi-enemy build (too large for the repository): per type the support templates
    of each fold alone (<enemy>_support_fold<k>.npz: BehaviourBuilder.fold_support), every contact with its
    attribution and residuals (contacts.jsonl.gz) and the fights with their folds (build.json). support_recall
    --encounter reads them."""
    import gzip

    from ssbot.knowledge import hitbox_tables as hb
    from ssbot.knowledge.behaviour_tables import N_FOLDS
    extra.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with gzip.open(extra / "contacts.jsonl.gz", "wt", encoding="utf-8") as fh:
        for tk, b in g.builders.items():
            if not b.instances:
                continue
            for r in b.contact_rows():
                fh.write(json.dumps({"type": tk, **r}) + "\n")
            for k in range(N_FOLDS):
                hb.save_templates(extra / f"{b.spec.enemy}_support_fold{k}.npz", b.fold_support(k))
    walk = {}
    for tk, b in g.builders.items():
        # per fold: logged dwell range per Control state and the successors logged (deaths left out), so the held-out
        # recall walks the other fold's graph only
        deaths = set(b.spec.death_states)
        dw: dict = {k: {} for k in range(N_FOLDS)}
        for d in b.dwells:
            lo, hi = dw[d.fold].get(d.state, (d.dwell_s, d.dwell_s))
            dw[d.fold][d.state] = (min(lo, d.dwell_s), max(hi, d.dwell_s))
        succ: dict = {k: {} for k in range(N_FOLDS)}
        for t in b.transitions:
            if t.frm is not None and t.to not in deaths:
                succ[t.fold].setdefault(t.frm, set()).add(t.to)
        walk[tk] = {"dwell": {str(k): {s: [round(v[0], 5), round(v[1], 5)] for s, v in d.items()}
                              for k, d in dw.items()},
                    "succ": {str(k): {s: sorted(v) for s, v in d.items()} for k, d in succ.items()}}
    (extra / "build.json").write_text(json.dumps(
        {"fights": g.fights, "code": code, "types": {tk: b.spec.enemy for tk, b in g.builders.items()},
         "walk": walk}, indent=1) + "\n", encoding="utf-8")
    print(f"extra: {extra} ({time.perf_counter() - t0:.1f} s)", flush=True)


def gauntlet_main(a: argparse.Namespace, fights: list, skipped: list, code: dict) -> int:
    """One table per enemy type of a multi-enemy arena (ssbot.knowledge.gauntlet_tables), written to
    <out>/<encounter lower>/, then the attack counts against the target with the rate per hour of fight time."""
    from ssbot.knowledge.gauntlet_tables import GauntletBuilder
    g = GauntletBuilder(GAUNTLET_SPECS[a.encounter], keep_paths=a.paths)
    t_all = time.perf_counter()
    for i, fight in enumerate(fights):
        t0 = time.perf_counter()
        info = g.scan(fight)
        print(f"[{i + 1}/{len(fights)}] {fight.id}: {info['frames']} frames, subjects {info['subjects']}, "
              f"instances {sum(info['instances'].values())}, {fight.outcome or '-'} ({time.perf_counter() - t0:.1f} s)",
              flush=True)
    if skipped:
        print(f"skipped {len(skipped)}:", *skipped[:20], sep="\n  ")
    hours = sum(f.f1 - f.f0 for f in fights) / 60.0 / 3600.0
    out = (a.out or default_out()) / a.encounter.lower()
    rc = 3 if g.unattributed else 0
    written = {}
    vals = {}
    for tk, b in g.builders.items():
        if not b.instances:
            print(f"== {tk}: no instances")
            continue
        tables = b.tables()
        vals[tk] = type_validation(tables["coverage"]["validation"])
        if not tables["coverage"]["validation"]["ok"]:
            rc = 3
        if not a.report_only:
            try:
                js, npz, tables = b.write(out, allow_failed=a.allow_failed_validation, code=code)
                written[tk] = str(js)
                print(f"wrote {js} ({js.stat().st_size / 1e3:.0f} KB), {npz} ({npz.stat().st_size / 1e3:.0f} KB)")
            except ValidationFailed as e:
                print(f"{tk}: validation failed, nothing written: {e}", file=sys.stderr)
        print(f"== {tk}")
        print(report(tables))
    rows = g.report_rows(hours=hours, target=TARGET_INSTANCES)
    print(f"\nattack instances per family over {len(fights)} fights, {hours:.2f} h of fight time "
          f"(target {TARGET_INSTANCES}; hours of fight time per instance at this rate):")
    for r in rows:
        if r["idle"] and not r["n"]:
            continue
        print(f"  {r['enemy']:16s} {r['family']:14s} {r['n']:5d}  {r['per_hour'] or 0:7.1f}/h  "
              f"{'idle' if r['idle'] else ('ok' if r['hours_to_target'] == 0 else r['hours_to_target'])}")
    print("counters:", dict(g.counters.most_common(20)))
    validation = {
        "ok": rc == 0, "folds": "per fight (alternating)",
        "unattributed": {"desc": "hero contacts no enemy could take (validation failures)", "n": len(g.unattributed),
                         "first": g.unattributed[:20]},
        "types": vals}
    print(f"\nvalidation {'ok' if rc == 0 else 'FAILED'}; unattributed contacts {len(g.unattributed)}")
    for tk, v in vals.items():
        h = v["heldout_anchor"]
        print(f"  {tk:22s} in sample: {v['uncovered_contacts']} uncovered, {v['unexplained']} unexplained, "
              f"{v['outside_attacks']} outside of {v['contacts']}; held out: {h.get('beyond_r_fail')} of {h.get('n')} "
              f"beyond R_FAIL ({h.get('share_beyond')}); conservative {v['support_conservative']}")
    if not a.report_only:
        out.mkdir(parents=True, exist_ok=True)
        (out / "coverage.json").write_text(json.dumps(
            {"encounter": a.encounter, "fights": g.fights, "fight_hours": round(hours, 3), "rows": rows,
             "validation": validation, "counters": dict(g.counters.most_common()), "tables": written, "code": code},
            indent=1) + "\n", encoding="utf-8")
    if a.extra is not None:
        try:
            write_extra(a.extra, g, code)
        except Exception:     # the tables are written already; keep the scan for a retry
            import pickle
            import traceback
            traceback.print_exc()
            with (a.extra / "gauntlet_builder.pkl").open("wb") as fh:
                pickle.dump(g, fh, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"extra failed; the builder is pickled in {a.extra}", file=sys.stderr)
    print(f"scan + build {time.perf_counter() - t_all:.1f} s")
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="*", type=Path, help="combat run directories")
    ap.add_argument("--human", action="append", default=[], help="SESSION:F0:F1 (repeatable)")
    ap.add_argument("--encounter", default="BellBeast", choices=sorted(SPECS) + sorted(GAUNTLET_SPECS),
                    help="a boss (one Control FSM) or a multi-enemy arena (one table per enemy type: "
                         "ssbot.knowledge.gauntlet_tables)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--max-fights", type=int, default=0, help="stop after this many fights (0 = all)")
    ap.add_argument("--report-only", action="store_true", help="do not write the knowledge files")
    ap.add_argument("--include-open", action="store_true", help="also read recordings still being written")
    ap.add_argument("--fsm-graph", type=Path, default=None,
                    help="the Control FSM's static graph (JSON of oracle RPC fsm.graph): never-logged edges join the "
                         "support")
    ap.add_argument("--paths", action="store_true",
                    help="store every family's per-instance boss trajectories (<family>/paths; by default only "
                         "families with a variable anchor)")
    ap.add_argument("--allow-failed-validation", action="store_true",
                    help="write the files even when a logged contact is uncovered or unexplained")
    ap.add_argument("--extra", type=Path, default=None,
                    help="multi-enemy arenas: write the per-fold supports and the contacts here (support_recall "
                         "--encounter; large, keep it out of the repository)")
    ap.add_argument("--fights-list", type=Path, default=None,
                    help="write the scanned fights (id, recording, frames) to this JSON (the frozen input of a build)")
    a = ap.parse_args(argv)

    fights, skipped = [], []
    for run in a.runs:
        f, s = run_fights(run, closed_only=not a.include_open)
        fights += f
        skipped += s
    fights += [parse_human(h) for h in a.human]
    if a.max_fights:
        fights = fights[:a.max_fights]
    if not fights:
        print("no fights to scan", *skipped, sep="\n  ", file=sys.stderr)
        return 1
    if a.fights_list is not None:
        a.fights_list.parent.mkdir(parents=True, exist_ok=True)
        a.fights_list.write_text(json.dumps(
            {"fights": [{"id": f.id, "path": str(f.path), "f0": f.f0, "f1": f.f1, "outcome": f.outcome}
                        for f in fights], "skipped": skipped}, indent=1) + "\n", encoding="utf-8")
    graph = json.loads(a.fsm_graph.read_text("utf-8")) if a.fsm_graph else None
    from ssbot.record.recorder import find_repo_root, git_info
    code = git_info(find_repo_root())  # the revision that runs the scan (files edited meanwhile do not count)
    if a.encounter in GAUNTLET_SPECS:
        return gauntlet_main(a, fights, skipped, code)
    b = BehaviourBuilder(SPECS[a.encounter], keep_paths=a.paths, fsm_graph=graph)
    t_all = time.perf_counter()
    for i, fight in enumerate(fights):
        t0 = time.perf_counter()
        info = b.scan(fight)
        print(f"[{i + 1}/{len(fights)}] {fight.id}: {info['frames']} frames, {info['instances']} instances, "
              f"{fight.outcome or '-'} ({time.perf_counter() - t0:.1f} s)", flush=True)
    if skipped:
        print(f"skipped {len(skipped)}:", *skipped[:20], sep="\n  ")
    tables = b.tables()
    rc = 0 if tables["coverage"]["validation"]["ok"] else 3
    if not a.report_only:
        try:
            js, npz, tables = b.write(a.out or default_out(), allow_failed=a.allow_failed_validation, code=code)
            print(f"wrote {js} ({js.stat().st_size / 1e3:.0f} KB), {npz} ({npz.stat().st_size / 1e3:.0f} KB)")
        except ValidationFailed as e:
            print(f"validation failed, nothing written: {e}", file=sys.stderr)
    print(f"scan + build {time.perf_counter() - t_all:.1f} s")
    print(report(tables))
    return rc


if __name__ == "__main__":
    sys.exit(main())
