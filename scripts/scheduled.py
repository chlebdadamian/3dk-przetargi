"""Uruchamia komendę przetargi z Harmonogramu zadań (pythonw, bez konsoli) z logiem w data/<nazwa>.log.

    pythonw scripts/scheduled.py daily
    pythonw scripts/scheduled.py fetch --source pz
"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

name = "-".join(a.lstrip("-") for a in sys.argv[1:]) or "przetargi"
log = ROOT / "data" / f"{name}.log"
log.parent.mkdir(exist_ok=True)

with open(log, "a", encoding="utf-8") as out:
    sys.stdout = sys.stderr = out
    print(f"\n=== {datetime.now():%Y-%m-%d %H:%M} {' '.join(sys.argv[1:])}", flush=True)
    sys.argv = ["przetargi", *sys.argv[1:]]
    try:
        from przetargi.__main__ import main
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"exit {e.code}")
    except Exception:
        traceback.print_exc()
