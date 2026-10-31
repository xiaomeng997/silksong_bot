"""SLAM_PLAY vocabulary for knife chain v0.1: the anchor and the primitives, each in one category (chain_v01.CATEGORIES):

  A  observation / math / hold filter: the STATE, the observed history (sent / latched keys, FSM states and times,
     seen hits), geometry (walls, body boxes, slash reach), physics (fall time, y projection), the in-flight /
     hold prediction (her x at the mask frame from the keys in flight)
  B  key template: walk toward a band (one step to its middle, none inside), drop keys, the planning modules' plans
     as masks, direction keys
  C  planning module (online search, NOT migrated: to become an offline table or the native planner's job):
     ClawStrike.plan, the air_chain strike check / search, their plan bookkeeping

Business branches (start, walk, jump, press, side, early slashes and Clawline fallbacks)
are the accepted knife_chain_slam_v01.json records, with the delivery's explicitly unsupported paths still excluded. Model helpers are reused from this development tree (slam_play.hero_x / control / clappers / _fall_frames / SlamPlay._in_reach / _cs_box / _cs_s_hit,
claw_strike, air_chain, cast_stab.rune_spans, two_play.guard_hit).

Ported from accepted v0.1; no runtime imports from the Opus directory.
Source SHA256: 8a5dc27c3719b6c527fa615750b366bae7b74854d6aaf1982356f742ff45c199
"""
from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace

from . import knife_chain_eval as CV
from ssbot.combat import air_chain as AC
from ssbot.combat import claw_strike as CS
from ssbot.combat import jump_behind as JB
from ssbot.combat import slam_play as SP

M_L, M_R, M_D, M_J, M_A, M_DASH = SP.M_L, SP.M_R, SP.M_D, SP.M_J, SP.M_A, SP.M_DASH
M_CLAW = CS.M_CLAW
SEND = SP.SEND_AHEAD
P = CV.Prims()
CV.register_core(P)

FLAGS = ("ENABLED", "GAME_CLOCK", "LATE", "SIDE", "NEAR", "EARLY", "TWO_PLAY", "TWO_HANDOFF", "TWO_TIGHT", "TWO_SIDE",
         "TWO_RUNEGATE", "STRIKEGUARD", "REACH_NAME")


def build_cfg() -> dict:
    """PlayCfg (SSBOT_FORUM_SLAM_PLAY_SET applied), CsCfg as cs_<name>, the switches, the module constants the
    records use (slam_play / claw_strike / air_chain literals), the log variable."""
    c = asdict(SP.PlayCfg.from_env())
    for k, v in asdict(CS.CsCfg.from_env()).items():
        c["cs_" + k] = v
    for k in FLAGS:
        c[k] = bool(getattr(SP, k))
    c.update(CLAWSTRIKE=bool(CS.CLAWSTRIKE), AIRSTRIKE=bool(CS.AIRSTRIKE), AIRCHAIN=bool(AC.AIRCHAIN),
             JUMP_BEHIND=bool(JB.ENABLED))
    c.update(WALK_U=SP.WALK_U, NEAR_V=SP.NEAR_V, NEAR_STAND_U=SP.NEAR_STAND_U, NEAR_BAND_LO=SP.NEAR_BAND_LO,
             WALL_L=SP.WALL_L, WALL_R=SP.WALL_R, SEND=SEND, CS_KEEP_F=SP.CS_KEEP_F, AC_KEEP_F=AC.KEEP_F,
             HALF_W=CS.HALF_W, bounce_vy=6.0, bounce_by=14, land_after=8, vx_stop=8.25, log_var="cs_log",
             stand_lo=c["stand"][0], stand_hi=c["stand"][1], reach_lo=c["reach"][0], reach_hi=c["reach"][1],
             band_lo=c["band"][0], band_hi=c["band"][1], cs_trigger=c["cs_trigger"],
             TWO_JUMP_ST=list(SP.TWO_JUMP_ST), TWO_SLAM_U=SP.TWO_SLAM_U, TWO_CAST_U=SP.TWO_CAST_U,
             TWO_BODY_U=SP.TWO_BODY_U, TWO_RUNE=list(SP.TWO_RUNE))
    return c


# ---- observations ----------------------------------------------------------------------------------------------

class Obs:
    """One tick's observations (the STATE of frame f and the policy's contact / input / clock / hero model)."""

    def __init__(self, f, s, ground, accepting, t, sim, guard, bombs, e, st, tin):
        self.f, self.s, self.ground, self.accepting, self.t = f, s, ground, accepting, t
        self.sim, self.guard, self.bombs = sim, guard, bombs
        self.e, self.st, self.tin = e, st, tin
        h = s.get("hero") or {}
        self.h = h
        self.hp = int(h.get("health") or 0)
        self.F = f + SEND

    @property
    def cx(self) -> float:
        return float(self.e["pos"][0])

    @property
    def cy(self) -> float:
        return float(self.e["pos"][1])

    @property
    def hx(self) -> float:
        return SP.hero_x(self.s)

    @property
    def vx(self) -> float:
        return float((self.h.get("vel") or [0, 0])[0])

    @property
    def vy(self) -> float:
        return float((self.h.get("vel") or [0, 0])[1])

    @property
    def atk_cd(self):
        cd = ((self.h.get("tm") or {}).get("atk_cd"))
        return None if cd is None else float(cd)

    @property
    def facing(self):
        fc = self.h.get("facing")
        return None if fc is None else float(fc)

    @property
    def silk(self) -> int:
        return int(self.h.get("silk") or 0)

    @property
    def can_harpoon(self) -> bool:
        return bool((self.h.get("can") or {}).get("harpoon", True))

    @property
    def box_bottom(self) -> float:
        hb = self.h.get("box") or [0, SP.FLOOR_Y - 1.56, 0, 0]
        return float(hb[1]) - (SP.FLOOR_Y - 1.56)

    @property
    def y_pos(self) -> float:
        return float((self.h.get("pos") or [0.0, SP.FLOOR_Y])[1])


OBS_NAMES = ("f", "F", "s", "ground", "accepting", "t", "sim", "guard", "bombs", "e", "st", "tin", "h", "hp", "cx",
             "cy", "hx", "vx", "vy", "atk_cd", "facing", "silk", "can_harpoon", "box_bottom", "y_pos")
#   the interpreter-context attributes a record may read as "obs.<name>" (the binder's observation names)


