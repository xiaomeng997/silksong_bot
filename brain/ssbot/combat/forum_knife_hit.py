"""Full hit paths and a shared post-bounce exit for experimental knife rows.

Used by the opt-in native producer; this grants no cross-tick continuation.
Never checks a missed strike or replaces the planned strike with an H abort.
"""
from dataclasses import dataclass, field
import numpy as np
from ssbot.knowledge import kinematics as km
from ssbot.map2 import oldwin_claw as claw


def hit_events(base, first, last, length=None):
    """Cover every integer first-contact time in every modeled hook outcome."""
    n=len(base.hooks);first=np.asarray(first,np.int64);last=np.asarray(last,np.int64)
    length=len(base.commands) if length is None else int(length)
    if (first.shape!=(n,) or last.shape!=(n,) or np.any(first>last)
            or np.any(first<=base.control_frames) or np.any(last>length)):
        raise ValueError("unsupported first-contact interval")
    for k in range(int(first.min()),int(last.max())+1):
        contact=np.clip(k,first,last)
        events=np.zeros((n,length),np.int64)
        events[np.arange(n),contact-1]=km.EV_POGO
        yield contact,events


def full_contacts(planner, forecast, rollout, *, start=0, escape=False):
    """Same hull sampler/width rejection, including the first queried frame."""
    from ssbot.combat.planner import _hull_points
    inverse=None
    ix=getattr(rollout,"query_index",None)
    if (ix is not None and getattr(rollout,"_query_bound",None) is rollout.bound
            and getattr(rollout,"_query_flags",None) is rollout.flags_all
            and not rollout.bound.flags.writeable and not rollout.flags_all.flags.writeable):
        bound=rollout.bound[ix,start:];flags=rollout.flags_all[ix,start:]
        inverse=rollout.query_inverse
    else:bound=rollout.bound[:,start:];flags=rollout.flags_all[:,start:]
    tk=np.arange(start,start+bound.shape[1])*planner.params.frame_time
    hx,hy=forecast.fc.half
    x,y,rows,wide=_hull_points(np.ascontiguousarray(bound),hx,hy,planner.cfg.max_points)
    hit=(forecast.rs.occupied_esc(x,y,tk) if escape else forecast.occupied(x,y,tk,False))
    if hit is None:raise ValueError("occupancy unavailable")
    n=len(bound);occ=hit[:n].copy()
    if len(rows):occ[rows]|=hit[n:].reshape(-1,len(rows),hit.shape[1]).any(axis=0)
    occ|=wide
    occ &= (flags&km.F_INVULN)==0
    return occ if inverse is None else occ[inverse]


@dataclass(frozen=True)
class HitWorld:
    """One target world, bound to its own contact interval and forecast."""
    key: object
    forecast: object
    base: object
    swing: np.ndarray
    first: np.ndarray
    last: np.ndarray
    robust: np.ndarray
    reroll: object = None


@dataclass
class HitExit:
    start: int
    through: int
    option: int
    raw: np.ndarray
    latched: np.ndarray
    paths: list
    contacts: list
    world_keys: list
    horizon: int
    expected_world_keys: tuple
    _proof: object = field(default=None, init=False, repr=False, compare=False)



_EXIT_ISSUER = object()


def _array_payload(values):
    """Keep one immutable byte snapshot per distinct array in this payload."""
    cache = {}
    result = []
    for value in values:
        key = id(value)
        if key not in cache:
            a = np.asarray(value)
            cache[key] = (a.dtype.str, a.shape, a.tobytes())
        result.append(cache[key])
    return tuple(result)


def _exit_payload(cert):
    return (cert.start, cert.through, cert.option, cert.horizon,
            tuple(cert.world_keys), tuple(cert.expected_world_keys),
            _array_payload((cert.raw, cert.latched, *cert.contacts)),
            tuple((id(p), id(p.bound), p.bound.shape) for p in cert.paths))


def _issued_exit(*args):
    """Called only by the successful common_escape branch."""
    import weakref
    cert = HitExit(*args)
    cert._proof = (_EXIT_ISSUER, weakref.ref(cert), _exit_payload(cert))
    return cert


def _require_issued_exit(cert):
    try:
        proof = cert._proof
        good = (type(cert) is HitExit and proof is not None
                and proof[0] is _EXIT_ISSUER and proof[1]() is cert
                and proof[2] == _exit_payload(cert))
    except (AttributeError, TypeError, ValueError, IndexError):
        good = False
    if not good:
        raise ValueError("hit/exit certificate was not issued or has changed")


FREE_MIN = 10


