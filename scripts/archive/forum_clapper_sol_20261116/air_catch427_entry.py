"""Recorded keys through B-1, own policy from B, synthetic hero from B+1.

This scene adapter preserves the reviewed replay lifecycle and all controller
code. It makes the one recorded-state policy tick explicit and measures it.
"""
from pathlib import Path
import hashlib
import runpy
import sys

api = runpy.run_path('C:/ssbot/data/m2_play/clapper_plan/analysis/dash_side412_20261113/entry.py')
base = api['base']
base_main = api['base_main']
original_instrument = api['instrument']
Parent = api['FixtureLifecycle']
FIXTURE = CUT = OWN = SYNTH = None


def once(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


def boundary(argv):
    """Validate and consume only the two explicit adapter fixture arguments."""
    flags = [a for a in argv if a.startswith('--fixture-recorded-run=')]
    owns = [a for a in argv if a.startswith('--fixture-own-from=')]
    assert len(flags) == len(owns) == 1
    raw, cut = flags[0].split('=', 1)[1].rsplit(':', 1)
    fixture, cut, own = Path(raw), int(cut), int(owns[0].split('=', 1)[1])
    assert fixture.resolve() == (Path(argv[1]) / 'run').resolve()
    synths = [a for a in argv if a.startswith('--opus-synth=')]
    starts = [a for a in argv if a.startswith('--p-from=')]
    no_force = [a for a in argv if a.startswith('--no-force-from=')]
    assert len(synths) == len(starts) == len(no_force) == 1
    synth, start, no_force_from = (int(a.split('=', 1)[1]) for a in (synths[0], starts[0], no_force[0]))
    assert cut + 1 == own == start == no_force_from and synth == own + 1
    assert not any(a.startswith(('--force-run=', '--force-run-any', '--fixture-opposite-key=',
                                  '--row-dbg=', '--add-ent=', '--swap-at=')) for a in argv)
    clean = [a for a in argv if a not in (flags[0], owns[0])]
    return fixture, cut, own, synth, clean


class RecordedInputLifecycle(Parent):
    def register_recorded_fixture(self, masks):
        assert FIXTURE is not None and masks and max(masks) <= CUT
        self.recorded_fixture = dict(
            path=str(FIXTURE), sha256=hashlib.sha256((FIXTURE / 'decisions_i0.chain.jsonl').read_bytes()).hexdigest(),
            through=CUT, own_controls_from=OWN, synthetic_from=SYNTH, measurement_from=OWN,
            loaded=len(masks), maximum_loaded_frame=max(masks), released_before_frame=None,
            scope='Own policy and sends from B, recorded hero at B only; synthetic hero from B+1. No forced measured keys.')

    def release_recorded_fixture(self, masks, frame):
        if frame <= CUT or self.recorded_fixture['released_before_frame'] is not None:
            return False
        assert frame == OWN, 'recorded fixture must be cleared before the first measured policy tick'
        masks.clear()
        self.recorded_fixture.update(released_before_frame=frame, remaining_forced_keys=len(masks))
        assert not masks
        return True

    def close(self, primary):
        super().close(primary)
        base['write_json'](self.dest / 'RECORDED_INPUT_FIXTURE.json', getattr(self, 'recorded_fixture', None))


def instrument(source):
    source = original_instrument(source)
    source = once(source, '    policy.warmup()\n',
                  '    lifecycle.register_recorded_fixture(FORCE_RUN)\n    policy.warmup()\n')
    source = once(source, '        if scenario_ and f_ in FORCE_RUN:', '        if f_ in FORCE_RUN:')
    # release_prefix is called at the start of every replay frame, before its
    # policy call; clearing at B also disables fixture selection on tick B.
    source = once(source, '            lifecycle.release_prefix(f)\n',
                  '            lifecycle.release_prefix(f)\n            lifecycle.release_recorded_fixture(FORCE_RUN, f)\n')
    return source


def main():
    global FIXTURE, CUT, OWN, SYNTH
    FIXTURE, CUT, OWN, SYNTH, clean = boundary(sys.argv)
    sys.argv = clean + ['--force-run=' + str(FIXTURE) + ':' + str(CUT)]
    base['instrument'] = instrument
    base['ReplayLifecycle'] = RecordedInputLifecycle
    base_main()


if __name__ == '__main__':
    main()
