"""
@file    metrics.py
@brief   Post-run KPIs: what the history MEANS.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-04

@details
Reads a run history and answers the questions a reviewer actually asks. Pure
functions over a list of dicts — nothing here touches an asset, an
environment or a controller, so metrics can be recomputed from an exported
CSV months later with the simulation gone.

Two families, and they are not interchangeable:

    RELIABILITY   did the outpost serve its loads?  Standard power-system
                measures — unserved energy, LOLP, LOLE, per-load
                availability. These are what a mission planner reads.

    DIAGNOSIS     WHY did it fail, when it did?  This project's own
                contribution: separating energy-limited hours from
                power-limited ones. A reserve can be deep and still
                unusable if the only device holding it is rated at 12 kW.

@note Every energy is integrated as sum(power) * dt — a left-endpoint
    rectangle rule, exact here because the bus reports a rate held constant
    across its own timestep rather than a sample of a continuous curve.

@note dt is INFERRED from the first two records rather than imported from
    config. A history exported from a dt = 0.25 h sensitivity run must
    integrate with its own timestep, not with whatever config happens to say
    today. A one-row history has no dt to infer and raises.

@see power_bus.py for the RECORD SCHEMA these functions read.
@see simulation_engine.py for how a history is produced and exported.


================================================================================
API
================================================================================

timestep_hours(history) -> float
    Infer dt from the first two records.

    @param  history  List of per-tick records, in time order.
    @return t_hours[1] - t_hours[0].
    @raise  ValueError if fewer than two records.

series_names(history, prefix) -> list[str]
    Every device or load name carrying a given column prefix.

    @param  prefix  One of "gen:", "soc:", "flow:", "load:", "shed:".
    @return Names in record order, prefix stripped.

    @note This is what keeps metrics.py independent of the outpost's parts
        list. Add a second reactor and every function below picks it up with
        no edit, because none of them names an asset.

--------------------------------------------------------------------------------
RELIABILITY
--------------------------------------------------------------------------------
energy_totals(history) -> dict
    Where every watt-hour went.

    @return generated_kwh, served_kwh, unserved_kwh, curtailed_kwh,
            charged_kwh, discharged_kwh, storage_loss_kwh,
            curtailment_fraction, round_trip_efficiency.

    @note storage_loss_kwh is charged - discharged: energy the outpost put
        into storage and never got back. It is the round-trip penalty made
        visible, and on a hybrid fleet it is dominated by the RFC's 0.385.
    @warning round_trip_efficiency is a RUN-LEVEL ratio, discharged/charged,
        not a device specification. It lands between the battery's 0.9025 and
        the RFC's 0.385 according to how the merit order split the traffic,
        and it is only meaningful once storage has returned roughly what it
        took — early in a run, or one ending mid-night, it reads low because
        energy is still in the tanks rather than lost.

reliability(history) -> dict
    Standard adequacy measures.

    @return lolp, lole_hours, unserved_kwh, worst_shortfall_w,
            shortfall_events, longest_shortfall_hours.

    @note LOLP (loss-of-load probability) is the FRACTION of ticks with any
        unserved power; LOLE (loss-of-load expectation) is the same thing in
        hours. Both are the standard vocabulary for generation adequacy, and
        quoting them is what lets this run be compared against a terrestrial
        study rather than only against itself.
    @note An "event" is a maximal run of consecutive shortfall ticks. Ten
        separate one-hour brownouts and one ten-hour brownout have identical
        unserved energy and very different operational meaning.

load_availability(history) -> dict
    Per-load uptime.

    @return {load name: fraction of ticks NOT shed}, plus "_worst".

    @note Availability, not energy served. A load shed during its idle window
        loses no energy at all, and a mission planner still wants to know the
        instrument was disconnected.
    @note ECLSS must read 1.000 in every scenario. If it ever does not, the
        CRITICAL exclusion has been broken and nothing else in the report
        matters.

shed_events(history) -> list[dict]
    Every shed as a discrete episode.

    @return One dict per episode: load, start_h, end_h, duration_hours,
            energy_forgone_kwh. Still-shed episodes end at the run's end and
            are marked ongoing.

    @note energy_forgone_kwh integrates what the load WOULD have drawn while
        disconnected, which needs the load's demand curve — unavailable from
        the history alone once the load reads 0 W. It is therefore reported
        only for episodes where the load's own column can supply it, and left
        as None otherwise. Honest gaps beat invented numbers.

--------------------------------------------------------------------------------
DIAGNOSIS
--------------------------------------------------------------------------------
failure_modes(history, shed_threshold=SOC_SHED_THRESHOLD) -> dict
    Split the bad hours by WHY they were bad.

    @return energy_limited_hours, power_limited_hours, both_hours,
            power_limited_fraction, worst_power_limited_soc.

    @note THE metric this project exists to produce. A tick is POWER-limited
        when headroom went negative while the aggregate reserve was still
        above the shed threshold — the tanks were full enough and the outpost
        browned out anyway, because the only device with energy left could
        not deliver fast enough. It is ENERGY-limited when the reserve itself
        had fallen through the floor.
    @note worst_power_limited_soc is the highest reserve at which a shortfall
        still occurred. The closer that number is to 1.0, the more emphatic
        the case that a single state-of-charge signal cannot protect this
        outpost.

storage_utilisation(history) -> dict
    Per-device depth and duty.

    @return Per device: min_soc, max_soc, depth_of_discharge,
            hours_at_floor, hours_charging, hours_discharging, peak_charge_w,
            peak_discharge_w.

    @note hours_at_floor is the power-headroom story in one number. A device
        pinned at its floor contributes nothing to the fleet's discharge
        ceiling, however healthy the aggregate reserve looks.

reactant_margin(history) -> dict
    RFC state of charge at each lunar dawn.

    @return per_dawn list of (t_hours, soc) and the minimum across them.

    @note The mission-critical number. Everything else can be recovered by
        waiting; hydrogen can only be remade in sunlight. The margin at dawn
        is how much the outpost had left when it stopped being able to run
        out.
    @note Dawn is detected as a False -> True transition in is_daylight, so
        this needs no clock of its own and stays correct if the synodic
        period is ever revised again.

report(history) -> str
    Every section above, formatted for a terminal.

    @return A multi-line string. Printing is the caller's business.
"""

