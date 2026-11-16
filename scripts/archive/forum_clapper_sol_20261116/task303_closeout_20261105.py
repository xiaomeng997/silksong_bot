import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess

M = Path('C:/modeling/silksong_bot')
W = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
TV = Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/task179_1263e9e3_20261105'
GIT = 'C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
SOURCE = '1263e9e398859b0fa98e6d3141ac955288e05059'
REL = 'docs/plans/forum_clapper_plan.md'

def git(root, *args):
    return subprocess.check_output([GIT, '-C', str(root), *args], text=True, encoding='utf-8').strip()

def readj(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def atomic(path, data):
    temp = path.with_name(path.name + '.sol303.tmp')
    temp.write_bytes(data)
    os.replace(temp, path)

def writej(path, obj):
    atomic(path, (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))

audit = readj(R / 'p_v2/ROOT_P_AUDIT.json')
status_path = B / 'sol/STATUS.json'
status = readj(status_path)
wake = readj(B / 'sol/OPUS_WAKE.json')
assert wake['seq'] == 219, wake
assert not status['live_or_budget_running'] and not status.get('own_offline_jobs')
assert audit['source'] == SOURCE and audit['integrity_pass'] and audit['functional_path_pass']
assert audit['critical_J_and_downslash_point_pass'] and not audit['complete_scheduling_gate_pass']
assert readj(R / 'p_v2/FINALIZED.json')['cleanup_verified']
assert git(W, 'log', '-1', '--format=%H', '--', 'brain/ssbot') == SOURCE
heads = {}
for root in (M, W, TV):
    assert not git(root, 'status', '--porcelain', '--untracked-files=no'), root
    heads[str(root)] = git(root, 'rev-parse', 'HEAD')
raw = (M / REL).read_bytes()
assert all((root / REL).read_bytes() == raw for root in (W, TV))
text = raw.decode('utf-8')
assert '进度7.169' not in text
lines = text.splitlines()
assert '当前进度（11-05，7.168）' in lines[2]
lines[2] = '2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-05，7.169）：178有限自然姿态现场验收已闭合；179主翻越/moving stomp仍未覆盖。1263e9e3修正后完整212拍P实际走到新Slam实例，首J11.5565ms/下劈12.2482ms在原有限点界内；4个较慢的中性/保持键拍仍待按真实HF/前缀及完整串行时序作有限分类，不签新game gate。Sol测量适配器首版错把新脚本发包强制为旧ordinary键，原结果完整保留并作废；已改适配器并重新匹配启动核验，执行器与控制源未改。**'
section = '''

#### 1263新实例接刀212拍P实测核收；只补慢拍调度边界，不扩179打法（11-05，进度7.169）

analysis/task179_1263e9e3_20261105/p_v2/ROOT_P_AUDIT.json：真实worker50844、field48444，P0–15/High/Numba4/GetProcessInformation EcoQoS关闭。连续2524..2735实际212调用、protocol2 trace完整、0overflow、0外来/新签名/异常；710加载源绑定同。功能断言明确2683 owner=slam/0、2699 slam/J、2720 slam/A+D，首次差异2683且之后无强制脚本键；2732为模型续推增加的一拍，不冒称新观测现场STATE。2683后英雄/HF为模型、敌人为录制条件、receive合成，原严格无hit及2728 modelhurt保留，不据此签实际命中或安全出口。

首J2699整拍11.5565ms、出刀2720整拍12.2482ms，均低于原历史lag p99=15.782995及保留reserve对应13.550338ms有限点；不是未来保证。212拍峰17.6957ms。超过该点的四拍是2564 chain/0=17.6957、2683 slam/0=15.9224、2696 slam/R=16.9741、2704 slam/保持J=13.5568。2564/HF与前缀已为0；2696已实际保持R；2704已保持J；这些事实不自动证明串行排队无影响。2683仍实际保持L，发0是释放边沿，不能称瞬间刹车或与重复0等价。接下来同179仅核这四拍及必要后继，优先从实际HF/已发前缀证明重复包是否等价，必要用原0/1/2帧迟应用小边界；保留原ta/J/出刀绝对时钟、所有中间拍测量成本、最新STATE消费，不整体顺延旧键、不降低余量、不另造新优化/大矩阵。完整scheduling gate仍false。

本次P首版p_v1因Sol通用adapter只排除B2链而未排除legacy slam，2683后把新脚本键强制成旧ordinary键，首次差异为空；其211拍不能证明修正路线性能，ROOT_INVALIDATED及原件完整保留。只修Sol适配器：复用Opus已核act里own_now==plan的强制范围，新增实际路径断言；v2入口hash abab517b3ee77b6bbe5369c0eefc78ac95b39c38ca73efa5ab7a2a30355819a9，新case/check+finalize匹配后才正式P。冻结executor_v1与控制源不改。首版finalize参数曾用含..的不同词法路径被owner匹配拒绝，后用原绝对路径正常核销，未为此重测。两个外层问题归Sol，不给Opus新增修测量器任务。

p_v2实际worker/field退出、golden/Prefs/旧DEMO SHA和mtime、registry148/instances空/restore_pendingfalse/无game均已核，FINALIZED cleanup_verified，STATUSfalse/无活动锁。原manifest false仅三项未请求分析accounting路径，原false保留；真实现场worker完整manifest门不变。178有限现场验收不重开；179主走路翻越/moving stomp仍0机会，下一新条件工程要等同包有限调度项核收及全部现有门，旧L1/失败/STOP不重试，当前无新game gate。seq220一次合包请求Opus最小分类，源码静止，Sol不并行重算同项；只有完成或实质阻挡才唤醒。
'''
new = ('\n'.join(lines).rstrip() + section).encode('utf-8')
atomic(M / REL, new)
git(M, 'add', '--', REL)
git(M, 'commit', '-m', 'docs: record corrected continuous P and bounded scheduling follow-up')
newheads = {str(M): git(M, 'rev-parse', 'HEAD')}
for root in (W, TV):
    atomic(root / REL, new)
    git(root, 'add', '--', REL)
    git(root, 'commit', '-m', 'docs: sync corrected P and bounded scheduling status')
    newheads[str(root)] = git(root, 'rev-parse', 'HEAD')
    assert not git(root, 'diff', heads[str(root)], 'HEAD', '--', 'brain/ssbot')
now = dt.datetime.now(dt.timezone.utc).isoformat()
status.update(at=now, phase='TASK179_FINITE_SCHEDULING', live_or_budget_running=False,
    current_plan='7.169', current_plan_head=newheads[str(W)], current_head=newheads[str(W)],
    current_source=SOURCE, candidate_source=SOURCE, last_accepted_source=SOURCE,
    source_review_pending=False, new_behavior_source_review='accepted source; full scheduling pending',
    pending_opus='seq220 same179 finite slow-packet scheduling; no new tactics or source changes requested',
    active_blocker='Only four slow packet/serial-schedule classifications pending; Task178 finite live accepted; main179/moving stomp uncovered. No game gate.',
    next_phase='Opus bounded late-application/HF-prefix classification then Sol gate review',
    p_receipt=str(R / 'p_v2/ROOT_P_AUDIT.json'), p_receipt_task179_1263=str(R / 'p_v2/ROOT_P_AUDIT.json'),
    next_watch_ready=False, next_trial=None, last_game_trial=str(B / 'sol/demos/w13_walk179_20261105T222716Z_8f9e9629'),
    last_game_root_audit=str(B / 'analysis/w13_walk179_20261105T222716Z_8f9e9629/ROOT_EVENT_AUDIT.json'),
    last_game_audit_pass=True, last_game_action_acceptance=False, last_game_full_hp_unknown=False,
    latest_episode_verification=str(R / 'exit_recheck/verified_i0_e0.json'),
    task178_status='complete_finite_live_acceptance', context_closeout_requested=False)
case = readj(B / 'sol/performance/cases/task179_1263e9e3_v2.json')
status['accepted_opus_numbers'] = sorted(set(status.get('accepted_opus_numbers', [])) | set(case['accepted_reviews']) | {303})
writej(status_path, status)
progress_path = B / 'sol/work_packages/task179/PROGRESS.json'
progress = readj(progress_path)
progress.update(at=now, state='1263 source accepted; corrected212 P critical points pass; finite serial scheduling pending',
    source=SOURCE, candidate_source=SOURCE, current_head=newheads[str(W)],
    performance='212 actual calls and correct script route; four slow neutral/hold ticks require finite scheduling classification',
    p_directory=str(R / 'p_v2'), p_receipt=str(R / 'p_v2/ROOT_P_AUDIT.json'),
    source_review='303 localized source ordinary review accepted',
    next='seq220 bounded same179 HF/prefix and late-application scheduling; no new game gate',
    task178='complete finite live acceptance, separate ledger')
writej(progress_path, progress)
letter = '''## 1263修正路线完整212拍P已核：同179只补四慢拍的有限调度分类（seq220）

固定executor已真实清理，STATUSfalse/ownjobs空/无活动锁。计划7.169已同步main/刀口/TV；运行1263e9e3未改，刀口文档HEAD {head}，Sol已结束该树文档/索引写。继续压缩后当前窗口即可，不等另开窗口。178已按预定自然姿态个例有限现场验收完成，不再补R1局；179主翻越和moving stomp仍未覆盖，不以178替179。

P原件：analysis/task179_1263e9e3_20261105/p_v2/ROOT_P_AUDIT.json、handled_to_new_slam/RESULT.json与trace、FUNCTIONAL_VALIDATION.json、FINALIZED.json。完整212实际调用，真实P0–15/High/Numba4/EcoQoSoff，0异常/外来/新签名、加载源hash同、trace完整0overflow，实际worker50844/field48444均已核销。断言2683 slam/0、2699 slam/J、2720 slam/A+D、首次分歧2683且此后无强制脚本键，确实测到新路径。首J11.5565ms、出刀12.2482ms在原13.550338ms有限点内。原manifest只有3个未请求分析accounting字段false照旧保留，不当现场完整清单。模型条件NPC/synthetic receive及严格无hit/2728 modelhurt边界原样，不签真实命中/出口。

需要一次合包补的只有这四拍及必要后继：2564 chain0=17.6957ms，2683 slam0=15.9224，2696 slamR=16.9741，2704保持J=13.5568。ROOT_P_AUDIT每项已有实际HF/prefix/邻近键与测量成本。2564当前和前缀0、2696已保持R、2704已保持J，先用真实HF与实际在途前缀判断重复包迟到是否真无输入边沿变化；不能只凭键同签通过，仍计对下一次决策/STATE消费的排队影响。2683仍latch/desired=L，前缀L，发0是松L，不是瞬间刹车；重点查它迟0/1/2帧及必要相邻后继，沿用之前n2604最小迟应用方式或直接精确前缀推导。不要先重跑矩阵、优化planner或为慢几个us改控制源。

串行检查必须用p_v2这次所有中间tick实测成本及原真实/合成接收锚、最新STATE消费和HF2/2实际在途键；原Slam ta/首J2699/DownSlash2720不整体顺延，保持原receive/deadline/reserve及Opt1相符晚<=2、>4无回报等门。把“重复保持包可以迟到”与“其计算延误下一关键包”分开核。若有限证据不够或不安全，给精确阻挡及最小必要选项即可，不放宽门/默认0安全，也不扩新打法/全场NPC模型。仅数据目录离线边界，当前不请求控制源更改；如必须改源先报告实际必要处。无新P/游戏权限，正式P及新单局仍Sol。

p_v1作废原因是Sol通用adapter漏排除legacy slam owner，把新脚本发包强制回旧ordinary输入；211拍原件/ROOT_INVALIDATED保留，不是控制算法失败。v2只把own_now==plan的强制范围按你已核act复制并新增路由断言，入口hash abab517b3ee77b6bbe5369c0eefc78ac95b39c38ca73efa5ab7a2a30355819a9；新check/finalize再P/finalize已完成。冻结执行器/控制源未改，外层适配问题归Sol，不需要你修。入口在sol/performance/adapters/task179_1263e9e3_v2.py，case同名v2.json。

请用自己E16–23/Idle按需做这一个有限分类并记实际PID/阶段，Sol不并行重算同项；不重复759/212正式P或无关旧场景、不添新动作/逐条ACK。完成或实质阻挡一次交付/唤醒，报告明确已核和未核。原STOP、首损Q1、所有旧NO_RETRY、完整日志/input.stats/资源/核心进程及真实清理门不变，当前无新game gate。

'''.format(head=newheads[str(W)])
mail = B / 'sol/TO_OPUS.md'
atomic(mail, (letter + mail.read_text(encoding='utf-8-sig')).encode('utf-8'))
writej(R / 'ROOT_303_CLOSEOUT.json', {'at': now, 'source': SOURCE, 'p_audit': str(R / 'p_v2/ROOT_P_AUDIT.json'), 'plan': '7.169', 'heads_before': heads, 'heads_after': newheads, 'next_seq': 220, 'new_game_gate': False, 'task178': 'complete_finite_live_acceptance'})
writej(B / 'sol/OPUS_WAKE.json', {'seq': 220, 'at': now, 'task': 179, 'note': 'Corrected212 P actual newSlam route and critical points accepted; only four slow HF/prefix/serial timing classifications pending. Same179 finite E only; no new source/tactics/P/game.178 finite live accepted. Read newest TO_OPUS.'})
print(json.dumps({'plan': '7.169', 'source': SOURCE, 'heads': newheads, 'seq': 220, 'exclusive': False, 'new_game_gate': False}, ensure_ascii=False))
