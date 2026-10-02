"""Kinematics excitation probe (M2 W1, DESIGN §3.5.2): scripted button sequences in the Bell Beast arena before the
trigger, recorded for ssbot.tools.kin_fit / kin_check. Fills the gaps the combat data leaves: every jump hold length,
releases on the way up and down, turnarounds, attacks while running and jumping, down attacks from every height,
queued jumps before landing, Silkspear and Bind on the ground and in the air, and (with --hurt) damage knockback from
both sides on the ground and in the air.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 1 --detach
    ../scripts/uv.cmd run python -m ssbot.probes.kin_excite [--instance 0] [--seed 0] [--trials 300] [--hurt]
    ../scripts/uv.cmd run python -m ssbot.tools.kin_fit <recording> --dry-run
    ../scripts/uv.cmd run python -m ssbot.tools.kin_check <recording>

Each trial loads the savestate (bellbeast_arena: hero at x 78 on the floor y 3.5677, the boss Dormant, its trigger
at x ~87.5, the vines at x ~88), sets HP / silk / facing with randomize_start(seed), waits until Hornet accepts
input, then plays one primitive drawn from a seeded schedule, one ACTION per STATE (continuous control, target frame
+2, as ssbot.train.episode does), and releases everything for a settle period. Before a schedule is played, the
kinematics model rolls it out from the logged start state and the schedule is redrawn if the hero would leave
x in [70, 85.5] (the trigger must not fire) - the probe also exercises the model it feeds. The whole run is one
recording (ssbot.record.recorder.Recorder) plus <recording>/kin_trials.jsonl with each trial's frames and schedule.

Safety: needs a free training instance (it loads savestates and drives input); never run it while a data job owns
the instances. Save suppression is turned on before the first load and left on (the savestate carries progress the
sandbox slot must not get). --hurt hits Hornet through the main link's hurt.special RPC (kind "damage", 1 mask,
HazardType ENEMY, the given impact side: HeroController.TakeDamage, so the real hit-stop and recoil; TRAIN profile
only) with LethalBlock set to block; every trial reloads the savestate and randomize_start puts HP back to 5. The
plan of a hurt trial is rolled out with the hit on every frame the RPC can land on (HURT_SPAN around the requested
one) and the knockback envelope of each such hit (ssbot.knowledge.knockback, the conservative bound) must stay inside
X_SAFE too.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import threading
from dataclasses import asdict, dataclass, field

import numpy as np

from ssbot.ipc.framing import MsgType, mask
from ssbot.ipc.oracle_link import OracleLink

SAVESTATE = "bellbeast_arena"
SCENE = "Bone_05"
X_SAFE = (70.0, 85.5)
SETTLE_FRAMES = 45
HURT_SPAN = (-2, 6)     # frames around the requested one the hurt.special hit can land on (RPC on the main thread)

M_NONE = 0
M_L, M_R = mask("left"), mask("right")
M_J, M_A, M_D, M_U = mask("jump"), mask("attack"), mask("down"), mask("up")
M_Q, M_B = mask("quickcast"), mask("bind")


@dataclass
class Trial:
    kind: str
    params: dict
    masks: list[int]                         # one button mask per frame from the first action frame
    hurt: dict | None = None                 # {"frame": offset, "side": "left" | "right"}
    seed: int = 0
    f0: int | None = None
    f1: int | None = None
    start: dict = field(default_factory=dict)
    redraws: int = 0


def _seg(m: int, n: int) -> list[int]:
    return [m] * max(int(n), 0)


def draw(rng: random.Random, hurt: bool) -> Trial:
    """One primitive with random parameters (frames are rendered frames at 60 Hz)."""
    d = rng.choice((M_L, M_R))
    kind = rng.choice(("move", "jump_hold", "jump_move", "jump_release_fall", "turnaround", "attack_run",
                       "attack_air", "down_attack", "jump_queue", "silkspear", "bind", "up_attack")
                      + (("hurt",) if hurt else ()))
    p: dict = {"dir": "left" if d == M_L else "right"}
    m: list[int] = []
    h = None
    if kind == "move":
        p["n"] = rng.randint(1, 40)
        m = _seg(d, p["n"])
    elif kind in ("jump_hold", "jump_move"):
        p["k"] = rng.randint(1, 24)
        mv = d if kind == "jump_move" else 0
        p["lead"] = rng.randint(0, 12) if mv else 0
        m = _seg(mv, p["lead"]) + _seg(M_J | mv, p["k"]) + _seg(mv, rng.randint(10, 40))
    elif kind == "jump_release_fall":
        p["k"] = rng.randint(4, 24)
        p["regrab"] = rng.randint(0, 20)                       # hold jump again while falling: air hang
        m = _seg(M_J, p["k"]) + _seg(0, p["regrab"]) + _seg(M_J | d, rng.randint(10, 30))
    elif kind == "turnaround":
        p["n1"], p["n2"] = rng.randint(3, 25), rng.randint(3, 25)
        o = M_R if d == M_L else M_L
        m = _seg(d, p["n1"]) + _seg(o, p["n2"])
    elif kind == "attack_run":
        p["n"], p["at"] = rng.randint(10, 35), rng.randint(0, 8)
        m = _seg(d, p["at"]) + _seg(d | M_A, 3) + _seg(d, p["n"])
    elif kind in ("attack_air", "up_attack"):
        p["k"], p["at"] = rng.randint(4, 24), rng.randint(2, 30)
        att = M_A | (M_U if kind == "up_attack" else 0)
        mv = d if rng.random() < 0.5 else 0
        m = _seg(M_J | mv, p["k"]) + _seg(mv, p["at"]) + _seg(att | mv, 3) + _seg(mv, 30)
    elif kind == "down_attack":
        p["k"], p["at"] = rng.randint(4, 24), rng.randint(2, 35)
        mv = d if rng.random() < 0.5 else 0
        m = _seg(M_J | mv, p["k"]) + _seg(mv, p["at"]) + _seg(M_D | M_A | mv, 3) + _seg(M_D | mv, 20) + _seg(0, 20)
    elif kind == "jump_queue":
        p["k"], p["early"] = rng.randint(1, 24), rng.randint(0, 6)
        mv = d if rng.random() < 0.5 else 0
        m = _seg(M_J | mv, p["k"]) + _seg(mv, 20)              # the re-press timing is patched in plan()
        p["mv"] = mv
    elif kind == "silkspear":
        p["air"] = rng.random() < 0.5
        p["k"] = rng.randint(4, 12) if p["air"] else 0
        mv = d if rng.random() < 0.5 else 0
        m = _seg(M_J | mv, p["k"]) + _seg(M_Q | mv, 3) + _seg(mv, 70)
    elif kind == "bind":
        p["air"] = rng.random() < 0.5
        p["k"] = rng.randint(4, 12) if p["air"] else 0
        m = _seg(M_J, p["k"]) + _seg(M_B, 3) + _seg(0, 100)
    elif kind == "hurt":
        p["air"] = rng.random() < 0.5
        p["k"] = rng.randint(4, 16) if p["air"] else 0
        p["side"] = rng.choice(("left", "right"))
        m = _seg(M_J, p["k"]) + _seg(d if rng.random() < 0.5 else 0, 60)
        h = {"frame": p["k"] + rng.randint(0, 6), "side": p["side"]}
    return Trial(kind, p, m, h)


def safe(S: np.ndarray, t: Trial, params, terrain) -> bool:
    """The trial keeps the hero (collider centre) inside X_SAFE: its rollout with every timing variant and, for a hurt
    trial, the rollouts (every timing variant) with the hit on each frame of HURT_SPAN plus the knockback envelope of
    each such hit."""
    from ssbot.knowledge import kinematics as km
    from ssbot.knowledge.knockback import knockback_boxes
    masks = np.array(t.masks + _seg(0, SETTLE_FRAMES), dtype=np.int64)[None]
    T = masks.shape[1]
    hw = params.half_width

    def ok(x0: float, x1: float) -> bool:
        return bool(x0 + hw >= X_SAFE[0] and x1 - hw <= X_SAFE[1])

    r = km.rollout(S, masks, params, terrain, variants="bounds")
    if not ok(r.bound[0, :, 0].min(), r.bound[0, :, 2].max()):
        return False
    if not t.hurt:
        return True
    bit = km.EV_HURT_L if t.hurt["side"] == "left" else km.EV_HURT_R
    frames = [f for f in range(t.hurt["frame"] + HURT_SPAN[0], t.hurt["frame"] + HURT_SPAN[1] + 1) if 0 <= f < T]
    ev = np.zeros((len(frames), T), dtype=np.int64)
    for j, f in enumerate(frames):
        ev[j, f] = bit
    rh = km.rollout(S, np.repeat(masks, len(frames), axis=0), params, terrain, events=ev, variants="bounds")
    if not ok(rh.bound[..., 0].min(), rh.bound[..., 2].max()):         # after control returns too, every lane
        return False
    hit_boxes = np.stack([r.bound[0, f + 1] for f in frames])     # the variants' hull: a superset of each lane
    swept, _, _ = knockback_boxes(hit_boxes, t.hurt["side"], params, terrain)
    return ok(swept[:, 0].min(), swept[:, 2].max())


def plan(rng: random.Random, state: dict, model, hurt: bool, tries: int = 20) -> Trial:
    """Draw trials until the model keeps the hero inside X_SAFE (and patch jump-queue re-presses to land timing)."""
    from ssbot.knowledge import kinematics as km
    params, terrain = model
    tr = km.Trace.from_states([state], params, mask_source="act")
    S = km.estimate_state(tr, [0], params, terrain=terrain)
    for i in range(tries):
        t = draw(rng, hurt)
        t.redraws = i
        if t.kind == "jump_queue":
            masks = np.array(t.masks + _seg(0, SETTLE_FRAMES), dtype=np.int64)
            r = km.rollout(S, masks[None], params, terrain)
            land = np.flatnonzero((r.flags[0, 1:] & km.F_GROUND) != 0)
            land = land[land > t.params["k"]]
            if len(land):
                at = max(int(land[0]) - t.params["early"], t.params["k"] + 1)
                t.masks[at:at + 6] = [M_J | t.params["mv"]] * 6
        if safe(S, t, params, terrain):
            return t
    return Trial("rest", {}, _seg(0, 30), None, redraws=tries)


def run_trial(link: OracleLink, t: Trial) -> Trial:
    masks = t.masks + _seg(0, SETTLE_FRAMES)
    last = link.frame
    t0 = None
    i = 0
    while i < len(masks):
        s = link.wait_state(newer_than=last, timeout_s=2.0)
        last = s["f"]
        if t0 is None:
            t0 = last + 2
            t.f0 = t0
        k = last + 2 - t0
        if 0 <= k < len(masks):
            link.act(last + 2, masks[k], hold_frames=0)
            i = k + 1
        if t.hurt and k == t.hurt["frame"] and "landed" not in t.hurt:
            res = link.rpc("hurt.special", kind="damage", amount=1, hazard="ENEMY", side=t.hurt["side"])
            t.hurt["landed"] = res.get("frame")
    link.act(link.frame + 2, 0, hold_frames=0)
    t.f1 = link.frame
    return t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--savestate", default=SAVESTATE)
    ap.add_argument("--out", default=r"C:\ssbot\data\runs\m2\kin_excite")
    ap.add_argument("--hurt", action="store_true", help="include damage knockback trials (hurt.special RPC)")
    a = ap.parse_args(argv)

    from ssbot.knowledge.kinematics import HeroParams, Terrain2D
    from ssbot.probes.common import load_slot, stand_up
    from ssbot.record.recorder import Recorder

    params = HeroParams.load()
    rng = random.Random(a.seed)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    rec = None
    try:
        load_slot(link, 1)
        stand_up(link)
        link.rpc("guards.set", save_suppression=True)
        if a.hurt:
            link.rpc("guards.set", lethal_block="block")
        terrains = TerrainTap(link)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"kin_excite_s{a.seed}",
                       config={"probe": "kin_excite", "seed": a.seed, "trials": a.trials, "hurt": a.hurt}).start()
        log = (rec.path / "kin_trials.jsonl").open("w", encoding="utf-8")
        terrain = None
        for n in range(a.trials):
            link.rpc("savestate.load", timeout_s=40, name=a.savestate, timeout=30)
            s = link.wait_state(lambda s: (s.get("game") or {}).get("scene") == SCENE and s["hero"]
                                and s["hero"]["hero_accepting_input"], timeout_s=20)
            link.rpc("randomize_start", timeout_s=30, seed=a.seed * 100000 + n, hp=[5, 5], silk=[4, 9],
                     facing="random", wait_frames=[0, 10])
            s = link.wait_state(lambda s: s["hero"] and s["hero"]["hero_accepting_input"], timeout_s=10)
            if terrain is None:
                t_msg = terrains.wait(SCENE)
                terrain = Terrain2D.from_message(t_msg, params.scene(SCENE)) if t_msg else Terrain2D.empty()
            t = plan(rng, s, (params, terrain), a.hurt)
            t.seed = a.seed
            t.start = {"pos": s["hero"]["pos"][:2], "silk": s["hero"]["silk"], "facing": s["hero"]["facing"]}
            run_trial(link, t)
            log.write(json.dumps(asdict(t)) + "\n")
            log.flush()
            print(f"{n:4d} {t.kind:18s} {t.params} frames {t.f0}-{t.f1}", flush=True)
        log.close()
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
        except Exception:  # noqa: BLE001 - best effort on the way out
            pass
        if rec is not None:
            print("recording:", rec.close().get("path", rec.path))
        link.close()
    return 0


class TerrainTap:
    """The latest TERRAIN message per scene from the link (sent once a room has finished entering)."""

    def __init__(self, link: OracleLink):
        self.cv = threading.Condition()
        self.by_scene: dict = {}
        link.subscribe_raw(self._on_raw)

    def _on_raw(self, msg_type: int, raw: bytes) -> None:
        if msg_type != MsgType.TERRAIN:
            return
        from ssbot.oracle.messages import split_frame, unpack
        msg = unpack(split_frame(raw)[2])
        with self.cv:
            self.by_scene[msg.get("scene_raw")] = msg
            self.cv.notify_all()

    def wait(self, scene: str, timeout_s: float = 15.0) -> dict | None:
        with self.cv:
            self.cv.wait_for(lambda: scene in self.by_scene, timeout_s)
            return self.by_scene.get(scene)


if __name__ == "__main__":
    sys.exit(main())
