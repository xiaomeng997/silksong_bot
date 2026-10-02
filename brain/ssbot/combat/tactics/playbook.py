"""L3 playbook loader (DESIGN §3.5.7, §4.4 knowledge/<build>/playbooks/<enemy>.yaml): stance, punish windows, Bind
states and the planner's scoring weights for one encounter. Pure data; safety rules are not in it."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
PLAYBOOKS = REPO / "knowledge" / "1.0.30000" / "playbooks"

DEFAULT_WEIGHTS = {"hit": 10.0, "stance": 0.6, "risk": 3.0, "waste": 0.6, "face": 0.3, "ground": 0.2, "cont": 0.15,
                   "jump": 0.15}


@dataclass
class Playbook:
    enemy: str
    boss_type: str
    scene: str
    arena_x: tuple[float, float]
    hero_y: float
    hidden_x: float
    engage_reach_u: float
    risk_horizon_s: tuple[float, float]
    punish_states: frozenset[str]
    punish_phases: frozenset[str]
    bind_states: frozenset[str]
    bind_hp_missing_min: int
    hit_damage: dict[str, float]
    no_hurtbox: frozenset[str] = frozenset()
    hidden_x_vision: float | None = None     # the hidden stance when the burst position is not seen (stage C)
    prepare: dict[str, tuple[float, str]] = field(default_factory=dict)   # state -> (x' from the anchor, side)
    long_horizon: dict = field(default_factory=dict)   # states, until, extra_s, map (observable phase -> state)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    @classmethod
    def from_dict(cls, d: dict) -> "Playbook":
        st = d.get("stance") or {}
        pun = d.get("punish") or []
        bind = d.get("bind") or {}
        return cls(enemy=d["enemy"], boss_type=d["boss_type"], scene=d["scene"],
                   arena_x=tuple(d["arena"]["x"]), hero_y=float(d["arena"]["hero_y"]),
                   hidden_x=float(st.get("hidden_x", sum(d["arena"]["x"]) / 2)),
                   engage_reach_u=float(st.get("engage_reach_u", 2.3)),
                   risk_horizon_s=tuple(st.get("risk_horizon_s", (0.4, 2.0))),
                   punish_states=frozenset(p["state"] for p in pun),
                   punish_phases=frozenset(p["phase"] for p in pun if p.get("phase")),
                   bind_states=frozenset(bind.get("states") or ()),
                   bind_hp_missing_min=int(bind.get("hp_missing_min", 2)),
                   hit_damage={k: float(v) for k, v in (d.get("hit_damage") or {"nail": 5}).items()},
                   no_hurtbox=frozenset(d.get("no_hurtbox") or ()),
                   hidden_x_vision=float(st["hidden_x_vision"]) if st.get("hidden_x_vision") is not None else None,
                   prepare={x["state"]: (float(x["x_prime"]), str(x.get("side", "attack")))
                            for x in d.get("prepare") or ()},
                   long_horizon=_long(d.get("long_horizon")),
                   weights=DEFAULT_WEIGHTS | {k: float(v) for k, v in (d.get("weights") or {}).items()})


def _long(d: dict | None) -> dict:
    if not d:
        return {}
    return {"states": frozenset(d["states"]), "until": d["until"], "extra_s": float(d.get("extra_s", 0.3)),
            "map": dict(d.get("map") or {})}


def load_playbook(enemy: str = "BellBeast", path: Path | str | None = None) -> Playbook:
    p = Path(path) if path else PLAYBOOKS / f"{enemy}.yaml"
    return Playbook.from_dict(yaml.safe_load(p.read_text("utf-8")))
