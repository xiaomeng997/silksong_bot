"""OracleBackend: the oracle's STATE stream -> WorldState, one STATE at a time (DESIGN §4.2, §4.5; training only).

    backend = OracleBackend(bosses=[BELL_BEAST], cstate_names=link.rpc("schema.cstate")["bools"])
    for s in RecordingReader(path).states():
        ws = backend.feed(s)

Live, OracleLink.subscribe_state sees every STATE on the reader thread; give the backend a queue:

    q = queue.SimpleQueue(); link.subscribe_state(q.put)
    backend = OracleBackend(source=q.get); ws = backend.step()

feed() must see every STATE in order: events ride on the STATE of their frame (a dropped STATE takes its events with
it; the gap shows in perception.dropped_frames), and these fields need memory:
  - Stamp.t_game_s: sum of the scaled dt, so it stands still through freezes and pauses (dt is 0 there).
  - Game.unpause_lockout_until_s: 0.3 s real time (QPC) after every pause/unpause edge (m0:C12).
  - HeroState timers, from cState edges plus the prefab constants (docs/facts/<build>/hero_constants.json), since the
    oracle exports no remaining times: iframes_left = INVUL_TIME - game time since cState.invulnerable rose, which is
    how HeroController.Invulnerable() counts (scaled deltaTime; measured: the sum of dt from rise to fall is 0.992 s
    for 96 of 98 rises after a hit in the trial run, INVUL_TIME 1.0 minus the rise frame); recoil_left =
    RECOIL_DURATION from cState.recoiling (measured 0.200-0.217 s); dash_cd_left = DASH_COOLDOWN from a dash start;
    action_lock_left = what is left of the attack/throw animation clip.
  - Entity velocity by finite difference when the entity has no rigidbody (vel nil), acceleration always so.
  - Entity kind is sticky per iid: the oracle's projectile src bit is a heuristic that comes and goes ("BoneBeast
    AtkBell R" carries it in 2270 of its 2439 frames, "AtkBell L" in 2258 of 2808), so the most specific kind seen
    so far is kept.
  - HIT_DEALT from enemy HP drops between consecutive STATEs: the oracle has no hit-dealt event (oracle/src has no
    HealthManager.TakeDamage tap). Measured: every Hunter nail hit on the Bell Beast took exactly 5 HP (27 drops in
    the trial episode, 29 in the person's fight); the killing blow shows no drop, because the entity leaves "ents" in
    the frame its Control FSM enters "Death Broadcast" (Silkspear from 15 HP in the trial run): ENEMY_KILLED comes from
    the boss's death states (BossSpec) or is_dead rising.
  - FSM_TRANSITION.hero_rel_pos and the time in the current FSM state (game time since the transition event; the
    exported StateTime stops once a state's actions have finished).

Cost on the trial run (2 episodes, 26.9k STATEs, 13900K): p50 77-92 us, p99 373-435 us per STATE.

Contact and mode come from the cState bits (field order: RPC "schema.cstate", or the facts copy cstate_schema.json).
A wall contact's side is taken from the facing, which BeginWallSlide sets towards the wall (HeroController.cs:8468-8479);
the oracle does not export touchingWallL/R.
"""
import json
import math
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ssbot.core.bosses import BossSpec
from ssbot.core.worldstate import (BIND_SILK, FM, BindOutcome, CameraPose, DamageBox, E, Entity, EnemyKilled, Ev, Event,
                                   Freeze, FsmTransition, Game, GateEdge, Hazard, HeroState, HitDealt, HitTaken, Info,
                                   Kind, Lethal, PauseBlock, PerceptionHealth, PhasePost, PlayTimeEst, Resources,
                                   SceneEnter, SceneLeave, Screen, Src, Stamp, TerrainRef, ToolSlot, WorldState,
                                   unknown)
from ssbot.ipc.ents import DAMAGE_FLAGS, HAZARD_TYPES, PARRY_BITS, PARRYABLE, SRC_BITS, is_threat

