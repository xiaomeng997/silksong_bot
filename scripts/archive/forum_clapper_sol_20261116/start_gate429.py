"""Read-only launch-average cadence check, for use before the existing GO gate."""
from pathlib import Path
import datetime
import hashlib
import json
import math


def check(demo):
    demo = Path(demo)
    try:
        ready = json.loads((demo/'launch/WATCH_READY.json').read_text(encoding='utf-8'))
        launch = json.loads((demo/'launch/readiness.json').read_text(encoding='utf-8'))
        contract = json.loads((demo/'contract.json').read_text(encoding='utf-8'))
        assert ready['source'] == contract['source']
        assert ready['contract_sha256'] == hashlib.sha256((demo/'contract.json').read_bytes()).hexdigest()
        created = float(launch['snapshots'][0]['expected_process']['created'])
        at = datetime.datetime.fromisoformat(ready['at']).timestamp()
        frame = ready['actual_frame']
        assert isinstance(frame, int) and not isinstance(frame, bool) and frame > 0
        seconds = at-created
        assert math.isfinite(seconds) and seconds > 0
        fps = frame/seconds
        assert math.isfinite(fps)
        return dict(passed=fps >= 30.0, fps=fps, frames=frame, seconds=seconds, minimum_fps=30.0,
                    source=contract['source'], scope='Startup average only; not current or combat FPS certification')
    except (OSError, KeyError, IndexError, ValueError, TypeError, AssertionError) as exc:
        return dict(passed=False, reason='missing or invalid bound launch data', error=type(exc).__name__)


if __name__ == '__main__':
    import sys
    result = check(sys.argv[1])
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
