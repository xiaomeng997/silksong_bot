"""Load community savestates in the training copy and check they work on 1.0.30000 (M2 W8/W9).

The community savestates (ssbot.tools.community_savestates) were made on 1.0.29315 with an older DebugMod; their
PlayerData field set matches 1.0.30000 but the top-level format is older. SavestateBridge only resolves plain names
in C:\\ssbot\\sandbox\\savestates, so each checked file is copied there as vs_<page>_<slot>.json first. For each: load,
wait until the hero has settled (ssbot.train.episode.wait_settled), and report scene, hero position vs the file's
savePos, HP / max HP, silk, crest, and the entities with HP (bosses in front of the arena show up once their scene
is loaded). Save suppression stays on. Also checks the derived cstate field order (docs/facts/1.0.30000/
cstate_schema.json) against the oracle's schema.cstate RPC.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 1 --detach
    ../scripts/uv.cmd run python -m ssbot.probes.community_check [p6_s1 p7_s3 ...]
"""
import json
import shutil
import sys
import time
from pathlib import Path

from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.probes.common import load_slot, stand_up
from ssbot.train.episode import wait_settled

COMMUNITY = Path(r"C:\ssbot\sandbox\savestates\community\0557f703fa25")
SAVESTATES = Path(r"C:\ssbot\sandbox\savestates")
FACTS = Path(__file__).resolve().parents[3] / "docs" / "facts" / "1.0.30000" / "cstate_schema.json"
DEFAULT = ["p6_s1", "p6_s3", "p6_s7", "p6_s8", "p6_s9", "p7_s1", "p7_s3", "p7_s4", "p7_s5"]


def main(argv: list[str] | None = None) -> int:
    names = (argv if argv is not None else sys.argv[1:]) or DEFAULT
    link = OracleLink(instance=0, connect_timeout_s=120)
    ok = True
    try:
        schema = link.rpc("schema.cstate")
        facts = json.loads(FACTS.read_text(encoding="utf-8"))
        same = schema.get("bools") == facts["bools"] and schema.get("ints") == facts["ints"]
        print(f"{'PASS' if same else 'FAIL'}  cstate schema matches the derived facts file "
              f"({len(schema.get('bools') or [])} bools, {len(schema.get('ints') or [])} ints)")
        ok &= same
        load_slot(link, 1)
        stand_up(link)
        link.rpc("guards.set", save_suppression=True)
        for n in names:
            src = COMMUNITY / f"{n}.json"
            data = json.loads(src.read_text(encoding="utf-8-sig"))
            local = f"vs_{n}"
            shutil.copyfile(src, SAVESTATES / f"{local}.json")
            want = data["saveScene"]
            pos = data.get("savePos") or {}
            t0 = time.perf_counter()
            try:
                link.rpc("savestate.load", timeout_s=60, name=local, timeout=50)
                s = wait_settled(link, want, timeout_s=30)
            except (OracleError, TimeoutError) as e:
                print(f"FAIL  {n:6s} {want:20s} load: {e}")
                ok = False
                continue
            h = s["hero"]
            ents = sorted({(e["type_key"], e.get("hp")) for e in s.get("ents") or [] if (e.get("hp") or 0) >= 50})
            dx = abs(h["pos"][0] - pos.get("x", 0)) + abs(h["pos"][1] - pos.get("y", 0))
            good = s["game"]["scene"] == want and dx < 2.0
            ok &= good
            print(f"{'PASS' if good else 'FAIL'}  {n:6s} {want:20s} {time.perf_counter() - t0:5.1f}s "
                  f"pos ({h['pos'][0]:.1f},{h['pos'][1]:.1f}) vs file ({pos.get('x', 0):.1f},{pos.get('y', 0):.1f}) "
                  f"hp {h['health']}/{h['max_health']} silk {h['silk']} crest {h.get('crest')} big ents {ents[:4]}")
    finally:
        link.close()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
