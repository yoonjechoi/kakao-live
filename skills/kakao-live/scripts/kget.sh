#!/bin/bash
# 카톡 첨부(사진·동영상·파일) 다운로드. 실체는 kget.py, 방은 rooms.json
#   tools/kget.sh --list              무엇이 있는지 먼저 본다
#   tools/kget.sh -r work --days 30
#   tools/kget.sh -r notice --kind video
exec python3 "$(cd "$(dirname "$0")" && pwd)/kget.py" "$@"
