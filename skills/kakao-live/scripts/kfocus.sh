#!/bin/bash
# KakaoTalk을 '채팅' 탭으로 전환 — kmsg send 직전에 호출해야 SEARCH_MISS를 피한다.
#
# 계측도 겸한다. AppleScript(=Apple Event 왕복)가 무엇을 보고 무엇을 했는지 돌려주게 해서
# 로그에 남긴다. 여기서 나오는 값이 "왜 3초 걸렸나"에 답하는 유일한 단서다.
#   windows : 카톡 창 개수. 0이면 전송이 통째로 막힌다(알려진 지뢰)
#   buttons : AX 트리에서 훑은 버튼 수 — 탐색 비용의 대리 지표
#   step    : no_window | clicked | miss  — 어디까지 갔나
#   cancel  : 검색창이 열려 있어 '취소'를 눌렀는지
#   delay_ms: AppleScript 안의 고정 대기 총합. dur_ms 에서 빼야 순수 AE 왕복이 나온다
#
# KFOCUS_TRACE=1 이면 단계를 쪼개 각 단계 소요를 따로 잰다.
# 평소엔 한 번에 실행한다 — 쪼개면 Apple Event 왕복이 늘어 오히려 느려진다.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/klib.sh"

DELAY_MS=700   # AppleScript 안의 delay 0.4 + 0.3

run_focus() {
  osascript <<'AS' 2>/dev/null
tell application "System Events"
  if not (exists process "KakaoTalk") then return "step=no_process|windows=0|buttons=0|cancel=no"
  tell process "KakaoTalk"
    set wc to (count of windows)
    if wc = 0 then return "step=no_window|windows=0|buttons=0|cancel=no"
    set frontmost to true
    delay 0.4
    set didCancel to "no"
    try
      click button "취소" of text field 1 of window 1
      set didCancel to "yes"
      delay 0.3
    end try
    set btnCount to 0
    set theStep to "miss"
    repeat with b in (buttons of window 1)
      set btnCount to btnCount + 1
      try
        if (value of attribute "AXIdentifier" of b) is "chatrooms" then
          click b
          set theStep to "clicked"
          exit repeat
        end if
      end try
    end repeat
    return "step=" & theStep & "|windows=" & wc & "|buttons=" & btnCount & "|cancel=" & didCancel
  end tell
end tell
AS
}

# 단계별 계측 모드 — 각 osascript 호출을 bash 에서 따로 잰다
run_focus_traced() {
  local t0 r
  t0=$(now_ms); osascript -e 'tell application "System Events" to tell process "KakaoTalk" to set frontmost to true' >/dev/null 2>&1
  klog kfocus ae.step name=frontmost "dur_ms=$(( $(now_ms) - t0 ))"
  t0=$(now_ms); osascript -e 'tell application "System Events" to tell process "KakaoTalk" to click button "취소" of text field 1 of window 1' >/dev/null 2>&1
  klog kfocus ae.step name=cancel_search "dur_ms=$(( $(now_ms) - t0 ))"
  t0=$(now_ms); r=$(run_focus)
  klog kfocus ae.step name=find_click_tab "dur_ms=$(( $(now_ms) - t0 ))"
  printf '%s' "$r"
}

T0=$(now_ms)
if [ "${KFOCUS_TRACE:-0}" = "1" ]; then RES=$(run_focus_traced); else RES=$(run_focus); fi
DUR=$(( $(now_ms) - T0 ))

# "step=clicked|windows=1|buttons=7|cancel=no" 를 로그 필드로
[ -z "$RES" ] && RES="step=script_fail|windows=-1|buttons=-1|cancel=no"
klog kfocus ae.focus "dur_ms=$DUR" "delay_ms=$DELAY_MS" $(printf '%s' "$RES" | tr '|' ' ')

sleep 0.6
echo "$RES"
