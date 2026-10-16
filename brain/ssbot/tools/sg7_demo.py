"""Task 1v1 SG7 (4): the person's 2026-10-15 slam demo against a stored map (forum.md 63).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sg7_demo --tag sg7 --out C:/ssbot/data/m2_map/sg7/demo_sg7.json

Reads the demo analysis (C:/ssbot/data/m2_map/human_1015/analysis.json: per slam the stage lengths, the physics phase,
the anchor; per down press the node before it (frame, x, the person's key, the actual vertical event: a jump hold or
a bounce)). Per press: the map's verdict at that node with what the hero had seen by then (SG7 stage maps: the stage
entries up to the node frame, rounded up to the map's 60 Hz clock; the demo ran at 120 fps): certified = the node
takes the slash with the person's key in every source (the slam's phase, every row map consistent with the
observation); also with any key, the node's value, the nearest certified cell on the same slice (dx) and press frame
(dk on the person's own path). A wall near the anchor: the wall bucket the planner would use (none: "wall").
Landed strikes: recall; presses that missed or were followed by a hammer hit: must not be certified.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

DEMO = Path("C:/ssbot/data/m2_map/human_1015/analysis.json")
STAGE_KEYS = ("Slam 0", "Slam 1", "Slam 2", "Slam Recover")


def entries(stage_len: dict) -> dict:
    """{stage: entry time (60 Hz frames since the antic entry)} from the recorded stage lengths."""
    out, t = {}, 0.0
    for st in ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2", "Slam Recover"):
        if st not in stage_len:
            break
        if st != "Slam Antic" and st != "Slam Effects?":
            out[st] = t
        t += float(stage_len[st] or 0.0)
    return out


def seen_at(ent: dict, kn: int) -> dict:
    """The entries the hero has seen by the end of frame kn (an entry at time t is visible from frame ceil(t))."""
    return {st: int(math.ceil(t - 1e-6)) for st, t in ent.items() if int(math.ceil(t - 1e-6)) <= kn}


class Ctx:
    def __init__(self, tag: str):
        from ssbot.combat import special_map_rt as smrt
        from ssbot.combat.forum_map import FORUM_ARENA
        from ssbot.tools.pogo_theory import load_kin
        params, terrain = load_kin()
        self.smrt, self.arena = smrt, FORUM_ARENA
        self.params, self.terrain = params, terrain
        self.tag = tag
        self.rts: dict = {}
        self.rt = self.get(tag)

    def get(self, tag: str):
        if tag not in self.rts:
            p = self.smrt.map_path(tag)
            self.rts[tag] = self.smrt.MapRuntime(self.params, self.terrain, p) if p.exists() else None
        return self.rts[tag]

    def rt_for(self, x0: float, face: int):
        rt = self.rt
        if not getattr(rt, "stage", None):
            return rt, ("wall" if rt.wall_exit(x0, face, self.arena) else "")
        b = rt.wall_bucket(x0, face, self.arena)
        if b is None:
            return None, "wall"
        if b == "":
            return rt, ""
        brt = self.get(self.tag + b)
        return (brt, b) if brt is not None else (None, "wall (bucket file missing)")

    @staticmethod
    def certified(rt, srcs, k, s, x, d) -> bool:
        for src in srcs:
            xi = src._xi(k, s, x)
            if xi < 0 or not src.pbit(int(src.rm[k]), d, s, xi):
                return False
        return True


def slice_of(rt, ma: dict, kn: int) -> int | None:
    """The actual event's slice at frame kn (analysis map_actual: a jump of hold param started at k0_slice, or a
    bounce at contact height param from k0_slice)."""
    ti = rt.ti
    j = kn - int(ma["k0_slice"])
    if ma["kind"] == "jump":
        h = float(ma["param"])
        if h not in ti._jt:
            return None
        return ti.slice_of({"kind": "jump", "h": h, "k": int(ma["k0_slice"])}, j)
    if ma["kind"] == "bounce":
        return ti.slice_of({"kind": "bounce", "yc": float(ma["param"]), "k": int(ma["k0_slice"])}, j)
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="sg7")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    ctx = Ctx(a.tag)
    D = json.loads(DEMO.read_text("utf-8"))
    rows = []
    for si, sl in enumerate(D["slams"]):
        ent = entries(sl.get("stage_len") or {})
        face = int(sl["face"])
        x0 = float(sl["x0"])
        p = int(sl["phase"])
        rt, bucket = ctx.rt_for(x0, face)
        hp = [h for h in sl.get("hp_lost") or []]
        for pr in sl.get("presses") or []:
            if pr.get("kind") != "down" or not pr.get("map"):
                continue
            kn = int(pr["map"]["node_k"])
            landed = pr.get("contact_k") is not None
            hit_after = [h for h in hp if pr["k"] <= h["k"] <= pr["k"] + 25]
            r = {"slam": si, "session": sl["session"], "attempt": sl["attempt"], "t": sl["t"], "k": pr["k"],
                 "stage": pr["stage"], "stage_k": pr["stage_k"], "x": pr["x"], "landed": landed,
                 "contact_k": pr.get("contact_k"), "hit_after": [h["source"] for h in hit_after],
                 "bucket": bucket, "sg4_cert": bool(pr["map"].get("strike_key")),
                 "sg4_cert_actual": bool((pr.get("map_actual") or {}).get("strike_key"))}
            rows.append(r)
            if rt is None:
                r["why"] = "wall"
                continue
            seen = seen_at(ent, kn)
            ok = rt.observe(seen, kn) if getattr(rt, "stage", None) else []
            r["seen"] = seen
            r["n_variants"] = len(ok)
            ma = pr.get("map_actual")
            c = int(pr["map"]["c"])
            nd_x = float(pr["x"]) if pr.get("x") is not None else None
            if ma is None or nd_x is None:
                r["why"] = "no actual slice (ground / off the macros)"
                continue
            s = slice_of(rt, ma, kn)
            if s is None or s < 0:
                r["why"] = "the person's event is not a map tube"
                continue
            srcs = rt._srcs([p])
            r["cert"] = Ctx.certified(rt, srcs, kn, s, nd_x, c)
            r["cert_any_key"] = any(Ctx.certified(rt, srcs, kn, s, nd_x, d) for d in (-1, 0, 1))
            srcs6 = rt._srcs(list(rt.srcs))
            r["cert_all_phases"] = Ctx.certified(rt, srcs6, kn, s, nd_x, c)
            v = min(src.S(kn, s, nd_x, c) for src in srcs)
            r["value"] = round(float(v), 3) if np.isfinite(v) else "-inf"
            near = None
            for dx in np.arange(-1.5, 1.5001, rt.ti.step):
                if Ctx.certified(rt, srcs, kn, s, nd_x + dx, c) and (near is None or abs(dx) < abs(near)):
                    near = round(float(dx), 3)
            r["nearest_dx"] = near
            # the same slice one / two frames earlier or later (the press time on the person's own path)
            dks = []
            for dk in (-3, -2, -1, 1, 2, 3):
                s2 = slice_of(rt, ma, kn + dk)
                if s2 is None or s2 < 0:
                    continue
                if Ctx.certified(rt, srcs, kn + dk, s2, nd_x, c):
                    dks.append(dk)
            r["cert_dk_same_x"] = dks
            r["h_err"] = ma.get("h_err")
            rt.observe(None)
    land = [r for r in rows if r["landed"]]
    bad = [r for r in rows if not r["landed"] or r["hit_after"]]
    summ = {"tag": a.tag, "presses": len(rows), "landed": len(land),
            "landed_cert": sum(1 for r in land if r.get("cert")),
            "landed_cert_any_key": sum(1 for r in land if r.get("cert_any_key")),
            "landed_cert_all_phases": sum(1 for r in land if r.get("cert_all_phases")),
            "landed_sg4_cert": sum(1 for r in land if r["sg4_cert_actual"]),
            "landed_wall_no_bucket": sum(1 for r in land if r.get("why") == "wall"),
            "landed_bucket": sum(1 for r in land if r["bucket"] not in ("", "wall", None)),
            "bad_presses": len(bad), "bad_cert": sum(1 for r in bad if r.get("cert")),
            "landed_value_finite": sum(1 for r in land if isinstance(r.get("value"), float)),
            "landed_near_dx_le_0.33": sum(1 for r in land if r.get("nearest_dx") is not None and abs(r["nearest_dx"]) <= 0.33)}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"summary": summ, "rows": rows}, indent=1, default=str), "utf-8")
    print(json.dumps(summ))
    for r in rows:
        print(r["slam"], r["k"], r["stage"], r["stage_k"], r["x"], "landed" if r["landed"] else "MISS", r["hit_after"],
              r["bucket"], "cert", r.get("cert"), "any", r.get("cert_any_key"), "v", r.get("value"), "dx",
              r.get("nearest_dx"), "dk", r.get("cert_dk_same_x"), r.get("why", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
