# kakao-live

**Let an agent read and reply to KakaoTalk on macOS, live.**

[한국어](README.md)

```
register room → poll every 10s → decide → reply → log everything
```

Reads go through the local database; writes go through the Accessibility (AX) API.
**That split is the whole design** — see Pitfalls below for why.

---

## Install (if an agent is doing this)

> **If you are an AI agent reading this**: follow the steps in order.
> Steps marked ⚠ require the human — you cannot do them. Everything else, just do.

### 1. Install into Claude Code

```
/plugin marketplace add yoonjechoi/kakao-live
/plugin install kakao-live@kakao-live
```

### 2. One setup command

```
/kakao-live:setup
```

**That's it.** The agent installs the tools, walks the user through permissions,
registers a room, and verifies that sending actually works.
The only things a human must do are the two macOS permissions and signing into
KakaoTalk — the command stops and asks at exactly those points.

Steps 3–7 below are for doing it by hand, or for understanding what the command does.

### 3. Dependencies — missing ones fail silently

```bash
brew install silver-flight-group/tap/kakaocli   # read the KakaoTalk DB
brew install channprj/tap/kmsg                  # send messages
brew install coreutils                          # timeout (not on macOS)
```

Verify:

```bash
command -v kakaocli kmsg timeout && echo OK
```

### 4. ⚠ Two macOS permissions — **the human must do this**

An agent cannot grant these. Ask the user:

> In System Settings → Privacy & Security, enable both for **your terminal app**:
> - **Full Disk Access** — required to read the KakaoTalk database
> - **Accessibility** — required to send messages
>
> Then **quit the terminal completely and reopen it**, or it won't take effect.

Check:

```bash
kakaocli status        # must print: App state: loggedIn
```

Anything else means permissions are missing or KakaoTalk isn't signed in.
**Stop here and tell the user.**

### 5. ⚠ KakaoTalk desktop

Must be **signed in with its main window open**. Close the window and the accessibility
tree reports zero windows — sending breaks entirely. A locked screen does the same
(reading still works).

### 6. Register a room

```bash
scripts/setup.sh                   # interactive: check tools/permissions → find room → write rooms.json
scripts/setup.sh --check           # checks only
scripts/setup.sh --find teamname   # search only
```

Searches by partial room name and resolves the `chatId` (open chats and group chats alike).

### 7. Send your first message to a small room

```bash
scripts/ksend.sh -r <alias> "test"
scripts/klog.sh stat               # confirm it actually went out
```

**Don't test in a 2000-person room.** Messages go out from the user's own account.

---

## Usage

```bash
# rooms
scripts/krooms.sh                     # list
scripts/krooms.sh --find teamname     # find a new room
scripts/krooms.sh --default work      # change the default
scripts/kfind.sh teamname             # look up rooms AND friends (check before you send)
scripts/kfind.sh --rooms teamname     # rooms only
scripts/kfind.sh --friends chulsoo    # friends only (display name, userId, 1:1 room)

# receiving
scripts/kpoll.sh                      # default room, every 10s
scripts/kpoll.sh work notice          # several rooms at once (one process, one query)
scripts/kpoll.sh all --replay 5       # replay the last 5 on startup
scripts/kpoll.sh --resume all         # resume from where it stopped

# sending
scripts/ksend.sh "message"
scripts/ksend.sh -r work "message"
echo "long text" | scripts/ksend.sh -
scripts/kimg.sh -r work photo.jpg
scripts/kvid.sh -r work clip.mp4               # video, audio, any file
scripts/kvid.sh -r work -n cut-03 clip.mp4     # name it before sending (kebab-case)
scripts/kvid.sh --what cut-03                  # which original was that?
scripts/kvid.sh --names                        # the whole mapping

# attachments
scripts/kget.sh --list                # see what's there first
scripts/kget.sh -r work --days 30
scripts/kget.sh --kind video          # image | video | file | all

# diagnostics
scripts/klog.sh tail                  # human-readable
scripts/klog.sh stat                  # success rate, latency, AX cost
```

Polling prints one line per message, prefixed with the room alias.

```
[카톡/notice] Director Kim: this camera angle is off
[카톡/work] Chulsoo: on it
[카톡/work] Director Kim: this one's better  ↩︎(cut-03.mp4)
```

A trailing `↩︎(…)` means the message is a **reply (quote)**, and the parentheses hold
what it replies to. A KakaoTalk reply carries none of that in its body — send three
files, get back "this one's better", and you'd have to ask which one. So the poller
prints the target alongside.

**In Claude Code, run the poller through the Monitor tool with `persistent: true`.**
Each line becomes an event.

---

## Workspace

Everything lands under `$KAKAO_HOME`, which defaults to `.kakao/` in the current directory.

