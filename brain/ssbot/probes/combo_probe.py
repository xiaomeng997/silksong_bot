"""Clawline / glide / down-slash / Sawtooth Circlet probe (research docs/research/clawline_glide_combo.md section 7).
Written offline and NOT RUN yet: the lead schedules it on a free training instance (it loads savestates and drives
input; save suppression and LethalBlock on all the time; optional PlayerData isInvincible).

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.combo_probe --instance 3 --savestate fo_r1_w0 --trials 12 \\
        [--exp saw,bypass,lockout,claw,rprlock] [--invincible] [--lockout-crest Wanderer]

The four questions the offline reading left open (each trial reloads the savestate, waits until the wave-0 enemies
are active and Hornet takes input, plays one scripted experiment, releases the keys):
  saw      Sawtooth Circlet ("Brolly Spike", granted with abilities.grant, blue slot unlocked): hop next to the
           nearest ground enemy and glide; slash.dump every frame with the spike's paths (it is parented to the hero
           by the Umbrella Float FSM, "Damager?" state) -> the live polygons (sign of the y scale: the bundle root
           is y-flipped), the enable window of Damager L / R after the spawn (animator: L 0.05-0.175 s, R
           0.10-0.20 s), "hit" events (13 = 8 x 1.6 with one Crafting Kit, then the 1-damage lag hit 0.1 s later).
  bypass   the glide's attack cancel (Umbrella Float "Attack Cancel" -> SetStartWithAttack -> RegainControl ->
           DoAttack, which checks neither attack_cooldown nor CanDownAttack): a Reaper down slash pogoes on the
           nearest ground enemy, the glide is pressed as soon as control returns and down + attack at Inflate +
           0.08 s, ~0.35 s after the down-slash press (inside the 0.5 s cooldown; hero.tm.atk_cd logged; each cycle
           flags inside_cooldown). Does the next down slash start at once? Up to 3 cycles: hero y at each pogo hit ->
           the climb per cycle (kin_jit: ~1.3 u, the loop breaks after ~3 hits). The control trial presses down +
           attack at the same delay without the glide (expected: nothing until atk_cd <= 0).
  lockout  the Sawtooth's one-spike-at-a-time check (brolly_spike_cooldown_check): glide next to a ground enemy,
           dash-cancel (or, with --lockout-crest Wanderer, attack-cancel) at Inflate + 0.075 s and re-glide at once ->
           a 2nd spike ~0.26-0.30 s after the 1st (< its 0.375 s AutoRecycleSelf). Expected: the 2nd deals nothing.
  claw     Clawline at the nearest enemy level with the hero: per frame the hero pos / clip / Harpoon Dash FSM state
           (fsmtap), the two harpoon hits and their damage, where the dash ends (the needle x snap), the harpoon
           bounce height, and the glide pressed k frames after control returns (earliest glide after a Clawline);
           whether the hooked enemy's body hurts during the dash (its DamageHero is switched off by
           SetDamageHeroAndRecord) and its attack colliders do (R1: 5 hits within 0.5 s of a hook).
  rprlock  Reaper down slash in the air, jump pressed k frames after the down-slash press (k 10..26): the first k
           that starts a glide (IsAttackLocked: cState.attacking with attack_time < 0.3 s; kin_jit keeps ATTACKING 0
           for the Custom down slash and lets the glide start at once).
Output: one recording (Recorder, profile TRAIN) plus <recording>/combo_trials.jsonl (one line per trial: the
experiment, its parameters, the frames, and the per-frame samples it took).
"""
from __future__ import annotations

import argparse
import json
import random
import sys

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink

M_L, M_R, M_U, M_D = mask("left"), mask("right"), mask("up"), mask("down")
M_J, M_A, M_DASH, M_CLAW = mask("jump"), mask("attack"), mask("dash"), mask("clawline")
SAW_ROOT = "Tool_brolly_spike(Clone)/Brolly_spike_position/brolly_slash_enemy_damager"
SAW_PATHS = (SAW_ROOT + "/Damager L", SAW_ROOT + "/Damager R")
DS_PATH = "Attacks/Scythe/DownSlash New"
DS_SRC = ("DownSlash New", "DownSlash", "DownSlashAlt", "DownSpike", "Downspike")
DS_CLIPS = ("v3 Down Slash", "DownSlash", "Down Slash", "DownSpike")
EXPS = ("saw", "bypass", "lockout", "claw", "rprlock")
GROUND_TYPES = ("Song Pilgrim 03", "Song Pilgrim 01", "Song Heavy Sentry")


