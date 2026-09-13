"""Deny by default. No tool arguments or repository contents are logged."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
SERENA_INSPECTION = {
    "initial_instructions", "get_symbols_overview", "find_symbol",
    "find_referencing_symbols", "search_for_pattern",
}
REVIEWERS = {
    "voxdara-review:logic-reviewer", "voxdara-review:integrity-reviewer",
    "voxdara-review:failure-reviewer", "voxdara-review:finding-validator",
}
GIT_METADATA = {
    ("-c", "core.fsmonitor=false", "--no-optional-locks", "status", "--short",
     "--untracked-files=all", "--ignore-submodules=all"),
    ("rev-parse", "--show-toplevel"), ("rev-parse", "HEAD"),
    ("rev-parse", "main"), ("branch", "--show-current"),
    ("merge-base", "main", "HEAD"),
    ("rev-list", "--left-right", "--count", "main...HEAD"),
    ("log", "--oneline", "main..HEAD"),
}


def safe_path(value, *, file_only=False):
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if not path.is_relative_to(ROOT) or (file_only and not path.is_file()):
        return False
    parts = tuple(p.lower() for p in path.relative_to(ROOT).parts)
    if not parts:
        return False  # Require scoped inspection; no recursive repository reads.
    return not (
        parts[0] in {".git", "benchmarks", "unsloth_compiled_cache"}
        or (parts[0] == "eval" and parts != ("eval", "eval_v1.md"))
        or parts[:2] == ("training", "data")
        or "runs" in parts or "node_modules" in parts or ".venv" in parts
        or path.suffix.lower() in {".safetensors", ".bin", ".pt", ".pth", ".ckpt"}
        or any(p.startswith(".env") or p in {"settings.json", "settings.local.json"}
               for p in parts)
    )


def safe_git(command):
    # Shell composition, expansion, redirection and escaped metacharacters are forbidden.
    if not isinstance(command, str) or re.search(r"[\n\r;&|<>`$\\]", command):
        return False
    args = shlex.split(command)
    if not args or args[0] != "git":
        return False
    if tuple(args[1:]) in GIT_METADATA:
        return True
    if args[1:4] != ["diff", "--no-ext-diff", "--no-textconv"]:
        return False
    rest = args[4:]
    metadata_only = bool(rest and rest[0] in {"--name-only", "--stat", "--numstat"})
    if metadata_only:
        rest = rest[1:]
    if rest and rest[0] == "--cached":
        rest = rest[1:]
    if rest and (rest[0] in {"main", "HEAD", "main...HEAD"}
                 or re.fullmatch(r"[0-9a-f]{40}", rest[0])):
        rest = rest[1:]
    if not rest:
        return metadata_only
    # Exact pathspecs only; allow deleted files without opening data or directories.
    return (rest[0] == "--" and len(rest) > 1
            and all(re.fullmatch(r"[A-Za-z0-9_ ./-]+", p) and safe_path(p)
                    and not (ROOT / p).is_dir() for p in rest[1:]))


def permitted(event):
    if event.get("hook_event_name") != "PreToolUse":
        return False
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or Path(cwd).resolve() != ROOT:
        return False
    tool, args = event.get("tool_name"), event.get("tool_input", {})
    if not isinstance(args, dict):
        return False
    if tool == "Read":
        return safe_path(args.get("file_path"), file_only=True)
    if tool == "Grep":
        return safe_path(args.get("path"), file_only=True)
    if tool == "Glob":
        path = args.get("path", str(ROOT))
        pattern = args.get("pattern")
        return (isinstance(path, str) and isinstance(pattern, str)
                and not Path(pattern).is_absolute()
                and ".." not in pattern.replace("\\", "/").split("/")
                and (Path(path).resolve() == ROOT or safe_path(path)))
    if tool == "ToolSearch":
        return True  # Discovery only; every discovered tool is independently gated.
    if tool in {"Agent", "Task"}:
        return (args.get("subagent_type") in REVIEWERS
                and args.get("isolation") is None
                and not args.get("run_in_background", False))
    if tool == "Bash":
        return safe_git(args.get("command"))
    if isinstance(tool, str) and tool.startswith("mcp__serena__"):
        name = tool.removeprefix("mcp__serena__")
        if name == "initial_instructions":
            return True
        return (name in SERENA_INSPECTION
                and safe_path(args.get("relative_path"), file_only=True))
    return False


def offline_tests():
    # Only the inspected offline suite; changed executable inputs need human review.
    pinned = {
        "tools/voxdara_experiment.py": "D479E47D16BB4354F365B16856EDF69BDF55DB371E21AFD6D8B6D92B90B163F4",
        "tests/test_voxdara_experiment.py": "CADD5C56F76EF995FE75F765D833CE92F18DFDD16AA6F6DAC10C8282EABB640C",
    }
    try:
        unchanged = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest().upper() == h
                        for p, h in pinned.items())
    except OSError:
        unchanged = False
    if not unchanged:
        print(json.dumps({"status": "NEEDS_EVIDENCE", "reason": "OFFLINE_SUITE_CHANGED"}))
        return 1
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "tests/test_voxdara_experiment.py"],
            cwd=ROOT, capture_output=True, timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        print(json.dumps({"status": "NEEDS_EVIDENCE", "reason": "OFFLINE_SUITE_UNAVAILABLE"}))
        return 1
    output = result.stdout + result.stderr
    print(json.dumps({"exit_code": result.returncode, "output_bytes": len(output),
                      "output_sha256": hashlib.sha256(output).hexdigest().upper(),
                      "source": "personally executed pinned offline suite"}))
    return result.returncode


if __name__ == "__main__":
    if sys.argv[1:] == ["--tests"]:
        sys.exit(offline_tests())  # Human-invoked only; not allowed as a reviewer tool.
    try:
        allowed = not sys.argv[1:] and permitted(json.load(sys.stdin))
    except Exception:
        allowed = False
    if not allowed:
        print("VOXDARA_READ_ONLY_DENIED: unapproved tool, scope or input", file=sys.stderr)
        sys.exit(2)
    print("{}")  # No automatic approval; retain Claude's normal permission checks.
