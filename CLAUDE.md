# cc-toolkit

## WeChat Hook 流程规则

Stop Hook 拦截微信消息后，只做 `wechat_send → (停)`，不输出任何多余文字（原因：一句"你好"回复就消耗600+ token，每多一字都是浪费）。
