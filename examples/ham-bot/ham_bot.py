#!/usr/bin/env python3
"""햄봇 — 「햄봇 안녕」에만 답하는 자동응답 예제. 같은 답을 두 번 보내지 않는 것이 핵심이다.

  KAKAO_HOME=/Users/Shared/HamBot/home python3 ham_bot.py

처리 상태는 <KAKAO_HOME>/ham.sqlite 에 남는다(죽었다 살아나도 이어진다).

  pending   받았고 아직 안 보냈다
  sending   보내는 중 — 이 상태로 프로세스가 죽으면 다시 뜰 때 uncertain 이 된다
  replied   DB 에서 🤖 답을 찾았다
  uncertain 나갔는지 모른다 — **다시 보내지 않는다.** 사람이 DB 를 보고 닫는다
  expired   5분 안에 못 보냈다(화면이 계속 잠겨 있었다 등)

보내기는 ksend.sh 를 KSEND_NO_RETRY=1 로 부른다. 끝 코드로 나눈다:
  1 = 보내기 전에 멈춤(방 검증·화면 잠금) → pending 으로 두고 다음 바퀴에 다시
  0 · 2 = 나갔을 수 있다 → DB 를 15초 동안 다시 보며 🤖 본문을 찾는다. 없으면 uncertain
"""
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unicodedata

HERE = Path(__file__).resolve().parent
SCRIPTS = Path(os.environ.get("KAKAO_LIVE_SCRIPTS") or HERE.parents[1] / "skills/kakao-live/scripts")
HOME = Path(os.environ.get("KAKAO_HOME") or HERE / ".kakao")

ROOM_NAME = "햄봇테스트"     # 1인 오픈채팅 — 사람이 하나뿐인 방에서만 답한다
ALIAS = "hamtest"
TRIGGER = "햄봇 안녕"
REPLY = "안녕하세요! 햄봇이에요. 🐹"
TICK = 10                   # 초
EXPIRE = 300                # 받은 뒤 이만큼 지나면 답하지 않는다
CONFIRM_FOR = 15            # 보낸 뒤 DB 를 다시 보는 시간
CONFIRM_EVERY = 3


def query(sql):
    p = subprocess.run(["kakaocli", "query", sql], capture_output=True, text=True, timeout=60)
    if p.returncode:
        raise RuntimeError("kakaocli query failed")
    return json.loads(p.stdout or "[]")


def norm(s):
    """카톡에 저장된 본문과 비교할 때 쓴다. 이모지 변형 문자(FE0F)·공백 차이로 빗나가지 않게."""
    s = unicodedata.normalize("NFC", s or "").replace("️", "")
    return " ".join(s.split())


def connect():
    HOME.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(HOME / "ham.sqlite"))
    db.execute("PRAGMA synchronous=FULL")
    db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value REAL)")
    db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, sent REAL, state TEXT, answer TEXT)")
    # 보내는 중에 죽었으면 나갔는지 모른다. pending 으로 되돌리지 않는다.
    db.execute("UPDATE events SET state='uncertain' WHERE state='sending'")
    db.commit()
    return db


def discover():
    """「햄봇테스트」가 정확히 한 개이고 사람이 한 명인지. 아니면 예외 — 아무것도 보내지 않는다."""
    rows = query(
        "SELECT DISTINCT r.chatId, r.activeMembersCount FROM NTChatRoom r "
        "JOIN NTOpenLink o ON o.linkId = r.linkId WHERE o.linkName = '%s'" % ROOM_NAME
    )
    if len(rows) != 1 or int(rows[0][1]) != 1:
        raise RuntimeError("expected exactly one single-member room named %s" % ROOM_NAME)
    cid = int(rows[0][0])
    register(cid)
    return cid


def register(cid):
    """rooms.json 에 hamtest 항목만 넣는다. 이미 있는 me · default · 다른 방은 그대로 둔다."""
    path = HOME / "rooms.json"
    try:
        reg = json.loads(path.read_text())
    except (OSError, ValueError):
        reg = {}
    reg.setdefault("rooms", {})
    want = {"chatId": cid, "search": ROOM_NAME, "label": ROOM_NAME, "note": "햄봇 1인 테스트방"}
    if reg["rooms"].get(ALIAS) == want and "default" in reg:
        return
    reg["rooms"][ALIAS] = want
    reg.setdefault("default", ALIAS)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2))
    tmp.replace(path)


