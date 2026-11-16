"""User-requested local delivery monitor. Metadata polling never calls a model.

New Opus numbers use the existing one-shot, deduplicated 30-second notifier.
This process never changes source, starts P/game, or writes Opus directories.
"""
from pathlib import Path
import argparse,datetime,json,os,re,subprocess,sys,time,traceback
import psutil

BASE=Path('C:/ssbot/data/m2_play/clapper_plan')
ROOT=BASE/'sol/mailwatch';DATA=ROOT/'monitor';LOCK=DATA/'ACTIVE.json'
THREAD='01a1bc0f-da63-7172-b7cf-54a018b74d6d'
PYTHONW=Path('C:/modeling/silksong_bot/brain/.venv/Scripts/pythonw.exe')
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def put(p,d):
    q=p.with_name(p.name+'.'+str(os.getpid())+'.tmp')
    q.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(q,p)
def alive(d):
    try:return abs(psutil.Process(d['pid']).create_time()-d['created'])<.01
    except psutil.NoSuchProcess:return False
def latest():
    with (BASE/'opus/TO_SOL.md').open(encoding='utf-8') as f:s=f.read(65536)
    m=re.search(r'最新编号[^#\r\n]*#(\d+)',s)
    if not m:raise ValueError('Missing latest Opus number; no message sent')
    return int(m[1])
def log(d):
    with (DATA/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(at=now(),**d),ensure_ascii=False)+'\n')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--dry-run',action='store_true');a=ap.parse_args()
    n=latest();scanned=int(read(BASE/'sol/STATUS.json').get('last_scanned_opus_number',0))
    if a.dry_run:
        print(json.dumps(dict(thread=THREAD,latest=n,last_scanned=scanned,needs_notification=n>scanned and not (ROOT/'events'/('opus_'+str(n))).exists(),sends_message=False),ensure_ascii=False));return
    DATA.mkdir(exist_ok=True)
    if LOCK.exists():
        old=read(LOCK)
        if alive(old):raise RuntimeError('Delivery monitor already running; no duplicate started')
        stale=DATA/'stale';stale.mkdir(exist_ok=True);os.replace(LOCK,stale/('ACTIVE_'+str(time.time_ns())+'.json'))
    me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
    identity=dict(pid=me.pid,created=me.create_time(),thread=THREAD,script=str(Path(__file__).resolve()),started_at=now(),cpus=me.cpu_affinity(),priority=int(me.nice()))
    with LOCK.open('x',encoding='utf-8') as f:json.dump(identity,f)
    state=dict(identity,phase='running',latest=n,last_scanned=scanned,last_attempt=0,notifications_launched=0,last_error=None)
    cache=None;next_heartbeat=0
    log(dict(event='started',**identity))
    try:
        while not (DATA/'STOP').exists():
            try:
                p=BASE/'opus/TO_SOL.md';stamp=(p.stat().st_mtime_ns,p.stat().st_size)
                if stamp!=cache:
                    n=latest();scanned=int(read(BASE/'sol/STATUS.json').get('last_scanned_opus_number',0));cache=stamp
                    state.update(latest=n,last_scanned=scanned,last_error=None)
                    if n>scanned and n>state['last_attempt'] and not (ROOT/'events'/('opus_'+str(n))).exists():
                        state['last_attempt']=n;put(DATA/'heartbeat.json',dict(state,at=now()))
                        child=subprocess.Popen([str(PYTHONW),'-B','-X','utf8',str(ROOT/'wake_sol.py'),'--number',str(n)],cwd=ROOT,
                            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                        state['notifications_launched']+=1
                        log(dict(event='one_shot_launched',number=n,launcher_pid=child.pid,delivery_not_yet_verified=True))
                if time.monotonic()>=next_heartbeat:
                    put(DATA/'heartbeat.json',dict(state,at=now()));next_heartbeat=time.monotonic()+30
            except Exception as e:
                state['last_error']=repr(e);log(dict(event='read_or_launch_error',error=repr(e)));put(DATA/'heartbeat.json',dict(state,at=now()))
            time.sleep(5)
    finally:
        state['phase']='stopped';put(DATA/'heartbeat.json',dict(state,at=now()))
        if LOCK.exists() and read(LOCK).get('pid')==me.pid:LOCK.unlink()

if __name__=='__main__':main()
