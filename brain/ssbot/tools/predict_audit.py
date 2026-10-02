"""Prediction audit of planner runs: the planner's attack predictions and the forecast's next-attack probabilities
checked against what happened (M2: the attack-outcome model must check itself).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.predict_audit C:/ssbot/data/runs/m2/<run> [...] [--worst 15]
        [--json out.json]

Inputs (SSBOT_LOG_ALL=1 decision logs): at each press the chosen plan's attack predictions (PlannerResult.attacks:
kind, start frame from the forecast origin fo, predicted hit, p = share of the 9 timing lanes that hit, hit frame,
predicted boss boxes at it and 0.25 / 0.5 s later, effect on the hero) and its nominal hero path ("path", every 4th
frame from fo); at the first tick of each underground phase the walk's family probabilities ("fam_p"). Actual
signals from the recordings: "hit" events on the boss (frame, src: Slash / AltSlash, UpSlash, DownSpike*, Needle
Damage), the boss's enabled colliders and the hero's box in STATE.

Attack tables, per kind (side, up, down, spear) and per boss phase at the press:
  confusion   predicted hit / miss against a hit event of the kind's source in [start + window, end + 2 frames];
  calibration p in five bins against the hit rate;
  timing      actual hit frame - predicted hit frame (predicted and actual hits);
  residuals   boss box centre (actual - predicted) at the hit frame and 0.25 / 0.5 s later, and the hero's centre
              against the nominal path at the same frames;
  fit         the median timing offset and boss dx fitted on even episodes, the residual left on odd ones (held out).
Threat table: Brier score and reliability of fam_p against the family of the next attack (the first attack state
after the phase: Emerge Antic C / charge phases, Emerge Antic L / leap, Burst Pos / Burst Antic / burst, Rage Pos /
roar).
The worst cases list confident misses (p >= 0.8, no hit) and unpredicted hits by |boss dx|.
"""
import argparse
import bisect
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

KINDS = {1: "side", 2: "up", 3: "down", 4: "spear"}
WINDOW = {1: (0, 6), 2: (2, 8), 3: (0, 16), 4: (17, 20)}
SRC = {1: ("Slash", "AltSlash"), 2: ("UpSlash",), 3: ("Down",), 4: ("Needle Damage",)}
FAMILY_OF_STATE = {"Emerge Antic C": "BB_CHARGE", "Charge Emerge": "BB_CHARGE", "emerge": "BB_CHARGE",
                   "dust_low": "BB_CHARGE", "Emerge Antic L": "BB_LEAP", "Leap Out": "BB_LEAP", "leap": "BB_LEAP",
                   "dust_tall": "BB_LEAP", "Burst Pos": "BB_BURST", "Burst Antic": "BB_BURST", "burst": "BB_BURST",
                   "dust_burst": "BB_BURST", "Rage Pos": "BB_RAGE", "Rage Antic": "BB_RAGE", "roar": "BB_RAGE"}


def _src_ok(kind: int, src) -> bool:
    return src is not None and any(str(src).startswith(x) for x in SRC[kind])


def _centre(b):
    return None if b is None else (0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3]))


