"""What the Forum R1 targeted collection logged (Forum plan R1 items 2-3, docs/plans/forum_planner_plan.md), from a
combat_run's recordings and AttemptRecords (policy data2 / data2_envoy, ssbot.train.forum_policy):

  families     attack-family starts per enemy type (FORUM_SPECS attack-start states on the "fsm" events), per hour of
               game time, by episode unit (wave start); "near_boundary_any_entry": starts (any entry into an attack
               start state) within 1 u of the family's boundary, hero to body centre (not R0's definition)
  boundary_r0  like-for-like with R0's Boundaries product (ssbot.knowledge.forum_products): transitions out of the
               type's decision states, hero x to the enemy transform x, within 1 u of R0's boundary_u
               (knowledge/.../boundaries.json): decisions, of them chosen, per game hour and as a share; and the
               policy's BAIT samples per family (stats bait_samples)
  clapper_dec  Choir Clapper decisions out of its decision states by hero place (pocket: the left-wall top; air;
               ground) and hero |dx| bin: the pocket changes its choices (the R1 fixer's check of the tables'
               covariates)
  never_seen   Envoy "Hop Up?" -> next state (a hop slash needs the "HOP UP" ray, which comes after a FINISHED the
               state sends itself), with the Envoy's distance to the wall on the hero's side; Bellbearer "Rethrow?" ->
               next; Maestro "Attack Choice" -> next
  clashes      freeze NailClashEffect: the nearest in-play enemy and its current family; Throwing Bell nail hits
               ("Nail Hit" / "Tink" states); the policy's clash swings by owner type
  clawline     hero damage while a Harpoon clip plays (and 0.25 s after), harpoon hits on enemies; a hit counts as
               from the hooked enemy when the nearest live enemy of the source's type to the hero is the one the
               harpoon hit (same iid) within 0.5 s, not only the same type
  under        game seconds grounded right under a flier (|dx| < 0.75, body bottom >= 1.5 u above the hero's
               transform) and hero hits from fliers there, against the same near a flier but not under (1.5-6 u),
               per type with the count expected under at the near rate and its Poisson P(X <= seen)
  pocket       game seconds at the left-wall top (transform x < 14.6, y >= 13.2) and the Choir Clappers' attack
               starts meanwhile
  climbs       the policy's CLIMB segments: tries, reached the top, game seconds to the top; "real" leaves out the
               segments that began with the hero already at the top (start_top, or t_top < 0.2 s in records
               without it)

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
R0_HOURS = 25.4             # game hours of R0's 107 gauntlets (forum.md 12.1; boundaries.json counts)
WALLS = (14.01, 48.99)
UNDER_DX, UNDER_DY, NEAR_DX = 0.75, 1.5, 6.0
HARPOON_TAIL_S = 0.25
TOP_START_S = 0.2           # a CLIMB "reaching" the top this fast began there (records before start_top was logged)
DX_BINS = (0.0, 3.0, 6.0, 10.0, 99.0)
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


def poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0
    term = math.exp(-lam)
    acc = term
    for i in range(1, k + 1):
        term *= lam / i
        acc += term
    return min(1.0, acc)


def dx_bin(d: float) -> str:
    for lo, hi in zip(DX_BINS[:-1], DX_BINS[1:]):
        if lo <= d < hi:
            return f"{lo:g}-{hi:g}"
    return f">{DX_BINS[-1]:g}"


def r0_boundaries(path: Path | None = None) -> dict:
    """{"type/family": {boundary_u, decisions_within_1u_of_boundary, of_them_chosen}} of R0's boundaries.json."""
    p = path or Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum" / "boundaries.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in d.items() if isinstance(v, dict) and "boundary_u" in v and "/" in k}


