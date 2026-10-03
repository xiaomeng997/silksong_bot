"""Behaviour tables for every enemy type of a multi-enemy fight (M2 W8: the High Halls Forum gauntlet, Hang_04 /
Hang_04_boss; DESIGN §3.5.8; docs/facts/1.0.30000/forum.md).

    b = GauntletBuilder(FORUM_SPECS)
    fights, skipped = run_fights(Path(r"C:\\ssbot\\data\\runs\\m2\\<run>"))   # behaviour_tables.run_fights
    for fight in fights:
        b.scan(fight)
    for tk, builder in b.builders.items():    # one BehaviourBuilder per enemy type
        builder.write(out_dir, allow_failed=True)

The single-boss builder (ssbot.knowledge.behaviour_tables) follows one entity type with one Control FSM and takes every
other damage entity for the boss's hazard. In the Forum up to six enemies of up to four types fight at once, several
of one type (two Choristors in wave 1, two Ministers, two Maestros with three summons each, the two Choir Clappers of
the finale), so GauntletBuilder splits each STATE into one stream per enemy entity (a "subject": the HealthManager
root's iid, which the "fsm" events carry as "ent" and the "hit" events as "ent") and feeds every stream to its own
FightScanner, all of one type into that type's BehaviourBuilder:
  ents     the subject's own entity, plus the hazard entities it owns (BehaviourSpec.projectiles: Choir Bellbearer's
           Throwing Bell, Reed's Song Reed Pin Projectile, Clawmaiden's Spear). A hazard is given to an owner when it
           is first seen or arms again (a pooled bell is reused): among the live subjects whose type throws it, those in
           an attack first, then the nearest.
  events   the subject's "fsm" events (ent == iid) and "hit" events (ent == iid), and the hero's "damage" /
           "damage_blocked" events whose source belongs to it: the source path names the enemy's GameObject ("Wave 1/
           Song Pilgrim 01", "Song Pilgrim 03 (3)/Body Damager") or a hazard type; a name several live subjects share
           (the Maestro's "Song Automaton Tiny(Clone)" summons, the waiting wave-12 "Song Reed") goes to the one in play
           nearest to the hero's box.
Enemies whose body hurts on contact while they walk or fly between attacks get an idle family
(BehaviourSpec.idle_family, "<P>_IDLE": from a decision state until the next attack), so the support covers them all
the time; a kill ends the instance ("hit" with dead, BehaviourSpec.death_on_kill: most of these Control FSMs have no
death state).

Families per type from the Control FSMs of the Hang_04_boss scene bundle (UnityPy dump, fsm_enemy_*.txt in the facts
session) and the first recording of run 20261002_221727 (instance 2, fo_A): attack-start states, the decision (hub)
states between attacks and the waiting states. Names: the game's journal (EnemyDeathEffects.journalRecord ->
EnemyJournalRecord.displayName -> EN_Journal), forum.md §9.
"""
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from ssbot.ipc.ents import DAMAGE_SRC
from ssbot.knowledge.behaviour_tables import (
    N_FOLDS,
    BehaviourBuilder,
    BehaviourSpec,
    Fight,
    FightScanner,
    _r,
    fight_states,
    match_source,
    multi_wounder_threat,
    support_threat,
)
from ssbot.train.encounters import FORUM
from ssbot.train.gauntlet import in_play, type_key

# flipX (EntityExporter: transform scale x < 0 XOR sprite FlipX) is False while these sprites face -x (FaceObjectV2
# spriteFacesRight 0 in every Forum enemy's Control FSM): mirror -1 for flipX False, +1 for True
FACES_LEFT = (-1, 1)


# Hazard entities exported under a shared GameObject name, told apart by their circle radius (run 20261002_221727 i2
# ep0; the damage events' sources name the parent: "rune bomb small(Clone)/damager" etc.): the Clapper's Bomb Cast
# bombs (r 2.166, 1 mask), the rune of its Jump Cast (r 7.187, 2 masks), the Clawmaiden's spear blast (r 3.553, 2)
HAZARD_ALIASES: dict[str, tuple[tuple[float, str], ...]] = {
    "damager": ((2.166, "rune bomb small"), (7.187, "rune slam"), (3.553, "handmaiden_spear_silk_explosion")),
}
ALIAS_TOL_U = 0.05
SNAP_F = 600          # frames of per-frame subject snapshots kept for blocked stretches reported late


