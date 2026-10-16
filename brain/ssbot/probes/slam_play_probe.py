"""Fixed-point live trials of the slam playbook (task 1v1 SP1, forum.md 65): the hero waits on the ground D u in front
of the Clapper (centre to centre, following it), and from the first STATE that reads Slam Antic the playbook's own
code (ssbot.combat.slam_play.SlamPlay.step, the policy's call) decides every frame; its mask for STATE f is sent for
f + 2 as the episode loop does (ssbot.train.episode._act), with an optional sleep before the send that stands in for
the planner's tick (--tick-ms). When the playbook declines or aborts the probe stands still (no key).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.slam_play_probe --instance 0 --dists 4.5,5.5,6.5,7.5 --per 20 \
        [--seed 1] [--tick-ms 0] [--savestate fo_cl_w7w] [--out C:/ssbot/data/m2_play/live] [--freeze 3:12]

The game clock (SP2): the probe sums the STATEs' scaled dt (a skipped frame at the current time scale) and passes it
to the playbook like the policy's Stamp.t_game_s (SSBOT_FORUM_SLAM_PLAY_CLOCK=0: the frame count of SP1). --freeze K:N
stands in for the live hit stop (SP2: a hit across 80 / 50 / 20 HP froze the game ~12 frames): at antic frame K the
time scale goes to 1e-4 for N STATE frames, then back to 1.
--skid N (SP4, the sprint skid of the live declines): at the antic sighting the probe dashes toward the Clapper (dash +
the direction 3 frames), holds the direction (a sprint) to frame N - 2, then the other direction 2 frames (a Sprint
Turn: no input for 10-30 frames, as after a planner dash + run); the playbook steps from frame N. (SP4 t1: from 8.5-9.5
u it ended 3.5-4.1 u in front still accepting input: no Sprint Turn lock - the emulation does not hold.)
--umbrella (SP4, with --hop H: the live "no input" declines in the air): each hop presses the jump again UMB_AT frames
after its start (in the air: the umbrella, no input for ~15-25 frames), so some antics begin with her gliding.
--stall P:S:N (SP4 item 2, the stall of run 065013): P STATE frames after the press was sent, the time scale S (<= 4,
DebugMod's path) for N STATE frames, then 1: Update runs once per frame with S x dt (the live stall: one frame of 7.0,
6 physics steps). The rows carry the STATE dt / fs; the trial's "stall" the realized frames and game time.

Per trial (<recording>/play_trials.jsonl): the distance class, the hero's x at the antic sighting, the playbook's run
(start / jump / press frames it sent, its end and why), and from the STATEs (act.mask = the keys the game held): the
antic entry fa, Slam 0 / Slam 1 / Slam Recover entries, the real jump and press frames, landed (the Clapper lost HP
within 14 frames of the press), bounce (vy > 6 within 14 frames after the press), the hero's damage (frame relative to
Slam 0, source) until the Slam Recover ends and after it (to the end of the trial), success = landed and no damage
until the Slam Recover ends. Settings env SSBOT_FORUM_SLAM_PLAY_SET (slam_play.PlayCfg.from_env).

Safety: a free training instance; save suppression and LethalBlock on; no invincibility; the time scale is set to 1.0
at the start (the instances are left frozen at 1e-4 between runs).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import replace
from pathlib import Path

from ssbot.combat import slam_play as sp
from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.probes.pogo_target import MIN_HP, Target, stop_requested

M_L, M_R, M_J, M_A = mask("left"), mask("right"), mask("jump"), mask("attack")
M_DASH = mask("dash")
M_D = mask("down")
WAIT_S = 12.0
SETTLE_F = 30
MAX_F = 260
UMB_AT = 12                 # --umbrella: the second jump press this many frames into each hop


def _ctl(e) -> str | None:
    return sp.control(e)[0]


class PlayProbe(Target):
    def __init__(self, link: OracleLink, savestate: str, tick_ms: float, pin: bool = False, hop: int = 0,
                 freeze: tuple[int, int] | None = None, skid: int = 0, umbrella: bool = False,
                 stall: tuple[int, float, int] | None = None, slash: int = 0):
        super().__init__(link, savestate)
        self.slash = slash
        self.hop = hop
        self.skid = skid
        self.umbrella = umbrella
        self.stall = stall
        self.freeze = freeze
        self.tg = 0.0                                     # the game clock (s): the sum of the STATEs' scaled dt
        self.tick_ms = tick_ms
        self.play = sp.SlamPlay()
        self.base = self.play.cfg
        self.pin = pin

    def scale1(self) -> None:
        r = self.link.rpc("time.scale", timeout_s=10, scale=1.0)
        t0 = time.monotonic()
        while abs(float((r or {}).get("time_scale") or 0.0) - 1.0) > 1e-3 and time.monotonic() - t0 < 5:
            time.sleep(0.2)
            r = self.link.rpc("time.scale", timeout_s=10)

    def load(self) -> dict:
        self.scale1()
        s = super().load()
        self.scale1()
        return s

    def follow_mask(self, s: dict, d: float) -> int:
        e = sp.clapper(s)
        if e is None:
            return 0
        tx = self.side_x(s, d)
        st = _ctl(e)
        if st == "Evade Scuttle" or abs(abs(sp.hero_x(s) - float(e["pos"][0])) - d) > 0.3:
            return self.walk_mask(s, tx)
        return 0

    def trial(self, d: float) -> dict:
        link = self.link
        s = link.wait_state(newer_than=link.frame, timeout_s=3.0)
        e = sp.clapper(s)
        hp = int(s["hero"].get("health") or 0)
        if e is None or hp < MIN_HP or (e.get("hp") or 0) < 70:
            s = self.load()
        last = s["f"]
        if self.pin:
            # --pin: the strike from D itself (the stand band pinned at D, the jump band around it): x at the jump
            # classes, the band's edges
            b = self.base
            self.play.cfg = replace(b, stand=(d - 0.12, d + 0.12), band=(min(b.band[0], d - 0.3), max(b.band[1], d + 0.3)),
                                    reach=(2.7, max(b.reach[1], d + 1.5)))
        self.play.reset()
        t0 = time.time()
        seen = None
        rows, n_after = [], 0
        fz = None                                         # --freeze: {"f0", "f1", "k"}
        stl = None                                        # --stall: {"f_press", "f0", "f1"}
        self.tg += float(s.get("dt") or 0.0)
        while True:
            e = sp.clapper(s)
            st = _ctl(e)
            if seen is None:
                if st == "Slam Antic":
                    seen = {"f": s["f"], "x": round((sp.hero_x(s) - float(e["pos"][0])) * (1 if e.get("flipX") else -1), 3),
                            "ground": sp.on_ground(s), "vx": round(float((s["hero"].get("vel") or [0, 0])[0]), 2),
                            "vy": round(float((s["hero"].get("vel") or [0, 0])[1]), 2),
                            "y": round(float(s["hero"]["pos"][1]), 3),
                            "accepting": bool(s["hero"].get("hero_accepting_input", True)),
                            "k0": int(round(sp.control(e)[1] * 60.0))}
                elif time.time() - t0 > WAIT_S:
                    return {"skip": "no slam"}
            if seen is None:
                m = self.follow_mask(s, d)
                if self.hop and (s["f"] // self.hop) % 2 == 0 and s["f"] % self.hop < 8:
                    m |= M_J                              # --hop: a short hop every 2 x HOP frames (airborne starts)
                if (self.hop and self.umbrella and (s["f"] // self.hop) % 2 == 0
                        and UMB_AT <= s["f"] % self.hop < UMB_AT + 2):
                    m |= M_J                              # --umbrella: the jump again in the air (the umbrella opens)
                if self.slash and e is not None and s["f"] % self.slash < 2 and abs(sp.hero_x(s) - float(e["pos"][0])) <= 5.2:
                    # --slash N (SP6): the planner's slashes while it idles (a cooldown and a knock-back at the antic)
                    m = (m & ~(M_L | M_R)) | M_A | (M_R if float(e["pos"][0]) > sp.hero_x(s) else M_L)
            else:
                if self.freeze is not None:
                    ka = s["f"] - seen["f"] + seen["k0"]          # STATE frames from the antic entry
                    if fz is None and ka >= self.freeze[0]:
                        link.rpc("time.scale", timeout_s=10, scale=1e-4)
                        fz = {"k": ka, "f0": s["f"], "f1": None}
                    elif fz is not None and fz["f1"] is None and s["f"] - fz["f0"] >= self.freeze[1]:
                        link.rpc("time.scale", timeout_s=10, scale=1.0)
                        fz["f1"] = s["f"]
                if self.stall is not None:
                    run_ = self.play.run if self.play.run is not None else (self.play.done[-1] if self.play.done else None)
                    if stl is None and run_ is not None and run_.k_press is not None:
                        stl = {"f_press": s["f"], "f0": None, "f1": None}
                    if stl is not None and stl["f0"] is None and s["f"] >= stl["f_press"] + self.stall[0]:
                        link.rpc("time.scale", timeout_s=10, scale=float(self.stall[1]))
                        stl["f0"] = s["f"]
                    elif stl is not None and stl["f0"] is not None and stl["f1"] is None and                             s["f"] - stl["f0"] >= self.stall[2]:
                        link.rpc("time.scale", timeout_s=10, scale=1.0)
                        stl["f1"] = s["f"]
                ks = s["f"] - seen["f"]
                if self.skid and ks < self.skid:
                    # --skid: dash + sprint toward it, then the other way (a Sprint Turn), the playbook not yet asked
                    tw = M_R if float(e["pos"][0]) > sp.hero_x(s) else M_L
                    m = (tw | M_DASH) if ks < 3 else (tw if ks < self.skid - 2 else (M_L | M_R) & ~tw)
                    seen.setdefault("skid_tw", tw)
                    if ks == self.skid - 1:
                        seen["skid_x"] = round((sp.hero_x(s) - float(e["pos"][0])) * (1 if e.get("flipX") else -1), 3)
                        seen["skid_acc"] = bool(s["hero"].get("hero_accepting_input", True))
                else:
                    pm = self.play.step(s["f"], s, sp.on_ground(s), bool(s["hero"].get("hero_accepting_input", True)),
                                        t_game=self.tg if sp.GAME_CLOCK else None)
                    if self.tick_ms > 0:
                        time.sleep(self.tick_ms / 1000.0)
                    m = 0 if pm is None else pm
            link.act(s["f"] + 2, m, hold_frames=0)
            if seen is not None:
                h = s.get("hero") or {}
                rows.append(self._row(s, e, m))
                if self.play.run is None and st not in sp.SLAM_STATES:
                    n_after += 1
                    if n_after > SETTLE_F:
                        break
                if len(rows) > MAX_F:
                    break
            s = link.wait_state(newer_than=last, timeout_s=3.0)
            if s["f"] > last + 1 and seen is not None:
                rows.append({"gap": s["f"] - last - 1})
            self.tg += float(s.get("dt") or 0.0) + (s["f"] - last - 1) * float(s.get("ts") or 1.0) / 60.0
            last = s["f"]
        link.act(last + 2, 0, hold_frames=0)
        if (fz is not None and fz["f1"] is None) or (stl is not None and stl["f0"] is not None and stl["f1"] is None):
            link.rpc("time.scale", timeout_s=10, scale=1.0)
        run = self.play.done[0] if self.play.done else self.play.run      # the trial's slam (not a next one in the settle)
        if stl is not None:
            # the realized stall: STATE frames with dt > 1.5 frames from the scale-up on (game frames, Updates)
            big = [r for r in rows if "f" in r and stl["f0"] is not None and r["f"] >= stl["f0"] and r.get("dtf", 1) > 1.5]
            stl["frames"] = [[r["f"], r["dtf"], r.get("fs")] for r in big[:6]]
        return {"d": d, "pin": self.pin, "seen": seen, "freeze": fz, "stall": stl} | self._outcome(run, rows)

    @staticmethod
    def _row(s: dict, e: dict | None, m: int) -> dict:
        h = s.get("hero") or {}
        evs = []
        for ev in s.get("ev") or ():
            k, dd = ev.get("k"), ev.get("d") or {}
            if k == "hit" and dd.get("type_key") == sp.CLAPPER:
                evs.append(["hit", str(dd.get("src")), dd.get("dealt")])
            elif k == "hp" and (dd.get("delta") or 0) < 0:
                evs.append(["hp", dd.get("delta"), str(dd.get("source"))])
            elif k == "damage":
                evs.append(["damage", str(dd.get("source")), dd.get("amount")])
        return {"f": s["f"], "m": m, "act": int((s.get("act") or {}).get("mask") or 0),
                "dtf": round(float(s.get("dt") or 0.0) * 60.0, 2), "fs": s.get("fs"),
                "x": round(sp.hero_x(s), 3), "y": round(float(h["pos"][1]), 3),
                "vy": round(float((h.get("vel") or [0, 0])[1]), 2), "g": sp.on_ground(s), "hp": int(h.get("health") or 0),
                "st": _ctl(e), "cx": None if e is None else round(float(e["pos"][0]), 3),
                "chp": None if e is None else e.get("hp"), "ev": evs}

    @staticmethod
    def _outcome(run, rows: list) -> dict:
        R = [r for r in rows if "f" in r]
        out = {"gaps": sum(r.get("gap", 0) for r in rows)}
        if run is not None:
            out["play"] = {"fa": run.fa, "face": run.face, "phase": run.phase, "why": run.why, "k_start": run.k_start,
                           "k_air": getattr(run, "k_air", None),
                           "x_start": run.x_start, "k_jump": run.k_jump, "x_jump": run.x_jump, "k_press": run.k_press}
        if not R or run is None:
            return out | {"trace": R}
        fa, face = run.fa, run.face

        def first(pred, after=None):
            return next((r["f"] for r in R if (after is None or r["f"] >= after) and pred(r)), None)

        s0 = first(lambda r: r["st"] == "Slam 0", fa)
        s1 = first(lambda r: r["st"] == "Slam 1", fa)
        rec = first(lambda r: r["st"] == "Slam Recover", fa)
        end = first(lambda r: r["st"] not in sp.SLAM_STATES, rec) if rec is not None else None
        prev = 0
        jump = press = None
        for r in (r for r in R if r["f"] >= fa - 1):
            rise = r["act"] & ~prev
            prev = r["act"]
            if jump is None and rise & M_J:
                jump = r["f"]
            if press is None and rise & M_A and (jump is not None or r["act"] & M_D):
                press = r["f"]                            # the strike (SP6: not an early side slash before the jump)
        landed = False
        bounce = False
        if press is not None:
            c0 = next((r["chp"] for r in R if r["f"] >= press - 1 and r["chp"] is not None), None)
            landed = any(r["chp"] is not None and c0 is not None and r["chp"] < c0 for r in R if press <= r["f"] <= press + 14)
            bounce = any(r["vy"] > 6 for r in R if press < r["f"] <= press + 14)
        contact = next((r["f"] for r in R if press is not None and r["f"] >= press and any(e[0] == "hit" for e in r["ev"])), None)
        hp0 = R[0]["hp"]
        hurts = []
        for r in R:
            for ev in r["ev"]:
                if ev[0] == "hp":
                    hurts.append({"f": r["f"], "rel_s0": None if s0 is None else r["f"] - s0, "src": ev[2][-28:],
                                  "st": r["st"], "in_slam": end is None or r["f"] < end})
        if not hurts:                                  # no hp event: the health field
            for a, b in zip(R, R[1:]):
                if b["hp"] < a["hp"]:
                    hurts.append({"f": b["f"], "rel_s0": None if s0 is None else b["f"] - s0, "src": "?", "st": b["st"],
                                  "in_slam": end is None or b["f"] < end})
        hurt_slam = [h for h in hurts if h["in_slam"]]
        xs = lambda r: None if r is None or r["cx"] is None else round((r["x"] - r["cx"]) * face, 3)   # noqa: E731
        # SP5 (SSBOT_FORUM_SLAM_PLAY_SIDE / _NEAR): the way out - the landing (frame from Slam 0, x rel. its centre, +
        # in front), the side slash after the press (its press from Slam 0, a hit on it within 10 frames, before / at
        # the landing), HP lost from the press to the landing + 15 (the playbook's part)
        way = {}
        if press is not None and s0 is not None:
            land = first(lambda r: r["g"], press + 9)
            lr = next((r for r in R if land is not None and r["f"] == land), None)
            sl = None
            prev = 0
            for r in (r for r in R if r["f"] >= press + 1):
                if sl is None and r["act"] & ~prev & M_A and r["f"] >= press + 10:
                    sl = r["f"]
                prev = r["act"]
            sl_hit = None if sl is None else next((r["f"] for r in R if sl <= r["f"] <= sl + 10 and any(
                e[0] == "hit" and "Down" not in str(e[1]) for e in r["ev"])), None)
            d = getattr(run, "near", None) or getattr(run, "over_dir", None)
            way = {"side": None if not d else ("front" if d == face else "behind"),
                   "side_why": getattr(run, "side_why", ""), "near_u": getattr(run, "near_u", None),
                   "land_s0": None if land is None else land - s0, "x_land": xs(lr) if lr is not None else None,
                   "slash_s0": None if sl is None else sl - s0, "slash_hit_s0": None if sl_hit is None else sl_hit - s0,
                   "slash_before_land": sl_hit is not None and land is not None and sl_hit <= land,
                   "hurt_way": [h for h in hurts if press <= h["f"] <= (land if land is not None else press + 80) + 15]}
        pp = next((r for r in R if press is not None and r["f"] == press), None)
        jp = next((r for r in R if jump is not None and r["f"] == jump), None)
        # SP6 (SSBOT_FORUM_SLAM_PLAY_EARLY): the side slashes before the jump - the presses (STATE frames from the antic
        # entry, x rel. its centre) and the hits on it before the jump (non-down sources), HP lost before the press
        early = {"k_early": list(getattr(run, "k_early", []) or [])}
        pre = [r for r in R if r["f"] >= fa and (jump is None or r["f"] < jump + 8)]
        prev = 0
        ep = []
        for r in pre:
            if r["act"] & ~prev & M_A:
                ep.append([r["f"] - fa, xs(r)])
            prev = r["act"]
        early["presses"] = ep
        early["hits"] = [[r["f"] - fa, xs(r), str(e[1])[-12:]] for r in pre for e in r["ev"]
                         if e[0] == "hit" and "Down" not in str(e[1])]
        early["hurt_pre"] = [h for h in hurts if press is None or h["f"] < press]
        cx0 = next((r["cx"] for r in R if r["f"] >= fa and r["cx"] is not None), None)
        early["drift"] = None if cx0 is None or jp is None or jp["cx"] is None else round((jp["cx"] - cx0) * face, 3)
        return out | {"early": early,
            "fa": fa, "antic": None if s0 is None else s0 - fa, "s0": s0, "s1": s1, "rec": rec, "end": end,
            "k_jump_real": None if jump is None else jump - fa, "k_press_real": None if press is None else press - fa,
            "press_rel_s0": None if (press is None or s0 is None) else press - s0,
            "x_jump": xs(jp), "x_press": xs(pp), "y_press": None if pp is None else pp["y"],
            "contact_rel_s0": None if (contact is None or s0 is None) else contact - s0,
            "landed": landed, "bounce": bounce, "hurt_slam": hurt_slam, "hurt_after": [h for h in hurts if not h["in_slam"]],
            "hp0": hp0, "success": bool(landed and not hurt_slam), "way": way, "trace": R}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--savestate", default="fo_cl_w7w")
    ap.add_argument("--dists", default="4.5,5.5,6.5,7.5")
    ap.add_argument("--per", type=int, default=20, help="slams per distance class (trials that saw a slam)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tick-ms", type=float, default=0.0)
    ap.add_argument("--max-trials", type=int, default=400)
    ap.add_argument("--out", default=r"C:\ssbot\data\m2_play\live")
    ap.add_argument("--tag", default="")
    ap.add_argument("--pin", action="store_true", help="the stand band pinned at each distance class (x at the jump)")
    ap.add_argument("--hop", type=int, default=0, help="while waiting, a hop (jump held 8 frames) every 2 x HOP frames")
    ap.add_argument("--freeze", default="", help="K:N: at antic frame K the time scale 1e-4 for N frames (a hit stop)")
    ap.add_argument("--skid", type=int, default=0, help="N: dash + sprint toward it from the antic sighting, a Sprint "
                    "Turn at N - 2; the playbook from frame N (SP4)")
    ap.add_argument("--umbrella", action="store_true", help="with --hop: the jump again in the air (the umbrella; SP4)")
    ap.add_argument("--slash", type=int, default=0, help="N: while waiting, a side slash toward it every N frames "
                    "when within 5.2 u (the planner's idle slashes; SP6)")
    ap.add_argument("--stall", default="", help="P:S:N: P STATE frames after the press was sent, the time scale S (<= 4) "
                    "for N STATE frames (a host stall; SP4 item 2)")
    a = ap.parse_args(argv)
    from ssbot.record.recorder import Recorder
    dists = [float(x) for x in a.dists.split(",")]
    rng = random.Random(a.seed)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    rec = None
    try:
        link.rpc("guards.set", save_suppression=True, lethal_block="block")
        link.rpc("fsmtap.set", all=True)
        fz = tuple(int(x) for x in a.freeze.split(":")) if a.freeze else None
        stall = None
        if a.stall:
            p_, s_, n_ = a.stall.split(":")
            stall = (int(p_), float(s_), int(n_))
        pr = PlayProbe(link, a.savestate, a.tick_ms, a.pin, a.hop, fz, a.skid, a.umbrella, stall, a.slash)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"slam_play_i{a.instance}_s{a.seed}{a.tag}",
                       config={"probe": "slam_play_probe", "seed": a.seed, "dists": dists, "per": a.per,
                               "tick_ms": a.tick_ms, "savestate": a.savestate, "pin": a.pin, "hop": a.hop,
                               "freeze": a.freeze, "game_clock": sp.GAME_CLOCK, "skid": a.skid, "late": sp.LATE,
                               "umbrella": a.umbrella, "stall": a.stall, "side": sp.SIDE, "near": sp.NEAR,
                               "early": sp.EARLY, "slash": a.slash,
                               "cfg": pr.play.cfg.__dict__}).start()
        log = (rec.path / "play_trials.jsonl").open("w", encoding="utf-8")
        pr.load()
        done = {d: 0 for d in dists}
        n = 0
        while n < a.max_trials and any(v < a.per for v in done.values()):
            if stop_requested():
                print("stop requested", flush=True)
                break
            left = [d for d in dists if done[d] < a.per]
            d = rng.choice(left)
            try:
                info = pr.trial(d)
            except Exception as ex:  # noqa: BLE001
                info = {"d": d, "error": repr(ex)}
                try:
                    pr.load()
                except Exception as ex2:  # noqa: BLE001
                    print("reload failed", ex2, flush=True)
                    break
            link.rpc("input.release", timeout_s=10)
            if "skip" not in info and "error" not in info:
                done[d] += 1
            row = {"n": n} | info
            log.write(json.dumps(row) + "\n")
            log.flush()
            n += 1
            print(json.dumps({k: v for k, v in row.items() if k != "trace"})[:400], flush=True)
        log.close()
        print("done", done, flush=True)
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
            link.rpc("fsmtap.set", all=False)
            link.rpc("time.scale", timeout_s=10, scale=1e-4)        # leave the game frozen (the person, 10-15)
        except Exception:  # noqa: BLE001
            pass
        if rec is not None:
            rec.close()
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
