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


@njit(cache=True, error_model="numpy")
def _trace(start,latched,game,frame_time,unscaled,params,terrain):
    # Retain full states while reusing the original single-lane frame loop.
    # There are no synthetic contacts/events in an observed post-bounce row.
    n=latched.size;state=start.copy()
    states=np.empty((state.size,n+1));boxes=np.empty((n+1,4));positions=np.empty((n+1,2))
    flags=np.empty(n+1,np.int64);games=np.empty(n+1)
    states[:,0]=state;games[0]=game
    q=_one(state,0,0,0,unscaled,params,terrain)
    boxes[0]=q[5][0,0];positions[0]=q[1][0,0];flags[0]=q[4][0,0]
    for i in range(n):
        game+=frame_time*state[km.TS]*state[km.WF_S]
        q=_one(state,latched[i],0,1,unscaled,params,terrain)
        state=q[6][:,0].copy()
        states[:,i+1]=state;games[i+1]=game
        boxes[i+1]=q[5][0,1];positions[i+1]=q[1][0,1];flags[i+1]=q[4][0,1]
    return states,boxes,positions,flags,games


class NominalStepper:
    def __init__(self,params,terrain):
        # Fresh per compilation, so changes in weighted loadout / frame time /
        # HERO2 bits cannot hit a stale process-global parameter cache.
        self.params=params.vector()[None,:]
        self.terrain=terrain.packed()
        self.unscaled=float(np.float32(params.frame_time))
        self.frame_time=float(params.frame_time)

    def run(self,start,mask=0,*,event=0,frames=1):
        if frames not in (0,1):raise ValueError("nominal step supports zero or one frame")
        phys,rend,vel,modes,flags,box,final=_one(np.ascontiguousarray(start,dtype=np.float64),
            int(mask),int(event),int(frames),self.unscaled,self.params,self.terrain)
        return km.Rollout(phys,rend,vel,modes,flags,final,box)


    def trace(self,start,latched,game):
        return _trace(np.ascontiguousarray(start,dtype=np.float64).reshape(km.K),np.ascontiguousarray(latched,dtype=np.int64),
                      float(game),self.frame_time,self.unscaled,self.params,self.terrain)
