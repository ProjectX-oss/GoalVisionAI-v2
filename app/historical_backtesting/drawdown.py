"""Pure drawdown and streak calculations."""

from decimal import Decimal


def drawdown_state(bankroll: Decimal, peak: Decimal) -> tuple[Decimal, Decimal]:
    absolute = max(Decimal(0), peak - bankroll)
    percentage = absolute / peak if peak > 0 else Decimal(0)
    return absolute, percentage


def longest_streak(values, positive: bool) -> int:
    longest = current = 0
    for value in values:
        matches = value > 0 if positive else value < 0
        current = current + 1 if matches else 0
        longest = max(longest, current)
    return longest


def maximum_drawdown_duration(bankrolls) -> int:
    peak = None
    current = longest = 0
    for bankroll in bankrolls:
        if peak is None or bankroll >= peak:
            peak = bankroll
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest
