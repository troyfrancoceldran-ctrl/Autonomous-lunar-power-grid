"""
End-to-end scenario regressions.

Invariant sections from tests/INVARIANTS.md covered here:
    H scenario-level regressions

These pin the headline numbers so a refactor that quietly changes the physics
is loud. When a model changes deliberately, recompute and update these — never
loosen one to make it pass. The comment beside each figure says where it came
from, so a future reader can tell a deliberate change from a regression.
"""

import pytest

from tests.names import BATTERY_NAME, ECLSS_NAME, RFC_NAME
from config import SOC_SHED_THRESHOLD, TIME_STEP_HOURS
import metrics


def kwh(history, key):
    return sum(r[key] for r in history) * TIME_STEP_HOURS / 1000.0


# =============================================================================
# H — THE NOMINAL RUN.  The outpost survives 60 days.
# =============================================================================

def test_nominal_run_serves_every_load(nominal_history):
    """Zero unserved energy. The whole design has to clear this bar."""
    assert kwh(nominal_history, "shortfall_w") == 0.0
    assert metrics.reliability(nominal_history)["lolp"] == 0.0


def test_nominal_energy_totals(nominal_history):
    """Measured 2026-09-04 after W02 (sine profile + dust derate)."""
    totals = metrics.energy_totals(nominal_history)
    assert totals["generated_kwh"] == pytest.approx(30225.6, rel=1e-4)
    assert totals["served_kwh"] == pytest.approx(20898.5, rel=1e-4)
    assert totals["curtailed_kwh"] == pytest.approx(8254.5, rel=1e-4)


def test_generation_exceeds_demand_with_margin(nominal_history):
    """The balance closes, which W02 was expected to break and did not.

    Two denominators, and they are not the same number. Against demand
    actually SERVED (20898 kWh, shed load excluded) generation is 145 %.
    Against total demand WANTED (22572 kWh, shedding ignored) it is 134 %.
    The 134 % figure quoted elsewhere is the second; a first draft of this
    test compared it against the first and failed for that reason alone.
    """
    totals = metrics.energy_totals(nominal_history)
    served = totals["served_kwh"] + totals["unserved_kwh"]
    assert totals["generated_kwh"] / served == pytest.approx(1.45, abs=0.02)
    assert served < totals["generated_kwh"]


def test_a_quarter_of_generation_is_curtailed(nominal_history):
    """27 % thrown away: the RFC cannot absorb the daylight surplus fast enough.

    A real sizing finding, not a bug. Pinned so that a change to storage
    ratings shows up here rather than being discovered by accident.
    """
    assert metrics.energy_totals(nominal_history)["curtailment_fraction"] == (
        pytest.approx(0.273, abs=0.01))


def test_fleet_reserve_bottoms_out_just_below_the_shed_threshold(nominal_history):
    """0.2955 — which is why the controller acts at all on a nominal run."""
    floor = min(r["aggregate_soc"] for r in nominal_history)
    assert floor == pytest.approx(0.2955, abs=1e-3)
    assert floor < SOC_SHED_THRESHOLD


def test_battery_spends_most_of_the_night_at_its_floor(nominal_history):
    """554 of 708 night hours. This IS the power-limited mechanism."""
    usage = metrics.storage_utilisation(nominal_history)
    assert usage[BATTERY_NAME]["hours_at_floor"] == pytest.approx(554, abs=5)


def test_rfc_still_has_reactant_at_every_dawn(nominal_history):
    """Hydrogen can only be remade in sunlight; the dawn margin is the number
    that decides whether the outpost survives the next night."""
    margins = metrics.reactant_margin(nominal_history)
    assert len(margins["dawns"]) >= 2
    assert margins["devices"][RFC_NAME]["min_at_dawn"] > 0.30


# =============================================================================
# H — THE CONTINGENCY.  A reactor outage in deep lunar night.
# =============================================================================

def test_outage_costs_one_event_and_a_bounded_amount(outage_history):
    reliability = metrics.reliability(outage_history)
    assert reliability["shortfall_events"] == 1
    assert reliability["unserved_kwh"] == pytest.approx(1.5, abs=0.01)
    assert reliability["longest_shortfall_hours"] == pytest.approx(1.0)


def test_every_shortfall_hour_is_power_limited(outage_history):
    """THE central claim of this project.

    An energy-only controller saw a comfortable 0.6159 and would have done
    nothing while the bus failed to serve 7.5 kW. If this test breaks, the
    claim needs re-earning before the result is quoted anywhere.
    """
    modes = metrics.failure_modes(outage_history)
    assert modes["power_limited_fraction"] == 1.0
    assert modes["energy_limited_hours"] == 0.0
    assert modes["worst_power_limited_soc"] == pytest.approx(0.6159, abs=1e-3)


def test_the_controller_does_not_chatter_during_the_outage(outage_history):
    """D-01 regression at run level.

    The stale-shortfall contract produced twelve actions in the 24 h outage
    window, shedding and restoring the same load alternately. Signed headroom
    brought it to four. A number climbing back toward twelve means the
    restore guard has regressed.
    """
    window = [r for r in outage_history if 500.0 <= r["t_hours"] < 524.0]
    actions = [r["action"] for r in window if r["action"]]
    assert len(actions) <= 5, f"controller chattered: {actions}"


def test_no_load_is_shed_and_restored_within_the_dwell_time(outage_history):
    """Contactors have finite switching lifetimes."""
    last_change = {}
    for record in outage_history:
        name = record["action"]
        if name is None:
            continue
        previous = last_change.get(name)
        if previous is not None:
            gap = record["t_hours"] - previous
            assert gap >= 1.0, f"{name} switched twice within {gap} h"
        last_change[name] = record["t_hours"]


# =============================================================================
# H — INVARIANTS THAT MUST HOLD IN EVERY SCENARIO.
# =============================================================================

@pytest.mark.parametrize("run", ["nominal_history", "outage_history"])
def test_life_support_availability_is_total(request, run):
    """If this ever drops below 1.0, stop and fix it before reading anything else."""
    history = request.getfixturevalue(run)
    assert metrics.load_availability(history)[ECLSS_NAME] == 1.0


@pytest.mark.parametrize("run", ["nominal_history", "outage_history"])
def test_storage_never_leaves_its_band(request, run):
    history = request.getfixturevalue(run)
    for name, stats in metrics.storage_utilisation(history).items():
        assert stats["min_soc"] >= 0.0499, f"{name} went below its floor"
        assert stats["max_soc"] <= 1.0, f"{name} went above its ceiling"


@pytest.mark.parametrize("run", ["nominal_history", "outage_history"])
def test_run_level_round_trip_sits_between_the_two_devices(request, run):
    """Between the battery's 0.9025 and the RFC's 0.385, per the merit split."""
    history = request.getfixturevalue(run)
    ratio = metrics.energy_totals(history)["round_trip_efficiency"]
    assert 0.385 < ratio < 0.9025


def test_the_outage_is_strictly_worse_than_nominal(nominal_history,
                                                   outage_history):
    """A contingency that improved things would mean the model is wrong."""
    assert (metrics.reliability(outage_history)["unserved_kwh"]
            > metrics.reliability(nominal_history)["unserved_kwh"])
    assert (metrics.energy_totals(outage_history)["generated_kwh"]
            < metrics.energy_totals(nominal_history)["generated_kwh"])
