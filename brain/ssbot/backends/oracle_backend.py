"""OracleBackend: the oracle's STATE stream -> WorldState, one STATE at a time (DESIGN §4.2, §4.5; training only).

    backend = OracleBackend(bosses=[BELL_BEAST], cstate_names=link.rpc("schema.cstate")["bools"])
    for s in RecordingReader(path).states():
        ws = backend.feed(s)

Live, OracleLink.subscribe_state sees every STATE on the reader thread; give the backend a queue:

    q = queue.SimpleQueue(); link.subscribe_state(q.put)
    backend = OracleBackend(source=q.get); ws = backend.step()

Positions (§4.1, the shared reference): HeroState.pos is the hurtbox centre (hero.box = HeroController.Bounds; live
Bell Beast run 20261001_122249, 2.15 M STATEs: 0.17-0.84 u below the transform from max to p1, mean 0.51 u, up to
3.9 u in the rest). Entity.pos is the centre of the main body collider: the collider
named like the entity root when the oracle exports collider names (the root's own collider), else the first exported
collider (GetComponentsInChildren lists the root's colliders first, and EntityExporter always exports root colliders,
disabled or not); with no collider, the render_aabb centre; else the transform. Live run: the Bell Beast's first
collider is its root box in 918,108 of 932,222 exported frames, whose centre is 0.68-4.01 u from the transform (mean
2.27 u); the rest are its first emergence after a savestate load (9,799 frames with no collider, then 4,315 with only
the charge polygon: the exporter's collider cache catching up), where only collider names tell the root box apart.
The transforms are kept as pos_transform (O).

feed() must see every STATE in order: events ride on the STATE of their frame (a dropped STATE takes its events with
it; the gap shows in perception.dropped_frames), and these fields need memory:
  - Stamp.t_game_s: sum of the scaled dt, so it stands still through freezes and pauses (dt is 0 there).
  - Game.unpause_lockout_until_s: 0.3 s real time (QPC) after every pause/unpause edge (m0:C12).
  - HeroState timers: exact from the oracle's hero.tm when it is exported (inv, recoil, dash_cd, atk_cd). Without it,
    from cState edges plus the prefab constants (docs/facts/<build>/hero_constants.json): iframes_left =
    INVUL_TIME - game time since cState.invulnerable rose, which is how HeroController.Invulnerable() counts (scaled
    deltaTime; trial run: the sum of dt from rise to fall is 0.992 s for 96 of 98 rises after a hit); recoil_left =
    RECOIL_DURATION from cState.recoiling (measured 0.200-0.217 s); dash_cd_left = DASH_COOLDOWN from a dash start,
    0 exactly when can.dash is true (CanDash needs dashCooldownTimer <= 0), and conf 0.5 when can.dash is false with
    no dash in the last DASH_COOLDOWN (the timer has other writers: shuttlecock 0.1, short pogo 0.1, wall jump
    0.05, HeroController.cs:7792, 4610, 8787); action_lock_left = what is left of the attack/throw clip.
  - Entity velocity by finite difference when the entity has no rigidbody (vel nil), acceleration always so.
  - Entity kind holds PROJECTILE for PROJECTILE_HOLD_S after the projectile src bit was last seen. The bit is
    "no HealthManager and a dynamic Rigidbody2D or the PROJECTILES layer" (EntityRegistry.cs:726), evaluated when
    the oracle's entity cache refreshes: on the trial run "BoneBeast AtkBell L" carries it in 3917 of 5918 frames
    in runs of p50 176 frames, with gaps of p50 86 frames (a bell resting between throws); falling DropBells carry
    it while they fall. Kind follows the bit with a short hold instead of keeping it for the episode.
  - HIT_DEALT: from the oracle's "hit" events when the stream has them (killing blows and hits on unexported enemies
    included; ENEMY_KILLED on dead). Older recordings: from enemy HP drops between consecutive STATEs (every Hunter
    nail hit on the Bell Beast took 5 HP: 56 of 56 drops on the trial run; the killing blow shows no drop because the
    boss leaves "ents" in the frame its Control FSM enters "Death Broadcast", so ENEMY_KILLED also comes from the
    BossSpec death states or is_dead rising).
  - HIT_TAKEN.amount: masks lost (health + blue): the TakeHealth "hp" event that follows the "damage" event, or for
    a lethal hit LethalBlock cancelled, the catastrophe / would_die "dmg"; the raw TakeDamage argument is amount_raw
    (O). Trial run: 8 hits took 2 masks, 91 lethal hits were cancelled (dmg 2), 2 hits during a bind took none;
    live run: 8,345 of 8,461 hits 2 masks, 116 none.
  - Bind outcome: DONE when the hero "spell" FSM reached "Bind Burst" during isBinding (trial run: Bind Air ->
    Binding -> Bind Burst -> Cooldown in all 4 binds), or HP rose; else BROKEN. Live run: 36 DONE (+3 masks each),
    17 BROKEN (HP unchanged).
  - HitDealt.hero_anim: the hero's animation clip at the hit, or while the hero is hurt the clip before the hurt (a
    spear still in flight when the hero is hit lands during "Stun"), so the vision path can price a hit by what the
    bot did. Live run: all 460 hits carrying "NeedleThrow Throwing" (the Silk Spear) took 15 HP, the other 4,081 took
    5 HP.
  - FSM_TRANSITION.hero_rel_pos and the time in the current FSM state (game time since the transition event; the
    exported StateTime stops once a state's actions have finished).

Cost per STATE on the live run (2.15 M STATEs, 13900K, two processes in parallel): p50 95-96 us, p99 172-186 us.

Contact and mode come from the cState bits (field order: RPC "schema.cstate", or the facts copy cstate_schema.json).
The wall side comes from hero.wall [touchingWallL, touchingWallR] when exported; without it, from the facing when
wall sliding or clinging (BeginWallSlide faces the wall, HeroController.cs:8468-8479), and from the facing with conf
0.5 when the hero only touches a wall (collision sets touchingWallL/R regardless of facing, cs:11487-11499).
DamageBox flags IGNORES_IFRAMES / IGNORES_PARRY follow HeroController.TakeDamage (worldstate.IFRAME_BLOCKED,
PARRY_BLOCKED); cog sources are Hazard.COG, which goes through both.
"""
import functools
import json
import math
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ssbot.core.bosses import BossSpec
from ssbot.core.worldstate import (BIND_SILK, FM, IFRAME_BLOCKED, PARRY_BLOCKED, BindOutcome, CameraPose, DamageBox, E,
                                   Entity, EnemyKilled, Ev, Event, Freeze, FsmTransition, Game, GateEdge, Hazard,
                                   HeroState, HitDealt, HitTaken, Info, Kind, Lethal, MenuRead, PauseBlock,
                                   PerceptionHealth, PhasePost, PlayTimeEst, Resources, SceneEnter, SceneLeave, Screen,
                                   Src, Stamp, TerrainRef, ToolSlot, WorldState, unknown)
from ssbot.ipc.ents import DAMAGE_FLAGS, HAZARD_TYPES, PARRY_BITS, PARRYABLE, SRC_BITS, is_threat

