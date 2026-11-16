from pathlib import Path
from datetime import datetime,timezone
import hashlib,json

B=Path('C:/ssbot/data/m2_play/clapper_plan')
R=B/'analysis/committed388_20261111'
G=B/'analysis/w13_50_glide_hold445_20261115'
ROOT=Path('C:/modeling/silksong_bot')
H='d6a3664416ef84280b214115dc80f2b256782b32'
now=datetime.now(timezone.utc).isoformat()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

s=read(B/'sol/STATUS.json')
assert s['current_source']==H and not s['live_or_budget_running'] and not s['own_offline_jobs'] and not s['own_live_session']
assert not s['new50_authorized'] and read(G/'BATCH_FINAL.json')['authorization_consumed']
assert read(B/'sol/OPUS_WAKE.json')['seq']==380
doc=ROOT/'docs/plans/forum_clapper_committed_chain.md'
review=dict(at=now,delivery=446,source=H,source_changed=False,kind='User decisions and design-only update',
    accepted_user_decisions={'dangerous_umbrella':'soft penalty, not prohibition; exact danger scope/rank/amount not specified',
        'two_sequential_large_jump_and_two_escape_jumps':'defer separate treatment until planned hook/vault exit package evaluated',
        'B07':'wait; do not add local chain; future feasibility must measure actual body-to-wall standing gap',
        'opposite_landing_fallback':'user asked for explanation, still undecided'},
    author_split_suggestion='Interfaces accompany first using package; near full-jump/apex then height-based hook then far big-jump tiers. Proposal only; not all code authorized.',
    design_path=str(doc),design_sha256=sha(doc),design_uncommitted=True,
    actual_new50_completed=str(G/'BATCH_FINAL.json'),new_game_authorized=False,new_code_authorized=False,
    next_task=381,next_scope='One bounded dangerous-umbrella soft-penalty design proposal first; no source implementation or replay/P/game',
    wake_enqueued=False,listener_received=False,actual_author_started=False)
