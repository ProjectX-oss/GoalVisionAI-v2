"""Pinned research semantics; never resolves the mutable runtime profile policy."""
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN
from enum import StrEnum

CONTRACT = 'PREMATCH_FOOTBALL_CONTEXT_V1'
SEMANTICS = 'PREMATCH_FOOTBALL_CONTEXT_V2_SEMANTICS_1'
PROFILE_POLICY = 'FC_OBSERVED_HISTORY_POLICY_V1'
PI_ALGORITHM = 'GV_PI_RATIONAL_REPLAY_V1'
ARITHMETIC = 'FC_DECIMAL28_HALF_EVEN_V1'
CANONICAL = 'FC_CANONICAL_JSON_V1'
FEATURE_NAMES = (
    'home_team_observed_weighted_scoring_rate',
    'home_team_observed_weighted_conceding_rate',
    'away_team_observed_weighted_scoring_rate',
    'away_team_observed_weighted_conceding_rate',
    'home_team_current_pi_adjusted_form',
    'away_team_current_pi_adjusted_form',
    'pi_designated_side_rating_difference',
)
REASONS = ('UNSUPPORTED_PROFILE', 'REGULATION_UNVERIFIED', 'UNSUPPORTED_REGULATION',
           'SOURCE_UNAVAILABLE', 'STALE_SOURCE', 'CONFLICTING_FACTS',
           'STALE_TEAM_HISTORY', 'INSUFFICIENT_SAMPLE', 'UNSUPPORTED_PI_STATE')


class Profile(StrEnum):
    SENIOR_MEN_PRO = 'SENIOR_MEN_PRO'
    SENIOR_WOMEN_PRO = 'SENIOR_WOMEN_PRO'
    LOWER_DIVISION_OR_SEMIPRO = 'LOWER_DIVISION_OR_SEMIPRO'
    DOMESTIC_CUP = 'DOMESTIC_CUP'
    INTERNATIONAL_CLUB = 'INTERNATIONAL_CLUB'
    INTERNATIONAL_SENIOR = 'INTERNATIONAL_SENIOR'
    YOUTH_U17_U18 = 'YOUTH_U17_U18'
    YOUTH_U19_U20 = 'YOUTH_U19_U20'
    INTERNATIONAL_YOUTH = 'INTERNATIONAL_YOUTH'
    YOUTH_U21_U23 = 'YOUTH_U21_U23'
    RESERVE_OR_B_TEAM = 'RESERVE_OR_B_TEAM'
    FRIENDLY = 'FRIENDLY'
    UNKNOWN = 'UNKNOWN'


def decimal_context() -> Context:
    """New explicit context, independent even of the caller's traps/exponent limits."""
    return Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                   capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])


def history_policy(profile: Profile) -> tuple[int, int] | None:
    """Return the version-pinned (horizon, half-life), in exact days."""
    if not isinstance(profile, Profile):
        raise ValueError('INVALID_PROFILE')
    if profile == Profile.UNKNOWN:
        return None
    if profile in (Profile.YOUTH_U17_U18, Profile.YOUTH_U19_U20, Profile.INTERNATIONAL_YOUTH):
        return 120, 30
    if profile == Profile.YOUTH_U21_U23:
        return 120, 45
    if profile in (Profile.RESERVE_OR_B_TEAM, Profile.FRIENDLY):
        return 180, 60
    return 365, 120


def feature_range(index: int) -> tuple[Decimal, Decimal]:
    """Inclusive validation bounds; never clipping bounds."""
    if not 0 <= index < 7:
        raise ValueError('UNKNOWN_FEATURE')
    return (Decimal('-79.2'), Decimal('79.2')) if index == 6 else (
        Decimal(0), Decimal(30 if index < 4 else 1))


