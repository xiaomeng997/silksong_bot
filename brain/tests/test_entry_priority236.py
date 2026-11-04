"""The first-side-hit preference cannot buy DPS with a worse exit or quota."""
import inspect
import numpy as np
import pytest
from ssbot.combat.forum_planner import ForumPlanner
from tests.test_entry_side_followthrough import run
from tests.test_forum_planner import params,arena


def captured_tick(monkeypatch,params,arena,x=27.5):
    real_sort=np.lexsort;captured=[]
    real_init=ForumPlanner.__init__
    def init(self,*a,**kw):
        real_init(self,*a,**kw);self.fcfg.K_b=3
    monkeypatch.setattr(ForumPlanner,'__init__',init)
    def sort(keys,*a,**kw):
        fr=inspect.currentframe().f_back
        local=fr.f_locals
        rank=local.get('entry_rank')
        if fr.f_code.co_name=='_ordinary_tick' and rank and len(keys)>20:
            captured.append((tuple(keys),dict(local)))
        return real_sort(keys,*a,**kw)
    monkeypatch.setattr(np,'lexsort',sort)
    pl,res=run(params,arena,x=x)
    assert not res.forced_risk and len(captured)==1
    return pl,res,*captured[0],real_sort


@pytest.mark.parametrize('better',['field','SG8','N2','hard_hazard'])
def test_actual_final_order_keeps_exit_and_position_above_first_hit(monkeypatch,params,arena,better):
    pl,res,keys,loc,sort=captured_tick(monkeypatch,params,arena)
    # Probe the ACTUAL final ranking tuple, with all unrelated tiers tied.
    # Row0 hits earlier. Row1 has a better future position / two exits / safety.
    probe=[np.zeros(2,dtype=np.int64) for _ in keys]
    early=next(i for i,k in enumerate(keys) if k is loc['entry_rank'][0])
    probe[early][:]=[2,7]
    desired={'field':loc['v2_nh'],'SG8':loc['offl'],'N2':loc['exit_rank'],'hard_hazard':loc['hz']}[better]
    idx=max(i for i,k in enumerate(keys) if k is desired)
    probe[idx][:]=[1000 if better=='field' else 1,0]
    assert int(sort(tuple(probe))[0])==1
    probe[idx][:]=0
    assert int(sort(tuple(probe))[0])==0  # earliest hit still breaks a quality tie


@pytest.mark.parametrize('x',[27.5,15.])
def test_actual_envelope_retains_original_safety_quota_and_v_siblings(monkeypatch,params,arena,x):
    pl,res,keys,loc,sort=captured_tick(monkeypatch,params,arena,x=x)
    # Reconstruct documented safe-tier members from untouched preselection,
    # independently of the mutable rest/top traversal order.
    original=[int(i) for i in loc['pre'] if not loc['core'][i]
              and not (loc['cont'] and i==loc['N']-1) and not loc['win_rows_'][i]]
    top=original[:pl.fcfg.K_b]
    assert set(loc['top'])==set(top)
    first=loc['first'];expected=[]
    for i in original[:8]:
        if first[i]>=0:
            expected += [j for j in original if first[j]==first[i] and j!=i and j not in set(top)][:pl.fcfg.sibs]
    assert loc['sib']==expected
