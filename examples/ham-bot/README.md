# 햄봇 인사 응답 런타임

`KAKAO_HOME`을 지정하고 `examples/ham-bot/ham_bot_runtime.py`를 실행한다. PATH에
kakaocli(PR #20 포함), kmsg, python3가 있어야 한다. 실제 실행 프로그램에 전체
디스크 접근 및 기기 제어(접근성) 권한이 필요하다.

10초마다 DB를 읽고 정확히 `햄봇 안녕`에만 답한다. 처음 설치할 때 이전 대화는
답하지 않는다. `햄봇테스트` 오픈채팅이 정확히 한 개이고 참여자가 한 명이어야
한다. 전송 직전에 이 조건을 다시 확인하며 ksend.sh의 kroom_verify도 유지한다.

커서와 처리 상태는 `KAKAO_HOME/ham.sqlite`에 저장한다. 전송 전에 `sending`을
커밋하고 DB에서 본문을 확인해야 `replied`로 기록한다. 결과가 불명확하거나
프로세스가 죽으면 `uncertain`이며 재전송하지 않는다. 잠금·세션 확인 실패는
전송 전에 차단한다. 아직 시도하지 않은 인사는 최대 5분 기다린다. 파일 잠금으로
프로세스 중복 실행을 차단한다.

햄봇은 KSEND_NO_RETRY=1로 ksend.sh의 UI 전송을 한 번만 시도한다.
기본 동작은 기존 재시도를 유지한다. KAKAO_HOME은 햄봇 전용 폴더를 쓴다. 실패하면 exit 2와 `send.uncertain`을
기록한다. 방 검증·잠금 차단은 exit 1이다. 성공 출력도 실제 DB와 대조해야 한다.

자동 실행은 Aqua 사용자 세션의 LaunchAgent에서 고정된 Python 및 스크립트의
절대 경로로 실행하고 RunAtLoad, KeepAlive, ThrottleInterval을 설정한다.
별도 KeepAlive 서비스에서 `/usr/bin/caffeinate -d -i -s`로 잠자기를 막는다.
launchctl 등록 성공, heartbeat 갱신, 강제 프로세스 종료 후 복구 및 실제
잠자기/재부팅을 검증해야 한다. plist 생성만으로 자동 실행이 등록되지는 않는다.

FileVault가 켜져 있으면 완전 재부팅 후 사람이 디스크를 잠금 해제하기 전에는
GUI 봇이 실행되지 않는다. caffeinate는 이미 걸린 화면 잠금을 풀지 않는다.
비밀번호를 수집하거나 저장하지 않는다.

검증: `python3 -m unittest discover -s examples/ham-bot -v`

실행 경로는 KAKAO_LIVE_SCRIPTS로 지정하거나 저장소의 skills/kakao-live/scripts를 사용한다.
LaunchAgent 견본의 REPO_ROOT, STATE_DIR, BIN_DIR는 설치할 절대 경로로 교체한다.
Documents 폴더의 TCC 제한을 피하려면 전용 설치 폴더를 쓰고, 실행 바이너리에 권한을 부여한다.
state 디렉터리는 700, 계정 설정 파일은 600으로 보호하고 Git에 포함하지 않는다.

실기 확인: 인사 수신 후 7초 뒤 자동응답 및 DB replied, SIGTERM 종료 후 15초 확인 시
새 PID 및 heartbeat 갱신. 최초 uncertain 1건은 원본 DB에서 정확·정규화 대조 모두
0건으로 확인했으며 재전송하지 않았다. 실제 재부팅과 잠자기 복귀는 미검증이다.
정전이나 완전 재부팅 뒤에는 FileVault 잠금 해제를 위해 사용자가 한 번 로그인해야 한다.
