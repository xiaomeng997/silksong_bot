"""One combat episode on a training instance (M2 W0): reset, intro, random start, fight, outcome (DESIGN §3.9, §4.4
AttemptRecord).

    tap = FightTap(link, BELL_BEAST)          # once per link: sees every STATE, so no event is missed
    rec = run_episode(link, BELL_BEAST, tap, policy, EpisodeConfig(mode="data", seed=17))

Flow: savestate.load (the reset) -> randomize_start(seed) (seeds the game's AI rolls, nothing else) -> the encounter's
intro (what the route does to start the fight; returns the wake frame) -> randomize_start(seed, hp, silk, dx, facing,
wait) while the boss is still waking (Bell Beast: about 2 s submerged) -> the policy plays one action per STATE
(continuous control, hold 0) until the outcome.

Outcomes (AttemptRecord.outcome):
  CLEAR         the boss's Control FSM entered a death state (Bell Beast: "Death Broadcast"; a gauntlet: the last wave
                ended, ssbot.train.gauntlet.GauntletTap), and in mode "eval" no lethal hit came until the encounter's
                post-clear window (Encounter.post_clear_s after the kill) was over; with a post-kill tail
                (Encounter.tail_quiet_s, Bell Beast 2 s: DESIGN §3.5.7, the person's question of 2026-10-04) only once
                no damage source has been live for that much game time after the kill (live_threats: the attack bells
                of a kill in Burst Out roll for seconds), the policy playing on meanwhile (act_after_clear); a hit in
                the tail counts like one in the fight (tail_hits), a lethal one is WOULD_DIE, a supervisor quit before
                the tail's end is QUIT ("quit after the kill"), and a tail longer than tail_max_s is STUCK;
  WOULD_DIE     a lethal hit (LethalBlock "catastrophe" / "would_die"); in mode "eval" the episode ends there, also
                when the hit comes with the kill or after it (Steel Soul: a death after the last kill still ends the
                run; the Forum's dying Clappers and their runes still hurt for seconds); in mode "data" (behaviour
                logging, the hero kept alive at >= 1 HP by LethalBlock) it is counted (AttemptRecord.would_die,
                lethal_after_clear) and play goes on;
  QUIT          the supervisor's pause-and-quit path ended the episode (a policy with a supervisor sets
                episode_outcome = "QUIT"; training emulates the quit, then the harness unpauses with Continue, or,
                when the policy runs a real quit (real_quit_active), the game goes to the main menu and the harness
                neither checks the scene meanwhile nor unpauses after);
  STUCK         no outcome within the encounter's timebox after the wake;
  HARNESS_FAIL  the reset, the intro or the link failed, or the game paused or left the scene unasked.
"""
import os
import random
import threading
import time
from dataclasses import asdict, dataclass, field

from ssbot.ipc import ents
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.train.encounters import Ctx, Encounter
from ssbot.train.gauntlet import GauntletTap

CLEAR, WOULD_DIE, QUIT, STUCK, HARNESS_FAIL = "CLEAR", "WOULD_DIE", "QUIT", "STUCK", "HARNESS_FAIL"
POST_CLEAR_FRAMES = 60   # default post-clear window (Encounter.post_clear_s): death animations, late hazards
PAUSE_AFTER_KILL_FRAMES = 1200   # a supervisor pause under way at the kill keeps the keys this long at most


def live_threats(state_ents, armed: tuple = ()) -> list[str]:
    """Type keys of the STATE's entities that can hurt the hero now or later: one with an enabled damage collider
    (eff > 0, can_cause_damage), or a hazard in an armed state of its type (Encounter.tail_armed: a drop bell's Antic,
    no collider until it falls). Hidden entities have no colliders (ssbot.ipc.ents)."""
    out = []
    for e in state_ents or ():
        if e.get("hidden"):
            continue
        tk = str(e.get("type_key") or "")
        live = any(c.get("enabled") and c.get("damage") and (c["damage"].get("eff") or 0) > 0
                   and c["damage"].get("can_cause_damage", True) for c in e.get("colliders") or ())
        if not live and armed:
            st = ((e.get("fsms") or [{}])[0] or {}).get("state")
            live = any(tk.startswith(p) and st in states for p, states in armed)
        if live:
            out.append(tk)
    return out


