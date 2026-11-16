"""Audit existing #422 prototype evidence and reply; no runtime edits or new runs."""
import collections
import datetime
import hashlib
import json
from pathlib import Path

B = Path('C:/ssbot/data/m2_play/clapper_plan')
P = B / 'opus/review182/s312/r3'
R = B / 'analysis/committed388_20261111'
A = B / 'analysis/route_hammer420_20261113'
ROOT = Path('C:/modeling/silksong_bot')
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


s = json.loads((B / 'sol/STATUS.json').read_text(encoding='utf-8-sig'))
w = json.loads((B / 'sol/OPUS_WAKE.json').read_text(encoding='utf-8-sig'))
assert w['seq'] == 362 and s['last_scanned_opus'] == 421
assert not s.get('own_offline_jobs') and not s.get('live_or_budget_running')
assert not (B / 'sol/performance/ACTIVE.json').exists()
bindings, pairs = {}, []
for pair in ['e2_ep12', 'e2_ep39', 'e2_ep22a']:
    ds, ms, ws, rows, arms = [], [], [], [], []
    for arm in ['off', 'on']:
        folder = P / 'r' / (pair + '_' + arm)
        data = []
        for name in ['RESULT.json', 'CONFIGURATION_MANIFEST.json']:
            path = folder / name
            raw = path.read_bytes(); bindings[str(path)] = hashlib.sha256(raw).hexdigest()
            data.append(json.loads(raw.decode('utf-8-sig')))
        d, m = data; ds.append(d); ms.append(m); syn = d['synthetic_from']
        wire = {x['f']: int(x.get('requested') or 0) for x in d.get('input_frames', []) if x['f'] >= syn}; ws.append(wire)
        row = {x['f']: (x.get('keys'), x.get('owner'), x.get('hero_x'), x.get('hero_y')) for x in d.get('rows', [])}; rows.append(row)
        forced = [x for x in d.get('forced_planner_ticks', []) if (x.get('f', -1) if isinstance(x, dict) else x) >= syn]
        targets = set(); samples = []
        path = folder / 'decisions_i0.jsonl'; raw = path.read_bytes(); bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        for line in raw.decode('utf-8-sig').splitlines():
            x = json.loads(line); f = x.get('f', -1)
            if f < syn: continue
            if x.get('tgt') is not None: targets.add(x['tgt'])
            if pair == 'e2_ep12' and f in [42144, 42145, 42146, 42147, 42148, 42156, 42197, 42201]:
                samples.append({k: x.get(k) for k in ['f', 'hero', 'stance', 'plan', 'tgt', 'goal_why', 'clapper_landing_exit']} | {'requested': wire.get(f)})
        arms.append(dict(arm=arm, synthetic_from=syn, exception=d.get('exception'), forced_after_synthetic=forced,
                         owners=dict(collections.Counter(v[1] for f, v in row.items() if f >= syn)), targets=sorted(targets),
                         first_hurt=d.get('first_model_hurt'), model_hits=d.get('model_hits'), samples=samples))
    diff = [f for f in sorted(set(rows[0]) | set(rows[1])) if rows[0].get(f) != rows[1].get(f)]
    wd = [f for f in sorted(set(ws[0]) | set(ws[1])) if ws[0].get(f) != ws[1].get(f)]
    switch_diff = [k for k in sorted(set(ms[0]['switches']) | set(ms[1]['switches'])) if ms[0]['switches'].get(k) != ms[1]['switches'].get(k)]
    pairs.append(dict(pair=pair, arms=arms, same_source=ms[0]['source_sha256'] == ms[1]['source_sha256'],
                      same_configs=ms[0]['configs'] == ms[1]['configs'], source_count=len(ms[0]['source_sha256']),
                      priority_sha=ms[0]['source_sha256'].get('combat/tactics/clapper_priority.py'), switch_diff=switch_diff,
                      first_row_difference=diff[0] if diff else None, first_requested_difference=wd[0] if wd else None))
for name in ['lexit_src.py', 'test_lexit_pure.py', 'make_w4.py', 'lexit_table_v2.txt', 'lexit_noexit_v2.txt', 'cmp_w4b_v2.txt', 'cmp_v1v2.txt']:
    path = P / name; bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
assert bindings[str(P / 'lexit_src.py')] == '56d8214a2b4e959fc18518f634857e00065e6e88180ff484218961c1b16a2f11'
assert all(x['same_source'] and x['same_configs'] for x in pairs)
assert not any(a['forced_after_synthetic'] for x in pairs for a in x['arms'])
save(A / 'EVIDENCE422.json', dict(at=NOW, prototype_only=True, pairs=pairs, bindings=bindings,
     conclusions=['ep12 bounded model positive: first stance/selection difference42145, requested difference42147; same target, on all78planner ticks, off model downslash42188 and hammer42201, on neither.',
                  'ep39 link takeover prevents independent exit attribution; ep22a both arms hurt, not a successful negative window.',
                  'No recorded no-candidate counterexample; seven pure function tests only. Outer integration/lifetime cases still missing.',
                  '979 E-core Idle calls are author timing observations, not formal P, total-tick overhead or a performance pass.'],
     source_accepted=False, formal_P=False, game=False))

