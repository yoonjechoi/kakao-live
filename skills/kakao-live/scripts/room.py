#!/usr/bin/env python3
"""tools/rooms.json 조회 헬퍼 — bash 래퍼들이 방 정보를 꺼내 쓰는 통로.

  room.py get <별칭> <필드>   # chatId | search | label | note  (별칭 생략/'-' 이면 기본 방)
  room.py resolve <별칭...>   # 별칭 정규화. 'all' 이면 전부. 인자 없으면 기본 방
  room.py list                # 사람이 읽는 목록
  room.py me                  # 내 userId
  room.py set-default <별칭>  # 기본 방 변경
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kkhome

CONF = kkhome.sub("rooms.json")


def load():
    if not os.path.exists(CONF):
        die("방 설정이 없다: %s\n먼저 setup.sh 를 실행해라." % CONF)
    with open(CONF, encoding="utf-8") as f:
        return json.load(f)


def die(msg):
    print("room.py: %s" % msg, file=sys.stderr)
    sys.exit(1)


def pick(d, alias):
    """별칭 하나를 방 dict 로. 빈 값/'-' 는 기본 방."""
    if not alias or alias == "-":
        alias = d["default"]
    if alias not in d["rooms"]:
        die("모르는 방 '%s' — 아는 방: %s" % (alias, ", ".join(d["rooms"])))
    return alias, d["rooms"][alias]


def main(argv):
    if not argv:
        die(__doc__)
    d, cmd = load(), argv[0]

    if cmd == "get":
        alias, room = pick(d, argv[1] if len(argv) > 1 else None)
        field = argv[2] if len(argv) > 2 else "chatId"
        if field == "alias":
            print(alias)
        elif field in room:
            print(room[field])
        else:
            die("'%s' 에 '%s' 필드가 없다" % (alias, field))

    elif cmd == "resolve":
        want = argv[1:]
        if not want:
            want = [d["default"]]
        if "all" in want:
            want = list(d["rooms"])
        seen = []
        for a in want:
            alias, _ = pick(d, a)
            if alias not in seen:
                seen.append(alias)
        print(" ".join(seen))

    elif cmd == "list":
        for alias, r in d["rooms"].items():
            star = " *기본" if alias == d["default"] else ""
            print("%-6s %-20d %-16s %s%s" % (alias, r["chatId"], r["search"], r["label"], star))
            if r.get("note"):
                print("%-6s %s" % ("", r["note"]))

    elif cmd == "me":
        print(d["me"])

    elif cmd == "path":
        print(CONF)

    elif cmd == "set-default":
        alias, _ = pick(d, argv[1] if len(argv) > 1 else None)
        d["default"] = alias
        with open(CONF, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("기본 방 → %s (%s)" % (alias, d["rooms"][alias]["label"]))

    else:
        die("모르는 명령 '%s'\n%s" % (cmd, __doc__))


if __name__ == "__main__":
    main(sys.argv[1:])
