"""
@file    tests/test_converters.py
@brief   T03 — power electronics, and the direction the loss falls.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-07

@details
The single thing worth testing hard here is the ASYMMETRY. A converter
multiplies on the way out and divides on the way in, and an implementation
that does the same thing in both directions is a machine that creates energy.
The conservation identity would catch it, but only after a full run; these
catch it in a line.
"""

import pytest

from config import CONVERTER_EFFICIENCY
from converters import Converter, build_converters
from environment import LunarEnvironment
from main import build_outpost
from simulation_engine import SimulationEngine


@pytest.fixture
def converter():
    return Converter("test", efficiency=0.8)


def _run(topology=False, converters=False):
    engine = SimulationEngine(
        build_outpost(LunarEnvironment(), None, topology, converters))
    engine.run()
    return engine


# --- the asymmetry -----------------------------------------------------------

def test_supplying_multiplies(converter):
    """1000 W leaves the asset; 800 W reaches the bus."""
    assert converter.delivered_w(1000.0) == pytest.approx(800.0)


def test_drawing_divides(converter):
    """The asset needs 800 W; the bus must send 1000 W."""
    assert converter.drawn_w(800.0) == pytest.approx(1000.0)


def test_the_two_directions_are_inverses(converter):
    assert converter.drawn_w(converter.delivered_w(1234.0)) == pytest.approx(1234.0)


def test_a_converter_never_creates_power(converter):
    """The failure an implementation that multiplies both ways would produce."""
    for power in (1.0, 100.0, 10_000.0):
        assert converter.delivered_w(power) < power
        assert converter.drawn_w(power) > power


def test_losses_are_positive_in_both_directions(converter):
    assert converter.loss_supplying_w(1000.0) == pytest.approx(200.0)
    assert converter.loss_drawing_w(800.0) == pytest.approx(200.0)


def test_a_perfect_converter_is_transparent():
    ideal = Converter("ideal", efficiency=1.0)
    assert ideal.delivered_w(500.0) == 500.0
    assert ideal.drawn_w(500.0) == 500.0
    assert ideal.loss_supplying_w(500.0) == 0.0


@pytest.mark.parametrize("bad", [0.0, -0.5, 1.5])
def test_impossible_efficiency_is_rejected(bad):
    """Caught at construction, not discovered as a strange result later."""
    with pytest.raises(ValueError):
        Converter("bad", efficiency=bad)


def test_converter_is_immutable():
    with pytest.raises(Exception):
        Converter("x").efficiency = 0.1


# --- binding -----------------------------------------------------------------

def test_every_asset_gets_a_converter():
    """Derived from the assembled bus, never from a restated list.

    Defect D-03 was a feeder bound to a name build_outpost had never used, and
    it failed silently. build_converters reads the bus itself so the same
    mistake cannot be made twice.
    """
    bus = build_outpost(LunarEnvironment(), None, converters=True)
    assets = ({s.name for s in bus.sources} | {d.name for d in bus.storage}
              | {l.name for l in bus.loads})
    assert set(bus.converters) == assets


def test_converters_default_to_the_configured_efficiency():
    bus = build_outpost(LunarEnvironment(), None, converters=True)
    for converter in bus.converters.values():
        assert converter.efficiency == CONVERTER_EFFICIENCY


# --- in a full run -----------------------------------------------------------

@pytest.fixture(scope="module")
def runs():
    return {name: _run(t, c) for name, (t, c) in {
        "bare": (False, False), "topology": (True, False),
        "converters": (False, True), "both": (True, True)}.items()}


@pytest.mark.parametrize("mode", ["bare", "topology", "converters", "both"])
def test_conservation_holds_in_every_mode(runs, mode):
    """The identity is not weakened by adding loss terms to it.

    An earlier draft converted the bus-side shortfall to a load-side figure by
    scaling it, which is only approximate, and broke this by 60.9 W. An exact
    bus-side number beats an approximate load-side one.
    """
    worst = max(abs((r["generation_w"] + r["discharged_w"])
                    - (r["served_w"] + r["charged_w"] + r["curtailed_w"]
                       + r["losses_w"]))
                for r in runs[mode].history)
    assert worst < 1e-6, f"{mode}: worst residual {worst:.3e} W"


def test_no_converters_means_no_converter_loss(runs):
    assert all(r["converter_loss_w"] == 0.0 for r in runs["bare"].history)
    assert all(r["converter_loss_w"] == 0.0 for r in runs["topology"].history)


def test_converters_alone_cost_more_than_conductors_alone(runs):
    """The headline of T03.

    Copper is visible and gets the attention; the power electronics are not
    and cost more. Fourteen times the unserved energy in this outpost.
    """
    conv = runs["converters"].summary()["unserved_kwh"]
    feed = runs["topology"].summary()["unserved_kwh"]
    assert conv > feed


def test_adding_converters_reduces_conductor_loss(runs):
    """Counter-intuitive and real, so it is pinned rather than left to chance.

    A converter throttles what its feeder carries: the PV array's output
    reaches the bus reduced by eta, so the largest feeder in the outpost
    carries less current and burns less. Adding one loss mechanism lowers the
    measured value of another.
    """
    with_conv = sum(r["feeder_loss_w"] for r in runs["both"].history)
    without = sum(r["feeder_loss_w"] for r in runs["topology"].history)
    assert with_conv < without


def test_losses_never_exceed_generation(runs):
    for mode, engine in runs.items():
        for r in engine.history:
            assert r["losses_w"] <= r["generation_w"] + r["discharged_w"] + 1e-9


def test_the_full_model_is_the_worst_case(runs):
    """More physics can only make the outpost worse, never better."""
    served = {m: e.summary()["served_kwh"] for m, e in runs.items()}
    assert served["both"] < served["topology"]
    assert served["both"] < served["converters"]
    assert served["bare"] == max(served.values())
