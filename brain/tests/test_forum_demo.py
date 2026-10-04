"""ssbot.tools.forum_demo: damage source attribution, attempt segmentation, multi-hit chains, kills and key counts on a
synthetic scan."""
from ssbot.ipc.framing import BIT
from ssbot.tools.forum_demo import anim_kind, attempts, killer, source_type, summarise


def test_source_type():
    assert source_type("Song Pilgrim 03 (2)/Whip Hit 2") == ("Song Pilgrim 03", "Whip Hit 2", "Song Pilgrim 03 (2)")
    assert source_type("Wave 1/Song Reed") == ("Song Reed", "body", "Song Reed")
    assert source_type("Colliders/Collider ParryStance")[:2] == ("Song Administrator", "Collider ParryStance")
    assert source_type("Throwing Bell(Clone)")[:2] == ("Pilgrim 03 Song", "Throwing Bell")
    assert source_type("rune slam(Clone)/damager")[:2] == ("Song Heavy Sentry", "rune slam")
    assert source_type("EmptyObjectFromNull/Song Automaton Tiny(Clone)")[:2] == ("Song Automaton Tiny", "body")
    assert source_type(None) == (None, None, None)


def test_killer_and_anim_kind():
    assert killer("WildSlash Enemy Damager") == "garmond"
    assert killer("DashUpper Slash") == "hero"
    assert killer("Damager") == "cogfly"
    assert killer("Enemy Damager") == "bell"
    assert anim_kind("Dash Upper Recovery") == "attack_recovery"
    assert anim_kind("SlashAlt") == "attack"
    assert anim_kind("Umbrella Float") == "air_move"
    assert anim_kind("BindCharge Air") == "bind"


def _row(f, bid=None, started=None, wave=None, mask=0, hp=7):
    return dict(f=f, udt=1 / 60, ts=1.0, scene="Hang_04", gs=4, paused=False, x=30.0, y=4.57, vx=0.0, vy=0.0,
                facing=1, box=[29.75, 3.5, 30.25, 5.6], hp=hp, silk=3, cs=[2, 0], anim="Idle", inv=False, cog=4,
                crest="Reaper", spell="Idle", mask=mask, move=[0.0, 0.0], b_id=bid, b_wave=wave, b_started=started,
                b_completed=False if bid else None, b_enemies=None)


MULTI = "Hero_Hornet(Clone)/Roar and Wound States/Multihit:CallMethodProper"
FINAL = "Hero_Hornet(Clone)/Roar and Wound States/Final Hit:DamageHeroDirectly"


def test_attempts_chain_death_and_keys():
    rows, ents, allies = [], [], []
    for f in range(100, 400):
        bid = 7 if f < 300 else (8 if f >= 320 else None)
        wave = None if bid is None else (0 if f < 200 or bid == 8 else 1)
        mask = (1 << BIT["attack"]) if f % 20 < 3 else 0
        rows.append(_row(f, bid, True if bid else None, wave, mask))
        reed = (1, "Song Reed", 31.0, 6.0, 55, "Stab Antic" if f < 250 else "Stab 1", 0.1, False)
        ents.append([reed] if bid else [])
        allies.append([])
    events = [
        (150, "hp", {"delta": -1, "src": "TakeHealth", "source": "Wave 1/Song Reed", "h": 6}),
        (180, "hit", {"ent": 2, "type_key": "Song Pilgrim 01", "src": "Slash", "dead": True, "hp_before": 4}),
        (181, "hit", {"ent": 2, "type_key": "Song Pilgrim 01", "src": "Slash", "dead": True, "hp_before": 0}),
        (260, "hp", {"delta": -1, "src": "TakeHealth", "fsm": MULTI, "source": MULTI, "h": 5}),
        (280, "hp", {"delta": -1, "src": "TakeHealth", "fsm": FINAL, "source": "Song Reed/ParrySlash Hit", "h": 4}),
        (290, "die", {"source": "Song Reed/Stab Hit 1", "h": 0}),
    ]
    atts = attempts({"rows": rows, "ents": ents, "allies": allies, "events": events, "snaps": {}})
    assert [a["battle_id"] for a in atts] == [7, 8]
    a = atts[0]
    assert a["outcome"] == "died" and a["f0"] == 100 and a["f1"] == 290
    assert [w["wave"] for w in a["waves"]] == [0, 1] and a["wave_reached"] == 1
    assert len(a["hits"]) == 2 and a["masks_lost"] == 3
    chain = a["hits"][1]
    assert chain["chain"] == 2 and chain["masks"] == 2 and chain["f"] == 260 and chain["type"] == "Song Reed"
    assert chain["family"] == "RE_STAB" and chain["attacker_state"] == "Stab 1"
    assert len(a["kills"]) == 1 and a["kills"][0]["by"] == "hero"      # the hp_before 0 repeat is not a kill
    assert a["death"]["type"] == "Song Reed" and a["death"]["wave"] == 1
    assert a["presses"]["attack"] == 9           # taps at 120, 140, ..., 280 (the one at 100 is held at f0)
    assert atts[1]["outcome"] == "left"
    sm = summarise(atts)
    assert sm["hits"] == 2 and sm["masks"] == 3 and sm["details"]["chain_masks"] == {2: 1}
