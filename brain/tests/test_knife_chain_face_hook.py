"""Targeted face-hook finite cases (ported from Task169): aimed face hook inside the same rune_transfer Run.

Each case drives the real chain table / transfer.propose / native callbacks of this development tree. The hero model
pose is a fixed airborne S0 per tick (routing and gates only, not physics); nothing here is a hit or flight claim."""
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

import ssbot
from ssbot.combat.knife_chain_air import load_runner as _load_runner


def load_runner():
    r=_load_runner();r.chains["rune_transfer"].cfg["FACE_HOOK"]=True
    return r


@pytest.fixture(autouse=True)
def enable_face_hook(monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_FACE_HOOK","1")
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_transfer import TransferPlan, propose, retreat_reserve, face_hook_check
from ssbot.knowledge import kinematics as K
from ssbot.combat.air_chain import ChainSim

ROOT = Path(ssbot.__file__).resolve().parents[2]
PARAMS = K.hero2(K.HeroParams.load(ROOT / "knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"))
TERRAIN = K.Terrain2D.from_boxes([(-100., -10., 100., 3.015)])


def ent(iid, x, st, face=-1, t=.1, vx=0.):
    return {"iid": iid, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [x, 7.45], "vel": [vx, 0.], "flipX": face > 0,
            "fsms": [{"name": "Control", "state": st, "t": t}],
            "colliders": [{"name": "Song Heavy Sentry", "enabled": True,
                           "verts_world": [x - 1.8, 3.01, x + 1.8, 3.01, x + 1.8, 6.92, x - 1.8, 6.92]}]}


def scene(f=1000, gap=6., st="Idle", y=7.0, vy=0., prefix=0, accepting=True, harpoon=True, clip="Airborne",
          t_state=.1, vx=0.):
    hx = 25.
    s = {"f": f, "dt": 1 / 60,
         "hero": {"pos": [hx, y], "box": [hx - .25, y - 1.553, hx + .25, y + .532], "vel": [0., vy], "health": 7,
                  "hero_accepting_input": accepting, "silk": 3, "can": {"harpoon": harpoon},
                  "tm": {"dash_cd": 0.}, "anim": {"clip": clip}},
         "ents": [ent(7, 12., "Cast 2", face=1), ent(8, hx + gap, st, face=-1, t=t_state, vx=vx)],
         "act": {"target": f, "applied": f, "mask": prefix,
                 "hf": {"latched": prefix, "desired": prefix, "pending": [0] * 22, "age": [100] * 22}}, "ev": []}
    S = K.initial_state(PARAMS, hx, y, vy=vy, mode=K.M_NORMAL, ground=False)
    sim = ChainSim(S, np.array([prefix], np.int64), K.HoldState.from_act(s["act"]), PARAMS, TERRAIN, f, f)
    return s, sim


def plan():
    return TransferPlan(8, 7, 990, 1000, 990 / 60., B["R"], 10000, 10000, 10000, False, 1000, 0)


def runner_with(link, **v):
    r = load_runner()
    r.run = Run("rune_transfer", link, {**dict(r.chains["rune_transfer"].vars), **plan().variables(), **v})
    return r


def step(r, f, **kw):
    s, sim = scene(f=f, **kw)
    made = propose(r, s, f / 60., sim, 8, False, np.zeros((0, 6)), set())
    return made, s


def adopt(r, made):
    r.run = made[0].run       # as if this draft had been sent (the native promotes it only after a real send)
    return r


# ---- absolute plan, slots, links, prefix --------------------------------------------------------------------------

def test_face_hook_enters_claw_once_and_keeps_absolute_slots_across_ticks():
    r = runner_with("air")
    made, _ = step(r, 1000)
    assert made is not None and made[0] is not None
    cs = made[0].run.v["cs"]
    assert made[0].run.link == "claw" and cs.f_press == 1003 and made[3] == B["R"]          # turn key at F0 = 1002
    adopt(r, made)
    made, _ = step(r, 1001, prefix=B["R"])
    assert made[0].run.v["cs"] == cs and made[0].run.link == "claw" and made[3] == B["CLAW"] | B["R"]   # P
    adopt(r, made)
    made, _ = step(r, 1002, prefix=B["CLAW"] | B["R"])
    assert made[0].run.v["cs"] == cs and made[3] == B["CLAW"] | B["R"]                       # second hold P+1
    adopt(r, made)
    made, _ = step(r, 1003, prefix=B["CLAW"] | B["R"])
    assert made[0].run.link == "claw_lock" and made[3] == 0                                    # lock: no key
    assert not (made[3] & B["J"])


def test_claw_prefix_is_only_admitted_inside_hook_links():
    made, _ = step(runner_with("air"), 1000, prefix=B["CLAW"])
    assert made is None
    cs = __import__("ssbot.combat.claw_strike", fromlist=["CsPlan"]).CsPlan(1000, 0, 1001, 0)
    made, _ = step(runner_with("claw_lock", cs=cs, hook_seen_f=cs.f_press+2, hook_hit_f=cs.f_press+8), 1000, prefix=B["CLAW"])
    assert made is not None and made[0] is not None and made[0].run.link == "claw_lock"


def test_reproposal_never_resets_the_hook_plan_to_none():
    from ssbot.combat.claw_strike import CsPlan
    cs = CsPlan(990, 0, 991, 0)
    made, _ = step(runner_with("claw_lock", cs=cs, hook_seen_f=cs.f_press+2, hook_hit_f=cs.f_press+8), 1000)
    assert made[0].run.v["cs"] is cs


# ---- target motion, control, timeout ------------------------------------------------------------------------------

def test_locked_hook_is_not_reset_when_the_target_starts_an_ordinary_jump():
    from ssbot.combat.claw_strike import CsPlan
    cs = CsPlan(995, 0, 996, 0)
    made, _ = step(runner_with("claw_lock", cs=cs, hook_seen_f=cs.f_press+2, hook_hit_f=cs.f_press+8), 1000, st="Jump Antic")
    assert made is not None and made[0] is not None and made[0].run.link == "claw_lock" and made[3] == 0
    assert step(runner_with("air"), 1000, st="Jump Antic")[0] is None                          # fresh entry unchanged


@pytest.mark.parametrize("case", ["early", "not_accepting", "harpoon_clip", "control"])
def test_strike_rules_resume_only_after_actual_control(case):
    from ssbot.combat.claw_strike import CsPlan
    f_press = 1002 - (13 if case != "early" else 5)              # F = f + 2 = 1002 at f 1000: 13 or 5 frames after P
    cs = CsPlan(f_press - 1, 0, f_press, 0)
    made, _ = step(runner_with("claw_lock", cs=cs, hook_seen_f=cs.f_press+2, hook_hit_f=cs.f_press+8), 1000, accepting=case != "not_accepting",
                   clip="Harpoon Catch" if case == "harpoon_clip" else "Airborne")
    run = made[0].run if made is not None and made[0] is not None else None
    if case == "control":
        assert run is not None and run.v["hook_done"] and run.link in {"air", "strike"}
    else:
        assert run is not None and run.link == "claw_lock" and not run.v.get("hook_done")


def test_no_control_return_aborts_the_run_instead_of_guessing():
    from ssbot.combat.claw_strike import CsPlan
    cs = CsPlan(950, 0, 951, 0)
    made, _ = step(runner_with("claw_lock", cs=cs, hook_seen_f=cs.f_press+2, hook_hit_f=cs.f_press+8), 1000, accepting=False)
    assert made is not None and made[0] is None and "no control return" in (made[1].ended_reason or "")


def test_harpoon_hit_on_another_body_aborts_the_locked_hook():
    from ssbot.combat.claw_strike import CsPlan
    made, _ = step(runner_with("claw_lock", cs=CsPlan(995, 0, 996, 0), hook_other_f=[1001, 9]), 1000)
    assert made is not None and made[0] is None and "another body" in (made[1].ended_reason or "")


def test_air_j_is_not_pressed_again_after_the_hook():
    from ssbot.combat.claw_strike import CsPlan
    r = runner_with("claw_lock", cs=CsPlan(988, 0, 989, 0), hook_seen_f=991, hook_hit_f=997, jump_until=10 ** 6)   # a stale approach J window
    made, _ = step(r, 1000)                 # J not held now: the existing air rule closes the window
    run = made[0].run
    assert run.v["hook_done"] and run.link in {"air", "strike"} and not made[3] & B["J"]
    assert run.v["jump_until"] < 10 ** 6


def test_hook_done_never_rearms_a_second_hook_in_the_same_run():
    r = runner_with("air", hook_done=True)
    made, _ = step(r, 1000)
    assert made is None or made[0] is None or (made[0].run.link != "claw" and made[0].run.v.get("cs") is None)


# ---- cheap face check: retreat, reverse, height --------------------------------------------------------------------

def check(s, sim, toward=1, bombs=None):
    from ssbot.combat.knife_chain_air import body_box
    return face_hook_check(sim, s["hero"], s["ents"][1], 1002, toward, bombs,
                           [(e["iid"], body_box(e)) for e in s["ents"]])


def test_retreat_reserve_counts_only_the_time_to_the_ray_capped_by_the_remaining_scuttle():
    t = 12 / 60.
    assert retreat_reserve(ent(8, 30., "Idle"), t, 1) == pytest.approx(15. * t)            # may start one at once
    assert retreat_reserve(ent(8, 30., "Slam Antic"), t, 1) == pytest.approx(15. * t)      # no unverified exemption
    assert retreat_reserve(ent(8, 30., "Evade Scuttle", t=.2), t, 1) == pytest.approx(15. * t)
    assert retreat_reserve(ent(8, 30., "Evade Scuttle", t=.65), t, 1) == pytest.approx(15. * (44 / 60. - .65))
    assert retreat_reserve(ent(8, 30., "Evade Scuttle", t=.8), t, 1) == 0.
    assert retreat_reserve(ent(8, 30., "Evade Scuttle", t=.8, vx=20.), t, 1) == pytest.approx(20. * t)  # observed floor
    assert retreat_reserve(ent(8, 30., "Evade Scuttle", t=.8, vx=20.), t, -1) == 0.
    with pytest.raises(ValueError):
        retreat_reserve(ent(8, 30., "Idle"), float("nan"), 1)


@pytest.mark.parametrize("gap,st,t_state,toward,expect", [
    (9.25, "Idle", .1, 1, "ok"),
    (10.25, "Idle", .1, 1, "face out of the modeled ray after the retreat reserve"),
    (11.5, "Evade Scuttle", .7, 1, "ok"),                    # two frames of the double scuttle left: 0.5 u
    (11.5, "Evade Scuttle", .2, 1, "face out of the modeled ray after the retreat reserve"),
    (6., "Slam Antic", .1, 1, "target state outside the face-hook scope"),
    (6., "Idle", .1, -1, "target body behind the ray origin"),                      # reverse direction
    (13., "Idle", .1, 1, "B2 identity ray does not take the target first"),         # beyond the veto's 10.5 u at P
])
def test_face_check_retreat_reserve_and_direction_boundaries(gap, st, t_state, toward, expect):
    s, sim = scene(gap=gap, st=st, t_state=t_state)
    ok, why, info = check(s, sim, toward)
    assert why == expect and ok == (expect == "ok")
    if why.startswith("face out"):          # the retreat decides: the same face is in the modeled ray without it
        assert info["ray_margin"] < 0 < info["ray_margin"] + info["retreat_reserve"]


def test_face_height_band_follows_the_observed_body_top_and_the_floor_hover():
    for y, expect in ((5.7, "held height below claw_strike's floor hover"), (6.2, "ok"),
                      (8.1, "B2 identity ray does not take the target first")):
        s, sim = scene(gap=7., y=y)
        assert check(s, sim)[1] == expect, y
    s, sim = scene(gap=7., y=8.1)
    v = s["ents"][1]["colliders"][0]["verts_world"]
    v[5] = v[7] = v[5] + .5                                     # a taller observed body: the band follows it, no 6.4
    assert check(s, sim)[1] == "ok"


def test_hook_path_declines_a_lit_small_rune_and_keeps_one_lit_outside_its_frames_or_path():
    s, sim = scene(gap=7., y=7.0)
    assert check(s, sim)[1] == "ok"
    lit = np.array([[7., 28., 3.65, 2.166, 0., 60.]])        # under the path while she holds / dashes
    late = np.array([[7., 28., 3.65, 2.166, 80., 120.]])     # lit only after the latest control
    beyond = np.array([[7., 40., 3.65, 2.166, 0., 60.]])     # past the farthest stop
    assert check(s, sim, bombs=lit)[1] == "hook path meets a lit small rune"
    assert check(s, sim, bombs=late)[1] == "ok"
    assert check(s, sim, bombs=beyond)[1] == "ok"


def test_face_check_takes_every_observed_body_like_the_b2_identity_veto():
    s, sim = scene(gap=8.)
    assert check(s, sim)[1] == "ok"
    s["ents"].append(ent(9, 28.5, "Idle"))                   # another Clapper in front of the target
    assert check(s, sim)[1] == "B2 identity ray does not take the target first"
    s["ents"][2]["colliders"] = []                            # an unknown body: no guess
    assert check(s, sim)[1] == "observed body unknown"


# ---- native: watch arming and hook-only evidence -------------------------------------------------------------------

def native():
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="facehook169")
    n.reset(0, start_frame=1000)
    return n


