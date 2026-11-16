from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/walk_rule418_20261113';P=B/'analysis/cluster_back416_20261113'
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';HEAD='8a9919e65f1e3c51ca0f96fdd9b59cb862fb9a20'
read=lambda p:json.loads(p.read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,v):
 q=p.with_suffix(p.suffix+'.sol.tmp');q.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8');os.replace(q,p)
def git(*args,cwd=W):return subprocess.check_output([GIT,'-C',str(cwd),*args])

def main():
 assert git('rev-parse','HEAD').decode().strip()==HEAD and not git('diff','HEAD','--','brain/ssbot').strip()
 state=read(B/'sol/STATUS.json');assert not state['own_offline_jobs'] and not state['live_or_budget_running'] and state['live_paused_by_user']
 assert read(B/'sol/OPUS_WAKE.json')['seq']==358
 A.mkdir(exist_ok=False);root=A/'source_8a9919e6';root.mkdir();parent=read(P/'SOURCE_PACKET.json');old=Path(parent['source_root'])
 names=set(parent['raw_runtime_files_sha256'])
 for n,h in {**parent['raw_runtime_files_sha256'],**parent['support_sha256']}.items():
  assert sha(old/n)==h;q=root/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,q)
 changed=[n for n in git('diff','--name-only',parent['source'],HEAD).decode().splitlines() if n.startswith(('brain/ssbot/','knowledge/'))]
 assert set(changed)=={'brain/ssbot/combat/attack_range.py','brain/ssbot/combat/knife_chain_geometry.py','brain/ssbot/combat/walk_rule.py','brain/ssbot/train/forum_planner_policy.py'}
 for n in changed:
  q=root/n;data=git('show',HEAD+':'+n)
  if q.exists() and b'\r\n' in q.read_bytes():data=data.replace(b'\n',b'\r\n')
  q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data);names.add(n)
 shutil.copytree(old/'.git',root/'.git');git('fetch','--quiet','--no-tags',str(W),HEAD,cwd=root);git('symbolic-ref','HEAD','refs/heads/codex/walk418_freeze',cwd=root);git('update-ref','refs/heads/codex/walk418_freeze',HEAD,cwd=root);git('read-tree',HEAD,cwd=root)
 assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=root).strip()
 put(A/'SOURCE_PACKET_ORIGINAL.json',dict(at=now(),source=HEAD,parent=parent['source'],source_root=str(root),raw_runtime_files_sha256={n:sha(root/n) for n in sorted(names)},runtime_support_files=parent['runtime_support_files'],support_sha256={n:sha(root/n) for n in parent['support_sha256']},runtime_delta=changed))
 proof=dict(at=now(),source=HEAD,reviewer='gpt-6-astra',reasoning_effort='xhigh',agent='/root/walk418_review',method='AST extraction of current _hits/route_hits; Python/NumPy, no JIT, file mutation, replay or timing.',
  input=dict(walker_x=24.5,hero_history_x=[34.5]*11,whole_route_x='linspace(34.5,29.5,31) + repeat(29.5,10)',whole_route_y='repeat(10.0,31) + linspace(9.46,4.6,10)',hero_box_offsets=[-.25,-1.553,.25,.532],whole_span=[0,40],suffix_span=[30,10],margin=.5),
  observed=dict(parent_contacts=[],whole_suffix_contacts=list(range(32,41)),suffix_only_contacts=[],whole_hi_at_30_and_40=[27.433333333333323]*2,suffix_hi_at_30_and_40=[25.96666666666666]*2),
  production_callers=['knife_chain_air_native.py:750-767 ordinary_post(parent) -> geo.scan(p); origin parent.through','knife_chain_face_hook.py:478-485 future control F continuation -> geo.scan_batch(paths)'],
  finding='P2: offset>0 substitutes the future first hero point for the missing prelude, so the walker stops closing too early; parent scan does not transfer its walker state/history.',
  physical_replay=False,live_damage_claim=False,other_reviewed_checks='No new P0-P2 found in owner/hazard/target separation, HeroBox convention, normal per-frame catch_up feed, or warmup signatures.')
 put(A/'ASTRA_REVIEW418.json',proof)
 review=dict(at=now(),source=HEAD,delivery=418,formal_received=True,accepted=False,source_accepted=False,source_review_pending=True,critical_review=str(A/'ASTRA_REVIEW418.json'),blocker=proof['finding'],repair_seq=359,author_tests_reported_before_warm=2105,author_post_warm_reports=[46,49],new_test_cases=14,broad_tests_repeated=False,formal_P_started=False,live_released=False,live_paused_by_user=True,
  production_evidence_gap='Author W4 is4924058d+package, frame-gated by patch_wkab; six manifest source files differ from8a. Useful local evidence, not final candidate async production proof.')
 put(A/'SOURCE_REVIEW.json',review);put(B/'analysis/committed388_20261111/RECEIPT418.json',review)
 text='''# #418关键源审（8a9919e6，11-13）

用户原话130/133/134已定走路规则和5.5u停步，未重新争论规则。按项目workflow由gpt-6-astra xhigh集中审核核心模型/接线，Sol核交付证据。Astra确认一个P2，其余所查owner/hazard/target排除、HeroBox约定、正常逐帧catch_up及warm签名未定位新P0-P2。作者14新例、2105受影响及预热后46/49为作者报告，未重跑广套件。

## P2：未来接续段用首点回填前段，漏算另一只已走近的距离

walk_rule.py:114–116把offset>0时now+1..origin-1的她位置设成未来首点。真实调用：knife_chain_air_native._continuations:750–767由ordinary_post(parent)生成origin=parent.through的后段、以当前原点geo.scan；knife_chain_face_hook.entry_outs:478–485由未来控制帧F生成后段、同当前geo.scan_batch。此前扫描父段并未传下walker区间/她最近11帧历史。

Astra已运行纯AST/NumPy组件反例，输入输出见ASTRA_REVIEW418.json：怪根24.5、历史她在34.5，前30帧高空从34.5接近29.5，后段在29.5下降。前段无碰身；完整路线后段32–40有接触，未来后段单独查却全部放过，根右端少1.4667u（27.4333对25.9667），已包含0.5余量。不是HERO2完整动作重放，不编造实机HP。

修复不变量：未来接续段继承同一候选前段推进后的walker区间与最近11帧她历史，或对未知前段及仍影响未来的历史作保守处理；缺前段不能靠未来终点回填缩小。单条/批量均需覆盖。一个完整路线后缀与携带前段状态检查一致的回归足够，复用原14例；不扩2105/大矩阵，不改已选走路规则或全局forecast。

作者W4重放（4924058d+包、INLINE1、patch_wkab按origin帧门控）是局部工程证据；manifest相对最终8a有6源差异。正式P前，修复最终源只补一对短开关功能证据：相同一致合成起点/实际异步profile、真实几何/选择/before_send/sent，无Clear/强选/生产帧门控。可复用原工具及一处窗口，不要求重跑6场景、50盘或精确帧矩阵。Sol源核通过再做受影响有限P。用户实机暂停，本次没有游戏或P。
'''
 (A/'REVIEW418.md').write_text(text,'utf-8')
 mail=B/'sol/TO_OPUS.md';oldmail=mail.read_text('utf-8-sig');first,rest=oldmail.split('\n',1)
 message='''
## seq359（#418同包）：Astra核到未来接续段低估走路区间；先修再最终源短正例/P

8a9919e6已读，按workflow集中调用gpt-6-astra xhigh核核心模型；规则/5.5u由用户已定，不重开。新P2：walk_rule.py114–116在off>0时把now+1..origin-1的她位置都设为未来首点，可能使怪过早停步。可达调用air_native._continuations750–767（ordinary_post origin=parent.through，当前geo.scan）、face_hook.entry_outs478–485（未来F，同geo.scan_batch）。父段单独查过不等于传下walker区间/她历史。

已运行纯AST/NumPy反例，完整输入/输出在analysis/walk_rule418_20261113/ASTRA_REVIEW418.json：怪24.5，她历史34.5，前30帧高空从34.5走向29.5、后10帧固定x29.5下降。前段无接触；完整路线32–40碰身，后段单查全无接触，根右端少1.4667u（27.4333 vs25.9667），已有0.5余量。只主张数学/组件漏查，不报实机HP。

请同包修正：接续段从同一候选前段继承walker状态及最近11帧她历史；或对未知前段/剩余历史窗口保守处理。缺失前段不能以未来终点反填而缩小。单条/批量都保留此不变量。一个“整路后缀=携前段状态检查”的回归，原14例复用，不扩大2105/矩阵。实现方式由你定，不改其它怪/hazard/target规则。

另功能证据的真实版本缺口合在这一包：W4明确是492+包且patch_wkab按origin门控，不能当最终8a生产通过。修后最终源只补一处原窗口的短开关对照，允许写明的一致合成输入，使用实际异步profile、真实几何/选择/before_send/sent，证明目标接受或拒绝分支+实际wire。无Clear/强选/生产帧门控，诊断只读包装可说明；可复用原工具，不重跑6回放/50局。核后Sol做有限P；本信不授权你P/游戏，用户仍暂停。

---
'''
 q=mail.with_suffix('.md.sol.tmp');q.write_text(first+'\n'+message+rest,'utf-8');os.replace(q,mail)
 state.update(at=now(),phase='WALK418_CRITICAL_REVIEW_REPAIR359_LIVE_PAUSED',last_scanned_opus=418,candidate_source=HEAD,source_review_pending=True,pending_opus=dict(seq=359,package=418,reason=proof['finding']),opus418_receipt=str(B/'analysis/committed388_20261111/RECEIPT418.json'),next_phase='Opus same-package future-prefix repair plus one final-source async short functional comparison. Sol reviews then finite P; game pause remains.')
 put(B/'sol/STATUS.json',state);put(A/'HANDOFF359.json',dict(at=now(),seq=359,package=418,mail_written=True,wake_enqueued=False,listener_received=False,actual_work_seen=False,formal_completion_seen=False))
 print(json.dumps(dict(source=HEAD,runtime_files=len(names),source_accepted=False,repair_seq=359,mail_written=True,P_started=False,game_paused=True),ensure_ascii=False))

if __name__=='__main__':main()
