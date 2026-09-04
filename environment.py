"""
@file    environment.py
@brief   Lunar day/night cycle and solar availability over simulated time.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-03

@details
The outpost sits through the 708.7 h lunar synodic cycle: 354.35 h of
continuous sunlight followed by 354.35 h of total darkness. This module
answers one question —
"how much sun is there at time t?" — and nothing else.

It is deliberately STATELESS beyond a single constructor argument, so
PVArray.available_power() can query any t, in any order, without the
environment having to be "stepped" forward in lockstep with the engine.

@note This class is the seam where the simulation meets reality. On real
    hardware it is replaced by an irradiance sensor reading; every downstream
    consumer keeps working unchanged.


================================================================================
API
================================================================================

--------------------------------------------------------------------------------
class LunarEnvironment
--------------------------------------------------------------------------------
Pure model of the lunar day/night cycle.

@var start_phase_hours  Offset [h] placing t=0 somewhere within the cycle.

__init__(start_phase_hours=0.0)
    Construct an environment with a chosen starting phase.

    @param start_phase_hours  Where t=0 sits within the 708.7 h cycle [h].
                            0.0 starts at lunar dawn; LUNAR_DAY_HOURS
                            (354.35) starts at nightfall, which is the stress
                            scenario for testing storage sizing.

is_daylight(t_hours) -> bool
    Whether the outpost is in sunlight at time t.

    @param  t_hours  Simulation time [h] since t=0.
    @return True during the lunar day, False during the night.

    @note The modulo folds absolute time into one cycle, so this stays correct
        across the full 60-day run and beyond.
    @note The comparison is STRICT: phase 354.35 is the first instant of
        night, not the last of day. Because the synodic cycle is not a whole
        number of hours, a 1 h timestep never lands exactly on the terminator
        — it is sampled at whichever integer hour precedes it, so the
        day/night split drifts by under an hour per cycle. Harmless at this
        resolution, but worth knowing before anyone reads an exact 354 h
        night off a plot.

solar_irradiance_fraction(t_hours) -> float
    Fraction of peak solar flux available at time t.

    @param  t_hours  Simulation time [h] since t=0.
    @return 1.0 in daylight, 0.0 at night. Always within [0, 1].

    @note Delegates to is_daylight() rather than repeating the modulo, so the
        two can never disagree about where the terminator falls.
    @note This stays a SQUARE WAVE by design — it answers "is there sun",
        not "how much". Magnitude is solar_elevation_fraction()'s job. Two
        methods rather than one because the polar/tracking case wants the
        square wave and the equatorial/fixed case wants the sine, and
        PVArray selects between them.


================================================================================
SPEC — W01 (closes finding F-02).  Author: user.  Reviewer: JARVIS.
================================================================================
Add solar_elevation_fraction() and factor the phase calculation out into a
shared private helper. Nothing outside this file changes in W01; PVArray
starts consuming the new method in W02.

WHY
    The square wave models the sun as a lamp switched on for 354.35 h at full
    strength. On the real surface the sun climbs from the horizon at dawn to
    near-zenith at local noon and back down, and the flux striking a fixed
    panel follows the SINE of that elevation angle (Lambert's cosine law,
    written against elevation instead of the zenith angle).

    The Moon's axial tilt is 1.54 deg, so at an equatorial or mid-latitude
    site the sun's path is very nearly a clean semicircle — a plain sine is a
    good model, not a crude one.

    @note Boundary of the model: NASA's Artemis surface sites are POLAR
        (Shackleton rim and neighbours), where the sun stays within a few
        degrees of the horizon and arrays are mounted vertically and tracked
        in azimuth. There the square wave is closer to right than the sine.
        That is exactly what config.PV_SUN_TRACKING selects between in W02 —
        so declare the regime rather than silently assuming one.

--------------------------------------------------------------------------------
_phase_hours(t_hours) -> float                                       [private]
--------------------------------------------------------------------------------
    Position within the current synodic cycle.

    @param  t_hours  Simulation time [h] since t=0.
    @return Phase in [0, LUNAR_CYCLE_HOURS), i.e. [0, 708.7).

    @note Refactor is_daylight() to call this instead of repeating the
        modulo. Three methods computing the same phase three times is three
        chances for them to disagree about where the terminator falls.
    @note Python's % returns a non-negative result for a positive modulus, so
        negative t_hours folds correctly with no special case.

--------------------------------------------------------------------------------
solar_elevation_fraction(t_hours) -> float
--------------------------------------------------------------------------------
    Sine of the solar elevation angle — the fraction of peak flux striking a
    horizontal panel at time t.

    @param  t_hours  Simulation time [h] since t=0.
    @return sin(pi * phase / LUNAR_DAY_HOURS) during the day, 0.0 at night.
            Always within [0, 1].

    @note Needs `import math` at the top of the module.
    @note The argument maps the day onto [0, pi]: dawn (phase 0) and sunset
        (phase -> LUNAR_DAY_HOURS) both give 0.0, local noon gives 1.0.
    @note Gate on the night case FIRST and return 0.0. Feeding a night phase
        into the sine gives a NEGATIVE number — physically it is the sun
        below the horizon, and it would quietly subtract PV power from the
        bus. Reuse is_daylight() for the gate so the two agree by
        construction.
    @warning Clamp the result with max(0.0, ...) even though the sine cannot
        be negative for phase in [0, LUNAR_DAY_HOURS). sin(pi) evaluates to
        1.22e-16 rather than 0, and this method feeds a multiplication chain
        that ends at a power balance; a defensive floor here costs nothing.

    PSEUDOCODE
        phase = self._phase_hours(t_hours)
        if not daylight at t:
            return 0.0
        return max(0.0, sin(pi * phase / LUNAR_DAY_HOURS))

--------------------------------------------------------------------------------
VERIFICATION — expected values
--------------------------------------------------------------------------------
    t [h]        phase       expected      meaning
    0.0          0.00      0.000000      lunar dawn, sun on the horizon
    88.5875      88.59      0.707107      mid-morning, quarter through day
    177.175      177.18      1.000000      local noon, sun at peak
    265.7625     265.76      0.707107      mid-afternoon
    354.0        354.00      0.003103      final hour before sunset
    354.35       354.35      0.000000      first instant of night
    500.0        500.00      0.000000      deep night
    708.7          0.00      0.000000      dawn of the next cycle
    886.0        177.30      0.999999      noon of the second cycle

    Also assert: 0.0 <= f(t) <= 1.0 for every t, and f(t) == 0.0 exactly
    whenever is_daylight(t) is False.

--------------------------------------------------------------------------------
CONSEQUENCE — read this before W02
--------------------------------------------------------------------------------
    The mean of sin over a half-cycle is 2/pi = 0.6366. Once PVArray consumes
    this in W02, daylight PV ENERGY falls to 63.7 % of what the square wave
    was reporting, and the dust derate takes 5 % more of what remains — about
    60.5 % in total. The 36.75 kW peak is unchanged; it is the area under the
    curve that collapses.

    Expect the energy balance to stop closing and PV_AREA_M2 to need growing.
    That is not a bug in your code — it is the square wave having flattered
    the design since Step 3. Do not tune anything to hide it; W02 will
    measure the new balance and resize deliberately.
"""
import math

