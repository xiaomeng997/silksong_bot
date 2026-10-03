"""Forum-loadout excitation probe (M2 W8; DESIGN §3.5.2): scripted button sequences for the movement the Forum plan
needs (wall slide, wall cling with Ascendant's Grip, wall jump, attacks off the wall, Drifter's Cloak glide, Swift
Step dash and the sprint after it) and the Reaper crest's swings, recorded for kin_check / kin_fit and, with
--attack-frames, the swings' damage colliders sampled every frame (slash.dump) for tools/attack_table_build --live.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.kin_excite_forum --instance 3 --setup kn_scout_p2_s2 \
        --save kn_forum_room                   # once: Reaper + Wallcling on the room's savestate, saved by the game
    ../scripts/uv.cmd run python -m ssbot.probes.kin_excite_forum --instance 3 --savestate kn_forum_room \
        --wall-x 61.5 --x-safe 50 75 --seed 98000 --trials 200 [--attack-frames 60]

Setup: the room savestate (a quiet room with a tall wall; probes/room_scout), crest.equip Reaper (unlock), then
abilities.grant combat with the tool "Wallcling" (Gameplay.WallClingTool, Ascendant's Grip; unlock_slots), and the
result is saved with savestate.save. The room savestates of the community set at High Halls time have Swift Step,
Cling Grip, Drifter's Cloak and Clawline and neither Faydown Cloak (double jump) nor Silk Soar, as the Forum plan
has it (the setup refuses a state with either of the two).

Each trial loads the savestate, sets HP / silk / facing (randomize_start, seeded), waits until Hornet takes input
and plays one primitive from the seeded schedule, one ACTION per STATE (target frame +2, as kin_excite), then
releases everything for a settle period. Primitives (d = towards the wall): wall_hold (run, jump into the wall,
hold towards it for a while: slide then cling, release: slide, then drop / re-hold / down), wall_jump (the same,
then a jump with no direction, away or back), wall_attack (side = wall slash, up, down off the wall), glide (jump,
release, press again and hold, steering), dash (on the ground or in the air, tap or hold, with or without a
direction), reaper_attack (side / alt / up / down on the ground and in the air). A plan is rolled out from the
logged start with the Forum parameters and redrawn when the hero would leave --x-safe (the model is what this probe
measures, so this only keeps her in the room). Output: one recording plus <recording>/kin_trials.jsonl, and with
--attack-frames <recording>/attack_frames.jsonl (one line per sampled frame and enabled damager).

Safety: a free training instance only (it loads savestates and drives input); save suppression on all the time.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import asdict

import numpy as np

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.probes.kin_excite import TerrainTap, Trial, _seg, run_trial

SETTLE_FRAMES = 40
M_L, M_R = mask("left"), mask("right")
M_J, M_A, M_D, M_U, M_DASH = mask("jump"), mask("attack"), mask("down"), mask("up"), mask("dash")
FORUM_ABILITIES = "walljump,wallcling,dash,brolly,reaper_down,wallslash_slowdown,hard_landing"
REAPER_PARAMS = {"attack_cooldown": 0.5, "attack_recovery": 0.3, "attack_duration": 0.35}


def forum_params():
    """The Hunter fit with the Forum loadout switched on and the Reaper's attack timers (crests.json "Reaper"): the
    starting point kin_fit refines."""
    from ssbot.knowledge import kinematics as km
    p = km.HeroParams.load()
    ab = 0
    for name in FORUM_ABILITIES.split(","):
        ab |= next(b for b, n in km.ABILITY_NAMES.items() if n == name)
    d = p.to_json() | {"abilities": ab, "crest": "Reaper"} | REAPER_PARAMS
    return km.HeroParams.from_json(d)


KINDS = ("wall_hold", "wall_hold", "wall_jump", "wall_jump", "wall_attack", "wall_scramble", "glide", "glide",
         "dash", "dash", "reaper_attack")


def draw(rng: random.Random, d: int, dist: float = 4.0, kinds: tuple = KINDS) -> Trial:
    """One primitive; d = +-1 the direction of the wall from the start, dist its distance (the wall primitives
    run most of the way first: at 8.25 u/s, stopping 0.5-3 u short)."""
    md = M_R if d > 0 else M_L
    mo = M_L if d > 0 else M_R
    kind = rng.choice(kinds)
    p: dict = {"d": d}
    m: list[int] = []
    run = rng.randint(0, 60)
    if kind in ("wall_hold", "wall_jump", "wall_attack", "wall_scramble"):
        run = max(0, int((dist - rng.uniform(0.5, 3.0)) / 8.25 * 60))
    p["run"] = run
    if kind == "wall_scramble":
        # the Wall Scramble FSM (dash while sliding and holding towards the wall: a climb, not in the model yet):
        # recorded so its velocity profile can be measured; repeats after the dash is released and pressed again
        k, h, s = rng.randint(4, 24), rng.randint(5, 40), rng.randint(3, 30)
        rep = rng.randint(0, 2)
        p.update(k=k, h=h, s=s, rep=rep)
        m = _seg(md, run) + _seg(M_J | md, k) + _seg(md, h)
        for _ in range(rep + 1):
            m += _seg(M_DASH | md, s) + _seg(md, rng.randint(18, 30))
        m += _seg(0, rng.randint(0, 30))
    elif kind in ("wall_hold", "wall_jump", "wall_attack"):
        k = rng.randint(4, 24)
        h = rng.randint(5, 120)
        p.update(k=k, h=h)
        m = _seg(md, run) + _seg(M_J | md, k) + _seg(md, h)
        if kind == "wall_hold":
            r = rng.randint(0, 60)
            end = rng.choice(("none", "rehold", "down", "away"))
            p.update(r=r, end=end)
            m += _seg(0, r)
            m += {"none": [], "rehold": _seg(md, rng.randint(5, 60)), "down": _seg(M_D, 4),
                  "away": _seg(mo, rng.randint(2, 10))}[end]
        elif kind == "wall_jump":
            j = rng.randint(1, 20)
            dirn = rng.choice((0, -d, d))
            mv = 0 if dirn == 0 else (md if dirn == d else mo)
            p.update(j=j, dir=dirn)
            m += _seg(M_J | mv, j) + _seg(mv, rng.randint(10, 40))
        else:
            att = rng.choice(("side", "up", "down"))
            hold = rng.random() < 0.6
            p.update(att=att, hold=hold)
            b = M_A | (M_U if att == "up" else M_D if att == "down" else 0) | (md if hold else 0)
            m += _seg(b, 3) + _seg(md if hold else 0, rng.randint(20, 60))
    elif kind == "glide":
        k, a = rng.randint(4, 20), rng.randint(2, 30)
        g = rng.randint(5, 90)
        steer = rng.choice(("none", "d", "o", "switch"))
        p.update(k=k, a=a, g=g, steer=steer)
        m = _seg(md if rng.random() < 0.5 else 0, run) + _seg(M_J, k) + _seg(0, a)
        for i in range(g):
            s = {"none": 0, "d": md, "o": mo, "switch": md if (i // 15) % 2 == 0 else mo}[steer]
            m.append(M_J | s)
        m += _seg(0, rng.randint(0, 30))
    elif kind == "dash":
        air = rng.random() < 0.5
        k = rng.randint(4, 16) if air else 0
        hold = rng.choice((1, 2, 3, rng.randint(4, 40)))
        dirn = rng.choice((0, d, -d))
        mv = 0 if dirn == 0 else (md if dirn == d else mo)
        p.update(air=air, k=k, hold=hold, dir=dirn)
        m = _seg(md if rng.random() < 0.3 else 0, run // 3) + _seg(M_J, k) + _seg(M_DASH | mv, hold) + _seg(mv, 20)
    else:
        air = rng.random() < 0.6
        k = rng.randint(4, 20) if air else 0
        att = rng.choice(("side", "side", "up", "down"))
        n = rng.choice((1, 1, 2))
        at = rng.randint(0, 20)
        p.update(air=air, k=k, att=att, n=n, at=at)
        b = M_A | (M_U if att == "up" else M_D if att == "down" else 0)
        m = _seg(M_J, k) + _seg(0, at)
        for _ in range(n):
            m += _seg(b, 3) + _seg(0, 28)
    return Trial(kind, p, m, None)


def safe(S: np.ndarray, t: Trial, params, terrain, x_safe) -> bool:
    from ssbot.knowledge import kinematics as km
    masks = np.array(t.masks + _seg(0, SETTLE_FRAMES), dtype=np.int64)[None]
    r = km.rollout(S, masks, params, terrain)
    xs = r.box[0, :, [0, 2]]
    return bool(xs.min() >= x_safe[0] and xs.max() <= x_safe[1])


def plan(rng: random.Random, state: dict, model, d: int, x_safe, dist: float = 4.0, kinds: tuple = KINDS,
         tries: int = 20) -> Trial:
    from ssbot.knowledge import kinematics as km
    params, terrain = model
    tr = km.Trace.from_states([state], params, mask_source="act")
    S = km.estimate_state(tr, [0], params, terrain=terrain)
    for i in range(tries):
        t = draw(rng, d, dist, kinds)
        t.redraws = i
        if safe(S, t, params, terrain, x_safe):
            return t
    return Trial("rest", {}, _seg(0, 30), None, redraws=tries)


def setup(link: OracleLink, room: str, save_as: str) -> dict:
    link.rpc("savestate.load", timeout_s=60, name=room, timeout=50)
    link.wait_state(lambda s: s.get("hero") and s["hero"].get("hero_accepting_input"), timeout_s=30)
    time.sleep(1.0)
    lst = link.rpc("abilities.list", timeout_s=20)
    fl = lst["flags"]
    if fl.get("hasDoubleJump") or fl.get("hasSuperJump"):
        raise SystemExit(f"{room}: has the double jump or Silk Soar, not the Forum loadout: {fl}")
    crest = link.rpc("crest.equip", timeout_s=20, name="Reaper", unlock=True)
    grant = link.rpc("abilities.grant", timeout_s=20, set="combat", tools=["Wallcling"], skill="Silk Spear",
                     unlock_slots=True)
    time.sleep(0.5)
    lst = link.rpc("abilities.list", timeout_s=20)
    wc = [t for t in lst["tools"] if t["name"] == "Wallcling"]
    if lst["crest"] != "Reaper" or not wc or not wc[0]["equipped"]:
        raise SystemExit(f"setup failed: crest {lst['crest']}, Wallcling {wc}, grant {grant}")
    saved = link.rpc("savestate.save", timeout_s=60, name=save_as)
    return {"crest": crest, "grant_changed": grant.get("changed"), "flags": lst["flags"], "slots": lst["slots"],
            "saved": saved}


def setup_bb(link: OracleLink, save_as: str = "kn_bb_reaper") -> dict:
    """bellbeast_arena with the Reaper crest and Silk Spear in a Reaper skill slot (the encounter's intro cuts the
    vines with it): train.encounters.BELL_BEAST_REAPER."""
    link.rpc("savestate.load", timeout_s=60, name="bellbeast_arena", timeout=50)
    link.wait_state(lambda s: s.get("hero") and s["hero"].get("hero_accepting_input"), timeout_s=30)
    time.sleep(1.0)
    crest = link.rpc("crest.equip", timeout_s=20, name="Reaper", unlock=True)
    grant = link.rpc("abilities.grant", timeout_s=20, set="combat", tools=[], skill="Silk Spear", unlock_slots=True)
    time.sleep(0.5)
    lst = link.rpc("abilities.list", timeout_s=20)
    spear = [s for s in lst["skills"] if s["tool"] == "Silk Spear"]
    if lst["crest"] != "Reaper" or not spear or not spear[0]["equipped"]:
        raise SystemExit(f"setup failed: crest {lst['crest']}, Silk Spear {spear}, grant {grant}")
    saved = link.rpc("savestate.save", timeout_s=60, name=save_as)
    return {"crest": crest, "grant_changed": grant.get("changed"), "bindings": lst.get("bindings"), "saved": saved}


def sample_attack(link: OracleLink, t: Trial, out, frames: int = 26) -> None:
    """Play an attack trial while sampling slash.dump every frame from the press: one line per (frame, slot) with an
    enabled damager."""
    masks = t.masks + _seg(0, SETTLE_FRAMES)
    press = next(i for i, m in enumerate(masks) if m & M_A)
    last = link.frame
    t0 = None
    i = 0
    pending: list = []
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
        if t0 + press <= last <= t0 + press + frames:
            pending.append(link.rpc_async("slash.dump"))
    link.act(link.frame + 2, 0, hold_frames=0)
    t.f1 = link.frame
    f_press = t0 + press
    for fut in pending:
        try:
            r = fut.result(timeout=5)
        except Exception:  # noqa: BLE001
            continue
        for a in r.get("attacks") or ():
            dms = [{"path": dm["path"], "enabled": any(c.get("enabled") for c in dm["colliders"]) and dm["enabled"],
                    "polys": [shp["v"] for c in dm["colliders"] for shp in (c.get("shapes_swing") or c["shapes"])]}
                   for dm in a.get("damagers") or ()]
            if any(d["enabled"] for d in dms):
                out.write(json.dumps({"slot": a["slot"], "k": r["frame"] - f_press, "f": r["frame"],
                                      "trial": t.kind, "params": t.params, "hero": r["hero"],
                                      "damagers": dms}) + "\n")
    out.flush()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=3)
    ap.add_argument("--setup", default=None, help="room savestate to build --save from (Reaper + Wallcling)")
    ap.add_argument("--save", default=None)
    ap.add_argument("--setup-bb", action="store_true", help="build kn_bb_reaper (Bell Beast arena, Reaper crest)")
    ap.add_argument("--savestate", default=None)
    ap.add_argument("--wall-x", type=float, default=None)
    ap.add_argument("--x-safe", type=float, nargs=2, default=None)
    ap.add_argument("--seed", type=int, default=98000)
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--attack-frames", type=int, default=0, help="extra attack trials sampled with slash.dump")
    ap.add_argument("--kinds", default="", help="comma-separated primitives (default: all, weighted)")
    ap.add_argument("--random-dir", action="store_true", help="each trial's direction at random (no wall)")
    ap.add_argument("--out", default=r"C:\ssbot\data\runs\m2\kn_excite_forum")
    a = ap.parse_args(argv)

    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.probes.common import load_slot
    from ssbot.record.recorder import Recorder

    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    rec = None
    try:
        load_slot(link, 1)
        link.rpc("guards.set", save_suppression=True)
        if a.setup_bb:
            print(json.dumps(setup_bb(link), default=str)[:3000])
            return 0
        if a.setup:
            print(json.dumps(setup(link, a.setup, a.save), default=str)[:3000])
            return 0
        params = forum_params()
        rng = random.Random(a.seed)
        terrains = TerrainTap(link)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"kn_excite_forum_s{a.seed}",
                       config={"probe": "kin_excite_forum", "seed": a.seed, "trials": a.trials,
                               "savestate": a.savestate, "wall_x": a.wall_x, "x_safe": a.x_safe,
                               "attack_frames": a.attack_frames}).start()
        log = (rec.path / "kin_trials.jsonl").open("w", encoding="utf-8")
        af = (rec.path / "attack_frames.jsonl").open("w", encoding="utf-8") if a.attack_frames else None
        terrain = None
        n_total = a.trials + a.attack_frames
        kinds = tuple(k.strip() for k in a.kinds.split(",") if k.strip()) or KINDS
        for n in range(n_total):
            link.rpc("savestate.load", timeout_s=60, name=a.savestate, timeout=50)
            s = link.wait_state(lambda s: s.get("hero") and s["hero"].get("hero_accepting_input"), timeout_s=30)
            scene = (s.get("game") or {}).get("scene")
            link.rpc("randomize_start", timeout_s=30, seed=a.seed * 1000 + n, hp=[5, 5], silk=[4, 9],
                     facing="random", wait_frames=[0, 10])
            s = link.wait_state(lambda s: s["hero"] and s["hero"]["hero_accepting_input"], timeout_s=10)
            if terrain is None:
                t_msg = terrains.wait(scene)
                terrain = Terrain2D.from_message(t_msg) if t_msg else Terrain2D.empty()
            x0 = float(s["hero"]["pos"][0])
            d = 1 if (a.wall_x if a.wall_x is not None else x0 + 1) > x0 else -1
            if a.random_dir:
                d = rng.choice((-1, 1))
            dist = abs(a.wall_x - x0) - 0.265 if a.wall_x is not None else 4.0
            x_safe = tuple(a.x_safe) if a.x_safe else (x0 - 30, x0 + 30)
            if n >= a.trials:                # attack-frame trials: Reaper swings only
                t = draw(rng, d, dist)
                while t.kind not in ("reaper_attack", "wall_attack"):
                    t = draw(rng, d, dist)
            else:
                t = plan(rng, s, (params, terrain), d, x_safe, dist, kinds)
            t.seed = a.seed
            t.start = {"pos": s["hero"]["pos"][:2], "silk": s["hero"]["silk"], "facing": s["hero"]["facing"]}
            if n >= a.trials:
                sample_attack(link, t, af)
                t.params["sampled"] = True
            else:
                run_trial(link, t)
            log.write(json.dumps(asdict(t)) + "\n")
            log.flush()
            print(f"{n:4d} {t.kind:14s} {t.params} frames {t.f0}-{t.f1}", flush=True)
        log.close()
        if af:
            af.close()
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
        except Exception:  # noqa: BLE001
            pass
        if rec is not None:
            print("recording:", rec.close().get("path", rec.path))
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
