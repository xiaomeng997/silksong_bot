"""Soak policy and full-ability mode (ssbot.tools.soak --abilities): interaction-safe up/down in every mode, key
coverage per mode, the keys it must never press, press timing, argument plumbing, the grant helpers and the worker's
grant flow against a fake link. No game."""
import argparse
import json
import random
import sys
import time

import msgpack
import pytest

from ssbot.ipc.framing import BIT as BUTTON_BIT
from ssbot.ipc.framing import MsgType, encode
from ssbot.tools import soak as S

ALL_BINDINGS = {"neutral": "Silk Spear", "up": None, "down": "Straight Pin"}
BASE = {"left", "right", "jump", "attack", "dash", "up", "down", "bind"}
ALLOWED = {None: BASE, "movement": BASE | {"clawline"}, "combat": BASE | {"quickcast"},
           "all": BASE | {"clawline", "quickcast"}}


def run(mode, bindings=None, frames=60_000, seed=1):
    keys, macros = S.ability_keys(mode, bindings)
    p = S.Policy(random.Random(seed), keys, macros)
    masks, macro_of = [], []
    for _ in range(frames):
        masks.append(p.step())
        macro_of.append(p.macro)
    return p, masks, macro_of


def key_runs(masks, bit):
    """[(start, length)] of consecutive frames with bit set."""
    out, start = [], None
    for i, m in enumerate(masks + [0]):
        if m & bit and start is None:
            start = i
        elif not m & bit and start is not None:
            out.append((start, i - start))
            start = None
    return out


def names_in(m: int) -> set[str]:
    return {k for k, b in BUTTON_BIT.items() if m & (1 << b)}


# ---- policy -----------------------------------------------------------------------------------------------------


H = S.BIT["left"] | S.BIT["right"]
BINDING_CASES = [ALL_BINDINGS, {}, {"neutral": None, "up": None, "down": "Straight Pin"}, {"neutral": "Silk Spear"}]


@pytest.mark.parametrize("mode", [None, *S.ABILITY_MODES])
@pytest.mark.parametrize("bindings", BINDING_CASES)
def test_up_and_down_never_start_an_interaction(mode, bindings):
    """InteractManager.cs:244 (1.0.30000) starts an NPC dialogue, bench or door on Up/Down.WasPressed with neither Left
    nor Right pressed. Every up/down rising edge of every mode is in a frame with left or right held (the mask is
    applied atomically per frame), the same key held on the frame before too (the run's own edge may lag a frame in the
    latch), and kept held for the whole up/down hold; only the Silk Soar macro lets go of it (S needs only down), two
    frames after down went in."""
    edges = {k: 0 for k in S.VERTICAL}
    for seed in range(30):
        _, masks, macro_of = run(mode, bindings, frames=8_000, seed=seed)
        for m in masks:
            assert m & H != H  # never left and right together
        for key in S.VERTICAL:
            for start, n in key_runs(masks, S.BIT[key]):
                side = masks[start] & H
                assert side in (S.BIT["left"], S.BIT["right"]), (key, seed, start)
                assert start > 0 and masks[start - 1] & side, (key, seed, start)
                held = n if macro_of[start] != "silk_soar" else 2
                assert all(masks[i] & side for i in range(start, min(start + held, len(masks)))), (key, seed, start)
                edges[key] += 1
    assert edges["up"] > 500 and edges["down"] > 500


def test_default_policy_up_slashes_and_down_slashes():
    """The default soak presses up now (up + attack = up-slash) and still down (down + attack in the air)."""
    _, masks, _ = run(None, frames=60_000, seed=5)
    attack_edges = [a for a, _ in key_runs(masks, S.BIT["attack"])]
    assert sum(1 for a in attack_edges if masks[a] & S.BIT["up"]) > 100
    assert sum(1 for a in attack_edges if masks[a] & S.BIT["down"]) > 50
    default = S.Policy(random.Random(3))
    keys, macros = S.ability_keys(None)
    assert keys == S.DEFAULT_KEYS and macros == ()
    via_modes = S.Policy(random.Random(3), keys, macros)  # what the worker builds without --abilities
    assert [default.step() for _ in range(5000)] == [via_modes.step() for _ in range(5000)]


