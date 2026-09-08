// conformance.js — hold the JS port to the Python model, tick for tick.
//
// The port is not trusted because it reads correctly. It is trusted because it
// reproduces a known-good 1440-tick run to within 1e-9 relative on every field
// of every tick, across three scenarios chosen to exercise disjoint paths.
//
// MEASURED, 2026-09-08. Against a full-precision golden the JS and Python
// models agree to within one ULP of a double:
//
//     bare      worst relative 0          bit-identical
//     topology  worst relative 1.85e-16   under 1 ULP (2.2e-16)
//     full      worst relative 1.85e-16
//
// The residue is not a modelling difference. `bare` has no topology, so it
// never calls Feeder.lossW, so it never squares a current — and it comes out
// bit-identical. The other two do, and Python squares with math.pow while this
// port uses `i * i`. IEEE-754 requires multiplication to be correctly rounded
// but does NOT require it of pow, so the two may differ by an ulp. `i * i` is
// the more accurate of the two, so it stays; chasing bit-identity by adopting
// a worse operation would be the wrong trade.
//
// The shipped golden is stored at 10 significant digits, which puts a floor of
// about 5e-10 on what this check can resolve. That is the number the report
// prints, and it is a property of the FILE FORMAT, not of the model.
//
// A divergence here is almost never dramatic. It is a `<=` where a `<` belongs,
// or Python's max() returning the first tie where a JS reduce returned the
// last. Those produce identical output for hundreds of ticks and then diverge
// once, which is exactly why the comparison is per-tick and not on summaries.

import { LunarEnvironment } from "./environment.js";
import { SimulationEngine } from "./engine.js";
import { buildOutpost } from "./outpost.js";

/** Relative tolerance. The golden is stored at 10 significant digits, so
 *  anything tighter than ~1e-10 would be comparing against rounding rather
 *  than against the model. */
export const REL_TOL = 1e-9;

/** Below this many watts, relative comparison is meaningless — a value that
 *  should be 0.0 and comes out 1e-18 is agreement, not a 100% error. */
export const ABS_FLOOR = 1e-6;

function agrees(got, want) {
  if (got === want) return true;
  if (!Number.isFinite(got) || !Number.isFinite(want)) return false;
  const diff = Math.abs(got - want);
  if (diff <= ABS_FLOOR) return true;
  return diff <= REL_TOL * Math.max(Math.abs(got), Math.abs(want));
}

/** Run the JS model under the same options the golden was exported with. */
export function runScenario(options) {
  const engine = new SimulationEngine(
    buildOutpost(new LunarEnvironment(), options.outage,
                options.topology, options.converters));
  engine.run();
  return engine;
}

/**
 * Compare a JS run against a golden export.
 * @returns {{scenario, ticks, fields, checks, failures, worst}}
 */
export function compare(golden, engine) {
  const { fields, actions, rows } = golden;
  const history = engine.history;
  const failures = [];
  let checks = 0;
  // The worst RELATIVE difference seen anywhere, failing or not. Zero here
  // means bit-identical output, which is a real and checkable claim; a small
  // non-zero number means agreement within tolerance. They are not the same
  // statement and the report should not conflate them.
  let worst = { field: null, relative: 0.0 };

  if (history.length !== rows.length) {
    failures.push({
      tick: -1, field: "LENGTH",
      got: history.length, want: rows.length,
      note: "tick count differs — nothing else is comparable",
    });
    return { scenario: golden.scenario, ticks: rows.length,
            fields: fields.length, checks, failures, worst };
  }

  for (let t = 0; t < rows.length; t++) {
    const record = history[t];
    const row = rows[t];

    for (let f = 0; f < fields.length; f++) {
      const field = fields[f];
      const want = row[f];
      let got = record[field];

      if (field === "action") {
        // Stored as an index into the action vocabulary; -1 for null.
        got = got === null || got === undefined ? -1 : actions.indexOf(got);
      } else if (typeof got === "boolean") {
        got = got ? 1 : 0;
      }

      checks++;
      // Track the worst divergence over EVERY comparison, not only failing
      // ones. Reporting the worst of the failures says "nothing failed" in a
      // column headed "worst difference", which is a different and much weaker
      // claim than the number actually shows.
      if (typeof got === "number" && Number.isFinite(got) && Number.isFinite(want)) {
        const scale = Math.max(Math.abs(got), Math.abs(want));
        const rel = scale > ABS_FLOOR ? Math.abs(got - want) / scale : 0.0;
        if (rel > worst.relative) worst = { field, relative: rel, tick: t, got, want };
      }
      if (got === undefined) {
        failures.push({ tick: t, field, got: "MISSING", want,
                        note: "field absent from the JS record" });
        continue;
      }
      if (!agrees(got, want)) {
        const scale = Math.max(Math.abs(got), Math.abs(want)) || 1;
        const relative = Math.abs(got - want) / scale;
        // Cap the report: a systematic divergence produces one failure per
        // tick, and sixty thousand lines of it says nothing the first ten do.
        if (failures.length < 12) failures.push({ tick: t, field, got, want, relative });
        else if (failures.length === 12) {
          failures.push({ tick: t, field: "...", got: "", want: "",
                          note: "further failures suppressed" });
        }
      }
    }
  }

  // Every field the JS produced that the golden has never heard of. A port
  // that ADDS a column is as wrong as one that drops one.
  const known = new Set(fields);
  for (const key of Object.keys(history[0])) {
    if (!known.has(key)) {
      failures.push({ tick: 0, field: key, got: "EXTRA", want: "",
                      note: "field present in JS but not in the golden" });
    }
  }

  return { scenario: golden.scenario, ticks: rows.length,
          fields: fields.length, checks, failures, worst };
}

/** Compare the summary block too — cheap, and it catches an aggregation bug
 *  that per-tick agreement would not (a wrong dt, a wrong reducer). */
export function compareSummary(golden, engine) {
  const got = engine.summary();
  const failures = [];
  for (const [key, want] of Object.entries(golden.summary)) {
    if (!agrees(got[key], want)) {
      failures.push({ field: key, got: got[key], want });
    }
  }
  return failures;
}

export function checkAll(goldens) {
  const results = [];
  for (const golden of goldens) {
    const engine = runScenario(golden.options);
    const result = compare(golden, engine);
    result.summaryFailures = compareSummary(golden, engine);
    result.passed = result.failures.length === 0
                && result.summaryFailures.length === 0;
    results.push(result);
  }
  return results;
}
