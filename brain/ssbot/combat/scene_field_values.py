"""Optional endpoint utility from one pinned scene-field snapshot.

The egress component has a fixed 0..1 scale. The illustrated total with an
unknown room component is deliberately unused. This utility changes no path
safety or hit counts. Unsupported/air endpoints get no bonus and remain logged
as unknown, not as a safety result. Model endpoint state selects capability.
"""
from __future__ import annotations
from collections import Counter
import math
import time
from types import SimpleNamespace
import numpy as np
from ssbot.knowledge import kinematics as K


class SceneFieldValues:
    def __init__(self, field, *, now_s, k_shift, frame_time, abilities, weight_hits=1., frame=None):
        if not all(math.isfinite(v) for v in [now_s,frame_time,weight_hits]) or frame_time<=0 or weight_hits<0:
            raise ValueError('invalid scene value clock/weight')
        if k_shift<0:raise ValueError('negative scene-value origin shift')
        self.field,self.now,self.shift,self.ft=field,float(now_s),int(k_shift),float(frame_time)
        self.abilities,self.weight_hits,self.frame=int(abilities),float(weight_hits),frame
        self.last=None
        self.last_points=self.last_layers=None

    def score_rollout(self, rollout):
        started=time.perf_counter()
        box=np.asarray(rollout.box);flags=np.asarray(rollout.flags);mode=np.asarray(rollout.mode);final=np.asarray(rollout.final)
        if box.ndim!=3 or box.shape[2]!=4 or final.shape!=(K.K,len(box)):
            raise ValueError('endpoint rollout has inconsistent shape')
        n,t,_=box.shape
        if flags.shape!=(n,t) or mode.shape!=(n,t):raise ValueError('endpoint flags/mode have inconsistent shape')
        values=np.zeros(n);known=np.zeros(n,bool)
        good=(flags[:,-1]&K.F_GROUND)!=0
        normal=mode[:,-1]==K.M_NORMAL
        # Ground sprint already supplies ground translation. Use the base
        # movement layer, without claiming immediate jump/dash cancellation.
        good &= normal | (mode[:,-1]==K.M_SPRINT)
        good &= np.isfinite(final).all(axis=0)
        jump=good & normal & (final[K.JHELD]<=0)
        dash=good & normal & (final[K.DASH_CD]<=0) & bool(self.abilities&K.AB_DASH)
        layers=np.full(n,'ground_run_wait',object)
        layers[jump]='ground_jump_ready';layers[dash]='ground_dash_ready';layers[jump&dash]='ground_jump_dash_ready'
        horizon=(t-1-self.shift)*self.ft
        points=np.column_stack(((box[:,-1,0]+box[:,-1,2])*.5,(box[:,-1,1]+box[:,-1,3])*.5,np.full(n,self.now+horizon)))
        self.last_points=points
        self.last_layers=np.where(good,layers,None)
        self.last_points.setflags(write=False);self.last_layers.setflags(write=False)
        reasons=Counter({'endpoint_mode_or_air_unknown':int((~good).sum())})
        for layer in np.unique(layers[good]):
            use=np.flatnonzero(good & (layers==layer))
            v,k,r=self.field.query(points[use],world='nominal',layer=str(layer),hyp='bounded_hold',component='egress')
            if not np.isfinite(v[k]).all():raise ValueError('known endpoint utility is nonfinite')
            values[use]=np.where(k,np.clip(v,0.,1.),0.)
            known[use]=k;reasons.update(map(str,r))
        self.last={'schema':1,'frame':self.frame,'component':'egress','world':'nominal','hypothesis':'bounded_hold',
                   'snapshot_id':self.field.meta['identity'][:16],'snapshot_origin_s':float(self.field.meta['t_origin_s']),
                   'weight_hits':self.weight_hits,'horizon_from_tracker_s':float(horizon),'rows':n,'known_rows':int(known.sum()),
                   'layers':{str(k):int((good&(layers==k)).sum()) for k in np.unique(layers[good])},
                   'reasons':dict(reasons),'known_value_range':[float(values[known].min()),float(values[known].max())] if known.any() else None,
                   'query_ms':(time.perf_counter()-started)*1000.,'path_safety_certified':False}
        return values,known

    def path_bonus(self, path, prefs):
        state=np.asarray(path.states)
        if state.ndim!=2 or state.shape[0]!=K.K:raise ValueError('path endpoint state unavailable')
        ro=SimpleNamespace(box=np.asarray(path.box)[None],flags=np.asarray(path.flags)[None],
                           mode=state[K.MODE][None],final=state[:,-1,None])
        value,known=self.score_rollout(ro)
        return float(value[0]*self.weight_hits*prefs.weights.get('hit',10.)) if known[0] else 0.