def scan_fight(fight, unit: str, acc: dict, starts: dict, bounds: dict, r0b: dict | None = None) -> None:
    r0b = r0b or {}
    r0_by_type: dict[str, list] = defaultdict(list)
    for key, v in r0b.items():
        tk0, fam0 = key.rsplit("/", 1)
        r0_by_type[tk0].append((fam0, float(v["boundary_u"])))
    last_fam: dict[int, tuple[str, int]] = {}
    pend_next: dict[int, tuple[str, dict]] = {}       # ent -> (state, info) waiting for the next transition
    prev = None
    harpoon_until = -1.0
    harpooned: list[tuple[float, str, object]] = []   # (game s, type, iid) of the enemies the harpoon hit
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
                sp = FORUM_SPECS.get(tk)
                if (sp is not None and e is not None and e.get("pos") and d.get("fsm") == sp.control_fsm
                        and d.get("from") in sp.decision_states):
                    dxt = abs(hx - e["pos"][0])
                    fam_to = sp.attack_starts.get(to)
                    for fam0, b0 in r0_by_type.get(tk, ()):
                        if abs(dxt - b0) <= 1.0:
                            row = acc["boundary_r0"][f"{tk}/{fam0}"]
                            row["decisions_within_1u"] += 1
                            row["chosen"] += int(fam_to == fam0)
                    if tk == "Song Heavy Sentry":
                        place = "pocket" if pocket else ("ground" if hy < 5.0 else "air")
                        acc["clapper_dec"][place][f"{d.get('from')}|{dx_bin(dxt)}"][to or "None"] += 1
                fam = starts.get((tk, d.get("fsm")), {}).get(to)
                if fam and e is not None:
                    x0, y0, x1, y1 = body_box(e)
                    dxh = abs((x0 + x1) / 2.0 - hx)
                    acc["families"][unit][f"{tk}/{fam}"] += 1
                    acc["families_all"][f"{tk}/{fam}"] += 1
                    last_fam[ent] = (fam, f)
                    b = bounds.get(tk, {}).get(fam)
                    if b and abs(dxh - b[1]) <= 1.0:
                        acc["near_boundary_any_entry"][f"{tk}/{fam}"] += 1
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
                    hooked = [(t, i) for gg, t, i in harpooned if g - gg <= 0.5]
                    same = [e2 for e2 in live if e2.get("type_key") == tk]
                    nearest = None
                    if same:
                        def gap(e2):
                            x0, y0, x1, y1 = body_box(e2)
                            return max(x0 - hx, hx - x1, 0.0) + max(y0 - hy, hy - y1, 0.0)
                        nearest = min(same, key=gap)["iid"]
                    acc["clawline"]["hero_hits_in_harpoon"].append({
                        "f": f, "source": src, "clip": clip, "from_hooked_type": tk in {t for t, _ in hooked},
                        "from_hooked_enemy": nearest is not None and (tk, nearest) in hooked})
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
                harpooned.append((g, d.get("type_key"), d.get("ent")))
        prev = s
    acc["game_s"][unit] += g


