"""How far an enemy's own support reaches (task "support reach", the person 2026-10-09: at raw frame 5690 of
20261009_085824 the purple support of 'Choristor 3' at k = 12 covered where they stood still, never hit, and the
Choristor clearly cannot reach that far; their hypothesis: the model lets the enemy run while it is in its wind-up).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.support_reach explain <session> --attempt N --frame F --enemy "Choristor 3"
        [--ks 0,12] [--out <dir>]                 # every placement of that enemy, which cover the hero, a PNG
    ../scripts/uv.cmd run python -m ssbot.tools.support_reach motion <hitboxes / recordings>   # antic motion

explain: ZoneEngine (tools.zone_overlay, the overlay's forecast path, as rerun_zones feeds it) fed up to the frame;
the enemy's tracker (Control state, time in state, the current instance: family, start, anchor, aim, re-anchor),
and every placement it owns (fine / window / bbox rows, tubes and boxes, hazard paths): its layer (forum_layer_audit
classify), template key, entry window, anchor / anchor box and mirror, margin, the world box it covers on the
hero-centre grid at each k and whether it covers the hero's centre.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

FT = 1.0 / 60.0
OUT = Path(r"C:\ssbot\data\m2_forum_reach")
DEMO_CACHE = Path(r"C:\ssbot\data\m2_forum_overlay\demo_cache")


def _one_hot(n: int, i: int) -> np.ndarray:
    m = np.zeros(n, bool)
    m[i] = True
    return m


def _bbox_of(mask: np.ndarray, grid) -> list | None:
    if mask is None or not mask.any():
        return None
    r, c = np.nonzero(mask)
    return [round(float(grid.xs[c.min()]), 2), round(float(grid.ys[r.min()]), 2), round(float(grid.xs[c.max()]), 2),
            round(float(grid.ys[r.max()]), 2)]


_SM: dict | None = None


def state_margins() -> dict:
    """{(type, family, state): u} of SSBOT_FORUM_MARGIN=state (empty otherwise)."""
    global _SM
    if _SM is None:
        import os
        from ssbot.combat.enemy_tables import FORUM_DIR, parse_state_margins
        _SM = {}
        if os.environ.get("SSBOT_FORUM_MARGIN", "family").strip().lower() == "state":
            _SM = parse_state_margins(json.loads((FORUM_DIR / "support_margins_state.json").read_text("utf-8"))
                                      .get("by_state") or {})
    return _SM


def placements_of(eng, fcast, iid: int, ks, hero) -> list[dict]:
    """Every placement / box / path of one owner, with its masks on the grid at ks and whether it covers hero."""
    from ssbot.tools.forum_layer_audit import _key_name, classify
    g = eng.grid
    store = fcast.fc.tables.store
    tables = fcast.fc.tables
    tk = np.asarray(ks, np.float64) * FT
    F = len(ks)
    cx = np.ascontiguousarray(np.repeat(g.gx, F, axis=1))
    cy = np.ascontiguousarray(np.repeat(g.gy, F, axis=1))
    hx = np.full((1, F), hero[0]) if hero else None
    hy = np.full((1, F), hero[1]) if hero else None
    lay_of = {}
    for key, kind, sel in classify(fcast):
        for i in np.flatnonzero(sel):
            lay_of[(kind, int(i))] = key[0]
    tkey = {s.iid: s.type_key for s in fcast.subjects}.get(iid)
    sm = state_margins()
    out = []
    for kind, meta, fn in (("pm", fcast.pm, fcast._fine_occ), ("wm", fcast.wm, fcast._win_occ),
                           ("bb", fcast.bb, fcast._bbox_occ)):
        n = len(meta["owner"])
        for i in np.flatnonzero(np.asarray(meta["owner"]) == iid) if n else ():
            sel = _one_hot(n, int(i))
            o = fn(cx, cy, tk, sel)
            h = fn(hx, hy, tk, sel)[0] if hero else np.zeros(F, bool)
            fam = str(meta["family"][i])
            if kind == "pm":
                tid = int(fcast.P.tid[i])
                ent = [round(-float(fcast.P.t_ref[i]), 4)] * 2
                anc = [round(float(fcast.P.ax[i]), 2), round(float(fcast.P.ay[i]), 2), 0.0, 0.0]
                mir = int(fcast.P.mirror[i])
            elif kind == "wm":
                tid = int(fcast.W.tid[i])
                ent = [round(float(fcast.W.e0[i]), 4), round(float(fcast.W.e1[i]), 4)]
                anc = [round(float(fcast.W.ax[i]), 2), round(float(fcast.W.ay[i]), 2), 0.0, 0.0]
                mir = int(fcast.W.mirror[i])
            else:
                tid = int(meta["tid"][i])
                ent = [round(float(meta["e0"][i]), 4), round(float(meta["e1"][i]), 4)]
                anc = [round(float(meta[k][i]), 2) for k in ("cx", "cy", "hx", "hy")]
                mir = int(meta["mir"][i])
            key = _key_name(store, tid)
            parts = key.split("/")
            st = parts[2] if len(parts) >= 4 else None
            m = tables.margins.get((tkey, fam), 0.0)
            if sm and st is not None and parts[-1] == "anchor":
                m = sm.get((tkey, fam, st), m)
            out.append({"kind": {"pm": "fine", "wm": "window", "bb": "bbox"}[kind], "row": int(i),
                        "layer": lay_of.get((kind, int(i))), "family": fam, "state": st, "key": key, "tid": tid,
                        "committed": bool(meta["committed"][i]), "p": round(float(meta["prob"][i]), 3),
                        "entry": ent, "on_off": [round(float(meta["on"][i]), 4), round(float(meta["off"][i]), 4)],
                        "ton": None if not math.isfinite(float(meta["ton"][i])) else round(float(meta["ton"][i]), 4),
                        "anchor": anc, "mirror": mir, "margin": round(float(m), 3),
                        "masks": {k: o[:, j].reshape(g.shape) & g.inside for j, k in enumerate(ks)},
                        "hero": {k: bool(h[j]) for j, k in enumerate(ks)}})
    for b in fcast.boxes:
        if int(b[0]) != iid:
            continue
        kind = b[1]
        o = fcast._box_occ(cx, cy, tk, kinds=(kind,), only={iid})
        h = fcast._box_occ(hx, hy, tk, kinds=(kind,), only={iid})[0] if hero else np.zeros(F, bool)
        out.append({"kind": f"box:{kind}", "layer": kind, "family": None, "state": None, "key": kind,
                    "box": [round(float(x), 2) for x in b[2:6]], "vel": [round(float(b[6]), 2), round(float(b[7]), 2)],
                    "grow": None if b[8] is None else [str(x) if isinstance(x, str) else round(float(x), 3)
                                                       for x in b[8]],
                    "t_from_to": [round(float(b[9]), 4), round(float(b[10]), 4)], "t_seen": round(float(b[11]), 4),
                    "masks": {k: o[:, j].reshape(g.shape) & g.inside for j, k in enumerate(ks)},
                    "hero": {k: bool(h[j]) for j, k in enumerate(ks)}})
        break_kinds = None  # noqa: F841 (one entry per box kind: _box_occ unions the owner's boxes of that kind)
    seen = set()
    out2 = []
    for r in out:                          # boxes of one kind are queried together: keep one row per kind
        if r["kind"].startswith("box:"):
            if r["kind"] in seen:
                continue
            seen.add(r["kind"])
        out2.append(r)
    for p in fcast.paths:
        if int(p.iid) != iid:
            continue
        o = fcast._path_occ(cx, cy, tk, only={iid})
        h = fcast._path_occ(hx, hy, tk, only={iid})[0] if hero else np.zeros(F, bool)
        out2.append({"kind": "path", "layer": "haz_path", "family": p.type_key, "state": None, "key": p.kind,
                     "masks": {k: o[:, j].reshape(g.shape) & g.inside for j, k in enumerate(ks)},
                     "hero": {k: bool(h[j]) for j, k in enumerate(ks)}})
    for r in out2:
        r["world"] = {k: _bbox_of(m, g) for k, m in r["masks"].items()}
    return out2


def tracker_info(eng, fcast, iid: int) -> dict:
    tr = eng.pol.fc.trackers[iid]
    T = fcast.origin_t
    c = tr.cur
    d = {"iid": iid, "name": eng.name(iid), "type": tr.tk, "state": tr.state,
         "t_in_state": None if tr.t_entry is None else round(T - tr.t_entry, 4),
         "pos": None if tr.pos is None else [round(float(v), 3) for v in tr.pos],
         "vel": [round(float(v), 3) for v in tr.vel], "seen_age": round(T - tr.seen_T, 4),
         "seen_box": None if tr.seen_box is None else [round(float(v), 2) for v in tr.seen_box],
         "flip": getattr(tr, "flip", None), "in_play": tr.in_play, "parked": tr.parked}
    if c is not None:
        d["cur"] = {"family": c.family, "start": c.start,
                    "since_start": None if c.t_start is None else round(T - c.t_start, 4),
                    "anchor": None if c.anchor is None else [round(float(v), 3) for v in c.anchor],
                    "mirror": c.mirror, "aim_state": c.aim_state,
                    "aim_anchor": None if c.aim_anchor is None else [round(float(v), 3) for v in c.aim_anchor],
                    "aim_bin": c.aim_bin, "aim_mirror": c.aim_mirror, "re_state": c.re_state,
                    "re_anchor": None if c.re_anchor is None else [round(float(v), 3) for v in c.re_anchor]}
    return d


def feed_to(eng, states, frame: int):
    """Feed until the first STATE whose raw frame is >= frame; returns that STATE."""
    for s in states:
        eng.feed(s)
        if s["_f_raw"] >= frame:
            return s
    return None


PAL = ((255, 80, 80), (80, 200, 255), (90, 255, 90), (255, 90, 255), (255, 200, 60), (60, 255, 255),
       (170, 120, 255), (255, 150, 150), (150, 255, 200), (200, 200, 90), (120, 160, 255), (255, 120, 40))


def draw_png(eng, s: dict, rows: list[dict], info: dict, ks, path: Path, title: str, only_hero: bool = False) -> None:
    """The arena (hero-centre grid) with each placement's outline at each k (one panel per k), the hero centre,
    the enemy's transform and its damage colliders (red), the anchors (crosses)."""
    import cv2
    from ssbot.tools.zone_overlay import damage_colliders, mask_contours
    g = eng.grid
    S = 14                                       # px per u
    W = int((g.xs[-1] - g.xs[0] + 8) * S)
    Hh = int((g.ys[-1] - g.ys[0] + 6) * S)
    x0, y0 = g.xs[0] - 4, g.ys[0] - 3

    def px(x, y):
        return int(round((x - x0) * S)), int(round(Hh - (y - y0) * S))
    panels = []
    hero = eng.hero(s)
    for k in ks:
        img = np.full((Hh, W, 3), 24, np.uint8)
        ins = mask_contours(g.inside)
        for c in ins:
            pts = np.array([px(*g.to_world(np.array([q[0]]), np.array([q[1]]))[0]) for q in c], np.int32)
            cv2.polylines(img, [pts], True, (70, 70, 70), 1)
        lines = [f"{title}  k = {k}"]
        n = 0
        for r in rows:
            m = r["masks"].get(k)
            if m is None or not m.any() or (only_hero and not r["hero"].get(k)):
                continue
            col = PAL[n % len(PAL)]
            n += 1
            for c in mask_contours(m):
                w = g.to_world(c[:, 0], c[:, 1])
                pts = np.array([px(*q) for q in w], np.int32)
                cv2.polylines(img, [pts], True, col, 2 if r["hero"].get(k) else 1)
            a = r.get("anchor")
            if a and math.isfinite(a[0]):
                p = px(a[0], a[1])
                cv2.drawMarker(img, p, col, cv2.MARKER_CROSS, 12, 2)
                if a[2] > 0 or a[3] > 0:
                    cv2.rectangle(img, px(a[0] - a[2], a[1] - a[3]), px(a[0] + a[2], a[1] + a[3]), col, 1)
            lab = f"{'*' if r['hero'].get(k) else ' '} {r['kind']} {r.get('layer')} {r.get('key')}"
            if r.get("entry"):
                lab += f" e[{r['entry'][0]:.2f},{r['entry'][1]:.2f}]"
            lines.append((lab, col))
        for poly, _cl, lab, _v, o in damage_colliders(s):
            pts = np.array([px(*q) for q in poly], np.int32)
            cv2.polylines(img, [pts], True, (60, 60, 255) if o == info["iid"] else (90, 90, 150), 2)
        if info.get("pos"):
            cv2.circle(img, px(*info["pos"]), 6, (255, 255, 255), 2)
            cv2.putText(img, f"{info['name']} {info['state']} {info['t_in_state']:.2f}s", px(info["pos"][0] - 2,
                        info["pos"][1] + 3.5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        if hero:
            cv2.circle(img, px(*hero), 5, (255, 255, 255), -1)
            cv2.putText(img, "hero", px(hero[0] + 0.4, hero[1] + 0.4), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 1, cv2.LINE_AA)
        y = 18
        for ln in lines:
            txt, col = (ln, (255, 255, 255)) if isinstance(ln, str) else ln
            cv2.putText(img, txt[:150], (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1, cv2.LINE_AA)
            y += 16
        panels.append(img)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.vstack(panels))


def cmd_explain(a) -> int:
    from ssbot.tools.zone_overlay import ZoneEngine, attempt_states
    session = Path(a.session)
    ks = tuple(int(x) for x in a.ks.split(","))
    eng = ZoneEngine(crest="Wanderer", threads=a.threads)
    seg, terrain, states = attempt_states(session, a.attempt, Path(a.demo_cache) if a.demo_cache else None)
    eng.crest = seg.get("crest") or eng.crest
    eng.start(terrain)
    s = feed_to(eng, states, a.frame)
    fc = eng.forecast()
    hero = eng.hero(s)
    print("enemies:", [(n, eng.state_of(i)) for i, n in eng.names.items()])
    for name in a.enemy.split(","):
        _explain_one(eng, s, fc, name, hero, ks, a, session)
    return 0


def _explain_one(eng, s, fc, name, hero, ks, a, session) -> None:
    a.enemy = name
    iid = next((i for i, n in eng.names.items() if n == name), None)
    if iid is None:
        print(f"no {name!r}")
        return
    info = tracker_info(eng, fc, iid)
    rows = placements_of(eng, fc, iid, ks, hero)
    rep = {"session": session.name, "attempt": a.attempt, "frame": int(s["_f_raw"]), "game_frame": int(s["f"]),
           "config": eng.config_text(), "hero": None if hero is None else [round(v, 3) for v in hero],
           "enemy": info, "placements": [{k: v for k, v in r.items() if k != "masks"} for r in rows],
           "cover_hero": {k: [i for i, r in enumerate(rows) if r["hero"].get(k)] for k in ks}}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{a.tag}{session.name}_f{s['_f_raw']}_{a.enemy.replace(' ', '_')}"
    (out / f"{tag}.json").write_text(json.dumps(rep, indent=1, default=str), "utf-8")
    draw_png(eng, s, rows, info, ks, out / f"{tag}.png", f"{session.name} f{s['_f_raw']} {a.enemy} {a.tag}")
    draw_png(eng, s, rows, info, ks, out / f"{tag}_hero.png", f"{session.name} f{s['_f_raw']} {a.enemy} "
             f"{a.tag} (only placements covering the hero)", only_hero=True)
    print(json.dumps({k: v for k, v in rep.items() if k != "placements"}, indent=1, default=str))
    for i, r in enumerate(rep["placements"]):
        print(i, json.dumps(r, default=str))


# ------------------------------------------------------------------------------------------------ recorded motion

HIT_RECOIL_S = 0.6      # a row this long after a hit on the enemy counts as "after a hit" (recoil / knockback)


def _fight_motion(path: str, fams: dict) -> dict:
    """{(tk, fam, state): stats} of one fight cache: per instance row, the body's displacement from the instance's
    anchor (u, x mirrored by the anchor's facing: + = forward) and from its entry into the row's state, and the
    damage colliders' reach (forward / back / up / down) from the anchor and from the body at that row; rows split by
    whether the enemy was hit within HIT_RECOIL_S before (recoil) or not."""
    from ssbot.knowledge.forum_cache import load_cache
    from ssbot.tools.forum_aim import FACES_LEFT, instances
    c = load_cache(Path(path))
    T = np.asarray(c["T"], np.float64)
    fi = {int(f): i for i, f in enumerate(c["f"])}
    hits: dict = {}
    for f, kind, d in c["events"]:
        if kind == "hit" and isinstance(d, dict) and d.get("ent") is not None and int(f) in fi:
            hits.setdefault(int(d["ent"]), []).append(T[fi[int(f)]])
    out: dict = {}
    insts = instances(c, fams, threat=True)
    for (tk, fam), lst in insts.items():
        for inst in lst:
            iid = inst["iid"]
            hs = np.asarray(hits.get(iid, ()), np.float64)
            ax, ay = inst["pos"][0]
            m = FACES_LEFT[1 if inst["flip"][0] else 0]
            st_entry = {}
            for j, st in enumerate(inst["st"]):
                if st not in st_entry:
                    st_entry[st] = j
                bx, by = inst["pos"][j]
                ex, ey = inst["pos"][st_entry[st]]
                t = inst["t"][j]
                recoil = bool(len(hs) and ((hs <= t + 1e-9) & (hs >= t - HIT_RECOIL_S)).any())
                d = out.setdefault((tk, fam, st), {"n_rows": 0, "inst": set(), "clean": _acc(), "recoil": _acc()})
                d["n_rows"] += 1
                d["inst"].add((iid, float(inst["t"][0])))
                a = d["recoil" if recoil else "clean"]
                _upd(a, "body_dx", (bx - ax) * m)
                _upd(a, "body_dy", by - ay)
                _upd(a, "state_dx", (bx - ex) * m)
                _upd(a, "speed", float(np.hypot(*inst["vel"][j])))
                for x0, y0, x1, y1 in inst["boxes"][j]:
                    if not np.isfinite(x0):
                        continue
                    u0, u1 = sorted(((x0 - ax) * m, (x1 - ax) * m))
                    _upd(a, "col_fwd_anchor", u1)
                    _upd(a, "col_back_anchor", u0)
                    v0, v1 = sorted(((x0 - bx) * m, (x1 - bx) * m))
                    _upd(a, "col_fwd_body", v1)
                    _upd(a, "col_back_body", v0)
                    _upd(a, "col_up_body", y1 - by)
                    _upd(a, "col_dn_body", y0 - by)
    for d in out.values():
        d["inst"] = len(d["inst"])
    return out


def _acc() -> dict:
    return {}


def _upd(a: dict, k: str, v: float) -> None:
    lo, hi, n = a.get(k, (math.inf, -math.inf, 0))
    a[k] = (min(lo, float(v)), max(hi, float(v)), n + 1)


def _merge(acc: dict, got: dict) -> None:
    for key, d in got.items():
        t = acc.setdefault(key, {"n_rows": 0, "inst": 0, "clean": {}, "recoil": {}})
        t["n_rows"] += d["n_rows"]
        t["inst"] += d["inst"]
        for part in ("clean", "recoil"):
            for k, (lo, hi, n) in d[part].items():
                l0, h0, n0 = t[part].get(k, (math.inf, -math.inf, 0))
                t[part][k] = (min(l0, lo), max(h0, hi), n0 + n)


def cmd_motion(a) -> int:
    """Per (type, family, state): how the body moves from the anchor and inside the state, and how far the damage
    colliders reach, from every Forum fight cache (dev + fresh), clean rows and rows after a hit apart."""
    import glob
    from concurrent.futures import ProcessPoolExecutor
    from ssbot.tools.forum_aim import DEV, FRESH, _low_priority, family_states
    fams = family_states()
    paths = sorted(glob.glob(str(DEV / "*.npz"))) + sorted(glob.glob(str(FRESH / "*.npz")))
    if a.limit:
        paths = paths[:a.limit]
    acc: dict = {}
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_low_priority) as ex:
        for i, got in enumerate(ex.map(_fight_motion, paths, [fams] * len(paths), chunksize=1)):
            _merge(acc, got)
            if (i + 1) % 20 == 0:
                print(f"{i + 1} / {len(paths)}", flush=True)
    rep = {"fights": len(paths), "recoil_s": HIT_RECOIL_S, "by_state": {
        f"{tk}|{fam}|{st}": {"n_rows": d["n_rows"], "inst": d["inst"],
                             **{part: {k: [round(lo, 3), round(hi, 3), n] for k, (lo, hi, n) in d[part].items()}
                                for part in ("clean", "recoil")}}
        for (tk, fam, st), d in sorted(acc.items())}}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1), "utf-8")
    print(f"{len(rep['by_state'])} states -> {out}")
    return 0


