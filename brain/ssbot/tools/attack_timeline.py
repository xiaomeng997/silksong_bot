"""Attack timeline viewer (M2 W2): PNG pictures of a boss's Control FSM per fight with the hits taken, and of the
space-time hitbox templates per attack family.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.attack_timeline timeline C:/ssbot/data/runs/m2/<run>
        [--human C:/ssbot/data/human/20260930_210337:64000:68460] [--max-fights 12] [--out timeline.png]
    ../scripts/uv.cmd run python -m ssbot.tools.attack_timeline snapshots [knowledge/.../BellBeast_hitboxes.npz]
        [--family BB_CHARGE --family BB_LEAP] [--every 0.25] [--out snapshots.png]

timeline: one row per fight, time in seconds from its first frame (frames / 60). Each attack instance (attack start
state until the return to a decision state, ssbot.knowledge.behaviour_tables) is a bar in its family's colour with
a tick at every state entry; decision states are grey; a hit taken is a red tick above the row (dark red when the
source is not the boss itself); the kill is a black bar. Reads a recording's events.jsonl (no STATE decoding).

snapshots: per family and frame ("anchor": the boss's frame, faced +x; "world": arena-fixed hazards), panels of the
union occupancy within consecutive windows of --every s after the attack start over the reach union (light grey),
with the boss's mean anchor-frame position in the window (cross) and a 5 u grid.
"""
import argparse
import sys
import zlib
from pathlib import Path

import cv2
import numpy as np

from ssbot.knowledge import hitbox_tables as hb
from ssbot.knowledge.behaviour_tables import SPECS, BehaviourSpec, fight_events, human_fight, run_fights

FAMILY_BGR = {"BB_CHARGE": (40, 140, 245), "BB_LEAP": (220, 130, 40), "BB_BURST": (70, 170, 60),
              "BB_RAGE": (170, 60, 160)}
GREY = (200, 200, 200)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def family_color(fam: str | None) -> tuple[int, int, int]:
    if fam is None:
        return GREY
    if fam in FAMILY_BGR:
        return FAMILY_BGR[fam]
    h = zlib.crc32(fam.encode())
    return 60 + h % 160, 60 + (h >> 8) % 160, 60 + (h >> 16) % 160


def control_segments(events: list[tuple[int, str, dict]], spec: BehaviourSpec) -> list[tuple[int, str, str | None]]:
    """[(frame, Control state, family of the attack it belongs to or None)] from a fight's fsm events."""
    out, fam = [], None
    for f, k, d in events:
        if k != "fsm" or d.get("fsm") != spec.control_fsm or not str(d.get("obj", "")).startswith(spec.boss_type):
            continue
        to = d.get("to")
        if to in spec.attack_starts:
            fam = spec.attack_starts[to]
        elif to in spec.decision_states or to in spec.death_states or to in spec.dormant:
            fam = None
        out.append((f, to, fam))
    return out


