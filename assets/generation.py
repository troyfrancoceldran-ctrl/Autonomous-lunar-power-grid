"""
@file    generation.py
@brief   Concrete PowerSource implementations: PVArray, FissionSurfacePower.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-03

@details
The outpost's two generation assets, with opposite characters:

    PVArray               36.75 kW peak, but ZERO for 354.35 consecutive hours.
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
@var dust_derate     Regolith obscuration factor [-].
@var sun_tracking    True = tracked array / Vertical Solar Array; False = fixed.

__init__(name="PV Array", area_m2, efficiency, packing_factor, dust_derate,
        sun_tracking)
    Construct a PV array from its nameplate specification.

    @param name            Identifier for logs and plots.
    @param area_m2         Array area [m^2].
    @param efficiency      Conversion efficiency in [0, 1].
    @param packing_factor  Aggregate array-level derate in [0, 1].
    @param dust_derate     Regolith obscuration factor in [0, 1].
    @param sun_tracking    Selects the daily profile; see available_power().

    @note The config constants supply DEFAULTS only. Each instance stores its
        own values, so two arrays of different sizes can coexist.
    @note dust_derate is kept SEPARATE from packing_factor although both are
        dimensionless multipliers near 1. Packing factor is array geometry and
        wiring; dust is a surface condition that worsens over mission life.
        Any later revision makes dust a function of elapsed time and leaves
        packing factor alone, so collapsing them would destroy that seam.

available_power(t_hours, environment) -> float
    Electrical power available from the array at time t.

    @param  t_hours      Simulation time [h] since t=0.
    @param  environment  LunarEnvironment supplying the solar profile.
    @return Available power [W]: 0 at night, ~34.9 kW at full sun.

    Computes P = G_sc * A * eta * f * d * phi(t), where G_sc is the solar
    constant at 1 AU (1361 W/m^2 — the Moon has no atmosphere, so the full
    extraterrestrial value reaches the panels), d is the dust derate, and
    phi(t) is a solar profile in [0, 1].

    Dimensionally: [W/m^2] * [m^2] * [-] * [-] * [-] * [-] = [W].

    @note sun_tracking SELECTS phi; it does not scale the result. True asks
        the environment for solar_irradiance_fraction() — the square wave a
        tracker or polar Vertical Solar Array sees. False asks for
        solar_elevation_fraction() — the sine a fixed equatorial array sees.
        Written as an if/else branch rather than arithmetic, because the
        branch is the statement of which site is being modelled. Multiplying
        by the bool instead would either annihilate the array (False == 0) or
        do nothing at all (True == 1).
    @note The array knows nothing about lunar cycles. It asks the environment
        for a fraction and scales by it — which is why swapping in a real
        irradiance sensor requires no change here.

--------------------------------------------------------------------------------
class FissionSurfacePower(PowerSource)
--------------------------------------------------------------------------------
Kilopower-class fission reactor; constant output, indifferent to time.

@var name                   Identifier used in logs and plot legends.
@var rated_power_w          Nameplate electrical output [W].
@var availability           Fraction of time online, in [0, 1].
@var outage_start_hours     Start of the scripted outage [h], or None.
@var outage_duration_hours  Length of that outage [h].

__init__(name="FSP Reactor", rated_power_w, availability, outage_start_hours,
        outage_duration_hours)
    Construct a reactor from its nameplate specification.

    @param name                   Identifier for logs and plots.
    @param rated_power_w          Nameplate electrical output [W].
    @param availability           Online fraction in [0, 1]; 1.0 = idealised.
    @param outage_start_hours     When the scripted outage begins [h]; None
                                disables it entirely.
    @param outage_duration_hours  How long it lasts [h].

available_power(t_hours, environment) -> float
    Electrical power available from the reactor at time t.

    @param  t_hours      Simulation time [h]; used only to test the outage
                        window.
    @param  environment  LunarEnvironment. DELIBERATELY UNUSED.
    @return 0.0 while inside the outage window, otherwise
            rated_power_w * availability [W].

    @note A reactor does not care whether the sun is up, so `environment` goes
        unread. It is nevertheless required: the uniform signature is what
        lets power_bus.py iterate over mixed source types without a single
        isinstance() check. Removing it to silence the linter would break
        polymorphic dispatch.
    @note The outage window is HALF-OPEN — start <= t < start + duration —
        matching the terminator convention in environment.py. It fires ONCE,
        not once per cycle: the point is a reproducible contingency, not a
        duty cycle.
    @warning The guard tests `is not None`, never truthiness. An outage
        starting at t = 0.0 — cold start with the reactor still offline — is a
        legitimate scenario, and `if self.outage_start_hours:` would silently
        read 0.0 as "disabled". Legal Python, wrong answer, no error.
    @note A reactor that never fails is the most idealised object a microgrid
        model can contain. NASA's FSP requirement set calls for autonomous
        start and stop without human assistance precisely because outages are
        expected events. Default config leaves this at None; switch it on for
        a contingency scenario.


================================================================================
SPEC — W02 (closes finding F-04).  Author: user.  Reviewer: JARVIS.
================================================================================
PVArray gains two derates it has been silently omitting: dust accumulation,
and the choice between a fixed array and a tracked one.

WHY
    Step 3 multiplied by solar_irradiance_fraction(), a square wave. That
    assumed BOTH that the array is perfectly pointed at the sun all day AND
    that its glass is clean. Neither is free, and neither was declared.

    Dust: lunar regolith is electrostatically charged, sharp and clingy, with
    no atmosphere or rain to remove it. Measured short-circuit current falls
    with deposited dust mass, and every nearby landing adds more.

    Pointing: a fixed horizontal array at an equatorial site follows the sine
    of solar elevation (W01). A tracker — or a NASA-style Vertical Solar Array
    at a polar site, turning in azimuth — holds near peak all day, which is
    the square wave. Assuming the wrong one overstates daily energy by 36 %.

__init__ gains two parameters, defaulting from config:

    dust_derate=PV_DUST_DERATE        obscuration factor in [0, 1]
    sun_tracking=PV_SUN_TRACKING      True = tracked/VSA, False = fixed

    Store both on self, as with every other nameplate value.

available_power(t_hours, environment) -> float
    P = G_sc * A * eta * f * d * phi(t)

        G_sc   SOLAR_CONSTANT_W_PER_M2   1361 W/m^2
        A      self.area_m2
        eta    self.efficiency
        f      self.packing_factor
        d      self.dust_derate                                     <-- new
        phi    profile chosen by self.sun_tracking                  <-- new

    phi(t) is environment.solar_irradiance_fraction(t) when sun_tracking is
    True, and environment.solar_elevation_fraction(t) when it is False.

    PSEUDOCODE
        if self.sun_tracking:
            phi = environment.solar_irradiance_fraction(t_hours)
        else:
            phi = environment.solar_elevation_fraction(t_hours)
        return G_sc * A * eta * f * d * phi

    @note Select ONE profile with if/else. Do not call both and discard one —
        the branch is the statement of which site we are modelling, and a
        reader should be able to see it.
    @warning Do NOT fold dust_derate into packing_factor, however tempting.
        They have different provenance (one is array geometry and wiring, the
        other is a surface condition) and different futures: dust becomes a
        function of mission elapsed time in any later revision, packing factor
        never does. Collapsing them now destroys that seam.
    @note The array still asks the environment for a fraction and scales by
        it. That property is what lets a real irradiance sensor replace the
        model later, and W02 must not break it.

VERIFICATION — expected values, at the config defaults
    base = 1361 * 100 * 0.30 * 0.90        = 36747.00 W   (undusted peak)
    base * dust_derate                      = 34909.65 W   (dusted peak)

        t [h]        fixed [W]      tracking [W]   meaning
        0.0             0.00         34909.65    dawn
        88.5875      24684.85         34909.65    quarter through day
        177.175       34909.65         34909.65    local noon — both agree
        354.0           108.33         34909.65    last hour before sunset
        354.35            0.00             0.00    first instant of night
        500.0             0.00             0.00    deep night

    Both profiles must give 0.0 at night and must agree exactly at local noon.
    If they disagree at noon, the dust derate has been applied to one path
    only.

MEASURED CONSEQUENCE — do not resize the array
    Running the full 60-day balance with sine + dust at PV_AREA_M2 = 100:
    unserved energy 0.0 kWh, battery floor 0.050, RFC floor 0.174 (against
    0.241 under the old square wave). The night is still survivable; only the
    reserve margin narrows. Daylight surplus is 11749 kWh against the 4720 kWh
    needed to refill the tanks, so surplus was never the binding constraint
    and extra area buys almost nothing — 200 m^2 lifts the RFC floor only to
    0.203. LEAVE PV_AREA_M2 AT 100 and record the narrower margin as a result.


================================================================================
SPEC — W03 (closes finding F-03).  Author: user.  Reviewer: JARVIS.
================================================================================
FissionSurfacePower gains a scripted outage window, so contingency behaviour
is reproducible rather than stochastic.

WHY
    A reactor that never fails is the single most idealised object in this
    model. NASA's FSP requirement set calls for autonomous start and stop
    without human assistance precisely because outages — scram, thermal
    trip, maintenance — are expected events, not unthinkable ones. An
    outpost design that has never been shown surviving one has not been
    shown to work.

__init__ gains two parameters, defaulting from config:

    outage_start_hours=FSP_OUTAGE_START_HOURS          float | None
    outage_duration_hours=FSP_OUTAGE_DURATION_HOURS    float

available_power(t_hours, environment) -> float
    Return 0.0 while inside the outage window, otherwise the existing
    rated_power_w * availability.

    Window is HALF-OPEN, matching the terminator convention in environment.py:

        outage_start_hours <= t_hours < outage_start_hours + duration

    PSEUDOCODE
        if self.outage_start_hours is not None:
            end = self.outage_start_hours + self.outage_duration_hours
            if self.outage_start_hours <= t_hours < end:
                return 0.0
        return self.rated_power_w * self.availability

    @warning Test `is not None`, NEVER a bare truthiness test. An outage
        starting at t = 0.0 is a perfectly reasonable scenario — cold start
        with the reactor still offline — and `if self.outage_start_hours:`
        would silently treat 0.0 as "disabled". This is the same class of
        fault as the missing @property in Step 4: legal Python, wrong answer,
        no error.
    @note A SINGLE window, not one per cycle. The point is a reproducible
        contingency, not a duty cycle.
    @note t_hours is now genuinely used, so the "DELIBERATELY UNUSED" note in
        this file's API section above must be corrected as part of W03.
        `environment` remains unused and that note stands.

VERIFICATION — with outage_start_hours=500.0, duration 24.0
        t [h]      expected [W]   meaning
        499.0          10000.0    before the window
        500.0              0.0    first hour offline (inclusive start)
        512.0              0.0    mid-outage
        523.9              0.0    last instant offline
        524.0          10000.0    recovered (exclusive end)
        600.0          10000.0    well after

    With outage_start_hours=None, available_power must be 10000.0 at every t.

    @note Leave FSP_OUTAGE_START_HOURS at None in config. The default run
        stays outage-free; the contingency is switched on deliberately for a
        scenario. t = 500 h sits in deep lunar night, which is the case worth
        studying — PV cannot help, so the whole deficit lands on storage.
"""
from assets.base_asset import PowerSource
from config import (SOLAR_CONSTANT_W_PER_M2
                    , PV_AREA_M2
                    , PV_EFFICIENCY
                    , PV_PACKING_FACTOR
                    , FSP_AVAILABILITY
                    , FSP_RATED_POWER_W
                    , PV_DUST_DERATE
                    , PV_SUN_TRACKING
                    , FSP_OUTAGE_DURATION_HOURS
                    , FSP_OUTAGE_START_HOURS)

