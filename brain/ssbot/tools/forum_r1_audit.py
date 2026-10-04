"""What the Forum R1 targeted collection logged (Forum plan R1 items 2-3, docs/plans/forum_planner_plan.md), from a
combat_run's recordings and AttemptRecords (policy data2 / data2_envoy, ssbot.train.forum_policy):

  families     attack-family starts per enemy type (FORUM_SPECS attack-start states on the "fsm" events), per hour of
               game time, by episode unit (wave start); hero |dx| at each start, and how many starts fell within 1 u of
               the family's choice boundary (boundaries.json of R0, or the built-in copy)
  never_seen   Envoy "Hop Up?" -> next state (a hop slash needs the "HOP UP" ray, which comes after a FINISHED the
               state sends itself), with the Envoy's distance to the wall on the hero's side; Bellbearer "Rethrow?" ->
               next; Maestro "Attack Choice" -> next
  clashes      freeze NailClashEffect: the nearest in-play enemy and its current family; Throwing Bell nail hits
               ("Nail Hit" / "Tink" states); the policy's clash swings by owner type
  clawline     hero damage while a Harpoon clip plays (and 0.25 s after), harpoon hits on enemies
  under        game seconds grounded right under a flier (|dx| < 0.75, body bottom >= 1.5 u above the hero's
               transform) and hero hits from fliers there, against the same near a flier but not under (1.5-6 u)
  pocket       game seconds at the left-wall top (transform x < 14.6, y >= 13.2) and the Choir Clappers' attack
               starts meanwhile
  climbs       the policy's CLIMB segments: tries, reached the top, game seconds to the top

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_r1_audit C:/ssbot/data/runs/m2/<run> [...] --json out.json
"""
import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from ssbot.knowledge.behaviour_tables import fight_states, run_fights
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
from ssbot.train.forum_policy import load_boundaries
from ssbot.train.gauntlet import in_play
from ssbot.train.wave_start import PARKED_STATES, body_box

POCKET_X, POCKET_Y = 14.6, 13.2
WALLS = (14.01, 48.99)
UNDER_DX, UNDER_DY, NEAR_DX = 0.75, 1.5, 6.0
HARPOON_TAIL_S = 0.25
BELL_NAIL_STATES = ("Nail Hit", "Tink L", "Tink R", "Tink U")
# the decision states in front of the never-seen moves (13.2 of forum.md): Envoy hop slash, Bellbearer quick rethrow,
# Maestro point
WATCH = frozenset((("Song Pilgrim 01", "Hop Up?"), ("Pilgrim 03 Song", "Rethrow?"),
                   ("Song Pilgrim Maestro", "Attack Choice")))
SOURCE_OWNER = {"Throwing Bell": "Pilgrim 03 Song", "Song Reed Pin Projectile": "Song Reed",
                "Spear": "Song Handmaiden", "handmaiden_spear_silk_explosion": "Song Handmaiden"}


def family_tables() -> tuple[dict, dict]:
    """{(type, fsm): {state: family}} for attack starts and {type: control fsm}."""
    starts, ctl = {}, {}
    for tk, s in FORUM_SPECS.items():
        starts[(tk, s.control_fsm)] = dict(s.attack_starts)
        ctl[tk] = s.control_fsm
    return starts, ctl


def source_type(src: str | None, live_types: set[str]) -> str | None:
    """The enemy type a hero damage source names (path "<parent>/<child>" or a projectile), when known."""
    if not src:
        return None
    for part in str(src).replace("(Clone)", "").split("/"):
        p = part.strip()
        base = p.rsplit(" (", 1)[0] if p.endswith(")") else p
        if base in FORUM_SPECS:
            return base
        if base in SOURCE_OWNER:
            return SOURCE_OWNER[base]
    return None


