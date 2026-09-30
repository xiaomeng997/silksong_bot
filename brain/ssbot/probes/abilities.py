"""Ability grant probe (oracle/src/Train/AbilityGrant.cs, soak --abilities): grant, check STATE, use every granted action
once, check that a savestate carries the grant, then undo it with a savestate load.

Needs: the training copy running with an SsOracle that has abilities.grant, and DebugMod; at the title the probe loads
sandbox slot 1 (the early save: Bonetown, no dash, no tools) and stands Hornet up, which leaves floor on both sides. Not
while a soak runs (its workers own the instances' links) and only on sandbox saves (the oracle refuses otherwise). The
probe turns save suppression on before the grant and turns it back off only once the grant is verifiably undone
(savestate ab_probe_before loaded, abilities.list back to what it was); otherwise it stays on and the probe says so:
then close the game without saving.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 1 --detach    # instance 0 (later: launcher --restore)
    ../scripts/uv.cmd run python -m ssbot.probes.abilities                 # instance 0, set all, then undo
    ../scripts/uv.cmd run python -m ssbot.probes.abilities --set movement --keep   # grant stays, suppression on
Options: --instance N, --skill NAME, --tools A,B ("" = none), --no-unlock-slots.

Sections: hello (RPCs), before (abilities.list; savestate ab_probe_before), grant (the reply: flags, sets, bindings,
slots), state (hero.can dash / harpoon / super_jump, hero.tools), exercise (dash, sprint, double jump, glide, clawline,
Silk Soar, Needle Strike, QuickCast without a direction and with down, silk topped up to 9 first; each prints the
ability cState flags and animation clips it saw; down is only ever pressed with right held, as in the soak, so no bench
or NPC nearby opens), reset (savestate ab_probe_after carries the grant; loading ab_probe_before takes it away again:
flags, tools and crest slots as before). PASS/FAIL per check, exit 1 on any FAIL. A FAIL of an exercise with plausible
clips printed is worth a look at the game window before calling it a bug: the Clawline and Silk Soar checks read
indirect signs (cooldown, vertical speed). After the undo the game's own bound-tool cache (abilities.list
"bindings_cached": HUD icons, QuickCast's pick) can still show the granted tools until the next equip or crest change,
because a DebugMod savestate load does not refresh it; the throw itself reads PlayerData and fails harmlessly.
"""
import argparse
import random
import sys
from collections import Counter

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.probes.common import in_gameplay, load_slot, stand_up
from ssbot.tools import cstate
from ssbot.tools.soak import (DOWN_CAST, EVIDENCE_CSTATE, MOVEMENT_CAN, SILK_SOAR, ability_gaps, granted_equips,
                              unreachable)

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


def same_as_before(now: dict, before: dict) -> list[str]:
    """What an abilities.list still has that the pre-grant one did not (empty = the grant is gone)."""
    def tools(d):
        return sorted(t["name"] for t in d["tools"]), sorted(x["tool"] for x in d["skills"] if x["unlocked"])
    return [k for k, a, b in (("flags", now["flags"], before["flags"]), ("slots", now["slots"], before["slots"]),
                              ("tools", tools(now), tools(before))) if a != b]


