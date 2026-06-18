{
  "permissions": {
    "allow": ["Bash(*)","Edit(*)","Write(*)","WebSearch","mcp__wechat__*"],
    "defaultMode": "auto"
  },
  "hooks": {
    "SessionStart": [{"matcher":"","hooks":[{"type":"command","command":"pythonw "{{HOOKS_DIR}}/launch_monitor.py""}]}],
    "Stop": [{"matcher":"","hooks":[{"type":"command","command":"python "{{HOOKS_DIR}}/wechat_poller.py"","timeout": 2000000}]}]
  },
  "skipDangerousModePermissionPrompt": true,
  "theme": "auto",
  "autoCompactEnabled": false,
  "worktree": {"baseRef": "fresh"},
  "enableAllProjectMcpServers": true
}
