"""Acceptance test of the hero kinematics model (M2 exit item, DESIGN §3.5.2): over every 30-frame window of logged
play, roll the model forward from the logged state at the window start with the logged buttons, and compare the
collider position after 0.5 s with the logged one (hero.box; the rendered hero.pos is reported beside it). Target:
99 % of windows within 0.1 u.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.kin_check <source> [<source> ...] [--horizon 30] [--tol 0.1]
        [--scene Bone_05] [--params knowledge/1.0.30000/kinematics/hero_hunter.json] [--json report.json] [--worst 20]

A source is a recording directory (ssbot.record.recorder), a human session (ssbot.tools.human_session:
state.raw.zst) or a fixture .npz (save_fixture). Three settings, all reported:
  input_only   logged timing (dt, udt and the 0 / 1 / 2 physics steps of each frame from the log), no contact events:
               what the buttons alone determine;
  with_events  logged timing and the logged contact events injected (nail recoil, recoil down, pogo, damage, silk
               gain, early Silkspear catch, external lock), which the threat layer has to predict at run time: the
               acceptance figure for the model itself;
  nominal      with_events, but the planner's timing: HeroParams.frame_time per frame, physics steps and the hit-stop
               time scale from the model's own clock (frame-time jitter flips 0.02 s step boundaries, so this one
               is lower; it is what a planner without the oracle's timing gets).
Every window lands in exactly one category (first match): uncovered:<why> (harness teleports, hazard respawns,
scene changes, deaths, control taken by another FSM, no terrain for the scene, nail-charge arts), hurt (a damage
knockback inside), contact (nail recoil, recoil down, pogo or an early Silkspear catch inside), cast, bind,
downspike, recovering (starts in the damage freeze / recoil), plain. Nothing is dropped: uncovered windows are
counted and listed by reason, and the "all" figures include them; "covered" leaves only the uncovered ones out.
Hit-stops the hero does not cause (enemy hits, boss stuns) only scale time, which the logged dt carries; windows
with one are counted as "time_freeze" beside the categories. Arena gates (scene overrides "enable") are world
state: a window runs with them closed unless a logged box of that window overlaps one.

The knockback section replays every logged hit through knockback_envelope from the state before it and counts the
no-input frames whose logged collider box stays inside the envelope.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.knowledge.kinematics import HeroParams, Terrain2D, Trace

STATE_KEYS = ("hero", "input", "act", "game", "fs", "dt", "udt", "ts", "ev", "pause")


# ---- sources --------------------------------------------------------------------------------------------------

def load_source(path: str | Path, params: HeroParams, scene_filter: str | None = None
                ) -> tuple[Trace, dict[str, Terrain2D]]:
    """(trace, {scene: terrain}) from a recording, a human session or a fixture."""
    path = Path(path)
    if path.suffix == ".npz":
        tr, terrains = load_fixture(path)
    elif (path / "state.raw.zst").is_file():
        from ssbot.ipc.framing import MsgType
        from ssbot.tools.raw_session import messages
        states, terr = [], {}
        for t, m in messages(path):
            if t == MsgType.STATE:
                states.append({k: m.get(k) for k in (*STATE_KEYS, "f")})
            elif t == MsgType.TERRAIN and m.get("scene_raw"):
                terr.setdefault(m["scene_raw"], m)
        tr = Trace.from_states(states, params)
    else:
        from ssbot.record.recorder import RecordingReader
        r = RecordingReader(path)
        tr = Trace.from_states(r.states(keys=STATE_KEYS), params)
        terr = {}
        for _, m in r.terrain():
            if isinstance(m, dict) and m.get("scene_raw"):
                terr.setdefault(m["scene_raw"], m)
    if path.suffix != ".npz":
        terrains = {name: Terrain2D.from_message(m, params.scene(name)) for name, m in terr.items()}
    if scene_filter:
        keep = np.array([tr.scenes[i] == scene_filter for i in tr.scene])
        tr.valid = tr.valid & keep
    return tr, terrains


def save_fixture(path: str | Path, tr: Trace, terrains: dict[str, Terrain2D]) -> None:
    """A trace plus its scenes' collision segments in one .npz (tests, offline checks)."""
    extra = {}
    for name, t in terrains.items():
        extra[f"terrain_h::{name}"] = t.hseg
        extra[f"terrain_v::{name}"] = t.vseg
        extra[f"terrain_g::{name}"] = t.gates
        extra[f"terrain_n::{name}"] = np.array(t.n_base, dtype=np.int64)
    d = {}
    from dataclasses import fields
    for f in fields(tr):
        d[f.name] = getattr(tr, f.name)
    meta = {k: d.pop(k) for k in ("clips", "spells", "scenes", "mask_source")}
    np.savez_compressed(path, meta=json.dumps(meta), **d, **extra)


