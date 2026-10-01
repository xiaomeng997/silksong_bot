"""Bell Beast start savestate (M2 W0): load a composed savestate (ssbot.tools.savestate_compose), check it, walk into
the trigger, and save the game-written training savestate.

The composed state is the Silk Spear restore point of a person's session (2026-09-30, Hunter, 5 masks, 9 silk,
Silkspear, Bell Beast not yet met) placed in Bone_05 left of the trigger (the person's session: the "Control" FSM of
"Bone Beast" leaves Dormant at hero x ~87.5 on the floor y 3.57). Save suppression stays on throughout, so nothing of
this progress reaches the sandbox slot.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 1 --detach
    ../scripts/uv.cmd run python -m ssbot.probes.m2_bellbeast [--composed bellbeast_compose] [--out bellbeast_arena]

Checks: the load lands in Bone_05 at the composed place; Bone Beast is present and Dormant; walking right wakes it
(Dormant -> Submerged Init) and it emerges (an "Emerge Antic*" state) within 6 s; the game-written savestate `out`
(saved right after the load, before the walk) loads back to the same place with the boss Dormant again.
"""
import argparse
import sys
import time

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.probes.common import load_slot, stand_up

BOSS = "Bone Beast"
SCENE = "Bone_05"


class ControlTracker:
    """The boss "Control" FSM state from the oracle's fsm events: the entity is exported only once it is active (the
    dormant boss is not in "ents"), but its FSM transitions are."""

    def __init__(self, link: OracleLink):
        self.state: str | None = None
        self.log: list[tuple[int, str | None, str]] = []
        link.subscribe_state(self._on)

    def _on(self, s: dict) -> None:
        for ev in s.get("ev") or []:
            if ev.get("k") != "fsm":
                continue
            d = ev["d"]
            if d.get("fsm") == "Control" and str(d.get("obj", "")).startswith(BOSS):
                self.state = d["to"]
                self.log.append((s["f"], d["from"], d["to"]))


def boss(s: dict) -> dict | None:
    for e in s.get("ents") or []:
        if e["type_key"] == BOSS:
            return e
    return None


def check(ok: bool, what: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {what}", flush=True)
    return ok


def load(link: OracleLink, name: str) -> dict:
    r = link.rpc("savestate.load", timeout_s=40.0, name=name, timeout=30)
    s = link.wait_state(lambda s: (s.get("game") or {}).get("scene") == SCENE and s["hero"]["hero_accepting_input"],
                        timeout_s=20.0)
    return {"reply": r, "state": s}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--composed", default="bellbeast_compose")
    ap.add_argument("--out", default="bellbeast_arena")
    a = ap.parse_args(argv)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    ctl = ControlTracker(link)
    ok = True
    try:
        load_slot(link, 1)
        stand_up(link)
        old = link.rpc("guards.get")["save_suppression"]
        ok &= check(link.rpc("guards.set", save_suppression=True)["save_suppression"], "save suppression on")

        r = load(link, a.composed)
        s = r["state"]
        pos = s["hero"]["pos"]
        print("load reply:", {k: r["reply"].get(k) for k in ("ms", "scene", "unload_ms")} if isinstance(r["reply"], dict) else r["reply"])
        print(f"hero at {pos[:2]}, hp {s['hero']['health']}/{s['hero']['max_health']}, silk {s['hero']['silk']}, "
              f"crest {s['hero'].get('crest')}")
        ok &= check(abs(pos[0] - 78.0) < 1.0, "hero at the composed x")
        time.sleep(1.0)
        print("boss Control events since the load:", ctl.log[-4:])
        ok &= check(ctl.state == "Dormant", "Bone Beast present and Dormant")

        saved = link.rpc("savestate.save", name=a.out)
        print("saved:", {k: saved.get(k) for k in ("path", "scene", "pos", "hp", "silk", "bytes")})

        # Walk right into the trigger and watch the boss wake.
        t0 = time.monotonic()
        woke = emerged = None
        while time.monotonic() - t0 < 8.0:
            link.act(link.frame + 1, mask("right"), hold_frames=6)
            s = link.wait_state(lambda x: True, timeout_s=1.0, newer_than=link.frame)
            st = ctl.state
            if woke is None and st not in (None, "Dormant", "Init"):
                woke = (round(time.monotonic() - t0, 2), st, [round(v, 2) for v in s["hero"]["pos"][:2]])
                print("woke:", woke)
            if woke and st and st.startswith("Emerge Antic"):
                emerged = (round(time.monotonic() - t0, 2), st)
                break
            if woke:
                link.act(link.frame + 1, 0, hold_frames=1)  # stop walking once it wakes
        ok &= check(woke is not None, "walking right wakes Bone Beast")
        ok &= check(emerged is not None, f"it emerges within 8 s ({emerged})")

        if emerged:
            s = link.wait_state(lambda s: boss(s) is not None, timeout_s=5.0)
            b = boss(s)
            print("boss entity:", {k: b.get(k) for k in ("pos", "hp", "is_dead", "inv")},
                  [(m["name"], m["state"]) for m in b["fsms"]])
        print("Control log:", ctl.log)
        r = load(link, a.out)
        s = r["state"]
        time.sleep(1.0)
        ok &= check(abs(s["hero"]["pos"][0] - 78.0) < 1.0 and ctl.state == "Dormant",
                    f"{a.out} loads back to x {s['hero']['pos'][0]:.2f} with the boss {ctl.state}")
        if old is False:
            print("save suppression left ON on purpose (progress from the composed save must not reach the slot);"
                  " close the game without saving")
    finally:
        link.close()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
