"""Clawline / glide / down-slash / Sawtooth Circlet probe (research docs/research/clawline_glide_combo.md section 7).
Written offline and NOT RUN yet: the lead schedules it on a free training instance (it loads savestates and drives
input; save suppression and LethalBlock on all the time; optional PlayerData isInvincible).

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.combo_probe --instance 3 --savestate fo_r1_w0 --trials 12 \\
        [--exp saw,bypass,claw,rprlock] [--invincible]

The four questions the offline reading left open (each trial reloads the savestate, waits until the wave-0 enemies
are active and Hornet takes input, plays one scripted experiment, releases the keys):
  saw      Sawtooth Circlet ("Brolly Spike", granted with abilities.grant, blue slot unlocked): hop next to the
           nearest ground enemy and glide; slash.dump every frame with the spike's paths (it is parented to the hero
           by the Umbrella Float FSM, "Damager?" state) -> the live polygons (sign of the y scale: the bundle root
           is y-flipped), the enable window of Damager L / R after the spawn (animator: L 0.05-0.175 s, R
           0.10-0.20 s), "hit" events (13 = 8 x 1.6 with one Crafting Kit, then the 1-damage lag hit 0.1 s later).
  bypass   the glide's attack cancel (Umbrella Float "Attack Cancel" -> SetStartWithAttack -> RegainControl ->
           DoAttack, which checks neither attack_cooldown nor CanDownAttack): in the air, a side slash at t0, the
           glide pressed once the crest's recovery is over, attack pressed at Inflate + 0.08 s; does the slash start
           before t0 + attack cooldown (Reaper 0.5 s)? The control trial presses attack at the same time without the
           glide (expected: queued until the cooldown ends).
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
EXPS = ("saw", "bypass", "claw", "rprlock")
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
               "cs": h.get("cstate"), "silk": h.get("silk"), "inv": h.get("invulnerable"),
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


def exp_bypass(d: Driver, rng: random.Random, glide: bool, recovery_s: float) -> dict:
    d.hold(M_J, 14)                                                 # full jump
    d.hold(0, 4)
    t0 = d.step(M_A)["f"]                                           # side slash at t0
    d.hold(0, int(recovery_s * 60) + 1)
    inflate_k = None
    if glide:
        d.hold(M_J, 1)
        _, inflate_k = d.until(lambda s: clip_is(s, "Umbrella Inflate") and not clip_is(s, "Umbrella Inflate Antic"),
                               M_J, 20)
        d.hold(M_J, 5)                                              # Inflate + 0.08 s
    else:
        d.hold(0, 10)
    fa = d.step(M_A | (M_J if glide else 0))["f"]                   # the attack (cancel) press
    d.hold(M_J if glide else 0, 1)
    d.hold(0, 30)
    return {"glide": glide, "t0_f": t0, "press_f": fa, "press_after_s": (fa - t0) / 60.0, "inflate_k": inflate_k}


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
    ap.add_argument("--recovery", type=float, default=0.3, help="the crest's AttackRecoveryTime (Reaper 0.3)")
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
                if x == "saw":   # the tool into a blue slot (the savestate does not have it)
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
                    info = exp_bypass(drv, rng, glide=(n % 2 == 0), recovery_s=a.recovery)
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
