"""Why the R5 terminal value does or does not move the Forum planner's choices (forum_planner_plan R5, the value
track's round 2; forum.md 20.5): replay recorded episodes open loop through ForumPlannerPolicy and audit every tick's
selection (ForumPlanner.last_sel) against what the recording's enemies actually did.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_tv_audit --run C:/ssbot/data/runs/m2/<run> --instance 0
        --episodes 0 1 2 [--frames 1500] --out C:/.../audit.json

The planner runs with ForumConfig.p_all (FORCED_RISK's P and first contacts for every allowed known row; the choice
still among the p_k preselected, so the decisions are the live ones). Per tick, FORCED_RISK and safe ticks apart:
  decided    the first selection key (hz, hz_soft, U, S, keep, mkeep, V, P, first contact on the envelope / on the
             nominal lane, J) on which the chosen row and the runner-up differ; "preselect" when the runner-up of all
             allowed rows was cut by the p_k preselection, "tail" when the tail pick moved the choice;
  changed    the choice under another ranking, a tick counted when its first CHANGE_F frames of keys differ from the
             chosen row's: J less the terminal value ("J0"), J before the first contacts ("J_first"), the terminal
             value alone before the first contacts ("TV_first"), the hindsight-clear row first ("oracle");
  hindsight  every allowed known row's nominal hero box against the recording's own threat colliders (enabled, can
             cause damage; their AABBs) on the same frames, the row's invulnerable frames skipped: clear = no overlap in
             the horizon. The enemies are the recording's (they reacted to the recorded hero, not to the row), so this
             is an estimate, and a biased one: the live ranking's choice is mostly the recorded path, the one the
             threats aimed at, so rows near it are judged unsafe more often (before hits the live choice is clear
             less often than a random allowed row: forum.md 20.11). Compare rankings with the random row's share
             ("random": the tick's share of clear allowed rows, averaged over ticks), not with the live choice; a key
             that tracks the recorded path (J0) gets an AUC below 0.5 without being harmful. Shares of ticks with a
             clear row, with each ranking's choice clear, and per key the
             within-tick AUC for clear rows (Mann-Whitney over the tick's allowed rows, pooled by pair count; 0.5: no
             information). Scores besides the planner's keys: the committed support's / the fine placements' share
             (P_com, P_fine: commit_rank), MultiForecast.prob, and the wave-0 forensics track's "seen" key (seen_n /
             seen_f: forced_rank "seen", ForumPlanner.seen_contacts).
"""
import argparse
import dataclasses
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

CHANGE_F = 6                      # two choices differ when their keys differ in the first this many frames
PRE_HIT_F = 36                    # "pre_hit": ticks at most this many frames before a recorded hit (any kind of tick)
ACCS = ("forced", "safe", "pre_hit")
DUMP: list | None = None          # --dump: per tick, the allowed rows' keys, scores and hindsight (offline rankings)
EP_KEY = [""]
KEY_NAMES = ("hz", "hz_soft", "U", "S", "keep", "mkeep", "V", "sk_n", "sk_f", "P", "Pcm", "Pf", "t_c", "t_hit", "J")


def threat_boxes(s: dict) -> np.ndarray:
    """[m, 4] AABBs (x0, y0, x1, y1) of the STATE's threat colliders (ipc.ents.is_threat)."""
    from ssbot.ipc.ents import is_threat
    out = []
    for e in s.get("ents") or ():
        for c in e.get("colliders") or ():
            if not is_threat(c):
                continue
            v = c.get("verts_world") or ()
            if len(v) < 2:
                continue
            r = c.get("r")
            if r is not None and len(v) == 2:
                out.append((v[0] - r, v[1] - r, v[0] + r, v[1] + r))
            else:
                xs, ys = v[0::2], v[1::2]
                out.append((min(xs), min(ys), max(xs), max(ys)))
    return np.array(out, np.float64).reshape(-1, 4)


