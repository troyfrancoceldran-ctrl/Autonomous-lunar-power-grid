"""
@file    visualization.py
@brief   Figures: what the history LOOKS like.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-04

@details
Four figures, each answering one question. Like metrics.py these are pure
functions over a history list — no asset, no environment, no controller — so
a figure can be redrawn from an exported CSV with the simulation gone.

    1  Power balance      where the watts came from and went, hour by hour
    2  Reserves           the two-tier storage story, with the night shaded
    3  Shed timeline      which load was disconnected, and for how long
    4  The two signals    energy reserve against power headroom — the figure
                        this project exists to produce

@note PALETTE. Colours are assigned by fixed slot order from a validated
    categorical palette, never picked for resemblance (the PV array is blue,
    not yellow). The order is the colour-blind-safety mechanism: adjacent
    slots are guaranteed separable, so reordering them to "look right" breaks
    the guarantee. Series identity is never carried by colour alone — every
    figure legends and direct-labels its series.

@note ONE AXIS PER FIGURE, always. No figure here plots two different units
    against left and right scales. Where two quantities of different scale
    matter (reserve fraction and headroom watts) they get two stacked panels
    sharing a time axis, which lets them be compared without inviting a false
    reading of where the curves cross.

@note metrics.report() is the table view for these figures — the same numbers
    in text, for anyone who cannot use the colour.

@see metrics.py for the numbers these draw.
@see power_bus.py for the RECORD SCHEMA they read.


================================================================================
API
================================================================================

SURFACE / INK / SERIES                                              [constants]
    Palette slots, light mode. SERIES is the fixed assignment order; index
    into it positionally rather than choosing by name.

figure_power_balance(history, path=None) -> Figure
    Stacked supply against demand, with curtailment and shortfall called out.

    @param  history  Per-tick records.
    @param  path     Save here if given; the figure is returned either way.

    @note Supply STACKS because the components sum to something meaningful —
        total power delivered to the bus. Demand is a line over the top, not
        a fifth stack layer: it is the target the stack is trying to reach,
        and drawing it as another band would imply it adds to supply.
    @note Curtailment is drawn BELOW the axis as a negative band. It is
        generated power that was thrown away, so showing it above zero would
        double-count it against the same watts already in the PV band.

figure_reserves(history, path=None) -> Figure
    Aggregate, battery and RFC state of charge, with the night shaded.

    @note The shed and restore thresholds are drawn as reference lines. The
        gap between them IS the hysteresis dead band, and seeing the
        aggregate trace sit inside it without acting is the clearest picture
        of why the band exists.
    @note Night shading comes from is_daylight rather than a computed clock,
        so it stays correct if the synodic period is ever revised.

figure_shed_timeline(history, path=None) -> Figure
    One row per load; a bar wherever that load was disconnected.

    @note Rows are ordered by LoadPriority, so the staircase reads top to
        bottom: the least important load sheds first and restores last. ECLSS
        occupies a row that should never contain a bar — an empty row is the
        result, not a missing series.

figure_two_signals(history, path=None) -> Figure
    Two stacked panels: energy reserve above, power headroom below.

    @note THE figure. The upper panel is the signal a conventional controller
        watches; the lower is the one this project added. Every point where
        the lower panel crosses zero while the upper sits comfortably high is
        an hour a single-signal controller would have slept through.
    @note The lower panel plots headroom and the fleet discharge ceiling
        together because they are both watts on one axis. The ceiling
        collapsing to the RFC's rating while the battery sits at its floor is
        the mechanism behind every power-limited hour.

make_all(history, outdir="data/figures") -> list[str]
    Render all four and return the paths written.
"""

import matplotlib
matplotlib.use("Agg")                    # no display needed; write files
import matplotlib.pyplot as plt          # noqa: E402

from config import SOC_SHED_THRESHOLD, SOC_RESTORE_THRESHOLD, LoadPriority
from metrics import series_names, timestep_hours

# Validated categorical palette, light mode. Assign in this order, never cycle.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
# Status colours are RESERVED and never reused as a series slot. Kept visually
# distinct from the categorical hues so a status cannot impersonate a series,
# and always shipped with a label rather than leaning on hue alone.
CRITICAL = "#d03b3b"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
INK_FAINT = "#c9c8c2"
NIGHT = "#eceae5"


