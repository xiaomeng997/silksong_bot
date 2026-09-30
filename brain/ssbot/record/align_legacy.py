"""Offset between the STATE clock and the video of an old human session (read-only; DESIGN §3.1.4 C4).

Sessions recorded before Core.Qpc (e.g. C:\\ssbot\\data\\human\\20260930_005501: state.raw.zst + video.mkv from
ffmpeg ddagrab) stamp STATE "q" with Mono's Stopwatch, which counts from the process's first call (probes.md, M1
clocks), and their video with container timestamps (1 ms) from ffmpeg's start. One constant links them: video frame
i shows the newest STATE frame f with q_ns[f] + offset <= pts_ns[i]. These sessions have no camera export, so the
camera-track aligner (ssbot.record.align) cannot run on them. What both streams show is when the game world stands
still: during a FreezeMoment (timeScale 0, e.g. on taking damage) the renders repeat pixel for pixel. Measured on
20260930_005501: the frames inside a dt == 0 run are identical to their predecessor, the first frame with dt > 0 again
always changes the image, but the FIRST frame of a run still differs from the one before (whatever the hit set up
after the previous render shows up), so it is not scored.

  1. Coarse: on a 1 ms grid, "gameplay advancing (+1) / frozen (-1)" from STATE is cross-correlated (FFT) with "image
     changing (+1) / still (-1)" from the video, over +-search_s around the offset implied by the first frames of both
     streams. Gameplay vs menus and fades dominate: this lands within about a frame.
  2. Frame: every 0.25 ms within +-fine_ms, a log-likelihood score of the still predictions (a video frame pair whose
     labels are frozen at both ends and did not advance in between must be still; P(still) = 0.95 there against the
     base rate elsewhere), so a still predicted for a changing pair costs more than a correct one gains. The offsets
     sharing the best score form a plateau shorter than a frame; the next frame phases score clearly lower.
  3. Phase: freezes are too rare to place the offset inside that plateau. Consecutive video frames should show
     consecutive STATE frames, and near a wrong phase capture jitter makes labels repeat and skip; the offset is the
     middle of the band where that count is lowest (it bottoms out at the game's own repeated frames).

The report gives the offset, its plateau and band, the runner-up's score (a clear margin means the mapping is
frame-exact), and every freeze run with the change of the video frames around it, to check by eye.

    python -m ssbot.record.align_legacy C:\\ssbot\\data\\human\\20260930_005501 --out legacy.json [--cache sig.npz]
        [--dump map.npz]      (per video frame: pts and the matched STATE frame)
Nothing is written into the session folder. Decoding (OpenCV's FFmpeg, 1 thread by default) runs ~160 frames/s.
"""
import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2  # comes with windows-capture
import numpy as np
import zstandard

from ssbot.record import formats

GS_PLAYING = 4
STILL = 0.002       # share of thumbnail pixels changed by >= 3 levels below which a frame counts as still
P_STILL = 0.95      # P(still) for a pair predicted frozen


@dataclass
class LegacyStates:
    f: np.ndarray            # (R,) STATE frames, ascending
    q_ns: np.ndarray         # (R,) end of frame on the session's own clock, ns
    dt: np.ndarray           # (R,) Time.deltaTime (0 while frozen)
    gs: np.ndarray           # (R,) GameState (-1 without a GameManager)


