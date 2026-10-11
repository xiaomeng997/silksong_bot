"""What a Wanderer down slash does when it meets something (task 1v1 T1(b), forum.md 46): every down slash of a
recording (the person's or a probe's), what its box met, whether the hero bounced, how, and what happened to the
enemy and to the hero afterwards.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.pogo_outcomes scan C:/ssbot/data/human/20261011_051105 [...] \
        --out C:/ssbot/data/m2_pogo/human.jsonl
    ../scripts/uv.cmd run python -m ssbot.tools.pogo_outcomes summary C:/ssbot/data/m2_pogo/human.jsonl

A down slash: the hero clip turning DownSlash / DownSlashAlt (the press registers on that frame: input.mask has
down + attack there). The bounce: the clip DownSpikeBounce 1 / 2 within BOUNCE_F frames (HeroController.DownAttack's
hit -> the downspike bounce). What it met: on the frame before the bounce (or, without one, on each frame of the
slash's active window) every enabled collider of a live entity whose box meets the slash box (the union of the
Wanderer DownSlash / DownSlashAlt polygons, both facings: attacks/wanderer.json): the enemy hurtbox (layer 11, the
HealthManager's box), an attack collider (its damage parry bits: TinkEffect / clash), or nothing. The hero's 'hit'
events (src DownSlash*) say which hurtbox took damage. Each row keeps the hero's path, input masks and the nearby
Clappers' Control state transitions from 60 frames before to WIN_F after the press, for the predictor's held-out
check (ssbot.combat.pogo_model) and the slam timing.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, deque
from pathlib import Path

import numpy as np

DS_CLIPS = ("DownSlash", "DownSlashAlt")
BOUNCE_CLIPS = ("DownSpikeBounce 1", "DownSpikeBounce 2")
BOUNCE_F = 16          # frames from the press within which a bounce counts as this slash's
ACTIVE_F = (1, 12)     # frames after the press searched for contacts without a bounce (live active frames 3-9)
WIN_F = 90             # frames kept after the press
PRE_F = 60             # frames of enemy FSM history kept before the press
# the slash box relative to the hero position: the union of DownSlash / DownSlashAlt, both facings (wanderer.json)
SLASH_BOX = (-1.75, 1.75, -2.17, 0.15)
NEAR_U = 9.0           # Clappers within this distance of the hero at the press are followed
BOUNCE_S = 0.45        # game s from the press searched for pogo onsets (vy >= 15)
LOSS_S = 1.0           # game s from the press a health loss counts against the slash
CLAPPER = "Song Heavy Sentry"


def _aabb(vs) -> tuple[float, float, float, float] | None:
    if not vs:
        return None
    a = np.asarray(vs, float).reshape(-1, 2)
    return float(a[:, 0].min()), float(a[:, 0].max()), float(a[:, 1].min()), float(a[:, 1].max())


def _meets(b, x: float, y: float, box=SLASH_BOX) -> bool:
    return b is not None and b[0] < x + box[1] and b[1] > x + box[0] and b[2] < y + box[3] and b[3] > y + box[2]


def _control(e: dict) -> tuple[str | None, float]:
    for m in e.get("fsms") or ():
        if m.get("name") == "Control":
            return m.get("state"), float(m.get("t") or 0.0)
    return None, 0.0


def contacts(s: dict, x: float, y: float, box=SLASH_BOX) -> list[dict]:
    """Every enabled collider of a live entity meeting the slash box at hero (x, y) on frame s."""
    out = []
    for e in s.get("ents") or ():
        if e.get("is_dead") or e.get("hidden"):
            continue
        for c in e.get("colliders") or ():
            if not c.get("enabled") or c.get("layer") == 13:      # 13: the FSMs' range triggers
                continue
            if not _meets(_aabb(c.get("verts_world")), x, y, box):
                continue
            d = c.get("damage") or {}
            st, tin = _control(e)
            out.append({"type": e.get("type_key"), "iid": e.get("iid"), "cat": e.get("category"), "name": c.get("name"),
                        "layer": c.get("layer"), "parry": d.get("parry") if d else None,
                        "dmg": d.get("dealt") if d else None, "hm": bool((e.get("src") or 0) & 1),
                        "state": st, "t": round(tin, 3), "pos": e.get("pos")[:2] if e.get("pos") else None})
    return out


def _hero(s: dict) -> dict:
    h = s.get("hero") or {}
    return {"f": s["f"], "pos": (h.get("pos") or [0, 0])[:2], "vel": h.get("vel"), "clip": (h.get("anim") or {}).get("clip"),
            "facing": h.get("facing"), "cs": h.get("cstate"), "inv": h.get("invulnerable"), "hp": h.get("health"),
            "mask": (s.get("input") or {}).get("mask", 0), "act": (s.get("act") or {}).get("mask", 0), "dt": s.get("dt")}


def analyse(buf: list[dict], i0: int, session: str) -> dict:
    """One down slash pressed at buf[i0] (frames before / after it in buf)."""
    s0 = buf[i0]
    f0 = s0["f"]
    pre = buf[i0 - 1] if i0 > 0 else s0
    h0 = _hero(pre)
    clip0 = _hero(s0)["clip"]
    post = [s for s in buf[i0:] if s["f"] <= f0 + WIN_F]
    hero = [_hero(s) for s in buf[max(i0 - 3, 0):] if s["f"] <= f0 + WIN_F]
    fb = next((s["f"] for s in post[1:] if s["f"] <= f0 + BOUNCE_F and _hero(s)["clip"] in BOUNCE_CLIPS
               and _hero(buf[buf.index(s) - 1])["clip"] not in BOUNCE_CLIPS), None)
    hits, dmg, blk, frz = [], [], [], []
    for s in post:
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "hit" and str(d.get("src", "")).startswith("DownSlash") and s["f"] <= f0 + BOUNCE_F:
                hits.append({"f": s["f"], "type": d.get("type_key"), "ent": d.get("ent"), "dealt": d.get("dealt"),
                             "hp_after": d.get("hp_after")})
            elif k == "damage":
                dmg.append({"f": s["f"], "source": d.get("source"), "inv": d.get("invuln")})
            elif k == "damage_blocked":
                blk.append({"f": s["f"], "source": d.get("source"), "why": d.get("why"), "first_f": d.get("first_f")})
            elif k == "freeze" and d.get("phase") == "start" and s["f"] <= f0 + BOUNCE_F + 4:
                frz.append({"f": s["f"], "type": d.get("type")})
    # contacts: on the frame before the bounce (the overlap that caused it), else every active frame
    con = []
    by_f = {s["f"]: s for s in post}
    if fb is not None:
        for g in (fb - 1, fb - 2):
            s = by_f.get(g)
            if s is not None:
                hx, hy = _hero(s)["pos"]
                con = contacts(s, hx, hy)
                if con:
                    break
    else:
        seen = set()
        for g in range(f0 + ACTIVE_F[0], f0 + ACTIVE_F[1] + 1):
            s = by_f.get(g)
            if s is None:
                continue
            hx, hy = _hero(s)["pos"]
            for c in contacts(s, hx, hy):
                key = (c["iid"], c["name"])
                if key not in seen:
                    seen.add(key)
                    con.append(c | {"f": g})
    # the Clappers near the press: their Control transitions around it
    hx0, hy0 = h0["pos"]
    near = [e for e in s0.get("ents") or () if e.get("type_key") == CLAPPER and not e.get("is_dead")
            and e.get("pos") and abs(e["pos"][0] - hx0) <= NEAR_U]
    claps = []
    for e in near:
        iid = e.get("iid")
        tr = []
        for s in buf:
            if s["f"] < f0 - PRE_F or s["f"] > f0 + WIN_F:
                continue
            for ev in s.get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "fsm" and d.get("iid") == iid and d.get("fsm") == "Control":
                    tr.append((s["f"], d.get("from"), d.get("to")))
        path = [(s["f"], [round(v, 3) for v in (next((x for x in s.get("ents") or () if x.get("iid") == iid), {})
                                                   .get("pos") or [0, 0])[:2]])
                for s in post[::3]]
        st, tin = _control(e)
        claps.append({"iid": iid, "state": st, "t": round(tin, 3), "pos": e["pos"][:2], "flipX": e.get("flipX"),
                      "fsm": tr, "path": path})
    # game time from the press (human sessions run at 0.5x: dt 1/120), the pogo by velocity (the bounce sets vy -10
    # for a step on the contact, then the pogo vy 17.4: kinematics EV_POGO), every rising onset within BOUNCE_S
    # (a second one: the same slash meeting something else), the masks lost within LOSS_S (the 'damage' events
    # include hits the downspike i-frames then drop: health is the truth)
    t, ts = 0.0, {}
    for s in post:
        ts[s["f"]] = t
        t += float(s.get("dt") or 0.0)
    ups, prev_vy = [], None
    for s in post[1:]:
        if ts[s["f"]] > BOUNCE_S:
            break
        vy = float(((s.get("hero") or {}).get("vel") or [0, 0])[1])
        if vy >= 15.0 and (prev_vy is None or prev_vy < 15.0):
            ups.append(s["f"])
        prev_vy = vy
    contact_f = []
    for u in ups:
        g = u
        for s in reversed([x for x in post if x["f"] < u]):
            if abs(float(((s.get("hero") or {}).get("vel") or [0, 0])[1]) + 10.0) < 0.05:
                g = s["f"]
            else:
                break
        contact_f.append(g)
    hp0 = (pre.get("hero") or {}).get("health")
    loss_f, loss_src = None, None
    for s in post:
        if ts[s["f"]] > LOSS_S:
            break
        hp = (s.get("hero") or {}).get("health")
        if hp0 is not None and hp is not None and hp < hp0:
            loss_f = s["f"]
            loss_src = next((ev.get("d", {}).get("source") for x in post if loss_f - 3 <= x["f"] <= loss_f
                             for ev in x.get("ev") or () if ev.get("k") == "hp" and (ev.get("d") or {}).get("delta", 0) < 0),
                            None)
            break
    return {"session": session, "f0": f0, "clip": clip0, "hero0": h0, "bounce_f": fb, "hits": hits, "contacts": con,
            "freeze": frz, "damage": dmg, "blocked": blk, "clappers": claps, "hero": hero,
            "up_f": ups, "contact_f": contact_f, "t_of": {str(k): round(v, 4) for k, v in ts.items()},
            "hp0": hp0, "loss_f": loss_f, "loss_t": None if loss_f is None else round(ts[loss_f], 4), "loss_src": loss_src}


def recordings(paths: list[Path]) -> list[Path]:
    """Human sessions (state.raw.zst), Recorder recordings (state.msgpack.zst) and run directories (rec/**)."""
    out = []
    for p in paths:
        if (p / "state.raw.zst").exists() or (p / "state.msgpack.zst").exists():
            out.append(p)
        else:
            out += sorted(q.parent for q in p.glob("rec/**/state.msgpack.zst"))
    return out


def rec_name(rec: Path) -> str:
    """A recording's id in the rows: the human session's name, else <run dir or probe dir>/<recording>."""
    if (rec / "state.raw.zst").exists():
        return rec.name
    up = rec.parents[3] if rec.parents[2].name == "rec" else rec.parents[2]
    return f"{up.name}/{rec.name}"


def _states(rec: Path):
    if (rec / "state.raw.zst").exists():
        from ssbot.tools.raw_session import states
        return states(rec)
    from ssbot.record.recorder import RecordingReader
    return RecordingReader(rec).states(0, 10 ** 9)


def scan(session: Path) -> list[dict]:
    buf: deque = deque()
    pending: list[int] = []        # press frames waiting for their window
    rows = []
    prev_clip = None
    name = rec_name(session)
    for s in _states(session):
        buf.append(s)
        c = ((s.get("hero") or {}).get("anim") or {}).get("clip")
        if c in DS_CLIPS and prev_clip not in DS_CLIPS:
            pending.append(s["f"])
        prev_clip = c
        while pending and s["f"] >= pending[0] + WIN_F:
            f0 = pending.pop(0)
            lst = list(buf)
            i0 = next(i for i, x in enumerate(lst) if x["f"] == f0)
            rows.append(analyse(lst, i0, name))
        lo = (pending[0] if pending else s["f"]) - PRE_F - 4
        while buf and buf[0]["f"] < lo:
            buf.popleft()
    for f0 in pending:
        lst = list(buf)
        i0 = next(i for i, x in enumerate(lst) if x["f"] == f0)
        rows.append(analyse(lst, i0, name))
    return rows


def category(r: dict) -> str:
    """hurtbox:<type> (a 'hit' of this slash), attack:<type>/<collider> (a bounce with an attack collider met and no
    hit), other (a bounce with neither), miss:<what it met or nothing> (no bounce)."""
    if r["bounce_f"] is not None:
        if r["hits"]:
            return f"hurtbox:{r['hits'][0]['type']}"
        att = [c for c in r["contacts"] if c["parry"] is not None and c["layer"] != 11]
        if att:
            return f"attack:{att[0]['type']}/{att[0]['name']}"
        hb = [c for c in r["contacts"] if c["layer"] == 11]
        if hb:
            return f"body_nohit:{hb[0]['type']}"
        return "bounce_other:" + ",".join(sorted({str(c['name']) for c in r["contacts"]}))[:60]
    if r["hits"]:
        return f"hit_nobounce:{r['hits'][0]['type']}"
    met = sorted({f"{c['type']}/{c['name']}" for c in r["contacts"] if c["layer"] != 11})
    return "miss:" + (",".join(met)[:80] if met else "nothing")


def summary(rows: list[dict]) -> dict:
    cats = Counter(category(r) for r in rows)
    out = {"n": len(rows), "bounces": sum(r["bounce_f"] is not None for r in rows), "categories": dict(cats.most_common())}
    lat = Counter(r["bounce_f"] - r["f0"] for r in rows if r["bounce_f"] is not None)
    out["bounce_frame_after_press"] = dict(sorted(lat.items()))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("scan")
    a1.add_argument("sessions", nargs="*", type=Path)
    a1.add_argument("--glob", nargs=2, metavar=("BASE", "PATTERN"), action="append", default=[],
                    help="also every directory BASE/PATTERN (a long run list)")
    a1.add_argument("--out", type=Path, required=True)
    a2 = sub.add_parser("summary")
    a2.add_argument("jsonl", nargs="+", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "scan":
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8") as fo:
            extra = [d for base, pat in a.glob for d in sorted(Path(base).glob(pat)) if d.is_dir()]
            for ses in recordings(list(a.sessions) + extra):
                rows = scan(ses)
                for r in rows:
                    fo.write(json.dumps(r) + "\n")
                print(ses.name, len(rows), json.dumps(summary(rows))[:400], flush=True)
        return 0
    rows = [json.loads(x) for p in a.jsonl for x in p.read_text("utf-8").splitlines() if x.strip()]
    print(json.dumps(summary(rows), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
