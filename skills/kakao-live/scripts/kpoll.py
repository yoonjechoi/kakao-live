#!/usr/bin/env python3
"""여러 카톡 방을 한 프로세스로 동시에 폴링한다 (Monitor 이벤트 스트림용).

  tools/kpoll.sh                 # 기본 방 하나
  tools/kpoll.sh ham bang        # 두 방 동시
  tools/kpoll.sh all             # rooms.json 의 모든 방
  tools/kpoll.sh --interval 5 all
  tools/kpoll.sh --replay 5 ham  # 시작할 때 최근 5개를 먼저 흘린다 (맥락 파악용)
  tools/kpoll.sh --resume all    # 지난번 끊긴 지점부터 (그 사이 온 메시지를 복구한다)

출력은 방이 섞이므로 항상 별칭을 붙인다:  [카톡/ham] 김감독: ...

--- 왜 시간 커서인가 (2026-08-15 실측) ---
처음엔 "최신 30개를 떠서 logId > last 인 것만" 이었다. 세 가지 이유로 메시지를 놓친다.

 1) 10초 사이 30개 넘게 오면 창 밖으로 밀린 건 영영 안 온다. 2000명 방에선 충분히 일어난다.
 2) **logId 는 단조증가가 아니다.** 최근 500건 중 12건이 sentAt 순서와 어긋났다.
    logId > last 로 거르면 순서가 역전된 메시지는 영구히 유실된다.
 3) 최신 sentAt 인 행이 가장 작은 logId 를 갖는 경우도 있다(authorId=0 인 시스템 레코드).

그래서 sentAt(초 단위) 을 커서로 쓰되,
 - 같은 초에 2~3건이 있으므로 `>=` 로 겹치게 읽고 (OVERLAP 초만큼 더 뒤로)
 - 이미 흘린 logId 를 기억해 중복을 지운다
 - 한 번에 LIMIT 만큼 차면 커서를 당겨 즉시 다시 읽는다 (폭주해도 무손실)

발신자 이름은 **displayName** 을 쓴다. `nickName` 은 일반 그룹방에서 상대의 카톡 본명(실명)이
나온다 — 방에서 쓰는 대화명이 아니다. 실제로 실명으로 부르는 사고를 냈다(2026-08-15).
  nickName='이피디'  displayName='우리팀'  ← 방에 보이는 건 뒤쪽이다

내 메시지를 거를 때 **authorId 로 거르면 안 된다** (2026-08-16 사고).
내가 쓰는 계정은 철수쌤 계정이다. `authorId <> me` 로 막으면 내 메아리와 함께
**철수쌤이 방에서 하신 말까지 통째로 안 보인다.** 실제로 35분간 못 봤다.
거를 것은 계정이 아니라 **내가 붙인 🤖 표시**다. ksend.sh 가 항상 붙이므로 이걸로 충분하다.
NTUser 는 한 userId 에 멀티프로필 행이 여러 개 있을 수 있어(철수쌤 계정은 7행) JOIN 하면
메시지가 중복된다. 그래서 조인이 아니라 LIMIT 1 서브쿼리로 뽑는다.

방들은 `chatId IN (...)` 으로 한 번에 조회한다. kakaocli 는 호출당 ~790ms(프로세스 기동 +
DB 열기)라 방마다 부르면 방 수만큼 선형으로 늘어난다. 묶으면 방이 몇 개든 한 번이다.
"""
import json, os, subprocess, sys, time
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import room as roomlib  # noqa: E402
import klog             # noqa: E402

LIMIT = int(os.environ.get("KPOLL_LIMIT", 500))  # 한 번에 읽는 최대 행. 닿으면 커서를 당겨 즉시 다시 읽는다
                                                 # (작게 주면 폭주 상황을 재현해 유실 여부를 검증할 수 있다)
