"""The first visible Clapper in Clawline's ray band, independent of intent.

This identifies the present-observation target only. The throw happens later;
this function does not predict enemy motion or admit an empty air-needle dash.
Band/reach: existing claw_strike CsCfg documentation and Clawline answer.txt.
"""
import math


def _box(value):
    if value is None or len(value)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in value):
        raise ValueError("unknown hook body box")
    x0,y0,x1,y1=value
    if not x0<x1 or not y0<y1:raise ValueError("invalid hook body box")
    return x0,y0,x1,y1


def first_ray_body(hero_box,face,bodies):
    """Return (iid, distance from ray origin), None if empty; unknown raises.

    bodies contains (iid, world AABB). Tied front edges are ambiguous, rather
    than silently selecting an iid by entity order. No input is mutated.
    """
    h=_box(hero_box)
    if type(face) is not int or face not in (-1,1):raise ValueError("unknown hook facing")
    x=.5*(h[0]+h[2]);lo,hi=h[1]+.50,h[1]+1.98
    seen=set();hits=[]
    for iid,box in bodies:
        if type(iid) is not int or iid in seen:raise ValueError("unknown or duplicate hook body identity")
        seen.add(iid);b=_box(box)
        near,far=((b[0]-x,b[2]-x) if face>0 else (x-b[2],x-b[0]))
        if far<0 or near>10.5 or b[1]>=hi or b[3]<=lo:continue
        hits.append((max(near,0.),iid))
    if not hits:return None
    hits.sort()
    if len(hits)>1 and abs(hits[1][0]-hits[0][0])<1e-6:raise ValueError("ambiguous first hook body")
    distance,iid=hits[0]
    return iid,distance