from config import SOC_SHED_THRESHOLD


def timestep_hours(history) -> float:
    """Infer dt from the first two records; a history of one has none."""
    if len(history) < 2:
        raise ValueError("need at least two records to infer the timestep")
    return history[1]["t_hours"] - history[0]["t_hours"]


def series_names(history, prefix: str) -> list:
    """Device or load names carrying a given column prefix, in record order."""
    return [key[len(prefix):] for key in history[0] if key.startswith(prefix)]


def _integrate(history, key: str) -> float:
    """Integrate a power column to kWh over the whole history."""
    return sum(record[key] for record in history) * timestep_hours(history) / 1000.0


def energy_totals(history) -> dict:
    """Where every watt-hour went, in kWh."""
    generated = _integrate(history, "generation_w")
    charged = _integrate(history, "charged_w")
    discharged = _integrate(history, "discharged_w")
    curtailed = _integrate(history, "curtailed_w")
    return {
        "generated_kwh": generated,
        "served_kwh": _integrate(history, "served_w"),
        "unserved_kwh": _integrate(history, "shortfall_w"),
        "curtailed_kwh": curtailed,
        "charged_kwh": charged,
        "discharged_kwh": discharged,
        "storage_loss_kwh": charged - discharged,
        "curtailment_fraction": curtailed / generated if generated else 0.0,
        "round_trip_efficiency": discharged / charged if charged else 0.0,
    }


def _episodes(history, predicate):
    """Maximal runs of consecutive ticks satisfying predicate; (start, end, n)."""
    dt = timestep_hours(history)
    runs, start, count = [], None, 0
    for record in history:
        if predicate(record):
            if start is None:
                start, count = record["t_hours"], 0
            count += 1
        elif start is not None:
            runs.append((start, start + count * dt, count))
            start, count = None, 0
    if start is not None:
        runs.append((start, start + count * dt, count))
    return runs


