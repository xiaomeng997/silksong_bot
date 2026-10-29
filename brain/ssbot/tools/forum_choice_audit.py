"""Observe the real h2 selector and ACTION sender on development recordings.

This tool never re-ranks candidates or changes controller source. Its process-local
hooks are for offline, deterministic-clock replay only; timings are not live tick
latency evidence. Rows after the first output divergence remain counterfactual.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import hashlib
import json
import math
import os
import sys
import zlib
from pathlib import Path


def freeze(value):
    """Copy audit values without retaining planner arrays or emitting JSON NaN."""
    import numpy as np
    if isinstance(value, np.ndarray):
        a = np.ascontiguousarray(value)
        if a.dtype.hasobject:
            return freeze(a.tolist())
        return {"array": "zlib-base64", "dtype": a.dtype.str, "shape": list(a.shape),
                "data": base64.b64encode(zlib.compress(a.tobytes(), 1)).decode("ascii")}
    if isinstance(value, np.generic):
        return freeze(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return {"float": str(value)}
    if isinstance(value, dict):
        return {str(k): freeze(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [freeze(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported audit value: {type(value).__name__}")


def thaw(value):
    """Decode arrays for independent audits. Array buffers are owned by the result."""
    import numpy as np
    if isinstance(value, dict) and value.get("array") == "zlib-base64":
        dtype = np.dtype(value["dtype"])
        if dtype.hasobject:
            raise ValueError("object arrays are not permitted")
        raw = zlib.decompress(base64.b64decode(value["data"], validate=True))
        shape = tuple(int(x) for x in value["shape"])
        if any(x < 0 for x in shape) or math.prod(shape) * dtype.itemsize != len(raw):
            raise ValueError("array shape/byte count mismatch")
        return np.frombuffer(raw, dtype=dtype).reshape(shape).copy()
    if isinstance(value, dict):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, list):
        return [thaw(v) for v in value]
    return value


def key_names(loc, count):
    """Label the keys actually passed to lexsort; no score or order is recomputed."""
    names = ["-J", "eml", "-t_hit", "-t_c", "Pf", "Pcm", "fs_face", "Pc", "sk_c",
             "-sk_f", "sk_n", "fs_bad", "~V", "v2_ff"]
    # rune_bombs is a module global, so the caller supplies the branch explicitly.
    if loc.get("_audit_noglide"):
        names.append("noglide")
    names += [f"ground_first[{i}]" for i in range(len(loc["gf_"]))]
    names += ["v2_nh", "off_lattice_or_rune_tier"]
    names += [f"window_rank[{i}]" for i in range(len(loc["wk_"]))]
    nd = []
    if loc["v2"] and (getattr(loc["prefs"], "no_dash", None) or ()):
        nd.append("no_dash")
    if loc["v2"] and loc["npg_"] and len(loc["sc"].get("targets") or ()):
        nd.append("no_pogo")
    if loc["v2"] and loc["rx_"]:
        nd.append("rune_exit")
    if len(nd) != len(loc["nd_"]):
        raise ValueError("unknown preference key schema")
    names += nd
    names += [f"kept_or_hold[{i}]" for i in range(len(loc["kk_"]))]
    names += ["~mkeep", "~keep", "clash_p", "S", "U", "hz_soft", "hz"]
    if len(names) != count:
        raise ValueError(f"selector key schema changed: {len(names)} labels / {count} keys")
    return names


class ChoiceAudit:
    """Scoped hooks. Capture rank inputs at the call, final choices at return."""
    def __init__(self, stream):
        self.stream = stream
        self.active = False
        self.current = None
        self.calls = []
        self.call_id = 0
        self.rows = 0
        self.ranked = 0
        self.body_calls = 0
        self.knife_rows = 0
        self.knife_chosen = 0
        self.knife_unsafe = 0
        self.errors = []
        self.restore = []

    def patch(self, obj, name, replacement):
        self.restore.append((obj, name, getattr(obj, name)))
        setattr(obj, name, replacement)

    def install(self):
        import numpy as np
        from ssbot.combat.forum_planner import ForumPlanner
        from ssbot.combat import forum_planner as planner_module
        from ssbot.combat.terminal import EnemyFields
        from ssbot.train import episode
        original_tick = ForumPlanner.tick
        original_sort = np.lexsort
        original_body = EnemyFields.from_bodies
        original_act = episode._act
        audit = self

        def lexsort(keys, *args, **kwargs):
            order = original_sort(keys, *args, **kwargs)
            frame = sys._getframe(1)
            loc = frame.f_locals
            if (audit.current is not None and frame.f_code is original_tick.__code__
                    and "wk_" in loc and len(keys) >= 7
                    and keys[-1] is loc.get("hz") and keys[-2] is loc.get("hz_soft")):
                try:
                    labels = dict(loc)
                    labels["_audit_noglide"] = bool(loc["v2"] and planner_module.rune_bombs.NOGLIDE)
                    audit.current["rank"] = {"keys_low_to_high": key_names(labels, len(keys)),
                        "keys": freeze(tuple(keys)), "unfiltered_order": freeze(order)}
                    audit.current["_frame"] = frame
                except Exception as exc:
                    audit.current["rank_error"] = f"{type(exc).__name__}: {exc}"
            return order

        def body(cls, f, *args, **kwargs):
            result = original_body(f, *args, **kwargs)
            if audit.current is not None:
                audit.current["_fields"].append((f, result))
            return result

        def tick(planner, *args, **kwargs):
            if not audit.active:
                return original_tick(planner, *args, **kwargs)
            audit.call_id += 1
            packet = {"call_id": audit.call_id, "_fields": []}
            audit.current = packet
            try:
                result = original_tick(planner, *args, **kwargs)
            finally:
                audit.current = None
            frame = packet.pop("_frame", None)
            if frame is not None:
                loc = frame.f_locals
                packet["rank"]["filtered_order"] = freeze(loc["order"])
                packet["selection"] = freeze(planner.last_sel)
                packet["after_escape_row"] = freeze(loc.get("esc_row"))
                packet["tail_ok"] = freeze(loc.get("tail_ok"))
                audit.ranked += 1
            else:
                packet["selection"] = None
                packet["branch"] = result.name
            fields = []
            for forecast, f in packet.pop("_fields"):
                fields.append({"keys": freeze(f.keys), "bins": f.nbins,
                    "closed_fraction_by_bin": freeze(f.Cl.mean(axis=(1, 2)) if f.Cl.size else []),
                    "saturated_fraction_by_bin": freeze((f.Vf >= 1).mean(axis=(1, 2)) if f.Vf.size else []),
                    "hero_half": freeze(forecast._fc.half),
                    "body_inputs": [{"iid": t.iid, "body": freeze(t.body), "vel": freeze(t.vel),
                                     "seen_T": t.seen_T} for t in forecast._fc.trackers.values()
                                    if t.in_play and not t.dead and not t.hidden and t.body is not None]})
            packet["fields"] = fields
            audit.body_calls += len(fields)
            packet["planner_result"] = {"idx": result.idx, "name": result.name, "mask": result.mask,
                                         "S": result.S, "forced_risk": result.forced_risk}
            packet["last_info"] = freeze(planner.last_info)
            knife = planner.last_info.get("knife", {})
            audit.knife_rows += int(knife.get("rows", 0))
            audit.knife_chosen += int(knife.get("chosen_row") is not None)
            audit.knife_unsafe += int(knife.get("chosen_row") is not None and result.S != 0)
            if "rank_error" in packet:
                audit.errors.append(packet["rank_error"])
            audit.calls.append(packet)
            return result

        def act(link, last, policy, state, tap):
            audit.calls = []
            audit.active = True
            try:
                result = original_act(link, last, policy, state, tap)
            finally:
                audit.active = False
                audit.current = None
            audit.rows += 1
            row = {"frame": last, "target_frame": last + 2,
                   "state": freeze(state), "planner_calls": audit.calls,
                   "policy_choice": freeze(getattr(policy, "measurement_choice", None)),
                   "sent_wire": link.sock.messages[-1].hex()}
            audit.stream.write(json.dumps(freeze(row), allow_nan=False, separators=(",", ":")) + "\n")
            audit.calls = []
            return result

        self.patch(np, "lexsort", lexsort)
        self.patch(ForumPlanner, "tick", tick)
        self.restore.append((EnemyFields, "from_bodies", EnemyFields.__dict__["from_bodies"]))
        EnemyFields.from_bodies = classmethod(body)
        self.patch(episode, "_act", act)

    def close(self):
        for obj, name, original in reversed(self.restore):
            setattr(obj, name, original)
        self.restore.clear()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--code-root", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--ticks", type=int, default=800)
    ap.add_argument("--tv", choices=("0", "1"), required=True)
    ap.add_argument("--knife", choices=("0", "1"), default="0")
    ap.add_argument("--reference", type=Path, help="matching unaudited replay output for identity validation")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--e-cores-idle", action="store_true", help="limit this process before importing / warming")
    a = ap.parse_args(argv)
    if a.knife == "1" and a.tv != "0":
        ap.error("knife audit requires TV off")
    if a.e_cores_idle:
        import psutil
        proc = psutil.Process()
        proc.cpu_affinity(list(range(16, 32)))
        proc.nice(psutil.IDLE_PRIORITY_CLASS)
        if proc.cpu_affinity() != list(range(16, 32)) or proc.nice() != psutil.IDLE_PRIORITY_CLASS:
            raise RuntimeError("offline resource isolation did not take effect")
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    # The environment callback installs hooks before replay.main sets this.
    # Numba must see the frozen pool size before any control module is imported.
    os.environ["NUMBA_NUM_THREADS"] = "4"
    sys.path.insert(0, str(a.code_root / "brain"))
    from ssbot.tools import forum_measure_replay as replay
    a.out.parent.mkdir(parents=True, exist_ok=True)
    replay_path = a.out.with_suffix(".replay.json")
    choices_path = a.out.with_suffix(".choices.jsonl")
    if any(p.exists() for p in (a.out, replay_path, choices_path)):
        raise FileExistsError("audit outputs already exist; use a fresh destination")
    environment = replay.h2_environment
    with choices_path.open("x", encoding="utf-8") as stream:
        audit = ChoiceAudit(stream)
        def arm(raw):
            env = environment(raw)
            env["SSBOT_FORUM_TV"] = a.tv
            if a.knife == "1":
                env.update(SSBOT_FORUM_KNIFE_ROWS="1", SSBOT_FORUM_WINDOWS="1", SSBOT_FORUM_WINDOWS_CORE="2",
                           SSBOT_FORUM_WINDOWS_PRESS="0", SSBOT_FORUM_SLAM_PLAY="0", SSBOT_FORUM_CLAWSTRIKE="0",
                           SSBOT_FORUM_SLAM_PLAY_PREFS="1")
            os.environ.update(env)
            audit.install()
            return env
        replay.h2_environment = arm
        try:
            with a.out.with_suffix(".log").open("x", encoding="utf-8") as log, contextlib.redirect_stdout(log):
                rc = replay.main(["--code-root", str(a.code_root), "--run", str(a.run),
                                  "--instance", str(a.instance), "--ticks", str(a.ticks),
                                  "--measure", "--out", str(replay_path)])
        finally:
            audit.close()
            replay.h2_environment = environment
    result = json.loads(replay_path.read_text(encoding="utf-8"))
    identity = None
    if a.reference:
        ref = json.loads(a.reference.read_text(encoding="utf-8"))
        identity = {"rows_equal": result["rows"] == ref["rows"],
                    "clock_reads_equal": result["clock_reads"] == ref["clock_reads"],
                    "ticks_equal": result["ticks"] == ref["ticks"]}
    checks = {"replay_ok": rc == 0, "trace_complete": result["trace_check"]["complete"],
              "configuration_complete": result["configuration"]["configuration_complete"],
              "every_ACTION_audited": audit.rows == result["ticks"],
              "real_selector_captured": audit.ranked > 0, "schema_errors_absent": not audit.errors}
    if a.tv == "1":
        checks["real_body_field_captured"] = audit.body_calls > 0
    if a.knife == "1":
        checks.update(knife_rows_seen=audit.knife_rows > 0, knife_chosen_seen=audit.knife_chosen > 0,
                      unsafe_knife_choice_absent=audit.knife_unsafe == 0)
    if identity is not None:
        checks["output_and_clock_identity"] = all(identity.values())
    summary = {"complete": all(checks.values()), "checks": checks, "identity": identity,
               "ticks": audit.rows, "ranked_calls": audit.ranked, "body_calls": audit.body_calls,
               "schema_errors": audit.errors[:20], "tv": int(a.tv), "replay": str(replay_path),
               "knife": {"enabled": int(a.knife), "rows": audit.knife_rows, "chosen": audit.knife_chosen,
                         "unsafe_chosen": audit.knife_unsafe},
               "choices": str(choices_path), "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "scope": "offline selector and ACTION provenance; no closed-loop benefit or live latency claim"}
    a.out.write_text(json.dumps(summary, indent=1, allow_nan=False), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
