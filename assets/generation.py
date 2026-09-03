"""
@file    generation.py
@brief   Concrete PowerSource implementations: PVArray, FissionSurfacePower.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-03

@details
The outpost's two generation assets, with opposite characters:

    PVArray               36.7 kW peak, but ZERO for 336 consecutive hours.
    FissionSurfacePower   10 kW flat, indifferent to the sun.

That asymmetry is the whole engineering problem. Anything the outpost draws
above the reactor's output during the night must have been stored during the
day and pushed back through an RFC round-trip of only 0.385.

@see environment.py for the irradiance model PVArray depends on.
@see base_asset.py for the PowerSource contract both classes satisfy.


================================================================================
 API
================================================================================

--------------------------------------------------------------------------------
 class PVArray(PowerSource)
--------------------------------------------------------------------------------
Photovoltaic array; output tracks the environment's irradiance.

@var name            Identifier used in logs and plot legends.
@var area_m2         Total array area [m^2].
@var efficiency      Photon-to-electron conversion efficiency [-].
@var packing_factor  Cell-to-array area loss, wiring, mismatch, pointing [-].

 __init__(name="PV Array", area_m2, efficiency, packing_factor)
    Construct a PV array from its nameplate specification.

    @param name            Identifier for logs and plots.
    @param area_m2         Array area [m^2].
    @param efficiency      Conversion efficiency in [0, 1].
    @param packing_factor  Aggregate array-level derate in [0, 1].

    @note The config constants supply DEFAULTS only. Each instance stores its
        own values, so two arrays of different sizes can coexist.

 available_power(t_hours, environment) -> float
    Electrical power available from the array at time t.

    @param  t_hours      Simulation time [h] since t=0.
    @param  environment  LunarEnvironment supplying the irradiance fraction.
    @return Available power [W]: 0 at night, ~36.7 kW at full sun.

    Computes P = G_sc * A * eta * f * phi(t), where G_sc is the solar constant
    at 1 AU (1361 W/m^2 — the Moon has no atmosphere, so the full
    extraterrestrial value reaches the panels) and phi(t) is the environment's
    irradiance fraction in [0, 1].

    Dimensionally: [W/m^2] * [m^2] * [-] * [-] * [-] = [W].

    @note The array knows nothing about lunar cycles. It asks the environment
        for a fraction and scales by it — which is why swapping in a real
        irradiance sensor requires no change here.

--------------------------------------------------------------------------------
 class FissionSurfacePower(PowerSource)
--------------------------------------------------------------------------------
Kilopower-class fission reactor; constant output, indifferent to time.

@var name           Identifier used in logs and plot legends.
@var rated_power_w  Nameplate electrical output [W].
@var availability   Fraction of time online, in [0, 1].

 __init__(name="FSP Reactor", rated_power_w, availability)
    Construct a reactor from its nameplate specification.

    @param name           Identifier for logs and plots.
    @param rated_power_w  Nameplate electrical output [W].
    @param availability   Online fraction in [0, 1]; 1.0 = never offline.
                          Values below 1.0 are reserved for future outage
                          modelling.

 available_power(t_hours, environment) -> float
    Electrical power available from the reactor at time t.

    @param  t_hours      Simulation time [h]. DELIBERATELY UNUSED.
    @param  environment  LunarEnvironment. DELIBERATELY UNUSED.
    @return Constant power [W] = rated_power_w * availability.

    @note A reactor does not care what time it is or whether the sun is up.
        Both parameters are nevertheless required: the uniform signature is
        what lets power_bus.py iterate over mixed source types without a single
        isinstance() check. Removing them to silence the linter would break
        polymorphic dispatch.
"""
from assets.base_asset import PowerSource
from config import (SOLAR_CONSTANT_W_PER_M2, PV_AREA_M2, PV_EFFICIENCY,
                    PV_PACKING_FACTOR, FSP_AVAILABILITY, FSP_RATED_POWER_W)


class PVArray(PowerSource):
    """Photovoltaic array; output tracks the environment's irradiance."""

    def __init__(self, name="PV Array", area_m2=PV_AREA_M2,
                efficiency=PV_EFFICIENCY, packing_factor=PV_PACKING_FACTOR):
        """Store the array's nameplate specification."""
        self.name = name
        self.area_m2 = area_m2
        self.efficiency = efficiency
        self.packing_factor = packing_factor

    def available_power(self, t_hours: float, environment) -> float:
        """P = G_sc * A * eta * f * phi(t), in watts."""
        irradiance = environment.solar_irradiance_fraction(t_hours)
        return (SOLAR_CONSTANT_W_PER_M2
                * self.area_m2
                * self.efficiency
                * self.packing_factor
                * irradiance)


class FissionSurfacePower(PowerSource):
    """Kilopower-class reactor; constant output, indifferent to time."""

    def __init__(self, name="FSP Reactor", rated_power_w=FSP_RATED_POWER_W,
                availability=FSP_AVAILABILITY):
        """Store the reactor's nameplate specification."""
        self.name = name
        self.rated_power_w = rated_power_w
        self.availability = availability

    def available_power(self, t_hours: float, environment) -> float:
        """Constant rated * availability; both arguments deliberately unused."""
        return self.rated_power_w * self.availability
