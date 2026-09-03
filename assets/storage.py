"""
@file    storage.py
@brief   Concrete PowerStorage implementations: BatteryBank, RegenerativeFuelCell.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-03

@details
The outpost's two storage assets, deliberately opposite in character:

    BatteryBank            200 kWh, 50 kW either way, round-trip 0.9025.
                        Efficient and fast, but empties in ~36 h against
                        a 5 kW deficit — barely a tenth of a lunar night.

    RegenerativeFuelCell   120 kg H2 = 4000 kWh chemical, 2200 kWh
                        deliverable, round-trip 0.385. Lossy and slow
                        (12 kW ceiling), but carries the remaining 300 h
                        of darkness and still finishes with fuel to spare.

That trade — efficiency against endurance — is the result this simulation
exists to demonstrate. Sizing a battery to bridge a 336 h night alone would
need ~1700 kWh, roughly 11 tonnes of cells landed on the Moon; hydrogen
stores ~33 kWh/kg against lithium's ~0.15, so the RFC wins on mass by two
orders of magnitude and pays for it in round-trip loss.

Unlike the generation assets, both classes are STATEFUL: charge() and
discharge() mutate stored energy or mass, so call order within a timestep
matters and each may be called only once per tick.

@note Both devices share one algorithm, differing only in domain:
    clamp the request to the device's power rating, convert power to the
    stored quantity, cap it at the remaining headroom (or the energy
    available above the floor), back-solve the bus-side power from the
    capped quantity, commit, and return what ACTUALLY flowed.

@warning The efficiency asymmetry is the crux of both classes. Charging
    MULTIPLIES by the inbound efficiency; discharging DIVIDES by the
    outbound one. Multiply in both places and the device creates energy.

@see base_asset.py for the PowerStorage contract both classes satisfy.


================================================================================
API
================================================================================

--------------------------------------------------------------------------------
class BatteryBank(PowerStorage)
--------------------------------------------------------------------------------
Lithium battery bank. Stores energy directly in watt-hours.

@var name                   Identifier used in logs and plot legends.
@var capacity_wh            Nameplate energy [Wh].
@var initial_soc            Fill fraction at t=0 [-].
@var max_charge_power_w     C-rate ceiling on absorption [W].
@var max_discharge_power_w  C-rate ceiling on delivery [W].
@var charge_efficiency      Fraction of bus energy that reaches the cells [-].
@var discharge_efficiency   Fraction of cell energy that reaches the bus [-].
@var soc_min                Hard floor as a fraction of capacity [-].
@var soc_max                Hard ceiling as a fraction of capacity [-].
@var energy_wh              THE STATE VARIABLE — energy stored right now [Wh].

__init__(name="Battery Bank", capacity_wh, initial_soc, max_charge_power_w,
        max_discharge_power_w, charge_efficiency, discharge_efficiency,
        soc_min, soc_max)
    Construct a battery bank from its nameplate specification.

    @note Config constants supply DEFAULTS only, so tests can build a small
        pack without editing the scenario file.
    @note energy_wh is the only assignment that TRANSFORMS its input rather
        than copying it. SoC is derived from it and never stored alongside,
        so the two can never disagree.

state_of_charge -> float                                          [@property]
    Fill fraction, energy_wh / capacity_wh.

    @return Fraction in [0, 1].

charge(power_w, dt_hours) -> float
    Absorb power from the bus for one timestep.

    @param  power_w   Power offered by the bus [W].
    @param  dt_hours  Timestep duration [h].
    @return Power ACTUALLY drawn from the bus [W], in [0, power_w].

    energy_in_wh = accepted_power_w * dt_hours * charge_efficiency, capped at
    the headroom below soc_max. When the cap bites, the bus-side power is
    back-solved from the capped energy so the reported draw always matches
    the energy that actually moved.

    @note MULTIPLIES by efficiency — the cells keep 95% of what the bus sends.

discharge(power_w, dt_hours) -> float
    Deliver power to the bus for one timestep.

    @param  power_w   Power requested by the bus [W].
    @param  dt_hours  Timestep duration [h].
    @return Power ACTUALLY delivered [W], in [0, power_w].

    energy_out_wh = delivered_power_w * dt_hours / discharge_efficiency,
    capped at the energy available above soc_min, with the same back-solve.

    @note DIVIDES by efficiency — the cells must give up more than reaches
        the bus. The shortfall between requested and delivered is what
        signals a brownout upstream.

_clamp_energy() -> None                                            [internal]
    Pin energy_wh inside [soc_min, soc_max] * capacity_wh against float drift
    accumulated over 1344 timesteps. Not part of the PowerStorage contract.

--------------------------------------------------------------------------------
class RegenerativeFuelCell(PowerStorage)
--------------------------------------------------------------------------------
Electrolyzer + fuel cell pair. Stores energy as hydrogen MASS, not watt-hours.

@var name                       Identifier used in logs and plot legends.
@var h2_capacity_kg             Tank capacity [kg H2].
@var initial_soc                Fill fraction at t=0 [-].
@var max_charge_power_w         Electrolyzer rated electrical input [W].
@var max_discharge_power_w      Fuel cell rated electrical output [W].
@var electrolyzer_efficiency    Electricity -> chemical energy, 0.70 [-].
@var fuel_cell_efficiency       Chemical -> electricity, 0.55 [-].
@var specific_energy_wh_per_kg  Hydrogen lower heating value, 33333.3 Wh/kg.
@var soc_min                    Hard floor as a fraction of capacity [-].
@var soc_max                    Hard ceiling as a fraction of capacity [-].
@var h2_mass_kg                 THE STATE VARIABLE — hydrogen held now [kg].

__init__(name="Regenerative Fuel Cell", h2_capacity_kg, initial_soc,
        max_charge_power_w, max_discharge_power_w, electrolyzer_efficiency,
        fuel_cell_efficiency, specific_energy_wh_per_kg, soc_min, soc_max)
    Construct an RFC from its nameplate specification.

    @note Two DIFFERENT efficiencies here, unlike the battery's single
        figure used twice: electrolysis at 0.70 in, fuel cell at 0.55 out.

state_of_charge -> float                                          [@property]
    Fill fraction, h2_mass_kg / h2_capacity_kg.

    @return Fraction in [0, 1].

    @note The base class asks for an ENERGY-equivalent fraction. Because
        stored energy is directly proportional to stored mass, the mass
        fraction IS the energy fraction — this looks like a shortcut and
        is not. It is what lets the controller compare this device against
        the battery without knowing they work differently.

o2_mass_kg -> float                                               [@property]
    Oxygen held in the tanks [kg].

    @return h2_mass_kg * 8.

    @note Derived, never stored. From 2 H2 + O2 -> 2 H2O, 4 g of hydrogen
        pairs with 32 g of oxygen, so the ratio is fixed at 8:1. Keeping a
        separate o2_mass_kg attribute would let the two drift apart.
    @note Extra to the PowerStorage contract; exists for metrics.py to
        report tankage mass.

charge(power_w, dt_hours) -> float
    Run the electrolyzer: split water, store hydrogen.

    @param  power_w   Power offered by the bus [W].
    @param  dt_hours  Timestep duration [h].
    @return Power ACTUALLY drawn from the bus [W], in [0, power_w].

    The bus supplies energy_elec_wh; 70% of it becomes chemical energy;
    dividing by 33333.3 Wh/kg gives the hydrogen made. Capped at the tank
    headroom, with the bus-side power back-solved when the cap bites.

    @note Two conversions where the battery had one — the battery's state
        variable WAS energy, so power x hours landed on it directly.

discharge(power_w, dt_hours) -> float
    Run the fuel cell: recombine hydrogen and oxygen, deliver electricity.

    @param  power_w   Power requested by the bus [W].
    @param  dt_hours  Timestep duration [h].
    @return Power ACTUALLY delivered [W], in [0, power_w].

    To put energy_elec_wh on the bus the stack must consume more than that:
    divide by 0.55, since 45% leaves as heat. Capped at the hydrogen
    available above soc_min.

    @note Measured: 10 kWh delivered costs 0.545455 kg of H2, while 10 kWh
        of charging makes only 0.21 kg. Restoring what one hour of discharge
        consumed therefore takes 25.97 kWh — a round trip of 0.385, matching
        ELECTROLYZER_EFFICIENCY * FUEL_CELL_EFFICIENCY exactly.

_clamp_mass() -> None                                              [internal]
    Pin h2_mass_kg inside [soc_min, soc_max] * h2_capacity_kg against float
    drift. Not part of the PowerStorage contract.
"""

