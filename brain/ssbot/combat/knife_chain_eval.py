"""Caller-owned v0.1 chain evaluation core; no keyboard or native activation.

Ported from the formally delivered chain_v01.py, SHA256 11c6dedbc1d3972a43904b984134680e2144d8a958c873a1148453e32e647d6c.
Records come from the shared validated format rather than a second schema.
step() mutates only this evaluator's logical state; Run.sent is a proposed-key
trace, NEVER a transport receipt. Native callers use preview() on a private
copy; committing from real selection/send/observation remains a separate task.
Primitives must not mutate external globals: deepcopy is not a callable sandbox.
No production policy imports or activates this evaluator in this checkpoint.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from .knife_chain_format import (Rule, KeyComp, Link, Admission, Chain, SEND_AHEAD, MASK_NAMES,
                                DEFAULT_VOCABULARY)
from .knife_chain_bindings import bind_chains

FORMAT_VERSION = "0.1"
CATEGORIES = {"A": "observation / math / hold filter", "B": "key template", "C": "planning module (not migrated)"}
NOT_ENCODED = "not encoded:"

class Prims:
    """The fixed vocabulary, each entry with its kind and category (A / B / C, CATEGORIES)."""

    def __init__(self):
        self.guards: dict[str, Callable] = {}
        self.values: dict[str, Callable] = {}
        self.gens: dict[str, Callable] = {}
        self.acts: dict[str, Callable] = {}
        self.dirs: dict[str, Callable] = {}
        self.meta: dict[tuple, dict] = {}

    def _reg(self, table, kind, name, cat, doc):
        def deco(fn):
            table[name] = fn
            self.meta[(kind, name)] = {"kind": kind, "name": name, "category": cat,
                                       "doc": (doc or (fn.__doc__ or "")).strip().split("\n")[0]}
            return fn
        return deco

    def guard(self, name, cat="A", doc=""):
        """A guard primitive; also usable in an expression as the boolean value {"fn": name, args} (values table)."""
        def deco(fn):
            self._reg(self.guards, "guard", name, cat, doc)(fn)
            self.values.setdefault(name, lambda x, _fn=fn, **kw: bool(_fn(x, **kw)))
            return fn
        return deco

    def value(self, name, cat="A", doc=""):
        return self._reg(self.values, "value", name, cat, doc)

    def gen(self, name, cat="B", doc=""):
        return self._reg(self.gens, "keygen", name, cat, doc)

    def action(self, name, cat="A", doc=""):
        return self._reg(self.acts, "action", name, cat, doc)

    def direction(self, name, cat="B", doc=""):
        return self._reg(self.dirs, "direction", name, cat, doc)

    def planner(self, name, cat="C", doc=""):
        """A planning module, called through `act` ({"a": name, "store": ..., args})."""
        return self._reg(self.acts, "planner", name, cat, doc)

    def catalog(self) -> list[dict]:
        return sorted(self.meta.values(), key=lambda m: (m["category"], m["kind"], m["name"]))


# ---- the interpreter -----------------------------------------------------------------------------------------------

class Run:
    def __init__(self, chain: str, link: str, v: dict):
        self.chain, self.link = chain, link
        self.v = v
        self.sent: list = []
        self.trace: list = []
        self.path: list = []
        self.closed: str | None = None
        self.entered: dict | None = None     # external entry: {"f", "link", "via", "sources"}

    @property
    def lid(self) -> str:
        return f"{self.chain}.{self.link}"


class X:
    def __init__(self, runner: "ChainRunner", run: Run | None, obs):
        self.R, self.run, self.obs = runner, run, obs
        self.mask: int | None = None
        self.tmp: dict = {}

    @property
    def cfg(self) -> dict:
        return self.R.chains[self.run.chain].cfg if self.run is not None else self.R.cfg0

    @property
    def v(self) -> dict:
        return self.run.v

    def clock(self, name: str):
        return self.R.anchor.clock(self, name)


LAZY = ("if", "and", "or")


def register_core(P: Prims) -> None:
    """The generic math / access / logic functions every family's expressions may call (category A)."""
    import math

    @P.value("mul", doc="the product of the operands (of)")
    def _mul(x, of):
        return math.prod(of)

    @P.value("div", doc="a / b")
    def _div(x, a, b):
        return a / b

    @P.value("abs", doc="|v|")
    def _abs(x, v):
        return abs(v)

    @P.value("neg", doc="-v")
    def _neg(x, v):
        return -v

    @P.value("int", doc="int(v) (toward zero)")
    def _int(x, v):
        return int(v)

    @P.value("round", doc="round(v, n)")
    def _round(x, v, n):
        return round(v, n)

    @P.value("clamp", doc="v limited to [lo, hi]")
    def _clamp(x, v, lo, hi):
        return min(max(v, lo), hi)

    @P.value("idx", doc="v[i] (None: None)")
    def _idx(x, v, i):
        return None if v is None else v[i]

    @P.value("attr", doc="a field of a record (None: None)")
    def _attr(x, v, name):
        if v is None:
            return None
        return v.get(name) if isinstance(v, dict) else getattr(v, name)

    @P.value("append", doc="the list with item appended (a new list)")
    def _append(x, list, item):                    # noqa: A002
        return [*(list or []), item]

    @P.value("last", doc="the list's last item (empty / None: None)")
    def _last(x, v):
        return v[-1] if v else None

    @P.value("fmt", doc="template.format(args)")
    def _fmt(_ctx, template, **kw):                # the template's own names may include x
        return template.format(**kw)

    @P.value("tuple", doc="the operands as a tuple")
    def _tuple(x, of):
        return tuple(of)

    @P.value("bits", doc="a static mask of MASK_NAMES (\"D|A\")")
    def _bits(x, spec):
        return sum(MASK_NAMES[p.strip()] for p in str(spec).split("|"))

    @P.value("not", doc="not v")
    def _not(x, v):
        return not v

    for name, doc in (("if", "lazy: then if c else else"), ("and", "lazy: all operands (of) true"),
                      ("or", "lazy: any operand (of) true")):
        P.value(name, doc=doc)(lambda x, **kw: None)