# ------------------------------------------------------------------------------------------------ real reach

REACH_KS = tuple(range(0, 61))   # every frame up to 1 s (the planner's horizon is 0.8 s)
K_SLACK = 1             # the templates' +-1 bin: the support at k is compared with the reach at k - 1 .. k + 1
KB_FREE_F = 20          # "no hit" rows: the enemy not hit from this many frames before t to t + k (a knockback
#                         lasts up to ~15 frames: forum.md Â§29.11)


def _fight_reach(path: str, ks=REACH_KS) -> dict:
    """{(tk, state at t, k, part): [u0, u1, v0, v1, n]} of one fight cache: the threat colliders (dealt > 0 or the
    multi-hit ones, the cache's e_box) of an enemy at frame t + k relative to its transform at t, x mirrored by its
    facing at t (+ = forward); part "all" or "nohit" (not hit from KB_FREE_F frames before t to t + k). Hidden rows
    skipped."""
    from ssbot.knowledge.forum_cache import load_cache
    c = load_cache(Path(path))
    T = np.asarray(c["T"], np.float64)
    f_all = np.asarray(c["f"], np.int64)
    fi_of = {int(f): i for i, f in enumerate(f_all)}
    e_iid = np.asarray(c["e_iid"], np.int64)
    e_fi = np.asarray(c["e_fi"], np.int64)
    hits: dict = {}
    for f, kind, d in c["events"]:
        if kind == "hit" and isinstance(d, dict) and d.get("ent") is not None and int(f) in fi_of:
            hits.setdefault(int(d["ent"]), []).append(fi_of[int(f)])
    out: dict = {}
    types, states = c["types"], c["states"]
    order = np.lexsort((e_fi, e_iid))
    iids, starts = np.unique(e_iid[order], return_index=True)
    ends = np.append(starts[1:], len(order))
    box = np.asarray(c["e_box"], np.float64)
    for iid, a, b in zip(iids.tolist(), starts.tolist(), ends.tolist()):
        rows = order[a:b]
        fi = e_fi[rows]
        tk = types[int(c["e_tk"][rows[0]])]
        x = np.asarray(c["e_x"][rows], np.float64)
        y = np.asarray(c["e_y"][rows], np.float64)
        m = np.where(np.asarray(c["e_flip"][rows]) != 0, 1.0, -1.0)      # FACES_LEFT: flipX True faces +x
        st = np.asarray(c["e_st"][rows])
        hid = np.asarray(c["e_hidden"][rows]) != 0
        bx = box[rows]
        hf = np.sort(np.asarray(hits.get(iid, ()), np.int64))
        for k in ks:
            j = np.minimum(np.searchsorted(fi, fi + k), len(fi) - 1)
            j = np.where(fi[j] == fi + k, j, -1)
            ok = (j >= 0) & ~hid
            ok[ok] &= ~hid[j[ok]] & np.isfinite(bx[j[ok], 0])
            idx = np.flatnonzero(ok)
            if not len(idx):
                continue
            jj = j[idx]
            u0 = (bx[jj, 0] - x[idx]) * m[idx]
            u1 = (bx[jj, 2] - x[idx]) * m[idx]
            lo, hi = np.minimum(u0, u1), np.maximum(u0, u1)
            v0, v1 = bx[jj, 1] - y[idx], bx[jj, 3] - y[idx]
            if len(hf):
                c0 = np.searchsorted(hf, fi[idx] - KB_FREE_F, "left")
                c1 = np.searchsorted(hf, fi[idx] + k, "right")
                nohit = c1 == c0
            else:
                nohit = np.ones(len(idx), bool)
            for s in np.unique(st[idx]):
                sel = st[idx] == s
                sname = states[int(s)] if s >= 0 else None
                for part, pm in (("all", sel), ("nohit", sel & nohit)):
                    if not pm.any():
                        continue
                    key = (tk, sname, k, part)
                    r = out.get(key)
                    vals = [float(lo[pm].min()), float(hi[pm].max()), float(v0[pm].min()), float(v1[pm].max()),
                            int(pm.sum())]
                    out[key] = vals if r is None else [min(r[0], vals[0]), max(r[1], vals[1]), min(r[2], vals[2]),
                                                       max(r[3], vals[3]), r[4] + vals[4]]
    return out


