"""Guarded stage launcher; fixed executor bytes stay unchanged and register the actual Python process."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,runpy,sys
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_body321_20261106';EX=B/'sol/performance/executor_v1.py'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['check','measure']);args=p.parse_args()
 st=read(B/'sol/STATUS.json');assert st['source_frozen_for_P'] and st['current_source']=='ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61' and not st.get('own_offline_jobs')
 assert not (B/'sol/performance/ACTIVE.json').exists()
 lines=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').splitlines()[:18]
 paused=next(x for x in lines if x.startswith('- **Opus 正在做**'))
 assert 'seq 247' in paused and '暂停' in paused,'await actual Opus pause'
 assert hashlib.sha256(EX.read_bytes()).hexdigest()=='58ddebd9cae93764d37b9fb4efa75ea7a2484bb6f4337895a245886e86062ffc'
 dest=A/('startup' if args.mode=='check' else 'p_NW');assert not dest.exists()
 if args.mode=='check':
  assert st['live_or_budget_running'] and st['phase']=='RETURN321_P_WAIT_OPUS_PAUSE'
  proof=A/'PAUSE_CONFIRMED.json';assert not proof.exists();proof.write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),summary=paused,source_frozen=True,actual_next_stage='non-timing minimal startup/exit only',new_games=0),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 else:
  assert not st['live_or_budget_running'] and read(A/'startup/FINALIZED.json')['cleanup_verified']
 # Transfer the pre-reservation to fixed executor, which atomically owns the job/ACTIVE and formal timing flag.
 st.update(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),live_or_budget_running=False,phase='321_TRANSFER_TO_FIXED_'+args.mode.upper())
 q=B/'sol/STATUS.body321stage.tmp';q.write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(q,B/'sol/STATUS.json')
 sys.argv=[str(EX),args.mode,'--case',str(A/'P_CASE.json'),'--output',str(dest)]
 if args.mode=='measure':sys.argv+=['--preflight',str(A/'startup')]
 runpy.run_path(str(EX),run_name='__main__')
if __name__=='__main__':main()
