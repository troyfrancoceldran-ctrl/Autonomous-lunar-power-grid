"""
@file    tests/test_protection.py
@brief   T04 — the trip curve, and whether the right device opens.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-07

@details
Same arrangement as test_topology.py: written FROM THE SPEC before any
implementation exists, so a test that disagrees with the code is a real
argument about which is wrong rather than a tautology. Anything depending on
an unwritten method SKIPS, so the suite stays green and

    pytest tests/test_protection.py -q -rs

prints what is left as a to-do list.

@note No expected value here is copied out of an implementation. Each is
    derived independently in the test, or is a relationship that holds
    whatever the constants are — trip time falling as the square of current,
    let-through staying flat, the cold case being the worst case.
"""

import math

import pytest

from config import (CABLE_TEMP_DAY_K, CABLE_TEMP_NIGHT_K,
                    CABLE_TEMP_REFERENCE_K, PROTECTION_COORDINATION_MARGIN_S,
                    SSPC_I2T_RATING_A2S, SSPC_INSTANTANEOUS_TRIP_MULTIPLE,
                    SSPC_MIN_TRIP_TIME_S)
from topology import Feeder, build_topology
import protection
from protection import (ProtectionDevice, build_protection,
                        feeder_rated_current_a, prospective_fault_current_a,
                        is_selective)


def needs(call):
    """Run `call`; skip if the method behind it is not written yet."""
    try:
        return call()
    except NotImplementedError as exc:
        pytest.skip(f"not implemented yet: {exc}")


@pytest.fixture
def device():
    """100 A continuous, so the instantaneous threshold lands at 1000 A."""
    return ProtectionDevice(name="test", rated_current_a=100.0)


@pytest.fixture
def feeder():
    """A 100 m run of 10 mm^2 at 120 V."""
    return Feeder("test", 100.0, 1.0e-5, 120.0)


# --- plumbing: works now -----------------------------------------------------

def test_instantaneous_threshold_is_a_multiple_of_the_rating(device):
    assert device.instantaneous_threshold_a == 100.0 * SSPC_INSTANTANEOUS_TRIP_MULTIPLE


def test_rated_current_inverts_the_sizing_rule():
    """A feeder sized for a power should be rated for that power's current.

    Round trip through T01: size a conductor for 12 kW at 120 V, then ask
    what current it was rated for. 100 A, or the two rules disagree.
    """
    area = Feeder.size_for_loss_budget(12_000.0, 120.0, 50.0, 0.05)
    sized = Feeder("x", 50.0, area, 120.0)
    assert feeder_rated_current_a(sized) == pytest.approx(100.0, rel=1e-9)


def test_every_feeder_gets_a_device():
    """The D-03 lesson: binding by name is silent when it fails."""
    buses = build_topology(sized=True)
    devices = build_protection(buses)
    feeders = {f.name for bus in buses for f in bus.feeders}
    assert set(devices) == feeders


def test_device_ratings_match_their_conductors():
    """A device rated above its cable protects itself and burns the cable."""
    buses = build_topology(sized=True)
    devices = build_protection(buses)
    for bus in buses:
        for f in bus.feeders:
            assert devices[f.name].rated_current_a == pytest.approx(
                feeder_rated_current_a(f))


# --- method 1: prospective fault current -------------------------------------

def test_fault_current_is_voltage_over_resistance(feeder):
    expected = 120.0 / feeder.resistance_ohm(CABLE_TEMP_REFERENCE_K)
    got = needs(lambda: prospective_fault_current_a(feeder, CABLE_TEMP_REFERENCE_K))
    assert got == pytest.approx(expected, rel=1e-9)


def test_the_cold_case_is_the_worst_case(feeder):
    """The T02 finding, inverted.

    Losses are worst when the cable is hot. Fault current is worst when it is
    COLD, because a cold conductor is a better one. Anything sized on a
    daytime fault is undersized at midnight.
    """
    night = needs(lambda: prospective_fault_current_a(feeder, CABLE_TEMP_NIGHT_K))
    day = prospective_fault_current_a(feeder, CABLE_TEMP_DAY_K)
    assert night > day * 5.0


def test_distance_protects_better_than_voltage_endangers():
    """The reactor sits at the highest voltage and has the LOWEST fault.

    A kilometre of thin aluminium is a large series resistance, and it limits
    the fault as effectively as a device would. This is the single most
    counter-intuitive number in the module.
    """
    user, transmission = build_topology(sized=True)
    reactor = needs(lambda: prospective_fault_current_a(
        transmission.feeders[0], CABLE_TEMP_NIGHT_K))
    worst_user = max(prospective_fault_current_a(f, CABLE_TEMP_NIGHT_K)
                     for f in user.feeders)
    assert transmission.feeders[0].nominal_voltage_v > user.nominal_voltage_v
    assert reactor < worst_user


def test_the_battery_fault_dwarfs_its_rating():
    """Why a mechanical contact is not an option here."""
    user, _ = build_topology(sized=True)
    battery = user.feeder("Battery Bank")
    fault = needs(lambda: prospective_fault_current_a(battery, CABLE_TEMP_NIGHT_K))
    assert fault > 50.0 * feeder_rated_current_a(battery)


