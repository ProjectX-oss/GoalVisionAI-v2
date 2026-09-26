"""Strict global identity, local shortlist and explicit missing LIVE features."""
from __future__ import annotations

from datetime import datetime
from .contracts import digest, integer, utc

STAT_FIELDS = ('Shots on Goal', 'Total Shots', 'Shots insidebox', 'Goalkeeper Saves',
               'Corner Kicks', 'Ball Possession', 'Total passes', 'Passes accurate',
               'Passes %', 'Yellow Cards', 'Red Cards')


def fixture_state(row: dict, now: datetime, competitions: frozenset[int]) -> dict:
    """Normalize only regulation 1H/2H, with complete identity and plausible time."""
    f, league, teams = row['fixture'], row['league'], row['teams']
    home, away = teams['home'], teams['away']
    goals, status = row['goals'], f['status']
    minute, phase = status.get('elapsed'), status.get('short')
    if not all(integer(x, 1) for x in (f['id'], league['id'], home['id'], away['id'])) or home['id'] == away['id']:
        raise ValueError('FIXTURE_IDENTITY_INVALID')
    if league['id'] not in competitions or not integer(league.get('season'), 2000, 2200):
        raise ValueError('UNSUPPORTED_COMPETITION')
    if phase not in {'1H', '2H'}:
        raise ValueError('NOT_IN_PROGRESS_REGULATION')
    if not integer(minute, 10, 82) or (phase == '1H' and minute > 45) or (phase == '2H' and minute < 46):
        raise ValueError('UNSUITABLE_MINUTE')
    if not all(integer(goals.get(k), 0, 20) for k in ('home', 'away')):
        raise ValueError('INVALID_SCORE')
    age = (utc(now)-utc(f['date'])).total_seconds()/60
    if not minute-3 <= age <= minute+35:
        raise ValueError('KICKOFF_MINUTE_INCOHERENT')
    if not all(isinstance(x, str) and x.strip() for x in (home.get('name'), away.get('name'), league.get('name'))):
        raise ValueError('IDENTITY_NAMES_MISSING')
    return {'fixture_id': f['id'], 'league_id': league['id'], 'league': league['name'],
            'season': league['season'], 'home_id': home['id'], 'away_id': away['id'],
            'home': home['name'], 'away': away['name'], 'kickoff': utc(f['date']).isoformat(),
            'status': phase, 'minute': minute, 'home_score': goals['home'], 'away_score': goals['away'],
            'retrieved_at': utc(now).isoformat(), 'source_fingerprint': digest(row)}


def shortlist(rows: list[dict], now: datetime, competitions: frozenset[int],
              contexts: dict[int, dict] | None = None) -> tuple[dict | None, list[dict]]:
    """Screen all rows without I/O; enrich at most one. Conflicting IDs abort selection."""
    contexts = contexts or {}
    accepted, decisions, seen = [], [], {}
    for row in rows:
        identity = row.get('fixture', {}).get('id')
        fingerprint = digest(row)
        if identity in seen and seen[identity] != fingerprint:
            return None, [{'reason': 'GLOBAL_IDENTITY_CONFLICT', 'fixture_id': identity}]
        if identity in seen:
            continue
        seen[identity] = fingerprint
        try:
            state = fixture_state(row, now, competitions)
            context = contexts.get(identity, {})
            rank = (bool(context.get('live_odds_coverage')), bool(context.get('prematch_context')),
                    -abs(60-state['minute']), -abs(state['home_score']-state['away_score']), -identity)
            accepted.append((rank, state))
            decisions.append({'fixture_id': identity, 'reason': 'ELIGIBLE', 'rank': list(rank)})
        except (KeyError, ValueError, TypeError) as exc:
            reason = str(exc) if type(exc) is ValueError else 'MALFORMED_FIXTURE'
            decisions.append({'fixture_id': identity, 'reason': reason})
    return max(accepted, key=lambda pair: pair[0])[1] if accepted else None, decisions


def features(state: dict, statistics: list[dict], events: list[dict] | None) -> dict:
    """Freeze actual provider fields. Unknown cards/shots remain None."""
    output: dict = {'home': {}, 'away': {}, 'red_cards': None, 'substitutions': None,
                    'contradictions': [], 'events_complete': events is not None}
    expected = {state['home_id']: 'home', state['away_id']: 'away'}
    seen = set()
    for row in statistics:
        team = row.get('team', {}).get('id')
        if team not in expected or team in seen:
            output['contradictions'].append('STATISTICS_TEAM_IDENTITY')
            continue
        seen.add(team)
        values = {s.get('type'): s.get('value') for s in row.get('statistics', [])}
        for field in STAT_FIELDS:
            raw = values.get(field)
            try:
                value = float(str(raw).removesuffix('%')) if raw is not None else None
                upper = 100 if field in {'Ball Possession', 'Passes %'} else 10000
                if value is not None and (not 0 <= value <= upper or
                    (field not in {'Ball Possession', 'Passes %'} and not value.is_integer())):
                    raise ValueError
                output[expected[team]][field] = value
            except (ValueError, TypeError):
                output[expected[team]][field] = None
                output['contradictions'].append('INVALID_STATISTIC')
    for side in ('home', 'away'):
        for field in STAT_FIELDS:
            output[side].setdefault(field, None)
        shots, sot = (output[side][k] for k in ('Total Shots', 'Shots on Goal'))
        if shots is not None and sot is not None and sot > shots:
            output['contradictions'].append('SOT_EXCEEDS_SHOTS')
    if events is not None:
        cards = {'home': 0, 'away': 0}
        substitutions = {'home': 0, 'away': 0}
        goals = {'home': 0, 'away': 0}
        red_players = set()
        for event in events:
            team = event.get('team', {}).get('id')
            minute = event.get('time', {}).get('elapsed')
            if team not in expected or not integer(minute, 0, state['minute']):
                output['contradictions'].append('EVENT_STATE_MISMATCH')
                continue
            side = expected[team]
            if event.get('type') == 'Goal':
                if event.get('detail') in {'Normal Goal', 'Penalty'}:
                    goals[side] += 1
                elif event.get('detail') != 'Missed Penalty':
                    output['contradictions'].append('AMBIGUOUS_GOAL_EVENT')
            if event.get('type') == 'Var':
                output['contradictions'].append('VAR_REQUIRES_STATE_REVIEW')
            if event.get('type') == 'Card' and event.get('detail') in {'Red Card', 'Second Yellow card'}:
                player = event.get('player', {}).get('id')
                if not integer(player, 1):
                    output['contradictions'].append('RED_CARD_PLAYER_UNKNOWN')
                elif (team, player) not in red_players:
                    cards[side] += 1
                    red_players.add((team, player))
            if event.get('type') == 'subst':
                substitutions[side] += 1
        output['red_cards'], output['substitutions'] = cards, substitutions
        for side in ('home', 'away'):
            if goals[side] != state[side+'_score']:
                output['contradictions'].append('EVENT_SCORE_DISAGREEMENT')
            observed = output[side]['Red Cards']
            if observed is not None and observed != cards[side]:
                output['contradictions'].append('RED_CARD_DISAGREEMENT')
    required = [output[s][f] for s in ('home', 'away') for f in ('Shots on Goal', 'Total Shots')]
    output['completeness'] = (sum(v is not None for v in required) + (output['red_cards'] is not None))/5
    output['source_fingerprint'] = digest([statistics, events])
    return output
