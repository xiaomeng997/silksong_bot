"""M1 harness-input probe: savestates, randomized starts, InputPathEmulator delay, minimum hold, brain-lost pause,
legacy anyKeyDown shim (oracle/src/Input, oracle/src/Train).

Needs: the training copy running with SsOracle (InputModule + TrainModule installed) and DebugMod, a sandbox save
loaded, Hornet standing in a quiet room (GameState PLAYING, no enemies nearby: the probe jumps and attacks for a few
seconds).

    cd brain
    uv run python -m ssbot.probes.m1_harness                      # savestate x10, randomize, latency, min hold,
                                                                  #   streamed taps under the 2/3/4 latency prior
    uv run python -m ssbot.probes.m1_harness --lost               # + brain-lost Pause tap (pauses, then unpauses;
                                                                  #   the tap lands alone, also right after a press)
    uv run python -m ssbot.probes.m1_harness --cutscene 120       # + legacy shim: waits up to 120 s for a CUTSCENE
                                                                  #   (ride a Bellway or start a skippable cutscene
                                                                  #   by hand), then taps jump and expects the skip
Options: --instance N, --name STATE (savestate name, default m1_probe), --reps N, --only SECTION[,SECTION].
Prints PASS/FAIL per check (an RPC error or timeout fails its section and the probe moves on) and exits 1 on any
FAIL. Leaves the latency model at 0 and releases every key.

The savestate RPCs take {name}; OracleLink.rpc's own first parameter is called `name`, so this probe sends the
accepted alias {state} instead.

The PlayMaker AnyKey site of the legacy shim (ActionHelpers.AnyKeyDown) is only exercised when an FSM with an AnyKey
or WaitAnyKey action runs; the hello and cutscene sections print its injected_hits.
"""
import argparse
import random
import statistics
import sys
import time

import msgpack

from ssbot.ipc.framing import HEADER, MsgType, mask
from ssbot.ipc.oracle_link import OracleError, OracleLink

PLAYING, CUTSCENE = 4, 7  # GlobalEnums.GameState
REQUIRED_RPCS = ("savestate.save", "savestate.load", "savestate.list", "randomize_start",
                 "input.latency_model", "input.stats", "input.release")
RESET_BUDGET_MS = 2000
LATENCY_PRIOR = [[2, 0.3], [3, 0.5], [4, 0.2]]  # DESIGN §3.9.2 loopback prior
# ACTION targets this many frames past the newest STATE seen, so a STATE that lags a few frames behind the game
# cannot make an ACTION arrive after its target.
LEAD = 8

failures: list[str] = []


def check(ok: bool, what: str) -> bool:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)
    return ok


def run_section(link: OracleLink, title: str, fn, *args) -> None:
    """Run one section; an RPC error or timeout is a FAIL of that section, not a traceback."""
    print("== " + title)
    try:
        fn(link, *args)
    except (OracleError, TimeoutError) as e:
        check(False, f"{title}: aborted by {type(e).__name__}: {e}")
        try:
            link.rpc("input.release")
        except (OracleError, TimeoutError, OSError):
            pass


class MaskRecorder:
    """act.mask of every STATE (not just the newest one polled), by frame, while recording."""

    def __init__(self, link: OracleLink):
        self.masks: dict[int, int] = {}
        self.on = True
        link.subscribe_raw(self._on_raw)

    def _on_raw(self, msg_type: int, raw: bytes) -> None:
        if self.on and msg_type == MsgType.STATE:
            st = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
            self.masks[st["f"]] = st["act"]["mask"]

    def stop(self) -> None:
        self.on = False


def runs(seq: list[int], bit: int) -> list[tuple[int, int]]:
    """(start index, length) of every run of consecutive entries with `bit` set."""
    out, i = [], 0
    while i < len(seq):
        if seq[i] & bit:
            j = i
            while j < len(seq) and seq[j] & bit:
                j += 1
            out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