def reliability(history) -> dict:
    """Standard adequacy measures: LOLP, LOLE, unserved energy, event shape."""
    dt = timestep_hours(history)
    bad = [r for r in history if r["shortfall_w"] > 0.0]
    events = _episodes(history, lambda r: r["shortfall_w"] > 0.0)
    return {
        "lolp": len(bad) / len(history),
        "lole_hours": len(bad) * dt,
        "unserved_kwh": _integrate(history, "shortfall_w"),
        "worst_shortfall_w": max((r["shortfall_w"] for r in history), default=0.0),
        "shortfall_events": len(events),
        "longest_shortfall_hours": max((e[1] - e[0] for e in events), default=0.0),
    }


def load_availability(history) -> dict:
    """Fraction of ticks each load was connected; plus the worst of them."""
    names = series_names(history, "shed:")
    out = {name: sum(1 for r in history if not r[f"shed:{name}"]) / len(history)
        for name in names}
    out["_worst"] = min(out.values()) if out else 1.0
    return out


def shed_events(history) -> list:
    """Every shed as a discrete episode, with energy forgone where knowable."""
    dt = timestep_hours(history)
    out = []
    for name in series_names(history, "shed:"):
        for start_h, end_h, count in _episodes(history, lambda r, n=name: r[f"shed:{n}"]):
            out.append({
                "load": name,
                "start_h": start_h,
                "end_h": end_h,
                "duration_hours": count * dt,
                "ongoing": end_h > history[-1]["t_hours"],
                # A shed load reports 0 W, so what it WOULD have drawn is not
                # recoverable from the history. Left None rather than guessed.
                "energy_forgone_kwh": None,
            })
    return sorted(out, key=lambda e: e["start_h"])


def failure_modes(history, shed_threshold: float = SOC_SHED_THRESHOLD) -> dict:
    """Split shortfall hours into energy-limited and power-limited."""
    dt = timestep_hours(history)
    bad = [r for r in history if r["shortfall_w"] > 0.0]
    power_limited = [r for r in bad if r["aggregate_soc"] > shed_threshold]
    energy_limited = [r for r in bad if r["aggregate_soc"] <= shed_threshold]
    return {
        "shortfall_hours": len(bad) * dt,
        "energy_limited_hours": len(energy_limited) * dt,
        "power_limited_hours": len(power_limited) * dt,
        "power_limited_fraction": len(power_limited) / len(bad) if bad else 0.0,
        "worst_power_limited_soc": max((r["aggregate_soc"] for r in power_limited),
                                    default=0.0),
        "shed_threshold": shed_threshold,
    }


def storage_utilisation(history) -> dict:
    """Per-device depth, duty and peak power, from the soc: and flow: columns."""
    dt = timestep_hours(history)
    out = {}
    for name in series_names(history, "soc:"):
        socs = [r[f"soc:{name}"] for r in history]
        flows = [r[f"flow:{name}"] for r in history]
        floor = min(socs)
        out[name] = {
            "min_soc": floor,
            "max_soc": max(socs),
            "depth_of_discharge": max(socs) - floor,
            "hours_at_floor": sum(1 for s in socs if abs(s - floor) < 1e-9) * dt,
            "hours_charging": sum(1 for f in flows if f > 0) * dt,
            "hours_discharging": sum(1 for f in flows if f < 0) * dt,
            "peak_charge_w": max((f for f in flows), default=0.0),
            "peak_discharge_w": -min((f for f in flows), default=0.0),
        }
    return out


def reactant_margin(history) -> dict:
    """RFC-style storage state at each lunar dawn; the mission-critical number."""
    dawns = [history[i]["t_hours"]
            for i in range(1, len(history))
            if history[i]["is_daylight"] and not history[i - 1]["is_daylight"]]
    out = {}
    for name in series_names(history, "soc:"):
        by_t = {r["t_hours"]: r[f"soc:{name}"] for r in history}
        per_dawn = [(t, by_t[t]) for t in dawns]
        out[name] = {
            "per_dawn": per_dawn,
            "min_at_dawn": min((s for _, s in per_dawn), default=None),
        }
    return {"dawns": dawns, "devices": out}


