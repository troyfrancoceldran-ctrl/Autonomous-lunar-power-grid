"""
@file    tests/test_topology.py
@brief   The electrical topology — plumbing now, physics as it lands.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-07

@details
T01 is split: the electrical core is the user's, the plumbing is Claude's.
This file tests both halves, but the halves are not ready at the same time,
so every test that depends on an unimplemented method SKIPS rather than
fails. The suite stays green while the physics is being written, and each
test lights up on its own as the method behind it starts working.

    pytest tests/test_topology.py -v -rs

`-rs` prints the skip reasons, so the skip list doubles as a to-do list.

@note The physics tests below were written FROM THE SPEC, before any
    implementation existed. They are therefore a statement of what the spec
    means, and if an implementation disagrees with one, either the code or
    the spec is wrong and it is worth finding out which before changing
    either.
@note Nothing here asserts a value copied from an implementation. Every
    expected number is either derived independently in the test or is a
    relationship (doubling V quarters A) that holds regardless of constants.
"""

import pytest

import topology
from topology import DCBus, Feeder, build_topology, cable_temperature_k
from config import (CABLE_TEMP_DAY_K, CABLE_TEMP_NIGHT_K,
                    CABLE_TEMP_REFERENCE_K, CONDUCTOR_DENSITY_KG_PER_M3,
                    CONDUCTOR_RESISTIVITY_OHM_M, MIN_CONDUCTOR_AREA_M2,
                    USER_BUS_MAX_SPAN_M, USER_BUS_VOLTAGE_V)


def needs(call):
    """Run `call`; skip the test if the method behind it is not written yet.

    The point of this helper is that a half-finished T01 produces a green
    suite with an honest skip list, not a red one that has to be ignored —
    an ignored red suite stops being read, and then it stops catching
    anything.
    """
    try:
        return call()
    except NotImplementedError as exc:
        pytest.skip(f"not implemented yet: {exc}")


@pytest.fixture
def feeder():
    """A 100 m run of 10 mm^2 aluminium at 120 V."""
    return Feeder(name="test", length_m=100.0, area_m2=1.0e-5,
                nominal_voltage_v=120.0)


# --- plumbing: works now -----------------------------------------------------

def test_conductor_length_is_the_round_trip(feeder):
    """A 100 m span holds 200 m of conductor. Out and back."""
    assert feeder.conductor_length_m == 200.0


def test_conductor_mass_uses_the_round_trip(feeder):
    """Mass derived independently, not copied from the implementation."""
    expected = CONDUCTOR_DENSITY_KG_PER_M3 * 1.0e-5 * 200.0
    assert feeder.conductor_mass_kg() == pytest.approx(expected)


def test_conductor_mass_scales_with_area_and_length():
    thin = Feeder("a", 100.0, 1.0e-5, 120.0)
    thick = Feeder("b", 100.0, 2.0e-5, 120.0)
    longer = Feeder("c", 200.0, 1.0e-5, 120.0)
    assert thick.conductor_mass_kg() == pytest.approx(2 * thin.conductor_mass_kg())
    assert longer.conductor_mass_kg() == pytest.approx(2 * thin.conductor_mass_kg())


def test_cable_temperature_is_a_step_function():
    assert cable_temperature_k(True) == CABLE_TEMP_DAY_K
    assert cable_temperature_k(False) == CABLE_TEMP_NIGHT_K


def test_bus_mass_is_the_sum_of_its_feeders():
    bus = DCBus("user", 120.0, [Feeder("a", 100.0, 1.0e-5, 120.0),
                                Feeder("b", 50.0, 1.0e-5, 120.0)])
    assert bus.total_conductor_mass_kg() == pytest.approx(
        sum(f.conductor_mass_kg() for f in bus.feeders))


def test_feeder_lookup_by_name():
    bus = DCBus("user", 120.0, [Feeder("a", 10.0, 1e-5, 120.0)])
    assert bus.feeder("a").length_m == 10.0
    with pytest.raises(KeyError):
        bus.feeder("nope")