from assets.base_asset import PowerStorage
from config import (BATTERY_CAPACITY_WH,
                    BATTERY_INITIAL_SOC,
                    BATTERY_MAX_CHARGE_POWER_W,
                    BATTERY_MAX_DISCHARGE_POWER_W,
                    BATTERY_CHARGE_EFFICIENCY,
                    BATTERY_DISCHARGE_EFFICIENCY,
                    BATTERY_SOC_MIN,
                    BATTERY_SOC_MAX,
                    H2_SPECIFIC_ENERGY_WH_PER_KG,
                    O2_TO_H2_MASS_RATIO,
                    ELECTROLYZER_EFFICIENCY,
                    FUEL_CELL_EFFICIENCY,
                    RFC_H2_CAPACITY_KG,
                    RFC_INITIAL_SOC,
                    RFC_MAX_CHARGE_POWER_W,
                    RFC_MAX_DISCHARGE_POWER_W,
                    RFC_SOC_MIN,
                    RFC_SOC_MAX)


class BatteryBank(PowerStorage):
    """Lithium battery bank; efficient and fast, but shallow."""

    def __init__(self, name="Battery Bank"
                , capacity_wh=BATTERY_CAPACITY_WH
                , initial_soc=BATTERY_INITIAL_SOC
                , max_charge_power_w=BATTERY_MAX_CHARGE_POWER_W
                , max_discharge_power_w=BATTERY_MAX_DISCHARGE_POWER_W
                , charge_efficiency=BATTERY_CHARGE_EFFICIENCY
                , discharge_efficiency=BATTERY_DISCHARGE_EFFICIENCY
                , soc_min=BATTERY_SOC_MIN
                , soc_max=BATTERY_SOC_MAX):
        """Store the nameplate spec; derive starting energy from initial_soc."""
        self.name = name
        self.capacity_wh = capacity_wh
        self.initial_soc = initial_soc
        self.max_charge_power_w = max_charge_power_w
        self.max_discharge_power_w = max_discharge_power_w
        self.charge_efficiency = charge_efficiency
        self.discharge_efficiency = discharge_efficiency
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.energy_wh = initial_soc * capacity_wh

    @property
    def state_of_charge(self) -> float:
        """Fill fraction, derived from stored energy."""
        return self.energy_wh / self.capacity_wh

    def charge(self, power_w: float, dt_hours: float) -> float:
        """Absorb from the bus; returns power ACTUALLY drawn [W]."""
        if dt_hours <= 0 or power_w <= 0:
            return 0.0

        accepted_power_w = min(power_w, self.max_charge_power_w)
        energy_in_wh = accepted_power_w * dt_hours * self.charge_efficiency
        headroom_wh = self.soc_max * self.capacity_wh - self.energy_wh

        if energy_in_wh > headroom_wh:                  # fills mid-timestep
            energy_in_wh = headroom_wh
            accepted_power_w = energy_in_wh / (dt_hours * self.charge_efficiency)

        self.energy_wh = self.energy_wh + energy_in_wh
        self._clamp_energy()
        return float(accepted_power_w)

    def discharge(self, power_w: float, dt_hours: float) -> float:
        """Deliver to the bus; returns power ACTUALLY delivered [W]."""
        if dt_hours <= 0 or power_w <= 0:
            return 0.0

        delivered_power_w = min(power_w, self.max_discharge_power_w)
        energy_out_wh = delivered_power_w * dt_hours / self.discharge_efficiency
        available_wh = self.energy_wh - self.soc_min * self.capacity_wh

        if energy_out_wh > available_wh:                # hits the floor mid-timestep
            energy_out_wh = available_wh
            delivered_power_w = energy_out_wh * self.discharge_efficiency / dt_hours

        self.energy_wh = self.energy_wh - energy_out_wh
        self._clamp_energy()
        return float(delivered_power_w)

    def _clamp_energy(self) -> None:
        """Keep stored energy inside its limits despite float drift."""
        floor_wh = self.soc_min * self.capacity_wh
        ceiling_wh = self.soc_max * self.capacity_wh
        self.energy_wh = min(max(self.energy_wh, floor_wh), ceiling_wh)


