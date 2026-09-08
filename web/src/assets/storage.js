// storage.js — BatteryBank and RegenerativeFuelCell. Port of assets/storage.py.
//
// The asymmetry to keep hold of: multiply by efficiency on the way IN, divide
// on the way OUT, and invert both again in deliverable_energy_wh. Getting one
// of the four backwards makes a device that generates energy, which the
// conservation identity will report immediately.
import { PowerStorage } from "./base.js";
import {
  BATTERY_CAPACITY_WH, BATTERY_INITIAL_SOC, BATTERY_MAX_CHARGE_POWER_W,
  BATTERY_MAX_DISCHARGE_POWER_W, BATTERY_CHARGE_EFFICIENCY,
  BATTERY_DISCHARGE_EFFICIENCY, BATTERY_SOC_MIN, BATTERY_SOC_MAX,
  H2_SPECIFIC_ENERGY_WH_PER_KG, O2_TO_H2_MASS_RATIO, ELECTROLYZER_EFFICIENCY,
  FUEL_CELL_EFFICIENCY, RFC_H2_CAPACITY_KG, RFC_INITIAL_SOC,
  RFC_MAX_CHARGE_POWER_W, RFC_MAX_DISCHARGE_POWER_W, RFC_SOC_MIN, RFC_SOC_MAX,
} from "../config.js";

export class BatteryBank extends PowerStorage {
  constructor({
    name = "Battery Bank", capacityWh = BATTERY_CAPACITY_WH,
    initialSoc = BATTERY_INITIAL_SOC,
    maxChargePowerW = BATTERY_MAX_CHARGE_POWER_W,
    maxDischargePowerW = BATTERY_MAX_DISCHARGE_POWER_W,
    chargeEfficiency = BATTERY_CHARGE_EFFICIENCY,
    dischargeEfficiency = BATTERY_DISCHARGE_EFFICIENCY,
    socMin = BATTERY_SOC_MIN, socMax = BATTERY_SOC_MAX,
  } = {}) {
    super();
    Object.assign(this, {
      name, capacityWh, initialSoc, maxChargePowerW, maxDischargePowerW,
      chargeEfficiency, dischargeEfficiency, socMin, socMax,
    });
    this.energyWh = initialSoc * capacityWh;
  }

  get stateOfCharge() { return this.energyWh / this.capacityWh; }

  charge(powerW, dtHours) {
    if (dtHours <= 0 || powerW <= 0) return 0.0;
    let acceptedPowerW = Math.min(powerW, this.maxChargePowerW);
    let energyInWh = acceptedPowerW * dtHours * this.chargeEfficiency;
    const headroomWh = this.socMax * this.capacityWh - this.energyWh;
    if (energyInWh > headroomWh) {          // fills mid-timestep
      energyInWh = headroomWh;
      acceptedPowerW = energyInWh / (dtHours * this.chargeEfficiency);
    }
    this.energyWh += energyInWh;
    this.clampEnergy();
    return acceptedPowerW;
  }

  discharge(powerW, dtHours) {
    if (dtHours <= 0 || powerW <= 0) return 0.0;
    let deliveredPowerW = Math.min(powerW, this.maxDischargePowerW);
    let energyOutWh = (deliveredPowerW * dtHours) / this.dischargeEfficiency;
    const availableWh = this.energyWh - this.socMin * this.capacityWh;
    if (energyOutWh > availableWh) {        // hits the floor mid-timestep
      energyOutWh = availableWh;
      deliveredPowerW = (energyOutWh * this.dischargeEfficiency) / dtHours;
    }
    this.energyWh -= energyOutWh;
    this.clampEnergy();
    return deliveredPowerW;
  }

  get deliverableEnergyWh() {
    const spendableWh = this.energyWh - this.socMin * this.capacityWh;
    return Math.max(0.0, spendableWh) * this.dischargeEfficiency;
  }

  get deliverableCapacityWh() {
    return (this.socMax - this.socMin) * this.capacityWh * this.dischargeEfficiency;
  }

