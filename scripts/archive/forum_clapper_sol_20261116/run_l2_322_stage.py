"""Guarded metadata transfer to unchanged executor."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,runpy,sys
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task180_l2_322_20261106';EX=B/'sol/performance/executor_v1.py'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['check','measure']);args=p.parse_args();st=read(B/'sol/STATUS.json')
 assert st['source_frozen_for_P'] and st['current_source']=='9f6da15674da8c396d729a680f6868d47d9e233f' and not st.get('own_offline_jobs') and not (B/'sol/performance/ACTIVE.json').exists()
 lines=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').splitlines()[:18];paused=next(x for x in lines if x.startswith('- **Opus 正在做**'));assert 'seq 249' in paused and '暂停' in paused,'await actual Opus pause'
 assert hashlib.sha256(EX.read_bytes()).hexdigest()=='58ddebd9cae93764d37b9fb4efa75ea7a2484bb6f4337895a245886e86062ffc'
 dest=A/('startup' if args.mode=='check' else 'p_N');assert not dest.exists()
 if args.mode=='check':
  assert st['live_or_budget_running'] and st['phase']=='TASK180_P_WAIT_OPUS_PAUSE'
  (A/'PAUSE_CONFIRMED.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),summary=paused,source_frozen=True,new_games=0),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 else:assert not st['live_or_budget_running'] and read(A/'startup/FINALIZED.json')['cleanup_verified']
 st.update(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),live_or_budget_running=False,phase='322_TRANSFER_TO_FIXED_'+args.mode.upper());q=B/'sol/STATUS.l2322stage.tmp';q.write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(q,B/'sol/STATUS.json')
 sys.argv=[str(EX),args.mode,'--case',str(A/'P_CASE.json'),'--output',str(dest)]
 if args.mode=='measure':sys.argv+=['--preflight',str(A/'startup')]
 runpy.run_path(str(EX),run_name='__main__')
if __name__=='__main__':main()
