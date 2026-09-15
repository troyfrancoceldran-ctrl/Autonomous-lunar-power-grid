# C++ for someone who writes Python

Author: Troy Celdran, with JARVIS (Claude Opus 5) as co-author
Written 2026-09-14, for B02.

Not a C++ tutorial. This is the *specific* subset needed to write
`docv_dsoc` and `Ekf::update`, and the traps that will actually fire while
you do. Everything else about the language can wait.

**Read the section for the task in front of you, not the whole document.**
It is written to be picked up mid-flight:

| you are writing | read |
|---|---|
| `docv_dsoc` (B02 fn 1) | everything down to *What you can safely ignore* |
| `Ekf::update` (B02 fn 2) | *Function 2* |
| reading the HIL bridge (B03) | *What changes on hardware* |
| the measurement table (B04) | nothing — that is Python |

---

## Start here: a translation of your own code

`ocv_v` in `include/battery_params.hpp` is a line-for-line port of the
`open_circuit_voltage_v` you wrote in B01. It is the best reference in the
repository, because you already know exactly what it is supposed to do.

```python
# Python — yours, assets/storage.py
def open_circuit_voltage_v(self, soc):
    x = 2.0 * soc - 1.0
    result = 0.0
    for coefficient in reversed(OCV_POLY_NMC):
        result = result * x + coefficient
    return result * self.cells
```

```cpp
// C++ — generated, include/battery_params.hpp
inline double ocv_v(double soc) {
    const double x = 2.0 * soc - 1.0;
    double result = 0.0;
    for (int i = OCV_POLY_N - 1; i >= 0; --i) {
        result = result * x + OCV_POLY[i];
    }
    return result * static_cast<double>(CELLS_SERIES);
}
```

Same algorithm, same order, same Horner accumulation. Every difference is
mechanical. `docv_dsoc` is this same loop shape.

---

## The mechanical differences

| Python | C++ | why |
|---|---|---|
| `x = 2.0 * soc - 1` | `const double x = 2.0 * soc - 1.0;` | every variable states its type; add `const` when it never changes |
| `result = 0.0` | `double result = 0.0;` | declared once with a type, then assigned freely |
| `for c in reversed(poly)` | `for (int i = N - 1; i >= 0; --i)` | you walk the index yourself |
| `for i, c in enumerate(poly)` | `for (int i = 0; i < N; ++i)` | the counter IS the loop |
| `poly[-1]` | **does not exist** | negative indexing is undefined behaviour, not an error — it reads whatever memory sits before the array |
| `len(poly)` | `OCV_POLY_N` | arrays do not carry their length; the header exports it as a constant |
| `x ** 2` | `x * x` | there is no `**` operator |
| `abs(x)` | `std::abs(x)` | needs `#include <cmath>` |
| `min(a, b)` | `std::min(a, b)` | needs `#include <algorithm>` |
| `self.soc` | `soc_` | members are already in scope; the trailing `_` marks them |
| `return` (bare) | must return a `double` | the return type is declared and enforced |
| `# comment` | `// comment` | |
| newline ends a statement | `;` ends a statement | indentation means nothing to the compiler |

---

## The five that will actually bite

### 1. `params::` prefixes

The constants live in `lunar::params`. Inside `namespace lunar`, plain
`OCV_POLY` will not resolve. Either qualify it:

```cpp
params::OCV_POLY[i]
params::CELLS_SERIES
params::SOC_MIN
```

or put an alias at the top of the file once and use the short form:

```cpp
namespace P = params;   // then: P::OCV_POLY[i]
```

### 2. Integer division silently truncates

`1 / 2` is `0` in C++. Not `0.5`, not an error. Write the decimal point
anywhere a division could involve two integers:

```cpp
dt_s / 3600.0      // correct
dt_s / 3600        // fine HERE only because dt_s is a double — do not rely on it
```

Make it a habit. The one time it matters, it will not announce itself.

### 3. `-Werror` is on, and so is `-Wconversion`

