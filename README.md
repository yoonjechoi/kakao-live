# kakao-live

**macOS 카카오톡을 에이전트가 실시간으로 읽고 답한다.**

[English](README.en.md)

```
방 등록 → 10초 폴링으로 새 메시지 수신 → 판단 → 답장 → 전부 로그
```

읽기는 로컬 DB, 쓰기는 접근성(AX) API. **이 분담이 핵심이다** — 이유는 아래 「함정」에 있다.

---

## 설치 (에이전트에게 시키는 경우)

> **AI 에이전트가 이 문서를 읽고 있다면**: 아래 순서를 그대로 따르면 된다.
> 사용자에게 물어야 하는 지점은 ⚠ 로 표시했다. 나머지는 알아서 진행해라.

### 1. Claude Code 에 설치

```
/plugin marketplace add yoonjechoi/kakao-live
/plugin install kakao-live@kakao-live
```

### 2. 준비 명령 한 번

```
/kakao-live:setup
```

**이거면 끝난다.** 도구 설치·권한 안내·방 등록·전송 확인까지 에이전트가 진행한다.
사람이 직접 해야 하는 건 macOS 권한 두 개와 카카오톡 로그인뿐이고, 그 지점에서 안내가 나온다.

아래 3~6번은 **수동으로 하거나 무엇이 일어나는지 알고 싶을 때** 참고한다.

### 3. 의존성 — 없으면 조용히 실패한다

```bash
brew install silver-flight-group/tap/kakaocli   # 카톡 DB 읽기
brew install channprj/tap/kmsg                  # 메시지 전송
brew install coreutils                          # timeout (macOS 에 없다)
```

설치 확인:

```bash
command -v kakaocli kmsg timeout && echo OK
```

### 4. ⚠ macOS 권한 2개 — **사용자가 직접 해야 한다**

에이전트는 이 설정을 대신 할 수 없다. 사용자에게 다음을 요청해라.

> 시스템 설정 → 개인정보 보호 및 보안 에서 **사용 중인 터미널 앱**에 두 가지를 켜주세요.
> - **전체 디스크 접근** — 카톡 DB 를 읽는 데 필요합니다
> - **손쉬운 사용** — 메시지를 보내는 데 필요합니다
>
> 켠 뒤 **터미널을 완전히 종료했다 다시 열어야** 적용됩니다.

확인:

```bash
kakaocli status        # App state: loggedIn 이 나와야 한다
```

`loggedIn` 이 아니면 권한이 없거나 카카오톡에 로그인이 안 된 것이다. **여기서 멈추고 사용자에게 알려라.**

### 5. ⚠ 카카오톡 데스크톱

**로그인되어 있고 메인 창이 열려 있어야 한다.** 창을 닫으면 접근성 트리가 창을 0개로 보고하고
전송이 통째로 막힌다. 화면이 잠겨 있어도 마찬가지다(읽기는 된다).

### 6. 방 등록

```bash
scripts/setup.sh                  # 대화형: 도구·권한 점검 → 방 검색 → rooms.json 생성
scripts/setup.sh --check          # 점검만
scripts/setup.sh --find 우리팀     # 방 검색만
```

방 이름 일부로 검색해 `chatId` 를 찾아준다(오픈채팅·일반 그룹방 양쪽).

### 7. 첫 전송은 사람 적은 방에서

```bash
scripts/ksend.sh -r <별칭> "테스트"
scripts/klog.sh stat              # 실제로 갔는지 확인
```

**2000명 방을 테스트에 쓰지 마라.** 전송은 사용자 계정으로 나간다.

---

## 사용

