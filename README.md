# Claude Code Toolkit

Claude Code 增强套件 — 换台电脑也能用。

## 功能

| 组件 | 说明 |
|------|------|
| **cc-monitor** | 实时浮窗显示 token 用量 + 上下文占比，可拖拽，含微信开关按钮 |
| **WeChat 集成** | 微信消息 → Stop Hook 唤醒 Claude → MCP read/send 收发 |
| **微信开关** | cc-monitor 浮窗点 wx 按钮启停，不开时不占用资源 |

---

## 新机器完整配置步骤

### 0. 前置要求

- Claude Code 已安装
- Python 3.8+（`python --version` 确认）
- Node.js（`node --version` 确认）
- Git（可选，用于 clone）

### 1. 安装微信依赖

本机首次：
```bash
pip install wmi psutil 2>nul || pip3 install wmi psutil
```

### 2. 复制脚本

```bash
# 克隆仓库
git clone https://gitee.com/bbsbbs4321/cc-toolkit.git C:/tmp/cc-toolkit

# 创建 hooks 目录
mkdir -p ~/.claude/hooks

# 复制所有脚本
cp C:/tmp/cc-toolkit/hooks/*.py ~/.claude/hooks/
```

### 3. 配置 settings.json

编辑 `~/.claude/settings.json`，写入以下内容（替换 `YOUR_USERNAME`）：

<details>
<summary>settings.json 完整内容（点击展开）</summary>

```json
{
  "permissions": {
    "allow": ["Bash(*)","Edit(*)","Write(*)","WebSearch","mcp__wechat__*"],
    "defaultMode": "auto"
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "pythonw \"C:/Users/YOUR_USERNAME/.claude/hooks/launch_monitor.py\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:/Users/YOUR_USERNAME/.claude/hooks/wechat_poller.py\""
          }
        ]
      }
    ]
  },
  "skipDangerousModePermissionPrompt": true,
  "theme": "auto",
  "autoCompactEnabled": false,
  "worktree": {"baseRef": "fresh"},
  "enableAllProjectMcpServers": true
}
```
</details>

**⚠️ 注意**：
- `YOUR_USERNAME` 要改成你的 Windows 用户名（如 `AMCI`）
- `SessionStart` 用 `pythonw`（无窗口后台启动 monitor，不弹 cmd）
- `Stop` 用 `python`（hook 需要等待轮询结束）

### 4. 注册 MCP 服务器

编辑 `~/.claude/mcp.json`，写入：

```json
{
  "mcpServers": {
    "wechat": {
      "command": "E:/python/python.exe",
      "args": ["-X", "utf8", "C:/Users/YOUR_USERNAME/.claude/hooks/wechat_mcp_server.py"]
    }
  }
}
```

如果 python 路径不同，用 `where python` 查。

### 5. 微信扫码登录

```bash
python ~/.claude/hooks/wechat_login.py
```

会弹出二维码在浏览器，扫码后 token 保存在 `~/.cc-weixin/token.json`。

### 6. 重启 Claude Code

启动后右上角出现 cc-monitor 浮窗即成功。

---

## 架构与通信

```
┌─────────────────────────────────────────────────┐
│ Claude Code 进程                                 │
│                                                  │
│  ┌──────────┐   ┌──────────────────────────┐    │
│  │ cc-monitor│   │  会话内 (Claude 运行时)    │    │
│  │ 浮窗(GUI) │   │                          │    │
│  │  ┌──────┐ │   │  MCP wechat_read/send    │    │
│  │  │wx按钮 │─┼──┼── 读写                    │    │
│  │  └──────┘ │   │     ↓                    │    │
│  └──────────┘   │  ┌─────────────────┐      │    │
│                 │  │ wechat_msg.json  │      │    │
│                 │  │ (队列 + 开关状态)  │      │    │
│                 │  └─────────────────┘      │    │
│                 │        ↕ 读写              │    │
│                 │  ┌─────────────────┐      │    │
│                 │  │ wechat_mcp_     │      │    │
│                 │  │ server.py       │      │    │
│                 │  │ (MCP stdio)     │      │    │
│                 │  └─────────────────┘      │    │
│                 └──────────────────────────┘    │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │ Stop Hook (每次工具调用后触发)              │    │
│  │  ┌─────────────────────────────────┐      │    │
│  │  │ wechat_poller.py                │      │    │
│  │  │ 1. 读 active 标志               │      │    │
│  │  │ 2. off → 直接退出                │      │    │
│  │  │ 3. on  → 长轮询微信 API (5分钟)   │      │    │
│  │  │ 4. 有新消息 → 写 wechat_msg.json │      │    │
│  │  │ 5. 输出 block → 唤醒 Claude      │      │    │
│  │  └─────────────────────────────────┘      │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘

微信服务器 ──WebSocket/API──→ wechat_poller.py (轮询)
wechat_poller.py ──写文件──→ wechat_msg.json
wechat_msg.json  ←──读文件── wechat_mcp_server.py (MCP)
wechat_msg.json  ←──读/写── cc-monitor wx按钮 (开关)
```

