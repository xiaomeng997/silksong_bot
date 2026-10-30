"""Prepacked single-lane calls into the EXISTING kinematics frame loop.

B2 interprets feedback every frame. Re-entering the public vector/shape/broadcast
wrapper each time is unnecessary; simulate remains the one physics authority.
No new movement rules, clock lanes, event timing or protected frames live here.
"""
from __future__ import annotations

import numpy as np
from numba import njit
from ssbot.knowledge import kinematics as km, kin_jit


@njit(cache=True, error_model="numpy")
def _one(start,mask,event,frames,unscaled,params,terrain):
    state=np.ascontiguousarray(start.reshape((start.size,1)))
    masks=np.full((1,frames),mask,np.int64)
    events=np.full((1,frames),event,np.int64)
    empty=np.zeros((0,0))
    udts=np.full((1,1),unscaled)
    ft=np.zeros(1);selector=np.zeros(1,np.int64)
    # This is the original nominal selector=0 path. alpha_margin is unused
    # for that selector; phase/bounds in the input state are not narrowed.
    return kin_jit.simulate(state,masks,events,empty,empty,udts,ft,selector,0.,params,terrain)


class NominalStepper:
    def __init__(self,params,terrain):
        # Fresh per compilation, so changes in weighted loadout / frame time /
        # HERO2 bits cannot hit a stale process-global parameter cache.
        self.params=params.vector()[None,:]
        self.terrain=terrain.packed()
        self.unscaled=float(np.float32(params.frame_time))

    def run(self,start,mask=0,*,event=0,frames=1):
        if frames not in (0,1):raise ValueError("nominal step supports zero or one frame")
        phys,rend,vel,modes,flags,box,final=_one(np.ascontiguousarray(start,dtype=np.float64),
            int(mask),int(event),int(frames),self.unscaled,self.params,self.terrain)
        return km.Rollout(phys,rend,vel,modes,flags,final,box)
