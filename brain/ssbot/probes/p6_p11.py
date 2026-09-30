"""P6 (timer rules) and P11 (serialized constants) on the training copy, unfocused.

Writes C:/ssbot/sandbox/constants_1.0.30000.json and a per-poll trace CSV, and prints for each
situation how much in-game time passed per second of wall time.
"""
import csv
import json
import time
from pathlib import Path

from ssbot.io.sinks.oracle_inject import OracleClient
from ssbot.probes.p3_inject import load_slot_one, step

OUT = Path(r"C:\ssbot\sandbox")
FIELDS = ("wall", "frame", "state", "menu", "scene", "playTime", "inventoryOpen", "timeScale", "keys", "hero")


class Tracer:
    def __init__(self, c: OracleClient, path: Path):
        self.c = c
        self.f = path.open("w", newline="", encoding="utf-8")
        self.w = csv.DictWriter(self.f, fieldnames=FIELDS, extrasaction="ignore")
        self.w.writeheader()

    def sample(self) -> dict:
        s = self.c.state()
        s["wall"] = round(time.perf_counter(), 4)
        self.w.writerow(s)
        return s

    def measure(self, label: str, seconds: float) -> float:
        """In-game seconds per wall second over a window, sampling at ~60 Hz."""
        a = self.sample()
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            time.sleep(1 / 60)
            b = self.sample()
        ratio = (b["playTime"] - a["playTime"]) / (b["wall"] - a["wall"])
        print(f"{label:<34} playTime/wall = {ratio:.3f}   (state={b['state']} inv={b.get('inventoryOpen')} scene={b['scene']})")
        return ratio

    def close(self) -> None:
        self.f.close()


def main() -> None:
    c = OracleClient()
    c.own(True)
    s = c.state()
    if s.get("state") != "PLAYING":
        s = load_slot_one(c)
    step("playing", s)
    time.sleep(4.0)  # let the bench wake-up animation finish

    constants = json.loads(c._call("constants"))
    (OUT / "constants_1.0.30000.json").write_text(json.dumps(constants, indent=1), encoding="utf-8")
    print("engine:", constants["engine"])
    hero = constants.get("hero", {})
    for k in sorted(hero):
        if any(t in k.upper() for t in ("INVUL", "DASH", "SPEED", "QUEUE", "RECOIL", "FREEZE", "JUMP_STEPS", "BIND", "PARRY")):
            print(f"  {k} = {hero[k]}")

    t = Tracer(c, OUT / "p6_trace.csv")
    t.measure("baseline PLAYING", 2.0)

    c.tap("inventory")
    time.sleep(1.0)
    t.measure("inventory open", 2.0)
    c.tap("inventory")
    time.sleep(1.0)
    t.measure("after closing inventory", 2.0)

    c.keys("quickmap")
    time.sleep(0.8)
    t.measure("quick map held (Tab)", 2.0)
    c.keys()
    time.sleep(1.0)
    t.measure("after quick map", 1.5)

    # Walk left until the scene changes, then compare in-game and wall time across the transition.
    scene0 = t.sample()["scene"]
    c.keys("left")
    start = t.sample()
    deadline = time.perf_counter() + 20
    while time.perf_counter() < deadline:
        time.sleep(1 / 60)
        cur = t.sample()
        if cur["scene"] != scene0 and cur["state"] == "PLAYING":
            break
    c.keys()
    time.sleep(1.0)
    end = t.sample()
    print(f"transition {scene0} -> {end['scene']}: wall {end['wall'] - start['wall']:.2f}s, "
          f"playTime {end['playTime'] - start['playTime']:.2f}s")
    t.close()
    c.close()


if __name__ == "__main__":
    main()
