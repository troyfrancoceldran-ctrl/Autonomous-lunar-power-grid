# C++ for someone who writes Python

Author: Troy Celdran, with JARVIS (Claude Opus 5) as co-author
Written 2026-09-14, for B02.

Not a C++ tutorial. This is the *specific* subset needed to write
`docv_dsoc` and `Ekf::update`, and the traps that will actually fire while
you do. Everything else about the language can wait.

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

## Where the maths is

- `include/ekf.hpp` — the six equations and four named traps, beside the code
- `docs/ekf_formulas.pdf` — the same material typeset, with charts
- `docs/estimator_formulas.pdf` — the battery underneath it

The syntax is the easy half. Those are the hard half.
