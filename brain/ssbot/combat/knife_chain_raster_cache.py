"""Exact pure dilation reuse during one B2 proposal, never query/safety reuse."""
from contextlib import contextmanager
from contextvars import ContextVar
import numpy as np
from .knife_chain_cs_cache import _value

_CURRENT=ContextVar("b2_exact_dilation",default=None)


class ExactDilationCache:
    def __init__(self):
        self.entries={};self.active=True;self.hits=self.misses=self.uncacheable=0

    def apply(self,parts,m,cell,compute,context):
        if not self.active:return compute(parts,m,cell)
        parts=list(parts)
        try:
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
        except (TypeError,AttributeError,ValueError):
            self.uncacheable+=1
            return compute(parts,m,cell)
        if key in self.entries:
            self.hits+=1;a,x,y=self.entries[key]
            return a.copy(),x,y
        self.misses+=1
        a,x,y=compute(parts,m,cell)
        self.entries[key]=(a.copy(),x,y)
        return a,x,y

    def clear(self):
        self.entries.clear();self.active=False

    def stats(self):
        return {"hits":self.hits,"misses":self.misses,"uncacheable":self.uncacheable,
                "entries":len(self.entries),"active":self.active}


def current_dilation_cache():return _CURRENT.get()


@contextmanager
def exact_dilation_scope():
    prior=_CURRENT.get()
    if prior is not None:
        yield prior
        return
    cache=ExactDilationCache();token=_CURRENT.set(cache)
    try:yield cache
    finally:
        _CURRENT.reset(token);cache.clear()
