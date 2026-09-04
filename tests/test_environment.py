"""
Tests for environment.py.

Invariant sections from tests/INVARIANTS.md covered here:
    A structural · B variation · C gate-before-guard · E boundaries

Fixtures available with no import (see conftest.py):
    env  loads  controller  battery  rfc  outpost
    nominal_history  outage_history  fine_history        <- READ-ONLY

Two rules, both learned the hard way in this project:
    - never retype a name; import it from conftest (COMMS_NAME, etc.)
    - never hardcode a config value; import the constant and assert the
    RELATIONSHIP, so the test survives a deliberate change to the number

SEEDED BY JARVIS as a worked example. These pass as written. Extend them —
the gaps are listed at the bottom of the file.
"""

import pytest

from config import (LUNAR_CYCLE_HOURS, LUNAR_DAY_HOURS, LUNAR_NIGHT_HOURS,
                    TIME_STEP_HOURS)
from environment import LunarEnvironment


# =============================================================================
# B — VARIATION.  Does it respond to its input at all?
#
# This section exists because two W01 implementations passed all nine
# reference values while is_daylight() returned a constant. Value tests could
# not see it; these can.
# =============================================================================

def test_is_daylight_actually_varies_with_time(env):
    """The lunar night must exist. A constant here voids the whole project."""
    seen = {env.is_daylight(t) for t in range(0, int(LUNAR_CYCLE_HOURS))}
    assert seen == {True, False}, "is_daylight returned the same answer all cycle"


def test_night_is_half_the_synodic_cycle(env):
    """Exactly half the cycle is dark.

    Sampled on a fine grid that divides the cycle evenly, NOT on integer
    hours. The first draft of this test counted integer hours in
    range(int(LUNAR_CYCLE_HOURS)) — 708 samples of a 708.7 h cycle — and got
    353 against an expected 354.35. That failure was the test's, not the
    code's: truncating the range threw away 0.7 h and integer sampling threw
    away more. Widening the tolerance would have buried a measurement error
    instead of fixing it.
    """
    n = 10_000
    step = LUNAR_CYCLE_HOURS / n
    dark = sum(1 for i in range(n) if not env.is_daylight(i * step))
    assert dark / n == pytest.approx(LUNAR_NIGHT_HOURS / LUNAR_CYCLE_HOURS,
                                    abs=1e-3)


def test_elevation_reaches_both_extremes(env):
    """The sun must actually rise and actually set."""
    values = [env.solar_elevation_fraction(t)
            for t in range(0, int(LUNAR_CYCLE_HOURS))]
    assert max(values) > 0.99, "the sun never got high"
    assert min(values) == 0.0, "the sun never set"


# =============================================================================
# C — GATE BEFORE GUARD.  Assert the reason, not just the value.
#
# solar_elevation_fraction clamps with max(0.0, ...). At deep night the raw
# sine is about -0.96, so the clamp alone produces a plausible 0.0 even when
# the day/night gate is broken. Asserting only the output cannot tell a
# working gate from a lucky clamp — so assert the gate too.
# =============================================================================

@pytest.mark.parametrize("t_hours", [354.35, 500.0, 600.0, 708.0])
def test_no_sun_at_night_and_the_gate_is_why(env, t_hours):
    """Both halves matter: the gate fired AND the output is zero."""
    assert not env.is_daylight(t_hours), "night was misclassified as day"
    assert env.solar_elevation_fraction(t_hours) == 0.0
    assert env.solar_irradiance_fraction(t_hours) == 0.0


def test_the_two_solar_methods_never_disagree(env):
    """Irradiance is non-zero exactly when elevation is, and vice versa."""
    for t in range(0, int(LUNAR_CYCLE_HOURS)):
        lit = env.solar_irradiance_fraction(t) > 0.0
        assert lit == env.is_daylight(t), f"disagreement at t={t} h"
        if not lit:
            assert env.solar_elevation_fraction(t) == 0.0


# =============================================================================
# E — BOUNDARIES.  The operators that were argued over.
# =============================================================================

def test_terminator_comparison_is_strict(env):
    """Phase exactly LUNAR_DAY_HOURS is the first instant of NIGHT, not day."""
    assert env.is_daylight(LUNAR_DAY_HOURS - 1e-9)
    assert not env.is_daylight(LUNAR_DAY_HOURS)


def test_negative_time_folds_correctly(env):
    """Python's % is non-negative for a positive modulus; no special case."""
    assert env._phase_hours(-10.0) == pytest.approx(LUNAR_CYCLE_HOURS - 10.0)
    assert env.is_daylight(-10.0) is False        # 698.7 h is deep night


def test_start_phase_shifts_the_whole_cycle():
    """start_phase_hours = LUNAR_DAY_HOURS puts t=0 at nightfall."""
    nightfall = LunarEnvironment(start_phase_hours=LUNAR_DAY_HOURS)
    assert not nightfall.is_daylight(0.0)
    assert nightfall.is_daylight(LUNAR_NIGHT_HOURS + 1.0)


def test_phase_stays_inside_one_cycle(env):
    """The modulo folds any t, however large, into [0, LUNAR_CYCLE_HOURS)."""
    for t in (0.0, 500.0, 1439.0, 100_000.0):
        assert 0.0 <= env._phase_hours(t) < LUNAR_CYCLE_HOURS


# =============================================================================
# A — STRUCTURAL, plus the reference values.
# =============================================================================

@pytest.mark.parametrize("t_hours, expected", [
    (0.0,       0.000000),      # lunar dawn, sun on the horizon
    (88.5875,   0.707107),      # quarter through the day
    (177.175,   1.000000),      # local noon
    (265.7625,  0.707107),      # mid-afternoon
    (354.0,     0.003103),      # final hour before sunset
    (354.35,    0.000000),      # first instant of night
    (500.0,     0.000000),      # deep night
    (708.7,     0.000000),      # dawn of the next cycle
    (886.0,     0.999999),      # noon of the second cycle
])
def test_elevation_reference_values(env, t_hours, expected):
    """The nine W01 verification points."""
    assert env.solar_elevation_fraction(t_hours) == pytest.approx(expected, abs=1e-5)


def test_readings_are_always_in_range_and_float(env):
    """Never negative, never above 1, and never an int from a max(0, ...)."""
    for t in range(0, 1440):
        value = env.solar_elevation_fraction(t)
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0, f"out of range at t={t} h"


def test_environment_is_pure(env):
    """Querying in any order gives the same answers; nothing is cached."""
    forward = [env.solar_elevation_fraction(t) for t in range(0, 800)]
    backward = [env.solar_elevation_fraction(t) for t in reversed(range(0, 800))]
    assert forward == list(reversed(backward))


# =============================================================================
# STILL TO WRITE — your turn
# =============================================================================
#
#   - solar_irradiance_fraction is exactly 1.0 in daylight (a square wave,
#     never a partial value) — the test that would catch someone "improving"
#     it into a second sine
#   - the day/night split is symmetric: day hours + night hours == the cycle
#   - a second LunarEnvironment with the same start_phase gives identical
#     readings (no hidden module-level state shared between instances)
#   - is_daylight is stable across cycle boundaries: t and t + LUNAR_CYCLE
#     agree, for several t
#
# Try this once they pass: comment out the `max(0.0, ...)` clamp in
# solar_elevation_fraction and re-run. If nothing goes red, the suite is not
# yet testing what it thinks it is.
