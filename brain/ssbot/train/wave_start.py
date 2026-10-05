"""Start a Forum gauntlet at wave index i for training (Forum plan R1 item 1, docs/plans/forum_planner_plan.md): for
targeted data collection and, later, a curriculum. Gates stay on full gauntlets (DESIGN §3.9.3).

The way in use: a DebugMod savestate taken during wave i (STATE_PREFIX, make_wave_states). DebugMod's RoomSpecific
saves "BattleScene|Battle Scene|<currentWave>" and its load sets currentWave before StartBattle, with a transpiler that
turns DoStartBattle's StartWave(0) into StartWave(currentWave): the battle restarts at wave i by itself (no roar; the
Start Range trigger is already used). What such a load does not give (docs/facts/1.0.30000/forum.md 13.1):
  - the helper from wave 2 on: wave 1's "Call Ally" fires on its own WAVE START only (a w1 load does bring Garmond);
  - an overlapping earlier wave's survivors (the wave starts alone);
  - a natural wave clock: room.battles reports wave i as soon as the battle starts (battleStartPause 0.75 s after
    the load), startDelay(i) (0-3 s) before the members are activated (wait_wave_active: the first STATE with the
    battle's currentEnemies > 0);
  - a natural child count: the members of waves 0..i-1 that never ran stay children of their wave objects, and
    BattleScene.DoCheckEnemiesNew counts childCount over waves 0..currentWave, so an overlapping wave (Forum wave 2,
    remainingEnemyToEnd 2) waits for a kill instead of its 1 s count check, and a doubled StartWave is not corrected.
    prune_ghosts removes them through the oracle RPC "battle.prune" (oracle commit after 06a7c2b, needs a deploy;
    without it the episode records ghosts="unpruned").

Skipping a running battle forward (skip_to_wave, used to make the savestates):
  oracle   RPC "battle.wave" {wave} (oracle 06a7c2b, needs a deploy): kills the live members of the waves before
           `wave` through HealthManager.Die, so the BattleScene advances by its own rules (start delays, the 1 s
           enemy-count checks, wave 1's "Call Ally"); about the waves' start delays plus 1 s per wave.
  policy   with the deployed oracle: the hero kills them herself, made invincible and strong for the skip through
           the oracle's debug line server (PlayerData isInvincible true, nailUpgrades 4: nail damage 21, Silk Spear
           kept charged with silk 9), driven by WaveSkipPolicy; the PlayerData values are put back when the wave
           starts. Slow on the Maestro waves (wave 6: 353 s of game time), but the BattleScene advances by itself.
Both stop when STATE room.battles reports currentWave == wave, then report what is in play (verify_wave_start).
"""
import math
import socket
import time

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.train.gauntlet import live_enemies, type_key

DEBUG_BASE_PORT = 47631          # the oracle's debug line server: 47631 + instance (oracle/src/Ipc/DebugServer.cs)
B = {k: mask(k) for k in ("left", "right", "jump", "attack", "up", "down", "quickcast", "dash")}
BOOST = (("nailUpgrades", "4"), ("isInvincible", "True"))
# Reaper reach relative to the hero transform, +x forward (knowledge/1.0.30000/attacks/reaper.json, M2.md: side slash
# x -0.25..3.60, y -0.42..2.69; up slash x -2.12..0.81, y -0.63..3.77), a little inside so the swing lands
SIDE_X, SIDE_Y = (0.0, 3.2), (-0.4, 2.5)
UP_X, UP_Y = (-1.6, 0.6), (0.4, 3.5)


