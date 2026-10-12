"""The special mode's decision board (combat.special_mode, task 1v1 G1): the Forum planner posts, per enemy, whether a
special row was safe on its last tick and the hero's x at its press; the L2 Clapper controller (tactics.gauntlet)
reads it on the next tick. A module of its own (no imports) so the controller reaches nothing else of the planner."""
import os

SPECIAL_MODE = os.environ.get("SSBOT_FORUM_SPECIAL_MODE", "0").strip() == "1"
# the L2 strike spot (default on with the mode; SSBOT_FORUM_SPECIAL_L2=0: the planner's special rows only)
L2_ON = SPECIAL_MODE and os.environ.get("SSBOT_FORUM_SPECIAL_L2", "1").strip() != "0"
L2_HOLD_S = 0.1           # the L2 strike spot outlives a flicker of the planner's decision this long (review 2026-10-12)
BOARD: dict = {}          # iid -> {"tick", "move", "k", "on", "x", "rows", "safe"} (the planner's last special decision)
