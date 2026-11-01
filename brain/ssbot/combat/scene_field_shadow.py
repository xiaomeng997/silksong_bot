"""Default-off selected-path observation of the independent ground aim field.

No key owner, rollout, prediction, ranking or safety filter. Existing tracker
facts and the already chosen nominal path are read once; only a bounded summary
is returned to measurement. Ground CC_JUMP_CAST/two-Clapper scope only.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from ssbot.combat import scene_field_aim as aim

@dataclass(frozen=True)
class ShadowConfig:
    grid_step_u: float=1.
    space_cap_u: float=16.
    ground_tolerance_u: float=.05
    max_samples: int=8


def native_view(trk,pend,ft):
    if pend is None:return {'status':'insufficient_coverage','reason':'pending_unknown'}
    if len(pend)!=1:return {'status':'insufficient_coverage','reason':'no_pending' if not pend else 'multiple_pending'}
    p=pend[0]
    if p.get('name')!='CC_JUMP_CAST':return {'status':'insufficient_coverage','reason':'unsupported_move'}
    rows={int(i):(e,inst) for i,(tk,e,inst) in trk.now.items() if tk=='Song Heavy Sentry'}
    if len(rows)!=2:return {'status':'insufficient_coverage','reason':'not_two_clappers'}
    ci=int(p['iid'])
    if ci not in rows:return {'status':'insufficient_coverage','reason':'missing_caster'}
    inst=rows[ci][1]
    if inst is None or inst.fam!='CC_JUMP_CAST':return {'status':'insufficient_coverage','reason':'unsupported_instance'}
    if inst.dec is not None:return {'status':'insufficient_coverage','reason':'decided'}
    def row(i):
        e=rows[i][0];pos=e['pos'];box=None
        for c in e.get('colliders') or e.get('cols') or ():
            v=c.get('verts_world')
            if c.get('kind')=='box' and str(c.get('name','')).startswith('Song Heavy Sentry') and v:
                if c.get('enabled') is not True:return None
                box=[min(v[0::2]),min(v[1::2]),max(v[0::2]),max(v[1::2])];break
        if box is None:return None
        return {'iid':i,'root':[float(pos[0]),float(pos[1])],'body_box':[float(x) for x in box]}
    caster=row(ci);other=row(next(i for i in rows if i!=ci))
    if caster is None or other is None:return {'status':'insufficient_coverage','reason':'body_geometry_unknown'}
    if any(abs(float(p[k])-caster['root'][j])>1e-9 for j,k in enumerate(('x','y'))):
        raise ValueError('pending anchor differs from current caster root')
    return {'caster':caster,'other':other,'age_frames':(float(trk.T)-float(inst.t0))/ft,
            'pending':{'iid':ci,'move':'CC_JUMP_CAST','decision_window_frames':[int(p['d_lo']),int(p['d_hi'])]}}


def query_aim(field,points,consts,cfg=ShadowConfig()):
    """Same whole-grid lookup for any route. No predictor is called here.

    points=(hurtbox-centre x,y,seconds after tracker origin). A pre-window point
    needs a separate holding witness and receives no bonus; a late endpoint
    cannot change the past aim. Nearest-cell values are soft approximations.
    """
    if field.get('status')!='ok':return []
    gx=field['fields']['grid_hx'];lo,hi=field['time']['remaining_s'];cy=sum(consts.standing_box_y)*.5
    out=[]
    for x,y,t in points:
        finite=np.isfinite([x,y,t])
        row={'centre':[float(x) if finite[0] else None,float(y) if finite[1] else None],
             'after_tracker_s':float(t) if finite[2] else None,'known':False,'bonus':0.}
        if not finite.all() or x<gx[0] or x>gx[-1]:row['reason']='outside_or_unknown'
        elif abs(y-cy)>cfg.ground_tolerance_u:row['reason']='ground_scope_only'
        elif t<lo-1e-10:row['reason']='before_window_requires_hold'
        elif t>hi+1e-10:row['reason']='after_decision_window'
        else:
            i=int(np.argmin(abs(gx-x)))
            if field['flags']['no_high_value'][i]:row['reason']='unsupported_cell'
            else:
                f=field['fields'];left=float(f['free_left_minus_other_body'][i]);right=float(f['free_right_minus_other_body'][i])
                row.update(known=True,reason='conditional_decision_position',grid_x=float(gx[i]),
                           free_left_u=left,free_right_u=right,landing_x=float(f['x_land'][i]),
                           bonus=min(max(left,right,0.)/cfg.space_cap_u,1.))
        out.append(row)
    return out


class SceneFieldShadow:
    def __init__(self,rules,consts,cfg=ShadowConfig()):
        if cfg.grid_step_u<=0 or cfg.space_cap_u<=0 or cfg.max_samples<1:raise ValueError('invalid shadow configuration')
        self.rules=rules;self.consts=consts;self.cfg=cfg
        x0=math.ceil((consts.walls[0]+consts.hero_half[0])/.5)*.5
        x1=math.floor((consts.walls[1]-consts.hero_half[0])/.5)*.5
        self.grid=np.arange(x0,x1+1e-9,cfg.grid_step_u);self.grid.setflags(write=False)

    @classmethod
    def for_forum(cls,arena_x):
        from ssbot.combat import attack_range as ar,forum_v2,jump_behind
        from ssbot.combat.are_types import clapper
        from ssbot.core import forum
        from ssbot.knowledge import hitbox_tables,forum_products
        hazard=next(h for h in clapper.SPEC.hazards if h.name=='rune slam')
        k=aim.Constants(walls=(forum.WALL_L,forum.WALL_R),hero_half=tuple(hitbox_tables.HERO_HALF_U),
            standing_box_y=tuple(forum_products.FLOOR_Y),rune_slam_r=float(hazard.radius),
            du_left_right=tuple(hazard.du_by_face),ground_centre_y=3.34,ft=ar.FT,
            decision_s=tuple(forum_v2.DECISION_S['CC_JUMP_CAST']),jump_gain=clapper.JUMP_GAIN,
            jump_short=clapper.JUMP_SHORT,jump_vx_max=clapper.JUMP_VX_MAX,
            wall_zone=tuple(clapper.WALL_ZONE),arena_x=tuple(arena_x))
        return cls(aim.RuleCallbacks(clapper.jump_rule,clapper.jump_branch,bool(jump_behind.WALL_PUSH)),k)

    def inspect(self,trk,pend,path,*,frame,origin_frame,k_shift,fresh=True):
        # No-pending ticks do not allocate a record or build a field.
        if not pend:return None
        base={'schema':1,'policy_frame':int(frame),'origin_frame':int(origin_frame),
              'source':'selected_planner_path_before_scripts','applied_to_ranking':False}
        if not fresh:return {**base,'status':'stale_result'}
        view=native_view(trk,pend,self.consts.ft)
        if view.get('status')=='insufficient_coverage':return {**base,'status':view['reason']}
        field=aim.build_aim(view,self.grid,self.rules,self.consts)
        if field['status']!='ok':return {**base,'status':field['reason']}
        base.update(window_s=field['time']['remaining_s'],grid_points=len(self.grid),
                    supported_grid_points=int((~field['flags']['no_high_value']).sum()),
                    space_cap_u=self.cfg.space_cap_u)
        if path is None:return {**base,'status':'no_path'}
        box=np.asarray(path,float)
        if box.ndim!=2 or box.shape[1]!=4 or not len(box):raise ValueError('expected a nonempty [T,4] nominal path')
        shift=int(k_shift)
        if shift<0:raise ValueError('negative tracker/planner shift')
        lo,hi=view['pending']['decision_window_frames'];a=lo+shift;b=hi+shift
        if a>=len(box):return {**base,'status':'beyond_row'}
        end=min(b,len(box)-1);js=list(range(a,end+1));take=js[:self.cfg.max_samples]
        pts=[[(box[j,0]+box[j,2])*.5,(box[j,1]+box[j,3])*.5,(j-shift)*self.consts.ft] for j in take]
        samples=query_aim(field,pts,self.consts,self.cfg)
        for j,row in zip(take,samples):row['planner_frame']=j
        return {**base,'status':'sampled','window_truncated':end<b,'production_bins':len(js),
                'omitted_bins':len(js)-len(take),'covered_samples':sum(r['known'] for r in samples),'samples':samples}
