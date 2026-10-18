# 보수적 전송 모드

`KSEND_NO_RETRY=1 ./ksend.sh -r test "메시지"`는 UI 전송을 한 번만 시도한다.
기본 재시도 동작은 유지한다. 🤖 머리말과 kroom_verify도 유지한다.

화면 잠금·세션 확인 실패 또는 방 검증 실패는 입력 전에 exit 1로 차단한다.
보수 모드에서 UI 시도 후 성공을 확인할 수 없으면 exit 2와 send.uncertain을
기록한다. 이 경우에는 다시 보내지 말고 원본 DB를 읽어 대조해야 한다.
성공 출력만으로 최종 전달을 단정하지 않는다.

session_guard는 ioreg의 사전·배열 출력을 모두 처리하며 잠긴 화면과 상태 불명은
차단한다. 검증: `python3 -m unittest discover -s skills/kakao-live/scripts -p 'test_send_safety.py'`.
