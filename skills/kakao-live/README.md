# kakao-live — scripts

**설치·사용·함정은 저장소 최상단 [README.md](../../README.md) 에 있다** (영문: [README.en.md](../../README.en.md)).
여기에 옮겨 적지 않는다 — 두 벌이 되면 한쪽이 낡는다. 실제로 그렇게 됐다(2026-08-16).

이 문서에는 **위 문서에 없는 것**만 둔다.

## 빠른 시작

```
/kakao-live:setup
```

## 동작 원리

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
klog ── JSONL ──▶ send/recv/ae.focus/audit 한 타임라인에
```

- **폴링** — `sentAt` 을 커서로 5초 겹치게 읽고 `logId` 로 중복 제거.
  `LIMIT` 이 차면 커서를 당겨 즉시 재조회하므로 폭주해도 무손실.
  여러 방은 `chatId IN (...)` 으로 묶어 한 번에 — `kakaocli` 는 **호출당 ~790ms** 라
  방마다 부르면 방 수만큼 선형으로 늘어난다. 묶으면 방이 몇 개든 한 번이다.
- **전송** — `-k`(keep-window)로 채팅창을 유지해 매번 검색하지 않는다.
  실측 1회 성공률 100%, 중앙 1.07초. 창이 쌓이면 느려진다(2개→7개일 때 1초→7초).
- **기록** — 4계층. 래퍼 / Apple Event / kmsg 내부(`--trace-ax`) / **필터 감사**.
  마지막 것이 "조용한 게 없어서인가, 내가 안 들어서인가" 에 답한다.

## 스크립트

| 파일 | 역할 |
|---|---|
| `setup.sh` | 도구·권한 점검 → 방 검색 → `rooms.json` 생성 |
| `krooms.sh` | 방 목록 / 기본 방 변경 / 새 방 찾기(`--find`) / 설정 위치(`--path`) |
| `room.py` | `rooms.json` 조회 헬퍼. 래퍼들이 부른다 |
| `kpoll.sh` `kpoll.py` | 다중 방 폴링. 시간 커서 + 누락 대조 |
| `ksend.sh` | 메인 전송기. 창 유지·재시도·개행 치환·🤖 접두사 |
| `kimg.sh` | 이미지 전송 |
| `kfocus.sh` | 카카오톡 '채팅' 탭 강제 전환. 전송기가 내부에서 부른다 |
| `kget.sh` `kget.py` | 첨부 다운로드 (사진·동영상·파일) |
| `klog.sh` `klog.py` | 로그 조회·분석 (`tail` / `stat` / `grep` / `raw`) |
| `kb_rollup.sh` `kb_rollup.py` | 대화를 markdown 으로 |
| `klib.sh` | 공용 함수 (`run_timeout`, `now_ms`, `klog`, `-r` 파싱). source 전용 |
| `kkhome.py` | 작업 공간 위치를 한 곳에서 정한다 (`$KAKAO_HOME`, 기본 `./.kakao/`) |

**`kmsg send` 를 직접 부르지 마라.** 래퍼가 처리하는 것들이 있다 — 이유는 저장소 README 의 「함정」.

## 단독 사용

Claude Code 없이 셸에서 그대로 돈다. `scripts/` 를 통째로 가져가면 된다.

```bash
export KAKAO_HOME=~/.kakao
scripts/setup.sh
scripts/kpoll.sh --interval 10 work
```
