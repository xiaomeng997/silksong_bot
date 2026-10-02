"""One combat episode on a training instance (M2 W0): reset, intro, random start, fight, outcome (DESIGN §3.9, §4.4
AttemptRecord).

    tap = FightTap(link, BELL_BEAST)          # once per link: sees every STATE, so no event is missed
    rec = run_episode(link, BELL_BEAST, tap, policy, EpisodeConfig(mode="data", seed=17))

Flow: savestate.load (the reset) -> randomize_start(seed) (seeds the game's AI rolls, nothing else) -> the encounter's
intro (what the route does to start the fight; returns the wake frame) -> randomize_start(seed, hp, silk, dx, facing,
wait) while the boss is still waking (Bell Beast: about 2 s submerged) -> the policy plays one action per STATE
(continuous control, hold 0) until the outcome.

Outcomes (AttemptRecord.outcome):
  CLEAR         the boss's Control FSM entered a death state (Bell Beast: "Death Broadcast");
  WOULD_DIE     a lethal hit (LethalBlock "catastrophe" / "would_die"); in mode "eval" the episode ends there, in mode
                "data" (behaviour logging, the hero kept alive at >= 1 HP by LethalBlock) it is counted and play goes on;
  QUIT          the supervisor's pause-and-quit path ended the episode (not used before W5);
  STUCK         no outcome within the encounter's timebox after the wake;
  HARNESS_FAIL  the reset, the intro or the link failed, or the game paused or left the scene unasked.
"""
import random
import threading
import time
from dataclasses import asdict, dataclass, field

from ssbot.ipc import ents
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.train.encounters import Ctx, Encounter

CLEAR, WOULD_DIE, QUIT, STUCK, HARNESS_FAIL = "CLEAR", "WOULD_DIE", "QUIT", "STUCK", "HARNESS_FAIL"
POST_CLEAR_FRAMES = 60   # keep recording a second after the kill (death animations, late hazards)


class FightTap:
    """Accumulates the encounter's events from every STATE (OracleLink.subscribe_state, reader thread). reset() starts
    a new episode; lists are replaced, not cleared, so a reader holding the old ones never sees them change."""

    def __init__(self, link: OracleLink, enc: Encounter):
        self.enc = enc
        self._lock = threading.Lock()
        self.reset()
        link.subscribe_state(self._on)

    def reset(self) -> None:
        with self._lock:
            self.control: str | None = None
            self.control_log: list[tuple[int, str | None, str]] = []
            self.wake_frame: int | None = None
            self.death_frame: int | None = None
            self.damage: list[tuple[int, dict]] = []
            self.lethal: list[tuple[int, str, dict]] = []
            self.freezes: list[dict] = []
            self.hp: list[tuple[int, dict]] = []
            self.other: list[tuple[int, str, dict]] = []

    def _on(self, s: dict) -> None:
        evs = s.get("ev")
        if not evs:
            return
        enc = self.enc
        with self._lock:
            for ev in evs:
                k = ev.get("k")
                d = ev.get("d") or {}
                f = s["f"]
                if k == "fsm":
                    if d.get("fsm") == enc.control_fsm and str(d.get("obj", "")).startswith(enc.boss_type):
                        self.control = d["to"]
                        self.control_log.append((f, d["from"], d["to"]))
                        if self.wake_frame is None and d["from"] in enc.dormant and d["to"] not in enc.dormant:
                            self.wake_frame = f
                        if self.death_frame is None and d["to"] in enc.death_states:
                            self.death_frame = f
                elif k == "damage":
                    self.damage.append((f, d))
                elif k in ("catastrophe", "would_die"):
                    self.lethal.append((f, k, d))
                elif k == "freeze":
                    if d.get("phase") == "start":
                        self.freezes.append({"f": f, **d})
                elif k == "hp":
                    self.hp.append((f, d))
                elif k in ("special_damage", "hazard_respawn", "hazard_death", "die", "hero_dead", "player_dead",
                           "gs", "scene_leave"):
                    self.other.append((f, k, d))

    def lethal_frames(self) -> list[int]:
        """Frames with a lethal hit (one hit can raise both a catastrophe and a would_die)."""
        return sorted({f for f, _, _ in self.lethal})


