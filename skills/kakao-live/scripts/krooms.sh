#!/bin/bash
# 방 목록 보기 / 기본 방 바꾸기 / 새 방 찾기
#   krooms.sh                    등록된 방 목록
#   krooms.sh --default work     기본 방 변경
#   krooms.sh --find 우리팀       카톡 DB에서 방 검색 (오픈채팅 + 일반 그룹방 둘 다)
#   krooms.sh --path             rooms.json 위치
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

case "${1:-list}" in
  --path) python3 "$HERE/room.py" path ;;
  --default) python3 "$HERE/room.py" set-default "${2:?별칭이 필요하다}" ;;
  --find)
    KW="${2:?검색어가 필요하다}"
    echo "=== 오픈채팅 (NTOpenLink.linkName) ==="
    kakaocli query "SELECT r.chatId, r.activeMembersCount, o.linkName
                    FROM NTChatRoom r JOIN NTOpenLink o ON o.linkId = r.linkId
                    WHERE o.linkName LIKE '%$KW%'" 2>&1
    echo "=== 일반 그룹방 (NTChatMeta type=3) ==="
    kakaocli query "SELECT chatId, content FROM NTChatMeta
                    WHERE type = 3 AND content LIKE '%$KW%'" 2>&1
    ;;
  list|*) python3 "$HERE/room.py" list ;;
esac