Every warning stops the build. That is deliberate: in an estimator, a silent
numeric conversion is a bug that produces plausible numbers.

The one you will hit is mixing an `int` loop counter into a `double`
expression. Say the conversion out loud:

```cpp
static_cast<double>(i) * params::OCV_POLY[i]
```

Verbose, but it is the compiler refusing to guess on your behalf.

`-Wshadow` is on too: do not give a local variable the same name as a
parameter or a member.

### 4. Headers are not imports

There is no `import`. A function you did not write comes from a header that
must be `#include`d at the top of the file:

| you want | you need |
|---|---|
| `std::clamp`, `std::min`, `std::max` | `#include <algorithm>` |
| `std::abs`, `std::pow`, `std::sqrt` | `#include <cmath>` |

Forget one and the error is enormous and points at the wrong line. If a
message mentions a name you recognise as standard-library, the fix is
almost always a missing include.

### 5. `const` on a member function

```cpp
double soc() const { return soc_; }
```

That trailing `const` is a promise not to modify the object. `update()`
does not have it, because changing the estimate is its entire job. You do
not need to write any new ones — just do not delete the ones that are there.

---

## One habit worth not bringing over

```cpp
using namespace std;   // works, and you will see it in tutorials everywhere
```

It compiles. It is also how C++ codebases acquire name collisions that only
appear months later, when someone includes a header that happens to define
its own `count` or `distance` and a call silently binds to the wrong one.

Write `std::clamp`, `std::abs`, `std::min` in full. Four extra characters,
and the reader always knows where a name came from. The same reasoning as
`import numpy as np` over `from numpy import *`.

Unused `#include`s are harmless — `<iostream>` costs nothing if you never
print — but drop them once the debugging is done.

---

## What you can safely ignore

For this task you need **none** of:

- pointers, `*`, `&`, address-of
- `new` / `delete`, or any memory management
- templates, `auto`, lambdas
- inheritance, virtual functions
- the STL beyond `std::clamp`

Every value here is a `double` or an `int`. The filter is deliberately
allocation-free so it can flash to an ESP32 later, which means the hardest
parts of C++ never enter the picture.

---

## Reading a C++ error message

They are long. The rule is: **read the FIRST error and ignore the rest.**
Errors cascade — one missing semicolon generates twenty complaints, and
nineteen are noise.

```
ekf.cpp:23:12: error: use of undeclared identifier 'OCV_POLY'
                   ^
```

`file:line:column: error: what`. The caret points at the exact character.
That is the whole format, and it is more precise than a Python traceback —
it is just buried in volume.

Three you are likely to see:

| message | means |
|---|---|
| `use of undeclared identifier 'X'` | missing `params::`, or a typo |
| `expected ';' after ...` | missing semicolon, usually the line ABOVE the one named |
| `implicit conversion loses precision` | `-Wconversion` — add the `static_cast<double>` |

---

## The build loop

```bash
cmake --build estimator/build && ./estimator/build/test_ekf
```

**Build after every few lines, not at the end.** Three overlapping mistakes
produce far worse messages than one, and this loop takes about a second.

Tests for unwritten methods report `SKIP`, not `FAIL`, so the build stays
green while you work and the skip list doubles as the to-do list.

Order of work:

1. **`docv_dsoc` first.** `jacobian_matches_a_numerical_derivative` checks it
   against a finite difference in isolation — it can be PROVEN right before
   anything depends on it.
2. **`Ekf::update` second**, once the Jacobian is trustworthy.

If you change `config.py`, regenerate the header rather than editing it:

```bash
.venv/bin/python estimator/tools/export_params.py
```

---

# Function 2: `Ekf::update`

Everything above still applies. Four things are new, and the first is the
only one that can cost you an afternoon.

## Members: assign them, never re-declare them

In Python you write `self.soc = ...`. In C++ the members already exist and
are already in scope. You simply assign:

```cpp
soc_ = soc_ - ...;      // assigns the member. Correct.
```