@pytest.mark.parametrize("mode", [None, *S.ABILITY_MODES])
def test_policy_never_presses_forbidden_keys(mode):
    _, masks, _ = run(mode, ALL_BINDINGS)
    seen = set().union(*(names_in(m) for m in masks))
    assert not seen & set(S.FORBIDDEN_KEYS)
    assert seen <= ALLOWED[mode]
    assert {"pause", "inventory", "map", "quickmap", "journal", "quests", "needolin"} <= set(S.FORBIDDEN_KEYS)
    assert not set(S.VERTICAL) & set(S.FORBIDDEN_KEYS)


@pytest.mark.parametrize("mode", [None, *S.ABILITY_MODES])
def test_policy_key_coverage_per_mode(mode):
    p, masks, _ = run(mode, ALL_BINDINGS)
    seen = set().union(*(names_in(m) for m in masks))
    assert seen == ALLOWED[mode]
    longest = {k: max((n for _, n in key_runs(masks, S.BIT[k])), default=0) for k in ("dash", "jump", "attack")}
    movement, combat = mode in ("movement", "all"), mode in ("combat", "all")
    assert (longest["dash"] >= 16) == movement          # sprint holds
    assert (longest["jump"] >= 30) == movement          # the glide press of the air_jumps macro
    assert (longest["attack"] >= 106) == combat         # Needle Strike charge (about 102 frames)
    assert (p.counts["air_jumps"] > 0) == movement
    assert (p.counts["silk_soar"] > 0) == movement
    assert (p.counts["down_cast"] > 0) == combat
    assert (p.counts["clawline"] > 0) == movement
    assert (p.counts["quickcast"] > 0) == combat
    assert p.counts["up"] > 0 and p.counts["down"] > 0


def test_quickcast_only_for_bound_directions():
    keys, macros = S.ability_keys("combat", {})
    assert "quickcast" not in keys and not macros          # nothing equipped that QuickCast could throw
    keys, macros = S.ability_keys("combat", {"neutral": None, "up": "Straight Pin", "down": None})
    assert "quickcast" not in keys and not macros          # Up-bound only: never cast with up held
    keys, macros = S.ability_keys("all", {"neutral": None, "down": "Straight Pin"})
    assert "quickcast" not in keys and [m.name for m in macros] == ["air_jumps", "silk_soar", "down_cast"]
    _, masks, macro_of = run("all", {"neutral": None, "down": "Straight Pin"})
    cast = [(m, mac) for m, mac in zip(masks, macro_of) if m & S.BIT["quickcast"]]
    assert cast and all(m & S.BIT["down"] and mac == "down_cast" for m, mac in cast)
    keys, macros = S.ability_keys("combat", {"neutral": "Silk Spear"})
    assert "quickcast" in keys and not macros
    with pytest.raises(ValueError):
        S.ability_keys("everything")


@pytest.mark.parametrize("mode", ["movement", "combat", "all"])
def test_clawline_and_quickcast_never_with_up_or_down_outside_macros(mode):
    _, masks, macro_of = run(mode, ALL_BINDINGS, frames=80_000, seed=7)
    down, up = S.BIT["down"], S.BIT["up"]
    both = 0
    for m, mac in zip(masks, macro_of):
        if m & (S.BIT["clawline"] | S.BIT["quickcast"]) and m & (down | up):
            both += 1
            assert mac in ("silk_soar", "down_cast") and not m & up
            if m & S.BIT["clawline"]:
                assert not m & H  # Silk Soar needs only down (m0:N41)
    assert both > 0
    # a plain clawline / quickcast press never starts with up or down held
    for key in ("clawline", "quickcast"):
        for start, _ in key_runs(masks, S.BIT[key]):
            if macro_of[start] is None:
                assert not masks[start] & (down | up)


