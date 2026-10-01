"""Quit map v0 (DESIGN §3.7.5, §3.7.7 "I3 extended to every window the quit map finds"; M2 W5): per scene and a
coarse state key, P(pause available), P(quit available), blocker statistics, and the windows in which quit was out
of reach, from the oracle's STATE "pause" / "game" fields in recordings.

    qm = QuitMap.load()                                   # knowledge/1.0.30000/quit_map.json
    qm.p_quit("Bone_05", "hurt0")                         # None = no data (treat as not quittable)
    qm.quittable("Bone_05", "free")                       # both P >= 0.99 over >= 1 s of data
    qm.commit_zones("Bone_05")                            # quit-unreachable windows > 0.5 s, as I3 zones

Per frame (real time = STATE udt): pause available = pause.blk == 0 (the PauseGate: a Pause press now pauses);
quit available = that and the Quit item enabled (!disableSaveQuit and no pending ScenePreloader, which is also what
Patch 4 checks besides disablePause). Paused frames and frames without a game are not samples.

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
Built 2026-10-01 from the person's session 20260930_210337 and the trial Bell Beast run 20261001_121446 (3.1 k s of
samples, 48 scenes): hurt0 windows in Bone_05 p50 0.233 s, max 0.25 s (99 hits); spike hazard deaths 2.27-2.32 s;
BossDeathSlow 1.38 s; EnemyBattleEndSlow 1.88 s; entry P(pause) 0.996 (the HUDCamera lock follows only cutscenes,
menus and stag rides); no disableSaveQuit seen; ScenePreloader pending 4.3 s in total.
The builder works on STATE dicts; tools/quit_map_build.py feeds it recordings (only the keys in STATE_KEYS are needed,
so a reader can skip the heavy sections).
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ssbot.safety import game_codes as gc
from ssbot.safety.invariants import CommitZone

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "quit_map.json"
STATE_KEYS = ("f", "udt", "game", "pause", "ev")
KEYS = ("transition", "entry", "hazard", "hurt0", "freeze", "hurt1", "interact", "inventory", "free")
ENEMY_HAZARDS = ("ENEMY", "NON_HAZARD", "EXPLOSION")     # i-frame-blocked damage: a hit, not a hazard death


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
    censored: bool = False      # cut by the end of the samples (pause, end of recording), not by availability

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
        self.cause: str | None = None
        self.cause_t = -1e9
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

    def _close(self, censored: bool = False) -> None:
        for attr in ("win_pause", "win_quit"):
            w = getattr(self, attr)
            if w is not None:
                w.censored = censored
                self._store(attr, w)

    def _events(self, s: dict) -> None:
        for ev in s.get("ev") or ():
            k = ev.get("k")
            d = ev.get("d") or {}
            label = None
            if k == "scene_enter":
                self.entry_t = self.t
                label = "scene_enter"
            elif k == "gs":
                if d.get("to_i") == gc.GS_PLAYING and d.get("from_i") != gc.GS_PAUSED:
                    self.entry_t = self.t
                label = f"gs:{d.get('to')}"
            elif k == "damage":
                hz = d.get("hazard")
                if hz in ENEMY_HAZARDS:
                    self.hit_t = self.t
                else:
                    self.hazard_t, self.hazard_end_t = self.t, None
                label = f"damage:{hz}"
            elif k == "hazard_death":
                self.hazard_t, self.hazard_end_t = self.t, None
                label = f"hazard_death:{d.get('hazard')}"
            elif k == "hazard_respawn" and d.get("phase") == "end":
                self.hazard_end_t = self.t
            elif k == "freeze" and d.get("phase") == "start":
                label = f"freeze:{d.get('type')}"
            elif k in ("special_damage", "catastrophe"):
                label = k
            if label is not None:
                self.cause, self.cause_t = label, self.t

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
        g, p = s.get("game"), s.get("pause")
        self._events(s)
        if not g or not p or g.get("gs") == gc.GS_PAUSED or not g.get("scene"):
            self._close(censored=True)
            return
        scene = g["scene"]
        key = self._key(g, p)
        blk = int(p.get("blk") or 0)
        dsq, preload = bool(p.get("dsq")), bool(p.get("preload"))
        pause_ok = blk == 0
        quit_ok = pause_ok and not dsq and not preload
        sc = self.scenes.setdefault(scene, _Scene())
        sc.acc.setdefault(key, _Acc()).add(dt, pause_ok, quit_ok)
        for bit, name in gc.BLK_NAMES.items():
            if blk & bit:
                sc.bits_s[name] = sc.bits_s.get(name, 0.0) + dt
        sc.dsq_s += dt * dsq
        sc.preload_s += dt * preload
        src["samples"] += 1
        src["s"] += dt
        cause = self.cause if self.t - self.cause_t <= 2.5 / 60 else None   # an event this frame or the last two
        for attr, ok in (("win_pause", pause_ok), ("win_quit", quit_ok)):
            w = getattr(self, attr)
            if ok:
                if w is not None:
                    self._store(attr, w)
                continue
            if w is None:   # a window runs on through scene changes and belongs to the scene it started in
                w = _Window(src=src["name"], scene=scene, f0=int(s.get("f") or 0), key=key, cause=cause)
                setattr(self, attr, w)
            w.s += dt
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
            longs = sorted((w for w in sc.quit_windows if w.s > P.long_s and w.key != "transition"),
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
        return {
            "version": 0, "build": "1.0.30000", **(meta or {}),
            "params": asdict(P),
            "keys": list(KEYS),
            "sources": self.sources,
            "global_by_key": {k: glob[k].summary() for k in KEYS if k in glob},
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

    def quittable(self, scene: str, key: str, min_p: float = 0.99, min_s: float = 1.0) -> bool:
        """Both pause and quit available with P >= min_p, over at least min_s seconds of samples (I1's "quittable")."""
        e = self.entry(scene, key)
        if not e or (e.get("s") or 0.0) < min_s:
            return False
        return (e.get("p_pause") or 0.0) >= min_p and (e.get("p_quit") or 0.0) >= min_p

    def windows(self, scene: str) -> dict:
        sc = self.scenes.get(scene) or {}
        return {"pause": sc.get("pause_windows"), "quit": sc.get("quit_windows"), "long": sc.get("long_windows", [])}

    def commit_zones(self, scene: str, min_s: float = 0.5) -> list[CommitZone]:
        """Quit-unreachable windows longer than min_s, one zone per (state key, cause) with its longest duration."""
        best: dict[tuple[str, str | None], float] = {}
        for w in (self.scenes.get(scene) or {}).get("long_windows", []):
            if w["s"] > min_s and not w.get("censored"):
                k = (w["key"], w.get("cause"))
                best[k] = max(best.get(k, 0.0), w["s"])
        return [CommitZone(key=f"{scene}:{k}:{c}", kind="window", unquittable_s=s)
                for (k, c), s in sorted(best.items(), key=lambda kv: -kv[1])]
