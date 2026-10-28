import gc
import time
import pytest
from ssbot.train.stall_diagnostics import StallDiagnostics, tail_summary
from ssbot.train.aa_v2 import PeriodGuard, validate_production_cli


def test_real_gc_and_numba_events_restore_callbacks_and_keep_thread_identity():
    from numba import njit
    before = list(gc.callbacks)
    diag = StallDiagnostics().install()
    try:
        diag.start_episode(0)
        diag.begin_tick(20)
        diag.phase("prediction")
        gc.collect()
        @njit
        def fresh(x): return x+1
        assert fresh(3) == 4
        diag.end_tick()
        data = diag.finish_episode()
        assert data["complete"]
        kinds = {(r["kind"],r["status"]) for r in data["events"]}
        assert {("gc","start"),("gc","stop"),("numba_compile","start"),("numba_compile","stop")} <= kinds
        assert all(r["tid"] and r["wall_ns"] >= r["thread_cpu_ns"] for r in data["events"])
    finally: diag.close()
    assert gc.callbacks == before


def test_exclusive_phase_cpu_vs_wall_and_bounded_event_loss():
    walls=iter([10,20,100]);cpus=iter([5,10,20])
    diag=StallDiagnostics(wall_clock=lambda:next(walls),cpu_clock=lambda:next(cpus))
    diag.begin_tick(1);diag.phase("logging");parts=diag.end_tick()
    assert [(p["name"],p["wall_ns"],p["cpu_ns"]) for p in parts] == [("tick_setup",10,5),("logging",80,10)]
    tiny=StallDiagnostics(capacity=2)
    for _ in range(3):tiny._event("test","start")
    assert len(tiny.events)==2 and not tiny.finish_episode()["complete"]


def test_one_audited_failure_continues_but_repeated_or_missing_measurement_stops():
    guard=PeriodGuard()
    assert not guard.observe(0,outcome="WATCHDOG",complete=True)
    assert not guard.observe(1,outcome="CLEAR",complete=True)
    assert guard.observe(0,outcome="WATCHDOG",complete=True)
    assert PeriodGuard().observe(0,outcome="WATCHDOG",complete=True,recovered=False)
    assert PeriodGuard().observe(0,outcome="CLEAR",complete=False)
    guard=PeriodGuard()
    for i in range(3):
        assert not guard.observe(i,outcome="WATCHDOG",complete=True)
    assert guard.observe(3,outcome="WATCHDOG",complete=True)


def test_injected_data_cannot_be_used_in_production_and_tail_keeps_extreme_tick():
    for cli in ({"measurement_protocol":1}, {"measurement_protocol":2,"measure_diagnostics":True,"engineering_probe":True},
                {"measurement_protocol":2,"measure_diagnostics":True,"measure_stall_ms":350}):
        with pytest.raises(ValueError):validate_production_cli(cli)
    validate_production_cli({"measurement_protocol":2,"measure_diagnostics":True})
    rows=[{"kind":"tick","f":f,"total_tick_ms":v} for f,v in ((10,1),(11,300),(12,2))]
    data=tail_summary(rows,wake_f=10,end_f=12)
    assert data["total"]["over_250ms"]==1 and data["longest_ticks"][0]["f"]==11
