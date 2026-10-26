"""Map v2 reflex stage 1: THE GENERATOR VALIDATED ON LIVE PRESSES (HANDOFF 'Task reflex'; ssbot.map2.reflex).
Offline only: the bot does not import this or ssbot.map2.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_val extract --set rx [--jobs 8]
        # traces of the live blocks not in M2's cache (SP13 fp2-fp5, the Clawline chase of SP10c / SP12b, the air
        # show's other blocks) -> C:/ssbot/data/m2_play/reflex/cache/rx (M2's extract_episode)
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_val scan [--sets fit,held,old,rx] [--jobs 8]
        # every live Clawline / down slash press of the recordings: the macro as latched (from its first key: the hop
        # from the ground, else the press), her exact kin state and the Clappers at the frame before it, the window
        # type, the live outcome (the strike landed on its target in the window's target states, HP lost) -> events
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_val probes        # M0 / M4a probe trials (Idle Clappers)
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_val person        # the person's 33 slam strikes (summary)
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_val judge [--jobs 8] [--cells]
        # per press the generator's verdict for THE LIVE MACRO: (a) from her exact state with every Clapper seen,
        # (b) at its table cell (every sample point, the target only: the table's own claim) -> judged_*.pkl
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_val report      # the confusion counts -> stage1.txt

Frames: game frames (a hit-stop freeze is not a frame; M2's Episode). A press P is the first frame whose latched
ACTION mask holds the key (STATE act.mask; M0's convention).
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.map2 import clapper as cm

OUT = Path(r"C:\ssbot\data\m2_play\reflex")
M2CACHE = Path(r"C:\ssbot\data\m2_play\map2\m2\cache")
SANDBOX = Path(r"C:\ssbot\sandbox")
SETS_EXTRA = {
    "rx": ["1v1sp13_fp2", "1v1sp13_fp3", "1v1sp13_fp4", "1v1sp13_fp5", "1v1sp10ct0", "1v1sp10ct1", "1v1sp10ct2",
           "1v1sp10cfpc", "1v1sp12b_fp1", "1v1sp12b_fp2", "1v1sp12b_fp3", "1v1sp12b_fp4", "1v1air1_b2",
           "1v1air1_b3", "1v1air1_b7", "1v1air1_show1", "1v1air1_show2"],
}
KIN_KEYS = ("hero", "input", "act", "game", "fs", "dt", "udt", "ts", "ev", "pause", "f")
M_CLAW = 1 << 4
DS_CLIPS = ("DownSlash", "DownSlashAlt")
CLAW_CLIP = "Harpoon Antic"
TAIL = 18                          # frames after the (last) down slash press in a macro (the next swing's earliest)
CLAW_POST = 45                     # a down slash pressed within this many frames after a Clawline's control belongs to it
HOP_MAX = 30                       # a down slash this many frames after leaving the ground is a hop macro


def etiquette() -> int:
    """Idle priority; while DEMO_SOON.paused exists (M4's live block) at most 2 workers on the E-cores (16 - 31), else
    up to 8. Returns the worker cap."""
    try:
        import psutil
        p = psutil.Process()
        p.nice(psutil.IDLE_PRIORITY_CLASS)
        if (SANDBOX / "DEMO_SOON.paused").exists():
            p.cpu_affinity(list(range(16, 32)))
            return 2
    except Exception:
        pass
    return 8


def stop_requested() -> bool:
    return (OUT / "STOP").exists()


# ---- extract --------------------------------------------------------------------------------------------------------

def cmd_extract(a) -> int:
    from ssbot.tools import m2_clapper as mc
    cap = etiquette()
    out_dir = OUT / "cache" / a.set
    out_dir.mkdir(parents=True, exist_ok=True)
    eps = mc._episodes(SETS_EXTRA[a.set])
    jobs = [(r, m, str(out_dir)) for r, m in eps]
    res = Counter()
    t0 = time.time()
    from multiprocessing import Pool
    with Pool(min(a.jobs, cap), initializer=etiquette) as pool:
        for k, r in enumerate(pool.imap_unordered(mc._extract_one, jobs)):
            res[r.split(" ")[0]] += 1
            if r.startswith("error"):
                print(r, flush=True)
            if k % 50 == 0:
                print(f"{k + 1}/{len(jobs)} {time.time() - t0:.0f}s {dict(res)}", flush=True)
    print(f"done {len(jobs)} episodes in {time.time() - t0:.0f}s: {dict(res)}")
    return 0


# ---- the recording around an event -----------------------------------------------------------------------------------

_TERR: dict = {}


def _recording(meta: dict) -> str | None:
    run = Path(meta["run"])
    p = run / f"attempts_i{meta['inst']}.jsonl"
    if not p.exists():
        return None
    for line in p.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("episode") == meta["episode"] and r.get("recording"):
            return r["recording"]
    return None


def _terrain(rr, rec: str, params):
    from ssbot.knowledge import kinematics as km
    t = _TERR.get(rec)
    if t is None:
        for _, m in rr.terrain():
            if isinstance(m, dict) and m.get("scene_raw"):
                t = km.Terrain2D.from_message(m, params.scene(m["scene_raw"]))
                break
        _TERR.clear()
        _TERR[rec] = t
    return t


def _her_state(rr, rec: str, f_dec: int, params) -> np.ndarray | None:
    """Her kin state at the STATE frame f_dec (the estimator over the 120 frames before it, the act masks)."""
    from ssbot.knowledge import kinematics as km
    states = list(rr.states(f_dec - 120, f_dec, keys=KIN_KEYS))
    if not states or int(states[-1]["f"]) != f_dec:
        return None
    tr = km.Trace.from_states(states, params, mask_source="act")
    S = km.estimate_state(tr, [len(states) - 1], params, terrain=_terrain(rr, rec, params))
    return np.asarray(S, float).reshape(km.K, -1)[:, 0]


# ---- the scan of one trace ------------------------------------------------------------------------------------------

def _onsets(clips: list, names: tuple) -> list:
    out = []
    for i in range(1, len(clips)):
        if clips[i] in names and clips[i - 1] not in names:
            out.append(i)
    return out


def _hit_on(E, iid, g_lo: int, g_hi: int, kinds: tuple) -> int | None:
    """The first game frame in g_lo .. g_hi with a hit of one of the kinds ('down' / 'claw') on the Clapper iid."""
    best = None
    for f, ent, src, att, dmg, dead in E.tr["hits"]:
        if ent != iid:
            continue
        g = E.g_of(int(f))
        if g is None or not g_lo <= g <= g_hi:
            continue
        kind = "down" if "Down" in str(src) else "claw" if "Harpoon Damager" == str(src) else "other"
        if kind in kinds and (best is None or g < best):
            best = g
    return best


def _hp_lost(E, g_lo: int, g_hi: int) -> list:
    out = []
    for f, delta, src in E.tr["hp_ev"]:
        g = E.g_of(int(f))
        if g is not None and g_lo <= g <= g_hi:
            out.append((g, src))
    return out


def _st_j(E, iid, g: int) -> tuple:
    """The Clapper's (state, frame in it) at game frame g."""
    st = E.st(iid, g)
    ent = None
    for gg, a, b, f in reversed(E.trans[iid]):
        if gg <= g and b == st:
            ent = gg
            break
    if ent is None:
        c = E.cl[iid]
        t = c["t"][E.g2i[min(max(g, 0), E.n_g - 1)]]
        return st, int(round(float(t) * 60)) if np.isfinite(t) else 0
    return st, g - ent


def _nearest_target(E, g: int, hx: float, d: int | None) -> int | None:
    best, bd = None, 1e9
    for iid in E.iids:
        i = E.g2i[g]
        c = E.cl[iid]
        if c["st"][i] is None or c["hp"][i] <= 0 or c["dead"][i]:
            continue
        cx = float(c["pos"][i, 0])
        if d is not None and (cx - hx) * d < -1.0:
            continue
        if abs(cx - hx) < bd:
            best, bd = iid, abs(cx - hx)
    return best


def _classify(kind: str, st: str | None, j: int, cls: str | None, contact_st: tuple | None, k_exp: int | None) -> str:
    """The window type of a live press from the target's state at the decision and the strike's expected frame."""
    from ssbot.map2 import reflex as rx
    if kind == "claw":
        if st == "Slam Antic" and j <= 16:
            # by the continuation's down slash: its contact's state, else its press frame (+ 4: the contact's p50)
            if contact_st is not None:
                if rx.in_states(contact_st[0], contact_st[1], rx.SECOND_WIN):
                    return "claw_head2"
                return "claw_slam0"
            if k_exp is not None:
                return "claw_slam0" if j + k_exp >= 44 else "claw_head2"
            return "claw_slam0"
        if st == "Spell Antic" and j <= 8:
            return "cast_claw"
        if st == "Evade Scuttle" and j <= 18:
            return "evade_claw"
        if st in ("Idle", "Walk"):
            return "idle_hook"
        return f"other:claw:{st}"
    if st == "Slam Antic":
        if contact_st is not None:
            first = rx.in_states(contact_st[0], contact_st[1], rx.FIRST_WIN)
        else:
            first = k_exp is not None and j + k_exp >= 44
        if cls == "G":
            return "hop_slam0" if first else "other:ds:hop_head"
        return "drop_slam0" if first else ("pogo_head2" if j <= 42 else "other:ds:late")
    if st in ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2"):
        if contact_st is not None:
            return "pogo_jantic" if contact_st[0] == st or contact_st[0] in (
                "Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2") else "ride_up"
        return "pogo_jantic" if k_exp is not None and j + k_exp < 30 else "ride_up"
    if st == "Jump":
        return "ride_up"
    if st == "Air":
        if contact_st is not None and contact_st[0] == "Air":
            return "ride_up" if contact_st[1] <= 26 else "ride_down"
        return "ride_up" if j + (k_exp or 0) <= 26 else "ride_down"
    if st in ("Spell Antic", "Cast 1", "Cast 2") and cls != "G":
        return "pogo_cast"
    if st in ("Idle", "Walk"):
        return "idle_pogo"
    return f"other:ds:{st}"


def scan_trace(path: str) -> list:
    """Every Clawline / down slash press of one cached trace as an event (module docstring)."""
    with open(path, "rb") as fh:
        tr = pickle.load(fh)
    rec = _recording(tr["meta"])
    if rec is None or not Path(rec).exists():
        return []
    return scan_tr(tr, rec, Path(path).parent.name)


def _touched(E, g_lo: int, g_hi: int) -> list:
    """Damage contacts on her in g_lo .. g_hi (damage / blocked: the invincible probes' 'would have been hit')."""
    return [(g, sk_, kind) for (g, iid, sk_, kind) in E.contacts if g_lo <= g <= g_hi]


def scan_tr(tr: dict, rec: str, src: str, f_range: tuple | None = None) -> list:
    """Every Clawline / down slash press of a trace (M2's extract_episode format) whose recording is rec; f_range: only
    presses in these STATE frames."""
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import reflex as rx
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools import m2_validate as mv
    meta = tr["meta"]
    E = mv.Episode(tr)
    H = tr["hero"]
    F = tr["F"]
    clips = list(H["clip"])
    gi = E.gi
    claws = _onsets(clips, (CLAW_CLIP,))
    dss = _onsets(clips, DS_CLIPS)
    if not claws and not dss:
        return []
    rr = RecordingReader(rec)
    params = _params()
    # her latched masks per recorded index (the act stream), read once for the trace's span
    acts = {}
    for s in rr.states(int(F[0]), int(F[-1]), keys=("act", "f")):
        acts[int(s["f"])] = int((s.get("act") or {}).get("mask") or 0)
    mask_i = np.array([acts.get(int(f), 0) for f in F], np.int64)
    mask_g = mask_i[E.g2i]                               # per game frame (the last recorded index of each)
    ground_g = H["onGround"][E.g2i]
    mem_at = mv._memories(E)
    K = cm.Know.load()
    events = []
    used_ds = set()
    claw_ctrl = []                                        # (g press, g ctrl) of the Clawlines
    items = [("claw", i) for i in claws] + [("ds", i) for i in dss]
    items.sort(key=lambda t: t[1])
    for kind, i in items:
        gP = int(gi[i])
        if f_range is not None and not f_range[0] <= int(F[i]) <= f_range[1]:
            continue
        if kind == "claw":
            # control: the first frame after the Harpoon Catch with input accepted (the trace has no flag: the first
            # non-Harpoon clip after the press)
            gc = None
            for ii in range(i + 1, min(i + 60, len(clips))):
                if not str(clips[ii]).startswith("Harpoon"):
                    gc = int(gi[ii]) - 1
                    break
            claw_ctrl.append((gP, gc))
            # the macro's start: a hop from the ground (jump latched from the take-off to the press, <= 7 frames)
            g0 = gP
            for h in range(1, 8):
                gg = gP - h
                if gg < 1:
                    break
                if not mask_g[gg] & km.B_JUMP:
                    break
                if ground_g[gg - 1] and not mask_g[gg - 1] & km.B_JUMP:
                    g0 = gg
                    break
            # the target: the Clapper hooked, else the nearest toward the press's direction
            d = 1 if mask_g[gP] & km.B_RIGHT else -1 if mask_g[gP] & km.B_LEFT else None
            tgt = None
            for f, ent, hsrc, att, dmg, dead in tr["hits"]:
                g = E.g_of(int(f))
                if g is not None and gP <= g <= gP + 12 and str(hsrc) == "Harpoon Damager":
                    tgt = ent
                    break
            if tgt is None:
                tgt = _nearest_target(E, gP, float(E.hx[gP]), d)
            if tgt is None or tgt not in E.iids:
                continue
            # the continuation's down slash (the first press after control within CLAW_POST frames)
            ds_g = None
            if gc is not None:
                for i2 in dss:
                    g2 = int(gi[i2])
                    if gc < g2 <= gc + CLAW_POST:
                        ds_g = g2
                        used_ds.add(i2)
                        break
            hook_g = _hit_on(E, tgt, gP, gP + 12, ("claw",))
            con_g = _hit_on(E, tgt, ds_g + 2, ds_g + 11, ("down",)) if ds_g is not None else None
            # the macro ends with its strike's i-frames (contact + 8; a miss: the press + 12) - the keys after it are the
            # next controller's (the reflex hands back there; its exit check covers the rest)
            g_end = (con_g + 8 if con_g is not None else ds_g + 12) if ds_g is not None else \
                ((gc + 15) if gc is not None else gP + 50)
        else:
            if i in used_ds:
                continue
            if any(c is not None and gp <= gP <= c + CLAW_POST for (gp, c) in claw_ctrl):
                continue
            # a hop: on the ground within HOP_MAX frames, jump latched from the take-off, no other mode on the way
            g0 = gP
            gl = None
            for gg in range(gP - 1, max(gP - HOP_MAX, 1), -1):
                if ground_g[gg]:
                    gl = gg
                    break
            if gl is not None:
                ok = bool(mask_g[gl + 1] & km.B_JUMP)
                for gg in range(gl + 1, gP):
                    if mask_g[gg] & km.B_ATTACK and not mask_g[gg - 1] & km.B_ATTACK:
                        ok = False                    # a slash on the way (its recoil is not in the strike module)
                        break
                    c_ = clips[E.g2i[gg]]
                    if c_ not in ("Airborne", "Idle", "Run", "Turn", "Land") and not str(c_).startswith("Slash"):
                        ok = False
                        break
                if ok:
                    g0 = gl + 1
            d = 1 if mask_g[gP] & km.B_RIGHT else -1 if mask_g[gP] & km.B_LEFT else None
            tgt = None
            for f, ent, hsrc, att, dmg, dead in tr["hits"]:
                g = E.g_of(int(f))
                if g is not None and gP + 2 <= g <= gP + 11 and "Down" in str(hsrc):
                    tgt = ent
                    break
            if tgt is None:
                tgt = _nearest_target(E, gP, float(E.hx[gP]), None)
            if tgt is None or tgt not in E.iids:
                continue
            ds_g = gP
            hook_g = None
            con_g = _hit_on(E, tgt, gP + 2, gP + 11, ("down",))
            g_end = con_g + 8 if con_g is not None else gP + 12
        gd = g0 - 1                                       # the decision frame
        if gd < 2 or g_end >= E.n_g - 2:
            continue
        st, j = _st_j(E, tgt, gd)
        if st is None:
            continue
        contact_st = _st_j(E, tgt, con_g - 1) if con_g is not None else None   # the state it was hit in
        k_exp = (ds_g - gd + 4) if ds_g is not None else None
        # her state at the decision
        f_dec = int(F[E.g2i[gd]])
        try:
            S = _her_state(rr, rec, f_dec, params)
        except Exception as ex:                          # an estimator failure: skip, say why
            S = None
            note = repr(ex)[:120]
        if S is None:
            continue
        hc = rx.her_class(S)
        cls = hc[0] if hc is not None else None
        wt = _classify(kind, st, j, cls, contact_st, k_exp)
        # the macro (latched, game frames from the decision): pre to the press (claw) / to the end (ds)
        if kind == "claw":
            pre = mask_g[g0:gP + 1].copy()
            pre[-1] &= ~M_CLAW
            claw_d = 1 if mask_g[gP] & km.B_RIGHT else -1 if mask_g[gP] & km.B_LEFT else \
                (1 if E.cl[tgt]["pos"][E.g2i[gP], 0] > E.hx[gP] else -1)
            post = mask_g[gP + 1:g_end + 1].copy() if g_end > gP else np.zeros(0, np.int64)
            ds_abs = [ds_g - gd] if ds_g is not None else []
            raw = (pre, claw_d, post, ds_abs)
        else:
            pre = mask_g[g0:g_end + 1].copy()
            raw = (pre, 0, np.zeros(0, np.int64), [ds_g - gd])
        # the Clappers at the decision
        obs, mems = [], {}
        for jj in E.iids:
            mm = mem_at(jj, gd)
            o = E.obs(jj, gd, mm)
            if o is not None and o.st is not None:
                obs.append(o)
                mems[jj] = mm
        if not any(o.iid == tgt for o in obs):
            continue
        hz = E.ghost_hazards(gd, {o.iid for o in obs}, K)
        hp = _hp_lost(E, g0, g_end)
        touch = _touched(E, g0, g_end)
        gap = None
        if kind == "claw" and claw_ctrl[-1][1] is not None:
            gc_ = claw_ctrl[-1][1]
            ii = E.g2i[min(gc_, E.n_g - 1)]
            hb_ = H["box"][ii]
            body = E.cl[tgt]["body"][ii]
            if np.all(np.isfinite(body)) and np.all(np.isfinite(hb_)):
                xh_ = 0.5 * (hb_[0] + hb_[2])
                dd_ = 1 if E.cl[tgt]["pos"][ii, 0] > xh_ else -1
                gap = float((body[0] - hb_[2]) if dd_ > 0 else (hb_[0] - body[2]))
        live_wt = window_of(wt)
        landed = False
        if live_wt is not None:
            if live_wt.strike == "claw":
                hs = _st_j(E, tgt, hook_g - 1) if hook_g is not None else None
                landed = hs is not None and rx.in_states(hs[0], hs[1], live_wt.target)
            else:
                landed = contact_st is not None and rx.in_states(contact_st[0], contact_st[1], live_wt.target)
        ev_ = dict(src=src, ep=meta["id"], rec=rec, unit=tr.get("unit"), arm=meta.get("arm"),
                   kind=kind, wt=wt, g0=g0, gd=gd, gP=gP, g_end=g_end, f_dec=f_dec, tgt=int(tgt), st=st, j=int(j),
                   cls=cls, n_cl=len(obs), S=S, obs=obs, mems=mems, hz=hz, raw=raw,
                   live=dict(landed=bool(landed), hook=hook_g, contact=con_g, contact_st=contact_st, hp=hp,
                             touch=touch, ok=bool(landed) and not hp,
                             ds=ds_g, ctrl=(None if kind != "claw" else claw_ctrl[-1][1]), gap=gap,
                             tseq=[_st_j(E, tgt, g) for g in range(gd, g_end + 1)]))
        events.append(ev_)
    return events


def _val_windows() -> dict:
    """Validation-only window types (not in the table set): the primitives on an Idle / Walk Clapper (the M0 / M4a
    probes' kind and the bots' Idle pogos / hooks)."""
    from ssbot.map2 import reflex as rx
    idle = (("Idle", 0, 999), ("Walk", 0, 999))
    return {"idle_pogo": rx.Window("idle_pogo", "待机头顶下劈(验证)", idle, ("G", "A", "F"), "ds", "down", idle,
                                   "validation only", generated=False),
            "idle_hook": rx.WINDOWS["idle_hook"]}


def window_of(name: str):
    from ssbot.map2 import reflex as rx
    w = rx.WINDOWS.get(name)
    if w is not None and (w.generated or name == "idle_hook"):
        return w
    return _val_windows().get(name)


_PARAMS = []


def _params():
    if not _PARAMS:
        from ssbot.map2 import envelope as env
        _PARAMS.append(env.load_params(hero2=True))
    return _PARAMS[0]


def _scan_job(path: str) -> tuple:
    try:
        return path, scan_trace(path), None
    except Exception as ex:
        import traceback
        return path, [], traceback.format_exc()[-800:]


def cmd_scan(a) -> int:
    cap = etiquette()
    paths = []
    for s in a.sets.split(","):
        base = (OUT / "cache" / s) if s in SETS_EXTRA else (M2CACHE / s)
        paths += [str(p) for p in sorted(base.glob("*.pkl"))]
    if a.limit:
        paths = paths[:a.limit]
    t0 = time.time()
    events, errs = [], []
    from multiprocessing import Pool
    with Pool(min(a.jobs, cap), initializer=etiquette, maxtasksperchild=40) as pool:
        for k, (p, evs, err) in enumerate(pool.imap_unordered(_scan_job, paths)):
            events += evs
            if err:
                errs.append((p, err))
            if k % 100 == 0:
                print(f"{k + 1}/{len(paths)} {time.time() - t0:.0f}s events {len(events)} errors {len(errs)}", flush=True)
            if stop_requested():
                print("STOP: the scan cut", flush=True)
                break
    out = OUT / f"events_{a.tag}.pkl"
    with open(out, "wb") as fh:
        pickle.dump(events, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"{len(events)} events from {len(paths)} traces in {time.time() - t0:.0f}s -> {out}; errors {len(errs)}")
    for p, e in errs[:5]:
        print(p, e)
    c = Counter((e["wt"], e["live"]["ok"]) for e in events)
    for k, v in sorted(c.items()):
        print(" ", k, v)
    return 0


# ---- the M0 / M4a probes (forced trials on the Clapper; the hero invincible in M0 and in half of M4a's) -------------------

PROBE_ROWS = {"probe_m0": [Path(r"C:\ssbot\data\m2_play\map2\all_rows.pkl")],
              "probe_m4": [Path(r"C:\ssbot\data\m2_play\map2\m4\rows_b1.pkl"),
                           Path(r"C:\ssbot\data\m2_play\map2\m4\rows_b2.pkl")]}
PROBE_EXPS = ("pogo", "side", "hook", "idle_hit", "hook_touch", "hook_pd", "bounce_jump")


def _probe_job(args) -> tuple:
    src, t = args
    from ssbot.tools import m2_clapper as mc
    res = t.get("res") or {}
    f0, f1 = res.get("f0"), res.get("f1")
    rec = t.get("rec")
    if f0 is None or f1 is None or not rec:
        return [], None
    try:
        row = {"recording": str(rec), "f_wake": int(f0) - 130, "f_end": int(f1) + 10}
        meta = {"id": f"{Path(rec).name}_n{t.get('n')}_{t.get('exp')}", "run": str(rec), "inst": -1, "episode": -1,
                "arm": t.get("exp"), "unit": "Forum_W_w7"}
        tr = mc.extract_episode(row, meta)
        tr["unit"] = "Forum_W_w7"
        evs = scan_tr(tr, str(rec), src, (int(f0), int(f1)))
        for e in evs:
            e["probe"] = dict(exp=t.get("exp"), inv=res.get("inv", True), n=t.get("n"))
        return evs, None
    except Exception:
        import traceback
        return [], traceback.format_exc()[-600:]


def cmd_probes(a) -> int:
    cap = etiquette()
    jobs = []
    for src, paths in PROBE_ROWS.items():
        for p in paths:
            for t in pickle.loads(p.read_bytes()):
                if t.get("exp") in PROBE_EXPS:
                    jobs.append((src, t))
    print(f"{len(jobs)} Clapper trials: {Counter(t.get('exp') for _, t in jobs)}", flush=True)
    events, errs = [], []
    t0 = time.time()
    from multiprocessing import Pool
    with Pool(min(a.jobs, cap), initializer=etiquette, maxtasksperchild=50) as pool:
        for k, (evs, err) in enumerate(pool.imap_unordered(_probe_job, jobs)):
            events += evs
            if err:
                errs.append(err)
            if k % 100 == 0:
                print(f"{k + 1}/{len(jobs)} {time.time() - t0:.0f}s events {len(events)} errors {len(errs)}", flush=True)
    with open(OUT / "events_probes.pkl", "wb") as fh:
        pickle.dump(events, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"{len(events)} events, errors {len(errs)}: {Counter((e['wt'], e['live']['ok']) for e in events)}")
    for e in errs[:3]:
        print(e)
    return 0


# ---- the person's slam strikes of 2026-10-15 (human_keys.json 'strikes': a summary, not the recordings) ----------------

def cmd_person(a) -> int:
    """The person's strikes as hop_slam0 events: her on the ground at x_press in front of a Slam Antic (the jump
    straight up: no drift in the air in any of them), the jump at jump_k held `hold` frames, the down slash at press_k
    (antic frames, rounded: the summary is the person's input stream at half frames); the outcome landed / hp."""
    etiquette()
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import reflex as rx
    from ssbot.map2 import search as ms
    W = ms.World()
    d = json.loads(Path(r"C:\ssbot\data\m2_play\human_keys.json").read_text("utf-8"))
    events = []
    C = 33.0
    for i, s_ in enumerate(d.get("strikes", [])):
        if s_.get("jump_k") is None or s_.get("press_k") is None or s_.get("x_press") is None:
            continue
        jk = int(round(float(s_["jump_k"])))
        pk = int(round(float(s_["press_k"])))
        hold = max(int(round(float(s_.get("hold") or 2))), 2)
        x = float(s_["x_press"])
        gd = jk - 1
        S = km.initial_state(W.params, C - x, cm.FLOOR + 1.5527, ground=True, facing=1)
        o = cm.Obs(1, "Slam Antic", gd / 60.0, C, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=gd)
        t = pk - jk + 1
        raw0 = rx.render(rx.Macro("ds", hop=hold, t=t), 1)
        landed = bool(s_.get("landed"))
        hp = [h for h in (s_.get("hp") or []) if jk <= float(h[0]) <= pk + TAIL]
        events.append(dict(src="person", ep=f"{s_.get('fight')}#{i}", rec=None, unit="person", arm="person", kind="ds",
                           wt="hop_slam0", g0=jk, gd=gd, gP=pk, g_end=pk + TAIL, f_dec=gd, tgt=1, st="Slam Antic", j=gd,
                           cls="G", n_cl=1, S=S, obs=[o], mems={1: cm.Memory()}, hz=[],
                           raw=(raw0.pre, 0, raw0.post, raw0.ds),
                           live=dict(landed=landed, hook=None, contact=None, contact_st=None, hp=hp, touch=[],
                                     ok=landed and not hp, ds=pk, ctrl=None),
                           person={k: s_.get(k) for k in ("x0", "jump_k", "hold", "press_k", "contact_s0", "landed",
                                                          "hp", "toward_pre", "g0")}))
    with open(OUT / "events_person.pkl", "wb") as fh:
        pickle.dump(events, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"{len(events)} person events: ok {sum(e['live']['ok'] for e in events)}")
    return 0


# ---- the report -------------------------------------------------------------------------------------------------------

GROUPS = (("bot runs", lambda r: not str(r["src"]).startswith(("probe", "person"))),
          ("M0 / M4a probes", lambda r: str(r["src"]).startswith("probe")),
          ("the person", lambda r: r["src"] == "person"))


def _conf(rs: list, key: str) -> dict:
    """TP / FP (miss, hp) / FN / TN of the model's verdict `key` against the live outcome."""
    c = Counter()
    for r in rs:
        v = r.get(key)
        if v is None:
            c["n/a"] += 1
            continue
        live = r["live"]
        w = bool(v["window"])
        if w and live["ok"]:
            c["TP"] += 1
        elif w:
            c["FP"] += 1
            c["FP_miss" if not live["landed"] else "FP_hp"] += 1
        elif live["ok"]:
            c["FN"] += 1
        else:
            c["TN"] += 1
    return c


def _row(c: Counter) -> str:
    tp, fp, fn, tn = c["TP"], c["FP"], c["FN"], c["TN"]
    prec = f"{tp / (tp + fp):.3f}" if tp + fp else "-"
    rec_ = f"{tp / (tp + fn):.3f}" if tp + fn else "-"
    return (f"TP {tp:4d} FP {fp:3d} (miss {c['FP_miss']}, hp {c['FP_hp']}) FN {fn:4d} TN {tn:4d} n/a {c['n/a']:3d}"
            f" | precision {prec} recall {rec_}")


def _manifest_of() -> dict:
    """The run directory's name -> its live block's manifest (C:/ssbot/sandbox/<name>_manifest.txt)."""
    out = {}
    for p in sorted(SANDBOX.glob("1v1*_manifest.txt")):
        nm = p.name[:-len("_manifest.txt")]
        for line in p.read_text("utf-8-sig").splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 4 and parts[3].strip():
                out.setdefault(Path(parts[3].strip()).name, nm)
    return out


def _block(ep: str, man: dict) -> str:
    """The manifest family of an event's episode id (<run dir>_i<inst>_e<ep>)."""
    run = ep.rsplit("_i", 1)[0]
    m = man.get(run, "")
    for pre, name in (("1v1sp13_fp", "SP13 forced fixed points"), ("1v1sp13_ab", "SP13 A/B"),
                      ("1v1sp13b", "SP13b"), ("1v1sp14", "SP14"), ("1v1air1", "SP-AIR1 show"),
                      ("1v1sp10c", "SP10c"), ("1v1sp12", "SP12"), ("1v1sp11", "SP11"), ("1v1sp8", "SP8")):
        if m.startswith(pre):
            return name
    return m or "?"


def cmd_report(a) -> int:
    rs = []
    for t in a.judged.split(","):
        rs += pickle.loads((OUT / f"judged_{t}.pkl").read_bytes())
    rs = [r for r in rs if "skip" not in r and "error" not in r]
    for t in a.judged.split(","):
        pr = OUT / f"judged_{t}_real.pkl"
        if pr.exists():
            rq = {(x["ep"], x["gP"], x["wt"]): x.get("real") for x in pickle.loads(pr.read_bytes())}
            for r in rs:
                if (r["ep"], r["gP"], r["wt"]) in rq:
                    r["real"] = rq[(r["ep"], r["gP"], r["wt"])]
    for r in rs:
        c, x = r.get("cell"), r.get("exact")
        r["cellx"] = None if c is None or x is None else dict(window=bool(c["window"] and x["window"]))
    lines = [f"{len(rs)} live presses judged ({a.judged})"]
    for gname, gf in GROUPS:
        g = [r for r in rs if gf(r)]
        if not g:
            continue
        lines.append(f"\n== {gname}: {len(g)} presses ==")
        for key, label in (("cell", "TABLE CELL (the target only, every sample point)"),
                           ("cellx", "TABLE CELL + the runtime's exact check (every Clapper, hazards)"),
                           ("exact1", "exact state, the target only"),
                           ("exact", "exact state, every Clapper"),
                           ("exact_nr", "exact state, every Clapper, WITHOUT the judge's robustness"),
                           ("exact_live", "Clawline: the LIVE continuation in the realized hook variant (the model "
                                          "on the bot's own keys)"),
                           ("real", "Q1 THE MODEL ON THE LIVE KEYS IN THE REALIZED OUTCOME (its branch and timing view; "
                                    "a Clawline's hook variant nearest the live stop)")):
            lines.append(f"-- {label}")
            by = defaultdict(list)
            for r in g:
                by[r["wt"]].append(r)
            for wt in sorted(by):
                lines.append(f"  {wt:12s} n {len(by[wt]):4d}  " + _row(_conf(by[wt], key)))
            lines.append(f"  {'ALL':12s} n {len(g):4d}  " + _row(_conf(g, key)))
    # the bot runs by live block, for the key window types (the table cell and the cell + the runtime's exact check)
    man = _manifest_of()
    lines.append("\n== the bot runs by live block (TABLE CELL | CELL + exact check | exact, every Clapper) ==")
    for wt in ("claw_slam0", "hop_slam0", "drop_slam0", "pogo_head2", "pogo_cast", "pogo_jantic", "ride_down",
               "ride_up", "evade_claw", "cast_claw"):
        g = [r for r in rs if r["wt"] == wt and GROUPS[0][1](r)]
        if not g:
            continue
        by = defaultdict(list)
        for r in g:
            by[_block(r["ep"], man)].append(r)
        for b, gg in sorted(by.items()):
            cc, cx, ex = _conf(gg, "cell"), _conf(gg, "cellx"), _conf(gg, "exact")
            lines.append(f"  {wt:11s} {b:26s} n {len(gg):4d} | cell TP {cc['TP']:4d} FP {cc['FP']:2d} FN {cc['FN']:4d} "
                         f"TN {cc['TN']:3d} n/a {cc['n/a']:3d} | cell+x TP {cx['TP']:4d} FP {cx['FP']:2d} | exact TP "
                         f"{ex['TP']:4d} FP {ex['FP']:2d} FN {ex['FN']:4d} TN {ex['TN']:3d} | live ok "
                         f"{sum(r['live']['ok'] for r in gg)}")
    # why the model said no where the live press was fine (FN), per type: the first failing outcome's reason
    lines.append("\n== the false negatives' reasons (exact, every Clapper: the first failing outcome; cell: n/a = her "
                 "class not in the table) ==")
    by = defaultdict(Counter)
    for r in rs:
        v = r.get("exact")
        if v is not None and not v["window"] and r["live"]["ok"]:
            w = str(v.get("why") or "")
            by[r["wt"]][w.split("@")[0].split(":")[0] or "?"] += 1
    for wt in sorted(by):
        lines.append(f"  {wt:12s} " + ", ".join(f"{k} {n}" for k, n in by[wt].most_common()))
    na = Counter((r["wt"], r["cls"]) for r in rs if r.get("cell") is None and r.get("key") is None)
    lines.append("  cells n/a by (type, her class at the decision): " + ", ".join(f"{k} {n}" for k, n in na.most_common(12)))
    # the false positives of the table cells, one line each
    lines.append("\n== the table cells' false positives (window by the cell, live not ok) ==")
    for r in rs:
        v = r.get("cell")
        if v is not None and v["window"] and not r["live"]["ok"]:
            lv = r["live"]
            lines.append(f"  {r['wt']:11s} {r['src']:9s} {r['ep'][-44:]} gP {r['gP']} {r['st']}:{r['j']} {r['cls']} "
                         f"landed {lv['landed']} hp {lv['hp']} contact {lv.get('contact_st')} n_cl {r['n_cl']} "
                         f"exact {r.get('exact', {}).get('window')} {r.get('exact', {}).get('why')}")
    lines.append("\n== the exact verdicts' false positives (every Clapper) ==")
    for r in rs:
        v = r.get("exact")
        if v is not None and v["window"] and not r["live"]["ok"]:
            lv = r["live"]
            lines.append(f"  {r['wt']:11s} {r['src']:9s} {r['ep'][-44:]} gP {r['gP']} {r['st']}:{r['j']} {r['cls']} "
                         f"landed {lv['landed']} hp {lv['hp']} contact {lv.get('contact_st')} n_cl {r['n_cl']}")
    txt = "\n".join(lines)
    (OUT / a.out).write_text(txt + "\n", encoding="utf-8")
    print(txt)
    return 0


# ---- judge ----------------------------------------------------------------------------------------------------------

def _mirror_mask(m: np.ndarray) -> np.ndarray:
    from ssbot.knowledge import kinematics as km
    m = np.asarray(m, np.int64)
    l_ = (m & km.B_LEFT) != 0
    r_ = (m & km.B_RIGHT) != 0
    out = m & ~(km.B_LEFT | km.B_RIGHT)
    return out | np.where(l_, km.B_RIGHT, 0) | np.where(r_, km.B_LEFT, 0)


def _real_one(args) -> dict:
    """Q1 only (the model on the live keys in the realized outcome) for one event."""
    ev_, _ = args
    r = _judge_one((ev_, False), only_real=True)
    return {k: r.get(k) for k in ("ep", "gP", "wt", "real", "error")}


def _judge_one(args, only_real: bool = False) -> dict:
    """The generator's verdicts for one live press: exact (her state, every Clapper) and at its cell (the target
    only, the samples mirrored to the Clapper facing +1)."""
    ev_, cells = args
    from dataclasses import replace
    from ssbot.map2 import reflex as rx
    W, ev = _world()
    wt = window_of(ev_["wt"])
    out = dict(ep=ev_["ep"], gP=ev_["gP"], wt=ev_["wt"], kind=ev_["kind"], live=ev_["live"], cls=ev_["cls"],
               st=ev_["st"], j=ev_["j"], n_cl=ev_["n_cl"], src=ev_["src"], unit=ev_.get("unit"), arm=ev_.get("arm"))
    if wt is None:
        out["skip"] = "no window type"
        return out
    pre, claw_d, post, ds = ev_["raw"]
    if wt.family == "cl":
        # the Clawline's press as pressed live; after control the continuation is the window's own (control is a branch
        # point the reflex sees): judge_cl finds one per hook variant for a down strike; a hook-only window plays no key
        # to control + 15 (the live HP losses counted to the live control + 15 too)
        post, ds = np.zeros(1 if wt.strike == "down" else rx.CL_HOOK_END, np.int64), []
        lv = dict(ev_["live"])
        if wt.strike == "claw" and lv.get("ctrl") is not None:
            lv["hp"] = [h for h in lv["hp"] if h[0] <= lv["ctrl"] + 15]
            lv["ok"] = bool(lv["landed"]) and not lv["hp"]
        out["live"] = lv
    live_post, live_ds = ev_["raw"][2], ev_["raw"][3]
    macro = rx.Macro(wt.family, raw=(pre, claw_d, post, ds))
    jf = rx.judge_cl if wt.family == "cl" else rx.judge
    t0 = time.perf_counter()
    try:
        if only_real:
            raise _OnlyReal()
        v = jf(W, ev, ev_["S"], ev_["obs"], ev_["tgt"], wt, macro, mems=ev_["mems"], hazards=ev_["hz"])
        out["exact"] = _vd(v)
        vn = jf(W, ev, ev_["S"], ev_["obs"], ev_["tgt"], wt, macro, mems=ev_["mems"], hazards=ev_["hz"],
                robust=False)
        out["exact_nr"] = _vd(vn)                     # without the judge's robustness (the search's own settings)
        tgt = next(o for o in ev_["obs"] if o.iid == ev_["tgt"])
        v1 = jf(W, ev, ev_["S"], [tgt], ev_["tgt"], wt, macro, mems={tgt.iid: ev_["mems"].get(tgt.iid)
                                                                       or cm.Memory()})
        out["exact1"] = _vd(v1)
    except _OnlyReal:
        pass
    except Exception as ex:
        import traceback
        out["error"] = traceback.format_exc()[-600:]
        out["ms"] = (time.perf_counter() - t0) * 1e3
        return out
    try:
        tgt = next(o for o in ev_["obs"] if o.iid == ev_["tgt"])
        # Q1, THE MODEL ON THE LIVE KEYS IN WHAT HAPPENED: the live macro (its live continuation too) judged only in
        # the outcomes whose target state sequence matches the live one best (the realized branch and timing view)
        # and, for a Clawline, the hook variant nearest the live stop
        tseq = ev_["live"].get("tseq")
        if tseq:
            sel = _realized(tseq, ev_["tgt"])
            gap_ = ev_["live"].get("gap")
            vv_ = None
            if wt.family == "cl" and gap_ is not None:
                vv_ = (min(rx.judge_variants(tgt) + (rx.FAR,), key=lambda v_: abs(v_.gap - gap_)),)
            if wt.family == "cl" and (wt.strike == "claw" or live_ds) and (vv_ is not None or wt.strike == "claw"):
                ml = rx.Macro(wt.family, raw=(pre, claw_d, live_post if wt.strike == "down" else post,
                                               live_ds if wt.strike == "down" else []))
                out["real"] = _vd(rx.judge(W, ev, ev_["S"], ev_["obs"], ev_["tgt"], wt, ml, mems=ev_["mems"],
                                           hazards=ev_["hz"], variants=vv_, select=sel))
            elif wt.family == "ds":
                out["real"] = _vd(rx.judge(W, ev, ev_["S"], ev_["obs"], ev_["tgt"], wt, macro, mems=ev_["mems"],
                                           hazards=ev_["hz"], select=sel))
        gap = ev_["live"].get("gap")
        if wt.family == "cl" and wt.strike == "down" and gap is not None and live_ds and not only_real:
            # Q1, the model's fidelity on the live keys: the live macro WITH its live continuation, in the hook
            # variant whose stop gap is nearest the live one (control is where the bot re-planned its strike)
            vv = min(rx.judge_variants(tgt) + (rx.FAR,), key=lambda v_: abs(v_.gap - gap))
            ml = rx.Macro(wt.family, raw=(pre, claw_d, live_post, live_ds))
            out["exact_live"] = _vd(rx.judge(W, ev, ev_["S"], ev_["obs"], ev_["tgt"], wt, ml, mems=ev_["mems"],
                                             hazards=ev_["hz"], variants=(vv,)))
            out["live_var"] = vv.name
        if cells and not only_real:
            key = rx.cell_of(ev_["S"], tgt, wt)
            out["key"] = key
            if key is None:
                out["cell"] = None
            else:
                m2 = macro
                if tgt.face < 0:
                    m2 = rx.Macro(wt.family, raw=(_mirror_mask(pre), -claw_d, _mirror_mask(post), ds))
                ok, vs = rx.judge_cell(W, ev, key, wt, m2, replace(tgt), stop=True)
                out["cell"] = dict(window=bool(ok), n=len(vs), why=next((x.why for x in vs if not x.window), ""))
    except Exception as ex:
        import traceback
        out["error"] = traceback.format_exc()[-600:]
    out["ms"] = (time.perf_counter() - t0) * 1e3
    return out


def _realized(tseq: list, iid: int):
    """A selector of the outcomes whose target state sequence (state, frame in it) over the macro's frames matches the
    live one best (the fewest mismatching frames)."""
    from ssbot.map2 import reflex as rx

    def sel(outs: list) -> list:
        sc = []
        for o in outs:
            bad = 0
            for k, lv in enumerate(tseq):
                st = rx._state_near(o.branch, iid, k)
                if st is None or lv[0] is None or st[0] != lv[0] or abs(int(st[1]) - int(lv[1])) > 1:
                    bad += 1                     # (a frame of slack: a reaction a frame later is the same branch)
            sc.append(bad)
        if not sc:
            return outs
        m = min(sc)
        return [o for o, b in zip(outs, sc) if b == m]
    return sel


class _OnlyReal(Exception):
    pass


def _vd(v) -> dict:
    return dict(window=v.window, lands=v.lands, safe=v.safe, exit=v.exit, n=v.n, why=v.why, k=v.k_strike, end=v.end,
                ms=round(v.ms, 1), cont=getattr(v, "cont", ()))


_WEV = []


def _world():
    if not _WEV:
        from ssbot.map2 import reflex as rx
        from ssbot.map2 import search as ms
        W = ms.World()
        _WEV.append((W, rx.judge_evaluator(W)))
    return _WEV[0]


def cmd_judge(a) -> int:
    cap = etiquette()
    evs = []
    for t in a.tags.split(","):
        with open(OUT / f"events_{t}.pkl", "rb") as fh:
            evs += pickle.load(fh)
    if a.wt:
        evs = [e for e in evs if e["wt"] in a.wt.split(",")]
    else:
        evs = [e for e in evs if window_of(e["wt"]) is not None]
    if a.limit:
        evs = evs[:a.limit]
    print(f"{len(evs)} events: {Counter(e['wt'] for e in evs)}", flush=True)
    t0 = time.time()
    res = []
    from multiprocessing import Pool
    jobs = [(e, a.cells) for e in evs]
    fn = _real_one if a.only == "real" else _judge_one
    with Pool(min(a.jobs, cap), initializer=etiquette, maxtasksperchild=200) as pool:
        for k, r in enumerate(pool.imap_unordered(fn, jobs, chunksize=4)):
            res.append(r)
            if k % 200 == 0:
                print(f"{k + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
            if stop_requested():
                print("STOP: the judge cut", flush=True)
                break
    out = OUT / f"judged_{a.out}.pkl"
    with open(out, "wb") as fh:
        pickle.dump(res, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"{len(res)} judged in {time.time() - t0:.0f}s -> {out}; errors {sum(1 for r in res if 'error' in r)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract")
    p.add_argument("--set", default="rx")
    p.add_argument("--jobs", type=int, default=8)
    p = sub.add_parser("scan")
    p.add_argument("--sets", default="fit,held,old,rx")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tag", default="all")
    p = sub.add_parser("judge")
    p.add_argument("--tags", default="all")
    p.add_argument("--out", default="all")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--wt", default="")
    p.add_argument("--cells", action="store_true")
    p.add_argument("--only", default="", help="real: only Q1 (merged into judged_<out without _real> by the report)")
    p = sub.add_parser("probes")
    p.add_argument("--jobs", type=int, default=8)
    sub.add_parser("person")
    p = sub.add_parser("report")
    p.add_argument("--judged", default="all")
    p.add_argument("--out", default="stage1_tables.txt")
    a = ap.parse_args(argv)
    return {"extract": cmd_extract, "scan": cmd_scan, "judge": cmd_judge, "probes": cmd_probes,
            "person": cmd_person, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
