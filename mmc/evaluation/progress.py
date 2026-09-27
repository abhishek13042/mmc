"""Terminal progress + run-logging helpers shared by the exporter and the
evaluator.

* :class:`Status` — timestamped ``step`` lines and an in-place ``bar`` so you can
  watch progress live in the terminal (elapsed seconds included).
* :class:`Tee` — mirrors everything printed to stdout into a log file, so every
  run is saved to disk verbatim (the live ``\\r`` progress bar is written to the
  real console only, never spamming the log).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime


class Tee:
    """Context manager: duplicate stdout into ``path`` while still printing.

    ``with Tee(path): ...`` — normal ``print`` output goes to both the console
    and the log file. Progress bars (which use carriage returns) bypass this and
    hit the raw console only, keeping the log readable.
    """

    def __init__(self, path: str):
        self.path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._f = open(path, "a", encoding="utf-8", buffering=1)
        self._stdout = None

    def write(self, s: str):
        self._stdout.write(s)
        # keep the log clean: skip transient bar updates (start with '\r')
        if not s.startswith("\r"):
            self._f.write(s)

    def flush(self):
        self._stdout.flush()
        self._f.flush()

    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self
        print(f"# run log started {datetime.now():%Y-%m-%d %H:%M:%S} -> {self.path}")
        return self

    def __exit__(self, *exc):
        sys.stdout = self._stdout
        try:
            self._f.close()
        except Exception:
            pass
        return False


class Status:
    """Lightweight progress reporter (no external deps)."""

    def __init__(self, label: str = ""):
        self.t0 = time.time()
        self.label = label

    def elapsed(self) -> float:
        return time.time() - self.t0

    def step(self, msg: str) -> None:
        """A permanent, timestamped progress line (goes to console + log)."""
        print(f"  [{datetime.now():%H:%M:%S}  +{self.elapsed():5.1f}s]  {msg}")

    def bar(self, i: int, total: int, label: str = "", width: int = 22) -> None:
        """In-place progress bar on the real console (bypasses the log).

        Call with ``i`` from 0..total; a newline is emitted when ``i >= total``.
        """
        total = max(total, 1)
        frac = min(i / total, 1.0)
        fill = int(frac * width)
        bar = "#" * fill + "-" * (width - fill)
        line = (f"\r  [{bar}] {i:>3}/{total} ({frac*100:3.0f}%)  "
                f"{label[:48]:<48}  +{self.elapsed():5.1f}s")
        stream = sys.__stdout__            # raw console, never the Tee/log
        stream.write(line)
        stream.flush()
        if i >= total:
            stream.write("\n")
            stream.flush()
