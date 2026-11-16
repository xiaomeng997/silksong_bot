"""Freeze reviewed d6a36644 and bind two affected finite P windows. No game API."""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import runpy
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
B = Path("C:/ssbot/data/m2_play/clapper_plan")
A = B / "analysis/glide_jump_hold445_20261115"
OLD = B / "analysis/middle_handoff434_20261114"
R = B / "analysis/committed388_20261111"
E = B / "opus/review182/s312/r7"
W = Path("C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot")
ROOT = Path("C:/modeling/silksong_bot")
H = "d6a3664416ef84280b214115dc80f2b256782b32"
PARENT = "8e34fb6c71a3338b7652c741b12c5048086c6ae9"
GIT = "C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe"
now = lambda: datetime.now(timezone.utc).isoformat()
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
norm = lambda s: hashlib.sha256(s.replace(b"\r\n", b"\n")).hexdigest()


def put(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args, cwd=W):
    p = subprocess.run([GIT, "-C", str(cwd), *args], capture_output=True, check=True)
    if p.stderr and A.exists():
        with (A / "SETUP_GIT_DIAGNOSTICS.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(at=now(), cwd=str(cwd), args=args,
                                   stderr=p.stderr.decode("utf-8", "replace")), ensure_ascii=False) + "\n")
    return p.stdout


assert git("rev-parse", "HEAD").decode().strip() == H
assert git("rev-parse", H + "^").decode().strip() == PARENT
assert not git("diff", "HEAD", "--", "brain/ssbot", "brain/tests/test_glide_jump_hold380.py").strip()
s = read(B / "sol/STATUS.json")
assert not s["live_or_budget_running"] and not s["own_offline_jobs"]
assert s.get("own_live_session") is None and not (B / "sol/performance/ACTIVE.json").exists()
resume = sys.argv[1:] == ["--resume-unpublished-freeze"]
assert not sys.argv[1:] or resume
if resume:
    assert A.is_dir() and not (A / "SOURCE_PACKET_FIXED.json").exists()
    assert not (A / "CASE_ON.json").exists() and not (A / "ORCHESTRATION.json").exists()
else:
    assert not A.exists()
    A.mkdir()
S = A / "source_fixed445"
S.mkdir(exist_ok=resume)
parent = read(OLD / "SOURCE_PACKET_FIXED.json")
assert parent["source"] == PARENT
base = Path(parent["source_root"])
for n, digest in {**parent["raw_runtime_files_sha256"], **parent["support_sha256"]}.items():
    assert sha(base / n) == digest, n
    dst = S / n
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base / n, dst)

changes = git("diff", "--name-only", PARENT, H).decode().splitlines()
runtime = [n for n in changes if n.startswith(("brain/ssbot/", "knowledge/"))]
assert set(runtime) == {"brain/ssbot/combat/forum_planner.py", "brain/ssbot/train/forum_planner_policy.py"}
assert set(changes) == set(runtime) | {"brain/tests/test_glide_jump_hold380.py"}
bindings = []
for n in changes:
    data = git("show", H + ":" + n)
    dst = S / n
    dst.parent.mkdir(parents=True, exist_ok=True)
    old = dst.read_bytes() if dst.exists() else b""
    dst.write_bytes(data.replace(b"\n", b"\r\n") if b"\r\n" in old else data)
    assert norm(data) == norm((W / n).read_bytes()) == norm(dst.read_bytes()), n
    bindings.append(dict(file=n, commit_lf_sha256=norm(data), fixed_raw_sha256=sha(dst)))

