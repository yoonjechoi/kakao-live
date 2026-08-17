import sys, time
from Quartz import (CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown,
                    kCGEventLeftMouseUp, kCGEventRightMouseDown, kCGEventRightMouseUp,
                    kCGEventMouseMoved, kCGHIDEventTap, kCGMouseButtonLeft, kCGMouseButtonRight)
def move(x,y):
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None,kCGEventMouseMoved,(x,y),kCGMouseButtonLeft)); time.sleep(0.15)
def lclick(x,y):
    move(x,y)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None,kCGEventLeftMouseDown,(x,y),kCGMouseButtonLeft)); time.sleep(0.08)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None,kCGEventLeftMouseUp,(x,y),kCGMouseButtonLeft)); time.sleep(0.25)
def rclick(x,y):
    move(x,y)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None,kCGEventRightMouseDown,(x,y),kCGMouseButtonRight)); time.sleep(0.08)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None,kCGEventRightMouseUp,(x,y),kCGMouseButtonRight)); time.sleep(0.9)

act_x, act_y = 1600, 500              # 창 활성화용 빈 곳
msg_x, msg_y = int(sys.argv[1]), int(sys.argv[2])
del_x, del_y = msg_x - 109, msg_y - 79   # 메뉴 「모두에게서 삭제」 상대 위치
lclick(act_x, act_y)                  # 1) 창 활성화 — 이게 없으면 메뉴가 안 뜬다
rclick(msg_x, msg_y)                  # 2) 말풍선 우클릭
lclick(del_x, del_y)                  # 3) 모두에게서 삭제
print(f"실행: 활성화 → 우클릭({msg_x},{msg_y}) → 삭제({del_x},{del_y})")
