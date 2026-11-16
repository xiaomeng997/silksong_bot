import ast
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

M = Path('C:/modeling/silksong_bot')
W = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
TV = Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/task179_1263e9e3_20261105'
OLD_TAG = 'w13_walk179_20261105T222716Z_8f9e9629'
OLD_SOURCE = '8f9e9629e404a3ed3b69412323765c80da804057'
SOURCE = '1263e9e398859b0fa98e6d3141ac955288e05059'
OLD = B / 'analysis' / OLD_TAG
GIT = 'C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
PY = M / 'brain/.venv/Scripts/python.exe'
REL = 'docs/plans/forum_clapper_plan.md'
now = dt.datetime.now(dt.timezone.utc).isoformat()
tag = 'w13_walk179L2_' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_1263e9e3'
A = B / 'analysis' / tag
T = B / 'sol/demos' / tag

def git(root, *args):
    return subprocess.check_output([GIT, '-C', str(root), *args], text=True, encoding='utf-8').strip()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def atomic(path, data):
    temp = path.with_name(path.name + '.sol304.tmp')
    temp.write_bytes(data)
    os.replace(temp, path)

def write(path, data):
    assert not path.exists(), path
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

status = read(B / 'sol/STATUS.json')
assert not status['live_or_budget_running'] and not status.get('own_offline_jobs')
assert status['current_plan'] == '7.169' and status['current_source'] == SOURCE
assert read(R / 'OPUS304_RECEIPT.json')['accepted']
assert read(R / 'p_v2/FINALIZED.json')['cleanup_verified']
assert not T.exists() and not A.exists()
assert not list((B/'sol/performance').glob('ACTIVE*'))
assert git(W, 'log', '-1', '--format=%H', '--', 'brain/ssbot') == SOURCE
heads = {}
for root in (M, W, TV):
    assert not git(root, 'status', '--porcelain', '--untracked-files=no'), root
    heads[str(root)] = git(root, 'rev-parse', 'HEAD')
