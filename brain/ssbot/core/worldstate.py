"""WorldState schema v2 (DESIGN §4.1-4.2): the one world model every brain module reads, whichever backend made it.

Backends: OracleBackend (training, exact), DegradedOracleBackend (= OracleBackend -> ObservabilityFilter -> SimpleNoise
-> DelayLine, the simulated final path of §3.9.2) and, from M3, VisionBackend. Conventions (§4.1): world units u of
the current scene (+x right, +y up, positions are collider centres), seconds, QPC nanoseconds, damage in masks.
Estimated values are wrapped in E (value, sigma, calibrated confidence, source, age).

Observability is machine-readable: every field carries metadata["obs"] = V (vision provides it), O (oracle only; None
in a VISION_EQUIVALENT view) or D (derived by shared code from V fields). Fields that hold an exact timer in the oracle
path also carry metadata["timer"] = True; the ObservabilityFilter sets those to None until the vision-side timer
models exist (§3.9.2 "精确计时器 -> 模型估计"). Event kinds carry their own observability in EVENT_OBS, and event
payloads mark their fields the same way.

    ws.view("VISION_EQUIVALENT")    # copy with every O field None and O-only events removed
    observability(HeroState)        # {"pos": "V", ..., "can": "O"}

Deviations from the §4.2 text, all additive: CameraPose.viewport/screen (needed to project into the image),
Game.unobservable is an Unobs bit set, Event payloads are typed dataclasses, Ev.SCENE_LEAVE / HAZARD_RESPAWN /
DAMAGE_BLOCKED / FREEZE.phase exist because the oracle reports them. Wire format: msgspec is not installed (2026-10),
so these are dataclasses(slots=True); the C# side does not mirror them (the oracle sends STATE dicts, the backend maps).
"""
import math
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from enum import Enum, IntEnum, IntFlag, StrEnum
from typing import Any, Iterator

SCHEMA_VERSION = 2

V, O, D = "V", "O", "D"
OBS = "obs"
TIMER = "timer"

ORACLE, VISION_EQUIVALENT = "ORACLE", "VISION_EQUIVALENT"
PROFILES = (ORACLE, VISION_EQUIVALENT)

Vec2 = tuple[float, float]
Poly = list[Vec2]

BIND_SILK = 9          # a bind takes the full 9-silk spool (Bind FSM; ssbot.train.data_policy binds only with 9)


def fld(obs: str, default: Any = MISSING, *, factory: Any = MISSING, timer: bool = False) -> Any:
    """A dataclass field tagged with its observability (V/O/D) and, for exact timers, timer=True."""
    md = {OBS: obs, TIMER: True} if timer else {OBS: obs}
    if factory is not MISSING:
        return field(default_factory=factory, metadata=md)
    if default is not MISSING:
        return field(default=default, metadata=md)
    return field(metadata=md)


# ---- enums (§4.2) ---------------------------------------------------------------------------------------------

class Src(IntEnum):
    ORACLE = 0
    VISION = 1
    DB = 2
    LEDGER = 3
    PREDICTED = 4
    EVENT = 5
    AUDIT = 6
    UNKNOWN = 7


class Screen(IntEnum):
    PLAYING = 0
    PLAYING_HUD_HIDDEN = 1
    DIALOG = 2
    ITEM_POPUP = 3
    AREA_TITLE = 4
    BENCH = 5
    SHOP = 6
    BELLWAY_MAP = 7
    INVENTORY = 8
    QUICK_MAP = 9
    PAUSE_MENU = 10
    MAIN_MENU = 11
    SAVE_SELECT = 12
    MODE_SELECT = 13
    FADE = 14
    TRANSITION = 15
    CUTSCENE_VIDEO = 16
    DEATH = 17
    ENDING = 18
    CREDITS = 19
    FOREIGN_WINDOW = 20
    MSG_CANVAS = 21          # SAVE_FAILED and other modal GenericMessageCanvas dialogs
    UNKNOWN = 31


