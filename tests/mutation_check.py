"""
Mutation check — NOT a pytest module (no test_ prefix, so it is not collected).

Run it directly:   .venv/bin/python tests/mutation_check.py

Reintroduces every bug this project actually shipped, one at a time, and
confirms the suite goes red for each. A suite that stays green here is
decoration: 188 passing tests told us nothing until this ran.

Each mutation is applied to the source, pytest is run, and the file is
restored immediately afterwards. The working tree is left clean.

TWO HARNESS BUGS worth remembering, both of which reported a false SURVIVED:

1. Every module here carries a Doxygen header whose SPEC sections quote the
    implementation verbatim as pseudocode. A naive replace(old, new, 1)
    rewrote the DOCUMENTATION and left the code untouched, so pytest tested
    unmutated code and correctly passed. Fixed by splitting at the end of
    the module docstring and mutating only the body. Four of nine mutations
    were falsely reported as survived until this was found.
2. Python caches compiled modules by source mtime, and a write-run-restore
    cycle this fast can execute a stale .pyc. Fixed with -B and by clearing
    __pycache__ between runs. (This turned out not to be the cause here, but
    it is a real hazard and the guard costs nothing.)

KNOWN EQUIVALENT MUTANT: M2 removes the night gate from
solar_elevation_fraction, leaving the max(0.0, ...) clamp as the only
defence. It survives and always will. _phase_hours bounds phase to
[0, 708.7), so the sine argument lands in [pi, 2pi) at night, where sine is
non-positive everywhere — measured worst case -3.2e-16. Gate and clamp are
behaviourally identical, so no test can tell them apart. The gate stays for
readability and because any future change to the profile formula would make
it load-bearing again.
"""
import os
import pathlib
import subprocess

# Resolve the project root from THIS file's location, never from a hardcoded
# path. A public repo has to run on someone else's machine.
os.chdir(pathlib.Path(__file__).resolve().parent.parent)
PYTHON = str(pathlib.Path(".venv/bin/python")) if pathlib.Path(".venv/bin/python").exists() else "python3"

MUTATIONS = [
("environment.py", "M1  is_daylight returns a constant (the W01 bug)",
"return self._phase_hours(t_hours) < LUNAR_DAY_HOURS",
"return self.start_phase_hours < LUNAR_DAY_HOURS"),

("environment.py", "M2  night gate removed; only the clamp defends",
"        if not self.is_daylight(t_hours):\n            return 0.0\n        phase = self._phase_hours(t_hours)",
"        phase = self._phase_hours(t_hours)"),

("assets/generation.py", "M3  sun_tracking multiplied, not branched (the W02 bug)",
"        if self.sun_tracking:\n            phi = environment.solar_irradiance_fraction(t_hours)\n        else:\n            phi = environment.solar_elevation_fraction(t_hours)",
  "        phi = (environment.solar_irradiance_fraction(t_hours)\n               * self.sun_tracking)"),

("assets/generation.py", "M4  outage guard uses truthiness, not `is not None`",
"if self.outage_start_hours is not None:",
"if self.outage_start_hours:"),

("assets/storage.py", "M5  RFC deliverable_energy_wh loses @property (the W04 bug)",
"    @property\n    def deliverable_energy_wh(self) -> float:\n        \"\"\"Bus-side energy still available [Wh], after floor and losses.\"\"\"\n        spendable_kg",
"    def deliverable_energy_wh(self) -> float:\n        \"\"\"Bus-side energy still available [Wh], after floor and losses.\"\"\"\n        spendable_kg"),

("assets/storage.py", "M6  RFC efficiency divides instead of multiplying",
  "        return (max(0.0, spendable_kg)\n                * self.specific_energy_wh_per_kg\n                * self.fuel_cell_efficiency)",
  "        return (max(0.0, spendable_kg)\n                * self.specific_energy_wh_per_kg\n                / self.fuel_cell_efficiency)"),

("controller.py", "M7  restore drops the fit test (the D-01 defect)",
"                        and load.demand(t_hours) <= headroom_w]",
"                        ]"),

("controller.py", "M8  CRITICAL loads become sheddable",
"                        if not load.shed\n                        and load.priority is not LoadPriority.CRITICAL]\n            if not candidates:\n                return None\n            target = max(candidates, key=lambda load: load.priority)\n            target.shed = True\n            self._last_change_h[target.name] = t_hours\n            return target\n\n        # ENERGY low.",
"                        if not load.shed]\n            if not candidates:\n                return None\n            target = max(candidates, key=lambda load: load.priority)\n            target.shed = True\n            self._last_change_h[target.name] = t_hours\n            return target\n\n        # ENERGY low."),

("config.py", "M9  dwell back to the timestep, making the guard vacuous",
"MIN_ACTION_DWELL_HOURS: float = 3.0",
"MIN_ACTION_DWELL_HOURS: float = 1.0"),
]

print(f"{'mutation':<62}{'result':>10}  caught by")
print("-" * 110)
survived = []
for path, label, old, new in MUTATIONS:
    p = pathlib.Path(path); original = p.read_text()

    # Mutate the CODE only. Every module here carries a Doxygen header whose
    # SPEC sections quote the implementation verbatim as pseudocode, so a
    # naive replace(old, new, 1) rewrites the documentation and leaves the
    # code untouched — pytest then tests unmutated code and correctly passes,
    # and the mutation is reported as survived. Split at the end of the module
    # docstring first.
    body_start = original.index('"""', original.index('"""') + 3) + 3
    head, body = original[:body_start], original[body_start:]
    if old not in body:
        where = "in the docstring only" if old in head else "not found"
        print(f"{label:<62}{'SKIP':>10}  anchor {where}"); continue
    p.write_text(head + body.replace(old, new, 1))
    # Python's .pyc invalidation is mtime-based with coarse granularity, so a
    # write-run-restore cycle this fast can execute a STALE cached module and
    # report a mutation as survived when it was never actually applied.
    subprocess.run(["find", ".", "-name", "__pycache__", "-type", "d",
                    "-not", "-path", "./.venv/*", "-exec", "rm", "-rf", "{}", "+"],
                capture_output=True)
    r = subprocess.run([PYTHON, "-B", "-m", "pytest", "tests/", "-q",
                        "--no-header", "-x", "--tb=no"],
                    capture_output=True, text=True)
    p.write_text(original)                       # restore immediately
    out = r.stdout
    failed = "failed" in out or "error" in out
    first = ""
    for line in out.splitlines():
        if line.startswith("FAILED") or line.startswith("ERROR"):
            first = line.split(" ")[0].split("::")[-1][:44]; break
    if not first:
        for line in out.splitlines():
            if "assert" in line or "Error" in line:
                first = line.strip()[:44]; break
    print(f"{label:<62}{'CAUGHT' if failed else 'SURVIVED':>10}  {first}")
    if not failed:
        survived.append(label)

print("-" * 110)
print("ALL MUTATIONS CAUGHT" if not survived
    else f"{len(survived)} SURVIVED — the suite has blind spots:\n  " + "\n  ".join(survived))