def _load(run: Path) -> tuple[list[dict], list[dict]]:
    from ssbot.record.recorder import RecordingReader
    preds, fams = [], []
    for dp in sorted(run.glob("decisions_i*.jsonl")):
        inst = dp.stem.split("_i")[1]
        rows = [json.loads(line) for line in dp.open()]
        need = set()
        local = []
        for n, d in enumerate(rows):
            if d.get("fam_p"):
                nxt = None
                for e in rows[n + 1:n + 600]:
                    if e["ep"] != d["ep"]:
                        break
                    if e.get("boss_state") in FAMILY_OF_STATE:
                        nxt = FAMILY_OF_STATE[e["boss_state"]]
                        break
                if nxt is not None:
                    fams.append({"p": d["fam_p"], "actual": nxt})
            for a in d.get("attacks") or ():
                kind, k, hit, p, jj, bxs, eff = a
                fo = d.get("fo", d["f"])
                pr = {"inst": inst, "ep": d["ep"], "fo": fo, "kind": kind, "start": fo + k, "pred": bool(hit),
                      "p": float(p), "f_hit": fo + jj, "boss_pred": bxs, "eff": eff, "phase": d.get("boss_state"),
                      "path": d.get("path")}
                for off in (0, 15, 30):
                    need.add(fo + jj + off)
                local.append(pr)
        hits = []
        boss_at, hero_at = {}, {}
        for rec in sorted(run.glob(f"rec/*/*/i{inst}_*")):
            ev_p = rec / "events.jsonl"
            if ev_p.exists():
                for line in ev_p.open():
                    if '"hit"' in line:
                        e = json.loads(line)
                        dd = e.get("data") or {}
                        if e.get("kind") == "hit" and dd.get("type_key") == "Bone Beast":
                            hits.append((e["frame"], dd.get("src")))
            if need:
                r = RecordingReader(rec)
                for s in r.states(min(need), max(need) + 1):
                    f = s["f"]
                    if f not in need:
                        continue
                    hb = (s.get("hero") or {}).get("box")
                    if hb:
                        hero_at[f] = (0.5 * (hb[0] + hb[2]), 0.5 * (hb[1] + hb[3]))
                    b = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
                    vs = [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in (b or {}).get("colliders") or ()
                          if c.get("enabled")]
                    if vs:
                        v = np.concatenate(vs)
                        boss_at[f] = (0.5 * (v[:, 0].min() + v[:, 0].max()), 0.5 * (v[:, 1].min() + v[:, 1].max()))
        hits.sort()
        hf = [h[0] for h in hits]
        for pr in local:
            w0, w1 = WINDOW[pr["kind"]]
            s0 = pr["start"]
            i0, i1 = bisect.bisect_left(hf, s0 + w0), bisect.bisect_right(hf, s0 + w1 + 2)
            got = [hits[i][0] for i in range(i0, i1) if _src_ok(pr["kind"], hits[i][1])]
            pr["actual"] = bool(got)
            pr["t_off"] = (got[0] - pr["f_hit"]) if got else None
            for n, off in enumerate((0, 15, 30)):
                bp = _centre(pr["boss_pred"][n]) if pr["boss_pred"] else None
                ba = boss_at.get(pr["f_hit"] + off)
                pr[f"boss_d{off}"] = None if bp is None or ba is None else (ba[0] - bp[0], ba[1] - bp[1])
                path = pr["path"] or []
                idx = (pr["f_hit"] + off - pr["fo"]) // 4
                hp = _centre(path[idx]) if 0 <= idx < len(path) else None
                ha = hero_at.get(pr["f_hit"] + off)
                pr[f"hero_d{off}"] = None if hp is None or ha is None else (ha[0] - hp[0], ha[1] - hp[1])
            pr.pop("path", None)
            preds.append(pr)
    return preds, fams


