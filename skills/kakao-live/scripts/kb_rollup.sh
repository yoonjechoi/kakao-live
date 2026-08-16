#!/bin/bash
# 로그의 대화를 kb/raw/kakao/ 로 롤업. 실체는 kb_rollup.py
#   tools/kb_rollup.sh [YYYY-MM-DD]
exec python3 "$(cd "$(dirname "$0")" && pwd)/kb_rollup.py" "$@"