BUILD = "1.0.30000"
FACTS = Path(__file__).resolve().parents[3] / "docs" / "facts"
QPC_FREQ = 10_000_000              # HELLO "qpc_freq" on this machine
PAUSE_LOCKOUT_S = 0.3              # WaitForSecondsRealtime(0.3f) after PauseGameToggle (m0:C12)
FRAME_S = 1.0 / 60.0
MAX_GAP_FRAMES = 30                # a longer gap in the STATE stream (reconnect, recording cut) resets entity memory
PROJECTILE_HOLD_S = 0.25           # game time a PROJECTILE kind outlives the last frame with the projectile bit

# Prefab values (docs/facts/1.0.30000/hero_constants.json, probe P11); the file wins when it is there.
HERO_DEFAULTS = {"INVUL_TIME": 1.0, "INVUL_TIME_PARRY": 0.15, "RECOIL_DURATION": 0.2, "DASH_COOLDOWN": 0.425}

# GlobalEnums.GameState / UIState / MainMenuState / ActorStates (decompiled 1.0.30000)
GS_MAIN_MENU, GS_LOADING, GS_ENTERING, GS_PLAYING, GS_PAUSED, GS_EXITING, GS_CUTSCENE = 1, 2, 3, 4, 5, 6, 7
UI_MAIN_MENU_HOME = 1
MENU_SAVE_PROFILES, MENU_PAUSE, MENU_PLAY_MODE = 6, 17, 18
ACTOR_NO_INPUT = 7

# Oracle "pause.blk" bits (Input/PauseGate.cs) -> PauseBlock
_BLK_MAP = ((1, PauseBlock.DISABLE_PAUSE), (2, PauseBlock.TIME_SLOWED), (4, PauseBlock.PAUSE_LOCKOUT),
            (8, PauseBlock.MSG_CANVAS), (16, PauseBlock.BLOCKING_INTERACT), (32, PauseBlock.NOT_ACCEPTING_INPUT),
            (64, PauseBlock.GAME_STATE_NOT_PLAYING), (128, PauseBlock.GAME_STATE_NOT_PLAYING))
BLK_DISABLE_PAUSE = 1

HAZARD_OF: dict[str, Hazard] = {n: Hazard[n] if n in Hazard.__members__ else Hazard.OTHER for n in HAZARD_TYPES}
BIND_DONE_STATES = frozenset(("Bind Burst",))      # hero "spell" FSM: the heal is applied in this state

_CS = ("onGround", "touchingWall", "wallSliding", "wallClinging", "wallScrambling", "swimming", "hazardDeath",
       "hazardRespawning", "dead", "dashing", "airDashing", "backDashing", "superDashing", "shadowDashing", "floating",
       "attacking", "upAttacking", "downAttacking", "downSpikeAntic", "downSpiking", "downSpikeBouncing",
       "downSpikeBouncingShort", "bouncing", "shroomBouncing", "isBinding", "recoiling", "recoilFrozen",
       "recoilingLeft", "recoilingRight", "recoilingDrill", "isToolThrowing", "casting", "parrying",
       "invulnerable", "inAcid", "isFrosted", "isMaggoted", "transitioning", "isInCutsceneMovement", "nailCharging")
_DASH = ("dashing", "airDashing", "backDashing", "superDashing", "shadowDashing")
_POGO = ("downSpikeBouncing", "downSpikeBouncingShort", "bouncing", "shroomBouncing")
_ATTACK = ("attacking", "upAttacking", "downAttacking", "downSpikeAntic", "downSpiking", "isToolThrowing", "casting",
           "parrying", "nailCharging")
_NAIL_RECOIL = ("recoilingLeft", "recoilingRight", "recoilingDrill")
_STATUS = (("inAcid", "ACID"), ("isFrosted", "FROST"), ("isMaggoted", "MAGGOTED"))


def load_facts(name: str, build: str = BUILD) -> dict | None:
    p = FACTS / build / name
    return json.loads(p.read_text("utf-8")) if p.is_file() else None


def cstate_names_from_facts(build: str = BUILD) -> list[str]:
    facts = load_facts("cstate_schema.json", build)
    if not facts:
        raise FileNotFoundError(f"{FACTS / build / 'cstate_schema.json'} missing: pass cstate_names from RPC "
                                f"schema.cstate")
    return list(facts["bools"])


def hero_constants(build: str = BUILD) -> dict[str, float]:
    facts = load_facts("hero_constants.json", build) or {}
    hero = facts.get("hero") or {}
    return {k: float(hero.get(k, v)) for k, v in HERO_DEFAULTS.items()}


def box_hazard(d: dict | None, cog: bool = False) -> Hazard:
    """Hazard of a collider "damage" map; a cog source (src bit) is COG whatever its DamageHero says."""
    if cog:
        return Hazard.COG
    h = (d or {}).get("hazard_type")
    if h is None or not 0 <= h < len(HAZARD_TYPES):
        return Hazard.OTHER
    return HAZARD_OF[HAZARD_TYPES[h]]


def damage_flags(d: dict, cog: bool = False) -> frozenset[str]:
    """DamageBox.flags of a collider "damage" map (parry bits, DamagePropertyFlags, the TakeDamage gate)."""
    return _flags(d.get("parry") or 0, d.get("flags") or 0, box_hazard(d, cog), (d.get("eff") or 0) < 0)


@functools.lru_cache(maxsize=1024)
def _flags(parry: int, fl: int, hz: Hazard, amount_fsm: bool) -> frozenset[str]:
    out = []
    if parry & PARRYABLE:
        out.append("PARRYABLE")
    if parry & PARRY_BITS["clash"]:
        out.append("DEFLECTABLE")
    if parry & PARRY_BITS["counter"]:
        out.append("COUNTER")
    if fl & DAMAGE_FLAGS["flame"]:
        out.append("FLAME")
    if fl & DAMAGE_FLAGS["void"]:
        out.append("VOID")
    if fl & (DAMAGE_FLAGS["acid"] | DAMAGE_FLAGS["silk_acid"]):
        out.append("TAG_ACID")
    if fl & DAMAGE_FLAGS["non_lethal"]:
        out.append("NON_LETHAL")
    if hz not in IFRAME_BLOCKED:
        out.append("IGNORES_IFRAMES")
    if hz not in PARRY_BLOCKED:
        out.append("IGNORES_PARRY")
    if amount_fsm:
        out.append("AMOUNT_FSM")
    return frozenset(out)


def entity_kind(e: dict, bosses: frozenset[str] | dict = frozenset()) -> Kind:
    """Kind of one exported entity from its category and src bits (one frame; OracleBackend adds a short hold)."""
    tk, cat, src = e["type_key"], e["category"], e.get("src") or 0
    if tk in bosses:
        return Kind.BOSS
    if cat == "enemy":
        return Kind.ENEMY
    if src & SRC_BITS["cog"]:
        return Kind.HAZARD_DYN
    if src & SRC_BITS["projectile"]:
        return Kind.PROJECTILE
    if cat == "hazard":
        hz = {c["damage"]["hazard_type"] for c in e.get("colliders") or () if c.get("damage")}
        return Kind.ENEMY_ATTACK if not hz or HAZARD_TYPES.index("ENEMY") in hz else Kind.HAZARD_DYN
    if cat == "player_attack":
        return Kind.HERO_ATTACK
    if cat == "breakable":
        return Kind.BREAKABLE
    if cat == "interactable":
        low = tk.lower()
        return Kind.LEVER if "lever" in low else Kind.HOOK if ("harpoon" in low or "hook" in low) else Kind.PICKUP
    if cat == "terrain":
        return Kind.PLATFORM_MOVING
    return Kind.UNKNOWN


