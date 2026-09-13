"""Launch a dedicated review session without persistent configuration changes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PLUGIN = Path(__file__).resolve().parent
ROOT = PLUGIN.parents[2]


def guard_command():
    config = json.loads((PLUGIN / "hooks/hooks.json").read_text(encoding="utf-8"))
    rules = config["hooks"]["PreToolUse"]
    if len(rules) != 1 or rules[0]["matcher"] != ".*" or len(rules[0]["hooks"]) != 1:
        raise ValueError("unexpected guard configuration")
    hook = rules[0]["hooks"][0]
    if hook["type"] != "command" or not isinstance(hook["args"], list):
        raise ValueError("guard must use an exec command")
    command = [hook["command"], *hook["args"]]
    if not all(isinstance(arg, str) and arg for arg in command):
        raise ValueError("invalid guard command")
    if not shutil.which(command[0]):
        raise ValueError("guard executable unavailable")
    return [arg.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN)) for arg in command]


def guard_preflight(env):
    command = guard_command()
    for tool, code in [("Write", 2), ("Read", 0)]:
        event = {"hook_event_name": "PreToolUse", "cwd": str(ROOT),
                 "tool_name": tool, "tool_input": {"file_path": "AGENTS.md"}}
        result = subprocess.run(command, input=json.dumps(event), text=True,
                                capture_output=True, timeout=10, cwd=ROOT, env=env,
                                check=False)
        if result.returncode != code or (code == 2 and not result.stderr.startswith(
                "VOXDARA_READ_ONLY_DENIED:")) or (code == 0 and json.loads(result.stdout) != {}):
            raise ValueError("guard self-test failed")


def serena_config():
    executable = shutil.which("serena")
    if not executable:
        raise ValueError("Serena executable unavailable")
    return {"mcpServers": {"serena": {
        "type": "stdio", "command": executable,
        "args": ["start-mcp-server", "--context", "claude-code", "--project", str(ROOT)],
    }}}


def main():
    env = os.environ.copy()
    env.update(DISABLE_AUTOUPDATER="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
               CLAUDE_CODE_AUTO_CONNECT_IDE="false", CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL="1")
    try:
        guard_preflight(env)
        mcp = serena_config()
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print("VOXDARA_REVIEW_STARTUP_BLOCKED: guard execution/self-test or Serena configuration failed; Claude was not launched.",
              file=sys.stderr)
        return 1
    return subprocess.run(
        ["claude", "--plugin-dir", str(PLUGIN), "--permission-mode", "manual",
         "--setting-sources", "project",
         "--strict-mcp-config", "--mcp-config", json.dumps(mcp),
         "--tools", "Read,Grep,Glob,Agent,Skill,Bash,ToolSearch",
         "--settings", json.dumps({"remoteControlAtStartup": False})],
        cwd=ROOT, env=env, check=False,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
