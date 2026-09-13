"""Local metadata and read-only boundary checks; no Claude API calls."""
import importlib.util
import contextlib
import io
import json
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / ".claude/plugins/voxdara-review"
GUARD = PLUGIN / "hooks/read_only.py"
spec = importlib.util.spec_from_file_location("review_guard", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
launcher_spec = importlib.util.spec_from_file_location("review_launcher", PLUGIN / "review.py")
launcher = importlib.util.module_from_spec(launcher_spec)
launcher_spec.loader.exec_module(launcher)


def metadata(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("frontmatter must start on the first line")
    frontmatter, body = text[4:].split("\n---\n", 1)
    # Do not let YAML's last-key-wins behavior hide duplicate metadata.
    node = yaml.compose(frontmatter)
    keys = [key.value for key, _ in node.value]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate frontmatter key")
    return yaml.safe_load(frontmatter), body


class ReviewHarnessTests(unittest.TestCase):
    def event(self, tool, **args):
        return {"hook_event_name": "PreToolUse", "cwd": str(ROOT),
                "tool_name": tool, "tool_input": args}

    def test_metadata_and_registration_contract(self):
        manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "voxdara-review")
        self.assertNotIn("dependencies", manifest)
        agents = list((PLUGIN / "agents").glob("*.md"))
        self.assertEqual(len(agents), 4)
        names = set()
        for path in agents:
            data, body = metadata(path)
            names.add("voxdara-review:" + data["name"])
            self.assertEqual(data["name"], path.stem)
            self.assertIsInstance(data["description"], str)
            self.assertGreater(len(data["description"]), 80)
            self.assertIn("When to invoke", body)
            self.assertEqual(data["model"], "inherit")
            self.assertEqual(data["tools"], ["Read", "Grep", "Glob"])
            self.assertNotIn("permissionMode", data)  # Ignored for plugin agents.
            self.assertNotIn("hooks", data)
        self.assertEqual(names, guard.REVIEWERS)
        skill, body = metadata(PLUGIN / "skills/voxdara-review/SKILL.md")
        self.assertEqual(skill["name"], "voxdara-review")
        self.assertIs(skill["disable-model-invocation"], True)
        self.assertIs(skill["user-invocable"], True)
        self.assertNotIn("context", skill)  # Serena reconnaissance stays in main.
        self.assertNotIn("Bash", skill["allowed-tools"])
        self.assertIn("independently CONFIRMED", body)
        self.assertIn("confidence >=80", body)
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())
        rule = hooks["hooks"]["PreToolUse"][0]
        self.assertEqual(rule["matcher"], ".*")
        self.assertEqual(rule["hooks"][0]["command"], "python")
        self.assertEqual(rule["hooks"][0]["args"],
                         ["-B", "${CLAUDE_PLUGIN_ROOT}/hooks/read_only.py"])

    def test_real_inspection_and_safe_git(self):
        for event in [self.event("Read", file_path="AGENTS.md"),
                      self.event("Read", file_path="eval/EVAL_V1.md"),
                      self.event("Grep", path="tools/voxdara_experiment.py"),
                      self.event("Glob", pattern="tests/*.py"),
                      self.event("mcp__serena__find_symbol",
                                 relative_path="tools/voxdara_experiment.py"),
                      self.event("Agent", subagent_type="voxdara-review:logic-reviewer")]:
            self.assertTrue(guard.permitted(event), event["tool_name"])
        for command in ["git -c core.fsmonitor=false --no-optional-locks status --short --untracked-files=all --ignore-submodules=all",
                        "git merge-base main HEAD",
                        "git diff --no-ext-diff --no-textconv --name-only main...HEAD",
                        "git diff --no-ext-diff --no-textconv HEAD -- tools/deleted_file.py",
                        "git diff --no-ext-diff --no-textconv --cached HEAD -- AGENTS.md"]:
            self.assertTrue(guard.permitted(self.event("Bash", command=command)), command)

    def test_mutation_remote_and_scope_bypasses_are_denied(self):
        for tool in ["Write", "Edit", "PowerShell", "NotebookEdit", "WebFetch",
                     "mcp__serena__execute_shell_command", "mcp__serena__replace_symbol_body",
                     "mcp__other__read_file"]:
            self.assertFalse(guard.permitted(self.event(tool)))
        for path in ["training/data/voxdara-cleanup-train-v2.jsonl",
                     "eval/voxdara-cleanup-eval-v1.jsonl",
                     "benchmarks/base-qwen3.5-0.8b/results.jsonl",
                     ".claude/settings.json", "../Voxdara/.git/config", "../AGENTS.md"]:
            self.assertFalse(guard.permitted(self.event("Read", file_path=path)), path)
        for command in ["git push", "git commit", "git checkout main", "git switch main",
                        "git status --short --ignore-submodules=all",
                        "git status --short --untracked-files=all --ignore-submodules=all",
                        "git -c core.fsmonitor=false status --short --untracked-files=all --ignore-submodules=all",
                        "git --no-optional-locks status --short --untracked-files=all --ignore-submodules=all",
                        "git -c core.fsmonitor=false --no-optional-locks status --short --untracked-files=all --ignore-submodules=all; git push",
                        "git diff main", "git diff --output=x",
                        "git status --short --ignore-submodules=all; git push",
                        "git diff --no-ext-diff --no-textconv -- main '$(git push)'",
                        "git diff --no-ext-diff --no-textconv HEAD -- eval/voxdara-cleanup-eval-v1.jsonl",
                        "git -c alias.x='!git push' x", "python tools/voxdara_experiment.py benchmark"]:
            self.assertFalse(guard.permitted(self.event("Bash", command=command)), command)
        self.assertFalse(guard.permitted(self.event("Grep", path=".")))
        self.assertFalse(guard.permitted(self.event("Glob", pattern="../../*")))
        self.assertFalse(guard.permitted(self.event("Agent", subagent_type="general-purpose")))
        self.assertFalse(guard.permitted(self.event("Agent", subagent_type="voxdara-review:logic-reviewer",
                                                   run_in_background=True)))
        outside = self.event("Read", file_path="AGENTS.md")
        outside["cwd"] = str(ROOT.parent)
        self.assertFalse(guard.permitted(outside))

    def test_hook_process_denies_malformed_input_and_retains_permissions(self):
        for payload, code in [("not json", 2), ("[]", 2),
                              (json.dumps(self.event("Write", file_path="AGENTS.md")), 2),
                              (json.dumps(self.event("Read", file_path="AGENTS.md")), 0)]:
            result = subprocess.run(launcher.guard_command(),
                                    input=payload, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, code)
            self.assertNotIn("AGENTS.md", result.stdout + result.stderr)
            if code == 0:
                self.assertEqual(json.loads(result.stdout), {})  # Never auto-approve.

    def test_changed_or_missing_suite_never_executes(self):
        for response in [dict(return_value=b"changed"), dict(side_effect=OSError("missing"))]:
            output = io.StringIO()
            with patch.object(guard.Path, "read_bytes", **response), \
                    patch.object(guard.subprocess, "run") as runner, \
                    contextlib.redirect_stdout(output):
                self.assertEqual(guard.offline_tests(), 1)
            runner.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())["reason"], "OFFLINE_SUITE_CHANGED")

    def test_offline_evidence_redacts_failure_output(self):
        result = subprocess.CompletedProcess([], 1, b"private transcript", b"secret credential")
        output = io.StringIO()
        with patch.object(guard.subprocess, "run", return_value=result), \
                contextlib.redirect_stdout(output):
            self.assertEqual(guard.offline_tests(), 1)
        evidence = json.loads(output.getvalue())
        self.assertEqual(evidence["exit_code"], 1)
        self.assertEqual(evidence["output_bytes"], len(result.stdout + result.stderr))
        self.assertNotIn("private transcript", output.getvalue())
        self.assertNotIn("secret credential", output.getvalue())

    def test_unavailable_offline_suite_is_an_evidence_gap(self):
        output = io.StringIO()
        with patch.object(guard.subprocess, "run", side_effect=subprocess.TimeoutExpired("test", 120)), \
                contextlib.redirect_stdout(output):
            self.assertEqual(guard.offline_tests(), 1)
        self.assertEqual(json.loads(output.getvalue())["reason"], "OFFLINE_SUITE_UNAVAILABLE")

    def test_launcher_uses_only_session_configuration(self):
        with patch.object(launcher.subprocess, "run", side_effect=[
                subprocess.CompletedProcess([], 2, "", "VOXDARA_READ_ONLY_DENIED: synthetic"),
                subprocess.CompletedProcess([], 0, "{}", ""),
                subprocess.CompletedProcess([], 7)]) as run:
            self.assertEqual(launcher.main(), 7)
        self.assertEqual(run.call_count, 3)
        for call, tool in zip(run.call_args_list[:2], ["Write", "Read"]):
            self.assertEqual(call.args[0], launcher.guard_command())
            self.assertEqual(json.loads(call.kwargs["input"])["tool_name"], tool)
        args, options = run.call_args
        command = args[0]
        self.assertEqual(options["cwd"], ROOT)
        self.assertEqual(options["env"]["DISABLE_AUTOUPDATER"], "1")
        self.assertEqual(options["env"]["CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL"], "1")
        self.assertEqual(command[command.index("--permission-mode") + 1], "manual")
        self.assertEqual(command[command.index("--setting-sources") + 1], "project")
        self.assertIn("--strict-mcp-config", command)
        mcp = json.loads(command[command.index("--mcp-config") + 1])
        self.assertEqual(set(mcp["mcpServers"]), {"serena"})
        server = mcp["mcpServers"]["serena"]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["args"],
                         ["start-mcp-server", "--context", "claude-code", "--project", str(ROOT)])
        self.assertEqual(command[command.index("--tools") + 1],
                         "Read,Grep,Glob,Agent,Skill,Bash,ToolSearch")
        self.assertEqual(json.loads(command[command.index("--settings") + 1]),
                         {"remoteControlAtStartup": False})

    def test_actual_configured_guard_preflight(self):
        hook = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]
        self.assertEqual(launcher.guard_command(), [hook["command"], *[
            arg.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN)) for arg in hook["args"]]])
        launcher.guard_preflight(os.environ.copy())  # Real configured executable, no sys.executable shortcut.

    def test_launcher_missing_configured_executable_never_starts_claude(self):
        config = json.loads((PLUGIN / "hooks/hooks.json").read_text())
        config["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "voxdara-nonexistent-hook-executable"
        with patch.object(launcher.Path, "read_text", return_value=json.dumps(config)), \
                patch.object(launcher.subprocess, "run") as run, \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(launcher.main(), 1)
        run.assert_not_called()
        self.assertIn("Claude was not launched", error.getvalue())

    def test_launcher_invalid_guard_self_test_never_starts_claude(self):
        for results in [
                [subprocess.CompletedProcess([], 0, "{}", "")],
                [subprocess.CompletedProcess([], 2, "", "unrelated crash")],
                [subprocess.CompletedProcess([], 2, "", "VOXDARA_READ_ONLY_DENIED:"),
                 subprocess.CompletedProcess([], 0, '{"permissionDecision":"allow"}', "")],
                [OSError("cannot spawn configured guard")],
                [subprocess.TimeoutExpired("configured guard", 10)]]:
            with self.subTest(results=results), \
                    patch.object(launcher.subprocess, "run", side_effect=results) as run, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(launcher.main(), 1)
            self.assertTrue(all(call.args[0] == launcher.guard_command() for call in run.call_args_list))

    def test_missing_serena_never_starts_claude(self):
        with patch.object(launcher, "guard_preflight"), \
                patch.object(launcher.shutil, "which", return_value=None), \
                patch.object(launcher.subprocess, "run") as run, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.main(), 1)
        run.assert_not_called()

    def test_hardened_status_enumerates_files_without_index_refresh(self):
        command = "git -c core.fsmonitor=false --no-optional-locks status --short --untracked-files=all --ignore-submodules=all"
        self.assertTrue(guard.safe_git(command))
        _, skill = metadata(PLUGIN / "skills/voxdara-review/SKILL.md")
        self.assertIn("`" + command + "`", skill)
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                                      text=True, check=True)
            git("init", "--quiet")
            tracked = repo / "tracked.txt"
            tracked.write_text("tracked\n")
            git("add", "tracked.txt")
            git("config", "core.fsmonitor", "voxdara-nonexistent-fsmonitor")
            os.utime(tracked, ns=(tracked.stat().st_atime_ns, tracked.stat().st_mtime_ns + 1_000_000_000))
            (repo / "phase").mkdir()
            for name in ["one.txt", "two.txt"]:
                (repo / "phase" / name).write_text("synthetic\n")
            index = repo / ".git/index"
            before = (hashlib.sha256(index.read_bytes()).hexdigest(),
                      index.stat().st_mtime_ns, index.stat().st_size)
            result = git(*shlex.split(command)[1:])
            self.assertIn("?? phase/one.txt", result.stdout.splitlines())
            self.assertIn("?? phase/two.txt", result.stdout.splitlines())
            self.assertNotIn("fsmonitor", result.stderr.lower())
            self.assertEqual(before, (hashlib.sha256(index.read_bytes()).hexdigest(),
                                      index.stat().st_mtime_ns, index.stat().st_size))


if __name__ == "__main__":
    unittest.main()