def semantic_manifest() -> dict[str, object]:
    """Fresh machine-readable manifest; future vector semantics are declarations only."""
    meanings = (
        'Target designated-home team all-venue observed regulation goals scored',
        'Target designated-home team all-venue observed regulation goals conceded',
        'Target designated-away team all-venue observed regulation goals scored',
        'Target designated-away team all-venue observed regulation goals conceded',
        'Home current-strength re-evaluation; decision-time Pi, not historical prematch strength',
        'Away current-strength re-evaluation; decision-time Pi, not historical prematch strength',
        'Target home designated-home rating minus target away designated-away rating',
    )
    return {
        'contract': CONTRACT, 'semantics': SEMANTICS, 'profile_policy': PROFILE_POLICY,
        'pi_algorithm': PI_ALGORITHM, 'arithmetic': ARITHMETIC, 'canonical': CANONICAL,
        'features': tuple({'name': name, 'meaning': meanings[i], 'range': feature_range(i),
                           'unit': 'goals per observed 90-minute fixture' if i < 4 else
                           'dimensionless performance' if i < 6 else 'local Pi rating units'}
                          for i, name in enumerate(FEATURE_NAMES)),
        'profiles': {p.value: history_policy(p) for p in Profile},
        'arithmetic_rules': {'precision': 28, 'rounding': 'ROUND_HALF_EVEN',
            'microseconds_per_day': 86400000000, 'intermediate_quantization': False,
            'weight_power': 'exponent=-(d0-di in exact days)/L; exp(exponent*ln(2)); round each Decimal operation at precision 28',
            'final_places': 6, 'negative_zero': '0.000000', 'invalid': 'hard error; no clipping'},
        'serialization': {'encoding': 'UTF-8', 'unicode': 'NFC', 'sort_keys': True,
            'separators': (',', ':'), 'ensure_ascii': False, 'json_floats': False,
            'timestamps': 'UTC YYYY-MM-DDTHH:MM:SS.ffffffZ',
            'intermediates': 'exact plain decimal; strip fractional trailing zeros; zero=0',
            'arrays': 'ordered', 'unknown_keys': 'reject; typed contracts only',
            'hash': 'SHA-256(domain + newline + canonical bytes); exclude self hash and write receipts',
            'domains': ('FC_SEMANTICS_V1', 'FC_SOURCE_BUNDLE_V1', 'FC_PI_STATE_V1',
                        'FC_SNAPSHOT_V1', 'LAB_VECTOR_V2', 'LAB_ARTIFACT_V2')},
        'scope': {'provider': 'API_FOOTBALL', 'namespace': ('provider', 'competition_id', 'team_id'),
            'identity_evidence': 'pinned gender/age/team category/classification; no name matching',
            'history_scope': 'OBSERVED_COMPETITION_QUERY', 'complete_team_history': False,
            'current_query': '/fixtures(results): league=C, season=S, status=FT, last=99',
            'previous_query': 'optional same query season=S-1; no fetch fallback',
            'max_response_entries': 99, 'max_pool': 198, 'oversize': 'invalidate response',
            'competition': 'exact only, including cup/international; no strength transfer',
            'season': 'current and optional previous only; no reset/decay',
            'ordering': 'UTC kickoff then numeric fixture ID; selection descending; replay ascending',
            'duplicates': 'identical collapse; conflicting facts quarantine from every calculation'},
        'eligibility': {'kickoff': '[T-H,T); always exclude target fixture; T<K',
            'identity': 'positive integer distinct team IDs; same provider/entity scope',
            'score': 'integer pair 0..30; reject pair together', 'finished': ('FT', 'AET', 'PEN'),
            'format': 'verified 90 minutes each included competition-season; unknown/other missing',
            'fulltime': 'prefer explicit pair; FT goals fallback only verified 90; AET/PEN require fulltime',
            'excluded': 'awarded/abandoned/suspended/postponed/cancelled/ongoing; ET/shootout/aggregate goals',
            'neutral': 'TRUE/FALSE/UNKNOWN retained; designation unchanged'},
        'source_rules': {'current_required': True, 'previous_optional': True,
            'current_age_hours_exclusive': 6, 'previous_age_hours_exclusive': 24,
            'target_age_minutes_exclusive': 15, 'expiry': 'T<expiry',
            'asof': 'provider_updated_at<=retrieval_completed_at<=known_at<=T; registered_at<=T',
            'equality_T': 'requires proven durable availability before capture transaction',
            'missing_provider_time': 'null; UNKNOWN; known_at=completion or later registration',
            'old_provider_update': 'does not expire fresh completed-result collection',
            'unproven_start_time': 'ASOF_UNPROVEN; never completion evidence',
            'selection': 'bounded exact query; latest completion, latest registration, ascending hash/id',
            'invalid_latest': 'no convenient older fallback',
            'pins': 'immutable retained sanitized facts including exclusions; correction is new version',
            'replay': 'verify retained evidence; missing/corrupt hard EVIDENCE_UNAVAILABLE; never fetch',
            'phase_a_boundary': 'validate supplied facts/known-at/freshness verdict only; no source readers'},
        'rates': {'min_N': 3, 'max_N': 8, 'venues': 'both', 'anchor': 'latest SELECTED kickoff',
            'formula': 'sum(w_i*X_i)/sum(w_i), X=GF or GA, latest-first sum',
            'effective_N': '(sum w)^2/sum(w^2); diagnostic only',
            'adjustments': 'none; no opponent/form/availability/xG/league mean'},
        'recency': 'latest eligible target game age<=min(H,120) days at T',
        'pi': {'seed': 'both dimensions Decimal(0)', 'pool': 'all valid unique bounded competition games',
            'e': '(GF_h-GF_a)-(r(h,H)-r(a,A))', 'u': 'e/(1+0.75*abs(e))',
            'updates': ('h.H+=0.15*u', 'h.A+=0.10*u', 'a.H-=0.10*u', 'a.A-=0.15*u'),
            'simultaneous': 'all read OLD state', 'support_total': 8, 'support_designated': 3,
            'difference': 'r(target_home,H)-r(target_away,A)', 'warm_start': False},
        'form': {'sample': 'same all-venue latest-eight as rates; min 3; no substitutions',
            'x': 'r(team,designation)-r(opponent,opposite designation) at T including sampled games',
            'expected': '0.5+x/(2*(1+abs(x))); rational, not logistic',
            'actual': ('win=1', 'draw=0.5', 'loss=0'),
            'margin': 'clamp(0.025*(GF-GA),-0.10,0.10)',
            'performance': 'clamp(0.5+actual-expected+margin,0,1)',
            'rank': 'a_i=N-i; latest-first zero-based', 'formula': 'sum(a_i*performance_i)/(N*(N+1)/2)',
            'support_total_each_team_opponent': 4, 'support_used_dimension_each': 1,
            'any_unsupported': 'whole side null UNSUPPORTED_PI_STATE; retain selected opponents'},
        'missingness': {'statuses': ('AVAILABLE', 'MISSING'), 'reasons_ordered': REASONS,
            'value': 'decimal iff AVAILABLE; otherwise null; supported zero is available',
            'counts': 'unavailable source=null; valid empty pool=0',
            'exclusions': 'do not null sufficient remaining sample; separate diagnostics',
            'freshness': ('FRESH_COLLECTION', 'STALE_COLLECTION', 'UNAVAILABLE'),
            'source_identity_hash_cutoff_violation': 'hard validation error'},
        'future_vector_declaration': {'schema': 'LAB_FROZEN_FEATURES_V2', 'stream': 'PREMATCH',
            'ordered_names': ('prior_probability', 'implied_probability', 'uncertainty',
                'signal_cmi_probability', 'signal_pi_probability', 'signal_api_probability', 'family_count') + FEATURE_NAMES,
            'base_rules': ('frozen accepted baseline 0<p<1', '1/exact frozen odds>1; 0<p<1',
                'profile uncertainty + captured missing penalties weight*0.005',
                'sole matching-market provenance CMI [0,1]', 'sole matching-market provenance Pi [0,1]',
                'sole matching-market provenance API [0,1]',
                'distinct qualifying predictive independence groups; exclude current market consensus'),
            'validation': 'frozen source pins <=T; no champion fallback; required probabilities cannot round to 0/1',
            'mask': '1 missing; 0 present', 'signal_reasons': ('SIGNAL_UNAVAILABLE', 'AMBIGUOUS_SIGNAL'),
            'transformer': 'LAB_MEDIAN_SCALE_MASK_V2', 'registry': 'LAB_MODEL_REGISTRY_V2',
            'transform': 'TRAIN-only available median (even mean); impute; population mean/std; zero std=1; binary64 pinned runtime; clip scaled to [-10,10]; interleave missing bit',
            'all_missing_TRAIN': 'median=mean=0 scale=1 -> [0,1]; later present rejects UNSUPPORTED_FEATURE_COVERAGE',
            'coordinates': 28, 'subsets': (7, 11, 14),
            'isolation': 'V1/LIVE unchanged; strict version/hash/order dispatch; V2 prospective only',
            'split': 'prior split hardening prerequisite; fixture groups; sealed boundary/reservations; strict 24h embargo; TRAIN fit VALIDATION rank; holdout gates unchanged'},
        'rest_days': 'excluded; observed competition history cannot certify completeness',
    }
