"""Versioned incident facts. Untrusted strings never become diagnostic text."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from zoneinfo import ZoneInfo

UNITS = (
    'goalvision-lab-v2-discover.service', 'goalvision-lab-combo-settle.service',
    'goalvision-adaptive-learning-observer.service', 'goalvision-adaptive-learning.service',
    'goalvision-lab-weekly-stats.service',
)
DISCOVERY = UNITS[0]
SCHEMA = 'goalvision-lab-v2-operator-cycle-v1'
RULE_VERSION = 1
LABELS = {
    'QUOTA_DB_CONTENTION': 'API kvotas rezervācijas datubāzes konflikts',
    'SERVICE_FAILURE': 'Serviss beidzās ar kļūdu',
    'ANALYSIS_FAILURE': 'Analīze beidzās ar kļūdu',
    'DELIVERY_FAILURE': 'Publikācijas piegādes kļūda',
    'DELIVERY_UNCERTAIN': 'Publikācijas piegāde nav droši apstiprināta',
    'CYCLE_PERSISTENCE': 'Cikla pierādījumu saglabāšanas kļūda',
    'INTEGRITY_FAILURE': 'Datu integritātes pārbaude neizdevās',
    'OBSERVATION_FAILURE': 'Novērojuma izveides vai pabeigšanas kļūda',
    'PROVIDER_FAILURE': 'Atkārtota datu avota kļūda',
    'AUTH_FAILURE': 'Autentifikācija neizdevās',
    'QUOTA_FAILURE': 'Atkārtoti nepietiekami dati vai API kvota',
    'DATABASE_LOCK': 'Atkārtota datubāzes bloķēšana',
    'MISSING_START': 'Nav pierādījumu par plānoto servisa sākumu',
    'RUNNING_LONG': 'Serviss pārsniedz konfigurēto izpildes laiku',
    'MISSING_OUTPUT': 'Pabeigtam ciklam trūkst sagaidāmā izvades ieraksta',
    'TIMER_INACTIVE': 'Plānotā uzdevuma taimeris nav aktīvs',
    'MONITORING_COVERAGE_DEGRADED': 'Daļa uzraudzības pierādījumu nav pieejama',
    'ADMIN_DELIVERY_DEGRADED': 'ADMIN paziņojumu piegāde ir traucēta',
}


def digest(value: object) -> str:
    """Stable identifiers never contain input text."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:24]


def identity(value: object) -> str:
    """Keep only established machine identifiers; hash everything else."""
    if isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', value):
        # Bot tokens, URLs, headers, and free text cannot pass this grammar.
        return value
    return 'UNKNOWN' if value is None else 'redacted-' + digest(value)


def epoch(value: object) -> float:
    """Parse source ISO timestamps only; invalid evidence stays unknown."""
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.timestamp() if stamp.tzinfo else 0
    except (ValueError, OverflowError):
        return 0


@dataclass(frozen=True)
class Event:
    """Sanitized occurrence; event key identifies evidence, signature identifies issue."""
    service: str
    rule: str
    object_id: str
    occurrence: str
    observed: float
    source: str
    severity: int = 2
    invocation: str = 'UNKNOWN'
    cycle: str = 'UNKNOWN'
    facts: dict = field(default_factory=dict)
    healthy: bool = False
    debounce: int = 1

    @property
    def signature(self) -> str:
        if self.rule == 'MONITORING_COVERAGE_DEGRADED' and self.source in ('ledger', 'weekly') and self.facts.get('reason') != 'UNRESOLVED_SCAN_IN_PROGRESS':
            return digest((2, self.service, self.rule, self.object_id))
        from .correlation import EXECUTION_RULES
        if self.rule in EXECUTION_RULES:
            execution = self.invocation if self.invocation != 'UNKNOWN' else self.occurrence
            return digest((RULE_VERSION, self.service, self.rule, self.object_id, execution))
        return digest((RULE_VERSION, self.service, self.rule, self.object_id))

    @property
    def key(self) -> str:
        return digest((self.signature, self.occurrence, self.healthy))

    def document(self) -> dict:
        """Export facts constructed by allowlisted adapters only."""
        return asdict(self)


def coverage(source: str, now: float, reason: str, *, object_id: str | None = None) -> Event:
    return Event('monitor', 'MONITORING_COVERAGE_DEGRADED', object_id or source,
                 reason, now, source, facts={'reason': reason})


ROTATION_GAP_REASONS = frozenset(("ROTATED_INODE_LOST", "FILE_TRUNCATED", "FILE_REWRITTEN"))


def rotation_gap_reason(row: dict) -> str | None:
    """Classify only retained stdout rotation gaps; unknown faults stay alertable."""
    if (row["service"] != "monitor" or row["rule"] != "MONITORING_COVERAGE_DEGRADED"
            or row["object_id"] != "stdout-rotation"):
        return None
    try:
        evidence = json.loads(row["evidence"])
        reason = evidence.get("facts", {}).get("reason")
        if evidence.get("source") == "stdout" and reason in ROTATION_GAP_REASONS:
            return reason
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def acknowledged_rotation_gap(row: dict) -> bool:
    """A historical gap remains recorded, but needs no timer-only reminder."""
    return bool(rotation_gap_reason(row) and row["state"] in ("OPEN", "REPEATED", "ESCALATED")
                and row["notified_state"] == "OPEN" and row["last_sent"] > 0
                and row["last_seen"] <= row["last_sent"])


def alert(row: dict, group: dict | None = None) -> str:
    """Concise Latvian plain text; includes identifiers useful after forwarding."""
    restored = row['state'] == 'RECOVERED'
    heading = '✅ GoalVision ADMIN • Darbība atjaunota' if restored else '🚨 GoalVision ADMIN • PREMATCH'
    when = datetime.fromtimestamp(row['last_seen'], timezone.utc).astimezone(ZoneInfo('Europe/Riga'))
    quota = row['rule'] == 'QUOTA_DB_CONTENTION'
    gap_reason = rotation_gap_reason(row) if not restored else None
    members = group['members'] if group else [row]
    status = 'darbība atjaunota' if restored else 'cikls beidzās ar kļūdu' if any(r['rule'] == 'SERVICE_FAILURE' for r in members) else 'nepieciešama pārbaude'
    codes = sorted({json.loads(r['evidence']).get('facts', {}).get('code', r['rule']) for r in members})
    if gap_reason:
        codes = [gap_reason]
        status = 'žurnāla nepilnība saglabāta pārbaudei'
    return '\n'.join((heading, f"Kļūda: {LABELS[row['rule']]}",
        f"Serviss: {'PREMATCH Discovery' if row['service'] == DISCOVERY else row['service']}",
        f"Posms: {row['rule']}",
        'Ietekme: šis API pieprasījums netika sākts' if quota else 'Ietekme: darbība atjaunota' if restored else 'Ietekme: daļu agrākās izvades nevar pārbaudīt' if gap_reason else 'Ietekme: rezultāts jāpārbauda',
        'Statuss: kvotas datubāze bija aizņemta ilgāk par drošo 500 ms robežu' if quota else f"Statuss: {status}",
        'Pierādījumi: ' + ', '.join(codes), f"Incidents: {row['id']}",
        f"Invocation: {group['invocation'] if group else row['invocation']}",
        f"Laiks: {when:%Y-%m-%d %H:%M:%S} Europe/Riga (Latvija)", f"Atkārtojumi: {row['count']}",
        'Darbība: Pārbaudīt sanitizēto incidenta pārskatu.'))[:3000]
