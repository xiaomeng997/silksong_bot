"""Configuration provenance from source and already constructed runtime objects.

No control modules are imported or configuration expressions evaluated here. A
missing binding is an explicit unresolved item, never a guessed default.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.metadata
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BASE_REV = "dc95a60289c6d27399061d1a049c581189300923"
_SWITCH = re.compile(r"SSBOT_FORUM_[A-Z][A-Z0-9_]*\Z")
_MISSING = object()


def runtime_manifest() -> dict:
    import psutil
    import numba
    process = psutil.Process()
    memory = process.memory_info()
    return {"pid": process.pid, "cpu_affinity": process.cpu_affinity(), "priority": int(process.nice()),
            "numba_threads": numba.get_num_threads(), "process_threads": process.num_threads(),
            "rss": memory.rss, "peak_wset": getattr(memory, "peak_wset", None),
            "process_cpu_times": process.cpu_times()._asdict(),
            "system_cpu_times": psutil.cpu_times()._asdict(), "available_memory": psutil.virtual_memory().available,
            "process_count": len(psutil.pids()), "monotonic_ns": time.perf_counter_ns(),
            "timer_resolution_s": time.get_clock_info("perf_counter").resolution}


def json_value(value, depth=0):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"float": str(value)}
    if isinstance(value, Path):
        return str(value)
    if depth >= 8:
        return _MISSING
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
    if isinstance(value, dict) and len(value) <= 4096:
        out = {}
        for key, item in value.items():
            converted = json_value(item, depth + 1)
            if converted is _MISSING or not isinstance(key, (str, int, float, bool)):
                return _MISSING
            out[str(key)] = converted
        return out
    if isinstance(value, (tuple, list, set, frozenset)) and len(value) <= 256:
        values = sorted(value, key=repr) if isinstance(value, (set, frozenset)) else value
        out = [json_value(item, depth + 1) for item in values]
        return _MISSING if any(item is _MISSING for item in out) else out
    return _MISSING


def _keys(node):
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant)
            and isinstance(n.value, str) and _SWITCH.fullmatch(n.value)}


def _instances(policy):
    """Small object graph; arrays, forecast histories and terrain are not config."""
    out, pending, seen = {}, [("policy", policy, 0)], set()
    while pending:
        path, obj, depth = pending.pop()
        if obj is None or id(obj) in seen or depth > 4:
            continue
        seen.add(id(obj))
        cls = type(obj)
        if not cls.__module__.startswith("ssbot.") or not hasattr(obj, "__dict__"):
            continue
        out.setdefault((cls.__module__, cls.__name__), []).append((path, obj))
        for name, value in vars(obj).items():
            if name in {"planner", "tac", "local", "two", "claw", "slam_play", "rune_lowhop",
                        "cast_stab", "evade_chase", "sc", "fc", "inner", "air_show", "rt", "_csx"}:
                pending.append((f"{path}.{name}", value, depth + 1))
    return out


def _config_objects(policy):
    out = {}
    for objects in _instances(policy).values():
        for path, obj in objects:
            for name, value in vars(obj).items():
                is_config = (dataclasses.is_dataclass(value) and not isinstance(value, type)
                             and (name.endswith("cfg") or name in {
                                 "params0", "params", "pb", "rules", "l2_rules", "_pq_emulated"}
                                  or type(value).__name__.endswith(("Config", "Cfg", "Rules", "Params", "Playbook"))))
                if is_config or name in {
                        "threads", "crest", "clash", "ab_arm", "free", "view", "l2_rules", "rules"}:
                    converted = json_value(value)
                    if converted is not _MISSING:
                        out[f"{path}.{name}"] = converted
    return out


def _known_runtime_bindings(policy, loaded):
    """Explicit joins for factory methods and module-level in-place config updates."""
    if policy is None:
        return {}
    out = {}
    paths = {
        "SSBOT_FORUM_AB": "ab", "SSBOT_FORUM_FR": "planner.fcfg.forced_rank",
        "SSBOT_FORUM_REACT": "planner.fcfg.react", "SSBOT_FORUM_L2_SET": "l2_rules",
        "SSBOT_FORUM_BELLS": "planner.fcfg.bell_hits",
        "SSBOT_FORUM_SLAM_PLAY_SET": "slam_play.cfg", "SSBOT_FORUM_CLAW_SET": "claw.cfg",
        "SSBOT_FORUM_AIRSHOW_SET": "air_show.cfg", "SSBOT_FORUM_CLAWSTRIKE_SET": "slam_play._csx.cfg",
        "SSBOT_FORUM_TWO_PMCAST_SET": "two.pccfg", "SSBOT_FORUM_TWO_RUNETIER_SET": "two.rt.cfg",
        "SSBOT_FORUM_HERO2": "params0.hero2", "SSBOT_FORUM_HERO2_OFF": "params0.hero2",
    }
    for key, path in paths.items():
        value, disabled = policy, None
        for part in path.split("."):
            if value is None:
                disabled = "component_not_constructed"
                break
            if not hasattr(value, part):
                value = _MISSING
                break
            value = getattr(value, part)
        # CLAWSTRIKE is constructed lazily: its unparsed settings remain unresolved.
        if disabled and key == "SSBOT_FORUM_CLAWSTRIKE_SET":
            continue
        converted = {"active": False, "reason": disabled} if disabled else json_value(value)
        if converted is not _MISSING:
            out[key] = {f"policy.{path}": converted}
    for key, module_name, name in (
        ("SSBOT_FORUM_TWO_CLAWAIR_SET", "ssbot.combat.claw_chase", "CA"),
        ("SSBOT_FORUM_TWO_FLIPB_SET", "ssbot.combat.two_play", "FB"),
        ("SSBOT_FORUM_TWO_JUMPTRAP_SET", "ssbot.combat.tactics.gauntlet", "JT"),
    ):
        module = loaded.get(module_name)
        if module is not None and name in vars(module):
            converted = json_value(vars(module)[name])
            if converted is not _MISSING:
                out[key] = {f"{module_name}.{name}": converted}
    for key, component in (("SSBOT_FORUM_WINDOWS", "win"),
                           ("SSBOT_FORUM_WINDOWS_PRESS", "wpress")):
        if hasattr(policy, component):
            out[key] = {f"policy.{component}.constructed": getattr(policy, component) is not None}
    if hasattr(policy, "win") and policy.win is None:
        out["SSBOT_FORUM_WINDOWS_ROWS"] = {"active": False, "reason": "window tracker not constructed"}
    elif getattr(policy, "planner", None) is not None:
        out["SSBOT_FORUM_WINDOWS_ROWS"] = {"policy.planner.win.constructed": policy.planner.win is not None}
    tables = getattr(getattr(policy, "fc", None), "tables", None)
    if tables is not None:
        out["SSBOT_FORUM_MARGIN"] = {"policy.fc.tables.source": tables.source,
                                    "policy.fc.tables.margins": json_value(tables.margins)}
        out["SSBOT_FORUM_AIM"] = {"loaded_aim_templates": [key for key in tables.store.keys if "/aim@" in key]}
    return out


def configuration_manifest(package_root: Path, policy=None, *, environ=None, modules=None) -> dict:
    package_root = Path(package_root)
    env = os.environ if environ is None else environ
    loaded = sys.modules if modules is None else modules
    instances = _instances(policy)
    switches, source_hashes = {}, {}
    # Include helper modules (notably knowledge.kinematics' HERO2), but not this
    # manifest's own registry or report/probe-only command-line programs.
    paths = [path for path in sorted(package_root.rglob("*.py"))
             if not {"tools", "probes", "tests", "__pycache__"}.intersection(path.relative_to(package_root).parts)
             and not path.name.startswith("forum_measure") and path.name != "measurement.py"]
    for path in paths:
        if not path.exists():
            continue
        rel = path.relative_to(package_root).as_posix()
        module_name = "ssbot." + rel[:-3].replace("/", ".")
        source = path.read_text("utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        source_hashes[rel] = hashlib.sha256(source.replace("\r\n", "\n").encode()).hexdigest()
        module = loaded.get(module_name)
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        definitions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}

        def dependencies(node, seen=frozenset()):
            keys = _keys(node)
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                    name = n.func.id
                    if name in definitions and name not in seen:
                        keys |= dependencies(definitions[name], seen | {name})
            return keys

        bindings = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            keys = dependencies(node.value)
            if not keys:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            scope, cls = parents.get(node), None
            function = False
            while scope is not None:
                if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function = True
                if isinstance(scope, ast.ClassDef):
                    cls = scope.name
                    break
                scope = parents.get(scope)
            for target in targets:
                values = []
                if isinstance(target, ast.Name) and not function:
                    owner = getattr(module, cls, None) if cls else module
                    if owner is not None and target.id in vars(owner):
                        values.append((f"{module_name}.{cls + '.' if cls else ''}{target.id}",
                                       vars(owner)[target.id]))
                elif (cls and isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                      and target.value.id == "self"):
                    for obj_path, obj in instances.get((module_name, cls), ()):
                        if target.attr in vars(obj):
                            values.append((f"{obj_path}.{target.attr}", vars(obj)[target.attr]))
                for value_path, value in values:
                    if isinstance(value, str) and _SWITCH.fullmatch(value):
                        continue  # an environment-key alias is not its parsed setting
                    converted = json_value(value)
                    if converted is not _MISSING:
                        for key in keys:
                            bindings.setdefault(key, {})[value_path] = converted
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            key = node.value
            if not _SWITCH.fullmatch(key):
                continue
            entry = switches.setdefault(key, {"raw": env.get(key), "present": key in env,
                                              "bindings": {}, "sources": [], "active_modules": []})
            entry["sources"].append({"path": rel, "line": node.lineno})
            entry["bindings"].update(bindings.get(key, {}))
            if module is not None and module_name not in entry["active_modules"]:
                entry["active_modules"].append(module_name)
    for name, bindings in _known_runtime_bindings(policy, loaded).items():
        if name in switches:
            for path, value in bindings.items():
                converted = json_value(value)
                if converted is not _MISSING:
                    switches[name]["bindings"][path] = converted
    unresolved = []
    for name, entry in switches.items():
        if entry["bindings"]:
            entry["resolution"] = "runtime_binding"
        elif not entry["active_modules"]:
            entry["resolution"] = "module_not_loaded"
        else:
            entry["resolution"] = "unresolved"
            unresolved.append(name)
        entry["effective"] = entry["bindings"] or None
    configs = _config_objects(policy)
    behavior = {"switches": {k: {"raw": v["raw"], "present": v["present"],
                                 "bindings": v["bindings"], "resolution": v["resolution"]}
                             for k, v in sorted(switches.items())}, "configs": configs}
    encoded = json.dumps(behavior, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    unknown = sorted(k for k in env if k.startswith("SSBOT_FORUM_") and k not in switches)
    return {"schema": 1, "switches": dict(sorted(switches.items())), "configs": configs,
            "source_sha256": source_hashes, "unresolved": sorted(unresolved),
            "unknown_environment_switches": unknown,
            "configuration_complete": not unresolved and not unknown,
            "behavior_sha256": hashlib.sha256(encoded).hexdigest()}


def code_manifest(repo: Path) -> dict:
    repo = Path(repo)
    def git(*args):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=20)
        return result.stdout.strip() if result.returncode == 0 else None
    files = {}
    for root in (repo / "brain" / "ssbot", repo / "knowledge"):
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json", ".yaml", ".yml", ".npz"}:
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1 << 20), b""):
                        digest.update(chunk)
                files[path.relative_to(repo).as_posix()] = digest.hexdigest()
    deps = {}
    for name in ("numpy", "numba", "msgpack", "msgspec", "psutil", "PyYAML", "zstandard"):
        try:
            deps[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            deps[name] = None
    identity_files = {}
    for path in (repo / "versions.lock", *sorted(Path(r"C:\ssbot\game\train\BepInEx\plugins").rglob("*Oracle*.dll"))):
        if path.is_file():
            identity_files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"base_revision": BASE_REV, "head_revision": git("rev-parse", "HEAD"),
            "working_tree": git("status", "--porcelain"), "files_sha256": files,
            "python": sys.version, "dependencies": deps, "runtime_identity_files": identity_files}
