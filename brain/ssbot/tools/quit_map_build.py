"""Build quit map v0 (ssbot.safety.quit_map) from recordings and write knowledge/1.0.30000/quit_map.json.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.quit_map_build --human C:/ssbot/data/human/20260930_210337
        --run C:/ssbot/data/runs/m2/20261001_121446_BellBeast_data [--out ../knowledge/1.0.30000/quit_map.json]

--human: a person's session (state.raw.zst written by ssbot.tools.human_session); --run: a combat run directory
(every recording under rec/ whose meta.json says "closed"; one still being written is skipped) or one recording
directory. Only the STATE keys the builder reads are decoded (msgpack skips the entity and terrain sections), so the
human session of 2026-09-30 (159 471 frames) takes about 3 s.
"""
import argparse
import json
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import zstandard

from ssbot.ipc.framing import HEADER, MsgType
from ssbot.record import formats
from ssbot.safety.quit_map import DEFAULT_PATH, STATE_KEYS, QuitMapBuilder


def raw_states(session: Path, keys: tuple[str, ...] = STATE_KEYS) -> Iterator[dict]:
    """STATE messages of a human session, streamed (the decompressed file is about 1 GB), decoding only `keys`."""
    with (session / "state.raw.zst").open("rb") as fh:
        r = zstandard.ZstdDecompressor().stream_reader(fh, read_size=1 << 20)
        while True:
            head = r.read(4)
            if len(head) < 4:
                return
            body = r.read(int.from_bytes(head, "little"))
            if len(body) < int.from_bytes(head, "little"):
                return   # truncated tail (recording interrupted)
            if body[0] == MsgType.STATE:
                yield formats.peek(memoryview(body)[HEADER.size - 4:], keys)


def recordings(path: Path) -> Iterator[Path]:
    """Closed recordings under a run directory (or the directory itself when it is one)."""
    cands = [path] if (path / "state.index.jsonl").is_file() or (path / "meta.json").is_file() else \
        sorted(p.parent for p in path.glob("rec/*/*/*/meta.json"))
    for p in cands:
        try:
            meta = json.loads((p / "meta.json").read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        if meta.get("status") != "closed":
            print(f"skip {p}: status {meta.get('status')!r}", file=sys.stderr)
            continue
        yield p


def git_rev() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).resolve().parents[2], timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build(human: list[Path], runs: list[Path]) -> dict:
    from ssbot.record.recorder import RecordingReader

    b = QuitMapBuilder()
    for h in human:
        b.begin(f"human/{h.name}", "human")
        for s in raw_states(h):
            b.add(s)
        b.end()
    for run in runs:
        for rec in recordings(run):
            b.begin(f"{run.name}/{rec.name}" if rec != run else rec.name, "train")
            for s in RecordingReader(rec).states(keys=STATE_KEYS):
                b.add(s)
            b.end()
    return b.build({"generated": datetime.now().isoformat(timespec="seconds"), "code_rev": git_rev(),
                    "builder": "ssbot.tools.quit_map_build"})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--human", action="append", default=[], type=Path)
    ap.add_argument("--run", action="append", default=[], type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_PATH)
    a = ap.parse_args(argv)
    if not a.human and not a.run:
        ap.error("give at least one --human or --run")
    data = build(a.human, a.run)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out}: {len(data['scenes'])} scenes from {len(data['sources'])} sources")
    for k, v in data["global_by_key"].items():
        print(f"  {k:10s} {v['s']:9.1f} s  P(pause) {v['p_pause']}  P(quit) {v['p_quit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
