"""Carry forward existing Windows-background authorization, binding this package to verified post-reboot identities.
No system process/service control. Old bound files stay immutable.
"""
from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess
import psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/b13b_402_20261113';OLD=B/'analysis/waypoint394_20261112'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
    assert not (B/'sol/performance/ACTIVE.json').exists()
    assert not (A/'RESOURCE_IDENTITY_REFRESH.json').exists()
    cfg=read(OLD/'RESOURCE_BACKGROUND_APPROVAL.json');assert cfg['approved'] and cfg['revision']=='verified-core-background-v1'
    old_binding=read(A/'REPLAY_INPUT_BINDING.json');assert all(sha(p)==h for p,h in old_binding['files'].items())
    identities=[];evidence=[]
    for p in psutil.process_iter(['name']):
        if p.info['name'] not in {'dwm.exe','MsMpEng.exe'}:continue
        name=p.name();exe=Path(p.exe());created=p.create_time();canon=str(exe).replace('\\','/').lower()
        if name=='dwm.exe':assert canon=='c:/windows/system32/dwm.exe'
        else:assert canon.startswith('c:/programdata/microsoft/windows defender/platform/') and canon.endswith('/msmpeng.exe')
        env=dict(os.environ);env['SSBOT_VERIFY_BACKGROUND_PATH']=str(exe)
        cmd="$s=Get-AuthenticodeSignature -LiteralPath $env:SSBOT_VERIFY_BACKGROUND_PATH; @{status=$s.Status.ToString(); signer=$s.SignerCertificate.Subject} | ConvertTo-Json -Compress"
        shell='C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/native/powershell/pwsh.exe'
        assert Path(shell).is_file()   # the current tool host, verified before this invocation
        signature=json.loads(subprocess.check_output([shell,'-NoProfile','-Command',cmd],env=env).decode('utf-8-sig'))
        assert signature['status']=='Valid' and 'O=Microsoft Corporation' in signature['signer']
        assert p.create_time()==created and Path(p.exe())==exe
        identity={'pid':p.pid,'name':name,'created':created};identities.append(identity)
        evidence.append(dict(identity,exe=str(exe),exe_sha256=sha(exe),signature=signature,status=p.status()))
    assert {x['name'] for x in identities}=={'dwm.exe','MsMpEng.exe'}
    for n in ['engineering_helpers.py','resource_background.py']:
        shutil.copy2(OLD/n,A/n);assert sha(OLD/n)==sha(A/n)
    cfg.update(at=now(),instances=identities,identity_evidence=evidence,reboot_identity_refresh_of={'file':str(OLD/'RESOURCE_BACKGROUND_APPROVAL.json'),'sha256':sha(OLD/'RESOURCE_BACKGROUND_APPROVAL.json')},scope='Carry forward existing DWM/Defender background authorization to verified current post-reboot identities. Exact PID/name/create binding, recorded load, unchanged classifier; all game/work/unknown blockers and bot deadlines retained. No process/service control.')
    put(A/'RESOURCE_BACKGROUND_APPROVAL.json',cfg)
    shutil.copy2(A/'REPLAY_INPUT_BINDING.json',A/'ENGINEERING_INPUT_BINDING.json');shutil.copy2(A/'CASE_NEW.json',A/'ENGINEERING_CASE_NEW.json')
    binding=dict(old_binding);binding['files']=dict(binding['files']);binding['at']=now();binding['scope']+='; immutable old resource inputs plus verified post-reboot resource-only copies for formal P.'
    newfiles=[A/'engineering_helpers.py',A/'resource_background.py',A/'RESOURCE_BACKGROUND_APPROVAL.json']+[Path(x) for x in cfg['authorization_sources']]
    for p in newfiles:binding['files'][str(p)]=sha(p)
    put(A/'REPLAY_INPUT_BINDING.json',binding)
    for name in ['NEW','BASELINE']:
        p=A/('CASE_'+name+'.json');c=read(p);c.update(resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'),input_binding_sha256=sha(A/'REPLAY_INPUT_BINDING.json'));put(p,c)
    put(A/'RESOURCE_IDENTITY_REFRESH.json',dict(at=now(),existing_authorization_only=True,no_process_control=True,old_inputs_unchanged=all(sha(p)==h for p,h in old_binding['files'].items()),same_helper_bytes=sha(A/'engineering_helpers.py')==sha(OLD/'engineering_helpers.py'),same_classifier_bytes=sha(A/'resource_background.py')==sha(OLD/'resource_background.py'),identities=identities,evidence=evidence,formal_case_binding_refreshed=True,engineering_input_snapshot=str(A/'ENGINEERING_INPUT_BINDING.json')))
    print(json.dumps({'old_inputs_unchanged':True,'same_rule_code':True,'current_identities':identities,'bound_inputs':len(binding['files'])}))

if __name__=='__main__':main()