def make_tap(link: OracleLink, enc: Encounter):
    """The encounter's event tracker: GauntletTap for a multi-wave arena (enc.waves), else FightTap."""
    return GauntletTap(link, enc) if enc.waves else FightTap(link, enc)


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
            self.tail_g = 0.0                         # game s after the kill (STATE dt summed after the death frame)
            self.tail_threat_g: float | None = None   # ... at the last frame a damage source was live
            self.tail_threats: dict[str, int] = {}    # live source type -> frames live after the kill
            self.tail_f: int | None = None            # the last frame the tail clock counted

    def tail_quiet_g(self) -> float:
        """Game s since the last frame with a live damage source after the kill (since the kill when none was)."""
        return self.tail_g - (self.tail_threat_g if self.tail_threat_g is not None else 0.0)

    def _tail(self, s: dict) -> None:
        f = s["f"]
        if self.tail_f is not None and f <= self.tail_f:
            return
        if f > self.death_frame:
            dt = s.get("dt")
            self.tail_g += float(dt) if isinstance(dt, (int, float)) else 1.0 / 60.0
        self.tail_f = f
        live = live_threats(s.get("ents"), getattr(self.enc, "tail_armed", ()))
        if live:
            self.tail_threat_g = self.tail_g
            for k in live:
                self.tail_threats[k] = self.tail_threats.get(k, 0) + 1

    def _on(self, s: dict) -> None:
        evs = s.get("ev")
        if not evs:
            if self.death_frame is not None and getattr(self.enc, "tail_quiet_s", None) is not None:
                with self._lock:
                    self._tail(s)
            return
        enc = self.enc
        with self._lock:
            self._events(s, evs, enc)
            if self.death_frame is not None and getattr(enc, "tail_quiet_s", None) is not None:
                self._tail(s)

    def _events(self, s: dict, evs: list, enc: Encounter) -> None:
        f = s["f"]
        for ev in evs:
            k = ev.get("k")
            d = ev.get("d") or {}
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
    attacks: dict = field(default_factory=dict)  # Control state -> entries this episode ("<type>/<fsm>/<state>"
                                                 # for a gauntlet)
    policy: dict = field(default_factory=dict)
    acts: int = 0
    late_states: int = 0                         # STATEs that arrived after the next one was already due (gaps)
    gauntlet: dict | None = None                 # GauntletTap.summary(): waves [{wave, f, t}], kills, allies
    lethal_after_clear: int = 0                  # lethal-hit frames at or after the kill (in the post-clear window)
    kill_s: float | None = None                  # wake -> the kill (the death state), frames / 60: time to kill
    f_kill: int | None = None
    tail_s: float | None = None                  # the post-kill tail (Encounter.tail_quiet_s): game s kill -> end
    tail_threat_s: float | None = None           # ... game s from the kill to the last live damage source (None: none)
    tail_threats: dict = field(default_factory=dict)   # live source type -> frames after the kill
    tail_hits: int = 0                           # hero hits ("damage") at or after the kill
    tail_hp_lost: int = 0
    tail_end: str | None = None                  # how the tail ended: "quiet", "scene <name>" (None: no tail / cut)


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


def unpause(link: OracleLink, tries: int = 4) -> bool:
    """After an emulated quit the game is held in the pause menu with Continue highlighted (safety.pause_quit stops
    there): Submit (enter) past the 0.3 s real-time lockout until the game runs again. The tap is a one-shot press
    (hold_frames > 0) and the inputs are released after: a continuous-control ACTION would arm the oracle's brain-lost
    watchdog, which pauses the game again 250 ms after the last ACTION (ActionScheduler)."""
    from ssbot.ipc.framing import mask
    ok = False
    for _ in range(tries):
        s = link.state or {}
        if not (s.get("game") or {}).get("paused"):
            ok = True
            break
        time.sleep(0.5)
        f = link.frame
        link.act(f + 2, mask("enter"), hold_frames=3)
        try:
            link.wait_state(lambda s: not (s.get("game") or {}).get("paused"), timeout_s=1.5)
        except TimeoutError:
            continue
    try:
        link.rpc("input.release", timeout_s=10)
    except (OracleError, TimeoutError, OSError):
        pass
    return ok or not ((link.state or {}).get("game") or {}).get("paused")


def boss_entity(s: dict, boss_type: str) -> dict | None:
    """The boss entity for the end-of-episode HP, hidden or not (a hidden boss's hp is still exported)."""
    return ents.boss_entity(s.get("ents"), boss_type, include_hidden=True)