class DebugLine:
    """One persistent connection to the oracle's debug line server (training-only commands: pdget / pdset). Kept
    open for an episode: a client that disconnects makes the server release the keys it set (none here)."""

    def __init__(self, instance: int, timeout_s: float = 5.0):
        self.sock = socket.create_connection(("127.0.0.1", DEBUG_BASE_PORT + instance), timeout=timeout_s)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.f = self.sock.makefile("rw", encoding="utf-8", newline="\n")

    def cmd(self, line: str) -> str:
        self.f.write(line + "\n")
        self.f.flush()
        r = self.f.readline().strip()
        if r.startswith("err"):
            raise OracleError(f"debug line {line!r}: {r}")
        return r

    def pdget(self, field: str) -> str:
        return self.cmd(f"pdget {field}")

    def pdset(self, field: str, value) -> str:
        return self.cmd(f"pdset {field} {value}")

    def close(self) -> None:
        try:
            self.f.close()
            self.sock.close()
        except OSError:
            pass


_CS_NAMES: list[str] | None = None


def hero_flags(s: dict) -> dict:
    """The hero's cState bools by name (docs/facts/1.0.30000/cstate_schema.json, as GauntletDataPolicy reads them)."""
    global _CS_NAMES
    if _CS_NAMES is None:
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[3] / "docs" / "facts" / "1.0.30000" / "cstate_schema.json"
        _CS_NAMES = json.loads(p.read_text(encoding="utf-8"))["bools"]
    from ssbot.tools.cstate import decode
    try:
        return decode(s["hero"]["cstate"], _CS_NAMES)
    except (KeyError, ValueError, TypeError):
        return {}


def body_box(e: dict) -> tuple[float, float, float, float]:
    """The entity's extent (x0, y0, x1, y1): its enabled colliders that hurt the hero (the Choir Clapper also carries
    enabled colliders that do not, "Tile Smasher" and the "... Ally" slams, much wider than its body), else all its
    enabled colliders, else the render box, else a point at pos."""
    for hurting in (True, False):
        xs, ys = [], []
        for c in e.get("colliders") or ():
            if not c.get("enabled") or (hurting and not ((c.get("damage") or {}).get("eff") or 0)):
                continue
            v = c.get("verts_world") or ()
            xs += v[0::2]
            ys += v[1::2]
        if xs:
            return min(xs), min(ys), max(xs), max(ys)
    rb = e.get("render_aabb")
    if rb and len(rb) >= 4:
        return rb[0], rb[1], rb[2], rb[3]
    x, y = e["pos"][0], e["pos"][1]
    return x, y, x, y


def overlaps(lo: float, hi: float, a: float, b: float) -> bool:
    return lo <= b and a <= hi