def store(x: X, target: str, value) -> None:
    """Write a result to a tick scratch name ("tmp.name" / "var.tmp.name") or a run variable ("name" / "var.name")."""
    if target.startswith("var."):
        target = target[4:]
    if target.startswith("tmp."):
        x.tmp[target[4:]] = value
    else:
        x.v[target] = value


class ChainRunner:
    def __init__(self, chains: dict, anchor, prims: Prims, cfg0: dict | None = None, *,
                 observation_names, literal_names=(), context_names=(), vocabulary=DEFAULT_VOCABULARY):
        self.chains = deepcopy(chains)
        self.binding = bind_chains(self.chains, primitives=prims, observation_names=observation_names,
                                   literal_names=literal_names, context_names=context_names, vocabulary=vocabulary)
        self.anchor = anchor
        self.P = prims
        self.cfg0 = deepcopy(cfg0) if cfg0 is not None else {}
        self.reset()

    def preview(self, *args, **kwargs):
        """Evaluate a private draft without committing run state or touching input objects.

        Copy the runner AND inputs together to preserve aliases inside the draft.
        This conservative copy has no certified live-tick budget; a family adapter
        must also keep primitive effects confined to its supplied context.
        """
        trial, copied_args, copied_kwargs = deepcopy((self, args, kwargs))
        mask = trial.step(*copied_args, **copied_kwargs)
        f = args[0] if args else kwargs["f"]
        return ChainPreview(f, mask, trial)

    def reset(self) -> None:
        self.run: Run | None = None
        self.done: list[Run] = []
        self.fired: dict = {}
        self.unsupported: list = []          # [f, link, why] of each abort "not encoded: ..." (replays: an error)
        self.anchor.reset(self)

    def _fire(self, run: Run, i: int, r: Rule, tag: str = "") -> None:
        key = f"{run.lid}#{i}:{r.do}{tag}"
        self.fired[key] = self.fired.get(key, 0) + 1

    # ---- expressions ----

    def ev(self, x: X, e):
        if e is None or isinstance(e, (bool, int, float)):
            return e
        if isinstance(e, str):
            if e == "k":
                return x.clock("antic")
            if e.startswith("cfg."):
                return x.cfg.get(e[4:])
            if e.startswith("var.tmp."):
                return x.tmp.get(e[8:])
            if e.startswith("var."):
                return x.v.get(e[4:])
            if e.startswith("tmp."):
                raise KeyError(f"scratch reference {e!r}: write var.{e}")
            if e.startswith("clk."):
                return x.clock(e[4:])
            if e.startswith("obs."):
                return getattr(x.obs, e[4:])
            return e
        if isinstance(e, list):
            return [self.ev(x, a) for a in e]
        if not isinstance(e, dict):
            return e
        if "lit" in e:
            return e["lit"]
        if "fn" in e:
            name = e["fn"]
            if name == "if":
                return self.ev(x, e["then"]) if self.ev(x, e["c"]) else self.ev(x, e.get("else"))
            if name == "and":
                return all(self.ev(x, a) for a in e["of"])
            if name == "or":
                return any(self.ev(x, a) for a in e["of"])
            args = {k: self.ev(x, v) for k, v in e.items() if k != "fn"}
            return self.P.values[name](x, **args)
        (op, a), = e.items()
        vals = [self.ev(x, y) for y in a]
        if op == "add":
            return sum(vals)
        if op == "sub":
            return vals[0] - vals[1]
        if op == "min":
            return min(vals)
        if op == "max":
            return max(vals)
        raise KeyError(f"expression operator {op!r}")

    def guard(self, x: X, g) -> bool:
        if g is None:
            return True
        if "all" in g:
            return all(self.guard(x, a) for a in g["all"])
        if "any" in g:
            return any(self.guard(x, a) for a in g["any"])
        if "not" in g:
            return not self.guard(x, g["not"])
        args = {k: self.ev(x, v) for k, v in g.items() if k != "p"}
        return bool(self.P.guards[g["p"]](x, **args))

    # ---- keys ----

    def mask_of(self, x: X, spec) -> int:
        if spec is None:
            return 0
        if isinstance(spec, int):
            return spec
        if isinstance(spec, dict):
            m = self.keys(x, self.link(x.run.chain, x.run.link), only=spec.get("only")) \
                if spec.get("keys") == "self" else 0
            for o in spec.get("or", ()):
                m |= self.mask_of(x, o)
            return m
        m = 0
        for part in str(spec).split("|"):
            part = part.strip()
            if part in MASK_NAMES:
                m |= MASK_NAMES[part]
            elif part in self.P.dirs:
                m |= int(self.P.dirs[part](x))
            elif part:
                raise KeyError(f"mask name {part!r}")
        return m

    def keys(self, x: X, link: Link, only: list | None = None) -> int:
        m = 0
        for kc in link.keys:
            if only is not None and kc.name not in only:
                continue
            if kc.lo is not None or kc.hi is not None:
                c = x.clock(kc.clock)
                if c is None:
                    continue
                lo, hi = self.ev(x, kc.lo), self.ev(x, kc.hi)
                if (lo is not None and c < lo) or (hi is not None and c > hi):
                    continue
            if kc.when is not None and not self.guard(x, kc.when):
                continue
            m0 = m
            if kc.gen is not None:
                m = int(self.P.gens[kc.gen](x, m, **{k: self.ev(x, v) for k, v in kc.args.items()}))
            else:
                m |= self.mask_of(x, kc.mask)
            if m != m0:
                key = f"{link.id}@{kc.name or kc.gen or kc.mask}"
                self.fired[key] = self.fired.get(key, 0) + 1
        return m

    # ---- links ----

    def link(self, chain: str, name: str) -> Link:
        return self.chains[chain].links[name]

    def _target(self, run: Run, to: str) -> tuple[str, str]:
        if "." in to:
            c, l_ = to.split(".", 1)
            return c, l_
        return run.chain, to

    def _rules(self, link: Link, chain: str) -> list:
        out = []
        for rs in link.inherit:
            out += self.chains[chain].rulesets[rs]
        return out + list(link.rules)

    def _why(self, x: X, w) -> str:
        """A reason: a scalar string is structural text; an expression (object) is evaluated."""
        if isinstance(w, (dict, list)):
            return str(self.ev(x, w))
        return w or ""

    def _apply_set(self, x: X, sets: dict) -> None:
        vals = {k: self.ev(x, v) for k, v in sets.items()}
        for k, v in vals.items():
            store(x, k, v)

    def _act(self, x: X, act: dict):
        return self.P.acts[act["a"]](x, **{k: (v if k == "store" else self.ev(x, v)) for k, v in act.items()
                                           if k != "a"})

    def _switch(self, x: X, to: str, note: str = "") -> None:
        run = x.run
        c, l_ = self._target(run, to)
        run.path.append([x.obs.f, f"{run.lid} -> {c}.{l_}", note])
        run.chain, run.link = c, l_

    def _emit(self, x: X, m: int, link: Link):
        for r in link.post:
            if self.guard(x, r.when):
                self.anchor.close(x, r.do, self._why(x, r.why))
                return None
        x.run.sent.append((x.obs.f + SEND_AHEAD, int(m)))
        x.run.trace.append([x.obs.f, x.run.lid, int(m)])
        return int(m)

    def enter_check(self, x: X, to: str) -> bool:
        """try: the target link's entry guard."""
        c, l_ = self._target(x.run, to)
        return self.guard(x, self.link(c, l_).entry)

    def _outcome(self, x: X, out: dict, link: Link, note: str, depth: int):
        do = out.get("do")
        if do == "abort":
            self.anchor.close(x, "abort", out.get("why", ""))
            return None
        if do in ("hold", "closed"):
            return None
        if do == "goto":
            self._apply_set(x, out.get("set", {}))
            self._switch(x, out["to"], out.get("note", note))
            if out.get("mode", "same") == "next":
                return self._emit(x, self.keys(x, link), link)
            return self.eval_link(x, depth + 1)
        raise ValueError(f"action outcome {out!r}")

    def eval_link(self, x: X, depth: int = 0):
        if depth > 16:
            raise RuntimeError(f"link loop at {x.run.lid}")
        run = x.run
        link = self.link(run.chain, run.link)
        for i, r in enumerate(self._rules(link, run.chain)):
            if not self.guard(x, r.when):
                continue
            self._fire(run, i, r)
            if r.pre:
                self._apply_set(x, r.pre)
            if r.act is not None:
                out = self._act(x, r.act)
                if out is not None:
                    return self._outcome(x, out, link, r.note, depth)
            if r.do in ("set", "act"):
                self._apply_set(x, r.set)
                continue
            if r.do == "keys":
                self._apply_set(x, r.set)
                break
            if r.do == "hold":
                self._apply_set(x, r.set)
                if r.why is not None:
                    run.v["why"] = self._why(x, r.why)
                return None
            if r.do in ("abort", "done"):
                self._apply_set(x, r.set)
                why = self._why(x, r.why)
                if r.do == "abort" and why.startswith(NOT_ENCODED):
                    self.unsupported.append([x.obs.f, run.lid, why])
                self.anchor.close(x, r.do, why)
                if r.do == "done" and self.anchor.reopen_wanted(why):
                    return self.anchor.reopen(x)
                return None
            if r.do == "try":
                ok = self.enter_check(x, r.to)
                self._fire(run, i, r, ":ok" if ok else ":fail")
                if ok:
                    self._apply_set(x, r.set)
                    self._switch(x, r.to, r.note)
                    return self.eval_link(x, depth + 1)
                if r.orelse == "hold":
                    return None
                continue
            if r.do == "goto":
                if r.mode == "next":
                    m = self.keys(x, link)
                    self._apply_set(x, r.set)
                    self._switch(x, r.to, r.note)
                    return self._emit(x, m, link)
                if r.mode == "emit":
                    m = self.mask_of(x, r.emit)
                    self._apply_set(x, r.set)
                    self._switch(x, r.to, r.note)
                    return self._emit(x, m, link)
                self._apply_set(x, r.set)
                self._switch(x, r.to, r.note)
                if r.mode == "keys":
                    lk = self.link(x.run.chain, x.run.link)
                    return self._emit(x, self.keys(x, lk), lk)
                return self.eval_link(x, depth + 1)
            raise ValueError(f"rule do {r.do!r}")
        m = self.keys(x, link)
        x.mask = m
        for i, r in enumerate(link.after_keys):
            if not self.guard(x, r.when):
                continue
            self._fire(run, 100 + i, r)
            if r.act is not None:
                self._act(x, r.act)
            self._apply_set(x, r.set)
            if r.do == "goto":
                self._switch(x, r.to, r.note)
                break
        return self._emit(x, m, link)

    def probe_entry(self, x: X, link: Link) -> str | None:
        """An external entry link (entry guard, `set` recovery rules, one `goto` whose guard is the check): its
        target when it applies now (the run's variables recovered), else None. No key is produced here."""
        if not self.guard(x, link.entry):
            return None
        for r in self._rules(link, x.run.chain):
            if r.do == "set":
                if self.guard(x, r.when):
                    self._apply_set(x, r.set)
            elif r.do == "goto":
                return r.to if self.guard(x, r.when) else None
            else:
                raise ValueError(f"entry link {link.id}: rule {r.do!r}")
        return None

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, t_game: float | None = None, skip=None,
             sim=None, guard=None, bombs=None):
        """The mask for frame f + 2 from the STATE of frame f, or None (the planner decides)."""
        return self.anchor.step(self, f, s, ground, accepting, t_game, skip, sim, guard, bombs)



@dataclass(frozen=True)
class ChainPreview:
    frame: int
    mask: int | None
    draft: ChainRunner
