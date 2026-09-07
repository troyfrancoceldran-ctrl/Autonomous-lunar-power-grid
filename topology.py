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
    T01  this file  Feeder and DCBus.
    T02  power_bus  Wire feeders into the tick. The conservation identity
                    gains loss terms and stops closing at exactly zero.
    T03  converters Converter efficiency as a thing distinct from device
                    efficiency. Every asset gains one; the RFC currently
                    hides its power electronics inside its round trip.
    T04  protection Fault current, device ratings, zonal coordination, and
                    the DC arc-interruption problem.

--------------------------------------------------------------------------------
HOW T01 IS SPLIT
--------------------------------------------------------------------------------
Agreed 2026-09-07: the ELECTRICAL CORE is the user's, the PLUMBING is Claude's.
The line is drawn at whether a method encodes a decision about electricity or
merely moves numbers around.

    USER — the electrical core                     marked  >>> YOURS
        resistance_ohm          rho(T), and R from geometry
        current_a               I = P / V
        voltage_drop_v          dV = I R
        loss_w                  P = I^2 R
        size_for_loss_budget    the A >= ... / V^2 derivation
        (T04 later)             fault current and device ratings

    CLAUDE — the plumbing                          already implemented
        Feeder / DCBus dataclasses and conductor_length_m
        conductor_mass_kg       geometry and density, no electricity in it
        DCBus aggregation       summing over feeders
        build_topology()        which feeders exist and what they connect
        T02 wiring, record schema, tests

Every plumbing method below WORKS NOW. The six marked >>> YOURS raise
NotImplementedError, and `tests/test_topology.py` skips the tests that depend
on them until they stop raising — so the suite stays green while you work and
lights up method by method as you go. Nothing to configure; just implement and
re-run pytest.

Ask for syntax or algorithm help at any point and it appears; the engineering
judgement stays yours.

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

4.  conductor_mass_kg(self)                                  [DONE — plumbing]

        m = density * A * L_conductor

    Geometry and density, no electricity in it, so it is on my side of the
    line. Written and tested; read it if you want the round-trip length
    handled correctly in one place.

5.  DCBus aggregation                                        [DONE — plumbing]

    total_loss_w() and total_conductor_mass_kg() both work. total_loss_w
    calls YOUR loss_w, so it will raise until method 3b lands — which is the
    point: the plumbing is ready and waiting on the physics.

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
                    FSP_RATED_POWER_W, FSP_SEPARATION_M,
                    MAX_FEEDER_LOSS_FRACTION, MIN_CONDUCTOR_AREA_M2,
                    TRANSMISSION_VOLTAGE_V, USER_BUS_MAX_SPAN_M,
                    USER_BUS_VOLTAGE_V)


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
    # START EDITING HERE — T01, method 1                            >>> YOURS
    # =========================================================================
    def resistance_ohm(self, temperature_k: float) -> float:
        """Round-trip resistance at a conductor temperature.

        rho(T) = CONDUCTOR_RESISTIVITY_OHM_M
                 * (1 + CONDUCTOR_TEMP_COEFF_PER_K
                        * (temperature_k - CABLE_TEMP_REFERENCE_K))
        R      = rho(T) * self.conductor_length_m / self.area_m2
        """
        raise NotImplementedError("T01 method 1")

    # ------------------------------------------------------------- 2 >>> YOURS
    def current_a(self, power_w: float, voltage_v: float) -> float:
        """I = P / V; 0.0 for a non-positive voltage."""
        raise NotImplementedError("T01 method 2")

    # ------------------------------------------------------------- 3 >>> YOURS
    def voltage_drop_v(self, power_w: float, voltage_v: float,
                       temperature_k: float) -> float:
        """dV = I * R."""
        raise NotImplementedError("T01 method 3a")

    def loss_w(self, power_w: float, voltage_v: float,
               temperature_k: float) -> float:
        """P_loss = I^2 * R."""
        raise NotImplementedError("T01 method 3b")

    # --------------------------------------------------------- 4 — plumbing
    def conductor_mass_kg(self) -> float:
        """Mass of conductor in this run, both directions.

        Geometry and density only — no electricity, which is why it sits on
        the plumbing side. Note it uses conductor_length_m, so the return
        path is counted here and nowhere else has to remember to.
        """
        return (CONDUCTOR_DENSITY_KG_PER_M3 * self.area_m2
                * self.conductor_length_m)

    # ------------------------------------------------------------- 6 >>> YOURS
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

    # --------------------------------------------------------- 5 — plumbing
    def total_loss_w(self, power_by_feeder: dict, temperature_k: float) -> float:
        """Sum loss over feeders; a feeder absent from the dict carries 0 W.

        Absent means idle, not an error: on a given tick most feeders carry
        nothing, and requiring every one to appear would make the caller
        build a full dict of zeros each time.

        @note Calls Feeder.loss_w, so this raises NotImplementedError until
            T01 method 3b lands. That is deliberate — the plumbing is
            finished and waiting on the physics, not silently returning 0.0.
        """
        return sum(
            feeder.loss_w(power_by_feeder.get(feeder.name, 0.0),
                          feeder.nominal_voltage_v, temperature_k)
            for feeder in self.feeders
        )

    def total_conductor_mass_kg(self) -> float:
        """Sum conductor mass over feeders. The number a lander cares about."""
        return sum(feeder.conductor_mass_kg() for feeder in self.feeders)

    def feeder(self, name: str):
        """Look a feeder up by name; KeyError if it is not on this bus."""
        for candidate in self.feeders:
            if candidate.name == name:
                return candidate
        raise KeyError(f"no feeder named {name!r} on bus {self.name!r}")