class PauseBlock(IntFlag):
    """Why a Pause press would be dropped now (PAUSE_LOCKOUT = !InputHandler.PauseAllowed: the 0.3 s real-time
    lockout after every pause/unpause, HUDCamera's 0.5 s, ReturnToMainMenu; m0:C12, N14). DISABLE_SAVEQUIT and
    PRELOAD_PENDING do not block pausing, only Save & Quit (greyed, or refused: m0:C8, §2.4)."""
    DISABLE_PAUSE = 1
    TIME_SLOWED = 2
    PAUSE_LOCKOUT = 4
    MSG_CANVAS = 8
    BLOCKING_INTERACT = 16
    NOT_ACCEPTING_INPUT = 32
    DISABLE_SAVEQUIT = 64
    PRELOAD_PENDING = 128
    FOCUS_LOST = 256
    GAME_STATE_NOT_PLAYING = 512


PAUSE_ONLY = PauseBlock(PauseBlock.DISABLE_SAVEQUIT | PauseBlock.PRELOAD_PENDING)   # bits that do not block a pause


class Kind(IntEnum):
    ENEMY = 0
    BOSS = 1
    PROJECTILE = 2
    ENEMY_ATTACK = 3
    HAZARD_DYN = 4
    HERO_ATTACK = 5
    PICKUP = 6
    NPC = 7
    BREAKABLE = 8
    LEVER = 9
    PLATFORM_MOVING = 10
    HOOK = 11
    HELPER = 12
    UNKNOWN = 15


class Hazard(IntEnum):
    """PIT goes through i-frames and SINK always applies (§1.5, §3.3.1 [m0:N1]); OTHER is the fallback only."""
    ENEMY = 0
    SPIKES = 1
    ACID = 2
    LAVA = 3
    COAL = 4
    COAL_SPIKES = 5
    ZAP = 6
    STEAM = 7
    RESPAWN_PIT = 8
    EXPLOSION = 9
    NON_HAZARD = 10
    COG = 11
    PIT = 12
    SINK = 13
    OTHER = 15


class FM(IntEnum):
    """Fractured Mask; UNKNOWN is treated as BROKEN."""
    NOT_EQUIPPED = 0
    INTACT = 1
    BROKEN = 2
    UNKNOWN = 3


class Unobs(IntFlag):
    """Game.unobservable: which parts of this WorldState are estimates standing in for oracle-exact values."""
    HP_FROM_HITS = 1          # Entity.hp_est from counted hits
    PHASE_FROM_TABLE = 2      # Entity.phase from the observable-phase table, not the FSM
    OFFSCREEN_HIDDEN = 4      # entities outside the image dropped; memory tracks kept
    TIMERS_DROPPED = 8        # exact timers set to None
    PLAYTIME_WALL = 16        # PlayTimeEst.live_s advanced by the wall clock
    NOISE = 32                # SimpleNoise applied
    DELAYED = 64              # DelayLine applied


# ---- E[T] ---------------------------------------------------------------------------------------------------

@dataclass(slots=True)
class E[T]:
    v: T
    sigma: float = 0.0
    conf: float = 1.0
    src: Src = Src.ORACLE
    age_ms: float = 0.0


def unknown[T](v: T, sigma: float = 0.0) -> E[T]:
    """A placeholder value nobody measured (conf 0)."""
    return E(v, sigma=sigma, conf=0.0, src=Src.UNKNOWN)


# ---- records (§4.2) -----------------------------------------------------------------------------------------

@dataclass(slots=True)
class Stamp:
    frame: int = fld(V, 0)
    t_sample_qpc_ns: int = fld(V, 0)
    t_pub_qpc_ns: int = fld(V, 0)
    t_game_s: float = fld(D, 0.0)          # advances at 0 rate through freezes and pauses (sum of scaled dt)
    backend: str = fld(V, "")
    config_fp: str = fld(V, "")


@dataclass(slots=True)
class MenuRead:                             # V: templates + OCR; O path: UI state
    cursor_item: str | None = fld(V, None)
    quit_greyed: bool | None = fld(V, None)
    slot_index: int | None = fld(V, None)
    slot_playtime_s: float | None = fld(V, None)
    slot_location: str | None = fld(V, None)
    slot_steel_soul: bool | None = fld(V, None)
    forbidden_highlight: bool = fld(V, False)   # Restore / Clear highlighted
    mode_has_steel_soul: bool | None = fld(V, None)


