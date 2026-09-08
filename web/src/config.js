// GENERATED FILE — do not edit.
//
// Produced by web/tools/export_config.py from config.py, so the browser model
// and the Python model cannot disagree about a constant. Change config.py and
// re-run the generator.
//
// Every comment below is carried across from the Python source, because a
// number without its justification is how a model quietly drifts away from the
// literature it claims to follow.


// --- Time base -------------------------------------------------------------
export const TIME_STEP_HOURS = 1.0;

// The Moon is tidally locked, so its ROTATION period is 27.3 d — but a point on
// the surface returns to the same position relative to the SUN only after the
// synodic period of 29.53 d = 708.7 h. That is the figure a power system must
// survive, and it is what NASA's Fission Surface Power requirement refers to
// when it calls for "at least 354 hr of nighttime energy storage".
// The common "14 Earth days = 336 h" shorthand understates the night by 5.1%.
export const LUNAR_SYNODIC_PERIOD_HOURS = 708.7;

export const LUNAR_DAY_HOURS = 354.35;

export const LUNAR_NIGHT_HOURS = 354.35;

export const LUNAR_CYCLE_HOURS = 708.7;

// >= 2 full synodic cycles (1417.4 h) so the run captures a complete
// charge/discharge round trip twice over, not 1.9 of one.
export const SIM_DURATION_DAYS = 60;

export const SIM_DURATION_HOURS = 1440;

export const N_STEPS = 1440;

export const RANDOM_SEED = 42;

// --- Generation -------------------------------------------------------------
// Solar constant at 1 AU. The Moon has no atmosphere, so unlike Earth's surface
// (~1000 W/m^2 at best) the full extraterrestrial value reaches the panels.
export const SOLAR_CONSTANT_W_PER_M2 = 1361.0;

export const PV_AREA_M2 = 100.0;

export const PV_EFFICIENCY = 0.3;

export const PV_PACKING_FACTOR = 0.9;

// Lunar regolith dust is electrostatically charged, clingy and abrasive; NASA
// measurements show short-circuit current falling exponentially with deposited
// dust mass, and every landing nearby adds more. A fixed derate is a crude
// stand-in for a mechanism that really worsens over mission life.
export const PV_DUST_DERATE = 0.95;

// Sun-elevation profile. A fixed horizontal array at an equatorial site sees
// irradiance vary as sin(pi * phase / day), averaging 2/pi = 0.637 of peak; a
// two-axis tracker or a NASA-style Vertical Solar Array holds close to peak all
// day. Assuming the wrong one overstates daily energy by 36%.
export const PV_SUN_TRACKING = false;

// Fission Surface Power — NASA Kilopower/FSP class, runs through the night.
// NASA's FSP requirement set: 40 kWe class (10 kWe demonstrator), >= 10 year
// design life, autonomous start/stop without human assistance.
export const FSP_RATED_POWER_W = 10000.0;

export const FSP_AVAILABILITY = 1.0;

// A scripted outage, so contingency behaviour is reproducible rather than
// stochastic. Set FSP_OUTAGE_START_HOURS to None to disable.
export const FSP_OUTAGE_START_HOURS = null;

export const FSP_OUTAGE_DURATION_HOURS = 24.0;

// --- Battery ----------------------------------------------------------------
export const BATTERY_CAPACITY_WH = 200000.0;

export const BATTERY_INITIAL_SOC = 1.0;

export const BATTERY_MAX_CHARGE_POWER_W = 50000.0;

export const BATTERY_MAX_DISCHARGE_POWER_W = 50000.0;

// 95% depth of discharge would be reckless in LEO, where practice keeps DoD
// below 30% because the spacecraft sees ~5000 cycles a year. A lunar surface
// system sees ONE cycle per synodic period — about 124 in a 10-year life — so
// deep discharge is affordable here. The justification is cycle count, not
// optimism: change the mission profile and this number must change with it.
export const BATTERY_SOC_MIN = 0.05;

export const BATTERY_SOC_MAX = 1.0;

export const BATTERY_CHARGE_EFFICIENCY = 0.95;

export const BATTERY_DISCHARGE_EFFICIENCY = 0.95;

// Controller thresholds, as fractions of the CAPACITY-WEIGHTED FLEET reserve
// (see power_bus.aggregate_soc), not of any one device.
export const SOC_SHED_THRESHOLD = 0.3;

