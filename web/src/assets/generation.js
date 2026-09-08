// generation.js — PVArray and FissionSurfacePower. Port of assets/generation.py.
import {
  SOLAR_CONSTANT_W_PER_M2, PV_AREA_M2, PV_EFFICIENCY, PV_PACKING_FACTOR,
  PV_DUST_DERATE, PV_SUN_TRACKING, FSP_RATED_POWER_W, FSP_AVAILABILITY,
  FSP_OUTAGE_START_HOURS, FSP_OUTAGE_DURATION_HOURS,
} from "../config.js";

export class PVArray {
  constructor({
    name = "PV Array", areaM2 = PV_AREA_M2, efficiency = PV_EFFICIENCY,
    packingFactor = PV_PACKING_FACTOR, dustDerate = PV_DUST_DERATE,
    sunTracking = PV_SUN_TRACKING,
  } = {}) {
    Object.assign(this, { name, areaM2, efficiency, packingFactor, dustDerate, sunTracking });
  }

  /** P = G_sc * A * eta * f * d * phi(t), in watts. */
  availablePower(tHours, environment) {
    // The flag SELECTS the profile; it never scales it. Used as a multiplier
    // this once made the array produce 0 W at noon.
    const phi = this.sunTracking
      ? environment.solarIrradianceFraction(tHours)
      : environment.solarElevationFraction(tHours);
    return SOLAR_CONSTANT_W_PER_M2 * this.areaM2 * this.efficiency
         * this.packingFactor * this.dustDerate * phi;
  }
}

export class FissionSurfacePower {
  constructor({
    name = "FSP Reactor", ratedPowerW = FSP_RATED_POWER_W,
    availability = FSP_AVAILABILITY, outageStartHours = FSP_OUTAGE_START_HOURS,
    outageDurationHours = FSP_OUTAGE_DURATION_HOURS,
  } = {}) {
    Object.assign(this, { name, ratedPowerW, availability, outageStartHours, outageDurationHours });
  }

  /** Rated * availability, or 0 W inside the scripted outage window. */
  availablePower(tHours) {
    // Guarded on null, not on truthiness: hour 0 is a legitimate start.
    if (this.outageStartHours !== null && this.outageStartHours !== undefined) {
      const end = this.outageStartHours + this.outageDurationHours;
      if (this.outageStartHours <= tHours && tHours < end) return 0.0;
    }
    return this.ratedPowerW * this.availability;
  }
}
