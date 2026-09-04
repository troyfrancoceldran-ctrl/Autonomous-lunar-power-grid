"""
Tests for power_bus.py.

Invariant sections from tests/INVARIANTS.md covered here:
    D conservation

If the conservation identity ever fails, a device has returned more than it
moved and every number this project reports is fiction. It is checked on
every tick of two full runs and a fine-timestep run.
"""

import pytest

from tests.names import ECLSS_NAME
from config import TIME_STEP_HOURS
from power_bus import PowerBus


def conservation_error(record):
    """generation + discharged - (served + charged + curtailed), in watts."""
    supplied = record["generation_w"] + record["discharged_w"]
    absorbed = (record["served_w"] + record["charged_w"]
                + record["curtailed_w"])
    return abs(supplied - absorbed)


# =============================================================================
# D — CONSERVATION, on every tick of every run.
# =============================================================================

@pytest.mark.parametrize("run", ["nominal_history", "outage_history",
                                "fine_history"])
def test_conservation_identity_holds_every_tick(request, run):
    history = request.getfixturevalue(run)
    for record in history:
        assert conservation_error(record) < 1e-9, (
            f"{run} broke conservation at t={record['t_hours']} h")


@pytest.mark.parametrize("run", ["nominal_history", "outage_history"])
def test_per_load_columns_sum_to_demand(request, run):
    history = request.getfixturevalue(run)
    for record in history:
        parts = sum(v for k, v in record.items() if k.startswith("load:"))
        assert parts == pytest.approx(record["demand_w"], abs=1e-9), (
            f"load columns disagree with demand_w at t={record['t_hours']} h")


@pytest.mark.parametrize("run", ["nominal_history", "outage_history"])
def test_signed_flows_sum_to_net_storage_movement(request, run):
    """flow: is positive charging, negative discharging, on one axis."""
    history = request.getfixturevalue(run)
    for record in history:
        flows = sum(v for k, v in record.items() if k.startswith("flow:"))
        expected = record["charged_w"] - record["discharged_w"]
        assert flows == pytest.approx(expected, abs=1e-9), (
            f"flow columns disagree at t={record['t_hours']} h")


@pytest.mark.parametrize("run", ["nominal_history", "outage_history"])
def test_never_charging_and_discharging_at_once(request, run):
    history = request.getfixturevalue(run)
    for record in history:
        assert record["charged_w"] == 0.0 or record["discharged_w"] == 0.0


@pytest.mark.parametrize("run", ["nominal_history", "outage_history"])
def test_residuals_are_never_negative(request, run):
    history = request.getfixturevalue(run)
    for record in history:
        assert record["shortfall_w"] >= 0.0
        assert record["curtailed_w"] >= 0.0
        assert record["generation_w"] >= 0.0


@pytest.mark.parametrize("run", ["nominal_history", "outage_history"])
def test_aggregate_soc_stays_a_fraction(request, run):
    history = request.getfixturevalue(run)
    assert all(0.0 <= r["aggregate_soc"] <= 1.0 for r in history)


def test_shortfall_implies_headroom_was_negative(outage_history):
    """The two must agree by construction — headroom IS the signed shortfall."""
    for record in outage_history:
        if record["shortfall_w"] > 0.0:
            assert record["headroom_w"] < 0.0, (
                f"unserved power with positive headroom at t={record['t_hours']} h")


def test_eclss_is_never_shed_across_a_full_run(nominal_history, outage_history):
    for history in (nominal_history, outage_history):
        assert all(not r[f"shed:{ECLSS_NAME}"] for r in history)


# =============================================================================
# The bus's own contract.
# =============================================================================

def test_bus_holds_no_state_between_ticks(outpost):
    """Every signal is measured fresh; nothing is remembered.

    An earlier design carried an unsigned shortfall from the previous tick,
    and the controller chattered because a successful shed zeroed it. The
    absence of that attribute is the fix, made testable.
    """
    assert not hasattr(outpost, "last_shortfall_w")


def test_headroom_is_signed_and_measured(outpost):
    """Positive with reserves and daylight; the sign carries the meaning."""
    assert outpost.headroom_w(100.0, TIME_STEP_HOURS) > 0.0


def test_aggregate_soc_is_capacity_weighted_not_a_mean(outpost):
    """A mean would give the battery — 7.95 % of reserve — an equal vote."""
    battery, rfc = outpost.storage
    battery.energy_wh = battery.soc_min * battery.capacity_wh
    weighted = outpost.aggregate_soc
    plain_mean = (battery.state_of_charge + rfc.state_of_charge) / 2
    assert weighted > plain_mean, "looks like an unweighted average"
    assert weighted == pytest.approx(0.9205, abs=1e-3)


def test_storage_ceiling_is_the_sum_of_device_ceilings(outpost):
    expected = sum(d.available_discharge_power_w(TIME_STEP_HOURS)
                for d in outpost.storage)
    assert outpost.storage_power_ceiling_w(TIME_STEP_HOURS) == pytest.approx(expected)


def test_a_bus_with_no_storage_reports_zero_rather_than_dividing(env, loads,
                                                                controller):
    """sum of an empty capacity is 0; the guard must not divide by it."""
    bus = PowerBus([], [], loads, controller, env)
    assert bus.aggregate_soc == 0.0
    assert bus.storage_power_ceiling_w(TIME_STEP_HOURS) == 0.0


def test_record_carries_a_column_for_every_asset(outpost):
    record = outpost.step(0.0, TIME_STEP_HOURS)
    for source in outpost.sources:
        assert f"gen:{source.name}" in record
    for device in outpost.storage:
        assert f"soc:{device.name}" in record
        assert f"flow:{device.name}" in record
    for load in outpost.loads:
        assert f"load:{load.name}" in record
        assert f"shed:{load.name}" in record


def test_step_is_not_idempotent(outpost):
    """Documented and deliberate: two calls at the same t double-charge."""
    first = outpost.step(400.0, TIME_STEP_HOURS)
    second = outpost.step(400.0, TIME_STEP_HOURS)
    assert first["aggregate_soc"] != second["aggregate_soc"]
