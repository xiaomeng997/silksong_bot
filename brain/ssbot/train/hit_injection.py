"""Pause stress test (DESIGN §3.7.5 G1 "10^4 fault injections, >= 30 % within +-3 frames of kills, clashes, bounces or
boss stuns"; M2 W5): a policy wrapper that injects one hit per episode through the oracle's hurt.special RPC (the
game's own HeroController.TakeDamage, ENEMY: hit-stop, recoil, i-frames, the 250 ms closed pause gate of probe P7),
large enough that the supervisor must quit (HP down to 1: h = 1, Q1), at a chosen kind of moment.

    pol = HitInjector(PlannerPolicy(view="oracle", ...), p_event=0.4)       # ssbot.tools.combat_run --inject-hits
    run as any policy (attach / warmup / reset / act / stats); stats()["inject"] says what was injected and when;
    ssbot.tools.pause_stress measures each trial from the run's recordings.

Kinds (one per episode, drawn at reset):
  rising / apex / falling   the hero airborne (hero_state airborne) with vy > 2, |vy| < 1.5, vy < -2 u/s
  attack / cast             during a nail attack (attack clips) or a Silkspear cast (NeedleThrow clips), air or ground
  pogo                      in a down-spike or its bounce (DownSpike clips)
  hit / kill / bounce       +-3 frames (offset drawn per episode) of the hero's predicted hit on the boss, of the
                            killing blow (boss HP <= the hero's hit), of a down-spike contact: the planner's own
                            prediction of its first scored attack (PlanResult.attack: kind, start frame) sets the
                            frame, so offsets before the event exist too; the measured offset comes from the recording
  roar                      0-3 frames into Rage Roar (Bell Beast has no stun; the roar is its only long committed
                            state with a screen effect)
p_event is the share of event kinds (hit / kill / bounce / roar); the rest are air / attack kinds. An episode whose
moment never comes falls back to the first airborne frame after fallback_s; a hit the game does not take (i-frames,
take_health_calls 0) re-arms. Injection waits min_s after the policy's first tick so the fight is under way.
The RPC is sent at the STATE of the chosen frame and lands at the oracle's next RPC pump (1-2 frames later): the
recording's damage event is the hit frame that counts.
Everything else is the wrapped policy's (attribute access falls through), so the harness sees the same pause
ownership, outcome and stats, plus stats()["inject"].
"""
import random

AIR_KINDS = ("rising", "apex", "falling", "attack", "cast", "pogo")
EVENT_KINDS = ("hit", "kill", "bounce", "roar")
HS_AIRBORNE = 3                      # GlobalEnums.ActorStates.airborne
HERO_HIT = 5                         # Bell Beast: every nail hit 5 HP (supervision.HERO_HIT_FLOOR)
ATTACK_CLIPS = ("Slash", "SlashAlt", "UpSlash", "DownSlash", "Slash Land", "Up Slash", "Attack")
HIT_DELAY = 2                        # a scored attack's box meets the boss 1-3 frames after its start frame (the
#                                      planner's attack windows; the start frame counts from the WorldState's frame)


def _clip(s: dict) -> str:
    return str(((s.get("hero") or {}).get("anim") or {}).get("clip") or "")