```
.kakao/
├── rooms.json              room registry ← the only place to change rooms
├── logs/YYYY-MM-DD.jsonl   structured log
├── logs/.kpoll-cursor.json polling cursor
├── files/<room>/<date>/    downloaded attachments
└── chat/YYYY-MM-DD.md      conversation rollup
```

To share one workspace across projects: `export KAKAO_HOME=~/.kakao`.

> ⚠ **Never commit `.kakao/`.** Group-chat message bodies and downloaded attachments live there.

### rooms.json

```json
{
  "me": 9999999,
  "default": "work",
  "rooms": {
    "notice": { "chatId": 222222222222222222, "search": "team notice",
                "label": "Team Notice", "note": "open chat, 2000 people" },
    "work":   { "chatId": 111111111111111, "search": "workroom",
                "label": "Work Room", "note": "" }
  }
}
```

| Field | What | Used by |
|---|---|---|
| `chatId` | numeric ID | kakaocli — reading the DB (polling, attachments) |
| `search` | **part of** the room name | kmsg — typed into the UI search box to find the room (sending) |
| `me` | your own userId | used to filter out the bot's own echo |

These are different things — don't mix them up. Pick a `search` fragment that
**doesn't also match another room**, or messages go to the wrong place.
Run `kfind.sh <fragment>` to see how many rooms it hits before you commit to it;
the senders count again at send time (see "Room search is a substring match" below).

> `chatId` **differs per machine.** Re-run `setup.sh --find` after moving computers.

---

## Rules for behaving in a group chat

Learned the hard way in real group chats. These are manners, not engineering.

- **Never drop the 🤖 prefix.** `ksend.sh` adds it automatically.
  Messages go out **from the user's account** — without a marker nobody can tell
  the bot from the human whose account it is.
- **Speak only when spoken to.** Answer when named or asked a question.
  Jumping in because a work topic came up and you could help is still too much.
- **In the room, one or two lines of conclusion.** Process, numbers, and design go to the terminal.
- **One thought per message.** A newline is the send key, so there are no line breaks inside
  a message — a long one lands as a wall. `ksend.sh` warns past 100 characters. Then cut it.
- **Let the human introduce you first.** A bot appearing out of nowhere startles people.
- **Refuse requests for personal information.** You are borrowing someone's account.
- Call people by **the name shown in the room**, never their real name (see Pitfalls).

---

## Pitfalls — all of these were measured, not guessed

### Don't use `kakaocli send`
Upstream issue #9: it hangs. When it can't resolve the room name it **exits 0 silently**
and the message goes nowhere. **Send with kmsg only.**

### `--dry-run` proves nothing
Neither `kakaocli` nor `kmsg` touches the AX layer in `--dry-run`.
The only way to know the send path works is **to actually send one line to a small room**.

### Zero windows means sending is dead — two different causes

| `windows=0` and | Cause | Fix |
|---|---|---|
| the Window menu is also empty | the window was closed | open the main window |
| the Window menu still lists windows | **the screen is locked** | a human must unlock it |

```bash
ioreg -n Root -d1 -a | grep -A1 CGSSessionScreenIsLocked   # true = locked
```

**Reading works while locked.** Polling hits the local DB and doesn't care; only writing breaks.

### Room search is a substring match — count the hits before sending
Both `kmsg` and `kakaocli` locate a room by **substring match** on its name. There is no
exact-match option. If your `search` fragment matches two rooms, **the message goes to the
wrong one, and you cannot take it back.** This nearly happened: a fragment meant for a 1:1
chat also matched an open chat (2000+ members) and another group chat, and measurement
showed the group chat winning, not the 1:1.

The defense splits in two. **A human picks; the tool stops.**

```bash
scripts/kfind.sh teamname     # picking — lays out every room the fragment hits
```

```
── 방 ──────────────────────────────────────────
  222222222222222222   오픈채팅   2593명  Team info sharing room
  111111111111111      그룹          8명  Our lovely team
  ⚠ 2 곳에 걸린다 — 이 조각으로는 전송하면 안 된다.
```

`ksend.sh`, `kimg.sh`, and `kvid.sh` re-check the same thing against the DB right before
sending and **abort if it isn't exactly one room** (`kroom_verify` in `klib.sh`).

```
⚠ 'teamname' 이 방 2개에 걸린다 — 엉뚱한 방으로 갈 수 있어 멈춘다:
전송을 멈췄다 — rooms.json 의 search 를 더 좁게 고쳐라 (방: work)
```

There is one way to unblock it: **narrow the `search` fragment in `rooms.json`.**
`KROOM_SKIP_VERIFY=1` disables the check, but disabling it writes `room verify.skipped`
to the log — the fact that you turned it off has to stay visible.

Room names live in **three different places**. Look at only one and you get false results.

| Table | What |
|---|---|
| `NTChatRoom.chatName` | usually an **empty string** |
| `NTOpenLink.linkName` | open-chat name |
| `NTChatMeta` (`type=3`) | ordinary group-chat name — often the only place a name exists |