def cmd_reach(a) -> int:
    """The real reach table (module docstring): per (type, Control state now, k) the box, relative to the enemy's
    transform now (x by its facing now), that its threat colliders k frames later stayed in, over every Forum fight
    cache (dev + fresh); "all" rows and "nohit" rows (not hit from KB_FREE_F frames before to k after)."""
    import glob
    from concurrent.futures import ProcessPoolExecutor
    from ssbot.tools.forum_aim import DEV, FRESH, _low_priority
    paths = sorted(glob.glob(str(DEV / "*.npz"))) + ([] if a.dev_only else sorted(glob.glob(str(FRESH / "*.npz"))))
    if a.limit:
        paths = paths[:a.limit]
    acc: dict = {}
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_low_priority) as ex:
        for i, got in enumerate(ex.map(_fight_reach, paths, chunksize=1)):
            for key, v in got.items():
                r = acc.get(key)
                acc[key] = v if r is None else [min(r[0], v[0]), max(r[1], v[1]), min(r[2], v[2]), max(r[3], v[3]),
                                                r[4] + v[4]]
            if (i + 1) % 20 == 0:
                print(f"{i + 1} / {len(paths)}", flush=True)
    K = max(REACH_KS)
    types: dict = {}
    for (tk, st, k, part), v in acc.items():
        arr = types.setdefault(tk, {}).setdefault(str(st), {}).setdefault(part, [None] * (K + 1))
        arr[k] = [round(v[0], 3), round(v[1], 3), round(v[2], 3), round(v[3], 3), v[4]]
    rep = {"fights": len(paths), "dev_only": bool(a.dev_only), "k_max": K, "kb_free_f": KB_FREE_F,
           "desc": "per type, Control state at t, part (all rows / nohit: not hit from kb_free_f frames before t to "
                   "t + k), k = 0 .. k_max: [u0, u1, v0, v1, n] = back / forward edge (x by the facing at t, + = "
                   "forward), bottom / top of the threat colliders (dealt > 0 or multi-hit) at t + k relative to the "
                   "transform at t, over n rows (tools.support_reach reach)",
           "types": types}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, separators=(",", ":")), "utf-8")
    print(f"{len(acc)} rows -> {out}")
    return 0


