"""Low-frequency field building in an owned process; two complete immutable slots.

The policy only offers the latest small scene and pins a published FieldSet.
No build, IPC send/receive, result decoding or worker wait runs in a policy tick.
A broker handles IPC; the process keeps Python/Numba build work off its GIL.
Slot reuse replaces objects, never the arrays a previous tick still holds.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
import multiprocessing as mp
import os
from pathlib import Path
import sys
import threading
import time
import traceback


_SPAWN_LOCK = threading.Lock()


@dataclass(frozen=True)
class Publication:
    epoch: int
    sequence: int
    key: tuple
    origin: float
    field: object
    build_ms: float
    slot: int


class DoubleBuffer:
    def __init__(self):
        self.slots = [None, None]
        self.current = None

    def publish(self, epoch, sequence, key, origin, field, build_ms):
        slot = 0 if self.current is None else 1 - self.current.slot
        complete = Publication(epoch, sequence, key, origin, field, build_ms, slot)
        self.slots[slot] = complete
        self.current = complete  # one reference swap, after the entire slot exists
        return complete

    def clear(self):
        self.current = None
        self.slots = [None, None]


def _pack(field):
    # MappingProxyType is intentionally not pickled. Only query data crosses;
    # raw diagnostic/template tensors stay in the builder process.
    return dict(grids=[(k, (g.times, g.xs, g.ys, g.values, g.known, g.regions))
                       for k, g in field.grids.items()], meta=field.meta,
                y0=field.y0, tol=field.tol, cache_key=field.cache_key,
                selection=field.selection)


def _unpack(wire):
    from .scene_field_grid import SceneFieldGrid
    from .scene_field_events import FieldSet
    import numpy as np
    grids = {}
    for key, arrays in wire['grids']:
        if len(arrays) != 6 or not all(isinstance(a, np.ndarray) for a in arrays):
            raise ValueError('invalid async grid arrays')
        times, xs, ys, values, known, regions = arrays
        if any(a.ndim != 1 or not len(a) for a in (times, xs, ys)):
            raise ValueError('invalid async grid axes')
        shape = (len(times), len(ys), len(xs))
        if (values.shape != shape or known.shape != shape or regions.shape != shape[1:]
                or values.dtype.kind != 'f' or any(a.dtype.kind != 'f' for a in (times,xs,ys))
                or known.dtype.kind != 'b' or regions.dtype.kind not in 'iu'):
            raise ValueError('invalid async grid shapes')
        # This private pipe carries only our validated builder's output. Its
        # grids already passed SceneFieldGrid's full axis/value checks there.
        # Pickle produced new process-private arrays: freeze them, without
        # copying/scanning the grid again while holding the policy's GIL.
        grid = object.__new__(SceneFieldGrid)
        for name, array in zip(('times','xs','ys','values','known','regions'), arrays):
            array.setflags(write=False)
            object.__setattr__(grid, name, array)
        grids[tuple(key)] = grid
    if not grids:
        raise ValueError('empty async field')
    field = FieldSet(grids, wire['meta'], {}, wire['y0'], wire['tol'],
                     wire['cache_key'], wire['selection'])
    from .scene_field_events import LAYERS
    from .scene_field_locked import field_complete
    sel = field.selection
    expected = {(w, h, layer, c) for w in sel.worlds for h in sel.hyps
                for layer in LAYERS for c in sel.components}
    if len(wire['grids']) != len(grids) or set(grids) != expected or not field_complete(field):
        raise ValueError('incomplete async field selection')
    return field


def _worker(conn, input_path, arena, selection):
    try:
        import psutil
        p = psutil.Process()
        cpus = list(range(24, min(32, psutil.cpu_count() or 0)))
        if not cpus:
            raise RuntimeError('no configured E cores for field builder')
        p.cpu_affinity(cpus)
        p.nice(psutil.IDLE_PRIORITY_CLASS)
        from numba import set_num_threads
        set_num_threads(1)
        from . import scene_field_events as E, scene_field_locked as L
        from .scene_field_grid import SceneFieldGrid
        from .scene_field_inputs import load_inputs
        inputs = load_inputs(input_path, E.Inputs)
        E.warmup()
        prepared = E.prepare(inputs, arena=arena)
        conn.send(('ready', dict(pid=p.pid, created=p.create_time(), cpus=p.cpu_affinity(),
                                priority=int(p.nice()), exe=p.exe(), prefix=sys.prefix)))
        while True:
            request = conn.recv()
            epoch, sequence, key, origin, scene = request
            started = time.perf_counter()
            field = E.build(scene, inputs, SceneFieldGrid, E.Config(), t_origin_s=origin,
                            prepared=prepared, select=selection)
            if not L.field_complete(field):
                raise ValueError('async builder returned incomplete event knots')
            if not all(g.times[0] <= origin <= g.times[-1] for g in field.grids.values()):
                raise ValueError('async field does not cover its origin')
            conn.send(('field', request[:4], _pack(field),
                       (time.perf_counter() - started) * 1000.))
    except (EOFError, BrokenPipeError):
        pass  # parent closed its end, including an abnormal parent exit
    except BaseException:
        try: conn.send(('error', traceback.format_exc()))
        except (EOFError, BrokenPipeError, OSError): pass
    finally:
        conn.close()


class AsyncFieldBuilder:
    """One in-flight build + one replaceable latest request, never a FIFO backlog.

    Old complete data may bridge a refresh for at most two refresh intervals,
    and only for the same room/move/lock/selection and covered absolute times.
    Construction and close may wait, so callers use them only at reset/cleanup.
    """
    def __init__(self, inputs, input_path, arena, selection=None, refresh_s=.25):
        if not math.isfinite(refresh_s) or refresh_s <= 0:
            raise ValueError('refresh_s must be finite and positive')
        self.inputs, self.selection = inputs, selection
        self.refresh_s = float(refresh_s)
        self.max_age_s = 2 * self.refresh_s
        self.buffer = DoubleBuffer()
        self._epoch = self._sequence = 0
        self._key = self._last_now = self._requested_at = None
        self._request = None
        self._failure = None
        self._closed = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._ready = threading.Event()
        self.worker_info = None
        context = mp.get_context('spawn')
        self._conn, child = context.Pipe()
        self._process = context.Process(target=_worker, args=(child, str(input_path), arena, selection),
                                        name='scene-field-builder', daemon=True)
        try:
            # Windows auxiliary workers use pythonw, without changing the
            # executable of any later multiprocessing launch in this process.
            with _SPAWN_LOCK:
                from multiprocessing import spawn
                previous = spawn.get_executable()
                old_launcher = os.environ.get('__PYVENV_LAUNCHER__')
                try:
                    if os.name == 'nt':
                        # Match CPython's venv bypass, but use the no-console
                        # base binary. Launching the venv redirector would
                        # give Process.pid the wrapper PID instead of the worker.
                        hidden = Path(sys._base_executable).with_name('pythonw.exe')
                        if not hidden.is_file(): raise RuntimeError('pythonw missing for field worker')
                        os.environ['__PYVENV_LAUNCHER__'] = str(Path(sys.executable).with_name('pythonw.exe'))
                        mp.set_executable(str(hidden))
                    self._process.start()
                finally:
                    mp.set_executable(previous)
                    if old_launcher is None:
                        os.environ.pop('__PYVENV_LAUNCHER__', None)
                    else:
                        os.environ['__PYVENV_LAUNCHER__'] = old_launcher
        except BaseException:
            child.close()
            self._conn.close()
            raise
        child.close()
        self._thread = threading.Thread(target=self._broker, name='scene-field-publisher', daemon=True)
        self._thread.start()
        if not self._ready.wait(120.):
            self.close()
            raise RuntimeError('field builder startup timed out')
        try:
            self._check()
        except BaseException:
            self.close()
            raise

    def _check(self):
        if self._failure is not None:
            raise RuntimeError('async field builder failed: ' + self._failure)
        if self._stop.is_set():
            raise RuntimeError('async field builder is closed')

    def _receive(self):
        while not self._stop.is_set():
            if self._conn.poll(.05):
                message = self._conn.recv()
                if message[0] == 'error':
                    raise RuntimeError(message[1])
                return message
            if not self._process.is_alive():
                raise RuntimeError('field builder exited without a result')
        return None

    def _broker(self):
        try:
            ready = self._receive()
            if ready is None: return
            if ready[0] != 'ready': raise RuntimeError('invalid builder startup message')
            self.worker_info = ready[1]
            if self.worker_info['pid'] != self._process.pid:
                raise RuntimeError('builder PID differs from the owned process')
            self._ready.set()
            last_sequence = 0
            while not self._stop.is_set():
                request = self._request  # latest immutable request reference
                if request is None or request[1] == last_sequence:
                    if not self._process.is_alive():
                        raise RuntimeError('idle field builder exited')
                    self._wake.wait(.5)
                    self._wake.clear()
                    continue
                self._conn.send(request)
                message = self._receive()
                if message is None: break
                if message[0] != 'field' or message[1] != request[:4]:
                    raise RuntimeError('field result does not match its request')
                field = _unpack(message[2])  # complete/read-only, off the policy thread
                if field.meta['t_origin_s'] != request[3] or not all(
                        g.times[0] <= request[3] <= g.times[-1] for g in field.grids.values()):
                    raise ValueError('async result has the wrong time origin')
                if request[0] == self._epoch and request[2] == self._key:
                    self.buffer.publish(*request[:4], field, message[3])
                last_sequence = request[1]
        except BaseException:
            if not self._stop.is_set(): self._failure = traceback.format_exc()
        finally:
            self._ready.set()
            self._conn.close()

    def invalidate(self):
        self._epoch += 1
        self._key = self._requested_at = self._last_now = None
        self._request = None
        self.buffer.clear()

    def get(self, view):
        """Non-waiting policy-side offer + read of one completed snapshot."""
        self._check()
        from . import scene_field_events as E, scene_field_locked as L
        if view.get('status') != 'ok':
            if self._key is not None: self.invalidate()
            return None, view.get('reason')
        now = float(view['t_origin_s'])
        if not math.isfinite(now): raise ValueError('game time must be finite')
        if not L.lock_coverage(view['scene'], self.inputs)['complete']:
            self.invalidate()
            return None, 'lock_event_over'
        key = L.field_key(E.cache_key, view['scene'], view['lock'], E.Config(), self.inputs,
                          select=self.selection)
        if key is None:
            self.invalidate()
            return None, 'out_of_build_scope'
        if key != self._key or (self._last_now is not None and now < self._last_now):
            self.invalidate()
            self._key = key
        self._last_now = now
        if self._requested_at is None or now >= self._requested_at + self.refresh_s:
            self._sequence += 1
            # Native adapter already copies entity scalars; this small request
            # copy additionally prevents any later caller mutation reaching IPC.
            scene = deepcopy(view['scene'])
            self._request = (self._epoch, self._sequence, key, now, scene)
            self._requested_at = now
            self._wake.set()
        pinned = self.buffer.current
        if pinned is None or pinned.epoch != self._epoch or pinned.key != key:
            return None, 'async_pending'
        if not 0 <= now - pinned.origin <= self.max_age_s:
            return None, 'async_snapshot_stale'
        if not all(g.times[0] <= now <= g.times[-1] for g in pinned.field.grids.values()):
            return None, 'async_snapshot_expired'
        return pinned.field, 'ok'

    def status(self):
        p = self.buffer.current
        return dict(mode='async_double_buffer', worker=self.worker_info,
                    request_sequence=self._sequence, published_sequence=None if p is None else p.sequence,
                    slot=None if p is None else p.slot, build_ms=None if p is None else p.build_ms,
                    max_age_s=self.max_age_s)

    def close(self):
        if self._closed: return
        self._stop.set()
        self._wake.set()
        self._thread.join(2.)
        self._process.join(2.)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(2.)
            self._thread.join(.5)
        if self._process.is_alive() or self._thread.is_alive():
            raise RuntimeError('field builder cleanup did not complete')
        self._conn.close()
        self._closed = True
