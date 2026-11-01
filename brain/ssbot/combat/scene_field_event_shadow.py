"""Default-off low-frequency observation of the locked-event ground field.

One complete field snapshot is shared by queries. This observer never calls a
predictor, changes a result, chooses keys or ranks actions. The sampled layer is
explicitly hypothetical; actual endpoint capability binding belongs to ranking.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from ssbot.combat import scene_field_events as E, scene_field_locked as L
from ssbot.combat.scene_field_grid import SceneFieldGrid
from ssbot.combat.scene_field_inputs import load_inputs


@lru_cache(maxsize=1)
def _startup_inputs():
    path = Path(__file__).resolve().parents[3] / 'knowledge/1.0.30000/scene_field/scene_field_inputs43.json'
    return load_inputs(path, E.Inputs)


@dataclass(frozen=True)
class EventShadowConfig:
    refresh_s: float = .25
    max_samples: int = 3
    layer: str = 'ground_run_wait'
    world: str = 'nominal'
    hypothesis: str = 'bounded_hold'


class SceneFieldEventShadow:
    def __init__(self, inputs, arenas, config=EventShadowConfig(), prepared=None, select=None):
        if config.max_samples < 1 or config.layer not in E.LAYERS:
            raise ValueError('invalid event shadow configuration')
        if config.world not in E.WORLDS or config.hypothesis not in E.HYPS:
            raise ValueError('unknown conditional world/hypothesis')
        self.inputs, self.arenas, self.cfg, self.prepared = inputs, arenas, config, prepared
        self.select = select
        self.cache = E.SceneFieldSetCache(config.refresh_s)
        self._last = self._key = None

    @classmethod
    def for_forum(cls, *, egress_only=False):
        from ssbot.core import forum as F
        arena = L.forum_arena(F.WALL_L, F.WALL_R, F.FLOOR_Y, F.DOME)
        inputs = _startup_inputs()
        E.warmup()  # Startup only; never first compile in inspect().
        select=E.Selection(worlds=('nominal',),hyps=('bounded_hold',),components=('egress',)) if egress_only else None
        return cls(inputs, {'Hang_04': arena}, prepared=E.prepare(inputs, arena=arena),select=select)

    def inspect(self, trk, state, pending, path, *, frame, origin_frame, k_shift, bombs, bombs_T, fresh=True):
        base = {'schema': 2, 'kind': 'locked_event_grid', 'policy_frame': int(frame),
                'origin_frame': int(origin_frame), 'applied_to_ranking': False,
                'source': 'selected_planner_path_before_scripts', 'world': self.cfg.world,
                'hypothesis': self.cfg.hypothesis, 'conditional_layer': self.cfg.layer,
                'actual_endpoint_capability_checked': False}
        if not fresh:
            return {**base, 'status': 'stale_result'}
        now = float(trk.T)
        if bombs_T is None or bombs is None:
            return {**base, 'status': 'small_runes_unknown'}
        if float(bombs_T) != now:
            return {**base, 'status': 'small_runes_stale'}
        view = L.locked_scene(trk, frame=frame, room=L.room_of_state(state), arenas=self.arenas,
                              bombs=bombs, bombs_complete=True, pend=pending)
        if view['status'] != 'ok':
            return {**base, 'status': view['reason']}
        if path is None:
            return {**base, 'status': 'no_path'}
        box = np.asarray(path, float)
        if box.ndim != 2 or box.shape[1] != 4 or not len(box):
            raise ValueError('expected a nonempty [T,4] nominal path')
        shift = int(k_shift)
        if shift < 0:
            raise ValueError('negative tracker/planner shift')
        if shift >= len(box):
            return {**base, 'status': 'beyond_row'}
        key = L.field_key(E.cache_key, view['scene'], view['lock'], E.Config(), self.inputs,select=self.select)
        started = time.perf_counter()
        fs, reason = L.field_for_tick(self.cache, E, view, self.inputs, SceneFieldGrid,
                                      E.Config(), prepared=self.prepared,select=self.select)
        build_ms = (time.perf_counter()-started)*1000.
        if fs is None:
            return {**base, 'status': reason}
        old, old_key = self._last, self._key
        rebuilt = fs is not old
        self._last, self._key = fs, key
        js = np.unique(np.linspace(shift, len(box)-1, min(self.cfg.max_samples, len(box)-shift), dtype=int))
        points = np.column_stack(((box[js,0]+box[js,2])*.5, (box[js,1]+box[js,3])*.5,
                                  now+(js-shift)/60.))
        args = dict(world=self.cfg.world, layer=self.cfg.layer, hyp=self.cfg.hypothesis)
        components = {c: fs.query(points, component=c, **args) for c in E.COMPONENTS}
        samples=[]
        for i,j in enumerate(js):
            row={'planner_frame':int(j), 'x':float(points[i,0]) if np.isfinite(points[i,0]) else None,
                 'y':float(points[i,1]) if np.isfinite(points[i,1]) else None,
                 'absolute_game_s':float(points[i,2]), 'components':{}}
            for c,(v,k,r) in components.items():
                row['components'][c]={'value':float(v[i]) if k[i] else None,'known':bool(k[i]),'reason':str(r[i])}
            samples.append(row)
        delta={}
        if rebuilt and old is not None and old_key==key:
            for c,(new,known,_) in components.items():
                prev,pk,_=old.query(points,component=c,**args)
                common=known & pk
                delta[c]={'common_samples':int(common.sum()),
                          'max_abs':float(np.max(np.abs(new[common]-prev[common]))) if common.any() else None}
        return {**base,'status':'sampled','refresh_s':self.cfg.refresh_s,'rebuilt':rebuilt,
                'build_or_cache_ms':build_ms,'snapshot_id':fs.meta['identity'][:16],
                'snapshot_origin_s':float(fs.meta['t_origin_s']),'snapshot_age_s':now-float(fs.meta['t_origin_s']),
                'grids':len(fs.grids),'lock_bin':view['lock']['lock_bin'],'move_bin':view['lock']['inst_t0_bin'],
                'room':view['lock']['room'],'weights_temporary':fs.meta['weights_TEMPORARY'],
                'cross_time_total_ranking_allowed':False,'refresh_delta':delta,'samples':samples}
