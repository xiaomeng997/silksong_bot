"""Hash every file of a Silksong install; used for versions.lock and pre-session checks."""
import hashlib
import json
import sys
from pathlib import Path


def hash_tree(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            out[p.relative_to(root).as_posix()] = h.hexdigest()
    return out


if __name__ == "__main__":
    json.dump(hash_tree(Path(sys.argv[1])), sys.stdout, indent=1)
