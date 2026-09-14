"""
@file    docs/make_ekf_formulas.py
@brief   Typeset the B02 filter mathematics as a PDF reference sheet.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-14

@details
Renders docs/ekf_formulas.pdf — the six equations, where each term comes from,
what the gain is doing, and the one result that should be expected in advance
so it is not mistaken for a failure.

Companion to estimator_formulas.pdf: that sheet is the PLANT (what the battery
does), this one is the FILTER (what to infer from it).

    .venv/bin/python docs/make_ekf_formulas.py

@note Every number is computed from this project's own constants at import
    time, so the sheet cannot drift from config.py.
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

from config import (BATTERY_CAPACITY_WH, BATTERY_MAX_DISCHARGE_POWER_W,  # noqa: E402
                    BATTERY_DISCHARGE_EFFICIENCY, BATTERY_R_INTERNAL_OHM,
                    CELLS_SERIES, CURRENT_SENSOR_BIAS_A, LUNAR_NIGHT_HOURS,
                    OCV_POLY_NMC, USER_BUS_VOLTAGE_V, VOLTAGE_SENSOR_NOISE_V)

V_NOM = 3.70 * CELLS_SERIES
Q_AH = BATTERY_CAPACITY_WH / V_NOM
I_RATED = BATTERY_MAX_DISCHARGE_POWER_W / USER_BUS_VOLTAGE_V


def ocv(z):
    x = 2.0 * z - 1.0
    r = 0.0
    for c in reversed(OCV_POLY_NMC):
        r = r * x + c
    return r * CELLS_SERIES


def docv(z, h=1e-6):
    return (ocv(z + h) - ocv(z - h)) / (2 * h)


def _axes(ax):
    ax.set_facecolor(SURFACE)
    ax.tick_params(colors=INK_SOFT, labelsize=7.5)
    ax.grid(True, color=INK_FAINT, linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK_FAINT)


RUN_AMPS = 40.0
RUN_STEPS = 1800
RUN_DT = 60.0
RUN_HOURS = RUN_STEPS * RUN_DT / 3600.0


def simulate(bias_a, filtered, steps=RUN_STEPS, dt=RUN_DT, amps=RUN_AMPS,
             q_proc=1e-9, start=0.90):
    """Truth and estimate across a steady discharge. Pure Python, no numpy.

    The current and window are chosen so the pack stays INSIDE the fitted
    range. At 150 A a 1689 Ah pack is empty in 11.3 h, and the first version
    of this sheet ran 15 h — walking the truth past zero and evaluating the
    OCV polynomial well outside the data it was fitted to.
    """
    truth, z, P = start, start, 1e-6
    r_meas = VOLTAGE_SENSOR_NOISE_V ** 2
    ts, err = [], []
    for k in range(steps):
        truth -= BATTERY_DISCHARGE_EFFICIENCY * amps * dt / (3600 * Q_AH)
        v_true = ocv(truth) - amps * BATTERY_R_INTERNAL_OHM
        # predict, on the BIASED current the sensor reports
        z -= BATTERY_DISCHARGE_EFFICIENCY * (amps + bias_a) * dt / (3600 * Q_AH)
        P += q_proc
        if filtered:
            H = docv(z)
            v_pred = ocv(z) - (amps + bias_a) * BATTERY_R_INTERNAL_OHM
            K = P * H / (H * H * P + r_meas)
            z += K * (v_true - v_pred)
            P = (1 - K * H) * P
        if truth < 0.05:
            raise ValueError(
                f"truth fell to {truth:.3f}, outside the fitted OCV range — "
                "lower `amps` or shorten the window")
        ts.append(k * dt / 3600.0)
        err.append((z - truth) * 100.0)
    return ts, err


def draw_bounded(ax):
    """The point of the exercise: unbounded drift becomes bounded error."""
    ts, raw = simulate(CURRENT_SENSOR_BIAS_A, filtered=False)
    _, filt = simulate(CURRENT_SENSOR_BIAS_A, filtered=True)
    ax.plot(ts, raw, color=CRITICAL, linewidth=2.2,
            label="coulomb counting alone")
    ax.plot(ts, filt, color=ACCENT, linewidth=2.2, label="EKF")
    ax.axhline(0, color=INK, linewidth=1.0)
    ax.annotate(f"{raw[-1]:+.1f} %", (ts[-1], raw[-1]),
                xytext=(-6, 8), textcoords="offset points",
                fontsize=8, color=CRITICAL, ha="right", va="bottom")
    ax.annotate(f"EKF settles near {filt[-1]:+.2f} %", (ts[-1] * 0.5, filt[-1]),
                xytext=(0, 10), textcoords="offset points",
                fontsize=7.5, color=ACCENT, ha="center", va="bottom")
    ax.margins(y=0.18)
    ax.set_xlabel("hours of steady discharge", fontsize=8, color=INK_SOFT)
    ax.set_ylabel("estimate − truth  [% SoC]", fontsize=8, color=INK_SOFT)
    ax.set_xlim(0, ts[-1])
    ax.legend(loc="lower left", frameon=False, fontsize=7.5, labelcolor=INK_SOFT)
    _axes(ax)


def draw_gain(ax):
    """K against the curve's slope — why chemistry beats instrumentation."""
    zs = [0.05 + 0.95 * i / 400 for i in range(401)]
    r_meas = VOLTAGE_SENSOR_NOISE_V ** 2
    for P_val, colour, style in ((1e-4, ACCENT, "-"), (1e-6, "#d67510", "-"),
                                 (1e-8, CRITICAL, "-")):
        ks = [P_val * docv(z) / (docv(z) ** 2 * P_val + r_meas) for z in zs]
        ax.semilogy([z * 100 for z in zs], ks, color=colour, linewidth=2.0,
                    linestyle=style, label=f"P = {P_val:.0e}")
    ax.set_xlabel("state of charge  [%]", fontsize=8, color=INK_SOFT)
    ax.set_ylabel("Kalman gain  K", fontsize=8, color=INK_SOFT)
    ax.set_xlim(5, 100)
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi * 3.0)
    ax.legend(loc="upper right", frameon=False, fontsize=7.5, ncol=3,
              labelcolor=INK_SOFT, title="confidence", title_fontsize=7.5)
    _axes(ax)


def plot(sheet, fn, height=0.20, caption=None):
    if caption:
        sheet.note(caption, indent=0.045)
        sheet.y -= 0.006
    ax = sheet.fig.add_axes([LEFT + 0.045, sheet.y - height,
                             RIGHT - LEFT - 0.09, height])
    fn(ax)
    sheet.y -= height + 0.045


# ============================================================================

def page_one():
    s = Sheet()
    s.title("The filter",
            "B02 — inferring a charge nobody can measure, from a voltage and "
            "a current that both lie.")

    s.heading("What a Kalman filter is")
    s.body("A weighted average between something you PREDICTED and something you")
    s.body("MEASURED, weighted by how much you trust each. Everything else is")
    s.body("bookkeeping for those weights.")
    s.space(0.006)
    s.body("You are walking a corridor with your eyes shut, counting paces. "
           "Counting is", colour=INK_SOFT)
    s.body("smooth and precise over a few steps, but the error grows without "
           "bound — you", colour=INK_SOFT)
    s.body("will never notice you are drifting left. Occasionally you open your "
           "eyes and", colour=INK_SOFT)
    s.body("glimpse a doorway through fog: blurry, but it does not drift.",
           colour=INK_SOFT)
    s.space(0.004)
    for a, b in (("counting paces", "coulomb counting — smooth, drifts on bias"),
                 ("glimpsing the door", "terminal voltage — noisy, but anchored")):
        s.fig.text(LEFT + 0.03, s.y, a, fontsize=9.5, color=INK, va="top")
        s.fig.text(LEFT + 0.26, s.y, b, fontsize=9.5, color=INK_SOFT, va="top")
        s.y -= 0.021

    s.rule()
    s.heading("The six lines")
    s.body("ONE state, so there are no matrices — all of it is scalar arithmetic.")
    s.space(0.008)

    x0 = LEFT + 0.045
    s.fig.text(LEFT + 0.01, s.y, "PREDICT", fontsize=9, color=ACCENT,
               weight="bold", va="top")
    s.y -= 0.026
    for expr, note in [
        (r"$\hat z^- = z - \dfrac{\eta\,I\,\Delta t}{3600\,Q}$",
         "where counting says you are"),
        (r"$P^- = P + Q_{proc}$", "and how much less sure you are for guessing"),
    ]:
        s.fig.text(x0, s.y, expr, fontsize=13, color=INK, va="top")
        s.fig.text(x0 + 0.30, s.y - 0.004, note, fontsize=8.5, color=INK_SOFT,
                   va="top")
        s.y -= 0.048

    s.space(0.004)
    s.fig.text(LEFT + 0.01, s.y, "CORRECT", fontsize=9, color=ACCENT,
               weight="bold", va="top")
    s.y -= 0.026
    for expr, note in [
        (r"$H = \dfrac{d\,\mathrm{OCV}}{dz}$",
         "the slope, at the PREDICTED state"),
        (r"$K = \dfrac{P^- H}{H^{2}P^- + R_{meas}}$",
         "how far to move toward the meter"),
        (r"$z = \hat z^- + K\,(V_{meas} - \hat V)$", "blend"),
        (r"$P = (1 - KH)\,P^-$", "confidence recovers"),
    ]:
        s.fig.text(x0, s.y, expr, fontsize=13, color=INK, va="top")
        s.fig.text(x0 + 0.30, s.y - 0.004, note, fontsize=8.5, color=INK_SOFT,
                   va="top")
        s.y -= 0.048

    s.footer(1, 3, "B02 filter")
    return s.fig


