"""Observation delay for the simulated final path, and the client of the oracle's action-side path emulation
(DESIGN §3.9.2 "DelayLine/InputPathEmulator").

Observation side (here): the brain sees the WorldState of k STATEs ago, k drawn once per episode from the loopback
prior 2/3/4 frames with weights 0.3/0.5/0.2 (seeded, so an episode replays with the same k).

    delay = DelayLine(seed=episode_seed)        # or delay.reset(seed) at each episode start
    ws = delay.push(noise.apply(filt.apply(backend.feed(state))))   # None for the first k STATEs

Action side (the oracle, oracle/src/Input/{LatencyModel,DelayLine,InputModule}.cs): RPC "input.latency_model" with
{delay_frames, jitter_frames, seed, dist?: [[frames, weight], ...], min_press_frames?, min_release_frames?}; it
returns the active model, and a call without arguments only queries it. Each ACTION then takes effect at
max(target_frame, arrival frame) + one draw (dist if given, else delay +- uniform jitter), never overtaking an
earlier ACTION; ACTIONs more than 3 frames late on arrival are dropped. Draws come from System.Random(seed), one per
accepted ACTION. Settings last for one connection; a new connection is oracle-exact (0 frames, press/release 2/2).
latency_model_args() builds and checks the arguments; set_action_latency(link, ...) sends them.

The 2/3/4 prior is the WHOLE loop (P8: SendInput -> first changed captured frame p50 45.6 ms, about 2.7 frames).
Putting it on both sides counts it twice: keep the action side at its default 0 unless the split between capture
delay and input delay has been measured (M3 loopback).
"""
from collections import deque
from collections.abc import Sequence

import numpy as np

from ssbot.core.worldstate import Unobs, WorldState

PRIOR = ((2, 0.3), (3, 0.5), (4, 0.2))       # loopback prior, frames and weights (§3.9.2)
MAX_DELAY_FRAMES = 60                        # LatencyModel.MaxDelayFrames
HOLD_LIMITS = (1, 30)                        # InputModule: min_press_frames / min_release_frames range


class DelayLine:
    def __init__(self, dist: Sequence[tuple[int, float]] = PRIOR, seed: int = 0):
        frames = np.array([int(k) for k, _ in dist])
        w = np.array([float(p) for _, p in dist])
        if len(frames) == 0 or (frames < 0).any() or not (w > 0).all():
            raise ValueError(f"bad delay distribution {dist}")
        self.frames = frames
        self.weights = w / w.sum()
        self.k = 0
        self.reset(seed)

    def reset(self, seed: int) -> int:
        """New episode: draw k and empty the line. Returns k."""
        rng = np.random.default_rng(seed)
        self.k = int(rng.choice(self.frames, p=self.weights))
        self._buf: deque[WorldState] = deque(maxlen=self.k + 1)
        return self.k

    def push(self, ws: WorldState) -> WorldState | None:
        """Add this frame's WorldState; return the one from k STATEs ago (None while the line fills)."""
        self._buf.append(ws)
        if len(self._buf) <= self.k:
            return None
        out = self._buf[0]
        out.perception.frame_age_ms = (ws.stamp.t_sample_qpc_ns - out.stamp.t_sample_qpc_ns) / 1e6
        if self.k:
            out.game.unobservable = int(out.game.unobservable | Unobs.DELAYED)
        return out


def latency_model_args(seed: int, dist: Sequence[tuple[int, float]] | None = None, delay_frames: int = 0,
                       jitter_frames: int = 0, min_press_frames: int | None = None,
                       min_release_frames: int | None = None) -> dict:
    """Arguments of RPC "input.latency_model", checked against the oracle's limits (LatencyModel.Configure,
    InputModule.SetLatencyModel) so a bad call fails here rather than as an RPC error."""
    if not 0 <= delay_frames <= MAX_DELAY_FRAMES or not 0 <= jitter_frames <= MAX_DELAY_FRAMES:
        raise ValueError(f"delay_frames and jitter_frames must be in [0, {MAX_DELAY_FRAMES}]")
    s = int(seed) & 0xFFFFFFFF               # the oracle reads it as a C# int (unchecked cast)
    args: dict = {"delay_frames": int(delay_frames), "jitter_frames": int(jitter_frames),
                  "seed": s - (1 << 32) if s > 0x7FFFFFFF else s}
    if dist is not None:
        rows = [[int(k), float(w)] for k, w in dist]
        if not rows or any(not 0 <= k <= MAX_DELAY_FRAMES or not w > 0 for k, w in rows):
            raise ValueError(f"dist frames must be in [0, {MAX_DELAY_FRAMES}] and weights positive: {dist}")
        args["dist"] = rows
    for name, v in (("min_press_frames", min_press_frames), ("min_release_frames", min_release_frames)):
        if v is not None:
            if not HOLD_LIMITS[0] <= v <= HOLD_LIMITS[1]:
                raise ValueError(f"{name} must be in {list(HOLD_LIMITS)}")
            args[name] = int(v)
    return args


def set_action_latency(link, seed: int, dist: Sequence[tuple[int, float]] | None = None, delay_frames: int = 0,
                       jitter_frames: int = 0, min_press_frames: int | None = None,
                       min_release_frames: int | None = None, timeout_s: float = 10.0) -> dict:
    """Configure the oracle's action-side path emulation on an OracleLink-like object (anything with
    rpc(name, timeout_s=..., **args)); returns the model the oracle reports back."""
    return link.rpc("input.latency_model", timeout_s=timeout_s,
                    **latency_model_args(seed, dist, delay_frames, jitter_frames, min_press_frames,
                                         min_release_frames))
