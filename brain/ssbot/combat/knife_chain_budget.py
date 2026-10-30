"""Persistent strict B2 learning budget shared by serial/parallel collector arms.

This is experiment accounting, never a controller. Atomic updates retain failures
and latch a stop before the policy can request another combat ACTION. A corrupt /
busy ledger is an integrity failure, not permission to reset the experiment.
"""
from __future__ import annotations
import json
import os
from pathlib import Path


class LearningStop(RuntimeError):
    pass


class LearningBudget:
    def __init__(self,path,*,batch,revision,worker):
        if not batch or not revision or not worker:raise ValueError("budget needs frozen batch/revision/worker")
        self.path=Path(path);self.batch=batch;self.revision=revision;self.worker=worker
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.state=None
        self._update(None)
        self.check()

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
                if data.get("batch")!=self.batch or data.get("revision")!=self.revision:
                    raise LearningStop("B2 budget belongs to another batch/condition revision; use a NEW batch")
            else:data={"schema":1,"policy":"strict-2hp-v1","batch":self.batch,"revision":self.revision,
                       "b_fight_hp":0,"tail_hp":0,"events":[],"stop":None}
            if event is not None and data["stop"] is None:
                event={**event,"worker":self.worker}
                event["id"]=f"{self.worker}:{event['episode']}:{event['frame']}:{event['arm']}:{event.get('fatal')}"
                if not any(x["id"]==event["id"] for x in data["events"]):
                    data["events"].append(event)
                    if event["tail"]:data["tail_hp"]+=event["hp_loss"]
                    elif event["arm"]=="B":data["b_fight_hp"]+=event["hp_loss"]
                    reasons=[]
                    if data["b_fight_hp"]>=2:reasons.append("B fight cumulative 2 HP")
                    if not event["tail"] and event["arm"]=="B" and event["hp_loss"]>0 and event["chain_related"]:
                        reasons.append("new chain-related fight injury; pause for diagnosis")
                    if event.get("fatal"):reasons.append(event["fatal"])
                    if reasons:data["stop"]={"frame":event["frame"],"episode":event["episode"],"worker":self.worker,
                                               "reasons":reasons,"mode":"batch_end" if data["b_fight_hp"]>=2 else "pause"}
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

    def _read(self):
        try:
            data=json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(data,dict) or data.get("schema")!=1 or not isinstance(data.get("events"),list)
                    or any(type(data.get(k)) is not int or data[k]<0 for k in ("b_fight_hp","tail_hp"))
                    or (data.get("stop") is not None and not isinstance(data["stop"],dict))):
                raise ValueError("invalid budget schema")
            return data
        except (OSError,ValueError) as exc:raise LearningStop("B2 budget missing/corrupt; preserve evidence") from exc

    def check(self):
        if self.path.with_name(self.path.name+".halt").exists():raise LearningStop("B2 integrity halt marker present")
        data=self._read()
        if data.get("batch")!=self.batch or data.get("revision")!=self.revision:
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
    p=Path(path)
    if p.with_name(p.name+".halt").exists():raise LearningStop("B2 integrity halt marker present; no retry")
    if p.with_name(p.name+".lock").exists():raise LearningStop("B2 budget lock present; no automatic retry")
    if p.with_name(p.name+".created").exists() and not p.exists():raise LearningStop("B2 ledger deleted; batch preserved")
    if p.exists():
        try:data=json.loads(p.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:raise LearningStop("B2 budget unreadable") from exc
        if data.get("batch")!=batch or data.get("stop") is not None:
            raise LearningStop("B2 prior batch stopped or identity differs; no automatic retry")


def mark_integrity_halt(reason):
    """Keep a halt even when config/bootstrap failed before budget construction."""
    path=os.environ.get("SSBOT_FORUM_CHAIN_BUDGET","")
    if not path:return
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p=p.with_name(p.name+".halt")
    try:
        with p.open("x",encoding="utf-8") as f:
            json.dump({"batch":os.environ.get("SSBOT_FORUM_CHAIN_BATCH"),"reason":str(reason)},f)
            f.flush();os.fsync(f.fileno())
    except FileExistsError:pass  # never replace the first failure
