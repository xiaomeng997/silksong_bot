"""Replay of recorded low-HP decisions under the Q1 / Q1a rule (DESIGN §3.7.4, the person's rule of 2026-10-03; M2
W5): for every Bell Beast eval episode that quit at h <= 2 (Q1 / Q6) or bound (a heal during the fight),
the recording drives a fresh PlannerPolicy of this code open loop over the low-HP stretch, and the decisions are
compared:

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.lowhp_replay C:/ssbot/data/runs/m2/<run> [<run> ...] [--json out.json]

  live   what the run did: its first PAUSE_PENDING frame and reasons, the Binds it started (cstate isBinding onsets
         after the hit) and completed (health up)
  new    this code, replayed: the first tick whose plan is the Bind (Q1a's heal first, the planner's own Bind rollout
         passing) or whose decision is PAUSE_PENDING (Q1 and the rest), from the hit that took the hero to h <= 2
  old    main before this change (5a83283), at the same ticks, as a counterfactual: it Binds where the new code does
         only when the playbook's hp_missing_min held (HP <= max - 2) and its h was the support's (the new h_basis
         "support"); with a certified-empty support its h was UNBOUNDED and the commit test refused the Bind (HP 3 >
         max - 3, h > 2). Its quits were the new ones with Q6 at h 2 (--q6-max-h 2): 10bfb66 already counted the
         worst known event for Q1.
For a Bind the new code would start: the support's T_min at the tick (>= 1.52 s by the commit test) and the ground
truth over the recorded frames of the Bind (decision frame + 2 .. + 2 + 83 + 9: the macro's latch lead, its 81-83
frames and delta_b): the least distance from any threat collider of the recording (ssbot.ipc.ents.is_threat) to the
hero's box held where the Bind starts (standing: the recorded box 2 frames on; airborne: the Bind rollout's boxes),
"censored" when the recording ends first (an emulated quit stops it at the pause); its verdict is then "unverified",
never "clear" (new_bind_check.verdict: clear / hit / unverified). A live Q1 on the hit's own frame (h <= 1 at once:
the pause stress chunks' injected hits) is replayed for that tick: does this code quit there too, or ask for a Bind.
--q6-max-h 2 replays with Q6 at h 2 (the rule before the person's of 2026-10-03), to tell its effect from Q1 / Q1a's.

The replay is the live loop up to drift: before the stretch the STATEs go through the perception path only (the
backend, the hero's state tracker, the forecaster's trackers, as PlannerPolicy._catch_up does for late ticks), and
from 60 frames before the hit every STATE is a full tick with the live masks as the planner's prefix
(ssbot.tools.quit_timeline). The supervisor starts fresh at the stretch (its Q4 count of earlier unpredicted hits is
not carried; the live reasons say whether a Q4 fired).
"""
import argparse
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

from ssbot.tools.postmortem import find_recording

WARM_F = 60                 # full ticks before the hit (the planner's continuity, the trackers' current phase)
BIND_F = 83 + 9             # the Bind's longest variant plus delta_b, frames
LEAD_F = 2                  # the ACTION for f + 2 goes out at STATE f
MAX_HP = 5
QUIT_IDS = ("Q1", "Q6")     # the low-HP quits the rule is about; the old Q3 reading ("h = 2 and N threat instances",
#                             20261002_03-08 runs, fixed since) quit on the hit frame itself and leaves nothing to replay


def _ids(reasons: list[str] | None, reason: str | None) -> list[str]:
    if reasons:
        return sorted({r.split(":", 1)[0] for r in reasons})
    return sorted(set(re.findall(r"\b(Q\d)\b", reason or "")))