export const SOC_RESTORE_THRESHOLD = 0.45;

// Minimum interval between two actions on the SAME load. This must be strictly
// GREATER than TIME_STEP_HOURS or the guard is vacuous: it tests
// `t - last >= min_dwell`, so at 1.0 h with a 1.0 h tick a load acted on at t
// is free again at t+1. It sat at 1.0 from Step 7 and went unnoticed until
// W04 added a branch that bypasses hysteresis and left dwell as the only brake.
export const MIN_ACTION_DWELL_HOURS = 3.0;

// --- Regenerative Fuel Cell (RFC) -------------------------------------------
export const H2_SPECIFIC_ENERGY_MJ_PER_KG = 120.0;

export const ELECTROLYZER_EFFICIENCY = 0.7;

export const FUEL_CELL_EFFICIENCY = 0.55;

// Pre-converted so no module has to do MJ -> Wh arithmetic inline.
export const H2_SPECIFIC_ENERGY_WH_PER_KG = 33333.333333333336;

// Stoichiometry of 2 H2 + O2 -> 2 H2O: 4 g of H2 pairs with 32 g of O2.
export const O2_TO_H2_MASS_RATIO = 8.0;

export const RFC_H2_CAPACITY_KG = 120.0;

export const RFC_INITIAL_SOC = 1.0;

export const RFC_MAX_CHARGE_POWER_W = 25000.0;

export const RFC_MAX_DISCHARGE_POWER_W = 12000.0;

export const RFC_SOC_MIN = 0.05;

export const RFC_SOC_MAX = 1.0;

// --- Load profiles -----------------------------------------------------------
// Life support: atmosphere circulation, CO2 scrubbing, water recovery.
// Runs flat, around the clock, and is never shed.
export const ECLSS_POWER_W = 6500.0;

// Habitat thermal control. The lunar surface swings from about +120 C in
// daylight to -170 C at night, so the load never goes away — it only changes
// job, from rejecting heat to adding it.
export const THERMAL_DAY_POWER_W = 5500.0;

export const THERMAL_NIGHT_POWER_W = 4500.0;

// High-gain Earth link: one transmit window per Earth day, standby between.
export const COMMS_ACTIVE_POWER_W = 2500.0;

export const COMMS_STANDBY_POWER_W = 500.0;

export const COMMS_WINDOW_HOURS = 8.0;

export const COMMS_PERIOD_HOURS = 24.0;

// Science campaigns: drills, rovers, instruments. Fully interruptible.
export const SCIENCE_ACTIVE_POWER_W = 6000.0;

export const SCIENCE_IDLE_POWER_W = 0.0;

export const SCIENCE_WINDOW_HOURS = 12.0;

export const SCIENCE_PERIOD_HOURS = 24.0;

// --- Electrical topology -----------------------------------------------------
// Added 2026-09-07 for the topology work (T01-T04). Everything above this line
// is a POWER BALANCE: watts in, watts out, no voltage anywhere. These constants
// are what turn it into something buildable.
// NASA's International Space Power System Interoperability Standard (ISPSIS)
// fixes the user bus at 120 VDC with 28 VDC for small loads. NASA's MIPS
// project states the constraint without hedging: "Power exchange must occur at
// 120 VDC (requirement) and a distance less than 100 m (limitation of 120 VDC)."
// That 100 m is not a style preference — it is the distance at which 120 V
// stops being able to move useful power without absurd conductor mass.
export const USER_BUS_VOLTAGE_V = 120.0;

export const AUX_BUS_VOLTAGE_V = 28.0;

export const USER_BUS_MAX_SPAN_M = 100.0;

// The reactor is the ONE asset that cannot sit on the user bus, and the reason
// is nuclear, not electrical: NASA FSP requires >= 1 km separation from other
// elements. At 3 km the reactor is over the 2.4 km lunar horizon from the crew.
// PV needs no such separation, which is why only the reactor gets a
// transmission link — "photovoltaic panels do not need extensive separation
// from the habitat, DC can be used for local power transfer."
export const FSP_SEPARATION_M = 1000.0;

// The ceiling on transmission voltage is SEMICONDUCTORS, not insulation.
// Fully space-qualified silicon devices are limited to 160 V, so a 1 kV bus
// needs six stacked 175 V bridges; radiation-hardening constraints cap
// practical DC transmission around 1.5 kV. GaN at 650 V is coming but single
// event effects are expected to limit its operating voltage.
export const QUALIFIED_SWITCH_VOLTAGE_V = 160.0;

