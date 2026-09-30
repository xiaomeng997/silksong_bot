"""Multi-instance training launcher (DESIGN §2.3 TRAIN: 4-6 instances; §2.7 PlayerPrefs), replacing
scripts/launch_train.ps1 for N instances.

    python -m ssbot.tools.launcher --make-golden          # once: snapshot the frozen PlayerPrefs to golden.reg
    python -m ssbot.tools.launcher --prepare-multi        # once: drop Unity's single-instance flag (training copy)
    python -m ssbot.tools.launcher -n 4                   # start instances 0..3, tile, wait for IPC, wait for exit
    python -m ssbot.tools.launcher --status | --restore

Per instance N: `-ssbot-instance N` (sandbox saves + IPC port 47017+N in SsOracle), `-logFile
C:\\ssbot\\sandbox\\logs\\player_N.log`, a small window (-screen-fullscreen 0 -screen-width/-height) moved into a tile
once it appears, and a wait until the oracle listens on its port.

PlayerPrefs (HKCU\\Software\\Team Cherry\\Hollow Knight Silksong) are shared by every copy of the game and Unity writes
the launch resolution back into them on exit (probe P9). Instead of per-launch before/after snapshots, which race when
several launchers run, all launchers share one registry of live instances (instances.json) under one lock file:
whoever sees the last registered instance gone restores the GOLDEN snapshot, exactly once per generation. A process
start and its registration happen under the same lock, so a restore can never overlap a starting instance.
Instances orphaned by a killed launcher are pruned (pid + creation time) by the next launcher or by --restore.
golden.reg must hash to versions.lock [frozen_settings].golden_prefs_sha256: launch and restore refuse otherwise, so a
replaced or corrupted snapshot never spreads into later sessions (§2.7). A launch also refuses while a game process
that no launcher registered is running (scripts/launch_train.ps1, a human session, your own game), because its
PlayerPrefs write on exit would race the golden restore.
"""
import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ssbot.ipc.framing import port as ipc_port
from ssbot.record.recorder import file_sha256, find_repo_root

TRAIN_DIR = Path(r"C:\ssbot\game\train")
FINAL_DIR = Path(r"C:\ssbot\game\final")
EXE = "Hollow Knight Silksong.exe"
DATA = "Hollow Knight Silksong_Data"
BOOT_CONFIG = f"{DATA}/boot.config"
BOOT_BACKUP_SUFFIX = ".ssbot-orig"
PREFS_KEY = r"HKCU\Software\Team Cherry\Hollow Knight Silksong"
PREFS_DIR = Path(r"C:\ssbot\sandbox\prefs")
LOG_DIR = Path(r"C:\ssbot\sandbox\logs")
# Unity bumps these on every launch; they are not settings (unity.player_session_count_h922449978 - note the
# underscore - and unity.player_sessionid_h1351336811).
VOLATILE_PREFS = re.compile(r"^unity\.player_session(_count|id)_h\d+$")


# ---- arguments and layout ------------------------------------------------------------------------------

def build_args(instance: int, width: int, height: int, log_dir: Path = LOG_DIR, extra: tuple[str, ...] = ()
               ) -> list[str]:
    """Unity player arguments for one training instance."""
    return ["-ssbot-instance", str(instance),
            "-logFile", str(Path(log_dir) / f"player_{instance}.log"),
            "-screen-fullscreen", "0", "-screen-width", str(width), "-screen-height", str(height),
            *extra]


