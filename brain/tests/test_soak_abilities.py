"""Soak full-ability mode (ssbot.tools.soak --abilities): policy key coverage per mode, the keys it must never press,
press timing, argument plumbing, the grant helpers and the worker's grant flow against a fake link. No game."""
import argparse
import json
import random
import sys

import msgpack
import pytest

from ssbot.ipc.framing import BIT as BUTTON_BIT
from ssbot.ipc.framing import MsgType, encode, mask
from ssbot.tools import soak as S

ALL_BINDINGS = {"neutral": "Silk Spear", "up": None, "down": "Straight Pin"}
BASE = {"left", "right", "jump", "attack", "dash", "down", "bind"}
ALLOWED = {None: BASE, "movement": BASE | {"clawline"}, "combat": BASE | {"quickcast"},
           "all": BASE | {"clawline", "quickcast"}}


class OldPolicy:
    """The soak policy as it was before the ability modes (verbatim), to prove the default stream is unchanged."""

    BIT = {name: mask(name) for name in ("left", "right", "jump", "attack", "dash", "down", "bind")}

    def __init__(self, rng: random.Random):
        self.r = rng
        self.move = None
        self.move_left = 0
        self.timers = {"jump": 0, "attack": 0, "dash": 0, "down": 0, "bind": 0}
        self.rest = {k: 0 for k in self.timers}

    def step(self) -> int:
        r = self.r
        if self.move_left <= 0:
            self.move = r.choices(("left", "right", None), (0.42, 0.42, 0.16))[0]
            self.move_left = r.randint(8, 100)
        self.move_left -= 1
        starts = {"jump": (0.05, 2, 24), "attack": (0.06, 2, 4), "dash": (0.012, 2, 4), "down": (0.01, 10, 40),
                  "bind": (0.0015, 2, 4)}
        m = self.BIT[self.move] if self.move else 0
        for k, (p, lo, hi) in starts.items():
            if self.timers[k] > 0:
                self.timers[k] -= 1
                m |= self.BIT[k]
                if self.timers[k] == 0:
                    self.rest[k] = 3
            elif self.rest[k] > 0:
                self.rest[k] -= 1
            elif r.random() < p:
                self.timers[k] = r.randint(lo, hi)
                m |= self.BIT[k]
        return m


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


@pytest.mark.parametrize("seed", [0, 1, 12345, 1_000_003 * 3 + 1_790_000_000])
def test_default_policy_draws_exactly_as_before(seed):
    old, new = OldPolicy(random.Random(seed)), S.Policy(random.Random(seed))
    keys, macros = S.ability_keys(None)
    via_modes = S.Policy(random.Random(seed), keys, macros)  # what the worker builds without --abilities
    for _ in range(30_000):
        m = old.step()
        assert new.step() == m
        assert via_modes.step() == m
    assert old.r.random() == new.r.random() == via_modes.r.random()


@pytest.mark.parametrize("mode", [None, *S.ABILITY_MODES])
def test_policy_never_presses_forbidden_keys(mode):
    _, masks, _ = run(mode, ALL_BINDINGS)
    seen = set().union(*(names_in(m) for m in masks))
    assert not seen & set(S.FORBIDDEN_KEYS)
    assert seen <= ALLOWED[mode]
    assert {"up", "pause", "inventory", "map", "quickmap", "journal", "quests"} <= set(S.FORBIDDEN_KEYS)


@pytest.mark.parametrize("mode", [None, *S.ABILITY_MODES])
def test_policy_key_coverage_per_mode(mode):
    p, masks, _ = run(mode, ALL_BINDINGS)
    seen = set().union(*(names_in(m) for m in masks))
    assert seen == ALLOWED[mode]
    longest = {k: max((n for _, n in key_runs(masks, S.BIT[k])), default=0) for k in ("dash", "jump", "attack")}
    movement, combat = mode in ("movement", "all"), mode in ("combat", "all")
    assert (longest["dash"] >= 16) == movement          # sprint holds
    assert (longest["jump"] >= 31) == movement          # double jump + glide holds
    assert (longest["attack"] >= 101) == combat         # Needle Strike charge
    assert (p.counts["silk_soar"] > 0) == movement
    assert (p.counts["down_cast"] > 0) == combat
    assert (p.counts["clawline"] > 0) == movement
    assert (p.counts["quickcast"] > 0) == combat


