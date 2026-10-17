"""The Clapper's small-rune casts in the 1v1 runs (task 1v1 SP8d, forum.md 75): per cast (Spell Antic -> Cast 1 ->
Cast 2, one live Clapper) where she is at the antic's start, the hits on it in the antic (Spell Antic entry to Cast 1),
through the cast (to Cast 2's end) and through the bombs (to the ring-1 light + 25 game frames or the next move's
start), her box bottom at the lit frames of every bomb within reach of her, HP lost (small rune bombs and the rest)
from the antic's start to the end of that span, and the SSBOT_FORUM_RUNE_LOWHOP script's record. Distances are centre
to centre (her box centre, its transform), + = in front; heights are her box bottom above the floor (y 3.0).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp8d_cast collect --manifest C:/ssbot/sandbox/1v1sp8dt1_manifest.txt \
        [--arms sp8dT] --out C:/ssbot/data/m2_play/sp8d/t1/cast.json
    ../scripts/uv.cmd run python -m ssbot.tools.sp8d_cast report --in C:/ssbot/data/m2_play/sp8d/t1/cast.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ssbot.combat import rune_bombs as rb
from ssbot.combat import slam_play as sp
from ssbot.tools.sp3_jumps import _rows, pct

FLOOR = 3.0
CLOSE_U = 8.28                     # Close Range at <= 8.28 u centre to centre (sp8c_evade)
PRE, POST = 8, 160
TAIL_F = 25                        # the span ends this many game frames after ring 1's light (or the next move)
HIT_SRC = ("Slash", "AltSlash", "UpSlash", "DownSlash", "DownSlashAlt", "DownSlash New", "WallSlash", "DashStab",
           "RecoilStab")


def _body(e):
    for col in e.get("colliders") or ():
        if col.get("name") == sp.CLAPPER and col.get("enabled") and col.get("verts_world"):
            xs, ys = col["verts_world"][0::2], col["verts_world"][1::2]
            return (min(xs), min(ys), max(xs), max(ys))
    return None


def frame(s: dict) -> dict:
    """The per-frame record the cast analysis reads (also C:/ssbot/data/m2_play/sp8d/scripts/cast_extract.py)."""
    e = sp.clapper(s)
    st, tin = sp.control(e)
    h = s.get("hero") or {}
    tm = h.get("tm") or {}
    hit, hpl, dmg = [], [], []
    for ev in s.get("ev") or ():
        k, d = ev.get("k"), ev.get("d") or {}
        if k == "hit" and d.get("type_key") == sp.CLAPPER:
            dealt = d.get("dealt", d.get("amount"))
            if dealt is None or float(dealt) > 0:
                hit.append(str(d.get("src")))
        elif k == "hp" and (d.get("delta") or 0) < 0:
            hpl.append((-int(d.get("delta")), str(d.get("source"))))
        elif k == "damage":
            dmg.append(str(d.get("source")))
    return {"f": int(s["f"]), "dt": float(s.get("dt") or 0.0), "st": st, "tin": tin, "n_cl": len(sp.clappers(s)),
            "cx": float(e["pos"][0]) if e else None, "cy": float(e["pos"][1]) if e else None,
            "face": (1 if e.get("flipX") else -1) if e else None, "body": _body(e) if e else None,
            "hbox": tuple(h.get("box") or ()), "vel": tuple(h.get("vel") or (0, 0)),
            "clip": str((h.get("anim") or {}).get("clip") or ""), "mask": int((s.get("act") or {}).get("mask") or 0),
            "ground": bool(sp.on_ground(s)), "atk_cd": float(tm.get("atk_cd") or 0.0),
            "health": int(h.get("health") or 0), "bombs": rb.bomb_ents(s.get("ents")), "hit": hit, "hpl": hpl,
            "dmg": dmg}


def _hx(fr: dict) -> float | None:
    b = fr["hbox"]
    return 0.5 * (b[0] + b[2]) if b else None


def cast_of(fr: list[dict], i0: int, label: dict, runs: list[dict]) -> dict | None:
    """One cast: fr the frames around it (frame()), i0 its Spell Antic entry. None with two Clappers."""
    x = fr[i0]
    if x["n_cl"] != 1 or x["cx"] is None or _hx(x) is None:
        return None
    face = x["face"]
    g = [0.0]
    for a in fr[1:]:
        g.append(g[-1] + a["dt"] * 60.0)
    g0 = g[i0]
    ent, prev = {}, None
    end_i = len(fr)
    for i in range(i0, len(fr)):
        st = fr[i]["st"]
        if i > i0 and st == "Spell Antic" and prev != "Spell Antic":
            end_i = i
            break
        if st != prev and st not in ent:
            ent[st] = i
        prev = st
    c1, c2 = ent.get("Cast 1"), ent.get("Cast 2")
    c2e = next((i for i in range(c2, end_i) if fr[i]["st"] != "Cast 2"), None) if c2 is not None else None
    nxt = next((i for i in range(c2e, end_i) if fr[i]["st"] not in ("Idle", "Cast 2")), end_i) if c2e else end_i
    d0 = (_hx(x) - x["cx"]) * face
    rec = {**label, "f": x["f"], "d0": round(d0, 2), "ground0": x["ground"], "bot0": round(x["hbox"][1] - FLOOR, 2),
           "close": d0 <= CLOSE_U, "cast2": c2 is not None}
    # bombs: rings relative to its x at the Cast 2 entry
    x0 = fr[c2]["cx"] if c2 is not None else x["cx"]
    seen = {}
    for i in range((c2 or i0) - 1, len(fr)):
        for iid, bx, by, lit in fr[i]["bombs"]:
            m = round((bx - x0) * face / rb.DX)
            if abs((bx - x0) * face - rb.DX * m) > 0.6:
                continue
            r = seen.setdefault((iid, round(bx, 1)), {"m": m, "x": bx, "y": by, "a": i, "on": None, "off": None})
            if lit:
                r["on"] = i if r["on"] is None else r["on"]
                r["off"] = i
    r1 = [r for r in seen.values() if r["m"] == (1 if d0 >= 0 else -1) and r["on"] is not None]
    on1 = r1[0]["on"] if r1 else None
    span_end = min(nxt if nxt is not None else end_i, end_i)
    if on1 is not None:
        span_end = max(span_end, next((i for i in range(on1, len(fr)) if g[i] - g[on1] >= TAIL_F), len(fr) - 1))
        span_end = min(span_end, end_i)
    span_end = min(span_end, len(fr) - 1)
    rec["k_c2"] = round(g[c2] - g0, 1) if c2 is not None else None
    rec["k_idle"] = round(g[c2e] - g0, 1) if c2e is not None else None
    rec["k_next"] = round(g[nxt] - g0, 1) if nxt is not None and nxt < len(fr) else None
    rec["next"] = fr[nxt]["st"] if nxt is not None and nxt < len(fr) else None
    rec["k_r1"] = round(g[on1] - g0, 1) if on1 is not None else None

    def hits(a, b):
        return [(round(g[i] - g0, 1), s) for i in range(a, min(b, len(fr))) for s in fr[i]["hit"] if s in HIT_SRC]
    rec["hits_antic"] = hits(i0, c1 if c1 is not None else (c2 if c2 is not None else end_i))
    rec["hits_cast"] = hits(i0, c2e if c2e is not None else end_i)
    rec["hits_span"] = hits(i0, span_end + 1)
    rec["span_k"] = round(g[min(span_end, len(fr) - 1)] - g0, 1)
    # ground share in the antic, her distance at the antic's end
    an = range(i0, c1 if c1 is not None else min(i0 + 44, len(fr)))
    rec["ground_antic"] = round(sum(fr[i]["ground"] for i in an) / max(1, len(an)), 2)
    ie = (c1 if c1 is not None else min(i0 + 44, len(fr) - 1))
    rec["d_antic_end"] = round((_hx(fr[ie]) - fr[ie]["cx"]) * face, 2) if fr[ie]["cx"] is not None else None
    # every bomb lit near her: the lowest box bottom over its lit frames while within R + her half width
    lits = []
    for r in seen.values():
        if r["on"] is None:
            continue
        near = []
        for i in range(r["on"], r["off"] + 1):
            hx = _hx(fr[i])
            if hx is not None and abs(hx - r["x"]) < rb.R + 0.25:
                near.append((round(fr[i]["hbox"][1] - FLOOR, 2), round(abs(hx - r["x"]), 2)))
        if near:
            lits.append({"m": r["m"], "k_on": round(g[r["on"]] - g0, 1), "bot_min": min(b for b, _ in near),
                         "dx": min(d for _, d in near), "n": len(near)})
    rec["lits"] = lits
    hurt = []
    for i in range(i0, span_end + 1):
        for a, s in fr[i]["hpl"]:
            hurt.append({"k": round(g[i] - g0, 1), "hp": a, "src": s[-40:],
                         "bot": round(fr[i]["hbox"][1] - FLOOR, 2) if fr[i]["hbox"] else None})
    rec["hurt"] = hurt
    rec["bomb_hp"] = sum(h["hp"] for h in hurt if "rune bomb small" in h["src"])
    # her height around ring 1's light (the hop) and the jump presses in the span
    if on1 is not None:
        rec["bot_r1"] = [round(fr[i]["hbox"][1] - FLOOR, 2) for i in range(on1, min(on1 + 7, len(fr)))]
    jp = []
    for i in range(max(i0, 1), span_end + 1):
        if fr[i]["mask"] & 1 and not fr[i - 1]["mask"] & 1:
            n = 0
            while i + n < len(fr) and fr[i + n]["mask"] & 1:
                n += 1
            jp.append((round(g[i] - g0, 1), n))
    rec["jumps"] = jp
    run = next((r for r in runs if abs(int(r.get("f0") or -99) - x["f"]) <= 4), None)
    rec["script"] = run
    return rec


def casts_of(fr: list[dict], label: dict, runs: list[dict]) -> list[dict]:
    out, prev = [], None
    for i, x in enumerate(fr):
        if x["st"] == "Spell Antic" and prev != "Spell Antic":
            c = cast_of(fr[max(0, i - PRE): i + POST], min(PRE, i), label, runs)
            if c is not None:
                out.append(c)
        prev = x["st"]
    return out


def collect(manifests: list[str], arms: set | None, out: Path) -> None:
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.slam_play_live import manifest
    C, eps = [], []
    for arm, inst, run in manifest(manifests, arms):
        arm = arm.lstrip("\ufeff")
        for row in _rows(run, inst):
            if not row.get("recording") or row.get("f_wake") is None:
                continue
            f0, f1 = int(row["f_wake"]), int(row.get("f_kill") or row["f_end"])
            try:
                states = list(RecordingReader(row["recording"]).states(f0, f1 + 40))
            except Exception as ex:                      # noqa: BLE001 - a broken recording is skipped and named
                print("skip", run.name, inst, row.get("episode"), ex)
                continue
            lab = {"arm": arm, "run": run.name, "inst": inst, "ep": int(row.get("episode", -1)),
                   "seed": row.get("seed")}
            runs = ((row.get("policy") or {}).get("rune_lowhop") or {}).get("hop_runs") or []
            fr = [frame(s) for s in states]
            C += casts_of(fr, lab, runs)
            eps.append({**lab, "kill": row.get("f_kill") is not None, "hp_lost": row.get("hp_lost"),
                        "kill_s": row.get("kill_s"), "outcome": row.get("outcome"),
                        "lowhop": {k: v for k, v in ((row.get("policy") or {}).get("rune_lowhop") or {}).items()
                                   if k != "hop_runs"}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"casts": C, "episodes": eps}), "utf-8")
    print("casts", len(C), "episodes", len(eps), "->", out)


def summary(C: list[dict]) -> dict:
    cl = [c for c in C if c["close"] and c["cast2"]]
    n = len(cl)
    if not n:
        return {"casts": len(C), "close": 0}
    safe = [c for c in cl if not any("rune bomb small" in h["src"] for h in c["hurt"])]
    nohp = [c for c in cl if not c["hurt"]]
    ok_r1 = [c for c in cl if c.get("bot_r1") is not None]
    return {"casts": len(C), "close": n, "far": sum(1 for c in C if not c["close"] and c["cast2"]),
            "d0": pct([c["d0"] for c in cl]),
            "antic_hits": round(sum(len(c["hits_antic"]) for c in cl) / n, 2),
            "cast_hits": round(sum(len(c["hits_cast"]) for c in cl) / n, 2),
            "span_hits": round(sum(len(c["hits_span"]) for c in cl) / n, 2),
            "span_s": round(sum(c["span_k"] for c in cl) / 60.0 / n, 2),
            "span_hps": round(sum(len(c["hits_span"]) for c in cl) / max(1e-9, sum(c["span_k"] for c in cl) / 60.0), 2),
            "no_bomb_hp": len(safe), "no_hp": len(nohp), "gate_share": round(len(nohp) / n, 3),
            "ground_antic": round(sum(c["ground_antic"] for c in cl) / n, 2),
            "d_antic_end": pct([c["d_antic_end"] for c in cl]),
            "bot_at_r1_min": pct([min(c["bot_r1"]) for c in ok_r1]),
            "next": dict(Counter(c["next"] for c in cl).most_common(6)),
            "hurt_src": dict(Counter(h["src"] for c in cl for h in c["hurt"]).most_common(6)),
            "scripts": sum(1 for c in cl if c.get("script")),
            "script_end": dict(Counter(f"{(c['script'] or {}).get('end')}:{(c['script'] or {}).get('why')}"
                                       for c in cl if c.get("script")).most_common(8))}


def report(inp: Path) -> None:
    d = json.loads(inp.read_text("utf-8"))
    C, E = d["casts"], d["episodes"]
    by = defaultdict(list)
    for c in C:
        by[c["arm"]].append(c)
    eb = defaultdict(list)
    for e in E:
        eb[e["arm"]].append(e)
    for arm in sorted(by):
        s = summary(by[arm])
        es = eb.get(arm, [])
        s["episodes"] = len(es)
        s["hp_hitless"] = sum(1 for e in es if not e.get("hp_lost"))
        print(arm, json.dumps(s))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--manifest", nargs="+", required=True)
    c.add_argument("--arms", nargs="*")
    c.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--in", dest="inp", required=True)
    a = ap.parse_args()
    if a.cmd == "collect":
        collect(a.manifest, set(a.arms) if a.arms else None, Path(a.out))
    else:
        report(Path(a.inp))


if __name__ == "__main__":
    main()