def report(history) -> str:
    """Every section formatted for a terminal; printing is the caller's job."""
    e = energy_totals(history)
    r = reliability(history)
    a = load_availability(history)
    f = failure_modes(history)
    u = storage_utilisation(history)
    m = reactant_margin(history)
    dt = timestep_hours(history)

    lines = []
    add = lines.append
    add(f"{'=' * 66}")
    add(f"RUN  {len(history)} ticks x {dt:g} h = {len(history) * dt:g} h")
    add(f"{'=' * 66}")

    add("\nENERGY [kWh]")
    add(f"  {'generated':<26}{e['generated_kwh']:>12.1f}")
    add(f"  {'served':<26}{e['served_kwh']:>12.1f}")
    add(f"  {'unserved':<26}{e['unserved_kwh']:>12.1f}")
    add(f"  {'curtailed':<26}{e['curtailed_kwh']:>12.1f}"
        f"   ({e['curtailment_fraction']:.1%} of generation)")
    add(f"  {'into storage':<26}{e['charged_kwh']:>12.1f}")
    add(f"  {'out of storage':<26}{e['discharged_kwh']:>12.1f}")
    add(f"  {'storage round-trip loss':<26}{e['storage_loss_kwh']:>12.1f}"
        f"   (run ratio {e['round_trip_efficiency']:.3f})")

    add("\nRELIABILITY")
    add(f"  {'LOLP':<26}{r['lolp']:>12.5f}")
    add(f"  {'LOLE':<26}{r['lole_hours']:>12.1f} h")
    add(f"  {'unserved energy':<26}{r['unserved_kwh']:>12.2f} kWh")
    add(f"  {'worst shortfall':<26}{r['worst_shortfall_w'] / 1000:>12.2f} kW")
    add(f"  {'shortfall events':<26}{r['shortfall_events']:>12}"
        f"   (longest {r['longest_shortfall_hours']:g} h)")

    add("\nFAILURE MODE — why the bad hours were bad")
    if r["lole_hours"] == 0:
        add("  none: every load served at every tick")
    else:
        add(f"  {'energy-limited':<26}{f['energy_limited_hours']:>12.1f} h"
            f"   (reserve below {f['shed_threshold']:.2f})")
        add(f"  {'power-limited':<26}{f['power_limited_hours']:>12.1f} h"
            f"   ({f['power_limited_fraction']:.0%} of shortfall hours)")
        add(f"  {'worst power-limited SoC':<26}{f['worst_power_limited_soc']:>12.4f}"
            f"   <- reserve looked this healthy while the bus was failing")

    add("\nLOAD AVAILABILITY")
    for name, frac in a.items():
        if name != "_worst":
            add(f"  {name[:44]:<46}{frac:>10.3%}")

    add("\nSTORAGE")
    for name, d in u.items():
        add(f"  {name}")
        add(f"    {'SoC range':<24}{d['min_soc']:.4f} - {d['max_soc']:.4f}"
            f"   (DoD {d['depth_of_discharge']:.4f})")
        add(f"    {'hours at floor':<24}{d['hours_at_floor']:>10.0f} h")
        add(f"    {'charging / discharging':<24}"
            f"{d['hours_charging']:>10.0f} h / {d['hours_discharging']:.0f} h")
        add(f"    {'peak charge / discharge':<24}"
            f"{d['peak_charge_w'] / 1000:>10.2f} kW / "
            f"{d['peak_discharge_w'] / 1000:.2f} kW")

    add(f"\nRESERVE AT DAWN  ({len(m['dawns'])} dawns in this run)")
    for name, d in m["devices"].items():
        if d["min_at_dawn"] is not None:
            trace = "  ".join(f"{s:.3f}" for _, s in d["per_dawn"])
            add(f"  {name[:30]:<32}{trace}")
    add("")
    return "\n".join(lines)
