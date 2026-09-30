"""M1 harness-input probe: savestates, randomized starts, InputPathEmulator delay, minimum hold, brain-lost pause,
legacy anyKeyDown shim (oracle/src/Input, oracle/src/Train).

Needs: the training copy running with SsOracle (InputModule + TrainModule installed) and DebugMod, a sandbox save
loaded, Hornet standing in a quiet room (GameState PLAYING, no enemies nearby: the probe jumps once).

    cd brain
    uv run python -m ssbot.probes.m1_harness                      # savestate x10, randomize, latency, min hold
    uv run python -m ssbot.probes.m1_harness --lost               # + brain-lost Pause tap (pauses, then unpauses)
    uv run python -m ssbot.probes.m1_harness --cutscene 120       # + legacy shim: waits up to 120 s for a CUTSCENE
                                                                  #   (ride a Bellway or start a skippable cutscene
                                                                  #   by hand), then taps jump and expects the skip
Options: --instance N, --name STATE (savestate name, default m1_probe), --reps N, --only SECTION[,SECTION].
Prints PASS/FAIL per check and exits 1 on any FAIL. Leaves the latency model at 0 and releases every key.

The savestate RPCs take {name}; OracleLink.rpc's own first parameter is called `name`, so this probe sends the
accepted alias {state} instead.
"""
import argparse
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

failures: list[str] = []


def check(ok: bool, what: str) -> bool:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)
    return ok


def section_hello(link: OracleLink) -> None:
    rpcs = set(link.hello.get("rpcs", ()))
    missing = [r for r in REQUIRED_RPCS if r not in rpcs]
    check(not missing, f"HELLO lists the harness RPCs (missing: {missing or 'none'})")
    legacy = link.rpc("input.stats")["legacy"]
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


def act_and_wait(link: OracleLink, target: int, buttons: int, ack: int, hold: int = 0) -> dict:
    link.act(target, buttons, hold_frames=hold, ack_seq=ack)
    return link.wait_state(lambda s: s["act"]["ack"] == ack, timeout_s=2)


def section_latency(link: OracleLink) -> None:
    link.rpc("input.latency_model", delay_frames=3, jitter_frames=0, seed=0)
    f = link.frame + 4
    s = act_and_wait(link, f, 0, 9001)
    link.rpc("input.release")
    check(s["act"]["target"] == f and s["act"]["applied"] == f + 3,
          f"delay 3: ACTION target {f} applied at {s['act']['applied']} (expected {f + 3})")

    link.rpc("input.latency_model", delay_frames=3, jitter_frames=1, seed=5)
    lags = []
    for i in range(12):
        f = link.frame + 4
        s = act_and_wait(link, f, 0, 9100 + i)
        lags.append(s["act"]["applied"] - s["act"]["target"])
    link.rpc("input.release")
    check(set(lags) <= {2, 3, 4}, f"delay 3 jitter 1: applied - target = {lags} (all in 2..4)")

    link.rpc("input.latency_model", delay_frames=0, jitter_frames=0, seed=0, dist=[[2, 0.3], [3, 0.5], [4, 0.2]])
    model = link.rpc("input.latency_model")
    print(f"     dist model: {model}")
    res = link.rpc("input.latency_model", delay_frames=0, jitter_frames=0, seed=0)
    check(res["delay_frames"] == 0 and "dist" not in res, "latency model back to 0 frames")
    f = link.frame + 3
    s = act_and_wait(link, f, 0, 9200)
    link.rpc("input.release")
    check(s["act"]["applied"] == f, f"delay 0: target {f} applied at {s['act']['applied']}")


