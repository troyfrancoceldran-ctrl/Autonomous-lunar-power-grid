"""
Tests for assets/storage.py.

Invariant sections from tests/INVARIANTS.md covered here:
    A structural · C gate-before-guard · D conservation · E boundaries
"""

import pytest

from config import (BATTERY_CAPACITY_WH, BATTERY_CHARGE_EFFICIENCY,
                    BATTERY_DISCHARGE_EFFICIENCY, BATTERY_MAX_CHARGE_POWER_W,
                    BATTERY_MAX_DISCHARGE_POWER_W, BATTERY_SOC_MAX,
                    BATTERY_SOC_MIN, ELECTROLYZER_EFFICIENCY,
                    FUEL_CELL_EFFICIENCY, H2_SPECIFIC_ENERGY_WH_PER_KG,
                    O2_TO_H2_MASS_RATIO, RFC_H2_CAPACITY_KG,
                    RFC_MAX_DISCHARGE_POWER_W, RFC_SOC_MIN)
from assets.base_asset import PowerStorage
from assets.storage import BatteryBank, RegenerativeFuelCell

BATTERY_DELIVERABLE_WH = ((BATTERY_SOC_MAX - BATTERY_SOC_MIN)
                          * BATTERY_CAPACITY_WH * BATTERY_DISCHARGE_EFFICIENCY)
RFC_DELIVERABLE_WH = ((1.0 - RFC_SOC_MIN) * RFC_H2_CAPACITY_KG
                      * H2_SPECIFIC_ENERGY_WH_PER_KG * FUEL_CELL_EFFICIENCY)


# =============================================================================
# A — STRUCTURAL.  The @property family, which the ABC cannot catch.
#
# An abstract PROPERTY is satisfied by a plain METHOD — Python only checks
# that the name exists. The RFC shipped both new members without @property
# and constructed happily; the failure surfaced two files away, dividing a
# bound method by a float inside the base class.
# =============================================================================

@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
@pytest.mark.parametrize("member", ["state_of_charge",
                                    "deliverable_energy_wh",
                                    "deliverable_capacity_wh"])
def test_readings_are_properties_not_methods(cls, member):
    assert isinstance(getattr(cls, member), property), (
        f"{cls.__name__}.{member} is a bound method, not a property")


@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
def test_power_ceiling_is_inherited_not_overridden(cls):
    """It is concrete on PowerStorage; a subclass copy would drift."""
    assert (cls.available_discharge_power_w
            is PowerStorage.available_discharge_power_w)


@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
def test_storage_satisfies_the_interface(cls):
    device = cls()
    assert isinstance(device, PowerStorage)
    assert isinstance(device.name, str) and device.name


@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
@pytest.mark.parametrize("member", ["state_of_charge",
                                    "deliverable_energy_wh",
                                    "deliverable_capacity_wh"])
def test_readings_are_floats(cls, member):
    """max(0, x) returns an int when it clamps; max(0.0, x) does not."""
    assert isinstance(getattr(cls(), member), float)


# =============================================================================
# C — GATE BEFORE GUARD, and the direction of the efficiency.
# =============================================================================

def test_deliverable_energy_is_zero_at_the_floor_and_that_is_why():
    """Assert the SoC too — zero alone could come from a broken formula."""
    battery = BatteryBank(initial_soc=BATTERY_SOC_MIN)
    assert battery.state_of_charge == pytest.approx(BATTERY_SOC_MIN)
    assert battery.deliverable_energy_wh == 0.0

    rfc = RegenerativeFuelCell(initial_soc=RFC_SOC_MIN)
    assert rfc.state_of_charge == pytest.approx(RFC_SOC_MIN)
    assert rfc.deliverable_energy_wh == 0.0


@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
def test_deliverable_energy_never_goes_negative(cls):
    """Float drift below the floor must not make a device subtract."""
    assert cls(initial_soc=0.0).deliverable_energy_wh >= 0.0


def test_outbound_efficiency_multiplies_here_and_divides_in_discharge():
    """Getting this backwards inflates the RFC by 1/0.55^2 = 3.3x."""
    rfc = RegenerativeFuelCell()
    spendable_kg = (1.0 - RFC_SOC_MIN) * RFC_H2_CAPACITY_KG
    chemical_wh = spendable_kg * H2_SPECIFIC_ENERGY_WH_PER_KG
    assert rfc.deliverable_energy_wh == pytest.approx(
        chemical_wh * FUEL_CELL_EFFICIENCY)
    assert rfc.deliverable_energy_wh < chemical_wh, "efficiency divided, not multiplied"


def test_deliverable_capacity_matches_the_documented_targets():
    assert BatteryBank().deliverable_capacity_wh == pytest.approx(180_500.0)
    assert RegenerativeFuelCell().deliverable_capacity_wh == pytest.approx(2_090_000.0)


def test_battery_is_a_small_share_of_fleet_reserve():
    """7.95 % — the figure that rules out a mean-of-SoCs aggregate."""
    battery = BatteryBank().deliverable_capacity_wh
    rfc = RegenerativeFuelCell().deliverable_capacity_wh
    assert battery / (battery + rfc) == pytest.approx(0.0795, abs=1e-4)


# =============================================================================
# D — CONSERVATION.  The accounting is not fiction.
# =============================================================================

@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
def test_charge_never_accepts_more_than_offered(cls):
    device = cls(initial_soc=0.5)
    for offered in (0.0, 1_000.0, 10_000.0, 1_000_000.0):
        accepted = cls(initial_soc=0.5).charge(offered, 1.0)
        assert 0.0 <= accepted <= offered
    assert device.charge(-100.0, 1.0) == 0.0


