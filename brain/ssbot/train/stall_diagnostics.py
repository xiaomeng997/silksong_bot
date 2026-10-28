"""Bounded opt-in stall evidence. No disk I/O, key selection or policy clock reads.

perf_counter_ns is separate from the controller's perf_counter budget. Events are
correlations, not causal attribution. deque.append/copy are atomic under CPython's
GIL; no callback acquires a lock that an interrupted allocation could already hold.
"""
from __future__ import annotations
from collections import deque
import gc
import threading
import time


class StallDiagnostics:
    def __init__(self, capacity=16384, *, wall_clock=None, cpu_clock=None,
                 stall_ms=0.0, stall_tick=200, stall_episode=0):
        if capacity < 1 or stall_ms < 0 or stall_tick < 1 or stall_episode < 0:
            raise ValueError("invalid diagnostic limits/injection")
        self.events = deque(maxlen=capacity)
        self.wall = wall_clock or time.perf_counter_ns
        self.cpu = cpu_clock or time.thread_time_ns
        self.local = threading.local()
        self.episode = None
        self.tick_no = 0
        self.stall_ms, self.stall_tick, self.stall_episode = stall_ms, stall_tick, stall_episode
        self.injected = False
        self.errors = deque(maxlen=32)
        self._installed = False
        self._listener = None
        self._cursor = -1
        from itertools import count
        self._sequence = count()

    def _event(self, kind, status, **data):
        self.events.append({"seq": next(self._sequence), "kind": kind, "status": status,
                            "wall_ns": self.wall(), "thread_cpu_ns": self.cpu(),
                            "tid": threading.get_ident(), "ep": self.episode,
                            "f": getattr(self.local, "frame", None), **data})

    def _gc(self, phase, info):
        try:
            self._event("gc", phase, generation=info.get("generation"),
                        collected=info.get("collected"), uncollectable=info.get("uncollectable"))
        except Exception as exc:
            self.errors.append(type(exc).__name__)

    def install(self):
        if self._installed:
            raise RuntimeError("diagnostics already installed")
        from numba.core import event
        owner = self
        class Compilation(event.Listener):
            def on_start(self, ev): self.record(ev, "start")
            def on_end(self, ev): self.record(ev, "stop")
            def record(self, ev, status):
                try:
                    data = ev.data or {}
                    dispatcher = data.get("dispatcher")
                    function = getattr(dispatcher, "py_func", None)
                    owner._event("numba_compile", status, token=id(data),
                                 function=(getattr(function, "__module__", "") + "." +
                                           getattr(function, "__qualname__", "unknown")),
                                 signature=str(data.get("args")))
                except Exception as exc:
                    owner.errors.append(type(exc).__name__)
        self._listener = Compilation()
        event.register("numba:compile", self._listener)
        gc.callbacks.append(self._gc)
        self._installed = True
        return self

    def close(self):
        if self._installed:
            from numba.core import event
            event.unregister("numba:compile", self._listener)
            gc.callbacks.remove(self._gc)
            self._installed = False

    def start_episode(self, episode):
        self.episode, self.tick_no = episode, 0

    def begin_tick(self, frame):
        self.tick_no += 1
        self.local.frame = frame
        self.local.parts = []
        self.local.point = ("tick_setup", self.wall(), self.cpu())

    def phase(self, name):
        point = getattr(self.local, "point", None)
        if point is None:
            return
        wall, cpu = self.wall(), self.cpu()
        old, start, start_cpu = point
        self.local.parts.append({"name": old, "start_ns": start, "end_ns": wall,
                                 "wall_ns": wall - start, "cpu_ns": cpu - start_cpu})
        self.local.point = (name, wall, cpu)

    def end_tick(self):
        self.phase("end")
        result = self.local.parts
        self.local.point = None
        self.local.frame = None
        return result

    def inject_if_due(self):
        if (self.stall_ms and not self.injected and self.episode == self.stall_episode
                and self.tick_no >= self.stall_tick):
            self.injected = True
            self.phase("injected_stall")
            self._event("injected_stall", "start", requested_ms=self.stall_ms)
            time.sleep(self.stall_ms / 1000.0)
            self._event("injected_stall", "stop", requested_ms=self.stall_ms)
            self.phase("policy")

    def finish_episode(self):
        self.episode = None
        # Include bounded lifetime history in each episode report. This avoids
        # clearing a callback's in-flight start while another thread writes it.
        rows = sorted(self.events.copy(), key=lambda r:r["seq"])
        lost = any(r["seq"] >= self.events.maxlen for r in rows)
        return {"schema": 1, "complete": not lost and not self.errors,
                "events_overwritten": lost, "callback_errors": list(self.errors), "events": rows,
                "injection_requested_ms": self.stall_ms, "injection_executed": self.injected,
                "clock": "perf_counter_ns / per-thread thread_time_ns",
                "interpretation": "phase times are exclusive; GC/compiler overlap is evidence, not proof of cause"}


def tail_summary(rows, *, wake_f=None, end_f=None):
    """One instance only; preserves the longest tick instead of hiding it in p99."""
    import numpy as np
    ticks = [r for r in rows if r.get("kind") == "tick"
             and (wake_f is None or r["f"] >= wake_f) and (end_f is None or r["f"] <= end_f)]
    values = [r["total_tick_ms"] for r in ticks]
    def stats(x):
        return {"n": len(x), "p50_ms": float(np.percentile(x, 50)) if x else None,
                "p99_ms": float(np.percentile(x, 99)) if x else None, "max_ms": max(x) if x else None,
                "over_100ms": sum(v > 100 for v in x), "over_250ms": sum(v > 250 for v in x)}
    phases = {}
    for row in ticks:
        for part in row.get("diagnostic_phases", []):
            phases.setdefault(part["name"], []).append(part)
    return {"total": stats(values),
            "phases": {name: {"wall": stats([p["wall_ns"]/1e6 for p in ps]),
                              "thread_cpu": stats([p["cpu_ns"]/1e6 for p in ps])}
                       for name, ps in phases.items()},
            "longest_ticks": [{"f": r["f"], "owner": r.get("owner"), "total_tick_ms": r["total_tick_ms"],
                               "phases": r.get("diagnostic_phases", [])}
                              for r in sorted(ticks, key=lambda r:r["total_tick_ms"], reverse=True)[:10]]}
