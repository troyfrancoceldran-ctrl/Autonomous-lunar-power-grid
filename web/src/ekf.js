// ekf.js — the one-state Extended Kalman Filter, in the browser.
//
// A port of estimator/src/ekf.cpp, which is the authority. This exists so the
// page can show the filter WORKING, tick by tick, rather than showing a chart
// of a result computed somewhere else: the whole point of the visualisation is
// that a reader watches an estimate diverge and get pulled back.
//
// It is kept honest the same way the rest of web/ is — by conformance testing
// against golden output generated from the real implementation. A port nobody
// checks is a second source of truth, and the first time it drifts the page
// starts lying about what the estimator does.
//
//   .venv/bin/python web/tools/export_ekf_golden.py
//   node web/src/conformance.js
//
// THE SIX LINES
//   predict:  z <- z - eta*I*dt/(3600*Q)
//             P <- P + Qproc
//   correct:  H <- dOCV/dz              at the PREDICTED state
//             K <- P*H / (H*H*P + R)
//             z <- z + K*(Vmeas - Vpred)
//             P <- (1 - K*H)*P
//
// K is the only interesting quantity: near 0 the filter has stopped believing
// the voltmeter. A flat OCV curve drives H to zero, which drives K to zero,
// however good the instrument — chemistry, not tuning.
import {
  OCV_POLY_NMC, CELLS_SERIES, BATTERY_R_INTERNAL_OHM,
  BATTERY_COULOMBIC_EFFICIENCY, BATTERY_CAPACITY_WH,
  BATTERY_SOC_MIN, BATTERY_SOC_MAX, VOLTAGE_SENSOR_NOISE_V,
} from "./config.js";

/** Nominal pack volts, the divisor that turns stored Wh into Ah. */
export const V_NOMINAL = 3.7 * CELLS_SERIES;
export const CAPACITY_AH = BATTERY_CAPACITY_WH / V_NOMINAL;

/** Pack open-circuit voltage at a state of charge. */
export function ocvV(soc) {
  const x = 2.0 * soc - 1.0;
  let result = 0.0;
  for (let i = OCV_POLY_NMC.length - 1; i >= 0; i -= 1) {
    result = result * x + OCV_POLY_NMC[i];
  }
  return result * CELLS_SERIES;
}

/**
 * The measurement Jacobian: d(pack OCV)/d(state of charge), volts per unit.
 *
 * THE CHAIN RULE. The polynomial is in x = 2*soc - 1, so differentiating the
 * coefficients gives dOCV/dx and still owes a factor of 2. Forget it and every
 * gain is half what it should be — the filter still runs, still converges,
 * just slower, which is exactly the kind of wrong that survives a demo.
 *
 * The loop stops at i >= 1: the constant term differentiates away, and running
 * down to 0 does not harmlessly add zero — it costs an extra multiply by x,
 * shifting every power by one.
 */
export function docvDsoc(soc) {
  const x = 2.0 * soc - 1.0;
  let result = 0.0;
  for (let i = OCV_POLY_NMC.length - 1; i >= 1; i -= 1) {
    result = result * x + i * OCV_POLY_NMC[i];
  }
  return result * CELLS_SERIES * 2.0;
}

export class Ekf {
  /**
   * @param initialSoc the prior — what you believe before any evidence
   * @param initialVar how strongly. Large means "I am guessing".
   * @param qProc      process variance per step
   * @param rMeas      measurement variance. A BELIEF, not a measurement.
   */
  constructor(initialSoc, initialVar = 1e-6, qProc = 1e-9,
              rMeas = VOLTAGE_SENSOR_NOISE_V ** 2) {
    this.soc = initialSoc;
    this.variance = initialVar;
    this.qProc = qProc;
    this.rMeas = rMeas;
    this.gain = 0.0;
  }

  /** One predict/correct cycle. @return the updated estimate. */
  update(currentA, terminalVoltageV, dtS) {
    // predict
    this.soc -= (BATTERY_COULOMBIC_EFFICIENCY * currentA * dtS)
      / (3600.0 * CAPACITY_AH);
    this.variance += this.qProc;

    // correct — H at the PREDICTED state, never the old one
    const h = docvDsoc(this.soc);
    const predictedV = ocvV(this.soc) - currentA * BATTERY_R_INTERNAL_OHM;
    const residualV = terminalVoltageV - predictedV;

    this.gain = (this.variance * h) / (h * h * this.variance + this.rMeas);
    this.soc += this.gain * residualV;
    this.variance = (1.0 - this.gain * h) * this.variance;

    // Clamp the estimate, never the variance: squeezing a confidence lies to
    // the filter about how much it knows.
    this.soc = Math.min(Math.max(this.soc, BATTERY_SOC_MIN), BATTERY_SOC_MAX);
    return this.soc;
  }
}
