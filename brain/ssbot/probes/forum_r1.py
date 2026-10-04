"""Forum plan R1 in-game probes (docs/plans/forum_planner_plan.md §5 R1; facts: docs/facts/1.0.30000/forum.md, R1
section). Training copy, oracle view, savestates prefixed fo_r1_.

  midsave   load fo_A, start the battle, optionally skip to --wave, savestate.save fo_r1_mid, load it again and watch
            --seconds: does the battle (room.battles) and its wave come back, or does the room start over?
  skip      load fo_A, start the battle, skip_to_wave(--wave) (ssbot.train.wave_start), report timing and the
            verify_wave_start check; --repeat N times with seeds from --seed.
  climb     load fo_A, start the battle, climb the left wall to the top with hold-toward-wall + dash (Wall
            Scramble, ssbot.train.climb), --repeat attempts (back down and walk away between them); success rate.

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.forum_r1 skip --instance 2 --wave 3
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

from ssbot.ipc.oracle_link import OracleError, OracleLink

OUT = Path(r"C:\ssbot\sandbox\forum_r1")


def connect(instance: int) -> OracleLink:
    from ssbot.probes.common import load_slot, stand_up
    from ssbot.train.episode import unpause
    link = OracleLink(instance=instance, connect_timeout_s=120)
    s = link.wait_state(lambda s: s.get("game") is not None, timeout_s=60)
    if (s.get("game") or {}).get("paused") and (s.get("game") or {}).get("scene"):
        unpause(link)       # left paused by the brain-lost watchdog (a client that went away while driving)
    load_slot(link, 1)
    stand_up(link)
    if not link.rpc("guards.set", timeout_s=30, save_suppression=True)["save_suppression"]:
        raise SystemExit("save suppression could not be turned on")
    return link


def start_battle(link: OracleLink, enc, tap, seed: int, savestate: str | None = None) -> dict:
    from ssbot.train.encounters import Ctx
    from ssbot.train.episode import wait_settled
    link.rpc("savestate.load", timeout_s=60, name=savestate or enc.savestate, timeout=50)
    tap.reset()
    wait_settled(link, enc.scene, timeout_s=40)
    link.rpc("randomize_start", timeout_s=30, seed=seed, wait_frames=[0, 5])
    ctx = Ctx(link=link, tap=tap)
    enc.intro(ctx)
    return {"intro": ctx.log, "wake": tap.wake_frame}


def battles(s: dict) -> list:
    return [{k: b.get(k) for k in ("name", "wave", "started", "completed", "enemies", "to_next")}
            for b in (s.get("room") or {}).get("battles") or ()]


def watch(link: OracleLink, seconds: float, every_s: float = 1.0) -> list:
    from ssbot.train.gauntlet import live_enemies
    rows = []
    t_end = time.monotonic() + seconds
    nxt = 0.0
    last = link.frame
    while time.monotonic() < t_end:
        s = link.wait_state(newer_than=last, timeout_s=3.0)
        last = s["f"]
        link.act(last + 2, 0, hold_frames=0)
        if time.monotonic() >= nxt:
            nxt = time.monotonic() + every_s
            h = s.get("hero") or {}
            rows.append({"f": s["f"], "scene": (s.get("game") or {}).get("scene"), "battles": battles(s),
                         "in_play": sorted(f"{e.get('type_key')}@{e['pos'][0]:.1f},{e['pos'][1]:.1f}"
                                           for e in live_enemies(s)),
                         "hero": [round(v, 2) for v in (h.get("pos") or ())[:2]], "input": h.get("hero_accepting_input")})
    return rows


def midsave(link: OracleLink, a) -> dict:
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.episode import make_tap, wait_settled
    from ssbot.train.wave_start import skip_to_wave
    enc = ENCOUNTERS["Forum_A"]
    tap = make_tap(link, enc)
    out: dict = {"start": start_battle(link, enc, tap, a.seed)}
    if a.wave > 0:
        out["skip"] = skip_to_wave(link, enc, a.wave, a.instance, timeout_s=a.timeout, method=a.method)
    out["hero_keys"] = sorted((link.state or {}).get("hero") or {})
    out["before_save"] = watch(link, 2.0)
    link.rpc("input.release", timeout_s=10)       # no continuous control while the save runs (brain-lost watchdog)
    out["save"] = link.rpc("savestate.save", timeout_s=30, name="fo_r1_mid")
    link.rpc("savestate.load", timeout_s=60, name="fo_r1_mid", timeout=50)
    wait_settled(link, enc.scene, timeout_s=40)
    out["after_load"] = watch(link, a.seconds)
    return out


def skip(link: OracleLink, a) -> dict:
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.episode import make_tap
    from ssbot.train.wave_start import skip_to_wave
    enc = ENCOUNTERS["Forum_A"]
    tap = make_tap(link, enc)
    runs = []
    for k in range(a.repeat):
        seed = a.seed + k
        r: dict = {"seed": seed}
        try:
            r["start"] = start_battle(link, enc, tap, seed)
            r["skip"] = skip_to_wave(link, enc, a.wave, a.instance, timeout_s=a.timeout, method=a.method)
            r["after"] = watch(link, a.seconds)
        except (RuntimeError, TimeoutError, OracleError) as e:
            r["error"] = f"{type(e).__name__}: {e}"
        runs.append(r)
        sk = r.get("skip") or {}
        print(f"seed {seed}: {sk.get('method')} real {sk.get('real_s')} s game {sk.get('game_s')} s "
              f"verify {json.dumps(sk.get('verify'))[:400]} {r.get('error') or ''}", flush=True)
    return {"wave": a.wave, "runs": runs}


def states(link: OracleLink, a) -> dict:
    """The wave-start savestates fo_r1_w<i> for --waves, from one policy skip through the gauntlet."""
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.episode import make_tap
    from ssbot.train.wave_start import make_wave_states
    enc = ENCOUNTERS["Forum_A"]
    tap = make_tap(link, enc)
    waves = [int(x) for x in a.waves.split(",")]
    out: dict = {"start": start_battle(link, enc, tap, a.seed)}
    out["make"] = make_wave_states(link, enc, waves, a.instance, timeout_s=a.timeout)
    for c in out["make"].get("on_wave") or ():
        if c.get("result"):
            print(f"wave {c['wave']}: {json.dumps(c['result'])[:500]}", flush=True)
    return out


def check(link: OracleLink, a) -> dict:
    """Load each fo_r1_w<i> and watch: does the battle restart at wave i, with which enemies and helpers?"""
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.episode import wait_settled
    from ssbot.train.wave_start import STATE_PREFIX, verify_wave_start, wait_wave_start
    enc = ENCOUNTERS["Forum_A"]
    out = {}
    for i in [int(x) for x in a.waves.split(",")]:
        r: dict = {}
        try:
            t0 = time.monotonic()
            link.rpc("savestate.load", timeout_s=60, name=f"{STATE_PREFIX}{i}", timeout=50)
            wait_settled(link, enc.scene, timeout_s=40)
            s = wait_wave_start(link, enc, i)
            r["start_real_s"] = round(time.monotonic() - t0, 2)
            r["at_start"] = verify_wave_start(s, enc, i)
            rows = watch(link, a.seconds, every_s=2.0)
            r["watch"] = rows
            r["at_end"] = verify_wave_start(link.state or {}, enc, i)
        except (RuntimeError, TimeoutError, OracleError) as e:
            r["error"] = f"{type(e).__name__}: {e}"
        out[i] = r
        print(f"w{i}: start {r.get('start_real_s')} s {json.dumps(r.get('at_start'))[:300]} | end "
              f"{json.dumps(r.get('at_end'))[:400]} {r.get('error') or ''}", flush=True)
    return out


def climb(link: OracleLink, a) -> dict:
    from ssbot.train.climb import ClimbProbe
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.episode import make_tap
    enc = ENCOUNTERS["Forum_A"]
    tap = make_tap(link, enc)
    from ssbot.train.wave_start import DebugLine
    out: dict = {"start": start_battle(link, enc, tap, a.seed, savestate=a.savestate),
                 "invincible": a.invincible, "hold_dash": not a.tap_dash}
    names = link.rpc("schema.cstate")["bools"]
    probe = ClimbProbe(names, random.Random(a.seed))
    dbg = DebugLine(a.instance) if a.invincible else None
    try:
        if dbg:
            dbg.pdset("isInvincible", "True")
        out.update(probe.run(link, tap, a.repeat, timeout_s=a.timeout, hold_dash=not a.tap_dash))
    finally:
        if dbg:
            dbg.pdset("isInvincible", "False")
            dbg.close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("midsave", "skip", "states", "check", "climb"))
    ap.add_argument("--instance", type=int, default=2)
    ap.add_argument("--wave", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--seed", type=int, default=127000)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--method", default="auto", choices=("auto", "oracle", "policy"))
    ap.add_argument("--savestate", default=None)
    ap.add_argument("--waves", default="1,2,3,4,5,6,7,8,9,10,11,12,13")
    ap.add_argument("--invincible", action="store_true", help="climb: PlayerData isInvincible during the tries")
    ap.add_argument("--tap-dash", action="store_true", help="climb: tap dash (2 frames) instead of holding it")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    link = connect(a.instance)
    try:
        res = {"midsave": midsave, "skip": skip, "states": states, "check": check, "climb": climb}[a.step](link, a)
    except (OracleError, TimeoutError, RuntimeError) as e:
        print(f"FAIL {type(e).__name__}: {e}")
        return 1
    finally:
        try:
            link.act(link.frame + 2, 0, hold_frames=0)
            link.rpc("input.release")
        except (OracleError, TimeoutError, OSError):
            pass
        link.close()
    p = OUT / f"{a.step}_i{a.instance}_{time.strftime('%H%M%S')}.json"
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, default=str)[:6000])
    print("written", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
