# kakao-live

macOS 카카오톡을 **실시간으로 읽고 답하는** 에이전트 도구 모음.
Claude Code 스킬로 쓰거나, 스크립트만 떼어 단독으로 써도 된다.

읽기는 로컬 DB, 쓰기는 접근성(AX) API. 이 분담이 핵심이다.

```
방 등록 → 10초 폴링으로 새 메시지 수신 → 판단 → 답장 → 전부 로그
```

---

## 1. 의존성

### 필수

| 도구 | 설치 | 역할 | 없으면 |
|---|---|---|---|
| **kakaocli** | `brew install silver-flight-group/tap/kakaocli` | 카톡 DB 읽기 (0.6.0) | 메시지를 못 읽는다 |
| **kmsg** | `brew install channprj/tap/kmsg` | 메시지·이미지 전송 | 못 보낸다 |
| **python3** | macOS 기본 (3.9+) | 폴링·로그·다운로드 본체 | 전부 동작 안 함 |
| **curl** | macOS 기본 | 첨부 다운로드 | 첨부만 안 됨 |
| **카카오톡 데스크톱** | 앱스토어 | 로그인 + 메인 창 열림 | 전송이 통째로 막힌다 |

### 권장

| 도구 | 설치 | 역할 | 없으면 |
|---|---|---|---|
| **coreutils** | `brew install coreutils` | `timeout` (macOS엔 없다) | perl `alarm` 으로 자동 대체 |
| **ffmpeg** | `brew install ffmpeg` | 받은 영상 다루기 | 다운로드는 됨, 후처리만 불가 |

한 줄로:

```bash
brew install silver-flight-group/tap/kakaocli channprj/tap/kmsg coreutils ffmpeg
```

### macOS 권한 2개 — 없으면 조용히 실패한다

시스템 설정 → 개인정보 보호 및 보안에서 **터미널**(또는 사용하는 터미널 앱)을 추가한다.

| 권한 | 왜 | 없을 때 증상 |
|---|---|---|
| **전체 디스크 접근** | 카톡 DB 읽기 | `kakaocli status` 부터 실패 |
| **손쉬운 사용** | UI 조작으로 전송 | 전송이 멈추거나 창을 못 찾음 |

권한을 준 뒤 **터미널을 완전히 종료했다 다시 열어야** 적용된다.

---

## 2. 설치

### Claude Code 스킬로

```bash
cp -r kakao-live ~/.claude/skills/          # 개인 스킬
# 또는 프로젝트에만:
cp -r kakao-live <프로젝트>/.claude/skills/
```

### 스크립트만 단독으로

`scripts/` 를 통째로 가져가면 된다. Claude Code 없이도 셸에서 그대로 돈다.

---

## 3. 처음 한 번

```bash
scripts/setup.sh
```

- 도구·권한·카카오톡 창 상태를 점검하고, 빠진 게 있으면 설치 명령까지 알려준다
- 방 이름 일부로 검색해 `chatId` 를 찾아준다 (오픈채팅·일반 그룹방 양쪽)
- `$KAKAO_HOME/rooms.json` 을 만든다

점검만 하려면 `scripts/setup.sh --check`, 방 검색만은 `scripts/setup.sh --find 검색어`.

### 작업 공간

모든 산출물이 `$KAKAO_HOME` 한 곳에 모인다. 기본값은 **현재 디렉토리의 `.kakao/`**.

```
.kakao/
├── rooms.json                  방 레지스트리 ← 방을 바꾸려면 여기만 고친다
├── logs/YYYY-MM-DD.jsonl       구조화 로그
├── logs/.kpoll-cursor.json     폴링 커서 (재시작 시 이어받기)
├── files/<방>/<날짜>/            내려받은 첨부
└── chat/YYYY-MM-DD.md          대화 롤업
```

여러 프로젝트에서 같은 방을 쓰려면 `export KAKAO_HOME=~/.kakao`.

### rooms.json

```json
{
  "me": 9999999,
  "default": "ham",
  "rooms": {
    "ham":  { "chatId": 222222222222222222, "search": "우리팀 공지",
              "label": "우리팀 공지방", "note": "오픈채팅 2000명" },
    "bang": { "chatId": 111111111111111, "search": "작업",
              "label": "작업방", "note": "" }
  }
}
```

| 필드 | 무엇 | 쓰는 곳 |
|---|---|---|
| `chatId` | 숫자 ID | kakaocli — DB 읽기(폴링·첨부) |
| `search` | 방 이름의 **일부** | kmsg — UI 검색창에 쳐서 방을 찾는다(전송) |
| `me` | 내 userId | 내가 보낸 메시지를 폴링에서 제외 |

성격이 다르니 헷갈리지 마라. `search` 는 **다른 방에 함께 걸리지 않는 조각**으로 고른다.
잘못 고르면 엉뚱한 방으로 간다.

> `chatId` 는 **기기마다 다를 수 있다.** 다른 컴퓨터로 옮기면 `setup.sh --find` 로 다시 확인해라.

---

## 4. 사용

