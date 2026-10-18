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
