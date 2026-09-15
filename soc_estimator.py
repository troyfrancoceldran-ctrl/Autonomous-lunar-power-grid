"""
@file    soc_estimator.py
@brief   Call the C++ EKF from the simulation, and turn its estimate into the
        one number the controller actually reads.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-15

@details
`BatteryBank.state_of_charge` is `energy_wh / capacity_wh`. Exact, noiseless,
free, and known every tick. NO REAL BATTERY CAN TELL YOU THAT — there is no
state-of-charge sensor. The controller in this simulation has therefore been
acting on information no outpost could have had.

This module removes the cheat. It loads the filter written in B02, feeds it
what the instruments would actually report, and hands the controller an
INFERENCE in place of the truth. B04 measures what that costs.

    from soc_estimator import FleetEstimator
    bus = PowerBus(..., estimator=FleetEstimator(battery))

WHY ctypes AND NOT A PYTHON PORT
    The measurement is only worth having if it exercises THE filter. A Python
    re-implementation would have to be kept in step by hand, and the first
    time it drifted the table would be quietly wrong. ctypes is in the
    standard library, so this costs no dependency. It is also the shape B03
    needs: marshalling scalars across a language boundary in-process, before
    a serial cable is involved.

API
    build_library() -> str
        Path to the shared library, with a clear error if it is not built.

    class Ekf
        update(current_a, terminal_voltage_v, dt_s) -> float
        soc / variance / gain                                   [@property]

    class FleetEstimator
        observe(energy_before_wh, energy_after_wh, dt_hours) -> None
            Feed the filter one tick of instrument readings.
        aggregate_soc(storage) -> float
            The fleet reserve with the battery INFERRED and the tanks exact.

@note ONLY THE BATTERY IS ESTIMATED. The RFC has no EKF, no OCV curve and no
    terminals in this model, so its contribution stays ground truth. That is
    a stated limitation rather than a hidden one: the battery holds 7.95 % of
    the fleet reserve, so the aggregate the controller sees is mostly exact
    and the effect measured here is a LOWER BOUND on what a fully instrumented
    outpost would suffer.
@note The filter runs AFTER dispatch, on the current that actually flowed, and
    the controller reads the result on the NEXT tick. That ordering is not a
    convenience — it is what a real BMS does. An estimate that used this
    tick's current would be answering with information the controller cannot
    have when it decides.
"""

import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "estimator", "build")

# macOS builds .dylib, Linux .so. Both are checked rather than guessed from
# sys.platform, because a build tree copied between machines should still work.
_CANDIDATES = ("libekf_c.dylib", "libekf_c.so", "ekf_c.dll")


class EstimatorNotBuilt(RuntimeError):
    """The shared library is missing; the C++ side has not been built."""


def build_library() -> str:
    """Path to the compiled filter, or a message saying how to produce it."""
    for name in _CANDIDATES:
        path = os.path.join(BUILD, name)
        if os.path.exists(path):
            return path
    raise EstimatorNotBuilt(
        "the C++ filter is not built, so there is nothing to estimate with.\n"
        "    cmake -S estimator -B estimator/build\n"
        "    cmake --build estimator/build")


def _bind():
    """Load the library and declare every signature. ctypes assumes int."""
    lib = ctypes.CDLL(build_library())
    d, v, p = ctypes.c_double, None, ctypes.c_void_p
    lib.ekf_create.argtypes = [d, d, d, d]
    lib.ekf_create.restype = p
    lib.ekf_destroy.argtypes = [p]
    lib.ekf_destroy.restype = v
    lib.ekf_update.argtypes = [p, d, d, d]
    lib.ekf_update.restype = d
    for name in ("ekf_soc", "ekf_variance", "ekf_gain"):
        getattr(lib, name).argtypes = [p]
        getattr(lib, name).restype = d
    for name in ("ekf_ocv_v", "ekf_docv_dsoc"):
        getattr(lib, name).argtypes = [d]
        getattr(lib, name).restype = d
    for name in ("ekf_capacity_ah", "ekf_coulombic_efficiency",
                "ekf_r_internal_ohm", "ekf_soc_min", "ekf_soc_max"):
        getattr(lib, name).argtypes = []
        getattr(lib, name).restype = d
    lib.ekf_cells_series.argtypes = []
    lib.ekf_cells_series.restype = ctypes.c_int
    return lib


_LIB = None