@dataclass(slots=True)
class PlayTimeEst:
    live_s: float = fld(V, 0.0)             # GameManager.PlayTime (O path exact; V path: wall clock since calibration)
    sigma_s: float = fld(D, 0.0)
    counting: bool = fld(D, False)
    last_calib_s: float | None = fld(D, None)
    saved_s: float | None = fld(O, None)    # playerData.playTime (last flush; what the achievement check reads)


@dataclass(slots=True)
class Game:
    screen: E[Screen] = fld(V, factory=lambda: unknown(Screen.UNKNOWN))
    menu: MenuRead | None = fld(V, None)
    game_state: int | None = fld(O, None)
    scene: E[str] = fld(V, factory=lambda: unknown(""))
    scene_variant: E[str] = fld(V, factory=lambda: unknown(""))
    entry_gate: str | None = fld(D, None)
    transitioning: bool = fld(V, False)
    memory_scene: bool | None = fld(O, None)            # IsMemoryScene(): death not fatal (to confirm)
    pause_available: E[bool] = fld(V, factory=lambda: unknown(False))   # V: quit map + freeze detection; O: exact
    quit_available: E[bool] = fld(V, factory=lambda: unknown(False))
    pause_blockers: int = fld(D, 0)                     # PauseBlock bits (V: inferred)
    unpause_lockout_until_s: float = fld(D, 0.0)        # QPC seconds: 0.3 s real time after each pause / unpause
    focus_ok: bool = fld(V, True)
    permadeath_mode: int | None = fld(O, None)          # V: slot check + HUD skin
    play_time: PlayTimeEst = fld(V, factory=PlayTimeEst)
    unobservable: int = fld(D, 0)                       # Unobs bits


@dataclass(slots=True)
class CameraPose:
    x: float = fld(V, 0.0)
    y: float = fld(V, 0.0)
    z: float = fld(V, 0.0)
    fov: float = fld(V, 0.0)
    V: tuple[float, ...] | None = fld(D, None)          # worldToCamera, 16 floats column-major (ssbot.tools.projector)
    P: tuple[float, ...] | None = fld(D, None)          # projection, same layout
    # the field V above shadows the tag V in the rest of this class body: spell the tag out
    sigma_xy: float = fld(D, 0.0)
    reliable: bool = fld(D, False)
    src: Src = fld("V", Src.UNKNOWN)
    viewport: tuple[float, float, float, float] = fld("V", (0.0, 0.0, 1.0, 1.0))   # normalised rect x, y, w, h
    screen: tuple[float, float] | None = fld("V", None)   # image size in pixels


@dataclass(slots=True)
class PhasePost:
    topk: list[tuple[str, float]] = fld(D, factory=list)
    t_in_phase: float = fld(D, 0.0)
    ttd_mean: float = fld(D, math.nan)
    ttd_p05: float = fld(D, math.nan)
    support_region: list[Vec2] | None = fld(D, None)                                  # safety
    prob_regions: list[tuple[list[Vec2], float, float, float]] = fld(D, factory=list)   # (poly, t_on, t_off, p)

    @property
    def top(self) -> str | None:
        return self.topk[0][0] if self.topk else None


@dataclass(slots=True)
class HeroState:
    pos: E[Vec2] = fld(V, factory=lambda: unknown((0.0, 0.0)))
    vel: E[Vec2] = fld(V, factory=lambda: unknown((0.0, 0.0)))
    facing: E[int] = fld(V, factory=lambda: unknown(1))
    hurtbox: list[Vec2] = fld(V, factory=list)
    contact: E[str] = fld(V, factory=lambda: unknown("AIR"))      # GROUND|WALL_L|WALL_R|AIR|WATER|HAZARD
    mode: E[str] = fld(V, factory=lambda: unknown("air"))         # ground|air|wall|dash|glide|attack|pogo|bind|hurt|
    #                                                                recoil|bench|cutscene
    iframes_left: E[float] | None = fld(D, None, timer=True)
    recoil_left: E[float] | None = fld(D, None, timer=True)
    dash_cd_left: E[float] | None = fld(D, None, timer=True)
    action_lock_left: E[float] | None = fld(D, None, timer=True)
    binding: E[str] = fld(V, factory=lambda: unknown("NONE"))     # NONE|IN_PROGRESS|INTERRUPTED|DONE
    committed_primitive: tuple[str, int] | None = fld(D, None)    # (primitive, hold frames left)
    can: dict[str, bool] | None = fld(O, None)