# --- method 2: the trip curve ------------------------------------------------

def test_below_the_rating_it_never_trips(device):
    assert needs(lambda: device.trip_time_s(99.0)) == math.inf
    assert device.trip_time_s(100.0) == math.inf


def test_at_the_instantaneous_threshold_it_hits_the_floor(device):
    at = needs(lambda: device.trip_time_s(device.instantaneous_threshold_a))
    assert at == pytest.approx(SSPC_MIN_TRIP_TIME_S)


def test_a_dead_short_never_trips_faster_than_the_hardware(device):
    """THE TRAP, as a test.

    With the branches in the wrong order a short circuit falls into the I^2t
    region and returns a trip time far below what silicon can physically do —
    which reads as superb protection and is fiction. Nothing may ever be
    faster than the floor.
    """
    for current in (1_000.0, 10_000.0, 36_600.0):
        assert needs(lambda c=current: device.trip_time_s(c)) >= SSPC_MIN_TRIP_TIME_S


def test_trip_time_falls_as_the_square_of_current(device):
    """Double the overload, quarter the time. 'Protects on energy' in one line."""
    slow = needs(lambda: device.trip_time_s(200.0))
    fast = device.trip_time_s(400.0)
    assert fast == pytest.approx(slow / 4.0, rel=1e-9)


def test_trip_time_is_monotonic(device):
    """More current is never tolerated for longer."""
    currents = [101.0, 150.0, 300.0, 600.0, 999.0, 1000.0, 5000.0]
    times = [needs(lambda c=c: device.trip_time_s(c)) for c in currents]
    assert times == sorted(times, reverse=True)


# --- method 3: let-through energy --------------------------------------------

def test_let_through_is_flat_across_the_i2t_region(device):
    """The definition of an I^2t device, not a coincidence.

    If this is not flat, the trip curve is not really integrating energy and
    method 2 is wrong.
    """
    values = [needs(lambda c=c: device.let_through_energy_a2s(c))
              for c in (150.0, 300.0, 600.0, 900.0)]
    for v in values:
        assert v == pytest.approx(SSPC_I2T_RATING_A2S, rel=1e-9)


def test_let_through_is_unbounded_below_the_rating(device):
    """Not a bug: a device that never trips lets through everything.

    It is the reason the rating must sit below what the cable survives
    continuously — the device is not protecting anything down here.
    """
    assert needs(lambda: device.let_through_energy_a2s(50.0)) == math.inf


def test_let_through_grows_again_in_the_instantaneous_region(device):
    """Above the threshold the time is fixed, so energy rises with I^2.

    This is the region where the CABLE is at risk even though the device is
    doing everything it can.
    """
    low = needs(lambda: device.let_through_energy_a2s(1_000.0))
    high = device.let_through_energy_a2s(2_000.0)
    assert high == pytest.approx(4.0 * low, rel=1e-9)


# --- method 4: selectivity ---------------------------------------------------

def test_a_smaller_device_clears_before_a_larger_one():
    """Zonal protection: the device nearest the fault opens, nothing else."""
    upstream = ProtectionDevice("main", rated_current_a=400.0)
    downstream = ProtectionDevice("branch", rated_current_a=50.0)
    assert needs(lambda: is_selective(upstream, downstream, 500.0))


def test_selectivity_fails_when_both_are_instantaneous():
    """A real limitation of solid-state protection, not an implementation flaw.

    Past a high enough fault current both devices are on their floor and
    return the same trip time, so no timing margin exists and selectivity by
    timing alone is impossible. Recording it because the honest answer is that
    the design has a limit, not that the code has a bug.
    """
    upstream = ProtectionDevice("main", rated_current_a=400.0)
    downstream = ProtectionDevice("branch", rated_current_a=50.0)
    huge = 100_000.0
    assert needs(lambda: upstream.trip_time_s(huge)) == downstream.trip_time_s(huge)
    assert not is_selective(upstream, downstream, huge)


def test_selectivity_needs_the_margin_not_merely_sooner():
    """Equal trip times are not selective, however tidy they look."""
    a = ProtectionDevice("a", rated_current_a=100.0)
    b = ProtectionDevice("b", rated_current_a=100.0)
    assert not needs(lambda: is_selective(a, b, 500.0))


def test_a_device_is_not_selective_against_itself(device):
    assert not needs(lambda: is_selective(device, device, 500.0))


def test_coordination_failures_reports_rather_than_raises():
    """A coordination study yields a list of problems, not an exception."""
    buses = build_topology(sized=True)
    devices = build_protection(buses)
    upstream = ProtectionDevice("bus main", rated_current_a=1_000.0)
    currents = needs(lambda: protection.fault_survey(buses))
    problems = protection.coordination_failures(upstream, devices, currents)
    assert isinstance(problems, list)
    assert all(isinstance(p, str) for p in problems)
