#!/usr/bin/env python3
"""로그의 대화를 지식베이스 raw 로 롤업한다.

받은 말은 **logId 로 DB 를 다시 조회**해서 쓴다. 로그를 그대로 믿지 않는 이유 두 가지 (2026-08-15):
 1) 옛 로그에는 발신자가 `nickName`(실명)으로 박혀 있다. 지식베이스에 실명을 넣지 않는다.
    DB 의 `displayName` 이 방에 보이는 이름이다. → kb/wiki/concepts/발신자-이름.md
 2) 로그의 `ts` 는 **수신 시각**이라, 폴러가 밀린 구간을 몰아 읽으면 전부 같은 시각으로 뭉친다.
    대화록에 필요한 건 원 발화 시각(`sentAt`)이다.
보낸 말은 로그가 정확하다(전송 시각 + 🤖 붙은 본문 그대로).

  tools/kb_rollup.sh [날짜]        기본 오늘

logs/YYYY-MM-DD.jsonl 에서 주고받은 말만 뽑아 kb/raw/kakao/YYYY-MM-DD.md 로 쓴다.
받은 말(kpoll recv)과 보낸 말(ksend send.ok)을 **시간순으로 합친다** — 한쪽만 있으면 대화가 아니다.

raw 는 무손실·자동이다. 여기서 무엇이 의미 있는지는 고르지 않는다.
고르는 일은 wiki/ 쪽에서 사람 판단으로 한다. (kb/CLAUDE.md 의 두 층 규칙)
"""
import json, os, subprocess, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kkhome  # noqa: E402


def main(argv):
    day = argv[0] if argv else datetime.now().strftime("%Y-%m-%d")
    src = kkhome.sub("logs", "%s.jsonl" % day)
    if not os.path.exists(src):
        print("로그 없음: %s" % src); return 1

    rows, dedup = [], set()
    for line in open(src, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") == "recv":
            # 폴러를 재시작하면 겹침 구간을 다시 읽어 같은 메시지가 로그에 여러 번 남는다.
            # logId 로 지운다. (logId 가 없던 옛 줄은 본문으로 지운다)
            key = r.get("log_id") or ("t", r.get("room"), r.get("sender"), r.get("text"))
            if key in dedup:
                continue
            dedup.add(key)
            rows.append((r["ts"], r.get("room", "?"), r.get("sender", "?"), r.get("text", ""), False,
                         r.get("log_id")))
        elif r.get("event") in ("send.ok",):
            # send.start 에 본문이 있다. send.ok 는 결과라 본문이 없을 수 있어 둘 다 본다
            rows.append((r["ts"], r.get("room", "?"), "나(🤖)", r.get("text", ""), True, None))
        elif r.get("event") == "send.start":
            rows.append((r["ts"], r.get("room", "?"), "나(🤖)", r.get("text", ""), True, None))

    # send.start 와 send.ok 가 같은 메시지를 두 번 넣지 않게: 본문 없는 내 발화는 버린다
    seen = set()
    merged, merged_raw = [], []
    for ts, room, who, text, mine, lid in sorted(rows):
        if mine:
            if not text or text in seen:
                continue
            seen.add(text)
        merged.append((ts, room, who, text))
        merged_raw.append((ts, room, who, text, mine, lid))

    if not merged:
        print("대화 없음: %s" % day); return 0

    # 받은 말은 DB 로 보정한다 — 대화명과 원 발화 시각
    recv_ids = [k for k in dedup if isinstance(k, int)]
    fix = {}
    if recv_ids:
        sql = """SELECT m.logId, m.sentAt,
                   COALESCE((SELECT NULLIF(u.displayName,'') FROM NTUser u
                             WHERE u.userId=m.authorId AND NULLIF(u.displayName,'') IS NOT NULL LIMIT 1),
                            (SELECT NULLIF(u.nickName,'') FROM NTUser u
                             WHERE u.userId=m.authorId AND NULLIF(u.nickName,'') IS NOT NULL LIMIT 1),
                            '?')
                 FROM NTChatMessage m WHERE m.logId IN (%s)""" % ",".join(str(i) for i in recv_ids)
        try:
            p = subprocess.run(["kakaocli", "query", sql], capture_output=True, text=True, timeout=60)
            for lid, sent, name in json.loads(p.stdout or "[]"):
                fix[int(lid)] = (float(sent), name)
        except Exception as e:
            print("DB 보정 실패(로그값 그대로 씀): %s" % e, file=sys.stderr)

    if fix:
        fixed = []
        for ts, room, who, text, mine, lid in merged_raw:
            if not mine and lid in fix:
                sent, name = fix[lid]
                ts = datetime.fromtimestamp(sent).astimezone().isoformat(timespec="seconds")
                who = name
            fixed.append((ts, room, who, text))
        merged = sorted(fixed)

    out_dir = kkhome.sub("chat")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "%s.md" % day)

    by_room = {}
    for ts, room, who, text in merged:
        by_room.setdefault(room, []).append((ts, who, text))

    with open(out, "w", encoding="utf-8") as f:
        f.write("# 카톡 대화 %s\n\n" % day)
        f.write("> `tools/kb_rollup.sh` 가 `logs/%s.jsonl` 에서 만든 것. 손대지 않는다.\n" % day)
        f.write("> 방 이름과 별칭은 `tools/rooms.json`, 사람은 `kb/wiki/people/` 참고.\n\n")
        for room, items in by_room.items():
            f.write("## [%s] %d건\n\n" % (room, len(items)))
            for ts, who, text in items:
                f.write("- `%s` **%s** — %s\n" % (ts[11:19], who, text))
            f.write("\n")

    print("%s  (%d건, 방 %d개)" % (out, len(merged), len(by_room)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
