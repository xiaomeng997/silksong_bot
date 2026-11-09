"""Task 182 seq 306: under episode-remaining-2hp-v1 a non-fatal HP record goes to a journal opened before the fight, and into the
ledger once the fighting has stopped. Real persisted budget, real files; the worker through the fake-IPC rig of test_b2_worker_batch."""
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from ssbot.combat import knife_chain_budget as K
from ssbot.combat.knife_chain_budget import LearningBudget, LearningStop, LOW_HP_POLICY, OBSERVE_POLICY, STRICT_POLICY, audit_events
from ssbot.tools import combat_run as C
from tests.test_b2_worker_batch import Rig


def low(path, worker="i0", revision="r"):
    return LearningBudget(path, batch="new", revision=revision, worker=worker, policy=LOW_HP_POLICY)


@pytest.fixture
def b(tmp_path):
    x = low(tmp_path / "budget.json")
    x.bind_execution({"real_quit": 1.})
    x.begin_attempt(episode=0, arm="B", seed=1)
    yield x
    if x._journal_fd is not None:
        os.close(x._journal_fd)
        x._journal_fd = None


def hit(b, frame=10, hp=2, **kw):
    return b.observe(episode=0, frame=frame, arm="B", hp_loss=hp, **{"chain_related": True, **kw})


def on_disk(b):
    return json.loads(b.path.read_text(encoding="utf-8"))


def lines(b):
    return b._journal_path.read_bytes().decode("utf-8").splitlines()