def load_fixture(path: str | Path) -> tuple[Trace, dict[str, Terrain2D]]:
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    names = [k for k in z.files if k != "meta" and not k.startswith("terrain_")]
    tr = Trace(**{k: z[k] for k in names}, **meta)
    terrains = {}
    for k in z.files:
        if k.startswith("terrain_h::"):
            name = k.split("::", 1)[1]
            g = z[f"terrain_g::{name}"] if f"terrain_g::{name}" in z.files else np.zeros((0, 4))
            nb = tuple(int(x) for x in z[f"terrain_n::{name}"]) if f"terrain_n::{name}" in z.files else (-1, -1)
            terrains[name] = Terrain2D(z[k], z[f"terrain_v::{name}"], np.zeros((0, 4)), [], g, nb)
    return tr, terrains


# ---- windows --------------------------------------------------------------------------------------------------

CATEGORIES = ("plain", "downspike", "cast", "bind", "recovering", "contact", "hurt")
SETTINGS = ("input_only", "with_events", "nominal")
CONTACT = km.EV_RECOIL_L | km.EV_RECOIL_R | km.EV_POGO | km.EV_CATCH | km.EV_RECOIL_DOWN


def window_starts(tr: Trace, horizon: int) -> np.ndarray:
    """Rows i such that rows i..i+horizon are consecutive frames with the hero present in gameplay."""
    good = tr.valid & np.isfinite(tr.phys[:, 0]) & np.r_[True, np.diff(tr.f) == 1]
    bad = np.cumsum(~good)
    i = np.arange(len(tr) - horizon)
    ok = (bad[i + horizon] - bad[i] == 0) & good[i]
    return i[ok]


def categorize(tr: Trace, starts: np.ndarray, horizon: int, modes: np.ndarray, events: np.ndarray,
               terrains: dict) -> np.ndarray:
    """Category label per window (see the module docstring)."""
    I = starts[:, None] + np.arange(0, horizon + 1)[None, :]
    lab = np.full(len(starts), "plain", dtype=object)
    mw = modes[I]
    ew = events[I[:, 1:]]
    mk = tr.marks[I]
    charge = tr.flag("nailCharging")[I].any(axis=1)
    scene_ok = np.array([tr.scenes[s] in terrains for s in tr.scene[starts]])
    order = [  # later entries win
        ("downspike", np.isin(mw, (km.M_DS_ANTIC, km.M_DS_SPIKE)).any(axis=1)),
        ("cast", (mw == km.M_CAST).any(axis=1)),
        ("bind", (mw == km.M_BIND).any(axis=1)),
        ("recovering", np.isin(mw[:, 0], (km.M_HURT_FREEZE, km.M_HURT_RECOIL))),
        ("contact", (ew & CONTACT).any(axis=1)),
        ("hurt", (ew & (km.EV_HURT_L | km.EV_HURT_R)).any(axis=1)),
        ("uncovered:nail_charge", charge),
        ("uncovered:locked", (mw == km.M_LOCKED).any(axis=1)),
        ("uncovered:scene", (mk & km.MK_SCENE).any(axis=1)),
        ("uncovered:death", (mk & km.MK_DEATH).any(axis=1)),
        ("uncovered:hazard", (mk & km.MK_HAZARD).any(axis=1)),
        ("uncovered:harness", (mk & km.MK_HARNESS).any(axis=1)),
        ("uncovered:no_terrain", ~scene_ok),
    ]
    for name, sel in order:
        lab[sel] = name
    return lab


def _stats(err: np.ndarray, tol: float) -> dict:
    if len(err) == 0:
        return {"n": 0}
    return {"n": int(len(err)), "within": round(float(np.mean(err <= tol)), 5),
            "p50": round(float(np.percentile(err, 50)), 4), "p95": round(float(np.percentile(err, 95)), 4),
            "p99": round(float(np.percentile(err, 99)), 4), "max": round(float(err.max()), 3)}


