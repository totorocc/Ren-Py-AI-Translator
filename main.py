"""Ren'Py AI Translator - desktop entry point.

Launches a native desktop window (pywebview) hosting the English UI and wires it
to the Python translation backend.
"""

from __future__ import annotations

import os
import sys

try:
    import webview
except ImportError:
    sys.stderr.write(
        "pywebview is not installed.\n"
        "Install dependencies first:\n"
        "    pip install -r requirements.txt\n"
    )
    sys.exit(1)

from renpy_translator.api import Api


def main() -> None:
    api = Api()
    base = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base, "web", "index.html")

    # IMPORTANT: do NOT store the window on `api`. The window holds a reference
    # back to the js_api object, so `api.window = window` creates a cycle
    # (api -> window -> api) that makes pywebview's bridge setup recurse
    # ("maximum recursion depth exceeded"). The API resolves the active window
    # lazily via webview.active_window() instead.
    webview.create_window(
        "Ren'Py AI Translator",
        url=html_path,
        js_api=api,
        width=1200,
        height=840,
        min_size=(940, 660),
        background_color="#0e1116",
    )
    # debug=False for a clean window; set RPT_DEBUG=1 to enable devtools.
    webview.start(debug=bool(os.environ.get("RPT_DEBUG")))


if __name__ == "__main__":
    main()
