"""Quit map v0 (DESIGN §3.7.5, §3.7.7 "I3 extended to every window the quit map finds"; M2 W5): per scene and a
coarse state key, P(pause available), P(quit available), blocker statistics, and the windows in which quit was out
of reach, from the oracle's STATE "pause" / "game" fields in recordings.

    qm = QuitMap.load()                                   # knowledge/1.0.30000/quit_map.json
    qm.p_quit("Bone_05", "hurt0")                         # None = no data
    qm.quittable("Bone_05", "free")                       # True / False; None = unknown (too little data): I1 stays
                                                          # in force and current_zone() is an "unknown" commit zone
    qm.commit_zones("Bone_05")                            # quit-unreachable windows > 0.5 s, as I3 zones
    qm.zone("hazard_death", "Bone_05", hazard="SPIKES")   # a §3.7.2 kind, length max(code floor, longest seen)

Per frame (real time = STATE udt): pause available = pause.blk == 0 (the PauseGate: a Pause press now pauses);
quit available = that and the Quit item enabled (!disableSaveQuit and no pending ScenePreloader, which is also what
Patch 4 checks besides disablePause). Paused frames, frames without a game and frames between a hero death and the
next scene entry are not samples. A harness operation (STATE event "harness": savestate.load, randomize_start,
death_reset) is not gameplay: the samples of its duration ("ms", logged when it ends, plus 2 frames) are taken back,
the frames after it are no samples until the pause gate first opens (a savestate load in the middle of a boss-death
slow motion leaves the slow motion running in the reloaded room: 23 frames of TIME_SLOWED "entry" per episode in the
live run 20261001_122249), and a window open during the operation or closed within its duration is censored, as is a
window cut by a hero death.
A window that starts in a transition (GameState not PLAYING) is split where PLAYING resumes, and the PLAYING part is
kept as a window of the new scene (typically key "entry": a boss intro or the HUDCamera lock after a cutscene).
A window's cause is the highest-priority event of its first frames (hazard death > hazard damage > enemy damage >
LethalBlock / special damage > freeze > scene change), not the last one logged.

The state key is what the runtime can know without the blocker bits (vision sees hits, freezes, dialogue, entries);
the first that applies wins:
  transition  GameState is not PLAYING (loads, entering / exiting a level, cutscenes)
  entry       < 1.0 s since a scene entry or a return to PLAYING (HUDCamera PreventPause 0.5 s, m0:N14)
  hazard      a hazard death until its respawn ended + 0.5 s (about 2.3 s of no pause for 1 spike hit, probe P7)
  hurt0       < 0.3 s since an enemy hit (the recoil window: no pause for about 0.25 s, probe P7, m0:N8)
  freeze      a FreezeMoment is running (TimeSlowed: hit-stop, BossDeathSlow, EnemyBattleEndSlow ...)
  hurt1       0.3-1.2 s since an enemy hit (i-frames, pausable)
  interact    a BlockingInteractable (dialogue, doors, shops)
  inventory   the inventory is open
  free        anything else
Built 2026-10-01 (tools/quit_map_build.py) from the person's session 20260930_210337 (2 637 s) and the closed
recordings of the Bell Beast runs 20261001_121446 (trial, 448 s) and 20261001_122249 (live, 12 recordings, 48 808 s):
51.9 k s of samples in 48 scenes. P(pause) by key over all scenes: entry 1.0, hazard 0.182, hurt0 0.244, freeze 0,
hurt1 1.0, interact 0.064, free 0.999. Bone_05 hurt0 windows: n = 11 504, p50 0.233 s, p95 0.25 s (probe P7: 0.25 s),
max 0.55 s (a hit during a Bind: the BindBreak freeze, live i2_000 f76332). Longest window per §3.7.2 kind: hazard
death SPIKES 2.317 s, ACID 2.183 s, LAVA 2.433 s; BossDeathSlow 1.383 s; EnemyBattleEndSlow 1.883 s (every BossDeathSlow
of the live run runs through the next savestate.load and is censored). No disableSaveQuit and no pending ScenePreloader
in any sample, so P(quit) = P(pause) everywhere.
The builder works on STATE dicts; tools/quit_map_build.py feeds it recordings (only the keys in STATE_KEYS are needed,
so a reader can skip the heavy sections).
"""
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ssbot.safety import game_codes as gc
from ssbot.safety.invariants import CommitZone, unknown_zone

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "quit_map.json"
STATE_KEYS = ("f", "udt", "game", "pause", "ev")
KEYS = ("transition", "entry", "hazard", "hurt0", "freeze", "hurt1", "interact", "inventory", "free")
ENEMY_HAZARDS = ("ENEMY", "NON_HAZARD", "EXPLOSION")     # i-frame-blocked damage: a hit, not a hazard death
DEATH_EVENTS = ("hero_dead", "player_dead", "permadeath_dead")
# cause label prefix -> priority (higher wins among the events of a window's first frames)
_PRIORITY = {"hazard_death": 6, "hazard_damage": 5, "damage": 4, "special_damage": 3, "catastrophe": 3, "freeze": 2,
             "gs": 1, "scene_enter": 1}
