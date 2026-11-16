from pathlib import Path
import datetime
import hashlib
import json
import numpy as np
from collections import Counter

B = Path('C:/ssbot/data/m2_play/clapper_plan')
A = B / 'analysis/dash_side412_20261113'
read = lambda p: json.loads(p.read_text('utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def stats(values):
    return dict(ticks=len(values), tick_p50_ms=float(np.percentile(values, 50)),
                tick_p99_ms=float(np.percentile(values, 99)), tick_max_ms=max(values),
                over_16_67ms=sum(v > 1000 / 60 for v in values))


def main():
    assert all(sha(Path(p)) == h for p, h in read(A / 'REPLAY_INPUT_BINDING.json')['files'].items())
    allowed = {'SSBOT_FORUM_CHAIN_BLOCK', 'SSBOT_FORUM_CHAIN_ORDER', 'SSBOT_FORUM_CHAIN_SCHEDULE',
               'SSBOT_WORKER_BOOST', 'SSBOT_WORKER_CPUS'}
    paths = {'new': {'G': A / 'P_NEW/G', 'A': A / 'P_NEW/A'},
             'baseline': {'G': A / 'P_BASELINE/G', 'A': A / 'P_BASELINE_A/A'}}
    cases = {'new': A / 'CASE_NEW.json', 'baseline': A / 'CASE_BASELINE.json'}
    outputs, wires, chains, profiles, packets = {}, {}, {}, [], {}
    for label, windows in paths.items():
        case = read(cases[label])
        packet = read(Path(case['source_packet_file']))
        packets[label] = packet
        source = Path(case['source_root'])
        assert sha(Path(case['source_packet_file'])) == case['source_packet_sha256']
        assert all(sha(source / n) == h for n, h in packet['raw_runtime_files_sha256'].items())
        assert all(sha(source / n) == h for n, h in packet['support_sha256'].items())
        normalized = {n: hashlib.sha256((source / n).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                      for n in packet['raw_runtime_files_sha256']}
        out, costs, wires[label], chains[label] = {}, [], {}, {}
        for q, p in windows.items():
            final = read(p.parent / 'FINALIZED.json')
            execution = read(p.parent / 'EXECUTION.json')
            assert final['cleanup_verified']
            if label == 'baseline' and q == 'G':
                assert not final['execution_ok'] and execution['error']['message'] == 'resource gate'
                assert [x['name'] for x in execution['contexts']] == ['G']
            else:
                assert final['execution_ok']
            context = next(x for x in execution['contexts'] if x['name'] == q)
            assert context['ready'] and context['measured_ticks'] == (25 if q == 'G' else 12)
            for worker in context['workers'].values():
                assert worker['ready'] and worker['closed'] and worker['exitcode'] == 0
            r, m = read(p / 'RESULT.json'), read(p / 'CONFIGURATION_MANIFEST.json')
            assert r['exception'] is None and not r['foreign'] and r['knife_head'] == case['source']
            assert r['p_entry']['formal']
            # Frozen runtime exports omit tests/package-manager metadata, while
            # their Git index retains the original tree. Check the owning runtime
            # bytes above; do not mistake these documented export deletions for a
            # clean full checkout or silently waive changes in ssbot itself.
            export_omissions = r['knife_brain_dirty'].splitlines()
            assert all(line.strip().startswith('D brain/tests/') or line.strip() in {
                'D brain/.python-version', 'D brain/pyproject.toml',
                'D brain/uv.lock', 'D brain/uv.toml'} for line in export_omissions)
            assert not any(x['f'] >= r['synthetic_from'] for x in r['forced_planner_ticks'])
            assert not m['unknown_environment_switches'] and set(m['unresolved']) <= allowed
            assert all(h == normalized.get('brain/ssbot/' + n) for n, h in m['source_sha256'].items())
            # The executor binds control settings, not per-output budget/probe
            # names. Table bindings retain their mode while source-root paths
            # naturally differ between the two byte-verified exports.
            profiles.append({k: {'raw': v['raw'], 'present': v['present'],
                                  'bindings': {n: b.replace(str(source), '<SOURCE>') if isinstance(b, str) else b
                                               for n, b in v['bindings'].items()}}
                             for k, v in m['switches'].items()
                             if k not in {'SSBOT_FORUM_CHAIN_BUDGET', 'SSBOT_FORUM_CHAIN_BATCH', 'SSBOT_FORUM_CHAIN_PROBE'}})
            for switch, expected in [('SSBOT_FORUM_CHAIN_B13', True), ('SSBOT_FORUM_CHAIN_B13B', True),
                                     ('SSBOT_FORUM_RUNE_EXIT_FINAL', True), ('SSBOT_FORUM_SLAM_NO_NEW_GLIDE', False),
                                     ('SSBOT_FORUM_TWO_PLAN_INLINE', '')]:
                assert list(m['switches'][switch]['bindings'].values()) == [expected]
            rt = r['p_entry']['timing']['runtime']
            assert rt['cpu_affinity'] == list(range(16)) and rt['priority'] == 128
            assert not rt['query_errors'] and not rt['power_throttling']['execution_speed_throttled']
            ticks, actions = [], {}
            for line in (p / 'measurement_trace.jsonl').open(encoding='utf-8'):
                z = json.loads(line)
                if z.get('kind') == 'tick':
                    ticks.append(z)
                if z.get('kind') == 'action':
                    assert z['policy_mask_matches_wire'] and z['policy_flags_match_wire'] and not z['target_already_observed']
                    actions[z['f']] = {k: z[k] for k in ['mask', 'owner', 'target_frame']}
            assert len(ticks) == len(actions) == r['p_entry']['ticks']
            frames = [t['f'] for t in ticks]
            assert frames == list(range(5590, 5615) if q == 'G' else range(20929, 20941))
            vals = [t['total_tick_ms'] for t in ticks]
            costs += vals
            chain = [json.loads(l) for l in (p / 'decisions_i0.chain.jsonl').open(encoding='utf-8')]
            chains[label][q] = chain
            if q == 'A':
                fixture = read(p / 'PREWINDOW_INPUT_FIXTURE.json')
                assert fixture['flip_frame'] == 20928 and fixture['restored_before_measured_frame'] == 20929
                assert not fixture['restored_in_cleanup']
                prior = next(z for z in chain if z.get('frame') == 20928 and z['event'] == 'transport_sent')
                assert prior['mask'] == 1048576 and prior['target'] == 20930
            out[q] = dict(**stats(vals), frames=frames, artifact=str(p), source_files=len(m['source_sha256']),
                          git_nonruntime_export_omissions=len(export_omissions),
                          actual_owners=dict(Counter(t['owner'] for t in ticks)),
                          workers_closed=True, unknown_switches=[], operational_unresolved=m['unresolved'])
            wires[label][q] = actions
        outputs[label] = dict(**stats(costs), source=case['source'], windows=out)
    assert all(p == profiles[0] for p in profiles)
    runtime_delta = [n for n, h in packets['new']['raw_runtime_files_sha256'].items()
                     if h != packets['baseline']['raw_runtime_files_sha256'].get(n)]
    assert runtime_delta == ['brain/ssbot/combat/knife_chain_air_native.py']
    assert outputs['new']['ticks'] == outputs['baseline']['ticks'] == 37
    ground = [z for z in chains['new']['G'] if z['event'] == 'rune_transfer_dash_refused' and z['frame'] == 5590]
    assert ground and ground[0]['opposite_in_flight']
    active = chains['new']['A']
    refused = next(z for z in active if z['event'] == 'rune_transfer_dash_refused' and z['frame'] == 20929)
    assert refused['active'] and refused['decision_pending'] and refused['opposite_in_flight']
    selected = [next(z for z in active if z['event'] == 'b2_selected' and z['frame'] == f) for f in [20928, 20929, 20930]]
    assert all(z['stage'] == 'active' and z['move'] == selected[0]['move'] for z in selected)
    assert any(z['event'] == 'rune_transfer_dash_checked' and z['frame'] == 20930 for z in active)
    assert wires['new']['A'][20929] == dict(mask=2097152, owner='chain', target_frame=20931)
    assert wires['new']['A'][20930] == dict(mask=2097156, owner='chain', target_frame=20932)
    assert wires['new']['G'][5590] == dict(mask=1048576, owner='plan', target_frame=5592)
    assert wires['baseline']['A'][20929]['mask'] == 2097156
    assert wires['baseline']['G'][5590]['mask'] == 2097156
    changes = {q: [dict(f=f, new=w, baseline=wires['baseline'][q][f])
                   for f, w in wires['new'][q].items() if w != wires['baseline'][q][f]] for q in ['G', 'A']}
    result = dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(), source=outputs['new']['source'],
                  source_and_inputs_unchanged=True, matching_frame_sets=True, matching_control_profiles=True,
                  actual_cleanup_verified=True, source_review_accepted=True, finite_measurement_valid=True,
                  finite_branch_evidence_accepted=True, scoped_engineering_timing_pass=False,
                  formal_timing_completed=True, performance_budget_pass=False, runtime_delta=runtime_delta,
                  full_scheduling_gate_pass=False, live_released=False, user_live_pause_retained=True,
                  outputs=outputs, actual_wire_differences=changes,
                  measured_delta_ms={k: outputs['new'][k] - outputs['baseline'][k] for k in ['tick_p50_ms', 'tick_p99_ms']},
                  production_evidence=dict(ground_refusal=ground[0], active_wait=refused,
                                           active_same_run=True, retry_actual_send=True,
                                           measured_controller_unpatched=True, before_send_sent_agree=True),
                  observed_cost_regression=dict(window='G', new_owners=outputs['new']['windows']['G']['actual_owners'],
                      baseline_owners=outputs['baseline']['windows']['G']['actual_owners'],
                      new_over_frame_budget=25, baseline_over_frame_budget=0,
                      scope='Different actions after refused impulse lead to ordinary planner fallback. This is observed total cost, not isolated guard overhead; no performance pass claimed.'),
                  baseline_resource_interruption=dict(artifact=str(A/'P_BASELINE/EXECUTION.json'),
                      failed_before_A_started=True, completed_G_retained=True,
                      blockers=read(A/'P_BASELINE/RESOURCE_A.json')['blockers'],
                      missing_A_only_completed_in=str(A/'P_BASELINE_A'), changed_resource_gate=False),
                  limitations=['37 ticks per arm; percentiles descriptive only, not a scheduling pass.',
                      'Synthetic hero and recorded enemies; one prior A input is synthetic and restored before timing.',
                      'Actual async plan/field workers and production geometry/before_send/sent; no live game.',
                      'Source changes actions and trajectories; cost delta is not isolated helper cost.',
                      'Rule misses 6/17 historical reverse dashes and delays 4 historically correct ones; no live direction or HP improvement established.',
                      'Original active-air all-owner scan independently component-verified; no new physical damage claim.',
                      'Five operational keys unresolved by adapter; real CPU/priority/throttling read back separately.'])
    (A/'ROOT_P_AUDIT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps(dict(outputs={k:{n:v for n,v in o.items() if n!='windows'} for k,o in outputs.items()},
                          delta=result['measured_delta_ms'], wire_differences={k:len(v) for k,v in changes.items()},
                          cleanup=True, finite_measurement_valid=True, performance_budget_pass=False,
                          full_scheduling=False), ensure_ascii=False))


if __name__ == '__main__':
    main()