def _act(link: OracleLink, last: int, policy, s: dict, tap) -> None:
    """The policy's mask for STATE `last`, applied at last + 2, with the ACTION flags the policy asks for after its
    tick (policy.action_flags: the pause machine's keys go out EXCLUSIVE, framing.ACTION_EXCLUSIVE)."""
    m = policy.act(s, tap)
    link.act(last + 2, m, hold_frames=0, flags=int(getattr(policy, "action_flags", 0) or 0))


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
    if ((link.state or {}).get("game") or {}).get("paused"):
        # left paused by the last episode (an emulated quit not yet resumed, or the oracle's brain-lost watchdog after
        # a stall of this worker): resume before the reset, or every episode after it fails "paused unasked"
        unpause(link)
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
    post_f = round(getattr(enc, "post_clear_s", POST_CLEAR_FRAMES / 60.0) * 60)
    if os.environ.get("SSBOT_POST_CLEAR_S"):
        # a longer post-kill window (the certified-kill check: the whole boss-death slow motion, ~100 real frames,
        # before the next savestate load, so the kill commitment's path through it is recorded)
        post_f = max(post_f, round(float(os.environ["SSBOT_POST_CLEAR_S"]) * 60))
    # a gauntlet's hazards outlive the last kill (the Forum's dying Clappers, runes, bombs): the policy keeps playing
    # through the window instead of standing still
    act_after = getattr(policy, "act_after_clear", False) or bool(getattr(enc, "waves", ()))
    # the post-kill tail instead of the fixed window (Encounter.tail_quiet_s; SSBOT_POST_CLEAR_S: the fixed window)
    tail = getattr(enc, "tail_quiet_s", None) is not None and not isinstance(tap, GauntletTap) \
        and not os.environ.get("SSBOT_POST_CLEAR_S")
    in_tail = False
    last = link.frame
    end_after = None
    while True:
        s = link.wait_state(newer_than=last, timeout_s=2.0)
        if s["f"] > last + 1:
            rec.late_states += 1
        last = s["f"]
        game = s.get("game") or {}
        if (tap.death_frame is not None and getattr(policy, "pause_owned", False)
                and getattr(policy, "episode_outcome", None) is None
                and last - tap.death_frame < PAUSE_AFTER_KILL_FRAMES):
            # a supervisor pause raised around the kill (the boss-death slow motion keeps the pause gate shut for
            # 1.35 s, m0:N13): its pause machine keeps the keys until its quit is done, as in a real run, instead of
            # being cut off by the post-kill zeros (the pause stress test injects hits within 3 frames of kills)
            if tap.lethal and cfg.mode == "eval":
                rec.outcome, rec.reason = WOULD_DIE, "lethal hit after the kill"
                break
            # the boss is dead: CLEAR (any other outcome ends the loop). Was `rec.outcome or CLEAR`, which kept the
            # record's default HARNESS_FAIL when the pause began before the kill (a pause triggered 1-3 frames before
            # a committed blow: pause stress chunk 20261002_232051 ep 26 and 39, "quit after the kill")
            rec.outcome = CLEAR
            _act(link, last, policy, s, tap)
            rec.acts += 1
            if getattr(policy, "episode_outcome", None) == QUIT:
                rec.reason = f"quit after the kill: {getattr(policy, 'outcome_reason', None)}"
                if tail:
                    rec.outcome = QUIT      # the encounter had not ended: the tail's quiet never came (DESIGN §3.5.7)
                end_after = last
            continue
        if tap.lethal and cfg.mode == "eval":
            # before the kill check: a lethal hit in the same STATE as the kill, or in the post-clear window, is a
            # death all the same
            rec.outcome = WOULD_DIE
            rec.reason = "lethal hit" if tap.death_frame is None else "lethal hit at/after the kill"
            break
        if end_after is not None:
            if last >= end_after:
                break
            # zeros after a kill, unless the policy asks to keep acting or the encounter is a gauntlet (the pause
            # stress test's hit injected just after the killing blow must reach the supervisor, which then owns the
            # keys through the block above)
            # a certified killing blow's plan (PlannerPolicy kill_commit_active) is played through the slow motion:
            # the plan the safety filter certified is the path executed, not the zeros (DESIGN §3.7.3 exception)
            after = (act_after or getattr(policy, "kill_commit_active", False)) and rec.outcome == CLEAR                 and not rec.reason
            if after:
                _act(link, last, policy, s, tap)
            else:
                link.act(last + 2, 0, hold_frames=0)
            continue
        if in_tail:
            # the post-kill tail (Encounter.tail_quiet_s): CLEAR once no damage source has been live for that long
            # (game time, FightTap.tail_quiet_g); the policy keeps playing (the planner dodges the bells), and a hit
            # here is a hit like any other (a lethal one: WOULD_DIE above, a supervisor quit: QUIT)
            if game.get("scene") != enc.scene and not getattr(policy, "real_quit_active", False):
                rec.tail_end = f"scene {game.get('scene')}"      # the room is gone, and what was live in it
                break
            if tap.tail_quiet_g() >= enc.tail_quiet_s:
                rec.tail_end = "quiet"
                break
            if game.get("paused") and not getattr(policy, "pause_owned", False):
                rec.outcome, rec.reason = HARNESS_FAIL, f"paused unasked at frame {last} (post-kill tail)"
                break
            if tap.tail_g > enc.tail_max_s or last - tap.death_frame > PAUSE_AFTER_KILL_FRAMES + enc.tail_max_s * 60:
                rec.outcome, rec.reason = STUCK, f"post-kill tail: damage sources live for {enc.tail_max_s:.0f} s"
                break
            if act_after or getattr(policy, "kill_commit_active", False):
                _act(link, last, policy, s, tap)
                rec.acts += 1
            else:
                link.act(last + 2, 0, hold_frames=0)
            if getattr(policy, "episode_outcome", None) == QUIT:
                rec.outcome = QUIT
                rec.reason = f"quit after the kill: {getattr(policy, 'outcome_reason', None)}"
                break
            continue
        if tap.death_frame is not None:
            rec.outcome = CLEAR
            if tail:
                in_tail = True
            else:
                end_after = last + post_f
            if getattr(policy, "kill_commit_active", False) or (tail and act_after):
                _act(link, last, policy, s, tap)          # the kill commitment keeps its keys from the kill frame on
                rec.acts += 1
            continue
        quitting = getattr(policy, "real_quit_active", False)     # a real quit: menus, then the main menu
        if game.get("paused") and not getattr(policy, "pause_owned", False):
            rec.outcome, rec.reason = HARNESS_FAIL, f"paused unasked at frame {last}"
            break
        if game.get("scene") != enc.scene and not quitting:
            rec.outcome, rec.reason = HARNESS_FAIL, f"left the scene: {game.get('scene')}"
            break
        if (last - (tap.wake_frame or rec.f_reset)) / 60.0 > timebox:
            rec.outcome, rec.reason = STUCK, f"timebox {timebox:.0f} s"
            break
        _act(link, last, policy, s, tap)
        rec.acts += 1
        if getattr(policy, "episode_outcome", None) == QUIT:
            rec.outcome, rec.reason = QUIT, getattr(policy, "outcome_reason", None)
            break
    rec.f_end = last
    if cfg.mode == "eval" and rec.outcome == CLEAR and tap.lethal_frames():
        # a lethal hit the reader thread delivered after the loop's last look (the STATE that closed the window)
        rec.outcome, rec.reason = WOULD_DIE, "lethal hit at/after the kill"
    if rec.outcome == QUIT and not getattr(policy, "real_quit_active", False):
        unpause(link)      # an emulated quit left the game paused (a real one ends on the main menu: no Continue)


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
    if tap.death_frame is not None:
        rec.lethal_after_clear = sum(1 for f in lf if f >= tap.death_frame)
        rec.f_kill = tap.death_frame
        if tap.wake_frame is not None:
            rec.kill_s = round((tap.death_frame - tap.wake_frame) / 60.0, 2)
        rec.tail_hits = sum(1 for f, _ in tap.damage if f >= tap.death_frame)
        rec.tail_hp_lost = -sum(d.get("delta", 0) for f, d in tap.hp
                                if f >= tap.death_frame and (d.get("delta") or 0) < 0)
        if getattr(tap, "tail_f", None) is not None:
            rec.tail_s = round(tap.tail_g, 3)
            rec.tail_threat_s = None if tap.tail_threat_g is None else round(tap.tail_threat_g, 3)
            rec.tail_threats = dict(tap.tail_threats)
    if tap.wake_frame is not None and rec.f_end is not None:
        rec.ingame_s = round((rec.f_end - tap.wake_frame) / 60.0, 2)
    if isinstance(tap, GauntletTap):
        rec.attacks = dict(tap.state_entries)
        rec.gauntlet = tap.summary()
        rec.boss_hp_end = None
        return
    attacks: dict[str, int] = {}
    for _, _, to in tap.control_log:
        attacks[to] = attacks.get(to, 0) + 1
    rec.attacks = attacks
    b = boss_entity(s, enc.boss_type)
    rec.boss_hp_end = b.get("hp") if b else None


def record_dict(rec: AttemptRecord) -> dict:
    return asdict(rec)