def _stats(rows: list[dict]) -> dict:
    out = {"n": len(rows)}
    cm = Counter((r["pred"], r["actual"]) for r in rows)
    out["confusion"] = {"pred_hit_hit": cm[(True, True)], "pred_hit_miss": cm[(True, False)],
                        "pred_miss_hit": cm[(False, True)], "pred_miss_miss": cm[(False, False)]}
    bins = defaultdict(list)
    for r in rows:
        bins[min(int(r["p"] * 5), 4)].append(r)
    out["calibration"] = {f"{b / 5:.1f}-{(b + 1) / 5:.1f}": {"n": len(v), "p_mean": round(float(np.mean(
        [x["p"] for x in v])), 2), "hit_rate": round(float(np.mean([x["actual"] for x in v])), 2)}
        for b, v in sorted(bins.items())}
    to = [r["t_off"] for r in rows if r["pred"] and r["t_off"] is not None]
    if to:
        out["timing_frames"] = {"n": len(to), "p5": float(np.percentile(to, 5)), "p50": float(np.median(to)),
                                "p95": float(np.percentile(to, 95))}
    for who in ("boss", "hero"):
        for off in (0, 15, 30):
            d = [r[f"{who}_d{off}"] for r in rows if r.get(f"{who}_d{off}") is not None]
            if d:
                a = np.abs(np.array(d))
                out[f"{who}_resid_{off}f"] = {"n": len(d), "dx_med": round(float(np.median([x[0] for x in d])), 2),
                                              "abs_dx_p50": round(float(np.median(a[:, 0])), 2),
                                              "abs_dx_p95": round(float(np.percentile(a[:, 0], 95)), 2),
                                              "abs_dy_p50": round(float(np.median(a[:, 1])), 2)}
    # systematic offsets: fit on even episodes, check on odd ones
    tr = [r for r in rows if r["ep"] % 2 == 0]
    te = [r for r in rows if r["ep"] % 2 == 1]
    t_tr = [r["t_off"] for r in tr if r["pred"] and r["t_off"] is not None]
    t_te = [r["t_off"] for r in te if r["pred"] and r["t_off"] is not None]
    d_tr = [r["boss_d0"][0] for r in tr if r.get("boss_d0") is not None]
    d_te = [r["boss_d0"][0] for r in te if r.get("boss_d0") is not None]
    if t_tr and t_te:
        c = float(np.median(t_tr))
        out["fit_timing"] = {"offset_frames": c, "held_out_median_before": float(np.median(t_te)),
                             "held_out_median_after": float(np.median(np.array(t_te) - c))}
    if d_tr and d_te:
        c = float(np.median(d_tr))
        out["fit_boss_dx"] = {"offset_u": round(c, 3), "held_out_abs_p50_before": round(float(np.median(np.abs(d_te))), 3),
                              "held_out_abs_p50_after": round(float(np.median(np.abs(np.array(d_te) - c))), 3)}
    return out


def _threat(fams: list[dict]) -> dict:
    if not fams:
        return {}
    keys = sorted({k for f in fams for k in f["p"]} | {f["actual"] for f in fams})
    brier = float(np.mean([sum((f["p"].get(k, 0.0) - (1.0 if f["actual"] == k else 0.0)) ** 2 for k in keys)
                           for f in fams]))
    rel = {}
    for k in keys:
        bins = defaultdict(list)
        for f in fams:
            p = f["p"].get(k, 0.0)
            bins[min(int(p * 5), 4)].append((p, f["actual"] == k))
        rel[k] = {f"{b / 5:.1f}-{(b + 1) / 5:.1f}": {"n": len(v), "p_mean": round(float(np.mean([x[0] for x in v])), 3),
                                                     "freq": round(float(np.mean([x[1] for x in v])), 3)}
                  for b, v in sorted(bins.items())}
    freq = Counter(f["actual"] for f in fams)
    return {"n": len(fams), "brier": round(brier, 4), "actual_freq": {k: round(v / len(fams), 3) for k, v in
                                                                     freq.items()}, "reliability": rel}


def audit(runs: list[Path], worst: int = 15) -> dict:
    preds, fams = [], []
    for run in runs:
        p, f = _load(run)
        preds += p
        fams += f
    out = {"attacks": {}, "by_phase": {}, "threat": _threat(fams)}
    for kind, name in KINDS.items():
        rows = [r for r in preds if r["kind"] == kind]
        if rows:
            out["attacks"][name] = _stats(rows)
            ph = defaultdict(list)
            for r in rows:
                ph[r["phase"]].append(r)
            out["by_phase"][name] = {str(k): {"n": len(v), "pred_hit_rate": round(float(np.mean([x["pred"] for x in v])), 2),
                                              "hit_rate": round(float(np.mean([x["actual"] for x in v])), 2)}
                                     for k, v in ph.items() if len(v) >= 5}
    bad = [r for r in preds if (r["pred"] and r["p"] >= 0.8 and not r["actual"]) or (not r["pred"] and r["actual"])]
    bad.sort(key=lambda r: -abs((r.get("boss_d0") or (0, 0))[0]))
    out["worst"] = [{k: (v if not isinstance(v, tuple) else [round(x, 2) for x in v]) for k, v in r.items()
                     if k in ("inst", "ep", "start", "f_hit", "kind", "phase", "pred", "p", "actual", "t_off", "boss_d0",
                              "hero_d0", "eff")} for r in bad[:worst]]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--worst", type=int, default=15)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    out = audit(a.runs, a.worst)
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
