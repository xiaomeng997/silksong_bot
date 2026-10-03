"""Forum savestates (M2 W8): compose the four arms from the community p7_s3 savestate and check them in game.

Arms (docs/facts/1.0.30000/forum.md): A = helpers (Garmond & Zaza) + Reaper + Ascendant's Grip + Cogfly, 7 masks (the
person's route plan); A5 = A with 5 masks; B = helpers + Hunter_v2 + Cogfly, 7 masks; C = no helpers + Hunter_v2 +
Cogfly, 7 masks (fallback). The community savestate (vichisuki, 0557f703fa25 p7_s3: Hang_04 x 53.24, Hunter, 5 masks,
dash / Cling Grip / Drifter's Cloak / Clawline / Needolin, no Faydown double jump, no Silk Soar, no Needle Strike, no
tools but Silkspear) is the base.

Steps:
  compose        offline: fo_pre_help7 / fo_pre_nohelp7 from p7_s3 with PlayerData masks (health, maxHealth,
                 maxHealthBase) and the helper flags (garmondAidForumBattle: what the Hang_04_boss "Call Ally" FSM
                 tests; garmondWillAidInForumBattle / garmondLibraryDefeatedHornet / metGarmond for consistency;
                 shakraAidForumBattle false).
  arm X          in game: load the pre savestate, crest.equip (unlock), abilities.grant {set: movement, tools} (the
                 only grant without the combat set's Needle Strike and six silk skills; it also sets the movement flags
                 the base lacks), savestate.save fo_X_raw, then offline every flag the grant changed goes back to the
                 base value (hasDoubleJump and hasSuperJump stay false: the route has neither at the Forum), load that,
                 check (abilities.list, crest.dump, PROGRESS PlayerData mirror) and savestate.save fo_X, a state the
                 game wrote itself. A5 is made from fo_A with masks 5.
  check X        in game: load fo_X, print the loadout, run the Forum intro and GauntletDataPolicy for --seconds with
                 every FSM reported (fsmtap.set all), and report the battle start, waves, kills by source and the
                 Garmond / Shakra Fighter Control states seen (helpers are not in "ents"), plus TERRAIN of the room.
  cling          in game: load fo_A, start the battle, go to the left gate wall, jump, hold left; report wallClinging /
                 wallSliding frames, the vertical speed while clinging and the highest cling y reached by wall jumps.

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.forum_setup compose
    ..\\scripts\\uv.cmd run python -m ssbot.probes.forum_setup arm A --instance 2
"""
import argparse
import json
import random
import shutil
import sys
import threading
import time
from pathlib import Path

from ssbot.ipc.framing import MsgType, mask
from ssbot.ipc.oracle_link import OracleError, OracleLink

COMMUNITY = Path(r"C:\ssbot\sandbox\savestates\community\0557f703fa25\p7_s3.json")
SAVESTATES = Path(r"C:\ssbot\sandbox\savestates")
OUT = Path(r"C:\ssbot\sandbox\forum_setup")
MOVEMENT = ("hasDash", "hasWalljump", "hasBrolly", "hasDoubleJump", "hasHarpoonDash", "hasSuperJump")
HELPER_FLAGS = ("garmondAidForumBattle", "garmondWillAidInForumBattle", "garmondLibraryDefeatedHornet", "metGarmond")
COGFLY, GRIP = "Cogwork Flier", "Wallcling"
ARMS = {
    "A": {"pre": "fo_pre_help7", "crest": "Reaper", "tools": [COGFLY, GRIP]},
    "B": {"pre": "fo_pre_help7", "crest": "Hunter_v2", "tools": [COGFLY]},
    "C": {"pre": "fo_pre_nohelp7", "crest": "Hunter_v2", "tools": [COGFLY]},
}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(name: str, d: dict) -> Path:
    p = SAVESTATES / f"{name}.json"
    d["saveStateIdentifier"] = name
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def compose() -> None:
    base = _read(COMMUNITY)
    shutil.copyfile(COMMUNITY, SAVESTATES / "fo_p7_s3.json")
    for name, helpers in (("fo_pre_help7", True), ("fo_pre_nohelp7", False)):
        d = json.loads(json.dumps(base))
        pd = d["savedPd"]
        pd["health"] = pd["maxHealth"] = pd["maxHealthBase"] = 7
        for k in HELPER_FLAGS:
            pd[k] = helpers
        pd["shakraAidForumBattle"] = False
        print(name, _write(name, d), {k: pd[k] for k in ("health", "maxHealth", *HELPER_FLAGS)})


class Progress:
    """PlayerData mirror from PROGRESS messages (ssbot.oracle.messages.ProgressMirror)."""

    def __init__(self, link: OracleLink):
        from ssbot.oracle.messages import ProgressMirror, unpack
        self.m = ProgressMirror()
        self._unpack = unpack
        self.lock = threading.Lock()
        link.subscribe_raw(self._on)

    def _on(self, t: int, frame: bytes) -> None:
        if t != MsgType.PROGRESS:
            return
        from ssbot.ipc.framing import HEADER
        try:
            msg = self._unpack(frame[HEADER.size:])
        except Exception:
            return
        with self.lock:
            self.m.apply(msg)

    def full(self, link: OracleLink, timeout_s: float = 10.0) -> dict:
        seq0 = self.m.full_seq
        link.rpc("progress.full", timeout_s=timeout_s)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and self.m.full_seq == seq0:
            time.sleep(0.05)
        with self.lock:
            return {"fields": dict(self.m.fields), "crest": self.m.crest, "equipped": self.m.equipped,
                    "tools": self.m.tools}


