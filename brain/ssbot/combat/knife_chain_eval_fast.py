"""Slam-family bound expression cache for B2; semantics stay in ChainRunner.

Cache expression structure, NEVER guard results, observations, configs or keys.
Unknown ad-hoc expressions still use the reference evaluator. The ordinary and
prototype evaluators retain their original path when B2 is off.
"""
from __future__ import annotations
from .knife_chain_eval import ChainRunner


def _value(e):
    if e is None or isinstance(e,(bool,int,float)):
        return lambda x:e
    if isinstance(e,str):
        if e=="k":return lambda x:x.clock("antic")
        if e.startswith("cfg."):
            name=e[4:];return lambda x:x.cfg.get(name)
        if e.startswith("var.tmp."):
            name=e[8:];return lambda x:x.tmp.get(name)
        if e.startswith("var."):
            name=e[4:]
            def read(x):
                v=x.v.get(name);notify=getattr(x.R.anchor,"read_value",None)
                if notify is not None:notify(x,name,v)
                return v
            return read
        if e.startswith("tmp."):
            def bad(x):raise KeyError(f"scratch reference {e!r}: write var.{e}")
            return bad
        if e.startswith("clk."):
            name=e[4:];return lambda x:x.clock(name)
        if e.startswith("obs."):
            name=e[4:];return lambda x:getattr(x.obs,name)
        return lambda x:e
    if isinstance(e,list):
        fns=tuple(_value(a) for a in e);return lambda x:[f(x) for f in fns]
    if not isinstance(e,dict):return lambda x:e
    if "lit" in e:
        v=e["lit"];return lambda x:v
    if "fn" in e:
        name=e["fn"]
        if name=="if":
            c,a,b=_value(e["c"]),_value(e["then"]),_value(e.get("else"))
            return lambda x:a(x) if c(x) else b(x)
        if name in {"and","or"}:
            fns=tuple(_value(a) for a in e["of"])
            return (lambda x:all(f(x) for f in fns)) if name=="and" else (lambda x:any(f(x) for f in fns))
        args=tuple((k,_value(v)) for k,v in e.items() if k!="fn")
        return lambda x:x.R.P.values[name](x,**{k:f(x) for k,f in args})
    (op,args),=e.items();fns=tuple(_value(a) for a in args)
    if op=="add":return lambda x:sum(f(x) for f in fns)
    if op=="sub":
        a,b=fns;return lambda x:a(x)-b(x)
    if op=="min":return lambda x:min(f(x) for f in fns)
    if op=="max":return lambda x:max(f(x) for f in fns)
    def bad(x):raise KeyError(f"expression operator {op!r}")
    return bad


def _guard(g):
    if g is None:return lambda x:True
    if "all" in g:
        fns=tuple(_guard(a) for a in g["all"]);return lambda x:all(f(x) for f in fns)
    if "any" in g:
        fns=tuple(_guard(a) for a in g["any"]);return lambda x:any(f(x) for f in fns)
    if "not" in g:
        fn=_guard(g["not"]);return lambda x:not fn(x)
    name=g["p"];args=tuple((k,_value(v)) for k,v in g.items() if k!="p")
    return lambda x:bool(x.R.P.guards[name](x,**{k:f(x) for k,f in args}) )


class BoundSlamRunner(ChainRunner):
    def ev(self,x,e):
        item=self._bound_values.get(id(e))
        return item[1](x) if item is not None and item[0] is e else super().ev(x,e)

    def guard(self,x,g):
        item=self._bound_guards.get(id(g))
        return item[1](x) if item is not None and item[0] is g else super().guard(x,g)

    def _rules(self,link,chain):
        item=self._bound_rules.get((chain,link.id))
        return item if item is not None else super()._rules(link,chain)

    def fork_empty(self,anchor):
        fork=super().fork_empty(anchor)
        fork._bound_values=self._bound_values;fork._bound_guards=self._bound_guards;fork._bound_rules=self._bound_rules
        return fork


def bind_slam_runner(runner):
    if isinstance(runner,BoundSlamRunner):return runner
    if type(runner) is not ChainRunner:return runner
    out=BoundSlamRunner.__new__(BoundSlamRunner);out.__dict__.update(runner.__dict__)
    values={};guards={};rules={}
    def ev(e):values[id(e)]=(e,_value(e))
    def guard(g):guards[id(g)]=(g,_guard(g))
    for cid,chain in out.chains.items():
        for link in chain.links.values():
            rows=ChainRunner._rules(out,link,cid);rules[cid,link.id]=tuple(rows)
            guard(link.entry)
            for r in [*rows,*link.post]:
                guard(r.when)
                for v in r.pre.values():ev(v)
                for v in r.set.values():ev(v)
                if isinstance(r.why,(dict,list)):ev(r.why)
                if r.act:
                    for k,v in r.act.items():
                        if k not in {"a","store"}:ev(v)
            for key in link.keys:
                ev(key.lo);ev(key.hi);guard(key.when)
                for v in key.args.values():ev(v)
    out._bound_values=values;out._bound_guards=guards;out._bound_rules=rules
    return out