def test_quickcast_only_for_bound_directions():
    keys, macros = S.ability_keys("combat", {})
    assert "quickcast" not in keys and not macros          # nothing equipped that QuickCast could throw
    keys, macros = S.ability_keys("combat", {"neutral": None, "up": "Straight Pin", "down": None})
    assert "quickcast" not in keys and not macros          # Up-bound only: the soak never presses up
    keys, macros = S.ability_keys("all", {"neutral": None, "down": "Straight Pin"})
    assert "quickcast" not in keys and [m.name for m in macros] == ["silk_soar", "down_cast"]
    _, masks, macro_of = run("all", {"neutral": None, "down": "Straight Pin"})
    cast = [(m, mac) for m, mac in zip(masks, macro_of) if m & S.BIT["quickcast"]]
    assert cast and all(m & S.BIT["down"] and mac == "down_cast" for m, mac in cast)
    keys, macros = S.ability_keys("combat", {"neutral": "Silk Spear"})
    assert "quickcast" in keys and not macros
    with pytest.raises(ValueError):
        S.ability_keys("everything")


@pytest.mark.parametrize("mode", ["movement", "combat", "all"])
def test_clawline_and_quickcast_never_with_down_outside_macros(mode):
    _, masks, macro_of = run(mode, ALL_BINDINGS, frames=80_000, seed=7)
    down = S.BIT["down"]
    both = 0
    for m, mac in zip(masks, macro_of):
        if m & (S.BIT["clawline"] | S.BIT["quickcast"]) and m & down:
            both += 1
            assert mac in ("silk_soar", "down_cast")
            assert not m & (S.BIT["left"] | S.BIT["right"])  # Silk Soar needs only down (m0:N41)
        if mac is not None:
            assert not m & (S.BIT["left"] | S.BIT["right"])
    assert both > 0
    # a plain clawline press never starts with down held
    for start, _ in key_runs(masks, S.BIT["clawline"]):
        if macro_of[start] is None:
            assert not masks[start] & down


def test_macro_shapes():
    for mac, key in ((S.SILK_SOAR, "clawline"), (S.DOWN_CAST, "quickcast")):
        d, k = S.BIT["down"], S.BIT[key]
        assert mac.frames == (d, d, d | k, d | k, d | k, d)
        assert set(mac.keys) == {"down", key}
    p, masks, macro_of = run("movement", frames=60_000, seed=3)
    starts = [i for i in range(len(masks)) if macro_of[i] == "silk_soar" and (i == 0 or macro_of[i - 1] != "silk_soar")]
    assert starts and len(starts) == p.counts["silk_soar"]
    for i in starts:
        if i + 6 <= len(masks):
            assert tuple(masks[i:i + 6]) == S.SILK_SOAR.frames


@pytest.mark.parametrize("mode", [None, *S.ABILITY_MODES])
def test_every_press_and_release_lasts_two_frames(mode):
    """The oracle's HoldFilter would stretch shorter presses/releases (C19); the policy never needs it."""
    _, masks, _ = run(mode, ALL_BINDINGS, frames=60_000, seed=11)
    for key, bit in S.BIT.items():
        rs = [(a, n) for a, n in key_runs(masks, bit) if a + n < len(masks)]  # not the one cut off by the sample end
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


def test_parse_args_and_worker_command():
    a = S.parse_args(["--minutes", "5"])
    assert a.abilities is None and a.ability_tools is None and a.ability_skill is None
    cmd = S.worker_command(a, 2, S.RUNS / "x", 1_790_000_000.4)
    assert cmd == [sys.executable, "-m", "ssbot.tools.soak", "--worker", "2", "--out", str(S.RUNS / "x"),
                   "--deadline", "1790000000"]  # the default soak's worker command, unchanged
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


def state_frame(f: int, hero: dict) -> bytes:
    return encode(MsgType.STATE, f, msgpack.packb({"f": f, "hero": hero}))


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


class FakeLink:
    def __init__(self, state: dict, grant: dict, rpcs=("abilities.grant", "abilities.list"), suppress: bool = True):
        self.hello = {"rpcs": list(rpcs)}
        self.state = state
        self.frame = state.get("f", 0)
        self.closed = False
        self.calls: list[tuple[str, dict]] = []
        self.answers = {"schema.cstate": {"bools": ["facingRight", "onGround", "dashing"], "words": 1},
                        "guards.set": {"save_suppression": suppress}, "abilities.grant": grant}

    def rpc(self, name, /, timeout_s=10.0, **args):
        self.calls.append((name, args))
        return self.answers[name]

    def wait_state(self, pred=lambda s: True, timeout_s=10.0, newer_than=None):
        if pred(self.state):
            return self.state
        raise TimeoutError("fake: condition not met")


