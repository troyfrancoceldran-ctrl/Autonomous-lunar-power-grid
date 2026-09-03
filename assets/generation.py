"""
Concrete PowerSource implementations: PVArray, FissionSurfacePower.

STATUS: Step 3 — implemented and verified. See PROGRESS.md.
Depends on: environment.py (Step 2).
"""
from assets.base_asset import PowerSource
from config import (SOLAR_CONSTANT_W_PER_M2, PV_AREA_M2, PV_EFFICIENCY, PV_PACKING_FACTOR, FSP_AVAILABILITY, FSP_RATED_POWER_W)

class PVArray(PowerSource):
    def __init__(self, name="PV Array", area_m2 = PV_AREA_M2, efficiency = PV_EFFICIENCY, packing_factor = PV_PACKING_FACTOR):
        self.name = name
        self.area_m2 = area_m2
        self.efficiency = efficiency
        self.packing_factor = packing_factor
    
    def available_power(self, t_hours: float, environment) -> float:
        irradiance = environment.solar_irradiance_fraction(t_hours)
        return (SOLAR_CONSTANT_W_PER_M2 
                * self.area_m2
                * self.efficiency
                * self.packing_factor
                * irradiance)
class FissionSurfacePower(PowerSource):
    def __init__(self, name="FSP Reactor", rated_power_w = FSP_RATED_POWER_W, availability = FSP_AVAILABILITY):
        self.name = name
        self.rated_power_w = rated_power_w
        self.availability = availability
    
    def available_power(self, t_hours: float, environment) -> float:
        return self.rated_power_w * self.availability