"""Write the compact per-fight caches of Forum gauntlets (ssbot.knowledge.forum_cache) for the offline Forum tools.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_extract C:/ssbot/data/runs/m2/<run> [<run> ...]
        --out C:/ssbot/data/m2_forum_r0/cache [--fights-list fights.json] [--max-fights N]

One <fight id with / as __>.npz (+ .json.gz with the events) per closed fight (behaviour_tables.run_fights); existing
caches are kept. --fights-list takes the frozen fight list a build wrote (behaviour_build --fights-list) instead of
the runs, so the caches and the tables come from the same fights.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from ssbot.knowledge.behaviour_tables import Fight, run_fights
from ssbot.knowledge.forum_cache import cache_name, extract_fight, save_cache


def fights_from(runs: list[Path], listing: Path | None) -> list[Fight]:
    if listing is not None:
        d = json.loads(listing.read_text("utf-8"))
        return [Fight("rec", Path(x["path"]), int(x["f0"]), int(x["f1"]), x["id"], x.get("outcome"))
                for x in d["fights"]]
    out = []
    for r in runs:
        out += run_fights(r)[0]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fights-list", type=Path, default=None)
    ap.add_argument("--max-fights", type=int, default=0)
    a = ap.parse_args(argv)
    fights = fights_from(a.runs, a.fights_list)
    if a.max_fights:
        fights = fights[:a.max_fights]
    t_all = time.perf_counter()
    for i, fight in enumerate(fights):
        path = a.out / cache_name(fight.id)
        if path.exists() and path.with_suffix(".json.gz").exists():
            continue
        t0 = time.perf_counter()
        c = extract_fight(fight)
        save_cache(c, path)
        print(f"[{i + 1}/{len(fights)}] {fight.id}: {len(c['f'])} frames, {len(c['e_fi'])} entity rows, "
              f"{len(c['a_fi'])} ally rows ({time.perf_counter() - t0:.1f} s)", flush=True)
    print(f"done {len(fights)} fights in {time.perf_counter() - t_all:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