def hindsight_clear(box: np.ndarray, inv: np.ndarray, fo: int, boxes: dict) -> np.ndarray:
    """[n] bool: row's nominal hero boxes [n, T1, 4] meet no recorded threat box on frames fo + 1 .. fo + T1 - 1
    (inv [n, T1]: invulnerable frames skipped)."""
    n, T1, _ = box.shape
    hit = np.zeros(n, bool)
    for k in range(1, T1):
        a = boxes.get(fo + k)
        if a is None or not len(a):
            continue
        b = box[:, k]
        ov = ((b[:, None, 0] < a[None, :, 2]) & (b[:, None, 2] > a[None, :, 0])
              & (b[:, None, 1] < a[None, :, 3]) & (b[:, None, 3] > a[None, :, 1])).any(axis=1)
        hit |= ov & ~inv[:, k]
    return ~hit


def auc_counts(score: np.ndarray, pos: np.ndarray) -> tuple[float, int]:
    """(Mann-Whitney U for the positives ranking above the negatives, pairs); ties count half."""
    n1, n0 = int(pos.sum()), int((~pos).sum())
    if not n1 or not n0:
        return 0.0, 0
    _, inv, cnt = np.unique(score, return_inverse=True, return_counts=True)
    r = (np.cumsum(cnt) - (cnt - 1) / 2.0)[inv]          # average ranks (1-based) with ties
    u = float(r[pos].sum()) - n1 * (n1 + 1) / 2.0
    return u, n1 * n0


def order_of(ls: dict, J: np.ndarray, pre: str = "J", first: str | None = None, extra=None,
             presel: bool = True) -> np.ndarray:
    """The selection's order of the allowed rows with J replaced (the planner's lexsort; FORCED_RISK: the p_k
    preselection by (-t_hit, -J) emulated unless presel is False). first: "J" ranks -J right after P (before the first
    contacts); "X" ranks -extra there."""
    sel = ls["allowed"].copy()
    forced = ls["forced"]
    t_hit, t_c, Pc = ls["t_hit"], ls["t_c"], ls["Pc"]
    Pf = ls.get("Pf", np.zeros(len(sel)))
    Pcm = ls.get("Pcm", np.zeros(len(sel)))
    sk_n = ls.get("sk_n", np.zeros(len(sel), np.int64))
    sk_f = ls.get("sk_f", np.zeros(len(sel), np.int64))
    if forced and presel:
        cand = np.flatnonzero(sel)
        Jp = J if pre == "J" else ls["J"]
        cand = cand[np.lexsort((-Jp[cand], -t_hit[cand], Pf[cand], Pcm[cand], -sk_f[cand], sk_n[cand]))][:ls["p_k"]]
        sel = np.zeros_like(sel)
        sel[cand] = True
    tail = (-J, -t_hit, -t_c)
    if first == "J":
        tail = (-t_hit, -t_c, -J)
    elif first == "X":
        tail = (-J, -t_hit, -t_c, -extra)
    o = np.lexsort(tail + (Pf, Pcm, Pc, -sk_f, sk_n, ~ls["V"], ~ls["mkeep"], ~ls["keep"], ls["S"], ls["U"],
                           ls["hz_soft"], ls["hz"]))
    return o[sel[o]]


def decided_key(ls: dict, a: int, b: int) -> str:
    keys = {"hz": ls["hz"], "hz_soft": ls["hz_soft"], "U": ls["U"], "S": ls["S"], "keep": ls["keep"],
            "mkeep": ls["mkeep"], "V": ls["V"], "sk_n": ls.get("sk_n", ls["Pc"] * 0),
            "sk_f": -ls.get("sk_f", ls["Pc"] * 0), "P": ls["Pc"], "Pcm": ls.get("Pcm", ls["Pc"] * 0),
            "Pf": ls.get("Pf", ls["Pc"] * 0), "t_c": ls["t_c"],
            "t_hit": ls["t_hit"], "J": ls["J"]}
    for k in KEY_NAMES:
        if keys[k][a] != keys[k][b]:
            return k
    return "tie"


def same_keys(cmd: np.ndarray, a: int, b: int) -> bool:
    return bool((cmd[a, :CHANGE_F] == cmd[b, :CHANGE_F]).all())