def test_hook_watch_is_armed_only_by_a_successful_send_of_the_absolute_plan():
    from ssbot.combat.knife_chain_b2 import B2Offer
    from ssbot.combat.knife_chain_air import AirAnchor
    from ssbot.combat.claw_strike import CsPlan
    n = native(); s, _ = scene(st="Idle"); n.begin(s)
    p = plan(); r = load_runner()
    d0 = r.fork_empty(AirAnchor()); d0.run = Run("rune_transfer", "air", {**dict(r.chains["rune_transfer"].vars), **p.variables()})
    first = B2Offer("manual_commitment", None, d0, B["R"], 0., p.move, {"manual_air": True, "rune_transfer": True, "caster": 7, "cast_fa": 990})
    planner = NS(measurement_enabled=False, jump_until=1100, macro_until=1150)
    n.planner_result(n.install(first, planner)); n.final("plan", B["R"])
    n.before_send(frame=1000, target=1002, mask=B["R"], flags=0, received_frame=1000); n.sent()
    assert n.commitment["move"] == p.move and n._hook_start is None
    cs = CsPlan(1003, 0, 1004, 0)
    d1 = n.runner.fork_empty(AirAnchor()); d1.run = Run("rune_transfer", "claw", {**n.runner.run.v, "cs": cs})
    hook = B2Offer("active", None, d1, B["R"], 0., p.move, {"manual_air": True, "rune_transfer": True, "caster": 7, "cast_fa": 990})
    s1, _ = scene(f=1001); n.begin(s1)
    n.planner_result(n.install(hook, planner)); n.final("plan", B["R"])
    assert n._hook_start is None                                       # a draft / selection is not a send
    n.before_send(frame=1001, target=1003, mask=B["R"], flags=0, received_frame=1001); n.sent()
    assert n._hook_start is not None and n._hook_start["targets"] == (1004, 1005)
    assert n._hook_start["move"] == p.move and not n._hook_start["sent_targets"]
    # the CLAW at P: B2's own identity veto checks it and B2's sent() records it (stage "active"); no re-arm
    watch = n._hook_start
    s2, sim2 = scene(f=1002, prefix=B["R"]); n.begin(s2); n.prepare(s2, ground=False, accepting=True, sim=sim2)
    d2 = n.runner.fork_empty(AirAnchor()); d2.run = Run("rune_transfer", "claw", {**n.runner.run.v})
    claw = B2Offer("active", None, d2, B["CLAW"] | B["R"], 0., p.move, {"manual_air": True, "rune_transfer": True, "caster": 7, "cast_fa": 990})
    n.planner_result(n.install(claw, planner)); n.final("plan", B["CLAW"] | B["R"])
    assert n.before_send(frame=1002, target=1004, mask=B["CLAW"] | B["R"], flags=0, received_frame=1002) is None  # kept
    checked = [e for e in n.events if e["event"] == "b2_hook_target_checked"]
    assert len(checked) == 1 and checked[0]["first_target"] == 8 and not n.counts["b2_hook_target_veto"]
    n.sent()
    assert n._hook_start is watch and watch["sent_targets"] == {1004}


