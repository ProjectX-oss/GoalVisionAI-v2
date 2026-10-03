"""Second offline timer; original V1 and production services are busy guards."""
from argparse import Namespace
from datetime import datetime
from typing import Callable
from app.dixon_coles_research import worker as bounded
from app.dixon_coles_research.contracts import utc
from .contracts import load_plan, VERSION
from .cli import run_report

SERVICES = bounded.SERVICES + ("goalvision-dixon-coles-research.service",)

def in_slot(now: datetime) -> bool:
    value = utc(now)
    return value.minute in (12, 42) and 30 <= value.second < 60

def cycle(args: Namespace, *, now: Callable[[], datetime] = bounded.clock,
          idle: Callable[[], bool] | None = None, execute: Callable = run_report) -> dict:
    # Protect original research even during the post-window enrollment path.
    from .cli import ORIGINAL_RESEARCH
    if (args.research_database.absolute().resolve() == ORIGINAL_RESEARCH.resolve()
            or (args.research_database.exists() and ORIGINAL_RESEARCH.exists()
                and args.research_database.samefile(ORIGINAL_RESEARCH))):
        raise ValueError("ORIGINAL_RESEARCH_OUTPUT_FORBIDDEN")
    return bounded.cycle(args, now=now,
        idle=idle or (lambda: bounded.production_idle(SERVICES)), execute=execute,
        plan_loader=load_plan, slot=in_slot, record_version=VERSION,
        extra_protected_paths=(ORIGINAL_RESEARCH,))

def main(argv: list[str] | None = None) -> int:
    return bounded.main(argv, cycle_function=cycle)

if __name__ == "__main__":
    raise SystemExit(main())