packet = read(R / 'SOURCE_PACKET.json')
assert all(sha(W/n) == h for n,h in packet['raw_runtime_files_sha256'].items())
assert not git(W, 'diff', SOURCE, '--', 'brain/ssbot', 'knowledge')
assert not any((Path('C:/ssbot/sandbox')/n).exists() for n in ('STOP_AGENTS','HUMAN_PRACTICE'))
spec = importlib.util.spec_from_file_location('root304_old_gate', OLD/'engineering_helpers.py')
helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
accepted = sorted(set(status['accepted_opus_numbers']) | {304})
assert helper.new_blockers(accepted) == []
sys.dont_write_bytecode = True
sys.path.insert(0, str(W/'brain'))
from ssbot.tools.launcher import PrefsGuard, current_prefs, read_reg_file, prefs_diff, running_game_pids
guard = PrefsGuard.default()
reg = guard.status()
assert reg.get('instances') == [] and not reg.get('restore_pending') and not reg.get('live')
assert running_game_pids() == []
assert guard.verify_golden() == 'fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469'
assert prefs_diff(current_prefs(guard.store), read_reg_file(guard.golden)) == []
demo = Path('C:/ssbot/sandbox/DEMO_SOON')
assert sha(demo) == '0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81'
assert demo.stat().st_mtime_ns == 1791523123325081300
raw = (M/REL).read_bytes()
assert all((r/REL).read_bytes() == raw for r in (W,TV))
lines = raw.decode('utf-8').splitlines()
assert '当前进度（11-05，7.169）' in lines[2]
lines[2] = '2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-05，7.170）：Opus304四慢拍已由Sol独立有限核收，无须改控制源。实测212拍成本配旧局接收时间线，在空闲开工p50/p99情景下0迟包/0跳帧，保持键迟1/2帧等价，松L迟1/2帧仍保留原J/下劈时钟；高负载压力的30迟包/10跳帧和严格modelhurt照旧保留，不签未来保证。另准备新源1263的179-L2有界单局，主验走路翻越/真实交还，辅助新锤实例接续和移动踩头；178已有限验收，不加专项局。原7HP首损Q1/输入/日志/资源/真实清理门不变。**'
section = '''

#### #304四慢拍有限调度核收，准备179-L2新条件单局（11-05，进度7.170）

Sol直接检查sched304/make_replay_late304及实际late1/late2工件，独立用原P212个tick_start/send_done/tick_end和实机STATE接收锚复算串行latest-STATE；再用生产NumPy hold_filter独立核游戏锁存。接收后空闲开工延迟p50=.270ms/p99=1.292ms两情景均212调用/0迟包/0跳帧，锁存与全准时相同；最小余量在2683为12.190/11.168ms，p99首J2699余15.501、2720出刀余15.1883ms。包离开和worker空闲分开，2564/2696慢段主要在send_done之后，仍计入后继开工占用；没有只凭整tick超点制造必需优化。

2564/2696/2704的当前latch/desired/前缀等于发包、22键pending全0，单迟1/2帧由生产HF核锁存全同。2683仍持L、发0释放不是同类保持；原FIFO迟应用1/2的完整policy/旧Slam分支均在2699发J、2715D、2720A+D，原ta/目标时钟不变；0foreign/异常/强制planner拍，11源hash当前同。模型位置改变、严格未命中及2727/2728受伤照旧，有限功能容忍不签命中/安全。全段每拍加极端idle_max7.132ms时实际202调用/30迟包/10跳帧/7锁存差，报告“9跳帧”文字按JSON和独立复算更正为10，不为文字重跑。接收来自旧代码路径，替代路径/GIL可改接收时刻，p99不是联合概率，更非未来保证；迟分支E成本未另测正式P，只接受当有限非精确拍容忍。收据analysis/task179_1263e9e3_20261105/OPUS304_RECEIPT.json；原ROOT_P_AUDIT的complete_scheduling_gate=false不涂绿，工程组合预算在新单局门独立列出处与限制。

当前源码仍1263e9e3，仅原Slam已处理标记按实例和离线Quit审计修正。此次新单局179-L2要验证修后的完整接续，非旧179-L1重试/补坏局，不混正式样本。主要目标仍走路怪翻越到真实交还；另账移动Walk支持踩头、新同怪Slam实例可接、实际DownSlash hit/pogo/交还和责任HP。178已按自然姿态个例有限完成，仅保留回归观察不再立R1后备。0机会不算成功，首损后原停止/原因定位/清理照旧，不为凑翻越继续打。仍使用已核Launcher/WMI单实际worker、相同工程profile/seed/7HP/HP<=6真实Q1/1episode/measure2，runtime/profile/模型/脚本/新budget/新namespace重新绑定；新worker自有OracleLink的input.stats bootstrap现场回执必须重新通过并保存，旧回执只作组件来源。

先把本节同步main/刀口/TV，之后刀口HEAD从新合同冻结至实际全清理。Sol自己新数据目录仅替换原单局脚本的namespace/source/阶段字面量，生命周期AST逆向逐字节核原版；旧原件/NO_RETRY/AA不动。源码和正式P不重做、Opus当前无新实现任务；游戏前STATUS原子true/5s静止/30s pulse，原资源/精确身份背景分类/STOP/无双起门不绕过。运行中只读收信，不并行重计算、不操作Windows核心进程；只有自有worker/场worker/game/registry/golden/Prefs/旧DEMO实际全部核清后false。用户已有无人值守授权持续有效，不另等到场。
'''
newplan = ('\n'.join(lines).rstrip() + section).encode('utf-8')
atomic(M/REL,newplan); git(M,'add','--',REL); git(M,'commit','-m','docs: accept bounded scheduling and prepare fresh engineering trial')
newheads={str(M):git(M,'rev-parse','HEAD')}
for root in (W,TV):
    atomic(root/REL,newplan);git(root,'add','--',REL);git(root,'commit','-m','docs: sync bounded scheduling and engineering trial plan')
    newheads[str(root)]=git(root,'rev-parse','HEAD')
    assert not git(root,'diff',heads[str(root)],'HEAD','--','brain/ssbot','knowledge')
A.mkdir()
for name in ('engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json'):
    (A/name).write_bytes((OLD/name).read_bytes())