class WaveSkipPolicy:
    """Kills the live wave members as fast as a hero can: nearest first, side slash in reach, up slash under a flier,
    down slash over one, Silk Spear on the level, dash to close the distance. Hold times are game seconds turned into
    frames with the STATE dt, so it plays the same at any time scale. Not a data policy: only for skip_to_wave."""

    def __init__(self, wave_types: set[str]):
        self.wave_types = wave_types
        self.hold = {k: 0 for k in B}
        self.rest = {k: 0 for k in B}
        self.frames = 0

    def _frames(self, s: dict, sec: float) -> int:
        dt = float(s.get("dt") or 1.0 / 60.0) or 1.0 / 60.0
        return max(2, math.ceil(sec / dt))

    def _press(self, k: str, n: int) -> None:
        if self.hold[k] == 0 and self.rest[k] == 0:
            self.hold[k] = max(2, n)

    def act(self, s: dict) -> int:
        self.frames += 1
        h = s.get("hero") or {}
        if not h.get("pos"):
            return 0
        hx, hy = h["pos"][0], h["pos"][1]
        facing = 1 if (h.get("facing") or 1) > 0 else -1
        live = [e for e in live_enemies(s) if type_key(e.get("type_key")) in self.wave_types]
        move = None
        if live:
            def gap(e):
                x0, y0, x1, y1 = body_box(e)
                gx = max(x0 - hx, hx - x1, 0.0)
                gy = max(y0 - (hy + 1.5), (hy - 0.5) - y1, 0.0)
                return gx + gy
            t = min(live, key=gap)
            x0, y0, x1, y1 = body_box(t)
            cx = (x0 + x1) / 2.0
            side = 1 if cx >= hx else -1
            fx0, fx1 = (hx + SIDE_X[0], hx + SIDE_X[1]) if side > 0 else (hx - SIDE_X[1], hx - SIDE_X[0])
            in_side = overlaps(fx0, fx1, x0, x1) and overlaps(hy + SIDE_Y[0], hy + SIDE_Y[1], y0, y1)
            in_up = overlaps(hx + UP_X[0], hx + UP_X[1], x0, x1) and overlaps(hy + UP_Y[0], hy + UP_Y[1], y0, y1)
            airborne = not hero_flags(s).get("onGround", hy < 4.8)
            gx = max(x0 - hx, hx - x1, 0.0)
            if in_side:
                if facing != side:
                    move = "right" if side > 0 else "left"
                else:
                    self._press("attack", 2)
            elif in_up:
                move = "right" if side > 0 else "left"
                self._press("up", self._frames(s, 0.15))
                self._press("attack", 2)
            elif y0 > hy + 2.2 and gx < 1.6:
                # a flier above: jump under it, up-slash on the way
                if not airborne:
                    self._press("jump", self._frames(s, 0.35))
                move = "right" if cx > hx + 0.3 else "left" if cx < hx - 0.3 else None
            elif y1 < hy - 1.0 and airborne and gx < 1.2:
                move = "right" if side > 0 else "left"
                self._press("down", self._frames(s, 0.2))
                self._press("attack", 2)
            else:
                move = "right" if side > 0 else "left"
                if gx > 7.0 and not airborne:
                    self._press("dash", 2)
            # Silk Spear along the floor line: silk is topped up by the skip loop
            if (h.get("silk") or 0) >= 4 and facing == side and abs((y0 + y1) / 2.0 - (hy + 0.5)) < 1.6 and gx < 14.0:
                self._press("quickcast", 2)
        m = 0
        for k in B:
            if self.hold[k] > 0:
                self.hold[k] -= 1
                m |= B[k]
                if self.hold[k] == 0:
                    self.rest[k] = 2
            elif self.rest[k] > 0:
                self.rest[k] -= 1
        if move:
            m |= B[move]
        if m & (B["up"] | B["down"]) and not m & (B["left"] | B["right"]):
            m &= ~(B["up"] | B["down"])
        return m


# Control states of entities that are in the room but not fighting: the Maestros' pooled "Song Automaton Tiny" sit at
# their Maestro's spawn point in "Dead" until summoned (fo_r1_w3, 2026-10-04: nine of them, colliders off). Since the
# R1 close-out gauntlet.WAITING_STATES has "Dead" too, so live_enemies already leaves them out; kept for the records'
# tools that filter with it (forum_r1_audit) and as the explicit name of the parked summons.
PARKED_STATES = frozenset(("Dead",))


def fighting(s: dict) -> list[dict]:
    """live_enemies without the parked summons (PARKED_STATES; a no-op filter since WAITING_STATES has them)."""
    return [e for e in live_enemies(s)
            if not any(f.get("state") in PARKED_STATES for f in e.get("fsms") or ())]


def battle_of(s: dict, name: str = "Battle Scene") -> dict | None:
    bl = (s.get("room") or {}).get("battles") or ()
    return next((b for b in bl if b.get("name") == name), bl[0] if bl else None)


def verify_wave_start(s: dict, enc, wave: int) -> dict:
    """What is in play at the wave's start (types and positions), the battle's own counters, the helpers: the check
    that a skip left the battle as a natural run of the gauntlet would be at that wave."""
    b = battle_of(s, enc.battle_name) or {}
    live = fighting(s)
    expected = [type_key(n) for n in enc.waves[wave].enemies]
    types = sorted(type_key(e.get("type_key")) for e in live)
    allies = [{"name": a.get("name"), "state": a.get("state"), "active": a.get("active"),
               "pos": [round(v, 2) for v in (a.get("pos") or ())[:2]]} for a in s.get("allies") or ()
              if str(a.get("name", "")).endswith("Fighter")]
    return {"wave": b.get("wave"), "started": b.get("started"), "completed": b.get("completed"),
            "enemies": b.get("enemies"), "to_next": b.get("to_next"), "in_play": types,
            "expected_new": sorted(expected),
            "new_present": all(types.count(t) >= expected.count(t) for t in set(expected)),
            "hero": {"hp": (s.get("hero") or {}).get("health"), "pos": [round(v, 2) for v in
                                                                     ((s.get("hero") or {}).get("pos") or ())[:2]]},
            "allies": allies}


