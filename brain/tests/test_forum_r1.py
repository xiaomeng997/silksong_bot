"""Forum plan R1: wave starts, the wall climb, the targeted data policy v2, the audit's helpers (no game needed)."""
import random

from ssbot.ipc.framing import mask
from ssbot.tools.combat_run import config_fp
from ssbot.tools.forum_r1_audit import source_type
from ssbot.train.climb import TOP_Y, WallClimber
from ssbot.train.encounters import ENCOUNTERS, FORUM
from ssbot.train.forum_policy import BOUNDARIES_FALLBACK, ENVOY, ForumDataPolicyV2, load_boundaries
from ssbot.train.wave_start import WaveSkipPolicy, body_box, fighting, verify_wave_start

L, D, J, A = mask("left"), mask("dash"), mask("jump"), mask("attack")


def _box(x0, y0, x1, y1, eff=1, enabled=True, parryable=False):
    return {"kind": "box", "enabled": enabled, "verts_world": [x0, y0, x1, y0, x1, y1, x0, y1],
            "damage": {"eff": eff, "dealt": eff, "parryable": parryable} if eff is not None else None}


def _ent(iid, tk, x, y, cols=(), state="Idle", hp=50):
    return {"iid": iid, "type_key": tk, "pos": [x, y, 0], "src": 3, "hp": hp, "is_dead": False, "hidden": False,
            "fsms": [{"name": "Control", "state": state}], "colliders": list(cols)}


def _state(hx, hy, ents=(), cstate=(0, 0), dt=1 / 60, facing=1, battles=None, silk=0, hp=5):
    return {"f": 100, "dt": dt, "hero": {"pos": [hx, hy, 0], "facing": facing, "cstate": cstate, "silk": silk,
                                         "health": hp, "vel": [0.0, 0.0]},
            "ents": list(ents), "room": {"battles": battles or []}, "ev": []}


def test_body_box_prefers_hurting_colliders():
    e = _ent(1, "Song Heavy Sentry", 30, 7, cols=[_box(28, 3, 32, 7), _box(10, 0, 50, 2, eff=0)])
    assert body_box(e) == (28, 3, 32, 7)
    e2 = _ent(2, "X", 5, 5, cols=[_box(10, 0, 50, 2, eff=0)])
    assert body_box(e2) == (10, 0, 50, 2)
    assert body_box(_ent(3, "X", 5, 6)) == (5, 6, 5, 6)


def test_fighting_drops_parked_tinies():
    s = _state(30, 4.57, ents=[_ent(1, "Song Automaton Tiny", 20.5, 10.9, state="Dead"),
                               _ent(2, "Song Handmaiden", 40, 10, state="Fly")])
    assert [e["iid"] for e in fighting(s)] == [2]


def test_verify_wave_start_reports_new_members_and_helpers():
    b = [{"name": "Battle Scene", "wave": 3, "started": True, "completed": False, "enemies": 1, "to_next": 0}]
    s = _state(30, 4.57, ents=[_ent(1, "Song Handmaiden", 40, 10, state="Fly")], battles=b)
    s["allies"] = [{"name": "Garmond Fighter", "state": "Dormant", "active": True, "pos": [43.6, 7.5]}]
    v = verify_wave_start(s, FORUM, 3)
    assert v["wave"] == 3 and v["new_present"] and v["in_play"] == ["Song Handmaiden"]
    assert v["allies"][0]["state"] == "Dormant"


def test_wave_start_encounters():
    for i in range(14):
        e = ENCOUNTERS[f"Forum_A_w{i}"]
        assert e.savestate == f"fo_r1_w{i}" and e.waves == FORUM.waves and e.timebox_s == 180.0


def test_wave_skip_policy_slashes_in_reach_and_dashes_far():
    pol = WaveSkipPolicy({"Song Pilgrim 03"})
    near = _state(30, 4.57, ents=[_ent(1, "Song Pilgrim 03", 31.5, 4.6, cols=[_box(31, 3.5, 32, 6)])])
    assert pol.act(near) & A
    pol2 = WaveSkipPolicy({"Song Pilgrim 03"})
    far = _state(20, 4.57, ents=[_ent(1, "Song Pilgrim 03", 40, 4.6, cols=[_box(39.5, 3.5, 40.5, 6)])])
    m = pol2.act(far)
    assert m & mask("right") and not m & A


def _cs(**flags):
    from ssbot.tools.cstate import encode
    from ssbot.train import wave_start
    wave_start.hero_flags({"hero": {}})            # loads the schema
    return encode(flags, wave_start._CS_NAMES)


def test_wall_climber_jumps_then_scrambles_then_holds_at_top():
    from ssbot.train.wave_start import hero_flags
    c = WallClimber(random.Random(1))
    s = _state(15.5, 4.57, cstate=_cs(onGround=True))
    m = c.act(s, hero_flags(s))
    assert m & L and m & J and c.phase == "APPROACH"
    s = _state(14.27, 8.0, cstate=_cs(wallSliding=True, wallClinging=True))
    m = c.act(s, hero_flags(s))
    assert c.phase == "CLIMB" and m & L and m & D and c.scrambles == 1
    s = _state(14.27, TOP_Y + 0.2, cstate=_cs(wallSliding=True, wallClinging=True))
    for _ in range(20):
        m = c.act(s, hero_flags(s))
    assert c.phase == "TOP" and m & L and not m & D


