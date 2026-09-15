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

# COULOMBIC efficiency is NOT the energy efficiency above, and conflating the
# two is a modelling error rather than a rounding one. The 0.95 pair counts
# WATT-HOURS: it carries the ohmic and conversion losses, most of which leave
# as heat across the internal resistance. Coulombic efficiency counts CHARGE —
# amp-hours in against amp-hours out — and for lithium-ion that is essentially
# unity, commonly quoted above 99 % and above 99.9 % for a well-behaved cell,
# because the electrons that go in come back out; what is lost is the VOLTAGE
# they come back at, not their number.
#
# The estimator counts charge, the plant keeps its books in energy, and the
# two must agree about how the state moves or B04 measures my bookkeeping
# instead of the filter. Declared as exactly 1.0: a simplification, stated,
# rather than a borrowed number that happens to be wrong by 5 %.
BATTERY_COULOMBIC_EFFICIENCY: float = 1.0

# Controller thresholds, as fractions of the CAPACITY-WEIGHTED FLEET reserve
# (see power_bus.aggregate_soc), not of any one device.
SOC_SHED_THRESHOLD: float = 0.30       # start shedding below this
SOC_RESTORE_THRESHOLD: float = 0.45    # allow restoring above this

# Minimum interval between two actions on the SAME load. This must be strictly
# GREATER than TIME_STEP_HOURS or the guard is vacuous: it tests
# `t - last >= min_dwell`, so at 1.0 h with a 1.0 h tick a load acted on at t
# is free again at t+1. It sat at 1.0 from Step 7 and went unnoticed until
# W04 added a branch that bypasses hysteresis and left dwell as the only brake.
MIN_ACTION_DWELL_HOURS: float = 3.0


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


# --- Electrical topology -----------------------------------------------------
# Added 2026-09-07 for the topology work (T01-T04). Everything above this line
# is a POWER BALANCE: watts in, watts out, no voltage anywhere. These constants
# are what turn it into something buildable.

# NASA's International Space Power System Interoperability Standard (ISPSIS)
# fixes the user bus at 120 VDC with 28 VDC for small loads. NASA's MIPS
# project states the constraint without hedging: "Power exchange must occur at
# 120 VDC (requirement) and a distance less than 100 m (limitation of 120 VDC)."
# That 100 m is not a style preference — it is the distance at which 120 V
# stops being able to move useful power without absurd conductor mass.
USER_BUS_VOLTAGE_V: float = 120.0
AUX_BUS_VOLTAGE_V: float = 28.0
USER_BUS_MAX_SPAN_M: float = 100.0

# The reactor is the ONE asset that cannot sit on the user bus, and the reason
# is nuclear, not electrical: NASA FSP requires >= 1 km separation from other
# elements. At 3 km the reactor is over the 2.4 km lunar horizon from the crew.
# PV needs no such separation, which is why only the reactor gets a
# transmission link — "photovoltaic panels do not need extensive separation
# from the habitat, DC can be used for local power transfer."
FSP_SEPARATION_M: float = 1000.0

# The ceiling on transmission voltage is SEMICONDUCTORS, not insulation.
# Fully space-qualified silicon devices are limited to 160 V, so a 1 kV bus
# needs six stacked 175 V bridges; radiation-hardening constraints cap
# practical DC transmission around 1.5 kV. GaN at 650 V is coming but single
# event effects are expected to limit its operating voltage.
QUALIFIED_SWITCH_VOLTAGE_V: float = 160.0
MAX_RAD_HARD_DC_V: float = 1500.0

# Aluminium, not copper. Al has 63 % of copper's conductivity at 30 % of its
# density, so about 2.1x the conductance per kilogram. On the Moon mass is the
# only currency that matters, and NASA's transmission study assumes aluminium
# conductor throughout.
CONDUCTOR_RESISTIVITY_OHM_M: float = 2.65e-8    # aluminium at 20 C
CONDUCTOR_DENSITY_KG_PER_M3: float = 2700.0
# Published values for aluminium scatter over 0.0039-0.0043 /K depending on
# alloy and reference temperature. The spread matters here: see the note on
# cable temperature in topology.py.
CONDUCTOR_TEMP_COEFF_PER_K: float = 0.0040

