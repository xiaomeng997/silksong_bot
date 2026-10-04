"""Gauntlet tracking (ssbot.train.gauntlet) on synthetic STATEs: the oracle's TypeKey, the BattleScene DecrementEnemy
replay over the Forum's 14 waves (overlapping waves 2, 4 and 9), the battle start from wave 0's spawn, the end from the
kill replay, the battle-end freeze or room.battles, and the gauntlet data policy picking live enemies."""
import random

from ssbot.ipc.framing import mask
from ssbot.train.data_policy import POCKET_CLING_SHARE, GauntletDataPolicy
from ssbot.train.encounters import FORUM, FORUM_WAVES
from ssbot.train.gauntlet import CHECK_AFTER_F, GauntletTap, WaveSim, type_key


class _Link:
    def __init__(self):
        self.subs = []

    def subscribe_state(self, fn):
        self.subs.append(fn)

    def feed(self, s):
        for fn in self.subs:
            fn(s)


def _ev(k, **d):
    return {"k": k, "d": d}


def test_type_key_matches_the_oracle():
    assert type_key("Song Reed (1)") == "Song Reed"
    assert type_key("Pilgrim 03 Song (1)") == "Pilgrim 03 Song"
    assert type_key("Song Pilgrim 03") == "Song Pilgrim 03"
    assert type_key("Bullet(Clone) (2)") == "Bullet"
    assert type_key("Wave 2 - Call Ally") == "Wave 2 - Call Ally"
    assert type_key("(3)") == "(3)"


def _kill_all(sim: WaveSim, f0: int = 100, step: int = 10) -> list[int]:
    """Kill an enemy every `step` frames whenever one is alive (as in a fight: no kill before a wave's activation);
    returns the frames of the kills."""
    f = f0
    kills = []
    while not sim.done:
        f += step
        sim.advance(f)
        if sim.alive > 0:
            sim.kill(f)
            kills.append(f)
    return kills


def _run_to_wave(sim: WaveSim, i: int) -> int:
    """Kill the alive enemies every 200 frames until wave i activates; returns its activation frame."""
    f = 100
    while sim.wave < i:
        f += 1
        sim.advance(f)
        if sim.wave < i and sim.alive > 0 and f % 200 == 0:
            sim.kill(f)
    return dict(sim.starts)[i]


def test_wave_sim_runs_the_forum_waves_in_order():
    total = sum(len(w.enemies) for w in FORUM_WAVES)
    assert total == 28 and len(FORUM_WAVES) == 14
    sim = WaveSim(FORUM_WAVES)
    sim.start(100)
    kills = _kill_all(sim, step=200)
    assert sim.done and sim.end_frame == kills[-1]
    assert [i for i, _ in sim.starts] == list(range(14))
    assert [f for _, f in sim.starts] == sorted(f for _, f in sim.starts)
    assert len(kills) == total
    # wave index 2 (2 enemies, remainingEnemyToEnd 2) ends at its 1 s enemy check, not with its own start: index 3
    # (startDelay 0.5 s) activates 1.5 s after it when nobody dies in between (BattleScene.StartWave)
    st = dict(sim.starts)
    assert st[3] - st[2] == CHECK_AFTER_F + round(FORUM_WAVES[3].start_delay_s * 60)
    # a kill of an index-2 enemy before that check ends the wave at once (DecrementEnemy: 1 <= 2)
    sim2 = WaveSim(FORUM_WAVES)
    sim2.start(100)
    f2 = _run_to_wave(sim2, 2)
    sim2.kill(f2 + 10)
    sim2.advance(f2 + 200)
    assert dict(sim2.starts)[3] == f2 + 10 + round(FORUM_WAVES[3].start_delay_s * 60)
    # a second kill while index 3 is still in its startDelay does not start it twice
    sim3 = WaveSim(FORUM_WAVES)
    sim3.start(100)
    f2 = _run_to_wave(sim3, 2)
    sim3.kill(f2 + 10)
    sim3.kill(f2 + 12)
    sim3.advance(f2 + 300)
    assert [i for i, _ in sim3.starts].count(3) == 1 and sim3.alive == 1


