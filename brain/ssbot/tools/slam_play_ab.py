"""The live A/B rn vs rnplay / rnplay6 per arm (task 1v1 SP2, forum.md 66), from run manifests (1v1_live.ps1).

Per arm:
- episodes: kills, HP-hitless kills (hits counted by HP loss: the bounce's i-frames produce `damage` events without HP
  loss), kill time, the HP-loss hits by source, by the Clapper's Control state and by the playbook's phase;
- every slam: the playbook started or not and why (the policy's counters for all slams; per slam the decision
  log's `play` field, only for the slams the log kept - it keeps the ticks around events: the run's phase, its frame
  k from the antic entry and its `why`), its own keys (slam_play_live: the jump at antic +K_JUMP, the attack + down at
  +K_PRESS, either one frame late), contact (the hero's attack hits the Clapper from the playbook's press to +14),
  the bounce (the hero's vy > 6 in the press's 14 frames), landed (its HP drops), HP lost in the slam (until the
  Slam Recover ends) and its source (the hammer = Slam Collider 1), HP lost in the 60 frames after, the retreat (the
  largest distance in the slam minus the distance at the antic entry, in front), x at the antic entry / the Slam 0
  entry / the slam's end (centre to centre, + = in front), the hero's landed hits in the slam (strikes);
- the small-rune casts (Spell Antic -> Cast 1 -> Cast 2): the hero's distance |d| per frame in the cast and in the 40
  frames after, dash / air dash clips (anywhere from the antic to +40 after the cast, and inside Cast 2), the hero's
  landed hits per cast, HP lost in the cast and the 60 frames after.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.slam_play_ab --manifest C:/ssbot/sandbox/1v1sp2_manifest.txt \
        [--arms rn,rnplay,rnplay6] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat import slam_play as sp
from ssbot.tools.slam_play_live import AFTER_F, manifest, pct, slams_of

CAST_ST = ("Spell Antic", "Cast 1", "Cast 2")
DASH_CLIPS = ("Air Dash", "Dash", "Sprint Air", "Sprint Air Short", "Sprint")
STARTED = ("land", "walk", "jump", "air", "after", "done")


def _hero_attacks():
    from ssbot.tools.forum_demo import HERO_ATTACKS
    return HERO_ATTACKS


def _signed(s: dict, e: dict | None, face: int | None = None) -> float | None:
    """The hero's x from the Clapper's centre, + = in front (face: the facing to use, default its own now)."""
    if e is None or not (s.get("hero") or {}).get("box"):
        return None
    face = face or (1 if e.get("flipX") else -1)
    return (sp.hero_x(s) - float(e["pos"][0])) * face


def _decisions(run: Path, inst: int) -> dict:
    """episode -> {frame: (play dict or None, plan, forced)} from the decision log."""
    out = defaultdict(dict)
    p = run / f"decisions_i{inst}.jsonl"
    if not p.exists():
        return out
    for line in p.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[int(r.get("ep", -1))][int(r["f"])] = (r.get("play"), r.get("plan"), bool(r.get("forced")))
    return out


def _episode(arm: str, inst: int, run: Path, row: dict, dec: dict, cfg) -> dict:
    from ssbot.record.recorder import RecordingReader
    HA = _hero_attacks()
    f_wake, f_end = int(row["f_wake"]), int(row["f_end"])
    fk = row.get("f_kill") or f_end
    states = list(RecordingReader(row["recording"]).states(f_wake, f_end))
    by_f = {int(s["f"]): s for s in states}
    ep_id = f"{run.name[:15]}{run.name[-2:] if run.name.endswith('_2') else ''}_i{inst}_e{row['episode']}"
    ticks = dec.get(int(row["episode"]), {})
    # per frame: the Clapper, its state, the hero's landed hits, HP-loss events, damage events
    clap, st_of, landed_f, hp_ev, dmg_ev = {}, {}, [], [], []
    for s in states:
        f = int(s["f"])
        e = sp.clapper(s)
        clap[f] = e
        st_of[f] = sp.control(e)[0]
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "hit" and d.get("type_key") == sp.CLAPPER and d.get("src") in HA:
                dealt = d.get("dealt", d.get("amount"))
                if dealt is None or float(dealt) > 0:
                    landed_f.append((f, str(d.get("src"))))
            elif k == "hp" and (d.get("delta") or 0) < 0:
                hp_ev.append((f, -int(d.get("delta")), str(d.get("source"))))
            elif k == "damage":
                dmg_ev.append((f, str(d.get("source"))))
    if not hp_ev:                                   # no hp event: the health field
        for a, b in zip(states, states[1:]):
            ha, hb = (a.get("hero") or {}).get("health"), (b.get("hero") or {}).get("health")
            if ha is not None and hb is not None and hb < ha:
                src = next((s_ for f_, s_ in dmg_ev if abs(f_ - int(b["f"])) <= 3), "?")
                hp_ev.append((int(b["f"]), ha - hb, src))

    def play_at(f):
        for g in (f, f - 1, f - 2, f - 3):
            t = ticks.get(g)
            if t is not None:
                return t
        return (None, None, False)

    # the HP-loss hits
    hits = []
    for f, amt, src in hp_ev:
        e = clap.get(f) or clap.get(f - 1)
        pl, plan, forced = play_at(f)
        s = by_f.get(f) or {}
        hits.append({"f": f, "amount": amt, "src": src.replace("(Clone)", "")[-40:], "src_full": src,
                     "st": st_of.get(f) or st_of.get(f - 1), "before_kill": f <= fk,
                     "air": not sp.on_ground(s) if s else None, "x": None if not s else _signed(s, e),
                     "play": None if not pl else f"{pl.get('phase')}@{pl.get('k')}", "plan": plan, "forced": forced})
    # slams
    S = slams_of(states, cfg)
    for x in S:
        fa = int(x["f"])
        end = x.get("end") or min(fa + 140, f_end)
        x["ep"] = ep_id
        pls = [(g, ticks[g][0]) for g in range(fa - 2, end + 1) if g in ticks and ticks[g][0]]
        pls = [(g, p) for g, p in pls if p.get("k") is not None and -5 <= p["k"] <= 200]
        phases = [p.get("phase") for _, p in pls]
        whys = [p.get("why") for _, p in pls if p.get("why")]
        x["play_seen"] = bool(pls)
        x["play_started"] = any(ph in STARTED for ph in phases)
        x["play_air_entry"] = "land" in phases
        x["play_k_start"] = next((p["k"] for _, p in pls if p.get("phase") in STARTED), None)
        x["play_last_phase"] = phases[-1] if phases else None
        x["play_why"] = whys[-1] if whys else ("" if pls else None)
        x["play_whys"] = dict(Counter(whys))
        press = None if x.get("k_press_real") is None else fa + int(x["k_press_real"])
        if press is not None:
            c = next((f for f, _ in landed_f if press <= f <= press + 14), None)
            x["contact"] = c is not None
            x["contact_rel_s0"] = None if (c is None or x.get("s0") is None) else c - x["s0"]
            x["bounce"] = any(float(((by_f.get(g) or {}).get("hero") or {}).get("vel", [0, 0])[1]) > 6
                              for g in range(press + 1, press + 15) if g in by_f)
        else:
            x["contact"] = x["bounce"] = False
            x["contact_rel_s0"] = None
        hs = [h for h in hits if fa <= h["f"] < end]
        ha = [h for h in hits if end <= h["f"] < end + AFTER_F]
        x["hp_slam"] = [(h["f"] - fa, h["src"], h["st"]) for h in hs]
        x["hp_after"] = [(h["f"] - fa, h["src"], h["st"]) for h in ha]
        x["hammer_hit"] = any("Slam Collider" in h["src_full"] for h in hs)
        x["strikes"] = sum(1 for f, _ in landed_f if fa <= f < end)
        x["strikes_down"] = sum(1 for f, s_ in landed_f if fa <= f < end and "Down" in s_)
        f0 = 1 if (clap.get(fa) or {}).get("flipX") else -1     # the facing at the antic entry (it turns after the slam)
        dv = [v for g in range(fa, end + 1) if g in by_f for v in [_signed(by_f[g], clap.get(g), f0)] if v is not None]
        d0 = x.get("x_antic")
        x["retreat_u"] = None if (d0 is None or not dv) else round((max(dv) - d0) if d0 >= 0 else (d0 - min(dv)), 2)
        se = by_f.get(end)
        x["x_end"] = None if se is None else (None if _signed(se, clap.get(end), f0) is None
                                              else round(_signed(se, clap.get(end), f0), 2))
        # the way out's landing: the first frame on the ground after the bounce, signed (+ in front)
        xl = None
        if x["bounce"] and press is not None:
            for g in range(press + 15, min(end + 60, f_end)):
                s_ = by_f.get(g)
                if s_ is not None and sp.on_ground(s_):
                    e_ = clap.get(g) or clap.get(fa)
                    v = _signed(s_, e_, f0)
                    xl = None if v is None else round(v, 2)
                    break
        x["x_land"] = xl
    # casts
    casts = []
    fl = sorted(by_f)
    prev = None
    for i, f in enumerate(fl):
        st = st_of.get(f)
        if st == "Spell Antic" and prev != "Spell Antic":
            fe = next((g for g in fl[i:] if st_of.get(g) not in CAST_ST), None)
            if fe is not None and fe - f <= 150:
                c2 = [g for g in range(f, fe) if st_of.get(g) == "Cast 2"]
                d_in = [abs(v) for g in range(f, fe + 1) if g in by_f
                        for v in [_signed(by_f[g], clap.get(g))] if v is not None]
                d_af = [abs(v) for g in range(fe, fe + 40) if g in by_f
                        for v in [_signed(by_f[g], clap.get(g) or clap.get(fe - 1))] if v is not None]
                clip = lambda g: (((by_f.get(g) or {}).get("hero") or {}).get("anim") or {}).get("clip")  # noqa: E731
                dash = [g - f for g in range(f, fe + 40) if clip(g) in DASH_CLIPS]
                dash_c2 = [g - f for g in c2 if clip(g) in ("Air Dash", "Dash")]
                casts.append({"ep": ep_id, "f": f, "len": fe - f, "d": d_in, "d_after": d_af,
                              "x_antic": None if f not in by_f else _signed(by_f[f], clap.get(f)),
                              "air_antic": not sp.on_ground(by_f[f]),
                              "hits": sum(1 for g, _ in landed_f if f <= g <= fe + 40),
                              "hp": [(h["f"] - f, h["src"]) for h in hits if f <= h["f"] <= fe + 60],
                              "dash_k": dash[:1], "dash_c2": bool(dash_c2),
                              "max": max(d_in + d_af) if d_in + d_af else None})
        prev = st
    kill_s = row.get("kill_s")
    return {"ep": ep_id, "arm": arm, "outcome": row.get("outcome"), "kill_s": kill_s,
            "ingame_s": row.get("ingame_s"), "attempts_hits": row.get("hits"),
            "hp_hits_before_kill": sum(1 for h in hits if h["before_kill"]),
            "hp_lost_before_kill": sum(h["amount"] for h in hits if h["before_kill"]),
            "hp_hits_tail": sum(1 for h in hits if not h["before_kill"]),
            "protected_touches": sum(1 for f, _ in dmg_ev if not any(abs(f - h["f"]) <= 3 for h in hits)),
            "landed": sum(1 for f, _ in landed_f if f <= fk),
            "fight_s": round((fk - f_wake) / 60.0, 2),
            "slam_play": (row.get("policy") or {}).get("slam_play"),
            "hits": hits, "slams": S, "casts": casts}


def summarize(E: list[dict]) -> dict:
    S = [x for e in E for x in e["slams"]]
    C = [c for e in E for c in e["casts"]]
    H = [h for e in E for h in e["hits"] if h["before_kill"]]
    kills = [e for e in E if e["kill_s"] is not None]
    # the playbook's strikes: its own keys at the script's frames, or a started run that pressed (a late landing's
    # jump at once moves the keys off the script's frames)
    pl = [x for x in S if x["played"] or (x["play_started"] and x.get("k_press_real") is not None)]
    st = [x for x in S if x["play_started"]]
    dc = [x for x in S if x["play_seen"] and not x["play_started"]]
    allw = [v for c in C for v in c["d"]]
    allw2 = [v for c in C for v in c["d_after"]]
    pc = Counter()
    for e in E:
        pc.update(e.get("slam_play") or {})
    out = {
        # the policy's own playbook counters (every slam; the decision log keeps only the ticks around events, so the
        # per-slam play_* fields below exist only for the slams it logged)
        "policy_slam_play": dict(sorted(pc.items())),
        "episodes": len(E), "outcomes": dict(Counter(e["outcome"] for e in E)), "kills": len(kills),
        "hp_hitless_kills": sum(1 for e in kills if e["hp_hits_before_kill"] == 0),
        "hp_hits_before_kill": sum(e["hp_hits_before_kill"] for e in E),
        "hp_lost_before_kill": sum(e["hp_lost_before_kill"] for e in E),
        "protected_touches": sum(e["protected_touches"] for e in E),
        "kill_s_p10_50_90": pct([e["kill_s"] for e in kills]),
        "landed_per_s_pooled": round(sum(e["landed"] for e in kills) / max(sum(e["fight_s"] for e in kills), 1e-9), 3),
        "landed_per_s_p50": pct([e["landed"] / e["fight_s"] for e in kills if e["fight_s"] > 0], (50,)),
        "hits_by_src": dict(Counter(h["src"] for h in H)), "hits_by_state": dict(Counter(str(h["st"]) for h in H)),
        "hits_by_play": dict(Counter(str(h["play"]) for h in H)),
        "hits_air": sum(1 for h in H if h["air"]), "hits_forced": sum(1 for h in H if h["forced"]),
        "slams": len(S), "play_logged": sum(1 for x in S if x["play_seen"]), "play_started_logged": len(st),
        "play_air_entry": sum(1 for x in S if x["play_air_entry"]),
        "play_declined_why_logged": dict(Counter(x["play_why"] or "(none)" for x in dc)),
        "play_started_end": dict(Counter(f"{x['play_last_phase']}:{x['play_why'] or ''}" for x in st)),
        "played_keys": len(pl), "played_contact": sum(1 for x in pl if x["contact"]),
        "played_bounce": sum(1 for x in pl if x["bounce"]), "played_landed": sum(1 for x in pl if x["landed"]),
        "played_kill": sum(1 for x in pl if x.get("kill")),
        "played_hp_slam": sum(1 for x in pl if x["hp_slam"]), "played_hp_after": sum(1 for x in pl if x["hp_after"]),
        "played_contact_rel_s0": dict(Counter(x["contact_rel_s0"] for x in pl if x["contact_rel_s0"] is not None)),
        "played_land_behind": sum(1 for x in pl if x["x_land"] is not None and x["x_land"] < 0),
        "played_land_front": sum(1 for x in pl if x["x_land"] is not None and x["x_land"] >= 0),
        "played_x_land": pct([abs(x["x_land"]) for x in pl if x["x_land"] is not None]),
        "hammer_hits": sum(1 for x in S if x["hammer_hit"]),
        "hp_in_slams": sum(len(x["hp_slam"]) for x in S), "hp_after_slams": sum(len(x["hp_after"]) for x in S),
        "hp_in_slams_src": dict(Counter(h[1] for x in S for h in x["hp_slam"])),
        "retreat_gt1.5": sum(1 for x in S if (x["retreat_u"] or 0) > 1.5),
        "fled_s0_gt9": sum(1 for x in S if x["x_s0"] is not None and abs(x["x_s0"]) > 9),
        "strikes": sum(x["strikes"] for x in S), "strikes_down": sum(x["strikes_down"] for x in S),
        "strikes_per_slam": round(sum(x["strikes"] for x in S) / max(len(S), 1), 3),
        "x_antic": pct([x["x_antic"] for x in S]), "x_s0": pct([x["x_s0"] for x in S]),
        "declined_x_antic": pct([x["x_antic"] for x in dc]),
        "casts": len(C), "cast_d_p10_50_90": pct(allw), "cast_d_after40_p10_50_90": pct(allw2),
        "cast_share_frames_gt8": round(float((np.asarray(allw + allw2) > 8).mean()), 3) if allw + allw2 else None,
        "casts_max_gt9": sum(1 for c in C if (c["max"] or 0) > 9),
        "casts_with_dash": sum(1 for c in C if c["dash_k"]), "casts_air_dash_in_cast2": sum(1 for c in C if c["dash_c2"]),
        "cast_dash_k_p50": pct([c["dash_k"][0] for c in C if c["dash_k"]], (50,)),
        "hits_per_cast": round(sum(c["hits"] for c in C) / max(len(C), 1), 2),
        "cast_hp": dict(Counter(h[1] for c in C for h in c["hp"])),
        "cast_x_antic": pct([abs(c["x_antic"]) for c in C if c["x_antic"] is not None]),
        "casts_air_antic": sum(1 for c in C if c["air_antic"]),
    }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--arms", default="")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    cfg = sp.PlayCfg()
    arms = set(filter(None, a.arms.split(",")))
    E = defaultdict(list)
    for arm, inst, run in manifest(a.manifest, arms):
        dec = _decisions(run, inst)
        for line in (run / f"attempts_i{inst}.jsonl").read_text("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("outcome") == "HARNESS_FAIL":
                E[arm].append({"ep": f"{run.name}_e{row.get('episode')}", "outcome": "HARNESS_FAIL", "kill_s": None,
                               "hp_hits_before_kill": 0, "hp_lost_before_kill": 0, "protected_touches": 0,
                               "landed": 0, "fight_s": 0, "hits": [], "slams": [], "casts": []})
                continue
            E[arm].append(_episode(arm, inst, run, row, dec, cfg))
    out = {arm: summarize(v) for arm, v in E.items()}
    for arm, v in out.items():
        print(arm, json.dumps(v))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({"arms": out, "episodes": E}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
