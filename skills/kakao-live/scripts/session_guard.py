#!/usr/bin/env python3
"""화면 잠금 확인 — kmsg 로 보내기 전에 부른다.

  python3 session_guard.py      exit 0 = 풀려 있다 / 1 = 잠겼다 / 2 = 모른다

화면이 잠기면 kmsg 는 카톡 창을 못 만진다(README 「창이 0개면 전송이 통째로 막힌다」).
그 상태로 보내면 실패하거나, 입력이 반쯤 들어간 채 결과를 모르게 된다. 그래서 먼저 본다.

`ioreg -a` 의 최상위 모양이 기기마다 다르다. 배열로 오기도 하고(문서 예시),
**사전으로 오기도 한다**(햄로그 맥미니 실측, 2026-10-18). 둘 다 받는다.
"""
import os
import plistlib
import subprocess
import sys

UNLOCKED, LOCKED, UNKNOWN = 0, 1, 2


def console_users(raw):
    data = plistlib.loads(raw)
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        raise ValueError("unexpected ioreg shape")
    return data.get("IOConsoleUsers") or []


def state(raw=None, uid=None):
    """(코드, 이유) 를 돌려준다. 확인 못 하면 UNKNOWN 이지 UNLOCKED 가 아니다."""
    uid = os.getuid() if uid is None else uid
    try:
        if raw is None:
            raw = subprocess.run(
                ["/usr/sbin/ioreg", "-n", "Root", "-d1", "-a"],
                capture_output=True, timeout=10, check=True,
            ).stdout
        users = console_users(raw)
    except Exception as e:  # noqa: BLE001 — 무엇이든 모르면 UNKNOWN
        return UNKNOWN, "ioreg: " + type(e).__name__
    mine = [u for u in users if u.get("kCGSSessionUserIDKey") == uid]
    if not mine:
        return UNKNOWN, "no console session for uid %d" % uid
    on_console = [u for u in mine if u.get("kCGSSessionOnConsoleKey")]
    if not on_console:
        return LOCKED, "session not on console (user switched away)"
    if any(u.get("CGSSessionScreenIsLocked") for u in on_console):
        return LOCKED, "screen locked"
    if not any(u.get("kCGSessionLoginDoneKey") for u in on_console):
        return UNKNOWN, "login not finished"
    return UNLOCKED, "unlocked"


def unlocked():
    return state()[0] == UNLOCKED


if __name__ == "__main__":
    code, why = state()
    if code != UNLOCKED:
        print(why, file=sys.stderr)
    sys.exit(code)
