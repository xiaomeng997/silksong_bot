"""Rerun viewer for an episode recording (DESIGN §3.10 tools), keyed on the oracle frame number ("frame" timeline).

    python -m ssbot.tools.viewer runs/2026-09-30/TRAIN/ep1              # spawn the Rerun viewer
    python -m ssbot.tools.viewer runs/.../ep1 --save ep1.rrd --from 1200 --to 5000 --ents-stride 2

Shows, as far as the recording has them:
  world/            hero position + per-scene trajectory, entity collider polygons ("ents"), TERRAIN polygons.
                    World y is negated when logged, so up is up in Rerun's y-down 2D view.
  series/hero       hp, max hp, blue hp, silk, silk max          series/time    t_live, t_saved, t_sess
  series/oracle     STATE build cost_us, time scale, oracle drop counter
  states/           GameState, scene, focus, and one lane per pause blocker bit ("pause.blk")
  events            every STATE event as a text log line

Sections are resolved defensively: the exporters for hero/ents/TERRAIN are built in parallel with this tool, so each
value is looked up under several plausible key paths (DESIGN §3.1.2 names first) and silently skipped when absent or
nil. `--series NAME=a.b.c` adds any other numeric STATE value as a series.
"""
import argparse
import math
import sys
import zlib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

from ssbot.record.recorder import RecordingReader

GAME_STATES = ("INACTIVE", "MAIN_MENU", "LOADING", "ENTERING_LEVEL", "PLAYING", "PAUSED", "EXITING_LEVEL",
               "CUTSCENE", "PRIMER")
# oracle/src/Export/BasicExporters.cs PauseExporter: Esc pauses only when blk == 0.
BLK_BITS = ("DISABLE_PAUSE", "TIME_SLOWED", "PAUSE_LOCKOUT", "MSG_CANVAS", "BLOCKING_INTERACT",
            "NOT_ACCEPTING_INPUT", "GAME_STATE_NOT_PLAYING")

P = tuple[str, ...]
HERO_POS: tuple[P, ...] = (("hero", "pos"), ("hero", "position"), ("hero", "p"))
SCENE: tuple[P, ...] = (("game", "scene"), ("game", "scene_raw"))
SERIES: dict[str, tuple[P, ...]] = {
    "series/hero/hp": (("hero", "health"), ("hero", "hp"), ("pd", "health"), ("player", "health")),
    "series/hero/hp_max": (("hero", "maxHealth"), ("hero", "max_health"), ("hero", "hp_max"), ("pd", "maxHealth")),
    "series/hero/hp_blue": (("hero", "healthBlue"), ("hero", "health_blue"), ("hero", "blue"), ("pd", "healthBlue")),
    "series/hero/silk": (("hero", "silk"), ("pd", "silk"), ("player", "silk")),
    "series/hero/silk_max": (("hero", "silk_max"), ("hero", "silkMax"), ("pd", "silk_max"), ("pd", "silkMax")),
    "series/time/t_live": (("game", "t_live"),),
    "series/time/t_saved": (("game", "t_saved"),),
    "series/time/t_sess": (("game", "t_sess"),),
    "series/oracle/cost_us": (("cost_us",),),
    "series/oracle/time_scale": (("ts",),),
    "series/oracle/drop": (("drop",),),
}
LANES: dict[str, tuple[P, ...]] = {
    "states/game_state": (("game", "gs"),),
    "states/scene": SCENE,
    "states/focus": (("focus",),),
    "states/hero_input": (("pause", "hero_input"),),
}
ENT_LIST_KEYS = ("list", "items", "ents", "entities")
ENT_COLLIDER_KEYS = ("colliders", "cols", "polys", "shapes", "hitboxes")
POLY_KEYS = ("verts_world", "verts", "points", "pts", "poly", "polygon", "path")
WARN_KINDS = ("DIE", "DEATH", "CATASTROPHE", "LETHAL", "FAIL", "ERROR", "DAMAGE")


# ---- defensive accessors -------------------------------------------------------------------------------

def get_path(d: Any, path: P) -> Any:
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def first(d: Any, paths: Iterable[P]) -> Any:
    for p in paths:
        v = get_path(d, p)
        if v is not None:
            return v
    return None


def number(v: Any) -> float | None:
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None


def point(v: Any) -> tuple[float, float] | None:
    """[x, y, ...] or {"x", "y"} -> (x, y)."""
    if isinstance(v, dict):
        x, y = number(v.get("x")), number(v.get("y"))
    elif isinstance(v, (list, tuple)) and len(v) >= 2:
        x, y = number(v[0]), number(v[1])
    else:
        return None
    return None if x is None or y is None else (x, y)


