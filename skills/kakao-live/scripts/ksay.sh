#!/bin/bash
# 카톡에 **문단으로** 보낸다 — 줄바꿈이 살아 있는 한 메시지.
#
#   ksay.sh -r work "첫 줄
#   둘째 줄
#   셋째 줄"
#   cat 글.txt | ksay.sh -r work -
#
# 왜 ksend.sh 와 따로 있나 (2026-08-16 팀장 지시:
# "메세지를 문단으로 길게 보내자. 10줄씩 보내자. 10줄보다 작으면 바로 보내고"):
#
#   ksend.sh 는 kmsg 로 **타이핑**해서 보낸다. 카톡 입력창은 개행이 곧 전송키라
#   여러 줄을 치면 메시지가 그 자리에서 쪼개진다. 그래서 ksend 는 개행을 " / " 로 바꾼다.
#   한 생각만 짧게 보내야 했던 이유가 그것이다.
#
#   이 도구는 **입력창 값을 통째로 써넣고 전송 버튼을 누른다**(orca computer).
#   타이핑이 아니라 값 설정이라 개행이 살아남는다. 실측으로 확인했다 —
#   3줄을 넣으니 DB 에 '...입니다.\n...바뀌면\n...보내겠습니다.' 로 한 건이 들어갔다.
#
# ⚠ 요소 인덱스는 **매 전송마다 바뀐다.**
#   메시지가 쌓이면 대화 내역 요소가 늘어 트리 전체가 밀린다.
#   인덱스를 고정해두고 연달아 보냈다가 중복 전송 사고를 냈다(2026-08-16, 김감독께 2건).
#   그래서 여기서는 **보내기 직전에 매번 트리를 다시 읽는다.**
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/klib.sh"

CHUNK="${KSAY_CHUNK:-10}"      # 몇 줄씩 끊어 보낼지. 이보다 짧으면 그대로 한 번에 나간다
ORCA="${ORCA_CLI_COMMAND:-orca}"
BUNDLE="com.kakao.KakaoTalkMac"

kroom_parse "$@"
set -- ${KROOM_ARGS+"${KROOM_ARGS[@]}"}

ALIAS=$(kroom "$KROOM_ALIAS" alias) || { klog room resolve.fail "arg=${KROOM_ALIAS:-?}" tool_caller=ksay; exit 1; }
LABEL=$(kroom "$KROOM_ALIAS" label)  || exit 1
CHAT=$(kroom  "$KROOM_ALIAS" search) || exit 1
CHATID=$(kroom "$KROOM_ALIAS" chatId) || exit 1

# 창을 id 로 직접 짚으므로 이름 부분일치 사고는 없다. 그래도 방 등록이 맞는지는 본다.
if [ "${KROOM_SKIP_VERIFY:-0}" != "1" ]; then
  kroom_verify "$CHAT" "$CHATID" || {
    echo "전송을 멈췄다 — rooms.json 의 search 를 더 좁게 고쳐라 (방: $ALIAS)" >&2
    klog ksay send.blocked "room=$ALIAS" "needle=$CHAT" reason=ambiguous_room; exit 1; }
fi

if [ "${1:-}" = "-" ]; then BODY=$(cat); else BODY="${1:?보낼 내용이 필요하다}"; fi
[ -z "${BODY//[[:space:]]/}" ] && { echo "빈 내용이다" >&2; exit 1; }

# 방 이름으로 창 id 를 찾는다 (창이 없으면 kmsg 로 한 번 열어준다)
find_window() {
  "$ORCA" computer list-windows --app "$BUNDLE" --json 2>/dev/null \
    | LABEL="$LABEL" python3 -c '
import sys, json, os
want = os.environ["LABEL"]
try: d = json.load(sys.stdin)
except Exception: sys.exit()
for w in d.get("result", {}).get("windows", []):
    if (w.get("title") or "") == want:
        print(w.get("id")); break'
}

WID=$(find_window)
if [ -z "$WID" ]; then
  echo "  창이 없다 — 연다" >&2
  kfocus
  run_timeout 45 kmsg read "$CHAT" --limit 1 -k >/dev/null 2>&1
  sleep 2
  WID=$(find_window)
fi
[ -z "$WID" ] || [ "$WID" = "None" ] && { echo "창을 못 찾았다: [$LABEL]" >&2; klog ksay window.fail "room=$ALIAS"; exit 1; }

# 입력창·전송 버튼 인덱스를 **지금** 읽는다. 캐시하지 마라 — 매 전송마다 달라진다.
read_idx() {
  "$ORCA" computer get-app-state --app "$BUNDLE" --window-id "$WID" --json --no-screenshot 2>/dev/null \
    | python3 -c '
import sys, json, re
try: d = json.load(sys.stdin)
except Exception: sys.exit()
if not d.get("ok"): sys.exit()
inp = snd = ""
for ln in d["result"]["snapshot"]["treeText"].splitlines():
    s = ln.strip()
    m = re.match(r"^(\d+)\s", s)
    if not m: continue
    if "메시지 입력" in s and "엔트리" in s: inp = m.group(1)
    if "전송" in s and "버튼" in s:          snd = m.group(1)
print(inp, snd)'
}