def contacts_fit(world, horizon, length):
    """The same fixed contact contract, with the caller's actual P + T."""
    from ssbot.combat.dslash import POST_F
    if (isinstance(horizon, (bool, np.bool_)) or not isinstance(horizon, (int, np.integer))
            or not 0 <= horizon < length):
        raise ValueError("actual integer contact horizon required")
    n = len(world.base.hooks)
    controls = np.asarray(world.base.control_frames)
    arrays = [np.asarray(x) for x in (world.swing, world.first, world.last)]
    robust = np.asarray(world.robust)
    if (controls.shape != (n,) or controls.dtype.kind not in "iu" or any(x.shape != (n,) or x.dtype.kind not in "iu" for x in arrays)
            or robust.shape != (n,) or robust.dtype.kind != "b"):
        raise ValueError("contact identity/arrays unavailable")
    swing, first, last = arrays
    return bool(n and robust.all() and np.all(first > controls) and np.all(first > horizon)
                and np.all(first >= swing) and np.all(first <= last) and np.all(last < length - POST_F)
                and np.all(swing >= controls) and np.all(swing - controls >= FREE_MIN))



def _world_key(key):
    """Canonical immutable identity for this coupled Slam's declared world."""
    if not isinstance(key, tuple) or len(key) != 3:
        raise ValueError("target world identity unavailable")
    iid, durations, shift = key
    def integer(x):
        return not isinstance(x, (bool, np.bool_)) and isinstance(x, (int, np.integer))
    if (not integer(iid) or not isinstance(durations, tuple) or len(durations) != 5
            or any(not integer(x) or x <= 0 for x in durations) or not integer(shift)):
        raise ValueError("target world identity unavailable")
    return int(iid), tuple(map(int, durations)), int(shift)


def _expected_domain(expected_worlds):
    try:
        reference = tuple(_world_key(k) for k in expected_worlds)
    except TypeError as exc:
        raise ValueError("explicit expected target world domain required") from exc
    if not reference:
        raise ValueError("nonempty expected target world domain required")
    if len(set(reference)) != len(reference):
        raise ValueError("duplicate target world in expected domain")
    return tuple(sorted(reference))


