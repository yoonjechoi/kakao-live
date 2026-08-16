#!/bin/bash
# 카톡 동영상·파일 전송 — 방은 rooms.json, 기록은 logs/.
#
#   kvid.sh 영상.mp4                    기본 방
#   kvid.sh -r bang 영상.mp4             별칭으로 방 지정
#   kvid.sh -r bang 영상.mp4 "설명 한 줄"  캡션을 먼저 보내고 영상을 올린다
#
# 왜 kmsg 를 못 쓰나 (2026-08-16 실측):
#   kmsg 에는 send-image 뿐이고 동영상 서브커맨드가 없다. mp4 를 send-image 에 주면
#   NSImage 로 열려다 "Failed to load image" 로 죽는다. 그래서 붙여넣기로 넣는다.
#
# 여기까지 오는 데 네 번 헛짚었다. 다음 사람이 같은 길을 또 파지 않도록 적어둔다:
#   1) AppleScript `set the clipboard to POSIX file` → 카톡이 안 받는다.
#      NSPasteboard 에 public.file-url + NSFilenamesPboardType 으로 올려야 한다.
#   2) `set frontmost to true` 만으로는 **키 입력이 카톡에 닿지 않는다.**
#      `tell application "KakaoTalk" to activate` 를 해야 ⌘V·Return 이 먹는다.
#      이것이 진짜 원인이었다 — ⌘O·⌘⇧G 가 전부 무반응이던 이유가 이거다.
#   3) 파일 다이얼로그(⌘O)로 경로를 타이핑하는 길은 쓰지 마라.
#      경로에 한글이 있으면 IME 때문에 깨지고, 다이얼로그는 루트에 머문다.
#   4) 붙여넣기는 메뉴(편집 → Paste)를 AX 로 클릭하는 쪽이 ⌘V 보다 안정적이다.
#
# 성공 판정은 화면이 아니라 **DB** 로 한다. 시트가 닫힌 것과 실제로 전송된 것은 다르다.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/klib.sh"

# --what <이름> — 방에 보낸 짧은 이름이 어느 원본이었는지 조회한다.
# 이름을 바꿔 보내는 이상 이 조회가 없으면 나도 원본을 못 짚는다.
if [ "${1:-}" = "--what" ] || [ "${1:-}" = "--names" ]; then
  NAMEMAP="$(python3 "$HERE/kkhome.py" sub kvid_names.tsv)"
  [ -f "$NAMEMAP" ] || { echo "아직 보낸 게 없다: $NAMEMAP" >&2; exit 1; }
  if [ "${1}" = "--names" ]; then
    column -t -s "$(printf '\t')" "$NAMEMAP"
  else
    Q="${2:?--what 뒤에 이름이 필요하다}"
    awk -F'\t' -v q="$Q" 'NR>1 && ($1==q || $1==q".mp4" || $1==q".mp3" || index($1,q)==1) {
      printf "%s\n  원본: %s\n  방: %s  보낸시각: %s\n", $1,$2,$3,$4 }' "$NAMEMAP" | tail -8
  fi
  exit 0
fi

kroom_parse "$@"
set -- ${KROOM_ARGS+"${KROOM_ARGS[@]}"}

# -n <이름> — 보낼 때 쓸 짧은 이름
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -n|--name) KVID_NAME="${2:?-n 뒤에 이름이 필요하다}"; shift 2 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
set -- ${ARGS+"${ARGS[@]}"}

ALIAS=$(kroom "$KROOM_ALIAS" alias) || { klog room resolve.fail "arg=${KROOM_ALIAS:-?}" tool_caller=kvid; exit 1; }
CHAT=$(kroom   "$KROOM_ALIAS" search) || exit 1
LABEL=$(kroom  "$KROOM_ALIAS" label)  || exit 1
CHATID=$(kroom "$KROOM_ALIAS" chatId) || exit 1

# 보내기 전에 **이 검색어가 정말 그 방 하나만 가리키는지** 확인한다. (klib.sh 의 kroom_verify)
if [ "${KROOM_SKIP_VERIFY:-0}" = "1" ]; then
  klog room verify.skipped "room=$ALIAS" "needle=$CHAT"
else
  if ! kroom_verify "$CHAT" "$CHATID"; then
    echo "전송을 멈췄다 — rooms.json 의 search 를 더 좁게 고쳐라 (방: $ALIAS)" >&2
    klog kvid send.blocked "room=$ALIAS" "needle=$CHAT" reason=ambiguous_room
    exit 1
  fi
fi

VID="${1:?video path required}"
CAPTION="${2:-}"
[ -f "$VID" ] || { echo "그런 파일이 없다: $VID" >&2; klog kvid video.fail "room=$ALIAS" err=no_such_file "path=$VID"; exit 1; }
VID="$(cd "$(dirname "$VID")" && pwd)/$(basename "$VID")"   # 절대경로
SIZE=$(stat -f %z "$VID" 2>/dev/null || echo 0)