def section_hello(link: OracleLink) -> None:
    rpcs = set(link.hello.get("rpcs", ()))
    missing = [r for r in REQUIRED_RPCS if r not in rpcs]
    check(not missing, f"HELLO lists the harness RPCs (missing: {missing or 'none'})")
    flags = link.hello.get("action_flags")
    check(flags == ["exclusive"], f"HELLO action_flags {flags} (the EXCLUSIVE oracle; an older DLL has no such key)")
    stats = link.rpc("input.stats")
    check("released_early" in stats["hold"], f"input.stats hold.released_early present ({stats['hold'].get('released_early')})")
    legacy = stats["legacy"]
    check(legacy["sites_patched"] == legacy["sites_expected"],
          f"legacy anyKeyDown shim: {legacy['sites_patched']}/{legacy['sites_expected']} call sites patched")
    for site, info in legacy["sites"].items():
        print(f"     {site}: patched={info['patched']} injected_hits={info['injected_hits']}")


def load(link: OracleLink, name: str) -> tuple[dict, float]:
    t0 = time.perf_counter()
    res = link.rpc("savestate.load", timeout_s=40, state=name, timeout=30)
    return res, (time.perf_counter() - t0) * 1000


def section_savestate(link: OracleLink, name: str, reps: int) -> None:
    saved = link.rpc("savestate.save", state=name)
    print(f"     saved '{name}': {saved['scene']} pos {fmt(saved['pos'])} hp {saved['hp']} silk {saved['silk']} "
          f"-> {saved['path']} ({saved['bytes']} B, {saved['ms']} ms)")
    listed = link.rpc("savestate.list")
    names = [s["name"] for s in listed["states"]]
    check(name in names, f"savestate.list contains '{name}' ({len(names)} own, {len(listed['debugmod'])} DebugMod slots)")

    oracle_ms, wall_ms = [], []
    for i in range(reps):
        # Move away first so every load has something to undo.
        link.rpc("randomize_start", seed=1000 + i, dx=[-2, 2], facing="random")
        res, wall = load(link, name)
        oracle_ms.append(res["ms"])
        wall_ms.append(wall)
        s = link.wait_state(lambda s: s["game"]["gs"] == PLAYING and s["game"]["entered"], timeout_s=5)
        dpos = max(abs(a - b) for a, b in zip(res["pos"], saved["pos"]))
        print(f"     load {i + 1:2d}: {res['ms']:5d} ms oracle (DebugMod {res['dm_ms']} ms, settle {res['settle_ms']} ms, "
              f"{res['frames']} frames), {wall:6.1f} ms wall, scene {res['scene']}, |dpos| {dpos:.3f}, "
              f"hero_input {res['hero_input']}, safe_loading {res['safe_loading']}, STATE f{s['f']}")
        if dpos > 0.5:
            check(False, f"load {i + 1} restored the saved position (|dpos| {dpos:.3f})")
        if res.get("death_reset"):
            check(False, f"load {i + 1} reset over a dead hero")
    print(f"     reset time p50 {statistics.median(oracle_ms):.0f} ms, max {max(oracle_ms)} ms (oracle); "
          f"wall p50 {statistics.median(wall_ms):.0f} ms, max {max(wall_ms):.0f} ms")
    check(max(wall_ms) <= RESET_BUDGET_MS, f"reset <= {RESET_BUDGET_MS} ms over {reps} loads (max wall {max(wall_ms):.0f} ms)")


def section_randomize(link: OracleLink, name: str) -> None:
    args = dict(hp=[1, 5], silk=[0, 9], dx=[-3, 3], facing="random", wait_frames=[0, 30])
    applied = {}
    for seed in (1, 2, 3, 1):
        load(link, name)
        r = link.rpc("randomize_start", timeout_s=20, seed=seed, **args)
        key = (r["hp"], r["silk"], round(r["dx"], 4), r["facing"], r["wait_frames"])
        print(f"     seed {seed}: hp {r['hp_before']}->{r['hp']} silk {r['silk_before']}->{r['silk']} "
              f"dx {r['dx_requested']:+.2f}->{r['dx']:+.2f} (dy {r['dy']:+.2f}, {r['dx_tries']} tries, {r['dx_note']}) "
              f"facing {r['facing']} wait {r['wait_frames']} f{r['frame_applied']}->f{r['frame_done']} | "
              f"now pos {fmt(r['pos'])} vel {fmt(r['vel'])} ground {r['on_ground']} hp {r['hp_now']} silk {r['silk_now']}")
        check(r["frame_done"] - r["frame_applied"] >= r["wait_frames"], f"seed {seed}: waited {r['wait_frames']} frames")
        if seed in applied:
            check(applied[seed] == key, f"seed {seed} reproduces the same start {key}")
        applied[seed] = key
    check(len(set(applied.values())) > 1, "different seeds give different starts")
    try:
        link.rpc("randomize_start", seed=1, facing="up")
        check(False, "bad facing rejected")
    except OracleError as e:
        check(True, f"bad facing rejected ({e})")