# ------------------------------------------------------------------------------------------------ the clip table

from ssbot.combat.reach_table import (CLIP_BANDS, CLIP_FILE, CLIP_KMAX, CLIP_MIN_ROWS, NT, PARTS,  # noqa: E402
                                      BODY_FILE, KB_FREE_F as CLIP_KB_F, ClipTable, empty_boxes, merge_boxes,
                                      save_clip, tau_bin, unclipped_states)


def _fight_reach_all(path: str, kmax: int = CLIP_KMAX, body: dict | None = None) -> dict:
    """{(tk, state): [B [NT + 1, 2, kmax + 1, 4], N [NT + 1, 2, kmax + 1]]} of one fight cache (combat.reach_table):
    the threat colliders (e_box) of an enemy k frames after a row, relative to its transform at the row (x by its
    facing then), by the row's time-in-state bin (NT: every bin) and part (0 all, 1 nohit: not hit from CLIP_KB_F
    frames before the row to k after); hidden rows skipped. body ({type: hull}, SSBOT_FORUM_BODYCLIP's table): the
    body hull at the transform k frames after (production_tubes body_hull, the idle tube's box) instead of the
    colliders; a type without a hull is skipped."""
    from ssbot.knowledge.forum_cache import load_cache
    c = load_cache(Path(path))
    e_iid = np.asarray(c["e_iid"], np.int64)
    e_fi = np.asarray(c["e_fi"], np.int64)
    box = np.asarray(c["e_box"], np.float64)
    f_all = np.asarray(c["f"], np.int64)
    fi_of = {int(f): i for i, f in enumerate(f_all)}
    hits: dict = {}
    for f, kind, d in c["events"]:
        if kind == "hit" and isinstance(d, dict) and d.get("ent") is not None and int(f) in fi_of:
            hits.setdefault(int(d["ent"]), []).append(fi_of[int(f)])
    types, states = c["types"], c["states"]
    order = np.lexsort((e_fi, e_iid))
    iids, starts = np.unique(e_iid[order], return_index=True)
    ends = np.append(starts[1:], len(order))
    acc: dict = {}
    for iid, a, b in zip(iids.tolist(), starts.tolist(), ends.tolist()):
        rows = order[a:b]
        fi = e_fi[rows]
        tk = types[int(c["e_tk"][rows[0]])]
        x = np.asarray(c["e_x"][rows], np.float64)
        y = np.asarray(c["e_y"][rows], np.float64)
        m = np.where(np.asarray(c["e_flip"][rows]) != 0, 1.0, -1.0)
        st = np.asarray(c["e_st"][rows]).astype(np.int64)
        tb = tau_bin(np.nan_to_num(np.asarray(c["e_tin"][rows], np.float64), nan=0.0))
        hid = np.asarray(c["e_hidden"][rows]) != 0
        bx = box[rows]
        if body is not None:
            h = body.get(tk)
            if h is None:
                continue
            bx = np.stack([x + h[0], y + h[1], x + h[2], y + h[3]], 1)
        has = np.isfinite(bx[:, 0]) & ~hid
        ok0 = ~hid & (st >= 0)
        codes = np.unique(st[ok0])
        if not len(codes) or not has.any():
            continue
        lidx = np.searchsorted(codes, st)
        hf = np.sort(np.asarray(hits.get(iid, ()), np.int64))
        B = empty_boxes(len(codes), NT, 2, kmax + 1)
        N = np.zeros((len(codes), NT, 2, kmax + 1), np.int64)
        for k in range(kmax + 1):
            j = np.minimum(np.searchsorted(fi, fi + k), len(fi) - 1)
            good = ok0 & (fi[j] == fi + k) & has[j]
            idx = np.flatnonzero(good)
            if not len(idx):
                continue
            jj = j[idx]
            u0 = (bx[jj, 0] - x[idx]) * m[idx]
            u1 = (bx[jj, 2] - x[idx]) * m[idx]
            vals = np.stack([np.minimum(u0, u1), np.maximum(u0, u1), bx[jj, 1] - y[idx], bx[jj, 3] - y[idx]], 1)
            nohit = np.ones(len(idx), bool) if not len(hf) else \
                np.searchsorted(hf, fi[idx] + k, "right") == np.searchsorted(hf, fi[idx] - CLIP_KB_F, "left")
            li, ti = lidx[idx], tb[idx]
            for part, sel in ((0, slice(None)), (1, nohit)):
                L, Ti, V = li[sel], ti[sel], vals[sel]
                if not len(L):
                    continue
                kk = np.full(len(L), k)
                pp = np.full(len(L), part)
                np.minimum.at(B[..., 0], (L, Ti, pp, kk), V[:, 0])
                np.maximum.at(B[..., 1], (L, Ti, pp, kk), V[:, 1])
                np.minimum.at(B[..., 2], (L, Ti, pp, kk), V[:, 2])
                np.maximum.at(B[..., 3], (L, Ti, pp, kk), V[:, 3])
                np.add.at(N, (L, Ti, pp, kk), 1)
        for i, s in enumerate(codes.tolist()):
            key = (tk, states[s])
            bb = np.concatenate([B[i], empty_boxes(1, 2, kmax + 1)], 0)
            nn = np.concatenate([N[i], np.zeros((1, 2, kmax + 1), np.int64)], 0)
            for t in range(NT):
                bb[NT] = merge_boxes(bb[NT], bb[t])
                nn[NT] += nn[t]
            r = acc.get(key)
            acc[key] = [bb, nn] if r is None else [merge_boxes(r[0], bb), r[1] + nn]
    return acc


