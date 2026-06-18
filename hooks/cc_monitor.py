#!/usr/bin/env python3
"""Claude Code Context Monitor — 实时浮窗显示 token 用量"""

import tkinter as tk
import json
import os
import glob
import threading
import time

HOME = os.environ.get('HOME', os.path.expanduser('~'))
if HOME.startswith('/'):
    import subprocess
    try:
        HOME = subprocess.check_output(['cygpath', '-w', HOME], text=True).strip()
    except Exception:
        pass

PROJECTS_DIR = os.path.join(HOME, '.claude', 'projects')
WX_QUEUE = os.path.join(HOME, '.claude', 'hooks', 'wechat_msg.json')
SETTINGS_PATH = os.path.join(HOME, '.claude', 'settings.json')
MAX_CTX = 1_000_000  # default, overridden per-tick via settings

MODEL_CTX = {
    'sonnet': 200_000,
    'opus': 200_000,
    'haiku': 200_000,
}

STATIC = {
    'System prompt':   5500,
    'System tools':   16800,
    'MCP tools':       4000,
    'Memory files':    1900,
    'Skills':           842,
}
STATIC_SUM = sum(STATIC.values())

# 每条分类独立颜色 — 高饱和度，肉眼明显区分
CAT_COLORS = [
    ('System prompt',   '#c9d1d9'),  # 白色
    ('System tools',    '#4da6ff'),  # 蓝色
    ('MCP tools',       '#00e5ff'),  # 青色
    ('Memory files',    '#ff9100'),  # 橙色
    ('Skills',          '#ffea00'),  # 黄色
    ('Messages',        '#ea80fc'),  # 粉紫
    ('Compact buffer',  '#c9d1d9'),  # 白色
    ('Free space',      '#69f0ae'),  # 亮绿
]

FONT = ('Consolas', 8)
CAT_ORDER = [c[0] for c in CAT_COLORS]


class Monitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.92)

        sw = self.root.winfo_screenwidth()
        self.root.geometry(f'252x272+{sw - 272}+20')

        self._ox = self._oy = 0
        self._last_text = ''

        self.c = {
            'bg': '#0d1117', 'card': '#161b22',
            'fg': '#c9d1d9', 'muted': '#8b949e',
            'red': '#f85149', 'yellow': '#d2991d', 'green': '#3fb950',
        }
        self.root.configure(bg=self.c['bg'])

        self._build()
        self._wx_update_label()
        self._tick()
        threading.Thread(target=self._loop, daemon=True).start()

    # ── UI ──────────────────────────────────────────
    def _build(self):
        c = self.c
        self.root.bind('<Button-1>', self._drag_start)
        self.root.bind('<B1-Motion>', self._drag_on)

        # 标题行
        h = tk.Frame(self.root, bg=c['bg'])
        h.pack(fill=tk.X, padx=10, pady=(8, 2))
        self.v_title = tk.Label(h, text='Claude Context', fg=c['fg'], bg=c['bg'],
                                font=('Segoe UI', 9, 'bold'))
        self.v_title.pack(side=tk.LEFT)

        # wx 开关
        self.v_wx = tk.Label(h, text='', fg=c['green'], bg=c['bg'],
                             font=('Segoe UI', 8, 'bold'), cursor='hand2')
        self.v_wx.pack(side=tk.RIGHT, padx=(0, 4))
        self.v_wx.bind('<Button-1>', self._wx_toggle)

        x = tk.Label(h, text='✕', fg=c['muted'], bg=c['bg'],
                     font=('Segoe UI', 11), cursor='hand2')
        x.pack(side=tk.RIGHT, padx=(0, 8))
        x.bind('<Button-1>', lambda e: self.root.destroy())

        cp = tk.Label(h, text='📋', fg=c['muted'], bg=c['bg'],
                      font=('Segoe UI', 10), cursor='hand2')
        cp.pack(side=tk.RIGHT)
        cp.bind('<Button-1>', self._copy)

        # 百分比
        self.v_pct = tk.Label(self.root, text='--%', fg=c['green'], bg=c['bg'],
                              font=('Consolas', 20, 'bold'))
        self.v_pct.pack(pady=(4, 0))

        # 进度条
        bar_bg = tk.Frame(self.root, bg=c['card'], height=6)
        bar_bg.pack(fill=tk.X, padx=10, pady=(4, 6))
        self.v_bar = tk.Frame(bar_bg, bg=c['green'], width=0, height=6)
        self.v_bar.place(x=0, y=0)

        # 分割线
        tk.Frame(self.root, bg=c['card'], height=1).pack(fill=tk.X, padx=10, pady=(0, 4))

        # 表头
        tk.Label(self.root, text='Estimated usage by category',
                 fg=c['muted'], bg=c['bg'], font=('Segoe UI', 7)).pack(padx=10, anchor=tk.W)

        # 每条分类一个独立 Label，保证颜色准确
        self.v_lines = {}
        detail_frame = tk.Frame(self.root, bg=c['bg'])
        detail_frame.pack(padx=10, pady=(2, 8), anchor=tk.W, fill=tk.X)

        for name, color in CAT_COLORS:
            lbl = tk.Label(detail_frame, text='', fg=color, bg=c['bg'],
                          font=FONT, anchor=tk.W, justify=tk.LEFT)
            lbl.pack(fill=tk.X)
            self.v_lines[name] = lbl

    # ── 拖拽 ────────────────────────────────────────
    def _drag_start(self, e):
        self._ox = e.x_root - self.root.winfo_x()
        self._oy = e.y_root - self.root.winfo_y()

    def _drag_on(self, e):
        self.root.geometry(f'+{e.x_root - self._ox}+{e.y_root - self._oy}')

    # ── 复制 ────────────────────────────────────────
    def _copy(self, e):
        self.root.clipboard_clear()
        self.root.clipboard_append(self._last_text)
        e.widget.config(fg=self.c['green'])
        self.root.after(300, lambda: e.widget.config(fg=self.c['muted']))

    # ── WeChat 开关 ─────────────────────────────────
    def _wx_state(self):
        try:
            with open(WX_QUEUE) as f:
                return json.load(f).get('active', False)
        except Exception:
            return False

    def _wx_toggle(self, e=None):
        on = not self._wx_state()
        try:
            q = json.load(open(WX_QUEUE)) if os.path.exists(WX_QUEUE) else {}
            q['active'] = on
            json.dump(q, open(WX_QUEUE, 'w'))
        except Exception:
            pass
        self._wx_update_label()

    def _wx_update_label(self):
        on = self._wx_state()
        color = self.c['muted'] if not on else (self.c['green'] if on else self.c['red'])
        self.v_wx.config(text='wx' if on else 'wx', fg=color)

    # ── 数据 ────────────────────────────────────────
    def _detect_max_ctx(self):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                s = json.load(f)
            m = s.get('model', '')
            return MODEL_CTX.get(m, 1_000_000)
        except Exception:
            return 1_000_000

    def _latest_file(self):
        files = glob.glob(os.path.join(PROJECTS_DIR, '*', '*.jsonl'))
        return max(files, key=os.path.getmtime) if files else None

    def _parse(self, path):
        total_in = total_out = total_cache = 0
        li = lc = lo = 0
        title = ''
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get('type') == 'assistant':
                        u = d.get('message', {}).get('usage', {})
                        if u:
                            total_in += u.get('input_tokens', 0)
                            total_out += u.get('output_tokens', 0)
                            total_cache += u.get('cache_read_input_tokens', 0)
                            li = u.get('input_tokens', 0)
                            lc = u.get('cache_read_input_tokens', 0)
                            lo = u.get('output_tokens', 0)
                    if not title and d.get('type') == 'ai-title':
                        title = d.get('aiTitle', '')
        except OSError:
            pass
        return total_in, total_out, total_cache, li, lc, lo, title

    def _loop(self):
        while True:
            self._tick()
            time.sleep(2)

    def _tick(self):
        try:
            path = self._latest_file()
            max_ctx = self._detect_max_ctx()
            if not path:
                self.root.after(0, self._render, 0, 0, 0, 0, 0, 0, '', max_ctx)
                return
            self.root.after(0, self._render, *self._parse(path), max_ctx)
        except Exception:
            pass
        self.root.after(0, self._wx_update_label)

    def _render(self, ti, to, tc, li, lc, lo, title, max_ctx):
        c = self.c

        msg_tokens = li
        compact = max(0, (li + lc) - STATIC_SUM - msg_tokens)
        if compact < 1000:
            compact = 3000

        total_used = STATIC_SUM + msg_tokens + compact
        pct = min(total_used / max_ctx * 100, 100)
        free = max_ctx - total_used

        if pct > 80:
            color = c['red']
        elif pct > 50:
            color = c['yellow']
        else:
            color = c['green']

        if title:
            self.v_title.config(text=title[:30])

        self.v_pct.config(text=f'{pct:.1f}%', fg=color)
        self.v_bar.place_configure(width=int(232 * pct / 100))
        self.v_bar.configure(bg=color)

        # 更新每条分类 Label
        def _p(v):
            return f'{v/max_ctx*100:.1f}%'

        vals = {s[0]: s[1] for s in STATIC.items()}
        vals.update({
            'System prompt':  STATIC['System prompt'],
            'System tools':   STATIC['System tools'],
            'MCP tools':      STATIC['MCP tools'],
            'Memory files':   STATIC['Memory files'],
            'Skills':         STATIC['Skills'],
            'Messages':       msg_tokens,
            'Compact buffer': compact,
            'Free space':     free,
        })

        plain_lines = []
        for name in CAT_ORDER:
            val = vals[name]
            line = f'  {name:15s} {val/1000:6.1f}k ({_p(val)})'
            plain_lines.append(line)
            self.v_lines[name].config(text=line)

        self._last_text = (
            'Estimated usage by category\n' +
            '\n'.join(plain_lines) +
            f'\n---\nSession: in {ti/1000:.1f}k  out {to/1000:.1f}k  cache {tc/1000:.1f}k'
        )


if __name__ == '__main__':
    PID_FILE = os.path.join(HOME, '.claude', 'cc_monitor.pid')
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    try:
        Monitor().root.mainloop()
    finally:
        if os.path.exists(PID_FILE) and open(PID_FILE).read().strip() == str(os.getpid()):
            os.remove(PID_FILE)
