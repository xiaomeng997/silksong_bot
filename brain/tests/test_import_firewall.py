"""Import firewall (DESIGN §8.2 CI rules): the final-run packages never reach the oracle, directly or through another
module, so nothing they compute can depend on a value only the training oracle has. They take a WorldState (vision
view).

The whole ssbot tree is parsed (AST, every import statement including function-level ones) into a module graph:
"import a.b.c" and "from a.b import c" also execute the packages a and a.b, and "from a.b import c" reaches the
module a.b.c when it exists. A guarded module (brain/ssbot/{combat,safety,nav,run,perception}) fails when any path
from it reaches a forbidden module: the oracle IPC (ssbot.ipc), the oracle message decoders (ssbot.oracle),
recordings (ssbot.record), the oracle backend and the degraded backend built on it. A package that does not exist yet
passes vacuously.
"""
import ast
from collections import deque
from pathlib import Path

SSBOT = Path(__file__).resolve().parents[1] / "ssbot"
GUARDED = ("combat", "safety", "nav", "run", "perception")
FORBIDDEN = ("ssbot.ipc", "ssbot.oracle", "ssbot.record", "ssbot.backends.oracle_backend",
             "ssbot.backends.degraded")


def _module_of(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root.parent).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _resolve(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        return node.module or ""
    base = package.split(".")
    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
    return ".".join(base + ([node.module] if node.module else []))


def _with_parents(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts) + 1)]


def import_graph(root: Path = SSBOT) -> dict[str, set[str]]:
    """module -> the ssbot modules importing it executes (packages included)."""
    files = {_module_of(p, root): p for p in root.rglob("*.py")}
    graph: dict[str, set[str]] = {}
    for mod, py in files.items():
        package = mod if py.name == "__init__.py" else mod.rpartition(".")[0]
        deps: set[str] = set()
        for node in ast.walk(ast.parse(py.read_text("utf-8-sig"), filename=str(py))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = _resolve(node, package)
                names = [base] + [f"{base}.{a.name}" for a in node.names if f"{base}.{a.name}" in files]
            for n in names:
                deps.update(x for x in _with_parents(n) if x == "ssbot" or x.startswith("ssbot."))
        deps.update(_with_parents(mod)[:-1])           # importing a module runs its parent packages
        deps.discard(mod)
        graph[mod] = deps
    return graph


def _forbidden(name: str) -> bool:
    return any(name == f or name.startswith(f + ".") for f in FORBIDDEN)


def violations(guarded: list[str], graph: dict[str, set[str]]) -> list[str]:
    """For every guarded module that reaches a forbidden one: the import chain."""
    out = []
    for start in sorted(guarded):
        prev = {start: None}
        q = deque([start])
        hit = None
        while q and hit is None:
            m = q.popleft()
            for d in sorted(graph.get(m, ())):
                if d in prev:
                    continue
                prev[d] = m
                if _forbidden(d):
                    hit = d
                    break
                q.append(d)
        if hit is not None:
            chain = [hit]
            while prev[chain[-1]] is not None:
                chain.append(prev[chain[-1]])
            out.append(" -> ".join(reversed(chain)))
    return out


def _guarded(graph: dict[str, set[str]], names: tuple[str, ...] = GUARDED) -> list[str]:
    return [m for m in graph if any(m == f"ssbot.{g}" or m.startswith(f"ssbot.{g}.") for g in names)]


def test_final_run_packages_do_not_reach_the_oracle():
    graph = import_graph()
    found = violations(_guarded(graph), graph)
    assert found == [], "import firewall:\n" + "\n".join(found)


def test_the_graph_sees_the_real_tree():
    graph = import_graph()
    assert "ssbot.backends.oracle_backend" in graph["ssbot.backends.degraded"]
    assert "ssbot.ipc.ents" in graph["ssbot.backends.oracle_backend"]
    assert _forbidden("ssbot.backends.degraded") and not _forbidden("ssbot.backends.observability")


def test_the_scanner_catches_every_form(tmp_path):
    root = tmp_path / "ssbot"
    pkg = root / "combat"
    for d in (root, pkg, root / "ipc", root / "backends", root / "core", root / "util", root / "oracle",
              root / "record"):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("")
    for name in ("ipc/oracle_link.py", "ipc/framing.py", "ipc/ents.py", "backends/oracle_backend.py",
                 "backends/observability.py", "core/worldstate.py", "oracle/messages.py", "record/recorder.py"):
        (root / name).write_text("")
    (root / "backends" / "degraded.py").write_text("from ssbot.backends.oracle_backend import OracleBackend\n")
    (root / "util" / "helper.py").write_text("from ssbot.ipc import framing\n")
    (root / "util" / "clean.py").write_text("import math\n")
    bad = {
        "a.py": "import ssbot.ipc.oracle_link\n",
        "b.py": "from ssbot.ipc import framing\n",
        "c.py": "from ssbot import ipc\n",
        "d.py": "from ssbot.backends.oracle_backend import OracleBackend\n",
        "e.py": "from ssbot.backends import oracle_backend as ob\n",
        "f.py": "from ..ipc.ents import collider_points\n",
        "g.py": "def f():\n    import ssbot.backends.oracle_backend\n",
        "h.py": "from ssbot.util.helper import framing\n",                # transitive
        "i.py": "from ssbot.backends.degraded import DegradedOracleBackend\n",
        "j.py": "from ssbot.oracle import messages\n",
        "k.py": "import ssbot.record.recorder\n",
        "l.py": "from . import a\n",                                       # through a sibling
    }
    ok = {
        "m.py": "from ssbot.core.worldstate import WorldState\nfrom ssbot.backends import observability\n",
        "n.py": "from ..core import worldstate\nimport ssbot.ipcx\nfrom ssbot.util import clean\n",
    }
    for name, src in (bad | ok).items():
        (pkg / name).write_text(src)
    graph = import_graph(root)
    found = violations(_guarded(graph, ("combat",)), graph)
    starts = sorted(x.split(" -> ")[0] for x in found)
    assert starts == sorted(f"ssbot.combat.{n[:-3]}" for n in bad)
    chain = next(x for x in found if x.startswith("ssbot.combat.h "))
    assert chain == "ssbot.combat.h -> ssbot.util.helper -> ssbot.ipc"