STATE_PREFIX = "fo_r1_w"      # wave-start savestates: fo_r1_w<i>, taken at wave i's activation (make_wave_states)


def wait_wave_start(link: OracleLink, enc, wave: int, timeout_s: float = 30.0) -> dict:
    """After a wave-start savestate load: keep the keys up until room.battles reports the battle started at `wave`
    (DebugMod's RoomSpecific restores currentWave and calls StartBattle; the Start Range trigger is already woken)."""
    last = link.frame
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        s = link.wait_state(newer_than=last, timeout_s=3.0)
        last = s["f"]
        b = battle_of(s, enc.battle_name) or {}
        if b.get("started") and b.get("wave", -1) >= wave:
            return s
        link.act(last + 2, 0, hold_frames=0)
    raise RuntimeError(f"the wave-start savestate did not start wave {wave} within {timeout_s:.0f} s")


def wait_wave_active(link: OracleLink, enc, wave: int, after: int | None = None, timeout_s: float = 10.0) -> dict:
    """The first STATE (newer than `after`) in which the battle at `wave` has activated its members: room.battles
    currentEnemies > 0 (BattleWave.WaveStarted counts them in, startDelay after StartWave). After a wave-start load
    room.battles reports the wave from the battle start on (module docstring), so this is the wave's real start.
    Keeps the keys up while it waits."""
    last = link.frame if after is None else after
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        s = link.wait_state(newer_than=last, timeout_s=3.0)
        last = s["f"]
        b = battle_of(s, enc.battle_name) or {}
        if b.get("started") and b.get("wave", -1) >= wave and (b.get("enemies") or 0) > 0:
            return s
        link.act(last + 2, 0, hold_frames=0)
    raise RuntimeError(f"wave {wave} did not activate its members within {timeout_s:.0f} s")


def prune_ghosts(link: OracleLink) -> dict:
    """Remove the never-run members of the earlier waves after a wave-start load (oracle RPC "battle.prune", module
    docstring). Returns the RPC's reply, or {"pruned": None, "error": ...} when the deployed oracle lacks it."""
    try:
        r = link.rpc("battle.prune", timeout_s=10)
        return r if isinstance(r, dict) else {"pruned": None, "reply": r}
    except OracleError as e:
        return {"pruned": None, "error": str(e)}


def make_wave_states(link: OracleLink, enc, waves: list[int], instance: int, prefix: str = STATE_PREFIX,
                     timeout_s: float = 900.0) -> dict:
    """One gauntlet from the encounter's savestate (intro already run): skip by policy to max(waves) and at the first
    STATE of each listed wave save <prefix><i> (boost off, input released: the save carries the route's PlayerData).
    DebugMod's savestate keeps "BattleScene|<name>|<currentWave>" (RoomSpecific.SaveBattleScene) and restarts the
    battle at that wave on load (forum.md R1: what such a load restores and what it does not)."""
    want = set(waves)

    def save(i: int, s: dict):
        if i not in want:
            return None
        r = link.rpc("savestate.save", timeout_s=30, name=f"{prefix}{i}")
        return {"name": r.get("name"), "pos": r.get("pos"), "hp": r.get("hp"), "verify": verify_wave_start(s, enc, i)}

    return skip_to_wave(link, enc, max(waves), instance, timeout_s=timeout_s, method="policy", on_wave=save)


