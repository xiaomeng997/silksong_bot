"""Read existing #317 production artifacts without rerunning the policy."""
from pathlib import Path
import datetime,hashlib,json,subprocess,sys,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return317_20261106';O=B/'opus/review179/l1_317'
D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),str(p)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def lines(p):return [json.loads(t) for t in p.read_text(encoding='utf-8-sig').splitlines() if t]
def sends(p,lo=0,hi=99999):
 return [(x['frame'],x.get('target'),x.get('mask'),x.get('owner')) for x in lines(p/'decisions_i0.chain.jsonl') if x.get('event')=='transport_sent' and lo<=x.get('frame',-1)<=hi]
j=read(A/'ROOT_JOB.json')
try:alive=abs(psutil.Process(j['pid']).create_time()-j['created'])<.01
except psutil.NoSuchProcess:alive=False
assert not alive
if not (A/'ROOT_CHECK_CLEANUP.json').exists():
 put(A/'ROOT_CHECK_CLEANUP.json',dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),actual_job=j,identity_exited=True,formal_P_ticks=0,games_started=0))
else:assert read(A/'ROOT_CHECK_CLEANUP.json')['identity_exited']
r=read(O/'a4air8/RESULT.json');assert r['exception'] is None and not r['foreign']
hashes={n:dict(recorded=h,current=sha(D/'brain/ssbot'/n)) for n,h in r['source_sha256'].items()}
assert all(v['recorded']==v['current'] for v in hashes.values())
raw=subprocess.check_output([G,'-C',str(D),'diff','2f43a7e9','c00074cc','--','brain/ssbot/combat/forum_planner.py'])
fingerprint=hashlib.sha256(raw).hexdigest()[:16];assert fingerprint==r['knife_diff_sha256_16'],fingerprint
tool=B/'opus/review179/l1_308/replay308.py';assert sha(tool)==r['tool']['replay308_sha256']
comparisons=[]
for left,right in [('a4air','a4air8'),('n1air7','n1air8'),('w3air7','w3prof2')]:
 sa0,sb0=sends(O/left),sends(O/right)
 lo=max(sa0[0][0],sb0[0][0]);hi=min(sa0[-1][0],sb0[-1][0])
 sa,sb=sends(O/left,lo,hi),sends(O/right,lo,hi);assert sa==sb
 comparisons.append(dict(before=left,after=right,window=[lo,hi],full_counts=[len(sa0),len(sb0)],transport_count=len(sa),all_final_target_mask_owner_equal=True))
events=lines(O/'a4air8/decisions_i0.chain.jsonl')
selected=[{k:v for k,v in x.items() if k in ('event','frame','target','reason','hit','owner','link','request','cast_fa')} for x in events if x.get('event') in ('b2_strike_accepted','b2_real_bounce_handback','transfer_no_witness_handback','return_request_start_deferred','rune_transfer_dash_checked') and 2785<=x.get('frame',-1)<=2840]
assert any(e.get('event')=='transfer_no_witness_handback' and e.get('frame')==2831 for e in selected)
timeline=[x for x in r['rows'] if x.get('f') in (2793,2795,2812,2816,2831,2836,2870,2884,2903)]
l2=[x for x in lines(O/'a4air8_l2trace.jsonl') if x.get('f') in (2816,2831,2836,2870)]
put(A/'ROOT_ARTIFACT_RECEIPT.json',dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source='c00074ccdd589c0e3c37ba4302234e689a858121',producer_head=r['knife_head'],producer_brain_dirty=r['knife_brain_dirty'],producer_diff16=fingerprint,reconstructed_from_git=True,selected_source_hashes=hashes,tool_sha256=sha(tool),model_options=r['tool']['model_options'],transport_comparisons=comparisons,model_hits=r['model_hits'],model_hurts=r['model_hurts'],timeline=timeline,selected_chain_events=selected,l2_timeline=l2,configuration_complete=r['configuration_complete'],configuration_unresolved=r['configuration_unresolved'],scope='Conditional recorded-reaction production-interface positive: legal handback and ground intent/landing/slash sends. Not natural closed-loop or repeated downslash proof; not formal P/live acceptance.'))
print(json.dumps(dict(source_bindings=len(hashes),grouped_outputs_equal=comparisons,model_hits=r['model_hits'],hurt_count=len(r['model_hurts']),formal_P=False)))
