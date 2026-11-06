"""Event-selected manual target preference, exercised through the real L2 entry."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from ssbot.combat.tactics import gauntlet as G, clapper_priority as P
from ssbot.combat.tactics.modes import EntryAttack, GoalPrefs
from ssbot.core.worldstate import DamageBox, E
from tests.test_forum_l2 import CC, WinFc, l2, subj, world
from tests.test_target_entry_attack import native
from tests.test_knife_chain_transfer import cast_scene


@pytest.fixture(autouse=True)
def manual(monkeypatch):
    for k in ("SSBOT_FORUM_CHAIN_NATIVE", "SSBOT_FORUM_CHAIN_B2", "SSBOT_FORUM_CHAIN_AIR_MANUAL"):
        monkeypatch.setenv(k, "1")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_ARM", "B")
    monkeypatch.setattr(G, "TWO_FOCUS", True)
    monkeypatch.setattr(G, "TWO_SPRINTSW", True)
    monkeypatch.setattr(G.jump_behind, "ENABLED", True)


def scene(xs=(20., 40.), hx=27., default=float("inf")):
    tac = l2(); tac.pb.arena_x = (0., 60.)
    es = [NS(id=i, flip_x=x < hx, vel=E((0., 0.)), dmg_boxes=[DamageBox(
        poly=[(x-1., 3.), (x+1., 3.), (x+1., 7.), (x-1., 7.)], active=True, name=CC)])
          for i, x in zip((7, 8), xs)]
    ws = world(hx, ents=es)
    ws.hero.hurtbox = [(hx-.25, 4.), (hx+.25, 4.), (hx+.25, 6.), (hx-.25, 6.)]
    fc = WinFc([subj(i, CC, x, family=G.CC_IDLE) for i, x in zip((7, 8), xs)], default=default)
    tac.goal = G.Goal(G.RUSH, 7, xs[0]+4., 1., family=G.CC_IDLE)
    return tac, ws, fc


def step(tac, ws, fc):
    ws.stamp.t_game_s += 1/60.
    return tac._decide(ws, fc, GoalPrefs(mode="ENGAGE", stance_x=27., weights={}, hit_w={7: 1., 8: 1.}))


def change(fc, iid, **kw):
    fc.subjects = [replace(s, **kw) if s.iid == iid else s for s in fc.subjects]


@pytest.mark.parametrize("family,state", [(G.CC_CAST, "Spell Antic"), (G.CC_SLAM, "Slam Antic"),
    (G.CC_JUMP, "Jump Antic"), (G.CC_JUMP_CAST, "Cast Slam Antic 2")])
def test_focus_outputs_through_its_antic_instead_of_early_long_switch(family, state):
    # The middle scene now has its own causal guide/landing decision.
    tac, ws, fc = scene(hx=15.); step(tac, ws, fc)
    change(fc, 7, family=family, state=state, committed=True)
    tac.two_esc = {"hold": 8, "mode": "wall", "stance": 50., "no_hit": [7, 8]}
    out = step(tac, ws, fc)
    assert out.target == 7 and 7 not in out.no_hit and out.entry_attack is None
    if family in P.JUMPS: assert out.stance_x == pytest.approx(16.)


TIGHT = dict(xs=(20., 22.4), hx=21.2)    # between the two with no standing room: bodies 19..21 and 21.4..23.4


@pytest.mark.parametrize("covered", [False, True])
def test_outside_takeoff_is_no_switch_into_the_cluster(covered):
    # Task 179 #309 (the person, seq 229): both Clappers beyond her - leaving the jumper for the other one is no dodge.
    tac, ws, fc = scene(hx=15.); step(tac, ws, fc)
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    assert step(tac, ws, fc).target == 7
    if covered: fc.default = 0.
    change(fc, 7, state="Jump")
    out = step(tac, ws, fc)
    assert out.target == 7 and out.entry_attack is None and 7 in out.no_hit
    assert all(c["rule"] != "takeoff" for c in tac.last["clapper_choices"])
    assert tac.last["clapper_region"] == "left"


@pytest.mark.parametrize("covered", [False, True])
def test_takeoff_between_the_two_switches_with_a_stomp_entry(covered):
    tac, ws, fc = scene(**TIGHT); step(tac, ws, fc)
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    assert step(tac, ws, fc).target == 7
    if covered: fc.default = 0.
    change(fc, 7, state="Jump")
    out = step(tac, ws, fc)
    assert tac.last["clapper_region"] == "tight"
    assert out.target == 8 and out.entry_attack.kind == "stomp"     # no ground room between: never a side slash
    assert out.entry_attack.source_family == G.CC_JUMP and out.entry_attack.source == 7
    assert out.hit_kw[8][3] > 0


@pytest.mark.parametrize("family", [G.CC_JUMP, G.CC_JUMP_CAST])
@pytest.mark.parametrize("covered", [False, True])
def test_takeoff_does_not_reintercept_the_same_departed_focus(family, covered):
    # Live 68f: takeoff switched away at2608, rear-intercept undid it at2609 (here between the two: #309).
    tac, ws, fc = scene(**TIGHT); step(tac, ws, fc)
    change(fc, 7, family=family, state="Jump Antic", committed=True)
    step(tac, ws, fc); tac.t_commit[7] = 1.
    if covered: fc.default = 0.
    change(fc, 7, state="Jump")
    assert step(tac, ws, fc).target == 8
    change(fc, 7, state="Air")
    tac.jb_land[7] = (10., 1., 20., True)  # it took off behind us; current geometry is outside
    for _ in range(tac.rules.period * 2):
        assert step(tac, ws, fc).target == 8
        assert not any(c["rule"] == "intercept" for c in tac.last.get("clapper_choices") or ())


@pytest.mark.parametrize("next_event", ["new_jump", "near_attack"])
def test_departed_focus_suppression_ends_at_a_new_move(next_event):
    tac, ws, fc = scene(**TIGHT); step(tac, ws, fc)
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    step(tac, ws, fc); tac.t_commit[7] = 1.
    change(fc, 7, state="Jump")
    assert step(tac, ws, fc).target == 8
    change(fc, 7, state="Air")
    tac.jb_land[7] = (10., 1., 20., True)
    assert step(tac, ws, fc).target == 8
    if next_event == "new_jump":
        tac.t_commit[7] = 2.
        assert step(tac, ws, fc).target == 7
        assert tac.last["clapper_winner"]["rule"] == "intercept"
    else:
        change(fc, 7, family=G.CC_IDLE, state="Idle", committed=False)
        step(tac, ws, fc)
        change(fc, 7, family=G.CC_SLAM, state="Slam Antic", committed=True)
        assert step(tac, ws, fc).target == 7
        assert tac.last["clapper_winner"]["rule"] == "near"


def test_no_micro_room_switch_without_a_new_event():
    tac, ws, fc = scene(); assert step(tac, ws, fc).target == 7
    change(fc, 8, pos=(36., 5.))
    for _ in range(tac.rules.period * 2): assert step(tac, ws, fc).target == 7


def test_new_near_nonfocus_attack_interrupts_default_then_does_not_bounce_back():
    tac, ws, fc = scene((28., 40.), 33.); assert step(tac, ws, fc).target == 7
    change(fc, 7, family=G.CC_SLAM, state="Slam Antic", committed=True)
    change(fc, 8, family=G.CC_CAST, state="Spell Antic", committed=True)
    assert step(tac, ws, fc).target == 8
    for _ in range(tac.rules.period * 2): assert step(tac, ws, fc).target == 8


def test_far_nonfocus_antic_does_not_steal_focus():
    tac, ws, fc = scene(); step(tac, ws, fc)
    change(fc, 8, family=G.CC_SLAM, state="Slam Antic", committed=True)
    assert step(tac, ws, fc).target == 7


def test_rear_jumper_is_intercepted_then_kept_after_landing():
    tac, ws, fc = scene((30., 28.), 26.); step(tac, ws, fc)
    change(fc, 8, family=G.CC_JUMP, state="Air", committed=True)
    tac.jb_land[8] = (18., 1., 28., True)
    out = step(tac, ws, fc)
    assert out.target == 8 and 8 in out.no_hit and out.entry_attack is None
    change(fc, 7, family=G.CC_SLAM, state="Slam Antic", committed=True)
    for _ in range(tac.rules.period * 2): assert step(tac, ws, fc).target == 8
    change(fc, 8, family=G.CC_IDLE, state="Idle", committed=False)
    assert step(tac, ws, fc).target == 8
    assert tac._clapper_priority["intercept"] is None


@pytest.mark.parametrize("side", [-1, 1])
def test_outside_jump_retreat_is_not_overwritten_by_escape_or_wall_pressure(side):
    xs, hx = ((52., 56.), 48.) if side < 0 else ((8., 4.), 12.)
    tac, ws, fc = scene(xs, hx); step(tac, ws, fc)
    change(fc, 8, family=G.CC_JUMP_CAST, state="Air", committed=True)
    tac.two_esc = {"hold": 8, "stance": 30., "no_hit": []}
    out = step(tac, ws, fc)
    assert (out.stance_x - hx) * side > 0
    assert out.no_hit == frozenset({7, 8}) and out.entry_attack is None
    assert tac.last["clapper_scene"] == "outer jump retreat"


@pytest.mark.parametrize("side", [-1, 1])
def test_outside_near_attack_requests_inward_contact_without_fake_crossing(side):
    xs, hx = ((20., 24.), 16.) if side < 0 else ((40., 36.), 44.)
    tac, ws, fc = scene(xs, hx); step(tac, ws, fc)
    change(fc, 7, family=G.CC_SLAM, state="Slam Antic", committed=True)
    out = step(tac, ws, fc)
    assert out.target == 7 and (out.stance_x-xs[0]) * side < 0
    assert 7 not in out.no_hit and out.hit_kw[7][3] > 0
    assert tac.last["clapper_scene"] == "flip inward intent"


def test_tight_middle_requests_overhead_without_claiming_continuous_pogo():
    tac, ws, fc = scene((20., 22.), 21.)
    out = step(tac, ws, fc)
    assert out.hit_kw[out.target][3] > 0
    assert out.target not in out.ground_hit | out.no_pogo | out.ground_first
    assert tac.last["clapper_scene"] == "tight middle overhead intent"


def test_unknown_body_cannot_fabricate_ground_arrival():
    tac, ws, fc = scene(); step(tac, ws, fc)
    ws.entities[1].dmg_boxes = []
    change(fc, 7, family=G.CC_JUMP, state="Air", committed=True)
    out = step(tac, ws, fc)
    assert out.target == 8 and out.entry_attack.kind == "stomp"
    assert tac.last["clapper_region"] is None


@pytest.mark.parametrize("arm", ["A", "", "b"])
def test_other_profiles_do_not_enter_manual_priority(monkeypatch, arm):
    _, _, fc = scene(); monkeypatch.setenv("SSBOT_FORUM_CHAIN_ARM", arm)
    assert not P.enabled(fc)


def test_reset_drops_intercept_and_region_state():
    tac, ws, fc = scene(); step(tac, ws, fc)
    assert tac._clapper_priority is not None
    tac.reset(); assert tac._clapper_priority is None


def test_incompatible_legacy_script_profile_keeps_its_existing_owner(monkeypatch):
    _, _, fc = scene(); monkeypatch.setattr(G.two_play, 'ASW', True)
    assert not P.enabled(fc)


def test_two_play_cannot_rewrite_a_manual_winner_or_run_its_old_early_escape(monkeypatch):
    T = G.two_play
    two = T.TwoPlay(); two.manual_focus = True
    monkeypatch.setattr(T, 'SPACE', True); monkeypatch.setattr(T, 'ESC', True)
    monkeypatch.setattr(T, 'OPEN', False); monkeypatch.setattr(T, 'IDLEHIT', True)
    two.esc = NS(mode='switch')
    monkeypatch.setattr(two, '_esc_step', lambda *a: pytest.fail('old early-switch keys must not override L2'))
    monkeypatch.setattr(two, '_idle_step', lambda *a: 321)
    p = GoalPrefs(mode='RUSH', stance_x=20., weights={}, target=7, clapper_choice='keep')
    assert two.space(p, cast_scene(), 10., 7) is p
    assert two.step(1000, cast_scene(), True, True, 7, 10.) == 321
    assert two.last_part == 'idle'
    two.manual_focus = False
    monkeypatch.setattr(two, '_esc_step', lambda *a: 456)
    assert two.step(1001, cast_scene(), True, True, 7, 10.) == 456
    assert two.last_part == 'esc'


def test_optional_wall_pressure_does_not_compete_again_after_manual_choice():
    tac, ws, fc = scene((4., 6.), 1.5); step(tac, ws, fc)
    assert tac.wall_pressure_candidate(ws, fc, 7, observed_bounce=True) is None


def test_lowering_one_tactic_maximum_really_changes_the_winner():
    tac, ws, fc = scene((28., 40.), 33.); step(tac, ws, fc)
    tac.rules.clapper_scores = {"near": 40.}
    change(fc, 8, family=G.CC_CAST, state="Spell Antic", committed=True)
    out = step(tac, ws, fc)
    assert out.target == 7
    choices = {c["rule"]: c for c in tac.last["clapper_choices"]}
    candidate = choices["near"]
    assert 0. < candidate["applicability"] < 1.
    assert candidate["score"] == pytest.approx(40. * candidate["applicability"] - candidate["switch_cost"])
    assert choices["keep"]["score"] > candidate["score"]


def test_lowering_flip_maximum_suppresses_inward_preference():
    tac, ws, fc = scene((20., 24.), 16.); step(tac, ws, fc)
    tac.rules.clapper_scores = {"flip": 10.}
    change(fc, 7, family=G.CC_SLAM, state="Slam Antic", committed=True)
    step(tac, ws, fc)
    assert tac.last["clapper_winner"]["rule"] == "keep"
    assert tac.last["clapper_scene"] != "flip inward intent"


@pytest.mark.parametrize("scores", [{"near": -1.}, {"unknown": 5.}, {"keep": float("nan")}])
def test_invalid_score_configuration_is_rejected_before_combat(scores):
    with pytest.raises(ValueError): G.L2Rules.from_dict({"clapper_scores": scores})


@pytest.mark.parametrize("family,primary", [(G.CC_JUMP, "Jump Antic"), (G.CC_JUMP_CAST, "Cast Slam Antic")])
def test_takeoff_entry_binds_real_causal_source_antic(family, primary):
    n = native(); s = cast_scene(); before = deepcopy(s)
    before['f'] = 998; before['ents'][0]['fsms'][0].update(state=primary, t=.2)
    n._ticks.append((998, before, 19.8, True, True))
    s['ents'][0]['fsms'][0].update(state='Air', t=.1)
    prefs = GoalPrefs(mode='RUSH', stance_x=38., weights={}, target=8,
                      entry_attack=EntryAttack(8, 'stomp', 7, family, 4., 10.))
    n.goal_preferences(s, prefs, handoff=True)
    assert n._transfer_ready and n._transfer_goal.responsibility.family == family
    assert n._transfer_goal.responsibility.antic_frame == 986
    assert n._transfer_goal.cast_ta == pytest.approx(19.6)


def test_air_source_without_observed_antic_does_not_invent_move_identity():
    n = native(); s = cast_scene(); s['ents'][0]['fsms'][0].update(state='Air', t=.1)
    p = GoalPrefs(mode='RUSH', stance_x=38., weights={}, target=8,
        entry_attack=EntryAttack(8, 'stomp', 7, G.CC_JUMP, 4., 10.))
    n.goal_preferences(s, p, handoff=True)
    assert n._transfer_goal is None and not n._transfer_ready


@pytest.mark.parametrize('family,primary', [(G.CC_JUMP, 'Jump Antic'), (G.CC_JUMP_CAST, 'Cast Slam Antic')])
@pytest.mark.parametrize('source_shift,available', [(0., True), (1., False)])
def test_jump_source_reaches_the_existing_action_offer_and_checks_its_instance(monkeypatch, family, primary, source_shift, available):
    from ssbot.combat import knife_chain_air_native as mod
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_transfer import transfer_motion_scene
    r, state, sim = transfer_motion_scene(K.M_NORMAL); r.run = None
    n = native(); n._clock = .1; n.runner = r
    prior = deepcopy(state); prior['f'] -= 1
    prior['ents'][0]['fsms'][0].update(state=primary, t=.08)
    n._ticks.append((prior['f'], prior, .08, True, True))
    state['ents'][0]['fsms'][0].update(state='Air', t=.02)
    p = GoalPrefs(mode='RUSH', stance_x=48., weights={}, target=8,
        entry_attack=EntryAttack(8, 'stomp', 7, family, 4., 10.))
    n.goal_preferences(state, p, handoff=True); n._context = (None, sim, None, None)
    monkeypatch.setattr(n, 'queued_prefix', lambda *a: (int(sim.prefix[0]), 'actual fixture prefix'))
    checked = []
    monkeypatch.setattr(mod.B2Geometry, 'preflight', lambda self, path: checked.append(path) or NS(complete=True, contacts=[]))
    fc = NS(rs=NS(trk=NS(T=.1, now={8: (None, None, None), 7: (None, None, NS(fam=family, t0=source_shift))})))
    offer = n._transfer_offer(state, .1, sim, fc, p, True)
    assert (offer is not None) == available
    assert bool(checked) == available
    if available:
        assert offer.draft.run.chain == 'rune_transfer' and offer.draft.run.v['_entry_source_confirmed']
        assert offer.mask == int(sim.prefix[0]) and not n._receipts and n.commitment is None


@pytest.mark.parametrize('family,state,distance', [(G.CC_IDLE,'Idle',7.),(None,'Idle',7.),('CC_EVADE','Evade Scuttle',7.),(G.CC_IDLE,'Idle',12.)])
def test_manual_keep_retains_the_same_sp4_contact_preferences_as_legacy(monkeypatch, family, state, distance):
    for name in ('ENABLED','NODASH','NOPOGO'): monkeypatch.setattr(G.slam_play,name,True)
    tac,ws,fc=scene((20.,50.),20.+distance);change(fc,7,family=family,state=state)
    out=step(tac,ws,fc)
    assert out.target==7 and 7 in out.no_pogo and 7 in out.ground_hit
    assert (7 in out.no_dash)==(distance<=G.slam_play.NODASH_U)
    monkeypatch.setattr(P,'enabled',lambda fc:False)
    old,ws2,fc2=scene((20.,50.),20.+distance);change(fc2,7,family=family,state=state)
    prior=step(old,ws2,fc2)
    assert (out.no_dash,out.no_pogo,out.ground_hit)==(prior.no_dash,prior.no_pogo,prior.ground_hit)


@pytest.mark.parametrize('entry_style',['entry','tight'])
def test_explicit_stomp_still_overrides_sp4_ground_only_bias(monkeypatch,entry_style):
    for name in ('ENABLED','NODASH','NOPOGO'): monkeypatch.setattr(G.slam_play,name,True)
    if entry_style=='tight':
        tac,ws,fc=scene((20.,22.),21.);out=step(tac,ws,fc)
    else:
        tac,ws,fc=scene(**TIGHT);step(tac,ws,fc)
        change(fc,7,family=G.CC_JUMP,state='Air',committed=True);fc.default=0.;out=step(tac,ws,fc)
        assert out.entry_attack.kind=='stomp'
    assert out.hit_kw[out.target][3]>0
    assert out.target not in out.no_pogo|out.ground_hit|out.ground_first


@pytest.mark.parametrize('side',[-1,1])
def test_wall_trap_never_offers_retreat_into_the_wall_or_silences_both_targets(side):
    xs,hx=((4.,8.),1.8) if side<0 else ((56.,52.),58.2)
    tac,ws,fc=scene(xs,hx);step(tac,ws,fc)
    change(fc,8,family=G.CC_JUMP,state='Air',committed=True);out=step(tac,ws,fc)
    assert all(c['rule']!='retreat' for c in tac.last['clapper_choices'])
    assert not {7,8}.issubset(out.no_hit)


@pytest.mark.parametrize('side',[-1,1])
def test_no_wall_squeeze_does_not_offer_the_wall_cluster_retreat(side):
    xs,hx=((20.,24.),16.) if side<0 else ((40.,36.),44.)
    tac,ws,fc=scene(xs,hx);step(tac,ws,fc)
    change(fc,8,family=G.CC_JUMP,state='Air',committed=True);step(tac,ws,fc)
    assert all(c['rule']!='retreat' for c in tac.last['clapper_choices'])
