---
description: 카카오톡 연결을 처음부터 끝까지 준비한다 — 도구 설치, 권한 안내, 방 등록, 전송 확인까지
---

# 카카오톡 연결 준비

사용자가 이 명령을 쳤다. **끝까지 네가 진행해라.** 사용자에게 되묻는 건 아래 ⚠ 지점뿐이다.
각 단계는 **결과를 확인하고** 다음으로 넘어간다. 확인 없이 "됐습니다" 라고 말하지 마라.

## 1. 도구

```bash
command -v kakaocli kmsg timeout
```

빠진 게 있으면 설치한다. **사용자에게 묻지 말고 바로 설치해라** — 이 명령을 친 것이 곧 요청이다.

```bash
brew install silver-flight-group/tap/kakaocli   # 카톡 DB 읽기
brew install channprj/tap/kmsg                  # 메시지 전송
brew install coreutils                          # timeout (macOS 에 없다)
```

`brew` 자체가 없으면 https://brew.sh 를 안내하고 **여기서 멈춘다.**

## 2. 권한 — ⚠ 사람만 할 수 있다

```bash
kakaocli status
```

`App state: loggedIn` 이 나오면 3번으로 간다. 아니면 아래를 **그대로 사용자에게 보여주고 기다린다.**

> 시스템 설정 → 개인정보 보호 및 보안 에서 **지금 쓰는 터미널 앱**에 두 가지를 켜주세요.
>
> - **전체 디스크 접근** — 카톡 대화를 읽는 데 필요합니다
> - **손쉬운 사용** — 메시지를 보내는 데 필요합니다
>
> 켜신 뒤 **터미널을 완전히 끄고 다시 열어주세요.** 그래야 적용됩니다.
> 그리고 **카카오톡 데스크톱 앱을 로그인 상태로 열어두세요.** 창이 닫혀 있으면 전송이 막힙니다.

다시 열고 나면 `kakaocli status` 로 재확인한다. **통과할 때까지 다음으로 넘어가지 마라.**

## 3. 방 등록

먼저 어느 방에 연결할지 ⚠ 사용자에게 묻는다. **방 이름의 일부**를 받으면 된다.

```bash
${CLAUDE_PLUGIN_ROOT}/skills/kakao-live/scripts/krooms.sh --find <이름조각>
```

오픈채팅과 일반 그룹방을 함께 조회한다. 여러 개가 나오면 어느 것인지 사용자에게 확인한다.

찾았으면 `$KAKAO_HOME/rooms.json`(기본 `./.kakao/rooms.json`) 을 만든다.
`setup.sh` 를 써도 되고 직접 써도 된다.

```json
{
  "me": <내 userId>,
  "default": "work",
  "rooms": {
    "work": { "chatId": <숫자ID>, "search": "<이름조각>", "label": "<방 이름>", "note": "" }
  }
}
```

`me` 는 사용자 본인의 userId 다. 이렇게 찾는다.

```bash
kakaocli query "SELECT DISTINCT authorId FROM NTChatMessage WHERE chatId=<chatId> ORDER BY logId DESC LIMIT 20"
```

어느 것이 본인인지 확실하지 않으면 사용자에게 확인한다.

**`search` 는 다른 방에 함께 걸리지 않는 조각으로 골라라.** 잘못 고르면 엉뚱한 방으로 간다.
정하기 전에 반드시 확인한다.

```bash
${CLAUDE_PLUGIN_ROOT}/skills/kakao-live/scripts/kfind.sh --rooms <이름조각>
```

`⚠ N 곳에 걸린다` 가 뜨면 **그 조각을 쓰지 마라.** 각 방의 전체 이름에서
다른 방에 없는 조각을 다시 골라 같은 방법으로 확인한다. `✓ 한 곳만 가리킨다` 여야 넘어간다.
(그래도 놓치면 전송 래퍼가 보내기 직전에 다시 세어 멈춘다 — 하지만 여기서 잡는 게 낫다.)

## 4. 실제로 되는지 확인 — 건너뛰지 마라

**`--dry-run` 은 확인 수단이 아니다.** AX 를 전혀 건드리지 않는다.
`kakaocli send` 도 쓰지 마라 — 조용히 exit 0 으로 끝난다.

⚠ **사람 적은 방**에서 한 줄 보내도 되는지 사용자에게 확인한 뒤 보낸다.

```bash
${CLAUDE_PLUGIN_ROOT}/skills/kakao-live/scripts/ksend.sh -r work "연결 확인용 메시지입니다"
${CLAUDE_PLUGIN_ROOT}/skills/kakao-live/scripts/klog.sh stat
```

`send.ok` 가 찍혀야 성공이다. 실패하면 원인은 대개 셋 중 하나다.

| 증상 | 원인 | 대처 |
|---|---|---|
| `windows=0`, 창 메뉴도 비었다 | 카톡 창을 닫았다 | 메인 창을 열어달라고 한다 |
| `windows=0`, 창 메뉴엔 창이 있다 | **화면 잠금** | 사람이 잠금을 풀어야 한다 |
| `SEARCH_MISS` | `search` 조각이 안 맞는다 | rooms.json 의 `search` 를 고친다 |

```bash
ioreg -n Root -d1 -a | grep -A1 CGSSessionScreenIsLocked   # true 면 잠긴 것
```

## 5. 받기 시작

```bash
${CLAUDE_PLUGIN_ROOT}/skills/kakao-live/scripts/kpoll.sh --interval 10 work
```

**Monitor 도구로 `persistent: true`** 로 띄운다. 새 메시지가 한 줄씩 이벤트로 들어온다.

## 마치면 사용자에게 알린다

무엇이 준비됐는지, 그리고 **방에서 지킬 것**을 짧게 전한다.

- 메시지는 **사용자 계정으로** 나가고 🤖 가 자동으로 붙는다. 떼지 않는다
- **부를 때만 나온다.** 잡담이나 남의 대화에 끼어들지 않는다
- 방에는 결론 한두 줄까지. 긴 설명은 여기(터미널)로 한다

자세한 것은 `${CLAUDE_PLUGIN_ROOT}/README.md`.
