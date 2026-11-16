"""Freeze #423 review inputs, verify production proof, return same-package P2."""
import ast
import collections
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

B = Path('C:/ssbot/data/m2_play/clapper_plan')
P = B / 'opus/review182/s312/r3'
A = B / 'analysis/landing_exit423_20261114'
R = B / 'analysis/committed388_20261111'
ROOT = Path('C:/modeling/silksong_bot')
WT = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
GIT = 'C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
HEAD = '844f645568105d1e96b4ad7eb227d60c2ffc76eb'
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()
sha = lambda data: hashlib.sha256(data).hexdigest()
norm = lambda data: data.replace(b'\r\n', b'\n')


def save(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def git(*args):
    return subprocess.check_output([GIT, '-C', str(WT), *args])


s = json.loads((B / 'sol/STATUS.json').read_text(encoding='utf-8-sig'))
w = json.loads((B / 'sol/OPUS_WAKE.json').read_text(encoding='utf-8-sig'))
assert w['seq'] == 363 and s['last_scanned_opus'] == 422
assert not s.get('own_offline_jobs') and not s.get('live_or_budget_running')
assert not (B / 'sol/performance/ACTIVE.json').exists()
assert git('rev-parse', 'HEAD').decode().strip() == HEAD
assert not git('diff', 'HEAD', '--', 'brain/ssbot', 'brain/tests/test_landing_exit.py').strip()
files = git('diff', '--name-only', HEAD + '^', HEAD).decode().splitlines()
assert set(files) == {'brain/ssbot/combat/tactics/clapper_priority.py', 'brain/ssbot/train/forum_planner_policy.py', 'brain/tests/test_landing_exit.py'}
A.mkdir(exist_ok=True)
raw, blobs = {}, {}
for name in files:
    data = git('show', HEAD + ':' + name); raw[name] = data
    dest = A / 'source_delta' / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
    author = P / 'trees/P5' / name
    assert norm(data) == norm(author.read_bytes())
    blobs[name] = dict(git_blob=git('rev-parse', HEAD + ':' + name).decode().strip(), sha256=sha(data), normalized_sha256=sha(norm(data)), author_sha256=sha(author.read_bytes()))
test_count = sum(isinstance(x, ast.FunctionDef) and x.name.startswith('test_') for x in ast.parse(raw['brain/tests/test_landing_exit.py']).body)
save(A / 'SOURCE_PACKET_ORIGINAL.json', dict(at=NOW, source=HEAD, parent=s['current_source'],
    delta=blobs, source_delta_root=str(A / 'source_delta'), runnable_frozen_source=False,
    parent_packet=str(B / 'analysis/walk_rule418_20261113/SOURCE_PACKET_FIXED.json'),
    runtime_change_count=2, test_function_count=test_count, author_parametrized_test_report=28,
    author_mutants_report=24, author_affected_report=963, author_tests_rerun_by_Sol=False))

base = B / 'analysis/walk_rule418_20261113/source_fixed419'
arms, manifests, binding = {}, {}, {}
for arm in ['off', 'on']:
    folder = P / 'r' / ('p5_ep12_' + arm)
    d = json.loads((folder / 'RESULT.json').read_text(encoding='utf-8-sig'))
    m = json.loads((folder / 'CONFIGURATION_MANIFEST.json').read_text(encoding='utf-8-sig')); manifests[arm] = m
    assert d['exception'] is None and d['seed'] == 428636 and d['synthetic_from'] == 42144
    assert not any(x['f'] >= 42144 for x in d.get('forced_planner_ticks', []))
    for name, digest in m['source_sha256'].items():
        key = 'brain/ssbot/' + name; data = raw.get(key)
        if data is None: data = (base / key).read_bytes()
        assert sha(norm(data)) == digest, name
    events = [json.loads(l) for l in (folder / 'decisions_i0.chain.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    wire = next(e for e in events if e.get('frame') == 42145 and e.get('event') == 'transport_sent')
    assert wire['target'] == 42147 and wire['mask'] == (2097152 if arm == 'on' else 0) and wire['owner'] == 'plan'
    dec = [json.loads(l) for l in (folder / 'decisions_i0.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    dec = [x for x in dec if 42144 <= x.get('f', -1) <= 42221]
    owners = collections.Counter(x.get('owner') for x in d.get('rows', []) if x['f'] >= 42144)
    arms[arm] = dict(source_files_matched=len(m['source_sha256']), actual_wire=wire, owners=dict(owners),
        target_ids=sorted({x['tgt'] for x in dec}), first_model_hurt=d.get('first_model_hurt'), model_hits=d.get('model_hits'),
        unknown_frames=[x['f'] for x in dec if (x.get('clapper_landing_exit') or {}).get('unknown')],
        exit_frames=[x['f'] for x in dec if ((x.get('clapper_landing_exit') or {}).get('stance') or {}).get('exit') is not None])
    for name in ['RESULT.json', 'CONFIGURATION_MANIFEST.json', 'decisions_i0.chain.jsonl', 'decisions_i0.jsonl']:
        path=folder/name; binding[str(path)] = sha(path.read_bytes())
assert manifests['on']['source_sha256'] == manifests['off']['source_sha256']
assert manifests['on']['configs'] == manifests['off']['configs']
switch_diff = [k for k in manifests['on']['switches'] if manifests['on']['switches'].get(k) != manifests['off']['switches'].get(k)]
assert set(switch_diff) == {'SSBOT_FORUM_LANDING_EXIT','SSBOT_FORUM_CHAIN_BATCH','SSBOT_FORUM_CHAIN_PROBE','SSBOT_FORUM_CHAIN_BUDGET'}
save(A/'PRODUCTION_EVIDENCE_ORIGINAL.json',dict(at=NOW,source=HEAD,pair=arms,bindings=binding,switch_diff=switch_diff,
    finite_action_proof_accepted=True,source_review_accepted=False,scope='Production policy/planner/geometry/send pathway in model replay; not physical-game acceptance or saved HP; source domain still P2.'))

counter = dict(decision_x=46.,hero_x=40.,observed_face=-1,STATE_vx=-1.,STATE_vy=38.,body_box=[44.,3.,48.,7.],
    path_frames=90,landing_k=54,ballistic_root=45.10,jump_rule_s=-1,jump_rule_L=1.41,decided_landing=44.59,
    decided_branch='open',wall_rule_corrected=44.59,root_delta=-.51,
    method='Astra executed original P5 functions via AST; body_box/control fixed-input providers; no JIT/project startup/replay/P/game')
review=dict(at=NOW,source=HEAD,accepted=False,source_review_pending=True,
    reviewers=['Sol: Git/delta/test source and final-source production-action binding','gpt-6-astra xhigh /root/walk418_review: concentrated final model/input/lifecycle review'],
    P2=[dict(id='D423-WALL',where='clapper_priority.py177 branch open and215 WALL_ZONE gate',
        problem='open decided branch and open ballistic root still admit wall-push correction; violates no-wall-correction domain',counterexample=counter,
        required='Same-instance inst.dec[x], observed bound face, current root through existing wall_rule: changed root=>whole tick unknown, both stances unchanged. Missing/nonfinite decision x unknown; do not substitute inst.x0.')],
    critical_remaining_increments_accepted=['observed flipX/no fallback and persistent changed-face unknown','unknown/tracker/velocity/scene gates','target-vs-other trigger','separate stance/withdraw side and lifecycle','default off bypass'],
    source_packet=str(A/'SOURCE_PACKET_ORIGINAL.json'),production_evidence=str(A/'PRODUCTION_EVIDENCE_ORIGINAL.json'),
    formal_P_started=False,live_released=False,next_owner='Opus same-package minimal domain repair')
save(A/'SOURCE_REVIEW_ORIGINAL.json',review)

mail='''## seq364（#423同包）：ep12最终源动作已核；还差一处无需墙修正的适用域门，先补再P

844f6455正式交付已读。Sol核Git三文件增量/28参数化例源码（23个测试函数）和两臂最终240源LF绑定；963/24变异为作者报告，不重跑。P5 ep12 seed428636、SYN42144后forcing0、其它控制配置一致。42145开臂plan实际transport_sent R→42147，关0；开78拍全planner、目标1577066不变、无模型hurt/hit，关42188模型刀和42201锤。42195–42199缺scene时确实unknown保留；有限动作证据核收，不当实机/净收益。此阶段尚未启动正式P/游戏。

Astra xhigh最终源集中核还有一个P2：branch=open + 当前无墙弹道root在WALL_ZONE，仍不能证明无需墙推。原函数AST最小反例已算：决定点x46、hero40、观测face−1，STATE vx−1/vy38、body=(44,3,48,7)；jump_rule经push_l给L1.41/决定落点44.59，所以jump_branch=open。body_path90帧在第54帧落地、当前root45.10，现门仍接受；wall_rule(46,45.10,−1)=44.59，仍要改−0.51u。只是确定模型适用域反例，不编实机HP归因。

请同包最小补修：用同实例决定点inst.dec["x"]、已绑定观测face和当前预测root核既有wall_rule；会改root就整拍unknown，主stance/withdraw保持。决定点缺失/非有限也unknown，不用inst.x0（它是招式开始锚，不是决定点；生产来源attack_range.py约692）。给共用测试夹具补真实dec输入，别为旧夹具放宽门；一个上述反例加一个确实无需墙修正的open正例足够，原28例相关复用，不重跑963/墙批/矩阵。其它限定增量Astra未见新P0–P2。

固定修复源后，ep12若键不变复用这次完整工程轨迹，补该窗最终源绑定/正常分支动作记录即可，勿重跑三对或42影子。Sol核修复后继续同源开关有限P；既有entry_v3和fixture截止可复用，不新造入口/精确帧包。证据analysis/landing_exit423_20261114/SOURCE_REVIEW_ORIGINAL.json、SOURCE_PACKET_ORIGINAL.json、PRODUCTION_EVIDENCE_ORIGINAL.json；原844结果保留。

本信不改默认关、不增实机；当前已核source仍7a43c1ed，candidate844待这处修正。你继续独占实现，Sol不写控制码。写信/单次信号/实收/实际改好分开核；原游戏暂停/停止批/AA/原录像保持。

---

'''
path=B/'sol/TO_OPUS.md';text=path.read_text(encoding='utf-8-sig');assert '## seq364' not in text
header,rest=text.split('\n',1);t=path.with_suffix('.tmp');t.write_text(header+'\n\n'+mail+rest.lstrip('\n'),encoding='utf-8');t.replace(path)
s.update(phase='LANDING_EXIT423_SOURCE_P2_DOMAIN_REPAIR_LIVE_PAUSED',last_scanned_opus=423,candidate_source=HEAD,
    source_review_pending=True,pending_opus='Same #423 seq364: no-wall-correction domain guard using inst.dec.x; fixed source pending',
    active_implementation={'owner':'Opus existing author','reviewer':'Sol + focused Astra xhigh','scope':'Same default-off landing exit package; one source domain repair',
        'stage':'repair feedback written; actual repair start not yet verified','formal_delivery_pending':True,'coordination_seq':364},
    next_phase='Opus fixes same-package domain gate plus narrow regression; Sol reviews increment/fixed-source action binding then affected formal P/cleanup. No game resume.')
save(B/'sol/STATUS.json',s)
save(R/'RECEIPT423.json',dict(at=NOW,opus_number=423,source=HEAD,source_accepted=False,source_review_pending=True,
    finite_action_evidence_accepted=True,source_review=str(A/'SOURCE_REVIEW_ORIGINAL.json'),reply_seq=364,
    mail_written=True,wake_enqueued=False,listener_received=False,actual_author_start_verified=False,
    formal_P_started=False,formal_P_completed=False,live_released=False))
path=R/'RECEIPT422.json';old=json.loads(path.read_text(encoding='utf-8-sig'));old.update(actual_author_start_verified=True,
    author_work_evidence='Fixed production delivery #423 844f6455',stage_completed_with_source_review_pending=True,closed_by=423);save(path,old)
path=ROOT/'docs/plans/forum_clapper_plan.md';text=path.read_text(encoding='utf-8-sig');assert '### 7.357 ' not in text
text+='''

### 7.357 #423默认关实现与最终源动作已核，仍缺墙推适用域一门，seq364同包补修（11-14）

844f6455父7a，三文件增量仅priority/policy日志和新tests；Sol核28参数化例源码（23函数），963/24变异为作者报告、不重跑。两臂最终240源LF绑定、seed428636/SYN42144后forcing0、同控制profile；42145开启plan实际R→42147，关0。开78拍全planner、同目标、无模型hurt/hit；关42188模型刀、42201锤。42195–42199缺geo确实unknown，工程动作核收，非实机收益。

Astra xhigh集中最终源核出一个P2：open分支+当前root在WALL_ZONE仍可需墙推。原函数AST反例：决定x46/hero40/face−1，vx−1/vy38/body=(44,3,48,7)；决定L1.41、落点44.59使branch=open；body_path第54帧root45.10，现门接受，而wall_rule仍改为44.59（−0.51u）。仅模型适用域反例，不归因真实损血。要求同实例inst.dec.x+观测face核wall_rule，若改写或决定点缺/非有限则整拍unknown、两个站位保持；inst.x0不能替代决定点。只补该反例/正常open及真实dec夹具，复用其它证据，不重跑963/墙批/42。

其它flipX/缺输入/未知整拍/目标区分/双输出锁侧清理/默认关未见新P0–P2。analysis/landing_exit423_20261114/SOURCE_PACKET_ORIGINAL、SOURCE_REVIEW_ORIGINAL、PRODUCTION_EVIDENCE_ORIGINAL与committed388_20261111/RECEIPT423登记；seq364写信/单次信号/实收/开工分别核。current仍7a、candidate844待修，正式P尚未起；修后Sol续同源开关有限P/清理，无游戏授权。暂停/停止批/冻结AA/原录像保持。
'''
path.write_text(text,encoding='utf-8')
print(json.dumps(dict(reply_seq=364,source=HEAD,source_accepted=False,production_manifest_matched=240,formal_P_started=False),ensure_ascii=False))
