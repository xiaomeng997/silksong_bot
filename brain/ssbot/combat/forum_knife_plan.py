"""Carry a newly checked hit/exit tail through ordinary row selection.

This is tick-local transport, not a controller or a continuation certificate.
The producer still owns contact/forecast certification. A new tick must rebuild
and recheck its candidate; retaining keys grants no right to execute them.
"""
from dataclasses import dataclass, field
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



_TAIL_ISSUER = object()


def _tail_payload(tail):
    from ssbot.combat.forum_knife_hit import _array_payload
    return (tail.frame, tail.horizon, tail.T, tail.jump, tail.through, tail.worlds,
            tuple(id(x) for x in tail.runtime_source) if tail.runtime_source is not None else None,
            _array_payload((tail.prefix, tail.start, tail.raw, tail.latched, *tail.hold)))


def _issue_tail(tail):
    import weakref
    object.__setattr__(tail, "_proof", (_TAIL_ISSUER, weakref.ref(tail), _tail_payload(tail)))
    return tail


def _require_issued_tail(tail):
    try:
        proof = tail._proof
        good = (type(tail) is CheckedTail and proof is not None
                and proof[0] is _TAIL_ISSUER and proof[1]() is tail
                and proof[2] == _tail_payload(tail))
    except (AttributeError, TypeError, ValueError, IndexError):
        good = False
    if not good:
        raise ValueError("checked tail was not issued or has changed")


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
    runtime_source: tuple | None = None
    _proof: object = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def from_exit(cls, cert, *, frame, start, hold, prefix, T, world_keys, runtime_source=None):
        from ssbot.combat.forum_knife_hit import _require_issued_exit
        _require_issued_exit(cert)
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
        if runtime_source is not None and (not isinstance(runtime_source, tuple) or len(runtime_source) != 2
                or any(x is None for x in runtime_source)):
            raise ValueError("complete runtime forecast and knowledge source required")
        return _issue_tail(cls(frame, _copy(prefix), H, T, _copy(_state(start)),
                   tuple(_copy(a) for a in _hold(hold)), _copy(raw), _copy(wire),
                   int(cert.start), int(cert.through), worlds, runtime_source))

    def for_row(self, *, frame, start, hold, prefix, T, cmd, latched):
        """Reject stale origins, altered in-flight keys, HoldState or row keys."""
        _require_issued_tail(self)
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


    def for_runtime_row(self, *, win, forecast, **origin):
        """Recompute the domain from this tick, independently of the candidate."""
        _require_issued_tail(self)
        knowledge = getattr(win, "knife_knowledge", None)
        if (self.runtime_source is None or self.runtime_source[0] is not forecast
                or self.runtime_source[1] is not knowledge):
            raise ValueError("checked tail runtime source changed or unavailable")
        from ssbot.combat.forum_knife_coupled import expected_slam_worlds
        from ssbot.combat.forum_knife_hit import _expected_domain
        iids = {key[0] for key in self.worlds}
        observations = [o for o in win.obs() if o.hp > 0]
        if len(observations) != 1 or {o.iid for o in observations} != iids:
            raise ValueError("checked tail target observation changed")
        reference = _expected_domain(expected_slam_worlds(observations[0], knowledge))
        if reference != _expected_domain(self.worlds):
            raise ValueError("checked tail differs from current expected world domain")
        return self.for_row(**origin)


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
