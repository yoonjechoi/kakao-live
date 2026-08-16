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

IMG="${1:?image path required}"
[ -f "$IMG" ] || { echo "그런 파일이 없다: $IMG" >&2; klog kimg image.fail "room=$ALIAS" err=no_such_file "path=$IMG"; exit 1; }
SIZE=$(stat -f %z "$IMG" 2>/dev/null || echo 0)

echo "→ [$ALIAS] $LABEL  ($(basename "$IMG"))" >&2
klog kimg image.start "room=$ALIAS" "file=$(basename "$IMG")" "bytes=$SIZE"

for i in 1 2 3; do
  kfocus
  T0=$(now_ms)
  OUT=$(run_timeout 60 kmsg send-image "$CHAT" "$IMG" 2>&1)
  DUR=$(( $(now_ms) - T0 ))
  if printf '%s' "$OUT" | grep -q "✓"; then
    klog kimg image.ok "room=$ALIAS" "dur_ms=$DUR" "attempt=$i" "bytes=$SIZE" "file=$(basename "$IMG")"
    echo "SENT [$ALIAS] ${DUR}ms"; exit 0
  fi
  klog kimg image.retry "room=$ALIAS" "attempt=$i" "dur_ms=$DUR" \
       "raw=$(printf '%s' "$OUT" | tr '\n' ' ' | cut -c1-800)"
  sleep 2
done
klog kimg image.fail "room=$ALIAS" "attempt=3" "bytes=$SIZE" \
     "raw=$(printf '%s' "$OUT" | tr '\n' ' ' | cut -c1-2000)"
echo "FAILED [$ALIAS]: $OUT" >&2; exit 1
