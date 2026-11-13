"""Task 182, Sol seq354 (#409): the manual-air B2 worker's garbage-collection policy (no heavy imports: tests run it in a child).

b13b404 bout 40 (ep39, f123311): the STATE reader thread (ipc.oracle_link._read_loop) unpacked STATE 123311 and its allocation
started an automatic full (gen2) collection: 68.48 ms wall, 62.5 ms thread CPU, nothing collected. It held the GIL until the state
was published, the tick started 68.6 ms late, its send targeted a frame already received, and the B2 receipt gate stopped the
batch (correctly). In that batch's 40 bouts 48 automatic gen2 collections ran inside fights (p50 ~28 ms; the five over 45 ms all
after bout 23, each a bout's second one).

The policy, for the manual-air B2 worker only (tools.combat_run.worker):
- prepare(): once before combat, collect and freeze (the original manual_air_precombat_collect_and_freeze), then raise the
  automatic gen2 threshold to GEN2_THRESHOLD; gen0 / gen1 keep theirs. A bout runs a few dozen gen1 collections (b13b404:
  ~26 per bout), and every full collection restarts the count, so no bounded bout reaches an automatic gen2.
- bout(): before every bout really starts (the worker's episode loop, before run_episode), unfreeze, collect everything, freeze
  what is alive again: last bout's garbage is freed and the long-lived heap stays out of the bout's young collections.
Both return a receipt (the original b2_gc_ready fields, plus thresholds and the process RSS as read). Nothing here runs on a
decision tick, the receive thread or a send; the B2 receipt gate and its bounds are unchanged."""
from __future__ import annotations

import gc
import os
import time

GEN2_THRESHOLD = 10_000     # gen1 collections before an automatic gen2 (CPython's third threshold); b13b404 bouts ran ~26


def rss() -> int | dict:
    """The process resident set (psutil memory_info().rss, bytes), or why it could not be read."""
    try:
        import psutil
        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception as exc:  # noqa: BLE001 - the receipt says so instead of failing the worker
        return {"failed": type(exc).__name__ + ": " + str(exc)}


def prepare() -> dict:
    """Before combat: collect, freeze, move automatic gen2 out of fights. The original b2_gc_ready fields stay as they were."""
    started = time.perf_counter()
    before = gc.get_freeze_count()
    collected = gc.collect()
    gc.freeze()
    threshold_before = list(gc.get_threshold())
    gc.set_threshold(threshold_before[0], threshold_before[1], GEN2_THRESHOLD)
    ms = (time.perf_counter() - started) * 1000.
    return {"policy": "manual_air_precombat_collect_and_freeze", "before": before, "collected": collected,
            "frozen": gc.get_freeze_count(), "gc_enabled": gc.isenabled(), "ms": ms,
            "threshold_before": threshold_before, "threshold": list(gc.get_threshold()),
            "gen2_policy": "automatic gen2 out of fights (threshold %d); bout() before every bout" % GEN2_THRESHOLD,
            "rss": rss()}


def bout(episode=None) -> dict:
    """Before a bout really starts (outside any tick): unfreeze, full collection, freeze again. The receipt keeps the b2_gc_ready
    field names (before / collected / frozen / gc_enabled / ms) and adds the thresholds and the RSS before and after."""
    rss_before = rss()
    started = time.perf_counter()
    before = gc.get_freeze_count()
    gc.unfreeze()
    collected = gc.collect()
    gc.freeze()
    ms = (time.perf_counter() - started) * 1000.
    return {"policy": "manual_air_bout_unfreeze_collect_freeze", "episode": episode, "before": before,
            "collected": collected, "frozen": gc.get_freeze_count(), "gc_enabled": gc.isenabled(), "ms": ms,
            "threshold": list(gc.get_threshold()), "gen_counts": list(gc.get_count()),
            "rss_before": rss_before, "rss_after": rss()}
