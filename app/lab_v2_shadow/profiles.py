"""Versioned, deterministic Lab competition policies; never discovery permissions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
import re
from typing import Mapping

from app.real_match_lab_analysis.fingerprint import fingerprint
from .capability import CapabilityTier, LeagueCapability

from .competition_registry import REGISTRY_VERSION, REGISTRY_FINGERPRINT, reviewed_competition

CLASSIFIER_VERSION = 'LAB_COMPETITION_CLASSIFIER_V4'
POLICY_VERSION = 'LAB_COMPETITION_POLICY_V2'


class CompetitionProfile(StrEnum):
    SENIOR_MEN_PRO = 'SENIOR_MEN_PRO'
    SENIOR_WOMEN_PRO = 'SENIOR_WOMEN_PRO'
    YOUTH_U17_U18 = 'YOUTH_U17_U18'
    YOUTH_U19_U20 = 'YOUTH_U19_U20'
    YOUTH_U21_U23 = 'YOUTH_U21_U23'
    RESERVE_OR_B_TEAM = 'RESERVE_OR_B_TEAM'
    LOWER_DIVISION_OR_SEMIPRO = 'LOWER_DIVISION_OR_SEMIPRO'
    DOMESTIC_CUP = 'DOMESTIC_CUP'
    INTERNATIONAL_CLUB = 'INTERNATIONAL_CLUB'
    INTERNATIONAL_SENIOR = 'INTERNATIONAL_SENIOR'
    INTERNATIONAL_YOUTH = 'INTERNATIONAL_YOUTH'
    FRIENDLY = 'FRIENDLY'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class Classification:
    competition_profile: CompetitionProfile
    classifier_version: str
    classification_reason: str
    classification_fingerprint: str
    flags: tuple[str, ...]
    age_category: str

    def document(self) -> dict:
        return asdict(self)


def classify(league: Mapping, teams: Mapping, fixture: Mapping, capability: LeagueCapability,
             *, overrides: Mapping[int, CompetitionProfile] | None = None) -> Classification:
    """Use reviewed ID overrides/explicit metadata, then narrow auditable patterns.

    Geography alone does not identify national teams. No inferred derby, neutral
    venue, professional status, or first/second leg without supporting metadata.
    """
    name = str(league.get('name') or capability.competition_name).casefold()
    individual_names = tuple(str((teams.get(side) or {}).get('name', '')).casefold() for side in ('home', 'away'))
    team_names = ' '.join(individual_names)
    text = name + ' ' + team_names
    age = re.search(r'\b(?:u[ -]?|under[ -]?)(17|18|19|20|21|23)\b', text)
    category = 'U' + age[1] if age else 'UNSPECIFIED'
    international = 'club world cup' not in name and bool(re.search(r'\b(world cup|euro(?:pean)? championship|nations league|international|africa cup of nations|copa america)\b', name))
    women = bool(re.search(r'\bwomen(?:s|\x27s)?\b|\b(?:femenina|femenil|feminin|feminine|feminina|frauen(?:liga)?|feminino)\b', name)) or league.get('gender') == 'women'
    profile, reason = CompetitionProfile.UNKNOWN, 'UNRECOGNIZED_METADATA'
    reviewed = reviewed_competition(str(league.get("provider", "API_FOOTBALL")), capability.league_id,
                                    str(league.get("country") or capability.country))
    # Explicit caller overrides are separate from the immutable reviewed registry.
    if reviewed is not None:
        profile, reason = CompetitionProfile(reviewed.profile), "REVIEWED_REGISTRY:" + REGISTRY_VERSION
        women = reviewed.gender == "women"
        category = reviewed.age_group
    elif overrides and capability.league_id in overrides:
        profile, reason = CompetitionProfile(overrides[capability.league_id]), 'REVIEWED_LEAGUE_ID_OVERRIDE'
    elif league.get('competition_profile') in CompetitionProfile._value2member_map_:
        profile, reason = CompetitionProfile(league['competition_profile']), 'EXPLICIT_COMPETITION_METADATA'
    elif re.search(r'\bfriendl(?:y|ies)\b', name):
        profile, reason = CompetitionProfile.FRIENDLY, 'NAME_FRIENDLY'
    elif age and international:
        profile, reason = CompetitionProfile.INTERNATIONAL_YOUTH, 'NAME_INTERNATIONAL_AND_AGE'
    elif age:
        profile = (CompetitionProfile.YOUTH_U17_U18 if int(age[1]) <= 18 else
                   CompetitionProfile.YOUTH_U19_U20 if int(age[1]) <= 20 else CompetitionProfile.YOUTH_U21_U23)
        reason = 'NAME_EXPLICIT_AGE_GROUP'
    elif re.search(r'\b(reserves?|b team)\b', text) or any(re.search(r'\s(?:b|ii)$', team) for team in individual_names):
        profile, reason = CompetitionProfile.RESERVE_OR_B_TEAM, 'NAME_RESERVE_OR_B_TEAM'
    elif re.search(r'\b(youth|academy|junior)\b', name):
        category, reason = 'YOUTH_UNSPECIFIED', 'YOUTH_WITHOUT_RELIABLE_AGE'
    elif international:
        profile, reason = CompetitionProfile.INTERNATIONAL_SENIOR, 'NAME_NATIONAL_TEAM_COMPETITION'
    elif re.search(r'\b(champions league|europa league|conference league|libertadores|sudamericana|club world cup|caribbean club championship)\b', name):
        profile, reason = CompetitionProfile.INTERNATIONAL_CLUB, 'NAME_INTERNATIONAL_CLUB'
    elif women:
        profile, reason = CompetitionProfile.SENIOR_WOMEN_PRO, 'NAME_WOMEN_COMPETITION'
    elif _lower_division(name, str(league.get('country') or capability.country)):
        profile, reason = CompetitionProfile.LOWER_DIVISION_OR_SEMIPRO, 'NAME_LOWER_OR_SEMIPRO'
    elif str(league.get('type') or capability.competition_type).casefold() == 'cup':
        profile, reason = CompetitionProfile.DOMESTIC_CUP, 'PROVIDER_CUP_TYPE'
    elif league.get('gender') == 'men' and league.get('level') == 'professional':
        profile, reason = CompetitionProfile.SENIOR_MEN_PRO, 'EXPLICIT_MEN_PRO_METADATA'
    flags = []
    round_name = str(league.get('round', '')).casefold()
    for enabled, flag in (
        (bool(fixture.get('neutral')), 'IS_NEUTRAL_VENUE'),
        (women, 'IS_WOMEN'),
        ('2nd leg' in round_name or 'second leg' in round_name, 'IS_SECOND_LEG'),
        ('qualif' in name + round_name, 'IS_QUALIFIER'),
        ('playoff' in round_name or 'play-off' in round_name, 'IS_PLAYOFF'),
        (any(x in round_name for x in ('final', 'round of', 'leg')), 'IS_KNOCKOUT'),
        (capability.lineups, 'LINEUPS_SUPPORTED'),
        (capability.fixture_statistics, 'STATS_SUPPORTED'),
        (capability.injuries, 'INJURIES_SUPPORTED'),
        (capability.odds, 'CURRENT_ODDS_SUPPORTED'),
    ):
        if enabled:
            flags.append(flag)
    material = (CLASSIFIER_VERSION, REGISTRY_VERSION, REGISTRY_FINGERPRINT, dict(league), team_names, profile, reason, sorted(flags), category)
    return Classification(profile, CLASSIFIER_VERSION, reason, fingerprint(material), tuple(sorted(flags)), category)


def _lower_division(name: str, country: str) -> bool:
    """Explicit lower-tier numbering/names; ambiguous Division One remains unknown.

    Country-scoped terms avoid treating a nation's top-flight '1. Liga' as lower.
    No team or fixture is admitted/excluded by this classification.
    """
    explicit = r"\b(semi[ -]?pro|regional|amateur|oberliga|regionalliga|non league premier|division [2-9]|[2-9]\. (?:liga|lig|division)|ligue [23]|liga (?:ii|iii|2)|serie [bc]|second league|second nl|tercera divisi[oó]n|segunda divisi[oó]n rfef|primera divisi[oó]n rfef|national [23])\b"
    if re.search(explicit, name):
        return True
    scoped = {
        'Japan': r'j[23] league',
        'China': r'league (?:one|two)',
        'Netherlands': r'(?:eerste|tweede|derde) divisie',
        'Poland': r'(?:ii|iii) liga',
        'Argentina': r'primera (?:b metropolitana|nacional|c)',
        'USA': r'usl championship|usl league (?:one|two)',
        'Turkey': r'[123]\. lig',
        'Sweden': r'superettan|ettan',
        'Hungary': r'nb (?:ii|iii)',
        'Thailand': r'thai league [23]',
        'Mexico': r'liga expansi[oó]n mx|liga premier serie [ab]',
        'Paraguay': r'division intermedia',
        'Uruguay': r'segunda divisi[oó]n',
        'Venezuela': r'segunda divisi[oó]n',
        'Slovenia': r'[23]\. snl',
        'Scotland': r'football league - (?:lowland|highland) league',
    }
    pattern = scoped.get(country)
    return bool(pattern and re.search(r'\b(?:' + pattern + r')\b', name))


def fallback_capability(league: Mapping) -> LeagueCapability:
    """Unknown coverage is optional-data uncertainty, never fixture exclusion."""
    return LeagueCapability(int(league['id']), int(league['season']), str(league.get('country') or 'UNKNOWN'),
                            str(league.get('name') or 'UNKNOWN'), str(league.get('type') or 'UNKNOWN'),
                            '', '', True, False, False, False, False, False, False, False,
                            CapabilityTier.TIER_C_BASIC, ('PROVIDER_COVERAGE_UNKNOWN',))


@dataclass(frozen=True)
class ProfilePolicy:
    profile: CompetitionProfile
    version: str = POLICY_VERSION
    uncertainty: Decimal = Decimal('0.015')
    experimental_edge: Decimal = Decimal('0.01')
    standard_edge: Decimal = Decimal('0.04')
    minimum_standard_agreement: Decimal = Decimal('0.75')
    standard_independent_families: int = 2
    strong_independent_families: int = 3
    home_advantage_basis: str = "SAME_COMPETITION_VENUE_RESULTS_ONLY"
    experimental_independent_families: int = 1
    scheduling_weight: int = 1
    history_days: int = 365
    half_life_days: int = 120
    refresh_minutes: tuple[int, ...] = (1440, 360, 75, 30, 10)
    market_preference: tuple[str, ...] = ('1X2', 'BTTS', 'TOTAL_2_5')
    priorities: tuple[tuple[str, str], ...] = ()
    minimum_tuning_selections: int = 200
    minimum_tuning_days: int = 90

    def weight(self, feature: str) -> Decimal:
        priority = dict(self.priorities).get(feature, 'LOW')
        return {'HIGH': Decimal('1'), 'MEDIUM': Decimal('0.65'), 'LOW': Decimal('0.25'), 'IGNORE': Decimal(0)}[priority]


def policy_for(profile: str) -> ProfilePolicy:
    """Initial experimental defaults, not empirically fitted competition claims."""
    p = CompetitionProfile(profile)
    youth = p in {CompetitionProfile.YOUTH_U17_U18, CompetitionProfile.YOUTH_U19_U20,
                  CompetitionProfile.YOUTH_U21_U23, CompetitionProfile.INTERNATIONAL_YOUTH}
    volatile = youth or p in {CompetitionProfile.RESERVE_OR_B_TEAM, CompetitionProfile.FRIENDLY}
    unknown = p == CompetitionProfile.UNKNOWN
    priorities = dict(current_odds='HIGH', recent_form='HIGH', scoring='HIGH', lineup='HIGH',
                      opponent_strength='HIGH', home_away='MEDIUM', injuries='MEDIUM',
                      standings='MEDIUM', advanced_stats='LOW', long_term_strength='MEDIUM',
                      old_h2h='LOW', senior_strength='IGNORE', competition_state='MEDIUM', travel_rest='MEDIUM')
    if p == CompetitionProfile.SENIOR_MEN_PRO:
        priorities.update(advanced_stats='HIGH', home_away='HIGH')
    if volatile:
        priorities.update(long_term_strength='LOW', standings='LOW', competition_state='HIGH')
    if p in {CompetitionProfile.DOMESTIC_CUP, CompetitionProfile.INTERNATIONAL_CLUB}:
        priorities.update(competition_state='HIGH', lineup='HIGH', long_term_strength='HIGH')
    if p == CompetitionProfile.INTERNATIONAL_SENIOR:
        priorities.update(long_term_strength='HIGH', competition_state='HIGH', home_away='LOW')
    if p == CompetitionProfile.LOWER_DIVISION_OR_SEMIPRO:
        priorities.update(advanced_stats='IGNORE', lineup='MEDIUM', home_away='HIGH')
    if unknown:
        priorities.update(advanced_stats='IGNORE', long_term_strength='LOW', home_away='LOW')
    return ProfilePolicy(p, home_advantage_basis="WOMEN_SAME_COMPETITION_VENUE_RESULTS_ONLY" if p == CompetitionProfile.SENIOR_WOMEN_PRO else "SAME_COMPETITION_VENUE_RESULTS_ONLY", uncertainty=Decimal('0.025') if volatile or unknown else Decimal('0.020') if p in {CompetitionProfile.LOWER_DIVISION_OR_SEMIPRO, CompetitionProfile.SENIOR_WOMEN_PRO} else Decimal('0.015'),
                         experimental_edge=Decimal('0.015') if volatile or unknown else Decimal('0.01'),
                         history_days=120 if youth else 180 if volatile else 365,
                         half_life_days=45 if p == CompetitionProfile.YOUTH_U21_U23 else 30 if youth else 60 if volatile else 120,
                         refresh_minutes=(1440, 360, 75, 45, 20, 10) if volatile else (1440, 360, 75, 30, 10),
                         market_preference=('BTTS', 'TOTAL_2_5', '1X2') if volatile else ('1X2', 'BTTS', 'TOTAL_2_5'),
                         priorities=tuple(sorted(priorities.items())))
