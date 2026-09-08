// loads.js — the four load tiers. Port of assets/loads.py.
import { Load } from "./base.js";
import { mod } from "../environment.js";
import {
  LoadPriority, ECLSS_POWER_W, THERMAL_DAY_POWER_W, THERMAL_NIGHT_POWER_W,
  COMMS_ACTIVE_POWER_W, COMMS_STANDBY_POWER_W, COMMS_WINDOW_HOURS,
  COMMS_PERIOD_HOURS, SCIENCE_ACTIVE_POWER_W, SCIENCE_IDLE_POWER_W,
  SCIENCE_WINDOW_HOURS, SCIENCE_PERIOD_HOURS,
} from "../config.js";

export class ECLSS extends Load {
  constructor({ name = "Environmental Control and Life Support System",
                powerW = ECLSS_POWER_W, priority = LoadPriority.CRITICAL } = {}) {
    super();
    Object.assign(this, { name, powerW, priority });
  }
  /** Flat, around the clock. Never shed. */
  demand() { return this.powerW; }
}

export class ThermalControl extends Load {
  constructor(environment, { name = "Thermal Control",
                            dayPowerW = THERMAL_DAY_POWER_W,
                            nightPowerW = THERMAL_NIGHT_POWER_W,
                            priority = LoadPriority.HIGH } = {}) {
    super();
    Object.assign(this, { name, dayPowerW, nightPowerW, priority, environment });
  }
  /** The load never goes away, it only changes job: reject heat, or add it. */
  demand(tHours) {
    return this.environment.isDaylight(tHours) ? this.dayPowerW : this.nightPowerW;
  }
}

export class CommsArray extends Load {
  constructor({ name = "Communications Array",
                activePowerW = COMMS_ACTIVE_POWER_W,
                standbyPowerW = COMMS_STANDBY_POWER_W,
                windowHours = COMMS_WINDOW_HOURS,
                periodHours = COMMS_PERIOD_HOURS,
                priority = LoadPriority.MEDIUM } = {}) {
    super();
    Object.assign(this, { name, activePowerW, standbyPowerW, windowHours, periodHours, priority });
  }
  /** One transmit window per Earth day, standby between. */
  demand(tHours) {
    return mod(tHours, this.periodHours) < this.windowHours
      ? this.activePowerW : this.standbyPowerW;
  }
}

export class SciencePayload extends Load {
  constructor({ name = "Science Payload",
                activePowerW = SCIENCE_ACTIVE_POWER_W,
                idlePowerW = SCIENCE_IDLE_POWER_W,
                windowHours = SCIENCE_WINDOW_HOURS,
                periodHours = SCIENCE_PERIOD_HOURS,
                priority = LoadPriority.LOW } = {}) {
    super();
    Object.assign(this, { name, activePowerW, idlePowerW, windowHours, periodHours, priority });
  }
  /** Fully interruptible: drills, rovers, instruments. */
  demand(tHours) {
    return mod(tHours, this.periodHours) < this.windowHours
      ? this.activePowerW : this.idlePowerW;
  }
}
