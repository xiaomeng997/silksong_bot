"""A/A v2 operational stop rules, separate from statistical effect gates."""
from __future__ import annotations


class PeriodGuard:
    """A known, audited watchdog failure is retained; isolated ones can continue."""
    def __init__(self, *, consecutive_watchdogs=2, total_watchdogs=4):
        self.consecutive_limit, self.total_limit = consecutive_watchdogs, total_watchdogs
        self.streak = {}
        self.watchdogs = 0

    def observe(self, instance, *, outcome, complete, recovered=True):
        reasons = []
        if not complete:
            reasons.append("measurement integrity failure")
        watchdog = outcome == "WATCHDOG"
        self.streak[instance] = self.streak.get(instance, 0) + 1 if watchdog else 0
        self.watchdogs += int(watchdog)
        if watchdog and not recovered:
            reasons.append("watchdog recovery not verified")
        if self.streak[instance] >= self.consecutive_limit:
            reasons.append("same instance reached consecutive watchdog limit")
        if self.watchdogs >= self.total_limit:
            reasons.append("period reached total watchdog limit")
        return reasons


def validate_production_cli(cli):
    if cli.get("engineering_probe") or cli.get("measure_stall_ms", 0):
        raise ValueError("engineering/injected data cannot enter production A/A")
    if cli.get("measurement_protocol") != 2 or not cli.get("measure_diagnostics"):
        raise ValueError("production v2 requires protocol 2 and diagnostics")
