"""attack_hit_audit: a hit on the hero ends the swing (HeroController.TakeDamage cancels the attack)."""
from __future__ import annotations

from types import SimpleNamespace

from ssbot.tools import attack_hit_audit as aha

NAMES = ["attacking", "upAttacking", "altAttack", "wallSliding"]


class _Tab:
    def __init__(self) -> None:
        self.sh = SimpleNamespace(frames=(5, 12), src="Slash", t_on=0.0, t_off=0.0)

    def __contains__(self, slot: str) -> bool:
        return slot == "normal"

    def __getitem__(self, slot: str):
        return self.sh


def _swing(n: int, contact: set[int], hit: int | None = None, damage: int | None = None) -> list[dict]:
    out = [{"hero": {"cstate": [0]}}]
    for k in range(n):
        ev = []
        if hit is not None and k == hit:
            ev.append({"k": "hit", "d": {"src": "Slash"}})
        if damage is not None and k == damage:
            ev.append({"k": "damage", "d": {}})
        # attacking with altAttack set: a "normal" swing in swings()
        out.append({"hero": {"cstate": [0b101]}, "ev": ev, "contact": k in contact})
    return out


def test_hero_hit_before_the_first_active_frame_cancels_the_swing(monkeypatch):
    monkeypatch.setattr(aha, "_contact", lambda s, tab, slot: bool(s.get("contact")))
    r = aha.audit(_swing(20, contact={6, 7}, damage=3)[1:], _Tab(), NAMES, slack=0)
    assert r["confusion"]["normal"] == {"TN": 1}
    assert r["cancelled"]["normal"] == {"cancelled": 1, "cancelled_before_active": 1}


def test_contact_before_the_hero_is_hit_still_counts(monkeypatch):
    monkeypatch.setattr(aha, "_contact", lambda s, tab, slot: bool(s.get("contact")))
    r = aha.audit(_swing(20, contact={6}, hit=7, damage=9)[1:], _Tab(), NAMES, slack=0)
    assert r["confusion"]["normal"] == {"TP": 1}
    r = aha.audit(_swing(20, contact={9}, damage=9)[1:], _Tab(), NAMES, slack=0)
    assert r["confusion"]["normal"] == {"TN": 1}
    assert r["cancelled"]["normal"]["contact_on_damage_frame"] == 1


def test_uncancelled_swing(monkeypatch):
    monkeypatch.setattr(aha, "_contact", lambda s, tab, slot: bool(s.get("contact")))
    r = aha.audit(_swing(20, contact={6}, hit=7)[1:], _Tab(), NAMES, slack=0)
    assert r["confusion"]["normal"] == {"TP": 1}
    assert "normal" not in r["cancelled"]
