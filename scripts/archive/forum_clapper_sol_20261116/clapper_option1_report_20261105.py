"""Summarize the existing-TRAIN census and explicit one-dimensional necessary space arithmetic."""
import hashlib
import json
import math
import shutil
from pathlib import Path
from datetime import datetime, timezone

B=Path('C:/ssbot/data/m2_play/clapper_plan')
O=B/'analysis/cluster_bait_space_20261105'
E=json.loads((O/'events.json').read_text(encoding='utf-8'))
I=json.loads((O/'inventory.json').read_text(encoding='utf-8'))
assert len({(e['recording'],e['f0'],e['jump_iid']) for e in E})==len(E)
assert not I['errors']
assert not any(any(r.get('rebuilt_indexes',{}).values()) for r in I['recordings'])
assert not any(z['js']=='Cast Jump' for e in E for z in e['rows'])
assert all(all(a['fc']<=b['fc'] for a,b in zip(e['rows'],e['rows'][1:])) for e in E)

def dist(v):
    v=sorted(v)
    q=lambda x:v[max(0,math.ceil(len(v)*x)-1)] if v else None
    return {'n':len(v),'p50':q(.5),'p95':q(.95),'p99':q(.99),'max':q(1.)}

groups={}
for dataset in ['existing_behavior_training','recent_w13']:
    for fam in ['jump','jump_cast']:
        for cn, pred in {
            'initial_idle':lambda e:e['other_state0']=='Idle',
            'initial_idle_walk':lambda e:True,
            'cluster_initial_idle':lambda e:e['outside'] and e['body_gap0'] is not None and e['body_gap0']<=1 and e['other_state0']=='Idle',
            'cluster_initial_idle_walk':lambda e:e['outside'] and e['body_gap0'] is not None and e['body_gap0']<=1,
            'cluster_retreat':lambda e:e['outside'] and e['body_gap0'] is not None and e['body_gap0']<=1 and e.get('retreat_during_aim',0)>=1,
            'cluster_ground':lambda e:e['outside'] and e['body_gap0'] is not None and e['body_gap0']<=1 and e['hero_y0']<6.5,
        }.items():
            ee=[e for e in E if e['dataset']==dataset and e['family']==fam and pred(e)]
            gg={'events':len(ee),'horizons':{}}
            for h in ['aim_lock','aim_plus_0.2','aim_plus_0.4','aim_plus_0.6','aim_plus_0.8','landing','attack_end']:
                hh=[e['horizons'][h] for e in ee if h in e['horizons']]
                gg['horizons'][h]={'advance':dist([z['max_advance'] for z in hh]),
                                   'net':dist([z['net_advance'] for z in hh]),
                                   'elapsed_physical_s':dist([z['elapsed_physical_s'] for z in hh]),
                                   'advance_no_other_attack':dist([z['max_advance'] for z in hh if z['all_idle_walk']])}
            groups[f'{dataset}/{fam}/{cn}']=gg

# Outward positive: J initial jumper center, W walker center, H hero at aim-lock.
# L=J+.916*clip(H-J-5, -12, 12); W_end=W+C.
# Existing JB minimum standback 3.1 on each side gives S=6.2 center separation.
# This is a geometric necessary-condition comparison, not a certified path/damage test.
S=6.2
examples=[]
for c in [0.,2.,3.84,4.,7.2,9.6,12.]:
    for delta in [-3.,0.,3.]:
        need=S+c-delta
        dbait=5.+need/.916
        examples.append({'walker_advance_C':c,'jumper_ahead_of_walker_delta':delta,
                         'min_landing_center_gap_S':S,'initial_hero_jumper_distance_D0':5.,
                         'required_jump_displacement':need,'model_jump_max_displacement':.916*12,
                         'within_open_jump_displacement_cap':need<=.916*12,
                         'necessary_aim_hero_to_jumper_center_distance':dbait,
                         'necessary_retreat_from_D0_5':max(0.,dbait-5.),
                         'meaning':'necessary geometry only; needs real timing, dynamic pursuit stop, wall branch, hazards and return path checks'})