def draw_timeline(rows: list[dict], spec: BehaviourSpec, px_per_s: float = 6.0) -> np.ndarray:
    """rows: [{"id", "f0", "f1", "segments", "hits": [(f, source)]}] -> BGR image."""
    left, top, row_h, bar_h = 260, 46, 26, 12
    span = max((r["f1"] - r["f0"]) / 60.0 for r in rows)
    w = int(left + span * px_per_s + 30)
    h = top + row_h * len(rows) + 30
    img = np.full((h, w, 3), 255, np.uint8)
    x_of = lambda f, f0: int(left + (f - f0) / 60.0 * px_per_s)  # noqa: E731
    for s in range(0, int(span) + 1, 10):
        x = int(left + s * px_per_s)
        cv2.line(img, (x, top - 6), (x, h - 24), (235, 235, 235), 1)
        if s % 30 == 0:
            cv2.putText(img, f"{s}s", (x - 8, h - 8), FONT, 0.38, (90, 90, 90), 1, cv2.LINE_AA)
    x = 10
    for fam in list(dict.fromkeys(spec.attack_starts.values())):
        cv2.rectangle(img, (x, 12), (x + 14, 24), family_color(fam), -1)
        cv2.putText(img, fam, (x + 18, 23), FONT, 0.42, (40, 40, 40), 1, cv2.LINE_AA)
        x += 30 + 9 * len(fam)
    for label, col in (("hit by the boss", (0, 0, 230)), ("hit by another source", (0, 0, 120)),
                       ("kill", (0, 0, 0))):
        cv2.rectangle(img, (x + 10, 10), (x + 13, 26), col, -1)
        cv2.putText(img, label, (x + 18, 23), FONT, 0.42, (40, 40, 40), 1, cv2.LINE_AA)
        x += 30 + 8 * len(label)
    for i, r in enumerate(rows):
        y = top + i * row_h
        cv2.putText(img, r["id"][-38:], (6, y + bar_h), FONT, 0.36, (30, 30, 30), 1, cv2.LINE_AA)
        segs = r["segments"]
        for j, (f, st, fam) in enumerate(segs):
            f_next = segs[j + 1][0] if j + 1 < len(segs) else r["f1"]
            x0, x1 = x_of(f, r["f0"]), max(x_of(f_next, r["f0"]), x_of(f, r["f0"]) + 1)
            if st in spec.death_states:
                cv2.rectangle(img, (x0, y), (x0 + 3, y + bar_h + 6), (0, 0, 0), -1)
                continue
            col = family_color(fam) if fam else ((120, 120, 120) if st in spec.dormant else GREY)
            cv2.rectangle(img, (x0, y + 3), (x1, y + bar_h + 3), col, -1)
            if fam:
                cv2.line(img, (x0, y + 3), (x0, y + bar_h + 3), (255, 255, 255), 1)
        for f, src in r["hits"]:
            xh = x_of(f, r["f0"])
            boss = src.endswith("/" + spec.boss_type) or src.startswith(spec.boss_type + "/")
            cv2.line(img, (xh, y - 2), (xh, y + 3), (0, 0, 230) if boss else (0, 0, 120), 2)
    return img


def timeline(a: argparse.Namespace) -> int:
    spec = SPECS[a.encounter]
    fights = []
    for run in a.runs:
        fights += run_fights(run)[0]
    fights += [human_fight(Path(p), int(f0), int(f1)) for p, f0, f1 in (h.rsplit(":", 2) for h in a.human)]
    fights = fights[:a.max_fights]
    if not fights:
        print("no fights", file=sys.stderr)
        return 1
    rows = []
    for fight in fights:
        evs = list(fight_events(fight))
        rows.append({"id": fight.id, "f0": fight.f0, "f1": fight.f1, "segments": control_segments(evs, spec),
                     "hits": [(f, str(d.get("source"))) for f, k, d in evs if k == "damage"]})
    img = draw_timeline(rows, spec, a.px_per_s)
    cv2.imwrite(str(a.out), img)
    print(f"wrote {a.out} ({img.shape[1]}x{img.shape[0]}, {len(rows)} fights)")
    return 0


def panel(tpl: hb.SpaceTimeTemplate, t0: float, t1: float, scale: float, color, path: np.ndarray | None,
          label: str) -> np.ndarray:
    """One snapshot: reach (light grey), occupancy in [t0, t1) (colour), 5 u grid, boss mean position (cross)."""
    reach = tpl.reach()
    occ = tpl.occupancy(t0, max(t0, t1 - tpl.bin_s / 2), tol_bins=0)
    h, w = int(np.ceil(tpl.ny * scale)), int(np.ceil(tpl.nx * scale))
    img = np.full((tpl.ny, tpl.nx, 3), 255, np.uint8)
    img[reach] = (225, 225, 225)
    img[occ] = color
    img = cv2.resize(img[::-1], (max(w, 1), max(h, 1)), interpolation=cv2.INTER_AREA)
    x0, y0, x1, y1 = tpl.bounds
    to_px = lambda x, y: (int((x - x0) / (x1 - x0) * w), int((y1 - y) / (y1 - y0) * h))  # noqa: E731
    for gx in np.arange(np.ceil(x0 / 5) * 5, x1, 5.0):
        cv2.line(img, to_px(gx, y0), to_px(gx, y1), (150, 150, 150) if gx == 0 else (240, 240, 240), 1)
    for gy in np.arange(np.ceil(y0 / 5) * 5, y1, 5.0):
        cv2.line(img, to_px(x0, gy), to_px(x1, gy), (150, 150, 150) if gy == 0 else (240, 240, 240), 1)
    if path is not None and len(path):
        sel = path[(path[:, 0] >= t0) & (path[:, 0] < t1)]
        if len(sel):
            cx, cy = to_px(float(sel[:, 6].mean()), float(sel[:, 7].mean()))
            cv2.drawMarker(img, (cx, cy), (0, 0, 0), cv2.MARKER_CROSS, 9, 1)
    out = np.full((h + 16, w + 4, 3), 255, np.uint8)
    out[16:16 + h, 2:2 + w] = img
    cv2.rectangle(out, (1, 15), (w + 2, h + 16 - 1), (160, 160, 160), 1)
    cv2.putText(out, label, (3, 11), FONT, 0.36, (30, 30, 30), 1, cv2.LINE_AA)
    return out


