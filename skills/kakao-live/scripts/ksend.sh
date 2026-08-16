#!/bin/bash
# 카톡 전송 래퍼 — 방은 rooms.json 에서 고르고, 무슨 일이 있었는지는 logs/ 에 남긴다.
#
#   ksend.sh "메시지"                 기본 방(rooms.json 의 default)
#   ksend.sh -r bang "메시지"          별칭으로 방 지정
#   KROOM=bang ksend.sh "메시지"       환경변수로도 됨
#   echo "메시지" | ksend.sh -r ham -   stdin
#   KSEND_TRACE=0 ksend.sh "..."      kmsg 의 AX 추적 끄기(기본 켬)
#
# 실측으로 확인한 것 (2026-08-15):
#  1) kmsg 는 기본으로 전송 후 채팅창을 닫는다 → 다음 전송이 매번 검색부터 다시 한다.
#     -k(--keep-window)를 주면 창이 남아 검색을 건너뛴다.
#  2) 검색은 카카오톡이 '채팅' 탭에 있을 때만 방을 찾는다. '친구' 탭이면 SEARCH_MISS.
#  3) kakaocli send 는 쓰지 마라 — 업스트림 Issue #9 로 전송이 멈춘다. 읽기 전용.
#  4) kmsg send --dry-run 은 AX 를 전혀 건드리지 않고 4줄 찍고 끝난다.
#     **동작 확인 수단이 아니다.** kakaocli 의 dry-run 과 같은 함정.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/klib.sh"

kroom_parse "$@"
set -- ${KROOM_ARGS+"${KROOM_ARGS[@]}"}

ALIAS=$(kroom "$KROOM_ALIAS" alias) || { klog room resolve.fail "arg=${KROOM_ALIAS:-?}" tool_caller=ksend; exit 1; }
CHAT=$(kroom  "$KROOM_ALIAS" search) || exit 1
LABEL=$(kroom "$KROOM_ALIAS" label)  || exit 1

if [ "${1:-}" = "-" ]; then MSG=$(cat); else MSG="${1:?message required}"; fi
# 개행은 카톡 UI에서 전송키로 처리돼 메시지가 쪼개진다. 한 줄로 만든다.
MSG=$(printf '%s' "$MSG" | tr '\n' ' ' | sed 's/  */ /g')
MSG="🤖 $MSG"

# 길면 카톡에서 벽처럼 보인다. 개행이 전송키라 한 메시지 안에서 줄을 못 바꾸므로
# **짧게 쓰는 것 말고 방법이 없다.** 2026-08-16 그렇게 지적받았다 — 그때 중앙 89자,
# 58%가 80자를 넘고 있었다. 눈에 안 보이니 계속 길어졌다. 그래서 잰다.
KSEND_WARN_LEN="${KSEND_WARN_LEN:-100}"
if [ "${#MSG}" -gt "$KSEND_WARN_LEN" ]; then
  echo "⚠ ${#MSG}자 — 카톡에선 길다. 한 생각만 남기고 끊어라 (기준 ${KSEND_WARN_LEN}자)" >&2
fi

TRACE=""; [ "${KSEND_TRACE:-1}" = "1" ] && TRACE="--trace-ax"

# 어느 방으로 나가는지 항상 남긴다 — 사람 많은 방에 오발송하면 되돌릴 수 없다
echo "→ [$ALIAS] $LABEL" >&2
klog ksend send.start "room=$ALIAS" "len=${#MSG}" "text=$MSG"

# kmsg 출력에서 AX 단서를 뽑는다. 무엇이 느렸는지는 여기에만 남는다.
ax_fields() {
  local out="$1" f=""
  printf '%s' "$out" | grep -qi "existing chat window" && f="$f existing_window=true"
  printf '%s' "$out" | grep -qi "search.miss\|not found\|찾을 수 없" && f="$f search_miss=true"
  printf '%s' "$out" | grep -qi "cache hit"  && f="$f ax_cache=hit"
  printf '%s' "$out" | grep -qi "cache miss" && f="$f ax_cache=miss"
  local n; n=$(printf '%s' "$out" | grep -ci "retry\|재시도" || true)
  [ "${n:-0}" -gt 0 ] && f="$f kmsg_retries=$n"
  printf '%s' "$f"
}

attempt_send() {   # attempt_send <시도번호>
  local n="$1" t0 dur out
  t0=$(now_ms)
  out=$(run_timeout 45 kmsg send -k $TRACE "$CHAT" "$MSG" 2>&1)
  dur=$(( $(now_ms) - t0 ))
  LAST_OUT="$out"; LAST_DUR="$dur"
  if printf '%s' "$out" | grep -q "✓"; then
    klog ksend send.ok "room=$ALIAS" "dur_ms=$dur" "attempt=$n" "len=${#MSG}" \
         $(ax_fields "$out") "raw=$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-500)"
    return 0
  fi
  return 1
}

# 1차: 창이 열려 있다고 보고 그냥 보낸다 (정상 상태에선 이 한 번으로 끝난다)
if attempt_send 1; then echo "SENT [$ALIAS] ${LAST_DUR}ms"; exit 0; fi
klog ksend send.retry "room=$ALIAS" "attempt=1" "dur_ms=$LAST_DUR" \
     $(ax_fields "$LAST_OUT") "raw=$(printf '%s' "$LAST_OUT" | tr '\n' ' ' | cut -c1-800)"

# 2차 이후: 탭을 맞추고 재시도 (kfocus 가 자기 계측을 따로 남긴다)
for i in 2 3 4; do
  kfocus
  if attempt_send "$i"; then echo "SENT [$ALIAS] ${LAST_DUR}ms (retry $((i-1)))"; exit 0; fi
  klog ksend send.retry "room=$ALIAS" "attempt=$i" "dur_ms=$LAST_DUR" \
       $(ax_fields "$LAST_OUT") "raw=$(printf '%s' "$LAST_OUT" | tr '\n' ' ' | cut -c1-800)"
  sleep 2
done

klog ksend send.fail "room=$ALIAS" "attempt=4" "len=${#MSG}" \
     $(ax_fields "$LAST_OUT") "raw=$(printf '%s' "$LAST_OUT" | tr '\n' ' ' | cut -c1-2000)"
echo "FAILED [$ALIAS]: $LAST_OUT" >&2
exit 1