def test_macro_shapes():
    d, c, f, j, r, left = (S.BIT[k] for k in ("down", "clawline", "quickcast", "jump", "right", "left"))
    rng = random.Random(0)
    assert S.SILK_SOAR.expand(rng, r) == [d | r, d | r, d, d, d | c, d | c, d | c, d]
    assert S.DOWN_CAST.expand(rng, left) == [d | left, d | left, d | left | f, d | left | f, d | left | f, d | left]
    assert set(S.SILK_SOAR.keys) == {"down", "clawline"} and set(S.DOWN_CAST.keys) == {"down", "quickcast"}
    assert S.AIR_JUMPS.keys == ("jump",)
    for _ in range(200):  # jump, release, jump (double jump), release, long jump (glide); right held throughout
        seq = S.AIR_JUMPS.expand(rng, r)
        assert all(m & r for m in seq)
        runs = key_runs(seq, j)
        assert len(runs) == 3 and all(4 <= n <= 8 for _, n in runs[:2]) and 30 <= runs[2][1] <= 80
        assert all(3 <= b - (a + n) <= 6 for (a, n), (b, _) in zip(runs, runs[1:]))
    p, masks, macro_of = run("movement", frames=60_000, seed=3)
    starts = [i for i in range(len(masks)) if macro_of[i] == "silk_soar" and (i == 0 or macro_of[i - 1] != "silk_soar")]
    assert starts and len(starts) == p.counts["silk_soar"]
    for i in starts:
        if i + 8 <= len(masks):
            side = masks[i] & H
            assert side and masks[i - 1] & side  # started inside a left/right run
            assert masks[i:i + 8] == S.SILK_SOAR.expand(rng, side)


@pytest.mark.parametrize("mode", [None, *S.ABILITY_MODES])
def test_every_press_and_release_lasts_two_frames(mode):
    """The oracle's HoldFilter would stretch shorter presses/releases (C19); the policy never needs it."""
    for seed in (11, 12, 13):
        _, masks, _ = run(mode, ALL_BINDINGS, frames=60_000, seed=seed)
        for key, bit in S.BIT.items():
            rs = [(a, n) for a, n in key_runs(masks, bit) if a + n < len(masks)]  # not the one cut off at the end
            assert all(n >= 2 for _, n in rs), key
            gaps = [b - (a + n) for (a, n), (b, _) in zip(rs, rs[1:])]
            assert all(g >= 2 for g in gaps), key


# ---- helpers ----------------------------------------------------------------------------------------------------


def test_ability_request():
    assert S.ability_request("movement", 3) == {"set": "movement"}
    assert S.ability_request("combat", 0) == {"set": "combat", "skill": "Silk Spear", "tools": ["Straight Pin"],
                                              "unlock_slots": True}
    r = S.ability_request("all", 7)
    assert r["skill"] == S.SKILL_ROTATION[7 % 6] and r["tools"] == [S.TOOL_ROTATION[7 % 6]]
    assert S.ability_request("all", 0, tools="", skill="Rune Rage")["tools"] == []
    assert S.ability_request("combat", 0, tools=" Tack, Tri Pin ,")["tools"] == ["Tack", "Tri Pin"]
    assert S.ability_request("combat", 0, skill="Parry")["skill"] == "Parry"
    with pytest.raises(ValueError):
        S.ability_request("none", 0)


def test_expected_can_and_gaps():
    assert S.expected_can("movement") == S.expected_can("all") == ("dash", "harpoon", "super_jump")
    assert S.expected_can("combat") == ()
    res = {"requested": ["Silk Spear", "Straight Pin", "Tack"],
           "slots": [{"tool": None}, {"tool": "Straight Pin"}, {"tool": "Silk Spear"}, {"tool": "Rosary Magnet"}]}
    want = S.granted_equips(res)
    assert want == ["Silk Spear", "Straight Pin"]
    s = {"hero": {"can": {"dash": True, "harpoon": True, "super_jump": False},
                  "tools": [None, "Straight Pin", "Silk Spear", "Rosary Magnet"]}}
    assert S.ability_gaps(s, ("dash", "harpoon", "super_jump"), want) == ["can.super_jump"]
    s["hero"]["can"]["super_jump"] = True
    assert S.ability_gaps(s, ("dash", "harpoon", "super_jump"), want) == []
    assert S.ability_gaps({"hero": None}, (), ["Tack"]) == ["tool Tack"]
    assert S.ability_gaps(None, ("dash",), []) == ["can.dash"]


