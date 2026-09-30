"""compat v1 (DESIGN §3.10 compat suite): items 1 (game copies vs versions.lock, no loader in FINAL), 2 without the
options-page OCR (golden PlayerPrefs hash pinned in versions.lock; current PlayerPrefs vs golden, which FAILs only
under --profile FINAL/VANILLA), 3 (SymbolCheck through the oracle), 7 (real save folder unchanged, real `default`
absent) and part of 8 (disk, microcode, gamepads).

    python -m ssbot.tools.compat                 # full check; exit 1 on any FAIL; prints a table
    python -m ssbot.tools.compat --profile FINAL # before a FINAL/VANILLA session: PlayerPrefs must be golden
    python -m ssbot.tools.compat --quick         # skip hashing the two 7.7 GB game copies
    python -m ssbot.tools.compat snapshot        # before a session: hash the real <AccountID> save folder(s)
    python -m ssbot.tools.compat verify          # after a session: fail if anything there changed

Game-copy rules (versions.lock [copies]): the FINAL copy is the vanilla depot plus steam_appid.txt and must not carry
winhttp.dll, doorstop_config.ini, .doorstop_version or BepInEx/. The TRAIN copy's vanilla files must match except
the renamed steam_api64.dll (-> .disabled, D15), the added loader files, and a boot.config without `single-instance=`
(launcher --prepare-multi) whose backup holds the vanilla bytes. Each copy is reduced to a "vanilla view" and its
tree hash (sha256 of json.dumps(sorted map), the scripts/hash_game.py convention) compared with versions.lock.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tomllib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ssbot.record.recorder import find_repo_root

STEAM_API = "Hollow Knight Silksong_Data/Plugins/x86_64/steam_api64.dll"
STEAM_DISABLED = STEAM_API + ".disabled"
BOOT = "Hollow Knight Silksong_Data/boot.config"
BOOT_BACKUP = BOOT + ".ssbot-orig"
LOADER_FILES = frozenset({"winhttp.dll", "doorstop_config.ini", ".doorstop_version", "changelog.txt"})
LOADER_DIR = "BepInEx/"
FINAL_FORBIDDEN = frozenset({"winhttp.dll", "doorstop_config.ini", ".doorstop_version"})
FINAL_EXTRA = "steam_appid.txt"
STEAM_APP_ID = "1030300"
LOCALLOW = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "AppData/LocalLow/Team Cherry/Hollow Knight Silksong"
SNAPSHOT = Path(r"C:\ssbot\sandbox\compat\saves_snapshot.json")
GOLDEN_PREFS = Path(r"C:\ssbot\sandbox\prefs\golden.reg")
REFERENCE_MANIFEST = Path(r"C:\ssbot\tools\hash_final.json")
MIN_FREE_GB = 10.0
MIN_MICROCODE = 0x12B  # DESIGN §2.6 hardware: 13th-gen Vmin fix
STRICT_PREFS_PROFILES = frozenset({"FINAL", "VANILLA"})  # final-copy sessions: PlayerPrefs must be golden (§2.7)


@dataclass
class Result:
    name: str
    status: str            # OK | FAIL | WARN | SKIP | INFO
    detail: str = ""
    data: dict = field(default_factory=dict)


# ---- hashing (same output as scripts/hash_game.py) -----------------------------------------------------

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_tree(root: Path, workers: int = 8) -> dict[str, str]:
    """{relative posix path: sha256} for every file under root; files hashed in parallel (hashlib drops the GIL)."""
    root = Path(root)
    files = sorted(p for p in root.rglob("*") if p.is_file())
    with ThreadPoolExecutor(workers) as ex:
        digests = list(ex.map(_sha256, files))
    return {p.relative_to(root).as_posix(): d for p, d in zip(files, digests)}


def tree_sha256(m: dict[str, str]) -> str:
    """The versions.lock tree_sha256 convention: sha256 over json.dumps(map, sort_keys=True)."""
    return hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()


def load_lock(path: Path | None = None) -> dict:
    if path is None:
        root = find_repo_root()
        if root is None:
            raise FileNotFoundError("versions.lock not found")
        path = root / "versions.lock"
    return tomllib.loads(Path(path).read_text("utf-8"))


# ---- copy -> vanilla view ------------------------------------------------------------------------------

def final_view(m: dict[str, str], root: Path | None = None) -> tuple[dict[str, str], list[str], dict]:
    """(vanilla map, problems, notes) for the FINAL copy."""
    problems = []
    for name in sorted(FINAL_FORBIDDEN & m.keys()):
        problems.append(f"loader file present: {name}")
    loader = [k for k in m if k.startswith(LOADER_DIR)]
    if loader:
        problems.append(f"BepInEx/ present ({len(loader)} files)")
    if FINAL_EXTRA not in m:
        problems.append(f"{FINAL_EXTRA} missing (the game restarts through Steam without it, m0:N28)")
    elif root is not None:
        app_id = (Path(root) / FINAL_EXTRA).read_text("utf-8", errors="replace").strip()
        if app_id != STEAM_APP_ID:
            problems.append(f"{FINAL_EXTRA} is {app_id!r}, expected {STEAM_APP_ID}")
    view = {k: v for k, v in m.items() if k != FINAL_EXTRA}
    return view, problems, {}


def _without_single_instance(data: bytes) -> bytes:
    return b"".join(line for line in data.splitlines(keepends=True)
                    if line.split(b"=", 1)[0].strip() != b"single-instance")


def train_view(m: dict[str, str], root: Path | None = None) -> tuple[dict[str, str], list[str], dict]:
    """(vanilla map, problems, notes) for the TRAIN copy: undo the allowed modifications."""
    problems = []
    notes: dict[str, Any] = {}
    view = {}
    loader = []
    for k, v in m.items():
        if k in LOADER_FILES or k.startswith(LOADER_DIR):
            loader.append(k)
        else:
            view[k] = v
    notes["loader_files"] = len(loader)
    if "winhttp.dll" not in m or not any(k.startswith(LOADER_DIR + "core/") for k in m):
        problems.append("BepInEx loader incomplete (winhttp.dll or BepInEx/core missing)")
    plugins = sorted({k.split("/")[2] for k in loader if k.startswith(LOADER_DIR + "plugins/") and k.count("/") >= 3})
    notes["plugins"] = plugins

    if STEAM_API in view:
        problems.append("steam_api64.dll present: the Steam subsystem is not detached (D15)")
    if STEAM_DISABLED in view:
        view[STEAM_API] = view.pop(STEAM_DISABLED)
        notes["steam"] = "detached"
    else:
        problems.append("steam_api64.dll.disabled missing")

    if BOOT_BACKUP in view:
        backup_hash = view.pop(BOOT_BACKUP)
        notes["boot_config"] = "multi-instance (single-instance removed)"
        if root is not None:
            cur = (Path(root) / BOOT).read_bytes() if BOOT in view else b""
            orig = (Path(root) / BOOT_BACKUP).read_bytes()
            if cur != _without_single_instance(orig):
                problems.append("boot.config differs from its backup by more than the single-instance line")
        view[BOOT] = backup_hash
    else:
        notes["boot_config"] = "vanilla (single-instance)"
    return view, problems, notes


def compare_to_lock(view: dict[str, str], lock: dict, reference: dict[str, str] | None = None) -> list[str]:
    game = lock.get("game", {})
    problems = []
    if game.get("file_count") is not None and len(view) != game["file_count"]:
        problems.append(f"{len(view)} vanilla files, versions.lock says {game['file_count']}")
    for name, want in game.get("files", {}).items():
        got = view.get(name)
        if got != want:
            problems.append(f"{name}: {'missing' if got is None else got[:12] + '…'} != {want[:12]}…")
    if game.get("tree_sha256") and tree_sha256(view) != game["tree_sha256"]:
        msg = "tree_sha256 differs from versions.lock"
        if reference is not None:
            changed = sorted(k for k in view.keys() & reference.keys() if view[k] != reference[k])
            missing = sorted(reference.keys() - view.keys())
            extra = sorted(view.keys() - reference.keys())
            parts = [f"{len(changed)} changed", f"{len(missing)} missing", f"{len(extra)} extra"]
            sample = (changed + missing + extra)[:5]
            msg += f" ({', '.join(parts)}: {', '.join(sample)})"
        problems.append(msg)
    return problems


def load_reference(lock: dict, path: Path = REFERENCE_MANIFEST) -> dict[str, str] | None:
    """A per-file manifest (scripts/hash_game.py output) to name differing files; trusted only if it hashes to
    the pinned tree_sha256."""
    try:
        ref = json.loads(Path(path).read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    ref = {k: v for k, v in ref.items() if k != FINAL_EXTRA}
    return ref if tree_sha256(ref) == lock.get("game", {}).get("tree_sha256") else None


def check_copy(kind: str, root: Path, lock: dict, reference: dict[str, str] | None = None,
               hasher: Callable[[Path], dict[str, str]] = hash_tree) -> Result:
    name = f"{kind} copy"
    root = Path(root)
    if not root.is_dir():
        return Result(name, "FAIL", f"{root} does not exist")
    m = hasher(root)
    view, problems, notes = (final_view if kind == "final" else train_view)(m, root)
    problems += compare_to_lock(view, lock, reference)
    data = {"root": str(root), "files": len(m), "tree_sha256": tree_sha256(view), **notes}
    if problems:
        return Result(name, "FAIL", "; ".join(problems), data)
    extra = f", {notes['loader_files']} loader files, steam {notes.get('steam')}, boot.config {notes.get('boot_config')}" \
        if kind == "train" else ", steam_appid.txt ok, no loader"
    return Result(name, "OK", f"{len(view)} vanilla files match versions.lock{extra}", data)


# ---- saves -----------------------------------------------------------------------------------------------

def save_dirs(locallow: Path = LOCALLOW) -> list[Path]:
    """The real save folders: named by the 32-bit Steam AccountID (m0:C14)."""
    if not locallow.is_dir():
        return []
    return sorted(p for p in locallow.iterdir() if p.is_dir() and p.name.isdigit())


def snapshot_saves(locallow: Path = LOCALLOW) -> dict:
    dirs = {}
    for d in save_dirs(locallow):
        files = hash_tree(d)
        dirs[d.name] = {"tree_sha256": tree_sha256(files), "files": files}
    return {"taken": datetime.now().isoformat(timespec="seconds"), "root": str(locallow), "dirs": dirs,
            "default_exists": (locallow / "default").exists()}


def diff_saves(before: dict, after: dict) -> list[str]:
    diffs = []
    for name in sorted(before["dirs"].keys() | after["dirs"].keys()):
        a = before["dirs"].get(name, {}).get("files")
        b = after["dirs"].get(name, {}).get("files")
        if a is None or b is None:
            diffs.append(f"{name}/ {'appeared' if a is None else 'disappeared'}")
            continue
        for f in sorted(a.keys() | b.keys()):
            if a.get(f) != b.get(f):
                what = "added" if f not in a else "removed" if f not in b else "changed"
                diffs.append(f"{name}/{f} {what}")
    return diffs


def check_default_absent(locallow: Path = LOCALLOW) -> Result:
    d = locallow / "default"
    if d.exists():
        n = sum(1 for p in d.rglob("*") if p.is_file()) if d.is_dir() else 1
        return Result("LocalLow default", "FAIL", f"{d} exists ({n} files): the final copy's Steam init failed or "
                      f"saves escaped the sandbox (m0:N28)")
    return Result("LocalLow default", "OK", f"{d} absent")


def check_saves_info(locallow: Path = LOCALLOW) -> Result:
    dirs = save_dirs(locallow)
    if not dirs:
        return Result("real saves", "INFO", f"no <AccountID> folder under {locallow}")
    snap = snapshot_saves(locallow)
    parts = [f"{n}: {len(v['files'])} files {v['tree_sha256'][:12]}" for n, v in snap["dirs"].items()]
    return Result("real saves", "INFO", "; ".join(parts), {"dirs": {n: v["tree_sha256"] for n, v in snap["dirs"].items()}})


# ---- oracle SymbolCheck ------------------------------------------------------------------------------------

def interpret_symbols(res: Any) -> tuple[bool | None, str]:
    """The symbols.check result shape belongs to the oracle package; accept the plausible ones."""
    if isinstance(res, bool):
        return res, "ok" if res else "failed"
    if isinstance(res, dict):
        failed = res.get("failed") or res.get("missing") or res.get("errors") or []
        ok = res.get("ok")
        ok = (not failed) if ok is None else bool(ok)
        total = res.get("total", res.get("checked", res.get("count")))
        shown = ", ".join(map(str, failed[:5])) if isinstance(failed, list) else str(failed)
        return ok, f"{total if total is not None else '?'} symbols, {len(failed) if isinstance(failed, list) else '?'} " \
                   f"failed{': ' + shown if failed else ''}"
    if isinstance(res, list):
        return not res, f"{len(res)} failed{': ' + ', '.join(map(str, res[:5])) if res else ''}"
    return None, repr(res)[:200]


def check_symbols(instance: int = 0, rpc_timeout_s: float = 60.0) -> Result:
    from ssbot.ipc.framing import port
    from ssbot.ipc.oracle_link import OracleError, OracleLink
    from ssbot.tools.launcher import port_listening

    p = port(instance)
    if not port_listening(p):
        return Result("SymbolCheck", "SKIP", f"no oracle listening on 127.0.0.1:{p}")
    try:
        link = OracleLink(instance=instance, connect_timeout_s=3)
    except (OSError, OracleError) as e:
        return Result("SymbolCheck", "SKIP", f"oracle on {p} did not handshake (another brain connected?): {e}")
    try:
        if "symbols.check" not in (link.hello or {}).get("rpcs", []):
            return Result("SymbolCheck", "WARN", f"oracle {link.hello.get('plugin')} has no symbols.check RPC")
        ok, detail = interpret_symbols(link.rpc("symbols.check", timeout_s=rpc_timeout_s))
        status = "OK" if ok else "FAIL" if ok is False else "WARN"
        return Result("SymbolCheck", status, f"instance {instance}: {detail}")
    except Exception as e:
        return Result("SymbolCheck", "FAIL", f"symbols.check failed: {e}")
    finally:
        link.close()


# ---- environment (part of item 8) --------------------------------------------------------------------------

def check_disk(paths: list[Path], min_gb: float = MIN_FREE_GB) -> Result:
    seen, parts, low = set(), [], []
    for p in paths:
        p = Path(p)
        while not p.exists() and p != p.parent:
            p = p.parent
        drive = p.anchor or str(p)
        if drive in seen:
            continue
        seen.add(drive)
        free = shutil.disk_usage(p).free / 2**30
        parts.append(f"{drive} {free:.0f} GB free")
        if free < min_gb:
            low.append(drive)
    return Result("disk space", "FAIL" if low else "OK", "; ".join(parts) + (f" (< {min_gb:.0f} GB)" if low else ""))


def microcode_revision() -> int | None:
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            v, _ = winreg.QueryValueEx(k, "Update Revision")
    except OSError:
        return None
    if isinstance(v, bytes):
        return int.from_bytes(v[4:8] if len(v) >= 8 else v[:4], "little")
    return int(v) if isinstance(v, int) else None


def check_microcode(min_rev: int = MIN_MICROCODE) -> Result:
    rev = microcode_revision()
    if rev is None:
        return Result("CPU microcode", "WARN", "could not read Update Revision")
    ok = rev >= min_rev
    return Result("CPU microcode", "OK" if ok else "FAIL", f"0x{rev:X} ({'>=' if ok else '<'} 0x{min_rev:X})")


def connected_xinput_pads() -> list[int] | None:
    if sys.platform != "win32":
        return None
    import ctypes
    for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            x = ctypes.WinDLL(dll)
            break
        except OSError:
            continue
    else:
        return None
    state = (ctypes.c_byte * 16)()
    return [i for i in range(4) if x.XInputGetState(i, ctypes.byref(state)) == 0]


def check_prefs(golden: Path = GOLDEN_PREFS, profile: str = "TRAIN", lock: dict | None = None,
                store=None, registry: dict | None = None) -> Result:
    """PlayerPrefs vs the golden snapshot (item 2 without the options-page OCR, which is not in v1).

    golden.reg must hash to versions.lock [frozen_settings].golden_prefs_sha256 in every profile. Under a training
    profile the rest only warns, because a user's own play legitimately changes the prefs until the next restore.
    Before a FINAL or VANILLA session (DESIGN §2.7: restore and hash first) it FAILs on a difference from golden, a
    missing pin, a restore the launcher still owes (--detach, a killed launcher) or a live training instance.
    store (a launcher.PrefsStore) and registry (a PrefsGuard.peek() dict) are for tests."""
    from ssbot.tools import launcher as L

    strict = profile.upper() in STRICT_PREFS_PROFILES
    bad = "FAIL" if strict else "WARN"
    if store is None and sys.platform != "win32":
        return Result("PlayerPrefs", "SKIP", "not Windows")
    golden = Path(golden)
    if not golden.is_file():
        return Result("PlayerPrefs", bad, f"no golden snapshot at {golden} (launcher --make-golden)")
    fails, warns, notes = [], [], []
    digest, pin = L.file_sha256(golden), L.golden_pin(golden, lock)
    if pin is None:
        (fails if strict else warns).append(f"versions.lock pins no golden_prefs_sha256 (golden.reg is {digest[:12]})")
    elif digest != pin:
        fails.append(f"golden.reg sha256 {digest[:12]} != versions.lock golden_prefs_sha256 {pin[:12]}: the snapshot "
                     f"was replaced or corrupted, launcher restores refuse it")
    else:
        notes.append(f"golden.reg matches the pin {pin[:12]}")
    if registry is None:
        registry = L.PrefsGuard(L.RegPrefsStore(), golden, golden.parent / "instances.json",
                                golden.parent / "instances.lock").peek()
    live = registry.get("live") or []
    if live:
        (fails if strict else notes).append(f"{len(live)} training instance(s) live "
                                            f"(pids {', '.join(str(i['pid']) for i in live[:6])})")
    elif registry.get("restore_pending"):
        (fails if strict else warns).append("a golden restore is pending (launcher --detach or a killed launcher): "
                                            "run `python -m ssbot.tools.launcher --restore`")
    try:
        diff = L.prefs_diff(L.current_prefs(store or L.RegPrefsStore()), L.read_reg_file(golden))
    except (RuntimeError, OSError) as e:
        diff = None
        (fails if strict else warns).append(f"could not export the current PlayerPrefs: {e}")
    if diff:
        (fails if strict else warns).append(f"{len(diff)} value(s) differ from golden ({', '.join(diff[:6])}); "
                                            f"launcher --restore once no instance runs")
    elif diff is not None:
        notes.append("current PlayerPrefs match golden")
    status = "FAIL" if fails else "WARN" if warns else "OK"
    return Result("PlayerPrefs", status, "; ".join(fails + warns + notes) + f" [profile {profile}]",
                  {"golden_sha256": digest, "pin": pin, "live": len(live),
                   "restore_pending": bool(registry.get("restore_pending")), "diff": diff or []})


def check_gamepads() -> Result:
    pads = connected_xinput_pads()
    if pads is None:
        return Result("gamepads", "SKIP", "XInput not available")
    if pads:
        return Result("gamepads", "WARN", f"XInput pad(s) connected in slot(s) {pads}: disconnect them (m0:N19)")
    return Result("gamepads", "OK", "no XInput pad connected (non-XInput pads are not detected)")


# ---- runner ----------------------------------------------------------------------------------------------

def run_checks(a: argparse.Namespace) -> list[Result]:
    results: list[Result] = []
    try:
        lock = load_lock(a.lock)
        game = lock.get("game", {})
        results.append(Result("versions.lock", "INFO", f"game {game.get('version')} build {game.get('buildid')}, "
                              f"{game.get('file_count')} files"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        return [Result("versions.lock", "FAIL", str(e))]
    copies = lock.get("copies", {})
    if not a.quick:
        reference = load_reference(lock, a.manifest)
        for kind in ("final", "train"):
            root = Path(copies.get(kind, {}).get("path", ""))
            results.append(check_copy(kind, root, lock, reference))
    else:
        results.append(Result("game copies", "SKIP", "--quick"))
    results.append(Result("SymbolCheck", "SKIP", "--no-oracle") if a.no_oracle else check_symbols(a.instance))
    results.append(check_default_absent(a.locallow))
    results.append(check_saves_info(a.locallow))
    repo = find_repo_root()
    results.append(check_disk([Path(r"C:\ssbot\sandbox"), (repo / "runs") if repo else Path.cwd()]))
    results.append(check_microcode())
    results.append(check_gamepads())
    results.append(check_prefs(a.golden, a.profile, lock))
    return results


def print_table(results: list[Result], out=None) -> None:
    out = out or sys.stdout
    w = max(len(r.name) for r in results)
    print(f"{'check':<{w}}  status  detail", file=out)
    print(f"{'-' * w}  ------  {'-' * 40}", file=out)
    for r in results:
        print(f"{r.name:<{w}}  {r.status:<6}  {r.detail}", file=out)


def exit_code(results: list[Result]) -> int:
    return 1 if any(r.status == "FAIL" for r in results) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.tools.compat", description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", default="check", choices=("check", "snapshot", "verify"))
    ap.add_argument("--profile", default="TRAIN", type=str.upper,
                    help="session profile (TRAIN, SHADOW, REHEARSAL-SEG, REHEARSAL-FULL, VANILLA, FINAL); FINAL and "
                         "VANILLA require golden PlayerPrefs")
    ap.add_argument("--quick", action="store_true", help="skip hashing the game copies")
    ap.add_argument("--no-oracle", action="store_true", help="skip SymbolCheck")
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--lock", type=Path, default=None, help="versions.lock (default: repo root)")
    ap.add_argument("--manifest", type=Path, default=REFERENCE_MANIFEST, help="per-file reference hashes")
    ap.add_argument("--locallow", type=Path, default=LOCALLOW)
    ap.add_argument("--snapshot", type=Path, default=SNAPSHOT, help="save-folder snapshot file")
    ap.add_argument("--golden", type=Path, default=GOLDEN_PREFS, help="golden PlayerPrefs .reg")
    ap.add_argument("--json", type=Path, help="also write the results as JSON")
    a = ap.parse_args(argv)

    if a.cmd == "snapshot":
        snap = snapshot_saves(a.locallow)
        a.snapshot.parent.mkdir(parents=True, exist_ok=True)
        a.snapshot.write_text(json.dumps(snap, indent=1), encoding="utf-8")
        results = [Result("save snapshot", "OK", f"{len(snap['dirs'])} folder(s) -> {a.snapshot}"),
                   check_default_absent(a.locallow)]
    elif a.cmd == "verify":
        try:
            before = json.loads(a.snapshot.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            results = [Result("save verify", "FAIL", f"no usable snapshot {a.snapshot}: {e}")]
        else:
            diffs = diff_saves(before, snapshot_saves(a.locallow))
            results = [Result("save verify", "FAIL" if diffs else "OK",
                              f"{len(diffs)} change(s) since {before.get('taken')}: {', '.join(diffs[:8])}" if diffs
                              else f"unchanged since {before.get('taken')}"), check_default_absent(a.locallow)]
    else:
        results = run_checks(a)
    print_table(results)
    if a.json:
        a.json.write_text(json.dumps({"profile": a.profile, "cmd": a.cmd, "time": datetime.now().isoformat(),
                                      "results": [asdict(r) for r in results]}, indent=1), encoding="utf-8")
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
