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
         "title_game_options", "title_options_hl")


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


def run_case(link, enc, name: str, instance: int) -> dict:
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
        s = link.wait_state(lambda s: R.where(s) == "title" and not (s.get("game") or {}).get("fading"),
                            timeout_s=60)
        R._wait_frame(link, s["f"] + 30)
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
            results[name] = run_case(link, enc, name, a.instance)
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
