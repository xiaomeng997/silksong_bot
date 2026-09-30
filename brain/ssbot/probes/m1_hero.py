"""M1 hero-cam-hud check: STATE sections "hero", "cam", "hud" and RPCs schema.cstate / schema.hero / hud.dump.

Needs the training copy running with SsOracle and `Hero.HeroModule.Install(host, harmony);` in Modules.InstallAll.
No focus needed (in-engine key injection).

    cd brain
    uv run python -m ssbot.probes.m1_hero                 # loads the highlighted save slot if at the title
    uv run python -m ssbot.probes.m1_hero --no-load --no-move --dump hud_dump.json

At the title it presses Enter (title -> save select) and Enter again (the highlighted slot) with frame-targeted
ACTIONs, exactly like P3. Make sure the highlighted slot holds a sandbox save: Enter on an EMPTY slot silently
starts a new Classic game (m0:N30). Unless --no-move, it then walks right and left for 30 frames each (getting up
from the bench first) to check vel and facing. Prints each section, then PASS/WARN/FAIL per invariant; exit code 1
if anything FAILs.
"""
import argparse
import json
import math
import statistics
import sys
import time

import msgpack

from ssbot.ipc.framing import HEADER, MsgType, mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.tools import cstate, projector

GS_PLAYING = 4
MENU_MAIN, MENU_SAVE_PROFILES = 1, 6
COST_LIMIT_US = 100
KEYS = ("hero", "cam", "hud")

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
    level = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    results.append((level, name, detail))
    print(f"  [{level}] {name}" + (f": {detail}" if detail else ""))
    return ok


def tap(link: OracleLink, button: str, hold_frames: int = 4) -> None:
    """Press at a frame shortly ahead and hold it long enough to be sampled (m0:N37)."""
    link.act(link.frame + 2, mask(button), hold_frames=hold_frames)


def hold(link: OracleLink, buttons: int, frames: int) -> None:
    link.act(link.frame + 2, buttons, hold_frames=frames)


def load_save(link: OracleLink) -> dict:
    print("not in gameplay: loading the highlighted save slot from the title")
    link.wait_state(lambda s: s["game"]["menu"] == MENU_MAIN, timeout_s=90)
    time.sleep(1.0)  # the menu ignores input while it fades in (P3)
    tap(link, "enter")
    link.wait_state(lambda s: s["game"]["menu"] == MENU_SAVE_PROFILES, timeout_s=10)
    time.sleep(1.0)
    tap(link, "enter")
    return link.wait_state(lambda s: s["game"]["gs"] == GS_PLAYING and s["hero"] is not None
                           and s["hero"]["hero_accepting_input"], timeout_s=120)


def collect(link: OracleLink, seconds: float) -> list[dict]:
    """Every STATE for `seconds` (the poller may skip frames; the raw subscriber sees all of them)."""
    frames: list[dict] = []
    active = [True]

    def on_raw(msg_type: int, raw: bytes) -> None:
        if active[0] and msg_type == MsgType.STATE:
            frames.append(msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False))

    link.subscribe_raw(on_raw)
    time.sleep(seconds)
    active[0] = False
    return list(frames)


def fmt(v):
    """Compact view: round floats, shorten long arrays."""
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, list):
        items = [fmt(x) for x in v[:8]]
        return items + [f"...+{len(v) - 8}"] if len(v) > 8 else items
    if isinstance(v, dict):
        return {k: fmt(x) for k, x in v.items()}
    return v


def pctl(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))]


def inside(x: float, y: float, box: tuple[float, float, float, float], tol: float = 1.0) -> bool:
    return box[0] - tol <= x <= box[2] + tol and box[1] - tol <= y <= box[3] + tol