```bash
# 방
scripts/krooms.sh                     # 목록
scripts/krooms.sh --find 우리팀        # 새 방 찾기
scripts/krooms.sh --default work      # 기본 방 변경

# 받기
scripts/kpoll.sh                      # 기본 방, 10초 간격
scripts/kpoll.sh work notice          # 여러 방 동시 (한 프로세스, 쿼리 1회)
scripts/kpoll.sh all --replay 5       # 시작할 때 최근 5개 먼저
scripts/kpoll.sh --resume all         # 끊긴 지점부터 복구

# 보내기
scripts/ksend.sh "메시지"
scripts/ksend.sh -r work "메시지"
echo "긴 내용" | scripts/ksend.sh -
scripts/kimg.sh -r work 사진.jpg
scripts/kvid.sh -r work 영상.mp4               # 동영상·오디오·임의 파일
scripts/kvid.sh -r work -n cut-03 영상.mp4      # 보낼 이름을 지정 (케밥케이스)
scripts/kvid.sh --what cut-03                  # 그 이름이 어느 원본이었나
scripts/kvid.sh --names                        # 전체 대응표

# 첨부 받기
scripts/kget.sh --list                # 뭐가 있는지 먼저
scripts/kget.sh -r work --days 30
scripts/kget.sh --kind video          # image | video | file | all

# 점검
scripts/klog.sh tail                  # 사람이 읽는 형식
scripts/klog.sh stat                  # 성공률·소요·AX 비용
```

폴링 출력은 한 줄에 하나, 방 별칭이 붙는다.

```
[카톡/notice] 김감독: 이 컷 각도가 이상한데
[카톡/work] 철수쌤: 확인해볼게요
```

**Claude Code 에서는 Monitor 도구로 `persistent: true`** 로 띄운다. 각 줄이 이벤트로 들어온다.

---

## 작업 공간

모든 산출물이 `$KAKAO_HOME` 한 곳에 모인다. 기본값은 현재 디렉토리의 `.kakao/`.

```
.kakao/
├── rooms.json              방 레지스트리 ← 방을 바꾸려면 여기만 고친다
├── logs/YYYY-MM-DD.jsonl   구조화 로그
├── logs/.kpoll-cursor.json 폴링 커서
├── files/<방>/<날짜>/       내려받은 첨부
└── chat/YYYY-MM-DD.md      대화 롤업
```

여러 프로젝트에서 같은 방을 쓰려면 `export KAKAO_HOME=~/.kakao`.

> ⚠ **`.kakao/` 를 git 에 올리지 마라.** 단톡방 대화 본문과 받은 첨부가 그대로 쌓인다.

### rooms.json

```json
{
  "me": 9999999,
  "default": "work",
  "rooms": {
    "notice": { "chatId": 222222222222222222, "search": "우리팀 공지",
                "label": "우리팀 공지방", "note": "오픈채팅 2000명" },
    "work":   { "chatId": 111111111111111, "search": "작업",
                "label": "작업방", "note": "" }
  }
}
```

| 필드 | 무엇 | 쓰는 곳 |
|---|---|---|
| `chatId` | 숫자 ID | kakaocli — DB 읽기(폴링·첨부) |
| `search` | 방 이름의 **일부** | kmsg — UI 검색창에 쳐서 방을 찾는다(전송) |
| `me` | 내 userId | 내 메아리를 걸러내는 데 쓴다 |

성격이 다르니 헷갈리지 마라. `search` 는 **다른 방에 함께 걸리지 않는 조각**으로 고른다.

> `chatId` 는 **기기마다 다르다.** 다른 컴퓨터로 옮기면 `setup.sh --find` 로 다시 확인해라.

---

## 방에서 지킬 것

실제 단톡방에서 부딪히며 배운 것이다. 기술이 아니라 예절 문제다.

- **🤖 접두사를 떼지 마라.** `ksend.sh` 가 자동으로 붙인다.
  메시지는 **사용자 계정으로** 나간다. 표시가 없으면 사람이 쓴 것과 구분되지 않는다.
- **부를 때만 나와라.** 호명이나 질문이 있을 때만 답한다.
  작업 얘기라서 도움이 되겠다 싶어 끼어드는 것도 과하다.