  clampEnergy() {
    const floorWh = this.socMin * this.capacityWh;
    const ceilingWh = this.socMax * this.capacityWh;
    this.energyWh = Math.min(Math.max(this.energyWh, floorWh), ceilingWh);
  }
}

export class RegenerativeFuelCell extends PowerStorage {
  constructor({
    name = "Regenerative Fuel Cell", h2CapacityKg = RFC_H2_CAPACITY_KG,
    initialSoc = RFC_INITIAL_SOC, maxChargePowerW = RFC_MAX_CHARGE_POWER_W,
    maxDischargePowerW = RFC_MAX_DISCHARGE_POWER_W,
    electrolyzerEfficiency = ELECTROLYZER_EFFICIENCY,
    fuelCellEfficiency = FUEL_CELL_EFFICIENCY,
    specificEnergyWhPerKg = H2_SPECIFIC_ENERGY_WH_PER_KG,
    socMin = RFC_SOC_MIN, socMax = RFC_SOC_MAX,
  } = {}) {
    super();
    Object.assign(this, {
      name, h2CapacityKg, initialSoc, maxChargePowerW, maxDischargePowerW,
      electrolyzerEfficiency, fuelCellEfficiency, specificEnergyWhPerKg,
      socMin, socMax,
    });
    this.h2MassKg = initialSoc * h2CapacityKg;
  }

  get stateOfCharge() { return this.h2MassKg / this.h2CapacityKg; }

  /** Stoichiometry, reported for the mass budget; nothing dispatches on it. */
  get o2MassKg() { return this.h2MassKg * O2_TO_H2_MASS_RATIO; }

  charge(powerW, dtHours) {
    if (dtHours <= 0 || powerW <= 0) return 0.0;
    let acceptedPowerW = Math.min(powerW, this.maxChargePowerW);
    const energyElecWh = acceptedPowerW * dtHours;
    let h2GainKg = (energyElecWh * this.electrolyzerEfficiency) / this.specificEnergyWhPerKg;
    const headroomKg = this.socMax * this.h2CapacityKg - this.h2MassKg;
    if (h2GainKg > headroomKg) {           // tanks fill mid-timestep
      h2GainKg = headroomKg;
      acceptedPowerW = (h2GainKg * this.specificEnergyWhPerKg)
                     / (dtHours * this.electrolyzerEfficiency);
    }
    this.h2MassKg += h2GainKg;
    this.clampMass();
    return acceptedPowerW;
  }

  discharge(powerW, dtHours) {
    if (dtHours <= 0 || powerW <= 0) return 0.0;
    let deliveredPowerW = Math.min(powerW, this.maxDischargePowerW);
    const energyElecWh = deliveredPowerW * dtHours;
    let h2UsedKg = energyElecWh / (this.fuelCellEfficiency * this.specificEnergyWhPerKg);
    const availableKg = this.h2MassKg - this.socMin * this.h2CapacityKg;
    if (h2UsedKg > availableKg) {          // tanks empty mid-timestep
      h2UsedKg = availableKg;
      deliveredPowerW = (h2UsedKg * this.specificEnergyWhPerKg * this.fuelCellEfficiency) / dtHours;
    }
    this.h2MassKg -= h2UsedKg;
    this.clampMass();
    return deliveredPowerW;
  }

  get deliverableEnergyWh() {
    const spendableKg = this.h2MassKg - this.socMin * this.h2CapacityKg;
    return Math.max(0.0, spendableKg) * this.specificEnergyWhPerKg * this.fuelCellEfficiency;
  }

  get deliverableCapacityWh() {
    return (this.socMax - this.socMin) * this.h2CapacityKg
         * this.specificEnergyWhPerKg * this.fuelCellEfficiency;
  }

  clampMass() {
    const floorKg = this.socMin * this.h2CapacityKg;
    const ceilingKg = this.socMax * this.h2CapacityKg;
    this.h2MassKg = Math.min(Math.max(this.h2MassKg, floorKg), ceilingKg);
  }
}