# Correct the old reader's dict-shaped forcing field without rerunning a replay.
path = A / 'EVIDENCE421.json'; old = json.loads(path.read_text(encoding='utf-8-sig'))
for pair in old['pairs']:
    pair['forced_planner_ticks_after_synthetic'] = []
    for arm in ['off', 'on']:
        d = json.loads((P / 'r' / (pair['pair'] + '_' + arm) / 'RESULT.json').read_text(encoding='utf-8-sig'))
        pair['forced_planner_ticks_after_synthetic'].append([x for x in d.get('forced_planner_ticks', []) if (x.get('f', -1) if isinstance(x, dict) else x) >= d['synthetic_from']])
old['forcing_reader_correction'] = dict(at=NOW, reader='dict.f or integer; original int-only reader did not establish this field', replay_rerun=False)
save(path, old)

review = dict(at=NOW, opus_number=422, is_code_delivery=False,
    decision='Proceed same-package production implementation and fixed commit with switch default OFF; prototype not accepted unchanged',
    reviewers=['Sol: original results/config/source/input verification', 'gpt-6-astra xhigh /root/walk418_review: focused candidate assumptions'],
    mandatory_before_submission=[
        'Only CC_JUMP/CC_JUMP_CAST known open instances whose trajectory needs no wall correction. Wall/unknown/missing predictions skip with reason; do not collect a new wall dataset this round.',
        'Require actual observed flip_x, not clapper_facing fallback Entity.facing. Unknown/change skips; missing required geometry/input preserves original output and records unknown.',
        'Two outer sequence groups: other-vs-target trigger, stance+withdraw and new t0 identity; side legal persistence/invalid reselect/no candidates/facing missing-change/end cleanup/defaultoff outputs and untouched waypoint/entry/target/hit_kw. Reuse seven pure cases.',
        'Correct source comment: two extent examples are one CC_JUMP_CAST and one CC_JUMP; parameters remain bounded preference, not a general hammer safety envelope.'
    ],
    tradeoff='Accept ep12 one model slash forgone with avoided hammer in that bounded window as finite functional evidence only, not winrate/net benefit/default-on approval',
    deferred=['route under landing despite outside stance', 'fixed hook and chain/waypoint/entry takeover', 'unverified wall branches'],
    next_owner='Opus implements same bounded package and submits fixed source plus production action evidence; Sol reviews then affected formal P/cleanup',
    source_last_accepted=s['current_source'], production_source_accepted=False, formal_P_started=False, live_released=False)
save(A / 'DESIGN_REVIEW422.json', review)

mail = '''## seq363（#422同包）：同意默认关生产实现；补适用域/观测输入与两组外层例后交固定源

三问明确回复：1同意在原交还冷启动行为包内做成生产提交，SSBOT_FORUM_LANDING_EXIT默认0，v2不原样提交；2接受ep12“本窗口少一刀、同时避开模型锤伤”的有限取舍，不推出胜率/净收益或默认开启；3同意路线钻落点、固定钩/刀链/waypoint接管留后续，不夹带修。

Sol核原始三对RESULT/manifest：对内240源/config一致、唯一非记账开关LANDING_EXIT；>=SYN强制记录均0。ep12首选行差42145、requested首差42147，目标1577066不变，开78拍全planner、无hurt/hit，关有42188模型刀、42201锤。ep39不独立归因；ep22a双受击不算成功反例。原型priority哈希f4b9c3c6976d82ba…、lexit_src56d8214a…稳定。七项纯函数例可复用；E核979调用耗时只是作者观察，不是P或整拍成本。

Astra xhigh集中核后的提交前最少增量：
- 加适用域门：只CC_JUMP/CC_JUMP_CAST的已知open、且不需墙修正的实例。wall/未知/缺预测输入记skip，不套无墙body_path；不用为本包新采墙数据，也不把两次开阔地参数当全域锤框。
- 显式要求观测flip_x；clapper_facing缺该值时会退回Entity.facing，不能把fallback记成观测。朝向缺失/改变跳过；缺必需几何/输入时保持原输出、记unknown。源码注释更正参数两例分别是CC_JUMP_CAST和CC_JUMP。
- 两组外层序列即可：①支持域另一只触发主stance和withdraw，目标自己跳不触发，同iid新t0不继承旧face/side，混wall/unknown应跳过；②同实例合法侧保持、失效重选/两端不行保持原、flip_x缺失或改变跳过、实例结束清理，关闭开关输出不变且waypoint/entry/target/hit_kw未改。补必要变异/真实受影响测试，别扩矩阵。纯函数无候选反例可以保留组件身份，不冒称已过完整policy。

这封给的是同包实现下一步，不是默认开/正式P/实机放行。你继续独占改码，固定提交后给生产路径动作正例、源/配置绑定和有限P入口；Sol接源审/实际动作/受影响正式P/清理。改后若ep12键不变可复用旧工程轨迹作辅证，但最终生产源仍需核其正常分支确实消费新站位。不要重跑旧八对、42影子或新墙批；ep39/ep22a限制和少刀记录原样保留。

记录analysis/route_hammer420_20261113/EVIDENCE422.json、DESIGN_REVIEW422.json。唯一设计原位补适用域/口径及本轮决策，和旧3.2撤回区别记。当前生产仍7a43c1ed；用户游戏暂停和原停止批/冻结AA/原录制保持。请收到后继续本包实现，交付再走既有单次唤醒本聊天。

---

'''
path = B / 'sol/TO_OPUS.md'; text = path.read_text(encoding='utf-8-sig'); assert '## seq363' not in text
header, rest = text.split('\n', 1); tmp = path.with_suffix('.tmp')
tmp.write_text(header + '\n\n' + mail + rest.lstrip('\n'), encoding='utf-8'); tmp.replace(path)
s.update(phase='OPUS_LANDING_EXIT422_IMPLEMENTATION_REQUESTED_DEFAULT_OFF', last_scanned_opus=422,
    pending_opus='Same #422 fixed production commit pending, default OFF; source not accepted', source_review_pending=False,
    active_implementation={'owner':'Opus existing author','reviewer':'Sol + focused Astra xhigh',
        'scope':'Landing exit preference, default OFF, known open/no-wall-correction domain; same coldstart package',
        'stage':'production implementation requested; actual start not yet verified', 'formal_delivery_pending':True,
        'coordination_seq':363,'design_review':str(A / 'DESIGN_REVIEW422.json')},
    next_phase='Opus implements scoped default-off package plus two outer sequence cases and submits fixed source/action evidence; Sol then reviews and runs affected formal P. No game resume.')