def test_boundaries_fallback_and_loader(tmp_path):
    assert load_boundaries(tmp_path / "missing.json") is BOUNDARIES_FALLBACK
    p = tmp_path / "b.json"
    p.write_text('{"product": "boundaries", "Song Pilgrim 01/EN_SLASH": {"p99_u": 4.9, "boundary_u": 5.68}, '
                 '"Song Pilgrim Maestro/MA_SLASH": {"p99_u": 28.85, "boundary_u": 30.0}}', encoding="utf-8")
    b = load_boundaries(p)
    assert b == {"Song Pilgrim 01": {"EN_SLASH": (4.9, 5.68)}}


def _forced(pol, tactic, seconds=30.0):
    pol.tactic = tactic
    pol.left_s = seconds


def test_policy_v2_clash_swings_but_never_at_a_protected_envoy_below_its_hp_floor():
    charge = _box(30.2, 3.6, 31.0, 5.6, parryable=True)          # its Charge Damager (parry clash bit)
    for hp, want in ((15, 0), (38, 1)):
        pol = ForumDataPolicyV2(protect=(ENVOY,), focus=(ENVOY,))
        pol.reset(random.Random(3), FORUM)
        env = _ent(1, ENVOY, 31.0, 4.6, cols=[_box(30.5, 3.5, 31.5, 6), charge], state="Charge", hp=hp)
        swings = 0
        for k in range(120):
            if k == 0 or pol.left_s < 1.0:
                _forced(pol, "CLASH")
            s = _state(28.5, 4.57, ents=[env], cstate=_cs(onGround=True))
            swings += bool(pol.act(s, None) & (A | mask("quickcast") | mask("clawline")))
        assert (swings > 0) == bool(want), (hp, swings)


def test_policy_v2_dash_in_dashes_then_slashes():
    pol = ForumDataPolicyV2()
    pol.reset(random.Random(4), FORUM)
    tgt = _ent(1, "Song Pilgrim 03", 36.0, 4.6, cols=[_box(35.5, 3.5, 36.5, 6)], state="Battle Idle")
    keys = []
    for k in range(40):
        if k == 0:
            _forced(pol, "DASH_IN")
        keys.append(pol.act(_state(30.0, 4.57, ents=[tgt], cstate=_cs(onGround=True)), None))
    first_dash = next(i for i, m in enumerate(keys) if m & D)
    assert any(m & A for m in keys[first_dash:]) and pol.stats()["dash_ins"] >= 1


def test_policy_v2_runs_every_tactic_and_counts():
    pol = ForumDataPolicyV2()
    pol.reset(random.Random(5), FORUM)
    ents = [_ent(1, "Song Handmaiden", 33.0, 11.0, cols=[_box(32.5, 10, 33.5, 12, parryable=True)], state="Fly"),
            _ent(2, "Song Pilgrim 03", 36.0, 4.6, cols=[_box(35.5, 3.5, 36.5, 6)], state="Battle Idle")]
    for k in range(12000):
        pol.act(_state(30 + (k % 300) / 100.0, 4.57, ents=ents, cstate=_cs(onGround=True)), None)
    st = pol.stats()
    assert len(st["tactic_n"]) >= 8, st["tactic_n"]
    assert st["climb_n"] >= 1 and sum(st["tactic_s"].values()) > 199.0


def test_config_fp_keeps_old_hash_at_1x_and_marks_time_scale():
    base = config_fp("Forum_A_w3,Forum_A_w7", "data2", "data", "oracle", "abc")
    assert base == config_fp("Forum_A_w3,Forum_A_w7", "data2", "data", "oracle", "abc", {})
    assert base != config_fp("Forum_A_w3,Forum_A_w7", "data2", "data", "oracle", "abc", {"time_scale": "2.0"})


def test_audit_source_type():
    assert source_type("Wave 4/Song Handmaiden", set()) == "Song Handmaiden"
    assert source_type("Song Pilgrim 03 (3)/Whip Hit 2", set()) == "Song Pilgrim 03"
    assert source_type("Throwing Bell(Clone)", set()) == "Pilgrim 03 Song"
    assert source_type(None, set()) is None


def test_speed_check_statistics():
    import numpy as np

    from ssbot.tools.forum_speed_check import Arm, chi2_p, ks, ks_p, perm_tests, tv
    assert ks([1, 2, 3], [1, 2, 3]) == 0.0 and ks([0, 0], [1, 1]) == 1.0
    assert ks_p(0.0, 100, 100) == 1.0 and ks_p(0.5, 200, 200) < 1e-6
    assert chi2_p({"a": 50, "b": 50}, {"a": 50, "b": 50}) > 0.5
    assert chi2_p({"a": 90, "b": 10}, {"a": 10, "b": 90}) < 1e-6
    assert tv({"a": 1}, {"b": 1}) == 1.0
    rng = np.random.default_rng(0)

    def arm(shift):
        a = Arm()
        for _ in range(8):                       # 8 fights, each with its own offset (samples cluster by fight)
            one = Arm()
            off = rng.normal(0, 0.05)
            one.dwell[("T", "S")] = list(rng.normal(1.0 + shift + off, 0.1, 40))
            one.choice["T"]["F1"] = 20
            one.choice["T"]["F2"] = 20
            a.merge(one)
            a.per_fight.append(one)
        return a

    same = perm_tests(arm(0.0), arm(0.0), 10, n_perm=99)
    diff = perm_tests(arm(0.0), arm(0.5), 10, n_perm=99)
    assert diff["dwell"]["p_below_0.05"] == 1 and same["choices"]["keys"] == 1
