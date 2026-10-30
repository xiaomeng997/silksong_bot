"""Shared delayed hazards: measured geometry and owner/lifecycle independence."""
import math
from dataclasses import replace

import numpy as np
import pytest
from ssbot.combat import attack_range as ar, forum_v2 as v2, rune_bombs as rb
from tests.test_attack_range_types import _clapper_table, _cl, CLAPPER


def occupied(mask,x,y):
    r,c=math.floor(y/ar.CELL)-mask.iy0,math.floor(x/ar.CELL)-mask.ix0
    return bool(0<=r<mask.m.shape[0] and 0<=c<mask.m.shape[1] and mask.m[r,c])


@pytest.mark.parametrize("face,du",[(-1,6.48),(1,6.75)])
def test_octagon_offsets_override_old_pooled_table_value(face,du):
    tab=_clapper_table();hz=next(h for h in tab.spec.hazards if h.name=="rune slam")
    tab.meta["hazards"][hz.name]["du"]=6.479526519775391
    m=tab.hazard_mask(hz,0.,0.,25.,6.6,face,66*ar.FT)
    x0,y0,x1,y1=m.bbox()
    assert (x0+x1)/2==pytest.approx(25+face*du,abs=ar.CELL)
    assert (y0+y1)/2==pytest.approx(3.33,abs=ar.CELL)
    assert not tab.hazard_mask(hz,0.,0.,25.,6.6,face,64*ar.FT).m.any()
    assert not tab.hazard_mask(hz,0.,0.,25.,6.6,face,73*ar.FT).m.any()


def test_airborne_octagon_corner_missing_from_old_circle_is_occupied():
    tab=_clapper_table();hz=next(h for h in tab.spec.hazards if h.name=="rune slam")
    m=tab.hazard_mask(hz,0,0,25.,6.6,1,66*ar.FT)
    cx,cy=31.75,3.33
    assert occupied(m,cx+6.25,cy+3.8)
    assert not occupied(ar.poly_mask([ar.circle_poly(cx,cy,hz.radius)]),cx+6.25,cy+3.8)


def test_independent_overlapping_damage_polygons_do_not_cancel_each_other():
    a=np.array([[0,0],[2,0],[2,2],[0,2.]])
    b=a+np.array([1.,0.])
    assert occupied(ar.poly_mask([a,b]),1.5,1.)
    assert occupied(ar.poly_mask([a,a]),1.,1.)


def tracker(monkeypatch):
    monkeypatch.setattr(rb,"BOMB",False)
    monkeypatch.setattr(rb,"NOPRE",False)
    return ar.RangeTracker(tables={CLAPPER:_clapper_table()})


def feed(trk,st,*,dead=False,empty=False):
    e=_cl(st,x=30.,flip=False)
    e["is_dead"]=dead
    trk.feed({"dt":ar.FT,"hero":{"pos":[36.75,5.]},"ents":[] if empty else [e]})


@pytest.mark.parametrize("gone",["dead","missing"])
def test_seen_large_rune_survives_owner_until_its_own_window_ends(monkeypatch,gone):
    trk=tracker(monkeypatch)
    for st in ("Cast Slam Antic","Jump","Slam 2"):feed(trk,st)
    hz,tt,x,y,face=trk.segs[3].spawned[0]
    feed(trk,"Idle",dead=gone=="dead",empty=gone=="missing")
    assert not trk.now and not trk.segs and 3 in trk.orphan_hazards
    on=int(round(65-(trk.T-tt)/ar.FT))
    rs=v2.RangeSupport.build(trk,samples=tuple(range(81)),margin_mode="focus",focus=3)
    du=hz.du_by_face[0 if face<0 else 1]
    cx=x+face*du
    assert rs.occupied(np.array([[cx]]),np.array([[5.]]),np.array([on])*ar.FT).item()
    assert rs.occupied_esc(np.array([[cx]]),np.array([[5.]]),np.array([on])*ar.FT).item()
    for _ in range(80):feed(trk,"Idle",empty=True)
    assert not trk.orphan_hazards


