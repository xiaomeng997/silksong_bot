"""Targeted down-slash trials against the Clapper's slam (task 1v1 T1, the person's experiment method 2026-10-11:
theory first, then live trials at chosen points and across the predicted boundary; forum.md 46).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.pogo_target --instance 0 --targets C:/ssbot/data/m2_pogo/target/t_i0.jsonl \
        [--savestate fo_cl_w7w] [--out C:/ssbot/data/m2_pogo/target/live]

A target (one line of --targets, made by ssbot.tools.pogo_theory targets): the jump's first frame tau_j counted from
the Clapper's Slam Antic entry (the first STATE whose Control state reads Slam Antic: k = 0), the hero's start x0 on
the floor in front of the Clapper (its facing at the antic entry, relative to its x then) and the path (pogo_slam
Path_: jump held h frames, the press a frames after the jump's first frame, the horizontal before / after the press
toward / none / away, the jump held again after the press), with the theory's prediction for it.

A trial: wait in front of the Clapper at x0 (re-approaching while it walks) for a Slam Antic (WAIT_S); from the antic
entry walk to x0 (frame exact: the hero stops dead; a target that cannot be reached by tau_j is skipped and logged)
and stand, then the path's masks frame by frame (each ACTION is sent for STATE frame + 2, the frame it lands on is
recorded), then SETTLE_F frames with no input. The savestate is reloaded before a trial when the hero has fewer than
MIN_HP masks (a probe's LethalBlock would hide a lethal hit) or the Clapper < 70 HP. Output: one recording (Recorder,
profile TRAIN) and <recording>/target_trials.jsonl (the target, the antic entry frame, the Clapper's x and facing
then, the hero's x at the jump frame, the frames each path mask was sent for, skipped / late flags).

Safety: a free training instance; save suppression and LethalBlock on; no invincibility.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ssbot.core.forum import WALL_L, WALL_R
from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.probes.combo_probe import Driver
from ssbot.probes.pogo_probe import CLAPPER, READY, clapper, control, hx

M_L, M_R = mask("left"), mask("right")
WAIT_S = 9.0
SETTLE_F = 40
MIN_HP = 5
WALK_U = 8.25 / 60          # the hero's walk per frame (stops dead)


def stop_requested() -> bool:
    return (Path(r"C:\ssbot\sandbox\STOP_AGENTS").exists() or Path(r"C:\ssbot\sandbox\pogo_target.stop").exists()
            or Path(r"C:\ssbot\sandbox\DEMO_SOON").exists())


def mirror(m: int) -> int:
    """Swap left and right (the canonical frame's 'toward' is left)."""
    lr = m & (M_L | M_R)
    out = m & ~(M_L | M_R)
    if lr & M_L:
        out |= M_R
    if lr & M_R:
        out |= M_L
    return out


class Target:
    def __init__(self, link: OracleLink, savestate: str):
        self.link = link
        self.savestate = savestate
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

    def step(self, m: int) -> dict:
        return self.d.step(m, ())

    def side_x(self, s: dict, x0: float) -> float | None:
        """The hero's x for x0 in front of the Clapper on her side (the other side when a wall is in the way)."""
        e = clapper(s)
        if e is None:
            return None
        cx = float(e["pos"][0])
        side = 1 if hx(s) >= cx else -1
        tx = cx + side * x0
        if not (WALL_L + 1.0 <= tx <= WALL_R - 1.0):
            tx = cx - side * x0
        return tx

    def walk_mask(self, s: dict, tx: float) -> int:
        """The walk mask for frame s.f + 2 toward tx: the hero's x then extrapolated from this frame's velocity (the
        two frames in flight already have their masks), none within half a walk step (she stops dead)."""
        vx = float((s["hero"].get("vel") or [0, 0])[0])
        dx = tx - (hx(s) + 2 * vx / 60)
        if abs(dx) <= WALK_U / 2 + 0.01:
            return 0
        return M_R if dx > 0 else M_L

    def walk_to(self, s: dict, tx: float, max_f: int, stop_on_antic: bool = False) -> tuple[dict, int]:
        for k in range(max_f):
            if stop_on_antic and control(clapper(s)) == "Slam Antic":
                return s, k
            m = self.walk_mask(s, tx)
            if m == 0 and abs(float((s["hero"].get("vel") or [0, 0])[0])) < 0.1:
                return self.step(0), k + 1
            s = self.step(m)
        return s, max_f

    def trial(self, t: dict) -> dict:
        s = self.step(0)
        e = clapper(s)
        hp = int(s["hero"].get("health") or 0)
        if e is None or hp < MIN_HP or (e.get("hp") or 0) < 70:
            s = self.load()
        x0 = float(t["x0"])
        wait_x0 = min(max(x0, 2.5), 7.0)
        tx = self.side_x(s, wait_x0)
        s, _ = self.walk_to(s, tx, 240)
        t0 = time.time()
        fa = None
        while time.time() - t0 < WAIT_S:
            e = clapper(s)
            st = control(e)
            if st == "Slam Antic":
                # the entry frame from the state's time (a re-approach walk may have run over it)
                tin = next((float(m.get("t") or 0.0) for m in e.get("fsms") or () if m.get("name") == "Control"), 0.0)
                fa = s["f"] - int(round(tin * 60))
                break
            # follow it frame by frame (the person, 2026-10-11 18:50: after a backstep the hero was out of Slam Range,
            # the Clapper went Far Range and jumped half the time): keep the test distance, chase a backstep at once
            m = 0
            if e is not None:
                tx = self.side_x(s, wait_x0)
                if st == "Evade Scuttle" or abs(abs(hx(s) - float(e["pos"][0])) - wait_x0) > 0.4:
                    m = self.walk_mask(s, tx)
            s = self.step(m)
        if fa is None:
            return {"skip": "no slam"}
        if s["f"] + 2 - fa > int(t["tau_j"]):
            return {"skip": "antic seen too late", "f_antic": fa, "k_seen": s["f"] - fa}
        e = clapper(s)
        cx = float(e["pos"][0])
        face = 1 if e.get("flipX") else -1          # flipX True: facing right (+x)
        # the hero must be on the facing side (the Clapper faced her at the entry)
        tx = cx + face * x0
        tau = int(t["tau_j"])
        masks = [int(m) for m in t["masks"]]
        if face == -1:
            masks = [mirror(m) for m in masks]
        sent = []
        # walk to x0 while the next sent frame (s.f + 2) is before the jump's first frame, then stand
        late = False
        while True:
            k_next = s["f"] + 2 - fa
            if k_next >= tau:
                break
            frames_left = tau - k_next
            m = self.walk_mask(s, tx)
            if m and abs(tx - hx(s)) > WALK_U * (frames_left + 2) + 0.05:
                late = True
            s = self.step(m)
        x_jump = None
        k_first = s["f"] + 2 - fa
        while True:
            k_next = s["f"] + 2 - fa
            i = k_next - tau
            if i >= len(masks):
                break
            m = masks[i] if i >= 0 else 0
            sent.append((k_next, i, m))
            if i == 0:
                x_jump = hx(s)
            s = self.step(m)
        for _ in range(SETTLE_F):
            s = self.step(0)
        return {"f_antic": fa, "cx": round(cx, 3), "face": face, "tx": round(tx, 3), "late": late,
                "k_first": k_first, "x_before_jump": None if x_jump is None else round(x_jump, 3),
                "f_jump": fa + tau, "f_press": fa + tau + int(t["a"]), "n_sent": len(sent),
                "gaps": sum(1 for a, b in zip(sent, sent[1:]) if b[0] - a[0] != 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--savestate", default="fo_cl_w7w")
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--start", type=int, default=0, help="first target line (a resumed run)")
    ap.add_argument("--out", default=r"C:\ssbot\data\m2_pogo\target\live")
    a = ap.parse_args(argv)
    from ssbot.record.recorder import Recorder
    targets = [json.loads(x) for x in a.targets.read_text("utf-8").splitlines() if x.strip()][a.start:]
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    rec = None
    try:
        link.rpc("guards.set", save_suppression=True, lethal_block="block")
        link.rpc("fsmtap.set", all=True)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"pogo_target_i{a.instance}_{a.targets.stem}_{a.start}",
                       config={"probe": "pogo_target", "targets": str(a.targets), "start": a.start,
                               "savestate": a.savestate}).start()
        log = (rec.path / "target_trials.jsonl").open("w", encoding="utf-8")
        pr = Target(link, a.savestate)
        pr.load()
        for n, t in enumerate(targets):
            if stop_requested():
                print("stop requested", flush=True)
                break
            try:
                info = pr.trial(t)
            except Exception as ex:  # noqa: BLE001
                info = {"error": repr(ex)}
                try:
                    pr.load()
                except Exception as ex2:  # noqa: BLE001
                    print("reload failed", ex2, flush=True)
                    break
            link.rpc("input.release", timeout_s=10)
            pr.d.collect()
            row = {"n": a.start + n, "target": {k: v for k, v in t.items() if k != "masks"}} | info
            log.write(json.dumps(row) + "\n")
            log.flush()
            print(json.dumps(row)[:300], flush=True)
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
