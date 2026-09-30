"""Launcher argument building, tiling, boot.config handling and the golden-PlayerPrefs locking logic.
No real registry writes: PrefsStore is replaced by an in-memory fake."""
import threading
from pathlib import Path

import pytest

from ssbot.tools import launcher as L

VANILLA_BOOT = (b"gfx-threading-mode=6\nwait-for-native-debugger=0\nhdr-display-enabled=0\nsingle-instance=\n"
                b"build-guid=0dfec00986fe4558b8f6fcfdb38ba4b1\n")


class FakeStore:
    """PlayerPrefs as a dict, exported/imported as UTF-16 .reg files like reg.exe does."""

    def __init__(self, values: dict[str, str]):
        self.values = dict(values)
        self.exports = 0
        self.restores = 0
        self.log: list[str] = []
        self.lock = threading.Lock()

    def export(self, path: Path) -> None:
        lines = ["Windows Registry Editor Version 5.00", "", f"[{L.PREFS_KEY.replace('HKCU', 'HKEY_CURRENT_USER')}]"]
        lines += [f'"{k}"={v}' for k, v in self.values.items()]
        Path(path).write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-16"))
        self.exports += 1
        self.log.append("export")

    def restore(self, path: Path) -> None:
        with self.lock:
            self.values = L.read_reg_file(path)
            self.restores += 1
            self.log.append("restore")


GOLDEN = {"GameLang_h509519951": "dword:0000002c", "KeyJump_h1034415184": "hex:5a,00",
          "unity.player_session_count_h922449978": "hex:35,00"}


@pytest.fixture
def prefs(tmp_path):
    store = FakeStore(GOLDEN)
    live: set[int] = set()
    guard = L.PrefsGuard(store, tmp_path / "golden.reg", tmp_path / "instances.json", tmp_path / "instances.lock",
                         alive=lambda pid, created: pid in live, log=lambda s: None, keep_after=tmp_path,
                         game_pids=lambda: sorted(live))  # every game process is one this registry started
    store.export(guard.golden)
    store.exports = 0
    return store, guard, live


def start(live: set[int], pid: int):
    def fn():
        live.add(pid)
        return pid, 1000.0 + pid
    return fn


def test_build_args():
    assert L.build_args(2, 1280, 720, Path(r"C:\ssbot\sandbox\logs"), ("-nolog",)) == [
        "-ssbot-instance", "2", "-logFile", r"C:\ssbot\sandbox\logs\player_2.log",
        "-screen-fullscreen", "0", "-screen-width", "1280", "-screen-height", "720", "-nolog"]


def test_tile_positions_grid_then_cascade():
    area = (0, 0, 3840, 2300)  # 2 columns x 3 rows of 1296 x 759
    pos = L.tile_positions(7, 1296, 759, area)
    assert pos[:6] == [(0, 0), (1296, 0), (0, 759), (1296, 759), (0, 1518), (1296, 1518)]
    assert pos[6] == (40, 40)  # grid (2 x 3) full: next layer cascades
    assert L.tile_positions(2, 5000, 5000, (100, 50, 900, 700)) == [(100, 50), (140, 90)]


def fake_game(root: Path, boot: bytes = VANILLA_BOOT, loader: bool = True) -> Path:
    (root / L.DATA).mkdir(parents=True)
    (root / L.EXE).write_bytes(b"MZ")
    (root / L.BOOT_CONFIG).write_bytes(boot)
    if loader:
        (root / "BepInEx" / "core").mkdir(parents=True)
    return root


def test_single_instance_detection_and_prepare(tmp_path):
    game = fake_game(tmp_path / "train")
    final = tmp_path / "final"
    assert L.single_instance_enabled(game)
    msg = L.prepare_multi(game, final)
    assert "removed" in msg and not L.single_instance_enabled(game)
    after = (game / L.BOOT_CONFIG).read_bytes()
    assert after == VANILLA_BOOT.replace(b"single-instance=\n", b"")
    backup = game / (L.BOOT_CONFIG + L.BOOT_BACKUP_SUFFIX)
    assert backup.read_bytes() == VANILLA_BOOT
    assert "already absent" in L.prepare_multi(game, final)
    assert backup.read_bytes() == VANILLA_BOOT  # a second run never overwrites the vanilla backup
    L.unprepare_multi(game, final)
    assert (game / L.BOOT_CONFIG).read_bytes() == VANILLA_BOOT and not backup.exists()