def nearest(state: dict, ground: bool | None = None) -> dict | None:
    """The nearest live wave enemy (ground types only with ground=True, flyers only with False)."""
    h = state["hero"]["pos"]
    best = None
    for e in state.get("ents") or ():
        if (e.get("hp") or 0) <= 0 or not e.get("pos"):
            continue
        g = e.get("type_key") in GROUND_TYPES
        if ground is not None and g != ground:
            continue
        d = abs(e["pos"][0] - h[0]) + 0.5 * abs(e["pos"][1] - h[1])
        if best is None or d < best[0]:
            best = (d, e)
    return best[1] if best else None


class Driver:
    """One ACTION per STATE at frame + 2 (as kin_excite); per-frame samples of the hero and events."""

    def __init__(self, link: OracleLink):
        self.link = link
        self.samples: list = []

    def step(self, buttons: int, dump: tuple = ()) -> dict:
        s = self.link.wait_state(newer_than=self.link.frame, timeout_s=2.0)
        self.link.act(s["f"] + 2, buttons, hold_frames=0)
        h = s.get("hero") or {}
        row = {"f": s["f"], "m": buttons, "pos": h.get("pos"), "vel": h.get("vel"), "clip": (h.get("anim") or {}).get("clip"),
               "cs": h.get("cstate"), "silk": h.get("silk"), "inv": h.get("invulnerable"), "tm": h.get("tm"),
               "ev": [ev for ev in s.get("ev") or () if ev.get("k") in ("hit", "damage", "damage_blocked", "fsm", "hp")]}
        if dump:
            fut = self.link.rpc_async("slash.dump", paths=list(dump))
            row["_dump"] = fut
        self.samples.append(row)
        return s

    def hold(self, buttons: int, frames: int, dump: tuple = ()) -> dict:
        s = None
        for _ in range(frames):
            s = self.step(buttons, dump)
        return s

    def until(self, pred, buttons: int, max_frames: int, dump: tuple = ()) -> tuple[dict, int]:
        for k in range(max_frames):
            s = self.step(buttons, dump)
            if pred(s):
                return s, k
        return s, -1

    def collect(self) -> list:
        out = []
        for r in self.samples:
            fut = r.pop("_dump", None)
            if fut is not None:
                try:
                    d = fut.result(timeout=5)
                    r["dump"] = [{"path": dm.get("path"), "enabled": dm.get("enabled"), "active": dm.get("active"),
                                  "polys": [shp["v"] for c in dm.get("colliders") or () for shp in c.get("shapes") or ()]}
                                 for a in d.get("attacks") or () for dm in a.get("damagers") or ()]
                    r["dump_hero"] = d.get("hero")
                except Exception as e:  # noqa: BLE001
                    r["dump_err"] = str(e)
            out.append(r)
        self.samples = []
        return out


def clip_is(s: dict, prefix: str) -> bool:
    return ((s.get("hero") or {}).get("anim") or {}).get("clip", "").startswith(prefix)


def exp_saw(d: Driver, rng: random.Random) -> dict:
    s = d.step(0)
    e = nearest(s, ground=True)
    if e is None:
        return {"skip": "no ground enemy"}
    side = -1 if e["pos"][0] < s["hero"]["pos"][0] else 1          # the enemy is at this side
    toward = M_L if side < 0 else M_R
    gap = rng.uniform(1.5, 4.5)                                     # stop this far from it (x)
    d.until(lambda s: abs(s["hero"]["pos"][0] - nearest(s, ground=True)["pos"][0]) <= gap + 0.6
            if nearest(s, ground=True) else True, toward, 120)
    d.hold(M_J, 2)                                                  # hop
    d.hold(0, rng.randint(2, 8))
    d.hold(M_J, 30, dump=SAW_PATHS)                                 # glide (antic -> Damager? spawns the spike)
    d.hold(0, 25, dump=SAW_PATHS)
    return {"gap": gap, "side": side, "enemy": e.get("type_key")}


