"""
Central scenario configuration for the lunar microgrid simulation.

Every other module should import constants from here rather than hardcoding
numbers, so a single file controls the whole scenario (and future scenarios
can be added as sibling config profiles, e.g. config_extended_night.py).
"""

from enum import IntEnum

# --- Time base -------------------------------------------------------------

TIME_STEP_HOURS: float = 1.0

# The Moon is tidally locked, so its ROTATION period is 27.3 d — but a point on
# the surface returns to the same position relative to the SUN only after the
# synodic period of 29.53 d = 708.7 h. That is the figure a power system must
# survive, and it is what NASA's Fission Surface Power requirement refers to
# when it calls for "at least 354 hr of nighttime energy storage".
# The common "14 Earth days = 336 h" shorthand understates the night by 5.1%.
LUNAR_SYNODIC_PERIOD_HOURS: float = 708.7

LUNAR_DAY_HOURS: float = LUNAR_SYNODIC_PERIOD_HOURS / 2.0     # 354.35 h of sunlight
LUNAR_NIGHT_HOURS: float = LUNAR_SYNODIC_PERIOD_HOURS / 2.0   # 354.35 h of darkness
LUNAR_CYCLE_HOURS: float = LUNAR_DAY_HOURS + LUNAR_NIGHT_HOURS

# >= 2 full synodic cycles (1417.4 h) so the run captures a complete
# charge/discharge round trip twice over, not 1.9 of one.
SIM_DURATION_DAYS: int = 60
SIM_DURATION_HOURS: float = SIM_DURATION_DAYS * 24
N_STEPS: int = int(SIM_DURATION_HOURS / TIME_STEP_HOURS)

RANDOM_SEED: int = 42


# --- Generation -------------------------------------------------------------

# Solar constant at 1 AU. The Moon has no atmosphere, so unlike Earth's surface
# (~1000 W/m^2 at best) the full extraterrestrial value reaches the panels.
SOLAR_CONSTANT_W_PER_M2: float = 1361.0

PV_AREA_M2: float = 100.0          # PROVISIONAL — revisit once Step 6 fixes real loads
PV_EFFICIENCY: float = 0.30        # triple-junction space-grade cells
PV_PACKING_FACTOR: float = 0.90    # cell-to-array area loss, wiring, mismatch, pointing

# Lunar regolith dust is electrostatically charged, clingy and abrasive; NASA
# measurements show short-circuit current falling exponentially with deposited
# dust mass, and every landing nearby adds more. A fixed derate is a crude
# stand-in for a mechanism that really worsens over mission life.
PV_DUST_DERATE: float = 0.95

# Sun-elevation profile. A fixed horizontal array at an equatorial site sees
# irradiance vary as sin(pi * phase / day), averaging 2/pi = 0.637 of peak; a
# two-axis tracker or a NASA-style Vertical Solar Array holds close to peak all
# day. Assuming the wrong one overstates daily energy by 36%.
PV_SUN_TRACKING: bool = False      # False = fixed array, sinusoidal profile

# Fission Surface Power — NASA Kilopower/FSP class, runs through the night.
# NASA's FSP requirement set: 40 kWe class (10 kWe demonstrator), >= 10 year
# design life, autonomous start/stop without human assistance.
FSP_RATED_POWER_W: float = 10_000.0
FSP_AVAILABILITY: float = 1.0      # long-run availability; 1.0 = idealised

# A scripted outage, so contingency behaviour is reproducible rather than
# stochastic. Set FSP_OUTAGE_START_HOURS to None to disable.
FSP_OUTAGE_START_HOURS: float | None = None
FSP_OUTAGE_DURATION_HOURS: float = 24.0


# --- Battery ----------------------------------------------------------------

BATTERY_CAPACITY_WH: float = 200_000.0      # 200 kWh usable-nameplate energy
BATTERY_INITIAL_SOC: float = 1.00           # starts full at t=0 (lunar dawn)

BATTERY_MAX_CHARGE_POWER_W: float = 50_000.0     # C-rate ceiling, bus side
BATTERY_MAX_DISCHARGE_POWER_W: float = 50_000.0

# 95% depth of discharge would be reckless in LEO, where practice keeps DoD
# below 30% because the spacecraft sees ~5000 cycles a year. A lunar surface
# system sees ONE cycle per synodic period — about 124 in a 10-year life — so
# deep discharge is affordable here. The justification is cycle count, not
# optimism: change the mission profile and this number must change with it.
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

# Pre-converted so no module has to do MJ -> Wh arithmetic inline.
H2_SPECIFIC_ENERGY_WH_PER_KG: float = H2_SPECIFIC_ENERGY_MJ_PER_KG * 1e6 / 3600.0

# Stoichiometry of 2 H2 + O2 -> 2 H2O: 4 g of H2 pairs with 32 g of O2.
O2_TO_H2_MASS_RATIO: float = 8.0

RFC_H2_CAPACITY_KG: float = 120.0           # ~2200 kWh deliverable after fuel-cell losses
RFC_INITIAL_SOC: float = 1.00               # tanks start full at t=0

RFC_MAX_CHARGE_POWER_W: float = 25_000.0    # electrolyzer rated electrical input
RFC_MAX_DISCHARGE_POWER_W: float = 12_000.0 # fuel cell rated electrical output

RFC_SOC_MIN: float = 0.05
RFC_SOC_MAX: float = 1.00


# --- Load profiles -----------------------------------------------------------

# Life support: atmosphere circulation, CO2 scrubbing, water recovery.
# Runs flat, around the clock, and is never shed.
ECLSS_POWER_W: float = 6500.0

# Habitat thermal control. The lunar surface swings from about +120 C in
# daylight to -170 C at night, so the load never goes away — it only changes
# job, from rejecting heat to adding it.
THERMAL_DAY_POWER_W: float = 5500.0
THERMAL_NIGHT_POWER_W: float = 4500.0

# High-gain Earth link: one transmit window per Earth day, standby between.
COMMS_ACTIVE_POWER_W: float = 2500.0
COMMS_STANDBY_POWER_W: float = 500.0
COMMS_WINDOW_HOURS: float = 8.0
COMMS_PERIOD_HOURS: float = 24.0

# Science campaigns: drills, rovers, instruments. Fully interruptible.
SCIENCE_ACTIVE_POWER_W: float = 6000.0
SCIENCE_IDLE_POWER_W: float = 0.0
SCIENCE_WINDOW_HOURS: float = 12.0
SCIENCE_PERIOD_HOURS: float = 24.0


# --- Load priority tiers -----------------------------------------------------

class LoadPriority(IntEnum):
    """Lower number = higher priority = shed last, restored first."""
    CRITICAL = 0   # ECLSS life-support minimum — never shed
    HIGH = 1       # habitat thermal control minimum
    MEDIUM = 2     # communications array
    LOW = 3        # science payloads, drills, rovers
