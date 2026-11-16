"""Bind the actual current-chat reply to this one fresh batch; no game launch."""
from pathlib import Path
import datetime,hashlib,json
B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_b13b404_20261113'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
answer='开始新50盘，直接开打（推荐）'

def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    assert not (G/'USER_NEW50_AUTHORIZATION.json').exists() and not (G/'START_AUTHORIZATION.json').exists()
    assert not (G/'LAUNCH_CLAIM.json').exists()
    bs=read(G/'BATCH_SPEC.json');assert not bs['started']
    head=bs['source']
    auth=dict(at=now,kind='explicit_user_chat_unattended_new50',user_text=answer,source=head,batch_id=G.name,
        planned_bouts=50,same_game_continuous=True,ready_dialog_required=False,source_review_required=True,
        affected_formal_timing_required=True,actual_preflight_resource_input_recording_cleanup_required=True,
        clear_or_real_2hp_continue=True,death_runtime_input_log_recovery_resource_cleanup_fault_stops_batch=True,
        reopen_stopped_batches=False,scope='Exactly this fresh B13+B13B same-seed50; full recording; 2HP protection continues, integrity faults stop. No later batches.',
        reply_source='Current chat request_user_input_async answer call_2cb5359897814bed8e8c5672eb66adec; also Opus relay406, same batch and not an additional50.',started=False,consumed=False)
    put(G/'USER_NEW50_AUTHORIZATION.json',auth)
    p=G/'CONTINUOUS_PLAN.json';x=read(p);x.update(authorization=answer,at=now);put(p,x)
    p=G/'TRIAL_CONFIG_DRAFT.json';x=read(p);x.update(user_authorized=True,authorization=answer,at=now);put(p,x)
    p=G/'finish_preparation.py';text=p.read_text(encoding='utf-8');assert 'range(376,405)' in text
    p.write_text(text.replace('range(376,405)','range(376,407)'),encoding='utf-8')
    p=G/'LIFECYCLE_REVIEW.json';x=read(p);x['files']['finish_preparation.py']=sha(G/'finish_preparation.py')
    x['authorization_mail_addendum']='405 descriptive cost and406 same-batch authorization relay read; explicit accepted set updated, no gate semantics changed.';put(p,x)
    p=G/'PENDING_AUTHORIZATION.json';x=read(p);x.update(answer_received_at=now,answer=answer,authorization_present=True,authorization_receipt=str(G/'USER_NEW50_AUTHORIZATION.json'),pending='Actual contract/warm/input/capture/resource/GO gates.');put(p,x)
    bs.update(authorization=answer,state='AUTHORIZED_PREPARATION',updated_at=now);put(G/'BATCH_SPEC.json',bs)
    p=B/'sol/STATUS.json';s=read(p);assert not s['live_or_budget_running'] and not s.get('own_live_session')
    s.update(at=now,last_scanned_opus=406,opus405_state='descriptive_cost_by_owner_read_not_independently_recomputed_no_new_task',opus406_state='same_batch_authorization_relay_and_current_chat_direct_answer_received',
        phase='B13B404_NEW50_AUTHORIZED_FINAL_PREPARATION',next_phase='Finish binding, launch held owned game/worker/capture, verify actual gates, then autonomous GO for this50 only.')
    put(p,s)
    p=B/'sol/TO_OPUS.md';t=p.read_text(encoding='utf-8');title='# Sol → Opus 留言队列\n';assert t.startswith(title)
    note='\n## #405/#406已收，当前聊天也明确开打同一批50（信息，无新任务/唤醒）\n\n用户在当前聊天选择“开始新50盘，直接开打”，已绑定w13_50_b13b404_20261113/e7e975f3，仅本批50。#406转达和本回复合并为同一批，不加局数；Sol正在做最后合约和真实预热/输入/录像/资源门，过后GO。#405按控制者的成本解释已读，原成对整拍耗时保留，不改成单helper因果证明；结束后统计按实际控制者分开。请按原约定在忙标记期间停止重计算；第3项不改控制代码，不启动游戏/P。\n\n---\n'
    p.write_text(title+note+t[len(title):],encoding='utf-8')
    print(json.dumps(dict(batch=G.name,source=head,authorized_bouts=50,same_batch_relay=True,game_started=False)))

if __name__=='__main__':main()
