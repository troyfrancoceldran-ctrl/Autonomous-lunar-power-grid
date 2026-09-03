"""
Concrete PowerStorage implementations: BatteryBank, RegenerativeFuelCell.

STATUS: Step 4 (BatteryBank) implemented and verified.
        Step 5 (RegenerativeFuelCell) not yet implemented. See PROGRESS.md.
"""

from assets.base_asset import PowerStorage
from config import (BATTERY_CAPACITY_WH
                    , BATTERY_INITIAL_SOC
                    , BATTERY_MAX_CHARGE_POWER_W
                    , BATTERY_MAX_DISCHARGE_POWER_W
                    , BATTERY_CHARGE_EFFICIENCY
                    , BATTERY_DISCHARGE_EFFICIENCY
                    , BATTERY_SOC_MIN
                    , BATTERY_SOC_MAX
                    )

# Battery Class
class BatteryBank(PowerStorage):
    def __init__(self, name = "Battery Bank"
                , capacity_wh = BATTERY_CAPACITY_WH
                , initial_soc = BATTERY_INITIAL_SOC
                , max_charge_power_w = BATTERY_MAX_CHARGE_POWER_W
                , max_discharge_power_w = BATTERY_MAX_DISCHARGE_POWER_W
                , charge_efficiency = BATTERY_CHARGE_EFFICIENCY
                , discharge_efficiency = BATTERY_DISCHARGE_EFFICIENCY
                , soc_min = BATTERY_SOC_MIN
                , soc_max = BATTERY_SOC_MAX):

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
        return self.energy_wh / self.capacity_wh
    
    def charge(self, power_w: float, dt_hours: float) -> float:
        if dt_hours <= 0 or power_w <= 0:
            return 0.0
        
        accepted_power_w = min(power_w, self.max_charge_power_w)
        energy_in_wh = accepted_power_w * dt_hours * self.charge_efficiency
        headroom_wh = self.soc_max * self.capacity_wh - self.energy_wh
        
        if energy_in_wh > headroom_wh:
            energy_in_wh = headroom_wh
            accepted_power_w = energy_in_wh / (dt_hours * self.charge_efficiency)

        self.energy_wh = self.energy_wh + energy_in_wh
        self._clamp_energy()
        return float(accepted_power_w)

    def discharge(self, power_w: float, dt_hours: float) -> float:
        if dt_hours <= 0 or power_w <= 0:
            return 0.0
        
        delivered_power_w = min(power_w, self.max_discharge_power_w)
        energy_out_wh = delivered_power_w * dt_hours / self.discharge_efficiency
        available_wh = self.energy_wh - self.soc_min * self.capacity_wh

        if energy_out_wh > available_wh:
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


# Fuel Cell Class
class RegenerativeFuelCell(PowerStorage):
    def __init__(self):
        return
    
    def state_of_charge(self) -> float:
        return
    