def worker(tmp_path, mode="all", instance=1, tools=None, skill=None) -> S.Worker:
    args = argparse.Namespace(worker=instance, out=str(tmp_path), deadline=1e12, abilities=mode, ability_tools=tools,
                              ability_skill=skill)
    return S.Worker(args)


def grant_reply(bindings, slots, requested, unplaced=()):
    return {"set": "all", "changed": ["hasDash (Swift Step)"], "unplaced": list(unplaced), "requested": requested,
            "bindings": bindings, "slots": slots, "sets": {"movement": True, "combat": True, "all": True}}


def log_lines(tmp_path, i=1):
    return [json.loads(x) for x in (tmp_path / f"worker_{i}.jsonl").read_text(encoding="utf-8").splitlines()]


def test_worker_grant_flow(tmp_path):
    w = worker(tmp_path, "all", 1)
    res = grant_reply({"neutral": "Thread Sphere", "up": None, "down": "Tri Pin"},
                      [{"tool": "Thread Sphere"}, {"tool": "Tri Pin"}], ["Thread Sphere", "Tri Pin"])
    w.link = FakeLink({"f": 50, "hero": {"can": {"dash": True, "harpoon": True, "super_jump": True},
                                         "tools": [None, "Tri Pin", "Thread Sphere"]}}, res)
    w.grant_abilities()
    w.log.close()
    assert [c[0] for c in w.link.calls] == ["schema.cstate", "guards.set", "abilities.grant"]
    assert w.link.calls[1][1] == {"save_suppression": True}
    assert w.link.calls[2][1] == {"set": "all", "skill": "Thread Sphere", "tools": ["Tri Pin"], "unlock_slots": True}
    rec = log_lines(tmp_path)[-1]
    assert rec["kind"] == "abilities" and rec["ok"] is True and rec["want_tools"] == ["Thread Sphere", "Tri Pin"]
    assert {"clawline", "quickcast"} <= set(rec["keys"]) and rec["macros"] == ["silk_soar", "down_cast"]
    assert w.stats.ability_bits == {"dashing": 2}
    assert "quickcast" in w.keys


def test_worker_grant_not_seen_in_state(tmp_path):
    w = worker(tmp_path, "movement", 1)
    res = grant_reply({"neutral": None, "up": None, "down": None}, [], [])
    w.link = FakeLink({"f": 9, "hero": {"can": {"dash": True, "harpoon": False, "super_jump": True}, "tools": []}}, res)
    w.grant_abilities()
    w.log.close()
    rec = log_lines(tmp_path)[-1]
    assert rec["ok"] is False and rec["gaps"] == ["can.harpoon"]
    assert "clawline" in w.keys and "quickcast" not in w.keys  # still plays the ability keys


def test_worker_grant_with_an_unplaced_tool_fails(tmp_path):
    w = worker(tmp_path, "combat", 0)
    res = grant_reply({"neutral": "Silk Spear", "up": None, "down": None}, [{"tool": "Silk Spear"}],
                      ["Silk Spear", "Straight Pin"], unplaced=["Straight Pin: no unlocked Red slot on Hunter ..."])
    w.link = FakeLink({"f": 3, "hero": {"can": {}, "tools": ["Silk Spear"]}}, res)
    w.grant_abilities()
    w.log.close()
    rec = log_lines(tmp_path, 0)[-1]
    assert rec["ok"] is False and rec["gaps"][0].startswith("unplaced: Straight Pin")
    assert rec["want_tools"] == ["Silk Spear"] and "quickcast" in w.keys and not w.macros


def test_worker_grant_refused_without_rpc_or_suppression(tmp_path):
    w = worker(tmp_path, "combat", 1)
    w.link = FakeLink({"f": 1, "hero": {}}, {}, rpcs=("ping",))
    w.grant_abilities()
    w.link = FakeLink({"f": 1, "hero": {}}, {}, suppress=False)
    w.grant_abilities()
    w.log.close()
    a, b = log_lines(tmp_path)[-2:]
    assert a["ok"] is False and "no abilities.grant" in a["error"]
    assert b["ok"] is False and "save suppression" in b["error"]
    assert "abilities.grant" not in [c[0] for c in w.link.calls]  # nothing granted without suppression
    assert "quickcast" not in w.keys  # no bindings known: no QuickCast