result={'at':datetime.now(timezone.utc).isoformat(),'kind':'offline raw recording census + necessary geometry arithmetic',
        'recordings':len(I['recordings']),'jump_events_with_idle_walk_peer_at_first_antic_STATE':len(E),
        'old_training_recordings':12,'old_training_finale_ranges':107,'recent_recordings':23,
        'method':{'unit':'u, entity root x displacement toward initial hero side, maximum over prefix (not sum of steps)',
                  'clock':'actual fc differences * 0.02 seconds; no f/60 conversion',
                  'family':'first observed Jump Antic or Cast Slam Antic STATE; takeoff Jump/Air; landing first Slam 2 STATE',
                  'quantile':'nearest rank ceil(p*n), one sample per observed jump/peer, not one per tick',
                  'censoring':'actor missing/dead, STATE gap, fixed clock reset, absent horizon excluded for that horizon; n reported',
                  'source_domain':'only recent local w13 TRAIN and recordings explicitly used by ChoirClapper.json sources; no AA/fresh/holdout',
                  'cluster':'hero outside both roots; observed body AABB gap <=1u; classification is not route safety',
                  'new_tactic_causality':'old observed hero motion; a different retreat/return can change DistanceWalk, so these are empirical summaries, not counterfactual trajectories'},
        'groups':groups,'space':{'axis':'toward hero from cluster at start','equation':'L - W_end = delta + .916*clip(D_bait-5,-12,12) - C; require >= S',
                              'S':S,'S_basis':'existing jump_behind.CFG min_back_u=3.1 on both sides, including turn/body margin; conservative placement assumption, not a new universal geometric lower bound',
                              'examples':examples},
        'limits':['99th percentile is empirical under these recorded policies; jumps within 107 encounters are correlated.',
                  'Initial Idle can transition into Walk/other actions; main cohorts do not discard these outcomes.',
                  'A horizon subset that stays Idle/Walk is descriptive and selected by future behavior, not a causal admission rule.',
                  'The clustered initial-Idle subsets are only 98 normal /87 cast starts; empirical p99 is the maximum there.',
                  'Existing DistanceWalk has 5.5/8.5u hysteresis; stop/reverse depends on current hero distance, not a fixed walk duration.',
                  'Do not multiply a global percentile by time, freeze walker, or turn a percentile into a hard safety certificate.',
                  'The necessary-space examples exclude wall-shortened/pushed jumps, timing feasibility, bodies during passage, current/rune hazards and next attacks.',
                  'No production code, gate, budget or live test changed.']}
