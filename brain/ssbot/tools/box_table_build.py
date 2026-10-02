"""Build the offline damage-box table the ObservabilityFilter places on visible entities (DESIGN §3.9.2; W6).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.box_table_build <rec dir> [<rec dir> ...] [--out PATH]

Every exported, not hidden entity of every STATE adds its damage colliders to its type's union (BoxTable.learn,
anchored on Entity.pos of decision 1 and mirrored with flipX). Shipping the table removes the last FSM-timing leak of
online learning: without it a collider's first appearance in a run (trial run: the Bell Beast's charge polygon at
"Charge Antic", its leap polygon at "Leap Out") shows the hidden state. Recordings used to build the table must be
held out from every coverage claim made with it (ObservabilityFilter docstring).

Cost: STATEs are peeked for "ents" only, ~40 us each (13900K, one core): ~11 s per 270k-STATE recording.
"""
import argparse
import json
import time
from pathlib import Path

from ssbot.backends.observability import DEFAULT_BOX_TABLE, BoxTable
from ssbot.backends.oracle_backend import BUILD, damage_boxes, entity_pos


def learn_recording(table: BoxTable, rec: Path) -> int:
    from ssbot.record.recorder import RecordingReader
    n = 0
    for s in RecordingReader(rec).states(keys=("ents",)):
        n += 1
        for e in s.get("ents") or ():
            if e.get("hidden"):
                continue
            boxes = damage_boxes(e)
            if boxes:
                table.learn(e["type_key"], entity_pos(e), bool(e.get("flipX")), boxes)
    return n


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("recordings", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_BOX_TABLE)
    a = ap.parse_args(argv)
    table = BoxTable()
    sources = []
    t0 = time.perf_counter()
    for rec in a.recordings:
        n = learn_recording(table, rec)
        sources.append({"recording": str(rec).replace("\\", "/"), "states": n})
        print(f"{rec}: {n} STATEs, {len(table.t)} types so far ({time.perf_counter() - t0:.0f} s)")
    doc = {"schema": 1, "build": BUILD, "anchor": "Entity.pos (decision 1), x mirrored when flipX",
           "built": time.strftime("%Y-%m-%d"), "sources": sources, "types": table.to_dict()}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=1) + "\n", "utf-8")
    for tk, rows in sorted(table.t.items()):
        print(f"  {tk}: {len(rows)} boxes")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