CAUSE_S = 2.5 / 60       # events this close before (or after) a window's first frame name its cause
RECENT_S = 40.0          # closed windows a harness operation can still censor (savestate.load times out at 30 s)
# commit-zone kind of a window cause (QuitMap.kind_max_s)
_KIND_OF_FREEZE = {"BossDeathSlow": "boss_death_slowmo", "EnemyBattleEndSlow": "arena_end_slowmo"}


def _prio(label: str | None) -> int:
    return -1 if label is None else _PRIORITY.get(label.split(":")[0], 0)


def cause_kind(cause: str | None, key: str | None = None) -> tuple[str | None, str | None]:
    """(§3.7.2 commit-zone kind, hazard type) of a stored window's cause and key; (None, None) when it is no kind."""
    c = cause or ""
    if c.startswith("hazard_death:") or c.startswith("hazard_damage:"):
        return "hazard_death", c.split(":", 1)[1] or None
    if c.startswith("freeze:") and c[7:] in _KIND_OF_FREEZE:
        return _KIND_OF_FREEZE[c[7:]], None
    if key == "entry":
        return "room_entry", None
    return None, None


@dataclass(slots=True)
class QuitMapParams:
    entry_s: float = 1.0
    hurt0_s: float = 0.3
    hurt1_s: float = 1.2
    hazard_tail_s: float = 0.5
    hazard_max_s: float = 4.0
    long_s: float = 0.5          # windows longer than this are commit-zone candidates (I3)
    keep_long: int = 12          # per scene, longest first


@dataclass(slots=True)
class _Acc:
    s: float = 0.0
    pause_s: float = 0.0
    quit_s: float = 0.0
    frames: int = 0

    def add(self, dt: float, pause_ok: bool, quit_ok: bool) -> None:
        self.s += dt
        self.frames += 1
        if pause_ok:
            self.pause_s += dt
        if quit_ok:
            self.quit_s += dt

    def summary(self) -> dict:
        return {"s": round(self.s, 3), "frames": self.frames,
                "p_pause": round(self.pause_s / self.s, 5) if self.s > 0 else None,
                "p_quit": round(self.quit_s / self.s, 5) if self.s > 0 else None}


@dataclass(slots=True)
class _Window:
    src: str
    scene: str
    f0: int
    key: str
    cause: str | None
    s: float = 0.0
    bits: int = 0
    dsq: bool = False
    preload: bool = False
    censored: bool = False      # cut by the end of the samples (pause, end of recording, death) or overlapping a
    #                             harness operation: not a gameplay window
    t0: float = 0.0             # builder clock at the window's first frame
    t_end: float = 0.0          # builder clock at the window's last frame

    def row(self) -> dict:
        names = gc.blk_names(self.bits) + (["DISABLE_SAVE_QUIT"] if self.dsq else []) + \
            (["PRELOAD"] if self.preload else [])
        return {"src": self.src, "f0": self.f0, "s": round(self.s, 3), "key": self.key, "cause": self.cause,
                "bits": names, "censored": self.censored}