def xrel(x) -> float:
    return (x.obs.hx - x.obs.cx) * x.v["face"]


# ---- the anchor ----------------------------------------------------------------------------------------------------

class SlamAnchor:
    """What opens and closes a run (chain record `anchor`): the target (the Clapper whose Control enters the antic
    state, handled slams not looked at again until it leaves the slam states), the clock (game frames from the antic
    entry + SEND), the s0 event (its first Slam 0 tick), the hurt abort, the same-tick second look after a landed
    close (reopen_after_done), the external entry dispatcher (no active run: the entry links listed in
    external_entries, history from self.hist)."""

    def __init__(self, chains: dict, cfg: dict):
        a = chains["slam_jump"].anchor
        self.reopen_rule = a.get("reopen_after_done") or {}
        self.entry_links = list(a.get("external_entries") or [])
        self.start = (a["start_chain"], a["start_link"])
        self.antic_state = a["antic_state"]
        self.slam_states = tuple(a["slam_states"])
        self.new_antic_f = a["new_antic_frames"]
        self.keep_after = a["keep_while"]
        self.chains = chains
        self.var_defaults = {k: v for k, v in chains["slam_jump"].vars.items() if not k.startswith("tmp.")}
        self.cfg = cfg
        self.hist = None                      # external entry: the observed history (replay: HistView)
        self.external = False                 # external entry on (cut-in tests)

    def reset(self, R) -> None:
        R.run = None
        R.done = []
        self.closed_iid = None
        self.closed: set = set()
        self.jfam: dict = {}
        self.rune: dict = {}
        self.t = 0.0
        self.ho = None
        self.rg_circ: dict = {}
        self.csx = None
        self.cs_declines: dict = {}
        self._start_cache: dict = {}          # derived scratch, never stored on borrowed HistView
        self._args = None
        self.entries: list = []               # external entries made [f, link, sources]
        self.handled_antics: set = set()      # external entry: antics (first tick) this runner closed a run of

    def count_decline(self, why: str) -> None:
        self.cs_declines[why] = self.cs_declines.get(why, 0) + 1

    # -- observation memory (slam_play._two_pick / _rg_observe) --

    def pick(self, R, s: dict, t: float):
        cs = SP.clappers(s)
        run = R.run
        for o in cs:
            st = SP.control(o)[0]
            iid = o.get("iid")
            if st not in self.slam_states and (run is None or run.v["iid"] != iid):
                self.closed.discard(iid)
            if st in ("Cast Slam Antic", "Cast Slam Antic 2"):
                self.jfam[iid] = "jc"
                self.rune.pop(iid, None)
            elif st == "Jump Antic":
                self.jfam[iid] = "j"
            elif st in ("Slam 2", "Slam Recover", "Idle") and self.jfam.get(iid) == "jc":
                self.jfam[iid] = "jc_landed"
                self.rune[iid] = (float(o["pos"][0]), 1 if o.get("flipX") else -1, t)
            elif st in (self.antic_state, "Spell Antic", "Evade Scuttle"):
                self.jfam.pop(iid, None)
        if run is not None:
            return next((o for o in cs if o.get("iid") == run.v["iid"]), None)
        hx = SP.hero_x(s) if (s.get("hero") or {}).get("box") or (s.get("hero") or {}).get("pos") else 0.0
        antic = [o for o in cs if SP.control(o)[0] == self.antic_state and o.get("iid") not in self.closed]
        if antic:
            return min(antic, key=lambda o: abs(float(o["pos"][0]) - hx))
        return next((o for o in cs if o.get("iid") not in self.closed), None)

    def rg_observe(self, s: dict, t: float) -> None:
        from ssbot.combat import cast_stab as _cst
        for lo, hi, ciid, lit in _cst.rune_spans(s):
            c = self.rg_circ.setdefault(ciid, {"t0": t, "lit": False, "burst": False, "cx": 0.5 * (lo + hi)})
            if abs(c["cx"] - 0.5 * (lo + hi)) > 0.5 or (c["burst"] and lit):
                c.update(t0=t, lit=False, burst=False, cx=0.5 * (lo + hi))
            if lit:
                c["lit"] = True
            elif c["lit"]:
                c["burst"] = True

    # -- run life --

    def phase(self, R, run) -> str:
        return R.link(run.chain, run.link).phase

    def close(self, x, kind: str, why: str) -> None:
        R, run = x.R, x.run
        if run is None:
            return
        ph = self.phase(R, run)
        if self.cfg["TWO_HANDOFF"] and self.cfg["TWO_PLAY"] and kind == "done" and run.v.get("k_press") is not None:
            self.ho = (run.v["iid"], self.t)
        if run.v.get("antic_first") is not None:
            self.handled_antics.add(run.v["antic_first"])
        run.v["phase_end"] = kind if (ph in ("walk", "jump", "air", "after") or kind == "abort") else ph
        run.v["why"] = run.v.get("why") or why
        run.closed = kind
        R.done.append(run)
        self.closed_iid = run.v["iid"]
        if self.cfg["TWO_PLAY"]:
            self.closed.add(run.v["iid"])
        R.run = None
        x.run = None

    def reopen_wanted(self, why: str) -> bool:
        r = self.reopen_rule
        return bool(r) and why == r.get("why") and all(self.cfg.get(k) for k in r.get("cfg_all", ()))

    def reopen(self, x):
        f, s, ground, accepting, t_game, skip, sim, guard, _ = self._args
        return self.step(x.R, f, s, ground, accepting, t_game, skip, sim, guard, None)

    def require_slam0(self, x, seen_frame):
        cutoff = getattr(x.R, "observation_cutoff", None)
        if cutoff is not None and seen_frame is not None and seen_frame > cutoff:
            raise CV.ChainObservationNotReady("Slam 0 observation lacks two-frame lead")

    def read_value(self, x, name, value):
        # Absence of Slam 0 does not block antic-clock attacks. Only a rule
        # reading an actual observed Slam 0 may incur the native causal gate.
        if name in ("s0", "ks0") and value is not None:
            self.require_slam0(x, x.v.get("s0"))

    def clock(self, x, name: str):
        v = x.v
        k = v["k"]
        if name == "antic":
            return k
        if name == "s0":
            self.require_slam0(x, v.get("s0"))
            return None if v.get("ks0") is None else k - v["ks0"]
        if name == "press":
            return None if v.get("k_press") is None else k - v["k_press"]
        if name == "jump":
            return None if v.get("k_jump") is None else k - v["k_jump"]
        if name == "turn":
            return None if v.get("k_turn") is None else k - v["k_turn"]
        if name == "mask":
            return x.obs.F
        if name == "claw_press":
            return None if v.get("cs") is None else x.obs.F - v["cs"].f_press
        if name == "strike_press":
            return None if v.get("cs_strike") is None else x.obs.F - v["cs_strike"].f_press
        raise KeyError(name)

    def _new_run(self, R, e, f, tin, ta):
        v = dict(self.var_defaults)
        v.update(iid=e.get("iid"), fa=int(f - round(tin * 60.0)), face=1 if e.get("flipX") else -1, ta=ta,
                 k_early=[], cs_log=[])
        return CV.Run(self.start[0], self.start[1], v)

    def step(self, R, f, s, ground, accepting, t_game, skip, sim, guard, bombs):
        c = self.cfg
        self._start_cache = {}
        self._args = (f, s, ground, accepting, t_game, skip, sim, guard, bombs)
        t = f / 60.0 if t_game is None else float(t_game)
        self.t = t
        e = self.pick(R, s, t) if c["TWO_PLAY"] else SP.clapper(s)
        if (c["TWO_RUNEGATE"] and c["TWO_PLAY"]) or c["CLAWSTRIKE"]:
            self.rg_observe(s, t)
        if skip and e is not None and e.get("iid") in skip:
            if R.run is not None and R.run.v["iid"] in skip:
                self.close(CV.X(R, R.run, None), "abort", "asw")
            return None
        st, tin = SP.control(e)
        run = R.run
        ta = (f - round(tin * 60.0)) / 60.0 if t_game is None else t - tin
        new_antic = run is not None and st == self.antic_state and abs(ta - run.v["ta"]) * 60.0 > self.new_antic_f
        if run is not None and (e is None or e.get("iid") != run.v["iid"] or new_antic or (
                st not in self.slam_states and not (self.phase(R, run) == self.keep_after[0]
                                                    and run.v[self.keep_after[1]]))):
            ph = self.phase(R, run)
            self.close(CV.X(R, run, None), "done" if ph in ("after", "air", "jump") else ph, "slam over")
            run = None
            if new_antic:
                self.closed_iid = None
        if st not in self.slam_states or (e is not None and e.get("iid") != self.closed_iid):
            self.closed_iid = None
        if run is None:
            if self.external and e is not None and e.get("iid") != self.closed_iid \
                    and e.get("iid") not in self.closed:
                run = self.external_entry(R, f, s, ground, accepting, t, sim, guard, bombs, e, st, tin)
                if run is None:
                    return None
            else:
                if st != self.antic_state or (e is not None and e.get("iid") == self.closed_iid):
                    return None
                run = R.run = self._new_run(R, e, f, tin, ta)
                self.restore_observed_land(R, run, f, s, ground, accepting, t, sim, guard, bombs, e, st, tin)
                if (c["TWO_HANDOFF"] and c["TWO_PLAY"] and self.ho is not None and self.ho[0] != run.v["iid"]
                        and (t - self.ho[1]) * 60.0 <= SP.HO_GAP_F):
                    run.v["ho_cand"] = True
        v = run.v
        obs = Obs(f, s, ground, accepting, t, sim, guard, bombs, e, st, tin)
        if st == "Slam 0" and v["s0"] is None:
            v["s0"] = f
            v["ks0"] = int(round(((t if t_game is None else t - tin) - v["ta"]) * 60.0))
        k = int(round((t - v["ta"]) * 60.0)) + SEND + c["lag"]
        v["k"] = k
        x = CV.X(R, run, obs)
        if v.get("ho_cand"):
            v["ho_cand"] = False
            if c["LATE"] and k <= c["k_jump_late2"] and run.link == "look":
                v["late"] = v["handoff"] = True
        if v["hp0"] is not None and obs.hp < v["hp0"]:
            self.close(x, "abort", "hurt")
            return None
        return R.eval_link(x)

    # -- external entry (no active run) --

    def restore_observed_land(self, R, run, f, s, ground, accepting, t, sim, guard, bombs, e, st, tin):
        """Recover only an observed early-air approach, without inventing sends.

        A missing decision/receipt keeps the general external dispatcher off.
        Still, actual observations can prove she was already in the air before
        k_air_max and has not left the land situation. Reuse that entry's own
        causal history/guards; no unselected draft or modeled action survives.
        """
        H = self.hist
        k = int(round((t - run.v["ta"]) * 60.0)) + SEND + self.cfg["lag"]
        if (not getattr(self, "b2_strict_observations", False) or H is None or H.cut != f or ground or st != self.antic_state or
                not self.cfg["air"] or k <= self.cfg["k_air_max"]):
            return False
        an = H.antic(run.v["iid"], self.antic_state, self.slam_states)
        if (an is None or an["fa"] != run.v["fa"] or an["face"] != run.v["face"] or
                abs(an["ta"] - run.v["ta"]) > 1e-6 or an["first_tick"] in self.handled_antics):
            return False
        # Probe on an independent provisional record. In particular, a failed
        # probe must not leak late/k_air into the ordinary fresh look fallback.
        v = dict(run.v)
        v.update(k=k, antic_first=an["first_tick"])
        candidate = CV.Run("slam_jump", "enter_land", v)
        x = CV.X(R, candidate, Obs(f, s, ground, accepting, t, sim, guard, bombs, e, st, tin))
        x.tmp["antic"] = an
        target = R.probe_entry(x, R.link("slam_jump", "enter_land"))
        ka = v.get("k_air")
        if (target != "land" or type(ka) is not int or ka > self.cfg["k_air_max"] or
                any(v.get(n) is None for n in R.link("slam_jump", "land").needs)):
            return False
        run.link = "land"
        # Only the two historical approach facts and ordinary observed hp0
        # travel. Never inherit an old Run, planner plan, or proposed key list.
        run.v.update(k_air=ka, late=bool(v["late"]), hp0=v["hp0"], antic_first=an["first_tick"])
        run.sent = list(H.sent_since(run.v["fa"], f))
        run.entered = {"f": f, "link": "slam_jump.land", "via": "observed_early_air",
                       "sources": {"k_air": "observed_history", "late": "observed_history", "hp0": "events"}}
        run.path.append([f, "observed early air -> slam_jump.land", "enter"])
        self.entries.append([f, "slam_jump.land", "observed_early_air"])
        return True

    def situations(self, R, f, s, ground, accepting, t, sim, guard, bombs, e, st, tin, first_only=False) -> list:
        """The external entry links (priority order) that apply now: [(entry link, target, vars, sources)]. Each is
        probed on its own provisional run (the anchor's identity from the history: the latest antic of the target,
        its Slam 0); only the current STATE and self.hist are read (no run of anyone)."""
        out = []
        H = self.hist
        if H is None:
            return out
        an = H.antic(e.get("iid"), self.antic_state, self.slam_states)
        if an is None or an["first_tick"] in self.handled_antics:
            return out
        k = int(round((t - an["ta"]) * 60.0)) + SEND + self.cfg["lag"]
        if k > self.cfg["k_end"]:
            return out
        s0 = H.slam0(an)
        for lid in self.entry_links:
            cid, name = lid.split(".", 1)
            lk = R.link(cid, name)
            v = dict(self.var_defaults)
            v.update(iid=e.get("iid"), fa=an["fa"], face=an["face"], ta=an["ta"], k=k, k_early=[], cs_log=[],
                     antic_first=an["first_tick"])
            if s0 is not None:
                v["s0"], v["ks0"] = s0
            run = CV.Run(cid, name, v)
            x = CV.X(R, run, Obs(f, s, ground, accepting, t, sim, guard, bombs, e, st, tin))
            x.tmp["antic"] = an
            target = R.probe_entry(x, lk)
            if target is None:
                continue
            tc, tl = R._target(run, target)
            miss = [n for n in R.link(tc, tl).needs if v.get(n) is None]
            if miss:
                continue
            out.append((lid, f"{tc}.{tl}", v, dict((lk.provenance or {}).get("recover_sources") or {})))
            if first_only:
                break
        return out

    def external_entry(self, R, f, s, ground, accepting, t, sim, guard, bombs, e, st, tin):
        sits = self.situations(R, f, s, ground, accepting, t, sim, guard, bombs, e, st, tin, first_only=True)
        if not sits:
            return None
        via, target, v, src = sits[0]
        cid, name = target.split(".", 1)
        run = R.run = CV.Run(cid, name, v)
        run.sent = list(self.hist.sent_since(v["fa"], f))
        run.entered = {"f": f, "link": target, "via": via, "sources": src}
        run.path.append([f, f"external {via} -> {target}", "enter"])
        self.entries.append([f, target, via])
        return run

    # -- the record (slam_play.SlamPlay.runs_rec's row) --

    def rec(self, R, run) -> list:
        v = run.v
        ph = v.get("phase_end") or R.link(run.chain, run.link).phase
        row = [v["iid"], v["fa"], ph, v["why"], v["k_start"], v["k_jump"], v["k_press"], v["bounced"], v["ks0"],
               v["k_air"], v["k"], v["side_why"]]
        if v.get("handoff") or v["cs_log"]:
            row += [bool(v.get("handoff")), None, v["k_slash"], [], None]
        if v["cs_log"]:
            row += [None if v["cs"] is None else v["cs"].row(), v["cs_log"], v["cs_k_press"], v["cs_k_ctrl"],
                    None if v["cs_strike"] is None else v["cs_strike"].row(), v["as_air"]]
        return row


