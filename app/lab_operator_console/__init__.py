"""Local, server-rendered GoalVision AI Lab operator console."""

from .config import CONSOLE_VERSION, ConsoleConfig
from .web import ConsoleApplication

__all__=["CONSOLE_VERSION","ConsoleApplication","ConsoleConfig"]
