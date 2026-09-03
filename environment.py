"""
@file    environment.py
@brief   Lunar day/night cycle and solar availability over simulated time.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-03

@details
The outpost sits through a 672 h lunar cycle: 336 h of continuous sunlight
followed by 336 h of total darkness. This module answers one question —
"how much sun is there at time t?" — and nothing else.

It is deliberately STATELESS beyond a single constructor argument, so
PVArray.available_power() can query any t, in any order, without the
environment having to be "stepped" forward in lockstep with the engine.

@note This class is the seam where the simulation meets reality. On real
      hardware it is replaced by an irradiance sensor reading; every
      downstream consumer keeps working unchanged.
"""
from config import LUNAR_CYCLE_HOURS
from config import LUNAR_DAY_HOURS


class LunarEnvironment:
    """
    @brief Pure model of the lunar day/night cycle.

    @var start_phase_hours  Offset [h] placing t=0 somewhere in the cycle.
    """

    def __init__(self, start_phase_hours: float = 0.0):
        """
        @brief Construct an environment with a chosen starting phase.

        @param start_phase_hours  Where t=0 sits within the 672 h cycle [h].
                                  0.0 starts at lunar dawn; 336.0 starts at
                                  nightfall, which is the stress scenario for
                                  testing storage sizing.
        """
        self.start_phase_hours = start_phase_hours

    def is_daylight(self, t_hours: float) -> bool:
        """
        @brief Whether the outpost is in sunlight at time t.

        @param t_hours  Simulation time [h] since t=0.
        @return True during the lunar day, False during the night.

        @note The modulo folds absolute time into one cycle, so this stays
              correct across the full 56-day run and beyond. The comparison
              is STRICT: phase 336.0 is the first hour of night, not the last
              hour of day. With a 1 h timestep the simulation lands exactly
              on that boundary once per cycle, so the operator matters.
        """
        phase = (t_hours + self.start_phase_hours) % LUNAR_CYCLE_HOURS
        return phase < LUNAR_DAY_HOURS

    def solar_irradiance_fraction(self, t_hours: float) -> float:
        """
        @brief Fraction of peak solar flux available at time t.

        @param t_hours  Simulation time [h] since t=0.
        @return 1.0 in daylight, 0.0 at night. Always within [0, 1].

        @note Delegates to is_daylight() rather than repeating the modulo, so
              the two can never disagree about where the terminator falls.
        @note v1 is a square wave. A sun-angle-based ramp near the terminator
              is a reasonable v2 refinement; only this method would change.
        """
        return 1.0 if self.is_daylight(t_hours) else 0.0