VAR_DEFAULTS = {"iid": None, "fa": None, "face": None, "ta": None, "antic_first": None, "why": "", "k_start": None, "x_start": None, "k_jump": None, "x_jump": None, "k_press": None,
                "s0": None, "ks0": None, "k": 0, "hp0": None, "bounced": False, "over_dir": None, "k_dash": None,
                "k_air": None, "k_press_plan": None, "stand": None, "band": None, "late": False, "side_why": "",
                "near": None, "near_u": 0.0, "k_turn": None, "k_slash": None, "k_early": None, "handoff": False,
                "ho_cand": False, "cs": None, "cs_toward": 0, "cs_k_press": None, "cs_k_ctrl": None,
                "cs_strike": None, "cs_log": None, "cs_hit": False, "cs_next": 0, "as_air": False,
                "phase_end": None}


# ==== A: observation / math / hold filter ==========================================================================

@P.guard("flag", doc="a boolean chain parameter")
def g_flag(x, name):
    return bool(x.cfg[name])


@P.guard("cmp", doc="a op b (None: false)")
def g_cmp(x, a, op, b):
    if a is None or b is None:
        return False
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}[op]


@P.guard("is_none", doc="v is None")
def g_is_none(x, v):
    return v is None


@P.guard("truthy", doc="bool(v)")
def g_truthy(x, v):
    return bool(v)