# --- the built topology ------------------------------------------------------

def test_topology_has_two_voltage_levels():
    user, transmission = build_topology()
    assert user.nominal_voltage_v == USER_BUS_VOLTAGE_V
    assert transmission.nominal_voltage_v > user.nominal_voltage_v


def test_every_user_bus_run_is_inside_the_ispsis_limit():
    """The 100 m figure is a NASA operating limit, not a layout preference."""
    user, _ = build_topology()
    assert topology.over_span_limit(user) == []
    assert all(f.length_m <= USER_BUS_MAX_SPAN_M for f in user.feeders)


def test_the_reactor_is_the_only_asset_off_the_user_bus():
    """The whole architecture in one assertion.

    The reactor is remote for NUCLEAR reasons — FSP separation — and that is
    the only thing forcing a second voltage level into this design.
    """
    user, transmission = build_topology()
    assert len(transmission.feeders) == 1
    assert transmission.feeders[0].name == "FSP Reactor"
    assert transmission.feeders[0].length_m > USER_BUS_MAX_SPAN_M
    assert not any(f.name == "FSP Reactor" for f in user.feeders)


def test_over_span_limit_flags_a_bus_that_outgrew_its_voltage():
    bad = DCBus("user", USER_BUS_VOLTAGE_V,
                [Feeder("too far", USER_BUS_MAX_SPAN_M + 1.0, 1e-5,
                        USER_BUS_VOLTAGE_V)])
    assert topology.over_span_limit(bad) == ["too far"]


def test_over_span_limit_does_not_apply_above_120v():
    """The 100 m limit belongs to 120 VDC, not to cables in general."""
    hv = DCBus("transmission", 1000.0,
            [Feeder("long haul", 1000.0, 1e-5, 1000.0)])
    assert topology.over_span_limit(hv) == []


def test_layout_covers_every_asset_and_load():
    """Every feeder in the layout is a real feeder on a real bus.

    This test used to list the expected names as string literals and check
    them against build_topology's literals — my own names against my own
    names, which passed happily while the reactor feeder was called something
    build_outpost had never heard of. The names now come from the layout
    table itself, and test_every_asset_is_bound_to_a_feeder does the part
    that actually matters by comparing against the assembled outpost.
    """
    user, transmission = build_topology()
    names = {f.name for f in user.feeders} | {f.name for f in transmission.feeders}
    expected = {name for name, _, _ in topology.USER_BUS_LAYOUT} | {"FSP Reactor"}
    assert names == expected
    assert len(names) == len(user.feeders) + len(transmission.feeders), \
        "duplicate feeder name — a later one would shadow an earlier one"


# --- the electrical core: skips until each method lands ----------------------

def test_resistance_uses_the_round_trip_length(feeder):
    """TRAP ONE. Using length_m instead halves every loss in the model."""
    r = needs(lambda: feeder.resistance_ohm(CABLE_TEMP_REFERENCE_K))
    expected = CONDUCTOR_RESISTIVITY_OHM_M * 200.0 / 1.0e-5
    assert r == pytest.approx(expected, rel=1e-9)


def test_resistance_rises_with_temperature(feeder):
    cold = needs(lambda: feeder.resistance_ohm(CABLE_TEMP_NIGHT_K))
    warm = feeder.resistance_ohm(CABLE_TEMP_REFERENCE_K)
    hot = feeder.resistance_ohm(CABLE_TEMP_DAY_K)
    assert cold < warm < hot


def test_day_night_resistance_swing_is_large(feeder):
    """TRAP TWO, as a number.

    This is the finding the spec asked you to discover: the same cable is a
    very different conductor at noon than at midnight, and it is WORST when
    generation is highest. Whether that helps or hurts is the interesting
    part.
    """
    cold = needs(lambda: feeder.resistance_ohm(CABLE_TEMP_NIGHT_K))
    hot = feeder.resistance_ohm(CABLE_TEMP_DAY_K)
    assert hot / cold > 5.0


