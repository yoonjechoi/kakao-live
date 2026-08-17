#!/bin/bash
# 카톡 래퍼 공용 — ksend.sh / kimg.sh 가 source 한다. 직접 실행하는 파일이 아니다.
KLIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# run_timeout <초> <명령...>
# coreutils 의 timeout 을 쓰고, 없으면 perl alarm 으로 떨어진다.
# 맥미니에는 coreutils 가 없어 한 번 걸렸다(2026-08-15). 설치했지만 fallback 은 남겨둔다 —
# 다음 기기에서 또 없을 때 전송이 통째로 죽는 것보다 낫다.
if command -v timeout >/dev/null 2>&1; then
  run_timeout() { timeout "$@"; }
elif command -v gtimeout >/dev/null 2>&1; then
  run_timeout() { gtimeout "$@"; }
else
  run_timeout() {
    local t="$1"; shift
    perl -e '
      my $t = shift;
      my $pid = fork();
      if (!defined $pid) { exit 127 }
      if ($pid == 0) { exec @ARGV; exit 127 }
      local $SIG{ALRM} = sub { kill "TERM", $pid; sleep 1; kill "KILL", $pid; exit 124 };
      alarm $t;
      waitpid $pid, 0;
      alarm 0;
      exit($? >> 8);
    ' "$t" "$@"
  }
fi

# kroom <별칭|빈값> <필드>   필드: alias | chatId | search | label | note
# 빈 값이면 rooms.json 의 기본 방. 모르는 별칭이면 stderr 에 알리고 1을 돌려준다.
kroom() {
  python3 "$KLIB_DIR/room.py" get "${1:--}" "${2:?field required}"
}

# 카카오톡을 '채팅' 탭으로 — kmsg 검색은 '친구' 탭이면 방을 못 찾는다(SEARCH_MISS)
kfocus() { "$KLIB_DIR/kfocus.sh" >/dev/null 2>&1; }

# 인자에서 -r/--room 을 뽑아 KROOM_ALIAS 로 남기고, 나머지를 KROOM_ARGS 배열에 담는다.
# 우선순위: -r 인자 > $KROOM 환경변수 > rooms.json 의 default
kroom_parse() {
  KROOM_ALIAS="${KROOM:-}"
  KROOM_ARGS=()
  while [ $# -gt 0 ]; do
    case "$1" in
      -r|--room) KROOM_ALIAS="${2:?-r 뒤에 방 별칭이 필요하다}"; shift 2 ;;
      --)        shift; KROOM_ARGS+=("$@"); return 0 ;;
      *)         KROOM_ARGS+=("$1"); shift ;;
    esac
  done
}

# now_ms — 밀리초 epoch. macOS date 는 %N 을 모른다. coreutils 의 gdate 를 쓰고,
# 없으면 python3 로 떨어진다(느리지만 정확).
if command -v gdate >/dev/null 2>&1; then
  now_ms() { gdate +%s%3N; }
elif date +%s%3N 2>/dev/null | grep -qv N; then
  now_ms() { date +%s%3N; }
else
  now_ms() { python3 -c 'import time;print(int(time.time()*1000))'; }
fi

# klog <tool> <event> [k=v ...]  — 구조화 로그 한 줄. 실패해도 도구를 죽이지 않는다.
klog() { python3 "$KLIB_DIR/klog.py" write "$@" 2>/dev/null || true; }

