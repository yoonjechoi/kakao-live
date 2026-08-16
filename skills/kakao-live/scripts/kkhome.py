#!/usr/bin/env python3
"""작업 공간 위치를 한 곳에서 정한다. 모든 스크립트가 여기를 거친다.

  $KAKAO_HOME 이 있으면 그 경로, 없으면 현재 디렉토리의 .kakao/

  <KAKAO_HOME>/
    rooms.json        방 레지스트리 (setup.sh 가 만든다)
    logs/YYYY-MM-DD.jsonl
    logs/.kpoll-cursor.json
    files/<방>/<날짜>/...   내려받은 첨부
    chat/YYYY-MM-DD.md      대화 롤업

프로젝트마다 다른 방을 쓰고 싶으면 프로젝트 디렉토리에서 실행하면 된다.
한 곳에 모으고 싶으면 export KAKAO_HOME=~/.kakao 를 쓴다.
"""
import os

def home():
    p = os.environ.get("KAKAO_HOME") or os.path.join(os.getcwd(), ".kakao")
    return os.path.abspath(p)

def sub(*parts):
    return os.path.join(home(), *parts)

def ensure(*parts):
    d = sub(*parts)
    os.makedirs(d, exist_ok=True)
    return d


# 셸 스크립트도 같은 답을 얻어야 한다. 없으면 각자 ../logs 같은 상대경로를 새로 지어내고,
# 그 순간 $KAKAO_HOME 이 한 곳에서 정해진다는 약속이 깨진다.
#   kkhome.py home            → <KAKAO_HOME>
#   kkhome.py sub logs a.tsv  → <KAKAO_HOME>/logs/a.tsv
#   kkhome.py ensure files    → 만들고 나서 경로를 찍는다
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "home"
    fn = {"home": lambda *a: home(), "sub": sub, "ensure": ensure}.get(cmd)
    if fn is None:
        sys.exit("kkhome.py [home|sub|ensure] [parts...]")
    print(fn(*sys.argv[2:]))
