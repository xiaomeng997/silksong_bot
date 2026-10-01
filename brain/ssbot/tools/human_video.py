"""A person's play session's screen video (DESIGN D12, §3.1.4 C4): the ffmpeg command that masks it and keeps the
frame marker's corner losslessly, where the marker lands in it, and the per-frame labels decoded afterwards.

The session (ssbot.tools.human_session) turns the oracle's frame marker on (ssbot.record.marker.marker_on, as every
training session does) and records the desktop with ffmpeg ddagrab (output 0) scaled to OUT = 1920x1080. ffmpeg_cmd()
builds one filter graph with two outputs from one split of the scaled frame, so both hold the same frames with the
same timestamps:
    video.mkv    the HEVC video (NVENC, CQP 18). Before the encoder sees a frame, the vision mask's rect for 1920x1080
                 (ssbot.vision.mask.mask_rect: 78 x 33 px at the top right) is filled with black, and so is the
                 marker's box wherever the session found it outside the mask (fills_for): the stored video never holds
                 a marker pixel there, and a dataset builder applies the same mask to the decoded frame again
    corner.mkv   the mask's rect alone (78 x 33), cropped before any lossy step, 8-bit gray FFV1 (lossless): only for
                 reading frame numbers, never an image a model sees
Without the marker (an older SsOracle refuses it) the video is masked the same way and there is no corner stream.

Where the marker lands. The session runs the game with -screen-fullscreen 1 -screen-width 1920 -screen-height 1080 on
a 3840x2160 desktop: Unity's fullscreen window is a borderless popup covering the desktop (3840x2160 client, the
display mode left at 3840x2160: checked 2026-09-30 while a session ran), into which Unity scales its 1920x1080 render
2x; ddagrab captures the 3840x2160 desktop and the graph scales it by area to 1920x1080 (the 2026-09-30 session's
video.mkv: 1920x1080 HEVC, timestamps on a 1/60 s grid). So render px map onto output px one to one: the marker,
(1860, 4)-(1916, 20) with 4 px cells, lands where mask.marker_rect(1920, 1080) says, inside the output's mask, and a
cell's inner pixels come through the 2x bilinear upscale and the 2x area downscale unchanged (they leak an eighth of
the neighbouring cell into a cell's edge pixels only), so FullResDecoder reads it as in a training capture
(tests/test_human_video.py runs that chain, also through ffmpeg). output_box() maps the oracle's report (STATE mk
rect, px of mk screen) to output px for any setup: Unity scales its render to the window's client on the desktop
(aspect kept, centred), ddagrab captures the desktop, the graph scales the desktop to OUT. A box not inside the mask
(a windowed game, another render size, another desktop) is filled too at the start and flagged mask_mismatch: not
training data.

Labels (labels(); python -m ssbot.tools.human_video <session>, which human_session runs at the end): every corner
frame is decoded with FullResDecoder as the crop of a 1920x1080 client, and every video frame (presentation order)
gets: its pts, its corner frame (the same pts; -1 if none), the decoded frame modulo 65536 or -1 and why
(DECODE_STATUS: absent, unclear, check; "implausible" when marker.reject_implausible rejects it; "off" without a
corner frame), its label frame and source (marker.capture_labels: the decoded frame where plausible, else the
timestamp label: video_start_qpc_ns + pts against STATE q, with D calibrated on the decoded frames), and mm (a STATE
within max_offset frames of its label reported the marker outside the mask, under any window placement seen during
the session). labels.npz holds the arrays, meta.json "labels" the summary: frames, marker / timestamp / none and the
marker-labelled share, decode statuses, D, mask_mismatch and training_safe.

    python -m ssbot.tools.human_video C:\\ssbot\\data\\human\\<session>      # (re)writes labels.npz, meta "labels"
"""
import argparse
import json
import math
import os
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import zstandard

from ssbot.ipc.framing import MsgType
from ssbot.record import align, formats
from ssbot.record.marker import (DECODE_STATUS, LABEL_SOURCES, FullResDecoder, Truth, capture_labels,
                                 reject_implausible)