class RegenerativeFuelCell(PowerStorage):
    """Electrolyzer + fuel cell; lossy and slow, but deep enough for the night."""

    def __init__(self, name="Regenerative Fuel Cell"
                , h2_capacity_kg=RFC_H2_CAPACITY_KG
                , initial_soc=RFC_INITIAL_SOC
                , max_charge_power_w=RFC_MAX_CHARGE_POWER_W
                , max_discharge_power_w=RFC_MAX_DISCHARGE_POWER_W
                , electrolyzer_efficiency=ELECTROLYZER_EFFICIENCY
                , fuel_cell_efficiency=FUEL_CELL_EFFICIENCY
                , specific_energy_wh_per_kg=H2_SPECIFIC_ENERGY_WH_PER_KG
                , soc_min=RFC_SOC_MIN
                , soc_max=RFC_SOC_MAX):
        """Store the nameplate spec; derive starting H2 mass from initial_soc."""
        self.name = name
        self.h2_capacity_kg = h2_capacity_kg
        self.initial_soc = initial_soc
        self.max_charge_power_w = max_charge_power_w
        self.max_discharge_power_w = max_discharge_power_w
        self.electrolyzer_efficiency = electrolyzer_efficiency
        self.fuel_cell_efficiency = fuel_cell_efficiency
        self.specific_energy_wh_per_kg = specific_energy_wh_per_kg
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.h2_mass_kg = initial_soc * h2_capacity_kg

    @property
    def state_of_charge(self) -> float:
        """Fill fraction; mass fraction equals energy fraction here."""
        return self.h2_mass_kg / self.h2_capacity_kg

    @property
    def o2_mass_kg(self) -> float:
        """Oxygen held, derived 8:1 from hydrogen by stoichiometry."""
        return self.h2_mass_kg * O2_TO_H2_MASS_RATIO

    def charge(self, power_w: float, dt_hours: float) -> float:
        """Electrolyze; returns power ACTUALLY drawn from the bus [W]."""
        if dt_hours <= 0 or power_w <= 0:
            return 0.0

        accepted_power_w = min(power_w, self.max_charge_power_w)
        energy_elec_wh = accepted_power_w * dt_hours
        h2_gain_kg = energy_elec_wh * self.electrolyzer_efficiency / self.specific_energy_wh_per_kg
        headroom_kg = self.soc_max * self.h2_capacity_kg - self.h2_mass_kg

        if h2_gain_kg > headroom_kg:                    # tanks fill mid-timestep
            h2_gain_kg = headroom_kg
            accepted_power_w = h2_gain_kg * self.specific_energy_wh_per_kg / (dt_hours * self.electrolyzer_efficiency)

        self.h2_mass_kg = self.h2_mass_kg + h2_gain_kg
        self._clamp_mass()
        return float(accepted_power_w)

    def discharge(self, power_w: float, dt_hours: float) -> float:
        """Run the fuel cell; returns power ACTUALLY delivered [W]."""
        if dt_hours <= 0 or power_w <= 0:
            return 0.0

        delivered_power_w = min(power_w, self.max_discharge_power_w)
        energy_elec_wh = delivered_power_w * dt_hours
        h2_used_kg = energy_elec_wh / (self.fuel_cell_efficiency * self.specific_energy_wh_per_kg)
        available_kg = self.h2_mass_kg - self.soc_min * self.h2_capacity_kg

        if h2_used_kg > available_kg:                   # tanks empty mid-timestep
            h2_used_kg = available_kg
            delivered_power_w = h2_used_kg * self.specific_energy_wh_per_kg * self.fuel_cell_efficiency / dt_hours

        self.h2_mass_kg = self.h2_mass_kg - h2_used_kg
        self._clamp_mass()
        return float(delivered_power_w)

    def _clamp_mass(self) -> None:
        """Keep stored mass inside its limits despite float drift."""
        floor_kg = self.soc_min * self.h2_capacity_kg
        ceiling_kg = self.soc_max * self.h2_capacity_kg
        self.h2_mass_kg = min(max(self.h2_mass_kg, floor_kg), ceiling_kg)
