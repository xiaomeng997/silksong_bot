"""Ability grant probe (oracle/src/Train/AbilityGrant.cs, soak --abilities): grant, check STATE, use every granted action
once, check that a savestate carries the grant, then undo it with a savestate load.

Needs: the training copy running with an SsOracle that has abilities.grant, and DebugMod; the early sandbox save loaded
(Bonetown: no dash, no tools), Hornet standing with some floor on both sides. Not while a soak runs (its workers own
the instances' links) and only on sandbox saves (the oracle refuses otherwise). The probe turns save suppression on
first, so nothing it grants is written to the sandbox slot.

    cd brain
    uv run python -m ssbot.probes.abilities                        # instance 0, set all, then undo
    uv run python -m ssbot.probes.abilities --set movement --keep   # leave the grant in place (save suppression stays on)
Options: --instance N, --skill NAME, --tools A,B ("" = none), --no-unlock-slots.

Sections: hello (RPCs), before (abilities.list; savestate ab_probe_before), grant (the reply: flags, sets, bindings,
slots), state (hero.can dash / harpoon / super_jump, hero.tools), exercise (dash, sprint, double jump, glide, clawline,
Silk Soar, Needle Strike, QuickCast without a direction and with down, silk topped up to 9 first; each prints the
ability cState flags and animation clips it saw), reset (savestate ab_probe_after carries the grant; loading
ab_probe_before takes it away again). PASS/FAIL per check, exit 1 on any FAIL. A FAIL of an exercise with plausible
clips printed is worth a look at the game window before calling it a bug: the Clawline and Silk Soar checks read
indirect signs (cooldown, vertical speed).
"""
import argparse
import sys
from collections import Counter

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.tools import cstate
from ssbot.tools.soak import EVIDENCE_CSTATE, MOVEMENT_CAN, ability_gaps, granted_equips

PLAYING = 4
JUMP_SPEED = 18.6  # hero_constants.json: a plain jump never rises faster
failures: list[str] = []


def check(ok: bool, what: str) -> bool:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)
    return ok


def stream(link: OracleLink, masks: list[int], after: int = 40) -> list[dict]:
    """Hold masks[i] on consecutive frames (one continuous-control ACTION per new STATE, as the soak worker sends
    them), release, keep watching `after` frames. Returns the STATEs seen (the newest one per poll)."""
    seen, last = [], link.frame
    try:
        for m in masks:
            s = link.wait_state(newer_than=last, timeout_s=2.0)
            last = s["f"]
            seen.append(s)
            link.act(last + 2, m, hold_frames=0)
    finally:
        link.rpc("input.release")
    end = last + after
    while last < end:
        s = link.wait_state(newer_than=last, timeout_s=2.0)
        last = s["f"]
        seen.append(s)
    return seen


class Evidence:
    def __init__(self, states: list[dict], names: list[str]):
        self.flags: Counter = Counter()
        self.clips: Counter = Counter()
        self.max_vx = self.max_vy = 0.0
        self.can_false: Counter = Counter()
        self.silk: list[int] = []
        self.amounts: dict[str, list[int]] = {}
        for s in states:
            h = s.get("hero") or {}
            if h.get("cstate"):
                cs = cstate.decode(h["cstate"], names)
                self.flags.update(n for n in EVIDENCE_CSTATE if cs.get(n))
            clip = (h.get("anim") or {}).get("clip")
            if clip:
                self.clips[clip] += 1
            vel = h.get("vel") or (0.0, 0.0)
            self.max_vx, self.max_vy = max(self.max_vx, abs(vel[0])), max(self.max_vy, vel[1])
            self.can_false.update(k for k, v in (h.get("can") or {}).items() if v is False)
            if isinstance(h.get("silk"), int):
                self.silk.append(h["silk"])
            for t, a in zip(h.get("tools") or (), h.get("tool_amounts") or ()):
                if t:
                    self.amounts.setdefault(t, []).append(a)

    def show(self) -> str:
        return (f"flags {dict(self.flags)}, max |vx| {self.max_vx:.1f}, max vy {self.max_vy:.1f}, "
                f"clips {dict(self.clips.most_common(6))}")


