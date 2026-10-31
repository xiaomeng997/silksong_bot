"""Private nominal projection of ONE selected control strike.

This defines a candidate program, not a cache of safety or runtime guard results.
The original C5 strike_search/check validates the plan once at conditional control;
model futures then hold its commands. Real runner classes and every actual tick's
checks stay unchanged. Complete physics/external geometry are still mandatory.
"""
from .knife_chain_eval import ChainRunner,store
from .knife_chain_eval_fast import BoundSlamRunner


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
    private_runner._selected_strike_info={"scope":"nominal selected-strike candidate only; live checks unchanged",
        "control_searches":0,"model_rechecks_omitted":0,"validation_frame":None,"validation_source":None}
    return private_runner
