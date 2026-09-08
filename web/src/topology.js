// topology.js — feeders and buses. Port of topology.py.
import {
  CABLE_TEMP_DAY_K, CABLE_TEMP_NIGHT_K, CABLE_TEMP_REFERENCE_K,
  CONDUCTOR_DENSITY_KG_PER_M3, CONDUCTOR_RESISTIVITY_OHM_M,
  CONDUCTOR_TEMP_COEFF_PER_K, FSP_RATED_POWER_W, FSP_SEPARATION_M,
  MAX_FEEDER_LOSS_FRACTION, MIN_CONDUCTOR_AREA_M2, TRANSMISSION_VOLTAGE_V,
  USER_BUS_MAX_SPAN_M, USER_BUS_VOLTAGE_V,
} from "./config.js";

/** 400 K in sunlight, 100 K at night. */
export function cableTemperatureK(isDaylight) {
  return isDaylight ? CABLE_TEMP_DAY_K : CABLE_TEMP_NIGHT_K;
}

export class Feeder {
  constructor(name, lengthM, areaM2, nominalVoltageV) {
    Object.assign(this, { name, lengthM, areaM2, nominalVoltageV });
  }

  /** Out and back. Applied here so nowhere else has to remember it. */
  get conductorLengthM() { return 2.0 * this.lengthM; }

  /** Round-trip resistance at a conductor temperature. */
  resistanceOhm(temperatureK) {
    const rho = CONDUCTOR_RESISTIVITY_OHM_M
      * (1 + CONDUCTOR_TEMP_COEFF_PER_K * (temperatureK - CABLE_TEMP_REFERENCE_K));
    return (rho * this.conductorLengthM) / this.areaM2;
  }

  /** I = P / V; 0 A for a non-positive voltage. */
  currentA(powerW, voltageV) {
    if (voltageV <= 0) return 0.0;
    return powerW / voltageV;
  }

  /** Volts lost along the run at this power and temperature. */
  voltageDropV(powerW, voltageV, temperatureK) {
    return this.currentA(powerW, voltageV) * this.resistanceOhm(temperatureK);
  }

  /** I^2 R dissipated in the conductor. */
  lossW(powerW, voltageV, temperatureK) {
    const i = this.currentA(powerW, voltageV);
    return i * i * this.resistanceOhm(temperatureK);
  }

  /** Conductor mass for the whole run, both directions. */
  conductorMassKg() {
    return CONDUCTOR_DENSITY_KG_PER_M3 * this.areaM2 * this.conductorLengthM;
  }

  /** Area meeting a loss budget, floored at the minimum gauge.
   *  Sized at the REFERENCE temperature, deliberately: a cable at 400 K needs
   *  1.43x this area for the same budget, and burying that choice would hide
   *  a real design decision. */
  static sizeForLossBudget(powerW, voltageV, lengthM, lossFraction) {
    const a = (powerW * CONDUCTOR_RESISTIVITY_OHM_M * (2 * lengthM))
            / (lossFraction * voltageV * voltageV);
    return Math.max(a, MIN_CONDUCTOR_AREA_M2);
  }
}

export class DCBus {
  constructor(name, nominalVoltageV, feeders = []) {
    Object.assign(this, { name, nominalVoltageV, feeders });
  }

  /** A feeder absent from the map is idle, not an error. */
  totalLossW(powerByFeeder, temperatureK) {
    return this.feeders.reduce(
      (sum, f) => sum + f.lossW(powerByFeeder[f.name] ?? 0.0,
                                f.nominalVoltageV, temperatureK), 0.0);
  }

  totalConductorMassKg() {
    return this.feeders.reduce((sum, f) => sum + f.conductorMassKg(), 0.0);
  }

  feeder(name) {
    const found = this.feeders.find((f) => f.name === name);
    if (!found) throw new Error(`no feeder named ${name} on bus ${this.name}`);
    return found;
  }
}

// NAMES MUST MATCH buildOutpost EXACTLY. A feeder is bound to its asset by
// name and a mismatch is SILENT — the asset simply gets no feeder and reports
// 0.0 W forever. That is defect D-03, which left a 1 km reactor link unused
// while every total still looked plausible.
export const USER_BUS_LAYOUT = [
  ["PV Array", 50.0, 34900.0],
  ["Battery Bank", 10.0, 50000.0],
  ["Regenerative Fuel Cell", 20.0, 25000.0],
  ["Environmental Control and Life Support System", 5.0, 6500.0],
  ["Thermal Control", 10.0, 5500.0],
  ["Communications Array", 30.0, 2500.0],
  ["Science Payload", 60.0, 6000.0],
];

export const PROVISIONAL_AREA_M2 = 1.0e-5;

export function buildTopology(sized = false, lossFraction = MAX_FEEDER_LOSS_FRACTION) {
  const area = (powerW, lengthM, voltageV) =>
    sized ? Feeder.sizeForLossBudget(powerW, voltageV, lengthM, lossFraction)
          : PROVISIONAL_AREA_M2;

  const user = new DCBus("user", USER_BUS_VOLTAGE_V,
    USER_BUS_LAYOUT.map(([name, lengthM, peakW]) =>
      new Feeder(name, lengthM, area(peakW, lengthM, USER_BUS_VOLTAGE_V), USER_BUS_VOLTAGE_V)));

  const transmission = new DCBus("transmission", TRANSMISSION_VOLTAGE_V, [
    new Feeder("FSP Reactor", FSP_SEPARATION_M,
      area(FSP_RATED_POWER_W, FSP_SEPARATION_M, TRANSMISSION_VOLTAGE_V),
      TRANSMISSION_VOLTAGE_V),
  ]);
  return [user, transmission];
}

/** Feeders exceeding the 100 m ISPSIS limitation. Reports, never asserts. */
export function overSpanLimit(bus) {
  if (bus.nominalVoltageV > USER_BUS_VOLTAGE_V) return [];
  return bus.feeders.filter((f) => f.lengthM > USER_BUS_MAX_SPAN_M).map((f) => f.name);
}