@P.guard("eq", doc="a == b")
def g_eq(x, a, b):
    return a == b


@P.guard("in_range", doc="lo <= v <= hi")
def g_in_range(x, v, lo, hi):
    return lo <= v <= hi


@P.guard("has", doc="the mask has every bit of bits")
def g_has(x, m, bits):
    return m is not None and (int(m) & int(bits)) == int(bits) and int(bits) != 0


@P.guard("ground", doc="cState.onGround (the backend's contact)")
def g_ground(x):
    return x.obs.ground


@P.guard("accepting", doc="hero_accepting_input")
def g_accepting(x):
    return x.obs.accepting


@P.guard("has_sim", doc="the policy's hero model of this tick exists")
def g_has_sim(x):
    return x.obs.sim is not None


@P.guard("harpoon_clip", doc="her animation clip is a Harpoon clip")
def g_harpoon(x):
    return str((x.obs.h.get("anim") or {}).get("clip") or "").startswith("Harpoon")


@P.guard("s_hit", doc="a hit event on the target this STATE that is not the Harpoon's")
def g_s_hit(x):
    if getattr(x.R.anchor,"b2_strict_observations",False) is True:
        from .knife_chain_observations import target_pogo_hit
        return target_pogo_hit(x.obs.s,x.v["iid"])
    return SP.SlamPlay._cs_s_hit(x.obs.s, SimpleNamespace(iid=x.v["iid"]))


@P.guard("inside_arena", doc="WALL_L + pad <= x <= WALL_R - pad")
def g_inside(x, v, pad):
    return SP.WALL_L + pad <= v <= SP.WALL_R - pad


@P.guard("in_reach", doc="the side slash from x xw facing look meets the target's body box (collider span)")
def g_in_reach(x, xw, look):
    return SP.SlamPlay._in_reach(x.obs.e, x.obs.cx, x.v["face"], xw, look)


