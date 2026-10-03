"""Velocity of a tracked object from the history of its detections (DESIGN §3.2.7 "跟踪、轨迹预测与游戏时间"): the
estimate a vision tracker has, and the only velocity the simulated final path may hand the brain.

Why. The oracle exports each entity's Rigidbody2D velocity; pixels never show it. The ObservabilityFilter and
SimpleNoise passed it through (SimpleNoise with Gaussian noise added), so anything built on Entity.vel in the vision
view read the game's own physics state (task V, 2026-10-02). Here a velocity is the least-squares slope of the last
detections' positions over game time: it lags an acceleration by half the window (a bell falling at g 66 u/s^2 reads
about 3.3 u/s slow with the 0.1 s window) and carries the position noise (sigma_v = sigma_pos / sqrt(sum (t - mean
t)^2): 0.15 u over 6 frames is about 1.2 u/s). A gap longer than GAP_S starts a new history (a new appearance of the
same object id is a new track for a detector).

    vt = VelocityTracks(); vt.reset()                 # per episode
    e.vel = vt.observe(e.id, t_game, x, y, sigma)     # once per detection, in time order
    vt.prune(t_game)                                  # once per frame: forget objects not seen for a while
"""
import math
from collections import deque

import numpy as np

from ssbot.core.worldstate import E, Src, Vec2, unknown

WINDOW_S = 0.1          # detections within this much game time of the newest one (6 frames at 60 fps) ...
MAX_N = 12              # ... and at most this many; when those span less than MIN_SPAN_S (slow motion: game time
MIN_SPAN_S = 0.03       # runs at 0.05 x), all MAX_N, else unknown (two noisy points 1 ms apart are no velocity)
GAP_S = 0.25            # no detection for this long: the next one starts a new history
FORGET_S = 1.0          # prune(): histories older than this are dropped


class VelocityTracks:
    def __init__(self, window_s: float = WINDOW_S, max_n: int = MAX_N, gap_s: float = GAP_S):
        self.window_s = window_s
        self.max_n = max_n
        self.gap_s = gap_s
        self.reset()

    def reset(self) -> None:
        self.hist: dict[int, deque] = {}

    def observe(self, iid: int, t: float, x: float, y: float, sigma: float = 0.0) -> E[Vec2]:
        """Add a detection of object iid and return its velocity estimate (unknown until two detections at distinct
        game times)."""
        h = self.hist.get(iid)
        if h is None or (h and t - h[-1][0] > self.gap_s):
            h = self.hist[iid] = deque(maxlen=self.max_n)
        h.append((float(t), float(x), float(y), float(sigma)))
        return velocity(h, self.window_s)

    def prune(self, t: float) -> None:
        for iid in [i for i, h in self.hist.items() if not h or t - h[-1][0] > FORGET_S]:
            del self.hist[iid]


def velocity(h, window_s: float = WINDOW_S) -> E[Vec2]:
    """Least-squares slope of the (t, x, y, sigma) rows within window_s of the newest (all rows when those span less
    than MIN_SPAN_S); unknown when even all rows span less (one row, a hit-stop or slow motion: game time stands
    (nearly) still)."""
    if len(h) < 2:
        return unknown((0.0, 0.0))
    a = np.asarray(h, np.float64)
    w = a[a[:, 0] >= a[-1, 0] - window_s]
    if len(w) >= 2 and w[-1, 0] - w[0, 0] >= MIN_SPAN_S:
        a = w
    elif a[-1, 0] - a[0, 0] < MIN_SPAN_S:
        return unknown((0.0, 0.0))
    t = a[:, 0] - a[:, 0].mean()
    den = float((t * t).sum())
    if den <= 1e-9:
        return unknown((0.0, 0.0))
    vx = float((t * (a[:, 1] - a[:, 1].mean())).sum()) / den
    vy = float((t * (a[:, 2] - a[:, 2].mean())).sum()) / den
    s = float(np.sqrt(np.mean(a[:, 3] ** 2)))
    return E((vx, vy), sigma=s / math.sqrt(den), conf=0.8, src=Src.PREDICTED)