def test_tap_start_waves_and_end_from_kills():
    link = _Link()
    tap = GauntletTap(link, FORUM)
    f = 1000
    link.feed({"f": f - 5, "ev": [_ev("fsm", obj="Song Reed", fsm="Control", to="Init", **{"from": None})]})
    assert tap.wake_frame is None     # a name a later wave reuses (wave 12's Song Reed runs from the load)
    link.feed({"f": f - 3, "ev": [_ev("fsm", obj="Song Pilgrim 01", fsm="Attack", to="Idle", **{"from": "Init"})]})
    assert tap.wake_frame is None     # not a start
    link.feed({"f": f, "ev": [_ev("fsm", obj="Song Pilgrim 01", fsm="Attack", to="Init", **{"from": None})]})
    assert tap.wake_frame == f and tap.wave == 0
    n = 0
    while tap.death_frame is None and f < 1000 + 200 * 60:
        f += 30
        if tap.sim.alive <= 0:
            link.feed({"f": f})            # waiting for the next wave's activation (startDelay, 1 s check)
            continue
        n += 1
        # the Maestro's summons die too (run 20261002_221727 i2 ep0): not wave members, no DecrementEnemy; a pooled
        # summon dies again under the same iid (run 20261002_231917 ep0)
        link.feed({"f": f, "ev": [_ev("hit", ent=-1 - n % 3, type_key="Song Automaton Tiny", dead=True, src="Slash",
                                      hp_before=4),
                                  _ev("hit", ent=n, type_key="Song Reed", dead=True, src="WildSlash Enemy Damager",
                                      hp_before=9)]})
    assert n == 28 and tap.death_frame == f and tap.end_source == "kills"
    summ = tap.summary()
    assert summ["wave_reached"] == 13 and summ["kills"]["n"] == 56
    assert summ["kills"]["by_src"] == {"WildSlash Enemy Damager": 28, "Slash": 28}
    waves = [w["f"] for w in summ["waves"]]
    assert [w["wave"] for w in summ["waves"]] == list(range(14)) and waves == sorted(waves)
    # the same death reported twice counts once; a hit on an enemy already at hp <= 0 is no new death
    link.feed({"f": f + 1, "ev": [_ev("hit", ent=n, type_key="Song Reed", dead=True, src="Slash", hp_before=3)]})
    link.feed({"f": f + 200, "ev": [_ev("hit", ent=n, type_key="Song Reed", dead=True, src="Slash", hp_before=-2)]})
    assert tap.summary()["kills"]["n"] == 56


def test_tap_prefers_room_battles_and_the_end_freeze():
    link = _Link()
    tap = GauntletTap(link, FORUM)
    b = {"name": "Battle Scene", "id": 5, "wave": 0, "waves": 14, "started": False, "completed": False,
         "enemies": 0, "to_next": 0}
    link.feed({"f": 10, "room": {"battles": [dict(b)]}})
    assert tap.wake_frame is None
    link.feed({"f": 20, "room": {"battles": [dict(b, started=True)]}})
    link.feed({"f": 30, "room": {"battles": [dict(b, started=True, wave=1)]},
               "ev": [_ev("hit", ent=1, type_key="Song Reed", dead=True, src="Slash")]})
    assert tap.wake_frame == 20 and tap.waves == [(0, 20), (1, 30)]
    link.feed({"f": 40, "room": {"battles": [dict(b, completed=True, wave=13)]}})
    assert tap.death_frame == 40 and tap.end_source == "room.battles"
    assert tap.summary()["wave_source"] == "room.battles"

    tap2 = GauntletTap(_Link(), FORUM)
    tap2._on({"f": 5, "ev": [_ev("fsm", obj="Song Pilgrim 01", fsm="Attack", to="Idle")]})
    tap2._on({"f": 9, "ev": [_ev("freeze", phase="start", type="EnemyBattleEndSlow")]})
    assert tap2.death_frame == 9 and tap2.end_source == "freeze"


def test_tap_counts_state_entries_and_allies():
    link = _Link()
    tap = GauntletTap(link, FORUM)
    link.feed({"f": 1, "ev": [_ev("fsm", obj="Song Pilgrim 03", fsm="Attack", to="Init")]})
    link.feed({"f": 2, "ev": [_ev("fsm", obj="Song Reed (1)", fsm="Control", to="Stab Antic")],
               "allies": [{"name": "Garmond Fighter", "active": True, "state": "Jump In"},
                          {"name": "Shakra Fighter", "active": True, "state": "Dormant"}]})
    assert tap.state_entries["Song Reed/Control/Stab Antic"] == 1
    assert tap.summary()["allies"] == {"Garmond Fighter": {"frames": 1, "first_t": round(1 / 60, 2)}}


def _state(enemies, hx=30.0):
    ents = [{"iid": i, "type_key": tk, "src": 1, "pos": [x, y, 0.0], "hp": 30, "is_dead": False, "fsms": []}
            for i, (tk, x, y) in enumerate(enemies)]
    return {"f": 1, "hero": {"pos": [hx, FORUM.floor_y, 0.0], "facing": 1, "health": 5, "silk": 0, "cstate": []},
            "ents": ents}


def test_waiting_enemies_are_not_in_play():
    from ssbot.train.gauntlet import live_enemies
    s = _state([("Song Pilgrim Maestro", 42.5, 10.9), ("Song Pilgrim 03", 40.0, 4.5), ("Song Reed", 35.0, 4.6)])
    s["ents"][0]["fsms"] = [{"name": "Control", "state": "Fly In Ready"}]
    s["ents"][1]["fsms"] = [{"name": "Attack", "state": None}]
    s["ents"][2]["fsms"] = [{"name": "Control", "state": "Stab Antic"}]
    assert [e["type_key"] for e in live_enemies(s)] == ["Song Reed"]