OVERLAP = 5.0      # 커서를 이만큼 뒤로 물려 겹치게 읽는다 (같은 초 안의 누락 방지)
SEEN_MAX = 4000    # 방별로 기억하는 logId 개수 — 중복 제거용
AUDIT_EVERY = 6    # 조용한 tick 이 이만큼 지날 때마다 '정말 없었나' 를 대조한다 (10초 간격이면 1분)
CURSOR = os.path.join(os.path.dirname(HERE), "logs", ".kpoll-cursor.json")

SQL = """
SELECT m.chatId, m.logId, m.sentAt,
       COALESCE((SELECT NULLIF(u.displayName,'') FROM NTUser u
                 WHERE u.userId = m.authorId AND NULLIF(u.displayName,'') IS NOT NULL LIMIT 1),
                (SELECT NULLIF(u.nickName,'') FROM NTUser u
                 WHERE u.userId = m.authorId AND NULLIF(u.nickName,'') IS NOT NULL LIMIT 1),
                '?'),
       m.message,
       m.attachment
FROM NTChatMessage m
WHERE m.chatId IN ({chat_ids})
  AND m.sentAt >= {since}
  AND NOT (m.authorId = {me} AND m.message LIKE '🤖%')
  AND m.logId NOT IN ({sent_ids})
  AND m.message IS NOT NULL AND m.message <> ''
  AND NOT (m.message LIKE '{{%' AND m.message LIKE '%"feedType"%')
ORDER BY m.sentAt {order}, m.logId {order}
LIMIT {limit}
"""


# 조용한 게 "말이 없는 것" 인지 "내가 안 듣는 것" 인지 구분하기 위한 대조 쿼리.
# 본 쿼리는 조건에 **맞는** 것만 세고, 조건에 안 맞아 버려진 건 어디에도 남지 않는다.
# 그래서 0건이 정상인지 내가 지운 건지 알 수가 없었다 — 2026-08-15 에 실제로 35분을 놓쳤다.
# 같은 창을 필터 없이 세고, 버림 사유별로 쪼개서 **설명되지 않는 차이**를 드러낸다.
SQL_AUDIT = """
SELECT COUNT(*),
       SUM(CASE WHEN m.authorId = {me} AND m.message LIKE '🤖%' THEN 1 ELSE 0 END),
       SUM(CASE WHEN m.message IS NULL OR m.message = '' THEN 1 ELSE 0 END),
       SUM(CASE WHEN m.message LIKE '{{%' AND m.message LIKE '%"feedType"%' THEN 1 ELSE 0 END),
       SUM(CASE WHEN m.logId IN ({sent_ids})
                 AND NOT (m.authorId = {me} AND m.message LIKE '🤖%')
                 AND m.message IS NOT NULL AND m.message <> ''
                 AND NOT (m.message LIKE '{{%' AND m.message LIKE '%"feedType"%') THEN 1 ELSE 0 END)
FROM NTChatMessage m
WHERE m.chatId IN ({chat_ids})
  AND m.sentAt >= {since}
"""


# 답장(인용)으로 온 메시지는 본문만 보면 무엇을 가리키는지 알 수 없다 — "이거다" 만 남는다.
# 대상은 **attachment JSON** 에 들어 있다: src_logId / src_userId / src_message.
# referer 컬럼은 0 이라 쓸모없다. 2026-08-16 철수쌤이 "DB 에 있을 거야, 찾아봐" 하셔서 찾았다.
# 이걸 안 붙이면 사람에게 "어느 거요?" 를 매번 되물어야 한다 (실제로 그랬다).
def reply_ctx(att):
    if not att:
        return ""
    try:
        d = json.loads(att)
    except Exception:
        return ""
    src = d.get("src_message")
    if not src:
        return ""
    return "  ↩︎(%s)" % str(src).replace("\n", " ")[:60]