def read_states(path: Path) -> LegacyStates:
    """STATE messages of a human session's state.raw.zst: bare wire frames in one zstd stream (tools/human_session)."""
    meta = json.loads((path / "meta.json").read_text("utf-8"))
    freq = (meta.get("hello") or {}).get("qpc_freq") or 10_000_000
    with (path / "state.raw.zst").open("rb") as fh:
        raw = zstandard.ZstdDecompressor().stream_reader(fh, read_across_frames=True).read()
    rows: dict[int, tuple] = {}
    mv = memoryview(raw)
    pos = 0
    while pos + 4 <= len(mv):
        n = int.from_bytes(mv[pos:pos + 4], "little")
        if pos + 4 + n > len(mv):
            break  # torn tail
        msg_type, _, flags, _, payload = formats.parse_frame(mv[pos:pos + 4 + n])
        pos += 4 + n
        if msg_type != 2:  # STATE
            continue
        s = formats.peek(payload, ("f", "q", "dt", "game"), flags)
        f, q = s.get("f"), s.get("q")
        if isinstance(f, int) and isinstance(q, int) and f not in rows:
            game = s.get("game") or {}
            rows[f] = (q * 1_000_000_000 // freq, float(s.get("dt") or 0.0), game.get("gs", -1))
    fs = sorted(rows)
    return LegacyStates(np.asarray(fs, np.int64), np.asarray([rows[f][0] for f in fs], np.int64),
                        np.asarray([rows[f][1] for f in fs]), np.asarray([rows[f][2] for f in fs], np.int64))


@dataclass
class VideoSignals:
    pts_ns: np.ndarray       # (N,) container timestamp, ns
    change: np.ndarray       # (N,) share of thumbnail pixels that changed by >= 3 levels since the previous frame
    luma: np.ndarray         # (N,) mean gray


def decode(video: Path, width: int = 160, threads: int = 1, progress=None) -> VideoSignals:
    """Decode every frame (OpenCV's FFmpeg, `threads` decoder threads) into per-frame change and brightness."""
    params = [cv2.CAP_PROP_N_THREADS, threads] if hasattr(cv2, "CAP_PROP_N_THREADS") else []
    cap = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG, params)
    if not cap.isOpened():
        raise OSError(f"cannot open {video}")
    pts, change, luma = [], [], []
    prev = size = None
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if size is None:
            h, w = img.shape[:2]
            size = (width, max(1, round(width * h / w)))
        g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), size, interpolation=cv2.INTER_AREA)
        pts.append(cap.get(cv2.CAP_PROP_POS_MSEC))
        change.append(1.0 if prev is None else float((cv2.absdiff(g, prev) >= 3).mean()))
        luma.append(float(g.mean()))
        prev = g
        if progress is not None and len(pts) % 5000 == 0:
            progress(len(pts))
    cap.release()
    return VideoSignals(np.round(np.asarray(pts) * 1e6).astype(np.int64), np.asarray(change), np.asarray(luma))


# ---- matching ------------------------------------------------------------------------------------------

def labels(st: LegacyStates, pts_ns: np.ndarray, offset: int) -> np.ndarray:
    """Row of the newest STATE frame with q_ns + offset <= pts, -1 if none (align.match on the legacy clocks)."""
    return np.searchsorted(st.q_ns + offset, pts_ns, side="right") - 1


