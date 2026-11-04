"""Keep an available middle before adding an optional wall-side corralling intent."""
from types import SimpleNamespace as NS
import pytest
from ssbot.combat.tactics import gauntlet as G, modes as M
from ssbot.core.worldstate import DamageBox
from tests.test_forum_l2 import CC,subj
from tests.test_wall_pressure_intent import scene,candidate

@pytest.fixture(autouse=True)
def manual_b(monkeypatch):
 for k in ('SSBOT_FORUM_CHAIN_NATIVE','SSBOT_FORUM_CHAIN_B2','SSBOT_FORUM_CHAIN_AIR_MANUAL'):monkeypatch.setenv(k,'1')
 monkeypatch.setenv('SSBOT_FORUM_CHAIN_ARM','B');monkeypatch.setattr(G,'TWO_FOCUS',False)

def pair(side=-1,hero=4.,peer=(20.,22.)):
 tac,ws,fc=scene(side=side,hero=hero)
 if side>0:peer=(60.-peer[1],60.-peer[0])
 ws.entities.append(NS(id=8,dmg_boxes=[DamageBox(poly=[(peer[0],3.),(peer[1],3.),(peer[1],7.),(peer[0],7.)],active=True,name=CC)]))
 fc.subjects.append(subj(8,CC,sum(peer)/2,family=G.CC_IDLE))
 return tac,ws,fc

@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('hero',[4.,8.])
def test_real_bounce_does_not_pull_a_usable_middle_to_the_outer_wall(side,hero):
 tac,ws,fc=pair(side,hero);p=M.GoalPrefs(mode='ENGAGE',target=7,stance_x=30.,weights={},hit_w={7:3.})
 intent=candidate(tac,ws,fc,observed_bounce=True)
 assert intent is None
 assert M.wall_pressure_prefs(p,intent) is p

@pytest.mark.parametrize('side',[-1,1])
def test_an_already_outer_hero_drops_wall_pressure_when_middle_is_available(side):
 tac,ws,fc=pair(side,1.5)
 assert candidate(tac,ws,fc,observed_bounce=True) is None

def test_single_target_bounce_keeps_the_existing_head_start():
 tac,ws,fc=scene(hero=4.)
 assert candidate(tac,ws,fc,observed_bounce=True).wall_side==-1

def test_no_hero_width_middle_does_not_claim_a_middle_refuge():
 tac,ws,fc=pair(peer=(5.3,7.3))
 assert candidate(tac,ws,fc,observed_bounce=True).wall_side==-1

def test_unknown_peer_body_never_invents_a_wall_side_permission():
 tac,ws,fc=pair();ws.entities[1].dmg_boxes=[]
 assert candidate(tac,ws,fc,observed_bounce=True) is None

@pytest.mark.parametrize('side',[-1,1])
def test_outer_hero_without_middle_room_still_has_the_temporary_wall_option(side):
 tac,ws,fc=pair(side,1.5,peer=(5.3,7.3))
 assert candidate(tac,ws,fc,observed_bounce=True).wall_side==side
