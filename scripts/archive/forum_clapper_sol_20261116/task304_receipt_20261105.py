import bisect
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

import psutil
import numpy as np

B = Path('C:/ssbot/data/m2_play/clapper_plan')
W = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
R = B / 'analysis/task179_1263e9e3_20261105'
O = B / 'opus/review179/l1_304'
proc = psutil.Process()
proc.cpu_affinity(list(range(24, 32)))
proc.nice(psutil.IDLE_PRIORITY_CLASS)
sys.dont_write_bytecode = True
sys.path.insert(0, str(W / 'brain'))
from ssbot.knowledge import kinematics as K
from ssbot.combat.knife_chain_deadline import FRAME_NS, PREVIOUS_STATE_WINDOW_NS, SEND_RESERVE_NS

def readj(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def jsonlines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

audit = readj(R / 'p_v2/ROOT_P_AUDIT.json')
assert audit['integrity_pass'] and audit['functional_path_pass']
expect = readj(O / 'SCHED304.json')
trace = jsonlines(R / 'p_v2/handled_to_new_slam/measurement_trace.jsonl')
ticks = {d['f']: d for d in trace if d['kind'] == 'tick'}
actions = {d['f']: d for d in trace if d['kind'] == 'action'}
frames = sorted(ticks)
assert frames == list(range(2524, 2736)) and set(ticks) == set(actions)
receives = {}
for d in jsonlines(B / 'sol/demos/w13_walk179_20261105T222716Z_8f9e9629/run/measurement_i0_e0.jsonl'):
    if d['kind'] == 'receive':
        receives.setdefault(d['f'], d['recv_ns'])
rf = sorted(receives)
rn = [receives[f] for f in rf]
assert rn == sorted(rn)
cost = {f: ticks[f]['tick_end_ns'] - ticks[f]['tick_start_ns'] for f in frames}
send = {f: actions[f]['send_done_ns'] - ticks[f]['tick_start_ns'] for f in frames}
assert all(0 <= send[f] <= cost[f] and actions[f]['target_frame'] == f + 2 for f in frames)
mask = {f: int(actions[f]['mask']) for f in frames}
pre = {}
for d in jsonlines(R / 'p_v2/handled_to_new_slam/decisions_i0.chain.jsonl'):
    if d.get('event') == 'transport_sent' and d['frame'] in (2522, 2523):
        pre[d['target']] = int(d['mask'])
assert set(pre) == {2524, 2525}

def schedule(wake_ms, extra=None):
    free = -float('inf')
    last = 2523
    rows = []
    while last < frames[-1]:
        available = [f for f in frames if f > last and receives[f] <= free]
        f = max(available) if available else last + 1
        start = max(free, receives[f]) + wake_ms * 1e6 + (extra or {}).get(f, 0) * 1e6
        sent = start + send[f]
        newest = rf[bisect.bisect_right(rn, sent) - 1]
        result = None
        for target in range(f + 2, f + 11):
            deadline = min(receives[target - 2] + PREVIOUS_STATE_WINDOW_NS + FRAME_NS,
                           receives[target - 1] + PREVIOUS_STATE_WINDOW_NS)
            if newest < target and sent + SEND_RESERVE_NS < deadline:
                result = (target, (deadline - sent - SEND_RESERVE_NS) / 1e6)
                break
        assert result is not None
        rows.append({'f': f, 'target': f + 2, 'applied': result[0], 'slack': result[1],
                     'skipped': list(range(last + 1, f)), 'start_lag': (start - receives[f]) / 1e6})
        free, last = start + cost[f], f
    return rows

def desired(rows, forced=None):
    packages = [(f, f, m) for f, m in sorted(pre.items())]
    packages += [(r['target'], r['applied'], mask[r['f']]) for r in rows]
    if forced:
        target, late = forced
        packages = [(t, t if t < target else max(t, target + late), m) for t, _, m in packages]
    return np.asarray([max((t, m) for t, applied, m in packages if applied <= f)[1]
                       for f in range(2525, 2738)], dtype=np.int64)

hf = K.HoldState.from_hf(ticks[2524]['hold_filter'])
ontime = [{'f': f, 'target': f + 2, 'applied': f + 2} for f in frames]
base_latch, _ = K.hold_filter(desired(ontime), hf)
variants = {}
for name in ('idle_p50', 'idle_p99', 'idle_max'):
    wake = expect['variants'][name]['wake_ms']
    rows = schedule(wake)
    late = [r for r in rows if r['applied'] > r['target']]
    skipped = [s for r in rows for s in r['skipped']]
    assert len(rows) == expect['variants'][name]['ticks']
    assert skipped == expect['variants'][name]['skipped']
    assert [(r['f'], r['applied'] - r['target']) for r in late] == [(r['g'], r['late']) for r in expect['variants'][name]['late']]
    latches, _ = K.hold_filter(desired(rows), hf)
    changed = np.flatnonzero(np.asarray(latches).reshape(-1) != np.asarray(base_latch).reshape(-1))
    for r in rows:
        if r['f'] in (2683, 2699, 2720):
            assert abs(r['slack'] - expect['variants'][name]['key_slack'][str(r['f'])]['slack_ms']) < .00006
    variants[name] = {'ticks': len(rows), 'late_packets': len(late), 'skipped': skipped,
                      'latched_difference_count': len(changed),
                      'critical': [r for r in rows if r['f'] in (2683, 2699, 2720)]}
    if name != 'idle_max':
        assert not late and not skipped and len(changed) == 0
repeated = {}
for f in (2564, 2696, 2704):
    h = ticks[f]['hold_filter']
    assert mask[f] == mask[f-1] == h['desired'] == h['latched']
    assert not any(h['pending']) and ticks[f]['inflight_prefix'] == [mask[f]]
    for delay in (1, 2):
        latch, _ = K.hold_filter(desired(ontime, (f + 2, delay)), hf)
        assert np.array_equal(latch, base_latch)
    repeated[f] = {'mask': mask[f], 'delay1_delay2_latched_equal': True}
late_results = {}
for delay in (1, 2):
    path = O / f'late{delay}/RESULT.json'
    result = readj(path)
    assert result['exception'] is None and result['foreign'] == [] and result['forced_planner_ticks'] == []
    assert result['knife_head'] == 'c775a51417fcea98adf770fa2c86fd754d66fdc1'
    assert result['knife_brain_dirty'] == '' and result['divergence_tick'] == 2683 and result['synthetic_from'] == 2685
    assert result['late']['late'] == [2685, delay]
    assert all(sha(W / 'brain/ssbot' / rel) == val for rel, val in result['source_sha256'].items())
    rows = {r['f']: r for r in result['rows']}
    for f, key in ((2683, '0'), (2699, 'J'), (2715, 'D'), (2720, 'A+D')):
        assert rows[f]['keys'] == key and rows[f]['owner'] == 'slam'
    assert rows[2722]['clip'] == 'DownSlash'
    late_results[delay] = {'path': str(path), 'source_hashes_match': True, 'critical_packets_unchanged': True,
                           'first_model_hurt': result['first_model_hurt'], 'physical_hit_proven': False}
receipt = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'delivery': 304, 'task': 179,
           'source': audit['source'], 'source_changed': False, 'reviewer': 'Sol ordinary independent artifact/math audit',
           'pid': proc.pid, 'cpu_affinity': proc.cpu_affinity(), 'priority': proc.nice(),
           'accepted': True, 'scope': 'four slow packets finite serial/HF classification, engineering gate input only',
           'variants': variants, 'repeated': repeated, 'late2683': late_results,
           'whole_route_guarantee': False, 'limitations': [
               'real receive timing from old live path; alternative route/GIL may alter receive timestamps',
               'idle_p50/p99 are empirical scenario costs, not joint probability or future service guarantee',
               'idle_max repeated every tick shows skipped and late packets, retained as stress',
               'strict no-hit/modelhurt retained; D-held hit proxy omits actual DownSlash lifetime',
               '2683-late costs were E/offline and not separately formal-P measured; finite functional tolerance only',
               'legacy slam has original dual-enemy admission, not B2 candidate certification'],
           'new_game_gate': False, 'inputs': {str(p): sha(p) for p in [O/'SCHED304.json',O/'sched304.py',O/'replay_late304.py',R/'p_v2/ROOT_P_AUDIT.json']}}
dest = R / 'OPUS304_RECEIPT.json'
assert not dest.exists()
dest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
compact = {k: {q: v[q] for q in ['ticks','late_packets','skipped','latched_difference_count']} for k,v in variants.items()}
print(json.dumps({'receipt': str(dest), 'accepted': True, 'variants': compact}, ensure_ascii=False))
