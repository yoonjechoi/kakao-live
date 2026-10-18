#!/usr/bin/env python3
"""Run explicitly configured direct rooms serially alongside the single-member test room.

HAM_BOT_DIRECT_ROOMS is a JSON list of {alias, name, chatId}. Room IDs stay local.
Only new messages after first startup are collected. All UI sends use ksend.sh.
"""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time


def load_bot():
    spec = importlib.util.spec_from_file_location('ham_bot_instance', Path(__file__).with_name('ham_bot.py'))
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)
    return bot


def direct_bot(config, home):
    alias, name, cid = config['alias'], config['name'], int(config['chatId'])
    if not re.fullmatch(r'[a-z][a-z0-9_-]*', alias) or alias == 'hamtest' or not name or cid <= 0:
        raise ValueError('invalid direct room configuration')
    bot = load_bot()
    bot.HOME = home / 'direct-rooms' / alias
    bot.ALIAS, bot.ROOM_NAME = alias, name

    def discover():
        # Exact identity and membership check, repeated immediately before every send.
        escaped = name.replace("'", "''")
        rows = bot.query("SELECT r.chatId,r.activeMembersCount FROM NTChatRoom r "
                         "JOIN NTUser u ON u.userId=r.directChatMemberUserId "
                         "WHERE u.displayName='%s'" % escaped)
        if len(rows) != 1 or int(rows[0][0]) != cid or int(rows[0][1]) != 2:
            raise RuntimeError('direct room identity or membership changed')
        bot.register(cid)
        return cid

    bot.discover = discover
    return bot


def main():
    os.umask(0o077)
    base = load_bot()
    base.HOME.mkdir(parents=True, exist_ok=True)
    lock = open(base.HOME / 'runtime.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('already running')
    configs = json.loads(os.environ.get('HAM_BOT_DIRECT_ROOMS', '[]'))
    if len({c['alias'] for c in configs}) != len(configs) or len({int(c['chatId']) for c in configs}) != len(configs):
        sys.exit('duplicate direct room configuration')
    bots = [base] + [direct_bot(c, base.HOME) for c in configs]
    for bot in bots:
        if not (bot.SCRIPTS / 'ksend.sh').is_file():
            sys.exit('ksend.sh not found')
    instances = [(bot, bot.connect()) for bot in bots]
    while True:
        for bot, db in instances:
            try:
                bot.tick(db)
                (bot.HOME / 'heartbeat').write_text(str(time.time()))
            except Exception as exc:
                print('waiting [%s]: %s' % (bot.ALIAS, exc), flush=True)
        time.sleep(base.TICK)


if __name__ == '__main__':
    main()