The trap:

```cpp
double soc_ = soc_ - ...;   // WRONG — creates a brand-new local variable
```

That `double` declares a *different* variable that merely shares the name.
It lives until the closing brace and then vanishes. The member is never
touched, `update()` returns a plausible number, and the filter silently
never learns anything.

**The build catches this one.** `-Wshadow` fires and `-Werror` makes it
fatal:

```
warning: declaration shadows a field of 'lunar::Ekf' [-Wshadow]
    double soc_ = 0.5;
           ^
```

Rule of thumb: write `double` only when introducing a **new** temporary.
Never in front of `soc_`, `variance_` or `gain_`.

## Name your intermediates

Six lines of algebra compressed into one expression is unreadable and
impossible to debug. Temporaries are free — the compiler eliminates them:

```cpp
const double h = docv_dsoc(soc_);
const double v_pred = params::ocv_v(soc_) - current_a * params::R_INTERNAL_OHM;
```

`const` on each says "this is computed once and never changes", which is
true of every intermediate in the six lines.

## `std::clamp` needs a header

```cpp
#include <algorithm>        // at the top of the file, beside <stdexcept>

soc_ = std::clamp(soc_, params::SOC_MIN, params::SOC_MAX);
```

Clamp `soc_` at the END, after the correction. Never clamp `variance_`: it
is a variance, and squeezing it lies to the filter about its own confidence.

## There is no simultaneous assignment

Python lets you write `a, b = b, a` and swap in one line. C++ evaluates
statements strictly top to bottom, so **if you overwrite a value you still
need, save it first**:

```cpp
const double soc_prior = soc_;   // keep it before soc_ changes
```

This is why trap 1 in `ekf.hpp` matters: `H` must be computed **after** the
predict step, because it has to be the slope at the *predicted* state. Move
that line above the predict and you have linearised about the old estimate —
a different filter, and a worse one. The compiler cannot help here; order is
a matter of meaning, not syntax.

## Housekeeping

Delete the `(void)` casts as the values become genuinely used —
`(void)current_a;`, `(void)q_proc_;` and the rest. They exist only to
silence unused-parameter warnings in a stub. Leaving one behind is harmless,
but it reads as scaffolding nobody cleared.

---

# B03: what changes on hardware

B03 is mine to write, but you will read it, and the shift is worth knowing
in advance. None of it affects how you write the filter now — the filter is
deliberately plain C++ so that it does not have to change.

| on the host (now) | on the ESP32 (B03) |
|---|---|
| `double` throughout | `float` is likely. CONFIRMED on the attached part: ESP32-D0WD-V3, whose LX6 core has a single-precision FPU, so `double` is emulated in software and markedly slower |
| `throw std::logic_error` | exceptions are off by default in ESP-IDF builds — errors become return codes |
| `int` | fixed-width `int32_t` / `uint8_t` from `<cstdint>`, because plain `int` has no guaranteed size across platforms |
| `main()` | `setup()` and `loop()` |
| test harness prints | bytes over a serial link, framed |

The one that reaches back into your code is **float vs double**. If the
filter moves to single precision, the variance `P` is the number to watch —
it can grow or shrink across many orders of magnitude, and single precision
has roughly 7 decimal digits to spend. Something to measure at B03, not to
pre-emptively design around.

Everything else stays: no dynamic allocation, no vendor headers, no STL
beyond `std::clamp`. That was the point of writing it this way.

---

# B04: back to Python

B04 is the measurement — truth versus estimate across the scenarios, and the
deliverable is a table. That runs in the simulation, in Python, on ground you
already know. No new syntax.

The only C++ you will touch is exporting profiles for the tests to read, and
that is `tools/` plumbing.

---

## Where the maths is

- `include/ekf.hpp` — the six equations and four named traps, beside the code
- `docs/ekf_formulas.pdf` — the same material typeset, with charts
- `docs/estimator_formulas.pdf` — the battery underneath it

The syntax is the easy half. Those are the hard half.
