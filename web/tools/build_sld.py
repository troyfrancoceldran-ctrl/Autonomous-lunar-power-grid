"""
@file    web/tools/build_sld.py
@brief   Inject the verified simulation core into the one-line diagram page.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-08

@details
The artifact CSP blocks fetch, so the page cannot load the model at runtime —
it has to ship inside the HTML. Rather than hand-copy the core into the page
(where it would immediately start drifting), this injects the SAME bundle the
conformance runner executes.

So the diagram is not drawing something that resembles the model. It is
drawing the model, byte for byte, in code that passed 198,720 comparisons
against the Python run.

    .venv/bin/python web/tools/build_sld.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from run_conformance import build_bundle, MODULES  # noqa: E402

PLACEHOLDER = "/*__SIM_BUNDLE__*/"


def main():
    template_path = os.path.join(ROOT, "web", "sld.template.html")
    with open(template_path, encoding="utf-8") as handle:
        page = handle.read()
    if PLACEHOLDER not in page:
        raise SystemExit(f"{template_path}: placeholder {PLACEHOLDER} not found")

    # conformance.js imports nothing the page needs and pulls in the golden
    # comparison machinery, so it is left out of the shipped bundle.
    bundle = build_bundle([m for m in MODULES if m != "conformance.js"])
    page = page.replace(PLACEHOLDER, bundle)

    out = os.path.join(ROOT, "web", "sld.html")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(page)
    print(f"  wrote {os.path.relpath(out, ROOT)}  "
        f"({os.path.getsize(out) / 1024:.1f} KB, "
        f"{len(bundle.splitlines())} lines of model)")


if __name__ == "__main__":
    main()