def check_trace(tr: Trace, terrains: dict[str, Terrain2D], params: HeroParams, horizon: int = 30,
                tol: float = 0.1, worst: int = 0, batch: int = 8192) -> dict:
    """Run every window of one trace in the three settings; returns the per-window errors."""
    modes = km.classify_modes(tr)
    events = km.derive_events(tr, modes)
    alpha = km.phase(tr, params.fdt)
    starts = window_starts(tr, horizon)
    labels = categorize(tr, starts, horizon, modes, events, terrains)
    table = km.state_table(tr, params, modes, alpha)
    I = starts[:, None] + np.arange(0, horizon + 1)[None, :]
    out = {"starts": starts, "labels": labels, "time_freeze": (tr.marks[I] & km.MK_FREEZE).any(axis=1)}
    for setting in SETTINGS:
        e_phys = np.full(len(starts), np.nan)
        e_pos = np.full(len(starts), np.nan)
        groups = []
        for scene_i in np.unique(tr.scene[starts]):
            name = tr.scenes[scene_i]
            sel = np.flatnonzero(tr.scene[starts] == scene_i)
            terrain = terrains.get(name, Terrain2D.empty())
            # arena gates (scene overrides "enable") are world state the hero model does not own: a window runs with
            # them closed unless a logged box of the window overlaps one (the hero walked through an open gate)
            closed = np.ones(len(sel), dtype=bool)
            for g in terrain.gates:
                W = starts[sel][:, None] + np.arange(0, horizon + 1)[None, :]
                b = tr.box[W]
                hit = (b[..., 2] > g[0]) & (b[..., 0] < g[2]) & (b[..., 3] > g[1]) & (b[..., 1] < g[3])
                closed &= ~hit.any(axis=1)
            groups.append((sel[closed], terrain))
            groups.append((sel[~closed], terrain.open()))
        for sel, terrain in groups:
            for b0 in range(0, len(sel), batch):
                part = sel[b0:b0 + batch]
                st = starts[part]
                S = km.estimate_state(tr, st, params, terrain=terrain, table=table)
                I = st[:, None] + np.arange(1, horizon + 1)[None, :]
                ev = None if setting == "input_only" else events[I]
                if setting == "nominal":
                    r = km.rollout(S, tr.mask[I], params, terrain, events=ev)
                else:
                    r = km.rollout(S, tr.mask[I], params, terrain, events=ev, dt=tr.dt[I], fs=tr.fs[I],
                                   udt=tr.udt[I])
                end = st + horizon
                e_phys[part] = np.linalg.norm(r.phys[:, horizon] - tr.phys[end], axis=1)
                e_pos[part] = np.linalg.norm(r.pos[:, horizon] - tr.pos[end], axis=1)
        out[setting] = {"phys": e_phys, "pos": e_pos}
    return out


def check_knockback(tr: Trace, terrains: dict[str, Terrain2D], params: HeroParams, tol: float = 0.02) -> dict:
    """Every logged hit (StartRecoil: recoilFrozen onset) against knockback_envelope from the state before it: the
    logged collider box must stay inside the envelope's union while the hero has no control."""
    modes = km.classify_modes(tr)
    table = km.state_table(tr, params, modes, km.phase(tr, params.fdt))
    hits = np.flatnonzero(tr.flag("recoilFrozen") & ~np.r_[False, tr.flag("recoilFrozen")[:-1]])
    n_hits, frames, inside, worst = 0, 0, 0, 0.0
    for i in hits:
        if i < 1 or not tr.valid[i - 1] or tr.dmg[i] == 0:
            continue
        terrain = terrains.get(tr.scenes[tr.scene[i]], Terrain2D.empty())
        S = km.estimate_state(tr, [i - 1], params, terrain=terrain, table=table)
        env = km.knockback_envelope(S, "left" if tr.dmg[i] < 0 else "right", params, terrain)
        n_hits += 1
        for k in range(len(env.union)):
            j = i + k
            if j >= len(tr) or modes[j] not in km.NO_INPUT:
                break
            b, u = tr.box[j], env.union[k]
            out = max(u[0] - b[0], u[1] - b[1], b[2] - u[2], b[3] - u[3], 0.0)
            frames += 1
            inside += out <= tol
            worst = max(worst, out)
    return {"hits": n_hits, "frames": frames, "inside": round(inside / frames, 5) if frames else None,
            "worst_excursion_u": round(worst, 4), "tol_u": tol}