def wait_standing(link: OracleLink, names: list[str]) -> dict:
    """The next STATE with Hornet on the ground and taking input (every exercise starts from there)."""
    return link.wait_state(lambda s: s["hero"]["hero_accepting_input"] and cstate.decode(s["hero"]["cstate"], names)["onGround"],
                           timeout_s=5)


def exercise(link: OracleLink, names: list[str], title: str, masks: list[int], after: int = 40) -> Evidence:
    wait_standing(link, names)
    ev = Evidence(stream(link, masks, after), names)
    print(f"     {title}: {ev.show()}")
    return ev


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--set", default="all", choices=("movement", "combat", "all"))
    ap.add_argument("--skill", default=None)
    ap.add_argument("--tools", default=None, help='comma-separated tool names ("" = none; default: the oracle\'s)')
    ap.add_argument("--no-unlock-slots", action="store_true")
    ap.add_argument("--keep", action="store_true", help="leave the grant in place (no undo)")
    a = ap.parse_args()

    link = OracleLink(instance=a.instance)
    old_suppression = None
    try:
        s = link.wait_state(timeout_s=5)
        print("== hello")
        missing = {"abilities.grant", "abilities.list", "schema.cstate", "guards.set", "savestate.save"} - set(link.hello.get("rpcs", ()))
        if not check(not missing, f"HELLO lists the ability RPCs (missing: {sorted(missing) or 'none'})"):
            sys.exit(1)
        if not s.get("game") or s["game"]["gs"] != PLAYING or not s.get("hero"):
            sys.exit("load the sandbox save and stand in Bonetown first")
        names = link.rpc("schema.cstate")["bools"]

        print("== before")
        before = link.rpc("abilities.list")
        print(f"     flags {before['flags']}\n     crest {before['crest']} slots {before['slots']}\n"
              f"     bindings {before['bindings']} config {before['config']} silk {before['silk']}/{before['silk_max']} "
              f"(skill cost {before['silk_skill_cost']}) tools {[t['name'] for t in before['tools']]}")
        link.rpc("savestate.save", state="ab_probe_before")

        print("== grant")
        old_suppression = link.rpc("guards.get")["save_suppression"]
        check(link.rpc("guards.set", save_suppression=True)["save_suppression"], "save suppression on")
        req = {"set": a.set, "unlock_slots": not a.no_unlock_slots}
        if a.set != "movement":
            if a.skill:
                req["skill"] = a.skill
            if a.tools is not None:
                req["tools"] = [t.strip() for t in a.tools.split(",") if t.strip()]
        res = link.rpc("abilities.grant", timeout_s=20, **req)
        print(f"     changed: {res['changed']}\n     unplaced: {res['unplaced']}\n     slots: {res['slots']}\n"
              f"     bindings: {res['bindings']} config: {res['config']}")
        movement, combat = a.set in ("movement", "all"), a.set != "movement"
        check(res["sets"][a.set], f"abilities.list reports set '{a.set}' complete")
        check(not res["unplaced"], "every requested tool found a slot")
        again = link.rpc("abilities.grant", timeout_s=20, **req)
        check(again["changed"] == [], f"a second grant changes nothing ({again['changed']})")
        try:
            link.rpc("abilities.grant", set="combat", tools=["No Such Tool"])
            check(False, "an unknown tool is refused")
        except OracleError as e:
            check(True, f"an unknown tool is refused ({e})")

        print("== state")
        want_can = MOVEMENT_CAN if movement else ()
        want_tools = granted_equips(res)
        try:
            link.wait_state(lambda s: not ability_gaps(s, want_can, want_tools), timeout_s=5)
            check(True, f"STATE shows the grant (can {want_can}, tools {want_tools})")
        except TimeoutError:
            check(False, f"STATE shows the grant: missing {ability_gaps(link.state, want_can, want_tools)}")

        print("== exercise")
        D, J, A, C, F, R, DN = (mask(k) for k in ("dash", "jump", "attack", "clawline", "quickcast", "right", "down"))
        if movement:
            ev = exercise(link, names, "dash", [D] * 3 + [0] * 3)
            check(ev.flags["dashing"] > 0 or ev.max_vx >= 20, "dash (Swift Step)")
            ev = exercise(link, names, "sprint", [R | D] * 60)
            check(ev.flags["isSprinting"] > 0, "sprint (dash held)")
            ev = exercise(link, names, "double jump", [J] * 6 + [0] * 6 + [J] * 6)
            check(ev.flags["doubleJumping"] > 0, "double jump (Faydown Cloak)")
            ev = exercise(link, names, "glide", [J] * 6 + [0] * 4 + [J] * 6 + [0] * 4 + [J] * 60)
            check(ev.flags["floating"] > 0, "glide (Drifter's Cloak)")
            ev = exercise(link, names, "clawline", [C] * 4, after=60)
            check(ev.can_false["harpoon"] > 0 or any("harpoon" in c.lower() for c in ev.clips),
                  "clawline (hero.can.harpoon went false for its cooldown, or a Harpoon clip)")
            ev = exercise(link, names, "silk soar", [DN, DN, DN | C, DN | C, DN | C, DN], after=60)
            check(ev.max_vy > JUMP_SPEED + 1, f"Silk Soar (rose at {ev.max_vy:.1f} u/s > jump speed {JUMP_SPEED})")
        if combat:
            ev = exercise(link, names, "needle strike", [A] * 110, after=40)
            check(ev.flags["nailCharging"] > 0, "Needle Strike charges (attack held)")
            skills = {x["tool"] for x in res["skills"]}
            for label, masks, bound in (("quickcast", [F] * 3, res["bindings"]["neutral"]),
                                        ("down + quickcast", [DN, DN, DN | F, DN | F, DN | F, DN], res["bindings"]["down"])):
                if not bound:
                    print(f"     {label}: nothing bound, skipped")
                    continue
                wait_standing(link, names)
                silk = link.rpc("randomize_start", seed=1, silk=[9, 9])["silk"]
                pre = link.wait_state(lambda s: s["hero"]["silk"] == silk, timeout_s=2)["hero"]
                ev = exercise(link, names, f"{label} ({bound})", masks, after=60)
                if bound in skills:
                    low = min(ev.silk or [silk])
                    check(low <= silk - res["silk_skill_cost"], f"{label} casts {bound} (silk {silk} -> {low})")
                else:
                    was = dict(zip(pre.get("tools") or (), pre.get("tool_amounts") or ())).get(bound)
                    low = min(ev.amounts.get(bound) or [was])
                    check(was is not None and low < was, f"{label} throws {bound} (amount {was} -> {low})")

        print("== reset")
        link.rpc("savestate.save", state="ab_probe_after")
        link.rpc("savestate.load", timeout_s=40, state="ab_probe_before", timeout=30)
        back = link.rpc("abilities.list")
        check(back["flags"] == before["flags"], "loading the pre-grant savestate takes the grant away")
        link.rpc("savestate.load", timeout_s=40, state="ab_probe_after", timeout=30)
        kept = link.rpc("abilities.list")
        check(kept["sets"][a.set] and kept["bindings"] == res["bindings"],
              "a savestate taken after the grant brings it back (what every soak reset relies on)")
        if not a.keep:
            link.rpc("savestate.load", timeout_s=40, state="ab_probe_before", timeout=30)
            check(link.rpc("abilities.list")["flags"] == before["flags"], "grant undone")
    finally:
        try:
            link.rpc("input.release")
            if old_suppression is not None and not a.keep:
                link.rpc("guards.set", save_suppression=old_suppression)
            elif a.keep:
                print("     --keep: save suppression stays on, so the kept grant never reaches the sandbox slot")
        except (OracleError, TimeoutError, OSError):
            pass
        link.close()
    print(f"\n{len(failures)} FAIL(s)" + (": " + "; ".join(failures) if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
