"""Component-only spy: which existing geometry gate checks a rejected dash's wait step?"""
import os,sys,json
from pathlib import Path
os.environ['NUMBA_DISABLE_JIT']='1'
sys.path.insert(0,str(Path(sys.argv[1])/'brain'))
sys.path.insert(1,'C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain')
import numpy as np
import pytest
from types import SimpleNamespace as NS
from dataclasses import replace
from ssbot.combat import knife_chain_air_native as N
from ssbot.combat.knife_chain_commitment import ContactScan
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from tests.test_shared_strike_approach import flight
from tests.test_dash_lock179 import chain,FC

m=pytest.MonkeyPatch();r,s,sim=flight();n=chain(m,r);calls=[]
class SpyGeometry:
    def __init__(self,*args):pass
    def scan(self,path):
        calls.append('scan_all_owners')
        return ContactScan('component_spy',path.origin,path.through,(),'spy_only')
    def preflight(self,path):
        calls.append('preflight_external_only')
        return ContactScan('component_spy',path.origin,path.through,(),'spy_only')
m.setattr(N,'B2Geometry',SpyGeometry)
m.setattr(n,'queued_prefix',lambda *a:(B['L'],'consistent fixture opposite prefix'))
sim=replace(sim,prefix=np.array([B['L']],np.int64))
offer=n._transfer_offer(s,0.,sim,FC,NS(target=8),False)
print(json.dumps(dict(root=sys.argv[1],geometry_calls=calls,offer=offer is not None,
    recipe=None if offer is None else offer.draft.run.v.get('approach_recipe'),
    decision=None if offer is None else offer.draft.run.v.get('air_dash_decided'),
    scope='Component spy only; proves gate selection, not a physical collision or live damage.')))