def polygon(v: Any) -> list[tuple[float, float]] | None:
    """A polygon from: a list of points; a flat [x0, y0, x1, y1, ...] list; a dict with a vertex list under one of
    POLY_KEYS; a box {"min", "max"} / {"aabb": [x0, y0, x1, y1]}; a circle {"center", "radius"}."""
    if isinstance(v, dict):
        for k in POLY_KEYS:
            if k in v:
                return polygon(v[k])
        box = v.get("aabb") or v.get("box") or v.get("bounds")
        if box is not None:
            return polygon(box) if not (isinstance(box, (list, tuple)) and len(box) == 4) else _box(box)
        if "min" in v and "max" in v:
            a, b = point(v["min"]), point(v["max"])
            return None if a is None or b is None else _box((*a, *b))
        c, r = point(v.get("center") or v.get("c")), number(v.get("radius") or v.get("r"))
        if c is not None and r:
            return [(c[0] + r * math.cos(t), c[1] + r * math.sin(t)) for t in np.linspace(0, 2 * np.pi, 17)[:-1]]
        return None
    if not isinstance(v, (list, tuple)) or len(v) < 2:
        return None
    if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        if len(v) >= 4 and len(v) % 2 == 0:
            return [(float(v[i]), float(v[i + 1])) for i in range(0, len(v), 2)]
        return None
    pts = [point(p) for p in v]
    return pts if len(pts) >= 2 and all(p is not None for p in pts) else None


def _box(b) -> list[tuple[float, float]] | None:
    vals = [number(x) for x in b]
    if any(x is None for x in vals):
        return None
    x0, y0, x1, y1 = vals
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def polygons_by_key(obj: Any, prefix: str = "", depth: int = 0) -> dict[str, list]:
    """Every list of polygons inside a TERRAIN-like payload, keyed by its path ("solids", "hazards", "geo/walls")."""
    out: dict[str, list] = {}
    if depth > 3 or not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        name = f"{prefix}{k}"
        if isinstance(v, list):
            polys = [p for p in (polygon(x) for x in v) if p is not None]
            if polys:
                out[name] = polys
        elif isinstance(v, dict):
            out.update(polygons_by_key(v, name + "/", depth + 1))
    return out


def entities(state: dict) -> list[dict]:
    ents = state.get("ents")
    if isinstance(ents, dict):
        for k in ENT_LIST_KEYS:
            if isinstance(ents.get(k), list):
                return [e for e in ents[k] if isinstance(e, dict)]
        return [e for e in ents.values() if isinstance(e, dict)]
    return [e for e in ents if isinstance(e, dict)] if isinstance(ents, list) else []


def colliders(ent: dict) -> Iterator[tuple[list, dict]]:
    for k in ENT_COLLIDER_KEYS:
        cols = ent.get(k)
        if isinstance(cols, list):
            for c in cols:
                poly = polygon(c)
                if poly is not None:
                    yield poly, c if isinstance(c, dict) else {}
            return
    poly = polygon(ent)
    if poly is not None:
        yield poly, ent


def flip(pts: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(x, -y) for x, y in pts]


def closed(pts: list) -> list:
    return pts + pts[:1] if len(pts) > 2 else pts


def color_for(name: str) -> tuple[int, int, int]:
    h = zlib.crc32(name.encode())
    return 80 + h % 150, 80 + (h >> 8) % 150, 80 + (h >> 16) % 150


def _is_damaging(c: dict) -> bool:
    d = c.get("damage") or c.get("dmg")
    if isinstance(d, dict):
        return bool(d.get("dealt", d.get("amount", 1)))
    return bool(d)


# ---- building the Rerun recording ----------------------------------------------------------------------

class Stats(dict):
    def bump(self, k: str, n: int = 1) -> None:
        self[k] = self.get(k, 0) + n


def blueprint() -> rrb.Blueprint:
    return rrb.Blueprint(
        rrb.Horizontal(
            rrb.Spatial2DView(origin="world", name="world (y up)"),
            rrb.Vertical(
                rrb.Tabs(rrb.TimeSeriesView(origin="series/hero", name="hp / silk"),
                         rrb.TimeSeriesView(origin="series/time", name="play time"),
                         rrb.TimeSeriesView(origin="series/oracle", name="oracle")),
                rrb.StateTimelineView(origin="states", name="game & pause blockers"),
                rrb.TextLogView(origin="events", name="events"),
                row_shares=[3, 3, 2],
            ),
            column_shares=[3, 2],
        ),
        collapse_panels=True,
    )


