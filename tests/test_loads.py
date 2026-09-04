"""
Tests for assets/loads.py.

Invariant sections from tests/INVARIANTS.md covered here:
    B variation · E boundaries
"""

import pytest

from config import (COMMS_ACTIVE_POWER_W, COMMS_PERIOD_HOURS,
                    COMMS_STANDBY_POWER_W, COMMS_WINDOW_HOURS, ECLSS_POWER_W,
                    LUNAR_DAY_HOURS, SCIENCE_ACTIVE_POWER_W,
                    SCIENCE_IDLE_POWER_W, SCIENCE_PERIOD_HOURS,
                    SCIENCE_WINDOW_HOURS, THERMAL_DAY_POWER_W,
                    THERMAL_NIGHT_POWER_W, LoadPriority)
from assets.base_asset import Load
from assets.loads import ECLSS, CommsArray, SciencePayload, ThermalControl


def all_loads(env):
    return [ECLSS(), ThermalControl(env), CommsArray(), SciencePayload()]


# =============================================================================
# B — VARIATION.  Each duty-cycled load must take BOTH its values.
# =============================================================================

@pytest.mark.parametrize("cls, low, high", [
    (CommsArray, COMMS_STANDBY_POWER_W, COMMS_ACTIVE_POWER_W),
    (SciencePayload, SCIENCE_IDLE_POWER_W, SCIENCE_ACTIVE_POWER_W),
])
def test_duty_cycled_loads_take_both_values(cls, low, high):
    load = cls()
    seen = {load.demand(t) for t in range(0, 48)}
    assert seen == {low, high}, f"{cls.__name__} never left one state"


def test_thermal_control_responds_to_day_and_night(env):
    """The one load that reads the environment rather than the clock alone."""
    thermal = ThermalControl(env)
    assert env.is_daylight(100.0)
    assert thermal.demand(100.0) == pytest.approx(THERMAL_DAY_POWER_W)
    assert not env.is_daylight(500.0)
    assert thermal.demand(500.0) == pytest.approx(THERMAL_NIGHT_POWER_W)


def test_eclss_is_genuinely_constant(env):
    """Life support does not duty-cycle; a varying value here is a bug."""
    eclss = ECLSS()
    assert {eclss.demand(t) for t in range(0, 1440)} == {ECLSS_POWER_W}


def test_demand_is_never_negative(env):
    for load in all_loads(env):
        assert all(load.demand(t) >= 0.0 for t in range(0, 1440))


# =============================================================================
# E — BOUNDARIES.  The duty-cycle comparison is STRICT.
# =============================================================================

@pytest.mark.parametrize("t_hours, active", [
    (0.0, True),                            # start of the window
    (COMMS_WINDOW_HOURS - 1, True),         # last active hour
    (COMMS_WINDOW_HOURS, False),            # boundary belongs to standby
    (COMMS_PERIOD_HOURS - 1, False),        # last standby hour
    (COMMS_PERIOD_HOURS, True),             # next period begins
    (COMMS_PERIOD_HOURS + 7, True),         # second cycle, still in window
])
def test_comms_duty_cycle_boundary_is_strict(t_hours, active):
    expected = COMMS_ACTIVE_POWER_W if active else COMMS_STANDBY_POWER_W
    assert CommsArray().demand(t_hours) == pytest.approx(expected)


@pytest.mark.parametrize("t_hours, active", [
    (0.0, True),
    (SCIENCE_WINDOW_HOURS - 1, True),
    (SCIENCE_WINDOW_HOURS, False),          # 108 h = 12 h into the day: idle
    (SCIENCE_PERIOD_HOURS, True),
])
def test_science_duty_cycle_boundary_is_strict(t_hours, active):
    expected = SCIENCE_ACTIVE_POWER_W if active else SCIENCE_IDLE_POWER_W
    assert SciencePayload().demand(t_hours) == pytest.approx(expected)


def test_duty_cycle_repeats_across_the_run(env):
    """t and t + period must agree, including across the terminator."""
    comms = CommsArray()
    for t in (0.0, 5.0, 13.0, 340.0, 500.0):
        assert comms.demand(t) == comms.demand(t + COMMS_PERIOD_HOURS)


def test_thermal_switches_exactly_at_the_terminator(env):
    thermal = ThermalControl(env)
    assert thermal.demand(LUNAR_DAY_HOURS - 1e-9) == pytest.approx(THERMAL_DAY_POWER_W)
    assert thermal.demand(LUNAR_DAY_HOURS) == pytest.approx(THERMAL_NIGHT_POWER_W)


# =============================================================================
# The shed contract, implemented once in the base class.
# =============================================================================

def test_effective_demand_is_zero_while_shed(env):
    for load in all_loads(env):
        assert load.effective_demand(10.0) == load.demand(10.0)
        load.shed = True
        assert load.effective_demand(10.0) == 0.0
        assert load.demand(10.0) >= 0.0, "demand() must ignore shed state"


def test_effective_demand_is_not_overridden(env):
    """Implemented once in Load; a subclass copy is a chance to get it wrong."""
    for load in all_loads(env):
        assert type(load).effective_demand is Load.effective_demand


def test_loads_start_connected(env):
    assert all(not load.shed for load in all_loads(env))


def test_priorities_are_distinct_and_eclss_is_critical(env):
    loads = all_loads(env)
    assert loads[0].priority is LoadPriority.CRITICAL
    assert len({load.priority for load in loads}) == len(loads)


def test_priority_ordering_matches_the_shed_staircase(env):
    """LOWER value = MORE important. Science must be the first to go."""
    loads = all_loads(env)
    least_important = max(loads, key=lambda load: load.priority)
    most_important = min(loads, key=lambda load: load.priority)
    assert least_important.name == SciencePayload().name
    assert most_important.name == ECLSS().name