from ssbot.record.video import inside, marker_screen
from ssbot.vision import mask as vmask

# A copy outside AppData (see brain/uv.toml): the winget install may only exist inside the Claude app's package view.
# ffmpeg 9.0.2: its NVENC API 13.1 needs NVIDIA driver >= 610 (617.14 installed).
FFMPEG = Path(r"C:\ssbot\tools\ffmpeg\bin\ffmpeg.exe")
FFPROBE = FFMPEG.with_name("ffprobe.exe")
OUT = (1920, 1080)
VIDEO, CORNER, LABELS, META = "video.mkv", "corner.mkv", "labels.npz", "meta.json"
# (input arguments, filters before the scale): the desktop of output 0, downloaded from the GPU
DDAGRAB = (("-f", "lavfi", "-i", "ddagrab=output_idx=0:framerate=60:draw_mouse=0"), "hwdownload,format=bgra,")
NVENC = ("-c:v", "hevc_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "constqp", "-qp", "18", "-g", "120")
LOSSLESS = ("-c:v", "ffv1", "-level", "3")
OFF = DECODE_STATUS.index("off")


# ---- where the marker lands, and the command ------------------------------------------------------------------------

def output_box(rect, render: tuple[int, int], client: tuple[int, int, int, int], desktop: tuple[int, int],
               out: tuple[int, int] = OUT) -> tuple[int, int, int, int] | None:
    """The oracle's marker (STATE mk rect, px of the `render` size) in output px: Unity scales the render to the
    game window's client (x, y, w, h on the desktop), aspect kept and centred (its fullscreen window; a windowed game
    renders at its client's size), ddagrab captures the desktop (w, h) and the graph scales that to `out`. Rounded
    outward, plus the interpolation's blur: a px per unit of render-to-output scale, at least 1 when anything scales
    (also when the scales cancel out, as 2x up and 2x down do). None for an empty rect."""
    x0, y0, x1, y1 = (float(v) for v in rect)
    if not (x1 > x0 and y1 > y0):
        return None
    (rw, rh), (cx, cy, cw, ch), (dw, dh), (ow, oh) = render, client, desktop, out
    s = min(cw / rw, ch / rh)
    bx, by = cx + (cw - rw * s) / 2, cy + (ch - rh * s) / 2
    kx, ky = ow / dw, oh / dh
    b = 0 if s == 1 and kx == 1 and ky == 1 else max(1, math.ceil(max(s * kx, s * ky)))
    return (math.floor((bx + x0 * s) * kx) - b, math.floor((by + y0 * s) * ky) - b,
            math.ceil((bx + x1 * s) * kx) + b, math.ceil((by + y1 * s) * ky) + b)


def fills_for(boxes: Iterable[tuple[int, int, int, int] | None], out: tuple[int, int] = OUT) -> list[list[int]]:
    """The rects the video's graph fills: the vision mask's for `out`, and every marker box not inside it (clipped
    to the frame)."""
    m = vmask.mask_rect(*out)
    fills = [list(m)]
    for b in boxes:
        if b is not None and not inside(b, m):
            c = [max(0, b[0]), max(0, b[1]), min(out[0], b[2]), min(out[1], b[3])]
            if c[2] > c[0] and c[3] > c[1] and c not in fills:
                fills.append(c)
    return fills


def ffmpeg_cmd(session: Path, fills: list, corner: tuple[int, int, int, int] | None = None, *, source=DDAGRAB,
               encoder: tuple[str, ...] = NVENC, out: tuple[int, int] = OUT, ffmpeg: Path = FFMPEG) -> list[str]:
    """The session's ffmpeg command: `source` (input arguments, filters ahead of the scale) scaled by area to `out`,
    then split: the `fills` filled black (drawbox) and encoded with `encoder` to video.mkv, and, with `corner`
    (x0, y0, x1, y1 in output px), that rect cropped from the unfilled frame as gray FFV1 to corner.mkv."""
    inputs, pre = source
    boxes = ",".join(f"drawbox=x={x0}:y={y0}:w={x1 - x0}:h={y1 - y0}:color=black:t=fill" for x0, y0, x1, y1 in fills)
    scaled = f"[0:v]{pre}scale={out[0]}:{out[1]}:flags=area"
    if corner is None:
        graph, tail = f"{scaled},{boxes},format=nv12[v]", []
    else:
        x0, y0, x1, y1 = corner
        graph = (f"{scaled},split=2[full][raw];[full]{boxes},format=nv12[v];"
                 f"[raw]crop={x1 - x0}:{y1 - y0}:{x0}:{y0},format=gray[c]")
        tail = ["-map", "[c]", *LOSSLESS, str(Path(session) / CORNER)]
    return [str(ffmpeg), "-hide_banner", "-loglevel", "info", "-stats", "-y", *inputs, "-filter_complex", graph,
            "-map", "[v]", *encoder, str(Path(session) / VIDEO), *tail]


# ---- reading the session --------------------------------------------------------------------------------------------

@dataclass
class States:
    """Per STATE frame of the session (ascending): end of frame (ns, QPC), marker drawn, and the marker's place
    (index into places: (mk rect, render size); -1 while it is off)."""
    f: np.ndarray
    t_eof: np.ndarray
    drawn: np.ndarray
    place: np.ndarray
    places: list


def _read(r, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = r.read(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def read_states(session: Path, freq: int, screen: tuple[int, int] | None = None) -> States:
    """The STATE frames of the session's state.raw.zst (bare wire frames in zstd, ssbot.tools.human_session),
    streamed: f, q and mk only. `screen`: the render size for an mk without one (the marker_on reply)."""
    rows: dict[int, tuple] = {}
    keys: dict[tuple, int] = {}
    with (Path(session) / "state.raw.zst").open("rb") as fh:
        r = zstandard.ZstdDecompressor().stream_reader(fh, read_across_frames=True)
        while True:
            head = _read(r, 4)
            n = int.from_bytes(head, "little") if len(head) == 4 else 0
            body = _read(r, n) if n else b""
            if not n or len(body) < n:
                break  # the end, or a torn tail
            msg_type, _, flags, _, payload = formats.parse_frame(head + body)
            if msg_type != MsgType.STATE:
                continue
            s = formats.peek(payload, ("f", "q", "mk"), flags, last=formats.STATE_LAST)
            f, q, mk = s.get("f"), s.get("q"), s.get("mk")
            if not (isinstance(f, int) and isinstance(q, int)) or f in rows:
                continue
            place = -1
            rect = mk.get("rect") if isinstance(mk, dict) else None
            if isinstance(rect, (list, tuple)) and len(rect) == 4 and all(isinstance(v, (int, float)) for v in rect):
                key = (tuple(float(v) for v in rect), marker_screen(s) or screen)
                place = keys.setdefault(key, len(keys))
            rows[f] = (q * 1_000_000_000 // freq, isinstance(mk, dict) and mk.get("drawn") is True, place)
    fs = sorted(rows)
    return States(np.asarray(fs, np.int64), np.asarray([rows[f][0] for f in fs], np.int64),
                  np.asarray([rows[f][1] for f in fs], bool), np.asarray([rows[f][2] for f in fs], np.int64),
                  list(keys))


def probe(path: Path, ffprobe: Path = FFPROBE) -> tuple[np.ndarray, tuple[int, int]]:
    """(pts of every packet in ns, ascending: presentation order; (w, h)) of a file's first video stream."""
    out = subprocess.run([str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,time_base:packet=pts", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    st = j["streams"][0]
    num, den = (int(v) for v in st["time_base"].split("/"))
    pts = np.sort(np.asarray([p["pts"] for p in j.get("packets") or () if isinstance(p.get("pts"), int)], np.int64))
    return pts * 1_000_000_000 * num // den, (int(st["width"]), int(st["height"]))


def corner_frames(path: Path, size: tuple[int, int], ffmpeg: Path = FFMPEG) -> Iterator[np.ndarray]:
    """The corner stream's frames as gray (h, w) arrays, in order (decoded by ffmpeg, frame for frame)."""
    w, h = size
    p = subprocess.Popen([str(ffmpeg), "-nostdin", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt",
                          "gray", "-fps_mode", "passthrough", "pipe:1"], stdout=subprocess.PIPE)
    try:
        while len(buf := _read(p.stdout, w * h)) == w * h:
            yield np.frombuffer(buf, np.uint8).reshape(h, w)
    finally:
        if p.poll() is None:
            p.kill()  # (our own decoder, when the caller stops early)
        p.stdout.close()
        p.wait()


def decode_corner(frames: Iterable[np.ndarray], corner: tuple[int, int, int, int], out: tuple[int, int] = OUT,
                  progress=None) -> tuple[np.ndarray, np.ndarray]:
    """Per corner frame: the decoded frame modulo 65536 (-1 if none) and its DECODE_STATUS index, read with the
    capture path's decoder as the crop at corner[:2] of an `out` client."""
    dec = FullResDecoder()
    values, statuses = [], []
    for img in frames:
        d = dec.decode(img, client=out, origin=(corner[0], corner[1]))
        values.append(-1 if d.value is None else d.value)
        statuses.append(DECODE_STATUS.index(d.status))
        if progress is not None and len(values) % 50_000 == 0:
            progress(len(values))
    return np.asarray(values, np.int64), np.asarray(statuses, np.int64)


# ---- labels ---------------------------------------------------------------------------------------------------------

def _near(bad_rows: np.ndarray, st: States, frames: np.ndarray, reach: int) -> np.ndarray:
    """Per label frame: a STATE frame within `reach` frames of it is flagged in bad_rows."""
    if not bad_rows.any():
        return np.zeros(len(frames), bool)
    f0 = int(st.f[0])
    dense = np.zeros(int(st.f[-1]) - f0 + 1 + 2 * reach + 1, np.int64)
    dense[st.f - f0 + reach + 1] = bad_rows
    c = np.cumsum(dense)
    k = np.clip(frames - f0 + reach + 1, 0, len(dense) - 1)
    lo, hi = np.clip(k - reach - 1, 0, len(c) - 1), np.clip(k + reach, 0, len(c) - 1)
    return (c[hi] - c[lo]) > 0


def build(meta: dict, st: States, video_pts: np.ndarray, corner_pts: np.ndarray, values: np.ndarray,
          statuses: np.ndarray, max_offset: int = align.Params.max_offset) -> tuple[dict, dict]:
    """The labels of every video frame (module docstring) from the session's meta (video_start_qpc_ns, "video":
    placements and render), its STATEs, the video's and the corner stream's pts (ns) and the corner frames' decodes.
    Returns (arrays for labels.npz, the summary for meta.json "labels")."""
    n = len(video_pts)
    ci = np.clip(np.searchsorted(corner_pts, video_pts), 0, max(0, len(corner_pts) - 1))
    match = (corner_pts[ci] == video_pts) if len(corner_pts) else np.zeros(n, bool)
    corner = np.where(match, ci, -1)
    value = np.where(match, values[ci] if len(values) else -1, -1)
    status = np.where(match, statuses[ci] if len(statuses) else OFF, OFF)
    t = int(meta["video_start_qpc_ns"]) + video_pts
    tr = Truth(np.arange(n), t, t, value, status, st.f, st.t_eof, st.drawn)
    tr = reject_implausible(tr, "frame", None, max_offset)
    lb = capture_labels(tr, "frame", None, max_offset)
    # The marker outside the mask: any placement of the game window seen during the session counts.
    v = meta.get("video") or {}
    mask = vmask.mask_rect(*OUT)
    fills = [tuple(r) for r in v.get("fills") or [mask]]
    render = tuple(v.get("render") or OUT)
    outside, unfilled = np.zeros(len(st.places), bool), np.zeros(len(st.places), bool)
    for i, (rect, screen) in enumerate(st.places):
        for pl in v.get("placements") or [{"client": [0, 0, *OUT], "desktop": list(OUT)}]:
            box = output_box(rect, tuple(screen or render), tuple(pl["client"]), tuple(pl["desktop"]))
            if box is not None:
                outside[i] |= not inside(box, mask)
                unfilled[i] |= not any(inside(box, r) for r in fills)
    def flagged(per_place: np.ndarray) -> np.ndarray:
        """Per video frame: a STATE within max_offset frames of its label reported such a place (any, unlabelled)."""
        if not len(st.f) or not len(st.places):
            return np.zeros(n, bool)
        rows = (st.place >= 0) & per_place[np.clip(st.place, 0, None)]
        return np.where(lb.frame >= 0, _near(rows, st, lb.frame, max_offset), rows.any())

    mm, raw = flagged(outside), flagged(unfilled)
    arrays = {"index": np.arange(n), "pts_ns": video_pts, "corner": corner, "mk": tr.value, "status": tr.status,
              "frame": lb.frame, "source": lb.source, "mm": mm.astype(np.uint8),
              "statuses": np.asarray(DECODE_STATUS), "sources": np.asarray(LABEL_SOURCES)}
    s = lb.summary()
    u, c = np.unique(tr.status, return_counts=True)
    summary = {"source": "marker", "file": LABELS, "frames": n, "corner_frames": len(corner_pts),
               "without_corner": int((~match).sum()), "marker": s["marker"], "timestamp": s["timestamp"],
               "none": s["none"], "marker_share": s["marker_share"], "clock": "video_start_qpc_ns + pts",
               "D_ms": s["D_ms"], "decode": {DECODE_STATUS[int(a)]: int(b) for a, b in zip(u, c)},
               "mask_mismatch": int(mm.sum()), "marker_pixels_stored": int(raw.sum()),
               "training_safe": bool(n) and not mm.any()}
    return arrays, summary


def write_meta(session: Path, meta: dict) -> None:
    tmp = Path(session) / (META + ".tmp")
    tmp.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, Path(session) / META)


def labels(session: str | Path, *, ffmpeg: Path = FFMPEG, ffprobe: Path = FFPROBE, progress=print) -> dict:
    """Decode the session's corner stream, write labels.npz and meta.json "labels"; returns that summary. A session
    without a corner stream (the marker was off, an older session) gets no labels file: its summary says timestamp
    labels and why, and nothing is written."""
    session = Path(session)
    meta = json.loads((session / META).read_text("utf-8"))
    v = meta.get("video") or {}
    if not (session / CORNER).is_file() or not v.get("corner"):
        why = (meta.get("marker") or {}).get("why") or "no corner stream (recorded without the frame marker)"
        return {"source": "timestamp", "why": why}
    corner = tuple(v["corner"])
    freq = (meta.get("hello") or {}).get("qpc_freq") or 10_000_000
    st = read_states(session, freq, tuple((meta.get("marker") or {}).get("screen") or v.get("render") or OUT))
    video_pts, _ = probe(session / VIDEO, ffprobe)
    corner_pts, size = probe(session / CORNER, ffprobe)
    progress(f"decoding {len(corner_pts)} corner frames ({size[0]}x{size[1]}) against {len(st.f)} STATE frames")
    values, statuses = decode_corner(corner_frames(session / CORNER, size, ffmpeg), corner,
                                     progress=lambda k: progress(f"  {k} corner frames"))
    if len(values) != len(corner_pts):
        progress(f"warning: {len(values)} corner frames decoded, {len(corner_pts)} packets: matched in order")
        m = min(len(values), len(corner_pts))
        corner_pts, values, statuses = corner_pts[:m], values[:m], statuses[:m]
    arrays, summary = build(meta, st, video_pts, corner_pts, values, statuses)
    np.savez_compressed(session / LABELS, **arrays)
    meta["labels"] = summary
    write_meta(session, meta)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.tools.human_video", description=__doc__.split("\n")[0])
    ap.add_argument("session", help="human session folder (meta.json, state.raw.zst, video.mkv, corner.mkv)")
    a = ap.parse_args(argv)
    summary = labels(a.session)
    print(json.dumps(summary, indent=1))
    return 0 if summary.get("source") == "marker" else 1


if __name__ == "__main__":
    sys.exit(main())