@P.value("other_clapper_danger", doc="the first spec (states, max distance to tx) another live Clapper's control state "
                                     "matches, or its jump cast's rune circle over tx: the spec's reason, else None")
def v_other_danger(x, tx, specs, rune_span):
    A = x.R.anchor
    e, s, t = x.obs.e, x.obs.s, x.obs.t
    for o in SP.clappers(s):
        if o.get("iid") == e.get("iid"):
            continue
        st = SP.control(o)[0]
        d = abs(float(o["pos"][0]) - tx)
        for sp in specs:
            if st in sp["states"] and (sp["max_d"] is None or d < sp["max_d"]):
                return sp["why"].format(st=st)
        rc = A.rune.get(o.get("iid"))
        if rc is not None and x.cfg["TWO_RUNEGATE"]:
            raise NotImplementedError("TWO_RUNEGATE: not encoded")
        if rc is not None and t <= rc[2] + rune_span[2] and rune_span[0] <= (tx - rc[0]) * rc[1] <= rune_span[1]:
            return "other rune circle"
    return None


@P.guard("other_in_way", doc="another Clapper's body box (+ her half width) between her and the target")
def g_other_in_way(x):
    o = _other(x)
    if o is None:
        return False
    ob = SP.SlamPlay._cs_box(o)
    lo, hi = sorted((x.obs.hx, x.obs.cx))
    return ob[0] - CS.HALF_W < hi and ob[2] + CS.HALF_W > lo


@P.guard("other_busy", doc="another Clapper exists and its control state is not Idle / Walk")
def g_other_busy(x):
    o = _other(x)
    return o is not None and SP.control(o)[0] not in ("Idle", "Walk")


@P.guard("other_in_antic", doc="another Clapper (not handled) is in the antic state")
def g_other_in_antic(x):
    for o in SP.clappers(x.obs.s):
        if o.get("iid") != x.v["iid"] and SP.control(o)[0] == "Slam Antic" and o.get("iid") not in x.R.anchor.closed:
            return True
    return False


@P.guard("room_gate", doc="claw room rule: she can leave the hammer's 13 u on her side (CsCfg.room)")
def g_room_gate(x):
    cx, hx = x.obs.cx, x.obs.hx
    o = _other(x)
    out_x = cx + x.v["face"] * 13.0
    return SP.WALL_L + 0.5 <= out_x <= SP.WALL_R - 0.5 and (
        o is None or not min(hx, out_x) - 0.5 < float(o["pos"][0]) < max(hx, out_x) + 0.5)


@P.guard("claw_path_bomb", doc="a lit / forecast small-rune bomb of another Clapper on the Clawline's path")
def g_claw_bomb(x, plan):
    bk = x.obs.bombs
    if bk is None or not len(bk):
        return False
    # Original h2 _claw_bomb checks another owner's rows only. Own delayed
    # hazards remain in RangeSupport and B2Geometry, including the approach.
    if all(int(row[0])==x.v["iid"] for row in bk):
        return False
    raise NotImplementedError("bombs of another Clapper on the Clawline path: not encoded (two Clappers)")


@P.guard("claw_path_circle", doc="a big rune circle lit or still to burst over the Clawline's x span (memory)")
def g_claw_circle(x):
    from ssbot.combat import cast_stab as _cst
    A = x.R.anchor
    cx, hx = x.obs.cx, x.obs.hx
    d = 1.0 if cx > hx else -1.0
    x_stop = cx - d * (CS.BODY_FRONT + 2.1 + CS.HALF_W)
    lo, hi = min(hx, x_stop) - 0.5, max(hx, x_stop) + 0.5
    for a, b, ciid, lit in _cst.rune_spans(x.obs.s):
        c = A.rg_circ.get(ciid)
        pending = lit or (c is not None and not c["burst"] and x.obs.t - c["t0"] < 1.6)
        if pending and a < hi and b > lo:
            return True
    return False


@P.guard("guard_spot", doc="TWO_GUARD: a landing at xx meets another Clapper's danger span (land / rune)")
def g_guard_spot(x, xx):
    from ssbot.combat import two_play as _tp
    if x.cfg["STRIKEGUARD"]:
        raise NotImplementedError("STRIKEGUARD: not encoded")
    if x.obs.guard is None:
        return False
    return _tp.guard_hit(x.obs.guard, xx - 0.25, xx + 0.25, kinds=("land", "rune"), own=x.v["iid"]) is not None


def _other(x):
    return next((o for o in SP.clappers(x.obs.s) if o.get("iid") != x.v["iid"]), None)


@P.value("x", doc="her box centre relative to the target's centre along its antic facing (u, + in front)")
def v_x(x):
    return xrel(x)


@P.value("fall_frames", doc="frames to the floor in a free fall from her y / vy (slam_play._fall_frames)")
def v_fall(x):
    return SP._fall_frames(x.obs.s)


@P.value("room", doc="the target's centre to the wall on world side d (u)")
def v_room(x, d):
    cx = x.obs.cx
    return (cx - SP.WALL_L) if d < 0 else (SP.WALL_R - cx)


@P.value("near_fit", doc="a landing u from the target on side d inside the walls (pad), down to near_u_min; None")
def v_near_fit(x, d, u):
    c = x.cfg
    room = v_room(x, d) - c["wall_pad"]
    if room >= u:
        return u
    return room if room >= c["near_u_min"] else None


@P.value("nearest_other_dir", doc="world direction from the target to the nearest other live Clapper (0: none / "
                                  "same x)")
def v_nearest_other(x):
    cx = x.obs.cx
    others = [float(o["pos"][0]) for o in x.obs.s.get("ents") or ()
              if o.get("type_key") == SP.CLAPPER and not o.get("is_dead") and (o.get("hp") or 0) > 0 and o.get("pos")
              and o.get("iid") != x.obs.e.get("iid")]
    if not others:
        return 0
    ox = min(others, key=lambda xx: abs(xx - cx))
    return 0 if ox == cx else (1 if ox > cx else -1)


@P.value("x_at_mask", doc="hold / in-flight prediction: her x at the mask frame from the run's keys in flight "
                          "(per frame speed u), else her vx")
def v_x_at_mask(x, u):
    c = x.cfg
    vx = x.obs.vx
    run = x.run
    xw = x.obs.hx
    for fr in range(x.obs.f + 1, x.obs.f + SEND + c["lag"]):
        m = next((m for f2, m in reversed(run.sent) if f2 <= fr), None) if run is not None and run.sent else None
        xw += vx / 60.0 if m is None else ((1 if m & M_R else 0) - (1 if m & M_L else 0)) * u
    return xw