def build(reader: RecordingReader, rec: rr.RecordingStream, *, f0: int | None = None, f1: int | None = None,
          ents_stride: int = 1, extra_series: dict[str, P] | None = None) -> Stats:
    """Log a recording (optionally a frame range) into rec. Returns counts of what was found."""
    stats = Stats()
    series_paths = dict(SERIES)
    for name, path in (extra_series or {}).items():
        series_paths[f"series/extra/{name}"] = (path,)
    series: dict[str, tuple[list, list]] = {k: ([], []) for k in series_paths}
    hero_f, hero_xy = [], []
    trail: list[tuple[float, float]] = []
    trail_start = None
    trail_scene = None
    lanes: dict[str, Any] = {}
    ents_logged = False

    rec.log("states/game_state", rr.StateConfiguration(values=list(GAME_STATES), labels=list(GAME_STATES)),
            static=True)
    for name in BLK_BITS:
        rec.log(f"states/pause/{name}", rr.StateConfiguration(values=["blocked", "clear"], colors=[0xE53935FF, 0],
                                                               visible=[True, False]), static=True)
    rec.log("series/hero/hp", rr.SeriesLines(colors=[[230, 60, 60]], names=["hp"]), static=True)
    rec.log("series/hero/silk", rr.SeriesLines(colors=[[240, 240, 240]], names=["silk"]), static=True)

    # TERRAIN arrives once per scene/variant; keep every message so a revisited scene shows its terrain again.
    terrain_msgs: list[tuple[int, str | None, dict]] = []
    for entry, msg in reader.terrain():
        at = entry.get("f") if entry.get("f") is not None else entry.get("after_f")
        scene_name = msg.get("scene") if isinstance(msg, dict) else None
        terrain_msgs.append((at if at is not None else -1, scene_name if isinstance(scene_name, str) else None,
                             polygons_by_key(msg if isinstance(msg, dict) else {})))

    def log_terrain(at: int, layers: dict[str, list]) -> None:
        rec.set_time("frame", sequence=at)
        rec.log("world/terrain", rr.Clear(recursive=True))
        for key, polys in layers.items():
            rec.log(f"world/terrain/{key}", rr.LineStrips2D([closed(flip(p)) for p in polys],
                                                            colors=[color_for(key)], radii=[0.04]))

    def enter_scene(f: int, names: set) -> None:
        known = [m for m in terrain_msgs if m[1] in names and m[0] < f]
        if known:
            log_terrain(f, known[-1][2])
        elif terrain_msgs:
            rec.set_time("frame", sequence=f)
            rec.log("world/terrain", rr.Clear(recursive=True))

    def flush_trail() -> None:
        # One strip per scene visit, logged at the visit's first frame: world coordinates restart in every
        # scene, so the view shows only the current scene's path (and nothing for a visit without a hero).
        if trail_start is None:
            return
        rec.set_time("frame", sequence=trail_start)
        if len(trail) >= 2:
            rec.log("world/hero/trail", rr.LineStrips2D([flip(trail)], colors=[[255, 200, 40]], radii=[0.05],
                                                        labels=[trail_scene or ""]))
            stats.bump("trail_segments")
        else:
            rec.log("world/hero/trail", rr.Clear(recursive=False))

    def lane(path: str, value: Any, f: int) -> None:
        """Log discrete values only when they change; None (section absent) shows as a gap."""
        if path not in lanes and value is None:
            lanes[path] = None
            return
        if lanes.get(path, ()) == value:
            return
        lanes[path] = value
        rec.set_time("frame", sequence=f)
        rec.log(path, rr.StateChange.cleared() if value is None else rr.StateChange(state=str(value)))

    last_f = None
    for s in reader.states(f0, f1):
        f = s.get("f")
        if not isinstance(f, int):
            continue
        last_f = f
        stats.bump("frames")
        # scalars
        for name, paths in series_paths.items():
            v = number(first(s, paths))
            if v is not None:
                series[name][0].append(f)
                series[name][1].append(v)
        # discrete lanes
        for path, paths in LANES.items():
            v = first(s, paths)
            if path == "states/game_state" and isinstance(v, int) and 0 <= v < len(GAME_STATES):
                v = GAME_STATES[v]
            lane(path, v, f)
        blk = get_path(s, ("pause", "blk"))
        for i, name in enumerate(BLK_BITS):
            lane(f"states/pause/{name}", None if not isinstance(blk, int) else
                 ("blocked" if blk >> i & 1 else "clear"), f)
        # hero
        scene = first(s, SCENE)
        pos = point(first(s, HERO_POS))
        if scene != trail_scene or trail_start is None:
            flush_trail()
            trail, trail_start, trail_scene = [], f, scene
            enter_scene(f, {get_path(s, p) for p in SCENE} - {None})
        if pos is not None:
            hero_f.append(f)
            hero_xy.append((pos[0], -pos[1]))
            trail.append(pos)
        # entities
        ents = entities(s)
        if ents and (f - (f0 or 0)) % ents_stride == 0:
            rec.set_time("frame", sequence=f)
            strips, colors, labels = [], [], []
            centers, center_labels = [], []
            for e in ents:
                label = str(e.get("type_key") or e.get("name") or e.get("type") or e.get("iid") or "")
                c = point(e.get("pos"))
                if c is not None:
                    centers.append((c[0], -c[1]))
                    center_labels.append(label)
                for poly, meta in colliders(e):
                    strips.append(closed(flip(poly)))
                    colors.append((255, 40, 40) if _is_damaging(meta) else color_for(
                        str(e.get("category") or e.get("layer") or label)))
                    labels.append(label)
            rec.log("world/ents/colliders", rr.LineStrips2D(strips, colors=colors, radii=[0.03], labels=labels))
            rec.log("world/ents/pos", rr.Points2D(centers, labels=center_labels, radii=[0.12]))
            ents_logged = True
            stats.bump("ent_frames")
        elif not ents and ents_logged:
            rec.set_time("frame", sequence=f)
            rec.log("world/ents", rr.Clear(recursive=True))
            ents_logged = False
    if last_f is not None:
        flush_trail()

    if hero_f:
        rec.send_columns("world/hero/pos", indexes=[rr.TimeColumn("frame", sequence=hero_f)],
                         columns=rr.Points2D.columns(positions=np.asarray(hero_xy, dtype=np.float32),
                                                     radii=np.full(len(hero_f), 0.25, dtype=np.float32)))
        stats.bump("hero_frames", len(hero_f))
    for name, (fs, vs) in series.items():
        if fs:
            rec.send_columns(name, indexes=[rr.TimeColumn("frame", sequence=fs)],
                             columns=rr.Scalars.columns(scalars=np.asarray(vs, dtype=np.float64)))
            stats.bump("series")

    # Each TERRAIN also replaces the polygons from the frame it arrived after (logged last, so it wins over the
    # scene-entry clear/re-log at the same frame).
    for at, _, layers in terrain_msgs:
        if (f0 is not None and at < f0) or (f1 is not None and at > f1):
            continue
        log_terrain(max(at, 0), layers)
        stats.bump("terrain_msgs")
        if layers:
            stats.bump("terrain_layers", len(layers))

    # Events (already extracted by the recorder into events.jsonl).
    for ev in reader.events():
        fr = ev.get("frame")
        if not isinstance(fr, int) or (f0 is not None and fr < f0) or (f1 is not None and fr > f1):
            continue
        kind = str(ev.get("kind"))
        rec.set_time("frame", sequence=fr)
        level = "WARN" if any(w in kind.upper() for w in WARN_KINDS) else "INFO"
        rec.log("events", rr.TextLog(f"{kind} {ev.get('data')}", level=level))
        stats.bump("events")
    return stats