def common_escape(planner, worlds, raw, hold, *, horizon, expected_worlds, audit=None):
    """One global input edge and one escape option for every supplied world.

    Re-roll from the original control states/events and check frame zero.
    No missed-strike path, H abort, per-world option, or new protection at J.
    Motion reuse is private to this call and requires the same base/callback,
    contacts and common wire. Every new rollout passes identity checks.
    """
    from ssbot.combat.holdfilter import hold_filter_jit
    worlds = tuple(worlds)
    raw = np.asarray(raw)
    if not worlds or raw.ndim != 1 or raw.dtype.kind not in "iu":
        raise ValueError("nonempty target worlds and one integer raw command required")
    raw = raw.astype(np.int64, copy=False)
    length = len(raw)
    log = {} if audit is None else audit
    log.update(status="unchecked", horizon=horizon, length=length,
               worlds=[], options=[], contact_gate=False)
    import hashlib
    import json
    reference = _expected_domain(expected_worlds)
    actual = tuple(_world_key(w.key) for w in worlds)
    if len(set(actual)) != len(actual):
        raise ValueError("duplicate target world identity")
    missing = set(reference) - set(actual)
    extra = set(actual) - set(reference)
    log.update(expected_world_count=len(reference),
               expected_world_sha256=hashlib.sha256(json.dumps(reference, separators=(",", ":")).encode()).hexdigest(),
               missing_worlds=sorted(missing), extra_worlds=sorted(extra))
    if missing or extra:
        log.update(reason="target_world_domain_mismatch")
        raise ValueError("target world domain mismatch")
    wire = hold_filter_jit(raw[None], hold)[0][0]
    failed_contacts = []
    for q, w in enumerate(worlds):
        if not np.array_equal(w.base.commands, wire):
            raise ValueError("latched prefix mismatch")
        origin = getattr(getattr(w.forecast, "rs", None), "knife_coupled_world", None)
        if not isinstance(origin, dict) or any(k not in origin for k in ("iid", "durations", "shift")):
            raise ValueError("paired forecast target world marker required")
        try:
            paired = _world_key((origin["iid"], tuple(origin["durations"]), origin["shift"]))
        except (ValueError, TypeError) as exc:
            raise ValueError("paired forecast target world marker invalid") from exc
        if _world_key(w.key) != paired:
            raise ValueError("forecast target world identity mismatch")
        good = contacts_fit(w, horizon, length)
        if not good:
            failed_contacts.append(q)
        log["worlds"].append(dict(key=w.key, contact_gate=good))
    if failed_contacts:
        log.update(status="failed", reason="contact_gate", failed_worlds=failed_contacts)
        return None
    log["contact_gate"] = True

    event_cache = {}
    def events(w):
        key = (id(w.base), np.asarray(w.first).tobytes(), np.asarray(w.last).tobytes())
        if key not in event_cache:
            event_cache[key] = list(hit_events(w.base, w.first, w.last))
        return event_cache[key]

    original = {}
    def integrate(w, contact, commands, cache):
        key = (id(w.base), id(w.reroll), contact.tobytes(), commands.tobytes())
        if key in cache:
            return cache[key]
        ev = np.zeros((len(w.base.hooks), len(commands)), np.int64)
        ev[np.arange(len(w.base.hooks)), contact - 1] = km.EV_POGO
        ro = (claw.with_events(w.base, planner.params, planner.terrain, ev,
                              threads=planner.cfg.threads, commands=commands)
              if w.reroll is None else w.reroll(ev, commands))
        if (len(ro.hooks) != len(w.base.hooks) or not np.array_equal(ro.commands, commands)
                or any(a is not b for a, b in zip(ro.hooks, w.base.hooks))):
            raise ValueError("hit continuation changed hook identity or commands")
        for name in ("control_frames", "hook_indices", "clock_indices"):
            old = getattr(w.base, name, None)
            if old is not None and not np.array_equal(getattr(ro, name, None), old):
                raise ValueError("hit continuation changed outcome identity")
        states = getattr(w.base, "control_states", None)
        if states is not None:
            actual = getattr(ro, "control_states", None)
            if (actual is None or states.keys() != actual.keys()
                    or any(not np.array_equal(states[k], actual[k]) for k in states)):
                raise ValueError("hit continuation changed control state identity")
        recorded = getattr(ro, "pogo_events", None)
        if recorded is not None and not np.array_equal(recorded, ev):
            raise ValueError("hit continuation changed pogo events")
        if (ro.bound.shape[:2] != (len(w.base.hooks), len(commands) + 1)
                or ro.flags_any.shape != ro.bound.shape[:2]):
            raise ValueError("hit continuation horizon unavailable")
        cache[key] = ro
        return ro

    blocked = np.zeros(length + 1, bool)
    seen = set()
    for w in worlds:
        for contact, _ in events(w):
            ro = integrate(w, contact, wire, original)
            if id(ro) not in seen:
                blocked |= np.any((ro.flags_any & (km.F_NO_INPUT | km.F_RELINQ)) != 0, axis=0)
                seen.add(id(ro))
    j = max(int(np.max(w.last)) for w in worlds) + 1
    while j < length and blocked[j]:
        j += 1
    if j >= length:
        raise ValueError("no supported post-bounce input edge")
    through = j + max(24, length - j)
    log.update(start=j, through=through)
    for w in worlds:
        rs = w.forecast.rs
        if not rs.samples or max(rs.samples) + rs.k_shift < through:
            raise ValueError("post-hit escape support horizon unavailable")
    prefix_bad = set()
    fixed_bad = set()
    for q, w in enumerate(worlds):
        bad = set()
        full = set()
        for contact, _ in events(w):
            ro = integrate(w, contact, wire, original)
            occ = full_contacts(planner, w.forecast, ro)
            full.update(map(int, np.flatnonzero(occ.any(axis=0))))
            bad.update(map(int, np.flatnonzero(occ[:, :j + 1].any(axis=0))))
        log["worlds"][q].update(prefix_unsafe=sorted(bad), fixed_unsafe=sorted(full))
        prefix_bad.update(bad)
        fixed_bad.update(full)
    log.update(prefix_unsafe=sorted(prefix_bad), fixed_unsafe=sorted(fixed_bad))
    if prefix_bad:
        log.update(status="failed", reason="prefix_unsafe")
        return None
    for option, suffix in enumerate(planner._esc_cmds(through - j)):
        full = np.concatenate((raw[:j], suffix))
        latched = hold_filter_jit(full[None], hold)[0][0]
        if len(latched) != through or not np.array_equal(latched[:j], wire[:j]):
            raise ValueError("exit changed strike prefix or horizon")
        # A new option gets a new motion cache; unchanged original keys may
        # reuse original motion. Forecast queries are always fresh.
        cache = original if np.array_equal(latched, wire) else {}
        paths, contacts, world_keys, failed, unsafe = [], [], [], [], set()
        for q, w in enumerate(worlds):
            for contact, _ in events(w):
                ro = integrate(w, contact, latched, cache)
                occ = full_contacts(planner, w.forecast, ro)
                esc = full_contacts(planner, w.forecast, ro, start=j, escape=True)
                bad = np.union1d(np.flatnonzero(occ.any(axis=0)),
                                 j + np.flatnonzero(esc.any(axis=0)))
                if len(bad):
                    failed.append(q)
                    unsafe.update(map(int, bad))
                    break
                paths.append(ro)
                contacts.append(contact)
                world_keys.append(w.key)
        log["options"].append(dict(option=option, failed_worlds=failed,
                                   unsafe_frames=sorted(unsafe)))
        if not failed:
            log.update(status="passed", option=option)
            return _issued_exit(j, through, option, full, latched, paths, contacts, world_keys, int(horizon), reference)
    log.update(status="failed", reason="no_common_exit")
    return None