def no_sync_io(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no create / rename / fsync on the combat tick")
    monkeypatch.setattr(K.os, "fsync", boom)
    monkeypatch.setattr(K.os, "replace", boom)


# ---- the combat tick

def test_a_nonfatal_hp_record_is_one_appended_line_and_no_sync_io(b, monkeypatch):
    before = b.path.read_bytes()
    no_sync_io(monkeypatch)
    hit(b)
    assert b.path.read_bytes() == before and not list(b.path.parent.glob("*.lock")) and not list(b.path.parent.glob("*.tmp.*"))
    assert len(lines(b)) == 2
    assert json.loads(lines(b)[1]) == dict(episode=0, frame=10, arm="B", hp_loss=2, chain_related=True, tail=False, fatal=None, worker="i0",
                                           id="i0:0:10:B:None")


def test_the_run_sees_the_record_at_once(b):
    hit(b, 10)
    hit(b, 20, tail=True)
    assert b.state["b_fight_hp"] == 2 and b.state["tail_hp"] == 2 and len(b.state["events"]) == 2 and b.state["stop"] is None
    assert on_disk(b)["b_fight_hp"] == 0


def test_a_tick_without_a_loss_writes_nothing(b):
    n = len(lines(b))
    b.observe(episode=0, frame=10, arm="B")
    assert len(lines(b)) == n


def test_the_per_tick_check_still_reads_halt_and_stop(b, tmp_path):
    hit(b)
    (tmp_path / "budget.json.halt").write_text("x", encoding="utf-8")
    with pytest.raises(LearningStop, match="halt"):
        b.observe(episode=0, frame=11, arm="B")
    (tmp_path / "budget.json.halt").unlink()
    other = low(tmp_path / "budget.json", worker="i1")
    with pytest.raises(LearningStop):
        other.observe(episode=7, frame=1, arm="B", fatal="elsewhere")
    with pytest.raises(LearningStop, match="elsewhere"):
        hit(b, 12)
    assert lines(b)[-1].startswith('{"arm"') and b._journal_pending
    os.close(other._journal_fd)
    other._journal_fd = None


def test_the_low_hp_quit_is_still_the_supervisors(b):
    hit(b)
    assert b.remaining_hp_quit == 2


# ---- into the ledger

def test_the_merge_gives_the_ledger_the_old_record_shape(b, tmp_path):
    hit(b, 10)
    hit(b, 20, tail=True, chain_related=False)
    assert b.merge_journal() == 2
    d = on_disk(b)
    assert d["b_fight_hp"] == 2 and d["tail_hp"] == 2 and d["stop"] is None
    old = LearningBudget(tmp_path / "strict.json", batch="new", revision="r", worker="i0")
    old.observe(episode=0, frame=10, arm="B", hp_loss=1)
    assert set(d["events"][0]) == set(old.state["events"][0])


def test_merging_twice_or_after_a_crash_does_not_count_twice(b, tmp_path):
    hit(b)
    rows, _ = b._read_journal()
    b._update({"kind": "journal_merge", "events": rows})              # the ledger written; the crash comes before anything else
    assert on_disk(b)["b_fight_hp"] == 2
    assert b.merge_journal() == 1 and b.merge_journal() == 0
    assert on_disk(b)["b_fight_hp"] == 2 and len(on_disk(b)["events"]) == 1
    os.close(b._journal_fd)
    b._journal_fd = None
    again = low(tmp_path / "budget.json")                             # a new process on the same account: nothing left to merge
    assert again._journal_pending == [] and again.merge_journal() == 0 and on_disk(again)["b_fight_hp"] == 2
    os.close(again._journal_fd)
    again._journal_fd = None


def test_a_crash_before_the_merge_leaves_the_records_to_reconcile(b, tmp_path):
    hit(b)
    os.close(b._journal_fd)
    b._journal_fd = None
    again = low(tmp_path / "budget.json")
    assert len(again._journal_pending) == 1 and again.state["b_fight_hp"] == 2 and on_disk(again)["b_fight_hp"] == 0
    assert again.merge_journal() == 1 and on_disk(again)["b_fight_hp"] == 2
    with pytest.raises(LearningStop, match="already reserved"):       # a recovery frees no slot
        again.begin_attempt(episode=0, arm="B", seed=1)
    os.close(again._journal_fd)
    again._journal_fd = None


def test_the_next_reservation_merges_first(b):
    hit(b)
    b.begin_attempt(episode=1, arm="B", seed=2)
    d = on_disk(b)
    assert d["b_fight_hp"] == 2 and len(d["attempts"]) == 2 and b._journal_pending == []


def test_finish_bout_merges(b):
    hit(b)
    assert b.finish_bout(episode=0, arm="B") == 1
    assert on_disk(b)["b_fight_hp"] == 2


def test_close_merges_and_closes(b):
    hit(b)
    b.close_journal()
    assert on_disk(b)["b_fight_hp"] == 2 and b._journal_fd is None
    b.close_journal()


# ---- the stop paths

def test_a_fatal_goes_after_the_journalled_records(b):
    hit(b, 10)
    with pytest.raises(LearningStop, match="send deadline"):
        b.observe(episode=0, frame=11, arm="B", fatal="send deadline")
    d = on_disk(b)
    assert [e["frame"] for e in d["events"]] == [10, 11] and d["b_fight_hp"] == 2 and d["stop"]["reasons"] == ["send deadline"]


def test_a_fatal_with_an_hp_loss_is_synchronous(b, monkeypatch):
    called = []
    real = os.fsync
    monkeypatch.setattr(K.os, "fsync", lambda fd: (called.append(fd), real(fd))[1])
    with pytest.raises(LearningStop, match="death"):
        b.observe(episode=0, frame=11, arm="B", hp_loss=2, fatal="death")
    assert called and on_disk(b)["b_fight_hp"] == 2 and len(lines(b)) == 1


def test_the_records_still_count_when_a_stop_is_already_latched(b):
    hit(b, 10)
    b._update(dict(episode=0, frame=5, arm="B", hp_loss=0, chain_related=False, tail=False, fatal="elsewhere"))
    assert b.merge_journal() == 1
    d = on_disk(b)
    assert d["b_fight_hp"] == 2 and d["stop"]["reasons"] == ["elsewhere"]


def test_a_stopped_batch_stays_stopped_after_a_merge(b):
    hit(b, 10)
    with pytest.raises(LearningStop):
        b.observe(episode=0, frame=11, arm="B", fatal="x")
    with pytest.raises(LearningStop):
        b.begin_attempt(episode=1, arm="B", seed=2)


# ---- failures: stop before another action, nothing lost silently

def test_a_short_write_stops_and_records_the_hp(b, monkeypatch):
    real = os.write
    calls = []

    def short(fd, data):
        calls.append(fd)
        return real(fd, data[:-3]) if fd == b._journal_fd else real(fd, data)
    monkeypatch.setattr(K.os, "write", short)
    with pytest.raises(LearningStop, match="short write"):
        hit(b, 10)
    monkeypatch.undo()
    d = on_disk(b)
    assert d["stop"] is not None and "short write" in d["stop"]["reasons"][0] and d["b_fight_hp"] == 2 and b._journal_pending == []


def test_a_write_error_stops_and_records_the_hp(b, monkeypatch):
    real = os.write

    def fail(fd, data):
        if fd == b._journal_fd:
            raise OSError(28, "no space")
        return real(fd, data)
    monkeypatch.setattr(K.os, "write", fail)
    hit_error = None
    with pytest.raises(LearningStop, match="write failed") as hit_error:
        hit(b, 10)
    monkeypatch.undo()
    assert on_disk(b)["b_fight_hp"] == 2 and "write failed" in on_disk(b)["stop"]["reasons"][0]


def test_a_short_write_after_good_records_keeps_them(b, monkeypatch):
    hit(b, 10)
    real = os.write
    monkeypatch.setattr(K.os, "write", lambda fd, data: real(fd, data[:5]) if fd == b._journal_fd else real(fd, data))
    with pytest.raises(LearningStop, match="short write"):
        hit(b, 20)
    monkeypatch.undo()
    d = on_disk(b)
    assert [e["frame"] for e in d["events"]] == [10, 20] and d["b_fight_hp"] == 4


def test_a_torn_last_line_merges_the_complete_records_then_stops(b):
    hit(b, 10)
    with open(b._journal_path, "ab") as f:
        f.write(b'{"arm":"B","epis')
    raw = b._journal_path.read_bytes()
    with pytest.raises(LearningStop, match="torn"):
        b.merge_journal()
    assert b._journal_path.read_bytes() == raw and on_disk(b)["b_fight_hp"] == 2


@pytest.mark.parametrize("bad", [b'not json\n', b'[1,2]\n', b'{"arm":"B"}\n'], ids=["text", "list", "fields"])
def test_a_damaged_complete_line_stops_and_merges_nothing(b, bad):
    hit(b, 10)
    with open(b._journal_path, "ab") as f:
        f.write(bad)
    with pytest.raises(LearningStop, match="corrupt|invalid"):
        b.merge_journal()
    assert on_disk(b)["b_fight_hp"] == 0 and b._journal_pending


@pytest.mark.parametrize("over", [dict(worker="i9"), dict(id="i0:0:10:B:x"), dict(hp_loss=0), dict(hp_loss=True), dict(arm="C"), dict(fatal="x"),
                                  dict(fatal="x", id="i0:0:11:B:x"), dict(tail=1)],
                         ids=["worker", "id", "zero", "bool_hp", "arm", "fatal", "fatal_with_its_id", "tail"])
def test_a_foreign_or_impossible_record_stops(b, over):
    hit(b, 10)
    row = {**json.loads(lines(b)[1]), "frame": 11, "id": "i0:0:11:B:None", **over}
    with open(b._journal_path, "ab") as f:
        f.write((json.dumps(row) + "\n").encode())
    with pytest.raises(LearningStop, match="invalid"):
        b.merge_journal()


def test_a_lost_record_stops(b):
    hit(b, 10)
    hit(b, 20)
    os.close(b._journal_fd)
    keep = b._journal_path.read_bytes().splitlines(keepends=True)[:-1]
    b._journal_path.write_bytes(b"".join(keep))
    b._journal_fd = os.open(b._journal_path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0))
    with pytest.raises(LearningStop, match="lost a record"):
        b.merge_journal()


