"""M1 skeleton check: IPC v1 handshake, STATE stream continuity and cost, RPC, frame-targeted ACTIONs."""
import statistics
import time

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink


def main() -> None:
    link = OracleLink()
    print("hello:", {k: link.hello[k] for k in ("plugin", "game", "instance", "qpc_freq", "rpcs")})
    print("ping ->", link.rpc("ping"))

    frames, costs, sizes = [], [], []
    link.subscribe_raw(lambda t, raw: sizes.append(len(raw)) if t == 2 else None)
    end = time.monotonic() + 10
    last = -1
    while time.monotonic() < end:
        s = link.wait_state(newer_than=last, timeout_s=2)
        last = s["f"]
        frames.append(s["f"])
        costs.append(s["cost_us"])
    seen = len(set(frames))
    span = frames[-1] - frames[0] + 1
    print(f"STATE frames polled {seen}/{span} (polling may skip; see recorder for delivery), drops reported {s['drop']}")
    print(f"STATE size p50 {statistics.median(sizes):.0f} B, max {max(sizes)} B; received {len(sizes)} messages")
    print(f"build cost us p50 {statistics.median(costs):.0f}  p99 {sorted(costs)[int(len(costs) * .99) - 1]}  max {max(costs)}")
    print("game:", {k: s["game"][k] for k in ("gs", "menu", "scene", "t_live", "pd_mode")} if s["game"] else None)
    print("pause:", s["pause"])

    # Frame-targeted ACTION: press Enter (title -> save select) at frame f+5 for 3 frames.
    target = link.frame + 5
    link.act(target, mask("enter"), hold_frames=3, ack_seq=42)
    s = link.wait_state(lambda s: s["act"]["ack"] == 42, timeout_s=2)
    print(f"ACTION target {target} applied at frame {s['act']['applied']} (lag {s['act']['applied'] - target}), mask {s['act']['mask']}")
    s = link.wait_state(lambda s: s["act"]["mask"] == 0, timeout_s=2)
    print(f"released by frame {s['f']}")
    link.rpc("input.release")  # stop driving, or the brain-lost watchdog taps Pause once we go idle
    time.sleep(1.5)
    print("menu now:", link.state["game"]["menu"])
    link.close()


if __name__ == "__main__":
    main()