@dataclass(slots=True)
class ToolSlot:
    tool_id: str = fld(V, "")
    ammo: E[int] = fld(V, factory=lambda: unknown(0))
    ammo_max: int = fld(V, 0)


@dataclass(slots=True)
class Resources:
    hp: E[int] = fld(V, factory=lambda: unknown(0))
    hp_max: E[int] = fld(V, factory=lambda: unknown(0))
    blue: E[int] = fld(V, factory=lambda: unknown(0))
    silk: E[int] = fld(V, factory=lambda: unknown(0))
    silk_max: E[int] = fld(V, factory=lambda: unknown(0))    # CurrentSilkMax (broken spool 9, cursed 3)
    silk_hearts: int = fld(V, 0)
    bind_ready: E[bool] = fld(D, factory=lambda: unknown(False))
    fractured_mask: E[FM] = fld(V, factory=lambda: unknown(FM.UNKNOWN))
    magma_ready: E[bool] | None = fld(V, None)
    pending_dmg: E[int] = fld(D, factory=lambda: unknown(0))  # remaining damage of attached DamageTags + frost clock
    status: frozenset[str] = fld(V, frozenset())                # ACID, FLAME, GRIND, FROST, ...
    crest: E[str] = fld(V, factory=lambda: unknown(""))        # from the inventory audit only (Src.AUDIT)
    equipped: list[str] = fld(V, factory=list)
    tools: list[ToolSlot] = fld(V, factory=list)
    rosaries: E[int] = fld(V, factory=lambda: unknown(0))
    shell_shards: E[int] = fld(V, factory=lambda: unknown(0))
    craftmetal: E[int] = fld(V, factory=lambda: unknown(0))
    lockets_free: int = fld(V, 0)


@dataclass(slots=True)
class DamageBox:
    poly: list[Vec2] = fld(D, factory=list)
    active: bool = fld(D, False)
    dmg_seq: tuple[int, ...] = fld(D, ())
    hazard: Hazard = fld(D, Hazard.OTHER)
    flags: frozenset[str] = fld(D, frozenset())   # PARRYABLE DEFLECTABLE COUNTER FLAME VOID MASK_BYPASS IGNORES_IFRAMES
    #                                               IGNORES_PARRY FIRST_NO_MASK CRITICAL GRAB TAG_ACID NON_LETHAL
    #                                               AMOUNT_FSM (the amount is known only to an FSM)


@dataclass(slots=True)
class Entity:
    id: int = fld(V, 0)
    kind: Kind = fld(V, Kind.UNKNOWN)
    type_key: E[str] = fld(V, factory=lambda: unknown(""))
    pos: E[Vec2] = fld(V, factory=lambda: unknown((0.0, 0.0)))
    vel: E[Vec2] = fld(V, factory=lambda: unknown((0.0, 0.0)))
    acc: Vec2 = fld(D, (0.0, 0.0))
    facing: E[int] = fld(V, factory=lambda: unknown(1))
    body_polys: list[list[Vec2]] = fld(V, factory=list)
    dmg_boxes: list[DamageBox] = fld(D, factory=list)
    phase: PhasePost | None = fld(D, None)          # A-class bosses / arena enemies only
    keepout: list[Vec2] | None = fld(D, None)       # ordinary enemies: reach union from the tables
    hp_est: E[float] | None = fld(D, None)
    fsm: list[tuple[str, str, float]] | None = fld(O, None)   # (fsm, state, game time in state)
    visible_frac: float = fld(V, 1.0)
    last_seen_ms: float = fld(V, 0.0)