def body_hulls() -> dict:
    """{type key: (x0, y0, x1, y1)} the body hull relative to the transform (support_margins.json production_tubes
    body_hull: the idle tube's box)."""
    from ssbot.tools.forum_aim import FORUM_DIR
    md = json.loads((FORUM_DIR / "support_margins.json").read_text("utf-8"))
    return {k: tuple(map(float, v)) for k, v in ((md.get("production_tubes") or {}).get("body_hull") or {}).items()}


def fam_of_states() -> dict:
    from ssbot.core.forum import FORUM_TYPES
    from ssbot.tools.forum_aim import FORUM_DIR
    out = {}
    for tk, sp in FORUM_TYPES.items():
        p = FORUM_DIR / f"{sp.enemy}.json"
        if not p.exists():
            continue
        for fam, a in json.loads(p.read_text("utf-8"))["attacks"].items():
            for s in a.get("states") or ():
                out.setdefault((tk, s), fam)
    return out


def cmd_clip_build(a) -> int:
    """The reach clip table (SSBOT_FORUM_RCLIP, combat.reach_table) from the DEV fight caches only, certified 2-fold
    by fight (r per type, state, time bin, part and look-ahead band = the most one fold's boxes exceed the other
    fold's run-time boxes; per state: the largest over its time bins); the table is every dev fight's, r added at
    run time."""
    import glob
    from concurrent.futures import ProcessPoolExecutor
    from ssbot.core.forum import FORUM_TYPES
    from ssbot.tools.forum_aim import FORUM_DIR, _low_priority
    from functools import partial
    paths = sorted(glob.glob(str(Path(a.dev) / "*.npz")))
    if a.limit:
        paths = paths[:a.limit]
    body = body_hulls() if getattr(a, "body", False) else None
    folds: list[dict] = [{}, {}]
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_low_priority) as ex:
        for i, got in enumerate(ex.map(partial(_fight_reach_all, body=body), paths, chunksize=1)):
            acc = folds[i % 2]
            for key, (B, N) in got.items():
                r = acc.get(key)
                acc[key] = [B, N] if r is None else [merge_boxes(r[0], B), r[1] + N]
            if (i + 1) % 20 == 0:
                print(f"{i + 1} / {len(paths)}", flush=True)
    fam_of = fam_of_states()
    allB, allN = {}, {}
    for acc in folds:
        for key, (B, N) in acc.items():
            if key in allB:
                allB[key], allN[key] = merge_boxes(allB[key], B), allN[key] + N
            else:
                allB[key], allN[key] = B.copy(), N.copy()
    skip = unclipped_states()
    r: dict = {}
    worst: dict = {}
    for f in (0, 1):
        train = ClipTable({k: v[0] for k, v in folds[1 - f].items()}, {k: v[1] for k, v in folds[1 - f].items()},
                          fam_of)
        for (tk, st), (B, N) in folds[f].items():
            if (tk, st) in skip or tk not in FORUM_TYPES:
                continue
            for part in (0, 1):
                ex_ = np.zeros(CLIP_KMAX + 1)
                for t in range(NT):
                    ok = N[t, part] > 0
                    if not ok.any():
                        continue
                    tb = train.boxes(tk, st, t, part)
                    b = B[t, part]
                    e = np.zeros(CLIP_KMAX + 1)
                    e[ok] = np.maximum.reduce([tb[ok, 0] - b[ok, 0], b[ok, 1] - tb[ok, 1], tb[ok, 2] - b[ok, 2],
                                               b[ok, 3] - tb[ok, 3], np.zeros(int(ok.sum()))])
                    e[~np.isfinite(e)] = 0.0
                    ex_ = np.maximum(ex_, e)
                    lo = 0
                    for band in CLIP_BANDS:
                        k1 = (tk, st, t, part, band)
                        r[k1] = max(r.get(k1, 0.0), float(e[lo:band + 1].max()))
                        lo = band + 1
                lo = 0
                for band in CLIP_BANDS:
                    v = float(ex_[lo:band + 1].max())
                    k1 = (tk, st, NT, part, band)
                    r[k1] = max(r.get(k1, 0.0), v)
                    k2 = (tk, "*", NT, part, band)
                    if v > r.get(k2, 0.0):
                        r[k2] = v
                        worst[f"{tk}|{PARTS[part]}|{band}"] = [st, int(lo + int(np.argmax(ex_[lo:band + 1]))),
                                                               round(v, 3), f]
                    lo = band + 1
    r = {k: float(np.ceil(v * 20.0) / 20.0) for k, v in r.items()}
    out = Path(a.out) if a.out else FORUM_DIR / (BODY_FILE if body is not None else CLIP_FILE)
    save_clip(out, allB, allN, fam_of, r)
    rep = {"desc": cmd_clip_build.__doc__.split("\n")[0], "fights": len(paths), "dev": str(a.dev),
           "what": "body hull (SSBOT_FORUM_BODYCLIP)" if body is not None else "threat colliders (SSBOT_FORUM_RCLIP)",
           "kmax": CLIP_KMAX, "min_rows": CLIP_MIN_ROWS, "tau_bins": NT, "kb_free_f": CLIP_KB_F,
           "bands": list(CLIP_BANDS), "states": len(allB),
           "r_type": {f"{k[0]}|{PARTS[k[3]]}|{k[4]}": v for k, v in sorted(r.items(), key=str) if k[1] == "*"},
           "r_worst": worst,
           "r_state": {f"{k[0]}|{k[1]}|{PARTS[k[3]]}|{k[4]}": v for k, v in sorted(r.items(), key=str)
                       if k[1] != "*" and k[2] == NT},
           "rows": {f"{tk}|{st}": int(n[NT, 0].sum()) for (tk, st), n in sorted(allN.items(), key=str)}}
    out.with_suffix(".json").write_text(json.dumps(rep, indent=1), "utf-8")
    print(f"{len(allB)} states -> {out}; r (type, all / nohit): {rep['r_type']}")
    return 0