- **방에는 결론 한두 줄까지.** 과정·수치·설계는 터미널로. 기술 대화를 방에 쏟지 마라.
- **한 메시지는 한 생각까지.** 개행이 전송키라 줄바꿈이 없다 — 길면 그대로 벽이 된다.
  `ksend.sh` 가 100자를 넘으면 경고한다. 경고가 뜨면 끊어라.
- **처음 들어갈 때는 사용자가 먼저 상황을 설명하게 한다.** 불쑥 봇이 말하면 놀란다.
- **개인정보를 묻는 말은 거절한다.** 남의 계정을 빌려 쓰는 처지다.
- 사람은 **방에 보이는 이름**으로 부른다. 실명을 알아도 쓰지 않는다(아래 함정).

---

## 함정 — 전부 실측으로 확인한 것

### `kakaocli send` 는 쓰지 마라
업스트림 이슈 #9 로 전송이 멈춘다. 이름을 못 찾으면 **exit 0 으로 조용히 끝난다**(메시지는 안 간다).
**보내기는 kmsg 로만.**

### `--dry-run` 은 동작 확인 수단이 아니다
`kakaocli` 도 `kmsg` 도 `--dry-run` 은 AX 를 전혀 건드리지 않는다.
전송 경로가 살아 있는지 보려면 **사람 적은 방에 실제로 한 줄 보내는 수밖에 없다.**

### 창이 0개면 전송이 통째로 막힌다
두 가지 원인이 있고 대처가 다르다.

| `windows=0` 인데 | 원인 | 대처 |
|---|---|---|
| 카톡 창 메뉴에도 창이 없다 | 창을 닫았다 | 메인 창을 연다 |
| 창 메뉴에는 창이 있다 | **화면 잠금** | 사람이 잠금을 풀어야 한다 |

```bash
ioreg -n Root -d1 -a | grep -A1 CGSSessionScreenIsLocked   # true 면 잠긴 것
```

**읽기는 잠겨 있어도 된다.** 폴링은 로컬 DB 라 무관하고, 쓰기만 막힌다.

### `nickName` 은 대화명이 아니다
일반 그룹방에서 `NTUser.nickName` 은 **주소록에 저장된 이름(실명)** 이 나온다.
방에 보이는 건 `displayName`. 실명으로 불러 사고 낸 적 있다.
게다가 한 userId 에 멀티프로필 행이 여러 개라 그냥 JOIN 하면 **메시지가 중복된다** —
`LIMIT 1` 서브쿼리로 뽑아야 한다.

### 내 메아리는 계정이 아니라 🤖 로 거른다
메시지가 **사용자 계정으로** 나가므로 `authorId <> me` 로 자기 메아리를 막고 싶어진다.
그러면 **그 계정 주인이 방에서 하는 말까지 통째로 안 보인다.** 실제로 35분을 놓쳤고
그중에 "너 내 말 듣고 있냐" 가 있었다. 거를 것은 계정이 아니라 🤖 접두사다.

### 폴링은 시간 커서로 해야 한다
"최신 N개를 떠서 logId 가 큰 것만" 은 세 가지로 메시지를 놓친다.

1. 사이에 N개 넘게 오면 밀려난 건 영영 안 온다
2. **`logId` 는 단조증가가 아니다** — 순서가 역전된 메시지가 영구 유실된다
3. `sentAt` 은 초 단위라 같은 초에 2~3건이 들어간다

`kpoll.py` 는 `sentAt` 커서로 **5초 겹치게** 읽고 `logId` 로 중복을 지우며,
한 번에 `LIMIT` 이 차면 커서를 당겨 즉시 다시 읽는다. 유실 0·중복 0 으로 검증했다.

### 개행은 전송키다
메시지에 개행이 있으면 카톡 UI 가 전송으로 처리해 쪼개진다. `ksend.sh` 가 공백으로 바꾼다.

