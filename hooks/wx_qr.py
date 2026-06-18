#!/usr/bin/env python3
"""微信扫码登录 — 生成二维码页面 → 浏览器打开 → 扫码 → 保存 token"""
import json, base64, io, webbrowser, os, time, urllib.request, urllib.error, random

BASE_URL = "https://ilinkai.weixin.qq.com"
TOKEN_FILE = os.path.expanduser("~/.cc-weixin/token.json")

def random_uin():
    return base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()

def api(method, path, data=None):
    url = f"{BASE_URL}/{path}"
    headers = {"Content-Type": "application/json", "X-WECHAT-UIN": random_uin()}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode())

def login():
    import urllib.parse
    from datetime import datetime

    print("获取二维码...")
    qr = api("GET", f"ilink/bot/get_bot_qrcode?bot_type=3")
    qrcode_id = qr["qrcode"]
    qr_img = qr.get("qrcode_img_content", qrcode_id)

    import qrcode as qc
    from PIL import Image
    img = qc.make(qr_img)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>微信扫码登录</title>
<style>
body {{ display:flex; justify-content:center; align-items:center; min-height:100vh; margin:0; background:#f5f5f5; font-family:sans-serif; }}
.card {{ background:#fff; border-radius:16px; padding:40px; box-shadow:0 4px 24px rgba(0,0,0,.12); text-align:center; }}
h2 {{ margin:0 0 8px; color:#07c160; }}
p {{ color:#666; margin:0 0 24px; }}
.qr {{ display:inline-block; padding:16px; border:2px solid #eee; border-radius:12px; }}
.qr img {{ display:block; width:280px; height:280px; }}
</style>
</head>
<body>
<div class="card">
<h2>微信扫码登录</h2>
<p>打开微信「扫一扫」绑定 ClawBot</p>
<div class="qr"><img src="data:image/png;base64,{b64}" alt="QR"></div>
</div>
</body>
</html>"""

    path = os.path.expanduser("~/Desktop/wechat_qrcode.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"二维码页面: {path}")
    webbrowser.open(path)

    print("等待扫码...")
    for i in range(150):
        try:
            st = api("GET", f"ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode_id)}")
            status = st.get("status", "wait")
            if status == "confirmed":
                print("\n登录成功！")
                os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
                json.dump({
                    "token": st["bot_token"],
                    "baseUrl": st.get("baseurl", BASE_URL),
                    "accountId": st.get("ilink_bot_id", ""),
                    "userId": st.get("ilink_user_id", ""),
                    "savedAt": datetime.now().isoformat(),
                }, open(TOKEN_FILE, "w"))
                print(f"Token 已保存: {TOKEN_FILE}")
                return
            elif status == "scaned":
                print("\r已扫码，请在微信确认..." if i % 2 == 0 else "", end="", flush=True)
            elif status == "expired":
                print("\n二维码已过期，重新运行脚本")
                return
            else:
                if i % 10 == 0:
                    print(".", end="", flush=True)
        except urllib.error.HTTPError as e:
            print(f"\nHTTP {e.code}: {e.read().decode()}")
            return
        except Exception as e:
            if i % 10 == 0:
                print(f"\n重试: {e}")
        time.sleep(2)

    print("\n登录超时")

if __name__ == "__main__":
    print("=" * 35)
    print("微信 ClawBot 扫码登录")
    print("=" * 35)
    print("依赖: pip install qrcode[pil]")
    print()
    login()
