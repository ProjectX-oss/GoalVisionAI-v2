"""Pinned standalone worker import root, independent of production PYTHONPATH."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.admin_autorepair.worker import main

raise SystemExit(main())