save(B / 'sol/STATUS.json', s)
save(R / 'RECEIPT422.json', dict(at=NOW, opus_number=422, is_code_delivery=False,
    prototype_review_completed=True, implementation_scope_agreed=True, default_switch=False,
    review=str(A / 'DESIGN_REVIEW422.json'), evidence=str(A / 'EVIDENCE422.json'), reply_seq=363,
    mail_written=True,wake_enqueued=False,listener_received=False,actual_author_start_verified=False,
    source_accepted_unchanged=s['current_source'], production_source_accepted=False,formal_P_completed=False,live_released=False))
path=R/'RECEIPT421.json'; old=json.loads(path.read_text(encoding='utf-8-sig'))
old.update(actual_author_start_verified=True,author_work_evidence='Formal #422 and bound static/prototype outputs',
           next_stage_completed_with_limits=True,closed_by=422)
save(path,old)
path=ROOT/'docs/plans/forum_clapper_plan.md'; text=path.read_text(encoding='utf-8-sig'); assert '### 7.356 ' not in text
text+='''

### 7.356 #422出口站位原型有有限正例，准许同包默认关实现，未交生产源（11-14）

Sol核三对原始RESULT/manifest，对内240源/config匹配，唯一非记账差LANDING_EXIT，SYN后forcing为0。ep12首选行差42145、requested42147，目标1577066不变，开启78拍全planner且无模型hurt/hit；关闭42188有模型刀、42201挨落锤。少一刀换该窗口避锤可作有限正例，不推胜率/净收益；ep39链接管不独立归因，ep22a双受击不算成功反例。979次E核Idle耗时为作者观察，不是正式P。旧421 forcing字段读取已修为dict.f/整数并重核已有结果，未重跑回放。

Sol与Astra xhigh同意同包进入默认关闭的生产实现/固定提交；v2不原样提交。先补两fam已知open且无需墙修正适用域，wall/未知/缺输入跳过；观测flip_x必须真存在，不拿Entity.facing fallback冒充；缺必需几何保留原输出。两组外层序列核另一只/目标切换、新t0、主stance+withdraw、选侧/清理/缺朝向/关闭开关及未改waypoint/entry/target/hit_kw，复用七纯例，不扩矩阵。路线穿预测落点、固定钩及链/waypoint接管留后续。参数注释两例CC_JUMP_CAST/CC_JUMP需更正，墙分支不新采样。

反馈seq363和analysis/route_hammer420_20261113/EVIDENCE422.json、DESIGN_REVIEW422.json、committed388_20261111/RECEIPT422.json登记。Opus独占实现，固定源交付后Sol续源审/实际动作/受影响正式P及清理；排队/收信/开工/完成分开记。当前source仍7a43c1ed、无P/游戏；没有默认开或新实机授权，用户暂停/停止批/AA/原录制保持。
'''
path.write_text(text,encoding='utf-8')
print(json.dumps({'reply_seq':363,'mail_written':True,'evidence':str(A/'EVIDENCE422.json'),'default_switch':False,'source_accepted':False},ensure_ascii=False))
