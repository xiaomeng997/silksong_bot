"""Isolated guard checks only: no replay imports, model, JIT or worker process."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

p = Path('C:/modeling/silksong_bot/tmp/air_catch427_entry.py')
tree = ast.parse(p.read_text(encoding='utf-8'))
boundary = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'boundary')
release = next(n for n in tree.body if isinstance(n, ast.ClassDef) for n in n.body
               if isinstance(n, ast.FunctionDef) and n.name == 'release_recorded_fixture')
ns = {'Path': Path}
exec(compile(ast.Module(body=[boundary, release], type_ignores=[]), str(p), 'exec'), ns)
checks = 0
for ep, own in [(0, 5710), (17, 57075), (19, 63221), (44, 135662)]:
    trial = Path('C:/ssbot/data/m2_play/clapper_plan/opus/review182/s312/r3/trials') / f'rt_ep{ep}'
    args = [str(p), str(trial), str(own+80), 'unused-output', f'--p-from={own}',
            f'--opus-synth={own+1}', f'--no-force-from={own}',
            f'--fixture-recorded-run={trial / "run"}:{own-1}', f'--fixture-own-from={own}']
    fixture, cut, b, synth, clean = ns['boundary'](args)
    assert cut == own-1 and b == own and synth == own+1 and len(clean) == len(args)-2
    checks += 1
    for change in [lambda a: a+[f'--no-force-from={own}'],
                   lambda a: [v.replace(f'--opus-synth={own+1}', f'--opus-synth={own}') for v in a],
                   lambda a: [v.replace(f'--p-from={own}', f'--p-from={own+1}') for v in a],
                   lambda a: [v.replace(f'--no-force-from={own}', f'--no-force-from={own+1}') for v in a],
                   lambda a: a+['--force-run-any'], lambda a: a+['--row-dbg=3'],
                   lambda a: a+['--fixture-opposite-key=3']]:
        try:
            ns['boundary'](change(args))
        except AssertionError:
            checks += 1
        else:
            raise AssertionError('invalid boundary accepted')
    ns.update(CUT=cut, OWN=b)
    obj = SimpleNamespace(recorded_fixture={'released_before_frame': None})
    masks = {own-1: 123}
    assert ns['release_recorded_fixture'](obj, masks, own-1) is False and masks
    assert ns['release_recorded_fixture'](obj, masks, own) is True and not masks
    assert obj.recorded_fixture['released_before_frame'] == own
    assert ns['release_recorded_fixture'](obj, masks, own+1) is False
    checks += 1
print(json.dumps({'isolated_boundary_checks': checks, 'no_replay_model_JIT_workers': True}))