def page_two():
    s = Sheet()
    s.title("2.  The gain, and what 'extended' means",
            "K is the only interesting quantity. Everything else serves it.")

    s.math(r"K = \frac{P H}{H^{2} P + R_{meas}}", size=15)
    s.body("Near 0, the filter ignores the voltmeter. Near 1, it follows it "
           "completely.")
    s.body("Between, it weighs evidence — which is the entire behaviour worth "
           "having.")

    s.space(0.006)
    s.heading("Why the chemistry outranks the instrument")
    s.body(r"$H$ is the OCV slope. As $H \to 0$, the numerator vanishes faster "
           "than the")
    s.body("denominator and the gain collapses:")
    s.math(r"H \to 0 \quad\Longrightarrow\quad K \to 0", size=14)
    s.body("A flat curve means the filter learns NOTHING from a measurement, "
           "however", colour=CRITICAL)
    s.body("good the voltmeter. That is not a tuning problem — it is the "
           "chemistry, and", colour=CRITICAL)
    s.body("it is why LFP estimators are known to diverge.", colour=CRITICAL)

    s.space(0.008)
    plot(s, draw_gain, height=0.20,
         caption="Gain across the charge range. A less certain filter "
                 "(larger P) leans harder on the meter.")

    s.rule()
    s.heading("What the E in EKF is doing")
    s.body("The measurement is a NONLINEAR function of the state — the OCV "
           "curve — so it")
    s.body("is linearised at each step by taking its slope at the current "
           "estimate.")
    s.math(r"V = \mathrm{OCV}(z) - IR \quad\longrightarrow\quad "
           r"H = \left.\frac{\partial V}{\partial z}\right|_{\hat z^-}", size=13)
    s.body(r"$H$ IS the extension. That is the whole difference from a plain "
           "Kalman filter,")
    s.body("and the reason the slope has been the thread through all of this.")

    s.footer(2, 3, "B02 filter")
    return s.fig