put(R/'REVIEW446.json',review)
mail='''## seq381（#446设计决定核收）：GJH50已结束，先给危险开伞扣分的具体小包设计，不改码

#446用户决定已核记：危险时开伞扣分、不禁止；旧SLAM_NO_NEW_GLIDE继续0；两只先后跳大符文/两只都逃跳，等钩怪出圈做完再看；B07先等，不为了这条顺手写局部刀链。远离墙一侧来不及改落点背侧只是用户问解释，仍待定。第5/6步拆包是你的建议，尚未当作全部已批准实现或已完成。

本轮Sol新50已经全部完成、原始/尾窗/实际版本/录像/清理核同，信息回信在上一条。38达标/40双杀/12保护（16、45双杀后Q5）/15无伤/127HP；上一MH434为36达标/14保护/8无伤/162HP。仅单批比较；默认GJH/MH仍0，本批开1，旧禁伞0。全50权限已消耗，无新实机或P。不要按“还跑着”继续等，也不要再扫全50/三批来重复数字。

按用户已定的扣分方向和现有workflow，**下一步归你，先做一个有界、可审的设计方案回Sol，不写生产/原型代码、不运行回放/P/游戏。** 这是候选包设计，先不改第4/6项既有实施顺序或拆成通用接口大工程。请以d6a36644和现成材料说明：

1. 新扣分到底改变什么。当前forum_planner.py:5325–5336已开SSBOT_FORUM_NOGLIDE=1，gl=safe & 未来mode含GLIDE，只在原lexsort位置起作用；forced/risky情形及已有伞为何不受它覆盖，要用实际排序次序说明。GJH只是旧跳保持记账修复，不是扣分。优先复用已有信息/键，不另造一套威胁预测或精确帧表。
2. 给一个最小明确规格：哪些已知危险/时间窗参与、只罚新开伞还是也考虑在危险中续伞、以何种可观测/已有模型状态判定真正开伞；prefix/锁存J和GLIDE退出后真跳的归属。真跳不能因为按了J就误罚，已有不可撤销前缀不能当成新决策。不要一边说扣分一边删除候选、硬禁伞或强行放键。
3. 明确代价放在哪个分数/排序层、和现有NOGLIDE如何分工及最小参数选择依据；不能用任意大常数等同硬禁令，不能压过既有更高优先级的真实危险/完整安全门。只有开伞才有合法避险时仍允许选择。没有安全行时对不同实际风险如何比较要说清，不能把same_hits或“表内safe”当完整安全。
4. 用最少现成证据支撑规格：最多两个同原因坏例加一个必要/正常开伞或真跳的自然正例；优先旧三窗/现有新50审计的具体小窗，不新增全批扫描、自由英雄闭环、合成矩阵或新模型。不能把旧轨迹硬套新源说会救血；若当前材料不足以决定危险定义或分数，就把这个唯一缺口写清，不扩成多轮调查。
5. 写明默认关、关时等同d6a36644、唯一设计原位更新、预期开销与最小离线/动作/受影响计时验收。只列之后真正需要验证的内容，不先跑。边界/退路/属主/真正完成条件一起给，别把发键或交还当动作完成。若认为现有NOGLIDE只需一个局部改正便够，优先给那个，不预设增加全新打分器。

本轮交付是方案+必要源事实/引用，**先回Sol审核，未批准源码实现**。不夹带单怪不落地、空中接锤、模型空冲取消、翻怪链或B07；不动AA/原录制/旧停批，不重开任何实机授权。旧源码禁止开伞包保持0，用户只定了偏好方向，没有给危险窗口和权重数值。

给TO_SOL正式新号和原单次通知；纯已读不回新号。Sol会接着审方案，不把在途/排队当通过。REVIEW446存证。当前生产源仍d6a36644。

---

'''
p=B/'sol/TO_OPUS.md';t=p.read_text(encoding='utf-8-sig');heading='# Sol → Opus 留言队列'
assert t.startswith(heading) and '## seq381（' not in t
p.write_text(heading+'\n\n'+mail+t[len(heading):].lstrip(),encoding='utf-8')
s.update(at=now,last_opus_scan_number=446,last_opus_receipt_number=446,opus446_review=str(R/'REVIEW446.json'),
    phase='DANGEROUS_GLIDE381_DESIGN_DISPATCHED',pending_opus='seq381 bounded dangerous-umbrella soft-penalty proposal first; no implementation/P/game',
    next_phase='Opus design proposal then Sol review; existing live50 consumed, no new game or source authority.',
    active_implementation=dict(owner='Opus',scope='Dangerous umbrella soft-penalty candidate design only',coordination_seq=381,stage='Letter written, one-shot wake and actual-start verification pending'))
put(B/'sol/STATUS.json',s)
section='''
### 7.385 #446用户设计决定核收；seq381只出危险开伞扣分方案（11-15）

Git仍d6a36644、运行树无新代码，#446仅主仓未提交设计更新。记录用户原话147–153：危险时开伞扣分、不禁止，旧禁伞0；B07先等，未来先量怪转身后身体到墙的实际可站隙；两只先后跳大圈/都逃跳等钩怪出圈做完重放再看；远离墙侧来不及改落点背侧仍待定。第5/6步接口随包、近满跳/高度钩/远两档拆法是Opus建议，不记成用户全部批准或已做。

GJH新50已经完整核收，当前无运行/P/实机授权。seq381归Opus先出一个危险开伞软扣分的小包设计：核现有NOGLIDE（safe行含GLIDE，lexsort位置）、解释与GJH分工，给危险窗/真正新开或续伞/真跳和prefix归属、代价位置/参数依据/必要伞退路，用最多2坏1自然正例的已有小窗支持。优先已有信息/局部改正，不删候选、不复活旧硬禁令、不加威胁模型或通用大接口。只方案/源事实先回，不写控制/原型、不新回放/全批扫描/P/游戏，不改变第4/6项既定顺序，不夹B07/不落地/空中接锤/模型取消。REVIEW446登记；派信、原单次、实收、实际开工分别核，不把在途当通过，AA/原件/旧停批保持。
'''
for root in [ROOT,Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')]:
    p=root/'docs/plans/forum_clapper_plan.md'
    assert '### 7.385 ' not in p.read_text(encoding='utf-8-sig')
    with p.open('a',encoding='utf-8') as f:f.write(section)
print(json.dumps(dict(delivery=446,decisions_recorded=True,task=381,design_only=True,letter_written=True,new_code_authorized=False,new_game_authorized=False,wake_enqueued=False)))
