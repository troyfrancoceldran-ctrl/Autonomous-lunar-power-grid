"""
AutonomousController — priority-based load shedding/restoration with
hysteresis, built as a Strategy so alternate dispatch algorithms (e.g. a
later RL-based controller) can be swapped in without touching power_bus.py
or simulation_engine.py.

STATUS: Step 7 — not yet implemented. See PROGRESS.md.
"""