def slot(i, typ, binding, tool):
    return {"index": i, "type": typ, "binding": binding, "locked": False, "tool": tool}


def test_unreachable_attack_items():
    """QuickCast is pressed only without a direction and with down: an Up-bound item, or one behind an earlier attack
    tool with the same binding, is never thrown in the soak."""
    ok = {"requested": ["Silk Spear", "Straight Pin"],
          "slots": [slot(0, "Red", "Down", "Straight Pin"), slot(1, "Blue", None, "Rosary Magnet"),
                    slot(2, "Skill", "Neutral", "Silk Spear")],
          "bindings": {"neutral": "Silk Spear", "up": None, "down": "Straight Pin"}}
    assert S.unreachable(ok) == []
    up = {"requested": ["Silk Spear", "Straight Pin"],
          "slots": [slot(0, "Red", "Neutral", "Straight Pin"), slot(2, "Skill", "Up", "Silk Spear")],
          "bindings": {"neutral": "Straight Pin", "up": "Silk Spear", "down": None}}
    assert S.unreachable(up) == ["Silk Spear (slot 2: Skill Up)"]
    shadowed = {"requested": ["Silk Spear", "Straight Pin"],
                "slots": [slot(0, "Red", "Neutral", "Straight Pin"), slot(2, "Skill", "Neutral", "Silk Spear")],
                "bindings": {"neutral": "Straight Pin", "up": None, "down": None}}
    assert S.unreachable(shadowed) == ["Silk Spear (slot 2: Skill Neutral)"]
    not_requested = {"requested": [], "slots": up["slots"], "bindings": up["bindings"]}
    assert S.unreachable(not_requested) == []  # a tool the save already had is not the grant's business


def test_parse_args_and_worker_command():
    a = S.parse_args(["--minutes", "5"])
    assert a.abilities is None and a.ability_tools is None and a.ability_skill is None
    cmd = S.worker_command(a, 2, S.RUNS / "x", 1_790_000_000.4)
    assert cmd == [sys.executable, "-m", "ssbot.tools.soak", "--worker", "2", "--out", str(S.RUNS / "x"),
                   "--deadline", "1790000000"]  # the default soak's worker command, unchanged (marker on)
    assert a.no_marker is False and S.parse_args(cmd[3:]).no_marker is False
    off = S.worker_command(S.parse_args(["--minutes", "5", "--no-marker"]), 0, S.RUNS, 1.0)
    assert off[-1] == "--no-marker" and S.parse_args(off[3:]).no_marker is True
    a = S.parse_args(["--minutes", "5", "--instances", "2", "--abilities", "all", "--ability-tools", "Tack,Tri Pin",
                      "--ability-skill", "Thread Storm"])
    cmd = S.worker_command(a, 1, S.RUNS / "x", 1_790_000_000)
    w = S.parse_args(cmd[3:])
    assert (w.worker, w.abilities, w.ability_tools, w.ability_skill) == (1, "all", "Tack,Tri Pin", "Thread Storm")
    w = S.parse_args(S.worker_command(S.parse_args(["--hours", "1", "--abilities", "movement"]), 0, S.RUNS, 1.0)[3:])
    assert (w.abilities, w.ability_tools, w.ability_skill) == ("movement", None, None)
    w = S.parse_args(S.worker_command(S.parse_args(["--hours", "1", "--abilities", "combat", "--ability-tools", ""]),
                                      0, S.RUNS, 1.0)[3:])
    assert w.ability_tools == "" and S.ability_request(w.abilities, 0, w.ability_tools)["tools"] == []


