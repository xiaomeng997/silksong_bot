"""Validate the knife contact predictor from fa+1 on 34 development events.

Recorded latched commands are the fixed input, not future knowledge available
online. Hero and target predictions use only history through the origin; raw
future STATEs are read separately as truth. No held-out or A/A inputs.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import numpy as np


def contact_gate(sw, cc, robust, controls, horizon, length, post_frames, free_min=10):
    sw,cc,robust,controls=map(np.asarray,(sw,cc,robust,controls))
    if not len(cc) or not (sw.shape==cc.shape==robust.shape==controls.shape):
        raise ValueError("missing or mismatched contact outcomes")
    return bool(robust.all() and (cc>horizon).all() and (cc<length-post_frames).all()
                and (sw-controls>=free_min).all())


def real_down_hits(frames,iid):
    return sorted({int(ev.get("f",s["f"])) for s in frames for ev in s.get("ev",())
                   if ev.get("k")=="hit" and ev.get("d",{}).get("ent")==iid
                   and "Down" in str(ev.get("d",{}).get("src",""))})


def clock_lanes(base,commands,params,terrain):
    """Expose every existing post-hook BOUNDS clock lane, not only nominal."""
    from ssbot.knowledge import kinematics as km
    nv=len(km.BOUNDS);n=len(base.hooks);length=len(commands)+1
    arrays={name:np.repeat(getattr(base,name)[:,None],nv,axis=1).copy() for name in ("box","mode","flags")}
    cache={}
    for q,c in enumerate(base.control_frames):
        c=int(c);st=base.control_states[q];key=(c,st.tobytes())
        if key not in cache:
            cache[key]=km.rollout(st,commands[None,c:],params,terrain,variants="bounds",lanes=True,threads=4)
        ro=cache[key]
        for name in arrays:
            arrays[name][q,:,c+1:]=getattr(ro,"var_"+name)[0,:,1:]
    for name,values in arrays.items():
        if not np.array_equal(values[:,0],getattr(base,name)):
            raise ValueError("nominal lane changed during clock expansion: "+name)
    return SimpleNamespace(**{name:values.reshape((n*nv,length)+values.shape[3:]) for name,values in arrays.items()},
            hooks=[h for h in base.hooks for _ in range(nv)],control_frames=np.repeat(base.control_frames,nv),
            hook_outcomes=n,clock_lanes=[x.name for x in km.BOUNDS])


def contact_interval(planner, rollout, commands, face, inner, outer, *, residual=.25):
    """Bound first contact, retaining every existing temporal shift and lane.

    Shrinking the target gives a sufficient contact despite hero residual;
    growing its outer animation envelope gives a necessary contact test.
    These are distinct: the guaranteed frame is not a pogo event time.
    """
    from ssbot.combat import dslash
    from ssbot.combat.forum_planner import ForumPlanner
    n=len(rollout.hooks);length=len(commands)
    masks=np.broadcast_to(commands,(n,length)).copy()
    inner=np.asarray(inner).copy();outer=np.asarray(outer).copy()
    if inner.shape!=outer.shape or inner.shape!=(length+1,4) or residual<0:
        raise ValueError("invalid contact bounds")
    inner[:,:2]+=residual;inner[:,2:]-=residual
    outer[:,:2]-=residual;outer[:,2:]+=residual
    first=[];last=[];starts=[]
    for shift in sorted({0,*map(int,dslash.CERT_SHIFTS)}):
        ix=np.clip(np.arange(length+1)+shift,0,length)
        hits=[]
        for body in (outer[ix],inner[ix]):
            valid=np.isfinite(body).all(axis=1)&(body[:,0]<body[:,2])&(body[:,1]<body[:,3])
            sw,cc,_,_=ForumPlanner._ds_hits(planner,rollout,masks,face,body[None],valid[None],
                np.ones(1,bool),np.full(n,2,np.int64),0.,np.zeros(0,np.int64))
            starts.append(sw);hits.append(cc)
        first.append(hits[0]);last.append(hits[1])
    first=np.stack(first);last=np.stack(last);starts=np.stack(starts)
    robust=(last>=0).all(axis=0)&(first>=0).all(axis=0)&(starts==starts[0]).all(axis=0)
    earliest=first.min(axis=0)
    latest=np.where((last>=0).all(axis=0),last.max(axis=0),-1)
    # A temporal unknown before the sufficient hit cannot certify first contact.
    for q,sw in enumerate(starts[0]):
        if sw<0 or not robust[q]:continue
        for shift in sorted({0,*map(int,dslash.CERT_SHIFTS)}):
            lo=max(0,int(sw)+int(planner.shapes[3][3,0])+shift)
            hi=min(length+1,int(latest[q])+shift+1)
            if not np.isfinite(outer[lo:hi]).all():robust[q]=False
    robust &= earliest<=latest
    return starts[0],earliest,latest,robust


def predict(history, origin, commands, iid, params, terrain, table, knowledge, shapes, state, *, coherent=False):
    if not history or any(int(s["f"])>origin for s in history) or int(history[-1]["f"])!=origin:
        raise ValueError("prediction history must stop at its origin")
    from ssbot.combat import attack_range as ar, forum_knife as fk
    from ssbot.combat.forum_planner import ForumPlanner
    from ssbot.combat import dslash
    from ssbot.map2 import clapper as cm, oldwin_claw as claw
    from ssbot.knowledge import kinematics as km
    from ssbot.tools.forum_knife_claw_audit import body_box
    trk=ar.RangeTracker(tables={table.spec.type_key:table})
    ct=cm.Tracker();game=0.
    for s in history:
        trk.feed(s);game+=float(s["dt"])*60;ct.feed(s,int(round(game)))
    obs=next(o for o in ct.obs() if o.iid==iid)
    if obs.st!="Slam Antic":raise ValueError("origin outside Slam Antic")
    seed=body_box(history[-1],iid)
    tbox=np.tile(seed,(1,len(commands)+1,1))
    ps=ForumPlanner._ds_move_paths(trk,[SimpleNamespace(iid=iid,hazard=False)],tbox)
    if 0 not in ps:raise ValueError("target move prediction unavailable")
    original=fk.slam_body_paths(obs,ps[0],knowledge)
    planner=SimpleNamespace(shapes=shapes)
    results=[];rollouts=[];families=0
    if coherent:
        base=claw.rollout(state,commands,params,terrain,original[0],iid,threads=4)
        shared=clock_lanes(base,commands,params,terrain)
        n=len(shared.hooks)
        sw,_,_,_=ForumPlanner._ds_hits(planner,shared,np.broadcast_to(commands,(n,len(commands))).copy(),
            1 if state[km.FACE]>=0 else -1,original[0][None],np.isfinite(original[0][:,0])[None],
            np.ones(1,bool),np.full(n,2,np.int64),0.,np.zeros(0,np.int64))
        if np.any(sw<0):raise ValueError("no supported down swing in a clock lane")
        limit=min(len(commands)+1,int(sw.max())+int(shapes[3][3,1])+int(max(abs(dslash.CERT_SHIFTS)))+1)
        groups={}
        inner_variants=fk.slam_body_variants(obs,ps[0],knowledge)
        outer_variants=fk.slam_body_variants(obs,ps[0],knowledge,outer=True)
        for (durations,body),(outer_durations,outer_body) in zip(inner_variants,outer_variants,strict=True):
            assert durations==outer_durations
            families+=1
            end=int(base.control_frames.max())+1
            if not np.array_equal(body[:end],original[0][:end],equal_nan=True):
                raise ValueError("coherent body changes hook; shared hook not certified")
            key=(body[:limit].tobytes(),outer_body[:limit].tobytes())
            if key not in groups:groups[key]=[body,[],outer_body]
            groups[key][1].append(durations)
        alternatives=list(groups.values())
    else:alternatives=[(b,[],b) for b in original]
    for body,timings,outer_body in alternatives:
        r=shared if coherent else clock_lanes(claw.rollout(state,commands,params,terrain,body,iid,threads=4),commands,params,terrain)
        rollouts.append(r)
        n=len(r.hooks)
        sw,cc,tt,robust=ForumPlanner._ds_hits(planner,r,np.broadcast_to(commands,(n,len(commands))).copy(),
            1 if state[km.FACE]>=0 else -1,body[None],np.isfinite(body[:,0])[None],np.ones(1,bool),
            np.full(n,2,np.int64),0.,dslash.CERT_SHIFTS)
        per_shift={};possible_contacts={}
        for shift in (-2,-1,0,1,2):
            _,jc,_,rr=ForumPlanner._ds_hits(planner,r,np.broadcast_to(commands,(n,len(commands))).copy(),
                1 if state[km.FACE]>=0 else -1,body[None],np.isfinite(body[:,0])[None],np.ones(1,bool),
                np.full(n,2,np.int64),0.,np.array([shift],np.int64))
            per_shift[str(shift)]=int(rr.sum())
            index=np.clip(np.arange(len(body))+shift,0,len(body)-1)
            shifted=body[index]
            _,possible,_,_=ForumPlanner._ds_hits(planner,r,np.broadcast_to(commands,(n,len(commands))).copy(),
                1 if state[km.FACE]>=0 else -1,shifted[None],np.isfinite(shifted[:,0])[None],np.ones(1,bool),
                np.full(n,2,np.int64),0.,np.zeros(0,np.int64))
            possible_contacts[str(shift)]=sorted(set(int(x) for x in possible if x>=0))
        bs,early,late,br=contact_interval(planner,r,commands,1 if state[km.FACE]>=0 else -1,body,outer_body)
        interval_gate=(contact_gate(bs,early,br,r.control_frames,37,len(commands),dslash.POST_F) and
                       contact_gate(bs,late,br,r.control_frames,37,len(commands),dslash.POST_F))
        results.append(dict(first_possible_contact=early.tolist(),last_guaranteed_contact=late.tolist(),
            residual_robust=br.tolist(),interval_gate=interval_gate,hero_residual_u=.25,
            duration_families=timings,hook_outcomes=r.hook_outcomes,clock_lanes=r.clock_lanes,per_shift_robust_counts=per_shift,possible_contact_frames=possible_contacts,
            body_probe=[dict(k=k,body=body[k].tolist() if np.isfinite(body[k]).all() else None,
                              hero_box_lo=r.box[:,k].min(axis=0).tolist(),hero_box_hi=r.box[:,k].max(axis=0).tolist()) for k in range(43,56)],
            start=sw.tolist(),contact=cc.tolist(),target=tt.tolist(),robust=robust.tolist(),
            controls=r.control_frames.tolist(),outcomes=n,
            gate=contact_gate(sw,cc,robust,r.control_frames,37,len(commands),dslash.POST_F),
            predicted_contact_range=None if np.any(cc<0) else [int(cc.min()),int(cc.max())]))
    return dict(origin_state=obs.st,origin_state_frame=obs.j,origin_target_hp=obs.hp,
                live_clappers=sum(x.hp>0 for x in ct.obs()),body_paths=len(alternatives),
                coherent_families=families,body_mode="coherent" if coherent else "pointwise_intersection",
                shape_source="Slam body intersection + current ARE displacement; no recorded future position",
                paths=results,gate=all(x["gate"] for x in results),
                interval_gate=coherent and all(x["interval_gate"] for x in results)),rollouts


def audit_case(case,params,table,knowledge,shapes,*,coherent=False):
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.reflex_val import _her_state,_terrain
    from ssbot.tools.forum_knife_claw_audit import require_frames
    from ssbot.knowledge import kinematics as km
    fa,iid=int(case["fa"]),int(case["iid"]);origin=fa+1
    end=origin+80
    rr=RecordingReader(case["recording"])
    raw=list(rr.states(origin-180,end,keys=("hero","ents","act","ev","dt","udt","fs")))
    frames=require_frames(raw,origin-180,end)
    commands=np.array([frames[f]["act"]["mask"] for f in range(origin+1,end+1)],np.int64)
    truth=real_down_hits([frames[f] for f in range(origin+1,end+1)],iid)
    listed=fa+int(case["hit_k"])
    if listed not in truth:raise ValueError("listed real contact not found")
    state=_her_state(rr,case["recording"],origin,params)
    if state is None:raise ValueError("unsupported initial state estimate")
    report=dict(episode=case["ep"],wave=case["wave"],iid=iid,origin=origin,listed_contact=listed,
                real_contacts=truth,real_contact_k=listed-origin,recording=case["recording"],
                future_slow_or_freeze_frames=[f for f in range(origin+1,listed+1) if frames[f]["dt"]<.01],
                input="recorded latched keys, conditional predictor audit",passed=False)
    try:
        pred,rollouts=predict([frames[f] for f in range(origin-180,origin+1)],origin,commands,iid,
                     params,_terrain(rr,case["recording"],params),table,knowledge,shapes,state,coherent=coherent)
        from ssbot.combat.forum_planner import ForumPlanner
        from ssbot.combat import dslash
        from ssbot.tools.forum_knife_claw_audit import body_box
        actual_body=[]
        for f in range(origin,end+1):
            try:actual_body.append(body_box(frames[f],iid))
            except ValueError:actual_body.append(np.full(4,np.nan))
        actual_body=np.asarray(actual_body)
        diag=[]
        for ro in rollouts:
            n=len(ro.hooks);pp=SimpleNamespace(shapes=shapes)
            sw,jj,_,rb=ForumPlanner._ds_hits(pp,ro,np.broadcast_to(commands,(n,len(commands))).copy(),
                1 if state[km.FACE]>=0 else -1,actual_body[None],np.isfinite(actual_body[:,0])[None],
                np.ones(1,bool),np.full(n,2,np.int64),0.,dslash.CERT_SHIFTS)
            diag.append(dict(scope="oracle target body only; diagnostic, NEVER acceptance evidence",
                robust_count=int(rb.sum()),outcomes=n,contact_range=[int(jj.min()),int(jj.max())]))
        report["diagnostic_recorded_target_body"]=diag
        ranges=[x["predicted_contact_range"] for x in pred["paths"]]
        covered=bool(all(x is not None and x[0]<=listed-origin<=x[1] for x in ranges))
        interval_covered=any(e>=0 and e<=listed-origin<=l for path in pred["paths"]
                             for e,l in zip(path["first_possible_contact"],path["last_guaranteed_contact"]))
        possible={j for path in pred["paths"] for js in path["possible_contact_frames"].values() for j in js}
        report.update(prediction=pred,real_contact_covered=covered,
            real_contact_in_residual_interval=interval_covered,
            real_contact_in_possible_timing_lanes=listed-origin in possible,
            possible_contact_range=None if not possible else [min(possible),max(possible)],
            current_encounter_hp_scope=case["wave"]=="w7" and pred["origin_target_hp"]>50 and pred["live_clappers"]==1,
            passed=pred["interval_gate"] and interval_covered,
            predicted_robust=bool(all(all(x["robust"]) for x in pred["paths"])))
    except (ValueError,KeyError,StopIteration) as exc:report["rejection"]=str(exc)
    return report


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases",type=Path,required=True)
    ap.add_argument("--arm-source",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--e-cores-idle",action="store_true")
    ap.add_argument("--coherent",action="store_true",help="preserve whole duration branches instead of a pointwise intersection")
    a=ap.parse_args(argv)
    if a.out.exists():raise FileExistsError(a.out)
    if a.e_cores_idle:
        import psutil
        p=psutil.Process();p.cpu_affinity(list(range(16,32)));p.nice(psutil.IDLE_PRIORITY_CLASS)
        assert p.cpu_affinity()==list(range(16,32)) and p.nice()==psutil.IDLE_PRIORITY_CLASS
    os.environ.update(json.loads(a.arm_source.read_text(encoding="utf-8"))["arm"])
    os.environ.update(NUMBA_NUM_THREADS="4",PYTHONDONTWRITEBYTECODE="1")
    from ssbot.combat import attack_range as ar
    from ssbot.combat.forum_planner import _shapes
    from ssbot.map2.envelope import load_params
    from ssbot.map2 import clapper as cm
    params=load_params(hero2=True);knowledge=cm.Know.load();shapes=_shapes("Wanderer")
    sp=ar.SPECS["Song Heavy Sentry"];table=ar.load_table(ar.table_path(sp),sp)
    cases=list(csv.DictReader(a.cases.read_text(encoding="utf-8-sig").splitlines()))
    results=[]
    for i,case in enumerate(cases):
        r=audit_case(case,params,table,knowledge,shapes,coherent=a.coherent);results.append(r)
        print(json.dumps(dict(case=i+1,origin=r["origin"],passed=r["passed"],
            robust=r.get("predicted_robust"),covered=r.get("real_contact_covered"),reason=r.get("rejection"))),flush=True)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    from ssbot.combat import forum_knife,forum_planner
    from ssbot.map2 import oldwin_claw
    from ssbot.knowledge import kinematics
    report=dict(scope=__doc__,body_mode="coherent" if a.coherent else "pointwise_intersection",runtime_promoted=False,cases=len(results),passed=sum(x["passed"] for x in results),
        modeled=sum("prediction" in x for x in results),robust=sum(x.get("predicted_robust",False) for x in results),
        dependency_sha256={m.__name__:sha(m.__file__) for m in (forum_knife,forum_planner,oldwin_claw,kinematics)},
        model_sha256={"attack_range":sha(ar.table_path(sp)),"clapper_m2":sha(cm.KNOW_PATH)},
        source_sha256=sha(__file__),case_sha256=sha(a.cases),arm_sha256=sha(a.arm_source),
        future_target_data_supplied=False,future_physics_clock_supplied=False,
        generated_fixed_keys_certified=False,heldout_opened=False,
        possible_timing_coverage=sum(x.get("real_contact_in_possible_timing_lanes",False) for x in results),
        current_encounter_hp_scope_cases=sum(x.get("current_encounter_hp_scope",False) for x in results),
        clock_domain="all nine existing BOUNDS lanes after each hook outcome",
        position_margin_contact_check="inner target eroded / outer animation envelope dilated by 0.25u; all temporal and clock lanes",
        interval_robust=sum(x.get("prediction",{}).get("interval_gate",False) for x in results),
        residual_interval_coverage=sum(x.get("real_contact_in_residual_interval",False) for x in results),
        results=results)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("x",encoding="utf-8") as stream:json.dump(report,stream,indent=1,allow_nan=False)
    return 0 if report["passed"]==len(cases) else 2


if __name__=="__main__":raise SystemExit(main())