def section_min_hold(link: OracleLink) -> None:
    """A 1-frame jump request must be latched for exactly 2 frames (C19 / m0:N37)."""
    masks: dict[int, int] = {}
    recording = [True]

    def on_raw(msg_type: int, raw: bytes) -> None:
        if recording[0] and msg_type == MsgType.STATE:
            st = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
            masks[st["f"]] = st["act"]["mask"]

    link.subscribe_raw(on_raw)  # every STATE, not just the newest one polled
    before = link.rpc("input.stats")["hold"]["holds_extended"]
    jump = mask("jump")
    f = link.frame + 3
    act_and_wait(link, f, jump, 9300, hold=1)
    link.wait_state(lambda s: s["f"] > f + 6, timeout_s=2)
    link.rpc("input.release")
    recording[0] = False
    after = link.rpc("input.stats")["hold"]["holds_extended"]
    frames = sorted(k for k, m in masks.items() if m & jump and f - 1 <= k <= f + 6)
    check(len(frames) == 2 and frames[1] == frames[0] + 1,
          f"1-frame jump latched for frames {frames} (expected 2 consecutive)")
    check(after == before + 1, f"input.stats hold.holds_extended {before} -> {after}")


def section_lost(link: OracleLink) -> None:
    """Brain-lost: stop sending ACTIONs while driving -> keys released, one Pause tap."""
    s = link.wait_state(lambda s: s["game"]["gs"] == PLAYING, timeout_s=5)
    if s["pause"]["blk"] != 0:
        print(f"     pause blockers {s['pause']['blk']} set; waiting for them to clear")
        link.wait_state(lambda s: s["pause"]["blk"] == 0, timeout_s=10)
    before = link.rpc("input.stats")
    act_and_wait(link, link.frame + 1, 0, 9400)
    t0 = time.monotonic()
    s = link.wait_state(lambda s: s["act"]["lost"], timeout_s=3)
    print(f"     act.lost after {(time.monotonic() - t0) * 1000:.0f} ms (frame {s['f']})")
    s = link.wait_state(lambda s: s["game"]["paused"], timeout_s=3)
    after = link.rpc("input.stats")
    check(s["game"]["paused"] and after["lost_pause_taps"] == before["lost_pause_taps"] + 1,
          f"brain lost -> game paused with {after['lost_pause_taps'] - before['lost_pause_taps']} tap(s) "
          f"(lost_events {before['lost_events']} -> {after['lost_events']})")
    # Unpause with Continue + Submit once the menu has faded in (DESIGN §3.7.5: an Esc may be handled twice).
    time.sleep(1.0)
    act_and_wait(link, link.frame + 1, mask("enter"), 9401, hold=2)
    s = link.wait_state(lambda s: not s["game"]["paused"], timeout_s=3)
    link.rpc("input.release")
    check(not s["game"]["paused"] and not s["act"]["lost"], "unpaused by an ACTION (Continue); brain no longer lost")


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
        link.rpc("input.release")
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
    ap.add_argument("--only", default="", help="comma list of sections: hello,savestate,randomize,latency,hold,lost,cutscene")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))

    def want(section: str, default: bool = True) -> bool:
        return section in only if only else default

    link = OracleLink(instance=a.instance)
    try:
        s = link.wait_state(timeout_s=5)
        if want("hello"):
            print("== hello"); section_hello(link)
        needs_game = any(want(x) for x in ("savestate", "randomize", "latency", "hold")) or a.lost
        if needs_game and (not s.get("game") or s["game"]["gs"] != PLAYING):
            sys.exit(f"load a sandbox save and stand in a quiet room first (GameState {s.get('game') and s['game']['gs']})")
        if want("savestate"):
            print("== savestate"); section_savestate(link, a.name, a.reps)
        if want("randomize"):
            print("== randomize_start"); section_randomize(link, a.name)
        if want("latency"):
            print("== InputPathEmulator latency"); section_latency(link)
        if want("hold"):
            print("== minimum hold"); section_min_hold(link)
        if want("lost", a.lost):
            print("== brain lost"); section_lost(link)
        if want("cutscene", a.cutscene > 0):
            print("== legacy shim / cutscene skip"); section_cutscene(link, a.cutscene or 120)
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
