"""Read-only B2 bootstrap proof from the worker's own OracleLink.

This records the current connection before preparation/reset/ACTION. It does
not configure latency, repair a queue or certify later action acceptance.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path


def validate_input_path(stats):
    if not isinstance(stats, dict):
        raise ValueError("input.stats must be a map")
    latency, hold = stats.get("latency"), stats.get("hold")
    if not isinstance(latency, dict) or not isinstance(hold, dict):
        raise ValueError("input.stats missing latency/hold configuration")
    for name in ("delay_frames", "jitter_frames"):
        if type(latency.get(name)) is not int or latency[name] != 0:
            raise ValueError("input.stats nonzero/unknown " + name)
    if latency.get("dist") is not None:
        raise ValueError("input.stats explicit latency distribution is not bound")
    for name in ("min_press_frames", "min_release_frames"):
        if type(hold.get(name)) is not int or hold[name] != 2:
            raise ValueError("input.stats HoldFilter differs: " + name)
    if type(stats.get("pending")) is not int or stats["pending"] != 0:
        raise ValueError("input.stats pending ACTION queue is not empty/known")
    return {"latency_frames": 0, "min_press_frames": 2,
            "min_release_frames": 2, "pending": 0}


def capture_input_path(link, path, *, instance, timeout_s=10.):
    """Query only this connected worker; exclusively retain success or failure."""
    record = {"schema": 1, "at": datetime.now(timezone.utc).isoformat(),
              "rpc": "input.stats", "read_only": True, "passed": False,
              "instance": instance, "worker_pid": os.getpid(),
              "scope": "worker connection bootstrap; not later application proof"}
    with Path(path).open("x", encoding="utf-8") as out:
        try:
            record["peer"] = list(link.sock.getpeername())
            record["frame_before"] = link.frame
            record["raw"] = link.rpc("input.stats", timeout_s=timeout_s)
            record["frame_after"] = link.frame
            record["verified"] = validate_input_path(record["raw"])
            record["passed"] = True
            return record
        except Exception as exc:
            record["error"] = type(exc).__name__ + ": " + str(exc)
            raise
        finally:
            json.dump(record, out, ensure_ascii=False, indent=1, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
