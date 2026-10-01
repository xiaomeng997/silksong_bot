"""DegradedOracleBackend = OracleBackend -> ObservabilityFilter -> SimpleNoise -> DelayLine: the simulated final
path (DESIGN §3.9.2, §4.5). The oracle's action-side delay is configured separately (delay_line.set_action_latency).

    deg = DegradedOracleBackend(OracleBackend(bosses=[BELL_BEAST]), ObservabilityFilter(bosses=[BELL_BEAST]))
    deg.reset(episode_seed)
    ws = deg.feed(state)        # every STATE, in order; None while the delay line fills
"""
from collections.abc import Callable

import numpy as np

from ssbot.backends.delay_line import DelayLine
from ssbot.backends.noise_simple import SimpleNoise
from ssbot.backends.observability import ObservabilityFilter
from ssbot.backends.oracle_backend import OracleBackend
from ssbot.core.worldstate import WorldState


class DegradedOracleBackend:
    def __init__(self, oracle: OracleBackend, filt: ObservabilityFilter, noise: SimpleNoise | None = None,
                 delay: DelayLine | None = None, source: Callable[[], dict] | None = None):
        self.oracle = oracle
        self.filt = filt
        self.noise = noise if noise is not None else SimpleNoise()
        self.delay = delay if delay is not None else DelayLine()
        self.source = source

    def reset(self, seed: int) -> int:
        """New episode: forget all memory, reseed noise and delay (independent streams). Returns the episode's k."""
        noise_seed, delay_seed = (int(c.generate_state(1)[0]) for c in np.random.SeedSequence(seed).spawn(2))
        self.oracle.reset()
        self.filt.reset()
        self.noise.reset(noise_seed)
        return self.delay.reset(delay_seed)

    def feed(self, state: dict) -> WorldState | None:
        return self.delay.push(self.noise.apply(self.filt.apply(self.oracle.feed(state))))

    def step(self) -> WorldState | None:
        if self.source is None:
            raise RuntimeError("DegradedOracleBackend.step() needs a source; use feed(state)")
        return self.feed(self.source())
