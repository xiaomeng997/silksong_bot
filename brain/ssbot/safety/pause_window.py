"""The Q1 pause window, per hit (DESIGN §3.7.5): after an enemy hit, disablePause holds through the recoil, so a Q1
pause can only land between the hit-freeze / recoil end (the PauseGate opens again) and the end of the i-frames, and
that window must be longer than detection + pause-loop latency. This module measures it for every hit from oracle
STATE, records where a pause actually landed, and raises an alert when a window is too short to rely on.

    mon = PauseWindowMonitor(detect_s=0.05, loop_s=0.10)
    every STATE:  mon.update(s)          # closed windows are appended to mon.windows; mon.alerts lists short ones

Per hit (STATE event "damage"): t_hit; t_open, the first frame after it with pause.blk == 0 (a Pause press would
pause); t_iframes_end, the first frame with the hero no longer invulnerable (hero.invulnerable false; with the oracle's
hero.tm section, hero.tm.inv reaching 0); t_pause, the frame game.paused turns true. The usable window is
t_iframes_end - t_open; margin = window - (detect_s + loop_s). While the window is open, hero.tm.inv (scaled seconds
of invulnerability left) gives an early estimate of its end, a lower bound in real time (scaled time runs slower in
freezes), so a short window alerts as soon as the gate opens.

Measured on the Bell Beast runs (trial 20261001_121446 i0_000: 99 hits; live 20261001_122249 i0_000 and i2_000: 1003
and 1145 hits): the gate reopens p50 0.232 s after the hit (max 0.55 s, a hit during a Bind: the BindBreak freeze), the
i-frames end 1.10-2.08 s after it, and the window is at least 0.945 s (p50 0.950 s) on every hit, against probe P7's
250 ms to about 1.2 s (§3.7.5). A "damage" event at 1 HP that LethalBlock swallowed in data mode (no recoil, the gate
never closes, no i-frames: 18 of 2265) is marked no_effect and never alerts. A parry's i-frames are only 0.15 s (probe
P11): a hit then leaves a much shorter window, which is what the alert is for.
"""
from dataclasses import dataclass, field


@dataclass(slots=True)
class HitWindow:
    f_hit: int
    t_hit: float
    source: str | None = None
    t_open: float | None = None          # PauseGate open again (pause.blk == 0)
    t_iframes_end: float | None = None   # invulnerability over
    t_iframes_est: float | None = None   # estimate from hero.tm.inv at the gate opening (lower bound)
    t_pause: float | None = None         # a pause landed (game.paused)
    gate_closed: bool = False            # the PauseGate closed after the hit (every hit that lands does)
    no_effect: bool = False              # neither the gate closed nor i-frames started: the hit did not land
    closed: bool = False

    @property
    def window_s(self) -> float | None:
        end = self.t_iframes_end if self.t_iframes_end is not None else self.t_iframes_est
        if self.t_open is None or end is None:
            return None
        return end - self.t_open

    def row(self) -> dict:
        def rel(t: float | None) -> float | None:
            return None if t is None else round(t - self.t_hit, 4)
        return {"f_hit": self.f_hit, "source": self.source, "open_s": rel(self.t_open),
                "iframes_end_s": rel(self.t_iframes_end), "iframes_est_s": rel(self.t_iframes_est),
                "pause_s": rel(self.t_pause), "window_s": None if self.window_s is None else round(self.window_s, 4),
                "no_effect": self.no_effect}


@dataclass(slots=True)
class PauseWindowMonitor:
    detect_s: float = 0.05               # cue detection (oracle: the frame itself; vision: P8 max 49.6 ms)
    loop_s: float = 0.10                 # one press cycle (6 frames) + input latency
    qpc_freq: float = 1e7
    windows: list[HitWindow] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    open: HitWindow | None = None

    @property
    def need_s(self) -> float:
        return self.detect_s + self.loop_s

    def _check(self, w: HitWindow, final: bool) -> None:
        ws = w.window_s
        if not w.no_effect and ws is not None and ws < self.need_s and (final or w.t_iframes_end is None):
            msg = (f"Q1 pause window after the hit at frame {w.f_hit}: {ws:.3f} s < detect + loop "
                   f"{self.need_s:.3f} s")
            if msg not in self.alerts:
                self.alerts.append(msg)

    def _close(self) -> None:
        w = self.open
        if w is not None:
            w.closed = True
            self._check(w, True)
            self.windows.append(w)
            self.open = None

    def update(self, s: dict) -> HitWindow | None:
        """Feed one STATE; returns the window that closed on it, if any."""
        t = (s.get("q") or 0) / self.qpc_freq
        hits = [ev for ev in s.get("ev") or () if ev.get("k") == "damage"]
        done = None
        if hits:
            if self.open is not None:     # a hit inside the previous window (a hazard, a grab): that one ends here
                done = self.open
                self._close()
            d = hits[0].get("d") or {}
            self.open = HitWindow(f_hit=int(s.get("f") or 0), t_hit=t, source=d.get("source"),
                                  gate_closed=bool((s.get("pause") or {}).get("blk")))
            return done
        w = self.open
        if w is None:
            return None
        hero = s.get("hero") or {}
        tm = hero.get("tm") if isinstance(hero.get("tm"), dict) else None
        inv = hero.get("invulnerable") if tm is None or tm.get("inv") is None else float(tm["inv"]) > 0
        blk = (s.get("pause") or {}).get("blk")
        w.gate_closed |= bool(blk)
        if w.t_open is None and blk == 0:
            w.t_open = t
            if not w.gate_closed and inv is False:
                w.no_effect = True        # LethalBlock (data mode) swallowed a lethal hit: no recoil, no i-frames
            if tm is not None and tm.get("inv") is not None:
                w.t_iframes_est = t + float(tm["inv"])
                self._check(w, False)
        if (s.get("game") or {}).get("paused") and w.t_pause is None:
            w.t_pause = t
        if inv is False and w.t_iframes_end is None and "hero" in s:
            w.t_iframes_end = t
        if w.t_iframes_end is not None or w.t_pause is not None:
            done = w
            self._close()
        return done