# A shallow, local object fetch avoids duplicating the old source's entire Git history.
git("init", "--quiet", cwd=S)
git("fetch", "--quiet", "--no-tags", "--depth=1", str(W), H, cwd=S)
git("symbolic-ref", "HEAD", "refs/heads/codex/glide-hold445-freeze", cwd=S)
git("update-ref", "refs/heads/codex/glide-hold445-freeze", H, cwd=S)
git("read-tree", H, cwd=S)
assert not git("diff", "HEAD", "--", "brain/ssbot", "knowledge", cwd=S).strip()
support = [*parent["support_sha256"], "brain/tests/test_glide_jump_hold380.py"]
packet = dict(at=now(), source=H, parent=PARENT, source_root=str(S), runtime_delta=runtime,
              raw_runtime_files_sha256={n: sha(S / n) for n in parent["raw_runtime_files_sha256"]},
              runtime_support_files=support, support_sha256={n: sha(S / n) for n in support})
put(A / "SOURCE_PACKET_FIXED.json", packet)

review = dict(at=now(), source=H, parent=PARENT, delivery=445, accepted=True,
              source_binding=bindings, independent_source_review="Sol runtime delta, logging, neighboring selection/lifecycle paths and tests read; no new P0-P2",
              critical_review=dict(agent="/root/walk418_review", scope="Same-stage concentrated source review; lifecycle, final-row index, prefix new-jump and tests", no_P0_P2=True),
              author_new_tests=11, author_affected_tests=170, root_repeated_author_tests=False,
              source_review_pending=False, game_authorized=False,
              limitations=["table-local safety is not full escape safety", "original deadline/hold-history mismatch retained", "glide dash-cancel model hint unresolved; no HP inference", "default off; old no-new-glide remains off"])
put(A / "SOURCE_REVIEW_FINAL.json", review)
put(R / "REVIEW445.json", dict(review, stage="Source accepted; finite P preparation, not yet measured"))

for name in ["engineering_helpers.py", "resource_background.py", "RESOURCE_BACKGROUND_APPROVAL.json", "entry_v4.py"]:
    shutil.copy2(OLD / name, A / name)
inputs = read(OLD / "REPLAY_INPUT_BINDING.json")["files"]
assert all(sha(Path(n)) == digest for n, digest in inputs.items())
trial = E / "trials/mh_ep9"
assert trial.exists()
inputs.update({str(p): sha(p) for p in trial.rglob("*") if p.is_file() and "__pycache__" not in p.parts})
inputs[str(A / "entry_v4.py")] = sha(A / "entry_v4.py")
inputs[str(ROOT / "tmp/run_glide445_p.py")] = sha(ROOT / "tmp/run_glide445_p.py")
put(A / "REPLAY_INPUT_BINDING.json", dict(at=now(), files=inputs,
    scope="Unchanged reviewed entry_v4 and stack. Own policy B, synthetic hero B+1; recorded fixture only through B-1. Not original-state forced shadow."))

case = read(OLD / "CASE_ON.json")
flags = [x for x in case["contexts"][0]["flags"] if not x.startswith(("--opus-synth=", "--no-force-from=", "--fixture-recorded-run=", "--fixture-own-from=", "--env=SSBOT_FORUM_MIDDLE_HANDOFF=", "--env=SSBOT_FORUM_GLIDE_JUMP_HOLD="))]
flags += ["--env=SSBOT_FORUM_MIDDLE_HANDOFF=1"]
case.update(source=H, source_root=str(S), source_packet_file=str(A / "SOURCE_PACKET_FIXED.json"),
            source_packet_sha256=sha(A / "SOURCE_PACKET_FIXED.json"), source_review_file=str(A / "SOURCE_REVIEW_FINAL.json"),
            entry_file=str(A / "entry_v4.py"), entry_sha256=sha(A / "entry_v4.py"),
            input_binding_file=str(A / "REPLAY_INPUT_BINDING.json"), input_binding_sha256=sha(A / "REPLAY_INPUT_BINDING.json"),
            resource_helper_file=str(A / "engineering_helpers.py"), resource_helper_sha256=sha(A / "engineering_helpers.py"),
            accepted_reviews=sorted(set(case["accepted_reviews"]) | set(range(435, 446))))
