"""Prepare a fresh50 candidate without a game, user authorization or launch claim."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
B = Path("C:/ssbot/data/m2_play/clapper_plan")
ROOT = Path("C:/modeling/silksong_bot")
OLD = B / "analysis/w13_50_middle_handoff434_20261114"
G = B / "analysis/w13_50_glide_hold445_20261115"
D = B / "sol/demos" / G.name
A = B / "analysis/glide_jump_hold445_20261115"
H = "d6a3664416ef84280b214115dc80f2b256782b32"
OLDH = "8e34fb6c71a3338b7652c741b12c5048086c6ae9"
now = lambda: datetime.now(timezone.utc).isoformat()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def put(p, data):
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rewrite(text):
    for old, new in [(OLD.name, G.name), ("MIDDLE_HANDOFF434_W13_HP2_CONTINUOUS", "GLIDE_HOLD445_W13_HP2_CONTINUOUS"),
                     ("middle_handoff434_20261114", "glide_jump_hold445_20261115"), ("source_fixed434", "source_fixed445"),
                     (OLDH, H), (OLDH[:8], H[:8])]:
        text = text.replace(old, new)
    return text


def obj(data):
    return json.loads(rewrite(json.dumps(data, ensure_ascii=False)))


assert not G.exists() and not D.exists()
assert read(A / "ROOT_P_AUDIT.json")["finite_measurement_valid"]
assert read(A / "ROOT_CLEANUP.json")["actual_cleanup_verified"]
assert read(A / "SOURCE_REVIEW_AND_P_FINAL.json")["source"] == H
s = read(B / "sol/STATUS.json")
assert not s["live_or_budget_running"] and not s.get("own_offline_jobs") and not s.get("own_live_session")
assert not (B / "sol/performance/ACTIVE.json").exists()
G.mkdir()
packet = read(A / "SOURCE_PACKET_FIXED.json")
S = Path(packet["source_root"])
assert all(sha(S / n) == h for n, h in {**packet["raw_runtime_files_sha256"], **packet["support_sha256"]}.items())
for p in OLD.glob("*.py"):
    t = rewrite(p.read_text(encoding="utf-8-sig"))
    if p.name == "finish_preparation.py":
        assert t.count("range(405,436)") == 1
        t = t.replace("range(405,436)", "range(405,446)")
        begin = t.index("formal_coverage_note='")
        end = t.index("')", begin)
        t = t[:begin] + "formal_coverage_note='Source-reviewed GJH lifecycle fix; unchanged entry_v4, same-source ON/OFF two affected windows43 frames per arm. Actual replay wire and cleanup verified, not full budget/scheduling or live benefit. Prior continuous lifecycle reused.'" + t[end + 1:]
    elif p.name == "trial.py":
        needle = ' assert e.get("SSBOT_FORUM_MIDDLE_HANDOFF")=="1","this authorized batch enables the reviewed normal-middle handoff"'
        assert needle in t
        t = t.replace(needle, needle + '\n assert e.get("SSBOT_FORUM_GLIDE_JUMP_HOLD")=="1","this batch enables the reviewed glide jump-hold lifecycle fix"')
    elif p.name == "release.py":
        needle = " assert ip['passed']"
        assert t.count(needle) == 1
        t = t.replace(needle, " assert worker.environ().get('SSBOT_FORUM_GLIDE_JUMP_HOLD')=='1','new worker environment does not bind GJH1'\n" + needle)
    ast.parse(t)
    (G / p.name).write_text(t, encoding="utf-8")
for n in ["RESOURCE_BACKGROUND_APPROVAL.json", "RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json"]:
    shutil.copy2(OLD / n, G / n)
reuse = obj(read(OLD / "RUNTIME354_REUSE.json"))
reuse.update(at=now(), source=H)
assert all(sha(S / n) == h for n, h in reuse["lifecycle_files_unchanged"].items())
assert sha(reuse["prior_real_probe"]) == reuse["prior_real_probe_sha256"]
put(G / "RUNTIME354_REUSE.json", reuse)
plan = obj(read(OLD / "CONTINUOUS_PLAN.json"))
plan.update(at=now(), source=H, comparison_baseline_source=OLDH, authorization=None, authorized=False,
            notes="Pending one fresh50; same50 seeds/order and MH1/AS1/LANDING_EXIT1 profile as latest MH50, only GJH1 added. No game or startup until a new explicit user reply. No old batch reopened.")
assert plan["seeds"] == read(OLD / "CONTINUOUS_PLAN.json")["seeds"] and len(plan["seeds"]) == 50
put(G / "CONTINUOUS_PLAN.json", plan)
draft = obj(read(OLD / "TRIAL_CONFIG_DRAFT.json"))
draft.update(at=now(), source=H, user_authorized=False, authorization=None, purpose="Glide jump-hold lifecycle correction, fresh same50 comparison",
             user_ready_required=False, combat_requires_new_ready=False, combat_start_authorization="explicit_user_chat_unattended_new50")
draft["environment"]["SSBOT_FORUM_GLIDE_JUMP_HOLD"] = "1"
assert draft["environment"]["SSBOT_FORUM_SLAM_NO_NEW_GLIDE"] == "0"
put(G / "TRIAL_CONFIG_DRAFT.json", draft)
candidate = obj(read(OLD / "CANDIDATE_SPEC.json"))
candidate.update(at=now(), source=H)
put(G / "CANDIDATE_SPEC.json", candidate)
validation = obj(read(OLD / "VALIDATION_PLAN.json"))
validation.update(at=now(), user_authorized=False, next_candidate=G.name,
                  scope="Pending fresh50, actual startup>=30fps gate. Full postkill-tail protection/HP audits; no model-based damage benefit claim.")
put(G / "VALIDATION_PLAN.json", validation)
checks = obj(read(OLD / "START_GATE_CHECKS.json"))
assert sha(G / "user_authorization.py") == checks["unchanged_user_authorization_sha256"]
assert sha(G / "start_gate.py") == checks["unchanged_start_gate_sha256"]
checks.update(at=now(), scope="Same authorization/ready predicates, metadata source/path changed. New actual worker/input/capture/resource/FPS and GJH environment gates still required after real reply.")
put(G / "START_GATE_CHECKS.json", checks)
lc = obj(read(OLD / "LIFECYCLE_REVIEW.json"))
lc.update(at=now(), accepted=True, files={p.name: sha(p) for p in G.glob("*.py")}, previous_review=str(OLD / "LIFECYCLE_REVIEW.json"),
          changes="Same continuous lifecycle and strict stop/cleanup; new source/path/coverage metadata, GJH1 configuration assertion and actual new-worker environment assertion. No user authorization created; no process launched.")
put(G / "LIFECYCLE_REVIEW.json", lc)
template = obj(read(OLD / "USER_NEW50_AUTHORIZATION.json"))
template.update(at=now(), kind="PENDING_NOT_AUTHORIZED", source=H, batch_id=G.name, user_text=None, question_item_id=None,
                provenance=None, started=False, glide_jump_hold_enabled_for_this_batch=True)
put(G / "AUTHORIZATION_TEMPLATE_NOT_VALID.json", template)
put(G / "BATCH_SPEC.json", dict(at=now(), batch=G.name, source=H, planned_bouts=50, state="PENDING_NEW_USER_AUTHORIZATION",
    ready=False, authorized=False, started=False, same_game=True, recording=True, hp2_continue=True, runtime_fault_stops=True,
    minimum_launch_fps=30, temporary_awake_request_proposed=True, physical_TV_current_state_not_assumed=True,
    only_new_feature="SSBOT_FORUM_GLIDE_JUMP_HOLD=1", same_other_flags_as=OLD.name, prior_paused_batch_reopened=False))
for src, dst in [("launch_middle434.ps1", "launch_glide445.ps1"), ("start_display_middle434.ps1", "start_display_glide445.ps1"),
                 ("watch_middle434_loop.py", "watch_glide445_loop.py")]:
    t = rewrite((ROOT / "tmp" / src).read_text(encoding="utf-8-sig")).replace("watch_middle434_loop.py", "watch_glide445_loop.py")
    if dst.endswith(".py"):
        ast.parse(t)
    (ROOT / "tmp" / dst).write_text(t, encoding="utf-8")
proposal = dict(at=now(), source=H, batch=G.name, prepared_without_authorization=True, authorized=False, game_started=False,
    planned_bouts=50, source_and_P=str(A / "SOURCE_REVIEW_AND_P_FINAL.json"), P=str(A / "ROOT_P_AUDIT.json"),
    baseline=OLD.name, only_new_feature="GJH1", same_seeds=True, same_game=True, recording=True, hp2_continue=True, fault_stops=True,
    startup_fps_required=30, full_scheduling_gate_pass=False, performance_budget_pass=False,
    pending="New current-chat explicit user authorization, then bind receipt and finish_preparation before launch",
    launch_wrapper=str(ROOT / "tmp/launch_then_release.ps1"), launch_script=str(ROOT / "tmp/launch_glide445.ps1"),
    launch_release_wrapper_sha256=sha(ROOT / "tmp/launch_then_release.ps1"))
put(A / "NEW50_PROPOSAL.json", proposal)
assert not D.exists() and not (G / "USER_NEW50_AUTHORIZATION.json").exists() and not (G / "LAUNCH_CLAIM.json").exists()
put(G / "PREAUTH_STAGING.json", dict(proposal, source_files=len(packet["raw_runtime_files_sha256"]),
    lifecycle_files=len(lc["files"]), seed_plan_sha256=sha(G / "CONTINUOUS_PLAN.json"),
    draft_sha256=sha(G / "TRIAL_CONFIG_DRAFT.json"), strict_authorization_guards_not_changed=True,
    actual_prepare_and_source_hashes_pending_reply=True))
print(json.dumps(dict(batch=G.name, source=H, staged=True, authorized=False, game_started=False, same50_seeds=True,
                     lifecycle_scripts=len(lc["files"]), source_files=len(packet["raw_runtime_files_sha256"])), ensure_ascii=False))