def undo(link: OracleLink, before: dict) -> bool:
    """Load ab_probe_before and check that the grant is gone."""
    link.rpc("savestate.load", timeout_s=40, state="ab_probe_before", timeout=30)
    left = same_as_before(link.rpc("abilities.list"), before)
    check(not left, f"grant undone (differs from before: {left or 'nothing'})")
    return not left


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
    granted = undone = undo_tried = False  # the grant RPC was sent / taken back again and verified / tried
    before = None
    try:
        print("== hello")
        missing = {"abilities.grant", "abilities.list", "schema.cstate", "guards.set", "savestate.save"} - set(link.hello.get("rpcs", ()))
        if not check(not missing, f"HELLO lists the ability RPCs (missing: {sorted(missing) or 'none'})"):
            sys.exit(1)
        s = link.wait_state(lambda s: s.get("game") is not None, timeout_s=180)
        if not in_gameplay(s):
            print("     not in gameplay: loading sandbox save slot 1 from the title")
            load_slot(link, 1)
        stand_up(link, timeout_s=30)
        link.rpc("input.release")
        names = link.rpc("schema.cstate")["bools"]

        print("== before")
        before = link.rpc("abilities.list")
        print(f"     flags {before['flags']}\n     crest {before['crest']} slots {before['slots']}\n"
              f"     bindings {before['bindings']} config {before['config']} silk {before['silk']}/{before['silk_max']} "
              f"(skill cost {before['silk_skill_cost']}) tools {[t['name'] for t in before['tools']]}")
        link.rpc("savestate.save", state="ab_probe_before")

        print("== grant")
        old_suppression = link.rpc("guards.get")["save_suppression"]
        if not check(link.rpc("guards.set", save_suppression=True)["save_suppression"], "save suppression on"):
            sys.exit(1)  # never grant without it
        req = {"set": a.set, "unlock_slots": not a.no_unlock_slots}
        if a.set != "movement":
            if a.skill:
                req["skill"] = a.skill
            if a.tools is not None:
                req["tools"] = [t.strip() for t in a.tools.split(",") if t.strip()]
        granted = True  # from here on the finally block must see the grant gone before suppression goes off
        res = link.rpc("abilities.grant", timeout_s=20, **req)
        print(f"     changed: {res['changed']}\n     unplaced: {res['unplaced']}\n     slots: {res['slots']}\n"
              f"     bindings: {res['bindings']} (cached {res['bindings_cached']}) config: {res['config']}")
        movement, combat = a.set in ("movement", "all"), a.set != "movement"
        check(res["sets"][a.set], f"abilities.list reports set '{a.set}' complete")
        check(not res["unplaced"], "every requested tool found a slot")
        check(not unreachable(res), f"QuickCast reaches each requested skill/tool without up (not: {unreachable(res)})")
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
        D, J, A, C, F, R = (mask(k) for k in ("dash", "jump", "attack", "clawline", "quickcast", "right"))
        rng = random.Random(0)  # the soak's macros, down pressed with right held (never an interaction)
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
            ev = exercise(link, names, "silk soar", SILK_SOAR.expand(rng, R), after=60)
            check(ev.max_vy > JUMP_SPEED + 1, f"Silk Soar (rose at {ev.max_vy:.1f} u/s > jump speed {JUMP_SPEED})")
        if combat:
            ev = exercise(link, names, "needle strike", [A] * 110, after=40)
            check(ev.flags["nailCharging"] > 0, "Needle Strike charges (attack held)")
            skills = {x["tool"] for x in res["skills"]}
            for label, masks, bound in (("quickcast", [F] * 3, res["bindings"]["neutral"]),
                                        ("down + quickcast", DOWN_CAST.expand(rng, R), res["bindings"]["down"])):
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
        left = same_as_before(link.rpc("abilities.list"), before)
        check(not left, f"loading the pre-grant savestate takes the grant away (differs: {left or 'nothing'})")
        link.rpc("savestate.load", timeout_s=40, state="ab_probe_after", timeout=30)
        kept = link.rpc("abilities.list")  # slots and bindings are read from PlayerData, not the game's cache
        check(kept["sets"][a.set] and kept["slots"] == res["slots"] and kept["bindings"] == res["bindings"],
              "a savestate taken after the grant brings it back (what every soak reset relies on)")
        if not a.keep:
            undo_tried = True
            undone = undo(link, before)
    finally:
        try:
            link.rpc("input.release")
        except (OracleError, TimeoutError, OSError):
            pass
        if granted and not undo_tried and not a.keep and before is not None:
            try:  # an exception or Ctrl+C between the grant and the undo: take it back before suppression goes off
                undone = undo(link, before)
            except (OracleError, TimeoutError, OSError, KeyError) as e:
                print(f"     undo failed: {type(e).__name__}: {e}")
        if a.keep and granted:
            print("     --keep: save suppression stays on, so the kept grant never reaches the sandbox slot")
        elif granted and not undone:
            print("\n!!!! the grant may still be live in PlayerData: save suppression is left ON. Close this game"
                  " WITHOUT saving (no Save & Quit), or load savestate ab_probe_before and check abilities.list. !!!!")
        elif old_suppression is not None:
            try:
                link.rpc("guards.set", save_suppression=old_suppression)
            except (OracleError, TimeoutError, OSError):
                pass
        link.close()
    print(f"\n{len(failures)} FAIL(s)" + (": " + "; ".join(failures) if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
