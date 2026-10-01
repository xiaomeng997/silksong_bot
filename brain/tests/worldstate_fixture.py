"""Real STATE dicts for the WorldState backend tests: three windows of the trial Bell Beast run, episode seed 1
(runs/m2/20261001_121446_BellBeast_data, rec/2026-10-01/TRAIN/i0_000), stored as one msgpack map, zstd level 19
(tests/data/bellbeast_states.msgpack.zst, 128 KB). The large per-frame bookkeeping sections are dropped and "hud"
keeps only "hidden".

  56520-56900  the wake (Control Dormant -> Submerged Init at 56532), first emergence and charge (the boss is first
               exported at 56714), a hit taken at 56777 (2 masks, LethalBlock catastrophe, freeze, disable_pause)
               and the first hit dealt at 56818 (150 -> 145)
  61560-62200  the Rage pattern (Rage Burst at 61600), hits dealt at 61616 / 61710, a DropBell hit at 62131
  68960-69060  the kill: last nail hit at 68995 (20 -> 15), Silkspear, Control -> "Death Broadcast" at 69029 in the
               frame the boss leaves "ents" (no HP drop for the killing blow)

Regenerate (needs the recording):  python -m tests.worldstate_fixture
"""
from pathlib import Path

import msgpack
import zstandard

PATH = Path(__file__).parent / "data" / "bellbeast_states.msgpack.zst"
SOURCE = Path(r"C:\ssbot\data\runs\m2\20261001_121446_BellBeast_data\rec\2026-10-01\TRAIN\i0_000")
WINDOWS = ((56520, 56900), (61560, 62200), (68960, 69060))
KEEP = ("f", "q", "fc", "fs", "udt", "dt", "ts", "fdt", "focus", "drop", "act", "ev", "game", "pause", "input", "hero",
        "cam", "ents")
BOSS_IID = 529544

_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is None:
        _cache = msgpack.unpackb(zstandard.ZstdDecompressor().decompress(PATH.read_bytes()), raw=False,
                                 strict_map_key=False)
    return _cache


def window(i: int) -> list[dict]:
    """The STATEs of WINDOWS[i] (fresh dicts: tests may modify them)."""
    f0, f1 = WINDOWS[i]
    states = [s for s in load()["states"] if f0 <= s["f"] <= f1]
    return msgpack.unpackb(msgpack.packb(states), raw=False, strict_map_key=False)


def main() -> None:
    from ssbot.record.recorder import RecordingReader
    r = RecordingReader(SOURCE)
    states = []
    for f0, f1 in WINDOWS:
        for s in r.states(f0, f1):
            d = {k: s[k] for k in KEEP if k in s}
            d["hud"] = {"hidden": (s.get("hud") or {}).get("hidden")}
            states.append(d)
    doc = {"source": "runs/m2/20261001_121446_BellBeast_data rec/2026-10-01/TRAIN/i0_000 (episode seed 1)",
           "windows": WINDOWS, "states": states}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_bytes(zstandard.ZstdCompressor(level=19).compress(msgpack.packb(doc)))
    print(f"{len(states)} STATEs -> {PATH} ({PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
