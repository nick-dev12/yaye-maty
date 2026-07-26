"""Compat : lance le test Jumia 20 minutes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    target = Path(__file__).with_name('run_jumia_test_20min.py')
    raise SystemExit(subprocess.call([sys.executable, str(target), *sys.argv[1:]]))
