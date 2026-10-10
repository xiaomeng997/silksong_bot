"""The person's sanity rule (2026-10-09): in the Forum, at ANY moment, a danger region that covers more than half of the
screen is certainly wrong. Per frame, the share of the visible screen (the STATE camera's viewport, the z = 0 plane
the hero stands in) covered by
  yellow      the overlay's inescapable zone (tools.zone_overlay ZoneEngine.yellow: committed + not started),
  support k   the planner's support at look-ahead k (ZoneEngine.support: every layer, hero-centre grid),
with the per-layer shares at k = 0 and the per-enemy yellow shares (to find the cause of a large one).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.zone_share run <session>:win[:<attempts>] | <bot run dir>[:<n eps>] ...
        --out <dir> [--every 3] [--ks 0,12] [--w0] [--png 4]
    ../scripts/uv.cmd run python -m ssbot.tools.zone_share summary <dir> [--json <out>]

Shares are in hero-centre space (as the overlay draws: where the hero CENTRE must not be), warped to the screen with
the camera homography (zone_overlay.homography) at SHARE_PX pixels. A bot run is every episode of its
attempts_i*.jsonl (HARNESS_FAIL rows and rows without a recording skipped); --w0 stops each episode / attempt at the
first frame of wave index >= 1.
"""
import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from ssbot.tools.zone_overlay import LAYERS, RENDER, battle, homography

SHARE_PX = (192, 108)
LIMIT = 0.5


def screen_share(masks: dict, grid, cam: dict, size: tuple[int, int] = SHARE_PX) -> dict:
    """{name: share of the screen covered} for masks [ny, nx] (row 0 = the lowest hero centre)."""
    import cv2
    _, Hg = homography(grid, cam, size)
    out = {}
    for name, m in masks.items():
        if m is None or not m.any():
            out[name] = 0.0
            continue
        img = np.ascontiguousarray(m[::-1]).astype(np.uint8)
        w = cv2.warpPerspective(img, Hg, size, flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT,
                                borderValue=0)
        out[name] = round(float(w.mean()), 4)
    return out


def frame_masks(fr: dict, ks) -> dict:
    """The masks measured for one compute() result."""
    k0 = ks[0]
    y = fr["ycom"].get(k0)
    ns = fr["yns"].get(k0)
    masks = {"yellow": None if y is None else (y | ns), "ycom": y, "yns": ns}
    for k in ks:
        sup = fr["support"].get(k, {})
        u = None
        for m in sup.values():
            u = m.copy() if u is None else (u | m)
        masks[f"s{k}"] = u
    for lay in LAYERS:
        masks[f"L_{lay}"] = fr["support"].get(k0, {}).get(lay)
    for iid, m in (fr.get("ycom_by") or {}).get(k0, {}).items():
        masks[f"Y_{iid}"] = m
    return masks


def _jobs(spec: str, cache: Path | None) -> list[dict]:
    """Human segments (forum_human_score spec) or a bot run's episodes ("<run dir>[:<n eps>]": a run dir holds
    attempts_i*.jsonl; "C:/<run dir>:6" has as many colons as a human "C:/<session>:win")."""
    head = spec.rpartition(":")[0] if spec.count(":") >= 2 else spec
    bot = any(Path(head).glob("attempts_i*.jsonl")) or any(Path(spec).glob("attempts_i*.jsonl"))
    if not bot and len(spec) > 2 and spec[1] == ":" and spec.count(":") >= 2:
        from ssbot.tools.forum_human_score import segments
        return [{"kind": "human", "seg": s} for s in segments(spec, cache)]
    path, _, n = spec.rpartition(":") if spec.count(":") >= 2 else (spec, "", "")
    run = Path(path)
    out = []
    for f in sorted(run.glob("attempts_i*.jsonl")):
        inst = int(f.stem.split("_i")[1])
        for x in f.read_text("utf-8").splitlines():
            r = json.loads(x) if x.strip() else None
            if r is None or r.get("outcome") == "HARNESS_FAIL" or not r.get("recording"):
                continue
            r.pop("acts", None)
            out.append({"kind": "bot", "run": run.name, "inst": inst, "row": r})
    return out[:int(n)] if n else out


def _states(job: dict):
    if job["kind"] == "human":
        from ssbot.tools.forum_human_score import load_segment
        return load_segment(job["seg"])
    from ssbot.record.recorder import RecordingReader
    row = job["row"]
    rd = RecordingReader(row["recording"])
    terrain = None
    for _, m in rd.terrain():
        if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
            terrain = m
    states = list(rd.states(row["f_wake"], row["f_end"]))
    for s in states:
        s["_f_raw"] = s["f"]
    return terrain, states


