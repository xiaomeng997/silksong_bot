"""M1 probe: frame/label alignment gate (DESIGN §3.1.4 C4; M1 exit: alignment >= 99.5 %, measured against ground truth).

A training session as every training session runs it: it turns the oracle's frame marker on (marker_on: RPC
"frame.marker" in the vision mask's corner with its cell, profile TRAIN only), so that every rendered image carries
the number of its frame (ssbot.record.marker), records the oracle STATE stream (Recorder) and a WGC thumbnail video of
the same instance's window (VideoRecorder marker=True: the marker read from each full-resolution capture, then masked
before the thumbnail is made) into one episode folder while it drives Hornet with continuous-control ACTIONs (runs,
stops, dashes and jumps of random length, turning back towards the start whenever she gets more than --span units
away), and turns the marker off again at the end, also after an error (and the oracle turns it off by itself if the
link drops).

Afterwards it checks STATE delivery and reports the exact gate from the decoded markers in the video index: the share
of the judged captures (the marker drawn around their label) that carry their marker label (PASS >= 99.5 %; a capture
whose marker did not decode although it was drawn falls back to its timestamp label and counts against it); the
label sources; the timestamp labels against the truth on the gate clock and the other one (offset of every capture's
decoded frame from its timestamp label after the constant-offset calibration D, the share at offset 0: what an
unmarked session's labels are worth); duplicates and skips. Then it runs the camera-trajectory monitor
(ssbot.record.align), which sessions without the marker rely on, and scores it capture by capture against the truth:
false aligned and false misaligned rates, and how many truly misaligned captures it flagged or could not see. The
drive keeps the camera changing speed, which the monitor needs (a constant offset is invisible in constant motion);
the marker does not.

Needs the training copy running with SsOracle (`python -m ssbot.tools.launcher -n 1 --detach`, or without --detach in
a second terminal, since the launcher then waits for the game to exit; after a --detach run, quit the game and run
`python -m ssbot.tools.launcher --restore`), in profile TRAIN (probe tools allowed), no other brain connected to that
instance, and Hornet in a room where the camera follows her horizontally with no enemies nearby (the Bonetown bench
room of the sandbox save works; at the title it loads save slot 1, which must hold a sandbox save: Enter on an empty
slot starts a new game, m0:N30). No focus needed (in-engine key injection), but the window must not be minimized (WGC
stops delivering frames). It stops driving early if the scene changes or the game leaves PLAYING.

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.m1_align                       # 60 s on instance 0
    ..\\scripts\\uv.cmd run python -m ssbot.probes.m1_align --seconds 300 --instance 1
    ..\\scripts\\uv.cmd run python -m ssbot.record.marker <episode> --monitor     # re-run the analysis later
    ..\\scripts\\uv.cmd run python -m ssbot.record.align <episode> --dump         # the monitor alone

The marker's cells are the vision mask's (ssbot.vision.mask.cell_px: 3 px at 720p, 4 at 1080p) in its corner (top
right); the thumbnails never show it. Prints progress every 10 s, the continuity report (with the video's label
sources), the monitor's report (calibrated D per clock, offset histogram, unjudged captures by cause, exclusions,
anomalies, masked share, registration scale by camera speed, split locations, noise) and then the exact report with
the monitor's score; writes marker.json (exact report and score), align.json (the monitor), align_frames.npz
(per-capture arrays, with the decoded truth as truth_f / truth_k) and labels.npz (per capture: label frame and source)
into the episode and exits 0 only on the gate's PASS, with at least --min-captures judged captures. --clock (default
the WGC frame clock) is the timestamp labels' clock. The monitor takes ~6 ms per capture at the default width.

Reading the exact report: "missing" markers fall back to timestamp labels and count against the gate (look at the
decode statuses: "absent" in every capture means the marker is not where the mask expects it, e.g. a client crop far
off or a client size that is not the game's screen); offsets -1 / +1 of the timestamp labels are captures showing the
frame before / after their label (late / early); duplicates are captures that repeat the frame before them, skipped
frames are frames no capture shows; lag is the capture time minus the end of the frame it shows.

Reading the monitor's score: "false aligned" (judged at 0, truly off) must stay 0; "false misaligned" and truly
aligned captures among its unjudged ones (mixed, split, cut, no_window) are what it costs aligned recordings; truly
misaligned captures among its left-out ones (uninformative, low_motion) are what it cannot see. Its limits are in the
ssbot.record.align docstring: parallax that makes the registered scale depend on the camera speed shows as mixed and
split captures that are truly aligned.

In-game runs: record in docs/facts/<version>/probes.md the gate (marker share, missing markers and their decode
status, the capture path's decode + mask cost from video.json), the timestamp labels (share, histogram, D per clock,
lag), duplicates and skips, the monitor's score (false aligned / false misaligned rates, unjudged and left-out
captures by truth), its registration scale against the camera speed (scale_by_speed) and where its splits fall
(split_at), with the layers the room shows; keep marker.json, align.json, align_frames.npz and labels.npz. The
monitor's parameters (drift, scale_tol, window, decisive) are to be tuned on such recordings.
"""
import argparse
import json
import random
import sys
import time
from datetime import datetime

