#!/usr/bin/env python3
"""tools/ 도구들의 구조화 로그 — 기록과 분석.

  logs/YYYY-MM-DD.jsonl 에 한 줄 1이벤트로 쌓는다. 도구별로 파일을 쪼개지 않는다 —
  "감독이 말했다 → 내가 답했다 → 3.2초 걸렸다" 가 한 타임라인에서 읽혀야 분석이 되기 때문이다.

  기록:  klog.py write <tool> <event> [k=v ...]        (bash 래퍼용)
  조회:  klog.py tail [날짜] [-n N]                     사람이 읽는 형식
         klog.py stat [날짜]                            성공률·소요·재시도·AE 비용
         klog.py grep <키워드> [날짜]
         klog.py raw  [날짜]                            원본 jsonl

  값은 k=v 로 넘긴다. 숫자로 보이면 숫자로, true/false 는 불린으로 저장한다.
  로깅이 도구를 죽이면 안 된다 — write 는 어떤 예외도 밖으로 내보내지 않는다.
"""
import json, os, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
import kkhome            # noqa: E402
LOGDIR = kkhome.sub("logs")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def path_for(day=None):
    return os.path.join(LOGDIR, "%s.jsonl" % (day or today()))


def coerce(v):
    if v in ("true", "false"):
        return v == "true"
    if v == "null":
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def write(tool, event, **fields):
    """이벤트 한 줄 append. 4KB 미만이라 O_APPEND 로 원자적 —
    kpoll 이 백그라운드로 도는 중에 ksend 가 끼어들어도 줄이 섞이지 않는다."""
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        rec = {"ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
               "tool": tool, "event": event}
        for k, v in fields.items():
            if v is not None and v != "":
                rec[k] = v
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        fd = os.open(path_for(), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:
        pass  # 로그가 도구를 죽이지 않는다


def read(day=None):
    p = path_for(day)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


# ---------- 조회 ----------

ICON = {"send.ok": "✓", "send.fail": "✗", "send.retry": "↻", "image.ok": "✓",
        "image.fail": "✗", "recv": "←", "query.fail": "!", "ae.focus": "◎",
        "resolve.fail": "!", "poll.start": "▶", "poll.stop": "■"}


def fmt(r):
    t = r["ts"][11:19]
    icon = ICON.get(r["event"], "·")
    room = ("[%s] " % r["room"]) if r.get("room") else ""
    tail = []
    if r.get("sender"):
        tail.append("%s:" % r["sender"])
    if r.get("text"):
        tail.append(r["text"][:100])
    for k in ("dur_ms", "attempt", "step", "err", "query_ms", "new", "windows", "buttons"):
        if k in r:
            tail.append("%s=%s" % (k, r[k]))
    return "%s %s %-14s %s%s" % (t, icon, r["event"], room, " ".join(str(x) for x in tail))


def cmd_tail(args):
    day = args[0] if args and not args[0].startswith("-") else None
    n = 40
    if "-n" in args:
        n = int(args[args.index("-n") + 1])
    for r in read(day)[-n:]:
        print(fmt(r))


def cmd_grep(args):
    kw = args[0]
    day = args[1] if len(args) > 1 else None
    for r in read(day):
        if kw in json.dumps(r, ensure_ascii=False):
            print(fmt(r))


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def summarize(vals, unit="ms"):
    if not vals:
        return "-"
    vals = sorted(vals)
    mid = vals[len(vals) // 2]
    return "n=%d 중앙%d%s 최소%d 최대%d" % (len(vals), mid, unit, vals[0], vals[-1])


def cmd_stat(args):
    day = args[0] if args else None
    rows = read(day)
    if not rows:
        print("로그 없음: %s" % path_for(day))
        return
    print("=== %s — 이벤트 %d건 ===" % (day or today(), len(rows)))

    # 전송
    ok = [r for r in rows if r["event"] in ("send.ok", "image.ok")]
    fail = [r for r in rows if r["event"] in ("send.fail", "image.fail")]
    retry = [r for r in rows if r["event"] in ("send.retry", "image.retry")]
    total = len(ok) + len(fail)
    if total:
        print("\n[전송] %d건  성공 %d (%.0f%%)  실패 %d  재시도 %d회"
              % (total, len(ok), pct(len(ok), total), len(fail), len(retry)))
        print("  소요: %s" % summarize([r["dur_ms"] for r in ok if "dur_ms" in r]))
        first = len([r for r in ok if r.get("attempt", 1) == 1])
        # 메시지가 길면 카톡에서 벽처럼 보인다. 개행을 못 쓰니 짧게 쓰는 수밖에 없다.
        # 안 재면 계속 길어진다 — 실제로 중앙 89자, 58%가 80자 초과인 채로 굴러갔다.
        lens = [r["len"] for r in ok if isinstance(r.get("len"), int)]
        if lens:
            over = sum(1 for l in lens if l > 100)
            print("  메시지 길이: %s  100자 초과 %d건 (%d%%)  ← 길면 읽기 힘들다"
                  % (summarize(lens, "자"), over, 100 * over // len(lens)))
        print("  1회에 성공: %d/%d (%.0f%%)  ← 낮으면 kfocus/창유지가 안 듣는 것"
              % (first, len(ok), pct(first, len(ok))))
        byroom = {}
        for r in ok + fail:
            byroom.setdefault(r.get("room", "?"), []).append(r["event"].endswith(".ok"))
        for room, res in byroom.items():
            print("  [%s] %d건 성공 %d" % (room, len(res), sum(res)))
        errs = {}
        for r in fail + retry:
            errs[r.get("err", "?")] = errs.get(r.get("err", "?"), 0) + 1
        if errs:
            print("  실패 유형: %s" % ", ".join("%s×%d" % kv for kv in sorted(errs.items(), key=lambda x: -x[1])))

    # Apple Event (kfocus)
    ae = [r for r in rows if r["event"] == "ae.focus"]
    if ae:
        # 스크립트가 깨진 건(-1)은 통계에서 뺀다. 대신 아래에 따로 센다.
        good = [r for r in ae if r.get("windows", -1) >= 0]
        durs = [r["dur_ms"] for r in good if "dur_ms" in r]
        # 창이 0개면 스크립트가 고정 대기 전에 빠져나온다. 그런 건을 섞으면
        # dur_ms - delay_ms 가 음수가 되어 지표가 망가진다(2026-08-16 실측 중앙 -500ms).
        acted = [r for r in good if r.get("windows", 0) > 0 and "dur_ms" in r]
        net = [r["dur_ms"] - r.get("delay_ms", 0) for r in acted]
        print("\n[Apple Event] kfocus %d회 (정상 %d)" % (len(ae), len(good)))
        print("  전체 소요: %s" % summarize(durs))
        if net:
            skipped = len(good) - len(acted)
            tail = "  (창 0개인 %d건 제외 — 고정 대기를 안 탄다)" % skipped if skipped else ""
            print("  고정 delay 뺀 순수 AE 왕복: %s%s" % (summarize(net), tail))
        steps = {}
        for r in ae:
            steps[r.get("step", "?")] = steps.get(r.get("step", "?"), 0) + 1
        print("  결과: %s" % ", ".join("%s×%d" % kv for kv in sorted(steps.items(), key=lambda x: -x[1])))
        nowin = len([r for r in ae if r.get("windows") == 0])
        if nowin:
            print("  ⚠ 카톡 창 0개였던 횟수: %d  ← 이때 전송은 통째로 막힌다" % nowin)
        bs = [r["buttons"] for r in good if r.get("buttons", -1) >= 0]
        if bs:
            print("  AX 버튼 훑은 수: %s  ← 소요와 상관되면 트리 탐색이 병목" % summarize(bs, "개"))
        broken = len(ae) - len(good)
        if broken:
            print("  ⚠ AppleScript 자체가 깨진 횟수: %d  ← 조용히 실패한다. 로그 없으면 못 본다" % broken)

    ae_step = [r for r in rows if r["event"] == "ae.step"]
    if ae_step:
        print("\n[Apple Event 단계별] (KFOCUS_TRACE=1 로 잰 것)")
        byname = {}
        for r in ae_step:
            byname.setdefault(r.get("name", "?"), []).append(r.get("dur_ms", 0))
        for name, vals in byname.items():
            print("  %-16s %s" % (name, summarize(vals)))

    # 폴링
    ticks = [r for r in rows if r["event"] == "tick"]
    qfail = [r for r in rows if r["event"] == "query.fail"]
    recv = [r for r in rows if r["event"] == "recv"]
    drain = [r for r in rows if r["event"] == "drain"]
    abort = [r for r in rows if r["event"] == "drain.abort"]
    if ticks or recv:
        print("\n[폴링] tick %d회  수신 %d건  쿼리실패 %d" % (len(ticks), len(recv), len(qfail)))
        print("  kakaocli 쿼리: %s" % summarize([r["query_ms"] for r in ticks if "query_ms" in r]))
        starts = len([r for r in rows if r["event"] == "poll.start"])
        ids = [r["log_id"] for r in recv if "log_id" in r]
        if ids:
            dup = len(ids) - len(set(ids))
            note = "" if starts <= 1 else "  (폴러가 %d번 떴다 — 재시작마다 겹침 구간을 다시 읽으므로 중복이 생긴다)" % starts
            print("  중복 수신: %d건  ← 한 프로세스 안에서 0이 아니면 dedupe 가 새는 것%s" % (dup, note))
        if drain:
            print("  drain %d라운드  ← 한 번에 LIMIT 만큼 차서 이어 읽은 횟수. 방이 폭주했다는 뜻" % len(drain))
        if abort:
            print("  ⚠ drain 중단 %d회 — 한 tick 안에 다 못 훑었다. 다음 tick 에 이어받지만"
                  " 반복되면 LIMIT 을 올릴 것" % len(abort))
        byroom = {}
        for r in recv:
            byroom[r.get("room", "?")] = byroom.get(r.get("room", "?"), 0) + 1
        for room, c in sorted(byroom.items(), key=lambda x: -x[1]):
            print("  [%s] 수신 %d건" % (room, c))

    bad = [r for r in rows if r["event"] == "resolve.fail"]
    if bad:
        print("\n[오발송 차단] %d회 — %s" % (len(bad), ", ".join(str(r.get("arg")) for r in bad)))


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "write":
        tool, event = args[0], args[1]
        fields = {}
        for kv in args[2:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                fields[k] = coerce(v)
        write(tool, event, **fields)
    elif cmd == "tail":
        cmd_tail(args)
    elif cmd == "stat":
        cmd_stat(args)
    elif cmd == "grep":
        cmd_grep(args)
    elif cmd == "raw":
        p = path_for(args[0] if args else None)
        sys.stdout.write(open(p, encoding="utf-8").read() if os.path.exists(p) else "")
    elif cmd == "path":
        print(path_for(args[0] if args else None))
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