@dataclass(slots=True)
class Threat:                                        # D: both backends share the code that fills it
    id: int = fld(D, 0)
    source_id: int | None = fld(D, None)
    kind: str = fld(D, "")                           # enemy_body|attack|projectile|hazard|grab|cog|tag
    shape: list[Vec2] = fld(D, factory=list)
    swept: list[tuple[float, list[Vec2]]] = fld(D, factory=list)
    motion: str = fld(D, "")
    params: list[float] = fld(D, factory=list)
    vel: Vec2 = fld(D, (0.0, 0.0))
    acc: Vec2 = fld(D, (0.0, 0.0))
    t_on: float = fld(D, 0.0)
    t_off: float = fld(D, 0.0)
    dmg_seq: tuple[int, ...] = fld(D, ())
    hazard: Hazard | None = fld(D, None)
    flags: frozenset[str] = fld(D, frozenset())
    in_support: bool = fld(D, False)
    p: float = fld(D, 0.0)
    conf: float = fld(D, 0.0)
    t_hit_hero: E[float] = fld(D, factory=lambda: unknown(math.inf))


@dataclass(slots=True)
class PerceptionHealth:
    frame_age_ms: float = fld(V, 0.0)
    dropped_frames: int = fld(V, 0)
    flash: bool = fld(V, False)
    torn: bool = fld(V, False)
    fx_density: float = fld(V, 0.0)
    conf: dict[str, float] = fld(V, factory=dict)


@dataclass(slots=True)
class TerrainRef:
    scene: str = fld(V, "")
    variant: str = fld(V, "")
    db_version: str = fld(V, "")
    dynamic_deltas: list[tuple[str, bool]] = fld(V, factory=list)


# ---- events (§4.2 "事件") -------------------------------------------------------------------------------------

class Ev(StrEnum):
    # combat
    HIT_TAKEN = "HIT_TAKEN"
    HIT_DEALT = "HIT_DEALT"
    ENEMY_KILLED = "ENEMY_KILLED"
    PARRY = "PARRY"
    CLASH = "CLASH"
    BIND_START = "BIND_START"
    BIND_DONE = "BIND_DONE"
    BIND_BROKEN = "BIND_BROKEN"
    FREEZE = "FREEZE"
    STATUS_TAG = "STATUS_TAG"
    DAMAGE_BLOCKED = "DAMAGE_BLOCKED"       # contacts during i-frames (oracle only)
    # behaviour
    FSM_TRANSITION = "FSM_TRANSITION"
    # progress
    SCENE_ENTER = "SCENE_ENTER"
    SCENE_LEAVE = "SCENE_LEAVE"
    HAZARD_RESPAWN = "HAZARD_RESPAWN"
    ITEM = "ITEM"
    PURCHASE = "PURCHASE"
    BENCH_REST = "BENCH_REST"
    SAVE_OBSERVED = "SAVE_OBSERVED"
    INTERACTION = "INTERACTION"
    # pause / quit
    PAUSE_ON = "PAUSE_ON"
    PAUSE_OFF = "PAUSE_OFF"
    PAUSE_BLOCKED = "PAUSE_BLOCKED"
    DISABLE_PAUSE_ON = "DISABLE_PAUSE_ON"
    DISABLE_PAUSE_OFF = "DISABLE_PAUSE_OFF"
    DISABLE_SAVEQUIT_ON = "DISABLE_SAVEQUIT_ON"
    DISABLE_SAVEQUIT_OFF = "DISABLE_SAVEQUIT_OFF"
    QUIT_BLOCKED = "QUIT_BLOCKED"
    # anomalies
    CATASTROPHE = "CATASTROPHE"
    WOULD_DIE = "WOULD_DIE"
    GUARD_TRIPPED = "GUARD_TRIPPED"
    PERCEPTION_LOST = "PERCEPTION_LOST"
    FOCUS_LOST = "FOCUS_LOST"
    WORLD_MISMATCH = "WORLD_MISMATCH"
    FORCED_RISK = "FORCED_RISK"
    OVERLAY_INTRUSION = "OVERLAY_INTRUSION"
    STUCK = "STUCK"
    CAPTURED = "CAPTURED"


