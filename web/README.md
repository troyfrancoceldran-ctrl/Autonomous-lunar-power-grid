# The model, in a browser

The same simulation as the Python model, running client-side — so a page can
*change* something and watch the outpost respond, rather than replaying an
exported history.

This directory is the port and the proof that it is faithful. The diagram that
uses it comes next.

---

## Why this was cheap

The core is **906 lines of executable code** against 2567 lines of
documentation, and every import in it is Python standard library:

| Python | JavaScript |
|---|---|
| `math` | `Math` |
| `dataclasses` | plain classes |
| `IntEnum` | a frozen object |
| `abc` | nothing — JS duck-types |

No numpy, no scipy, nothing that resists a port. That was not planned for the
browser: the controller was written as plain arithmetic in Step 7 so it could
one day run on a microcontroller. The same discipline made this nearly
mechanical.

---

## The conformance check

A port that fails loudly is not the risk. The risk is one that diverges
**quietly** — a `<=` where a `<` belongs — leaving two simulators, no way to
say which is right, and months of results resting on whichever happened to run.

So the port is not trusted because it reads correctly. It is trusted because it
reproduces a known-good Python run tick for tick.

```bash
.venv/bin/python web/tools/run_conformance.py
```

```
  scenario     ticks  fields     checks   worst rel   result
  --------------------------------------------------------------
  bare         1440      46      66240    4.63e-10   PASS
  topology     1440      46      66240    4.93e-10   PASS
  full         1440      46      66240    4.91e-10   PASS
```

**198,720 comparisons.** Three scenarios chosen to exercise disjoint paths:
`bare` is the model as it stood at Step 12, `topology` adds the feeder losses,
and `full` adds converters and a reactor outage — which is the only one that
reaches shortfall, shedding and the restore guard.

### How closely they actually agree

The ~5e-10 above is **the golden file's format, not the model**. The shipped
golden stores 10 significant digits, which puts a floor of about 5e-10 on what
the check can resolve. Re-exported at full precision:

| scenario | worst relative |
|---|---|
| bare | **0** — bit-identical |
| topology | 1.85e-16 |
| full | 1.85e-16 |

1.85e-16 is under one ULP of a double (2.2e-16), and the pattern names its own
cause: `bare` never calls `Feeder.lossW`, so it never squares a current, and it
comes out bit-identical. The other two do — and Python squares with
`math.pow` while the port uses `i * i`. IEEE-754 requires multiplication to be
correctly rounded but not `pow`, so they may differ by an ulp. `i * i` is the
*more* accurate of the two, so it stays. Chasing bit-identity by adopting a
worse operation would be the wrong trade.

### No Node required

There is no Node on the development machine and installing one would add a
toolchain the project does not otherwise need. macOS ships JavaScriptCore,
reachable as `osascript -l JavaScript`, and it runs every feature the port
uses. `run_conformance.py` strips the module syntax, concatenates in dependency
order, inlines the golden and executes that. The browser keeps proper ES
modules; only the headless path sees the flattened form.

The same check runs in a browser at `web/conformance.html`, which needs a
server because `fetch` will not read `file://`:

```bash
python3 -m http.server 8000        # from the repo root
# then open http://localhost:8000/web/conformance.html
```

---

## Constants are generated, not copied

`web/src/config.js` is produced from `config.py`:

```bash
.venv/bin/python web/tools/export_config.py
```

Every constant in this project carries a citation and several were argued over
— the 708.7 h synodic period, the 0.05 battery floor, the 3.0 h dwell.
Hand-copying that table into a second language works exactly once, and then
somebody revises a number on one side only. Generating it means the two agree
by construction rather than by discipline, and the comments come across too.

---

## Layout

```
web/
  src/
    config.js          GENERATED from config.py — do not edit
    environment.js     day/night cycle, and a safe modulo
    assets/
      base.js          the CONCRETE parts of the Python ABCs
      generation.js    PVArray · FissionSurfacePower
      storage.js       BatteryBank · RegenerativeFuelCell
      loads.js         ECLSS · ThermalControl · CommsArray · SciencePayload
    controller.js      shed/restore, with Python's first-wins tie-breaking
    topology.js        feeders, buses, conductor sizing
    converters.js      power electronics
    powerBus.js        one tick: measure, decide, dispatch, record
    engine.js          the loop, and summary()
    outpost.js         the parts list — the only file naming a concrete class
    conformance.js     the comparison itself
  golden/              frozen Python output, 3 scenarios × 1440 ticks
  tools/               generators and the headless runner
  conformance.html     the same check, in the browser
```

---

## Three things that would have gone wrong

Recorded because they are the porting hazards worth knowing, not because they
did go wrong — the conformance check was written first, so none of them ever
reached a result.

**Python's `%` returns a non-negative remainder for a positive divisor; JS
keeps the sign of the dividend.** `t` is never negative here, but relying on
that is the kind of assumption that survives until it doesn't. `environment.js`
exports a `mod` helper and the load duty cycles use it.

**`max(seq, key=f)` returns the FIRST maximum in Python.** A JS `reduce`
written with `>=` returns the last, which silently changes which load sheds
whenever two share a priority. `controller.js` compares strictly.

**A `None` outage start is not falsy-equivalent.** Hour 0 is a legitimate
outage start, so the guard is `!== null`, mirroring Python's `is not None`.
This one already caused a real defect once, on the Python side.