@pytest.mark.parametrize("argv", [
    ["--minutes", "5", "--abilities", "everything"],
    ["--minutes", "5", "--ability-tools", "Tack"],
    ["--minutes", "5", "--abilities", "movement", "--ability-skill", "Parry"],
    ["--minutes", "5", "--abilities", "combat", "--ability-skill", "Fireball"],
    ["--abilities", "all"],
])
def test_parse_args_refuses(argv):
    with pytest.raises(SystemExit):
        S.parse_args(argv)


def state_frame(f: int, hero: dict, **more) -> bytes:
    return encode(MsgType.STATE, f, msgpack.packb({"f": f, "hero": hero, **more}))


def test_frame_stats_counts_interaction_rising_edges():
    """pause.interact (InteractManager.BlockingInteractable) going false -> true is one interaction the policy started;
    a frame without the pause map (a load) keeps the last value, and the value carries across windows."""
    st = S.FrameStats()
    seq = [None, False, True, True, "nomap", True, False, False, True]
    for f, v in enumerate(seq, 1):
        st.on_raw(MsgType.STATE, state_frame(f, {}, pause=None if v == "nomap" else {"interact": v, "bench": False}))
    assert st.take()["interacts"] == 2
    st.on_raw(MsgType.STATE, state_frame(20, {}, pause={"interact": True}))  # still the same interaction
    assert st.take()["interacts"] == 0
    for f, v in ((21, False), (22, True)):
        st.on_raw(MsgType.STATE, state_frame(f, {}, pause={"interact": v}))
    assert st.take()["interacts"] == 1
    fresh = S.FrameStats()  # a worker that starts mid-interaction does not count it
    fresh.on_raw(MsgType.STATE, state_frame(1, {}, pause={"interact": True}))
    assert fresh.take()["interacts"] == 0


def test_frame_stats_ability_evidence():
    names = ["facingRight", "onGround", "dashing", "doubleJumping", "floating", "isToolThrowing"]
    cstate = [(1 << 2) | (1 << 5)]  # dashing, isToolThrowing
    hero = {"cstate": cstate, "anim": {"clip": "Dash"}, "spell": ["Inactive", 0.5]}
    plain = S.FrameStats()
    plain.on_raw(MsgType.STATE, state_frame(1, hero))
    assert "abilities" not in plain.take()  # default soak: no extra counting, same episode lines
    st = S.FrameStats()
    st.track_abilities(names)
    assert st.ability_bits == {"dashing": 2, "doubleJumping": 3, "floating": 4, "isToolThrowing": 5}
    for f in range(1, 4):
        st.on_raw(MsgType.STATE, state_frame(f, hero))
    st.on_raw(MsgType.STATE, state_frame(4, {"cstate": [1 << 4], "anim": {"clip": "Float"}, "spell": None}))
    st.on_raw(MsgType.STATE, state_frame(5, None))
    d = st.take()
    assert d["abilities"] == {"cstate": {"dashing": 3, "isToolThrowing": 3, "floating": 1},
                              "clips": {"Dash": 3, "Float": 1}, "spell": {"Inactive": 3}}
    assert st.take()["abilities"] == {"cstate": {}, "clips": {}, "spell": {}}


def test_ability_evidence_sums_windows():
    eps = [{"presses": {"dash": 3, "silk_soar": 1},
            "stats_between": {"abilities": {"cstate": {"dashing": 2}, "clips": {"Dash": 2}, "spell": {}}},
            "stats": {"abilities": {"cstate": {"dashing": 5, "floating": 1}, "clips": {"Idle": 9}, "spell": {"A": 1}}}},
           {"presses": {"dash": 1}, "stats": {"events": {}}}]
    ev = S.ability_evidence(eps)
    assert ev["presses"] == {"dash": 4, "silk_soar": 1}
    assert ev["cstate_frames"] == {"dashing": 7, "floating": 1}
    assert ev["clips"] == {"Idle": 9, "Dash": 2} and ev["spell_states"] == {"A": 1}


# ---- worker grant flow (fake link) --------------------------------------------------------------------------------