# ── 사람이 부를 수 있는 이름으로 바꿔서 보낸다 ────────────────────
# 2026-08-16 그렇게 지적받았다: "sfx_One_s_20260816_183555_pitchslow.mp3" 같은 걸 보내놓고
# 어느 거냐고 물으면 사람은 못 짚는다. **나는 다 기억하지만 사람은 아니다.**
# 그래서 보낼 때만 짧은 이름(영단어+2자리 숫자)으로 복사해 올린다. 원본은 안 건드린다.
#   -n 이름   직접 지정          예) -n slowA
#   기본값     파일명에서 영단어 하나 + 01,02… 순번
# 이름 규칙은 **케밥케이스**다 — 소문자 단어를 하이픈으로 잇는다 (2026-08-16 결정).
# camelCase 를 쓰지 마라. 사람이 소리내어 부를 때 대문자가 안 들린다 —
# "slowA" 는 말로 하면 "슬로우에이"인지 "슬로우 A"인지 갈리지만 "slow-a" 는 안 갈린다.
kebab() {
  printf '%s' "$1" \
    | sed -E 's/([a-z0-9])([A-Z])/\1-\2/g' \
    | tr '[:upper:]' '[:lower:]' \
    | tr '_ .' '---' \
    | sed -E 's/-+/-/g; s/^-//; s/-$//'
}
KVID_NAME="${KVID_NAME:-}"
if [ -n "$KVID_NAME" ]; then
  NICE=$(kebab "$KVID_NAME")
else
  # 파일명에서 알파벳 토막 중 가장 뜻이 있어 보이는 것 하나 + 두 자리 순번
  STEM=$(basename "$VID"); STEM="${STEM%.*}"
  WORD=$(printf '%s' "$STEM" | tr '_-' '\n\n' | grep -E '^[A-Za-z]{3,}$' | head -1)
  [ -z "$WORD" ] && WORD="clip"
  SEQ=$(( ($(date +%s) % 99) + 1 ))
  NICE=$(kebab "$(printf '%s-%02d' "$WORD" "$SEQ")")
fi
EXT="${VID##*.}"
SENDDIR=$(mktemp -d -t kvidsend)
SENDFILE="$SENDDIR/${NICE}.${EXT}"
cp "$VID" "$SENDFILE"

# 이름을 바꿨으면 **어디로 갔는지 반드시 남긴다.**
# klog 는 이벤트 로그라 날짜별로 흩어지고 파묻힌다. 나중에 "slowA 로 가자" 소리를 들었을 때
# 원본을 못 짚으면 이름 바꾼 게 오히려 독이 된다(2026-08-16 그렇게 지적받았다).
# 그래서 전용 대응표를 한 곳에 append 로 쌓는다. 조회는 `kvid.sh --what slowA`.
NAMEMAP="$(python3 "$HERE/kkhome.py" sub kvid_names.tsv)"
mkdir -p "$(dirname "$NAMEMAP")"
[ -f "$NAMEMAP" ] || printf 'sent_name\toriginal_path\troom\tsent_at\n' > "$NAMEMAP"
# 같은 이름을 다른 파일에 또 쓰면 사람이 헷갈린다 — 그 순간 경고한다
PREV=$(awk -F'\t' -v n="${NICE}.${EXT}" '$1==n {print $2}' "$NAMEMAP" | tail -1)
if [ -n "$PREV" ] && [ "$PREV" != "$VID" ]; then
  echo "⚠ '${NICE}.${EXT}' 는 전에 다른 파일이었다: $PREV" >&2
  klog kvid name.collide "room=$ALIAS" "name=${NICE}.${EXT}" "prev=$PREV" "now=$VID"
fi
printf '%s\t%s\t%s\t%s\n' "${NICE}.${EXT}" "$VID" "$ALIAS" "$(date '+%Y-%m-%dT%H:%M:%S')" >> "$NAMEMAP"

echo "   보낼 이름: $(basename "$SENDFILE")  ← $(basename "$VID")" >&2
klog kvid rename "room=$ALIAS" "from=$(basename "$VID")" "to=$(basename "$SENDFILE")"
VID="$SENDFILE"

echo "→ [$ALIAS] $LABEL  ($(basename "$VID"), $((SIZE/1024))KB)" >&2
klog kvid video.start "room=$ALIAS" "file=$(basename "$VID")" "bytes=$SIZE"

# 전송 전 마지막 메시지 — 이걸로 실제 전송 여부를 판정한다
# 마지막 메시지의 **고유 id** 를 본다.
# 내용/타입 서명으로 비교하면 안 된다 — 영상을 연달아 보내면 둘 다 "video|동영상" 이라
# 변화 없음으로 읽고 재전송해 방을 도배한다(2026-08-16, 두 번 당했다).
# id 는 메시지마다 달라서 "새 메시지가 붙었나"를 정확히 판정한다.
last_msg_sig() {
  kakaocli messages --chat-id "$CHATID" --limit 1 --json 2>/dev/null \
    | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    m=d[-1] if d else {}
    print(str(m.get("id") or "?")+"|"+(m.get("type") or "?"))
except Exception:
    print("?|?")' 2>/dev/null || echo "?|?"
}
BEFORE=$(last_msg_sig)