def job_name(job: dict) -> str:
    if job["kind"] == "human":
        s = job["seg"]
        return f"{Path(s['session']).name}_a{s['attempt']}"
    return f"{job['run']}_i{job['inst']}_ep{job['row']['episode']}"


def run_job(eng, job: dict, ks, every: int, w0: bool) -> list[dict]:
    terrain, states = _states(job)
    crest = (job.get("seg") or {}).get("crest")
    eng.crest = crest if crest in ("Wanderer", "Reaper") else eng.crest
    eng.start(terrain)
    rows = []
    for s in states:
        b = battle(s)
        if w0 and b is not None and b.get("started") and (b.get("wave") or 0) >= 1:
            break
        eng.feed(s)
        if s["f"] % every:
            continue
        cam = s.get("cam")
        if not cam or not cam.get("V"):
            continue
        fr = eng.compute(ks=ks, support=True, yellow=True)
        if not fr["running"]:
            continue
        sh = screen_share(frame_masks(fr, ks), eng.grid, cam)
        hc = fr["hero"]
        rows.append({"f": int(s["_f_raw"]), "gf": int(s["f"]), "wave": (b or {}).get("wave"),
                     "hero": [round(hc[0], 2), round(hc[1], 2)] if hc else None,
                     "sh": {k: v for k, v in sh.items() if v > 0 or not k.startswith(("L_", "Y_"))},
                     "com": fr["info"].get("committed"), "ns": fr["info"].get("not_started"),
                     "names": fr.get("names")})
    return rows


def cmd_run(a) -> int:
    from ssbot.tools.zone_overlay import ZoneEngine
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ks = tuple(int(x) for x in a.ks.split(","))
    eng = ZoneEngine(crest="Wanderer", threads=a.threads)
    cache = Path(a.demo_cache) if a.demo_cache else None
    for spec in a.specs:
        for job in _jobs(spec, cache):
            name = job_name(job)
            p = out / f"{name}.jsonl"
            if p.exists() and not a.force:
                continue
            t0 = time.perf_counter()
            rows = run_job(eng, job, ks, a.every, a.w0)
            p.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
            mx = max((r["sh"].get("yellow", 0) for r in rows), default=0)
            ms = max((r["sh"].get(f"s{ks[0]}", 0) for r in rows), default=0)
            print(f"{name}: {len(rows)} frames, max yellow {mx:.3f}, max support k{ks[0]} {ms:.3f} "
                  f"({time.perf_counter() - t0:.0f} s)", flush=True)
    return 0


def summarize(d: Path, limit: float = LIMIT) -> dict:
    res: dict = {"dir": str(d), "limit": limit, "groups": {}}
    for p in sorted(d.glob("*.jsonl")):
        grp = "human" if p.name[:8].isdigit() and "_Forum_" not in p.name else "bot"
        g = res["groups"].setdefault(grp, {"files": 0, "frames": 0, "over": {}, "q": {}, "worst": {}, "cause": {}})
        g["files"] += 1
        rows = [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]
        g["frames"] += len(rows)
        for r in rows:
            for key, v in r["sh"].items():
                if key.startswith(("L_", "Y_")):
                    continue
                g["q"].setdefault(key, []).append(v)
                if v > limit:
                    g["over"][key] = g["over"].get(key, 0) + 1
                    w = g["worst"].setdefault(key, [])
                    w.append([v, p.stem, r["f"]])
                    if key in ("yellow", "s0"):
                        pre = "Y_" if key == "yellow" else "L_"
                        lays = {k: x for k, x in r["sh"].items() if k.startswith(pre)}
                        if key == "yellow":
                            lays["not_started"] = r["sh"].get("yns", 0.0)
                        top = max(lays, key=lays.get) if lays else None
                        if top is not None and top.startswith("Y_"):
                            fam = next((f"{c[1][-8:]}/{c[2]}" for c in r.get("com") or () if f"Y_{c[0]}" == top),
                                       "?")
                            top = f"Y_{fam}"
                        g["cause"].setdefault(key, {}).setdefault(top, 0)
                        g["cause"][key][top] += 1
    for g in res["groups"].values():
        q = g.pop("q")
        g["share"] = {k: {"p50": round(float(np.percentile(v, 50)), 4), "p95": round(float(np.percentile(v, 95)), 4),
                          "p99": round(float(np.percentile(v, 99)), 4), "max": round(float(max(v)), 4),
                          "over": g["over"].get(k, 0), "over_pct": round(100.0 * g["over"].get(k, 0) / len(v), 3)}
                      for k, v in q.items()}
        g.pop("over")
        g["worst"] = {k: sorted(v, reverse=True)[:12] for k, v in g["worst"].items()}
    return res


