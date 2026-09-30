"""compat v1: hash comparison of game copies on temp directories, save snapshots, SymbolCheck interpretation."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from ssbot.record.recorder import find_repo_root
from ssbot.tools import compat as C
from ssbot.tools import launcher as L
from tests.fake_oracle import FakeOracle
from tests.test_launcher import VANILLA_BOOT

VANILLA = {
    "Hollow Knight Silksong.exe": b"MZ-exe",
    "UnityPlayer.dll": b"player",
    C.STEAM_API: b"steam-api",
    C.BOOT: VANILLA_BOOT,
    "Hollow Knight Silksong_Data/Managed/Assembly-CSharp.dll": b"game-code",
    "MonoBleedingEdge/etc/mono/config": b"<config/>",
}


def write_tree(root: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def lock():
    m = {k: sha(v) for k, v in VANILLA.items()}
    return {"game": {"file_count": len(m), "tree_sha256": C.tree_sha256(m),
                     "files": {k: m[k] for k in ("Hollow Knight Silksong.exe", C.STEAM_API)}}}


def final_copy(tmp_path: Path) -> Path:
    return write_tree(tmp_path / "final", {**VANILLA, "steam_appid.txt": b"1030300"})


def train_copy(tmp_path: Path) -> Path:
    files = dict(VANILLA)
    files[C.STEAM_DISABLED] = files.pop(C.STEAM_API)
    files.update({"winhttp.dll": b"doorstop", "doorstop_config.ini": b"[General]", ".doorstop_version": b"4.3",
                  "changelog.txt": b"...", "BepInEx/core/BepInEx.dll": b"bep",
                  "BepInEx/plugins/SsOracle/SsOracle.dll": b"oracle", "BepInEx/LogOutput.log": b"log"})
    return write_tree(tmp_path / "train", files)


def test_hash_tree_matches_scripts_hash_game(tmp_path):
    root = write_tree(tmp_path / "g", VANILLA)
    script = find_repo_root() / "scripts" / "hash_game.py"
    spec = importlib.util.spec_from_file_location("hash_game", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert C.hash_tree(root) == mod.hash_tree(root)


def test_tree_sha256_convention():
    m = {"b": "2", "a": "1"}
    assert C.tree_sha256(m) == hashlib.sha256(b'{"a": "1", "b": "2"}').hexdigest()


def test_real_versions_lock_parses():
    lock = C.load_lock()
    assert lock["game"]["version"] == "1.0.30000" and lock["game"]["file_count"] == 2268
    assert set(lock["copies"]) == {"final", "train"}


def test_final_copy_ok_and_violations(tmp_path, lock):
    root = final_copy(tmp_path)
    r = C.check_copy("final", root, lock)
    assert r.status == "OK", r.detail
    (root / "winhttp.dll").write_bytes(b"x")
    (root / "BepInEx").mkdir()
    (root / "BepInEx" / "a.dll").write_bytes(b"x")
    r = C.check_copy("final", root, lock)
    assert r.status == "FAIL" and "winhttp.dll" in r.detail and "BepInEx/" in r.detail


def test_final_copy_needs_steam_appid(tmp_path, lock):
    root = final_copy(tmp_path)
    (root / "steam_appid.txt").unlink()
    assert "steam_appid.txt missing" in C.check_copy("final", root, lock).detail
    (root / "steam_appid.txt").write_text("123")
    assert "expected 1030300" in C.check_copy("final", root, lock).detail


def test_modified_vanilla_file_is_named_with_reference(tmp_path, lock):
    root = final_copy(tmp_path)
    ref = {k: sha(v) for k, v in VANILLA.items()}
    (root / "Hollow Knight Silksong_Data/Managed/Assembly-CSharp.dll").write_bytes(b"patched")
    r = C.check_copy("final", root, lock, reference=ref)
    assert r.status == "FAIL" and "tree_sha256 differs" in r.detail and "Assembly-CSharp.dll" in r.detail
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({**ref, "steam_appid.txt": "x"}))
    assert C.load_reference(lock, manifest) == ref
    manifest.write_text(json.dumps({**ref, "extra": "x"}))
    assert C.load_reference(lock, manifest) is None  # untrusted: does not hash to the pinned tree


def test_train_copy_ok_with_loader_and_detached_steam(tmp_path, lock):
    root = train_copy(tmp_path)
    r = C.check_copy("train", root, lock)
    assert r.status == "OK", r.detail
    assert r.data["loader_files"] == 7 and r.data["plugins"] == ["SsOracle"] and r.data["steam"] == "detached"


def test_train_copy_prepared_for_multi_instance_still_matches(tmp_path, lock):
    root = train_copy(tmp_path)
    L.prepare_multi(root, final_dir=tmp_path / "final")
    r = C.check_copy("train", root, lock)
    assert r.status == "OK", r.detail and "multi-instance" in r.data["boot_config"]
    (root / C.BOOT).write_bytes(VANILLA_BOOT.replace(b"hdr-display-enabled=0", b"hdr-display-enabled=1")
                                .replace(b"single-instance=\n", b""))
    r = C.check_copy("train", root, lock)
    assert r.status == "FAIL" and "more than the single-instance line" in r.detail


def test_train_copy_with_steam_api_back_fails(tmp_path, lock):
    root = train_copy(tmp_path)
    (root / C.STEAM_DISABLED).rename(root / C.STEAM_API)
    r = C.check_copy("train", root, lock)
    assert r.status == "FAIL" and "not detached" in r.detail


def test_train_copy_extra_vanilla_side_file_fails(tmp_path, lock):
    root = train_copy(tmp_path)
    (root / "Hollow Knight Silksong_Data" / "stray.txt").write_bytes(b"x")
    r = C.check_copy("train", root, lock)
    assert r.status == "FAIL" and "vanilla files" in r.detail


def test_missing_copy_fails(tmp_path, lock):
    assert C.check_copy("final", tmp_path / "nope", lock).status == "FAIL"


def test_saves_snapshot_and_verify(tmp_path):
    ll = write_tree(tmp_path / "LocalLow", {"122627504/user1.dat": b"a", "122627504/shared.dat": b"s",
                                            "DebugModData/x.json": b"{}", "Player.log": b"log"})
    before = C.snapshot_saves(ll)
    assert list(before["dirs"]) == ["122627504"] and not before["default_exists"]
    assert C.diff_saves(before, C.snapshot_saves(ll)) == []
    (ll / "Player.log").write_bytes(b"changed")  # outside the AccountID folder: irrelevant
    (ll / "122627504" / "user1.dat").write_bytes(b"b")
    (ll / "122627504" / "user2.dat").write_bytes(b"new")
    assert C.diff_saves(before, C.snapshot_saves(ll)) == ["122627504/user1.dat changed", "122627504/user2.dat added"]
    assert C.main(["snapshot", "--locallow", str(ll), "--snapshot", str(tmp_path / "s.json")]) == 0
    assert C.main(["verify", "--locallow", str(ll), "--snapshot", str(tmp_path / "s.json")]) == 0
    (ll / "122627504" / "shared.dat").unlink()
    assert C.main(["verify", "--locallow", str(ll), "--snapshot", str(tmp_path / "s.json")]) == 1


def test_default_folder_must_not_exist(tmp_path):
    assert C.check_default_absent(tmp_path).status == "OK"
    (tmp_path / "default").mkdir()
    assert C.check_default_absent(tmp_path).status == "FAIL"


@pytest.mark.parametrize("res,ok", [
    (True, True), (False, False),
    ({"ok": True, "total": 150, "failed": []}, True),
    ({"total": 150, "missing": ["HeroController.cState"]}, False),
    ({"ok": False, "checked": 3}, False),
    ([], True), (["GameManager.PlayTime"], False),
    ("weird", None),
])
def test_interpret_symbols(res, ok):
    assert C.interpret_symbols(res)[0] is ok


def test_symbols_rpc_through_oracle():
    fo = FakeOracle(symbols={"ok": False, "total": 150, "failed": ["DamageHero._damageHeroes"]})
    try:
        r = C.check_symbols(fo.instance, rpc_timeout_s=5)
    finally:
        fo.close()
    assert r.status == "FAIL" and "DamageHero._damageHeroes" in r.detail


def test_symbols_skipped_without_oracle():
    assert C.check_symbols(instance=18000).status == "SKIP"  # port 65017: nothing listens there


def test_disk_threshold(tmp_path):
    assert C.check_disk([tmp_path], min_gb=0).status == "OK"
    assert C.check_disk([tmp_path / "not" / "yet"], min_gb=1e9).status == "FAIL"


def test_prefs_check_without_golden_only_warns(tmp_path):
    assert C.check_prefs(tmp_path / "golden.reg").status in ("WARN", "SKIP")


def test_table_and_exit_code(capsys):
    rs = [C.Result("a", "OK", "fine"), C.Result("longer name", "WARN", "hmm"), C.Result("b", "SKIP")]
    C.print_table(rs)
    out = capsys.readouterr().out
    assert "longer name  WARN    hmm" in out and C.exit_code(rs) == 0
    assert C.exit_code(rs + [C.Result("c", "FAIL")]) == 1
