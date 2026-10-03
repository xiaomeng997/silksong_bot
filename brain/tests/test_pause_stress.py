"""Pause stress test pieces (ssbot.train.hit_injection, ssbot.tools.pause_stress): the injector waits for its kind of
moment and then asks hurt.special for a hit down to 1 HP, re-arms when the game did not take it, never injects while
the supervisor's pause machine owns the keys, and leaves the wrapped policy's interface intact; the trial summary
reads a synthetic recording (the hit, the closed gate, the pause, the menu keys, the main menu) the way the run's
recordings will be read."""
import random
from concurrent.futures import Future

from ssbot.ipc.framing import BUTTONS
from ssbot.tools import pause_stress as ps
from ssbot.train.hit_injection import HitInjector


class FakeLink:
    def __init__(self, take: bool = True):
        self.calls: list[dict] = []
        self.take = take

    def rpc_async(self, name, **args):
        self.calls.append({"name": name, **args})
        fut = Future()
        hp = args["amount"] + 1                       # the injector asks for HP - 1
        fut.set_result({"frame": 1000 + len(self.calls), "hp_before": hp,
                        "hp_after": hp - args["amount"] if self.take else hp, "take_health_calls": int(self.take)})
        return fut


class Inner:
    def __init__(self):
        self.pause_owned = False
        self.episode_outcome = None
        self.acts = 0

    def reset(self, rng, enc):
        rng.random()

    def act(self, s, tap=None):
        self.acts += 1
        return 7

    def stats(self):
        return {"view": "oracle"}


def _s(f: int, hp: int = 5, hs: int = 1, vy: float = 0.0, clip: str = "Idle", paused: bool = False) -> dict:
    return {"f": f, "game": {"paused": paused}, "hero": {"health": hp, "hero_state": hs, "vel": [0.0, vy],
                                                          "facing": 1, "anim": {"clip": clip}}}


def _injector(kind: str, take: bool = True) -> tuple[HitInjector, FakeLink]:
    inj = HitInjector(Inner(), p_event=0.0, min_s=1.0)
    link = FakeLink(take)
    inj.attach(link)
    inj.reset(random.Random(1), None)
    inj.kind = inj.log["kind"] = kind
    return inj, link


def test_injector_waits_for_its_moment_then_takes_the_hero_to_one_hp():
    inj, link = _injector("rising")
    assert inj.act(_s(0)) == 7 and inj.pause_owned is False          # the wrapped policy's mask and attributes
    for f in range(1, 59):
        inj.act(_s(f, hs=3, vy=5.0))
    assert not link.calls                                             # min_s: not before the fight is under way
    inj.act(_s(60, hs=3, vy=-4.0))                                    # falling: not this episode's kind
    assert not link.calls
    inj.act(_s(61, hp=4, hs=3, vy=4.0))
    assert link.calls == [{"name": "hurt.special", "kind": "damage", "amount": 3, "hazard": "ENEMY", "side": "left"}]
    for f in range(62, 200):
        inj.act(_s(f, hs=3, vy=4.0))
    st = inj.stats()
    assert len(link.calls) == 1 and st["view"] == "oracle" and st["inject"]["kind"] == "rising"
    assert st["inject"]["replies"][0]["hp_after"] == 1


def test_injector_rearms_when_the_game_does_not_take_the_hit_and_respects_an_owned_pause():
    inj, link = _injector("apex", take=False)
    for f in range(0, 400):
        inj.act(_s(f, hs=3, vy=0.5))
    assert len(link.calls) == 1 + inj.max_retries                     # i-frames: retried, then given up
    inj, link = _injector("apex")
    inj.inner.pause_owned = True
    for f in range(0, 200):
        inj.act(_s(f, hs=3, vy=0.5))
    assert not link.calls                                             # never into a pause under way
    inj.inner.pause_owned = False
    for f in range(200, 210):
        inj.act(_s(f, hp=1, hs=3, vy=0.5))
    assert not link.calls                                             # HP 1: nothing left to take down to 1


def test_bit_table_matches_the_framing_buttons():
    assert ps.KEYS == BUTTONS


def _rec(f, *, blk=0, paused=False, gs=4, latched=0, ev=(), q=None) -> dict:
    return {"f": f, "q": q if q is not None else f * 166_667, "ev": list(ev),
            "hero": {"hero_state": 3, "vel": [0.0, -3.0], "anim": {"clip": "Airborne"}, "cstate": None},
            "act": {"hf": {"latched": latched}}, "game": {"paused": paused, "gs": gs, "scene": "Bone_05"},
            "pause": {"blk": blk}, "ts": 1.0}


def test_trial_measures_latency_keys_unpauses_and_the_menu():
    P, ENTER, JUMP = ps.BIT["pause"], ps.BIT["enter"], ps.BIT["jump"]
    states = []
    for f in range(90, 400):
        if f < 100:
            states.append(_rec(f, latched=JUMP))
        elif f < 115:
            states.append(_rec(f, blk=3, ev=[{"k": "damage", "d": {"amount": 4}}] if f == 100 else ()))
        elif f < 117:
            states.append(_rec(f, latched=P if f == 116 else 0))
        elif f < 300:
            states.append(_rec(f, blk=64, paused=True, latched=P if f < 119 else ENTER if f in (200, 201) else 0))
        else:
            states.append(_rec(f, paused=True, gs=1))
    row = {"outcome": "QUIT", "reason": "QUIT: Q1", "policy": {
        "first_pending_f": 100, "inject": {"kind": "falling", "offset": 0, "sent": [{"f": 99}],
                                           "replies": [{"frame": 100, "hp_before": 5, "hp_after": 1,
                                                        "take_health_calls": 1}]},
        "real_quit": {"armed": True, "wrong_submits": 0, "unexpected_unpauses": 0}}}
    t = ps.trial(row, states, [])
    assert t["took"] and t["hit_f"] == 100 and t["airborne"] and t["first_pausable"] == 15 and t["paused"] == 17
    assert t["latency"] == 2 and t["pending"] == 0 and t["foreign_key_frames_paused"] == 0
    assert t["pause_key_frames_paused"] == 2 and t["unpauses"] == 0 and t["main_menu"]
    assert t["to_menu_frames"] == 300 - 117 and abs(t["to_menu_s"] - 183 * 0.0166667) < 1e-3
    # a jump latched while paused, and the world running again before the main menu: both counted
    states2 = [dict(s) for s in states]
    for s in states2:
        if 150 <= s["f"] < 152:
            s["act"] = {"hf": {"latched": JUMP}}
        if s["f"] == 160:
            s["game"] = {"paused": False, "gs": 4, "scene": "Bone_05"}
    assert t["foreign_edges_paused"] == 0 and t["last_foreign_edge"] is None
    t2 = ps.trial(row, states2, [])
    assert t2["foreign_key_frames_paused"] == 2 and t2["unpauses"] == 1
    assert t2["foreign_edges_paused"] == 1 and t2["last_foreign_edge"] == 150 - 117
    s = ps.summarize([t, t2])
    assert s["hits_taken"] == 2 and s["unintended_unpauses"] == 1 and s["foreign_keys_while_paused"] == 2
    assert s["latency_frames"]["max"] == 2 and s["main_menu"] == 2
