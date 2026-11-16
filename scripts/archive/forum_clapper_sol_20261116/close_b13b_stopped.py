"""Independent physical cleanup on a stopped batch; retain its measurement failure."""
from pathlib import Path
import hashlib
G=Path('C:/ssbot/data/m2_play/clapper_plan/analysis/w13_50_b13b404_20261113')
p=G/'root_cleanup.py';text=p.read_text(encoding='utf-8')
old="assert wr['complete'] and not wr['secondary_errors']"
new="""assert wr['complete']
assert wr['primary_error']=='LearningStop: missing critical application receipt beyond four-frame upper bound'
assert len(wr['secondary_errors'])==1 and wr['secondary_errors'][0]['origin']=='measurement'
assert wr['secondary_errors'][0]['reason']=='measurement incomplete; stop before another episode'
assert all(v in ('pass','not_required') for v in wr['resources'].values())
"""
assert text.count(old)==1
text=text.replace(old,new)
anchor="with (R/'ROOT_CLEANUP.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)"
assert text.count(anchor)==1
extra="""out['physical_cleanup_complete']=True
out['primary_error_preserved']=wr['primary_error']
out['secondary_measurement_errors_preserved']=wr['secondary_errors']
out['measurement_acceptance_pass']=False
out['standard_cleanup_check_failed']='root_cleanup.py line20 rejects all secondary errors, including the retained incomplete measurement from the primary receipt fault. No resource cleanup failed.'
out['standard_cleanup_script_sha256']='"""+hashlib.sha256(p.read_bytes()).hexdigest()+"'\n"
text=text.replace(anchor,extra+anchor)
exec(compile(text,str(Path(__file__)), 'exec'),{'__name__':'__main__','__file__':str(p)})