import numpy as np

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.probes.common import GS_PLAYING, in_gameplay, load_slot, stand_up
from ssbot.record import align, marker
from ssbot.record.recorder import DEFAULT_OUT, Recorder, RecordingReader
from ssbot.record.video import DEFAULT_WIDTH, VideoRecorder, instance_window

LEAD = 2  # ACTION target frames ahead of the newest STATE


class Pattern:
    """Buttons for each frame: segments of 10-70 frames that run left or right (or stand, 1 in 5), start with a dash
    tap now and then, and hold jump for a random 4-18 frames (variable height) now and then. Hornet is steered back
    once she is `span` units from where she started, so she stays in the room."""

    def __init__(self, seed: int = 0, span: float = 6.0):
        self.rng = random.Random(seed)
        self.span = span
        self.x0: float | None = None
        self.left = 0
        self.dir = 0
        self.jump = 0
        self.dash = 0

    def next(self, x: float) -> int:
        if self.x0 is None:
            self.x0 = x
        off = x - self.x0
        if self.left <= 0:
            self.left = self.rng.randint(10, 70)
            self.dir = 0 if self.rng.random() < 0.2 else self.rng.choice((-1, 1))
            if abs(off) > self.span / 2 and self.dir * off > 0:
                self.dir = -self.dir
            if self.dir and self.rng.random() < 0.25:
                self.dash = 2
            if self.rng.random() < 0.35:
                self.jump = self.rng.randint(4, 18)
        if abs(off) > self.span and self.dir * off >= 0:
            self.dir = -1 if off > 0 else 1  # too far: head back now
        self.left -= 1
        buttons = []
        if self.dir:
            buttons.append("right" if self.dir > 0 else "left")
        if self.jump > 0:
            buttons.append("jump")
            self.jump -= 1
        if self.dash > 0:
            buttons.append("dash")
            self.dash -= 1
        return mask(*buttons)