def hazard_type(e: dict) -> str:
    """The entity's type_key, or its alias (HAZARD_ALIASES) when it is a shared name with a known radius."""
    tk = e.get("type_key") or ""
    alias = HAZARD_ALIASES.get(tk)
    if alias:
        for c in e.get("colliders") or ():
            r = c.get("r")
            if r is not None:
                for r0, name in alias:
                    if abs(r - r0) <= ALIAS_TOL_U:
                        return name
    return tk


def _spec(enemy: str, boss_type: str, fsm: str, hp: int, prefix: str, attacks: dict[str, str],
          decisions: tuple[str, ...], dormant: tuple[str, ...], death: tuple[str, ...] = (),
          spawns: tuple[tuple[str, tuple[str, ...]], ...] = (),
          rest: tuple[str, ...] = ("Init", "Dormant")) -> BehaviourSpec:
    fams = tuple(dict.fromkeys(attacks.values()))
    idle = f"{prefix}_IDLE"
    return BehaviourSpec(
        enemy=enemy, scene=FORUM.scene, boss_type=boss_type, control_fsm=fsm, hp=hp, dormant=dormant,
        death_states=death, attack_starts=attacks, decision_states=decisions, dir_states={},
        directed=fams + (idle,), phase_marks={}, phases={"P1": "the whole fight (no phases)"}, initial_phase="P1",
        world_fixed=(), rest_states=rest, flip_mirror=FACES_LEFT, arena_x=FORUM.arena_x, floor_y=FORUM.floor_y,
        idle_family=idle, death_on_kill=True, projectiles=tuple(p for p, _ in spawns), spawns=spawns,
        multi_wounder=True)