def scan_fight(fight, unit: str, acc: dict, starts: dict, bounds: dict) -> None:
    last_fam: dict[int, tuple[str, int]] = {}
    pend_next: dict[int, tuple[str, dict]] = {}       # ent -> (state, info) waiting for the next transition
    prev = None
    harpoon_until = -1.0
    harpooned: list[tuple[float, str]] = []           # (game s, type) of the enemies the harpoon hit
    g = 0.0
    for s in fight_states(fight, keys=("f", "dt", "hero", "ents", "ev")):
        f = s["f"]
        dt = float(s.get("dt") or 0.0)
        g += dt
        h = s.get("hero") or {}
        if not h.get("pos"):
            continue
        hx, hy = h["pos"][0], h["pos"][1]
        ents = s.get("ents") or ()
        by_iid = {e["iid"]: e for e in ents}
        live = [e for e in ents if e.get("type_key") in FORUM_SPECS and (e.get("hp") or 0) > 0 and in_play(e)
                and not any(fs.get("state") in PARKED_STATES for fs in e.get("fsms") or ())]
        clip = str(((h.get("anim") or {}).get("clip")) or "")
        if clip.startswith("Harpoon"):
            harpoon_until = g + HARPOON_TAIL_S
            acc["clawline"]["harpoon_s"] += dt
        # under / near a flier
        grounded = abs((h.get("vel") or [0, 0])[1]) < 1e-3 and hy < 5.0
        fl = []
        for e in live:
            x0, y0, x1, y1 = body_box(e)
            if y0 >= hy + UNDER_DY:
                fl.append((abs((x0 + x1) / 2.0 - hx), e.get("type_key")))
        under_t = {t for d, t in fl if d < UNDER_DX} if grounded else set()
        near_t = {t for d, t in fl if UNDER_DX * 2 <= d < NEAR_DX} - under_t if grounded else set()
        under, near = bool(under_t), bool(near_t)
        if under:
            acc["under"]["under_s"] += dt
        elif near:
            acc["under"]["near_s"] += dt
        for t in under_t:
            acc["under_by_type"][t]["under_s"] += dt
        for t in near_t:
            acc["under_by_type"][t]["near_s"] += dt
        pocket = hx < POCKET_X and hy >= POCKET_Y
        if pocket:
            acc["pocket"]["pocket_s"] += dt
            acc["pocket"]["by_unit_s"][unit] += dt
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "fsm":
                ent = d.get("ent")
                e = by_iid.get(ent)
                tk = (e or {}).get("type_key") or str(d.get("obj", "")).rsplit(" (", 1)[0]
                to = d.get("to")
                if ent in pend_next and d.get("fsm") == pend_next[ent][1].get("fsm") and to != pend_next[ent][0]:
                    st0, info = pend_next.pop(ent)
                    acc["never_seen"][st0][to or "None"] += 1
                    if d.get("from") == st0 and d.get("t_in_prev") is not None:
                        acc["never_seen_dwell_max"][st0] = max(acc["never_seen_dwell_max"].get(st0, 0.0),
                                                                float(d["t_in_prev"]))
                    if st0 == "Hop Up?":
                        acc["hop_up"].append({**info, "next": to})
                fam = starts.get((tk, d.get("fsm")), {}).get(to)
                if fam and e is not None:
                    x0, y0, x1, y1 = body_box(e)
                    dxh = abs((x0 + x1) / 2.0 - hx)
                    acc["families"][unit][f"{tk}/{fam}"] += 1
                    acc["families_all"][f"{tk}/{fam}"] += 1
                    last_fam[ent] = (fam, f)
                    b = bounds.get(tk, {}).get(fam)
                    if b and abs(dxh - b[1]) <= 1.0:
                        acc["near_boundary"][f"{tk}/{fam}"] += 1
                    if pocket and tk == "Song Heavy Sentry":
                        acc["pocket"]["clapper_starts"][fam] += 1
                        acc["pocket"]["clapper_from"][f"{fam} <- {d.get('from')}"] += 1
                if (tk, to) in WATCH and e is not None:
                    info = {"fsm": d.get("fsm"), "f": f}
                    if to == "Hop Up?":
                        ex = e["pos"][0]
                        wall = WALLS[0] if hx < ex else WALLS[1]
                        info.update(envoy_x=round(ex, 2), hero_x=round(hx, 2), wall_gap=round(abs(ex - wall), 2))
                    pend_next[ent] = (to, info)     # keyed by state name below; WATCH names one type each
                if tk == "Throwing Bell" and to in BELL_NAIL_STATES:
                    acc["clashes"]["bell_nail"][to] += 1
            elif k == "freeze" and d.get("phase") == "start" and d.get("type") == "NailClashEffect":
                src = prev or s
                cand = []
                for e in src.get("ents") or ():
                    for c in e.get("colliders") or ():
                        dm = c.get("damage") or {}
                        if c.get("enabled") and dm.get("parryable"):
                            v = c.get("verts_world") or ()
                            if v:
                                dx = max(min(v[0::2]) - hx, hx - max(v[0::2]), 0.0)
                                dy = max(min(v[1::2]) - hy, hy - max(v[1::2]), 0.0)
                                cand.append((dx + dy, e))
                if cand:
                    _, e = min(cand, key=lambda t: t[0])
                    owner = e.get("type_key")
                    fam = last_fam.get(e["iid"], ("?", 0))
                    fam_name = fam[0] if f - fam[1] < 240 else "IDLE"
                    acc["clashes"]["nail_clash"][f"{owner}/{fam_name}"] += 1
                else:
                    acc["clashes"]["nail_clash"]["?"] += 1
            elif k == "damage":
                src = d.get("source")
                tk = source_type(src, set())
                if g <= harpoon_until:
                    hooked = [t for gg, t in harpooned if g - gg <= 0.5]
                    acc["clawline"]["hero_hits_in_harpoon"].append({"f": f, "source": src, "clip": clip,
                                                                    "from_hooked": tk in hooked})
                if tk in under_t:
                    acc["under"]["hits_under"] += 1
                    acc["under_by_type"][tk]["hits_under"] += 1
                elif tk in near_t:
                    acc["under"]["hits_near"] += 1
                    acc["under_by_type"][tk]["hits_near"] += 1
                if pocket:
                    fam = next((last_fam[i][0] for i, e2 in by_iid.items() if e2.get("type_key") == tk
                                and i in last_fam), "?")
                    acc["pocket"]["hits"][f"{unit}: {tk}/{fam}/{src}"] += 1
            elif k == "hit" and str(d.get("src") or "").startswith("Harpoon"):
                acc["clawline"]["harpoon_hits"] += 1
                harpooned.append((g, d.get("type_key")))
        prev = s
    acc["game_s"][unit] += g


