from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys

B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/cluster_back416_20261113'
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
P=B/'analysis/dash_side412_20261113/source_fixed415'
read=lambda p:json.loads(p.read_text('utf-8-sig'))
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()


def put(p,v):
    q=p.with_suffix(p.suffix+'.sol.tmp')
    q.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
    os.replace(q,p)


def main():
    wake=read(B/'sol/OPUS_WAKE.json');assert wake['seq']==357
    s=read(B/'sol/STATUS.json')
    assert not s['own_offline_jobs'] and not s['live_or_budget_running'] and s['live_paused_by_user']
    A.mkdir(exist_ok=False)
    probes={}
    for k,root in [('new',W),('baseline',P)]:
        z=subprocess.run([sys.executable,'-B','-X','utf8','C:/modeling/silksong_bot/tmp/cluster416_scope_probe.py',str(root)],capture_output=True,text=True,encoding='utf-8')
        assert z.returncode==0,z.stderr
        probes[k]=json.loads(z.stdout)
    assert probes['new']['after_lure']['selected']=='lure' and probes['new']['after_lure']['skip'].get('8') is not None
    assert probes['new']['pending_middle_return'] is None and probes['new']['skipped']['iid']==8
    assert probes['baseline']['after_lure']['reason']=='other_move' and probes['baseline']['pending_middle_return']['iid']==8
    put(A/'SCOPE_PROBE.json',dict(at=now(),probes=probes,physical_damage_claim=False))
    replay=B/'opus/review182/s312/px/r2/p2c_x4_ep1_s9484_PX'
    m=read(replay/'CONFIGURATION_MANIFEST.json')
    assert all(hashlib.sha256((W/'brain/ssbot'/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h for n,h in m['source_sha256'].items())
    sends=[json.loads(l) for l in (replay/'decisions_i0.chain.jsonl').open(encoding='utf-8')]
    selected=[z for z in sends if z['event']=='transport_sent' and z.get('frame') in [9498,9499,9500]]
    assert next(z for z in selected if z['frame']==9499)['mask']==2097154
    put(A/'AUTHOR_PRODUCTION_EVIDENCE.json',dict(at=now(),artifact=str(replay),source_files_matched=len(m['source_sha256']),
        normalized_LF_fingerprints=True,actual_sends=selected,synthetic_from=9484,measured_profile_INLINE='1',
        limitations=['Model hero, recorded enemies, no live improvement claim.','Five adapter operational keys unresolved; formal Sol P not started.','Harness scores no side-slash model hit; reach estimate is not actual hit proof.']))
    files=['brain/ssbot/combat/tactics/clapper_plans.py','brain/ssbot/combat/tactics/clapper_tactics.py','brain/ssbot/combat/two_play.py','brain/ssbot/train/forum_planner_policy.py','brain/tests/test_cluster_plan2_back.py']
    source='114eb8ff19267b7e3f4f3a949126b6f3d5f0ff3e'
    review=dict(at=now(),delivery=416,source=source,accepted=False,source_review_pending=True,
        reviewed_files_sha256={n:hashlib.sha256((W/n).read_bytes()).hexdigest() for n in files},
        author_tests_reported=1094,author_new_tests_source_reviewed=16,broad_tests_repeated=False,
        positive_production_evidence_verified=True,new_blocker='P2: _other_jump_over suppresses other_move and records back_skip outside cluster attack plan 2; lure_slash also loses its public middle-return request.',
        counterexample=str(A/'SCOPE_PROBE.json'),formal_P_started=False,repair_seq=358,live_paused_by_user=True)
    put(A/'SOURCE_REVIEW.json',review)
    put(B/'analysis/committed388_20261111/RECEIPT416.json',review)
    text='''# #416独立源审（114eb8ff，11-13）

用户原话125的范围为成团方案2（cluster attack）回来接着平砍，不回中间。作者16新测试源码与最终1094通过记录已读，不重跑广套件。新旧4运行文件差异已读；作者p2c的239源码LF指纹与114工作树一致，9486保持attack_back_other、9498 in_reach、9499实际two:idle发送A+R到9501、9500续到9502均核。合成主角自9484，怪按录制；平砍命中只作刀宽估算，不冒称实机命中或改善。

## 待修P2：方案2例外泄漏到方案1，额外取消另一只已落地跳怪的回中待办

clapper_plans.py:1474在所有带other_move的阶段调用_other_jump_over，1604–1617不检查scene/selected/phase，危险已过时在非dry路径直接_skip_middle。lure_slash也在调用范围，clapper_tactics.py:466–471随后按back_skip不再为该招结束生成公共回中待办。不是只给已明确要求的cluster attack回程例外。

独立L2组件探针（tmp/cluster416_scope_probe.py，明确预置lure_slash并补历史near事实，不是完整物理/发键证据）：同样另一只CC_JUMP/Slam Recover，114保持lure_slash并写back_skip[8]=10.0667；转Idle后pending back为空、back_skipped却记cluster attack plan。父e1c按原other_move失效、不写skip，同一招结束生成iid8公共回中待办。证据SCOPE_PROBE.json。不主张已发生掉血。

请同包把方案2的other_move例外及回中抑制限定到获准的cluster attack范围，保留lure/其它方案的原行为；若有明确已批准的跨方案规则，请先提供来源及相应行为证据，避免凭函数复用扩大语义。复用本反例补一个区分分支的回归即可；原方案2正例与IdleHit安全守卫保留。键序列不变则复用p2c生产证据，不要求重跑1094或回放矩阵。源码修正核收后Sol做受影响有限P，#415地面回退成本作为既存限制继续记录，不夹带优化。本次未开P或游戏，用户暂停不变。
'''
    (A/'REVIEW416.md').write_text(text,'utf-8')
    mail=B/'sol/TO_OPUS.md';old=mail.read_text('utf-8-sig');first,rest=old.split('\n',1)
    message='''
## seq358（#416同包）：方案2正例已核；_other_jump_over把回中抑制泄漏到lure

114eb8ff新4运行文件、16测试源码及最终1094报告已读，不重跑广套件。p2c的239源码LF指纹与提交工作树一致；9486保持回程、9498 in_reach、9499 two:idle A+R→9501/9500续→9502已核。合成/录制怪/平砍只估算未核真命中的限制保留。

唯一当前P2：1474对所有other_move阶段调用_other_jump_over；1604–1617不检查cluster/attack范围、非dry时直接_skip_middle。独立同fixture的lure_slash负例：另一只CC_JUMP/Slam Recover，114保持lure并写back_skip[8]；同一招转Idle不再生成公共back，日志却写cluster attack plan。父e1c原other_move失效、不写skip，结束仍生成该招back。tmp/cluster416_scope_probe.py、analysis/cluster_back416_20261113/SCOPE_PROBE.json；明确L2组件/预置lure_slash和历史near，不编造物理掉血。

用户125只要求方案2回来接着砍。请同包限定这一例外与回中抑制到已授权cluster attack范围，保留lure/其它分支原行为；若你认为跨方案也是既定语义，请先给明确来源和行为证据。补一个区分lure/attack的回归足够，原正例与IdleHit守卫保留；键/接口没变化则复用p2c，不重跑1094或矩阵。核后Sol统一有限P，415既存G成本不夹带优化；用户实机暂停。

---
'''
    q=mail.with_suffix('.md.sol.tmp');q.write_text(first+'\n'+message+rest,'utf-8');os.replace(q,mail)
    s.update(at=now(),phase='CLUSTER416_SOURCE_REVIEW_SCOPE_REPAIR358_LIVE_PAUSED',candidate_source=source,
        source_review_pending=True,last_scanned_opus=416,pending_opus=dict(seq=358,package=416,reason=review['new_blocker']),
        opus416_receipt=str(B/'analysis/committed388_20261111/RECEIPT416.json'),
        next_phase='Opus same-package scoped repair; Sol reviews delivery then runs affected finite P. Game pause remains. No stopped batch resumed.')
    put(B/'sol/STATUS.json',s)
    put(A/'HANDOFF358.json',dict(at=now(),seq=358,package=416,mail_written=True,wake_enqueued=False,
        listener_received=False,actual_work_seen=False,formal_completion_seen=False))
    print(json.dumps(dict(source=source,source_accepted=False,repair_seq=358,mail_written=True,formal_P_started=False,game_paused=True),ensure_ascii=False))


if __name__=='__main__':main()