# ------------------------------------------------------------------------------------------------ the scan

MIN_ROWS = 30           # a state with fewer recorded rows takes its family's (then its type's) reach
TOL_U = 1.0             # beyond the real reach by more than this (u)


class Reach:
    """The real reach table (cmd_reach) by state, family (union of its states) and type (union of all)."""

    def __init__(self, path: Path = OUT / "reach.json"):
        from ssbot.core.forum import FORUM_TYPES
        from ssbot.tools.forum_aim import FORUM_DIR
        d = json.loads(Path(path).read_text("utf-8"))["types"]
        self.st: dict = {}
        for tk, sts in d.items():
            for st, parts in sts.items():
                for part, arr in parts.items():
                    for k, v in enumerate(arr):
                        if v is not None:
                            self.st[(tk, st, k, part)] = v
        self.fam_of: dict = {}
        for tk, sp in FORUM_TYPES.items():
            p = FORUM_DIR / f"{sp.enemy}.json"
            if not p.exists():
                continue
            for fam, a in json.loads(p.read_text("utf-8"))["attacks"].items():
                for s in a.get("states") or ():
                    self.fam_of.setdefault((tk, s), fam)
        self.fam: dict = {}
        self.typ: dict = {}
        for (tk, st, k, part), v in self.st.items():
            for key, acc in (((tk, self.fam_of.get((tk, st)), k, part), self.fam), ((tk, k, part), self.typ)):
                r = acc.get(key)
                acc[key] = list(v) if r is None else [min(r[0], v[0]), max(r[1], v[1]), min(r[2], v[2]),
                                                      max(r[3], v[3]), r[4] + v[4]]

    @staticmethod
    def _union(acc: dict, keys) -> list | None:
        out = None
        for key in keys:
            v = acc.get(key)
            if v is None:
                continue
            out = list(v) if out is None else [min(out[0], v[0]), max(out[1], v[1]), min(out[2], v[2]),
                                               max(out[3], v[3]), out[4] + v[4]]
        return out

    def box(self, tk: str, state: str | None, k: int, part: str = "all", level: str = "state"):
        """(u0, u1, v0, v1, level used) or None: the union over k - K_SLACK .. k + K_SLACK."""
        kk = range(max(0, k - K_SLACK), k + K_SLACK + 1)
        if level == "state":
            v = self._union(self.st, [(tk, state, x, part) for x in kk])
            if v is not None and v[4] >= MIN_ROWS:
                return (*v[:4], "state")
        fam = self.fam_of.get((tk, state))
        if level in ("state", "family") and fam is not None:
            v = self._union(self.fam, [(tk, fam, x, part) for x in kk])
            if v is not None and v[4] >= MIN_ROWS:
                return (*v[:4], "family")
        v = self._union(self.typ, [(tk, x, part) for x in kk])
        return None if v is None else (*v[:4], "type")