def page_three():
    s = Sheet()
    s.title("3.  What to expect",
            "Recorded in advance, so the result is not mistaken for a failure.")

    s.note("A positive current bias over-reports the discharge, so the estimate "
           "falls FASTER")
    s.note("than the truth and the error is negative throughout.")
    s.space(0.008)
    s.body("The bias is NOT in the state vector. This filter has one state, "
           "the charge,")
    s.body("so it has nothing to estimate the bias WITH — and it will not "
           "remove it.")
    s.space(0.006)
    s.body("What it will do is reach equilibrium, where the voltage correction "
           "each")
    s.body("step exactly cancels the drift the biased current injected. The "
           "error stops")
    s.body("growing and stays put.")

    s.space(0.008)
    ts, raw = simulate(CURRENT_SENSOR_BIAS_A, filtered=False)
    _, filt = simulate(CURRENT_SENSOR_BIAS_A, filtered=True)
    plot(s, draw_bounded, height=0.20,
         caption=f"A {CURRENT_SENSOR_BIAS_A:.1f} A bias on a "
                 f"{Q_AH:.0f} Ah pack, {RUN_AMPS:.0f} A steady discharge.")

    s.body("UNBOUNDED drift becomes BOUNDED error. That is the finding — not "
           "that the",
           colour=ACCENT)
    s.body("estimate is perfect, but that it stops getting worse.", colour=ACCENT)

    s.space(0.006)
    rows = [("", f"after {RUN_HOURS:.0f} h",
             f"over one {LUNAR_NIGHT_HOURS:.0f} h night"),
            ("coulomb counting", f"{raw[-1]:+.1f} %",
             f"{-CURRENT_SENSOR_BIAS_A*LUNAR_NIGHT_HOURS/Q_AH*100:+.0f} % and falling"),
            ("EKF", f"{filt[-1]:+.2f} %", "bounded — it stops here")]
    for i, (a, b, c) in enumerate(rows):
        w = "bold" if i == 0 else "normal"
        sz = 8.5 if i == 0 else 10
        col = INK_SOFT if i == 0 else INK
        s.fig.text(LEFT + 0.03, s.y, a, fontsize=sz, color=col, weight=w, va="top")
        s.fig.text(LEFT + 0.28, s.y, b, fontsize=sz,
                   color=CRITICAL if i == 1 else col, weight=w, va="top")
        s.fig.text(LEFT + 0.48, s.y, c, fontsize=sz,
                   color=CRITICAL if i == 1 else col, weight=w, va="top")
        s.y -= 0.024

    s.space(0.008)
    s.rule()
    s.heading("If the residual is too large")
    s.body("The fix is NOT better sensors and NOT more tuning. It is to give "
           "the filter")
    s.body(r"the bias to estimate — a second state, $[\,z,\;b_I\,]$, which "
           "makes it a 2x2")
    s.body("problem and lets the filter drive the residual toward zero. Serious "
           "battery")
    s.body(r"management does the same thing with $R$, for the same reason.")
    s.space(0.004)
    s.body("Do not do it first. But recognise the symptom when you see it.",
           colour=INK_SOFT)

    s.space(0.010)
    s.rule()
    s.note("Sources: Plett, G. L. (2004), 'Extended Kalman filtering for battery")
    s.note("management systems of LiPB-based HEV battery packs', Parts 1-3,")
    s.note("J. Power Sources 134(2):262-276. Every number here is computed from")
    s.note("this project's own config.py. Regenerate with docs/make_ekf_formulas.py.")

    s.footer(3, 3, "B02 filter")
    return s.fig


def main():
    pages = [page_one(), page_two(), page_three()]
    path = os.path.join(HERE, "ekf_formulas.pdf")
    with PdfPages(path) as pdf:
        for fig in pages:
            pdf.savefig(fig, facecolor=SURFACE)
    for i, fig in enumerate(pages, 1):
        fig.savefig(os.path.join(HERE, f"_ekf_preview_{i}.png"), dpi=110,
                    facecolor=SURFACE)
        plt.close(fig)
    print(f"  wrote {os.path.relpath(path, ROOT)}")
    print(f"  {os.path.getsize(path)/1024:.1f} KB, {len(pages)} pages")


if __name__ == "__main__":
    main()
