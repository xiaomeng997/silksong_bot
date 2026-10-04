"""Upper bounds of the damage one landed hit of each hero attack can deal, from the equipped crest, the needle level and
the tools (DESIGN §3.7.3: YELLOW forbids a possibly killing blow, the boss-death slow motion keeps the pause gate shut;
§3.5.6). The killing-blow rule of the supervisor and of the L0 safety filter asks this table, per attack, whether the
next landed hit can take an enemy to 0 HP.

    dmg = HeroDamage.from_loadout("Hunter", needle_level=0, tools=("Silk Spear",))
    dmg.nail, dmg.spear                  # 5.0, 15.0: one Hunter nail hit, one Silkspear hit
    dmg.of_prim(Prim.ATTACK_SIDE)        # 5.0
    dmg.observe("Slash", "Nail", 5)      # a recorded hit: raises its kind's bound if the table was low (and says so)

Why (task "STUCK at 15 HP", 2026-10-04): the bound used to be one number for every attack, max(5, the largest hit
dealt this attempt) in the supervision glue and SPEAR_DAMAGE = 15 for every attack in the planner. After a Silkspear
hit (15) a nail hit counted as able to deal 15, so at boss HP <= 15 and h = 2 the bot never attacked, never gathered
silk, never Bound and never left YELLOW (6 STUCK episodes at 15 HP in runs 20261003_175813 / 231255 / 231257). Below
full HP the Silkspear is not allowed at all (silk skills only at full HP), so the nail's 5 is the only hit that counts.

The game's damage of a nail hit (DamageEnemies.cs 948-1031, HealthManager.cs 1011-1022, decomp 1.0.30000):
  PlayerData.nailDamage (5 / 9 / 13 / 17 / 21 by nailUpgrades, PlayerData.cs 2896) x the damager's
  nailDamageMultiplier (the crest's attack table: 1.0 for every Hunter / Reaper slash, the charge slash 1.4 / 2.5,
  knowledge/1.0.30000/attacks) x the nail imbuement's NailDamageMultiplier (a tool imbues the nail) x Warrior rage
  1.25 (Warrior crest) x the Hunter combo (Hunter_v2 1.3, Hunter_v3 1.3 / 1.5; base Hunter none) x the silk taunt
  1.5 (consumed by the next hit after a taunt: the bot has no taunt primitive, so never; a taunt primitive must add
  TAUNT_MULT here) x Barbed Wire 1.25 (equipped), then a Wanderer critical hit x 3
  (only with the Wanderer crest equipped: HeroController.IsWandererLucky, or a queued critical from the Wanderer's own
  moves). Logged: Hunter crest, needle level 0, every nail hit 5 (4,081 hits of live run 20261001_122249, 21 of 21
  in each STUCK episode, "crit" false in all), the Silkspear 15 (460 hits).
Unknown parts are bounded from above, never guessed low: an unknown crest takes every crest factor (crit x 3, combo
1.5, rage 1.25), an equipped tool not known to leave the nail's damage alone (KNOWN_NEUTRAL) takes the imbuement and
Barbed Wire factors, the Silkspear scales with the needle (a flat 15 would only make it smaller), and thrown tools
and the Clawline are unbounded (none in the M2 loadouts; their damage is not in the facts).
observe() raises a kind's bound to any larger hit the recording / STATE shows, and reports it: the table was wrong.
"""
import math
from dataclasses import dataclass, replace

from ssbot.core.primitives import Prim

NEEDLE_DAMAGE = (5, 9, 13, 17, 21)          # PlayerData.nailDamage by nailUpgrades (PlayerData.cs 2896)
SPEAR_DAMAGE_L0 = 15.0                      # Silkspear at needle level 0 (460 of 460 logged hits)
TAUNT_MULT = 1.5                            # DamageEnemies: SilkTauntEffectConsume
BARBED_WIRE_MULT = 1.25                     # Gameplay.BarbedWireDamageDealtMultiplier
IMBUE_MULT = 1.5                            # bound on an unlisted nail imbuement's NailDamageMultiplier (assumption)
ZAP_MULT = 1.25                             # Gameplay.ZapDamageMult on skills with the zap imbuement tool
WARRIOR_MULT = 1.25                         # Gameplay.WarriorDamageMultiplier (rage mode)
HUNTER_COMBO = {"Hunter": 1.0, "Hunter_v2": 1.3, "Hunter_v3": 1.5}   # Gameplay.HunterCombo*DamageMult (v3: max)
WANDERER_CRIT = 3.0                         # Gameplay.WandererCritMultiplier
# the crest's largest nailDamageMultiplier among the swings the planner can press (side / alt / up / wall / down /
# dash stab; not the charge slash: attack presses are 3 frames, candidates.PRESS, never held into a nail art)
SLOT_MULT = {"Hunter": 1.0, "Hunter_v2": 1.0, "Hunter_v3": 1.0, "Reaper": 1.0}
CREST_MULT = {"Hunter": 1.0, "Hunter_v2": HUNTER_COMBO["Hunter_v2"], "Hunter_v3": HUNTER_COMBO["Hunter_v3"],
              "Reaper": 1.0, "Wanderer": WANDERER_CRIT, "Warrior": WARRIOR_MULT}
