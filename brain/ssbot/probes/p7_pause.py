"""P7: when can Esc still pause after Hornet is hit? (training copy, unfocused, sandbox Classic save)

1. Gate traces: hurt once (ENEMY, then SPIKES) and record every frame's pause gates for ~3 s.
2. Pause attempts: hurt, wait d ms, tap Esc, check whether the game paused; for a range of d.
Heals back to full between trials with pdset (training only).
"""
import json
import time
from pathlib import Path

from ssbot.io.sinks.oracle_inject import OracleClient
from ssbot.probes.p3_inject import load_slot_one, step

GATES = ("frame", "state", "timeScale", "timeSlowed", "pauseAllowed", "acceptingInput", "disablePause",
         "blockingInteractable", "invuln", "hp")


def settle(c: OracleClient) -> None:
    """Wait until the hero is back to normal: playing, no i-frames, pause allowed; then heal."""
    c.wait_for(lambda s: s.get("state") == "PLAYING" and not s.get("invuln") and s.get("pauseAllowed")
               and not s.get("disablePause") and not s.get("timeSlowed"), 10)
    c._call("pdset health 5")
    time.sleep(0.3)


def gate_trace(c: OracleClient, hazard: str, frames: int) -> None:
    settle(c)
    path = c._call(f"trace {frames}").split(" ", 1)[1]
    time.sleep(0.1)
    hit_frame = int(c._call(f"hurt 1 {hazard}").split()[1])
    time.sleep(frames / 60 + 0.5)
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines()]
    print(f"\n== {hazard}: hit at frame {hit_frame}; gate changes ==")
    last = None
    t0 = next((r["t"] for r in rows if r["frame"] >= hit_frame), rows[0]["t"])
    for r in rows:
        cur = tuple(r.get(k) for k in GATES[1:])
        if cur != last:
            print(f"  +{(r['t'] - t0) * 1000:7.1f} ms  f{r['frame'] - hit_frame:+4d}  " +
                  " ".join(f"{k}={r.get(k)}" for k in GATES[1:]))
            last = cur


def pause_attempts(c: OracleClient, delays_ms: list[int]) -> None:
    print("\n== Esc at d ms after an ENEMY hit ==")
    for d in delays_ms:
        settle(c)
        c._call("hurt 1 ENEMY")
        time.sleep(d / 1000)
        c.tap("pause", 0.05)
        time.sleep(0.25)
        s = c.state()
        paused = s.get("state") == "PAUSED"
        print(f"  d={d:4d} ms -> {'PAUSED' if paused else 'not paused'}  (disablePause={s.get('disablePause')}, "
              f"timeSlowed={s.get('timeSlowed')}, pauseAllowed={s.get('pauseAllowed')})")
        if paused:
            c.wait_for(lambda s: s.get("menu") == "PAUSE_MENU" and not s.get("menuFading"), 5)
            time.sleep(0.4)
            c.tap("enter", 0.05)  # Continue
            c.wait_for(lambda s: s.get("state") == "PLAYING", 5)


def main() -> None:
    c = OracleClient()
    c.own(True)
    s = c.state()
    if s.get("state") != "PLAYING":
        s = load_slot_one(c)
    step("playing", s)
    time.sleep(3)
    c.tap("left", 0.3)  # get off the bench
    time.sleep(1)
    gate_trace(c, "ENEMY", 150)
    gate_trace(c, "SPIKES", 240)
    pause_attempts(c, [30, 100, 200, 300, 400, 500, 700, 1000])
    c._call("pdset health 5")
    c.close()


if __name__ == "__main__":
    main()
