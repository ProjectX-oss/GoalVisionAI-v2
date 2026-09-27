"""No-network activation boundary shared by operations and offline tests."""
from __future__ import annotations

from dataclasses import replace
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from .correlation import supersede, groups, EXECUTION_RULES, EPOCH_POLICY, epoch_hold
from .delivery import SenderConfig, DeliveryError

EPOCH = 'ADMIN_NOTIFICATION_EPOCH_V1'


def readiness(config: dict) -> dict:
    sender = SenderConfig(**config.get('sender', {}))
    if (sender.operator_confirmed_start is not True or type(sender.bot_id) is not int
            or type(sender.private_chat_id) is not int or type(sender.enabled) is not bool):
        raise ValueError('INVALID_SENDER_CONFIGURATION')
    replace(sender, enabled=True).validate()
    token = Path(sender.token_file)
    if token.is_symlink() or not token.is_file() or token.stat().st_mode & 0o077:
        raise ValueError('SECRET_FILE_PERMISSIONS')
    value = token.read_text().strip()
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,100}', value) or int(value.split(':')[0]) != sender.bot_id:
        raise ValueError('TOKEN_IDENTITY_CONFIGURATION_MISMATCH')
    return {'sender_enabled': sender.enabled, 'identity_configured': True,
            'private_destination_configured': True, 'operator_confirmed_start': True,
            'transport_validation': 'PREVIOUS_OPERATOR_VALIDATION_REUSED_NO_NETWORK'}


def projection(db: sqlite3.Connection, config: dict) -> dict:
    try:
        result = {**readiness(config), 'configuration_ready': True}
    except (OSError, ValueError, TypeError, DeliveryError):
        sender = config.get('sender', {})
        result = {'sender_enabled': sender.get('enabled'), 'configuration_ready': False,
                  'identity_configured': bool(sender.get('bot_id') and sender.get('bot_username')),
                  'private_destination_configured': type(sender.get('private_chat_id')) is int and sender['private_chat_id'] > 0,
                  'operator_confirmed_start': sender.get('operator_confirmed_start') is True}
    table_names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    active = list(db.execute("SELECT id,rule FROM incidents WHERE state IN ('OPEN','REPEATED','ESCALATED')"))
    projected_groups = groups(db)
    result['alert_group_summary'] = [{'correlation_id': g['correlation_id'],
        'primary_incident': g['primary_incident'], 'primary_rule': g['members'][0]['rule'],
        'supporting_incidents': [r['id'] for r in g['members'][1:]]}
        for g in projected_groups if any(r['state'] in ('OPEN','REPEATED','ESCALATED') for r in g['members'])][:200]
    result['unresolved_incident_summary'] = [dict(r) for r in active[:200]]
    result['summary_truncated'] = len(active) > 200 or len(projected_groups) > 200
    result.update(active_alert_groups=sum(any(r['state'] in ('OPEN','REPEATED','ESCALATED') for r in g['members'])
                                         for g in projected_groups) + sum(r['rule'] not in EXECUTION_RULES for r in active),
                  unresolved_incidents=len(active),
                  invalidated_incidents=db.execute("SELECT count(*) FROM incidents WHERE state='INVALIDATED'").fetchone()[0],
                  superseded_notifications=db.execute("SELECT count(*) FROM outbox WHERE state='SUPERSEDED'").fetchone()[0],
                  unsent_pre_enablement_notifications=db.execute("""SELECT count(*) FROM outbox WHERE state='PENDING'
                    AND attempts=0 AND acknowledged=0 AND receipt IS NULL
                    AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.outbox=outbox.id)""").fetchone()[0],
                  attempted_notifications=db.execute('SELECT count(*) FROM attempts').fetchone()[0],
                  notification_epoch=[dict(r) for r in db.execute('SELECT * FROM notification_epochs')]
                    if 'notification_epochs' in table_names else [])
    result['activation_review_required'] = []
    if result['notification_epoch']:
        columns = {r[1] for r in db.execute('PRAGMA table_info(epoch_incidents)')}
        if (len(result['notification_epoch']) != 1 or
                result['notification_epoch'][0]['policy'] != EPOCH_POLICY or
                not {'episode_at_activation', 'generation_at_activation'} <= columns):
            result['activation_review_required'] = [{'reason': 'ACTIVATION_SNAPSHOT_REVIEW_REQUIRED'}]
        else:
            for row in db.execute('SELECT * FROM incidents'):
                reason = epoch_hold(db, dict(row))
                if reason and reason.endswith('REVIEW_REQUIRED'):
                    result['activation_review_required'].append({'incident': row['id'], 'reason': reason})
                    if len(result['activation_review_required']) >= 200:
                        result['summary_truncated'] = True
                        break
    return result


