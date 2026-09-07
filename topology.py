"""
@file    topology.py
@brief   Electrical topology: the step that turns a power balance into a grid.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — spec and review only
@date    2026-09-07

@details
Everything built so far is a POWER BALANCE. Watts arrive, watts leave, and the
books close to 0.000e+00 W every tick. There is no voltage anywhere in the
model, no current, no conductor, and therefore nothing that could be built,
costed or massed. This module is where that changes.

--------------------------------------------------------------------------------
THE ARCHITECTURE, AND WHY IT IS NOT ONE BUS
--------------------------------------------------------------------------------
The literature settles most of this, and it settles it differently from what a
terrestrial instinct suggests.

  * The user bus is 120 VDC. Not a choice — NASA's International Space Power
    System Interoperability Standard (ISPSIS) fixes 120/28 VDC, and the MIPS
    project states the operating limit bluntly: "Power exchange must occur at
    120 VDC (requirement) and a distance less than 100 m (limitation of
    120 VDC)." Everything inside the outpost lives on that bus.

  * The reactor cannot. NASA FSP requires the reactor sited at least 1 km from
    other elements, and that requirement is NUCLEAR, not electrical — shielding
    by distance, with 3 km putting it below the 2.4 km lunar horizon. So the
    reactor is the one asset that needs a transmission link, and it needs one
    for a reason that has nothing to do with power engineering.

  * PV does not need a link. The same study is explicit: "photovoltaic panels
    do not need extensive separation from the habitat, DC can be used for local
    power transfer." The array sits on the user bus.

So the topology is a 120 VDC user bus with every asset on it EXCEPT the
reactor, which sits a kilometre away behind a boost / transmission / buck
chain. That asymmetry is the whole finding, and it is worth noticing that the
existing model — where the reactor is simply a source of 10 kW — hides it
completely.

--------------------------------------------------------------------------------
THE CEILING ON TRANSMISSION VOLTAGE IS SEMICONDUCTORS
--------------------------------------------------------------------------------
The terrestrial reflex is "raise the voltage until insulation or clearance
stops you". On the lunar surface that is the wrong limit. Fully space-qualified
silicon switches top out at 160 V, so a 1 kV transmission bus is built from six
stacked 175 V bridges, and radiation-hardening constraints cap practical DC
around 1.5 kV. The cable would happily carry more; there is nothing qualified
to switch it.

This is why NASA's own trade study lands on 3 kV AC 3-phase at 1 kHz for long
hauls despite DC cable being lighter — transformers step voltage without
needing a qualified switch at line potential. For a 1 km, 10 kW link the
stacked-DC route stays tractable, which is the case modelled here.

--------------------------------------------------------------------------------
WORK ORDERS
--------------------------------------------------------------------------------
    T01  this file  Feeder and DCBus: R(T), current, voltage drop, I^2R,
                    conductor mass, and the sizing rule that follows from a
                    loss budget.                                     <- YOU
    T02  power_bus  Wire feeders into the tick. The conservation identity
                    gains loss terms and stops closing at exactly zero.
    T03  converters Converter efficiency as a thing distinct from device
                    efficiency. Every asset gains one; the RFC currently
                    hides its power electronics inside its round trip.
    T04  protection Fault current, device ratings, zonal coordination, and
                    the DC arc-interruption problem.

Per the working agreement the physics in T01 is yours; ask for syntax or
algorithm help at any point and it appears. T02 plumbing is mine.

--------------------------------------------------------------------------------
T01 SPEC — WHAT TO IMPLEMENT
--------------------------------------------------------------------------------
Four methods on `Feeder`, then two on `DCBus`. Every one is a one-liner or
close to it; the difficulty is entirely in getting the physics right, and
there are three specific traps flagged below.

1.  resistance_ohm(self, temperature_k) -> float

        rho(T) = rho_20 * [1 + alpha * (T - T_ref)]
        R      = rho(T) * L_conductor / A

    TRAP ONE — L_conductor is NOT self.length_m. Current has to go out and
    come back. A DC feeder of physical span L contains 2L of conductor, and
    forgetting the return path halves every loss in the model. Use
    `self.conductor_length_m`, which is already defined for you below.

    TRAP TWO — temperature is not a detail here. A cable on the regolith has
    no convection and no air. NASA quotes surface cable temperatures reaching
    400 K in sunlight; lunar night bottoms out near 100 K. Run those through
    the formula before you write another line — the answer is interesting
    enough that it changes what the rest of the model says, and I would rather
    you find it than be told it.

2.  current_a(self, power_w, voltage_v) -> float

        I = P / V

    Guard V <= 0. This is DC, so there is no power factor and no phase
    angle — one of the few places where the lunar case is SIMPLER than
    terrestrial practice.

3.  voltage_drop_v(self, power_w, voltage_v, temperature_k) -> float
    loss_w(self, power_w, voltage_v, temperature_k) -> float

        dV     = I * R
        P_loss = I^2 * R

    TRAP THREE — P_loss is I^2 * R, not I * dV... except those are the same
    number. Convince yourself of that before moving on; if they disagree in
    your implementation, one of them is wrong.

4.  conductor_mass_kg(self) -> float

        m = density * A * L_conductor

    Round-trip length again.

5.  DCBus.total_loss_w(...) and DCBus.total_conductor_mass_kg()

    Sum over feeders. Trivial once the above is right.

6.  Feeder.size_for_loss_budget(...)  [CLASSMETHOD, the interesting one]

    Given a power, a voltage, a length and a loss fraction f, return the
    conductor area needed. Derive it rather than looking it up:

        P_loss = I^2 * R  <= f * P
        I = P / V,  R = rho * L_c / A

        (P/V)^2 * rho * L_c / A <= f * P
        A >= P * rho * L_c / (f * V^2)

    Note what that says: **A scales with 1/V^2**, so conductor mass does too.
    Doubling the transmission voltage quarters the copper. That single
    relationship is why the reactor link runs at kilovolts and why NASA's
    study concludes "the most important factor for decreasing mass is to
    increase Voltage".

    Then clamp to MIN_CONDUCTOR_AREA_M2 — below 16 AWG the limit is handling
    and thermal cycling, not electricity.

--------------------------------------------------------------------------------
WHAT THIS DELIBERATELY DOES NOT MODEL YET
--------------------------------------------------------------------------------
Declared, so nobody mistakes absence for oversight:

  * Insulation mass. It grows with voltage while conductor mass falls with
    V^2, so total cable mass has a genuine minimum — NASA finds it at about
    +/-4000 VDC for a 40 kW, 3 km link, using FEP at a 4.4 kV/mm design
    stress. Without it, this model will tell you higher voltage is always
    better, which is false. T01 may add it; if not, it is a declared gap.
  * Micrometeoroid shielding and cable redundancy, both excluded from NASA's
    own mass figure too.
  * Skin effect. This is DC, so there is none. Worth stating because it is
    the first thing a terrestrial engineer asks about a 1 kHz AC alternative.
  * The linear temperature coefficient at 100 K. Resistivity flattens toward
    a residual value at cryogenic temperatures and the linear extrapolation
    overstates how good night-time conductors get. The model is honest in
    daylight and optimistic at night.

@see config.py for every constant used here, each with its source.
@see NASA NTRS 20220002315, "Lunar Power Transmission for Fission Surface
    Power" — the 160 V device limit, the 5 %/3 km loss budget, the +/-4 kV
    optimum, aluminium conductor.
@see NASA NTRS 20250000763, Csank, "Electric Power on the Moon" — ISPSIS
    120 VDC, the 100 m limitation, the radial/ring/mesh mass trade, and the
    1.5 kV radiation-hardening cap.


================================================================================
API
================================================================================

Feeder                                                              [dataclass]
    One electrical run between a bus and an asset, or between two buses.

    @param  name                Human label, used in records and figures.
    @param  length_m            PHYSICAL span. The conductor is twice this.
    @param  area_m2             Cross-sectional area of ONE conductor.
    @param  nominal_voltage_v   Operating voltage of the run.

    @property conductor_length_m
        2 * length_m. Out and back. Provided so the return path cannot be
        forgotten silently.

    resistance_ohm(temperature_k) -> float
        Round-trip resistance at a conductor temperature.
        @note Temperature is mandatory, not defaulted. A default would let a
            caller quietly evaluate a 400 K daylight cable at 20 C.

    current_a(power_w, voltage_v) -> float
        @return P / V, or 0.0 for a non-positive voltage.

    voltage_drop_v(power_w, voltage_v, temperature_k) -> float
    loss_w(power_w, voltage_v, temperature_k) -> float
    conductor_mass_kg() -> float

    size_for_loss_budget(power_w, voltage_v, length_m, loss_fraction) -> float
        [classmethod] Required conductor area, clamped to the minimum gauge.

DCBus                                                               [dataclass]
    A voltage level and the feeders attached to it.

    @param  name               'user' or 'transmission'.
    @param  nominal_voltage_v  120.0 for the user bus.
    @param  feeders            The runs attached.

    total_loss_w(power_by_feeder, temperature_k) -> float
    total_conductor_mass_kg() -> float

cable_temperature_k(is_daylight) -> float
    400 K in sunlight, 100 K at night. A step function, matching the square
    wave the environment already uses for availability.
"""