def skip_to_wave(link: OracleLink, enc, wave: int, instance: int, timeout_s: float = 600.0,
                 method: str = "auto", log: list | None = None, on_wave=None) -> dict:
    """After the intro (battle started): advance the BattleScene to `wave` (module docstring). Returns {method, wave,
    real_s, game_s, frames, kills?, verify}. Raises RuntimeError when the wave is not reached in time."""
    t0 = time.monotonic()
    f0 = link.frame
    out: dict = {"target": wave}
    if wave <= 0:
        out.update(method="none", real_s=0.0, frames=0)
        out["verify"] = verify_wave_start(link.state or {}, enc, 0)
        return out
    if method in ("auto", "oracle") and on_wave is None:
        try:
            r = link.rpc("battle.wave", timeout_s=timeout_s + 10, wave=wave, timeout=timeout_s)
            out.update(method="oracle", oracle=r)
        except OracleError as e:
            if method == "oracle" or "unknown" not in str(e).lower():
                raise RuntimeError(f"battle.wave failed: {e}") from e
            out["oracle_error"] = str(e)
    if out.get("method") != "oracle":
        out.update(_skip_by_policy(link, enc, wave, instance, timeout_s, on_wave=on_wave))
    s = link.wait_state(lambda s: (battle_of(s, enc.battle_name) or {}).get("wave", -1) >= wave, timeout_s=10.0)
    out["real_s"] = round(time.monotonic() - t0, 2)
    out["frames"] = s["f"] - f0
    out["verify"] = verify_wave_start(s, enc, wave)
    if log is not None:
        log.append({"skip": {k: v for k, v in out.items() if k != "verify"}, "verify": out["verify"]})
    return out


def _skip_by_policy(link: OracleLink, enc, wave: int, instance: int, timeout_s: float,
                    on_wave=None) -> dict:
    """WaveSkipPolicy with the boost on until room.battles reports `wave`. on_wave(i, state), when given, is called
    at the first STATE of every wave i in 1..wave with the boost taken off and the input released (the savestate
    maker saves there: a save must not carry the boosted PlayerData), then the boost goes back on."""
    wave_types = {t for w in enc.waves for t in w.types}
    pol = WaveSkipPolicy(wave_types)
    dbg = DebugLine(instance)
    saved: dict[str, str] = {}
    game_s = 0.0
    seen = 0
    calls = []

    def boost(on: bool) -> None:
        for k, v in BOOST + (("silk", "9"),):
            if on:
                saved.setdefault(k, dbg.pdget(k))
                dbg.pdset(k, v)
            elif k in saved:
                dbg.pdset(k, saved[k])

    try:
        boost(True)
        deadline = time.monotonic() + timeout_s
        last = link.frame
        n = 0
        while True:
            s = link.wait_state(newer_than=last, timeout_s=3.0)
            last = s["f"]
            game_s += float(s.get("dt") or 0.0)
            b = battle_of(s, enc.battle_name) or {}
            w = b.get("wave", -1) if b.get("started") else -1
            if on_wave is not None and w > seen:
                for i in range(seen + 1, min(w, wave) + 1):
                    link.act(last + 2, 0, hold_frames=0)
                    link.rpc("input.release", timeout_s=10)
                    boost(False)
                    calls.append({"wave": i, "f": s["f"], "result": on_wave(i, s)})
                    if i < wave:
                        boost(True)
                seen = w
                last = link.frame
            if w >= wave:
                break
            if b.get("completed"):
                raise RuntimeError("the battle ended during the skip")
            if time.monotonic() > deadline:
                raise RuntimeError(f"skip to wave {wave}: still at wave {b.get('wave')} after {timeout_s:.0f} s")
            link.act(last + 2, pol.act(s), hold_frames=0)
            n += 1
            if n % 30 == 0 and ((s.get("hero") or {}).get("silk") or 0) < 9:
                dbg.pdset("silk", 9)
        link.act(link.frame + 2, 0, hold_frames=0)
    finally:
        try:
            boost(False)
        except (OracleError, OSError):
            pass
        dbg.close()
    return {"method": "policy", "game_s": round(game_s, 2), "acts": pol.frames, "restored": saved,
            **({"on_wave": calls} if on_wave is not None else {})}