def test_a_fatal_with_a_damaged_journal_still_latches(b):
    hit(b, 10)
    with open(b._journal_path, "ab") as f:
        f.write(b"garbage\n")
    with pytest.raises(LearningStop, match="send deadline.*corrupt"):
        b.observe(episode=0, frame=11, arm="B", fatal="send deadline")
    assert on_disk(b)["stop"] is not None


def test_finish_bout_latches_a_stop_when_the_merge_fails(b):
    hit(b, 10)
    with open(b._journal_path, "ab") as f:
        f.write(b"garbage\n")
    assert b.finish_bout(episode=0, arm="B") is None
    with pytest.raises(LearningStop, match="corrupt"):
        b.check()
    with pytest.raises(LearningStop):
        b.begin_attempt(episode=1, arm="B", seed=2)


def test_a_missing_journal_is_not_made_anew_for_an_opened_account(b, tmp_path):
    os.close(b._journal_fd)
    b._journal_fd = None
    b._journal_path.unlink()
    with pytest.raises(LearningStop, match="missing for an opened account"):
        low(tmp_path / "budget.json")
    assert not b._journal_path.exists()


@pytest.mark.parametrize("tail,msg", [(b'{"arm":"B"', "torn"), (b"garbage\n", "corrupt")], ids=["torn", "corrupt"])
def test_a_damaged_journal_is_refused_when_opening(b, tmp_path, tail, msg):
    hit(b, 10)
    os.close(b._journal_fd)
    b._journal_fd = None
    with open(b._journal_path, "ab") as f:
        f.write(tail)
    raw = b._journal_path.read_bytes()
    with pytest.raises(LearningStop, match=msg):
        low(tmp_path / "budget.json")
    assert b._journal_path.read_bytes() == raw