def test_current_is_power_over_voltage(feeder):
    assert needs(lambda: feeder.current_a(12_000.0, 120.0)) == pytest.approx(100.0)


@pytest.mark.parametrize("bad_voltage", [0.0, -120.0])
def test_current_guards_non_positive_voltage(feeder, bad_voltage):
    assert needs(lambda: feeder.current_a(1000.0, bad_voltage)) == 0.0


def test_loss_and_voltage_drop_agree(feeder):
    """TRAP THREE. P = I^2 R and P = I dV are the same number.

    If these ever disagree, one of the two methods is wrong — this test
    cannot tell you which, only that you have a problem.
    """
    power, volts, temp = 6_000.0, 120.0, CABLE_TEMP_REFERENCE_K
    loss = needs(lambda: feeder.loss_w(power, volts, temp))
    drop = feeder.voltage_drop_v(power, volts, temp)
    current = feeder.current_a(power, volts)
    assert loss == pytest.approx(current * drop, rel=1e-9)


def test_loss_scales_with_the_square_of_power(feeder):
    """Double the current, quadruple the loss. The reason voltage matters."""
    single = needs(lambda: feeder.loss_w(3_000.0, 120.0, CABLE_TEMP_REFERENCE_K))
    double = feeder.loss_w(6_000.0, 120.0, CABLE_TEMP_REFERENCE_K)
    assert double == pytest.approx(4 * single, rel=1e-9)


def test_sizing_area_scales_inversely_with_voltage_squared():
    """Doubling the transmission voltage quarters the conductor.

    This single relationship is why the reactor link runs at kilovolts, and
    why NASA concludes the most important factor for reducing mass is to
    increase voltage.
    """
    a_low = needs(lambda: Feeder.size_for_loss_budget(10_000.0, 500.0, 1000.0, 0.05))
    a_high = Feeder.size_for_loss_budget(10_000.0, 1000.0, 1000.0, 0.05)
    assert a_high == pytest.approx(a_low / 4.0, rel=1e-9)


def test_sizing_clamps_to_the_minimum_gauge():
    """Below 16 AWG the limit is handling and thermal cycling, not amps."""
    tiny = needs(lambda: Feeder.size_for_loss_budget(1.0, 1000.0, 1.0, 0.5))
    assert tiny == MIN_CONDUCTOR_AREA_M2


def test_a_sized_feeder_actually_meets_its_budget():
    """The round trip: size a feeder, then measure what it does.

    Sizing and loss are separate methods derived from the same physics, so
    this catches an algebra slip in either one — the strongest single check
    in this file.
    """
    power, volts, length, budget = 10_000.0, 1000.0, 1000.0, 0.05
    area = needs(lambda: Feeder.size_for_loss_budget(power, volts, length, budget))
    sized = Feeder("sized", length, area, volts)
    loss = sized.loss_w(power, volts, CABLE_TEMP_REFERENCE_K)
    assert loss == pytest.approx(budget * power, rel=1e-6)


def test_bus_total_loss_sums_its_feeders():
    bus = DCBus("user", 120.0, [Feeder("a", 100.0, 1e-5, 120.0),
                                Feeder("b", 50.0, 1e-5, 120.0)])
    loads = {"a": 3_000.0, "b": 2_000.0}
    total = needs(lambda: bus.total_loss_w(loads, CABLE_TEMP_REFERENCE_K))
    expected = sum(f.loss_w(loads[f.name], f.nominal_voltage_v,
                            CABLE_TEMP_REFERENCE_K) for f in bus.feeders)
    assert total == pytest.approx(expected)


