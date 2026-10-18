# 햄봇 — 늘 켜 둔 맥에서 도는 자동응답 예제

1인 오픈채팅 「햄봇테스트」에 **「햄봇 안녕」** 이 오면 🤖 인사를 한 번 보낸다.
햄로그 님 맥미니에서 Codex 가 세우고 실제로 돌려 본 구성이다(2026-10-18).
작은 봇이지만 **같은 답을 두 번 보내지 않는 것**과 **꺼져도 저절로 다시 서는 것**은 그대로 가져다 쓸 수 있다.

```
LaunchAgent ── ham_bot.py (10초마다) ── kakaocli query ──▶ 카톡 DB (읽기)
                    │
                    └─ KSEND_NO_RETRY=1 ksend.sh ──▶ kmsg ──▶ 카톡 창 (보내기)
```

## 같은 답을 두 번 보내지 않는다

처리 상태를 `<KAKAO_HOME>/ham.sqlite` 에 남긴다. 보내기 **전에** `sending` 을 먼저 적는다.

| 상태 | 뜻 | 다음 |
|---|---|---|
| `pending` | 받았고 아직 안 보냈다 | 화면이 풀리면 보낸다 |
| `sending` | 보내는 중 | 이 상태로 죽으면 다시 뜰 때 `uncertain` |
| `replied` | DB 에서 🤖 답을 찾았다 | 끝 |
| `uncertain` | 나갔는지 모른다 | **다시 보내지 않는다.** 사람이 DB 를 보고 닫는다 |
| `expired` | 5분 안에 못 보냈다 | 답하지 않는다 |

`ksend.sh` 의 끝 코드로 나눈다(`KSEND_NO_RETRY=1`, 저장소 README 「보냈는지 모를 때는 다시 보내지 마라」).

- **1** = 보내기 전에 멈췄다(방 검증 · 화면 잠금). 아무것도 안 갔으니 `pending` 으로 두고 다음 바퀴에 다시.
- **0 · 2** = 나갔을 수 있다. DB 를 15초 동안 다시 보며 🤖 본문을 찾는다. 없으면 `uncertain`.

본문 비교는 정규화해서 한다(NFC, 이모지 변형 문자 `U+FE0F` 제거, 공백 정리).
첫 실기에서 답은 갔는데 DB 대조가 빗나가 `uncertain` 으로 남은 일이 있었다 — 그때는 보낸 직후 DB 를 한 번만 봤다.

### 카톡 DB 는 새 메시지를 `-wal` 에 먼저 쓴다
방금 오간 메시지는 본 DB 파일보다 옆의 `<DB>-wal` 에 먼저 들어간다. **원래 경로를 읽기 전용으로 열면**
(kakaocli 가 이렇게 한다) SQLite 가 `-wal` 까지 읽어서 최신이 보인다. DB 를 다른 곳에 **복사해서** 읽으면
`-wal` 에 있던 최근 메시지가 빠진다 — 복사하려면 `-wal` · `-shm` 을 같이 옮긴다. 실측으로는 보낸 뒤 약 1초에 DB 에서 보였다.

## 꺼져도 다시 선다 — LaunchAgent

- `com.example.hambot.plist` — 봇. `KeepAlive` 라 죽으면 10초 안에 다시 띄운다.
  실측: 강제 종료 뒤 15초 안에 새 PID 와 heartbeat 갱신.
- `com.example.hambot-awake.plist` — `caffeinate -d -i -s` 로 잠자기를 막는다.

```bash
cp com.example.hambot*.plist ~/Library/LaunchAgents/      # 경로를 자기 위치로 고친 뒤
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.hambot.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.hambot-awake.plist
launchctl print gui/$(id -u)/com.example.hambot | grep -E 'state|pid'
```

> **등록은 사람이 터미널에서 한다.** 에이전트 실행 환경(샌드박스)에서는 `launchctl bootstrap` 이 거절된다(실측).

### 설치 위치는 `~/Documents` 밖에
LaunchAgent 가 띄운 프로세스는 문서 · 데스크톱 · 다운로드 폴더를 macOS 권한(TCC) 때문에 못 읽는다.
스크립트를 `~/Documents` 아래 두면 등록은 되는데 바로 죽는다. 햄봇은 `/Users/Shared/HamBot`(권한 700)에 둔다.

### 권한은 **실제로 도는 프로그램**에 준다
터미널에서 돌릴 때는 터미널 앱이 기준이지만, LaunchAgent 로 돌리면 그 프로그램 자체가 기준이다.

- 전체 디스크 접근 — `kakaocli` 실행 파일
- 손쉬운 사용(최신 macOS: 「기기 제어 및 데이터 접근」) — `kmsg` 실행 파일

`swift build` 로 다시 빌드하면 서명이 바뀌어 허용이 풀린 것처럼 보인다. 한 번 둔 실행 파일은 다시 빌드하지 않는다.

## 사람이 해 둘 것

- 시스템 설정 → 에너지: 「디스플레이가 꺼져 있을 때 자동으로 잠자기 방지」 · 「정전 후 자동으로 시동」 켬
- 시스템 설정 → 잠금 화면: 화면 보호기 · 디스플레이 끄기 「안 함」, 암호 요구 「안 함」
- **FileVault 가 켜져 있으면** 재시동 뒤 사람이 한 번 로그인해야 봇이 선다(디스크 잠금을 풀기 전에는 화면 세션이 없다).
  FileVault 를 끄라는 뜻이 아니다 — 재시동 뒤 로그인 한 번이 필요하다는 것만 알고 쓴다.

## 시험

```bash
python3 -m unittest discover -s examples/ham-bot -v     # 카톡 없이 돈다
```

실기에서 볼 것: 받은 시각 · 답한 시각 · `replied` 판정, 화면에 🤖 이 **한 번만** 왔는지,
강제 종료 뒤 다시 서는 시간. 실제 잠자기 복귀와 재시동은 아직 확인 전이다.

## 맥미니 검토 보강

- 기존 배포판과 동일한 `runtime.lock`을 사용하므로 두 버전을 같은 KAKAO_HOME으로 동시에 실행하지 않는다. 교체 전 기존 서비스를 중지하고, 프로세스가 하나인지 확인한다.
- 확인 본문이 여러 건이면 성공으로 닫지 않고 uncertain 및 duplicate_seen으로 남긴다. 자동 재전송은 하지 않는다.
- 읽은 행의 ID를 짧은 겹침 구간 동안 보존해, 같은 초의 500행 페이지가 반복되어 다음 인사를 못 읽는 문제를 막는다.
- 이 PR 파일 자체의 실기 전환은 아직 하지 않았다. 현재 가동 중인 배포판은 유지한다.


### 명시적으로 허용한 1:1 방 추가

`ham_bot_rooms.py`는 기존 테스트방과 설정한 1:1 방을 한 프로세스에서 순서대로 처리합니다. `HAM_BOT_DIRECT_ROOMS`에 `[{"alias":"friend","name":"상대 표시 이름","chatId":123456789}]` 형태의 JSON을 지정합니다. 실제 방 ID는 로컬에만 보관하세요. 이름과 방 ID가 정확히 일치하고 멤버가 2명일 때만 처리하며, ksend의 kroom_verify도 유지합니다. 각 추가 방은 KAKAO_HOME/direct-rooms/별칭 아래 별도 커서와 상태를 보관하므로 기존 테스트방 이벤트가 다른 방으로 전달되지 않습니다. 최초 시작 이전 인사는 가져오지 않습니다. 기존 단일 방 런타임을 중지한 뒤 같은 KAKAO_HOME/runtime.lock을 쓰는 이 실행 파일로 전환하세요.
