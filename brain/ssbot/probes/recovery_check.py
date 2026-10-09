"""Live check of the harness recovery (train.recovery, combat_run.back_into_slot) on one training instance: drive the
game into each state the workers met, run the recovery, record what it pressed and where the game ended. Training copy
only, oracle STATE, save suppression on (the one real quit to the title is combat_run's --real-quit path).

  pause_options_hl   paused, the highlight moved to Options (mouse hover did that): resume
  pause_quit_hl      paused, the highlight on Quit: resume
  pause_options      paused in the Options menu: resume (Down to Back, Back, Continue)
  pause_game_options paused in Options -> its first item's sub-menu: resume
  exit_prompt        the "quit to menu?" prompt with Yes highlighted: resume (No, Continue)
  brain_lost         continuous control stops: the oracle's watchdog pauses; pause_cause on the first paused STATE,
                     then resume
  title_game_options a real quit, then the title's Options -> Game options (20261005_164501 i1): back_into_slot
  title_options_hl   the title's highlight on Options: back_into_slot (MenuError, Esc, Up, Start Game)
  episode_pause      a real data episode (run_episode, the data policy) whose ACTIONs open the pause menu mid-fight:
                     HARNESS_FAIL "paused unasked", combat_run.after_harness_fail, then a second episode runs
  episode_settings   the same, then the pause menu's Options -> its first sub-menu (what the person found on 10-05);
                     the next episode starts from there (its own resume before the reset), no after_harness_fail
  worker_pause       combat_run.worker itself (2 episodes, on this probe's link): episode 0's ACTIONs open the pause
                     menu (PauseAt), the worker's after_harness_fail resumes, episode 1 runs at the time scale read
  worker_norecover   the same with after_harness_fail doing nothing (the old worker of 20261008_015907 i0): the
                     worker's ready_for_episode resumes before the time scale read, episode 1 runs
  title_items        the title's main menu: which menu Down x1..4 + Enter opens from Start Game (Esc back, Up as
                     many), then Up x1 + Enter (does the list wrap?), then back_into_slot; recovery.TITLE_ITEM

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.recovery_check --instance 4 [--cases a,b,...]
Writes C:\\ssbot\\sandbox\\recovery_check\\<time>_i<N>.json; facts: docs/facts/1.0.30000/pause_quit.md section 11.
"""
import argparse
import contextlib
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.train import recovery as R

OUT = Path(r"C:\ssbot\sandbox\recovery_check")
CASES = ("pause_options_hl", "pause_quit_hl", "pause_options", "pause_game_options", "exit_prompt", "brain_lost",
         "title_game_options", "title_options_hl", "episode_pause", "episode_settings", "worker_pause",
         "worker_norecover", "title_items")
SEED = 990_000          # the episode cases' seeds (probe only: no attempt rows are written)
EP_TIMEBOX_S = 12.0     # the second episode: a short timebox (STUCK at its end is a healthy episode here)


class PauseAt:
    """The inner policy's keys plus one Pause press (3 frames) from the episode's `at`-th ACTION on, once the pause
    gate is open (pause.blk 0): the harness's own side opens the pause menu mid-fight. A press the game dropped (no
    pause a second later: the episode loop ends at the first paused STATE, so act is not called after one) is
    repeated."""

    def __init__(self, inner, at: int = 180, episodes: int | None = None):
        self.inner, self.at, self.episodes = inner, at, episodes    # episodes: press in the first N only (None: all)
        self.n, self.pressed, self.ep = 0, None, 0

    def reset(self, rng, enc) -> None:
        self.inner.reset(rng, enc)
        self.n, self.pressed = 0, None
        self.ep += 1

    def stats(self) -> dict:
        return {"pause_at": self.at, "episode": self.ep}

    def act(self, s: dict, tap) -> int:
        m = self.inner.act(s, tap) & ~R.PAUSE_BIT
        self.n += 1
        if self.n < self.at or (self.episodes is not None and self.ep > self.episodes):
            return m
        if self.pressed is not None and self.n - self.pressed > 60:
            self.pressed = None
        if self.pressed is None and not ((s.get("pause") or {}).get("blk") or 0):
            self.pressed = self.n
        if self.pressed is not None and self.n - self.pressed < 3:
            m |= R.PAUSE_BIT
        return m


