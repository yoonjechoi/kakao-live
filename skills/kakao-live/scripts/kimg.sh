#!/bin/bash
# 카톡 이미지 전송 — 방은 rooms.json, 기록은 logs/.
#   kimg.sh /경로/파일.jpg
#   kimg.sh -r bang /경로/파일.jpg
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/klib.sh"

kroom_parse "$@"
set -- ${KROOM_ARGS+"${KROOM_ARGS[@]}"}

ALIAS=$(kroom "$KROOM_ALIAS" alias) || { klog room resolve.fail "arg=${KROOM_ALIAS:-?}" tool_caller=kimg; exit 1; }
CHAT=$(kroom  "$KROOM_ALIAS" search) || exit 1
LABEL=$(kroom "$KROOM_ALIAS" label)  || exit 1
CHATID=$(kroom "$KROOM_ALIAS" chatId) || exit 1

# 보내기 전에 **이 검색어가 정말 그 방 하나만 가리키는지** 확인한다.
# 부분일치라 여러 방에 걸리면 엉뚱한 방으로 나가고, 나간 건 되돌릴 수 없다(2026-08-16 철수쌤 지시).
# KROOM_SKIP_VERIFY=1 로 끌 수 있으나, 끄면 왜 껐는지 로그에 남는다.
if [ "${KROOM_SKIP_VERIFY:-0}" = "1" ]; then
  klog room verify.skipped "room=$ALIAS" "needle=$CHAT"
else
  if ! kroom_verify "$CHAT" "$CHATID"; then
    echo "전송을 멈췄다 — rooms.json 의 search 를 더 좁게 고쳐라 (방: $ALIAS)" >&2
    klog kimg send.blocked "room=$ALIAS" "needle=$CHAT" reason=ambiguous_room
    exit 1
  fi
fi


IMG="${1:?image path required}"
[ -f "$IMG" ] || { echo "그런 파일이 없다: $IMG" >&2; klog kimg image.fail "room=$ALIAS" err=no_such_file "path=$IMG"; exit 1; }
SIZE=$(stat -f %z "$IMG" 2>/dev/null || echo 0)

echo "→ [$ALIAS] $LABEL  ($(basename "$IMG"))" >&2
klog kimg image.start "room=$ALIAS" "file=$(basename "$IMG")" "bytes=$SIZE"

# 전송 전 마지막 메시지 id — 새 첨부가 붙었는지 판정하는 기준점
BEFORE_ID=$(kakaocli query "SELECT logId FROM NTChatMessage WHERE chatId=$CHATID ORDER BY sentAt DESC LIMIT 1" 2>/dev/null \
  | python3 -c 'import sys,json
try: print(json.load(sys.stdin)[0][0])
except Exception: print("")' 2>/dev/null)

for i in 1 2 3; do
  kfocus
  T0=$(now_ms)
  OUT=$(run_timeout 60 kmsg send-image "$CHAT" "$IMG" 2>&1)
  DUR=$(( $(now_ms) - T0 ))
  if printf '%s' "$OUT" | grep -q "✓"; then
    # 내가 올린 사진이 폴링에 "사진" 으로 되돌아오지 않게 logId 를 남긴다
    SENTID=$(record_sent_attachment "$CHATID" "$BEFORE_ID" || true)
    klog kimg image.ok "room=$ALIAS" "dur_ms=$DUR" "attempt=$i" "bytes=$SIZE" \
         "file=$(basename "$IMG")" "sent_id=${SENTID:-?}"
    echo "SENT [$ALIAS] ${DUR}ms"; exit 0
  fi
  klog kimg image.retry "room=$ALIAS" "attempt=$i" "dur_ms=$DUR" \
       "raw=$(printf '%s' "$OUT" | tr '\n' ' ' | cut -c1-800)"
  sleep 2
done
klog kimg image.fail "room=$ALIAS" "attempt=3" "bytes=$SIZE" \
     "raw=$(printf '%s' "$OUT" | tr '\n' ' ' | cut -c1-2000)"
echo "FAILED [$ALIAS]: $OUT" >&2; exit 1
