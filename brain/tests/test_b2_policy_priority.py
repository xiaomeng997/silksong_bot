"""Policy arbitration tests use the actual act AST, without modeling new physics."""
import ast
import copy
import inspect
from collections import Counter
from types import SimpleNamespace as NS

import pytest
from ssbot.train import forum_planner_policy as mod
from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy


def chain(arm="B", stage="approach", mask=2):
    return NS(b2=True, arm=arm, candidate_generation=arm=="B",
              _b2_selected=None if stage=="recovery" else NS(stage=stage, mask=mask),
              final=lambda *a: None)


class Script:
    def __init__(self, mask=8, critical=False):
        self.mask=mask; self.is_critical=critical; self.observed=[]; self.stepped=[]; self.yielded=[]; self.aborted=[]
        self.pmc=False; self.b2=False; self.pm_giveup=None; self.run=None
    def observe(self, f, s): self.observed.append(f)
    def critical(self): return self.is_critical
    def step(self, *a, **kw): self.stepped.append(a[0]); return self.mask
    def yield_to(self, s): self.yielded.append(s["f"])
    def abort(self, reason): self.aborted.append(reason)


def selected(stage="approach", mask=2, arm="B"):
    p=Policy.__new__(Policy); p.chain_native=chain(arm, stage, mask)
    p.planner=NS(last_info={"b2":{"stage":stage}})
    res=NS(name="CHAIN B2 "+stage, mask=mask)
    return p,res


@pytest.mark.parametrize("stage", ["approach","commitment","active","continuation","recovery"])
@pytest.mark.parametrize("mask", [0,2])
def test_selected_chain_all_stages_require_fresh_matching_result(stage, mask):
    p,res=selected(stage,mask)
    assert p._b2_selected_for_policy(res,fresh=True)==(stage!="recovery" or mask==0)
    assert not p._b2_selected_for_policy(res,fresh=False)
    if stage!="recovery":
        p.chain_native._b2_selected.mask ^= 1
        assert not p._b2_selected_for_policy(res,fresh=True)
        p.chain_native._b2_selected.mask=res.mask
        p.chain_native._b2_selected.stage="other"
        assert not p._b2_selected_for_policy(res,fresh=True)


@pytest.mark.parametrize("arm",["A",None])
def test_baseline_has_no_b2_policy_priority(arm):
    p,res=selected(arm=arm)
    assert p._b2_priority_chain() is None
    assert not p._b2_selected_for_policy(res,fresh=True)


@pytest.mark.parametrize("kwargs,reason",[
    ({},None),({"low_crit":True},"low_crit"),({"asw_crit":True},"asw_crit"),
    ({"m2_on":True},"m2"),({"supervisor":True},"supervisor"),
    ({"low_crit":True,"asw_crit":True,"m2_on":True,"supervisor":True},"supervisor")])
def test_policy_gate_precedence(kwargs,reason):
    flags=dict(low_crit=False,asw_crit=False,m2_on=False,supervisor=False);flags.update(kwargs)
    assert Policy._b2_policy_gate(**flags)==reason


def test_current_tick_low_critical_is_observed_before_gate(monkeypatch):
    p,_=selected();p.rune_lowhop=Script(critical=True);p.two=None
    assert p._b2_script_critical(17,{"f":17})==(True,None,False,False)
    assert p.rune_lowhop.observed==[17]


def arbitration_code():
    # Execute the production arbitration statements, not a test reimplementation.
    tree=ast.parse(inspect.getsource(mod));cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=="ForumPlannerPolicy")
    body=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=="act").body
    start=next(i for i,x in enumerate(body) if isinstance(x,ast.Assign) and ast.unparse(x.targets[0])=="mask" and "r.mask" in ast.unparse(x.value))
    end=next(i for i,x in enumerate(body) if i>start and isinstance(x,ast.Assign) and ast.unparse(x.targets[0])=="key")
    return compile(ast.fix_missing_locations(ast.Module(body=copy.deepcopy(body[start:end]),type_ignores=[])),mod.__file__,"exec")


def run_arbitration(p,res,*,mask_sup=None,low_crit=False,asw_crit=False,m2=None):
    p.sc=NS(pq=None);p.pause_owned=False;p.m2=m2;p.wpress=None;p.air_show=None
    p._play_tick=None;p.v2feed=None;p.counts=Counter();p._cogfly=lambda *a:None;p.cog={"frames":set()}
    p.slam_play=Script(mask=16);p.claw=Script(mask=32);p.cast_stab=Script(mask=64)
    p.rune_lowhop=Script(mask=8,critical=low_crit);p.evade_chase=Script(mask=128)
    p.two=None;p._wake_f=None;p.enc=NS(name="w7")
    s={"f":2599,"hero":{}}
    scope=dict(self=p,res=res,r=NS(mask=mask_sup),s=s,raw=s,f=2599,fo=2599,
        ws=NS(stamp=NS(t_game_s=1.),hero=NS(contact=NS(v="GROUND"))),S0=None,
        prefix=[],hold=None,prefs=NS(target=7),esc_on=False,wt=None,fcast=None,
        m2_mask=None if m2 is None else 256,b2_priority=p._b2_priority_chain(),
        b2_critical=(low_crit,None,asw_crit,False) if p._b2_priority_chain() is not None else None,
        air_tick=False)
    exec(arbitration_code(),mod.__dict__,scope)
    return scope


@pytest.mark.parametrize("stage",["approach","commitment","active","continuation","recovery"])
@pytest.mark.parametrize("mask",[0,2])
def test_production_arbitration_restores_slam_slot_and_lower_scripts_yield(stage,mask):
    if stage=="recovery":mask=0
    p,res=selected(stage,mask);out=run_arbitration(p,res)
    assert (out["own"],out["mask"],out["play"])==("chain",mask,mask)
    assert not p.slam_play.stepped and not p.claw.stepped and not p.cast_stab.stepped
    assert p.rune_lowhop.yielded==[2599] and not p.rune_lowhop.stepped
    assert p.evade_chase.yielded==[2599] and not p.evade_chase.stepped
    assert not p.rune_lowhop.observed, "B critical snapshot must not observe LOWHOP twice"


@pytest.mark.parametrize("flags,expected",[
    ({"low_crit":True},"low_crit"),({"asw_crit":True},"asw_crit"),
    ({"mask_sup":512},"supervisor"),({"m2":NS(took=False)},"m2")])
def test_production_arbitration_does_not_give_b2_critical_or_supervisor_keys(flags,expected):
    p,res=selected();out=run_arbitration(p,res,**flags)
    assert out["own"]!="chain"
    assert p.chain_native.policy_gate_reason==expected


def test_baseline_production_script_order_stays_slam_first():
    p,res=selected(arm="A");out=run_arbitration(p,res)
    assert (out["own"],out["mask"])==("slam",16)
    assert p.slam_play.stepped==[2599]
    assert not p.claw.stepped and not p.cast_stab.stepped
    assert p.rune_lowhop.observed==[2599] and p.rune_lowhop.yielded==[2599]
    assert not hasattr(p.chain_native,"policy_gate_reason")


def test_public_chain_owner_preserves_native_selected_planner_identity():
    p,res=selected();called=[];p.chain_native.final=lambda *a:called.append(a);p.measurement=None
    p._measure_choice("chain",2,res)
    assert called==[("plan",2)]
    p._measure_choice("low",8,res)
    assert called[-1]==("low",8)
    p.chain_native.arm="A";p._measure_choice("chain",2,res)
    assert called[-1]==("chain",2)
