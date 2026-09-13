# Voxdara Independent Review Harness v1

From `C:\Projects\Voxdara`, validate the local files, then start a **dedicated**
review session (Claude Code 2.1.270 was inspected):

```powershell
python -B -m unittest tests/test_review_harness.py
claude plugin validate .claude/plugins/voxdara-review --strict --json
python -B .claude/plugins/voxdara-review/review.py
```

In that session, check `/hooks` shows this plugin's PreToolUse command, `/skills`
shows `voxdara-review:voxdara-review`, and typing `@voxdara-review:` shows these
four registered agents (the `/agents` wizard is removed in 2.1.270):
`voxdara-review:logic-reviewer`, `voxdara-review:integrity-reviewer`,
`voxdara-review:failure-reviewer`, `voxdara-review:finding-validator`.
Then invoke **`/voxdara-review:voxdara-review`**. No installation, marketplace,
configuration edit, PR or external review plugin is required. Restart the session
after editing plugin metadata; command/skill validation alone is not load proof.
Do not use this dedicated session for implementation: the guard lasts until exit.
The launcher disables automatic updater/IDE installation and remote-control
startup only in its child session, removes mutation built-ins from the tool pool,
and keeps manual permission checks. It persists no configuration.
It loads project settings and this explicit plugin, excluding user/local settings
that enable unrelated plugins. Authentication is unchanged. MCP connections are
replaced for this child session by an explicit Serena-only
`--mcp-config` with `--strict-mcp-config`. The installed `serena` executable is
resolved from PATH and starts with `--context claude-code --project <repo-root>`.
Unrelated connector MCPs are excluded; global configuration is unchanged.

The main session establishes Git identity/scope, uses Serena reconnaissance,
provides compact evidence to three independent reviewers, sends each candidate
to a fresh disproof validator, confirms structures with Serena again, and emits
confirmed findings plus `CODEX REPAIR HANDOFF`. Read-only built-in fallback is
explicit when Serena is unavailable; material gaps cannot PASS. All reviewer
metadata uses simple descriptions and inherited models. No Serena in subagents.

The plugin's one necessary PreToolUse guard uses the documented exec form
(`command` plus `args`), without a shell or shell-environment setup. It applies
session-wide, including
subagents, and denies unknown/mutation tools by default. The guard grants **no
automatic approval**; the skill pre-approves inspection and reviewer dispatch
only, retaining ordinary permission checks for other accepted calls. Only fixed
Git metadata commands and content diffs are accepted. Status uses
`git -c core.fsmonitor=false --no-optional-locks status --short --untracked-files=all --ignore-submodules=all`
for individual untracked enumeration without optional index refresh or fsmonitor;
content diffs use `--no-ext-diff --no-textconv` and explicit safe files. Read/Grep and
Serena inspect explicit safe repository files; Glob lists scoped filenames.
Raw datasets, historical transcripts, local settings/secrets and model artifacts
are excluded. Only the four foreground review agents can be dispatched. No
shell composition, arbitrary processes/tests, PowerShell or remote tools.

Human-invoked offline regression evidence (no ML execution):

```powershell
python -B .claude/plugins/voxdara-review/hooks/read_only.py --tests
```

This captures output locally and returns exit code, length and hash only. It pins
the inspected experiment tool/test bytes; changed executable inputs yield
`NEEDS_EVIDENCE / OFFLINE_SUITE_CHANGED`. Reviewers must obtain human-reviewed
offline test evidence for future changed suites. They never run changed code
blindly. Run the ordinary suite yourself for full local failure diagnostics:
`python -B -m unittest tests/test_voxdara_experiment.py`.

## Verification and limitations

The metadata/guard tests independently use **already installed PyYAML**; there is
no new production dependency. They exercise accepted inspection, tool/command/
path denial and malformed-hook fail-closed behavior. Missing Python/hook runtime
or disabled/managed-blocked hooks is an invocation blocker. The launcher resolves
and executes the actual `hooks.json` command/arguments against a synthetic denied
Write and an accepted Read before starting Claude; execution or self-test failure
aborts startup. Keep the plugin and PATH trusted and unchanged during the session.
Before reviewing,
verify hook registration and executable guard behavior, not only manifest JSON.
For runtime probes use ordinary startup/interactive discovery and direct agent
selection; do not rely solely on print-mode slash-command execution.

No agent prompt can prove model obedience. The guard controls exposed tool calls,
not Claude's own session storage, trusted local lifecycle hooks, or a human who
disables the plugin. Files/configuration must stay trusted and unchanged during
review. This is a Claude tool boundary, not an OS sandbox. Tool errors, reviewer
failure, unavailable validation or conflicting evidence remain explicit gaps.
The installed tool names/server ID are `Agent` and `mcp__serena__`; a renamed
Serena server fails closed and requires explicit built-in fallback. Read/Grep are
file-scoped; structural reconnaissance must target files, not recursive roots.

The requested verdict policy leaves HIGH-only findings without a defined
PASS/BLOCKED disposition. Such reviews use NEEDS_HUMAN_REVIEW. MEDIUM findings
may coexist with PASS; unvalidated candidates never enter the repair handoff.
Live PEFT resolution stays NOT_VERIFIED; this plugin does not resolve that gate.

Design references were the installed official plugin-dev plugin, especially
plugin-structure, agent-development and hook-development guidance, plus official
[skills](https://code.claude.com/docs/en/skills),
[subagents](https://code.claude.com/docs/en/sub-agents) and
[hooks](https://code.claude.com/docs/en/hooks) documentation. The installed agent
validator still suggests inline `<example>` blocks despite its guidance favoring
plain descriptions, and its hook validator expects direct event keys despite
the documented plugin wrapper. Its agent script also exits on the first warning
because of `set -e` with a zero-valued post-increment; the hook script requires
`jq`, which is absent locally and misleadingly reports invalid JSON. Claude's
directory validator returned empty contents, so independent parsing and runtime
discovery are required. These tools are aids, not runtime dependencies.

Verified locally: strict manifest validation with zero warnings; independent
PyYAML parsing and guard regression checks; all 19 existing offline tests; `/skills`
discovery; all four agents in `@` typeahead and runtime initialization; plugin
PreToolUse in `/hooks`; selected reviewer runtime tool pool exactly
`Read, Grep, Glob`. The ordinary print prompt timed out after emitting initialization.
A model-driven harmless command-denial probe was interrupted on connection
refusal (firewall/proxy), so end-to-end review and live model-driven hook denial
remain NOT_VERIFIED. The existing shell-form Serena lifecycle hook also hit
sandbox session-env permissions; this plugin uses exec-form hooks instead.