# =============================================================================
# The outpost's actual wiring — plumbing, mine.
# =============================================================================
# Physical layout. Every distance is a guess with a reason, and every reason is
# a geometry constraint rather than an electrical one:
#
#   PV array      50 m   clear of habitat shadowing, and far enough that
#                        habitat traffic does not re-deposit dust on it
#   Battery       10 m   adjacent to the habitat; short runs are cheap and it
#                        is the highest-current asset on the bus
#   RFC           20 m   standoff for stored hydrogen and oxygen
#   ECLSS          5 m   inside the habitat
#   Thermal       10 m   radiators on the habitat exterior
#   Comms         30 m   high-gain antenna clear of structure
#   Science       60 m   field instruments, the longest user-bus run
#   Reactor     1000 m   NOT a layout choice — the FSP separation requirement
#
# The user bus holds every run under the 100 m ISPSIS limit. The reactor is
# 10x outside it, which is precisely why it needs its own voltage level.

USER_BUS_LAYOUT = [
    # (name,             length_m, peak_w)
    ("PV Array",             50.0,  34_900.0),
    ("Battery Bank",         10.0,  50_000.0),
    ("Regenerative Fuel Cell", 20.0, 25_000.0),
    ("Environmental Control and Life Support System", 5.0, 6_500.0),
    ("Thermal Control",      10.0,   5_500.0),
    ("Communications Array", 30.0,   2_500.0),
    ("Science Payload",      60.0,   6_000.0),
]

# PROVISIONAL conductor area, used so the topology can be built and inspected
# before T01's sizing method exists. Once size_for_loss_budget lands, call
# build_topology(sized=True) and these are replaced by computed values.
PROVISIONAL_AREA_M2 = 1.0e-5      # 10 mm^2


def build_topology(sized: bool = False,
                   loss_fraction: float = MAX_FEEDER_LOSS_FRACTION):
    """Construct the outpost's buses and feeders.

    @param  sized  False uses PROVISIONAL_AREA_M2 everywhere, so the topology
                   is inspectable before the sizing method exists. True sizes
                   every feeder from its peak power via
                   Feeder.size_for_loss_budget — which raises until T01
                   method 6 is implemented.
    @return (user_bus, transmission_bus)

    @note This is the ONLY place feeder geometry is named, the same way
        main.build_outpost is the only place concrete assets are named. A
        figure or a metric should read the topology, never restate it.
    """
    def area(power_w, length_m, voltage_v):
        if not sized:
            return PROVISIONAL_AREA_M2
        return Feeder.size_for_loss_budget(power_w, voltage_v, length_m,
                                           loss_fraction)

    user = DCBus(name="user", nominal_voltage_v=USER_BUS_VOLTAGE_V, feeders=[
        Feeder(name=name,
               length_m=length_m,
               area_m2=area(peak_w, length_m, USER_BUS_VOLTAGE_V),
               nominal_voltage_v=USER_BUS_VOLTAGE_V)
        for name, length_m, peak_w in USER_BUS_LAYOUT
    ])

    transmission = DCBus(
        name="transmission",
        nominal_voltage_v=TRANSMISSION_VOLTAGE_V,
        feeders=[Feeder(
            name="Fission Surface Power",
            length_m=FSP_SEPARATION_M,
            area_m2=area(FSP_RATED_POWER_W, FSP_SEPARATION_M,
                         TRANSMISSION_VOLTAGE_V),
            nominal_voltage_v=TRANSMISSION_VOLTAGE_V,
        )],
    )
    return user, transmission


def over_span_limit(bus) -> list:
    """Feeders on a 120 VDC bus that exceed the ISPSIS 100 m limitation.

    Returns names, so a caller can report them rather than just assert. On the
    nominal layout this is empty for the user bus and would be non-empty the
    moment someone moved an asset out past the limit without changing voltage.
    """
    if bus.nominal_voltage_v > USER_BUS_VOLTAGE_V:
        return []
    return [f.name for f in bus.feeders if f.length_m > USER_BUS_MAX_SPAN_M]
