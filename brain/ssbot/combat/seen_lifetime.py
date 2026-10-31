"""Finite game-time lifetime for the existing forced seen-contact ranking only."""
import numpy as np
from numba import njit, prange
from .forum_planner import _rect_meets_polys as meets

@njit(cache=True,parallel=True)
def timed_seen(box,inv,verts,starts,pbox,vel,tk,rows,grow,expiry,lag,vmin,sweep):
    N,T1=box.shape[0],box.shape[1];n_p=len(starts)-1
    cnt=np.zeros(N,np.int64);first=np.full(N,T1,np.int64)
    for m in prange(len(rows)):
        c=rows[m]
        for k in range(1,T1):
            if inv[c,k]:continue
            x0,y0,x1,y1=box[c,k,0]-grow,box[c,k,1]-grow,box[c,k,2]+grow,box[c,k,3]+grow
            hit=False
            for p in range(n_p):
                fast=sweep and vel[p,0]*vel[p,0]+vel[p,1]*vel[p,1]>=vmin*vmin
                for j in range(3):
                    if j!=1 and not fast:continue
                    t=tk[k]+(j-1)*lag
                    if t>expiry[p]:continue
                    dx,dy=vel[p,0]*t,vel[p,1]*t
                    if pbox[p,0]+dx>x1 or pbox[p,2]+dx<x0 or pbox[p,1]+dy>y1 or pbox[p,3]+dy<y0:continue
                    if meets(x0,y0,x1,y1,verts,starts[p:p+2],dx,dy):hit=True;break
                if hit:break
            if hit:
                cnt[c]+=1
                if first[c]==T1:first[c]=k
    return cnt,first

