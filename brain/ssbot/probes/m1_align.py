"""M1 probe: frame/label alignment (DESIGN §3.1.4 C4; M1 exit: alignment >= 99.5 %).

Records the oracle STATE stream (Recorder) and a WGC thumbnail video of the same instance's window (VideoRecorder)
into one episode folder while it drives Hornet with continuous-control ACTIONs: runs, stops, dashes and jumps of
random length, turning back towards the start whenever she gets more than --span units away. The camera then keeps
changing speed, which is what the aligner needs (a constant offset is invisible in constant motion). Afterwards it
checks STATE delivery and runs ssbot.record.align on the episode.

Needs the training copy running with SsOracle (`python -m ssbot.tools.launcher -n 1 --detach`, or without --detach in
a second terminal, since the launcher then waits for the game to exit; after a --detach run, quit the game and run
`python -m ssbot.tools.launcher --restore`), no other brain connected to that instance, and Hornet in a room where the
camera follows her horizontally with no enemies nearby (the Bonetown bench room of the sandbox save works; at the
title it loads save slot 1, which must hold a sandbox save: Enter on an empty slot starts a new game, m0:N30). No
focus needed (in-engine key injection), but the window must not be minimized (WGC stops delivering frames). It stops
driving early if the scene changes or the game leaves PLAYING.

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.m1_align                       # 60 s on instance 0
    ..\\scripts\\uv.cmd run python -m ssbot.probes.m1_align --seconds 300 --instance 1
    ..\\scripts\\uv.cmd run python -m ssbot.record.align <episode> --dump          # re-run the analysis later

Prints progress every 10 s, the continuity report, the alignment report (calibrated D per clock, offset histogram,
unjudged captures by cause, exclusions, anomalies, masked share, noise), writes align.json (with the verdict of both
clocks) into the episode and exits 0 only on PASS on the gate clock (--clock, default the WGC frame clock): >= 99.5 %
of the judgeable captures at offset 0, unjudged ones counting against it, with at least --min-informative judged
captures and --min-coverage of all. The analysis takes ~5 ms per capture at the default width (~20 s for 60 s).

Hornet and the HUD are masked out of the registration by the recorded STATE "hero" and "hud" (the camera keeps her
near the image centre, where she would pull every measured camera step towards 0), and so is anything else that keeps
its pixels while the image moves. Reading a FAIL:
    offsets -1 / +1       judged capture by capture: frames shown late / early; 1 - share estimates their share
    excursions            runs of captures out of step and back (stale captures, periodic judder); judged one by one
    unjudged no_window    nothing fits anywhere near: judder throughout (or the registration failed: see split)
    unjudged cut, breaks  latency steps (the offset changes and stays), or registration glitches that could not be
                          bridged (bridged captures were judged across glitches)
    unjudged split        the neighbours on the two sides disagree; many of them with few anomalies point at the
                          registration, not the timing: compare `python -m ssbot.record.align <episode> --no-mask`
"""
import argparse
import json
import random
import sys
import time
from datetime import datetime

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.probes.common import GS_PLAYING, in_gameplay, load_slot, stand_up
from ssbot.record import align
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
    ap.add_argument("--min-informative", type=int, default=align.Params.min_informative)
    ap.add_argument("--min-coverage", type=float, default=align.Params.min_coverage)
    ap.add_argument("--clock", choices=("frame", "arrival"), default=align.GATE_CLOCK,
                    help="gate clock (the other one is reported as a cross-check)")
    a = ap.parse_args()

    link = OracleLink(instance=a.instance)
    print("hello:", {k: link.hello.get(k) for k in ("plugin", "game", "instance", "qpc_freq")})
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
    stand_up(link)
    time.sleep(0.5)

    rec = Recorder(link, out_dir=a.out, profile="PROBE", episode=f"m1_align_{datetime.now():%H%M%S}_i{a.instance}",
                   game_dir=a.game_dir, config={"probe": "m1_align", "seconds": a.seconds, "seed": a.seed,
                                                "span": a.span, "width": a.width}).start()
    vid = None

    def progress(s: dict) -> None:
        print(f"  t+{time.monotonic() - t0:5.0f} s  frame {s['f']}  STATE {rec.states} (drops {rec.dropped['state']})"
              f"  captures {vid.pushed} (drops {vid.dropped})  hero x {s['hero']['pos'][0]:.2f}")

    why = "error"
    try:  # a failing video start still releases the input and closes the recording and the link
        vid = VideoRecorder(rec.path, hwnd=hwnd, width=a.width).start()
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
        vsum = vid.close() if vid is not None else None
        rsum = rec.close()
        link.close()
    print(f"stopped driving: {why}")
    print(f"video: {vsum}")
    cont = RecordingReader(rec.path).check(deep=True)
    print("\n" + cont.format())
    print(f"recorder drops {rsum['drops']}; error {rsum['error']}")

    print("\n== alignment ==")
    rep, *_ = align.align_episode(rec.path, align.Params(min_informative=a.min_informative,
                                                         min_coverage=a.min_coverage), a.clock,
                                  progress=lambda n: print(f"  registered {n} captures"))
    print(rep.format())
    (rec.path / "align.json").write_text(json.dumps(rep.as_dict(), indent=1), encoding="utf-8")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
