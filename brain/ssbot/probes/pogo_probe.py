"""Down slash against the Clapper (task 1v1 T1(b), forum.md 46): scripted Wanderer jumps + down slashes at the
Clapper's hammer during its slam and at its body, recorded for ssbot.tools.pogo_outcomes and the predictor's held-out
check (ssbot.combat.pogo_model).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.pogo_probe --instance 0 --savestate fo_cl_w7w --trials 60 \
        --seed 700000 [--out C:/ssbot/data/m2_pogo/live]

Each trial (one ACTION per STATE at frame + 2, as kin_excite): walk to a random distance d in front of the Clapper
(the side the hero is on; the other side when the wall leaves no room) and wait for a Slam Antic (its own choice; the
hero stays put, re-approaching after other moves) up to WAIT_S. kind "slam": from the antic's first frame, a jump at
a random delay, held for a random time, with no / towards / away horizontal input, and down + attack pressed at a
random delay after the jump (the presses span the antic's end, Slam 0 - 2 and the recover). kind "body" (no slam
within WAIT_S, or every BODY_EVERY-th trial with the Clapper idle / walking within 3.5 u): a jump towards it and the
down slash over its head. kind "air": the same jump and down slash with nothing near (the miss branch's data).
Then 70 frames with no input. The savestate is reloaded when the hero has <= 3 masks or the Clapper < 70 HP.
slash.dump is sampled on the down slash's frames (its damager polygon by facing). Output: one recording (Recorder,
profile TRAIN) and <recording>/pogo_trials.jsonl (one line per trial: kind, parameters, frames).

Safety: a free training instance; save suppression and LethalBlock on all the time; no invincibility (the hammer's
damage after a bounce is what is measured).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time

from ssbot.core.forum import WALL_L, WALL_R
from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.probes.combo_probe import Driver

M_L, M_R, M_D = mask("left"), mask("right"), mask("down")
M_J, M_A = mask("jump"), mask("attack")
CLAPPER = "Song Heavy Sentry"
WAIT_S = 7.0
BODY_EVERY = 4
SETTLE_F = 70
READY = ("Idle", "Walk", "Close Range", "Far Range", "Start Battle?", "Battle Idle")


def clapper(s: dict) -> dict | None:
    return next((e for e in s.get("ents") or () if e.get("type_key") == CLAPPER and not e.get("is_dead")
                 and (e.get("hp") or 0) > 0 and e.get("pos")), None)


def control(e: dict | None) -> str | None:
    for m in (e or {}).get("fsms") or ():
        if m.get("name") == "Control":
            return m.get("state")
    return None


def hx(s: dict) -> float:
    return float(s["hero"]["pos"][0])


def stop_requested() -> bool:
    from pathlib import Path
    return (Path(r"C:\ssbot\sandbox\STOP_AGENTS").exists() or Path(r"C:\ssbot\sandbox\pogo_probe.stop").exists()
            or Path(r"C:\ssbot\sandbox\DEMO_SOON").exists())


class Probe:
    def __init__(self, link: OracleLink, savestate: str, rng: random.Random):
        self.link = link
        self.savestate = savestate
        self.rng = rng
        self.d = Driver(link)

    def load(self) -> dict:
        self.link.rpc("input.release", timeout_s=10)
        self.link.rpc("savestate.load", timeout_s=60, name=self.savestate, timeout=50)
        t0 = time.time()
        while time.time() - t0 < 30:
            s = self.link.wait_state(newer_than=self.link.frame, timeout_s=3.0)
            e = clapper(s)
            if s.get("hero") and s["hero"].get("hero_accepting_input") and e is not None and control(e) in READY:
                return s
        raise RuntimeError("the Clapper never became ready")

    def step(self, m: int, dump: bool = False) -> dict:
        s = self.d.step(m, ())
        if dump:
            self.d.samples[-1]["_dump"] = self.link.rpc_async("slash.dump")
        return s

    def approach(self, dist: float, max_f: int = 240) -> dict:
        """Walk until the hero is dist in front of (on her side of) the Clapper."""
        s = self.step(0)
        for _ in range(max_f):
            e = clapper(s)
            if e is None:
                return s
            cx = float(e["pos"][0])
            side = 1 if hx(s) >= cx else -1
            tx = cx + side * dist
            if not (WALL_L + 1.0 <= tx <= WALL_R - 1.0):
                tx = cx - side * dist
            dx = tx - hx(s)
            if abs(dx) < 0.3:
                return self.step(0)
            s = self.step(M_R if dx > 0 else M_L)
        return s

    def air(self, s: dict, horiz: int, j_hold: int, a_delay: int, toward_x: float | None) -> dict:
        """Jump (held j_hold frames), down + attack a_delay frames after the jump press, then SETTLE_F frames.
        horiz: 0 none, 1 towards toward_x, -1 away from it."""
        def hmask(st):
            if horiz == 0 or toward_x is None:
                return 0
            sgn = 1 if toward_x >= hx(st) else -1
            return (M_R if sgn * horiz > 0 else M_L)
        f_jump = None
        f_press = None
        for k in range(a_delay + 14):
            m = hmask(s)
            if k < j_hold:
                m |= M_J
            if k == a_delay:
                m |= M_D | M_A
            elif a_delay < k <= a_delay + 2:
                m |= M_D
            s = self.step(m, dump=a_delay <= k <= a_delay + 12)
            if k == 0:
                f_jump = s["f"] + 2
            if k == a_delay:
                f_press = s["f"] + 2
        for _ in range(SETTLE_F):
            s = self.step(hmask(s) if horiz else 0)
        return {"f_jump": f_jump, "f_press": f_press, "s": s}

    def trial(self, n: int) -> dict:
        rng = self.rng
        s = self.step(0)
        e = clapper(s)
        hp = int(s["hero"].get("health") or 0)
        if e is None or hp <= 3 or (e.get("hp") or 0) < 70:
            s = self.load()
            e = clapper(s)
        dist = rng.uniform(2.0, 7.5)
        body = n % BODY_EVERY == BODY_EVERY - 1
        if body:
            dist = rng.uniform(1.5, 3.5)
        s = self.approach(dist)
        info = {"trial": n, "dist": round(dist, 2)}
        if not body:
            t0 = time.time()
            fa = None
            while time.time() - t0 < WAIT_S:
                s = self.step(0)
                e = clapper(s)
                st = control(e)
                if st == "Slam Antic":
                    fa = s["f"]
                    break
                if st in READY and abs(hx(s) - float(e["pos"][0])) > dist + 1.5:
                    s = self.approach(dist)
            if fa is not None:
                j0 = rng.randint(10, 46)
                for _ in range(j0):
                    s = self.step(0)
                horiz = rng.choice((0, 0, 1, -1))
                j_hold = rng.randint(3, 16)
                a_delay = rng.randint(5, 30)
                cx = float(clapper(s)["pos"][0]) if clapper(s) else None
                r = self.air(s, horiz, j_hold, a_delay, cx)
                return info | {"kind": "slam", "f_antic": fa, "j0": j0, "horiz": horiz, "j_hold": j_hold,
                               "a_delay": a_delay, "f_jump": r["f_jump"], "f_press": r["f_press"]}
            info["no_slam"] = True
        e = clapper(s)
        near = e is not None and abs(hx(s) - float(e["pos"][0])) <= 3.5 and control(e) in READY
        horiz = 1 if near else rng.choice((0, 1, -1))
        j_hold = rng.randint(6, 16)
        a_delay = rng.randint(8, 26)
        cx = float(e["pos"][0]) if e is not None else None
        if not near and cx is not None:       # far from it: jump away (nothing to hit)
            horiz = -1
        r = self.air(s, horiz, j_hold, a_delay, cx)
        return info | {"kind": "body" if near else "air", "horiz": horiz, "j_hold": j_hold, "a_delay": a_delay,
                       "f_jump": r["f_jump"], "f_press": r["f_press"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--savestate", default="fo_cl_w7w")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--seed", type=int, default=700000)
    ap.add_argument("--out", default=r"C:\ssbot\data\m2_pogo\live")
    a = ap.parse_args(argv)
    from ssbot.record.recorder import Recorder

    rng = random.Random(a.seed)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    rec = None
    try:
        link.rpc("guards.set", save_suppression=True, lethal_block="block")
        link.rpc("fsmtap.set", all=True)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"pogo_probe_s{a.seed}",
                       config={"probe": "pogo_probe", "seed": a.seed, "savestate": a.savestate}).start()
        log = (rec.path / "pogo_trials.jsonl").open("w", encoding="utf-8")
        pr = Probe(link, a.savestate, rng)
        pr.load()
        for n in range(a.trials):
            if stop_requested():
                print("stop requested", flush=True)
                break
            try:
                info = pr.trial(n)
            except Exception as ex:  # noqa: BLE001
                info = {"trial": n, "error": repr(ex)}
                try:
                    pr.load()
                except Exception as ex2:  # noqa: BLE001
                    print("reload failed", ex2, flush=True)
                    break
            link.rpc("input.release", timeout_s=10)
            samples = pr.d.collect()
            dumps = [{"f": r["f"], "dump": r.get("dump"), "hero": r.get("dump_hero")} for r in samples if "dump" in r]
            log.write(json.dumps(info | {"dumps": dumps}) + "\n")
            log.flush()
            print(json.dumps(info), flush=True)
        log.close()
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
            link.rpc("fsmtap.set", all=False)
        except Exception:  # noqa: BLE001
            pass
        if rec is not None:
            rec.close()
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
