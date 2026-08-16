#!/bin/bash
# 방·친구를 정확히 짚기 위한 조회 도구 — 보내지 않는다. 고르기 위한 것이다.
#
#   kfind.sh 우리팀              방과 친구를 한 번에 찾는다
#   kfind.sh --rooms 우리팀       방만
#   kfind.sh --friends 철수       친구만
#
# 왜 필요한가:
#   kmsg·kakaocli 는 방을 **이름 부분일치**로 찾고 정확일치 옵션이 없다.
#   그래서 검색어가 여러 방에 걸리면 엉뚱한 방으로 나간다 — 나간 건 되돌릴 수 없다.
#   래퍼는 그걸 감지해 멈출 수는 있어도(klib.sh 의 kroom_verify) **무엇을 써야 하는지는 못 고른다.**
#   고르는 건 사람이나 LLM 이 한다. 이 도구는 그 판단에 필요한 것을 다 펼쳐 보인다:
#   전체 이름, chatId, 인원수, 그리고 **그 검색어가 몇 군데에 걸리는지.**
#
# 방 이름은 세 군데에 나뉘어 있다 — 한 군데만 보면 못 찾는다:
#   NTChatRoom.chatName   대부분 빈 문자열
#   NTOpenLink.linkName   오픈채팅 이름
#   NTChatMeta(type=3)    일반 그룹방 이름
#
# 1:1 방은 **이름이 아예 없다.** 그래서 이름으로는 원리적으로 못 고른다 —
# 친구 쪽에서 userId·directChatId 로 짚어야 한다. 그것도 여기서 보여준다.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/klib.sh"

MODE="both"
case "${1:-}" in
  --rooms)   MODE="rooms";   shift ;;
  --friends) MODE="friends"; shift ;;
esac
Q="${1:?찾을 이름 조각이 필요하다}"
# SQL 문자열 이스케이프 — 작은따옴표만 막으면 된다(읽기 전용 쿼리다)
QE=$(printf '%s' "$Q" | sed "s/'/''/g")

if [ "$MODE" = "rooms" ] || [ "$MODE" = "both" ]; then
  echo "── 방 ──────────────────────────────────────────"
  run_timeout 40 kakaocli query "
    SELECT DISTINCT
      r.chatId,
      COALESCE(NULLIF(r.chatName,''), o.linkName, m.content, '(이름 없음 — 1:1 방)') AS name,
      r.activeMembersCount,
      CASE r.type WHEN 0 THEN '1:1' WHEN 1 THEN '그룹' WHEN 4 THEN '오픈채팅' ELSE '기타' END
    FROM NTChatRoom r
    LEFT JOIN NTOpenLink o ON o.linkId = r.linkId
    LEFT JOIN NTChatMeta m ON m.chatId = r.chatId AND m.type = 3
    WHERE (r.chatName LIKE '%${QE}%' OR o.linkName LIKE '%${QE}%' OR m.content LIKE '%${QE}%')
    ORDER BY r.activeMembersCount DESC
  " 2>/dev/null | python3 -c '
import sys, json
try:
    rows = json.load(sys.stdin)
except Exception:
    rows = []
if not rows:
    print("  걸리는 방 없음")
else:
    for cid, name, cnt, kind in rows:
        print("  %-20s %-8s %5s명  %s" % (cid, kind, cnt, name))
    if len(rows) > 1:
        print("  ⚠ %d 곳에 걸린다 — 이 조각으로는 전송하면 안 된다." % len(rows))
        print("    각 방의 전체 이름 중 **다른 방에 없는** 조각을 골라 rooms.json 의 search 에 넣어라.")
    else:
        print("  ✓ 한 곳만 가리킨다 — 전송에 써도 된다")
'
fi

if [ "$MODE" = "friends" ] || [ "$MODE" = "both" ]; then
  echo "── 친구 (대화명 기준) ───────────────────────────"
  # nickName 은 주소록에 저장된 이름(대개 실명)이다.
  # **displayName(대화명)으로 찾고, 실명은 찍지 않는다.** 실명으로 불러 사고 낸 적이 있다.
  run_timeout 40 kakaocli query "
    SELECT userId, displayName, directChatId, friendType
    FROM NTUser
    WHERE linkId = 0 AND displayName LIKE '%${QE}%'
      AND COALESCE(purged,0)=0 AND COALESCE(suspended,0)=0
    ORDER BY (directChatId != 0) DESC
  " 2>/dev/null | python3 -c '
import sys, json
try:
    rows = json.load(sys.stdin)
except Exception:
    rows = []
if not rows:
    print("  걸리는 친구 없음")
else:
    for uid, dname, dchat, ftype in rows:
        has = ("1:1 방 %s" % dchat) if dchat else "1:1 방 없음 (대화한 적 없음)"
        print("  userId=%-12s %-16s %s" % (uid, dname, has))
    print("  ※ 1:1 방은 **이름이 없다.** 이름 검색으로는 못 고른다 —")
    print("     kmsg 는 이름 부분일치라 위 chatId 를 줘도 다른 방이 잡힐 수 있다. 반드시 확인하고 보낼 것.")
'
fi
