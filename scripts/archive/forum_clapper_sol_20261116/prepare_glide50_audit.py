"""Adapt only postprocessing; preserve the contract-bound scripts and raw data."""
from pathlib import Path
from datetime import datetime, timezone
import ast, hashlib, json, psutil

ROOT=Path('C:/modeling/silksong_bot')
B=Path('C:/ssbot/data/m2_play/clapper_plan')
G=B/'analysis/w13_50_glide_hold445_20261115'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=datetime.now(timezone.utc).isoformat()
s=read(B/'sol/STATUS.json')
for x in s.get('own_offline_jobs',[]):
    try:
        assert abs(psutil.Process(x['pid']).create_time()-x['created'])>.01
    except psutil.NoSuchProcess:
        pass
failure=dict(at=now, stage='postprocessing only', controller_failure=False,
             reason='Inherited audit assumed exactly 8-character Git abbreviation; actual row uses valid 7-character d6a3664+dirty.',
             original_script=str(G/'audit_repeat50.py'), original_sha256=sha(G/'audit_repeat50.py'),
             preserved_first_audit=str(G/'audits/MEASUREMENT_e0.json'), old_process=read(G/'AUDIT_PROCESS.json'),
             repair='Validate exact manifest HEAD/file hashes and an unambiguous full-source prefix of 7..40 hex chars; resume the already complete first raw audit.')
with (G/'POSTPROCESS_FAILURE_1.json').open('x',encoding='utf-8') as f:json.dump(failure,f,ensure_ascii=False,indent=2)
s.update(own_offline_jobs=[],phase='GLIDE44550_POSTPROCESS_REPAIR')
(B/'sol/STATUS.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

t=(G/'audit_repeat50.py').read_text(encoding='utf-8-sig')
t=t.replace('A=Path(__file__).resolve().parent',f'A=Path({str(G)!r})')
t=t.replace("write(A/'AUDIT_PROCESS.json',receipt)","write(A/'AUDIT_PROCESS_ROOT.json',receipt)")
needle="""        assert not out.exists()
        with log.open('x',encoding='utf-8') as fp:
            proc=subprocess.run([sys.executable,'-X','utf8','-B','-m','ssbot.tools.forum_measure_audit','--run',str(D/'run'),'--instance','0','--episode',str(ep),'--out',str(out),'--protocol-version','2'],env=env,stdout=fp,stderr=subprocess.STDOUT)
        au=read(out); cli.append({'episode':ep,'returncode':proc.returncode,'complete':au['complete'],'out':str(out)})"""
assert needle in t
t=t.replace(needle,"""        if out.exists():
            assert ep==0 and (A/'POSTPROCESS_FAILURE_1.json').exists(), 'unexpected preexisting audit'
            au=read(out); assert au['complete']
            cli.append({'episode':ep,'returncode':0,'complete':True,'out':str(out),'reused_complete_audit_before_short_revision_assertion':True})
        else:
            with log.open('x',encoding='utf-8') as fp:
                proc=subprocess.run([sys.executable,'-X','utf8','-B','-m','ssbot.tools.forum_measure_audit','--run',str(D/'run'),'--instance','0','--episode',str(ep),'--out',str(out),'--protocol-version','2'],env=env,stdout=fp,stderr=subprocess.STDOUT)
            au=read(out); cli.append({'episode':ep,'returncode':proc.returncode,'complete':au['complete'],'out':str(out)})""")
needle="        assert row['code_rev'].removesuffix('+dirty') in (gate['source'],gate['source'][:8]),(ep,row['code_rev'],gate['source'])"
assert needle in t
t=t.replace(needle,"""        revision=row['code_rev'].removesuffix('+dirty')
        assert 7<=len(revision)<=40 and all(c in '0123456789abcdef' for c in revision) and gate['source'].startswith(revision),(ep,revision,gate['source'])
        manifest=read(D/f'run/measurement_manifest_i0_e{ep}.json')
        assert manifest['code']['head_revision']==gate['source'] and manifest['configuration_complete'] and not manifest['unresolved']
        import hashlib
        assert all(hashlib.sha256((S/path).read_bytes()).hexdigest()==digest for path,digest in manifest['code']['files_sha256'].items())""")
ast.parse(t)
out=ROOT/'tmp/audit_glide50.py'
assert not out.exists()
out.write_text(t,encoding='utf-8')
print(json.dumps(dict(postprocessing_ready=True, original_bound_scripts_unchanged=True, raw_unchanged=True, actual_game_complete=True)))
