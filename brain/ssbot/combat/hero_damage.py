"""Upper bounds of the damage one landed hit of each hero attack can deal, from the equipped crest, the needle level, the
tools and the target's damage scaling (DESIGN §3.7.3: YELLOW forbids an uncertified possibly killing blow, the
boss-death slow motion keeps the pause gate shut; §3.5.6). The killing-blow rule of the supervisor and of the L0 safety
filter asks this table, per attack, whether the next landed hit can take an enemy to 0 HP. A bound is never below the
game's value: it is the game's own formula with every rounding taken upwards.

    dmg = HeroDamage.from_loadout("Hunter", needle_level=0, tools=("Silk Spear",), scaling={0: 1.03})
    dmg.nail, dmg.spear                  # 5.0, 15.0: one Hunter nail hit, one Silkspear hit
    dmg.of_prim(Prim.ATTACK_SIDE)        # 5.0
    dmg.at(math.inf).nail                # inf: a target whose damage scaling is unknown
    dmg.observe("Slash", "Nail", 5)      # a recorded hit: raises its kind's bound if the table was low (and says so)

Why (task "STUCK at 15 HP", 2026-10-04): the bound used to be one number for every attack, max(5, the largest hit
dealt this attempt) in the supervision glue and SPEAR_DAMAGE = 15 for every attack in the planner. After a Silkspear
hit (15) a nail hit counted as able to deal 15, so at boss HP <= 15 and h = 2 the bot never attacked, never gathered
silk, never Bound and never left YELLOW (8 STUCK episodes at 15 HP in runs 20261003_175813 / 231255 / 231257).

The game's damage of a hero hit (decomp 1.0.30000; every Mathf.RoundToInt rounds half to even on a float32):
  DamageEnemies.DoDamage (948-1085):
    base   = RoundToInt(PlayerData.nailDamage * nailDamageMultiplier)       (useNailDamage; nailDamage 5 / 9 / 13 /
             17 / 21 by nailUpgrades, PlayerData.cs 2896; nailDamageMultiplier: the swing's, crests.json: 1.0 for every
             Hunter / Reaper / Wanderer swing the planner presses, the charge slash 1.4 / 2.5 / 2.3 is never pressed)
    stack  = DamageStack.PopDamage: RoundToInt(base * (1 + sum(m_i - 1)) + offset): the multipliers ADD (not
             multiply): the nail imbuement's NailDamageMultiplier, Warrior rage 1.25, the Hunter combo (Hunter_v2 1.3;
             Hunter_v3 1.5 or 1.3, if / else), the silk taunt 1.5 (the hit after a taunt: the bot has no taunt
             primitive, so never; a taunt primitive must add TAUNT_MULT), Barbed Wire 1.25, the damager's own
             DamageMultiplier (1.0 on every hero damager, crests.json); offset = -damageDealtOffset (0 on every hero
             damager). damageMultPerHit (Wanderer [0.9, 0.1, 0.1]) only lowers it.
    dealt  = RoundToInt(stack)
    hero damagers with useNailDamage false (crests.json: damageDealt 5, no hero multipliers) deal 5 whatever the needle
  HealthManager.TakeDamage (943-1013, 1284):
    scaled = RoundToInt(dealt * damageScaling.LevelNMult)   (ApplyDamageScaling: the target's own per-level factor,
             level nailUpgrades for nail damage, -1 -> 1.0 for the fixed damagers; not in any export: audited per enemy
             type from the recordings' dealt -> dmg pairs, tools/kill_window, knowledge kill_windows.json "scaling")
    crit   = RoundToInt(scaled * 3)                          (a Wanderer critical hit: HeroController.IsWandererLucky
             needs the Wanderer crest, QueuedNextHitCritical comes only from the Wanderer's own moves)
    hp    -= RoundToInt(crit * HitInstance.Multiplier)      (Multiplier 1 from DoDamage)
Each stage is bounded with round_up(x) = floor(x + 0.5 + ROUND_EPS) >= RoundToInt(float32(x)) (the float32 error of
these products is far below ROUND_EPS), on upper bounds of every factor: monotone, so the result is never below the
game's value (tests/test_kill_rule.py emulates DamageStack and RoundToInt in float32 over every crest, needle level,
tool and scaling). The verifier's counter-examples of the first version (the exact product, not rounded): Hunter_v3
needle 0 is 8 (7.5 rounded half to even), Hunter_v2 needle 1 is 12 (11.7); both are bounds now.
Logged: Hunter crest, needle level 0, every nail hit 5 and every Silkspear 15 on Bell Beast (1,049 / 270 hits of run
20261003_231255, dealt = dmg, "crit" false in all).
Unknown parts are bounded from above, never guessed low: an unknown crest takes every crest factor (combo 1.5 and rage
1.25 added, crit x 3) and the largest swing multiplier 2.5; an unknown needle level (vision without an inventory audit)
takes every level; an equipped tool not known to leave the nail's damage alone (KNOWN_NEUTRAL) adds the imbuement
(IMBUE_MULT, an assumption: no imbuement in the facts) and Barbed Wire; a target type without an audited scaling at the
needle level is unbounded (inf: every press may kill it); the Silkspear scales with the needle (a flat 15 would only
make it smaller); thrown tools and the Clawline are unbounded (none in the M2 loadouts; their damage is not in the
facts). observe() raises a kind's bound to any larger hit the recording / STATE shows, and reports it.
"""
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace

