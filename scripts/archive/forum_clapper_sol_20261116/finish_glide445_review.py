"""Record completed review/P and statically finish the unapproved new50 proposal."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import subprocess

B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B/'analysis/committed388_20261111'
A = B/'analysis/glide_jump_hold445_20261115'
G = B/'analysis/w13_50_glide_hold445_20261115'
OLD = B/'analysis/w13_50_middle_handoff434_20261114'
D = B/'sol/demos'/G.name
ROOT = Path('C:/modeling/silksong_bot')
H = 'd6a3664416ef84280b214115dc80f2b256782b32'
now = datetime.now(timezone.utc).isoformat()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def put(p, x):
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

assert not D.exists()
for n in ['USER_NEW50_AUTHORIZATION.json', 'LAUNCH_CLAIM.json', 'ENGINEERING_GATE.json']:
    assert not (G/n).exists(), n
assert not (B/'sol/performance/ACTIVE.json').exists()
p = read(A/'ROOT_P_AUDIT.json')
assert p['source'] == H and p['finite_measurement_valid'] and p['actual_cleanup_verified']
assert p['actual_owned_processes_exited'] == 16 and p['source_and_inputs_unchanged']

# The live audit must compare the immediately preceding MH50, including real
# postkill protected quits, rather than an inherited historical baseline.
q = G/'audit_repeat50.py'
t = q.read_text(encoding='utf-8-sig')
t = t.replace('w13_50_separated312_20261110_r1/ROOT_50_RESULT.json', OLD.name+'/ROOT_50_RESULT.json')
t = t.replace("phase='SEPARATED31250_RAW_AUDIT'", "phase='GLIDE44550_RAW_AUDIT'")
q.write_text(t, encoding='utf-8')
# Preserve the old helper as an explicitly unused historical helper.
q = G/'audit_seq312.py'
t = q.read_text(encoding='utf-8-sig').replace('glide_jump_hold445_20261115/source\'', 'glide_jump_hold445_20261115/source_fixed445\'')
t = t.replace('"""Post-cleanup independent audit of the new continuous 50. No game control."""',
              '"""Legacy Q1-only helper; not the audit entry for this batch. Use audit_repeat50.py."""')
q.write_text(t, encoding='utf-8')

# Adapt the already used source/config/GC/video postprocessor; add the new
# actual manifest binding to its existing per-bout checks.
q = G/'summarize_current50.py'
t = (ROOT/'tmp/summarize_middle50.py').read_text(encoding='utf-8-sig')
t = t.replace('w13_50_middle_handoff434_20261114', G.name)
t = t.replace('analysis/middle_handoff434_20261114', 'analysis/glide_jump_hold445_20261115')
t = t.replace('source_fixed434', 'source_fixed445')
needle = "            ('SSBOT_FORUM_MIDDLE_HANDOFF', 'ssbot.combat.slam_play.MIDDLE_HANDOFF', True, '1'),"
assert needle in t
t = t.replace(needle, needle+"\n            ('SSBOT_FORUM_GLIDE_JUMP_HOLD', 'ssbot.combat.forum_planner.GLIDE_JUMP_HOLD', True, '1'),")
t = t.replace('B13B=True, middle_handoff=True,', 'B13B=True, glide_jump_hold=True, middle_handoff=True,')
q.write_text(t, encoding='utf-8')
files = sorted(G.glob('*.py'))
for f in files:
    ast.parse(f.read_text(encoding='utf-8-sig'), filename=str(f))
lc = read(G/'LIFECYCLE_REVIEW.json')
lc.update(at=now, files={f.name:sha(f) for f in files})
lc['postprocessing_review'] = 'Current MH434 baseline; real Q1/Q5 and postkill tail retained. Per-bout actual GJH binding added to reused version/GC/video audit. No postprocessing or runtime launched.'
put(G/'LIFECYCLE_REVIEW.json', lc)
plan = read(G/'CONTINUOUS_PLAN.json')
assert plan['seeds'] == read(OLD/'CONTINUOUS_PLAN.json')['seeds']
assert not plan['authorized']
draft = read(G/'TRIAL_CONFIG_DRAFT.json')
assert not draft['user_authorized']
oldenv = read(OLD/'TRIAL_CONFIG_DRAFT.json')['environment']
normalized_oldenv = {k:v.replace(OLD.name, G.name) for k,v in oldenv.items()}
delta = {k:(normalized_oldenv.get(k),v) for k,v in draft['environment'].items() if normalized_oldenv.get(k)!=v}
assert delta == {'SSBOT_FORUM_GLIDE_JUMP_HOLD': (None,'1')}, delta
assert draft['environment']['SSBOT_FORUM_SLAM_NO_NEW_GLIDE'] == '0'
staged = read(G/'PREAUTH_STAGING.json')
staged.update(at=now, lifecycle_files=len(files), postprocessing_static_review=True,
              lifecycle_review_sha256=sha(G/'LIFECYCLE_REVIEW.json'))
put(G/'PREAUTH_STAGING.json', staged)

review = read(R/'REVIEW445.json')
review.update(at=now, stage='Independent source review and finite formal P completed; cleanup verified; new50 statically staged pending fresh user permission',
              formal_P_completed=True, finite_measurement_valid=True, actual_cleanup_verified=True,
              formal_P_audit=str(A/'ROOT_P_AUDIT.json'), cleanup=str(A/'ROOT_CLEANUP.json'),
              outputs={arm:{k:v for k,v in x.items() if k!='contexts'} for arm,x in p['outputs'].items()},
              performance_budget_pass=False, full_scheduling_gate_pass=False,
              proposed_new50=str(G), game_authorized=False)
put(R/'REVIEW445.json', review)
r444 = read(R/'REVIEW444.json')
r444.update(formal_delivery_pending=False, formal_delivery=445, formal_source_review_completed=True,
            formal_P_completed=True, next_owner='Sol, pending actual new user authorization for one new50')
put(R/'REVIEW444.json', r444)
s = read(B/'sol/STATUS.json')
s.update(at=now, phase='GLIDE445_REVIEW_P_COMPLETE_NEW50_PERMISSION_PENDING',
         live_or_budget_running=False, own_offline_jobs=[], own_live_session=None,
         current_source=H, candidate_source=H, source_review_pending=False,
         last_opus_scan_number=445, last_opus_receipt_number=445,
         pending_opus=None, pending_user='Fresh explicit new50 authorization; prior batches fully consumed',
         authorized_batch=None, authorized_bouts=0, new50_authorized=False,
         candidate_batch=G.name, candidate_demo=str(D),
         next_phase='Fresh user authorization only; then bind actual reply, final preflight, preheat and launch/release pipeline. No game until reply.',
         glide445_review=str(R/'REVIEW445.json'), glide445_P=str(A/'ROOT_P_AUDIT.json'),
         glide445_cleanup=str(A/'ROOT_CLEANUP.json'), glide445_new50_proposal=str(G/'PREAUTH_STAGING.json'),
         glide445_default_enabled=False, old_slam_no_new_glide_enabled=False,
         active_implementation=dict(owner='Sol', scope='New50 proposal and permission', stage='Source/P/cleanup complete, static staging ready; game not authorized or started'))
put(B/'sol/STATUS.json', s)

msg = f'''## #445源审和有限P核收：d6a36644已清理，新50待用户；信息，无新派工/不唤醒

Sol独立源审+同阶段Astra复核无P0-P2。两个实际受影响窗OPEN12拍、FLOAT31拍，ON/OFF各43拍，零拍检查和正式measure/finalize均完成；OWN起不强制键、英雄B+1模型，实际wire/目标/开关已核。OPEN首拍两臂仍允许J开伞；FLOAT首拍ON为D+L，OFF仍J+R。只证明这次实际回放选择消除了错误保持，不宣称实机接锤或救血。

整拍ON p50/p99={p['outputs']['ON']['tick_p50_ms']:.3f}/{p['outputs']['ON']['tick_p99_ms']:.3f}ms，OFF={p['outputs']['OFF']['tick_p50_ms']:.3f}/{p['outputs']['OFF']['tick_p99_ms']:.3f}ms；超16.67各13/8拍，仍超帧，不是预算/全域调度通过。FLOAT两臂各一次GC事件，不能据此归因。源728文件/输入hash未变，正式窗无新JIT；16个自有进程加有界driver退出、Prefs/golden/旧DEMO复原、registry空、无游戏/ACTIVE。收据{A/'ROOT_P_AUDIT.json'}和ROOT_CLEANUP。

新候选{G.name}静态配置已备：仅GJH1新增、MH1/AS1/LANDING_EXIT1及旧禁伞0同上一批、同50种子同序。默认GJH0/MH0照旧。旧50授权耗尽，尚未新授权/开游戏/亮屏/录制；等当前聊天新批授权，再做实际预热/worker/input/capture/资源/FPS>=30门。同游戏全录、2HP续、运行故障停。不重开任何旧停批/AA/原始录像。当前无新实现任务，不扩模型或新原因，等本轮实机后再定。

---

'''
mail = B/'sol/TO_OPUS.md'
old = mail.read_text(encoding='utf-8-sig')
assert '#445源审和有限P核收：' not in old
heading = '# Sol → Opus 留言队列'
assert old.startswith(heading)
mail.write_text(heading+'\n\n'+msg+old[len(heading):].lstrip(), encoding='utf-8')

section = f'''
### 7.383 #445伞内跳保持修复源审核收；两窗有限P完成，新50待授权（11-15）

固定d6a36644（父8e34fb6c），3文件源/WT/冻结hash绑定；Sol及同阶段Astra窄审无P0-P2。实际GLIDE在所有候选/旧timer读取之前使旧保持失效；prefix末退出/落地后的新真跳保留原长短跳时钟，开伞/漂浮J不续挂高度承诺。11新增/170影响测试核证不重复。仅Forum默认关GJH，不禁伞/强收伞、不改共享模型/Planner/hold filter/评分顺序；旧禁伞0保持。原单拍上下文/截止差异和逃生unsafe、伞内空冲取消模型线索均保留，不认证收益。

Sol用未改entry_v4/executor_v2做零拍check及正式两臂measure/finalize；OPEN51162–51173共12拍，FLOAT51210–51240共31拍，ON/OFF各43拍。记录只强制至B-1，B起真实policy/wire，英雄B+1合成；敌人仍录像，不是实机闭环。OPEN首拍两臂仍J开伞；FLOAT首拍ON D+L、OFF J+R，后续31拍有分叉。ON整拍p50/p99/max14.760/21.478/21.900ms、13超16.67；OFF14.401/19.341/19.356ms、8超，有限测量有效，不是预算/全域调度通过。两臂FLOAT各一次拍内GC，不归因、不扩GC包。

源728文件/输入hash未变，正式窗无新JIT；实际主P核High/worker E核Idle、ready/closed收据齐；16自有进程和有界driver退出、Prefs/golden/旧DEMO恢复、registry空、无游戏/ACTIVE。初次未发布冻结准备的Git输出断言失败（无内容差异），在任何P/游戏前修复并保留SETUP_FAILURE_1，随后内容再核；不算控制/测量失败。REVIEW445、SOURCE_REVIEW_AND_P_FINAL、ROOT_P_AUDIT/ROOT_CLEANUP登记。

新候选w13_50_glide_hold445_20261115仅静态备好：同上一MH50的50种子顺序和MH1/AS1/LANDING_EXIT1配置，只加GJH1；旧禁伞0，默认GJH/MH仍关。连续生命周期和严格停止/实际保护/尾窗审计复用；新增worker实际GJH环境及每局manifest绑定核、相邻MH434基线、启动>=30FPS、launch后立即走reviewed release包装。未建有效新授权/launch claim/demo，未开游戏/常亮/录像。旧50全部消耗，当前下一步是用户决定一个新50，心跳不扩权限；同游戏全录、真实2HP退出续收、运行故障停，不续旧停止批/不改AA或原件。给Opus信息回执，无新派工/无唤醒。
'''
for root in [ROOT, Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')]:
    planfile = root/'docs/plans/forum_clapper_plan.md'
    assert '### 7.383 ' not in planfile.read_text(encoding='utf-8-sig')
    with planfile.open('a', encoding='utf-8') as f:
        f.write(section)

put(G/'POSTPROCESSING_STATIC_REVIEW.json', dict(at=now, source=H, audit=str(G/'audit_repeat50.py'),
    summary=str(G/'summarize_current50.py'), baseline=str(OLD/'ROOT_50_RESULT.json'),
    all_scripts_AST_valid=True, actual_manifest_GJH_binding_required=True,
    real_protected_quit_and_postkill_tail=True, legacy_audit_seq312_not_used=True,
    game_started=False, authorized=False))
print(json.dumps(dict(source=H, P_valid=True, cleanup=True, static_ready=True, source_same=True,
                     seeds_same=True, config_delta=delta, new50_authorized=False, game_started=False,
                     Opus_info_written=True, new_task=False, wake_sent=False), ensure_ascii=False))
