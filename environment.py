"""
LunarEnvironment — models the lunar day/night cycle and solar availability
over simulated time.

STATUS: Step 2 — implemented and verified. See PROGRESS.md.

Contract:
    - class LunarEnvironment
    - method: is_daylight(t_hours: float) -> bool
        True when t_hours falls in a lunar-day window, given
        config.LUNAR_DAY_HOURS / config.LUNAR_NIGHT_HOURS / config.LUNAR_CYCLE_HOURS.
        Must be correct across multiple cycles (use modulo on t_hours).
    - method: solar_irradiance_fraction(t_hours: float) -> float
        Returns a value in [0, 1]: 0.0 at night, and for now a flat 1.0
        during the day is an acceptable first pass (a sun-angle-based
        ramp up/down near terminator crossings is a reasonable v2 refinement,
        not required for v1).
    - Should be a pure function of t_hours plus config constants — no
        hidden mutable state, so PVArray.available_power() can call it freely
        at any t without needing to "step" the environment forward.
"""
from config import LUNAR_CYCLE_HOURS
from config import LUNAR_DAY_HOURS

class LunarEnvironment: 
    def __init__(self, start_phase_hours: float = 0.0):
        self.start_phase_hours = start_phase_hours
    
    def is_daylight(self, t_hours: float) -> bool:
        phase = (t_hours + self.start_phase_hours) % LUNAR_CYCLE_HOURS
        return phase < LUNAR_DAY_HOURS
    
    def solar_irradiance_fraction(self, t_hours: float) -> float:
        return 1.0 if self.is_daylight(t_hours) else 0.0
            
    