class Acc:
    def __init__(self):
        self.n = Counter()
        self.decided = Counter()
        self.changed = Counter()
        self.clear = Counter()
        self.auc = defaultdict(lambda: [0.0, 0])

    def as_dict(self) -> dict:
        n = max(self.n["ticks"], 1)
        nh = max(self.n["hind"], 1)
        return {"ticks": self.n["ticks"], "decided": {k: round(v / n, 3) for k, v in self.decided.most_common()},
                "presel_cut": round(self.n["presel_cut"] / n, 3), "chosen_P1": round(self.n["P1"] / n, 3),
                "changed": {k: round(v / n, 3) for k, v in sorted(self.changed.items())},
                "hindsight_ticks": self.n["hind"],
                "clear": {k: round(v / nh, 3) for k, v in sorted(self.clear.items())},
                "clear_rows_mean": round(self.n["clear_rows"] / max(self.n["rows"], 1), 3),
                "auc": {k: (round(u / p, 3) if p else None, p) for k, (u, p) in sorted(self.auc.items())},
                "raw": {"n": dict(self.n), "decided": dict(self.decided), "changed": dict(self.changed),
                        "clear": dict(self.clear), "auc": {k: list(v) for k, v in self.auc.items()}}}

    @classmethod
    def merged(cls, raws: list[dict]) -> "Acc":
        """One Acc from the "raw" parts of several outputs (runs audited in separate processes)."""
        a = cls()
        for r in raws:
            a.n.update(r["n"])
            a.decided.update(r["decided"])
            a.changed.update(r["changed"])
            a.clear.update(r["clear"])
            for k, (u, p) in r["auc"].items():
                a.auc[k][0] += u
                a.auc[k][1] += p
        return a


def contact_scores(ls: dict, f, allowed: np.ndarray, frame_time: float) -> dict[str, np.ndarray]:
    """Per row (higher = less contact), on stage 1's frames and the nominal box centre: the committed support's share
    of frames in contact ("P_com": current attacks, tails, death tails, hazards), the fine placements' ("P_fine": the
    current attacks' states with a known entry), the placements' path probability (MultiForecast.prob)."""
    from ssbot.combat.forum_planner import ForumPlanner
    box = ls["box"]
    T1 = box.shape[1]
    fr = ForumPlanner._s1_frames(T1)
    tk = np.arange(T1, dtype=np.float64)[fr] * frame_time
    b = box[allowed][:, fr]
    cx, cy = 0.5 * (b[..., 0] + b[..., 2]), 0.5 * (b[..., 1] + b[..., 3])
    inv = (ls["flags"][allowed][:, fr] & __import__("ssbot.knowledge.kinematics", fromlist=["F_INVULN"]).F_INVULN) != 0
    out = {}
    N = len(ls["allowed"])
    for k, occ in (("P_com", lambda: f._union_occ(cx, cy, tk, committed_only=True)),
                   ("P_fine", lambda: f._fine_occ(cx, cy, tk))):
        v = np.zeros(N)
        v[allowed] = -(occ() & ~inv).mean(axis=1)
        out[k] = v
    v = np.zeros(N)
    v[allowed] = -f.prob(cx, cy, tk)
    out["prob"] = v
    from ssbot.combat.forum_planner import seen_contacts, seen_polys
    ws = getattr(getattr(f, "_fc", None), "_ws", None)
    sn, sf = np.zeros(N), np.zeros(N)
    if ws is not None:
        verts, starts, pbox, pvel = seen_polys(ws)
        if len(pbox):
            T1 = box.shape[1]
            cnt, fst = seen_contacts(np.ascontiguousarray(box, np.float64),
                                     np.ascontiguousarray((ls["flags"] & __import__(
                                         "ssbot.knowledge.kinematics", fromlist=["F_INVULN"]).F_INVULN) != 0),
                                     verts, starts, pbox, pvel, np.arange(T1, dtype=np.float64) * frame_time,
                                     np.ascontiguousarray(allowed, np.int64), 0.0)
            sn[allowed], sf[allowed] = -cnt[allowed], fst[allowed]
    out["seen_n"] = sn                  # higher = better: minus the frames in contact, the first contact frame
    out["seen_f"] = sf
    return out