def snapshots(a: argparse.Namespace) -> int:
    tpls, extra = hb.load_templates(a.npz)
    fams = a.family or sorted({k.split("/")[0] for k in tpls})
    blocks = []
    for fam in fams:
        for frame in hb.FRAMES:
            tpl = tpls.get(f"{fam}/{frame}")
            if tpl is None:
                continue
            act = tpl.active()
            every = a.every
            while act and (act[1] + every) / every > a.max_panels:
                every *= 2
            starts = np.arange(0.0, (act[1] if act else 0.0) + 1e-9, every)
            starts = [t for t in starts if tpl.occupancy(t, t + every - tpl.bin_s / 2, tol_bins=0).any()]
            scale = min(a.panel_px / tpl.nx, a.panel_px / tpl.ny)
            path = extra.get(f"{fam}/boss_path") if frame == "anchor" else None
            panels = [panel(tpl, t, t + every, scale, family_color(fam), path, f"{t:.2f}-{t + every:.2f}s")
                      for t in starts]
            if not panels:
                continue
            ph = max(p.shape[0] for p in panels)
            row = np.full((ph + 22, sum(p.shape[1] + 4 for p in panels) + 4, 3), 255, np.uint8)
            x0, y0, x1, y1 = tpl.bounds
            cv2.putText(row, f"{fam} / {frame}  (n={tpl.n_instances}, x {x0:.1f}..{x1:.1f}, y {y0:.1f}..{y1:.1f} u,"
                             f" cell {tpl.cell} u)", (4, 14), FONT, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
            x = 4
            for p in panels:
                row[22:22 + p.shape[0], x:x + p.shape[1]] = p
                x += p.shape[1] + 4
            blocks.append(row)
    if not blocks:
        print("no templates", file=sys.stderr)
        return 1
    w = max(b.shape[1] for b in blocks)
    img = np.full((sum(b.shape[0] + 8 for b in blocks), w, 3), 255, np.uint8)
    y = 0
    for b in blocks:
        img[y:y + b.shape[0], :b.shape[1]] = b
        y += b.shape[0] + 8
    cv2.imwrite(str(a.out), img)
    print(f"wrote {a.out} ({img.shape[1]}x{img.shape[0]}, {len(blocks)} template rows)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("timeline")
    t.add_argument("runs", nargs="*", type=Path)
    t.add_argument("--human", action="append", default=[], help="SESSION:F0:F1")
    t.add_argument("--encounter", default="BellBeast", choices=sorted(SPECS))
    t.add_argument("--max-fights", type=int, default=12)
    t.add_argument("--px-per-s", type=float, default=6.0)
    t.add_argument("--out", type=Path, default=Path("timeline.png"))
    s = sub.add_parser("snapshots")
    s.add_argument("npz", nargs="?", type=Path, default=None)
    s.add_argument("--family", action="append", default=[])
    s.add_argument("--every", type=float, default=0.25)
    s.add_argument("--max-panels", type=int, default=16)
    s.add_argument("--panel-px", type=int, default=260)
    s.add_argument("--out", type=Path, default=Path("snapshots.png"))
    a = ap.parse_args(argv)
    if a.cmd == "timeline":
        return timeline(a)
    if a.npz is None:
        from ssbot.tools.behaviour_build import default_out
        a.npz = default_out() / "BellBeast_hitboxes.npz"
    return snapshots(a)


if __name__ == "__main__":
    sys.exit(main())
