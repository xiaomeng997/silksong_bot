"""Private nominal projection of selected hook and control-strike programs.

This defines a candidate program, not a cache of safety or runtime guard results.
The original C5 strike_search/check validates the plan once at conditional control;
model futures then hold its commands. Real runner classes and every actual tick's
checks stay unchanged. Complete physics/external geometry are still mandatory.
"""
from .knife_chain_eval import ChainRunner,store
from .knife_chain_eval_fast import BoundSlamRunner
from copy import deepcopy


def _hook_key(run,plan):
    if plan is None:return None
    from .knife_chain_cs_cache import _value
    try:
        context=tuple(run.v.get(k) for k in ("iid","fa","ta","face","cs_toward"))
        if any(v is None for v in context):return None
        return (_value(context),_value(plan))
    except (TypeError,AttributeError):
        # This is only an optimization key. Unknown representations keep the
        # original C5 search/check, including any error from that original call.
        return None


def _selected_hook(runner):
    """Current real guard's complete all-control witness, held by a model only."""
    from .claw_strike import CsPlan
    run=runner.run
    if run is None:return None
    plan=run.v.get("cs");cfg=getattr(getattr(runner.anchor,"csx",None),"cfg",None)
    if not isinstance(plan,CsPlan) or cfg is None:return None
    try:
        n=len(cfg.gaps)*len(cfg.ctrl)
        if not n or len(plan.var_ok)!=n or len(plan.strike)!=n:return None
        if any(type(v) is not int or v<=0 for v in plan.var_ok):return None
        if plan.n_ok!=sum(plan.var_ok) or any(p is None for p in plan.strike):return None
    except (TypeError,AttributeError):return None
    key=_hook_key(run,plan)
    return None if key is None else (key,deepcopy(plan))


def _plan_key(x,plan):
    if plan is None:return None
    return ((x.v.get("iid"),x.v.get("fa"),x.v.get("ta"),x.v.get("face")),
            tuple(getattr(plan,k) for k in ("f0","dirk","d_end","f_down","f_umb","f_press","k_press","b_iid","c_down","c_strike","inv_until")))


def _stored(x,name):
    if name.startswith("var.tmp."):return x.tmp.get(name[8:])
    if name.startswith("var."):return x.v.get(name[4:])
    return None


class _SelectedStrike:
    _nominal_projection_only=True
    def _act(self,x,act):
        name=act.get("a")
        if name=="claw_plan" and self._selected_hook is not None:
            plan=x.v.get("cs");p_only=self.ev(x,act.get("p_only"))
            if plan is not None and p_only==plan.f_press and _hook_key(x.run,plan)==self._selected_hook[0]:
                # Define this same fixed candidate program. The actual runner
                # still replans/checks every tick; full nominal hook physics,
                # target instance, external path and N=2 checks remain fresh.
                store(x,act["store"],deepcopy(self._selected_hook[1]));x.tmp["plan_ms"]=0.
                self._selected_strike_info["model_hook_rechecks_omitted"]+=1
                return None
        if name=="strike_check":
            plan=self.ev(x,act["plan"]);key=_plan_key(x,plan)
            if key is not None and key==self._selected_strike_key:
                self._selected_strike_info["model_rechecks_omitted"]+=1
                store(x,act["store"],True)
                return None
            result=super()._act(x,act)
            if _stored(x,act["store"]):
                self._selected_strike_key=key
                self._selected_strike_info["validation_frame"]=x.obs.f
                self._selected_strike_info["validation_source"]="original C5 strike_check"
            return result
        result=super()._act(x,act)
        if name=="strike_search":
            self._selected_strike_info["control_searches"]+=1
            plan=_stored(x,act["store"])
            if plan is not None:
                self._selected_strike_key=_plan_key(x,plan)
                self._selected_strike_info["validation_frame"]=x.obs.f
                self._selected_strike_info["validation_source"]="original C5 strike_search/evaluate grid"
        return result


class _SelectedBound(_SelectedStrike,BoundSlamRunner):pass
class _SelectedPlain(_SelectedStrike,ChainRunner):pass


def selected_claw_projection(private_runner):
    """Caller must own this model copy. Never mutate shared primitive registries."""
    if isinstance(private_runner,_SelectedStrike):return private_runner
    if type(private_runner) is BoundSlamRunner:private_runner.__class__=_SelectedBound
    elif type(private_runner) is ChainRunner:private_runner.__class__=_SelectedPlain
    else:raise TypeError("unknown model runner type")
    private_runner._selected_strike_key=None
    private_runner._selected_hook=_selected_hook(private_runner)
    private_runner._selected_strike_info={"scope":"nominal selected hook/strike candidate only; live checks unchanged",
        "control_searches":0,"model_rechecks_omitted":0,"model_hook_rechecks_omitted":0,
        "hook_program_source":"current all-control C5 witness" if private_runner._selected_hook is not None else None,
        "validation_frame":None,"validation_source":None}
    return private_runner