def test_the_journal_is_bound_to_batch_revision_worker(b, tmp_path):
    h = json.loads(lines(b)[0])
    assert h == dict(schema=1, kind="event_journal", batch="new", revision="r", worker="i0", policy=LOW_HP_POLICY)
    os.close(b._journal_fd)
    b._journal_fd = None
    wrong = {**h, "revision": "other"}
    b._journal_path.write_bytes((json.dumps(wrong) + "\n").encode())
    with pytest.raises(LearningStop, match="header differs"):
        low(tmp_path / "budget.json")


def test_each_worker_has_its_own_file(tmp_path):
    a, c = low(tmp_path / "budget.json", worker=r"C:\run\decisions_i0.chain.jsonl"), low(tmp_path / "budget.json", worker=r"C:\run\decisions_i1.chain.jsonl")
    assert a._journal_path != c._journal_path and ":" not in a._journal_path.name
    a.observe(episode=0, frame=1, arm="B", hp_loss=2)
    c.observe(episode=0, frame=1, arm="B", hp_loss=2)
    assert a.merge_journal() == 1 and c.merge_journal() == 1
    d = on_disk(a)
    assert d["b_fight_hp"] == 4 and len(d["events"]) == 2
    a.close_journal(); c.close_journal()


# ---- the production chain path

def test_the_chain_records_an_hp_loss_on_the_fast_path_and_stops_through_the_ledger(tmp_path, monkeypatch):
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    from tests.test_knife_chain_b2 import raw, runner
    budget = low(tmp_path / "ledger.json", worker="w")
    n = NativeChainB2(runner_factory=runner, probe_ref="journal306", budget=budget)
    n.reset(0, start_frame=1000)
    s0 = raw(1000)
    n.observe_learning(s0)
    s = raw(1001)
    s["hero"]["health"] = s0["hero"]["health"] - 2
    no_sync_io(monkeypatch)
    n.observe_learning(s)
    monkeypatch.undo()
    assert n.learning_stop is None and budget.state["b_fight_hp"] == 2 and budget.remaining_hp_quit == 2
    assert on_disk(budget)["b_fight_hp"] == 0
    with pytest.raises(LearningStop, match="send deadline"):
        n._stop("send deadline beyond four frames", 1002)
    d = on_disk(budget)
    assert d["b_fight_hp"] == 2 and [e["frame"] for e in d["events"]] == [1001, 1002] and d["stop"] is not None
    budget.close_journal()


def test_the_chain_stops_when_the_record_cannot_be_kept(tmp_path, monkeypatch):
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    from tests.test_knife_chain_b2 import raw, runner
    budget = low(tmp_path / "ledger.json", worker="w")
    n = NativeChainB2(runner_factory=runner, probe_ref="journal306", budget=budget)
    n.reset(0, start_frame=1000)
    s0 = raw(1000)
    n.observe_learning(s0)
    s = raw(1001)
    s["hero"]["health"] = s0["hero"]["health"] - 2
    real = os.write
    monkeypatch.setattr(K.os, "write", lambda fd, data: real(fd, data[:4]) if fd == budget._journal_fd else real(fd, data))
    with pytest.raises(LearningStop, match="short write"):
        n.observe_learning(s)
    monkeypatch.undo()
    assert n.learning_stop and "short write" in n.learning_stop and on_disk(budget)["b_fight_hp"] == 2
    budget.close_journal()


# ---- what stays as it was

def test_strict_policy_is_synchronous_and_has_no_journal(tmp_path):
    x = LearningBudget(tmp_path / "budget.json", batch="new", revision="r", worker="i0")
    assert x.policy == STRICT_POLICY and x._journal_path is None
    with pytest.raises(LearningStop, match="cumulative 2 HP"):
        x.observe(episode=0, frame=1, arm="B", hp_loss=2, chain_related=True)
    assert on_disk(x)["b_fight_hp"] == 2 and on_disk(x)["stop"] is not None
    assert not list(tmp_path.glob("*.events.*"))
    assert x.merge_journal() == 0 and x.finish_bout(episode=0, arm="B") == 0
    x.close_journal()


