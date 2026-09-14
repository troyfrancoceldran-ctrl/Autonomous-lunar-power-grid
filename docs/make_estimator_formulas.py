"""
@file    docs/make_estimator_formulas.py
@brief   Typeset the B01 mathematics as a PDF reference sheet.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-14

@details
Renders docs/estimator_formulas.pdf — the equations behind giving the battery
terminals, and the arithmetic that decides how they should be modelled.

Every figure in it is DERIVED FROM THIS PROJECT'S OWN CONSTANTS rather than
quoted from a paper. The literature agrees, and where it does the sheet says
so, but the numbers are the outpost's.

    .venv/bin/python docs/make_estimator_formulas.py

@note Reuses the Sheet layout engine from make_protection_formulas.py so the
    two reference sheets are one document family. No LaTeX required —
    matplotlib's mathtext does the typesetting.
@note Also writes PNG previews, because a PDF cannot be eyeballed from a
    terminal and the last sheet shipped with three layout collisions that only
    looking caught.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from make_protection_formulas import (                # noqa: E402
    Sheet, LEFT, RIGHT, INK, INK_SOFT, INK_FAINT, ACCENT, CRITICAL, SURFACE)

from config import (BATTERY_CAPACITY_WH, BATTERY_MAX_DISCHARGE_POWER_W,   # noqa: E402
                    USER_BUS_VOLTAGE_V, LUNAR_NIGHT_HOURS)

# --- the pack, and the two candidate chemistries ----------------------------
CELLS_SERIES = 32
V_NOM = 3.70 * CELLS_SERIES                 # 118.4 V
Q_AH = BATTERY_CAPACITY_WH / V_NOM          # 1689 Ah
I_RATED = BATTERY_MAX_DISCHARGE_POWER_W / USER_BUS_VOLTAGE_V   # 417 A
R_PACK = 0.015                              # ohm

NMC = [(0.00, 3.00), (0.10, 3.45), (0.20, 3.55), (0.30, 3.620), (0.40, 3.680),
       (0.50, 3.730), (0.60, 3.800), (0.70, 3.880), (0.80, 3.970),
       (0.90, 4.070), (1.00, 4.20)]
LFP = [(0.00, 2.50), (0.05, 3.10), (0.10, 3.200), (0.20, 3.250), (0.30, 3.265),
       (0.40, 3.272), (0.50, 3.278), (0.60, 3.282), (0.70, 3.288),
       (0.80, 3.300), (0.90, 3.340), (0.95, 3.400), (1.00, 3.65)]


def ocv_cell(table, z):
    """Linear interpolation between breakpoints — the recommended form."""
    for i in range(len(table) - 1):
        (z0, v0), (z1, v1) = table[i], table[i + 1]
        if z0 <= z <= z1:
            return v0 + (v1 - v0) * (z - z0) / (z1 - z0)
    return table[-1][1]


def slope_mv_per_pct(table, lo, hi):
    return (ocv_cell(table, hi) - ocv_cell(table, lo)) * 1000.0 / ((hi - lo) * 100.0)


NMC_SLOPE = slope_mv_per_pct(NMC, 0.30, 0.70)
LFP_SLOPE = slope_mv_per_pct(LFP, 0.30, 0.70)
DV_R = I_RATED * R_PACK * 0.10              # 10 % error in R, at rated current


def _axes(ax):
    ax.set_facecolor(SURFACE)
    ax.tick_params(colors=INK_SOFT, labelsize=7.5)
    ax.grid(True, color=INK_FAINT, linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK_FAINT)


def draw_ocv(ax):
    """Pack OCV against state of charge, both chemistries."""
    zs = [i / 400 for i in range(401)]
    ax.plot([z * 100 for z in zs], [ocv_cell(NMC, z) * CELLS_SERIES for z in zs],
            color=ACCENT, linewidth=2.2, label="NMC / NCA")
    ax.plot([z * 100 for z in zs], [ocv_cell(LFP, z) * CELLS_SERIES for z in zs],
            color=CRITICAL, linewidth=2.2, label="LFP")
    ax.axvspan(30, 70, color=INK_FAINT, alpha=0.35, zorder=0)
    ax.annotate("the working range", (50, 88), ha="center", fontsize=7.5,
                color=INK_SOFT)
    ax.set_xlabel("state of charge  [%]", fontsize=8, color=INK_SOFT)
    ax.set_ylabel("pack OCV  [V]", fontsize=8, color=INK_SOFT)
    ax.set_xlim(0, 100)
    ax.set_ylim(78, 140)
    ax.legend(loc="lower right", frameon=False, fontsize=7.5, labelcolor=INK_SOFT)
    _axes(ax)


def draw_slope(ax):
    """dOCV/dz — the quantity that decides whether SoC is observable."""
    pts = [i / 200 for i in range(1, 200)]
    def slope(tbl, z):
        h = 0.005
        return abs(ocv_cell(tbl, min(1, z + h)) - ocv_cell(tbl, max(0, z - h))) \
               * 1000 * CELLS_SERIES / ((min(1, z + h) - max(0, z - h)) * 100)
    ax.semilogy([z * 100 for z in pts], [slope(NMC, z) for z in pts],
                color=ACCENT, linewidth=2.2, label="NMC / NCA")
    ax.semilogy([z * 100 for z in pts], [slope(LFP, z) for z in pts],
                color=CRITICAL, linewidth=2.2, label="LFP")
    ax.axhline(DV_R * 1000, color=INK, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.annotate(f"{DV_R*1000:.0f} mV — the error a 10 % mistake in $R$ causes\n"
                "at rated current. Below this line the IR drop is\n"
                "bigger than a whole percent of charge.",
                (24, 1500), fontsize=7, color=INK)
    ax.set_xlabel("state of charge  [%]", fontsize=8, color=INK_SOFT)
    ax.set_ylabel("|dOCV/dz|  [mV per %SoC]", fontsize=8, color=INK_SOFT)
    ax.set_xlim(0, 100)
    ax.set_ylim(1.5, 5000)
    ax.legend(loc="lower center", ncol=2, frameon=False, fontsize=7.5,
              labelcolor=INK_SOFT)
    _axes(ax)


def draw_drift(ax):
    """Coulomb-count drift across one lunar night, for three sensor biases."""
    hours = list(range(0, int(LUNAR_NIGHT_HOURS) + 1, 2))
    for pct, colour, style in ((0.1, ACCENT, "-"), (0.5, "#d67510", "-"),
                               (1.0, CRITICAL, "-")):
        bias = I_RATED * pct / 100
        ax.plot(hours, [bias * h / Q_AH * 100 for h in hours],
                color=colour, linewidth=2.0, linestyle=style,
                label=f"{pct} % of rated  ({bias:.2f} A)")
    ax.axhline(100, color=INK, linewidth=1.0, linestyle=(0, (4, 3)))
    ax.annotate("a full pack of error", (232, 103), fontsize=7.5, color=INK_SOFT)
    ax.set_xlabel("hours into the lunar night", fontsize=8, color=INK_SOFT)
    ax.set_ylabel("accumulated SoC error  [%]", fontsize=8, color=INK_SOFT)
    ax.set_xlim(0, LUNAR_NIGHT_HOURS)
    ax.set_ylim(0, 115)
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.86), frameon=False,
              fontsize=7.5, labelcolor=INK_SOFT,
              title="current-sensor bias", title_fontsize=7.5)
    _axes(ax)


def plot(sheet, fn, height=0.20, caption=None):
    if caption:
        sheet.note(caption, indent=0.045)
        sheet.y -= 0.006
    ax = sheet.fig.add_axes([LEFT + 0.045, sheet.y - height,
                             RIGHT - LEFT - 0.09, height])
    fn(ax)
    sheet.y -= height + 0.045
    return ax


# ============================================================================

def page_one():
    s = Sheet()
    s.title("Estimator mathematics",
            "B01 — giving the battery terminals, so there is something to "
            "measure rather than a state to read.")

    s.heading("Symbols")
    for sym, desc, unit in [
        (r"$z$", "state of charge, in [0, 1]", "–"),
        (r"$\mathrm{OCV}(z)$", "open-circuit voltage at that charge", "V"),
        (r"$I$", "pack current, POSITIVE discharging", "A"),
        (r"$R$", "internal resistance", r"$\Omega$"),
        (r"$V$", "terminal voltage — what a voltmeter reads", "V"),
        (r"$Q$", "usable charge capacity", "Ah"),
        (r"$\eta$", "coulombic efficiency", "–"),
        (r"$b_I$", "current-sensor BIAS — the term that matters", "A"),
    ]:
        s.fig.text(LEFT + 0.02, s.y, sym, fontsize=10.5, color=INK, va="top")
        s.fig.text(LEFT + 0.20, s.y, desc, fontsize=9.5, color=INK_SOFT, va="top")
        s.fig.text(RIGHT, s.y, unit, fontsize=9.5, color=INK_FAINT,
                   va="top", ha="right")
        s.y -= 0.0205

    s.rule()
    s.heading("1.  The plant")
    s.body("A battery hides its charge. What it exposes is a voltage, pulled "
           "down by")
    s.body("whatever current is being drawn through its own resistance:")
    s.math(r"V = \mathrm{OCV}(z) \;-\; I\,R")
    s.body("That single term is what makes estimation hard rather than "
           "arithmetic. A")
    s.body("heavy discharge LOOKS like a low state of charge, and separating "
           "the two is")
    s.body("the filter's entire job.")

    s.space(0.006)
    s.body("Charge itself moves by integration — coulomb counting:")
    s.math(r"\frac{dz}{dt} = -\frac{\eta\,I}{3600\,Q}"
           r"\qquad\Longrightarrow\qquad"
           r"z_{k+1} = z_k - \frac{\eta\,I_k\,\Delta t}{3600\,Q}", size=13)
    s.note("Δt in seconds, Q in amp-hours, hence the 3600.")

    s.space(0.008)
    plot(s, draw_ocv, height=0.185,
         caption="Pack OCV for the two candidate chemistries, 32 cells in series. "
                 "The shaded band is where the outpost actually lives.")

    s.footer(1, 4, "B01 estimator")
    return s.fig


def page_two():
    s = Sheet()
    s.title("2.  Choosing the OCV curve",
            "Five ways to write OCV(z), and why the least clever one wins here.")

    s.body("Analytic forms, in rough order of how often they appear in the "
           "literature:")
    s.space(0.008)
    x0 = LEFT + 0.03
    for name, expr, note, drop in [
        ("Polynomial", r"$\mathrm{OCV}(z)=\sum_{i=0}^{n} a_i z^{i}$",
         "fits anything; monotonicity not guaranteed", 0.044),
        ("Shepherd", r"$\mathrm{OCV}(z)=E_0-\frac{K}{z}+A e^{-Bz}$",
         r"diverges as $z\to0$", 0.032),
        ("Nernst", r"$\mathrm{OCV}(z)=E_0+K_1\ln z+K_2\ln(1-z)$",
         r"diverges at BOTH ends", 0.032),
        ("Plett combined",
         r"$\mathrm{OCV}(z)=K_0-\frac{K_1}{z}-K_2 z+K_3\ln z+K_4\ln(1-z)$",
         "accurate mid-range; same endpoint problem", 0.036),
        ("Lookup + linear", r"$\mathrm{OCV}(z)$ interpolated between breakpoints",
         "monotonic by construction", 0.030),
    ]:
        # The note goes BELOW the equation, not beside it, and each row states
        # its own drop: the polynomial's summation carries a lower limit that
        # reaches much further down than the other four expressions do.
        s.fig.text(x0, s.y, name, fontsize=9.5, color=INK, va="top", weight="bold")
        s.fig.text(x0 + 0.17, s.y - 0.004, expr, fontsize=11, color=INK, va="top")
        s.fig.text(x0, s.y - drop, note, fontsize=8, color=INK_SOFT, va="top")
        s.y -= drop + 0.022

    s.space(0.004)
    s.heading("Take the lookup table")
    s.body("Not because it is simpler, but because three of its properties are "
           "load-bearing here:")
    s.space(0.004)
    s.body("• MONOTONIC BY CONSTRUCTION. Check the breakpoints once and the "
           "curve can", indent=0.02)
    s.body("never fold back on itself. A fitted polynomial can, and where it "
           "does, SoC", indent=0.035)
    s.body("becomes ambiguous — two charges, one voltage.", indent=0.035)
    s.space(0.004)
    s.body("• NO ENDPOINT DIVERGENCE. Every analytic form above except the "
           "polynomial", indent=0.02)
    s.body(r"carries a $\ln z$ or a $1/z$. This pack's floor is $z=0.05$, "
           "close enough to", indent=0.035)
    s.body("the singularity that the fit is doing its worst work exactly where "
           "the", indent=0.035)
    s.body("outpost spends 277 hours of every 354-hour night.", indent=0.035)
    s.space(0.004)
    s.body("• IT PORTS. A const array and two multiplies cross-compile to an "
           "ESP32", indent=0.02)
    s.body(r"without a $\ln$ in sight, and swapping NMC for LFP is swapping a "
           "table.", indent=0.035)

    s.space(0.008)
    s.rule()
    s.body("Whichever form you take, one property is not optional:")
    s.math(r"\frac{d\,\mathrm{OCV}}{dz} > 0 \quad \mathrm{everywhere}", size=13)
    s.body("Page 4 is about what happens when it is merely small.")

    s.footer(2, 4, "B01 estimator")
    return s.fig


def page_three():
    s = Sheet()
    s.title("3.  Why a filter at all",
            "Two ways to know the charge. Both wrong, and wrong differently.")

    s.body("With perfect instruments the terminal equation inverts and no "
           "filter is needed:")
    s.math(r"z = \mathrm{OCV}^{-1}\!\left(V + I R\right)", size=13)
    s.body("Instruments are not perfect, and the two available methods fail in "
           "opposite")
    s.body("directions — which is precisely what makes them worth fusing.")

    s.space(0.006)
    s.heading("Coulomb counting — precise, and biased")
    s.body("Integrating current is exact over short intervals. But a sensor "
           "BIAS integrates")
    s.body("too, and never washes out:")
    s.math(r"\varepsilon_z(t) = \frac{b_I\,t}{3600\,Q}", size=13)
    s.body(f"With Q = {Q_AH:.0f} Ah and a bias of just 0.5 % of the "
           f"{I_RATED:.0f} A rating:")

    s.space(0.004)
    plot(s, draw_drift, height=0.185,
         caption="Drift across one lunar night. A straight line with no "
                 "restoring force — nothing recovers it.")

    s.body(f"A 0.5 % bias reaches {I_RATED*0.005*LUNAR_NIGHT_HOURS/Q_AH*100:.0f} % "
           "SoC error by dawn. The controller would", colour=CRITICAL)
    s.body("shed life support on a pack that was nearly full, or fail to shed "
           "on one", colour=CRITICAL)
    s.body("that was nearly empty.", colour=CRITICAL)

    s.space(0.006)
    s.heading("Voltage inversion — unbiased, and blunt")
    s.body("Reading charge from voltage has no memory, so no drift. Its error "
           "is instead")
    s.body(r"whatever error sits in $V$ and $IR$, divided by the curve's slope:")
    s.math(r"\varepsilon_z = \frac{\Delta V + I\,\Delta R}"
           r"{d\,\mathrm{OCV}/dz}", size=13)
    s.body("An EKF runs coulomb counting as its PREDICT step and voltage as "
           "its CORRECT")
    s.body("step, so the drift is continually anchored by a measurement that "
           "cannot drift.")

    s.footer(3, 4, "B01 estimator")
    return s.fig


def page_four():
    s = Sheet()
    s.title("4.  Observability",
            "The slope of the curve is not a detail. It is the whole question.")

    s.body("The measurement Jacobian — how much the predicted voltage moves "
           "when the")
    s.body("estimated charge moves — is just the curve's slope:")
    s.math(r"H = \frac{\partial V}{\partial z} = "
           r"\frac{d\,\mathrm{OCV}}{dz}", size=14)
    s.body("and the Kalman gain carries it:")
    s.math(r"K = \frac{P\,H}{H^{2}P + R_v}"
           r"\qquad\Longrightarrow\qquad H \to 0 \;\Rightarrow\; K \to 0", size=13)
    s.body("A flat curve means the filter learns nothing from a measurement, "
           "no matter")
    s.body("how good the voltmeter is. This is not a tuning problem. It is the "
           "chemistry.", colour=CRITICAL)

    s.space(0.008)
    plot(s, draw_slope, height=0.185,
         caption="Pack-level slope, log scale. LFP's plateau sits an order of "
                 "magnitude below NMC's across the entire working range.")

    s.rule()
    s.heading("The same filter, two chemistries")
    s.body(f"Measured from this project's own constants — {CELLS_SERIES}S pack, "
           f"{I_RATED:.0f} A rated,")
    s.body(f"{R_PACK*1000:.0f} mΩ, and a 10 % uncertainty in R (a "
           f"{DV_R*1000:.0f} mV error at rated current):")
    s.space(0.006)
    rows = [("", "slope, mid-range", "SoC error"),
            ("NMC / NCA", f"{NMC_SLOPE*CELLS_SERIES:.0f} mV/%SoC",
             f"{DV_R*1000/(NMC_SLOPE*CELLS_SERIES):.1f} %"),
            ("LFP", f"{LFP_SLOPE*CELLS_SERIES:.0f} mV/%SoC",
             f"{DV_R*1000/(LFP_SLOPE*CELLS_SERIES):.0f} %")]
    for i, (a, b, c) in enumerate(rows):
        weight = "bold" if i == 0 else "normal"
        size = 8.5 if i == 0 else 10
        colour = INK_SOFT if i == 0 else INK
        s.fig.text(LEFT + 0.03, s.y, a, fontsize=size, color=colour,
                   weight=weight, va="top")
        s.fig.text(LEFT + 0.26, s.y, b, fontsize=size, color=colour,
                   weight=weight, va="top")
        s.fig.text(LEFT + 0.52, s.y, c, fontsize=size,
                   color=CRITICAL if i == 2 else colour, weight=weight, va="top")
        s.y -= 0.024

    s.space(0.006)
    s.body("An eleven-fold difference, from the curve alone. The literature "
           "reports the")
    s.body("same shape of result — roughly 8 % against 49 % — and LFP "
           "estimators are known")
    s.body("to diverge for exactly this reason.")

    s.space(0.008)
    s.rule()
    s.note("Sources: Plett, G. L. (2004), 'Extended Kalman filtering for battery")
    s.note("management systems of LiPB-based HEV battery packs', Parts 1-3,")
    s.note("J. Power Sources 134(2):262-276. Slope figures cross-checked against")
    s.note("published NMC and LFP OCV characterisations. Regenerate this sheet with")
    s.note("docs/make_estimator_formulas.py.")

    s.footer(4, 4, "B01 estimator")
    return s.fig


def main():
    pages = [page_one(), page_two(), page_three(), page_four()]
    path = os.path.join(HERE, "estimator_formulas.pdf")
    with PdfPages(path) as pdf:
        for fig in pages:
            pdf.savefig(fig, facecolor=SURFACE)
    for i, fig in enumerate(pages, 1):
        fig.savefig(os.path.join(HERE, f"_est_preview_{i}.png"), dpi=110,
                    facecolor=SURFACE)
        plt.close(fig)
    print(f"  wrote {os.path.relpath(path, ROOT)}")
    print(f"  {os.path.getsize(path)/1024:.1f} KB, {len(pages)} pages")


if __name__ == "__main__":
    main()
