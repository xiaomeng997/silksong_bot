"""Read existing #421 evidence; archive no new replay, P or game."""
import datetime
import hashlib
import json
from pathlib import Path

B = Path('C:/ssbot/data/m2_play/clapper_plan')
P = B / 'opus/review182/s312/r3'
A = B / 'analysis/route_hammer420_20261113'
rows = []
accounting = {'SSBOT_FORUM_CHAIN_BATCH', 'SSBOT_FORUM_CHAIN_PROBE', 'SSBOT_FORUM_CHAIN_BUDGET'}
for name in ['d_ep22a', 'd_ep22b', 'd_ep38', 'd_ep28', 'd_ep1', 'd_ep30', 'd_ep29', 'd_ep39']:
    rs, ms, bindings = [], [], {}
    for arm in ['off', 'on']:
        folder = P / 'r' / (name + '_' + arm)
        for fname in ['RESULT.json', 'CONFIGURATION_MANIFEST.json']:
            path = folder / fname
            raw = path.read_bytes()
            bindings[str(path)] = hashlib.sha256(raw).hexdigest()
            (rs if fname == 'RESULT.json' else ms).append(json.loads(raw.decode('utf-8-sig')))
    maps = [{r['f']: (r.get('keys'), r.get('owner'), r.get('hero_x'), r.get('hero_y')) for r in d.get('rows', [])} for d in rs]
    changed = [f for f in sorted(set(maps[0]) | set(maps[1])) if maps[0].get(f) != maps[1].get(f)]
    switch_diff = [k for k in sorted(set(ms[0]['switches']) | set(ms[1]['switches'])) if ms[0]['switches'].get(k) != ms[1]['switches'].get(k)]
    prediffs = [f for f in changed if f < rs[0]['synthetic_from']]
    forced_after = [[x for x in (d.get('forced_planner_ticks') or []) if (x.get('f', -1) if isinstance(x, dict) else x) >= d['synthetic_from']] for d in rs]
    rows.append(dict(pair=name, synthetic_from=[d['synthetic_from'] for d in rs],
                     first_row_difference=changed[0] if changed else None,
                     first_difference_before_synthetic=bool(prediffs),
                     first_model_hurt=[d.get('first_model_hurt') for d in rs],
                     same_sources=ms[0]['source_sha256'] == ms[1]['source_sha256'],
                     source_count=[len(m['source_sha256']) for m in ms],
                     same_configs=ms[0]['configs'] == ms[1]['configs'],
                     switch_diff=switch_diff,
                     non_accounting_switch_diff=[s for s in switch_diff if s not in accounting],
                     forced_planner_ticks_after_synthetic=forced_after,
                     exceptions=[d.get('exception') for d in rs],
                     bindings=bindings))
letter = next(x for x in (B / 'opus/TO_SOL.md').read_text(encoding='utf-8-sig').splitlines() if x.startswith('| 421 |'))
report = dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(), opus_number=421,
              type='withdrawn-prototype evidence review; not production acceptance',
              pairs=rows, letter421=letter,
              findings=[
                  'ep38: first row difference 117547 is after SYN117542; on hands back then vault far_lock hooks into other body at117571, off has no modeled hurt in this bounded window. Supports shelving prototype, not a live HP claim.',
                  'ep22b and ep28 have owner/row differences before SYN while recorded-input forcing is active. Eight pairs are engineering windows with limits, not eight uniform same-internal-state counterfactual trials.',
                  'stance_landing.py uses observed later landing root and infers facing from hero side there, then projects it backward through flight. Four recurring-inside cases are retrospective candidates, not four proven predictable/avoidable losses.',
                  'Single empirical hammer extent is narrower than shared attack-range envelopes; it may suggest an L2 preference but must not replace unchanged planner/geometry safety checks.',
                  'No further old-prototype replay or formal P is necessary to keep it unmerged. Author-reported23tests/20mutants/1697affected are not independently rerun or claimed production acceptance.'
              ],
              production_source_accepted=False, formal_P=False, game=False,
              no_new_replay=True, accepted_source_unchanged='7a43c1edf0148834bb78eff0ebb7da7f9723c718')
for name in ['stance_landing.py', 'stance_landing.txt', 'cmp_w3.py', 'cmp_w3_v32.txt', 'PROTOTYPE_V32_HASHES.txt', 'route_hammer_v32.patch']:
    path = P / name
    report.setdefault('evidence_files', {})[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
path = A / 'EVIDENCE421.json'
temp = path.with_suffix('.tmp')
temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
temp.replace(path)
print(json.dumps({'artifact': str(path), 'pairs': len(rows), 'all_pair_sources_match': all(x['same_sources'] for x in rows),
                  'all_pair_configs_match': all(x['same_configs'] for x in rows),
                  'pre_synthetic_difference_pairs': [x['pair'] for x in rows if x['first_difference_before_synthetic']],
                  'ep38': {k: rows[2][k] for k in ['first_row_difference', 'first_model_hurt']},
                  'all_non_accounting_diffs': sorted({s for x in rows for s in x['non_accounting_switch_diff']})}, ensure_ascii=False))