def test_prepare_refuses_final_and_non_training_copies(tmp_path):
    game = fake_game(tmp_path / "train")
    with pytest.raises(SystemExit):
        L.prepare_multi(game, final_dir=game)
    vanilla = fake_game(tmp_path / "vanilla", loader=False)
    with pytest.raises(SystemExit):
        L.prepare_multi(vanilla, final_dir=tmp_path / "final")
    assert (game / L.BOOT_CONFIG).read_bytes() == VANILLA_BOOT
    assert (vanilla / L.BOOT_CONFIG).read_bytes() == VANILLA_BOOT


def test_parse_reg_and_diff_ignore_session_counters():
    text = ('Windows Registry Editor Version 5.00\r\n\r\n[HKEY_CURRENT_USER\\Software\\X]\r\n'
            '"a"=dword:00000001\r\n"unity.player_sessionid_h1351336811"=hex:33,30,\\\r\n  35,00\r\n'
            '"unity.player_session_count_h922449978"=hex:35,00\r\n'
            '"b"=hex:5a,\\\r\n  00\r\n')
    v = L.parse_reg(text)
    assert v == {"a": "dword:00000001", "unity.player_sessionid_h1351336811": "hex:33,30,35,00",
                 "unity.player_session_count_h922449978": "hex:35,00", "b": "hex:5a,00"}
    w = dict(v, **{"unity.player_sessionid_h1351336811": "hex:00", "a": "dword:00000002"})
    assert L.prefs_diff(v, w) == ["a"]
    # Unity bumps both counters on every launch: neither is a settings difference nor changes the digest.
    bumped = dict(v, **{"unity.player_sessionid_h1351336811": "hex:00",
                        "unity.player_session_count_h922449978": "hex:36,00"})
    assert L.prefs_diff(v, bumped) == []
    assert L.prefs_digest(v) == L.prefs_digest(dict(reversed(list(bumped.items())))) != L.prefs_digest(w)
    assert not L.VOLATILE_PREFS.match("unity.player_session_countx_h1") and not L.VOLATILE_PREFS.match("GameLang_h1")


def test_restores_once_when_last_instance_exits(prefs):
    store, guard, live = prefs
    guard.launch(start(live, 1), 0)
    guard.launch(start(live, 2), 1)
    store.values["Screenmanager Resolution Width_h182942802"] = "dword:00000500"  # Unity writes on exit
    live.discard(1)
    assert guard.release(1) is False and store.restores == 0
    live.discard(2)
    assert guard.release(2) is True and store.restores == 1
    assert store.values == GOLDEN
    assert guard.release(2) is False and guard.reconcile() is False and store.restores == 1
    st = guard.status()
    assert st["instances"] == [] and not st["restore_pending"] and st["restores"] == 1


def test_two_launchers_share_one_registry(prefs, tmp_path):
    store, a, live = prefs
    b = L.PrefsGuard(store, a.golden, a.state_path, a.lock_path, alive=a.alive, log=lambda s: None,
                     game_pids=a.game_pids)
    a.launch(start(live, 11), 0)
    b.launch(start(live, 21), 4)
    live.discard(11)
    assert a.release(11) is False  # launcher B's instance is still running
    live.discard(21)
    assert b.release(21) is True and store.restores == 1


