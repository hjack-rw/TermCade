"""PyInstaller entry point for the standalone desktop build.

A thin __main__ so the launcher's package-relative imports resolve (a PyInstaller entry script runs
as __main__, outside any package). Everything real lives in ``xiaolin_showdown.launch``.
"""

from __future__ import annotations

from xiaolin_showdown.launch import main

if __name__ == "__main__":
    main()
