"""A/A v2 collection primitives. Engineering data never qualify for production."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from ssbot.record.recorder import RecordingReader
from ssbot.train.measurement import validate_trace
from ssbot.train.stall_diagnostics import tail_summary
from ssbot.train.aa_v2 import validate_production_cli, runtime_errors


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as out:
        json.dump(value, out, indent=1, allow_nan=False, default=str)


def audit_environment():
    # A caller's sys.path changes do not propagate to a new Python process.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    return env


def verify_episode(run, instance, episode=0, *, production=False, context=None):
    run = Path(run)
    attempt = next(json.loads(s) for s in (run/f"attempts_i{instance}.jsonl").read_text().splitlines()
                   if json.loads(s)["episode"] == episode)
    m = attempt["measurement"]
    manifest = json.loads(Path(m["manifest"]).read_text())
    if production:
        validate_production_cli(manifest["cli"])
    trace = validate_trace(Path(m["path"]))
    audit_path = run/f"audit_i{instance}_e{episode}.json"
    args = [sys.executable,"-B","-m","ssbot.tools.forum_measure_audit","--run",str(run),
            "--instance",str(instance),"--episode",str(episode),"--out",str(audit_path)]
    result = subprocess.run(args,capture_output=True,text=True,timeout=120,env=audit_environment(),
                            cwd=Path(__file__).resolve().parents[3])
    (run/f"audit_i{instance}_e{episode}.log").write_text(result.stdout+result.stderr,encoding="utf-8")
    if not audit_path.exists():
        raise RuntimeError(result.stdout+result.stderr)
    audit = json.loads(audit_path.read_text())
    continuity = RecordingReader(attempt["recording"]).check(deep=True).as_dict()
    rows = [json.loads(s) for s in Path(m["path"]).read_text().splitlines()]
    window = audit["window"]
    have_boundaries = isinstance(window["wake_f"], int) and isinstance(window["end_f"], int)
    tail = tail_summary(rows if have_boundaries else [],wake_f=window["wake_f"],end_f=window["end_f"])
    errors = runtime_errors(manifest)
    if m.get("protocol_version") != 2:
        errors.append("attempt is not protocol v2")
    if production and not rows[-1].get("diagnostics", {}).get("complete"):
        errors.append("missing/incomplete required production diagnostics")
    if not m["complete"] or not trace["complete"] or not audit["complete"] or not continuity["ok"]:
        errors.append("incomplete measurement/trace/raw audit")
    online = m["window"]
    for key in ("wake_f","end_f","T","target_ids","watchdog_f","tail_end_f","tail_end_reason"):
        if online.get(key) != window.get(key):errors.append("online/offline window mismatch: "+key)
    for state in (RecordingReader(attempt["recording"]).states(window["wake_f"],window["tail_end_f"]) if have_boundaries else []):
        game,hero = state.get("game") or {},state.get("hero") or {}
        if not isinstance(game.get("cheat"),int) or game["cheat"]&3 or hero.get("is_invincible") or hero.get("invincibility_source"):
            errors.append("cheat or missing cheat status");break
    recovered = True
    if window.get("watchdog_f") is not None:
        recovery = run/f"recovery_i{instance}_e{episode}.json"
        recovered = recovery.exists() and json.loads(recovery.read_text()).get("recovered") is True
        # Recovery controls continuation, not whether already observed HP/time are known.
    result = {"protocol_version":2,"complete":not errors,"errors":errors,"instance":instance,"episode":episode,
              "run":str(run),"seed":attempt["seed"],"outcome":attempt.get("measurement_outcome",attempt["outcome"]),
              "audit":audit,"trace":trace,"continuity":continuity,"behavior_sha256":m["behavior_sha256"],
              "recovered":recovered,"diagnostic_tail":tail,
              "main_ticks":{"n":tail["total"]["n"],"p50":tail["total"]["p50_ms"],"p99":tail["total"]["p99_ms"],
                            "gap_ge3":sum((x.get("processed_frame_gap") or 0)>=3 for x in rows
                                          if have_boundaries and x.get("kind")=="tick" and window["wake_f"]<=x["f"]<=window["end_f"])/max(1,tail["total"]["n"])},
              "diagnostics":rows[-1].get("diagnostics"),"production_eligible":production and not errors}
    result.update(context or {})
    write_new(run/f"verified_i{instance}_e{episode}.json",result)
    return result


def run_round(run, *, root, environment, wave, seed, instances=(0,1), episodes=1,
              diagnostics=None, stall_ms=0.0, engineering=False, timeout_s=600, slot=None):
    """Runs fixed attempts once. No failed episode is dropped or automatically replaced."""
    run,root = Path(run),Path(root)
    if any((Path("C:/ssbot/sandbox")/n).exists() for n in ("STOP_AGENTS","HUMAN_PRACTICE","DEMO_SOON")):
        raise RuntimeError("human stop/practice marker; no new worker launched")
    run.mkdir()
    if stall_ms and not engineering:
        raise ValueError("injection is forbidden outside engineering")
    diagnostics = diagnostics or {i:True for i in instances}
    write_new(run/"config.json",{"purpose":"engineering" if engineering else "A/A v2", "seed":seed,
                                "wave":wave,"episodes":episodes,"diagnostics":diagnostics,"stall_ms":stall_ms,
                                "env":{k:v for k,v in environment.items() if k.startswith("SSBOT_")}})
    procs=[]
    try:
        for i in instances:
            args=[sys.executable,"-B","-m","ssbot.tools.combat_run","_worker","--run-dir",str(run),
                  "--instance",str(i),"--encounter",f"Forum_W_w{wave}","--mode","eval","--policy","planner",
                  "--view","oracle","--threads","4","--forum-clash","main","--episodes",str(episodes),
                  "--seed",str(seed),"--same-seeds","--measure","--measurement-protocol","2"]
            if diagnostics[i]:args.append("--measure-diagnostics")
            if engineering:args.append("--engineering-probe")
            if stall_ms and i==instances[0]:args += ["--measure-stall-ms",str(stall_ms)]
            log=(run/f"worker_i{i}.log").open("w",encoding="utf-8")
            process=subprocess.Popen(args,cwd=root,env=environment,stdout=log,stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            procs.append((i,process,log))
        started=time.monotonic()
        while any(p.poll() is None for _,p,_ in procs):
            if any((Path("C:/ssbot/sandbox")/n).exists() for n in ("STOP_AGENTS","HUMAN_PRACTICE","DEMO_SOON")):
                (run/"STOP").write_text("human stop/practice marker",encoding="utf-8")
            if time.monotonic()-started>timeout_s:raise TimeoutError("v2 worker timeout")
            time.sleep(.5)
        for _,_,log in procs:log.close()
        failures=[(i,p.returncode) for i,p,_ in procs if p.returncode]
        # Keep partial attempts and audit evidence before stopping on worker errors.
        verified=[]
        for i,_,_ in procs:
            path=run/f"attempts_i{i}.jsonl"
            for a in [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []:
                context = ({k:v for k,v in slot.items() if k!="labels"} | {"label":slot["labels"][i]}) if slot else None
                verified.append(verify_episode(run,i,a["episode"],production=not engineering,context=context))
        if failures:raise RuntimeError("v2 worker failure (evidence retained): "+str(failures))
        if len(verified)!=len(instances)*episodes:raise RuntimeError("missing fixed attempts")
        return verified
    finally:
        for _,p,log in procs:
            if p.poll() is None:
                (run/"STOP").write_text("collector stopping",encoding="utf-8")
                try:p.wait(timeout=8)
                except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=15)
            if not log.closed:log.close()


def run_period(protocol, index, *, root, environment, output_root):
    """Already-launched games only. A frozen, scheduled v2 contract is mandatory."""
    import hashlib
    from datetime import datetime
    from ssbot.train.aa_v2 import PeriodGuard
    from ssbot.tools.forum_aa_v2_analysis import analyze, load_rows
    if protocol.get("schema") != 2 or protocol.get("status") != "FROZEN":
        raise ValueError("a frozen production v2 protocol is required")
    period = protocol["periods"][index]
    if not period.get("planned_start"):
        raise ValueError("v2 production schedule is not frozen")
    protocol_sha = hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    due = datetime.fromisoformat(period["planned_start"])
    now = datetime.now().astimezone()
    if not 0 <= (now-due).total_seconds() <= protocol["max_start_delay_seconds"]:
        raise ValueError("outside frozen v2 start window")
    for name,wanted in (protocol["files_sha256"] | protocol.get("static_identity_files", {})).items():
        path=Path(name) if Path(name).is_absolute() else Path(root)/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=wanted:
            raise ValueError("v2 source/model identity changed: "+name)
    previous_rows=load_rows(Path(output_root))
    if len(previous_rows)!=32*index or any(r['period']>=index for r in previous_rows):
        raise ValueError("previous v2 periods incomplete or unexpected attempts")
    if any(not (Path(output_root)/f"period_{i}/complete.json").exists() for i in range(index)):
        raise ValueError("previous v2 period did not finish")
    out=Path(output_root)/f"period_{index}"
    out.mkdir()
    write_new(out/"started.json",{"at":now.isoformat(),"planned_start":period["planned_start"]})
    guard=PeriodGuard(**protocol["continuation_limits"])
    rows=[]
    for b in period["blocks"]:
        block=protocol["blocks"][b]
        for round_no in (0,1):
            labels={i:("A" if (b+round_no+i)%2==0 else "B") for i in (0,1)}
            try:
                new=run_round(out/f"b{b:02d}_r{round_no}",root=root,environment=environment,
                              wave=13,seed=block["seed"],slot={"period":index,"block":b,"round":round_no,"labels":labels,"protocol_sha256":protocol_sha})
            except Exception as exc:
                write_new(out/"STOPPED.json",{"reason":repr(exc),"all_attempts_retained":True})
                raise
            reasons=[]
            for row in new:
                if row["behavior_sha256"] != protocol.get("behavior_sha256"):
                    reasons.append("configuration differs from frozen v2 contract")
                reasons += guard.observe(row["instance"],outcome=row["outcome"],complete=row["complete"],recovered=row["recovered"])
            rows += new
            if reasons:
                write_new(out/"STOPPED.json",{"reasons":reasons,"all_attempts_retained":True})
                return {"complete":False,"stop_reasons":reasons,"rows":rows}
        report=analyze(previous_rows+rows)
        write_new(out/f"after_block_{b:02d}.json",report)
        if report.get("stop_reasons"):
            write_new(out/"STOPPED.json",{"reasons":report["stop_reasons"],"all_attempts_retained":True})
            return {"complete":False,"stop_reasons":report["stop_reasons"],"rows":rows}
    write_new(out/"complete.json",{"at":datetime.now().astimezone().isoformat(),"episodes":len(rows)})
    return {"complete":True,"rows":rows}
