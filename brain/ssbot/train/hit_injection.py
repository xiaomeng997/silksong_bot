"""Pause stress test (DESIGN §3.7.5 G1 "10^4 fault injections, >= 30 % within +-3 frames of kills, clashes, bounces or
boss stuns"; M2 W5): a policy wrapper that injects one fault per episode at a chosen kind of moment, so that the
supervisor must pause and quit from there.

    pol = HitInjector(PlannerPolicy(view="oracle", ...), p_event=0.5)       # ssbot.tools.combat_run --inject-hits
    run as any policy (attach / warmup / reset / act / stats); stats()["inject"] says what was injected and when;
    ssbot.tools.pause_stress measures each trial from the run's recordings.

Faults (one per episode):
  hit       hurt.special damage down to 1 HP: the game's own HeroController.TakeDamage (ENEMY: hit-stop, recoil,
            i-frames, the 250 ms closed pause gate of probe P7), h = 1, Q1
  trigger   a supervisor quit trigger with no damage (Supervisor.inject, trigger QF): the pause loop starts from
            whatever the game and the key path are doing, usually with the gate open and planner keys down (the menu
            key guard's case, safety.key_guard); needs the wrapped policy's SupervisedControl (inner.sc)
  menu      both on one tick, on a frame with a planner key latched: the hit lands 1-2 frames after the trigger, i.e.
            0-2 frames before the loop's first Pause press reaches the game, the frame the pause menu would open
            (the press is dropped when the hit's disablePause wins the frame; the loop must retry at the gate)

Moments. The first stress chunk (11b4ca0, 20261002_180411) aimed its kill / bounce / hit kinds at the planner's
predicted attack frame and landed 4 of 112 within +-3 frames of a measured kill / bounce / clash / stun (3.6 %): a hit
before the moment cancels the hero's attack, so the moment never comes (the bounce trials hit in DownSpike Antic), and
the prediction (start frame + 2) was early for down-spikes. Now the hard moments are taken on their first frame, or,
where the moment is committed and its frame known, a few frames before it:
  kill    the killing blow (a hit event leaving the boss at <= 0 HP, BossDeathSlow, a death state). hit: on its first
          frame (lands +1..+2, in the 1.35 s slow motion that keeps the pause gate shut, m0:N13). trigger: offset
          -3..+2 from the blow: >= 0 from its first frame; < 0 only from a committed blow with the boss at or under
          its damage: a Silkspear hits 18-20 frames after the quickcast press (run 20261002_190611, 6 episodes:
          26 of 26 needle hits, 18 / 19 / 20 frames 12 / 13 / 1; it flies on whatever the keys do), so the
          trigger goes at press + 19 + offset; a nail press hits 1-4 frames later (Slash / AltSlash 38 of 56 at +1),
          so its offset is at least -1 (the press is seen on the frame it is latched); either only when the planner
          scored that attack as a hit
  bounce  downSpikeBouncing onset: trigger only, onset + 0..2. The game takes no enemy hit there: hits sent at
          onset + 1 and + 2 (run at + 2 and + 3) were all refused (take_health_calls 0; chunks 20261002_225739 ep 0,
          230409: 4 of 4): a bounce off the boss sets the long down-spike invulnerability
          (DOWNSPIKE_INVULNERABILITY_STEPS_LONG = 10 physics steps; STATE hero.cstate_int[1] downspikeInvulnerabilitySteps
          read 8 on the onset frame and counted down to 0 about 10 frames later, 230409 ep 14), which TakeDamage refuses
          for ENEMY hits. Every refused hit is a "damage" event the planner counts as unpredicted, so two of them end
          the attempt as a Q4 quit with no fault in it
  cast    the first frame of a NeedleThrow clip (a Silkspear: AnticG / AnticA); hit / trigger + 0..2
  clash   parrying onset, or a nail recoil onset with no hit dealt on that frame or the 2 before (a tink off a bell);
          hit / trigger + 0..2. Weight 0 against the Bell Beast: none came within clash_fallback_s in 5 of 5 trials
          (chunks 20261002_225013, 230409) and the 6 calibration fights had no parry
p_event is the share of these (weights bounce 3 : cast 3 : menu 2 : kill 1 : clash 0; hit or trigger 50 / 50 for
cast and kill); the rest are coverage kinds: hit faults on airborne frames (rising vy > 2, apex |vy| < 1.5, falling
vy < -2), attack, pogo (as the first chunk), and trigger faults on any frame with a planner key latched ("keys": the
key guard under load). An episode whose moment never comes falls back after fallback_s (kill: kill_fallback_s, as the
boss is one hit from death only near the end of a 55-80 s fight; clash: clash_fallback_s): a hit on the next
airborne frame, a trigger at once. A hit the game does not take (i-frames, take_health_calls 0) re-arms. Faults wait
min_s after the policy's first tick so the fight is under way. Trigger faults are injected before the wrapped
policy's tick, so its supervisor raises PAUSE_PENDING on that very STATE; the hit RPC is sent at the STATE of the
chosen frame and lands at the oracle's next RPC pump (1-2 frames later): the recording's damage event is the hit frame
that counts.
Everything else is the wrapped policy's (attribute access falls through), so the harness sees the same pause
ownership, outcome and stats, plus stats()["inject"].
"""
import json
import random

