"""The resident L2 plan worker (Task 182): one owned process, one request in flight + the latest pending, complete plans.

Same process / pipe / double-buffer machinery as combat.scene_field_async (its hidden spawn, its DoubleBuffer), with
its own validity: the field builder takes only post-lock scenes and refreshes on a period, a plan request is made for
an event before the lock and is valid by its move instance, generation and support, not by an age.

The policy thread only swaps a request reference and reads the current publication: no pickling, pipe call or wait in
a tick (the broker thread does those). A result never touches the executor or a key: the foreground reads it on its
own tick and checks instance, generation, validity and support (l2_plan.PlanExecutor.offer).

InlineChannel is the offline determinism: the same request / latest contract in this process, the plan appearing a
fixed number of ticks after its request (SSBOT_FORUM_TWO_PLAN_INLINE=N, replays and tests only; the manifest shows it).
"""
from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
import sys
import threading
import time
import traceback

from ssbot.combat.scene_field_async import _SPAWN_LOCK, DoubleBuffer

PLAN_CPUS = tuple(range(24, 32))    # the same E cores and Idle priority as the field builder


def _worker(conn, params, cpus):
    try:
        import psutil
        p = psutil.Process()
        use = [c for c in cpus if c < (psutil.cpu_count() or 0)]
        if not use:
            raise RuntimeError("no configured E cores for the plan worker")
        p.cpu_affinity(use)
        p.nice(psutil.IDLE_PRIORITY_CLASS)
        from numba import set_num_threads
        set_num_threads(1)
        from . import clapper_plans as P
        P.warm(params)
        conn.send(("ready", dict(pid=p.pid, created=p.create_time(), cpus=p.cpu_affinity(),
                                 priority=int(p.nice()), exe=p.exe(), prefix=sys.prefix)))
        terrain = None
        while True:
            request = conn.recv()
            if request[0] == "model":
                params, terrain = request[1], request[2]
                continue
            epoch, sequence, key, snapshot = request
            started = time.perf_counter_ns()
            plan = P.generate(snapshot, params, terrain)
            conn.send(("plan", (epoch, sequence, key), plan, (time.perf_counter_ns() - started) / 1e6))
    except (EOFError, BrokenPipeError):
        pass  # the parent closed its end, including an abnormal parent exit
    except BaseException:
        try:
            conn.send(("error", traceback.format_exc()))
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        conn.close()


