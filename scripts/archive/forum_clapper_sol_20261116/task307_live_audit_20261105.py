from pathlib import Path
old=Path('C:/modeling/silksong_bot/tmp/task304_live_audit_20261105.py').read_text(encoding='utf-8')
old=old.replace('w13_walk179L2_20261106T000950Z_1263e9e3','w13_guard179L3_20261106T012400Z_5df8711e')
old=old.replace('1263e9e398859b0fa98e6d3141ac955288e05059','5df8711ea04accff8c03e87560d31b53b2e87a09')
old=old.replace('2738<=f<=2804','2590<=f<=3100').replace("2738<=d['f']<=2804","2590<=d['f']<=3100").replace("2738<=d['frame']<=2804","2590<=d['frame']<=3100")
old=old.replace("'known_causal_prefix':'2761 actual bounce on335476 then target335470 already SlamAntic; rune_transfer.air returns external-step blocked2793; ordinary planner takes over,2801 actual2HP from335470 SlamCollider1. HP exposure oldsourceMove is responsibility only, not collider attribution.'","'known_causal_prefix':'Pending actual L3 causal review; do not import L2 cause'" )
old=old.replace("'status':'firstloss stopped; causality review needed; do not retry'","'status':'Single bout ended; actual causal review needed; do not retry'")
exec(compile(old,__file__,'exec'))
