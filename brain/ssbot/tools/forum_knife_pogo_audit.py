"""Read-only development audit of downspike protection against real FixedUpdates.

The existing 34 successful hook/down contacts are development data. This isolates
protection timing, not trajectory safety, future enemy behavior or treatment benefit.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def counter_after_steps(initial, steps):
    counts = np.asarray(steps)
    if (counts.ndim != 1 or not np.isfinite(counts).all() or np.any(counts < 0)
            or np.any(counts != np.floor(counts)) or initial < 0 or int(initial) != initial):
        raise ValueError("invalid physics counter input")
    return np.maximum(int(initial) - np.cumsum(counts, dtype=np.int64), 0)


def audit_case(case, params):
    from ssbot.knowledge import kinematics as km
    from ssbot.record.recorder import RecordingReader
    fa, iid = int(case["fa"]), int(case["iid"])
    contact = fa + int(case["hit_k"])
    out = {"episode": case["ep"], "wave": case["wave"], "recording": case["recording"],
           "iid": iid, "contact": contact, "complete": False, "passed": False}
    try:
        rr = RecordingReader(case["recording"])
        last = contact + 24
        states = list(rr.states(contact - 1, last, keys=("hero", "dt", "udt", "fs", "ev")))
        frames = require_frames_without_inputs(states, contact - 1, last)
        hits = [ev for ev in frames[contact].get("ev", ()) if ev.get("k") == "hit"
                and ev.get("d", {}).get("ent") == iid
                and "Down" in str(ev.get("d", {}).get("src", ""))]
        if not hits:
            raise ValueError("listed down contact absent from raw events")
        counters = np.array([frames[f]["hero"]["cstate_int"][1] for f in range(contact, last + 1)])
        fs = np.array([frames[f]["fs"] for f in range(contact, last + 1)])
        # Stop before another reset: audit it separately, never relabel it as
        # the continuation of this contact's eight-step protection.
        resets = np.flatnonzero(counters[1:] > np.maximum(counters[:-1] - fs[1:], 0)) + 1
        end = int(resets[0]) if len(resets) else len(counters)
        predicted = np.r_[counters[0], counter_after_steps(counters[0], fs[1:])]
        exact = bool(np.array_equal(predicted[:end], counters[:end]))
        dt = np.array([frames[f]["dt"] for f in range(contact, last + 1)])
        udt = np.array([frames[f]["udt"] for f in range(contact, last + 1)])
        start = km.initial_state(params, 30., 12., ground=False)
        events = np.zeros((1, len(dt)), np.int64); events[0, 0] = km.EV_POGO
        ro = km.rollout(start, np.zeros_like(events), params, dt=dt, fs=fs, udt=udt,
                        events=events, threads=1)
        timer = (ro.flags[0, 1:] & km.F_INVULN) != 0
        observed = counters > 0
        # Separately screen the normal-future-clock support from the real
        # pre-contact phase. Actual future fs are never supplied to this check.
        from ssbot.map2.oldwin_claw import pogo_protection
        from ssbot.tools.reflex_val import _her_state
        phase_state = _her_state(rr, case["recording"], contact - 1, params)
        clock = {"scope": "nominal future clock from observed pre-contact phase"}
        try:
            nominal, every, any_lane = pogo_protection(phase_state, events, params)
            certified = every[0, 1:]
            clock.update(checked=True,
                         overclaimed_frames=(contact + np.flatnonzero(certified[:end] & ~observed[:end])).tolist(),
                         conservative_short_frames=(contact + np.flatnonzero(observed[:end] & ~certified[:end])).tolist(),
                         phase=[float(phase_state[k]) for k in (km.ALPHA,km.ALO,km.AHI)])
        except ValueError as exc:
            clock.update(checked=False, reason=str(exc))
        timer_short = np.flatnonzero(observed[:end] & ~timer[:end])
        timer_long = np.flatnonzero(~observed[:end] & timer[:end])
        out.update(complete=True, passed=exact and counters[0] == 8
                       and clock["checked"] and not clock["overclaimed_frames"],
                   initial_count=int(counters[0]), contact_fs=int(fs[0]),
                   counter_recurrence_exact=exact, future_clock=clock,
                   next_reset_frame=None if not len(resets) else contact + int(resets[0]),
                   compared_frames=end, observed_protected_frames=int(observed[:end].sum()),
                   timer_short_frames=(contact + timer_short).tolist(),
                   timer_long_frames=(contact + timer_long).tolist(),
                   frames=[{"f": f, "k": f-contact, "fs": int(frames[f]["fs"]),
                            "dt": frames[f]["dt"], "counter": int(counters[f-contact]),
                            "counter_predicted": int(predicted[f-contact]),
                            "timer_invulnerable": bool(timer[f-contact]),
                            "health": frames[f]["hero"].get("health"),
                            "events": [ev for ev in frames[f].get("ev", ())
                                       if ev.get("k") in ("hit", "damage", "hp", "damage_blocked")]}
                           for f in range(contact, last+1)])
    except (ValueError, KeyError, IndexError) as exc:
        out["error"] = str(exc)
    return out


def require_frames_without_inputs(states, first, last):
    from ssbot.tools.forum_knife_claw_audit import require_frames
    # Reuse strict gap/clock validation; this timing audit does not need keys.
    return require_frames([{**s, "act": {"mask": 0}} for s in states], first, last)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--e-cores-idle", action="store_true")
    a = ap.parse_args(argv)
    if a.e_cores_idle:
        import psutil
        p = psutil.Process(); p.cpu_affinity(list(range(16,32))); p.nice(psutil.IDLE_PRIORITY_CLASS)
        assert p.cpu_affinity() == list(range(16,32)) and p.nice() == psutil.IDLE_PRIORITY_CLASS
    from ssbot.map2.envelope import load_params
    schema_path = Path(__file__).resolve().parents[3] / "docs/facts/1.0.30000/cstate_schema.json"
    schema = json.loads(schema_path.read_text())
    assert schema["ints"][1] == "downspikeInvulnerabilitySteps"
    if a.out.exists(): raise FileExistsError(a.out)
    cases = list(csv.DictReader(a.cases.read_text(encoding="utf-8-sig").splitlines()))
    if not cases: raise ValueError("empty development case list")
    params = load_params(hero2=True)
    results = []
    for case in cases:
        result = audit_case(case, params); results.append(result)
        print(json.dumps({k:v for k,v in result.items() if k not in ("frames", "recording")}),flush=True)
    report = {"scope": __doc__, "cases":len(results), "passed":sum(r["passed"] for r in results),
              "all_passed": all(r["passed"] for r in results), "production_enabled":False,
              "source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "case_source_sha256":hashlib.sha256(a.cases.read_bytes()).hexdigest(),
              "schema_sha256":hashlib.sha256(schema_path.read_bytes()).hexdigest(), "results":results}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("x",encoding="utf-8") as stream:
        json.dump(report,stream,indent=1,allow_nan=False)
    return 0 if report["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
