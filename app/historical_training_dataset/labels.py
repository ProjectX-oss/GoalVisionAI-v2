"""Deterministic supported-market labels derived only from the final score."""

from .exceptions import SourceProvenanceError
from .models import HistoricalSourceMatch


LABEL_ORDER = (
    "HOME_WIN", "DRAW", "AWAY_WIN",
    "OVER_1_5", "UNDER_1_5",
    "OVER_2_5", "UNDER_2_5",
    "OVER_3_5", "UNDER_3_5",
    "BTTS_YES", "BTTS_NO",
)


def generate_labels(match: HistoricalSourceMatch) -> tuple[tuple[str, int], ...]:
    home = match.full_time_home_score
    away = match.full_time_away_score
    if type(home) is not int or type(away) is not int or home < 0 or away < 0:
        raise SourceProvenanceError("Eligible matches require a valid final score.")
    total = home + away
    values = {
        "HOME_WIN": int(home > away),
        "DRAW": int(home == away),
        "AWAY_WIN": int(home < away),
        "OVER_1_5": int(total >= 2),
        "UNDER_1_5": int(total <= 1),
        "OVER_2_5": int(total >= 3),
        "UNDER_2_5": int(total <= 2),
        "OVER_3_5": int(total >= 4),
        "UNDER_3_5": int(total <= 3),
        "BTTS_YES": int(home > 0 and away > 0),
        "BTTS_NO": int(home == 0 or away == 0),
    }
    labels = tuple((name, values[name]) for name in LABEL_ORDER)
    validate_labels(labels)
    return labels


def validate_labels(labels: tuple[tuple[str, int], ...]) -> None:
    if tuple(name for name, _ in labels) != LABEL_ORDER:
        raise SourceProvenanceError("Label order differs from the v1 schema.")
    values = dict(labels)
    if any(type(value) is not int or value not in (0, 1) for value in values.values()):
        raise SourceProvenanceError("Labels must be binary integers.")
    if sum(values[name] for name in ("HOME_WIN", "DRAW", "AWAY_WIN")) != 1:
        raise SourceProvenanceError("Exactly one match-result label must be positive.")
    for over, under in (("OVER_1_5", "UNDER_1_5"), ("OVER_2_5", "UNDER_2_5"), ("OVER_3_5", "UNDER_3_5"), ("BTTS_YES", "BTTS_NO")):
        if values[over] + values[under] != 1:
            raise SourceProvenanceError("Complementary labels must sum to one.")
    if not values["OVER_3_5"] <= values["OVER_2_5"] <= values["OVER_1_5"]:
        raise SourceProvenanceError("Goal-total labels must be monotonic.")
