#!/usr/bin/env python3
"""카톡 방의 첨부(사진·동영상·파일)를 원본 그대로 내려받는다.

  tools/kget.sh                       기본 방, 최근 7일
  tools/kget.sh -r bang --days 30
  tools/kget.sh -r ham --limit 20 --kind image
  tools/kget.sh --list                받지 않고 목록만 (무엇이 있는지 먼저 본다)

저장 위치:  $KAKAO_HOME/files/<방별칭>/<YYYY-MM-DD>/HHMMSS_<보낸사람>_<파일명>

--- 알아낸 것 (2026-08-15 실측) ---
첨부의 실제 주소는 `NTChatMessage.attachment` JSON 안에 있고, **인증 없이 그냥 받아진다.**
서명(credential+expires)이 URL에 이미 박혀 있어 curl 한 번이면 원본 화질이 온다.
받은 바이트 수가 JSON 의 `s` 값과 정확히 일치하는지로 검증한다.

메시지 type 별로 필드가 다르다.
  2  사진      url                    (s=바이트, mt=mime, w/h)
  3  동영상    urlh(고화질) > url      (sh/s=바이트, d=초)
  27 다중이미지 imageUrls[]            (sl[]=바이트 배열)
  18 파일      url + name(원본이름)    (s=바이트)
  12/20 이모티콘, 71 링크공유 → 첨부가 아니다. 건너뛴다.

`expire` 는 **밀리초** epoch 다(URL 쿼리의 expires 는 초). 지난 것은 서버가 거부하므로
받기 전에 걸러내고 "만료"로 보고한다 — 조용히 실패하지 않게.

`localFilePath` 는 **내가 보낸 것**에만 로컬 원본 경로가 들어 있다. 받은 것에는 비어 있다.
"""
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import room as roomlib  # noqa: E402
import klog             # noqa: E402
import kkhome           # noqa: E402

KINDS = {2: "image", 3: "video", 27: "image", 18: "file"}
SKIP = {12, 20, 71, 0, 1, 26, 16385}   # 이모티콘·링크공유·텍스트·피드