# 채팅창이 열려 있어야 붙여넣을 곳이 생긴다.
# 창이 없으면 캡션을 kmsg 로 보내며 연다(-k 로 남긴다). 캡션이 없으면 파일명으로 연다.
window_open() {
  osascript -e "tell application \"System Events\" to tell process \"KakaoTalk\" to return (exists window \"$LABEL\")" 2>/dev/null
}
if [ "$(window_open)" != "true" ] || [ -n "$CAPTION" ]; then
  OPEN_MSG="${CAPTION:-$(basename "$VID") 올립니다}"
  kfocus
  run_timeout 45 kmsg send -k "$CHAT" "🤖 $OPEN_MSG" >/dev/null 2>&1
  klog kvid caption.sent "room=$ALIAS" "len=${#OPEN_MSG}" "text=🤖 $OPEN_MSG"
  sleep 1
fi

# 파일을 클립보드에 올린다 — 반드시 NSPasteboard 로. AppleScript clipboard 는 안 통한다.
pb_put() {
  VIDPATH="$1" osascript -l JavaScript <<'JXA' 2>/dev/null
ObjC.import('AppKit');
var p = $.NSProcessInfo.processInfo.environment.objectForKey('VIDPATH').js;
var pb = $.NSPasteboard.generalPasteboard;
pb.clearContents;
pb.writeObjects($([$.NSURL.fileURLWithPath($(p))])) ? "ok" : "fail";
JXA
}

# 방 이름을 osascript 에 넘길 때 `system attribute` 를 쓰지 마라 — UTF-8 한글이 깨진다.
# "소중한 우리팀…" 가 "�以� �＿濡洹�…" 로 와서 window 매칭이 통째로 실패한다(2026-08-16).
# 임시 파일에 적고 `do shell script "cat"` 으로 읽으면 온전히 넘어온다.
paste_and_send() {
  local lf; lf=$(mktemp -t kvidlabel)
  printf '%s' "$1" > "$lf"
  KVID_LABEL_FILE="$lf" osascript <<'AS' 2>/dev/null
set labelFile to (system attribute "KVID_LABEL_FILE")
set theLabel to (do shell script "cat " & quoted form of labelFile)
tell application "KakaoTalk" to activate
delay 1.2
tell application "System Events"
  tell process "KakaoTalk"
    set w to window theLabel
    try
      perform action "AXRaise" of w
    end try
    delay 0.6
    try
      set focused of text area 1 of scroll area 2 of w to true
    end try
    delay 0.4
    -- 붙여넣기는 메뉴로. ⌘V 보다 확실하다. 메뉴 이름은 로케일에 따라 둘 중 하나다.
    try
      click menu item "Paste" of menu 1 of menu bar item "편집" of menu bar 1
    on error
      click menu item "붙여넣기" of menu 1 of menu bar item "편집" of menu bar 1
    end try
    delay 2.5
    -- 확인 시트가 뜬다. 기본 버튼(Return)으로 보낸다.
    set had to (count of sheets of w)
    if had > 0 then
      key code 36
      delay 3.0
    end if
    return "sheet_seen=" & (had as text) & " sheet_left=" & ((count of sheets of w) as text)
  end tell
end tell
AS
  rm -f "$lf"
}

for i in 1 2 3; do
  T0=$(now_ms)
  PB=$(pb_put "$VID")
  if [ "$PB" != "ok" ]; then
    klog kvid video.retry "room=$ALIAS" "attempt=$i" err=pasteboard_fail
    sleep 2; continue
  fi
  RES=$(paste_and_send "$LABEL")
  DUR=$(( $(now_ms) - T0 ))

  sleep 2
  AFTER=$(last_msg_sig)
  TYPE="${AFTER##*|}"
  # 화면이 아니라 DB 로 판정한다 — 시트가 닫혀도 안 간 적이 있다.
  #
  # 판정을 타입 화이트리스트로 걸지 마라. mp3 는 type=unknown 으로 들어와서
  # video/file/image 만 인정하던 판정이 **성공을 실패로 읽고 3번 재전송해 방을 도배했다**
  # (2026-08-16). 첨부는 종류가 계속 늘어나므로 "text 가 아니면 붙은 것"으로 뒤집는다.
  if [ "$AFTER" != "$BEFORE" ] && [ "$TYPE" != "text" ]; then
    klog kvid video.ok "room=$ALIAS" "dur_ms=$DUR" "attempt=$i" "bytes=$SIZE" \
         "file=$(basename "$VID")" "msg_type=$TYPE" "$RES"
    echo "SENT [$ALIAS] ${DUR}ms type=$TYPE  이름=$(basename "$VID")"
    rm -rf "$SENDDIR"
    exit 0
  fi
  klog kvid video.retry "room=$ALIAS" "attempt=$i" "dur_ms=$DUR" "$RES" \
       "before=$BEFORE" "after=$AFTER"
  sleep 2
done

klog kvid video.fail "room=$ALIAS" "attempt=3" "bytes=$SIZE" "file=$(basename "$VID")" \
     "before=$BEFORE" "after=$(last_msg_sig)"
echo "FAILED [$ALIAS] — DB 에 영상이 안 찍혔다. logs 확인." >&2
rm -rf "$SENDDIR"
exit 1
