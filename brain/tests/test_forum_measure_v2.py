from types import SimpleNamespace
import pytest
from ssbot.train.forum_measure_window import MeasurementWindow
from ssbot.train.forum_measure_metrics import audit_states
from ssbot.tools.forum_measure_audit import audit_window


def state(f, *, paused=False, lost=False, hp=7, events=(), dead=False):
    return {"f":f,"dt":.1,"hero":{"health":hp,"health_blue":0},"ev":list(events),
            "game":{"paused":paused},"act":{"lost":lost},"room":{},
            "ents":[{"iid":i,"type_key":"Song Heavy Sentry","hp":0 if dead else 230,"is_dead":dead}
                    for i in (1,2)]}


def window():return MeasurementWindow(SimpleNamespace(wake_frame=10),wave=13,expected_targets=2,game_limit=120,protocol_version=2)


def test_watchdog_ends_at_first_observed_pause_includes_damage_during_stall_and_is_failure():
    w=window()
    ev={"f":11,"k":"hp","q":1,"d":{"delta":-1,"blue_delta":0}}
    rows=[state(9),state(10),state(11,hp=6,events=[ev]),state(12,paused=True,lost=True,hp=6),state(13,paused=True,lost=True,hp=6)]
    for s in rows[1:]:w.observe(s,s['f']*100_000_000)
    w.finish_at(13,"episode_harness_fail")
    m=w.snapshot();a=audit_window(rows,m,{"unit":"Forum_W_w13","f_wake":10,"outcome":"HARNESS_FAIL"})
    assert m["complete"] and m["end_f"]==12 and m["T"]==pytest.approx(.3)
    assert a["complete"] and not a["success"] and a["K_star"]==120 and a["metrics"]["L"]==1


@pytest.mark.parametrize("fault",["gap","hp","unknown_pause"])
def test_real_missing_state_or_hp_mismatch_never_becomes_complete(fault):
    w=window();rows=[state(9),state(10),state(12 if fault=="gap" else 11,paused=True,lost=fault!="unknown_pause",hp=6 if fault=="hp" else 7)]
    for s in rows[1:]:w.observe(s,s['f']*100_000_000)
    w.finish_at(rows[-1]['f'],"episode_harness_fail")
    a=audit_window(rows,w.snapshot(),{"unit":"Forum_W_w13","f_wake":10,"outcome":"HARNESS_FAIL"})
    assert not a["complete"]


def test_watchdog_in_postkill_tail_retains_primary_and_marks_operational_failure():
    w=window();rows=[state(9),state(10),state(11,dead=True),state(12,dead=True,paused=True,lost=True)]
    for s in rows[1:]:w.observe(s,s['f']*100_000_000)
    a=audit_window(rows,w.snapshot(),{"unit":"Forum_W_w13","f_wake":10,"outcome":"HARNESS_FAIL"})
    assert w.snapshot()["end_f"]==11 and w.snapshot()["tail_end_reason"]=="watchdog"
    assert a["complete"] and not a["success"] and a["K_star"]==120


def test_known_zero_dt_tail_is_observed_not_missing_and_has_no_invented_rate():
    w=window();rows=[state(9),state(10),state(11,dead=True),state(12,dead=True,paused=True,lost=True)]
    rows[-1]['dt']=0
    for s in rows[1:]:w.observe(s,s['f']*100_000_000)
    a=audit_window(rows,w.snapshot(),{'unit':'Forum_W_w13','f_wake':10,'outcome':'HARNESS_FAIL'})
    assert a['complete'] and not a['success']
    assert a['tail']['metrics']['T']==0 and a['tail']['metrics']['HP_per_min'] is None


def test_disconnect_missing_summary_end_produces_incomplete_prefix_report(monkeypatch,tmp_path):
    import json,msgpack
    from ssbot.tools import forum_measure_audit as tool
    rows=[state(f) for f in range(9,13)]
    class Reader:
        def __init__(self,path):pass
        def records(self,kind):
            for row in rows:yield None,row['f']*100_000_000,None,0,None,msgpack.packb(row,use_bin_type=True)
    monkeypatch.setattr(tool,'RecordingReader',Reader)
    attempt={'episode':0,'f_wake':10,'f_end':None,'unit':'Forum_W_w13','outcome':'HARNESS_FAIL',
             'recording':'unused','measurement':{'protocol_version':2,'window':{'last_f':11}}}
    (tmp_path/'attempts_i0.jsonl').write_text(json.dumps(attempt)+'\n')
    target=tmp_path/'audit.json'
    assert tool.main(['--run',str(tmp_path),'--instance','0','--out',str(target)])==1
    result=json.loads(target.read_text())
    assert not result['complete'] and result['summary_end_missing']
    assert result['window']['end_f']==11 and result['metrics']['T']==pytest.approx(.2)
    assert 'episode fault: unobserved HP/time interval cannot be assumed empty' in result['window']['errors']