FORUM_SPECS: dict[str, BehaviourSpec] = {s.boss_type: s for s in (
    # Choir Clapper: 230 HP, body and Slam Collider 1/2 deal 2; wave 7 alone, the finale as a pair
    _spec("ChoirClapper", "Song Heavy Sentry", "Control", 230, "CC",
          {"Slam Antic": "CC_SLAM", "Jump Antic": "CC_JUMP", "Spell Antic": "CC_CAST",
           "Cast Slam Antic": "CC_JUMP_CAST", "Cast Jump Antic": "CC_JUMP_CAST", "Evade Scuttle": "CC_EVADE",
           "Drop Antic": "CC_ENTRY", "Idle Roar Antic": "CC_ENTRY"},
          ("Walk", "Close Range", "Far Range", "Idle", "After Scuttle", "Dmg Attack", "Escape Jump", "Avoid Type",
           "Z Set", "Sing", "Sing End", "Extra Idle", "Start Battle"),
          ("Init", "Rest", "On-plane Rest", "Start Idle", "Start Battle?", "Start Battle 2"),
          spawns=(("rune bomb small", ("CC_CAST",)), ("rune slam", ("CC_JUMP_CAST",))),
          rest=("Init", "Dormant", "Idle")),
    # Clawmaiden: 48 HP, Spear 2, the rest 1; drains silk (Silk Suck FSM)
    _spec("Clawmaiden", "Song Handmaiden", "Control", 48, "CM",
          {"Slash Antic": "CM_SLASH", "Fly To Slash": "CM_SLASH", "Spin Antic": "CM_SPIN",
           "Tele Out Antic": "CM_TELE", "Tele Out Antic 2": "CM_TELE", "Reappear Pause": "CM_TELE",
           "Wake": "CM_ENTRY", "Quick Wake": "CM_ENTRY", "Called By Enemy": "CM_TELE"},
          ("Fly", "Set Distance", "Tele?", "Start", "Startle", "Sing", "Sing End"),
          ("Init", "Pause", "Respawner?", "Rest", "Silk?", "Silkless", "Set FG", "Set BG", "Off Plane",
           "Battle Ready", "Burned?", "Wake Away Pause", "Away"),
          death=("Zero HP", "Die", "Burn Death", "Sim Death"),
          spawns=(("Spear", ("CM_SPIN",)), ("handmaiden_spear_silk_explosion", ("CM_SPIN",))),
          rest=("Init", "Dormant", "Idle", "Deactivate")),
    # Minister: 60 HP, parry stance and its counter
    _spec("Minister", "Song Administrator", "Control", 60, "MI",
          {"Attack Antic": "MI_CHARGE", "Shove Horizontally?": "MI_PARRY", "Parry Stance Antic": "MI_PARRY",
           "Evade Antic": "MI_EVADE", "Battle Fly In": "MI_ENTRY", "Wake Fly In Pause": "MI_ENTRY",
           "Check Pos": "MI_ENTRY", "Ground Wake": "MI_ENTRY", "Wall Wake": "MI_ENTRY"},
          ("Chase", "Range Check", "Attack Choice", "Evade?", "Retreat?", "Set Attack Time", "ReAlert", "Sing",
           "Sing End", "Unalert Patrol", "Off Wall Idle", "Start Off Wall"),
          ("Init", "Fly In Ready", "Rest Ground", "Rest Wall")),
    # Maestro: 65 HP, summons three Song Automaton Tiny
    _spec("Maestro", "Song Pilgrim Maestro", "Control", 65, "MA",
          {"Fire Antic": "MA_SLASH", "Call": "MA_SUMMON", "Defend Start": "MA_DEFEND", "Point Start": "MA_POINT",
           "Check Pos": "MA_ENTRY", "Fly In": "MA_ENTRY", "Wake Thread": "MA_ENTRY"},
          ("Fly", "Forum Fly", "Chase", "Summon?", "Attack Choice", "Ready Formation", "Startle", "First Startle",
           "Sing", "Sing End", "Notify Sing End", "Idle"),
          ("Init", "Pause", "Fly In Pause", "Fly In Ready", "Start Idle", "Corpse Spawn", "Init Old"),
          death=("Death",)),
    # the Maestro's summon (pooled, 28 HP, body 1): not a wave member, comes back after a kill
    _spec("MaestroAutomaton", "Song Automaton Tiny", "Control", 28, "AT",
          {"Fire Ready": "AT_FIRE", "Defend Ready": "AT_DEFEND", "Swoop In Pause": "AT_ENTRY",
           "Leave Pause": "AT_LEAVE"},
          ("Ready", "Returned"),
          ("Dead", "Pause", "Die", "Set Pos", "Left"), death=("Death Fx",)),
    # Reed: 55 HP, stab, javelin throw, parry stance
    _spec("Reed", "Song Reed", "Control", 55, "RE",
          {"Stab Pos": "RE_STAB", "Stab Antic": "RE_STAB", "Merch Slash Antic": "RE_STAB",
           "Throw Range": "RE_THROW", "Throw Antic Anim": "RE_THROW", "Defend Start": "RE_DEFEND",
           "Evade Antic": "RE_EVADE", "Battle Fly In": "RE_ENTRY", "Fly In": "RE_ENTRY", "Set Battle": "RE_ENTRY",
           "Wake Pause": "RE_ENTRY", "Deparent?": "RE_ENTRY", "Battle Wait": "RE_ENTRY",
           "Battle Wait 2": "RE_ENTRY"},
          ("Alert", "Choice", "Startle", "Alert Begin", "Sing", "Sing End", "Move Cancel", "Back To Idle", "Idle",
           "Patrol Point", "Go Left", "Go Right", "Go Up", "Go Down", "Merchant Look", "Merchant Option",
           "Merchant Shout"),
          ("Init", "Custom Target?", "Target Hero", "Custom Target", "Fly In Ready", "Sleep", "Off Plane?", "FG",
           "BG", "Start Patrol", "Start Praying", "Preacher Pray", "Merchant Start", "Fly In Instant"),
          death=("Death",), spawns=(("Song Reed Pin Projectile", ("RE_THROW",)),),
          rest=("Init", "Dormant", "Stick", "Deactivate", "Recycle")),
    # Envoy: 38 HP, slash / jump slash / charge / hop slash, an ambush from the wave-0 start
    _spec("Envoy", "Song Pilgrim 01", "Attack", 38, "EN",
          {"Slash Antic": "EN_SLASH", "JumpSlash Antic": "EN_JUMPSLASH", "Charge Antic": "EN_CHARGE",
           "HopSlash Antic": "EN_HOPSLASH", "Ambush Antic": "EN_AMBUSH", "Wake Pause": "EN_ENTRY",
           "Wake": "EN_ENTRY", "Black Thread Wake": "EN_ENTRY"},
          ("Walker", "Attack Wait", "Leader?", "Hop Up?", "Alert Followers", "Pray", "Pray End", "Leader Voice",
           "Wake End"),
          ("Init", "Ambush Ready", "Sleep", "Off Plane?", "FG", "BG", "Custom Target?", "Target Hero",
           "Custom Target", "Start Praying", "Create Noise"),
          death=("Zero HP",)),
    # Choristor: 55 HP, slash (combo), whip (Whip Hit 1-6 deal 0), jump spin slash
    _spec("Choristor", "Song Pilgrim 03", "Attack", 55, "CH",
          {"Slash Antic": "CH_SLASH", "Whip Antic": "CH_WHIP", "Jump Antic": "CH_JUMP", "Enter Idle": "CH_ENTRY",
           "Battle Wake": "CH_ENTRY", "Wake Pause": "CH_ENTRY", "Wake Thread": "CH_ENTRY", "Quick Wake": "CH_ENTRY"},
          ("Battle Idle", "Move Start", "Hop Antic", "Hop Check", "Hop Back", "Hop Forward", "Hop Up", "Ground Check",
           "Hop Land", "Attack Choice", "Slash Check", "Whip Check", "Jump Check", "BT?", "Cancel To Hop Back",
           "Unalert Tick?", "Alert Tick", "Unalert Tick", "Unalert", "Alert", "Sing", "Sing End", "Walker",
           "Force Unalert", "Detach From Art 2", "End Voice"),
          ("Init", "Wait", "Start Praying", "Preacher Pray", "Sleep", "Off Plane?", "FG", "BG", "Custom Target?",
           "Target Hero", "Custom Target", "Pray Voice?", "FG Jump", "Set Battler")),
    # Choir Bellbearer: 35 HP, flies, throws bells (Throwing Bell, gravity 1.0, bounces)
    _spec("ChoirBellbearer", "Pilgrim 03 Song", "Control", 35, "CB",
          {"Throw Evade": "CB_THROW", "Evade Antic": "CB_EVADE", "Battle Fly In": "CB_ENTRY", "Fly In": "CB_ENTRY",
           "Battle Wait": "CB_ENTRY", "Wake Pause 2": "CB_ENTRY", "Wake Thread": "CB_ENTRY"},
          ("In Range", "Out of Range", "Insta Throw?", "Startle", "Sing", "Sing End", "Go Left", "Go Right", "Go Up",
           "Go Down", "Unalert Patrol", "To Patrol", "To Start", "Follow", "Active"),
          ("Init", "Fly In Ready", "Sleep", "Off Plane?", "FG", "BG", "Preacher Pray", "Start Patrol Voice",
           "Fly In Instant"),
          spawns=(("Throwing Bell", ("CB_THROW",)),), rest=("Init", "Dormant", "Deactivate", "Recycle", "Break")),
)}