def audit(runs: list[Path], max_fights: int | None = None) -> dict:
    starts, _ = family_tables()
    bounds = load_boundaries()
    acc = {"families": defaultdict(Counter), "families_all": Counter(), "near_boundary": Counter(),
           "never_seen": defaultdict(Counter), "never_seen_dwell_max": {}, "hop_up": [], "game_s": Counter(),
           "clashes": {"nail_clash": Counter(), "bell_nail": Counter(), "policy_swings": Counter()},
           "clawline": {"harpoon_s": 0.0, "hero_hits_in_harpoon": [], "harpoon_hits": 0, "presses": 0},
           "under": {"under_s": 0.0, "near_s": 0.0, "hits_under": 0, "hits_near": 0, "policy_under_s": 0.0},
           "pocket": {"pocket_s": 0.0, "clapper_starts": Counter(), "hits": Counter(), "by_unit_s": Counter(),
                      "clapper_from": Counter()},
           "under_by_type": defaultdict(lambda: {"under_s": 0.0, "near_s": 0.0, "hits_under": 0, "hits_near": 0}),
           "climbs": {"n": 0, "ok": 0, "t_top": []}, "fights": 0, "skipped": []}
    n = 0
    for run in runs:
        rows = {}
        for p in sorted(Path(run).glob("attempts_i*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    rows[(r.get("instance"), r.get("episode"))] = r
        fights, skipped = run_fights(Path(run))
        acc["skipped"] += skipped
        for fight in fights:
            if max_fights is not None and n >= max_fights:
                break
            inst, ep = fight.id.split("/")[-2:]
            r = rows.get((int(inst[1:]), int(ep[2:]))) or {}
            unit = r.get("unit") or "?"
            scan_fight(fight, unit, acc, starts, bounds)
            pol = r.get("policy") or {}
            acc["clashes"]["policy_swings"].update(pol.get("clash_swings") or {})
            acc["clawline"]["presses"] += int(pol.get("claw_presses") or 0)
            acc["under"]["policy_under_s"] += float(pol.get("under_s") or 0.0)
            for c in pol.get("climbs") or ():
                acc["climbs"]["n"] += 1
                if c.get("ok"):
                    acc["climbs"]["ok"] += 1
                    acc["climbs"]["t_top"].append(c.get("t_top"))
            acc["fights"] += 1
            n += 1
    t = sorted(x for x in acc["climbs"]["t_top"] if x is not None)
    acc["climbs"]["t_top_p50"] = t[len(t) // 2] if t else None
    acc["climbs"]["t_top_p95"] = t[min(len(t) - 1, max(0, math.ceil(0.95 * len(t)) - 1))] if t else None
    hu = acc["hop_up"]
    acc["hop_up_summary"] = {"n": len(hu), "wall_gap_lt_3": sum(1 for h in hu if h.get("wall_gap", 99) < 3.0),
                              "next": dict(Counter(h.get("next") for h in hu))}
    acc["hop_up"] = hu[:50]
    del acc["climbs"]["t_top"]
    hours = sum(acc["game_s"].values()) / 3600.0
    acc["per_hour_all"] = {k: round(v / hours, 1) for k, v in acc["families_all"].most_common()} if hours else {}
    acc["hours"] = round(hours, 3)
    for t, v in acc["under_by_type"].items():
        v["per_min_under"] = round(60.0 * v["hits_under"] / v["under_s"], 2) if v["under_s"] > 1 else None
        v["per_min_near"] = round(60.0 * v["hits_near"] / v["near_s"], 2) if v["near_s"] > 1 else None
    cl = acc["clawline"]
    cl["hits_from_hooked"] = sum(1 for h in cl["hero_hits_in_harpoon"] if h.get("from_hooked"))
    u = acc["under"]
    u["hits_per_min_under"] = round(60.0 * u["hits_under"] / u["under_s"], 2) if u["under_s"] else None
    u["hits_per_min_near"] = round(60.0 * u["hits_near"] / u["near_s"], 2) if u["near_s"] else None
    return json.loads(json.dumps(acc, default=lambda o: dict(o) if isinstance(o, Counter) else str(o)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--max-fights", type=int)
    a = ap.parse_args(argv)
    out = audit(a.runs, a.max_fights)
    txt = json.dumps(out, indent=1)
    if a.json:
        a.json.write_text(txt, encoding="utf-8")
    brief = {k: out[k] for k in ("fights", "hours", "families_all", "near_boundary", "never_seen",
                                 "never_seen_dwell_max", "clashes",
                                 "clawline", "under", "pocket", "climbs")}
    brief["hop_up_summary"] = out["hop_up_summary"]
    brief["under_by_type"] = out["under_by_type"]
    brief["clawline"] = {**brief["clawline"], "hero_hits_in_harpoon": len(out["clawline"]["hero_hits_in_harpoon"])}
    print(json.dumps(brief, indent=1)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