def summarize(results: list[dict], tol: float, horizon: int) -> dict:
    labels = np.concatenate([r["labels"] for r in results]) if results else np.array([], dtype=object)
    rep: dict = {"horizon_frames": horizon, "tol_u": tol, "windows": int(len(labels)),
                 "categories": dict(Counter(labels.tolist()).most_common()),
                 "time_freeze_windows": int(sum(int(r["time_freeze"].sum()) for r in results)),
                 "knockback": [r["knockback"] for r in results if "knockback" in r]}
    covered = np.array([not lab.startswith("uncovered") for lab in labels], dtype=bool)
    for setting in SETTINGS:
        e_phys = np.concatenate([r[setting]["phys"] for r in results]) if results else np.zeros(0)
        e_pos = np.concatenate([r[setting]["pos"] for r in results]) if results else np.zeros(0)
        s = {"all": {"phys": _stats(e_phys, tol), "pos": _stats(e_pos, tol)},
             "covered": {"phys": _stats(e_phys[covered], tol), "pos": _stats(e_pos[covered], tol)},
             "by_category": {}}
        for cat in sorted(set(labels.tolist())):
            m = labels == cat
            s["by_category"][cat] = {"phys": _stats(e_phys[m], tol), "pos": _stats(e_pos[m], tol)}
        rep[setting] = s
    return rep


def format_report(rep: dict) -> str:
    lines = [f"windows {rep['windows']} (horizon {rep['horizon_frames']} frames, tol {rep['tol_u']} u)"]
    for kb in rep.get("knockback", ()):
        lines.append(f"knockback: {kb['hits']} hits, {kb['frames']} no-input frames, inside envelope {kb['inside']} "
                     f"(worst excursion {kb['worst_excursion_u']} u)")
    for setting in SETTINGS:
        s = rep[setting]
        a, c = s["all"], s["covered"]
        lines.append(f"{setting}: all {a['phys'].get('within', 0):.4f} (pos {a['pos'].get('within', 0):.4f})"
                     f"  covered {c['phys'].get('within', 0):.4f} (pos {c['pos'].get('within', 0):.4f},"
                     f" n={c['phys'].get('n', 0)})")
        for cat, v in s["by_category"].items():
            p = v["phys"]
            lines.append(f"   {cat:24s} n={p['n']:6d} within={p.get('within', 0):.4f} p50={p.get('p50', 0):.4f} "
                         f"p99={p.get('p99', 0):.3f} max={p.get('max', 0):.2f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--params", default=str(km.DEFAULT_PARAMS))
    ap.add_argument("--horizon", type=int, default=30)
    ap.add_argument("--tol", type=float, default=0.1)
    ap.add_argument("--scene", default=None, help="only windows in this scene")
    ap.add_argument("--json", default=None, help="write the report here")
    ap.add_argument("--worst", type=int, default=10, help="list the worst covered windows (with_events)")
    a = ap.parse_args(argv)
    params = HeroParams.load(a.params)
    results = []
    for src in a.sources:
        t0 = time.time()
        tr, terrains = load_source(src, params, a.scene)
        res = check_trace(tr, terrains, params, a.horizon, a.tol)
        res["knockback"] = check_knockback(tr, terrains, params)
        res["source"] = src
        results.append(res)
        print(f"{src}: {len(tr)} frames, {len(res['starts'])} windows, {time.time() - t0:.1f} s", file=sys.stderr)
        if a.worst:
            e = res["with_events"]["phys"]
            cov = np.array([not lab.startswith("uncovered") for lab in res["labels"]])
            order = np.argsort(-np.where(cov, e, -1))[:a.worst]
            for k in order:
                if e[k] > a.tol:
                    f0 = int(tr.f[res["starts"][k]])
                    print(f"   worst f={f0} err={e[k]:.3f} {res['labels'][k]}", file=sys.stderr)
    rep = summarize(results, a.tol, a.horizon)
    rep["sources"] = a.sources
    rep["params"] = a.params
    print(format_report(rep))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
