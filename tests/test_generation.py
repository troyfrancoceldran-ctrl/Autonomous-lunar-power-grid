"""
Tests for assets/generation.py.

Invariant sections from tests/INVARIANTS.md covered here:
    A structural · B variation · C gate-before-guard · E boundaries
"""

import pytest

from config import (FSP_RATED_POWER_W, LUNAR_CYCLE_HOURS, LUNAR_DAY_HOURS,
                    PV_AREA_M2, PV_DUST_DERATE, PV_EFFICIENCY,
                    PV_PACKING_FACTOR, SOLAR_CONSTANT_W_PER_M2)
from assets.base_asset import PowerSource
from assets.generation import FissionSurfacePower, PVArray

UNDUSTED_PEAK_W = (SOLAR_CONSTANT_W_PER_M2 * PV_AREA_M2
                   * PV_EFFICIENCY * PV_PACKING_FACTOR)
DUSTED_PEAK_W = UNDUSTED_PEAK_W * PV_DUST_DERATE


# =============================================================================
# B — VARIATION.  A generator that never generates is a test failure.
#
# The first W02 implementation multiplied by the sun_tracking BOOLEAN instead
# of branching on it. PV_SUN_TRACKING is False, so the array produced 0 W at
# every hour of the run — including local noon. No value test existed that
# could see it. These would have.
# =============================================================================

@pytest.mark.parametrize("tracking", [False, True])
def test_pv_array_actually_generates(env, tracking):
    """Peak output over a whole cycle must be non-zero, in either regime.

    This asserts ONLY that the array generates. The exact peak is a separate
    test, because a fixed array sampled on integer hours never lands on local
    noon at 177.175 h — it reaches 34909.61 W rather than 34909.65 W. Folding
    both claims into one test made it fail on a sampling artefact while the
    thing it existed to catch was fine.
    """
    pv = PVArray(sun_tracking=tracking)
    peak = max(pv.available_power(t, env) for t in range(int(LUNAR_CYCLE_HOURS)))
    assert peak > 0.0, "the array produced zero power at every hour of a cycle"
    assert peak == pytest.approx(DUSTED_PEAK_W, rel=1e-5)


@pytest.mark.parametrize("tracking", [False, True])
def test_pv_peak_at_exact_local_noon(env, tracking):
    """Sampled AT noon, both regimes hit the dusted peak exactly."""
    pv = PVArray(sun_tracking=tracking)
    assert pv.available_power(LUNAR_DAY_HOURS / 2, env) == pytest.approx(
        DUSTED_PEAK_W, rel=1e-9)


def test_pv_output_varies_across_the_day(env):
    """A fixed array follows the sine; it must not be flat while the sun is up."""
    pv = PVArray(sun_tracking=False)
    daylight = [pv.available_power(t, env) for t in range(int(LUNAR_DAY_HOURS))]
    assert len(set(round(v, 3) for v in daylight)) > 100, "output looks like a square wave"


def test_tracking_array_is_flat_across_the_day(env):
    """A tracked array holds near peak all day — that IS the square wave."""
    pv = PVArray(sun_tracking=True)
    lit = [pv.available_power(t, env) for t in range(int(LUNAR_DAY_HOURS))]
    assert all(v == pytest.approx(DUSTED_PEAK_W) for v in lit)


def test_fsp_varies_only_when_an_outage_is_configured(env):
    """Without an outage the reactor is constant; with one it is not."""
    steady = FissionSurfacePower()
    assert len({steady.available_power(t, env) for t in range(0, 1440)}) == 1

    interrupted = FissionSurfacePower(outage_start_hours=500.0,
                                      outage_duration_hours=24.0)
    assert len({interrupted.available_power(t, env) for t in range(0, 1440)}) == 2


# =============================================================================
# C — GATE BEFORE GUARD, and the dust derate reaching both paths.
# =============================================================================

@pytest.mark.parametrize("tracking", [False, True])
def test_no_pv_power_at_night_and_the_gate_is_why(env, tracking):
    pv = PVArray(sun_tracking=tracking)
    for t in (400.0, 500.0, 600.0):
        assert not env.is_daylight(t)
        assert pv.available_power(t, env) == 0.0