send_one() {   # send_one <문단>
  local text="$1" idx snd t0 dur
  read -r idx snd < <(read_idx)
  if [ -z "$idx" ] || [ -z "$snd" ]; then
    klog ksay idx.fail "room=$ALIAS" "wid=$WID"; return 1
  fi
  t0=$(now_ms)
  "$ORCA" computer set-value --app "$BUNDLE" --window-id "$WID" \
      --element-index "$idx" --value "$text" --json --no-screenshot >/dev/null 2>&1
  sleep 2.0
  # ★ 값을 넣으면 트리가 다시 그려져 **전송 버튼 인덱스가 바뀐다** (122 → 128 로 변하는 것을 봤다).
  #   설정 전에 읽은 인덱스로 누르면 엉뚱한 버튼을 눌러 조용히 아무 일도 안 일어난다.
  #   그래서 값을 넣은 **뒤에** 한 번 더 읽는다.
  local snd2
  read -r _ snd2 < <(read_idx)
  [ -n "$snd2" ] && snd="$snd2"
  "$ORCA" computer click --app "$BUNDLE" --window-id "$WID" \
      --element-index "$snd" --json --no-screenshot >/dev/null 2>&1
  sleep 2.2
  dur=$(( $(now_ms) - t0 ))
  # 화면이 아니라 DB 로 판정한다
  local got
  got=$(run_timeout 25 kakaocli messages --chat-id "$CHATID" --limit 1 --json 2>/dev/null \
        | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print((d[-1].get("text") or "").strip() if d else "")
except Exception: print("")')
  # sed 는 줄 단위라 여러 줄 문자열의 뒷공백을 못 다듬는다 — 파이썬으로 비교한다
  local want
  want=$(printf '%s' "$text" | python3 -c 'import sys;sys.stdout.write(sys.stdin.read().strip())')
  if [ "$got" = "$want" ]; then
    klog ksay say.ok "room=$ALIAS" "dur_ms=$dur" "lines=$(printf '%s\n' "$text" | wc -l | tr -d ' ')" "idx=$idx"
    return 0
  fi
  klog ksay say.mismatch "room=$ALIAS" "dur_ms=$dur" "sent=$(printf '%s' "$text" | head -c 60)"
  return 1
}

echo "→ [$ALIAS] $LABEL  (창 $WID)" >&2
TOTAL=$(printf '%s\n' "$BODY" | wc -l | tr -d ' ')
klog ksay say.start "room=$ALIAS" "lines=$TOTAL" "chunk=$CHUNK"

# 문단이 몇 개 나올지 먼저 센다 — "1/3" 처럼 전체를 같이 보여주려면 필요하다
NPARA=$(printf '%s\n' "$BODY" | python3 -c '
import sys
n=int(sys.argv[1]); ls=sys.stdin.read().rstrip("\n").split("\n")
ls=[l for l in ls]
print((len(ls)+n-1)//n)' "$CHUNK")

# CHUNK 줄씩 끊는다. 그보다 짧으면 통째로 한 번에.
#
# 문단마다 **🤖 와 번호를 앞에 붙인다** (2026-08-16 팀장 지시).
# 이유가 있다 — 여러 문단이 연달아 오면 어디가 하나의 글이고 어디서 끊겼는지
# 받는 사람이 알 수 없다. 번호가 있으면 "2번째가 안 왔다" 를 사람이 바로 짚는다.
# 문단이 하나뿐이면 번호는 군더더기라 🤖 만 붙인다.
FAIL=0; N=0
while IFS= read -r -d '' PARA; do
  [ -z "${PARA//[[:space:]]/}" ] && continue
  N=$((N+1))
  # 호출자가 이미 🤖 를 붙였으면 떼고 다시 붙인다 — 두 번 찍히면 지저분하다
  PARA="${PARA#🤖 }"
  if [ "$NPARA" -gt 1 ]; then
    PARA="🤖 ${N}/${NPARA}
${PARA}"
  else
    PARA="🤖 ${PARA}"
  fi
  if send_one "$PARA"; then
    echo "  ✓ 문단$N ($(printf '%s\n' "$PARA" | wc -l | tr -d ' ')줄)"
  else
    echo "  ✗ 문단$N 실패" >&2; FAIL=$((FAIL+1))
  fi
done < <(printf '%s\n' "$BODY" | python3 -c '
import sys
n = int(sys.argv[1])
lines = sys.stdin.read().rstrip("\n").split("\n")
for i in range(0, len(lines), n):
    sys.stdout.write("\n".join(lines[i:i+n]) + "\0")
' "$CHUNK")

if [ "$FAIL" -gt 0 ]; then
  klog ksay say.fail "room=$ALIAS" "failed=$FAIL" "of=$N"
  echo "FAILED [$ALIAS] $FAIL/$N 문단" >&2; exit 1
fi
klog ksay say.done "room=$ALIAS" "paras=$N" "lines=$TOTAL"
echo "SENT [$ALIAS] $N 문단 / $TOTAL 줄"
