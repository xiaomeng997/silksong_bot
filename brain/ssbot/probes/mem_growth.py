"""Where does memory grow per savestate load? (the M1 soak: private bytes about +35 MB/h per instance at about 730
savestate loads/h, handles about +15/h; 2026-09-30).

Needs one training instance with a sandbox save in gameplay (python -m ssbot.tools.launcher -n 1 --detach, then load a
save; --load does slot 1 from the title) and nothing else connected to its IPC port.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.mem_growth [--loads 600] [--every 100] [--instance 0] [--load]

Saves a savestate "mem_probe" where Hornet stands, then loads it --loads times. Every --every loads it samples
mem.stats with a forced GC (gc=true) and object counts (objects=true), plus the game process's private bytes, RSS and
handles (psutil, pid from the launcher registry). Prints each sample and the least-squares growth per 100 loads of every
metric, so the growth can be pinned on the managed heap (ours or the game's), Unity's allocator, loaded objects of some
type, the oracle's caches, or native memory outside all of these (private bytes growing while the rest stay flat).
"""
import argparse
import json
import sys
import time
from pathlib import Path

from ssbot.ipc.oracle_link import OracleError, OracleLink

STATE_NAME = "mem_probe"


def game_pid(instance: int) -> int | None:
    from ssbot.tools.launcher import PrefsGuard

    for x in PrefsGuard.default().status()["live"]:
        if int(x.get("instance", -1)) == instance:
            return int(x["pid"])
    return None


def proc_numbers(pid: int | None) -> dict:
    if pid is None:
        return {}
    import psutil

    try:
        p = psutil.Process(pid)
        mi = p.memory_info()
        return {"private_mb": mi.private / 2**20, "rss_mb": mi.rss / 2**20, "handles": p.num_handles()}
    except Exception:  # noqa: BLE001 - a sample without process numbers is still useful
        return {}


def flatten(sample: dict) -> dict[str, float]:
    """The numeric metrics of one sample: bytes as MB, counts as counts."""
    m = sample["mem"]
    out = {k: m[k] / 2**20 for k in ("gc_total", "mono_used", "mono_heap", "unity_allocated", "unity_reserved",
                                      "gfx_driver") if isinstance(m.get(k), (int, float))}
    out["fsm_infos"] = m.get("oracle", {}).get("fsm_infos", 0)
    for k, v in (m.get("oracle", {}).get("ents") or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[f"ents.{k}"] = v
    for k, v in (m.get("objects") or {}).items():
        out[f"obj.{k}"] = v
    out.update(sample.get("proc", {}))
    return out


def slopes(samples: list[dict]) -> dict[str, float]:
    """Least-squares growth per 100 loads of every metric present in all samples."""
    if len(samples) < 2:
        return {}
    rows = [(s["loads"], flatten(s)) for s in samples]
    keys = set(rows[0][1])
    for _, r in rows[1:]:
        keys &= set(r)
    out = {}
    n = len(rows)
    xm = sum(x for x, _ in rows) / n
    var = sum((x - xm) ** 2 for x, _ in rows)
    for k in sorted(keys):
        ym = sum(r[k] for _, r in rows) / n
        out[k] = sum((x - xm) * (r[k] - ym) for x, r in rows) / var * 100 if var else 0.0
    return out


def sample(link: OracleLink, pid: int | None, loads: int) -> dict:
    mem = link.rpc("mem.stats", timeout_s=60, gc=True, objects=True)
    return {"loads": loads, "t": time.time(), "mem": mem, "proc": proc_numbers(pid)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--loads", type=int, default=600)
    ap.add_argument("--every", type=int, default=100)
    ap.add_argument("--load", action="store_true", help="load sandbox slot 1 from the title screen first")
    ap.add_argument("--out", type=Path, default=None, help="write the samples as JSON here")
    a = ap.parse_args(argv)

    link = OracleLink(instance=a.instance)
    try:
        if "mem.stats" not in (link.hello.get("rpcs") or []):
            print("[FAIL] the oracle has no mem.stats RPC (an older plugin?)")
            return 2
        from ssbot.probes.common import in_gameplay, load_slot, stand_up

        s = link.wait_state(lambda s: s.get("game") is not None, timeout_s=60)
        if not in_gameplay(s):
            if not a.load:
                print("[FAIL] not in gameplay: load a sandbox save first, or pass --load")
                return 2
            load_slot(link, 1)
        stand_up(link)
        link.rpc("input.release")
        link.rpc("savestate.save", timeout_s=30, state=STATE_NAME)
        pid = game_pid(a.instance)
        samples = [sample(link, pid, 0)]
        print(json.dumps(flatten(samples[0]), indent=None)[:600])
        t0 = time.monotonic()
        for i in range(1, a.loads + 1):
            link.rpc("savestate.load", timeout_s=40, state=STATE_NAME, timeout=30)
            if i % a.every == 0 or i == a.loads:
                samples.append(sample(link, pid, i))
                f = flatten(samples[-1])
                print(f"{i:5d} loads, {time.monotonic() - t0:6.0f} s: private {f.get('private_mb', 0):8.1f} MB, "
                      f"mono_used {f.get('mono_used', 0):7.1f} MB, unity_alloc {f.get('unity_allocated', 0):8.1f} MB, "
                      f"objects {int(f.get('obj.Object', 0))}, handles {f.get('handles', 0)}", flush=True)
        per100 = slopes(samples)
        print("\ngrowth per 100 loads (least squares; MB for memory, counts otherwise):")
        for k, v in sorted(per100.items(), key=lambda kv: -abs(kv[1])):
            if abs(v) > 1e-6:
                print(f"  {k:28s} {v:+10.3f}")
        if a.out:
            a.out.write_text(json.dumps({"samples": samples, "per_100_loads": per100}, indent=1), encoding="utf-8")
            print(f"wrote {a.out}")
        return 0
    except (OracleError, TimeoutError, OSError) as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        return 1
    finally:
        try:
            link.rpc("input.release", timeout_s=5)
        except Exception:  # noqa: BLE001
            pass
        link.close()


if __name__ == "__main__":
    sys.exit(main())
