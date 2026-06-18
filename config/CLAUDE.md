# Project Instructions

## WeChat Hook 流程规则

Stop Hook 拦截微信消息后，只做 `wechat_send → (停)`，不输出任何多余文字（原因：一句"你好"回复就消耗600+ token，每多一字都是浪费）。

## 自动保存上下文

当 SessionEnd hook 触发后你恢复工作时，先执行 `/save-memory` 保存上下文，再继续你的任务。
