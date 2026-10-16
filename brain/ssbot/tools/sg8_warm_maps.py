"""Task 1v1 SG8 (forum.md 64, stalls): decompress every slam map tag and wall bucket into the mmap cache before a live
run (special_map_rt.load_levels: C:/ssbot/cache/special_map/<file>_<size>_<mtime>/*.npy). Live 2026-10-15 a bucket's
first use decompressed 1.5 GB mid-fight (~3 s, twice: HARNESS_FAIL). 1v1_freeze.ps1 runs this on the frozen checkout's
knowledge dir after copying it (the cache key is the file's size and mtime, so a copy with its mtime kept reuses an
entry made from the worktree's file).

    ../scripts/uv.cmd run python -m ssbot.tools.sg8_warm_maps [--dir <knowledge/.../forum>] [--tags sg4,sg7,sg7r,sg8]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ssbot.combat import special_map as sm
from ssbot.combat import special_map_rt as smrt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=sm.MAP_DIR)
    ap.add_argument("--tags", default="", help="comma-separated tags (default: every special_map_CL_SLAM_*_levels.npz)")
    a = ap.parse_args(argv)
    files = sorted(a.dir.glob("special_map_CL_SLAM_*_levels.npz"))
    if a.tags:
        want = set(a.tags.split(","))
        files = [f for f in files if f.stem[len("special_map_CL_SLAM_"):-len("_levels")].split("_")[0] in want]
    out = []
    t0 = time.time()
    for f in files:
        t1 = time.time()
        try:
            srcs, ti, meta = smrt.load_levels(f, mmap=True)
            out.append({"file": f.name, "s": round(time.time() - t1, 2), "mb": meta.get("array_mb")})
        except Exception as ex:  # noqa: BLE001
            out.append({"file": f.name, "error": repr(ex)[:200]})
        print(json.dumps(out[-1]), flush=True)
    print(json.dumps({"files": len(files), "seconds": round(time.time() - t0, 1), "cache": str(smrt.CACHE)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