@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
def test_discharge_never_delivers_more_than_requested(cls):
    for requested in (0.0, 1_000.0, 10_000.0, 1_000_000.0):
        delivered = cls().discharge(requested, 1.0)
        assert 0.0 <= delivered <= requested


def test_battery_round_trip_is_the_documented_efficiency():
    """0.95 in x 0.95 out = 0.9025. Multiply in both places and it creates energy.

    The round trip lives in the STORED energy, not in the bus-side power of
    two independent calls. A first draft compared charge()'s return against
    discharge()'s and got exactly 1.0 — both requests were satisfiable, so
    both returned the 10 kW asked for, and the loss was invisible. Measure
    what the bus put in against what the device can give back.
    """
    battery = BatteryBank(initial_soc=BATTERY_SOC_MIN)
    drawn_wh = battery.charge(10_000.0, 1.0) * 1.0
    assert battery.deliverable_energy_wh / drawn_wh == pytest.approx(
        BATTERY_CHARGE_EFFICIENCY * BATTERY_DISCHARGE_EFFICIENCY, rel=1e-9)


def test_rfc_round_trip_is_the_documented_efficiency():
    """0.70 electrolysis x 0.55 fuel cell = 0.385."""
    rfc = RegenerativeFuelCell(initial_soc=0.5)
    before_kg = rfc.h2_mass_kg
    rfc.charge(10_000.0, 1.0)
    made_kg = rfc.h2_mass_kg - before_kg
    assert made_kg == pytest.approx(
        10_000.0 * ELECTROLYZER_EFFICIENCY / H2_SPECIFIC_ENERGY_WH_PER_KG)

    rfc2 = RegenerativeFuelCell(initial_soc=0.5)
    used_before = rfc2.h2_mass_kg
    rfc2.discharge(10_000.0, 1.0)
    used_kg = used_before - rfc2.h2_mass_kg
    assert used_kg == pytest.approx(
        10_000.0 / (FUEL_CELL_EFFICIENCY * H2_SPECIFIC_ENERGY_WH_PER_KG))
    assert (made_kg / used_kg) == pytest.approx(
        ELECTROLYZER_EFFICIENCY * FUEL_CELL_EFFICIENCY, rel=1e-9)


@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
def test_a_full_device_accepts_nothing(cls):
    assert cls(initial_soc=1.0).charge(50_000.0, 1.0) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
def test_an_empty_device_delivers_nothing(cls, ):
    empty = cls(initial_soc=BATTERY_SOC_MIN if cls is BatteryBank else RFC_SOC_MIN)
    assert empty.discharge(50_000.0, 1.0) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("cls", [BatteryBank, RegenerativeFuelCell])
def test_state_of_charge_stays_inside_its_band(cls):
    device = cls(initial_soc=0.5)
    for _ in range(200):
        device.charge(1_000_000.0, 1.0)
    assert device.state_of_charge <= 1.0
    for _ in range(400):
        device.discharge(1_000_000.0, 1.0)
    assert device.state_of_charge >= device.soc_min - 1e-12


def test_rfc_oxygen_is_derived_never_stored():
    """2 H2 + O2 -> 2 H2O fixes the ratio at 8:1; a stored copy would drift."""
    rfc = RegenerativeFuelCell()
    assert rfc.o2_mass_kg == pytest.approx(rfc.h2_mass_kg * O2_TO_H2_MASS_RATIO)
    rfc.discharge(10_000.0, 1.0)
    assert rfc.o2_mass_kg == pytest.approx(rfc.h2_mass_kg * O2_TO_H2_MASS_RATIO)


# =============================================================================
# E — BOUNDARIES.  The power ceiling and its two regimes.
# =============================================================================

def test_power_ceiling_at_nameplate():
    assert BatteryBank().available_discharge_power_w(1.0) == pytest.approx(
        BATTERY_MAX_DISCHARGE_POWER_W)
    assert RegenerativeFuelCell().available_discharge_power_w(1.0) == pytest.approx(
        RFC_MAX_DISCHARGE_POWER_W)


def test_empty_device_has_no_power_ceiling():
    assert BatteryBank(initial_soc=BATTERY_SOC_MIN).available_discharge_power_w(1.0) == 0.0


@pytest.mark.parametrize("dt", [0.0, -1.0])
def test_non_positive_timestep_is_guarded(dt):
    """A zero step would divide by zero; a negative one would report negative."""
    assert BatteryBank().available_discharge_power_w(dt) == 0.0


def test_ceiling_is_rating_limited_when_full():
    """Halving dt changes nothing while the converter rating binds."""
    rfc = RegenerativeFuelCell()
    assert rfc.available_discharge_power_w(0.5) == rfc.available_discharge_power_w(1.0)


def test_ceiling_is_energy_limited_when_nearly_empty():
    """Deep in the energy-limited regime, halving dt doubles the ceiling.

    Pick the SoC carefully: at initial_soc=0.06 the RFC still holds 22 kWh,
    which its 12 kW stack caps at both step sizes, and the test proves
    nothing. It has to be depleted enough that energy binds at BOTH dt.
    """
    rfc = RegenerativeFuelCell(initial_soc=0.0525)
    assert rfc.available_discharge_power_w(1.0) < RFC_MAX_DISCHARGE_POWER_W
    assert rfc.available_discharge_power_w(0.5) == pytest.approx(
        2 * rfc.available_discharge_power_w(1.0))


def test_charge_respects_the_power_rating():
    battery = BatteryBank(initial_soc=0.5)
    assert battery.charge(1_000_000.0, 1.0) == pytest.approx(
        BATTERY_MAX_CHARGE_POWER_W)


def test_deliverable_never_exceeds_capacity():
    for device in (BatteryBank(), RegenerativeFuelCell()):
        assert device.deliverable_energy_wh <= device.deliverable_capacity_wh