def test_concurrent_releases_restore_exactly_once(prefs):
    store, guard, live = prefs
    pids = list(range(100, 108))
    for i, pid in enumerate(pids):
        guard.launch(start(live, pid), i)
    barrier = threading.Barrier(len(pids))
    results = []

    def exit_and_release(pid):
        barrier.wait()
        live.discard(pid)
        results.append(guard.release(pid))

    threads = [threading.Thread(target=exit_and_release, args=(p,)) for p in pids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert results.count(True) == 1 and store.restores == 1


def test_orphans_of_a_killed_launcher_are_pruned_and_restored(prefs):
    store, guard, live = prefs
    guard.launch(start(live, 5), 0)
    live.discard(5)  # the game exited but its launcher died before releasing it
    order = []
    store_restore = store.restore
    store.restore = lambda p: (order.append("restore"), store_restore(p))

    def spawn():
        order.append("start")
        live.add(6)
        return 6, None

    guard.launch(spawn, 0)  # the next launcher restores the previous generation before starting
    assert order == ["restore", "start"] and store.restores == 1
    assert [i["pid"] for i in guard.status()["instances"]] == [6]
    live.discard(6)
    assert guard.reconcile() is True and store.restores == 2


def test_launch_requires_golden(tmp_path):
    guard = L.PrefsGuard(FakeStore({}), tmp_path / "missing.reg", tmp_path / "i.json", tmp_path / "i.lock",
                         alive=lambda *_: True, log=lambda s: None, game_pids=lambda: [])
    with pytest.raises(SystemExit):
        guard.launch(lambda: (1, None), 0)


def test_same_instance_id_is_refused_while_live(prefs):
    store, guard, live = prefs
    guard.launch(start(live, 1), 0)
    with pytest.raises(SystemExit, match="instance 0 is already running"):
        guard.launch(start(live, 2), 0)  # a second `-n 2` with the default --first 0
    assert 2 not in live and [i["pid"] for i in guard.status()["instances"]] == [1]
    guard.launch(start(live, 3), 1)
    live.discard(1)
    guard.launch(start(live, 4), 0)  # id 0 is free again once its process is gone


def test_unregistered_game_process_blocks_launch(prefs):
    store, guard, live = prefs
    others = [4242]  # e.g. launch_train.ps1 or a human session
    guard.game_pids = lambda: sorted(live | set(others))
    with pytest.raises(SystemExit, match="4242"):
        guard.launch(start(live, 1), 0)
    assert not live and store.restores == 0
    others.clear()
    guard.launch(start(live, 1), 0)
    guard.launch(start(live, 2), 1)  # this registry's own instances are not foreign


def test_golden_pin_is_enforced_on_launch_and_restore(prefs):
    store, guard, live = prefs
    guard.pin = L.file_sha256(guard.golden)
    guard.launch(start(live, 1), 0)
    original = guard.golden.read_bytes()
    guard.golden.write_bytes(original + b"\r\n")  # replaced or corrupted snapshot
    live.discard(1)
    with pytest.raises(SystemExit, match="golden_prefs_sha256"):
        guard.release(1)
    st = guard.status()
    assert store.restores == 0 and st["restore_pending"] and st["instances"] == []
    with pytest.raises(SystemExit):
        guard.launch(start(live, 2), 0)  # a launch would commit to a restore that must be refused
    assert 2 not in live
    guard.golden.write_bytes(original)
    assert guard.reconcile() is True and store.restores == 1


def test_golden_pin_from_versions_lock(tmp_path):
    golden = tmp_path / "golden.reg"
    lock = {"frozen_settings": {"golden_prefs": str(golden), "golden_prefs_sha256": "ABC123"}}
    assert L.golden_pin(golden, lock) == "abc123"
    assert L.golden_pin(tmp_path / "other.reg", lock) is None  # the pin is for another file
    assert L.golden_pin(golden, {"frozen_settings": {"golden_prefs_sha256": "abc"}}) == "abc"
    assert L.golden_pin(golden, {"frozen_settings": {}}) is None and L.golden_pin(golden, {}) is None
    pin = L.golden_pin(L.PREFS_DIR / "golden.reg")  # the repo's own versions.lock
    assert pin is None or len(pin) == 64


def test_make_golden_guards(prefs):
    store, guard, live = prefs
    with pytest.raises(SystemExit):
        guard.make_golden()  # exists
    guard.launch(start(live, 9), 0)
    with pytest.raises(SystemExit):
        guard.make_golden(force=True)  # an instance is running
    live.discard(9)
    store.values["x"] = "dword:00000001"
    old = L.file_sha256(guard.golden)
    guard.pin = old
    msg = guard.make_golden(force=True)
    new = L.file_sha256(guard.golden)
    assert "golden PlayerPrefs written" in msg and new in msg and f'golden_prefs_sha256 = "{new}"' in msg
    assert L.read_reg_file(guard.golden)["x"] == "dword:00000001"
    assert not guard.status()["restore_pending"]
    kept = list(guard.golden.parent.glob("golden.replaced_*.reg"))
    assert len(kept) == 1 and L.file_sha256(kept[0]) == old  # the pinned snapshot is never lost
    with pytest.raises(SystemExit, match="golden_prefs_sha256"):
        guard.launch(start(live, 10), 0)  # until versions.lock pins the new file
    guard.pin = new
    guard.launch(start(live, 10), 0)


def test_file_lock_excludes_other_holders(tmp_path):
    p = tmp_path / "x.lock"
    with L.FileLock(p):
        with pytest.raises(TimeoutError):
            with L.FileLock(p, timeout_s=0.2):
                pass
    with L.FileLock(p, timeout_s=0.2):
        pass


class FakePopen:
    next_pid = 900_001
    calls: list = []
    by_pid: dict = {}

    def __init__(self, argv, cwd=None):
        FakePopen.calls.append((argv, cwd))
        self.pid = FakePopen.next_pid
        FakePopen.next_pid += 1
        FakePopen.by_pid[self.pid] = self
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 1

    def kill(self):
        self.returncode = 1

    def wait(self, timeout=None):
        return self.returncode


def test_launcher_starts_registers_and_restores_on_exit(prefs, tmp_path):
    store, guard, _ = prefs
    guard.alive = lambda pid, created: pid in FakePopen.by_pid and FakePopen.by_pid[pid].returncode is None
    game = fake_game(tmp_path / "train")
    FakePopen.calls = []
    ln = L.Launcher(game, width=640, height=360, guard=guard, log_dir=tmp_path / "logs", tile=False,
                    final_dir=tmp_path / "final", popen=FakePopen, log=lambda s: None)
    with pytest.raises(SystemExit):
        ln.preflight([0, 1])  # boot.config still has single-instance
    ln.preflight([0])
    L.prepare_multi(game, tmp_path / "final")
    ln.preflight([0, 1])
    insts = ln.start([0, 1])
    with pytest.raises(SystemExit, match=r"\[1\] already running"):
        ln.preflight([1, 2])  # a second launcher with overlapping ids
    argv, cwd = FakePopen.calls[1]
    assert argv[0] == str(game / L.EXE) and cwd == str(game)
    assert argv[1:] == L.build_args(1, 640, 360, tmp_path / "logs")
    assert [i["instance"] for i in guard.status()["instances"]] == [0, 1]
    for x in insts:
        x.proc.returncode = 0
    ln.wait_exit(poll_s=0.01)
    assert store.restores == 1 and all(x.released for x in insts)


def test_preflight_counts_instances_of_other_launchers(prefs, tmp_path):
    store, guard, live = prefs
    game = fake_game(tmp_path / "train")  # boot.config still has single-instance=
    ln = L.Launcher(game, guard=guard, log_dir=tmp_path / "logs", tile=False, final_dir=tmp_path / "final",
                    popen=FakePopen, log=lambda s: None)
    ln.preflight([0])  # alone: single-instance does no harm
    guard.launch(start(live, 77), 3)  # another launcher's instance
    with pytest.raises(SystemExit, match="single-instance"):
        ln.preflight([0])  # a second player would activate the first and quit during startup
    L.prepare_multi(game, tmp_path / "final")
    ln.preflight([0])


@pytest.mark.skipif(L.sys.platform != "win32", reason="Win32 window API")
def test_window_api_takes_64_bit_handles():
    bogus = 0xFFFFFFFF80001234  # above 32 bits: without argtypes ctypes raised OverflowError
    assert not L.user32.IsWindowVisible(bogus)
    assert L.window_rect(bogus) == (0, 0, 0, 0)
    L.move_window(bogus, 10, 10)  # fails quietly (invalid handle), no exception
    assert L.find_window(0xFFFFFFF0) == 0  # a full enumeration completes
