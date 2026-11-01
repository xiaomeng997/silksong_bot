"""Persistent B2 learning accounting shared by serial/parallel collector arms.

This is experiment accounting, never a controller. Atomic updates retain failures
and latch a stop before the policy can request another combat ACTION. A corrupt /
busy ledger is an integrity failure, not permission to reset the experiment.
"""
from __future__ import annotations
import json
import hashlib
import os
from pathlib import Path


class LearningStop(RuntimeError):
    pass


STRICT_POLICY = "strict-2hp-v1"
LOW_HP_POLICY = "episode-remaining-2hp-v1"


class LearningBudget:
    def __init__(self,path,*,batch,revision,worker,policy=STRICT_POLICY):
        if not batch or not revision or not worker:raise ValueError("budget needs frozen batch/revision/worker")
        if policy not in {STRICT_POLICY,LOW_HP_POLICY}:raise ValueError("unknown B2 learning policy")
        self.path=Path(path);self.batch=batch;self.revision=revision;self.worker=worker;self.policy=policy
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.state=None
        self._update(None)
        self.check()

    @property
    def remaining_hp_quit(self):
        # The supervisor, not the ledger, owns the post-hit pause and real quit.
        return 2 if self.policy==LOW_HP_POLICY else None

    def _update(self,event):
        lock=self.path.with_name(self.path.name+".lock")
        try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError as exc:raise LearningStop("B2 budget ledger busy/stale; preserve lock and stop") from exc
        try:
            os.write(fd,str(os.getpid()).encode())
            marker=self.path.with_name(self.path.name+".created")
            if marker.exists() and not self.path.exists():
                raise LearningStop("B2 budget ledger deleted; preserve batch marker and stop")
            if self.path.exists():
                data=self._read()
                if (data.get("batch")!=self.batch or data.get("revision")!=self.revision or
                        data.get("policy")!=self.policy):
                    raise LearningStop("B2 budget belongs to another batch/condition revision; use a NEW batch")
            else:data={"schema":1,"policy":self.policy,"batch":self.batch,"revision":self.revision,
                       "b_fight_hp":0,"tail_hp":0,"events":[],"attempts":[],"execution":None,"stop":None}
            if event is not None and data["stop"] is None:
                if event.get("kind")=="execution":self._bind_execution(data,event["conditions"])
                elif event.get("kind")=="attempt":self._reserve_attempt(data,event)
                else:
                    event={**event,"worker":self.worker}
                    event["id"]=f"{self.worker}:{event['episode']}:{event['frame']}:{event['arm']}:{event.get('fatal')}"
                    if not any(x["id"]==event["id"] for x in data["events"]):
                        data["events"].append(event)
                        if event["tail"]:data["tail_hp"]+=event["hp_loss"]
                        elif event["arm"]=="B":data["b_fight_hp"]+=event["hp_loss"]
                        reasons=[]
                        if self.policy==STRICT_POLICY and data["b_fight_hp"]>=2:reasons.append("B fight cumulative 2 HP")
                        if (self.policy==STRICT_POLICY and not event["tail"] and event["arm"]=="B" and
                                event["hp_loss"]>0 and event["chain_related"]):
                            reasons.append("new chain-related fight injury; pause for diagnosis")
                        if event.get("fatal"):reasons.append(event["fatal"])
                        if reasons:data["stop"]={"frame":event["frame"],"episode":event["episode"],"worker":self.worker,
                                                   "reasons":reasons,"mode":"batch_end" if self.policy==STRICT_POLICY and data["b_fight_hp"]>=2 else "pause"}
            temp=self.path.with_name(self.path.name+f".tmp.{os.getpid()}")
            with temp.open("w",encoding="utf-8") as f:
                json.dump(data,f,ensure_ascii=False,indent=1);f.write("\n");f.flush();os.fsync(f.fileno())
            os.replace(temp,self.path)
            if not marker.exists():
                with marker.open("x",encoding="utf-8") as mf:
                    json.dump({"batch":self.batch,"revision":self.revision},mf)
                    mf.flush();os.fsync(mf.fileno())
            self.state=data
            return data
        finally:
            os.close(fd);lock.unlink()

    def _bind_execution(self,data,conditions):
        canonical=json.loads(json.dumps(conditions,sort_keys=True,allow_nan=False))
        digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        previous=data.get("execution")
        if previous is not None and (previous["sha256"]!=digest or previous["conditions"]!=canonical):
            raise LearningStop("B2 execution conditions changed; use a NEW batch")
        data["execution"]={"sha256":digest,"conditions":canonical}

    def _reserve_attempt(self,data,event):
        attempts=data.setdefault("attempts",[])
        identity=f"{self.worker}:{event['episode']}"
        if any(a["id"]==identity for a in attempts):
            raise LearningStop("B2 attempt already reserved; no automatic replacement/retry")
        arm=event["arm"]
        if len(attempts)>=8 or sum(a["arm"]==arm for a in attempts)>=4:
            data["stop"]={"mode":"batch_end","reasons":["B2 smoke upper limit: 8 total / 4 per arm"],
                          "worker":self.worker,"episode":event["episode"],"frame":None}
            return
        if data.get("execution") is None:raise LearningStop("B2 execution conditions must be bound before reservation")
        crossover=data["execution"]["conditions"].get("crossover")
        if crossover is not None:
            planned=crossover["schedule"]["attempts"]
            order=event.get("order")
            if (type(order) is not int or order!=len(attempts) or order>=len(planned) or
                    any(event.get(k)!=planned[order][k] for k in ("order","block","arm","seed"))):
                raise LearningStop("B2 attempt differs from frozen crossover order/arm/block/seed")
        attempts.append({"id":identity,"worker":self.worker,"episode":event["episode"],"arm":arm,
                         "seed":event["seed"],"policy_episode":event.get("policy_episode"),
                         "block":event.get("block"),"order":event.get("order"),
                         "execution_sha256":data["execution"]["sha256"],"status":"reserved"})

    def bind_execution(self,conditions):
        """Freeze CLI / ordinary planner switches too; A/B arm and seeds vary explicitly."""
        self._update({"kind":"execution","conditions":conditions})
        self.check()

    def begin_attempt(self,*,episode,arm,seed,policy_episode=None,block=None,order=None):
        """Atomic reservation BEFORE ready/reset; failures consume their slot."""
        if type(episode) is not int or episode<0 or arm not in {"A","B"} or type(seed) is not int:
            raise ValueError("invalid B2 attempt reservation")
        if any(v is not None and (type(v) is not int or v<0) for v in (block,order)):
            raise ValueError("invalid B2 crossover labels")
        self._update({"kind":"attempt","episode":episode,"arm":arm,"seed":seed,"policy_episode":policy_episode,
                      "block":block,"order":order})
        self.check()
        return dict(self.state["attempts"][-1])

    def _read(self):
        try:
            data=json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(data,dict) or data.get("schema")!=1 or not isinstance(data.get("events"),list)
                    or any(type(data.get(k)) is not int or data[k]<0 for k in ("b_fight_hp","tail_hp"))
                    or (data.get("stop") is not None and not isinstance(data["stop"],dict))):
                raise ValueError("invalid budget schema")
            if not isinstance(data.get("attempts",[]),list):raise ValueError("invalid attempts")
            if data.get("stop") is not None and not isinstance(data["stop"].get("reasons"),list):raise ValueError("invalid stop reason")
            return data
        except (OSError,ValueError) as exc:raise LearningStop("B2 budget missing/corrupt; preserve evidence") from exc

    def check(self):
        if self.path.with_name(self.path.name+".halt").exists():raise LearningStop("B2 integrity halt marker present")
        data=self._read()
        if (data.get("batch")!=self.batch or data.get("revision")!=self.revision or
                data.get("policy")!=self.policy):
            raise LearningStop("B2 budget identity changed")
        self.state=data
        if data["stop"] is not None:raise LearningStop("B2 stopped: "+"; ".join(data["stop"]["reasons"]))

    def observe(self,*,episode,frame,arm,hp_loss=0,chain_related=False,tail=False,fatal=None):
        if arm not in {"A","B"} or type(hp_loss) is not int or hp_loss<0:raise ValueError("invalid budget event")
        if hp_loss or fatal:
            self._update(dict(episode=int(episode),frame=int(frame),arm=arm,hp_loss=hp_loss,
                              chain_related=bool(chain_related),tail=bool(tail),fatal=fatal))
        self.check()


