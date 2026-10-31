"""Exact ClawStrike strike-evaluation reuse inside ONE private actual step.

No geometry/safety weakening: a miss runs the original candidate grid/evaluate.
Inputs that change cannot borrow its result. Parameters, terrain and individual
TLS objects must remain read-only during this scope; their identities are held
strongly so id reuse cannot alias a previous input. Never carry this cache into
another observed/model step. Plan results are privately copied on store and hit.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import fields,is_dataclass,replace
import struct
import numpy as np

MISSING=object()


def _value(v):
    if isinstance(v,np.ndarray):
        if v.dtype.hasobject:raise TypeError("object array is not an exact numeric key")
        return ("array",v.dtype.str,v.shape,np.ascontiguousarray(v).tobytes())
    if isinstance(v,np.generic):return ("scalar",v.dtype.str,v.tobytes())
    if v is None:return ("none",)
    if type(v) is bool:return ("bool",v)
    if type(v) is int:return ("int",v)
    if type(v) is float:return ("float",struct.pack("!d",v))
    if type(v) is str:return ("str",v)
    if isinstance(v,(tuple,list)):return (type(v).__name__,tuple(_value(x) for x in v))
    if is_dataclass(v):
        return (type(v).__module__,type(v).__qualname__,tuple((f.name,_value(getattr(v,f.name))) for f in fields(v)))
    raise TypeError("unsupported exact strike key input")


class ExactCsStepCache:
    def __init__(self):
        self._entries={};self._readonly={};self.active=True
        self.hits=self.misses=self.stores=self.uncacheable=0

    def _identity(self,obj):
        self._readonly[id(obj)]=obj
        return id(obj)

    def key(self,owner,sim,ctx,a_entry,toward,coarse):
        if not self.active:return None
        try:
            # Include every HoldState lane and every CsCtx scalar, including the
            # target identity and the OTHER body. No rounded coordinates/time.
            hold=tuple((f.name,_value(getattr(sim.hold,f.name))) for f in fields(sim.hold))
            context=tuple((f.name,_value(getattr(ctx,f.name))) for f in fields(ctx) if f.name!="tls")
            return (_value(sim.start),_value(sim.prefix),hold,_value(sim.f),_value(sim.fo),context,
                    _value(a_entry),_value(toward),_value(coarse),_value(owner.cfg),
                    self._identity(sim.params),self._identity(sim.terrain),
                    tuple(self._identity(tl) for tl in ctx.tls))
        except (TypeError,AttributeError):
            # Unknown input representations lose the optimization, never the
            # original evaluation or an exception raised by that evaluation.
            self.uncacheable+=1
            return None

    def lookup(self,key):
        if not self.active:return MISSING
        value=self._entries.get(key,MISSING)
        if value is MISSING:
            self.misses+=1
            return MISSING
        self.hits+=1
        return [replace(p) for p in value]

    def put(self,key,plans):
        if self.active:
            self._entries[key]=tuple(replace(p) for p in plans)
            self.stores+=1

    def clear(self):
        self._entries.clear();self._readonly.clear();self.active=False

    def stats(self):
        return {"hits":self.hits,"misses":self.misses,"stores":self.stores,"uncacheable":self.uncacheable,
                "entries":len(self._entries),"active":self.active}


@contextmanager
def exact_cs_step(anchor,*,enabled=True):
    """Attach exact reuse only to this private preview anchor's one step.

    The caller owns the preview anchor, not the live controller anchor. Retain
    normal cfg/parameter initialization in its private ClawStrike after exit,
    but remove every cached value/reference even when the step raises. A default
    CS instance never has an active cache. Disabled scopes do not touch it.
    """
    if not enabled:
        yield None
        return
    from .claw_strike import ClawStrike,CsCfg
    old=anchor.csx
    if old is not None and getattr(old,"_exact_cs_step_cache",None) is not None:
        raise RuntimeError("exact CS step scopes cannot nest on the same anchor")
    private=(ClawStrike(CsCfg.from_env()) if old is None else ClawStrike(old.cfg,old.params,old.terrain))
    cache=ExactCsStepCache();private._exact_cs_step_cache=cache;anchor.csx=private
    try:yield cache
    finally:
        private._exact_cs_step_cache=None
        cache.clear()
