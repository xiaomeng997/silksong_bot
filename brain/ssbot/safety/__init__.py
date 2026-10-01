"""Safety supervisor (DESIGN §3.7): hits_to_death, invariants I1-I4, risk tiers and triggers, the pause loop and quit
sequence, the quit map and the frozen-state unpause check. Hand-written and unit-tested, never learned (§3.5.8).

Import firewall (DESIGN §8.2 CI rules): nothing here imports ssbot.ipc or an oracle backend; the oracle-mode cue
adapter reads a STATE dict it is handed.
"""