class PlanChannel:
    """One in flight + the latest pending, never a FIFO backlog. Construction and close may wait (startup / cleanup)."""
    mode = "process"

    def __init__(self, params, cpus=None, start_timeout_s=120.):
        cpus = PLAN_CPUS if cpus is None else cpus
        self.buffer = DoubleBuffer()
        self._epoch = self._sequence = 0
        self._request = None
        self._model = self._model_sent = None
        self._failure = None
        self._closed = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._ready = threading.Event()
        self.worker_info = None
        self.sent = self.published = 0
        context = mp.get_context("spawn")
        self._conn, child = context.Pipe()
        self._process = context.Process(target=_worker, args=(child, params, tuple(cpus)),
                                        name="l2-plan-worker", daemon=True)
        try:
            # As scene_field_async: the hidden base binary, without changing later launches of this process.
            with _SPAWN_LOCK:
                from multiprocessing import spawn
                previous = spawn.get_executable()
                old_launcher = os.environ.get("__PYVENV_LAUNCHER__")
                try:
                    if os.name == "nt":
                        hidden = Path(sys._base_executable).with_name("pythonw.exe")
                        if not hidden.is_file():
                            raise RuntimeError("pythonw missing for the plan worker")
                        os.environ["__PYVENV_LAUNCHER__"] = str(Path(sys.executable).with_name("pythonw.exe"))
                        mp.set_executable(str(hidden))
                    self._process.start()
                finally:
                    mp.set_executable(previous)
                    if old_launcher is None:
                        os.environ.pop("__PYVENV_LAUNCHER__", None)
                    else:
                        os.environ["__PYVENV_LAUNCHER__"] = old_launcher
        except BaseException:
            child.close()
            self._conn.close()
            raise
        child.close()
        self._thread = threading.Thread(target=self._broker, name="l2-plan-publisher", daemon=True)
        self._thread.start()
        if not self._ready.wait(start_timeout_s):
            self.close()
            raise RuntimeError("plan worker startup timed out")
        self.check_health()

    @property
    def failure(self):
        return self._failure

    def check_health(self) -> None:
        """Reset / start boundary only; no waiting or rebuilding."""
        if self._failure is None and not self._process.is_alive() and not self._closed:
            self._failure = "owned plan worker exited"
        if self._failure is not None:
            raise RuntimeError("plan worker failed: " + self._failure)

    def _receive(self):
        while not self._stop.is_set():
            if self._conn.poll(.05):
                message = self._conn.recv()
                if message[0] == "error":
                    raise RuntimeError(message[1])
                return message
            if not self._process.is_alive():
                raise RuntimeError("plan worker exited without a result")
        return None

    def _broker(self):
        try:
            ready = self._receive()
            if ready is None:
                return
            if ready[0] != "ready" or ready[1]["pid"] != self._process.pid:
                raise RuntimeError("invalid plan worker startup message")
            self.worker_info = ready[1]
            self._ready.set()
            last = 0
            while not self._stop.is_set():
                if self._model is not self._model_sent:
                    self._model_sent = self._model
                    self._conn.send(("model", *self._model_sent))
                request = self._request        # the latest immutable request reference
                if request is None or request[1] == last:
                    if not self._process.is_alive():
                        raise RuntimeError("idle plan worker exited")
                    self._wake.wait(.5)
                    self._wake.clear()
                    continue
                self._conn.send(request)
                self.sent += 1
                message = self._receive()
                if message is None:
                    break
                if message[0] != "plan" or message[1] != request[:3]:
                    raise RuntimeError("plan result does not match its request")
                if request[0] == self._epoch:
                    self.buffer.publish(request[0], request[1], request[2], time.perf_counter_ns(), message[2],
                                        message[3])
                    self.published += 1
                last = request[1]
        except BaseException:
            if not self._stop.is_set():
                self._failure = traceback.format_exc()
        finally:
            self._ready.set()
            self._conn.close()

    def set_model(self, params, terrain) -> None:
        self._model = (params, terrain)
        self._wake.set()

    def request(self, key, snapshot) -> int:
        """Non-blocking: replaces the latest pending request (a newer one merges it); returns its sequence."""
        self._sequence += 1
        self._request = (self._epoch, self._sequence, key, snapshot)
        self._wake.set()
        return self._sequence

    def latest(self):
        """The current complete publication of this epoch, or None. Never waits."""
        pub = self.buffer.current
        return pub if pub is not None and pub.epoch == self._epoch else None

    def tick(self) -> None:
        pass

    def invalidate(self) -> None:
        self._epoch += 1
        self._request = None
        self.buffer.clear()

    def status(self) -> dict:
        pub = self.buffer.current
        return dict(mode=self.mode, worker=self.worker_info, requested=self._sequence, sent=self.sent,
                    published=self.published, published_sequence=None if pub is None else pub.sequence,
                    failure=self._failure)

    def close(self) -> None:
        if self._closed:
            return
        self._stop.set()
        self._wake.set()
        self._thread.join(2.)
        self._process.join(2.)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(2.)
            self._thread.join(.5)
        if self._process.is_alive() or self._thread.is_alive():
            raise RuntimeError("plan worker cleanup did not complete")
        self._conn.close()
        self._closed = True


class InlineChannel:
    """The same contract in this process, for replays and tests: a request is built `delay` ticks later (one in flight +
    the latest pending, as the process). failure / check_health / close / invalidate behave the same."""
    mode = "inline"

    def __init__(self, params, delay=1):
        self.params, self.delay = params, int(delay)
        self.terrain = None
        self.buffer = DoubleBuffer()
        self._epoch = self._sequence = 0
        self._flight = self._latest = None     # (due tick, request tuple) / request tuple
        self._tick = 0
        self.failure = None
        self.worker_info = None
        self.sent = self.published = 0

    def check_health(self) -> None:
        if self.failure is not None:
            raise RuntimeError("plan worker failed: " + self.failure)

    def set_model(self, params, terrain) -> None:
        self.params, self.terrain = params, terrain

    def request(self, key, snapshot) -> int:
        self._sequence += 1
        self._latest = (self._epoch, self._sequence, key, snapshot)
        return self._sequence

    def latest(self):
        pub = self.buffer.current
        return pub if pub is not None and pub.epoch == self._epoch else None

    def tick(self) -> None:
        from . import clapper_plans as P
        self._tick += 1
        if self._flight is None and self._latest is not None:
            self._flight, self._latest = (self._tick + self.delay - 1, self._latest), None   # delay 1: the next tick's read
            self.sent += 1
        if self._flight is not None and self._tick >= self._flight[0]:
            request = self._flight[1]
            self._flight = None
            started = time.perf_counter_ns()
            plan = P.generate(request[3], self.params, self.terrain)
            if request[0] == self._epoch:
                self.buffer.publish(request[0], request[1], request[2], time.perf_counter_ns(), plan,
                                    (time.perf_counter_ns() - started) / 1e6)
                self.published += 1

    def invalidate(self) -> None:
        self._epoch += 1
        self._flight = self._latest = None
        self.buffer.clear()

    def status(self) -> dict:
        pub = self.buffer.current
        return dict(mode=self.mode, delay=self.delay, requested=self._sequence, sent=self.sent,
                    published=self.published, published_sequence=None if pub is None else pub.sequence, failure=None)

    def close(self) -> None:
        pass
