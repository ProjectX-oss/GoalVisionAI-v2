"""Pinned standalone import root, independent of PREMATCH PYTHONPATH and packages."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.admin_alerts.cli import main

raise SystemExit(main())
