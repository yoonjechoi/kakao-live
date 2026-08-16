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
# 그래서 검색어가 여러 방에 걸리면 엉뚱한 방으로 나간다 — 나간 건 되돌릴 수 없다.
#
# 실제로 걸릴 뻔했다(2026-08-16). 개인톡에 보내려던 검색어가 같은 낱말을 품은
# 오픈채팅(2000명대)과 다른 그룹방 두 곳에도 걸렸고, 실측하니 개인톡이 아니라
# 그룹방이 잡혔다. 그래서 **보내기 전에 DB 로 세어보고, 하나가 아니면 멈춘다.**
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
  #   NTChatMeta(type=3)    일반 그룹방 이름  ← 여기만 있는 방이 흔하다
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