def audit(runs: list[Path], max_fights: int | None = None) -> dict:
    starts, _ = family_tables()
    bounds = load_boundaries()
    r0b = r0_boundaries()
    acc = {"families": defaultdict(Counter), "families_all": Counter(), "near_boundary_any_entry": Counter(),
           "boundary_r0": defaultdict(lambda: {"decisions_within_1u": 0, "chosen": 0}), "bait_samples": Counter(),
           "clapper_dec": defaultdict(lambda: defaultdict(Counter)),
           "never_seen": defaultdict(Counter), "never_seen_dwell_max": {}, "hop_up": [], "game_s": Counter(),
           "clashes": {"nail_clash": Counter(), "bell_nail": Counter(), "policy_swings": Counter()},
           "clawline": {"harpoon_s": 0.0, "hero_hits_in_harpoon": [], "harpoon_hits": 0, "presses": 0},
           "under": {"under_s": 0.0, "near_s": 0.0, "hits_under": 0, "hits_near": 0, "policy_under_s": 0.0},
           "pocket": {"pocket_s": 0.0, "clapper_starts": Counter(), "hits": Counter(), "by_unit_s": Counter(),
                      "clapper_from": Counter()},
           "under_by_type": defaultdict(lambda: {"under_s": 0.0, "near_s": 0.0, "hits_under": 0, "hits_near": 0}),
           "climbs": {"n": 0, "ok": 0, "t_top": []},
           "climbs_real": {"n": 0, "ok": 0, "t_top": [], "started_at_top": 0, "pocket_n": 0},
           "fights": 0, "skipped": []}
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
            scan_fight(fight, unit, acc, starts, bounds, r0b)
            pol = r.get("policy") or {}
            acc["clashes"]["policy_swings"].update(pol.get("clash_swings") or {})
            acc["clawline"]["presses"] += int(pol.get("claw_presses") or 0)
            acc["under"]["policy_under_s"] += float(pol.get("under_s") or 0.0)
            acc["bait_samples"].update(pol.get("bait_samples") or {})
            for c in pol.get("climbs") or ():
                acc["climbs"]["n"] += 1
                if c.get("ok"):
                    acc["climbs"]["ok"] += 1
                    acc["climbs"]["t_top"].append(c.get("t_top"))
                top0 = c.get("start_top")
                if top0 is None:
                    top0 = bool(c.get("ok")) and (c.get("t_top") or 0.0) < TOP_START_S
                cr = acc["climbs_real"]
                if top0:
                    cr["started_at_top"] += 1
                    continue
                cr["n"] += 1
                cr["pocket_n"] += int(bool(c.get("pocket")))
                if c.get("ok"):
                    cr["ok"] += 1
                    cr["t_top"].append(c.get("t_top"))
            acc["fights"] += 1
            n += 1
    for key in ("climbs", "climbs_real"):
        t = sorted(x for x in acc[key]["t_top"] if x is not None)
        acc[key]["t_top_p50"] = t[len(t) // 2] if t else None
        acc[key]["t_top_p95"] = t[min(len(t) - 1, max(0, math.ceil(0.95 * len(t)) - 1))] if t else None
        del acc[key]["t_top"]
    hu = acc["hop_up"]
    acc["hop_up_summary"] = {"n": len(hu), "wall_gap_lt_3": sum(1 for h in hu if h.get("wall_gap", 99) < 3.0),
                              "next": dict(Counter(h.get("next") for h in hu))}
    acc["hop_up"] = hu[:50]
    hours = sum(acc["game_s"].values()) / 3600.0
    r0_hours = R0_HOURS
    for key, row in acc["boundary_r0"].items():
        v0 = r0b.get(key, {})
        n0, c0 = v0.get("decisions_within_1u_of_boundary"), v0.get("of_them_chosen")
        row.update(per_hour=round(row["decisions_within_1u"] / hours, 2) if hours else None,
                   chosen_per_hour=round(row["chosen"] / hours, 2) if hours else None,
                   chosen_share=round(row["chosen"] / row["decisions_within_1u"], 3) if row["decisions_within_1u"]
                   else None,
                   r0_boundary_u=v0.get("boundary_u"), r0_decisions_within_1u=n0, r0_chosen=c0,
                   r0_per_hour=round(n0 / r0_hours, 2) if n0 is not None else None,
                   r0_chosen_per_hour=round(c0 / r0_hours, 2) if c0 is not None else None,
                   r0_chosen_share=round(c0 / n0, 3) if n0 else None)
    acc["per_hour_all"] = {k: round(v / hours, 1) for k, v in acc["families_all"].most_common()} if hours else {}
    acc["hours"] = round(hours, 3)
    for t, v in acc["under_by_type"].items():
        v["per_min_under"] = round(60.0 * v["hits_under"] / v["under_s"], 2) if v["under_s"] > 1 else None
        v["per_min_near"] = round(60.0 * v["hits_near"] / v["near_s"], 2) if v["near_s"] > 1 else None
        if v["near_s"] > 1 and v["under_s"] > 0:
            lam = v["hits_near"] / v["near_s"] * v["under_s"]
            v["expected_under_at_near_rate"] = round(lam, 2)
            v["p_le_seen"] = round(poisson_cdf(int(v["hits_under"]), lam), 3)
    cl = acc["clawline"]
    cl["hits_from_hooked_type"] = sum(1 for h in cl["hero_hits_in_harpoon"] if h.get("from_hooked_type"))
    cl["hits_from_hooked_enemy"] = sum(1 for h in cl["hero_hits_in_harpoon"] if h.get("from_hooked_enemy"))
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
    brief = {k: out[k] for k in ("fights", "hours", "families_all", "near_boundary_any_entry", "boundary_r0",
                                 "bait_samples", "never_seen", "never_seen_dwell_max", "clashes",
                                 "clawline", "under", "pocket", "climbs", "climbs_real")}
    brief["hop_up_summary"] = out["hop_up_summary"]
    brief["under_by_type"] = out["under_by_type"]
    brief["clawline"] = {**brief["clawline"], "hero_hits_in_harpoon": len(out["clawline"]["hero_hits_in_harpoon"])}
    print(json.dumps(brief, indent=1)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