windows = [("OPEN", 51162, 51173), ("FLOAT", 51210, 51240)]
for arm, enabled in [("ON", "1"), ("OFF", "0")]:
    contexts = []
    for name, own, last in windows:
        cf = flags + [f"--opus-synth={own + 1}", f"--no-force-from={own}", f"--fixture-recorded-run={trial / 'run'}:{own - 1}",
                      f"--fixture-own-from={own}", "--env=SSBOT_FORUM_GLIDE_JUMP_HOLD=" + enabled]
        contexts.append(dict(name=name, trial=str(trial), **{"from": own}, last=last, flags=cf))
    put(A / f"CASE_{arm}.json", dict(case, case_id="glide_jump_hold445_" + arm.lower(), contexts=contexts))
put(A / "P_PLAN.json", dict(at=now(), source=H, source_review_accepted=True, adapter="unchanged reviewed entry_v4",
    per_arm_frames=sum(z - f + 1 for _, f, z in windows), windows=[dict(name=n, episode=9, own_and_measure_from=f, synthetic_from=f + 1, last=z) for n, f, z in windows],
    profile="MH434 AS1/LANDING_EXIT1/MH1; only GJH ON/OFF; old NO_NEW_GLIDE0", performance_budget_pass=False, game_authorized=False,
    scope="Finite whole-policy/tick and actual-key sanity/cost on affected branches, not global scheduling or prevented-HP proof"))
helper = runpy.run_path(str(A / "engineering_helpers.py"))
resource = helper["resource_guard"]()
put(A / "RESOURCE_INITIAL.json", resource)

s.update(at=now(), phase="GLIDE445_SOURCE_ACCEPTED_FINITE_P_PREPARED", current_source=H, candidate_source=H,
         source_review_pending=False, last_scanned_opus=445, opus445_receipt=str(R / "REVIEW445.json"), pending_opus=None,
         next_phase="Sol zero-tick check/finalize then finite two-window GJH ON/OFF measure/finalize; no game authority.",
         active_implementation=dict(owner="Sol", scope="Reviewed source and affected finite P", stage="P prepared, not started", formal_delivery_pending=False, coordination_seq=380))
put(B / "sol/STATUS.json", s)
p = B / "sol/TO_OPUS.md"
text = p.read_text(encoding="utf-8-sig")
heading = "## #445源审核收：d6a36644归Sol有限P，期间只读收信（信息，无新任务/不唤醒）"
if heading not in text:
    h = "# Sol → Opus 留言队列\n"
    assert text.startswith(h)
    notice = "\n" + heading + "\n\nSol+同阶段Astra窄源复核无新增P0-P2；3文件提交/WT/冻结规范化hash已绑定，11新增/170影响测试只核不重跑。原完整单拍ONOFF选行/J释放证据有限接受，escape unsafe与模型/原截止/记忆差异保留，不认证收益。默认GJH0/旧禁伞0保持。\n\n下一步归Sol，source_fixed445和未改entry_v4已备，ep9新开伞/已开伞两个受影响窗共每臂43拍，先零拍check/finalize再measure/finalize；OWN以后不强制，模型B+1，只切GJH，MH1同数据。请暂停本包改源/重计算，P期间仅读信；不另派工/不发wake，不游戏、不重开停止批/AA/原件。重要真实阻挡照原通信给Sol。\n\n---\n\n"
    p.write_text(h + notice + text[len(h):].lstrip("\r\n"), encoding="utf-8")
put(A / "PREPARATION.json", dict(at=now(), source=H, source_files=len(packet["raw_runtime_files_sha256"]), input_files=len(inputs),
    per_arm_frames=43, resource_blockers=resource["blockers"], formal_P_not_started=True, no_game=True))
print(json.dumps(dict(source=H, source_accepted=True, runtime_files=len(packet["raw_runtime_files_sha256"]), input_files=len(inputs),
    per_arm_frames=43, resource_blockers=resource["blockers"], formal_P_not_started=True, no_game=True), ensure_ascii=False))