def parse_series(specs: list[str]) -> dict[str, P]:
    out = {}
    for spec in specs:
        name, _, path = spec.partition("=")
        if not path:
            raise SystemExit(f"--series expects NAME=a.b.c, got {spec!r}")
        out[name] = tuple(path.split("."))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ssbot.tools.viewer", description=__doc__.split("\n")[0])
    ap.add_argument("path", help="episode directory (runs/<date>/<profile>/<episode>)")
    ap.add_argument("--from", dest="f0", type=int)
    ap.add_argument("--to", dest="f1", type=int)
    ap.add_argument("--ents-stride", type=int, default=1, help="log entity polygons every N frames")
    ap.add_argument("--series", action="append", default=[], help="extra series NAME=dotted.path")
    ap.add_argument("--save", help="write an .rrd file instead of spawning the viewer")
    a = ap.parse_args(argv)

    reader = RecordingReader(a.path)
    rec = rr.RecordingStream("ssbot-viewer", recording_id=str(Path(a.path).resolve()))
    if a.save:
        rec.save(a.save, default_blueprint=blueprint())
    else:
        rec.spawn(default_blueprint=blueprint())
    stats = build(reader, rec, f0=a.f0, f1=a.f1, ents_stride=max(1, a.ents_stride),
                  extra_series=parse_series(a.series))
    rec.flush()
    print(f"logged {dict(stats)}" + (f" -> {a.save}" if a.save else ""))
    missing = [k for k in ("hero_frames", "ent_frames", "terrain_msgs", "events") if k not in stats]
    if missing:
        print(f"not in this recording (skipped): {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
