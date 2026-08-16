#!/bin/bash
# 도구 로그 조회 — 실체는 klog.py, 로그는 logs/YYYY-MM-DD.jsonl
#   klog.sh tail [날짜] [-n 40]   사람이 읽는 형식
#   klog.sh stat [날짜]           성공률·소요·재시도·Apple Event 비용
#   klog.sh grep <키워드> [날짜]
#   klog.sh raw  [날짜]           원본 jsonl (jq 로 넘길 때)
exec python3 "$(cd "$(dirname "$0")" && pwd)/klog.py" "${@:-tail}"
