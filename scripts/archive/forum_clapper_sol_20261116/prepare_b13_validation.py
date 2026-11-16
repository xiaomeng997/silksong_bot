"""Sol-owned freeze and affected replay cases; no controller edits or live actions."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess,sys

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/b13_399_20261112'
OLD=B/'analysis/slamstart398_20261112';WT=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args,cwd=WT):return subprocess.check_output([GIT,*args],cwd=cwd)

def main():
    expected=sys.argv[1];source=git('rev-parse',expected).decode().strip()
    assert git('rev-parse','HEAD').decode().strip()==source
    root=A/'source';assert not root.exists();root.mkdir()
    old=read(OLD/'SOURCE_PACKET.json')
    files=old['raw_runtime_files_sha256']
    for n,h in {**files,**old['support_sha256']}.items():
        src=OLD/'source'/n;assert sha(src)==h,n
        dst=root/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    delta=git('diff','--name-only',old['source'],source).decode().splitlines()
    runtime_delta=[n for n in delta if n in files]
    assert set(runtime_delta)=={'brain/ssbot/combat/knife_chain_air_native.py','brain/ssbot/combat/knife_chain_air_v01.json','brain/ssbot/combat/knife_chain_transfer.py'},runtime_delta
    for n in runtime_delta:
        data=git('show',source+':'+n);dst=root/n
        if b'\r\n' in dst.read_bytes():data=data.replace(b'\n',b'\r\n')
        dst.write_bytes(data)
    shutil.copytree(OLD/'source/.git',root/'.git')
    git('symbolic-ref','HEAD','refs/heads/b13_399_freeze',cwd=root)
    git('update-ref','refs/heads/b13_399_freeze',source,cwd=root)
    git('read-tree','HEAD',cwd=root)
    assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=root).strip()
    raw={n:sha(root/n) for n in files}
    packet=dict(at=now(),source=source,parent=old['source'],source_root=str(root),runtime_files=len(raw),raw_runtime_files_sha256=raw,
                runtime_support_files=old['runtime_support_files'],support_sha256={n:sha(root/n) for n in old['runtime_support_files']},
                reviewed_commits=['0e3d6593',source],runtime_delta=runtime_delta)
    put(A/'SOURCE_PACKET.json',packet)
    shutil.copy2(OLD/'entry.py',A/'entry.py')
    # Existing adapter chain + reviewed fixed executor/helper. Previous inputs remain immutable; add actual new trial bytes.
    binding=read(OLD/'REPLAY_INPUT_BINDING.json')['files'];assert all(sha(p)==h for p,h in binding.items())
    K=B/'opus/review182/s312/b13'
    scenes=[('W1','p12_ep20',67014,67053),('W2','p12_ep9',37696,37737),('W3','p12_ep13',48865,48901),('W4','c86_ep13',41443,41476)]
    contexts=[]
    oldcase=read(OLD/'CASE_NEW.json')
    flags0=oldcase['contexts'][0]['flags']
    for name,trial,syn,last in scenes:
        t=K/'trials'/trial
        for dp,dn,fs in os.walk(t,followlinks=True):
            for f in fs:
                p=Path(dp)/f;binding[str(p)]=sha(p)
        flags=[x for x in flags0 if not x.startswith(('--opus-synth=','--no-force-from='))]
        flags += ['--opus-synth='+str(syn),'--no-force-from='+str(syn)]
        contexts.append(dict(name=name,trial=str(t),**{'from':syn-2},last=last,flags=flags,
            scope='B13 own target-body air guard: real async policy/geometry/send; model hero after SYN, enemy follows recording. W4 older c86 recording, current runtime profile explicit.'))
    put(A/'REPLAY_INPUT_BINDING.json',dict(at=now(),complete=True,files=binding,scope='Existing reviewed entry chain and new four trial trees including raw recorded states; no changed control code in input adapter.'))
    for side,value in [('NEW','1'),('BASELINE','0')]:
        c=dict(oldcase);c.update(source=source,source_root=str(root),entry_file=str(A/'entry.py'),entry_sha256=sha(A/'entry.py'),
            source_review_file=str(A/'SOURCE_REVIEW.json'),source_packet_file=str(A/'SOURCE_PACKET.json'),source_packet_sha256=sha(A/'SOURCE_PACKET.json'),
            input_binding_file=str(A/'REPLAY_INPUT_BINDING.json'),input_binding_sha256=sha(A/'REPLAY_INPUT_BINDING.json'),case_id='b13_399_'+side.lower(),contexts=[])
        c['accepted_reviews']=sorted(set(c['accepted_reviews']+[399,int(sys.argv[2])]))
        for q in contexts:
            q=dict(q);q['flags']=q['flags']+['--env=SSBOT_FORUM_CHAIN_B13='+value];c['contexts'].append(q)
        put(A/('CASE_'+side+'.json'),c)
    put(A/'SOURCE_REVIEW.json',dict(at=now(),source=source,accepted=False,scope='B13 first transfer-air package plus same-package steer lifecycle/route repair; awaiting production verification.',live_released=False,formal_timing_pass=False))
    print(json.dumps(dict(source=source,freeze=str(root),runtime_files=len(raw),bound_inputs=len(binding),windows=[q['name'] for q in contexts])))

if __name__=='__main__':main()