from ssbot.knowledge.kinematics import CSTATE_NAMES_PATH

AIR_KINDS = ("rising", "apex", "falling", "attack", "pogo")
COVERAGE_KINDS = AIR_KINDS + ("keys",)
EVENT_KINDS = ("bounce", "cast", "menu", "kill", "clash")
EVENT_WEIGHTS = (3, 3, 2, 1, 0)
FAULT_HIT, FAULT_TRIGGER, FAULT_MENU = "hit", "trigger", "menu"
HS_AIRBORNE = 3                      # GlobalEnums.ActorStates.airborne
HERO_HIT = 5                         # Bell Beast: every nail hit 5 HP (supervision.HERO_HIT_FLOOR)
NEEDLE_HIT = 15                      # Silkspear ("Needle Damage", run 20261002_190611: 26 of 26 hits 15 HP)
NEEDLE_DELAY = 19                    # quickcast press latched -> needle hit, frames (18-20)
NAIL_DELAY = 1                       # attack press latched -> nail hit, frames (Slash / AltSlash mode)
BIT_ATTACK, BIT_QUICKCAST = 1 << 1, 1 << 6     # ACTION button bits (ssbot.ipc.framing.BUTTONS)
ATTACK_CLIPS = ("Slash", "SlashAlt", "UpSlash", "DownSlash", "Slash Land", "Up Slash", "Attack")
_CS = ("downSpikeBouncing", "parrying", "recoilingLeft", "recoilingRight", "recoilFrozen")


def _clip(s: dict) -> str:
    return str(((s.get("hero") or {}).get("anim") or {}).get("clip") or "")


def _latched(s: dict) -> int:
    act = s.get("act") or {}
    hf = act.get("hf") or {}
    return int(hf.get("latched") if hf.get("latched") is not None else act.get("mask") or 0)


