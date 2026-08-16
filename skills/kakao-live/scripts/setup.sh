#!/bin/bash
# 카톡 연동 환경 점검 + 방 등록. 처음 한 번 실행한다.
#
#   scripts/setup.sh              점검 + 대화형 방 등록
#   scripts/setup.sh --check      점검만
#   scripts/setup.sh --find 우리팀  방 검색만
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KHOME="${KAKAO_HOME:-$PWD/.kakao}"

ok(){ printf "  \033[32m✓\033[0m %s\n" "$1"; }
no(){ printf "  \033[31m✗\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33m!\033[0m %s\n" "$1"; }

check() {
  local fail=0
  echo "── 도구 ──"
  for c in kakaocli kmsg ffmpeg python3 curl; do
    if command -v "$c" >/dev/null 2>&1; then ok "$c"; else
      no "$c 없음"; fail=1
      case "$c" in
        kakaocli) echo "      brew install silver-flight-group/tap/kakaocli" ;;
        kmsg)     echo "      brew install channprj/tap/kmsg" ;;
        ffmpeg)   echo "      brew install ffmpeg   (첨부 영상 다룰 때만 필요)" ;;
      esac
    fi
  done
  command -v timeout >/dev/null 2>&1 || command -v gtimeout >/dev/null 2>&1 \
    && ok "timeout" || { warn "timeout 없음 — brew install coreutils (없으면 perl 로 대체 동작)"; }

  echo "── 카카오톡 ──"
  local st; st=$(kakaocli status 2>/dev/null)
  if printf '%s' "$st" | grep -q "App state:.*loggedIn"; then ok "로그인됨"
  else no "로그인 안 됨 — 카카오톡 데스크톱 앱을 켜고 로그인할 것"; fail=1; fi
  if printf '%s' "$st" | grep -q "Full Disk Access:.*OK"; then ok "전체 디스크 접근 권한"
  else no "전체 디스크 접근 권한 없음 — 시스템 설정 > 개인정보 보호 및 보안 > 전체 디스크 접근 에 터미널 추가"; fail=1; fi

  echo "── 접근성(손쉬운 사용) ──"
  if osascript -e 'tell application "System Events" to count processes' >/dev/null 2>&1; then
    ok "접근성 권한"
    local wc; wc=$(osascript -e 'tell application "System Events" to tell process "KakaoTalk" to count windows' 2>/dev/null || echo 0)
    if [ "${wc:-0}" -gt 0 ]; then ok "카카오톡 창 ${wc}개 열림"
    else no "카카오톡 메인 창이 닫혀 있다 — 창을 열어둬야 전송이 된다"; fail=1; fi
  else
    no "접근성 권한 없음 — 시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용 에 터미널 추가"; fail=1
  fi

  echo "── 작업 공간 ──"
  echo "     KAKAO_HOME = $KHOME"
  [ -f "$KHOME/rooms.json" ] && ok "rooms.json 있음" || warn "rooms.json 없음 — 아래에서 만든다"
  return $fail
}

find_rooms() {
  local kw="$1"
  echo "── 오픈채팅 (NTOpenLink.linkName) ──"
  kakaocli query "SELECT r.chatId, r.activeMembersCount, o.linkName
                  FROM NTChatRoom r JOIN NTOpenLink o ON o.linkId=r.linkId
                  WHERE o.linkName LIKE '%$kw%'" 2>/dev/null \
  | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: d=[]
for cid,n,name in d: print('  %-20s %5s명  %s' % (cid, n, name))
print('  (없음)' if not d else '')"
  echo "── 일반 그룹방 (NTChatMeta type=3) ──"
  kakaocli query "SELECT chatId, content FROM NTChatMeta WHERE type=3 AND content LIKE '%$kw%'" 2>/dev/null \
  | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: d=[]
for cid,name in d: print('  %-20s        %s' % (cid, name))
print('  (없음)' if not d else '')"
}

case "${1:-}" in
  --check) check; exit $? ;;
  --find)  find_rooms "${2:?검색어가 필요하다}"; exit 0 ;;
esac

echo "╭─ 카톡 연동 점검 ─────────────────────────────"
check; CHECK=$?
echo "╰──────────────────────────────────────────────"
[ $CHECK -ne 0 ] && { echo; echo "위 항목을 먼저 해결하고 다시 실행해라."; exit 1; }

# ── 방 등록 ──
echo
mkdir -p "$KHOME/logs" "$KHOME/files" "$KHOME/chat"
ME=$(kakaocli status 2>/dev/null | awk -F': *' '/User ID/{print $2}' | tr -d ' ')
[ -z "$ME" ] && { echo "User ID 를 못 읽었다. kakaocli status 를 확인해라."; exit 1; }
echo "내 userId: $ME  (내가 보낸 메시지를 걸러내는 데 쓴다)"

if [ -f "$KHOME/rooms.json" ]; then
  echo "이미 rooms.json 이 있다: $KHOME/rooms.json"
  python3 "$HERE/room.py" list
  echo; echo "방을 더 넣으려면 이 파일을 직접 고치면 된다."
  exit 0
fi

echo
read -r -p "등록할 방 이름의 일부 (예: 우리팀): " KW
[ -z "${KW:-}" ] && { echo "취소"; exit 1; }
echo; find_rooms "$KW"
echo
read -r -p "chatId: " CID
read -r -p "별칭 (영문 짧게, 예: notice): " ALIAS
read -r -p "kmsg 가 검색할 방 이름 조각 (예: 우리팀 공지): " SEARCH
read -r -p "설명 (선택): " LABEL

python3 - "$KHOME/rooms.json" "$ME" "$CID" "$ALIAS" "$SEARCH" "${LABEL:-$SEARCH}" <<'PY'
import json, sys
path, me, cid, alias, search, label = sys.argv[1:7]
json.dump({
  "_note": [
    "카톡 방 레지스트리 — 모든 스크립트가 이 파일만 본다. 방을 바꾸려면 여기만 고친다.",
    "chatId : kakaocli(DB 읽기)용 숫자 ID. 기기마다 다를 수 있다. setup.sh --find 로 확인.",
    "search : kmsg(UI 전송)가 검색창에 칠 문자열. 다른 방에 함께 걸리지 않는 조각으로 고를 것.",
    "me     : 내 userId. 폴링에서 내가 보낸 메시지를 걸러내는 데 쓴다."
  ],
  "me": int(me),
  "default": alias,
  "rooms": {alias: {"chatId": int(cid), "search": search, "label": label, "note": ""}}
}, open(path, "w"), ensure_ascii=False, indent=2)
print("\n만들었다: %s" % path)
PY

echo
echo "확인:  scripts/krooms.sh"
echo "테스트: scripts/ksend.sh \"테스트\"      ← 사람 적은 방에서 먼저 해볼 것"
