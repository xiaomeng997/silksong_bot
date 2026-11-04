"""An outside passive focus must not keep rewarded DPS ahead of returning inside."""
from dataclasses import replace
import pytest
from ssbot.combat.tactics import gauntlet as G, modes as M
from ssbot.core.worldstate import E
from tests.test_wall_middle_guard import pair

@pytest.fixture(autouse=True)
def manual_b(monkeypatch):
 for k in ('SSBOT_FORUM_CHAIN_NATIVE','SSBOT_FORUM_CHAIN_B2','SSBOT_FORUM_CHAIN_AIR_MANUAL'): monkeypatch.setenv(k,'1')
 monkeypatch.setenv('SSBOT_FORUM_CHAIN_ARM','B');monkeypatch.setattr(G,'TWO_FOCUS',False)

def decide(monkeypatch,side=-1,hero=1.5,peer=(20.,22.)):
 tac,ws,fc=pair(side,hero,peer)
 monkeypatch.setattr(tac,'_pick',lambda *a:tac.goal)
 prefs=M.GoalPrefs(mode='ENGAGE',stance_x=30.,weights={},hit_w={7:3.,8:1.})
 return tac,ws,fc,prefs

@pytest.mark.parametrize('side',[-1,1])
def test_outside_passive_focus_prefers_middle_and_keeps_other_target_reward(monkeypatch,side):
 tac,ws,fc,p=decide(monkeypatch,side)
 out=tac._decide(ws,fc,p)
 assert out.target==7 and out.entry_attack is None and out.wall_pressure is None
 assert 7 in out.no_hit and 8 not in out.no_hit
 assert 5.25<=out.stance_x<=19.75 if side<0 else 40.25<=out.stance_x<=54.75
 assert (out.stance_x-ws.hero.pos.v[0])*side<0
 assert 'return middle' in tac.goal.why

@pytest.mark.parametrize('side',[-1,1])
def test_reentering_middle_immediately_restores_normal_hit_preferences(monkeypatch,side):
 tac,ws,fc,p=decide(monkeypatch,side)
 assert 7 in tac._decide(ws,fc,p).no_hit
 hx=8. if side<0 else 52.
 ws.hero.pos=E((hx,5.6));ws.hero.hurtbox=[(hx-.25,4.5),(hx+.25,4.5),(hx+.25,6.5),(hx-.25,6.5)]
 out=tac._decide(ws,fc,p)
 assert 7 not in out.no_hit and 'return middle' not in tac.goal.why

@pytest.mark.parametrize('family,state',[(G.CC_SLAM,'Slam Antic'),(G.CC_JUMP,'Jump Antic'),(G.CC_JUMP_CAST,'Cast Antic'),(G.CC_CAST,'Cast Antic')])
def test_current_attack_stance_is_not_overridden(monkeypatch,family,state):
 tac,ws,fc,p=decide(monkeypatch)
 fc.subjects[0]=replace(fc.subjects[0],family=family,state=state)
 out=tac._decide(ws,fc,p)
 assert 'return middle' not in tac.goal.why

@pytest.mark.parametrize('case',['single','narrow','unknown_peer','unknown_hero','unknown_conf','overlap','entry','prior_no_hit','arm_a','off'])
def test_unavailable_geometry_or_existing_owner_priority_has_no_middle_intent(monkeypatch,case):
 tac,ws,fc,p=decide(monkeypatch,peer=(5.3,7.3) if case=='narrow' else (20.,22.))
 if case=='single':fc.subjects=fc.subjects[:1];ws.entities=ws.entities[:1]
 elif case=='unknown_peer':ws.entities[1].dmg_boxes=[]
 elif case=='unknown_hero':ws.hero.hurtbox=[]
 elif case=='unknown_conf':ws.hero.pos=E(ws.hero.pos.v,conf=0.)
 elif case=='overlap':ws.entities[1].dmg_boxes[0].poly=[(4.,3.),(6.,3.),(6.,7.),(4.,7.)]
 elif case=='entry':tac.goal.entry_attack=M.EntryAttack(7,'stomp',8,G.CC_CAST,10.,10.)
 elif case=='prior_no_hit':p=replace(p,no_hit=frozenset({7}))
 elif case=='arm_a':monkeypatch.setenv('SSBOT_FORUM_CHAIN_ARM','A')
 elif case=='off':monkeypatch.setenv('SSBOT_FORUM_CHAIN_AIR_MANUAL','0')
 out=tac._decide(ws,fc,p)
 assert 'return middle' not in tac.goal.why

@pytest.mark.parametrize('side',[-1,1])
def test_midfield_outer_side_also_returns_and_never_selects_another_target(monkeypatch,side):
 tac,ws,fc,p=decide(monkeypatch,side)
 shift=12. if side<0 else -12.
 for e in ws.entities:
  e.dmg_boxes[0].poly=[(x+shift,y) for x,y in e.dmg_boxes[0].poly]
 fc.subjects=[replace(s,pos=(s.pos[0]+shift,s.pos[1])) for s in fc.subjects]
 hx=ws.hero.pos.v[0]+shift;ws.hero.pos=E((hx,5.6));ws.hero.hurtbox=[(x+shift,y) for x,y in ws.hero.hurtbox]
 out=tac._decide(ws,fc,p)
 assert out.target==7 and 7 in out.no_hit and (out.stance_x-hx)*side<0


@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('hero',[3.,4.,5.2499])
def test_hero_over_target_keeps_same_target_followup_reward(monkeypatch,side,hero):
 tac,ws,fc,p=decide(monkeypatch,side,hero)
 out=tac._decide(ws,fc,p)
 assert 7 not in out.no_hit and 'return middle' not in tac.goal.why

@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('hero,returning',[(2.75,True),(2.7501,False)])
def test_outer_requires_the_whole_hero_box_to_clear_the_outer_body_edge(monkeypatch,side,hero,returning):
 tac,ws,fc,p=decide(monkeypatch,side,hero)
 out=tac._decide(ws,fc,p)
 assert (7 in out.no_hit)==returning

@pytest.mark.parametrize('side',[-1,1])
def test_an_earlier_tactical_danger_stance_keeps_priority(monkeypatch,side):
 tac,ws,fc,p=decide(monkeypatch,side)
 tac.ta=frozenset({"guard"})
 wanted=1. if side<0 else 59.
 monkeypatch.setattr(tac,'_ta_rules',lambda ws,fc,out,*a:(replace(out,stance_x=wanted),['guard']))
 out=tac._decide(ws,fc,p)
 assert out.stance_x==wanted and 7 not in out.no_hit