@dataclass(slots=True)
class _Scene:
    acc: dict[str, _Acc] = field(default_factory=dict)
    bits_s: dict[str, float] = field(default_factory=dict)
    dsq_s: float = 0.0
    preload_s: float = 0.0
    pause_windows: list[_Window] = field(default_factory=list)
    quit_windows: list[_Window] = field(default_factory=list)


class QuitMapBuilder:
    def __init__(self, params: QuitMapParams | None = None):
        self.p = params or QuitMapParams()
        self.scenes: dict[str, _Scene] = {}
        self.sources: list[dict] = []
        self._src: dict | None = None

    def begin(self, source: str, kind: str) -> None:
        """A new recording: per-recording clocks and windows start over."""
        self.end()
        self._src = {"name": source, "kind": kind, "frames": 0, "samples": 0, "s": 0.0}
        self.t = 0.0
        self.entry_t = -1e9
        self.hit_t = -1e9
        self.hazard_t: float | None = None
        self.hazard_end_t: float | None = None
        self.dead = False
        self._causes: list[tuple[float, int, str]] = []      # (t, priority, label) of the last frames' events
        self._recent: list[_Window] = []                     # windows closed lately (harness censoring)
        self._hist: deque = deque()                          # recent samples (t, scene, key, dt, ok, quit_ok, ...)
        self.harness_hold = False                            # after a harness op, until the pause gate opens
        self.win_pause: _Window | None = None
        self.win_quit: _Window | None = None

    def end(self) -> None:
        if self._src is None:
            return
        self._close(censored=True)
        self._src["s"] = round(self._src["s"], 2)
        self.sources.append(self._src)
        self._src = None

    def _store(self, attr: str, w: _Window) -> None:
        sc = self.scenes[w.scene]
        (sc.pause_windows if attr == "win_pause" else sc.quit_windows).append(w)
        setattr(self, attr, None)
        self._recent.append(w)

    def _close(self, censored: bool = False) -> None:
        for attr in ("win_pause", "win_quit"):
            w = getattr(self, attr)
            if w is not None:
                w.censored = w.censored or censored
                self._store(attr, w)

    def _censor_harness(self, d: dict) -> None:
        """A harness operation: windows open now, or closed while it ran (its "ms", plus 2 frames), are not
        gameplay (trial f56112: a BossDeathSlow window ran through a savestate.load); the samples of that span are
        taken back and the frames after it are held out until the pause gate opens."""
        since = self.t - float(d.get("ms") or 0.0) / 1000.0 - 2 / 60
        for w in self._recent:
            if w.t_end >= since:
                w.censored = True
        for attr in ("win_pause", "win_quit"):
            w = getattr(self, attr)
            if w is not None:
                w.censored = True
        while self._hist and self._hist[-1][0] >= since:
            self._count(*self._hist.pop()[1:], sign=-1)
        self.harness_hold = True

    def _count(self, scene: str, key: str, dt: float, pause_ok: bool, quit_ok: bool, blk: int, dsq: bool,
               preload: bool, sign: int = 1) -> None:
        """Add (sign 1) or take back (sign -1) one sample."""
        sc = self.scenes.setdefault(scene, _Scene())
        a = sc.acc.setdefault(key, _Acc())
        a.s += sign * dt
        a.frames += sign
        a.pause_s += sign * dt * pause_ok
        a.quit_s += sign * dt * quit_ok
        for bit, name in gc.BLK_NAMES.items():
            if blk & bit:
                sc.bits_s[name] = sc.bits_s.get(name, 0.0) + sign * dt
        sc.dsq_s += sign * dt * dsq
        sc.preload_s += sign * dt * preload
        self._src["samples"] += sign
        self._src["s"] += sign * dt

    def _events(self, s: dict) -> None:
        for ev in s.get("ev") or ():
            k = ev.get("k")
            d = ev.get("d") or {}
            label = None
            if k == "scene_enter":
                self.entry_t = self.t
                self.dead = False
                label = "scene_enter"
            elif k == "gs":
                if d.get("to_i") == gc.GS_PLAYING and d.get("from_i") != gc.GS_PAUSED:
                    self.entry_t = self.t
                label = f"gs:{d.get('to')}"
            elif k == "damage":
                hz = d.get("hazard")
                if hz in ENEMY_HAZARDS:
                    self.hit_t = self.t
                    label = f"damage:{hz}"
                else:
                    self.hazard_t, self.hazard_end_t = self.t, None
                    label = f"hazard_damage:{hz}"
            elif k == "hazard_death":
                self.hazard_t, self.hazard_end_t = self.t, None
                label = f"hazard_death:{d.get('hazard')}"
            elif k == "hazard_respawn" and d.get("phase") == "end":
                self.hazard_end_t = self.t
            elif k == "freeze" and d.get("phase") == "start":
                label = f"freeze:{d.get('type')}"
            elif k in ("special_damage", "catastrophe"):
                label = k
            elif k in DEATH_EVENTS:
                self.dead = True
            elif k == "harness":
                self._censor_harness(d)
            if label is not None:
                self._causes.append((self.t, _PRIORITY[label.split(":")[0]], label))

    def _cause(self) -> str | None:
        """Highest-priority event label of this frame and the last two (latest on ties)."""
        self._causes = [c for c in self._causes if self.t - c[0] <= CAUSE_S]
        return max(self._causes, key=lambda c: (c[1], c[0]))[2] if self._causes else None

    def _key(self, g: dict, p: dict) -> str:
        P, t = self.p, self.t
        if g.get("gs") != gc.GS_PLAYING:
            return "transition"
        if t - self.entry_t < P.entry_s:
            return "entry"
        if self.hazard_t is not None:
            over = (self.hazard_end_t is not None and t - self.hazard_end_t > P.hazard_tail_s) or \
                t - self.hazard_t > P.hazard_max_s
            if over:
                self.hazard_t = self.hazard_end_t = None
            else:
                return "hazard"
        if t - self.hit_t < P.hurt0_s:
            return "hurt0"
        if (g.get("slowed") or 0) > 0:
            return "freeze"
        if t - self.hit_t < P.hurt1_s:
            return "hurt1"
        if p.get("interact"):
            return "interact"
        if p.get("inv"):
            return "inventory"
        return "free"

    def add(self, s: dict) -> None:
        src = self._src
        if src is None:
            raise RuntimeError("begin() a source first")
        src["frames"] += 1
        dt = float(s.get("udt") or 0.0)
        self.t += dt
        self._recent = [w for w in self._recent if self.t - w.t_end <= RECENT_S]
        while self._hist and self.t - self._hist[0][0] > RECENT_S:
            self._hist.popleft()
        g, p = s.get("game"), s.get("pause")
        self._events(s)
        if not g or not p or g.get("gs") == gc.GS_PAUSED or not g.get("scene") or self.dead:
            self._close(censored=True)
            return
        blk = int(p.get("blk") or 0)
        if self.harness_hold:
            if blk:
                self._close(censored=True)
                return
            self.harness_hold = False
        scene = g["scene"]
        key = self._key(g, p)
        dsq, preload = bool(p.get("dsq")), bool(p.get("preload"))
        pause_ok = blk == 0
        quit_ok = pause_ok and not dsq and not preload
        sample = (scene, key, dt, pause_ok, quit_ok, blk, dsq, preload)
        self._count(*sample)
        self._hist.append((self.t,) + sample)
        cause = self._cause()
        for attr, ok in (("win_pause", pause_ok), ("win_quit", quit_ok)):
            w = getattr(self, attr)
            if w is not None and (ok or (w.key == "transition" and key != "transition")):
                self._store(attr, w)       # a transition window ends where PLAYING resumes; the rest is the new room's
                w = None
            if ok:
                continue
            if w is None:   # otherwise a window runs on through scene changes and belongs to the scene it started in
                w = _Window(src=src["name"], scene=scene, f0=int(s.get("f") or 0), key=key, cause=cause, t0=self.t)
                setattr(self, attr, w)
            elif cause != w.cause and self.t - w.t0 <= CAUSE_S and _prio(cause) > _prio(w.cause):
                w.cause = cause            # a higher-priority event in the window's first frames (hazard after freeze)
            w.s += dt
            w.t_end = self.t
            w.bits |= blk
            w.dsq |= dsq
            w.preload |= preload

    def build(self, meta: dict | None = None) -> dict:
        self.end()
        P = self.p
        scenes, glob = {}, {}
        for name in sorted(self.scenes):
            sc = self.scenes[name]
            tot = _Acc()
            for k, a in sc.acc.items():
                tot.s += a.s
                tot.pause_s += a.pause_s
                tot.quit_s += a.quit_s
                tot.frames += a.frames
                g = glob.setdefault(k, _Acc())
                g.s += a.s
                g.pause_s += a.pause_s
                g.quit_s += a.quit_s
                g.frames += a.frames
            longs = sorted((w for w in sc.quit_windows if w.s > P.long_s and w.key != "transition" and not w.censored),
                           key=lambda w: -w.s)[:P.keep_long]
            scenes[name] = {
                **tot.summary(),
                "by_key": {k: sc.acc[k].summary() for k in KEYS if k in sc.acc},
                "blockers_s": {k: round(v, 3) for k, v in sorted(sc.bits_s.items())},
                "dsq_s": round(sc.dsq_s, 3), "preload_s": round(sc.preload_s, 3),
                "pause_windows": _window_stats(sc.pause_windows),
                "quit_windows": _window_stats(sc.quit_windows),
                "long_windows": [w.row() for w in longs],
            }
        kinds: dict[str, dict] = {}
        for sc in self.scenes.values():
            for w in sc.quit_windows:
                kind, hz = cause_kind(w.cause, w.key)
                if kind is None or w.censored:
                    continue
                e = kinds.setdefault(kind, {"n": 0, "max_s": 0.0, "by_hazard": {}})
                e["n"] += 1
                e["max_s"] = round(max(e["max_s"], w.s), 3)
                if hz:
                    e["by_hazard"][hz] = round(max(e["by_hazard"].get(hz, 0.0), w.s), 3)
        return {
            "version": 0, "build": "1.0.30000", **(meta or {}),
            "params": asdict(P),
            "keys": list(KEYS),
            "sources": self.sources,
            "global_by_key": {k: glob[k].summary() for k in KEYS if k in glob},
            "kinds": {k: kinds[k] for k in sorted(kinds)},
            "scenes": scenes,
        }