def test_both_profiles_agree_at_local_noon(env):
    """Disagreement here means the dust derate reached only one path."""
    noon = LUNAR_DAY_HOURS / 2
    fixed = PVArray(sun_tracking=False).available_power(noon, env)
    tracked = PVArray(sun_tracking=True).available_power(noon, env)
    assert fixed == pytest.approx(tracked)
    assert fixed == pytest.approx(DUSTED_PEAK_W)


def test_dust_derate_is_actually_applied(env):
    """Peak with dust must be strictly below peak without it."""
    noon = LUNAR_DAY_HOURS / 2
    dusty = PVArray(dust_derate=PV_DUST_DERATE).available_power(noon, env)
    clean = PVArray(dust_derate=1.0).available_power(noon, env)
    assert dusty < clean
    assert dusty == pytest.approx(clean * PV_DUST_DERATE)


def test_dust_and_packing_are_separate_factors(env):
    """They must not have been collapsed into one number."""
    pv = PVArray()
    assert pv.dust_derate != pv.packing_factor or PV_DUST_DERATE == PV_PACKING_FACTOR
    assert hasattr(pv, "dust_derate") and hasattr(pv, "packing_factor")


# =============================================================================
# E — BOUNDARIES.  The outage window, and the guard that defines it.
# =============================================================================

@pytest.mark.parametrize("t_hours, online", [
    (499.0, True),      # before the window
    (500.0, False),     # inclusive start
    (512.0, False),     # mid-outage
    (523.9, False),     # last instant offline
    (524.0, True),      # exclusive end
    (600.0, True),      # well after
])
def test_outage_window_is_half_open(env, t_hours, online):
    fsp = FissionSurfacePower(outage_start_hours=500.0, outage_duration_hours=24.0)
    expected = FSP_RATED_POWER_W if online else 0.0
    assert fsp.available_power(t_hours, env) == pytest.approx(expected)


def test_outage_starting_at_zero_is_not_read_as_disabled(env):
    """The `is not None` guard. A truthiness test would return 10 kW here.

    A cold start with the reactor still offline is a legitimate scenario, and
    `if self.outage_start_hours:` treats 0.0 as False. Legal Python, wrong
    answer, no error — this is the only test that distinguishes them.
    """
    fsp = FissionSurfacePower(outage_start_hours=0.0, outage_duration_hours=24.0)
    assert fsp.available_power(0.0, env) == 0.0
    assert fsp.available_power(24.0, env) == pytest.approx(FSP_RATED_POWER_W)


def test_outage_fires_once_not_once_per_cycle(env):
    """A reproducible contingency, not a duty cycle."""
    fsp = FissionSurfacePower(outage_start_hours=500.0, outage_duration_hours=24.0)
    offline = [t for t in range(0, 1440) if fsp.available_power(t, env) == 0.0]
    assert offline == list(range(500, 524))


# =============================================================================
# A — STRUCTURAL.
# =============================================================================

@pytest.mark.parametrize("cls", [PVArray, FissionSurfacePower])
def test_sources_satisfy_the_interface(cls):
    source = cls()
    assert isinstance(source, PowerSource)
    assert isinstance(source.name, str) and source.name


def test_sources_are_pure(env):
    """Querying arbitrary t in any order gives the same answers."""
    for source in (PVArray(), FissionSurfacePower(outage_start_hours=500.0)):
        forward = [source.available_power(t, env) for t in range(0, 800)]
        shuffled = {t: source.available_power(t, env)
                    for t in reversed(range(0, 800))}
        assert forward == [shuffled[t] for t in range(0, 800)]


def test_output_is_never_negative(env):
    """A negative source would SUBTRACT power from the bus."""
    for source in (PVArray(), PVArray(sun_tracking=True), FissionSurfacePower()):
        assert all(source.available_power(t, env) >= 0.0 for t in range(0, 1440))


def test_config_supplies_defaults_not_hardcoded_values():
    """Two arrays of different sizes must be able to coexist."""
    small = PVArray(area_m2=10.0)
    standard = PVArray()
    assert small.area_m2 == 10.0
    assert standard.area_m2 == PV_AREA_M2