@dataclass
class EpisodeConfig:
    mode: str = "data"                          # "data" (WOULD_DIE counted, play goes on) | "eval" (ends there)
    seed: int = 0
    hp: tuple[int, int] | None = None           # randomize_start ranges applied at the wake; None = as loaded
    silk: tuple[int, int] | None = None
    dx: tuple[float, float] | None = None
    facing: str | None = "random"
    wait_frames: tuple[int, int] = (0, 30)
    timebox_s: float | None = None              # default: the encounter's


@dataclass
class AttemptRecord:
    unit: str
    stage: str
    profile: str
    build: str
    code_rev: str | None
    config_fp: str
    start_kind: str
    mode: str
    seed: int
    outcome: str = HARNESS_FAIL
    reason: str | None = None
    ingame_s: float | None = None              # wake -> outcome, game frames / 60
    wall_s: float | None = None
    reset_ms: float | None = None
    f_reset: int | None = None
    f_wake: int | None = None
    f_end: int | None = None
    hits: int = 0
    hp_lost: int = 0
    min_hp: int | None = None
    would_die: int = 0
    first_lethal_f: int | None = None
    lethal_sources: list = field(default_factory=list)
    hit_sources: dict = field(default_factory=dict)
    rand: dict | None = None
    intro: list = field(default_factory=list)
    boss_hp_end: int | None = None
    attacks: dict = field(default_factory=dict)  # Control state -> entries this episode
    policy: dict = field(default_factory=dict)
    acts: int = 0
    late_states: int = 0                         # STATEs that arrived after the next one was already due (gaps)


def _rand(link: OracleLink, **args) -> dict:
    r = link.rpc("randomize_start", timeout_s=30, **args)
    return {k: r.get(k) for k in ("seed", "hp", "silk", "dx", "facing", "wait_frames")} if isinstance(r, dict) else r


def wait_settled(link: OracleLink, scene: str, still_frames: int = 10, tol_u: float = 0.01,
                 timeout_s: float = 20.0) -> dict:
    """The first STATE after a savestate load from which the hero stays put for `still_frames` frames, in `scene`,
    accepting input. hero_accepting_input alone is not enough: after a load the game can still be moving the hero
    for a while with velocity 0 and can.cast true (2026-10-01, first Bell Beast data run: 17 frames sliding from x 88.3
    back to the savestate's 78.0 at 0.63 u/frame), and a Silkspear pressed then was ignored (4 of 85 intros)."""
    deadline = time.monotonic() + timeout_s
    last = link.frame
    anchor, still = None, 0
    while time.monotonic() < deadline:
        s = link.wait_state(newer_than=last, timeout_s=2.0)
        last = s["f"]
        ok = (s.get("game") or {}).get("scene") == scene and s["hero"]["hero_accepting_input"]
        x, y = s["hero"]["pos"][0], s["hero"]["pos"][1]
        if ok and anchor is not None and abs(x - anchor[0]) <= tol_u and abs(y - anchor[1]) <= tol_u:
            still += 1
            if still >= still_frames:
                return s
        else:
            still = 0
        anchor = (x, y) if ok else None
    raise TimeoutError(f"hero not settled in {scene} within {timeout_s} s")


def boss_entity(s: dict, boss_type: str) -> dict | None:
    """The boss entity for the end-of-episode HP, hidden or not (a hidden boss's hp is still exported)."""
    return ents.boss_entity(s.get("ents"), boss_type, include_hidden=True)


def run_episode(link: OracleLink, enc: Encounter, tap: FightTap, policy, cfg: EpisodeConfig,
                rec: AttemptRecord) -> AttemptRecord:
    t_start = time.perf_counter()
    try:
        _run(link, enc, tap, policy, cfg, rec)
    except (OracleError, TimeoutError, RuntimeError, KeyError, TypeError, ConnectionError) as e:
        rec.outcome, rec.reason = HARNESS_FAIL, f"{type(e).__name__}: {e}"
    finally:
        try:
            link.act(link.frame + 2, 0, hold_frames=0)
            link.rpc("input.release", timeout_s=10)
        except (OracleError, TimeoutError, OSError):
            pass
        rec.wall_s = round(time.perf_counter() - t_start, 2)
        _summarise(tap, rec, link.state or {}, enc)
        stats = getattr(policy, "stats", None)
        rec.policy = stats() if stats else {}
    return rec