def act_and_wait(link: OracleLink, target: int, buttons: int, ack: int, hold: int = 0, release: bool = True) -> dict:
    """Send one ACTION and wait for the STATE that acknowledges it. With `release`, stop driving right after (the
    keys pressed keep their minimum press; only queued edges are dropped), so the probe never idles while driving:
    250 ms without an ACTION would count as brain lost and tap Pause."""
    link.act(target, buttons, hold_frames=hold, ack_seq=ack)
    try:
        return link.wait_state(lambda s: s["act"]["ack"] == ack, timeout_s=2)
    finally:
        if release:
            link.rpc("input.release")


def section_latency(link: OracleLink) -> None:
    try:
        link.rpc("input.latency_model", delay_frames=3, jitter_frames=0, seed=0)
        f = link.frame + LEAD
        s = act_and_wait(link, f, 0, 9001)
        check(s["act"]["target"] == f and s["act"]["applied"] == f + 3,
              f"delay 3: ACTION target {f} applied at {s['act']['applied']} (expected {f + 3})")

        link.rpc("input.latency_model", delay_frames=3, jitter_frames=1, seed=5)
        lags = []
        for i in range(12):
            f = link.frame + LEAD
            s = act_and_wait(link, f, 0, 9100 + i)
            lags.append(s["act"]["applied"] - s["act"]["target"])
        check(set(lags) <= {2, 3, 4}, f"delay 3 jitter 1: applied - target = {lags} (all in 2..4)")

        link.rpc("input.latency_model", delay_frames=0, jitter_frames=0, seed=0, dist=LATENCY_PRIOR)
        model = link.rpc("input.latency_model")
        print(f"     dist model: {model}")
    finally:
        res = link.rpc("input.latency_model", delay_frames=0, jitter_frames=0, seed=0)
    check(res["delay_frames"] == 0 and "dist" not in res, "latency model back to 0 frames")
    f = link.frame + LEAD
    s = act_and_wait(link, f, 0, 9200)
    check(s["act"]["applied"] == f, f"delay 0: target {f} applied at {s['act']['applied']}")


def section_min_hold(link: OracleLink) -> None:
    """A 1-frame jump request must be latched for exactly 2 frames (C19 / m0:N37)."""
    rec = MaskRecorder(link)
    before = link.rpc("input.stats")["hold"]["holds_extended"]
    jump = mask("jump")
    f = link.frame + LEAD
    act_and_wait(link, f, jump, 9300, hold=1)  # released right after the ack: the 2-frame press must still happen
    link.wait_state(lambda s: s["f"] > f + 6, timeout_s=2)
    rec.stop()
    after = link.rpc("input.stats")["hold"]["holds_extended"]
    frames = sorted(k for k, m in rec.masks.items() if m & jump and f - 1 <= k <= f + 6)
    check(len(frames) == 2 and frames[1] == frames[0] + 1,
          f"1-frame jump latched for frames {frames} (expected 2 consecutive)")
    check(after == before + 1, f"input.stats hold.holds_extended {before} -> {after}")


def tap_pattern(seed: int, frames: int, tail: int) -> list[int]:
    """Per key (jump, attack): a press of 1-2 frames, then a gap of 3-6 frames (a 2/2-frame filter needs 4 frames per
    tap, so this never builds a backlog); `tail` idle frames at the end so every tap has played out before the stream
    stops. Same shape as TapPattern in oracle/tests/InputLogicCheck."""
    rng = random.Random(seed)
    masks = [0] * (frames + tail)
    for bit in (mask("jump"), mask("attack")):
        t = rng.randrange(0, 6)
        while t < frames:
            n = rng.randint(1, 2)
            for i in range(t, min(frames, t + n)):
                masks[i] |= bit
            t += n + rng.randint(3, 6)
    return masks


