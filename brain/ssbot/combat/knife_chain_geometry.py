"""B2 path queries over the existing planner's source-separated RangeSupport.

Normal approach/post checks keep the target. Conditional strike checks tag only
its SAME currently observed CC_SLAM instance; its delayed hazards are always
separate. The approach preflight is rejection-only and never grants admission.
"""
from __future__ import annotations

from dataclasses import dataclass,field
import numpy as np
from ssbot.knowledge import kinematics as km
from .knife_chain_commitment import ContactScan, PathContact


class GeometryUnavailable(ValueError):
    pass


@dataclass
class B2Geometry:
    forecast: object
    origin: int
    move: object
    instance: object
    _fresh: dict=field(default_factory=dict,init=False,repr=False)
    _owners: dict=field(default_factory=dict,init=False,repr=False)

    def _owner_occupancy(self,rs,x,y,tk,iid):
        """Reuse one owner raster within this tick's immutable support snapshot.

        Every path still has fresh points, clock, sweep and protection. A new
        B2Geometry is made for every proposal; no positions/verdicts cross ticks.
        Adapters overriding occupied_only retain their own query semantics.
        """
        from .forum_v2 import LayerSupport
        if getattr(rs.occupied_only,"__func__",None) is not LayerSupport.occupied_only:
            return rs.occupied_only(x,y,tk,{iid})
        key=(id(rs),int(iid))
        if key not in self._owners:
            # Retain rs too: an id cannot be recycled within this query group.
            self._owners[key]=(rs,np.zeros(rs.stack.shape,bool),set())
        _,stack,filled=self._owners[key]
        # Dilate only the samples this query reads (LayerSupport.samples_read); a later query of this group fills
        # its own. The cells read are the whole owner stack's (Task 178 tick cost).
        need=rs.samples_read(tk)-filled
        if need:
            rs._stack_of(lambda owner:owner==iid,into=stack,samples=need)
            filled|=need
        return rs.occ_stack_b(stack,x,y,tk,{iid})

    def support(self, length, *, first=None):
        from .forum_v2 import RangeSupport, SAMPLE_KS
        rs=getattr(self.forecast,"rs",None)
        if rs is None or not hasattr(rs,"trk"):
            raise GeometryUnavailable("B2 needs the real RangeSupport/tracker")
        if first is not None:
            # Continuations query every physical-time template bin in their
            # actual window. A prior-bin closing shape at the left sparse knot
            # must not survive across the whole next sampling bracket.
            if not 0 <= first <= length:
                raise GeometryUnavailable("invalid exact continuation window")
            key=("frames",first,length)
            if key not in self._fresh:
                # The exact per-frame clock also holds inside a larger window.
                # Reuse its rasters, never a path's contacts/protection verdict.
                for window,support in self._fresh.items():
                    if (isinstance(window,tuple) and window[0]=="frames" and
                            window[1]<=first and length<=window[2]):
                        return support
                self._fresh[key]=RangeSupport.build(rs.trk,samples=tuple(range(first,length+1)),
                    canvas=rs.cv,margin_mode=rs.margin_mode,focus=getattr(rs,"focus_arg",rs.focus))
            return self._fresh[key]
        if rs.k_shift!=0 or length>rs.samples[-1]:
            # Admission is bound to THIS observed move, not a cached raster from
            # before its entry. Rebuild from the current tracker on reuse too.
            if length not in self._fresh:
                samples=tuple(sorted(set(SAMPLE_KS)|set(range(0,length+7,6))|{length}))
                self._fresh[length]=RangeSupport.build(rs.trk,samples=samples,margin_mode=rs.margin_mode,
                                      focus=getattr(rs,"focus_arg",rs.focus))
            rs=self._fresh[length]
        return rs

    def _walkers(self,rs,paths,spans,width,box=None,preludes=None):
        """combat.walk_rule (the person 11-13, quote 130): {iid: body contacts [len(paths), width]} of every other
        Clapper whose Idle / Walk body its walk rule covers on these routes (walk_rule.walker_x: not the target, no
        move instance); spans[i] = (first frame - origin, last frame index). Empty with SSBOT_FORUM_TWO_WALK_RULE=0.
        preludes[i] (Sol seq 359): what is known of her x before a path that starts after the origin (walk_rule.prelude_xs:
        the same candidate's earlier part, or a list of alternatives); None there: the path's own walk_prelude, else
        unknown (the walker may close over those frames: never a smaller interval than the whole candidate's)."""
        from . import walk_rule as wr
        trk=getattr(rs,"trk",None)
        if not wr.ENABLED or trk is None:return {}
        target=getattr(self.move,"target_iid",None)
        out={};hist=None;pre=None
        for iid in sorted(getattr(trk,"now",None) or {}):
            x0=wr.walker_x(trk,iid,target)
            if x0 is None:continue
            if hist is None:
                hist=wr.hero_history(trk)
                pre=[wr.gap_xs(self.origin,int(o),(preludes[i] if preludes is not None and preludes[i] is not None
                                                     else getattr(paths[i],"walk_prelude",None)))
                     for i,(o,_) in enumerate(spans)]
            out[iid]=wr.route_hits(x0,hist,paths,spans,width,box=box,preludes=pre)[0]
        return out

    def _query(self,path,limit,*,external_only=False,prelude=None):
        rs,length,x,y,tk,inv,owners,same=self._sweep(path,limit)
        walk=self._walkers(rs,[path],[(path.origin-self.origin,length)],length+1,preludes=[prelude])
        contacts=[];covered=np.zeros(length+1,bool)
        for iid in sorted(owners):
            haz=np.asarray(rs.occupied_hazards(x,y,tk,{iid})).any(axis=0)&~inv
            total=np.asarray(self._owner_occupancy(rs,x,y,tk,iid)).any(axis=0)&~inv
            covered|=total|haz
            for k in np.flatnonzero(haz):contacts.append(PathContact(path.origin+int(k),iid,"delayed"))
            if external_only and iid==self.move.target_iid:continue
            if iid in walk:
                # combat.walk_rule: the other Clapper's Idle / Walk body by its walk rule, not by the raster's growth
                # (the raster still covers its cells above: no "other" contact from them)
                for k in np.flatnonzero(walk[iid][0]&~inv&~haz):contacts.append(PathContact(path.origin+int(k),iid,"body"))
                continue
            kind="move" if getattr(getattr(rs.trk,"now",{}).get(iid,(None,None,None))[2],"fam",None) else "body"
            label=self.move if same and iid==self.move.target_iid else None
            for k in np.flatnonzero(total&~haz):contacts.append(PathContact(path.origin+int(k),iid,kind,label))
        unknown=np.asarray(rs.occupied(x,y,tk)).any(axis=0)&~inv&~covered
        for k in np.flatnonzero(unknown):contacts.append(PathContact(path.origin+int(k),None,"other"))
        return ContactScan(self.ref(path),path.origin,path.origin+length,tuple(contacts),
                           "RangeSupport owner/hazard layers; current tracker instance; bounded sweep"+self._walk_src(walk))

    @staticmethod
    def _walk_src(walk):
        return "; walk rule body: "+",".join(str(i) for i in sorted(walk)) if walk else ""

    def scan_delayed(self,path,limit=None):
        """The "delayed" contacts of scan(path, limit) alone, in its order (Task 182 seq 272: a waypoint Run's whole-route check):
        the same sweep, clock, protection, owners and support, each owner's delayed hazard layers only (its spawned hazards and
        its per-bomb small-rune forecast), none of the body / move / unknown occupancy rasters the step gate's full scan builds."""
        rs,length,x,y,tk,inv,owners,_=self._sweep(path,len(path.commands) if limit is None else limit)
        contacts=[]
        for iid in sorted(owners):
            haz=np.asarray(rs.occupied_hazards(x,y,tk,{iid})).any(axis=0)&~inv
            for k in np.flatnonzero(haz):contacts.append(PathContact(path.origin+int(k),iid,"delayed"))
        return ContactScan(self.ref(path),path.origin,path.origin+length,tuple(contacts),
                           "RangeSupport delayed hazard layers only; bounded sweep")

    def _sweep(self,path,limit):
        """_query's points: the support for the path's window, the bounded sweep of its box centres, their clock and protection,
        the owners to ask and whether the target maps to the tracked slam instance."""
        if path.origin<self.origin:raise GeometryUnavailable("path predates forecast origin")
        length=min(int(limit),len(path.box)-1)
        if length<0:raise GeometryUnavailable("empty path query")
        offset=path.origin-self.origin
        from . import observed_slam
        exact=path.stage=="continuation" and observed_slam.ENABLED
        rs=self.support(offset+length,first=offset) if exact else self.support(offset+length)
        bx=path.box[:length+1];c=.5*(bx[:,:2]+bx[:,2:])
        # Raster is already dilated by the standard hero box. Sweep long hook /
        # dash steps at the existing canvas resolution instead of teleporting.
        rows=[c]
        distance=np.linalg.norm(np.diff(c,axis=0),axis=1)
        n=int(np.ceil(distance.max(initial=0.)/rs.cv.cell))
        if n>32:raise GeometryUnavailable("nominal displacement exceeds bounded sweep")
        for j in range(1,max(n,1)):
            prev=np.vstack([c[:1],c[:-1]])
            rows.append(prev+(c-prev)*(j/max(n,1)))
        points=np.stack(rows)
        x=points[:,:,0];y=points[:,:,1]
        _,_,inside=rs.cv.index(x,y)
        if not np.asarray(inside).all():raise GeometryUnavailable("path leaves modeled canvas")
        tk=(np.arange(length+1)+offset)*self._frame_time(rs)
        inv=(path.check_flags[:length+1]&km.F_INVULN)!=0 if path.stage!="continuation" else (path.flags[:length+1]&km.F_INVULN)!=0
        owners=set(getattr(rs.trk,"now",{}))|set(getattr(rs.trk,"orphan_hazards",{}))|set(rs.haz_raw)
        owners|={int(p[0]) for parts in rs.raw.values() for p in parts}
        owners|={int(p[0]) for parts in rs.layers.values() for p in parts}
        if rs.bombs is not None:owners|={int(i) for i in rs.bombs[:,0]}
        current=getattr(rs.trk,"now",{}).get(self.move.target_iid)
        same=(current is not None and current[2] is self.instance and getattr(current[2],"fam",None)=="CC_SLAM")
        if path.stage=="commitment" and not same:
            raise GeometryUnavailable("h2 guard target no longer maps to the tracked slam instance")
        return rs,length,x,y,tk,inv,owners,same

    @staticmethod
    def _frame_time(rs):
        # RangeSupport's sampling time is FT, independently of the hero jitter.
        from .attack_range import FT
        return FT

    def scan(self,path,limit=None,*,prelude=None):
        """prelude (Sol seq 359): the same candidate's part before a path that starts after the origin (_walkers)."""
        return self._query(path,len(path.commands) if limit is None else limit,prelude=prelude)

    def scan_batch(self,paths,*,preludes=None):
        """[scan(p) for p in paths] with one raster pass per owner (Task 179 #308: a whole locked hook's ~100 variant
        rows and the continuations of its forced bounce, in one tick). Each path keeps its own origin, clock, sweep
        points (scan's rows; a column that did not move contributes its centre once, its other rows being exact copies
        of it), protection flags and the support scan(p) reads; continuations first build one exact per-frame window
        over all of them, which scan(p) reuses the same way. Contacts per path in scan's order; the first path scan(p)
        would refuse raises that refusal. preludes[i]: scan(p, prelude=...) of path i (Sol seq 359)."""
        if not paths:return []
        from . import observed_slam
        spans=[(p.origin-self.origin,min(len(p.commands),len(p.box)-1)) for p in paths]
        exact=[p.stage=="continuation" and observed_slam.ENABLED for p in paths]
        windows=[(o,n) for (o,n),e in zip(spans,exact) if e and o>=0 and n>=0]
        if windows:self.support(max(o+n for o,n in windows),first=min(o for o,_ in windows))
        groups,failed={},None
        for i,(p,(offset,length),e) in enumerate(zip(paths,spans,exact)):
            try:
                if p.origin<self.origin:raise GeometryUnavailable("path predates forecast origin")
                if length<0:raise GeometryUnavailable("empty path query")
                rs=self.support(offset+length,first=offset) if e else self.support(offset+length)
            except GeometryUnavailable as exc:
                failed=(i,exc);break       # scan(p) never reaches the later paths
            groups.setdefault(id(rs),(rs,[]))[1].append(i)
        built,refused=[],[]
        for rs,ids in groups.values():
            N=len(ids);L=np.array([spans[i][1]+1 for i in ids]);W=int(L.max())
            valid=np.arange(W)[None,:]<L[:,None]
            box=np.zeros((N,W,4));inv=np.zeros((N,W),bool)
            for g,i in enumerate(ids):
                rows=np.asarray(paths[i].box[:L[g]])
                if rows.dtype!=np.float64:raise ValueError("scan_batch takes float64 rows (scan's arithmetic)")
                box[g,:L[g]]=rows
                flags=paths[i].check_flags if paths[i].stage!="continuation" else paths[i].flags
                inv[g,:L[g]]=(np.asarray(flags[:L[g]])&km.F_INVULN)!=0
            c=.5*(box[...,:2]+box[...,2:]);prev=np.concatenate([c[:,:1],c[:,:-1]],axis=1)
            step=np.where(valid,np.linalg.norm(c-prev,axis=-1),0.)
            m=np.ones(N,np.int64)
            for g,i in enumerate(ids):
                n=int(np.ceil(step[g].max(initial=0.)/rs.cv.cell))
                if n>32:refused.append((i,0,"nominal displacement exceeds bounded sweep"));continue
                m[g]=max(n,1)
            # scan's sweep rows: the centre, then prev+(c-prev)*(j/m) for j=1..m-1 (equal to the centre where unmoved)
            moving=valid&(c!=prev).any(axis=-1)
            gi,ki=np.nonzero(valid);X=[c[gi,ki]];C=[gi*W+ki]
            for j in range(1,int(m.max())):
                gj,kj=np.nonzero(moving&(j<m)[:,None])
                X.append(prev[gj,kj]+(c[gj,kj]-prev[gj,kj])*(j/m[gj])[:,None]);C.append(gj*W+kj)
            X=np.concatenate(X);C=np.concatenate(C)
            _,_,inside=rs.cv.index(X[:,0],X[:,1])
            refused+=[(ids[int(g)],1,"path leaves modeled canvas") for g in np.unique(C[~np.asarray(inside)]//W)]
            current=getattr(rs.trk,"now",{}).get(self.move.target_iid)
            same=(current is not None and current[2] is self.instance and getattr(current[2],"fam",None)=="CC_SLAM")
            if not same:
                refused+=[(i,2,"h2 guard target no longer maps to the tracked slam instance")
                          for i in ids if paths[i].stage=="commitment"]
            tk=((np.arange(W)[None,:]+np.array([spans[i][0] for i in ids])[:,None])*self._frame_time(rs)).ravel()
            built.append((rs,X,C,tk[C],(inv|~valid).ravel(),ids,W,same,box))
        if refused:raise GeometryUnavailable(min(refused)[2])
        if failed is not None:raise failed[1]
        out=[None]*len(paths)
        for rs,X,C,T,off,ids,W,same,box in built:
            x,y=X[:,0],X[:,1]
            def columns(hit):
                col=np.zeros(len(ids)*W,bool);col[C[np.asarray(hit)]]=True;return col&~off
            owners=set(getattr(rs.trk,"now",{}))|set(getattr(rs.trk,"orphan_hazards",{}))|set(rs.haz_raw)
            owners|={int(p[0]) for parts in rs.raw.values() for p in parts}
            owners|={int(p[0]) for parts in rs.layers.values() for p in parts}
            if rs.bombs is not None:owners|={int(i) for i in rs.bombs[:,0]}
            contacts=[[] for _ in ids];covered=np.zeros(len(ids)*W,bool)
            walk=self._walkers(rs,[paths[i] for i in ids],[spans[i] for i in ids],W,box=box,
                               preludes=None if preludes is None else [preludes[i] for i in ids])
            for iid in sorted(owners):
                haz=columns(rs.occupied_hazards(x,y,T,{iid}))
                total=columns(self._owner_occupancy(rs,x,y,T,iid))
                covered|=total|haz
                kind="move" if getattr(getattr(rs.trk,"now",{}).get(iid,(None,None,None))[2],"fam",None) else "body"
                label=self.move if same and iid==self.move.target_iid else None
                for g,k in zip(*np.divmod(np.flatnonzero(haz),W)):
                    contacts[g].append(PathContact(paths[ids[g]].origin+int(k),iid,"delayed"))
                if iid in walk:
                    # combat.walk_rule: as scan (the other Clapper's Idle / Walk body by its walk rule)
                    for g,k in zip(*np.divmod(np.flatnonzero(walk[iid].ravel()&~off&~haz),W)):
                        contacts[g].append(PathContact(paths[ids[g]].origin+int(k),iid,"body"))
                    continue
                for g,k in zip(*np.divmod(np.flatnonzero(total&~haz),W)):
                    contacts[g].append(PathContact(paths[ids[g]].origin+int(k),iid,kind,label))
            for g,k in zip(*np.divmod(np.flatnonzero(columns(rs.occupied(x,y,T))&~covered),W)):
                contacts[g].append(PathContact(paths[ids[g]].origin+int(k),None,"other"))
            for g,i in enumerate(ids):
                o=paths[i].origin
                out[i]=ContactScan(self.ref(paths[i]),o,o+spans[i][1],tuple(contacts[g]),
                                   "RangeSupport owner/hazard layers; current tracker instance; bounded sweep"+self._walk_src(walk))
        return out

    def preflight(self,path,*,prelude=None):
        """Only rejects OTHER enemies / all delayed hazards on a modeled future.

        Used during approach, before the actual strike guard exists. No returned
        value can grant a target move admission or select the future strike.
        prelude: as scan's (Sol seq 359).
        """
        return self._query(path,len(path.commands),external_only=True,prelude=prelude)

    @staticmethod
    def ref(path):
        return f"b2:{path.origin}:{path.stage}:{path.through}:{id(path)}"
