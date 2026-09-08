"""
@file    web/tools/run_conformance.py
@brief   Run the JS conformance check headlessly, with no Node and no install.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-08

@details
The browser is the JS port's real home, and web/conformance.html runs the same
check there. But a check you can only run by opening a browser is a check that
stops being run, so this script executes it from the terminal.

There is no Node on this machine and installing one would add a toolchain the
project does not otherwise need. macOS already ships JavaScriptCore, reachable
as `osascript -l JavaScript`, and it supports every feature the port uses —
classes, getters, destructuring, spread, Map, template literals.

What it does NOT support is ES modules or file reads. So this script bundles:
strips the import/export syntax, concatenates the modules in dependency order,
inlines the golden data, and appends a runner. The browser keeps proper
modules; only this headless path sees the flattened form.

    .venv/bin/python web/tools/run_conformance.py

@note The bundle is written to the scratch directory, not into the repo. It is
    a build artifact of a verification step, not source.
@warning Stripping `export ` and `import ...` with regexes is only safe because
    this codebase's imports are all static, top-level and of the two shapes the
    patterns below match. It is a bundler for THIS project, not a general one,
    and it fails loudly rather than silently if it meets something else.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "web", "src")
GOLDEN = os.path.join(ROOT, "web", "golden")

# Dependency order. Hand-maintained because it is twelve files and a resolver
# would be more code than the thing it resolves.
MODULES = [
    "config.js",
    "environment.js",
    "assets/base.js",
    "assets/generation.js",
    "assets/storage.js",
    "assets/loads.js",
    "controller.js",
    "topology.js",
    "converters.js",
    "powerBus.js",
    "engine.js",
    "outpost.js",
    "conformance.js",
]

IMPORT_RE = re.compile(r"^import\s+.*?;\s*$", re.MULTILINE | re.DOTALL)
EXPORT_RE = re.compile(r"^export\s+(const|class|function|let|var)\s", re.MULTILINE)


def strip_module_syntax(source, path):
    """Remove import statements and `export ` prefixes."""
    # Multi-line imports: match from `import` to the terminating `;`.
    out, index = [], 0
    for match in re.finditer(r"^import\b", source, re.MULTILINE):
        start = match.start()
        end = source.find(";", start)
        if end == -1:
            raise ValueError(f"{path}: unterminated import statement")
        out.append(source[index:start])
        index = end + 1
    out.append(source[index:])
    source = "".join(out)

    source = EXPORT_RE.sub(r"\1 ", source)
    if re.search(r"^\s*export\b", source, re.MULTILINE):
        raise ValueError(f"{path}: an export form this bundler does not handle")
    return source


def build_bundle():
    parts = ["'use strict';\n"]
    for name in MODULES:
        path = os.path.join(SRC, name)
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        parts.append(f"\n// ===== {name} " + "=" * (60 - len(name)) + "\n")
        parts.append(strip_module_syntax(source, name))
    return "".join(parts)


RUNNER = r"""
// ===== headless runner =======================================================
var results = checkAll(GOLDENS);
var allPassed = true;
console.log("");
console.log("  scenario     ticks  fields     checks   worst rel   result");
console.log("  " + Array(63).join("-"));
for (var i = 0; i < results.length; i++) {
var r = results[i];
if (!r.passed) allPassed = false;
var worst = r.worst.relative ? r.worst.relative.toExponential(2) : "0";
console.log(
    "  " + r.scenario.padEnd(12) +
    String(r.ticks).padStart(5) + String(r.fields).padStart(8) +
    String(r.checks).padStart(11) + worst.padStart(12) +
    (r.passed ? "   PASS" : "   FAIL"));
}
console.log("");
for (var i = 0; i < results.length; i++) {
var r = results[i];
for (var j = 0; j < r.failures.length; j++) {
    var f = r.failures[j];
    console.log("  " + r.scenario + " tick " + f.tick + " " + f.field +
                "  got " + f.got + "  want " + f.want +
                (f.note ? "  (" + f.note + ")" : ""));
}
for (var j = 0; j < r.summaryFailures.length; j++) {
    var f = r.summaryFailures[j];
    console.log("  " + r.scenario + " SUMMARY " + f.field +
                "  got " + f.got + "  want " + f.want);
}
}
console.log(allPassed
? "  CONFORMANCE PASS — the JS port reproduces the Python model exactly."
: "  CONFORMANCE FAIL — see the divergences above.");
"""


def main():
    scenarios = json.load(open(os.path.join(GOLDEN, "manifest.json")))
    goldens = []
    for name in scenarios:
        with open(os.path.join(GOLDEN, f"{name}.json"), encoding="utf-8") as handle:
            goldens.append(json.load(handle))

    bundle = build_bundle()
    bundle += "\nvar GOLDENS = " + json.dumps(goldens, separators=(",", ":")) + ";\n"
    bundle += RUNNER

    scratch = os.environ.get("TMPDIR", tempfile.gettempdir())
    path = os.path.join(scratch, "lunar_conformance_bundle.js")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(bundle)
    print(f"  bundled {len(MODULES)} modules + {len(goldens)} scenarios "
        f"-> {len(bundle) / 1024 / 1024:.2f} MB")

    result = subprocess.run(["osascript", "-l", "JavaScript", path],
                            capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.stderr.strip():
        sys.stderr.write(result.stderr)
    raise SystemExit(0 if "CONFORMANCE PASS" in (result.stdout + result.stderr) else 1)


if __name__ == "__main__":
    main()