def beyond(mask: np.ndarray, grid, pos, facing: int, rb, tol: float = TOL_U) -> tuple[np.ndarray, np.ndarray]:
    """(cells of mask farther than tol outside the reach box, their Chebyshev distance to it) on the hero-centre grid:
    the reach box (u0, u1, v0, v1) relative to pos (x by facing), grown by the hero half extents."""
    hx, hy = grid.half
    u0, u1, v0, v1 = rb[:4]
    x0, x1 = (pos[0] + u0, pos[0] + u1) if facing >= 0 else (pos[0] - u1, pos[0] - u0)
    x0, x1, y0, y1 = x0 - hx, x1 + hx, pos[1] + v0 - hy, pos[1] + v1 + hy
    dx = np.maximum(np.maximum(x0 - grid.xs, grid.xs - x1), 0.0)[None, :]
    dy = np.maximum(np.maximum(y0 - grid.ys, grid.ys - y1), 0.0)[:, None]
    d = np.maximum(dx, dy)
    return mask & (d > tol), d


def owner_groups(fcast, iid: int) -> list[tuple[tuple, str, np.ndarray]]:
    """[((layer, family, state key, kind), kind, selection)] of one owner's placements (forum_layer_audit classify's
    layers, split by the template key's state)."""
    from ssbot.tools.forum_layer_audit import _key_name, classify
    store = fcast.fc.tables.store
    out = []
    for (lay, _tk, fam), kind, sel in classify(fcast):
        meta = {"pm": fcast.pm, "wm": fcast.wm, "bb": fcast.bb}[kind]
        tids = {"pm": fcast.P.tid, "wm": fcast.W.tid, "bb": fcast.bb["tid"]}[kind]
        mine = sel & (np.asarray(meta["owner"]) == iid)
        by: dict = {}
        for i in np.flatnonzero(mine):
            parts = _key_name(store, tids[i]).split("/")
            st = parts[2] if len(parts) >= 4 else ("<family>" if len(parts) == 3 else "?")
            by.setdefault(st, []).append(int(i))
        for st, idx in by.items():
            s2 = np.zeros(len(sel), bool)
            s2[idx] = True
            out.append(((lay, fam, st, kind), kind, s2))
    return out


def scan_frame(eng, fcast, reach: Reach, ks, hero, attribute: bool = True) -> list[dict]:
    """Per named enemy in play: its own support at each k against its real reach (state level, all rows; also
    the family level and the no-hit rows), and the placements that reach beyond it."""
    g = eng.grid
    sb = eng.support_by(ks, fcast)
    out = []
    tk_ = np.asarray(ks, np.float64) * FT
    F = len(ks)
    cx = cy = None
    for iid, name, st, pos, _col in eng.enemies():
        tr = eng.pol.fc.trackers[iid]
        facing = 1 if getattr(tr, "flip", 0) else -1
        rec = {"iid": iid, "name": name, "type": tr.tk, "state": st, "pos": [round(pos[0], 2), round(pos[1], 2)],
               "fam": tr.cur.family if tr.cur is not None else None, "k": {}}
        any_b = False
        for j, k in enumerate(ks):
            m = sb.get(k, {}).get(iid)
            if m is None or not m.any():
                continue
            r = {"cells": int(m.sum())}
            for lvl, part in (("state", "all"), ("family", "all"), ("state", "nohit")):
                rb = reach.box(tr.tk, st, k, part, lvl)
                if rb is None:
                    continue
                b, d = beyond(m, g, pos, facing, rb)
                tag = f"{lvl}_{part}"
                r[tag] = {"level": rb[4], "beyond": int(b.sum()), "excess": round(float(d[m].max()), 2)}
                if hero is not None:
                    hc = int(round((hero[0] - g.x0) / g.cell)), int(round((hero[1] - g.y0) / g.cell))
                    if 0 <= hc[0] < g.nx and 0 <= hc[1] < g.ny and m[hc[1], hc[0]]:
                        r[tag]["hero_d"] = round(float(d[hc[1], hc[0]]), 2)
            sa = r.get("state_all")
            if sa is not None and sa["beyond"] > 0:
                any_b = True
                if attribute:
                    if cx is None:
                        cx = np.ascontiguousarray(np.repeat(g.gx, F, axis=1))
                        cy = np.ascontiguousarray(np.repeat(g.gy, F, axis=1))
                    rb = reach.box(tr.tk, st, k, "all", "state")
                    hc = None
                    if hero is not None:
                        hc = int(round((hero[0] - g.x0) / g.cell)), int(round((hero[1] - g.y0) / g.cell))
                        if not (0 <= hc[0] < g.nx and 0 <= hc[1] < g.ny):
                            hc = None
                    causes = []
                    fn = {"pm": fcast._fine_occ, "wm": fcast._win_occ, "bb": fcast._bbox_occ}
                    for key, kind, sel in owner_groups(fcast, iid):
                        o = fn[kind](cx, cy, tk_, sel)[:, j].reshape(g.shape) & g.inside
                        if not o.any():
                            continue
                        b, d = beyond(o, g, pos, facing, rb)
                        if b.any():
                            causes.append(["/".join(map(str, key)), int(b.sum()), round(float(d[o].max()), 2),
                                           bool(hc is not None and b[hc[1], hc[0]])])
                    for kind in sorted({b_[1] for b_ in fcast.boxes if int(b_[0]) == iid}):
                        o = fcast._box_occ(cx, cy, tk_, kinds=(kind,), only={iid})[:, j].reshape(g.shape) & g.inside
                        if o.any():
                            b, d = beyond(o, g, pos, facing, rb)
                            if b.any():
                                causes.append([f"box/{kind}", int(b.sum()), round(float(d[o].max()), 2),
                                               bool(hc is not None and b[hc[1], hc[0]])])
                    r["causes"] = sorted(causes, key=lambda c: -c[1])
            rec["k"][k] = r
        rec["beyond"] = any_b
        out.append(rec)
    return out


