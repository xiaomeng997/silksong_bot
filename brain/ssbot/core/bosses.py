"""What the backends need to know about a boss: its type_key, the FSM that carries its attack phases, the states that
mean it is dying, its maximum HP (the vision path's hit-count estimate starts there) and the table from FSM states to
the phases a vision model can tell apart.

Shared by OracleBackend (phase from the FSM, ENEMY_KILLED on a death state), ObservabilityFilter (HP from hits,
observable phase) and the threat forecaster (ssbot.combat.forecast reads the observable phase back to FSM states), so
it lives outside all of them: modules behind the import firewall may read it too.

BELL_BEAST from the trial runs (runs/m2/20261001_121446_BellBeast_data, 2 episodes; the person's session
human/20260930_210337): "Bone Beast", HealthManager hp 150 at the first sighting, "Control" FSM, the kill goes
Control -> "Death Broadcast" in the frame the entity leaves the "ents" list (the killing blow shows no HP drop).

Observable phases (BELL_BEAST_PHASES, M2 W3): what a vision model can tell apart is the boss's animation clip and
whether it is drawn at all. Live run 20261001_122249, recording i2_002 (every exported frame; the boss is not exported
while it is underground, which the ObservabilityFilter turns into the phase "hidden"): the visible Control states and
their clips are Charge Emerge "Charge Emerge", Charge Antic "Charge Antic", Charge "Charge Loop", Charge End
"Charge End", Leap Out and Descending "Attack Leap", Leap Land "Attack Leap End", Burst Out "Attack Burst",
Rage Burst and Rage Roar "Rage Roar", Roar End "Rage End", and Dig In, which keeps the clip of the state before it
("Charge End" after a charge, 5,054 frames; "Attack Leap End" after a leap, 4,694). So Charge End, Leap Land and Dig In
are one phase ("recover": the forecaster tells a charge's end from a leap's by the phase before it), Leap Out and
Descending one ("leap"), Rage Burst and Rage Roar one ("roar"). States that are drawn at most for a transition frame
(Emerge Antic C / L as the boss starts to show, Fire Bells and Burst Recovery around the burst, Rage Antic and Rage
Submerge around the roar) take the phase of the drawn state next to them. Every other state is underground.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BossSpec:
    type_key: str
    control_fsm: str = "Control"
    death_states: tuple[str, ...] = ()
    hp_max: float | None = None
    phases: dict[str, str] = field(default_factory=dict)   # FSM state -> observable phase; missing = "unknown"
    drawn: tuple[str, ...] = ()        # FSM states in which the boss is drawn (and hittable) for more than a frame


BELL_BEAST_PHASES = {
    "Emerge Antic C": "emerge", "Charge Emerge": "emerge", "Charge Antic": "charge_antic", "Charge": "charge",
    "Charge End": "recover", "Leap Land": "recover", "Dig In": "recover",
    "Emerge Antic L": "leap", "Leap Out": "leap", "Descending": "leap",
    "Fire Bells": "burst", "Burst Out": "burst", "Burst Recovery": "burst",
    "Rage Antic": "roar", "Rage Burst": "roar", "Rage Roar": "roar", "Roar End": "roar_end", "Rage Submerge": "roar_end",
}

BELL_BEAST_DRAWN = ("Charge Emerge", "Charge Antic", "Charge", "Charge End", "Dig In", "Leap Out", "Descending",
                    "Leap Land", "Burst Out", "Rage Burst", "Rage Roar", "Roar End")

BELL_BEAST = BossSpec(type_key="Bone Beast", control_fsm="Control", death_states=("Death Broadcast",), hp_max=150.0,
                      phases=BELL_BEAST_PHASES, drawn=BELL_BEAST_DRAWN)

BOSSES: dict[str, BossSpec] = {b.type_key: b for b in (BELL_BEAST,)}
