"""M1 probe: record from a running oracle, check STATE frame continuity, open the Rerun viewer.

Needs the training copy running with SsOracle (e.g. `python -m ssbot.tools.launcher -n 1`) and no other brain
connected to that instance. Any game screen works; a gameplay room exercises hero/ents/TERRAIN if those exporters
are installed.

    cd brain
    uv run python -m ssbot.probes.m1_record                       # 60 s, instance 0, then opens the viewer
    uv run python -m ssbot.probes.m1_record --seconds 3600        # the M1 exit run: 60 min >= 99.9 % delivery
    uv run python -m ssbot.probes.m1_record --no-viewer --instance 1

Prints per-10 s progress, the continuity report (delivery %, gaps, oracle/recorder drops, build cost, EOF->brain
latency), file sizes and MB/min, a random-access self-test, then PASS/FAIL. PASS = delivery >= 99.9 %, no
recorder drops, no non-monotonic frames, index consistent with the data and seeks returning the right frames.
"""
import argparse
import collections
import sys
import time
from datetime import datetime

from ssbot.ipc.oracle_link import OracleLink
from ssbot.record.recorder import DEFAULT_OUT, Recorder, RecordingReader


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--game-dir", default=r"C:\ssbot\game\train")
    ap.add_argument("--no-viewer", action="store_true")
    a = ap.parse_args()

    link = OracleLink(instance=a.instance)
    print("hello:", {k: link.hello.get(k) for k in ("plugin", "game", "instance", "qpc_freq")})
    print("rpcs:", link.hello.get("rpcs"))
    rec = Recorder(link, out_dir=a.out, profile="PROBE", episode=f"m1_record_{datetime.now():%H%M%S}_i{a.instance}",
                   game_dir=a.game_dir, config={"probe": "m1_record", "seconds": a.seconds}).start()
    print(f"recording {a.seconds:.0f} s -> {rec.path}")
    t0 = time.monotonic()
    next_report = t0 + 10
    try:
        while time.monotonic() - t0 < a.seconds:
            if link.closed:
                print("oracle connection closed early")
                break
            time.sleep(0.2)
            if time.monotonic() >= next_report:
                s = link.state or {}
                game = s.get("game") or {}
                print(f"  t+{time.monotonic() - t0:5.0f} s  frame {link.frame}  recorded {rec.states}  "
                      f"queue max {rec.max_queue}  drops {rec.dropped['state']}  oracle drop counter "
                      f"{s.get('drop')}  scene {game.get('scene')}  cost_us {s.get('cost_us')}")
                next_report += 10
    except KeyboardInterrupt:
        print("stopped early")
    summary = rec.close()
    link.close()

    reader = RecordingReader(rec.path)
    rep = reader.check(deep=True)
    print("\n" + rep.format())
    print(f"recorder: {summary['streams']['state']['records']} STATE, {summary['streams']['terrain']['records']} "
          f"TERRAIN, {summary['streams']['progress']['records']} PROGRESS, {summary['events']} events; "
          f"drops {summary['drops']}; error {summary['error']}")

    sizes = reader.sizes()
    minutes = max(rep.duration_s or a.seconds, 1e-9) / 60
    for name, size in sizes.items():
        print(f"  {name:24s} {size / 2**20:10.3f} MB")
    total = sum(sizes.values())
    print(f"  {'total':24s} {total / 2**20:10.3f} MB  ({total / 2**20 / minutes:.2f} MB/min)")
    st = summary["streams"]["state"]
    if st["bytes"]:
        print(f"  STATE zstd ratio {st['raw_bytes'] / st['bytes']:.1f}x, {st['raw_bytes'] / max(st['records'], 1):.0f} "
              f"B/frame raw")

    kinds = collections.Counter(ev.get("kind") for ev in reader.events())
    print("events by kind:", dict(kinds.most_common(12)))

    seek_ok = True
    if rep.f_first is not None:
        mid = (rep.f_first + rep.f_last) // 2
        got = [s["f"] for s in reader.states(mid, mid + 5)]
        missing = {f for a_, b_ in rep.gaps for f in range(a_ + 1, b_)}
        want = [f for f in range(mid, mid + 6) if f <= rep.f_last and f not in missing]
        seek_ok = got == want and (reader.state(rep.f_last) or {}).get("f") == rep.f_last
        print(f"random access: states({mid}, {mid + 5}) -> {got}  {'ok' if seek_ok else 'WRONG, expected ' + str(want)}")
        present = [k for k, v in (reader.state(mid) or {}).items() if v is not None]
        print("STATE sections present:", present)

    drops = sum(summary["drops"]["queue"].values()) + summary["drops"]["disk"] + summary["drops"]["failed"]
    ok = rep.ok and drops == 0 and rep.index_consistent and seek_ok and rep.expected > 0
    print(f"\n{'PASS' if ok else 'FAIL'}  delivery {rep.delivery * 100:.4f} % over {rep.expected} frames "
          f"({(rep.duration_s or 0):.0f} s)")

    if not a.no_viewer:
        from ssbot.tools import viewer
        viewer.main([str(rec.path)])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
