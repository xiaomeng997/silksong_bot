"""L2 tactics (DESIGN §3.5.1, §3.5.5): the mode (ENGAGE / EVADE / HEAL / HOLD) and the planner's preferences for the
tick, from the playbook (L3), the forecast and the supervisor's flags. Rules, not learning (§3.5.8: tactic weights are
tuned on savestate batches; they only move performance, never the invariants)."""
from ssbot.combat.tactics.modes import ENGAGE, EVADE, HEAL, HOLD, PREPARE, TacticPrefs, Tactics
from ssbot.combat.tactics.playbook import Playbook, load_playbook

__all__ = ["ENGAGE", "EVADE", "HEAL", "HOLD", "PREPARE", "Playbook", "TacticPrefs", "Tactics", "load_playbook"]
