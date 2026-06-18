#!/usr/bin/env python3
"""微信登录 — 网页二维码 → 扫码 → 保存 token"""
import json, time, os, sys, io, base64, urllib.request, urllib.error

BASE_URL = "https://ilinkai.weixin.qq.com"
BOT_TYPE = "3"
TOKEN_FILE = os.path.expanduser("~/.cc-weixin/token.json")
QR_HTML = os.path.expanduser("~/Desktop/wechat_qrcode.html")

def random_uin():
    import random
    return base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()

def api(method, path, data=None, token=None, timeout=15):
    url = f"{BASE_URL}/{path}"
    headers = {"Content-Type": "application/json", "X-WECHAT-UIN": random_uin()}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["AuthorizationType"] = "ilink_bot_token"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP {e.code}: {e.read().decode()}")

def get_qrcode():
    return api("GET", f"ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}")

def poll_qrcode(qrcode):
    return api("GET", f"ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode)}")

def make_qr_html(qr_img_content):
    """生成内嵌二维码图片的 HTML 页面"""
    import qrcode as qc
    from PIL import Image
    img = qc.make(qr_img_content)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>微信扫码登录 ClawBot</title>
<style>
body {{ display:flex; justify-content:center; align-items:center; min-height:100vh; margin:0; background:#f5f5f5; font-family:sans-serif; }}
.card {{ background:#fff; border-radius:16px; padding:40px; box-shadow:0 4px 24px rgba(0,0,0,.12); text-align:center; }}
h2 {{ margin:0 0 8px; color:#07c160; }}
p {{ color:#666; margin:0 0 24px; }}
.qr {{ display:inline-block; padding:16px; border:2px solid #eee; border-radius:12px; }}
.qr img {{ display:block; width:280px; height:280px; }}
.status {{ margin-top:20px; padding:10px; border-radius:8px; font-size:14px; }}
.waiting {{ background:#fff3cd; color:#856404; }}
.scanned {{ background:#cce5ff; color:#004085; }}
.done {{ background:#d4edda; color:#155724; }}
</style>
</head>
<body>
<div class="card">
<h2>🔗 微信扫码登录</h2>
<p>打开微信「扫一扫」绑定 ClawBot</p>
<div class="qr"><img src="data:image/png;base64,{b64}" alt="QR Code"></div>
<div class="status waiting" id="status">⏳ 等待扫码...</div>
</div>
<script>
let retry = 0;
const maxRetry = 30;
function poll() {{
  fetch('/status').then(r=>r.text()).then(s=>{{
    const el = document.getElementById('status');
    if (s === 'wait') {{ el.className='status waiting'; el.textContent='⏳ 等待扫码...'; setTimeout(poll, 2000); }}
    else if (s === 'scaned') {{ el.className='status scanned'; el.textContent='👀 已扫码，请在微信确认'; setTimeout(poll, 2000); }}
    else if (s === 'done') {{ el.className='status done'; el.textContent='✅ 登录成功！可以关闭此页面'; }}
    else {{ if(++retry > maxRetry) {{ el.textContent='⏰ 登录超时，请重新生成二维码'; return; }} setTimeout(poll, 2000); }}
  }}).catch(()=>{{ setTimeout(poll, 2000); }});
}}
setTimeout(poll, 1000);
</script>
</body>
</html>"""

def serve_status_page(qrcode_id, timer=300):
    """简易 HTTP 服务器：返回二维码页面 + /status 轮询接口"""
    import http.server
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                try:
                    st = poll_qrcode(qrcode_id)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(st.get("status", "wait").encode())
                except:
                    self.send_response(200)
                    self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())
        def log_message(self, *a): pass
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return port, server

def login():
    print("获取二维码...")
    qr = get_qrcode()
    qrcode_id = qr["qrcode"]
    qr_img = qr.get("qrcode_img_content", "")
    global html
    html = make_qr_html(qr_img)

    port, server = serve_status_page(qrcode_id)
    url = f"http://127.0.0.1:{port}"
    print(f"二维码页面: {url}")
    os.startfile(url)

    deadline = time.time() + 300
    refresh = 0
    while time.time() < deadline:
        try:
            st = poll_qrcode(qrcode_id)
        except:
            time.sleep(2); continue
        status = st.get("status", "wait")
        if status == "wait":
            print(".", end="", flush=True)
        elif status == "scaned":
            print("\n已扫码，请在微信确认...")
        elif status == "expired":
            refresh += 1
            if refresh > 3:
                raise Exception("二维码多次过期")
            print(f"\n刷新二维码({refresh}/3)...")
            qr = get_qrcode()
            qrcode_id = qr["qrcode"]
            qr_img = qr.get("qrcode_img_content", "")
            html = make_qr_html(qr_img)
        elif status == "confirmed":
            print("\n登录成功！")
            os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
            session = {
                "token": st["bot_token"],
                "baseUrl": st.get("baseurl", BASE_URL),
                "accountId": st.get("ilink_bot_id", ""),
                "userId": st.get("ilink_user_id", ""),
                "savedAt": datetime.now().isoformat(),
            }
            json.dump(session, open(TOKEN_FILE, "w"))
            print(f"Bot ID: {session['accountId']}")
            print(f"Token 已保存: {TOKEN_FILE}")
            print("现在可以启动 Claude 配合 Stop Hook 自动回复微信消息了。")
            return session
        time.sleep(1)
    raise Exception("登录超时")

if __name__ == "__main__":
    from datetime import datetime
    import urllib.parse
    print("=" * 45)
    print("微信 ClawBot 登录")
    print("=" * 45)
    login()
