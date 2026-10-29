"""CC_SLAM forecast audit on the existing 34 development trajectories.

Fixed early-Antic origin; raw real paths are outcomes, never supplied to the
forecast. Real game-time queries are a separate oracle diagnostic. No A/A data,
held-out evaluation, safety certification or production model edits.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np

PARTS = ("arc1", "slam2", "body")


def collider_part(name):
    if name.startswith("Slam Collider 1"): return "arc1"
    if name.startswith("Slam Collider 2"): return "slam2"
    if name.startswith("Song Heavy Sentry"): return "body"
    return None


def polygon_distance(rect, vertices):
    """Euclidean distance to one exported closed outline, including concavity."""
    from ssbot.combat.planner import _rect_meets_polys
    vs=np.asarray(vertices,float).reshape(-1,2)
    if len(vs)<3 or not np.isfinite(vs).all():raise ValueError("invalid real collider vertices")
    flat=np.ascontiguousarray(vs);starts=np.array([0,len(vs)],np.int64)
    if _rect_meets_polys(*rect,flat,starts,0.,0.):return 0.
    x0,y0,x1,y1=rect
    corners=np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]])
    def point_edges(points,a):
        end=np.roll(a,-1,axis=0);v=end-a;length=(v*v).sum(axis=1)
        t=np.clip(((points[:,None]-a[None])*v[None]).sum(axis=2)/np.maximum(length,1e-30),0.,1.)
        delta=points[:,None]-(a[None]+t[:,:,None]*v[None])
        return float(np.sqrt((delta*delta).sum(axis=2).min()))
    return min(point_edges(corners,vs),point_edges(vs,corners))


def aabb_distance(a,b):
    return math.hypot(max(a[0]-b[2],b[0]-a[2],0.),max(a[1]-b[3],b[1]-a[3],0.))


def real_distances(state, iid):
    ent = next((e for e in state.get("ents", ()) if e.get("iid") == iid), None)
    if ent is None: return None
    b = np.asarray(state["hero"]["box"], float)
    cx, cy = .5*(b[0]+b[2]), .5*(b[1]+b[3])
    hurt = (cx-.2277,cy+.133-1.1249,cx+.2277,cy+.133+1.1249)
    out = {part:{"bounds_u":None,"hurtbox_u":None,"aabb_u":None,"enabled":0,
                 "can_damage":0,"names":[],"layers":[]} for part in PARTS}
    for c in ent.get("colliders", ()):
        name=str(c.get("name", ""));part=collider_part(name);dm=c.get("damage")
        if (part is None or "Ally" in name or not c.get("enabled",True)
                or (part=="body" and c.get("layer")!=11)
                or not dm or (dm.get("dealt",0)<=0 and dm.get("eff",0)<=0)):
            continue
        # Root bodies use layer 11; the real Slam arcs are layer 22.
        # Never silently drop damaging arcs by applying the root-body filter.
        vs=np.asarray(c.get("verts_world",()),float)
        if len(vs)<6 or len(vs)%2 or not np.isfinite(vs).all():
            raise ValueError("invalid real collider vertices")
        points=vs.reshape(-1,2);pb=(points[:,0].min(),points[:,1].min(),points[:,0].max(),points[:,1].max())
        d=out[part];d["enabled"]+=1;d["can_damage"]+=int(dm.get("can_cause_damage") is not False)
        d["names"].append(name);d["layers"].append(c.get("layer"))
        for key,value in (("bounds_u",polygon_distance(b,points)),("hurtbox_u",polygon_distance(hurt,points)),
                          ("aabb_u",aabb_distance(b,pb))):
            d[key]=float(value) if d[key] is None else min(d[key],float(value))
    control=next((m for m in ent.get("fsms",()) if m.get("name")=="Control"),{})
    st=control.get("state")
    complete=bool(out["body"]["enabled"] and st in ("Slam Antic","Slam 0","Slam 1","Slam 2","Slam Recover"))
    if st=="Slam 1":complete &= bool(out["arc1"]["enabled"])
    if st=="Slam 2":complete &= bool(out["slam2"]["enabled"])
    return {"state":st,"state_time":control.get("t"),"parts":out,"complete_for_clear_label":complete}


def contacts(s, iid, unique_type):
    out=[]
    for ev in s.get("ev",()):
        if ev.get("k") not in ("damage","damage_blocked"): continue
        d=ev.get("d",{});source=str(d.get("source", ""));name=source.rsplit("/",1)[-1]
        part=collider_part(name)
        if part is None: continue
        owner = d.get("ent",d.get("iid"))
        # These events often contain no iid. In w13 do not guess which clone
        # shares a root name: exact polygons/distances remain authoritative.
        if owner is None:
            parent=source.rsplit("/",1)[0].rsplit("/",1)[-1]
            matches={e.get("iid") for e in s.get("ents",())
                     if any(c.get("name")==parent and c.get("kind")=="box" and c.get("layer")==11
                            for c in e.get("colliders",()))}
            if len(matches)==1:owner=next(iter(matches))
            elif unique_type:owner=iid
        owner_known = owner == iid
        out.append({"part":part,"owner_matches":owner_known,"owner_ambiguous":owner is None,
                    "kind":ev["k"],"source":source,"data":d})
    return out


def query_support(support, boxes, tk, *, owners=None):
    from ssbot.combat.forum_planner import ForumPlanner
    from ssbot.combat.forum_v2 import BOUNDS_HALF
    planner=SimpleNamespace(cfg=SimpleNamespace(max_points=2))
    f=SimpleNamespace(fc=SimpleNamespace(half=BOUNDS_HALF))
    query=(lambda x,y:support.occupied(x,y,tk)) if owners is None else (
           lambda x,y:support.occupied_only(x,y,tk,owners))
    return ForumPlanner._contacts_fn(planner,f,boxes[None],tk,np.zeros((1,len(tk)),bool),query)[0]


def support_components(trk, iid, samples, margin):
    from ssbot.combat import attack_range as ar, forum_v2 as v2
    tk,e,inst=trk.now[iid];tab=trk.tables[tk]
    if inst is None or inst.fam!="CC_SLAM": raise ValueError("origin is not a started CC_SLAM")
    base=v2.RangeSupport.build(trk,samples=tuple(samples),focus=iid)
    core=v2.LayerSupport(base.cv,base.samples)
    zero=v2.LayerSupport(base.cv,base.samples)
    phase={name:v2.LayerSupport(base.cv,base.samples) for name in ("Slam 1","Slam 2","other")}
    if v2.MARGIN_MODE!="focus" or abs(v2.FOCUS_M-margin)>1e-9:
        raise ValueError("audit requires canonical focus margin 0.5")
    tp=tab.templates[("CC_SLAM","main")]
    age=ar.bin_of(trk.T-inst.t0)
    current=inst.states[-1];rank=tp.order.get(current,-1)
    for si,k in enumerate(samples):
        est=trk.estimate(iid,k)
        if est.core is None: raise ValueError("core separation is disabled")
        c,ix,iy=v2.coarse(est.core,tab.cell,base.cv.cell)
        core.add_raw(si,iid,c,ix,iy,margin,None)
        zero.add_raw(si,iid,c,ix,iy,0.,None)
        bb=min(max(age+k,0),tp.nb-1)
        px,py=tab.position(tp,age+k,(inst.x0,inst.y0),inst.s,inst.hero_du,"CC_SLAM")
        qx,qy=tab.position(tp,age,(inst.x0,inst.y0),inst.s,inst.hero_du,"CC_SLAM")
        px=min(max(float(e["pos"][0])+px-qx,tab.walls[0]),tab.walls[1])
        py=float(e["pos"][1])+py-qy
        parts=[(st,sh) for st,sh in tp.sst[bb].items() if tp.order.get(st,1<<30)>=rank]
        for st,(sh,iu,iv) in parts:
            mask=ar.place_shape(sh,iu,iv,px,py,inst.s,tab.cell)
            c,x,y=v2.coarse(mask,tab.cell,base.cv.cell)
            phase[st if st in phase else "other"].add_raw(si,iid,c,x,y,margin,None)
    for layer in (core,zero,*phase.values()):layer.finish()
    return base,core,zero,phase


def audit_case(case, tab):
    from ssbot.combat import attack_range as ar, forum_v2 as v2, forum_knife as fk
    from ssbot.record.recorder import RecordingReader
    fa,iid=int(case["fa"]),int(case["iid"])
    origin=fa+1;hit=fa+int(case["hit_k"]);last=max(origin+70,hit+24)
    rr=RecordingReader(case["recording"])
    raw=list(rr.states(origin-180,last,keys=("hero","ents","ev","dt","udt","fs")))
    frames={int(s["f"]):s for s in raw}
    if not all(f in frames for f in range(origin-1,last+1)):raise ValueError("raw STATE gap")
    trk=ar.RangeTracker(tables={tab.spec.type_key:tab})
    for s in raw:
        if s["f"]<=origin:trk.feed(s)
    if iid not in trk.now: raise ValueError("target absent at origin")
    inst=trk.now[iid][2]
    if inst is None or inst.fam!="CC_SLAM":raise ValueError("wrong family at origin")
    length=last-origin
    sparse=tuple(v2.SAMPLE_KS)+(length,)
    sparse=tuple(sorted(set(sparse)))
    dense=tuple(range(max(sparse)+1))
    m=.5
    base,core,zero,phase=support_components(trk,iid,sparse,m)
    db,dc,dz,dp=support_components(trk,iid,dense,m)
    boxes=np.array([frames[f]["hero"]["box"] for f in range(origin,last+1)])
    nominal=np.arange(len(boxes))*ar.FT
    game=np.r_[0.,np.cumsum([float(frames[f]["dt"]) for f in range(origin+1,last+1)])]
    clock=fk.safety_forecast(v2.V2Forecast(SimpleNamespace(fc=None),base),length,slam_iid=iid)
    flags={"knife_clock":query_support(clock.rs,boxes,nominal,owners=[iid]),
           "target_sparse":query_support(base,boxes,nominal,owners=[iid]),
           "core_sparse":query_support(core,boxes,nominal),"core_dense":query_support(dc,boxes,nominal),
           "core_dense_swept":query_support(dc,boxes,nominal)|query_support(dc,boxes,np.maximum(nominal-ar.FT,0)),
           "core_dense_game_clock":query_support(dc,boxes,game),
           "core_zero_sparse":query_support(zero,boxes,nominal),"core_zero_dense":query_support(dz,boxes,nominal)}
    for st,p in phase.items():flags["sparse_state_"+st]=query_support(p,boxes,nominal)
    for st,p in dp.items():flags["dense_state_"+st]=query_support(p,boxes,nominal)
    rows=[]
    for k,f in enumerate(range(origin,last+1)):
        s=frames[f];h=s["hero"]
        if not isinstance(s.get("fs"),(int,float)) or s["fs"]<0:raise ValueError("invalid physics count")
        geo=real_distances(s,iid)
        same=[e for e in s.get("ents",()) if e.get("type_key")==tab.spec.type_key and not e.get("is_dead")]
        calls=contacts(s,iid,len(same)==1)
        counter=h["cstate_int"][1]
        rows.append({"f":f,"k":k,"game_k":float(game[k]*60),"fs":s["fs"],"dt":s["dt"],
                     "pogo_counter":counter,"post_protection":f>hit and counter==0,
                     "health":h.get("health"),"hero_box":boxes[k].tolist(),"geometry":geo,"calls":calls,
                     "hp_events":[e for e in s.get("ev",()) if e.get("k")=="hp"],
                     "forecast":{name:bool(values[k]) for name,values in flags.items()}})
    for k,row in enumerate(rows):
        neighborhood=rows[max(0,k-1):min(len(rows),k+2)]
        known=all(x["geometry"] is not None and x["geometry"]["complete_for_clear_label"] for x in neighborhood)
        distances=[p["hurtbox_u"] for x in neighborhood if x["geometry"] is not None
                   for p in x["geometry"]["parts"].values() if p["hurtbox_u"] is not None]
        has_call=any(c["owner_matches"] or c["owner_ambiguous"] for x in neighborhood for c in x["calls"])
        row["strong_clear_1u"] = bool(known and (not distances or min(distances)>1.) and not has_call)
    return {"episode":case["ep"],"wave":case["wave"],"iid":iid,"origin":origin,"hit":hit,
            "age_at_origin":(trk.T-inst.t0)*60,"forecast_backend":"V2 RangeSupport/attack_range",
            "scope":"target-only CC_SLAM, focus margin 0.5; w13 is component isolation, not full-world safety",
            "frozen_or_slow_frames":sum(r["dt"]<.01 for r in rows),
            "knife_clock":clock.rs.knife_slam_clock,"rows":rows}


def summarize(results):
    """Descriptive development counts; neither independent trials nor A/A inference."""
    out={}
    good=[r for r in results if r["complete"]]
    for group in ("all","w7","w13","normal","freeze_or_slow"):
        cases=[c for c in good if group=="all" or c["wave"]==group
               or (group=="normal" and not c["frozen_or_slow_frames"])
               or (group=="freeze_or_slow" and c["frozen_or_slow_frames"])]
        rows=[(c,r) for c in cases for r in c["rows"]]
        strong=[(c,r) for c,r in rows if r["post_protection"] and r["strong_clear_1u"]]
        callbacks=[(c,r) for c,r in rows if any(e["owner_matches"] for e in r["calls"])]
        keys=next(iter(good))["rows"][0]["forecast"] if good else ()
        out[group]={"cases":len(cases),"post_protection_frames":sum(r["post_protection"] for c,r in rows),
                    "strong_clear_post_protection_frames":len(strong),
                    "matched_callback_frames":len(callbacks),"queries":{}}
        for key in keys:
            flagged=[(c,r) for c,r in strong if r["forecast"][key]]
            out[group]["queries"][key]={"strong_clear_flagged_frames":len(flagged),
                "strong_clear_flagged_cases":len({c["origin"] for c,r in flagged}),
                "matched_callback_frames_recalled":sum(r["forecast"][key] for c,r in callbacks),
                "callback_parts_recalled":{part:{"total":sum(any(e["owner_matches"] and e["part"]==part for e in r["calls"]) for c,r in callbacks),
                    "recalled":sum(r["forecast"][key] and any(e["owner_matches"] and e["part"]==part for e in r["calls"]) for c,r in callbacks)} for part in PARTS}}
    return out


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases",type=Path,required=True);ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--e-cores-idle",action="store_true")
    a=ap.parse_args(argv)
    if a.e_cores_idle:
        import psutil
        p=psutil.Process();p.cpu_affinity(list(range(16,32)));p.nice(psutil.IDLE_PRIORITY_CLASS)
        assert p.cpu_affinity()==list(range(16,32)) and p.nice()==psutil.IDLE_PRIORITY_CLASS
    if a.out.exists():raise FileExistsError(a.out)
    from ssbot.combat import attack_range as ar
    sp=ar.SPECS["Song Heavy Sentry"];path=ar.table_path(sp);tab=ar.load_table(path,sp)
    cases=list(csv.DictReader(a.cases.read_text(encoding="utf-8-sig").splitlines()))
    results=[]
    for i,case in enumerate(cases):
        try:r=audit_case(case,tab);r["complete"]=True
        except (ValueError,KeyError,IndexError) as exc:r={"episode":case["ep"],"complete":False,"error":str(exc)}
        results.append(r);print(json.dumps({"case":i+1,**{k:v for k,v in r.items() if k!="rows"}}),flush=True)
    from ssbot.combat import forum_knife as fk, forum_v2 as v2
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    tp=tab.templates[("CC_SLAM","main")]
    state_bins={st:[min(i for i,x in enumerate(tp.sst) if st in x),
                    max(i for i,x in enumerate(tp.sst) if st in x)] for st in tp.order}
    report={"scope":__doc__,"runtime_promoted":False,
      "cases_sha256":sha(a.cases),"knife_source_sha256":sha(fk.__file__),
      "shared_sources_sha256":{Path(m.__file__).name:sha(m.__file__) for m in (ar,v2)},
      "template":{"instances":tp.n,"state_bins":state_bins,"exact_shape_names":list(tab.meta.get("shapes",{})),
                  "note":"Empty shapes means attack_range_build.poly_of used AABB fallback; no polygon replacement certified here."},"cases":len(results),"complete":sum(r["complete"] for r in results),
      "notes":["No contact call does not prove no contact; use polygon distance as well.",
               "State-specific forecast rasters include that state's body and arc together; they are not collider channels.",
               "Slam 1 calls may appear a frame after its exported polygon turns off; +/-1 frame is used only for truth labels.",
               "A strong clear diagnostic requires >1u canonical-hurtbox distance in all three adjacent frames.",
               "No callbacks without iid are assigned to one of two Clappers by name alone."],
      "source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      "table_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
      "summary":summarize(results),"results":results}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("x",encoding="utf-8") as stream:json.dump(report,stream,indent=1,allow_nan=False)
    return 0 if report["complete"]==len(cases) else 2


if __name__=="__main__":raise SystemExit(main())