def cmd_summary(a) -> int:
    res = {str(d): summarize(Path(d), a.limit) for d in a.dirs}
    for d, r in res.items():
        for grp, g in r["groups"].items():
            print(f"{d} [{grp}] {g['files']} files, {g['frames']} frames")
            for k in ("yellow", "ycom", "yns", *sorted(x for x in g["share"] if x.startswith("s"))):
                v = g["share"].get(k)
                if v:
                    print(f"  {k:7s} p50 {v['p50']:.3f} p95 {v['p95']:.3f} p99 {v['p99']:.3f} max {v['max']:.3f} "
                          f"over {v['over']} ({v['over_pct']:.2f} %)")
            for k, c in g["cause"].items():
                print(f"  cause of {k} > {a.limit}: " + ", ".join(f"{x} {n}" for x, n in
                                                                 sorted(c.items(), key=lambda kv: -kv[1])))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), "utf-8")
    return 0


def cmd_png(a) -> int:
    """PNGs of given frames of a human session (the overlay drawn over the recorded video), e.g. the worst ones."""
    import cv2
    from ssbot.tools.zone_overlay import (View, VideoFrames, ZoneEngine, _video_index, attempt_states, composite,
                                          legend_lines, render)
    session = Path(a.session)
    eng = ZoneEngine(crest="Wanderer", threads=a.threads)
    seg, terrain, states = attempt_states(session, a.attempt, Path(a.demo_cache) if a.demo_cache else None)
    eng.crest = seg.get("crest") or eng.crest
    want = sorted(int(x) for x in a.frames.split(","))
    vidx = _video_index(session)
    vf = VideoFrames(session)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    eng.start(terrain)
    view = View(mode=a.mode, k=a.k)
    n = 0
    for s in states:
        eng.feed(s)
        fr_raw = s["_f_raw"]
        if not want or fr_raw > want[-1] + 1:
            break
        if not any(abs(fr_raw - w) <= 1 for w in want):
            continue
        want = [w for w in want if abs(fr_raw - w) > 1]
        fr = eng.compute(ks=(a.k,), support=view.show("support"))
        vi = vidx.get(fr_raw)
        img = vf.get(vi) if vi is not None else None
        if img is None:
            continue
        sh = screen_share(frame_masks(fr, (a.k,)), eng.grid, s["cam"]) if s.get("cam") else {}
        extra = f"f {fr_raw}  yellow {sh.get('yellow', 0):.0%}  support k{a.k} {sh.get(f's{a.k}', 0):.0%}"
        ov = render(fr, eng.grid, (img.shape[1], img.shape[0]), view,
                    legend=legend_lines(fr, view, eng.config_text(), extra))
        cv2.imwrite(str(out / f"{a.tag}{session.name}_a{a.attempt}_f{fr_raw}_k{a.k}_{a.mode.replace('+', '')}.png"),
                    composite(img, ov))
        n += 1
    vf.close()
    print(json.dumps({"pngs": n, "out": str(out)}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="zone_share")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("specs", nargs="+")
    r.add_argument("--out", required=True)
    r.add_argument("--every", type=int, default=3)
    r.add_argument("--ks", default="0,12")
    r.add_argument("--w0", action="store_true")
    r.add_argument("--threads", type=int, default=4)
    r.add_argument("--demo-cache", default=r"C:\ssbot\data\m2_forum_overlay\demo_cache")
    r.add_argument("--force", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--limit", type=float, default=LIMIT)
    s.add_argument("--json")
    p = sub.add_parser("png")
    p.add_argument("session")
    p.add_argument("--attempt", type=int, default=0)
    p.add_argument("--frames", required=True)
    p.add_argument("--k", type=int, default=0)
    p.add_argument("--mode", default="yellow+red")
    p.add_argument("--out", required=True)
    p.add_argument("--tag", default="")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--demo-cache", default=r"C:\ssbot\data\m2_forum_overlay\demo_cache")
    a = ap.parse_args(argv)
    return {"run": cmd_run, "summary": cmd_summary, "png": cmd_png}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