def test_a_feeder_absent_from_the_dict_is_idle_not_an_error():
    """Most feeders carry nothing on most ticks; that is not a failure."""
    bus = DCBus("user", 120.0, [Feeder("a", 100.0, 1e-5, 120.0),
                                Feeder("idle", 50.0, 1e-5, 120.0)])
    total = needs(lambda: bus.total_loss_w({"a": 3_000.0},
                                        CABLE_TEMP_REFERENCE_K))
    only_a = bus.feeder("a").loss_w(3_000.0, 120.0, CABLE_TEMP_REFERENCE_K)
    assert total == pytest.approx(only_a)


def test_sized_topology_is_lighter_where_voltage_is_higher():
    """The architecture paying off, measured.

    The reactor run is 1 km against a 60 m worst case on the user bus — but
    it is also at 1000 V against 120 V. Per metre of run, the high-voltage
    link should be the cheaper conductor despite carrying comparable power.
    """
    user, transmission = needs(lambda: build_topology(sized=True))
    hv = transmission.feeders[0]
    pv = user.feeder("PV Array")
    assert (hv.conductor_mass_kg() / hv.length_m
            < pv.conductor_mass_kg() / pv.length_m)


# --- the guard has to reach the methods that need it -------------------------
# Added after review: the original suite tested the V <= 0 guard on current_a
# ONLY, so an implementation could satisfy it while voltage_drop_v and loss_w
# divided by zero on the same input. All three take the same arguments and
# should agree about what a dead bus means.

@pytest.mark.parametrize("bad_voltage", [0.0, -120.0])
def test_voltage_drop_guards_non_positive_voltage(feeder, bad_voltage):
    """No drop across a feeder carrying no current."""
    assert needs(lambda: feeder.voltage_drop_v(1000.0, bad_voltage,
                                            CABLE_TEMP_REFERENCE_K)) == 0.0


@pytest.mark.parametrize("bad_voltage", [0.0, -120.0])
def test_loss_guards_non_positive_voltage(feeder, bad_voltage):
    """No I^2R in a feeder carrying no current."""
    assert needs(lambda: feeder.loss_w(1000.0, bad_voltage,
                                    CABLE_TEMP_REFERENCE_K)) == 0.0


def test_the_three_methods_agree_about_a_dead_bus(feeder):
    """One guard, one place. Three methods, one answer.

    The fix is for voltage_drop_v and loss_w to obtain their current from
    current_a rather than recomputing P/V, so the guard lives in exactly one
    place — the same reasoning that put the temperature conversion inside
    resistance_ohm and left the callers to just call it.
    """
    for volts in (0.0, -120.0):
        assert feeder.current_a(1000.0, volts) == 0.0
        assert feeder.voltage_drop_v(1000.0, volts, CABLE_TEMP_REFERENCE_K) == 0.0
        assert feeder.loss_w(1000.0, volts, CABLE_TEMP_REFERENCE_K) == 0.0


# =============================================================================
# T02 — the topology wired into the tick
# =============================================================================
# These are integration tests: they run the real engine rather than poking at
# a Feeder. Both bugs T02 shipped were only visible at this level.

from environment import LunarEnvironment          # noqa: E402
from main import build_outpost                    # noqa: E402
from simulation_engine import SimulationEngine    # noqa: E402


def _run(topology, outage=None):
    engine = SimulationEngine(
        build_outpost(LunarEnvironment(), outage, topology))
    engine.run()
    return engine.history


@pytest.fixture(scope="module")
def wired_history():
    """A full 60-day run with feeders modelled. Read-only."""
    return _run(True)


@pytest.fixture(scope="module")
def bare_history():
    """The same run with no topology, i.e. the model as it stood before T02."""
    return _run(False)