def _menu_view(s: dict) -> dict:
    g = s.get("game") or {}
    m = s.get("menu") or {}
    return {"f": s.get("f"), "where": R.where(s), "gs": g.get("gs"), "ui": g.get("ui"), "menu": g.get("menu"),
            "paused": g.get("paused"), "sel": m.get("sel"), "alpha": m.get("alpha"), "scene": g.get("scene")}


def _wait_where(link, places, timeout_s: float = 10.0) -> dict:
    places = (places,) if isinstance(places, str) else tuple(places)
    return link.wait_state(lambda s: R.where(s) in places, timeout_s=timeout_s)


def _tap_and_wait(link, key: str) -> dict:
    return R._wait_frame(link, R.tap(link, key))


def _pause(link) -> dict:
    """Esc in gameplay (the pause gate open), then the pause menu ready."""
    link.wait_state(lambda s: R.where(s) == "game" and ((s.get("pause") or {}).get("blk") == 0), timeout_s=20)
    R.tap(link, "pause")
    return _wait_where(link, "pause_menu")


def _reset(link, enc) -> None:
    from ssbot.train.episode import wait_settled
    link.rpc("input.release", timeout_s=10)
    link.rpc("savestate.load", timeout_s=40, name=enc.savestate, timeout=30)
    wait_settled(link, enc.scene, timeout_s=60)


def _resume_case(link, setup) -> dict:
    start = setup()
    t0 = time.monotonic()
    f0 = link.frame
    ok, steps = R.resume(link, log=print)
    s = link.state or {}
    return {"start": _menu_view(start), "ok": ok, "steps": steps, "s": round(time.monotonic() - t0, 2),
            "frames": (s.get("f") or 0) - f0, "end": _menu_view(s)}


def _episode(link, enc, tap, policy, seed: int, timebox_s: float | None = None) -> dict:
    """One run_episode as a combat_run worker runs it (data mode), summarised."""
    from ssbot.tools.combat_run import mode_config
    from ssbot.train.episode import AttemptRecord, run_episode
    rec = AttemptRecord(unit=enc.name, stage="TRAIN", profile="TRAIN", build="1.0.30000", code_rev=None,
                        config_fp="recovery_check", start_kind="savestate", mode="data", seed=seed)
    t0 = time.monotonic()
    run_episode(link, enc, tap, policy, mode_config("data", seed, timebox_s), rec)
    return {"outcome": rec.outcome, "reason": rec.reason, "acts": rec.acts, "ingame_s": rec.ingame_s,
            "wall_s": round(time.monotonic() - t0, 2), "loop_gap_ms_max": rec.loop_gap_ms_max,
            "start_resume": rec.start_resume, "end": _menu_view(link.state or {})}


class _Shared:
    """The probe's link lent to combat_run.worker (one connection per instance): everything but close()."""

    def __init__(self, link):
        self._link = link

    def __getattr__(self, name):
        return getattr(self._link, name)

    def close(self) -> None:
        pass


