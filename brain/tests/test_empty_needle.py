"""The measured empty-needle approach has no enemy-hook/bounce successor."""
import numpy as np
import pytest

from ssbot.combat import knife_chain_empty_needle as N
from ssbot.combat.knife_chain_nominal import NominalUnsupported
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.air_chain import ChainSim
from ssbot.knowledge import kinematics as K,hero2 as H2
from tests.test_shared_strike_approach import flight


def scene(**kwargs):
    _,s,sim=flight(**kwargs)
    sim.start[K.SILK]=3.
    sim.start[K.INV_T]=.2
    return sim


def test_measured_horizontal_flight_and_real_control_contract():
    sim=scene();sim.start[K.AIRDASHED]=1
    before=sim.start.copy();hold=sim.hold.latched.copy()
    made=N.compile_empty(sim,0.,[(8,[34.74,3.015,38.33,6.917])],1)
    assert made.activation_frame==1002 and made.control_frame==1034
    path=made.path
    assert path.through==1034 and len(path.box)==len(path.commands)+1
    assert path.commands[1]==B['R']|B['CLAW'] and sum(bool(m&B['CLAW']) for m in path.commands)==1
    assert path.contact_frame is None and path.press_frame is None and path.end=='control'
    assert not np.any(path.check_flags[2:]&K.F_INVULN)
    end=made.control_state
    assert end[K.AIRDASHED]==1 and end[K.BOUNCE]<0 and end[K.ATTACKING]==0
    assert end[K.VX]==end[K.VY]==0 and end[K.XVX]==pytest.approx(12.45849609375)
    assert end[K.SILK]==2. and end[K.ATK_CD]<=0
    assert end[K.XVXD]==4. and not end[K.GROUND]
    assert not path.box.flags.writeable and not end.flags.writeable
    np.testing.assert_array_equal(before,sim.start);np.testing.assert_array_equal(hold,sim.hold.latched)
    # There is no vertical displacement throughout the dash/catch. This is
    # horizontal Air Needle, not a hooked target's forced upward bounce.
    ys=path.states[K.PY,2+H2.CLAW_THROW_F:]
    assert np.ptp(ys)<1e-10


@pytest.mark.parametrize('late',[0,1,2])
@pytest.mark.parametrize('throw',[8,9])
def test_supported_latch_and_throw_variants_keep_absolute_command(late,throw):
    sim=scene();made=N.compile_empty(sim,0.,[],1,throw_frames=throw,activation_delay=late)
    assert made.path.commands[1]==B['R']|B['CLAW']
    assert made.activation_frame==1002+late and made.control_frame==1002+late+32+(throw-9)
    assert not np.any(made.path.commands[2:]&B['CLAW'])
    assert made.path.assumptions['actual_control_required']


def test_mirror_preserves_height_and_reverses_horizontal_displacement():
    a=scene(x=27.,vx=0.);b=scene(x=27.,vx=0.)
    right=N.compile_empty(a,0.,[],1);left=N.compile_empty(b,0.,[],-1)
    assert right.control_state[K.PX]+left.control_state[K.PX]==pytest.approx(54.)
    np.testing.assert_allclose(right.path.box[:,1],left.path.box[:,1])
    assert left.control_state[K.XVX]==-right.control_state[K.XVX]


@pytest.mark.parametrize('bad',['ground','time_scale','slow_frame','held_claw','queued_claw','no_silk','shuttle','residual','glide'])
def test_unknown_or_different_fsm_entry_does_not_get_a_pure_flight(bad):
    sim=scene()
    if bad=='ground':sim.start[K.GROUND]=1.;sim.start[K.PY]=4.568
    elif bad=='time_scale':sim.start[K.TS]=.5
    elif bad=='slow_frame':sim.params.frame_time=1/30.
    elif bad=='held_claw':sim.hold.latched[0,B['CLAW'].bit_length()-1]=True
    elif bad=='queued_claw':sim.prefix[0]=B['CLAW']
    elif bad=='no_silk':sim.start[K.SILK]=0.
    elif bad=='shuttle':sim.start[K.SHUT]=18.
    elif bad=='residual':sim.start[K.XVX]=3.
    elif bad=='glide':sim.start[K.MODE]=K.M_GLIDE
    with pytest.raises(NominalUnsupported):N.compile_empty(sim,0.,[],1)


@pytest.mark.parametrize('bodies,reason',[
    ([(8,[31.,8.,34.,12.])],'would hook'),  # body inside the ray
    ([(8,[38.2,9.,39.2,10.])],'ram successor'),  # outside ray; hit by forward dash damager
    ([(8,None)],'unknown'),             # missing observed body is unknown, never empty
])
def test_body_hook_ram_and_missing_body_are_not_empty_successors(bodies,reason):
    with pytest.raises((NominalUnsupported,ValueError),match=reason):
        N.compile_empty(scene(vy=0.),0.,bodies,1)


def test_wall_inside_dash_rejects_without_adding_a_wall_bounce_model():
    sim=scene(x=42.,vy=0.)
    sim.terrain=K.Terrain2D.from_boxes([(-200.,-10.,400.,3.015),(48.99,0.,70.,40.)])
    with pytest.raises(NominalUnsupported,match='terrain'):
        N.compile_empty(sim,0.,[],1)


def test_existing_shared_strike_exit_uses_residual_and_can_countersteer():
    from ssbot.combat.knife_chain_transfer import press_now_row
    sim=scene()
    made=N.compile_empty(sim,0.,[],1)
    control=ChainSim(made.control_state.copy(),np.array([0],np.int64),made.path.hold_end,
                     sim.params,sim.terrain,made.control_frame,made.control_frame)
    row=press_now_row(control,np.array([34.74,3.015,38.33,6.917]),made.control_frame+2,0,B['R'])
    assert row is not None and row['approach_direction']==-1
    assert row['press_F']>=made.control_frame+2 and row['contact_frame']>row['press_F']
    assert made.path.contact_frame is None  # exit witness does not credit a hit
