#!/usr/bin/env python3
"""Ham greeting bot: durable cursor/outbox; never replay an attempted send."""
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import sys

HERE = Path(os.environ.get('KAKAO_LIVE_SCRIPTS', str(Path(__file__).resolve().parents[2] / 'skills/kakao-live/scripts')))
sys.path.insert(0, str(HERE))
HOME = Path(os.environ['KAKAO_HOME'])
REPLY = '안녕하세요! 햄봇이에요. 🐹'


def query(sql):
    p = subprocess.run(['kakaocli', 'query', sql], capture_output=True, text=True, timeout=240)
    if p.returncode:
        raise RuntimeError('DB query failed')
    return json.loads(p.stdout)


from session_guard import unlocked


def connect():
    HOME.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(HOME / 'ham.sqlite'))
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, sent REAL, state TEXT, answer TEXT)')
    # A crash after claiming a send is uncertain, never pending again.
    db.execute("UPDATE events SET state='uncertain' WHERE state='sending'")
    db.commit()
    return db


def discover():
    rows = query("SELECT DISTINCT r.chatId, r.activeMembersCount FROM NTChatRoom r JOIN NTOpenLink o ON o.linkId=r.linkId WHERE o.linkName='햄봇테스트'")
    if len(rows) != 1 or int(rows[0][1]) != 1:
        raise RuntimeError('Expected exactly one single-member Ham test room')
    cid = int(rows[0][0])
    path = HOME / 'rooms.json'
    registry = json.loads(path.read_text()) if path.exists() else {'me': 0, 'default': 'hamtest', 'rooms': {}}
    registry.setdefault('rooms', {})['hamtest'] = {'chatId': cid, 'search': '햄봇테스트', 'label': '햄봇테스트'}
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(registry, ensure_ascii=False))
    tmp.replace(path)
    return cid


def tick(db):
    cid = discover()
    row = db.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()
    if row is None:
        # First installation starts now. Never respond to historical greetings.
        db.execute("INSERT INTO meta VALUES ('cursor', ?)", (time.time(),))
        db.commit()
        print('ready', flush=True)
        return
    since = float(row[0]) - 5
    rows = query('SELECT logId, sentAt, message FROM NTChatMessage WHERE chatId=%d AND sentAt>=%.3f AND message="햄봇 안녕" AND logId NOT IN (%s) ORDER BY sentAt, logId LIMIT 500' % (cid, since, ','.join(str(int(r[0])) for r in db.execute('SELECT id FROM events WHERE sent>=?', (since,))) or '0'))
    cursor = float(row[0])
    for lid, sent, text in rows:
        cursor = max(cursor, float(sent))
        state = 'pending' if (text or '').strip() == '햄봇 안녕' else 'ignored'
        db.execute('INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?)', (str(lid), float(sent), state, REPLY))
    db.execute("UPDATE meta SET value=? WHERE key='cursor'", (cursor,))
    db.commit()
    # Persistent pending messages may wait for unlock. Anything attempted never retries.
    if not unlocked():
        print('waiting: screen locked or session unknown', flush=True)
        return
    for lid, sent, answer in db.execute("SELECT id, sent, answer FROM events WHERE state='pending' ORDER BY sent").fetchall():
        if time.time() - sent > 300:
            db.execute("UPDATE events SET state='expired' WHERE id=?", (lid,))
            db.commit()
            continue
        discover()  # Recheck member count immediately before every send.
        db.execute("UPDATE events SET state='sending' WHERE id=?", (lid,))
        db.commit()
        started = time.time()
        try:
            result = subprocess.run([str(HERE / 'ksend.sh'), '-r', 'hamtest', answer],
                                    capture_output=True, timeout=100,
                                    env=dict(os.environ, KSEND_NO_RETRY='1'))
            print(json.dumps({'send_exit': result.returncode, 'diagnostic': str(result.stdout)[-1000:] + str(result.stderr)[-1000:]}), flush=True)
            if result.returncode == 1:
                # In conservative mode exit 1 is exclusively a pre-UI block.
                state = 'pending'
            else:
                state = 'uncertain'
                for attempt in range(4):
                    matches = query("SELECT logId FROM NTChatMessage WHERE chatId=%d AND sentAt>=%d AND message='🤖 %s'" % (cid, int(started)-1, answer.replace("'", "''")))
                    if len(matches) == 1:
                        state = 'replied'
                        break
                    if attempt < 3:
                        time.sleep(5)  # Read again; never send again.
        except Exception:
            state = 'uncertain'
        db.execute('UPDATE events SET state=? WHERE id=?', (state, lid))
        db.commit()
        print(json.dumps({'event': state, 'received_at': sent, 'checked_at': time.time()}), flush=True)


def main():
    os.umask(0o077)
    HOME.mkdir(parents=True, exist_ok=True)
    lock = open(HOME / 'runtime.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    db = connect()
    while True:
        try:
            tick(db)
            (HOME / 'heartbeat').write_text(str(time.time()))
        except Exception as e:
            print('waiting: ' + type(e).__name__ + ': ' + str(e), flush=True)
        time.sleep(10)


if __name__ == '__main__':
    main()