def preflight_environment(encounter, *, no_record=False):
    """Read-only preflight, before IPC/reset; stopped batches are never retried."""
    if os.environ.get("SSBOT_FORUM_CHAIN_B2","0").strip()!="1":return
    if (encounter!="Forum_W_w7" or no_record or
            os.environ.get("SSBOT_FORUM_CHAIN_NATIVE","0").strip()!="1"):
        raise LearningStop("B2 requires recorded Forum_W_w7 and explicit native mode")
    batch=os.environ.get("SSBOT_FORUM_CHAIN_BATCH","")
    path=os.environ.get("SSBOT_FORUM_CHAIN_BUDGET","")
    if not batch or not path or not os.environ.get("SSBOT_FORUM_CHAIN_PROBE","") or os.environ.get("SSBOT_FORUM_CHAIN_ARM") not in {"A","B"}:
        raise LearningStop("B2 needs named batch/probe, explicit arm and shared budget path")
    attempt_labels(0)
    crossover_schedule()
    p=Path(path)
    if p.with_name(p.name+".halt").exists():raise LearningStop("B2 integrity halt marker present; no retry")
    if p.with_name(p.name+".lock").exists():raise LearningStop("B2 budget lock present; no automatic retry")
    if p.with_name(p.name+".created").exists() and not p.exists():raise LearningStop("B2 ledger deleted; batch preserved")
    if p.exists():
        try:data=json.loads(p.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:raise LearningStop("B2 budget unreadable") from exc
        if data.get("batch")!=batch or data.get("stop") is not None:
            raise LearningStop("B2 prior batch stopped or identity differs; no automatic retry")


def mark_integrity_halt(reason, *, primary=None, primary_origin=None, secondary_origin=None):
    """Keep the first halt, with known original stop ahead of a later shell fault.

    Existing markers are immutable. Supplying primary changes provenance only:
    the marker still blocks every later preflight exactly as before.
    """
    path=os.environ.get("SSBOT_FORUM_CHAIN_BUDGET","")
    if not path:return
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p=p.with_name(p.name+".halt")
    try:
        with p.open("x",encoding="utf-8") as f:
            record={"batch":os.environ.get("SSBOT_FORUM_CHAIN_BATCH"),"reason":str(reason if primary is None else primary)}
            if primary is not None:
                record["primary_error_origin"]=primary_origin
                if str(reason)!=str(primary):
                    record["secondary_errors"]=[{"origin":secondary_origin or "integrity_halt","reason":str(reason)}]
            json.dump(record,f)
            f.flush();os.fsync(f.fileno())
    except FileExistsError:pass  # never replace the first failure


def preflight_options(options):
    """First-smoke invocation constraints; no IPC, file creation or process start."""
    preflight_environment(options.encounter,no_record=options.no_record)
    if os.environ.get("SSBOT_FORUM_CHAIN_B2","0").strip()!="1":return
    if (options.mode!="eval" or options.policy!="planner" or options.view!="oracle" or
            options.time_scale!=1. or options.real_quit!=1. or options.inject_hits!=0.):
        raise LearningStop("B2 requires eval/planner/oracle at1x, deterministic real quit=1, without injected hits")
    episodes=options.episodes
    if type(episodes) is not int or not 1<=episodes<=4:
        raise LearningStop("B2 first smoke allows 1..4 attempts per arm invocation")
    instances=getattr(options,"instances",None)
    if instances is not None:
        try:ids=[int(v) for v in instances.split(",")]
        except (TypeError,ValueError) as exc:raise LearningStop("invalid B2 instance list") from exc
        if not ids or len(ids)!=len(set(ids)) or min(ids)<0 or len(ids)*episodes>4:
            raise LearningStop("B2 invocation exceeds four attempts for one arm / invalid instances")


def execution_conditions(options,environ=None):
    """Condition identity shared by both arms; seeds are recorded per attempt."""
    env=os.environ if environ is None else environ
    keys=("encounter","mode","policy","view","threads","time_scale","timebox","real_quit","inject_hits",
          "start_hp","start_silk","silk_reserve","key_cost","forum_clash","no_record","rotate","same_seeds",
          "measure","measurement_protocol","measure_diagnostics","measure_timing_only","measure_max_records",
          "measure_stall_ms","measure_stall_tick","measure_stall_episode","engineering_probe")
    labels={"SSBOT_FORUM_CHAIN_ARM","SSBOT_FORUM_CHAIN_BATCH","SSBOT_FORUM_CHAIN_BUDGET",
            "SSBOT_FORUM_CHAIN_BLOCK","SSBOT_FORUM_CHAIN_ORDER"}
    crossover=crossover_schedule(env)
    return {"schema":1,"smoke_limit":{"total":8,"per_arm":4},
            "learning_policy":{"name":LOW_HP_POLICY,"remaining_hp":2,"scope":"episode","pause_then_real_quit":True},
            **({"crossover":crossover} if crossover is not None else {}),
            "options":{k:getattr(options,k,None) for k in keys},
            "environment":{k:v for k,v in sorted(env.items()) if k.startswith("SSBOT_") and k not in labels}}


def attempt_labels(episode, environ=None):
    """Explicit crossover labels; ORDER is this invocation's first global slot.

    No labels means unknown, never a block inferred from wall clock or episode.
    When a frozen schedule is supplied its exact slot is checked atomically at
    reservation. Multi-worker schedules must assign their slots explicitly.
    """
    env=os.environ if environ is None else environ
    raw=[env.get("SSBOT_FORUM_CHAIN_"+k,"").strip() for k in ("BLOCK","ORDER")]
    if not any(raw):return {"block":None,"order":None}
    if not all(raw):raise LearningStop("B2 crossover BLOCK and ORDER must be supplied together")
    try:values=[int(v) for v in raw]
    except (TypeError,ValueError) as exc:raise LearningStop("invalid B2 crossover BLOCK/ORDER") from exc
    if min(values)<0 or type(episode) is not int or episode<0:raise LearningStop("invalid B2 crossover BLOCK/ORDER")
    return {"block":values[0],"order":values[1]+episode}


def crossover_schedule(environ=None):
    """Bind a reviewable frozen sequence, separately from per-attempt labels.

    schema 1: {batch, attempts:[{order,block,arm,seed}, ...]}. Zero-based order is
    contiguous; a short engineering trial may have fewer than eight entries.
    The immutable content copy plus exact file hash is part of execution identity.
    """
    env=os.environ if environ is None else environ
    path=env.get("SSBOT_FORUM_CHAIN_SCHEDULE","").strip()
    if not path:return None
    try:
        raw=Path(path).read_bytes();schedule=json.loads(raw)
        rows=schedule["attempts"]
        if (schedule.get("schema")!=1 or schedule.get("batch")!=env.get("SSBOT_FORUM_CHAIN_BATCH")
                or not isinstance(rows,list) or not 1<=len(rows)<=8):raise ValueError("schema/batch/attempts")
        for i,row in enumerate(rows):
            if (type(row.get("order")) is not int or row["order"]!=i or type(row.get("block")) is not int
                    or row["block"]<0 or row.get("arm") not in {"A","B"} or type(row.get("seed")) is not int):
                raise ValueError("invalid order/block/arm/seed")
        if any(sum(r["arm"]==a for r in rows)>4 for a in ("A","B")):raise ValueError("per-arm limit")
        labels=attempt_labels(0,env)
        if labels["order"] is None:raise ValueError("schedule requires explicit BLOCK/ORDER")
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        raise LearningStop("B2 frozen crossover schedule invalid: "+str(exc)) from exc
    return {"sha256":hashlib.sha256(raw).hexdigest(),"schedule":schedule}