def ds_hit(s: dict) -> bool:
    return any(ev.get("k") == "hit" and (ev.get("d") or {}).get("src") in DS_SRC for ev in s.get("ev") or ())


def ds_started(s: dict) -> bool:
    return any(clip_is(s, p) for p in DS_CLIPS)


def is_inflate(s: dict) -> bool:
    return clip_is(s, "Umbrella Inflate") and not clip_is(s, "Umbrella Inflate Antic")


def approach(d: Driver, gap: float, ground: bool = True) -> dict | None:
    """Walk towards the nearest (ground) enemy until |dx| <= gap; returns the last state or None."""
    s = d.step(0)
    e = nearest(s, ground=ground)
    if e is None:
        return None
    toward = M_L if e["pos"][0] < s["hero"]["pos"][0] else M_R
    s, _ = d.until(lambda s: (n := nearest(s, ground=ground)) is None or abs(s["hero"]["pos"][0] - n["pos"][0]) <= gap,
                   toward, 150)
    return s


def exp_bypass(d: Driver, rng: random.Random, glide: bool, cooldown_s: float, cycles: int = 3) -> dict:
    """The glide's attack cancel inside the Reaper's 0.5 s attack cooldown (review fix: the old version pressed after a
    side slash and only reached the cancel at ~0.53 s, past the cooldown). A Reaper down slash pogoes on the nearest
    ground enemy; the bounce returns control (the down-slash FSM's RelinquishControlNotVelocity ran ResetAttacks, so the
    glide is not attack-locked), the glide is pressed at once and down + attack at Inflate + 0.08 s, i.e. ~0.35 s after
    the down-slash press, well inside attack_cooldown (hero.tm.atk_cd is logged every frame). glide=False is the
    control: down + attack at the same delay after the pogo without a glide (expected: no down slash until atk_cd <= 0).
    Repeats for `cycles` pogoes to measure the climb per cycle (kin_jit: ~1.3 u per cycle, the loop breaks after ~3)."""
    s = approach(d, 0.4)
    if s is None:
        return {"skip": "no ground enemy"}
    d.hold(M_J, 14)                                                 # full jump next to / over it
    d.hold(0, 6)
    out = {"glide": glide, "cycles": []}
    f_ds = d.step(M_D | M_A)["f"]                                   # the first down slash
    for c in range(cycles):
        cyc = {"ds_press_f": f_ds}
        s, k_hit = d.until(ds_hit, M_D, 30)
        if k_hit < 0:
            cyc["miss"] = True
            out["cycles"].append(cyc)
            break
        cyc["hit_f"] = s["f"]
        cyc["hero_y_at_hit"] = (s.get("hero") or {}).get("pos", [None, None])[1]
        s, k_ctl = d.until(lambda s: bool((s.get("hero") or {}).get("hero_accepting_input")), 0, 30)
        cyc["control_back_f"] = s["f"]
        if glide:
            d.hold(M_J, 1)                                          # a new jump press -> glide (if CanFloat)
            s, k_inf = d.until(is_inflate, M_J, 20)
            cyc["inflate_f"] = s["f"] if k_inf >= 0 else None
            if k_inf < 0:
                cyc["no_glide"] = True
                out["cycles"].append(cyc)
                break
            d.hold(M_J, 4)                                          # Inflate + 0.075 s (ListenForAttack delay)
            press = M_J | M_D | M_A
        else:
            d.hold(0, 10)                                           # same delay as antic (~5) + Inflate wait (5)
            press = M_D | M_A
        s = d.step(press)
        fa = s["f"]
        tm = (s.get("hero") or {}).get("tm") or {}
        cyc.update(press_f=fa, press_after_ds_s=(fa - f_ds) / 60.0, atk_cd_at_press=tm.get("atk_cd"),
                   inside_cooldown=(fa - f_ds) / 60.0 < cooldown_s - 2 / 60.0)
        s, k_ds = d.until(ds_started, press & ~M_A if glide else M_D, 40)
        cyc["ds_start_after_press_frames"] = k_ds                   # 0-2: the cancel fired at once (bypass)
        out["cycles"].append(cyc)
        if k_ds < 0:
            break
        f_ds = fa
    d.hold(0, 30)
    ys = [c.get("hero_y_at_hit") for c in out["cycles"] if c.get("hero_y_at_hit") is not None]
    out["climb_per_cycle"] = [round(b - a, 3) for a, b in zip(ys, ys[1:])]
    return out