@P.value("y_at_slash", doc="her y above the standing y at the mask frame + 1 (free flight: vy, gravity)")
def v_y_at_slash(x):
    c = x.cfg
    y = x.obs.y_pos - SP.FLOOR_Y
    vy = x.obs.vy
    for _ in range(SEND + c["lag"] + 1):
        y += vy / 60.0
        vy -= SP.GRAV / 60.0
    return y


@P.value("last_sent", doc="history: the last mask this run sent (0: none)")
def v_last_sent(x):
    return x.run.sent[-1][1] if x.run.sent else 0


@P.value("plan_row", doc="a plan record's row (log)")
def v_plan_row(x, plan):
    return None if plan is None else plan.row()


# ==== B: key templates =============================================================================================

@P.gen("walk_to_band", doc="one step toward the band's middle at the mask frame (in-flight prediction), none inside")
def gen_walk(x, m, band):
    lo, hi = band
    xw = v_x_at_mask(x, x.cfg["WALK_U"])
    cx, face = x.obs.cx, x.v["face"]
    xr = (xw - cx) * face
    if lo <= xr <= hi:
        return m
    tx = cx + face * 0.5 * (lo + hi)
    return m | (M_R if tx > xw else M_L)


@P.gen("drop", doc="clear the given key bits from the mask so far")
def gen_drop(x, m, bits):
    return m & ~int(bits)


@P.gen("claw_plan_mask", doc="the Clawline plan's keys at the mask frame (claw_strike.plan_mask)")
def gen_claw(x, m):
    return m | CS.plan_mask(x.v["cs"], x.obs.F, x.v["cs_toward"])


@P.gen("strike_plan_mask", doc="the strike plan's keys at the mask frame (air_chain.mask_at)")
def gen_strike(x, m):
    return m | AC.mask_at(x.v["cs_strike"], x.obs.F)


@P.gen("dir_key", doc="the L / R key toward world direction d (d > 0: R) added to the mask")
def gen_dir_key(x, m, d):
    return m | (M_R if d > 0 else M_L)


@P.value("dir_bits", cat="B", doc="the L / R key bit toward world direction d (d > 0: R)")
def v_dir_bits(x, d):
    return M_R if d > 0 else M_L


@P.direction("side", doc="the key toward the chosen side (near)")
def d_side(x):
    return M_R if x.v["near"] > 0 else M_L


@P.direction("turn_key", doc="the key toward the target from the chosen side (-near)")
def d_turn(x):
    return M_R if -x.v["near"] > 0 else M_L


@P.direction("over", doc="the key toward over_dir (none when 0)")
def d_over(x):
    return (M_R if x.v["over_dir"] > 0 else M_L) if x.v["over_dir"] else 0


# ==== C: planning modules (not migrated; called through `act` with a "store" target) ===============================

def _csx(x):
    A = x.R.anchor
    if A.csx is None:
        A.csx = CS.ClawStrike(CS.CsCfg.from_env())
    return A.csx


def _cs_ctx(x):
    v = x.v
    sim = x.obs.sim
    fc = x.obs.h.get("facing")
    kb0 = int(round((x.obs.t - v["ta"]) * 60.0)) - (x.obs.f - sim.fo)
    return CS.CsCtx(s_iid=v["iid"], s_x=x.obs.cx, s_y=x.obs.cy, s_face=v["face"], kb0=kb0, hero_x=x.obs.hx,
                    face=1 if fc is None or float(fc) >= 0 else -1, other_box=SP.SlamPlay._cs_box(_other(x)),
                    tls=AC.timelines())


@P.planner("claw_plan", doc="ClawStrike.plan(sim, ctx, ground, accepting, hop_until, p_only): the (hop, P) whose "
                            "every Clawline variant has a strike plan; CsPlan or None -> store (tmp.plan_ms: wall ms)")
def pl_claw(x, store, ground, accepting, hop_until=None, p_only=None):
    import time
    cs = _csx(x)
    sim = x.obs.sim
    if cs.params is None:
        cs.params, cs.terrain = sim.params, sim.terrain
    kwargs = {"hop_until": hop_until, "p_only": p_only}
    if getattr(x.R.anchor, "b2_strict_observations", False):
        from .knife_chain_jump import B2_HOOK_JUMP_LEAD
        prior = x.v.get("cs")
        if prior is not None and prior.hop:
            # Keep the ORIGINAL jump's absolute floor during p_only checks
            # and fallback searches. A later tick cannot pull it earlier.
            kwargs["p_min"] = int(prior.f0) + B2_HOOK_JUMP_LEAD
        elif ground and accepting:
            kwargs["p_min"] = int(sim.f) + 2 + B2_HOOK_JUMP_LEAD
    t0 = time.perf_counter()
    res = cs.plan(sim, _cs_ctx(x), ground, accepting, **kwargs)
    x.tmp["plan_ms"] = round(1e3 * (time.perf_counter() - t0), 1)
    CV.store(x, store, res)


@P.planner("plan_adopt", doc="a re-planned CsPlan keeps the committed hop's frames (f0, hop) -> store")
def pl_adopt(x, store, q, p):
    if q is not p:
        q.f0, q.hop = p.f0, p.hop
    CV.store(x, store, q)


def _strike_ctx(x):
    v = x.v
    sim = x.obs.sim
    a_entry = int(round(x.obs.f - (x.obs.t - v["ta"]) * 60.0))
    fc = x.obs.h.get("facing")
    actx = AC.Ctx(b_iid=v["iid"], b_x=x.obs.cx, b_y=x.obs.cy, b_face=v["face"], kb0=sim.fo - a_entry,
                  a_box=SP.SlamPlay._cs_box(_other(x)), hero_x=x.obs.hx,
                  face=1 if fc is None or float(fc) >= 0 else -1, tls=AC.timelines())
    return actx, a_entry


@P.planner("strike_check", doc="air_chain.check: the committed strike plan still passes from this tick's model "
                               "-> store (bool)")
def pl_strike_check(x, store, plan):
    actx, _ = _strike_ctx(x)
    CV.store(x, store, bool(AC.check(x.obs.sim, actx, plan)))


@P.planner("strike_search", doc="air_chain.evaluate over the press_k x drifts grid from control; the best by "
                                "|k_press - 47|, drift, contact (n_ok set), or None -> store")