def _pct(xs: np.ndarray, q: float) -> float:
    return round(float(np.percentile(xs, q)), 3)


def _window_stats(ws: list[_Window]) -> dict:
    done = [w for w in ws if not w.censored]
    out: dict = {"n": len(done), "censored": len(ws) - len(done)}
    if not done:
        return out
    d = np.array([w.s for w in done])
    out.update(total_s=round(float(d.sum()), 3), p50_s=_pct(d, 50), p95_s=_pct(d, 95), max_s=round(float(d.max()), 3))
    by: dict[str, dict] = {}
    for k in KEYS:
        dk = np.array([w.s for w in done if w.key == k])
        if dk.size:
            by[k] = {"n": int(dk.size), "p50_s": _pct(dk, 50), "max_s": round(float(dk.max()), 3)}
    out["by_key"] = by
    return out


class QuitMap:
    """Read-only queries over a built quit map (dict as written by QuitMapBuilder.build)."""

    def __init__(self, data: dict):
        self.data = data
        self.scenes: dict = data.get("scenes") or {}

    @classmethod
    def load(cls, path: str | Path = DEFAULT_PATH) -> "QuitMap":
        return cls(json.loads(Path(path).read_text("utf-8")))

    def entry(self, scene: str, key: str, fallback: bool = False) -> dict | None:
        e = (self.scenes.get(scene) or {}).get("by_key", {}).get(key)
        if e is None and fallback:
            e = (self.data.get("global_by_key") or {}).get(key)
        return e

    def p_pause(self, scene: str, key: str, fallback: bool = False) -> float | None:
        e = self.entry(scene, key, fallback)
        return None if e is None else e.get("p_pause")

    def p_quit(self, scene: str, key: str, fallback: bool = False) -> float | None:
        e = self.entry(scene, key, fallback)
        return None if e is None else e.get("p_quit")

    def quittable(self, scene: str, key: str, min_p: float = 0.99, min_s: float = 1.0) -> bool | None:
        """Both pause and quit available with P >= min_p (I1's "quittable"); None (unknown) with less than min_s
        seconds of samples for this scene and key. Unknown is not "not quittable": I1 stays in force (invariants.i1)
        and current_zone() makes it an I3 commit zone of unknown length."""
        e = self.entry(scene, key)
        if not e or (e.get("s") or 0.0) < min_s:
            return None
        return (e.get("p_pause") or 0.0) >= min_p and (e.get("p_quit") or 0.0) >= min_p

    def known_scene(self, scene: str, min_s: float = 10.0) -> bool:
        return ((self.scenes.get(scene) or {}).get("s") or 0.0) >= min_s

    def windows(self, scene: str) -> dict:
        sc = self.scenes.get(scene) or {}
        return {"pause": sc.get("pause_windows"), "quit": sc.get("quit_windows"), "long": sc.get("long_windows", [])}

    def commit_zones(self, scene: str, min_s: float = 0.5) -> list[CommitZone]:
        """Quit-unreachable windows longer than min_s, one zone per (state key, cause) with its longest duration; for
        a scene the map has (almost) no data on, one "unknown" zone of unbounded length (a missing estimate must not
        leave I3 with nothing to check)."""
        if not self.known_scene(scene):
            return [unknown_zone(f"{scene}:unknown")]
        best: dict[tuple[str, str | None], float] = {}
        for w in (self.scenes.get(scene) or {}).get("long_windows", []):
            if w["s"] > min_s and not w.get("censored"):
                k = (w["key"], w.get("cause"))
                best[k] = max(best.get(k, 0.0), w["s"])
        return [CommitZone(key=f"{scene}:{k}:{c}", kind="window", unquittable_s=s)
                for (k, c), s in sorted(best.items(), key=lambda kv: -kv[1])]

    def current_zone(self, scene: str, key: str, min_p: float = 0.99, min_s: float = 1.0) -> CommitZone | None:
        """The unquittable window the hero is in for (scene, key): None when quittable; the longest quit window seen
        for that key (by_key max) when not; an "unknown" zone when the map cannot tell."""
        q = self.quittable(scene, key, min_p, min_s)
        if q:
            return None
        by = (((self.scenes.get(scene) or {}).get("quit_windows") or {}).get("by_key") or {}).get(key)
        if q is None or not by:
            return unknown_zone(f"{scene}:{key}:unknown")
        return CommitZone(key=f"{scene}:{key}", kind="window", unquittable_s=by["max_s"])

    def kind_max_s(self, kind: str, scene: str | None = None, hazard: str | None = None) -> float | None:
        """Longest window of a §3.7.2 kind seen: for hazard deaths and death / arena-end slow motion over the whole
        map (game constants; per hazard type when given and seen, else every type), for room entries in `scene`."""
        out = None
        if kind != "room_entry":
            e = (self.data.get("kinds") or {}).get(kind)
            if e:
                out = (e.get("by_hazard") or {}).get(hazard) if hazard else None
                out = e.get("max_s") if out is None else out
        if scene is not None:
            for w in (self.scenes.get(scene) or {}).get("long_windows", []):
                if not w.get("censored") and cause_kind(w.get("cause"), w.get("key"))[0] == kind:
                    out = max(out or 0.0, w["s"])
        return out

    def zone(self, kind: str, scene: str, hazard: str | None = None, hazard_damage: int = 1,
             window=None) -> CommitZone:
        """A §3.7.2 commit zone whose length is the larger of the code floor (invariants.ZONE_KINDS) and the longest
        window of that kind the map has seen."""
        seen = self.kind_max_s(kind, scene, hazard)
        return CommitZone(key=f"{scene}:{kind}" + (f":{hazard}" if hazard else ""), kind=kind, unquittable_s=seen,
                          window=window, hazard_damage=hazard_damage)