# ── 보내기 전 방 검증 ────────────────────────────────────────────
# kmsg / kakaocli 는 방을 **이름 부분일치**로 찾는다. 정확일치 옵션이 없다.
# 그래서 검색어가 여러 방에 걸리면 엉뚱한 방으로 나간다 — 되돌릴 수 없다.
#
# 실제로 걸릴 뻔했다(2026-08-16): 「우리팀」로 개인톡을 보내려 했는데 그 문자열이
# 「우리팀 AI 정보 공유방」(오픈채팅 2593명)·「work」·
# 「[우리팀] 글로벌 실패프젝방」에 모두 들어간다. 실측하니 개인톡이 아니라 그룹방이 잡혔다.
# 철수쌤 지시: "래퍼에서는 부분일치로 찾지말고 정확하게 찾아야지."
#
# kroom_verify <검색어> <기대하는 chatId>
#   0 = 안전 (그 검색어가 기대한 방 하나만 가리킨다)
#   1 = 위험 (여러 방에 걸리거나 다른 방을 가리킨다) — 호출부는 전송을 멈춰야 한다
kroom_verify() {
  local needle="$1" want="$2"
  [ -z "$needle" ] && return 1
  local out
  # 방 이름은 **세 군데에 나뉘어 있다.** 한 군데만 보면 오탐이 난다:
  #   NTChatRoom.chatName   대부분 빈 문자열이다
  #   NTOpenLink.linkName   오픈채팅 이름
  #   NTChatMeta(type=3)    일반 그룹방 이름  ← work방이 여기 있다
  out=$(run_timeout 30 kakaocli query "
    SELECT DISTINCT r.chatId
    FROM NTChatRoom r
    LEFT JOIN NTOpenLink o ON o.linkId = r.linkId
    LEFT JOIN NTChatMeta m ON m.chatId = r.chatId AND m.type = 3
    WHERE (r.chatName LIKE '%${needle}%'
        OR o.linkName  LIKE '%${needle}%'
        OR m.content   LIKE '%${needle}%')
  " 2>/dev/null) || { echo "검증 쿼리 실패 — 전송을 멈춘다" >&2; return 1; }

  local ids n
  ids=$(printf '%s' "$out" | grep -oE '[0-9]{6,}' | sort -u)
  n=$(printf '%s\n' "$ids" | grep -c . || true)

  if [ "${n:-0}" -eq 0 ]; then
    echo "⚠ '$needle' 로 찾히는 방이 없다 — DB 이름이 비었을 수 있다(1:1 방 등)" >&2
    klog room verify.none "needle=$needle" "want=$want"
    return 1
  fi
  if [ "${n:-0}" -gt 1 ]; then
    echo "⚠ '$needle' 이 방 ${n}개에 걸린다 — 엉뚱한 방으로 갈 수 있어 멈춘다:" >&2
    printf '%s\n' "$ids" | sed 's/^/    /' >&2
    klog room verify.ambiguous "needle=$needle" "want=$want" "hits=$n"
    return 1
  fi
  if [ "$ids" != "$want" ]; then
    echo "⚠ '$needle' 은 $ids 를 가리킨다 (기대한 것: $want) — 멈춘다" >&2
    klog room verify.mismatch "needle=$needle" "want=$want" "got=$ids"
    return 1
  fi
  klog room verify.ok "needle=$needle" "chat_id=$want"
  return 0
}

# ── 내가 보낸 첨부를 폴러가 알아보게 남긴다 ──────────────────────
#
# 첨부(영상·사진·파일)는 DB 에 본문이 "동영상"·"사진" 으로 저장된다.
# 텍스트는 ksend 가 붙이는 🤖 로 걸러지지만 **첨부는 붙일 자리가 없다.**
# 그래서 내가 올린 것이 그대로 "철수쌤: 동영상" 으로 되돌아와 두 번 헛짚었다(2026-08-17).
#
# 첨부를 보내는 도구는 성공 직후 **반드시** 이 함수를 부른다.
# kvid 만 고치고 kimg 를 빼먹어서 사진이 또 샜다 — 그래서 공통 함수로 옮겼다.
#
#   record_sent_attachment <chatId> [보내기전_logId]
#
# DB 에 찍히는 것이 전송 판정보다 늦다(실측 1초). 한 번만 읽으면 빈손으로 돌아온다.
# 실패하면 sentid.fail 을 남긴다 — **0 이어야 할 자리에 숫자가 찍히는 것이 경보다.**
record_sent_attachment() {
  local chatid="$1" before="${2:-}" newid="" t
  local f="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../logs/kvid_sent.ids"
  touch "$f"
  # ★ "가장 최근 메시지" 를 읽으면 안 된다 — 전송이 15.8초 걸린 사이 내가 보낸 **다음 텍스트**가
  #   먼저 DB 에 들어가, 그 텍스트의 logId 를 첨부인 줄 알고 기록했다(2026-08-17, 사진이 또 샜다).
  #   전송 직전 id(before) 보다 뒤에 붙은 것 중 **첨부인 것**만 고른다.
  for t in 1 2 3 4; do
    newid=$(kakaocli query "SELECT logId FROM NTChatMessage WHERE chatId=$chatid
              AND logId > ${before:-0}
              AND message IN ('사진','동영상','파일','음성메시지')
            ORDER BY logId ASC LIMIT 1" 2>/dev/null \
      | python3 -c 'import sys,json
try:
    v=int(json.load(sys.stdin)[0][0])
    print(v if 0 < v < 9000000000000000000 else "")
except Exception:
    print("")' 2>/dev/null)
    [ -n "$newid" ] && [ "$newid" != "$before" ] && break
    newid=""; sleep 1
  done
  if [ -n "$newid" ]; then
    printf '%s\n' "$newid" >> "$f"
    tail -n 200 "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    printf '%s' "$newid"
  else
    klog kattach sentid.fail "chat_id=$chatid" "note=logId 를 못 읽어 메아리 필터에 못 넣었다"
    return 1
  fi
}
