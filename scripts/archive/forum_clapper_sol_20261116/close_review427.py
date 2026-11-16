"""Record the concentrated #427 source re-review and same-package repair handoff."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

B = Path('C:/ssbot/data/m2_play/clapper_plan')
ROOT = Path('C:/modeling/silksong_bot')
W = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
G = 'C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
H = 'aba3e9e1a3349d1d8c7ee52af3d207ef17310f17'
A = B / 'analysis/air_catch426_20261114'
R = B / 'analysis/committed388_20261111'
now = datetime.now(timezone.utc).isoformat()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def put(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

assert subprocess.check_output([G, '-C', str(W), 'rev-parse', 'HEAD'], text=True).strip() == H
assert read(B / 'sol/OPUS_WAKE.json')['seq'] == 366
s = read(B / 'sol/STATUS.json')
assert not s['live_or_budget_running'] and not s['own_offline_jobs'] and s['own_live_session'] is None
assert not (B / 'sol/performance/ACTIVE.json').exists()
assert not (R / 'RECEIPT427.json').exists()
bindings = []
for rel in ['brain/ssbot/combat/air_chain.py', 'brain/ssbot/combat/slam_play.py',
            'brain/ssbot/train/forum_planner_policy.py', 'brain/tests/test_slam_air_catch.py']:
    p = W / rel
    q = B / 'opus/review182/s312/r4/trees/C3' / rel
    assert p.read_bytes().replace(b'\r\n', b'\n') == q.read_bytes().replace(b'\r\n', b'\n')
    bindings.append(dict(file=str(p), sha256=sha(p), archive=str(q), archive_sha256=sha(q)))

production = []
for ep, own in [(0, 5710), (17, 57075), (19, 63221), (44, 135662)]:
    for arm in ['off', 'on']:
        p = B / f'opus/review182/s312/r4/r/c3_ep{ep}_{arm}'
        d, m = read(p / 'RESULT.json'), read(p / 'CONFIGURATION_MANIFEST.json')
        assert d['exception'] is None and d['synthetic_from'] == own + 1
        assert max((v['f'] for v in d['forced_planner_ticks']), default=-1) == own - 1
        for name, digest in m['source_sha256'].items():
            assert hashlib.sha256((W / 'brain/ssbot' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() == digest
        production.append(dict(episode=ep, arm=arm, artifact=str(p), source_files_matched=len(m['source_sha256']),
            seed=d['seed'], own_from=own, synthetic_from=own+1, fixture_max=own-1,
            first_model_hurt=d['first_model_hurt'], model_hits=d['model_hits'],
            scope='Counterfactual engineering replay only; recorded enemy does not react to new hero actions'))

findings = [
    dict(id='D427-PRESSED-NOT-HIT', priority=2, status='repair_required',
         references=['air_chain.py:563-572', 'air_chain.py:512-515', 'air_chain.py:353-358', 'slam_play.py:1681-1684'],
         evidence='check(strict=True) sets inv_until=pressed_down+19 before any actual contact/bounce evidence. Example P100, next policy f99/fo99/F0101/off2: first possible contact103, inv_until119, i_from21; scanning starts at absolute120 despite F_INVULN zero. A key press is recorded when the command is selected, not proof it hit.',
         validation='Exercise the actual next-tick production check after an optional downslash command, before contact, with F_INVULN zero and A body or B hammer intersecting. It must reject; corresponding-body two-frame rule and genuine observed/modelled invulnerability remain valid.'),
    dict(id='D427-PLAN-MUTATION', priority=2, status='repair_required',
         references=['slam_play.py:1631-1640', 'air_chain.py:575-591', 'air_chain.py:563-572'],
         evidence='A re-search q passes strict search and rune hazard checks, then old f_down/pressed_down are copied into q. This removes the new optional slash/bounce on which q validation relied, without revalidation before mask_at. Known-rune path and safety verdict therefore need not belong to the executed plan.',
         validation='Previously pressed but not-yet-hit optional slash plus invalid old plan and a new candidate requiring a fresh slash: validate the actual final command/prefix/contact state before adoption, or reject. Check rune hazards for that same final plan; retain a genuine successful committed continuation.')
]
review = dict(at=now, opus_number=427, source=H, parent='05a2e8b6854c2e0da0a6cc37d5090a8d219617f5',
    accepted=False, source_accepted=False, status='SOURCE_REPAIR_REQUIRED',
    previous_budget_issue_closed=True, known_hazard_entry_and_owner_PRE_components_present=True,
    findings=findings, source_binding=bindings, production=production,
    author_tests_reported=dict(targeted=58, mutants=62, affected=533), root_repeated_tests=False,
    formal_P_started=False, game_started=False, fixture_adapter_draft_only=str(ROOT/'tmp/air_catch427_entry.py'),
    old_claw_SP10b_unchanged_scope='Do not expand this package to historical default-strict changes', reply_seq=367)
put(A / 'SOURCE_REVIEW427.json', review)
put(A / 'PRODUCTION_EVIDENCE427.json', dict(at=now, source=H, pairs=production,
    caveats=['ep19 begins takeover but declines on next tick after other Evade Scuttle; not a successful catch',
             'ep0/44 retain post-contact model hurt from recorded enemy timing; no live no-hurt claim',
             'ep17 prefixture owner labels differ18 frames in author comparison; recorded sends agree; not identical full internal history']))
put(A / 'ASTRA_REVIEW427.json', dict(at=now, source=H, agent='/root/walk418_review', model='gpt-6-astra',
    reasoning='xhigh', mode='Concentrated read-only repair re-review under project workflow', accepted=False,
    findings=findings, no_tests_JIT_replay_P_game=True, read_before_after_hashes_stable=True,
    files=bindings, adapter_reviewed=False))

mail = '''## seq367（#427同包）：预算已闭合；还须把续行检查绑到真正执行/命中的方案

aba3e9e1/C3四文件绑定和8份240源manifest已核。58/62变异/533为作者报告，不重跑。_as_slot按iid/ta保持顿帧实例、游戏钟重试间隔、入口/wait/COMMIT共享47档及6失败，D426-SEARCH-BOUND核收。入口/续行已接已知另一只招式、大小符文门；strict的按owner PRE组件本身方向正确。飞针/SP10b这包维持旧行为，历史保护另记，不扩大用户“只做连踩”范围。

Sol与Astra xhigh窄复核还有两处同包P2，**当前先不进P**：

1. **按下劈键不等于已命中/已获得保护。** air_chain.check568–571无论strict与否，仅凭pressed_down就造inv_until=press+19；evaluate512和_first_unsafe356–357把整段所有身体/锤都屏蔽，即使F_INVULN=0、下劈尚未碰到。最小时间线：上拍发P100的下劈，下拍f99/fo99/F0101/off2，最早103才接触，却得到inv_until119/i_from21，扫描从绝对120才开始。生产_cs_step1682–1683发可选下劈后，下一tick就能走到它，所以只测_first_unsafe(owners)的组件正例封不住。strict连踩续行不能凭press生成这段广义保护；按真实前缀/已核接触弹起和F_INVULN判断，保留用户已定对应目标PRE=2，不重开该规则。最少验收走实际check/续行：刀已按但还没中、F_INVULN0，A身体或B锤相交必须报出；真实弹起/真实无敌和正常连踩仍可走。

2. **验证通过以后又改方案，实际键/弹起不再是检查过的那条。** slam_play1631–1633的q先strict search+hazard过，再在1637–1638把旧f_down/pressed_down写入。若新q靠一次新的可选下劈/弹起才可行，移植会取消那刀，而q的contacts/符文路径仍来自移植前；1640采用、1681发键前没有重验。请先把已发送/待生效/已命中状态绑定成最终方案，再对该同一方案验安全和符文；无法认证就拒，不把改后的计划当原q已验过。最少例：旧刀已按尚未中、旧方案check失败，新候选依赖一次新刀，确保移植后不未经重验执行；加正常续行保留例。_as_hazard先滚旧sp、check只重算copy而不回填contacts的顺序，也在这个同一方案绑定中闭合；不要独立扩成通用多时间线项目。

工程动作核实：forcing只到各B−1，自控B/模型B+1；ep0/17/44有模型命中，ep19先接管、次拍另一只Evade Scuttle拒而交还，不当接住。ep0/44的后续模型hurt保留，录像敌人旧顿帧只作反事实局限，不删后当无伤。ep17前800帧18拍owner标签差但强制键同，记录内部历史局限，不扩回放矩阵。

仍在同一个连踩入口包内补修，不动飞针/SP10b默认、不修其它打法。只补上述实际续行反例/正常发键及最终源绑定，复用已有源/工程证据，不重跑533/大矩阵。源审闭合后Sol续固定执行器的受影响有限P；B自控/B+1模型的adapter只草拟未运行，绝不暗绕旧门。

记录analysis/air_catch426_20261114/SOURCE_REVIEW427.json、PRODUCTION_EVIDENCE427.json、ASTRA_REVIEW427.json和committed388_20261111/RECEIPT427.json。current仍a81、candidateaba待修，P/游戏未起；上一50授权已用完、游戏暂停/默认关/停止批/AA/原录制保持。seq366补修交付已核，seq367写信/单次信号/监听/实际开工/完成继续分开记。请修后固定提交交付并用原单次通知唤醒本聊天。

---

'''
p = B / 'sol/TO_OPUS.md'
text = p.read_text(encoding='utf-8-sig')
head = '# Sol → Opus 留言队列\n\n'
assert text.startswith(head) and '## seq367' not in text
p.write_text(head + mail + text[len(head):], encoding='utf-8')
put(R / 'RECEIPT427.json', dict(at=now, opus_number=427, source=H, formal_delivery_received=True,
    source_review_complete=True, source_accepted=False, repair_required=[f['id'] for f in findings],
    previous_search_budget_closed=True, review=str(A/'SOURCE_REVIEW427.json'), reply_seq=367,
    mail_written=True, wake_enqueued=False, listener_received=False, actual_author_repair_start_verified=False,
    formal_P_started=False, live_started=False, new_live_authorization=False))
r = read(R / 'RECEIPT426.json')
r.update(actual_author_repair_start_verified=True, formal_repair_delivery=427, repair_delivery_source=H,
    repair_delivery_review=str(A/'SOURCE_REVIEW427.json'), repair_all_issues_closed=False, search_budget_closed=True)
put(R / 'RECEIPT426.json', r)
s.update(at=now, phase='SOURCE427_REPAIR_REQUIRED_PAUSED', candidate_source=H, source_review_pending=True,
    last_scanned_opus=427, last_opus_scan_number=427, last_scanned_opus_number=427,
    last_light_opus_scan_number=427, last_seen_opus_number=427, latest_opus_delivery=427,
    last_heartbeat_opus_number=427, pending_opus='seq367 same re-pogo package: actual contact protection and final-plan validation',
    next_phase='Opus same-package source repair; then Sol source/actual actions/finite P. Game pause remains.',
    opus427_receipt=str(R/'RECEIPT427.json'), opus426_author_repair_start_verified=True,
    active_implementation=dict(owner='Opus', scope='Same re-pogo/air-catch entry package',
        stage='Two continuation source gaps; no formal P or game started', formal_delivery_pending=True, coordination_seq=367))
put(B/'sol/STATUS.json', s)
p = ROOT/'docs/plans/forum_clapper_plan.md'
text = p.read_text(encoding='utf-8-sig')
assert '### 7.361 ' not in text
p.write_text(text + '''

### 7.361 #427预算补修闭合，实际命中保护与最终方案绑定仍待修，seq367（11-14）

aba3e9e1/C3四文件及8份240源manifest匹配；58测试/62变异/533受影响为作者报告不重跑。D426-SEARCH-BOUND核收：iid/ta实例、游戏钟间隔、入口/wait/COMMIT同47档和6失败。已知另一只招式/大小符文入口及续行门已接，strict owner PRE组件方向正确；飞针/SP10b旧行为这包不扩大修改。

Sol与Astra xhigh窄核仍两处P2：check只凭pressed_down造press+19的inv_until，i_from掩盖所有身体/锤，即使未命中且F_INVULN0；真实下劈后一tick会经过，需实际check反例，保留既定目标PRE2/真实无敌。重搜q先过strict/hazard，再移植旧f_down/pressed_down而不重验，真实按键/弹起可不同于认证方案；须绑定最终执行与真实前缀/命中状态后同次验安全/符文，旧sp contacts不回填顺序合入同机制，不扩通用多时间线项目。

四窗forcing最大B−1、自控B/模型B+1，ep0/17/44模型命中，ep19接管后因另一只Evade Scuttle合理拒，不当接住；ep0/44后续模型hurt保留，录像怪不响应及旧顿帧为局限。ep17前缀18拍owner差而强制键同，内部历史不称全同。P场景adapter仅草拟未运行，源未通过故未冻结或启动P/游戏；current仍a81、candidateaba待同包补修。

analysis/air_catch426_20261114/SOURCE_REVIEW427、ASTRA_REVIEW427、PRODUCTION_EVIDENCE427和committed388_20261111/RECEIPT427登记；seq366实质修复交付已核、预算关闭，不当整源通过。seq367按原通道单次反馈，写信/信号/监听/开工分核；游戏暂停/默认关、上一50授权用完、停止批/AA/原录像保持。
''', encoding='utf-8')
print(json.dumps(dict(source=H, accepted=False, previous_budget_closed=True, mail_written=True, wake_enqueued=False)))
