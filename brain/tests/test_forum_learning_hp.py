"""HP2 learning exit is usable without enabling the w7-only chain controller."""
from types import SimpleNamespace as NS
import random
from ssbot.train import forum_planner_policy as PP
from ssbot.train.encounters import ENCOUNTERS
from ssbot.knowledge.kinematics import Terrain2D


def policy(monkeypatch, floor):
    monkeypatch.setattr(PP,"REMAINING_HP_QUIT",floor)
    monkeypatch.setattr(PP,"SCENE_FIELD_SHADOW",False)
    monkeypatch.setattr(PP,"SCENE_FIELD_RANK",False)
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_NATIVE","0")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_B2","0")
    p=PP.ForumPlannerPolicy(crest="Wanderer",clash="main")
    p.terrain=Terrain2D.empty()
    p.reset(random.Random(123),ENCOUNTERS["Forum_W_w13"])
    assert p.chain_native is None
    return p


def test_w13_reset_uses_q1_hp_floor_without_starting_b2(monkeypatch):
    p=policy(monkeypatch,2)
    assert p.sc.cfg.remaining_hp_quit==2
    assert p.sc.sup.cfg.remaining_hp_quit==2


def test_disabled_generic_floor_retains_ordinary_h2(monkeypatch):
    p=policy(monkeypatch,0)
    assert p.sc.cfg.remaining_hp_quit is None


def test_weighted_model_reconfiguration_keeps_the_same_hp_boundary(monkeypatch):
    p=policy(monkeypatch,2)
    p._first_tick(NS(res=NS(equipped=(PP.ANKLET,))),{"hero":{"crest":"Wanderer"}})
    assert p.weighted and p.sc.cfg.remaining_hp_quit==p.sc.sup.cfg.remaining_hp_quit==2


def test_explicit_floor_cannot_weaken_an_existing_batch_boundary(monkeypatch):
    monkeypatch.setattr(PP,"REMAINING_HP_QUIT",1)
    p=PP.ForumPlannerPolicy.__new__(PP.ForumPlannerPolicy)
    p.chain_native=NS(budget=NS(remaining_hp_quit=2))
    assert p._remaining_hp_quit()==2
    monkeypatch.setattr(PP,"REMAINING_HP_QUIT",3)
    assert p._remaining_hp_quit()==3