def test_observe_policy_is_synchronous_and_has_no_journal(tmp_path):
    x = LearningBudget(tmp_path / "budget.json", batch="new", revision="r", worker="i0", policy=OBSERVE_POLICY)
    x.observe(episode=0, frame=1, arm="B", hp_loss=2)
    assert on_disk(x)["b_fight_hp"] == 2 and not list(tmp_path.glob("*.events.*"))


def test_the_attempt_slot_is_still_atomic_and_no_retry(b):
    with pytest.raises(LearningStop, match="already reserved"):
        b.begin_attempt(episode=0, arm="B", seed=1)
    assert len(on_disk(b)["attempts"]) == 1


# ---- the audit's reading

def test_the_audit_sees_journalled_records_after_a_crash(b):
    hit(b, 10)
    hit(b, 20, tail=True)
    v = audit_events(b.path)
    assert [e["frame"] for e in v["unmerged"]] == [10, 20] and v["b_fight_hp"] == 2 and v["tail_hp"] == 2 and not v["torn"] and not v["corrupt"]
    assert on_disk(b)["b_fight_hp"] == 0


def test_the_audit_after_a_merge_has_nothing_unmerged_and_no_double(b):
    hit(b, 10)
    b.merge_journal()
    v = audit_events(b.path)
    assert v["unmerged"] == [] and v["b_fight_hp"] == 2 and len(v["events"]) == 1


def test_the_audit_names_a_torn_or_corrupt_journal(b):
    hit(b, 10)
    with open(b._journal_path, "ab") as f:
        f.write(b'{"arm"')
    v = audit_events(b.path)
    assert v["torn"] == [b._journal_path.name] and v["b_fight_hp"] == 2 and v["clean"] is False
    with open(b._journal_path, "ab") as f:
        f.write(b'\n')
    v = audit_events(b.path)
    assert [x["file"] for x in v["corrupt"]] == [b._journal_path.name] and v["b_fight_hp"] == 0 and v["clean"] is False


def test_the_audit_is_clean_when_every_journal_reads(b):
    hit(b, 10)
    assert audit_events(b.path)["clean"] is True
    b.merge_journal()
    assert audit_events(b.path)["clean"] is True


def test_a_repeated_id_in_one_journal_counts_once_in_the_audit_and_the_merge(b):
    hit(b, 10)
    with open(b._journal_path, "ab") as f:
        f.write((lines(b)[1] + "\n").encode())
    v = audit_events(b.path)
    assert v["b_fight_hp"] == 2 and len(v["unmerged"]) == 1 and v["clean"] is True
    b.merge_journal()
    assert on_disk(b)["b_fight_hp"] == 2 and len(on_disk(b)["events"]) == 1
    assert audit_events(b.path)["b_fight_hp"] == 2


def test_a_record_the_ledger_has_counts_once_in_the_audit(b):
    hit(b, 10)
    b.merge_journal()
    hit(b, 20)
    v = audit_events(b.path)
    assert v["b_fight_hp"] == 4 and [e["frame"] for e in v["unmerged"]] == [20]


@pytest.mark.parametrize("over,why", [(dict(batch="unrelated-batch"), "header"), (dict(revision="other"), "header"), (dict(policy=STRICT_POLICY), "header"),
                                      (dict(schema=2), "header"), (dict(kind="other"), "header"), (dict(worker="i9"), "file name")],
                         ids=["batch", "revision", "policy", "schema", "kind", "worker"])
def test_the_audit_does_not_count_a_foreign_journal(b, over, why):
    hit(b, 10)
    os.close(b._journal_fd)
    b._journal_fd = None
    rows = lines(b)
    rows[0] = json.dumps({**json.loads(rows[0]), **over})
    b._journal_path.write_bytes(("\n".join(rows) + "\n").encode())
    v = audit_events(b.path)
    assert v["b_fight_hp"] == 0 and v["unmerged"] == [] and v["clean"] is False
    assert [x["file"] for x in v["corrupt"]] == [b._journal_path.name] and why in v["corrupt"][0]["reason"]


@pytest.mark.parametrize("over", [dict(hp_loss=True), dict(arm="C"), dict(fatal="x"), dict(worker="i9"), dict(id="other"), dict(extra=1)],
                         ids=["bool_hp", "arm", "fatal", "worker", "id", "extra_field"])