(O/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

report='''# 成团时后撤引导再钻：待机怪移动与必要空间（离线）

用户修正：两怪成团、英雄在外侧时，优先在瞄准阶段后撤拉开落点、起跳后钻到两怪之间；空间或时间不足，才在瞄准阶段贴近砍、起跳后撤躲、落地回来。不能把此情况写成一律撤离，也不能去翻另一只成团怪。

## 原始统计

35 个已有 TRAIN 录像：最近 23 个 w13 + 当前行为表已使用的 12 个旧录像（107 个双怪终局范围）。共 1664 个“起跳前摇首见时另一只为 Idle/Walk”的跳跃事件。按实际 fc*0.02 计时间，一跳一个样本；向英雄原始所在侧的最大位移，不把来回走的路程相加。没有打开 AA、fresh 或留出；读取器没有重建/改写任何原始索引。

主要表只取前摇首见时另一只实际为 Idle，不因它稍后改为走路/出招而删去；最近数据单列，未和旧策略混成新版成功率。99 分位用 nearest-rank。

| 起跳招式 | 前摇→起跳 n | 前摇→起跳中位 / 99分位 | 前摇→落地 n | 前摇→落地中位 / 99分位 |
|---|---:|---:|---:|---:|
'''
for fam,label in [('jump','普通跳锤'),('jump_cast','跳大符文')]:
    g=groups[f'existing_behavior_training/{fam}/initial_idle']['horizons']
    a=g['aim_lock']['advance'];l=g['landing']['advance']
    report+=f"| {label} | {a['n']} | {a['p50']:.2f} / {a['p99']:.2f} u | {l['n']} | {l['p50']:.2f} / {l['p99']:.2f} u |\n"
report+='''
普通跳的瞄准期约0.50s，跳大符文约0.92–0.94s。待机怪中位数几乎不动，但99分位仍接近走满瞄准期。成团、人在外侧的初始Idle子集只有普通98/大符文87次；其瞄准期最大为4.00/7.36u，不能据小子集把上界降得更低。若初始已Walk，旧样本瞄准期99分位为4.00/7.52u（所有初始Idle/Walk为4.00/7.52u）。成团且英雄确实后撤≥1u的旧样本普通133/大符文152次，瞄准期99分位4.32/7.52u；并没有证明后撤时同伴通常只走一两步。

“到落地”是更长窗口，不能把它的位移全算在尚未过完的瞄准期；反过来只用瞄准期数字也不保证钻回后仍有中间位置。完整分层和每个事件的逐STATE轨迹见RESULT.json/events.json/events.csv。样本是既有策略条件分布，不能称为新打法99%安全保证；同一局多次起跳也不独立。

## 必要空间算式（开阔地分支，非完整路线验收）

朝英雄外侧记正：起跳怪与走路怪初始中心差 δ=J−W；瞄准锁定时英雄距起跳怪 D；走路怪到所考察时刻前进 C。现有跳跃模型位移为 .916*clamp(D−5,−12,12)，最大10.992u；因此两怪未来中心间隔为 δ+.916*clamp(D−5,−12,12)−C。

按现有 min_back_u=3.1u 在两边各留一份站位余量，示例需中心间隔 S=6.2u。只是沿用现有身体/转身余量的保守放置条件，不称精确最小身体间隙。必要 D≥5+(6.2+C−δ)/.916，同时所需跳移不得超过10.992u；实际必须继续核原墙分支、回钻时间/冲刺资源、身体与锤框、符文及更晚出招。

例如两怪中心重合、英雄原在怪前5u：
- 同伴不动：需英雄到怪前11.77u，即后撤至少6.77u。
- 同伴前移2u：需怪前13.95u，后撤至少8.95u。
- 同伴前移4u：需怪前16.14u，后撤至少11.14u，已接近跳移上限。
- 同伴前移超过4.792u：在此起点和6.2u间隔假设下，仅拉远瞄准已不够；不是再多跑就能解决。

若起跳怪比走路怪更靠近英雄3u，则相同C=4u例所需后撤降到7.86u；若起跳怪反在后面3u，需求跳移超上限。故必须看谁在前，不能只量英雄身后到墙的距离。

以上 C 必须取对应终点时刻。不能把原录像“直到落地还走了11u”硬套到新回钻动作：DistanceWalk维持5.5/8.5u滞回距离，英雄折返接近会使它停走/后退。也不能默认此反应一定及时。结论是按当前距离/状态/剩余瞄准时间算候选，在锁定后用已知落点和实际同伴位置复核；中间站不下就选贴砍后撤分支。本轮只算数据与必要条件，没有新NPC模拟器、运行代码或游戏放行。
'''
(O/'REPORT.md').write_text(report,encoding='utf-8')
shutil.copyfile('C:/modeling/silksong_bot/tmp/clapper_option1_stats_20261105.py',O/'census.py')
shutil.copyfile(__file__,O/'summarize.py')
manifest={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in O.iterdir() if x.is_file() and x.name!='MANIFEST.json'}
(O/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'complete':True,'events':len(E),'result':str(O/'RESULT.json'),'report':str(O/'REPORT.md'),
                  'checks':['unique events','no index rebuild','physical clock monotone','no Cast Jump endpoint ambiguity','no inventory errors']}))
