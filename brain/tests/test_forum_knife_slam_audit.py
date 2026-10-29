import numpy as np
from ssbot.tools.forum_knife_slam_audit import polygon_distance,real_distances,contacts


def test_concave_arc_distance_is_not_its_aabb_overlap():
    p=np.array([[0,0],[3,0],[3,1],[1,1],[1,3],[0,3]],float)
    assert abs(polygon_distance((2,2,2.5,2.5),p)-1.)<1e-12
    assert polygon_distance((.2,.2,.8,.8),p)==0.


def test_root_and_arc_layers_are_not_confused():
    poly=[0.,0.,1.,0.,1.,1.,0.,1.]
    def col(name,layer):return dict(name=name,kind="box",enabled=True,layer=layer,
                                  damage=dict(dealt=2,eff=2),verts_world=poly)
    ent=dict(iid=7,colliders=[col("Song Heavy Sentry",11),col("Slam Collider 1",22),
                            col("Slam Collider 1 Ally",24)],fsms=[dict(name="Control",state="Slam 1")])
    s=dict(hero=dict(box=[3.,0.,4.,1.]),ents=[ent])
    geo=real_distances(s,7)
    assert geo["parts"]["arc1"]["enabled"]==1 and geo["parts"]["arc1"]["layers"]==[22]
    assert geo["parts"]["body"]["bounds_u"]==2.
    assert geo["complete_for_clear_label"]
    ent["colliders"]=ent["colliders"][:1]
    assert not real_distances(s,7)["complete_for_clear_label"]


def test_two_clapper_contact_without_iid_requires_a_unique_root_name():
    s=dict(ents=[dict(iid=7,colliders=[dict(name="Song Heavy Sentry",kind="box",layer=11)]),
                 dict(iid=8,colliders=[dict(name="Song Heavy Sentry (2)",kind="box",layer=11)])],
           ev=[dict(k="damage",d=dict(source="Song Heavy Sentry (2)/Slam Collider 1"))])
    assert contacts(s,8,False)[0]["owner_matches"]
    assert not contacts(s,7,False)[0]["owner_matches"]
    s["ev"][0]["d"]["source"]="Colliders/Slam Collider 1"
    assert contacts(s,8,False)[0]["owner_ambiguous"]
