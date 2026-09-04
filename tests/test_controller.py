"""
Tests for controller.py.

Invariant sections from tests/INVARIANTS.md covered here:
    A structural · F control policy

Section F carries safety weight. If test_eclss_never_sheds fails, nothing
else in this suite matters.
"""

import pytest

from tests.names import COMMS_NAME, ECLSS_NAME, SCIENCE_NAME, THERMAL_NAME
from config import (MIN_ACTION_DWELL_HOURS, SOC_RESTORE_THRESHOLD,
                    SOC_SHED_THRESHOLD, TIME_STEP_HOURS)
from controller import AutonomousController, ControlStrategy

PLENTY = 999_000.0        # headroom that fits anything
NONE_ACTED = None


def name_of(load):
    return None if load is None else load.name


# =============================================================================
# A — STRUCTURAL.
# =============================================================================

def test_controller_satisfies_the_interface(controller):
    assert isinstance(controller, ControlStrategy)
    assert isinstance(controller.name, str) and controller.name


def test_dwell_guard_can_actually_bind():
    """MUST exceed the timestep or `t - last >= dwell` is true on the next tick.

    This relationship — not the value — is the invariant. It sat at 1.0
    against a 1.0 h tick from Step 7 until Step 8, making the dwell timer a
    no-op for five build steps with nothing to notice.
    """
    assert MIN_ACTION_DWELL_HOURS > TIME_STEP_HOURS


def test_thresholds_leave_a_dead_band():
    """Equal thresholds would oscillate every tick around the crossing."""
    assert SOC_RESTORE_THRESHOLD > SOC_SHED_THRESHOLD


def test_controller_starts_with_no_action_history(controller):
    assert controller._last_change_h == {}


# =============================================================================
# F — CONTROL POLICY.  Safety first.
# =============================================================================

def test_eclss_never_sheds(controller, loads):
    """Losing life support to save the bus is not a trade this may make."""
    for t in range(0, 40):
        controller.update(float(t), 0.01, loads, -99_000.0)
    eclss = next(load for load in loads if load.name == ECLSS_NAME)
    assert not eclss.shed, "CRITICAL exclusion broken — nothing else matters"


def test_deficit_outliving_every_sheddable_load_reports_rather_than_acts(
        controller, loads):
    """When only CRITICAL remains, return None and let the record show it."""
    for t in range(0, 40):
        controller.update(float(t), 0.01, loads, -99_000.0)
    assert controller.update(100.0, 0.01, loads, -99_000.0) is NONE_ACTED
    assert sum(1 for load in loads if load.shed) == 3


def test_dead_band_is_idle(controller, loads):
    """Between the thresholds with margin to spare, do nothing at all."""
    midpoint = (SOC_SHED_THRESHOLD + SOC_RESTORE_THRESHOLD) / 2
    assert controller.update(0.0, midpoint, loads, PLENTY) is NONE_ACTED


def test_shed_order_is_least_important_first(controller, loads):
    """LoadPriority inverts: shedding takes max() of the priority value."""
    order = [name_of(controller.update(float(t * MIN_ACTION_DWELL_HOURS),
                                       0.20, loads, PLENTY))
             for t in range(4)]
    assert order == [SCIENCE_NAME, COMMS_NAME, THERMAL_NAME, None]


def test_restore_order_is_most_important_first(controller, loads):
    """And restoring takes min(). That inversion is easy to get backwards."""
    for t in range(3):
        controller.update(float(t * MIN_ACTION_DWELL_HOURS), 0.20, loads, PLENTY)
    base = 100.0
    order = [name_of(controller.update(base + t * MIN_ACTION_DWELL_HOURS,
                                       0.90, loads, PLENTY))
             for t in range(4)]
    assert order == [THERMAL_NAME, COMMS_NAME, SCIENCE_NAME, None]


def test_power_branch_outranks_the_dead_band(controller, loads):
    """Negative headroom acts even at a reserve of 0.99."""
    assert name_of(controller.update(0.0, 0.99, loads, -1.0)) == SCIENCE_NAME


