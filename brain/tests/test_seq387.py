"""Task 182 seq 312 #387 (Sol seq 331: back's old half-plane circle gate against the shared ledger; Sol seq 333, the person 11-10: the
small rune's high hook opening; Sol seq 335: the opening first in the transfer air link, the hooked body's identity apart from the
caster through the B2 veto, the hook watch, the model anchor and the recovery). L2 through its real entry (tests/test_clapper_priority's
scene); the chain through transfer.propose on the face-hook test scenes (fixed airborne S0 per tick: routing and gates, no hit claim)."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_face_hook as FH, knife_chain_transfer as T
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.tactics import clapper_plans as CP, clapper_separated as SEP
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)
from tests.test_middle_return313 import near_attack
from tests.test_separated312 import start


@pytest.fixture(autouse=True)
def plans_on(monkeypatch):
    monkeypatch.setattr(CP, "ENABLED", True)


@pytest.mark.parametrize("ledger,offered", [(True, True), (False, False)])
def test_the_ledger_decides_the_return_the_old_half_plane_only_without_it(ledger, offered):
    # Sol seq 331 (PRE_REVIEW386_CIRCLE.json, moved inside the walls): 8 slams, she is outside; a live circle [10, 22] covers neither the
    # return's place (8's face side of the gap) nor the seam (24.5); an old jump-cast entry of 7 facing +1 marks the whole half-plane
    # in front of 16. With the shared ledger its spans decide (the return is offered); without it the old gate holds (as before)
    tac, ws, fc = start((16., 33.), 45.)
    tac.rune[7] = (16., 1., "test", ws.stamp.t_game_s + 30.)
    tac.rune_life = NS(live=lambda t: [NS(lo=10., hi=22.)]) if ledger else None
    near_attack(tac, ws, fc, iid=8)
    back = tac.last["clapper_back"]
    assert (back is not None) is offered
    if offered:
        assert back["move"] == [8, SEP.CC_SLAM] and not 10. - .5 < back["stance"] < 22. + .5 and back["seam"] > 22.5
        assert tac.last["clapper_winner"]["rule"] == "back"


def test_a_ledger_circle_over_the_place_still_holds_the_return():
    tac, ws, fc = start((16., 33.), 45.)
    tac.rune_life = NS(live=lambda t: [NS(lo=20., hi=35.)])                     # over the gap and 8's face side
    near_attack(tac, ws, fc, iid=8)
    assert tac.last["clapper_back"] is None and tac.last["clapper_winner"]["rule"] != "back"


# ---- seq 333: the "top" band (the usable band's upper edge) along a real held jump ----

def _jump_decisions(gap, band, last=30):
    """Each airborne decision of a held 24-frame jump toward an Idle body `gap` u away (early_jump's own construction: the state and
    the in-flight key at the decision, the recipe's key at F0 as the next press's)."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.holdfilter import hold_filter_jit
    from ssbot.combat.knife_chain_air import body_box, model_path
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_face_hook_step import MOVE, ground_scene
    r, s, sim = ground_scene(gap=gap, vel=0.)
    f = s["f"]
    keys = np.array([B["J"] | B["R"]] * 24 + [B["R"]] * 40, np.int64)
    path = model_path(sim, NS(origin=f, press_k=None, entry_k=0, contact_frame=None, iid=8, move=MOVE), keys, f / 60.)
    full = np.asarray(path.commands, np.int64)
    bodies = [(e["iid"], body_box(e)) for e in s["ents"]]
    out = []
    for d in range(1, last):
        if path.flags[d + 2] & K.F_GROUND:
            continue
        sd = ChainSim(np.asarray(path.states[:, d], float), full[d:d + 1].copy(), hold_filter_jit(full[None, :d], sim.hold)[1],
                      sim.params, sim.terrain, f + d, f + d)
        hd = {**s["hero"], "hero_accepting_input": not bool(path.flags[d] & K.F_NO_INPUT)}
        ok, why, info = T.face_hook_check(sd, hd, s["ents"][1], f + d + 2, 1, None, bodies, high_band=band, next_key=int(full[d + 1]))
        out.append((d, ok, why, info))
    return out


def test_the_top_band_hooks_at_the_last_rising_press_still_wholly_in_the_band():
    top, mid = _jump_decisions(9., "top"), _jump_decisions(9., True)
    first_top = next(r for r in top if r[1])
    first_mid = next(r for r in mid if r[1])
    assert first_mid[0] < first_top[0]                                     # the old high band: its middle, earlier and lower
    info = first_top[3]
    assert info["vy_press"] > 0 and info["held_high"] < info["band_hi"] <= info["next_held_high"]   # the next press leaves the band
    assert {why for d, ok, why, _ in top if d < first_top[0]} == {"high hook: a higher press in the band follows"}
    assert info["held_low"] > first_mid[3]["held_high"]


