"""Read-only B2 preflight evidence; never launch/connect/restore or change markers.
Draft only. --out writes the report, otherwise stdout. No ssbot imports or kernels.
"""
import argparse,hashlib,json,os,subprocess,sys,sysconfig,tomllib
from pathlib import Path
from datetime import datetime,timezone
import importlib.metadata
import psutil
ap=argparse.ArgumentParser();ap.add_argument('--code',default='C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');ap.add_argument('--out');a=ap.parse_args()
code=Path(a.code).resolve()
def sha(p):
 p=Path(p)
 return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def git(*args,cwd=code):
 q=subprocess.run(['git',*args],cwd=cwd,capture_output=True,text=True,timeout=30)
 return {'returncode':q.returncode,'stdout':q.stdout.strip(),'stderr':q.stderr.strip()}
def readjson(p):
 p=Path(p)
 try:return {'path':str(p),'exists':p.exists(),'sha256':sha(p),'value':json.loads(p.read_text(encoding='utf-8')) if p.is_file() else None}
 except (OSError,ValueError) as exc:return {'path':str(p),'error':str(exc)}
def file(p):
 p=Path(p);return {'path':str(p),'exists':p.exists(),'size':p.stat().st_size if p.is_file() else None,'sha256':sha(p)}
me=psutil.Process();me.nice(psutil.IDLE_PRIORITY_CLASS);me.cpu_affinity(list(range(16,32)))
lock=tomllib.loads((code/'versions.lock').read_text(encoding='utf-8'))
base=Path('C:/ssbot/data/m2_play/clapper_plan/analysis/b2_post_reuse_20261030/baseline_identity.json')
expected=json.loads(base.read_text(encoding='utf-8'))
overlay=[{'file':v['file'],'expected':v['sha256'],'actual':sha(code/v['file'])} for v in expected['overlay']]
sources={str(p.relative_to(code)).replace('\\','/'):sha(p) for p in sorted((code/'brain/ssbot').rglob('*.py'))}
sources['brain/ssbot/combat/knife_chain_slam_v01.json']=sha(code/'brain/ssbot/combat/knife_chain_slam_v01.json')
game=[]
for p in psutil.process_iter(['pid','name','create_time']):
 if 'silksong' in (p.info['name'] or '').lower():game.append(p.info)
ports=[];port_error=None
try:
 for c in psutil.net_connections(kind='tcp'):
  if c.laddr and 47017<=c.laddr.port<=47024:ports.append({'port':c.laddr.port,'pid':c.pid,'status':c.status})
except (psutil.Error,OSError) as exc:port_error=repr(exc)
freeze={}
for k,p in {'v1':'C:/Users/Meng/.codex/worktrees/forum-measurement/silksong_bot','v2':'C:/Users/Meng/.codex/worktrees/forum-aa-v2/silksong_bot'}.items():freeze[k]=git('rev-parse','HEAD',cwd=p)
settings=lock['frozen_settings'];golden=file(settings['golden_prefs']);golden['expected']=settings['golden_prefs_sha256'];golden['matches']=golden['sha256']==golden['expected']
sandbox=Path('C:/ssbot/sandbox')
markers={str(p):{'exists':p.exists(),'sha256':sha(p)} for p in [sandbox/'STOP_AGENTS',sandbox/'DEMO_SOON',sandbox/'prefs'/'instances.lock']}
versions={}
for name in ['numpy','numba','psutil','pytest']:
 try:versions[name]=importlib.metadata.version(name)
 except importlib.metadata.PackageNotFoundError:versions[name]=None
report={'scope':__doc__,'time_utc':datetime.now(timezone.utc).isoformat(),'code':str(code),'git_head':git('rev-parse','HEAD'),'git_status':git('status','--porcelain'),'python':{'executable':sys.executable,'version':sys.version,'exe_sha256':sha(sys.executable),'venv_cfg':file(Path(sys.executable).parents[1]/'pyvenv.cfg'),'packages':versions},'source_manifest':sources,'source_manifest_sha256':hashlib.sha256(json.dumps(sources,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'overlay':overlay,'overlay_exact':all(x['actual']==x['expected'] for x in overlay),'versions_lock':file(code/'versions.lock'),'golden':golden,'launcher_state':readjson(sandbox/'prefs'/'instances.json'),'markers':markers,'silksong_processes':game,'passive_ports':ports,'passive_ports_error':port_error,'frozen_heads':freeze,'aa_schedule':file('C:/ssbot/data/m2_play/clapper_plan/step0/v2/schedule_v2_20261028.json'),'aa_stopped':file('C:/ssbot/data/m2_play/clapper_plan/step0/v2/run_20261028_v2/STOPPED.json'),'aa_active_lock':file('C:/ssbot/data/m2_play/clapper_plan/step0/v2/run_20261028_v2/ACTIVE.lock'),'unverified':['No current game/Oracle readiness certified by an empty port list','Registry restoration is not proven without real Launcher cleanup receipt','No game launched; no actual TCP/physics/action acceptance observed','Runtime changes are in progress; not a final frozen manifest','No block/seed/conditions contract issued by this script']}
result=json.dumps(report,ensure_ascii=False,indent=1)
if a.out:
 out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('x',encoding='utf-8') as f:f.write(result+'\n')
else:print(result)