# A cable lying on the regolith has no convection and no atmosphere. NASA
# quotes surface cable temperatures reaching 400 K in sunlight; the lunar
# night bottoms out near 100 K. Both are far outside the range where a linear
# temperature coefficient is honest — see the declared simplification.
CABLE_TEMP_DAY_K: float = 400.0
CABLE_TEMP_NIGHT_K: float = 100.0
CABLE_TEMP_REFERENCE_K: float = 293.15

# NASA's transmission study constrains cable loss to 5 % at 3 km for a 40 kW
# system. Voltage drop is held to the same figure here: below ~5 % the loads
# and converters stop caring, above it they start misbehaving.
MAX_FEEDER_LOSS_FRACTION: float = 0.05
MAX_FEEDER_VOLTAGE_DROP_FRACTION: float = 0.05

# A minimum gauge is a HANDLING limit, not an electrical one: thinner wire
# survives neither deployment nor thermal cycling. NASA's study holds
# conductors larger than 16 AWG (1.31 mm^2).
MIN_CONDUCTOR_AREA_M2: float = 1.31e-6

# Converter efficiency is NOT the same thing as device efficiency. The battery
# already has a round-trip number for its electrochemistry; this is the power
# electronics between it and the bus, and it applies to every asset including
# the ones that currently have no losses at all. NASA's UMIC rack targets
# > 95 % at 10 kW.
CONVERTER_EFFICIENCY: float = 0.95

# PROVISIONAL — the reactor link's transmission voltage. This is a T01
# DECISION, not a given: it should fall out of the mass-versus-voltage trade
# (conductor mass ~ 1/V^2, insulation mass ~ V) clamped by MAX_RAD_HARD_DC_V
# and by how many 160 V devices you are willing to stack. 1000 V is a
# placeholder that keeps the topology constructible until that work is done.
TRANSMISSION_VOLTAGE_V: float = 1000.0


# --- Protection (T04) --------------------------------------------------------
# DC has no natural current zero, so a mechanical breaker has nothing to help
# it extinguish the arc. Spacecraft practice is the Solid State Power
# Controller (SSPC) — the ISS distributes through RPCMs, and NASA's AMPS
# switchgear module is the modern equivalent at 0.5 kg against the ISS RPCM's
# 4.7 kg. An SSPC forces the current to zero by switching, in microseconds.

# A typical SSPC protection curve has three regions: a no-trip region below
# the rating, an I^2t region for overload, and an instantaneous region for
# short circuits. Instantaneous thresholds run up to about 10x rated current.
SSPC_INSTANTANEOUS_TRIP_MULTIPLE: float = 10.0

# Solid-state switching acts in microseconds, which is what makes it viable
# where a mechanical contact would weld shut.
SSPC_MIN_TRIP_TIME_S: float = 50e-6

# Let-through energy the device and its cable can absorb before damage. An
# SSPC protects on ENERGY, not merely on current — a breaker trips when the
# current reaches a threshold, an SSPC when enough has passed through.
SSPC_I2T_RATING_A2S: float = 2000.0

# Selectivity margin: a downstream device must clear this much sooner than the
# one above it, or a feeder fault takes out the whole bus. NASA calls the goal
# "zonal protection" — the breaker nearest the fault trips and nothing else.
PROTECTION_COORDINATION_MARGIN_S: float = 1e-4


# --- Battery terminals and instruments (B01) ---------------------------------
# Everything above describes what the battery STORES. This section describes
# what it EXPOSES — a voltage a meter could read — so that state of charge
# becomes something to infer rather than something to look up.
#
# NOTE ON THE UNASSIGNED NAMES BELOW. Several constants here are declared with
# a type and no value. That is deliberate: a bare annotation binds no module
# attribute, so `from config import X` raises ImportError until you assign one.
# A placeholder number would import cleanly and be silently wrong, which is the
# worse failure by a distance.