def pl_strike_search(x, store, k_ctrl, toward):
    cfg = _csx(x).cfg
    v = x.v
    F, sim = x.obs.F, x.obs.sim
    actx, a_entry = _strike_ctx(x)
    f_min = max(F, a_entry + k_ctrl + cfg.cd_f - 1, a_entry + cfg.press_k[0])
    plans = []
    for fp in range(f_min, a_entry + cfg.press_k[1] + 1):
        for d in cfg.drifts:
            for dk in ((0,) if d == 0 else (toward, -toward)):
                m_ = 0 if dk == 0 else (M_R if dk > 0 else M_L)
                plans.append(AC.Plan(F, m_, F + d, None, None, fp, fp - a_entry, v["iid"]))
    ok = AC.evaluate(sim, actx, plans, F) if plans else []
    best = None
    if ok:
        ok.sort(key=lambda q_: (abs(q_.k_press - 47), q_.d_end - q_.f0, q_.c_strike - q_.f_press))
        ok[0].n_ok = len(ok)
        best = ok[0]
    CV.store(x, store, best)


@P.planner("plan_mark", doc="the strike plan's sent presses (this tick's mask): its first down slash, else the strike "
                            "-> store ('down' / 'struck' / None)")
def pl_mark(x, store, plan):
    out = None
    if plan.f_down is not None and plan.pressed_down is None and x.mask & M_A:
        plan.pressed_down = x.obs.F
        out = "down"
    elif plan.pressed is None and x.obs.F >= plan.f_press and x.mask & M_A:
        plan.pressed = x.obs.F
        out = "struck"
    CV.store(x, store, out)


# ==== A: the run's own log (diagnostics; cfg log_var) ===============================================================

def _log(x):
    return x.v.get(x.cfg.get("log_var", "log")) or []


@P.guard("log_has", doc="the run's log has an entry tagged tag (and, given, reason why at [2])")
def g_log_has(x, tag, why=None):
    return any(len(e) > 1 and e[1] == tag and (why is None or (len(e) > 2 and e[2] == why)) for e in _log(x))


@P.guard("log_last_is", doc="the run's last log entry is tagged tag")
def g_log_last_is(x, tag):
    lg = _log(x)
    return bool(lg) and lg[-1][1] == tag


@P.value("other_state", doc="another live Clapper's control state (None: none)")
def v_other_state(x):
    o = _other(x)
    return None if o is None else SP.control(o)[0]


# ==== A: generic observed-history primitives (external entry; the HistView cut at the entry tick) ===================

class ObservedClaw:
    """A Clawline seen in the sent keys: its press's mask frame and direction (the run's plan is not observable)."""

    def __init__(self, f_press: int, toward: int):
        self.f_press, self.toward = f_press, toward
        self.f0, self.hop = None, 0

    def row(self) -> list:
        return ["observed", self.f_press, self.toward]


def _H(x):
    return x.R.anchor.hist, x.tmp["antic"]


@P.value("h_edge_F", doc="history: the first mask frame (this antic, <= now + 1) where all bits begin, without the "
                         "`without` bits, after / before given frames, at antic frame >= min_k; None")
def v_h_edge_F(x, bits, without=0, after_F=None, before_F=None, min_k=None):
    H, an = _H(x)
    for F in H.edges(int(bits), an, after_F=after_F, before_F=before_F, without=int(without or 0)):
        if min_k is None or H.k_of(F, an) >= min_k:
            return F
    return None


@P.value("h_edges_k", doc="history: antic frames k of every edge of bits (without `without`) before before_F")
def v_h_edges_k(x, bits, without=0, before_F=None):
    H, an = _H(x)
    return [H.k_of(F, an) for F in H.edges(int(bits), an, before_F=before_F, without=int(without or 0))]


@P.value("h_k", doc="history: the antic frame k of a mask frame (the tick that sent it)")
def v_h_k(x, F):
    if F is None:
        return None
    H, an = _H(x)
    return H.k_of(F, an)


@P.value("h_tick_k", doc="history: the antic frame k of a tick's mask frame (tick + SEND)")
def v_h_tick_k(x, f):
    if f is None:
        return None
    H, an = _H(x)
    return H.k_of_tick(f, an)


@P.value("h_dir_F", doc="history: the first mask frame after after_F with exactly one of L / R (not exclude_dir)")
def v_h_dir_F(x, after_F, exclude_dir=None):
    if after_F is None:
        return None
    H, an = _H(x)
    hit = H.first_dir(an, after_F, exclude_dir=exclude_dir)
    return None if hit is None else hit[0]


@P.value("h_dir_at", doc="history: the L / R direction (+1 / -1) of the mask sent for frame F (0: none / both)")
def v_h_dir_at(x, F):
    if F is None:
        return None
    H, _ = _H(x)
    m = H.sent.get(F, 0)
    l_, r_ = bool(m & M_L), bool(m & M_R)
    return 0 if l_ == r_ else (1 if r_ else -1)


@P.value("h_tick_f", doc="history: the first stepped tick (this antic, before now) with antic frame k > after_k "
                         "where cond holds: vy_gt (her vy > arg), s_hit (a hit on the target, not the Harpoon's), "
                         "ground, ctrl (input back, no Harpoon clip, mask frame > arg + 12)")
def v_h_tick_f(x, cond, after_k=None, arg=None):
    H, an = _H(x)
    return H.first_tick(an, after_k, cond, arg, x.v["iid"], before_f=x.obs.f)


@P.value("h_hp_prev", doc="history: her HP at the last stepped tick before now (none: now); a live run's hp0 (a "
                          "drop since its start would have ended it)")
def v_h_hp_prev(x):
    H = x.R.anchor.hist
    for r in reversed(H.rows):
        if r[0] < x.obs.f:
            return int(((r[1].get("hero") or {}).get("health")) or 0)
    return x.obs.hp


START_LINKS = ("look", "land")


@P.value("h_start", doc="history + the chain's own start links: look / land re-run by a fresh runner over the stepped "
                        "ticks of this antic before now, planning modules off (no hero model: no Clawline try); "
                        "{link: look | land | walk (started) | closed, k_start, k_air, late, stand, band, x_start}")