# Which event kinds a vision path can report at all (O kinds are removed from a VISION_EQUIVALENT view).
EVENT_OBS: dict[Ev, str] = {k: V for k in Ev} | {
    Ev.DAMAGE_BLOCKED: O, Ev.FSM_TRANSITION: O, Ev.DISABLE_PAUSE_ON: O, Ev.DISABLE_PAUSE_OFF: O,
    Ev.DISABLE_SAVEQUIT_ON: O, Ev.DISABLE_SAVEQUIT_OFF: O, Ev.CATASTROPHE: O, Ev.WOULD_DIE: O, Ev.GUARD_TRIPPED: O,
    Ev.PAUSE_BLOCKED: D, Ev.PERCEPTION_LOST: D, Ev.WORLD_MISMATCH: D, Ev.FORCED_RISK: D, Ev.STUCK: D,
}


@dataclass(slots=True)
class HitTaken:
    amount: int = fld(V, 0)                       # masks lost, as the HUD shows them
    hazard: Hazard = fld(D, Hazard.OTHER)
    source_type: str | None = fld(D, None)        # entity type_key when it could be resolved, else the object path
    source_id: int | None = fld(D, None)
    caller_path: str | None = fld(O, None)        # the game object path or the C# method that dealt it


@dataclass(slots=True)
class HitDealt:
    target_id: int = fld(V, 0)
    type_key: str = fld(V, "")
    amount: float | None = fld(O, None)           # vision sees the hit flash, not the damage
    hp_after: float | None = fld(O, None)


@dataclass(slots=True)
class EnemyKilled:
    target_id: int = fld(V, 0)
    type_key: str = fld(V, "")


@dataclass(slots=True)
class Freeze:
    phase: str = fld(V, "start")                  # start | end
    profile: str | None = fld(O, None)            # FreezeMomentTypes name or the direct caller
    duration_s: float | None = fld(D, None)       # on "end": real time it lasted


@dataclass(slots=True)
class FsmTransition:
    enemy_id: int | None = fld(O, None)           # entity root iid
    type_key: str | None = fld(O, None)
    fsm: str | None = fld(O, None)
    from_state: str | None = fld(O, None)         # None on a start / restart
    to_state: str | None = fld(O, None)
    hero_rel_pos: Vec2 | None = fld(O, None)      # entity pos - hero pos at the transition (None if never seen)
    t_in_prev: float | None = fld(O, None)        # StateTime of from_state (scaled)


@dataclass(slots=True)
class SceneEnter:
    scene: str = fld(V, "")
    gate: str | None = fld(D, None)
    planned: bool | None = fld(D, None)


@dataclass(slots=True)
class SceneLeave:
    scene: str | None = fld(V, None)
    next_scene: str | None = fld(D, None)


@dataclass(slots=True)
class Lethal:                                     # CATASTROPHE and WOULD_DIE (LethalBlock)
    path: str | None = fld(O, None)               # damage | special | die | ...
    blocked: bool | None = fld(O, None)           # the lethal outcome was cancelled (training)
    amount: int | None = fld(O, None)
    hazard: Hazard | None = fld(O, None)
    source: str | None = fld(O, None)


@dataclass(slots=True)
class GateEdge:                                   # DISABLE_PAUSE_ON/OFF, DISABLE_SAVEQUIT_ON/OFF
    gate: str | None = fld(O, None)
    value: bool | None = fld(O, None)
    writer: str | None = fld(O, None)


@dataclass(slots=True)
class BindOutcome:
    hp_before: int = fld(V, 0)
    hp_after: int = fld(V, 0)


@dataclass(slots=True)
class Info:                                       # anything else the oracle reported, kept verbatim
    d: dict | None = fld(O, None)


@dataclass(slots=True)
class Event:
    kind: Ev = fld(V, Ev.PERCEPTION_LOST)
    frame: int = fld(V, 0)
    t_game_s: float = fld(D, 0.0)
    data: Any = fld(V, None)                      # payload dataclass; its fields carry their own observability


# ---- the world state ------------------------------------------------------------------------------------------