from ssbot.core.primitives import Prim

NEEDLE_DAMAGE = (5, 9, 13, 17, 21)          # PlayerData.nailDamage by nailUpgrades (PlayerData.cs 2896)
SPEAR_DAMAGE_L0 = 15.0                      # Silkspear dealt at needle level 0 (460 of 460 logged hits)
TAUNT_MULT = 1.5                            # DamageEnemies: SilkTauntEffectConsume (the bot never taunts)
BARBED_WIRE_MULT = 1.25                     # Gameplay.BarbedWireDamageDealtMultiplier
IMBUE_MULT = 1.5                            # bound on an unlisted nail imbuement's NailDamageMultiplier (assumption)
ZAP_MULT = 1.25                             # Gameplay.ZapDamageMult on skills with the zap imbuement tool
WARRIOR_MULT = 1.25                         # Gameplay.WarriorDamageMultiplier (rage mode)
HUNTER_COMBO = {"Hunter": 1.0, "Hunter_v2": 1.3, "Hunter_v3": 1.5}   # Gameplay.HunterCombo*DamageMult (v3: max)
WANDERER_CRIT = 3.0                         # Gameplay.WandererCritMultiplier
# the crest's largest nailDamageMultiplier among the swings the planner can press (side / alt / up / wall / down /
# dash stab; not the charge slash: attack presses are 3 frames, candidates.PRESS, never held into a nail art)
SLOT_MULT = {"Hunter": 1.0, "Hunter_v2": 1.0, "Hunter_v3": 1.0, "Reaper": 1.0, "Wanderer": 1.0}
# the stack's additive terms (m - 1) of each crest: the Hunter combos, Warrior rage; an unknown crest takes both
CREST_ADDS = {"Hunter": (), "Hunter_v2": (HUNTER_COMBO["Hunter_v2"] - 1,), "Hunter_v3": (HUNTER_COMBO["Hunter_v3"] - 1,),
              "Reaper": (), "Wanderer": (), "Warrior": (WARRIOR_MULT - 1,)}
UNKNOWN_ADDS = (HUNTER_COMBO["Hunter_v3"] - 1, WARRIOR_MULT - 1)
CRIT_CRESTS = frozenset({"Wanderer"})
UNKNOWN_SLOT_MULT = 2.5                     # the largest swing multiplier in the attack tables (Reaper charge)
FIXED_DEALT = 5.0                           # hero damagers with useNailDamage false (crests.json damageDealt 5)
ROUND_EPS = 1e-3
UNKNOWN_SCALING = math.inf                  # a target type without an audited damage scaling
# tools that do not change a nail hit's damage (crests.json gameplay: weighted anklet = knockback / i-frames, dice =
# luck, long needle = reach, moss = silk; the Silkspear is a silk skill with its own bound; the Fractured Mask)
KNOWN_NEUTRAL = frozenset({"Silk Spear", "Weighted Anklet", "Magnetite Dice", "Longneedle", "Mosscreep Tool 1",
                           "Mosscreep Tool 2", "Fractured Mask"})
BARBED_WIRE = "Barbed Wire"
SPEAR_SRC = ("Needle Damage",)              # the Silkspear's damager ("hit" event src)
NAIL = frozenset({Prim.ATTACK_SIDE, Prim.ATTACK_UP, Prim.ATTACK_DOWN, Prim.HIT_TARGET})


def round_up(x: float) -> float:
    """An upper bound of Mathf.RoundToInt(float32(x)) (half to even): floor(x + 0.5 + ROUND_EPS); inf stays inf."""
    return x if not math.isfinite(x) else float(math.floor(x + 0.5 + ROUND_EPS))


def _scale(dealt: float, s: float, crit: bool) -> float:
    """The target side of one hit: ApplyDamageScaling, then the Wanderer critical hit."""
    if not math.isfinite(s) or not math.isfinite(dealt):
        return math.inf
    v = round_up(dealt * s)
    return round_up(v * WANDERER_CRIT) if crit else v