def prepare_epoch(db: sqlite3.Connection, now: float) -> int:
    """One transaction; a failed config enable keeps this durable audit for review."""
    count = 0
    with db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM notification_epochs').fetchone():
            raise ValueError('ACTIVATION_ALREADY_PREPARED_REVIEW_REQUIRED')
        db.execute('INSERT INTO notification_epochs VALUES (?,?,?)',
                   (EPOCH, now, EPOCH_POLICY))
        if db.execute('''SELECT 1 FROM incidents WHERE typeof(episode)!='integer' OR episode<1
                OR typeof(generation)!='integer' OR generation<1''').fetchone():
            raise ValueError('ACTIVATION_SNAPSHOT_REVIEW_REQUIRED')
        db.execute('''INSERT INTO epoch_incidents(incident,epoch,episode_at_activation,generation_at_activation)
            SELECT id,?,episode,generation FROM incidents''', (EPOCH,))
        for row in db.execute("SELECT * FROM outbox WHERE created<?", (now,)).fetchall():
            count += supersede(db, row, 'PRE_ENABLEMENT_BACKLOG_SUPERSEDED', now, EPOCH)
    return count


def write_config(path: Path, value: dict) -> None:
    """Replace and fsync explicit config while retaining mode and ownership."""
    if path.is_symlink():
        raise ValueError('CONFIG_SYMLINK')
    stat = path.stat()
    fd, name = tempfile.mkstemp(prefix='.admin-config-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w') as handle:
            os.fchmod(handle.fileno(), stat.st_mode & 0o777)
            if os.geteuid() == 0:
                os.fchown(handle.fileno(), stat.st_uid, stat.st_gid)
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def enable(config_path: Path, db: sqlite3.Connection, now: float) -> int:
    """Caller holds ADMIN scan lock and has stopped ADMIN only."""
    config = json.loads(config_path.read_text())
    readiness(config)
    if config['sender'].get('enabled') is not False:
        raise ValueError('SENDER_MUST_BE_FALSE')
    count = prepare_epoch(db, now)
    original = json.loads(json.dumps(config))
    config['sender']['enabled'] = True
    try:
        write_config(config_path, config)
        if json.loads(config_path.read_text()) != config:
            raise ValueError('ENABLED_CONFIG_VERIFICATION_FAILED')
    except BaseException:
        # A replace may have succeeded before a directory fsync/verification error.
        # Caller also leaves ADMIN persistently fenced if rollback itself fails.
        write_config(config_path, original)
        raise
    return count


def resume_projection(db: sqlite3.Connection, config: dict) -> dict:
    """Read-only validation of the existing immutable activation boundary."""
    result = projection(db, config)
    epochs = result['notification_epoch']
    safe = (len(epochs) == 1 and epochs[0]['id'] == EPOCH
            and epochs[0]['policy'] == EPOCH_POLICY
            and type(epochs[0]['activated_at']) in (int, float)
            and math.isfinite(epochs[0]['activated_at']) and epochs[0]['activated_at'] > 0)
    columns = {r[1] for r in db.execute('PRAGMA table_info(epoch_incidents)')}
    complete = {'incident', 'epoch', 'episode_at_activation', 'generation_at_activation'} <= columns
    if complete:
        complete = not db.execute('''SELECT 1 FROM epoch_incidents e LEFT JOIN incidents i ON i.id=e.incident
            WHERE i.id IS NULL OR e.epoch!=? OR typeof(e.episode_at_activation)!='integer'
            OR e.episode_at_activation<1 OR typeof(e.generation_at_activation)!='integer'
            OR e.generation_at_activation<1''', (EPOCH,)).fetchone()
    unknown = []
    for row in db.execute("SELECT * FROM incidents WHERE rule='ADMIN_DELIVERY_DEGRADED' AND state IN ('PENDING','OPEN','REPEATED','ESCALATED')"):
        evidence = json.loads(row['evidence'])
        if evidence.get('facts', {}).get('code') == 'UNKNOWN':
            unknown.append(row['id'])
    result['actionable_unknown_delivery_incidents'] = unknown
    result['activation_snapshot_complete'] = bool(safe and complete)
    result['active_actionable_post_epoch_incidents'] = [
        {'id': r['id'], 'rule': r['rule']} for r in db.execute(
            "SELECT * FROM incidents WHERE state IN ('OPEN','REPEATED','ESCALATED')")
        if not epoch_hold(db, dict(r))] if safe and complete else []
    result['resume_ready'] = bool(safe and complete and not result['activation_review_required']
        and not unknown and result['configuration_ready'] and result['sender_enabled'] is False)
    return result


def resume(config_path: Path, db: sqlite3.Connection) -> None:
    """Enable under the caller's ADMIN fence/scan lock; never mutate the database."""
    original = json.loads(config_path.read_text())
    if not resume_projection(db, original)['resume_ready']:
        raise ValueError('EXISTING_ACTIVATION_NOT_RESUME_READY')
    config = json.loads(json.dumps(original))
    config['sender']['enabled'] = True
    try:
        write_config(config_path, config)
        if json.loads(config_path.read_text()) != config:
            raise ValueError('RESUME_CONFIG_VERIFICATION_FAILED')
    except BaseException:
        write_config(config_path, original)
        raise