def predictions(st: LegacyStates, pts_ns: np.ndarray, offset: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per video frame i (pair i - 1 -> i), gameplay only: predicted still, predicted changing, labels."""
    L = labels(st, pts_ns, offset)
    Lp = np.r_[-1, L[:-1]]
    Lc, Lpc = np.clip(L, 0, None), np.clip(Lp, 0, None)
    play = st.gs == GS_PLAYING
    g = (Lp >= 0) & play[Lc] & play[Lpc]
    adv = np.cumsum(st.dt > 0)
    advanced = adv[Lc] > adv[Lpc]
    still = g & ~advanced & (st.dt[Lpc] == 0)   # renders after two frozen updates: identical
    return still, g & advanced, L


def _signal(edges: np.ndarray, values: np.ndarray, t0: int, n: int) -> np.ndarray:
    """values[k] on [edges[k], edges[k + 1]) (ns) sampled on a 1 ms grid of n points from t0."""
    idx = np.clip((edges - t0) // 1_000_000, 0, n)
    out = np.zeros(n)
    out[:] = np.repeat(np.r_[0.0, values, 0.0], np.diff(np.r_[0, idx, n]))[:n]
    return out


def coarse(st: LegacyStates, vid: VideoSignals, guess: int, search_s: float) -> int:
    """Offset (ns, 1 ms resolution) maximizing the correlation of the advancing/frozen and changing/still signals."""
    play = st.gs == GS_PLAYING
    both = play[1:] & play[:-1]
    s_val = np.where(both, np.where(st.dt[1:] > 0, 1.0, np.where(st.dt[:-1] == 0, -1.0, 0.0)), 0.0)
    ns = int((st.q_ns[-1] - st.q_ns[0]) // 1_000_000) + 1
    s = _signal(st.q_ns, s_val, int(st.q_ns[0]), ns)
    v_val = np.where(vid.change[1:] < STILL, -1.0, 1.0)
    nv = int((vid.pts_ns[-1] - vid.pts_ns[0]) // 1_000_000) + 1
    v = _signal(vid.pts_ns, v_val, int(vid.pts_ns[0]), nv)
    n = 1 << int(np.ceil(np.log2(ns + nv)))
    xc = np.fft.irfft(np.conj(np.fft.rfft(s, n)) * np.fft.rfft(v, n), n)  # xc[m] = sum_k s[k] v[k + m]
    m = np.r_[np.arange(nv), np.arange(-ns, 0)]
    val = np.r_[xc[:nv], xc[n - ns:]]
    offs = int(vid.pts_ns[0]) - int(st.q_ns[0]) + m * 1_000_000   # s at q, v at q + offset
    inside = np.abs(offs - guess) <= search_s * 1e9
    return int(offs[inside][np.argmax(val[inside])])


@dataclass
class LegacyReport:
    path: str = ""
    states: int = 0
    video_frames: int = 0
    guess_ms: float | None = None          # from the first frames of both streams
    coarse_ms: float | None = None
    offset_ms: float | None = None         # q_ns + offset = pts_ns of the video frame that first shows it
    plateau_ms: list | None = None         # offsets sharing the best score: the right frame
    band_ms: list | None = None            # the part of the plateau with the fewest inconsistent labels: the phase
    score: float | None = None
    runner_up: float | None = None         # best score outside the plateau (another frame phase)
    still_pairs: list | None = None        # [correct, wrong] still predictions at offset_ms
    base_still: float | None = None        # share of still pairs among advancing gameplay pairs
    shared_labels: int = 0                 # video frames labelled like their predecessor at offset_ms
    inconsistent: int = 0                  # shared labels + labels skipping a frame the video did not skip
    freeze_runs: list = field(default_factory=list)   # [first frame, length, video changes x1000 around it]
    notes: list = field(default_factory=list)

    def format(self) -> str:
        lines = [f"{self.path}: STATE {self.states} frames, video {self.video_frames} frames",
                 f"offset (q_ns + offset = pts_ns): {self.offset_ms} ms; frame plateau {self.plateau_ms} ms, phase "
                 f"band {self.band_ms} ms (guess {self.guess_ms}, coarse {self.coarse_ms})",
                 f"score {self.score} vs runner-up {self.runner_up}; still pairs [correct, wrong] {self.still_pairs}; "
                 f"base still rate {self.base_still}; video frames sharing a label {self.shared_labels}, "
                 f"inconsistent labels {self.inconsistent}",
                 "freeze runs (first frame, length: label offset from the run start : change x1000; * = frozen):"]
        lines += [f"  f{r[0]} ({r[1]}): {r[2]}" for r in self.freeze_runs]
        lines += [f"note: {n}" for n in self.notes]
        return "\n".join(lines)


def _inconsistent(st: LegacyStates, pts_ns: np.ndarray, offset: int) -> int:
    """Video frames labelled like their predecessor, plus labels that skip a STATE frame while the video did not
    skip one (its step is under 1.5 STATE periods)."""
    L = labels(st, pts_ns, offset)
    period = float(np.median(np.diff(st.q_ns)))
    jump = np.diff(L)
    valid = L[1:] >= 0
    return int((valid & (jump == 0)).sum() + (valid & (jump >= 2) & (np.diff(pts_ns) < 1.5 * period)).sum())


def _run_at(mask: np.ndarray, i: int) -> tuple[int, int]:
    """First and last index of the run of True in mask that contains i."""
    lo, hi = i, i
    while lo > 0 and mask[lo - 1]:
        lo -= 1
    while hi < len(mask) - 1 and mask[hi + 1]:
        hi += 1
    return lo, hi


def find_offset(st: LegacyStates, vid: VideoSignals, search_s: float = 30.0, fine_ms: float = 100.0,
                step_ms: float = 0.25) -> LegacyReport:
    rep = LegacyReport(states=len(st.f), video_frames=len(vid.pts_ns))
    guess = int(vid.pts_ns[0]) - int(st.q_ns[0])
    rep.guess_ms = guess / 1e6
    c = coarse(st, vid, guess, search_s)
    rep.coarse_ms = c / 1e6
    obs = vid.change < STILL
    _, change, _ = predictions(st, vid.pts_ns, c)
    p0 = float(np.clip(obs[change].mean(), 0.01, 0.9)) if change.any() else 0.2
    rep.base_still = round(p0, 4)
    w_ok, w_bad = np.log(P_STILL / p0), np.log((1 - P_STILL) / (1 - p0))
    grid = c + np.round(np.arange(-fine_ms, fine_ms + step_ms / 2, step_ms) * 1e6).astype(np.int64)
    score = np.empty(len(grid))
    for k, off in enumerate(grid):
        s, _, _ = predictions(st, vid.pts_ns, int(off))
        score[k] = w_ok * (s & obs).sum() + w_bad * (s & ~obs).sum()
    top = score.max()
    best = score >= top - 1e-9
    runs = np.flatnonzero(np.diff(np.r_[0, best.astype(int), 0]) != 0).reshape(-1, 2)
    a, b = max(runs, key=lambda r: r[1] - r[0])
    rep.plateau_ms = [round(int(grid[a]) / 1e6, 3), round(int(grid[b - 1]) / 1e6, 3)]
    rep.score = round(float(top), 2)
    # Within the plateau (the right frame), the phase: consecutive video frames should show consecutive STATE frames.
    # Near a wrong phase, capture jitter makes labels repeat and skip; the count bottoms out (at the game's own
    # repeated frames) over the band where every frame is labelled right.
    bad = np.array([_inconsistent(st, vid.pts_ns, int(o)) for o in grid[a:b]])
    ok = bad <= bad.min() + max(2, 0.02 * bad.min())  # the valley floor is noisy by a few frames on real sessions
    lo_, hi_ = _run_at(ok, int(np.argmin(bad)))
    off = int((grid[a + lo_] + grid[a + hi_]) // 2)
    rep.offset_ms = round(off / 1e6, 3)
    rep.band_ms = [round(int(grid[a + lo_]) / 1e6, 3), round(int(grid[a + hi_]) / 1e6, 3)]
    outside = np.ones(len(grid), bool)
    edge = int(round(2.0 / step_ms))
    outside[max(0, a - edge):b + edge] = False  # the plateau and its 2 ms edges
    rep.runner_up = round(float(score[outside].max()), 2) if outside.any() else None
    if len(runs) > 1:
        starts = [round(int(grid[r]) / 1e6, 3) for r in runs[:, 0]]
        rep.notes.append(f"{len(runs)} separate plateaus share the best score, starting at {starts} ms")
    s, _, L = predictions(st, vid.pts_ns, off)
    rep.still_pairs = [int((s & obs).sum()), int((s & ~obs).sum())]
    rep.shared_labels = int(((L[1:] == L[:-1]) & (L[1:] >= 0)).sum())
    rep.inconsistent = int(bad.min())
    frozen = (st.gs == GS_PLAYING) & (st.dt == 0)
    for r0, r1 in np.flatnonzero(np.diff(np.r_[0, frozen.astype(int), 0]) != 0).reshape(-1, 2):
        i0, i1 = np.searchsorted(L, r0 - 2), np.searchsorted(L, r1 + 2)
        cells = " ".join(f"{st.f[L[i]] - st.f[r0]:+d}{'*' if frozen[L[i]] else ''}:{vid.change[i] * 1000:.0f}"
                         for i in range(i0, min(i1, len(L))))
        rep.freeze_runs.append([int(st.f[r0]), int(r1 - r0), cells])
    if rep.runner_up is not None and top - rep.runner_up < 10:
        rep.notes.append("weak margin over the next frame phase: the offset may be a frame off")
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.record.align_legacy", description=__doc__.split("\n")[0])
    ap.add_argument("session", help="human session folder (meta.json, state.raw.zst, video.mkv)")
    ap.add_argument("--out", help="write the report here (JSON); never into the session")
    ap.add_argument("--cache", help="video signals .npz: loaded if it exists, else written after decoding")
    ap.add_argument("--dump", help="per video frame pts_ns and matched STATE frame (.npz)")
    ap.add_argument("--search-s", type=float, default=30.0)
    ap.add_argument("--threads", type=int, default=1, help="decoder threads")
    a = ap.parse_args(argv)
    session = Path(a.session)
    for p in (a.out, a.cache, a.dump):
        if p and Path(p).resolve().is_relative_to(session.resolve()):
            ap.error(f"{p} is inside the session folder, which this tool only reads")
    st = read_states(session)
    if a.cache and Path(a.cache).is_file():
        z = np.load(a.cache)
        vid = VideoSignals(z["pts_ns"], z["change"], z["luma"])
    else:
        t0 = time.monotonic()
        vid = decode(session / "video.mkv", threads=a.threads,
                     progress=lambda n: print(f"  decoded {n} frames ({time.monotonic() - t0:.0f} s)", file=sys.stderr))
        if a.cache:
            np.savez(a.cache, pts_ns=vid.pts_ns, change=vid.change, luma=vid.luma)
    rep = find_offset(st, vid, a.search_s)
    rep.path = str(session)
    print(rep.format())
    if a.out:
        Path(a.out).write_text(json.dumps(asdict(rep), indent=1), encoding="utf-8")
    if a.dump:
        L = labels(st, vid.pts_ns, int(rep.offset_ms * 1e6))
        np.savez_compressed(a.dump, pts_ns=vid.pts_ns, state_f=np.where(L >= 0, st.f[np.clip(L, 0, None)], -1),
                            offset_ns=int(rep.offset_ms * 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