def scaling_at(scaling: "float | Mapping[int, float] | None", level: int) -> float:
    """The target's damage-scaling bound at a needle level: a number for every level, a {level: bound} table (a level
    missing from it is unknown), None unknown (UNKNOWN_SCALING)."""
    if scaling is None:
        return UNKNOWN_SCALING
    if isinstance(scaling, Mapping):
        v = scaling.get(level, scaling.get(str(level)))
        return UNKNOWN_SCALING if v is None else float(v)
    return float(scaling)


@dataclass(frozen=True)
class HeroDamage:
    crest: str
    needle: int                 # PlayerData.nailDamage (the largest when the level is unknown)
    nail: float                 # one landed nail hit (any swing the planner presses), upper bound, target side included
    spear: float                # one Silkspear hit (SILKSKILL), upper bound
    tool: float                 # one thrown tool hit (TOOL), upper bound; inf: unknown
    crit: bool                  # the crest can deal critical hits (Wanderer)
    raised: tuple[str, ...] = ()   # observe(): kinds a logged hit raised (the table was low)
    needle_level: int | None = 0   # nailUpgrades; None: unknown (every level counted)
    levels: tuple = ()          # ((level, nail dealt, spear dealt), ...): the attacker side per level counted
    scaling: float = 1.0        # the target's damage-scaling bound the nail / spear bounds use (max over levels)
    floor_nail: float = 0.0     # observe(): the largest logged hit of each kind (a bound is never below it)
    floor_spear: float = 0.0

    @classmethod
    def from_loadout(cls, crest: str | None, needle_level: int | None = 0, tools=(),
                     scaling: "float | Mapping[int, float] | None" = 1.0) -> "HeroDamage":
        """The bounds for an audited loadout. crest None / "" / unlisted: every crest factor (unknown is never low);
        needle_level None: unknown, every level; scaling: the target's damage-scaling bound (scaling_at)."""
        c = crest or ""
        slot = SLOT_MULT.get(c, UNKNOWN_SLOT_MULT)
        adds = list(CREST_ADDS.get(c, UNKNOWN_ADDS))
        tools = {t for t in tools or () if t}
        unknown = tools - KNOWN_NEUTRAL - {BARBED_WIRE}
        if BARBED_WIRE in tools or unknown:
            adds.append(BARBED_WIRE_MULT - 1)
        if unknown:
            adds.append(IMBUE_MULT - 1)
        spear_adds = (IMBUE_MULT - 1 + ZAP_MULT - 1) if unknown else 0.0
        lv = range(len(NEEDLE_DAMAGE)) if needle_level is None else \
            (min(max(int(needle_level), 0), len(NEEDLE_DAMAGE) - 1),)
        levels = []
        for k in lv:
            nd = NEEDLE_DAMAGE[k]
            base = round_up(nd * slot)                                # RoundToInt(nailDamage * nailDamageMultiplier)
            nail = max(round_up(base * (1.0 + sum(adds))), FIXED_DEALT)   # DamageStack.PopDamage
            spear = round_up(round_up(SPEAR_DAMAGE_L0 * nd / NEEDLE_DAMAGE[0]) * (1.0 + spear_adds))
            levels.append((k, nail, spear))
        d = cls(crest=c, needle=max(NEEDLE_DAMAGE[k] for k in lv), nail=0.0, spear=0.0, tool=math.inf,
                crit=c in CRIT_CRESTS or c not in CREST_ADDS,
                needle_level=None if needle_level is None else lv[0], levels=tuple(levels))
        return d.at(scaling)

    def at(self, scaling: "float | Mapping[int, float] | None") -> "HeroDamage":
        """These bounds against a target whose damage scaling is `scaling` (scaling_at; inf / None: unknown)."""
        nail = spear = 0.0
        smax = 0.0
        for k, n_dealt, s_dealt in self.levels:
            s = scaling_at(scaling, k)
            smax = max(smax, s)
            # the fixed damagers' level is -1 (ApplyDamageScaling x 1): only the nail's dealt scales
            nail = max(nail, _scale(n_dealt, s, self.crit), _scale(FIXED_DEALT, 1.0, self.crit))
            spear = max(spear, _scale(s_dealt, s, False))
        return replace(self, nail=max(nail, self.floor_nail), spear=max(spear, self.floor_spear), scaling=smax)

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
        extra = {"floor_nail": float(dmg)} if k == "nail" else {"floor_spear": float(dmg)} if k == "spear" else {}
        return replace(self, **{k: float(dmg)}, **extra, raised=tuple(sorted({*self.raised, k})))
