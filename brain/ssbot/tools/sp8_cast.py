"""The jump cast's antic in the 1v1 runs (task 1v1 SP8a, forum.md 72): per jump cast (CC_JUMP_CAST, the big rune) the
hits on it before the Jump Aim by source, the SP8 scripts' records (SSBOT_FORUM_JB_DASH_COMBO: the DashStab, the
RecoilStab's start and hit on the game clock; SSBOT_FORUM_JB_DASH_STOP: the release, where she stopped, the presses,
a skid or a DashStab out of the stop), her place at the aim, HP lost from the antic start to the landing + 30 frames
and to the rune's last lit frame + 10, and behind the landing or not; the jump slams for comparison. Distances are
centre to centre (the hero's box centre, the Clapper's transform), + = in front.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp8_cast collect --manifest C:/ssbot/sandbox/1v1sp8t1_manifest.txt \
        [--arms sp8dcT] --out C:/ssbot/data/m2_play/sp8/t1/cast.json
    ../scripts/uv.cmd run python -m ssbot.tools.sp8_cast report --in C:/ssbot/data/m2_play/sp8/t1/cast.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ssbot.tools.sp3_jumps import _hp_events, _rows, jumps_of, pct

LAND_SAFE_F = 30                   # HP lost from the antic start to the landing + this (the trial criterion)


def collect(manifests: list[str], arms: set | None, out: Path) -> None:
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.forum_demo import HERO_ATTACKS
    from ssbot.tools.slam_play_live import manifest
    jumps, eps = [], []
    for arm, inst, run in manifest(manifests, arms):
        for row in _rows(run, inst):
            if not row.get("recording") or row.get("f_wake") is None:
                continue
            f0, f1 = int(row["f_wake"]), int(row.get("f_kill") or row["f_end"])
            try:
                states = list(RecordingReader(row["recording"]).states(f0, f1 + 200))
            except Exception as ex:                      # noqa: BLE001 - a broken recording is skipped and named
                print("skip", run.name, inst, row.get("episode"), ex)
                continue
            lab = {"arm": arm, "run": run.name, "inst": inst, "ep": int(row.get("episode", -1))}
            J = [j for j in jumps_of(states, lab, HERO_ATTACKS) if j["f"] <= f1]
            cst = row.get("cast_stab") or {}
            runs = list(cst.get("runs") or [])
            for j in J:
                j.pop("path", None)
                j.pop("shapes", None)
                j.pop("arc", None)
                j["script"] = next((r for r in runs if j["f"] - 2 <= int(r.get("f0") or -1) <= j["f"] + 40), None)
            hp = [(f, a, s_) for f, a, s_ in _hp_events(states) if f <= f1]
            eps.append({**lab, "kill": row.get("f_kill") is not None, "fight_s": round((f1 - f0) / 60.0, 2),
                        "outcome": row.get("outcome"), "hp_hits": len(hp), "hp_src": [s_[-40:] for _, _, s_ in hp],
                        "cast_stab": {k: v for k, v in cst.items() if k != "runs"}})
            jumps.extend(J)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"jumps": jumps, "episodes": eps}), "utf-8")
    print(f"{len(jumps)} jumps, {len(eps)} episodes -> {out}")


def _antic_hits(j: dict) -> list[dict]:
    ka = j["k_aim"] - j["k_land"]                   # the aim, STATE frames from the landing (< 0)
    return [h for h in j["hits"] if h["k"] < ka]


def _hurt(j: dict, upto: int | None) -> list[dict]:
    return [h for h in j.get("hurt") or [] if h.get("k") is not None and (upto is None or h["k"] <= upto)]


def summarize(J: list[dict], E: list[dict]) -> dict:
    by = defaultdict(list)
    for j in J:
        by[(j["arm"], j["fam"])].append(j)
    out = {}
    for (arm, fam), L in sorted(by.items()):
        n = len(L)
        ah = [_antic_hits(j) for j in L]
        src = Counter(h["src"] for hs in ah for h in hs)
        rune_end = [((j.get("rune") or {}).get("lit") or [None, None])[1] for j in L]
        hurt30 = [bool(_hurt(j, LAND_SAFE_F)) for j in L]
        hurt_rune = [bool(_hurt(j, (re + 10) if re is not None else j["k_end"] - j["k_land"] + 60))
                     for j, re in zip(L, rune_end)]
        behind = [j.get("hero_land") is not None and j["hero_land"] < 0 for j in L]
        d = {"n": n, "antic_hits": sum(len(x) for x in ah), "antic_hits_per": round(sum(len(x) for x in ah) / n, 3),
             "antic_hits_dist": dict(Counter(len(x) for x in ah)), "src": dict(src),
             "rel0": pct([j["rel0"] for j in L]), "rel_aim": pct([j["rel_aim"] for j in L]),
             "safe_land30": n - sum(hurt30), "safe_rune10": n - sum(hurt_rune), "behind_at_landing": sum(behind),
             "safe_and_behind": sum(1 for a, b in zip(hurt30, behind) if not a and b),
             "hurt": [{"ep": j["ep"], "run": j["run"], "hurt": _hurt(j, None)} for j in L if _hurt(j, None)][:12],
             "hits_total_per": round(sum(len(j["hits"]) for j in L) / n, 3)}
        if fam == "CC_JUMP_CAST":
            S = [j for j in L if j.get("script")]
            d["scripts"] = len(S)
            d["script_modes"] = dict(Counter(j["script"]["mode"] for j in S))
            st = [j for j in S if j["script"]["mode"] == "stab"]
            if st:
                ds_hit = [j for j in st if j["script"].get("k_hit") is not None]
                rs_pl = [j for j in ds_hit if j["script"].get("rs")]
                rs_st = [j for j in rs_pl if j["script"].get("rs_start_g") is not None]
                rs_hit = [j for j in rs_st if j["script"].get("rs_hit_g") is not None
                          and any(h["src"] == "RecoilStab" for h in _antic_hits(j) + j["hits"])]
                d["T1"] = {"stabs": len(st), "dashstab_hits": len(ds_hit), "rs_planned_at_hit": len(rs_pl),
                           "rs_started": len(rs_st), "rs_hit": len(rs_hit),
                           "rs_hit_unseen": sum(1 for j in rs_st if j["script"].get("why") == "rs hit unseen"),
                           "x0": pct([j["script"]["x0"] for j in st]), "k0": pct([j["script"]["k0"] for j in st]),
                           "k_hit": pct([j["script"]["k_hit"] for j in ds_hit]),
                           "rs_start_g": pct([j["script"]["rs_start_g"] for j in rs_st]),
                           "rs_hit_g": pct([j["script"]["rs_hit_g"] for j in rs_st if j["script"].get("rs_hit_g")]),
                           "at_aim_x": pct([(j["script"].get("at_aim") or {}).get("x") for j in rs_st]),
                           "at_aim_feet": pct([(j["script"].get("at_aim") or {}).get("feet") for j in rs_st]),
                           "ends": dict(Counter((j["script"]["end"], j["script"]["why"]) for j in st).most_common()),
                           "antic_hits_per_stab": round(sum(len(_antic_hits(j)) for j in st) / len(st), 3),
                           "antic_hits_per_rs": round(sum(len(_antic_hits(j)) for j in rs_pl) / len(rs_pl), 3)
                           if rs_pl else None,
                           "safe_land30_rs": sum(1 for j in rs_pl if not _hurt(j, LAND_SAFE_F)),
                           "behind_rs": sum(1 for j in rs_pl if (j.get("hero_land") or 0) < 0)}
            sp = [j for j in S if j["script"]["mode"] == "stop"]
            if sp:
                nh = [len(_antic_hits(j)) for j in sp]
                d["T2"] = {"stops": len(sp), "tap": sum(1 for j in sp if (j["script"].get("pred") or {}).get("tap")),
                           "x0": pct([j["script"]["x0"] for j in sp]), "k0": pct([j["script"]["k0"] for j in sp]),
                           "rel_j": pct([j["script"].get("rel_j") for j in sp]),
                           "x_stop": pct([j["script"].get("x_stop") for j in sp]),
                           "x_stop_pred": pct([(j["script"].get("pred") or {}).get("x_stop") for j in sp]),
                           "skid": sum(1 for j in sp if j["script"].get("skid")),
                           "stab_in_stop": sum(1 for j in sp if j["script"].get("stab_in_stop")),
                           "presses": dict(Counter(len(j["script"].get("presses") or []) for j in sp)),
                           "antic_hits_dist": dict(Counter(nh)), "ge2": sum(1 for x in nh if x >= 2),
                           "antic_hits_per_stop": round(sum(nh) / len(sp), 3),
                           "ends": dict(Counter((j["script"]["end"], j["script"]["why"]) for j in sp).most_common()),
                           "safe_land30": sum(1 for j in sp if not _hurt(j, LAND_SAFE_F)),
                           "behind": sum(1 for j in sp if (j.get("hero_land") or 0) < 0)}
            no = [j for j in L if not j.get("script")]
            d["no_script"] = {"n": len(no), "antic_hits_per": round(sum(len(_antic_hits(j)) for j in no) / len(no), 3)
                              if no else None, "rel0": pct([j["rel0"] for j in no])}
        out[f"{arm} {fam}"] = d
    ea = defaultdict(list)
    for e in E:
        ea[e["arm"]].append(e)
    for arm, L in sorted(ea.items()):
        why = Counter()
        for e in L:
            for k, v in (e.get("cast_stab") or {}).items():
                if k.startswith("no_") or k.startswith("why_") or k.startswith("end_"):
                    why[k] += v
        out[f"{arm} episodes"] = {"n": len(L), "kills": sum(e["kill"] for e in L),
                                  "fight_s": pct([e["fight_s"] for e in L]),
                                  "hp_hits": sum(e["hp_hits"] for e in L),
                                  "hp_hitless": sum(1 for e in L if not e["hp_hits"]),
                                  "hp_src": dict(Counter(s for e in L for s in e["hp_src"])), "cast_stab": dict(why)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--manifest", action="append", required=True)
    c.add_argument("--arms", default="")
    c.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--in", dest="inp", required=True)
    r.add_argument("--json", default="")
    a = ap.parse_args(argv)
    if a.cmd == "collect":
        collect(a.manifest, set(x for x in a.arms.split(",") if x) or None, Path(a.out))
    else:
        d = json.loads(Path(a.inp).read_text("utf-8"))
        rep = summarize(d["jumps"], d["episodes"])
        for k, v in rep.items():
            print("==", k)
            for kk, vv in v.items():
                print("  ", kk, json.dumps(vv) if not isinstance(vv, (int, float, str)) else vv)
        if a.json:
            Path(a.json).write_text(json.dumps(rep, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