@pytest.mark.parametrize("hazard",["rune slam","rune bomb small"])
def test_target_own_hazards_remain_in_shared_focus_support_after_move_switch(monkeypatch,hazard):
    trk=tracker(monkeypatch)
    for st in (("Cast Slam Antic","Jump","Slam 2") if hazard=="rune slam" else ("Spell Antic","Cast 2")):
        feed(trk,st)
    hz,tt,x,y,face=trk.segs[3].spawned[0]
    feed(trk,"Slam Antic")
    on=int(round((65 if hazard=="rune slam" else 21)-(trk.T-tt)/ar.FT))
    e=trk.estimate(3,on)
    assert e.haz.m.any()
    rs=v2.RangeSupport.build(trk,samples=(on,),margin_mode="focus",focus=3)
    cx=x if hazard=="rune bomb small" else x+face*hz.du_by_face[0 if face<0 else 1]
    cy=5. if hazard=="rune slam" else 4.0
    assert rs.occupied(np.array([[cx]]),np.array([[cy]]),np.array([on])*ar.FT).item()
    assert rs.occupied_only(np.array([[cx]]),np.array([[cy]]),np.array([on])*ar.FT,[3]).item()
    assert rs.occupied_hazards(np.array([[cx]]),np.array([[cy]]),np.array([on])*ar.FT,[3]).item()



def test_parry_stop_does_not_freeze_target_spawned_hazard_clock(monkeypatch):
    from types import SimpleNamespace
    from ssbot.combat import forum_planner as fp
    planner=fp.ForumPlanner.__new__(fp.ForumPlanner)
    planner.cfg=SimpleNamespace(max_points=2)
    monkeypatch.setattr(fp,"stop_grow",lambda name,fr:(np.zeros(len(fr)),np.zeros(len(fr))))
    zero=lambda x,y,t,*args,**kw:np.zeros(x.shape,bool)
    forecast=SimpleNamespace(v2=True,fc=SimpleNamespace(half=(.5,1.2)),occupied_without=zero,
                             occupied_only=zero,occupied=zero)
    bound=np.broadcast_to([0.,0.,.2,.2],(1,12,4)).copy()
    skip=np.zeros((1,12),bool);times=np.arange(12)*ar.FT
    # The owner is frozen at frame 2, before its delayed object's real frame 6.
    original=planner._clash_contacts(forecast,bound,times,skip,[{3:(2,CLAPPER)}])
    assert not original.any()
    forecast.occupied_hazards=lambda x,y,t,ids:np.broadcast_to(t>=6*ar.FT,x.shape).copy()
    checked=planner._clash_contacts(forecast,bound,times,skip,[{3:(2,CLAPPER)}])
    assert not checked[0,:6].any() and checked[0,6:].all()


def test_independent_per_bomb_hazard_keeps_owner_and_actual_clock():
    rs=v2.RangeSupport(v2.Canvas(),(0,10))
    rs.bombs=np.array([[3.,30.,4.,2.,0.,10.]])
    X=np.array([[30.]]);Y=np.array([[4.]]);tk=np.array([5*ar.FT])
    assert rs.occupied_hazards(X,Y,tk,[3]).item()
    assert not rs.occupied_hazards(X,Y,tk,[8]).item()


@pytest.mark.parametrize("mode,expected", [("focus",.5),("rule",.5),("table",.5),("flat:0.2",.2),("zero",0.)])
def test_orphan_anchor_does_not_inherit_walk_uncertainty(monkeypatch,mode,expected):
    trk=tracker(monkeypatch)
    for st in ("Cast Slam Antic","Jump","Slam 2"):feed(trk,st)
    hz,tt,x,y,face=trk.segs[3].spawned[0]
    feed(trk,"Idle",empty=True)
    on=int(round(65-(trk.T-tt)/ar.FT))
    rs=v2.RangeSupport.build(trk,samples=(on,),margin_mode=mode)
    parts=rs.haz_raw[3]
    assert parts and all(p[4]==expected and p[5]==expected for p in parts)
    du=hz.du_by_face[0 if face<0 else 1]
    cx=x+face*du
    center=np.array([[cx]]);Y=np.array([[5.]]);times=np.array([on])*ar.FT
    # A real lit orphan stays dangerous; a body-drift halo several units
    # outside the same fixed circle must not block another target's path.
    assert rs.occupied(center,Y,times).item()
    assert rs.occupied_esc(center,Y,times).item()
    assert rs.occupied_hazards(center,Y,times,[3]).item()
    outside=np.array([[cx+hz.radius+2.]])
    assert not rs.occupied_hazards(outside,np.array([[3.33]]),times,[3]).item()