def v_h_start(x):
    H, an = _H(x)
    cache = x.R.anchor._start_cache
    key = (an["iid"], an["first_tick"], x.obs.f)
    if key in cache:
        return cache[key]
    R, A0 = x.R, x.R.anchor
    shadow = R.fork_empty(SlamAnchor(R.chains, A0.cfg))
    out = {"link": "look", "k_start": None, "k_air": None, "late": False, "stand": None, "band": None,
           "x_start": None}
    for f, s, t, g, a in H.ticks_since(an):
        if f >= x.obs.f:
            break
        shadow.step(f, s, g, a, t_game=t if SP.GAME_CLOCK else None, skip=None, sim=None, guard=[], bombs=None)
        run = shadow.run
        if run is None or run.v.get("iid") != an["iid"]:
            out = dict(out, link="closed")
            break
        v = run.v
        out = {"link": run.link if run.link in START_LINKS else "walk", "k_start": v["k_start"], "k_air": v["k_air"],
               "late": bool(v["late"]), "stand": v["stand"], "band": v["band"], "x_start": v["x_start"]}
        if out["link"] not in START_LINKS:
            break
    cache[key] = out
    return out


@P.value("h_claw", doc="history: the Clawline seen in the sent keys (its first CLAW mask frame, direction)")
def v_h_claw(x):
    H, an = _H(x)
    hit = H.key_edge(M_CLAW, an)
    if hit is None:
        return None
    m = H.sent[hit[0]]
    return ObservedClaw(hit[0], 1 if m & M_R else -1)


@P.value("h_side_decision", doc="history + the chain's own side rules: the side decided at the first stepped tick "
                                "after the bounce with Slam 0 + near_decide_s0 (before now): near / near_u / "
                                "side_why / f")
def v_h_side(x, want):
    d = x.R.anchor.side_decision(x)
    return None if d is None else d[want]


def _side_decision(self, x):
    """Evaluate the chain's side_decision rule set on the recorded observation of the decision tick (no script state:
    the press from the sent keys, the bounce from her vy / the hit seen, Slam 0 from the FSM)."""
    H, an = _H(x)
    R = x.R
    v0 = x.v
    kp = v0.get("k_press")
    s0 = H.slam0(an)
    if kp is None or s0 is None:
        return None
    f_s0, ks0 = s0
    self.require_slam0(x, f_s0)
    cond = "s_hit" if v0.get("cs") is not None else "vy_gt"
    fb = H.first_tick(an, kp, cond, self.cfg["bounce_vy"], v0["iid"], before_f=x.obs.f)
    if fb is None:
        return None
    f_d = None
    for f, s, t, g, a in H.ticks_since(an):
        if f >= x.obs.f:
            break
        if f < fb or f < f_s0:
            continue
        if H.k_of_tick(f, an) - ks0 >= self.cfg["near_decide_s0"]:
            f_d = f
            break
    if f_d is None:
        return None
    s_d = H.state(f_d)
    e, (st, tin) = H._ctl(s_d, v0["iid"])
    if e is None:
        return None
    obs = Obs(f_d, s_d, H.ground(f_d), H.accepting(f_d), H.t_game(f_d), None, x.obs.guard, None, e, st, tin)
    v = dict(self.var_defaults)
    v.update(iid=v0["iid"], fa=v0["fa"], face=v0["face"], ta=v0["ta"], k=H.k_of_tick(f_d, an), s0=f_s0, ks0=ks0,
             bounced=True, k_press=kp, near=None, cs=v0.get("cs"), k_early=[], cs_log=[])
    xd = CV.X(R, CV.Run("slam_jump", "after", v), obs)
    for r in self.chains["slam_jump"].rulesets["side_decision"]:
        if not R.guard(xd, r.when):
            continue
        if r.do == "abort" and str(r.why).startswith(CV.NOT_ENCODED):
            raise NotImplementedError(str(r.why))
        if r.do == "set":
            R._apply_set(xd, r.set)
    if v["near"] is None:
        return None
    return {"near": v["near"], "near_u": v["near_u"], "side_why": v["side_why"], "f": f_d,
            "F": f_d + SEND}


SlamAnchor.side_decision = _side_decision


LITERAL_NAMES = frozenset(['<', '<=', '>', '>=', 'A', 'AIRSTRIKE', 'CLAW', 'CLAWSTRIKE', 'D', 'DASH', 'D|A', 'EARLY', 'F', 'J', 'JUMP_BEHIND', 'LATE', 'NEAR', 'SIDE', 'Slam Antic', 'TWO_HANDOFF', 'TWO_PLAY', 'TWO_SIDE', 'band', 'behind', 'clear', 'ctrl', 'f0', 'f_press', 'force', 'ground', 'guard', 'ho_aim', 'hop', 'k_air', 'k_start', 'land', 'late', 'link', 'look', 'n_ok', 'near', 'near_u', 'old', 'room', 's_hit', 'side_why', 'stand', 'struck', 'toward', 'two', 'vy_gt', 'walk', 'wall', 'x_start'])


def make_runner(chains, *, cfg=None):
    """Bound family evaluator; C-category searches remain explicit unmigrated modules."""
    cfg = chains["slam_jump"].cfg if cfg is None else cfg
    return CV.ChainRunner(chains, SlamAnchor(chains, cfg), P, cfg0=cfg,
                          observation_names=OBS_NAMES, literal_names=LITERAL_NAMES, context_names={"sent"})


def load_runner():
    """Load the accepted rule records, using this process's explicit legacy configuration."""
    import json
    from pathlib import Path
    from .knife_chain_format import chains_from_json
    chains = chains_from_json(json.loads(Path(__file__).with_name("knife_chain_slam_v01.json").read_text("utf-8")))
    cfg = build_cfg()
    for off in ("TWO_TIGHT", "TWO_SIDE", "TWO_RUNEGATE", "STRIKEGUARD", "AIRCHAIN", "AIRSTRIKE"):
        if cfg[off]:
            raise ValueError(f"{off} is not encoded in chain v0.1")
    cfg["two_danger_specs"] = [
        {"states": list(cfg["TWO_JUMP_ST"]), "max_d": None, "why": "other {st}"},
        {"states": ["Slam 0", "Slam 1", "Slam Effects?", "Slam 2"], "max_d": cfg["TWO_SLAM_U"], "why": "other {st}"},
        {"states": ["Spell Antic", "Cast 1", "Cast 2"], "max_d": cfg["TWO_CAST_U"], "why": "other {st}"},
        {"states": ["Slam Recover"], "max_d": cfg["TWO_BODY_U"], "why": "other Slam Recover"}]
    for chain in chains.values():
        chain.cfg = cfg.copy()
    return make_runner(chains)