class HitInjector:
    act_after_clear = True               # train/episode: keep acting through the post-kill frames (a kill-timed hit)

    def __init__(self, inner, p_event: float = 0.5, min_s: float = 4.0, fallback_s: float = 45.0,
                 kill_fallback_s: float = 150.0, clash_fallback_s: float = 20.0, max_retries: int = 3,
                 boss_type: str | None = None, death_states: tuple[str, ...] = ("Death Broadcast",)):
        self.inner = inner
        self.p_event = p_event
        self.min_s = min_s
        self.fallback_s = fallback_s
        self.kill_fallback_s = kill_fallback_s
        self.clash_fallback_s = clash_fallback_s
        self.max_retries = max_retries
        self.boss_type = boss_type
        self.death_states = death_states
        names = json.loads(CSTATE_NAMES_PATH.read_text(encoding="utf-8"))["bools"]
        self._cs_idx = {n: names.index(n) for n in _CS}
        self.link = None
        self.log: dict = {}
        self.kind, self.fault, self.offset = AIR_KINDS[0], FAULT_HIT, 0
        self.f0: int | None = None
        self.sched: int | None = None
        self.fut = None
        self.retries, self.done = 0, True        # nothing to inject before the first reset
        self._prev: dict = {}
        self._hit_frames: list[int] = []
        self._attacks: list = []             # (tick frame, the planner's PlanResult.attack then)

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
        if enc is not None:
            self.boss_type = getattr(enc, "boss_type", self.boss_type)
            self.death_states = tuple(getattr(enc, "death_states", self.death_states))
        r = random.Random(rng.random())      # after the inner policy's own draws: its seeds are those of a plain run
        if r.random() < self.p_event:
            kind = r.choices(EVENT_KINDS, EVENT_WEIGHTS)[0]
            fault = {"menu": FAULT_MENU, "bounce": FAULT_TRIGGER}.get(kind) or r.choice((FAULT_HIT, FAULT_TRIGGER))
        else:
            kind = r.choice(COVERAGE_KINDS)
            fault = FAULT_TRIGGER if kind == "keys" else FAULT_HIT
        if fault == FAULT_TRIGGER and getattr(self.inner, "sc", None) is None:
            fault = FAULT_HIT                # no supervisor to trigger: the plain hit
        if kind == "kill" and fault == FAULT_TRIGGER:
            offset = r.randint(-3, 2)
        elif fault == FAULT_HIT:
            offset = r.randint(0, 1)
        else:
            offset = r.randint(0, 2)
        self.kind, self.fault, self.offset = kind, fault, offset
        self.f0 = None
        self.sched = None
        self.fut = None
        self.retries = 0
        self.done = False
        self._prev = {}
        self._hit_frames: list[int] = []
        self._attacks: list = []
        self.log = {"kind": kind, "fault": fault, "offset": offset, "sent": [], "replies": [], "fallback": False,
                    "moments": []}

    def stats(self) -> dict:
        st = self.inner.stats() if hasattr(self.inner, "stats") else {}
        self._collect()
        st["inject"] = self.log
        return st

    def act(self, s: dict, tap=None) -> int:
        try:
            self._step(s)            # before the tick: a trigger reaches this STATE's supervisor step
        except Exception as e:  # noqa: BLE001 - an injection problem must never break the fight loop
            self.log.setdefault("errors", []).append(f"{s.get('f')}: {e!r}")
        return self.inner.act(s, tap)

    # ---- moments ------------------------------------------------------------------------------------------------

    def _cs(self, s: dict) -> dict[str, bool]:
        w = (s.get("hero") or {}).get("cstate")
        if not w:
            return {}
        out = {}
        for n, i in self._cs_idx.items():
            out[n] = bool(i >> 6 < len(w) and (w[i >> 6] >> (i & 63)) & 1)
        return out

    def _boss_hp(self, s: dict) -> float | None:
        for e in s.get("ents") or ():
            if e.get("type_key") == self.boss_type and isinstance(e.get("hp"), (int, float)):
                return e["hp"]
        tr = getattr(getattr(self.inner, "fc", None), "tracker", None)
        return getattr(getattr(tr, "ctx", None), "hp", None)

    def _features(self, s: dict) -> dict:
        """This STATE's onsets and edges against the previous one (kept in self._prev)."""
        f = s["f"]
        cs = self._cs(s)
        clip = _clip(s)
        lat = _latched(s)
        p = self._prev
        ev = s.get("ev") or ()
        kill = hit = False
        for e in ev:
            k, d = e.get("k"), e.get("d") or {}
            if k == "hit":
                hit = True
                hp = d.get("hp_after")
                if d.get("dead") or (isinstance(hp, (int, float)) and hp <= 0 and
                                     (self.boss_type is None or d.get("type_key") == self.boss_type)):
                    kill = True
            elif k == "freeze" and d.get("type") == "BossDeathSlow" and d.get("phase", "start") == "start":
                kill = True
            elif k == "fsm" and d.get("to") in self.death_states:
                kill = True
        if hit:
            self._hit_frames = [x for x in self._hit_frames if x >= f - 2] + [f]
        rec_on = (cs.get("recoilingLeft") or cs.get("recoilingRight")) and not (
            p.get("recoilingLeft") or p.get("recoilingRight")) and not cs.get("recoilFrozen")
        out = {"kill": kill and not p.get("killed"),
               "bounce": bool(cs.get("downSpikeBouncing") and not p.get("downSpikeBouncing")),
               "cast": clip.startswith("NeedleThrow") and not str(p.get("clip", "")).startswith("NeedleThrow"),
               "clash": bool((cs.get("parrying") and not p.get("parrying")) or
                             (rec_on and not any(x >= f - 2 for x in self._hit_frames))),
               "needle": bool(lat & BIT_QUICKCAST and not p.get("lat", 0) & BIT_QUICKCAST),
               "nail": bool(lat & BIT_ATTACK and not p.get("lat", 0) & BIT_ATTACK),
               "lat": lat}
        self._prev = dict(cs, clip=clip, lat=lat, killed=bool(p.get("killed") or kill))
        return out

    def _schedule(self, s: dict, x: dict) -> int | None:
        """The frame to fire at, once this episode's moment is seen (or, for a committed kill, predicted)."""
        f = s["f"]
        k, o = self.kind, self.offset
        if k in ("bounce", "cast", "clash"):
            if x[k]:
                self.log["moments"].append([k, f])
                return f + o
            return None
        if k == "kill":
            if x["kill"]:
                self.log["moments"].append(["kill", f])
                return f + max(o, 0)
            if o < 0 and self.fault == FAULT_TRIGGER:
                hp = self._boss_hp(s)
                if hp is None or hp <= 0:
                    return None
                if x["needle"] and hp <= NEEDLE_HIT and self._scored(f, needle=True):
                    self.log["moments"].append(["needle_press", f])
                    return f + NEEDLE_DELAY + o
                if x["nail"] and hp <= HERO_HIT and self._scored(f, needle=False):
                    self.log["moments"].append(["nail_press", f])
                    return f + max(NAIL_DELAY + o, 0)
            return None
        h = s.get("hero") or {}
        vy = (h.get("vel") or [0.0, 0.0])[1]
        air = h.get("hero_state") == HS_AIRBORNE
        clip = _clip(s)
        now = {"rising": air and vy > 2.0, "apex": air and abs(vy) < 1.5, "falling": air and vy < -2.0,
               "attack": any(clip.startswith(c) for c in ATTACK_CLIPS), "pogo": clip.startswith("DownSpike"),
               "keys": x["lat"] != 0, "menu": x["lat"] != 0}.get(k, False)
        return f if now else None

    def _scored(self, f: int, needle: bool) -> bool:
        """The planner scored the attack pressed now as a hit: a tick of the last 4 frames whose chosen plan's first
        scored hit (PlanResult.attack: kind 1-3 nail, 4 Silkspear; start frame from that tick's origin) starts
        within 3 frames of it. A press it did not score is not a predicted kill (chunk 20261002_225013 ep 6: a
        SlashAlt press with the boss at 5 HP whiffed, the trigger fired, no kill)."""
        for t, a in self._attacks:
            if t >= f - 4 and a and (int(a[0]) == 4) == needle and int(a[1]) <= 3:
                return True
        return False

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
        if took or self.fault == FAULT_MENU:       # menu: the trigger has fired; one hit, taken or not
            self.done = True
        elif self.retries < self.max_retries:
            self.retries += 1
            self.sched = None
        else:
            self.done = True

    def _ready(self, s: dict) -> bool:
        """A fault may go now: a fight frame, not paused, no pause under way, and HP >= 2 when it includes a hit."""
        g = s.get("game") or {}
        hp = (s.get("hero") or {}).get("health")
        need = 1 if self.fault == FAULT_TRIGGER else 2
        return not (g.get("paused") or not isinstance(hp, int) or hp < need
                    or getattr(self.inner, "pause_owned", False))

    def _step(self, s: dict) -> None:
        self._collect()
        f = s["f"]
        if self.f0 is None:
            self.f0 = f
        x = self._features(s)
        att = getattr(getattr(self.inner, "planner_last", None), "attack", None)
        self._attacks = [(t, a) for t, a in self._attacks if t >= f - 6] + [(f - 1, att)]
        if self.done or self.fut is not None or self.link is None or f - self.f0 < self.min_s * 60:
            return
        if not self._ready(s):
            return
        if self.sched is None:
            self.sched = self._schedule(s, x)
        late = {"kill": self.kill_fallback_s, "clash": self.clash_fallback_s}.get(self.kind, self.fallback_s) * 60
        if self.sched is None and f - self.f0 > late:
            h = s.get("hero") or {}
            if self.fault == FAULT_TRIGGER or h.get("hero_state") == HS_AIRBORNE:
                self.sched = f
                self.log["fallback"] = True
        if self.sched is None or f < self.sched:
            return
        h = s.get("hero") or {}
        row = {"f": f, "hp": h.get("health"), "kind": self.kind, "fault": self.fault, "sched": self.sched,
               "hero_state": h.get("hero_state"), "vy": round((h.get("vel") or [0, 0])[1], 2), "clip": _clip(s),
               "latched": x["lat"]}
        if self.fault in (FAULT_TRIGGER, FAULT_MENU):
            self.inner.sc.inject_fault("QF", f"injected fault ({self.kind})")
            self.log["trigger_f"] = f
            if self.fault == FAULT_TRIGGER:
                self.done = True
        if self.fault in (FAULT_HIT, FAULT_MENU):
            side = "left" if h.get("facing", 1) > 0 else "right"
            self.fut = self.link.rpc_async("hurt.special", kind="damage", amount=int(h["health"]) - 1,
                                           hazard="ENEMY", side=side)
        self.log["sent"].append(row)