BUILD = "1.0.30000"
FACTS = Path(__file__).resolve().parents[3] / "docs" / "facts"
QPC_FREQ = 10_000_000              # HELLO "qpc_freq" on this machine
PAUSE_LOCKOUT_S = 0.3              # WaitForSecondsRealtime(0.3f) after PauseGameToggle (m0:C12)
FRAME_S = 1.0 / 60.0
MAX_GAP_FRAMES = 30                # a longer gap in the STATE stream (reconnect, recording cut) resets entity memory

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

# Kind refinement order for the sticky per-iid kind (a later entry never gives way to an earlier one).
_KIND_RANK = {Kind.UNKNOWN: 0, Kind.ENEMY_ATTACK: 1, Kind.HAZARD_DYN: 1, Kind.PROJECTILE: 2}


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


def damage_flags(d: dict) -> frozenset[str]:
    """DamageBox.flags of a collider "damage" map (parry bits, DamagePropertyFlags, hazard type)."""
    out = []
    parry = d.get("parry") or 0
    if parry & PARRYABLE:
        out.append("PARRYABLE")
    if parry & PARRY_BITS["clash"]:
        out.append("DEFLECTABLE")
    if parry & PARRY_BITS["counter"]:
        out.append("COUNTER")
    fl = d.get("flags") or 0
    if fl & DAMAGE_FLAGS["flame"]:
        out.append("FLAME")
    if fl & DAMAGE_FLAGS["void"]:
        out.append("VOID")
    if fl & (DAMAGE_FLAGS["acid"] | DAMAGE_FLAGS["silk_acid"]):
        out.append("TAG_ACID")
    if fl & DAMAGE_FLAGS["non_lethal"]:
        out.append("NON_LETHAL")
    h = d.get("hazard_type")
    if h is not None and 0 <= h < len(HAZARD_TYPES) and HAZARD_TYPES[h] in ("PIT", "SINK"):
        out.append("IGNORES_IFRAMES")
    if (d.get("eff") or 0) < 0:
        out.append("AMOUNT_FSM")
    return frozenset(out)


def entity_kind(e: dict, bosses: frozenset[str] | dict = frozenset()) -> Kind:
    """Kind of one exported entity from its category and src bits (one frame; OracleBackend keeps it sticky)."""
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


def _pts(flat: Sequence[float]) -> list[tuple[float, float]]:
    return list(zip(flat[0::2], flat[1::2]))


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
    hit_t: float = -math.inf          # game time of the last HIT_TAKEN
    dead: bool = False