GAUNTLET_SPECS: dict[str, dict[str, BehaviourSpec]] = {"Forum": FORUM_SPECS}


@dataclass(slots=True)
class _Subject:
    iid: int
    type_key: str
    scanner: FightScanner
    name: str | None = None          # its GameObject name (the Control FSM's "obj", else its root collider's name)
    ent: dict | None = None          # its latest export
    seen_f: int = -1
    first_f: int = -1
    n0: int = 0                      # its builder's instance count when it was created


def _armed(e: dict, rest: tuple[str, ...]) -> bool:
    cols = [c for c in e.get("colliders") or () if support_threat(c)]
    fsms = e.get("fsms") or ()
    st = fsms[0].get("state") if fsms else None
    return bool(cols) or (st is not None and st not in rest)


def _gap(b: tuple, box: tuple) -> float:
    return math.hypot(max(b[0] - box[2], box[0] - b[2], 0.0), max(b[1] - box[3], box[1] - b[3], 0.0))


def _box_dist(e: dict | None, box: tuple | None, name: str | None = None) -> tuple[float, float]:
    """(distance from the hero box to the entity's enabled damage colliders (only those named name, if given; inf
    without any), distance to its transform position)."""
    if box is None or e is None:
        return math.inf, math.inf
    best = math.inf
    for c in e.get("colliders") or ():
        if not (support_threat(c) or multi_wounder_threat(c)) or (name and c.get("name") != name):
            continue
        v = c.get("verts_world") or ()
        if len(v) >= 2:
            best = min(best, _gap((min(v[0::2]), min(v[1::2]), max(v[0::2]), max(v[1::2])), box))
    p = e.get("pos")
    return best, (_gap((p[0], p[1], p[0], p[1]), box) if p else math.inf)


