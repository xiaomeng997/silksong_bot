"""P15: what does killing the process do around a Steel Soul death? (training copy, sandbox slot 3 only)

For each trial: restore the Steel Soul template into sandbox slot 3, launch, load slot 3, deal a lethal hit through
the real TakeDamage path, then either watch how long the Dead state takes to reach the file, or kill the process
d ms after the hit and read what the file says.
"""
import shutil
import subprocess
import time
from pathlib import Path

from ssbot.io import game_window
from ssbot.io.sinks.oracle_inject import OracleClient
from ssbot.probes.p3_inject import menu_ready
from ssbot.tools.savefile import decode

SANDBOX = Path(r"C:\ssbot\sandbox\saves\0\default")
TEMPLATE = Path(r"C:\ssbot\sandbox\p15_template")
LAUNCHER = r"C:\modeling\silksong_bot\scripts\launch_train.ps1"


def restore_template() -> None:
    for f in SANDBOX.glob("user3*"):
        f.unlink()
    rp = SANDBOX / "Restore_Points3"
    if rp.exists():
        shutil.rmtree(rp)
    for f in TEMPLATE.iterdir():
        shutil.copy2(f, SANDBOX / f.name)


def game_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Hollow Knight Silksong.exe"], capture_output=True, text=True)
    return "Hollow Knight Silksong.exe" in out.stdout


def launch_and_load() -> OracleClient:
    prev = game_window.foreground()
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", LAUNCHER])
    time.sleep(6)
    game_window.restore_foreground(prev)
    deadline = time.time() + 60
    while True:
        try:
            c = OracleClient()
            break
        except OSError:
            if time.time() > deadline:
                raise
            time.sleep(1)
    menu_ready(c, "MAIN_MENU", 60)
    c.tap("enter", 0.08)
    menu_ready(c, "SAVE_PROFILES", 10)
    c.tap("right", 0.08); time.sleep(0.3); c.tap("right", 0.08); time.sleep(0.4)
    c.tap("enter", 0.08)
    c.wait_for(lambda s: s.get("state") == "PLAYING" and s.get("hero") is not None and s.get("permadeath") == "On", 60)
    c.wait_for(lambda s: not s.get("disablePause") and s.get("pauseAllowed"), 20)
    time.sleep(1.0)
    return c


def slot_mode() -> int:
    return decode(SANDBOX / "user3.dat")["playerData"]["permadeathMode"]


def trial(kill_after_ms: int | None) -> None:
    restore_template()
    c = launch_and_load()
    mtime0 = (SANDBOX / "user3.dat").stat().st_mtime_ns
    t0 = time.perf_counter()
    c._call("hurt 99 ENEMY")
    if kill_after_ms is None:
        written = None
        while time.perf_counter() - t0 < 10:
            if (SANDBOX / "user3.dat").stat().st_mtime_ns != mtime0:
                time.sleep(0.05)
                if slot_mode() == 2:
                    written = time.perf_counter() - t0
                    break
            time.sleep(0.005)
        print(f"baseline: Dead reached user3.dat after {written * 1000:.0f} ms" if written else "baseline: file never became Dead")
        c.close()
        subprocess.run(["taskkill", "/F", "/IM", "Hollow Knight Silksong.exe"], capture_output=True)
    else:
        time.sleep(kill_after_ms / 1000)
        subprocess.run(["taskkill", "/F", "/IM", "Hollow Knight Silksong.exe"], capture_output=True)
        killed_at = (time.perf_counter() - t0) * 1000
        time.sleep(1.0)
        mode = slot_mode()
        changed = (SANDBOX / "user3.dat").stat().st_mtime_ns != mtime0
        print(f"kill at +{killed_at:5.0f} ms: permadeathMode={mode} ({'DEAD' if mode == 2 else 'alive'}), "
              f"file rewritten={changed}, backups={sorted(p.name for p in SANDBOX.glob('user3.dat.bak*'))}")
    while game_running():
        time.sleep(0.5)
    time.sleep(2)  # launcher restores PlayerPrefs


if __name__ == "__main__":
    trial(None)
    for d in (0, 100, 300, 1000):
        trial(d)