export const MAX_RAD_HARD_DC_V = 1500.0;

// Aluminium, not copper. Al has 63 % of copper's conductivity at 30 % of its
// density, so about 2.1x the conductance per kilogram. On the Moon mass is the
// only currency that matters, and NASA's transmission study assumes aluminium
// conductor throughout.
export const CONDUCTOR_RESISTIVITY_OHM_M = 2.65e-08;

export const CONDUCTOR_DENSITY_KG_PER_M3 = 2700.0;

// Published values for aluminium scatter over 0.0039-0.0043 /K depending on
// alloy and reference temperature. The spread matters here: see the note on
// cable temperature in topology.py.
export const CONDUCTOR_TEMP_COEFF_PER_K = 0.004;

// A cable lying on the regolith has no convection and no atmosphere. NASA
// quotes surface cable temperatures reaching 400 K in sunlight; the lunar
// night bottoms out near 100 K. Both are far outside the range where a linear
// temperature coefficient is honest — see the declared simplification.
export const CABLE_TEMP_DAY_K = 400.0;

export const CABLE_TEMP_NIGHT_K = 100.0;

export const CABLE_TEMP_REFERENCE_K = 293.15;

// NASA's transmission study constrains cable loss to 5 % at 3 km for a 40 kW
// system. Voltage drop is held to the same figure here: below ~5 % the loads
// and converters stop caring, above it they start misbehaving.
export const MAX_FEEDER_LOSS_FRACTION = 0.05;

export const MAX_FEEDER_VOLTAGE_DROP_FRACTION = 0.05;

// A minimum gauge is a HANDLING limit, not an electrical one: thinner wire
// survives neither deployment nor thermal cycling. NASA's study holds
// conductors larger than 16 AWG (1.31 mm^2).
export const MIN_CONDUCTOR_AREA_M2 = 1.31e-06;

// Converter efficiency is NOT the same thing as device efficiency. The battery
// already has a round-trip number for its electrochemistry; this is the power
// electronics between it and the bus, and it applies to every asset including
// the ones that currently have no losses at all. NASA's UMIC rack targets
// > 95 % at 10 kW.
export const CONVERTER_EFFICIENCY = 0.95;

// PROVISIONAL — the reactor link's transmission voltage. This is a T01
// DECISION, not a given: it should fall out of the mass-versus-voltage trade
// (conductor mass ~ 1/V^2, insulation mass ~ V) clamped by MAX_RAD_HARD_DC_V
// and by how many 160 V devices you are willing to stack. 1000 V is a
// placeholder that keeps the topology constructible until that work is done.
export const TRANSMISSION_VOLTAGE_V = 1000.0;

// --- Protection (T04) --------------------------------------------------------
// DC has no natural current zero, so a mechanical breaker has nothing to help
// it extinguish the arc. Spacecraft practice is the Solid State Power
// Controller (SSPC) — the ISS distributes through RPCMs, and NASA's AMPS
// switchgear module is the modern equivalent at 0.5 kg against the ISS RPCM's
// 4.7 kg. An SSPC forces the current to zero by switching, in microseconds.
// A typical SSPC protection curve has three regions: a no-trip region below
// the rating, an I^2t region for overload, and an instantaneous region for
// short circuits. Instantaneous thresholds run up to about 10x rated current.
export const SSPC_INSTANTANEOUS_TRIP_MULTIPLE = 10.0;

// Solid-state switching acts in microseconds, which is what makes it viable
// where a mechanical contact would weld shut.
export const SSPC_MIN_TRIP_TIME_S = 5e-05;

// Let-through energy the device and its cable can absorb before damage. An
// SSPC protects on ENERGY, not merely on current — a breaker trips when the
// current reaches a threshold, an SSPC when enough has passed through.
export const SSPC_I2T_RATING_A2S = 2000.0;

// Selectivity margin: a downstream device must clear this much sooner than the
// one above it, or a feeder fault takes out the whole bus. NASA calls the goal
// "zonal protection" — the breaker nearest the fault trips and nothing else.
export const PROTECTION_COORDINATION_MARGIN_S = 0.0001;

// Lower number = higher priority = shed last, restored first.
export const LoadPriority = Object.freeze({
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
});