def q(sql):
    p = subprocess.run(["kakaocli", "query", sql], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        sys.exit("kakaocli 실패: %s" % (p.stderr or "").strip())
    return json.loads(p.stdout) if p.stdout.strip() else []


def safe(name, fallback):
    name = re.sub(r'[/\x00-\x1f]', "_", (name or "").strip()) or fallback
    return name[:120]


def items_of(mtype, att, msg_id):
    """(url, 바이트, 파일명) 리스트로 펴준다."""
    out = []
    if mtype == 2:
        u = att.get("url")
        if u:
            ext = (att.get("mt", "image/jpeg").split("/")[-1] or "jpg").replace("jpeg", "jpg")
            out.append((u, att.get("s"), "%s.%s" % (msg_id, ext)))
    elif mtype == 3:
        u = att.get("urlh") or att.get("url")
        if u:
            out.append((u, att.get("sh") if att.get("urlh") else att.get("s"), "%s.mp4" % msg_id))
    elif mtype == 27:
        urls = att.get("imageUrls") or []
        sizes = att.get("sl") or []
        mts = att.get("mtl") or []
        for i, u in enumerate(urls):
            ext = (mts[i].split("/")[-1] if i < len(mts) else "jpg").replace("jpeg", "jpg")
            out.append((u, sizes[i] if i < len(sizes) else None, "%s_%d.%s" % (msg_id, i + 1, ext)))
    elif mtype == 18:
        u = att.get("url")
        if u:
            out.append((u, att.get("s") or att.get("size"), safe(att.get("name"), "%s.bin" % msg_id)))
    return out


def fetch(url, dest, expect):
    p = subprocess.run(["curl", "-sS", "-L", "--max-time", "300", "-o", dest, "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    code = (p.stdout or "").strip()
    if code != "200":
        if os.path.exists(dest):
            os.remove(dest)
        return False, "HTTP %s" % code
    got = os.path.getsize(dest)
    if expect and got != expect:
        return False, "크기 불일치 %d≠%d" % (got, expect)
    return True, got


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("-r", "--room", default=os.environ.get("KROOM", "-"))
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--kind", choices=["all", "image", "video", "file"], default="all")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args(argv)
    if a.help:
        print(__doc__); return 0

    conf = roomlib.load()
    alias, room = roomlib.pick(conf, a.room)
    since = time.time() - a.days * 86400

    me = conf["me"]
    rows = q("""SELECT m.logId, m.type, m.attachment, m.sentAt, m.authorId,
                  COALESCE((SELECT NULLIF(u.displayName,'') FROM NTUser u
                            WHERE u.userId=m.authorId AND NULLIF(u.displayName,'') IS NOT NULL LIMIT 1),
                           (SELECT NULLIF(u.nickName,'') FROM NTUser u
                            WHERE u.userId=m.authorId AND NULLIF(u.nickName,'') IS NOT NULL LIMIT 1),'?')
                FROM NTChatMessage m
                WHERE m.chatId=%d AND m.sentAt >= %r
                  AND m.attachment IS NOT NULL AND m.attachment NOT IN ('', '{}')
                ORDER BY m.sentAt DESC %s""" % (room["chatId"], float(since),
                                                ("LIMIT %d" % a.limit) if a.limit else ""))

    now_ms = time.time() * 1000
    plan, expired = [], 0
    for log_id, mtype, att_s, sent, author, who in rows:
        # 내 계정은 멀티프로필이라 실명이 뽑힐 수 있다. 지식베이스에 실명을 남기지 않는다.
        if author == me:
            who = "나"
        if mtype in SKIP or mtype not in KINDS:
            continue
        if a.kind != "all" and KINDS[mtype] != a.kind:
            continue
        try:
            att = json.loads(att_s)
        except Exception:
            continue
        if att.get("expire") and att["expire"] < now_ms:
            expired += 1
            continue
        day = datetime.fromtimestamp(sent).strftime("%Y-%m-%d")
        hhmmss = datetime.fromtimestamp(sent).strftime("%H%M%S")
        for url, size, fname in items_of(mtype, att, log_id):
            plan.append(dict(kind=KINDS[mtype], day=day, hhmmss=hhmmss, who=safe(who, "?"),
                             url=url, size=size, fname=fname, sent=sent))

    print("[%s] %s — 받을 수 있는 첨부 %d개%s"
          % (alias, room["label"], len(plan), "  (만료 %d개 제외)" % expired if expired else ""))
    if not plan:
        return 0

    outroot = kkhome.sub("files", alias)
    ok = skip = fail = 0
    for it in plan:
        d = os.path.join(outroot, it["day"])
        name = "%s_%s_%s" % (it["hhmmss"], it["who"], it["fname"])
        dest = os.path.join(d, name)
        mb = (it["size"] or 0) / 1048576.0
        if a.list:
            print("  %s  %-5s %7.2fMB  %s" % (it["day"], it["kind"], mb, name))
            continue
        if os.path.exists(dest) and (not it["size"] or os.path.getsize(dest) == it["size"]):
            skip += 1
            continue
        os.makedirs(d, exist_ok=True)
        good, info = fetch(it["url"], dest, it["size"])
        if good:
            ok += 1
            print("  ✓ %7.2fMB  %s" % (mb, name))
            klog.write("kget", "download.ok", room=alias, kind=it["kind"], bytes=info, file=name)
        else:
            fail += 1
            print("  ✗ %s — %s" % (name, info), file=sys.stderr)
            klog.write("kget", "download.fail", room=alias, kind=it["kind"], file=name, err=str(info))

    if not a.list:
        print("받음 %d · 건너뜀 %d · 실패 %d  →  %s" % (ok, skip, fail, outroot))
        klog.write("kget", "run", room=alias, ok=ok, skipped=skip, failed=fail, expired=expired)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
