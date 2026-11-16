from pathlib import Path
import collections
import datetime as dt
import hashlib
import json
import os
import sys

import psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/w13_walk179L2_20261106T000950Z_1263e9e3'
T=B/'sol/demos/w13_walk179L2_20261106T000950Z_1263e9e3'
R=T/'run'
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'brain'))
from ssbot.record.recorder import RecordingReader
from ssbot.tools.forum_aa_v2 import verify_episode
from ssbot.combat.knife_chain_format import MASK_NAMES

def readj(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(s) for s in p.read_text(encoding='utf-8-sig').splitlines() if s]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf-8') as fp:json.dump(d,fp,ensure_ascii=False,indent=2);fp.write('\n')
def keys(m):return '+'.join(n for n,b in MASK_NAMES.items() if int(m or 0)&b) or '0'
assert not readj(B/'sol/STATUS.json')['live_or_budget_running']
before={str(p):sha(p) for p in T.rglob('*') if p.is_file()}
out=A/'verification';out.mkdir()
(out/'attempts_i0.jsonl').write_bytes((R/'attempts_i0.jsonl').read_bytes())
verified=verify_episode(out,0,0,production=False)
assert before=={str(p):sha(p) for p in T.rglob('*') if p.is_file()}
attempt=rows(R/'attempts_i0.jsonl')[0]
state=list(RecordingReader(attempt['recording']).states(attempt['f_wake'],attempt['f_end']))
chain=rows(R/'decisions_i0.chain.jsonl');dec=rows(R/'decisions_i0.jsonl')
trace=rows(R/'measurement_i0_e0.jsonl')
manifest=readj(R/'measurement_manifest_i0_e0.json')
counts=collections.Counter(d.get('event') for d in chain)
events=[];transitions=[];previous={};timeline=[];contacts=[]
for s in state:
    f=s['f'];h=s.get('hero') or {};en=[]
    for e in s.get('ents') or []:
        if e.get('type_key')!='Song Heavy Sentry':continue
        cf=next((v for v in e.get('fsms',[]) if v.get('name')=='Control'),{})
        en.append({'iid':e['iid'],'x':e['pos'][0],'y':e['pos'][1],'hp':e.get('hp'),'state':cf.get('state'),'t':cf.get('t'),'flipX':e.get('flipX')})
        signature=cf.get('state')
        if previous.get(e['iid'])!=signature:
            transitions.append({'f':f,**en[-1]});previous[e['iid']]=signature
    for ev in s.get('ev') or []:
        if ev.get('k') in ('hit','damage','hp'):
            events.append({'f':f,**ev})
    if 2738<=f<=2804 or f in (2649,2680,2687,2712,2720,2753,2761):
        timeline.append({'f':f,'fc':s.get('fc'),'fs':s.get('fs'),'hp':h.get('health'),
                         'pos':h.get('pos'),'vel':h.get('vel'),'clip':(h.get('anim')or{}).get('clip'),
                         'can':h.get('can'),'tm':{k:(h.get('tm')or{}).get(k) for k in ['jump_steps','atk_cd','atk_t','dash_cd']},
                         'input':s.get('input'),'act':s.get('act'),'enemies':en,
                         'events':[ev for ev in s.get('ev')or[] if ev.get('k') in ('fsm','hit','damage','hp')]})
    if f in (2753,2761,2788,2792,2793,2795,2800,2801):
        contacts.append({'f':f,'hero_box':h.get('box'),'hero_clip':(h.get('anim')or{}).get('clip'),
                         'hero_pos':h.get('pos'),'enemy':[{k:e.get(k) for k in ['iid','pos','vel','fsms','colliders']} for e in s.get('ents')or[] if e.get('type_key')=='Song Heavy Sentry']})
bounces=[e for e in chain if e.get('event')=='b2_real_bounce_handback']
hp_loss=[e for e in chain if e.get('event')=='b2_hp_loss']
issues=[e for e in chain if e.get('event') in ('b2_controller_defect','b2_learning_stop')]
vault_events=[e for e in chain if 'vault' in str(e.get('event','')).lower()]
jumps=[e for e in transitions if 'jump' in str(e.get('state','')).lower()]
selected=[e for e in chain if e.get('event') in ['target_transfer_blade','target_transfer_bounce_goal','b2_recovery','b2_failure_exposure','rune_transfer_rejected','b2_strike_accepted','b2_real_bounce_handback','chain_interrupted']]
window=verified['audit']['window'];metrics=verified['audit'].get('metrics',{})
report={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'tag':T.name,'runtime_source':'1263e9e398859b0fa98e6d3141ac955288e05059',
 'execution_head':readj(T/'contract.json')['execution_head'],'actual_worker_pid':manifest['runtime_before']['pid'],
 'engineering_only':True,'original_files_unchanged':True,'original_files_sha256':before,
 'episode_verified_complete':verified['complete'],'episode_errors':verified['errors'],
 'configuration_complete':manifest['configuration_complete'],'configuration_unresolved':manifest.get('unresolved'),
 'input_path':readj(R/'b2_input_path_i0.json'),'trace':verified['trace'],'continuity':verified['continuity'],
 'fight_window':window,'metrics':metrics,'main_ticks':verified['main_ticks'],
 'first_loss':hp_loss,'damage_and_target_hit_events':events,'chain_event_counts':dict(counts),
 'selected_events':selected,'controller_defects_or_learning_stops':issues,
 'walking_vault':{'events':vault_events,'jump_fsm_entries':jumps,'covered':bool(vault_events),'accepted':False},
 'moving_stomp':{'accepted':False,'scope':'row support requires branch-specific audit, no Walk success inferred from generic bounces'},
 'new_slam_instance_fix':{'accepted_live':False,'scope':'no same-iid second-Slam admission identified; not inferred from source/P or first Slam'},
 'task178':'previous finite acceptance retained, this is not a replacement178trial',
 'bounces':bounces,'status':'firstloss stopped; causality review needed; do not retry',
 'known_causal_prefix':'2761 actual bounce on335476 then target335470 already SlamAntic; rune_transfer.air returns external-step blocked2793; ordinary planner takes over,2801 actual2HP from335470 SlamCollider1. HP exposure oldsourceMove is responsibility only, not collider attribution.',
 'actual_cleanup':str(A/'ROOT_CLEANUP.json'),'next_game_gate':False}
write(A/'ROOT_EVENT_AUDIT.json',report)
write(A/'ROOT_ACTUAL_TIMELINE.json',{'scope':'actual raw states/events, no model injection','enemy_control_transitions':transitions,'states':timeline,'ordinary_decisions':[d for d in dec if isinstance(d.get('f'),int) and 2738<=d['f']<=2804],'chain_events':[d for d in chain if isinstance(d.get('frame'),int) and 2738<=d['frame']<=2804 and d.get('event')not in ('state_sample','planner_input','row_registered','b2_nominal_path')],'ticks':[d for d in trace if d.get('kind') in ('tick','action') and isinstance(d.get('f'),int) and 2738<=d['f']<=2804]})
write(A/'ROOT_SELECTED_CONTACTS.json',contacts)
print(json.dumps({'complete':verified['complete'],'errors':verified['errors'],'configuration_complete':manifest['configuration_complete'],'main_ticks':verified['main_ticks'],'window':window,'hp_loss':hp_loss,'bounces':bounces,'walking_vault_event_count':len(vault_events),'jumpFSMentries':jumps,'metrics_keys':list(metrics)},ensure_ascii=False)[:4500])