import dataclasses

from config import (CABLE_TEMP_DAY_K, CABLE_TEMP_NIGHT_K,
                    CABLE_TEMP_REFERENCE_K, CONDUCTOR_DENSITY_KG_PER_M3,
                    CONDUCTOR_RESISTIVITY_OHM_M, CONDUCTOR_TEMP_COEFF_PER_K,
                    MIN_CONDUCTOR_AREA_M2)


def cable_temperature_k(is_daylight: bool) -> float:
    """400 K in sunlight, 100 K at night."""
    return CABLE_TEMP_DAY_K if is_daylight else CABLE_TEMP_NIGHT_K


@dataclasses.dataclass
class Feeder:
    """One electrical run; see the API section for the contract."""

    name: str
    length_m: float
    area_m2: float
    nominal_voltage_v: float

    @property
    def conductor_length_m(self) -> float:
        """Out and back. Every length in this class is this one, not length_m."""
        return 2.0 * self.length_m

    # =========================================================================
    # START EDITING HERE — T01, method 1
    # =========================================================================
    def resistance_ohm(self, temperature_k: float) -> float:
        """Round-trip resistance at a conductor temperature.

        rho(T) = CONDUCTOR_RESISTIVITY_OHM_M
                 * (1 + CONDUCTOR_TEMP_COEFF_PER_K
                        * (temperature_k - CABLE_TEMP_REFERENCE_K))
        R      = rho(T) * self.conductor_length_m / self.area_m2
        """
        raise NotImplementedError("T01 method 1")

    # ------------------------------------------------------------------ 2 ---
    def current_a(self, power_w: float, voltage_v: float) -> float:
        """I = P / V; 0.0 for a non-positive voltage."""
        raise NotImplementedError("T01 method 2")

    # ------------------------------------------------------------------ 3 ---
    def voltage_drop_v(self, power_w: float, voltage_v: float,
                       temperature_k: float) -> float:
        """dV = I * R."""
        raise NotImplementedError("T01 method 3a")

    def loss_w(self, power_w: float, voltage_v: float,
               temperature_k: float) -> float:
        """P_loss = I^2 * R."""
        raise NotImplementedError("T01 method 3b")

    # ------------------------------------------------------------------ 4 ---
    def conductor_mass_kg(self) -> float:
        """m = density * area * round-trip length."""
        raise NotImplementedError("T01 method 4")

    # ------------------------------------------------------------------ 6 ---
    @classmethod
    def size_for_loss_budget(cls, power_w: float, voltage_v: float,
                             length_m: float, loss_fraction: float) -> float:
        """Conductor area meeting a loss budget; clamped to MIN_CONDUCTOR_AREA_M2.

        A >= power_w * rho * (2 * length_m) / (loss_fraction * voltage_v ** 2)

        Use CONDUCTOR_RESISTIVITY_OHM_M at the reference temperature — sizing
        against a hot cable is a design decision, and doing it silently inside
        a sizing helper hides it.
        """
        raise NotImplementedError("T01 method 6")


@dataclasses.dataclass
class DCBus:
    """A voltage level and the feeders attached to it."""

    name: str
    nominal_voltage_v: float
    feeders: list = dataclasses.field(default_factory=list)

    # ------------------------------------------------------------------ 5 ---
    def total_loss_w(self, power_by_feeder: dict, temperature_k: float) -> float:
        """Sum loss_w over feeders; a feeder absent from the dict carries 0 W."""
        raise NotImplementedError("T01 method 5a")

    def total_conductor_mass_kg(self) -> float:
        """Sum conductor_mass_kg over feeders."""
        raise NotImplementedError("T01 method 5b")