def standing(f: int, **hero) -> dict:
    """A STATE with Hornet up and taking input (stand_up returns at once)."""
    return {"f": f, "game": {"gs": 4, "paused": False, "scene": "Bone_05"},
            "pause": {"bench": False, "interact": False},
            "hero": {"hero_accepting_input": True, "pos": [1.0, 2.0], **hero}}


class FakeLink:
    """answers: a reply, an exception to raise, or a list of those (one per call, the last one repeats)."""

    def __init__(self, state: dict, grant, rpcs=("abilities.grant", "abilities.list"), suppress: bool = True):
        self.hello = {"rpcs": list(rpcs)}
        self.state = state
        self.frame = state.get("f", 0)
        self.closed = False
        self.calls: list[tuple[str, dict]] = []
        self.answers = {"schema.cstate": {"bools": ["facingRight", "onGround", "dashing"], "words": 1},
                        "guards.set": {"save_suppression": suppress}, "abilities.grant": grant,
                        "input.release": {}, "savestate.list": {"states": []}, "savestate.save": {},
                        "frame.marker": {"on": True, "corner": "tr", "cell": 3}}

    def rpc(self, name, /, timeout_s=10.0, **args):
        self.calls.append((name, args))
        a = self.answers[name]
        if isinstance(a, list):
            a = a.pop(0) if len(a) > 1 else a[0]
        if isinstance(a, Exception):
            raise a
        return a

    def wait_state(self, pred=lambda s: True, timeout_s=10.0, newer_than=None):
        if pred(self.state):
            return self.state
        raise TimeoutError("fake: condition not met")

    def subscribe_raw(self, fn):
        pass

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch):
    monkeypatch.setattr(S.time, "sleep", lambda s: None)


def worker(tmp_path, mode="all", instance=1, tools=None, skill=None, deadline=1e12) -> S.Worker:
    args = argparse.Namespace(worker=instance, out=str(tmp_path), deadline=deadline, abilities=mode,
                              ability_tools=tools, ability_skill=skill)
    return S.Worker(args)


def grant_reply(bindings, slots, requested, unplaced=()):
    return {"set": "all", "changed": ["hasDash (Swift Step)"], "unplaced": list(unplaced), "requested": requested,
            "bindings": bindings, "slots": slots, "sets": {"movement": True, "combat": True, "all": True}}


def log_lines(tmp_path, i=1):
    return [json.loads(x) for x in (tmp_path / f"worker_{i}.jsonl").read_text(encoding="utf-8").splitlines()]


def calls(link, name):
    return [c for c in link.calls if c[0] == name]


GRANTED = {"can": {"dash": True, "harpoon": True, "super_jump": True}, "tools": [None, "Tri Pin", "Thread Sphere"]}
REACHABLE = grant_reply({"neutral": "Thread Sphere", "up": None, "down": "Tri Pin"},
                        [slot(1, "Red", "Down", "Tri Pin"), slot(2, "Skill", "Neutral", "Thread Sphere")],
                        ["Thread Sphere", "Tri Pin"])


def test_worker_grant_flow(tmp_path):
    w = worker(tmp_path, "all", 1)
    w.link = FakeLink(standing(50, **GRANTED), REACHABLE)
    assert w.grant_abilities() is True
    w.log.close()
    assert [c[0] for c in w.link.calls] == ["schema.cstate", "guards.set", "abilities.grant"]
    assert w.link.calls[1][1] == {"save_suppression": True}
    assert w.link.calls[2][1] == {"set": "all", "skill": "Thread Sphere", "tools": ["Tri Pin"], "unlock_slots": True}
    rec = log_lines(tmp_path)[-1]
    assert rec["kind"] == "abilities" and rec["ok"] is True and rec["want_tools"] == ["Thread Sphere", "Tri Pin"]
    assert rec["attempts"] == 1 and rec["retries"] == []
    assert {"clawline", "quickcast", "up", "down"} <= set(rec["keys"])
    assert rec["macros"] == ["air_jumps", "silk_soar", "down_cast"]
    assert w.stats.ability_bits == {"dashing": 2}
    assert "quickcast" in w.keys