def tile_positions(n: int, slot_w: int, slot_h: int, area: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    """Top-left corners for n windows of slot_w x slot_h (outer size) in the work area (left, top, right, bottom):
    row-major grid; when the grid is full, further windows cascade over it offset by 40 px per layer."""
    left, top, right, bottom = area
    cols = max(1, (right - left) // max(1, slot_w))
    rows = max(1, (bottom - top) // max(1, slot_h))
    out = []
    for i in range(n):
        layer, k = divmod(i, cols * rows)
        r, c = divmod(k, cols)
        out.append((left + c * slot_w + 40 * layer, top + r * slot_h + 40 * layer))
    return out


# ---- boot.config single-instance flag ------------------------------------------------------------------

def boot_config(game_dir: Path) -> Path:
    return Path(game_dir) / BOOT_CONFIG


def single_instance_enabled(game_dir: Path) -> bool:
    """Unity's boot.config key `single-instance=` (any value) makes a second player activate the first and quit."""
    p = boot_config(game_dir)
    if not p.is_file():
        return False
    return any(line.split("=", 1)[0].strip() == "single-instance"
               for line in p.read_text("utf-8", errors="replace").splitlines())


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve() or (Path(a).exists() and Path(b).exists()
                                                           and os.path.samefile(a, b))
    except OSError:
        return False


def assert_training_copy(game_dir: Path, final_dir: Path = FINAL_DIR) -> None:
    """Refuse anything that is not the modded training copy: the final copy must stay byte-identical (§2.3 FINAL)."""
    if _same_dir(game_dir, final_dir):
        raise SystemExit(f"refusing: {game_dir} is the FINAL copy")
    if not (Path(game_dir) / "BepInEx").is_dir() or not (Path(game_dir) / EXE).is_file():
        raise SystemExit(f"refusing: {game_dir} is not a training copy (no {EXE} + BepInEx)")


def prepare_multi(game_dir: Path, final_dir: Path = FINAL_DIR) -> str:
    """Remove `single-instance=` from the training copy's boot.config after backing the file up once."""
    assert_training_copy(game_dir, final_dir)
    p = boot_config(game_dir)
    if not single_instance_enabled(game_dir):
        return f"{p}: single-instance already absent"
    backup = p.with_name(p.name + BOOT_BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(p, backup)
    raw = p.read_bytes()
    kept = [line for line in raw.splitlines(keepends=True)
            if line.split(b"=", 1)[0].strip() != b"single-instance"]
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(b"".join(kept))
    os.replace(tmp, p)
    return f"{p}: removed single-instance (backup {backup.name})"


def unprepare_multi(game_dir: Path, final_dir: Path = FINAL_DIR) -> str:
    assert_training_copy(game_dir, final_dir)
    p = boot_config(game_dir)
    backup = p.with_name(p.name + BOOT_BACKUP_SUFFIX)
    if not backup.exists():
        return f"{p}: no backup, nothing to restore"
    os.replace(backup, p)
    return f"{p}: restored from {backup.name}"


# ---- PlayerPrefs ---------------------------------------------------------------------------------------

class PrefsStore(Protocol):
    """The registry operations the launcher needs; tests substitute an in-memory fake."""
    def export(self, path: Path) -> None: ...
    def restore(self, path: Path) -> None: ...


class RegPrefsStore:
    """PlayerPrefs through reg.exe (a .reg export is what versions.lock and compat hash)."""
    key = PREFS_KEY

    @staticmethod
    def _reg(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        # reg.exe reports success on stderr; only the exit code matters.
        r = subprocess.run(["reg", *args], capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"reg {' '.join(args)} failed ({r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
        return r

    def export(self, path: Path) -> None:
        self._reg("export", self.key, str(path), "/y")

    def restore(self, path: Path) -> None:
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        self._reg("delete", self.key, "/f", check=False)  # absent key is fine
        self._reg("import", str(path))


def parse_reg(text: str) -> dict[str, str]:
    """Values of a .reg export ({name: raw value text}), continuation lines joined; section headers ignored."""
    values: dict[str, str] = {}
    logical: list[str] = []
    buf = ""
    for line in text.splitlines():
        line = line.rstrip()
        if buf:
            line = buf + line.lstrip()
            buf = ""
        if line.endswith("\\"):
            buf = line[:-1]
            continue
        logical.append(line)
    for line in logical:
        m = re.match(r'^"((?:[^"\\]|\\.)*)"=(.*)$', line)
        if m:
            values[m.group(1)] = m.group(2)
        elif line.startswith("@="):
            values["@"] = line[2:]
    return values


def read_reg_file(path: Path) -> dict[str, str]:
    raw = Path(path).read_bytes()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", errors="replace")
    return parse_reg(text)


def prefs_diff(a: dict[str, str], b: dict[str, str], volatile: re.Pattern = VOLATILE_PREFS) -> list[str]:
    names = {k for k in a.keys() | b.keys() if not volatile.match(k)}
    return sorted(k for k in names if a.get(k) != b.get(k))


def prefs_digest(values: dict[str, str], volatile: re.Pattern = VOLATILE_PREFS) -> str:
    """Order-independent hash of the settings (session counters excluded), to compare two exports by content.
    versions.lock pins the golden.reg file itself instead (golden_prefs_sha256 = sha256 of its bytes)."""
    stable = {k: v for k, v in values.items() if not volatile.match(k)}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def current_prefs(store: PrefsStore) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "now.reg"
        store.export(p)
        return read_reg_file(p)


def _same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def golden_pin(golden: Path, lock: dict | None = None) -> str | None:
    """versions.lock [frozen_settings].golden_prefs_sha256 (lowercase), or None when the lock pins no hash or pins a
    different file (golden_prefs) than `golden`. lock: a parsed versions.lock; None reads the repo's."""
    if lock is None:
        root = find_repo_root()
        try:
            lock = tomllib.loads((root / "versions.lock").read_text("utf-8")) if root else {}
        except (OSError, tomllib.TOMLDecodeError):
            lock = {}
    fs = lock.get("frozen_settings", {})
    pin, pinned_path = fs.get("golden_prefs_sha256"), fs.get("golden_prefs")
    if not pin or (pinned_path and not _same_path(pinned_path, golden)):
        return None
    return str(pin).lower()


# ---- cross-launcher instance registry ------------------------------------------------------------------

class FileLock:
    """Exclusive OS lock on a lock file (msvcrt on Windows, flock elsewhere). The OS drops it if the holder dies,
    so a crashed launcher never leaves a stale lock. Each FileLock opens its own handle: threads exclude too."""

    def __init__(self, path: Path, timeout_s: float = 60.0):
        self.path = Path(path)
        self.timeout_s = timeout_s
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                self._lock()
                return self
            except OSError:
                if time.monotonic() > deadline:
                    os.close(self.fd)
                    self.fd = None
                    raise TimeoutError(f"could not lock {self.path} within {self.timeout_s} s")
                time.sleep(0.02)

    def _lock(self) -> None:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(self.fd, 0, os.SEEK_SET)
            msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def __exit__(self, *exc) -> None:
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(self.fd)
            self.fd = None


def process_alive(pid: int, created: float | None) -> bool:
    """True while that exact process (pid + creation time, so pid reuse is not mistaken for it) exists."""
    import psutil
    try:
        p = psutil.Process(pid)
        if created is not None and abs(p.create_time() - created) > 1.0:
            return False
        return p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def process_created(pid: int) -> float | None:
    import psutil
    try:
        return psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def running_game_pids(exe: str = EXE) -> list[int]:
    """Pids of every running game process (any copy: training, final, human session)."""
    import psutil
    name = exe.lower()
    return sorted(p.pid for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower() == name)


class PrefsGuard:
    """Shared record of live training instances; restores the golden PlayerPrefs once, when the last one is gone.

    instances.json: {"instances": [{"pid", "created", "instance", "launcher", "started"}],
                     "restore_pending": bool, "restores": int, "last_restore": str | None}

    pin: the sha256 golden.reg must have (versions.lock golden_prefs_sha256); launch and restore refuse on a mismatch.
    None only warns (a lock without the pin); PrefsGuard.default reads it from versions.lock.
    """

    def __init__(self, store: PrefsStore, golden: Path, state_path: Path, lock_path: Path,
                 alive: Callable[[int, float | None], bool] = process_alive,
                 log: Callable[[str], None] = print, keep_after: Path | None = None, pin: str | None = None,
                 game_pids: Callable[[], list[int]] = running_game_pids):
        self.store = store
        self.golden = Path(golden)
        self.state_path = Path(state_path)
        self.lock_path = Path(lock_path)
        self.alive = alive
        self.log = log
        self.keep_after = keep_after  # directory for an "after_<stamp>.reg" export before each restore (forensics)
        self.pin = pin.lower() if pin else None
        self.game_pids = game_pids
        self._unpinned_logged = False

    @classmethod
    def default(cls, prefs_dir: Path = PREFS_DIR, lock: dict | None = None) -> "PrefsGuard":
        golden = prefs_dir / "golden.reg"
        return cls(RegPrefsStore(), golden, prefs_dir / "instances.json", prefs_dir / "instances.lock",
                   keep_after=prefs_dir, pin=golden_pin(golden, lock))

    def verify_golden(self) -> str:
        """sha256 of golden.reg; SystemExit when it is missing or differs from the pin."""
        if not self.golden.is_file():
            raise SystemExit(f"no golden PlayerPrefs snapshot at {self.golden}; run --make-golden first")
        digest = file_sha256(self.golden)
        if self.pin is None:
            if not self._unpinned_logged:
                self._unpinned_logged = True
                self.log(f"[prefs] WARNING versions.lock pins no golden_prefs_sha256 for {self.golden} "
                         f"(sha256 {digest}); the snapshot is not verified")
        elif digest != self.pin:
            raise SystemExit(f"refusing: {self.golden} has sha256 {digest}, versions.lock [frozen_settings] "
                             f"golden_prefs_sha256 is {self.pin}. Put the pinned snapshot back, or pin the new one "
                             f"deliberately")
        return digest

    def lock(self) -> FileLock:
        return FileLock(self.lock_path)

    def _read(self) -> dict:
        try:
            d = json.loads(self.state_path.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            d = {}
        d.setdefault("instances", [])
        d.setdefault("restore_pending", False)
        d.setdefault("restores", 0)
        d.setdefault("last_restore", None)
        return d

    def _write(self, d: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def _prune(self, d: dict) -> list[dict]:
        dead = [i for i in d["instances"] if not self.alive(i["pid"], i.get("created"))]
        d["instances"] = [i for i in d["instances"] if i not in dead]
        return dead

    def _restore_if_last(self, d: dict) -> bool:
        if d["instances"] or not d["restore_pending"]:
            return False
        try:
            self.verify_golden()
        except SystemExit as e:  # restore_pending stays set: --restore once golden.reg is right again
            self.log(f"[prefs] RESTORE REFUSED: {e}")
            raise
        if self.keep_after is not None:
            try:
                self.store.export(Path(self.keep_after) / f"after_{datetime.now():%Y%m%d_%H%M%S}.reg")
            except Exception as e:  # forensics only
                self.log(f"[prefs] could not export the pre-restore state: {e}")
        try:
            self.store.restore(self.golden)
        except Exception as e:
            self.log(f"[prefs] RESTORE FAILED ({e}); import {self.golden} manually")
            raise
        d["restore_pending"] = False
        d["restores"] += 1
        d["last_restore"] = datetime.now().isoformat(timespec="seconds")
        self.log(f"[prefs] last instance gone: golden PlayerPrefs restored from {self.golden}")
        return True

    def launch(self, start: Callable[[], tuple[int, float | None]], instance: int) -> int:
        """Run start() (which starts one game process and returns (pid, creation time)) and register it, under the
        lock. A pending restore of an earlier generation (orphaned instances now dead) is done first. Refuses an
        unverified golden.reg, an instance id that is already live (its port, log and sandbox are taken), and game
        processes no launcher registered."""
        self.verify_golden()  # a launch commits to a later restore, so refuse before starting anything
        with self.lock():
            d = self._read()
            self._prune(d)
            same = [i for i in d["instances"] if i["instance"] == instance]
            if same:
                raise SystemExit(f"refusing: instance {instance} is already running (pid {same[0]['pid']}, launcher "
                                 f"{same[0].get('launcher')}): its port {ipc_port(instance)}, log and sandbox saves "
                                 f"are taken; pick other ids with --first")
            registered = {i["pid"] for i in d["instances"]}
            foreign = [p for p in self.game_pids() if p not in registered]
            if foreign:
                raise SystemExit(f"refusing: game process(es) {foreign} were not started by this launcher "
                                 f"(launch_train.ps1, a human session or your own game); their PlayerPrefs write on "
                                 f"exit would race the golden restore. Quit them first")
            self._restore_if_last(d)
            pid, created = start()
            d["instances"].append({"pid": pid, "created": created, "instance": instance, "launcher": os.getpid(),
                                   "started": datetime.now().isoformat(timespec="seconds")})
            d["restore_pending"] = True
            self._write(d)
            return pid

    def release(self, pid: int | None = None) -> bool:
        """Forget pid (it exited) and prune dead entries; restore golden if nothing is left. True if restored."""
        with self.lock():
            d = self._read()
            if pid is not None:
                d["instances"] = [i for i in d["instances"] if i["pid"] != pid]
            self._prune(d)
            try:
                return self._restore_if_last(d)
            finally:
                self._write(d)

    def reconcile(self) -> bool:
        return self.release(None)

    def status(self) -> dict:
        with self.lock():
            return self.peek()

    def peek(self) -> dict:
        """status() without the lock, for read-only checks (compat): instances.json is only ever replaced whole."""
        d = self._read()
        d["live"] = [i for i in d["instances"] if self.alive(i["pid"], i.get("created"))]
        return d

    def make_golden(self, force: bool = False) -> str:
        with self.lock():
            d = self._read()
            self._prune(d)
            if d["instances"]:
                raise SystemExit(f"refusing: {len(d['instances'])} training instance(s) still running")
            if self.golden.exists() and not force:
                raise SystemExit(f"{self.golden} exists; pass --force to replace it")
            self.golden.parent.mkdir(parents=True, exist_ok=True)
            old = None
            if self.golden.exists():  # keep the replaced snapshot: it may be the pinned one
                old = self.golden.with_name(f"{self.golden.stem}.replaced_{datetime.now():%Y%m%d_%H%M%S}.reg")
                os.replace(self.golden, old)
            self.store.export(self.golden)
            d["restore_pending"] = False
            self._write(d)
        values = read_reg_file(self.golden)
        digest = file_sha256(self.golden)
        msg = (f"golden PlayerPrefs written to {self.golden} ({len(values)} values, sha256 {digest})"
               + (f"; previous snapshot kept as {old.name}" if old else ""))
        if self.pin is None:
            return msg + f"\npin it in versions.lock [frozen_settings]: golden_prefs_sha256 = \"{digest}\""
        if self.pin != digest:
            return msg + (f"\nversions.lock pins {self.pin}: set [frozen_settings] golden_prefs_sha256 = \"{digest}\" "
                          f"and commit it; until then launch and restore refuse this snapshot")
        return msg + "; matches versions.lock"


# ---- windows and ports (Win32) -------------------------------------------------------------------------

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)  # a private instance: these prototypes stay local
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    # Full prototypes: without argtypes ctypes passes a Python int as a C int, and a HWND above 0xFFFFFFFF would raise
    # OverflowError (inside the EnumWindows callback it would silently stop the enumeration).
    for _name, _res, _args in (
            ("EnumWindows", wintypes.BOOL, (WNDENUMPROC, wintypes.LPARAM)),
            ("GetWindowThreadProcessId", wintypes.DWORD, (wintypes.HWND, wintypes.LPDWORD)),
            ("IsWindowVisible", wintypes.BOOL, (wintypes.HWND,)),
            ("GetClassNameW", ctypes.c_int, (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)),
            ("GetWindowRect", wintypes.BOOL, (wintypes.HWND, ctypes.POINTER(wintypes.RECT))),
            ("SetWindowPos", wintypes.BOOL, (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                             ctypes.c_int, wintypes.UINT)),
            ("SystemParametersInfoW", wintypes.BOOL, (wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT)),
            ("SetProcessDPIAware", wintypes.BOOL, ())):
        _fn = getattr(user32, _name)
        _fn.restype, _fn.argtypes = _res, _args


def set_dpi_aware() -> None:
    """Window rectangles in physical pixels (the game itself is DPI-aware; a 4K desktop is usually scaled)."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def find_window(pid: int) -> int:
    """The visible Unity top-level window of pid, or 0."""
    found = []

    def cb(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value == "UnityWndClass":
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else 0


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def work_area() -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA (primary monitor)
    return r.left, r.top, r.right, r.bottom


def move_window(hwnd: int, x: int, y: int) -> None:
    SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
    user32.SetWindowPos(hwnd, None, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)


def port_listening(port: int, pid: int | None = None) -> bool:
    """Whether something (pid, if given) listens on 127.0.0.1:port. Reads the TCP table instead of connecting,
    because the oracle serves one brain at a time and a probe connection would briefly take that slot."""
    try:
        import psutil
        for c in psutil.net_connections(kind="tcp4"):
            if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port and (pid is None or c.pid == pid):
                return True
        return False
    except (ImportError, OSError):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False


# ---- launcher ------------------------------------------------------------------------------------------

@dataclass
class Instance:
    index: int
    pid: int
    proc: subprocess.Popen
    port: int
    log: Path
    hwnd: int = 0
    pos: tuple[int, int] | None = None
    ready_s: float | None = None
    exit_code: int | None = None
    released: bool = False
    started: float = field(default_factory=time.monotonic)


class Launcher:
    def __init__(self, game_dir: Path = TRAIN_DIR, *, width: int = 1280, height: int = 720,
                 guard: PrefsGuard | None = None, log_dir: Path = LOG_DIR, tile: bool = True,
                 extra: tuple[str, ...] = (), final_dir: Path = FINAL_DIR, popen=subprocess.Popen,
                 log: Callable[[str], None] = print,
                 listening: Callable[[int, int | None], bool] = port_listening):
        self.game_dir = Path(game_dir)
        self.width, self.height = width, height
        self.guard = guard or PrefsGuard.default()
        self.log_dir = Path(log_dir)
        self.tile = tile
        self.extra = tuple(extra)
        self.final_dir = Path(final_dir)
        self.popen = popen
        self.log = log
        self.listening = listening
        self.instances: list[Instance] = []

    def preflight(self, indices: list[int]) -> None:
        """Fail fast before starting anything (launch() repeats the instance checks under the lock)."""
        assert_training_copy(self.game_dir, self.final_dir)
        self.guard.verify_golden()
        live = self.guard.status()["live"]
        taken = sorted({i["instance"] for i in live} & set(indices))
        if taken:
            raise SystemExit(f"refusing: instance(s) {taken} already running; pick other ids with --first")
        # Instances started by other launchers count too: with single-instance= a second player just activates the
        # first and quits during startup.
        if len(indices) + len(live) > 1 and single_instance_enabled(self.game_dir):
            raise SystemExit(f"{boot_config(self.game_dir)} has single-instance= and {len(live)} instance(s) already "
                             f"running; run --prepare-multi first")
        try:
            diff = prefs_diff(current_prefs(self.guard.store), read_reg_file(self.guard.golden))
            if diff:
                self.log(f"[prefs] WARNING current PlayerPrefs differ from golden in {len(diff)} value(s): "
                         f"{', '.join(diff[:8])}{' ...' if len(diff) > 8 else ''}")
        except (FileNotFoundError, RuntimeError) as e:
            self.log(f"[prefs] could not compare with golden: {e}")

    def start(self, indices: list[int], stagger_timeout_s: float = 120.0) -> list[Instance]:
        """Start the instances one at a time: each waits until the one before it listens on its IPC port (SsOracle
        loads after BepInEx and the other plugins). Started together, two BepInEx preloaders race on
        BepInEx/config/BepInEx.cfg (ConfigFile.Save in the Preloader type initializer); the loser gets a sharing
        violation and runs without mods, so its oracle never listens (preloader_*.log in the game folder; seen
        2026-09-30 with 2 instances). A previous instance that does not listen in time is left to wait_ready."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        exe = self.game_dir / EXE
        prev: Instance | None = None
        for i in indices:
            if prev is not None:
                self._wait_listening(prev, stagger_timeout_s)
            args = build_args(i, self.width, self.height, self.log_dir, self.extra)
            holder: list[subprocess.Popen] = []

            def spawn(args=args) -> tuple[int, float | None]:
                p = self.popen([str(exe), *args], cwd=str(self.game_dir))
                holder.append(p)
                return p.pid, process_created(p.pid)

            pid = self.guard.launch(spawn, i)
            inst = Instance(i, pid, holder[0], ipc_port(i), self.log_dir / f"player_{i}.log")
            self.instances.append(inst)
            self.log(f"[launch] instance {i}: pid {pid}, port {inst.port}, log {inst.log}")
            prev = inst
        return list(self.instances)

    def _wait_listening(self, x: Instance, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if x.proc.poll() is not None or self.listening(x.port, x.pid):
                return True
            time.sleep(0.2)
        self.log(f"[launch] instance {x.index} not listening after {timeout_s:.0f} s; starting the next one anyway")
        return False

    def wait_ready(self, timeout_s: float = 180.0) -> None:
        """Tile each window as it appears (re-applied while Unity settles its own position), then wait for every
        oracle to listen on its IPC port."""
        deadline = time.monotonic() + timeout_s
        pending = [x for x in self.instances if x.ready_s is None]
        slot = None
        area = work_area() if (self.tile and sys.platform == "win32") else None
        placed_at: dict[int, float] = {}
        while pending:
            if time.monotonic() > deadline:
                raise TimeoutError("not ready: " + ", ".join(f"instance {x.index}" for x in pending))
            for x in list(pending):
                if x.proc.poll() is not None:
                    x.exit_code = x.proc.returncode
                    raise RuntimeError(f"instance {x.index} (pid {x.pid}) exited with {x.exit_code} during startup; "
                                       f"see {x.log}")
                if sys.platform == "win32" and not x.hwnd:
                    x.hwnd = find_window(x.pid)
                if area is not None and x.hwnd:
                    l, t, r, b = window_rect(x.hwnd)
                    if slot is None:
                        slot = (r - l, b - t)
                    if x.pos is None:
                        x.pos = tile_positions(x.index - min(i.index for i in self.instances) + 1, *slot, area)[-1]
                    if (l, t) != x.pos and time.monotonic() - placed_at.get(x.index, 0) > 0.25:
                        move_window(x.hwnd, *x.pos)
                        placed_at[x.index] = time.monotonic()
                window_done = area is None or x.hwnd or time.monotonic() - x.started > 30
                if window_done and self.listening(x.port, x.pid):
                    x.ready_s = time.monotonic() - x.started
                    pending.remove(x)
                    self.log(f"[ready] instance {x.index}: port {x.port} listening after {x.ready_s:.1f} s"
                             + (f", window at {x.pos}" if x.pos else ", window not found (not tiled)"
                                if area is not None else ""))
            time.sleep(0.2)

    def wait_exit(self, poll_s: float = 0.5) -> None:
        """Block until every instance exited; each exit is released at once (the last one restores golden)."""
        while any(not x.released for x in self.instances):
            for x in self.instances:
                if not x.released and x.proc.poll() is not None:
                    self._release(x)
            time.sleep(poll_s)

    def _release(self, x: Instance) -> None:
        x.exit_code = x.proc.returncode
        x.released = True
        self.log(f"[exit] instance {x.index} (pid {x.pid}) exited with {x.exit_code}")
        self.guard.release(x.pid)

    def terminate(self, grace_s: float = 10.0) -> None:
        for x in self.instances:
            if x.proc.poll() is None:
                x.proc.terminate()
        deadline = time.monotonic() + grace_s
        for x in self.instances:
            try:
                x.proc.wait(max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                x.proc.kill()
                x.proc.wait()
            if not x.released:
                self._release(x)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.tools.launcher", description=__doc__.split("\n")[0])
    act = ap.add_mutually_exclusive_group(required=True)
    act.add_argument("-n", "--count", type=int, help="launch N instances (instance ids --first .. --first+N-1)")
    act.add_argument("--make-golden", action="store_true",
                     help="export the current PlayerPrefs as golden.reg (then pin its sha256 in versions.lock)")
    act.add_argument("--prepare-multi", action="store_true", help="drop single-instance from the training copy")
    act.add_argument("--unprepare-multi", action="store_true", help="restore the original boot.config")
    act.add_argument("--status", action="store_true", help="show the shared instance registry and golden.reg")
    act.add_argument("--restore", action="store_true", help="prune dead instances; restore golden if none left")
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--game-dir", type=Path, default=TRAIN_DIR)
    ap.add_argument("--prefs-dir", type=Path, default=PREFS_DIR)
    ap.add_argument("--log-dir", type=Path, default=LOG_DIR)
    ap.add_argument("--no-tile", action="store_true")
    ap.add_argument("--ready-timeout", type=float, default=180.0)
    ap.add_argument("--detach", action="store_true", help="return once ready; a later --restore restores prefs")
    ap.add_argument("--force", action="store_true", help="with --make-golden: overwrite")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[], help="more Unity arguments (last)")
    a = ap.parse_args(argv)

    guard = PrefsGuard.default(a.prefs_dir)
    if a.make_golden:
        print(guard.make_golden(a.force))
        return 0
    if a.prepare_multi:
        print(prepare_multi(a.game_dir))
        return 0
    if a.unprepare_multi:
        print(unprepare_multi(a.game_dir))
        return 0
    if a.status:
        s = guard.status()
        s["golden"] = {"path": str(guard.golden), "pin": guard.pin,
                       "sha256": file_sha256(guard.golden) if guard.golden.is_file() else None}
        print(json.dumps(s, indent=1))
        return 0
    if a.restore:
        restored = guard.reconcile()
        s = guard.status()
        print("restored golden" if restored else f"no restore: {len(s['live'])} live, pending {s['restore_pending']}")
        return 0

    set_dpi_aware()
    launcher = Launcher(a.game_dir, width=a.width, height=a.height, guard=guard, log_dir=a.log_dir,
                        tile=not a.no_tile, extra=tuple(a.extra))
    indices = list(range(a.first, a.first + a.count))
    launcher.preflight(indices)
    try:
        launcher.start(indices)
        launcher.wait_ready(a.ready_timeout)
        print(f"{'inst':>4} {'pid':>7} {'port':>6} {'ready s':>8}  window        log")
        for x in launcher.instances:
            print(f"{x.index:>4} {x.pid:>7} {x.port:>6} {x.ready_s or 0:>8.1f}  {str(x.pos):13s} {x.log}")
        if a.detach:
            print("detached: run `python -m ssbot.tools.launcher --restore` after the instances exit")
            return 0
        print("waiting for the instances to exit (Ctrl+C terminates them)")
        launcher.wait_exit()
    except KeyboardInterrupt:
        print("interrupted: terminating instances")
        launcher.terminate()
    except BaseException:
        launcher.terminate()
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