def exp_lockout(d: Driver, rng: random.Random, via: str) -> dict:
    """The Sawtooth lockout (bundle: Tool_brolly_spike's PlayMakerFSM brolly_spike_cooldown_check tags the new spike,
    one frame later untags it, FindGameObject withTag 'Brolly Spike Slash' and, if the previous spike is still alive,
    i.e. within its AutoRecycleSelf 0.375 s, deactivates the new one). Next to a ground enemy: glide (spike 1), cancel
    at Inflate + 0.075 s (via='dash': a dash cancel, Reaper; via='attack': an attack cancel, run with
    --lockout-crest Wanderer: 0.1 s attack lock + the FSM's 0.1 s Cooldown), then press jump every frame until the next
    glide antic -> spike 2 ~0.26-0.30 s after spike 1. Expected: spike 2 deals nothing (no Damager L/R hit events after
    its spawn while spike 1's were there); spawn frames from the Inflate-after-Antic clip onsets."""
    gap = rng.uniform(1.5, 3.0)
    s = approach(d, gap + 0.6)
    if s is None:
        return {"skip": "no ground enemy"}
    d.hold(M_J, 3)                                                  # hop
    d.hold(0, 3)
    spawns = []
    d.hold(M_J, 1, dump=SAW_PATHS)
    s, k = d.until(is_inflate, M_J, 20, dump=SAW_PATHS)            # spike 1 spawned (Damager? -> Inflate)
    if k < 0:
        return {"skip": "no glide 1"}
    spawns.append(s["f"])
    d.hold(M_J, 4, dump=SAW_PATHS)
    d.step(M_J | (M_DASH if via == "dash" else M_A), dump=SAW_PATHS)
    d.hold(0, 1, dump=SAW_PATHS)
    for _ in range(40):                                             # jump pressed on alternate frames (new presses)
        s = d.step(M_J, dump=SAW_PATHS)
        if clip_is(s, "Umbrella Inflate Antic"):
            break
        s = d.step(0, dump=SAW_PATHS)
        if clip_is(s, "Umbrella Inflate Antic"):
            break
    s, k = d.until(is_inflate, M_J, 20, dump=SAW_PATHS)
    if k >= 0:
        spawns.append(s["f"])
    d.hold(M_J, 20, dump=SAW_PATHS)
    d.hold(0, 10)
    return {"via": via, "gap": gap, "spawn_f": spawns,
            "spawn_gap_s": (spawns[1] - spawns[0]) / 60.0 if len(spawns) == 2 else None}


def exp_claw(d: Driver, rng: random.Random, k_glide: int) -> dict:
    s = d.step(0)
    e = nearest(s)
    if e is None:
        return {"skip": "no enemy"}
    toward = M_L if e["pos"][0] < s["hero"]["pos"][0] else M_R
    d.hold(toward, 2)
    d.hold(toward | M_CLAW, 2)                                      # Clawline (superdash) towards it
    s, k = d.until(lambda s: (s["hero"] or {}).get("hero_accepting_input") and not clip_is(s, "Harpoon"), 0, 60)
    d.hold(0, k_glide)
    d.hold(M_J, 25)                                                 # glide as early as allowed
    d.hold(0, 30)
    return {"enemy": e.get("type_key"), "enemy_pos": e.get("pos"), "k_glide": k_glide, "control_back_k": k}


