"""What the backends need to know about a boss: its type_key, the FSM that carries its attack phases, the states that
mean it is dying, its maximum HP (the vision path's hit-count estimate starts there) and the table from FSM states to
the phases a vision model can tell apart.

Shared by OracleBackend (phase from the FSM, ENEMY_KILLED on a death state) and ObservabilityFilter (HP from hits,
observable phase), so it lives outside both: modules behind the import firewall may read it too.

BELL_BEAST from the trial runs (runs/m2/20261001_121446_BellBeast_data, 2 episodes; the person's session
human/20260930_210337): "Bone Beast", HealthManager hp 150 at the first sighting, "Control" FSM, the kill goes
Control -> "Death Broadcast" in the frame the entity leaves the "ents" list (the killing blow shows no HP drop).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BossSpec:
    type_key: str
    control_fsm: str = "Control"
    death_states: tuple[str, ...] = ()
    hp_max: float | None = None
    phases: dict[str, str] = field(default_factory=dict)   # FSM state -> observable phase; missing = "unknown"


BELL_BEAST = BossSpec(type_key="Bone Beast", control_fsm="Control", death_states=("Death Broadcast",), hp_max=150.0)

BOSSES: dict[str, BossSpec] = {b.type_key: b for b in (BELL_BEAST,)}
