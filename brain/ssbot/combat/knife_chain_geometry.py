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
            self._owners[key]=(rs,rs._stack_of(lambda owner:owner==iid))
        return rs.occ_stack_b(self._owners[key][1],x,y,tk,{iid})

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

    def _query(self,path,limit,*,external_only=False):
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
        contacts=[];covered=np.zeros(length+1,bool)
        for iid in sorted(owners):
            haz=np.asarray(rs.occupied_hazards(x,y,tk,{iid})).any(axis=0)&~inv
            total=np.asarray(self._owner_occupancy(rs,x,y,tk,iid)).any(axis=0)&~inv
            covered|=total|haz
            for k in np.flatnonzero(haz):contacts.append(PathContact(path.origin+int(k),iid,"delayed"))
            if external_only and iid==self.move.target_iid:continue
            kind="move" if getattr(getattr(rs.trk,"now",{}).get(iid,(None,None,None))[2],"fam",None) else "body"
            label=self.move if same and iid==self.move.target_iid else None
            for k in np.flatnonzero(total&~haz):contacts.append(PathContact(path.origin+int(k),iid,kind,label))
        unknown=np.asarray(rs.occupied(x,y,tk)).any(axis=0)&~inv&~covered
        for k in np.flatnonzero(unknown):contacts.append(PathContact(path.origin+int(k),None,"other"))
        return ContactScan(self.ref(path),path.origin,path.origin+length,tuple(contacts),
                           "RangeSupport owner/hazard layers; current tracker instance; bounded sweep")

    @staticmethod
    def _frame_time(rs):
        # RangeSupport's sampling time is FT, independently of the hero jitter.
        from .attack_range import FT
        return FT

    def scan(self,path,limit=None):
        return self._query(path,len(path.commands) if limit is None else limit)

    def preflight(self,path):
        """Only rejects OTHER enemies / all delayed hazards on a modeled future.

        Used during approach, before the actual strike guard exists. No returned
        value can grant a target move admission or select the future strike.
        """
        return self._query(path,len(path.commands),external_only=True)

    @staticmethod
    def ref(path):
        return f"b2:{path.origin}:{path.stage}:{path.through}:{id(path)}"
