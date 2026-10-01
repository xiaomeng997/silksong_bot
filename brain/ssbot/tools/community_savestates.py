"""Fetch and check the community savestates (vichisuki, Bell route practice; DESIGN §8.1, M2 W8/W9, P13).

Source: github.com/vichisuki/vichisuki-Silksong-Practice-Resources, BellRoute-LP/Savestates/<page>/savestate<slot>.json
(DebugMod JSON; README BellRoute-LP/Savestates/BELLROUTE-SAVESTATES-README.md). Only the .json savestates are fetched,
pinned to one commit, into C:\\ssbot\\sandbox\\savestates\\community\\<commit[:12]>\\p<page>_s<slot>.json, with a
manifest (path, sha256, size, checks) next to them.

Why these checks (2026-10-01): the files are data, read by Unity's JsonUtility into fixed types (DebugMod
SaveStateManager / our DebugModBridge.FromJson): no type names, no polymorphism, so a file cannot run code; the worst a
bad file can do is set odd game state in the sandboxed training copy. The checks keep that worst case visible: valid
JSON object, size, top-level keys and savedPd keys against a reference savestate written by this build's DebugMod
(unknown keys are ignored by JsonUtility but reported as version drift), no oversized strings, the savedPd "version".
A file that fails is kept out of the folder (quarantine/ instead).

    python -m ssbot.tools.community_savestates fetch [--commit SHA] [--reference soak_233809_i0]
    python -m ssbot.tools.community_savestates check <folder>
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO = "vichisuki/vichisuki-Silksong-Practice-Resources"
PREFIX = "BellRoute-LP/Savestates/"
OUT = Path(r"C:\ssbot\sandbox\savestates\community")
SAVESTATES = Path(r"C:\ssbot\sandbox\savestates")
MAX_BYTES = 400_000
MAX_STRING = 20_000
UA = {"User-Agent": "ssbot-community-savestates"}


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def _strings(o, out: list[int]) -> None:
    if isinstance(o, str):
        out.append(len(o))
    elif isinstance(o, dict):
        for k, v in o.items():
            out.append(len(k))
            _strings(v, out)
    elif isinstance(o, list):
        for v in o:
            _strings(v, out)


def check(data: bytes, ref: dict) -> dict:
    """{"ok", "problems", "drift": {...}, "scene", "identifier", "version", "pos"} for one file."""
    problems: list[str] = []
    out: dict = {"bytes": len(data)}
    if len(data) > MAX_BYTES:
        problems.append(f"size {len(data)} > {MAX_BYTES}")
    try:
        d = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return {**out, "ok": False, "problems": [f"not JSON: {e}"]}
    if not isinstance(d, dict):
        return {**out, "ok": False, "problems": ["top level is not an object"]}
    lens: list[int] = []
    _strings(d, lens)
    if lens and max(lens) > MAX_STRING:
        problems.append(f"a string of {max(lens)} chars")
    if any("$type" in str(k) for k in d) or b'"$type"' in data:
        problems.append("contains $type keys")
    for k in ("saveScene", "savedPd", "savePos", "saveStateIdentifier"):
        if k not in d:
            problems.append(f"missing {k}")
    pd = d.get("savedPd") if isinstance(d.get("savedPd"), dict) else {}
    out["drift"] = {
        "top_unknown": sorted(set(d) - set(ref)),
        "top_missing": sorted(set(ref) - set(d)),
        "pd_unknown": sorted(set(pd) - set(ref["savedPd"])),
        "pd_missing_n": len(set(ref["savedPd"]) - set(pd)),
    }
    out.update(scene=d.get("saveScene"), identifier=d.get("saveStateIdentifier"), version=pd.get("version"),
               pos=d.get("savePos"), hp=pd.get("health"), max_hp=pd.get("maxHealth"), silk=pd.get("silk"),
               crest=pd.get("CurrentCrestID"), play_time=pd.get("playTime"), permadeath=pd.get("permadeathMode"))
    out["ok"] = not problems
    out["problems"] = problems
    return out


def fetch(commit: str | None, reference: str) -> int:
    ref = json.loads((SAVESTATES / f"{reference}.json").read_text(encoding="utf-8"))
    if not commit:
        commit = json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/main"))["sha"]
    tree = json.loads(_get(f"https://api.github.com/repos/{REPO}/git/trees/{commit}?recursive=1"))
    if tree.get("truncated"):
        raise SystemExit("tree listing truncated")
    paths = sorted(e["path"] for e in tree["tree"]
                   if e["type"] == "blob" and e["path"].startswith(PREFIX) and e["path"].endswith(".json"))
    folder = OUT / commit[:12]
    quarantine = folder / "quarantine"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"repo": REPO, "commit": commit, "files": []}
    bad = 0
    for p in paths:
        page, name = p[len(PREFIX):].split("/")
        slot = name.removeprefix("savestate").removesuffix(".json")
        data = _get(f"https://raw.githubusercontent.com/{REPO}/{commit}/{p}")
        res = check(data, ref)
        local = f"p{page}_s{slot}.json"
        dst = (folder if res["ok"] else quarantine) / local
        dst.parent.mkdir(exist_ok=True)
        dst.write_bytes(data)
        bad += not res["ok"]
        manifest["files"].append({"source": p, "local": str(dst.relative_to(folder)),
                                  "sha256": hashlib.sha256(data).hexdigest(), **res})
        print(f"{'ok ' if res['ok'] else 'BAD'} {local:14s} {res.get('scene')!s:28s} v{res.get('version')} "
              f"hp {res.get('hp')}/{res.get('max_hp')} {res.get('crest')} {'; '.join(res['problems'])}", flush=True)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"{len(paths)} files, {bad} quarantined -> {folder}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--commit")
    f.add_argument("--reference", default="soak_233809_i0")
    c = sub.add_parser("check")
    c.add_argument("folder", type=Path)
    c.add_argument("--reference", default="soak_233809_i0")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        return fetch(a.commit, a.reference)
    ref = json.loads((SAVESTATES / f"{a.reference}.json").read_text(encoding="utf-8"))
    bad = 0
    for p in sorted(a.folder.glob("*.json")):
        if p.name == "manifest.json":
            continue
        res = check(p.read_bytes(), ref)
        bad += not res["ok"]
        print(p.name, res["ok"], res["problems"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
