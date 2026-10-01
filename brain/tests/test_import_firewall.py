"""Import firewall (DESIGN §8.2 CI rules): the final-run packages never import the oracle IPC or the oracle backend,
so nothing they compute can depend on a value only the training oracle has. They take a WorldState (vision view).

AST scan of brain/ssbot/{combat,safety,nav,run,perception}; a package that does not exist yet passes vacuously.
Caught: import ssbot.ipc[.x], from ssbot.ipc[.x] import y, from ssbot import ipc, import / from of
ssbot.backends.oracle_backend, from ssbot.backends import oracle_backend, and the same through relative imports.
"""
import ast
from pathlib import Path

SSBOT = Path(__file__).resolve().parents[1] / "ssbot"
GUARDED = ("combat", "safety", "nav", "run", "perception")
FORBIDDEN = ("ssbot.ipc", "ssbot.backends.oracle_backend")


def _module_of(path: Path, root: Path) -> list[str]:
    rel = path.relative_to(root.parent).with_suffix("")
    parts = list(rel.parts)
    return parts[:-1] if parts[-1] == "__init__" else parts


def _resolve(node: ast.ImportFrom, package: list[str]) -> str:
    if node.level == 0:
        return node.module or ""
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
    return ".".join(base + ([node.module] if node.module else []))


def _hit(name: str) -> bool:
    return any(name == f or name.startswith(f + ".") for f in FORBIDDEN)


def violations(pkg_dir: Path, root: Path = SSBOT) -> list[str]:
    out = []
    for py in sorted(pkg_dir.rglob("*.py")):
        mod = _module_of(py, root)
        package = mod if py.name == "__init__.py" else mod[:-1]
        tree = ast.parse(py.read_text("utf-8"), filename=str(py))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = _resolve(node, package)
                names = [base] + [f"{base}.{a.name}" for a in node.names]
            for n in names:
                if _hit(n):
                    out.append(f"{py.relative_to(root.parent)}:{node.lineno}: {n}")
                    break
    return out


def test_final_run_packages_do_not_import_the_oracle():
    found = []
    for name in GUARDED:
        d = SSBOT / name
        if d.is_dir():
            found += violations(d)
    assert found == [], "import firewall:\n" + "\n".join(found)


def test_the_scanner_catches_every_form(tmp_path):
    root = tmp_path / "ssbot"
    pkg = root / "combat"
    pkg.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    bad = {
        "a.py": "import ssbot.ipc.oracle_link\n",
        "b.py": "from ssbot.ipc import framing\n",
        "c.py": "from ssbot import ipc\n",
        "d.py": "from ssbot.backends.oracle_backend import OracleBackend\n",
        "e.py": "from ssbot.backends import oracle_backend as ob\n",
        "f.py": "from ..ipc.ents import collider_points\n",
        "g.py": "def f():\n    import ssbot.backends.oracle_backend\n",
    }
    ok = {
        "h.py": "from ssbot.core.worldstate import WorldState\nfrom ssbot.backends import observability\n",
        "i.py": "from ..core import worldstate\nimport ssbot.ipcx\n",
    }
    for name, src in (bad | ok).items():
        (pkg / name).write_text(src)
    found = violations(pkg, root)
    assert sorted(x.split(":")[0].replace("\\", "/") for x in found) == sorted(f"ssbot/combat/{n}" for n in bad)
