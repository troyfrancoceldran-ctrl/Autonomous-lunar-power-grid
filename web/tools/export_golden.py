"""
@file    web/tools/export_golden.py
@brief   Freeze the Python model's output so the JS port can be held to it.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-08

@details
The risk in porting a simulator to a second language is not that it fails
loudly. It is that it diverges quietly — a `<=` where a `<` belongs — and you
end up with two models, no way to say which is right, and months of results
built on whichever one you happened to run.

So the port is not trusted because it looks correct. It is trusted because it
reproduces a known-good run tick for tick, to the last watt.

    .venv/bin/python web/tools/export_golden.py

Writes web/golden/<scenario>.json, one file per scenario, in a compact
columnar form: field names once, then one row of numbers per tick. That is
about a third the size of a list of objects and reads back in one map.

@note THREE SCENARIOS, chosen to exercise disjoint code paths rather than to
    be thorough for its own sake:
    bare      no topology, no converters — the model as it stood at Step 12
    topology  feeders only — the T01/T02 loss path
    full      feeders + converters + a reactor outage — every branch,
                including shortfall, shedding and the restore guard
    A port that matches all three has no untested corner left that the Python
    suite covers.

@note Booleans are stored as 0/1 and `action` (a string or null) as an index
    into a small vocabulary, so every column is numeric and the comparison on
    the JS side is one code path rather than three.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from environment import LunarEnvironment          # noqa: E402
from main import build_outpost                    # noqa: E402
from simulation_engine import SimulationEngine    # noqa: E402

SCENARIOS = {
    "bare":     dict(outage=None,  topology=False, converters=False),
    "topology": dict(outage=None,  topology=True,  converters=False),
    "full":     dict(outage=500.0, topology=True,  converters=True),
}


def trim(value):
    """Ten significant digits.

    Doubles carry 15-17, and the conformance check compares at a relative
    tolerance of 1e-9, so ten digits is three orders tighter than anything
    that will ever be asked of it — while cutting the golden files by more
    than half. Full repr was spending twenty characters to store precision
    nothing reads.
    """
    if isinstance(value, float):
        return float(f"{value:.10g}")
    return value


def encode(history):
    """Columnar, all-numeric. Returns (fields, actions, rows)."""
    fields = [k for k in history[0] if k != "action"]
    actions = sorted({r["action"] for r in history if r["action"] is not None})
    index = {name: i for i, name in enumerate(actions)}

    rows = []
    for record in history:
        row = []
        for key in fields:
            value = record[key]
            row.append(int(value) if isinstance(value, bool) else trim(value))
        row.append(-1 if record["action"] is None else index[record["action"]])
        rows.append(row)
    return fields + ["action"], actions, rows


def main():
    outdir = os.path.join(ROOT, "web", "golden")
    os.makedirs(outdir, exist_ok=True)
    manifest = {}

    for name, opts in SCENARIOS.items():
        engine = SimulationEngine(build_outpost(
            LunarEnvironment(), opts["outage"], opts["topology"],
            opts["converters"]))
        engine.run()
        fields, actions, rows = encode(engine.history)

        payload = {
            "scenario": name,
            "options": opts,
            "fields": fields,
            "actions": actions,
            "rows": rows,
            "summary": {k: trim(v) for k, v in engine.summary().items()},
        }
        path = os.path.join(outdir, f"{name}.json")
        with open(path, "w") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        size = os.path.getsize(path)
        manifest[name] = {"options": opts, "ticks": len(rows),
                        "fields": len(fields), "bytes": size}
        print(f"  {name:<10} {len(rows):5d} ticks x {len(fields):3d} fields"
            f"   {size / 1024:8.1f} KB")

    with open(os.path.join(outdir, "manifest.json"), "w") as handle:
        json.dump(manifest, handle, indent=2)
    total = sum(m["bytes"] for m in manifest.values())
    print(f"  {'TOTAL':<10} {total / 1024:32.1f} KB")


if __name__ == "__main__":
    main()
