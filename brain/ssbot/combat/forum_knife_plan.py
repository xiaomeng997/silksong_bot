"""Carry a newly checked hit/exit tail through ordinary row selection.

This is tick-local transport, not a controller or a continuation certificate.
The producer still owns contact/forecast certification. A new tick must rebuild
and recheck its candidate; retaining keys grants no right to execute them.
"""
from dataclasses import dataclass
import numpy as np
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.knowledge import kinematics as km


def _integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(name + " must be an integer")
    return int(value)


def _copy(value):
    out = np.array(value, copy=True)
    out.setflags(write=False)
    return out


def _state(value):
    out = np.asarray(value)
    if out.shape not in ((km.K,), (km.K, 1)) or not np.isfinite(out).all():
        raise ValueError("one finite origin state required")
    return out.reshape(km.K)


def _hold(value):
    arrays = tuple(np.asarray(getattr(value, name)) for name in ("latched", "desired", "pending", "age"))
    if any(a.shape != (1, km.N_BUTTONS) for a in arrays):
        raise ValueError("one complete origin HoldState required")
    return arrays


@dataclass(frozen=True)
class CheckedTail:
    """Immutable copy of one exit, tied to this origin and actual P/T/H."""
    frame: int
    prefix: np.ndarray
    horizon: int
    T: int
    start: np.ndarray
    hold: tuple
    raw: np.ndarray
    latched: np.ndarray
    jump: int
    through: int
    worlds: tuple

    @classmethod
    def from_exit(cls, cert, *, frame, start, hold, prefix, T, world_keys):
        from ssbot.combat.forum_knife_hit import HitExit
        if not isinstance(cert, HitExit):
            raise ValueError("complete hit/exit certificate required")
        frame = _integer(frame, "origin frame")
        T = _integer(T, "T")
        if frame < 0:
            raise ValueError("nonnegative origin frame required")
        prefix = np.asarray(prefix)
        if prefix.ndim != 1 or prefix.dtype.kind not in "iu" or T <= 0:
            raise ValueError("integer queued prefix and positive T required")
        H = len(prefix) + T
        if _integer(cert.horizon, "certificate H") != H:
            raise ValueError("certificate uses a different actual H")
        raw, wire = np.asarray(cert.raw), np.asarray(cert.latched)
        if (raw.ndim != 1 or raw.dtype.kind not in "iu" or wire.shape != raw.shape
                or wire.dtype.kind not in "iu" or cert.through != len(raw)
                or not H < cert.start < cert.through or cert.through < H + 24
                or cert.through - cert.start < 24 or not np.array_equal(raw[:len(prefix)], prefix)):
            raise ValueError("complete checked strike and exit tail required")
        actual = hold_filter_jit(raw[None], hold)[0][0]
        if not np.array_equal(actual, wire):
            raise ValueError("checked full wire changed")
        worlds = tuple(world_keys)
        if not worlds or len(set(worlds)) != len(worlds) or None in worlds:
            raise ValueError("explicit unique target worlds required")
        declared = tuple(cert.expected_world_keys)
        if not declared or len(set(declared)) != len(declared) or set(declared) != set(worlds):
            raise ValueError("certificate expected world domain changed")
        if (not cert.paths or len(cert.paths) != len(cert.contacts)
                or len(cert.paths) != len(cert.world_keys) or set(cert.world_keys) != set(worlds)):
            raise ValueError("certificate world coverage changed")
        for ro, contact in zip(cert.paths, cert.contacts):
            contact = np.asarray(contact)
            if (not len(contact) or contact.shape != (len(ro.hooks),) or contact.dtype.kind not in "iu"
                    or np.any(contact <= H) or np.any(contact >= cert.start)
                    or not np.array_equal(ro.commands, wire)
                    or ro.bound.shape[:2] != (len(contact), cert.through + 1)):
                raise ValueError("checked path/contact identity changed")
        return cls(frame, _copy(prefix), H, T, _copy(_state(start)),
                   tuple(_copy(a) for a in _hold(hold)), _copy(raw), _copy(wire),
                   int(cert.start), int(cert.through), worlds)

    def for_row(self, *, frame, start, hold, prefix, T, cmd, latched):
        """Reject stale origins, altered in-flight keys, HoldState or row keys."""
        P = len(self.prefix)
        if (_integer(frame, "origin frame") != self.frame or _integer(T, "T") != self.T
                or not np.array_equal(np.asarray(prefix), self.prefix)
                or not np.array_equal(_state(start), self.start)
                or any(not np.array_equal(a, b) for a, b in zip(_hold(hold), self.hold))):
            raise ValueError("checked tail origin changed; recheck required")
        if (not np.array_equal(np.asarray(cmd), self.raw[P:self.horizon])
                or not np.array_equal(np.asarray(latched), self.latched[:self.horizon])):
            raise ValueError("selected row changed checked keys")
        return self.raw[P:].copy()


def pick_tail(planner, f, roll, hold_end, ranked, horizon, default, checked):
    """Respect rank and tail_k; a checked J-tail needs no no-strike H abort."""
    if not checked:
        return planner._tail_pick(f, roll, hold_end, ranked, horizon, default)
    K = min(int(planner.cfg.tail_k), len(ranked))
    if not K:
        return default, None
    for row in ranked[:K]:
        row = int(row)
        if row in checked:
            return row, True
        chosen, good = planner._tail_pick(f, roll, hold_end, np.array([row], np.int64), horizon, row)
        if good:
            return chosen, True
    return default, False


def selected_tail(result, checked, *, T):
    """Keep every checked key after P, including the strike AFTER H."""
    if result.idx not in checked or result.S or getattr(result, "forced_risk", False):
        return None
    full = checked[result.idx]
    cmd = np.asarray(result.cmd)
    if (len(cmd) != _integer(T, "T") or len(cmd) > len(full) or not np.array_equal(cmd, full[:len(cmd)])
            or result.mask != int(cmd[0])):
        raise ValueError("selection changed checked command")
    return full.copy()