def check_hero(s: dict, schema: dict, enums: dict) -> None:
    h = s["hero"]
    print("\n== hero ==")
    print(json.dumps(fmt(h), ensure_ascii=False))
    if not check("hero section present", h is not None):
        return
    check("0 <= health <= max_health", 0 <= h["health"] <= h["max_health"], f"{h['health']}/{h['max_health']}")
    check("health_blue >= 0", h["health_blue"] >= 0, str(h["health_blue"]))
    check("silk <= silk_max", h["silk_max"] is not None and 0 <= h["silk"] <= h["silk_max"],
          f"{h['silk']}/{h['silk_max']} parts={h['silk_parts']}")
    words = h["cstate"]
    ok = check("cstate words match schema.cstate", len(words) == schema["words"], f"{len(words)} words, {len(schema['bools'])} bools")
    if ok:
        cs = cstate.decode(words, schema["bools"])
        on = [k for k, v in cs.items() if v]
        print(f"  cState true: {on}")
        check("facing matches cState.facingRight", cs["facingRight"] == (h["facing"] == 1))
        ci = cstate.ints(h["cstate_int"], schema["ints"])
        print(f"  cState ints: {ci}")
    check("vel present", h["vel"] is not None and all(math.isfinite(v) for v in h["vel"]))
    anim = h["anim"]
    if check("anim present", anim is not None, "" if anim is None else f"{anim['clip']} {anim['frame']}/{anim['n']} @ {anim['fps']} fps"):
        check("anim frame in range", anim["n"] == 0 or 0 <= anim["frame"] < anim["n"])
    names = enums["hero_state"]
    print(f"  hero_state={names[h['hero_state']]} transition={enums['transition_state'][h['transition_state']]} "
          f"damage_mode={enums['damage_mode'][h['damage_mode']]} can={h['can']}")
    check("fractured_mask exported", h.get("fractured_mask") is not None, str(h.get("fractured_mask")))
    check("tools/tool_amounts aligned", len(h["tools"]) == len(h["tool_amounts"]),
          f"{list(zip(h['tools'], h['tool_amounts']))} (+{h['tools_extra']} extra)")


def check_cam(s: dict) -> tuple | None:
    c = s["cam"]
    print("\n== cam ==")
    print(json.dumps(fmt({k: v for k, v in (c or {}).items() if k not in ("V", "P")})))
    if not check("cam section present", c is not None):
        return None
    for m in ("V", "P"):
        ok = len(c[m]) == 16 and all(math.isfinite(x) for x in c[m])
        check(f"{m} is 16 finite floats and not identity", ok and not projector.is_identity(c[m]))
    check("V/P captured at render time (src == 1)", c["src"] == 1,
          "src=0: Camera.onPreRender did not fire for the main camera; shake is missing from V" if c["src"] != 1 else "",
          warn_only=True)
    print(f"  V = {[round(x, 3) for x in c['V']]}")
    print(f"  P = {[round(x, 3) for x in c['P']]}")
    rx, ry, rw, rh = c["rect"]
    check("viewport rect normalized", 0 <= rx and 0 <= ry and rx + rw <= 1.0001 and ry + rh <= 1.0001, str(c["rect"]))
    return projector.viewport_px(c)


def check_projection(s: dict, viewport: tuple) -> None:
    h, c = s["hero"], s["cam"]
    if h is None or c is None:
        return
    px, ok = projector.project_cam([h["pos"]], c)
    x, y = px[0]
    sw, sh = c["screen"]
    detail = f"hero {fmt(h['pos'])} -> ({x:.1f}, {y:.1f}) px; viewport {tuple(round(v) for v in viewport)}; screen {sw}x{sh}"
    check("hero projects inside the viewport", bool(ok[0]) and inside(x, y, viewport), detail)
    if h.get("box"):
        x0, y0, x1, y1 = h["box"]
        corners, _ = projector.project_cam([[x0, y0, h["pos"][2]], [x1, y1, h["pos"][2]]], c)
        w_px, h_px = abs(corners[1][0] - corners[0][0]), abs(corners[1][1] - corners[0][1])
        check("hero collider is a plausible on-screen size", 5 < w_px < sw / 4 and 10 < h_px < sh / 3,
              f"{w_px:.0f}x{h_px:.0f} px", warn_only=True)