def test_the_top_band_falling_into_it_hooks_at_once():
    first = next(r for r in _jump_decisions(13., "top", last=48) if r[1])  # out of reach while rising: on the way down
    assert first[3]["vy_press"] < 0 and first[3]["held_high"] < first[3]["band_hi"]


# ---- seq 333 / 335: the opening in the transfer Run (the ray's first body; first in the air link) ----

def _opening_scene(caster_x, other_x, hx=25., y=7.0, vy=0., other_state="Idle", prefix=0):
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_face_hook import PARAMS, TERRAIN, ent, scene as fh_scene
    s, _ = fh_scene(y=y, vy=vy, prefix=prefix)
    s["hero"]["pos"][0] = hx
    s["hero"]["box"] = [hx - .25, y - 1.553, hx + .25, y + .532]
    s["ents"] = [ent(7, caster_x, "Cast 2", face=1), ent(8, other_x, other_state, face=-1)]
    S = K.initial_state(PARAMS, hx, y, vy=vy, mode=K.M_NORMAL, ground=False)
    return s, ChainSim(S, np.array([prefix], np.int64), K.HoldState.from_act(s["act"]), PARAMS, TERRAIN, s["f"], s["f"])


def _caster_run(**v):
    from ssbot.combat.knife_chain_air import load_runner
    from ssbot.combat.knife_chain_eval import Run
    r = load_runner()
    assert r.chains["rune_transfer"].cfg["FACE_HOOK"] is False                # the scene's own hook: no global face hook
    p = T.TransferPlan(7, 7, 990, 1000, 990 / 60., B["L"], 10000, 10000, 0, False, 1000, 0)
    r.run = Run("rune_transfer", "air", {**dict(r.chains["rune_transfer"].vars), **p.variables(), **v})
    return r


@pytest.mark.parametrize("other_x,hooked", [(20.5, 8), (31., 7)])
def test_the_opening_hooks_the_rays_first_body_and_keeps_the_caster_the_runs_target(other_x, hooked):
    # N standing in front of her toward the caster (not evading): the hook takes N; N gone behind her (it evaded): the still caster
    from ssbot.combat.knife_chain_air import body_box
    s, sim = _opening_scene(17., other_x)
    ok, why, info = T.face_hook_check_any(sim, s["hero"], s["ents"], 1002, -1)
    assert ok and info["hooked_iid"] == hooked, why
    made = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    v = made[0].run.v
    assert made[0].run.link == "claw" and v["hooked_iid"] == hooked and v["hook_press"]["iid"] == hooked
    assert v["iid"] == 7 and v["caster"] == 7 and made[1].move.target_iid == 7       # the Move and its target: the caster's
    no = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set())
    assert no[0].run.link == "air" and no[0].run.v.get("cs") is None              # without the opening: no hook on the caster
    if hooked == 7:   # the caster in its cast: no face hook of its own outside the opening
        bodies = [(e["iid"], body_box(e)) for e in s["ents"]]
        assert T.face_hook_check(sim, s["hero"], s["ents"][0], 1002, -1, None, bodies)[1] == "target state outside the face-hook scope"


