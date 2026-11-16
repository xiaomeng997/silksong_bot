"""Actual source, GC lifecycle and video audit after the completed new50."""
from pathlib import Path
import collections, datetime, hashlib, json, subprocess
import numpy as np
import psutil

B = Path('C:/ssbot/data/m2_play/clapper_plan')
G = B/'analysis/w13_50_middle_handoff434_20261114'
A = B/'analysis/middle_handoff434_20261114'
D = B/'sol/demos'/G.name
S = A/'source_fixed434'
read = lambda p: json.loads(p.read_text('utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p, obj):
    with p.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')

def main():
    me = psutil.Process()
    me.cpu_affinity(list(range(24,32)))
    me.nice(psutil.IDLE_PRIORITY_CLASS)
    assert read(G/'ROOT_CLEANUP.json')['runtime_batch_complete']
    assert read(G/'RAW_AUDIT_COMPLETION.json')['complete']
    result = read(G/'ROOT_50_RESULT.json')
    rows = [json.loads(l) for l in (D/'run/attempts_i0.jsonl').read_text('utf-8').splitlines() if l.strip()]
    packet = read(A/'SOURCE_PACKET_FIXED.json')
    expected = packet['raw_runtime_files_sha256']
    contract = read(D/'contract.json')
    assert all(sha(S/p) == h for p,h in expected.items())
    assert all(sha(Path(p)) == h for p,h in contract['prerequisites'].items())
    versions, gc_bouts, rss = [], [], []
    windows, owners, age, gaps = [], collections.defaultdict(list), [], collections.Counter()
    last_footer = None
    for ep, row in enumerate(rows):
        manifest = read(D/f'run/measurement_manifest_i0_e{ep}.json')
        assert manifest['configuration_complete'] and not manifest['unknown_environment_switches'] and not manifest['unresolved']
        assert manifest['code']['head_revision'] == contract['source']
        assert all(p in expected and h == expected[p] for p,h in manifest['code']['files_sha256'].items())
        for key, binding, value, raw in [
            ('SSBOT_FORUM_AIRSTRIKE', 'ssbot.combat.claw_strike.AIRSTRIKE', True, '1'),
            ('SSBOT_FORUM_MIDDLE_HANDOFF', 'ssbot.combat.slam_play.MIDDLE_HANDOFF', True, '1'),
            ('SSBOT_FORUM_CHAIN_B13', 'ssbot.combat.knife_chain_transfer.B13', True, '1'),
            ('SSBOT_FORUM_CHAIN_B13B', 'ssbot.combat.knife_chain_transfer.B13B', True, '1'),
            ('SSBOT_FORUM_SLAM_NO_NEW_GLIDE', 'ssbot.combat.forum_planner.SLAM_NO_NEW_GLIDE', False, '0'),
            ('SSBOT_FORUM_LANDING_EXIT', 'ssbot.combat.tactics.clapper_priority.LANDING_EXIT', True, '1'),
            ('SSBOT_FORUM_TWO_WALK_RULE', 'ssbot.combat.walk_rule.ENABLED', True, '1'),
            ('SSBOT_FORUM_RUNE_EXIT_FINAL', 'ssbot.combat.tactics.clapper_priority.RUNE_EXIT_FINAL', True, '1')]:
            switch = manifest['switches'][key]
            assert switch['raw'] == raw and switch['bindings'] == {binding:value}
        runtime = manifest['runtime_before']
        assert runtime['cpu_affinity'] == list(range(16)) and runtime['priority'] == 128 and runtime['numba_threads'] == 4
        assert manifest['seed'] == row['seed']
        versions.append(dict(bout=ep+1, source=contract['source'], files_verified=len(manifest['code']['files_sha256']), B13=True, B13B=True, middle_handoff=True, airstrike=True, extra_no_new_glide=False, landing_exit=True, walk_rule=True, rune_exit_final=True))
        gc = row['b2_context']['gc_bout']
        assert gc['episode'] == ep and gc['threshold'] == [2000,10,10000] and gc['gc_enabled'] and gc['frozen'] > 0
        gc_bouts.append(dict(bout=ep+1, **gc))
        rss.append(dict(bout=ep+1, quiet_before=gc['rss_before'], quiet_after=gc['rss_after'], worker_after=manifest['runtime_after']['rss']))
        lo, hi = None, None
        footer = None
        for line in (D/f'run/measurement_i0_e{ep}.jsonl').open(encoding='utf-8'):
            tick = json.loads(line)
            if tick.get('kind') == 'footer':
                footer = tick
            f = tick.get('f')
            if tick.get('kind') == 'tick' and isinstance(f,int) and row['f_wake'] <= f <= row['f_end'] and not tick.get('error'):
                owners[tick.get('owner') or 'none'].append(tick['total_tick_ms'])
                start = tick['tick_start_ns']
                lo = start if lo is None else min(lo, start)
                end = tick.get('tick_end_ns', start + round(tick['total_tick_ms']*1e6))
                hi = end if hi is None else max(hi, end)
                if tick.get('recv_ns') is not None:
                    age.append((start-tick['recv_ns'])/1e6)
                gaps[tick.get('processed_frame_gap',1)] += 1
        assert footer and footer['complete'] and not footer['overflow']
        diagnostics = footer['diagnostics']
        assert diagnostics['complete'] and not diagnostics['events_overwritten'] and not diagnostics['callback_errors']
        assert diagnostics['injection_requested_ms'] == 0 and not diagnostics['injection_executed']
        assert lo is not None and hi is not None
        windows.append(dict(bout=ep+1, lo=lo, hi=hi))
        last_footer = footer
        print(f'version/GC trace audit {ep+1}/50', flush=True)
    events = last_footer['diagnostics']['events']
    # Diagnostics are cumulative across bouts. Count only the final footer once.
    assert len({e['seq'] for e in events}) == len(events)
    starts = {e['seq']:e for e in events if e['kind']=='gc' and e['status']=='start'}
    gc_pairs = []
    for e in events:
        if e['kind'] != 'gc' or e['status'] != 'stop':
            continue
        prior = starts.get(e['seq']-1)
        if prior is None:
            continue
        assert prior['generation']==e['generation'] and prior['tid']==e['tid']
        bouts = [w['bout'] for w in windows if prior['wall_ns'] <= w['hi'] and e['wall_ns'] >= w['lo']]
        gc_pairs.append(dict(generation=e['generation'], start_ns=prior['wall_ns'], end_ns=e['wall_ns'], ms=(e['wall_ns']-prior['wall_ns'])/1e6, overlaps_combat_bouts=bouts, tid=e['tid']))
    gen2 = [e for e in gc_pairs if e['generation']==2]
    in_fight = [e for e in gen2 if e['overlaps_combat_bouts']]
    assert not in_fight, in_fight
    costs = [v for vv in owners.values() for v in vv]
    stats = lambda v: dict(n=len(v), p50_ms=float(np.percentile(v,50)), p99_ms=float(np.percentile(v,99)), max_ms=max(v), over_16_67_ms=sum(x>1000/60 for x in v))
    put(G/'ACTUAL_VERSION_AUDIT.json', dict(at=now(), source=contract['source'], bouts=50, mixed_source=False, runtime_files_unchanged=len(expected), prerequisites_unchanged=len(contract['prerequisites']), all_actual_switches_verified=True, rows=versions))
    put(G/'RUNTIME_GC_AUDIT.json', dict(at=now(), source=contract['source'], complete=True, actual_quiet_collections=50, gc_bouts=gc_bouts, RSS=rss, generation2_events_total=len(gen2), generation2_in_combat=len(in_fight), gen2_events=gen2, combat_tick_windows=windows, all50_diagnostics_complete=True, deliberate_stall_in_new50=False, costs=stats(costs), costs_by_owner={k:stats(v) for k,v in owners.items()}, before_tick_STATE_age=stats(age), processed_frame_gap_counts=dict(gaps), limitations=['Combat windows use actual first/last processed tick wall times; model-wide automatic gen2 impossibility is not claimed.', 'Recorded real per-bout full collections occurred before combat; gen0/1 stay enabled.', 'Tick costs exclude time before tick_start. This is one live batch, not new replay-P or a global scheduling proof.']))
    video = D/'w13.mp4'
    ffprobe = 'C:/Users/Meng/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffprobe.exe'
    probe = json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,r_frame_rate,nb_frames,duration:format=duration,size','-of','json',str(video)],text=True))
    v = probe['streams'][0]
    capture = read(D/'launch/CAPTURE_CLOSED.json')
    assert int(v['nb_frames']) == capture['frames'] and capture['encoder_returncode']==0
    duration = float(probe['format']['duration'])
    put(G/'VIDEO_RECEIPT.json',dict(at=now(),video=str(video),bytes=video.stat().st_size,duration_seconds=duration,duration_display=f'{int(duration//60)}:{duration%60:04.1f}',fps=v['r_frame_rate'],frames=int(v['nb_frames']),width=v['width'],height=v['height'],codec=v['codec_name'],encoder_returncode=0,ffprobe_verified=True,raw_video_unmodified=True))
    prefixes = []
    for label, group in [('first30',result['rows'][:30]),('last20',result['rows'][30:])]:
        prefixes.append(dict(part=label,n=len(group),both_killed=sum(r['outcome']=='CLEAR' for r in group),pass_bouts=sum(r['criterion_pass'] for r in group),protected_quits=sum(r['protected_quit'] for r in group),HP=sum(r['loss_hp'] for r in group)))
    put(G/'SEGMENT_RESULT.json',dict(at=now(),groups=prefixes,full50_no_protected_quit_pass=result['criterion_pass']))
    print(json.dumps(dict(versions=50, quiet_GC=50, gen2_in_combat=len(in_fight),gen2_total=len(gen2), tick_cost=stats(costs), RSS_first=rss[0],RSS_last=rss[-1],video_duration=duration,segments=prefixes),ensure_ascii=False))

if __name__=='__main__':
    main()