@dataclass(slots=True)
class _Memory:
    f: int | None = None
    t_game: float = 0.0
    scene: str | None = None
    paused: bool | None = None
    focus: bool | None = None
    lockout_until: float = 0.0
    t_live: float | None = None
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
        evs = s.get("ev") or ()
        if any(ev.get("k") in ("damage", "special_damage") for ev in evs):
            m.hero.hit_t = m.t_game       # the hit's i-frames start in the same STATE (StartRecoil)
        hd = s.get("hero")
        hero, res = self._hero(hd, p, f, derived)
        hero_xy = hero.pos.v if hd else None
        ents, by_type = self._entities(s.get("ents") or (), f, hero_xy, derived)
        oracle_events = self._events(evs, f, hero_xy, ents, by_type)
        game = self._game(s, g, p, hd, f, t_real, derived)

        cam = self._cam(s.get("cam"))
        stamp = Stamp(frame=f, t_sample_qpc_ns=t_ns, t_pub_qpc_ns=self.clock() if self.clock else t_ns,
                      t_game_s=m.t_game, backend=self.backend, config_fp=self.config_fp)
        return WorldState(stamp=stamp, game=game, cam=cam, hero=hero, res=res, entities=ents, threats=[],
                          terrain=TerrainRef(scene=scene or ""), events=oracle_events + derived,
                          perception=PerceptionHealth(dropped_frames=gap))

    # ---- hero --------------------------------------------------------------------------------------------------

    def _cs(self, words: Sequence[int]) -> dict[str, bool]:
        if len(words) != self._words:
            raise ValueError(f"{len(words)} cstate words for {len(self.cstate_names)} fields: wrong cstate schema")
        return {n: bool((words[w] >> b) & 1) for n, (w, b) in self._bit.items()}

    def _hero(self, h: dict | None, p: dict, f: int, out: list[Event]) -> tuple[HeroState, Resources]:
        m, hm, k = self.m, self.m.hero, self.k
        if h is None:
            self.m.hero = _HeroMemory(hit_t=hm.hit_t)
            return HeroState(), Resources()
        t = m.t_game
        cs = self._cs(h["cstate"])
        hm.dead = cs.get("dead", False)
        x, y = float(h["pos"][0]), float(h["pos"][1])
        vel = h.get("vel")
        facing = int(h.get("facing") or 1)
        box = h.get("box")
        hurtbox = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])] if box else []

        if cs.get("hazardDeath") or cs.get("hazardRespawning"):
            contact = "HAZARD"
        elif cs.get("swimming"):
            contact = "WATER"
        elif cs.get("onGround"):
            contact = "GROUND"
        elif cs.get("wallSliding") or cs.get("wallClinging") or cs.get("touchingWall"):
            contact = "WALL_L" if facing < 0 else "WALL_R"
        else:
            contact = "AIR"

        def any_of(names: Sequence[str]) -> bool:
            return any(cs.get(n) for n in names)

        no_input = h.get("hero_state") == ACTOR_NO_INPUT
        if p.get("bench"):
            mode = "bench"
        elif cs.get("transitioning") or cs.get("isInCutsceneMovement") or (
                no_input and h.get("control_relinquished") and not (cs.get("recoiling") or cs.get("recoilFrozen"))):
            mode = "cutscene"
        elif cs.get("recoilFrozen") or cs.get("recoiling") or cs.get("dead") or contact == "HAZARD":
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

        # i-frames: Invulnerable() counts invulnerableDuration down with scaled deltaTime from StartInvulnerable.
        inv = cs.get("invulnerable", False)
        if inv and not hm.inv:
            hm.inv_t0 = t
            hm.inv_dur = k["INVUL_TIME"] if t - hm.hit_t <= 2 * FRAME_S else None
        hm.inv = inv
        parry_t = float(h.get("parry_invuln_timer") or 0.0)
        if inv and hm.inv_dur is not None:
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

        rec = cs.get("recoiling", False)
        if rec and not hm.rec:
            hm.rec_t0 = t
        hm.rec = rec
        if cs.get("recoilFrozen"):
            recoil = E(k["RECOIL_DURATION"], sigma=FRAME_S, conf=0.8, src=Src.PREDICTED)
        elif rec and no_input:
            recoil = E(max(0.0, k["RECOIL_DURATION"] - (t - hm.rec_t0)), sigma=FRAME_S, conf=0.9, src=Src.PREDICTED)
        else:
            recoil = E(0.0)

        dash = any_of(_DASH[:3])
        if dash and not hm.dash:
            hm.dash_t0 = t
        hm.dash = dash
        dash_cd = E(max(0.0, k["DASH_COOLDOWN"] - (t - hm.dash_t0)), sigma=FRAME_S, conf=0.8, src=Src.PREDICTED)

        anim = h.get("anim") or {}
        if any_of(_ATTACK):
            fps, n = float(anim.get("fps") or 0.0), int(anim.get("n") or 0)
            left = max(0.0, n / fps - float(anim.get("t") or 0.0)) if fps > 0 else 0.0
            lock = E(left, sigma=0.05, conf=0.5, src=Src.PREDICTED)
        else:
            lock = E(0.0, conf=0.8, src=Src.PREDICTED)

        hp = int(h.get("health") or 0)
        binding = "NONE"
        if cs.get("isBinding"):
            binding = "IN_PROGRESS"
            if not hm.bind:
                hm.bind_hp0 = hp
                out.append(Event(Ev.BIND_START, f, t, BindOutcome(hp, hp)))
        elif hm.bind:
            ok = hp > hm.bind_hp0
            binding = "DONE" if ok else "INTERRUPTED"
            out.append(Event(Ev.BIND_DONE if ok else Ev.BIND_BROKEN, f, t, BindOutcome(hm.bind_hp0, hp)))
        hm.bind = bool(cs.get("isBinding"))

        hero = HeroState(
            pos=E((x, y)), vel=E((float(vel[0]), float(vel[1]))) if vel else unknown((0.0, 0.0)),
            facing=E(facing), hurtbox=hurtbox, contact=E(contact), mode=E(mode), iframes_left=iframes,
            recoil_left=recoil, dash_cd_left=dash_cd, action_lock_left=lock, binding=E(binding),
            can=dict(h["can"]) if h.get("can") else None)
        return hero, self._resources(h, cs, hp)

    def _resources(self, h: dict, cs: dict[str, bool], hp: int) -> Resources:
        fm = h.get("fractured_mask")
        if not fm or fm.get("equipped") is None:
            fm_v = E(FM.UNKNOWN, conf=0.0, src=Src.UNKNOWN)
        else:
            fm_v = E(FM.NOT_EQUIPPED if not fm["equipped"] else FM.INTACT if fm["amount_left"] > 0 else FM.BROKEN)
        names = h.get("tools") or []
        amounts = h.get("tool_amounts") or []
        tools = [ToolSlot(tool_id=n, ammo=E(int(a or 0))) for n, a in zip(names, amounts) if n]
        silk_max = h.get("silk_max")
        silk = int(h.get("silk") or 0)
        can = h.get("can") or {}
        return Resources(
            hp=E(hp), hp_max=E(int(h.get("max_health") or 0)), blue=E(int(h.get("health_blue") or 0)),
            silk=E(silk), silk_max=E(int(silk_max)) if silk_max is not None else unknown(0),
            silk_hearts=int(h.get("silk_regen_max") or 0),
            bind_ready=E(bool(can["bind"]) and silk >= BIND_SILK) if can.get("bind") is not None else unknown(False),
            fractured_mask=fm_v, pending_dmg=unknown(0),
            status=frozenset(tag for n, tag in _STATUS if cs.get(n)),
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
            kind = entity_kind(e, self.bosses)
            if tr is not None and _KIND_RANK.get(tr.kind, 3) > _KIND_RANK.get(kind, 3) and kind in _KIND_RANK:
                kind = tr.kind
            px, py = float(e["pos"][0]), float(e["pos"][1])
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
            facing = E(1 if vx > 0 else -1, conf=0.6, src=Src.PREDICTED) if abs(vx) > 0.1 else \
                E(-1 if e.get("flipX") else 1, conf=0.3, src=Src.PREDICTED)

            body, boxes = [], []
            cog = bool((e.get("src") or 0) & SRC_BITS["cog"])
            for c in e.get("colliders") or ():
                pts = _pts(c["verts_world"])
                if c.get("enabled"):
                    body.append(pts)
                d = c.get("damage")
                if d is not None:
                    eff, dealt = int(d.get("eff") or 0), int(d.get("dealt") or 0)
                    h = d.get("hazard_type")
                    hazard = Hazard.COG if cog else HAZARD_OF.get(HAZARD_TYPES[h], Hazard.OTHER) \
                        if h is not None and 0 <= h < len(HAZARD_TYPES) else Hazard.OTHER
                    boxes.append(DamageBox(poly=pts, active=is_threat(c), hazard=hazard, flags=damage_flags(d),
                                           dmg_seq=(eff,) if eff > 0 else (dealt,) if dealt > 0 else ()))

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
            if tr is not None and tr.hp is not None and hp is not None and hp < tr.hp:
                out.append(Event(Ev.HIT_DEALT, f, t, HitDealt(iid, tk, float(tr.hp - hp), float(hp))))
            killed = tr.killed if tr is not None else False
            if dead and not killed:
                out.append(Event(Ev.ENEMY_KILLED, f, t, EnemyKilled(iid, tk)))
                killed = True
            m.tracks[iid] = _Track(tk, kind, (px, py), vel.v, t, hp, dead, killed)

            ent = Entity(id=iid, kind=kind, type_key=E(tk), pos=E((px, py)), vel=vel, acc=acc, facing=facing,
                         body_polys=body, dmg_boxes=boxes, phase=phase,
                         hp_est=E(float(hp)) if hp is not None else None, fsm=fsm, visible_frac=1.0)
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
        """("Boss Scene/BoneBeast AtkBell R", ...) -> the type_key it names and the nearest such entity's id."""
        if not path:
            return None, None
        for part in reversed(path.split("/")):
            cands = by_type.get(part)
            if cands:
                if hero_xy is None or len(cands) == 1:
                    return part, cands[0].id
                best = min(cands, key=lambda c: (c.pos.v[0] - hero_xy[0]) ** 2 + (c.pos.v[1] - hero_xy[1]) ** 2)
                return part, best.id
            for tr_iid, tr in self.m.tracks.items():
                if tr.type_key == part:
                    return part, tr_iid
        return path, None

    def _events(self, evs: Iterable[dict], f: int, hero_xy: tuple[float, float] | None, ents: list[Entity],
                by_type: dict[str, list[Entity]]) -> list[Event]:
        m = self.m
        t = m.t_game
        out: list[Event] = []
        for ev in evs:
            k = ev.get("k")
            d = ev.get("d") or {}
            fe = int(ev.get("f", f))
            if k == "damage":
                st, sid = self._resolve_source(d.get("source"), by_type, hero_xy)
                m.hero.hit_t = t
                out.append(Event(Ev.HIT_TAKEN, fe, t, HitTaken(
                    amount=int(d.get("amount") or 0), hazard=HAZARD_OF.get(str(d.get("hazard")), Hazard.OTHER),
                    source_type=st, source_id=sid, caller_path=d.get("source"))))
            elif k == "special_damage":
                if d.get("reached_special") is False:
                    continue
                m.hero.hit_t = t
                out.append(Event(Ev.HIT_TAKEN, fe, t, HitTaken(
                    amount=int(d.get("amount") or 0), hazard=Hazard.OTHER, source_type=d.get("method"),
                    caller_path=d.get("fsm") or d.get("method"))))
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

    # ---- game, camera ------------------------------------------------------------------------------------------

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
            screen=E(self._screen(g, p, s.get("hud"), hd is not None and m.hero.dead, raw)), menu=None,
            game_state=gs,
            scene=E(g.get("scene") or ""), scene_variant=unknown(""), entry_gate=g.get("gate"),
            transitioning=bool(g.get("transition")), memory_scene=g.get("memory"),
            pause_available=E(pause_ok), quit_available=E(bool(quit_ok)), pause_blockers=int(blk),
            unpause_lockout_until_s=m.lockout_until, focus_ok=focus, permadeath_mode=g.get("pd_mode"),
            play_time=PlayTimeEst(live_s=float(t_live or 0.0), counting=counting, saved_s=g.get("t_saved")))

    @staticmethod
    def _screen(g: dict, p: dict, hud: dict | None, dead: bool, raw_blk: int) -> Screen:
        """Only what the oracle exports: DIALOG, ITEM_POPUP, AREA_TITLE, SHOP, BELLWAY_MAP, QUICK_MAP, FADE, ENDING
        and CREDITS have no source yet and come out as their nearest exported state."""
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
        if gs in (GS_LOADING, GS_ENTERING, GS_EXITING) or g.get("transition"):
            return Screen.TRANSITION
        if gs == GS_CUTSCENE:
            return Screen.CUTSCENE_VIDEO
        if p.get("inv"):
            return Screen.INVENTORY
        if p.get("bench"):
            return Screen.BENCH
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