from config import LUNAR_CYCLE_HOURS
from config import LUNAR_DAY_HOURS


class LunarEnvironment:
    """Pure model of the lunar day/night cycle."""

    def __init__(self, start_phase_hours: float = 0.0):
        """Place t=0 at a chosen point in the 708.7 h synodic cycle."""
        self.start_phase_hours = start_phase_hours

    def _phase_hours(self, t_hours: float) -> float:
        """Position within the current synodic cycle, in [0, 708.7)."""
        return (t_hours + self.start_phase_hours) % LUNAR_CYCLE_HOURS

    def is_daylight(self, t_hours: float) -> bool:
        """True while the outpost is in sunlight. Strict < at the terminator."""
        return self._phase_hours(t_hours) < LUNAR_DAY_HOURS

    def solar_irradiance_fraction(self, t_hours: float) -> float:
        """Peak-flux fraction in [0, 1]; square wave — availability only."""
        return 1.0 if self.is_daylight(t_hours) else 0.0

    def solar_elevation_fraction(self, t_hours: float) -> float:
        """Sine of solar elevation in [0, 1]; 0.0 at night."""
        if not self.is_daylight(t_hours):
            return 0.0
        phase = self._phase_hours(t_hours)
        return max(0.0, math.sin(math.pi * phase / LUNAR_DAY_HOURS))
