"""Parallel form of the support query (ssbot.knowledge.hitbox_tables.SupportQuery.query) for the planner's tick.

The reference kernel runs one thread over every (placement, time step, candidate); with 450 candidates x 49 frames
and 20-60 placements it took p50 0.5 / p99 1.8 ms of a 3 ms tick (planner_bench, live i2_002). This one splits the
candidates into chunks run in parallel (numba prange), each chunk over every placement and time step, with the same
cell lookup (packed bits, anchor frame, mirror, static templates, empty-bin skip); tests/test_planner.py holds it to
SupportQuery.query bit for bit.
"""
import numba
import numpy as np

from ssbot.knowledge.hitbox_tables import SupportQuery

CHUNKS = 16


@numba.njit(cache=True, parallel=True)
def _query_par(bits, boff, imeta, fmeta, full, tk, xt, yt, out, chunks):
    n_t, n_c = xt.shape
    n_p = boff.shape[0]
    for ch in numba.prange(chunks):
        c0 = ch * n_c // chunks
        c1 = (ch + 1) * n_c // chunks
        if c1 <= c0:
            continue
        for p in range(n_p):
            ix0, iy0, nx, ny, nt, rb = imeta[p, 0], imeta[p, 1], imeta[p, 2], imeta[p, 3], imeta[p, 4], imeta[p, 5]
            mirror, anchored, static, fo = imeta[p, 6], imeta[p, 7], imeta[p, 8], imeta[p, 9]
            inv = 1.0 / fmeta[p, 2]
            ax, ay = fmeta[p, 3], fmeta[p, 4]
            if not anchored:
                mirror, ax, ay = 1, 0.0, 0.0
            for k in range(n_t):
                b = 0 if static else int(np.rint((fmeta[p, 5] + tk[k] - fmeta[p, 0]) / fmeta[p, 1]))
                if b < 0 or b >= nt or full[fo + b] == 0:
                    continue
                base = boff[p] + b * ny * rb
                for n in range(c0, c1):
                    if out[k, n]:
                        continue
                    fx = mirror * (xt[k, n] - ax) * inv - ix0
                    fy = (yt[k, n] - ay) * inv - iy0
                    if fx < 0.0 or fy < 0.0 or fx >= nx or fy >= ny:
                        continue
                    ix = int(fx)
                    if (bits[base + int(fy) * rb + (ix >> 3)] >> (7 - (ix & 7))) & 1:
                        out[k, n] = True


def query_par(q: SupportQuery, x, y, tk, chunks: int = CHUNKS) -> np.ndarray:
    """[N, T] bool, the same as q.query(x, y, tk), candidates in parallel chunks."""
    xt = np.ascontiguousarray(np.asarray(x, np.float64).T)
    yt = np.ascontiguousarray(np.asarray(y, np.float64).T)
    tk = np.ascontiguousarray(tk, np.float64)
    out = np.zeros(xt.shape, np.bool_)
    if q._place:
        boff, im, fm = q.arrays()
        _query_par(q.bits, boff, im, fm, q.full, tk, xt, yt, out, min(chunks, max(1, xt.shape[1] // 8)))
    return np.ascontiguousarray(out.T)