# Open-circuit voltage, per CELL, as a degree-7 least-squares fit of a standard
# NMC/NCA discharge curve. Coefficients are in the mapped variable
#     x = 2 * soc - 1
# so the fit is conditioned on [-1, 1] rather than [0, 1]. ASCENDING order:
# OCV(x) = c[0] + c[1]x + c[2]x^2 + ... — evaluate with Horner, reversed.
#
# Max fit error 6.3 mV per cell, and VERIFIED MONOTONIC on [0.05, 1.0], which
# is the property the whole estimator rests on: where dOCV/dz <= 0, one voltage
# means two charges and state of charge stops being observable at all.
#
# The same fit against an LFP curve FOLDS BACK at every degree from 5 to 9
# (dOCV/dz goes negative around z = 0.16-0.38), so the LFP comparison in B04
# needs a lookup table or a piecewise fit, not this form. Write
# open_circuit_voltage_v so the curve can be swapped without touching the
# method body.
OCV_POLY_NMC: tuple = (
    +3.736277252,   # x^0
    +0.282556708,   # x^1
    +0.022414644,   # x^2
    +0.393657303,   # x^3
    +0.331825038,   # x^4
    -0.860396242,   # x^5
    -0.490196078,   # x^6
    +0.784167834,   # x^7
)

# Cells in series. Sets pack voltage: CELLS_SERIES * OCV(soc). The pack has to
# sit sensibly against USER_BUS_VOLTAGE_V = 120 V — a 32S NMC pack runs about
# 96 V empty, 118 V nominal and 134 V full, which is why T03's converters exist.
CELLS_SERIES: int = 32

# Pack ohmic resistance. DO NOT PICK THIS INDEPENDENTLY — it is already in this
# file wearing different clothes. storage.py spends `delivered / eta` on
# discharge, so eta is delivered over spent, which at the terminals is exactly
#     eta = V / OCV = 1 - I*R/OCV      =>      R = OCV * (1 - eta) / I_rated
# Evaluate at the rated operating point: pack OCV at 50 % SoC, and the rated
# current BATTERY_MAX_DISCHARGE_POWER_W / USER_BUS_VOLTAGE_V.
#
# Cross-check the answer before trusting it: I^2 R should come out at about
# 5 % of 50 kW, because that is the same loss BATTERY_DISCHARGE_EFFICIENCY
# already claims. If it does not, one of the two is wrong.
#
# The gain from having both: eta is fixed, R is fixed, but I is not — so
# efficiency becomes current-dependent, as a real pack's is. The flat 0.95 was
# only ever correct at full load, and the battery spends most of the night
# nowhere near it.
BATTERY_R_INTERNAL_OHM: float = 0.0143

# --- the instruments, which are not the pack --------------------------------
# An estimator earns its place by fusing two flawed measurements. Model the
# flaws or there is nothing to fuse: with perfect sensors the terminal equation
# inverts algebraically and no filter is needed.

# Current-channel noise, 1 sigma, per sample. Zero-mean, so it averages out and
# costs the coulomb count nothing in the long run.
CURRENT_SENSOR_NOISE_A: float = 0.5

# Current-channel BIAS — a FIXED offset, not a random draw. This is the term
# that matters: it integrates straight into a coulomb count and never washes
# out, so the error grows without bound and has no restoring force. Correcting
# it is the entire reason the filter exists.
#
# Keep it deterministic rather than drawn at construction. This project
# reproduces exactly (see RANDOM_SEED), a per-instance random bias would make
# every run's battery subtly different, and B04 wants to SWEEP this value
# deliberately — which you cannot do to something you randomised.
CURRENT_SENSOR_BIAS_A: float = 2.0

# Voltage-channel noise, 1 sigma, per sample. Blunt but UNBIASED, which is what
# lets it anchor the drift above. Its cost in state of charge is this divided
# by the OCV slope — so the same voltmeter is worth eleven times more on NMC
# than on LFP.
VOLTAGE_SENSOR_NOISE_V: float = 0.0068