src=(OLD/'trial.py').read_text(encoding='utf-8-sig')
trial=src.replace(OLD_TAG,tag)
assert trial.replace(tag,OLD_TAG)==src
ast.parse(trial);(A/'trial.py').write_text(trial,encoding='utf-8')
src2=(OLD/'run_unattended.py').read_text(encoding='utf-8-sig')
coord=src2.replace(OLD_SOURCE,SOURCE).replace('WALK179_L1','WALK179_L2')
assert coord.replace(SOURCE,OLD_SOURCE).replace('WALK179_L2','WALK179_L1')==src2
ast.parse(coord);(A/'run_unattended.py').write_text(coord,encoding='utf-8')
write(A/'SCRIPT_PORT_RECEIPT.json',{'at':now,'source':SOURCE,'origin':str(OLD),'trial_inverse_exact':True,'coordinator_inverse_exact':True,'helpers_byte_equal':True,'syntax_valid':True,'old_trials_changed':False})
draft=read(OLD/'TRIAL_CONFIG_DRAFT.json')
draft=json.loads(json.dumps(draft).replace(OLD_TAG,tag).replace(OLD_SOURCE,SOURCE))
draft.update(purpose='179-L2 new-source existingSlam reentry fix; main walking-vault and real handback; moving stomp separately',coverage_target='Walking-vault/main; same-iid newSlam actual reentry/targethit/pogo/handoff; moving Walk-supported stomp separately.178 finite already accepted; no extraR1')
write(A/'TRIAL_CONFIG_DRAFT.json',draft)
acceptance={'at':now,'planned_id':'179-L2','main_goal':'walking-target vault through actual crossing/hit/pogo where relevant/real handback and liability audit',
 'auxiliary':{'moving_stomp':'separate natural Walk-supported row/send/accept/hit/pogo/handoff;0opportunity uncovered',
 'new_slam_instance':'old same iid handled mark must not block a new Slam antic; actual newRun/keys/DownSlash/hit/bounce/handoff audit',
 'task178':'already finite live accepted; incidental regression only, no178R1'},
 'new_condition':'1263 closes actual179L1 stale per-iid handled mark; old stopped L1 preserved; not retry of same unfixed cause',
 'limits':'one new engineering bout;7HP/HP<=6firstlossQ1; original death/keys/log/Opt1/source/P/resource/cleanup gates; no replacement',
 'source':SOURCE,'execution_head':newheads[str(W)],'trial':str(T),'analysis':str(A),'not_formal_sample':True}
write(A/'ACCEPTANCE.json',acceptance)
budget={'at':now,'source':SOURCE,'accepted_for':'one bounded new engineering, not future performance or live safety guarantee',
 'corrected_P':str(R/'p_v2/ROOT_P_AUDIT.json'),'finite_slow_classification':str(R/'OPUS304_RECEIPT.json'),
 'unmodified_prior_vault_P':str(B/'analysis/task179_8f9e9629_20261105/p_v1/ROOT_P_AUDIT.json'),
 'unmodified_prior_other_P':str(B/'analysis/task179_64428fda_20261105/p_inprocess/ROOT_P_AUDIT.json'),
 'limits':'old receive timeline/conditionalNPC/HERO2; highloadstress retained; real actions and newworker bootstrap must still be audited',
 'engineering_budget_gate':True,'future_timing_guarantee':False,'physical_safety_certified':False}
write(A/'ROOT_BUDGET_ACCEPTANCE.json',budget)
gate=read(OLD/'ENGINEERING_GATE.json')
gate.update(at=now,source=SOURCE,execution_head=newheads[str(W)],source_packet=str(R/'SOURCE_PACKET.json'),source_review=303,
 accepted_opus_numbers=accepted,planned_id='179-L2',p_scope=str(R/'p_v2/ROOT_P_AUDIT.json'),
 budget_scope='corrected212 measured full route plus304 finite slow-packet closure; unchanged179 vault/otherP original provenance; no future guarantee',
 known_limits='conditional model/NPC/no-hit/modelhurt retained; no universal safety; main179 still uncovered;178 finite completed')
new_evidence=[R/'SOURCE_PACKET.json',R/'SOURCE_REVIEW.json',R/'CHECKS_AND_EXIT_RECHECK.json',R/'ADAPTER_V2_REVIEW.json',
 R/'p_v2/ROOT_P_AUDIT.json',R/'p_v2/FINALIZED.json',R/'OPUS304_RECEIPT.json',
 B/'sol/performance/checks/20261105_task179_1263e9e3_v2/FINALIZED.json',
 A/'SCRIPT_PORT_RECEIPT.json',A/'run_unattended.py',A/'resource_background.py',A/'RESOURCE_BACKGROUND_APPROVAL.json',
 A/'ACCEPTANCE.json',A/'ROOT_BUDGET_ACCEPTANCE.json',B/'sol/work_packages/task178/LIVE_ACCEPTANCE.json']
