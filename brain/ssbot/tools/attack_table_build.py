"""Build knowledge/<build>/attacks/<crest>.json (ssbot.knowledge.attack_shapes) from the oracle's slash dump and,
when given, live per-frame samples of the swings (probes/attack_frames.py).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.attack_table_build --crest Reaper [--dump <crests.json>]
        [--live <run>/attack_frames.jsonl] [--dry-run]

From the dump (docs/facts/1.0.30000/crests.json, P17 "crests" -> <crest> -> "slash": every attack object of the
crest, damagers with their colliders in world space at the dumped hero pose): each slot's damage polygons relative to
the hero collider centre in the facing frame (shapes_swing, the swing's own scale, where the oracle gave it), the
Clash Tink polygon's box, and the active window from the NailSlash clip (collider on at the first animation event,
off at the second: NailSlash.cs, oracle SlashDump.Clip). Slots the clip does not time (the Reaper down slash, a
Downspike component swung by the Crest Attacks FSM; dash stab; charge; taunt) get the clip length or a placeholder
and are marked "timing": "unmeasured" until live samples exist.

From live samples (one JSON line per sampled frame of a swing: {slot, k (rendered frames since the press reached the
game), enabled: {damager path: bool}, hero: {box, facing}, damagers: [{path, enabled, polys (world)}]}): the frames
each damager was enabled (frames), and the polygons as seen while enabled (the median over samples of each vertex,
relative to the sampled hero box centre), which replace the dump's where they disagree by more than 0.02 u.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.knowledge.attack_shapes import REPO, ROOT, AttackShape, AttackTable

DUMP = REPO / "docs" / "facts" / "1.0.30000" / "crests.json"
DUMP_MAIN = Path(r"C:\modeling\silksong_bot\docs\facts\1.0.30000\crests.json")    # untracked in the main checkout
# hit event src names of the damagers (HitInstance.Source.name = the damager GameObject's name)
RECOIL = {"velocity": 3.75, "steps": 8, "source": "HeroController.Recoil: RECOIL_HOR_VELOCITY x RECOIL_HOR_STEPS "
          "(hero_constants.json); the long recoil (16) only for RecoilLeftLong / RightLong callers"}


def _rel(v: np.ndarray, cx: float, cy: float, face: int) -> np.ndarray:
    return np.c_[(v[:, 0] - cx) * face, v[:, 1] - cy]


def from_dump(dump: dict, crest: str) -> AttackTable:
    sl = dump["crests"][crest]["slash"]
    h = sl["hero"]
    box = h["box"]
    cx, cy = 0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])
    face = 1 if h["facing"] >= 0 else -1
    cfg = next((c for c in dump["table"]["configs"] if c["crest"] == crest), {})
    shapes: dict[str, AttackShape] = {}
    notes = [f"P17 slash.dump frame {sl.get('frame')} (crests.json captured {dump.get('captured')}), hero "
             f"{h['pos'][:2]} facing {face}, config {sl.get('config')}"]
    for a in sl["attacks"]:
        slot = a["slot"]
        clip = next((n.get("clip") for n in a["nail"] if n.get("clip")), None)
        polys, mult, srcs = [], 1.0, []
        for dm in a["damagers"]:
            if "Knockback" in dm["path"]:
                continue                      # Downspike knockback damagers push enemies, they are not the hit
            for col in dm["colliders"]:
                # NailSlash.StartSlash sets the swing's localScale to its "scale" (shapes_swing); a Downspike does
                # not: the Hunter down spike's idle outline (scale 1.2 x 1.33) is the one that matched 240 of 241
                # hits live (planner.DOWN_POLY, probes.md "M2: down-slash whiffs")
                swing = col.get("shapes_swing") if a.get("component") == "NailSlash" else None
                for shp in swing or col["shapes"]:
                    polys.append(_rel(np.asarray(shp["v"], float).reshape(-1, 2), cx, cy, face))
            mult = float(dm.get("nail_damage_mult") or 1.0)
            if dm["path"].split("/")[-1] not in srcs:
                srcs.append(dm["path"].split("/")[-1])
        if not polys:
            continue
        clash = []
        for n in a["nail"]:
            for col in n.get("clash_tink") or []:
                for shp in col["shapes"]:
                    r = _rel(np.asarray(shp["v"], float).reshape(-1, 2), cx, cy, face)
                    clash.append((r[:, 0].min(), r[:, 0].max(), r[:, 1].min(), r[:, 1].max()))
        cb = (min(c[0] for c in clash), max(c[1] for c in clash), min(c[2] for c in clash),
              max(c[3] for c in clash)) if clash else ()
        ev = [e[0] for e in (clip or {}).get("events") or [] if str(e[1]) != "Bounce"]
        fps = float((clip or {}).get("fps") or 0.0)
        if fps > 0 and len(ev) >= 2:
            t_on, t_off, how = ev[0] / fps, ev[1] / fps, f"clip {clip['name']} events {ev[:2]} at {fps:g} fps"
        elif fps > 0:
            t_on, t_off = (ev[0] / fps if ev else 0.0), clip["frames"] / fps
            how = f"clip {clip['name']} ({clip['frames']} frames at {fps:g} fps): timing unmeasured"
        else:
            t_on, t_off, how = 0.0, 0.2, "no clip: timing unmeasured"
        shapes[slot] = AttackShape(slot=slot, src="|".join(srcs) or a["go"], polys=tuple(polys), t_on=float(t_on), t_off=float(t_off),
                                   damage_mult=mult, clash_box=tuple(float(c) for c in cb),
                                   source=f"slash.dump; {how}")
    config = {k: cfg.get(k) for k in ("duration", "cooldown", "recovery", "down", "down_recovery", "dash_stab")}
    config["down_slash_event"] = sl.get("down_slash_event")
    src = CUSTOM_DOWN_SRC.get(sl.get("down_slash_event") or "")
    if src and "down" in shapes:
        d = shapes["down"]
        shapes["down"] = AttackShape(d.slot, src, d.polys, d.t_on, d.t_off, d.frames, d.damage_mult, d.clash_box,
                                     d.source + f"; hit src {src} (the FSM's object; polygon still the group object's "
                                     "until a slash.dump paths sample)")
    return AttackTable(crest, dump.get("game", "1.0.30000"), config, shapes, dict(RECOIL), notes)


# slash.dump "paths" samples (slot "path:<hero-relative path>") that stand for a table slot: the object the FSM
# really swings, whose polygons replace the dump's (the dump's custom down slot is the config group's DownSlash object)
PATH_SLOTS = {"path:Attacks/Scythe/DownSlash New": "down"}
# the hit src of a Custom down slash: the object the Crest Attacks FSM swings (FindChild in its Init state; live
# Bell Beast Reaper run 20261002_225836: 18 hits with src "DownSlash New", none with the group object's "DownSlash")
CUSTOM_DOWN_SRC = {"RPR DOWNSLASH": "DownSlash New"}


def _on(d: dict) -> bool:
    return bool(d.get("enabled")) and d.get("active", True) is not False


def apply_live(tab: AttackTable, lines: list[dict]) -> list[str]:
    """Fold live per-frame samples into the table: frames each slot's damager was enabled, polygons while enabled."""
    by_slot: dict[str, list[dict]] = defaultdict(list)
    for r in lines:
        by_slot[PATH_SLOTS.get(r["slot"], r["slot"])].append(r)
    out = []
    for slot, rows in by_slot.items():
        if slot not in tab:
            continue
        sh = tab[slot]
        replace = any(r["slot"] in PATH_SLOTS for r in rows)
        if replace:
            rows = [r for r in rows if r["slot"] in PATH_SLOTS]
        on = sorted({r["k"] for r in rows if any(_on(d) for d in r.get("damagers") or ())})
        no_active = not any("active" in d for r in rows for d in r.get("damagers") or ())
        if no_active and len(on) >= 20 and len(on) == len({r["k"] for r in rows}):
            # samples from before the probe recorded activeInHierarchy: an object enabled on every sampled frame of
            # every trial is an inactive group object (down / charge / taunt), not a swing
            out.append(f"{slot}: skipped (enabled on every sampled frame, no active flag: an inactive object)")
            continue
        polys = defaultdict(list)
        for r in rows:
            b = r["hero"]["box"]
            cx, cy = 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])
            f = 1 if r["hero"]["facing"] >= 0 else -1
            for d in r.get("damagers") or ():
                if _on(d) and "Knockback" not in d["path"]:
                    for i, p in enumerate(d["polys"]):
                        polys[(d["path"], i)].append(_rel(np.asarray(p, float).reshape(-1, 2), cx, cy, f))
        new = tuple(np.median(np.stack(v), axis=0) for v in polys.values() if len({len(x) for x in v}) == 1)
        moved = 0.0
        if new and len(new) == len(sh.polys) and all(a.shape == b.shape for a, b in zip(new, sh.polys)):
            moved = max(float(np.abs(a - b).max()) for a, b in zip(new, sh.polys))
        frames = (on[0], on[-1]) if on else ()
        if replace and new:
            moved = float("inf")              # another object: its polygons, whatever the dump's were
        tab.shapes[slot] = AttackShape(slot, sh.src, new if (new and moved > 0.02) else sh.polys,
                                       sh.t_on, sh.t_off, frames, sh.damage_mult, sh.clash_box,
                                       sh.source + f"; live frames {frames} ({len(rows)} samples"
                                       + (", polygons of the FSM's own object" if replace and new else
                                          f", polygon moved {moved:.3f} u" if moved > 0.02 else "") + ")")
        out.append(f"{slot}: frames {frames}, " + ("polygons replaced" if replace and new else
                                                   f"polygon shift {moved:.3f} u") + f", {len(rows)} samples")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crest", default="Reaper")
    ap.add_argument("--dump", type=Path, default=None)
    ap.add_argument("--live", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    path = a.dump or (DUMP if DUMP.exists() else DUMP_MAIN)
    tab = from_dump(json.loads(path.read_text(encoding="utf-8")), a.crest)
    if a.live:
        lines = [json.loads(x) for x in a.live.read_text(encoding="utf-8").splitlines() if x.strip()]
        for msg in apply_live(tab, lines):
            print(msg)
        tab.notes.append(f"live samples: {a.live}")
    for k, s in tab.shapes.items():
        b = s.box
        print(f"{k:10s} src {s.src:22s} on {s.t_on:.3f}-{s.t_off:.3f} s frames {s.frames} box x {b[0]:+.2f}..{b[1]:+.2f}"
              f" y {b[2]:+.2f}..{b[3]:+.2f}")
    if not a.dry_run:
        print("wrote", tab.save(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
