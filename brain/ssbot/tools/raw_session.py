"""Read and summarise a human-session recording written by ssbot.tools.human_session (state.raw.zst + meta.json).

    python -m ssbot.tools.raw_session C:/ssbot/data/human/<session>
"""
import json
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import msgpack
import zstandard

from ssbot.ipc.framing import HEADER, MsgType, names

GS_NAMES = ["INACTIVE", "MAIN_MENU", "LOADING", "ENTERING_LEVEL", "PLAYING", "PAUSED", "EXITING_LEVEL", "CUTSCENE",
            "PRIMER"]


def messages(session: Path) -> Iterator[tuple[int, dict]]:
    """Yield (msg_type, decoded payload) for every recorded message, in order."""
    with (session / "state.raw.zst").open("rb") as f:
        data = zstandard.ZstdDecompressor().stream_reader(f).read()
    off = 0
    while off + 4 <= len(data):
        n = int.from_bytes(data[off:off + 4], "little")
        body = data[off + 4:off + 4 + n]
        off += 4 + n
        if len(body) < n:
            break  # truncated tail (recording interrupted)
        yield body[0], msgpack.unpackb(body[HEADER.size - 4:], raw=False, strict_map_key=False)


def states(session: Path) -> Iterator[dict]:
    return (m for t, m in messages(session) if t == MsgType.STATE)


def summarise(session: Path) -> dict:
    frames = list(states(session))
    if not frames:
        return {"frames": 0}
    fs = [s["f"] for s in frames]
    span_s = (frames[-1]["q"] - frames[0]["q"]) / 1e7
    scenes, hp, src, buttons = [], [], Counter(), Counter()
    gs_time = Counter()
    last_mask = 0
    for s in frames:
        g = s.get("game") or {}
        gs_time[GS_NAMES[g["gs"]] if "gs" in g and g["gs"] < len(GS_NAMES) else "none"] += s["udt"]
        if g.get("scene") and (not scenes or scenes[-1] != g["scene"]):
            scenes.append(g["scene"])
        inp = s.get("input")
        if inp:
            if inp["mask"] or any(abs(v) > 0.3 for v in inp["move"]):
                src[inp["src"]] += 1
            pressed = inp["mask"] & ~last_mask
            for n in names(pressed):
                buttons[n] += 1
            last_mask = inp["mask"]
    return {
        "frames": len(frames),
        "frame_gaps": sum(1 for a, b in zip(fs, fs[1:]) if b != a + 1),
        "oracle_drops": frames[-1].get("drop"),
        "span_s": round(span_s, 1),
        "fps": round(len(frames) / span_s, 2) if span_s else None,
        "time_by_game_state_s": {k: round(v, 1) for k, v in gs_time.most_common()},
        "scenes_visited": scenes,
        "play_time_live_end": (frames[-1].get("game") or {}).get("t_live"),
        "active_input_frames_by_source": dict(src),
        "button_presses": dict(buttons.most_common()),
        "cost_us_p50": sorted(s["cost_us"] for s in frames)[len(frames) // 2],
    }


if __name__ == "__main__":
    session = Path(sys.argv[1])
    meta_path = session / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        print("meta:", {k: meta[k] for k in ("started", "duration_s", "state_frames_written",
                                             "state_frames_dropped_by_recorder", "kept_gamepad_prefs") if k in meta})
    else:
        print("meta: missing (session did not finish cleanly)")
    print(json.dumps(summarise(session), indent=1, ensure_ascii=False))