def drive(link: OracleLink, seconds: float, pattern: Pattern, progress) -> str:
    """Continuous control (hold_frames 0) for every new STATE; returns why it stopped."""
    s = link.wait_state()
    scene = s["game"]["scene"]
    last = s["f"]
    end = time.monotonic() + seconds
    next_report = time.monotonic() + 10
    while time.monotonic() < end:
        s = link.wait_state(newer_than=last, timeout_s=2)
        last = s["f"]
        game, hero = s.get("game") or {}, s.get("hero")
        if game.get("gs") != GS_PLAYING or hero is None:
            return f"left PLAYING (gs {game.get('gs')})"
        if game.get("scene") != scene:
            return f"scene changed to {game.get('scene')}"
        link.act(last + LEAD, pattern.next(hero["pos"][0]))
        if time.monotonic() >= next_report:
            progress(s)
            next_report += 10
    return "time"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--game-dir", default=r"C:\ssbot\game\train")
    ap.add_argument("--no-load", action="store_true", help="do not navigate menus; require gameplay")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="thumbnail width (px)")
    ap.add_argument("--span", type=float, default=6.0, help="units Hornet may stray from her start x")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--min-captures", type=int, default=1000, help="judged captures the gate needs")
    ap.add_argument("--min-informative", type=int, default=align.Params.min_informative)
    ap.add_argument("--min-coverage", type=float, default=align.Params.min_coverage)
    ap.add_argument("--clock", choices=("frame", "arrival"), default=align.GATE_CLOCK,
                    help="the timestamp labels' clock (the other one is reported as a cross-check)")
    a = ap.parse_args()

    link = OracleLink(instance=a.instance)
    print("hello:", {k: link.hello.get(k) for k in ("plugin", "game", "instance", "qpc_freq")})
    if "frame.marker" not in (link.hello.get("rpcs") or []):
        print("FAIL: this oracle has no frame.marker RPC (rebuild and deploy SsOracle)")
        return 1
    hwnd = instance_window(a.instance)
    if not hwnd:
        print(f"FAIL: no game window owns port of instance {a.instance}")
        return 1
    s = link.wait_state(timeout_s=10)
    if not in_gameplay(s):
        if a.no_load:
            print("FAIL: not in gameplay and --no-load given")
            return 1
        print("not in gameplay: loading save slot 1 from the title")
        load_slot(link, 1)
    s = stand_up(link)
    time.sleep(0.5)

    try:
        print("frame marker:", marker.marker_on(link))
    except (OracleError, TimeoutError) as e:
        print(f"FAIL: frame marker not on ({e}); the gate needs it (profile TRAIN, not -ssbot-human)")
        try:
            marker.marker_off(link)
        except (OracleError, TimeoutError, OSError):
            pass
        link.close()
        return 1

    rec = vid = None
    why = "error"
    t0 = time.monotonic()

    def progress(s: dict) -> None:
        print(f"  t+{time.monotonic() - t0:5.0f} s  frame {s['f']}  STATE {rec.states} (drops {rec.dropped['state']})"
              f"  captures {vid.pushed} (drops {vid.dropped})  hero x {s['hero']['pos'][0]:.2f}  marker "
              f"{'on' if (s.get('mk') or {}).get('drawn') else 'OFF'}")

    vsum = rsum = None
    try:  # a failing start still releases the input, closes the recording and turns the marker off
        rec = Recorder(link, out_dir=a.out, profile="PROBE", episode=f"m1_align_{datetime.now():%H%M%S}_i{a.instance}",
                       game_dir=a.game_dir, config={"probe": "m1_align", "seconds": a.seconds, "seed": a.seed,
                                                    "span": a.span, "width": a.width, "marker": True}).start()
        vid = VideoRecorder(rec.path, hwnd=hwnd, width=a.width, marker=True, states=lambda: link.state).start()
        print(f"recording {a.seconds:.0f} s -> {rec.path} (window {hwnd:#x})")
        t0 = time.monotonic()
        why = drive(link, a.seconds, Pattern(a.seed, a.span), progress)
    except (TimeoutError, OracleError) as e:
        why = f"error: {e}"
    except KeyboardInterrupt:
        why = "interrupted"
    finally:
        try:
            link.rpc("input.release")
        except (OracleError, TimeoutError, OSError) as e:
            print(f"input.release failed: {e}")
        time.sleep(0.5)  # a last stretch of both streams with the camera settling
        try:
            vsum = vid.close() if vid is not None else None
            rsum = rec.close() if rec is not None else None
        finally:
            try:
                print("frame marker:", marker.marker_off(link))
            except (OracleError, TimeoutError, OSError) as e:
                print(f"frame marker off failed ({e}); it goes off when the link closes")
            link.close()
    print(f"stopped driving: {why}")
    if rec is None:
        return 1
    print(f"video: {vsum}")
    cont = RecordingReader(rec.path).check(deep=True)
    print("\n" + cont.format())
    print(f"recorder drops {rsum['drops']}; error {rsum['error']}")

    print("\n== exact alignment (frame marker) ==")
    xrep, arrays, tr = marker.exact_episode(rec.path, a.clock, min_captures=a.min_captures)
    print("\n== monitor (camera trajectory) ==")
    mrep, off, mot, trk = marker.monitor_against_truth(
        rec.path, xrep, arrays, align.Params(min_informative=a.min_informative, min_coverage=a.min_coverage), a.clock,
        progress=lambda n: print(f"  registered {n} captures"))
    print(mrep.format())
    (rec.path / "align.json").write_text(json.dumps(mrep.as_dict(), indent=1), encoding="utf-8")
    if off is not None:
        shown = arrays["shown"]
        truth_k = np.where((shown >= 0) & (off.label >= 0), shown - trk.f[np.clip(off.label, 0, None)], 0)
        align.dump(rec.path / "align_frames.npz", off, mot, trk, truth_f=shown, truth_k=truth_k)
    print("\n== gate ==")
    print(xrep.format())
    (rec.path / "marker.json").write_text(json.dumps(xrep.as_dict(), indent=1), encoding="utf-8")
    lb = marker.capture_labels(tr, a.clock, xrep.primary.D_ms)
    np.savez_compressed(rec.path / "labels.npz", seq=lb.seq, frame=lb.frame, source=lb.source,
                        sources=np.asarray(marker.LABEL_SOURCES))
    return 0 if xrep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
