"""
@file    web/tools/export_config.py
@brief   Generate web/src/config.js from config.py so the two cannot drift.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-08

@details
Every constant in this project carries a citation, and several of them were
argued over — the 708.7 h synodic period, the 0.05 battery floor, the 3.0 h
dwell. Hand-copying that table into a second language would work exactly once,
and then someone would revise a number on one side only.

So the JS constants are GENERATED. Change config.py, re-run this, and the two
agree by construction rather than by discipline.

    .venv/bin/python web/tools/export_config.py

@note The comment above each constant is carried across too. A number without
    its justification is how a model starts drifting from the literature it
    claims to follow, and the JS reader deserves the same reasoning the Python
    reader gets.
@note LoadPriority is emitted as a frozen object. JS has no IntEnum, but the
    values are compared with === and ordered with < and >, both of which work
    on plain numbers — which is all the Python code relies on.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import config as cfg  # noqa: E402

HEADER = """// GENERATED FILE — do not edit.
//
// Produced by web/tools/export_config.py from config.py, so the browser model
// and the Python model cannot disagree about a constant. Change config.py and
// re-run the generator.
//
// Every comment below is carried across from the Python source, because a
// number without its justification is how a model quietly drifts away from the
// literature it claims to follow.

"""


def source_comments():
    """Map CONSTANT -> the comment block immediately above it in config.py."""
    lines = open(os.path.join(ROOT, "config.py")).read().splitlines()
    out, block = {}, []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            block.append(stripped.lstrip("#").rstrip())
        elif re.match(r"^[A-Z][A-Z0-9_]*\s*:", stripped):
            name = stripped.split(":")[0].strip()
            if block:
                out[name] = list(block)
            block = []
        elif not stripped:
            continue
        else:
            block = []
    return out


def js_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite constant")
        return repr(value)
    return repr(value)


def main():
    comments = source_comments()
    parts = [HEADER]

    names = [n for n in dir(cfg)
            if n.isupper() and isinstance(getattr(cfg, n), (int, float, bool, type(None)))]
    # dir() sorts alphabetically; config.py's own order is the readable one.
    order = {}
    for i, line in enumerate(open(os.path.join(ROOT, "config.py"))):
        m = re.match(r"^([A-Z][A-Z0-9_]*)\s*:", line)
        if m:
            order[m.group(1)] = i
    names.sort(key=lambda n: order.get(n, 1e9))

    for name in names:
        for line in comments.get(name, []):
            parts.append(f"//{line}" if line else "//")
        parts.append(f"export const {name} = {js_value(getattr(cfg, name))};")
        parts.append("")

    parts.append("// Lower number = higher priority = shed last, restored first.")
    parts.append("export const LoadPriority = Object.freeze({")
    for member in cfg.LoadPriority:
        parts.append(f"  {member.name}: {member.value},")
    parts.append("});")
    parts.append("")

    path = os.path.join(ROOT, "web", "src", "config.js")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write("\n".join(parts))
    print(f"  wrote {os.path.relpath(path, ROOT)}")
    print(f"  {len(names)} constants + LoadPriority "
        f"({len(list(cfg.LoadPriority))} members), "
        f"{os.path.getsize(path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
