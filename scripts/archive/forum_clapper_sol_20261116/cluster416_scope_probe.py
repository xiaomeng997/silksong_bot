"""One L2 component counterexample; no game and no physical damage claim."""
import json
import os
import sys
from pathlib import Path

os.environ['NUMBA_DISABLE_JIT'] = '1'
sys.path.insert(0, str(Path(sys.argv[1])/'brain'))
sys.path.insert(1, 'C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain')
import pytest
from tests.test_cluster_plan2_back import _cluster, change, go_, G
from tests.test_clapper_priority import manual

m = pytest.MonkeyPatch()
manual.__wrapped__(m)
tac, ws, fc, ex = _cluster(m)
ex.select('lure', ws.stamp.t_game_s)
ex.name = 'lure_slash'
change(fc, 8, family=G.CC_JUMP, state='Slam Recover', committed=True)
ws.entities[1].fsm = [('Control', 'Slam Recover', .02)]
go_(tac, ws, fc)
mem = tac._clapper_priority
after_lure = dict(status=ex.status, phase=ex.name, selected=ex.selected,
                  skip=dict(mem.get('back_skip') or {}), reason=ex.reason)
# Seed only the already-recorded historical nearness fact: the public return
# collector normally records this on any earlier nearby tick of that jump.
mem['moves'][8]['near'] = True
change(fc, 8, family=G.CC_IDLE, state='Idle', committed=False)
ws.entities[1].fsm = [('Control', 'Idle', 0.)]
go_(tac, ws, fc)
print(json.dumps(dict(root=sys.argv[1], branch='lure', after_lure=after_lure,
    pending_middle_return=mem.get('back'), skipped=mem.get('back_skipped'),
    scope='L2 component, seeded historical nearness; no geometry/send/live/HP claim.'), ensure_ascii=False))
m.undo()