def section_stream(link: OracleLink, seconds: float = 4.0) -> None:
    """Minimum hold with the latency prior on: one ACTION per frame carrying 1- and 2-frame taps. Every requested press
    must reach the game (act.mask) for >= min_press_frames, with >= min_release_frames up before a re-press, even when
    the sampled delays bunch several ACTIONs into one frame."""
    frames, tail = int(seconds * 60), 30
    pattern = tap_pattern(7, frames, tail)
    total = len(pattern)
    rec = MaskRecorder(link)
    try:
        model = link.rpc("input.latency_model", delay_frames=0, jitter_frames=0, seed=7, dist=LATENCY_PRIOR)
        before = link.rpc("input.stats")
        base = link.frame + LEAD
        sent, last = 0, link.frame
        while sent < total:
            s = link.wait_state(newer_than=last, timeout_s=2)
            last = s["f"]
            while sent < total and base + sent <= last + LEAD:
                link.act(base + sent, pattern[sent], ack_seq=20000 + sent)
                sent += 1
        # The idle tail is longer than LEAD + the largest delay + the hold backlog, so every tap has been latched
        # and released by now; stop driving before the watchdog could see a pause in the stream.
        link.rpc("input.release")
        link.wait_state(lambda s: s["f"] >= base + total, timeout_s=5)
    finally:
        rec.stop()
        link.rpc("input.latency_model", delay_frames=0, jitter_frames=0, seed=0)
    after = link.rpc("input.stats")

    span = range(base, base + total)
    seen = [rec.masks.get(k) for k in span]
    gaps = sum(m is None for m in seen)
    if not check(gaps == 0, f"stream: STATE received for all {total} frames (missing {gaps})"):
        return
    stale = after["stale"] - before["stale"]
    check(stale == 0, f"stream: all {total} ACTIONs arrived before they went stale (stale {stale}; the probe lagged if not)")
    min_press = model["min_press_frames"]
    min_release = model["min_release_frames"]
    for key in ("jump", "attack"):
        bit = mask(key)
        asked, got = runs(pattern, bit), runs(seen, bit)
        short = [r for r in got if r[1] < min_press]
        close = [(a, b) for a, b in zip(got, got[1:]) if b[0] - (a[0] + a[1]) < min_release]
        lags = [g[0] - a[0] for a, g in zip(asked, got)]
        check(len(got) == len(asked) and not short and not close,
              f"stream {key}: {len(asked)} presses requested (1-2 frames), {len(got)} latched, "
              f"shorter than {min_press} frames: {short}, re-pressed within {min_release}: {close}, "
              f"lag {min(lags, default=0)}..{max(lags, default=0)} frames")
    hb, ha = before["hold"], after["hold"]
    check(ha["taps_collapsed"] == hb["taps_collapsed"],
          f"stream: no tap collapsed (taps_collapsed {hb['taps_collapsed']} -> {ha['taps_collapsed']}); "
          f"coalesced ACTIONs {after['coalesced'] - before['coalesced']}, "
          f"holds_extended +{ha['holds_extended'] - hb['holds_extended']}, "
          f"presses_deferred +{ha['presses_deferred'] - hb['presses_deferred']}")


def pause_landing(rec: MaskRecorder, after: int) -> tuple[int | None, int | None]:
    """(frame, latched mask) of the first recorded frame after `after` with Pause latched: the frame the tap lands."""
    bit = mask("pause")
    for f in sorted(k for k in rec.masks if k > after):
        if rec.masks[f] & bit:
            return f, rec.masks[f]
    return None, None


def wait_pausable(link: OracleLink) -> None:
    s = link.wait_state(lambda s: s["game"]["gs"] == PLAYING, timeout_s=5)
    if s["pause"]["blk"] != 0:
        print(f"     pause blockers {s['pause']['blk']} set; waiting for them to clear")
        link.wait_state(lambda s: s["pause"]["blk"] == 0, timeout_s=10)


def unpause_continue(link: OracleLink, ack: int) -> dict:
    """Continue + Submit once the menu has faded in (DESIGN §3.7.5: an Esc may be handled twice). Released right
    after the ack: idling while driving would re-arm the watchdog and tap Pause again."""
    time.sleep(1.0)
    act_and_wait(link, link.frame + 1, mask("enter"), ack, hold=2)
    return link.wait_state(lambda s: not s["game"]["paused"], timeout_s=3)


