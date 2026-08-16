---
name: kakao-live
description: macOS 카카오톡을 실시간으로 읽고 답하는 에이전트 도구 모음. 방을 10초마다 폴링해 새 메시지를 스트림으로 받고, 메시지·이미지·동영상을 보내고, 사진·동영상·파일 첨부를 원본으로 내려받고, 모든 동작을 구조화 로그로 남긴다. 여러 방을 동시에 다룬다. 트리거 — "카톡 봇", "카톡 실시간", "카톡으로 대화해", "카톡 폴링", "카톡방 모니터링", "카톡으로 보내줘", "카톡으로 영상 보내줘", "카톡 첨부 받아줘", "카톡 사진 다운로드", "단톡방 자동응답", "kakao bot", "kakaotalk live", "kakao polling".
---

# kakao-live

macOS 카카오톡 데스크톱 앱을 상대로 **읽기는 로컬 DB, 쓰기는 UI 자동화**로 처리한다.
이 분담은 바꾸지 마라 — 이유는 아래 「함정」에 있다.

| | 도구 | 방식 |
|---|---|---|
| 읽기 | `kakaocli` | 로컬 DB 직접 조회. 안정적 |
| 쓰기 | `kmsg` | 접근성(AX) API로 UI 조작 |

## 준비가 안 돼 있으면 먼저 준비한다

이 스킬이 발동했는데 `$KAKAO_HOME/rooms.json`(기본 `./.kakao/rooms.json`) 이 없으면
**아직 연결이 안 된 것이다.** 사용자에게 명령을 더 치라고 하지 말고 `/kakao-live:setup` 의
절차를 그대로 수행해라 — 도구 설치, 권한 안내, 방 등록, 전송 확인까지.

```bash
kakaocli status                                  # loggedIn 이어야 한다
ls "${KAKAO_HOME:-./.kakao}/rooms.json"          # 없으면 준비부터
```

사람이 대신 해야 하는 건 **macOS 권한 두 개(전체 디스크 접근·손쉬운 사용)와 카카오톡 로그인**
뿐이다. 그 외에는 묻지 말고 진행해라.

## 처음 한 번

```bash
scripts/setup.sh          # 도구·권한·창 상태 점검 → 방 검색 → rooms.json 생성
```

설정과 산출물은 전부 `$KAKAO_HOME`(기본 `./.kakao/`)에 모인다.
프로젝트마다 다른 방을 쓰려면 그 디렉토리에서 실행하고, 한 곳에 모으려면 `export KAKAO_HOME=~/.kakao`.

## 명령

```bash
scripts/krooms.sh                     # 등록된 방
scripts/krooms.sh --find 우리팀        # 새 방 찾기 (오픈채팅·그룹방 양쪽)
scripts/krooms.sh --default bang      # 기본 방 변경
scripts/kfind.sh 우리팀                # 방·친구 조회 — 어느 방인지 확실치 않으면 먼저 이걸
scripts/kfind.sh --friends 철수        # 친구만 (대화명·userId·1:1 방 유무)

scripts/kpoll.sh                      # 기본 방 폴링 (10초)
scripts/kpoll.sh ham bang             # 여러 방 동시
scripts/kpoll.sh all --replay 5       # 전부 + 시작 시 최근 5개
scripts/kpoll.sh --resume all         # 끊긴 지점부터 (그 사이 메시지 복구)

scripts/ksend.sh "메시지"              # 기본 방
scripts/ksend.sh -r bang "메시지"      # 방 지정
scripts/kimg.sh -r bang 사진.jpg
scripts/kvid.sh -r bang 영상.mp4              # 동영상·오디오·임의 파일
scripts/kvid.sh -r bang -n cut-03 영상.mp4     # 보낼 이름 지정 (케밥케이스)
scripts/kvid.sh --what cut-03                 # 그 이름이 어느 원본이었나

scripts/kget.sh --list                # 첨부 목록만
scripts/kget.sh -r ham --days 30      # 사진·동영상·파일 원본 다운로드
scripts/kget.sh --kind video

scripts/klog.sh tail                  # 무슨 일이 있었나
scripts/klog.sh stat                  # 성공률·소요·AX 비용
scripts/kb_rollup.sh                  # 대화를 markdown 으로
```