@dataclass(slots=True)
class WorldState:
    stamp: Stamp = fld(V, factory=Stamp)
    game: Game = fld(V, factory=Game)
    cam: CameraPose = fld(V, factory=CameraPose)
    hero: HeroState = fld(V, factory=HeroState)
    res: Resources = fld(V, factory=Resources)
    entities: list[Entity] = fld(V, factory=list)
    threats: list[Threat] = fld(D, factory=list)
    terrain: TerrainRef = fld(V, factory=TerrainRef)
    world_flags: dict[str, E[bool]] = fld(D, factory=dict)
    events: list[Event] = fld(V, factory=list)
    ledger_rev: int = fld(D, 0)
    perception: PerceptionHealth = fld(V, factory=PerceptionHealth)

    def view(self, profile: str) -> "WorldState":
        """ORACLE: self. VISION_EQUIVALENT: a copy with every O field None, O-only events dropped and O payload
        fields None. Only the schema-level projection: replacing exact values in V/D fields by vision-equivalent
        estimates (hp from hits, phases from tables, off-screen entities, timers, playTime) is the
        ObservabilityFilter's job (ssbot.backends.observability)."""
        if profile == ORACLE:
            return self
        if profile != VISION_EQUIVALENT:
            raise ValueError(f"unknown profile {profile!r} (expected one of {PROFILES})")
        return strip_o(self)


# ---- observability tables and the generic O stripper ---------------------------------------------------------

_SPEC: dict[type, tuple[tuple[str, str, bool], ...]] = {}


def _spec(cls: type) -> tuple[tuple[str, str, bool], ...]:
    """(name, obs, is_timer) per field; fields without a tag (E's own v/sigma/...) count as V."""
    s = _SPEC.get(cls)
    if s is None:
        s = _SPEC[cls] = tuple((f.name, f.metadata.get(OBS, V), bool(f.metadata.get(TIMER))) for f in fields(cls))
    return s


def observability(cls: type) -> dict[str, str]:
    return {name: obs for name, obs, _ in _spec(cls)}


def timer_fields(cls: type) -> tuple[str, ...]:
    return tuple(name for name, _, t in _spec(cls) if t)


SCHEMA_CLASSES: tuple[type, ...] = (
    Stamp, MenuRead, PlayTimeEst, Game, CameraPose, PhasePost, HeroState, ToolSlot, Resources, DamageBox, Entity,
    Threat, PerceptionHealth, TerrainRef, WorldState, Event, HitTaken, HitDealt, EnemyKilled, Freeze, FsmTransition,
    SceneEnter, SceneLeave, Lethal, GateEdge, BindOutcome, Info)

_ATOMS = (int, float, str, bool, bytes, Enum, frozenset, type(None))


def strip_o(obj: Any) -> Any:
    """Deep copy of obj with O fields None (dataclasses recursively, inside lists, tuples and dicts); events whose
    kind is O in EVENT_OBS are dropped."""
    if isinstance(obj, _ATOMS):
        return obj
    if is_dataclass(obj):
        cls = type(obj)
        kw = {}
        for name, obs, _ in _spec(cls):
            if obs == O:
                kw[name] = None
            elif name == "events" and cls is WorldState:
                kw[name] = [strip_o(e) for e in obj.events if EVENT_OBS.get(e.kind, V) != O]
            else:
                kw[name] = strip_o(getattr(obj, name))
        return cls(**kw)
    if isinstance(obj, list):
        return [strip_o(x) for x in obj]
    if isinstance(obj, tuple):
        return obj if not obj or isinstance(obj[0], (int, float, str)) else tuple(strip_o(x) for x in obj)
    if isinstance(obj, dict):
        return {k: strip_o(v) for k, v in obj.items()}
    return obj


def iter_fields(obj: Any, path: str = "") -> Iterator[tuple[str, str, bool, Any]]:
    """(path, obs, is_timer, value) for every tagged field reachable from obj, depth first."""
    if is_dataclass(obj) and not isinstance(obj, type):
        for name, obs, timer in _spec(type(obj)):
            v = getattr(obj, name)
            p = f"{path}.{name}" if path else name
            yield p, obs, timer, v
            yield from iter_fields(v, p)
    elif isinstance(obj, (list, tuple)):
        for i, x in enumerate(obj):
            if is_dataclass(x):
                yield from iter_fields(x, f"{path}[{i}]")
    elif isinstance(obj, dict):
        for k, x in obj.items():
            if is_dataclass(x):
                yield from iter_fields(x, f"{path}[{k!r}]")