def check_hud(states: list[dict]) -> None:
    s = states[-1]
    hud = s["hud"]
    print("\n== hud ==")
    print(json.dumps(fmt({k: v for k, v in (hud or {}).items() if k != "cam"}), ensure_ascii=False))
    if not check("hud section present", hud is not None):
        return
    check("hud camera present", hud["cam"] is not None)
    shown = [x for x in states if x["hud"] and not x["hud"]["hidden"] and x["hero"]]
    # A HUD that is hidden for the whole window (cutscene, or a wrong visibility flag) still gets checked, but
    # only as warnings: hidden masks may legitimately sit off screen.
    soft = not check("HUD visible in some sampled frame", bool(shown), f"vis={hud['vis']}", warn_only=True)
    s = shown[-1] if shown else states[-1]
    hud, h, screen = s["hud"], s["hero"], s["cam"]["screen"] if s["cam"] else None
    box = (0.0, 0.0, float(screen[0]), float(screen[1])) if screen else None
    masks = [m for m in hud["masks"] if m is not None]
    active = [m for m in masks if m[1]]
    check("health_display masks found", len(masks) >= h["max_health"],
          f"{len(masks)} found, {len(active)} active, max_health {h['max_health']}; states {[m[2] for m in active]}")
    rects = [m[3] for m in active if m[3] is not None]
    check("active masks have rects", len(rects) == len(active) > 0, f"{len(rects)}/{len(active)}", warn_only=soft)
    if box and rects:
        check("mask rects inside the screen", all(inside(r[0], r[1], box) and inside(r[2], r[3], box) for r in rects),
              str([[round(v) for v in r] for r in rects[:6]]), warn_only=soft)
        xs = [r[0] for r in rects]
        check("mask rects ordered left to right", xs == sorted(xs), warn_only=True)
    spool = hud["spool"]
    if check("silk spool found", spool is not None):
        slots = spool["slots"] or []
        check("spool slots == silk_max", len(slots) == h["silk_max"], f"{len(slots)} slots, silk_max {h['silk_max']}")
        if box and slots:
            check("spool slots inside the screen", all(p is not None and inside(p[0], p[1], box) for p in slots),
                  f"first {fmt(slots[0])} pitch {fmt(spool['pitch'])} px", warn_only=soft)
        check("chunks shown == silk", len(spool["chunks"]) == h["silk"], f"{len(spool['chunks'])} chunks, silk {h['silk']}",
              warn_only=True)
    check("bind orb rect", hud["bind_orb"] is not None, str(fmt(hud["bind_orb"])), warn_only=True)
    print(f"  tools: {fmt(hud['tools'])}")


def check_costs(states: list[dict]) -> None:
    print("\n== cost (previous-frame main-thread us, C14) ==")
    totals = [s["cost_us"] for s in states]
    for key in KEYS:
        xs = [s["cost_ex"][key] for s in states if key in s["cost_ex"]]
        if not xs:
            check(f"cost_ex[{key}] reported", False)
            continue
        p50, p99 = statistics.median(xs), pctl(xs, 0.99)
        check(f"cost_ex[{key}] p50 < {COST_LIMIT_US} us", p50 < COST_LIMIT_US, f"p50 {p50:.0f} p99 {p99:.0f} max {max(xs)} (n={len(xs)})")
    sizes = {k: statistics.median(len(msgpack.packb(s[k])) for s in states) for k in KEYS}
    print(f"  STATE build total p50 {statistics.median(totals):.0f} us, p99 {pctl(totals, 0.99)} us; "
          f"section sizes p50 {sizes} bytes")


