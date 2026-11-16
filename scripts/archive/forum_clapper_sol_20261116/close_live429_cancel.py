from pathlib import Path
from datetime import datetime,timezone
import json

B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_air_catch429_display_20261114';D=B/'sol/demos'/G.name
OP=B/'analysis/display_start429_20261114';ROOT=Path('C:/modeling/silksong_bot');R=B/'analysis/committed388_20261111'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'));now=datetime.now(timezone.utc).isoformat()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
cleanup=read(G/'ROOT_CLEANUP.json');cad=read(G/'STARTUP_CADENCE_GATE.json');hold=read(G/'DISPLAY_HOLD_READY.json');closed=read(G/'DISPLAY_HOLD_CLOSED.json')
assert cleanup['complete'] and not cleanup['runtime_batch_complete'] and len(cleanup['actual_owned_processes_exited'])==16
assert not cad['passed'] and cad['fps']<30 and closed['held'] and closed['released'] and not closed['error']
assert not (D/'launch/WATCH_GO.json').exists()
rows=[json.loads(l) for l in (D/'run/attempts_i0.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
assert not rows
result=dict(at=now,batch=G.name,source=cad['source'],authorized_maximum_bouts=50,actual_bouts=0,
 completed50=False,GO_sent=False,cancelled_before_combat=True,reason='Startup average3.7296fps below30fps; gate refused GO',
 startup_cadence=cad,temporary_display_request_held=True,display_ready=hold,display_closed=closed,
 physical_TV_power_verified=False,actual_cleanup_verified=True,actual_owned_processes_exited=16,
 runtime_files_unchanged=cleanup['runtime_files_unchanged'],prerequisites_unchanged=cleanup['prerequisites_unchanged'],
 video=str(D/'w13.mp4'),video_capture=cleanup['capture_closed'],
 stopped_batch_restart_allowed=False,additional_game_authorized=False,
 conclusion='Temporary Windows display request did not restore launch cadence. It does not prove physical television on/off or a unique rendering cause.',
 next='Await user clarification on physical TV off versus Windows idle display, then decide concrete next action. No control-code or no-landing feature change.')
put(G/'ROOT_ZERO_BOUT_RESULT.json',result)
spec=read(G/'BATCH_SPEC.json');spec.update(state='CANCELLED_BEFORE_GO_SLOW_START_CLEANED',started=False,ready=False,
 game_prewarme_started=True,attempted=0,completed_bouts=0,completed=False,display_request_released=True,
 startup_fps=cad['fps'],authorization_closed=True,restart_allowed=False,updated_at=now)
put(G/'BATCH_SPEC.json',spec)
proposal=read(OP/'NEW50_DISPLAY_PROPOSAL.json');proposal.update(state='AUTHORIZED_PREWARM_CANCELLED_ZERO_BOUTS',game_started=True,
 combat_started=False,actual_bouts=0,result=str(G/'ROOT_ZERO_BOUT_RESULT.json'),display_request_released=True,new_game_authorized=False)
put(OP/'NEW50_DISPLAY_PROPOSAL.json',proposal)
put(R/'RECEIPT429_DISPLAY_RUNTIME.json',dict(at=now,source=cad['source'],actual_user_authorization='允许临时亮屏并开新50盘',
 actual_bouts=0,startup_fps=cad['fps'],gate_refused=True,temporary_request_active_during_launch=True,
 temporary_request_released=True,actual_cleanup_verified=True,physical_TV_power_unknown=True,
 result=str(G/'ROOT_ZERO_BOUT_RESULT.json')))
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s['own_live_session']
s.update(at=now,phase='LIVE429_CANCELLED_ZERO_BOUTS_CLEANED_AWAIT_TV_STATE',live_paused_by_user=True,
 live_pause_released_only_for_batch=None,own_offline_jobs=[],live429_authorization_consumed=True,
 live429_result=str(G/'ROOT_ZERO_BOUT_RESULT.json'),display_request_active=False,pending_opus=None,
 pending_user='Clarify LG television physically powered off/disconnected versus Windows idle display; no further game permission yet',
 next_phase='Cancelled before GO, all16 owned exited including display holder/redirector. Await TV-state clarification; no automatic retry or restart of either stopped batch.')
put(B/'sol/STATUS.json',s)
mail='''## 运行补充：#429临时常亮已实试，启动仍3.73fps，GO前取消0盘；等用户电视状态（信息，不新派工/不唤醒）

用户当前Sol聊天call_332df21ce9104715b349be44be4684dc明确“允许临时亮屏并开新50盘”。新候选w13_50_air_catch429_display_20261114，同d7、AS1/出口1和同50种子；旧428停止批未动。临时SetThreadExecutionState请求实际成功持有（20:10:07Z Ready，actual holder43016/创建1794687007.661254），游戏随后预热；原WMI回执PID是venv redirector39412，已核实际helper PID并补记两者，无第二次启动，全部身份纳入清理。

新增门实际算到193帧/51.7483s=3.72959fps，低于30，于20:12:31Z在原GO之前拒绝；WATCH_GO不存在，attempts文件为空，实际0盘。协调器按取消路径清理；20:12:33Z holder收到batch ended，显式释放成功。Root核16自有进程全退出、728源/39先决未变、Prefs/golden/旧DEMO恢复，录像561帧encoder0。游戏和常亮请求都已结束，不重试该取消批，也不续旧49。

这次只证明Windows请求成功持有仍未恢复启动帧节奏，不证明电视物理开/关、HDMI连通或唯一DXGI原因。不要写“保持屏幕唤醒后预期41fps已通过”。用户早先说“你八成打不开那个电视”；Sol已问当前是遥控器关机/断电还是仅Windows自动关屏，尚待答。物理状态不明前不增加代码/驱动/服务改动或再次游戏试验。

G/ROOT_ZERO_BOUT_RESULT.json、STARTUP_CADENCE_GATE、DISPLAY_HOLD_READY/CLOSED、DISPLAY_RECEIPT_NOTE、ROOT_CLEANUP及committed388_20261111/RECEIPT429_DISPLAY_RUNTIME记录。当前runtime源码仍d7，现有有限P有效但无新实机行为结果；不落地仍没有实现条件。下一步归用户澄清与Sol调度，本信仅新实测信息，暂不新派分析/实现任务、不发wake，避免为未明物理条件继续扩机制研究。

---

'''
p=B/'sol/TO_OPUS.md';text=p.read_text(encoding='utf-8-sig');head='# Sol → Opus 留言队列\n\n';assert text.startswith(head) and '## 运行补充：#429临时常亮已实试' not in text
p.write_text(head+mail+text[len(head):],encoding='utf-8')
p=ROOT/'docs/plans/forum_clapper_plan.md';text=p.read_text(encoding='utf-8-sig');assert '### 7.365 ' not in text
p.write_text(text+'''

### 7.365 用户授权常亮新50，实际仍3.73fps，帧速门GO前取消0盘；已清理16进程（11-14）

当前聊天call_332df21ce9104715b349be44be4684dc明确“允许临时亮屏并开新50盘”。新w13_50_air_catch429_display_20261114，同d7/AS1/出口1/50种子，旧428不续。Windows常亮请求真实成功持有，从20:10:07Z到20:12:33Z，实际holder43016；WMI venv redirector39412与实际PID不同导致首回执断言，核正同一次启动两身份并记DISPLAY_RECEIPT_NOTE，无重复helper。绑定文件在新G，不改旧批先决。

预热193帧/51.7483s=3.72959fps，20:12:31Z新30FPS门按授权在GO前拒绝，WATCH_GO无、attempts空，实际0盘；协调器取消并清理。常亮holder因batch ended显式释放成功，Root核16进程全退出、728源/39先决保持、Prefs/golden/旧DEMO恢复、录像561帧encoder0。G/ROOT_ZERO_BOUT_RESULT、STARTUP_CADENCE_GATE、DISPLAY_HOLD_READY/CLOSED、ROOT_CLEANUP及RECEIPT429_DISPLAY_RUNTIME留证。

本次只能说明常亮请求没恢复启动帧速，不能自证物理电视电源/HDMI状态或唯一机制。用户此前说“你八成打不开那个电视”，Sol已问是遥控器关机/断电还是Windows自动关屏，等待澄清。无新GO/游戏重试/常亮请求/代码或系统改动，两个停止/取消批均不重开；current仍已审d7，默认关、游戏暂停。只把新实测作为信息回信，不额外派研究任务或wake。有效50仍未完成，不落地条件未满足。
''',encoding='utf-8')
print(json.dumps(dict(actual_bouts=0,startup_fps=cad['fps'],GO_sent=False,owned_exited=16,display_released=True,waiting_for_TV_state=True)))
