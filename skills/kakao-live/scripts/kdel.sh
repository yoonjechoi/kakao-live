#!/usr/bin/env bash
# 카톡 메시지 삭제 — 내가 보낸 마지막 메시지를 지운다.
#
#   kdel.sh -r bang                 마지막 내 메시지 1건
#   kdel.sh -r bang --dry           클릭하지 않고 좌표만 계산해 보여준다
#
# ── 알아낸 것 (2026-08-17) ────────────────────────────────────
# 1) **창을 먼저 좌클릭해 활성화해야 우클릭 메뉴가 뜬다.** 이것이 없으면
#    `orca` 든 Quartz 든 우클릭이 그냥 먹히지 않는다. 반나절을 여기서 썼다.
# 2) 합성 클릭(`orca computer click`)으로도 뜨지만 **Quartz CGEvent 가 확실**하다.
# 3) 컨텍스트 메뉴는 **AX 트리에 안 잡힌다**(`menus of app: 0`). 좌표로만 누른다.
# 4) 메뉴 구성이 방 종류에 따라 다르다.
#      오픈채팅  : 모두에게서 삭제 / 나에게서만 삭제 / 가리기
#      일반 그룹 : **나에게서만 삭제** 만
# 5) 「나에게서만 삭제」는 **선택 모드 → 체크박스 → 확인 → 삭제** 4단계다.
#    한 번의 클릭으로 끝나지 않는다.
# 6) 지워도 **DB(NTChatMessage)에는 남는다.** 판정은 화면으로 해야 한다.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/klib.sh"
kroom_parse "$@"; set -- "${KROOM_ARGS[@]:-}"
DRY=0; [ "${1:-}" = "--dry" ] && DRY=1

LABEL=$(kroom "$KROOM_ALIAS" search) || exit 1
WIN=$(orca computer list-windows --app "카카오톡" 2>/dev/null | grep -F "$LABEL" | head -1)
[ -z "$WIN" ] && { echo "방 창이 안 열려 있다. 먼저 ksend 로 메시지를 보내 창을 연다." >&2; exit 1; }

WID=$(printf '%s' "$WIN" | sed -E 's/.*id:([0-9]+).*/\1/')
# 한글이 섞인 줄을 파이프로 넘기면 깨진다 — sed 로 뽑는다
# 한글이 섞인 줄이라 sed 치환이 통째로 실패한다 — grep -o 로 숫자만 뽑는다
# ★ '@' 뒤에 공백이 온다: "(668x781 @ 1242,472)" — 공백을 빠뜨리면 매칭이 통째로 실패한다
COORD=$(printf '%s' "$WIN" | grep -oE '@ *[0-9]+,[0-9]+' | tr -d '@ ')
OX="${COORD%%,*}"
OY="${COORD##*,}"
echo "  창 id=$WID 원점=($OX,$OY)"

if [ "$DRY" = "1" ]; then
  echo "  --dry: 클릭하지 않는다"
  exit 0
fi
echo "  ※ 말풍선 좌표는 화면을 보고 정해야 한다 — 자동 검출은 아직 없다."
echo "     kdel_click.py 로 좌표를 넘겨 실행한다."