폴링은 **Monitor 도구로 `persistent: true`** 로 띄운다. 각 줄이 이벤트가 된다.

```
[카톡/ham] 김감독: 이 컷 각도가 이상한데
[카톡/ham] 김감독: 이게 낫다  ↩︎(cut-03.mp4)
```

`↩︎(…)` 는 **답장(인용)** 이고 괄호 안이 그 대상이다. 파일 여러 개를 보낸 뒤 "이게 낫다" 만
오면 무엇을 가리키는지 알 수 없다 — 이 표시로 짚어라. 되묻지 마라.

## 방에서 지킬 것

이건 실제 단톡방에서 부딪히며 배운 것이다. 지키지 않으면 사람들이 불편해한다.

- **🤖 접두사를 뗄 생각을 하지 마라.** `ksend.sh` 가 자동으로 붙인다.
  메시지는 **사용자 계정으로** 나간다. 표시가 없으면 사람이 쓴 것과 구분되지 않는다.
- **부를 때만 나와라.** 호명이나 질문이 있을 때만 답한다.
  작업 얘기라서 도움이 되겠다 싶어 끼어드는 것도 과하다 — 실제로 그렇게 지적받았다.
- **사람 많은 방에서는 3~4줄씩 끊고 반응을 본다.** 한 번에 쏟으면 도배로 보인다.
- **한 메시지는 한 생각까지.** 개행이 전송키라 줄바꿈이 없다 — 길면 그대로 벽이 된다.
  `ksend.sh` 가 100자를 넘으면 경고한다. 경고가 뜨면 끊어라.
- **처음 들어갈 때는 사용자가 먼저 상황을 설명하게 한다.** 불쑥 봇이 말하면 놀란다.
- **개인정보를 묻는 말은 거절한다.** 남의 계정을 빌려 쓰는 처지다.
- 사람 이름은 **방에 보이는 이름**으로 부른다. 실명이 아니다(아래 함정 참고).

## 함정 — 전부 실측으로 확인한 것

### `kakaocli send` 는 쓰지 마라
업스트림 이슈 #9 로 전송이 멈춘다. 이름을 못 찾으면 **exit 0 으로 조용히 끝난다**(메시지는 안 간다).
`--dry-run` 은 이름 확인 없이 통과하므로 동작 확인 수단이 아니다. **보내기는 kmsg 로만.**

### `kmsg send --dry-run` 도 확인 수단이 아니다
AX 를 전혀 건드리지 않고 4줄 찍고 끝난다. 전송 경로가 살아 있는지 보려면
**사람 적은 방에 실제로 한 줄 보내는 수밖에 없다.**

### 카카오톡 창을 닫으면 전송이 통째로 막힌다
접근성 트리가 창을 0개로 보고한다. 메인 창은 열어둬야 한다.
'친구' 탭에 있으면 방 이름 검색이 실패한다 — `kfocus.sh` 가 '채팅' 탭으로 되돌린다.

### 방을 이름으로 짚을 때 — **부분일치라 엉뚱한 방으로 간다**
`kmsg` 도 `kakaocli` 도 정확일치가 없다. 조각이 두 방에 걸리면 그중 하나로 나가고
**되돌릴 수 없다.** 그래서 순서가 정해져 있다.

1. 방이 확실치 않으면 **먼저 `scripts/kfind.sh <조각>`** — 걸리는 방을 전부 펼쳐 준다.
   `⚠ N 곳에 걸린다` 가 뜨면 그 조각으로 보내지 마라.
2. 전송 래퍼(`ksend`·`kimg`·`kvid`)는 보내기 직전에 DB 로 한 번 더 세고,
   하나가 아니면 **멈춘다**(`klib.sh` 의 `kroom_verify`).
3. 막혔으면 푸는 방법은 하나다 — **`rooms.json` 의 `search` 를 더 좁은 조각으로 고친다.**
   `KROOM_SKIP_VERIFY=1` 로 끄지 마라. 끄면 `room verify.skipped` 가 로그에 남는다.

