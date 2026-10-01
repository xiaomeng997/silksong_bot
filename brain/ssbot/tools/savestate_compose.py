"""Compose a DebugMod savestate (C:\\ssbot\\sandbox\\savestates\\<name>.json) from a game save's progress and a place.

A DebugMod savestate is JSON: saveScene, savePos, facing, savedPd (PlayerData, DebugMod's own serialization),
savedSd (SceneData: persistentBools / persistentInts / geoRocks) and a few flags. Loading one reloads the scene fresh
(enemies start in their initial state), so a boss savestate is "the hero standing in the arena before the trigger".

compose() takes a template savestate made by this build's DebugMod (any one: its field set is the reference), overlays
the PlayerData and SceneData of a game save (user*.dat or a restore point, decoded by ssbot.tools.savefile), and puts
the hero at `scene`/`pos`. Fields DebugMod writes that the save lacks keep the template's value; fields only in the
save (scenesVisited, ...) are dropped, as DebugMod's own savestates lack them too. The result is a starting point: load
it once in game, check it (savestate.load reply, the scene's state), and save it again with savestate.save so the
savestate used for training is one the game itself wrote.

    python -m ssbot.tools.savestate_compose --template soak_233809_i0 --save <user1.dat | restoreDataN.dat>
        --scene Bone_05 --pos 80.0 3.5677 --facing right --name bellbeast_compose
"""
import argparse
import base64
import json
from pathlib import Path

from ssbot.tools import savefile

FOLDER = Path(r"C:\ssbot\sandbox\savestates")


def read_save(path: Path) -> dict:
    """{"playerData", "sceneData"} of a user*.dat, or of a restore point (restoreData*.dat: an envelope whose "data" is
    another encoded save holding "saveGameData")."""
    d = savefile.decode_bytes(path.read_bytes())
    if "playerData" in d:
        return d
    inner = savefile.decode_bytes(base64.b64decode(d["data"]))
    data = inner["saveGameData"]
    return json.loads(data) if isinstance(data, str) else data


def compose(template: dict, save: dict, scene: str, pos: tuple[float, float], facing_right: bool,
            name: str) -> tuple[dict, dict]:
    """The new savestate and a report {overlaid, kept_template_only, dropped_save_only}."""
    out = json.loads(json.dumps(template))
    pd_t, pd_s = out["savedPd"], save["playerData"]
    overlaid = [k for k in pd_t if k in pd_s]
    for k in overlaid:
        pd_t[k] = pd_s[k]
    out["savedSd"] = {k: save["sceneData"][k] for k in template["savedSd"]}
    out["saveStateIdentifier"] = name
    out["saveScene"] = scene
    out["loadedScenes"] = [scene]
    out["loadedSceneActiveScenes"] = [scene]
    out["savePos"] = {"x": float(pos[0]), "y": float(pos[1]), "z": template["savePos"].get("z", 0.004)}
    out["facingRight"] = bool(facing_right)
    out["facingLeft"] = not facing_right
    out["isKinematized"] = False
    out["semiPersistentBools"] = []
    out["semiPersistentInts"] = []
    report = {"overlaid": len(overlaid), "kept_template_only": sorted(set(pd_t) - set(pd_s)),
              "dropped_save_only": sorted(set(pd_s) - set(pd_t))}
    return out, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True, help="savestate name in the sandbox folder")
    ap.add_argument("--save", required=True, type=Path)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--pos", required=True, type=float, nargs=2)
    ap.add_argument("--facing", choices=("left", "right"), default="right")
    ap.add_argument("--name", required=True)
    a = ap.parse_args(argv)
    template = json.loads((FOLDER / f"{a.template}.json").read_text(encoding="utf-8"))
    out, report = compose(template, read_save(a.save), a.scene, tuple(a.pos), a.facing == "right", a.name)
    dst = FOLDER / f"{a.name}.json"
    if dst.exists():
        raise SystemExit(f"refusing to overwrite {dst}")
    dst.write_text(json.dumps(out), encoding="utf-8")
    pd = out["savedPd"]
    print(json.dumps({"path": str(dst), **report, "hp": pd.get("health"), "silk": pd.get("silk"),
                      "playTime": pd.get("playTime"), "crest": pd.get("CurrentCrestID")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
