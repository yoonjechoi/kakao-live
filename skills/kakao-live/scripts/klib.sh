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