def test_every_asset_is_bound_to_a_feeder():
    """The test that would have caught the reactor sitting unconnected.

    The original layout test asserted a list of string literals against the
    literals in build_topology — my own names checked against my own names,
    which proves only that I can copy. The reactor is called 'FSP Reactor' in
    build_outpost and was called 'Fission Surface Power' in build_topology, so
    it silently had no feeder and reported 0.0 W of loss for a 1 km run.

    Binding by name is convenient but unsafe in exactly this way: a mismatch
    is not an error, it is a missing entry that reads as zero.
    """
    bus = build_outpost(LunarEnvironment(), None, topology=True)
    assets = ({s.name for s in bus.sources}
              | {d.name for d in bus.storage}
              | {l.name for l in bus.loads})
    feeders = set(bus._feeders)
    assert assets - feeders == set(), "asset with no feeder (loss reads 0.0 W)"
    assert feeders - assets == set(), "feeder bound to no asset"


def test_conservation_identity_holds_with_topology(wired_history):
    """generation + discharged == served + charged + curtailed + losses.

    The project's central invariant, extended by one term. Losses do not
    excuse the books from balancing; they are simply another destination for
    watts, and if they were double-counted or dropped this would show it.
    """
    worst = max(abs((r["generation_w"] + r["discharged_w"])
                    - (r["served_w"] + r["charged_w"] + r["curtailed_w"]
                       + r["losses_w"]))
                for r in wired_history)
    assert worst < 1e-6, f"worst residual {worst:.3e} W"


def test_surplus_dispatch_never_overspends(wired_history):
    """Curtailment cannot go negative.

    The first T02 draft offered a device the whole remaining surplus while the
    bus could only deliver that minus the feeder cut, so the device accepted
    power that did not exist. The books were then forced to clamp at zero and
    the conservation residual reached 1.625e+03 W. Negative curtailment is the
    symptom that clamping was hiding.
    """
    assert min(r["curtailed_w"] for r in wired_history) > -1e-9


def test_no_topology_means_no_losses(bare_history):
    """Omitting the buses reproduces the pre-T02 model exactly.

    Not a convenience: it keeps every result published before T02 checkable
    rather than silently revised by a change of physics.
    """
    assert all(r["losses_w"] == 0.0 for r in bare_history)
    assert all(r["generation_bus_w"] == r["generation_w"] for r in bare_history)
    assert all(r["demand_bus_w"] == r["demand_w"] for r in bare_history)


def test_topology_costs_energy(wired_history, bare_history):
    """Modelling the conductor can only make the outpost worse, never better."""
    served_wired = sum(r["served_w"] for r in wired_history)
    served_bare = sum(r["served_w"] for r in bare_history)
    assert served_wired < served_bare


def test_the_cable_is_worse_in_daylight(wired_history):
    """The T01 temperature finding, surviving into a full run.

    Loss as a FRACTION of generation, so this is not merely the observation
    that more power flows in daylight.
    """
    def fraction(records):
        gen = sum(r["generation_w"] for r in records)
        return sum(r["losses_w"] for r in records) / gen

    day = fraction([r for r in wired_history if r["is_daylight"]])
    night = fraction([r for r in wired_history if not r["is_daylight"]])
    assert day > night * 2.0


def test_cable_temperature_is_recorded_and_tracks_daylight(wired_history):
    for r in wired_history:
        expected = CABLE_TEMP_DAY_K if r["is_daylight"] else CABLE_TEMP_NIGHT_K
        assert r["cable_temperature_k"] == expected


def test_every_feeder_reports_its_own_loss(wired_history):
    """A per-feeder column, so a figure can show WHERE the copper goes."""
    bus = build_outpost(LunarEnvironment(), None, topology=True)
    for name in bus._feeders:
        assert f"floss:{name}" in wired_history[0]
    total = sum(v for k, v in wired_history[0].items() if k.startswith("floss:"))
    # Per-feeder losses are reported for every feeder every tick; the tick
    # total counts only the paths that actually carried power.
    assert total >= wired_history[0]["losses_w"] - 1e-9


def test_losses_are_never_negative(wired_history):
    for r in wired_history:
        assert r["losses_w"] >= 0.0
        assert r["gen_loss_w"] >= 0.0
        assert r["load_loss_w"] >= 0.0
        assert r["storage_loss_w"] >= 0.0
