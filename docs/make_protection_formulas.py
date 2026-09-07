"""
@file    docs/make_protection_formulas.py
@brief   Typeset the T04 mathematics as a PDF reference sheet.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-07

@details
Renders docs/protection_formulas.pdf from the same equations that live in
protection.py's docstring. No LaTeX distribution is required — matplotlib's
own mathtext engine handles the typesetting, and matplotlib is already a
dependency of this project, so the sheet can be regenerated anywhere the
simulation runs.

    .venv/bin/python docs/make_protection_formulas.py

@note Also writes PNG previews of each page beside the PDF, because a PDF
    cannot be eyeballed from a terminal and a formula sheet with a broken
    glyph in it is worse than no formula sheet.
@note mathtext is a SUBSET of LaTeX. No \\begin{cases}, no \\text{}, no
    tabular. Piecewise definitions are laid out as separate rows with a drawn
    brace, which is why this file does its own positioning.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# A4 portrait, and the light palette from visualization.py so the sheet and
# the figures look like one document.
PAGE = (8.27, 11.69)
INK = "#0b0b0b"
INK_SOFT = "#52514e"
INK_FAINT = "#c9c8c2"
ACCENT = "#1963a4"
CRITICAL = "#b13328"
SURFACE = "#fcfcfb"

LEFT = 0.09
RIGHT = 0.93


class Sheet:
    """A page with a top-down cursor. Every block advances it."""

    def __init__(self):
        self.fig = plt.figure(figsize=PAGE)
        self.fig.patch.set_facecolor(SURFACE)
        self.y = 0.955

    def _text(self, s, size, colour, weight="normal", x=LEFT, style="normal"):
        self.fig.text(x, self.y, s, fontsize=size, color=colour, weight=weight,
                    style=style, va="top", ha="left", wrap=False)

    def title(self, s, sub=None):
        self._text(s, 19, INK, weight="bold")
        self.y -= 0.030
        if sub:
            self._text(sub, 9.5, INK_SOFT)
            self.y -= 0.020
        self.rule()

    def heading(self, s):
        self.y -= 0.012
        self._text(s, 12, ACCENT, weight="bold")
        self.y -= 0.024

    def body(self, s, colour=INK, size=9.5, indent=0.0):
        self._text(s, size, colour, x=LEFT + indent)
        self.y -= 0.0175

    def note(self, s, indent=0.0):
        self.body(s, colour=INK_SOFT, size=8.8, indent=indent)

    def math(self, s, size=15, indent=0.045, colour=INK):
        """One display equation. `s` is mathtext WITHOUT the $ delimiters."""
        self.y -= 0.008
        self._text(f"${s}$", size, colour, x=LEFT + indent)
        self.y -= 0.034

    def mono(self, s, colour=INK_SOFT, size=8.6, indent=0.045):
        self.fig.text(LEFT + indent, self.y, s, fontsize=size, color=colour,
                      va="top", ha="left", family="monospace")
        self.y -= 0.016

    def plot(self, draw, height=0.19, caption=None):
        """An axes at the cursor. `draw(ax)` fills it; the cursor advances.

        The caption goes ABOVE the axes. Below, it has to clear both the
        x-label and the page footer, and page one has no room for that — the
        first attempt put it underneath and it ran off the bottom edge.
        """
        if caption:
            self.note(caption, indent=0.045)
            self.y -= 0.006
        ax = self.fig.add_axes([LEFT + 0.045, self.y - height,
                                RIGHT - LEFT - 0.09, height])
        ax.set_facecolor(SURFACE)
        ax.tick_params(colors=INK_SOFT, labelsize=7.5)
        ax.grid(True, color=INK_FAINT, linewidth=0.5, alpha=0.7, which="both")
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(INK_FAINT)
        draw(ax)
        self.y -= height + 0.045     # clears the axes x-label
        return ax

    def rule(self):
        self.y -= 0.006
        self.fig.add_artist(plt.Line2D([LEFT, RIGHT], [self.y, self.y],
                                    color=INK_FAINT, linewidth=0.8))
        self.y -= 0.018

    def space(self, amount=0.012):
        self.y -= amount

    def footer(self, page, total):
        self.fig.text(RIGHT, 0.035, f"{page} / {total}", fontsize=8,
                    color=INK_FAINT, ha="right")
        self.fig.text(LEFT, 0.035,
                    "lunar_microgrid_sim — T04 protection", fontsize=8,
                    color=INK_FAINT, ha="left")


def page_one():
    s = Sheet()
    s.title("Protection mathematics",
            "T04 — solid-state protection for a 120 VDC lunar microgrid.  "
            "Symbols used throughout protection.py.")

    s.heading("Symbols")
    for sym, desc, unit in [
        (r"$V$", "feeder nominal voltage", "V"),
        (r"$R(T)$", "feeder resistance at conductor temperature $T$", r"$\Omega$"),
        (r"$I_f$", "prospective fault current", "A"),
        (r"$I_r$", "rated continuous current", "A"),
        (r"$k$", "instantaneous trip multiple", "–"),
        (r"$I_{inst} = k\,I_r$", "instantaneous threshold", "A"),
        (r"$K$", "$I^2t$ rating — the let-through energy", r"$A^2s$"),
        (r"$t_{min}$", "minimum switching time", "s"),
        (r"$\Delta$", "coordination margin", "s"),
    ]:
        s.fig.text(LEFT + 0.02, s.y, sym, fontsize=10.5, color=INK, va="top")
        s.fig.text(LEFT + 0.19, s.y, desc, fontsize=9.5, color=INK_SOFT, va="top")
        s.fig.text(RIGHT, s.y, unit, fontsize=9.5, color=INK_FAINT,
                va="top", ha="right")
        s.y -= 0.0205

    s.rule()
    s.heading("1.  Prospective fault current")
    s.body("Bolted fault — zero fault resistance — at the far end of the feeder,")
    s.body("with the source treated as ideal, so this is an upper bound.")
    s.math(r"I_f(T) = \frac{V}{R(T)}")
    s.body("Expanded through the T01 resistance, with the round-trip length "
        r"$L_c = 2L$:")
    s.math(r"I_f(T) = \frac{V\,A}{\rho_{20}\,[\,1 + \alpha(T - T_{ref})\,]\cdot 2L}")

    s.body("The temperature ratio is where the finding lives. "
        r"$V$, $A$ and $L$ all cancel,")
    s.body("so the 6.28× swing belongs to the material, not to this outpost:")
    s.math(r"\frac{I_f(T_1)}{I_f(T_2)} = "
        r"\frac{1 + \alpha(T_2 - T_{ref})}{1 + \alpha(T_1 - T_{ref})}"
        r"\qquad\Rightarrow\qquad"
        r"\frac{I_f(100\,K)}{I_f(400\,K)} = \frac{1.4274}{0.22740} = 6.28")

    s.space(0.004)
    s.body("Worked — battery feeder, "
        r"$A = 36.81\,mm^2$, $L = 10\,m$, $V = 120\,V$, $T = 100\,K$:",
        colour=INK_SOFT)
    s.mono("R   = 6.026e-9 × 20 / 36.81e-6  =  3.274e-3 Ω")
    s.mono("I_f = 120 / 3.274e-3            =  36 650 A")
    s.space(0.006)
    s.body("That is 88× the feeder's 417 A rating. No mechanical contact opens",
        colour=CRITICAL)
    s.body("36 kA of direct current and is ever useful again.", colour=CRITICAL)

    s.space(0.010)
    s.plot(draw_fault_vs_temperature,
        caption="Battery feeder. Protection must be designed against the COLD "
                "case; losses against the hot one.")

    s.footer(1, 4)
    return s.fig


def page_two():
    s = Sheet()
    s.title("2.  The trip curve",
            "Three regions, and the order they are tested in is load-bearing.")

    s.body("Piecewise, tested in this order:")
    s.space(0.010)
    x0 = LEFT + 0.06
    rows = [
        (r"$t(I) = \infty$", r"$I \leq I_r$", "never trips"),
        (r"$t(I) = t_{min}$", r"$I \geq I_{inst} = k\,I_r$", "instantaneous"),
        (r"$t(I) = K\,/\,I^2$", "otherwise", r"$I^2t$ overload"),
    ]
    brace_top = s.y + 0.004
    for expr, cond, label in rows:
        s.fig.text(x0, s.y, expr, fontsize=13, color=INK, va="top")
        s.fig.text(x0 + 0.26, s.y, cond, fontsize=11.5, color=INK_SOFT, va="top")
        s.fig.text(x0 + 0.50, s.y, label, fontsize=9, color=INK_FAINT, va="top")
        s.y -= 0.042
    brace_bottom = s.y + 0.030
    s.fig.add_artist(plt.Line2D([x0 - 0.020, x0 - 0.020],
                                [brace_bottom, brace_top],
                                color=INK_FAINT, linewidth=1.4))

    s.space(0.010)
    s.body("The curve is DISCONTINUOUS at "
        r"$I_{inst}$, and deliberately so — the two")
    s.body("regions are different physical mechanisms. With the shipped constants:")
    s.math(r"\frac{K}{I_{inst}^{\,2}} = \frac{2000}{10^{6}} = 2\,ms"
        r"\qquad\longrightarrow\qquad t_{min} = 50\,\mu s")
    s.body("A 40× step down. That is exactly why the branch order matters: test")
    s.body(r"$I \geq I_{inst}$ BEFORE falling through to $K/I^2$, or a dead short is")
    s.body("quoted a trip time the hardware cannot achieve.", colour=CRITICAL)

    s.space(0.008)
    s.plot(draw_trip_curve, height=0.26,
        caption="A 100 A device. The vertical drop at $I_{inst}$ is the "
                "discontinuity, and it is deliberate.")

    s.footer(2, 4)
    return s.fig


def page_three():
    s = Sheet()
    s.title("3.  Let-through energy",
            "Whether the CABLE survives, as opposed to whether the device noticed.")
    x0 = LEFT + 0.06

    s.math(r"E(I) = I^{2}\,t(I)")
    s.body("which by region collapses to:")
    s.space(0.008)
    for expr, cond, label in [
        (r"$E(I) = \infty$", r"$I \leq I_r$", "not protecting anything"),
        (r"$E(I) = K$", r"$I_r < I < I_{inst}$", "flat — the definition"),
        (r"$E(I) = I^{2}\,t_{min}$", r"$I \geq I_{inst}$", r"grows as $I^2$"),
    ]:
        s.fig.text(x0, s.y, expr, fontsize=12.5, color=INK, va="top")
        s.fig.text(x0 + 0.26, s.y, cond, fontsize=11, color=INK_SOFT, va="top")
        s.fig.text(x0 + 0.50, s.y, label, fontsize=9, color=INK_FAINT, va="top")
        s.y -= 0.040

    s.space(0.006)
    s.body("The middle line is an identity, not a coincidence:")
    s.math(r"I^{2}\cdot\frac{K}{I^{2}} = K", size=12)
    s.body("which is what makes the flatness test a statement about what an")
    s.body(r"$I^2t$ device IS, rather than a value copied out of an implementation.")

    s.space(0.008)
    s.body("At the worst fault in this outpost:", colour=INK_SOFT)
    s.math(r"E = (36\,650)^{2}\times 50\times10^{-6} = 6.7\times10^{4}\;A^{2}s",
        size=12)
    s.body("against the adiabatic conductor withstand "
        r"$K_{cable} = k_c^{2}A^{2}$, with $k_c$")
    s.body("from IEC 60364-4-43 (aluminium runs roughly 76–94 with "
        r"$A$ in $mm^2$).")
    s.body(r"At $k_c = 94$ that is about $1.2\times10^{7}\,A^{2}s$ — "
        "two orders of margin.")
    s.body("The CABLE is fine. The DEVICE is the constraint.", colour=ACCENT)

    s.space(0.008)
    s.plot(draw_let_through, height=0.235,
        caption="Flat at $K$ while the device integrates; rising as $I^2$ once "
                "it can only switch as fast as it switches.")

    s.footer(3, 4)
    return s.fig


def page_four():
    s = Sheet()
    s.title("4.  Selectivity",
            "Zonal protection: the device nearest the fault opens, and nothing else.")

    s.math(r"\mathrm{selective}\;\Longleftrightarrow\;"
           r"t_{down}(I) + \Delta \;\leq\; t_{up}(I)")

    s.body(r"Substitute both devices in their $I^2t$ region and something falls out")
    s.body("that is worth more than the formula itself:")
    s.math(r"\frac{K_d}{I^{2}} + \Delta \;\leq\; \frac{K_u}{I^{2}}")
    s.math(r"\Longleftrightarrow\qquad I \;\leq\; \sqrt{\frac{K_u - K_d}{\Delta}}")

    s.space(0.008)
    s.rule()
    s.heading("The sting")
    s.body("build_protection gives every device the same "
           r"$K$, so $K_u - K_d = 0$ and the")
    s.body(r"bound collapses to $I \leq 0$.", colour=CRITICAL)
    s.space(0.006)
    s.body(r"Selectivity in the $I^2t$ region is NEVER achievable with identical",
           colour=CRITICAL)
    s.body("$I^2t$ ratings, however far apart the current ratings are.",
           colour=CRITICAL)
    s.space(0.010)
    s.body("So with the shipped constants, selectivity survives in exactly one band:")
    s.math(r"I_{r,down} \;<\; I \;\leq\; I_{r,up}")
    s.body("where the downstream device is tripping and the upstream one still reads")
    s.body(r"$\infty$, because the fault is below ITS rating. Above that band both are")
    s.body(r"in $I^2t$ with equal $K$ (equal times), or both are instantaneous (equal")
    s.body(r"$t_{min}$). Neither is selective.")
    s.space(0.008)
    s.body("That is a real design limitation, not a defect — and it is why practice")
    s.body(r"staggers the $I^2t$ ratings and not merely the current ratings.",
           colour=ACCENT)

    s.rule()
    s.heading("Check before you run")
    s.mono("upstream 400 A / downstream 50 A,  I = 500 A", colour=INK)
    s.mono("    t_up   = 2000 / 500²  = 8 ms")
    s.mono("    t_down = t_min        = 50 µs        ->  SELECTIVE")
    s.space(0.004)
    s.mono("upstream 100 A / downstream 100 A, I = 500 A", colour=INK)
    s.mono("    both   = 8 ms                        ->  not selective")
    s.space(0.004)
    s.mono("both instantaneous,                I = 100 kA", colour=INK)
    s.mono("    both   = 50 µs                       ->  not selective")

    s.space(0.014)
    s.rule()
    s.note("Sources: NASA NTRS 20250000763 (zonal protection, ISS RPCM 4.7 kg vs")
    s.note("AMPS module 0.5 kg); IEC 60364-4-43 for the adiabatic withstand")
    s.note("constant. Regenerate with docs/make_protection_formulas.py.")

    s.footer(4, 4)
    return s.fig


def main():
    pages = [page_one(), page_two(), page_three(), page_four()]
    pdf_path = os.path.join(HERE, "protection_formulas.pdf")
    with PdfPages(pdf_path) as pdf:
        for fig in pages:
            pdf.savefig(fig, facecolor=SURFACE)
    for i, fig in enumerate(pages, 1):
        fig.savefig(os.path.join(HERE, f"_formulas_preview_{i}.png"),
                    dpi=110, facecolor=SURFACE)
        plt.close(fig)
    print(f"wrote {pdf_path}")
    print(f"      {os.path.getsize(pdf_path) / 1024:.1f} KB, {len(pages)} pages")




# =============================================================================
# The curves. Computed from the equations above, NOT from protection.py, so
# the sheet renders whether or not T04 is implemented yet.
# =============================================================================

RHO20, ALPHA, TREF = 2.65e-8, 0.0040, 293.15
K_RATING, T_MIN, I_RATED, K_MULT = 2000.0, 50e-6, 100.0, 10.0


def _resistance(area_m2, length_m, temperature_k):
    rho = RHO20 * (1 + ALPHA * (temperature_k - TREF))
    return rho * 2 * length_m / area_m2


def _trip_time(current_a):
    if current_a <= I_RATED:
        return float("inf")
    if current_a >= I_RATED * K_MULT:
        return T_MIN
    return K_RATING / current_a ** 2


def draw_fault_vs_temperature(ax):
    """The battery feeder, 100 K to 400 K."""
    temps = [100 + i for i in range(301)]
    currents = [120.0 / _resistance(36.81e-6, 10.0, t) / 1000 for t in temps]
    ax.plot(temps, currents, color=ACCENT, linewidth=2.0)
    for t, label, colour in ((100, "night", CRITICAL), (293.15, "20 °C", INK_SOFT),
                             (400, "day", INK_SOFT)):
        i = 120.0 / _resistance(36.81e-6, 10.0, t) / 1000
        ax.plot([t], [i], "o", color=colour, markersize=5, zorder=3)
        ax.annotate(f"{label}\n{i:.1f} kA", (t, i), textcoords="offset points",
                    xytext=(8, 4), fontsize=7.5, color=colour)
    ax.set_xlabel("conductor temperature  [K]", fontsize=8, color=INK_SOFT)
    ax.set_ylabel("$I_f$  [kA]", fontsize=8, color=INK_SOFT)
    ax.set_xlim(90, 430)
    ax.set_ylim(0, 42)


def draw_trip_curve(ax):
    """The three regions, log-log, for a 100 A device."""
    lo = [i for i in range(101, 1000)]
    ax.plot(lo, [_trip_time(i) * 1000 for i in lo], color=ACCENT, linewidth=2.2,
            label=r"$I^2t$:  $t = K/I^2$")
    hi = [1000 * 1.02 ** n for n in range(0, 240)]
    hi = [i for i in hi if i <= 100000]
    ax.plot(hi, [T_MIN * 1000] * len(hi), color=CRITICAL, linewidth=2.2,
            label=r"instantaneous:  $t = t_{min}$")
    ax.axvline(I_RATED, color=INK_FAINT, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.axvline(I_RATED * K_MULT, color=INK_FAINT, linewidth=1.2,
               linestyle=(0, (4, 3)))
    ax.annotate(r"$I_r$", (I_RATED, 3e-2), fontsize=9, color=INK_SOFT,
                textcoords="offset points", xytext=(-16, 0))
    ax.annotate(r"$I_{inst}$", (I_RATED * K_MULT, 3e-2), fontsize=9,
                color=INK_SOFT, textcoords="offset points", xytext=(4, 0))
    ax.annotate("never trips\nbelow $I_r$", (55, 8e0), fontsize=7.5,
                color=INK_FAINT)
    ax.annotate("40× step", (1050, 3e-1), fontsize=7.5, color=CRITICAL)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("current  [A]", fontsize=8, color=INK_SOFT)
    ax.set_ylabel("trip time  [ms]", fontsize=8, color=INK_SOFT)
    ax.set_xlim(50, 1e5); ax.set_ylim(1e-2, 5e2)
    ax.legend(loc="upper right", frameon=False, fontsize=7.5,
              labelcolor=INK_SOFT)


def draw_let_through(ax):
    """Flat across the I^2t region, then rising as I^2."""
    lo = [i for i in range(101, 1000)]
    ax.plot(lo, [i ** 2 * _trip_time(i) for i in lo], color=ACCENT,
            linewidth=2.2, label=r"$E = K$  (flat)")
    hi = [1000 * 1.02 ** n for n in range(0, 240)]
    hi = [i for i in hi if i <= 100000]
    ax.plot(hi, [i ** 2 * T_MIN for i in hi], color=CRITICAL, linewidth=2.2,
            label=r"$E = I^2 t_{min}$")
    ax.axhline(K_RATING, color=INK_FAINT, linewidth=1.0, linestyle=(0, (4, 3)))
    ax.plot([36650], [36650 ** 2 * T_MIN], "o", color=CRITICAL, markersize=6,
            zorder=3)
    ax.annotate("worst fault\n$6.7\\times10^4\\,A^2s$",
                (36650, 36650 ** 2 * T_MIN), textcoords="offset points",
                xytext=(-78, 14), fontsize=7.5, color=CRITICAL)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("current  [A]", fontsize=8, color=INK_SOFT)
    ax.set_ylabel("let-through  [$A^2s$]", fontsize=8, color=INK_SOFT)
    ax.set_xlim(90, 1e5); ax.set_ylim(1e2, 1e6)
    ax.legend(loc="upper left", frameon=False, fontsize=7.5, labelcolor=INK_SOFT)


if __name__ == "__main__":
    main()
