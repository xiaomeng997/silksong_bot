"""Precision of the down-slash predictor (ssbot.combat.pogo_model; task 1v1 T1(b), forum.md 46.4): every down slash
of 1x recordings (the bot's runs, pogo_probe) replayed from the state before the press with the recorded inputs; the
contact found on the predicted path against the recorded colliders, the hit-bounce / miss branch against the real
path. No margins.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.pogo_check --rows C:/ssbot/data/m2_pogo/bot_all.jsonl \
        --recs <recording or run dir> ... [--split test|calib|all] [--ev-off 0] --out <json>

Per case (the real outcome: hurtbox:<type> / tink:<type> = a bounce, pass:<collider> = met a collider that does not
bounce, miss = nothing): contact recall / precision (predicted vs real bounce), the timing error (predicted - real
contact frame), and the position error |predicted - real hero.pos| at 6 / 12 / 18 / 24 / 36 frames after the press for
the branch the predictor picks ("pick": hit branch with a predicted contact, else miss) and for the hit branch timed
by the real contact ("timed"); a comparison stops at the first health loss. split: recordings by a hash of their path,
calib = even, test = odd (the calibration of EV_OFF used calib only).
"""
from __future__ import annotations

import argparse
import json
import sys
import zlib
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

DELTAS = (6, 12, 18, 24, 36)
T = 40


def split_of(name: str) -> str:
    return "calib" if zlib.crc32(name.encode()) % 2 == 0 else "test"


def case_of(r: dict) -> str:
    if r.get("up_f"):
        if r["hits"]:
            return f"hurtbox:{r['hits'][0]['type']}"
        t = [c for c in r["contacts"] if c["layer"] == 22 and c["parry"] is not None and int(c["parry"]) & 1]
        return f"tink:{t[0]['type']}" if t else "bounce:other"
    if r["hits"]:
        return f"hit_nobounce:{r['hits'][0]['type']}"
    p = [c for c in r["contacts"] if c["layer"] == 22]
    if p:
        return "pass:" + p[0]["name"].split(" (")[0].replace(" Ally", "")
    return "miss"


