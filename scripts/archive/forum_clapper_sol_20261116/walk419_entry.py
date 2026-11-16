"""Reviewed replay lifecycle with a recorded-input fixture ending before synthesis/timing."""
from pathlib import Path
import hashlib,json,runpy,sys
api=runpy.run_path('C:/ssbot/data/m2_play/clapper_plan/analysis/dash_side412_20261113/entry.py')
base=api['base'];base_main=api['base_main'];original_instrument=api['instrument']
Parent=api['FixtureLifecycle'];FIXTURE=None;CUT=None

def once(source,old,new):
    assert source.count(old)==1,old
    return source.replace(old,new,1)

class RecordedInputLifecycle(Parent):
    def register_recorded_fixture(self,masks):
        assert FIXTURE is not None and masks and max(masks)<=CUT
        self.recorded_fixture=dict(path=str(FIXTURE),sha256=hashlib.sha256((FIXTURE/'decisions_i0.chain.jsonl').read_bytes()).hexdigest(),
            through=CUT,loaded=len(masks),maximum_loaded_frame=max(masks),released_before_frame=None,
            scope='Recording own real sends through the pre-synthetic fixture only; no forced keys or controller patch in the measured window.')
    def release_recorded_fixture(self,masks,frame):
        if frame<=CUT or self.recorded_fixture['released_before_frame'] is not None:return False
        masks.clear();assert not masks
        self.recorded_fixture['released_before_frame']=frame
        self.recorded_fixture['remaining_forced_keys']=0
        return True
    def close(self,primary):
        super().close(primary)
        base['write_json'](self.dest/'RECORDED_INPUT_FIXTURE.json',getattr(self,'recorded_fixture',None))

def instrument(source):
    source=original_instrument(source)
    source=once(source,'    policy.warmup()\n','    lifecycle.register_recorded_fixture(FORCE_RUN)\n    policy.warmup()\n')
    # The stable P stack uses replay308 (not replay308f). Allow its existing
    # observed-key dictionary outside WALK_SCEN only under the bounded fixture;
    # the dictionary is emptied at synthesis, well before every measured tick.
    source=once(source,'        if scenario_ and f_ in FORCE_RUN:',
        '        if f_ in FORCE_RUN:')
    source=once(source,'            lifecycle.release_prefix(f)\n',
        '            lifecycle.release_prefix(f)\n            lifecycle.release_recorded_fixture(FORCE_RUN, f)\n')
    return source

def main():
    global FIXTURE,CUT
    flags=[a for a in sys.argv if a.startswith('--fixture-recorded-run=')]
    assert len(flags)==1
    raw,cut=flags[0].split('=',1)[1].rsplit(':',1);FIXTURE=Path(raw);CUT=int(cut);sys.argv.remove(flags[0])
    assert FIXTURE.resolve()==(Path(sys.argv[1])/'run').resolve(),'fixture must be this trial own recorded sends'
    synth=int(next(a.split('=',1)[1] for a in sys.argv if a.startswith('--opus-synth=')))
    start=int(next(a.split('=',1)[1] for a in sys.argv if a.startswith('--p-from=')))
    assert CUT+1==synth and CUT<start
    no_force=[a for a in sys.argv if a.startswith('--no-force-from=')]
    assert len(no_force)==1 and int(no_force[0].split('=',1)[1])<=synth, 'old live-key fallback must stop by synthesis'
    assert not any(a.startswith(('--force-run=','--force-run-any','--fixture-opposite-key=','--row-dbg=','--add-ent=','--swap-at=')) for a in sys.argv)
    sys.argv += ['--force-run='+str(FIXTURE)+':'+str(CUT)]
    base['instrument']=instrument;base['ReplayLifecycle']=RecordedInputLifecycle;base_main()

if __name__=='__main__':main()
