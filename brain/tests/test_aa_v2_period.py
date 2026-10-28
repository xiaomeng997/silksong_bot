from datetime import datetime
import pytest
from ssbot.tools import forum_aa_v2 as collector
from ssbot.tools.forum_aa_v2_analysis import analyze


def test_period_retains_known_failure_and_runs_next_round(monkeypatch,tmp_path):
    calls=[]
    def round(run,**kw):
        slot=kw['slot'];calls.append(slot['round']);rows=[]
        for i in (0,1):
            fail=i==0 and slot['round']==0
            rows.append({**{k:v for k,v in slot.items() if k!='labels'},'instance':i,'label':slot['labels'][i],
                         'seed':kw['seed'],'protocol_version':2,'complete':True,'production_eligible':True,
                         'outcome':'WATCHDOG' if fail else 'CLEAR','recovered':True,'behavior_sha256':'same',
                         'audit':{'success':not fail,'K_star':120 if fail else 20,'metrics':{'L':0,'T':5 if fail else 20}},
                         'main_ticks':{'p50':5,'p99':10,'gap_ge3':0}})
        return rows
    monkeypatch.setattr(collector,'run_round',round)
    p={'schema':2,'status':'FROZEN','periods':[{'planned_start':datetime.now().astimezone().isoformat(),'blocks':[0]}],
       'max_start_delay_seconds':60,'files_sha256':{},'behavior_sha256':'same','blocks':[{'seed':1}],
       'continuation_limits':{'consecutive_watchdogs':2,'total_watchdogs':4}}
    report=collector.run_period(p,0,root=tmp_path,environment={},output_root=tmp_path)
    assert report['complete'] and calls==[0,1] and len(report['rows'])==4
    assert report['rows'][0]['outcome']=='WATCHDOG'
    assert analyze(report['rows'])['watchdog_failures']==1
    report['rows'][0]['protocol_sha256']='other'
    with pytest.raises(ValueError):analyze(report['rows'])


def test_unscheduled_v2_and_engineering_data_are_rejected(tmp_path):
    with pytest.raises(ValueError):collector.run_period({'schema':2,'status':'FROZEN','periods':[{'planned_start':None}]},0,root=tmp_path,environment={},output_root=tmp_path)
    with pytest.raises(ValueError):analyze([{'protocol_version':1}])
    with pytest.raises(ValueError):analyze([{'protocol_version':2,'production_eligible':False}])
