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
    @note v1 is a square wave. A sun-angle-based ramp near the terminator is a
        reasonable v2 refinement; only this method would change.
"""
from config import LUNAR_CYCLE_HOURS
from config import LUNAR_DAY_HOURS


class LunarEnvironment:
    """Pure model of the lunar day/night cycle."""

    def __init__(self, start_phase_hours: float = 0.0):
        """Place t=0 at a chosen point in the 708.7 h synodic cycle."""
        self.start_phase_hours = start_phase_hours

    def is_daylight(self, t_hours: float) -> bool:
        """True while the outpost is in sunlight. Strict < at the terminator."""
        phase = (t_hours + self.start_phase_hours) % LUNAR_CYCLE_HOURS
        return phase < LUNAR_DAY_HOURS

    def solar_irradiance_fraction(self, t_hours: float) -> float:
        """Peak-flux fraction in [0, 1]; square wave in v1."""
        return 1.0 if self.is_daylight(t_hours) else 0.0
