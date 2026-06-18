#!/usr/bin/env python3
"""WeChat MCP Server — 收发微信消息，通过 iLink Bot API"""
import json, sys, os, uuid, base64, random, urllib.request, urllib.error

TOKEN_FILE = os.path.expanduser("~/.cc-weixin/token.json")
QUEUE_FILE = os.path.expanduser("~/.claude/hooks/wechat_msg.json")

def log(*a):
    print(*a, file=sys.stderr, flush=True)

def random_uin():
    return base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()

def api_post(base_url, endpoint, body, token=None, timeout=38):
    url = f"{base_url.rstrip('/')}/{endpoint}"
    headers = {"Content-Type": "application/json", "AuthorizationType": "ilink_bot_token", "X-WECHAT-UIN": random_uin()}
    if token: headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP {e.code}: {e.read().decode()}")

def get_session():
    if not os.path.exists(TOKEN_FILE):
        raise Exception("未登录，请先运行 wechat_login.py")
    return json.load(open(TOKEN_FILE))

def get_pending():
    if not os.path.exists(QUEUE_FILE):
        return []
    q = json.load(open(QUEUE_FILE))
    return q.get("pending", [])

def clear_pending():
    if os.path.exists(QUEUE_FILE):
        q = json.load(open(QUEUE_FILE))
        q["pending"] = []
        json.dump(q, open(QUEUE_FILE, "w"))

def send_wechat(to_user, text, ctx=""):
    clear_pending()
    session = get_session()
    token = session["token"]
    base_url = session.get("baseUrl", "https://ilinkai.weixin.qq.com")
    cid = f"wxw-{uuid.uuid4().hex}"
    api_post(base_url, "ilink/bot/sendmessage", {
        "msg": {
            "from_user_id": "", "to_user_id": to_user,
            "client_id": cid, "message_type": 2,
            "message_state": 2, "context_token": ctx,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        },
    }, token)

# ─── MCP stdio 协议 ───

def handle_request(req):
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "wechat", "version": "1.0.0"},
            }
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": [
                {
                    "name": "wechat_read",
                    "description": "读取微信待处理消息列表",
                    "inputSchema": {"type": "object", "properties": {}, "required": []},
                },
                {
                    "name": "wechat_send",
                    "description": "发送微信消息",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "to_user": {"type": "string", "description": "接收用户 ID（来自 wechat_read 的 from 字段）"},
                            "text": {"type": "string", "description": "消息内容"},
                            "ctx": {"type": "string", "description": "上下文 token（来自消息的 ctx 字段，可选）"},
                        },
                        "required": ["to_user", "text"],
                    },
                },
            ]}
        }

    if method == "tools/call":
        tool = params.get("name")
        args = params.get("arguments", {})

        try:
            if tool == "wechat_read":
                pending = get_pending()
                if not pending:
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "[]"}]}}
                clear_pending()
                lines = []
                for m in pending:
                    lines.append(f"[{m['from']}]\n{m['text']}")
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "\n---\n".join(lines)}]}}

            elif tool == "wechat_send":
                send_wechat(args["to_user"], args["text"], args.get("ctx", ""))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "已发送"}]}}

            else:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"未知工具: {tool}"}}

        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}

    if method == "notifications/initialized":
        return None

    log(f"未知方法: {method}")
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"未知方法: {method}"}}

def main():
    log("[WX-MCP] 启动")
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            if resp:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            pass
        except Exception as e:
            log(f"[WX-MCP] 错误: {e}")

if __name__ == "__main__":
    main()
