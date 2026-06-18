#!/usr/bin/env python3
"""
WeChat Stop Hook — 阻塞等待微信新消息，有消息才放 Claude 继续
架构：Stop Hook 脚本自包含长轮询，没消息时阻塞，不空转 Claude
"""
import json, sys, os, time, urllib.request, urllib.error, urllib.parse, base64

QUEUE_FILE = os.path.expanduser("~/.claude/hooks/wechat_msg.json")
TOKEN_FILE = os.path.expanduser("~/.cc-weixin/token.json")

# 递归防护
if os.environ.get("STOP_HOOK_ACTIVE"):
    sys.exit(0)


def log(msg):
    print(msg, file=sys.stderr, flush=True)

def read_session():
    if not os.path.exists(TOKEN_FILE):
        log("[WX-HOOK] 未找到 token 文件，请先运行 wechat_login.py")
        return None
    return json.load(open(TOKEN_FILE))

def random_uin():
    import random
    return base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()

def api_post(base_url, endpoint, body, token, timeout=38):
    url = f"{base_url.rstrip('/')}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": random_uin(),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP {e.code}: {e.read().decode()}")

def get_updates(base_url, token, buf):
    resp = api_post(base_url, "ilink/bot/getupdates", {"get_updates_buf": buf or ""}, token)
    return resp if resp else {"ret": 0, "msgs": [], "get_updates_buf": buf}

def extract_text(msg):
    for item in msg.get("item_list", []):
        t = item.get("type")
        if t == 1 and item.get("text_item", {}).get("text"):
            return item["text_item"]["text"]
        if t == 3 and item.get("voice_item", {}).get("text"):
            return f"[语音] {item['voice_item']['text']}"
        if t == 2: return "[图片]"
        if t == 4: return f"[文件] {item.get('file_item', {}).get('file_name', '')}"
        if t == 5: return "[视频]"
    return "[空消息]"

def read_queue():
    if not os.path.exists(QUEUE_FILE):
        return {"pending": [], "buf": ""}
    return json.load(open(QUEUE_FILE))

def write_queue(data):
    json.dump(data, open(QUEUE_FILE, "w"))

def wait_for_message(session):
    """长轮询等待微信新消息（永久阻塞，除非 wx 开关关闭），返回消息 dict / None"""
    token = session["token"]
    base_url = session.get("baseUrl", "https://ilinkai.weixin.qq.com")

    while True:
        try:
            # 每次循环检查开关 — 关闭就退出
            queue = read_queue()
            if not queue.get("active", True):
                log("[WX] deactivated, exiting")
                return None
            if queue.get("pending"):
                log(f"[WX] queue {len(queue['pending'])} pending")
                return queue["pending"][0]

            resp = get_updates(base_url, token, queue.get("buf", ""))
            msgs = resp.get("msgs") or []
            new_buf = resp.get("get_updates_buf", queue.get("buf", ""))

            if msgs:
                for msg in msgs:
                    text = extract_text(msg)
                    from_id = msg.get("from_user_id", "")
                    ctx = msg.get("context_token", "")
                    queue["pending"].append({"from": from_id, "text": text, "ctx": ctx})
                    log(f"[WX] msg: {from_id}: {text[:60]}")
                queue["buf"] = new_buf
                write_queue(queue)
                return queue["pending"][0]

        except Exception as e:
            if "timed out" not in str(e).lower():
                log(f"[WX] err: {e}")
            # 超时重试

        time.sleep(1)

def toggle_active(on=True):
    """启/停 WeChat Hook 循环模式"""
    queue = {"pending": [], "buf": "", "active": on}
    if os.path.exists(QUEUE_FILE):
        q = json.load(open(QUEUE_FILE))
        q["active"] = on
        queue = q
    json.dump(queue, open(QUEUE_FILE, "w"))
    return on

def main():
    # 检查 active 开关 — 只有标记 active=true 时才阻塞等消息
    if os.path.exists(QUEUE_FILE):
        queue = json.load(open(QUEUE_FILE))
        if not queue.get("active"):
            sys.exit(0)
    else:
        sys.exit(0)

    session = read_session()
    if not session:
        log("[WX-HOOK] 未登录，请先运行 wechat_login.py")
        sys.exit(0)

    log("[WX] wait...")
    msg = wait_for_message(session)

    if msg:
        # block 前清 pending，防止后续 Stop hook 重复触发
        q = json.load(open(QUEUE_FILE))
        q["pending"] = []
        json.dump(q, open(QUEUE_FILE, "w"))
        print(json.dumps({"decision":"block","reason":f"wx:{msg['from']}|{msg['text']}"}))

if __name__ == "__main__":
    main()
