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

Exit codes: 0 ok; 1 nothing to scan; 3 validation failed (a contact farther than R_FAIL_U from its family's logged
occupancy, a contact whose source had no exported damage collider and no export hole near it, or a contact outside
every attack): nothing is written unless --allow-failed-validation (then coverage.validation.ok is false in the file).

Cost (2026-10-01, i9-13900K, one core, the committed Bell Beast build): scanning 2.87 M STATE frames of 266 fights
took 638 s (0.22 ms per frame, ~2.4 s per data episode; the human session's range streams in 2 s), and finishing the
templates, validating 184,521 contacts in sample and held out, dilating, testing the decision covariates and writing
took 117 s.
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="*", type=Path, help="combat run directories")
    ap.add_argument("--human", action="append", default=[], help="SESSION:F0:F1 (repeatable)")
    ap.add_argument("--encounter", default="BellBeast", choices=sorted(SPECS))
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
    graph = json.loads(a.fsm_graph.read_text("utf-8")) if a.fsm_graph else None
    from ssbot.record.recorder import find_repo_root, git_info
    code = git_info(find_repo_root())  # the revision that runs the scan (files edited meanwhile do not count)
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