def test_power_branch_outranks_the_energy_branch(controller, loads):
    """Both conditions true: the acute failure is handled first."""
    assert name_of(controller.update(0.0, 0.29, loads, -900.0)) == SCIENCE_NAME


def test_power_branch_bypasses_dwell(controller, loads):
    """An unserved-power event is not chatter; waiting an hour to be tidy is
    worse than shedding deliberately in priority order."""
    same_tick = 10.0
    order = [name_of(controller.update(same_tick, 0.90, loads, -7500.0))
             for _ in range(3)]
    assert order == [SCIENCE_NAME, COMMS_NAME, THERMAL_NAME]


def test_energy_branch_respects_dwell(controller, loads):
    """The other two branches must NOT bypass it.

    Dwell is PER-LOAD, not a global freeze. A first draft asserted that no
    action at all followed within the dwell window, and failed correctly: the
    controller had gone on to shed Comms, which had never been touched. The
    real claim is that the SAME load cannot change state again, so this
    watches Science across a shed and an attempted restore.
    """
    assert name_of(controller.update(0.0, 0.20, loads, PLENTY)) == SCIENCE_NAME
    assert controller.update(TIME_STEP_HOURS, 0.90, loads, PLENTY) is NONE_ACTED
    assert name_of(controller.update(MIN_ACTION_DWELL_HOURS, 0.90,
                                     loads, PLENTY)) == SCIENCE_NAME


def test_one_action_per_call(controller, loads):
    """A staircase, not a cliff — shed only as much as is actually needed."""
    controller.update(0.0, 0.10, loads, PLENTY)
    assert sum(1 for load in loads if load.shed) == 1


# =============================================================================
# F — D-01 REGRESSION.  The defect Step 8 found by running the thing.
# =============================================================================

def test_d01_no_restore_just_because_the_shed_worked(controller, loads):
    """The exact sequence that chattered.

    Shed on negative headroom; the shed removes the shortfall, so the next
    tick sees headroom back at zero with a healthy reserve. The earlier
    contract tested `shortfall_w <= 0` and restored here, recreating the
    deficit — twelve actions in twenty-four hours. Zero headroom means
    nothing fits, so nothing may come back.
    """
    controller.update(10.0, 0.90, loads, -1500.0)
    # t = 34 h is 10 h into a science window, so the payload genuinely wants
    # 6 kW. A first draft used t = 20 h, where the payload is idle at 0 W and
    # therefore fits in zero headroom — the documented duty-cycle limit,
    # walked straight into by the test written to guard against it.
    assert controller.update(34.0, 0.90, loads, 0.0) is NONE_ACTED


def test_restore_requires_the_load_to_actually_fit(controller, loads):
    """Sampled where the payload is ACTIVE.

    A duty-cycled load drawing 0 W fits trivially in any margin, so a test
    sampled during its idle window proves nothing. t=10 and t=34 are both
    inside the science window.
    """
    science = next(load for load in loads if load.name == SCIENCE_NAME)
    controller.update(10.0, 0.90, loads, -1500.0)
    wanted_w = science.demand(34.0)
    assert wanted_w > 0.0, "pick a t where the load is active"

    assert controller.update(34.0, 0.90, loads, wanted_w - 1.0) is NONE_ACTED
    assert name_of(controller.update(34.0, 0.90, loads, wanted_w)) == SCIENCE_NAME


def test_persistent_shortfall_never_oscillates(controller, loads):
    """Six consecutive ticks: sheds down to CRITICAL and then stops."""
    actions = [name_of(controller.update(float(t), 0.90, loads, -500.0))
               for t in range(6)]
    assert actions[:3] == [SCIENCE_NAME, COMMS_NAME, THERMAL_NAME]
    assert actions[3:] == [None, None, None]
    assert sum(1 for load in loads if load.shed) == 3


def test_headroom_is_the_only_power_input(controller, loads):
    """Signed, and read directly — the controller never derives it."""
    assert controller.update(0.0, 0.90, loads, -0.001) is not NONE_ACTED
    fresh_loads = loads
    for load in fresh_loads:
        load.shed = False
    assert AutonomousController().update(0.0, 0.90, fresh_loads, 0.0) is NONE_ACTED