def audit_tick(pol, fo: int, boxes: dict, acc: dict, pre_hit: bool = False) -> None:
    ls = pol.planner.last_sel
    if ls is None:
        return
    for n, key in enumerate((("forced" if ls["forced"] else "safe"),) + (("pre_hit",) if pre_hit else ())):
        r = _audit_tick(pol, fo, boxes, acc[key], ls)
        if n == 0 and DUMP is not None and r is not None:
            clr, scores, allowed = r
            DUMP.append({"fo": fo, "ep": EP_KEY[0], "forced": bool(ls["forced"]), "pre_hit": bool(pre_hit),
                         "chosen": int(np.searchsorted(allowed, int(ls["chosen"]))) if ls["allowed"][ls["chosen"]]
                         else -1,
                         "presel": np.isin(allowed, order_of(ls, ls["J"])) if ls["forced"] else None,
                         "cmd": ls["cmd"][allowed, :CHANGE_F].astype(np.int32),
                         "clr": clr[allowed],
                         **{k: np.asarray(v)[allowed].astype(np.float32) for k, v in scores.items()},
                         **{k: np.asarray(ls[k])[allowed] for k in ("V", "keep", "mkeep", "S", "U", "hz",
                                                                     "hz_soft")}})


def _audit_tick(pol, fo: int, boxes: dict, a: "Acc", ls: dict):
    a.n["ticks"] += 1
    cmd, J = ls["cmd"], ls["J"]
    chosen = int(ls["chosen"])
    o = order_of(ls, J)
    o_all = order_of(dict(ls, forced=False, p_k=10 ** 9), J) if ls["forced"] else o
    if chosen != ls["first"]:
        a.decided["tail"] += 1
    elif len(o) > 1:
        a.decided[decided_key(ls, int(o[0]), int(o[1]))] += 1
    else:
        a.decided["single"] += 1
    if ls["forced"] and len(o_all) and int(o_all[0]) != int(o[0]):
        a.n["presel_cut"] += 1          # the best of every allowed row was not among the p_k preselected
    if ls["forced"]:
        a.n["P1"] += bool(ls["Pc"][int(o[0])] >= 0.999)
    jtv = ls.get("J_tv")
    alts = {}
    if jtv is not None:
        J0 = J - jtv
        alts["J0"] = order_of(ls, J0, pre="J0")
        alts["TV_first"] = order_of(ls, J, first="X", extra=jtv)
    alts["J_first"] = order_of(ls, J, first="J")
    allowed = np.flatnonzero(ls["allowed"])
    f = pol.forecasts[-1][1]
    extra = contact_scores(ls, f, allowed, pol.params.frame_time) if len(allowed) else {}
    for k, v in extra.items():
        if k != "seen_f":
            alts[k + "_first"] = order_of(ls, J, first="X", extra=v, presel=False)
    for k, oo in alts.items():
        if len(oo) and not same_keys(cmd, int(oo[0]), int(o[0])):
            a.changed[k] += 1
    # hindsight
    if not len(allowed):
        return
    from ssbot.knowledge.kinematics import F_INVULN
    T1 = ls["box"].shape[1]
    if any(fo + k not in boxes for k in (1, T1 - 1)):
        return
    clr = np.zeros(len(ls["allowed"]), bool)
    clr[allowed] = hindsight_clear(ls["box"][allowed], (ls["flags"][allowed] & F_INVULN) != 0, fo, boxes)
    a.n["hind"] += 1
    a.n["rows"] += len(allowed)
    a.n["clear_rows"] += int(clr[allowed].sum())
    a.clear["any"] += bool(clr[allowed].any())
    a.clear["random"] += float(clr[allowed].mean())
    a.clear["chosen"] += bool(clr[chosen])
    for k, oo in alts.items():
        if len(oo):
            a.clear[k] += bool(clr[int(oo[0])])
    # J-only among all allowed rows (no support key at all)
    a.clear["J_only"] += bool(clr[allowed[int(np.argmax(J[allowed]))]])
    if jtv is not None:
        a.clear["TV_only"] += bool(clr[allowed[int(np.argmax(jtv[allowed]))]])
    pos = clr[allowed]
    scores = {"J": J, "P": -ls["Pc"], "t_c": ls["t_c"].astype(float), "t_hit": ls["t_hit"].astype(float)}
    if jtv is not None:
        scores.update(J_tv=jtv, J0=J - jtv, E=ls["E"], trapped=-ls["trapped"].astype(float),
                      overlap=-ls["overlap"], hexp=-ls["hexp"])
    scores.update(extra)
    for k, v in scores.items():
        if v is None:
            continue
        u, p = auc_counts(np.asarray(v, float)[allowed], pos)
        a.auc[k][0] += u
        a.auc[k][1] += p
    return clr, scores, allowed


