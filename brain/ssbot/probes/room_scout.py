"""Room scout (M2 W8 kinematics excitation): load candidate savestates on one training instance and report, per room,
the tall wall faces near the hero, the floor under her and whether any enemy is around, so the Forum-loadout
excitation (probes/kin_excite_forum) gets a quiet room with tall walls.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.room_scout --instance 3 kn_scout_p2_s2 kn_scout_p9_s4 ...
        [--out C:/ssbot/sandbox/kn_scout]

Each savestate (a name in C:\\ssbot\\sandbox\\savestates) is loaded with save suppression on; after the hero settles,
the room's TERRAIN (latest of the scene) is saved as <out>/<name>.terrain.msgpack, and the STATE's enemies (entities
with a health manager or a damaging collider, not hidden) are counted. Walls: vertical faces at least --min-height
tall within --radius of the hero, with the side the hero would cling from (open air there) and whether the wall
faces pass kin_jit.facing_near_wall from a cling pose at mid height.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import msgpack
import numpy as np


def walls_near(terrain, x: float, y: float, radius: float, min_h: float) -> list[dict]:
    from ssbot.knowledge import kin_jit
    from ssbot.knowledge.kinematics import HeroParams
    from ssbot.tools.coverage_map import _inside_solid
    p = HeroParams()
    TT = terrain.packed()
    out = []
    for xw, ya, yb in terrain.vseg:
        if yb - ya < min_h or abs(xw - x) > radius or yb < y - radius or ya > y + radius:
            continue
        for side in (-1.0, 1.0):
            px = xw - side * (p.half_width + p.skin)
            py = 0.5 * (ya + yb)
            if _inside_solid(terrain, px, py, p):
                continue
            ok = bool(kin_jit.facing_near_wall(px, py, side, p.wall_ray, TT))
            out.append({"x": float(xw), "y0": float(ya), "y1": float(yb), "h": float(yb - ya),
                        "hero_side": "right" if side < 0 else "left", "cling_ok_mid": ok})
    return sorted(out, key=lambda w: -w["h"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+")
    ap.add_argument("--instance", type=int, default=3)
    ap.add_argument("--out", type=Path, default=Path(r"C:\ssbot\sandbox\kn_scout"))
    ap.add_argument("--radius", type=float, default=30.0)
    ap.add_argument("--min-height", type=float, default=8.0)
    a = ap.parse_args(argv)
    from ssbot.ipc.ents import is_hidden, is_threat
    from ssbot.ipc.oracle_link import OracleLink
    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.probes.common import load_slot
    from ssbot.probes.kin_excite import TerrainTap
    a.out.mkdir(parents=True, exist_ok=True)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    try:
        load_slot(link, 1)
        link.rpc("guards.set", save_suppression=True)
        tap = TerrainTap(link)
        for name in a.names:
            t0 = time.time()
            res = link.rpc("savestate.load", timeout_s=60, name=name, timeout=50)
            s = link.wait_state(lambda s: s.get("hero") and s["hero"].get("hero_accepting_input"), timeout_s=30)
            scene = (s.get("game") or {}).get("scene")
            time.sleep(1.5)
            s = link.state
            msg = tap.wait(scene, timeout_s=10)
            hero = s["hero"]
            x, y = float(hero["pos"][0]), float(hero["pos"][1])
            ents = [e for e in s.get("ents") or () if not is_hidden(e)]
            enemies = [e.get("type_key") for e in ents if e.get("hp") is not None or
                       any(is_threat(c) for c in e.get("colliders") or ())]
            print(f"== {name}: scene {scene} hero ({x:.2f}, {y:.2f}) load {time.time() - t0:.1f} s, reply "
                  f"{ {k: res.get(k) for k in ('ok', 'scene', 'ms') if isinstance(res, dict)} }")
            print(f"   enemies/threats in view: {enemies[:12]}")
            if msg is None:
                print("   no TERRAIN")
                continue
            (a.out / f"{name}.terrain.msgpack").write_bytes(msgpack.packb(msg, use_bin_type=True))
            terr = Terrain2D.from_message(msg)
            ws = walls_near(terr, x, y, a.radius, a.min_height)
            for w in ws[:8]:
                print(f"   wall x {w['x']:.2f} y {w['y0']:.1f}..{w['y1']:.1f} (h {w['h']:.1f}), hero on its "
                      f"{w['hero_side']}, cling ok at mid {w['cling_ok_mid']}")
            under = [r for r in terr.hseg if r[1] <= x <= r[2] and r[0] <= y]
            if under:
                fl = max(under, key=lambda r: r[0])
                print(f"   floor under hero y {fl[0]:.2f} x {fl[1]:.1f}..{fl[2]:.1f}")
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
        except Exception:  # noqa: BLE001
            pass
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
