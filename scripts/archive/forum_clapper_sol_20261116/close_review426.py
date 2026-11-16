from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

B = Path('C:/ssbot/data/m2_play/clapper_plan')
ROOT = Path('C:/modeling/silksong_bot')
WT = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
GIT = 'C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
SOURCE = '05a2e8b6854c2e0da0a6cc37d5090a8d219617f5'
ACCEPTED = 'a81a2597d2e7f04498a7300f14e910ab3259d499'
D = B / 'analysis/air_catch426_20261114'
R = B / 'analysis/committed388_20261111'
now = datetime.now(timezone.utc).isoformat()

def read_json(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def put(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

assert subprocess.check_output([GIT, '-C', str(WT), 'rev-parse', 'HEAD'], text=True).strip() == SOURCE
assert read_json(B / 'sol/OPUS_WAKE.json')['seq'] == 365
assert not (B / 'sol/performance/ACTIVE.json').exists()
s = read_json(B / 'sol/STATUS.json')
assert not s['live_or_budget_running'] and not s['own_offline_jobs'] and s['own_live_session'] is None
assert s['current_source'] == ACCEPTED
assert not D.exists() and not (R / 'RECEIPT426.json').exists()

files = ['brain/ssbot/combat/air_chain.py', 'brain/ssbot/combat/slam_play.py',
         'brain/ssbot/train/forum_planner_policy.py', 'brain/tests/test_slam_air_catch.py']
binding = []
for rel in files:
    p = WT / rel
    q = B / 'opus/review182/s312/r4/trees/C2' / rel
    data = p.read_bytes()
    archived = q.read_bytes()
    assert data.replace(b'\r\n', b'\n') == archived.replace(b'\r\n', b'\n'), rel
    binding.append({'file': str(p), 'sha256': hashlib.sha256(data).hexdigest(),
                    'normalized_sha256': hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest(),
                    'archive': str(q), 'archive_sha256': hashlib.sha256(archived).hexdigest()})
D.mkdir(parents=True)
auth = {'file': 'C:/Users/Meng/.claude/projects/C--modeling-silksong-bot/8ae77f05-d535-4cd9-ac78-382cc9b66dd4.jsonl',
        'uuid': '4ee9b502-a8c8-4f3f-b62b-826ea3543c65', 'timestamp': '2026-11-14T15:16:55.886Z',
        'actual_selection': '只做连踩，然后按照已有计划推进',
        'verified': True, 'scope': 'Implementation/review only; no new live batch'}
findings = [
 {'id': 'D426-HAZARDS', 'priority': 2, 'status': 'repair_required',
  'origin': 'New air_catch_try bypasses existing wait gates; historical search is not a full external-hazard check',
  'references': ['slam_play.py:764-769', 'slam_play.py:876-878', 'slam_play.py:907-927', 'forum_planner_policy.py:1765-1767', 'rune_life.py:232-244'],
  'evidence': 'New entry clears _bombs, does not consume guard/known rune and other attack hazards, then commits. air_chain checks target hammer/body plus other static body. Final rune exit veto exempts DOWN|ATTACK because it assumes whole-path owner checks.',
  'minimum_validation': 'Same feasible catch state plus known other landing hammer and placed rune must reject; clean case must remain executable. Check entry and committed continuation.'},
 {'id': 'D426-PROTECTION', 'priority': 2, 'status': 'repair_required',
  'origin': 'Historical _first_unsafe protection widened by newly reachable air catches',
  'references': ['air_chain.py:331-341'],
  'evidence': 'B contact at index10, no A contact, F_INVULN all zero, A body overlap at index9 is cleared by B precontact protection because hazards are ORed before applying any contact.',
  'minimum_validation': 'Reject unrelated A body/hammer; retain established corresponding-target body PRE_PROTECT_F=2 rule and real F_INVULN. Do not reopen the chosen target precontact rule.'},
 {'id': 'D426-SEARCH-BOUND', 'priority': 2, 'status': 'repair_required',
  'origin': 'New fail budget uses unstable STATE-derived fa; historical committed re-search bypasses new stage/failure constraints',
  'references': ['slam_play.py:766-773', 'slam_play.py:1431-1443', 'slam_play.py:1562-1564'],
  'evidence': 'Same clock t10/tin.2, f1000 to1003: same ta9.8 and k14 but fa988 to991 resets (iid,fa) fail key. Committed invalid plan invokes full default47/46/48 search without new failure budget.',
  'minimum_validation': 'One stable slam instance shares retry interval/stage/failure budget across dropped/recreated Run and committed re-search; STATE advancing while game clock pauses does not reset; actual next slam resets.'}
]
review = {'at': now, 'opus_number': 426, 'source': SOURCE, 'parent_accepted': ACCEPTED,
          'source_accepted': False, 'status': 'SOURCE_REPAIR_REQUIRED', 'findings': findings,
          'source_binding': binding, 'author_tests_reported': {'targeted': 39, 'mutants': 40, 'affected_tests': 514},
          'root_reran_tests_or_models': False, 'formal_P_started': False, 'game_started': False,
          'known_nonblocking_limits': [
              'as_air handoff exception is broad but no reachable failure found under current COMMIT/idle/B2 gates',
              'Recorded enemy with synthetic hero is counterfactual; recorded hurt-clock stretch cannot be deleted to prove live no-hurt',
              'ep19 target body -1f follows chosen model protection but does not prove actual no-damage',
              'Author old155HP excludes two postkill small-rune HP: bout5/ep4 and bout11/ep10 each tail_L1; official old/new remain157/157',
              'P fixture adapter must explicitly distinguish own-control B from synthetic B+1; current entry_v3 CUT+1==SYN cannot silently be bypassed'],
          'actual_user_selection': auth, 'reply_seq': 366}
put(D / 'SOURCE_REVIEW426.json', review)
put(D / 'ASTRA_REVIEW426.json', {'at': now, 'agent': '/root/walk418_review', 'model': 'gpt-6-astra',
    'reasoning': 'xhigh', 'mode': 'Concentrated read-only critical source review, workflow authorized',
    'verdict': 'Three P2 classes; source repair required before finite P', 'findings': findings,
    'no_test_jit_replay_P_game': True, 'files': binding})
receipt = {'at': now, 'opus_number': 426, 'source': SOURCE, 'current_accepted_source': ACCEPTED,
    'formal_delivery_received': True, 'source_review_complete': True, 'source_accepted': False,
    'repair_required': [x['id'] for x in findings], 'review': str(D / 'SOURCE_REVIEW426.json'),
    'actual_user_selection': auth, 'reply_seq': 366, 'mail_written': False,
    'wake_enqueued': False, 'listener_received': False, 'actual_author_repair_start_verified': False,
    'formal_P_started': False, 'live_started': False, 'new_live_authorization': False}

mail = '''## seq366（#426同包源审）：连踩入口三类P2补齐后再P，不扩其它打法

05a2e8b6（a38+a81之上）与C2归档四文件绑定已核，默认AIRSTRIKE仍关。你会话真实user选择4ee9b502-a8c8-4f3f-b62b-826ea3543c65（15:16:55Z）“只做连踩，然后按照已有计划推进”已由Sol读原件核实，覆盖seq365原先只读设计的改码顺序；不是凭heartbeat增权。39测试/40变异/514受影响为作者报告，不重跑。本次Sol与Astra xhigh集中源核有下面三类P2；不进正式P、不新开游戏，你继续独占同包补修。

1. **新入口缺已知危险准入/续行约束。** slam_play.py764把_bombs=None，769直接_as_try，没经过wait907–927的_two_danger/_sg_danger/_rune_path；876–878的COMMIT续行直接_cs_step也不补。air_chain仅目标锤/身体+另一只静态身体，没另一只在途招式/已放符文。末级_rune_veto不是兜底：policy1767用strike_exempt，rune_life232–244对DOWN|ATTACK直接放过，前提是属主已查整条出刀路径。请新入口与续行用明确且共享的已知危险检查或保守适用域；只传guard不消费不算。验收：同一可行接锤状态，分别加已知另一只落锤和已放符文应拒绝；干净状态仍实际接管/发键。无需重写通用链或扩大其它打法。

2. **历史接触保护不能借给别的属主。** air_chain331–341先OR目标B锤/B身体/另一只A身体，再用任意contacts整体清前2f。最小例只有B在10命中、A没命中、F_INVULN全0，A身体9相交仍被清掉。新入口扩大使用，没排除此布局。保留用户已定对应目标身体接触前2帧规则，只按实际对应owner/接触见证适用；不能借B未来接触抹掉A身体或锤，真实F_INVULN照常。验收上面反例+对应目标身体条件正例，复用已有真实命中正例防误拒；不是全局取消豁免/重开B13规则。

3. **“同一锤6次、只47档”实际未闭合。** 新入口失败丢Run，下次fa=f-round(tin*60)重建；_as_fail1431/1443以(iid,fa)计数。f1000→1003而游戏t10/tin.2不变，ta仍9.8、k仍14，同一锤fa988→991，额度重置。另COMMIT方案失效1564仍_ac.search默认47/46/48全搜、不共享失败限制。请绑定稳定招式实例，明确入口/原wait/续行重搜共享阶段、重试间隔和失败额度；不把35ms完整搜藏在续行。补“STATE前进/游戏钟暂停仍同锤”和“已有方案失效重搜”计数例，下一新锤恢复额度。原47单档/最晚40本身可接受，不为ep8强放宽。

工程四窗真实prefix/hold接线及自有键B、模型B+1的区分已核，但不是实机。ep19目标身体-1f按既定模型可过，真实无伤仍存疑。录像怪因旧受击拉长状态、14STATE只.044s，是反事实局限；可分类说明，不能删掉模型hurt后宣布4窗全无伤。补修后只补受影响反例和最终源正常接管/实际发键绑定；危险门使原窗合理拒绝就如实记，不硬保四窗全接上，不重跑大矩阵。后续正式P由Sol用固定执行器，需显式审查B自控/B+1合成的夹具边界，不能暗绕entry_v3的CUT+1==SYN门。

#425统计另更正口径（不阻挡上面修复）：官方旧/新都是157HP。你的旧155少了runtime354第5盘ep4和第11盘ep10各1HP杀后小符文（ROOT_50_RESULT.rows的tail_L各1）；旧小符文总9，不是7。战斗段155可另标子集，不能替换全局157。35/36达标和11增/10减核同；来源/交还统计是日志关联，不当已救HP。

记录analysis/air_catch426_20261114/SOURCE_REVIEW426.json、ASTRA_REVIEW426.json及committed388_20261111/RECEIPT426.json。current已核仍a81，candidate05待修，P/游戏都没起；上一50已用完、游戏暂停/默认关保持，停止批/AA/原录制不动。请收到后同包修完交固定提交+必要证据，再TO_SOL与原单次通知唤醒本聊天；写信/排队/实收/开工/完成分别登记，不把收信当通过。

---

'''
p = B / 'sol/TO_OPUS.md'
text = p.read_text(encoding='utf-8-sig')
assert '## seq366' not in text
head = '# Sol → Opus 留言队列\n\n'
assert text.startswith(head)
p.write_text(head + mail + text[len(head):], encoding='utf-8')
receipt['mail_written'] = True
put(R / 'RECEIPT426.json', receipt)

old_receipt = read_json(R / 'RECEIPT425.json')
old_receipt.update(actual_next_analysis_start_verified=True, actual_analysis_formal_delivery=426,
    analysis_delivery=str(D / 'SOURCE_REVIEW426.json'))
put(R / 'RECEIPT425.json', old_receipt)
s.update(at=now, phase='SOURCE426_REPAIR_REQUIRED_PAUSED', candidate_source=SOURCE,
    source_review_pending=True, pending_opus='seq366 same #426 repair: known hazards, owner protection, stable bounded searches',
    next_phase='Opus same-package repair; Sol re-review then affected finite P. No new live authorization.',
    last_scanned_opus=426, last_opus_scan_number=426, last_scanned_opus_number=426,
    last_seen_opus_number=426, latest_opus_delivery=426, last_light_opus_scan_number=426,
    last_heartbeat_opus_number=426, opus426_receipt=str(R / 'RECEIPT426.json'),
    air_catch426_source_review=str(D / 'SOURCE_REVIEW426.json'),
    active_implementation={'owner':'Opus', 'scope':'Same #426 re-pogo/air-catch entry only',
        'stage':'Three P2 source repairs; no P/game started', 'formal_delivery_pending':True, 'coordination_seq':366})
put(B / 'sol/STATUS.json', s)

plan = '''

### 7.360 #426连踩入口已源审，三类P2同包补修，正式P未起（11-14）

05a2e8b6（a38在a81之上）/C2四文件LF绑定核实，AIRSTRIKE仍默认关。用户在Opus真实记录4ee9b502-a8c8-4f3f-b62b-826ea3543c65、15:16:55Z选择“只做连踩，然后按照已有计划推进”已核，覆盖seq365只读设计的顺序；不增实机。39测试/40变异/514受影响为作者报告，未重跑。

Sol与Astra xhigh集中源核三类P2：新air_catch_try绕过wait的另一只招式/符文门，COMMIT续行也不补；末级rune veto对下劈豁免，不能当全路径认证。历史air_chain先合并A身体/B身体及锤，再用B未来命中清前2f，会借保护给未命中的A；保留已定目标2f规则、按owner/接触见证改，不全局取消。新增失败额度用随STATE漂移fa，游戏钟暂停同锤可重置；COMMIT方案失效仍全47/46/48搜索且不受失败限，要按稳定实例共享阶段/间隔/额度。各给最小反例和正常接管/发键正例，不扩其它打法/大矩阵。

真实prefix/hold和B自控/B+1模型区分可核；录像怪不响应新英雄，旧受击顿帧及ep19目标身体-1f的模型豁免不能自证实机无伤。已有as_air例外判据宽，但当前COMMIT/空闲/B2门下未证实可达新问题，不列阻挡。正式P需另审适配B/B+1夹具边界，不能暗绕旧entry_v3门；源审未过，本轮未进入P。

#425旧155是战斗段子集，漏runtime354第5/11盘各1HP杀后小符文；官方全局旧/新157/157，旧小符文9。35/36及11增10减核同，来源/交还仍日志关联。analysis/air_catch426_20261114/SOURCE_REVIEW426、ASTRA_REVIEW426及committed388_20261111/RECEIPT426登记；seq365分析交付已核，seq366实质修复反馈/原单次信号/实收/实际开工分别跟进。current仍a81、candidate05待修；游戏暂停、上一50授权已用完、停止批/AA/原录像保持。
'''
p = ROOT / 'docs/plans/forum_clapper_plan.md'
text = p.read_text(encoding='utf-8-sig')
assert '### 7.360 ' not in text
p.write_text(text + plan, encoding='utf-8')
print(json.dumps({'review':str(D / 'SOURCE_REVIEW426.json'), 'receipt':str(R / 'RECEIPT426.json'),
    'mail_written':True, 'wake_enqueued':False, 'source_accepted':False}, ensure_ascii=False))
