"""Reviewed catalog derived from the canonical live feature definitions."""

from __future__ import annotations

from dataclasses import dataclass

from app.feature_store import FEATURE_DEFINITIONS
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT
from app.real_match_lab_analysis.fingerprint import fingerprint


CATALOG_VERSION = "goalvision-live-78-feature-catalog-v1"


@dataclass(frozen=True, slots=True)
class FeatureCatalogEntry:
    index: int
    feature_name: str
    display_name_lv: str
    description_en: str
    category: str
    explanation_group: str
    unit: str
    direction_semantics: str
    missingness_semantics: str
    expected_range: tuple[str | None, str | None] | None
    source_type: str
    temporal_cutoff_required: bool
    public_display_eligible: bool
    internal_only: bool
    wording_template_lv: str
    quality_dependencies: tuple[str, ...]


_GROUP_LABELS = {
    "HOME_RECENT_FORM":"Mājinieku nesenā forma", "AWAY_RECENT_FORM":"Viesu nesenā forma",
    "HOME_ATTACK":"Mājinieku uzbrukuma rādītāji", "AWAY_ATTACK":"Viesu uzbrukuma rādītāji",
    "HOME_DEFENCE":"Mājinieku aizsardzības rādītāji", "AWAY_DEFENCE":"Viesu aizsardzības rādītāji",
    "VENUE_CONTEXT":"Mājas un izbraukuma konteksts", "SEASON_CONTEXT":"Sezonas konteksts",
    "RELATIVE_STRENGTH":"Komandu relatīvā attiecība", "GOAL_ENVIRONMENT":"Vārtu vides rādītāji",
    "AVAILABILITY":"Sastāvu un spēlētāju pieejamība", "SCHEDULE":"Atpūta un spēļu grafiks",
    "COMPETITION_CONTEXT":"Sacensību konteksts", "DATA_AVAILABILITY":"Datu pieejamība",
}


def _group(name: str) -> str:
    if name.endswith("availability_indicator") or "sample_size" in name or name == "snapshot_completeness_score": return "DATA_AVAILABILITY"
    if any(x in name for x in ("lineup", "injur", "suspension", "missing_key", "goalkeeper")): return "AVAILABILITY"
    if "rest_days" in name or "congestion" in name: return "SCHEDULE"
    if "competition" in name or "derby" in name or "neutral_venue" in name: return "COMPETITION_CONTEXT"
    if name.startswith("combined_") or name.startswith("head_to_head_"): return "GOAL_ENVIRONMENT"
    if "difference" in name: return "RELATIVE_STRENGTH"
    if "season" in name or "league_position" in name: return "SEASON_CONTEXT"
    if "venue" in name or "at_home" in name or "_away_" in name and not name.startswith("away_recent"): return "VENUE_CONTEXT"
    if name.startswith("home_recent"):
        return "HOME_ATTACK" if any(x in name for x in ("scored", "xg_for", "failed_to_score")) else "HOME_DEFENCE" if any(x in name for x in ("conceded", "xg_against", "clean_sheet")) else "HOME_RECENT_FORM"
    if name.startswith("away_recent"):
        return "AWAY_ATTACK" if any(x in name for x in ("scored", "xg_for", "failed_to_score")) else "AWAY_DEFENCE" if any(x in name for x in ("conceded", "xg_against", "clean_sheet")) else "AWAY_RECENT_FORM"
    return "COMPETITION_CONTEXT"


def _unit(name: str) -> str:
    if name.endswith("indicator") or name.endswith("rate") or name == "snapshot_completeness_score": return "RATIO_0_1"
    if "per_match" in name: return "PER_MATCH"
    if "days" in name: return "DAYS"
    if "count" in name or "size" in name or "matches_played" in name: return "COUNT"
    return "MODEL_INPUT_UNIT"


def _entry(index, definition) -> FeatureCatalogEntry:
    group = _group(definition.name)
    expected = None if definition.valid_range is None else tuple(None if value is None else str(value) for value in definition.valid_range)
    public = group not in {"DATA_AVAILABILITY"} and not definition.name.startswith("head_to_head_")
    dependencies = tuple(sorted({"SOURCE_RECENCY", "MISSINGNESS_DISCLOSURE"} | ({"LINEUP_QUALITY"} if "lineup" in definition.name else set()) | ({"INJURY_QUALITY"} if any(x in definition.name for x in ("injur", "missing_key", "suspension")) else set())))
    return FeatureCatalogEntry(index,definition.name,_GROUP_LABELS[group],definition.description,group,group,_unit(definition.name),"TARGET_AND_ARTIFACT_COEFFICIENT_DEPENDENT",definition.missing_data_behavior,expected,";".join(definition.source_fields),True,public,not public,f"Modeļa ievaddati grupā “{_GROUP_LABELS[group]}” {{direction}} izvēli.",dependencies)


CATALOG = tuple(_entry(index, definition) for index, definition in enumerate(FEATURE_DEFINITIONS))
if tuple(item.feature_name for item in CATALOG) != LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names or len(CATALOG) != 78:
    raise RuntimeError("The reviewed explainability catalog does not cover the canonical live-78 contract.")
CATALOG_BY_NAME = {item.feature_name:item for item in CATALOG}
CATALOG_FINGERPRINT = fingerprint({"version":CATALOG_VERSION,"entries":CATALOG})


def group_label(group_id: str) -> str:
    return _GROUP_LABELS[group_id]