def test_missed_planned_claw_window_recovers_and_the_move_is_not_retried():
    n = native(); s, _ = scene(); n.begin(s)
    p = plan()
    from ssbot.combat.knife_chain_commitment import MoveInstance
    n.commitment = {"move": p.move, "origin": 1000, "ta": 0.}
    n._transfer_responsibility[p.move] = (MoveInstance(7, 990, "CC_CAST"), None)   # what _transfer_offer records
    n._hook_start = {"move": p.move, "origin": 1000, "targets": (1004, 1005), "sent_targets": set(), "seen_frame": None}
    assert n._check_hook_start(1004) is True
    assert p.move in n._failed_hook_moves and n.commitment is None


def test_hook_only_harpoon_hit_and_bounce_are_evidence_not_a_downslash_completion(monkeypatch):
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    from ssbot.combat.claw_strike import CsPlan
    n = native(); s, _ = scene(); n.begin(s)
    p = plan(); r = n.runner
    r.run = Run("rune_transfer", "claw_lock", {**dict(r.chains["rune_transfer"].vars), **p.variables(), "cs": CsPlan(990, 0, 991, 0)})
    n.commitment = {"move": p.move, "origin": 988, "ta": 0.}
    n._hook_start = {"move": p.move, "origin": 988, "targets": (991, 992), "sent_targets": {991}, "seen_frame": 993}
    # B2's own hook-bounce handover stays VAULT_IDLE-only: it must not fire for this transfer Move
    s2, _ = scene(f=1001, clip="Harpoon Catch", accepting=False)
    s2["ev"] = [{"k": "hit", "f": 1001, "d": {"src": "Harpoon Dash Damager", "ent": 8}}]
    s2["hero"]["cstate_int"] = [0, 3]
    assert n._observe_hook_bounce(s2) is None
    monkeypatch.setattr(NativeChainB2, "observe", lambda self, state: None)   # isolate the prototype's recorder
    n.observe(s2)
    v = n.runner.run.v
    assert v.get("hook_hit_f") == 1001 and not v.get("bounced") and "hook_ctrl_f" not in v
    assert n.post_context is None and n._hit is None and n._accepted is None
    assert n.runner.run.chain == "rune_transfer" and n.runner.run.link == "claw_lock"
    s3, _ = scene(f=1002); n.observe(s3)
    assert n.runner.run.v["hook_ctrl_f"] == 1002 and not n.runner.run.v.get("bounced")


@pytest.mark.parametrize("bad", [None, [], [float("nan"),0.], [True,0.]])
def test_unknown_target_velocity_cannot_license_a_face_hook(bad):
    s,sim=scene();s["ents"][1]["vel"]=bad
    assert check(s,sim)[0] is False


def test_face_hook_default_off_and_arm_a_does_not_activate(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_CHAIN_FACE_HOOK",raising=False)
    n=native();assert not n._face_hook_mode and not n.runner.chains[T.PROGRAM].cfg["FACE_HOOK"]
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_FACE_HOOK","1");n.arm="A";n.reset(1)
    assert not n._face_hook_mode


def test_invalid_face_hook_activation_value_is_rejected(monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_FACE_HOOK","maybe")
    with pytest.raises(ValueError,match="FACE_HOOK"):native()


@pytest.mark.parametrize("evidence", ["unseen", "no_hit"])
def test_control_without_seen_target_hook_cannot_release_to_strike(evidence):
    from ssbot.combat.claw_strike import CsPlan
    v={} if evidence=="unseen" else {"hook_seen_f":992}
    made,_=step(runner_with("claw_lock",cs=CsPlan(988,0,989,0),**v),1000)
    if evidence=="unseen":assert made[0].run.link=="claw_lock"
    else:assert made[0] is None and "without actual target" in made[1].ended_reason


def test_runtime_cannot_certify_free_flight_as_a_hooked_current_step(monkeypatch):
    from ssbot.combat.claw_strike import CsPlan
    n=native();s,sim=scene();n.begin(s)
    n._transfer_ready=True;n._context=(None,None,None,np.zeros((0,6)))
    n.queued_prefix=lambda f,state:(int(sim.prefix[0]),None)
    draft=load_runner();draft.run=Run(T.PROGRAM,"claw",{**dict(draft.chains[T.PROGRAM].vars),**plan().variables(),"cs":CsPlan(1002,0,1003,0)})
    monkeypatch.setattr(T,"propose",lambda *a,**kw:(draft,plan(),None,B["R"]))
    assert n._transfer_offer(s,1000/60.,sim,NS(),NS(target=8,entry_attack=None),False) is None
    assert n.commitment is None and n._hook_start is None
