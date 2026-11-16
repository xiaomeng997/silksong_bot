"""Read-only recent w13 jump/idle displacement census. No policy execution."""
import bisect
import csv
import hashlib
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psutil

B = Path('C:/ssbot/data/m2_play/clapper_plan')
OUT = B / 'analysis/cluster_bait_space_20261105'
READER_ROOT = Path('C:/Users/Meng/.codex/worktrees/forum-watch-approved-5df/silksong_bot')
sys.path.insert(0, str(READER_ROOT / 'brain'))
from ssbot.record.recorder import RecordingReader

IDLE = {'Idle', 'Walk'}
START = {'Jump Antic': 'jump', 'Cast Slam Antic': 'jump_cast'}
DEAD = {'Dead', 'Dormant', 'Inactive', 'Set Pos', 'Init'}


def dump(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def atomic_status(change):
    p = B / 'sol/STATUS.json'
    s = json.loads(p.read_text(encoding='utf-8'))
    change(s)
    q = p.with_name(f'STATUS.option1.{os.getpid()}.tmp')
    dump(q, s)
    os.replace(q, p)


def control(e):
    return next((x['state'] for x in e.get('fsms', []) if x.get('name') == 'Control'), '')


def body(e):
    vv = []
    for c in e.get('colliders', []):
        if c.get('enabled') and c.get('damage') and c.get('name', '').startswith('Song Heavy Sentry'):
            vv.extend(c.get('verts_world', [])[::2])
    return [min(vv), max(vv)] if vv else None


def compact(s):
    cs = {}
    for e in s.get('ents') or []:
        if e.get('type_key') != 'Song Heavy Sentry' or e.get('is_dead') or e.get('hp', 0) <= 0 or e.get('hidden'):
            continue
        st = control(e)
        if st in DEAD:
            continue
        cs[e['iid']] = {'x': e['pos'][0], 'y': e['pos'][1], 'vx': e.get('vel', [None])[0],
                        'state': st, 'hp': e.get('hp'), 'body': body(e)}
    h = s.get('hero')
    return {'f': s['f'], 'fc': s.get('fc'), 'dt': s.get('dt'),
            'hx': h['pos'][0] if h else None, 'hy': h['pos'][1] if h else None,
            'hbox': h.get('box') if h else None, 'cs': cs}


def distribution(vals):
    vals = sorted(vals)
    n = len(vals)
    if not n:
        return {'n': 0}
    q = lambda p: vals[max(0, math.ceil(n*p)-1)]
    return {'n': n, 'p50': q(.5), 'p90': q(.9), 'p95': q(.95), 'p99': q(.99),
            'max': vals[-1], 'min': vals[0],
            'observed_max_population_coverage_95_lower_if_iid': .05**(1/n)}


def run():
    p = psutil.Process()
    p.cpu_affinity(list(range(24, 32)))
    p.nice(psutil.IDLE_PRIORITY_CLASS)
    OUT.mkdir(parents=True, exist_ok=True)
    stat = json.loads((B/'sol/STATUS.json').read_text(encoding='utf-8'))
    if stat.get('live_or_budget_running'):
        raise RuntimeError('Game/P active; no census started')
    job = {'pid': p.pid, 'created': p.create_time(), 'kind': 'E raw recording census, no planner/JIT/game',
           'script': str(Path(__file__)), 'out': str(OUT), 'affinity': p.cpu_affinity(),
           'started': datetime.now(timezone.utc).isoformat()}
    atomic_status(lambda s: s.update(own_offline_jobs=[*s.get('own_offline_jobs', []), job]))
    try:
        inventory = {}
        errors = []
        for ap in sorted((B/'sol/demos').glob('w13*/run/attempts_i*.jsonl')):
            for line_no, line in enumerate(ap.read_text(encoding='utf-8').splitlines(), 1):
                try:
                    a = json.loads(line)
                    rp = Path(a['recording'])
                    key = str(rp.resolve()).lower()
                    inventory.setdefault(key, {'recording': str(rp), 'dataset':'recent_w13', 'attempts': []})['attempts'].append(
                        {'file': str(ap), 'line': line_no})
                except Exception as e:
                    errors.append({'file': str(ap), 'line': line_no, 'error': repr(e)})
        # Only old TRAIN recordings already used by the current behavior table.
        # No AA, fresh/holdout collection, or new recording is opened.
        source_path = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/knowledge/1.0.30000/enemies/forum/ChoirClapper.json')
        src = json.loads(source_path.read_text(encoding='utf-8'))
        grouped = {}
        for ss in src['sources']:
            if ss['subject'].endswith(('(2)', '(3)')):
                k = (ss['path'], ss['f0'], ss['f1'])
                grouped.setdefault(k, []).append(ss)
        for (path, _, f1), group in grouped.items():
            rp = Path(path)
            key = str(rp.resolve()).lower()
            item = inventory.setdefault(key, {'recording':str(rp), 'dataset':'existing_behavior_training',
                                              'attempts':[], 'ranges':[]})
            item['ranges'].append([min(s['first_f'] for s in group), f1])
        all_events = []
        for ri, item in enumerate(inventory.values()):
            rp = Path(item['recording'])
            if not rp.is_dir():
                errors.append({'recording': str(rp), 'error': 'missing'})
                continue
            r = RecordingReader(rp)
            # These are existing, indexed TRAIN recordings, never AA/holdout.
            if r.meta.get('profile') != 'TRAIN':
                errors.append({'recording': str(rp), 'error': 'non-TRAIN skipped'})
                continue
            ranges = sorted(set(map(tuple,item.get('ranges', [(None,None)]))))
            frames = [compact(s) for f0,f1 in ranges for s in r.states(f0,f1,keys=('f','fc','dt','hero','ents'))]
            item['frames'] = len(frames)
            item['drops'] = r.meta.get('drops')
            item['rebuilt_indexes'] = r.rebuilt
            item['meta_sha256'] = hashlib.sha256((rp/'meta.json').read_bytes()).hexdigest()
            for i in range(1, len(frames)):
                a0, a = frames[i-1], frames[i]
                if len(a['cs']) != 2 or a['hx'] is None or a['fc'] is None or a['f'] != a0['f']+1:
                    continue
                for jid, je in a['cs'].items():
                    if je['state'] not in START or jid not in a0['cs'] or a0['cs'][jid]['state'] == je['state']:
                        continue
                    wid = next(x for x in a['cs'] if x != jid)
                    we = a['cs'][wid]
                    if we['state'] not in IDLE:
                        continue
                    sign = 1 if a['hx'] > we['x'] else -1
                    outside = (a['hx']-we['x'])*(a['hx']-je['x']) > 0
                    body_gap = None
                    if je['body'] and we['body']:
                        lo, hi = sorted([je, we], key=lambda e:e['x'])
                        body_gap = hi['body'][0]-lo['body'][1]
                    rows = []
                    takeoff = land = end = None
                    break_reason = None
                    prev_f = a['f']-1
                    for z in frames[i:]:
                        if z['f'] != prev_f+1:
                            break_reason = 'missing STATE'
                            break
                        prev_f = z['f']
                        if jid not in z['cs'] or wid not in z['cs'] or z['hx'] is None or z['fc'] is None:
                            break_reason = 'actor/hero absent/dead'
                            break
                        j, w = z['cs'][jid], z['cs'][wid]
                        elapsed = (z['fc']-a['fc'])*.02
                        if elapsed < 0:
                            break_reason = 'fixed clock reset'
                            break
                        rows.append({'f':z['f'], 'fc':z['fc'], 't':elapsed, 'jx':j['x'], 'wx':w['x'],
                                     'hx':z['hx'], 'hy':z['hy'], 'js':j['state'], 'ws':w['state'],
                                     'advance': sign*(w['x']-we['x']), 'wbody':w['body'], 'jbody':j['body']})
                        if takeoff is None and j['state'] in {'Jump', 'Air', 'Cast Jump'}:
                            takeoff = len(rows)-1
                        if takeoff is not None and land is None and j['state'] == 'Slam 2':
                            land = len(rows)-1
                        if land is not None and end is None and j['state'] in IDLE:
                            end = len(rows)-1
                        if end is not None or elapsed >= 2.6:
                            break
                    ev = {'recording':str(rp), 'dataset':item['dataset'], 'jump_iid':jid, 'other_iid':wid, 'family':START[je['state']],
                          'f0':a['f'], 'fc0':a['fc'], 'jumper_x0':je['x'], 'other_x0':we['x'],
                          'hero_x0':a['hx'], 'hero_y0':a['hy'], 'other_state0':we['state'],
                          'outward_sign':sign, 'outside':outside, 'center_gap0':abs(je['x']-we['x']),
                          'body_gap0':body_gap, 'horizons':{}, 'break_reason':break_reason, 'rows':rows}
                    endpoints = {'aim_lock':takeoff, 'landing':land, 'attack_end':end}
                    for name, ix in endpoints.items():
                        if ix is None:
                            continue
                        sl = rows[:ix+1]
                        ev['horizons'][name] = metric(sl, a, we, sign)
                    if takeoff is not None:
                        t0 = rows[takeoff]['t']
                        ev['retreat_during_aim'] = max(sign*(z['hx']-a['hx']) for z in rows[:takeoff+1])
                        for dur in [.2,.4,.6,.8]:
                            ix = next((k for k,z in enumerate(rows) if z['t'] >= t0+dur-1e-6), None)
                            if ix is not None:
                                ev['horizons'][f'aim_plus_{dur:.1f}'] = metric(rows[:ix+1], a, we, sign)
                    for dur in [.5,1.,1.5,2.]:
                        ix = next((k for k,z in enumerate(rows) if z['t'] >= dur-1e-6), None)
                        if ix is not None:
                            ev['horizons'][f't_{dur:.1f}'] = metric(rows[:ix+1], a, we, sign)
                    all_events.append(ev)
            print(json.dumps({'recording':ri+1, 'of':len(inventory), 'events_so_far':len(all_events)}, ensure_ascii=False), flush=True)
        dump(OUT/'events.json', all_events)
        dump(OUT/'inventory.json', {'recordings':list(inventory.values()),'errors':errors, 'job':job,
                                  'reader_root':str(READER_ROOT), 'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        cohorts = {
            'all_idle_walk_at_aim':lambda e:True,
            'idle_at_aim':lambda e:e['other_state0']=='Idle',
            'walk_at_aim':lambda e:e['other_state0']=='Walk',
            'outside':lambda e:e['outside'],
            'outside_body_gap_le_1':lambda e:e['outside'] and e['body_gap0'] is not None and e['body_gap0']<=1.,
            'outside_center_gap_le_6':lambda e:e['outside'] and e['center_gap0']<=6.,
            'outside_retreat_ge_1':lambda e:e['outside'] and e.get('retreat_during_aim',0)>=1.,
        }
        summaries = {}
        for name, filt in cohorts.items():
            ee = [e for e in all_events if filt(e)]
            horizons = sorted({h for e in ee for h in e['horizons']})
            summaries[name] = {'events':len(ee), 'by_family':dict(Counter(e['family'] for e in ee)), 'horizons':{}}
            for h in horizons:
                hh = [e['horizons'][h] for e in ee if h in e['horizons']]
                summaries[name]['horizons'][h] = {k:distribution([x[k] for x in hh]) for k in
                    ['max_advance','net_advance','elapsed_physical_s']}
                summaries[name]['horizons'][h]['all_idle_walk_fraction'] = (
                    sum(x['all_idle_walk'] for x in hh)/len(hh) if hh else None)
        strata={}
        for dataset in ['recent_w13','existing_behavior_training']:
            for fam in ['jump','jump_cast','both']:
                for c,filt in cohorts.items():
                    ee=[e for e in all_events if e['dataset']==dataset and (fam=='both' or e['family']==fam) and filt(e)]
                    key=f'{dataset}/{fam}/{c}'
                    strata[key]={'events':len(ee),'horizons':{}}
                    for h in sorted({h for e in ee for h in e['horizons']}):
                        hh=[e['horizons'][h] for e in ee if h in e['horizons']]
                        strata[key]['horizons'][h]={
                            'max_advance':distribution([x['max_advance'] for x in hh]),
                            'max_advance_if_always_idle_walk':distribution([x['max_advance'] for x in hh if x['all_idle_walk']]),
                            'time':distribution([x['elapsed_physical_s'] for x in hh])}
        dump(OUT/'summary.json', summaries)
        dump(OUT/'strata.json',strata)
        flat=[]
        for e in all_events:
            for h,x in e['horizons'].items():
                flat.append({k:e[k] for k in ['recording','f0','jump_iid','other_iid','family','other_state0','outside','center_gap0','body_gap0']} |
                            {'horizon':h} | x)
        if flat:
            with (OUT/'events.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
        print(json.dumps({'complete':True,'recordings':len(inventory),'events':len(all_events),'errors':errors,
                          'summary':{k:v['events'] for k,v in summaries.items()}},ensure_ascii=False),flush=True)
    finally:
        atomic_status(lambda s:s.update(own_offline_jobs=[x for x in s.get('own_offline_jobs',[]) if x.get('pid')!=os.getpid()]))


def metric(rows, start, other, sign):
    return {'f_end':rows[-1]['f'], 'fc_end':rows[-1]['fc'], 'elapsed_physical_s':rows[-1]['t'],
            'max_advance':max(0.,max(z['advance'] for z in rows)), 'net_advance':rows[-1]['advance'],
            'all_idle_walk':all(z['ws'] in IDLE for z in rows),
            'other_states':'|'.join(dict.fromkeys(z['ws'] for z in rows))}


if __name__ == '__main__':
    run()
