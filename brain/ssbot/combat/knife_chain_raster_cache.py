"""Exact pure dilation reuse during one B2 proposal, and across one V2Feed's per-tick support builds (this tick's and the
previous tick's only); never query/safety reuse."""
from contextlib import contextmanager
from contextvars import ContextVar
import numpy as np
from .knife_chain_cs_cache import _value

_CURRENT=ContextVar("b2_exact_dilation",default=None)


class ExactDilationCache:
    def __init__(self):
        self.entries={};self.active=True;self.hits=self.misses=self.uncacheable=0

    def _key(self,parts,m,cell,compute,context):
        # Numeric content is a complete key only for native arrays/scalars.
        # Subclasses can override view/arithmetic used by the original
        # compute, so they retain that original behavior on every call.
        values=[m,cell,*context,*[v for _,x,y in parts for v in (x,y)]]
        if any(type(a) is not np.ndarray for a,_,_ in parts):
            raise TypeError("array subclass is not a pure raster input")
        if any(not (type(v) in (bool,int,float) or
                    isinstance(v,np.generic) and type(v) is v.dtype.type and v.dtype.kind in "biuf")
               for v in values):
            raise TypeError("unknown scalar representation is not a pure numeric input")
        key=(compute,_value(context),_value(m),_value(cell),
             tuple((_value(a),_value(x),_value(y)) for a,x,y in parts))
        hash(key)
        return key

    def _get(self,key):return self.entries.get(key)

    def _put(self,key,entry):self.entries[key]=entry

    def apply(self,parts,m,cell,compute,context):
        if not self.active:return compute(parts,m,cell)
        parts=list(parts)
        try:key=self._key(parts,m,cell,compute,context)
        except (TypeError,AttributeError,ValueError):
            self.uncacheable+=1
            return compute(parts,m,cell)
        hit=self._get(key)
        if hit is not None:
            self.hits+=1;a,x,y=hit
            return a.copy(),x,y
        self.misses+=1
        a,x,y=compute(parts,m,cell)
        self._put(key,(a.copy(),x,y))
        return a,x,y

    def clear(self):
        self.entries.clear();self.active=False

    def stats(self):
        return {"hits":self.hits,"misses":self.misses,"uncacheable":self.uncacheable,
                "entries":len(self.entries),"active":self.active}


class SupportDilationCache(ExactDilationCache):
    """Task 182 seq 287: ExactDilationCache's reuse (the same complete content key, private copies, unknown inputs computed
    as before) across the per-tick support builds of ONE owner (a V2Feed, never shared).

    Only pure dilation results: no owner, hazard, clock, path or safety conclusion is stored. The lifetime is the tick and
    the one before it: begin(frame) of a later frame drops everything but the last tick's results (a skipped frame is no
    tick), a result the build used this tick counts as this tick's (so a key not used for two ticks is gone); the same
    frame keeps them (a second build of the tick); an earlier frame (a rewind) and reset() clear both. Stays bounded:
    past MAX_ENTRIES in one tick a result is computed and not stored."""
    MAX_ENTRIES=4096

    def __init__(self):
        super().__init__()
        self.previous={};self.frame=None

    def begin(self,frame):
        if self.frame is None or frame>self.frame:
            self.previous,self.entries=self.entries,{}
        elif frame<self.frame:
            self.previous,self.entries={},{}
        self.frame=frame

    def reset(self):
        self.previous,self.entries={},{}
        self.frame=None

    def _get(self,key):
        hit=self.entries.get(key)
        if hit is None:
            hit=self.previous.get(key)
            if hit is not None:self._put(key,hit)
        return hit

    def _put(self,key,entry):
        if len(self.entries)<self.MAX_ENTRIES:self.entries[key]=entry

    def stats(self):
        return {**super().stats(),"previous":len(self.previous),"frame":self.frame}


def current_dilation_cache():return _CURRENT.get()


@contextmanager
def exact_dilation_scope():
    prior=_CURRENT.get()
    if prior is not None and not isinstance(prior,SupportDilationCache):
        yield prior
        return
    # (a proposal never borrows a support build's cache: its results stay the proposal's, its lifetime unchanged)
    cache=ExactDilationCache();token=_CURRENT.set(cache)
    try:yield cache
    finally:
        _CURRENT.reset(token);cache.clear()


@contextmanager
def support_dilation_scope(cache,frame):
    """One support build of tick `frame` served by `cache`. Inside an active scope (a B2 proposal building a support) that
    scope keeps serving as before and `cache` is not touched. The scope always ends with the build, also on an exception
    (the results already stored are exact, so they may stay for the tick)."""
    if _CURRENT.get() is not None:
        yield _CURRENT.get()
        return
    cache.begin(frame)
    token=_CURRENT.set(cache)
    try:yield cache
    finally:_CURRENT.reset(token)