### 关键设计

**Stop Hook + MCP 分离**：
- Stop Hook 不管收发，只负责"等消息 → 叫醒 Claude"
- MCP Server 不管轮询，只负责"读消息 / 发消息"
- 两者通过 `wechat_msg.json` 文件解耦

**为什么不用服务进程**：
- 对比 [claude-child](https://gitee.com/bbsbbs4321/claude-child)（独立的 HTTP 子进程服务）
- Stop Hook 方案无需端口、无需通信协议、无需心跳
- 零额外进程常驻，不使用时零资源消耗
- 开关控制只需写一个 JSON 文件

**wx 按钮怎么工作**：
1. 点击切换 `wechat_msg.json` 的 `active` 字段
2. 下次 Stop Hook 触发时 poller 读到 `false` 直接退出
3. 关闭后微信消息不唤醒 Claude，不占任何资源

### 数据流：收到微信消息

```
微信消息 → wechat_poller.py (Stop Hook) 
  → 写入 wechat_msg.json pending
  → print({"decision":"block","reason":"wx"}) 
  → Claude 被唤醒
  → Claude 调 MCP wechat_read
  → wechat_mcp_server.py 读 wechat_msg.json → 返回消息列表
  → Claude 处理 → MCP wechat_send
  → wechat_mcp_server.py 调 iLink API 发回微信
```

cc-monitor 标题栏右侧有 **wx** 按钮：
- 🟢 绿色 = 开启（微信消息会唤醒 Claude）
- ⚫ 灰色 = 关闭

点击切换，立即生效，无需重启。

---

## 文件结构

```
~/.claude/
├── settings.json              # Hook + 权限配置
├── mcp.json                   # MCP 服务器注册
├── hooks/
│   ├── cc_monitor.py          # Token 用量浮窗（GUI）
│   ├── launch_monitor.py      # SessionStart 后台启动器
│   ├── wechat_poller.py       # Stop Hook 微信消息轮询
│   ├── wechat_mcp_server.py   # MCP Server（stdio 协议）
│   └── wechat_login.py        # 微信扫码登录
├── cc_monitor.pid             # 浮窗 PID（防重复自动管理）
└── wechat_msg.json            # 微信消息队列（自动创建）
```

## 卸载

```bash
# 删脚本
rm -rf ~/.claude/hooks/cc_monitor.py ~/.claude/hooks/launch_monitor.py ~/.claude/hooks/wechat_*.py ~/.claude/cc_monitor.pid ~/.claude/hooks/wechat_msg.json

# 去掉 settings.json 里的 hooks 段
# 去掉 mcp.json 里的 wechat 段
```
## 快捷方式
E:\py脚本\新环境\terminal-1.18.1462.0\WindowsTerminal.exe cmd.exe /k cd /d E:\py脚本\新环境\terminal-1.18.1462.0 && claude --dangerously-skip-permissions "停停"
## 常见问题

**Q: 浮窗没出现？**
检查 `pythonw` 是否可用（`where pythonw`），手动跑 `pythonw ~/.claude/hooks/launch_monitor.py` 看报错。

**Q: 微信不响应？**
1. `python ~/.claude/hooks/wechat_login.py` 重新扫码
2. 检查浮窗 wx 按钮是不是绿色
3. 检查 `~/.cc-weixin/token.json` 是否存在