def section_lost(link: OracleLink) -> None:
    """Brain-lost: stop sending ACTIONs while driving -> keys released, one Pause tap. With the EXCLUSIVE oracle
    (HELLO action_flags) the tap is QueueExclusiveCutAll: the frame it lands on latches Pause and nothing else."""
    wait_pausable(link)
    before = link.rpc("input.stats")
    rec = MaskRecorder(link)
    # Continuous control with a key down (Down: looks down, moves nothing) arms the watchdog; a bare release would
    # not. Then go quiet while driving: the oracle must let go of Down and tap Pause.
    s0 = act_and_wait(link, link.frame + 1, mask("down"), 9400, release=False)
    t0 = time.monotonic()
    s = link.wait_state(lambda s: s["act"]["lost"], timeout_s=3)
    print(f"     act.lost after {(time.monotonic() - t0) * 1000:.0f} ms (frame {s['f']})")
    try:
        released = link.wait_state(lambda s: s["act"]["mask"] == 0, timeout_s=0.5)["f"]
    except TimeoutError:
        released = None
    check(released is not None, f"brain lost -> held keys released (latched mask 0 at frame {released})")
    s = link.wait_state(lambda s: s["game"]["paused"], timeout_s=3)
    after = link.rpc("input.stats")
    rec.stop()
    check(s["game"]["paused"] and after["lost_pause_taps"] == before["lost_pause_taps"] + 1,
          f"brain lost -> game paused with {after['lost_pause_taps'] - before['lost_pause_taps']} tap(s) "
          f"(lost_events {before['lost_events']} -> {after['lost_events']})")
    f_p, m_p = pause_landing(rec, s0["f"])
    check(f_p is not None and m_p == mask("pause"),
          f"brain lost -> the Pause tap lands alone (frame {f_p}, latched 0x{m_p or 0:x}, Pause 0x{mask('pause'):x})")
    s = unpause_continue(link, 9401)
    check(not s["game"]["paused"] and not s["act"]["lost"], "unpaused by an ACTION (Continue); brain no longer lost")


def section_lost_late(link: OracleLink, reps: int = 8) -> None:
    """Brain-lost right after a fresh press: the last ACTION presses Up a few frames before the watchdog fires (Up:
    looks up, moves nothing). The old tap (ReleaseAllNow) kept such a key for its minimum press, so it could share
    the Pause frame; QueueExclusiveCutAll cuts it (input.stats hold.released_early counts it when it had latched
    for fewer than the minimum press frames). The lead before the watchdog is swept, since the watchdog fires on
    wall time (250 ms after the last ACTION's arrival) and the frame rate varies."""
    pause, up = mask("pause"), mask("up")
    s = link.wait_state(timeout_s=2)
    f_a, t_a = s["f"], time.monotonic()
    s = link.wait_state(lambda s: s["f"] >= f_a + 30, timeout_s=3)
    fps = (s["f"] - f_a) / (time.monotonic() - t_a)
    base = max(1, round(0.25 * fps) - 3)
    print(f"     ~{fps:.0f} fps: last ACTION's Up at +{base}..+{base + 3} frames after its arrival")
    alone, cut_gap1, gaps = 0, 0, []
    early0 = link.rpc("input.stats")["hold"]["released_early"]
    for i in range(reps):
        wait_pausable(link)
        lead = base + i % 4
        rec = MaskRecorder(link)
        s0 = act_and_wait(link, link.frame + 1, mask("down"), 9600 + 2 * i, release=False)
        link.act(link.frame + lead, up, ack_seq=9601 + 2 * i)       # then quiet
        link.wait_state(lambda s: s["game"]["paused"], timeout_s=3)
        time.sleep(0.1)
        rec.stop()
        f_p, m_p = pause_landing(rec, s0["f"])
        ups = sorted(f for f, m in rec.masks.items() if m & up and f > s0["f"])
        gap = f_p - ups[0] if ups and f_p is not None else None
        gaps.append(gap)
        ok = f_p is not None and m_p == pause
        alone += ok
        cut_gap1 += ok and gap == 1
        print(f"     rep {i}: lead +{lead}, Up latched {ups[:4]}{'...' if len(ups) > 4 else ''}, Pause lands f{f_p} "
              f"latched 0x{m_p or 0:x}, Up -> Pause {gap} frame(s)")
        s = unpause_continue(link, 9700 + i)
    early = link.rpc("input.stats")["hold"]["released_early"] - early0
    check(alone == reps, f"brain lost after a fresh press: the Pause tap lands alone {alone} / {reps} "
                         f"(Up 1 frame before the tap: {cut_gap1}, gaps {gaps})")
    check(cut_gap1 == 0 or early >= cut_gap1,
          f"input.stats hold.released_early +{early} (>= the {cut_gap1} taps with Up latched 1 frame before)")