gate['evidence'].update({str(p):sha(p) for p in new_evidence})
assert all(sha(Path(p))==h for p,h in gate['evidence'].items())
write(A/'ENGINEERING_GATE.json',gate)
subprocess.run([str(PY),'-X','utf8','-B',str(A/'trial.py')],cwd=W,check=True)
contract=read(T/'contract.json')
assert contract['source']==SOURCE and contract['execution_head']==newheads[str(W)]
assert all(sha(Path(p))==h for p,h in contract['prerequisites'].items())
write(A/'ROOT_PREFLIGHT_STATIC.json',{'at':now,'passed':True,'source':SOURCE,'heads':newheads,'source_files':len(packet['raw_runtime_files_sha256']),
 'registry':reg,'games':[],'golden_sha256':guard.verify_golden(),'prefs_diff':[], 'old_demo_sha256':sha(demo),'old_demo_mtime_ns':demo.stat().st_mtime_ns,
 'script_lifecycle_port_exact':True,'new_blockers':[],'game_started':False})
status.update(at=now,phase='WALK179_L2_PREPARED',current_plan='7.170',current_head=newheads[str(W)],current_plan_head=newheads[str(W)],
 accepted_opus_numbers=accepted,pending_opus='304 accepted; source/index static for fresh179L2, readonly during game, no implementation task',
 active_blocker='none for one new bounded179L2; actual walking-vault/movingstomp still unverified',
 next_phase='fresh179L2 resource preflight and detached own coordinator',next_trial=str(T),next_watch_ready=True,
 next_watch_user_authorized=True,source_review_pending=False,
 opus304_receipt=str(R/'OPUS304_RECEIPT.json'),engineering_gate=str(A/'ENGINEERING_GATE.json'))
atomic(B/'sol/STATUS.json',(json.dumps(status,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
letter='''## #304有限核收，准备新179-L2，源码静止/游戏期间只读（seq221）

Sol已独立复算212拍实测成本+原局接收双锚/串行latestSTATE，并用生产NumPy HF重核三个保持包迟1/2。p50/p99情景0迟包/0跳帧/0锁存差；2683有限晚1/2的J/D/A+D原clock核同，11源hash同、无强制/异常。收据analysis/task179_1263e9e3_20261105/OPUS304_RECEIPT.json。idle_max实际JSON与独算是10跳帧/202调用，不是报告的9；文字小误不必重跑或单独编号回修。高负载30迟包/7锁存差、旧接收时钟/GIL和严格modelhurt/nohit限制全留，有限工程预算不作未来/命中安全证明。

计划7.170已同步，刀口HEAD {head}、运行1263不变。新namespace {tag}，主179走路翻越/真实交还，moving stomp及新同iid锤实例接续分账；178已有限完成，不再R1。原L1首损原件/NO_RETRY不动。新源审/组合P和304有限闭合/相同profile/新预算/input.stats现场回执、原STOP/7HP首损Q1/资源/实际清理门绑定，Sol准备一次新工程；条件不齐不开。刀口HEAD现在冻结到真实清理，你无新实现/重算任务；STATUStrue时只读收信、暂停自己的重活，等Sol结论，无需ACK或唤醒。用户压缩后继续/无人值守授权仍有效。

'''.format(head=newheads[str(W)],tag=tag)
mail=B/'sol/TO_OPUS.md';atomic(mail,(letter+mail.read_text(encoding='utf-8-sig')).encode('utf-8'))
atomic(B/'sol/OPUS_WAKE.json',(json.dumps({'seq':221,'at':now,'task':179,'note':'304 accepted finite; prepared fresh179L2 after full gates. source static and readonly during game. No ACK/new task.'},ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
write(B/'sol/work_packages/task179/LIVE179_L2_BINDING.json',{'at':now,'source':SOURCE,'tag':tag,'analysis':str(A),'trial':str(T),'execution_head':newheads[str(W)],'game_started':False})
print(json.dumps({'tag':tag,'analysis':str(A),'trial':str(T),'head':newheads[str(W)],'plan':'7.170','prepared':True,'game_started':False},ensure_ascii=False))
