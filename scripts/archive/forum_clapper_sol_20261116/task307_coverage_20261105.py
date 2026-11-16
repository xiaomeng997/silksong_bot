from pathlib import Path
import sys,json,hashlib,collections,datetime as dt
B=Path('C:/ssbot/data/m2_play/clapper_plan');TAG='w13_guard179L3_20261106T012400Z_5df8711e'
A=B/'analysis'/TAG;T=B/'sol/demos'/TAG;W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'brain'))
from ssbot.record.recorder import RecordingReader
def r(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x]
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report=r(A/'ROOT_EVENT_AUDIT.json');tl=r(A/'ROOT_ACTUAL_TIMELINE.json');c=r(T/'contract.json');m=r(T/'run/measurement_manifest_i0_e0.json');ch=rows(T/'run/decisions_i0.chain.jsonl')
actual=dict(m['code']['files_sha256']);actual['versions.lock']=m['code']['runtime_identity_files'][str(W/'versions.lock')]
assert actual==c['files'];assert not r(B/'sol/STATUS.json')['live_or_budget_running']
a=rows(T/'run/attempts_i0.jsonl')[0];states=list(RecordingReader(a['recording']).states(a['f_wake'],a['f_end']))
def compact(s):
 h=s.get('hero')or{}
 return {'f':s['f'],'hp':h.get('health'),'hero_pos':h.get('pos'),'hero_vel':h.get('vel'),'clip':(h.get('anim')or{}).get('clip'),'act':s.get('act'),'enemies':[{'iid':e['iid'],'pos':e.get('pos'),'Control':next((v for v in e.get('fsms',[]) if v.get('name')=='Control'),{})} for e in s.get('ents',[]) if e.get('type_key')=='Song Heavy Sentry'],'events':[e for e in s.get('ev')or[] if e.get('k') in ('hit','damage','hp')]}
sel={2515,2543,2550,2571,2579,2586,2599,2600,2601,2602,2603,2604,2619,2621,2623,2645,2675,2679,2682,2683,2685,2686,2694,2699,2704,2706,2713,2715,2717,2718,2720,2721}
state_sel=[compact(s) for s in states if s['f'] in sel]
dashj=[compact(s) for s in states if s['f']<=2721 and (int(((s.get('act')or{}).get('hf')or{}).get('latched',0))&5)==5]
byf={s['f']:s for s in states}
for x in dashj:
 prev=byf.get(x['f']-1)
 if prev is not None:
  pm=int(((prev.get('act')or{}).get('hf')or{}).get('latched',0));nm=int(x['act']['hf']['latched'])
  x['previous_latched']=pm;x['rising_dash']=not bool(pm&4) and bool(nm&4);x['rising_J']=not bool(pm&1) and bool(nm&1)
apps=[x for x in ch if x['event']=='application_first_seen'];receipts=[x for x in ch if x['event']=='b2_receipt']
app_hist=dict(collections.Counter(x['applied']-x['target'] for x in apps))
phases=[];prev=None
for x in ch:
 if x['event']=='chain_selected' and 2675<=x.get('frame',-1)<=2718:
  if x['link']!=prev:phases.append({'frame':x['frame'],'link':x['link']});prev=x['link']
coverage={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':c['source'],'execution_head':c['execution_head'],'source_manifest_matches_contract':True,'source_files':len(actual),'oracle_dll_sha256':m['code']['runtime_identity_files']['C:\\ssbot\\game\\train\\BepInEx\\plugins\\SsOracle\\SsOracle.dll'],
 'walk_vault':{'natural_opportunities':1,'takeoff_frame':2675,'source_jump':335470,'walking_target':335476,'target_entry':'stomp','actual_route_phases':phases,'legacy_vault_named_events':0,'actual_facehook_start':2685,'actual_needle_hit':2694,'actual_dash_damage':2706,'target_evade_scuttle':2699,'DownSlash_after_hook':False,'over_target':False,'real_downslash_bounce_handback':False,'accepted':False,'note':'one actual transfer attempt toward Walk target, not zero opportunity; no walking vault success'},
 'moving_stomp':{'actual_Walk_transfer_attempts':1,'selected_Walk_supported_strike_rows':0,'actual_Walk_DownSlash':0,'accepted':False},
 'new_slam_instance_fix':{'actual_same_iid_SlamAntic':[x for x in tl['enemy_control_transitions'] if x['state']=='Slam Antic'],'second_antic_2571_actual_B2_press_hit':[2579,2586],'legacy_script_reopening_demonstrated':False,'accepted_live':False,'note':'two physical Slam instances exist; second handled by active B2, not evidence for legacy closed-marker regression'},
 'guard_recovery':{'frame':2621,'event':'rune_transfer_dash_refused','actual_final_owner':'plan','actual_left_applied_from':2623,'no_loss_until':2720,'new_antic_deadline_guard_uniquely_triggered':False,'note':'actual existing locked-motion refusal and ordinary handback observed; not isolated proof of new Slam deadline guard'},
 'simultaneous_dash_jump':{'actual_latched_frames':[s['f'] for s in dashj],'interpreted_as_307_extreme_lag_equivalence':False,'scope':'natural observed states only; does not certify all simultaneous-input priority'},
 'receipts':{'n':len(receipts),'kind_histogram':dict(collections.Counter(x['kind'] for x in receipts)),'lag_histogram':dict(collections.Counter(x['lag'] for x in receipts)),'application_first_seen':len(apps),'application_lag_histogram':app_hist,'not_action_proof':True},
 'task178':'existing finite live acceptance complete, unchanged','actual_cleanup':True,'next_game_gate':False,'same_cause_retry':False}
write(A/'ROOT_COVERAGE.json',coverage)
write(A/'ROOT_CAUSAL_PREFIX.json',{'scope':'actual states/events only; no counterfactual NPC simulation','states':state_sel,'simultaneous_dash_jump_states':dashj,'entry_to_exit':[x for x in ch if 2675<=x.get('frame',-1)<=2721 and x['event'] in ('target_entry_attack_bound','target_transfer_blade','b2_jump_dispatch_clock','b2_jump_start_seen','b2_hook_target_checked','b2_hook_start_sent','b2_hook_start_seen','rune_transfer_rejected','b2_recovery','b2_failure_exposure','b2_hp_loss')],
 'actual_cause_limit':'2721 rawdamage names jumping335470 while Air; specific collider unavailable, do not relabel as SlamCollider1. Walking335476 retreat observed after needlehit; no proof that needle caused retreat.'})
report['walking_vault'].update(opportunities=1,attempt_route='rune_transfer aimed facehook toward Walk target',actual_facehook_start=2685,actual_needle_hit=2694,real_overhead_downslash=False,accepted=False)
report['new_slam_instance_fix']=coverage['new_slam_instance_fix'];report['status']='first2HP loss2721; actualcleanup/integrity pass; Walk-target facehook never reached overhead; no retry'
report['known_causal_prefix']='2675 other monster takeoff -> Walk target335476 stomp transfer -> 2685 realHarpoon ->2694 needlehit ->2699 targetretreat ->2706 hookdashdamage ->2717 externalstepblocked ->2721 damage by airborne335470. No newDownSlash.'
write(A/'ROOT_EVENT_AUDIT.json',report)
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in report['original_files_sha256'].items())
print(json.dumps({'source_files':len(actual),'walk_opportunities':1,'walk_success':False,'receipts':coverage['receipts'],'simultaneous_dash_jump_frames':coverage['simultaneous_dash_jump']['actual_latched_frames'],'original_files_unchanged':True},ensure_ascii=False))
