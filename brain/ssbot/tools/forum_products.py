"""Forum R0 data products (ssbot.knowledge.forum_products) over the per-fight caches (ssbot.tools.forum_extract).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_products --cache C:/ssbot/data/m2_forum_r0/cache
        [--out ../knowledge/1.0.30000/enemies/forum] [--only chains,quiet] [--max-fights N] [--print]

Writes one <out>/<product>.json per product (chains, death_tails, kill_freeze, strikes, quiet, garmond, stances,
below, clawmaiden_distance, bells, boundaries) with the fights it read and the code revision.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from ssbot.knowledge.forum_cache import load_cache
from ssbot.knowledge.forum_products import PRODUCTS, FightView, Products


def default_out() -> Path:
    from ssbot.record.recorder import find_repo_root
    return (find_repo_root() or Path.cwd()) / "knowledge" / "1.0.30000" / "enemies" / "forum"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", default="", help="comma-separated products (default: all)")
    ap.add_argument("--max-fights", type=int, default=0)
    ap.add_argument("--print", action="store_true", help="print the results instead of writing them")
    a = ap.parse_args(argv)
    names = [x for x in a.only.split(",") if x] or list(PRODUCTS)
    paths = sorted(a.cache.glob("*.npz"))
    if a.max_fights:
        paths = paths[:a.max_fights]
    acc = Products(names)
    t_all = time.perf_counter()
    for i, p in enumerate(paths):
        t0 = time.perf_counter()
        acc.add(FightView(load_cache(p)))
        print(f"[{i + 1}/{len(paths)}] {p.stem} ({time.perf_counter() - t0:.1f} s)", flush=True)
    res = acc.result()
    from ssbot.record.recorder import find_repo_root, git_info
    code = git_info(find_repo_root())
    src = {"fights": acc.fights, "cache": str(a.cache), "code": code,
           "tool": "python -m ssbot.tools.forum_products --cache " + str(a.cache)}
    if a.print:
        print(json.dumps(res, indent=1, default=str))
        return 0
    out = a.out or default_out()
    out.mkdir(parents=True, exist_ok=True)
    for k, v in res.items():
        (out / f"{k}.json").write_text(json.dumps({"product": k, "sources": src, **v}, indent=1, default=str) + "\n",
                                       encoding="utf-8")
        print(f"wrote {out / (k + '.json')}")
    print(f"{len(paths)} fights in {time.perf_counter() - t_all:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
