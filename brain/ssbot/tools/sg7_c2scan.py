"""Task 1v1 SG7 (1): every Clapper slam of a set of recordings, per frame, with what the Slam Collider 2 damage rule
needs (forum.md 63): the Clapper's Control state, the enabled Slam Collider 1 / 2 boxes and their polygons (world vertices: they are PolygonCollider2Ds, the box is only
their bounding box), the root box, the hero's
physics box (STATE hero.box), its cstate bools that decide the real HeroBox shape (HeroBox.cs), the downspike
i-frame counter (cstate_int downspikeInvulnerabilitySteps, decremented in HeroController.FixedUpdate), the
invulnerable / recoiling flags, the hero clip, and the events: the hero's hits on this Clapper, every TakeDamage
attempt that got past the oracle's gate ("damage": source), the blocked ones ("damage_blocked": source, why, n,
first_f, last_f) and the hp losses (source).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sg7_c2scan <recordings / run dirs> [--glob BASE PATTERN] \
        --out C:/ssbot/data/m2_map/sg7/c2/slams_<tag>.jsonl

Read-only on the recordings. One JSON line per slam: rec, iid, f0, frames [...] (frames from the antic entry to 40
frames after the slam family ends, so a late Collider 2 / body contact is kept).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CLAPPER = "Song Heavy Sentry"
SLAM = ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2", "Slam Recover")
HAMMER = ("Slam Collider 1", "Slam Collider 2")
TAIL_F = 40
# cstate bool indices (docs/facts/1.0.30000/cstate_schema.json "bools")
CS = {"onGround": 1, "shadowDashing": 8, "dashing": 11, "isSprinting": 12, "airDashing": 15, "wallSliding": 20,
      "wallClinging": 21, "attacking": 24, "downAttacking": 33, "downSpiking": 36, "downSpikeBouncing": 37,
      "downSpikeRecovery": 39, "bouncing": 40, "recoiling": 51, "invulnerable": 52, "parrying": 71, "evading": 87}
DS_INT = 1                          # cstate_int index of downspikeInvulnerabilitySteps


def _box(vs):
    if not vs:
        return None
    xs, ys = vs[0::2], vs[1::2]
    return [round(min(xs), 4), round(max(xs), 4), round(min(ys), 4), round(max(ys), 4)]


def _control(e: dict):
    for m in e.get("fsms") or ():
        if m.get("name") == "Control":
            return m.get("state"), float(m.get("t") or 0.0)
    return None, 0.0


def _bits(cs) -> int:
    if not cs:
        return 0
    out = 0
    for n, i in CS.items():
        if (cs[i >> 6] >> (i & 63)) & 1:
            out |= 1 << list(CS).index(n)
    return out


def hero_row(s: dict) -> dict:
    h = s.get("hero") or {}
    ci = h.get("cstate_int") or []
    evs = []
    for ev in s.get("ev") or ():
        k = ev.get("k")
        d = ev.get("d") or {}
        if k == "hit":
            evs.append(["hit", d.get("ent"), d.get("type_key"), d.get("src"), d.get("dealt")])
        elif k == "damage":
            evs.append(["damage", d.get("source"), d.get("amount"), d.get("hazard")])
        elif k == "damage_blocked":
            evs.append(["blocked", d.get("source"), d.get("why"), d.get("n"), d.get("first_f"), d.get("last_f"),
                        d.get("end")])
        elif k == "hp" and (d.get("delta") or 0) < 0:
            evs.append(["hp", d.get("delta"), d.get("source")])
    return {"f": s["f"], "dt": s.get("dt"), "hb": h.get("box"), "hp_": [round(v, 4) for v in (h.get("pos") or [0, 0])[:2]],
            "hv": [round(v, 3) for v in (h.get("vel") or [0, 0])[:2]], "cs": _bits(h.get("cstate")),
            "ds": ci[DS_INT] if len(ci) > DS_INT else None, "inv": h.get("invulnerable"),
            "clip": (h.get("anim") or {}).get("clip"), "fac": h.get("facing"), "ev": evs}


def clapper_row(e: dict) -> dict:
    st, tin = _control(e)
    root, ham, poly, rkind = None, {}, {}, None
    for c in e.get("colliders") or ():
        nm = c.get("name") or ""
        if c.get("layer") == 11 and nm.startswith(CLAPPER) and root is None and c.get("enabled", True):
            root = _box(c.get("verts_world"))
            rkind = c.get("kind")
            if rkind != "box":
                poly["r"] = [round(v, 3) for v in c.get("verts_world") or ()]
        elif nm.startswith(HAMMER) and "Ally" not in nm and c.get("enabled"):
            key = nm.split(" (")[0][-1]
            ham[key] = _box(c.get("verts_world"))
            poly[key] = [round(v, 3) for v in c.get("verts_world") or ()]
            dm = c.get("damage") or {}
            if dm.get("dealt") != 2 or dm.get("can_cause_damage") is False:
                poly["dm" + key] = [dm.get("dealt"), dm.get("can_cause_damage")]
    return {"st": st, "tin": round(tin, 4), "pos": [round(v, 4) for v in (e.get("pos") or [0, 0])[:2]],
            "flip": bool(e.get("flipX")), "root": root, "rkind": rkind, "ham": ham, "poly": poly, "hpc": e.get("hp")}


def scan(rec: Path) -> list[dict]:
    from ssbot.tools.pogo_outcomes import _states, rec_name
    name = rec_name(rec)
    live: dict = {}
    out = []
    for s in _states(rec):
        if not isinstance(s.get("f"), int):
            continue
        hr = None
        seen = set()
        for e in s.get("ents") or ():
            if e.get("type_key") != CLAPPER or not e.get("pos"):
                continue
            iid = e.get("iid")
            seen.add(iid)
            st, _ = _control(e)
            cur = live.get(iid)
            if cur is not None:
                if st == "Slam Antic" and cur["last_st"] != "Slam Antic":
                    out.append(live.pop(iid))
                    cur = None
                elif st not in SLAM:
                    cur["tail"] += 1
                    if cur["tail"] > TAIL_F or e.get("is_dead"):
                        out.append(live.pop(iid))
                        cur = None
            if cur is None and st == "Slam Antic" and not e.get("is_dead"):
                cur = live[iid] = {"rec": name, "iid": iid, "f0": s["f"], "frames": [], "tail": 0, "last_st": st}
            if cur is not None:
                if hr is None:
                    hr = hero_row(s)
                row = dict(hr)
                row.update(clapper_row(e))
                row["dead"] = bool(e.get("is_dead"))
                cur["frames"].append(row)
                cur["last_st"] = st
        for iid in [k for k in live if k not in seen]:
            out.append(live.pop(iid))
    out += list(live.values())
    for c in out:
        c.pop("tail", None)
        c.pop("last_st", None)
    return out


def main(argv=None) -> int:
    from ssbot.tools.pogo_outcomes import recordings
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--glob", nargs=2, metavar=("BASE", "PATTERN"), action="append", default=[])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    extra = [d for base, pat in a.glob for d in sorted(Path(base).glob(pat)) if d.is_dir()]
    recs = recordings(list(a.paths) + extra)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with a.out.open("w", encoding="utf-8") as fh:
        for rec in recs:
            try:
                sl = scan(rec)
            except Exception as ex:          # a broken recording: report, keep going
                print(rec, "ERROR", repr(ex), flush=True)
                continue
            for c in sl:
                fh.write(json.dumps(c, separators=(",", ":")) + "\n")
            n += len(sl)
            print(rec, len(sl), flush=True)
    print("slams", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