```bash
# 방
scripts/krooms.sh                     # 목록
scripts/krooms.sh --find 우리팀        # 새 방 찾기
scripts/krooms.sh --default bang      # 기본 방 변경

# 받기
scripts/kpoll.sh                      # 기본 방, 10초 간격
scripts/kpoll.sh ham bang             # 여러 방 동시 (한 프로세스, 쿼리 1회)
scripts/kpoll.sh all --replay 5       # 시작할 때 최근 5개 먼저
scripts/kpoll.sh --resume all         # 끊긴 지점부터 복구
scripts/kpoll.sh --interval 5 ham

# 보내기
scripts/ksend.sh "메시지"
scripts/ksend.sh -r bang "메시지"
KROOM=bang scripts/ksend.sh "메시지"
echo "긴 내용" | scripts/ksend.sh -
scripts/kimg.sh -r bang 사진.jpg

# 첨부 받기
scripts/kget.sh --list                # 뭐가 있는지 먼저
scripts/kget.sh -r ham --days 30
scripts/kget.sh --kind video          # image | video | file | all

# 점검
scripts/klog.sh tail                  # 사람이 읽는 형식
scripts/klog.sh stat                  # 성공률·소요·AX 비용
scripts/klog.sh grep 키워드
scripts/kb_rollup.sh                  # 대화를 markdown 으로
```

폴링 출력은 한 줄에 하나다. 방 별칭이 붙는다.

```
[카톡/ham] 김감독: 이 컷 각도가 이상한데
[카톡/bang] 계정 주인: 확인해볼게요
```

Claude Code 에서는 **Monitor 도구로 `persistent: true`** 로 띄우면 각 줄이 이벤트로 들어온다.

---

## 5. 알아둘 것

### 보내기 전에

- 전송은 **사용자 계정으로** 나간다. `ksend.sh` 가 🤖 접두사를 자동으로 붙이는 이유다. 떼지 마라.
- 처음 쓰는 방이면 **사람 적은 방에서** 한 줄 보내 확인해라. 2000명 방을 테스트에 쓰지 마라.
- 어느 방으로 나가는지 stderr 에 `→ [ham] 우리팀 공지방` 으로 찍힌다. 확인해라.

### 조용히 실패하는 것들

| 증상 | 원인 | 대처 |
|---|---|---|
| 보냈는데 안 감 | `kakaocli send` 사용 (업스트림 #9) | `ksend.sh` 만 써라 |
| `--dry-run` 은 되는데 실제로 안 감 | dry-run 은 AX 를 안 건드린다 | 실제로 한 줄 보내 확인 |
| 전송이 통째로 막힘 | 카카오톡 메인 창이 닫힘 | 창을 열어라. 강제 종료하지 마라 |
| **창이 열려 있는데도 막힘** | **화면 잠금.** 잠금 화면에서 AX 는 창을 0개로 본다 | 사람이 잠금을 풀어야 한다. 읽기는 잠겨도 된다 |
| `SEARCH_MISS` | 카톡이 '친구' 탭에 있음 | `ksend.sh` 가 자동 처리 |
| 메시지가 여러 개로 쪼개짐 | 개행이 전송키 | `ksend.sh` 가 공백 치환 |
| 사람을 실명으로 부름 | `nickName` 은 주소록 이름 | `displayName` 을 쓴다 (내장) |
| 메시지가 중복 조회됨 | 멀티프로필로 JOIN 이 불어남 | `LIMIT 1` 서브쿼리 (내장) |
| 메시지를 놓침 | logId 기준 필터 | 시간 커서 + 겹침 (내장) |
| **내 계정 주인의 말만 안 들림** | `authorId <> me` 로 메아리를 막으면 계정 주인 본인의 말까지 막힌다 | 🤖 접두사로 거른다 (내장) |

문제가 생기면 먼저 `scripts/klog.sh stat` 을 봐라. 무엇이 몇 번 실패했는지 남아 있다.

### 개인정보

- 수신 메시지 **본문이 로그에 그대로 쌓인다.** 단톡방 대화가 로컬에 남는다는 뜻이다.
- 받은 첨부도 원본으로 저장된다.
- `.kakao/` 를 git 에 올리지 마라. `.gitignore` 에 넣어라.

```gitignore
.kakao/
```

---

## 6. 동작 원리

```
        ┌───────────────── 읽기 ─────────────────┐
kakaocli ── SQL ──▶ NTChatMessage + NTUser        시간 커서 + logId 중복제거
                    (sentAt 커서, 5초 겹침)       ──▶ [카톡/방] 이름: 내용
                                                       │
        ┌───────────────── 쓰기 ─────────────────┐     ▼
kmsg ── AX API ──▶ 채팅 탭 확인 → 방 검색 → 입력   ◀── 판단
       (-k 로 창 유지, 실패 시 kfocus 후 재시도)
                                                       │
        ┌───────────────── 기록 ─────────────────┐     ▼
klog ── JSONL ──▶ send/recv/ae.focus/tick 한 타임라인에
```

- **폴링**: `sentAt` 을 커서로 5초 겹치게 읽고 `logId` 로 중복 제거. `LIMIT` 이 차면 커서를 당겨 즉시 재조회.
  여러 방은 `chatId IN (...)` 으로 묶어 한 번에 — `kakaocli` 는 호출당 ~790ms 라 방마다 부르면 선형으로 늘어난다.
- **전송**: `-k`(keep-window)로 채팅창을 유지해 매번 검색하지 않는다. 실측 1회 성공률 100%, 중앙값 1.07초.
- **로그**: 래퍼 계층 / Apple Event 계층 / kmsg 내부(`--trace-ax`) 3단으로 남긴다.

---

## 7. 한계

- **macOS 전용.** 카카오톡 데스크톱 앱과 접근성 API에 의존한다.
- 카카오톡 앱이 **켜져 있고 로그인**돼 있어야 한다. 창도 열려 있어야 한다.
- 전송이 UI 자동화라 전송 중에는 카톡 창이 잠깐 앞으로 나온다.
- 카카오톡 앱 업데이트로 접근성 트리가 바뀌면 전송이 깨질 수 있다.
- 첨부 URL에는 만료가 있다. 오래된 첨부는 받을 수 없다.

## 라이선스

MIT