def _worker_case(link, enc, instance: int, recover: bool) -> dict:
    """combat_run.worker for 2 data episodes on this link (OracleLink lent through _Shared), its policy the data policy
    with one Pause press in episode 0 (PauseAt): episode 0 must end HARNESS_FAIL "paused unasked", episode 1 must run
    (not HARNESS_FAIL) with the time scale read back. recover False: after_harness_fail does nothing (the old
    worker), so the worker's ready_for_episode has to resume. Rows go to a probe directory, not the data runs."""
    from unittest import mock
    from ssbot.tools import combat_run
    from ssbot.train.data_policy import DataPolicy
    run_dir = OUT / f"worker_{datetime.now():%Y%m%d_%H%M%S}_{'recover' if recover else 'norecover'}"
    run_dir.mkdir(parents=True, exist_ok=True)
    patches = [mock.patch("ssbot.ipc.oracle_link.OracleLink", lambda instance, connect_timeout_s: _Shared(link)),
               mock.patch.object(combat_run, "make_policy", lambda *a, **k: PauseAt(DataPolicy(), episodes=1))]
    if not recover:
        patches.append(mock.patch.object(combat_run, "after_harness_fail", lambda link, enc, instance: None))
    buf = io.StringIO()
    t0 = time.monotonic()
    with contextlib.ExitStack() as st:
        for p in patches:
            st.enter_context(p)
        try:
            with contextlib.redirect_stdout(buf):
                rc = combat_run.main(["_worker", "--instance", str(instance), "--run-dir", str(run_dir), "--encounter",
                                      enc.name, "--episodes", "2", "--no-record", "--timebox", str(EP_TIMEBOX_S),
                                      "--seed", str(SEED + (20 if recover else 30))])
        except (Exception, SystemExit) as e:  # noqa: BLE001 - recorded
            rc = f"raised {type(e).__name__}: {e}"
    rows = [json.loads(x) for x in (run_dir / f"attempts_i{instance}.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()] if (run_dir / f"attempts_i{instance}.jsonl").exists() else []
    eps = [{k: r.get(k) for k in ("episode", "outcome", "reason", "acts", "time_scale_game", "loop_gap_ms_max",
                                  "start_resume")} for r in rows]
    log = buf.getvalue().splitlines()
    ok = (rc == 0 and len(rows) == 2 and rows[0]["outcome"] == "HARNESS_FAIL"
          and "paused unasked" in (rows[0]["reason"] or "") and rows[1]["outcome"] != "HARNESS_FAIL"
          and rows[1]["time_scale_game"] == 1.0)
    return {"ok": ok, "rc": rc, "episodes": eps, "log": log, "s": round(time.monotonic() - t0, 2),
            "run_dir": str(run_dir), "end": _menu_view(link.state or {})}


def _quit_to_title(link) -> dict:
    """Pause, Quit, Yes (a real quit; save suppression on), then the title's main menu settled."""
    _pause(link)
    _tap_and_wait(link, "down")
    _tap_and_wait(link, "down")
    _tap_and_wait(link, "enter")
    s = _wait_where(link, "exit_prompt")
    R._wait_frame(link, s["f"] + 20)
    if (link.state.get("menu") or {}).get("sel") != "yes":
        _tap_and_wait(link, "up")
    assert (link.state.get("menu") or {}).get("sel") == "yes", _menu_view(link.state)
    R.tap(link, "enter")                        # Yes: the real quit (save suppression on)
    s = link.wait_state(lambda s: R.where(s) == "title" and not (s.get("game") or {}).get("fading"), timeout_s=60)
    return R._wait_frame(link, s["f"] + 30)


def _title_opens(link) -> int | None:
    """Enter on the main menu: the menu it opens once settled (None: nothing within 10 s)."""
    _tap_and_wait(link, "enter")
    try:
        s = link.wait_state(lambda s: (s.get("game") or {}).get("menu") != R.MENU_MAIN
                            and not (s.get("game") or {}).get("fading"), timeout_s=10)
    except TimeoutError:
        return None
    R._wait_frame(link, s["f"] + 20)
    return (s.get("game") or {}).get("menu")


def _title_items(link, enc, instance: int) -> dict:
    """From the title's Start Game highlight: Down x n + Enter for n = 1..4 (each menu left with title_home, then Up x
    n back to Start Game), then Up x 1 + Enter: the save select (6) if the list stops at its top, the quit-game prompt
    (14) if it wraps. back_into_slot from wherever that leaves the title."""
    from ssbot.tools.combat_run import back_into_slot
    _quit_to_title(link)
    t0 = time.monotonic()
    opened, homes = {}, {}
    for n in range(1, 5):
        for _ in range(n):
            _tap_and_wait(link, "down")
        opened[n] = _title_opens(link)
        ok, steps = R.title_home(link)
        homes[n] = {"ok": ok, "esc": len(steps)}
        for _ in range(n):
            _tap_and_wait(link, "up")
    _tap_and_wait(link, "up")
    up1 = _title_opens(link)
    if R.where(link.state) == "title_submenu":
        R.title_home(link)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            back_into_slot(link, enc, instance)
        back = True
    except Exception as e:  # noqa: BLE001 - recorded
        back = False
        buf.write(f"raised {type(e).__name__}: {e}\n")
    item = {m: n for n, m in opened.items() if m is not None}
    ok = all(R.TITLE_ITEM.get(m) == n for m, n in item.items()) and back
    return {"ok": ok, "down_opens": opened, "title_home": homes, "up1_opens": up1,
            "wraps": up1 == R.MENU_QUIT_GAME_PROMPT if up1 is not None else None,
            "title_item_matches": {str(m): R.TITLE_ITEM.get(m) == n for m, n in item.items()}, "back": back,
            "log": buf.getvalue().splitlines(), "s": round(time.monotonic() - t0, 2), "end": _menu_view(link.state or {})}


def _episode_case(link, enc, tap, instance: int, settings: bool) -> dict:
    """A data episode whose ACTIONs open the pause menu mid-fight (PauseAt), then (settings) the pause menu's Options
    and its first sub-menu, then the worker's recovery (after_harness_fail, or with settings the next episode's own
    resume before its reset), then a second episode: it must not be a HARNESS_FAIL."""
    from ssbot.tools.combat_run import after_harness_fail
    from ssbot.train.data_policy import DataPolicy
    out = {"ep1": _episode(link, enc, tap, PauseAt(DataPolicy()), SEED + (10 if settings else 0))}
    if settings:
        _wait_where(link, "pause_menu")
        _tap_and_wait(link, "down")
        _tap_and_wait(link, "enter")
        s = _wait_where(link, "pause_submenu")
        R._wait_frame(link, s["f"] + 20)
        _tap_and_wait(link, "enter")       # the Options menu's first item (Game): a sub-menu, no setting
        s = link.wait_state(lambda s: R.where(s) == "pause_submenu"
                            and (s.get("game") or {}).get("menu") != R.MENU_OPTIONS, timeout_s=10)
        link.rpc("input.release", timeout_s=10)
        out["before_ep2"] = _menu_view(s)
    else:
        out["before_recovery"] = _menu_view(link.state or {})
        out["after_harness_fail"] = after_harness_fail(link, enc, instance)
        out["after_recovery"] = _menu_view(link.state or {})
    out["ep2"] = _episode(link, enc, tap, DataPolicy(), SEED + (11 if settings else 1), EP_TIMEBOX_S)
    out["ok"] = (out["ep1"]["outcome"] == "HARNESS_FAIL" and "paused unasked" in (out["ep1"]["reason"] or "")
                 and out["ep2"]["outcome"] != "HARNESS_FAIL")
    return out


def run_case(link, enc, name: str, instance: int, tap=None) -> dict:
    if name in ("episode_pause", "episode_settings"):
        return _episode_case(link, enc, tap, instance, settings=name == "episode_settings")
    if name in ("worker_pause", "worker_norecover"):
        return _worker_case(link, enc, instance, recover=name == "worker_pause")
    if name == "title_items":
        return _title_items(link, enc, instance)
    if name == "pause_options_hl":
        def setup():
            _pause(link)
            _tap_and_wait(link, "down")
            return link.wait_state(lambda s: (s.get("menu") or {}).get("sel") == "options", timeout_s=5)
        return _resume_case(link, setup)
    if name == "pause_quit_hl":
        def setup():
            _pause(link)
            _tap_and_wait(link, "down")
            _tap_and_wait(link, "down")
            return link.state
        return _resume_case(link, setup)
    if name == "pause_options":
        def setup():
            _pause(link)
            _tap_and_wait(link, "down")
            _tap_and_wait(link, "enter")
            return _wait_where(link, "pause_submenu")
        return _resume_case(link, setup)
    if name == "pause_game_options":
        def setup():
            _pause(link)
            _tap_and_wait(link, "down")
            _tap_and_wait(link, "enter")
            s = _wait_where(link, "pause_submenu")
            R._wait_frame(link, s["f"] + 20)
            _tap_and_wait(link, "enter")       # the Options menu's first item (Game): a sub-menu, no setting
            return link.wait_state(lambda s: R.where(s) == "pause_submenu"
                                   and (s.get("game") or {}).get("menu") != R.MENU_OPTIONS, timeout_s=10)
        return _resume_case(link, setup)
    if name == "exit_prompt":
        def setup():
            _pause(link)
            _tap_and_wait(link, "down")
            _tap_and_wait(link, "down")
            _tap_and_wait(link, "enter")
            s = _wait_where(link, "exit_prompt")
            R._wait_frame(link, s["f"] + 20)
            if (link.state.get("menu") or {}).get("sel") != "yes":
                _tap_and_wait(link, "up")
            return link.state
        return _resume_case(link, setup)
    if name == "brain_lost":
        first: dict = {}

        def on_state(s):
            if not first and (s.get("game") or {}).get("paused"):
                first.update(s)
        link.subscribe_state(on_state)

        def setup():
            link.wait_state(lambda s: R.where(s) == "game" and ((s.get("pause") or {}).get("blk") == 0), timeout_s=20)
            for _ in range(30):                     # continuous control with a key down arms the watchdog
                f = link.frame
                link.act(f + 2, mask("up"), hold_frames=0)
                link.wait_state(newer_than=f, timeout_s=2)
            t_stop = time.monotonic()
            s = link.wait_state(lambda s: R.where(s) in R.PAUSED_PLACES, timeout_s=10)
            first["_ms_to_pause"] = round((time.monotonic() - t_stop) * 1000.0)
            return _wait_where(link, "pause_menu")
        out = _resume_case(link, setup)
        out["cause"] = R.pause_cause(first)
        out["ms_to_pause"] = first.get("_ms_to_pause")
        out["first_paused"] = {"f": first.get("f"), "act": first.get("act"), "input": (first.get("input") or {}).get("mask")}
        return out
    if name in ("title_game_options", "title_options_hl"):
        from ssbot.tools.combat_run import back_into_slot
        _quit_to_title(link)
        _tap_and_wait(link, "down")                 # the highlight on Options
        if name == "title_game_options":
            _tap_and_wait(link, "enter")            # Options
            s = link.wait_state(lambda s: (s.get("game") or {}).get("menu") == R.MENU_OPTIONS
                                and not (s.get("game") or {}).get("fading"), timeout_s=10)
            R._wait_frame(link, s["f"] + 20)
            _tap_and_wait(link, "enter")            # Options' first item: Game options
            s = link.wait_state(lambda s: (s.get("game") or {}).get("menu") not in (R.MENU_OPTIONS, R.MENU_MAIN)
                                and not (s.get("game") or {}).get("fading"), timeout_s=10)
        start = _menu_view(link.state)
        t0 = time.monotonic()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):    # back_into_slot logs to stdout
                back_into_slot(link, enc, instance)
            ok = True
        except Exception as e:  # noqa: BLE001 - recorded
            ok = False
            buf.write(f"raised {type(e).__name__}: {e}\n")
        return {"start": start, "ok": ok, "log": buf.getvalue().splitlines(), "s": round(time.monotonic() - t0, 2),
                "end": _menu_view(link.state or {})}
    raise SystemExit(f"unknown case {name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, required=True)
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--encounter", default="BellBeast")
    a = ap.parse_args(argv)
    from ssbot.tools.combat_run import back_into_slot
    from ssbot.train.encounters import ENCOUNTERS
    enc = ENCOUNTERS[a.encounter]
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    s = link.wait_state(lambda s: s.get("game") is not None, timeout_s=60)
    print("start:", _menu_view(s), flush=True)
    if R.where(s) in R.PAUSED_PLACES:
        print("resume at the start:", R.resume(link, log=print), flush=True)
    if R.where(link.state) != "game" or not (link.state.get("game") or {}).get("scene"):
        back_into_slot(link, enc, a.instance)
    if not link.rpc("guards.set", timeout_s=30, save_suppression=True)["save_suppression"]:
        raise SystemExit("save suppression could not be turned on")
    from ssbot.train.episode import make_tap
    tap = make_tap(link, enc)           # one tap for every episode, as in a worker (it subscribes to the STATEs)
    results = {}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{datetime.now():%Y%m%d_%H%M%S}_i{a.instance}.json"
    for name in a.cases.split(","):
        stop = Path(r"C:\ssbot\sandbox\STOP_AGENTS"), Path(r"C:\ssbot\sandbox\DEMO_SOON")
        if any(p.exists() for p in stop):
            print("stop file: ending", flush=True)
            break
        _reset(link, enc)
        print(f"== {name}", flush=True)
        try:
            results[name] = run_case(link, enc, name, a.instance, tap)
        except Exception as e:  # noqa: BLE001 - recorded, the next case resets
            results[name] = {"error": f"{type(e).__name__}: {e}", "state": _menu_view(link.state or {})}
            if R.where(link.state) in R.PAUSED_PLACES:
                R.resume(link)
            elif R.where(link.state) not in ("game",):
                back_into_slot(link, enc, a.instance)
        print(json.dumps(results[name], default=str), flush=True)
        path.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    if R.where(link.state) != "game":
        back_into_slot(link, enc, a.instance)
    link.rpc("guards.set", timeout_s=30, save_suppression=True)
    _reset(link, enc)
    link.rpc("input.release", timeout_s=10)
    link.close()
    print(f"wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
