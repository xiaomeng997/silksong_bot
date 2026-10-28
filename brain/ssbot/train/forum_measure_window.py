"""Frame-indexed measurement clock and target deaths, fed every raw STATE.

This observes facts only. It neither changes the controller's observations nor
predicts an enemy. The fight starts at wake even when targets spawn later.
"""
from __future__ import annotations

import math
import threading

CLAPPER = "Song Heavy Sentry"


class MeasurementWindow:
    def __init__(self, tap, *, wave: int, expected_targets: int, game_limit: float,
                 wall_limit: float = 180.0, tail_seconds: float = 2.0, max_frames: int = 100_000,
                 defer_wake: bool = False, protocol_version: int = 1):
        if protocol_version not in (1, 2):
            raise ValueError("unsupported measurement protocol")
        self.protocol_version = protocol_version
        self.watchdog_f = None
        self.tap = tap
        self.wave = wave
        self.expected_targets = expected_targets
        self.game_limit = game_limit
        self.wall_limit = wall_limit
        self.tail_seconds = tail_seconds
        self.max_frames = max_frames
        self.lock = threading.Lock()
        self.wake_f = self.wake_ns = self.last_f = None
        self.targets = set()
        self.deaths = {}
        self.times = {}
        self.game_s = 0.0
        self.end_f = self.end_reason = self.end_game_s = None
        self.tail_end_f = self.tail_end_reason = None
        self.errors = set()
        self._pending = [] if defer_wake else None
        self._fixed_wake = None

    def observe(self, state: dict, received_ns: int | None) -> None:
        with self.lock:
            if self._pending is not None:
                if len(self._pending) >= self.max_frames:
                    self.errors.add("intro STATE buffer capacity exceeded")
                else:
                    # The wave intro can rebase tap.wake_frame after the reader
                    # already observed battle start. Retain facts until it commits.
                    self._pending.append(({k: state.get(k) for k in ("f", "dt", "ents", "ev", "room", "game", "act")}, received_ns))
                return
            self._observe(state, received_ns)

    def start_at(self, wake: int | None) -> None:
        """Commit the intro's final f_wake and replay every already received STATE."""
        with self.lock:
            if self._pending is None:
                raise RuntimeError("measurement start was already committed")
            pending, self._pending = self._pending, None
            if not isinstance(wake, int):
                self.errors.add("intro did not provide final f_wake")
                return
            self._fixed_wake = wake
            for state, received_ns in pending:
                self._observe(state, received_ns)

    def _observe(self, state: dict, received_ns: int | None) -> None:
        wake = self._fixed_wake if self._fixed_wake is not None else self.tap.wake_frame
        f = state["f"]
        if wake is None or f < wake or self.tail_end_f is not None:
            return
        if self.wake_f is None:
            self.wake_f, self.wake_ns = wake, received_ns
            if f != wake:
                self.errors.add("wake STATE missing")
        if self.last_f is not None and f != self.last_f + 1:
            self.errors.add("raw STATE gap/duplicate")
            if f <= self.last_f:
                return
        self.last_f = f
        if len(self.times) >= self.max_frames:
            self.errors.add("measurement clock capacity exceeded")
            return
        dt = state.get("dt")
        if not isinstance(dt, (int, float)) or not math.isfinite(dt) or dt < 0:
            self.errors.add("invalid/missing raw dt")
        else:
            self.game_s += dt
        self.times[f] = self.game_s
        if received_ns is None or self.wake_ns is None:
            self.errors.add("missing receive timestamp")
            wall_s = None
        else:
            wall_s = (received_ns - self.wake_ns) / 1e9
        candidates = []
        watchdog = (self.protocol_version == 2 and (state.get("game") or {}).get("paused") is True
                    and bool((state.get("act") or {}).get("lost")))
        if watchdog and self.watchdog_f is None:
            self.watchdog_f = f
        if watchdog:
            candidates.append((f, 0.5, "watchdog"))
        for entity in state.get("ents") or ():
            if entity.get("type_key") != CLAPPER:
                continue
            iid = entity.get("iid")
            if (iid is not None and not entity.get("hidden") and not entity.get("is_dead")
                    and isinstance(entity.get("hp"), (int, float)) and entity["hp"] > 0):
                self.targets.add(iid)
            if iid in self.targets and entity.get("is_dead"):
                self.deaths.setdefault(iid, f)
        for event in state.get("ev") or ():
            ef = event.get("f", f)
            if not isinstance(ef, int) or ef < wake:
                continue
            data = event.get("d") or {}
            if event.get("k") in {"catastrophe", "would_die", "die", "hero_dead", "player_dead"}:
                candidates.append((ef, 0, "lethal"))
            if (event.get("k") == "hit" and data.get("type_key") == CLAPPER
                    and data.get("dead") and (data.get("hp_before") is None or data["hp_before"] > 0)):
                iid = data.get("ent")
                if iid is not None:
                    self.targets.add(iid)
                    self.deaths[iid] = min(ef, self.deaths.get(iid, ef))
        if len(self.targets) > self.expected_targets:
            self.errors.add("ambiguous target identities")
        if len(self.targets) == self.expected_targets and self.targets.issubset(self.deaths):
            candidates.append((max(self.deaths[iid] for iid in self.targets), 1, "targets_dead"))
        if self.game_s >= self.game_limit:
            candidates.append((f, 2, "game_timeout"))
        if wall_s is not None and wall_s >= self.wall_limit:
            candidates.append((f, 3, "wall_timeout"))
        if candidates:
            ef, _, reason = min(candidates)
            if (self.end_f is None or ef < self.end_f
                    or (ef == self.end_f and reason == "lethal")):
                self.end_f, self.end_reason = ef, reason
                self.end_game_s = self.times.get(ef)
                if self.end_game_s is None:
                    self.errors.add("end frame missing from raw clock")
        battles = (state.get("room") or {}).get("battles") or ()
        next_wave = any(b.get("started") and isinstance(b.get("wave"), int)
                        and b["wave"] > self.wave for b in battles)
        if watchdog and self.end_f is not None:
            self.tail_end_f, self.tail_end_reason = f, "watchdog"
        elif next_wave:
            if self.end_f is None:
                self.errors.add("next wave without target death evidence")
            self.tail_end_f, self.tail_end_reason = f - 1, "next_wave"
        elif self.end_f is not None:
            if self.end_reason != "targets_dead":
                self.tail_end_f, self.tail_end_reason = self.end_f, self.end_reason
            elif self.end_game_s is not None and self.game_s - self.end_game_s >= self.tail_seconds:
                self.tail_end_f, self.tail_end_reason = f, "tail_complete"
            elif wall_s is not None and wall_s >= self.wall_limit:
                self.tail_end_f, self.tail_end_reason = f, "tail_wall_limit"

    def snapshot(self) -> dict:
        with self.lock:
            result = {"wake_f": self.wake_f, "last_f": self.last_f, "game_s": self.game_s,
                    "target_ids": sorted(self.targets), "deaths": {str(k): v for k, v in self.deaths.items()},
                    "end_f": self.end_f, "end_reason": self.end_reason, "T": self.end_game_s,
                    "tail_end_f": self.tail_end_f, "tail_end_reason": self.tail_end_reason,
                    "timeout_overshoot_s": max(0.0, self.end_game_s - self.game_limit)
                        if self.end_reason == "game_timeout" and self.end_game_s is not None else 0.0,
                    "errors": sorted(self.errors), "complete": self.end_f is not None and not self.errors
                        and self.end_game_s is not None and self.end_game_s > 0,
                    "time_convention": "sum raw dt for wake_f <= f <= end_f; frame-end boundary"}
            if self.protocol_version == 2:
                result.update(protocol_version=2, watchdog_f=self.watchdog_f,
                              operational_failure=self.watchdog_f is not None,
                              exposure_terminated_by_failure=self.end_reason == "watchdog")
            return result

    def finish_at(self, frame: int, reason: str) -> None:
        """A controller quit/episode fault is a failure, never a technical exclusion."""
        with self.lock:
            if self.end_f is not None:
                if self.tail_end_f is None:
                    self.tail_end_f, self.tail_end_reason = frame, reason
                return
            self.end_f, self.end_reason = frame, reason
            self.end_game_s = self.times.get(frame)
            self.tail_end_f, self.tail_end_reason = frame, reason
            if self.end_game_s is None:
                self.errors.add("failure frame missing from raw clock")
            if reason == "episode_harness_fail" and not (self.protocol_version == 2 and self.watchdog_f is not None):
                self.errors.add("episode fault: unobserved HP/time interval cannot be assumed empty")