def test_worker_grant_retries_a_refusal(tmp_path):
    """A grant refused for a passing reason (a transition, a load) is tried again after a stand_up; one line."""
    w = worker(tmp_path, "all", 1)
    w.link = FakeLink(standing(50, **GRANTED), [S.OracleError("not in a steady gameplay state"), REACHABLE])
    assert w.grant_abilities() is True
    w.log.close()
    lines = [x for x in log_lines(tmp_path) if x["kind"] == "abilities"]
    assert len(lines) == 1 and lines[0]["ok"] is True and lines[0]["attempts"] == 2
    assert "steady gameplay" in lines[0]["retries"][0]
    assert len(calls(w.link, "abilities.grant")) == 2


def test_worker_grant_not_seen_in_state(tmp_path):
    w = worker(tmp_path, "movement", 1)
    res = grant_reply({"neutral": None, "up": None, "down": None}, [], [])
    w.link = FakeLink(standing(9, can={"dash": True, "harpoon": False, "super_jump": True}, tools=[]), res)
    assert w.grant_abilities() is False
    w.log.close()
    rec = log_lines(tmp_path)[-1]
    assert rec["ok"] is False and rec["gaps"] == ["can.harpoon"] and rec["attempts"] == S.GRANT_TRIES
    assert "clawline" in w.keys and "quickcast" not in w.keys


def test_worker_grant_with_an_unplaced_tool_fails(tmp_path):
    w = worker(tmp_path, "combat", 0)
    res = grant_reply({"neutral": "Silk Spear", "up": None, "down": None}, [slot(2, "Skill", "Neutral", "Silk Spear")],
                      ["Silk Spear", "Straight Pin"], unplaced=["Straight Pin: no unlocked Red slot on Hunter ..."])
    w.link = FakeLink(standing(3, can={}, tools=["Silk Spear"]), res)
    assert w.grant_abilities() is False
    w.log.close()
    rec = log_lines(tmp_path, 0)[-1]
    assert rec["ok"] is False and rec["gaps"][0].startswith("unplaced: Straight Pin")
    assert rec["want_tools"] == ["Silk Spear"] and "quickcast" in w.keys and not w.macros


def test_worker_grant_with_a_skill_quickcast_never_throws_fails(tmp_path):
    """The skill landed on Up (never cast with up held): hero.tools shows it, but the soak would never use it."""
    w = worker(tmp_path, "combat", 0)
    res = grant_reply({"neutral": "Straight Pin", "up": "Silk Spear", "down": None},
                      [slot(0, "Red", "Neutral", "Straight Pin"), slot(2, "Skill", "Up", "Silk Spear")],
                      ["Silk Spear", "Straight Pin"])
    w.link = FakeLink(standing(3, can={}, tools=["Straight Pin", None, "Silk Spear"]), res)
    assert w.grant_abilities() is False
    w.log.close()
    rec = log_lines(tmp_path, 0)[-1]
    assert rec["gaps"] == ["never thrown: Silk Spear (slot 2: Skill Up)"]


def test_worker_grant_refused_without_rpc_or_suppression(tmp_path):
    w = worker(tmp_path, "combat", 1)
    w.link = FakeLink(standing(1), {}, rpcs=("ping",))
    assert w.grant_abilities() is False
    w.link = FakeLink(standing(1), {}, suppress=False)
    assert w.grant_abilities() is False
    w.log.close()
    a, b = log_lines(tmp_path)[-2:]
    assert a["ok"] is False and "no abilities.grant" in a["error"]
    assert b["ok"] is False and "save suppression" in b["error"]
    assert not calls(w.link, "abilities.grant")  # nothing granted without suppression
    assert "quickcast" not in w.keys  # no bindings known: no QuickCast