def collect(db, cid):
    row = db.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()
    if row is None:
        # 처음 뜬 순간부터만 답한다. 예전 「햄봇 안녕」에 몰아서 답하지 않는다.
        db.execute("INSERT INTO meta VALUES ('cursor', ?)", (time.time(),))
        db.commit()
        print("ready", flush=True)
        return
    cursor = float(row[0])
    rows = query(
        "SELECT logId, sentAt, message FROM NTChatMessage WHERE chatId = %d AND sentAt >= %d "
        "ORDER BY sentAt, logId LIMIT 500" % (cid, int(cursor) - 5)
    )
    for lid, sent, text in rows:
        cursor = max(cursor, float(sent))
        if norm(text) == TRIGGER:
            db.execute("INSERT OR IGNORE INTO events VALUES (?, ?, 'pending', ?)", (str(lid), float(sent), REPLY))
    db.execute("UPDATE meta SET value=? WHERE key='cursor'", (cursor,))
    db.commit()


def confirmed(cid, answer, since):
    want = norm("🤖 " + answer)
    deadline = time.time() + CONFIRM_FOR
    while True:
        rows = query(
            "SELECT logId, message FROM NTChatMessage WHERE chatId = %d AND sentAt >= %d "
            "AND message LIKE '🤖%%'" % (cid, int(since) - 2)
        )
        hits = [r for r in rows if norm(r[1]) == want]
        if hits:
            return len(hits)
        if time.time() >= deadline:
            return 0
        time.sleep(CONFIRM_EVERY)


def send(answer):
    env = dict(os.environ, KSEND_NO_RETRY="1", KAKAO_HOME=str(HOME))
    p = subprocess.run([str(SCRIPTS / "ksend.sh"), "-r", ALIAS, answer], env=env, capture_output=True, timeout=120)
    return p.returncode


def deliver(db, cid):
    for lid, sent, answer in db.execute(
        "SELECT id, sent, answer FROM events WHERE state='pending' ORDER BY sent"
    ).fetchall():
        if time.time() - sent > EXPIRE:
            db.execute("UPDATE events SET state='expired' WHERE id=?", (lid,))
            db.commit()
            continue
        cid = discover()  # 보내기 직전에 한 번 더 — 그 사이 누가 들어왔으면 멈춘다
        db.execute("UPDATE events SET state='sending' WHERE id=?", (lid,))
        db.commit()
        started = time.time()
        try:
            rc = send(answer)
            if rc == 1:
                state = "pending"  # 아무것도 안 갔다 — 다음 바퀴에 다시
            else:
                n = confirmed(cid, answer, started)
                state = "replied" if n else "uncertain"
                if n > 1:
                    print(json.dumps({"event": "duplicate_seen", "count": n}), flush=True)
        except Exception:  # noqa: BLE001 — 시간 초과 포함, 모르면 uncertain
            state = "uncertain"
        db.execute("UPDATE events SET state=? WHERE id=?", (state, lid))
        db.commit()
        print(json.dumps({"event": state, "received_at": sent, "checked_at": time.time()}), flush=True)
        if state == "pending":
            return  # 막혔으면 이번 바퀴는 여기까지


def tick(db):
    cid = discover()
    collect(db, cid)
    deliver(db, cid)


def main():
    os.umask(0o077)
    HOME.mkdir(parents=True, exist_ok=True)
    lock = open(HOME / "ham.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # 둘이 뜨면 같은 답을 두 번 보낸다
    except BlockingIOError:
        sys.exit("already running")
    db = connect()
    while True:
        try:
            tick(db)
            (HOME / "heartbeat").write_text(str(time.time()))
        except Exception as e:  # noqa: BLE001 — 바퀴 하나가 죽어도 루프는 산다
            print("waiting: %s: %s" % (type(e).__name__, e), flush=True)
        time.sleep(TICK)


if __name__ == "__main__":
    main()