CRIT_CRESTS = frozenset({"Wanderer"})
UNKNOWN_CREST_MULT = WANDERER_CRIT * HUNTER_COMBO["Hunter_v3"] * WARRIOR_MULT
UNKNOWN_SLOT_MULT = 2.5                     # the largest swing multiplier in the attack tables (Reaper charge)
# tools that do not change a nail hit's damage (crests.json gameplay: weighted anklet = knockback / i-frames, dice =
# luck, long needle = reach, moss = silk; the Silkspear is a silk skill with its own bound; the Fractured Mask)
KNOWN_NEUTRAL = frozenset({"Silk Spear", "Weighted Anklet", "Magnetite Dice", "Longneedle", "Mosscreep Tool 1",
                           "Mosscreep Tool 2", "Fractured Mask"})
BARBED_WIRE = "Barbed Wire"
SPEAR_SRC = ("Needle Damage",)              # the Silkspear's damager ("hit" event src)
NAIL = frozenset({Prim.ATTACK_SIDE, Prim.ATTACK_UP, Prim.ATTACK_DOWN, Prim.HIT_TARGET})


@dataclass(frozen=True)
class HeroDamage:
    crest: str
    needle: int                 # PlayerData.nailDamage
    nail: float                 # one landed nail hit (any swing the planner presses), upper bound
    spear: float                # one Silkspear hit (SILKSKILL), upper bound
    tool: float                 # one thrown tool hit (TOOL), upper bound; inf: unknown
    crit: bool                  # the crest can deal critical hits (Wanderer)
    raised: tuple[str, ...] = ()   # observe(): kinds a logged hit raised (the table was low)

    @classmethod
    def from_loadout(cls, crest: str | None, needle_level: int = 0, tools=()) -> "HeroDamage":
        """The bounds for an audited loadout. crest None / "" / unlisted: every crest factor (unknown is never low)."""
        needle = NEEDLE_DAMAGE[min(max(int(needle_level), 0), len(NEEDLE_DAMAGE) - 1)]
        c = crest or ""
        slot = SLOT_MULT.get(c, UNKNOWN_SLOT_MULT)
        mult = CREST_MULT.get(c, UNKNOWN_CREST_MULT)
        tools = {t for t in tools or () if t}
        if BARBED_WIRE in tools:
            mult *= BARBED_WIRE_MULT
        unknown = tools - KNOWN_NEUTRAL - {BARBED_WIRE}
        if unknown:
            mult *= IMBUE_MULT * BARBED_WIRE_MULT
        nail = math.floor(needle * slot + 0.5) * mult
        # a hit's damage is rounded; the bound keeps the exact product (never below the game's value)
        spear = SPEAR_DAMAGE_L0 * needle / NEEDLE_DAMAGE[0] * (ZAP_MULT if unknown else 1.0)
        return cls(crest=c, needle=needle, nail=float(nail), spear=float(spear), tool=math.inf,
                   crit=c in CRIT_CRESTS or c not in CREST_MULT)

    def of_prim(self, p: Prim) -> float:
        """One landed hit of primitive p; 0 for the non-damaging ones."""
        if p in NAIL:
            return self.nail
        if p == Prim.SILKSKILL:
            return self.spear
        if p in (Prim.TOOL, Prim.CLAWLINE):
            return self.tool
        return 0.0

    def kill_prims(self, hp: float | None, prims=None) -> frozenset[Prim]:
        """The damaging primitives (of `prims`, default all) whose one landed hit may take an enemy with `hp` to 0."""
        if hp is None:
            return frozenset()
        return frozenset(p for p in (prims if prims is not None else Prim) if 0 < self.of_prim(p) and hp <= self.of_prim(p))

    def kind_of(self, src: str | None, attack: str | None) -> str:
        """The bound a recorded hit ("hit" event src / attack) belongs to: nail, spear or tool."""
        if src and any(src.startswith(s) for s in SPEAR_SRC):
            return "spear"
        if attack in ("Nail", "NailBeam"):
            return "nail"
        return "tool"

    def observe(self, src: str | None, attack: str | None, dmg: float | None) -> "HeroDamage":
        """This table with the kind of a logged hero hit raised to its damage if that was more (the table was low)."""
        if dmg is None or not math.isfinite(float(dmg)):
            return self
        k = self.kind_of(src, attack)
        if float(dmg) <= getattr(self, k):
            return self
        return replace(self, **{k: float(dmg)}, raised=tuple(sorted({*self.raised, k})))