def _run(link: OracleLink, enc: Encounter, tap: FightTap, policy, cfg: EpisodeConfig, rec: AttemptRecord) -> None:
    errors = []
    for attempt in range(3):
        t0 = time.perf_counter()
        try:
            link.rpc("savestate.load", timeout_s=40, name=enc.savestate, timeout=30)
            rec.reset_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            break
        except (OracleError, TimeoutError) as e:
            errors.append(str(e))
            time.sleep(2.0)
    else:
        raise RuntimeError(f"savestate.load failed 3 times: {errors}")
    tap.reset()
    s = wait_settled(link, enc.scene)
    rec.f_reset = s["f"]
    _rand(link, seed=cfg.seed, wait_frames=[0, 10])
    ctx = Ctx(link=link, tap=tap)
    try:
        enc.intro(ctx)
    finally:
        rec.intro = ctx.log
    rec.f_wake = tap.wake_frame
    args = {"seed": cfg.seed, "wait_frames": list(cfg.wait_frames)}
    for k in ("hp", "silk", "dx"):
        v = getattr(cfg, k)
        if v is not None:
            args[k] = list(v)
    if cfg.facing:
        args["facing"] = cfg.facing
    rec.rand = _rand(link, **args)

    policy.reset(random.Random(cfg.seed), enc)
    timebox = cfg.timebox_s or enc.timebox_s
    last = link.frame
    end_after = None
    while True:
        s = link.wait_state(newer_than=last, timeout_s=2.0)
        if s["f"] > last + 1:
            rec.late_states += 1
        last = s["f"]
        game = s.get("game") or {}
        if end_after is not None:
            if last >= end_after:
                break
            link.act(last + 2, 0, hold_frames=0)
            continue
        if tap.death_frame is not None:
            rec.outcome = CLEAR
            end_after = last + POST_CLEAR_FRAMES
            continue
        if tap.lethal and cfg.mode == "eval":
            rec.outcome, rec.reason = WOULD_DIE, "lethal hit"
            break
        if game.get("paused"):
            rec.outcome, rec.reason = HARNESS_FAIL, f"paused unasked at frame {last}"
            break
        if game.get("scene") != enc.scene:
            rec.outcome, rec.reason = HARNESS_FAIL, f"left the scene: {game.get('scene')}"
            break
        if (last - (tap.wake_frame or rec.f_reset)) / 60.0 > timebox:
            rec.outcome, rec.reason = STUCK, f"timebox {timebox:.0f} s"
            break
        link.act(last + 2, policy.act(s, tap), hold_frames=0)
        rec.acts += 1
    rec.f_end = last


def _summarise(tap: FightTap, rec: AttemptRecord, s: dict, enc: Encounter) -> None:
    rec.hits = len(tap.damage)
    srcs: dict[str, int] = {}
    for _, d in tap.damage:
        k = str(d.get("source"))
        srcs[k] = srcs.get(k, 0) + 1
    rec.hit_sources = srcs
    rec.hp_lost = -sum(d.get("delta", 0) for _, d in tap.hp if (d.get("delta") or 0) < 0)
    hs = [d.get("h") for _, d in tap.hp if d.get("h") is not None]
    rec.min_hp = min(hs) if hs else None
    lf = tap.lethal_frames()
    rec.would_die = len(lf)
    rec.first_lethal_f = lf[0] if lf else None
    rec.lethal_sources = [d.get("src") or d.get("source") for _, k, d in tap.lethal if k == "catastrophe"][:10]
    if tap.wake_frame is not None and rec.f_end is not None:
        rec.ingame_s = round((rec.f_end - tap.wake_frame) / 60.0, 2)
    attacks: dict[str, int] = {}
    for _, _, to in tap.control_log:
        attacks[to] = attacks.get(to, 0) + 1
    rec.attacks = attacks
    b = boss_entity(s, enc.boss_type)
    rec.boss_hp_end = b.get("hp") if b else None


def record_dict(rec: AttemptRecord) -> dict:
    return asdict(rec)