def check_move(link: OracleLink) -> None:
    print("\n== move: right 30 frames, then left 30 frames ==")
    s = link.wait_state()
    if s["pause"] and s["pause"]["bench"]:
        # Loading a save puts Hornet on the bench: the first direction press only makes her get up (P3).
        tap(link, "right", 8)
        link.wait_state(lambda s: not s["pause"]["bench"] and s["hero"]["hero_accepting_input"], timeout_s=10)
        time.sleep(1.0)
    for button, sign in (("right", 1), ("left", -1)):
        x0 = link.wait_state()["hero"]["pos"][0]
        hold(link, mask(button), 30)
        start = link.frame
        best_v, facing, clip = 0.0, 0, None
        while True:
            s = link.wait_state(newer_than=link.frame, timeout_s=3)
            h = s["hero"]
            if s["f"] >= start + 10:
                best_v = max(best_v, h["vel"][0] * sign)
                facing, clip = h["facing"], h["anim"] and h["anim"]["clip"]
            if s["f"] >= start + 28:
                break
        s = link.wait_state(lambda s: s["act"]["mask"] == 0 and s["f"] >= start + 35, timeout_s=3)
        dx = s["hero"]["pos"][0] - x0
        check(f"{button}: facing", facing == sign, f"facing {facing} clip {clip}")
        moved = dx * sign > 0.5
        check(f"{button}: vel.x follows the motion", best_v > 0.5 if moved else True,
              f"max vel.x*sign {best_v:.2f}, dx {dx:+.2f}")
        check(f"{button}: moved", moved, f"dx {dx:+.2f} (blocked by a wall?)", warn_only=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--no-load", action="store_true", help="do not navigate menus; require gameplay")
    ap.add_argument("--no-move", action="store_true", help="do not walk left/right")
    ap.add_argument("--dump", help="write the hud.dump RPC result (HUD hierarchy) to this JSON file")
    args = ap.parse_args()

    link = OracleLink(instance=args.instance)
    rpcs = set(link.hello["rpcs"])
    print("hello:", {k: link.hello[k] for k in ("plugin", "game", "instance")})
    missing = {"schema.cstate", "schema.hero", "hud.dump"} - rpcs
    if missing:
        print(f"FAIL: RPCs missing {missing}: is Hero.HeroModule.Install wired into Modules.InstallAll?")
        return 1
    schema = link.rpc("schema.cstate")
    enums = link.rpc("schema.hero")
    print(f"schema.cstate: {len(schema['bools'])} bools in {schema['words']} words, ints {schema['ints']}")
    check("cState has 92 bools + 4 ints (1.0.30000)", len(schema["bools"]) == 92 and len(schema["ints"]) == 4, warn_only=True)

    s = link.wait_state(timeout_s=10)
    if s["game"] is None or s["game"]["gs"] != GS_PLAYING or s["hero"] is None:
        if args.no_load:
            print("FAIL: not in gameplay and --no-load given")
            return 1
        s = load_save(link)
    link.wait_state(lambda s: s["hero"] is not None and s["hero"]["hero_accepting_input"], timeout_s=30)
    time.sleep(1.0)

    states = [x for x in collect(link, args.seconds) if x["hero"] is not None]
    print(f"collected {len(states)} gameplay STATEs over {args.seconds:.1f} s")
    if not check("gameplay STATEs collected", len(states) > 10):
        return 1
    s = states[-1]
    check_hero(s, schema, enums)
    viewport = check_cam(s)
    if viewport:
        check_projection(s, viewport)
    check_hud(states)
    check_costs(states)
    if not args.no_move:
        check_move(link)

    dump = link.rpc("hud.dump", depth=4, max=600)
    fsm_nodes = [n["path"] for n in dump["nodes"] if any("health_display" in c for c in n["comps"])]
    print(f"\nhud.dump: root {dump['root']}, {len(dump['nodes'])} nodes (truncated={dump['truncated']}), "
          f"health_display at {fsm_nodes[:3]}{'...' if len(fsm_nodes) > 3 else ''}")
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=1)
        print(f"wrote {args.dump}")
    link.close()

    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f"\n{'FAIL' if fails else 'PASS'}: {len(results) - len(fails) - len(warns)} passed, {len(warns)} warnings, {len(fails)} failed")
    for level, name, detail in fails + warns:
        print(f"  {level} {name}: {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