def type_key_of(name: str) -> str:
    """EntityRegistry.TypeKey: strip trailing "(Clone)" and " (n)" suffixes, repeatedly."""
    end = len(name)
    while True:
        while end > 0 and name[end - 1] == " ":
            end -= 1
        if end >= 7 and name[end - 7:end] == "(Clone)":
            end -= 7
            continue
        if end >= 3 and name[end - 1] == ")":
            i = end - 2
            while i >= 0 and name[i].isdigit():
                i -= 1
            if 0 <= i < end - 2 and name[i] == "(":
                end = i
                continue
        break
    return name if end == 0 else name[:end]


def _pts(flat: Sequence[float]) -> list[tuple[float, float]]:
    return list(zip(flat[0::2], flat[1::2]))


def _centre(flat: Sequence[float]) -> tuple[float, float]:
    xs, ys = flat[0::2], flat[1::2]
    return (min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5


def main_collider(e: dict) -> dict | None:
    """The entity's main body collider (§4.1): the one named like the root when names are exported, else the first
    exported collider. None when there is none (or names say the root has none)."""
    cols = [c for c in e.get("colliders") or () if c.get("verts_world")]
    if not cols:
        return None
    if any(c.get("name") is not None for c in cols):
        tk = e.get("type_key") or ""
        return next((c for c in cols if c.get("name") is not None and type_key_of(c["name"]) == tk), None)
    return cols[0]


def damage_boxes(e: dict) -> list[DamageBox]:
    """One DamageBox per exported collider with a "damage" map; active = enabled and able to deal damage now."""
    cog = bool((e.get("src") or 0) & SRC_BITS["cog"])
    out = []
    for c in e.get("colliders") or ():
        d = c.get("damage")
        if d is not None:
            eff, dealt = int(d.get("eff") or 0), int(d.get("dealt") or 0)
            out.append(DamageBox(poly=_pts(c["verts_world"]), active=is_threat(c), hazard=box_hazard(d, cog),
                                 flags=damage_flags(d, cog), name=c.get("name"),
                                 dmg_seq=(eff,) if eff > 0 else (dealt,) if dealt > 0 else ()))
    return out


def entity_pos(e: dict) -> tuple[float, float]:
    """Entity.pos per §4.1: main body collider centre, else render_aabb centre, else the transform."""
    c = main_collider(e)
    if c is not None:
        return _centre(c["verts_world"])
    r = e.get("render_aabb")
    if r:
        return (r[0] + r[2]) * 0.5, (r[1] + r[3]) * 0.5
    return float(e["pos"][0]), float(e["pos"][1])


@dataclass(slots=True)
class _Track:
    type_key: str
    kind: Kind
    pos: tuple[float, float]
    vel: tuple[float, float]
    t: float
    hp: int | None
    dead: bool
    killed: bool = False
    proj_t: float = -math.inf      # game time the projectile bit was last seen


@dataclass(slots=True)
class _HeroMemory:
    inv: bool = False
    inv_t0: float = 0.0
    inv_dur: float | None = None
    rec: bool = False
    rec_t0: float = 0.0
    dash: bool = False
    dash_t0: float = -math.inf
    bind: bool = False
    bind_hp0: int = 0
    bind_burst: bool = False
    hit_t: float = -math.inf          # game time of the last HIT_TAKEN
    dead: bool = False
    hp_total: int | None = None       # health + blue of the previous STATE (PlayerData exported)


@dataclass(slots=True)
class _Memory:
    f: int | None = None
    t_game: float = 0.0
    scene: str | None = None
    paused: bool | None = None
    focus: bool | None = None
    lockout_until: float = 0.0
    t_live: float | None = None
    hit_events: bool = False          # the stream carries oracle "hit" events: HIT_DEALT comes from them
    hero: _HeroMemory = field(default_factory=_HeroMemory)
    tracks: dict[int, _Track] = field(default_factory=dict)
    fsm_entry: dict[tuple[int, str], float] = field(default_factory=dict)


class OracleBackend:
    """STATE dict -> WorldState (exact, Src.ORACLE unless derived). Threats stay empty (combat/forecast fills them)."""

    TRACK_TTL_S = 10.0           # forget an entity not exported for this long (game time)

    def __init__(self, cstate_names: Sequence[str] | None = None, bosses: Iterable[BossSpec] = (),
                 source: Callable[[], dict] | None = None, backend: str = "oracle", config_fp: str = "",
                 qpc_freq: int = QPC_FREQ, constants: dict[str, float] | None = None,
                 clock: Callable[[], int] | None = time.perf_counter_ns):
        names = list(cstate_names) if cstate_names is not None else cstate_names_from_facts()
        self.cstate_names = names
        self._bit = {n: (names.index(n) >> 6, names.index(n) & 63) for n in _CS if n in names}
        self._words = (len(names) + 63) // 64
        self.bosses = {b.type_key: b for b in bosses}
        self.source = source
        self.backend = backend
        self.config_fp = config_fp
        self.qpc_freq = qpc_freq
        self.k = constants or hero_constants()
        self.clock = clock
        self.m = _Memory()
        self._hero_clip: str | None = None     # the hero's last animation clip outside the hurt mode

    def reset(self) -> None:
        """Forget all memory (new episode / reconnect)."""
        self.m = _Memory()

    def step(self) -> WorldState:
        if self.source is None:
            raise RuntimeError("OracleBackend.step() needs a source; use feed(state)")
        return self.feed(self.source())

    # ---- one STATE ---------------------------------------------------------------------------------------------

    def feed(self, s: dict) -> WorldState:
        m = self.m
        f = int(s["f"])
        gap = 0 if m.f is None else max(0, f - m.f - 1)
        m.f = f
        m.t_game += float(s.get("dt") or 0.0) * (1 + gap)    # a dropped STATE's dt is approximated by this one's
        q = int(s.get("q") or 0)
        t_ns = q * 1_000_000_000 // self.qpc_freq
        t_real = t_ns / 1e9
        g = s.get("game") or {}
        p = s.get("pause") or {}
        scene = g.get("scene")
        if scene != m.scene or gap > MAX_GAP_FRAMES:    # entity memory does not survive a room change or a long gap
            m.scene = scene
            m.tracks.clear()
            m.fsm_entry.clear()

        derived: list[Event] = []
        evs = list(s.get("ev") or ())
        if not m.hit_events and any(ev.get("k") == "hit" for ev in evs):
            m.hit_events = True
        hd = s.get("hero")
        cs = self._cs(hd["cstate"]) if hd else {}
        hp_prev = m.hero.hp_total
        hp_now = int(hd["health"]) + int(hd.get("health_blue") or 0) if hd and hd.get("health") is not None else None
        taken = self._hits_taken(evs, cs, hp_prev, hp_now)
        if taken:
            m.hero.hit_t = m.t_game       # the hit's i-frames start in the same STATE (StartRecoil)
        hero, res = self._hero(hd, cs, p, f, derived)
        if hero.mode.v != "hurt" or self._hero_clip is None:     # a hit landing while the hero is hurt was dealt
            self._hero_clip = ((hd or {}).get("anim") or {}).get("clip")    # by the action before (a spear in flight)
        hero_xy = hero.pos.v if hd else None
        ents, by_type = self._entities(s.get("ents") or (), f, hero_xy, derived)
        oracle_events = self._events(evs, f, hero_xy, ents, by_type, taken, cs)
        game = self._game(s, g, p, hd, f, t_real, derived)

        cam = self._cam(s.get("cam"))
        stamp = Stamp(frame=f, t_sample_qpc_ns=t_ns, t_pub_qpc_ns=self.clock() if self.clock else t_ns,
                      t_game_s=m.t_game, backend=self.backend, config_fp=self.config_fp)
        return WorldState(stamp=stamp, game=game, cam=cam, hero=hero, res=res, entities=ents, threats=[],
                          terrain=self._terrain(scene, s.get("room")), events=oracle_events + derived,
                          perception=PerceptionHealth(dropped_frames=gap))

    # ---- hero --------------------------------------------------------------------------------------------------

    def _cs(self, words: Sequence[int]) -> dict[str, bool]:
        if len(words) != self._words:
            raise ValueError(f"{len(words)} cstate words for {len(self.cstate_names)} fields: wrong cstate schema")
        return {n: bool((words[w] >> b) & 1) for n, (w, b) in self._bit.items()}

    @staticmethod
    def _contact(cs: dict[str, bool], wall: Sequence | None, facing: int) -> E[str]:
        if cs.get("hazardDeath") or cs.get("hazardRespawning"):
            return E("HAZARD")
        if cs.get("swimming"):
            return E("WATER")
        if cs.get("onGround"):
            return E("GROUND")
        sliding = cs.get("wallSliding") or cs.get("wallClinging")
        if wall is not None and len(wall) >= 2 and (wall[0] or wall[1]):
            if wall[0] and wall[1]:
                return E("WALL_L" if facing < 0 else "WALL_R")
            return E("WALL_L" if wall[0] else "WALL_R")
        if sliding:
            return E("WALL_L" if facing < 0 else "WALL_R")
        if cs.get("touchingWall"):
            return E("WALL_L" if facing < 0 else "WALL_R", conf=0.5, src=Src.PREDICTED)
        return E("AIR")

    def _hero(self, h: dict | None, cs: dict[str, bool], p: dict, f: int, out: list[Event]
              ) -> tuple[HeroState, Resources]:
        m, hm = self.m, self.m.hero
        if h is None:
            self.m.hero = _HeroMemory(hit_t=hm.hit_t)
            return HeroState(), Resources()
        t = m.t_game
        hm.dead = cs.get("dead", False)
        tx, ty = float(h["pos"][0]), float(h["pos"][1])
        vel = h.get("vel")
        facing = int(h.get("facing") or 1)
        box = h.get("box")
        if box:
            hurtbox = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
            pos = ((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5)
        else:
            hurtbox, pos = [], (tx, ty)
        contact = self._contact(cs, h.get("wall"), facing)

        def any_of(names: Sequence[str]) -> bool:
            return any(cs.get(n) for n in names)

        no_input = h.get("hero_state") == ACTOR_NO_INPUT
        if p.get("bench"):
            mode = "bench"
        elif cs.get("transitioning") or cs.get("isInCutsceneMovement") or (
                no_input and h.get("control_relinquished") and not (cs.get("recoiling") or cs.get("recoilFrozen"))):
            mode = "cutscene"
        elif cs.get("recoilFrozen") or cs.get("recoiling") or cs.get("dead") or contact.v == "HAZARD":
            mode = "hurt"
        elif cs.get("isBinding"):
            mode = "bind"
        elif any_of(_DASH):
            mode = "dash"
        elif any_of(_POGO):
            mode = "pogo"
        elif any_of(_ATTACK):
            mode = "attack"
        elif any_of(_NAIL_RECOIL):
            mode = "recoil"
        elif cs.get("wallSliding") or cs.get("wallClinging") or cs.get("wallScrambling"):
            mode = "wall"
        elif cs.get("floating"):
            mode = "glide"
        elif cs.get("onGround"):
            mode = "ground"
        else:
            mode = "air"

        tm = h.get("tm") if isinstance(h.get("tm"), dict) else None
        iframes, recoil, dash_cd, lock = self._timers(h, cs, tm, no_input, any_of(_ATTACK), any_of(_DASH[:3]))

        hp = int(h["health"]) if h.get("health") is not None else None
        binding = "NONE"
        spell = h.get("spell")
        spell_state = spell[0] if isinstance(spell, (list, tuple)) and spell else None
        if cs.get("isBinding"):
            binding = "IN_PROGRESS"
            if not hm.bind:
                hm.bind_hp0 = hp or 0
                hm.bind_burst = False
                out.append(Event(Ev.BIND_START, f, t, BindOutcome(hp or 0, hp or 0)))
            if spell_state in BIND_DONE_STATES:
                hm.bind_burst = True
        elif hm.bind:
            ok = hm.bind_burst or spell_state in BIND_DONE_STATES or (hp is not None and hp > hm.bind_hp0)
            binding = "DONE" if ok else "INTERRUPTED"
            out.append(Event(Ev.BIND_DONE if ok else Ev.BIND_BROKEN, f, t, BindOutcome(hm.bind_hp0, hp or 0)))
        hm.bind = bool(cs.get("isBinding"))
        hm.hp_total = hp + int(h.get("health_blue") or 0) if hp is not None else None

        alpha = h.get("alpha")
        hero = HeroState(
            pos=E(pos), vel=E((float(vel[0]), float(vel[1]))) if vel else unknown((0.0, 0.0)),
            facing=E(facing), hurtbox=hurtbox, contact=contact, mode=E(mode), iframes_left=iframes,
            recoil_left=recoil, dash_cd_left=dash_cd, action_lock_left=lock, binding=E(binding),
            can=dict(h["can"]) if h.get("can") else None, pos_transform=(tx, ty),
            tm={kk: float(v) for kk, v in tm.items() if isinstance(v, (int, float))} if tm is not None else None,
            phys_alpha=float(alpha) if alpha is not None else None)
        return hero, self._resources(h, cs, hp)

    def _timers(self, h: dict, cs: dict[str, bool], tm: dict | None, no_input: bool, attacking: bool, dash: bool
                ) -> tuple[E[float], E[float], E[float], E[float]]:
        """iframes_left, recoil_left, dash_cd_left, action_lock_left (exact from hero.tm when it is there)."""
        m, hm, k = self.m, self.m.hero, self.k
        t = m.t_game
        inv = cs.get("invulnerable", False)
        if inv and not hm.inv:
            hm.inv_t0 = t
            hm.inv_dur = k["INVUL_TIME"] if t - hm.hit_t <= 2 * FRAME_S else None
        hm.inv = inv
        rec = cs.get("recoiling", False)
        if rec and not hm.rec:
            hm.rec_t0 = t
        hm.rec = rec
        if dash and not hm.dash:
            hm.dash_t0 = t
        hm.dash = dash
        parry_t = float(h.get("parry_invuln_timer") or 0.0)

        # i-frames: Invulnerable() counts invulnerableDuration down with scaled deltaTime from StartInvulnerable.
        tm_inv = float(tm["inv"]) if tm is not None and tm.get("inv") is not None else None
        if tm_inv is not None and (tm_inv > 0.0 or not inv):
            iframes = E(max(tm_inv, parry_t))
        elif inv and hm.inv_dur is not None:
            left = max(0.0, hm.inv_dur - (t - hm.inv_t0))
            iframes = E(max(left, parry_t), sigma=FRAME_S, conf=0.9, src=Src.PREDICTED)
        elif inv:   # invulnerable for a reason with no known duration (hazard respawn, bind, cutscene ...)
            iframes = E(max(0.0, k["INVUL_TIME"] - (t - hm.inv_t0), parry_t), sigma=k["INVUL_TIME"], conf=0.3,
                        src=Src.PREDICTED)
        elif parry_t > 0.0:
            iframes = E(parry_t)
        elif h.get("can_take_damage") is False:
            iframes = E(0.0, sigma=math.inf, conf=0.0, src=Src.UNKNOWN)
        else:
            iframes = E(0.0)

        if tm is not None and tm.get("recoil") is not None:
            recoil = E(max(0.0, float(tm["recoil"])))
        elif cs.get("recoilFrozen"):
            recoil = E(k["RECOIL_DURATION"], sigma=FRAME_S, conf=0.8, src=Src.PREDICTED)
        elif rec and no_input:
            recoil = E(max(0.0, k["RECOIL_DURATION"] - (t - hm.rec_t0)), sigma=FRAME_S, conf=0.9, src=Src.PREDICTED)
        else:
            recoil = E(0.0)

        can_dash = (h.get("can") or {}).get("dash")
        if tm is not None and tm.get("dash_cd") is not None:
            dash_cd = E(max(0.0, float(tm["dash_cd"])))
        elif can_dash is True:
            dash_cd = E(0.0)
        else:
            left = max(0.0, k["DASH_COOLDOWN"] - (t - hm.dash_t0))
            dash_cd = E(left, sigma=FRAME_S, conf=0.8, src=Src.PREDICTED) if left > 0 or can_dash is None else \
                E(0.0, sigma=0.1, conf=0.5, src=Src.PREDICTED)

        anim = h.get("anim") or {}
        clip_left = 0.0
        if attacking:
            fps, n = float(anim.get("fps") or 0.0), int(anim.get("n") or 0)
            clip_left = max(0.0, n / fps - float(anim.get("t") or 0.0)) if fps > 0 else 0.0
        if tm is not None and tm.get("atk_cd") is not None:
            cd = max(0.0, float(tm["atk_cd"]))
            lock = E(max(cd, clip_left), sigma=0.05, conf=0.8, src=Src.PREDICTED) if clip_left > cd else E(cd)
        elif attacking:
            lock = E(clip_left, sigma=0.05, conf=0.5, src=Src.PREDICTED)
        else:
            lock = E(0.0, conf=0.8, src=Src.PREDICTED)
        return iframes, recoil, dash_cd, lock

    @staticmethod
    def _pending(h: dict, cs: dict[str, bool], hp_total: int | None) -> E[int]:
        """Resources.pending_dmg: what attached DamageTags and the frost clock can still deal (masks, an upper bound;
        hero.tags, docs/facts/1.0.30000/state_fields_m2.md §4: nil = no TagDamageTaker, [] = no tag). A tag without a
        hit limit (dmg_left -1: swimming in frost water) or with an unreadable dmg_left, the frost clock
        (cState.isFrosted: 1 HP every 1.75 s through i-frames while frostAmount >= 1, HeroController.cs:2697-2762,
        m0:N3) and a stream without hero.tags are unbounded or unknown: conf 0 and v = health + blue, lethal by itself
        where hits_to_death subtracts it (as safety.hits_to_death.pending_from_tags reads hero.tags)."""
        lethal = int(hp_total) if hp_total is not None else 0
        if "tags" not in h:
            return E(lethal, sigma=math.inf, conf=0.0, src=Src.UNKNOWN)
        if cs.get("isFrosted"):
            return E(lethal, sigma=math.inf, conf=0.0, src=Src.PREDICTED)
        tags = h["tags"]
        if tags is None:
            return E(0)
        total = 0
        for tg in tags if isinstance(tags, list) else (None,):
            d = tg.get("dmg_left") if isinstance(tg, dict) else None
            if isinstance(d, bool) or not isinstance(d, (int, float)) or d < 0:
                return E(lethal, sigma=math.inf, conf=0.0, src=Src.PREDICTED)
            total += int(d)
        return E(total)

    def _resources(self, h: dict, cs: dict[str, bool], hp: int | None) -> Resources:
        status = set(tag for n, tag in _STATUS if cs.get(n))
        tags = h.get("tags")
        if isinstance(tags, list):
            status.update(str(tg.get("kind") or "TAG").upper() for tg in tags if isinstance(tg, dict))
        pending = self._pending(h, cs, hp + int(h.get("health_blue") or 0) if hp is not None else None)
        if hp is None:          # HeroExporter writes PlayerData keys only when pd != null (a load in progress)
            return Resources(pending_dmg=pending, status=frozenset(status))
        fm = h.get("fractured_mask")
        if not fm or fm.get("equipped") is None:
            fm_v = E(FM.UNKNOWN, conf=0.0, src=Src.UNKNOWN)
        else:
            fm_v = E(FM.NOT_EQUIPPED if not fm["equipped"] else FM.INTACT if fm["amount_left"] > 0 else FM.BROKEN)
        names = h.get("tools") or []
        amounts = h.get("tool_amounts") or []
        maxes = h.get("tool_max") or []
        tools = [ToolSlot(tool_id=n, ammo=E(int(amounts[i] or 0)) if i < len(amounts) else unknown(0),
                          ammo_max=int(maxes[i] or 0) if i < len(maxes) and maxes[i] is not None else 0)
                 for i, n in enumerate(names) if n]
        silk_max = h.get("silk_max")
        silk = int(h.get("silk") or 0)
        can = h.get("can") or {}
        return Resources(
            hp=E(hp), hp_max=E(int(h.get("max_health") or 0)), blue=E(int(h.get("health_blue") or 0)),
            silk=E(silk), silk_max=E(int(silk_max)) if silk_max is not None else unknown(0),
            silk_hearts=int(h.get("silk_regen_max") or 0),
            bind_ready=E(bool(can["bind"]) and silk >= BIND_SILK) if can.get("bind") is not None else unknown(False),
            fractured_mask=fm_v, pending_dmg=pending, status=frozenset(status),
            crest=E(h.get("crest") or ""), equipped=[t.tool_id for t in tools], tools=tools,
            rosaries=E(int(h.get("geo") or 0)), shell_shards=E(int(h.get("shell_shards") or 0)))

    # ---- entities ----------------------------------------------------------------------------------------------

    def _entities(self, ents: Iterable[dict], f: int, hero_xy: tuple[float, float] | None, out: list[Event]
                  ) -> tuple[list[Entity], dict[str, list[Entity]]]:
        m = self.m
        t = m.t_game
        result: list[Entity] = []
        by_type: dict[str, list[Entity]] = {}
        seen = set()
        for e in ents:
            iid = int(e["iid"])
            seen.add(iid)
            tk = e["type_key"]
            tr = m.tracks.get(iid)
            src = e.get("src") or 0
            kind = entity_kind(e, self.bosses)
            proj_t = t if src & SRC_BITS["projectile"] else tr.proj_t if tr is not None else -math.inf
            if kind in (Kind.ENEMY_ATTACK, Kind.UNKNOWN) and t - proj_t <= PROJECTILE_HOLD_S:
                kind = Kind.PROJECTILE
            hidden = bool(e.get("hidden"))
            px, py = entity_pos(e) if not hidden else (float(e["pos"][0]), float(e["pos"][1]))
            dtg = t - tr.t if tr is not None else 0.0
            if e.get("vel") is not None:
                vel = E((float(e["vel"][0]), float(e["vel"][1])))
            elif tr is not None and dtg > 0:
                vel = E(((px - tr.pos[0]) / dtg, (py - tr.pos[1]) / dtg), sigma=0.1, conf=0.7, src=Src.PREDICTED)
            elif tr is not None:
                vel = E(tr.vel, sigma=0.1, conf=0.7, src=Src.PREDICTED)
            else:
                vel = unknown((0.0, 0.0))
            acc = ((vel.v[0] - tr.vel[0]) / dtg, (vel.v[1] - tr.vel[1]) / dtg) if tr is not None and dtg > 0 \
                else (0.0, 0.0)
            vx = vel.v[0]
            flip = bool(e.get("flipX"))
            facing = E(1 if vx > 0 else -1, conf=0.6, src=Src.PREDICTED) if abs(vx) > 0.1 else \
                E(-1 if flip else 1, conf=0.3, src=Src.PREDICTED)

            body = [_pts(c["verts_world"]) for c in e.get("colliders") or () if c.get("enabled")]
            boxes = damage_boxes(e)

            fsm = []
            for fs in e.get("fsms") or ():
                t0 = m.fsm_entry.get((iid, fs["name"]))
                fsm.append((fs["name"], fs["state"], t - t0 if t0 is not None else float(fs.get("t") or 0.0)))
            phase = None
            spec = self.bosses.get(tk)
            if spec is not None:
                ctl = next((x for x in fsm if x[0] == spec.control_fsm), None)
                if ctl is not None:
                    phase = PhasePost(topk=[(ctl[1], 1.0)], t_in_phase=ctl[2])

            hp = e.get("hp")
            dead = bool(e.get("is_dead"))
            if not m.hit_events and tr is not None and tr.hp is not None and hp is not None and hp < tr.hp:
                out.append(Event(Ev.HIT_DEALT, f, t, HitDealt(iid, tk, float(tr.hp - hp), float(hp),
                                                              hero_anim=self._hero_clip)))
            killed = tr.killed if tr is not None else False
            if dead and not killed:
                out.append(Event(Ev.ENEMY_KILLED, f, t, EnemyKilled(iid, tk)))
                killed = True
            m.tracks[iid] = _Track(tk, kind, (px, py), vel.v, t, hp, dead, killed, proj_t)

            anim = e.get("anim")
            ra = e.get("render_aabb")
            ent = Entity(id=iid, kind=kind, type_key=E(tk), pos=E((px, py)), vel=vel, acc=acc, facing=facing,
                         body_polys=body, dmg_boxes=boxes, phase=phase,
                         hp_est=E(float(hp)) if hp is not None else None, fsm=fsm,
                         visible_frac=0.0 if hidden else 1.0,
                         anim=(str(anim.get("clip")), int(anim.get("frame") or 0)) if anim else None,
                         render_box=(float(ra[0]), float(ra[1]), float(ra[2]), float(ra[3])) if ra else None,
                         flip_x=flip, hidden=hidden, pos_transform=(float(e["pos"][0]), float(e["pos"][1])))
            result.append(ent)
            by_type.setdefault(tk, []).append(ent)
        for iid in [i for i, tr in m.tracks.items() if i not in seen and t - tr.t > self.TRACK_TTL_S]:
            del m.tracks[iid]
            for key in [key for key in m.fsm_entry if key[0] == iid]:
                del m.fsm_entry[key]
        return result, by_type

    # ---- oracle events -----------------------------------------------------------------------------------------

    def _resolve_source(self, path: str | None, by_type: dict[str, list[Entity]],
                        hero_xy: tuple[float, float] | None) -> tuple[str | None, int | None]:
        """("Boss Scene/BoneBeast AtkBell R", ...) -> the type_key it names and the nearest such entity's id;
        (None, None) when no part of the path names a known entity type (the path stays in caller_path, O)."""
        if not path:
            return None, None
        for part in reversed(path.split("/")):
            cands = [c for c in by_type.get(part, ()) if not c.hidden]
            if cands:
                if hero_xy is None or len(cands) == 1:
                    return part, cands[0].id
                best = min(cands, key=lambda c: (c.pos.v[0] - hero_xy[0]) ** 2 + (c.pos.v[1] - hero_xy[1]) ** 2)
                return part, best.id
            for tr_iid, tr in self.m.tracks.items():
                if tr.type_key == part:
                    return part, tr_iid
        return None, None

    @staticmethod
    def _hit_amount(evs: Sequence[dict], i: int, n_hits: int, hp_prev: int | None, hp_now: int | None) -> int:
        """Masks the damage event evs[i] took: the TakeHealth "hp" event or the cancelled-lethal event that follows
        it (before the next damage event); else the STATE's HP drop when it is the frame's only hit; else 0."""
        for ev in evs[i + 1:]:
            k = ev.get("k")
            d = ev.get("d") or {}
            if k in ("damage", "special_damage"):
                break
            if k == "hp" and "amount" in d:
                return max(0, -int(d.get("delta") or 0) - int(d.get("blue_delta") or 0))
            if k in ("catastrophe", "would_die") and d.get("blocked"):
                return int(d.get("dmg", d.get("amount")) or 0)
        if n_hits == 1 and hp_prev is not None and hp_now is not None:
            return max(0, hp_prev - hp_now)
        return 0

    @classmethod
    def _hits_taken(cls, evs: Sequence[dict], cs: dict[str, bool], hp_prev: int | None, hp_now: int | None
                    ) -> dict[int, int]:
        """Index of every "damage" / "special_damage" event that took effect -> the masks it took. The oracle's no-op
        filter (HealthTap Blocked) mirrors only TakeDamage's i-frame gate; later gates return without effect too:
        downspike invulnerability on a pogo, the parry window, evading, shadow dash, HAZARD_ONLY damage mode
        (HeroController.cs:5374-5410). Live run i3_000: all 10 "damage" events with no health taken were pogo hits,
        HP unchanged; trial run: 2 during a bind. A hit took effect when it took health, was a lethal hit LethalBlock
        cancelled, or put the hero into recoil in its STATE with no other hit of the STATE taking health (0-mask
        hits that go through: Warding Bell bind shield, Lucky Dice, cs:5413-5446). The others become DAMAGE_BLOCKED."""
        n_hits = sum(ev.get("k") in ("damage", "special_damage") for ev in evs)
        amounts: dict[int, int] = {}
        for i, ev in enumerate(evs):
            k = ev.get("k")
            if k == "damage" or (k == "special_damage" and (ev.get("d") or {}).get("reached_special") is not False):
                amounts[i] = cls._hit_amount(evs, i, n_hits, hp_prev, hp_now)
        recoil = bool(cs.get("recoilFrozen") or cs.get("recoiling") or cs.get("hazardDeath") or cs.get("dead"))
        zero_ok = recoil and not any(a > 0 for a in amounts.values())
        return {i: a for i, a in amounts.items() if a > 0 or zero_ok or evs[i].get("k") == "special_damage"}

    def _events(self, evs: Sequence[dict], f: int, hero_xy: tuple[float, float] | None, ents: list[Entity],
                by_type: dict[str, list[Entity]], taken: dict[int, int], cs: dict[str, bool]) -> list[Event]:
        m = self.m
        t = m.t_game
        out: list[Event] = []
        for i, ev in enumerate(evs):
            k = ev.get("k")
            d = ev.get("d") or {}
            fe = int(ev.get("f", f))
            if k == "damage" and i not in taken:
                why = "pogo" if any(cs.get(n) for n in _POGO + ("downSpiking",)) else                     "bind" if cs.get("isBinding") else "gate"
                out.append(Event(Ev.DAMAGE_BLOCKED, fe, t, Info({
                    "source": d.get("source"), "hazard": d.get("hazard"), "why": why, "n": 1,
                    "amount": d.get("amount"), "end": "rejected"})))
            elif k == "damage":
                st, sid = self._resolve_source(d.get("source"), by_type, hero_xy)
                raw = d.get("amount")
                out.append(Event(Ev.HIT_TAKEN, fe, t, HitTaken(
                    amount=taken[i], hazard=HAZARD_OF.get(str(d.get("hazard")), Hazard.OTHER),
                    source_type=st, source_id=sid, caller_path=d.get("source"),
                    amount_raw=int(raw) if raw is not None else None)))
            elif k == "special_damage":
                if i not in taken:
                    continue
                raw = d.get("amount")
                out.append(Event(Ev.HIT_TAKEN, fe, t, HitTaken(
                    amount=taken[i], hazard=Hazard.OTHER, source_type=None,
                    caller_path=d.get("fsm") or d.get("method"), amount_raw=int(raw) if raw is not None else None)))
            elif k == "hit":
                out.extend(self._hit_dealt(d, fe, t))
            elif k in ("catastrophe", "would_die"):
                out.append(Event(Ev.CATASTROPHE if k == "catastrophe" else Ev.WOULD_DIE, fe, t, Lethal(
                    path=d.get("path") or d.get("cause"), blocked=d.get("blocked"),
                    amount=d.get("dmg", d.get("amount")),
                    hazard=HAZARD_OF.get(str(d["hazard"]), Hazard.OTHER) if d.get("hazard") else None,
                    source=d.get("src"))))
            elif k == "freeze":
                ms = d.get("ms")
                out.append(Event(Ev.FREEZE, fe, t, Freeze(phase=str(d.get("phase") or "start"), profile=d.get("type"),
                                                         duration_s=ms / 1000.0 if ms is not None else None)))
            elif k == "fsm":
                out.extend(self._fsm_event(d, fe, t, hero_xy, ents))
            elif k == "pause_gate":
                gate = d.get("gate")
                on = bool(d.get("value"))
                kind = {"disable_pause": (Ev.DISABLE_PAUSE_ON, Ev.DISABLE_PAUSE_OFF),
                        "disable_save_quit": (Ev.DISABLE_SAVEQUIT_ON, Ev.DISABLE_SAVEQUIT_OFF)}.get(gate)
                if kind is not None:
                    out.append(Event(kind[0] if on else kind[1], fe, t, GateEdge(gate, on, d.get("src"))))
            elif k == "scene_enter":
                out.append(Event(Ev.SCENE_ENTER, fe, t, SceneEnter(scene=d.get("scene") or "", gate=d.get("gate"))))
            elif k == "scene_leave":
                out.append(Event(Ev.SCENE_LEAVE, fe, t, SceneLeave(scene=d.get("from"), next_scene=d.get("to"))))
            elif k == "hazard_respawn":
                out.append(Event(Ev.HAZARD_RESPAWN, fe, t, Info(dict(d))))
            elif k == "save":
                out.append(Event(Ev.SAVE_OBSERVED, fe, t, Info(dict(d))))
            elif k == "damage_blocked":
                out.append(Event(Ev.DAMAGE_BLOCKED, fe, t, Info(dict(d))))
            elif k == "harness" and d.get("op") == "savestate.load":
                # the scene was rebuilt in place: entity and hero memory are stale (iids change on a load)
                m.tracks.clear()
                m.fsm_entry.clear()
                m.hero = _HeroMemory()
        return out

    def _hit_dealt(self, d: dict, fe: int, t: float) -> list[Event]:
        """Oracle "hit" (HealthManager damage the hero dealt) -> HIT_DEALT, plus ENEMY_KILLED for a killing blow."""
        ent = d.get("ent")
        if ent is None:
            return []
        iid = int(ent)
        tr = self.m.tracks.get(iid)
        tk = d.get("type_key") or (tr.type_key if tr is not None else "")
        dmg = d.get("dmg")
        hp_after = d.get("hp_after")
        dead = bool(d.get("dead"))
        out = [Event(Ev.HIT_DEALT, fe, t, HitDealt(
            iid, tk, float(dmg) if dmg is not None else None, float(hp_after) if hp_after is not None else None,
            attack=d.get("attack"), crit=d.get("crit"), killing=dead, hero_anim=self._hero_clip))]
        if dead and (tr is None or not tr.killed):
            out.append(Event(Ev.ENEMY_KILLED, fe, t, EnemyKilled(iid, tk)))
            if tr is not None:
                tr.killed = True
        if tr is not None and hp_after is not None:
            tr.hp = int(hp_after)
        return out

    def _fsm_event(self, d: dict, fe: int, t: float, hero_xy: tuple[float, float] | None, ents: list[Entity]
                   ) -> list[Event]:
        m = self.m
        ent_iid = d.get("ent")
        fsm = d.get("fsm") or ""
        if ent_iid is None:
            return []
        ent_iid = int(ent_iid)
        m.fsm_entry[(ent_iid, fsm)] = t
        cur = next((e for e in ents if e.id == ent_iid), None)
        tr = m.tracks.get(ent_iid)
        pos = cur.pos.v if cur is not None else tr.pos if tr is not None else None
        tk = cur.type_key.v if cur is not None else tr.type_key if tr is not None else d.get("obj")
        if cur is not None:   # the entity's state list was built before this event: show the new state's entry
            cur.fsm = [(n, s, 0.0) if n == fsm else (n, s, ts) for n, s, ts in cur.fsm or ()]
            if cur.phase is not None and self.bosses.get(tk) and self.bosses[tk].control_fsm == fsm:
                cur.phase.t_in_phase = 0.0
        rel = (pos[0] - hero_xy[0], pos[1] - hero_xy[1]) if pos is not None and hero_xy is not None else None
        out = [Event(Ev.FSM_TRANSITION, fe, t, FsmTransition(
            enemy_id=ent_iid, type_key=tk, fsm=fsm, from_state=d.get("from"), to_state=d.get("to") or "",
            hero_rel_pos=rel, t_in_prev=d.get("t_in_prev")))]
        spec = self.bosses.get(tk) if tk else None
        if spec is not None and fsm == spec.control_fsm and d.get("to") in spec.death_states:
            if tr is None or not tr.killed:
                out.append(Event(Ev.ENEMY_KILLED, fe, t, EnemyKilled(ent_iid, tk)))
                if tr is not None:
                    tr.killed = True
        return out

    # ---- game, camera, terrain ---------------------------------------------------------------------------------

    def _game(self, s: dict, g: dict, p: dict, hd: dict | None, f: int, t_real: float, out: list[Event]) -> Game:
        m = self.m
        t = m.t_game
        gs = g.get("gs")
        paused = bool(g.get("paused")) or gs == GS_PAUSED
        if m.paused is not None and paused != m.paused:
            out.append(Event(Ev.PAUSE_ON if paused else Ev.PAUSE_OFF, f, t, None))
            m.lockout_until = t_real + PAUSE_LOCKOUT_S
        m.paused = paused
        focus = bool(s.get("focus", True))
        if m.focus and not focus:
            out.append(Event(Ev.FOCUS_LOST, f, t, None))
        m.focus = focus

        raw = int(p.get("blk") or 0) if p else 128
        blk = PauseBlock(0)
        for bit, flag in _BLK_MAP:
            if raw & bit:
                blk |= flag
        if p.get("dsq"):
            blk |= PauseBlock.DISABLE_SAVEQUIT
        if p.get("preload"):
            blk |= PauseBlock.PRELOAD_PENDING
        if not focus:
            blk |= PauseBlock.FOCUS_LOST
        pause_ok = paused or (raw == 0 and focus)
        quit_ok = pause_ok and not (p.get("dsq") or p.get("preload") or raw & BLK_DISABLE_PAUSE)

        t_live = g.get("t_live")
        counting = t_live is not None and m.t_live is not None and t_live > m.t_live
        m.t_live = t_live
        return Game(
            screen=E(self._screen(g, p, s.get("hud"), hd is not None and m.hero.dead, raw)), menu=self._menu(s),
            game_state=gs,
            scene=E(g.get("scene") or ""), scene_variant=unknown(""), entry_gate=g.get("gate"),
            transitioning=bool(g.get("transition")), memory_scene=g.get("memory"),
            pause_available=E(pause_ok), quit_available=E(bool(quit_ok)), pause_blockers=int(blk),
            unpause_lockout_until_s=m.lockout_until, focus_ok=focus, permadeath_mode=g.get("pd_mode"),
            play_time=PlayTimeEst(live_s=float(t_live or 0.0), counting=counting, saved_s=g.get("t_saved")))

    @staticmethod
    def _menu(s: dict) -> MenuRead | None:
        """Oracle STATE "menu" (while paused) -> MenuRead: the highlighted item and whether Quit is greyed."""
        mn = s.get("menu")
        if not isinstance(mn, dict):
            return None
        q = mn.get("quit_ok")
        return MenuRead(cursor_item=mn.get("sel"), quit_greyed=(not q) if q is not None else None)

    @staticmethod
    def _screen(g: dict, p: dict, hud: dict | None, dead: bool, raw_blk: int) -> Screen:
        """Only what the oracle exports: ITEM_POPUP, AREA_TITLE, SHOP, BELLWAY_MAP, QUICK_MAP, ENDING and CREDITS
        have no source yet and come out as their nearest exported state; DIALOG stands for any active
        BlockingInteractable (pause.interact: dialogue, doors, shops), which blocks pausing. TRANSITION is GameState
        LOADING (play time stands still); entering / exiting a level is FADE (GameManager.IncreaseGameTimer counts
        it)."""
        if not g:
            return Screen.UNKNOWN
        gs, ui, menu = g.get("gs"), g.get("ui"), g.get("menu")
        if raw_blk & 8:
            return Screen.MSG_CANVAS
        if gs == GS_MAIN_MENU or ui == UI_MAIN_MENU_HOME:
            return {MENU_SAVE_PROFILES: Screen.SAVE_SELECT, MENU_PLAY_MODE: Screen.MODE_SELECT}.get(menu,
                                                                                                Screen.MAIN_MENU)
        if g.get("paused") or gs == GS_PAUSED:
            return Screen.PAUSE_MENU
        if dead:
            return Screen.DEATH
        if gs == GS_LOADING:
            return Screen.TRANSITION
        if gs in (GS_ENTERING, GS_EXITING) or g.get("transition"):
            return Screen.FADE
        if gs == GS_CUTSCENE:
            return Screen.CUTSCENE_VIDEO
        if p.get("inv"):
            return Screen.INVENTORY
        if p.get("bench"):
            return Screen.BENCH
        if p.get("interact"):
            return Screen.DIALOG
        if gs == GS_PLAYING:
            return Screen.PLAYING_HUD_HIDDEN if (hud or {}).get("hidden") else Screen.PLAYING
        return Screen.UNKNOWN

    @staticmethod
    def _cam(c: dict | None) -> CameraPose:
        if not c:
            return CameraPose()
        pos = c.get("pos") or (0.0, 0.0, 0.0)
        return CameraPose(x=float(pos[0]), y=float(pos[1]), z=float(pos[2]), fov=float(c.get("fov") or 0.0),
                          V=tuple(c["V"]) if c.get("V") else None, P=tuple(c["P"]) if c.get("P") else None,
                          sigma_xy=0.0, reliable=c.get("src") == 1, src=Src.ORACLE,
                          viewport=tuple(c.get("rect") or (0.0, 0.0, 1.0, 1.0)),
                          screen=tuple(c["screen"]) if c.get("screen") else None)

    @staticmethod
    def _terrain(scene: str | None, room: dict | None) -> TerrainRef:
        """Battle / arena gates (oracle room.gates) as the dynamic terrain deltas."""
        gates = []
        for gt in (room or {}).get("gates") or ():
            box = gt.get("box")
            if box and len(box) == 4:
                gates.append((str(gt.get("name") or ""), bool(gt.get("enabled")),
                              (float(box[0]), float(box[1]), float(box[2]), float(box[3]))))
        return TerrainRef(scene=scene or "", dynamic_deltas=[(n, on) for n, on, _ in gates], gates=gates)