def targets_of(s: dict):
    from ssbot.combat.pogo_model import collider_kind
    out = []
    for e in s.get("ents") or ():
        if e.get("is_dead") or e.get("hidden"):
            continue
        hm = bool((e.get("src") or 0) & 1)
        for c in e.get("colliders") or ():
            if not c.get("enabled") or not c.get("verts_world"):
                continue
            d = c.get("damage") or {}
            k = collider_kind(c.get("layer"), d.get("parry") if d else None, hm)
            if k is None:
                continue
            v = np.asarray(c["verts_world"], float).reshape(-1, 2)
            if c.get("kind") not in ("box", "polygon") and len(v) > 8:
                v = v[:: max(len(v) // 8, 1)]
            out.append((v, k))
    return out


def run(recs: list[Path], rows_by: dict, ev_offs: tuple, split: str) -> dict:
    from ssbot.combat.pogo_model import PogoModel
    from ssbot.knowledge import kinematics as kin
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.pogo_outcomes import rec_name
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    res = {o: [] for o in ev_offs}
    for rec in recs:
        name = rec_name(rec)
        if split != "all" and split_of(name) != split:
            continue
        rows = {r["f0"]: r for r in rows_by.get(name, [])}
        if not rows:
            continue
        rd = RecordingReader(rec)
        terrain = None
        for _, m in rd.terrain():
            terrain = kin.Terrain2D.from_message(m, params.scene("Hang_04"))
            break
        pms = {o: PogoModel(params, terrain, ev_off=o) for o in ev_offs}
        trk = kin.StateTracker(params, terrain or kin.Terrain2D.empty())
        buf: deque = deque(maxlen=T + 8)
        starts = {}
        for s in rd.states(0, 10 ** 9):
            trk.push(s)
            buf.append(s)
            f = s["f"]
            if f + 1 in rows:
                try:
                    starts[f + 1] = trk.state().copy()
                except Exception:  # noqa: BLE001
                    pass
            f0 = f - T + 1
            if f0 in rows and f0 in starts:
                S = [x for x in buf if f0 - 1 <= x["f"] <= f0 - 1 + T]
                if len(S) != T + 1 or S[0]["f"] != f0 - 1:
                    continue
                st = starts.pop(f0)
                for o, pm in pms.items():
                    res[o].append(one(pm, st, S, rows[f0], name))
    return res


def one(pm, start, S: list[dict], r: dict, name: str) -> dict:
    f0 = r["f0"]
    masks = np.array([int((x.get("input") or {}).get("mask", 0) or 0) for x in S[1:]], np.int64)
    facing = 1 if float((S[0].get("hero") or {}).get("facing") or 1) >= 0 else -1
    tg = {j: targets_of(S[j]) for j in range(len(S))}
    br = pm.branches(start, masks, 1, lambda j: tg.get(j, ()), facing)
    real = np.array([(x.get("hero") or {}).get("pos", [np.nan, np.nan])[:2] for x in S], float)
    hp = [(x.get("hero") or {}).get("health") for x in S]
    lost = next((j for j in range(1, len(S)) if hp[j] is not None and hp[0] is not None and hp[j] < hp[0]), len(S))
    act_c = (r["contact_f"][0] - (f0 - 1)) if r.get("up_f") else -1
    geo_j, _ = pm.contact(real, facing, 1, lambda j: tg.get(j, ()))     # the contact rule on the real path
    pick = br.hit if br.hit is not None else br.miss
    timed = pm.rollout(start, masks, act_c) if act_c >= 0 else None
    err, err_t = {}, {}
    for d in DELTAS:
        j = d + 1
        if j >= len(S) or j >= lost:
            continue
        err[d] = float(np.hypot(*(pick.pos[0, j] - real[j])))
        if timed is not None:
            err_t[d] = float(np.hypot(*(timed.pos[0, j] - real[j])))
    return {"rec": name, "f0": f0, "case": case_of(r), "pred_j": br.contact_j, "pred_kind": br.kind, "act_j": act_c,
            "geo_j": geo_j,
            "err": err, "err_timed": err_t, "lost_j": lost if lost < len(S) else None}


def summary(res: list[dict]) -> dict:
    by = defaultdict(list)
    for x in res:
        c = x["case"]
        key = c if c.startswith(("hurtbox", "tink", "pass")) else c.split(":")[0]
        by[key].append(x)
        by["ALL"].append(x)

    def q(v, p):
        return round(float(np.percentile(v, p)), 3) if v else None
    out = {}
    for k, xs in sorted(by.items(), key=lambda z: -len(z[1])):
        bounce = [x for x in xs if x["act_j"] >= 0]
        pred = [x for x in xs if x["pred_j"] >= 0]
        both = [x for x in xs if x["act_j"] >= 0 and x["pred_j"] >= 0]
        dt = [x["pred_j"] - x["act_j"] for x in both]
        geo = [x for x in xs if x.get("geo_j", -1) >= 0]
        gb = [x for x in xs if x["act_j"] >= 0 and x.get("geo_j", -1) >= 0]
        gdt = [x["geo_j"] - x["act_j"] for x in gb]
        o = {"n": len(xs), "bounce": len(bounce), "pred_contact": len(pred),
             "geo_recall": round(len(gb) / len(bounce), 3) if bounce else None,
             "geo_precision": round(len(gb) / len(geo), 3) if geo else None,
             "geo_timing": dict(sorted({str(v): gdt.count(v) for v in set(gdt)}.items(), key=lambda z: int(z[0]))),
             "recall": round(len(both) / len(bounce), 3) if bounce else None,
             "precision": round(len(both) / len(pred), 3) if pred else None,
             "timing_err_frames": dict(sorted({str(v): dt.count(v) for v in set(dt)}.items(), key=lambda z: int(z[0]))),
             "timing_exact": round(sum(v == 0 for v in dt) / len(dt), 3) if dt else None}
        for nm, fld in (("pick", "err"), ("timed", "err_timed")):
            for d in DELTAS:
                v = [x[fld][d] for x in xs if d in x[fld]]
                if v:
                    o[f"{nm}_{d}"] = {"n": len(v), "p50": q(v, 50), "p90": q(v, 90), "p99": q(v, 99),
                                      "max": round(max(v), 3)}
        out[k] = o
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=Path, nargs="+", required=True)
    ap.add_argument("--recs", type=Path, nargs="+", required=True)
    ap.add_argument("--split", default="all", choices=("all", "calib", "test"))
    ap.add_argument("--ev-off", default=None, help="EV_POGO offsets to compare, e.g. -1,0,1 (default pogo_model.EV_OFF)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    from ssbot.combat import pogo_model
    from ssbot.tools.pogo_outcomes import recordings
    rows_by = defaultdict(list)
    for p in a.rows:
        for line in p.read_text("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows_by[r["session"]].append(r)
    offs = (pogo_model.EV_OFF,) if a.ev_off is None else tuple(int(x) for x in str(a.ev_off).split(","))
    res = run(recordings(a.recs), rows_by, offs, a.split)
    out = {"split": a.split, "by_ev_off": {str(o): {"n": len(r), "cases": summary(r)} for o, r in res.items()}}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1), "utf-8")
    a.out.with_suffix(".rows.jsonl").write_text("".join(json.dumps(dict(x, ev_off=o)) + "\n" for o, r in res.items() for x in r), "utf-8")
    print(json.dumps(out, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