def _connect(instance: int) -> OracleLink:
    from ssbot.probes.common import load_slot, stand_up
    link = OracleLink(instance=instance, connect_timeout_s=120)
    load_slot(link, 1)
    stand_up(link)
    if not link.rpc("guards.set", save_suppression=True)["save_suppression"]:
        raise SystemExit("save suppression could not be turned on")
    return link


def _load(link: OracleLink, name: str) -> dict:
    from ssbot.train.episode import wait_settled
    link.rpc("savestate.load", timeout_s=60, name=name, timeout=50)
    return wait_settled(link, "Hang_04", timeout_s=40)


def loadout(link: OracleLink, prog: Progress) -> dict:
    ab = link.rpc("abilities.list")
    cd = link.rpc("crest.dump")
    pf = prog.full(link)
    f = pf["fields"]
    return {"abilities": ab, "crest": (cd.get("current") or {}).get("crest") if isinstance(cd, dict) else None,
            "crest_dump_current": (cd.get("current") if isinstance(cd, dict) else None),
            "pd": {k: f.get(k) for k in ("health", "maxHealth", "maxHealthBase", "silk", "CurrentCrestID",
                                         *MOVEMENT, "hasChargeSlash", *HELPER_FLAGS, "shakraAidForumBattle",
                                         "hang04Battle")},
            "equipped": pf["equipped"], "crest_section": pf["crest"]}


def make_arm(link: OracleLink, prog: Progress, arm: str) -> dict:
    out: dict = {"arm": arm}
    if arm == "A5":
        d = _read(SAVESTATES / "fo_A.json")
        pd = d["savedPd"]
        pd["health"] = pd["maxHealth"] = pd["maxHealthBase"] = 5
        _write("fo_A5_fix", d)
        _load(link, "fo_A5_fix")
    else:
        spec = ARMS[arm]
        pre = _read(SAVESTATES / f"{spec['pre']}.json")["savedPd"]
        _load(link, spec["pre"])
        out["before"] = loadout(link, prog)
        out["equip"] = link.rpc("crest.equip", name=spec["crest"], unlock=True)
        g = link.rpc("abilities.grant", set="movement", tools=spec["tools"])
        if g.get("unplaced"):
            out["grant_first"] = g
            g = link.rpc("abilities.grant", set="movement", tools=spec["tools"], unlock_slots=True)
        out["grant"] = g
        link.rpc("savestate.save", name=f"fo_{arm}_raw")
        d = _read(SAVESTATES / f"fo_{arm}_raw.json")
        restored = {}
        for k in MOVEMENT + ("hasChargeSlash",):
            if d["savedPd"].get(k) != pre.get(k):
                restored[k] = [d["savedPd"].get(k), pre.get(k)]
                d["savedPd"][k] = pre.get(k)
        out["flags_restored"] = restored
        _write(f"fo_{arm}_fix", d)
        _load(link, f"fo_{arm}_fix")
    out["after"] = loadout(link, prog)
    link.rpc("savestate.save", name=f"fo_{arm}")
    out["saved"] = str(SAVESTATES / f"fo_{arm}.json")
    _load(link, f"fo_{arm}")
    out["reloaded"] = loadout(link, prog)
    return out


def check(link: OracleLink, prog: Progress, arm: str, seconds: float, seed: int) -> dict:
    from ssbot.train.data_policy import GauntletDataPolicy
    from ssbot.train.encounters import ENCOUNTERS, Ctx
    from ssbot.train.gauntlet import GauntletTap
    enc = ENCOUNTERS[f"Forum_{arm}"]
    tap = GauntletTap(link, enc)
    helper_states: dict[str, list] = {}
    terrain: list = []

    def on_state(s: dict) -> None:
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "fsm" and str(d.get("obj", "")).endswith("Fighter") and d.get("fsm") == "Control":
                helper_states.setdefault(d["obj"], []).append((s["f"], d.get("to")))

    def on_raw(t: int, frame: bytes) -> None:
        if t == MsgType.TERRAIN:
            terrain.append(frame)

    link.subscribe_state(on_state)
    link.subscribe_raw(on_raw)
    link.rpc("fsmtap.set", all=True)
    out: dict = {"arm": arm}
    try:
        _load(link, f"fo_{arm}")
        out["loadout"] = loadout(link, prog)
        tap.reset()
        link.rpc("randomize_start", timeout_s=30, seed=seed, wait_frames=[0, 5])
        ctx = Ctx(link=link, tap=tap)
        enc.intro(ctx)
        out["intro"] = ctx.log
        pol = GauntletDataPolicy()
        pol.reset(random.Random(seed), enc)
        last = link.frame
        t_end = time.monotonic() + seconds
        while time.monotonic() < t_end and tap.death_frame is None:
            s = link.wait_state(newer_than=last, timeout_s=2.0)
            last = s["f"]
            link.act(last + 2, pol.act(s, tap), hold_frames=0)
        link.act(link.frame + 2, 0, hold_frames=0)
        link.rpc("input.release")
        out["gauntlet"] = tap.summary()
        out["hero_hits"] = len(tap.damage)
        out["lethal"] = len(tap.lethal_frames())
        out["policy"] = pol.stats()
        out["helper_states"] = {k: v[:40] for k, v in helper_states.items()}
        s = link.state or {}
        out["room_keys"] = sorted((s.get("room") or {}).keys())
        out["allies_key"] = "allies" in s
        if terrain:
            from ssbot.oracle.messages import Terrain, unpack
            from ssbot.ipc.framing import HEADER
            tm = Terrain.decode(unpack(terrain[-1][HEADER.size:]))
            out["terrain"] = tm.summary()
            (OUT / f"terrain_{arm}.bin").write_bytes(terrain[-1])
    finally:
        link.rpc("fsmtap.set", all=False)
    return out