def test_no_down_slash_row_before_the_openings_hook(monkeypatch):
    # Sol seq 335: the air link's stomp row comes before its face hook in the table; the opening goes first
    row = {"F0": 1002, "masks": [B["D"] | B["A"]] * 12, "press_F": 1003, "contact_frame": 1008, "support": "still"}
    monkeypatch.setattr(T, "contact_body_witness", lambda *a, **k: np.array([15.2, 3.01, 18.8, 6.92]))
    monkeypatch.setattr(T, "press_now_row", lambda *a, **k: dict(row))
    s, sim = _opening_scene(12., 31.)                                          # the caster out of the hook's reach: no hook now
    plain = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set())
    assert plain[0].run.link == "strike"
    opening = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    assert opening[0].run.link == "air" and opening[0].run.v.get("row") is None
    assert opening[0].run.v["face_hook_check"]["why"] == "no body on the hook ray"
    done = T.propose(_caster_run(hook_done=True, hooked_iid=8), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    assert done[0].run.link == "strike"                                        # after the real hook: the Run's own down slash


def test_an_opening_lost_to_a_face_too_near_hands_the_run_its_down_slash(monkeypatch):
    # the caster right beside her: no hook can be pressed (its face inside the press minimum); the opening is lost for this Run and its
    # ordinary down slash takes over on the next tick (no useless jump past a caster she can strike). (Pinned to B13 off: the old Run;
    # B13's body guard over a pending opening: tests/test_b13_guard.py)
    monkeypatch.setattr(T, "B13", False)
    row = {"F0": 1002, "masks": [B["D"] | B["A"]] * 12, "press_F": 1003, "contact_frame": 1008, "support": "still"}
    monkeypatch.setattr(T, "contact_body_witness", lambda *a, **k: np.array([21.2, 3.01, 24.8, 6.92]))
    monkeypatch.setattr(T, "press_now_row", lambda *a, **k: dict(row))
    s, sim = _opening_scene(23., 31.)
    r = _caster_run()
    first = T.propose(r, s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    v = first[0].run.v
    assert first[0].run.link == "air" and v["opening_lost"] == "face inside claw_strike's 0.5 u press minimum"
    assert not T.opening_pending(v)
    r.run = first[0].run                                                       # as if sent
    again = T.propose(r, s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    assert again[0].run.link == "strike"


def test_the_air_dash_waits_for_the_openings_hook_and_is_the_casters_after_it():
    s, sim = _opening_scene(15., 31., hx=26., y=9.)                           # far from the caster, no body on her ray now
    pending = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    assert not pending[3] & B["DASH"]
    before = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set())
    assert not before[3] & B["DASH"]                                           # the caster target's old exclusion
    after = T.propose(_caster_run(hook_done=True, hooked_iid=8), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set())
    assert after[3] & B["DASH"] and after[0].run.v["approach_recipe"] == "air_dash"


def test_a_fresh_opening_starts_on_the_caster_from_the_observed_cast():
    from ssbot.combat.knife_chain_air import load_runner
    s, sim = _opening_scene(17., 20.5)
    goal = T.TransferGoal(8, 7, 990)                                           # observe_goal's: the other one its destination
    r = load_runner()
    made = T.propose(r, s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), goal, hook_open=True)
    assert made[0].run.link == "claw" and made[0].run.v["iid"] == 7 and made[0].run.v["caster"] == 7
    assert made[1].cast_fa == 990 and made[0].run.v["hooked_iid"] == 8
    assert T.propose(load_runner(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), goal) is None
    assert T.propose(load_runner(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), {(7, 990, "opening")}, goal, hook_open=True) is None


# ---- Sol seq 334: a package entry / the opening start from the planner's own umbrella (a local release) ----

@pytest.mark.parametrize("prefs,released", [
    (NS(target=8), False),                                                     # an ordinary transfer: deferred as before
    (NS(target=8, entry_attack=NS(scope="rune_end", target=8, kind="stomp")), True),
    (NS(target=8, entry_attack=NS(scope="seam_slam", target=8, kind="stomp")), True),
    (NS(target=8, hook_open=(8, 990)), True),                                  # the small rune's opening on this Run's target
])
def test_the_umbrella_is_released_only_for_the_packages_entries_and_the_opening(monkeypatch, prefs, released):
    from ssbot.combat import knife_chain_air_native as N
    from ssbot.knowledge import kinematics as K
    from tests.test_dash_lock179 import FC, chain
    from tests.test_shared_strike_approach import flight
    r, s, sim = flight(); r.run = None; n = chain(monkeypatch, r)
    np.asarray(sim.start).reshape(K.K, -1)[K.MODE] = K.M_GLIDE
    called = []
    monkeypatch.setattr(N.transfer, "propose", lambda *a, **kw: called.append(kw) or None)
    assert n._transfer_offer(s, 0., sim, FC, prefs, False) is None
    events = {e["event"]: e for e in n.events}
    if released:
        # (the note marks a Run made in the umbrella; nothing is made here: no note, the release is the sent key)
        assert called and "rune_transfer_start_deferred" not in events and "rune_transfer_glide_release" not in events
        assert bool(called[0].get("hook_open")) == hasattr(prefs, "hook_open")
    else:
        assert not called and events["rune_transfer_start_deferred"]["mode"] == K.M_GLIDE
    np.asarray(sim.start).reshape(K.K, -1)[K.MODE] = K.M_DASH                   # a dash stays locked for every one of them
    called.clear(); n.events.clear()
    assert n._transfer_offer(s, 0., sim, FC, prefs, False) is None
    assert not called and any(e["event"] == "rune_transfer_start_deferred" for e in n.events)


def test_the_opening_is_the_runes_start_not_a_running_bounce_on_the_caster(monkeypatch):
    # e387_J30 102672: the rune began while a bounce follow-up off the caster ran (its own down slash on the caster followed): that Run
    # is no opening; a Run begun from the observed cast is, and keeps being one
    from ssbot.combat.knife_chain_eval import Run
    from tests.test_dash_lock179 import chain
    from tests.test_shared_strike_approach import flight
    r, s, sim = flight(); r.run = None; n = chain(monkeypatch, r)
    prefs = NS(target=8, hook_open=(8, 990))
    n._transfer_goal = T.TransferGoal(8, 7, 990, 0.)                           # the observed cast
    assert n._opening(prefs, 1000) and not n._opening(NS(target=8, hook_open=(7, 990)), 1000)
    n._transfer_goal = T.TransferGoal(8, 8, 990, 0., "BOUNCE")                 # a bounce off it: no fresh opening
    assert not n._opening(prefs, 1000)
    r.run = Run("rune_transfer", "air", {"iid": 8, "opening_run": True})
    assert n._opening(prefs, 1000)
    r.run = Run("rune_transfer", "air", {"iid": 8})
    assert not n._opening(prefs, 1000)
    from ssbot.combat.knife_chain_air import load_runner
    s2, sim2 = _opening_scene(17., 20.5)
    made = T.propose(_caster_run(), s2, 1000 / 60., sim2, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    assert not made[0].run.v.get("opening_run")                               # an active Run keeps its own mark (none here)
    fresh = T.propose(load_runner(), s2, 1000 / 60., sim2, 7, False, np.zeros((0, 6)), set(), T.TransferGoal(8, 7, 990), hook_open=True)
    assert fresh[0].run.v["opening_run"] is True


def test_the_caster_is_the_one_casting_not_an_earlier_runes_bomb_owner(monkeypatch):
    # Sol seq 338 / ep46 (DUAL_CAST_FACT_CHECK): 132 cast 147799-147873 and was Idle from 147874 with its bombs out; 126 began its Spell
    # Antic at 147884 (never two casting at once: Cast 2 frees the buddy lock). g387_C46 flipped between the two
    from ssbot.combat.tactics import gauntlet as G
    from tests.test_separated312 import cast, tick
    tac, ws, fc = start((20., 30.), 25.)
    out = cast(tac, ws, fc, 8)                                                 # the first cast
    f8 = ws.stamp.frame
    assert out.target == 8 and out.hook_open == (8, f8)
    change(fc, 8, family=G.CC_IDLE, state="Idle", committed=False)            # its cast over, its bombs still out
    monkeypatch.setattr(SEP, "rune_on", lambda sc, bombs: (True, {8}))
    out = tick(tac, ws, fc)
    # (Sol seq 339: the rune stage lasts while its bombs do: 2.2 goes on, the bombs' owner its down slash target, no new opening)
    assert tac.last["clapper_rune_down"]["case"] == "2.2 bombs" and tac.last["clapper_winner"]["rule"] == "rune_down"
    assert out.target == 8 and out.hook_open is None
    monkeypatch.setattr(SEP, "rune_on", lambda sc, bombs: (True, {7, 8}))
    out = cast(tac, ws, fc, 7)                                                 # the next cast while 8's bombs are out
    assert tac.last["clapper_rune_down"]["case"] == "2.2 hook" and out.target == 7 and out.hook_open == (7, ws.stamp.frame)
    out = tick(tac, ws, fc)
    assert out.target == 7 and out.hook_open[0] == 7


def test_the_opening_has_its_own_once_per_cast_key():
    # g387_C40 130618-130623: a plain transfer to the other one began on the cast before 2.2 took the scene; the opening still starts
    from ssbot.combat.knife_chain_air import load_runner
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain
    s, sim = _opening_scene(17., 20.5)
    goal = T.TransferGoal(8, 7, 990)
    plain = NativeManualAirChain._finished_key({"caster": 7, "cast_fa": 990})
    opening = NativeManualAirChain._finished_key({"caster": 7, "cast_fa": 990, "opening": True})
    assert plain == (7, 990) and opening == (7, 990, "opening")
    assert T.propose(load_runner(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), {plain}, goal, hook_open=True) is not None
    assert T.propose(load_runner(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), {opening}, goal, hook_open=True) is None


def test_the_caster_target_holds_the_side_key_back_while_it_would_carry_her_into_the_taller_body(monkeypatch):
    # g387_X14 54855: after a real bounce off the caster, the air link's side key carried her into its body corner (top 7.78 in the cast)
    # (B13 off: with it the body guard releases the side key itself: tests/test_b13_guard.py)
    monkeypatch.setattr(T, "B13", False)
    from ssbot.combat import knife_chain_air_native as N
    from ssbot.knowledge import kinematics as K
    from tests.test_dash_lock179 import FC, chain, geometry
    from tests.test_shared_strike_approach import flight
    def offer(state):
        r, s, sim = flight(x=27., y=8.4, vy=6., target_x=29.6)
        n = chain(monkeypatch, r); geometry(monkeypatch)
        e = next(x for x in s["ents"] if x["iid"] == 8)
        x0 = float(e["pos"][0])
        e["fsms"] = [{"name": "Control", "state": state, "t": .2}]
        e["colliders"] = [{"name": "Song Heavy Sentry", "enabled": True,
                           "verts_world": [x0 - 1.8, 3.015, x0 + 1.8, 3.015, x0 + 1.8, 9.5, x0 - 1.8, 9.5]}]   # a body she would fly into
        n._transfer_offer(s, 0., sim, FC, NS(target=8), False)
        return [ev for ev in n.events if ev["event"] == "transfer_side_held_back"]
    held = offer("Cast 1")
    assert held and held[0]["casting"] is True
    assert not offer("Idle")                                                   # (an Idle target: the approach as before)


# ---- the person 11-10: too near to hook -> jump; the rising side down slash, the jump held; evaded -> rising on to the hook ----

def _ground_opening(hx, n_state="Idle"):
    """J30 102672's layout (probe387_hookN.py): F casting at 32.4, N at 40.12 between her and F, she standing at hx."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_face_hook_step import PARAMS, TERRAIN, act, ent
    f = 1000
    s = {"f": f, "dt": 1 / 60,
         "hero": {"pos": [hx, 4.5677], "box": [hx - .25, 3.015, hx + .25, 5.0939], "vel": [0., 0.], "health": 7,
                  "hero_accepting_input": True, "silk": 3, "can": {"harpoon": True}, "tm": {"dash_cd": .0}, "anim": {"clip": "Idle"}},
         "ents": [ent(7, 32.4, "Cast 2", face=1), ent(8, 40.12, n_state, face=1)], "act": act(f, 0), "ev": []}
    S = K.initial_state(PARAMS, hx, 4.5677, vx=0., mode=K.M_NORMAL, ground=True)
    return s, ChainSim(S, np.array([0], np.int64), K.HoldState.from_act(s["act"]), PARAMS, TERRAIN, f, f)


@pytest.mark.parametrize("hx,ok,near", [(43., False, True), (45., False, True), (46., True, None), (48., False, False)])
def test_the_early_jump_tells_too_near_from_short_of_reach(hx, ok, near):
    from ssbot.combat.knife_chain_air import load_runner
    s, sim = _ground_opening(hx)
    p = T.TransferPlan(7, 7, 990, 990, 990 / 60., B["L"], 10000, 10000, 10000, False, 1000, 10)
    e = FH.early_jump(load_runner(), p, sim, 1000 / 60., s, s["ents"][0], np.zeros((0, 6)), 10, "walk", False, high_band="top",
                      any_body=True)
    assert bool(e["ok"]) is ok and e.get("near") is near
    assert e.get("hooked_iid") == (8 if ok else None)


def test_too_near_on_the_ground_jumps_at_once_and_a_reachable_one_waits_for_its_early_jump():
    from ssbot.combat.knife_chain_air import load_runner
    goal = T.TransferGoal(8, 7, 990)
    s, sim = _ground_opening(43.)
    made = T.propose(load_runner(), s, 1000 / 60., sim, 7, True, np.zeros((0, 6)), set(), goal, hook_open=True)
    assert made[0].run.v["early_hook"]["near"] and made[1].jump_k == made[1].entry_k + 2 and made[3] & B["J"]
    s, sim = _ground_opening(46.)
    made = T.propose(load_runner(), s, 1000 / 60., sim, 7, True, np.zeros((0, 6)), set(), goal, hook_open=True)
    assert made[0].run.v["early_hook"]["ok"] and not made[3] & (B["J"] | B["DASH"])   # the jump on the next tick, no dash meanwhile


@pytest.mark.parametrize("vy,armed", [(6., True), (-3., False)])
def test_a_too_near_hook_arms_the_rising_side_slash_only_while_rising(vy, armed):
    s, sim = _opening_scene(23., 31., vy=vy)                                  # the caster's face inside the press minimum
    made = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    v = made[0].run.v
    assert v["face_hook_check"]["why"] in T.OPENING_LOST
    assert (v.get("opening_slash") == 7) is armed and bool(v.get("opening_lost")) is (not armed)


def test_the_rising_side_slash_strikes_that_body_and_a_miss_goes_on_rising_to_the_hook(monkeypatch):
    seen, lefts = [], []
    row = {"F0": 1002, "masks": [B["D"] | B["A"]] * 12, "press_F": 1003, "contact_frame": 1008, "support": "still"}
    monkeypatch.setattr(T, "contact_body_witness", lambda e, *a, **k: seen.append(e["iid"]) or np.array([18.4, 3.01, 22.0, 6.92]))
    monkeypatch.setattr(T, "press_now_row", lambda *a, **k: lefts.append(a[3]) or dict(row))
    s, sim = _opening_scene(17., 20.2, vy=6.)                                  # N (8) in front of her, the caster F (7) behind it
    r = _caster_run(opening_slash=8, jump_until=1060)
    made = T.propose(r, s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    assert made[0].run.link == "strike" and made[0].run.v["slash_iid"] == 8 and seen == [8]
    assert lefts == [0]   # (the row's own jump hold: the remaining hold, none in this scene; a held jump keeps J through the row)
    r.run = made[0].run
    from ssbot.combat.air_chain import ChainSim
    s2, sim2 = _opening_scene(17., 20.2, vy=2.)
    s2["f"] = 1016                                                             # past press_F + miss_after: no hit (it evaded)
    sim2 = ChainSim(sim2.start, sim2.prefix, sim2.hold, sim2.params, sim2.terrain, 1016, 1016)
    s2["act"].update(target=1016, applied=1016)
    later = T.propose(r, s2, 1016 / 60., sim2, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    v = later[0].run.v
    assert later[0].run.link in ("air", "claw") and v["opening_slash_done"] and v.get("slash_iid") is None and not v.get("opening_lost")


def test_hooking_n_in_front_of_the_still_caster_takes_the_caster_as_the_other_branch():
    # the person: "不管走路那只是否闪身肯定能钩到一只": N close in front of F (its worst-case retreat by the needle's latest hit, 3.5 u,
    # reaches F's near face): the needle may meet F instead, F's body the hooked one in that branch. N's own retreat bound is not cut
    # at F's face (Sol seq 341: a hooked N may go on retreating after the hit, carrying her dash toward F)
    s, sim = _opening_scene(14., 17.2)                                         # F casting at 14 (face 15.8), N Idle at 17.2 (face 19.0)
    made = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    v = made[0].run.v
    assert made[0].run.link == "claw" and v["hooked_iid"] == 8 and v["hook_alt"] == 7
    assert max(v["hook_press"]["reserve"]) > 19.0 - 15.8 + 5.                 # its whole retreat bound, past F's near face
    assert FH.hook_alt(v) == 7 and FH.hook_alt({"hook_alt": None}) is None
    alt = v["hook_press"]["alt"]                                               # the other branch: F itself, still, through its cast
    assert alt["iid"] == 7 and alt["body"][2] == pytest.approx(15.8) and alt["move_until"] == v["cast_fa"] + T.HOOK_CAST_SPAN_F


def test_n_that_cannot_leave_the_ray_before_the_needle_is_the_needles_only_body():
    # Sol seq 341 (k387_hookN / hookNstay, J30 102684: N's face 6.7 u in front of F's, its worst-case retreat by the needle's latest
    # hit 3.5 u): the needle meets N in every case, so there is no F branch (whose track assumed N off the ray while its scan met N)
    from ssbot.map2 import strike as SK
    s, sim = _opening_scene(14., 20.5)                                         # N's face 22.3, F's 15.8: 6.5 u
    made = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    v = made[0].run.v
    assert made[0].run.link == "claw" and v["hooked_iid"] == 8 and v["hook_alt"] is None and "alt" not in v["hook_press"]
    n = s["ents"][1]
    t = (1002 + T.HOOK_PRESS_AFTER_F + T.HOOK_LATE_F + SK.HOOK_THROW_F - 1000) / 60.
    assert T.retreat_reserve(n, t, -1) < 22.3 - 15.8 < T.retreat_reserve(n, 1., -1)   # out of reach by the hit, not by the dash's end
    assert not T.needle_passes(sim, n, 1002, -1, 22.3 - 15.8) and T.needle_passes(sim, n, 1002, -1, 19.0 - 15.8)
    entry = FH._entry(NS(origin=1000, box=np.asarray(sim.roll(np.full((1, 3), B["L"], np.int64)).box[0, sim.off:sim.off + 3], float),
                         assumptions={}), v, 1000)
    assert {ex for _, _, _, ex in entry} == {(8, None)}                       # one branch: N's body its only exemption


def test_the_openings_hook_counts_only_what_is_up_there_with_her():
    # the person 11-10: "小符文天上什么都没有，只要高度够，晚一秒都没有危险。你就跳到高度出钩，一定钩的到，弹到最高点交给踩头代码接管就好"
    from ssbot.combat.knife_chain_commitment import ContactScan, PathContact
    v = {"hook_open": (7, 990), "caster": 7, "cast_fa": 990}
    assert not FH.opening_counts(PathContact(1010, 8, "body"), v)             # N's body: hooked, or the walk growth at her
    assert not FH.opening_counts(PathContact(1010, 7, "body"), v)
    assert not FH.opening_counts(PathContact(1010, 7, "move"), v)             # the caster's cast body (its "move" label)
    assert FH.opening_counts(PathContact(990 + T.HOOK_CAST_SPAN_F + 1, 7, "move"), v)   # an attack after its cast
    assert FH.opening_counts(PathContact(1010, 8, "move"), v)                 # N's attack
    assert FH.opening_counts(PathContact(1010, 7, "delayed"), v)              # the bombs, a big rune
    assert FH.opening_counts(PathContact(1010, 8, "body"), {})                # any other hook: every contact as before

    class Geo:                                                                 # each path meets those of three contacts it covers
        def scan_batch(self, paths):
            cs = (PathContact(1012, 8, "body"), PathContact(1013, 7, "move"), PathContact(1030, 7, "delayed"))
            return [ContactScan("p", q.origin, q.through, tuple(c for c in cs if q.origin <= c.frame <= q.through), "stub", True)
                    for q in paths]
    s, sim = _opening_scene(14., 20.5)                                         # the J30-like layout: N's branch alone
    made = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    v = made[0].run.v
    path = NS(origin=1000, box=np.asarray(sim.roll(np.full((1, 3), B["L"], np.int64)).box[0, sim.off:sim.off + 3], float),
              assumptions={})
    scan, _ = FH.entry_scan(Geo(), path, v, 1000)
    assert {(c.owner_iid, c.kind) for c in scan.contacts} == {(7, "delayed")}  # the opening: the rune only
    plain = {k: w for k, w in v.items() if k != "hook_open"}
    scan, _ = FH.entry_scan(Geo(), path, plain, 1000)
    assert {(c.owner_iid, c.kind) for c in scan.contacts} == {(8, "body"), (7, "move"), (7, "delayed")}   # before its window


def test_each_hook_branch_exempts_only_its_own_hooked_body():
    # Sol seq 340: the N branch exempts N's body only; the F branch F's body, its "move"-labelled body only through its cast's end;
    # a later attack, the other body, the bombs never
    from ssbot.combat.knife_chain_commitment import PathContact
    n_branch, f_branch = (8, None), (7, 1050)
    assert FH._exempt(PathContact(1030, 8, "body"), n_branch, 1020, 1040)
    assert not FH._exempt(PathContact(1030, 7, "move"), n_branch, 1020, 1040)    # F in the N branch: a contact
    assert not FH._exempt(PathContact(1030, 8, "body"), f_branch, 1020, 1040)    # N in the F branch: a contact
    assert FH._exempt(PathContact(1030, 7, "move"), f_branch, 1020, 1040)
    assert not FH._exempt(PathContact(1052, 7, "move"), (7, 1050), 1020, 1060)   # after its cast: a move is an attack
    assert not FH._exempt(PathContact(1030, 7, "delayed"), f_branch, 1020, 1040) # its bombs
    assert not FH._exempt(PathContact(1045, 7, "body"), f_branch, 1020, 1040)    # outside the window


@pytest.mark.parametrize("ent,field", [(8, "hook_hit_f"), (7, "hook_hit_f"), (9, "hook_other_f")])
def test_the_needle_on_the_other_branch_body_is_the_hook_hit(monkeypatch, ent, field):
    from ssbot.combat.claw_strike import CsPlan
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    from ssbot.combat.knife_chain_eval import Run
    from tests.test_knife_chain_face_hook import native, scene as fh_scene
    n = native(); s, _ = fh_scene(); n.begin(s)
    p = T.TransferPlan(7, 7, 990, 1000, 990 / 60., B["L"], 10000, 10000, 0, False, 1000, 0)
    r = n.runner
    r.run = Run("rune_transfer", "claw_lock", {**dict(r.chains["rune_transfer"].vars), **p.variables(), "cs": CsPlan(990, 0, 991, 0),
                                               "hooked_iid": 8, "hook_alt": 7})
    n.commitment = {"move": p.move, "origin": 988, "ta": 0.}
    n._hook_start = {"move": p.move, "origin": 988, "targets": (991, 992), "sent_targets": {991}, "seen_frame": 993, "hook_iid": 8}
    s2, _ = fh_scene(f=1001, clip="Harpoon Catch", accepting=False)
    s2["ev"] = [{"k": "hit", "f": 1001, "d": {"src": "Harpoon Dash Damager", "ent": ent}}]
    monkeypatch.setattr(NativeChainB2, "observe", lambda self, state: None)
    n.observe(s2)
    assert field in n.runner.run.v
    assert n._hook_start.get("hook_hit_iid") == (ent if field == "hook_hit_f" else None)
    assert T.hooked_body(n.runner.run.v, 7, n._hook_start) == (ent if field == "hook_hit_f" else 8)


def test_the_takeoff_frame_with_the_jump_held_is_rising():
    # i387_nearN 102674: the first airborne frame (y 4.054 -> 4.074) had no upward speed yet: the held jump is the rising part
    from ssbot.knowledge import kinematics as K
    S = np.zeros(K.K)
    x = NS(v={"jump_until": 30}, obs=NS(k=10, sim=NS(start=S)))
    assert T._rising(x)                                                        # J held, vy 0
    x.v["jump_until"] = 10
    assert not T._rising(x)                                                    # released, vy 0
    S[K.VY] = 2.
    assert T._rising(x)                                                        # released, still moving up


def test_b2_credits_the_rising_side_slash_on_its_own_body(monkeypatch):
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_eval import Run
    from tests.test_knife_chain_face_hook import native
    n = native()
    move = MoveInstance(7, 990, "RUNE_TRANSFER")
    n.runner.run = Run("rune_transfer", "strike", {"iid": 7, "slash_iid": 8})
    assert n._strike_iid({"move": move}) == 8
    n.runner.run = Run("rune_transfer", "strike", {"iid": 7, "slash_iid": None})
    assert n._strike_iid({"move": move}) == 7


# ---- seq 335: the hooked body's identity, apart from the Move's target ----

def test_hook_identity_reads_the_watch_then_the_run_then_the_moves_target():
    assert T.hook_iid({}, 7) == 7
    assert T.hook_iid({"hooked_iid": 8}, 7) == 8
    assert T.hook_iid({"hooked_iid": 8}, 7, {"hook_iid": 9}) == 9
    assert T.hook_iid({"hooked_iid": None}, 7, {"hook_iid": None}) == 7
    assert T.opening_pending({"hook_open": True}) and not T.opening_pending({"hook_open": True, "hook_done": True})
    assert not T.opening_pending({})


def test_the_b2_identity_veto_checks_the_hooked_body_not_the_moves_target():
    from tests.test_hook_target_identity import setup_hook
    n, s, sim, offer = setup_hook()                                            # the Move's target 8, the ray's first body 7
    reason, _ = n._hook_target_check(offer, 1000, 1002, offer.mask)
    assert reason == "hook ray first body differs from planned target"
    offer.draft.run.v["hooked_iid"] = 7                                        # the opening planned its hook on 7
    reason, info = n._hook_target_check(offer, 1000, 1002, offer.mask)
    assert reason is None and info["planned_target"] == 7 and info["move_target"] == 8


def test_the_hook_step_model_follows_the_watched_hooked_body():
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_geometry import GeometryUnavailable
    from tests.test_knife_chain_face_hook_step import anchor, seen, step_path
    a = anchor()                                                               # the hook on 8
    P = a["P"]
    caster_move = MoveInstance(7, 990, "RUNE_TRANSFER")                        # the Run's Move: the caster's
    w = {**seen(P), "move": caster_move}
    with pytest.raises(GeometryUnavailable):
        FH.step_paths(step_path(P + 20), {"hook_press": a}, w, P + 20)        # no hooked identity: the old same-Move check
    assert FH.step_paths(step_path(P + 20), {"hook_press": a}, {**w, "hook_iid": 8}, P + 20)
    with pytest.raises(GeometryUnavailable):
        FH.step_paths(step_path(P + 20), {"hook_press": a}, {**w, "hook_iid": 7}, P + 20)


@pytest.mark.parametrize("ent,field", [(8, "hook_hit_f"), (7, "hook_other_f")])
def test_the_watch_credits_the_harpoon_hit_on_the_hooked_body_only(monkeypatch, ent, field):
    from ssbot.combat.claw_strike import CsPlan
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    from ssbot.combat.knife_chain_eval import Run
    from tests.test_knife_chain_face_hook import native, scene as fh_scene
    n = native(); s, _ = fh_scene(); n.begin(s)
    p = T.TransferPlan(7, 7, 990, 1000, 990 / 60., B["L"], 10000, 10000, 0, False, 1000, 0)
    r = n.runner
    r.run = Run("rune_transfer", "claw_lock", {**dict(r.chains["rune_transfer"].vars), **p.variables(), "cs": CsPlan(990, 0, 991, 0),
                                               "hooked_iid": 8})
    n.commitment = {"move": p.move, "origin": 988, "ta": 0.}
    n._hook_start = {"move": p.move, "origin": 988, "targets": (991, 992), "sent_targets": {991}, "seen_frame": 993, "hook_iid": 8}
    s2, _ = fh_scene(f=1001, clip="Harpoon Catch", accepting=False)
    s2["ev"] = [{"k": "hit", "f": 1001, "d": {"src": "Harpoon Dash Damager", "ent": ent}}]
    monkeypatch.setattr(NativeChainB2, "observe", lambda self, state: None)
    n.observe(s2)
    v = n.runner.run.v
    assert field in v and ({"hook_hit_f", "hook_other_f"} - {field}).isdisjoint(v)
    assert p.move.target_iid == 7                                              # the Move stays the caster's