# 내가 올린 첨부(영상·이미지·파일)는 본문이 "동영상"·"사진" 으로 저장된다.
# 텍스트는 🤖 접두사로 걸러지지만 첨부는 붙일 자리가 없어 그대로 되돌아온다 —
# 실제로 내가 올린 영상이 6초 뒤 "철수쌤: 동영상" 으로 두 번 잡혔다(2026-08-17).
# kvid.sh 가 보낸 첨부의 logId 를 logs/kvid_sent.ids 에 적어두고, 그것만 건너뛴다.
# 파일이 없거나 비어 있으면 아무것도 거르지 않는다(0 을 쓰면 IN () 문법 오류가 난다).
SENT_IDS_PATH = os.path.join(HERE, "..", "logs", "kvid_sent.ids")


def sent_ids():
    try:
        with open(SENT_IDS_PATH) as f:
            # int64 최대값 같은 헛값이 섞이면 조용히 아무것도 안 거른다. 범위로 막는다.
            ids = [ln.strip() for ln in f
                   if ln.strip().isdigit() and 0 < int(ln.strip()) < 9_000_000_000_000_000_000]
    except OSError:
        return "0"
    return ",".join(ids[-200:]) or "0"


def audit(chat_ids, since, me, passed):
    """필터가 버린 것을 사유별로 센다. (설명되는 버림, 설명 안 되는 버림) 또는 None.

    passed 는 본 쿼리가 실제로 가져온 행 수다. 5초 겹침 때문에 이미 흘린 것도 포함된다.
    total - passed 가 곧 버린 양이고, 그게 사유 합과 같아야 한다.
    남으면 **아무도 모르게 새고 있다는 뜻**이다."""
    sql = SQL_AUDIT.format(chat_ids=",".join(str(c) for c in chat_ids),
                           since=repr(float(since)), me=me, sent_ids=sent_ids())
    try:
        out = subprocess.run(["kakaocli", "query", sql], capture_output=True, text=True, timeout=20)
        row = json.loads(out.stdout)[0]
        total, echo, empty, feed, mine_att = (int(v or 0) for v in row)
    except Exception as e:
        klog.write("kpoll", "audit.fail", err=str(e)[:200])
        return None
    explained = echo + empty + feed + mine_att
    dropped = total - passed
    return explained, dropped - explained



# ── 도배 감지 ────────────────────────────────────────────────
# 2026-08-17 vibe 방에 낯선 사람이 들어와 **1분에 69건**을 쏟았다(실측).
# 운영진이 70~100번씩 손으로 지웠다. 그 사이 아무 경보도 없었다.
# 정상 사용자는 1분에 그만큼 못 친다 — 평소 최다 발화자도 하루 16건이었다.
# 임계 20 은 철수쌤이 "그건 넘을 수 있다" 하셔서 **40** 으로 올렸다(2026-08-17).
# 실제 도배는 1분에 69건이었으니 40 이면 여전히 잡힌다.
FLOOD_WINDOW = 60
FLOOD_LIMIT  = 40

SQL_FLOOD = """
SELECT m.authorId,
       COALESCE((SELECT NULLIF(u.displayName,'') FROM NTUser u
                 WHERE u.userId = m.authorId AND NULLIF(u.displayName,'') IS NOT NULL LIMIT 1), '?'),
       COUNT(*) AS c
FROM NTChatMessage m
WHERE m.chatId = {chat_id} AND m.sentAt >= {since}
GROUP BY m.authorId
HAVING c >= {limit}
ORDER BY c DESC
"""


def flood_check(chat_id, alias):
    """한 사람이 짧은 시간에 쏟아내면 알린다. 조용히 지나가면 아무도 모른다."""
    since = time.time() - FLOOD_WINDOW
    sql = SQL_FLOOD.format(chat_id=chat_id, since=repr(float(since)), limit=FLOOD_LIMIT)
    try:
        out = subprocess.run(["kakaocli", "query", sql], capture_output=True, text=True, timeout=20)
        rows = json.loads(out.stdout) if out.stdout.strip() else []
    except Exception as e:
        klog.write("kpoll", "flood.fail", room=alias, err=str(e)[:150])
        return
    for author, name, cnt in rows:
        print("[도배/%s] %s 님이 %d초 안에 %d건 — 확인이 필요합니다"
              % (alias, name, FLOOD_WINDOW, cnt), flush=True)
        klog.write("kpoll", "flood.detected", room=alias, sender=name,
                   author_id=author, count=cnt, window=FLOOD_WINDOW)