**A 1:1 room has no name at all**, so it can never be picked by name.
`kfind.sh --friends` shows display name, `userId`, and `directChatId` instead.

### A reply doesn't say what it replies to
The target of a KakaoTalk reply (quote) is not in the message body. It's in the
`NTChatMessage.attachment` JSON: `src_logId` / `src_userId` / `src_message`.
**The `referer` column is 0 and useless.** `kpoll.py` reads it and appends `↩︎(target)`.
Without it, send several files and get back "this one's better" and you have to ask, every time.

### `nickName` is not the display name
In ordinary group chats `NTUser.nickName` is **the name saved in your address book —
their real name**. What the room shows is `displayName`. Getting this wrong once meant
addressing someone by their legal name in front of everyone.
Also, one userId can have several multi-profile rows, so a naive JOIN **duplicates every
message** — pull the name with a `LIMIT 1` subquery instead.

### Filter your own echo by the 🤖 prefix, not by account
Since messages go out **from the user's account**, it's tempting to suppress your own echo
with `authorId <> me`. That also **hides everything the account's owner says in the room.**
This cost 35 minutes of silence once — and one of the missed messages was
"are you even listening to me?". Filter on the prefix you added, not on identity.

### Polling must use a time cursor
"Take the newest N and keep the ones with a larger logId" loses messages three ways:

1. If more than N arrive in between, the ones pushed out never come back
2. **`logId` is not monotonic** — an out-of-order message is lost permanently
3. `sentAt` has one-second resolution, so 2–3 messages share a timestamp

`kpoll.py` reads with a `sentAt` cursor **overlapping by 5 seconds**, de-duplicates by
`logId`, and when a batch hits `LIMIT` it pulls the cursor forward and reads again
immediately. Verified at zero loss and zero duplicates.

### A newline is the send key
A newline inside a message makes the KakaoTalk UI send it, splitting your message.
`ksend.sh` replaces newlines with spaces.

### A long message becomes a wall
A newline is the send key, so **there is no way to break a line inside one message.**
`ksend.sh` warns past 100 characters (`KSEND_WARN_LEN`), and `klog.sh stat` prints the length
distribution alongside. Unmeasured, messages only grow — ours were running at a median of 89
characters with 58% over 80 before anyone looked.

### Video cannot go through `kmsg` — it gets pasted in
`kmsg` only has `send-image`; hand it an mp4 and it dies trying to open it as an NSImage.
`kvid.sh` puts the file URL on the NSPasteboard and clicks Edit → Paste through the AX tree.

- AppleScript's `set the clipboard to POSIX file` is not accepted by KakaoTalk — it must be NSPasteboard.
- `set frontmost to true` alone does not deliver keystrokes to KakaoTalk; you need `activate`.
- **Success is judged from the DB, not the screen.** Compare the **id** of the last message,
  never its content or type — send two videos in a row and both read as `video`, so a type
  comparison concludes "it didn't send" and retries until the room is flooded.
- The file is **copied to a short kebab-case name before sending** (the original is untouched).
  Nobody can point at `sfx_One_s_20260816_183555_pitchslow.mp3` when you ask which one it was.
  The mapping lives in `<KAKAO_HOME>/kvid_names.tsv`; look it up with `kvid.sh --what <name>`.

### Attachments download without authentication
The URL lives inside the `NTChatMessage.attachment` JSON with the signature already baked in.
`expire` is in **milliseconds** (the `expires` in the URL is in seconds). Expired ones are
reported as such rather than silently failing.

---

## Finding out what went wrong

These tools **have a history of failing silently**. That's why everything is logged.

```bash
scripts/klog.sh stat
```

Instrumentation has four layers.

| Layer | What it records | Question it answers |
|---|---|---|
| wrapper | `send.ok/retry/fail`, duration, attempts | what fraction succeeds first try |
| Apple Event | window count, AX buttons walked, pure round trip | was the window closed, is tree traversal the bottleneck |
| kmsg internals | cache hits, search misses | is window-keeping actually working |
| **filter audit** | rows the poller **discarded**, by reason | **is it quiet because nobody spoke, or because I stopped listening** |

The last layer matters most. When a filter silently drops messages, the query still succeeds
and simply returns no rows — nothing reports a failure.
**If you build something that skips or filters, count what it threw away.**
A number appearing where zero belongs is the alarm.

---

## Limitations

- **macOS only.** It depends on the KakaoTalk desktop app and the Accessibility API.
- KakaoTalk must be **running and signed in**, with **a window open and the screen unlocked**.
- Sending is UI automation, so the KakaoTalk window briefly comes to the front.
- A KakaoTalk update that changes the accessibility tree can break sending.
- Attachment URLs expire.

## Privacy

Incoming **message bodies are written to the log verbatim**, and attachments are saved as-is.
Never push `.kakao/` to a public repository.

## License

MIT
