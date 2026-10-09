"""Derived Forum savestates for experiments (forum_planner_plan R8).

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.forum_states wanderer --instance 3 --src fo_r1_w4 --dst fo_r8_w4w \
        --wave 4

wanderer: load SRC (a wave-start savestate: DebugMod restarts the battle at its wave), equip the Wanderer crest
(crest.equip, unlock), check it with abilities.list and save DST once room.battles reports the battle started at
--wave (as wave_start.make_wave_states: the load of DST restarts the battle at the same wave, RoomSpecific keeps the
BattleScene's current wave; a save before the start does not). Only the crest changes; tools stay where the game
puts them for a crest equipped for the first time (the Minister-below experiment swings the nail only). Safety: a
free training instance (it loads and saves savestates); save suppression on.
"""
import argparse
import json
import sys

from ssbot.ipc.oracle_link import OracleLink


def wanderer(link: OracleLink, src: str, dst: str, wave: int) -> dict:
    from ssbot.train.encounters import FORUM
    from ssbot.train.wave_start import battle_of, wait_wave_start
    link.rpc("savestate.load", timeout_s=60, name=src, timeout=50)
    link.wait_state(lambda s: s.get("hero") and s["hero"].get("hero_accepting_input"), timeout_s=30)
    eq = link.rpc("crest.equip", timeout_s=20, name="Wanderer", unlock=True)
    lst = link.rpc("abilities.list", timeout_s=20)
    if lst.get("crest") != "Wanderer":
        raise SystemExit(f"crest.equip did not take: {lst.get('crest')} ({eq})")
    # as make_wave_states: saved once room.battles reports the battle started at the wave (a save before that has
    # no started BattleScene to restore, and its load does not restart the battle)
    s = wait_wave_start(link, FORUM, wave)
    saved = link.rpc("savestate.save", timeout_s=60, name=dst)
    b = battle_of(s, FORUM.battle_name) or {}
    return {"equip": eq, "crest": lst.get("crest"), "slots": lst.get("slots"), "saved": saved,
            "battle": {k: b.get(k) for k in ("name", "wave", "started", "enemies")}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("wanderer",))
    ap.add_argument("--instance", type=int, required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--wave", type=int, required=True, help="the wave SRC starts (fo_r1_w<i>: i)")
    a = ap.parse_args(argv)
    from ssbot.probes.common import load_slot
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    try:
        load_slot(link, 1)
        link.rpc("guards.set", save_suppression=True)
        print(json.dumps(wanderer(link, a.src, a.dst, a.wave), default=str)[:4000])
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
        except Exception:  # noqa: BLE001
            pass
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
