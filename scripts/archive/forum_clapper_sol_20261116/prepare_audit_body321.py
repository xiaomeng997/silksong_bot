from pathlib import Path
import ast
p=Path('C:/modeling/silksong_bot/tmp/audit_return318_p.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace('four already completed P windows','two already completed #321 P windows').replace("A=B/'analysis/task179_return318_20261106'","A=B/'analysis/task179_body321_20261106'")
s=s.replace('read completed219 P ticks, source/cleanup check and historical receive serial arithmetic','read completed50 P ticks, source/cleanup and finite historical receive arithmetic')
s=s.replace("finals={n:read(A/n/'FINALIZED.json') for n in ['p_on','p_nw','p_off']};assert all(f['cleanup_verified'] for f in finals.values())\n assert finals['p_nw']['execution_ok'] and finals['p_off']['execution_ok']\n assert len({finals['p_on']['pid'],finals['p_nw']['pid'],finals['p_off']['pid']})==3", "finals={n:read(A/n/'FINALIZED.json') for n in ['startup','p_NW']};assert all(f['cleanup_verified'] and f['execution_ok'] for f in finals.values())\n assert finals['startup']['pid']!=finals['p_NW']['pid']")
s=s.replace("O=B/'opus/review179/l1_317'","O=B/'opus/review179/l1_321'")
old="[('A','p_on/A',2785,2900,116,[2793,2795,2812,2816,2831,2836,2870,2884],'a4air9'),('N','p_nw/N',2810,2830,21,[2813,2819,2822,2824],'n1air9'),('W','p_nw/W',2860,2900,41,[2869,2874,2881,2892],'w3air9'),('D','p_off/D',2600,2640,41,[2601,2604,2632,2639],'n1off9')]"
new="[('N','p_NW/N',2813,2835,23,[2813,2819,2822,2824,2830,2835],'f_n1ref'),('W','p_NW/W',2794,2820,27,[2794,2796,2803,2806,2812,2813,2820],'f_w3')]"
assert old in s;s=s.replace(old,new)
s=s.replace('assert total==219','assert total==50')
s=s.replace("resource_interruption='N not started in p_on due unchanged gate; A116 retained. After actual cleanup new guard empty and tar exited; separate remaining N/W and off D, no A repeat.'", "resource_interruption=None")
s=s.replace("scope='Four finite P samples of current conditional production paths; no live/continuous-downslash certification; serial arithmetic must be reviewed before any game gate.'", "scope='N23/W27 finite affectedP on321; not whole-task performance/latency pass or live certificate. Old219 samples not repeated. All peaks and diagnostics preserved.'")
s=s.replace("footer=tr[-1];stats[name]=", "footer=tr[-1];peakf=max(fs,key=lambda f:cost[f]);\n  put(A/(name+'_FULL_DIAGNOSTICS.json'),dict(at=now(),peak_frame=peakf,peak_tick=ticks[peakf],peak_action=actions[peakf],footer=footer))\n  stats[name]=")
s=s.replace("st=read(B/'sol/STATUS.json');st.update(at=now(),phase='RETURN318_P_AUDIT_DONE' if err is None else 'RETURN318_P_AUDIT_ERROR',own_offline_jobs=[]);status(st)", "# Keep own E job registered until the caller confirms actual exit.\n pass")
s=s.replace('RETURN318','RETURN321').replace('audit318.tmp','audit321.tmp')
ast.parse(s);out=Path('C:/modeling/silksong_bot/tmp/audit_body321_p.py');assert not out.exists();out.write_text(s,encoding='utf-8')
print(str(out))