def test_the_audit_does_not_count_a_journal_with_a_malformed_record(b, over):
    hit(b, 10)
    row = {**json.loads(lines(b)[1]), "frame": 11, "id": "i0:0:11:B:None", **over}
    with open(b._journal_path, "ab") as f:
        f.write((json.dumps(row) + "\n").encode())
    v = audit_events(b.path)
    assert v["b_fight_hp"] == 0 and v["clean"] is False and "invalid" in v["corrupt"][0]["reason"]


def test_a_stray_file_with_the_journal_suffix_is_not_counted(b, tmp_path):
    hit(b, 10)
    (tmp_path / "budget.json.events.notatag").write_bytes(b'{"worker":"i0"}\n')
    v = audit_events(b.path)
    assert v["b_fight_hp"] == 2 and v["clean"] is False and [x["file"] for x in v["corrupt"]] == ["budget.json.events.notatag"]


# ---- the worker: every bout end, the last one, an exception

def low_rig(tmp_path, monkeypatch, n=3, hits=(), boom=None):
    """The fake-IPC worker on a real low-HP ledger; hits[i] = the HP records of bout i."""
    import ssbot.train.episode as episode
    from tests.test_b2_continuous_plan import write_plan
    rig = Rig(tmp_path, monkeypatch)
    plan = write_plan(tmp_path / "plan.json", n)
    real_init = LearningBudget.__init__

    def init(self, path, *, batch, revision, worker, policy=STRICT_POLICY):
        real_init(self, path, batch=batch, revision=revision, worker=worker, policy=LOW_HP_POLICY)
    monkeypatch.setattr(LearningBudget, "__init__", init)
    disk_at_start = []

    def run_episode(link, enc, tap, pol, cfg, rec):
        i = rig.attempts
        rig.attempts += 1
        pol.episode += 1
        disk_at_start.append(json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))["b_fight_hp"])
        for f in (hits[i] if i < len(hits) else ()):
            pol.chain_native.budget.observe(episode=i, frame=f, arm="B", hp_loss=2)
        rec.outcome = "CLEAR"
        rec.ingame_s = 1.
        if boom == i:
            raise RuntimeError("the bout broke")
    monkeypatch.setattr(episode, "run_episode", run_episode)
    return rig, dict(episodes=n, continuous_plan=str(tmp_path / "plan.json")), disk_at_start


def test_every_bout_is_in_the_ledger_before_the_next_starts_and_the_last_too(tmp_path, monkeypatch):
    rig, kw, disk = low_rig(tmp_path, monkeypatch, hits=[(10, 20), (30,), (40,)])
    assert rig.run(**kw) == 0
    assert disk == [0, 4, 6]
    d = json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))
    assert d["b_fight_hp"] == 8 and [e["frame"] for e in d["events"]] == [10, 20, 30, 40]
    assert audit_events(tmp_path / "budget.json")["unmerged"] == []
    assert rig.receipts()[0]["resources"]["b2_event_journal"] == "pass"


def test_an_exception_in_a_bout_still_merges_at_the_workers_close(tmp_path, monkeypatch):
    rig, kw, disk = low_rig(tmp_path, monkeypatch, hits=[(10,)], boom=0)
    with pytest.raises(BaseException):
        rig.run(**kw)
    d = json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))
    assert d["b_fight_hp"] == 2
    assert rig.receipts()[0]["resources"]["b2_event_journal"] == "pass"
    assert (tmp_path / "budget.json.halt").exists()


def test_a_journal_that_cannot_merge_stops_the_batch_at_the_bout_end(tmp_path, monkeypatch):
    import ssbot.train.episode as episode
    rig, kw, disk = low_rig(tmp_path, monkeypatch, hits=[(10,)])
    inner = episode.run_episode

    def damaged(link, enc, tap, pol, cfg, rec):
        inner(link, enc, tap, pol, cfg, rec)
        with open(pol.chain_native.budget._journal_path, "ab") as f:
            f.write(b"garbage\n")
    monkeypatch.setattr(episode, "run_episode", damaged)
    with pytest.raises(LearningStop, match="corrupt"):
        rig.run(**kw)
    assert rig.attempts == 1 and (tmp_path / "budget.json.halt").exists()
    row = json.loads((tmp_path / "attempts_i0.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "corrupt" in row["b2_learning_stop"]