def query(chat_ids, since, me, limit=LIMIT, newest_first=False):
    """(rows, query_ms). 실패해도 폴링은 계속 살아 있어야 하므로 예외를 삼키고 로그만 남긴다.
    조용한 게 '메시지 없음' 인지 '폴러가 죽음' 인지는 로그로 구분한다."""
    sql = SQL.format(chat_ids=",".join(str(c) for c in chat_ids),
                     since=repr(float(since)), me=me, limit=limit,
                     sent_ids=sent_ids(),
                     order="DESC" if newest_first else "ASC")
    t0 = time.time()
    try:
        p = subprocess.run(["kakaocli", "query", sql], capture_output=True, text=True, timeout=30)
        ms = int((time.time() - t0) * 1000)
        if p.returncode != 0:
            klog.write("kpoll", "query.fail", query_ms=ms, err=(p.stderr or "").strip()[:300])
            return None, ms
        return (json.loads(p.stdout) if p.stdout.strip() else []), ms
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        klog.write("kpoll", "query.fail", query_ms=ms, err="%s: %s" % (type(e).__name__, e))
        return None, ms


def load_cursor():
    try:
        with open(CURSOR, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cursor(state):
    try:
        os.makedirs(os.path.dirname(CURSOR), exist_ok=True)
        tmp = CURSOR + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, CURSOR)
    except Exception:
        pass


