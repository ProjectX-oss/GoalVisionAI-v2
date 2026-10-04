"""Operator Lab private START enrollment; only getMe/getUpdates, never a send."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import time
from datetime import datetime, timezone
import urllib.request

BASE = Path('/opt/goalvision-prematch-settlement-quota-reserve-9d73894-20261004')
PYTHON = '/home/arvis/GoalVisionAI/.venv/bin/python'


def contract(package):
    sys.path.insert(0, str(BASE/'application'))
    path = package/'overlay/app/lab_private_single/routing.py'
    spec = importlib.util.spec_from_file_location('reviewed_private_lab_routing', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

def telegram_read(token, method, parameters=None):
    if method not in {'getMe', 'getUpdates'}:
        raise ValueError('READ_ONLY_TELEGRAM_METHOD_REQUIRED')
    request = urllib.request.Request('https://api.telegram.org/bot'+token+'/'+method,
        data=json.dumps(parameters or {}).encode(), headers={'Content-Type':'application/json'}, method='POST')
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=15) as response:
            body = response.read(1048577)
        if len(body)>1048576:
            raise ValueError
        data = json.loads(body)
        if data.get('ok') is not True:
            raise ValueError
        return data['result']
    except Exception:
        raise ValueError('TELEGRAM_IDENTITY_READ_FAILED') from None

def recipient(updates, nonce, issued_at, now):
    if not isinstance(updates, list):
        raise ValueError('PRIVATE_START_NOT_FOUND')
    found = {}
    for update in updates:
        if not isinstance(update, dict):
            continue
        message = update.get('message') or {}
        sender, chat = message.get('from') or {}, message.get('chat') or {}
        if (message.get('text') != '/start '+nonce or chat.get('type') != 'private'
                or sender.get('is_bot') is not False
                or type(chat.get('id')) is not int or chat['id'] <= 0
                or sender.get('id') != chat['id']
                or type(message.get('date')) is not int
                or not issued_at-5 <= message['date'] <= now+30
                or now-issued_at > 900
                or type(update.get('update_id')) is not int
                or update['update_id'] < 0 or 'forward_origin' in message):
            continue
        found[str(chat['id'])] = update['update_id']
    if len(found)!=1:
        raise ValueError('PRIVATE_START_NOT_FOUND_OR_AMBIGUOUS')
    return next(iter(found.items()))


def configure(package, *, reader=telegram_read, ask=input):
    import pwd
    from hashlib import sha256
    mod = contract(package)
    if os.geteuid() != pwd.getpwnam('arvis').pw_uid:
        raise ValueError('RUN_CONFIGURE_AS_ARVIS_WITHOUT_SUDO')
    path = mod.CONFIG_PATH
    if path.exists() or path.is_symlink():
        mod.load_config()
        print('PRIVATE_LAB_CONFIGURATION_ALREADY_PRESENT')
        return
    from app.lab_combo.bot_routing import load_config as load_combo
    from app.lab_telegram.service import load_lab_telegram_config, validate_lab_telegram_config
    from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
    anchor = load_combo()
    lab = load_lab_telegram_config(Path('/home/arvis/GoalVisionAI/.env'))
    if validate_lab_telegram_config(lab) is not None:
        raise ValueError('LAB_CREDENTIAL_NOT_CONFIGURED')
    bot = reader(lab.token, 'getMe')
    if (not isinstance(bot,dict) or bot.get('is_bot') is not True
            or '@'+str(bot.get('username','')) != LAB_BOT_USERNAME
            or type(bot.get('id')) is not int or str(bot['id']) != lab.token.split(':',1)[0]):
        raise ValueError('PRIVATE_LAB_BOT_IDENTITY_MISMATCH')
    nonce, issued = 'gvprivate_'+secrets.token_hex(16), int(time.time())
    print('Atver saiti savā Telegram kontā un nospied START:')
    print('https://t.me/'+LAB_BOT_USERNAME[1:]+'?start='+nonce)
    ask('Pēc START nospiešanas šeit nospied Enter: ')
    updates = reader(lab.token,'getUpdates',{'limit':100,'timeout':0})
    chat_id,update_id=recipient(updates,nonce,issued,int(time.time()))
    if chat_id != anchor.chat_id:
        raise ValueError('PRIVATE_START_DOES_NOT_MATCH_CONFIRMED_OWNER')
    stamp=datetime.now(timezone.utc).isoformat()
    route=mod.validate_route({'version':mod.VERSION,'product':'PRIVATE_SINGLE',
        'bot_username':LAB_BOT_USERNAME,'bot_id':str(bot['id']),'chat_id':chat_id,'chat_type':'private',
        'statistics_period':mod.PERIOD,'period_started_at':stamp})
    data={'route':route,'verified_at':stamp,'start_update_id':update_id,
          'recipient_anchor_fingerprint':sha256(json.dumps(anchor.route,sort_keys=True).encode()).hexdigest()}
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.parent.is_symlink() or path.parent.stat().st_mode & 0o077:
        raise ValueError('PRIVATE_DIRECTORY_PERMISSION_REQUIRED')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as output:
            json.dump(data,output,sort_keys=True)
            output.write('\n');output.flush();os.fsync(output.fileno())
        mod.load_config()
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    print('PRIVATE_LAB_RECIPIENT_CONFIGURED; confirmed COMBO owner matched')
    print('bot='+LAB_BOT_USERNAME+'; private SINGLE odds>=1.70; model probability 70-80%')
    print('No message sent. Runtime unchanged until operator --apply.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    package=Path(__file__).resolve().parent
    try:
        if args.check:
            config=contract(package).load_config()
            print('PRIVATE_LAB_CONFIGURATION_VALID; bot='+config.route['bot_username'])
        else:
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                raise ValueError('INTERACTIVE_TERMINAL_REQUIRED')
            configure(package)
    except (Exception,KeyboardInterrupt):
        print('PRIVATE_LAB_CONFIGURATION_NOT_COMPLETED; use the START link with the confirmed COMBO owner account.')
        raise SystemExit(1) from None

if __name__ == '__main__':
    main()