def episodes(runs: list[Path]):
    """(run, row) of every episode with a low-HP decision: a QUIT whose trigger is Q1 / Q6, or a heal
    (recording "hp" event with delta > 0 inside the fight)."""
    from ssbot.tools.combat_run import load_attempts
    for run in runs:
        for row in load_attempts(run):
            if not row.get("recording") or row.get("f_end") is None or row.get("acts") is None:
                continue
            pol = row.get("policy") or {}
            ids = _ids(pol.get("first_pending_reasons"), row.get("reason"))
            quit_ = row.get("outcome") == "QUIT" and any(i in QUIT_IDS for i in ids)
            heals = _heals(run, row)
            if quit_ or heals:
                yield run, row, ids, heals


def _heals(run: Path, row: dict) -> list[tuple[int, int]]:
    return _events(run, row)[0]


def _events(run: Path, row: dict) -> tuple[list[tuple[int, int]], list[int]]:
    """(heals as (frame, HP before), frames of the hits that left HP <= max - 2) from the recording's events.jsonl."""
    rec = find_recording(run, row)
    p = rec / "events.jsonl"
    f0, f1 = row["f_end"] - row["acts"] - (row.get("late_states") or 0), row["f_end"]
    heals, low = [], []
    if p.is_file():
        for line in p.open(encoding="utf-8"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = e.get("data") or {}
            if not f0 <= (e.get("frame") or 0) <= f1:
                continue
            if e.get("kind") == "hp" and (d.get("delta") or 0) > 0:
                heals.append((e["frame"], int(d.get("h") or 0) - int(d.get("delta") or 0)))
            elif e.get("kind") == "damage" and d.get("h") is not None and d.get("amount") is not None \
                    and int(d["h"]) - int(d["amount"]) <= MAX_HP - 2:
                low.append(e["frame"])
    return heals, low


def _min_dist(states_by_f: dict, boxes: dict[int, tuple]) -> tuple[float | None, int, bool]:
    """(least distance from a recorded threat collider to the hero's box over the frames, frames checked, censored)."""
    from ssbot.ipc.ents import is_threat
    from ssbot.tools.forum_pocket import collider_box_distance
    best, n, censored = None, 0, False
    for f, box in sorted(boxes.items()):
        s = states_by_f.get(f)
        if s is None:
            censored = True
            continue
        n += 1
        for e in s.get("ents") or ():
            for c in e.get("colliders") or ():
                if is_threat(c):
                    d = collider_box_distance(c, box)
                    best = d if best is None else min(best, d)
    return best, n, censored


def replay(run: Path, row: dict, ids: list[str], heals: list, pol, threads: int = 4) -> dict:
    from ssbot.core.primitives import Prim
    from ssbot.knowledge.kinematics import Terrain2D, cstate_names
    from ssbot.record.recorder import RecordingReader
    from ssbot.safety.supervisor import H_SUPPORT, bind_allowed
    from ssbot.tools.pause_stress import _cs
    from ssbot.tools.quit_timeline import control
    from ssbot.train.encounters import BELL_BEAST
    names = cstate_names()
    rec = find_recording(run, row)
    r = RecordingReader(rec)
    for _, m in r.terrain():
        if m.get("scene_raw") == BELL_BEAST.scene:
            pol.terrain = Terrain2D.from_message(m, pol.params.scene(BELL_BEAST.scene))
    start = row["f_end"] - row["acts"] - (row.get("late_states") or 0)
    states = list(r.states(start, row["f_end"]))
    # the ground truth stops at the live pause (the world is frozen from there) or the episode's end
    paused = next((s["f"] for s in states if (s.get("game") or {}).get("paused")), row["f_end"] + 1)
    by_f = {s["f"]: s for s in states if s["f"] < paused}
    pol_row = row.get("policy") or {}
    live_pend = pol_row.get("first_pending_f")
    # the hit that took the hero to h <= 2 (3 HP or less against 2-mask hits) before the live decision
    hits = [s for s in states if any(e.get("k") == "damage" for e in s.get("ev") or ())
            and ((s.get("hero") or {}).get("health") or 9) <= MAX_HP - 2]
    last = live_pend if live_pend is not None else row["f_end"]
    before = [s for s in hits if s["f"] <= last]
    if not before:
        return {"skipped": "no hit to h <= 2 before the decision"}
    fh = before[0]["f"]
    # live Binds after the hit
    live_binds = []
    prev = False
    for s in states:
        if s["f"] < fh:
            continue
        b = bool(_cs(names, s).get("isBinding"))
        if b and not prev:
            live_binds.append(s["f"] - fh)
        prev = b
    # the stretch: to the live pause, else to the first live Bind (+ 5 frames), else to the episode's end
    end_f = live_pend if live_pend is not None else fh + live_binds[0] + 5 if live_binds else row["f_end"]

    class Tap:
        wake_frame = row.get("f_wake")
    pol.reset(random.Random(row["seed"]), BELL_BEAST)
    last_prefs: dict = {}
    orig = pol.tac.decide

    def decide(*a, **k):
        p = orig(*a, **k)
        last_prefs["p"] = p
        return p
    pol.tac.decide = decide
    feed0 = pol.backend.feed

    def feed(s):
        w = feed0(s)
        if w is not None:
            last_prefs["ws"] = w
        return w
    pol.backend.feed = feed
    ticks = []
    try:
        for i, s in enumerate(states):
            f = s["f"]
            if f > end_f + 1:
                break
            nxt = states[i + 1] if i + 1 < len(states) else None
            if nxt is not None and nxt["f"] == f + 1 and (nxt.get("act") or {}).get("mask") is not None:
                pol.sent[f + 1] = int(nxt["act"]["mask"])
            if f < fh - WARM_F:
                _perceive(pol, s, Tap)
                continue
            last_prefs.pop("p", None)
            pol.act(s, Tap)
            if f < fh or pol.planner_last is None or "p" not in last_prefs:
                continue                     # a pause tick (the planner is not ticked) or before the hit
            d = pol.decision
            res = pol.planner_last
            ws = last_prefs.get("ws")
            prefs = last_prefs.get("p")
            hero = s.get("hero") or {}
            hp, silk = hero.get("health"), hero.get("silk")
            fo, fcast = pol.forecasts[-1][0], pol.forecasts[-1][1]
            t_min = math.inf
            if ws is not None:
                t_min = fcast.t_min(ws.hero.pos.v[0], ws.hero.pos.v[1], t_max=2.0)
            new_bind = res.name == "BIND" and not (d is not None and d.pause_pending)
            old_bind = new_bind and hp is not None and hp <= MAX_HP - pol.pb.bind_hp_missing_min and \
                d is not None and d.h_basis == H_SUPPORT
            item = {"f": f - fh, "control": control(s), "hp": hp, "silk": silk,
                    "h": None if d is None else d.h, "basis": None if d is None else d.h_basis,
                    "tier": None if d is None else d.tier, "pending": bool(d is not None and d.pause_pending),
                    "reasons": [] if d is None else [x for x in d.reasons if x[:2] in ("Q1", "Q3", "Q5", "Q6")],
                    "mode": getattr(prefs, "mode", None), "bind_why": getattr(prefs, "bind_why", ""),
                    "t_min": None if not math.isfinite(t_min) else round(t_min, 3), "plan": res.name,
                    "new_bind": new_bind, "old_bind": old_bind,
                    "commit_ok": bool(hp is not None and silk is not None and d is not None and d.h is not None
                                      and bind_allowed(int(silk), int(hp), MAX_HP, int(d.h), t_min).ok)}
            if new_bind:
                item["path"] = None if res.path is None else [list(map(float, b)) for b in res.path]
                item["fo"] = fo
            ticks.append(item)
    finally:
        pol.tac.decide = orig
    out = {"hit_f": fh, "end_f": end_f - fh, "live_pending": None if live_pend is None else live_pend - fh,
           "live_ids": ids, "live_binds": live_binds, "live_heals": [(f - fh, hpb) for f, hpb in heals if f >= fh],
           "ticks": len(ticks)}
    nb = next((t for t in ticks if t["new_bind"]), None)
    npend = next((t for t in ticks if t["pending"]), None)
    ob = next((t for t in ticks if t["old_bind"]), None)
    out["new_bind"] = None if nb is None else nb["f"]
    out["new_pending"] = None if npend is None else npend["f"]
    out["new_pending_reasons"] = None if npend is None else npend["reasons"]
    out["old_bind"] = None if ob is None else ob["f"]
    out["silk9_ticks"] = sum((t["silk"] or 0) >= 9 for t in ticks)
    out["free_ticks"] = sum(t["control"] == "free" for t in ticks)
    out["t_min_ok_ticks"] = sum((t["t_min"] is None or t["t_min"] >= 1.52) for t in ticks)
    out["worst_basis_ticks"] = sum(t["basis"] == "worst known" for t in ticks)
    out["bind_why"] = dict(Counter((t["bind_why"] or "").split(";")[0][:40] for t in ticks if not t["new_bind"])
                           .most_common(4))
    if nb is not None:
        f = fh + nb["f"]
        boxes: dict[int, tuple] = {}
        stand = by_f.get(f + LEAD_F) or by_f.get(f)
        hb = (stand.get("hero") or {}).get("box") if stand else None
        on_ground = bool(_cs(names, stand).get("onGround")) if stand else False
        if hb and on_ground:
            for k in range(LEAD_F, LEAD_F + BIND_F):
                boxes[f + k] = tuple(hb)
        elif nb.get("path"):
            fo = nb["fo"]
            for k, b in enumerate(nb["path"]):
                if f + LEAD_F <= fo + k <= f + LEAD_F + BIND_F:
                    boxes[fo + k] = tuple(b)
        dist, n, cens = _min_dist(by_f, boxes)
        hit = dist is not None and dist <= 0.0
        # a Bind the recording does not cover to its end is unverified, not clear: the world after the live pause is
        # not recorded (fixer review 2026-10-03: 20261002_152649 i2 ep3 had 5 of 92 frames, and the live run quit 3
        # frames into the same Bind with a threat 0.93 u away)
        out["new_bind_check"] = {"t_min": nb["t_min"], "hp": nb["hp"], "silk": nb["silk"], "basis": nb["basis"],
                                 "on_ground": on_ground, "frames": n, "frames_needed": len(boxes), "censored": cens,
                                 "min_dist": None if dist is None else round(dist, 3),
                                 "would_be_hit": hit,
                                 "verdict": "hit" if hit else "unverified" if cens or not n else "clear"}
    return out


def _perceive(pol, s: dict, tap) -> None:
    """The perception path only (PlannerPolicy._catch_up's body): no tactics, no planner, no supervisor."""
    f = s["f"]
    pol._last_f = f
    pol.raw[f] = s
    for old in [k for k in pol.raw if k < f - 12]:
        del pol.raw[old]
    ws = pol.backend.feed(s)
    if ws is None:
        return
    raw = pol.raw.get(ws.stamp.frame, s)
    raw["_t"] = ws.stamp.t_game_s
    pol.trk.push(raw)
    pol._wake(ws, s, tap)
    pol.fc.update(ws)


def classify(x: dict) -> str:
    """Live vs new decision, "<live>-><new>": bind / quit / fight (no decision in the stretch: for the new code, none
    up to the live pause or Bind, after which the recording no longer follows what it would have done)."""
    r = x.get("replay") or {}
    if r.get("skipped"):
        return "quit@hit" if r["skipped"].startswith("live pause on the hit") else "skipped"
    nb, npd, lp = r.get("new_bind"), r.get("new_pending"), r.get("live_pending")
    live_bound = bool(r.get("live_binds"))
    new_first = "bind" if nb is not None and (npd is None or nb < npd) else "quit" if npd is not None else "fight"
    live_first = "bind" if live_bound and (lp is None or min(r["live_binds"]) < lp) else "quit" if lp is not None \
        else "fight"
    return f"{live_first}->{new_first}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--q6-max-h", type=int, default=None,
                    help="SupervisorConfig.q6_max_h for the replayed code (2: Q6 at h 2 as before 2026-10-03)")
    a = ap.parse_args(argv)
    from dataclasses import replace as dc_replace

    from ssbot.train.planner_policy import PlannerPolicy
    pols: dict[str, PlannerPolicy] = {}
    items = []
    for run, row, ids, heals in episodes(a.runs):
        view = (row.get("policy") or {}).get("view", "oracle")
        pend = (row.get("policy") or {}).get("first_pending_f")
        low = _events(run, row)[1]
        if pend is not None and low and pend - low[0] <= 1 and not heals and "Q1" not in ids:
            # the live supervisor quit on the hit's own frame for a reason this code no longer has (stage C before
            # task V read the oracle STATE; Q6 on FORCED_RISK at the hit frame before the i-frames were counted,
            # 20261002_102538): nothing between the hit and the live decision to replay. A Q1 on the hit frame (h <= 1
            # at once: the pause stress chunks' injected hits, a second Bell Beast hit) is replayed: its hit tick says
            # whether this code quits there too or would ask for a Bind
            rp = {"skipped": "live pause on the hit frame", "live_pending": pend - low[0], "live_ids": ids}
        else:
            if view not in pols:
                pols[view] = PlannerPolicy(view=view, threads=a.threads)
                if a.q6_max_h is not None:
                    pols[view].sc.cfg = dc_replace(pols[view].sc.cfg, q6_max_h=a.q6_max_h)
            try:
                rp = replay(run, row, ids, heals, pols[view], a.threads)
            except Exception as e:  # noqa: BLE001 - one broken recording must not end the batch
                rp = {"skipped": f"error {e!r}"[:200]}
        x = {"run": run.name, "instance": row.get("instance"), "episode": row.get("episode"), "view": view,
             "code": row.get("code_rev"), "outcome": row.get("outcome"), "replay": rp}
        x["change"] = classify(x)
        items.append(x)
        print(json.dumps({k: x[k] for k in ("run", "instance", "episode", "view", "change")}
                         | {k: rp.get(k) for k in ("live_ids", "live_pending", "live_binds", "new_bind", "new_pending",
                                                   "old_bind", "silk9_ticks", "worst_basis_ticks", "new_bind_check",
                                                   "skipped")}), flush=True)
        if a.limit and len(items) >= a.limit:
            break
    summ = {"episodes": len(items), "changes": dict(Counter(x["change"] for x in items)),
            "by_view": {v: dict(Counter(x["change"] for x in items if x["view"] == v))
                        for v in sorted({x["view"] for x in items})},
            "new_binds": sum(x["replay"].get("new_bind") is not None for x in items),
            "new_binds_not_old": sum(x["replay"].get("new_bind") is not None and x["replay"].get("old_bind") is None
                                     for x in items),
            "new_bind_would_be_hit": sum(bool((x["replay"].get("new_bind_check") or {}).get("would_be_hit"))
                                         for x in items),
            "new_bind_censored": sum(bool((x["replay"].get("new_bind_check") or {}).get("censored")) for x in items),
            "new_bind_verdicts": dict(Counter((x["replay"].get("new_bind_check") or {}).get("verdict")
                                              for x in items if x["replay"].get("new_bind_check"))),
            "new_pending_ids": dict(Counter(",".join(sorted({r.split(":", 1)[0] for r in
                                                             x["replay"].get("new_pending_reasons") or ()}))
                                            for x in items if x["replay"].get("new_pending") is not None)),
            "live_ids": dict(Counter(",".join(x["replay"].get("live_ids") or ()) for x in items))}
    print(json.dumps(summ, indent=1))
    if a.json:
        a.json.write_text(json.dumps({"summary": summ, "items": items}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