def cmd_scan(a) -> int:
    """Every 'every'-th frame of the jobs (zone_share's: human sessions / bot runs, --w0): per enemy its support at
    k against its real reach (Reach): one JSONL per job with every (frame, enemy)."""
    import time
    from ssbot.tools.zone_overlay import ZoneEngine, battle
    from ssbot.tools.zone_share import _jobs, _states, job_name
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ks = tuple(int(x) for x in a.ks.split(","))
    reach = Reach(Path(a.reach))
    eng = ZoneEngine(crest="Wanderer", threads=a.threads)
    cache = Path(a.demo_cache) if a.demo_cache else None
    for spec in a.specs:
        for job in _jobs(spec, cache):
            name = job_name(job)
            p = out / f"{name}.jsonl"
            if p.exists() and not a.force:
                continue
            t0 = time.perf_counter()
            terrain, states = _states(job)
            crest = (job.get("seg") or {}).get("crest")
            eng.crest = crest if crest in ("Wanderer", "Reaper") else eng.crest
            eng.start(terrain)
            rows = []
            for s in states:
                b = battle(s)
                if a.w0 and b is not None and b.get("started") and (b.get("wave") or 0) >= 1:
                    break
                fed = eng.feed(s)
                if s["f"] % a.every or not fed:
                    continue
                fc = eng.forecast()
                if fc is None:
                    continue
                hero = eng.hero(s)
                ens = scan_frame(eng, fc, reach, ks, hero, attribute=not a.no_attr)
                rows.append({"f": int(s["_f_raw"]), "gf": int(s["f"]), "wave": (b or {}).get("wave"),
                             "hero": None if hero is None else [round(hero[0], 2), round(hero[1], 2)],
                             "enemies": ens})
            p.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
            nb = sum(1 for r in rows if any(e["beyond"] for e in r["enemies"]))
            print(f"{name}: {len(rows)} frames, {nb} with an enemy beyond its reach ({time.perf_counter() - t0:.0f} s)",
                  flush=True)
    return 0


def summarize_scan(d: Path) -> dict:
    """Frames / enemy-frames beyond the real reach (state level, all rows; > TOL_U), by group (human / bot), type,
    layer and cause (the placement group with the most beyond cells), and the hero-covered-but-beyond count."""
    from collections import Counter, defaultdict
    res: dict = {}
    for p in sorted(Path(d).glob("*.jsonl")):
        grp = "human" if p.name[:8].isdigit() and "_Forum_" not in p.name else "bot"
        g = res.setdefault(grp, {"frames": 0, "enemy_frames": 0, "by_k": defaultdict(Counter)})
        for x in p.read_text("utf-8").splitlines():
            if not x.strip():
                continue
            r = json.loads(x)
            g["frames"] += 1
            fb = defaultdict(bool)
            for e in r["enemies"]:
                g["enemy_frames"] += 1
                for k, kr in e["k"].items():
                    c = g["by_k"][k]
                    c["enemy_frames_with_support"] += 1
                    for tag in ("state_all", "family_all", "state_nohit"):
                        t = kr.get(tag)
                        if t is None:
                            continue
                        if t["beyond"] > 0:
                            c[f"beyond_{tag}"] += 1
                            fb[(k, tag)] = True
                            if t.get("hero_d", 0) > TOL_U:
                                c[f"hero_beyond_{tag}"] += 1
                    t = kr.get("state_all")
                    if t is not None and t["beyond"] > 0:
                        c[f"type|{e['type']}"] += 1
                        c[f"level|{t['level']}"] += 1
                        cs = kr.get("causes") or []
                        if cs:
                            top = cs[0][0]
                            lay, fam = top.split("/")[:2]
                            c[f"layer|{lay}"] += 1
                            c[f"cause|{e['type'][-10:]}|{top}"] += 1
                            for cc in cs:
                                c[f"anylayer|{cc[0].split('/')[0]}"] += 1
                            c["beyond_cells"] += t["beyond"]
                            for cc in cs:
                                if len(cc) > 3 and cc[3]:
                                    c[f"herocause|{e['type'][-10:]}|{cc[0]}"] += 1
                                    c[f"herolayer|{cc[0].split('/')[0]}"] += 1
                                    c[f"herotype|{e['type']}"] += 1
            for (k, tag), v in fb.items():
                if v:
                    g["by_k"][k][f"frames_beyond_{tag}"] += 1
    return {grp: {"frames": g["frames"], "enemy_frames": g["enemy_frames"],
                  "by_k": {k: dict(sorted(c.items(), key=lambda kv: (kv[0].split("|")[0], -kv[1])))
                           for k, c in g["by_k"].items()}} for grp, g in res.items()}


def cmd_scan_summary(a) -> int:
    res = {str(d): summarize_scan(Path(d)) for d in a.dirs}
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), "utf-8")
    for d, r in res.items():
        for grp, g in r.items():
            print(f"{d} [{grp}] {g['frames']} frames, {g['enemy_frames']} enemy-frames")
            for k, c in g["by_k"].items():
                top = [f"{x} {n}" for x, n in c.items() if "|" not in x]
                print(f"  k {k}: " + ", ".join(top))
                for pre in ("type|", "layer|", "cause|", "herotype|", "herolayer|", "herocause|"):
                    items = [(x, n) for x, n in c.items() if x.startswith(pre)][:a.top]
                    print(f"    {pre} " + "; ".join(f"{x[len(pre):]} {n}" for x, n in items))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="support_reach")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("explain")
    e.add_argument("session")
    e.add_argument("--attempt", type=int, default=0)
    e.add_argument("--frame", type=int, required=True)
    e.add_argument("--enemy", required=True)
    e.add_argument("--ks", default="0,12")
    e.add_argument("--out", default=str(OUT / "explain"))
    e.add_argument("--tag", default="")
    e.add_argument("--threads", type=int, default=4)
    e.add_argument("--demo-cache", default=str(DEMO_CACHE))
    m = sub.add_parser("motion")
    m.add_argument("--out", default=str(OUT / "motion.json"))
    m.add_argument("--workers", type=int, default=4)
    m.add_argument("--limit", type=int, default=0)
    r = sub.add_parser("reach")
    r.add_argument("--out", default=str(OUT / "reach.json"))
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--dev-only", action="store_true")
    s = sub.add_parser("scan")
    s.add_argument("specs", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--every", type=int, default=3)
    s.add_argument("--ks", default="0,12")
    s.add_argument("--w0", action="store_true")
    s.add_argument("--reach", default=str(OUT / "reach.json"))
    s.add_argument("--no-attr", action="store_true")
    s.add_argument("--threads", type=int, default=4)
    s.add_argument("--demo-cache", default=str(DEMO_CACHE))
    s.add_argument("--force", action="store_true")
    cb = sub.add_parser("clip-build")
    cb.add_argument("--dev", default=r"C:\ssbot\data\m2_forum_r0\cache")
    cb.add_argument("--out")
    cb.add_argument("--workers", type=int, default=4)
    cb.add_argument("--limit", type=int, default=0)
    cb.add_argument("--body", action="store_true", help="the body hull's reach (SSBOT_FORUM_BODYCLIP: body_reach.npz)")
    q = sub.add_parser("summary")
    q.add_argument("dirs", nargs="+")
    q.add_argument("--json")
    q.add_argument("--top", type=int, default=12)
    a = ap.parse_args(argv)
    return {"explain": cmd_explain, "motion": cmd_motion, "reach": cmd_reach, "scan": cmd_scan,
            "summary": cmd_scan_summary, "clip-build": cmd_clip_build}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
