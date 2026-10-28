"""Recompute clocks, HP losses and enemy-event denominators from raw recordings."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from ssbot.record import formats
from ssbot.record.recorder import RecordingReader
from ssbot.train.forum_measure_metrics import audit_states
from ssbot.train.forum_measure_window import MeasurementWindow


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--instance", type=int, required=True)
    ap.add_argument("--episode", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    attempt = next(json.loads(line) for line in (a.run / f"attempts_i{a.instance}.jsonl").read_text("utf-8").splitlines()
                   if line and json.loads(line).get("episode") == a.episode)
    wake, last = attempt["f_wake"], attempt["f_end"]
    is_two = attempt["unit"] == "Forum_W_w13"
    window = MeasurementWindow(SimpleNamespace(wake_frame=wake), wave=13 if is_two else 7,
                               expected_targets=2 if is_two else 1, game_limit=120 if is_two else 60)
    reader, states = RecordingReader(attempt["recording"]), []
    for _, received_ns, _, flags, _, payload in reader.records("state"):
        frame = formats.peek(payload, ("f",), flags).get("f")
        if not isinstance(frame, int) or frame < wake - 1:
            continue
        if frame > last + 2:
            break
        state = formats.peek(payload, ("f", "dt", "hero", "ents", "ev", "room"), flags)
        states.append(state)
        window.observe(state, received_ns)
    if attempt.get("outcome") != "CLEAR":
        window.finish_at(last, "episode_" + str(attempt.get("outcome", "unknown")).lower())
    measured = window.snapshot()
    end = measured["end_f"] if measured["end_f"] is not None else last
    audited = audit_states(states, wake_f=wake, end_f=end, target_ids=measured["target_ids"])
    if measured["T"] is not None and measured["T"] != audited["T"]:
        audited["problems"].append("online/offline game-clock mismatch")
        audited["complete"] = False
    result = {"run": str(a.run), "instance": a.instance, "episode": a.episode,
              "historical_recalculation": "measurement" not in attempt,
              "window": measured, "metrics": audited,
              "complete": measured["complete"] and audited["complete"]}
    result["success"] = measured["end_reason"] == "targets_dead" and attempt.get("outcome") == "CLEAR"
    result["K_star"] = audited["T"] if result["success"] else 120.0 if is_two else 60.0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=1, allow_nan=False)
        out.write("\n")
    print(json.dumps({"complete": result["complete"], "window": measured,
                      "L": audited["L"], "T": audited["T"], "problems": audited["problems"],
                      "hammers": audited["hammer_counts"]}, indent=1))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
