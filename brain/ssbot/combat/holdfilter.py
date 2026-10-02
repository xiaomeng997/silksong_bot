"""Compiled HoldFilter for the planner's candidates (oracle/src/Input/HoldFilter.cs; the NumPy reference is
ssbot.knowledge.kinematics.hold_filter, which tests/test_planner.py holds this to bit for bit).

The planner sends commanded masks; the oracle (and the final SendInput sink) latch them through the HoldFilter: a
release waits until the key has been down min_press latched frames, a press until it has been up min_release frames,
left and right are never latched together, and more than max_pending queued toggles of one key drop the oldest press +
release pair. The rollout needs the latched masks. The reference loops over frames in NumPy (about 5 ms for 500 x 50
candidates), too slow for the 3 ms tick; this is the same per-lane state machine in numba, over the keys in use only
(an idle key just ages), lanes in parallel.
"""
import numba
import numpy as np

from ssbot.knowledge.kinematics import _AGE_LONG, _LEFT_BIT, _RIGHT_BIT, N_BUTTONS, HoldState


@numba.njit(cache=True)
def _lane(i, masks, latched0, desired0, pending0, age0, min_press, min_release, max_pending, out, st_l, st_d, st_p,
          st_a, keys, keys_mask):
    T = masks.shape[1]
    nb = latched0.shape[1]
    nk = keys.shape[0]
    i = np.int64(i)
    r = np.int64(0) if latched0.shape[0] == 1 else i
    lat = np.zeros(nb, np.bool_)
    des = np.zeros(nb, np.bool_)
    pen = np.zeros(nb, np.int64)
    age = np.zeros(nb, np.int64)
    nxt = np.zeros(nb, np.bool_)
    prs = np.zeros(nb, np.bool_)
    for b in range(nb):
        lat[b] = latched0[r, b]
        des[b] = desired0[r, b]
        pen[b] = pending0[r, b]
        age[b] = age0[r, b]
    for t in range(T):
        m = masks[i, t]
        for kk in range(nk):
            b = keys[kk]
            want = ((m >> b) & 1) == 1
            if want != des[b]:
                pen[b] += 1
            des[b] = want
            if pen[b] > max_pending:
                pen[b] -= 2
            nxt[b] = lat[b]
            has = pen[b] > 0
            rel = has and lat[b] and age[b] >= min_press
            p = has and (not lat[b]) and age[b] >= min_release
            prs[b] = p
            if rel:
                nxt[b] = False
            if p:
                nxt[b] = True
            if rel or p:
                pen[b] -= 1
        both = nxt[_LEFT_BIT] and nxt[_RIGHT_BIT]
        for b in (_LEFT_BIT, _RIGHT_BIT):
            if both and prs[b]:
                nxt[b] = False
                pen[b] += 1
                if not des[b]:
                    pen[b] = 0
        v = 0
        for kk in range(nk):
            b = keys[kk]
            if nxt[b] != lat[b]:
                age[b] = 1
            else:
                age[b] = min(age[b] + 1, _AGE_LONG)
            lat[b] = nxt[b]
            if lat[b]:
                v |= 1 << b
        out[i, t] = v
    for b in range(nb):
        if not keys_mask[b]:
            age[b] = min(age[b] + T, _AGE_LONG)
        st_l[i, b] = lat[b]
        st_d[i, b] = des[b]
        st_p[i, b] = pen[b]
        st_a[i, b] = age[b]


@numba.njit(cache=True, parallel=True)
def _filter_par(masks, latched0, desired0, pending0, age0, min_press, min_release, max_pending, out, st_l, st_d, st_p,
                st_a, keys, keys_mask):
    for i in numba.prange(masks.shape[0]):
        _lane(i, masks, latched0, desired0, pending0, age0, min_press, min_release, max_pending, out, st_l, st_d,
              st_p, st_a, keys, keys_mask)


@numba.njit(cache=True)
def _filter(masks, latched0, desired0, pending0, age0, min_press, min_release, max_pending, out, st_l, st_d, st_p,
            st_a, keys, keys_mask):
    for i in range(masks.shape[0]):
        _lane(i, masks, latched0, desired0, pending0, age0, min_press, min_release, max_pending, out, st_l, st_d,
              st_p, st_a, keys, keys_mask)


def hold_filter_jit(masks: np.ndarray, state: HoldState | None = None, min_press: int = 2, min_release: int = 2,
                    max_pending: int = 3, parallel: bool = True) -> tuple[np.ndarray, HoldState]:
    """Same contract as kinematics.hold_filter: (latched masks [N, T], filter state after the last frame)."""
    masks = np.ascontiguousarray(np.asarray(masks, dtype=np.int64))
    one = masks.ndim == 1
    masks = masks[None] if one else masks
    n, T = masks.shape
    st = state or HoldState.idle(1)
    if len(st.latched) not in (1, n):
        raise ValueError(f"hold state for {len(st.latched)} lanes, masks for {n}")
    out = np.zeros((n, T), np.int64)
    sl = np.zeros((n, N_BUTTONS), np.bool_)
    sd = np.zeros((n, N_BUTTONS), np.bool_)
    sp = np.zeros((n, N_BUTTONS), np.int64)
    sa = np.zeros((n, N_BUTTONS), np.int64)
    # Keys never commanded, latched, wanted or queued stay up and only age: skip them (8 of 22 keys in combat).
    used = int(np.bitwise_or.reduce(masks.ravel())) if masks.size else 0
    active = np.asarray(st.latched) | np.asarray(st.desired) | (np.asarray(st.pending) != 0)
    used |= int((active.any(axis=0).astype(np.int64) << np.arange(N_BUTTONS, dtype=np.int64)).sum())
    used |= (1 << _LEFT_BIT) | (1 << _RIGHT_BIT)
    keys = np.array([b for b in range(N_BUTTONS) if used >> b & 1], np.int64)
    keys_mask = np.zeros(N_BUTTONS, np.bool_)
    keys_mask[keys] = True
    fn = _filter_par if parallel and n >= 64 else _filter
    fn(masks, np.ascontiguousarray(st.latched, np.bool_), np.ascontiguousarray(st.desired, np.bool_),
       np.ascontiguousarray(st.pending, np.int64), np.ascontiguousarray(st.age, np.int64), min_press, min_release,
       max_pending, out, sl, sd, sp, sa, keys, keys_mask)
    return (out[0] if one else out), HoldState(sl, sd, sp, sa)
