"""
Central scenario configuration for the lunar microgrid simulation.

Every other module should import constants from here rather than hardcoding
numbers, so a single file controls the whole scenario (and future scenarios
can be added as sibling config profiles, e.g. config_extended_night.py).
"""

from enum import IntEnum

# --- Time base -------------------------------------------------------------

TIME_STEP_HOURS: float = 1.0

LUNAR_DAY_HOURS: float = 14 * 24        # 336 h of continuous sunlight
LUNAR_NIGHT_HOURS: float = 14 * 24      # 336 h of total darkness
LUNAR_CYCLE_HOURS: float = LUNAR_DAY_HOURS + LUNAR_NIGHT_HOURS  # 672 h (~28 Earth days)

SIM_DURATION_DAYS: int = 56             # >= 2 full lunar cycles, per requirement
SIM_DURATION_HOURS: float = SIM_DURATION_DAYS * 24
N_STEPS: int = int(SIM_DURATION_HOURS / TIME_STEP_HOURS)

RANDOM_SEED: int = 42


# --- Battery ----------------------------------------------------------------

BATTERY_SOC_MIN: float = 0.05      # hard floor, fraction of capacity
BATTERY_SOC_MAX: float = 1.00
BATTERY_CHARGE_EFFICIENCY: float = 0.95
BATTERY_DISCHARGE_EFFICIENCY: float = 0.95

# Controller hysteresis thresholds (fractions of battery capacity)
SOC_SHED_THRESHOLD: float = 0.30       # start shedding below this
SOC_RESTORE_THRESHOLD: float = 0.45    # allow restoring above this
MIN_ACTION_DWELL_HOURS: float = 1.0    # minimum time between shed/restore on the same load


# --- Regenerative Fuel Cell (RFC) -------------------------------------------

H2_SPECIFIC_ENERGY_MJ_PER_KG: float = 120.0   # lower heating value, ~33.3 kWh/kg
ELECTROLYZER_EFFICIENCY: float = 0.70
FUEL_CELL_EFFICIENCY: float = 0.55


# --- Load priority tiers -----------------------------------------------------

class LoadPriority(IntEnum):
    """Lower number = higher priority = shed last, restored first."""
    CRITICAL = 0   # ECLSS life-support minimum — never shed
    HIGH = 1       # habitat thermal control minimum
    MEDIUM = 2     # communications array
    LOW = 3        # science payloads, drills, rovers