### 메시지가 길면 벽이 된다
개행이 전송키라 **한 메시지 안에서 줄을 바꿀 방법이 없다.** 길게 쓰면 그대로 벽으로 붙는다.
`ksend.sh` 는 100자(`KSEND_WARN_LEN`)를 넘으면 경고하고, `klog.sh stat` 이 길이 분포를 같이 찍는다.
재지 않으면 계속 길어진다 — 실측 중앙 89자, 58%가 80자를 넘은 채로 굴러가고 있었다.

### 동영상은 `kmsg` 로 못 보낸다 — 붙여넣기로 넣는다
`kmsg` 에는 `send-image` 뿐이라 mp4 를 주면 NSImage 로 열려다 죽는다.
`kvid.sh` 는 NSPasteboard 에 파일 URL 을 올리고 편집 메뉴의 Paste 를 AX 로 클릭한다.

- AppleScript 의 `set the clipboard to POSIX file` 은 카톡이 안 받는다 — NSPasteboard 여야 한다.
- `set frontmost to true` 만으로는 키 입력이 카톡에 닿지 않는다. `activate` 를 해야 ⌘V·Return 이 먹는다.
- **성공 판정은 화면이 아니라 DB 로 한다.** 마지막 메시지의 **id** 가 바뀌었는지 보고,
  내용·타입으로 비교하지 마라 — 영상을 연달아 보내면 둘 다 `video` 라 "안 갔다"고 읽고
  재전송해 방을 도배한다.
- 보낼 때 **파일 이름을 짧은 케밥케이스로 바꿔 올린다**(원본은 그대로 둔다).
  `sfx_One_s_20260816_183555_pitchslow.mp3` 를 올려놓고 "어느 거요" 라고 물으면 사람은 못 짚는다.
  대응표는 `<KAKAO_HOME>/kvid_names.tsv`, 조회는 `kvid.sh --what <이름>`.

### 첨부는 인증 없이 받아진다
주소가 `NTChatMessage.attachment` JSON 안에 서명까지 박혀 있다.
`expire` 는 **밀리초** epoch(URL 의 `expires` 는 초). 지난 건 "만료"로 보고한다.

---

## 무엇이 잘못됐는지 보려면

도구들은 **조용히 실패하는 전력**이 있다. 그래서 전부 로그를 남긴다.

```bash
scripts/klog.sh stat
```

계측은 4계층이다.

| 계층 | 남기는 것 | 답할 수 있는 질문 |
|---|---|---|
| 래퍼 | `send.ok/retry/fail`, 소요, 시도 횟수 | 1회에 성공하는 비율 |
| Apple Event | 창 개수, AX 버튼 수, 순수 왕복 | 창이 닫혔나, 트리 탐색이 병목인가 |
| kmsg 내부 | 캐시 히트, 검색 실패 | 창 유지가 듣고 있나 |
| **필터 감사** | 폴링이 **버린** 행을 사유별로 | **조용한 게 없어서인가, 내가 안 들어서인가** |

마지막 계층이 중요하다. 필터가 조용히 메시지를 지우면 쿼리는 성공하고 행만 없으므로
`fail` 이 나지 않는다. **거르는 것을 만들면 몇 건을 버렸는지도 세야 한다** —
0 이어야 할 자리에 숫자가 찍히는 순간이 곧 경보다.

---

## 한계

- **macOS 전용.** 카카오톡 데스크톱 앱과 접근성 API 에 의존한다.
- 카카오톡이 **켜져 있고 로그인**돼 있어야 하고, **창이 열려 있고 화면 잠금이 풀려** 있어야 한다.
- 전송이 UI 자동화라 전송 중에 카톡 창이 잠깐 앞으로 나온다.
- 카카오톡 앱 업데이트로 접근성 트리가 바뀌면 전송이 깨질 수 있다.
- 첨부 URL 에는 만료가 있다.

## 개인정보

수신 메시지 **본문이 로그에 그대로 쌓인다.** 받은 첨부도 원본으로 저장된다.
`.kakao/` 를 공개 저장소에 올리지 마라.

## 라이선스

MIT
