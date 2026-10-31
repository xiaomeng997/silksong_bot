"""Bounded receive-clock estimate for the B2 first ground jump, not an application receipt.

The 13 ms window is calibrated from the 15e engineering game. It cannot
certify an unseen future input update; real application/takeoff remain required.
"""
FRAME_NS=16_666_667
PREVIOUS_STATE_WINDOW_NS=13_000_000
SEND_RESERVE_NS=1_000_000


def first_jump_clock(timing, target):
    if not isinstance(timing,dict):raise ValueError("missing dispatch receive clock")
    names=("now_ns","anchor_frame","anchor_ns","latest_received_frame")
    if any(type(timing.get(k)) is not int for k in names):raise ValueError("unknown dispatch receive clock field")
    now,frame,received,latest=(timing[k] for k in names)
    if type(target) is not int or target-frame not in (1,2):raise ValueError("dispatch clock is not one/two frames before target")
    if received<0 or now<received or latest<frame:raise ValueError("dispatch receive clock is inconsistent")
    deadline=received+PREVIOUS_STATE_WINDOW_NS+(target-frame-1)*FRAME_NS
    deadline_anchor=frame
    if "earlier_frame" in timing or "earlier_ns" in timing:
        ef,en=timing.get("earlier_frame"),timing.get("earlier_ns")
        if (type(ef) is not int or type(en) is not int or ef!=target-2 or frame!=target-1 or
                en<0 or en>received):raise ValueError("inconsistent earlier receive anchor")
        earlier_deadline=en+PREVIOUS_STATE_WINDOW_NS+FRAME_NS
        if earlier_deadline<deadline:deadline,deadline_anchor=earlier_deadline,ef
    finish=now+SEND_RESERVE_NS
    return {**{k:timing[k] for k in (*names,"earlier_frame","earlier_ns") if k in timing},"estimated_finish_ns":finish,"deadline_ns":deadline,"deadline_anchor_frame":deadline_anchor,
            "send_reserve_ns":SEND_RESERVE_NS,"window_after_previous_state_ns":PREVIOUS_STATE_WINDOW_NS,
            "remaining_ns":deadline-finish,"late":latest>=target or finish>=deadline,"target_already_received":latest>=target,
            "scope":"calibrated send estimate; not proof of application or takeoff"}