def _legend(ax, ncol):
    """Legend ABOVE the axes, never inside it.

    These are dense 1440-point series that fill their frame, so every in-axes
    position lands on data somewhere in the run — the first draft put one
    across the battery trace and another across the headroom curve. Above the
    frame is the only placement that cannot collide.
    """
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=ncol,
            frameon=False, fontsize=8, labelcolor=INK_SOFT,
            handlelength=1.6, columnspacing=1.6, borderaxespad=0.2)


SHORT_NAMES = {"Environmental Control and Life Support System": "ECLSS (life support)"}


def _short(name):
    """Axis-length label for a load; the official names do not fit."""
    return SHORT_NAMES.get(name, name)


def _style(ax, title, ylabel, xlabel="hours since lunar dawn", pad=26):
    """Recessive grid and axes; ink tokens for all text."""
    ax.set_facecolor(SURFACE)
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=pad)
    ax.set_ylabel(ylabel, color=INK_SOFT, fontsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK_SOFT, fontsize=9)
    ax.tick_params(colors=INK_SOFT, labelsize=8)
    ax.grid(True, color=INK_FAINT, linewidth=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_FAINT)


def _shade_night(ax, history):
    """Shade the lunar night from is_daylight, not from a computed clock."""
    dt = timestep_hours(history)
    start = None
    for record in history:
        if not record["is_daylight"] and start is None:
            start = record["t_hours"]
        elif record["is_daylight"] and start is not None:
            ax.axvspan(start, record["t_hours"], color=NIGHT, zorder=0)
            start = None
    if start is not None:
        ax.axvspan(start, history[-1]["t_hours"] + dt, color=NIGHT, zorder=0)


def _figure(nrows=1, height=4.0):
    """A themed figure with the chart surface applied."""
    fig, axes = plt.subplots(nrows, 1, figsize=(11, height), sharex=(nrows > 1))
    fig.patch.set_facecolor(SURFACE)
    return fig, axes


def _save(fig, path):
    """Write the figure if a path was given; return it either way."""
    if path:
        fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    return fig


def figure_power_balance(history, path=None):
    """Stacked supply against demand; curtailment below the axis."""
    t = [r["t_hours"] for r in history]
    sources = series_names(history, "gen:")
    bands = [[r[f"gen:{n}"] / 1000 for r in history] for n in sources]
    bands.append([r["discharged_w"] / 1000 for r in history])
    labels = sources + ["Storage discharge"]

    fig, ax = _figure(height=4.2)
    _shade_night(ax, history)
    ax.stackplot(t, *bands, labels=labels,
                colors=SERIES[:len(bands)], edgecolor=SURFACE, linewidth=0.3)
    ax.plot(t, [r["demand_w"] / 1000 for r in history],
            color=INK, linewidth=1.6, label="Demand (after shedding)")
    ax.fill_between(t, 0, [-r["curtailed_w"] / 1000 for r in history],
                    color=INK_FAINT, label="Curtailed")
    ax.axhline(0, color=INK_FAINT, linewidth=1.0)

    _style(ax, "Power balance — supply stacked against demand", "power  [kW]", pad=30)
    _legend(ax, 5)
    ax.set_xlim(t[0], t[-1])
    return _save(fig, path)


def figure_reserves(history, path=None):
    """Aggregate, battery and RFC state of charge, with the night shaded."""
    t = [r["t_hours"] for r in history]
    traces = [("Fleet aggregate", [r["aggregate_soc"] for r in history])]
    traces += [(n, [r[f"soc:{n}"] for r in history])
            for n in series_names(history, "soc:")]

    fig, ax = _figure(height=4.2)
    _shade_night(ax, history)
    ax.axhspan(SOC_SHED_THRESHOLD, SOC_RESTORE_THRESHOLD,
            color=INK_FAINT, alpha=0.45, zorder=1)
    ax.axhline(SOC_SHED_THRESHOLD, color=INK_SOFT, linewidth=1.0,
            linestyle=(0, (4, 3)), zorder=2)
    ax.axhline(SOC_RESTORE_THRESHOLD, color=INK_SOFT, linewidth=1.0,
            linestyle=(0, (4, 3)), zorder=2)
    ax.text(t[-1], (SOC_SHED_THRESHOLD + SOC_RESTORE_THRESHOLD) / 2,
            "  hysteresis\n  dead band", color=INK_SOFT, fontsize=8, va="center")

    for i, (label, values) in enumerate(traces):
        ax.plot(t, values, color=SERIES[i], linewidth=2.0, label=label, zorder=3)

    _style(ax, "Storage reserves — the two-tier split", "state of charge  [-]", pad=30)
    _legend(ax, 3)
    ax.set_xlim(t[0], t[-1] * 1.10)
    ax.set_ylim(0, 1.05)
    return _save(fig, path)


