"""Independent arithmetic/source binding of an existing one-state diagnostic. No replay."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import difflib,hashlib,json,numpy as np

B=Path('C:/ssbot/data/m2_play/clapper_plan')
R=B/'analysis/committed388_20261111'
K=B/'opus/review182/s312/r7'
S=B/'analysis/glide_jump_hold445_20261115/source_fixed445'
T=K/'trees/P7'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
lf=lambda p:p.read_bytes().replace(b'\r\n',b'\n')
d=read(K/'r/e38.dbg.json');rows=d['rows'];N=d['N'];P=d['P'];kn=d['key_names']
assert N==len(rows)==558 and [x['i'] for x in rows]==list(range(N)) and d['key_names_ok']
keys=np.array([x['keys'] for x in rows],dtype=float)
order=np.lexsort(tuple(keys[:,i] for i in range(len(kn)-1,-1,-1)))
assert [int(i) for i in order[:12]]==d['order_head'][:12]
sel=np.array([x['sel'] for x in rows],dtype=bool)
legal=[int(i) for i in order if sel[i]]
classes=[]
for x in rows:
    m=x['mode'];lat=x['latched'];cmd=x['cmd']
    pre=m[P]==8
    classes.append(dict(no_glide=8 not in m[P+1:],first_open=not pre and m[P+1]==8,
        later_open=not pre and m[P+1]!=8 and 8 in m[P+1:],
        continued_first=pre and bool(lat[P]&1) and bool(cmd[0]&1),
        forced_J=bool(lat[P]&1) and not bool(cmd[0]&1)))
best=next(i for i in legal if classes[i]['no_glide'])
winner=d['chosen'];diff=next(i for i,(a,b) in enumerate(zip(rows[winner]['keys'],rows[best]['keys'])) if a!=b)
assert winner==d['order_first']==d['res_idx']==144 and best==5 and kn[diff]=='v2_nh'
assert rows[144]['nh']==1 and rows[5]['nh']==0 and rows[144]['v2nh']==-1 and rows[5]['v2nh']==0
assert d['tail_ok'] is False and d['esc']['unsafe'] and d['stay_info'] is None
checked={int(i):int(fail) for rr,ff in d['esc_calls'] for i,fail in zip(rr,ff)}
assert len(checked)==16 and set(checked.values())=={1}
cost_annotations={}
for name,eligible in [('first_key_only',[c['first_open'] or c['continued_first'] for c in classes]),
                      ('all_future_open_or_first_continued',[c['first_open'] or c['later_open'] or c['continued_first'] for c in classes])]:
    ann=keys.copy();ann[:,kn.index('v2_nh')]+=np.array(eligible)*np.array([x['safe'] for x in rows])
    oo=np.lexsort(tuple(ann[:,i] for i in range(len(kn)-1,-1,-1)))
    top=[int(i) for i in oo if sel[i]][:12]
    cost_annotations[name]=dict(initial_order_top=top,names=[rows[i]['name'] for i in top],
        scope='Arithmetic annotation only; no modified selector, tail/promotion or hero run')
packet=read(S.parent/'SOURCE_PACKET_FIXED.json')
unchanged=[];missing=[];different=[]
for f in packet['raw_runtime_files_sha256']:
    if not (T/f).exists():missing.append(f)
    elif lf(S/f)==lf(T/f):unchanged.append(f)
    else:different.append(f)
assert different==['brain/ssbot/combat/forum_planner.py'],different
patch=''.join(difflib.unified_diff(lf(S/different[0]).decode().splitlines(True),lf(T/different[0]).decode().splitlines(True),
    fromfile='a/'+different[0],tofile='b/'+different[0]))
assert patch.encode()==lf(K/'dbg_P7.patch')
result=read(K/'r/e38/RESULT.json')
assert result['exception'] is None and result['divergence_tick'] is None and result['synthetic_from']==135008
hash_binding=[]
for f,h in result['source_sha256'].items():
    actual=T/'brain/ssbot'/f
    assert sha(actual)==h,(f,sha(actual),h)
    hash_binding.append(dict(file=f,sha256=h,base_same=f!='combat/forum_planner.py'))
live=None
for line in (B/'sol/demos/w13_50_middle_handoff434_20261114/run/decisions_i0.jsonl').open(encoding='utf-8'):
    if '135004' not in line:continue
    x=json.loads(line)
    if x.get('f')==135004:live=x;break
assert live and live['fi']['enveloped']==128 and live['fi']['cut']
assert 'scene_field_rank' not in live['fi']
counts={name:dict(total=sum(c[name] for c in classes),legal=sum(c[name] and rows[i]['sel'] for i,c in enumerate(classes))) for name in classes[0]}
out=dict(at=datetime.now(timezone.utc).isoformat(),delivery=448,source='d6a3664416ef84280b214115dc80f2b256782b32',
    artifact_sha256={str(p):sha(p) for p in [K/'r/e38.dbg.json',K/'r/e38/RESULT.json',K/'dbg_P7.patch',K/'make_dbg_p7.py',K/'dbg_read382.py']},
    runtime_LF_unchanged=len(unchanged),missing_from_analysis_tree=missing,changed_runtime_only=different,exact_analysis_patch_verified=True,
    recorded_module_bindings=hash_binding,rows=N,legal=len(legal),classes=counts,original_winner=winner,best_legal_no_glide=best,
    first_differing_key=dict(index=diff,name=kn[diff],winner=rows[winner]['keys'][diff],best_no_glide=rows[best]['keys'][diff]),
    current_tail_checks=checked,actual_original_final=dict(index=winner,mask=d['pending_mask'],tail_ok=False,unsafe=True),
    cost1_annotations=cost_annotations,
    limitations=['All sends forced through135007; no changed-control or synthetic-hero result.',
        'Analysis has192 enveloped/safe rows and no deadline; actual live tick128/cut. Analysis prio positions do not prove original live priority/history.',
        'scene_values absent in this reconstruction; original fi has no scene_field_rank result. Effective flag1 is not proof of identical worker state.',
        'Post-cost initial ranking is not the final new escape/promotion winner or injury benefit.',
        'First-continuation classification in old diagnostic does not implement phase/forced-prefix unknown guards.'])
(R/'ROOT448_TABLE_CHECK.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:out[k] for k in ['runtime_LF_unchanged','missing_from_analysis_tree','changed_runtime_only','rows','legal','classes','first_differing_key','cost1_annotations']},ensure_ascii=False))