def run_episode(pol, run: Path, inst: int, ep: int, frames: int, acc: dict) -> dict:
    from ssbot.combat.forum_planner import ForumPlanner
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.encounters import ENCOUNTERS
    rows = [json.loads(x) for x in (run / f"attempts_i{inst}.jsonl").read_text("utf-8").splitlines() if x]
    row = next(r for r in rows if r.get("episode") == ep)
    rd = RecordingReader(row["recording"])
    for _, m in rd.terrain():
        if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
            pol.terrain_msg = m
    pol.reset(random.Random(0), ENCOUNTERS[row["unit"]])
    assert isinstance(pol.planner, ForumPlanner)
    pol.planner.fcfg.p_all = True
    step0 = getattr(pol.sc.step, "orig", pol.sc.step)

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else \
            dataclasses.replace(r, mask=None, outcome=None)
    step.orig = step0
    pol.sc.step = step
    f0, f1 = row["f_wake"], row["f_end"]
    boxes = {}
    for s in rd.states(f0, f1 + 80):
        boxes[s["f"]] = threat_boxes(s)
    hits = [h["f"] for h in (row.get("policy") or {}).get("hit_log") or () if h.get("kind") == "damage"]
    EP_KEY[0] = f"{run.name}_i{inst}_ep{ep}"
    n = 0
    for s in rd.states(f0, f1):
        if n >= frames:
            break
        pol.planner.last_sel = None
        pol.act(s, None)
        if pol.planner.last_sel is not None and pol._mode_last == "EVADE":
            fo = int(pol.forecasts[-1][0])
            audit_tick(pol, fo, boxes, acc, pre_hit=any(0 < h - fo <= PRE_HIT_F for h in hits))
            pol.planner.last_sel = None
        n += 1
    print(f"episode {ep}: {n} states, hits {hits}", file=sys.stderr, flush=True)
    return {"run": str(run), "instance": inst, "episode": ep, "states": n, "outcome": row.get("outcome"),
            "hits": row.get("hits")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=Path, default=None)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episodes", type=int, nargs="+", default=[0])
    ap.add_argument("--frames", type=int, default=1500)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--merge", type=Path, nargs="+", default=None, help="merge these outputs instead of auditing")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dump", type=Path, default=None, help="per-tick rows (pickle, gzip) for offline rankings")
    a = ap.parse_args(argv)
    global DUMP
    if a.dump:
        DUMP = []
    if a.merge:
        outs = [json.loads(p.read_text("utf-8")) for p in a.merge]
        out = {"episodes": [e for o in outs for e in o["episodes"]],
               **{k: Acc.merged([o[k]["raw"] for o in outs]).as_dict() for k in ACCS}}
    else:
        from ssbot.train.forum_planner_policy import ForumPlannerPolicy
        pol = ForumPlannerPolicy(threads=a.threads)
        pol.warmup()
        acc = {k: Acc() for k in ACCS}
        eps = []
        for ep in a.episodes:
            try:
                eps.append(run_episode(pol, a.run, a.instance, ep, a.frames, acc))
            except StopIteration:
                eps.append({"run": str(a.run), "instance": a.instance, "episode": ep, "missing": True})
        out = {"episodes": eps, **{k: v.as_dict() for k, v in acc.items()}}
    if DUMP is not None:
        import gzip
        import pickle
        with gzip.open(a.dump, "wb") as fh:
            pickle.dump(DUMP, fh, protocol=pickle.HIGHEST_PROTOCOL)
    txt = json.dumps(out, indent=1)
    print(txt)
    if a.out:
        a.out.write_text(txt, "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