def figure_shed_timeline(history, path=None):
    """One row per load; a bar wherever that load was disconnected."""
    dt = timestep_hours(history)
    names = series_names(history, "shed:")
    fig, ax = _figure(height=2.8)
    _shade_night(ax, history)

    for row, name in enumerate(names):
        spans, start = [], None
        for record in history:
            if record[f"shed:{name}"] and start is None:
                start = record["t_hours"]
            elif not record[f"shed:{name}"] and start is not None:
                spans.append((start, record["t_hours"] - start))
                start = None
        if start is not None:
            spans.append((start, history[-1]["t_hours"] + dt - start))
        if spans:
            ax.broken_barh(spans, (row - 0.32, 0.64),
                        facecolors=SERIES[row % len(SERIES)], zorder=3)

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([_short(n) for n in names], fontsize=8)
    ax.invert_yaxis()
    ax.set_ylim(len(names) - 0.5, -0.5)
    _style(ax, "Load shedding — bars mark hours disconnected", "")
    ax.grid(True, axis="x", color=INK_FAINT, linewidth=0.6, alpha=0.6)
    ax.grid(False, axis="y")
    ax.set_xlim(history[0]["t_hours"], history[-1]["t_hours"])
    # No legend: the row labels ARE the identity. A colour key here would say
    # only "shed", which the title already says, while implying the colours
    # encode something they do not.
    return _save(fig, path)


def figure_two_signals(history, path=None):
    """Energy reserve above, power headroom below — two panels, one time axis."""
    t = [r["t_hours"] for r in history]
    fig, (top, bot) = _figure(nrows=2, height=6.0)

    for ax in (top, bot):
        _shade_night(ax, history)

    top.plot(t, [r["aggregate_soc"] for r in history],
            color=SERIES[0], linewidth=2.0, label="Fleet aggregate SoC")
    top.axhline(SOC_SHED_THRESHOLD, color=INK_SOFT, linewidth=1.0,
                linestyle=(0, (4, 3)))
    _style(top, "The energy signal — what a conventional controller watches",
        "state of charge  [-]", xlabel="", pad=30)
    _legend(top, 2)
    top.set_ylim(0, 1.05)

    bot.plot(t, [r["storage_ceiling_w"] / 1000 for r in history],
            color=SERIES[1], linewidth=2.0, label="Fleet discharge ceiling")
    bot.plot(t, [r["headroom_w"] / 1000 for r in history],
            color=SERIES[0], linewidth=2.0, label="Power headroom")
    bot.axhline(0, color=INK, linewidth=1.2)

    brownouts = [r["t_hours"] for r in history if r["shortfall_w"] > 0]
    for i, t_bad in enumerate(brownouts):
        bot.axvline(t_bad, color=CRITICAL, linewidth=1.6, zorder=1,
                    label="Unserved power" if i == 0 else None)

    _style(bot, "The power signal — what this project added", "power  [kW]", pad=30)
    _legend(bot, 3)

    for ax in (top, bot):
        ax.set_xlim(t[0], t[-1])
    fig.tight_layout()
    return _save(fig, path)


def make_all(history, outdir="data/figures"):
    """Render all four figures into outdir; returns the paths written."""
    import os
    os.makedirs(outdir, exist_ok=True)
    jobs = [
        (figure_power_balance, "power_balance.png"),
        (figure_reserves, "reserves.png"),
        (figure_shed_timeline, "shed_timeline.png"),
        (figure_two_signals, "two_signals.png"),
    ]
    paths = []
    for fn, name in jobs:
        path = os.path.join(outdir, name)
        fig = fn(history, path)
        plt.close(fig)
        paths.append(path)
    return paths
