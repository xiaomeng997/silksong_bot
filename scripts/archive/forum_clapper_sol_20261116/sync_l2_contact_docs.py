"""Validate and synchronize only the requested L2 documentation change."""
from pathlib import Path
import ast,datetime,hashlib,json,os,re,subprocess
B=Path('C:/ssbot/data/m2_play/clapper_plan');M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';REL='docs/plans/forum_clapper_l2_tactics.md';S='9f6da15674da8c396d729a680f6868d47d9e233f'
def git(r,*a):return subprocess.check_output([G,'-C',str(r),*a],encoding='utf-8').strip()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st['source_frozen_for_P'] and not st.get('own_offline_jobs') and st['current_source']==S
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];assert re.search(r'\*\*最新编号\*\*：#322\b',summary) and read(B/'sol/OPUS_WAKE.json')['seq']==250
assert git(D,'rev-parse','HEAD')=='f9e253b16f3324439fd55d192683bfd9f1977dfb'
assert git(M,'diff','--name-only')==REL and not git(M,'diff','--cached','--name-only')
assert not git(D,'diff','--name-only') and not git(V,'diff','--name-only')
assert not git(D,'diff',S,'--','brain/ssbot')
old=subprocess.check_output([G,'-C',str(M),'show','HEAD:'+REL])
assert all((root/REL).read_bytes().replace(b'\r\n',b'\n')==old.replace(b'\r\n',b'\n') for root in (D,V))
doc=(M/REL).read_text(encoding='utf-8-sig');rules=set()
tree=ast.parse((D/'brain/ssbot/combat/tactics/clapper_tactics.py').read_text(encoding='utf-8'))
for cls in (n for n in tree.body if isinstance(n,ast.ClassDef)):
 for n in cls.body:
  if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='scores' for t in n.targets):rules.update(ast.literal_eval(n.value))
assert len(rules)==13 and all('`'+r+'`' in doc for r in rules)
assert all('middle_jump → '+route in doc for route in ('guide','stand','under','over','hold'))
assert doc.count('大黄蜂当前空地要求')==6 and 'ReturnRequest' in doc and 'return_body' in doc
width=None
for line in doc.splitlines():
 if line.startswith('|'):
  cells=len(line.split('|'))-2
  if width is None:width=cells
  else:assert cells==width,('table column count',line)
 else:width=None
heads={}
for root in (M,D,V):
 if root!=M:(root/REL).write_bytes((M/REL).read_bytes())
 git(root,'diff','--check','--',REL);git(root,'add','--',REL);git(root,'commit','-m','docs: specify hero contact requirements for L2 tactics','--',REL)
 heads[str(root)]=git(root,'rev-parse','HEAD');assert not git(root,'diff','--name-only') and not git(root,'diff','--cached','--name-only')
assert (M/REL).read_bytes()==(D/REL).read_bytes()==(V/REL).read_bytes()
assert not git(D,'diff',S,'--','brain/ssbot')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st['source_frozen_for_P'] and not st.get('own_offline_jobs')
st.update(at=now(),current_head=heads[str(D)],l2_tactic_document=str(M/REL),l2_tactic_document_source=S,l2_hero_contact_documented_at=now(),l2_tactic_document_sha256=hashlib.sha256((M/REL).read_bytes()).hexdigest())
p=B/'sol/STATUS.contact_docs.tmp';p.write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
print(json.dumps(dict(updated=REL,rules=sorted(rules),middle_routes=5,three_copies_equal=True,tracked_runtime_unchanged=True,heads=heads),ensure_ascii=False))