def main(argv):
    interval, replay, tick_every, resume = 10.0, 0, 30, False
    aliases = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--interval", "-i"):
            interval = float(argv[i + 1]); i += 2
        elif a in ("--replay", "-n"):
            replay = int(argv[i + 1]); i += 2
        elif a == "--tick-every":
            tick_every = int(argv[i + 1]); i += 2
        elif a == "--resume":
            resume = True; i += 1
        else:
            aliases.append(a); i += 1

    conf = roomlib.load()
    me = conf["me"]
    r = subprocess.run([sys.executable, os.path.join(HERE, "room.py"), "resolve"] + aliases,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        return 1
    targets = r.stdout.split()
    by_chat = {conf["rooms"][a]["chatId"]: a for a in targets}
    chat_ids = list(by_chat)

    saved = load_cursor() if resume else {}
    seen = {a: OrderedDict() for a in targets}   # alias -> {logId: None}, 삽입순
    cur = {}                                     # alias -> 마지막으로 본 sentAt

    now = time.time()
    for a in targets:
        room = conf["rooms"][a]
        s = saved.get(a, {})
        cur[a] = float(s.get("ts", now))
        for lid in s.get("ids", [])[-SEEN_MAX:]:
            seen[a][int(lid)] = None
        print("[폴링] %s — %s (%s)%s" % (a, room["label"], room.get("note", ""),
                                        "  ↩︎이어받기" if s else ""),
              file=sys.stderr, flush=True)

    klog.write("kpoll", "poll.start", rooms=",".join(targets), interval=interval,
               pid=os.getpid(), resume=resume)

    # --replay N: 시작 직전 N개를 한 번 흘린다.
    # 본 쿼리(sentAt ASC)를 재활용하면 '가장 오래된 N개'가 나온다. 방마다 DESC 로 따로 읽는다.
    # 시작할 때 한 번뿐이라 방 수만큼 호출해도 괜찮다 — 정확성이 우선.
    if replay and not resume:
        for a in targets:
            rows, _ms = query([conf["rooms"][a]["chatId"]], 0, me, limit=replay, newest_first=True)
            for cid, lid, ts, sender, text, att in reversed(rows or []):
                print("[카톡/%s] %s: %s%s" % (a, sender, (text or "").replace("\n", " / ")[:400],
                      reply_ctx(att)), flush=True)
                seen[a][int(lid)] = None

    tick = 0
    try:
        while True:
            tick += 1
            since = min(cur.values()) - OVERLAP
            drained = 0
            tick_new = 0          # 이 tick 전체에서 흘린 새 메시지 수
            last_rows = 0         # 마지막 조회가 가져온 행 수 (겹침분 포함)
            while True:                       # LIMIT 에 닿으면 커서를 당겨 즉시 다시 읽는다
                rows, ms = query(chat_ids, since, me)
                if rows is None:              # 쿼리 실패 — 이미 로그에 남았다. 커서는 그대로 둔다
                    break
                fresh = 0
                for cid, lid, ts, sender, text, att in rows:
                    a = by_chat.get(cid)
                    if a is None:
                        continue
                    lid = int(lid)
                    if lid in seen[a]:
                        continue
                    seen[a][lid] = None
                    if len(seen[a]) > SEEN_MAX:
                        seen[a].popitem(last=False)
                    line = (text or "").replace("\n", " / ")[:400] + reply_ctx(att)
                    print("[카톡/%s] %s: %s" % (a, sender, line), flush=True)
                    klog.write("kpoll", "recv", room=a, sender=sender, text=line, log_id=lid, sent_at=float(ts))
                    cur[a] = max(cur[a], float(ts))
                    fresh += 1
                tick_new += fresh
                last_rows = len(rows)

                # 새 메시지가 몰린 tick 에서만 도배를 본다 — 조용하면 볼 일이 없다.
                # 한 번에 여러 건이 들어오는 것이 도배의 첫 징후다.
                if fresh >= 5:
                    for a in aliases:
                        flood_check(conf["rooms"][a]["chatId"], a)

                # tick 을 매번 남기면 하루 수만 줄이 된다. 주기적으로만 남기되
                # 새 메시지가 있거나 쿼리가 느려진 순간은 놓치지 않는다.
                if fresh or ms > 1000 or tick % tick_every == 0:
                    klog.write("kpoll", "tick", query_ms=ms, rows=len(rows), new=fresh,
                               rooms=len(chat_ids), drain=drained)

                if len(rows) < LIMIT:
                    break
                # 창이 꽉 찼다 = 더 있을 수 있다. 마지막 행 시각부터 이어 읽는다.
                drained += 1
                since = float(rows[-1][2])
                klog.write("kpoll", "drain", rows=len(rows), round=drained, since=since)
                if drained > 20:
                    klog.write("kpoll", "drain.abort", round=drained)
                    break

            # 조용한 tick 에서만 대조한다. 새 메시지가 있었다면 듣고 있다는 게 이미 증명됐고,
            # 조용할 때가 바로 "말이 없는 건지 내가 안 듣는 건지" 모르는 순간이다.
            # 비용도 조용할 때만 든다(kakaocli 호출 1회 ~800ms).
            if tick_new == 0 and tick % AUDIT_EVERY == 0:
                res = audit(chat_ids, since, me, last_rows)
                if res is not None:
                    explained, unexplained = res
                    if unexplained:
                        # 사유로 설명되지 않는 버림 = 아무도 모르게 새고 있다는 뜻
                        klog.write("kpoll", "audit.leak", dropped=explained + unexplained,
                                   explained=explained, unexplained=unexplained, since=since)
                    elif tick % (AUDIT_EVERY * 10) == 0:
                        klog.write("kpoll", "audit.ok", explained=explained, since=since)

            save_cursor({a: {"ts": cur[a], "ids": list(seen[a])[-SEEN_MAX:]} for a in targets})
            time.sleep(interval)
    except KeyboardInterrupt:
        klog.write("kpoll", "poll.stop", reason="interrupt")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