방 이름은 세 군데(`NTChatRoom.chatName` / `NTOpenLink.linkName` / `NTChatMeta` type=3)에
나뉘어 있고 첫 번째는 대개 비어 있다. **1:1 방은 이름이 아예 없어** 이름으로는 못 고른다 —
`kfind.sh --friends` 로 `userId`·`directChatId` 를 보고 짚어라.

### 답장은 본문에 대상이 없다
카톡 답장(인용)의 대상은 `NTChatMessage.attachment` JSON 의 `src_message` 에 있다
(`referer` 컬럼은 0 이라 쓸모없다). `kpoll.py` 가 `↩︎(대상)` 으로 붙여 준다.

### `nickName` 은 대화명이 아니다
일반 그룹방에서 `NTUser.nickName` 은 **주소록에 저장된 이름(실명)** 이 나온다.
방에 보이는 건 `displayName`. 실명으로 불러 사고 낸 적 있다.
게다가 한 userId 에 멀티프로필 행이 여러 개라 그냥 JOIN 하면 **메시지가 중복된다** —
`LIMIT 1` 서브쿼리로 뽑아야 한다.

### 폴링은 시간 커서로 해야 한다
"최신 N개를 떠서 logId 가 큰 것만" 은 세 가지로 메시지를 놓친다.
1. 사이에 N개 넘게 오면 밀려난 건 영영 안 온다
2. **logId 는 단조증가가 아니다** — 순서가 역전된 메시지가 영구 유실된다
3. `sentAt` 은 초 단위라 같은 초에 2~3건이 들어간다

`kpoll.py` 는 `sentAt` 커서로 **5초 겹치게** 읽고 `logId` 로 중복을 지우며,
한 번에 `LIMIT` 이 차면 커서를 당겨 즉시 다시 읽는다. 유실 0·중복 0 으로 검증했다.

### 내 메아리는 계정이 아니라 🤖 로 거른다
메시지가 **사용자 계정으로** 나가므로 `authorId <> me` 로 자기 메아리를 막고 싶어진다.
그러면 **그 계정 주인이 방에서 하는 말까지 통째로 안 보인다.** 실제로 계정 주인 말 7개를
35분간 못 봤고, 그중에 "야 너 내말도들어?" 가 있었다. 거를 것은 계정이 아니라 🤖 접두사다.

### 개행은 전송키다
메시지에 개행이 있으면 카톡 UI 가 전송으로 처리해 쪼개진다. `ksend.sh` 가 공백으로 바꾼다.

### 동영상은 `kmsg` 로 못 보낸다 — 붙여넣기로 넣는다
`kmsg` 에는 `send-image` 뿐이라 mp4 를 주면 NSImage 로 열려다 죽는다.
`kvid.sh` 는 NSPasteboard 에 파일 URL 을 올리고 편집 메뉴의 Paste 를 AX 로 클릭한다.
AppleScript 의 `set the clipboard to POSIX file` 은 카톡이 안 받고, `set frontmost to true`
만으로는 키 입력이 닿지 않는다(`activate` 가 필요하다).
**성공 판정은 화면이 아니라 DB 로 한다** — 마지막 메시지의 **id** 가 바뀌었는지 본다.

### 첨부는 인증 없이 받아진다
주소가 `NTChatMessage.attachment` JSON 안에 있고 서명이 이미 박혀 있다.
`expire` 는 **밀리초** epoch(URL 의 `expires` 는 초). 지난 건 걸러서 "만료"로 보고한다.

## 무엇이 잘못됐는지 보려면

도구들은 **조용히 실패하는 전력**이 있다. 그래서 전부 로그를 남긴다.

```bash
scripts/klog.sh stat
```

`send.ok/retry/fail`(소요·시도횟수), `ae.focus`(카톡 창 개수·AX 버튼 수·순수 Apple Event 왕복),
`--trace-ax` 에서 뽑은 캐시 히트 여부, 폴링 `tick`·`drain`·`query.fail` 이 한 타임라인에 쌓인다.
1회 성공률이 낮으면 창 유지가 안 듣는 것이고, `drain.abort` 가 반복되면 `KPOLL_LIMIT` 을 올린다.

## 설치와 의존성

`README.md` 참고. 요약하면 `kakaocli` + `kmsg` + macOS 권한 2개 + 카카오톡 로그인.
