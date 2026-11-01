"""Observed-state primitives for the empirical w7 fixed-hook table.

The old key template is an explicitly chosen learning policy, not a forecast
certificate. No rollout, C5, contact predictor or N=2 call is made here.
"""
import math
from . import claw_strike as CS, air_chain as AC
from .knife_chain_format import MASK_NAMES as B


def register(P):
    from . import knife_chain_slam as F

    @P.guard("fixed_hook_entry")
    def entry(x):
        o=x.obs;v=x.v;h=o.h;cfg=x.cfg
        if not getattr(x.R.anchor,"fixed_hook_enabled",False):return False
        if o.st!="Slam Antic" or not cfg["FH_K_MIN"]<=v["k"]<=cfg["FH_K_MAX"]:return False
        if not o.ground or not o.accepting or h.get("can",{}).get("harpoon") is not True or o.silk<1:return False
        toward=-v["face"];key=B["R"] if toward>0 else B["L"]
        hf=(o.s.get("act") or {}).get("hf") or {}
        if hf.get("latched")!=key or hf.get("desired")!=key:return False
        gap=F.xrel(x)
        if not all(math.isfinite(z) for z in (gap,o.vx)) or not cfg["FH_GAP_MIN"]<=gap<=cfg["FH_GAP_MAX"]:return False
        if o.facing is None or (1 if o.facing>=0 else -1)!=toward or o.vx*toward<=0:return False
        if F.g_claw_circle(x):return False
        if o.bombs is not None and len(o.bombs):
            from .rune_bombs import HB_HX, BOMB_M
            lo,hi=sorted((o.hx,o.cx+v["face"]*CS.BODY_FRONT))
            # Cheap initial horizontal approach guard, not a flight certificate.
            # Keep every owner and the existing bomb/hero margin.
            for row in o.bombs:
                if len(row)!=6 or not all(math.isfinite(float(z)) for z in row):return False
                _,bx,_,radius,_,off=row
                if radius<0:return False
                reach=radius+HB_HX+BOMB_M
                if off>=0 and lo-reach<=bx<=hi+reach:return False
        return True

    @P.action("fixed_hook_plan")
    def hook_plan(x):
        if x.v["cs"] is not None:return
        F0=x.obs.F
        x.v.update(cs=CS.CsPlan(F0,3,F0+2,x.v["k"]+2),cs_toward=-x.v["face"],
                   hp0=x.obs.hp,k_start=x.v["k"],x_start=F.xrel(x),why="fixed hook")

    @P.action("fixed_hook_strike")
    def strike(x):
        if x.v["cs_strike"] is not None:return
        gap=abs(F.xrel(x));k=x.v["k"]
        if not math.isfinite(gap) or not 2.4<=gap<=4.9 or k>47:
            return {"do":"abort","why":"fixed hook control outside empirical strike template"}
        drift=6 if gap>=4.6 else 3 if gap>=4.24 else 0
        key=(B["R"] if x.v["cs_toward"]>0 else B["L"]) if drift else 0
        x.v["cs_strike"]=AC.Plan(x.obs.F,key,x.obs.F+drift,None,None,x.obs.F+47-k,47,x.v["iid"])
        x.v["cs_k_ctrl"]=k-2

    @P.action("fixed_hook_wait")
    def wait(x):
        v=x.v;o=x.obs
        if o.st not in x.R.anchor.slam_states:
            return {"do":"abort","why":"fixed hook wait: left observed slam sequence without verified release"}
        if v["fh_wait_f"]==o.f:return
        v["fh_wait_f"]=o.f
        if v["fh_recover"] is None:
            if o.st=="Slam Recover":v["fh_recover"]=o.f
            return
        fs=o.s.get("fs")
        if type(fs) is not int or fs<0:
            return {"do":"abort","why":"fixed hook wait: unknown physical-step clock"}
        v["fh_steps"]+=fs
        if v["fh_steps"]>=2:
            x.R.anchor.fixed_release={"frame":o.f,"recover":v["fh_recover"],"steps":v["fh_steps"]}

    @P.guard("fixed_hook_released")
    def released(x):
        return x.v["fh_recover"] is not None and x.v["fh_steps"]>=2