class HitInjector:
    def __init__(self, inner, p_event: float = 0.4, min_s: float = 4.0, fallback_s: float = 45.0,
                 max_retries: int = 3):
        self.inner = inner
        self.p_event = p_event
        self.min_s = min_s
        self.fallback_s = fallback_s
        self.max_retries = max_retries
        self.link = None
        self.log: dict = {}
        self.kind, self.offset, self.f0, self.sched, self.fut = AIR_KINDS[0], 0, None, None, None
        self.retries, self.done = 0, True        # nothing to inject before the first reset

    def __getattr__(self, name):          # pause_owned, episode_outcome, real_quit_active, planner_last, ...
        return getattr(self.inner, name)

    # ---- the policy interface -----------------------------------------------------------------------------------

    def attach(self, link) -> None:
        self.link = link
        if hasattr(self.inner, "attach"):
            self.inner.attach(link)

    def warmup(self) -> float:
        return self.inner.warmup() if hasattr(self.inner, "warmup") else 0.0

    def reset(self, rng: random.Random, enc) -> None:
        self.inner.reset(rng, enc)
        r = random.Random(rng.random())      # after the inner policy's own draws: its seeds are those of a plain run
        kind = r.choice(EVENT_KINDS) if r.random() < self.p_event else r.choice(AIR_KINDS)
        self.kind = kind
        self.offset = r.randint(-3, 3) if kind in ("hit", "kill", "bounce") else r.randint(0, 3)
        self.f0: int | None = None
        self.sched: int | None = None        # frame to inject at (event kinds)
        self.fut = None
        self.retries = 0
        self.done = False
        self.log = {"kind": kind, "offset": self.offset, "sent": [], "replies": [], "fallback": False}

    def stats(self) -> dict:
        st = self.inner.stats() if hasattr(self.inner, "stats") else {}
        self._collect()
        st["inject"] = self.log
        return st

    def act(self, s: dict, tap=None) -> int:
        mask = self.inner.act(s, tap)
        try:
            self._step(s)
        except Exception as e:  # noqa: BLE001 - an injection problem must never break the fight loop
            self.log.setdefault("errors", []).append(f"{s.get('f')}: {e!r}")
        return mask

    # ---- injection ----------------------------------------------------------------------------------------------

    def _collect(self) -> None:
        """The last RPC's reply: a hit the game did not take (i-frames, a parry) re-arms, up to max_retries."""
        if self.fut is None or not self.fut.done():
            return
        try:
            rep = self.fut.result()
        except Exception as e:  # noqa: BLE001
            rep = {"error": repr(e)}
        self.fut = None
        self.log["replies"].append(rep)
        took = isinstance(rep, dict) and rep.get("take_health_calls", 0) and rep.get("hp_after", 0) < rep.get(
            "hp_before", 0)
        if took:
            self.done = True
        elif self.retries < self.max_retries:
            self.retries += 1
            self.sched = None
        else:
            self.done = True

    def _ready(self, s: dict) -> int | None:
        """The HP to take the hero down to 1 from, when an injection may go now (a fight frame, not paused, no pause
        under way, HP >= 2), else None."""
        g = s.get("game") or {}
        h = s.get("hero") or {}
        hp = h.get("health")
        if g.get("paused") or not isinstance(hp, int) or hp < 2 or getattr(self.inner, "pause_owned", False):
            return None
        return hp

    def _moment(self, s: dict) -> bool:
        """The episode's kind of moment is now (air / attack kinds), or its scheduled frame has come (event kinds)."""
        f = s["f"]
        k = self.kind
        h = s.get("hero") or {}
        vy = (h.get("vel") or [0.0, 0.0])[1]
        air = h.get("hero_state") == HS_AIRBORNE
        clip = _clip(s)
        if k == "rising":
            return air and vy > 2.0
        if k == "apex":
            return air and abs(vy) < 1.5
        if k == "falling":
            return air and vy < -2.0
        if k == "attack":
            return any(clip.startswith(c) for c in ATTACK_CLIPS)
        if k == "cast":
            return clip.startswith("NeedleThrow")
        if k == "pogo":
            return clip.startswith("DownSpike")
        if self.sched is None:
            self.sched = self._schedule(s)
        return self.sched is not None and f >= self.sched

    def _schedule(self, s: dict) -> int | None:
        """Event kinds: the frame to inject at, from the planner's prediction of its first scored attack (hit, kill:
        only with the boss one hit from death, bounce: a down attack) or from the roar's first frame."""
        f = s["f"]
        if self.kind == "roar":
            boss = getattr(getattr(self.inner, "fc", None), "tracker", None)
            return f + self.offset if boss is not None and boss.state == "Rage Roar" else None
        res = getattr(self.inner, "planner_last", None)
        att = getattr(res, "attack", None) if res is not None else None
        if not att:
            return None
        kind, k0, _box = att
        if self.kind == "bounce" and kind != 3:
            return None
        if self.kind == "kill":
            hp = getattr(getattr(getattr(self.inner, "fc", None), "tracker", None), "ctx", None)
            hp = getattr(hp, "hp", None)
            if hp is None or hp > HERO_HIT:
                return None
        if k0 > 6:                      # only a press about to go out (the plan is re-chosen every tick)
            return None
        return f + k0 + HIT_DELAY + self.offset - 1     # the RPC lands about 1 frame after it is sent

    def _step(self, s: dict) -> None:
        self._collect()
        f = s["f"]
        if self.f0 is None:
            self.f0 = f
        if self.done or self.fut is not None or self.link is None or f - self.f0 < self.min_s * 60:
            return
        hp = self._ready(s)
        if hp is None:
            return
        go = self._moment(s)
        if not go and f - self.f0 > self.fallback_s * 60 and (s.get("hero") or {}).get("hero_state") == HS_AIRBORNE:
            go = True
            self.log["fallback"] = True
        if not go:
            return
        side = "left" if (s.get("hero") or {}).get("facing", 1) > 0 else "right"
        self.fut = self.link.rpc_async("hurt.special", kind="damage", amount=int(hp) - 1, hazard="ENEMY", side=side)
        h = s.get("hero") or {}
        self.log["sent"].append({"f": f, "hp": hp, "kind": self.kind, "sched": self.sched,
                                 "hero_state": h.get("hero_state"), "vy": round((h.get("vel") or [0, 0])[1], 2),
                                 "clip": _clip(s)})