def section_cutscene(link: OracleLink, wait_s: float) -> None:
    print(f"     waiting up to {wait_s:.0f} s for a CUTSCENE (trigger a skippable cutscene or a Bellway ride now)")
    try:
        link.wait_state(lambda s: s["game"]["gs"] == CUTSCENE, timeout_s=wait_s)
    except TimeoutError:
        check(False, "no CUTSCENE reached; see the module docstring for how to test the shim by hand")
        return
    time.sleep(1.5)  # stag scenes ignore input for their first 1.2 s; SKIP_PROMPT needs the prompt first
    before = link.rpc("input.stats")["legacy"]["sites"]
    for i in range(2):  # SKIP_PROMPT cutscenes need a second press 0.3-3 s after the first
        act_and_wait(link, link.frame + 1, mask("jump"), 9500 + i, hold=2)
        try:
            link.wait_state(lambda s: s["game"]["gs"] != CUTSCENE, timeout_s=1.0)
            break
        except TimeoutError:
            pass
    after = link.rpc("input.stats")["legacy"]["sites"]
    hits = {k: after[k]["injected_hits"] - before[k]["injected_hits"] for k in after}
    s = link.state
    print(f"     legacy hits during the skip: {hits}")
    check(s["game"]["gs"] != CUTSCENE, f"cutscene skipped by an injected key (GameState now {s['game']['gs']})")
    check(hits.get("InputHandler.CutsceneInput", 0) + hits.get("InputHandler.StagCutsceneInput", 0) > 0,
          "the skip came through the legacy anyKeyDown shim")


def fmt(v) -> str:
    return "(" + ", ".join(f"{x:.2f}" for x in v) + ")" if isinstance(v, (list, tuple)) else str(v)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--name", default="m1_probe")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--lost", action="store_true", help="also test the brain-lost Pause tap")
    ap.add_argument("--cutscene", type=float, default=0, metavar="SECONDS", help="also test the legacy shim on a cutscene")
    ap.add_argument("--only", default="",
                    help="comma list of sections: hello,savestate,randomize,latency,hold,stream,lost,lost_late,cutscene")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))

    def want(section: str, default: bool = True) -> bool:
        return section in only if only else default

    link = OracleLink(instance=a.instance)
    try:
        s = link.wait_state(timeout_s=5)
        if want("hello"):
            run_section(link, "hello", section_hello)
        needs_game = any(want(x) for x in ("savestate", "randomize", "latency", "hold", "stream")) or a.lost
        if needs_game and (not s.get("game") or s["game"]["gs"] != PLAYING):
            sys.exit(f"load a sandbox save and stand in a quiet room first (GameState {s.get('game') and s['game']['gs']})")
        if want("savestate"):
            run_section(link, "savestate", section_savestate, a.name, a.reps)
        if want("randomize"):
            run_section(link, "randomize_start", section_randomize, a.name)
        if want("latency"):
            run_section(link, "InputPathEmulator latency", section_latency)
        if want("hold"):
            run_section(link, "minimum hold", section_min_hold)
        if want("stream"):
            run_section(link, "minimum hold under the latency prior (streamed taps)", section_stream)
        if want("lost", a.lost):
            run_section(link, "brain lost", section_lost)
        if want("lost_late", a.lost):
            run_section(link, "brain lost right after a fresh press (QueueExclusiveCutAll)", section_lost_late)
        if want("cutscene", a.cutscene > 0):
            run_section(link, "legacy shim / cutscene skip", section_cutscene, a.cutscene or 120)
    finally:
        try:
            link.rpc("input.latency_model", delay_frames=0, jitter_frames=0, seed=0)
            link.rpc("input.release")
        except (OracleError, TimeoutError, OSError):
            pass
        link.close()
    print("ALL PASS" if not failures else f"{len(failures)} FAIL(S): " + "; ".join(failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
