#!/bin/bash
# 다중 방 폴링 래퍼 — 실체는 kpoll.py, 방 목록은 rooms.json.
#   tools/kpoll.sh              기본 방
#   tools/kpoll.sh notice work     여러 방 동시
#   tools/kpoll.sh all          전부
exec python3 "$(cd "$(dirname "$0")" && pwd)/kpoll.py" "$@"