def exp_rprlock(d: Driver, rng: random.Random, k_jump: int) -> dict:
    d.hold(M_J, 14)
    d.hold(0, 4)
    f = d.step(M_D | M_A)["f"]                                      # Reaper down slash
    d.hold(M_D, max(0, k_jump - 1))
    d.hold(M_J, 3)                                                  # glide press k frames after the slash press
    d.hold(M_J, 20)
    d.hold(0, 20)
    return {"ds_f": f, "k_jump": k_jump}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=3)
    ap.add_argument("--savestate", default="fo_r1_w0")
    ap.add_argument("--trials", type=int, default=12, help="per experiment")
    ap.add_argument("--exp", default=",".join(EXPS))
    ap.add_argument("--seed", type=int, default=131000)
    ap.add_argument("--cooldown", type=float, default=0.5, help="the crest's attack cooldown (Reaper 0.5)")
    ap.add_argument("--lockout-crest", default="", help="crest.equip this crest (e.g. Wanderer) for the lockout "
                    "experiment and use the attack cancel; default: stay Reaper and use the dash cancel")
    ap.add_argument("--invincible", action="store_true", help="PlayerData isInvincible during the trials")
    ap.add_argument("--out", default=r"C:\ssbot\data\runs\m2\combo_probe")
    a = ap.parse_args(argv)
    from ssbot.record.recorder import Recorder
    from ssbot.train.wave_start import DebugLine

    rng = random.Random(a.seed)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    dbg = DebugLine(a.instance) if a.invincible else None
    rec = None
    try:
        link.rpc("guards.set", save_suppression=True, lethal_block="block")
        link.rpc("fsmtap.set", all=True)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"combo_probe_s{a.seed}",
                       config={"probe": "combo_probe", "seed": a.seed, "exp": a.exp, "savestate": a.savestate}).start()
        log = (rec.path / "combo_trials.jsonl").open("w", encoding="utf-8")
        exps = [x for x in a.exp.split(",") if x in EXPS]
        granted = False
        for n in range(a.trials):
            for x in exps:
                link.rpc("savestate.load", timeout_s=60, name=a.savestate, timeout=50)
                link.wait_state(lambda s: s.get("hero") and s["hero"].get("hero_accepting_input")
                                and any((b.get("enemies") or 0) > 0 for b in (s.get("room") or {}).get("battles") or ()),
                                timeout_s=30)
                if x == "lockout" and a.lockout_crest:   # before the grant: the crest keeps its own tool equips
                    link.rpc("crest.equip", timeout_s=20, name=a.lockout_crest, unlock=True)
                if x in ("saw", "lockout", "bypass"):   # the tool into a blue slot (the savestate does not have it)
                    g = link.rpc("abilities.grant", timeout_s=20, set="movement", tools=["Brolly Spike"],
                                 unlock_slots=True)
                    granted = granted or bool(g)
                if dbg:
                    dbg.pdset("isInvincible", "True")
                link.rpc("randomize_start", timeout_s=30, seed=a.seed * 100 + n, hp=[7, 7], silk=[9, 9],
                         facing="random", wait_frames=[0, 6])
                drv = Driver(link)
                if x == "saw":
                    info = exp_saw(drv, rng)
                elif x == "bypass":
                    info = exp_bypass(drv, rng, glide=(n % 2 == 0), cooldown_s=a.cooldown)
                elif x == "lockout":
                    info = exp_lockout(drv, rng, via="attack" if a.lockout_crest else "dash")
                elif x == "claw":
                    info = exp_claw(drv, rng, k_glide=n % 6)
                else:
                    info = exp_rprlock(drv, rng, k_jump=10 + (n * 2) % 18)
                link.rpc("input.release", timeout_s=10)
                log.write(json.dumps({"exp": x, "trial": n, **info, "samples": drv.collect()}) + "\n")
                log.flush()
                print(x, n, json.dumps(info)[:200], flush=True)
        log.close()
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
            link.rpc("fsmtap.set", all=False)
            if a.lockout_crest:
                link.rpc("crest.equip", timeout_s=20, restore=True)
        except Exception:  # noqa: BLE001
            pass
        if dbg:
            dbg.pdset("isInvincible", "False")
            dbg.close()
        if rec is not None:
            rec.close()
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
