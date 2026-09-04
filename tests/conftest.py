"""
@file    tests/conftest.py
@brief   Shared pytest fixtures. Not a test file — pytest imports it for you.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-04

@details
conftest.py is a pytest convention: every fixture defined here is available
by NAME in any test file in this directory, with no import. Write a test
function that takes an argument called `nominal_history` and pytest hands it
the fixture below.

    def test_something(nominal_history):
        assert nominal_history[0]["t_hours"] == 0.0

@note The full runs are SESSION-scoped: built once and shared by every test
    that asks for them. A 1440-tick run takes well under a second, but
    rebuilding it per test makes the suite slow enough that it stops being
    run, and a suite that is not run is worse than no suite.
@warning Because they are shared, treat a history fixture as READ-ONLY. It is
    a list of dicts and Python will happily let you mutate it; doing so
    corrupts every later test in the session. The fresh_* fixtures exist for
    anything that needs to mutate.
"""

import pytest

from controller import AutonomousController
from environment import LunarEnvironment
from main import build_outpost
from simulation_engine import SimulationEngine
from assets.loads import ECLSS, ThermalControl, CommsArray, SciencePayload
from assets.storage import BatteryBank, RegenerativeFuelCell


# --- fresh objects: use these whenever a test mutates state ------------------

@pytest.fixture
def env():
    """A LunarEnvironment starting at lunar dawn."""
    return LunarEnvironment()


@pytest.fixture
def loads(env):
    """The four standard loads, none shed, in priority order."""
    return [ECLSS(), ThermalControl(env), CommsArray(), SciencePayload()]


@pytest.fixture
def controller():
    """An AutonomousController with config thresholds and no action history."""
    return AutonomousController()


@pytest.fixture
def battery():
    """A full BatteryBank."""
    return BatteryBank()


@pytest.fixture
def rfc():
    """A full RegenerativeFuelCell."""
    return RegenerativeFuelCell()


@pytest.fixture
def outpost(env):
    """A freshly wired PowerBus, nothing stepped yet."""
    return build_outpost(env)


# --- shared runs: read-only, built once per session -------------------------

@pytest.fixture(scope="session")
def nominal_history():
    """The full 60-day run with no reactor outage. READ-ONLY."""
    engine = SimulationEngine(build_outpost(LunarEnvironment()))
    return engine.run()


@pytest.fixture(scope="session")
def outage_history():
    """The full 60-day run with a 24 h reactor outage from t = 500 h. READ-ONLY."""
    engine = SimulationEngine(build_outpost(LunarEnvironment(), 500.0))
    return engine.run()


@pytest.fixture(scope="session")
def fine_history():
    """A 48 h run at dt = 0.25 h, for timestep-independence checks. READ-ONLY."""
    engine = SimulationEngine(build_outpost(LunarEnvironment()),
                              duration_hours=48.0, dt_hours=0.25)
    return engine.run()


# --- names, so no test ever retypes one -------------------------------------
#
# Retyping "Comms Array" instead of "Communications Array" cost a whole test
# run during Step 8. Import these; never write a load name as a literal.

ECLSS_NAME = ECLSS().name
THERMAL_NAME = ThermalControl(LunarEnvironment()).name
COMMS_NAME = CommsArray().name
SCIENCE_NAME = SciencePayload().name
BATTERY_NAME = BatteryBank().name
RFC_NAME = RegenerativeFuelCell().name