def library():
    """Load once, on first use — importing this module must not require a build."""
    global _LIB
    if _LIB is None:
        _LIB = _bind()
    return _LIB


class Ekf:
    """A handle on one C++ filter. Scalars in, scalars out."""

    def __init__(self, initial_soc: float, initial_var: float,
                q_proc: float, r_meas: float):
        self._lib = library()
        self._handle = self._lib.ekf_create(initial_soc, initial_var,
                                            q_proc, r_meas)
        if not self._handle:
            raise MemoryError("ekf_create returned NULL")

    def update(self, current_a: float, terminal_voltage_v: float,
            dt_s: float) -> float:
        """One predict/correct cycle; returns the updated estimate."""
        return self._lib.ekf_update(self._handle, current_a,
                                    terminal_voltage_v, dt_s)

    @property
    def soc(self) -> float:
        """The current estimate."""
        return self._lib.ekf_soc(self._handle)

    @property
    def variance(self) -> float:
        """How confident the filter is; small means certain."""
        return self._lib.ekf_variance(self._handle)

    @property
    def gain(self) -> float:
        """The last Kalman gain. Near zero means it stopped believing the meter."""
        return self._lib.ekf_gain(self._handle)

    def __del__(self):
        handle, lib = getattr(self, "_handle", None), getattr(self, "_lib", None)
        if handle and lib:
            lib.ekf_destroy(handle)
            self._handle = None


class FleetEstimator:
    """The battery inferred, the tanks exact, expressed as one fleet fraction."""

    def __init__(self, battery, q_proc: float = 1e-9,
                r_meas: float = None, initial_var: float = 1e-6,
                seed: int = 12345, initial_soc: float = None):
        """
        @param battery       the BatteryBank whose charge is to be inferred
        @param q_proc        process variance per step — how far the filter
                            distrusts its own model
        @param r_meas        measurement variance. Defaults to the sensor's
                            true noise, which assumes the model is otherwise
                            perfect; it is a BELIEF, not a measurement.
        @param initial_soc   the filter's prior. Defaults to the battery's
                            true starting charge — a commissioned pack is
                            calibrated once, and the drift starts after.
        """
        lib = library()
        self.battery = battery
        self.v_nominal = battery.capacity_wh / lib.ekf_capacity_ah()
        if r_meas is None:
            r_meas = battery.volt_sensor_noise ** 2
        start = battery.state_of_charge if initial_soc is None else initial_soc
        self.filter = Ekf(start, initial_var, q_proc, r_meas)
        self.rng = random.Random(seed)
        self.history = []
        # The same biased reading integrated with NO correction. Carried so the
        # figure can show what the filter is beating rather than assert it.
        self.counted = start
        self.capacity_ah = lib.ekf_capacity_ah()

    def observe(self, energy_before_wh: float, energy_after_wh: float,
                dt_hours: float) -> None:
        """One tick of instrument readings, taken AFTER the power has flowed."""
        if dt_hours <= 0:
            return
        # Pack current from the pack's own energy change, POSITIVE discharging.
        # Taking it from the stored energy rather than from the bus-side flow
        # sidesteps the converter and feeder entirely: those losses happen
        # outside the pack and no ammeter on the battery would see them.
        drained_wh = energy_before_wh - energy_after_wh
        current_a = drained_wh / (self.v_nominal * dt_hours)
        reported_a, reported_v = self.battery.measure(current_a, self.rng)
        self.filter.update(reported_a, reported_v, dt_hours * 3600.0)
        self.counted = min(max(
            self.counted - reported_a * dt_hours / self.capacity_ah, 0.0), 1.0)
        self.history.append((current_a, reported_a, reported_v,
                            self.battery.state_of_charge, self.filter.soc,
                            self.filter.gain, self.filter.variance))

    @property
    def soc(self) -> float:
        """The battery estimate alone."""
        return self.filter.soc

    def aggregate_soc(self, storage) -> float:
        """Fleet reserve, with the battery's share inferred rather than read."""
        energy_wh = capacity_wh = 0.0
        for device in storage:
            capacity_wh += device.deliverable_capacity_wh
            if device is self.battery:
                spendable = max(0.0, self.filter.soc - device.soc_min)
                energy_wh += (spendable * device.capacity_wh
                              * device.discharge_efficiency)
            else:
                energy_wh += device.deliverable_energy_wh
        return energy_wh / capacity_wh if capacity_wh > 0 else 0.0