def test_parked_tinies_are_not_in_play():
    """The Maestros' pooled Tinies wait in "Dead" (R1 close-out): not in play; summoned (Fire Ready) they are."""
    from ssbot.train.gauntlet import WAITING_STATES, in_play, live_enemies
    assert "Dead" in WAITING_STATES and "Die" in WAITING_STATES
    s = _state([("Song Automaton Tiny", 20.5, 10.9), ("Song Automaton Tiny", 24.4, 10.9),
                ("Song Automaton Tiny", 30.0, 8.0), ("Song Heavy Sentry", 35.0, FORUM.floor_y)])
    s["ents"][0]["fsms"] = [{"name": "Control", "state": "Dead"}]
    s["ents"][1]["fsms"] = [{"name": "Control", "state": "Die"}]
    s["ents"][2]["fsms"] = [{"name": "Control", "state": "Fire Ready"}]
    s["ents"][3]["fsms"] = [{"name": "Control", "state": "Idle"}]
    assert [e["iid"] for e in live_enemies(s)] == [2, 3]
    assert not in_play(s["ents"][0]) and in_play(s["ents"][2])


def test_gauntlet_policy_ignores_parked_tinies():
    """v1 targets only enemies in play: a parked Tiny (nearer to the hero) is neither a target nor a non-Clapper that
    keeps the pocket test ("only Clappers left") off."""
    for seed in range(20):
        pol = GauntletDataPolicy()
        pol.reset(random.Random(seed), FORUM)
        s = _state([("Song Heavy Sentry", 45.0, FORUM.floor_y), ("Song Automaton Tiny", 24.4, 10.9)], hx=25.0)
        s["ents"][0]["fsms"] = [{"name": "Control", "state": "Idle"}]
        s["ents"][1]["fsms"] = [{"name": "Control", "state": "Dead"}]
        pol.mode_left = 0
        pol.act(s, None)
        assert pol.targets == {"Song Heavy Sentry": 1}


def test_gauntlet_policy_presses_toward_a_live_enemy_and_clings_left():
    pol = GauntletDataPolicy()
    pol.reset(random.Random(3), FORUM)
    pol.mode, pol.mode_left = "PRESS", 1000
    s = _state([("Song Reed", 40.0, FORUM.floor_y)])
    moves = [pol.act(s, None) & mask("left", "right") for _ in range(20)]
    assert all(m == mask("right") for m in moves)
    assert pol.stats()["targets"] == {"Song Reed": 20}
    # nobody alive: no chase; CLING walks to the left wall
    pol.mode, pol.mode_left, pol.wall = "CLING", 1000, -1
    moves = [pol.act(_state([]), None) & mask("left", "right") for _ in range(10)]
    assert all(m == mask("left") for m in moves)


def test_gauntlet_policy_takes_the_pocket_when_only_clappers_are_left():
    pol = GauntletDataPolicy()
    pol.reset(random.Random(5), FORUM)
    clappers = [("Song Heavy Sentry", 21.0, 7.45), ("Song Heavy Sentry", 42.0, 7.45)]
    picks = []
    for _ in range(400):
        pol.mode_left = 0
        pol.act(_state(clappers), None)
        picks.append((pol.mode, pol.wall))
    cling = [w for m, w in picks if m == "CLING"]
    assert 0.4 < len(cling) / len(picks) < 0.6 and cling.count(-1) > 0.9 * len(cling)
    # by frames CLING takes POCKET_CLING_SHARE (0.85), not the 0.5 of the picks
    pol.reset(random.Random(6), FORUM)
    pol.mode_left = 0
    for _ in range(60_000):
        pol.act(_state(clappers), None)
    fr = pol.stats()["mode_frames"]
    assert abs(fr["CLING"] / sum(fr.values()) - POCKET_CLING_SHARE) < 0.04
    pol.reset(random.Random(5), FORUM)
    # clinging at the top of the left wall: hold toward it, no wall jump
    pol.mode, pol.mode_left, pol.wall = "CLING", 10_000, -1
    pol._cstate = lambda s: {"wallClinging": True, "onGround": False}
    s = _state(clappers, hx=14.27)
    s["hero"]["pos"][1] = 13.5
    acts = [pol.act(s, None) for _ in range(300)]
    assert all(a & mask("left") for a in acts) and not any(a & mask("jump") for a in acts)
    assert pol.stats()["pocket_frames"] == 300
    # lower on the wall: it climbs with wall jumps
    s["hero"]["pos"][1] = 10.0
    acts = [pol.act(s, None) for _ in range(300)]
    assert any(a & mask("jump") for a in acts)