@pytest.mark.parametrize("ok", [False, True])
def test_worker_takes_no_savestate_without_the_grant(tmp_path, monkeypatch, ok):
    """A savestate without the grant would be reused by every later start of the worker (and each reset would undo a
    later grant): a failed grant exits 6 before savestate.save; a good one goes on to it."""
    link = FakeLink(standing(7, **GRANTED), REACHABLE if ok else S.OracleError("harness busy (warp)"))
    monkeypatch.setattr(S, "OracleLink", lambda instance, connect_timeout_s: link)
    monkeypatch.setattr(S.Worker, "enter_gameplay", lambda self: None)
    monkeypatch.setattr(S.Worker, "start_segment", lambda self: None)
    monkeypatch.setattr(S.Worker, "done", lambda self: True)
    w = worker(tmp_path, "all", 1, deadline=time.time() + 3600)
    code = w.run()
    exit_line = log_lines(tmp_path)[-1]
    if ok:
        assert code == 0 and calls(link, "savestate.save") == [("savestate.save", {"state": w.name})]
    else:
        assert code == S.EXIT_NO_GRANT == exit_line["code"] and "no savestate" in exit_line["why"]
        assert not calls(link, "savestate.list") and not calls(link, "savestate.save")
        assert len(calls(link, "abilities.grant")) == S.GRANT_TRIES


# ---- the frame marker: on in every worker, as in every training session -------------------------------------------

# STATE "mk" of the default marker on a 1280x720 render, as SsOracle reports it.
MK_720 = {"drawn": True, "corner": "tr", "cell": 3, "rect": [1235.0, 3.0, 1277.0, 15.0], "screen": [1280, 720]}

def test_frame_stats_count_marked_frames():
    st = S.FrameStats()
    for f, mk in enumerate([None, {"drawn": True}, {"drawn": False}, {"drawn": True}], 1):
        st.on_raw(MsgType.STATE, state_frame(f, {}, mk=mk))
    assert st.take()["marked"] == 2 and st.take()["marked"] == 0


def test_worker_turns_the_marker_on_and_survives_a_refusal(tmp_path):
    w = worker(tmp_path, None, 1)
    drawn = standing(9) | {"mk": MK_720}
    w.link = FakeLink(drawn, None)
    w.turn_marker_on()
    w.link = FakeLink(standing(9), None)
    w.link.answers["frame.marker"] = S.OracleError("-ssbot-human: a person's session is recorded without the marker")
    w.turn_marker_on()
    w.link = FakeLink(standing(9), None)                     # accepted, but no STATE shows it: turned off again
    w.turn_marker_on()
    assert [(n, a.get("on")) for n, a in w.link.calls] == [("frame.marker", True), ("frame.marker", False)]
    w.log.close()
    lines = [x for x in log_lines(tmp_path) if x["kind"] == "marker"]
    assert [(x["on"], x.get("cell")) for x in lines] == [(True, 3), (False, None), (False, None)]
    assert "ssbot-human" in lines[1]["error"] and lines[2]["error"].startswith("TimeoutError")


@pytest.mark.parametrize("no_marker", [False, True])
def test_worker_run_turns_the_marker_on_after_entering_gameplay(tmp_path, monkeypatch, no_marker):
    link = FakeLink(standing(7) | {"mk": MK_720}, None, rpcs=())
    order = []
    monkeypatch.setattr(S, "OracleLink", lambda instance, connect_timeout_s: link)
    monkeypatch.setattr(S.Worker, "enter_gameplay", lambda self: order.append("gameplay"))
    monkeypatch.setattr(S.Worker, "start_segment", lambda self: None)
    monkeypatch.setattr(S.Worker, "done", lambda self: True)
    args = argparse.Namespace(worker=1, out=str(tmp_path), deadline=time.time() + 3600, abilities=None,
                              ability_tools=None, ability_skill=None, no_marker=no_marker)
    assert S.Worker(args).run() == 0
    names = [c[0] for c in link.calls]
    if no_marker:
        assert "frame.marker" not in names
    else:
        assert names[:1] == ["frame.marker"] and names.index("frame.marker") < names.index("savestate.list")
        assert [x for x in log_lines(tmp_path) if x["kind"] == "marker"][0]["on"] is True