class GauntletBuilder:
    """One BehaviourBuilder per enemy type of a multi-enemy fight, fed per enemy entity (see the module docstring)."""

    def __init__(self, specs: dict[str, BehaviourSpec], keep_paths: bool = False):
        self.specs = specs
        self.builders = {tk: BehaviourBuilder(s, keep_paths=keep_paths) for tk, s in specs.items()}
        self.proj_types: dict[str, list[str]] = defaultdict(list)    # hazard prefix -> enemy types that spawn it
        for tk, s in specs.items():
            for p in s.projectiles:
                self.proj_types[p].append(tk)
        self.counters: Counter = Counter()
        self.recordings: dict[str, int] = {}
        self.fights: list[dict] = []
        self._last_owner: dict[str, tuple[int, int]] = {}
        self._f = 0

    def _proj_owner_types(self, tk: str) -> list[str]:
        return [o for p, os in self.proj_types.items() if tk == p or tk.startswith(p) for o in os]

    def scan(self, fight: Fight, states=None) -> dict:
        """Scan one fight (its STATEs from fight_states unless given); returns a summary (subjects per type,
        instances added per type)."""
        rec = str(fight.path)
        fold = self.recordings.setdefault(rec, len(self.recordings)) % N_FOLDS
        for b in self.builders.values():
            b._built = None
            b.recordings.setdefault(rec, fold)
        subjects: dict[int, _Subject] = {}
        owner: dict[int, int] = {}          # hazard iid -> owning subject iid
        armed_last: dict[int, bool] = {}
        n_inst0 = {tk: len(b.instances) for tk, b in self.builders.items()}
        frames = 0
        last_f = None
        snaps: dict[int, tuple] = {}         # frame -> (subject iid -> ent, hazards, hero box)
        self._last_owner: dict[str, tuple[int, int]] = {}   # hazard type -> (frame, owner) last seen

        def subject(iid: int, tk: str, f: int) -> _Subject:
            sub = subjects.get(iid)
            if sub is None:
                b = self.builders[tk]
                sc = FightScanner(self.specs[tk], f"{fight.id}/{tk}#{iid}", b, fold)
                sub = subjects[iid] = _Subject(iid, tk, sc, first_f=f, n0=len(b.instances))
            return sub

        for s in fight_states(fight) if states is None else states:
            f = s.get("f")
            if not isinstance(f, int) or (last_f is not None and f <= last_f):
                continue
            last_f = f
            self._f = f
            frames += 1
            hero = s.get("hero") or {}
            hb = hero.get("box")
            box = (float(hb[0]), float(hb[1]), float(hb[2]), float(hb[3])) if hb else None
            per: dict[int, list] = defaultdict(list)
            hazards = []
            for e in s.get("ents") or ():
                tk = e.get("type_key")
                if tk in self.specs:
                    sub = subject(e["iid"], tk, f)
                    sub.ent, sub.seen_f = e, f
                    if sub.name is None:
                        sub.name = next((c["name"] for c in e.get("colliders") or ()
                                         if c.get("name") and (c["name"] == tk or c["name"].startswith(tk + " (")
                                                               or c["name"].startswith(tk + "("))), None)
                    per[e["iid"]].append(e)
                elif tk and int(e.get("src") or 0) & DAMAGE_SRC:
                    ht = hazard_type(e)
                    if self._proj_owner_types(ht):
                        hazards.append(e if ht == tk else {**e, "type_key": ht})
            for e in hazards:
                iid = e["iid"]
                types = self._proj_owner_types(e["type_key"])
                rest = tuple({r for t in types for r in self.specs[t].rest_states})
                armed = _armed(e, rest)
                if iid not in owner or (armed and not armed_last.get(iid, False)):
                    o = self._pick_owner(e, types, subjects, f)
                    if o is not None:
                        owner[iid] = o
                    else:
                        self.counters[f"hazard without an owner: {e['type_key']}"] += 1
                armed_last[iid] = armed
                if iid in owner:
                    per[owner[iid]].append(e)
                    self._last_owner[e["type_key"]] = (f, owner[iid])
            snaps[f] = ({sid: es[0] for sid, es in per.items() if es and es[0].get("type_key") in self.specs},
                        hazards, box)
            snaps.pop(f - SNAP_F, None)
            evs: dict[int, list] = defaultdict(list)
            for ev in s.get("ev") or ():
                k, d = ev.get("k"), ev.get("d") or {}
                if k == "fsm":
                    sid = d.get("ent")
                    tk = type_key(d.get("obj"))
                    if sid not in subjects and tk in self.specs and d.get("fsm") == self.specs[tk].control_fsm:
                        subject(sid, tk, f)
                    sub = subjects.get(sid)
                    if sub is not None:
                        if d.get("fsm") == self.specs[sub.type_key].control_fsm and d.get("obj"):
                            sub.name = d["obj"]
                        evs[sid].append(ev)
                elif k == "hit":
                    sub = subjects.get(d.get("ent"))
                    if sub is not None:
                        evs[sub.iid].append(ev)
                elif k in ("damage", "damage_blocked"):
                    src = str(d.get("source"))
                    # a blocked stretch is reported when it ends and may span several enemies of one name (the
                    # Maestro's summons): each of its frames is attributed on that frame's snapshot
                    if k == "damage_blocked" and isinstance(d.get("first_f"), int) and isinstance(d.get("last_f"), int):
                        parts = [(ff, snaps.get(ff), {**d, "first_f": ff, "last_f": ff})
                                 for ff in range(d["first_f"], d["last_f"] + 1)]
                    else:
                        parts = [(f, None, d)]
                    for ff, snap, dd in parts:
                        sid = self._attribute(src, subjects, owner, *(snap[1:] if snap else (hazards, box)),
                                              ents=snap[0] if snap else None)
                        if sid is None:
                            self.counters[f"hero contacts without an enemy: {src}"] += 1
                            continue
                        sub = subjects[sid]
                        known = {sub.type_key} | {e["type_key"] for e in per.get(sid, ())}
                        if match_source(src, known)[0] is None:
                            # a source naming only a collider child ("Colliders/Collider ParryStance"): put the
                            # subject's name in front so the scanner finds its type
                            dd = {**dd, "source": f"{sub.name or sub.type_key}/{src}"}
                        evs[sid].append({**ev, "d": dd} if dd is not d else ev)
            for sid, sub in subjects.items():
                sub.scanner.feed({"f": f, "dt": s.get("dt"), "hero": hero, "ents": per.get(sid, ()),
                                  "ev": evs.get(sid, ())})
        by_type: Counter = Counter()
        for sub in subjects.values():
            sub.scanner.close()
            b = self.builders[sub.type_key]
            sc = sub.scanner
            by_type[sub.type_key] += 1
            b.fights.append({"id": sc.fight, "kind": fight.kind, "path": str(fight.path), "f0": fight.f0,
                             "f1": fight.f1, "outcome": fight.outcome, "frames": sc.frames, "gaps": sc.gaps,
                             "game_s": _r(sc.T, 2), "subject": sub.name, "died": sc.dead, "fold": fold,
                             "first_f": sub.first_f})
        info = {"id": fight.id, "frames": frames, "subjects": dict(by_type),
                "instances": {tk: len(b.instances) - n_inst0[tk] for tk, b in self.builders.items()
                              if len(b.instances) > n_inst0[tk]}, "fold": fold}
        self.fights.append(info)
        return info

    def _pick_owner(self, e: dict, types: list[str], subjects: dict[int, _Subject], f: int) -> int | None:
        """A hazard's owner when it is first seen or arms again: among the live subjects of the types that spawn it,
        one in an attack that spawns it (BehaviourSpec.spawns) or that ended one within spawn_window_s, else one in
        any attack, then the nearest."""
        cands = [s for s in subjects.values() if s.type_key in types and s.ent is not None and f - s.seen_f < 120]
        if not cands:
            return None
        x, y = e["pos"][0], e["pos"][1]

        def key(s: _Subject):
            spec = self.specs[s.type_key]
            sc = s.scanner
            fams = next((fs for p, fs in spec.spawns if e["type_key"] == p or e["type_key"].startswith(p)), ())
            cur = sc.cur
            spawning = (cur is not None and cur.family in fams) or any(
                i.family in fams and i.t_end is not None and sc.T - i.t_start - i.t_end <= spec.spawn_window_s
                for i in sc.done)
            attacking = cur is not None and cur.family != spec.idle_family
            p = s.ent["pos"]
            return (not spawning, not attacking, s.scanner.dead, math.hypot(p[0] - x, p[1] - y))
        return min(cands, key=key).iid

    def _attribute(self, src: str, subjects: dict[int, _Subject], owner: dict[int, int], hazards: list,
                   box: tuple | None, ents: dict[int, dict] | None = None) -> int | None:
        """The subject a hero contact's source belongs to (see the module docstring). The source names the enemy's
        GameObject, or a hazard type, or only a collider child ("Colliders/Collider ParryStance": the Minister's body
        colliders sit under a "Colliders" child): then the subject exporting an enabled damage collider of that
        name. Several candidates: those in play and alive, then the nearest damage collider to the hero box."""
        parts = [p for p in src.split("/") if p]
        ent = (lambda sb: ents.get(sb.iid, sb.ent)) if ents is not None else (lambda sb: sb.ent)
        cands = [s for s in subjects.values() if s.name and s.name in parts]
        leaf = None
        if not cands:
            tk, _ = match_source(src, set(self.proj_types) | set(self.specs) | {e["type_key"] for e in hazards})
            if tk in self.specs:
                cands = [s for s in subjects.values() if s.type_key == tk]
            elif tk is not None:
                near = [(e, owner[e["iid"]]) for e in hazards if e["iid"] in owner and
                        (e["type_key"] == tk or e["type_key"].startswith(tk))]
                if near:
                    return min(near, key=lambda en: _box_dist(en[0], box))[1]
                last = self._last_owner.get(tk)   # the hazard left the export before its damage event
                if last is not None and self._f - last[0] <= 120 and last[1] in subjects:
                    self.counters["hazard contacts after the hazard left the export (its last owner)"] += 1
                    return last[1]
                return None
            else:
                leaf = parts[-1] if parts else None
                cands = [s for s in subjects.values() if ent(s) is not None and leaf and
                         _box_dist(ent(s), box, leaf)[0] < math.inf]
                if not cands:
                    return None
                self.counters["contacts named by a collider child only (subject exporting it)"] += 1
        if len(cands) > 1:
            # the scanner's dead flag: a kill, until the next attack start (the pooled summons come back)
            live = [s for s in cands if ent(s) is not None and not s.scanner.dead and in_play(ent(s))]
            cands = live or cands
        if len(cands) > 1:
            cands.sort(key=lambda s: _box_dist(ent(s), box, leaf))
            self.counters["contacts with a shared source name (nearest subject)"] += 1
        return cands[0].iid

    def report_rows(self, hours: float | None = None, target: int = 200) -> list[dict]:
        """Attack instances per (type, family) with the rate per hour of episode time and the hours to the target."""
        rows = []
        for tk, b in self.builders.items():
            spec = self.specs[tk]
            n = Counter(i.family for i in b.instances)
            for fam in list(dict.fromkeys(spec.attack_starts.values())) + [spec.idle_family]:
                c = n.get(fam, 0)
                rate = c / hours if hours else None
                rows.append({"type": tk, "enemy": spec.enemy, "family": fam, "n": c,
                             "idle": fam == spec.idle_family,
                             "per_hour": _r(rate, 1) if rate is not None else None,
                             "hours_to_target": (_r(max(0, target - c) / rate, 1) if rate else None)
                             if c < target else 0.0})
        return rows