class PVArray(PowerSource):
    """Photovoltaic array; output tracks the environment's irradiance."""

    def __init__(self, name="PV Array"
                , area_m2=PV_AREA_M2
                , efficiency=PV_EFFICIENCY
                , packing_factor=PV_PACKING_FACTOR
                , dust_derate=PV_DUST_DERATE
                , sun_tracking=PV_SUN_TRACKING):
        """Store the array's nameplate specification."""
        self.name = name
        self.area_m2 = area_m2
        self.efficiency = efficiency
        self.packing_factor = packing_factor
        self.dust_derate = dust_derate
        self.sun_tracking = sun_tracking

    def available_power(self, t_hours: float, environment) -> float:
        """P = G_sc * A * eta * f * d * phi(t), in watts."""
        if self.sun_tracking:
            phi = environment.solar_irradiance_fraction(t_hours)
        else:
            phi = environment.solar_elevation_fraction(t_hours)
        return (SOLAR_CONSTANT_W_PER_M2
                * self.area_m2
                * self.efficiency
                * self.packing_factor
                * self.dust_derate
                * phi)


class FissionSurfacePower(PowerSource):
    """Kilopower-class reactor; constant output, indifferent to time."""

    def __init__(self, name="FSP Reactor"
                , rated_power_w=FSP_RATED_POWER_W
                , availability=FSP_AVAILABILITY
                , outage_start_hours=FSP_OUTAGE_START_HOURS
                , outage_duration_hours=FSP_OUTAGE_DURATION_HOURS):
        """Store the reactor's nameplate specification."""
        self.name = name
        self.rated_power_w = rated_power_w
        self.availability = availability
        self.outage_start_hours = outage_start_hours
        self.outage_duration_hours = outage_duration_hours

    def available_power(self, t_hours: float, environment) -> float:
        """Rated * availability, or 0 W inside the scripted outage window."""
        if self.outage_start_hours is not None:
            end = self.outage_start_hours + self.outage_duration_hours
            if self.outage_start_hours <= t_hours < end:
                return 0.0
        return self.rated_power_w * self.availability