def cling(link: OracleLink, seconds: float, seed: int) -> dict:
    """Wall cling with Ascendant's Grip on the arena's left wall (arm A)."""
    from ssbot.tools.cstate import decode
    from ssbot.train.encounters import ENCOUNTERS, Ctx
    from ssbot.train.gauntlet import GauntletTap
    enc = ENCOUNTERS["Forum_A"]
    names = link.rpc("schema.cstate")["bools"]
    tap = GauntletTap(link, enc)
    _load(link, "fo_A")
    tap.reset()
    link.rpc("randomize_start", timeout_s=30, seed=seed, wait_frames=[0, 5])
    ctx = Ctx(link=link, tap=tap)
    enc.intro(ctx)
    L, J = mask("left"), mask("jump")
    rows = []
    last = link.frame
    t_end = time.monotonic() + seconds
    phase, hold_j, rest_j = "walk", 0, 0
    while time.monotonic() < t_end:
        s = link.wait_state(newer_than=last, timeout_s=2.0)
        last = s["f"]
        h = s["hero"]
        cs = decode(h["cstate"], names)
        x, y = h["pos"][0], h["pos"][1]
        vy = (h.get("vel") or [0, 0])[1]
        rows.append((last, round(x, 3), round(y, 3), round(vy, 3), cs["wallClinging"], cs["wallSliding"],
                     cs["touchingWall"], cs["onGround"], cs["wallJumping"]))
        m = L
        if phase == "walk" and x < enc.arena_x[0] + 3.0:
            phase = "climb"
        if phase == "climb":
            # jump on the ground; on the wall, a wall jump now and then (hold left keeps re-grabbing higher)
            if hold_j > 0:
                m |= J
                hold_j -= 1
                if hold_j == 0:
                    rest_j = 20
            elif rest_j > 0:
                rest_j -= 1
            elif cs["onGround"] or ((cs["wallClinging"] or cs["wallSliding"]) and random.random() < 0.05):
                hold_j = 12
        link.act(last + 2, m, hold_frames=0)
    link.act(link.frame + 2, 0, hold_frames=0)
    link.rpc("input.release")
    cl = [r for r in rows if r[4]]
    out = {"frames": len(rows), "clinging_frames": len(cl), "sliding_frames": sum(1 for r in rows if r[5]),
           "touching_frames": sum(1 for r in rows if r[6]),
           "cling_vy_abs_max": max((abs(r[3]) for r in cl), default=None),
           "cling_x": sorted({r[1] for r in cl})[:5], "cling_y_max": max((r[2] for r in cl), default=None),
           "y_max": max(r[2] for r in rows), "hits": len(tap.damage), "wave": tap.wave}
    (OUT / "cling_rows.json").write_text(json.dumps(rows), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("compose", "arm", "check", "cling", "loadout"))
    ap.add_argument("arm", nargs="?", default="A")
    ap.add_argument("--instance", type=int, default=2)
    ap.add_argument("--seconds", type=float, default=90.0)
    ap.add_argument("--seed", type=int, default=95000)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.step == "compose":
        compose()
        return 0
    link = _connect(a.instance)
    prog = Progress(link)
    try:
        if a.step == "arm":
            res = make_arm(link, prog, a.arm)
        elif a.step == "check":
            res = check(link, prog, a.arm, a.seconds, a.seed)
        elif a.step == "loadout":
            _load(link, f"fo_{a.arm}")
            res = loadout(link, prog)
        else:
            res = cling(link, a.seconds, a.seed)
    except (OracleError, TimeoutError, RuntimeError) as e:
        print(f"FAIL {type(e).__name__}: {e}")
        return 1
    finally:
        try:
            link.act(link.frame + 2, 0, hold_frames=0)
            link.rpc("input.release")
        except (OracleError, TimeoutError, OSError):
            pass
        link.close()
    p = OUT / f"{a.step}_{a.arm}_{time.strftime('%H%M%S')}.json"
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str)[:12000])
    print("written", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
